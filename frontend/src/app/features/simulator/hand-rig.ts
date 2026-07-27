/**
 * Procedural anatomical hand rig.
 *
 * The hierarchy mirrors the HANDi EPN V3 joint naming exactly (D0, D1_P, D1_D,
 * D2_P, D2_I, D2_D … D5_D), so a joint frame from the backend maps onto a pivot
 * by id with no translation table in between.
 *
 * Segment lengths follow adult anthropometric proportions (Buchholz &
 * Armstrong) normalised so the middle finger reaches roughly 1.0 world unit.
 *
 * Handedness is baked into the geometry rather than applied as a negative
 * scale: mirroring by ``scale.x = -1`` inverts every surface normal, which
 * breaks the lighting and the shadow terminator. Rebuilding with negated X is
 * cheap (the whole rig is procedural) and stays physically correct.
 */

import * as THREE from 'three';

import { Ring, loft, phalanxRings } from './loft';
import { sharedNailMaterial, sharedSkinMaterial } from './skin-textures';

export type Side = 'right' | 'left';

interface FingerLayout {
  digit: string;
  /** Metacarpophalangeal origin in palm space (right hand). */
  base: THREE.Vector3;
  /** Splay of the finger axis in the palm plane, radians. */
  spread: number;
  /** Forward tilt at the knuckle: fingers do not sit in the palm plane. */
  tilt: number;
  /** [proximal, intermediate, distal] segment lengths. */
  segments: [number, number, number];
  /** [base, middle, tip] radii. */
  radii: [number, number, number];
}

const FINGERS: FingerLayout[] = [
  {
    digit: 'D2', base: new THREE.Vector3(-0.205, 0.415, 0.010), spread: 0.085, tilt: 0.05,
    segments: [0.400, 0.240, 0.170], radii: [0.062, 0.054, 0.045],
  },
  {
    digit: 'D3', base: new THREE.Vector3(-0.052, 0.452, 0.016), spread: 0.018, tilt: 0.02,
    segments: [0.440, 0.268, 0.178], radii: [0.064, 0.056, 0.046],
  },
  {
    digit: 'D4', base: new THREE.Vector3(0.098, 0.434, 0.008), spread: -0.055, tilt: 0.03,
    segments: [0.408, 0.250, 0.170], radii: [0.060, 0.052, 0.044],
  },
  {
    digit: 'D5', base: new THREE.Vector3(0.232, 0.374, -0.014), spread: -0.150, tilt: 0.06,
    segments: [0.318, 0.190, 0.148], radii: [0.051, 0.045, 0.039],
  },
];

const THUMB = {
  base: new THREE.Vector3(-0.268, -0.020, 0.052),
  metacarpal: 0.330,
  segments: [0.255, 0.215] as [number, number],
  radii: [0.077, 0.066] as [number, number],
  /** Resting opposition: the thumb sits rotated out of the palm plane. */
  rest: new THREE.Euler(0.12, 0.0, 0.66),
};

export interface HandRig {
  root: THREE.Group;
  side: Side;
  /** Backend joint id -> the pivot that rotates for that joint. */
  pivots: Map<string, THREE.Object3D>;
  dispose(): void;
}

function mesh(geometry: THREE.BufferGeometry, material: THREE.Material): THREE.Mesh {
  const result = new THREE.Mesh(geometry, material);
  result.castShadow = true;
  result.receiveShadow = true;
  return result;
}

// ─────────────────────────────────────────────────────────────────────────────
// Palm
// ─────────────────────────────────────────────────────────────────────────────

/**
 * The palm is the part that most betrays a procedural hand.
 *
 * It is built as a loft that widens from the wrist to the knuckle line, is
 * squared off in cross-section (flat front and back, rounded edges) and is
 * thinner on the palmar side than the dorsal side. The thenar and hypothenar
 * muscle masses are added as separate lofts, because they sit proud of the
 * palm plane and cannot be expressed as a single sweep.
 */
function buildPalm(material: THREE.Material, mirror: number): THREE.Group {
  const group = new THREE.Group();

  const rings: Ring[] = [
    { y: -0.300, rx: 0.196, rz: 0.093, cz: 0.004, squareness: 2.7, flatten: 0.10 },
    { y: -0.210, rx: 0.214, rz: 0.097, cz: 0.002, squareness: 2.9, flatten: 0.12 },
    { y: -0.110, rx: 0.244, rz: 0.100, cz: 0.000, squareness: 3.1, flatten: 0.15 },
    { y: -0.010, rx: 0.272, rz: 0.098, cz: -0.004, squareness: 3.2, flatten: 0.18 },
    { y: 0.090, rx: 0.290, rz: 0.093, cz: -0.008, squareness: 3.3, flatten: 0.20 },
    { y: 0.190, rx: 0.296, rz: 0.086, cz: -0.012, squareness: 3.3, flatten: 0.22 },
    { y: 0.280, rx: 0.292, rz: 0.078, cz: -0.014, squareness: 3.2, flatten: 0.22 },
    { y: 0.350, rx: 0.283, rz: 0.072, cz: -0.014, squareness: 3.0, flatten: 0.20 },
    { y: 0.402, rx: 0.268, rz: 0.067, cz: -0.012, squareness: 2.8, flatten: 0.16 },
    { y: 0.438, rx: 0.243, rz: 0.062, cz: -0.008, squareness: 2.5, flatten: 0.10 },
  ];
  group.add(mesh(loft(rings, 40), material));

  // Thenar eminence: the thumb muscle pad, the single most recognisable
  // landmark on a human palm.
  const thenar = mesh(
    loft([
      { y: -0.150, rx: 0.052, rz: 0.030, squareness: 2.2, flatten: 0.05 },
      { y: -0.060, rx: 0.085, rz: 0.050, squareness: 2.2, flatten: 0.05 },
      { y: 0.040, rx: 0.096, rz: 0.056, squareness: 2.2, flatten: 0.05 },
      { y: 0.140, rx: 0.080, rz: 0.046, squareness: 2.2, flatten: 0.05 },
      { y: 0.215, rx: 0.046, rz: 0.026, squareness: 2.2, flatten: 0.05 },
    ], 24),
    material,
  );
  thenar.position.set(-0.150 * mirror, 0.010, -0.072);
  thenar.rotation.z = 0.22 * mirror;
  group.add(thenar);

  // Hypothenar eminence: the pad along the little-finger edge.
  const hypothenar = mesh(
    loft([
      { y: -0.170, rx: 0.038, rz: 0.024, squareness: 2.2, flatten: 0.05 },
      { y: -0.070, rx: 0.062, rz: 0.038, squareness: 2.2, flatten: 0.05 },
      { y: 0.050, rx: 0.068, rz: 0.041, squareness: 2.2, flatten: 0.05 },
      { y: 0.170, rx: 0.055, rz: 0.033, squareness: 2.2, flatten: 0.05 },
      { y: 0.265, rx: 0.030, rz: 0.018, squareness: 2.2, flatten: 0.05 },
    ], 24),
    material,
  );
  hypothenar.position.set(0.212 * mirror, 0.030, -0.064);
  hypothenar.rotation.z = -0.10 * mirror;
  group.add(hypothenar);

  // Metacarpal ridges on the back of the hand: four shallow tendon lines that
  // catch the key light and stop the dorsum reading as a flat slab.
  for (const finger of FINGERS) {
    const ridge = mesh(
      loft([
        { y: 0.00, rx: 0.028, rz: 0.012, squareness: 2, flatten: 0 },
        { y: 0.12, rx: 0.031, rz: 0.014, squareness: 2, flatten: 0 },
        { y: 0.26, rx: 0.027, rz: 0.012, squareness: 2, flatten: 0 },
        { y: 0.34, rx: 0.017, rz: 0.007, squareness: 2, flatten: 0 },
      ], 16),
      material,
    );
    ridge.position.set(finger.base.x * mirror * 0.92, 0.055, 0.055);
    group.add(ridge);
  }

  return group;
}

function buildWrist(material: THREE.Material): THREE.Mesh {
  return mesh(
    loft([
      { y: -0.720, rx: 0.196, rz: 0.140, squareness: 2.4, flatten: 0.06 },
      { y: -0.600, rx: 0.188, rz: 0.130, squareness: 2.5, flatten: 0.07 },
      { y: -0.480, rx: 0.178, rz: 0.117, squareness: 2.6, flatten: 0.08 },
      { y: -0.380, rx: 0.180, rz: 0.106, squareness: 2.7, flatten: 0.09 },
      { y: -0.300, rx: 0.190, rz: 0.096, squareness: 2.7, flatten: 0.10 },
    ], 32),
    material,
  );
}

// ─────────────────────────────────────────────────────────────────────────────
// Nails
// ─────────────────────────────────────────────────────────────────────────────

/**
 * A nail plate, curved across its width and set into the fingertip.
 *
 * Small, but its specular highlight is a strong realism cue: under image-based
 * lighting the eye reads a glossy nail against matte skin immediately.
 */
function buildNail(width: number, length: number, material: THREE.Material): THREE.Mesh {
  const geometry = new THREE.SphereGeometry(1, 20, 14, 0, Math.PI * 2, 0, Math.PI / 2.2);
  const position = geometry.attributes['position'] as THREE.BufferAttribute;
  for (let i = 0; i < position.count; i++) {
    position.setXYZ(
      i,
      position.getX(i) * width,
      position.getY(i) * width * 0.42,
      position.getZ(i) * length,
    );
  }
  position.needsUpdate = true;
  geometry.computeVertexNormals();

  const result = new THREE.Mesh(geometry, material);
  result.castShadow = false;
  result.receiveShadow = true;
  return result;
}

// ─────────────────────────────────────────────────────────────────────────────
// Rig
// ─────────────────────────────────────────────────────────────────────────────

export function buildHandRig(side: Side = 'right'): HandRig {
  // Textures and materials are session-shared: they are identical for both
  // hands, and regenerating them dominated the cost of a left/right switch.
  const skin = sharedSkinMaterial();
  const nailMaterial = sharedNailMaterial();
  const pivots = new Map<string, THREE.Object3D>();
  const mirror = side === 'left' ? -1 : 1;

  const root = new THREE.Group();
  root.name = `hand-root-${side}`;
  root.add(buildPalm(skin, mirror), buildWrist(skin));

  // ── Fingers D2..D5 ────────────────────────────────────────────────────────
  for (const finger of FINGERS) {
    const mcp = new THREE.Group();
    mcp.name = `${finger.digit}_P`;
    mcp.position.set(finger.base.x * mirror, finger.base.y, finger.base.z);
    mcp.rotation.set(finger.tilt, 0, finger.spread * mirror);
    root.add(mcp);
    pivots.set(`${finger.digit}_P`, mcp);

    mcp.add(mesh(
      loft(phalanxRings(finger.segments[0], finger.radii[0], finger.radii[1]), 22),
      skin,
    ));

    const pip = new THREE.Group();
    pip.name = `${finger.digit}_I`;
    pip.position.y = finger.segments[0];
    mcp.add(pip);
    pivots.set(`${finger.digit}_I`, pip);

    pip.add(mesh(
      loft(phalanxRings(finger.segments[1], finger.radii[1], finger.radii[2]), 22),
      skin,
    ));

    const dip = new THREE.Group();
    dip.name = `${finger.digit}_D`;
    dip.position.y = finger.segments[1];
    pip.add(dip);
    pivots.set(`${finger.digit}_D`, dip);

    dip.add(mesh(
      loft(
        phalanxRings(finger.segments[2], finger.radii[2], finger.radii[2] * 0.80, { tip: true }),
        22,
      ),
      skin,
    ));

    const nail = buildNail(finger.radii[2] * 0.80, finger.radii[2] * 1.25, nailMaterial);
    nail.position.set(0, finger.segments[2] * 0.52, finger.radii[2] * 0.62);
    nail.rotation.x = Math.PI / 2 - 0.30;
    dip.add(nail);
  }

  // ── Thumb: D0 rotation, then D1_P and D1_D ────────────────────────────────
  const cmc = new THREE.Group();
  cmc.name = 'D0';
  cmc.position.set(THUMB.base.x * mirror, THUMB.base.y, THUMB.base.z);
  cmc.rotation.set(THUMB.rest.x, THUMB.rest.y, THUMB.rest.z * mirror);
  root.add(cmc);
  pivots.set('D0', cmc);

  cmc.add(mesh(
    loft(phalanxRings(THUMB.metacarpal, THUMB.radii[0] * 1.10, THUMB.radii[0], { flatten: 0.16 }), 24),
    skin,
  ));

  const thumbProximal = new THREE.Group();
  thumbProximal.name = 'D1_P';
  thumbProximal.position.y = THUMB.metacarpal;
  cmc.add(thumbProximal);
  pivots.set('D1_P', thumbProximal);

  thumbProximal.add(mesh(
    loft(phalanxRings(THUMB.segments[0], THUMB.radii[0], THUMB.radii[1], { flatten: 0.20 }), 24),
    skin,
  ));

  const thumbDistal = new THREE.Group();
  thumbDistal.name = 'D1_D';
  thumbDistal.position.y = THUMB.segments[0];
  thumbProximal.add(thumbDistal);
  pivots.set('D1_D', thumbDistal);

  thumbDistal.add(mesh(
    loft(
      phalanxRings(THUMB.segments[1], THUMB.radii[1], THUMB.radii[1] * 0.82, { tip: true, flatten: 0.20 }),
      24,
    ),
    skin,
  ));

  const thumbNail = buildNail(THUMB.radii[1] * 0.86, THUMB.radii[1] * 1.20, nailMaterial);
  thumbNail.position.set(0, THUMB.segments[1] * 0.50, THUMB.radii[1] * 0.62);
  thumbNail.rotation.x = Math.PI / 2 - 0.30;
  thumbDistal.add(thumbNail);

  return {
    root,
    side,
    pivots,
    dispose(): void {
      // Geometry is per-rig and owned here; materials and textures are shared
      // across rigs, so disposing them would blank the other hand.
      root.traverse((object) => {
        const item = object as THREE.Mesh;
        item.geometry?.dispose();
      });
    },
  };
}

/** Rest orientation of each pivot, captured so flexion is applied as a delta. */
export function captureRestPose(rig: HandRig): Map<string, THREE.Euler> {
  const rest = new Map<string, THREE.Euler>();
  rig.pivots.forEach((pivot, id) => rest.set(id, pivot.rotation.clone()));
  return rest;
}
