"""Peak envelopes shared by the music track and original sound on timeline clips."""
STYLE = """
.oa-cut-wave{display:block;position:relative;width:100%;height:var(--oa-wave-height,18px);min-height:8px;
 overflow:hidden;color:inherit;pointer-events:none;text-align:left}
.oa-cut-wave svg{display:block;width:100%;height:100%;position:absolute;inset:0}
.oa-cut-wave .oa-wave-note{position:absolute;inset-inline-start:3px;top:0;font:9px/1.25 system-ui;
 max-width:100%;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
"""

SCRIPT = r"""
function OADirectorWaveforms(read, english=()=>false){
 const ns='http://www.w3.org/2000/svg', cache=new Map(),pending=new Map(),queue=[],watched=new Map();
 let bindings=new WeakMap(),generation=0,active=0,pruning=false;
 const label=(cn,en)=>english()?en:cn;
 function pump(){
   while(active<2&&queue.length){
     const job=queue.shift();
     if(!job.needed.some(fn=>fn())){pending.delete(job.key);job.reject(new Error('detached'));continue;}
     active++;
     Promise.resolve().then(()=>read('timeline_waveform',job.args)).then(result=>{
       if(result.sha256!==job.args.sha256||result.start_ms!==job.args.start_ms||result.end_ms!==job.args.end_ms||
         !['ready','silent','no_audio'].includes(result.state)||!Array.isArray(result.peaks)||
         result.peaks.length>job.args.bins||(result.state!=='no_audio'&&
         (!result.peaks.length||!(result.sample_rate>0&&result.samples_per_bin>0)))||
         result.peaks.some(p=>!Number.isInteger(p)||p<0||p>255))throw Error('waveform receipt');
       if(generation===job.generation){
         cache.set(job.key,result);
         if(cache.size>96)cache.delete(cache.keys().next().value);
       }
       job.resolve(result);
     }).catch(job.reject).finally(()=>{if(pending.get(job.key)===job)pending.delete(job.key);active--;pump();});
   }
 }
 function request(args,valid){
   const key=JSON.stringify(args);
   if(cache.has(key)){const r=cache.get(key);cache.delete(key);cache.set(key,r);return Promise.resolve(r);}
   let job=pending.get(key);
   if(!job){job={args,key,generation,needed:[]};job.promise=new Promise((resolve,reject)=>Object.assign(job,{resolve,reject}));
     pending.set(key,job);queue.push(job);}
   job.needed.push(valid);queueMicrotask(pump);return job.promise;
 }
 function tooltip(host,text){
   host.title=text;host.setAttribute('aria-label',text);
   const parent=host.parentElement;
   if(!parent)return;
   const prior=parent.dataset.waveTooltip||'',existing=parent.title;
   const base=prior&&existing.endsWith(prior)?existing.slice(0,-prior.length):existing;
   const suffix=(base?' · ':'')+text;parent.dataset.waveTooltip=suffix;parent.title=base+suffix;
 }
 function show(host,state,message){
   host.dataset.waveState=state;
   host.setAttribute('role','img');host.setAttribute('aria-label',message);host.title=message;
   if(state!=='loading')tooltip(host,message);
   let note=host.querySelector('.oa-wave-note');
   if(!note){note=document.createElement('span');note.className='oa-wave-note';host.append(note);}
   note.textContent=state==='ready'?'':message;
 }
 function envelope(container,spec,parts,scale){
   const gain=spec.volume/100,duration=spec.out_ms-spec.in_ms;
   function draw(level,opacity){
     const ops=[];
     for(const part of parts){
       const step=part.samples_per_bin*1000/part.sample_rate;
       for(let k=0;k<part.peaks.length;k++){
         const left=part.start_ms+k*step, right=Math.min(part.end_ms,left+step);
         const x=((left-spec.in_ms)*1000/duration).toFixed(2),w=((right-left)*1000/duration).toFixed(2);
         const h=(part.peaks[k]*47/255*level*scale).toFixed(2);
         if(+h>0)ops.push('M'+x+' '+(50-h)+'h'+w+'v'+(2*h)+'h-'+w+'z');
       }
     }
     const path=document.createElementNS(ns,'path');path.setAttribute('d',ops.join(''));
     path.setAttribute('fill','currentColor');path.setAttribute('opacity',opacity);container.append(path);
   }
   const line=document.createElementNS(ns,'line');
   for(const [k,v] of Object.entries({x1:'0',x2:'1000',y1:'50',y2:'50',stroke:'currentColor',opacity:'.32','vector-effect':'non-scaling-stroke'}))line.setAttribute(k,v);
   container.append(line);
   if(gain<1)draw(1,.22);
   if(gain>0)draw(gain,.95);
 }
 function shape(host,spec,parts){
   const svg=document.createElementNS(ns,'svg');
   svg.setAttribute('viewBox','0 0 1000 100');svg.setAttribute('preserveAspectRatio','none');svg.setAttribute('aria-hidden','true');
   const peak=parts.reduce((largest,part)=>Math.max(largest,...part.peaks),0);
   const scale=peak?Math.min(4,255/peak):1;
   envelope(svg,spec,parts,scale);
   host.querySelector('svg')?.remove();host.prepend(svg);return scale;
 }
 async function load(host,spec,stamp){
   const valid=()=>host.isConnected&&bindings.get(host)===stamp&&stamp.generation===generation;
   if(!valid())return;
   const duration=spec.out_ms-spec.in_ms, count=Math.ceil(duration/120000);
   const target=Math.max(160,Math.min(1024,Math.ceil(host.getBoundingClientRect().width)));
   const parts=[];
   try{
     for(let i=0;i<count;i++){
       if(!valid())return;
       const start=spec.in_ms+Math.floor(duration*i/count),end=spec.in_ms+Math.floor(duration*(i+1)/count);
       const args={project_id:spec.project_id,work_id:spec.work_id,sha256:spec.sha256,
         ...(spec.delivery_id?{delivery_id:spec.delivery_id}:{attempt_id:spec.attempt_id}),
         start_ms:start,end_ms:end,bins:Math.max(1,Math.min(512,Math.ceil(target*(end-start)/duration)))};
       const part=await request(args,valid);
       if(!valid())return;
       if(part.state==='no_audio'){show(host,'no_audio',label('无音轨','No audio track'));return;}
       parts.push(part);
     }
     const scale=shape(host,spec,parts);
     const silent=parts.every(p=>p.state==='silent'),muted=spec.volume===0;
     host.dataset.sourceSilent=String(silent);host.dataset.volume=String(spec.volume);
     const level=spec.clipSound?label('镜头原声 ','Clip audio ')+spec.volume+'%':
       label('音频波形，音量 '+spec.volume+'%','Audio waveform, volume '+spec.volume+'%');
     const msg=silent?(spec.clipSound?label('镜头原声无声','Silent clip audio'):label('源音频为静音','Silent source')):
       muted&&!spec.clipSound?label('已静音','Muted'):level;
     show(host,silent?'silent':muted?'muted':'ready',msg);
     const mixing=spec.clipSound&&muted?label(' · 下方音轨独立混音',' · Other tracks are mixed separately'):'';
     if(!silent||mixing)tooltip(host,msg+mixing+(silent?'':label(' · 波形显示 ×',' · Waveform display ×')+scale.toFixed(1)));
   }catch(err){if(valid())show(host,'error',label('波形暂不可用','Waveform unavailable'));}
 }
 const observer=typeof IntersectionObserver==='function'?new IntersectionObserver(entries=>{
   for(const e of entries)if(e.isIntersecting){
     const entry=watched.get(e.target);observer.unobserve(e.target);watched.delete(e.target);if(entry)load(e.target,...entry);
   }
 },{rootMargin:'240px'}):null;
 function attach(host,spec){
   if(!host)return;
   const key=JSON.stringify(spec);
   if(bindings.get(host)?.key===key&&host.childNodes.length)return;
   host.replaceChildren();host.classList.add('oa-cut-wave');
   delete host.dataset.sourceSilent;delete host.dataset.volume;
   const stamp={key,generation};bindings.set(host,stamp);
   if(!(spec.out_ms>spec.in_ms)){show(host,'error',label('无有效音频选区','Empty audio range'));return;}
   show(host,'loading',label('读取波形','Reading waveform'));
   if(observer){
     watched.set(host,[spec,stamp]);observer.observe(host);
     if(!pruning){pruning=true;queueMicrotask(()=>{pruning=false;
       for(const el of watched.keys())if(!el.isConnected){observer.unobserve(el);watched.delete(el);}
     });}
   }else queueMicrotask(()=>load(host,spec,stamp));
 }
 // Tile coordinates stay in source milliseconds; cropping changes the SVG viewport only.
 function region(host,spec,sourceEnd,msPerPixel){
   const svg=document.createElementNS(ns,'svg'),tiles=new Map(),epoch=generation;
   const tileMs=Math.max(512,Math.min(120000,2**Math.round(Math.log2(Math.max(1,msPerPixel)*384))));
   const bins=Math.max(1,Math.min(512,Math.round(tileMs/Math.max(.1,msPerPixel))));
   let first=0,last=0;
   svg.setAttribute('preserveAspectRatio','none');svg.setAttribute('aria-hidden','true');
   host.classList.add('oa-cut-wave');host.replaceChildren(svg);
   function status(){
     const visible=[...tiles.values()];
     const pending=visible.some(t=>!t.state),error=visible.some(t=>t.state==='error');
     const state=error?'error':pending?'loading':visible.every(t=>t.state==='no_audio')?'no_audio':
       visible.every(t=>t.state==='silent')?'silent':spec.volume===0?'muted':'ready';
     if(host.dataset.waveState===state)return;
     const names={loading:label('读取波形','Reading waveform'),error:label('波形暂不可用','Waveform unavailable'),
       ready:label('音频波形','Audio waveform'),silent:label('源音频为静音','Silent source'),
       muted:label('已静音','Muted'),no_audio:label('无音轨','No audio track')};
     show(host,state,names[state]);host.dataset.sourceSilent=String(state==='silent');host.dataset.volume=String(spec.volume);
   }
   function fetchTile(start){
     const end=Math.min(sourceEnd,start+tileMs),part={node:document.createElementNS(ns,'g')};tiles.set(start,part);
     const valid=()=>epoch===generation&&host.isConnected&&tiles.get(start)===part;
     const args={project_id:spec.project_id,work_id:spec.work_id,sha256:spec.sha256,attempt_id:spec.attempt_id,
       start_ms:start,end_ms:end,bins:Math.max(1,Math.ceil(bins*(end-start)/tileMs))};
     void request(args,valid).then(data=>{
       if(!valid())return;
       part.state=data.state;
       part.node.setAttribute('transform','translate('+start+' 0) scale('+((end-start)/1000)+' 1)');
       if(data.state!=='no_audio')envelope(part.node,{in_ms:start,out_ms:end,volume:spec.volume},[data],1);
       svg.append(part.node);status();
     }).catch(()=>{if(valid()){part.state='error';status();}});
   }
   return function view(start,end){
     if(end<=start)return;
     svg.setAttribute('viewBox',start+' 0 '+(end-start)+' 100');
     const from=Math.floor(start/tileMs)*tileMs,until=Math.ceil(end/tileMs)*tileMs;
     if(first===from&&last===until)return;
     first=from;last=until;
     for(const [t,part] of tiles)if(t<from||t>=until){part.node.remove();tiles.delete(t);}
     for(let t=from;t<until&&t<sourceEnd;t+=tileMs)if(!tiles.has(t))fetchTile(t);
     status();
   };
 }
 function reset(){
   generation++;bindings=new WeakMap();cache.clear();pending.clear();
   for(const job of queue.splice(0))job.reject(Error('detached'));
   observer?.disconnect();watched.clear();
 }
 return {attach,region,reset,request};
}
"""
