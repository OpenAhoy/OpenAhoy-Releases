"""Character reference browser and exact-version storyboard picker."""

PAGE = '<section id="characterLibrary" aria-label="形象资产库" hidden></section>'

HTML = r'''
<dialog id="characterPicker" aria-label="从形象库选择"><div class="cl-picker-head"><strong>从形象库选择</strong><button type="button" id="clPickerClose">关闭</button></div><section id="clPickerLibrary" aria-label="镜头参考图库"></section></dialog>
<dialog id="characterDetail" aria-labelledby="clDetailTitle"><div id="clDetailContent"></div></dialog>
<dialog id="characterImport" aria-labelledby="clImportTitle"><div id="clImportFields" class="cl-form">
 <div class="cl-dialog-head"><h2 id="clImportTitle">导入形象索引</h2><button type="button" id="clImportClose">关闭</button></div>
 <label>所属项目<select id="clImportProject" required></select></label>
 <div class="cl-actions"><button type="button" id="clImportBrowse">从项目目录选择</button><output id="clImportChosen"></output></div>
 <section id="clImportBrowser" aria-label="项目目录" hidden></section>
 <details><summary>手动指定索引文件和路径</summary>
  <label>项目内的索引文件<input id="clImportFile" type="file" accept=".json,application/json" required></label>
  <label>索引的项目相对路径<input id="clImportPath" required placeholder="例如 references/characters.json"></label>
  <button type="button" id="clImportReview">预览导入</button>
 </details>
 <div class="cl-actions"><button type="button" id="clImportApply" class="primary" disabled>登记索引</button></div>
 <p role="status" id="clImportStatus"></p><ul id="clImportRows"></ul>
</div></dialog>
'''

STYLE = r'''
#characterLibrary,#characterPicker,#characterDetail,#characterImport{
 --cl-bg:var(--bg);--cl-card:var(--surface);--cl-frame:var(--soft);--cl-line:var(--line);
 --cl-accent:var(--accent);--cl-tint:var(--oa-selection,var(--tint));
 --cl-green:light-dark(#27694d,#a6d9c2);--cl-green-bg:light-dark(#e2f3e9,#263c33);
 --cl-gray:var(--muted);--cl-gray-bg:var(--soft)
}
#characterLibrary{min-height:0;flex:1;overflow:hidden}
#characterLibrary .cl-header h1{display:none}
#characterLibrary .cl-header{justify-content:flex-end}
#clImportChosen,#clImportBrowser{overflow-wrap:anywhere}
#clImportBrowser{border:1px solid var(--cl-line);border-radius:8px;padding:8px;max-height:210px;overflow:auto}
#clImportBrowser button{display:block;max-width:100%;margin-top:4px;text-align:start}
#clImportBrowser .cl-directory::before{content:'› ';font-weight:650}
.cl-layout{display:grid;grid-template-columns:151px minmax(0,1fr);grid-template-rows:minmax(0,1fr);
 box-sizing:border-box;height:100%;min-width:0;
 background:var(--cl-bg);border:1px solid var(--cl-line);border-radius:14px;color:var(--ink)}
.cl-projects{display:flex;flex-direction:column;align-items:stretch;gap:5px;padding:16px 10px;
 border-right:1px solid var(--cl-line);min-height:0;overflow:auto;overscroll-behavior:contain}
:is(#videoDirectorDesk,#characterPicker) .cl-projects button{display:grid;grid-template-columns:minmax(0,1fr) auto;
 align-items:center;flex-shrink:0;min-width:0;max-width:100%;gap:6px;text-align:start}
.cl-project-label{min-width:0;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.cl-project-count{font-variant-numeric:tabular-nums;white-space:nowrap;color:var(--muted)}
.cl-projects button[aria-pressed=true],.cl-filters button[aria-pressed=true]{background:var(--cl-tint);color:var(--cl-accent)}
.cl-main{min-width:0;min-height:0;padding:clamp(13px,2vw,29px);overflow:auto;
 overscroll-behavior:contain;scrollbar-gutter:stable}
.cl-header{display:flex;justify-content:space-between;align-items:start;gap:12px;flex-wrap:wrap}
.cl-header h1{margin:0;font-size:15px;font-weight:650;line-height:1.35}
.cl-controls,.cl-actions,.cl-filters{display:flex;align-items:center;flex-wrap:wrap;gap:6px}
:is(#videoDirectorDesk,#characterPicker) .cl-controls input[type=search]{margin:0;width:clamp(175px,19vw,255px)}
.cl-filters{margin:16px 0 8px}
:is(#videoDirectorDesk,#characterPicker) .cl-series-filter{
 display:grid;grid-template-columns:auto minmax(0,1fr);align-items:center;gap:6px;
 width:min(100%,235px);margin:0;color:var(--muted);font-size:12px
}
.cl-series-filter select{width:100%;min-width:0;text-overflow:ellipsis}
.cl-count{margin:0 0 12px;color:var(--muted)}
.cl-grid{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:12px}
.oa-native :is(#characterLibrary,#characterPicker) .cl-card{
 display:grid;grid-template-rows:auto 1fr;align-content:stretch;align-items:start;justify-items:stretch;width:100%;
 min-width:0;padding:0;border:1px solid var(--cl-line);
 border-radius:10px;background:var(--cl-card);box-shadow:none;overflow:hidden;text-align:start;font:inherit;color:inherit}
.oa-native :is(#characterLibrary,#characterPicker) .cl-card:is(:hover,:focus-visible){border-color:var(--cl-accent);background:var(--cl-card)}
.cl-picture{display:grid;place-items:center;width:100%;aspect-ratio:1.24;overflow:hidden;background:var(--cl-frame);
 color:var(--cl-gray);font-size:12px;white-space:normal;text-align:center}
.cl-picture img{display:block;width:100%;height:100%;object-fit:contain;min-height:0}
.cl-card-copy{display:grid;align-content:start;gap:5px;padding:10px 11px;min-width:0;white-space:normal}
.cl-card[aria-pressed=true]{outline:2px solid var(--cl-accent);outline-offset:-2px}
.cl-card-copy strong{font-size:16px;line-height:1.2;overflow-wrap:anywhere}
.cl-card-meta{display:flex;align-items:center;flex-wrap:wrap;gap:5px;color:var(--muted);font-size:12px}
.cl-badge{border-radius:5px;background:var(--cl-gray-bg);color:var(--cl-gray);padding:2px 6px;font-size:11px}
.cl-badge[data-status=current]{background:var(--cl-green-bg);color:var(--cl-green)}
.cl-badge[data-status=candidate]{background:var(--cl-tint);color:var(--cl-accent)}
.cl-subtitle,.cl-detail-fields dd{color:var(--muted);overflow-wrap:anywhere;font-size:12px}
#characterPicker,#characterDetail,#characterImport{background:var(--cl-card);color:var(--ink);border:1px solid var(--cl-line);
 border-radius:14px;max-height:92dvh;padding:0;overflow:auto}
#characterPicker{width:min(1180px,96vw)}
#characterDetail{width:min(840px,94vw)}
#characterImport{width:min(520px,94vw)}
#characterPicker::backdrop,#characterDetail::backdrop,#characterImport::backdrop{background:#110c08a0}
#characterPicker .cl-layout{height:min(76dvh,780px);border-radius:0;border:0}
.cl-picker-head,.cl-dialog-head{display:flex;align-items:center;justify-content:space-between;gap:8px}
.cl-picker-head,.cl-detail{padding:14px}
.cl-dialog-head h2{margin:0;font-size:20px;overflow-wrap:anywhere}
.cl-detail .cl-picture{aspect-ratio:auto;min-height:120px;margin:10px 0}
.cl-detail .cl-picture img{max-height:55dvh;width:100%;height:auto}
.cl-detail-fields{display:grid;grid-template-columns:auto minmax(0,1fr);gap:4px 12px;margin:12px 0}
.cl-detail-fields dd{margin:0}
.cl-form{display:grid;gap:8px;padding:16px}
.cl-form p,.cl-form ul{margin:0;overflow-wrap:anywhere}
.cl-form ul{padding-left:18px}
@media(max-width:1269px){.cl-grid{grid-template-columns:repeat(3,minmax(0,1fr))}}
@media(max-width:880px){.cl-layout{grid-template-columns:minmax(0,1fr);grid-template-rows:auto minmax(0,1fr)}
 .cl-projects{flex-direction:row;flex-wrap:wrap;align-content:start;max-height:min(30dvh,180px);
  border-right:0;border-bottom:1px solid var(--cl-line);padding:8px}
}
@media(max-width:635px){
 .cl-header,.cl-controls{width:100%}
 .cl-controls{display:grid;grid-template-columns:minmax(0,1fr) auto auto}
 :is(#videoDirectorDesk,#characterPicker) .cl-controls input[type=search]{width:100%;min-width:0}
 .cl-grid{grid-template-columns:repeat(2,minmax(0,1fr));gap:8px}
 .cl-main{padding:12px}
 .cl-layout button{min-height:32px}
 .cl-card-copy{padding:8px}
 .cl-projects button{min-height:35px}
}
@media(max-width:799px){
 .oa-native.oa-character-view .oa-sidebar{
  display:grid;grid-template-columns:minmax(0,1fr) auto;gap:3px;padding:7px 10px
 }
 .oa-native.oa-character-view .oa-sidebar .oa-brand{min-height:28px;display:flex;gap:6px}
 .oa-native.oa-character-view .oa-sidebar #wechatCompactUpdates{grid-area:1/2}
 .oa-native.oa-character-view .oa-sidebar #softwareUpdateSlot:empty{display:none}
 .oa-native.oa-character-view .oa-sidebar > div:has(#platformNavigation){
  display:flex;gap:4px;grid-area:2/1/3/-1;overflow-x:auto;scrollbar-width:thin
 }
 .oa-native.oa-character-view .oa-sidebar .oa-nav{margin:0;flex:none;flex-wrap:nowrap}
 .oa-native.oa-character-view .oa-sidebar .oa-nav button{min-height:34px;padding:4px 7px}

}
'''

SCRIPT = r'''
function OACharacterLibrary(tool,openProjectSettings){
 const $=id=>document.getElementById(id);
 const page=$('characterLibrary'),picker=$('characterPicker'),detail=$('characterDetail'),importer=$('characterImport');
 const useText={full_body:'标准全身',face:'人脸',expression:'表情',pose:'动作',style:'风格／质感'};
 const stateText={current:'当前参考',candidate:'待确认',historical:'历史'};
 const action=(name,args={})=>tool('video.director.read',{action:name,...args});
 const edit=(name,args)=>tool('video.director.edit',{action:name,...args});
 const projectMedia=(name,args)=>tool('wce.ui.video.director.media',{action:name,...args});
 const media=(name,row,extra={})=>tool('wce.ui.video.director.media',{
   action:name,project_id:row.file.project_id,version_id:row.id,sha256:row.file.sha256,...extra});
 const t=(text,...values)=>OAUI.format(text,values);
 function node(tag,cls='',text){
   const el=document.createElement(tag);if(cls)el.className=cls;
   if(text!==undefined)OAUI.set(el,text);return el;
 }
 function button(text,activate){
   const el=node('button','',text);el.type='button';el.onclick=activate;return el;
 }
 const messages={
   DIRECTOR_CHARACTER_MANIFEST_CHANGED:'索引文件已变化，请重新选择。',
   DIRECTOR_CHARACTER_MANIFEST_INVALID:'索引格式有误，请检查文件。',
   DIRECTOR_STALE_REVISION:'镜头修订已更新，请返回新修订重新选择。',
   INVALID_TOOL_ARGUMENTS:'索引格式或输入有误。',
   DIRECTOR_ASSET_OUTSIDE_PROJECT:'索引或图片路径超出项目目录。',
   DIRECTOR_CHARACTER_DUPLICATE:'索引含有重复的版本标识。',
   DIRECTOR_CHARACTER_VERSION_CONFLICT:'这个版本标识已登记给其他内容，请使用新的版本标识。',
   DIRECTOR_CHARACTER_CURRENT_CONFLICT:'当前参考已变化，请刷新后重试。',
   DIRECTOR_CHARACTER_STALE_INDEX:'索引已有更新，请重新预览。',
   DIRECTOR_CHARACTER_REFERENCE_MISMATCH:'登记版本或原图指纹已变化，请重新选择。',
   DIRECTOR_ASSET_CHANGED:'原图的内容与登记版本不一致，请恢复原文件或登记新版本。',
   BOOTSTRAP_UNSAFE_PATH:'文件无法读取，请核对原项目路径与文件。',
   DIRECTOR_CHARACTER_ORIGINAL_MISSING:'找不到原图。请核对原项目路径。',
   DIRECTOR_CHARACTER_ORIGINAL_UNAVAILABLE:'原图不可用。请检查原文件或登记新版本。',
   DIRECTOR_PROJECT_NOT_REGISTERED:'项目登记已变化，请检查项目设置。',
   DIRECTOR_PROJECT_UNAVAILABLE:'项目目录不可用，请核对项目登记。',
   VIDEO_FRAME_CHANGED:'原图的内容与登记版本不一致，请恢复原文件或登记新版本。',
   INVALID_LOCAL_FILE:'文件无法读取，请核对原项目路径与文件。',
 };
 const error=problem=>messages[problem?.message]||'无法读取形象资产，请核对项目登记和原图。';
 function importError(problem){
   const diagnostic=problem?.diagnostic;
   if(!diagnostic?.manifest_field)return t(error(problem));
   const field=diagnostic.manifest_field,position=diagnostic.manifest_position;
   if(field==='use'&&position)return t('第 {0} 项的 use 无效。允许值：{1}',position,(diagnostic.allowed_values||Object.keys(useText)).join(', '));
   return position?t('第 {0} 项的 {1} 有误。{2}',position,field,t(error(problem))):
     t('索引的 {0} 有误。{1}',field,t(error(problem)));
 }
 let projects=[],refreshID=0,pickerSession=null,detailResource=null,detailEpoch=0,detailTrigger=null,importPlan=null,importEpoch=0;
 const browserStorage='jiusera.assets.characters';
 let retained={}, restoreBrowser=false, browserDetail=false;
 try{retained=JSON.parse(localStorage.getItem(browserStorage))||{};}catch(_){}
 function keepBrowser(){
   if(page.hidden||restoreBrowser)return;
   retained={project:browser.project,series:browser.series,status:browser.status,query:browser.search.value,
     scroll:browser.main.scrollTop,detailScroll:browserDetail?detail.scrollTop:0,
     selected:retained.selected,show:browserDetail};
   try{localStorage.setItem(browserStorage,JSON.stringify(retained));}catch(_){}
 }
 const exactKey=row=>JSON.stringify([row.file.project_id,row.id,row.file.sha256]);
 const jobs=[];let running=0;
 function drain(){
   while(running<3&&jobs.length){
     const task=jobs.shift();if(!task.figure.isConnected)continue;
     running++;
     media('character_thumbnail',task.row).then(result=>{
       if(!task.figure.isConnected)return;
       if(result.sha256!==task.row.file.sha256||result.mime_type!=='image/jpeg'||!result.data?.startsWith('/9j/'))
         throw Error('DIRECTOR_CHARACTER_ORIGINAL_UNAVAILABLE');
       const img=node('img');img.alt=task.row.character.name;img.src='data:image/jpeg;base64,'+result.data;
       task.figure.replaceChildren(img);
     }).catch(problem=>{
       if(task.figure.isConnected){task.figure.textContent=t(error(problem));task.figure.dataset.unavailable='true';}
     }).finally(()=>{running--;drain();});
   }
 }
 const observed=new WeakMap();
 const thumbnails=new IntersectionObserver(entries=>{
   for(const entry of entries)if(entry.isIntersecting){
     thumbnails.unobserve(entry.target);jobs.push({figure:entry.target,row:observed.get(entry.target)});
   }
   drain();
 },{rootMargin:'120px'});
 function badge(row){
   const el=node('span','cl-badge',stateText[row.status]);el.dataset.status=row.status;return el;
 }
 function makeView(host,picking){
   const shell=node('div','cl-layout'),side=node('nav','cl-projects'),main=node('div','cl-main');
   OAUI.attr(side,'aria-label','按项目筛选');
   const header=node('header','cl-header'),title=node('h1','','形象资产库'),controls=node('div','cl-controls');
   title.tabIndex=-1;
   const search=node('input');search.type='search';search.placeholder=t('搜索人物、别名或项目');
   OAUI.attr(search,'placeholder','搜索人物、别名或项目');
   OAUI.attr(search,'aria-label','搜索人物、别名或项目');
   const refreshButton=button('刷新',()=>void refresh());
   controls.append(search,refreshButton);
   if(!picking)controls.append(button('导入索引',()=>showImport(view)));
   header.append(title,controls);
   const filters=node('div','cl-filters'),count=node('p','cl-count'),grid=node('div','cl-grid');
   const seriesLabel=node('label','cl-series-filter'),seriesSelect=node('select');
   seriesLabel.append(node('span','','系列'),seriesSelect);
   filters.append(seriesLabel);
   count.setAttribute('role','status');main.append(header,filters,count,grid);shell.append(side,main);host.append(shell);
   const view={side,main,title,search,projectButtons:new Map(),seriesSelect,statusButtons:[],count,grid,
     project:'',series:'',status:'all',picking};
   for(const [id,label] of [['all','全部版本'],...Object.entries(stateText)]){
     const filter=button(label,()=>{view.status=id;render(view);});filter.dataset.filter=id;filters.append(filter);
     view.statusButtons.push(filter);
   }
   seriesSelect.onchange=()=>{view.series=seriesSelect.value;render(view);};
   syncProjects(view);syncSeries(view);
   search.oninput=()=>render(view);if(!picking)main.onscroll=keepBrowser;return view;
 }
 const browser=makeView(page,false),selection=makeView($('clPickerLibrary'),true),views=[browser,selection];
 function syncProjects(view){
   const rows=new Map([['',['全部项目',projects.reduce((sum,row)=>sum+row.assets.length,0)]]]);
   for(const {id,name,assets} of projects)rows.set(id,[name,assets.length]);
   const focused=view.side.contains(document.activeElement)?document.activeElement:null;
   for(const [id,el] of view.projectButtons){
     if(rows.has(id))continue;
     el.remove();view.projectButtons.delete(id);
   }
   let next=view.side.firstElementChild;
   for(const [id,[label,count]] of rows){
     let el=view.projectButtons.get(id);
     if(!el){
       el=button(undefined,()=>{
         if(view.project===id)return;
         view.project=id;view.series='';syncSeries(view);render(view);
       });
       el.append(node('span','cl-project-label'),node('span','cl-project-count'));
       if(!id){
         OAUI.attr(el,'title',label);OAUI.set(el.firstElementChild,label);
       }
       view.projectButtons.set(id,el);
     }
     if(id&&el.title!==label){el.title=label;OAUI.raw(el.firstElementChild,label);}
     if(el.lastElementChild.textContent!==String(count))el.lastElementChild.textContent=String(count);
     if(el!==next)view.side.insertBefore(el,next);
     next=el.nextElementSibling;
   }
   if(focused?.isConnected&&focused!==document.activeElement)focused.focus({preventScroll:true});
 }
 function syncSeries(view){
   const names=new Map();
   const selected=projects.find(row=>row.id===view.project);
   for(const row of selected?.assets||[]){
     const series=row.character.series;
     names.set(series,(names.get(series)||0)+1);
   }
   if(!names.has(view.series))view.series='';
   const options=[['',t('全部系列')],...Array.from(names,([name,count])=>[name,name+' · '+count])];
   const select=view.seriesSelect;
   if(select.options.length!==options.length||options.some(([value,text],i)=>
      select.options[i].value!==value||select.options[i].textContent!==text)){
     select.replaceChildren(...options.map(([value,text])=>{
       const option=node('option');option.value=value;
       if(value)OAUI.raw(option,text);else OAUI.set(option,'全部系列');
       return option;
     }));
   }
   select.disabled=!names.size;
   select.value=view.series;
 }
 function render(view){
   if(view.picking&&!picker.open)return;
   if(!view.picking&&page.hidden)return;
   for(const [id,el] of view.projectButtons)el.setAttribute('aria-pressed',String(id===view.project));
   for(const el of view.statusButtons)el.setAttribute('aria-pressed',String(view.status===el.dataset.filter));
   OAUI.attr(view.seriesSelect,'title',view.series?'{0}':'全部系列',view.series);
   const query=view.search.value.trim().normalize('NFKC').toLocaleLowerCase();
   const rows=projects.filter(project=>!view.project||project.id===view.project).flatMap(project=>
     project.assets.filter(row=>
       (!view.series||row.character.series===view.series)&&(view.status==='all'||row.status===view.status)
       &&[row.character.name,row.character.series,project.name,row.label,row.use,t(useText[row.use]),...row.character.aliases]
         .some(field=>field.normalize('NFKC').toLocaleLowerCase().includes(query)))
       .map(row=>({...row,projectName:project.name})));
   const rank={current:0,candidate:1,historical:2};rows.sort((a,b)=>rank[a.status]-rank[b.status]);
   const selected=projects.find(row=>row.id===view.project);
   view.count.textContent=rows.length?
     [view.series||selected?.name||t('全部项目'),t('{0} 个版本',rows.length)].join(' · '):
     t(selected?.unavailable?'项目目录或索引无法读取，请检查项目设置。':
       projects.some(row=>row.assets.length)?'没有匹配的形象。':'还没有已登记的形象。');
   if(projects.some(project=>project.unavailable)&&!selected)view.count.append(' · '+t('部分项目不可用'));
   for(const figure of view.grid.querySelectorAll('.cl-picture'))thumbnails.unobserve(figure);
   view.grid.replaceChildren(...rows.map(row=>{
     const card=button(row.character.name,()=>showDetail(view,row,card));card.className='cl-card';card.dataset.version=row.id;
     card.dataset.exact=exactKey(row);
     if(!view.picking)card.setAttribute('aria-pressed',String(retained.selected===card.dataset.exact));
     const figure=node('span','cl-picture','正在读取原图…'),copy=node('span','cl-card-copy');
     const meta=node('span','cl-card-meta');
     meta.append(node('span','',useText[row.use]),badge(row));
     copy.append(node('strong','',row.character.name),meta,node('span','cl-subtitle',row.character.series+' · '+row.label));
     card.replaceChildren(figure,copy);
     observed.set(figure,row);thumbnails.observe(figure);return card;
   }));
   if(!view.picking)keepBrowser();
 }
 async function refresh(){
   const id=++refreshID;
   if(!projects.length)for(const view of views)view.count.textContent=t('正在读取形象资产…');
   try{
     const result=await action('character_library');
     if(id!==refreshID)return;
     projects=result.projects;
     if(restoreBrowser&&!page.hidden){
       browser.project=retained.project||'';browser.series=retained.series||'';
       browser.status=retained.status||'all';browser.search.value=retained.query||'';
     }
     for(const view of views){
       if(!projects.some(row=>row.id===view.project)){view.project='';view.series='';}
       syncProjects(view);syncSeries(view);
       render(view);
     }
     if(restoreBrowser&&!page.hidden){
       const previous=retained;
       browser.main.scrollTop=Number(previous.scroll)||0;
       restoreBrowser=false;
       if(previous.show){
         [...browser.grid.querySelectorAll('.cl-card')].find(card=>card.dataset.exact===previous.selected)?.click();
         detail.scrollTop=Number(previous.detailScroll)||0;
       }
       keepBrowser();
     }
   }catch(problem){
     if(id===refreshID)for(const view of views)view.count.textContent=t(error(problem));
   }
 }
 function clearDetail(){
   detailEpoch++;if(detailResource){URL.revokeObjectURL(detailResource);detailResource=null;}
 }
 function closeDetail(){
   clearDetail();if(detail.open)detail.close();
 }
 detail.addEventListener('close',()=>{
   if(detail.open)return;
   if(browserDetail){browserDetail=false;keepBrowser();}
   clearDetail();
   if(detailTrigger?.isConnected&&!pickerSession?.closing)detailTrigger.focus();
   detailTrigger=null;
 });
 async function exactImage(row,alive){
   const chunks=[];let total=0,offset=0,mime='';
   do{
     const part=await media('character_original',row,{offset});
     if(!alive())return null;
     if(part.sha256!==row.file.sha256||part.offset!==offset
       ||!Number.isSafeInteger(part.total)||part.total<=0
       ||!['image/png','image/jpeg'].includes(part.mime_type)
       ||(offset&&(part.mime_type!==mime||part.total!==total)))throw Error('DIRECTOR_CHARACTER_ORIGINAL_UNAVAILABLE');
     mime=part.mime_type;total=part.total;
     const bytes=Uint8Array.from(atob(part.data),symbol=>symbol.charCodeAt(0));
     if(!bytes.length||offset+bytes.length>total)throw Error('DIRECTOR_CHARACTER_ORIGINAL_UNAVAILABLE');
     chunks.push(bytes);offset+=bytes.length;
   }while(offset<total);
   const blob=new Blob(chunks,{type:mime});
   if(crypto.subtle){
     const sum=await crypto.subtle.digest('SHA-256',await blob.arrayBuffer());
     if(Array.from(new Uint8Array(sum),v=>v.toString(16).padStart(2,'0')).join('')!==row.file.sha256)
       throw Error('VIDEO_FRAME_CHANGED');
   }
   return alive()?blob:null;
 }
 function showDetail(view,row,trigger){
   clearDetail();
   const token=detailEpoch,alive=()=>detail.open&&token===detailEpoch;
   const content=$('clDetailContent');content.replaceChildren();content.className='cl-detail';
   const top=node('header','cl-dialog-head'),title=node('h2','',row.character.name);title.id='clDetailTitle';
   top.append(title,button('关闭',closeDetail));
   const frame=node('div','cl-picture','正在核对原图…'),fields=node('dl','cl-detail-fields'),actions=node('div','cl-actions');
   for(const [label,value] of [['项目',row.projectName],['系列',row.character.series],['版本',row.label+' · '+row.id],
     ['用途',useText[row.use]],['状态',stateText[row.status]],['来源',row.source||'未注明'],['原图路径',row.file.path],
     ...(row.origin?[['来源版本', [projects.find(project=>project.id===row.origin.project_id)?.name||row.origin.project_id,
                                 row.origin.version_id].join(' · ')]]:[]),
     ...(row.description?[['说明',row.description]]:[])]){
     fields.append(node('dt','',label),node('dd','',value));
   }
   const feedback=node('p','cl-subtitle');feedback.setAttribute('role','status');
   const original=button('打开原图',async()=>{
     original.disabled=true;
     try{
       const blob=await exactImage(row,alive);if(!blob)return;
       if(detailResource)URL.revokeObjectURL(detailResource);
       detailResource=URL.createObjectURL(blob);
       const img=node('img');img.alt=row.character.name;
       img.onerror=()=>{if(alive()){feedback.textContent=t('当前页面无法显示原图。');original.disabled=false;}};
       img.src=detailResource;frame.replaceChildren(img);frame.scrollIntoView({block:'nearest'});
       feedback.textContent=t('正在显示登记原图。');
     }catch(problem){if(alive()){feedback.textContent=t(error(problem));original.disabled=false;}}
   });original.disabled=true;actions.append(original);
   const session=pickerSession;
   const crossProject=view.picking&&session?.project!==row.file.project_id;
   const execute=view.picking?button(crossProject?'引入本项目':'用作镜头参考',async()=>{
     execute.disabled=true;
     try{
       let selected=row;
       if(crossProject){
         const imported=await edit('character_import_version',{project_id:session.project,
           origin:{project_id:row.file.project_id,version_id:row.id,sha256:row.file.sha256}});
         if(imported.file?.project_id!==session.project||imported.file.sha256!==row.file.sha256||!imported.version_id)
           throw Error('DIRECTOR_CHARACTER_REFERENCE_MISMATCH');
         selected={...row,id:imported.version_id,file:imported.file};
       }else await media('character_thumbnail',row);
       if(!alive()||pickerSession!==session)return;
       session.choose(selected);session.closing=true;closeDetail();picker.close();
     }catch(problem){if(alive())feedback.textContent=t(error(problem));}
     finally{if(alive())execute.disabled=false;}
   }):row.status!=='current'?button('设为此用途的当前参考',async()=>{
     execute.disabled=true;
     try{
       await edit('character_set_current',{project_id:row.file.project_id,version_id:row.id,
         ...(row.current?{expected_current:row.current}:{})});
       if(!alive())return;
       closeDetail();await refresh();
       view.grid.querySelector('[data-version="'+row.id+'"]')?.focus();
     }catch(problem){if(alive())feedback.textContent=t(error(problem));}
     finally{if(alive())execute.disabled=false;}
   }):null;
   if(execute){execute.disabled=true;actions.append(execute);}
   if(crossProject)feedback.textContent=t('复制此版本的原图到「{0}」，并加入镜头参考。',
     projects.find(project=>project.id===session.project)?.name||t('本项目'));
   const projectSettings=button('查看项目设置',()=>{
     closeDetail();if(picker.open)picker.close();void openProjectSettings();
   });projectSettings.hidden=true;actions.append(projectSettings);
   content.append(top,frame,fields,feedback,actions);
   detailTrigger=trigger;if(!detail.open)detail.showModal();
   browserDetail=!view.picking;
   if(browserDetail){
     retained.selected=exactKey(row);
     for(const card of browser.grid.querySelectorAll('.cl-card'))
       card.setAttribute('aria-pressed',String(card.dataset.exact===retained.selected));
     detail.onscroll=keepBrowser;keepBrowser();
   }
   media('character_thumbnail',row).then(value=>{
     if(!alive()||value.sha256!==row.file.sha256||!value.data?.startsWith('/9j/'))return;
     const img=node('img');img.alt=row.character.name;img.src='data:image/jpeg;base64,'+value.data;
     frame.replaceChildren(img);original.disabled=false;if(execute)execute.disabled=false;
   }).catch(problem=>{
     if(alive()){frame.textContent=t(error(problem));projectSettings.hidden=false;}
   });
 }
 const importProject=$('clImportProject'),importFile=$('clImportFile'),importPath=$('clImportPath'),
   importStatus=$('clImportStatus'),importRows=$('clImportRows'),apply=$('clImportApply'),review=$('clImportReview'),
   browse=$('clImportBrowse'),fileBrowser=$('clImportBrowser'),chosen=$('clImportChosen');
 function resetImport(){
   importEpoch++;importPlan=null;apply.disabled=true;review.disabled=false;
   importRows.replaceChildren();importStatus.textContent='';chosen.textContent='';
 }
 function showImport(view){
   resetImport();importFile.value='';importPath.value='';fileBrowser.hidden=true;
   importProject.replaceChildren(...projects.filter(row=>!row.unavailable).map(row=>{
     const item=node('option','',row.name);item.value=row.id;return item;
   }));
   if(view.project&&projects.some(row=>row.id===view.project&&!row.unavailable))importProject.value=view.project;
   browse.disabled=review.disabled=!importProject.options.length;
   if(review.disabled)importStatus.textContent=t('请先在项目与 Skills 中登记项目。');
   importer.showModal();
 }
 function acceptPlan(project_id,source,plan){
   importPlan={project_id,source,expected_revision:plan.revision};
   chosen.textContent=source.path;
   const available={available:'原图可用',missing:'缺少原图',unavailable:'原图校验失败'},
     entry={new:'新版本',existing:'已登记',conflict:'版本冲突'};
   importRows.replaceChildren(...plan.assets.map(row=>node('li','',
     [row.name,row.id,t(stateText[row.status]),t(available[row.availability]),t(entry[row.entry])].join(' · '))));
   apply.disabled=plan.assets.some(row=>row.entry==='conflict'||(row.status==='current'&&row.entry==='new'&&row.availability!=='available'));
   importStatus.textContent=t(apply.disabled?'请先处理冲突或不可用的当前版本。':'索引预览已就绪。');
 }
 async function browseFolder(directory=''){
   resetImport();
   const token=importEpoch,project_id=importProject.value;
   fileBrowser.hidden=false;
   fileBrowser.replaceChildren(node('p','','正在读取项目目录…'));
   try{
     const result=await projectMedia('character_manifest_files',{project_id,...(directory?{directory}:{})});
     if(token!==importEpoch||!importer.open)return;
     const relative=name=>directory?directory+'/'+name:name;
     const parent=directory.split('/').slice(0,-1).join('/');
     const caption=node('strong');caption.textContent=directory||t('项目根目录');
     const items=[caption];
     if(directory)items.push(button('返回上一级',()=>void browseFolder(parent)));
     for(const name of result.folders){
       const folder=button(name,()=>void browseFolder(relative(name)));
       folder.className='cl-directory';folder.textContent=name;folder.setAttribute('aria-label',name);items.push(folder);
     }
     for(const name of result.files){
       const file=button('',()=>void pickManifest(project_id,relative(name)));
       file.textContent=name;items.push(file);
     }
     if(!result.folders.length&&!result.files.length)items.push(node('p','','此目录没有可选的索引。'));
     fileBrowser.replaceChildren(...items);
   }catch(problem){
     if(token===importEpoch)fileBrowser.replaceChildren(node('p','',importError(problem)));
   }
 }
 async function pickManifest(project_id,path){
   resetImport();const token=importEpoch;chosen.textContent=path;
   try{
     const plan=await projectMedia('character_manifest_pick',{project_id,path});
     if(token!==importEpoch||!importer.open)return;
     if(plan.source?.path!==path)throw Error('DIRECTOR_CHARACTER_MANIFEST_CHANGED');
     fileBrowser.hidden=true;acceptPlan(project_id,plan.source,plan);
   }catch(problem){if(token===importEpoch)importStatus.textContent=importError(problem);}
 }
 browse.onclick=()=>fileBrowser.hidden?void browseFolder():(fileBrowser.hidden=true,resetImport());
 importProject.onchange=()=>{fileBrowser.hidden=true;importFile.value='';importPath.value='';resetImport();};
 importPath.oninput=resetImport;
 importFile.onchange=resetImport;
 $('clImportClose').onclick=()=>importer.close();importer.addEventListener('close',resetImport);
 review.onclick=async()=>{
   if(![importProject,importFile,importPath].every(field=>field.reportValidity()))return;
   resetImport();const token=importEpoch;review.disabled=true;fileBrowser.hidden=true;
   const project_id=importProject.value,path=importPath.value.trim(),file=importFile.files[0];
   try{
     if(!file||!crypto.subtle)throw Error('DIRECTOR_CHARACTER_MANIFEST_INVALID');
     const hash=await crypto.subtle.digest('SHA-256',await file.arrayBuffer());
     const sha256=Array.from(new Uint8Array(hash),v=>v.toString(16).padStart(2,'0')).join('');
     const source={path,sha256};const plan=await action('character_import_preview',{project_id,source});
     if(token!==importEpoch||!importer.open)return;
     acceptPlan(project_id,source,plan);
   }catch(problem){if(token===importEpoch)importStatus.textContent=importError(problem);}
   finally{if(token===importEpoch)review.disabled=false;}
 };
 importPath.addEventListener('keydown',event=>{
   if(event.key==='Enter'&&!review.disabled){event.preventDefault();review.click();}
 });
 apply.onclick=async()=>{
   const plan=importPlan,token=importEpoch;if(!plan)return;apply.disabled=true;
   try{
     const result=await edit('character_import',plan);
     if(token!==importEpoch)return;
     importStatus.textContent=t(result.state==='UNCHANGED'?'这些版本已登记。':'登记完成。');
     await refresh();
   }catch(problem){if(token===importEpoch){importStatus.textContent=importError(problem);apply.disabled=false;}}
 };
 function choose(project,accept,trigger){
   pickerSession={project,choose:accept,trigger};selection.project=project;selection.series='';selection.status='all';selection.search.value='';
   syncSeries(selection);picker.showModal();render(selection);void refresh();
 }
 $('clPickerClose').onclick=()=>picker.close();
 picker.addEventListener('close',()=>{
   if(picker.open)return;
   if(detail.open)closeDetail();
   const trigger=pickerSession?.trigger;pickerSession=null;if(trigger?.isConnected)trigger.focus();
 });
 return {
   open(){
     if(!page.hidden)return;
     restoreBrowser=true;page.hidden=false;void refresh();
   },
   focus(){browser.title.focus();},
   close(){
     if(!page.hidden){keepBrowser();restoreBrowser=false;page.hidden=true;browserDetail=false;}
     closeDetail();if(picker.open)picker.close();if(importer.open)importer.close();
   },
   closePicker(){if(picker.open){closeDetail();picker.close();}},
   choose,
 };
}
'''
