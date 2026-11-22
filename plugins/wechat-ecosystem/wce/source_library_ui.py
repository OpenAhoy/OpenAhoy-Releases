"""Independent asset view for project source entrances."""
HTML = '''
<section id="sourceLibrary" aria-label="信源库" hidden>
 <div class="jsl-tools">
   <label><span>项目</span><select id="jslProject"></select></label>
   <label><span>搜索信源</span><input id="jslSearch" type="search" placeholder="名称、网址或主题"></label>
   <button id="jslAdd" type="button" aria-controls="jslEditor" aria-expanded="false">添加信源</button>
 </div>
 <div id="jslEditor" class="jsl-editor" hidden>
   <h2 id="jslEditorTitle">添加信源</h2>
   <div class="jsl-fields">
     <label id="jslAddress"><span>入口网址</span><input id="jslUrl" type="url" placeholder="https://" maxlength="4096"></label>
     <label><span>显示名称</span><input id="jslName" type="text" maxlength="160"></label>
     <label><span>主题</span><input id="jslTopic" type="text" maxlength="180"></label>
     <label><span>类型</span><select id="jslKind">
       <option value="website">网站</option><option value="newsroom">新闻室</option>
       <option value="section">栏目</option><option value="account">账号</option><option value="rss">RSS</option>
     </select></label>
   </div>
   <div class="jsl-actions">
     <button id="jslCancel" type="button">取消</button>
     <button id="jslSave" type="button">保存</button>
   </div>
 </div>
 <p id="jslStatus" role="status"></p>
 <ul id="jslList" aria-label="信源列表" tabindex="-1"></ul>
</section>
'''

STYLE = '''
#sourceLibrary{flex:1 1 0;min-width:0;min-height:0;display:flex;flex-direction:column;gap:10px}
#sourceLibrary[hidden],#sourceLibrary [hidden]{display:none}
#videoDirectorDesk:has(#sourceLibrary:not([hidden])) :is(#directorSound,#directorShowcase,#directorMore){display:none}
#sourceLibrary button{min-height:32px}
#sourceLibrary :is(input,select){width:100%;min-width:0;color:var(--ink);background:var(--surface);
 border:1px solid var(--line);border-radius:7px;padding:6px 8px;min-height:34px}
#sourceLibrary label{min-width:0;display:grid;gap:3px}
#sourceLibrary label span{font-size:12px;color:var(--muted)}
.jsl-tools{display:grid;grid-template-columns:minmax(135px,220px) minmax(160px,330px) auto;
 align-items:end;justify-content:start;gap:8px}
.jsl-tools #jslAdd,.jsl-actions #jslSave{justify-self:start;color:var(--ink);background:var(--tint)}
#jslEditor{flex:none;background:var(--surface);border:1px solid var(--line);border-radius:10px;padding:10px;display:grid;gap:8px}
#jslEditor h2{font-size:15px;margin:0}
.jsl-fields{display:grid;grid-template-columns:minmax(0,1.4fr) repeat(2,minmax(0,1fr)) minmax(100px,.6fr);gap:8px}
.jsl-actions{display:flex;justify-content:flex-end;gap:6px}
#jslStatus{margin:0;color:var(--muted);font-size:12px;overflow-wrap:anywhere}
#jslStatus:empty{display:none}
#jslList{min-height:0;overflow:auto;overscroll-behavior:contain;margin:0;padding:0;list-style:none}
.jsl-row{display:grid;grid-template-columns:minmax(0,1fr) minmax(0,24%) auto;align-items:center;
 min-height:56px;gap:8px;padding:6px 1px;border-bottom:1px solid var(--line)}
.jsl-row a{min-width:0;display:grid;gap:3px;color:var(--ink);text-decoration:none;padding:4px}
.jsl-row a:is(:hover,:focus-visible) b{text-decoration:underline}
.jsl-row :is(b,small){overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.jsl-row small,.jsl-row-meta{font-size:12px;color:var(--muted)}
.jsl-row-meta{display:flex;justify-content:flex-start;gap:6px;min-width:0}
.jsl-row-meta small:first-child{flex:none}
@media(max-width:650px){
 .jsl-tools{grid-template-columns:minmax(0,1fr) auto;justify-content:stretch}
 .jsl-tools label:nth-child(2){grid-row:2;grid-column:1/-1}
 .jsl-fields{grid-template-columns:repeat(2,minmax(0,1fr))}
 #jslAddress{grid-column:1/-1}
 .jsl-row{grid-template-columns:minmax(0,1fr) auto;gap:4px 6px}
 .jsl-row-meta{grid-column:1;grid-row:2;padding-inline:4px 0}
 .jsl-row button{grid-column:2;grid-row:1/span 2}
}
'''

SCRIPT = r'''
function OASourceLibrary(invoke,openURL){
 const $=id=>document.getElementById(id),root=$('sourceLibrary'),project=$('jslProject'),search=$('jslSearch'),
   list=$('jslList'),status=$('jslStatus'),editor=$('jslEditor'),add=$('jslAdd'),save=$('jslSave'),
   url=$('jslUrl'),name=$('jslName'),topic=$('jslTopic'),kind=$('jslKind');
 const kinds={website:'网站',newsroom:'新闻室',section:'栏目',account:'账号',rss:'RSS'};
 const storeKey='jiusera.sources.project';
 const errors={SOURCE_INVALID_URL:'请输入有效的公开网址。',SOURCE_PUBLIC_URL_REQUIRED:'请输入公开网址。',
   SOURCE_STORAGE_INVALID:'信源文件无法读取。',SOURCE_FORMAT_UNSUPPORTED:'此信源库需要支持该格式的 Jiusera。',
   SOURCE_PRIVATE_URL_PARAMETER:'请使用无需登录的公用链接。',SOURCE_STALE_REVISION:'这条信源已更新，请重新打开编辑。',
   DIRECTOR_PROJECT_NOT_REGISTERED:'当前项目已不可用。',HOST_OPEN_LINK_UNAVAILABLE:'当前宿主无法打开链接，可复制网址。'};
 let epoch=0,sequence=0,revision=null,rows=[],editing=null,timer=0,writing=false;
 function node(tag,text){const item=document.createElement(tag);if(text)item.textContent=text;return item;}
 function message(value){OAUI.set(status,value);}
 function showError(error){message(errors[error.message]||'信源操作失败，请重试。');}
 function remember(){try{localStorage.setItem(storeKey,project.value);}catch(_){}}
 function resume(){try{return localStorage.getItem(storeKey)||'';}catch(_){return '';}}
 function render(){
   const term=search.value.trim().toLocaleLowerCase();
   const shown=rows.filter(row=>!term||[row.name,row.url,row.topic,OAUI.format(kinds[row.kind])]
     .some(value=>value.toLocaleLowerCase().includes(term)));
   list.replaceChildren();
   if(!shown.length){
     const empty=node('li');
     OAUI.set(empty,term?'没有匹配的信源。':'这个项目尚未收录信源。');
     if(project.value)list.append(empty);
     return;
   }
   const frag=document.createDocumentFragment();
   for(const row of shown){
     const li=node('li');li.className='jsl-row';li.dataset.source=row.id;
     const link=node('a');link.href=row.url;link.target='_blank';link.rel='noopener noreferrer';
     link.append(node('b',row.name),node('small',row.url));
     link.onclick=async event=>{
       event.preventDefault();
       try{await openURL(row.url);}catch(error){showError(error);}
     };
     const meta=node('div');meta.className='jsl-row-meta';
     meta.append(OAUI.label(kinds[row.kind]||'网站'));
     if(row.topic)meta.append(node('small',row.topic));
     const origin=node('small');OAUI.set(origin,row.origin==='codex'?'Codex 收录':'手动收录');meta.append(origin);
     const change=node('button');change.type='button';OAUI.set(change,'编辑');change.onclick=()=>edit(row,change);
     li.append(link,meta,change);frag.append(li);
   }
   list.append(frag);
 }
 function validate(){
   save.disabled=writing||!project.value||(editing?!name.value.trim():!url.value.trim());
 }
 function edit(row,trigger){
   editing={row,trigger};
   editor.hidden=false;add.setAttribute('aria-expanded','true');
   $('jslAddress').hidden=!!row;url.value='';
   name.value=row?.name||'';topic.value=row?.topic||'';kind.value=row?.kind||'website';
   OAUI.set($('jslEditorTitle'),row?'编辑信源':'添加信源');
   message('');validate();
   (row?name:url).focus();
 }
 function endEdit(focus=false){
   const trigger=editing?.trigger;editing=null;
   editor.hidden=true;add.setAttribute('aria-expanded','false');
   if(focus)(trigger?.isConnected?trigger:add).focus();
 }
 async function refresh(quiet=false){
   const id=project.value;if(!id)return;
   const scope=epoch,ticket=++sequence;
   try{
     const data=await invoke('own.sources.library',{action:'list',project_id:id,
         ...(quiet&&revision!==null?{known_revision:revision}:{})});
     if(scope!==epoch||ticket!==sequence||project.value!==id)return;
     if(data.state==='SOURCES'){revision=data.revision;rows=data.sources;render();}
   }catch(error){if(scope===epoch&&ticket===sequence&&!quiet)showError(error);}
 }
 function watch(){
   clearTimeout(timer);
   if(root.hidden||!project.value)return;
   timer=setTimeout(async()=>{
     if(!document.hidden&&!writing)await refresh(true);
     watch();
   },3000);
 }
 async function changeProject(clearSearch=true){
   ++epoch;sequence++;revision=null;rows=[];endEdit();message('');writing=false;add.disabled=!project.value;
   if(clearSearch)search.value='';search.disabled=!project.value;render();remember();
   if(project.value){await refresh();watch();}
 }
 async function submit(){
   if(save.disabled||!editing)return;
   const scope=epoch,id=project.value,current=editing.row,display=name.value.trim();
   const action=current?'edit':'add';
   const fields=current?{source_id:current.id,expected_revision:current.revision,name:display}:
     {url:url.value.trim(),origin:'user',...(display?{name:display}:{})};
   writing=true;validate();
   try{
     const result=await invoke('own.sources.library',{action,project_id:id,...fields,
        topic:topic.value.trim(),kind:kind.value});
     if(scope!==epoch)return;
     message(result.state==='SOURCE_EXISTS'?'已收录，已保留原记录。':'信源已保存。');
     search.value='';endEdit(true);await refresh();
   }catch(error){if(scope===epoch)showError(error);}
   finally{if(scope===epoch){writing=false;validate();}}
 }
 add.onclick=()=>edit(null,add);
 $('jslCancel').onclick=()=>endEdit(true);
 save.onclick=()=>void submit();
 editor.onkeydown=event=>{
   if(event.key==='Escape'){event.preventDefault();endEdit(true);}
   if(event.key==='Enter'&&event.target.matches('input')&&!event.isComposing){event.preventDefault();void submit();}
 };
 project.onchange=()=>void changeProject();
 url.oninput=name.oninput=validate;
 search.oninput=render;
 const visibility=()=>{if(!document.hidden&&!root.hidden&&project.value&&!writing)void refresh(true);};
 document.addEventListener('visibilitychange',visibility);
 return {async open(){
   root.hidden=false;add.disabled=true;search.disabled=true;
   const scope=++epoch;
   rows=[];revision=null;render();message('');
   try{
     const data=await invoke('video.director.read',{action:'projects'});
     if(root.hidden||scope!==epoch)return;
     const query=new URLSearchParams(location.search).get('project')||'';
     const previous=[query,project.value,resume()].find(id=>data.projects.some(row=>row.id===id));
     project.replaceChildren();
     for(const row of data.projects){
       const option=node('option',row.label||row.name);option.value=row.id;project.append(option);
     }
     if(previous)project.value=previous;
     if(!data.projects.length){message('在 Codex 关联项目后即可收录信源。');return;}
     await changeProject(false);
   }catch(error){if(scope===epoch)showError(error);}
 },close(){
   clearTimeout(timer);epoch++;sequence++;endEdit();root.hidden=true;
 }};
}
'''
