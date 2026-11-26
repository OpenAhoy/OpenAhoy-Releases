"""Picture-message composer for the account selected in management."""

HTML = r'''
<section id="wechatPictures" class="panel" hidden>
 <h2>图片消息</h2>
 <p id="wxPictureAccount"></p>
 <div class="actions">
  <label>永久图片（1–20 张，第一张为封面）
    <input id="wxPictureFiles" type="file" accept="image/jpeg,image/png" multiple></label>
  <button id="wxPictureLoad" type="button">查找本号草稿</button>
 </div>
 <select id="wxPictureDraft" aria-label="选择图片消息草稿" hidden></select>
 <section id="wxPictureGroup" hidden><h3 class="oa-content-heading">合并本号草稿</h3>
  <div id="wxPictureGroupItems"></div>
  <label><input type="checkbox" id="wxPictureGroupConfirm"> 我确认合并所选草稿。新组核对一致后，微信草稿箱中的旧组将被移除。</label>
  <div class="actions">
   <button type="button" id="wxPictureMerge">合并所选草稿</button>
   <button type="button" id="wxPictureMergeStatus">查原合并</button>
  </div>
 </section>
 <ol id="wxPictureOrder"></ol>
 <label>标题 <input id="wxPictureTitle" maxlength="32"></label>
 <label>短文 <textarea id="wxPictureText" rows="4" maxlength="19999"></textarea></label>
 <div class="actions">
  <button id="wxPictureSave" type="button">保存图片消息</button>
  <button id="wxPictureRead" type="button">查回原请求</button>
  <button id="wxPicturePublish" type="button" hidden>普通发表</button>
  <button id="wxPicturePoll" type="button" hidden>查询原发表</button>
  <button id="wxPictureNotify" type="button" hidden>同时群发通知</button>
  <button id="wxPictureFallback" type="button" hidden>改为普通发表</button>
  <label id="wxPictureConfirmNotifyRow" hidden><input id="wxPictureConfirmNotify" type="checkbox"> 确认将本组图文群发给当前公众号的全部关注者</label>
  <button id="wxPictureNew" type="button">新建图片消息</button>
 </div>
 <p id="wxPictureStatus" aria-live="polite"></p>
 <ol id="wxPictureLinks"></ol>
</section>'''

SCRIPT = r'''
const OAWechatPictures=host=>{
 const el=id=>document.getElementById('wxPicture'+id),make=tag=>document.createElement(tag);
 const tool='own.wechat.content', entries=el('Order');
 let files=[],observed,observedHandle,publication,busy=false,account='',generation=0;
 let draft;
 const durable=(target,step)=>'jiusera.wechat.picture.'+target.connection_id+'.'+step;
 const copy=(key,...values)=>OAUI.message(key,...values);
 const note=value=>OAUI.set(el('Status'),value?'{0}':'',value);
 const usable=target=>target?.isCurrent()&&target.connection_id===account;
 function refresh(){
   const target=host.templateTarget(),next=target?.connection_id||'';
   if(next!==account){account=next;generation++;busy=false;reset();}
   if(target?.name)OAUI.raw(el('Account'),target.name);
   else OAUI.set(el('Account'),'先选择本号连接');
   controls();
 }
 function controls(){
   for(const id of ['Save','Read','Load','Draft','Files','Title','Text','Publish','Poll','New'])
     el(id).disabled=!account||busy;
   for(const control of el('Group').querySelectorAll('button,input'))control.disabled=!account||busy;
   const started=!!publication&&publication.state!=='NOT_ATTEMPTED';
   const hasSource=!!observed?.intent_handle;
   const notify=hasSource&&observed?.kind==='merge'&&!observed.contains_picture_messages&&!started;
   el('Publish').hidden=!hasSource||started;
   el('Poll').hidden=!hasSource&&!publication?.intent_handle;
   el('Notify').hidden=el('ConfirmNotifyRow').hidden=!notify;
   el('ConfirmNotify').disabled=busy||!account;
   el('Notify').disabled=busy||!account||!el('ConfirmNotify').checked;
   el('Fallback').hidden=!publication?.fallback_allowed;
   el('Fallback').disabled=busy||!account;
 }
 function reset(){
   files=[];draft=null;observed=null;observedHandle='';publication=null;el('ConfirmNotify').checked=false;
   for(const id of ['Title','Text','Files'])el(id).value='';
   el('Draft').replaceChildren();el('Draft').hidden=true;el('Links').replaceChildren();
   el('Group').hidden=true;el('Group').open=false;el('GroupItems').replaceChildren();el('GroupConfirm').checked=false;
   note('');renderFiles();
 }
 function renderFiles(){
   entries.replaceChildren();
   files.forEach((file,index)=>{
     const row=make('li'), label=make('span');
     if(index===0)OAUI.set(label,'封面 · {0}',file.name);else OAUI.raw(label,file.name);
     row.append(label);
     for(const [name,change,disabled] of [
       ['上移',()=>[files[index-1],files[index]]=[files[index],files[index-1]],index===0],
       ['下移',()=>[files[index],files[index+1]]=[files[index+1],files[index]],index===files.length-1],
       ['移除',()=>files.splice(index,1),false]]){
       const button=make('button');button.type='button';OAUI.set(button,name);
       button.disabled=disabled||busy;button.onclick=()=>{change();renderFiles();};row.append(' ',button);
     }
     entries.append(row);
   });
 }
 async function call(target,name,argumentsForCall){
   if(!usable(target))throw Error('公众号已切换');
   const reply=await host.templateCall(name,{...argumentsForCall,connection_id:target.connection_id});
   if(!usable(target))throw Error('公众号已切换');
   if(reply?.isError||!reply?.structuredContent)throw Error(reply?.structuredContent?.error||'未取得结果，请查询原请求');
   return reply.structuredContent;
 }
 async function run(task){
   const target=host.templateTarget();if(!usable(target)||busy)return;
   const ticket=generation;busy=true;controls();renderFiles();
   try{await task(target);}
   catch(error){if(usable(target))note(copy(error.message));}
   finally{if(generation===ticket){busy=false;controls();renderFiles();}}
 }
 async function data(file){
   const bytes=new Uint8Array(await file.arrayBuffer());let text='';
   for(let i=0;i<bytes.length;i+=8192)text+=String.fromCharCode(...bytes.subarray(i,i+8192));
   return btoa(text);
 }
 const save=()=>crypto.randomUUID();
 const contentStatus=value=>value.error_code!==undefined?copy('微信接口返回 {0}',value.error_code):copy({
   VERIFIED:'已查回并核对图片顺序',SAVED:'已保存到本号草稿箱',UNCHANGED:'已查回原草稿，内容相同',
   UNKNOWN:'微信结果未知，保留原请求',
   SOURCE_CHANGED:'平台草稿已修改，请重新载入',READBACK_MISMATCH:'微信读回内容有差异'
 }[value.state]||value.state);
 el('Files').onchange=()=>{
   const added=Array.from(el('Files').files);el('Files').value='';
   if(added.length+files.length>20){note(copy('最多 20 张图片'));return;}
   if(added.some(file=>!['image/jpeg','image/png'].includes(file.type)||!file.size||file.size>700*1024)){
     note(copy('此面板支持 700 KB 以内的 JPEG 或 PNG。较大的图片可交给 Codex 从本地文件导入。'));return;
   }
   files.push(...added);renderFiles();
 };
 el('Load').onclick=()=>run(async target=>{
   const inventory=await call(target,'own.drafts.inventory',{});
   const picker=el('Draft');
   const hint=make('option');OAUI.set(hint,'选择一条图片消息');hint.value='';
   picker.replaceChildren(hint);
   const groupItems=el('GroupItems');groupItems.replaceChildren();el('GroupConfirm').checked=false;
   for(const group of inventory.groups){
     const selection={inventory_handle:inventory.inventory_handle,index:group.index,
       expected_projection_sha256:group.projection_sha256,article_count:group.article_count};
     const groupLabel=make('label'),toggle=make('input');toggle.type='checkbox';
     toggle.value=JSON.stringify(selection);toggle.onchange=()=>{el('GroupConfirm').checked=false;};
     groupLabel.append(toggle,document.createTextNode(group.titles.join('、')));
     const line=make('div');line.append(groupLabel);groupItems.append(line);
     (group.article_types||[]).forEach((type,index)=>{
       if(type!=='newspic')return;
       const option=make('option');option.textContent=group.titles[index];
       option.value=JSON.stringify({selection,index});
       picker.append(option);
     });
   }
   picker.hidden=false;
   el('Group').hidden=inventory.groups.length<2;
   note(copy(picker.options.length>1?'已读取图片消息草稿':'本页没有图片消息草稿'));
 });
 function mergeResult(value){
   const message=({COMPLETED:'已合并并查回新草稿',ADD_UNKNOWN:'微信结果未知，保留原合并请求',
           ADD_REJECTED:'微信拒绝合并，原稿保留',PRESERVATION_MISMATCH:'新组内容有差异，原稿保留'})[value.state];
   note(message?copy(message):contentStatus(value));
   if(value.state==='COMPLETED'){
     observed=value;publication=null;el('ConfirmNotify').checked=false;el('Group').open=false;el('Group').hidden=true;
     el('Draft').replaceChildren();el('Draft').hidden=true;draft=null;
   }
 }
 el('MergeStatus').onclick=()=>run(async target=>{
   const request_key=localStorage.getItem(durable(target,'merge'));
   if(!request_key)throw Error('本号暂无原合并请求');
   mergeResult(await call(target,'own.drafts.current.status',{request_key}));
 });
 el('Merge').onclick=()=>run(async target=>{
   const selections=[...el('GroupItems').querySelectorAll('input:checked')].map(input=>JSON.parse(input.value));
   if(selections.length<2||selections.reduce((n,selection)=>n+selection.article_count,0)>8)
     throw Error('请选择至少 2 组，合计最多 8 篇');
   if(!el('GroupConfirm').checked)throw Error('请核对并确认所选草稿');
   const key=durable(target,'merge'),previous=localStorage.getItem(key);
   if(previous){
     let status;
     try{status=await call(target,'own.drafts.current.status',{request_key:previous});}
     catch(error){if(error.message!=='CURRENT_DRAFT_OPERATION_NOT_FOUND')throw error;}
     if(status&&!['COMPLETED','SOURCE_CHANGED','SOURCE_UNAVAILABLE','ADD_REJECTED'].includes(status.state))
       throw Error('请查原合并请求，原任务未终止时不另建草稿');
   }
   const request_key=save();localStorage.setItem(key,request_key);el('GroupConfirm').checked=false;
   mergeResult(await call(target,'own.drafts.current.merge',{request_key,selections}));
 });
 el('Draft').onchange=()=>run(async target=>{
   if(!el('Draft').value){draft=null;return;}
   draft=JSON.parse(el('Draft').value);
   const value=await call(target,'own.drafts.current.read',{selection:draft.selection,article_index:draft.index});
   const article=value.articles[draft.index],parts=[value.content];let next=value.next_content_offset;
   while(next!==null){
     const slice=await call(target,'own.drafts.current.read',{selection:draft.selection,article_index:draft.index,content_offset:next});
     parts.push(slice.content);next=slice.next_content_offset;
   }
   el('Title').value=article.title;el('Text').value=parts.join('');
   draft.photoCount=article.image_info.image_list.length;
   note(copy('原稿有 {0} 张图。可保留原图，或上传整组替换。',draft.photoCount));
 });
 el('Save').onclick=()=>run(async target=>{
   const title=el('Title').value.trim(),content=el('Text').value;
   if(!title||(!files.length&&!draft))throw Error('填写标题并选择至少一张图片');
   const image_handles=[];
   for(const file of files){
     file.requestKey ||= save();
     const row=await call(target,tool,{action:'upload_image',request_key:file.requestKey,
       source:{mime_type:file.type,base64:await data(file)}});
     if(row.state!=='MEDIA_READY'){note([contentStatus(row),row.operation_handle]);return;}
     image_handles.push(row.operation_handle);
   }
   const key=save();
   localStorage.setItem(durable(target,'request'),key);
   const article={title,content,...(image_handles.length?{image_handles}:{})};
   const action=draft?'update_picture':'create_picture';
   const original=await call(target,tool,{action,request_key:key,article,
     ...(draft?{selection:draft.selection,index:draft.index}:{})});
   observed=original;observedHandle=original.operation_handle;publication=null;el('ConfirmNotify').checked=false;
   localStorage.setItem(durable(target,'operation'),observedHandle);
   note(contentStatus(original));
 });
 el('Read').onclick=()=>run(async target=>{
   const key=localStorage.getItem(durable(target,'request'));
   const row=key?await call(target,tool,{action:'status_by_key',request_key:key}):null;
   const handle=row?.operation_handle||observedHandle;
   if(!handle)throw Error('本号暂无原请求');
   observed=await call(target,tool,{action:'readback',operation_handle:handle});
   observedHandle=handle;publication=null;el('ConfirmNotify').checked=false;note(contentStatus(observed));
   if(observed?.intent_handle){
     const status=await call(target,'own.publications.current.status',{intent_handle:observed.intent_handle});
     if(status.state!=='NOT_ATTEMPTED')showPublication(status);
   }
 });
 function showPublication(value){
   publication=value;note(OAWechatPublication.text(value));
   OAWechatPublication.links(el('Links'),value,url=>void host.openLink(url).catch(()=>note(copy('当前宿主无法打开链接'))));
 }
 const publish=(mode,fallback=false)=>run(async target=>{
   const handle=fallback?publication?.intent_handle:observed?.intent_handle;
   if(!handle||mode==='notify'&&!el('ConfirmNotify').checked)return;
   el('ConfirmNotify').checked=false;
   try{
     showPublication(await call(target,'own.publications.current.dispatch',{
        intent_handle:handle,mode,...(fallback?{fallback_from_notify:true}:{})}));
   }catch(error){
     const original=await call(target,'own.publications.current.status',{intent_handle:handle});
     if(original.state==='NOT_ATTEMPTED')throw error;
     showPublication(original);
   }
 });
 el('Publish').onclick=()=>publish('ordinary');
 el('Notify').onclick=()=>publish('notify');
 el('Fallback').onclick=()=>publish('ordinary',true);
 el('ConfirmNotify').onchange=controls;
 el('Poll').onclick=()=>run(async target=>{
   const handle=publication?.intent_handle||observed?.intent_handle;
   if(!handle)return;
   const original=await call(target,'own.publications.current.status',{intent_handle:handle});
   showPublication(original.state==='NOT_ATTEMPTED'||original.route==='MASS_SENDALL'&&!original.task_id?original:
     await call(target,'own.publications.current.poll',{intent_handle:original.intent_handle}));
 });
 el('New').onclick=()=>{reset();controls();};
 return {refresh};
};
'''
