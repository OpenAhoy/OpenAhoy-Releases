"""Official material, published-article, and message tools in account settings."""

HTML = r'''
<section id="wxContentTools" class="panel" hidden>
 <h2>素材与发布</h2>
 <p id="wxOpsAccount"></p>
 <div class="oa-tabs" role="tablist" aria-label="公众号内容工具">
  <button type="button" data-wx-pane="media" role="tab" aria-selected="true">素材</button>
  <button type="button" data-wx-pane="published" role="tab" aria-selected="false">已发表</button>
  <button type="button" data-wx-pane="message" role="tab" aria-selected="false">预览与群发</button>
 </div>
 <div id="wxOpsMedia">
  <div class="actions">
   <label>类型 <select id="wxOpsMediaType">
    <option value="image">图片</option><option value="voice">语音</option><option value="video">视频</option>
    <option value="news">图文素材</option></select></label>
   <button type="button" id="wxOpsMaterialList">读取永久素材</button>
   <button type="button" id="wxOpsMaterialCount">素材数量</button>
  </div>
  <div class="actions">
   <label>有效期 <select id="wxOpsMediaLife"><option value="permanent">永久</option><option value="temporary">临时</option></select></label>
   <label>本地文件 <input id="wxOpsFile" type="file" accept="image/png,image/jpeg,image/gif,audio/mpeg,audio/amr,video/mp4"></label>
   <button type="button" id="wxOpsUpload">上传到本号</button>
  </div>
  <div id="wxOpsVideoFields" hidden>
   <label>视频标题 <input id="wxOpsVideoTitle"></label>
   <label>视频简介 <input id="wxOpsVideoDescription"></label>
  </div>
  <ol id="wxOpsMaterialRows"></ol>
  <div id="wxOpsMediaView"></div>
 </div>
 <div id="wxOpsPublished" hidden>
  <button type="button" id="wxOpsPublishedList">读取本号已发表</button>
  <ol id="wxOpsPublishedRows"></ol>
  <article id="wxOpsPublishedBody" style="white-space:pre-wrap;overflow-wrap:anywhere"></article>
 </div>
 <div id="wxOpsMessage" hidden>
  <label>方式 <select id="wxOpsMode"><option value="preview">预览给一人</option>
    <option value="openid-preview">预览给一个 OpenID</option>
    <option value="tag">按标签群发</option><option value="all">全部关注者</option>
    <option value="openids">按 OpenID 群发（认证服务号）</option></select></label>
  <label id="wxOpsRecipientLabel"><span id="wxOpsRecipientText">微信号</span> <input id="wxOpsRecipient" autocomplete="off"></label>
  <label id="wxOpsOpenIDLabel" hidden>本号 OpenID 名单（每行一个，2–10,000 个）
   <textarea id="wxOpsOpenIDs" rows="3" autocomplete="off" spellcheck="false"></textarea></label>
  <label>消息类型 <select id="wxOpsMessageType"><option value="text">纯文本</option><option value="mpnews">图文</option>
   <option value="image">图片</option><option value="voice">语音</option><option value="mpvideo">视频</option>
   <option value="music">音乐（预览）</option><option value="wxcard">卡券</option></select></label>
  <label><span id="wxOpsMessageLabel">消息正文</span> <textarea id="wxOpsMessageBody" rows="3"></textarea></label>
  <div class="actions" id="wxOpsDraftPicker" hidden>
   <button type="button" id="wxOpsLoadDrafts">读取本号图文草稿</button>
   <select id="wxOpsDraft" aria-label="选择图文草稿"></select>
  </div>
  <p id="wxOpsDraftNotice" hidden>微信可能在图文群发成功后移除所用草稿。请核对受众并确认。</p>
  <label><input type="checkbox" id="wxOpsConfirm"> 我已核对当前账号、内容和接收范围</label>
  <div class="actions"><button type="button" id="wxOpsDeliver">发送预览</button>
   <button type="button" id="wxOpsMessageStatus">查原请求</button></div>
 </div>
 <p id="wxOpsStatus" aria-live="polite"></p>
</section>'''

SCRIPT = r'''
const OAWechatContentTools=host=>{
 const el=id=>document.getElementById('wxOps'+id),section=document.getElementById('wxContentTools');
 const make=tag=>document.createElement(tag),tool='own.wechat.content';
 let account='',busy=false,epoch=0,active='media',objectURL=null;
 const key=(target,action)=>'jiusera.wechat.content.'+target.connection_id+'.'+action;
 const copy=(key,...values)=>OAUI.message(key,...values);
 const note=text=>OAUI.set(el('Status'),text?'{0}':'',text);
 const valid=target=>target?.isCurrent()&&target.connection_id===account;
 function buttons(){
   for(const control of section.querySelectorAll('button[id]'))control.disabled=!account||busy;
 }
 function refresh(){
   const target=host.templateTarget(),id=target?.connection_id||'';
   if(id!==account){
     account=id;epoch++;busy=false;
     for(const name of ['MaterialRows','MediaView','PublishedRows','PublishedBody'])el(name).replaceChildren();
     for(const name of ['File','Recipient','OpenIDs','MessageBody','VideoTitle','VideoDescription'])el(name).value='';
     el('Draft').replaceChildren();
     if(objectURL){URL.revokeObjectURL(objectURL);objectURL=null;}
     el('Confirm').checked=false;note('');
   }
   if(target?.name)OAUI.raw(el('Account'),target.name);
   else OAUI.set(el('Account'),'先选择一个公众号');
   buttons();
 }
 async function run(task){
   const target=host.templateTarget();if(!valid(target)||busy)return;
   const start=epoch;busy=true;buttons();
   const call=async (name,args)=>{
     if(!valid(target))throw Error('公众号已切换');
     const reply=await host.templateCall(name,{connection_id:target.connection_id,...args});
     if(!valid(target))throw Error('公众号已切换');
     if(reply.isError||!reply.structuredContent)throw Error(reply.structuredContent?.error||'未取得结果，请查原请求');
     return reply.structuredContent;
   };
   const invoke=(action,args={})=>call(tool,{action,...args});
   try{await task(invoke,target,call);}
   catch(error){if(valid(target))note(copy(error.message));}
   finally{if(start===epoch){busy=false;buttons();}}
 }
 function status(value){
   if(value.error_code!==undefined)return copy('微信返回 {0}',value.error_code);
   return copy({OBSERVED:'已读回',ACCEPTED:'微信已受理，等待平台结果',PREVIEW_ACCEPTED:'微信已受理预览',UNKNOWN:'结果未知，保留原请求',
     SOURCE_CHANGED:'草稿已变化，请重新读取并确认',
     MEDIA_READY:'已上传',COMPLETED:'已完成'}[value.state]||value.state);
 }
 function resultButton(label,action){
   const b=make('button');b.type='button';OAUI.set(b,label);b.onclick=action;return b;
 }
 function tab(name){
   active=name;
   for(const t of section.querySelectorAll('[data-wx-pane]')){
     const id=t.dataset.wxPane,shown=id===active;
     t.setAttribute('aria-selected',String(shown));
     el(id.charAt(0).toUpperCase()+id.slice(1)).hidden=!shown;
   }
 }
 for(const t of section.querySelectorAll('[data-wx-pane]'))t.onclick=()=>tab(t.dataset.wxPane);
 el('MaterialCount').onclick=()=>run(async call=>{
   const result=await call('material_counts'),c=result.counts||{};
   note(result.error_code!==undefined?status(result):[status(result),
     copy('图片 {0} · 语音 {1} · 视频 {2} · 图文 {3}',c.image_count??'—',c.voice_count??'—',c.video_count??'—',c.news_count??'—')]);
 });
 async function materialBlob(value,read){
   const parts=[],limit=10*1024*1024;
   const decode=src=>Uint8Array.from(atob(src),x=>x.charCodeAt(0));
   if(!Number.isSafeInteger(value.bytes)||value.bytes<1||value.bytes>limit)throw Error('素材大小无法核对');
   if(value.base64)parts.push(decode(value.base64));
   else{
     let offset=0;
     while(offset<value.bytes){
       const result=await read('material_bytes',{read_handle:value.read_handle,offset});
       const bytes=decode(result.base64),next=offset+bytes.length;
       if(result.offset!==offset||!bytes.length||next>value.bytes||
         result.next_offset!==(next===value.bytes?null:next)||result.sha256!==value.sha256||result.bytes!==value.bytes)
         throw Error('素材分段校验失败，请重新读取');
       parts.push(bytes);offset=next;
     }
   }
   const blob=new Blob(parts,{type:value.mime_type});
   if(blob.size!==value.bytes)throw Error('素材大小无法核对');
   if(crypto.subtle){
     const sum=new Uint8Array(await crypto.subtle.digest('SHA-256',await blob.arrayBuffer()));
     if(Array.from(sum,b=>b.toString(16).padStart(2,'0')).join('')!==value.sha256)throw Error('素材摘要不匹配');
   }
   return blob;
 }
 async function showMaterial(value,read){
   const view=el('MediaView'),generation=epoch;
   let media,blob;
   if(value.mime_type&&(value.base64||value.read_handle)){
     media=make(value.mime_type.startsWith('image/')?'img':value.mime_type.startsWith('audio/')?'audio':'video');
     blob=await materialBlob(value,read);
   }else if(value.details){
     media=make('p');
     const description=value.details.title||value.details.description;
     if(description)OAUI.raw(media,description);else OAUI.set(media,'微信已返回素材信息');
   }
   if(generation!==epoch)return;
   if(objectURL){URL.revokeObjectURL(objectURL);objectURL=null;}
   view.replaceChildren();
   if(blob){
     objectURL=URL.createObjectURL(blob);
     media.src=objectURL;media.controls=true;media.style.maxWidth='100%';
     if(media.tagName==='IMG')OAUI.attr(media,'alt','微信素材原件');
   }
   if(media)view.append(media);
   note(status(value));
 }
 el('MaterialList').onclick=()=>run(async call=>{
   const result=await call('list_materials',{media_type:el('MediaType').value});
   const box=el('MaterialRows');box.replaceChildren();
   for(const asset of result.items||[]){
     const row=make('li');row.textContent=asset.name||asset.media_id;
     if(asset.media_id)row.append(' ',resultButton('查看',()=>run(async read=>{
       await showMaterial(await read('material_details',{media_id:asset.media_id}),read);
     })));
     box.append(row);
   }
   note([status(result),copy('本页 {0} 条',result.items?.length||0)]);
 });
 function syncMedia(){
   el('VideoFields').hidden=el('MediaType').value!=='video'||el('MediaLife').value!=='permanent';
 }
 el('MediaType').onchange=el('MediaLife').onchange=syncMedia;
 el('Upload').onclick=()=>run(async (call,target)=>{
   const file=el('File').files[0],type=el('MediaType').value,lifetime=el('MediaLife').value;
   if(!file||!file.size||file.size>700*1024||type==='news')throw Error('请选择 700 KB 以内的本地图片、语音或视频');
   const bytes=new Uint8Array(await file.arrayBuffer());let text='';
   for(let i=0;i<bytes.length;i+=8192)text+=String.fromCharCode(...bytes.subarray(i,i+8192));
   const req=crypto.randomUUID();localStorage.setItem(key(target,'media'),req);
   const result=await call('upload_media',{request_key:req,media_type:type,lifetime,mime_type:file.type,base64:btoa(text),
     ...(type==='video'&&lifetime==='permanent'?{video_description:{title:el('VideoTitle').value,introduction:el('VideoDescription').value}}:{})});
   note([status(result),copy('素材回执 {0}',result.operation_handle)]);
   if(result.state==='MEDIA_READY'&&lifetime==='temporary'){
     const handle={operation_handle:result.operation_handle};
     const preview=(title,action)=>resultButton(title,()=>run(async read=>showMaterial(await read(action,handle),read)));
     const buttons=el('MaterialRows');const row=make('li');
     row.append(preview('查看此临时素材','temporary_details'));
     if(type==='voice')row.append(' ',preview('读取高清语音','high_quality_voice'));
     buttons.prepend(row);
   }
 });
 el('PublishedList').onclick=()=>run(async call=>{
   const value=await call('list_published'),list=el('PublishedRows');list.replaceChildren();
   for(const group of value.items||[]){
     (group.content?.news_item||[]).forEach((row,i)=>{
       const item=make('li');
       if(row.title)OAUI.raw(item,row.title);else OAUI.set(item,'已发表作品');
       item.append(' ',resultButton('读全文',()=>run(async read=>{
         const parts=[];let offset=0;
         while(offset!==null){
           const result=await read('read_published',{article_id:group.article_id,index:i+1,content_offset:offset});
           if(result.error_code!==undefined){note(status(result));return;}
           const inert=make('template');inert.innerHTML=result.content;
           parts.push(inert.content.textContent);offset=result.next_content_offset;
         }
         el('PublishedBody').textContent=parts.join('\n');note(copy('已读回正文'));
       })));list.append(item);
     });
   }
   note([status(value),copy('本页 {0} 组',value.items?.length||0)]);
 });
 function syncDelivery(){
   const mode=el('Mode').value,kind=el('MessageType').value;
   const preview=mode==='preview'||mode==='openid-preview';
   OAUI.set(el('RecipientText'),mode==='preview'?'微信号':mode==='openid-preview'?'OpenID':mode==='tag'?'标签 ID':'');
   el('RecipientLabel').hidden=mode==='all'||mode==='openids';
   el('OpenIDLabel').hidden=mode!=='openids';
   OAUI.set(el('Deliver'),preview?'发送预览':'提交群发');
   el('DraftPicker').hidden=kind!=='mpnews';
   el('DraftNotice').hidden=kind!=='mpnews'||preview||!el('Draft').value;
   el('MessageLabel').parentElement.hidden=kind==='mpnews'&&!!el('Draft').value;
   OAUI.set(el('MessageLabel'),kind==='text'?'消息正文':kind==='music'?'微信音乐素材 ID':
       kind==='wxcard'?'卡券 ID':kind==='image'&&!preview?'图片素材回执（每行一个）':'本号素材回执');
 }
 el('LoadDrafts').onclick=()=>run(async (read,target,call)=>{
   const value=await call('own.drafts.inventory',{});
   const hint=make('option');hint.value='';OAUI.set(hint,'选择草稿或输入已有图文素材回执');
   el('Draft').replaceChildren(hint);
   for(const group of value.groups||[]){
     if(group.article_types?.some(type=>type!=='news'))continue;
     const option=make('option');option.textContent=group.titles.join('、');
     option.value=JSON.stringify({inventory_handle:value.inventory_handle,index:group.index,
       expected_projection_sha256:group.projection_sha256,article_count:group.article_count});
     el('Draft').append(option);
   }
   el('Confirm').checked=false;syncDelivery();
   note(copy(el('Draft').options.length>1?'已读取本页图文草稿':'本页没有可选图文草稿'));
 });
 el('Mode').onchange=el('MessageType').onchange=el('Draft').onchange=()=>{el('Confirm').checked=false;syncDelivery();};
 for(const control of ['Recipient','OpenIDs','MessageBody'])el(control).oninput=()=>{el('Confirm').checked=false;};
 el('Deliver').onclick=()=>run(async (call,target)=>{
   if(!el('Confirm').checked)throw Error('请先核对接收范围');
   const mode=el('Mode').value,kind=el('MessageType').value,text=el('MessageBody').value.trim();
   const preview=mode==='preview'||mode==='openid-preview', action=preview?'preview_message':'send_broadcast';
   if(kind==='music'&&!preview)throw Error('官方群发文档未给出音乐消息对象');
   const input=el('Recipient').value.trim();
   if(mode!=='all'&&mode!=='openids'&&!input)throw Error('请填写接收者或标签 ID');
   if(mode==='tag'&&!/^\d+$/.test(input))throw Error('标签 ID 必须是数字');
   const openids=mode==='openids'?el('OpenIDs').value.trim().split(/\s+/):null;
   if(openids&&(openids.length<2||openids.length>10000||new Set(openids).size!==openids.length))
     throw Error('请填写 2–10,000 个不同的本号 OpenID');
   const draft=kind==='mpnews'&&el('Draft').value;
   const message=kind==='text'?{kind,text}:kind==='music'?{kind,music_media_id:text}:kind==='wxcard'?{kind,card:{card_id:text}}:
     kind==='image'&&!preview?{kind,image_handles:text.split(/\s+/)}:
     {kind,media:draft?{draft_selection:JSON.parse(draft)}:{media_handle:text}};
   const previous=localStorage.getItem(key(target,'delivery'));
   if(previous){
     let row;
     try{row=await call('status_by_key',{request_key:previous});}
     catch(error){if(error.message!=='CURRENT_DRAFT_OPERATION_NOT_FOUND')throw error;}
     if(row?.state==='UNKNOWN'||row?.state==='PREPARED')throw Error('请先查回原请求，结果未知时不重复发送');
   }
   const req=crypto.randomUUID();localStorage.setItem(key(target,'delivery'),req);el('Confirm').checked=false;
   const result=await call(action,{request_key:req,confirm:true,message,...(mode==='preview'?
     {recipient:{wechat_name:input}}:mode==='openid-preview'?{recipient:{openid:input}}:
     {campaign:req,audience:mode==='all'?{all_followers:true}:mode==='openids'?{openids}:{tag_id:Number(input)}})});
   note(status(result));
   if(result.state==='ACCEPTED')el('OpenIDs').value='';
 });
 el('MessageStatus').onclick=()=>run(async (call,target)=>{
   const request_key=localStorage.getItem(key(target,'delivery'));
   if(!request_key)throw Error('本号暂无预览或群发请求');
   const result=await call('status_by_key',{request_key});
   if(result.kind==='send_broadcast'&&result.state==='ACCEPTED'){
     const final=await call('broadcast_status',{operation_handle:result.operation_handle});
     const outcome={SEND_SUCCESS:'发送成功',SENDING:'发送中',SEND_FAIL:'发送失败',DELETE:'已撤下'}[final.status];
     note(outcome?copy(outcome):status(final));return;
   }
   note(status(result));
 });
 syncDelivery();
 return {refresh};
};
'''
