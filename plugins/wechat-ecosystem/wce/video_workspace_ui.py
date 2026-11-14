"""The project video workspace in the existing management resource."""

HTML = '''
<section id="videoWorkspace" hidden>
<header class="oa-video-header"><h1>视频生成</h1><label class="oa-video-project">项目<select id="videoProject"></select></label><button id="videoSettings" type="button" aria-expanded="false">模型设置</button></header>
<div id="videoSettingsPanel" hidden>__CREDENTIAL__</div>
<div class="oa-video-grid">
<section class="oa-video-preview">
<div class="oa-video-section-head"><h2>成片</h2><button id="videoCompare" type="button" aria-pressed="false">版本对比</button></div>
<div id="videoPlayers"><div><label class="oa-video-version">当前版本<select id="videoPrimary"></select></label>
<div id="videoPlayer" class="oa-frame-player" role="group" aria-label="当前版本" tabindex="-1"></div><p id="videoFacts"></p><div id="videoUsage" class="oa-video-usage" hidden></div>
<div class="oa-video-file-actions"><button id="videoDownload" class="oa-video-download" type="button" aria-live="polite" disabled>下载原文件</button><button id="videoSequence" type="button" hidden>连播原片与续写</button></div></div>
<div id="videoComparison" hidden><label>对比版本<select id="videoComparePick"></select></label>
<div id="videoComparePlayer" class="oa-frame-player" role="group" aria-label="对比版本"></div><p id="videoCompareFacts"></p><div id="videoCompareUsage" class="oa-video-usage" hidden></div></div></div>
<div class="oa-video-actions oa-video-derivatives">
<span>从选中版本继续</span>
<button id="videoAgain" type="button">再生成一版</button>
<button id="videoEdit" type="button">修改画面</button>
<button id="videoExtend" type="button">延长镜头</button>
</div></section>
<section class="oa-video-composer">
<h2>创作设置</h2>
<div class="oa-video-inputs"><label>模型<select id="videoWorkspaceModel"><option value="doubao-seedance-2-5-260628">Seedance 2.5</option>
<option value="doubao-seedance-2-0-260128">Seedance 2.0</option><option value="doubao-seedance-2-0-mini-260615">Seedance 2.0 Mini</option>
<option value="doubao-seedance-1-0-pro-250528">Seedance 1.0 Pro</option></select></label>
<label>模式<select id="videoMode"><option value="frames">首尾帧</option><option value="text">文字生成</option>
<option value="reference">参考图</option><option value="edit">修改画面</option><option value="extend">延长镜头</option></select></label></div>
<div class="oa-video-frames"><label id="videoFirstLabel"><span id="videoFrameLabel">首帧</span><input id="videoFirst" type="text" placeholder="项目内图片相对路径"></label>
<label id="videoLastLabel">尾帧<input id="videoLast" type="text" placeholder="项目内图片相对路径"></label></div>
<label id="videoDirectionLabel" hidden>方向<select id="videoDirection"><option value="before">向前延长</option><option value="after" selected>向后延长</option></select></label>
<label>镜头和动作<textarea id="videoPrompt" rows="4" maxlength="4096"></textarea></label>
<div class="oa-video-output"><label>时长<select id="videoDuration" aria-describedby="videoDurationHint"></select><small id="videoDurationHint"></small></label>
<label>清晰度<select id="videoResolution"><option>480p</option><option selected>720p</option><option>1080p</option></select></label>
<label class="oa-video-audio"><span>音频</span><span><input type="checkbox" id="videoAudio">生成音频</span></label></div>
<p id="videoSource"></p>
<details id="videoReferenceFallback" hidden><summary>使用已有的方舟素材</summary>
<label>方舟视频素材 ID<input id="videoReferenceAsset" type="text" placeholder="asset://…" maxlength="136" autocomplete="off"></label>
</details>
<div class="oa-video-actions"><button id="videoGenerate" class="primary" type="button">生成</button>
<button id="videoRefresh" type="button">查询原任务</button></div>
<p class="help">提交生成、修改或延长会按方舟用量计费。</p>
<p id="videoNotice" role="status" aria-live="polite"></p>
</section></div>
<details class="oa-video-library" aria-labelledby="videoLibraryTitle">
<summary id="videoLibraryTitle">项目视频资产库</summary>
<p id="videoLibraryEmpty" class="help">这个项目还没有成片。</p>
<ul id="videoLibraryList"></ul>
<details id="videoLibraryTrash" hidden><summary>最近移除</summary>
<ul id="videoLibraryTrashList"></ul></details>
<form id="videoLibraryRename" hidden><label>视频名称 <input id="videoLibraryName" required maxlength="120"></label>
<button class="primary" type="submit">保存名称</button><button id="videoLibraryCancel" type="button">取消</button></form>
<div id="videoLibraryConfirm" hidden><p>从资产库移除此视频？文件、生成记录和后续版本会保留，可在「最近移除」恢复。</p>
<button id="videoLibraryRemove" type="button">移除视频</button><button id="videoLibraryKeep" type="button">取消</button></div>
<p id="videoLibraryStatus" class="help" role="status" aria-live="polite"></p>
</details>
</section>
'''

STYLE = '''
#videoWorkspace{min-width:0;min-height:0;overflow:auto}
#videoWorkspace[hidden],#videoWorkspace [hidden],body.oa-video-open #nativeWorkspace{display:none!important}
#openVideoWorkspace[aria-current=page]{background:var(--management-selected,var(--line));font-weight:650}
 .oa-video-header,.oa-video-actions,.oa-video-file-actions,.oa-video-section-head{display:flex;align-items:center;gap:8px;flex-wrap:wrap}
.oa-video-header,.oa-video-section-head{justify-content:space-between}
.oa-video-header{margin-bottom:10px}
.oa-video-project{display:flex;align-items:center;gap:6px;min-width:0;max-width:100%;margin:0;font-size:12px}
.oa-video-project select{width:auto;min-width:0;max-width:calc(100% - 38px);min-height:32px;margin:0;font-size:12px}
.oa-video-header h1,.oa-video-grid h2{margin:0;line-height:1.3}
.oa-video-header h1{font-size:23px}
.oa-video-library{margin:12px 0 0;padding:8px 14px;background:var(--surface);border-radius:14px;box-shadow:0 3px 14px #0001}
.oa-video-library>summary{font-size:13px;font-weight:650;line-height:24px;cursor:pointer}
.oa-video-library[open]>summary{margin-bottom:5px}
.oa-video-library ul{max-height:220px;overflow:auto;margin:0;padding:0;list-style:none}
.oa-video-library li{display:flex;justify-content:space-between;align-items:center;gap:6px 12px;flex-wrap:wrap;padding:5px 7px;border-radius:8px}
.oa-video-library li:has(button[aria-pressed=true]){background:var(--tint)}
.oa-video-library li>div:first-child{min-width:0;flex:1 1 210px;overflow-wrap:anywhere}
.oa-video-library small,.oa-video-library code{display:block;color:var(--muted);font-size:11px;overflow-wrap:anywhere}
.oa-video-library :is(button,input){min-height:29px;font-size:12px}
.oa-video-library :is(form,#videoLibraryConfirm){padding:8px;background:var(--tint);border-radius:8px}
.oa-video-library input{max-width:100%}
.oa-video-library :is(details,p){margin:5px 0 0}
.oa-video-library p:empty,.oa-video-library ul:empty{display:none}
#videoWorkspace .oa-video-download{inline-size:11em;max-inline-size:100%}
.oa-video-grid{display:grid;grid-template-columns:minmax(0,1fr) minmax(0,1.15fr);gap:14px;align-items:start}
.oa-video-grid h2{font-size:15px}
.oa-video-grid>section{min-width:0;padding:14px;border:0;border-radius:14px;background:var(--surface);box-shadow:0 3px 14px #0001;display:grid;gap:10px}
.oa-video-composer{grid-row:1;grid-column:1}
.oa-video-preview{grid-row:1;grid-column:2}
.oa-video-grid label{display:grid;gap:3px;align-content:start;min-width:0;font-size:12px}
.oa-video-grid :is(input,select,textarea){box-sizing:border-box;max-width:100%;min-width:0;font:inherit}
.oa-video-grid :is(select,input[type=text]){min-height:34px}
.oa-video-grid textarea{width:100%;resize:vertical}
.oa-video-grid :is(button,input,select){margin:0}
.oa-video-header button,.oa-video-grid button{min-height:32px;padding:4px 9px;font-size:12px}
.oa-video-inputs,.oa-video-frames,.oa-video-output{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:7px;align-items:start}
.oa-video-inputs{grid-template-columns:minmax(0,1.25fr) minmax(0,1fr)}
.oa-video-frames{grid-template-columns:repeat(2,minmax(0,1fr))}
.oa-video-frames:not(:has(label:not([hidden]))){display:none}
.oa-video-audio>span:last-child{min-height:34px;display:flex;align-items:center;gap:5px}
.oa-video-grid p{margin:0;overflow-wrap:anywhere}
.oa-video-derivatives{padding-top:6px}
.oa-video-derivatives>span{font-size:12px;color:var(--muted);flex-basis:100%}
#videoPlayers{display:grid;grid-template-columns:minmax(0,1fr);gap:10px}
#videoPlayers:has(#videoComparison:not([hidden])){grid-template-columns:repeat(2,minmax(0,1fr))}
#videoPlayers>div{display:grid;gap:6px;align-content:start;min-width:0}
#videoPlayers .oa-frame-screen{max-height:min(310px,44dvh)}
#videoPlayers :is(#videoFacts,#videoCompareFacts){font-size:12px;color:var(--muted)}
#videoSettingsPanel{margin-bottom:12px}
.oa-video-usage{display:flex;gap:4px 12px;flex-wrap:wrap;align-items:baseline;font-size:12px;color:var(--muted)}
.oa-video-usage button{min-height:26px;padding:2px 7px;font-size:12px}
@media(max-width:720px){.oa-video-grid{grid-template-columns:minmax(0,1fr)}.oa-video-preview{grid-row:1;grid-column:1}.oa-video-composer{grid-row:2}}
@media(max-width:485px){#videoPlayers:has(#videoComparison:not([hidden])),.oa-video-inputs,.oa-video-frames{grid-template-columns:minmax(0,1fr)}.oa-video-grid>section{padding:11px}}
'''

SCRIPT = r'''
const OAVideoWorkspace = (call, credential, openBilling) => {
 const $=id=>document.getElementById(id);
 const project=$('videoProject'), primary=$('videoPrimary'), compare=$('videoComparePick');
 const current=$('videoPlayer'), alternate=$('videoComparePlayer');
 const model=$('videoWorkspaceModel'), mode=$('videoMode'), duration=$('videoDuration');
 const notice=(message,...values)=>OAUI.set($('videoNotice'),message,...values);
 const invoke=(action,fields={})=>call('wce.ui.video.workspace',{action,...fields});
 const scope=()=>({project_id:project.value});
 const lookup=id=>versions.find(row=>row.generation_attempt_id===id);
 const latestFailure=()=>versions[0]?.state==='FAILED'?versions[0]:null;
 const terminals=new Set(['ASSET_READY','SUBMIT_UNKNOWN','SUBMIT_REJECTED','FAILED','EXPIRED','CANCELLED','NOT_FOUND']);
 const beforeSubmit=new Set(['VIDEO_KEY_NOT_CONFIGURED','VIDEO_KEYCHAIN_ACCESS_REQUIRED','VIDEO_PROJECT_NOT_REGISTERED',
   'VIDEO_REFERENCE_DURATION_INVALID','VIDEO_ASSET_CHANGED','VIDEO_FRAME_OUTSIDE_PROJECT','VIDEO_FRAME_CHANGED',
   'VIDEO_FRAME_INVALID','VIDEO_FRAME_TOO_LARGE','INVALID_LOCAL_FILE','INVALID_TOOL_ARGUMENTS',
   'VIDEO_MODE_UNSUPPORTED','VIDEO_MODE_PARAMETERS_INVALID','VIDEO_DURATION_INVALID','VIDEO_OUTPUT_INVALID',
   'VIDEO_OUTPUT_UNSUPPORTED','VIDEO_REQUEST_TOO_LARGE']);
 let versions=[], active=false, busy=false, epoch=0, pollTimer, pendingAttempt='', selectionQueue=Promise.resolve();
 let library=[], libraryEdit=null, libraryBusy=null;
 const downloads=new Map();
 const libraryNotice=(text,...values)=>OAUI.set($('videoLibraryStatus'),text,...values);
 let draftSource='', sequence=null, flexibleDuration='5';
 const players=new WeakMap();
 function label(select,id,text){
   const opt=document.createElement('option');opt.value=id;OAUI.raw(opt,text);select.append(opt);
 }
 function clear(player){
   players.get(player)?.close();
   players.delete(player);
 }
 function projectUsage(player,row){
   const panel=$(player===current?'videoUsage':'videoCompareUsage');
   panel.hidden=!row;
   panel.replaceChildren();
   if(!row)return;
   function label(key,...values){
     const text=document.createElement('span');
     OAUI.set(text,key,...values);panel.append(text);
   }
   const usage=row.usage||{};
   const fields=[['生成 Token {0}',usage.completion_tokens],['总 Token {0}',usage.total_tokens],
                 ['联网搜索 {0} 次',usage.tool_usage?.web_search]];
   let hasCount=false;
   for(const [key,value] of fields){
     if(!Number.isSafeInteger(value)||value<0)continue;
     label(key,new Intl.NumberFormat().format(value));
     hasCount=true;
   }
   if(!hasCount)label('方舟未返回用量');
   label('实扣金额未返回');
   const billing=document.createElement('button');billing.type='button';
   OAUI.set(billing,'查看火山账单');
   billing.onclick=async()=>{try{await openBilling();}catch(_){notice('当前宿主无法打开火山账单。');}};
   panel.append(billing);
 }
 function playAsset(player,row,facts){
   clear(player);OAUI.set(facts,'');projectUsage(player,row);
   if(!row?.asset)return;
   const capture=scope(),{width,height,seconds,audio_tracks}=row.asset;
   OAUI.set(facts,'{0} × {1} · {2} 秒 · {3}',width,height,seconds,OAUI.message(audio_tracks?'预览静音，原文件有声':'无声'));
   const preview=OAFramePlayer(player,start=>invoke('preview_frames',{
      ...capture,generation_attempt_id:row.generation_attempt_id,start
   }),seconds,{
     failed:()=>OAUI.set(facts,'预览未能载入，可下载原文件。'),
     seeked:time=>{
       if(!$('videoComparison').hidden)players.get(player===current?alternate:current)?.jump(Math.floor(time*8),false);
     },
     ended:()=>{
       if(player!==current||!sequence)return;
       if(!sequence.next){previewVersions();return;}
       const next=sequence.next;
       sequence.next=null;
       playAsset(current,next,$('videoFacts'))?.play();
     }
   });
   players.set(player,preview);preview.first();return preview;
 }
 function persist(){
   const fields={...scope(),primary:primary.value};
   if(!$('videoComparison').hidden&&compare.value)fields.compare=compare.value;
   if(fields.primary)selectionQueue=selectionQueue.then(()=>invoke('select',fields)).catch(()=>{});
 }
 function previewVersions(save=true){
   sequence=null;
   if(save)persist();
   playAsset(current,lookup(primary.value),$('videoFacts'));
   const visible=!$('videoComparison').hidden;
   playAsset(alternate,visible?lookup(compare.value):null,$('videoCompareFacts'));
   controls();
   for(const button of $('videoLibraryList').querySelectorAll('button[data-video]'))
     button.setAttribute('aria-pressed',String(button.dataset.video===primary.value));
 }
 function closeLibraryEdit(){
   libraryEdit=null;
   $('videoLibraryRename').hidden=true;
   $('videoLibraryConfirm').hidden=true;
 }
 function renderLibrary(){
   const live=$('videoLibraryList'),trash=$('videoLibraryTrashList');
   live.replaceChildren();trash.replaceChildren();
   const add=(parent,label,callback)=>{
     const button=document.createElement('button');button.type='button';OAUI.set(button,label);
     button.onclick=callback;button.disabled=!!libraryBusy;parent.append(button);return button;
   };
   for(const row of library){
     const id=row.generation_attempt_id;
     const item=document.createElement('li'),info=document.createElement('div'),actions=document.createElement('div');
     actions.className='oa-video-file-actions';
     const title=document.createElement('strong');OAUI.raw(title,row.name);
     const facts=document.createElement('small');
     const storage={SAVED:'已保存到项目',HISTORY:'历史成片',COPY_PENDING:'项目副本尚未保存',COPY_CONFLICT:'项目同名文件已变化',COPY_UNAVAILABLE:'项目目录不可用'};
     OAUI.set(facts,'{0} · {1} 秒 · {2}',new Date(row.created_at*1000).toLocaleString(),row.seconds,
       OAUI.message(row.state==='READY'?storage[row.storage]:'原文件不可用'));
     info.append(title,facts);
     if(row.storage==='SAVED'){const path=document.createElement('code');OAUI.raw(path,row.project_path);info.append(path);}
     item.append(info,actions);
     if(row.trashed){
       add(actions,'恢复',()=>libraryAction('restore',id));trash.append(item);continue;
     }
     const play=add(actions,'选中播放',()=>{
       primary.value=id;primary.dispatchEvent(new Event('change'));
       current.scrollIntoView({block:'nearest'});current.focus();
     });
     play.dataset.video=id;play.disabled=play.disabled||row.state!=='READY';
     play.setAttribute('aria-pressed',String(id===primary.value));
     const download=add(actions,'下载原文件',event=>{
       if(event.isTrusted)downloadOriginal(id);
     });
     download.className='oa-video-download';download.dataset.downloadId=id;
     download.setAttribute('aria-live','polite');
     updateDownload(download,id,row.state==='READY');
     add(actions,'重命名',()=>{closeLibraryEdit();libraryEdit={id,epoch};$('videoLibraryName').value=row.name;
       $('videoLibraryRename').hidden=false;$('videoLibraryName').select();});
     add(actions,'移除',()=>{closeLibraryEdit();libraryEdit={id,epoch};$('videoLibraryConfirm').hidden=false;$('videoLibraryKeep').focus();});
     if(row.state==='READY'&&['COPY_PENDING','COPY_UNAVAILABLE'].includes(row.storage))
       add(actions,'保存到项目',()=>libraryAction('copy',id));
     if(row.state==='READY'&&row.storage==='COPY_CONFLICT')add(actions,'校验项目文件',()=>libraryAction('copy',id));
     live.append(item);
   }
   $('videoLibraryEmpty').hidden=!!live.children.length;
   $('videoLibraryTrash').hidden=!trash.children.length;
 }
 async function libraryAction(action,id,fields={}){
   if(libraryBusy||!active||!project.value)return;
   const request={epoch};libraryBusy=request;closeLibraryEdit();renderLibrary();
   try{
     const row=await invoke(action,{...scope(),generation_attempt_id:id,...fields});
     if(!active||epoch!==request.epoch)return;
     if(row.generation_attempt_id!==id)throw new Error('VIDEO_LIBRARY_RESULT');
     library=library.map(item=>item.generation_attempt_id===id?row:item);
     libraryNotice(action==='copy'?(row.storage==='SAVED'?'已保存到项目：{0}':'项目副本尚未保存，请检查项目目录。'):'',row.project_path||'');
   }catch(_){if(active&&epoch===request.epoch)libraryNotice('未能更新视频资产库。');}
   finally{if(libraryBusy===request){libraryBusy=null;if(active){renderLibrary();controls();}}}
 }
 function controls(){
   const selected=lookup(primary.value);
   updateDownload($('videoDownload'),primary.value,!!selected?.asset&&!sequence);
   $('videoAgain').disabled=busy||!selected?.asset;
   $('videoEdit').disabled=busy||!selected?.asset;
   $('videoExtend').disabled=$('videoEdit').disabled;
   $('videoSequence').hidden=!(selected?.asset&&selected.mode==='extend'&&lookup(selected.source_attempt_id)?.asset);
   $('videoCompare').disabled=!versions.some(row=>row.asset&&row.generation_attempt_id!==primary.value);
   $('videoGenerate').disabled=busy||!!pendingAttempt||!project.value;
   project.disabled=busy;
   $('videoRefresh').disabled=busy||!(pendingAttempt||latestFailure()||selected);
   const needsSource=mode.value==='edit'||mode.value==='extend';
   $('videoReferenceFallback').hidden=!needsSource;
   $('videoFirstLabel').hidden=mode.value!=='frames'&&mode.value!=='reference';
   $('videoLastLabel').hidden=mode.value!=='frames';
   OAUI.set($('videoFrameLabel'),mode.value==='reference'?'参考图':'首帧');
   $('videoDirectionLabel').hidden=mode.value!=='extend';
   model.disabled=mode.value!=='frames';
   if(model.disabled)model.selectedIndex=0;
   const fixed=model.selectedIndex!==0;
   $('videoResolution').disabled=fixed;
   $('videoAudio').disabled=fixed;
   if(fixed){$('videoResolution').value='720p';$('videoAudio').checked=false;}
   const editing=mode.value==='edit';
   duration.disabled=editing||fixed;
   duration.value=editing?'-1':fixed?'5':flexibleDuration;
   OAUI.set($('videoDurationHint'),editing?'随源片':fixed?'当前模型固定 5 秒':'4–30 秒，也可选自动');
   if(needsSource)OAUI.set($('videoSource'),'使用当前成片，画幅跟随源片。');
   else OAUI.set($('videoSource'),'');
 }
 function render(data,preferred){
   versions=data.versions;
   library=data.library||[];
   const ready=versions.filter(row=>row.asset);
   primary.replaceChildren();compare.replaceChildren();
   const counts=new Map();
   const names={frames:'首尾帧',text:'文字生成',reference:'参考图',edit:'修改画面',extend:'延长镜头'};
   for(const row of [...ready].reverse()){
     const kind=row.mode||'frames';
     counts.set(kind,(counts.get(kind)||0)+1);
     row.displayVersion=counts.get(kind);
   }
   for(const row of ready){
     for(const select of [primary,compare]){
       const option=document.createElement('option');
       option.value=row.generation_attempt_id;
       OAUI.set(option,'{0} · 第 {1} 版',OAUI.message(names[row.mode]||'首尾帧'),row.displayVersion);
       select.append(option);
     }
   }
   for(const id of [preferred,data.selection?.primary,ready[0]?.generation_attempt_id]){
     if(ready.some(row=>row.generation_attempt_id===id)){primary.value=id;break;}
   }
   const saved=data.selection?.compare;
   const alternative=ready.find(row=>row.generation_attempt_id!==primary.value);
   if(saved&&lookup(saved)?.asset&&saved!==primary.value)compare.value=saved;
   else if(alternative)compare.value=alternative.generation_attempt_id;
   $('videoComparison').hidden=!(saved&&alternative&&saved!==primary.value);
   $('videoCompare').setAttribute('aria-pressed',String(!$('videoComparison').hidden));
   renderLibrary();
   const unresolved=versions.find(row=>!terminals.has(row.state));
   const savedAttempt=loadPending();
   const existing=lookup(savedAttempt);
   if(existing&&terminals.has(existing.state))savePending('');
   pendingAttempt=(savedAttempt&&(!existing||!terminals.has(existing.state))?savedAttempt:unresolved?.generation_attempt_id)||'';
   const unknown=versions.find(row=>row.state==='SUBMIT_UNKNOWN'&&row.created_at>=ready[0]?.created_at);
   if(!unresolved){
     const latest=latestFailure()||unknown;
     if(latest)report(latest);
   }
   previewVersions(false);
   if(pendingAttempt)queuePoll(pendingAttempt);
 }
 async function refresh(preferred){
   const token=++epoch;
   closeLibraryEdit();
   try{
     await selectionQueue.catch(()=>{});
     const directory=await invoke('history');
     if(!active||epoch!==token)return;
     const saved=project.value||getProject()||directory.recent_project;
     project.replaceChildren();
     for(const item of directory.projects)label(project,item.id,item.name);
     if(directory.projects.some(item=>item.id===saved))project.value=saved;
     const data=project.value?await invoke('history',scope()):{versions:[]};
     if(!active||epoch!==token)return;
     render(data,preferred);
     if(preferred&&primary.value===preferred)persist();
     if(!project.value)notice('先在项目与 Skills 中登记项目。');
   }catch(_){if(active&&epoch===token)notice('视频工作区暂不可用。');}
 }
 function getProject(){try{return localStorage.getItem('openahoy.video.project')||'';}catch(_){return '';}}
 function loadPending(){try{return localStorage.getItem('openahoy.video.pending.'+project.value)||'';}catch(_){return '';}}
 function savePending(id){
   try{
     const key='openahoy.video.pending.'+project.value;
     if(id)localStorage.setItem(key,id);else localStorage.removeItem(key);
   }catch(_){}
 }
 function queuePoll(id){
   clearTimeout(pollTimer);
   if(active)pollTimer=setTimeout(()=>poll(id),3500);
 }
 async function poll(id){
   if(!active||busy||!id)return;
   const capture=scope(),token=epoch;
   try{
     const row=await invoke('status',{...capture,generation_attempt_id:id});
     if(!active||token!==epoch)return;
     report(row);
     if(terminals.has(row.state)){
       savePending('');pendingAttempt='';
       if(!row.query_error)await refresh(row.asset?id:null);
     }
     else if(row.query_error||row.download_error)notice('状态查询未完成，请查询原任务。');
     else queuePoll(id);
   }catch(_){if(active&&epoch===token)notice('状态查询未完成，请查询原任务。');}
 }
 function report(row){
   const states={SUBMITTED:'任务已提交。',RUNNING:'方舟正在生成。',QUEUED:'任务在方舟排队。',ASSET_READY:'新版本已保存。',
     SUBMIT_REJECTED:'方舟拒绝了任务。',SUBMIT_UNKNOWN:'提交结果未知，请查询原任务。',FAILED:'方舟任务失败。',EXPIRED:'方舟任务已过期。',CANCELLED:'任务已取消。',NOT_FOUND:'当前没有该任务的回执。',SAVE_PENDING:'视频仍待保存。'};
   if(row.rejection){const d=row.rejection;notice('{0} HTTP {1} {2} {3}',OAUI.message(states[row.state]),d.http_status,d.ark_error_code||'',d.ark_request_id||'');}
   else if(row.failure?.ark_error_code||row.query_error)notice('{0} · {1}',OAUI.message(states[row.state]),row.failure?.ark_error_code||row.query_error);
   else notice(states[row.state]||'状态查询未完成，请查询原任务。');
 }
 function startDraft(next){
   const row=lookup(primary.value);if(!row)return;
   const recipe=row.recipe;
   $('videoReferenceAsset').value='';
   draftSource=row.generation_attempt_id;
   mode.value=next==='again'?(recipe?.mode||'frames'):next;
   if(next==='again'){
     model.value=row.model;
     if(row.model===model.options[0].value&&mode.value!=='edit')flexibleDuration=String(recipe?.duration??row.duration??5);
     $('videoResolution').value=recipe?.resolution||'720p';$('videoAudio').checked=!!recipe?.audio;
     $('videoPrompt').value=recipe?.prompt||'';$('videoFirst').value=recipe?.paths[0]||'';$('videoLast').value=recipe?.paths[1]||'';
     if(mode.value==='extend')$('videoDirection').value=recipe?.direction||'after';
     if(['edit','extend'].includes(mode.value))draftSource=row.source_attempt_id||draftSource;
     $('videoReferenceAsset').value=recipe?.reference_asset||'';
     if(!recipe)notice('旧版回执只保存了素材和提示词摘要，请重新填写需要的内容。');
   }else{
     $('videoPrompt').value='';$('videoAudio').checked=false;
   }
   controls();$('videoPrompt').focus();
 }
 async function submit(event){
   if(!event.isTrusted||busy||pendingAttempt||!project.value)return;
   const prompt=$('videoPrompt').value.trim(), kind=mode.value;
   const paths=kind==='frames'?[$('videoFirst').value.trim(),$('videoLast').value.trim()]
     :kind==='reference'?[$('videoFirst').value.trim()]:[];
   const source=['edit','extend'].includes(kind)?lookup(draftSource||primary.value):null;
   if(!prompt||paths.some(path=>!path)||(['edit','extend'].includes(kind)&&!source?.asset))return notice('请补齐当前模式所需的素材和提示词。');
   const id='video-'+crypto.randomUUID(),capture=scope(),token=epoch;
   const fields={...capture,generation_attempt_id:id,prompt,mode:kind,paths,model:model.value,
                 resolution:$('videoResolution').value,duration:Number(duration.value),audio:$('videoAudio').checked};
   if(source){fields.source_attempt_id=source.generation_attempt_id;fields.source_sha256=source.asset.sha256;}
   if(source&&$('videoReferenceAsset').value.trim())fields.reference_asset=$('videoReferenceAsset').value.trim();
   if(kind==='extend')fields.direction=$('videoDirection').value;
   busy=true;pendingAttempt=id;savePending(id);controls();
   try{
     const row=await invoke('submit',fields);
     if(!active||token!==epoch)return;
     report(row);
     if(terminals.has(row.state)){savePending('');pendingAttempt='';await refresh();}
     else queuePoll(id);
   }catch(error){
     if(!active||token!==epoch)return;
     if(error.message==='VIDEO_REFERENCE_SOURCE_UNAVAILABLE'){
       savePending('');pendingAttempt='';$('videoReferenceFallback').open=true;notice('方舟原视频已不可用，需要方舟可读的素材。');
     }else if(beforeSubmit.has(error.message)){
       savePending('');pendingAttempt='';notice('未能完成视频提交。');
     }else notice('提交结果未知，请查询原任务。');
   }finally{busy=false;if(active)controls();}
 }
 for(const seconds of [-1,...Array.from({length:27},(_,idx)=>idx+4)]){
   const option=document.createElement('option');option.value=seconds;
   if(seconds===-1)OAUI.set(option,'自动');else option.textContent=seconds+' s';
   duration.append(option);
 }
 duration.value=flexibleDuration;
 duration.addEventListener('change',()=>{flexibleDuration=duration.value;});
 for(const field of [model,mode])field.addEventListener('change',()=>{draftSource='';$('videoReferenceAsset').value='';controls();});
 project.addEventListener('change',()=>{clearTimeout(pollTimer);draftSource='';versions=[];library=[];libraryBusy=null;downloads.clear();
   primary.replaceChildren();compare.replaceChildren();closeLibraryEdit();libraryNotice('');renderLibrary();previewVersions(false);
   try{localStorage.setItem('openahoy.video.project',project.value);}catch(_){}void refresh();});
 primary.addEventListener('change',()=>{draftSource='';if(compare.value===primary.value){
   const other=versions.find(row=>row.asset&&row.generation_attempt_id!==primary.value);
   compare.value=other?.generation_attempt_id||'';
 }previewVersions();});
 compare.addEventListener('change',()=>{if(compare.value===primary.value){
   const other=versions.find(row=>row.asset&&row.generation_attempt_id!==compare.value);
   if(other)primary.value=other.generation_attempt_id;
 }draftSource='';previewVersions();});
 $('videoCompare').onclick=()=>{
   const panel=$('videoComparison');
   panel.hidden=!panel.hidden;
   $('videoCompare').setAttribute('aria-pressed',String(!panel.hidden));previewVersions();
 };
 for(const [id,kind] of [['videoAgain','again'],['videoEdit','edit'],['videoExtend','extend']]){
   $(id).onclick=()=>startDraft(kind);
 }
 $('videoGenerate').addEventListener('click',submit);
 $('videoSequence').onclick=async()=>{
   const extension=lookup(primary.value),original=lookup(extension?.source_attempt_id);
   if(!extension?.asset||!original?.asset)return;
   $('videoComparison').hidden=true;$('videoCompare').setAttribute('aria-pressed','false');clear(alternate);
   const ordered=extension.recipe?.direction==='before'?[extension,original]:[original,extension];
   const plan={next:ordered[1]};
   sequence=plan;
   controls();
   playAsset(current,ordered[0],$('videoFacts'))?.play();
 };
 $('videoRefresh').onclick=()=>poll(pendingAttempt||latestFailure()?.generation_attempt_id||primary.value);
 function updateDownload(button,id,available){
   const state=downloads.get(id);
   OAUI.set(button,({pending:'正在下载…',saved:'已下载',unknown:'下载未确认'})[state?.status]||'下载原文件');
   button.title=state?.filename||'';
   button.disabled=!available||!!libraryBusy;
 }
 function updateDownloads(){
   for(const button of $('videoLibraryList').querySelectorAll('[data-download-id]')){
     const id=button.dataset.downloadId;
     updateDownload(button,id,library.some(row=>row.generation_attempt_id===id&&row.state==='READY'));
   }
   controls();
 }
 async function downloadOriginal(id){
   const row=lookup(id);
   if(!row?.asset||libraryBusy||!active)return;
   const request={epoch};libraryBusy=request;downloads.set(id,{status:'pending'});updateDownloads();
   try{
     const result=await invoke('export',{...scope(),generation_attempt_id:row.generation_attempt_id});
     if(result.state!=='EXPORTED'||result.sha256!==row.asset.sha256||result.bytes!==row.asset.bytes)throw Error();
     if(libraryBusy===request)downloads.set(id,{status:'saved',filename:result.filename});
   }catch(_){if(libraryBusy===request)downloads.set(id,{status:'unknown'});}
   finally{if(libraryBusy===request){
     libraryBusy=null;
     if(active)updateDownloads();
   }}
 }
 $('videoDownload').onclick=event=>{if(event.isTrusted&&!sequence)downloadOriginal(primary.value);};
 $('videoLibraryCancel').onclick=$('videoLibraryKeep').onclick=closeLibraryEdit;
 $('videoLibraryRename').onsubmit=event=>{
   event.preventDefault();
   if(libraryEdit?.epoch===epoch)libraryAction('rename',libraryEdit.id,{name:$('videoLibraryName').value});
 };
 $('videoLibraryRemove').onclick=()=>{if(libraryEdit?.epoch===epoch)libraryAction('trash',libraryEdit.id);};
 $('videoSettings').onclick=()=>{
   const panel=$('videoSettingsPanel');panel.hidden=!panel.hidden;
   $('videoSettings').setAttribute('aria-expanded',String(!panel.hidden));
   $('videoModel').open=!panel.hidden;if(!panel.hidden)credential.refresh();
 };
 return {open(){active=true;void refresh();},close(){active=false;epoch++;clearTimeout(pollTimer);
   sequence=null;libraryBusy=null;downloads.clear();closeLibraryEdit();
   $('videoSettingsPanel').hidden=true;$('videoModel').open=false;$('videoSettings').setAttribute('aria-expanded','false');
   clear(current);clear(alternate);}};
};
'''
