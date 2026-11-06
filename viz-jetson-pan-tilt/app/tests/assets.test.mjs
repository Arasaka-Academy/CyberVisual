import test from 'node:test';
import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';
import { GLTFLoader } from 'three/examples/jsm/loaders/GLTFLoader.js';
import { Vector3 } from 'three';
import { transformPoint } from '../src/kinematics.mjs';

const bytes = await readFile(new URL('../public/assets/gimbal.glb', import.meta.url));
const { scene } = await new GLTFLoader().parseAsync(bytes.buffer.slice(bytes.byteOffset, bytes.byteOffset + bytes.byteLength), '');
const world = name => scene.getObjectByName(name).getWorldPosition(new Vector3()).toArray();
const close = (a, b) => a.forEach((v, i) => assert.ok(Math.abs(v - b[i]) < .000001, `${a} != ${b}`));

test('exported GLB turns the camera with pan while the base and yaw stator remain fixed', () => {
  scene.getObjectByName('PanPivot').rotation.y = 0;
  scene.getObjectByName('TiltPivot').rotation.x = 0;
  scene.updateMatrixWorld(true);
  const base = world('base'), stator = world('yaw-motor-stack');
  scene.getObjectByName('PanPivot').rotation.y = Math.PI / 2;
  scene.updateMatrixWorld(true);
  close(world('anchor_camera_optical'), [.0278, .126, 0]);
  close(world('base'), base);
  close(world('yaw-motor-stack'), stator);
});

test('the exported camera connector follows both real pivots, matching cable kinematics', () => {
  scene.getObjectByName('PanPivot').rotation.y = 45 * Math.PI / 180;
  scene.getObjectByName('TiltPivot').rotation.x = -30 * Math.PI / 180;
  scene.updateMatrixWorld(true);
  close(world('anchor_camera_csi'), transformPoint([0, .1085, -.024], 45, 30, 'tilt'));
  close(world('anchor_tilt_uart'), transformPoint([.096, .147, 0], 45, 30, 'pan'));
});

test('all original CAD triangle counts survive asset export', async () => {
  const source = JSON.parse(await readFile(new URL('../../../models/imx477-hq/figure/scene.json', import.meta.url), 'utf8'));
  for (const part of source.parts) {
    const mesh = scene.getObjectByName(part.name);
    assert.ok(mesh?.isMesh, part.name);
    const triangles = (mesh.geometry.index?.count ?? mesh.geometry.attributes.position.count) / 3;
    assert.equal(triangles, part.faces.length, part.name);
    assert.equal(mesh.material.side, 0, `${part.name} is single sided`);
  }
});
