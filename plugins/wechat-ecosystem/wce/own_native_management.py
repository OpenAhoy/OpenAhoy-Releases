"""Static MCP App. Account data arrives through the standard parent bridge."""
from .own_native_management_contract import RESOURCE

MIME = 'text/html;profile=mcp-app'

SCRIPT = r'''
(() => {
 'use strict';
 const $=id=>document.getElementById(id),bridge=window.parent,pending=new Map();
 const allowed=new Set(['wce.ui.management.overview','wce.ui.platform.action','x.ui.action','xhs.ui.action','x.attempt.status','wce.ui.projects.action','own.templates.read','wce.ui.templates.download']);
 let counter=0,navigationEpoch=0,ready=false,closed=false,refreshing=false,launching=false,backendOpening=false,hostCapabilities={},rows=[],directory=[],selected='',activePlatform='';
 const notice=(text,error=false)=>{$('notice').textContent=text;$('notice').className='notice'+(error?' error':'');};
 const key=row=>JSON.stringify([row.platform_id,row.connection_id]);
 const platform=id=>directory.find(p=>p.id===id);
 const current=()=>rows.find(row=>key(row)===selected);
 const name=row=>row.presentation?.display_name||'账号资料暂不可用';
 const initializedEditors=new Set();let binding=null,xManagement=null,xhsManagement=null,projectContext=null,contextOpen=false;
 const localExports=new Map(),selectedByPlatform=new Map();let selectEpoch=0,platformEpoch=0,selectionIntent=0;
 const hostDownloadsUnknown=new Set();
 const originalSelection={platform:'',account:''};
 const editors=new Map(Object.entries(OAPlatformSettings).map(([id,adapter])=>[id,adapter.mount((operation,args)=>platformCall(id,operation,args),()=>{navigationEpoch++;},{
  templateCall:(name,args)=>tool(name,args),
  templateTarget(){const row=current(),capture=navigationEpoch;return row&&row.platform_id===id?{connection_id:row.connection_id,name:name(row),isCurrent:()=>!closed&&ready&&navigationEpoch===capture&&current()===row}:null;},
  async templateDownload(m,getBytes,{queryOnly=false,onDispatch=()=>{}}={}){
   if(hostCapabilities.downloadFile){
    if(queryOnly)throw new Error('TEMPLATE_DOWNLOAD_UNKNOWN');
    const raw=await getBytes();let binary='';for(const byte of raw)binary+=String.fromCharCode(byte);
    onDispatch();
    const result=await rpc('ui/download-file',{contents:[{type:'resource',resource:{uri:'openahoy-template://download/'+m.id+'/'+m.version,mimeType:'application/zip',blob:btoa(binary)}}]});
    if(!result||result.isError)throw new Error('TEMPLATE_DOWNLOAD_UNKNOWN');return {state:'HOST_DOWNLOADED'};
   }
   onDispatch();return content(await tool('wce.ui.templates.download',{template_id:m.id,version:m.version,manifest_sha256:m.manifest_sha256,action:queryOnly?'query':'write'}));
  },
  async openLink(url){
   if(!hostCapabilities.openLinks)throw new Error('HOST_OPEN_LINK_UNAVAILABLE');
   const result=await rpc('ui/open-link',{url});if(!result||result.isError)throw new Error('HOST_OPEN_LINK_FAILED');return result;
  },
  async downloadFile(text,filename,{connection_id,queryOnly=false}={}){
   const row=current();if(!row||row.connection_id!==connection_id)throw new Error('RULES_CONFIG_TARGET_CHANGED');
   if(hostCapabilities.downloadFile){
    if(queryOnly||hostDownloadsUnknown.has(row.connection_id))throw new Error('RULES_DOWNLOAD_UNKNOWN');
    let result;try{result=await rpc('ui/download-file',{contents:[{type:'resource',resource:{uri:'openahoy-config://download/'+encodeURIComponent(filename),mimeType:'application/json',text}}]});}
    catch(_){hostDownloadsUnknown.add(row.connection_id);throw new Error('RULES_DOWNLOAD_UNKNOWN');}
    if(!result||result.isError)throw new Error('RULES_DOWNLOAD_FAILED');return result;
   }
   // Only absent host capability uses the separately declared app-only export.
   // A refused or uncertain host download never comes through this path.
   let original=localExports.get(row.connection_id),query=!!original;
   if(queryOnly&&!original)throw new Error('RULES_EXPORT_ORIGINAL_UNAVAILABLE');
   if(!original){original={connection_id:row.connection_id,export_id:'config-'+[...crypto.getRandomValues(new Uint8Array(16))].map(v=>v.toString(16).padStart(2,'0')).join(''),configuration:text};localExports.set(row.connection_id,original);}
   try{
    const result=await platformCall(row.platform_id,'EXPORT_CONFIG',{...original,action:query?'query':'write'});
    if(result?.isError||!result?.structuredContent)throw new Error(result?.structuredContent?.error||'CONFIG_EXPORT_UNAVAILABLE');
    const value=result.structuredContent;
    if(value.export_id!==original.export_id)throw new Error('CONFIG_EXPORT_RESULT_UNKNOWN');
    if(value.state==='CONFIG_EXPORT_NOT_FOUND'){localExports.delete(row.connection_id);return value;}
    if(value.state!=='CONFIG_EXPORTED')return {state:'CONFIG_EXPORT_PENDING'};
    const bytes=new TextEncoder().encode(original.configuration),expected=[...new Uint8Array(await crypto.subtle.digest('SHA-256',bytes))].map(v=>v.toString(16).padStart(2,'0')).join('');
    if(value.sha256!==expected||value.utf8_bytes!==bytes.length||value.destination!=='Downloads'||value.filename!=='OpenAhoy-配置-'+original.export_id.slice(7)+'.json')throw new Error('CONFIG_EXPORT_RESULT_UNKNOWN');
    localExports.delete(row.connection_id);return {...value,from_query:query};
   }catch(error){
    if(['CONFIG_EXPORT_INVALID','CONFIG_EXPORT_ACCOUNT_MISMATCH'].includes(error.message)){localExports.delete(row.connection_id);throw new Error(error.message);}
    return {state:'CONFIG_EXPORT_PENDING'};
   }
  }
 })]));
 function dispose(){binding?.dispose();xManagement?.dispose();xhsManagement?.dispose();projectContext?.dispose();closed=true;ready=false;for(const editor of editors.values())editor.setReady(false);
   for(const p of pending.values()){clearTimeout(p.timer);p.reject(new Error('VIEW_CLOSED'));}pending.clear();
   for(const el of document.querySelectorAll('button,input,select,textarea'))el.disabled=true;
 }
 function rpc(method,params){return new Promise((resolve,reject)=>{
   if(closed){reject(new Error('VIEW_CLOSED'));return;}
   const id=++counter,timer=setTimeout(()=>{pending.delete(id);reject(new Error('HOST_TIMEOUT'));},35000);
   pending.set(id,{resolve,reject,timer});bridge.postMessage({jsonrpc:'2.0',id,method,params},'*');
 });}
 addEventListener('message',event=>{
   if(event.source!==bridge||event.data?.jsonrpc!=='2.0')return;
   const v=event.data;
   if(v.method==='ui/resource-teardown'){
     if(!Object.hasOwn(v,'id'))return;
     if(!['string','number'].includes(typeof v.id)||!v.params||typeof v.params!=='object'||Array.isArray(v.params)||Object.keys(v.params).length||Object.hasOwn(v,'result')||Object.hasOwn(v,'error')){
       bridge.postMessage({jsonrpc:'2.0',id:v.id,error:{code:-32602,message:'Invalid params'}},'*');return;
     }
     dispose();bridge.postMessage({jsonrpc:'2.0',id:v.id,result:{}},'*');return;
   }
   const item=pending.get(v.id);if(!item)return;clearTimeout(item.timer);pending.delete(v.id);
   if(v.method||v.error||!Object.hasOwn(v,'result'))item.reject(new Error('HOST_ERROR'));else item.resolve(v.result);
 });
 async function tool(name,args){if(!ready||!allowed.has(name))throw new Error('UI_TOOL_UNAVAILABLE');return rpc('tools/call',{name,arguments:args});}
 function content(result){if(result?.isError||!result?.structuredContent)throw new Error('MANAGEMENT_READ_FAILED');return result.structuredContent;}
 async function platformCall(id,operation,args){
   const p=platform(id);if(!p)throw new Error('PLATFORM_UNSUPPORTED');
   if(['READ_RULES','SAVE_RULES','RESTORE_RULES','EXPORT_CONFIG'].includes(operation)){
     if(!p.settings_supported||!editors.has(id))throw new Error('PLATFORM_SETTINGS_UNAVAILABLE');
     if((args.scope==='account'||operation==='EXPORT_CONFIG')&&!rows.some(row=>row.platform_id===id&&row.connection_id===args.connection_id))throw new Error('PLATFORM_ACCOUNT_MISMATCH');
   }else if(!['OPEN_BINDING','OPEN_SECURITY','BINDING_CHECK','BINDING_BEGIN','BINDING_SUBMIT','BINDING_STATUS','BINDING_CANCEL','BINDING_RESUME'].includes(operation)||!p.binding_supported)throw new Error('PLATFORM_BINDING_UNAVAILABLE');
   return tool('wce.ui.platform.action',{platform_id:id,operation,arguments:args});
 }
 function bindingPlatform(){return platform(activePlatform)||null;}
 function buttons(){
   const p=bindingPlatform(),row=current();
   $('accountBackend').parentElement.hidden=activePlatform!=='wechat_official_account';$('wechatBackendHelp').hidden=activePlatform!=='wechat_official_account';
   $('refresh').disabled=!ready||refreshing||launching;
   $('showAdd').disabled=!ready||launching||!p?.binding_supported;
   $('accountRules').disabled=!ready||refreshing||!row||!platform(row.platform_id)?.settings_supported||!editors.has(row.platform_id);
   $('accountImport').disabled=$('accountRules').disabled;
   $('accountCreate').disabled=$('accountRules').disabled;
   $('accountBackend').disabled=!ready||backendOpening||!row||!editors.get(row.platform_id)?.openBackend;
 }
 function showSettings(id){
   const p=platform(id),editor=editors.get(id),supported=!!p?.settings_supported&&!!editor;
   $('pageTitle').textContent=p?p.name:(id?'平台暂不可用':'选择平台');
   $('platformHelp').textContent=p?.settings_help||'';$('unsupportedSettings').hidden=supported;
   for(const el of document.querySelectorAll('#settingsPanel [data-platform-id]'))el.hidden=!supported||el.dataset.platformId!==id;
   $('xSettings').hidden=id!=='x';if(id==='x')$('unsupportedSettings').hidden=true;
   $('xhsSettings').hidden=id!=='xiaohongshu';if(id==='xiaohongshu')$('unsupportedSettings').hidden=true;
   $('contextSettingsTab').setAttribute('aria-selected',String(contextOpen));$('platformSettingsTab').setAttribute('aria-selected',String(!contextOpen));
   $('projectContextPanel').hidden=!contextOpen;
   if(contextOpen){$('wechatSettings').hidden=true;$('xSettings').hidden=true;$('xhsSettings').hidden=true;$('unsupportedSettings').hidden=true;}
   return supported;
 }
 async function selectPlatform(id,focus=false){
   const intent=++platformEpoch;navigationEpoch++;activePlatform=id;document.body.classList.remove('oa-x-tools');renderPlatforms();await renderAccounts();if(closed||intent!==platformEpoch||activePlatform!==id)return;showSettings(id);
   if(id==='x'&&ready&&!contextOpen)xManagement.activate();else xManagement.deactivate();
   if(id==='xiaohongshu'&&ready&&!contextOpen)xhsManagement.activate();else xhsManagement.deactivate();
   $('xCapabilities').hidden=id!=='x';
   if(focus)for(const el of $('platformNavigation').children)if(el.dataset.platformId===id)el.focus();
 }
 function avatar(row){
   const box=document.createElement('div');box.className='avatar';box.setAttribute('aria-label',name(row)+'，未设置头像');const a=row.presentation?.avatar;
   if(row.platform_id==='x'&&typeof row.profile_image_url==='string'&&/^https:\/\/pbs\.twimg\.com\/profile_images\/[A-Za-z0-9_./-]+$/.test(row.profile_image_url)){
    const img=document.createElement('img');img.src=row.profile_image_url;img.alt=name(row)+'头像';img.referrerPolicy='no-referrer';img.style.width=img.style.height='100%';box.append(img);return box;
   }
   if(a&&a.width===96&&a.height===96&&typeof a.rgba==='string'&&a.rgba.length===49152){try{const raw=atob(a.rgba);if(raw.length!==36864)throw new Error('AVATAR_INVALID');
     const canvas=document.createElement('canvas');canvas.width=canvas.height=96;canvas.style.width=canvas.style.height='100%';canvas.getContext('2d').putImageData(new ImageData(Uint8ClampedArray.from(raw,c=>c.charCodeAt(0)),96,96),0,0);box.append(canvas);box.setAttribute('aria-label',name(row)+'头像');return box;
   }catch(_){}}
   box.textContent=Array.from(name(row))[0]||'账';return box;
 }
 function card(row,choose=false){
   const el=document.createElement('div');el.className='account';el.style.display='flex';el.dataset.accountKey=key(row);
   const body=document.createElement('div');body.style.minWidth='0';const title=document.createElement(choose?'button':'strong');title.className=choose?'account-select':'account-title';title.textContent=name(row);
   if(choose){el.tabIndex=0;el.setAttribute('role','option');el.addEventListener('click',e=>{if(!e.target.closest('button,a')){selectionIntent++;select(key(row));}});el.addEventListener('keydown',e=>{if(e.target===el&&['Enter',' '].includes(e.key)){e.preventDefault();selectionIntent++;select(key(row));}});title.setAttribute('aria-pressed',String(key(row)===selected));title.addEventListener('click',()=>{selectionIntent++;select(key(row));});}
   const attribution=document.createElement('span');attribution.className='help';attribution.style.display='block';attribution.textContent=platform(row.platform_id)?.name||'未知平台 · 操作不可用';
   const state=document.createElement('span');state.className='status'+(['CONNECTED','BOUND_IDLE'].includes(row.state)?' good':'');state.textContent=({CONNECTED:'已连接',BOUND_IDLE:'已绑定 · 空闲',DISCONNECTED:'已断开',ACTION_REQUIRED:'需要处理',BUSY:'正在使用'}[row.state]||'状态待核对');
   body.append(title,attribution,state);el.append(avatar(row),body);return el;
 }
 async function select(id){
   const requested=rows.find(row=>key(row)===id),token=++selectEpoch;
   let target=requested;
   const editor=requested&&editors.get(requested.platform_id);
   if(ready&&requested&&initializedEditors.has(requested.platform_id)){
     const ok=await editor.selectScope(requested.connection_id);
     if(closed||token!==selectEpoch)return false;
     if(ok===false){target=rows.find(row=>row.platform_id===requested.platform_id&&row.connection_id===editor.scope?.());notice('原规则正在处理或结果待确认；已保留原规则目标，请先接续原操作。',true);}
   }
   id=target?key(target):'';
   navigationEpoch++;
   for(const editor of editors.values())editor.closeCreator();
   selected=rows.some(row=>key(row)===id)?id:'';if(selected)selectedByPlatform.set(activePlatform,selected);
   for(const el of $('accounts').children){const chosen=el.dataset.accountKey===selected;el.classList.toggle('is-selected',chosen);el.setAttribute('aria-selected',String(chosen));el.querySelector('button')?.setAttribute('aria-pressed',String(chosen));}
   const row=current();$('accountCurrent').replaceChildren();if(row){const text=document.createElement('span'),title=document.createElement('strong'),sub=document.createElement('small');title.textContent=name(row);sub.textContent=row.platform_id==='x'&&row.username?'@'+row.username:({CONNECTED:'已连接',BOUND_IDLE:'已绑定 · 空闲',DISCONNECTED:'已断开',BUSY:'正在使用',ACTION_REQUIRED:'需要处理'}[row.state]||'状态待核对');text.append(title,sub);$('accountCurrent').append(avatar(row),text);}else $('accountCurrent').textContent='平台默认规则 / 尚未选择账号';
   $('selectedAccount').replaceChildren();
   if(row){const line=document.createElement('p');line.className='account-id';line.textContent=typeof row.account_id==='string'?(platform(row.platform_id)?.account_id_label||'账号标识')+' '+row.account_id:'账号资料暂不可用';$('selectedAccount').append(line);}
   else{const p=document.createElement('p');p.textContent='选择一个账号，查看所属平台与设置。';$('selectedAccount').append(p);}
   projectContext?.target(activePlatform,row?.connection_id||'',rows);for(const editor of editors.values())editor.targetChanged?.();buttons();
 }
 async function renderAccounts(){
   const visible=rows.filter(row=>row.platform_id===activePlatform);
   $('accounts').replaceChildren();for(const row of visible)$('accounts').append(card(row,true));
   if(!visible.length){const p=document.createElement('p');p.className='empty';p.textContent=platform(activePlatform)?'此平台尚未绑定账号，点击“绑定账号”开始。':'当前没有可管理的账号。';$('accounts').append(p);}
   $('accountCount').textContent=String(visible.length);
   const remembered=selectedByPlatform.get(activePlatform)||selected;await select(visible.some(row=>key(row)===remembered)?remembered:(visible[0]?key(visible[0]):''));
 }
 function renderPlatforms(){
   const ids=[...new Set([...directory.map(p=>p.id),...rows.map(row=>row.platform_id),...(activePlatform?[activePlatform]:[])])];
   $('platformNavigation').replaceChildren();
   for(const id of ids){
     const p=platform(id),button=document.createElement('button');OAPlatformBranding.decorate(button,id,p?p.name:'原平台当前不可用');
     button.dataset.platformId=id;button.setAttribute('aria-current',id===activePlatform?'page':'false');
     button.addEventListener('click',()=>selectPlatform(id,true));$('platformNavigation').append(button);
   }
   if(!ids.length){const p=document.createElement('p');p.className='help';p.textContent='暂无可用平台';$('platformNavigation').append(p);}
 }
 async function refresh(){
   if(!ready||refreshing||launching)return;refreshing=true;buttons();notice('正在读取账号…');
   try{
     const value=content(await tool('wce.ui.management.overview',{}));if(closed)return;
     if(!Array.isArray(value.platforms)||value.platforms.some(p=>!p||typeof p.id!=='string'||typeof p.name!=='string'||typeof p.settings_supported!=='boolean'||typeof p.binding_supported!=='boolean')||new Set(value.platforms.map(p=>p.id)).size!==value.platforms.length)throw new Error('PLATFORM_INVALID_DIRECTORY');
     if(!Array.isArray(value.connections)||value.connections.some(row=>!row||typeof row.platform_id!=='string'||typeof row.connection_id!=='string'||(row.account_id!==undefined&&typeof row.account_id!=='string')||typeof row.state!=='string')||new Set(value.connections.map(key)).size!==value.connections.length)throw new Error('MANAGEMENT_INVALID_SNAPSHOT');
     directory=value.platforms;rows=value.connections;
     if(!activePlatform)activePlatform=directory[0]?.id||rows[0]?.platform_id||'';
     renderPlatforms();await renderAccounts();showSettings(activePlatform);
     for(const [id,editor]of editors){const own=rows.filter(row=>row.platform_id===id);editor.accounts(own,new Map(own.map(row=>[row.connection_id,name(row)])));}
     notice('已读取 '+rows.length+' 个账号；绑定状态不代表所有平台接口已实测。');
     for(const [id,editor]of editors){
       if(closed)return;
       if(platform(id)?.settings_supported&&!initializedEditors.has(id)){
         await editor.setReady(true);initializedEditors.add(id);const row=current();if(row?.platform_id===id)await select(key(row));
       }
     }
   }catch(_){if(!closed)notice('账号读取失败，已有显示可能不是最新状态；可点击刷新重试。',true);}
   finally{refreshing=false;buttons();}
 }
 binding=OAInlineBinding.mount(async(operation,args)=>content(await platformCall(originalSelection.platform,operation,args)),{
  enter(){originalSelection.platform=activePlatform;originalSelection.account=selected;$('nativeWorkspace').hidden=true;},
  leave(){$('nativeWorkspace').hidden=false;activePlatform=originalSelection.platform;select(originalSelection.account);},
  async complete(cid,existing=false,state='BOUND_IDLE'){$('nativeWorkspace').hidden=false;activePlatform=originalSelection.platform;await refresh();const row=rows.find(r=>r.connection_id===cid&&r.platform_id===activePlatform);if(row)await select(key(row));notice(state==='DISCONNECTED'?'原绑定已提交，账号当前已断开。':state==='ACTION_REQUIRED'?'原绑定已提交，当前账号需要处理，请查看账号状态。':existing?'账号已绑定，已选中原账号。':'已验证并绑定。');}
 });
 xManagement=OAXManagement.mount((operation,args)=>tool('x.ui.action',{operation,arguments:args}),async url=>{
  if(!hostCapabilities.openLinks)throw new Error('HOST_OPEN_LINK_UNAVAILABLE');const result=await rpc('ui/open-link',{url});if(!result||result.isError)throw new Error('HOST_OPEN_LINK_FAILED');return result;
 },async(cid,original)=>{await refresh();if(!closed&&original?.platform==='x'&&activePlatform==='x'&&original.epoch===platformEpoch&&original.intent===selectionIntent){const row=rows.find(r=>r.platform_id==='x'&&r.connection_id===cid);if(row)await select(key(row));}},{captureSelection:()=>({platform:activePlatform,epoch:platformEpoch,intent:selectionIntent})});
 xhsManagement=OAXHSManagement.mount((operation,args)=>tool('xhs.ui.action',{operation,...args}),refresh,()=>current()?.platform_id==='xiaohongshu'?current().connection_id:null);
 projectContext=OAProjectContext.mount((operation,args)=>tool('wce.ui.projects.action',{operation,arguments:args}),async text=>{
  if(!hostCapabilities.message?.text)throw new Error('HOST_MESSAGE_UNAVAILABLE');
  const result=await rpc('ui/message',{role:'user',content:[{type:'text',text}]});if(!result||typeof result!=='object'||Array.isArray(result)||(result.isError!==undefined&&typeof result.isError!=='boolean')||result.isError)throw new Error('HOST_MESSAGE_NOT_CONFIRMED');return result;
 },{readPost:(cid,attempt)=>tool('x.attempt.status',{connection_id:cid,kind:'post',attempt_id:attempt}),
  async downloadArtifact(raw,filename,a){
   const row=current();if(!row||row.platform_id!=='x'||row.connection_id!==a.connection_id)throw new Error('X_CONFIG_TARGET_CHANGED');
   if(hostCapabilities.downloadFile){
    if(a.queryOnly)throw new Error('X_CONFIG_DOWNLOAD_UNKNOWN');a.onDispatch();
    const result=await rpc('ui/download-file',{contents:[{type:'resource',resource:{uri:'openahoy-config://download/'+encodeURIComponent(filename),mimeType:a.artifact==='skill'?'text/markdown':'application/json',text:raw}}]});
    if(!result||result.isError)throw new Error('X_CONFIG_DOWNLOAD_UNKNOWN');return {state:'HOST_DOWNLOADED'};
   }
   const args={connection_id:a.connection_id,configuration:a.configuration,export_id:a.export_id,artifact:a.artifact,action:a.queryOnly?'query':'write'};a.onDispatch();
   const value=content(await tool('wce.ui.projects.action',{operation:'X_CONFIG_EXPORT',arguments:args}));
   if(value.state==='CONFIG_EXPORTED'){
    const bytes=new TextEncoder().encode(raw),hash=[...new Uint8Array(await crypto.subtle.digest('SHA-256',bytes))].map(x=>x.toString(16).padStart(2,'0')).join('');
    if(value.export_id!==a.export_id||value.sha256!==hash||value.utf8_bytes!==bytes.length||value.destination!=='Downloads')throw new Error('X_CONFIG_DOWNLOAD_UNKNOWN');
   }return value;
  }});
 document.querySelectorAll('[data-workspace-project]').forEach(button=>button.addEventListener('click',()=>$('contextSettingsTab').click()));
 $('xWorkspaceTools').onclick=()=>{document.body.classList.add('oa-x-tools');};
 $('xProductionEdit').addEventListener('click',()=>document.body.classList.remove('oa-x-tools'));
 const xBack=document.createElement('button');xBack.id='xWorkspaceBack';xBack.textContent='返回内容配置';xBack.className='oa-x-tools-back';xBack.onclick=()=>document.body.classList.remove('oa-x-tools');$('xSettings').prepend(xBack);
 const xCapabilities=document.createElement('details');xCapabilities.className='oa-capability-details';const xCaption=document.createElement('summary');xCaption.textContent='X 支持的自动能力';xCapabilities.append(xCaption,$('xCapabilities'));$('xSettings').prepend(xCapabilities);
 $('contextSettingsTab').addEventListener('click',()=>{contextOpen=true;showSettings(activePlatform);xManagement.deactivate();xhsManagement.deactivate();$('xCapabilities').hidden=activePlatform!=='x';projectContext.activate();});
 $('platformSettingsTab').addEventListener('click',()=>{contextOpen=false;projectContext.deactivate();showSettings(activePlatform);if(activePlatform==='x')xManagement.activate();if(activePlatform==='xiaohongshu')xhsManagement.activate();});
 async function secure(){if(!ready||!bindingPlatform()?.binding_supported)return;if(activePlatform==='xiaohongshu'){await xhsManagement.begin();return;}if(activePlatform==='x'){const intent=navigationEpoch;await xManagement.activate();if(!closed&&activePlatform==='x'&&navigationEpoch===intent)await xManagement.authorize();return;}await binding.open();}
 $('refresh').addEventListener('click',refresh);$('showAdd').addEventListener('click',secure);
 $('accountCreate').addEventListener('click',async()=>{
   const row=current(),original=selected,editor=row&&editors.get(row.platform_id);if(!editor||!platform(row.platform_id)?.settings_supported)return;
   const epoch=++navigationEpoch;
   const ok=await editor.openCreator(row.connection_id,name(row),()=>!closed&&selected===original&&activePlatform===row.platform_id&&navigationEpoch===epoch);
   if(ok&&!closed&&selected===original&&navigationEpoch===epoch){editor.showCreator();$('settingsPanel').scrollIntoView({block:'start'});}
 });
 $('accountBackend').addEventListener('click',async()=>{
   const row=current(),editor=row&&editors.get(row.platform_id);if(!ready||backendOpening||!editor?.openBackend)return;
   backendOpening=true;buttons();
   try{await editor.openBackend();notice('宿主已受理打开公众号后台；请核对浏览器当前账号，登录过期需在微信官方页面扫码。');}
   catch(error){notice(error.message==='HOST_OPEN_LINK_UNAVAILABLE'?'当前宿主未提供打开外链的能力，未打开公众号后台。':'宿主未能打开公众号后台，请稍后重试。',true);}
   finally{backendOpening=false;buttons();}
 });
 $('accountImport').addEventListener('click',()=>{
   const row=current(),original=selected,epoch=navigationEpoch,editor=row&&editors.get(row.platform_id);
   if(!editor||!platform(row.platform_id)?.settings_supported)return;
   editor.showRules();$('settingsPanel').scrollIntoView({block:'start'});
   editor.chooseConfiguration(row.connection_id,name(row),()=>!closed&&selected===original&&activePlatform===row.platform_id&&navigationEpoch===epoch);
 });
 $('accountRules').addEventListener('click',async()=>{
   const row=current(),original=selected,editor=row&&editors.get(row.platform_id);if(!editor||!platform(row.platform_id)?.settings_supported)return;
   const intent=++navigationEpoch;
   const ok=await editor.selectScope(row.connection_id);if(closed||selected!==original||navigationEpoch!==intent)return;
   if(ok===false){notice('规则正在处理或结果待确认，请在原规则范围接续。',true);return;}
   if(activePlatform===row.platform_id&&showSettings(row.platform_id)){editor.showRules();$('settingsPanel').scrollIntoView({block:'start'});}
 });
 addEventListener('pagehide',event=>{if(!event.persisted)dispose();});buttons();
 rpc('ui/initialize',{appInfo:{name:'openahoy-management',version:'3.0.0'},protocolVersion:'2026-01-26',appCapabilities:{availableDisplayModes:['inline','fullscreen']}})
 .then(async host=>{if(closed||host?.protocolVersion!=='2026-01-26'||!host.hostCapabilities?.serverTools)throw new Error('NO_SERVER_TOOLS');
   hostCapabilities=host.hostCapabilities;ready=true;projectContext.setReady(true,!!hostCapabilities.message?.text);bridge.postMessage({jsonrpc:'2.0',method:'ui/notifications/initialized'},'*');buttons();await refresh();
 }).catch(()=>{ready=false;buttons();notice('当前宿主管理工具桥不可用，未进行任何账号操作。',true);});
})();

'''


def resource():
    from .own_settings_ui import LOGO, STYLE
    from .own_management_ui import STYLE as management_style, native_page_body
    from .own_wechat_management import settings_html, settings_script
    from .own_inline_binding_ui import SCRIPT as binding_script
    from .x_management_ui import HTML as x_html, SCRIPT as x_script
    from .xhs_management_ui import HTML as xhs_html, SCRIPT as xhs_script
    from .platform_branding import script as platform_branding_script
    from .project_context_ui import HTML as project_html, SCRIPT as project_script, STYLE as project_style
    from .content_templates_ui import STYLE as template_style
    from .x_schedule_ui import STYLE as schedule_style, SCRIPT as schedule_script
    from .x_operating_ui import STYLE as operating_style, SCRIPT as operating_script
    html = ('<!doctype html><html lang="zh-CN"><meta charset="utf-8">'
        '<meta name="viewport" content="width=device-width,initial-scale=1">'
        '<title>OpenAhoy · 平台管理</title><style>' + STYLE + management_style + project_style + template_style + schedule_style + operating_style + '</style>'
        + native_page_body(LOGO, settings_html(templates=True) + x_html + xhs_html + project_html)
        + '<script>' + platform_branding_script() + settings_script(compact=True) + binding_script + x_script + xhs_script + schedule_script + operating_script + project_script + SCRIPT + '</script></body></html>')
    return {'contents': [{'uri': RESOURCE, 'mimeType': MIME, 'text': html,
        '_meta': {'ui': {'csp': {'connectDomains': [], 'resourceDomains': ['https://pbs.twimg.com'], 'frameDomains': []}},
                  'openai/ui': {'availableDisplayModes': ['inline', 'fullscreen'], 'preferredDisplayMode': 'inline'}}}]}


class NativeManagement:
    def resource(self):
        return resource()

    def close(self):
        pass  # The native view owns no HTTP listener or account session.
