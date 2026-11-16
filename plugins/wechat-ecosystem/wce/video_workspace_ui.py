"""The project video workspace in the existing management resource."""

HTML = '''
<section id="videoWorkspace" hidden>
<div id="videoProjectPage">
<header class="oa-video-header"><h1 id="videoPageTitle" tabindex="-1">预览与资产</h1><div class="oa-video-header-actions"><label class="oa-video-project">项目<select id="videoProject"></select></label><button id="videoRefresh" type="button">刷新成片</button><button id="videoSettings" type="button" aria-controls="videoSettingsPage">模型设置</button></div></header>
<section class="oa-video-library" aria-labelledby="videoLibraryTitle">
<h2 id="videoLibraryTitle">项目视频资产库</h2>
<div class="oa-video-library-items" role="region" aria-labelledby="videoLibraryTitle" tabindex="0">
<p id="videoLibraryEmpty" class="help">这个项目还没有成片。</p>
<ul id="videoLibraryList"></ul>
<details id="videoLibraryTrash" hidden><summary>最近移除</summary>
<ul id="videoLibraryTrashList"></ul></details>
<form id="videoLibraryRename" hidden><label>视频名称 <input id="videoLibraryName" required maxlength="120"></label>
<button class="primary" type="submit">保存名称</button><button id="videoLibraryCancel" type="button">取消</button></form>
<div id="videoLibraryConfirm" hidden><p>从资产库移除此视频？文件、生成记录和后续版本会保留，可在「最近移除」恢复。</p>
<button id="videoLibraryRemove" type="button">移除视频</button><button id="videoLibraryKeep" type="button">取消</button></div>
<p id="videoLibraryStatus" class="help" role="status" aria-live="polite"></p>
</div>
</section>
<section class="oa-video-preview" aria-label="成片">
<div id="videoPlayers"><div>
<div class="oa-video-section-head"><label class="oa-video-version">当前版本<select id="videoPrimary"></select></label><button id="videoCompare" type="button" aria-pressed="false">版本对比</button></div>
<div id="videoPlayer" class="oa-frame-player" role="group" aria-label="当前版本" tabindex="-1"></div>
<div class="oa-video-result"><div class="oa-video-meta"><p id="videoFacts"></p><details id="videoUsageDetails" class="oa-video-usage-details" hidden><summary>用量与账单</summary><div id="videoUsage" class="oa-video-usage"></div></details></div>
<div class="oa-video-file-actions"><button id="videoDownload" class="oa-video-download" type="button" aria-live="polite" disabled>下载原文件</button><button id="videoSequence" type="button" hidden>连播原片与续写</button></div></div></div>
<div id="videoComparison" hidden><div class="oa-video-section-head"><label class="oa-video-version">对比版本<select id="videoComparePick"></select></label></div>
<div id="videoComparePlayer" class="oa-frame-player" role="group" aria-label="对比版本"></div>
<div class="oa-video-result"><div class="oa-video-meta"><p id="videoCompareFacts"></p><details id="videoCompareUsageDetails" class="oa-video-usage-details" hidden><summary>用量与账单</summary><div id="videoCompareUsage" class="oa-video-usage"></div></details></div></div></div></div>
<p id="videoEmpty" class="help" hidden>这个项目还没有成片。</p>
<p id="videoNotice" class="help" role="status" aria-live="polite"></p>
</section>
</div>
<section id="videoSettingsPage" aria-labelledby="videoSettingsTitle" hidden>
<header class="oa-video-header"><h1 id="videoSettingsTitle" tabindex="-1">模型设置</h1><button id="videoSettingsBack" type="button" aria-controls="videoProjectPage">返回预览与资产</button></header>
__CREDENTIAL__
</section>
</section>
'''

STYLE = '''
#videoWorkspace{min-width:0;min-height:0;flex:1}
#videoWorkspace[hidden],#videoWorkspace [hidden],body.oa-video-open #nativeWorkspace{display:none!important}
#openVideoWorkspace[aria-current=page]{background:var(--management-selected,var(--line));font-weight:650}
#videoProjectPage{display:grid;height:100%;grid-template-columns:clamp(164px,21%,238px) minmax(0,1fr);grid-template-rows:auto minmax(0,1fr);grid-template-areas:"heading heading" "library preview";gap:10px;min-width:0}
#videoProjectPage>.oa-video-header{grid-area:heading}
.oa-video-header,.oa-video-header-actions,.oa-video-file-actions,.oa-video-section-head,.oa-video-result,.oa-video-meta{display:flex;align-items:center;gap:6px;flex-wrap:wrap}
.oa-video-header,.oa-video-section-head,.oa-video-result{justify-content:space-between}
.oa-video-header h1,.oa-video-library h2{margin:0;line-height:1.3}
.oa-video-header h1{font-size:23px}
.oa-video-library h2{font-size:15px}
#videoWorkspace :is(.oa-video-project,.oa-video-version){display:flex;align-items:center;gap:6px;min-width:0;max-width:100%;margin:0;font-size:12px}
#videoWorkspace .oa-video-project select{inline-size:clamp(8rem,20vw,16rem);max-inline-size:100%;min-height:32px;margin:0;font-size:12px}
#videoWorkspace .oa-video-version select{width:auto;max-width:100%;min-width:0;margin:0;font-size:12px}
.oa-video-preview,.oa-video-library{min-width:0;min-height:0;padding:10px 12px;border-radius:14px;background:var(--surface)}
.oa-video-preview{grid-area:preview;display:grid;grid-template-rows:minmax(0,1fr) auto;gap:6px}
.oa-video-preview p{margin:0;overflow-wrap:anywhere}
.oa-video-preview p:empty,.oa-video-library p:empty,.oa-video-library ul:empty{display:none}
#videoPlayers{display:grid;grid-template-columns:minmax(0,1fr);min-height:0;gap:10px}
#videoPlayers:has(#videoComparison:not([hidden])){grid-template-columns:repeat(2,minmax(0,1fr))}
#videoPlayers>div{display:grid;grid-template-rows:auto minmax(0,1fr) auto;gap:5px;align-items:start;min-width:0;min-height:0}
#videoPlayers .oa-frame-player{grid-template-rows:minmax(0,1fr) auto;min-height:0;height:100%}
#videoPlayers .oa-frame-screen{aspect-ratio:var(--video-ratio,16/9);height:100%;width:auto;min-width:0;min-height:0;max-width:100%;justify-self:center;align-self:center}
#videoPlayers .oa-frame-controls input{min-height:28px;padding:0;margin:0;box-shadow:none}
.oa-video-meta{column-gap:10px}
#videoPlayers :is(#videoFacts,#videoCompareFacts){font-size:12px;color:var(--muted)}
.oa-video-usage{display:flex;gap:4px 10px;flex-wrap:wrap;align-items:baseline;font-size:12px;color:var(--muted)}
.oa-video-preview .oa-video-usage-details{margin:0;position:relative}
.oa-video-usage-details:not([open])>.oa-video-usage{display:none}
#videoWorkspace :is(button,select){min-height:29px;padding:4px 8px;font-size:12px}
#videoWorkspace .oa-video-download{min-inline-size:8.5em}
#videoEmpty{align-self:center;justify-self:center}
.oa-video-library{grid-area:library;display:grid;grid-template-rows:auto minmax(0,1fr);gap:6px;padding:8px}
.oa-video-library-items{min-width:0;overflow:auto;overscroll-behavior:contain;scrollbar-gutter:stable}
.oa-video-library ul{margin:0;padding:0;list-style:none}
#videoLibraryList,#videoLibraryTrashList{display:grid;gap:2px}
.oa-video-library li{position:relative;display:grid;grid-template-columns:minmax(0,1fr) 29px;align-items:center;gap:2px;min-width:0;border-radius:7px}
#videoLibraryTrashList li{grid-template-columns:minmax(0,1fr) auto}
.oa-video-library li:has(button[aria-pressed=true]){background:var(--oa-selection,var(--tint))}
.oa-video-library li>div{min-width:0;padding:3px 5px}
.oa-video-library :is(strong,small){display:block;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.oa-video-library strong{font-size:12px;line-height:15px}
.oa-video-library small{color:var(--muted);font-size:10px;line-height:13px}
#videoWorkspace .oa-video-asset-pick{width:100%;min-width:0;min-height:32px;padding:2px 5px;text-align:start;display:block;background:transparent;overflow:hidden}
#videoWorkspace .oa-video-asset-pick:hover:not(:disabled){background:var(--oa-hover,var(--tint))}
#videoWorkspace .oa-video-library .oa-video-file-actions button{min-height:24px;font-size:11px;padding:2px 5px}
#videoWorkspace .oa-video-library .oa-video-download{min-inline-size:0}
.oa-video-library :is(form,#videoLibraryConfirm){padding:8px;background:var(--tint);border-radius:8px}
.oa-video-library input{max-width:100%}
.oa-video-library :is(details,p){margin:5px 0 0}
.oa-video-library .oa-video-asset-menu{margin:0;padding-inline-end:3px}
.oa-video-asset-menu summary{display:grid;place-items:center;min-width:26px;min-height:30px;border-radius:6px;font-size:16px;cursor:pointer}
.oa-video-asset-menu summary::-webkit-details-marker{display:none}
.oa-video-asset-menu summary:hover{background:var(--oa-hover,var(--tint))}
.oa-video-asset-menu[open]{grid-column:1/-1}
.oa-video-asset-menu[open]>summary{position:absolute;inset-block-start:0;inset-inline-end:3px}
.oa-video-asset-menu[open]>div{padding:0 5px 4px}
.oa-video-library .oa-video-asset-menu:not([open])>div{display:none}
#videoSettingsPage{max-width:600px;max-height:100%;margin-inline:auto;overflow:auto;overscroll-behavior:contain;padding:2px}
#videoModel,#videoRelayCard{margin-top:10px}
.oa-video-model-brands{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:6px;margin-block-end:12px}
.oa-video-model-brand{min-width:0;min-height:48px;display:flex;flex-wrap:wrap;align-items:center;gap:2px 7px;padding:4px 7px;border-radius:8px;background:var(--oa-fill,var(--line))}
.oa-video-model-brand img{display:block;object-fit:contain;width:86px;max-width:100%;height:auto;border-radius:4px;background:#fff}
.oa-video-model-brand strong{font-size:12px}
.oa-video-model-brand small{font-size:11px;color:var(--muted)}
#videoModel:has(option[value=ark]:checked) [data-model=seedance],#videoModel:has(:is(option[value=cn],option[value=global]):checked) [data-model=minimax]{background:var(--oa-selection,var(--tint))}
#videoCredentialForm{display:grid;grid-template-columns:minmax(0,1fr) auto;gap:5px 8px;align-items:center}
#videoCredentialForm label{grid-column:1/-1;margin:0}
#videoCredentialForm input{min-width:0;margin:0}
.oa-video-relay-heading,.oa-video-relay-footer{display:flex;align-items:center;gap:6px 9px;flex-wrap:wrap}
.oa-video-relay-heading img{width:70px;height:auto;object-fit:contain;border-radius:4px;background:#fff}
.oa-video-relay-heading h2{margin:0;font-size:15px}
#videoRelayForm{display:grid;grid-template-columns:minmax(0,1fr);gap:5px;margin-top:10px}
#videoRelayForm :is(label,input){min-width:0;margin:0}
#videoRelayOriginHint{margin:0 0 3px;font-size:12px}
.oa-video-relay-footer{justify-content:space-between;margin-top:3px}
.oa-video-relay-footer p{margin:0;font-size:12px;color:var(--muted)}

@media(max-width:799px),(max-height:599px){
 .oa-management.oa-native.oa-video-open .oa-shell{display:grid;height:100dvh;min-height:0;grid-template-columns:minmax(0,1fr);grid-template-rows:auto minmax(0,1fr);overflow:hidden}
 .oa-management.oa-native.oa-video-open .oa-sidebar{display:flex;flex-flow:row wrap;justify-content:flex-start;align-items:center;gap:4px 10px;padding:5px 10px}
 .oa-video-open .oa-sidebar>div:has(#platformNavigation),.oa-video-open .oa-sidebar .oa-nav{display:flex;flex-wrap:wrap;gap:4px}
 .oa-management.oa-native.oa-video-open .oa-sidebar .oa-nav button{min-height:28px;font-size:12px;padding:3px 6px}
 .oa-video-open .oa-sidebar .oa-brand-logo{width:96px}
 .oa-management.oa-native.oa-video-open .oa-sidebar #softwareUpdateSlot{width:auto;order:1}
 .oa-video-open .oa-sidebar .oa-software-update{padding:2px 6px;gap:4px}
 .oa-video-open .oa-sidebar .oa-support-links{display:flex;flex-wrap:wrap;gap:4px;margin:0;padding:0}
 .oa-management.oa-native.oa-video-open .oa-content{display:flex;flex-direction:column;min-height:0;overflow:hidden;padding:8px 12px 10px}
 #videoProjectPage{gap:6px}
 .oa-video-preview,.oa-video-library{padding:7px 8px}
 .oa-video-header h1{font-size:19px}
}
@media(min-width:901px) and (min-height:600px){
 .oa-video-usage-details>summary{display:none}
}
@media(max-width:900px),(max-height:599px){
 #videoWorkspace :is(.oa-video-header-actions,.oa-video-section-head){flex-wrap:nowrap}
 #videoWorkspace :is(.oa-video-project,.oa-video-version){white-space:nowrap}
 #videoWorkspace :is(.oa-video-project,.oa-video-version) select{min-width:0}
 .oa-video-meta{position:relative}
 .oa-video-preview .oa-video-usage-details{position:static}
 .oa-video-usage-details[open]>.oa-video-usage{position:absolute;bottom:calc(100% + 6px);left:0;z-index:2;width:max-content;max-width:min(240px,100%);padding:8px;border-radius:8px;background:var(--surface);box-shadow:var(--oa-popover-shadow)}
}
@media(max-width:550px){
 #videoProjectPage{grid-template-columns:minmax(0,1fr);grid-template-rows:auto clamp(92px,24%,125px) minmax(0,1fr);grid-template-areas:"heading" "library" "preview"}
 .oa-management.oa-native.oa-video-open .oa-sidebar #softwareUpdateSlot{width:calc(100% - 160px);order:0}
 .oa-video-open .oa-sidebar>div:has(#platformNavigation),.oa-video-open .oa-sidebar .oa-support-links{order:1}
 #videoWorkspace .oa-video-project select{inline-size:min(8rem,25vw)}
 #videoWorkspace .oa-video-version{flex:1 1 0}
 #videoWorkspace .oa-video-version select{flex:1;width:0}
 .oa-video-result{display:grid;grid-template-columns:minmax(0,1fr) auto;gap:4px}
 .oa-video-meta{gap:1px 6px}
 #videoPlayers:has(#videoComparison:not([hidden])) .oa-video-version{display:grid}
 #videoPlayers:has(#videoComparison:not([hidden])) .oa-video-version select{width:100%}
}
@media(max-height:460px),(max-width:550px) and (max-height:510px){
 #videoProjectPage{overflow:auto;overscroll-behavior:contain}
 #videoProjectPage>.oa-video-preview{min-height:210px}
}
@media(max-width:550px) and (max-height:510px){
 #videoProjectPage{grid-template-rows:auto 92px minmax(210px,1fr)}
}
@media(max-width:450px){#videoCredentialForm{grid-template-columns:minmax(0,1fr)}}
'''

SCRIPT = r'''
const OAVideoWorkspace = (call, credential, openBilling) => {
 const $=id=>document.getElementById(id);
 const project=$('videoProject'), primary=$('videoPrimary'), compare=$('videoComparePick');
 const current=$('videoPlayer'), alternate=$('videoComparePlayer');
 const notice=(message,...values)=>OAUI.set($('videoNotice'),message,...values);
 const invoke=(action,fields={})=>call('wce.ui.video.workspace',{action,...fields});
 const scope=()=>({project_id:project.value});
 const lookup=id=>versions.find(row=>row.generation_attempt_id===id);
 let versions=[], active=false, epoch=0, selectionQueue=Promise.resolve();
 let library=[], libraryEdit=null, libraryBusy=null;
 const downloads=new Map();
 const libraryNotice=(text,...values)=>OAUI.set($('videoLibraryStatus'),text,...values);
 let sequence=null;
 const players=new WeakMap();
 const compactUsage=matchMedia('(max-width:900px),(max-height:599px)');
 function syncUsage(){
   for(const id of ['videoUsageDetails','videoCompareUsageDetails'])$(id).open=!compactUsage.matches;
 }
 compactUsage.addEventListener('change',syncUsage);
 syncUsage();
 function label(select,id,text){
   const opt=document.createElement('option');opt.value=id;OAUI.raw(opt,text);select.append(opt);
 }
 function clear(player){
   players.get(player)?.close();
   players.delete(player);
 }
 function projectUsage(player,row){
   const panel=$(player===current?'videoUsage':'videoCompareUsage');
   panel.parentElement.hidden=!row;
   panel.parentElement.open=!compactUsage.matches;
   panel.replaceChildren();
   if(!row)return;
   function label(key,...values){
     const text=document.createElement('span');
     OAUI.set(text,key,...values);panel.append(text);
   }
   const usage=row.usage||{};
   const fields=[['生成 Token {0}',usage.completion_tokens??usage.total_tokens],
                 ['联网搜索 {0} 次',usage.tool_usage?.web_search]];
   if(row.model==='MiniMax-H3'){
     if(Number.isFinite(usage.output_seconds))label('输出 {0} 秒',usage.output_seconds);
     if(Number.isSafeInteger(usage.input_image_count))label('输入 {0} 张图',usage.input_image_count);
   }
   let hasCount=false;
   for(const [key,value] of fields){
     if(!Number.isSafeInteger(value)||value<0)continue;
     label(key,new Intl.NumberFormat().format(value));
     hasCount=true;
   }
   if(!hasCount&&!Number.isFinite(usage.output_seconds))label('供应商未返回用量');
   const estimate=row.list_price_usd??row.list_price_cny;
   if(Number.isFinite(estimate)){
     const amount=new Intl.NumberFormat(undefined,{style:'currency',currency:row.list_price_usd!==undefined?'USD':'CNY'}).format(estimate);
     label('刊例估算 {0}',amount);
   }
   if(row.model==='MiniMax-H3-Relay')return;
   const billing=document.createElement('button');billing.type='button';
   OAUI.set(billing,'查看实际账单');
   billing.onclick=async()=>{try{await openBilling(row.provider_site);}catch(_){notice('当前宿主无法打开账单。');}};
   panel.append(billing);
 }
 function playAsset(player,row,facts){
   clear(player);OAUI.set(facts,'');projectUsage(player,row);
   if(!row?.asset)return;
   const capture=scope(),{width,height,seconds,audio_tracks}=row.asset;
   OAUI.set(facts,'{0} × {1} · {2} 秒 · {3}',width,height,seconds,OAUI.message(audio_tracks?'预览静音，原文件有声':'无声'));
   player.style.setProperty('--video-ratio',width+'/'+height);
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
     const created=new Date(row.created_at*1000);
     const date=created.toLocaleString(undefined,{month:'numeric',day:'numeric',hour:'numeric',minute:'2-digit'});
     OAUI.set(facts,'{0} · {1} 秒',date,row.seconds);
     OAUI.attr(facts,'title','{0} · {1} 秒 · {2}',created.toLocaleString(),row.seconds,
       OAUI.message(row.state==='READY'?storage[row.storage]:'原文件不可用'));
     title.title=row.storage==='SAVED'?row.name+' · '+row.project_path:row.name;
     if(row.trashed){
       info.append(title,facts);item.append(info,actions);
       add(actions,'恢复',()=>libraryAction('restore',id));trash.append(item);continue;
     }
     const play=document.createElement('button');play.type='button';
     play.className='oa-video-asset-pick';
     play.append(title,facts);
     play.onclick=()=>{
       primary.value=id;primary.dispatchEvent(new Event('change'));
     };
     play.dataset.video=id;play.disabled=!!libraryBusy||row.state!=='READY';
     play.setAttribute('aria-pressed',String(id===primary.value));
     const menu=document.createElement('details'),summary=document.createElement('summary');
     summary.textContent='⋯';OAUI.attr(summary,'aria-label','{0} 的更多操作',row.name);
     menu.className='oa-video-asset-menu';
     const options=document.createElement('div');options.className='oa-video-file-actions';
     menu.append(summary,options);item.append(play,menu);
     const download=add(options,'下载',event=>{
       if(event.isTrusted)downloadOriginal(id);
     });
     download.className='oa-video-download';download.dataset.downloadId=id;
     download.setAttribute('aria-live','polite');
     updateDownload(download,id,row.state==='READY');
     add(options,'重命名',()=>{menu.open=false;closeLibraryEdit();libraryEdit={id,epoch};$('videoLibraryName').value=row.name;
       $('videoLibraryRename').hidden=false;$('videoLibraryName').focus();$('videoLibraryName').select();});
     add(options,'移除',()=>{menu.open=false;closeLibraryEdit();libraryEdit={id,epoch};$('videoLibraryConfirm').hidden=false;$('videoLibraryKeep').focus();});
     if(row.state==='READY'&&['COPY_PENDING','COPY_UNAVAILABLE'].includes(row.storage))
       add(options,'保存到项目',()=>libraryAction('copy',id));
     if(row.state==='READY'&&row.storage==='COPY_CONFLICT')add(options,'校验项目文件',()=>libraryAction('copy',id));
     live.append(item);
   }
   $('videoLibraryEmpty').hidden=!!live.children.length;
   $('videoLibraryTrash').hidden=!trash.children.length;
 }
 async function libraryAction(action,id,fields={}){
   if(libraryBusy||!active||!project.value)return;
   const request={epoch};libraryBusy=request;closeLibraryEdit();renderLibrary();controls();
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
   $('videoSequence').hidden=!(selected?.asset&&selected.mode==='extend'&&lookup(selected.source_attempt_id)?.asset);
   $('videoCompare').disabled=!versions.some(row=>row.asset&&row.generation_attempt_id!==primary.value);
   $('videoRefresh').disabled=!!libraryBusy;
   $('videoPlayers').hidden=!selected?.asset;
   $('videoEmpty').hidden=!!selected?.asset;
 }
 function render(data){
   versions=data.versions;
   library=data.library||[];
   const ready=versions.filter(row=>row.asset);
   primary.replaceChildren();compare.replaceChildren();
   const counts=new Map();
   const names={frames:'首尾帧',first:'单首帧',last:'单尾帧',text:'文字生成',reference:'多图参考',edit:'修改画面',extend:'延长镜头',workflow:'AutoDL · MiniMax H3'};
   for(const row of [...ready].reverse()){
     const kind=row.mode||'frames';
     counts.set(kind,(counts.get(kind)||0)+1);
     row.displayVersion=counts.get(kind);
   }
   for(const row of ready){
     for(const select of [primary,compare]){
       const option=document.createElement('option');
       option.value=row.generation_attempt_id;
       const modelName=row.model==='MiniMax-H3-Relay'?'AutoDL · MiniMax H3':names[row.mode]||'首尾帧';
       OAUI.set(option,'{0} · 第 {1} 版',OAUI.message(modelName),row.displayVersion);
       select.append(option);
     }
   }
   for(const id of [data.selection?.primary,ready[0]?.generation_attempt_id]){
     if(ready.some(row=>row.generation_attempt_id===id)){primary.value=id;break;}
   }
   const saved=data.selection?.compare;
   const alternative=ready.find(row=>row.generation_attempt_id!==primary.value);
   if(saved&&lookup(saved)?.asset&&saved!==primary.value)compare.value=saved;
   else if(alternative)compare.value=alternative.generation_attempt_id;
   $('videoComparison').hidden=!(saved&&alternative&&saved!==primary.value);
   $('videoCompare').setAttribute('aria-pressed',String(!$('videoComparison').hidden));
   renderLibrary();
   previewVersions(false);
 }
 async function refresh(){
   if(libraryBusy)return;
   const token=++epoch;
   closeLibraryEdit();
   notice('');
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
     render(data);
     if(!project.value)notice('先在项目与 Skills 中登记项目。');
   }catch(_){if(active&&epoch===token)notice('视频工作区暂不可用。');}
 }
 function getProject(){try{return localStorage.getItem('openahoy.video.project')||'';}catch(_){return '';}}
 project.addEventListener('change',()=>{
   document.querySelector('.oa-video-library-items').scrollTop=0;versions=[];library=[];libraryBusy=null;downloads.clear();
   primary.replaceChildren();compare.replaceChildren();closeLibraryEdit();libraryNotice('');renderLibrary();previewVersions(false);
   try{localStorage.setItem('openahoy.video.project',project.value);}catch(_){}void refresh();});
 primary.addEventListener('change',()=>{if(compare.value===primary.value){
   const other=versions.find(row=>row.asset&&row.generation_attempt_id!==primary.value);
   compare.value=other?.generation_attempt_id||'';
 }previewVersions();});
 compare.addEventListener('change',()=>{if(compare.value===primary.value){
   const other=versions.find(row=>row.asset&&row.generation_attempt_id!==compare.value);
   if(other)primary.value=other.generation_attempt_id;
 }previewVersions();});
 $('videoCompare').onclick=()=>{
   const panel=$('videoComparison');
   panel.hidden=!panel.hidden;
   $('videoCompare').setAttribute('aria-pressed',String(!panel.hidden));previewVersions();
 };
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
 $('videoRefresh').onclick=()=>void refresh();
 function updateDownload(button,id,available){
   const state=downloads.get(id);
   const caption=({pending:'正在下载…',saved:'已下载',unknown:'下载未确认'})[state?.status];
   OAUI.set(button,caption||(button.dataset.downloadId?'下载':'下载原文件'));
   OAUI.attr(button,'aria-label',caption||'下载原文件');
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
   const request={};libraryBusy=request;downloads.set(id,{status:'pending'});updateDownloads();
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
 function settings(open,focus=true){
   $('videoProjectPage').hidden=open;
   $('videoSettingsPage').hidden=!open;
   if(open){
     for(const player of [current,alternate])players.get(player)?.pause();
   }
   credential.setOpen(open);
   if(focus)$(open?'videoSettingsTitle':'videoSettings').focus();
 }
 $('videoSettings').onclick=()=>settings(true);
 $('videoSettingsBack').onclick=()=>settings(false);
 return {open(){active=true;void refresh();},close(){active=false;epoch++;
   sequence=null;libraryBusy=null;downloads.clear();closeLibraryEdit();
   settings(false,false);
   clear(current);clear(alternate);}};
};
'''
