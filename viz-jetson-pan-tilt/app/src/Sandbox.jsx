import { useRef, useState } from 'react';
import { Check, Plus, Cable, Play, Square, Unplug, AlertCircle, Cpu, Camera, Rotate3D, Braces, PlugZap } from 'lucide-react';
import { partIds, partNames, ports, portById, validateBuild, isValidConnection } from './simulation.mjs';
import Snapshot from './Snapshot.jsx';

const partIcons = { nano: Cpu, yaw: Rotate3D, upper: Braces, tilt: Rotate3D, camera: Camera, power: PlugZap };

export default function Sandbox({ state, dispatch }) {
  const build = state.sandbox;
  const pending = build.pendingPort;
  const setPending = port => dispatch({ type: 'PENDING_PORT', port });
  const boardRef = useRef(null);
  const pointerStart = useRef(null);
  const [pointer, setPointer] = useState(null);
  const result = validateBuild(build);
  const sources = ports.filter(p => p.side === 'source'), targets = ports.filter(p => p.side === 'target');
  const linked = id => build.connections.some(e => e.from === id || e.to === id);
  const ready = p => build.placed.includes(p.owner);

  const choose = port => {
    if (!ready(port)) return;
    if (!pending) setPending(port.id);
    else if (pending === port.id) setPending(null);
    else { dispatch({ type: 'CONNECT', from: pending, to: port.id }); setPending(null); }
  };
  const portButton = port => <button key={port.id} className={`port ${pending === port.id ? 'port-selected' : ''} ${linked(port.id) ? 'port-linked' : ''}`}
    type="button" aria-label={`连接 ${port.label}`} aria-pressed={pending === port.id} disabled={!ready(port)}
    data-port={port.id} data-kind={port.kind}
    onClick={() => choose(port)}
    onPointerDown={e => {
      if (!ready(port) || e.button !== 0) return;
      pointerStart.current = { id: port.id, x: e.clientX, y: e.clientY };
    }}>
    {port.side === 'target' && <span className="port-dot">{linked(port.id) && <Check size={10} />}</span>}
    <span>{port.label}</span>
    {port.side === 'source' && <span className="port-dot">{linked(port.id) && <Check size={10} />}</span>}
  </button>;

  const handleMove = e => {
    if (!pointerStart.current || !boardRef.current) return;
    if (Math.hypot(e.clientX - pointerStart.current.x, e.clientY - pointerStart.current.y) < 8) return;
    const b = boardRef.current.getBoundingClientRect();
    setPointer({ x1: pointerStart.current.x - b.left, y1: pointerStart.current.y - b.top, x2: e.clientX - b.left, y2: e.clientY - b.top });
  };
  const handleUp = e => {
    if (pointer && pointerStart.current) {
      const port = document.elementFromPoint(e.clientX, e.clientY)?.closest('[data-port]')?.dataset.port;
      if (port && ready(portById[port]) && port !== pointerStart.current.id) dispatch({ type: 'CONNECT', from: pointerStart.current.id, to: port });
      setPending(null);
    }
    pointerStart.current = null; setPointer(null);
  };

  return <div className="sandbox-controls">
    <div className="subsection-heading"><h3>1. 放入设备</h3><span>{build.placed.length} / 6</span></div>
    <p className="control-help">拖到工作台，或点选放入。</p>
    <div className="parts-tray" aria-label="零件托盘">
      {partIds.map(id => {
        const placed = build.placed.includes(id), Icon = partIcons[id];
        return <button key={id} type="button" className={`tray-part ${placed ? 'placed' : ''}`} draggable={!placed}
          aria-label={`${placed ? '已放入' : '放入'}${partNames[id]}`} disabled={placed}
          onDragStart={e => { e.dataTransfer.setData('application/x-lesson-part', id); e.dataTransfer.effectAllowed = 'copy'; }}
          onClick={() => dispatch({ type: 'PLACE', part: id })}>
          <Icon size={17} strokeWidth={1.5} /><span>{partNames[id]}</span>{placed ? <Check size={14} /> : <Plus size={14} />}
        </button>;
      })}
    </div>
    <div className="subsection-heading wiring-heading"><h3>2. 连接接口</h3><Cable size={16} /></div>
    <p className="control-help" id="wiring-help">先点起点，再点终点；也可在接口间拖线。</p>
    <div className="wiring-board" ref={boardRef} onPointerMove={handleMove} onPointerUp={handleUp}
      onPointerLeave={() => { pointerStart.current = null; setPointer(null); }} aria-describedby="wiring-help">
      <div className="ports-column">{sources.map(portButton)}</div>
      <div className="ports-column">{targets.map(portButton)}</div>
      {pointer && <svg className="wire-drag" aria-hidden="true"><path d={`M${pointer.x1},${pointer.y1} C${(pointer.x1 + pointer.x2) / 2},${pointer.y1} ${(pointer.x1 + pointer.x2) / 2},${pointer.y2} ${pointer.x2},${pointer.y2}`} /></svg>}
    </div>
    {pending && <p className="pending-wire" role="status">已选 {portById[pending].label}，请选择另一端。</p>}
    {build.connections.length > 0 && <ul className="connections" aria-label="已连接线路">
      {build.connections.map((edge, index) => <li key={`${edge.from}-${edge.to}`} className={isValidConnection(edge) ? '' : 'invalid'}>
        <span>{isValidConnection(edge) ? <Check size={13} /> : <AlertCircle size={13} />}{portById[edge.from].label} → {portById[edge.to].label}</span>
        <button type="button" aria-label={`移除连接 ${portById[edge.from].label} 到 ${portById[edge.to].label}`} onClick={() => dispatch({ type: 'REMOVE_CONNECTION', index })}><Unplug size={13} /></button>
      </li>)}
    </ul>}
    <div className="run-controls">
      <button type="button" className="primary-button" onClick={() => dispatch({ type: 'RUN' })} disabled={build.running}><Play size={15} fill="currentColor" />运行实验</button>
      <button type="button" className="secondary-button" onClick={() => dispatch({ type: 'STOP' })} disabled={!build.running}><Square size={13} fill="currentColor" />停止</button>
    </div>
    {build.checked && !result.ok && <div className="build-feedback" role="alert"><strong><AlertCircle size={15} />还差一点，检查这些地方</strong><ul>{build.errors.map(error => <li key={error}>{error}</li>)}</ul></div>}
    {result.ok && <p className="build-success" role="status"><Check size={16} />{build.running ? state.reducedMotion ? '系统已运行，以静态姿态展示。' : '系统已运行，图像每两秒采集一帧。' : '组装与连接完整，可以运行。'}</p>}
    {state.frame && <Snapshot frame={state.frame} phase={state.phase} compact />}
  </div>;
}
