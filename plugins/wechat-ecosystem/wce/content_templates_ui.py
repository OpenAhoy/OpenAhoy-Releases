"""Optional bundled material UI, isolated from the accepted account layout."""
HTML = r'''
<section id="creativeTemplates" class="panel" hidden aria-label="创作模板">
<div class="template-top"><div><h3>官方创作模板</h3><p class="help">Jiusera 维护 · 可选创作方案。新模板随插件更新，使用左侧全局「检查更新」。</p></div><button id="templateReload">刷新模板</button></div>
<p id="templateNotice" class="notice" role="status" aria-live="polite"></p>
<div id="templateCards" class="template-cards"></div>
<section id="templatePreview" hidden aria-label="模板效果预览">
<header class="template-preview-header"><div><strong>草稿效果预览</strong><span>只读演示</span></div><button id="templateClose">返回模板</button></header>
<div class="template-draft-workspace">
<aside class="template-preview-sidebar" aria-label="草稿及发布后样式">
<div class="template-draft-card"><div id="templateAccount" class="template-account-name"></div><div class="template-draft-cover"><img id="templateDraftCover" alt="草稿封面"><div id="templateDraftTitle"></div></div><div class="template-draft-caption">草稿封面</div></div>
<section class="template-published-example" aria-label="发布后宽图卡片"><h4>发布后 · 宽图</h4><div class="template-published-wide"><div class="template-published-meta"><span id="templateWideAccount"></span><span>发布后</span></div><div class="template-published-row"><p id="templateWideTitle"></p><img id="templateWideCover" alt="发布后宽图 · 2.35:1"></div></div><p class="template-crop-note">2.35:1 · 完整封面</p></section>
<section class="template-published-example" aria-label="发布后方图卡片"><h4>发布后 · 方图</h4><div id="templateSquareAccount" class="template-square-account"></div><div class="template-published-square"><img id="templateSquareCover" alt="发布后方图 · 同图最左侧1:1"><p id="templateSquareTitle"></p></div><p class="template-crop-note">1:1 · 同一封面最左侧选区</p></section>
</aside>
<main class="template-draft-paper" aria-label="公众号文章草稿预览"><div class="template-paper-scroll"><div class="template-paper-content"><header class="template-article-heading"><h1 id="templateArticleTitle"></h1><p id="templateArticleAuthor"></p></header><div id="templateArticle" class="template-article"></div></div></div><footer class="template-paper-footer"><span id="templateWordCount"></span><span>模板预览 · 不保存或发布</span></footer></main>
</div>
</section>
<p class="help">应用只补充文风、配图、排版和模板引用；保留本号作者、选题、已有自定义内容及其他字段。下载不保存配置，不改旧稿或在途任务。</p>
</section>
'''
STYLE = r'''
.template-top{display:flex;align-items:center;justify-content:space-between;gap:12px}.template-top h3{margin:0}.template-top .help{margin:4px 0 0}.template-cards{display:grid;gap:12px;margin:12px 0}.template-card{display:grid;grid-template-columns:148px minmax(0,1fr);gap:16px;padding:14px;border:1px solid var(--line);border-radius:10px}.template-card img{display:block;width:100%;aspect-ratio:2.35;object-fit:cover;border-radius:6px}.template-card h3{margin:0 0 5px}.template-card .help{margin:6px 0}.template-target{color:var(--accent);font-size:12px}.template-card .actions{margin-top:10px}#creativeTemplates{min-height:0;overflow:auto}
#creativeTemplates.template-previewing{padding:0;background:#f5f5f5;overflow:hidden}#creativeTemplates.template-previewing>.template-top,#creativeTemplates.template-previewing>.notice,#creativeTemplates.template-previewing>.template-cards,#creativeTemplates.template-previewing>.help{display:none}
#templatePreview:not([hidden]){height:calc(100dvh - 215px);min-height:460px;display:grid;grid-template-rows:auto minmax(0,1fr);color:#333;font-family:-apple-system,BlinkMacSystemFont,"PingFang SC","Microsoft YaHei",sans-serif}
.template-preview-header{display:flex;align-items:center;justify-content:space-between;gap:12px;min-height:52px;padding:10px 20px;background:#fff;border-bottom:1px solid #ededed}.template-preview-header strong{font-size:14px;font-weight:600}.template-preview-header span{margin-left:12px;color:#999;font-size:12px}.template-preview-header button{font-size:12px;padding:6px 12px;min-height:30px}
.template-draft-workspace{display:grid;grid-template-columns:280px minmax(0,768px);justify-content:center;gap:clamp(24px,4vw,88px);padding:24px;min-height:0;overflow:hidden;align-items:start}.template-preview-sidebar{min-width:0;max-height:100%;overflow:auto;scrollbar-width:thin;padding-bottom:8px}.template-draft-card{background:#fff;border:1px solid #eee;border-radius:4px;overflow:hidden}.template-account-name{font-size:13px;padding:12px 14px;color:#555}.template-draft-cover{position:relative;border:1px solid #07c160}.template-draft-cover img{display:block;width:100%;aspect-ratio:2.35;object-fit:cover}.template-draft-cover>div{position:absolute;inset:auto 0 0;padding:9px 12px;color:#fff;background:#0008;font-size:13px;line-height:1.4}.template-draft-caption{padding:14px;text-align:center;color:#999;font-size:12px}
.template-published-example{margin:22px 0 0}.template-published-example h4{font-size:12px;line-height:1.5;font-weight:500;color:#666;margin:0 0 9px}.template-published-wide{padding:12px;background:#ededee;border-radius:7px}.template-published-meta{display:flex;justify-content:space-between;align-items:center;gap:8px;font-size:11px;color:#85858a;margin-bottom:7px}.template-published-meta>span:first-child,.template-square-account{color:#426187}.template-published-row{display:grid;grid-template-columns:minmax(0,1fr) 96px;align-items:center;gap:12px}.template-published-row p,.template-published-square p{margin:0;font-size:13px;line-height:1.55;font-weight:400;color:#191919;overflow-wrap:anywhere}.template-published-row img{display:block;width:96px;aspect-ratio:2.35;object-fit:cover}.template-square-account{font-size:12px;margin-bottom:8px}.template-published-square{display:grid;grid-template-columns:50px minmax(0,1fr);gap:10px;align-items:center;padding:9px;background:#ededee;border-radius:6px}.template-published-square img{display:block;width:50px;height:50px;object-fit:cover;object-position:left center}.template-crop-note{font-size:11px;color:#999;margin:7px 0 0}
.template-draft-paper{display:grid;grid-template-rows:minmax(0,1fr) auto;min-width:0;width:100%;height:100%;background:#fff;border-radius:4px;border:1px solid #eee;overflow:hidden}.template-paper-scroll{min-height:0;overflow:auto;scrollbar-width:thin;overscroll-behavior:contain}.template-paper-content{padding:54px clamp(24px,5vw,80px) 32px}.template-article-heading{padding:0 16px;margin:0 0 8px}.template-article-heading h1{margin:0 0 12px;color:#333;font-size:24px;line-height:1.4;font-weight:600;overflow-wrap:anywhere}.template-article-heading p{margin:0;color:#9a9a9a;font-size:14px;line-height:1.5}.template-article{width:100%;background:#fff}.template-paper-footer{display:flex;justify-content:space-between;gap:12px;padding:15px 20px;border-top:1px solid #f3f3f3;color:#999;font-size:12px}
@media(max-width:1000px){.template-draft-workspace{grid-template-columns:230px minmax(0,1fr);gap:18px;padding:18px}.template-paper-content{padding:36px 20px 24px}.template-article-heading h1{font-size:22px}}
@media(min-width:701px) and (max-height:800px){.template-draft-workspace{grid-template-columns:240px minmax(0,768px);gap:24px;padding:18px}.template-draft-caption{display:none}.template-account-name{padding:6px 12px}.template-published-example{margin-top:12px}.template-published-example h4{margin-bottom:5px}.template-published-wide{padding:9px}.template-square-account{margin-bottom:5px}.template-published-square{padding:6px;grid-template-columns:44px minmax(0,1fr)}.template-published-square img{width:44px;height:44px}.template-crop-note{margin-top:4px;font-size:10px}}
@media(max-width:700px){#templatePreview:not([hidden]){height:auto;min-height:0}.template-draft-workspace{grid-template-columns:minmax(0,1fr);overflow:visible;padding:14px;gap:20px}.template-preview-sidebar{max-height:none;overflow:visible;display:grid;grid-template-columns:1fr 1fr;gap:14px}.template-draft-card{grid-column:1/-1;width:min(300px,100%)}.template-published-example{margin:0;min-width:0}.template-draft-paper{height:680px}.template-paper-content{padding:30px 10px}.template-published-row{grid-template-columns:minmax(0,1fr);gap:8px}.template-published-row img{width:100%}.template-published-square{grid-template-columns:44px minmax(0,1fr);gap:8px}.template-published-square img{width:44px;height:44px}#creativeTemplates.template-previewing{overflow:auto}.template-preview-header{padding:10px 14px}.template-paper-footer{padding:12px}.template-preview-header span{margin-left:8px}}
@media(max-width:560px){.template-card{grid-template-columns:1fr;gap:10px}.template-card>img{max-width:280px}.template-card .actions button{flex:1}.template-top{align-items:flex-start}}
'''
SCRIPT = r'''
window.OACreativeTemplates={mount(rules,host){
 'use strict';
 const $=id=>document.getElementById(id),decode=new TextDecoder('utf-8',{fatal:true});
 let ready=false,busy=false,reloadPending=false,epoch=0,catalog=null,downloadUnknown=new Set(),lastTarget='';
 const hash=async bytes=>[...new Uint8Array(await crypto.subtle.digest('SHA-256',bytes))].map(v=>v.toString(16).padStart(2,'0')).join('');
 const ui=globalThis.OAUI;
 const set=(node,text,...values)=>{if(ui)ui.set(node,text,...values);else node.textContent=text.replace(/\{(\d+)\}/g,(match,i)=>values[i]??match);};
 const say=(text,...values)=>set($('templateNotice'),text,...values);
 const target=()=>host.templateTarget?.()||null;
 const pin=m=>({template_id:m.id,version:m.version,manifest_sha256:m.manifest_sha256});
 async function read(args){const v=await host.templateCall('own.templates.read',args);if(v?.isError||!v?.structuredContent)throw Error(v?.structuredContent?.error||'TEMPLATE_UNAVAILABLE');return v.structuredContent;}
 async function bytes(m,file,entry){
  const parts=[];let size=0;
  for(let index=0;index<entry.chunks;index++){
   const p=await read({...pin(m),view:'part',file,index});
   const chunk=Uint8Array.from(atob(p.base64),c=>c.charCodeAt(0));
   if(p.file!==file||p.index!==index||p.manifest_sha256!==m.manifest_sha256||await hash(chunk)!==p.sha256)throw Error('TEMPLATE_CHANGED');
   parts.push(chunk);size+=chunk.length;
  }
  const out=new Uint8Array(size);let n=0;for(const p of parts){out.set(p,n);n+=p.length;}
  if(size!==entry.bytes||await hash(out)!==entry.sha256)throw Error('TEMPLATE_INCOMPLETE');return out;
 }
 function release(){$('templatePreview').hidden=true;$('creativeTemplates').classList.remove('template-previewing');$('templateArticle').shadowRoot?.replaceChildren();for(const id of ['templateDraftCover','templateWideCover','templateSquareCover'])$(id).removeAttribute('src');}
 async function image(m,item){
  // Inline verified package bytes: blob URLs are not portable across MCP App
  // sandbox origins/CSP. Chunked conversion avoids argument-stack limits.
  const raw=await bytes(m,item.file,m.files[item.file]);let binary='';
  for(let i=0;i<raw.length;i+=32768)binary+=String.fromCharCode(...raw.subarray(i,i+32768));
  return 'data:'+item.mime+';base64,'+btoa(binary);
 }
 async function preview(m){
  release();const captured=epoch;const html=decode.decode(await bytes(m,'example/source.html',m.files['example/source.html']));
  const doc=new DOMParser().parseFromString(html,'text/html'),images=new Map();
  const meta=m.files['example/metadata.json']?JSON.parse(decode.decode(await bytes(m,'example/metadata.json',m.files['example/metadata.json']))):{};
  for(const item of m.assets)images.set('../'+item.file,await image(m,item));
  if(captured!==epoch||!ready){release();return;}
  // Rebuild a strict, inert subset. No scripts, frame, custom elements, links,
  // event attributes, external URLs or style url() enter the host document.
  const tags=new Set(['SECTION','P','H2','STRONG','IMG']);
  const styles=new Set(['padding','font-family','background','margin','font-size','line-height','letter-spacing','font-weight','color','display','width','height']);
  function copy(node){
   if(node.nodeType===3)return document.createTextNode(node.textContent);
   if(node.nodeType!==1||!tags.has(node.tagName))throw Error('TEMPLATE_PREVIEW_UNSUPPORTED');
   const out=document.createElement(node.tagName.toLowerCase());
   for(const a of node.attributes)if(!['style','src','alt'].includes(a.name))throw Error('TEMPLATE_PREVIEW_UNSUPPORTED');
   for(const declaration of (node.getAttribute('style')||'').split(';')){if(!declaration.trim())continue;const colon=declaration.indexOf(':'),property=declaration.slice(0,colon).trim().toLowerCase(),val=declaration.slice(colon+1).trim();if(colon<1||!styles.has(property)||/[\\]|url\s*\(|expression\s*\(|@/i.test(val))throw Error('TEMPLATE_PREVIEW_UNSUPPORTED');out.style.setProperty(property,val);}
   if(node.tagName==='IMG'){if(!images.has(node.getAttribute('src')))throw Error('TEMPLATE_PREVIEW_UNSUPPORTED');out.src=images.get(node.getAttribute('src'));out.alt=node.getAttribute('alt')||'';}
   for(const child of node.childNodes)out.append(copy(child));return out;
  }
  const root=$('templateArticle').shadowRoot||$('templateArticle').attachShadow({mode:'open'});root.replaceChildren();for(const node of doc.body.childNodes)root.append(copy(node));
  const title=typeof meta.title==='string'?meta.title:m.name,author=typeof meta.author==='string'?meta.author:'',account=target()?.name||'演示公众号';
  const cover=images.get('../'+(meta.cover||m.assets[0].file));if(!cover)throw Error('TEMPLATE_PREVIEW_UNSUPPORTED');
  for(const id of ['templateDraftCover','templateWideCover','templateSquareCover'])$(id).src=cover;
  for(const id of ['templateDraftTitle','templateWideTitle','templateSquareTitle','templateArticleTitle'])$(id).textContent=title;
  for(const id of ['templateAccount','templateWideAccount','templateSquareAccount'])$(id).textContent=account;
  if(author){if(ui)ui.raw($('templateArticleAuthor'),author);else $('templateArticleAuthor').textContent=author;}else set($('templateArticleAuthor'),'请输入作者');
  set($('templateWordCount'),'正文字数 {0}',Array.from(doc.body.textContent.replace(/\s/g,'')).length);
  $('templatePreview').hidden=false;$('creativeTemplates').classList.add('template-previewing');$('creativeTemplates').scrollTop=0;
  say('同包HTML与配图的草稿式预览；实际发布显示以微信为准。');
 }
 async function download(m){
  const key=m.id+'@'+m.version+'#'+m.manifest_sha256;
  // An uncertain dispatch is queried only, never retried via another surface.
  const queryOnly=downloadUnknown.has(key);
  const result=await host.templateDownload(m,()=>bytes(m,'@bundle',m.bundle),{queryOnly,onDispatch:()=>downloadUnknown.add(key)});
  if(result?.state==='TEMPLATE_EXPORTED'){if(result.sha256!==m.bundle.sha256||result.bytes!==m.bundle.bytes||result.destination!=='Downloads')throw Error('TEMPLATE_DOWNLOAD_UNKNOWN');downloadUnknown.delete(key);say('已保存到下载文件夹：'+result.filename);}
  else if(result?.state==='HOST_DOWNLOAD_REJECTED'){downloadUnknown.delete(key);say('宿主拒绝了下载，可再次点击。');}
  else if(result?.state==='HOST_DOWNLOADED'){downloadUnknown.delete(key);say('宿主已接受模板包下载，请查看下载结果。');}
  else if(result?.state==='TEMPLATE_EXPORT_NOT_FOUND'){downloadUnknown.delete(key);say('未找到原下载文件；没有自动重写，可再次点击下载。');}
  else if(result?.state==='HOST_DOWNLOAD_UNCONFIRMED')say('宿主下载结果待确认，请查看下载目录。');
  else say('下载结果待确认，点击下载只查询原文件，不重复写入。');
 }
 async function run(fn){if(!ready||busy)return;busy=true;buttons();try{await fn();}catch(e){say('未完成：'+e.message+'。请核对原操作结果，不要重复提交。');}finally{busy=false;buttons();if(reloadPending&&ready){reloadPending=false;void load();}}}
 function buttons(){for(const el of $('templateCards').querySelectorAll('button'))el.disabled=!ready||busy||(el.dataset.apply==='true'&&!target());$('templateReload').disabled=!ready||busy;}
 async function load(){
  if(!ready||busy)return;const captured=++epoch;busy=true;buttons();say('正在读取官方模板与已选版本…');
  try{
   const c=await read({view:'catalog'}),t=target();let refs=[];
   if(t)refs=(await read({view:'selected',connection_id:t.connection_id})).templates;
   const materials=[];for(const row of c.templates){const m=await read({view:'manifest',template_id:row.id,version:row.version});if(m.manifest_sha256!==row.manifest_sha256||m.manifest_file.sha256!==row.manifest_sha256)throw Error('TEMPLATE_CHANGED');const original=JSON.parse(decode.decode(await bytes(m,'manifest.json',m.manifest_file)));if(original.id!==row.id||original.version!==row.version)throw Error('TEMPLATE_CHANGED');materials.push({...original,manifest_sha256:row.manifest_sha256,manifest_file:m.manifest_file,bundle:m.bundle});}
   if(captured!==epoch||!ready)return;
   release();$('creativeTemplates').scrollTop=0;$('templateCards').replaceChildren();catalog=c;
   for(const m of materials){
    const card=document.createElement('article');card.className='template-card';
    const cover=document.createElement('img');cover.src=await image(m,m.assets[0]);cover.alt=m.name+'封面演示';
    if(captured!==epoch||!ready)return;
    const body=document.createElement('div'),title=document.createElement('h3'),desc=document.createElement('p'),change=document.createElement('p'),state=document.createElement('p'),actions=document.createElement('div');
    set(title,'{0} · {1} · Jiusera官方',m.name,m.version);desc.textContent=m.description;desc.className='help';change.textContent=m.changelog.join(' ');change.className='help';state.className='template-target';
    const prior=refs.filter(r=>r.id===m.id).at(-1);set(state,!t?'预览和下载无需绑定；应用前请选择公众号。':prior?.manifest_sha256===m.manifest_sha256?'「{0}」已采用此版本':prior?'「{0}」已有 {1}；此版本可用，应用后保留已有自定义。':'应用目标：「{0}」',t?.name,prior?.version);actions.className='actions';
    for(const [text,action,apply] of [['预览效果',()=>preview(m),false],['下载完整模板',()=>download(m),false],['应用到此公众号',async()=>{const chosen=target();if(!chosen)throw Error('TEMPLATE_ACCOUNT_REQUIRED');const out=await rules.applyTemplate(m,{connection_id:chosen.connection_id,name:chosen.name,isCurrent:chosen.isCurrent});if(out?.verified||out?.alreadyApplied){set(state,'「{0}」已采用此版本',chosen.name);say(out.alreadyApplied?'本号已采用此版本，没有重复追加。':'模板已应用，八项有效规则及继承关系已独立读回。');}else say(out?.pending?'原保存结果待确认，请在生产规则中查询原操作，不要重复应用。':'应用尚未确认，请查看生产规则提示。');},true]]){
     const b=document.createElement('button');set(b,text);b.dataset.apply=String(apply);if(apply)b.className='primary';b.addEventListener('click',()=>run(action));actions.append(b);
    }
    body.append(title,desc,change,state,actions);card.append(cover,body);$('templateCards').append(card);
   }
   say(materials.length?'模板随插件发布更新；升级不自动覆盖本号设置。应用前请核对下方变更范围。':'当前没有可用模板。');
  }catch(e){if(captured===epoch)say('模板暂不可用：{0}；现有生产规则及发文通路不受影响。',e.message);}
  finally{busy=false;buttons();if(reloadPending&&ready){reloadPending=false;void load();}}
 }
 async function featured(){
   const list=await read({view:'catalog'}),row=list.templates?.[0];
   if(!row)return null;
   const data=await read({view:'manifest',template_id:row.id,version:row.version});
   if(data.manifest_sha256!==row.manifest_sha256||data.manifest_file.sha256!==row.manifest_sha256)
     throw Error('TEMPLATE_CHANGED');
   const material=JSON.parse(decode.decode(await bytes(data,'manifest.json',data.manifest_file)));
   if(material.id!==row.id||material.version!==row.version)throw Error('TEMPLATE_CHANGED');
   return {...material,manifest_sha256:row.manifest_sha256};
 }
 async function refreshTarget(){const cid=target()?.connection_id||'';if(cid!==lastTarget){lastTarget=cid;epoch++;if(busy)reloadPending=true;else if(!$('creativeTemplates').hidden)await load();}}
 $('templateReload').addEventListener('click',()=>load());
 $('templateClose').addEventListener('click',()=>{release();if(!$('templateCards').childElementCount)void load();});
 return {setReady(value){ready=value;if(!value){epoch++;release();}buttons();},show(){return load();},featured,previewFeatured(){return run(async()=>{
   const material=await featured();
   if(!material)throw Error('TEMPLATE_UNAVAILABLE');
   return preview(material);
 });},targetChanged(){void refreshTarget();},dispose(){ready=false;epoch++;release();}};
}};
'''
