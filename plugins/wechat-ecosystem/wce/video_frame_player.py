"""Shared in-panel visual playback over decoded image frames."""

STYLE = '''
.oa-frame-player{display:grid;gap:6px;min-width:0}
.oa-frame-player img{display:block;width:100%;height:100%;object-fit:contain}
.oa-frame-player .oa-frame-screen{aspect-ratio:16/9;overflow:hidden;background:#161719;border-radius:10px}
.oa-frame-player .oa-frame-controls{display:flex;align-items:center;gap:8px}
.oa-frame-player .oa-frame-controls button{min-height:30px;flex:none;padding:3px 8px;font-size:12px}
.oa-frame-player .oa-frame-controls input{flex:1;min-width:0;accent-color:var(--accent)}
.oa-frame-player .oa-frame-controls output{font-size:12px;font-variant-numeric:tabular-nums}
.oa-inline-video-player{display:grid;gap:5px;min-width:0}
.oa-inline-video-player video,.oa-video-poster{display:block;width:100%;aspect-ratio:16/9;object-fit:contain;background:#161719;border-radius:7px}
.oa-inline-video-player p{font-size:12px;margin:0;color:var(--muted)}
#homeIntro{width:100%;min-width:0;margin:20px 0 0}
#homeIntro h2{font-size:15px;margin:0}
.oa-home-intro-heading{display:flex;align-items:center;justify-content:space-between;gap:8px;margin-bottom:8px}
#homeIntroToggle{min-height:32px;padding:3px 9px}
'''

SCRIPT = r'''
function OAStudioPreviewSound(control){
 const storageKey='openahoy.jiusera.preview-sound',clients=new Set();
 const nativeMedia=new Map();
 let enabled=false,selected=null,context=null,master=null,meter=null,samples=null,level=null;
 function output(ctx){
   if(!master){
     master=ctx.createGain();master.gain.value=level??1;master.connect(ctx.destination);
   }
   return master;
 }
 function setLevel(value){
   if(value!==null&&!Number.isFinite(value))return;
   const target=value===null?null:Math.max(0,Math.min(1,value));
   if(target===level)return;
   if(level===null)for(const media of nativeMedia.keys())nativeMedia.set(media,media.volume);
   level=target;
   if(master)master.gain.setTargetAtTime(level??1,context.currentTime,.012);
   for(const [media,original] of nativeMedia)media.volume=level??original;
 }
 function peakDb(){
   if(!master||level===null||context.state!=='running')return -60;
   if(!meter){meter=context.createAnalyser();meter.fftSize=256;samples=new Float32Array(meter.fftSize);master.connect(meter);}
   meter.getFloatTimeDomainData(samples);
   let peak=0;for(const sample of samples)peak=Math.max(peak,Math.abs(sample));
   return Math.max(-60,Math.min(0,20*Math.log10(peak)));
 }
 try{enabled=localStorage.getItem(storageKey)==='on';}catch(_){}
 function paint(){
   control.setAttribute('aria-pressed',String(enabled));
   OAUI.set(control,enabled?'声音开':'声音关');
   for(const update of clients)if(update!==selected)update(false,enabled);
   selected?.(enabled&&!document.hidden,enabled);
 }
 function unlock(event){
   if(!enabled||!event?.isTrusted||!globalThis.AudioContext)return;
   try{
     if(!context){context=new AudioContext();context.addEventListener('statechange',paint);}
     if(context.state!=='running')void context.resume().then(paint,paint);
   }catch(_){}
 }
 function register(update){
   clients.add(update);update(false,enabled);
   return {
     claim(){if(selected!==update){selected=update;paint();}},
     release(){if(selected===update){selected=null;paint();}},
     close(){clients.delete(update);if(selected===update){selected=null;paint();}},
   };
 }
 function bindMedia(video,change=()=>{}){
   nativeMedia.set(video,video.volume);
   if(level!==null)video.volume=level;
   let allowed=false,preference=false,seeking=false;
   function refresh(){
     const audible=allowed&&!seeking;
     video.muted=!audible;
     change(audible,preference);
   }
   const lease=register((grant,enabled)=>{allowed=grant;preference=enabled;refresh();});
   const lockMute=()=>{if((!allowed||seeking)&&!video.muted)video.muted=true;};
   const events={play:lease.claim,pause:lease.release,ended:lease.release,
     seeking:()=>{seeking=true;refresh();},seeked:()=>{seeking=false;refresh();},
     volumechange:lockMute,click:unlock};
   for(const [name,action] of Object.entries(events))video.addEventListener(name,action);
   return ()=>{
     for(const [name,action] of Object.entries(events))video.removeEventListener(name,action);
     video.muted=true;if(level!==null)video.volume=nativeMedia.get(video)??1;nativeMedia.delete(video);lease.close();
   };
 }
 function toggle(event){
   if(!event.isTrusted)return;
   enabled=!enabled;
   try{localStorage.setItem(storageKey,enabled?'on':'off');}catch(_){}
   unlock(event);paint();
 }
 control.onclick=toggle;
 const visibility=()=>paint();document.addEventListener('visibilitychange',visibility);
 paint();
 return {register,bindMedia,unlock,toggle,output,setLevel,peakDb,context:()=>context,close(){
   document.removeEventListener('visibilitychange',visibility);
   selected=null;paint();clients.clear();setLevel(null);nativeMedia.clear();meter?.disconnect();master?.disconnect();
   if(context&&context.state!=='closed')void context.close().catch(()=>{});
 }};
}

function OAStudioFrameSound(sound,original,tracks,announce){
 let allowed=false,enabled=false,running=false,closed=false,unavailable=!original;
 let decoded=null,decoding=false,source=null,last=null,anchor=0;
 const lease=sound.register((permit,preference)=>{allowed=permit;enabled=preference;update();});
 function stop(){
   if(!source)return;
   const current=source;source=null;
   try{current.stop();}catch(_){}
   current.disconnect();
 }
 function update(){
   if(closed)return;
   if(!tracks){announce('silent');return;}
   if(!enabled){stop();announce('muted');return;}
   if(unavailable){stop();announce('unavailable');return;}
   if(!running||!allowed){stop();announce('paused');return;}
   const context=sound.context();
   if(context?.state!=='running'){stop();announce('activation');return;}
   if(!decoded){
     announce('loading');
     if(!decoding){
       decoding=true;
       void original.arrayBuffer().then(bytes=>context.decodeAudioData(bytes)).then(buffer=>{
         if(closed)return;
         if(!buffer.numberOfChannels||!buffer.length)throw Error('VIDEO_AUDIO_UNAVAILABLE');
         decoded=buffer;update();
       }).catch(()=>{unavailable=true;update();});
     }
     return;
   }
   if(!last||performance.now()-last.at>300||last.seconds>=decoded.duration){
     stop();announce('paused');return;
   }
   const now=context.currentTime;
   if(!source||Math.abs(now-anchor-last.seconds)>.19){
     stop();
     const next=context.createBufferSource();next.buffer=decoded;
     next.connect(sound.output?.(context)??context.destination);source=next;anchor=now-last.seconds;
     next.onended=()=>{if(source===next){source=null;announce('paused');}next.disconnect();};
     next.start(0,last.seconds);
   }
   // A delayed frame can never leave its audio running on a separate timeline.
   source.stop(now+.29);
   announce('playing');
 }
 return {
   play(){running=true;lease.claim();update();},
   frame(seconds){last={seconds,at:performance.now()};if(running)update();},
   silence(willResume){last=null;running=willResume;if(!willResume)lease.release();update();},
   close(){closed=true;stop();lease.close();decoded=null;},
 };
}

function OAFramePlayer(root, call, seconds, {poster='', showControls=true, loop=false, ended=()=>{}, failed=()=>{}, seeked=()=>{}, transport=null}={}){
 const rate=8, count=Math.ceil(seconds*rate), frames=new Map(), pending=new Map();
 const screen=document.createElement('div'), image=document.createElement('img');
 screen.className='oa-frame-screen';image.alt='';if(poster)image.src=poster;screen.append(image);root.append(screen);
 let toggle,seek,clock;
 if(showControls){
   const controls=document.createElement('div');controls.className='oa-frame-controls';
   toggle=document.createElement('button');seek=document.createElement('input');clock=document.createElement('output');
   toggle.type='button';seek.type='range';seek.min='0';seek.max=String(count-1);seek.step='1';
   OAUI.attr(seek,'aria-label','播放进度');controls.append(toggle,seek,clock);root.append(controls);
   toggle.onclick=event=>{if(running)pause();else{transport?.gesture(event);play();}};
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
   running=false;revision++;clearTimeout(timer);transport?.silence(false);update();
 }
 async function show(frame,token){
   try{
     await load(frame);
     if(disposed||token!==revision)return;
     const url=frames.get(frame);
     const decoded=new Image();decoded.src=url;await decoded.decode();
     if(disposed||token!==revision)return;
     image.src=url;index=frame;transport?.frame(index/rate);update();
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
   nextFrameAt=performance.now();running=true;transport?.play();update();void show(index,++revision);
 }
 function jump(frame,notify=true){
   clearTimeout(timer);transport?.silence(running);nextFrameAt=performance.now();index=Math.min(count-1,Math.max(0,frame));update();
   void show(index,++revision);if(notify)seeked(index/rate);
 }
 update();
 return {play,pause,jump,isPlaying:()=>running,first(){void show(0,revision);},close(){pause();disposed=true;root.replaceChildren();}};
}

function OAVideoPreview(root,asset,{chunk,frames,run=false,lazy=false,poster='',onVideo=()=>{},sound=null,statusTarget=null}){
 const surface=document.createElement('div'),status=document.createElement('p'),load=document.createElement('button');
 delete root.dataset.previewMode;delete root.dataset.previewFailure;delete root.dataset.soundState;
 root.classList.add('oa-inline-video-player');surface.className='oa-frame-player';status.setAttribute('role','status');
 load.type='button';OAUI.set(load,'播放');
 if(statusTarget){
   surface.tabIndex=0;surface.setAttribute('role','button');OAUI.attr(surface,'aria-label','播放');
   root.replaceChildren(surface);statusTarget.replaceChildren(status);
 }else root.replaceChildren(surface,load,status);
 let closed=false,native=null,url='',visual=null,started=false,firstBatch,observer;
 let original=null,releaseNative=null,frameSound=null,engaged=false,wantsPlay=false;
 function audioState(state,message=''){
   if(root.dataset.soundState!==state){root.dataset.soundState=state;OAUI.set(status,message);}
 }
 function disposeNative(){
   releaseNative?.();releaseNative=null;
   if(native){const video=native;native=null;video.pause();video.removeAttribute('src');video.load();}
   if(url){URL.revokeObjectURL(url);url='';}
 }
 function fallback(reason,play,seconds=0){
   if(closed||visual)return;
   root.dataset.previewMode='frames';root.dataset.previewFailure=reason;
   disposeNative();load.hidden=true;surface.replaceChildren();
   const labels={silent:'原片无音轨',muted:'声音已关闭',unavailable:'当前环境无法解码原片声音',
     paused:'画面预览',activation:'点击播放启用声音',loading:'正在读取音轨…',playing:'画面预览 · 有声'};
   if(sound)frameSound=OAStudioFrameSound(sound,original,asset.audio_tracks,
     state=>audioState(state,labels[state]));
   else OAUI.set(status,asset.audio_tracks?'预览静音，原文件有声':'画面预览');
   visual=OAFramePlayer(surface,start=>start===0&&firstBatch?firstBatch:frames(start),asset.seconds,{
     poster,showControls:!statusTarget,ended:()=>sourceState(false),transport:frameSound&&{...frameSound,gesture:sound.unlock},failed:()=>{
       sourceState(false);OAUI.set(status,reason==='read'?'无法读取原文件。':'当前环境无法播放原文件。');
     },
   });
   if(seconds>0)visual.jump(Math.floor(seconds*8));
   if(play){visual.play();sourceState(true);}else if(!seconds)visual.first();
 }
 async function open(play){
   if(closed||started)return;
   started=true;wantsPlay=play;load.hidden=true;OAUI.set(status,'正在读取原文件…');
   try{
     let offset=0;
     const parts=[];
     while(offset<asset.bytes&&!closed){
       const part=await chunk(offset);
       if(closed)return;
       if(part.offset!==offset||part.total!==asset.bytes||part.sha256!==asset.sha256)throw Error('VIDEO_ASSET_CHANGED');
       const bytes=Uint8Array.from(atob(part.bytes),character=>character.charCodeAt(0));
       if(!bytes.length||offset+bytes.length>asset.bytes)throw Error('VIDEO_ASSET_CHANGED');
       offset+=bytes.length;parts.push(bytes);
     }
     if(closed)return;
     const video=document.createElement('video');native=video;
     video.controls=!statusTarget;video.controlsList='nodownload';video.preload='metadata';video.playsInline=true;
     if(sound)releaseNative=sound.bindMedia(video,(allowed,enabled)=>{
       if(root.dataset.previewMode!=='native')return;
       const state=asset.audio_tracks?(allowed?'playing':enabled?'paused':'muted'):'silent';
       audioState(state,state==='silent'?'原片无音轨':'');
     });
     if(poster)video.poster=poster;
     let running=play;
     video.addEventListener('playing',()=>{if(native===video){running=true;sourceState(true);}});
     video.addEventListener('pause',()=>{if(native===video){running=false;sourceState(false);}});
     video.addEventListener('error',()=>{
       if(native!==video)return;
       const reason=video.error?.code===3?'decode':'media-source';
       fallback(reason,statusTarget?wantsPlay:running,video.currentTime);
     },{once:true});
     video.addEventListener('loadedmetadata',()=>{
       if(native!==video||closed)return;
       root.dataset.previewMode='native';OAUI.set(status,'');
       if(sound&&!asset.audio_tracks)audioState('silent','原片无音轨');
       if(wantsPlay)void video.play().catch(()=>{});
     },{once:true});
     original=new Blob(parts,{type:'video/mp4'});url=URL.createObjectURL(original);
     surface.replaceChildren(video);video.src=url;onVideo(video);
   }catch(_){fallback('read',wantsPlay);}
 }
 function sourceState(playing){
   if(!statusTarget)return;
   OAUI.attr(surface,'aria-label',playing?'暂停':'播放');
   surface.setAttribute('aria-pressed',String(playing));
 }
 function toggleSource(event){
   sound?.unlock(event);
   engaged=true;
   if(started&&!visual&&(!native||native.readyState===0)){
     wantsPlay=!wantsPlay;sourceState(wantsPlay);return;
   }
   if(native){wantsPlay=native.paused;if(wantsPlay)void native.play().catch(()=>{});else native.pause();}
   else if(visual){if(visual.isPlaying())visual.pause();else visual.play();sourceState(visual.isPlaying());}
   else {sourceState(true);void open(true);}
 }
 if(statusTarget){
   surface.onclick=toggleSource;
   surface.onkeydown=event=>{
     if(event.key!=='Enter'&&event.key!==' ')return;
     event.preventDefault();if(!event.repeat)toggleSource(event);
   };
 }
 load.onclick=event=>{sound?.unlock(event);void open(true);};
 if(lazy){
   const image=document.createElement('img');image.alt='';image.className='oa-video-poster';
   surface.append(image);
   if(poster)image.src=poster;
   else {
     const loadPoster=()=>{
       observer?.disconnect();
       if(closed)return;
       firstBatch=frames(0).catch(()=>{firstBatch=null;});
       void firstBatch.then(batch=>{
         const data=batch?.frames?.[0];
         if(closed||typeof data!=='string'||data.length>128000||!data.startsWith('/9j/')||!/^[A-Za-z0-9+/=]+$/.test(data))return;
         poster='data:image/jpeg;base64,'+data;
         if(image.isConnected)image.src=poster;
         if(native)native.poster=poster;
       });
     };
     if(typeof IntersectionObserver==='function'){
       observer=new IntersectionObserver(entries=>{if(entries.some(entry=>entry.isIntersecting))loadPoster();});
       observer.observe(image);
     }else loadPoster();
   }
 }else void open(run);
 return {toggle:toggleSource,engaged:()=>engaged,close(){
   closed=true;status.remove();observer?.disconnect();visual?.close();frameSound?.close();disposeNative();original=null;root.replaceChildren();
 }};
}
'''
