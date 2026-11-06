/** Browser coordinates are metres, Y up. CAD's -Y optical axis becomes +Z. */
export const TILT_HEIGHT = .126;
export const GIMBAL_POSITION = [.055, 0, 0];
export const NANO_POSITION = [-.130, 0, -.015];
export const SUPPLY_POSITION = [-.145, 0, -.105];
export const radians = degrees => degrees * Math.PI / 180;

export function transformPoint(point, pan = 0, tilt = 0, group = 'fixed') {
  let [x, y, z] = point;
  if (group === 'tilt') {
    const t = radians(tilt), dy = y - TILT_HEIGHT;
    [y, z] = [dy * Math.cos(t) + z * Math.sin(t) + TILT_HEIGHT, -dy * Math.sin(t) + z * Math.cos(t)];
  }
  if (group === 'pan' || group === 'tilt') {
    const p = radians(pan);
    [x, z] = [x * Math.cos(p) + z * Math.sin(p), -x * Math.sin(p) + z * Math.cos(p)];
  }
  return [x, y, z];
}

export function opticalPose(pan = 0, tilt = 0) {
  const p = radians(pan), t = radians(tilt);
  return {
    position: transformPoint([0, TILT_HEIGHT, .0278], pan, tilt, 'tilt'),
    direction: [Math.sin(p) * Math.cos(t), Math.sin(t), Math.cos(p) * Math.cos(t)],
    up: [-Math.sin(p) * Math.sin(t), Math.cos(t), -Math.cos(p) * Math.sin(t)],
  };
}

const add = (a, b) => a.map((v, i) => v + b[i]);
export function connectionAnchors(pan, tilt) {
  const world = (point, group) => add(transformPoint(point, pan, tilt, group), GIMBAL_POSITION);
  return {
    'nano.uart-pan': add(NANO_POSITION, [-.014, .010, -.035]),
    'nano.uart-tilt': add(NANO_POSITION, [-.006, .010, -.035]),
    'nano.csi': add(NANO_POSITION, [-.022, .006, .036]),
    'yaw.uart': world([0, .012, .025], 'fixed'),
    'yaw.power': world([.008, .012, .025], 'fixed'),
    'tilt.uart': world([.096, .147, 0], 'pan'),
    'tilt.power': world([.096, .140, .006], 'pan'),
    'camera.csi': world([0, .1085, -.024], 'tilt'),
    'power.pan': add(SUPPLY_POSITION, [.025, .008, 0]),
    'power.tilt': add(SUPPLY_POSITION, [.025, .008, -.006]),
  };
}
