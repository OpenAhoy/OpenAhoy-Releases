"""Static MCP App. Account data arrives through the standard parent bridge."""
from .own_native_management_contract import RESOURCE
from .management_locale import mark_chrome, script as locale_script
from .management_fonts import style as font_style

MIME = 'text/html;profile=mcp-app'

SCRIPT = r'''
(() => {
 'use strict';
 const $=id=>document.getElementById(id),bridge=window.parent,pending=new Map();
 const accountPanel=$('accountPanel'),accountList=$('accounts'),platformNavigation=$('platformNavigation');
 const compactAccounts=matchMedia('(max-width:560px)');
 let accountsExpanded=false,renderedAccounts=[];
 const floatingMenus='details.oa-more-settings[open],details.oa-account-menu[open],details.oa-task-menu[open]';
 function closeFloatingMenus(except=null){
   for(const menu of document.querySelectorAll(floatingMenus))if(menu!==except)menu.open=false;
 }
 document.addEventListener('click',event=>{
   const path=event.composedPath();
   if(path.includes($('oaLocale')))return;
   for(const menu of document.querySelectorAll(floatingMenus))if(!path.includes(menu))menu.open=false;
   if(accountPanel.matches(':popover-open')&&!path.includes(accountPanel)&&!path.includes(platformButton())){
     closeAccountNavigation();
   }
 },true);
 document.addEventListener('keydown',event=>{
   if(event.key!=='Escape'||event.defaultPrevented||document.querySelector('dialog[open]'))return;
   const menu=document.querySelector(floatingMenus);
   if(menu){event.preventDefault();closeFloatingMenus();menu.querySelector(':scope > summary')?.focus();return;}
   if(accountPanel.matches(':popover-open')){event.preventDefault();closeAccountNavigation({focus:true});}
 });
 mountOpenAhoyHints();
 const allowed=new Set(['own.wechat.content','own.drafts.inventory','own.drafts.current.read',
   'own.drafts.current.merge','own.drafts.current.status',
   'own.publications.current.dispatch','own.publications.current.poll',
   'own.sources.library','audio.project.presets','wce.ui.management.overview','wce.ui.management.disconnect','wce.ui.management.save_display_name','wce.ui.platform.action','x.ui.action','xhs.ui.action','x.attempt.status','wce.ui.projects.action','own.templates.read','wce.ui.templates.download','video.ark.connection.status','video.tokenhex.connection.check','wce.ui.video.credential','wce.ui.video.workspace','video.director.read','video.director.edit','wce.ui.video.director.media','wce.ui.wechat.storage_recovery','wce.ui.wechat.analytics','wce.ui.writing.rules']);

 let counter=0,navigationEpoch=0,ready=false,closed=false,refreshing=false,launching=false,backendOpening=false,hostCapabilities={},rows=[],directory=[],selected='',activePlatform='';
 const homeView='published';
 let view='startup',hostView='',explicitNavigation=false,guide=null,accountRead=false;
 let wechatPage='monitor';
 const isWechat=()=>view==='platform'&&activePlatform==='wechat_official_account';
 const notice=(text,error=false,...values)=>{OAUI.set($('notice'),text,...values);$('notice').className='notice'+(error?' error':'');};
 const key=row=>JSON.stringify([row.platform_id,row.connection_id]);
 const platform=id=>directory.find(p=>p.id===id);
 const current=()=>rows.find(row=>key(row)===selected&&row.platform_id===activePlatform);
 const name=row=>row.presentation?.display_name||'';
 const platformNames=new Map([['wechat_official_account','公众号'],['x','X'],['xiaohongshu','小红书']]);
 const platformName=id=>platformNames.get(id);
 const featureCopy=new Map([
   ['wechat_official_account','管理公众号、草稿和发布设置。'],
   ['x','管理 X 账号、创作规则和开发者应用。'],
   ['xiaohongshu','绑定小红书账号并管理笔记发布。']
 ]);
 const assetLabels={characters:'形象',images:'图片',gif:'动图',video:'视频',audio:'音频',articles:'文章',sources:'信源库'};
 const studioRoutes=new Map([
   ['jiusera-monitor',{section:'monitor'}],['jiusera-canvas',{section:'desk'}],['jiusera-assets',{section:'assets'}],
   ['media',{section:'monitor'}],...Object.keys(assetLabels).map(kind=>[kind,{section:'assets',kind}])
 ]);
 const studioURLs={monitor:'jiusera-monitor',desk:'jiusera-canvas',assets:'jiusera-assets'};
 function route(value){
   if(value==='home')return homeView;
   return value==='about'||value==='published'||value==='studio-showcase'||studioRoutes.has(value)||platformNames.has(value)?value:'';
 }
 function routeFromURL(){
   const hash=location.hash.slice(1),query=new URLSearchParams(location.search),fragment=new URLSearchParams(hash);
   return [fragment.get('view'),fragment.get('platform'),query.get('view'),query.get('platform'),hash].map(route).find(Boolean)||'';
 }
 function launchFromURL(){
   const target=routeFromURL(),query=new URLSearchParams(location.search);
   const fields=['project','work','scene','shot','revision'];
   const identifiers=fields.map(field=>query.get(field));
   if((!target||target==='jiusera-canvas')&&identifiers.every(value=>/^[a-f0-9]{32}$/.test(value||''))){
     const scope=Object.fromEntries(fields.map((field,index)=>[field+'_id',identifiers[index]]));
     return {target:'jiusera-canvas',shot:{scope,tab:query.get('tab')}};
   }
   return {target};
 }
 const addressLaunch=launchFromURL();
 const initializedEditors=new Set();let binding=null,xManagement=null,xhsManagement=null,projectContext=null,contextOpen=false;
 const localExports=new Map(),selectedByPlatform=new Map();let selectEpoch=0,platformEpoch=0,selectionIntent=0,pendingSelection=null;
 const hostDownloadsUnknown=new Set();
 async function hostDownload(resource, onUnknown){
   let result;
   try{result=await rpc('ui/download-file',{contents:[{type:'resource',resource}]});}
   catch(error){
     if(error.rpcCode===-32601||error.rpcCode===-32602)return {state:'HOST_DOWNLOAD_REJECTED'};
     onUnknown();return {state:'HOST_DOWNLOAD_UNCONFIRMED'};
   }
   if(result?.isError===true)return {state:'HOST_DOWNLOAD_REJECTED'};
   if(result&&typeof result==='object'&&!Array.isArray(result)&&
      (result.isError===false||result.isError===undefined))return {state:'HOST_DOWNLOADED'};
   onUnknown();return {state:'HOST_DOWNLOAD_UNCONFIRMED'};
 }
 const originalSelection={platform:'',account:''};
 const editors=new Map(Object.entries(OAPlatformSettings).map(([id,adapter])=>[id,adapter.mount((operation,args)=>platformCall(id,operation,args),()=>{navigationEpoch++;},{
  templateCall:(name,args)=>tool(name,args),
  templateTarget(){const row=current(),capture=navigationEpoch;return row&&row.platform_id===id?{connection_id:row.connection_id,name:name(row),isCurrent:()=>{const live=current();return !closed&&ready&&navigationEpoch===capture&&live&&key(live)===key(row)&&live.account_id===row.account_id&&live.binding_revision===row.binding_revision;}}:null;},
  async templateDownload(m,getBytes,{queryOnly=false,onDispatch=()=>{}}={}){
   if(hostCapabilities.downloadFile){
    if(queryOnly)throw new Error('TEMPLATE_DOWNLOAD_UNKNOWN');
    const raw=await getBytes();let binary='';for(const byte of raw)binary+=String.fromCharCode(byte);
    return hostDownload({uri:'openahoy-template://download/'+encodeURIComponent(m.id+'-'+m.version+'.zip'),
      mimeType:'application/zip',blob:btoa(binary)},onDispatch);
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
    const result=await hostDownload({uri:'openahoy-config://download/'+encodeURIComponent(filename),
      mimeType:'application/json',text},()=>hostDownloadsUnknown.add(row.connection_id));
    if(result.state==='HOST_DOWNLOAD_REJECTED')throw new Error('RULES_DOWNLOAD_FAILED');
    if(result.state==='HOST_DOWNLOAD_UNCONFIRMED')throw new Error('RULES_DOWNLOAD_UNKNOWN');
    return result;
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
    if(value.sha256!==expected||value.utf8_bytes!==bytes.length||value.destination!=='Downloads'||!['Jiusera-配置-','OpenAhoy-配置-'].some(prefix=>value.filename===prefix+original.export_id.slice(7)+'.json'))throw new Error('CONFIG_EXPORT_RESULT_UNKNOWN');
    localExports.delete(row.connection_id);return {...value,from_query:query};
   }catch(error){
    if(['CONFIG_EXPORT_INVALID','CONFIG_EXPORT_ACCOUNT_MISMATCH'].includes(error.message)){localExports.delete(row.connection_id);throw new Error(error.message);}
    return {state:'CONFIG_EXPORT_PENDING'};
   }
  }
 })]));
 function applyHostTheme(context){if(context?.theme==='light'||context?.theme==='dark')document.body.dataset.colorScheme=context.theme;}
 function dispose(){showcase.show(false);homeIntro?.close();showMedia('');studioSound.close();video.dispose();binding?.dispose();xManagement?.dispose();xhsManagement?.dispose();projectContext?.dispose();closed=true;ready=false;for(const editor of editors.values())editor.setReady(false);
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
   if(v.method==='ui/notifications/tool-input'&&!Object.hasOwn(v,'id')){
     const args=v.params?.arguments;
     const target=route(args?.view)||route(args?.platform_id);
     // The host can deliver launch arguments after initialization. Accept one
     // explicit launch per frame, unless the URL or the user already chose.
     if(target&&!closed&&!addressLaunch.target&&!hostView&&!explicitNavigation){
       hostView=target;
       if(ready&&view===homeView&&target!==homeView)void openView(target);
     }
     return;
   }
   if(v.method==='ui/notifications/host-context-changed'&&!Object.hasOwn(v,'id')){if(ready&&!closed)applyHostTheme(v.params);return;}
   if(v.method==='ui/resource-teardown'){
     if(!Object.hasOwn(v,'id'))return;
     if(!['string','number'].includes(typeof v.id)||!v.params||typeof v.params!=='object'||Array.isArray(v.params)||Object.keys(v.params).length||Object.hasOwn(v,'result')||Object.hasOwn(v,'error')){
       bridge.postMessage({jsonrpc:'2.0',id:v.id,error:{code:-32602,message:'Invalid params'}},'*');return;
     }
     dispose();bridge.postMessage({jsonrpc:'2.0',id:v.id,result:{}},'*');return;
   }
   const item=pending.get(v.id);if(!item)return;clearTimeout(item.timer);pending.delete(v.id);
   if(v.method||v.error||!Object.hasOwn(v,'result')){
     const error=new Error('HOST_ERROR');
     if(!v.method&&!Object.hasOwn(v,'result')&&Number.isInteger(v.error?.code))error.rpcCode=v.error.code;
     item.reject(error);
   }else item.resolve(v.result);
 });
 async function tool(name,args){if(!ready||!allowed.has(name))throw new Error('UI_TOOL_UNAVAILABLE');return rpc('tools/call',{name,arguments:args});}
 function content(result){if(result?.isError||!result?.structuredContent)throw new Error('MANAGEMENT_READ_FAILED');return result.structuredContent;}
 OAWritingRules(async args=>{
   const result=await tool('wce.ui.writing.rules',args);
   if(result?.isError)throw Error(result.structuredContent?.error);
   return content(result);
 });
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
   $('refresh').setAttribute('aria-busy',String(refreshing));
   const addLabel=activePlatform==='xiaohongshu'?'扫码绑定小红书':activePlatform==='x'?'绑定 X 账号':'绑定账号';
   OAUI.set($('showAdd'),addLabel);OAUI.attr($('showAdd'),'aria-label',addLabel);
   $('showAdd').disabled=!ready||refreshing||launching||!p?.binding_supported||
     (activePlatform==='xiaohongshu'&&!(xhsManagement?.canBegin()));
   $('accountRules').disabled=!ready||refreshing||!row||!platform(row.platform_id)?.settings_supported||!editors.has(row.platform_id);
   $('accountImport').disabled=$('accountRules').disabled;
   $('accountCreate').disabled=$('accountRules').disabled;
   $('accountBackend').disabled=!ready||backendOpening||!row||!editors.get(row.platform_id)?.openBackend;
 }
 function showSettings(id){
   const p=platform(id),editor=editors.get(id),supported=!!p?.settings_supported&&!!editor;
   paintAccountHeader();
   if(p&&platformName(id))OAUI.set($('platformHelp'),p.settings_help||'');else OAUI.raw($('platformHelp'),p?.settings_help||'');$('unsupportedSettings').hidden=supported;
   for(const el of document.querySelectorAll('#settingsPanel [data-platform-id]'))el.hidden=!supported||el.dataset.platformId!==id;
   $('xSettings').hidden=id!=='x';if(id==='x')$('unsupportedSettings').hidden=true;
   $('xhsSettings').hidden=id!=='xiaohongshu';if(id==='xiaohongshu')$('unsupportedSettings').hidden=true;
   $('contextSettingsTab').setAttribute('aria-selected',String(contextOpen));$('platformSettingsTab').setAttribute('aria-selected',String(!contextOpen));
   $('projectContextPanel').hidden=!contextOpen;
   if(contextOpen){$('wechatSettings').hidden=true;$('xSettings').hidden=true;$('xhsSettings').hidden=true;$('unsupportedSettings').hidden=true;}
   return supported;
 }
 async function selectPlatform(id,{focus,user}){
   showMedia('');const intent=++platformEpoch;selectEpoch++;selectionIntent++;navigationEpoch++;
   closeXTools();activePlatform=id;
   accountsExpanded=user||!compactAccounts.matches;
   paintAccountHeader();
   if(isWechat())wechatPage='monitor';
   renderView();renderPlatforms();await renderAccounts();if(closed||intent!==platformEpoch||view!=='platform'||activePlatform!==id)return;showSettings(id);
   if(id==='x'&&ready&&!contextOpen)xManagement.activate();else xManagement.deactivate();
   if(id==='xiaohongshu'&&ready&&!contextOpen)xhsManagement.activate();else xhsManagement.deactivate();
   $('xCapabilities').hidden=id!=='x';
   if(focus)platformButton()?.focus();
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
 let removalTarget=null, removing=false;
 const removalDialog=$('accountRemoveDialog');
 const nameDialog=$('accountNameDialog'),displayName=$('accountDisplayName'),saveName=$('accountNameSave');
 let nameTarget=null;
 function canEditName(row){
   return row.platform_id==='wechat_official_account'&&['BOUND','BOUND_IDLE','BUSY','CONNECTED'].includes(row.state)
     &&['MISSING','SAVED'].includes(row.presentation?.state)&&Number.isSafeInteger(row.presentation.revision);
 }
 function currentNameTarget(row){
   return !closed&&ready&&view==='platform'&&activePlatform===row.platform_id&&rows.some(item=>
     key(item)===key(row)&&item.account_id===row.account_id&&item.binding_revision===row.binding_revision&&canEditName(item));
 }
 $('accountNameCancel').onclick=()=>nameDialog.close();
 nameDialog.addEventListener('close',()=>{if(!nameDialog.open)nameTarget=null;});
 $('accountNameForm').onsubmit=async event=>{
   event.preventDefault();const row=nameTarget,desired=displayName.value.trim();
   if(!event.isTrusted||saveName.disabled||!row||!currentNameTarget(row))return;
   if(!desired){OAUI.set($('accountNameStatus'),'请输入显示名称。');return;}
   saveName.disabled=true;displayName.disabled=true;
   let observed;
   try{
     await tool('wce.ui.management.save_display_name',{connection_id:row.connection_id,
       account_id:row.account_id,binding_revision:row.binding_revision,
       expected_revision:row.presentation.revision,display_name:desired});
   }catch(_){/* Read back the scoped account after a lost or failed response. */}
   try{observed=await refresh({afterWrite:true});}catch(_){}
   if(closed||nameTarget!==row||!nameDialog.open)return;
   const found=observed?.find(item=>key(item)===key(row)&&item.account_id===row.account_id&&item.binding_revision===row.binding_revision);
   if(found?.presentation?.display_name===desired&&found.presentation.revision>row.presentation.revision){
     nameDialog.close();notice('已保存显示名称。');return;
   }
   OAUI.set($('accountNameStatus'),'名称未能确认。请关闭并重新打开此账号的编辑窗口，查看当前名称。');
 };
 const recoveryDialog=$('accountRecoveryDialog');
 let recoveryTarget=null,recoveryCheck=null;
 async function storageRecovery(row,action){
   if(recoveryTarget!==row)return;
   const button=$('accountRecoveryAsk'),status=$('accountRecoveryStatus');
   try{
     const result=content(await tool('wce.ui.wechat.storage_recovery',{action}));
     if(recoveryTarget!==row)return;
     button.hidden=result.state!=='READY_FOR_CONFIRMATION';
     button.disabled=false;
     if(result.state==='READY_FOR_CONFIRMATION'){
       OAUI.raw($('accountRecoveryTarget'),result.appids.join(' · '));
       OAUI.set(status,'已核对两个原绑定。请在 macOS 中确认恢复。');
     }else if(result.state==='PENDING'){
       OAUI.set(status,'等待 macOS 本人确认。');
       recoveryCheck=setTimeout(()=>void storageRecovery(row,'status'),1000);
     }else if(result.state==='COMMITTED'){
       const observed=await refresh({afterWrite:true});
       if(recoveryTarget!==row)return;
       const live=observed?.find(item=>key(item)===key(row));
       OAUI.set(status,live&&['BOUND','BOUND_IDLE','CONNECTED','BUSY'].includes(live.state)
         ?'原公众号绑定已恢复，列表已更新。':'原恢复记录已验证。账号列表暂未确认，请刷新查看。');
     }else if(result.state==='VERIFY_REQUIRED'){
       OAUI.set(status,'找到了原恢复记录。请保持 macOS 已登录且解锁，再刷新检查。');
     }else if(result.code==='CONNECTION_RECOVERY_CONFIRMATION_CANCELLED'){
       OAUI.set(status,'已取消。关闭后可重新检查。');
     }else if(result.code==='CONNECTION_RECOVERY_WITNESS_UNAVAILABLE'){
       OAUI.set(status,'当前安装无法保护恢复凭据。请等待可用的更新。');
     }else{
       OAUI.set(status,'暂时无法恢复原绑定。');
     }
   }catch(_){
     if(recoveryTarget===row)OAUI.set(status,'暂时无法检查本机恢复。');
   }
 }
 function recoveryAction(row){
   const button=document.createElement('button');
   button.type='button';button.className='oa-account-recovery';
   OAUI.set(button,'查看恢复方法');
   button.onclick=()=>{
     if(closed||activePlatform!==row.platform_id||!rows.includes(row))return;
     recoveryTarget=row;
     OAUI.raw($('accountRecoveryTarget'),[row.label,row.recovery.registered_appid].filter(Boolean).join(' · '));
     const reason={STORAGE_IDENTITY_CHANGED:'本机存储编号已变，原账号仍在登记中。',
                   CHECK_RECOVERY_WITNESS:'请先检查已保存的本机恢复记录。'};
     OAUI.set($('accountRecoveryReason'),reason[row.recovery.kind]||'暂时无法核实本机绑定，需先检查原登记。');
     OAUI.set($('accountRecoveryStatus'),'');
     $('accountRecoveryAsk').hidden=true;
     $('accountRecoveryAsk').disabled=false;
     recoveryDialog.showModal();
     void storageRecovery(row,'inspect');
   };
   return button;
 }
 $('accountRecoveryClose').onclick=()=>recoveryDialog.close();
 recoveryDialog.addEventListener('close',()=>{clearTimeout(recoveryCheck);recoveryTarget=null;});
 $('accountRecoveryAsk').onclick=async event=>{
   const row=recoveryTarget;
   if(!event.isTrusted||!row||row.platform_id!==activePlatform)return;
   const live=rows.find(item=>key(item)===key(row));
   if(!live?.recovery||live.recovery.kind!==row.recovery.kind||
      live.recovery.registered_appid!==row.recovery.registered_appid){
     $('accountRecoveryAsk').hidden=true;
     OAUI.set($('accountRecoveryStatus'),'账号状态已变化，请关闭后查看最新列表。');
     return;
   }
   $('accountRecoveryAsk').disabled=true;
   await storageRecovery(row,'confirm');
 };
 function accountMenu(row,bindingAvailable){
   const menu=document.createElement('details'),toggle=document.createElement('summary');
   const actions=document.createElement('div'),rebind=document.createElement('button'),remove=document.createElement('button');
   menu.className='oa-account-menu';
   toggle.textContent='⋯';toggle.dataset.oaHint='';OAUI.attr(toggle,'aria-label','{0} 的更多操作',name(row)||row.account_id);
   remove.type='button';remove.className='oa-account-remove';OAUI.set(remove,'移除账号');
   remove.onclick=()=>{
     if(!ready||closed||refreshing||removing||activePlatform!==row.platform_id)return;
     if(!rows.some(item=>key(item)===key(row)&&item.account_id===row.account_id&&item.binding_revision===row.binding_revision))return;
     menu.open=false;removalTarget=row;
     OAUI.raw($('accountRemoveTarget'),[name(row),platformName(row.platform_id),row.account_id].filter(Boolean).join(' · '));
     removalDialog.showModal();
   };
   rebind.type='button';OAUI.set(rebind,'重新绑定');
   rebind.onclick=async event=>{
     if(!event.isTrusted||!ready||closed||removing||refreshing||activePlatform!==row.platform_id)return;
     menu.open=false;
     await select(key(row));
     const chosen=current();
     if(closed||!chosen||key(chosen)!==key(row)||chosen.binding_revision!==row.binding_revision)return;
     if(row.platform_id==='wechat_official_account')return binding.open(row);
     if(row.platform_id==='xiaohongshu')return xhsManagement.reconnect(row.connection_id);
     await openXAuthorization(true);
   };
   if(bindingAvailable&&canEditName(row)){
     const edit=document.createElement('button');edit.type='button';OAUI.set(edit,'编辑显示名称');
     edit.onclick=event=>{
       if(!event.isTrusted||refreshing||!currentNameTarget(row))return;
       closeFloatingMenus();nameTarget=row;displayName.value=name(row);
       displayName.disabled=false;saveName.disabled=false;OAUI.set($('accountNameStatus'),'');
       nameDialog.showModal();displayName.select();
     };
     actions.append(edit);
   }
   if(row.platform_id==='x'){
     const developer=document.createElement('button');developer.type='button';
     OAUI.raw(developer,'X Developer Console');
     developer.onclick=()=>{menu.open=false;void openXDeveloper(row);};
     actions.append(developer);
   }
   if(bindingAvailable)actions.append(rebind,remove);
   menu.append(toggle,actions);
   bindWorkspacePopover(menu);
   return menu;
 }
 function placeWorkspacePopover(anchor,popup,{size=224,start=false,limit=Infinity}={}){
   const box=anchor.getBoundingClientRect(),root=document.documentElement;
   const width=Math.min(size,root.clientWidth-16);
   const left=Math.max(8,Math.min(root.clientWidth-width-8,start?box.left:box.right-width));
   const below=root.clientHeight-box.bottom-12,above=box.top-12;
   const down=below>=Math.min(popup.scrollHeight,180)||below>=above;
   Object.assign(popup.style,{width:width+'px',left:left+'px',maxHeight:Math.min(limit,Math.max(48,down?below:above))+'px',
     top:down?box.bottom+4+'px':'auto',bottom:down?'auto':root.clientHeight-box.top+4+'px'});
 }
 function unmountWorkspacePopover(popup){
   if(!popup.hasAttribute('popover'))return;
   if(popup.matches(':popover-open'))popup.hidePopover();
   popup.removeAttribute('popover');popup.classList.remove('oa-workspace-popover');
   for(const property of ['width','left','max-height','top','bottom'])popup.style.removeProperty(property);
 }
 function bindWorkspacePopover(details){
   const anchor=details.querySelector(':scope > summary'),popup=details.querySelector(':scope > div');
   details.addEventListener('toggle',()=>{
     if(details.open&&view==='platform'&&typeof popup.showPopover==='function'){
       popup.setAttribute('popover','manual');
       popup.classList.add('oa-workspace-popover');
       if(!popup.matches(':popover-open'))popup.showPopover();
       placeWorkspacePopover(anchor,popup);
     }else unmountWorkspacePopover(popup);
   });
 }
 bindWorkspacePopover(document.querySelector('#accountTools details.oa-more-settings'));
 addEventListener('resize',()=>{if(view==='platform'){closeFloatingMenus();syncAccountNavigation();}});
 accountList.addEventListener('scroll',()=>closeFloatingMenus(),{passive:true});
 accountPanel.addEventListener('scroll',()=>closeFloatingMenus(),{passive:true});
 $('accountRemoveCancel').onclick=()=>removalDialog.close();
 removalDialog.addEventListener('close',()=>{removalTarget=null;});
 $('accountRemoveConfirm').onclick=async event=>{
   const row=removalTarget;
   if(!event.isTrusted||!row||removing||closed||!ready||refreshing)return;
   if(view!=='platform'||activePlatform!==row.platform_id||!rows.some(item=>key(item)===key(row)&&item.account_id===row.account_id&&item.binding_revision===row.binding_revision)){
     removalDialog.close();return;
   }
   removing=true;removalDialog.close();
   let disconnected=false;
   try{
     const result=await tool('wce.ui.management.disconnect',{
       platform_id:row.platform_id,connection_id:row.connection_id,account_id:row.account_id,binding_revision:row.binding_revision
     });
     const value=content(result);
     disconnected=!result.isError&&value.connection_id===row.connection_id&&value.state==='DISCONNECTED';
   }catch(_){}
   finally{
     removing=false;
     if(!closed){
       const observed=await refresh({afterWrite:true});
       const confirmed=observed?.some(item=>key(item)===key(row)&&item.state==='DISCONNECTED');
       const stillVisible=rows.some(item=>key(item)===key(row));
       if(view==='platform'&&activePlatform===row.platform_id){
         const verified=confirmed||(disconnected&&!stillVisible);
         notice(verified?'已从 Jiusera 移除账号。':'请刷新核对账号状态，移除结果尚未确认。',!verified);
       }
     }
   }
 };
 function accountCard(row){
   const el=document.createElement('div'),pick=document.createElement('button');
   const label=document.createElement('span'),title=document.createElement('strong'),state=document.createElement('small');
   const id=key(row),display=row.recovery?row.label:name(row);
   el.className='account';el.dataset.accountKey=id;
   pick.type='button';pick.className='account-select';pick.setAttribute('aria-controls','nativeWorkspace');
   title.dataset.oaOverflow='';
   if(display)OAUI.raw(title,display);else OAUI.set(title,'账号资料暂不可用');
   const connected=['CONNECTED','BOUND','BOUND_IDLE'].includes(row.state);
   state.className='status'+(connected?' good':'');
   OAUI.set(state,row.platform_id==='x'&&connected?'已连接':accountState(row));
   label.className='oa-account-copy';
   label.append(title,state);
   const photo=avatar(row);photo.setAttribute('aria-hidden','true');
   pick.append(photo,label);
   pick.onclick=async()=>{
     const intent=++selectionIntent;
     await select(id);
     if(intent===selectionIntent&&id===selected)closeAccountNavigation({compactOnly:true,focus:true});
   };
   el.append(pick);
   const canManage=row.account_id&&/^[a-f0-9]{64}$/.test(row.binding_revision)&&row.error!=='CONNECTION_ENTRY_UNAVAILABLE';
   if(canManage||row.platform_id==='x')el.append(accountMenu(row,canManage));
   else if(row.platform_id==='wechat_official_account'&&row.recovery)el.append(recoveryAction(row));
   return el;
 }
 function xDeveloperState(row){
   const state=xManagement?.pendingAuthorization(row.connection_id)?'NEEDS_AUTHORIZATION':row.own_application;
   const labels={CONNECTED:'开发者应用已接入',NEEDS_AUTHORIZATION:'待完成 X 授权',UNCONFIGURED:'自有应用未配置'};
   return labels[state]||'状态待核对';
 }
 async function select(id){
   const selecting={platform:activePlatform};
   pendingSelection=selecting;
   try{return await selectAccount(id);}
   finally{if(pendingSelection===selecting)pendingSelection=null;}
 }
 async function selectAccount(id){
   const platformId=activePlatform,token=++selectEpoch;
   const requested=rows.find(row=>row.platform_id===platformId&&key(row)===id);
   let target=requested;
   const editor=editors.get(requested?.platform_id||activePlatform);
   const staged=ready&&initializedEditors.has(requested?.platform_id||activePlatform)&&editor;
   const isCurrent=()=>!closed&&activePlatform===platformId&&token===selectEpoch&&(!requested||rows.some(row=>key(row)===id&&
     row.account_id===requested.account_id&&row.binding_revision===requested.binding_revision));
   let accepted=true;
   if(staged){
     accepted=await editor.stageAccountScope(requested?.connection_id||'',isCurrent);
     if(accepted===null||!isCurrent())return false;
     if(!accepted){target=rows.find(row=>row.platform_id===activePlatform&&row.connection_id===editor.scope?.());notice('原规则正在处理或结果待确认；已保留原规则目标，请先接续原操作。',true);}
   }
   if(target)target=rows.find(row=>key(row)===key(target)&&row.platform_id===activePlatform);
   id=target?key(target):'';
   if(id!==selected)navigationEpoch++;
   for(const editor of editors.values())editor.closeCreator();
   selected=rows.some(row=>key(row)===id)?id:'';if(selected)selectedByPlatform.set(activePlatform,selected);
   paintSelection();
   revealSelectedAccount();
   const row=current();
   projectContext?.target(activePlatform,row?.connection_id||'',rows);for(const editor of editors.values())editor.targetChanged?.();
   if(staged&&accepted)void editor.loadAccountScope(row?.connection_id||'');
   xManagement?.setupTargetChanged();
   if(activePlatform==='x')xManagement?.updateBilling();
   updateXDeveloper();
   if(activePlatform==='xiaohongshu')xhsManagement.updateControls();else buttons();
 }
 function accountState(row){
   return {CONNECTED:'已连接',BOUND:'已绑定',BOUND_IDLE:'已绑定 · 空闲',DISCONNECTED:'已断开',
           ACTION_REQUIRED:'需要处理',BUSY:'正在使用'}[row.state]||'状态待核对';
 }
 function targetAnalytics(){
   const row=current();
   const valid=isWechat()&&wechatPage==='monitor'&&$('inlineBinding').hidden&&
     row?.platform_id===activePlatform&&['BOUND','BOUND_IDLE','CONNECTED','BUSY'].includes(row.state);
   analytics?.target(valid?row:null,valid?name(row):'');
 }
 function renderWechatWorkspace(){
   const shown=isWechat()&&$('inlineBinding').hidden;
   const monitor=shown&&wechatPage==='monitor';
   document.body.classList.toggle('oa-wechat-view',shown);
   $('wechatWorkspaceNavigation').hidden=!shown;
   $('wechatMonitorTab').setAttribute('aria-pressed',String(monitor));
   $('wechatConfigTab').setAttribute('aria-pressed',String(shown&&!monitor));
   $('wechatAnalytics').hidden=!monitor;
   $('settingsPanel').hidden=monitor;
   targetAnalytics();
 }
 function setWechatPage(page,{rules=false}={}){
   if(!isWechat())return;
   closeFloatingMenus();
   wechatPage=page;
   if(rules){contextOpen=false;projectContext.deactivate();showSettings(activePlatform);}
   renderWechatWorkspace();
 }
 $('wechatMonitorTab').onclick=()=>setWechatPage('monitor');
 $('wechatConfigTab').onclick=()=>setWechatPage('settings');
 function revealAccountConfiguration(row){
   if(row.platform_id==='wechat_official_account')setWechatPage('settings',{rules:true});
 }
 function paintSelection(){
   targetAnalytics();
   for(const el of accountList.querySelectorAll(':scope > .account')){
     const chosen=el.dataset.accountKey===selected;
     el.classList.toggle('is-selected',chosen);
     el.querySelector('.account-select').setAttribute('aria-current',chosen?'true':'false');
   }
   paintAccountHeader();
   const row=current();
   $('selectedAccount').replaceChildren();
   if(row){const line=document.createElement('p');line.className='account-id';line.textContent=typeof row.account_id==='string'?(platform(row.platform_id)?.account_id_label||'账号标识')+' '+row.account_id:'账号资料暂不可用';$('selectedAccount').append(line);}
   else{const p=document.createElement('p');OAUI.set(p,'选择一个账号，查看所属平台与设置。');$('selectedAccount').append(p);}
   guide?.render();
 }
 function paintAccountHeader(){
   const row=current(),p=platform(activePlatform),label=platformName(activePlatform);
   const title=$('pageTitle'),caption=$('accountCaption');
   caption.hidden=!row;
   $('accountTools').hidden=!row||activePlatform!=='wechat_official_account';
   if(row){
     const display=row.recovery?row.label:name(row);
     if(display)OAUI.raw(title,display);else OAUI.set(title,'账号资料暂不可用');
     const parts=[label?OAUI.message(label):p?.name||'',OAUI.message(accountState(row))];
     if(row.platform_id==='x'&&row.username)parts.push('@'+row.username);
     OAUI.set(caption,'{0}',parts);
   }else if(label)OAUI.set(title,label);
   else if(p)OAUI.raw(title,p.name);
   else OAUI.set(title,activePlatform?'平台暂不可用':'选择平台');
 }
 async function renderAccounts({preserveSelection=false}={}){
   const visible=rows.filter(row=>row.platform_id===activePlatform);
   if(!accountList.childElementCount||visible.length!==renderedAccounts.length||visible.some((row,i)=>row!==renderedAccounts[i])){
     const samePlatform=renderedAccounts[0]?.platform_id===activePlatform;
     const previousScroll=samePlatform?accountList.scrollTop:0;
     const focused=document.activeElement?.closest('.account')?.dataset.accountKey;
     accountList.replaceChildren(...visible.map(accountCard));
     if(!visible.length){const p=document.createElement('p');p.className='empty';OAUI.set(p,'尚未绑定账号');accountList.append(p);}
     if(focused)Array.from(accountList.children).find(el=>el.dataset.accountKey===focused)?.querySelector('.account-select')?.focus({preventScroll:true});
     renderedAccounts=visible;
     accountList.scrollTop=previousScroll;
   }
   $('accountCount').textContent=String(visible.length);
   if(preserveSelection&&pendingSelection?.platform===activePlatform){
     paintSelection();buttons();return;
   }
   if(preserveSelection&&visible.some(row=>key(row)===selected)){
     paintSelection();
     const row=current();
     if(initializedEditors.has(activePlatform))void editors.get(activePlatform)?.loadAccountScope(row.connection_id);
     updateXDeveloper();buttons();return;
   }
   const prior=selectedByPlatform.get(activePlatform);
   if(preserveSelection&&prior&&!visible.some(row=>key(row)===prior)){
     if(selected===prior){
       selected='';navigationEpoch++;
       projectContext?.target(activePlatform,'',rows);
     }
     paintSelection();updateXDeveloper();buttons();return;
   }
   const remembered=prior||selected;
   await select(visible.some(row=>key(row)===remembered)?remembered:(visible[0]?key(visible[0]):''));
 }
 function platformButton(){
   return platformNavigation.querySelector('button[aria-current=page]');
 }
 function closeAccountNavigation({compactOnly=false,focus=false}={}){
   if(!accountsExpanded||(compactOnly&&!compactAccounts.matches))return;
   accountsExpanded=false;
   closeFloatingMenus();
   syncAccountNavigation();
   if(focus)platformButton()?.focus();
 }
 function syncAccountNavigation(){
   const button=platformButton();
   const shown=!!button&&accountsExpanded&&!$('nativeWorkspace').hidden;
   const floating=shown&&compactAccounts.matches&&typeof accountPanel.showPopover==='function';
   button?.setAttribute('aria-expanded',String(shown));
   if(!floating)unmountWorkspacePopover(accountPanel);
   accountPanel.hidden=!shown;
   if(floating){
     accountPanel.setAttribute('popover','manual');
     accountPanel.classList.add('oa-workspace-popover');
     if(!accountPanel.matches(':popover-open'))accountPanel.showPopover();
     placeWorkspacePopover(button,accountPanel,{size:310,start:true,limit:380});
   }
 }
 function revealSelectedAccount(){
   if(accountPanel.hidden)return;
   const row=accountList.querySelector('.is-selected');if(!row)return;
   const floating=accountPanel.matches(':popover-open');
   const scroll=floating?accountPanel:accountList;
   const border=scroll.getBoundingClientRect(),item=row.getBoundingClientRect();
   const top=border.top+(floating?accountPanel.querySelector('.oa-list-head').offsetHeight:0);
   if(item.top<top)scroll.scrollTop+=item.top-top;
   else if(item.bottom>border.bottom)scroll.scrollTop+=item.bottom-border.bottom;
 }
 function renderPlatforms(){
   const ids=[...new Set([...directory.map(p=>p.id),...rows.map(row=>row.platform_id),...(activePlatform?[activePlatform]:[])])];
   unmountWorkspacePopover(accountPanel);
   platformNavigation.replaceChildren();
   for(const id of ids){
     const p=platform(id),group=document.createElement('div'),button=document.createElement('button');
     const active=view==='platform'&&id===activePlatform;
     group.className='oa-platform-group';
     button.type='button';button.className='oa-platform-trigger';
     OAPlatformBranding.decorate(button,id,p?.name,OAUI);
     button.dataset.platformId=id;button.setAttribute('aria-current',active?'page':'false');
     button.setAttribute('aria-expanded',String(active&&accountsExpanded));
     const chevron=document.createElement('span');
     chevron.className='oa-platform-chevron';chevron.setAttribute('aria-hidden','true');
     button.append(chevron);
     button.onclick=async event=>{
       if(!ready||closed||!$('inlineBinding').hidden)return;
       if(view==='platform'&&activePlatform===id){
         closeFloatingMenus();accountsExpanded=!accountsExpanded;syncAccountNavigation();revealSelectedAccount();
       }else await openView(id,{user:true,focus:true});
       if(event.detail===0&&compactAccounts.matches&&accountsExpanded&&activePlatform===id){
         (accountList.querySelector('.is-selected .account-select')||accountList.querySelector('.account-select'))?.focus();
       }
     };
     group.append(button);
     if(active){button.setAttribute('aria-controls','accountPanel');group.append(accountPanel);}
     platformNavigation.append(group);
   }
   if(!accountPanel.isConnected)platformNavigation.append(accountPanel);
   if(!ids.length){const p=document.createElement('p');p.className='help';OAUI.set(p,'暂无可用平台');platformNavigation.append(p);}
   syncAccountNavigation();
 }
 function renderFeatures(){
   const grid=$('homeFeatures'),links=$('wbPlatformLinks');
   grid.replaceChildren();links.replaceChildren();
   for(const [id,copy] of featureCopy){
     if(!directory.some(p=>p.id===id&&p.binding_supported))continue;
     const card=document.createElement('button'),title=document.createElement('span'),description=document.createElement('span');
     card.type='button';card.className='oa-home-card';card.dataset.homePlatform=id;
     title.className='oa-home-card-title';OAPlatformBranding.decorate(title,id,platformName(id),OAUI);
     description.className='oa-home-card-description';OAUI.set(description,copy);
     card.append(title,description);
     card.onclick=()=>openView(id,{user:true,focus:true});grid.append(card);
     const link=document.createElement('button');
     link.type='button';link.dataset.wbRoute=id;
     OAPlatformBranding.decorate(link,id,platformName(id),OAUI);links.append(link);
   }
 }
 let refreshTask=null;
 function refresh({afterWrite=false}={}){
   if(!ready||closed||launching||view==='studio-showcase')return Promise.resolve();
   if(refreshTask)return afterWrite?refreshTask.then(()=>refresh()):refreshTask;
   refreshTask=readAccounts().finally(()=>{refreshTask=null;refreshing=false;if(!closed)buttons();guide?.render();});
   return refreshTask;
 }
 function prepareEditors(){
   for(const [id,editor]of editors){
     if(!platform(id)?.settings_supported||initializedEditors.has(id))continue;
     editor.setReady(true,{deferRead:true});
     initializedEditors.add(id);
   }
 }
 async function readAccounts(){
   const origin={view,platformEpoch,platform:activePlatform};
   const sameView=()=>!closed&&view===origin.view&&platformEpoch===origin.platformEpoch;
   const visibleRows=all=>all.filter(row=>origin.view!=='platform'||row.platform_id===origin.platform);
   const before=JSON.stringify(visibleRows(rows));
   accountRead=false;guide?.render();refreshing=true;buttons();notice('正在读取账号…');
   try{
     const value=content(await tool('wce.ui.management.overview',{}));if(closed)return;
     if(!Array.isArray(value.platforms)||value.platforms.some(p=>!p||typeof p.id!=='string'||typeof p.name!=='string'||typeof p.settings_supported!=='boolean'||typeof p.binding_supported!=='boolean')||new Set(value.platforms.map(p=>p.id)).size!==value.platforms.length)throw new Error('PLATFORM_INVALID_DIRECTORY');
     if(!Array.isArray(value.connections)||value.connections.some(row=>!row||typeof row.platform_id!=='string'||typeof row.connection_id!=='string'||(row.account_id!==undefined&&typeof row.account_id!=='string')||typeof row.state!=='string')||new Set(value.connections.map(key)).size!==value.connections.length)throw new Error('MANAGEMENT_INVALID_SNAPSHOT');
     const directoryChanged=JSON.stringify(directory)!==JSON.stringify(value.platforms);
     directory=value.platforms;
     const previous=new Map(rows.map(row=>[key(row),row]));
     rows=value.connections.filter(row=>row.state!=='DISCONNECTED').map(row=>{
       const old=previous.get(key(row));
       return JSON.stringify(old)===JSON.stringify(row)?old:row;
     });
     accountRead=true;
     workbench.paintAccounts(rows,directory);
     if(directoryChanged){renderPlatforms();renderFeatures();if(view==='platform')showSettings(activePlatform);}
     for(const [id,editor]of editors){
       const own=rows.filter(row=>row.platform_id===id);
       editor.accounts(own,new Map(own.map(row=>[row.connection_id,name(row)])));
     }
     prepareEditors();
     if(view==='platform')void renderAccounts({preserveSelection:true});
     OAUI.set($('homeStatus'),'');
     if(sameView()){
       const visible=visibleRows(rows),attention=visible.filter(row=>row.state==='ACTION_REQUIRED').length;
       if(attention)notice('已刷新，{0} 个账号需要处理。',true,attention);
       else if(before===JSON.stringify(visible))notice('已刷新，账号状态无变化。');
       else notice('已刷新，当前显示 {0} 个账号。',false,visible.length);
     }
     return value.connections;
   }catch(error){
     if(sameView()){
       notice(error.message==='HOST_TIMEOUT'?'账号刷新超时，仍显示上次读取结果。':'账号刷新失败，仍显示上次读取结果。',true);
       if(view==='about')OAUI.set($('homeStatus'),'暂时无法读取平台。');
     }
   }
 }
 binding=OAInlineBinding.mount(async(operation,args)=>content(await platformCall(originalSelection.platform,operation,args)),{
  enter(){originalSelection.platform=activePlatform;originalSelection.account=selected;$('nativeWorkspace').hidden=true;closeAccountNavigation({compactOnly:true});syncAccountNavigation();},
  leave(){$('nativeWorkspace').hidden=false;activePlatform=originalSelection.platform;syncAccountNavigation();select(originalSelection.account);},
  async complete(cid,existing=false,state='BOUND_IDLE'){$('nativeWorkspace').hidden=false;activePlatform=originalSelection.platform;syncAccountNavigation();await refresh({afterWrite:true});const row=rows.find(r=>r.connection_id===cid&&r.platform_id===activePlatform);if(row)await select(key(row));notice(state==='DISCONNECTED'?'原绑定已提交，账号当前已断开。':state==='ACTION_REQUIRED'?'原绑定已提交，当前账号需要处理，请查看账号状态。':existing?'账号已绑定，已选中原账号。':'已验证并绑定。');}
 });
 async function sendChatRequest(text){
  if(!hostCapabilities.message?.text)throw new Error('HOST_MESSAGE_UNAVAILABLE');
  const result=await rpc('ui/message',{role:'user',content:[{type:'text',text}]});if(!result||typeof result!=='object'||Array.isArray(result)||(result.isError!==undefined&&typeof result.isError!=='boolean')||result.isError)throw new Error('HOST_MESSAGE_NOT_CONFIRMED');return result;
 }
 async function openXLink(url){
  if(!hostCapabilities.openLinks)throw new Error('HOST_OPEN_LINK_UNAVAILABLE');const result=await rpc('ui/open-link',{url});if(!result||result.isError)throw new Error('HOST_OPEN_LINK_FAILED');return result;
 }
 xManagement=OAXManagement.mount((operation,args)=>tool('x.ui.action',{operation,arguments:args}),openXLink,async(cid,original)=>{await refresh({afterWrite:true});if(!closed&&original?.platform==='x'&&activePlatform==='x'&&original.epoch===platformEpoch&&original.intent===selectionIntent){const row=rows.find(r=>r.platform_id==='x'&&r.connection_id===cid);if(row)await select(key(row));}},{captureSelection:()=>({platform:activePlatform,epoch:platformEpoch,intent:selectionIntent}),selectedAccount:()=>current()?.platform_id==='x'?current().connection_id:null,sendChatRequest,canSendChatRequest:()=>!!hostCapabilities.message?.text,onStatusChange:updateXDeveloper});
 xhsManagement=OAXHSManagement.mount((operation,args)=>tool('xhs.ui.action',{operation,...args}),()=>refresh({afterWrite:true}),()=>current()?.platform_id==='xiaohongshu'?current().connection_id:null,buttons);
 projectContext=OAProjectContext.mount(async(operation,args)=>{
   if(args?.platform_id&&args.connection_id&&!rows.some(row=>
     row.platform_id===args.platform_id&&row.connection_id===args.connection_id))
     return {isError:true,structuredContent:{error:'PROJECT_ACCOUNT_MISMATCH'}};
   return tool('wce.ui.projects.action',{operation,arguments:args});
 },sendChatRequest,{readPost:(cid,attempt)=>tool('x.attempt.status',{connection_id:cid,kind:'post',attempt_id:attempt}),
  async downloadArtifact(raw,filename,a){
   const row=current();if(!row||row.platform_id!=='x'||row.connection_id!==a.connection_id)throw new Error('X_CONFIG_TARGET_CHANGED');
   if(hostCapabilities.downloadFile){
    if(a.queryOnly)throw new Error('X_CONFIG_DOWNLOAD_UNKNOWN');
    return hostDownload({uri:'openahoy-config://download/'+encodeURIComponent(filename),
      mimeType:a.artifact==='skill'?'text/markdown':'application/json',text:raw},a.onDispatch);
   }
   const args={connection_id:a.connection_id,configuration:a.configuration,export_id:a.export_id,artifact:a.artifact,action:a.queryOnly?'query':'write'};a.onDispatch();
   const value=content(await tool('wce.ui.projects.action',{operation:'X_CONFIG_EXPORT',arguments:args}));
   if(value.state==='CONFIG_EXPORTED'){
    const bytes=new TextEncoder().encode(raw),hash=[...new Uint8Array(await crypto.subtle.digest('SHA-256',bytes))].map(x=>x.toString(16).padStart(2,'0')).join('');
    if(value.export_id!==a.export_id||value.sha256!==hash||value.utf8_bytes!==bytes.length||value.destination!=='Downloads')throw new Error('X_CONFIG_DOWNLOAD_UNKNOWN');
   }return value;
  }});
 document.querySelectorAll('[data-workspace-project]').forEach(button=>button.addEventListener('click',()=>$('contextSettingsTab').click()));
 $('xWorkspaceTools').onclick=()=>{closeXTools();document.body.classList.add('oa-x-tools');};
 $('xWorkspaceBilling').onclick=()=>{closeXTools();document.body.classList.add('oa-x-tools');xManagement.openBilling();};
 $('xConnectOwnApplication').onclick=()=>openXDeveloper(current());
 let xDeveloperKey='';
 function closeXTools(){
   xDeveloperKey='';$('xDeveloperSettings').hidden=true;$('xBilling').open=false;
   xManagement.closeAuthorization();document.body.classList.remove('oa-x-tools','oa-x-developer-open');
 }
 function updateXDeveloper(){
   if(!xDeveloperKey)return;
   const row=current();
   if(row?.platform_id!=='x'||key(row)!==xDeveloperKey){closeXTools();return;}
   OAUI.raw($('xDeveloperIdentity'),[name(row),row.username?'@'+row.username:''].filter(Boolean).join(' · '));
   OAUI.set($('xDeveloperState'),xDeveloperState(row));
   OAUI.set($('xDeveloperConnect'),row.own_application==='CONNECTED'?'更换开发者应用':'连接自己的 X 开发者应用');
 }
 async function openXDeveloper(row){
   if(!ready||closed||row?.platform_id!=='x')return;
   const intent=++selectionIntent;
   if(selected!==key(row))await select(key(row));
   if(closed||intent!==selectionIntent||activePlatform!=='x'||selected!==key(row))return;
   closeAccountNavigation({compactOnly:true});
   closeXTools();contextOpen=false;projectContext.deactivate();showSettings('x');
   xDeveloperKey=key(row);document.body.classList.add('oa-x-tools','oa-x-developer-open');
   $('xDeveloperSettings').hidden=false;OAUI.set($('xDeveloperNotice'),'');updateXDeveloper();
   $('xDeveloperHeading').focus();$('xDeveloperSettings').scrollIntoView({block:'nearest'});
   await xManagement.activate();
 }
 $('xDeveloperConnect').onclick=async event=>{
   if(!event.isTrusted||!xDeveloperKey||xDeveloperKey!==selected)return;
   const opened=xManagement.openAuthorization(true,true);
   $('xAuthorization').scrollIntoView({block:'nearest'});
   if(await opened)void xManagement.startSetup(event);
 };
 $('xDeveloperConsole').onclick=async()=>{
   const target=xDeveloperKey;
   const username=current()?.username;
   try{
    await openXLink('https://console.x.com/');
    if(target===xDeveloperKey&&username)OAUI.set($('xDeveloperNotice'),'请在 X Developer Console 核对或切换到 @{0}。',username);
   }
   catch(_){if(target===xDeveloperKey)OAUI.set($('xDeveloperNotice'),'当前宿主无法打开 X Developer Console。');}
 };
 $('xProductionEdit').addEventListener('click',closeXTools);
 const xBack=document.createElement('button');xBack.id='xWorkspaceBack';OAUI.set(xBack,'返回内容配置');xBack.className='oa-x-tools-back';xBack.onclick=closeXTools;$('xSettings').prepend(xBack);
 const xCapabilities=document.createElement('details');xCapabilities.className='oa-capability-details';const xCaption=document.createElement('summary');OAUI.set(xCaption,'X 支持的自动能力');xCapabilities.append(xCaption,$('xCapabilities'));$('xSettings').prepend(xCapabilities);
 $('contextSettingsTab').addEventListener('click',()=>{closeXTools();contextOpen=true;showSettings(activePlatform);xManagement.deactivate();xhsManagement.deactivate();$('xCapabilities').hidden=activePlatform!=='x';projectContext.activate();});
 $('platformSettingsTab').addEventListener('click',()=>{contextOpen=false;projectContext.deactivate();showSettings(activePlatform);if(activePlatform==='x')xManagement.activate();if(activePlatform==='xiaohongshu')xhsManagement.activate();});
 async function openXAuthorization(existing){
   closeXTools();
   contextOpen=false;projectContext.deactivate();showSettings('x');document.body.classList.add('oa-x-tools');
   xManagement.openAuthorization(existing,existing);await xManagement.activate();
 }
 async function secure(){if(!ready||!bindingPlatform()?.binding_supported)return;if(activePlatform==='xiaohongshu'){await xhsManagement.begin();return;}if(activePlatform==='x'){await openXAuthorization(false);return;}await binding.open();}
 async function readAnalytics(args){
   const result=await tool('wce.ui.wechat.analytics',args);
   if(result?.isError){
     const code=result.structuredContent?.error||result.content?.[0]?.text;
     throw new Error(typeof code==='string'&&/^[A-Z0-9_]{1,96}$/.test(code)?code:'WECHAT_ANALYTICS_UNAVAILABLE');
   }
   return content(result);
 }
 const analytics=OAWechatAnalytics(readAnalytics,openXLink);
 const workbench=OAWorkbench({open:target=>openView(target,{user:true,focus:true}),
   readAnalytics,openLink:openXLink,platformName,platformDirectoryIcon:(node,id,label)=>OAPlatformBranding.decorate(node,id,label,OAUI),
   accountName:row=>name(row)||row.label||row.account_id||''});
 const video = OAVideoCredential((name,args)=>tool(name,args).then(content),()=>ready&&!closed);
 const mediaTool=async(name,args)=>{
   const result=await tool(name,args);
   if(result?.isError){
     const problem=new Error(result.structuredContent?.error||result.content?.[0]?.text||'VIDEO_TOOL_FAILED');
     problem.diagnostic=result.structuredContent;
     throw problem;
   }
   return content(result);
 };
 OAVideoProviders(sendChatRequest,openXLink,()=>!!hostCapabilities.message?.text);
 const audioWorkspace=OAAudioWorkspace(mediaTool,sendChatRequest,openXLink,()=>!!hostCapabilities.message?.text);
 $('monitorVideoSettings').append($('monitorComponents').querySelector('.oa-provider-grid'));
 $('monitorGifSettings').append($('monitorComponents').querySelector('.oa-gif-key'));
 $('monitorAudioSettings').append($('audioWorkspace'));
 let providerMode='';
 function showMediaProvider(mode){
   if(providerMode&&providerMode!=='audio')video.setOpen(false,providerMode);
   providerMode=mode;
   $('monitorProviders').hidden=!mode;
   $('monitorVideoSettings').hidden=mode!=='video';
   $('monitorGifSettings').hidden=mode!=='gif';
   $('monitorAudioSettings').hidden=mode!=='audio';
   $('monitorVideoProvider').setAttribute('aria-pressed',String(mode==='video'));
   $('monitorGifProvider').setAttribute('aria-pressed',String(mode==='gif'));
   $('monitorAudioProvider').setAttribute('aria-pressed',String(mode==='audio'));
   if(mode==='audio'){
     $('audioWorkspace').hidden=false;
     audioWorkspace.open(null,{providerOnly:true});
   }else{
     $('audioWorkspace').hidden=true;
     audioWorkspace.close();
     if(mode)video.setOpen(true,mode);
   }
 }
 $('monitorVideoProvider').onclick=()=>showMediaProvider('video');
 $('monitorGifProvider').onclick=()=>showMediaProvider('gif');
 $('monitorAudioProvider').onclick=()=>showMediaProvider('audio');
 const studioEntries=$('jiuseraEntries'), studioParent=$('openMediaStudio'), assetKinds=$('directorAssetKinds');
 let showcaseBack=homeView;
 const showcase=OAStudioShowcase((action,args)=>mediaTool('wce.ui.video.director.media',{action,...args}),
   ()=>void openView(showcaseBack,{user:true,focus:true}),
   shot=>void openView('jiusera-canvas',{user:true,focus:true,shot}));
 const studioSound=OAStudioPreviewSound($('directorSound'));
 let studioExpanded=false,mediaView='',mainStudio='monitor',assetKind='';
 const assetRoute=kind=>kind||'jiusera-assets';
 function updateAssetURL(target){
   try{
     if(!['http:','https:','file:'].includes(location.protocol))return;
     const url=new URL(location.href);
     const old=routeFromURL();
     if(!target&&studioRoutes.get(old)?.section!=='assets')return;
     if(studioRoutes.get(url.searchParams.get('view'))?.section==='assets')url.searchParams.delete('view');
     url.hash=target?'view='+target:'';
     history.replaceState(history.state,'',url);
   }catch(_){}
 }
 const paintAssetKind=kind=>{
   const active=mediaView==='assets';
   assetKind=active?kind:'';
   assetKinds.hidden=!active||!!kind;
   $('directorAssetBack').hidden=!active||!kind;
   if(active)OAUI.set($('directorTitle'),assetLabels[kind]||'资产库');
 };
 const imageAssets=OAImageAssets(mediaTool);
 const newsSources=OASourceLibrary(mediaTool,openXLink);
 const monitor=OAMediaMonitor((action,args)=>mediaTool('wce.ui.video.workspace',{action,...args}),sendChatRequest,
   {musicCall:mediaTool,musicShot:scope=>enterStudio('desk',{shot:{scope},user:true,focus:true}),sound:studioSound,canAttach:row=>director.canAttach(row),attach:row=>director.attach(row),
    typeChanged:kind=>{if(mediaView==='assets'){paintAssetKind(kind);updateAssetURL(assetRoute(kind));}}});
 const gallery=OAAssetGallery(assetKinds,mediaTool,studioSound,openXLink);
 function showAssetKind(kind='',asset=null){
   if(kind!==assetKind){
     switch(assetKind){
       case 'characters': characters.close();break;
       case 'images': imageAssets.close();break;
       case 'sources': newsSources.close();break;
       case 'articles': $('articleAssetLibrary').hidden=true;break;
       case 'video': case 'audio': case 'gif':
         if(!['video','audio','gif'].includes(kind))monitor.close();
     }
   }
   paintAssetKind(kind);
   const articlePage=$('articleAssetLibrary');
   articlePage.hidden=kind!=='articles';
   if(!kind)gallery.open();else gallery.close();
   document.dispatchEvent(new CustomEvent('jiusera:asset-category',{detail:{kind,asset}}));
   if(kind==='characters')characters.open();
   else if(kind==='images')imageAssets.open();
   else if(kind==='sources')void newsSources.open();
   else if(['video','audio','gif'].includes(kind))monitor.open(kind,asset);
 }
 for(const button of assetKinds.querySelectorAll('[data-asset-kind]'))
   button.onclick=()=>enterStudio('assets',{kind:button.dataset.assetKind,user:true,focus:true});
 $('directorAssetBack').onclick=()=>enterStudio('assets',{user:true,focus:true});
 async function openProjectSettings(){
   await openView(activePlatform||'wechat_official_account',{focus:true});
   setWechatPage('settings');
   $('contextSettingsTab').click();
 }
 const characters=OACharacterLibrary(mediaTool,openProjectSettings);
 const director=OADirector(mediaTool,sendChatRequest,()=>!!hostCapabilities.message?.text,{
    guideChanged:()=>guide?.render(),
    sound:studioSound,chooseCharacter:characters.choose,readCharacterOriginal:characters.readOriginal,
    closeCharacterPicker:characters.closePicker,
    go:section=>enterStudio(section,{user:true,focus:true}),
    back:()=>enterStudio(mainStudio,{user:true,focus:true}),
    library:()=>enterStudio('assets',{kind:'video',user:true,focus:true}),
    asset:asset=>enterStudio('assets',{kind:asset.kind||asset.family,asset,user:true,focus:true}),
    source:url=>{
      const target=new URL(url);
      if(target.protocol!=='https:'||!['www.douyin.com','deepmind.google'].includes(target.hostname))
        throw Error('DIRECTOR_INVALID_SOURCE');
      return openXLink(target.href);
    },
    project:openProjectSettings,openLink:openXLink,
 });
 const intro=$('homeIntroPlayer'),introToggle=$('homeIntroToggle');
 let introPreference=false;
 const homeIntro=intro?OAFramePlayer(intro,async start=>{
   OAUI.set($('homeIntroStatus'),'');
   return content(await tool('wce.ui.video.workspace',{action:'intro_frames',start}));
 },10.5,{poster:intro.dataset.poster,showControls:false,loop:true,failed:()=>{
   introPreference=false;
   OAUI.set($('homeIntroStatus'),'宣传片暂时无法播放。');
   syncIntro();
 }}):null;
 function syncIntro(){
   if(!homeIntro)return;
   const visible=ready&&!closed&&view==='about'&&!document.hidden;
   if(visible&&introPreference)homeIntro.play();
   else if(homeIntro.isPlaying())homeIntro.pause();
   introToggle.disabled=!visible;
   OAUI.set(introToggle,homeIntro.isPlaying()?'暂停':'播放');
 }
 if(introToggle){
   introToggle.onclick=()=>{introPreference=!homeIntro.isPlaying();syncIntro();};
   document.addEventListener('visibilitychange',syncIntro);
 }
 function showMedia(section,{kind='',asset,shot}={}){
   const before=mediaView;
   if(!before&&!section)return;
   if(before!==section){
     navigationEpoch++;
     if(before==='assets'){
       gallery.close();characters.close();monitor.close();imageAssets.close();newsSources.close();$('articleAssetLibrary').hidden=true;
       document.dispatchEvent(new CustomEvent('jiusera:asset-category',{detail:{kind:'',asset:null}}));
     }
     if(before==='tasks')monitor.close();
     if(before==='providers')showMediaProvider('');
   }
   mediaView=section;
   $('mediaStudio').hidden=!section;
   document.body.classList.toggle('oa-video-open',!!section);
   if(section!=='assets')paintAssetKind('');
   if(!section){director.close();return;}
   if(!before){
     closeXTools();xManagement.deactivate();xhsManagement.deactivate();projectContext.deactivate();
     void director.open(section,shot);
   }else{
     director.view(section);
     if(shot)void director.openShot(shot);
   }
   if(section==='assets'&&(before!==section||kind!==assetKind||asset))showAssetKind(kind,asset);
   if(section==='tasks'&&before!==section)monitor.open('all');
   if(section==='providers'&&before!==section)showMediaProvider('video');
 }
 function paintStudioNavigation(){
   studioParent.setAttribute('aria-expanded',String(studioExpanded));
   studioEntries.hidden=!studioExpanded;
   for(const button of studioEntries.querySelectorAll('[data-studio-page]'))
     button.setAttribute('aria-current',mediaView&&mainStudio===button.dataset.studioPage?'page':'false');
 }
 function enterStudio(section,{kind,asset,shot,user=false,focus=false}={}){
   if(closed||!ready||!$('inlineBinding').hidden)return;
   if(view!=='studio'){
     platformEpoch++;selectionIntent++;selectEpoch++;
     closeFloatingMenus();notice('');view='studio';
   }
   studioExpanded=true;
   if(section in studioURLs)mainStudio=section;
   if(user){
     explicitNavigation=true;
     if(section==='assets')updateAssetURL(assetRoute(kind));
     else if(mediaView==='assets')updateAssetURL('');
   }
   showMedia(section,{kind,asset,shot});renderView();renderPlatforms();
   if(focus&&!asset)$('directorTitle').focus({preventScroll:true});
 }
 function renderView(){
   document.body.classList.toggle('oa-platform-view',view==='platform');
   renderWechatWorkspace();
   syncIntro();
   $('openAhoyHome').hidden=view!=='about';
   $('nativeWorkspace').hidden=view!=='platform'||!$('inlineBinding').hidden;
   showcase.show(view==='studio-showcase');
   const screen=view==='studio'?(mediaView==='desk'?'canvas':mediaView):view;
   workbench.paint(screen,{showCanvas:screen==='canvas'});
   paintStudioNavigation();
   guide?.render();
 }
 async function openView(target,{user=false,focus=false,shot}={}){
   closeFloatingMenus();
   if(closed||!ready||!$('inlineBinding').hidden)return;
   if(target==='studio-showcase'){
     if(view!=='studio-showcase'){
       showcaseBack=view==='studio'?(mediaView==='assets'?assetRoute(assetKind):studioURLs[mediaView]||homeView):
         view==='platform'?(activePlatform||homeView):view==='startup'?homeView:view;
       platformEpoch++;selectionIntent++;selectEpoch++;navigationEpoch++;
       closeXTools();xManagement.deactivate();xhsManagement.deactivate();projectContext.deactivate();
       view=target;showMedia('');renderView();
     }
     if(user)explicitNavigation=true;
     if(focus)$('scTitle').focus({preventScroll:true});
     return;
   }
   if(view==='studio-showcase'&&!accountRead){
     view='startup';
     showcase.show(false);
     void refresh();
   }
   if(studioRoutes.has(target)){
     const {section,kind}=studioRoutes.get(target);
     enterStudio(section,{kind,user,focus,shot});
     return;
   }
   if(user&&mediaView==='assets')updateAssetURL('');
   if(activePlatform!==target||view!=='platform')notice('');
   if(user)explicitNavigation=true;
   if(target==='about'||target==='published'){
     platformEpoch++;selectionIntent++;selectEpoch++;navigationEpoch++;
     closeXTools();xManagement.deactivate();xhsManagement.deactivate();projectContext.deactivate();
     view=target;showMedia('');renderView();renderPlatforms();
     if(focus)$(target==='about'?'homeTitle':'wbPublishedTitle').focus();
     return;
   }
   if(view==='platform'&&activePlatform===target)return;
   view='platform';
   await selectPlatform(target,{focus,user});
 }
 guide=OAWorkflowGuide({
   status(){
     const row=accountRead&&view==='platform'&&current();
     return {work:view==='studio'?director.guideContext():null,platform:view==='platform'?activePlatform:'',
       account:row?{id:row.connection_id,label:name(row)||row.label||row.account_id||'',state:accountState(row)}:null};
   },
   async locate(target,step,currentRequest,scope,tab='text'){
     if(!ready||closed||!$('inlineBinding').hidden||(step===4&&!platform(target)))return false;
     await openView(target,{user:true});
     if(!currentRequest()||closed)return false;
     let control;
     if(step===4){
       if(view!=='platform'||activePlatform!==target)return false;
       accountsExpanded=true;syncAccountNavigation();revealSelectedAccount();
       control=accountList.querySelector('.is-selected .account-select')||platformButton();
     }else{
       if(view!=='studio'||mediaView!==studioRoutes.get(target).section)return false;
       if(step===2){
         const work=director.guideContext();
         if(work&&work.project===scope?.project&&work.work===scope.work){
           if(work.shot)control=$('directorTabs').querySelector(`[data-tab="${tab}"]`);
           else if(work.shots)control=$('directorSceneSelect');
           else if(!$('directorNewShot').disabled)control=$('directorNewShot');
           else control=$('directorNewScene');
         }else control=$('directorWork');
       }else{
         control=$(['directorChatWork','dmGoCanvas'][step])||
           assetKinds.querySelector('[data-asset-kind=characters]');
       }
       if(control?.disabled){
         if(step===0){$('directorMore').open=true;control=$('directorMore').querySelector('summary');}
         else control=$('directorTitle');
       }
     }
     if(!control?.getClientRects().length&&step===2)control=$('directorTitle');
     if(!control?.getClientRects().length)return false;
     control.focus();
     return true;
   }
 });
 $('openHome').onclick=()=>openView(homeView,{user:true,focus:true});
 studioParent.onclick=()=>{
   if(mediaView){studioExpanded=!studioExpanded;paintStudioNavigation();return;}
   void openView('media',{user:true,focus:true});
 };
 for(const button of studioEntries.querySelectorAll('[data-studio-page]'))
   button.onclick=()=>enterStudio(button.dataset.studioPage,{user:true,focus:true});
 $('refresh').addEventListener('click',()=>void refresh());$('showAdd').addEventListener('click',secure);
 $('accountCreate').addEventListener('click',async()=>{
   const row=current(),original=selected,editor=row&&editors.get(row.platform_id);if(!editor||!platform(row.platform_id)?.settings_supported)return;
   revealAccountConfiguration(row);
   const epoch=++navigationEpoch;
   const isCurrent=()=>!closed&&selected===original&&activePlatform===row.platform_id&&navigationEpoch===epoch&&
     current()?.binding_revision===row.binding_revision&&current()?.account_id===row.account_id;
   const ok=await editor.openCreator(row.connection_id,name(row),isCurrent);
   if(ok&&isCurrent()){editor.showCreator();if(!isWechat())$('settingsPanel').scrollIntoView({block:'start'});}
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
   revealAccountConfiguration(row);editor.showRules();
   if(!isWechat())$('settingsPanel').scrollIntoView({block:'start'});
   editor.chooseConfiguration(row.connection_id,name(row),()=>!closed&&selected===original&&activePlatform===row.platform_id&&
     navigationEpoch===epoch&&current()?.binding_revision===row.binding_revision&&current()?.account_id===row.account_id);
 });
 $('accountRules').addEventListener('click',async()=>{
   const row=current(),original=selected,editor=row&&editors.get(row.platform_id);if(!editor||!platform(row.platform_id)?.settings_supported)return;
   revealAccountConfiguration(row);
   const intent=++navigationEpoch;
   const isCurrent=()=>!closed&&selected===original&&navigationEpoch===intent&&
     current()?.binding_revision===row.binding_revision&&current()?.account_id===row.account_id;
   const ok=await editor.selectScope(row.connection_id,{isCurrent});if(!isCurrent())return;
   if(ok===false){notice('规则正在处理或结果待确认，请在原规则范围接续。',true);return;}
   if(activePlatform===row.platform_id&&showSettings(row.platform_id)){
     editor.showRules();if(!isWechat())$('settingsPanel').scrollIntoView({block:'start'});
   }
 });
 addEventListener('pagehide',event=>{if(!event.persisted)dispose();});buttons();
 rpc('ui/initialize',{appInfo:{name:'openahoy-management',version:'3.0.0'},protocolVersion:'2026-01-26',appCapabilities:{availableDisplayModes:['inline','fullscreen']}})
 .then(async host=>{if(closed||host?.protocolVersion!=='2026-01-26'||!host.hostCapabilities?.serverTools)throw new Error('NO_SERVER_TOOLS');
   hostCapabilities=host.hostCapabilities;ready=true;applyHostTheme(host.hostContext);projectContext.setReady(true,!!hostCapabilities.message?.text);bridge.postMessage({jsonrpc:'2.0',method:'ui/notifications/initialized'},'*');
   void openView(addressLaunch.target||hostView||homeView,{shot:addressLaunch.shot});
   buttons();await refresh();
   // Optional host checks run after the first paint.
   requestAnimationFrame(()=>requestAnimationFrame(()=>{
     if(closed||!ready)return;
     syncIntro();
   }));
 }).catch(()=>{ready=false;buttons();notice('当前宿主管理工具桥不可用，未进行任何账号操作。',true);workbench.failed();});
})();

'''


def resource():
    from .own_settings_ui import LOGO, STYLE
    from .own_management_ui import HOME_STYLE, STYLE as management_style, native_page_body
    from .management_workspace_ui import NATIVE_FINISH_STYLE, PLATFORM_ACCOUNT_NAV_STYLE
    from .management_interactions import STYLE as interaction_style, SCRIPT as interaction_script
    from .workflow_guide_ui import STYLE as guide_style, SCRIPT as guide_script
    from .workbench_ui import STYLE as workbench_style, SCRIPT as workbench_script, trend_resource
    from .writing_workflow_ui import SCRIPT as writing_rules_script
    from .own_wechat_management import settings_html, settings_script
    from .own_inline_binding_ui import SCRIPT as binding_script
    from .video_inline_ui import SCRIPT as video_script
    from .audio_workspace_ui import STYLE as audio_style, SCRIPT as audio_script
    from .wechat_analytics_ui import STYLE as stats_style, SCRIPT as stats_script
    from .wechat_workspace_ui import STYLE as wechat_workspace_style
    from .video_provider_ui import STYLE as provider_style, SCRIPT as provider_script
    from .openai_gif_ui import STYLE as gif_style
    from .video_workspace_ui import STYLE as video_style
    from .media_monitor_ui import STYLE as monitor_style, SCRIPT as monitor_script
    from .video_director_canvas_ui import STYLE as canvas_style, SCRIPT as canvas_script
    from .video_director_ui import STYLE as director_style, SCRIPT as director_script
    from .video_director_monitor_ui import STYLE as review_style, SCRIPT as review_script
    from .character_library_ui import STYLE as characters_style, SCRIPT as characters_script
    from .character_turntable_ui import SCRIPT as character_turntable_script
    from .asset_catalog_ui import STYLE as assets_style, SCRIPT as assets_script
    from .source_library_ui import STYLE as sources_style, SCRIPT as sources_script
    from .studio_showcase_ui import STYLE as showcase_style, SCRIPT as showcase_script
    from .video_frame_player import STYLE as frame_style, SCRIPT as frame_script
    from .x_management_ui import HTML as x_html, SCRIPT as x_script
    from .xhs_management_ui import HTML as xhs_html, SCRIPT as xhs_script
    from .platform_branding import script as platform_branding_script
    from .project_context_ui import HTML as project_html, SCRIPT as project_script, STYLE as project_style
    from .content_templates_ui import STYLE as template_style
    from .x_schedule_ui import STYLE as schedule_style, SCRIPT as schedule_script
    from .x_operating_ui import STYLE as operating_style, SCRIPT as operating_script
    html = ('<!doctype html><html lang="en"><meta charset="utf-8">'
        '<meta name="viewport" content="width=device-width,initial-scale=1">'
        '<title>Jiusera · Workspace</title><style>' + STYLE + management_style + project_style + template_style + schedule_style + operating_style + '</style>'
        + '<style>' + font_style() + NATIVE_FINISH_STYLE + video_style + provider_style + audio_style + stats_style + gif_style + HOME_STYLE + frame_style + monitor_style + director_style + review_style + characters_style + canvas_style + interaction_style + wechat_workspace_style + PLATFORM_ACCOUNT_NAV_STYLE + guide_style + workbench_style + assets_style + sources_style + showcase_style + trend_resource('css') + '</style>'
        + mark_chrome(native_page_body(LOGO, settings_html(templates=True) + x_html + xhs_html + project_html))
        + '<script>' + locale_script() + platform_branding_script() + settings_script(compact=True) + binding_script + video_script + frame_script + provider_script + audio_script + stats_script + monitor_script + canvas_script + review_script + director_script + character_turntable_script + characters_script + assets_script + sources_script + x_script + xhs_script + schedule_script + operating_script + project_script + interaction_script + guide_script + trend_resource('js') + workbench_script + showcase_script + writing_rules_script + SCRIPT + '</script></body></html>')
    return {'contents': [{'uri': RESOURCE, 'mimeType': MIME, 'text': html,
        '_meta': {'ui': {'csp': {'connectDomains': [], 'resourceDomains': ['https://pbs.twimg.com', 'https://cdn1.suno.ai',
                                                                 'https://cdn2.suno.ai', 'https://suno-data-uploads.s3.amazonaws.com', 'https://acemusic.ai'], 'frameDomains': []}},
                  'openai/ui': {'availableDisplayModes': ['inline', 'fullscreen'], 'preferredDisplayMode': 'inline'}}}]}


class NativeManagement:
    def resource(self):
        return resource()

    def close(self):
        pass  # The native view owns no HTTP listener or account session.
