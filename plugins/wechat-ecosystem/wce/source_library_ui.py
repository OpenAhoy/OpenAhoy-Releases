"""Independent asset view for project source entrances."""
HTML = '''
<section id="sourceLibrary" aria-label="信源库" hidden>
 <div class="jsl-tools">
   <label><span>项目</span><select id="jslProject"></select></label>
   <label><span>公众号</span><select id="jslAccount"></select></label>
   <label><span>搜索信源</span><input id="jslSearch" type="search" placeholder="名称、网址或主题"></label>
   <button id="jslAdd" type="button" aria-controls="jslEditor" aria-expanded="false">添加信源</button>
 </div>
 <p id="jslStorage" hidden></p>
 <div class="jsl-scope-actions" id="jslScopeActions" hidden>
   <label><input type="checkbox" id="jslStrict"><span>严格校验稿件来源</span></label>
   <details id="jslScan">
     <summary>检查新闻更新</summary>
     <div class="jsl-scan-actions">
       <label><span>起始日（UTC）</span><input type="date" id="jslSince"></label>
       <button type="button" id="jslScanStart">检查至现在</button>
       <button type="button" id="jslScanResume" hidden>续查原轮</button>
     </div>
     <p id="jslScanStatus" role="status"></p><ol id="jslScanRows"></ol>
   </details>
 </div>
 <div id="jslEditor" class="jsl-editor" hidden>
   <h2 id="jslEditorTitle">添加信源</h2>
   <div class="jsl-fields">
     <label id="jslAddress"><span>入口网址</span><input id="jslUrl" type="url" placeholder="https://" maxlength="4096"></label>
     <label><span>显示名称</span><input id="jslName" type="text" maxlength="160"><small id="jslNameRequired" hidden>编辑时必须填写名称。</small></label>
     <label><span>主题</span><input id="jslTopic" type="text" maxlength="180"></label>
     <label><span>类型</span><select id="jslKind">
       <option value="website">网站</option><option value="newsroom">新闻室</option>
       <option value="section">栏目</option><option value="account">账号</option><option value="rss">RSS</option>
     </select></label>
     <label id="jslReview" hidden><span>审核状态</span><select id="jslReviewState">
       <option value="pending">待审核</option><option value="approved">已审核</option><option value="rejected">不采用</option>
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
#videoDirectorDesk:has(#sourceLibrary:not([hidden])) :is(#directorSound,#directorMore){display:none}
#sourceLibrary button{min-height:32px}
#sourceLibrary :is(input,select){width:100%;min-width:0;color:var(--ink);background:var(--surface);
 border:1px solid var(--line);border-radius:7px;padding:6px 8px;min-height:34px}
#sourceLibrary label{min-width:0;display:grid;gap:3px}
#sourceLibrary label span{font-size:12px;color:var(--muted)}
.jsl-tools{display:grid;grid-template-columns:repeat(2,minmax(110px,180px)) minmax(120px,300px) auto;
 align-items:end;justify-content:start;gap:8px}
#jslStorage,#jslScanStatus{margin:0;color:var(--muted);font-size:12px;overflow-wrap:anywhere}
.jsl-scope-actions,.jsl-scan-actions{display:flex;gap:8px;align-items:start;flex-wrap:wrap}
#jslScopeActions>label{display:flex;align-items:center}
#jslScopeActions input[type=checkbox]{width:auto;min-height:0}
#jslScan{flex:1;min-width:190px}
#jslScan summary{cursor:pointer;font-weight:650}
#jslScan[open]{max-height:min(36dvh,290px);overflow:auto;padding:3px 5px}
.jsl-scan-actions{padding:6px 0;align-items:end}
#jslScanRows{margin:6px 0;padding-inline-start:22px;font-size:12px}
#jslScanRows li{padding:3px 0;overflow-wrap:anywhere}
#jslScanRows a{color:var(--ink);text-decoration:underline}
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
 .jsl-tools label:nth-child(3){grid-row:2;grid-column:1}
 .jsl-tools #jslAdd{grid-column:2;grid-row:2}
 .jsl-fields{grid-template-columns:repeat(2,minmax(0,1fr))}
 #jslAddress{grid-column:1/-1}
 .jsl-row{grid-template-columns:minmax(0,1fr) auto;gap:4px 6px}
 .jsl-row-meta{grid-column:1;grid-row:2;padding-inline:4px 0}
 .jsl-row button{grid-column:2;grid-row:1/span 2}
}
'''

SCRIPT = r'''
function OASourceLibrary(invoke,openURL,accountChoices){
 const $=id=>document.getElementById(id),root=$('sourceLibrary'),project=$('jslProject'),account=$('jslAccount'),search=$('jslSearch'),
   list=$('jslList'),status=$('jslStatus'),editor=$('jslEditor'),add=$('jslAdd'),save=$('jslSave'),
   url=$('jslUrl'),name=$('jslName'),topic=$('jslTopic'),kind=$('jslKind');
 const kinds={website:'网站',newsroom:'新闻室',section:'栏目',account:'账号',rss:'RSS'};
 const storeKey='jiusera.sources.project',accountKey='jiusera.sources.account';
 const strict=$('jslStrict'),scan=$('jslScan'),scanList=$('jslScanRows'),since=$('jslSince');
 const scanStart=$('jslScanStart'),scanResume=$('jslScanResume');
 const scopeArgs=()=>account.value?{connection_id:account.value}:{};
 const reviews={pending:'待审核',approved:'已审核',rejected:'不采用'};
 const scanStates={new:'发现新增',no_update:'本次未见更新',failed:'读取失败',unscanned:'未扫描'};
 let currentScan=null,scanning=false;
 const scanKey=()=>['jiusera.sources.scan',project.value,account.value].join('.');
 function shortID(){return Array.from(crypto.getRandomValues(new Uint8Array(16)),n=>n.toString(16).padStart(2,'0')).join('');}
 function stash(key,value){try{localStorage.setItem(key,value);}catch(_){}}
 function load(key){try{return localStorage.getItem(key)||'';}catch(_){return '';}}
 function utc(value){return new Date(value).toISOString();}
 function scanMessage(text){OAUI.set($('jslScanStatus'),text);}
 function drawScan(){
   scanList.replaceChildren();
   scanStart.disabled=scanning||!account.value;
   scanResume.hidden=!currentScan?.rows.some(row=>['failed','unscanned'].includes(row.status));
   scanResume.disabled=scanning;
   if(!currentScan)return;
   const {rows,window}=currentScan;
   OAUI.set($('jslScanStatus'),'{0} / {1} 个入口已核查 · {2} — {3}',
     rows.filter(row=>row.status!=='unscanned').length,rows.length,window.since,window.through);
   for(const row of rows){
     const item=node('li');
     item.append(node('b',row.name),document.createTextNode(' · '+OAUI.format(scanStates[row.status])));
     if(row.attempted_at)item.append(document.createTextNode(' · '+row.attempted_at));
     if(row.error)item.append(document.createTextNode(' · '+row.error));
     if(row.articles?.length){
       const links=node('ul');
       for(const entry of row.articles){
         const li=node('li'),a=node('a',entry.title||entry.url);
         a.href=entry.url;a.rel='noopener noreferrer';
         a.onclick=event=>{event.preventDefault();openURL(entry.url).catch(showError);};
         li.append(a,document.createTextNode(' · '+entry.published_at));
         links.append(li);
       }
       item.append(links);
     }
     scanList.append(item);
   }
 }
 async function checkSources(resume){
   if(scanning||!account.value)return;
   const source=epoch,fields={project_id:project.value,...scopeArgs()};
   const scanId=resume?currentScan?.scan_id:shortID();
   if(!scanId||(!resume&&!since.value))return;
   scanning=true;drawScan();scanMessage('正在检查信源…');
   try{
     if(!resume){
       const window={since:utc(since.value+'T00:00:00Z'),through:utc(Date.now())};
       const initial=await invoke('own.sources.library',{action:'start_scan',...fields,scan_id:scanId,...window});
       if(source!==epoch)return;
       currentScan=initial;stash(scanKey(),scanId);drawScan();
     }
     const pending=currentScan.rows.filter(row=>row.status==='unscanned'||(resume&&row.status==='failed'))
       .map(row=>row.source_id);
     for(let offset=0;offset<pending.length&&source===epoch;offset+=4){
       const sourceIds=pending.slice(offset,offset+4);
       const result=await invoke('own.sources.library',{action:'check_scan',...fields,scan_id:scanId,
         limit:sourceIds.length,source_ids:sourceIds,...(resume?{retry_failed:true}:{})});
       if(source!==epoch)return;
       currentScan=result;drawScan();
     }
   }catch(error){if(source===epoch)showError(error);}
   finally{if(source===epoch){scanning=false;drawScan();}}
 }
 $('jslScanStart').onclick=()=>void checkSources(false);
 $('jslScanResume').onclick=()=>void checkSources(true);
 strict.onchange=async()=>{
   const token=epoch,desired=strict.checked;
   strict.disabled=true;
   try{
     await invoke('own.sources.library',{action:'configure',project_id:project.value,...scopeArgs(),
       expected_revision:revision,strict:desired});
     if(token===epoch)await refresh();
   }catch(error){if(token===epoch){strict.checked=!desired;showError(error);}}
   finally{if(token===epoch)strict.disabled=false;}
 };
 const errors={SOURCE_INVALID_URL:'请输入有效的公开网址。',SOURCE_PUBLIC_URL_REQUIRED:'请输入公开网址。',
   SOURCE_STORAGE_INVALID:'信源文件无法读取。',SOURCE_STORAGE_UNAVAILABLE:'无法打开当前项目或账号的信源目录。',
   SOURCE_ACCOUNT_NOT_BOUND:'这个公众号当前未绑定。',SOURCE_ACCOUNT_UNAVAILABLE:'无法核验当前公众号的绑定。',
   SOURCE_SCAN_WINDOW_INVALID:'时间范围须在过去 30 天内，且起始早于结束。',SOURCE_SCAN_CATALOG_LIMIT:'此版本每轮最多检查 100 个入口。',
   CONNECTION_BUSY:'这轮检查正在另一处运行。',SOURCE_NAME_REQUIRED:'编辑时必须填写名称。',SOURCE_FORMAT_UNSUPPORTED:'此信源库需要支持该格式的 Jiusera。',
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
     if(account.value)meta.append(OAUI.label(reviews[row.review||'pending']));
     const origin=node('small');OAUI.set(origin,row.origin==='codex'?'Codex 收录':'手动收录');meta.append(origin);
     const change=node('button');change.type='button';OAUI.set(change,'编辑');change.onclick=()=>edit(row,change);
     li.append(link,meta,change);frag.append(li);
   }
   list.append(frag);
 }
 function validate(){
   const missing=!!editing?.row&&!name.value.trim();
   $('jslNameRequired').hidden=!missing;name.required=!!editing?.row;
   save.disabled=writing||!project.value||(editing?.row?missing:!url.value.trim());
 }
 function edit(row,trigger){
   editing={row,trigger};
   editor.hidden=false;add.setAttribute('aria-expanded','true');
   $('jslAddress').hidden=!!row;url.value='';
   name.value=row?.name||'';topic.value=row?.topic||'';kind.value=row?.kind||'website';
   $('jslReview').hidden=!row||!account.value;$('jslReviewState').value=row?.review||'pending';
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
     const data=await invoke('own.sources.library',{action:'list',project_id:id,...scopeArgs(),
         ...(quiet&&revision!==null?{known_revision:revision}:{})});
     if(scope!==epoch||ticket!==sequence||project.value!==id)return;
     if(data.state==='SOURCES'){
       revision=data.revision;rows=data.sources;render();
       strict.checked=data.strict===true;strict.disabled=false;
       OAUI.set($('jslStorage'),'保存在项目内 · {0}',data.storage||'JiuseraAssets/Sources');
       $('jslStorage').hidden=false;
     }
   }catch(error){if(scope===epoch&&ticket===sequence)showError(error);}
 }
 function watch(){
   clearTimeout(timer);
   if(root.hidden||!project.value)return;
   timer=setTimeout(async()=>{
     if(!document.hidden&&!writing)await refresh(true);
     watch();
   },3000);
 }
 function populateAccounts(){
   const people=accountChoices();
   account.disabled=people===null;
   const selected=new URLSearchParams(location.search).get('connection_id')||load(accountKey);
   const shared=node('option');shared.value='';OAUI.set(shared,'项目共用');
   account.replaceChildren(shared);
   for(const item of people||[]){
     const option=node('option',item.label);option.value=item.id;account.append(option);
   }
   if(selected&&!Array.from(account.options).some(option=>option.value===selected)){
     const option=node('option');option.value=selected;
     OAUI.set(option,people===null?'正在读取公众号…':'已选公众号不可用');
     account.append(option);
   }
   account.value=selected;
 }
 async function changeProject(clearSearch=true){
   const token=++epoch;sequence++;revision=null;rows=[];endEdit();message('');writing=false;add.disabled=!project.value||account.disabled;
   $('jslStorage').hidden=true;
   $('jslScopeActions').hidden=!account.value;strict.checked=false;strict.disabled=true;
   currentScan=null;scanning=false;scan.open=false;scanMessage('');drawScan();
   since.value=utc(Date.now()-7*86400000).slice(0,10);
   if(clearSearch)search.value='';search.disabled=!project.value;render();remember();
   if(project.value&&!account.disabled){
     await refresh();
     if(token!==epoch)return;
     watch();
     const scanId=account.value&&load(scanKey());
     if(scanId){
       try{
         const result=await invoke('own.sources.library',{action:'read_scan',project_id:project.value,...scopeArgs(),scan_id:scanId});
         if(token===epoch){currentScan=result;drawScan();}
       }catch(error){if(token===epoch&&error.message!=='SOURCE_SCAN_NOT_FOUND')showError(error);}
     }
   }
 }
 async function submit(){
   if(save.disabled||!editing)return;
   const scope=epoch,id=project.value,current=editing.row,display=name.value.trim();
   const action=current?'edit':'add';
   const fields=current?{source_id:current.id,expected_revision:current.revision,name:display,...(account.value?{review:$('jslReviewState').value}:{})}:
     {url:url.value.trim(),origin:'user',...(display?{name:display}:{})};
   writing=true;validate();
   try{
     const result=await invoke('own.sources.library',{action,project_id:id,...scopeArgs(),...fields,
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
 account.onchange=()=>{stash(accountKey,account.value);void changeProject();};
 url.oninput=name.oninput=validate;
 search.oninput=render;
 const visibility=()=>{if(!document.hidden&&!root.hidden&&project.value&&!writing)void refresh(true);};
 document.addEventListener('visibilitychange',visibility);
 return {accountsChanged(){
   if(root.hidden||!project.value)return;
   const pending=account.disabled,previous=account.value;
   populateAccounts();
   if(pending||previous!==account.value)void changeProject(false);
 },async open(){
   root.hidden=false;add.disabled=true;search.disabled=true;
   const scope=++epoch;
   rows=[];revision=null;render();message('');
   try{
     const data=await invoke('video.director.read',{action:'projects'});
     if(root.hidden||scope!==epoch)return;
     const query=new URLSearchParams(location.search).get('project')||'';
     const previous=[query,project.value,resume()].find(id=>data.projects.some(row=>row.id===id));
     project.replaceChildren();
     populateAccounts();
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
