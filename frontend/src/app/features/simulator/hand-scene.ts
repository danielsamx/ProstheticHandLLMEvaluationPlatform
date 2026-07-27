/**
 * Three.js scene for the prosthetic hand simulator.
 *
 * Safety model, unchanged from the backend's:
 *
 *  * The hand has NO manual pose controls. `applyPose` is the only movement
 *    entry point, and it is fed exclusively by validated backend frames.
 *  * Angles are clamped to the mechanical limits published by `/hand/spec`
 *    before they reach a transform, so even a bug upstream cannot render a
 *    physically impossible pose.
 *  * The CAMERA is user-controlled — orbit and zoom. Moving the viewpoint is
 *    not moving the prosthesis, so it costs nothing in safety terms and makes
 *    the pose far easier to inspect.
 */

import { signal } from '@angular/core';
import * as THREE from 'three';
import { OrbitControls } from 'three/examples/jsm/controls/OrbitControls.js';
import { RoomEnvironment } from 'three/examples/jsm/environments/RoomEnvironment.js';
import { GLTFLoader } from 'three/examples/jsm/loaders/GLTFLoader.js';
import { RGBELoader } from 'three/examples/jsm/loaders/RGBELoader.js';

import { HandSpec, Handedness, JointAngle, JointSpec } from '@core/models/hand.model';
import { HandRig, Side, buildHandRig, captureRestPose } from './hand-rig';
import { disposeSharedSkin } from './skin-textures';

const DEG2RAD = Math.PI / 180;

interface JointTrack {
  pivot: THREE.Object3D;
  rest: THREE.Euler;
  spec: JointSpec;
  from: number;
  to: number;
  current: number;
}

export interface SceneStats {
  fps: number;
  triangles: number;
  animating: boolean;
}

export class HandScene {
  private renderer!: THREE.WebGLRenderer;
  private scene!: THREE.Scene;
  private camera!: THREE.PerspectiveCamera;
  private controls!: OrbitControls;
  private rig!: HandRig;
  private pmrem!: THREE.PMREMGenerator;
  private handedness: Handedness = 'right';
  /**
   * Both hands, built once and kept.
   *
   * Switching used to tear the rig down and rebuild it, which meant
   * regenerating the skin textures and every lofted surface — around a second
   * of frozen UI per toggle. Keeping both and flipping `visible` makes the
   * switch a single frame, at the cost of one extra mesh tree in memory.
   */
  private rigs = new Map<Side, HandRig>();

  private tracks = new Map<string, JointTrack>();
  private jointSpecs = new Map<string, JointSpec>();
  /** Latest committed angle per joint, preserved across a handedness rebuild. */
  private lastAngles = new Map<string, number>();

  private animationStart = 0;
  private animationDuration = 0;
  private animating = false;

  private frameHandle = 0;
  private resizeObserver?: ResizeObserver;
  private clock = new THREE.Clock();
  private frames = 0;
  private fpsAccumulator = 0;

  /** Exposed as a signal so the zoneless template updates without polling. */
  readonly stats = signal<SceneStats>({ fps: 0, triangles: 0, animating: false });

  // ── Lifecycle ─────────────────────────────────────────────────────────────

  init(container: HTMLElement, spec: HandSpec | null, handedness: Handedness = 'right'): void {
    this.handedness = handedness;

    this.renderer = new THREE.WebGLRenderer({
      antialias: true,
      alpha: true,
      powerPreference: 'high-performance',
    });
    this.renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2));
    this.renderer.setSize(container.clientWidth, container.clientHeight);
    this.renderer.shadowMap.enabled = true;
    this.renderer.shadowMap.type = THREE.PCFSoftShadowMap;
    this.renderer.toneMapping = THREE.ACESFilmicToneMapping;
    this.renderer.toneMappingExposure = 1.0;
    this.renderer.outputColorSpace = THREE.SRGBColorSpace;
    container.appendChild(this.renderer.domElement);

    this.scene = new THREE.Scene();
    this.scene.background = null;

    this.camera = new THREE.PerspectiveCamera(
      32, container.clientWidth / container.clientHeight, 0.05, 100,
    );
    this.camera.position.set(1.35, 0.55, 2.15);

    this.setupControls(container);
    this.setupEnvironment();
    this.setupLights();
    this.setupGround();

    this.buildRig();

    if (spec) this.applySpec(spec);

    this.resizeObserver = new ResizeObserver(() => this.resize(container));
    this.resizeObserver.observe(container);

    this.clock.start();
    this.loop();

    // Build the other hand during an idle slot so even the first toggle is
    // instant. Geometry only — the expensive textures are already shared.
    const other: Side = handedness === 'right' ? 'left' : 'right';
    const warm = () => this.rigFor(other);
    if ('requestIdleCallback' in window) {
      (window as unknown as { requestIdleCallback: (cb: () => void) => void })
        .requestIdleCallback(warm);
    } else {
      setTimeout(warm, 400);
    }
  }

  dispose(): void {
    cancelAnimationFrame(this.frameHandle);
    this.resizeObserver?.disconnect();
    this.controls?.dispose();
    this.rigs.forEach((rig) => rig.dispose());
    this.rigs.clear();
    disposeSharedSkin();
    this.pmrem?.dispose();
    this.renderer?.dispose();
    this.renderer?.domElement.remove();
  }

  // ── Camera ────────────────────────────────────────────────────────────────

  /**
   * Orbit, zoom and pan.
   *
   * The hand itself stays fixed in world space; the user moves around it.
   * Damping is on because an undamped orbit on a trackpad feels twitchy, and
   * the distance is clamped so the camera cannot end up inside the palm or so
   * far away that the pose is unreadable.
   */
  private setupControls(container: HTMLElement): void {
    this.controls = new OrbitControls(this.camera, container);
    this.controls.target.set(0, 0.12, 0);
    this.controls.enableDamping = true;
    this.controls.dampingFactor = 0.08;
    this.controls.rotateSpeed = 0.85;
    this.controls.zoomSpeed = 0.9;
    this.controls.panSpeed = 0.6;
    this.controls.minDistance = 0.85;
    this.controls.maxDistance = 6.0;
    // Stop just short of the poles: passing through them flips the up vector
    // and the hand appears to snap upside down.
    this.controls.minPolarAngle = 0.15;
    this.controls.maxPolarAngle = Math.PI - 0.15;
    this.controls.update();
  }

  resetCamera(): void {
    this.camera.position.set(1.35, 0.55, 2.15);
    this.controls.target.set(0, 0.12, 0);
    this.controls.update();
  }

  // ── Scene setup ───────────────────────────────────────────────────────────

  /**
   * Image-based lighting from a procedurally generated room.
   *
   * A real .hdr probe would be marginally better, but the platform has to work
   * on an air-gapped research machine, so the default environment ships as
   * geometry rather than a download. `loadHdri` swaps in a real probe when one
   * is available.
   */
  private setupEnvironment(): void {
    this.pmrem = new THREE.PMREMGenerator(this.renderer);
    this.pmrem.compileEquirectangularShader();
    const environment = this.pmrem.fromScene(new RoomEnvironment(), 0.04);
    this.scene.environment = environment.texture;
    this.scene.environmentIntensity = 1.0;
  }

  /** Swap in a real HDRI probe (equirectangular .hdr). */
  loadHdri(url: string): Promise<void> {
    return new Promise((resolve, reject) => {
      new RGBELoader().load(
        url,
        (texture) => {
          texture.mapping = THREE.EquirectangularReflectionMapping;
          const environment = this.pmrem.fromEquirectangular(texture);
          this.scene.environment = environment.texture;
          texture.dispose();
          resolve();
        },
        undefined,
        (error) => reject(error),
      );
    });
  }

  private setupLights(): void {
    // Three-point rig on top of the IBL: key for shape, fill to open the
    // shadows, rim to separate the hand from the white background.
    const key = new THREE.DirectionalLight(0xfff2e8, 2.4);
    key.position.set(2.4, 3.2, 2.2);
    key.castShadow = true;
    key.shadow.mapSize.set(2048, 2048);
    key.shadow.camera.near = 0.5;
    key.shadow.camera.far = 12;
    key.shadow.camera.left = -1.8;
    key.shadow.camera.right = 1.8;
    key.shadow.camera.top = 1.8;
    key.shadow.camera.bottom = -1.8;
    key.shadow.bias = -0.0007;
    key.shadow.normalBias = 0.018;
    key.shadow.radius = 7; // soft penumbra
    this.scene.add(key);

    const fill = new THREE.DirectionalLight(0xdce9ff, 0.85);
    fill.position.set(-2.6, 1.1, 1.5);
    this.scene.add(fill);

    // Navy rim from behind, echoing the interface palette.
    const rim = new THREE.SpotLight(0x2f6fb0, 16, 9, Math.PI / 7, 0.7, 2);
    rim.position.set(-1.2, 2.0, -2.4);
    this.scene.add(rim);

    this.scene.add(new THREE.HemisphereLight(0xffffff, 0xd6dee6, 0.55));
  }

  private setupGround(): void {
    // A shadow catcher rather than a visible floor: on a white background the
    // pose reads best when only its contact shadow anchors it.
    const ground = new THREE.Mesh(
      new THREE.PlaneGeometry(16, 16),
      new THREE.ShadowMaterial({ opacity: 0.20, color: 0x001f3f }),
    );
    ground.rotation.x = -Math.PI / 2;
    ground.position.y = -0.95;
    ground.receiveShadow = true;
    this.scene.add(ground);
  }

  // ── Rig ───────────────────────────────────────────────────────────────────

  /** Build a side once, then reuse it. */
  private rigFor(side: Side): HandRig {
    const existing = this.rigs.get(side);
    if (existing) return existing;

    const rig = buildHandRig(side);
    rig.root.position.y = 0.06;
    rig.root.rotation.x = -0.14;
    rig.root.visible = false;
    this.scene.add(rig.root);
    this.rigs.set(side, rig);
    return rig;
  }

  private buildRig(): void {
    this.rig = this.rigFor(this.handedness);
    this.rig.root.visible = true;
    this.bindTracks();
  }

  /**
   * Show the other hand.
   *
   * The two rigs are separate geometry rather than one mirrored by
   * `scale.x = -1`: a negative scale inverts every surface normal and wrecks
   * both the lighting and the shadow terminator. The first switch pays for
   * building the second rig (geometry only — textures are already shared);
   * every switch after that is a visibility flip.
   *
   * The current pose carries across, so toggling hands mid-experiment does not
   * silently reset the display to rest.
   */
  setHandedness(handedness: Handedness): void {
    if (!this.rig || this.handedness === handedness) {
      this.handedness = handedness;
      return;
    }

    this.tracks.forEach((track, id) => this.lastAngles.set(id, track.current));

    this.rig.root.visible = false;
    this.handedness = handedness;
    this.buildRig();

    // Reapply the pose immediately rather than animating into it.
    this.tracks.forEach((track, id) => {
      const angle = this.lastAngles.get(id) ?? track.spec.min_flexion_deg;
      track.from = angle;
      track.to = angle;
      track.current = angle;
      this.commit(track);
    });
  }

  applySpec(spec: HandSpec): void {
    this.jointSpecs.clear();
    for (const joint of spec.joints) this.jointSpecs.set(joint.id, joint);
    this.bindTracks();
  }

  private bindTracks(): void {
    if (!this.rig) return;
    const rest = captureRestPose(this.rig);
    this.tracks.clear();

    this.rig.pivots.forEach((pivot, id) => {
      const spec = this.jointSpecs.get(id);
      if (!spec) return;
      const current = this.lastAngles.get(id) ?? 0;
      this.tracks.set(id, {
        pivot,
        spec,
        rest: rest.get(id) ?? pivot.rotation.clone(),
        from: current,
        to: current,
        current,
      });
    });
  }

  // ── The only movement entry point ─────────────────────────────────────────

  /**
   * Apply a validated pose.
   *
   * Angles are clamped against the backend's own mechanical limits before being
   * committed, which makes an out-of-range render structurally impossible.
   */
  applyPose(joints: JointAngle[], durationMs: number): void {
    if (!this.tracks.size) return;

    for (const frame of joints) {
      const track = this.tracks.get(frame.joint_id);
      if (!track) continue;
      track.from = track.current;
      track.to = Math.min(
        track.spec.max_flexion_deg,
        Math.max(track.spec.min_flexion_deg, frame.angle_deg),
      );
    }

    this.animationStart = performance.now();
    this.animationDuration = Math.max(120, durationMs || 600);
    this.animating = true;
  }

  /** Return to the neutral open pose (end-of-session requirement). */
  resetToRest(durationMs = 700): void {
    this.tracks.forEach((track) => {
      track.from = track.current;
      track.to = track.spec.min_flexion_deg;
    });
    this.animationStart = performance.now();
    this.animationDuration = durationMs;
    this.animating = true;
  }

  /**
   * Replace the procedural mesh with an external rigged model.
   *
   * The slot exists so a photogrammetry-grade hand can be dropped in without
   * touching the control logic: bones are matched by name against the backend
   * joint ids (D0, D1_P … D5_D), case-insensitively.
   */
  loadGltf(url: string): Promise<void> {
    return new Promise((resolve, reject) => {
      new GLTFLoader().load(
        url,
        (gltf) => {
          const pivots = new Map<string, THREE.Object3D>();
          gltf.scene.traverse((object) => {
            const id = object.name.toUpperCase();
            if (this.jointSpecs.has(id)) pivots.set(id, object);
            object.castShadow = true;
            object.receiveShadow = true;
          });

          if (pivots.size === 0) {
            reject(new Error(
              'The GLTF contains no nodes named after the HANDi joint ids ' +
              '(D0, D1_P, D1_D, D2_P … D5_D). Rename the bones and retry.',
            ));
            return;
          }

          this.scene.remove(this.rig.root);
          this.rig.dispose();
          this.rig = {
            root: gltf.scene as unknown as THREE.Group,
            side: this.handedness,
            pivots,
            dispose: () => gltf.scene.clear(),
          };
          this.scene.add(this.rig.root);
          this.bindTracks();
          resolve();
        },
        undefined,
        (error) => reject(error),
      );
    });
  }

  // ── Render loop ───────────────────────────────────────────────────────────

  private loop = (): void => {
    this.frameHandle = requestAnimationFrame(this.loop);
    const delta = this.clock.getDelta();

    this.step();
    this.controls.update();
    this.renderer.render(this.scene, this.camera);

    this.frames++;
    this.fpsAccumulator += delta;
    if (this.fpsAccumulator >= 0.5) {
      this.stats.set({
        fps: Math.round(this.frames / this.fpsAccumulator),
        triangles: this.renderer.info.render.triangles,
        animating: this.animating,
      });
      this.frames = 0;
      this.fpsAccumulator = 0;
    }
  };

  private step(): void {
    if (!this.animating) return;

    const elapsed = performance.now() - this.animationStart;
    const raw = Math.min(1, elapsed / this.animationDuration);
    const t = this.easeInOutCubic(raw);

    this.tracks.forEach((track, id) => {
      track.current = track.from + (track.to - track.from) * t;
      this.lastAngles.set(id, track.current);
      this.commit(track);
    });

    if (raw >= 1) this.animating = false;
  }

  private commit(track: JointTrack): void {
    const radians = track.current * DEG2RAD;
    const rest = track.rest;

    if (track.spec.axis === 'y') {
      // Thumb opposition rotates about the palm normal rather than flexing.
      const direction = this.handedness === 'left' ? 1 : -1;
      track.pivot.rotation.set(rest.x, rest.y + direction * radians, rest.z);
    } else {
      // Flexion curls the digit towards the palm: negative about local X.
      track.pivot.rotation.set(rest.x - radians, rest.y, rest.z);
    }
  }

  private easeInOutCubic(t: number): number {
    return t < 0.5 ? 4 * t * t * t : 1 - Math.pow(-2 * t + 2, 3) / 2;
  }

  private resize(container: HTMLElement): void {
    const width = container.clientWidth;
    const height = container.clientHeight;
    if (!width || !height) return;
    this.camera.aspect = width / height;
    this.camera.updateProjectionMatrix();
    this.renderer.setSize(width, height);
  }
}
