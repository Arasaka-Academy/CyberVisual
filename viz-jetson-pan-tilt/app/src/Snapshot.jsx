import { useEffect, useRef, useState } from 'react';
import { Camera, Focus, ArrowDownToLine } from 'lucide-react';
import * as THREE from 'three';
import { opticalPose, GIMBAL_POSITION } from './kinematics.mjs';

function makeVirtualScene() {
  const scene = new THREE.Scene();
  scene.background = new THREE.Color('#e5e9e4');
  scene.add(new THREE.HemisphereLight(0xffffff, 0x8c9a85, 2.1));
  const sun = new THREE.DirectionalLight(0xfff9eb, 2.4);
  sun.position.set(-1, 2, -1);
  scene.add(sun);

  const chart = document.createElement('canvas');
  chart.width = 1200; chart.height = 800;
  const ctx = chart.getContext('2d');
  ctx.fillStyle = '#f3f2e9'; ctx.fillRect(0, 0, 1200, 800);
  ctx.strokeStyle = '#d5d8ca'; ctx.lineWidth = 2;
  for (let x = 0; x <= 1200; x += 80) { ctx.beginPath(); ctx.moveTo(x, 0); ctx.lineTo(x, 800); ctx.stroke(); }
  for (let y = 0; y <= 800; y += 80) { ctx.beginPath(); ctx.moveTo(0, y); ctx.lineTo(1200, y); ctx.stroke(); }
  ctx.strokeStyle = '#506951'; ctx.lineWidth = 8;
  for (const r of [60, 130, 200]) { ctx.beginPath(); ctx.arc(600, 370, r, 0, Math.PI * 2); ctx.stroke(); }
  ctx.beginPath(); ctx.moveTo(335, 370); ctx.lineTo(865, 370); ctx.moveTo(600, 105); ctx.lineTo(600, 635); ctx.stroke();
  ctx.fillStyle = '#344f3b'; ctx.font = '30px monospace';
  ctx.fillText('CYBERVISUAL / VIRTUAL TARGET', 45, 64);
  ctx.font = '20px monospace'; ctx.fillText('SIMULATED SCENE', 45, 758);
  const colors = ['#bc6e42', '#e5b966', '#498b7f', '#375c77', '#56674c', '#292f2c'];
  colors.forEach((c, i) => { ctx.fillStyle = c; ctx.fillRect(45 + i * 63, 658, 56, 56); });
  for (let i = 0; i < 9; i++) {
    ctx.fillStyle = i % 2 ? '#f3f2e9' : '#344137';
    ctx.fillRect(925 + i * 18, 160, 12, 330);
  }
  const texture = new THREE.CanvasTexture(chart);
  texture.colorSpace = THREE.SRGBColorSpace;
  const target = new THREE.Mesh(new THREE.PlaneGeometry(.75, .5), new THREE.MeshStandardMaterial({ map: texture, roughness: 1 }));
  target.position.set(.055, .19, .60);
  target.rotation.y = Math.PI;
  scene.add(target);
  const floor = new THREE.Mesh(new THREE.PlaneGeometry(4, 4), new THREE.MeshStandardMaterial({ color: '#cbd2c3', roughness: 1 }));
  floor.rotation.x = -Math.PI / 2;
  floor.position.y = -.03;
  scene.add(floor);
  for (const [x, y, z, color, size] of [
    [-.10, .022, .38, '#b56d44', .075], [.19, .015, .44, '#30776e', .06],
  ]) {
    const box = new THREE.Mesh(new THREE.BoxGeometry(size, size, size), new THREE.MeshStandardMaterial({ color, roughness: .7 }));
    box.position.set(x, y, z); box.rotation.y = .22; scene.add(box);
  }
  return scene;
}

export default function Snapshot({ frame, phase, compact = false }) {
  const engine = useRef(null);
  const [image, setImage] = useState(null);
  const [failed, setFailed] = useState(false);

  useEffect(() => {
    let renderer;
    try {
      renderer = new THREE.WebGLRenderer({ antialias: true, preserveDrawingBuffer: true });
      renderer.setSize(640, 400);
      renderer.setPixelRatio(1);
      renderer.outputColorSpace = THREE.SRGBColorSpace;
      renderer.toneMapping = THREE.ACESFilmicToneMapping;
      renderer.toneMappingExposure = .9;
      engine.current = { renderer, scene: makeVirtualScene(), camera: new THREE.PerspectiveCamera(52, 1.6, .005, 5) };
    } catch { setFailed(true); }
    return () => {
      if (engine.current) {
        engine.current.scene.traverse(obj => {
          obj.geometry?.dispose();
          if (obj.material) { obj.material.map?.dispose(); obj.material.dispose(); }
        });
      }
      renderer?.dispose();
      engine.current = null;
    };
  }, []);

  useEffect(() => {
    if (!frame || !engine.current) return;
    const { renderer, scene, camera } = engine.current;
    const pose = opticalPose(frame.pan, frame.tilt);
    camera.position.fromArray(pose.position.map((v, i) => v + GIMBAL_POSITION[i]));
    camera.up.fromArray(pose.up);
    camera.lookAt(new THREE.Vector3().fromArray(pose.direction).add(camera.position));
    renderer.render(scene, camera);
    setImage(renderer.domElement.toDataURL('image/png'));
  }, [frame]);

  return <section className={`snapshot ${compact ? 'snapshot-compact' : ''}`} aria-label="虚拟取景">
    <div className="snapshot-heading"><span><Focus size={15} />虚拟取景</span><span>{frame ? `帧 ${String(frame.id).padStart(3, '0')}` : '等待采集'}</span></div>
    <div className={`snapshot-image ${phase === 'exposing' ? 'exposing' : ''}`}>
      {image ? <img src={image} alt={`云台水平 ${frame.pan.toFixed(1)} 度、俯仰 ${frame.tilt.toFixed(1)} 度时的虚拟取景`} data-pan={frame.pan} data-tilt={frame.tilt} /> :
        <div className="snapshot-placeholder"><Camera size={24} strokeWidth={1.3} /><span>{failed ? '当前浏览器无法生成虚拟取景' : '按下采集，看看镜头里的世界'}</span></div>}
      <span className="viewfinder-corner corner-tl" /><span className="viewfinder-corner corner-tr" />
      <span className="viewfinder-corner corner-bl" /><span className="viewfinder-corner corner-br" />
      {image && <span className="capture-stamp"><ArrowDownToLine size={12} />CSI · 虚拟图像</span>}
    </div>
    <div className="snapshot-meta"><span>水平 {frame ? signed(frame.pan) : '—'}</span><span>俯仰 {frame ? signed(frame.tilt) : '—'}</span><span>52° 示例视角</span></div>
  </section>;
}

function signed(n) { return `${n > .05 ? '+' : ''}${Math.abs(n) < .05 ? '0' : n.toFixed(1)}°`; }
