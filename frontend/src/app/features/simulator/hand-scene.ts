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

import { computed, signal } from '@angular/core';
import * as THREE from 'three';
import { OrbitControls } from 'three/examples/jsm/controls/OrbitControls.js';
import { RoomEnvironment } from 'three/examples/jsm/environments/RoomEnvironment.js';
import { GLTFLoader } from 'three/examples/jsm/loaders/GLTFLoader.js';
import { RGBELoader } from 'three/examples/jsm/loaders/RGBELoader.js';

import { HandSpec, Handedness, JointAngle, JointSpec } from '@core/models/hand.model';
import { HandRig, Side, buildHandRig, captureRestPose } from './hand-rig';

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

/** Named camera positions offered by the viewport controls. */
export type CameraView = 'default' | 'palm' | 'back' | 'side' | 'top';

/**
 * Why the viewport might be empty.
 *
 * A blank 3D panel is the least debuggable failure in the whole application:
 * it looks identical whether WebGL is unavailable, the canvas has zero size,
 * the hardware specification never arrived, or the context was lost. Reporting
 * the reason turns "the hand is not showing" into something actionable.
 */
export interface SceneDiagnostics {
  webglAvailable: boolean;
  contextLost: boolean;
  canvasWidth: number;
  canvasHeight: number;
  meshCount: number;
  jointsBound: number;
  specLoaded: boolean;
  lastError: string | null;
}

/** Is WebGL usable at all in this browser? */
function probeWebGL(): { ok: boolean; detail: string | null } {
  try {
    const canvas = document.createElement('canvas');
    const context =
      canvas.getContext('webgl2') ??
      canvas.getContext('webgl') ??
      canvas.getContext('experimental-webgl');
    if (!context) {
      return {
        ok: false,
        detail:
          'This browser reports no WebGL context. Hardware acceleration may be ' +
          'disabled, or the GPU driver is blocklisted. Check chrome://gpu.',
      };
    }
    return { ok: true, detail: null };
  } catch (error) {
    return { ok: false, detail: `WebGL probe threw: ${(error as Error).message}` };
  }
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
  /** Which preset the camera was last sent to; cleared when the user orbits. */
  readonly activeView = signal<CameraView | null>('default');

  /** Populated whenever the scene state changes, so the panel can explain itself. */
  readonly diagnostics = signal<SceneDiagnostics>({
    webglAvailable: true,
    contextLost: false,
    canvasWidth: 0,
    canvasHeight: 0,
    meshCount: 0,
    jointsBound: 0,
    specLoaded: false,
    lastError: null,
  });

  /** True when there is something on screen to look at. */
  readonly ready = computed(() => {
    const d = this.diagnostics();
    return d.webglAvailable && !d.contextLost && d.meshCount > 0 &&
           d.canvasWidth > 0 && d.canvasHeight > 0;
  });

  // ── Lifecycle ─────────────────────────────────────────────────────────────

  init(container: HTMLElement, spec: HandSpec | null, handedness: Handedness = 'right'): void {
    this.handedness = handedness;

    const webgl = probeWebGL();
    if (!webgl.ok) {
      this.diagnostics.update((d) => ({
        ...d, webglAvailable: false, lastError: webgl.detail,
      }));
      return;
    }

    // The panel can be laid out at zero height on the first frame; falling back
    // to a nominal size keeps the renderer valid until the ResizeObserver fires,
    // instead of leaving a 0x0 canvas that never recovers.
    const width = container.clientWidth || 640;
    const height = container.clientHeight || 480;

    try {
    this.renderer = new THREE.WebGLRenderer({
      antialias: true,
      alpha: true,
      powerPreference: 'high-performance',
    });
    this.renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2));
    this.renderer.setSize(width, height);
    this.renderer.shadowMap.enabled = true;
    this.renderer.shadowMap.type = THREE.PCFSoftShadowMap;
    this.renderer.toneMapping = THREE.ACESFilmicToneMapping;
    this.renderer.toneMappingExposure = 1.0;
    this.renderer.outputColorSpace = THREE.SRGBColorSpace;
    container.appendChild(this.renderer.domElement);

    this.scene = new THREE.Scene();
    this.scene.background = null;

    this.camera = new THREE.PerspectiveCamera(32, width / height, 0.05, 100);
    this.camera.position.set(1.35, 0.55, 2.15);

    this.setupControls(container);
    this.setupEnvironment();
    this.setupLights();
    this.setupGround();

    this.buildRig();

    if (spec) this.applySpec(spec);

    this.resizeObserver = new ResizeObserver(() => this.resize(container));
    this.resizeObserver.observe(container);

    // A lost context is otherwise silent: the canvas simply stops updating.
    this.renderer.domElement.addEventListener('webglcontextlost', (event) => {
      event.preventDefault();
      this.diagnostics.update((d) => ({
        ...d, contextLost: true,
        lastError: 'The WebGL context was lost. This usually means the GPU ' +
                   'driver reset or the tab was starved of memory.',
      }));
    });
    this.renderer.domElement.addEventListener('webglcontextrestored', () => {
      this.diagnostics.update((d) => ({ ...d, contextLost: false, lastError: null }));
    });

    this.refreshDiagnostics();

    this.clock.start();
    this.loop();
    } catch (error) {
      this.diagnostics.update((d) => ({
        ...d,
        lastError: `Scene initialisation failed: ${(error as Error).message}`,
      }));
      return;
    }

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
    // The shared skin is deliberately NOT released here. Routing away from the
    // laboratory destroys this component and routing back creates another, and
    // tearing down the cache on every visit would pay the one-second texture
    // generation each time. It is a handful of megabytes for the session.
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

    // A manual orbit means the view is no longer a named preset, and an
    // in-flight tween should yield to the user rather than fight them.
    this.controls.addEventListener('start', () => {
      this.cameraTween = null;
      this.controls.enableDamping = true;
      this.activeView.set(null);
    });

    this.controls.update();
  }

  /** Where the camera returns to, and the view each preset frames. */
  private static readonly VIEWS: Record<CameraView, { position: [number, number, number]; target: [number, number, number] }> = {
    default: { position: [1.35, 0.55, 2.15], target: [0, 0.12, 0] },
    palm:    { position: [0.0, 0.15, 2.35], target: [0, 0.10, 0] },
    back:    { position: [0.0, 0.20, -2.35], target: [0, 0.10, 0] },
    side:    { position: [2.30, 0.30, 0.10], target: [0, 0.10, 0] },
    top:     { position: [0.05, 2.30, 0.55], target: [0, 0.05, 0] },
  };

  private cameraTween: {
    from: THREE.Vector3; to: THREE.Vector3;
    fromTarget: THREE.Vector3; toTarget: THREE.Vector3;
    start: number; duration: number;
  } | null = null;

  /**
   * Move the camera to a named view.
   *
   * Animated rather than snapped: an instant jump loses the viewer's sense of
   * which way the hand is facing, and re-orienting after every reset is exactly
   * the friction the button is meant to remove. Damping is suspended during the
   * tween so OrbitControls does not fight the interpolation.
   */
  moveCameraTo(view: CameraView = 'default', durationMs = 650): void {
    const preset = HandScene.VIEWS[view] ?? HandScene.VIEWS.default;

    this.cameraTween = {
      from: this.camera.position.clone(),
      to: new THREE.Vector3(...preset.position),
      fromTarget: this.controls.target.clone(),
      toTarget: new THREE.Vector3(...preset.target),
      start: performance.now(),
      duration: Math.max(1, durationMs),
    };
    this.controls.enableDamping = false;
    this.activeView.set(view);
  }

  resetCamera(): void {
    this.moveCameraTo('default');
  }

  private stepCamera(): void {
    if (!this.cameraTween) return;

    const tween = this.cameraTween;
    const raw = Math.min(1, (performance.now() - tween.start) / tween.duration);
    const t = this.easeInOutCubic(raw);

    this.camera.position.lerpVectors(tween.from, tween.to, t);
    this.controls.target.lerpVectors(tween.fromTarget, tween.toTarget, t);

    if (raw >= 1) {
      this.cameraTween = null;
      this.controls.enableDamping = true;
    }
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

    // Ambient floor bounce. Without it the palm side falls into near-black
    // against the light background, which reads as a missing surface.
    this.scene.add(new THREE.HemisphereLight(0xffffff, 0xc8d6e2, 0.75));
    this.scene.add(new THREE.AmbientLight(0xffffff, 0.25));
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
    this.refreshDiagnostics();
  }

  /** Recount what is actually in the scene, for the panel's diagnostics. */
  private refreshDiagnostics(): void {
    let meshes = 0;
    this.rig?.root.traverse((object) => {
      if ((object as THREE.Mesh).isMesh && object.visible) meshes++;
    });

    this.diagnostics.update((d) => ({
      ...d,
      canvasWidth: this.renderer?.domElement.width ?? 0,
      canvasHeight: this.renderer?.domElement.height ?? 0,
      meshCount: meshes,
      jointsBound: this.tracks.size,
      specLoaded: this.jointSpecs.size > 0,
    }));
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
    this.refreshDiagnostics();
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
    this.stepCamera();
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
    this.refreshDiagnostics();
  }
}
