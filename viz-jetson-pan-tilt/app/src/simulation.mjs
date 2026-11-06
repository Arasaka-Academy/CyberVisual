export const lessonIds = ['assembly', 'pan', 'tilt', 'uart', 'capture', 'sandbox'];
export const partIds = ['nano', 'yaw', 'upper', 'tilt', 'camera', 'power'];
export const partNames = { nano: 'Jetson Nano', yaw: '水平电机', upper: '上座支架', tilt: '俯仰电机', camera: 'IMX477 相机', power: '电机电源' };
export const requiredConnections = [
  ['nano.uart-pan', 'yaw.uart'], ['nano.uart-tilt', 'tilt.uart'],
  ['camera.csi', 'nano.csi'], ['power.pan', 'yaw.power'], ['power.tilt', 'tilt.power'],
];
export const ports = [
  { id: 'nano.uart-pan', label: 'Nano · 水平 UART', owner: 'nano', kind: 'uart', side: 'source' },
  { id: 'nano.uart-tilt', label: 'Nano · 俯仰 UART', owner: 'nano', kind: 'uart', side: 'source' },
  { id: 'camera.csi', label: '相机 · CSI 输出', owner: 'camera', kind: 'csi', side: 'source' },
  { id: 'power.pan', label: '电源 · 水平支路', owner: 'power', kind: 'power', side: 'source' },
  { id: 'power.tilt', label: '电源 · 俯仰支路', owner: 'power', kind: 'power', side: 'source' },
  { id: 'yaw.uart', label: '水平电机 · UART', owner: 'yaw', kind: 'uart', side: 'target' },
  { id: 'tilt.uart', label: '俯仰电机 · UART', owner: 'tilt', kind: 'uart', side: 'target' },
  { id: 'nano.csi', label: 'Nano · CSI 输入', owner: 'nano', kind: 'csi', side: 'target' },
  { id: 'yaw.power', label: '水平电机 · 供电', owner: 'yaw', kind: 'power', side: 'target' },
  { id: 'tilt.power', label: '俯仰电机 · 供电', owner: 'tilt', kind: 'power', side: 'target' },
];
export const portById = Object.fromEntries(ports.map(p => [p.id, p]));
const clamp = (n, min, max) => Math.max(min, Math.min(max, n));
const timing = { uartDelivery: .8, uartMotion: 2, exposure: .35, csiTransfer: 1.15 };
const pairKey = (a, b) => [a, b].sort().join('|');
const validPairs = new Set(requiredConnections.map(([a, b]) => pairKey(a, b)));
export const isValidConnection = edge => validPairs.has(pairKey(edge.from, edge.to));

export function signalProgress(state, kind) {
  if (state.lesson === 'sandbox') return (state.elapsed * .62) % 1;
  if (kind === 'uart') return clamp(state.elapsed / timing.uartDelivery, 0, 1);
  if (kind === 'csi') return clamp((state.elapsed - timing.exposure) / timing.csiTransfer, 0, 1);
  return 0;
}

export function createState(lesson = 'assembly') {
  return {
    lesson: lessonIds.includes(lesson) ? lesson : 'assembly', assembly: 1,
    pan: 0, tilt: 0, elapsed: 0, phase: 'idle', signals: false,
    selected: null, reducedMotion: false, frame: null, pendingFrame: null, frameCount: 0,
    sandbox: { placed: [], connections: [], errors: [], running: false, checked: false, pendingPort: null },
  };
}

export function validateBuild(build) {
  const errors = [];
  for (const id of partIds) if (!build.placed.includes(id)) errors.push(`请放入${partNames[id]}。`);
  const wrong = build.connections.filter(edge => !isValidConnection(edge));
  for (const edge of wrong) errors.push(`接口不匹配：${portById[edge.from]?.label ?? edge.from} → ${portById[edge.to]?.label ?? edge.to}。`);
  for (const [from, to] of requiredConnections) {
    if (!build.connections.some(edge => pairKey(edge.from, edge.to) === pairKey(from, to))) {
      errors.push(`缺少连接：${portById[from].label} → ${portById[to].label}。`);
    }
  }
  return { ok: errors.length === 0, errors };
}

function editBuild(state, patch) {
  const sandbox = { ...state.sandbox, ...patch, running: false };
  sandbox.errors = sandbox.checked || sandbox.connections.length ? validateBuild(sandbox).errors : [];
  return { ...state, sandbox, phase: 'idle' };
}

export function reduce(state, action) {
  switch (action.type) {
    case 'LESSON':
      if (!lessonIds.includes(action.lesson)) return state;
      return { ...createState(action.lesson), reducedMotion: state.reducedMotion };
    case 'RESET': return { ...createState(state.lesson), reducedMotion: state.reducedMotion };
    case 'SELECT': return { ...state, selected: action.part };
    case 'ASSEMBLY':
      return Number.isFinite(action.value) ? { ...state, assembly: clamp(action.value, 0, 1) } : state;
    case 'ANGLE':
      if (!Number.isFinite(action.value) || !['pan', 'tilt'].includes(action.axis)) return state;
      return { ...state, [action.axis]: clamp(action.value, action.axis === 'pan' ? -90 : -35, action.axis === 'pan' ? 90 : 35) };
    case 'SEND':
      if (state.lesson !== 'uart' || ['sending', 'moving'].includes(state.phase)) return state;
      return { ...state, signals: true, elapsed: 0, pan: state.reducedMotion ? 30 : 0,
        tilt: state.reducedMotion ? 15 : 0, phase: state.reducedMotion ? 'complete' : 'sending' };
    case 'CAPTURE': {
      if (state.lesson !== 'capture' || ['exposing', 'transferring'].includes(state.phase)) return state;
      const pendingFrame = { id: state.frameCount + 1, pan: state.pan, tilt: state.tilt };
      return { ...state, elapsed: 0, signals: true, pendingFrame,
        frame: state.reducedMotion ? pendingFrame : state.frame,
        frameCount: pendingFrame.id, phase: state.reducedMotion ? 'complete' : 'exposing' };
    }
    case 'MOTION_PREFERENCE': {
      const next = { ...state, reducedMotion: action.value };
      if (!action.value) return next;
      if (['sending', 'moving'].includes(state.phase)) return { ...next, pan: 30, tilt: 15, phase: 'complete' };
      if (['exposing', 'transferring'].includes(state.phase)) return { ...next, frame: state.pendingFrame, phase: 'complete' };
      return next;
    }
    case 'PLACE':
      if (!partIds.includes(action.part) || state.sandbox.placed.includes(action.part)) return state;
      return editBuild(state, { placed: [...state.sandbox.placed, action.part] });
    case 'PENDING_PORT': return { ...state, sandbox: { ...state.sandbox, pendingPort: action.port } };
    case 'CONNECT': {
      if (!portById[action.from] || !portById[action.to] || action.from === action.to) return state;
      const { from, to } = portById[action.from].side === 'target' && portById[action.to].side === 'source'
        ? { from: action.to, to: action.from } : action;
      const exists = state.sandbox.connections.some(e => pairKey(e.from, e.to) === pairKey(from, to));
      const connections = state.sandbox.connections.filter(e => ![from, to].includes(e.from) && ![from, to].includes(e.to));
      if (!exists) connections.push({ from, to });
      return editBuild(state, { connections, pendingPort: null });
    }
    case 'REMOVE_CONNECTION':
      return editBuild(state, { connections: state.sandbox.connections.filter((_, i) => i !== action.index) });
    case 'RUN': {
      if (state.lesson !== 'sandbox') return state;
      const result = validateBuild(state.sandbox);
      return { ...state, phase: result.ok ? 'running' : 'idle', signals: result.ok,
        ...(result.ok && state.reducedMotion ? { pan: 30, tilt: 15, frame: { id: state.frameCount + 1, pan: 30, tilt: 15 }, frameCount: state.frameCount + 1 } : {}),
        sandbox: { ...state.sandbox, running: result.ok, checked: true, errors: result.errors } };
    }
    case 'STOP': return { ...state, phase: 'stopped', sandbox: { ...state.sandbox, running: false } };
    default: return state;
  }
}

const smooth = t => t * t * (3 - 2 * t);
export function advance(state, seconds) {
  if (!Number.isFinite(seconds) || seconds <= 0 || state.reducedMotion) return state;
  if (state.lesson === 'sandbox') {
    if (!state.sandbox.running) return state;
    const elapsed = state.elapsed + seconds;
    const pan = 32 * Math.sin(elapsed * .7), tilt = 18 * Math.sin(elapsed * .5);
    const capture = !state.frame || Math.floor(elapsed / 2) > Math.floor(state.elapsed / 2);
    return { ...state, elapsed, pan, tilt,
      ...(capture ? { frameCount: state.frameCount + 1, frame: { id: state.frameCount + 1, pan, tilt } } : {}) };
  }
  if (state.lesson === 'uart' && ['sending', 'moving'].includes(state.phase)) {
    const end = timing.uartDelivery + timing.uartMotion;
    const elapsed = Math.min(end, state.elapsed + seconds);
    const progress = smooth(clamp((elapsed - timing.uartDelivery) / timing.uartMotion, 0, 1));
    return { ...state, elapsed, pan: progress * 30, tilt: progress * 15,
      phase: elapsed < timing.uartDelivery ? 'sending' : elapsed < end ? 'moving' : 'complete' };
  }
  if (state.lesson === 'capture' && ['exposing', 'transferring'].includes(state.phase)) {
    const end = timing.exposure + timing.csiTransfer;
    const elapsed = Math.min(end, state.elapsed + seconds);
    return { ...state, elapsed, frame: elapsed >= timing.exposure ? state.pendingFrame : state.frame,
      phase: elapsed < timing.exposure ? 'exposing' : elapsed < end ? 'transferring' : 'complete' };
  }
  return state;
}
