"""The embedded, read-only media workspace."""
from .audio_workspace_ui import BRAND

HTML = '''
<section id="mediaMonitor">
 <header class="mm-toolbar">
  <h1 id="monitorTitle" tabindex="-1">媒体工坊</h1>
  <button id="monitorRefresh" type="button">刷新</button><button id="monitorSunoJump" type="button" hidden>音频供应商</button><button id="monitorSettings" type="button">供应商设置</button>
 </header>
 <div class="mm-toolbar">
  <nav id="monitorFilters" aria-label="媒体类型"><button type="button" data-kind="all">全部</button><button type="button" data-kind="video">视频</button><button type="button" data-kind="audio">音频</button><button type="button" data-kind="gif">动图</button></nav>
  <input id="monitorSearch" type="search" placeholder="搜索资产" aria-label="搜索资产">
 </div>
 <div class="mm-toolbar mm-status"><nav id="monitorStates" aria-label="按状态筛选"></nav><span id="monitorRead" role="status"></span></div>
 <div class="mm-columns">
  <section id="monitorList" aria-label="任务与资产" tabindex="-1"></section>
  <section id="monitorDetail" aria-label="选中详情" tabindex="-1">
   <div class="mm-toolbar mm-return"><button id="monitorListBack" type="button">返回列表</button><button id="monitorRelationBack" type="button" hidden>返回上一项</button></div>
   <div id="monitorBody"></div>
   <div id="monitorSuno" hidden></div>
  </section>
 </div>
</section>
<section id="monitorProviders" hidden>
 <header class="mm-toolbar"><h1 id="monitorSettingsTitle" tabindex="-1">供应商设置</h1><button id="monitorSettingsBack" type="button">返回媒体工坊</button></header>
 <nav id="monitorProviderTabs" class="mm-toolbar"><button id="monitorVideoProvider" type="button">视频</button><button id="monitorGifProvider" type="button">动图</button><button id="monitorAudioProvider" type="button">音频</button></nav>
 <div id="monitorVideoSettings"></div><div id="monitorGifSettings" hidden></div><div id="monitorAudioSettings" hidden></div>
</section>
'''

STYLE = '''
.oa-management [id^="monitor"]{min-width:0}
#mediaMonitor,#monitorProviders{display:flex;min-height:0;flex:1;flex-direction:column;gap:8px;font-size:13px}
#monitorProviders{overflow:auto;padding:2px 4px}
#mediaStudio h1{font-size:21px;line-height:1.2;margin:0;letter-spacing:-.02em}
.mm-toolbar{display:flex;align-items:center;gap:6px;flex-wrap:wrap}
.mm-toolbar>h1{margin-inline-end:auto!important}
.mm-toolbar nav{display:flex;gap:3px;flex-wrap:wrap}
#mediaStudio button:not(.mm-row),#monitorSearch,#mediaMonitor select{min-height:32px;padding:3px 8px;font-size:12px;max-width:100%}
#mediaMonitor :is(select,input){color:var(--ink);background:var(--surface);border:1px solid var(--line);border-radius:7px}
#monitorSearch{flex:1 1 130px;max-width:260px;margin-inline-start:auto;min-width:0}
#mediaMonitor button[aria-pressed=true],#monitorProviderTabs button[aria-pressed=true]{color:var(--accent);background:var(--tint);border-color:transparent}
#monitorRead,.mm-muted{font-size:12px;color:var(--muted);overflow-wrap:anywhere}
#monitorRead{margin-inline-start:auto}
.mm-status button{font-variant-numeric:tabular-nums}
.mm-columns{display:grid;grid-template-columns:minmax(228px,36%) minmax(0,1fr);min-height:0;flex:1;gap:10px}
#monitorList,#monitorDetail{overflow:auto;min-height:0;border:1px solid var(--line);border-radius:10px;background:var(--surface)}
#monitorList{padding:3px}
#monitorDetail{padding:9px 10px}
#mediaMonitor .mm-row{min-height:49px;width:100%;display:grid;grid-template-columns:48px minmax(0,1fr) auto;align-items:center;gap:7px;border:0;border-radius:6px;box-shadow:none;padding:4px 5px;text-align:start;background:transparent}
#mediaMonitor .mm-row+.mm-row{border-top:1px solid var(--line)}
#mediaMonitor .mm-row:hover{background:var(--oa-fill,var(--soft))}
#mediaMonitor .mm-row[aria-current=true]{background:var(--tint);color:var(--accent)}
.mm-thumb{width:48px;height:33px;border-radius:5px;overflow:hidden;display:grid;place-items:center;background:var(--oa-fill,var(--soft));color:var(--muted);font-size:15px}
.mm-thumb img{width:100%;height:100%;object-fit:cover}
.mm-text{display:grid;min-width:0;gap:1px}
.mm-text>*{white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.mm-text small{font-size:11px;color:var(--muted)}
.mm-badge{display:inline-flex;align-items:center;border-radius:5px;padding:1px 4px;font-size:11px;color:var(--muted);white-space:nowrap}
.mm-badge[data-group=complete]{background:#338a4d20;color:#23713b}
.mm-badge[data-group=failed]{background:#d7526420;color:#a63a4d}
.mm-badge[data-group=running]{background:#4489e125;color:#325e9d}
.mm-badge[data-group=pending]{background:#cb8c2726;color:#80570c}
[data-color-scheme=dark] .mm-badge[data-group=complete]{color:#8cdaa5}
[data-color-scheme=dark] .mm-badge[data-group=failed]{color:#ffabb6}
[data-color-scheme=dark] .mm-badge[data-group=running]{color:#a2c7ff}
[data-color-scheme=dark] .mm-badge[data-group=pending]{color:#f5c575}
#monitorBody{display:grid;gap:7px}
#monitorBody p,#monitorBody h2,#monitorBody h3{margin:0}
#monitorBody h2{font-size:15px;overflow-wrap:anywhere}
#monitorBody h3{font-size:12px}
#monitorBody .mm-toolbar select{flex:1 1 130px;width:auto;min-width:0;margin:0}
.mm-heading{display:grid;grid-template-columns:minmax(0,1fr) auto;align-items:start;gap:4px}
.mm-preview{display:grid;gap:7px}
.mm-preview[data-compare=true]{grid-template-columns:repeat(2,minmax(0,1fr))}
.mm-preview video,.mm-preview canvas{display:block;max-width:100%;width:100%;height:min(34dvh,300px);background:#101013;object-fit:contain;border-radius:8px}
.mm-preview audio{width:100%;height:36px;margin-block:6px}
.mm-relation{display:flex;align-items:center;gap:6px;flex-wrap:wrap;padding:3px 0}
.mm-relation img{width:16px;height:16px;border-radius:4px}
.mm-relation .mm-text{flex:1 1 95px}
.mm-links,.mm-facts{border-top:1px solid var(--line);padding-top:5px}
.mm-facts summary{cursor:pointer;min-height:32px;padding-block:5px}
.mm-facts>p{margin-block-end:5px!important}
.mm-return{display:flex;margin-bottom:5px}
#monitorListBack{display:none}
#monitorSuno{margin-top:8px}
#monitorSuno .oa-audio-card{padding:7px}
#monitorSuno .oa-audio-local{display:none}
#monitorSuno summary{min-height:32px;padding-block:5px;cursor:pointer}
#monitorSuno .oa-audio-heading,#monitorSuno .oa-audio-monitor,#monitorSuno .oa-audio-section-heading,
#monitorSuno :is(#audioActionNotice,#audioList,#audioEmpty,#audioTitle,#audioEmptyPreview,#audioNotice){display:none!important}
#monitorSuno{container-type:inline-size}
#monitorSuno :is(.oa-audio-dashboard,.oa-audio-workspace){display:grid;grid-template-columns:minmax(0,1fr);gap:6px}
@container (min-width:540px){#monitorSuno .oa-audio-dashboard{grid-template-columns:repeat(2,minmax(0,1fr))}}
@container (width < 540px){
 #monitorSuno .oa-audio-provider-nav{display:flex}
 #monitorSuno :is([data-provider-view=suno] #audioAceCard,[data-provider-view=ace] #audioSunoCard){display:none}
}
#monitorSuno .oa-audio-preview:has(#sunoPlayer[hidden]):has(#sunoPlaybackState:empty){display:none}
@media(max-width:690px){
 .mm-columns{display:block}
 #monitorList,#monitorDetail{max-height:100%;height:100%}
 #mediaMonitor[data-detail=true] #monitorList,#mediaMonitor:not([data-detail=true]) #monitorDetail{display:none}
 #monitorListBack{display:inline-flex}
 #mediaStudio{overflow:hidden}
 #monitorSearch{max-width:none}
 .mm-preview video,.mm-preview canvas{height:min(29dvh,220px)}
}
@media(prefers-reduced-motion:reduce){#mediaStudio *{transition:none!important}}
'''

SCRIPT = r'''
function OAMediaMonitor(invoke, sendChat, activateSettings, activateSuno, canvas=null){
 const $=id=>document.getElementById(id);
 const root=$('mediaMonitor'),list=$('monitorList'),detail=$('monitorDetail'),body=$('monitorBody');
 const filters=$('monitorFilters'),states=$('monitorStates'),search=$('monitorSearch');
 const narrow=matchMedia('(max-width:690px)');
 let routedTarget=null;
 const medium={video:'视频',audio:'音频',gif:'动图'};
 const stateName={complete:'已完成',failed:'失败',running:'进行中',pending:'待核实'};
 const stageName={ASSET_READY:'成片可用',UNAVAILABLE:'源文件不可用',SUBMITTED:'已提交',
   PROCESSING:'处理中',QUEUED:'排队中',RUNNING:'处理中',SUBMIT_UNKNOWN:'提交结果待核实',SAVE_PENDING:'生成完成待保存',
   RESULT_RECEIVED:'已收到结果',FAILED:'执行失败',SUBMIT_REJECTED:'提交被拒绝',NOT_SENT:'未提交',
   CANCELLED:'已取消',EXPIRED:'已过期'};
 const ops={video:['playback','export'],audio:['audio_chunk','audio_export'],gif:['gif_chunk','gif_export']};
 const mediaMime={video:'video/mp4',gif:'image/gif'};
 const usageLabels={completion_tokens:'生成 Token',total_tokens:'总 Token',prompt_tokens:'提示词 Token',
   total_seconds:'计量总秒数',input_seconds:'输入秒数',output_seconds:'输出秒数',
   input_audio_seconds:'输入音频秒数',input_image_count:'输入图数',web_search:'搜索次数'};
 let active=false,loading=false,readSequence=0,playerEpoch=0,kind='all',state='',rows=[],unavailable=[],readAt=0;
 let selected='',compare='',loaded='',history=[],releases=[];
 const thumbnails=new Map();
 const key=row=>JSON.stringify([row.family,row.project,row.attempt]);
 const fingerprint=row=>key(row)+':'+row.asset.sha256;
 const scope=row=>({project_id:row.project,[row.family==='audio'?'attempt_id':'generation_attempt_id']:row.attempt});
 const fmt=value=>new Intl.NumberFormat(document.documentElement.lang).format(value);
 const stamp=value=>new Date(value*1000).toLocaleString(document.documentElement.lang,{month:'short',day:'numeric',hour:'2-digit',minute:'2-digit'});
 const title=row=>[row.project_label,row.account_label,row.title].filter(Boolean).join(' · ');
 const message=OAUI.message;
 const playable=row=>row?.state==='ASSET_READY'&&Number.isSafeInteger(row.asset?.bytes)&&row.asset.bytes>0&&!!row.asset.sha256;
 const byKey=id=>rows.find(row=>key(row)===id);
 function element(tag,cls){const node=document.createElement(tag);if(cls)node.className=cls;return node;}
 function label(tag,name,...values){const node=element(tag);OAUI.set(node,name,...values);return node;}
 function button(name,action){const node=label('button',name);node.type='button';node.onclick=action;return node;}
 function raw(tag,text,cls){const node=element(tag,cls);OAUI.raw(node,text);return node;}
 function badge(row){
   const node=label('span',stateName[row.group]||stateName.pending);
   node.className='mm-badge';node.dataset.group=row.group;
   if((row.group==='pending'||row.group==='failed')&&stageName[row.state])OAUI.attr(node,'data-oa-hint',stageName[row.state]);
   return node;
 }
 function saveSelection(){
   try{sessionStorage.setItem('openahoy.media.monitor',JSON.stringify({kind,selected}));}catch(_){}
 }
 try{
   const saved=JSON.parse(sessionStorage.getItem('openahoy.media.monitor'));
   if(saved&&['all',...Object.keys(medium)].includes(saved.kind))kind=saved.kind;
   if(typeof saved?.selected==='string')selected=saved.selected;
 }catch(_){}
 function matches(){
   const query=search.value.trim().toLocaleLowerCase();
   return rows.filter(row=>(kind==='all'||kind===row.kind)&&(!state||state===row.group)
      &&(!query||[title(row),row.model,row.attempt].filter(Boolean).join(' ').toLocaleLowerCase().includes(query)));
 }
 function thumb(row,node){
   const source=thumbnails.get(fingerprint(row));
   if(!source)return;
   const img=element('img');img.alt='';img.src=source;node.replaceChildren(img);
 }
 function makeList(){
   const visible=matches(),scroll=list.scrollTop;
   list.replaceChildren();list.setAttribute('aria-busy',String(loading));
   for(const row of visible){
     const node=button('{0}',()=>choose(row,true,true));
     node.className='mm-row';node.dataset.asset=key(row);node.dataset.oaOverflow='.mm-text strong';node.dataset.oaFullName=title(row);
     node.setAttribute('aria-current',String(key(row)===selected));
     const icon=raw('span',{video:'▸',audio:'♫',gif:'▧'}[row.kind],'mm-thumb');
     icon.setAttribute('aria-hidden','true');thumb(row,icon);
     const text=element('span','mm-text');
     const subtitle=[message(medium[row.kind]),row.model||row.provider,row.updated_at?stamp(row.updated_at):null].filter(Boolean);
     text.append(raw('strong',title(row)),label('small','{0}',subtitle));
     node.replaceChildren(icon,text,badge(row));list.append(node);
   }
   if(!visible.length)list.append(label('p',loading?'正在读取媒体记录…':'没有符合条件的媒体记录。'));
   list.scrollTop=scroll;
   for(const control of filters.querySelectorAll('button'))control.setAttribute('aria-pressed',String(control.dataset.kind===kind));
   $('monitorSunoJump').hidden=kind!=='audio';
   states.replaceChildren();
   const current=rows.filter(row=>kind==='all'||row.kind===kind);
   for(const [group,name] of Object.entries(stateName)){
     const control=button('{0} {1}',()=>{state=state===group?'':group;renderFiltered();states.querySelector('[data-group='+group+']').focus();});
     control.dataset.group=group;OAUI.set(control,'{0} {1}',message(name),fmt(current.filter(row=>row.group===group).length));
     control.setAttribute('aria-pressed',String(state===group));states.append(control);
   }
 }
 function clearPlayers(){
   playerEpoch++;for(const dispose of releases.splice(0))dispose();
 }
 function rememberThumbnail(row,source){
   if(!source||thumbnails.has(fingerprint(row)))return;
   thumbnails.set(fingerprint(row),source);
   for(const item of list.querySelectorAll('button'))if(item.dataset.asset===key(row))thumb(row,item.firstElementChild);
 }
 function capture(row,picture,width,height,resolution=96){
   if(!width||!height||thumbnails.has(fingerprint(row)))return;
   const canvas=element('canvas');canvas.width=resolution;canvas.height=Math.max(1,Math.round(resolution*height/width));
   canvas.getContext('2d').drawImage(picture,0,0,canvas.width,canvas.height);
   const source=canvas.toDataURL('image/jpeg',.8);
   rememberThumbnail(row,source);
   return source;
 }
 async function mediaBytes(row,current){
   const chunks=[];let offset=0;
   while(offset<row.asset.bytes){
     if(!current())return null;
     const value=await invoke(ops[row.family][0],{...scope(row),offset});
     if(!current())return null;
     const {total,sha256}=value;
     if(total!==row.asset.bytes||(sha256&&sha256!==row.asset.sha256)||(value.offset??offset)!==offset)throw Error('MEDIA_CHANGED');
     const data=Uint8Array.from(atob(value.bytes??value.data),character=>character.charCodeAt(0));
     const next=offset+data.length;
     if(next===offset||next>total||(value.next??next)!==next)throw Error('MEDIA_CHANGED');
     chunks.push(data);offset=next;
   }
   return new Blob(chunks,{type:row.asset.mime||mediaMime[row.kind]});
 }
 async function gifPlayer(blob,row,slot,current,run){
   if(typeof ImageDecoder!=='function')throw Error('MEDIA_GIF_DECODER_UNAVAILABLE');
   const bytes=await blob.arrayBuffer();if(!current())return;
   const decoder=new ImageDecoder({type:'image/gif',data:bytes,preferAnimation:true});
   let timer,playing=run,frameIndex=0,step=0;
   releases.push(()=>{clearTimeout(timer);step++;decoder.close();});
   await decoder.tracks.ready;if(!current())return;
   const canvas=element('canvas'),toolbar=element('div','mm-toolbar');
   const context=canvas.getContext('2d'),loop=element('input');loop.type='checkbox';loop.checked=true;
   const loopLabel=element('label');loopLabel.append(loop,OAUI.label('循环'));
   const toggle=button(playing?'暂停':'播放',()=>{
     playing=!playing;clearTimeout(timer);step++;OAUI.set(toggle,playing?'暂停':'播放');
     if(playing)void draw(step).catch(fail);
   });
   toolbar.append(toggle,loopLabel);slot.replaceChildren(canvas,toolbar);
   const count=decoder.tracks.selectedTrack.frameCount;
   const delays=new Map(),duration=element('span');duration.className='mm-muted';
   toolbar.append(duration);
   function fail(){if(current())slot.replaceChildren(label('p','无法预览此文件。'));}
   async function draw(intent){
     const {image}=await decoder.decode({frameIndex});
     try{
       if(!current()||intent!==step)return;
       if(!canvas.dataset.ready){canvas.width=image.displayWidth;canvas.height=image.displayHeight;canvas.dataset.ready='true';}
       context.drawImage(image,0,0);
       if(frameIndex===0)capture(row,canvas,canvas.width,canvas.height);
       if(typeof image.duration==='number'&&image.duration>0)delays.set(frameIndex,image.duration);
       if(delays.size===count&&!duration.textContent){
         const seconds=[...delays.values()].reduce((sum,value)=>sum+value,0)/1e6;
         OAUI.set(duration,'{0} 秒',fmt(seconds));
       }
       if(!playing)return;
       if(frameIndex+1>=count&&!loop.checked){playing=false;frameIndex=0;OAUI.set(toggle,'播放');return;}
       frameIndex=(frameIndex+1)%count;
       timer=setTimeout(()=>void draw(intent).catch(fail),Math.max(16,(image.duration||100000)/1000));
     }finally{image.close();}
   }
   await draw(step);
 }
 async function play(row,slot,run=false){
   if(!playable(row)){slot.append(label('p',stageName[row.state]||'记录状态待核实'));return;}
   const epoch=playerEpoch,current=()=>active&&epoch===playerEpoch;
   slot.replaceChildren(label('p','正在读取原文件…'));
   try{
     const blob=await mediaBytes(row,current);if(!blob||!current())return;
     if(row.kind==='gif'){await gifPlayer(blob,row,slot,current,run);return;}
     const player=element(row.kind==='video'?'video':'audio'),url=URL.createObjectURL(blob);
     player.controls=true;player.controlsList='nodownload';player.preload='metadata';player.playsInline=true;player.src=url;
     releases.push(()=>{player.pause();player.removeAttribute('src');player.load();URL.revokeObjectURL(url);});
     if(row.kind==='video'){
       const preview=thumbnails.get(fingerprint(row));if(preview)player.poster=preview;
       else player.addEventListener('loadeddata',()=>{
         if(!current())return;
         // A paused Chromium video may not have composited its first frame yet.
         // Request a decoded frame close to the start, without starting playback.
         if(!run&&player.paused&&player.currentTime===0&&player.duration>.1){
           player.addEventListener('seeked',()=>{if(current())capture(row,player,player.videoWidth,player.videoHeight,480);},{once:true});
           player.currentTime=.08;
         }else if(player.requestVideoFrameCallback){
           const token=player.requestVideoFrameCallback(()=>{if(current())capture(row,player,player.videoWidth,player.videoHeight,480);});
           releases.push(()=>player.cancelVideoFrameCallback(token));
         }
       },{once:true});
     }
     player.addEventListener('error',()=>{if(current())slot.replaceChildren(label('p','无法预览此文件。'));},{once:true});
     slot.replaceChildren(player);
     if(run)await player.play().catch(()=>{});
   }catch(_){if(current())slot.replaceChildren(label('p','无法预览此文件。'));}
 }
 async function download(event,row,control){
   if(!event.isTrusted||control.disabled)return;
   control.disabled=true;control.setAttribute('aria-busy','true');OAUI.set(control,'正在保存…');delete control.dataset.state;
   try{
     const result=await invoke(ops[row.family][1],scope(row));
     if(result.state!=='EXPORTED'||result.sha256!==row.asset.sha256||result.bytes!==row.asset.bytes)throw Error('MEDIA_CHANGED');
     OAUI.set(control,'已下载');
   }catch(_){OAUI.set(control,'下载失败 · 重试');control.dataset.state='error';}
   finally{control.removeAttribute('aria-busy');control.disabled=false;}
 }
 function jump(ref,run){
   const next=byKey(key(ref));if(!next)return;
   history.push({kind,state,selected,compare,search:search.value,listScroll:list.scrollTop,detailScroll:detail.scrollTop});
   if(kind!=='all'&&kind!==next.kind)kind=next.kind;
   state='';search.value='';choose(next,true,true,run);
 }
 function restore(){
   const previous=history.pop();if(!previous)return;
   kind=previous.kind;state=previous.state;selected=previous.selected;compare=previous.compare;search.value=previous.search;
   makeList();renderDetail(true);list.scrollTop=previous.listScroll;detail.scrollTop=previous.detailScroll;detail.focus({preventScroll:true});saveSelection();
 }
 function interval(rel){
   if(typeof rel.seconds!=='number')return null;
   const n=value=>String(Math.round(value*1000)/1000);
   return message('视频 {0}–{1}s · 音轨 {2}–{3}s',n(rel.video_start),n(rel.video_start+rel.seconds),
                  n(rel.music_offset),n(rel.music_offset+rel.seconds));
 }
 function relationships(row){
   if(row.kind==='gif')return;
   const section=element('section','mm-links');
   section.append(label('h3',row.kind==='video'?'此版本使用的配乐':'使用此音频的视频'));
   if(row.kind==='video'){
     const rel=row.soundtrack;
     if(rel?.target){
       const line=element('div','mm-relation');
       if(rel.provider==='suno'){const logo=element('img');logo.src='data:image/x-icon;base64,__SUNO_BRAND__';logo.alt='';line.append(logo);}
       const text=element('div','mm-text');
       text.append(raw('strong',[({suno:'Suno','ace-music':'ACE Music'}[rel.provider]||rel.provider),rel.target.title].filter(Boolean).join(' · ')));
       if(interval(rel))text.append(label('small','{0}',interval(rel)));
       line.append(text,button('试听',()=>jump(rel.target,true)),button('查看音频',()=>jump(rel.target,false)));
       section.append(line);
     }else section.append(label('p',rel?'原音频当前不可读取':'配乐来源未记录'));
     const original={retained:'已保留原声',excluded:'未保留原声',silent:'原片无音轨'}[row.original_audio];
     if(original)section.append(label('p',original));
   }else{
     if(!row.used_in?.length)section.append(label('p','暂无已记录的合成版本。'));
     for(const rel of row.used_in||[]){
       const next=byKey(key(rel)),line=element('div','mm-relation'),text=element('div','mm-text');
       text.append(label('strong',next?.version?'{0} · 版本 {1}':'{0}',rel.title,next?.version));
       if(interval(rel))text.append(label('small','{0}',interval(rel)));
       line.append(text,button('查看视频',()=>jump(rel,false)));section.append(line);
     }
   }
   body.append(section);
 }
 function versionSelect(row){
   if(!row.versions)return;
   const lane=element('div','mm-toolbar');
   for(const mode of ['version','compare']){
     const select=element('select');
     const name=mode==='version'?'当前版本':'版本对比';
     OAUI.attr(select,'aria-label',name);
     if(mode==='compare')select.append(label('option',name));
     for(const version of row.versions){
       const id=key(version);if(mode==='compare'&&(id===key(row)||!playable(byKey(id))))continue;
       const option=label('option','版本 {0} · {1}',version.version,version.title);option.value=id;select.append(option);
     }
     if(mode==='compare')select.firstChild.value='';
     select.value=mode==='version'?key(row):compare;
     select.onchange=()=>{if(mode==='version')choose(byKey(select.value),true,false);
       else{compare=select.value;renderDetail(true);body.querySelector('[aria-label="'+OAUI.format(name)+'"]').focus();}};
     lane.append(select);
   }
   body.append(lane);
 }
 function usageSummary(usage){
   const values={...usage,...usage?.tool_usage};
   return Object.entries(usageLabels).filter(([id])=>typeof values[id]==='number')
                .map(([id,name])=>message('{0} {1}',message(name),fmt(values[id])));
 }
 function facts(row){
   const fold=element('details','mm-facts');
   fold.append(label('summary','原任务与用量'));
   if(row.model||row.provider)fold.append(raw('p',[row.provider,row.model,row.provider_site].filter(Boolean).join(' · ')));
   fold.append(label('p',row.original_task?'供应商任务 {0}':'未记录供应商任务号',row.original_task));
   fold.append(label('p','本机回执 {0}',row.attempt));
   if(row.updated_at)fold.append(label('p','最后记录 {0}',stamp(row.updated_at)));
   if(row.diagnostic)fold.append(raw('p',row.diagnostic));
   const meters=usageSummary(row.usage);
   fold.append(label('p',meters.length?'供应商用量 · {0}':'供应商用量未返回',meters));
   const cost=row.actual_amount??row.list_price_cny??row.list_price_usd;
   const unit=row.actual_currency||(row.list_price_cny!=null?'CNY':'USD');
   fold.append(label('p',cost==null?'实扣金额未返回':row.actual_amount!=null?'供应商实扣 {0} {1}':'公开标价估算 {0} {1} · 实扣未返回',
                     cost==null?'':fmt(cost),unit));
   const controls=element('div','mm-toolbar');
   if(row.original_task&&row.family==='video'){
     const status=label('p',''), query=button('查询原任务',async()=>{
       query.disabled=true;OAUI.set(status,'正在查询原任务…');
       try{
         const snapshot=await invoke('media_monitor_task',scope(row));
         const source=message(snapshot.source==='LOCAL_ASSET'?'本机原件':'供应商');
         const state=message(stageName[snapshot.state]||'记录状态待核实');
         const checked=stamp(snapshot.read_at),reading=usageSummary(snapshot.usage);
         OAUI.set(status,reading.length?'{0} · {1} · {2} · {3}':'{0} · {1} · {2}',
                   source,state,checked,reading);
       }catch(_){OAUI.set(status,'原任务暂不可查询，已保留本机回执。');}
       finally{query.disabled=false;}
     });
     status.setAttribute('role','status');controls.append(query);fold.append(status);
   }else controls.append(button('刷新原回执',()=>void refresh()));
   const instruction=title(row)+'\n'+OAUI.format('本机回执 {0}',[row.attempt])+'\n'+row.project;
   const use=button('在 Codex 中继续',async()=>{
     try{await sendChat(instruction);OAUI.set(use,'已发到当前 Codex 聊天。');}
     catch(_){
       const copy=element('textarea');copy.readOnly=true;copy.value=instruction;OAUI.attr(copy,'aria-label','复制任务信息');
       if(navigator.clipboard){try{await navigator.clipboard.writeText(instruction);OAUI.set(use,'已复制任务信息');return;}catch(_){}}
       fold.append(copy);copy.focus();copy.select();
     }
   });
   controls.append(use);fold.append(controls);body.append(fold);
 }
 function renderDetail(force=false,run=false){
   if(root.hidden||narrow.matches&&root.dataset.detail!=='true'){
     clearPlayers();loaded='';activateSuno(false);
     return;
   }
   const row=byKey(selected);
   const snapshot=JSON.stringify([row,compare,kind==='audio']);
   $('monitorRelationBack').hidden=!history.length;
   const showSuno=!canvas&&(row?.kind==='audio'||kind==='audio');
   $('monitorSuno').hidden=!showSuno;activateSuno(showSuno);
   if(!force&&loaded===snapshot)return;
   loaded=snapshot;clearPlayers();body.replaceChildren();
   if(!row){if(!showSuno)body.append(label('p','选择一项查看详情。'));return;}
   const heading=element('div','mm-heading'),meta=element('div');
   const qualified=[row.project_label,row.account_label].filter(Boolean).join(' · ');
   meta.append(raw('h2',row.title),raw('p',qualified,'mm-muted'));heading.append(meta,badge(row));body.append(heading);
   versionSelect(row);
   if(playable(row)){
     const preview=element('div','mm-preview'),primary=element('div');
     preview.append(primary);body.append(preview);void play(row,primary,run);
     const second=byKey(compare);
     if(playable(second)){
       const related=element('div');preview.dataset.compare='true';preview.append(related);void play(second,related);
     }
     const meter=element('div','mm-toolbar mm-muted'),asset=row.asset;
     const properties=[asset.width&&asset.height?asset.width+' × '+asset.height:null,
       typeof asset.seconds==='number'?message('{0} 秒',fmt(asset.seconds)):null,
       typeof (asset.frames??asset.frame_count)==='number'?message('{0} 帧',fmt(asset.frames??asset.frame_count)):null].filter(Boolean);
     meter.append(label('span','{0}',properties));
     const save=button('下载原文件',event=>void download(event,row,save));save.setAttribute('aria-live','polite');meter.append(save);
     if(canvas?.canAttach(row))meter.append(button('加入画布',()=>canvas.attach(row)));
     if(row.kind==='video'){
       const score=button('生成配乐',async()=>{
         const instruction=OAMusicRequest('score',{project:row.project,attempt:row.attempt});
         try{await sendChat(instruction);OAUI.set(score,'已发到当前 Codex 聊天。');}
         catch(_){
           const copy=element('textarea');copy.readOnly=true;copy.value=instruction;OAUI.attr(copy,'aria-label','复制 Codex 指令');
           meter.append(copy);copy.focus();copy.select();
         }
       });
       meter.append(score);
     }
     body.append(meter);
   }else body.append(label('p',stageName[row.state]||'记录状态待核实'));
   relationships(row);facts(row);
 }
 function choose(row,openDetail=false,focus=false,run=false){
   if(!row)return;
   if(selected!==key(row))compare='';
   selected=key(row);root.dataset.detail=String(openDetail);makeList();renderDetail(false,run);saveSelection();
   if(openDetail)detail.scrollTop=0;
   if(focus)detail.focus({preventScroll:true});
 }
 function renderFiltered(){
   const matching=matches();
   if(!matching.some(row=>key(row)===selected)){
     selected=key(matching.find(playable)||matching[0]||{});compare='';
   }
   if(!matching.length){selected='';root.dataset.detail='false';}
   makeList();renderDetail();saveSelection();
 }
 async function refresh(){
   if(!active||loading)return;
   loading=true;const request=++readSequence;
   const control=$('monitorRefresh');control.disabled=true;control.setAttribute('aria-busy','true');makeList();
   try{
     const result=await invoke('media_monitor',{});
     if(!active||request!==readSequence)return;
     if(!Array.isArray(result.rows))throw Error('MEDIA_READ_FAILED');
     rows=result.rows;readAt=result.read_at;unavailable=result.unavailable||[];
     delete $('monitorRead').dataset.state;
     OAUI.set($('monitorRead'),unavailable.length?'读取于 {0} · 部分记录不可用':'读取于 {0}',stamp(readAt));
   }catch(_){if(active&&request===readSequence){
     $('monitorRead').dataset.state='error';
     OAUI.set($('monitorRead'),readAt?'刷新失败 · 保留 {0} 的记录':'无法读取媒体记录。',readAt?stamp(readAt):'');
   }}
   finally{
     if(active&&request===readSequence){
       loading=false;control.removeAttribute('aria-busy');control.disabled=false;renderFiltered();
       if(routedTarget){
         const target=routedTarget;routedTarget=null;
         const row=byKey(key(target));
         if(playable(row)&&row.asset.sha256===target.sha256)choose(row,true,true);
         else{
           selected='';clearPlayers();makeList();
           body.replaceChildren(label('p','原素材不存在或已变更。'));
           root.dataset.detail='true';
         }
       }
     }
   }
 }
 for(const control of filters.querySelectorAll('button'))control.onclick=()=>{
   kind=control.dataset.kind;state='';root.dataset.detail='false';renderFiltered();list.scrollTop=0;
 };
 search.oninput=()=>{renderFiltered();list.scrollTop=0;};
 $('monitorListBack').onclick=()=>{
   root.dataset.detail='false';renderDetail();(Array.from(list.querySelectorAll('button')).find(item=>item.dataset.asset===selected)||list).focus({preventScroll:true});
 };
 $('monitorRelationBack').onclick=restore;
 $('monitorSunoJump').onclick=()=>{
   root.dataset.detail='true';renderDetail();
   const current=$('audioProviderAce').getAttribute('aria-pressed')==='true'?'audioProviderAce':'audioProviderSuno';
   const control=$(current);
   (control.getClientRects().length?control:$('sunoRefresh')).focus({preventScroll:true});
   $('monitorSuno').scrollIntoView({block:'start'});
 };
 narrow.addEventListener('change',()=>{if(active)renderDetail();});
 $('monitorRefresh').onclick=()=>void refresh();
 $('monitorSettings').onclick=()=>{clearPlayers();loaded='';activateSuno(false);activateSettings(true);};
 $('monitorSettingsBack').onclick=()=>{activateSettings(false);renderDetail(true);$('monitorSettings').focus();};
 return {open(target,asset=null){
   kind=canvas?'all':target==='media'?kind:target;
   routedTarget=asset;
   if(asset){state='';search.value='';}
   if(active){renderFiltered();if(asset)void refresh();return;}
   active=true;loaded='';root.dataset.detail='false';activateSettings(false);void refresh();
 },close(){
   routedTarget=null;active=false;loading=false;readSequence++;history=[];clearPlayers();loaded='';$('monitorRefresh').removeAttribute('aria-busy');activateSuno(false);activateSettings(false);
 }};
}
'''.replace('__SUNO_BRAND__', BRAND)
