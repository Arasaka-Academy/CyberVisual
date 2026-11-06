import { useEffect, useRef, useState, useSyncExternalStore } from 'react';
import { ArrowLeft, ArrowRight, Beaker, Camera, Check, ChevronRight, Cpu, Focus, Grid3X3, Info, Moon, RotateCcw, Rotate3D, Send, Sun, Lightbulb } from 'lucide-react';
import Scene from './Scene.jsx';
import Snapshot from './Snapshot.jsx';
import Sandbox from './Sandbox.jsx';
import { lessons, partDetails, phaseLabels, themes } from './lessons.mjs';
import { lessonStore, telemetry } from './store.mjs';

const dispatch = lessonStore.dispatch;
const themeOrder = ['paper', 'graphite', 'blueprint'];
const readTheme = () => { try { const value = localStorage.getItem('cybervisual.lesson.theme'); return themes[value] ? value : 'paper'; } catch { return 'paper'; } };

function RangeControl({ id, label, value, min, max, unit = '°', onChange, help }) {
  return <div className="range-control">
    <div className="range-label"><label htmlFor={id}>{label}</label><output htmlFor={id}>{value > 0 && unit === '°' ? '+' : ''}{value}{unit}</output></div>
    <input id={id} type="range" min={min} max={max} value={value} aria-describedby={`${id}-help`} onChange={event => onChange(Number(event.target.value))} />
    <div className="range-ticks" aria-hidden="true"><span>{min}{unit}</span><span>{unit === '°' ? '0°' : '装配进度'}</span><span>{unit === '°' ? '+' : ''}{max}{unit}</span></div>
    <p className="range-help" id={`${id}-help`}>{help}</p>
  </div>;
}

function CommandSteps({ phase }) {
  const current = phase === 'sending' ? 0 : phase === 'moving' ? 1 : phase === 'complete' ? 2 : -1;
  return <ol className="command-steps" aria-label="指令过程">
    {['发送目标', '驱动与运动', '到达目标'].map((text, i) => <li key={text} className={i <= current ? 'step-done' : ''}>
      <span className="step-mark">{current > i || current === 2 ? <Check size={11} /> : i + 1}</span><span>{text}</span>
    </li>)}
  </ol>;
}

function LessonControl({ state }) {
  switch (state.lesson) {
    case 'assembly': return <RangeControl id="assembly-progress" label="装配进度" value={Math.round(state.assembly * 100)} min={0} max={100} unit="%"
      onChange={value => dispatch({ type: 'ASSEMBLY', value: value / 100 })} help="向左拆开，向右组装。所有零件都从工作台归位。" />;
    case 'pan': return <RangeControl id="pan-angle" label="水平角度" value={state.pan} min={-90} max={90}
      onChange={value => dispatch({ type: 'ANGLE', axis: 'pan', value })} help="±90° 是本课的教学范围，实物还需考虑线缆与限位。" />;
    case 'tilt': return <RangeControl id="tilt-angle" label="俯仰角度" value={state.tilt} min={-35} max={35}
      onChange={value => dispatch({ type: 'ANGLE', axis: 'tilt', value })} help="±35° 是本课的教学范围，实物仍需核对机构限位。" />;
    case 'uart': return <div className="uart-controls">
      <div className="target-message"><span>教学示意 · 目标</span><div><span>水平 <b>+30°</b></span><span>俯仰 <b>+15°</b></span></div></div>
      <button type="button" className="primary-button full-width" disabled={['sending', 'moving'].includes(state.phase)} onClick={() => dispatch({ type: 'SEND' })}>
        <Send size={16} />{state.phase === 'complete' ? '再演示一次' : state.phase === 'sending' ? '正在发送…' : state.phase === 'moving' ? '正在转动…' : '发送双轴目标'}
      </button>
      <CommandSteps phase={state.phase} />
      <p className="range-help">采用语义指令解释过程，实际协议取决于电机驱动器型号。</p>
    </div>;
    case 'capture': return <div className="capture-controls">
      <Snapshot frame={state.frame} phase={state.phase} />
      <button type="button" className="primary-button full-width" disabled={['exposing', 'transferring'].includes(state.phase)} onClick={() => dispatch({ type: 'CAPTURE' })}>
        <Camera size={17} />{state.phase === 'exposing' ? '正在采集…' : state.phase === 'transferring' ? '正在回传…' : state.frame ? '再采集一帧' : '采集一帧'}
      </button>
      <p className="range-help">画面来自三维虚拟场景；镜头视场采用教学假设。</p>
    </div>;
    case 'sandbox': return <Sandbox state={state} dispatch={dispatch} />;
    default: return null;
  }
}

function References({ dialogRef }) {
  return <dialog className="reference-dialog" ref={dialogRef} aria-labelledby="reference-title">
    <div className="dialog-content"><Focus size={26} strokeWidth={1.4} /><h2 id="reference-title">模型与接口说明</h2>
      <p>这是一份浏览器原理课。零件、运动和数据流共同解释系统分工。</p>
      <dl>
        <div><dt>机械结构</dt><dd>底座、上座、托架与紧固件沿用项目内的实际 CAD 网格。相机零俯仰时按现有镜头包络相对底座居中。</dd></div>
        <div><dt>相机与镜头</dt><dd>IMX477 HQ PCB 为 38 × 38 mm、孔距 30 × 30 mm。镜头使用 Ø40 mm 参考外形，虚拟取景采用 52° 示例视角。</dd></div>
        <div><dt>运算板与驱动</dt><dd>Nano 采用 100 × 80 mm 参考开发板外形，接口布局为示意。微雪一体电机具体型号尚未提供，背部控制板表示内置串口驱动器。</dd></div>
        <div><dt>接口与供电</dt><dd>UART、CSI 和供电连线表达逻辑关系。真实引脚、电平、波特率、协议及供电规格，需按对应实物资料确认。Nano 默认单独供电。</dd></div>
        <div><dt>运动范围</dt><dd>水平 ±90°、俯仰 ±35° 为教学范围。模型与示意线缆不构成实物负载或排线运动验证。</dd></div>
      </dl>
      <div className="reference-links"><a href="https://www.waveshare.net/wiki/IMX477_12.3MP_Camera" target="_blank" rel="noreferrer">微雪 IMX477 资料 ↗</a><a href="https://developer.nvidia.com/embedded/jetson-nano-developer-kit" target="_blank" rel="noreferrer">NVIDIA Jetson Nano ↗</a></div>
      <form method="dialog"><button className="primary-button full-width">返回课件<ArrowRight size={16} /></button></form>
    </div>
  </dialog>;
}

export default function App() {
  const state = useSyncExternalStore(lessonStore.subscribe, lessonStore.getSnapshot);
  const [theme, setTheme] = useState(readTheme);
  const dialogRef = useRef(null), activeTab = useRef(null);
  const index = lessons.findIndex(lesson => lesson.id === state.lesson), lesson = lessons[index];
  const selected = partDetails[state.selected];
  const ThemeIcon = theme === 'paper' ? Sun : theme === 'graphite' ? Moon : Grid3X3;

  useEffect(() => {
    document.documentElement.dataset.theme = theme;
    document.querySelector('meta[name="theme-color"]').setAttribute('content', themes[theme].background);
    try { localStorage.setItem('cybervisual.lesson.theme', theme); } catch { /* Storage can be disabled in private/embedded contexts. */ }
  }, [theme]);
  useEffect(() => {
    const preference = matchMedia('(prefers-reduced-motion: reduce)');
    const update = () => dispatch({ type: 'MOTION_PREFERENCE', value: preference.matches });
    update(); preference.addEventListener('change', update);
    return () => preference.removeEventListener('change', update);
  }, []);
  useEffect(() => {
    const keydown = event => {
      if (event.metaKey || event.ctrlKey || event.altKey || dialogRef.current?.open || event.target.closest('input,textarea,select,[contenteditable="true"]')) return;
      if (/^[1-6]$/.test(event.key)) { event.preventDefault(); dispatch({ type: 'LESSON', lesson: lessons[Number(event.key) - 1].id }); }
      if (event.key === 'Escape') dispatch({ type: 'SELECT', part: null });
      if (event.key.toLowerCase() === 'r') dispatch({ type: 'RESET' });
    };
    window.addEventListener('keydown', keydown);
    window.__lesson = { getState: lessonStore.getSnapshot, telemetry };
    return () => { window.removeEventListener('keydown', keydown); delete window.__lesson; };
  }, []);
  useEffect(() => {
    const nav = activeTab.current?.parentElement;
    if (nav && activeTab.current) {
      const b = activeTab.current.getBoundingClientRect(), n = nav.getBoundingClientRect();
      if (b.left < n.left || b.right > n.right) nav.scrollTo({ left: activeTab.current.offsetLeft - nav.clientWidth / 2 + activeTab.current.offsetWidth / 2, behavior: state.reducedMotion ? 'instant' : 'smooth' });
    }
  }, [state.lesson, state.reducedMotion]);

  const choose = id => dispatch({ type: 'LESSON', lesson: id });
  const step = direction => {
    choose(lessons[(index + direction + lessons.length) % lessons.length].id);
    if (matchMedia('(max-width: 850px)').matches) document.getElementById('lesson-nav').scrollIntoView({ behavior: state.reducedMotion ? 'instant' : 'smooth', block: 'start' });
  };

  return <div className="app-shell">
    <header className="site-header"><a className="brand" href="#" onClick={e => { e.preventDefault(); choose('assembly'); }} aria-label="CyberVisual，返回第一课"><span className="brand-symbol"><Focus size={22} strokeWidth={1.5} /></span><span>CyberVisual<span className="brand-divider">/</span><span className="brand-course">交互实验课</span></span></a>
      <div className="header-actions"><span className="simulation-tag"><span />浏览器原理仿真</span><button className="theme-button" aria-label={`切换主题，当前${themes[theme].name}`} onClick={() => setTheme(themeOrder[(themeOrder.indexOf(theme) + 1) % themeOrder.length])}><ThemeIcon size={16} /><span>{themes[theme].name}</span></button></div>
    </header>
    <main>
      <section className="intro" aria-labelledby="page-title"><div><h1 id="page-title">双轴视觉云台<span className="title-period">。</span></h1><p>动手理解，一台会转动的相机如何工作。</p></div><div className="hardware-summary"><span><Cpu size={17} />Jetson Nano</span><span><Rotate3D size={17} />2 × 42 步进电机</span><span><Camera size={17} />IMX477</span></div></section>
      <nav id="lesson-nav" className="lesson-nav" aria-label="课程章节">{lessons.map((item, i) => <button key={item.id} ref={item.id === state.lesson ? activeTab : null} type="button" data-lesson={item.id} aria-current={item.id === state.lesson ? 'step' : undefined} className={`${item.id === state.lesson ? 'active' : ''} ${item.id === 'sandbox' ? 'sandbox-tab' : ''}`} onClick={() => choose(item.id)}>
        {item.id === 'sandbox' ? <Beaker size={16} /> : <span className="chapter-number">{String(i + 1).padStart(2, '0')}</span>}<span>{item.nav}</span>
      </button>)}</nav>
      <div className={`lesson-workspace ${state.lesson === 'sandbox' ? 'sandbox-workspace' : ''}`}>
        <div className="scene-column"><Scene state={state} theme={theme} dispatch={dispatch} />
          <div className="scene-caption"><span>{lesson.caption}</span><span>点选零件，查看分工<ChevronRight size={13} /></span></div>
        </div>
        <section className="lesson-panel" aria-labelledby="lesson-title">
          <div className="lesson-panel-top"><span>{state.lesson === 'sandbox' ? '自由实验' : `第 ${index + 1} 课 / 共 5 课`}</span><button type="button" className="reset-button" onClick={() => dispatch({ type: 'RESET' })} aria-label="复位当前课程"><RotateCcw size={14} />复位</button></div>
          <div className="lesson-copy" key={state.lesson}><h2 id="lesson-title">{lesson.title.split('\n').map((line, i) => <span key={i}>{line}</span>)}</h2><p className="lesson-intro">{lesson.intro}</p><p className="lesson-detail">{lesson.detail}</p></div>
          <div className="lesson-operation"><LessonControl state={state} /></div>
          {['uart', 'capture', 'sandbox'].includes(state.lesson) && <p className={`phase-status ${state.phase !== 'idle' ? 'phase-active' : ''}`} role="status"><span className={`phase-shape phase-${state.phase}`} />{phaseLabels[state.phase]}</p>}
          {lesson.insight && <p className="lesson-insight"><Lightbulb size={17} strokeWidth={1.4} /><span>{lesson.insight}</span></p>}
          {selected && <aside className="part-detail" aria-label="零件说明"><span>{selected.role}</span><h3>{selected.title}</h3><p>{selected.text}</p><button type="button" onClick={() => dispatch({ type: 'SELECT', part: null })}>返回课程<ArrowRight size={12} /></button></aside>}
          <div className="lesson-pagination"><button type="button" onClick={() => step(-1)} disabled={index === 0}><ArrowLeft size={16} />上一课</button><button type="button" onClick={() => step(1)}>{index === 4 ? '自己搭建' : index === 5 ? '重新学习' : '下一课'}<ArrowRight size={16} /></button></div>
        </section>
      </div>
      <section className="system-map" aria-label="系统分工"><button onClick={() => dispatch({ type: 'SELECT', part: 'nano' })}><Cpu size={19} strokeWidth={1.4} /><span><strong>思考与控制</strong><small>Jetson Nano</small></span></button><button onClick={() => dispatch({ type: 'SELECT', part: 'yaw' })}><Rotate3D size={19} strokeWidth={1.4} /><span><strong>运动与朝向</strong><small>两个一体驱动步进电机</small></span></button><button onClick={() => dispatch({ type: 'SELECT', part: 'camera' })}><Camera size={19} strokeWidth={1.4} /><span><strong>观察与取景</strong><small>IMX477 HQ</small></span></button></section>
    </main>
    <footer className="site-footer"><button type="button" onClick={() => dialogRef.current.showModal()}><Info size={14} />模型与接口说明</button><span className="keyboard-help">1–5 切课 · 6 搭建 · R 复位 · Esc 取消选中</span><span>探索 · 理解 · 动手</span></footer>
    <References dialogRef={dialogRef} />
  </div>;
}
