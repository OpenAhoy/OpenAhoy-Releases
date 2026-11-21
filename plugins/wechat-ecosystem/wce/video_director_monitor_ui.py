"""Read-only Jiusera review of the active work and its original deliveries."""

HTML = '''
<section id="directorMonitor" aria-label="导演台" hidden>
 <section class="dm-panel dm-main" aria-labelledby="dmScreenTitle">
  <header class="dm-heading">
   <div class="dm-heading-copy"><h2 id="dmScreenTitle">监看</h2><p id="dmNow"></p><p id="dmShotStage" role="status"></p><span id="dmPlaybackState" class="dm-state" hidden></span></div>
   <div class="dd-actions">
    <button id="dmFilm" type="button" hidden>作品成片</button>
    <button id="dmGoCanvas" type="button">去画布</button>
   </div>
  </header>
  <label id="dmCandidateLabel" hidden>视频候选 <select id="dmCandidate"></select></label>
  <div id="dmScreen"></div>
 </section>
 <aside class="dm-sidebar">
  <section class="dm-panel" aria-labelledby="dmShotsTitle">
   <div class="dm-heading"><h2 id="dmShotsTitle">镜头</h2><span id="dmShotCount"></span></div>
   <div id="dmShots"></div>
  </section>
  <section class="dm-panel" aria-labelledby="dmTasksTitle">
   <div class="dm-heading"><h2 id="dmTasksTitle">任务</h2><button id="dmTasksLink" type="button">任务详情</button></div>
   <div id="dmTasks"></div>
  </section>
 </aside>
</section>
'''

STYLE = '''
#directorMonitor{display:grid;grid-template-columns:minmax(0,2.35fr) minmax(212px,1fr);gap:12px;
 align-content:start;align-items:start;min-width:0}
.dm-panel{min-width:0;border:1px solid var(--line);border-radius:12px;background:var(--surface);padding:12px}
.dm-main,.dm-sidebar{display:grid;min-width:0;gap:10px;align-content:start}
.dm-heading{display:flex;justify-content:space-between;align-items:center;gap:8px}
.dm-heading-copy{min-width:0}
#dmNow,#dmShotCount,#dmShotStage{color:var(--muted);font-size:11px;overflow-wrap:anywhere}
#dmNow:empty,#dmShotStage:empty{display:none}
#videoDirectorDesk #dmCandidateLabel:not([hidden]){display:flex;align-items:center;gap:7px}
#dmCandidateLabel>select{flex:1;min-width:0;text-overflow:ellipsis}
#dmScreen{min-width:0}
#dmScreen .oa-video-poster,#dmScreen video,#dmScreen .oa-frame-screen,
#dmScreen[data-kind=image]>img,.dm-screen-empty{width:100%;aspect-ratio:16/9;max-height:min(59dvh,620px);
 object-fit:contain;border-radius:8px}
#dmScreen[data-kind=image]>img{display:block;background:var(--soft)}
#dmScreen .oa-inline-video-player>button{justify-self:start}
.dm-screen-empty{display:grid;place-items:center;background:var(--soft);color:var(--muted);text-align:center;padding:10px}
#dmShots,#dmTasks{display:grid;gap:4px;margin-top:7px;min-width:0}
#dmShots>p,#dmTasks>p{color:var(--muted);font-size:12px}
.dm-scene{color:var(--muted);font-size:11px;margin-top:3px}
#videoDirectorDesk .dm-shot,.dm-task{display:grid;align-items:center;gap:7px;text-align:start}
#videoDirectorDesk .dm-shot{grid-template-columns:46px minmax(0,1fr) auto;width:100%;min-width:0;padding:4px 5px;
 background:transparent;box-shadow:none;border-color:transparent;min-height:38px}
#videoDirectorDesk .dm-shot[aria-pressed=true]{background:var(--oa-selection,var(--tint));border-color:var(--line)}
.dm-task{grid-template-columns:minmax(0,1fr) auto;min-height:27px;padding:3px 5px;border-bottom:1px solid var(--line)}
.dm-task:last-child{border-bottom:0}
.dm-label{min-width:0;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;font-size:12px}
.dm-thumbnail{display:grid;place-items:center;width:46px;height:28px;border-radius:4px;overflow:hidden;background:var(--soft)}
.dm-thumbnail img{display:block;width:100%;height:100%;object-fit:cover}
.dm-state{display:inline-flex;align-items:center;gap:4px;color:var(--muted);font-size:11px;white-space:nowrap}
.dm-state::before{content:'';display:block;width:6px;height:6px;border-radius:50%;background:currentColor;flex:none}
.dm-state[data-tone=ready]{color:light-dark(#28734d,#8bd7ac)}
.dm-state[data-tone=active]{color:light-dark(#345c9b,#a9c8ff)}
.dm-state[data-tone=attention]{color:light-dark(#936012,#ffd287)}
.dm-state[data-tone=failed]{color:light-dark(#aa394e,#ffadb8)}
@media(max-width:840px){
 #directorMonitor{grid-template-columns:minmax(0,1fr)}
 .dm-sidebar{grid-template-columns:repeat(2,minmax(0,1fr))}
}
@media(max-width:550px){
 .dm-sidebar{grid-template-columns:minmax(0,1fr)}
 .dm-panel{padding:9px}
 #dmScreen .oa-video-poster,#dmScreen video,#dmScreen .oa-frame-screen{max-height:none}
}
'''

SCRIPT = r'''
function OADirectorMonitor({chooseShot,goCanvas,openTasks,play,picture}){
 const $=id=>document.getElementById(id);
 const screen=$('dmScreen'),selector=$('dmCandidate'),shotList=$('dmShots'),taskList=$('dmTasks');
 const film=$('dmFilm'),now=$('dmNow'),go=$('dmGoCanvas');
 const phases={
   ASSET_READY:['可播放','ready',2],SUBMITTED:['已提交','active',0],QUEUED:['排队中','active',0],
   RUNNING:['生成中','active',0],SAVE_PENDING:['正在取件','active',0],
   AWAITING_RECEIPT:['等待回执','attention',1],SUBMIT_UNKNOWN:['结果待确认','attention',1],
   UNKNOWN:['结果待确认','attention',1],UNAVAILABLE:['原素材不可读','attention',1],
   FAILED:['生成失败','failed',1],SUBMIT_REJECTED:['提交被拒绝','failed',1],
   EXPIRED:['已过期','failed',1],CANCELLED:['已取消','failed',1],
 };
 const missing=['尚未生成','empty',3];
 const history=new Map();
 let scope='',model=null,thumbs=new Map(),player=null,screenKey='',shotKey='',taskKey='',optionKey='';
 let choiceEpoch=0,choosing=false;
 const el=(tag,cls='')=>Object.assign(document.createElement(tag),{className:cls});
 const phase=row=>row?(phases[row.state]||phases.UNKNOWN):missing;
 const playable=row=>row?.state==='ASSET_READY'&&!!(row.asset||row).sha256;
 const preferred=rows=>rows.find(row=>row.adopted&&playable(row))||rows.find(playable)||rows.find(row=>row.adopted)||rows[0];
 const text=(tag,name,cls='')=>{const node=el(tag,cls);OAUI.set(node,name);return node;};
 const raw=(tag,name,cls='')=>{const node=el(tag,cls);OAUI.raw(node,name);node.title=name;return node;};
 function badge(row){
   const [label,tone]=phase(row),node=text('span',label,'dm-state');
   node.dataset.tone=tone;if(row)node.dataset.state=row.state;
   return node;
 }
 function thumbnails(scene,shot,slot){
   if(!shot.cover_revision)return;
   const target={...model.scope,scene_id:scene.id,shot_id:shot.id,revision_id:shot.cover_revision};
   const key=JSON.stringify(target);
   if(!thumbs.has(key))thumbs.set(key,picture(target,true).then(img=>img?.src).catch(()=>null));
   void thumbs.get(key).then(src=>{
     if(!src||!slot.isConnected)return;
     const img=el('img');img.alt='';img.src=src;slot.replaceChildren(img);
   });
 }
 function selectSource(kind){
   choice().source=kind;
   draw();
 }
 const choice=()=>history.get(scope);
 function closeScreen(){player?.close();player=null;screenKey='';screen.replaceChildren();}
 function render(state){
   if(!state?.work){
     if(!model&&screen.dataset.kind==='empty')return;
     clear();
     screen.dataset.kind='empty';
     screen.append(text('p','暂无可播放视频','dm-screen-empty'));
     OAUI.raw($('dmShotCount'),'0');
     shotList.append(text('p','还没有镜头'));
     taskList.append(text('p','暂无任务'));
     go.disabled=false;
     return;
   }
   const next=JSON.stringify(state.scope);
   if(next!==scope){
     scope=next;choiceEpoch++;choosing=false;thumbs=new Map();shotKey='';taskKey='';optionKey='';closeScreen();
     if(!history.has(scope))history.set(scope,{source:'auto',candidates:new Map()});
   }
   $('dmTasksLink').disabled=false;model=state;draw();
 }
 function draw(){
   const {work,context,cards}=model,selection=choice();
   const shots=work.scenes.flatMap(scene=>scene.shots.map(shot=>{
     const revision=shot.adopted_revision||shot.head_revision;
     const title=shot.revisions.find(row=>row.id===revision)?.title||'';
     const rows=cards.filter(row=>row.kind==='shot_video'&&row.scene_id===scene.id&&row.shot_id===shot.id);
     return {scene,shot,revision,title,rows};
   }));
   const films=cards.filter(row=>row.kind==='work_video'),inbox=cards.filter(row=>row.kind==='inbox_video');
   const focus=shots.find(row=>row.shot.id===context?.shot_id&&row.scene.id===context?.scene_id);
   const sources=selection.source==='film'||(selection.source==='auto'&&films.some(playable))?films:
                 work.inbox?inbox:(focus?.rows||[]);
   const category=sources===films?'film':work.inbox?'inbox':focus?.shot.id;
   const active=sources.find(row=>row.id===selection.candidates.get(category))||preferred(sources);
   const revision=focus&&context.revision;
   const visibleTitle=sources===films?active?.title:work.inbox?active?.title:revision?.title;
   OAUI.raw(now,visibleTitle||'');
   const storyboard=revision&&[revision.notes,revision.purpose,revision.opening,revision.action,revision.ending,
     revision.composition,revision.camera,revision.lighting].some(part=>part?.trim());
   const evidence=revision&&[storyboard?OAUI.format('分镜已保存'):'',
     revision.images.length?OAUI.format('参考图已关联'):''].filter(Boolean);
   OAUI.raw($('dmShotStage'),evidence?.length?['v'+revision.number,...evidence].join(' · '):'');
   const state=$('dmPlaybackState'),[message,tone]=phase(active);
   state.hidden=!active;
   if(active){state.dataset.tone=tone;OAUI.set(state,message);}
   film.hidden=!films.some(playable);
   film.setAttribute('aria-pressed',String(sources===films));
   go.disabled=choosing;
   selector.dataset.category=category||'';
   const nextOptions=JSON.stringify(sources.map(row=>[row.id,row.state,row.title,row.adopted,row.engine]));
   if(nextOptions!==optionKey){
     optionKey=nextOptions;
     selector.replaceChildren(...sources.map((row,index)=>{
       const option=new Option('',row.id);
       if(row.kind==='shot_video')OAUI.set(option,'候选 {0} · {1}',index+1,
         [row.engine?.model,OAUI.message(phase(row)[0]),row.adopted?OAUI.message('已采用'):null].filter(Boolean));
       else OAUI.raw(option,row.title);
       return option;
     }));
   }
   if(active)selector.value=active.id;
   $('dmCandidateLabel').hidden=sources.length<2;
   const target=targetFor(focus,context);
   const visual=playable(active)?['video',scope,active.id,(active.asset||active).sha256]:
     target?['image',scope,target,active?.state]:['empty',scope,active?.state];
   const fingerprint=JSON.stringify(visual);
   if(fingerprint!==screenKey){
     closeScreen();screenKey=fingerprint;screen.dataset.kind=visual[0];
     if(visual[0]==='video')player=play(screen,active,model.scope);
     else{
       screen.append(text('p',active?phase(active)[0]:'暂无可播放视频','dm-screen-empty'));
       if(target)void picture(target).then(img=>{
         if(img&&screenKey===fingerprint)screen.replaceChildren(img);
       }).catch(()=>{});
     }
   }
   const shotSignature=JSON.stringify(shots.map(({scene,shot,title,rows})=>[scene.id,scene.title,shot.id,title,
     shot.cover_revision,preferred(rows)?.state,context?.shot_id===shot.id,sources===films]));
   if(shotSignature!==shotKey){
     shotKey=shotSignature;const nodes=[];let group='';
     for(const item of shots){
       const {scene,shot,title,rows}=item;
       if(scene.id!==group){nodes.push(raw('div',scene.title,'dm-scene'));group=scene.id;}
       const control=el('button','dm-shot');control.type='button';control.dataset.shot=shot.id;
       control.setAttribute('aria-pressed',String(focus===item&&sources!==films));
       const slot=el('span','dm-thumbnail');slot.setAttribute('aria-hidden','true');
       control.append(slot,raw('strong',title,'dm-label'),badge(preferred(rows)));
       control.onclick=async()=>{
         if(scope!==JSON.stringify(model.scope))return;
         const intent=++choiceEpoch;
         choice().source='shot';
         choosing=true;go.disabled=true;
         try{await chooseShot(scene.id,shot.id,item.revision);}
         finally{
           if(intent===choiceEpoch){choosing=false;go.disabled=false;}
         }
       };
       nodes.push(control);thumbnails(scene,shot,slot);
     }
     OAUI.raw($('dmShotCount'),String(shots.length));
     shotList.replaceChildren(...(nodes.length?nodes:[text('p','还没有镜头')]));
   }
   const tasks=new Map();
   for(const row of cards){
     if(!row.attempt_id||row.kind==='work_video')continue;
     const prior=tasks.get(row.attempt_id);
     if(!prior||phase(row)[2]<phase(prior)[2])tasks.set(row.attempt_id,row);
   }
   const ordered=[...tasks.values()].sort((a,b)=>phase(a)[2]-phase(b)[2]);
   const taskSignature=JSON.stringify(ordered.map(row=>[row.attempt_id,row.state,row.title]));
   if(taskSignature!==taskKey){
     taskKey=taskSignature;
     taskList.replaceChildren(...(ordered.length?ordered.map(row=>{
       const line=el('div','dm-task');line.dataset.attempt=row.attempt_id;
       line.append(raw('strong',row.title,'dm-label'),badge(row));return line;
     }):[text('p','暂无任务')]));
   }
 }
 function targetFor(focus,context){
   if(!focus||!context)return null;
   const revision=context.revision?.images?.length?context.revision.id:focus.shot.cover_revision;
   return revision?{...model.scope,scene_id:focus.scene.id,shot_id:focus.shot.id,revision_id:revision}:null;
 }
 function clear(){
   closeScreen();model=null;scope='';choiceEpoch++;choosing=false;thumbs.clear();shotKey='';taskKey='';optionKey='';
   delete screen.dataset.kind;
   OAUI.raw(now,'');OAUI.raw($('dmShotCount'),'');OAUI.raw($('dmShotStage'),'');
   $('dmPlaybackState').hidden=true;film.hidden=true;
   $('dmCandidateLabel').hidden=true;selector.replaceChildren();
   shotList.replaceChildren();taskList.replaceChildren();go.disabled=true;$('dmTasksLink').disabled=true;
 }
 selector.onchange=()=>{
   if(model)choice().candidates.set(selector.dataset.category,selector.value);
   if(model)draw();
 };
 film.onclick=()=>{if(model)selectSource('film');};
 go.onclick=()=>goCanvas();
 $('dmTasksLink').onclick=openTasks;
 return {render,clear};
}
'''
