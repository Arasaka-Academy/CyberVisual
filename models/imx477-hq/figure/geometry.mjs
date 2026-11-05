// Exact CAD triangles, shaded and ordered as SVG solid surfaces.
// The SVG uses the anatomy kit's orthographic camera, without WebGL or a CDN.
const add = (a,b) => a.map((v,i)=>v+b[i]);
const sub = (a,b) => a.map((v,i)=>v-b[i]);
const mul = (a,t) => a.map(v=>v*t);
const dot = (a,b) => a.reduce((s,v,i)=>s+v*b[i],0);
const cross = (a,b) => [a[1]*b[2]-a[2]*b[1],a[2]*b[0]-a[0]*b[2],a[0]*b[1]-a[1]*b[0]];
const unit = a => mul(a,1/(Math.hypot(...a)||1));
const rotate = (p,angle) => { const c=Math.cos(angle),s=Math.sin(angle); return [p[0],p[1]*c-p[2]*s,p[1]*s+p[2]*c]; };
const area = p => Math.hypot(...cross(sub(p.v[1],p.v[0]),sub(p.v[2],p.v[0])));
const phase=(s,a,b)=>Math.max(0,Math.min(1,(s-a)/(b-a)));

export function assemblyMotion(part,s){
  const move=phase(s,.65,1),group=[-20*move,0,15*move];
  if(part.name.startsWith('m2p5x12')||part.name.startsWith('m2p5-washer')){
    const i=Number(part.name.split('-')[part.name.startsWith('m2p5x12')?1:2]),side=i<2?-1:1;
    return {offset:add(group,[14*side*phase(s,.16,.28),-18*phase(s,0,.16),0]),flex:0};
  }
  if(part.name.startsWith('m2p5-nut'))return {offset:add(group,[0,4*phase(s,.55,.65),0]),flex:0};
  if(['camera','glass'].includes(part.category))return {offset:add(group,[0,-30*phase(s,.3,.55),0]),flex:0};
  if(part.name.startsWith('m3x5'))return {offset:add(group,[0,8*phase(s,0,.25),0]),flex:0};
  return {offset:mul(part.explode,move),flex:0};
}

export function prepareScene(data) {
  const parts=data.parts.map(part => {
    const vertices=part.vertices, faces=part.faces.map(indices=>{
      const v=indices.map(i=>vertices[i]);
      return {indices,v,n:unit(cross(sub(v[1],v[0]),sub(v[2],v[0])))};
    });
    const edges=new Map();
    faces.forEach((f,index)=>f.indices.forEach((a,i)=>{
      const b=f.indices[(i+1)%3],key=a<b?a+':'+b:b+':'+a;
      if(!edges.has(key))edges.set(key,[]);
      edges.get(key).push(index);
    }));
    faces.forEach(f=>{f.adj=f.indices.map((a,i)=>{
      const b=f.indices[(i+1)%3],key=a<b?a+':'+b:b+':'+a;
      return edges.get(key).map(j=>faces[j].n);
    });});
    return {...part,faces};
  });
  parts.pivot=[0,0,data.parameters.tilt_axis_z];
  return parts;
}

function onSegment(p,a,b) {
  const ab=sub(b,a),ap=sub(p,a),length=dot(ab,ab),t=dot(ap,ab)/(length||1);
  return t>=-1e-5&&t<=1.00001&&Math.hypot(...sub(ap,mul(ab,t)))<1e-4;
}

function split(poly,n,w) {
  const ds=poly.v.map(v=>dot(n,v)-w),eps=1e-5;
  const front=ds.some(d=>d>eps),back=ds.some(d=>d< -eps);
  if(!front&&!back)return {coplanar:[poly]};
  if(!back)return {front:[poly]};
  if(!front)return {back:[poly]};
  const f=[],b=[];
  for(let i=0;i<poly.v.length;i++){
    const j=(i+1)%poly.v.length,a=poly.v[i],da=ds[i],db=ds[j];
    if(da>=-eps)f.push(a);
    if(da<=eps)b.push(a);
    if((da>eps&&db< -eps)||(da< -eps&&db>eps)){
      const v=add(a,mul(sub(poly.v[j],a),da/(da-db)));f.push(v);b.push(v);
    }
  }
  return {front:f.length>=3?[{...poly,v:f}]:[],back:b.length>=3?[{...poly,v:b}]:[]};
}

function ordered(polygons,V) {
  let splits=0;
  const walk=(polys,depth=0)=>{
    if(!polys.length)return [];
    if(depth>240)throw new Error('CAD painter BSP exceeded depth bound');
    let candidate=polys[0],largest=0;
    // Large real planes cut the scene into stable, simple regions first.
    for(const p of polys){const a=area(p);if(a>largest){largest=a;candidate=p;}}
    const n=candidate.n,w=dot(n,candidate.v[0]),f=[],b=[],c=[];
    for(const p of polys){
      const s=split(p,n,w);if(s.front)f.push(...s.front);if(s.back)b.push(...s.back);if(s.coplanar)c.push(...s.coplanar);
      if(s.front&&s.back)splits++;
    }
    if(splits>45000)throw new Error('CAD painter BSP exceeded split bound');
    return dot(n,V)>0?[...walk(b,depth+1),...c,...walk(f,depth+1)]:[...walk(f,depth+1),...c,...walk(b,depth+1)];
  };
  return {polygons:walk(polygons),splits};
}

function ink(category,n,theme,name) {
  const light=theme==='light',facing=Math.round(Math.max(0,Math.min(1,.52+.25*n[2]-.22*n[1]-.1*n[0]))*256)/256;
  if(category==='new')return `hsl(29 67% ${light?62+facing*17:22+facing*15}%)`;
  if(category==='glass')return `hsl(206 15% ${light?17+facing*9:43+facing*11}%)`;
  if(category==='motor')return `hsl(220 3% ${light?(name.includes('stack')?23:44)+facing*12:13+facing*12}%)`;
  if(category==='fastener')return `hsl(220 4% ${light?28+facing*11:37+facing*14}%)`;
  if(category==='camera')return `hsl(212 4% ${light?(name==='camera-pcb'?30:36)+facing*14:21+facing*15}%)`;
  return `hsl(42 7% ${light?78+facing*18:24+facing*15}%)`;
}

export function drawScene(scene,P,{explode=0,pitch=0,theme='light',exact=true,audit=false}={}) {
  const a=P.azimuth*Math.PI/180,e=P.elevation*Math.PI/180,scale=P.scale*Math.sqrt(1.6);
  const V=[Math.cos(a)*Math.cos(e),Math.sin(a)*Math.cos(e),Math.sin(e)];
  let frameOffsetY=0;
  const project=([x,y,z])=>[P.origin[0]+(x*Math.sin(a)-y*Math.cos(a))*scale,
    P.origin[1]+((x*Math.cos(a)+y*Math.sin(a))*Math.sin(e)-z*Math.cos(e))*scale+frameOffsetY];
  const pol=[],r=-pitch*Math.PI/180,pivot=scene.pivot;
  const cameraBounds=[[Infinity,Infinity,Infinity],[-Infinity,-Infinity,-Infinity]];
  for(const part of scene){
    const tilts=['new','camera','glass'].includes(part.category)||part.name.startsWith('m3x5')||part.name.startsWith('m2p5')||part.name==='tilt-shaft';
    const motion=assemblyMotion(part,explode);
    const point=v=>add(tilts?add(rotate(sub(v,pivot),r),pivot):v,motion.offset);
    const normal=v=>tilts?rotate(v,r):v;
    for(const face of part.faces){
      const v=face.v.map(point),n=motion.flex?unit(cross(sub(v[1],v[0]),sub(v[2],v[0]))):normal(face.n),feature=[];
      if(['camera','glass'].includes(part.category))for(const p of v)for(let i=0;i<3;i++){
        cameraBounds[0][i]=Math.min(cameraBounds[0][i],p[i]);
        cameraBounds[1][i]=Math.max(cameraBounds[1][i],p[i]);
      }
      if(dot(n,V)<1e-7)continue;
      face.adj.forEach((adj,i)=>{
        if(adj.length!==2||adj.some(m=>dot(normal(m),V)<1e-7)||dot(adj[0],adj[1])<.75)
          feature.push([v[i],v[(i+1)%3]]);
      });
      pol.push({v,n,feature,category:part.category,name:part.name});
    }
  }
  let minY=Infinity,maxY=-Infinity;
  for(const p of pol)for(const v of p.v){const y=project(v)[1];minY=Math.min(minY,y);maxY=Math.max(maxY,y);}
  frameOffsetY=310-(minY+maxY)/2;
  const sorted=exact?ordered(pol,V):{polygons:pol.sort((p,q)=>dot(mul(p.v.reduce(add,[0,0,0]),1/p.v.length),V)-dot(mul(q.v.reduce(add,[0,0,0]),1/q.v.length),V)),splits:0};
  const path=vertices=>vertices.map((v,i)=>{const p=project(v);return (i?'L':'M')+p[0].toFixed(3)+' '+p[1].toFixed(3);}).join('')+'Z';
  let body='',pending=null;
  const flush=()=>{if(!pending)return;body+=`<g data-cad-part="${pending.name}"><path d="${pending.fill}" fill="${pending.colour}" stroke="${pending.colour}" stroke-width=".24" stroke-linejoin="round"/>`;if(pending.edges)body+=`<path class="iso-line" d="${pending.edges}" fill="none" stroke="${theme==='light'?'#414448':'#b2b3b6'}" stroke-width=".55" stroke-linecap="round"/>`;body+='</g>';};
  for(const p of sorted.polygons){
    const colour=ink(p.category,p.n,theme,p.name);
    let edges='';
    for(let i=0;i<p.v.length;i++){
      const a=p.v[i],b=p.v[(i+1)%p.v.length];
      if(p.feature.some(([s,t])=>onSegment(a,s,t)&&onSegment(b,s,t))){
        const u=project(a),v=project(b);edges+='M'+u[0].toFixed(3)+' '+u[1].toFixed(3)+'L'+v[0].toFixed(3)+' '+v[1].toFixed(3);
      }
    }
    const key=p.name+'|'+colour+'|'+Math.round(dot(p.n,p.v[0])*1000);
    if(!pending||pending.key!==key){flush();pending={key,name:p.name,colour,fill:'',edges:''};}
    pending.fill+=path(p.v);pending.edges+=edges;
  }
  flush();
  return {body,triangles:pol.length,fragments:sorted.polygons.length,splits:sorted.splits,frameOffsetY,
    cameraCentre:cameraBounds[0].map((v,i)=>(v+cameraBounds[1][i])/2),...(audit?{orderedPolygons:sorted.polygons}:{} )};
}
