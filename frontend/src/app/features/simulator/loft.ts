/**
 * Lofted surface builder.
 *
 * Capsules and boxes read as robotic. Real anatomy is a stack of cross-sections
 * whose width, depth and centre all vary along the limb, so every part of the
 * hand here is built by sweeping a superelliptical profile through a list of
 * rings and skinning between them.
 */

import * as THREE from 'three';

export interface Ring {
  /** Position along the sweep axis (+Y). */
  y: number;
  /** Half-width across the hand (X). */
  rx: number;
  /** Half-depth palm-to-back (Z). */
  rz: number;
  /** Lateral offset of this cross-section's centre. */
  cx?: number;
  /** Dorsal/palmar offset of this cross-section's centre. */
  cz?: number;
  /**
   * Superellipse exponent. 2 is a true ellipse; higher values square off the
   * silhouette, which is what gives the palm its flat front and back while the
   * fingers stay round.
   */
  squareness?: number;
  /**
   * Palmar flattening, 0..1. Fingers and palm are flat on the gripping side and
   * convex on the back; without this every segment looks like a sausage.
   */
  flatten?: number;
}

function superellipse(theta: number, rx: number, rz: number, n: number): [number, number] {
  const cos = Math.cos(theta);
  const sin = Math.sin(theta);
  const exponent = 2 / n;
  const x = Math.sign(cos) * Math.abs(cos) ** exponent * rx;
  const z = Math.sign(sin) * Math.abs(sin) ** exponent * rz;
  return [x, z];
}

/**
 * Skin a sequence of rings into a closed solid.
 *
 * Rings must be ordered along +Y. The result is centred on the sweep axis so a
 * joint pivot can be placed at the origin.
 */
export function loft(rings: Ring[], radialSegments = 24): THREE.BufferGeometry {
  const positions: number[] = [];
  const uvs: number[] = [];
  const indices: number[] = [];

  const ringCount = rings.length;

  for (let r = 0; r < ringCount; r++) {
    const ring = rings[r];
    const squareness = ring.squareness ?? 2;
    const flatten = ring.flatten ?? 0;
    const cx = ring.cx ?? 0;
    const cz = ring.cz ?? 0;

    for (let s = 0; s <= radialSegments; s++) {
      const theta = (s / radialSegments) * Math.PI * 2;
      let [x, z] = superellipse(theta, ring.rx, ring.rz, squareness);

      // Compress the palmar half (negative Z) towards the plane.
      if (z < 0) z *= 1 - flatten;

      positions.push(x + cx, ring.y, z + cz);
      uvs.push(s / radialSegments, r / (ringCount - 1));
    }
  }

  const stride = radialSegments + 1;
  for (let r = 0; r < ringCount - 1; r++) {
    for (let s = 0; s < radialSegments; s++) {
      const a = r * stride + s;
      const b = a + 1;
      const c = a + stride;
      const d = c + 1;
      indices.push(a, c, b, b, c, d);
    }
  }

  // Caps: a centre vertex fanned to the first and last ring.
  const capBottom = positions.length / 3;
  positions.push(rings[0].cx ?? 0, rings[0].y - rings[0].rz * 0.35, rings[0].cz ?? 0);
  uvs.push(0.5, 0);
  for (let s = 0; s < radialSegments; s++) {
    indices.push(capBottom, s + 1, s);
  }

  const last = ringCount - 1;
  const capTop = positions.length / 3;
  positions.push(rings[last].cx ?? 0, rings[last].y + rings[last].rz * 0.35, rings[last].cz ?? 0);
  uvs.push(0.5, 1);
  const offset = last * stride;
  for (let s = 0; s < radialSegments; s++) {
    indices.push(capTop, offset + s, offset + s + 1);
  }

  const geometry = new THREE.BufferGeometry();
  geometry.setAttribute('position', new THREE.Float32BufferAttribute(positions, 3));
  geometry.setAttribute('uv', new THREE.Float32BufferAttribute(uvs, 2));
  geometry.setIndex(indices);
  geometry.computeVertexNormals();
  return geometry;
}

/**
 * Cross-sections for one phalanx.
 *
 * The bulges at both ends are the condyles — the bone flares at each joint —
 * and the waist between them is what makes a finger look jointed rather than
 * extruded.
 */
export function phalanxRings(
  length: number,
  radiusBase: number,
  radiusTip: number,
  options: { tip?: boolean; flatten?: number } = {},
): Ring[] {
  const flatten = options.flatten ?? 0.22;
  const steps = 9;
  const rings: Ring[] = [];

  for (let i = 0; i <= steps; i++) {
    const t = i / steps;
    const base = radiusBase + (radiusTip - radiusBase) * t;

    // Condyle bulge at both ends, slight waist in the middle.
    const knuckle = 1 + 0.11 * Math.exp(-((t - 0.02) ** 2) / 0.006)
                      + 0.07 * Math.exp(-((t - 0.98) ** 2) / 0.008)
                      - 0.045 * Math.exp(-((t - 0.5) ** 2) / 0.05);

    let rx = base * knuckle;
    let rz = base * knuckle * 0.88;

    if (options.tip && t > 0.72) {
      // Round the fingertip off instead of ending on a flat cap.
      const k = (t - 0.72) / 0.28;
      const dome = Math.cos((k * Math.PI) / 2);
      rx *= 0.35 + 0.65 * dome;
      rz *= 0.35 + 0.65 * dome;
    }

    rings.push({
      y: t * length,
      rx,
      rz,
      cz: -base * 0.05,
      squareness: 2.25,
      flatten,
    });
  }

  return rings;
}
