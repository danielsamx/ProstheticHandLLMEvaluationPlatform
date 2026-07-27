/**
 * Procedural PBR skin texture set.
 *
 * Generated on a canvas at 1024x1024 rather than shipped as binaries: the
 * platform must run offline next to a local LM Studio instance, and a texture
 * download is one more thing to fail. The maps are deliberately subtle - the
 * realism here comes mostly from the IBL and the geometry.
 */

import * as THREE from 'three';

const SIZE = 1024;

function canvas(): [HTMLCanvasElement, CanvasRenderingContext2D] {
  const element = document.createElement('canvas');
  element.width = SIZE;
  element.height = SIZE;
  return [element, element.getContext('2d')!];
}

/** Cheap value noise; good enough for pore-scale detail. */
function noise2d(x: number, y: number, seed: number): number {
  const n = Math.sin(x * 12.9898 + y * 78.233 + seed * 43.7585) * 43758.5453;
  return n - Math.floor(n);
}

function smoothNoise(x: number, y: number, seed: number): number {
  const xi = Math.floor(x);
  const yi = Math.floor(y);
  const xf = x - xi;
  const yf = y - yi;
  const u = xf * xf * (3 - 2 * xf);
  const v = yf * yf * (3 - 2 * yf);
  const a = noise2d(xi, yi, seed);
  const b = noise2d(xi + 1, yi, seed);
  const c = noise2d(xi, yi + 1, seed);
  const d = noise2d(xi + 1, yi + 1, seed);
  return a * (1 - u) * (1 - v) + b * u * (1 - v) + c * (1 - u) * v + d * u * v;
}

function fbm(x: number, y: number, octaves: number, seed: number): number {
  let value = 0;
  let amplitude = 0.5;
  let frequency = 1;
  for (let i = 0; i < octaves; i++) {
    value += amplitude * smoothNoise(x * frequency, y * frequency, seed + i);
    amplitude *= 0.5;
    frequency *= 2;
  }
  return value;
}

export interface SkinTextures {
  map: THREE.Texture;
  normalMap: THREE.Texture;
  roughnessMap: THREE.Texture;
}

/**
 * Generated once per session and shared.
 *
 * Building the set means evaluating fractal noise over three 1024x1024 buffers
 * — roughly three million pixels, each costing several trigonometric calls, all
 * on the main thread. That is around a second of frozen UI. Nothing about the
 * result depends on which hand is being rendered, so regenerating it on every
 * left/right toggle was pure waste; the cache makes the switch instant.
 */
let cachedTextures: SkinTextures | null = null;
let cachedSkin: THREE.MeshPhysicalMaterial | null = null;
let cachedNail: THREE.MeshPhysicalMaterial | null = null;

export function createSkinTextures(): SkinTextures {
  if (cachedTextures) return cachedTextures;
  cachedTextures = {
    map: createAlbedo(),
    normalMap: createNormal(),
    roughnessMap: createRoughness(),
  };
  return cachedTextures;
}

/** Materials are shared too — they are immutable and hold the textures. */
export function sharedSkinMaterial(): THREE.MeshPhysicalMaterial {
  cachedSkin ??= createSkinMaterial(createSkinTextures());
  return cachedSkin;
}

export function sharedNailMaterial(): THREE.MeshPhysicalMaterial {
  cachedNail ??= createNailMaterial();
  return cachedNail;
}

/** Release the shared set. Only the component teardown should call this. */
export function disposeSharedSkin(): void {
  cachedSkin?.dispose();
  cachedNail?.dispose();
  cachedTextures?.map.dispose();
  cachedTextures?.normalMap.dispose();
  cachedTextures?.roughnessMap.dispose();
  cachedSkin = null;
  cachedNail = null;
  cachedTextures = null;
}

function createAlbedo(): THREE.Texture {
  const [element, ctx] = canvas();
  const image = ctx.createImageData(SIZE, SIZE);
  const data = image.data;

  for (let y = 0; y < SIZE; y++) {
    for (let x = 0; x < SIZE; x++) {
      const u = x / SIZE;
      const v = y / SIZE;

      // Base tone with a slow dermal-blood gradient.
      const melanin = fbm(u * 6, v * 6, 4, 1.0);
      const blood = fbm(u * 3 + 5, v * 3 + 5, 3, 2.0);
      const pores = fbm(u * 220, v * 220, 2, 3.0);

      const r = 232 - melanin * 34 + blood * 18 - pores * 9;
      const g = 188 - melanin * 40 + blood * 6 - pores * 9;
      const b = 172 - melanin * 42 - blood * 4 - pores * 8;

      const index = (y * SIZE + x) * 4;
      data[index] = Math.max(0, Math.min(255, r));
      data[index + 1] = Math.max(0, Math.min(255, g));
      data[index + 2] = Math.max(0, Math.min(255, b));
      data[index + 3] = 255;
    }
  }

  ctx.putImageData(image, 0, 0);
  const texture = new THREE.CanvasTexture(element);
  texture.colorSpace = THREE.SRGBColorSpace;
  texture.wrapS = texture.wrapT = THREE.RepeatWrapping;
  texture.anisotropy = 8;
  return texture;
}

function createNormal(): THREE.Texture {
  const [element, ctx] = canvas();
  const image = ctx.createImageData(SIZE, SIZE);
  const data = image.data;
  const strength = 2.4;

  const height = (x: number, y: number) =>
    fbm(x / SIZE * 190, y / SIZE * 190, 3, 7.0) * 0.75 +
    fbm(x / SIZE * 26, y / SIZE * 26, 2, 11.0) * 0.25;

  for (let y = 0; y < SIZE; y++) {
    for (let x = 0; x < SIZE; x++) {
      // Central differences over the height field -> tangent-space normal.
      const dx = (height(x + 1, y) - height(x - 1, y)) * strength;
      const dy = (height(x, y + 1) - height(x, y - 1)) * strength;
      const length = Math.hypot(dx, dy, 1);

      const index = (y * SIZE + x) * 4;
      data[index] = ((-dx / length) * 0.5 + 0.5) * 255;
      data[index + 1] = ((-dy / length) * 0.5 + 0.5) * 255;
      data[index + 2] = ((1 / length) * 0.5 + 0.5) * 255;
      data[index + 3] = 255;
    }
  }

  ctx.putImageData(image, 0, 0);
  const texture = new THREE.CanvasTexture(element);
  texture.wrapS = texture.wrapT = THREE.RepeatWrapping;
  texture.anisotropy = 8;
  return texture;
}

function createRoughness(): THREE.Texture {
  const [element, ctx] = canvas();
  const image = ctx.createImageData(SIZE, SIZE);
  const data = image.data;

  for (let y = 0; y < SIZE; y++) {
    for (let x = 0; x < SIZE; x++) {
      // Skin is glossier where it is taut (knuckles, fingertips) and rougher
      // in the creases; the noise stands in for that variation.
      const value = 150 + fbm(x / SIZE * 90, y / SIZE * 90, 3, 13.0) * 90;
      const index = (y * SIZE + x) * 4;
      data[index] = data[index + 1] = data[index + 2] = Math.min(255, value);
      data[index + 3] = 255;
    }
  }

  ctx.putImageData(image, 0, 0);
  const texture = new THREE.CanvasTexture(element);
  texture.wrapS = texture.wrapT = THREE.RepeatWrapping;
  return texture;
}

/**
 * Physically-based skin.
 *
 * Three effects stacked, in order of how much they contribute:
 *  - `sheen` gives the soft velvet falloff at grazing angles that separates
 *    skin from plastic more than any texture does;
 *  - `transmission` plus a warm `attenuationColor` fakes subsurface scattering,
 *    so light bleeds red through the thin tissue at the finger edges;
 *  - `clearcoat` stands in for the oily epidermal layer.
 */
export function createSkinMaterial(textures: SkinTextures): THREE.MeshPhysicalMaterial {
  return new THREE.MeshPhysicalMaterial({
    map: textures.map,
    normalMap: textures.normalMap,
    normalScale: new THREE.Vector2(0.62, 0.62),
    roughnessMap: textures.roughnessMap,
    roughness: 0.58,
    metalness: 0.0,
    clearcoat: 0.20,
    clearcoatRoughness: 0.55,
    sheen: 0.55,
    sheenRoughness: 0.62,
    sheenColor: new THREE.Color(0xffd2be),
    transmission: 0.075,
    thickness: 0.42,
    attenuationColor: new THREE.Color(0xc4574a),
    attenuationDistance: 0.55,
    ior: 1.4,
    flatShading: false,
  });
}

/** Nail plate: glossy, slightly translucent, near-white with a pink bed. */
export function createNailMaterial(): THREE.MeshPhysicalMaterial {
  return new THREE.MeshPhysicalMaterial({
    color: 0xf6dcd4,
    roughness: 0.18,
    metalness: 0.0,
    clearcoat: 0.9,
    clearcoatRoughness: 0.08,
    transmission: 0.12,
    thickness: 0.05,
    ior: 1.5,
  });
}
