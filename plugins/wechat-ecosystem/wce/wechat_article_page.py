"""Independent WeChat draft and published columns, with in-place draft editing."""

HTML = r'''
<section id="wechatArticlesPage" hidden data-pane="published" aria-labelledby="wechatArticlesHeading">
 <header class="wx-setup-heading"><h2 id="wechatArticlesHeading">文章与草稿</h2>
  <button id="wechatArticlesBack" type="button">返回公众号配置</button>
  <div class="wx-article-mobile" aria-label="文章分类">
   <button id="wechatArticlesPublished" type="button" aria-pressed="true">已发表</button>
   <button id="wechatArticlesDrafts" type="button" aria-pressed="false">草稿箱</button>
  </div>
 </header>
 <div id="wechatArticleColumns">
  <section data-kind="published" aria-labelledby="wechatPublishedTitle"><h3 id="wechatPublishedTitle">已发表</h3>
   <p data-state role="status"></p><ol></ol><button data-next hidden>下一页</button></section>
  <section data-kind="drafts" aria-labelledby="wechatDraftsTitle"><h3 id="wechatDraftsTitle">草稿箱</h3>
   <p data-state role="status"></p><ol></ol><button data-next hidden>下一页</button></section>
 </div>
 <div id="wechatArticleDetail" hidden>
  <div class="wx-article-detail-head"><button id="wechatArticlesListBack" type="button">返回文章列表</button>
   <button id="wechatArticleOfficial" type="button" hidden>打开微信原文</button></div>
  <p id="wechatArticlesStatus" role="status"></p>
  <div id="wechatArticlesReader"></div>
 </div>
</section>'''

STYLE = r'''
#wechatArticlesPage{min-width:0;overflow:auto;padding:4px 7px 18px}
#wechatArticlesPage .wx-setup-heading{margin-bottom:14px;flex-wrap:wrap}
#wechatArticlesPage .wx-setup-heading h2{margin:0;font-size:22px}
#wechatArticleColumns{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:16px}
#wechatArticleColumns>section{min-width:0;border-radius:16px;background:var(--surface);box-shadow:var(--oh-press);padding:12px}
#wechatArticleColumns h3{margin:0 0 10px}
#wechatArticleColumns [data-state]:empty,#wechatArticlesStatus:empty{display:none}
#wechatArticleColumns ol{list-style:none;padding:0;margin:0 0 8px;display:grid;gap:8px}
#wechatArticleColumns .wx-article-card{width:100%;min-width:0;display:flex;justify-content:start;gap:11px;
 text-align:start;white-space:normal;overflow-wrap:anywhere;min-height:56px;padding:8px 10px}
.wx-article-card img{width:52px;height:45px;object-fit:cover;border-radius:6px;flex:none}
.wx-article-card span{display:grid;gap:3px}
.wx-article-card small{font-weight:400;color:var(--muted)}
.wx-article-mobile{display:none}
.wx-article-detail-head{display:flex;gap:8px;margin:0 0 12px}
#wechatArticleDetail:not([hidden]){max-width:1000px}
#wechatArticlesReader{overflow-wrap:anywhere}
#wechatArticlesReader article{box-sizing:border-box;max-width:660px;padding:clamp(12px,3vw,26px);
 background:var(--surface);border-radius:12px;line-height:1.75}
#wechatArticlesReader img{max-width:100%;height:auto;border-radius:6px}
#wechatArticlesReader article :is(h3,h4){margin-block:12px 7px}
#wechatArticleEditor{display:grid;gap:12px;grid-template-columns:minmax(0,1fr) minmax(145px,238px);align-items:start}
#wechatArticleEditor :is(label,fieldset){display:grid;gap:6px;min-width:0;margin:0}
#wechatArticleEditor fieldset{border:0;padding:0}
#wechatArticleEditor :is(input[type=text],textarea){box-sizing:border-box;width:100%;min-height:40px}
.wx-article-body,.wx-article-fields{display:grid;gap:8px;background:var(--surface);box-shadow:var(--oh-press);
 min-width:0;padding:11px;border-radius:12px}
.wx-article-body [contenteditable]{outline-offset:2px;min-height:22px;padding:6px;background:var(--oh-surface);border-radius:5px}
.wx-article-format{display:flex;gap:6px}
.wx-article-fields [type=file]{max-width:100%;font-size:12px}
#wechatArticlesReader article[data-phone]{max-width:390px}
@media(max-width:720px){
 #wechatArticleColumns,#wechatArticleEditor{grid-template-columns:minmax(0,1fr)}
 #wechatArticlesPage[data-pane=published] [data-kind=drafts],
 #wechatArticlesPage[data-pane=drafts] [data-kind=published]{display:none}
 .wx-article-mobile{display:flex;gap:8px}
}
'''

SCRIPT = r'''
function OAWechatArticles(call,openLink,back){
 const $=id=>document.getElementById(id),ui=globalThis.OAUI,make=tag=>document.createElement(tag);
 const page=$('wechatArticlesPage'),columns=$('wechatArticleColumns'),detail=$('wechatArticleDetail'),reader=$('wechatArticlesReader');
 const status=(text,...args)=>ui.set($('wechatArticlesStatus'),text,...args);
 const drafts=new Map();
 const panes=Object.fromEntries([...columns.children].map(node=>[node.dataset.kind,{node,offset:0,next:null,run:0}]));
 let row=null,identity='',detailRun=0,activeState=null,focusOrigin=null;
 const makeKey=()=> 'article-'+[...crypto.getRandomValues(new Uint8Array(16))].map(v=>v.toString(16).padStart(2,'0')).join('');
 const direct=()=>row?.binding_provider!=='WECHAT_THIRD_PARTY';
 const broker=()=>row?.component_grant?.state==='ACTIVE'&&row.component_grant.permissions?.some(x=>x===11||x===100);
 const officialPublished=()=>row?.component_grant?.state==='ACTIVE'&&row.component_grant.permissions?.includes(7);
 const button=(text,click)=>{
   const item=make('button');item.type='button';ui.set(item,text);item.onclick=click;return item;
 };
 function link(url,image=false){
   try{
     const target=new URL(url);
     if(target.protocol!=='https:'||target.username||target.password||target.port)return null;
     if(image)return ['mmbiz.qpic.cn','mmbiz.qlogo.cn'].includes(target.hostname)?target.href:null;
     return target.hostname==='mp.weixin.qq.com'&&/^\/s(?:\/|$)/.test(target.pathname)?target.href:null;
   }catch(_){return null;}
 }
 function cover(url,alt){
   const src=link(url,true);if(!src)return null;
   const image=make('img');image.alt=alt;image.loading='lazy';image.referrerPolicy='no-referrer';image.src=src;return image;
 }
 function content(html){
   const template=make('template');template.innerHTML=html;
   const allowed=new Set(['P','DIV','SECTION','H1','H2','H3','H4','H5','H6','STRONG','B','EM','I','U','S','UL','OL','LI','BLOCKQUOTE','BR','PRE','CODE','FIGCAPTION','HR','SPAN','FIGURE']);
   const blocked=new Set(['SCRIPT','STYLE','IFRAME','OBJECT','TEMPLATE','NOSCRIPT','SVG','MATH','VIDEO','AUDIO','INPUT','BUTTON']);
   const result=document.createDocumentFragment();
   function copy(src,dst){
     if(src.nodeType===3){dst.append(document.createTextNode(src.textContent));return;}
     if(src.nodeType!==1||blocked.has(src.tagName))return;
     if(src.tagName==='IMG'){
       const image=cover(src.getAttribute('src')||src.getAttribute('data-src'),src.alt);
       if(image)dst.append(image);else if(src.alt)dst.append(document.createTextNode(src.alt));
       return;
     }
     if(src.tagName==='A'){
       const url=link(src.getAttribute('href'));
       if(url){dst.append(button(src.textContent,()=>void openLink(url)));return;}
     }
     if(!allowed.has(src.tagName)){for(const child of src.childNodes)copy(child,dst);return;}
     const node=make(src.tagName.toLowerCase());
     for(const child of src.childNodes)copy(child,node);
     dst.append(node);
   }
   for(const node of template.content.childNodes)copy(node,result);
   return result;
 }
 async function invoke(name,cid,args){
   const value=await call(name,{connection_id:cid,...args});
   if(value?.isError||!value?.structuredContent)throw Error(value?.structuredContent?.error||'UNAVAILABLE');
   return value.structuredContent;
 }
 async function allContent(name,cid,args){
   const parts=[];let offset=0,first=null;
   while(offset!==null){
     const value=await invoke(name,cid,{...args,content_offset:offset,
        ...(first&&name==='own.wechat.content'?{content_sha256:first.content_sha256}:{})});
     if(typeof value.content!=='string'||!(/^[a-f0-9]{64}$/.test(value.content_sha256))||
        (first&&value.content_sha256!==first.content_sha256))throw Error('UNAVAILABLE');
     first??=value;parts.push(value.content);
     const next=value.next_content_offset;
     if(next!==null&&(!Number.isSafeInteger(next)||next<=offset||next>2097152))throw Error('UNAVAILABLE');
     offset=next;
   }
   const content=parts.join('');
   const actual=[...new Uint8Array(await crypto.subtle.digest('SHA-256',new TextEncoder().encode(content)))]
      .map(v=>v.toString(16).padStart(2,'0')).join('');
   if(actual!==first.content_sha256)throw Error('UNAVAILABLE');
   return {...first,content};
 }
 function togglePane(kind){
   page.dataset.pane=kind;
   $('wechatArticlesPublished').setAttribute('aria-pressed',String(kind==='published'));
   $('wechatArticlesDrafts').setAttribute('aria-pressed',String(kind==='drafts'));
 }
 function listBack(){
   detailRun++;activeState=null;detail.hidden=true;columns.hidden=false;reader.replaceChildren();status('');
   focusOrigin?.focus({preventScroll:true});
 }
 function show(title,body,url,phone=false){
   const article=make('article'),heading=make('h3');heading.textContent=title;
   if(phone)article.setAttribute('data-phone','');
   article.append(heading,content(body));reader.replaceChildren(article);
   const official=$('wechatArticleOfficial');official.hidden=!url;
   official.onclick=()=>void openLink(url).catch(()=>status('当前宿主无法打开链接'));
 }
 function renderListItem(pane,{title,url,image,timestamp,position,total,load}){
   const card=button('',async()=>{
      const nav=++detailRun;focusOrigin=card;activeState=null;
      detail.hidden=false;columns.hidden=true;reader.replaceChildren();$('wechatArticleOfficial').hidden=true;
      status('正在读取文章');
      try{await load(()=>nav===detailRun);if(nav===detailRun&&$('wechatArticlesStatus').textContent==='正在读取文章')status('');}
      catch(error){if(nav===detailRun)status('文章未能读取，请返回列表重试。');}
   });
   card.className='wx-article-card';
   const thumb=cover(image,'');
   const caption=make('span'),heading=make('strong'),meta=make('small');
   heading.textContent=title;caption.append(heading);
   const date=Number.isFinite(timestamp)&&timestamp>0?new Intl.DateTimeFormat(undefined,{dateStyle:'medium'}).format(timestamp*1000):'';
   const sequence=total>1?ui.format('第 {0} 篇 / 共 {1} 篇',[position+1,total]):'';
   if(sequence||date){meta.textContent=[date,sequence].filter(Boolean).join(' · ');caption.append(meta);}
   if(thumb)card.append(thumb);card.append(caption);
   const item=make('li');item.append(card);pane.node.querySelector('ol').append(item);
 }
 async function loadList(kind,offset){
   if(!row)return;
   const pane=panes[kind],ticket=++pane.run,account=row,cid=account.connection_id;
   const following=()=>pane.run===ticket&&row?.connection_id===cid&&row?.binding_revision===account.binding_revision;
   const note=text=>ui.set(pane.node.querySelector('[data-state]'),text);
   const next=pane.node.querySelector('[data-next]');next.hidden=true;
   pane.node.querySelector('ol').replaceChildren();note('正在读取文章');
   try{
     if(kind==='published'&&officialPublished()){
       const value=await invoke('own.wechat.authorized_drafts',cid,{action:'list_published',offset});
       if(!following())return;
       if(value.state!=='OBSERVED')throw Error('UNAVAILABLE');
       pane.next=value.next_offset;
       for(const group of value.items){
         const load=async valid=>{
           const observed=await invoke('own.wechat.authorized_drafts',cid,{action:'read_published',article_id:group.article_id});
           if(!valid())return null;
           if(observed.state!=='OBSERVED')throw Error('UNAVAILABLE');
           return observed.articles;
         };
         const render=article=>{
           if(article.deleted){status('微信已删除此篇文章');return;}
           show(article.title||ui.format('已发表作品'),article.content,link(article.url));
         };
         const cards=group.articles||[{title:ui.format('查看已发表图文组')}];
         cards.forEach((article,index)=>renderListItem(pane,{
           title:article.title||ui.format('已发表作品'),timestamp:group.update_time,image:article.cover_url,
           position:index,total:cards.length,
           load:async valid=>{
             const observed=await load(valid);if(!observed)return;
             if(group.articles&&observed[index]){render(observed[index]);return;}
             reader.replaceChildren(...observed.map((item,i)=>button(item.title||ui.format('第 {0} 篇',[i+1]),()=>render(item))));
             status('');
           }
         }));
       }
     }else if(kind==='published'){
       if(!direct()){note('本号尚未获得已发表读取权限');return;}
       const value=await invoke('own.wechat.content',cid,{action:'list_published',offset,count:20});
       if(!following())return;
       if(value.error_code!==undefined)throw Error('UNAVAILABLE');
       const items=value.items||[];
       for(const group of items){
         const articles=group.content?.news_item||[];
         articles.forEach((article,i)=>renderListItem(pane,{
           title:article.title||ui.format('已发表作品'),timestamp:group.update_time,image:article.thumb_url,
           position:i,total:articles.length,load:async valid=>{
             const observed=await allContent('own.wechat.content',cid,{action:'read_published',article_id:group.article_id,index:i+1});
             if(valid())show(article.title,observed.content,link(article.url));
           },
         }));
       }
       pane.next=items.length&&offset+items.length<value.total_count?offset+items.length:null;
     }else if(broker()){
       const value=await invoke('own.wechat.authorized_drafts',cid,{action:'list',offset});
       if(!following())return;
       if(value.state!=='OBSERVED')throw Error('UNAVAILABLE');
       pane.next=value.next_offset;
       for(const entry of value.items)entry.titles.forEach((title,i)=>renderListItem(pane,{
         title,image:entry.covers?.[i],timestamp:entry.update_time,position:i,total:entry.article_count,
         load:async valid=>{
           const observed=await invoke('own.wechat.authorized_drafts',cid,{action:'read',draft_ref:entry.draft_ref});
           if(!valid())return;
           if(observed.state!=='OBSERVED'||!observed.articles[i])throw Error('UNAVAILABLE');
           show(title,observed.articles[i].content||'',null);
           status('扫码账号可在此阅读原草稿。编辑原稿请打开微信公众平台。');
           reader.append(button('打开微信公众平台',()=>void openLink('https://mp.weixin.qq.com/')));
         },
       }));
     }else if(direct()){
       const value=await invoke('own.drafts.inventory',cid,offset?{cursor:offset}:{});
       if(!following())return;
       pane.next=value.cursor??null;
       for(const group of value.groups||[]){
         const selection={inventory_handle:value.inventory_handle,index:group.index,
           expected_projection_sha256:group.projection_sha256,article_count:group.article_count};
         group.titles.forEach((title,index)=>renderListItem(pane,{
           title,image:group.covers?.[index],timestamp:group.update_time,position:index,total:group.article_count,
           load:async valid=>{
             const observed=await allContent('own.drafts.current.read',cid,{selection,article_index:index});
             if(!valid())return;
             const article=observed.articles?.[index]||{title};
             const id=identity+':'+selection.expected_projection_sha256+':'+index;
             const state=drafts.get(id)||{cid,id,selection,index,article,body:observed.content,changes:{},coverFile:null};
             drafts.set(id,state);activeState=state;edit(state);
           },
         }));
       }
     }else{note('当前公众号的草稿读取未获授权');return;}
     next.hidden=pane.next==null;
     note(pane.node.querySelector('ol').childElementCount?'':kind==='drafts'?'本号草稿箱为空':'本号暂无已发表文章');
   }catch(_){if(following())note('文章未能读取，请重试');}
 }
 function edit(state){
   const {article}=state;
   if((article.article_type&&article.article_type!=='news')||!article.thumb_media_id){
     show(article.title,state.body,null);
     status('此草稿包含需由微信处理的内容。');
     reader.append(button('打开微信公众平台',()=>void openLink('https://mp.weixin.qq.com/')));
     return;
   }
   const editor=make('form'),body=make('div'),fields=make('div'),actions=make('div');
   editor.id='wechatArticleEditor';editor.onsubmit=event=>event.preventDefault();
   body.className='wx-article-body';fields.className='wx-article-fields';actions.className='actions';
   function field(name,title,limit,multi=false){
     const label=make('label'),input=make(multi?'textarea':'input');if(!multi)input.type='text';
     input.maxLength=limit;input.value=state.changes[name]??article[name]??'';
     label.append(ui.label(title),input);fields.append(label);
     input.oninput=()=>{if(input.value===(article[name]??''))delete state.changes[name];else state.changes[name]=input.value;};
   }
   field('title','文章标题',64);field('author','作者署名',16);field('digest','文章摘要',120,true);
   const image=cover(article.thumb_url,'');if(image)fields.append(image);
   const chooser=make('label'),file=make('input');file.type='file';file.accept='image/jpeg,image/png';
   chooser.append(ui.label(state.coverFile?'已选择替换封面':'更换封面'),file);fields.append(chooser);
   file.onchange=()=>{state.coverFile=file.files[0]||null;};
   const rich=make('div'),toolbar=make('div');toolbar.className='wx-article-format';
   body.append(ui.label('正文'),toolbar,rich);
   const raw=state.changes.content??state.body, pieces=[];let pos=0;
   const gather=()=>pieces.map(piece=>piece.element?piece.open+piece.element.innerHTML+piece.close:piece.raw).join('');
   for(const match of raw.matchAll(/(<(?:p|h[2-6]|blockquote)\b[^>]*>)([\s\S]*?)(<\/(?:p|h[2-6]|blockquote)\s*>)/gi)){
     if(/<(?!\/?(?:strong|b|em|i|u|s|br)\b)[^>]*>/i.test(match[2])||/<[^>]+\s+[^>]+>/i.test(match[2]))continue;
     const before=raw.slice(pos,match.index);
     if(before.trim()){pieces.push({raw:before});rich.append(content(before));}
     else if(before)pieces.push({raw:before});
     const editable=make('div');editable.contentEditable='true';editable.setAttribute('role','textbox');editable.setAttribute('aria-label',ui.format('正文段落'));
     editable.append(content(match[2]));
     editable.addEventListener('paste',event=>{event.preventDefault();document.execCommand('insertText',false,event.clipboardData.getData('text/plain'));});
     editable.oninput=()=>{state.changes.content=gather();};
     pieces.push({open:match[1],element:editable,close:match[3]});rich.append(editable);pos=match.index+match[0].length;
   }
   const rest=raw.slice(pos);pieces.push({raw:rest});rich.append(content(rest));
   if(rich.querySelector('[contenteditable]')){
     for(const [label,command] of [['加粗','bold'],['斜体','italic']]){
       const control=button(label,()=>{document.execCommand(command);state.changes.content=gather();});
       control.onmousedown=event=>event.preventDefault();toolbar.append(control);
     }
   }else body.append(ui.label('特殊正文排版保留原样，可在微信公众平台继续编辑。'));
   const saveButton=button(state.pending?'查原保存结果':'保存到微信草稿',()=>void save(state,saveButton));
   if(state.finished)saveButton.disabled=true;
   actions.append(button('手机预览',()=>{
      show(state.changes.title??article.title,state.changes.content??state.body,null,true);
      reader.prepend(button('返回草稿编辑',()=>edit(state)));
   }),saveButton);
   fields.append(actions);editor.append(body,fields);reader.replaceChildren(editor);
 }
 async function save(state,control){
   if(state.busy||activeState!==state)return;
   const account=row?.connection_id;
   const still=()=>activeState===state&&row?.connection_id===account;
   state.busy=true;control.disabled=true;
   try{
     let result;
     if(state.pending){
       const original=await invoke('own.wechat.content',state.cid,{action:'status_by_key',request_key:state.pending});
       if(!still())return;
       result=['UNKNOWN','SAVED','READBACK_MISMATCH'].includes(original.state)?
         await invoke('own.wechat.content',state.cid,{action:'readback',operation_handle:original.operation_handle}):original;
     }else{
       const changes={...state.changes};
       if(state.coverFile){
         const file=state.coverFile;
         if(!['image/jpeg','image/png'].includes(file.type)||file.size>700*1024){status('请选 700 KB 以内的 JPG 或 PNG 封面');return;}
         let binary='';for(const byte of new Uint8Array(await file.arrayBuffer()))binary+=String.fromCharCode(byte);
         state.coverKey??=makeKey();
         const cover=await invoke('own.wechat.content',state.cid,{action:'upload_image',request_key:state.coverKey,
           source:{mime_type:file.type,base64:btoa(binary)}});
         if(!still())return;
         if(cover.state!=='UPLOADED'){status('封面上传尚未确认，草稿未提交');return;}
         changes.cover_handle=cover.operation_handle;
       }
       if(!Object.keys(changes).length){status('草稿没有改动');return;}
       const request_key=makeKey();state.pending=request_key;
       result=await invoke('own.wechat.content',state.cid,{action:'update_news',request_key,selection:state.selection,index:state.index,changes});
     }
     if(['VERIFIED','UNCHANGED'].includes(result.state)){
       drafts.delete(state.id);
       if(still()){
         listBack();ui.set(panes.drafts.node.querySelector('[data-state]'),'草稿已保存并从微信读回');
         void loadList('drafts',0);
       }
     }else if(['SOURCE_CHANGED','REJECTED'].includes(result.state)){
       state.pending=null;
       if(still())status(result.state==='SOURCE_CHANGED'?'微信草稿已改变。原填写已保留，请重新打开草稿核对。':'微信拒绝保存草稿（{0}）',result.error_code);
     }else if(still())status('原保存结果尚未确认，可查询原结果。');
   }catch(error){
     if(['WECHAT_DRAFT_EDIT_OPEN_OFFICIAL','WECHAT_DRAFT_EDIT_PRESERVE_BLOCKS','WECHAT_DRAFT_COVER_NOT_AVAILABLE','INVALID_TOOL_ARGUMENTS'].includes(error.message)){
       state.pending=null;
       if(still())status('当前内容需要在微信公众平台编辑，原填写已保留。');
     }else if(still())status('原保存结果尚未确认，可查询原结果。');
   }finally{
     state.busy=false;
     if(still()){control.disabled=state.finished===true;ui.set(control,state.finished?'已保存':state.pending?'查原保存结果':'保存到微信草稿');}
   }
 }
 $('wechatArticlesDrafts').onclick=()=>togglePane('drafts');
 $('wechatArticlesPublished').onclick=()=>togglePane('published');
 $('wechatArticlesBack').onclick=back;$('wechatArticlesListBack').onclick=listBack;
 for(const [kind,pane] of Object.entries(panes))pane.node.querySelector('[data-next]').onclick=()=>void loadList(kind,pane.next);
 return {target(value){
   const key=value?value.connection_id+':'+value.binding_revision:'';
   if(key===identity)return;
   row=value;identity=key;focusOrigin=null;listBack();
   for(const pane of Object.values(panes)){pane.run++;pane.node.querySelector('ol').replaceChildren();}
   if(row){void loadList('published',0);void loadList('drafts',0);}
 }};
}
'''
