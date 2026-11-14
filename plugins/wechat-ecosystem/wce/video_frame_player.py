"""Shared in-panel visual playback over decoded image frames."""

STYLE = '''
.oa-frame-player{display:grid;gap:6px;min-width:0}
.oa-frame-player img{display:block;width:100%;height:100%;object-fit:contain}
.oa-frame-player .oa-frame-screen{aspect-ratio:16/9;overflow:hidden;background:#161719;border-radius:10px}
.oa-frame-player .oa-frame-controls{display:flex;align-items:center;gap:8px}
.oa-frame-player .oa-frame-controls button{min-height:30px;flex:none;padding:3px 8px;font-size:12px}
.oa-frame-player .oa-frame-controls input{flex:1;min-width:0;accent-color:var(--accent)}
.oa-frame-player .oa-frame-controls output{font-size:12px;font-variant-numeric:tabular-nums}
#homeIntro{width:100%;min-width:0;margin:20px 0 0}
#homeIntro h2{font-size:15px;margin:0 0 8px}
'''

SCRIPT = r'''
function OAFramePlayer(root, call, seconds, {poster='', showControls=true, loop=false, ended=()=>{}, failed=()=>{}, seeked=()=>{}}={}){
 const rate=8, count=Math.ceil(seconds*rate), frames=new Map(), pending=new Map();
 const screen=document.createElement('div'), image=document.createElement('img');
 screen.className='oa-frame-screen';image.alt='';if(poster)image.src=poster;screen.append(image);root.append(screen);
 let toggle,seek,clock;
 if(showControls){
   const controls=document.createElement('div');controls.className='oa-frame-controls';
   toggle=document.createElement('button');seek=document.createElement('input');clock=document.createElement('output');
   toggle.type='button';seek.type='range';seek.min='0';seek.max=String(count-1);seek.step='1';
   OAUI.attr(seek,'aria-label','播放进度');controls.append(toggle,seek,clock);root.append(controls);
   toggle.onclick=()=>{if(running)pause();else play();};
   seek.oninput=()=>jump(Number(seek.value));
 }
 let index=0, revision=0, running=false, disposed=false, timer;
 let nextFrameAt=0;
 const time=value=>Math.floor(value/60)+':'+String(Math.floor(value%60)).padStart(2,'0');
 function update(){
   if(!showControls)return;
   OAUI.set(toggle,running?'暂停':'播放');
   seek.value=String(index);
   clock.textContent=time(index/rate)+' / '+time(seconds);
 }
 function load(frame){
   const start=frame-frame%4;
   if(frames.has(frame))return Promise.resolve();
   if(pending.has(start))return pending.get(start);
   const request=(async()=>{
     const batch=await call(start);
     if(disposed)return;
     if(batch.start!==start||!Array.isArray(batch.frames)||batch.frames.length!==Math.min(4,count-start))
       throw new Error('VIDEO_PREVIEW_UNAVAILABLE');
     for(const [offset,data] of batch.frames.entries()){
       if(typeof data!=='string'||data.length>128000||!/^\/9j\/[A-Za-z0-9+/=]+$/.test(data))
         throw new Error('VIDEO_PREVIEW_UNAVAILABLE');
       frames.set(start+offset,'data:image/jpeg;base64,'+data);
     }
   })().finally(()=>pending.delete(start));
   pending.set(start,request);
   return request;
 }
 function pause(){
   running=false;revision++;clearTimeout(timer);update();
 }
 async function show(frame,token){
   try{
     await load(frame);
     if(disposed||token!==revision)return;
     const url=frames.get(frame);
     const decoded=new Image();decoded.src=url;await decoded.decode();
     if(disposed||token!==revision)return;
     image.src=url;index=frame;update();
     if(!loop)for(const cached of frames.keys())if(Math.abs(cached-index)>24)frames.delete(cached);
     if(running){
       if(frame+4<count)void load(frame+4).catch(()=>{});
       nextFrameAt=Math.max(nextFrameAt+1000/rate,performance.now());
       timer=setTimeout(()=>{
         if(!loop&&index===count-1){pause();ended();}
         else void show((index+1)%count,token);
       },Math.max(0,nextFrameAt-performance.now()));
     }
   }catch(_){if(!disposed&&token===revision){pause();failed();}}
 }
 function play(){
   if(disposed||running)return;
   if(index===count-1)index=0;
   nextFrameAt=performance.now();running=true;update();void show(index,++revision);
 }
 function jump(frame,notify=true){
   clearTimeout(timer);nextFrameAt=performance.now();index=Math.min(count-1,Math.max(0,frame));update();
   void show(index,++revision);if(notify)seeked(index/rate);
 }
 update();
 return {play,pause,jump,first(){void show(0,revision);},close(){pause();disposed=true;root.replaceChildren();}};
}
'''
