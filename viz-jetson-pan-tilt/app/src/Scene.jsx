import { Component, Suspense, useEffect, useLayoutEffect, useMemo, useRef, useState } from 'react';
import { Canvas, useFrame, useThree } from '@react-three/fiber';
import { Grid, Html, Line, OrbitControls, RoundedBox, useGLTF } from '@react-three/drei';
import { Home, ScanLine, ArrowUpRight, Rotate3D, RefreshCw } from 'lucide-react';
import * as THREE from 'three';
import { RoomEnvironment } from 'three/examples/jsm/environments/RoomEnvironment.js';
import { GIMBAL_POSITION, NANO_POSITION, SUPPLY_POSITION, opticalPose, radians } from './kinematics.mjs';
import { lessonStore, telemetry } from './store.mjs';
import { isValidConnection, signalProgress } from './simulation.mjs';
import { themes } from './lessons.mjs';

const assetUrl = file => window.__LESSON_ASSETS__?.[file] ?? `${import.meta.env.BASE_URL}assets/${file}`;
const initialTarget = [-.02, .067, 0];
const trayOffsets = { yaw: [.13, 0, .09], upper: [.14, -.062, -.065], tilt: [-.02, -.10, -.13], camera: [-.10, -.103, .125], nano: [-.025, 0, .12], power: [.22, 0, .015] };
const assemblyPhases = { yaw: [.02, .25], upper: [.25, .50], tilt: [.50, .73], camera: [.73, 1] };
const smooth = value => { const x = THREE.MathUtils.clamp(value, 0, 1); return x * x * (3 - 2 * x); };
const anchors = {
  'nano.uart-pan': ['nano', 'anchor_nano_uart'], 'nano.uart-tilt': ['nano', 'anchor_nano_uart_tilt'],
  'nano.csi': ['nano', 'anchor_nano_csi'], 'yaw.uart': ['gimbal', 'anchor_pan_uart'],
  'yaw.power': ['gimbal', 'anchor_pan_power'], 'tilt.uart': ['gimbal', 'anchor_tilt_uart'],
  'tilt.power': ['gimbal', 'anchor_tilt_power'], 'camera.csi': ['gimbal', 'anchor_camera_csi'],
  'power.pan': ['power', 'anchor_supply'], 'power.tilt': ['power', 'anchor_supply_tilt'],
};

function placement(state, id) {
  let progress = 1;
  if (state.lesson === 'sandbox') progress = state.sandbox.placed.includes(id) ? 1 : 0;
  else if (state.lesson === 'assembly' && assemblyPhases[id]) {
    const [start, end] = assemblyPhases[id];
    progress = smooth((state.assembly - start) / (end - start));
  }
  const offset = trayOffsets[id].map(v => v * (1 - progress));
  if (progress > 0 && progress < 1) offset[1] += .027 * Math.sin(progress * Math.PI);
  return offset;
}

function SimulationClock() {
  const frames = useRef({ time: 0, count: 0 });
  useFrame((_, delta) => {
    lessonStore.tick(delta);
    frames.current.time += delta; frames.current.count++;
    if (frames.current.time > 1) { telemetry.fps = Math.round(frames.current.count / frames.current.time); frames.current = { time: 0, count: 0 }; }
  }, -5);
  return null;
}

function StudioEnvironment({ theme }) {
  const { gl, scene } = useThree();
  useEffect(() => {
    const pmrem = new THREE.PMREMGenerator(gl), room = new RoomEnvironment();
    const target = pmrem.fromScene(room, .04);
    scene.environment = target.texture;
    scene.environmentIntensity = .5;
    return () => { scene.environment = null; target.dispose(); room.dispose(); pmrem.dispose(); };
  }, [gl, scene]);
  return <>
    <color attach="background" args={[themes[theme].background]} />
    <hemisphereLight args={['#f5f5ed', '#9aa48d', 1.3]} />
    <directionalLight position={[-.3, .5, .4]} intensity={2.4} color="#fff3dd" castShadow
      shadow-mapSize={[1024, 1024]} shadow-camera-left={-.4} shadow-camera-right={.4}
      shadow-camera-top={.4} shadow-camera-bottom={-.4} shadow-camera-near={.01} shadow-camera-far={2}
      shadow-normalBias={.0004} shadow-bias={-.00005} />
    <directionalLight position={[.3, .2, -.3]} intensity={1.2} color="#e9eff4" />
    <RoundedBox args={[.56, .006, .37]} radius={.004} smoothness={3} position={[-.03, -.0035, 0]} receiveShadow>
      <meshStandardMaterial color={themes[theme].floor} roughness={.88} />
    </RoundedBox>
    <Grid position={[-.03, -.00035, 0]} args={[.55, .36]} cellSize={.02} sectionSize={.1}
      cellColor={themes[theme].grid} sectionColor={themes[theme].grid} cellThickness={.4} sectionThickness={.7}
      fadeDistance={1.2} fadeStrength={1} infiniteGrid={false} />
  </>;
}

function Asset({ kind, file, position, state, theme, models }) {
  const { scene } = useGLTF(assetUrl(file));
  const model = useMemo(() => {
    const copy = scene.clone(true);
    copy.traverse(obj => {
      if (!obj.isMesh) return;
      obj.material = obj.material.clone();
      obj.userData.originalColor = obj.material.color.clone();
      obj.castShadow = true; obj.receiveShadow = true;
    });
    return copy;
  }, [scene]);
  const root = useRef(null);
  const groups = useMemo(() => kind === 'gimbal' ? {
    yaw: [model.getObjectByName('YawMotor'), model.getObjectByName('YawRotor')],
    upper: [model.getObjectByName('UpperStructure')],
    tilt: [model.getObjectByName('TiltMotor'), model.getObjectByName('TiltRotor')],
    camera: [model.getObjectByName('CameraAssembly')],
  } : null, [kind, model]);

  useLayoutEffect(() => { models.current[kind] = model; telemetry.ready = true; return () => { delete models.current[kind]; }; }, [kind, model, models]);
  useEffect(() => () => { model.traverse(obj => { if (obj.isMesh) obj.material.dispose(); }); }, [model]);
  useEffect(() => {
    model.traverse(obj => {
      if (!obj.isMesh) return;
      let parent = obj, part = kind === 'gimbal' ? null : kind;
      while (parent) { if (parent.userData.lessonPart) { part = parent.userData.lessonPart; break; } parent = parent.parent; }
      obj.material.color.copy(obj.userData.originalColor);
      if (theme === 'blueprint' && !obj.name.includes('glass')) obj.material.color.lerp(new THREE.Color('#7eb0c3'), .48);
      const selected = state.selected === part;
      obj.material.emissive.set(selected ? '#a05c35' : '#000000');
      obj.material.emissiveIntensity = selected ? .20 : 0;
      if (state.selected && !selected) obj.material.color.lerp(new THREE.Color(themes[theme].floor), .13);
    });
  }, [model, theme, state.selected]);

  useFrame((_, delta) => {
    const current = lessonStore.getSnapshot();
    if (groups) {
      model.getObjectByName('PanPivot').rotation.y = radians(current.pan);
      model.getObjectByName('TiltPivot').rotation.x = -radians(current.tilt);
      for (const [id, nodes] of Object.entries(groups)) {
        const target = new THREE.Vector3().fromArray(placement(current, id));
        for (const node of nodes) {
          if (current.reducedMotion || current.lesson === 'assembly') node.position.copy(target);
          else node.position.lerp(target, 1 - Math.exp(-delta * 15));
        }
      }
    } else if (root.current) {
      const target = new THREE.Vector3().fromArray(position).add(new THREE.Vector3().fromArray(placement(current, kind)));
      if (current.reducedMotion || current.lesson !== 'sandbox') root.current.position.copy(target);
      else root.current.position.lerp(target, 1 - Math.exp(-delta * 15));
    }
    model.updateWorldMatrix(true, true);
  }, -4);

  const select = event => {
    if (event.delta > 5) return;
    let obj = event.object, part = kind === 'gimbal' ? null : kind;
    while (obj) { if (obj.userData.lessonPart) { part = obj.userData.lessonPart; break; } obj = obj.parent; }
    if (part) { event.stopPropagation(); lessonStore.dispatch({ type: 'SELECT', part }); }
  };
  return <group ref={root} position={position}><primitive object={model} onClick={select} /></group>;
}

function readAnchors(models) {
  const points = {};
  for (const [id, [type, name]] of Object.entries(anchors)) {
    const node = models.current[type]?.getObjectByName(name);
    if (node) points[id] = node.getWorldPosition(new THREE.Vector3());
  }
  return points;
}

function CablePath({ edge, models, active, kind, invalid }) {
  const line = useRef(null), packet = useRef(null);
  const initial = useMemo(() => [[0, 0, 0], [.001, 0, 0]], []);
  const color = invalid ? '#c56648' : kind === 'csi' ? '#2a8b7d' : kind === 'power' ? '#738776' : '#af754e';
  useFrame(() => {
    const points = readAnchors(models), start = points[edge.from], end = points[edge.to];
    if (!start || !end || !line.current) return;
    const a = start.clone(), b = end.clone();
    const c1 = a.clone(), c2 = b.clone();
    if (kind === 'power') { c1.y += .015; c1.z += .07; c2.y += .022; c2.z += .045; }
    else if (kind === 'csi') { c1.add(new THREE.Vector3(-.04, .05, -.025)); c2.add(new THREE.Vector3(.018, .065, .008)); }
    else { c1.y = Math.max(a.y, b.y) + .055; c1.z -= .015; c2.y = b.y + .035; c2.z += .025; }
    const curve = new THREE.CubicBezierCurve3(a, c1, c2, b);
    const samples = curve.getPoints(48);
    line.current.geometry.setPositions(samples.flatMap(p => p.toArray()));
    line.current.computeLineDistances();
    if (packet.current) {
      const state = lessonStore.getSnapshot();
      packet.current.position.copy(curve.getPoint(signalProgress(state, kind)));
      packet.current.visible = active && !state.reducedMotion;
    }
    telemetry.anchors = Object.fromEntries(Object.entries(points).map(([id, v]) => [id, v.toArray()]));
    telemetry.connectorGap = Math.max(samples[0].distanceTo(start), samples.at(-1).distanceTo(end));
  }, -2);
  return <>
    <Line ref={line} points={initial} color={color} lineWidth={kind === 'power' ? 1.4 : 2} transparent opacity={active ? .95 : .58} />
    <mesh ref={packet} visible={false}><sphereGeometry args={[.0019, 10, 8]} /><meshBasicMaterial color={color} /></mesh>
  </>;
}

function Connections({ state, models }) {
  let edges = [];
  if (state.lesson === 'sandbox') edges = state.sandbox.connections;
  else if (state.signals && state.lesson === 'uart') edges = [{ from: 'nano.uart-pan', to: 'yaw.uart' }, { from: 'nano.uart-tilt', to: 'tilt.uart' }];
  else if (state.signals && state.lesson === 'capture') edges = [{ from: 'camera.csi', to: 'nano.csi' }];
  return edges.map(edge => {
    const kind = edge.from.includes('power') || edge.to.includes('power') ? 'power' : edge.from.includes('csi') || edge.to.includes('csi') ? 'csi' : 'uart';
    const active = state.sandbox.running || (kind === 'uart' && state.phase === 'sending') || (kind === 'csi' && state.phase === 'transferring');
    return <CablePath key={`${edge.from}-${edge.to}`} edge={edge} models={models} active={active} kind={kind} invalid={!isValidConnection(edge)} />;
  });
}

function AxisGuide({ state }) {
  const pose = opticalPose(state.pan, state.tilt);
  const origin = pose.position.map((v, i) => v + GIMBAL_POSITION[i]);
  const tip = origin.map((v, i) => v + pose.direction[i] * .060);
  const points = useMemo(() => Array.from({ length: 65 }, (_, i) => {
    const angle = radians(state.lesson === 'pan' ? -90 + i / 64 * 180 : -35 + i / 64 * 70);
    return state.lesson === 'pan' ? [.055 + Math.sin(angle) * .066, .002, Math.cos(angle) * .066] : [.106, .126 + Math.sin(angle) * .049, Math.cos(angle) * .049];
  }), [state.lesson]);
  if (!['pan', 'tilt'].includes(state.lesson)) return null;
  return <>
    <Line points={points} color="#ac744d" lineWidth={1.5} transparent opacity={.65} />
    <Line points={[origin, tip]} color="#b8754d" lineWidth={2} />
    <mesh position={tip}><sphereGeometry args={[.002, 10, 8]} /><meshBasicMaterial color="#ad6c43" /></mesh>
  </>;
}

function ModelLabels({ state, models }) {
  const nano = useRef(null), camera = useRef(null);
  useFrame(() => {
    const n = models.current.nano?.getObjectByName('Nano_heatsink_base');
    const c = models.current.gimbal?.getObjectByName('anchor_camera_optical');
    if (n && nano.current) { n.getWorldPosition(nano.current.position); nano.current.position.y += .046; }
    if (c && camera.current) { c.getWorldPosition(camera.current.position); camera.current.position.y += .046; }
  }, -1.5);
  if (state.lesson === 'sandbox' || (state.lesson === 'assembly' && state.assembly < .98)) return null;
  return <>
    <group ref={nano}><Html center zIndexRange={[4, 0]} style={{ pointerEvents: 'none' }}><div className="model-label"><span className="label-dot" />Jetson Nano<span className="label-leader" /></div></Html></group>
    <group ref={camera}><Html center zIndexRange={[4, 0]} style={{ pointerEvents: 'none' }}><div className="model-label"><span className="label-dot" />IMX477<span className="label-leader" /></div></Html></group>
  </>;
}

function ViewControls({ state, view, revision }) {
  const { camera, size } = useThree(), controls = useRef(null), flying = useRef(true);
  const destination = useRef({ eye: new THREE.Vector3(), target: new THREE.Vector3() });
  const needsTray = state.lesson === 'sandbox' ? state.sandbox.placed.length < 6 : state.lesson === 'assembly' && state.assembly < .98;
  useEffect(() => {
    const focused = ['pan', 'tilt'].includes(state.lesson);
    const narrowTray = needsTray && size.width / size.height < 1.15;
    const target = narrowTray ? [.015, .068, .015] : focused ? [.055, .082, 0] : [-.02, .067, 0];
    let eye = focused ? [.29, .22, .36] : [.32, .245, .43];
    if (size.width / size.height < 1.15) eye = narrowTray ? [.53, .385, .83] : [.365, .295, .57];
    if (view === 'front') eye = [target[0], .11, narrowTray ? 1.08 : .58];
    if (view === 'top') eye = [target[0], narrowTray ? 1.08 : .62, .015];
    destination.current = { eye: new THREE.Vector3(...eye), target: new THREE.Vector3(...target) };
    flying.current = true;
  }, [state.lesson, needsTray, size.width, size.height, view, revision]);
  useFrame((_, delta) => {
    if (!flying.current || !controls.current) return;
    const blend = state.reducedMotion ? 1 : 1 - Math.exp(-delta * 5);
    camera.position.lerp(destination.current.eye, blend);
    controls.current.target.lerp(destination.current.target, blend);
    controls.current.update();
    if (camera.position.distanceTo(destination.current.eye) < .0002 && controls.current.target.distanceTo(destination.current.target) < .0002) flying.current = false;
  });
  return <OrbitControls ref={controls} target={initialTarget} makeDefault enableDamping dampingFactor={.12} minDistance={.17} maxDistance={1.25}
    maxPolarAngle={Math.PI / 2 - .02} minPolarAngle={.03} enablePan={false} onStart={() => { flying.current = false; }} />;
}

function SceneDiagnostics({ models }) {
  const { camera, controls } = useThree();
  const elapsed = useRef(0);
  useFrame((_, delta) => {
    elapsed.current += delta;
    if (elapsed.current < .25 || !models.current.gimbal) return;
    elapsed.current = 0;
    camera.updateMatrixWorld();
    const points = [];
    for (const model of Object.values(models.current)) model.traverse(obj => {
      if (!obj.isMesh) return;
      if (!obj.geometry.boundingBox) obj.geometry.computeBoundingBox();
      const box = obj.geometry.boundingBox;
      for (const x of [box.min.x, box.max.x]) for (const y of [box.min.y, box.max.y]) for (const z of [box.min.z, box.max.z]) points.push(new THREE.Vector3(x, y, z).applyMatrix4(obj.matrixWorld).project(camera));
    });
    telemetry.subjectBounds = {
      left: (Math.min(...points.map(p => p.x)) + 1) / 2, right: (Math.max(...points.map(p => p.x)) + 1) / 2,
      top: (1 - Math.max(...points.map(p => p.y))) / 2, bottom: (1 - Math.min(...points.map(p => p.y))) / 2,
    };
    telemetry.camera = { position: camera.position.toArray(), target: controls?.target?.toArray() };
  });
  return null;
}

class SceneBoundary extends Component {
  state = { failed: false };
  static getDerivedStateFromError() { return { failed: true }; }
  render() {
    if (this.state.failed) return <div className="scene-fallback"><img src={assetUrl('reference-assembly.png')} alt="IMX477 云台静态装配参考图" /><div><strong>3D 视图暂时无法加载</strong><p>可查看静态结构，或重试 WebGL 视图。</p><button className="secondary-button" onClick={this.props.retry}><RefreshCw size={15} />重新加载</button></div></div>;
    return this.props.children;
  }
}

export default function Scene({ state, theme, dispatch }) {
  const models = useRef({}), [view, setView] = useState('free'), [revision, setRevision] = useState(0), [attempt, setAttempt] = useState(0);
  const [dragOver, setDragOver] = useState(false);
  return <section className={`scene-stage ${dragOver ? 'stage-drop' : ''}`} aria-label="交互式云台工作台"
    onDragOver={e => { if (state.lesson === 'sandbox') { e.preventDefault(); setDragOver(true); } }}
    onDragLeave={() => setDragOver(false)} onDrop={e => { e.preventDefault(); setDragOver(false); dispatch({ type: 'PLACE', part: e.dataTransfer.getData('application/x-lesson-part') }); }}>
    <div className="stage-top"><span><span className="status-dot" />{state.lesson === 'sandbox' ? '搭建工作台' : '整机视图'}</span><div className="view-controls" aria-label="查看方向">
      <button aria-label="复位视角" title="复位视角" onClick={() => { setView('free'); setRevision(n => n + 1); }}><Home size={16} /></button>
      <button aria-label="正面视角" aria-pressed={view === 'front'} title="正面视角" onClick={() => setView('front')}><ScanLine size={16} /></button>
      <button aria-label="顶视角" aria-pressed={view === 'top'} title="顶视角" onClick={() => setView('top')}><ArrowUpRight size={17} /></button>
    </div></div>
    <SceneBoundary key={attempt} retry={() => setAttempt(n => n + 1)}>
      <Canvas shadows dpr={[1, 1.7]} camera={{ position: [.32, .245, .43], fov: 32, near: .001, far: 5 }}
        gl={{ antialias: true, powerPreference: 'high-performance' }}
        onCreated={({ gl }) => { gl.toneMapping = THREE.ACESFilmicToneMapping; gl.toneMappingExposure = .95; gl.outputColorSpace = THREE.SRGBColorSpace; }}
        onPointerMissed={() => dispatch({ type: 'SELECT', part: null })}>
        <SimulationClock /><StudioEnvironment theme={theme} />
        <Suspense fallback={<Html center><span className="scene-loading">正在准备云台…</span></Html>}>
          <Asset kind="gimbal" file="gimbal.glb" position={GIMBAL_POSITION} state={state} theme={theme} models={models} />
          <Asset kind="nano" file="nano.glb" position={NANO_POSITION} state={state} theme={theme} models={models} />
          <Asset kind="power" file="supply.glb" position={SUPPLY_POSITION} state={state} theme={theme} models={models} />
          <Connections state={state} models={models} /><AxisGuide state={state} /><ModelLabels state={state} models={models} />
        </Suspense>
        <ViewControls state={state} view={view} revision={revision} />
        <SceneDiagnostics models={models} />
      </Canvas>
    </SceneBoundary>
    {dragOver && <div className="drop-hint">松开放入，设备会归位到装配位置</div>}
    <div className="stage-bottom"><div className="pose-readouts"><span>水平 <b data-testid="pan-readout">{signed(state.pan)}</b></span><span>俯仰 <b data-testid="tilt-readout">{signed(state.tilt)}</b></span></div><span className="orbit-help"><Rotate3D size={14} /><span className="desktop-hint">拖动旋转 · 滚轮缩放</span><span className="touch-hint">单指旋转 · 双指缩放</span></span></div>
  </section>;
}
function signed(value) { return `${value > .05 ? '+' : ''}${Math.abs(value) < .05 ? '0' : value.toFixed(0)}°`; }
for (const file of ['gimbal.glb', 'nano.glb', 'supply.glb']) useGLTF.preload(assetUrl(file));
