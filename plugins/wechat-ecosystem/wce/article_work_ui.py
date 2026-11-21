"""The account-owned article stage shared by canvas, monitor and asset library."""

STYLE = '''
#articleWork:not([hidden]),.aw-asset-detail:not([hidden]){
 display:grid;grid-template-rows:auto minmax(0,1fr);min-width:0;min-height:0;gap:10px;
}
#articleWork[hidden],.aw-asset-detail[hidden]{display:none!important}
[data-workbench=canvas] #articleWork{
 position:fixed;inset:var(--wb-top) 10px var(--wb-dock);z-index:4;
}
.aw-head{display:flex;align-items:flex-start;justify-content:space-between;gap:8px;padding:0 8px;min-width:0}
.aw-controls{display:flex;gap:8px;align-items:center;min-width:0}
.aw-head h2{font-size:17px;line-height:1.2;overflow-wrap:anywhere;margin:0}
.aw-meta{color:var(--muted);font-size:12px;margin:3px 0 0}
.aw-body{display:grid;grid-template-columns:minmax(145px,240px) minmax(0,1fr);gap:12px;min-height:0}
.aw-reader{min-width:0;min-height:0;display:grid;place-items:stretch center;background:var(--soft);
 border-radius:13px;overflow:hidden;border:1px solid var(--line)}
.aw-reader iframe{width:min(100%,420px);height:100%;display:block;border:0;background:#fff}
.aw-outline{min-height:0;overflow:auto;align-content:start;display:grid;gap:5px;padding:5px 1px}
.aw-outline button{text-align:start;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;min-width:0}
.aw-outline button[aria-pressed=true]{background:var(--oa-selection,var(--tint));border-color:var(--line)}
.aw-receipts{font-size:12px;color:var(--muted);max-height:100%;overflow:auto}
.aw-receipts summary{font-weight:650;cursor:pointer}
.aw-receipts a{color:inherit}
.aw-error{padding:12px;color:var(--muted)}
[data-workbench=monitor] #articleWork .aw-body{grid-template-columns:minmax(0,1fr) minmax(180px,25%)}
[data-workbench=monitor] #articleWork .aw-reader{grid-row:1;grid-column:1}
[data-workbench=monitor] #articleWork .aw-outline{grid-row:1;grid-column:2}
.aw-asset-detail{min-height:0}
.aw-asset-detail .aw-body{grid-template-columns:minmax(0,1fr)}
.aw-asset-detail .aw-outline{display:none}
.aw-library{display:grid;grid-template-columns:minmax(170px,28%) minmax(0,1fr);gap:12px;height:100%;min-height:0}
.aw-list{min-height:0;overflow:auto;display:grid;align-content:start;gap:6px}
.aw-list button{text-align:start;min-width:0;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
@media(max-width:650px){
 .aw-head{align-items:center;padding:0 1px}
 .aw-head h2{font-size:14px}
 .aw-head .aw-meta{font-size:10px;line-height:1.2}
 .aw-controls{font-size:11px;gap:4px}
 .aw-controls .aw-receipts{font-size:11px}
 .aw-controls select{max-width:113px}
 .aw-body{grid-template-columns:minmax(0,1fr);grid-template-rows:auto minmax(0,1fr);gap:5px}
 .aw-outline{display:flex;gap:4px;overflow:auto;padding:2px;max-height:65px}
 .aw-outline button{flex:none;max-width:160px}
 [data-workbench=monitor] #articleWork .aw-body{grid-template-columns:minmax(0,1fr)}
 [data-workbench=monitor] #articleWork .aw-reader{grid-row:2;grid-column:1}
 [data-workbench=monitor] #articleWork .aw-outline{grid-row:1;grid-column:1}
 .aw-library{grid-template-columns:minmax(0,1fr);grid-template-rows:auto minmax(0,1fr)}
 .aw-list{max-height:100px}
}
'''

SCRIPT = r'''
function OAArticleWork(root, read, media, openURL){
 const $=(tag,cls)=>Object.assign(document.createElement(tag),{className:cls||''});
 const label=(tag,value,cls)=>{const el=$(tag,cls);el.textContent=value;return el;};
 const head=$('header','aw-head'), heading=$('div'), title=$('h2'), meta=$('p','aw-meta');
 const controls=$('div','aw-controls'),versions=$('select');
 const body=$('div','aw-body'), outline=$('nav','aw-outline'), reader=$('div','aw-reader');
 const frame=$('iframe'), receipts=$('details','aw-receipts'), delivery=$('div');
 const viewState=new Map(), mediaURLs=[];
 const positionKey=key=>'jiusera.article-position:'+root.id+':'+key;
 function position(key){
   if(viewState.has(key))return viewState.get(key);
   try{return JSON.parse(localStorage.getItem(positionKey(key)))||{};}catch(_){return {};}
 }
 let loaded=null, active='', revision='', pending=0, deliveryKey='', selectedVersion='', versionKey='', scrollTimer;
 frame.title=OAUI.format('文章排版预览');
 frame.setAttribute('sandbox','allow-same-origin');
 outline.setAttribute('aria-label',OAUI.format('文章内容'));
 receipts.append(label('summary',OAUI.format('交付回执')),delivery);
 heading.append(title,meta);controls.append(versions,receipts);head.append(heading,controls);
 versions.setAttribute('aria-label',OAUI.format('稿件版本'));
 reader.append(frame);body.append(outline,reader);root.append(head,body);
 function reset(){
   loaded=null;revision='';deliveryKey='';versionKey='';selectedVersion='';pending++;
   frame.onload=null;frame.removeAttribute('srcdoc');
   for(const url of mediaURLs.splice(0))URL.revokeObjectURL(url);
   outline.replaceChildren();delivery.replaceChildren();
 }
 function remember(){
   if(!active||!loaded)return;
   const doc=frame.contentDocument;
   if(doc?.scrollingElement)loaded.scroll=doc.scrollingElement.scrollTop;
   const saved={scroll:loaded.scroll||0,section:loaded.section};
   viewState.set(active,saved);
   try{localStorage.setItem(positionKey(active),JSON.stringify(saved));}catch(_){}
 }
 window.addEventListener('pagehide',remember);
 function hide(){clearTimeout(scrollTimer);root.hidden=true;if(active){remember();reset();active='';}}
 const phases={
   SUCCEEDED:'已存草稿',MATCHED:'草稿已经读回',RESULT_UNKNOWN:'草稿结果待确认',
   FAILED:'草稿保存失败',REJECTED:'草稿未保存',NOT_ATTEMPTED:'尚未发表',
   ACCEPTED:'发表中',PUBLISHED:'已发表',PUBLISHED_URLS_INCOMPLETE:'已发表，链接未齐',
   UNKNOWN:'发表结果待确认',SUBMIT_UNKNOWN:'发表结果待确认',
   LOCAL_STATUS_UNAVAILABLE:'发表回执暂不可读',
 };
 function deliveryStatus(rows){
   const key=JSON.stringify(rows);
   if(deliveryKey===key)return;
   deliveryKey=key;delivery.replaceChildren();
   if(!rows.length)delivery.append(label('p',OAUI.format('当前版本暂无草稿回执')));
   for(const row of rows){
     const state=[row.draft_state,row.readback_state,row.publication_state].filter(Boolean);
     const p=label('p',state.map(item=>OAUI.format(phases[item]||item)).join(' · '));
     const handle=label('small',row.attempt_id);
     delivery.append(p,handle);
     if(row.url){
       let url;
       try{url=new URL(row.url);}catch(_){}
       if(url?.protocol==='https:'&&url.hostname==='mp.weixin.qq.com'){
         const a=label('a',OAUI.format('阅读已发表文章'));
         a.href=url.href;a.onclick=event=>{event.preventDefault();void openURL(url.href);};
         delivery.append(a);
       }
     }
   }
 }
 async function imageURL(scope, version, slot, image, epoch){
   const source=new Uint8Array(image.size);
   for(let offset=0;offset<image.size;){
     if(epoch!==pending)return null;
     const part=await media('article_image',{...scope,version,slot,offset});
     if(part.version!==version||part.slot!==slot||part.sha256!==image.sha256||
        part.project_id!==scope.project_id||part.work_id!==scope.work_id||
        part.size!==image.size||part.declared_type!==image.declared_type||part.offset!==offset)
       throw Error('ARTICLE_WORK_IMAGE_SCOPE');
     const bytes=Uint8Array.from(atob(part.data),c=>c.charCodeAt(0));
     if(part.next!==offset+bytes.length||part.next<=offset||part.next>image.size)throw Error('ARTICLE_WORK_IMAGE_RANGE');
     source.set(bytes,offset);offset=part.next;
   }
   const hash=Array.from(new Uint8Array(await crypto.subtle.digest('SHA-256',source)),n=>n.toString(16).padStart(2,'0')).join('');
   if(epoch!==pending)return null;
   if(hash!==image.sha256)throw Error('ARTICLE_WORK_IMAGE_CHANGED');
   const url=URL.createObjectURL(new Blob([source],{type:image.declared_type}));mediaURLs.push(url);
   return url;
 }
 function renderLayout(row,scope,epoch){
   const dom=new DOMParser().parseFromString(row.layout,'text/html');
   const images=[...dom.body.querySelectorAll('img')];
   for(const img of images){
     const source=img.getAttribute('src')||'';
     img.removeAttribute('src');img.removeAttribute('srcset');
     if(source.startsWith('data:,jiusera-'))img.dataset.awImage=source.slice(14);
   }
   const sections=[...dom.body.querySelectorAll('h1,h2,h3,h4,h5,h6,p,blockquote,img,li,pre')];
   const items=[['aw-cover',OAUI.format('封面')]];
   for(const [i,node] of sections.entries()){
     node.id='aw-section-'+i;
     const bodyText=node.textContent.trim();
     const name=node.tagName==='IMG'?(node.alt||OAUI.format('正文配图')):bodyText.slice(0,62);
     if(name)items.push([node.id,name]);
   }
   outline.replaceChildren();
   for(const [id,name] of items){
     const choice=label('button',name);choice.type='button';choice.title=name;
     const mark=()=>choice.setAttribute('aria-pressed',String(loaded?.section===id));
     choice.onclick=()=>{
       if(!loaded)return;
       loaded.section=id;
       frame.contentDocument?.getElementById(id)?.scrollIntoView({block:'nearest'});
       for(const other of outline.querySelectorAll('button'))other.setAttribute('aria-pressed',String(other===choice));
     };
     mark();outline.append(choice);
   }
   const shell=$('main'),heading=label('h1',row.title),author=label('p',row.author,'author');
   const cover=$('img','cover');cover.id='aw-cover';cover.alt=OAUI.format('封面');cover.dataset.awImage=row.cover;
   shell.append(cover,heading);if(row.author)shell.append(author);shell.append(...dom.body.childNodes);
   frame.onload=()=>{
     if(epoch!==pending)return;
     const doc=frame.contentDocument;
     if(!doc?.getElementById('aw-cover'))return;
     const restore=()=>{doc.scrollingElement.scrollTop=loaded?.scroll||0;};
     doc.addEventListener('scroll',()=>{
       if(epoch!==pending)return;
       clearTimeout(scrollTimer);scrollTimer=setTimeout(remember,120);
     },{passive:true});
     restore();
     for(const [slot,image] of Object.entries(row.images)){
       const targets=[...doc.querySelectorAll('img[data-aw-image]')].filter(node=>node.dataset.awImage===slot);
       void imageURL(scope,row.version,slot,image,epoch).then(url=>{
         if(url&&epoch===pending)for(const target of targets)target.src=url;
       }).catch(()=>{
         if(epoch===pending)for(const target of targets)target.alt=OAUI.format('原图暂不可读');
       });
     }
   };
   frame.srcdoc='<!doctype html><html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">'+
     '<meta http-equiv="Content-Security-Policy" content="default-src \'none\'; img-src blob: data:; style-src \'unsafe-inline\'; navigate-to \'none\'">'+
     '<style>html{background:white;color:#18221d;font:16px/1.75 system-ui}body{margin:0}main{padding:18px}h1{font-size:25px;line-height:1.34;margin:14px 0}.author{color:#617067}.cover{display:block;width:100%;min-height:48px;aspect-ratio:2.35;object-fit:cover;background:#f2f4f3}img{max-width:100%}</style>'+
     '</head><body>'+shell.outerHTML+'<\/body><\/html>';
 }
 async function show(scope, mode){
   root.hidden=false;root.dataset.stage=mode;
   const key=scope.project_id+':'+scope.work_id;
   if(active!==key){remember();reset();active=key;title.textContent='';meta.textContent=OAUI.format('正在读取文章…');}
   const started=pending, known=revision, requested=selectedVersion;
   versions.onchange=()=>{selectedVersion=versions.value;pending++;void show(scope,mode);};
   try{
     const row=await read('article_work',{...scope,...(known?{known_version:known}:{}),...(requested?{version:requested}:{})});
     if(key!==active||started!==pending||root.hidden||
        row.project_id!==scope.project_id||row.work_id!==scope.work_id)return;
     title.textContent=row.title;
     meta.textContent=row.account_label+' · '+row.account_hint+' · '+OAUI.format('第 {0} 版',[row.revision]);
     const ordered=row.versions||[];
     const listKey=JSON.stringify(ordered);
     versions.hidden=ordered.length<2;
     if(listKey!==versionKey){
       versionKey=listKey;
       versions.replaceChildren(new Option(OAUI.format('最新稿'),''),...ordered.map(
         item=>new Option(OAUI.format('第 {0} 版',[item.revision]),item.version)));
     }
     versions.value=selectedVersion;
     deliveryStatus(row.receipts||[]);
     if(row.version!==revision){
       remember();
       frame.onload=null;
       for(const url of mediaURLs.splice(0))URL.revokeObjectURL(url);
       loaded=position(key);revision=row.version;
       renderLayout(row,scope,++pending);
     }
   }catch(problem){
     if(key!==active||started!==pending)return;
     meta.textContent=OAUI.format(revision?'暂时无法更新，保留上次已读取的稿件':'文章原稿暂不可读');
   }
 }
 return {show,hide};
}

function OAArticleLibrary(root,read,media,openURL,goToArticle){
 const chrome=document.createElement('div');chrome.className='aw-library';
 const list=document.createElement('nav');list.className='aw-list';list.setAttribute('aria-label',OAUI.format('文章资产'));
 const detail=document.createElement('section');detail.id='articleAssetReader';detail.className='aw-asset-detail';detail.hidden=true;
 const area=document.createElement('div');area.style.cssText='min-height:0;display:grid;grid-template-rows:auto minmax(0,1fr);gap:6px';
 const back=document.createElement('button');back.type='button';OAUI.set(back,'回到作品画布');back.hidden=true;
 const stage=OAArticleWork(detail,read,media,openURL);
 const scopes=new Map();
 let epoch=0, selected='', scroll=0;
 try{selected=localStorage.getItem('jiusera.article-asset.selection')||'';}catch(_){}
 area.append(back,detail);chrome.append(list,area);root.append(chrome);
 function pick(row){
   selected=row.project_id+':'+row.work_id;
   try{localStorage.setItem('jiusera.article-asset.selection',selected);}catch(_){}
   for(const button of list.querySelectorAll('button'))button.setAttribute('aria-pressed',String(button.dataset.key===selected));
   back.hidden=false;back.disabled=false;
   back.onclick=()=>{back.disabled=true;void goToArticle(row).catch(()=>{back.disabled=false;});};
   void stage.show({project_id:row.project_id,work_id:row.work_id},'assets');
 }
 document.addEventListener('jiusera:asset-category',async event=>{
   const token=++epoch;
   if(event.detail.kind!=='articles'){scroll=list.scrollTop;stage.hide();back.hidden=true;return;}
   let rows;
   try{({articles:rows}=await read('article_catalog'));}
   catch(_){if(token===epoch)OAUI.set(list,'文章索引暂不可读');return;}
   if(token!==epoch||root.hidden)return;
   list.replaceChildren();scopes.clear();
   for(const row of rows){
     const button=document.createElement('button');button.type='button';
     button.dataset.key=row.project_id+':'+row.work_id;
     button.textContent=[row.title,row.account_label&&row.account_label+' · '+row.account_hint,row.project].filter(Boolean).join(' · ');
     button.title=button.textContent;
     button.onclick=()=>pick(row);
     list.append(button);scopes.set(button.dataset.key,row);
   }
   const row=scopes.get(selected)||rows[0];
   if(row)pick(row);
   else{OAUI.set(list,'暂无已登记文章');stage.hide();back.hidden=true;}
   list.scrollTop=scroll;
 });
}
'''
