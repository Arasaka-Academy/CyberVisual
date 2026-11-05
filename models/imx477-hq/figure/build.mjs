import { readFileSync, writeFileSync, mkdirSync } from 'node:fs';
import { dirname, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';
import * as k from './vendor/iso-kit.mjs';
import { prepareScene, drawScene, assemblyMotion } from './geometry.mjs';

const HERE=dirname(fileURLToPath(import.meta.url));
const data=JSON.parse(readFileSync(resolve(HERE,'scene.json'),'utf8'));
const scene=prepareScene(data),W=800,H=620;
const points=data.parts.flatMap(p=>p.vertices.flatMap(v=>[v,v.map((x,i)=>x+assemblyMotion(p,1).offset[i])]));
const front=k.fitProjection(points,W,H,{pad:62,azimuth:225,elevation:26});
const rear=k.fitProjection(points,W,H,{pad:62,azimuth:45,elevation:26});
const orthofront=k.fitProjection(points,W,H,{pad:62,azimuth:270,elevation:0});
const top=k.fitProjection(points,W,H,{pad:62,azimuth:270,elevation:90});
const stamp=JSON.stringify({front,rear,orthofront,top});
const geometry=readFileSync(resolve(HERE,'geometry.mjs'),'utf8').replace(/export /g,'');

const css=`
:root{font-synthesis:none}body{--new:#b86e33;--line:#dfdfd9;--surface:#f8f8f5;--quiet:#71716b;--dark:#202320}
body[data-theme="dark"]{--new:#dea263;--line:#32332f;--surface:#1b1c19;--quiet:#9c9e94;--dark:#eee}
.iso-page{margin:38px auto 60px;width:min(1120px,100% - 40px)}
a{color:inherit;text-decoration:none}a:hover{text-decoration:underline}
.breadcrumb{font:10px/1.4 var(--anatomy-mono);letter-spacing:.16em;color:var(--quiet);display:flex;justify-content:space-between;gap:20px}
.breadcrumb span:last-child{letter-spacing:.04em}.intro{display:flex;align-items:end;justify-content:space-between;gap:24px;padding:31px 0 27px}
h1{font-size:35px;line-height:1.2;letter-spacing:-.04em;color:var(--dark);font-weight:600;margin:0 0 12px}
.intro p{margin:0;color:var(--quiet);font-size:13px;letter-spacing:.025em}.download{background:var(--dark);color:var(--anatomy-page);padding:12px 17px;border-radius:5px;font-size:12px;white-space:nowrap}
.iso-plate{border:1px solid var(--line);border-radius:9px;background:var(--anatomy-card);box-shadow:0 4px 10px #00000003;overflow:hidden;padding-bottom:24px;position:relative}
.iso-plate-corner{font-family:var(--anatomy-mono);font-size:10px;letter-spacing:.03em;color:var(--quiet)}
.drawing-grid{display:grid;grid-template-columns:minmax(0,1fr) 232px;padding:30px 30px 0 0}
.iso-stage{outline:none;touch-action:pan-y;min-width:0}.iso-stage:focus-visible{outline:2px solid var(--new);outline-offset:-10px;border-radius:12px}
.iso-stage[data-view="orthofront"] [data-shadow],.iso-stage[data-view="top"] [data-shadow]{display:none}
.iso-svg{width:100%;height:auto;display:block;aspect-ratio:800/620}.specs{align-self:center;padding-right:5px}
.eyebrow{font-size:9px;letter-spacing:.14em;font-family:var(--anatomy-mono);color:var(--quiet);margin:0 0 9px}
.specs h2{font-size:17px;letter-spacing:-.02em;color:var(--dark);font-weight:550;margin:0 0 12px}
.specs p{font-size:12px;line-height:1.9;margin:0;color:var(--quiet)}
.spec-block{border-top:1px solid var(--line);padding-top:19px;margin-top:23px}.spec-block:first-child{border:0;margin:0;padding:0}
.spec-block .accent{color:var(--new)}.hardware{display:grid;grid-template-columns:1fr auto;gap:9px 12px;font:12px/1.5 var(--anatomy-mono);color:var(--dark)}
.hardware span:nth-child(2n){color:var(--quiet)}
.controls{display:flex;align-items:center;gap:15px;flex-wrap:wrap;padding:4px 28px 25px;justify-content:space-between}
button{appearance:none;font:inherit;border:1px solid var(--line);border-radius:5px;background:transparent;color:var(--quiet);padding:7px 11px;cursor:pointer;font-size:11px}
button:hover{border-color:var(--quiet)}button[aria-pressed="true"]{background:var(--surface);color:var(--dark);border-color:var(--quiet)}
button:focus-visible,a:focus-visible,input:focus-visible{outline:2px solid var(--new);outline-offset:3px}
.buttons{display:flex;gap:6px;flex-wrap:wrap}.slider{display:flex;align-items:center;gap:10px;font-size:11px;color:var(--quiet)}
.slider input{width:130px;accent-color:var(--new)}output{font-family:var(--anatomy-mono);font-variant-numeric:tabular-nums;min-width:34px;color:var(--dark)}
.iso-legend{display:flex;justify-content:space-between;gap:18px;flex-wrap:wrap;padding:15px 2px 0;font-size:11px;color:var(--quiet)}
.legend-keys{display:flex;gap:19px;align-items:center}.legend-keys span{display:flex;gap:7px;align-items:center}.swatch{width:8px;height:8px;border:1px solid #93968e;background:#d5d6cf;border-radius:2px}.swatch.new{background:#e1a163;border-color:#c98848}.swatch.motor{background:#5a5d5f;border-color:#414447}
.facts{display:grid;grid-template-columns:repeat(4,1fr);border-top:1px solid var(--line);border-bottom:1px solid var(--line);margin-top:31px;padding:21px 0}
.fact{padding-left:25px;border-left:1px solid var(--line)}.fact:first-child{padding:0;border:0}.fact b{font:23px/1.2 var(--anatomy-mono);color:var(--dark);font-weight:450}.fact small{display:block;font-size:10px;color:var(--quiet);margin-top:8px}
.steps{display:grid;grid-template-columns:repeat(3,1fr);gap:35px;padding-top:28px}.step-no{font:10px var(--anatomy-mono);color:var(--new)}.steps h3{font-size:13px;color:var(--dark);font-weight:550;margin:9px 0}.steps p{margin:0;font-size:11px;line-height:1.9;color:var(--quiet)}
.note{font-size:10px;color:var(--quiet);line-height:1.9;border-top:1px solid var(--line);padding-top:16px;margin-top:27px}.note a{text-decoration:underline;text-underline-offset:3px}.footer{font:9px/1.6 var(--anatomy-mono);letter-spacing:.05em;display:flex;justify-content:space-between;color:var(--quiet);margin-top:22px}
@media(max-width:720px){.iso-page{width:calc(100% - 28px);margin-top:23px}.intro{align-items:start;flex-direction:column;gap:18px;padding:26px 0 24px}h1{font-size:29px}.intro p{font-size:11px}.download{padding:10px 13px}.drawing-grid{display:block;padding:25px 0 0}.iso-svg{width:115%;margin-left:-7.5%}.specs{display:grid;grid-template-columns:1fr 1fr;gap:16px;padding:0 22px 22px}.spec-block{margin:0;padding-top:14px}.spec-block:first-child{border-top:1px solid var(--line);padding-top:14px}.spec-block:last-child{display:none}.specs h2{font-size:14px}.specs p{font-size:10px}.hardware{font-size:10px;gap:6px 8px}.eyebrow{font-size:8px}.controls{padding:0 20px 24px;gap:16px}.slider input{width:95px}.iso-plate-corner{font-size:8px}.legend-keys{gap:12px}.iso-legend{font-size:9px;gap:10px}.facts{grid-template-columns:repeat(2,1fr);gap:20px 0}.fact:nth-child(3){padding-left:0;border:0}.fact b{font-size:21px}.fact small{font-size:9px}.steps{grid-template-columns:1fr;gap:20px;padding-top:24px}.steps h3{margin:6px 0}.breadcrumb{font-size:8px;letter-spacing:.1em}.breadcrumb span:last-child{display:none}.footer{font-size:8px}.note{font-size:9px}}
@media(prefers-reduced-motion:reduce){*{scroll-behavior:auto!important}}
`;

for(const theme of ['light','dark']){
  const assembled=drawScene(scene,front,{theme,exact:true});
  const exploded=drawScene(scene,front,{theme,explode:1,exact:true});
  const bodySvg=`<defs><filter id="ground-shadow"><feGaussianBlur stdDeviation="10"/></filter></defs><g data-shadow transform="translate(0 ${assembled.frameOffsetY})"><ellipse cx="407" cy="534" rx="147" ry="18" fill="${theme==='light'?'#c8c9bd':'#030402'}" opacity=".27" filter="url(#ground-shadow)"/></g><g data-scene>${assembled.body}</g>`;
  const label='微雪 IMX477 HQ 居中双轴云台：原底座、带加强肋的居中上座、绕到背面的四点螺丝托架。零俯仰时相机与参考镜头的联合包络中心对齐底座中心X=0、Y=0。';
  const svg=k.figureSvg({width:W,height:H,label,body:bodySvg});
  const neutralReadout='0° · X '+assembled.cameraCentre[0].toFixed(2)+' / Y '+assembled.cameraCentre[1].toFixed(2)+' mm';
  const plate=k.plateHtml({fig:'FIG. 01',title:'IMX477 / C·CS',hint:'空格拆装 · ← → 调整俯仰',readout:neutralReadout,body:`
<div class="drawing-grid"><div class="iso-stage" tabindex="0" role="group" aria-label="交互装配示意图，空格切换拆装，左右方向键调整俯仰，Escape复位">${svg}</div>
<aside class="specs" aria-label="安装规格"><div class="spec-block"><div class="eyebrow">CENTRED CAMERA + LENS</div><h2>正面、顶视均居中</h2><p>零俯仰：包络中心 X 0 / Y 0 mm<br>38 × 38 mm · 孔距 30 × 30 mm<br>四点螺丝固定，背面留空 5 mm。</p></div>
<div class="spec-block"><div class="eyebrow">CAMERA FASTENERS · NEW</div><div class="hardware"><span>M2.5 × 12</span><span>4 颗</span><span>M2.5 螺母</span><span>4 个</span><span>绝缘垫圈</span><span>4 个</span></div></div>
<div class="spec-block"><div class="eyebrow">PRINTED IN PETG</div><h2 class="accent">居中上座 + 绕背托架</h2><p>俯仰轴通过参考相机包络中心。<br>原 9 颗 M3 螺丝继续使用。<br>底座沿用，上座和托架重打印。</p></div></aside></div>
<div class="controls"><div class="buttons"><button data-mode="assembly" aria-pressed="true">装配</button><button data-mode="explode" aria-pressed="false">拆装</button><button data-view aria-pressed="false">背面</button><button data-ortho="orthofront" aria-pressed="false">正面</button><button data-ortho="top" aria-pressed="false">顶视</button></div><label class="slider">俯仰 <input data-pitch type="range" min="-35" max="35" step="1" value="0" aria-label="参考俯仰角"><output data-angle>0°</output></label><button data-theme-toggle>${theme==='light'?'深色':'浅色'}</button></div>`});
  const content=`<style>${css}</style><div class="breadcrumb"><span>CYBERVISUAL / MECHANICAL</span><span>05 NOV 2026 · REV C</span></div>
<header class="intro"><div><h1>IMX477 居中云台</h1><p>相机与参考镜头，正面和顶视均对齐底座中心。</p></div><a class="download" href="../print/IMX477-HQ-print-layout.3mf" download>下载打印盘 · 3MF ↗</a></header>
${plate}<div class="iso-legend"><div class="legend-keys"><span><i class="swatch"></i>原底座与居中上座</span><span><i class="swatch new"></i>绕背相机托架</span><span><i class="swatch motor"></i>电机与相机</span></div><span>镜头外形为参考包络</span></div>
<div class="facts"><div class="fact"><b>3</b><small>打印件：底座、居中上座、托架</small></div><div class="fact"><b>13</b><small>9 颗原有 M3 + 4 颗新增 M2.5</small></div><div class="fact"><b>X 0 / Y 0</b><small>参考相机包络中心 mm · 零俯仰</small></div><div class="fact"><b>±35°</b><small>已检查的参考刚体俯仰包络</small></div></div>
<div class="steps"><div><span class="step-no">01 / BASE</span><h3>打印居中上座和托架</h3><p>底座可沿用。底座用 4 颗 M3×10 固定水平电机；新上座用 4 颗 M3×6 固定右侧抬高的俯仰电机。</p></div><div><span class="step-no">02 / CARRIER</span><h3>安装绕背托架</h3><p>对齐 D 轴平面装入托架。径向底孔先攻 M3 螺纹，再用 M3×5 固定。侧臂绕到 PCB 背面，让镜头落在底座中央。</p></div><div><span class="step-no">03 / CAMERA</span><h3>四角拧入 M2.5 螺丝</h3><p>背面放入 4 个六角螺母，PCB 四孔对齐支撑柱；前面垫绝缘垫圈，用 4 颗 M2.5×12 对角轻拧固定。CSI 排线留足转动余量。</p></div></div>
<p class="note">首件试装设计，尚未打印或实物验证。PCB 厚度按 1.6 mm、垫圈按 0.5 mm、普通六角螺母按厚 2 mm 建模；居中按 Ø40 mm / 从 PCB 前伸 54 mm 的参考镜头包络计算，更换镜头需重算。实际元件避让、轴配合、负载和排线余量需确认。±35° 来自每 1° 的刚体模型检查。 <a href="../README.zh-CN.md">打印与装配说明 ↗</a> · <a href="../validation.json">几何验证记录 ↗</a></p>
<div class="footer"><span>ANATOMY FIGURE / CAD GEOMETRY IN MILLIMETRES</span><a href="assembly-${theme}.svg" download>SVG ↗</a></div>`;
  const live=`${geometry}
const scene=prepareScene(${JSON.stringify(data)}), cameras=${stamp};
let theme=${JSON.stringify(theme)},back=false,cameraMode='front',explode=0,target=0,pitch=0,wantPitch=0,frame=0,last=0,visible=true,inView=true,manual=performance.now(),tourStep=0;
const stage=document.querySelector('.iso-stage'), graphic=document.querySelector('[data-scene]'),readout=document.querySelector('[data-readout]'),slider=document.querySelector('[data-pitch]'),angle=document.querySelector('[data-angle]'),viewButton=document.querySelector('button[data-view]');
const reduced=matchMedia('(prefers-reduced-motion: reduce)');
const paint=(exact=true)=>{const result=drawScene(scene,back?cameras.rear:cameras[cameraMode],{theme,explode,pitch,exact});graphic.innerHTML=result.body;document.querySelector('[data-shadow]').setAttribute('transform','translate(0 '+result.frameOffsetY+')');graphic.dataset.fragments=result.fragments;graphic.dataset.splits=result.splits;stage.dataset.explode=explode.toFixed(4);stage.dataset.pitch=pitch.toFixed(3);stage.dataset.view=back?'rear':cameraMode;const centre=result.cameraCentre.map(v=>Math.abs(v)<.0005?'0.00':v.toFixed(2));readout.textContent=(explode>.01?'拆装示意 '+Math.round(explode*100)+'%':Math.round(pitch)+'° · X '+centre[0]+' / Y '+centre[1]+' mm');angle.textContent=Math.round(pitch)+'°';slider.value=String(Math.round(wantPitch));document.querySelectorAll('[data-mode]').forEach(b=>b.setAttribute('aria-pressed',String(b.dataset.mode===(target>.5?'explode':'assembly'))));viewButton.setAttribute('aria-pressed',String(back));document.querySelectorAll('[data-ortho]').forEach(b=>b.setAttribute('aria-pressed',String(!back&&cameraMode===b.dataset.ortho)));};
function tick(now){if(!visible){frame=0;return;}const dt=last?Math.min(.08,(now-last)/1000):.03;last=now;const f=reduced.matches?1:1-Math.exp(-dt/.24);explode+=(target-explode)*f;pitch+=(wantPitch-pitch)*f;const done=Math.abs(explode-target)<.002&&Math.abs(pitch-wantPitch)<.02;if(done){explode=target;pitch=wantPitch;}paint(true);frame=done?0:requestAnimationFrame(tick);}
const run=()=>{if(!frame&&visible){last=0;frame=requestAnimationFrame(tick);}};
const steer=()=>{manual=performance.now();run();};
document.querySelectorAll('[data-mode]').forEach(b=>b.addEventListener('click',()=>{target=b.dataset.mode==='explode'?1:0;wantPitch=0;steer();}));
slider.addEventListener('input',()=>{target=0;wantPitch=Number(slider.value);steer();});
viewButton.addEventListener('click',e=>{back=!back;e.currentTarget.setAttribute('aria-pressed',String(back));manual=performance.now();paint(true);});
document.querySelectorAll('[data-ortho]').forEach(b=>b.addEventListener('click',()=>{cameraMode=!back&&cameraMode===b.dataset.ortho?'front':b.dataset.ortho;back=false;explode=target=0;pitch=wantPitch=0;manual=performance.now();paint(true);}));
document.querySelector('[data-theme-toggle]').addEventListener('click',e=>{theme=theme==='light'?'dark':'light';document.body.dataset.theme=theme;e.currentTarget.textContent=theme==='light'?'深色':'浅色';manual=performance.now();paint(true);});
stage.addEventListener('keydown',e=>{if(e.key===' '){target=target>.5?0:1;wantPitch=0;}else if(e.key==='ArrowLeft'){target=0;wantPitch=Math.max(-35,wantPitch-5);}else if(e.key==='ArrowRight'){target=0;wantPitch=Math.min(35,wantPitch+5);}else if(e.key==='Escape'||e.key==='Home'){target=0;wantPitch=0;}else return;e.preventDefault();steer();});
stage.addEventListener('pointerdown',()=>{manual=performance.now();});
new IntersectionObserver(entries=>{inView=entries.at(-1).isIntersecting;visible=inView&&!document.hidden;if(visible&&(Math.abs(explode-target)>.002||Math.abs(pitch-wantPitch)>.02))run();else if(!visible&&frame){cancelAnimationFrame(frame);frame=0;}},{rootMargin:'100px'}).observe(stage);
document.addEventListener('visibilitychange',()=>{visible=inView&&!document.hidden;if(visible)run();});
reduced.addEventListener('change',()=>{manual=performance.now();if(reduced.matches){explode=target;pitch=wantPitch;paint(true);}});
setInterval(()=>{if(visible&&!document.hidden&&!reduced.matches&&!stage.matches(':hover,:focus-within')&&!document.querySelector('.controls').matches(':hover,:focus-within')&&performance.now()-manual>20000){tourStep++;target=tourStep%3===1?1:0;wantPitch=0;run();}},7000);
window.__cadFigure={setPose:({apart=0,tilt=0,rear=false,view='front'}={})=>{manual=performance.now();target=explode=apart;wantPitch=pitch=tilt;back=rear;cameraMode=view;paint(true);},scenePartCount:scene.length};
`;
  const html=k.pageHtml({title:'IMX477 相机云台 · CyberVisual',theme,body:content,script:live,width:1120}).replace('<html lang="en">','<html lang="zh-CN">');
  writeFileSync(resolve(HERE,theme==='light'?'index.html':'index-dark.html'),html);
  writeFileSync(resolve(HERE,`assembly-${theme}.svg`),k.figureSvg({width:W,height:H,label,body:bodySvg,standalone:theme}));
  writeFileSync(resolve(HERE,`exploded-${theme}.svg`),k.figureSvg({width:W,height:H,label:label+'（拆装位置）',body:`<g>${exploded.body}</g>`,standalone:theme}));
  for(const [name,camera] of [['front',orthofront],['top',top]]){
    const view=drawScene(scene,camera,{theme,exact:true});
    writeFileSync(resolve(HERE,`${name}-${theme}.svg`),k.figureSvg({width:W,height:H,label:label+`（${name==='front'?'正面':'顶视'}）`,body:view.body,standalone:theme}));
  }
  console.log(theme,JSON.stringify({parts:scene.length,assembled:{triangles:assembled.triangles,fragments:assembled.fragments,splits:assembled.splits},exploded:{triangles:exploded.triangles,fragments:exploded.fragments,splits:exploded.splits}}));
}
