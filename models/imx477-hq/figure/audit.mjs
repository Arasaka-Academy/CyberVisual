// Independent orthographic ray/plane depth samples over the actual CAD polygons.
// Imported STL surfaces cannot be represented by anatomy's primitive recorder.
// This checks their SVG painter order; generate.py checks real solid collisions.
import {readFileSync,writeFileSync} from 'node:fs';
import {dirname,resolve} from 'node:path';
import {fileURLToPath} from 'node:url';
import * as k from './vendor/iso-kit.mjs';
import {prepareScene,drawScene,assemblyMotion} from './geometry.mjs';
const here=dirname(fileURLToPath(import.meta.url)),data=JSON.parse(readFileSync(resolve(here,'scene.json'))),scene=prepareScene(data);
const points=data.parts.flatMap(p=>p.vertices.flatMap(v=>[v,v.map((x,i)=>x+assemblyMotion(p,1).offset[i])]));
const dot=(a,b)=>a.reduce((s,v,i)=>s+v*b[i],0);
const records=[];
for(const [azimuth,elevation] of [[225,26],[45,26],[270,0],[270,90]]){
  const P=k.fitProjection(points,800,620,{pad:62,azimuth,elevation});
  const a=azimuth*Math.PI/180,e=elevation*Math.PI/180,scale=P.scale*Math.sqrt(1.6);
  const R=[Math.sin(a),-Math.cos(a),0],D=[Math.cos(a)*Math.sin(e),Math.sin(a)*Math.sin(e),-Math.cos(e)],V=[Math.cos(a)*Math.cos(e),Math.sin(a)*Math.cos(e),Math.sin(e)];
  const poses=[...Array.from({length:11},(_,i)=>({explode:i/10,pitch:0})),{explode:0,pitch:-35},{explode:0,pitch:35}];
  for(const pose of poses){
    const result=drawScene(scene,P,{...pose,audit:true}),grid=13,depths=new Map();let failures=0,covered=0,samples=0;
    for(const polygon of result.orderedPolygons){
      const vertices=polygon.v.map(v=>{const p=k.iso(v,P);return[p[0],p[1]+result.frameOffsetY];});
      const minX=Math.min(...vertices.map(v=>v[0])),maxX=Math.max(...vertices.map(v=>v[0])),minY=Math.min(...vertices.map(v=>v[1])),maxY=Math.max(...vertices.map(v=>v[1]));
      for(let y=Math.ceil(minY/grid)*grid+.371;y<maxY;y+=grid)for(let x=Math.ceil(minX/grid)*grid+.173;x<maxX;x+=grid){
        let sign=0,inside=true;
        for(let i=0;i<vertices.length;i++){
          const p=vertices[i],q=vertices[(i+1)%vertices.length],c=(q[0]-p[0])*(y-p[1])-(q[1]-p[1])*(x-p[0]);
          if(Math.abs(c)<1e-8)continue;
          const next=Math.sign(c);if(sign&&sign!==next){inside=false;break;}sign=next;
        }
        if(!inside)continue;
        const u=(x-P.origin[0])/scale,v=(y-P.origin[1]-result.frameOffsetY)/scale,base=R.map((r,i)=>r*u+D[i]*v);
        const distance=(dot(polygon.n,polygon.v[0])-dot(polygon.n,base))/dot(polygon.n,V);
        const key=x.toFixed(3)+','+y.toFixed(3),prior=depths.get(key);
        if(prior!==undefined&&prior-distance>1e-3)failures++;
        depths.set(key,Math.max(prior??-Infinity,distance));samples++;
      }
    }
    covered=depths.size;records.push({azimuth,elevation,...pose,visible_triangles:result.triangles,ordered_fragments:result.fragments,covered_pixels:covered,ray_surface_tests:samples,depth_order_failures:failures});
  }
}
const failures=records.reduce((n,r)=>n+r.depth_order_failures,0);
writeFileSync(resolve(here,'depth-audit.json'),JSON.stringify({method:'Independent ray/plane depth samples on real CAD surfaces; grid 13 viewBox pixels, deterministic subpixel offset.',poses:records,depth_order_failures:failures},null,2)+'\n');
console.log(`SVG CAD depth audit: ${records.length} poses; ${records.reduce((n,r)=>n+r.ray_surface_tests,0)} ray/surface tests; ${failures} depth order failures`);
if(failures){process.exitCode=1;}else console.log('SVG CAD depth audit passed');
