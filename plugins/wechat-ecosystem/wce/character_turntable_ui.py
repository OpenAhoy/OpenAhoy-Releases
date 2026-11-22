"""Local geometric character rig for the versioned equipment-page demonstration."""

SCRIPT = r'''
function OACharacterTurntable(canvas){
 const gl=canvas.getContext('webgl',{alpha:true,antialias:true,preserveDrawingBuffer:true});
 const ctx=gl?null:canvas.getContext('2d');
 const TAU=2*Math.PI, radians=degrees=>degrees*Math.PI/180;
 const skin='#d39a75',dark='#3e2a2a';
 let pieces={hair:'hair-silver',wardrobe:'wardrobe-training',accessories:'accessories-none'};
 let yaw=0, zoom=1, focusX=0, focusY=0, beforeCloseup=null,feature='',motion=0,drag=null;
 let triangles=[];
 function triangle(a,b,c,color,lines=false){triangles.push({points:[a,b,c],color,lines});}
 function quad(a,b,c,d,color){triangle(a,b,c,color);triangle(a,c,d,color);}
 function ring(x,y,z,rx,rz,n){return Array.from({length:n},(_,i)=>[
   x+Math.cos(i/n*TAU)*rx,y,z+Math.sin(i/n*TAU)*rz]);}
 function tailor(sections,color,n=14){
   const rings=sections.map(([x,y,z,rx,rz])=>ring(x,y,z,rx,rz,n));
   for(let level=0;level<rings.length-1;level++){
     const a=rings[level],b=rings[level+1];
     for(let i=0;i<n;i++){const j=(i+1)%n;quad(a[i],a[j],b[j],b[i],color);}
   }
   for(const edge of [0,rings.length-1]){
     const points=rings[edge],center=sections[edge].slice(0,3);
     for(let i=0;i<n;i++)triangle(center,points[i],points[(i+1)%n],color);
   }
 }
 function oval(x,y,z,rx,ry,rz,color,n=16,steps=10){
   const sections=Array.from({length:steps+1},(_,i)=>{
     const a=(i/steps-.5)*Math.PI,cos=Math.max(.002,Math.cos(a));
     return [x,y+Math.sin(a)*ry,z,cos*rx,cos*rz];
   });
   tailor(sections,color,n);
 }
 function limb(x,y1,y2,z,r1,r2,color){tailor([[x,y1,z,r1,r1*.86],[x,y2,z,r2,r2*.86]],color,12);}
 function base(){
   oval(0,3.79,.015,.38,.49,.37,skin,24,15);
   limb(0,3.16,3.52,0,.18,.20,skin);
   oval(0,2.62,0,.429,.62,.224,skin);
   oval(0,1.96,.01,.384,.23,.221,skin);
   for(const side of [-1,1]){
     const x=side*.24;
     oval(x,1.10,.01,.17,.86,.16,skin);
     oval(x,.22,.09,.16,.19,.27,'#23252b');
     oval(side*.58,2.62,-.01,.13,.62,.135,skin);
     oval(side*.61,1.99,.005,.13,.22,.12,skin);
     oval(side*.375,3.75,.01,.07,.115,.105,skin);
     const eyed=side*.146;
     oval(eyed,3.85,.345,.092,.050,.027,'#f3e7d7',15,8);
     oval(eyed,3.851,.370,.039,.043,.015,'#688a85',14,8);
     oval(eyed,3.852,.383,.020,.027,.007,'#211f26',12,7);
     oval(eyed-.007,3.867,.391,.008,.009,.004,'#faf2e9',10,6);
     oval(eyed,3.951,.331,.10,.018,.021,dark,12,6);
   }
   oval(0,3.76,.359,.057,.102,.078,'#c98d6c',16);
   oval(0,3.63,.320,.091,.027,.025,'#814c4b',16);
 }
 function hairstyle(){
   const hair=pieces.hair;
   const tint=hair==='hair-bob'?'#473041':hair==='hair-tied'?'#a36b54':'#c8ccd5';
   oval(0,4.07,-.055,.435,.315,.407,tint,22,12);
   oval(0,3.87,-.21,.384,.40,.30,tint,20,11);
   if(hair==='hair-tied'){
     oval(.035,4.23,-.40,.19,.19,.22,'#b98468',18);
     oval(.045,3.94,-.475,.135,.32,.18,tint,16);
     return;
   }
   const long=hair!=='hair-bob';
   for(const side of [-1,1]){
     oval(side*.317,long?3.46:3.69,-.085,.17,long?.65:.37,.228,tint,20,12);
     oval(side*.31,long?3.20:3.53,-.25,.111,long?.50:.19,.173,
          long?'#a4a9b9':'#694454',15,10);
   }
   if(long)oval(0,3.48,-.32,.39,.60,.20,'#bec0cc',20,12);
   else oval(0,3.68,-.31,.35,.255,.22,'#563a49',18,10);
 }
 function outfit(){
   if(pieces.wardrobe==='wardrobe-suit'){
     for(const side of [-1,1]){
       const x=side*.226;
       tailor([[x,.28,.015,.181,.188],[x,.83,0,.185,.192],[x,1.51,0,.235,.23],[x,2.02,.012,.241,.256]],'#4d5266');
       limb(side*.579,2.16,3.06,-.01,.141,.187,'#53596e');
       limb(side*.58,2.12,2.25,-.011,.13,.143,'#e3d8d2');
     }
     tailor([[0,1.84,0,.51,.285],[0,2.31,0,.463,.26],[0,2.99,0,.615,.304],[0,3.15,-.015,.40,.244]],'#505569',18);
     triangle([-.218,3.13,.226],[.218,3.13,.226],[0,2.66,.313],'#e6dfd8',true);
     triangle([-.28,3.13,.25],[-.045,2.66,.328],[-.33,2.90,.312],'#788096',true);
     triangle([.28,3.13,.25],[.045,2.66,.328],[.33,2.90,.312],'#788096',true);
     for(const y of [2.41,2.25,2.10])oval(.035,y,.287,.024,.028,.022,'#c8ad83',10,6);
   }else if(pieces.wardrobe==='wardrobe-gala'){
     tailor([[0,.15,0,.77,.45],[0,.65,-.018,.65,.382],[0,1.64,-.01,.54,.316],
       [0,2.05,0,.50,.29],[0,2.35,0,.43,.275],[0,2.85,.012,.48,.304],[0,3.05,.01,.43,.26]],'#d3cbd9',20);
     tailor([[0,2.23,0,.445,.30],[0,2.35,0,.449,.30]],'#a88b9d',20);
     for(const side of [-1,1]){
       oval(side*.44,3.00,.02,.145,.185,.19,'#c1a6c0',18,10);
       triangle([side*.54,1.74,.214],[side*.71,.27,.31],[side*.39,.20,.40],'#b6adbd',true);
     }
     oval(0,2.30,.315,.08,.05,.036,'#dbba8f',14);
   }else{
     tailor([[0,2.40,0,.425,.273],[0,2.79,0,.50,.283],[0,2.97,.003,.46,.26]],'#2c3547',18);
     tailor([[0,2.38,0,.434,.279],[0,2.47,0,.446,.277]],'#627089',18);
     for(const side of [-1,1]){
       const x=side*.23;
       tailor([[x,1.33,0,.182,.20],[x,1.57,0,.235,.237],[x,2.11,.01,.23,.264]],'#343549');
     }
     tailor([[0,1.72,.001,.405,.248],[0,1.91,.002,.461,.285],[0,2.12,.008,.447,.277]],'#485067',18);
   }
 }
 function accessories(){
   if(pieces.accessories==='accessories-jewels'){
     for(const side of [-1,1]){
       oval(side*.395,3.66,.04,.048,.076,.052,'#e9c384',12);
       limb(side*.59,2.17,2.28,.002,.149,.149,'#d9af74');
       limb(side*.22,.16,.52,0,.184,.201,'#806c86');
     }
     tailor([[0,2.26,0,.51,.33],[0,2.31,0,.51,.33]],'#e2bd87',18);
   }else if(pieces.accessories==='accessories-boots'){
     for(const side of [-1,1]){
       limb(side*.235,.18,.86,0,.182,.192,'#423844');
       oval(side*.235,.21,.09,.185,.166,.26,'#4c4050');
       limb(side*.235,.62,.72,0,.197,.197,'#976d65');
     }
   }
 }
 const pipeline=gl?makePipeline():null;
 function makePipeline(){
   const vert='attribute vec3 position;attribute vec3 normal;attribute vec3 color;uniform vec4 framing;uniform vec2 turn;varying vec3 vNormal;varying vec3 vColor;'
    +'vec3 spin(vec3 p){return vec3(p.x*turn.x+p.z*turn.y,p.y,-p.x*turn.y+p.z*turn.x);}'
    +'void main(){vec3 p=spin(position);gl_Position=vec4((p.x-framing.z)*framing.x,(p.y-2.23-framing.w)*framing.y,-p.z*.68,1.);vNormal=spin(normal);vColor=color;}';
   const frag='precision mediump float;varying vec3 vNormal;varying vec3 vColor;'
    +'void main(){vec3 n=normalize(vNormal);if(!gl_FrontFacing)n=-n;'
    +'float intensity=.73+max(0.,dot(n,normalize(vec3(-.55,.76,.8))))*.34;gl_FragColor=vec4(vColor*intensity,1.);}';
   const program=gl.createProgram();
   for(const [type,source] of [[gl.VERTEX_SHADER,vert],[gl.FRAGMENT_SHADER,frag]]){
     const shader=gl.createShader(type);gl.shaderSource(shader,source);gl.compileShader(shader);
     if(!gl.getShaderParameter(shader,gl.COMPILE_STATUS))throw Error(gl.getShaderInfoLog(shader));
     gl.attachShader(program,shader);
   }
   gl.linkProgram(program);gl.useProgram(program);gl.enable(gl.DEPTH_TEST);
   const buffer=gl.createBuffer();gl.bindBuffer(gl.ARRAY_BUFFER,buffer);
   ['position','normal','color'].forEach((name,index)=>{
     const attribute=gl.getAttribLocation(program,name);gl.enableVertexAttribArray(attribute);
     gl.vertexAttribPointer(attribute,3,gl.FLOAT,false,36,index*12);
   });
   return {framing:gl.getUniformLocation(program,'framing'),turn:gl.getUniformLocation(program,'turn'),buffer};
 }
 function geometry(){
   triangles=[];base();outfit();hairstyle();accessories();
   if(pipeline){
     const data=[];
     for(const {points:[p,q,r],color} of triangles){
       const ax=q[0]-p[0],ay=q[1]-p[1],az=q[2]-p[2],bx=r[0]-p[0],by=r[1]-p[1],bz=r[2]-p[2];
       const normal=[ay*bz-az*by,az*bx-ax*bz,ax*by-ay*bx];
       const length=Math.hypot(...normal)||1;
       const hex=parseInt(color.slice(1),16),rgb=[hex>>16,(hex>>8)&255,hex&255].map(level=>level/255);
       for(const point of [p,q,r])data.push(...point,...normal.map(value=>value/length),...rgb);
     }
     gl.bindBuffer(gl.ARRAY_BUFFER,pipeline.buffer);gl.bufferData(gl.ARRAY_BUFFER,new Float32Array(data),gl.STATIC_DRAW);
   }
 }
 function shaded(hex,shade){
   const value=parseInt(hex.slice(1),16),levels=[value>>16,(value>>8)&255,value&255];
   return 'rgb('+levels.map(channel=>Math.min(255,Math.max(0,Math.round(channel*shade)))).join(',')+')';
 }
 function draw(){
   const box=canvas.getBoundingClientRect();
   if(!box.width||!box.height)return;
   const dpr=Math.min(devicePixelRatio||1,2);
   const w=Math.round(box.width*dpr),h=Math.round(box.height*dpr);
   if(canvas.width!==w)canvas.width=w;
   if(canvas.height!==h)canvas.height=h;
   const a=Math.cos(radians(yaw)),b=Math.sin(radians(yaw));
   const scale=Math.min(h*.86/4.45,w*.72/1.55)*zoom;
   if(pipeline){
     gl.viewport(0,0,w,h);gl.clearColor(0,0,0,0);gl.clear(gl.COLOR_BUFFER_BIT|gl.DEPTH_BUFFER_BIT);
     gl.uniform4f(pipeline.framing,2*scale/w,2*scale/h,focusX,focusY);gl.uniform2f(pipeline.turn,a,b);
     gl.drawArrays(gl.TRIANGLES,0,triangles.length*3);
   }else if(ctx)paintFallback(w,h,a,b,scale);
   canvas.dataset.yaw=String(Math.round(((yaw%360)+360)%360));
   canvas.dataset.feature=feature;canvas.dataset.worn=[pieces.hair,pieces.wardrobe,pieces.accessories].join(',');
   canvas.dataset.render='mesh';
   canvas.dataset.renderer=pipeline?'webgl':'canvas';
 }
 function paintFallback(w,h,a,b,scale){
   ctx.clearRect(0,0,w,h);
   const cx=w/2-focusX*scale,cy=h*.5+(2.23+focusY)*scale;
   const project=([x,y,z])=>[x*a+z*b,y, -x*b+z*a];
   if(zoom<1.2){
     ctx.save();ctx.translate(cx,cy-.08*scale);ctx.scale(1,.22);
     const shadow=ctx.createRadialGradient(0,0,0,0,0,1.03*scale);
     shadow.addColorStop(0,'#25225945');shadow.addColorStop(1,'#25225900');
     ctx.fillStyle=shadow;ctx.beginPath();ctx.arc(0,0,scale*1.04,0,TAU);ctx.fill();ctx.restore();
   }
   const world=triangles.map(entry=>{
     const coords=entry.points.map(project),[p,q,r]=coords;
     const ax=q[0]-p[0],ay=q[1]-p[1],az=q[2]-p[2],bx=r[0]-p[0],by=r[1]-p[1],bz=r[2]-p[2];
     const normal=[ay*bz-az*by,az*bx-ax*bz,ax*by-ay*bx];
     const len=Math.hypot(...normal)||1;
     const light=(-.48*normal[0]+.60*normal[1]+.64*normal[2])/len;
     const shade=.77+.29*light;
     return {coords,stroke:entry.lines,fill:shaded(entry.color,shade),
             depth:(p[2]+q[2]+r[2])/3};
   }).sort((left,right)=>left.depth-right.depth);
   for(const {coords,fill} of world){
     ctx.beginPath();
     ctx.moveTo(cx+coords[0][0]*scale,cy-coords[0][1]*scale);
     for(let i=1;i<3;i++)ctx.lineTo(cx+coords[i][0]*scale,cy-coords[i][1]*scale);
     ctx.closePath();ctx.fillStyle=fill;ctx.fill();ctx.strokeStyle=fill;ctx.lineWidth=.7;ctx.stroke();
   }
 }
 const observer=new ResizeObserver(draw);observer.observe(canvas);
 const update=()=>draw();
 function down(event){
   if(event.button!==0||feature)return;
   drag={x:event.clientX,yaw};canvas.setPointerCapture(event.pointerId);canvas.classList.add('cl-dragging');
 }
 function move(event){
   if(!drag)return;
   yaw=drag.yaw+(event.clientX-drag.x)*360/Math.max(136,canvas.clientWidth*.82);update();
 }
 function up(){drag=null;canvas.classList.remove('cl-dragging');}
 function keys(event){
   if(feature||!['ArrowLeft','ArrowRight'].includes(event.key))return;
   event.preventDefault();yaw+=event.key==='ArrowRight'?15:-15;update();
 }
 canvas.addEventListener('pointerdown',down);canvas.addEventListener('pointermove',move);
 canvas.addEventListener('pointerup',up);canvas.addEventListener('pointercancel',up);
 canvas.addEventListener('lostpointercapture',up);canvas.addEventListener('keydown',keys);
 function approach(target){
   cancelAnimationFrame(motion);
   const from={yaw,zoom,focusX,focusY};
   const start=performance.now(),duration=matchMedia('(prefers-reduced-motion: reduce)').matches?1:280;
   function step(now){
     const progress=Math.min(1,(now-start)/duration),t=1-(1-progress)**3;
     yaw=from.yaw+(target.yaw-from.yaw)*t;zoom=from.zoom+(target.zoom-from.zoom)*t;
     focusX=from.focusX+(target.focusX-from.focusX)*t;focusY=from.focusY+(target.focusY-from.focusY)*t;draw();
     if(progress<1)motion=requestAnimationFrame(step);
   }
   motion=requestAnimationFrame(step);
 }
 geometry();draw();
 return {equip(group,part){pieces={...pieces,[group]:part};geometry();draw();},
   focus(side){
     beforeCloseup??={yaw,zoom,focusX,focusY};
     feature=side;
     const face=Math.round(yaw/360)*360;
     approach({yaw:face,zoom:15,focusX:side==='left-eye'?.146:-.146,focusY:3.85-2.23});
   },
   restore(){
     if(!beforeCloseup)return;
     feature='';approach(beforeCloseup);beforeCloseup=null;
   },
   draw,close(){cancelAnimationFrame(motion);observer.disconnect();up();
     for(const [type,handler] of [['pointerdown',down],['pointermove',move],['pointerup',up],['pointercancel',up],
         ['lostpointercapture',up],['keydown',keys]])canvas.removeEventListener(type,handler);
   }};
}
'''
