import test from 'node:test';
import assert from 'node:assert/strict';
import { createState, reduce, advance, validateBuild, requiredConnections, signalProgress } from '../src/simulation.mjs';
import { transformPoint, opticalPose } from '../src/kinematics.mjs';

const near = (actual, want) => actual.forEach((v, i) => assert.ok(Math.abs(v - want[i]) < 1e-8, `${actual} != ${want}`));
const action = (state, type, data = {}) => reduce(state, { type, ...data });
const built = () => {
  let s = createState('sandbox');
  for (const part of ['nano', 'yaw', 'upper', 'tilt', 'camera', 'power']) s = action(s, 'PLACE', { part });
  for (const [from, to] of requiredConnections) s = action(s, 'CONNECT', { from, to });
  return s;
};

test('pan carries the upper camera around the vertical axis', () => {
  near(transformPoint([0, .126, .04], 90, 0, 'tilt'), [.04, .126, 0]);
});

test('positive tilt raises the lens around the actual 126 mm axis', () => {
  near(transformPoint([0, .126, .04], 0, 30, 'tilt'), [0, .146, .03464101615137755]);
  near(transformPoint([.07, .126, 0], 0, 30, 'pan'), [.07, .126, 0]);
});

test('tilt then pan compose in the same order as the nested rig', () => {
  near(transformPoint([0, .126, .04], 90, 30, 'tilt'), [.03464101615137755, .146, 0]);
  near(opticalPose(90, 30).direction, [.8660254037844386, .5, 0]);
});

test('slider input stays within demonstration travel and rejects non-finite input', () => {
  let s = createState('pan');
  s = action(s, 'ANGLE', { axis: 'pan', value: 999 });
  assert.equal(s.pan, 90);
  s = action(s, 'ANGLE', { axis: 'pan', value: NaN });
  assert.equal(s.pan, 90);
  s = action(createState('tilt'), 'ANGLE', { axis: 'tilt', value: -100 });
  assert.equal(s.tilt, -35);
});

test('UART motion starts after delivery and completes at the requested pose', () => {
  let s = action(createState('uart'), 'SEND');
  assert.equal(s.phase, 'sending');
  s = advance(s, .2);
  assert.equal(s.pan, 0);
  s = advance(s, 3.8);
  assert.equal(s.phase, 'complete');
  assert.equal(s.pan, 30);
  assert.equal(s.tilt, 15);
});

test('signal packets reach their destination when delivery completes', () => {
  const command = action(createState('uart'), 'SEND');
  assert.equal(signalProgress(advance(command, .4), 'uart'), .5);
  const received = advance(command, .8);
  assert.equal(received.phase, 'moving');
  assert.equal(signalProgress(received, 'uart'), 1);
  const capture = action(createState('capture'), 'CAPTURE');
  assert.equal(signalProgress(advance(capture, .2), 'csi'), 0);
  near([signalProgress(advance(capture, .925), 'csi')], [.5]);
  assert.equal(signalProgress(advance(capture, 1.5), 'csi'), 1);
});

test('switching lessons cancels an in-flight command and resets the new lesson', () => {
  let s = advance(action(createState('uart'), 'SEND'), 1.5);
  assert.ok(s.pan > 0);
  s = action(s, 'LESSON', { lesson: 'tilt' });
  assert.equal(s.pan, 0);
  assert.equal(s.tilt, 0);
  assert.equal(s.phase, 'idle');
  assert.equal(advance(s, 10).pan, 0);
});

test('capture stores the exposure pose rather than a later moving pose', () => {
  let s = { ...createState('capture'), pan: 25, tilt: -10 };
  s = advance(action(s, 'CAPTURE'), 2);
  assert.equal(s.frame.pan, 25);
  assert.equal(s.frame.tilt, -10);
  assert.equal(s.phase, 'complete');
  assert.equal(s.frame.id, 1);
});

test('missing supply blocks running even if motion and data are connected', () => {
  let s = built();
  s = { ...s, sandbox: { ...s.sandbox, placed: s.sandbox.placed.filter(p => p !== 'power') } };
  const result = validateBuild(s.sandbox);
  assert.equal(result.ok, false);
  assert.ok(result.errors.some(e => e.includes('电源')));
  s = action(s, 'RUN');
  assert.equal(s.sandbox.running, false);
});

test('connecting UART to CSI gives a visible mismatch and blocks running', () => {
  let s = built();
  s = action(s, 'CONNECT', { from: 'nano.uart-pan', to: 'camera.csi' });
  assert.equal(validateBuild(s.sandbox).ok, false);
  assert.ok(s.sandbox.errors.some(e => e.includes('不匹配')));
  assert.equal(action(s, 'RUN').sandbox.running, false);
});

test('clicking the receiving port first preserves the actual signal direction', () => {
  let s = action(createState('sandbox'), 'CONNECT', { from: 'tilt.uart', to: 'nano.uart-tilt' });
  s = action(s, 'CONNECT', { from: 'nano.csi', to: 'camera.csi' });
  assert.deepEqual(s.sandbox.connections, [
    { from: 'nano.uart-tilt', to: 'tilt.uart' },
    { from: 'camera.csi', to: 'nano.csi' },
  ]);
});

test('a correct build runs and Stop freezes pose and frame state', () => {
  let s = action(built(), 'RUN');
  assert.equal(s.sandbox.running, true);
  s = advance(s, 1.2);
  assert.ok(Math.abs(s.pan) > 1);
  s = action(s, 'STOP');
  const pose = [s.pan, s.tilt, s.elapsed];
  const after = advance(s, 10);
  assert.deepEqual([after.pan, after.tilt, after.elapsed], pose);
  assert.equal(after.sandbox.running, false);
});

test('removing a required cable while running stops motion immediately', () => {
  let s = advance(action(built(), 'RUN'), .8);
  s = action(s, 'CONNECT', { from: 'nano.uart-pan', to: 'yaw.uart' });
  assert.equal(s.sandbox.running, false);
  assert.equal(validateBuild(s.sandbox).ok, false);
  assert.equal(advance(s, 3).pan, s.pan);
});

test('a duplicate or unknown part cannot create additional placed hardware', () => {
  let s = createState('sandbox');
  s = action(s, 'PLACE', { part: 'nano' });
  s = action(s, 'PLACE', { part: 'nano' });
  s = action(s, 'PLACE', { part: 'unknown' });
  assert.deepEqual(s.sandbox.placed, ['nano']);
});

test('reduced motion still completes UART teaching and capture', () => {
  let s = { ...createState('uart'), reducedMotion: true };
  s = action(s, 'SEND');
  assert.equal(s.pan, 30);
  assert.equal(s.tilt, 15);
  assert.equal(s.phase, 'complete');
  s = action({ ...createState('capture'), reducedMotion: true }, 'CAPTURE');
  assert.equal(s.phase, 'complete');
  assert.equal(s.frame.id, 1);
});
