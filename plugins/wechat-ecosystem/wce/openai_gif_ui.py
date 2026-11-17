"""Independent animated GIF page in the native management app."""

HTML = '''
<section id="gifWorkspace" aria-labelledby="gifPageTitle" hidden>
<header class="oa-video-header">
<h1 id="gifPageTitle" tabindex="-1">动图生成</h1>
<div class="oa-video-header-actions">
<label class="oa-gif-project">项目<select id="gifProject"></select></label>
<button id="gifRefresh" type="button">刷新</button>
</div>
</header>
<section class="oa-gif-key">
<div class="oa-video-relay-heading"><h2>OpenAI API Key</h2><small>GPT‑Image‑2.6 Flare</small></div>
<div class="oa-gif-key-controls">
<input id="videoOpenAIGifCredential" type="password" aria-label="OpenAI API Key" maxlength="4096" autocomplete="new-password" spellcheck="false" autocapitalize="off" required disabled>
<button id="videoOpenAIGifSave" type="button" class="primary" disabled>保存 API Key</button>
</div>
<p id="videoOpenAIGifState" class="help" role="status" aria-live="polite"></p>
</section>
<div class="oa-gif-workbench">
<section class="oa-video-library" aria-labelledby="gifLibraryTitle">
<h2 id="gifLibraryTitle">项目动图</h2>
<div class="oa-video-library-items" role="region" aria-labelledby="gifLibraryTitle" tabindex="0">
<p id="gifLibraryStatus" class="help" role="status" aria-live="polite"></p>
<ul id="gifList"></ul>
</div>
</section>
<section class="oa-video-preview oa-gif-preview" aria-label="动图预览">
<div id="gifPreviewBody" hidden>
<img id="gifImage" alt="生成的动图" hidden>
<div class="oa-video-result">
<p id="gifPreviewStatus" class="help" role="status" aria-live="polite"></p>
<button id="gifDownload" class="oa-video-download" type="button" aria-live="polite" disabled>下载原文件</button>
</div>
</div>
<p id="gifPreviewEmpty" class="help">在 Codex 中选择一张项目图片并描述希望生成的动作。成品会显示在这里。</p>
</section>
</div>
</section>
'''

STYLE = '''
#gifWorkspace[hidden],#gifWorkspace [hidden]{display:none!important}
#openGifWorkspace[aria-current=page]{background:var(--management-selected,var(--line));font-weight:650}
#gifWorkspace{flex:1;display:grid;grid-template-rows:auto auto minmax(0,1fr);gap:8px;min-width:0;min-height:0}
.oa-gif-project{display:flex;align-items:center;gap:6px;margin:0;font-size:12px;min-width:0}
.oa-gif-project select{inline-size:clamp(6rem,25vw,16rem);margin:0}
.oa-gif-key{display:grid;grid-template-columns:auto minmax(0,1fr) auto;gap:5px 12px;align-items:center;padding:8px 10px;border-radius:9px;background:var(--oa-fill,var(--line))}
.oa-gif-key .oa-video-relay-heading small{color:var(--muted)}
.oa-gif-key-controls{display:flex;align-items:center;gap:6px;min-width:0}
.oa-gif-key-controls input{min-width:0;max-width:25rem;margin:0}
.oa-gif-key-controls button{flex:none}
.oa-gif-key p,.oa-gif-preview p{margin:0}
.oa-gif-workbench{display:grid;grid-template-columns:clamp(132px,21%,220px) minmax(0,1fr);min-height:0;gap:8px}
#gifList{display:grid;gap:3px}
#gifList button{display:grid;justify-items:start;text-align:start;width:100%;min-width:0;overflow-wrap:anywhere}
#gifList button[aria-pressed=true]{background:var(--oa-selection,var(--tint))}
#gifPreviewBody{display:grid;height:100%;min-height:0;grid-template-rows:minmax(0,1fr) auto;gap:6px}
#gifImage{height:100%;width:100%;min-height:0;object-fit:contain;grid-row:1}
#gifPreviewBody .oa-video-result{grid-row:2}
@media(max-width:760px){.oa-gif-key{grid-template-columns:minmax(0,1fr)}}
@media(max-width:460px){.oa-gif-workbench{grid-template-columns:minmax(0,1fr);grid-template-rows:clamp(70px,26%,116px) minmax(0,1fr)}}
'''

SCRIPT = r'''
const OAGifWorkspace=(call,credential)=>{
 const $=id=>document.getElementById(id);
 const project=$('gifProject'), list=$('gifList'), image=$('gifImage'), download=$('gifDownload');
 const workspace=(action,fields={})=>call('wce.ui.video.workspace',{action,...fields});
 const states={PROCESSING:'生成中',SUBMIT_UNKNOWN:'结果待确认',SUBMIT_REJECTED:'生成请求被拒绝',
   RESULT_RECEIVED:'已收到成品',SAVE_PENDING:'待保存到项目',NOT_SENT:'未发出请求'};
 let open=false, epoch=0, selection=0, current=null, ready=false;
 function clear(){
   selection++;current=null;ready=false;image.hidden=true;image.removeAttribute('src');
   download.disabled=true;download.removeAttribute('title');OAUI.set(download,'下载原文件');
   $('gifPreviewBody').hidden=true;$('gifPreviewEmpty').hidden=false;
 }
 async function preview(row){
   clear();current=row;
   const token=selection,fields={project_id:project.value,generation_attempt_id:row.generation_attempt_id};
   const stillSelected=()=>open&&token===selection;
   for(const button of list.querySelectorAll('button'))button.setAttribute('aria-pressed',String(button.dataset.id===row.generation_attempt_id));
   $('gifPreviewBody').hidden=false;$('gifPreviewEmpty').hidden=true;
   OAUI.set($('gifPreviewStatus'),'正在加载动图…');
   try{
     const parts=[];
     let offset=0;
     while(offset<row.asset.bytes){
       const part=await workspace('gif_chunk',{...fields,offset});
       if(!stillSelected())return;
       if(part.total!==row.asset.bytes||part.offset!==offset||!Number.isSafeInteger(part.next)||part.next<=offset||part.next>part.total
           ||(part.next<part.total&&(part.next-offset)%3!==0)||typeof part.data!=='string')throw new Error('INVALID_GIF_CHUNK');
       parts.push(part.data);offset=part.next;
     }
     OAUI.attr(image,'alt','生成的动图');
     image.src='data:image/gif;base64,'+parts.join('');
     await image.decode();
     if(!stillSelected())return;
     image.hidden=false;ready=true;download.disabled=false;
     OAUI.set($('gifPreviewStatus'),'{0} × {1} · {2} 帧',row.asset.width,row.asset.height,row.asset.frames);
   }catch(_){if(stillSelected())OAUI.set($('gifPreviewStatus'),'动图暂时无法预览。');}
 }
 async function refresh(){
   const token=++epoch, prior=current?.generation_attempt_id;
   clear();list.replaceChildren();$('gifRefresh').disabled=true;
   const status=$('gifLibraryStatus');
   OAUI.set(status,'正在加载动图…');
   try{
     const {projects}=await workspace('gif_history');
     if(!open||token!==epoch)return;
     let saved=project.value;
     try{saved=saved||localStorage.getItem('openahoy.gif.project');}catch(_){}
     project.replaceChildren(...projects.map(item=>new Option(item.name,item.id)));
     if(projects.some(item=>item.id===saved))project.value=saved;
     if(!project.value){OAUI.set(status,'先在项目与 Skills 中登记项目。');return;}
     const {gifs}=await workspace('gif_history',{project_id:project.value});
     if(!open||token!==epoch)return;
     OAUI.set(status,gifs.length?'':'这个项目还没有动图。');
     for(const row of gifs){
       const item=document.createElement('li'), button=document.createElement('button'), facts=document.createElement('small');
       button.type='button';button.dataset.id=row.generation_attempt_id;
       button.disabled=row.state!=='ASSET_READY';
       OAUI.raw(button,row.generation_attempt_id);
       if(row.state==='ASSET_READY')OAUI.set(facts,'GIF · {0} 帧',row.asset.frames);
       else OAUI.set(facts,states[row.state]||'结果待确认');
       button.append(facts);button.onclick=()=>void preview(row);item.append(button);list.append(item);
     }
     const finished=gifs.filter(row=>row.state==='ASSET_READY');
     const first=finished.find(row=>row.generation_attempt_id===prior)||finished[0];
     if(first)void preview(first);
   }catch(_){if(open&&token===epoch)OAUI.set(status,'暂时无法读取项目动图。');}
   finally{if(open&&token===epoch)$('gifRefresh').disabled=false;}
 }
 project.onchange=()=>{
   try{localStorage.setItem('openahoy.gif.project',project.value);}catch(_){}
   void refresh();
 };
 $('gifRefresh').onclick=()=>void refresh();
 download.onclick=async event=>{
   if(!event.isTrusted||!current||!ready||download.disabled)return;
   const token=selection,row=current;
   download.disabled=true;OAUI.set(download,'正在下载…');
   try{
     const result=await workspace('gif_export',{project_id:project.value,generation_attempt_id:row.generation_attempt_id});
     if(!open||token!==selection)return;
     if(result.state!=='EXPORTED'||result.sha256!==row.asset.sha256)throw new Error('GIF_EXPORT_UNAVAILABLE');
     OAUI.set(download,'已下载');download.title=result.filename;
   }catch(_){if(open&&token===selection)OAUI.set(download,'未确认下载');}
   finally{if(open&&token===selection)download.disabled=false;}
 };
 return {
   open(){open=true;credential.setOpen(true,'gif');void refresh();},
   close(){open=false;epoch++;credential.setOpen(false,'gif');clear();}
 };
};
'''
