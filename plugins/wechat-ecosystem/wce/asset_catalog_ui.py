"""Asset categories and the project-scoped image browser."""

from html import escape

KINDS = {
    'characters': ('形象', 'characterLibrary', 'M20 21v-2a4 4 0 0 0-4-4H8a4 4 0 0 0-4 4v2M16 7a4 4 0 1 1-8 0 4 4 0 0 1 8 0Z'),
    'images': ('图片', 'imageAssetLibrary', 'M4 4h16v16H4zM4 16l5-5 4 4 3-3 4 4M14 8h1'),
    'gif': ('动图', 'mediaMonitor', 'M3 4h18v16H3zM8 4v16m8-16v16'),
    'video': ('视频', 'mediaMonitor', 'M3 5h18v14H3zM10 9l5 3-5 3z'),
    'audio': ('音频', 'mediaMonitor', 'M3 12h2m3-4v8m4-12v16m4-12v8m3-4h2'),
    'articles': ('文章', 'articleAssetLibrary', 'M5 3h10l4 4v14H5zM9 11h6m-6 4h6m-6 3h4'),
}


HTML = (
    '<nav id="directorAssetKinds" aria-label="资产分类" hidden>'
    + ''.join(
        f'<button type="button" data-asset-kind="{key}" aria-controls="{target}">'
        f'<svg viewBox="0 0 24 24" class="oa-icon" aria-hidden="true"><path d="{escape(icon)}"/></svg>'
        f'<span>{title}</span><span class="ja-tail"><span class="ja-count"></span><span class="ja-arrow" aria-hidden="true">›</span></span></button>'
        for key, (title, target, icon) in KINDS.items()
    )
    + '</nav>'
    + '''
<section id="imageAssetLibrary" aria-label="图片资产" hidden>
 <div class="ja-image-tools">
  <label>项目<select id="jaImageProject"></select></label>
  <label>搜索资产<input id="jaImageSearch" type="search"></label>
  <button id="jaImageRefresh" type="button">刷新</button>
 </div>
 <p id="jaImageStatus" role="status"></p>
 <div class="ja-image-columns">
  <div id="jaImageList" aria-label="图片列表"></div>
  <article id="jaImageDetail" tabindex="-1"></article>
 </div>
</section>
<section id="articleAssetLibrary" aria-label="文章资产" hidden></section>
'''
)

STYLE = '''
.oa-management.oa-native[data-workbench=assets]:not(.oa-platform-view) #videoDirectorDesk {
 overflow:hidden;scrollbar-gutter:auto;gap:10px
}
[data-workbench=assets] #videoDirectorDesk>.dd-toolbar {flex:none}
[data-workbench=assets] #videoDirectorDesk #mediaMonitor,
[data-workbench=assets] #characterLibrary,
[data-workbench=assets] #imageAssetLibrary,
[data-workbench=assets] #articleAssetLibrary {flex:1 1 0;min-height:0;min-width:0}
[data-workbench=assets] #articleAssetLibrary {overflow:auto;overscroll-behavior:contain}
[data-workbench=assets] #directorAssetKinds {
 display:grid;grid-template-columns:repeat(auto-fit,minmax(min(100%,180px),1fr));
 gap:8px;align-content:start;align-items:stretch;overflow:auto;min-height:0;
 padding:1px 1px 6px
}
[data-workbench=assets] #directorAssetKinds button {
 display:grid;grid-template-columns:24px minmax(0,1fr) auto;gap:9px;min-height:54px;
 align-items:center;padding:10px 12px;text-align:start;background:var(--surface);
 color:var(--ink);border:1px solid var(--line);border-radius:10px;box-shadow:none
}
[data-workbench=assets] #directorAssetKinds button:hover {background:var(--tint)}
#directorAssetKinds svg {width:20px;height:20px}
.ja-tail{display:flex;align-items:center;gap:7px}.ja-count{font-size:11px;color:var(--muted)}
.ja-arrow,#jaImageStatus {color:var(--muted)}
#imageAssetLibrary {display:flex;flex-direction:column;gap:7px}
.ja-image-tools {display:flex;align-items:end;flex-wrap:wrap;gap:7px}
.ja-image-tools label {display:grid;gap:3px;flex:1 1 90px;min-width:0;max-width:240px}
.ja-image-columns {display:grid;grid-template-columns:minmax(145px,30%) minmax(0,1fr);gap:8px;
 flex:1;min-height:0}
#jaImageList,#jaImageDetail {min-width:0;min-height:0;overflow:auto;overscroll-behavior:contain;
 border:1px solid var(--line);border-radius:9px;background:var(--surface);padding:8px}
#jaImageList button {display:grid;width:100%;text-align:start;justify-items:start;gap:2px;
 box-shadow:none;border-color:transparent;background:transparent;overflow-wrap:anywhere}
#jaImageList button[aria-pressed=true] {background:var(--tint)}
#jaImageList small {color:var(--muted)}
#jaImageDetail {display:grid;align-content:start;gap:8px}
#jaImageDetail img {display:block;max-width:100%;height:auto;max-height:60dvh;object-fit:contain}
#jaImageDetail ul {margin:0;padding-inline-start:18px}
#jaImageDetail header {display:flex;align-items:center;justify-content:space-between;gap:6px}
#jaImageListBack {display:none}
@media(max-width:690px) {
 [data-workbench=assets] #videoDirectorDesk .mm-columns {display:grid;grid-template-columns:minmax(0,1fr);
  grid-template-rows:minmax(0,1fr);min-height:0}
 [data-workbench=assets] :is(#monitorList,#monitorDetail) {height:auto;max-height:none}
 .ja-image-columns {grid-template-columns:minmax(0,1fr)}
 #imageAssetLibrary[data-detail=true] #jaImageList,
 #imageAssetLibrary:not([data-detail=true]) #jaImageDetail {display:none}
 #jaImageListBack {display:inline-flex}
}
@media (max-width:520px) {
 [data-workbench=assets] #directorAssetKinds {grid-template-columns:repeat(2,minmax(0,1fr))}
}
'''

SCRIPT = r'''
function OAImageAssets(tool){
 const $=id=>document.getElementById(id), root=$('imageAssetLibrary');
 const list=$('jaImageList'), detail=$('jaImageDetail'), filter=$('jaImageProject');
 const search=$('jaImageSearch'), status=$('jaImageStatus'), refresh=$('jaImageRefresh');
 const storage='jiusera.assets.images';
 let active=false, readTimer=0, imageTimer=0, url='', projects=[], rows=[], selected='';
 let listedScroll=0, detailScroll=0;
 try{
   const saved=JSON.parse(localStorage.getItem(storage));
   selected=typeof saved?.selected==='string'?saved.selected:'';
   listedScroll=Number(saved?.list)||0;detailScroll=Number(saved?.details)||0;
   root.dataset.detail=String(!!saved?.show);
   search.value=typeof saved?.query==='string'?saved.query:'';
   filter.dataset.saved=typeof saved?.project==='string'?saved.project:'';
 }catch(_){}
 function keep(){
   if(!root.hidden){
     if(list.getClientRects().length)listedScroll=list.scrollTop;
     if(detail.getClientRects().length)detailScroll=detail.scrollTop;
   }
   try{localStorage.setItem(storage,JSON.stringify({selected,list:listedScroll,details:detailScroll,
     show:root.dataset.detail==='true',query:search.value,project:filter.value||filter.dataset.saved||''}));}catch(_){}
 }
 function clearImage(){
   imageTimer++;
   if(url)URL.revokeObjectURL(url);
   url='';
 }
 const call=(action,args={})=>tool('wce.ui.video.director.media',{action,...args});
 const rowKey=row=>JSON.stringify([row.project_id,row.sha256]);
 const element=(tag,title,raw=false)=>{const el=document.createElement(tag);if(title!==undefined)(raw?OAUI.raw:OAUI.set)(el,title);return el;};
 function choose(row){
   if(selected!==rowKey(row))detailScroll=0;
   if(list.getClientRects().length)listedScroll=list.scrollTop;
   selected=rowKey(row);root.dataset.detail='true';draw();
   detail.focus({preventScroll:true});keep();
 }
 function draw(){
   const query=search.value.trim().toLocaleLowerCase();
   const visible=rows.filter(row=>(!filter.value||row.project_id===filter.value)&&
     (!query||[row.title,row.project_label,...row.uses.map(use=>use.work)].some(s=>s.toLocaleLowerCase().includes(query))));
   const current=visible.find(row=>rowKey(row)===selected);
   clearImage();list.replaceChildren();detail.replaceChildren();
   for(const row of visible){
     const button=element('button');
     button.type='button';button.setAttribute('aria-pressed',String(row===current));
     button.append(element('strong',row.title,true),element('small',row.project_label,true));
     button.onclick=()=>choose(row);list.append(button);
   }
   if(!visible.length)list.append(element('p','没有已登记的图片。'));
   if(current){
     const title=element('h2',current.title,true),bar=element('header');
     const back=element('button','返回列表');back.type='button';back.id='jaImageListBack';
     back.onclick=()=>{keep();root.dataset.detail='false';list.scrollTop=listedScroll;list.querySelector('[aria-pressed=true]')?.focus();keep();};
     bar.append(title,back);detail.append(bar);
     const preview=element('div');const loading=element('p','正在读取原图…');loading.role='status';
     preview.append(loading);detail.append(preview);
     detail.append(element('p',current.project_label,true),element('h3','使用位置'));
     const usages=element('ul');
     for(const use of current.uses){
       const row=element('li'),label=use.kind==='article'?(use.role==='cover'?'文章封面':'正文配图'):use.kind==='canvas'?'画布':'镜头参考';
       OAUI.set(row,'{0} · {1}',label,[use.work,use.account,use.shot,use.title].filter(Boolean).join(' / '));usages.append(row);
     }
     detail.append(usages);void original(current,preview);
   }else{
     root.dataset.detail='false';
     detail.append(element('p','选择图片查看原图与使用位置。'));
   }
   list.scrollTop=listedScroll;detail.scrollTop=detailScroll;
 }
 async function original(row,preview){
   const ticket=imageTimer;
   const chunks=[];let offset=0,total=0,mime='';
   try{
     do{
       const part=await call('asset_image_original',{project_id:row.project_id,sha256:row.sha256,offset});
       if(ticket!==imageTimer||!active)return;
       if(part.sha256!==row.sha256||part.offset!==offset||!Number.isSafeInteger(part.total)||part.total<=0||
           !['image/png','image/jpeg'].includes(part.mime_type)||(offset&&(part.total!==total||part.mime_type!==mime)))
         throw Error('DIRECTOR_ASSET_CHANGED');
       total=part.total;mime=part.mime_type;
       const bytes=Uint8Array.from(atob(part.data),char=>char.charCodeAt(0));
       if(!bytes.length||offset+bytes.length>total)throw Error('DIRECTOR_ASSET_CHANGED');
       chunks.push(bytes);offset+=bytes.length;
     }while(offset<total);
     const blob=new Blob(chunks,{type:mime});
     if(crypto.subtle){
       const hash=await crypto.subtle.digest('SHA-256',await blob.arrayBuffer());
       if(Array.from(new Uint8Array(hash),n=>n.toString(16).padStart(2,'0')).join('')!==row.sha256)
         throw Error('DIRECTOR_ASSET_CHANGED');
     }
     if(ticket!==imageTimer||!active)return;
     url=URL.createObjectURL(blob);
     const image=element('img');image.alt=row.title;image.src=url;
     image.onerror=()=>{if(ticket===imageTimer&&active)preview.replaceChildren(element('p','无法读取登记原图。'));};
     image.onload=()=>{if(ticket===imageTimer&&active)detail.scrollTop=detailScroll;};
     preview.replaceChildren(image);
   }catch(_){if(ticket===imageTimer&&active)preview.replaceChildren(element('p','无法读取登记原图。'));}
 }
 async function read(){
   const ticket=++readTimer;
   const target=filter.value||filter.dataset.saved||'';
   OAUI.set(status,'正在读取图片…');refresh.disabled=true;
   try{
     const result=await call('asset_image_library');
     if(!active||ticket!==readTimer)return;
     if(!Array.isArray(result.projects))throw Error('DIRECTOR_ASSET_READ_FAILED');
     projects=result.projects;rows=projects.flatMap(project=>project.images);
     filter.replaceChildren(element('option','全部项目'));
     filter.firstElementChild.value='';
     for(const project of projects){
       const option=element('option',project.name,true);option.value=project.id;filter.append(option);
     }
     filter.value=projects.some(project=>project.id===target)?target:'';
     delete filter.dataset.saved;
     OAUI.set(status,projects.some(project=>project.unavailable)?'部分项目无法读取。':'');
     draw();
   }catch(_){if(active&&ticket===readTimer)OAUI.set(status,'无法读取图片资产。');}
   finally{if(ticket===readTimer)refresh.disabled=false;}
 }
 const changed=()=>{listedScroll=0;detailScroll=0;draw();keep();};
 search.oninput=changed;filter.onchange=changed;refresh.onclick=()=>void read();
 list.onscroll=detail.onscroll=()=>{if(active)keep();};
 return {open(){active=true;root.hidden=false;void read();},close(){
   if(!active)return;keep();active=false;readTimer++;clearImage();root.hidden=true;
 }};
}
'''
