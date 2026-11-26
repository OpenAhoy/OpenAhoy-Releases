"""Static MCP App. Account data arrives through the standard parent bridge."""
from .own_native_management_contract import RESOURCE
from .management_locale import mark_chrome, script as locale_script
from .management_fonts import style as font_style

MIME = 'text/html;profile=mcp-app'

# Synchronize before the workspace bundle initializes its views or the MCP handshake completes.
WORKSPACE_THEME = r"""
const OAWorkspaceTheme = (() => {
  let query, view = window;
  while (view) {
    try {
      const preference = view.matchMedia('(prefers-color-scheme: dark)');
      if (preference.media === 'not all') break;
      query = preference;
      // The embedding element can force a scheme on the child. Prefer the outermost
      // accessible system preference, leaving cross-origin host windows opaque.
      if (view.parent === view) break;
      view = view.parent;
    } catch { break; }
  }
  function apply(theme) {
    if (document.body.dataset.colorScheme === theme) return;
    document.documentElement.style.colorScheme = theme;
    document.body.dataset.colorScheme = theme;
  }
  function sync() { apply(query.matches ? 'dark' : 'light'); }
  if (query) {
    sync();
    query.addEventListener('change', sync);
  }
  return {
    host(context) {
      if (!query && ['light', 'dark'].includes(context?.theme)) apply(context.theme);
    },
    dispose() { query?.removeEventListener('change', sync); }
  };
})();
"""


SCRIPT = r'''
(() => {
 'use strict';
 const $=id=>document.getElementById(id),bridge=window.parent,pending=new Map();
 const accountPanel=$('accountPanel'),accountList=$('accounts'),platformNavigation=$('platformNavigation');
 const addWechatAccount=document.createElement('button');
 const compactAccounts=matchMedia('(max-width:560px)');
 const wechatSide=$('wbWechatTools'),wechatBack=$('wechatWorkspaceBack');
 const wechatActions=$('accountTools').parentElement;
 const accountHeader=wechatActions.parentElement;
 const wechatTabs=$('wechatWorkspaceNavigation');
 const wechatDock=OAWorkbenchDockDisclosure(document.querySelector('.wb-dock [data-wb-route=openahoy]'),wechatTabs,
   ()=>wechatTabs.querySelector('[aria-pressed=true]'));
 let wasWechat=false;
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
 const allowed=new Set(['own.wechat.authorized_drafts','own.wechat.content','own.drafts.inventory','own.drafts.current.read',
   'own.drafts.current.merge','own.drafts.current.status','wce.ui.openahoy.mcp.check',
   'own.publications.current.dispatch','own.publications.current.poll','own.publications.current.status',
   'wce.ui.wechat.component_binding','wce.ui.characters.dry_run',
   'own.sources.library','audio.project.presets','wce.ui.management.overview','wce.ui.management.disconnect','wce.ui.management.save_display_name','wce.ui.platform.action','x.ui.action','xhs.ui.action','x.attempt.status','wce.ui.projects.action','own.templates.read','wce.ui.templates.download','video.ark.connection.status','video.tokenhex.connection.check','wce.ui.video.credential','wce.ui.video.vidmuse','wce.ui.video.workspace','video.director.read','video.director.edit','wce.ui.video.director.media','wce.ui.wechat.storage_recovery','wce.ui.wechat.analytics','wce.ui.writing.rules','wce.ui.studio']);

 let counter=0,navigationEpoch=0,ready=false,closed=false,refreshing=false,launching=false,backendOpening=false,hostCapabilities={},rows=[],directory=[],selected='',activePlatform='';
 const homeView='published';
 let view='startup',hostLaunch=null,explicitNavigation=false,guide=null,accountRead=false;
 const wechatPlatform='wechat_official_account';
 const xPlatform='x';
 const douyinPlatform='douyin';
 const accountRoutes=new Set([wechatPlatform,xPlatform,douyinPlatform]);
 let profileReadIntent=0,profileReadOwner='';
 let wechatPage='settings',wechatConnection='',xConnection='',boardEntry=null;
 const wechatPages=['monitor','settings','profile','articles','media','readers','messages','comments',
   'menu','shop','coupons','stores','channels','web','operations','publish'];
 const wechatContentRoutes=['media','readers','comments','channels','operations','publish'];
 const wechatDeskRoutes=['messages','menu','shop','coupons','stores','web'];
 const isWechat=()=>view==='platform'&&activePlatform===wechatPlatform;
 const isXWorkspace=()=>view==='platform'&&activePlatform===xPlatform;
 const notice=(text,error=false,...values)=>{OAUI.set($('notice'),text,...values);$('notice').className='notice'+(error?' error':'');};
 const key=row=>JSON.stringify([row.platform_id,row.connection_id]);
 const platform=id=>directory.find(p=>p.id===id);
 const current=()=>rows.find(row=>key(row)===selected&&row.platform_id===activePlatform);
 const componentOnly=row=>row?.binding_provider==='WECHAT_THIRD_PARTY';
 const official=row=>row.platform_id===wechatPlatform&&row.official_profile?.state==='ACTIVE'?row.official_profile:null;
 const name=row=>{
   const info=official(row);
   return ((info?.use_official||Number.isSafeInteger(info?.identity_verified_at))&&info?.nickname)||row.presentation?.display_name||'';
 };
 const platformNames=new Map([['wechat_official_account','公众号'],['x','X'],['xiaohongshu','小红书']]);
 const platformName=id=>platformNames.get(id);
 const assetLabels={characters:'形象',images:'图片',gif:'动图',video:'视频',audio:'音频',articles:'文章',sources:'信源库'};
 const modelAliases=new Map([['providers','video'],['video-providers','video'],['gif-providers','gif'],['audio-providers','music']]);
 const modelSections=new Map([...document.querySelectorAll('#wbModels [data-model-pane]')].map(pane=>[pane.dataset.modelPane,pane]));
 const modelLayout=OAModelLayout();
 const modelTiles=new Map([...$('wbModelGrid').querySelectorAll('[data-model-id]')].map(tile=>[tile.dataset.modelId,tile]));
 const modelGroupOf=(group,alias)=>modelSections.has(group)?group:modelAliases.get(alias)||'';
 const modelId=value=>modelTiles.has(value)?value:'';
 let modelGroup='',activeModel='',modelDetailTrigger=null;
 const studioRoutes=new Map([
   ['jiusera-monitor',{section:'monitor'}],['jiusera-canvas',{section:'desk'}],['jiusera-assets',{section:'assets'}],
   ['media',{section:'monitor'}],...Object.keys(assetLabels).map(kind=>[kind,{section:'assets',kind}])
 ]);
 const studioURLs={monitor:'jiusera-monitor',desk:'jiusera-canvas',assets:'jiusera-assets'};
 const lunifyRoutes=new Set(['l-unify-home','l-unify-songs','l-unify']);
 const lunifyFields=['project','song','version'];
 function lunifySelection(params){
   const selection={};
   for(const field of lunifyFields){
     const value=params.get(field)||params.get(field+'_id');
     if(value)selection[field]=value;
   }
   return selection.project?selection:undefined;
 }
 function lunifySelectionFromURL(query){
   const fragment=new URLSearchParams(location.hash.slice(1));
   if(fragment.get('view')==='l-unify')return lunifySelection(fragment);
   return lunifySelection(query);
 }
 function route(value){
   if(value==='home')return homeView;
   if(value==='studio-showcase')return 'jiusera-assets';
   if(value==='settings')return 'about';
   if(modelAliases.has(value))return 'models';
   return value==='about'||value==='published'||['models','audio-workspace','profile','music-recipes',douyinPlatform].includes(value)||lunifyRoutes.has(value)||value==='openahoy'||studioRoutes.has(value)||platformNames.has(value)?value:'';
 }
 function routeFromURL(){
   const hash=location.hash.slice(1),query=new URLSearchParams(location.search),fragment=new URLSearchParams(hash);
   return [fragment.get('view'),fragment.get('platform'),query.get('view'),query.get('platform'),hash].map(route).find(Boolean)||'';
 }
 function launchFromURL(){
   const target=routeFromURL(),query=new URLSearchParams(location.search);
   if(target==='models'){
     const hash=location.hash.slice(1),fragment=new URLSearchParams(hash);
     const fragmentRoute=[fragment.get('view'),fragment.get('platform'),hash].find(value=>route(value)===target);
     const scope=fragmentRoute?fragment:query;
     const alias=fragmentRoute||[query.get('view'),query.get('platform')].find(value=>route(value)===target);
     return {target,modelSection:modelGroupOf(scope.get('group'),alias),modelProvider:modelId(scope.get('provider'))};
   }
   if(accountRoutes.has(target)){
     const fragment=new URLSearchParams(location.hash.slice(1));
     const fromFragment=route(fragment.get('view'))===target||route(fragment.get('platform'))===target;
     const scope=fromFragment?fragment:query;
     return {target,connection:scope.get('connection_id')||'',page:scope.get('tab')};
   }
   const fragment=new URLSearchParams(location.hash.slice(1));
   const mvSource=fragment.has('view')?fragment:query;
   if((target==='jiusera-monitor'||target==='media'||target==='l-unify'&&mvSource.get('video')==='1')&&['project','work'].every(f=>/^[a-f0-9]{32}$/.test(mvSource.get(f)||'')))
     return {target,imwVideo:true,shot:{kind:'mv-work',scope:{project_id:mvSource.get('project'),work_id:mvSource.get('work')}},
       musicSelection:target==='l-unify'&&lunifyFields.every(k=>mvSource.get(k))?lunifySelection(mvSource):undefined};
   const fields=['project','work','scene','shot','revision'];
   const shotScope=fragment.get('view')==='jiusera-canvas'&&fragment.has('project')?fragment:query;
   const identifiers=fields.map(field=>shotScope.get(field));
   if((!target||target==='jiusera-canvas')&&identifiers.every(value=>/^[a-f0-9]{32}$/.test(value||''))){
     const scope=Object.fromEntries(fields.map((field,index)=>[field+'_id',identifiers[index]]));
     return {target:'jiusera-canvas',shot:{scope,tab:shotScope.get('tab')}};
   }
   const musicScope=fragment.get('view')===target?fragment:query;
   if(target==='l-unify-songs'){
     const project=musicScope.get('project')||musicScope.get('project_id')||'';
     return {target,musicProject:/^[a-f0-9]{32}$/.test(project)?project:undefined};
   }
   if(target==='l-unify'){
     const feature=musicScope.get('feature');
     if(musicScope.get('video')!=='1'&&['project','work'].every(k=>/^[a-f0-9]{32}$/.test(musicScope.get(k)||'')))
       return {target,musicSelection:lunifySelection(musicScope),foldedScope:{project_id:musicScope.get('project'),work_id:musicScope.get('work')}};

     return {target,imwVideo:musicScope.get('video')==='1',musicSelection:lunifyFields.every(k=>musicScope.get(k)||musicScope.get(k+'_id'))?lunifySelectionFromURL(query):undefined,musicFeature:['master','solo'].includes(feature)?feature:undefined};
   }
   return {target};
 }
 const addressLaunch=launchFromURL();
 function clearAccountQuery(url){
   for(const field of ['view','platform']){
     const target=route(url.searchParams.get(field));
     if(accountRoutes.has(target)||target==='models')url.searchParams.delete(field);
   }
   if(routeFromURL()==='models')for(const field of ['group','provider'])url.searchParams.delete(field);
   if(accountRoutes.has(routeFromURL())){
     url.searchParams.delete('connection_id');
     url.searchParams.delete('tab');
   }
 }
 function updateAccountURL(target,connection='',tab='settings',{push=false}={}){
   try{
     if(!['http:','https:','file:'].includes(location.protocol))return;
     const url=new URL(location.href);
     clearAccountQuery(url);
     const fragment=new URLSearchParams();
     if(target)fragment.set('view',target);
     if(accountRoutes.has(target)){
       if(connection)fragment.set('connection_id',connection);
       if(target===wechatPlatform&&['monitor','profile','articles'].includes(tab))fragment.set('tab',tab);
     }
     url.hash=fragment.toString();
     if(url.href!==location.href)history[push?'pushState':'replaceState'](history.state,'',url);
   }catch(_){}
 }
 const initializedEditors=new Set();let xManagement=null,xhsManagement=null,projectContext=null,contextOpen=false;
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
 const editors=new Map(Object.entries(OAPlatformSettings).map(([id,adapter])=>[id,adapter.mount((operation,args)=>platformCall(id,operation,args),()=>{navigationEpoch++;},{
  templateCall:(name,args)=>tool(name,args),
  async configurationSources(connection_id,templates){
   if(templates.length){
    const catalog=content(await tool('own.templates.read',{view:'catalog'}));
    const known=[...catalog.templates,...(catalog.archived_templates||[])];
    if(templates.some(ref=>!known.some(item=>['id','version','manifest_sha256'].every(key=>item[key]===ref[key]))))
      throw new Error('RULES_CONFIG_TEMPLATE_UNAVAILABLE');
   }
   const current=content(await tool('wce.ui.projects.action',{operation:'READ',
    arguments:{platform_id:'wechat_official_account',connection_id}}));
   if(!current.project)return {project:null};
   const skills=current.settings.skills.map(id=>current.sources.find(row=>row.id===id&&row.kind==='skill'));
   if(skills.some(row=>!row||row.status!=='CURRENT'))throw new Error('RULES_CONFIG_PROJECT_CHANGED');
   return {project:{id:current.project.id,source_digest:current.project.source_digest,
    skills:skills.map(({id,sha256})=>({id,sha256}))}};
  },
  sendChatRequest,
  openProjectSettings:()=>$('contextSettingsTab').click(),
  openWechatArticles:()=>setWechatPage('articles'),
  templateConnections(){return view==='platform'&&activePlatform===id?
    rows.filter(r=>r.platform_id===id&&['BOUND','BOUND_IDLE','CONNECTED','BUSY'].includes(r.state))
      .map(r=>({connection_id:r.connection_id,name:name(r)})):[];},
  templateTarget(){const row=current(),capture=navigationEpoch;return row&&row.platform_id===id&&(!componentOnly(row)||row.state==='BOUND_IDLE')?{connection_id:row.connection_id,name:name(row),official_profile:row.official_profile,component_grant:row.component_grant,isCurrent:()=>{const live=current();return !closed&&ready&&navigationEpoch===capture&&live&&key(live)===key(row)&&live.account_id===row.account_id&&live.binding_revision===row.binding_revision;}}:null;},
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
 function dispose(){OAWorkspaceTheme.dispose();disableIMW();OAStudio.dispose();homeIntro?.close();showMedia('');studioSound.close();video.dispose();if(audioMode)audioWorkspace.close();xManagement?.dispose();xhsManagement?.dispose();projectContext?.dispose();closed=true;ready=false;for(const editor of editors.values())editor.setReady(false);
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
     if(target&&!closed&&!addressLaunch.target&&!hostLaunch&&!explicitNavigation){
       hostLaunch={target,connection:typeof args?.connection_id==='string'?args.connection_id:'',
         modelSection:target==='models'?modelGroupOf(args?.group,args?.view||args?.platform_id):undefined,modelProvider:modelId(args?.provider)};
       if(ready&&view===homeView&&target!==homeView)void openView(target,hostLaunch);
     }
     return;
   }
   if(v.method==='ui/notifications/host-context-changed'&&!Object.hasOwn(v,'id')){if(ready&&!closed)OAWorkspaceTheme.host(v.params);return;}
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
   OAUI.set($('showAdd').querySelector('span'),addLabel);OAUI.attr($('showAdd'),'aria-label',addLabel);OAUI.attr($('showAdd'),'title',addLabel);
   $('showAdd').disabled=!ready||refreshing||launching||!p?.binding_supported||
     (activePlatform==='xiaohongshu'&&!(xhsManagement?.canBegin()));
   addWechatAccount.disabled=$('showAdd').disabled;
   $('accountRules').disabled=!ready||refreshing||!row||(componentOnly(row)&&row.state!=='BOUND_IDLE')||!platform(row.platform_id)?.settings_supported||!editors.has(row.platform_id);
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
 async function selectPlatform(id,{focus,user,connection,page}){
   showMedia('');const intent=++platformEpoch;selectEpoch++;selectionIntent++;navigationEpoch++;
   closeXTools();activePlatform=id;
   accountsExpanded=user||!compactAccounts.matches;
   paintAccountHeader();
   if(isWechat()){
     wechatPage=wechatPages.includes(page)?page:'settings';
     wechatConnection=connection;selected='';
   }
   if(isXWorkspace()){xConnection=connection;selected='';}
   renderView();renderPlatforms();await renderAccounts();if(closed||intent!==platformEpoch||view!=='platform'||activePlatform!==id)return;showSettings(id);
   if(id==='x'&&ready&&!contextOpen)xManagement.activate();else xManagement.deactivate();
   if(id==='xiaohongshu'&&ready&&!contextOpen)xhsManagement.activate();else xhsManagement.deactivate();
   $('xCapabilities').hidden=id!=='x';
   if(focus)(isWechat()?$('wechatBack'):isXWorkspace()?$('xPlatformBack'):platformButton())?.focus({preventScroll:true});
 }
 function profileImage(a,label){
   if(a?.width!==96||a.height!==96||typeof a.rgba!=='string'||a.rgba.length!==49152)return null;
   try{
     const raw=atob(a.rgba);if(raw.length!==36864)return null;
     const canvas=document.createElement('canvas');canvas.width=canvas.height=96;
     canvas.setAttribute('role','img');OAUI.attr(canvas,'aria-label',label);
     canvas.getContext('2d').putImageData(new ImageData(Uint8ClampedArray.from(raw,c=>c.charCodeAt(0)),96,96),0,0);
     return canvas;
   }catch(_){return null;}
 }
 function avatar(row){
   const box=document.createElement('div');box.className='avatar';box.setAttribute('aria-label',name(row)+'，未设置头像');
   const info=official(row),a=(info?.use_official&&info.avatar)||row.presentation?.avatar;
   if(Number.isSafeInteger(info?.identity_verified_at)&&typeof info.avatar_url==='string'){
     try{
       const url=new URL(info.avatar_url);
       if(['https://mmbiz.qpic.cn','https://mmbiz.qlogo.cn','https://wx.qlogo.cn','https://thirdwx.qlogo.cn'].includes(url.origin)&&url.pathname!=='/'&&!url.search&&!url.hash&&!url.username&&!url.password){
         const img=document.createElement('img');img.alt=OAUI.format('官方头像');img.referrerPolicy='no-referrer';
         img.style.width=img.style.height='100%';img.style.objectFit='cover';
         const fallback=()=>{box.textContent=Array.from(name(row))[0]||'账';box.setAttribute('aria-label',OAUI.format('头像暂不可用'));};
         fallback();
         img.addEventListener('load',()=>{box.replaceChildren(img);box.setAttribute('aria-label',img.alt);},{once:true});
         img.referrerPolicy='no-referrer';img.src=url.href;return box;
       }
     }catch(_){}
   }
   if(row.platform_id===douyinPlatform&&['image/jpeg','image/png','image/webp'].includes(a?.mime)&&
      typeof a.data==='string'&&a.data.length<=65536&&/^[A-Za-z0-9+/]+={0,2}$/.test(a.data)){
     const img=document.createElement('img');
     img.src='data:'+a.mime+';base64,'+a.data;img.alt='';
     img.style.width=img.style.height='100%';img.style.objectFit='cover';
     img.addEventListener('error',()=>{box.textContent=Array.from(name(row))[0]||'账';box.setAttribute('aria-label',name(row)+'，未设置头像');},{once:true});
     box.append(img);box.setAttribute('aria-label',name(row)+'头像');return box;
   }
   if(row.platform_id==='x'&&typeof row.profile_image_url==='string'&&/^https:\/\/pbs\.twimg\.com\/profile_images\/[A-Za-z0-9_./-]+$/.test(row.profile_image_url)){
    const img=document.createElement('img');img.src=row.profile_image_url;img.alt=name(row)+'头像';img.referrerPolicy='no-referrer';img.style.width=img.style.height='100%';box.append(img);return box;
   }
   const canvas=profileImage(a,'头像');
   if(canvas){canvas.style.width=canvas.style.height='100%';box.append(canvas);box.setAttribute('aria-label',name(row)+'头像');return box;}
   box.textContent=Array.from(name(row))[0]||'账';return box;
 }
 let removalTarget=null, removing=false;
 const removalDialog=$('accountRemoveDialog');
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
     OAUI.set($('accountRemoveNote'),row.platform_id===wechatPlatform?
       '将停止此号在本工作区的连接并移除账号卡。文章、配置及其他账号会保留。微信侧授权可在微信后台管理。':
       '将断开此账号在 Jiusera 的连接并停止后续自动任务。平台账号、内容、资产和操作记录会保留。');
     OAUI.set($('accountRemoveTitle'),row.platform_id===wechatPlatform?'解绑并移除':'移除账号');
     removalDialog.showModal();
   };
   rebind.type='button';OAUI.set(rebind,'重新绑定');
   rebind.onclick=async event=>{
     if(!event.isTrusted||!ready||closed||removing||refreshing||activePlatform!==row.platform_id)return;
     menu.open=false;
     await select(key(row));
     const chosen=current();
     if(closed||!chosen||key(chosen)!==key(row)||chosen.binding_revision!==row.binding_revision)return;
     if(row.platform_id===wechatPlatform)return openWechatBinding(row,toggle);
     if(row.platform_id==='xiaohongshu')return xhsManagement.reconnect(row.connection_id);
     await openXAuthorization(true);
   };
   if(row.platform_id==='x'){
     const developer=document.createElement('button');developer.type='button';
     OAUI.raw(developer,'X Developer Console');
     developer.onclick=()=>{menu.open=false;void openXDeveloper(row);};
     actions.append(developer);
   }
   if(row.platform_id===wechatPlatform){
     const status=document.createElement('button');status.type='button';OAUI.set(status,'查看状态详情');
     status.onclick=async()=>{
       menu.open=false;
       const live=rows.find(item=>key(item)===key(row)&&item.account_id===row.account_id);
       if(!isWechat()||!live)return;
       await showWechatStatus(live);
     };
     OAUI.set(remove,'解绑并移除');
     actions.append(rebind,status,remove);
   }else if(bindingAvailable)actions.append(rebind,remove);
   menu.append(toggle,actions);
   bindWorkspacePopover(menu);
   return menu;
 }
 function placeWorkspacePopover(anchor,popup,{size=224,start=false,limit=Infinity,inward=false}={}){
   const box=anchor.getBoundingClientRect(),root=document.documentElement;
   const width=Math.min(size,root.clientWidth-16);
   const left=Math.max(8,Math.min(root.clientWidth-width-8,start?box.left:box.right-width));
   if(inward){
     const height=Math.min(root.clientHeight-16,popup.scrollHeight+2);
     const top=Math.min(root.clientHeight-height-8,Math.max(8,box.top+(box.height-height)/2));
     Object.assign(popup.style,{width:width+'px',left:Math.max(8,box.left-width-6)+'px',
       maxHeight:height+'px',top:top+'px',bottom:'auto'});
     return;
   }
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
       placeWorkspacePopover(anchor,popup,{inward:wechatSide.contains(anchor)});
     }else unmountWorkspacePopover(popup);
   });
 }
 bindWorkspacePopover(document.querySelector('#accountTools details.oa-more-settings'));
 addEventListener('resize',()=>{if(view==='platform'){closeFloatingMenus();syncAccountNavigation();}});
 accountList.addEventListener('scroll',()=>closeFloatingMenus(),{passive:true});
 accountPanel.addEventListener('scroll',()=>closeFloatingMenus(),{passive:true});
 $('accountRemoveCancel').onclick=()=>removalDialog.close();
 removalDialog.addEventListener('close',()=>{
   const account=removalTarget;removalTarget=null;
   if(!removing&&account&&isWechat())
     Array.from(accountList.children).find(el=>el.dataset.accountKey===key(account))?.querySelector('summary')?.focus();
 });
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
       platform_id:row.platform_id,connection_id:row.connection_id,account_id:row.account_id,binding_revision:row.binding_revision,
       ...(row.platform_id===wechatPlatform&&Number.isSafeInteger(row.component_grant?.generation)?
         {expected_grant_generation:row.component_grant.generation}:{})
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
   const [stateLabel,tone]=row.platform_id===xPlatform?openAhoyBoard.connectionState(row):[accountState(row),''];
   const connected=row.platform_id===xPlatform?tone==='ready':['CONNECTED','BOUND','BOUND_IDLE'].includes(row.state);
   state.className='status'+(connected?' good':'');
   OAUI.set(state,stateLabel);
   label.className='oa-account-copy';
   label.append(title,state);
   if(row.platform_id===wechatPlatform){
     const identifier=row.account_id||row.connection_id;
     const duplicate=rows.some(item=>item.platform_id===wechatPlatform&&key(item)!==id&&name(item)===name(row));
     if(duplicate){
       const tail=document.createElement('span');
       tail.className='oa-account-id-tail';OAUI.raw(tail,identifier.slice(-8));
       label.append(tail);
       OAUI.attr(pick,'aria-label','{0} · {1} · {2}',display||OAUI.message('账号资料暂不可用'),identifier,OAUI.message(accountState(row)));
     }
   }
   const photo=avatar(row);photo.setAttribute('aria-hidden','true');
   pick.append(photo,label);
   pick.onclick=async()=>{
     const intent=++selectionIntent;
     await select(id);
     if(intent!==selectionIntent||id!==selected)return;
     if(isWechat()){
       wechatConnection=row.connection_id;
       updateAccountURL(wechatPlatform,wechatConnection,wechatPage);
       paintWechatConnection();
     }else if(isXWorkspace()){
       xConnection=row.connection_id;
       updateAccountURL(xPlatform,xConnection);
       paintXConnection();
     }else closeAccountNavigation({compactOnly:true,focus:true});
   };
   el.append(pick);
   const canManage=row.account_id&&/^[a-f0-9]{64}$/.test(row.binding_revision)&&row.error!=='CONNECTION_ENTRY_UNAVAILABLE';
   if((canManage||row.platform_id==='x'||(row.platform_id===wechatPlatform&&row.account_id&&!row.recovery)))el.append(accountMenu(row,canManage));
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
   if(staged&&accepted&&(!componentOnly(row)||row.state==='BOUND_IDLE'))void editor.loadAccountScope(row?.connection_id||'');
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
   const valid=isWechat()&&wechatPage==='monitor'&&!componentOnly(row)&&
     row?.platform_id===activePlatform&&['BOUND','BOUND_IDLE','CONNECTED','BUSY'].includes(row.state);
   analytics?.target(valid?row:null,valid?name(row):'');
 }
 function renderWechatWorkspace(){
   const inWechat=isWechat();
   const shown=inWechat;
   if(inWechat!==wasWechat){
     wasWechat=inWechat;
     if(inWechat){wechatSide.append(wechatBack,wechatActions);}
     else {accountHeader.prepend(wechatBack);accountHeader.append(wechatActions);}
   }
   wechatSide.hidden=!shown;
   const monitor=shown&&wechatPage==='monitor';
   const configs=shown&&wechatPage==='settings',profile=shown&&wechatPage==='profile',
     articles=shown&&wechatPage==='articles';
   const contentRoute=shown&&wechatContentRoutes.includes(wechatPage);
   const deskRoute=shown&&wechatDeskRoutes.includes(wechatPage);
   const component=shown&&componentOnly(current());
   const componentConfigured=component&&current().state==='BOUND_IDLE';
   $('wechatComponentAccessNotice').hidden=!component||profile||(configs&&componentConfigured);
   document.body.classList.toggle('oa-wechat-view',isWechat());
   $('wechatWorkspaceBack').hidden=!shown;
   $('wechatAccountPicker').hidden=!shown;
   wechatDock.show(shown);
   for(const [id,value] of [['wechatArticlesTab',articles],['wechatMediaTab',wechatPage==='media'],
       ['wechatReadersTab',['readers','messages','comments'].includes(wechatPage)],
       ['wechatCommerceTab',['menu','shop','coupons','stores','operations'].includes(wechatPage)],
       ['wechatConfigTab',configs||profile||monitor||['channels','web'].includes(wechatPage)]])
     $(id).setAttribute('aria-pressed',String(value));
   $('wechatAnalytics').hidden=!monitor||component;
   $('settingsPanel').hidden=shown&&(!(configs||contentRoute)||(component&&!componentConfigured));
   $('wechatOfficialAccount').hidden=!profile;
   $('wechatArticlesPage').hidden=!articles;
   $('wechatAccountDesk').hidden=!deskRoute;
   accountDesk.target(current(),deskRoute?wechatPage:'');
   const activeEditor=editors.get(wechatPlatform);
   if(shown)activeEditor.showDesk(contentRoute?wechatPage:'');
   if(contentRoute)accountDesk.nav(wechatPage,$('wechatInlineDeskNavigation'));
   articleReader.target(articles?current():null);
   if(profile)paintOfficialProfile();
   const identity=profile?current():null;
   const owner=identity&&(identity.component_grant||componentOnly(identity))?
     JSON.stringify([identity.connection_id,identity.account_id,identity.component_grant?.generation]):'';
   if(owner!==profileReadOwner){
     profileReadOwner=owner;profileReadIntent++;$('wechatProfileRefresh').disabled=false;
     if(owner)void refreshWechatProfile();
   }
   syncAuthorizedDrafts(profile?current():null);
   targetAnalytics();
 }
 function setWechatPage(page,{rules=false}={}){
   if(!isWechat())return;
   closeFloatingMenus();
   wechatPage=page;
   if(routeFromURL()===wechatPlatform)updateAccountURL(wechatPlatform,wechatConnection,wechatPage);
   if(rules){contextOpen=false;projectContext.deactivate();showSettings(activePlatform);}
   renderWechatWorkspace();
 }
 const articleReader=OAWechatArticles(tool,openXLink,()=>setWechatPage('settings'));
 const accountDesk=OAWechatAccountDesk(tool,openXLink,setWechatPage);
 $('wechatProfileArticles').onclick=()=>setWechatPage('articles');
 $('wechatArticlesTab').onclick=()=>setWechatPage('articles');
 $('wechatMediaTab').onclick=()=>setWechatPage('media');
 $('wechatReadersTab').onclick=()=>setWechatPage('readers');
 $('wechatCommerceTab').onclick=()=>setWechatPage('menu');
 $('wechatConfigTab').onclick=()=>setWechatPage('settings');
 for(const entry of document.querySelectorAll('[data-wechat-desk]'))
   entry.onclick=()=>setWechatPage(entry.dataset.wechatDesk);
 OAUI.onChange(()=>{if(isWechat()&&wechatPage==='profile')paintOfficialProfile();});
 let authorizedDraftTarget='',authorizedDraftEpoch=0,authorizedDraftBusy=false,authorizedDraftNext=null;
 function syncAuthorizedDrafts(row){
   const grant=row?.component_grant, cid=Number.isSafeInteger(grant?.generation)?row.connection_id:'';
   const key=cid?cid+':'+grant.generation+':'+grant.state:'';
   $('wechatAuthorizedDrafts').hidden=!cid;
   $('wechatAuthorizedDraftsRead').disabled=!cid||authorizedDraftBusy;
   if(key===authorizedDraftTarget)return;
   authorizedDraftTarget=key;authorizedDraftEpoch++;authorizedDraftNext=null;authorizedDraftBusy=false;
   $('wechatAuthorizedDraftsRead').disabled=!cid;
   $('wechatAuthorizedDraftsNext').hidden=true;$('wechatAuthorizedDraftsNext').disabled=false;
   $('wechatAuthorizedDraftsRows').replaceChildren();$('wechatAuthorizedDraftContents').replaceChildren();
   OAUI.set($('wechatAuthorizedDraftsStatus'),'');
 }
 async function readAuthorizedDrafts(action,options={}){
   if(authorizedDraftBusy||!authorizedDraftTarget)return;
   const row=current(),issued=authorizedDraftEpoch;
   authorizedDraftBusy=true;
   $('wechatAuthorizedDraftsRead').disabled=$('wechatAuthorizedDraftsNext').disabled=true;
   OAUI.set($('wechatAuthorizedDraftsStatus'),'正在读取本号草稿');
   try{
     const result=await tool('own.wechat.authorized_drafts',{action,connection_id:row.connection_id,...options});
     if(result?.isError)throw Error(result.structuredContent?.error||'WECHAT_AUTHORIZED_DRAFTS_UNVERIFIED');
     const value=content(result);
     if(issued!==authorizedDraftEpoch||row!==current()||wechatPage!=='profile')return;
     const errors={WORKSPACE_AUTH_REQUIRED:'未取得工作区授权',WORKSPACE_ACCESS_DENIED:'本工作区不能读取该号草稿',
       READ_UNAVAILABLE:'扫码授权的草稿服务暂不可用',GRANT_CHANGED:'本号授权已变化，请刷新账号后再试',
       RATE_LIMITED:'读取过于频繁，请稍后重试',WECHAT_READ_UNAVAILABLE:'微信草稿读取失败'};
     if(value.state!=='OBSERVED'){OAUI.set($('wechatAuthorizedDraftsStatus'),errors[value.state]||'草稿读取失败');return;}
     if(action==='read'){
       $('wechatAuthorizedDraftContents').replaceChildren(...value.articles.map(a=>{
         const entry=document.createElement('article'),title=document.createElement('h4'),body=document.createElement('p');
         title.textContent=a.title;body.style.whiteSpace='pre-wrap';body.style.overflowWrap='anywhere';
         const inert=new DOMParser().parseFromString(a.content||a.digest||'','text/html');
         inert.querySelectorAll('script,style,iframe').forEach(n=>n.remove());body.textContent=inert.body.textContent;
         entry.append(title,body);return entry;
       }));
       OAUI.set($('wechatAuthorizedDraftsStatus'),'已读回本号草稿');
       return;
     }
     authorizedDraftNext=value.next_offset;$('wechatAuthorizedDraftsNext').hidden=authorizedDraftNext===null;
     $('wechatAuthorizedDraftContents').replaceChildren();
     $('wechatAuthorizedDraftsRows').replaceChildren(...value.items.map(item=>{
       const li=document.createElement('li'),button=document.createElement('button');
       button.type='button';button.textContent=item.titles.join(' · ');
       button.onclick=()=>void readAuthorizedDrafts('read',{draft_ref:item.draft_ref});li.append(button);return li;
     }));
     OAUI.set($('wechatAuthorizedDraftsStatus'),value.total_count?'本号共有 {0} 组草稿':'微信返回本号草稿箱为空',value.total_count);
   }catch(error){
     if(issued===authorizedDraftEpoch)OAUI.set($('wechatAuthorizedDraftsStatus'),
       String(error?.message).includes('NOT_GRANTED')?'本号未授予素材或草稿权限':'草稿读取失败');
   }finally{
     if(issued===authorizedDraftEpoch){
       authorizedDraftBusy=false;$('wechatAuthorizedDraftsRead').disabled=$('wechatAuthorizedDraftsNext').disabled=false;
     }
   }
 }
 $('wechatAuthorizedDraftsRead').onclick=()=>void readAuthorizedDrafts('list');
 $('wechatAuthorizedDraftsNext').onclick=()=>{if(authorizedDraftNext!==null)void readAuthorizedDrafts('list',{offset:authorizedDraftNext});};
 function paintOfficialProfile(){
   const row=current(),info=row&&official(row),snapshot=row?.official_profile;
   const state=$('wechatOfficialState'),fields=$('wechatOfficialFields'),graphic=$('wechatOfficialGraphic');
   fields.replaceChildren();graphic.replaceChildren();$('wechatStatusAvatar').replaceChildren();
   OAUI.set(state,!row?'先选择一个公众号':({
     ACTIVE:'已取得微信官方资料',SERVICE_NOT_CONFIGURED:'第三方授权服务尚未配置',
     AUTH_REQUIRED:'本号尚未取得第三方授权',REVOKED:'本号已撤销第三方授权',
     STALE:'本号官方资料已过期，等待授权服务同步',UNAVAILABLE:'本号官方资料暂时不可用',
   })[snapshot?.state]||'本号官方资料暂未同步');
   $('wechatProfileRefresh').hidden=true;
   const feedback=$('wechatProfileFeedback');
   if(feedback.dataset.connection!==(row?.connection_id||'')){feedback.textContent='';feedback.dataset.connection=row?.connection_id||'';}
   if(!row)return;
   $('wechatProfileRefresh').hidden=!row.component_grant&&!componentOnly(row);
   const type=info&&[OAUI.format('订阅号'),OAUI.format('订阅号（历史类型）'),OAUI.format('服务号')][info.service_type_id??info.account_type];
   const checked=info?.verify_type_id??info?.verification;
   const verification=Number.isInteger(checked)?OAUI.format(
     ({'-1':'未认证',0:'已微信认证',1:'已微博认证',3:'资质已认证，名称未认证',4:'资质及微博已认证，名称未认证'})[checked]||
       '认证类型 {0}',[checked]):'';
   const grant=row.component_grant,permissions=grant?.state==='ACTIVE'?grant.permissions:info?.permissions;
   const permissionLabels={1:'消息管理',2:'用户管理',3:'账号服务',4:'网页服务',6:'客服管理',7:'群发与通知',11:'素材管理',15:'菜单管理'};
   const checkedAt=info?.identity_verified_at??snapshot?.observed_at;
   const observed=Number.isSafeInteger(checkedAt)?new Date(checkedAt*1000).toLocaleString(document.documentElement.lang):'';
   for(const [label,value] of [
     ['连接方式',OAUI.format(componentOnly(row)?'管理员扫码':grant?'原直连及管理员扫码':'原直连')],
     ['账号状态',OAUI.format(accountState(row))],
     ['权限来源',grant?OAUI.format('微信第三方平台授权回执'):info?OAUI.format('已同步的微信官方资料'):''],
     ['AppID',row.account_id],['官方昵称',info?.nickname],['微信号',info?.alias],
     ...(row.presentation?.name_source==='REGISTRY_LABEL'&&row.presentation.display_name?
       [['本地名称',row.presentation.display_name]]:[]),['账号主体',info?.principal_name],
     ['原始 ID',info?.original_id],['账号类型',type],['微信认证',verification],
     ['已授予的权限集',permissions?.length?permissions.map(id=>
       permissionLabels[id]?OAUI.format(permissionLabels[id])+' ('+id+')':String(id)).join(' · '):
       info?OAUI.format('未返回已授予权限集'):''],
     ...(componentOnly(row)?[['微信凭证状态',({
       CURRENT:OAUI.format('可用'),REQUIRED:OAUI.format('等待官网续期'),
       UNCONFIRMED:OAUI.format('官网续期结果未确认')
     })[info?.refresh_state]]]:[]),
     ['最近同步',observed],
   ]){
     const term=document.createElement('dt'),detail=document.createElement('dd');
     OAUI.set(term,label);
     if(value)OAUI.raw(detail,value);else OAUI.set(detail,'未返回');
     fields.append(term,detail);
   }
   $('wechatStatusAvatar').replaceChildren(avatar(row));
   const qr=profileImage(info?.qrcode,'公众号二维码');
   if(qr){const label=document.createElement('p');OAUI.set(label,'公众号二维码');graphic.append(qr,label);}
 }
 function revealAccountConfiguration(row){
   if(row.platform_id==='wechat_official_account')setWechatPage('settings',{rules:true});
 }
 function paintSelection(){
   clearXRecovery();
   targetAnalytics();
   paintWechatConnection();
   if(isWechat())renderWechatWorkspace();
   paintXConnection();
   if(isWechat()&&wechatPage==='profile')paintOfficialProfile();
   for(const el of accountList.querySelectorAll(':scope > .account')){
     const chosen=el.dataset.accountKey===selected;
     el.classList.toggle('is-selected',chosen);
     el.querySelector('.account-select').setAttribute('aria-current',chosen?'true':'false');
   }
   paintAccountHeader();
   const row=current();
   openAhoyBoard.paintAccountEvidence($('xAccountEvidence'),isXWorkspace()?row:null);
   $('selectedAccount').replaceChildren();
   if(row){const line=document.createElement('p');line.className='account-id';line.textContent=typeof row.account_id==='string'?(platform(row.platform_id)?.account_id_label||'账号标识')+' '+row.account_id:'账号资料暂不可用';$('selectedAccount').append(line);}
   else{const p=document.createElement('p');OAUI.set(p,'选择一个账号，查看所属平台与设置。');$('selectedAccount').append(p);}
   guide?.render();
 }
 function paintWechatConnection(){
   $('wechatAccountMissing').hidden=!(isWechat()&&accountRead&&wechatConnection&&
      !rows.some(row=>row.platform_id===wechatPlatform&&row.connection_id===wechatConnection));
 }
 function paintXConnection(){
   $('xAccountMissing').hidden=!(isXWorkspace()&&accountRead&&xConnection&&
      openAhoyBoard.readState(xPlatform)!=='FAILED'&&
      !rows.some(row=>row.platform_id===xPlatform&&row.connection_id===xConnection));
 }
 function paintAccountHeader(){
   const row=current(),p=platform(activePlatform),label=platformName(activePlatform);
   const title=$('pageTitle'),caption=$('accountCaption');
   caption.hidden=!row;
   $('accountTools').hidden=!row||activePlatform!=='wechat_official_account';
   if(row){
     const display=row.recovery?row.label:name(row);
     if(display)OAUI.raw(title,display);else OAUI.set(title,'账号资料暂不可用');
     const state=row.platform_id===xPlatform?openAhoyBoard.connectionState(row)[0]:accountState(row);
     const parts=[label?OAUI.message(label):p?.name||'',OAUI.message(state)];
     if(row.platform_id==='x'&&row.username)parts.push('@'+row.username);
     OAUI.set(caption,'{0}',parts);
   }else if(label)OAUI.set(title,label);
   else if(p)OAUI.raw(title,p.name);
   else OAUI.set(title,activePlatform?'平台暂不可用':'选择平台');
 }
 async function renderAccounts({preserveSelection=false}={}){
   const visible=rows.filter(row=>row.platform_id===activePlatform&&
     !(isXWorkspace()&&row.connection_id==='x-unavailable'));
   const addWasFocused=document.activeElement===addWechatAccount;
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
   if(isWechat()){
     if(addWechatAccount.parentElement!==accountList)accountList.append(addWechatAccount);
     if(addWasFocused) addWechatAccount.focus({preventScroll:true});
   }else addWechatAccount.remove();
   if(isXWorkspace()&&!visible.length){
     const empty=accountList.querySelector('.empty');
     const state=openAhoyBoard.readState(xPlatform);
     OAUI.set(empty,state==='FAILED'?'账号读取失败':accountRead?'尚未绑定账号':'正在读取账号…');
   }
   $('accountCount').textContent=String(visible.length);
   if(preserveSelection&&pendingSelection?.platform===activePlatform){
     paintSelection();buttons();return;
   }
   const requestedConnection=isWechat()?wechatConnection:isXWorkspace()?xConnection:'';
   if(requestedConnection){
     const requested=visible.find(row=>row.connection_id===requestedConnection);
     const requestedKey=requested?key(requested):'';
     if(!preserveSelection||selected!==requestedKey||!requested){
       await select(requestedKey);
       return;
     }
   }
   if(preserveSelection&&visible.some(row=>key(row)===selected)){
     paintSelection();
     const row=current();
     syncAuthorizedDrafts(isWechat()&&wechatPage==='profile'?row:null);
     if(isWechat()&&wechatPage==='articles')articleReader.target(row);
     if(initializedEditors.has(activePlatform)&&(!componentOnly(row)||row.state==='BOUND_IDLE'))void editors.get(activePlatform)?.loadAccountScope(row.connection_id);
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
   if(isWechat()||isXWorkspace()){
     unmountWorkspacePopover(accountPanel);
     accountPanel.hidden=$('nativeWorkspace').hidden;
     return;
   }
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
   unmountWorkspacePopover(accountPanel);
   if(isWechat()||isXWorkspace()){
     $(isWechat()?'wechatAccountPicker':'xAccountPicker').append(accountPanel);
     platformNavigation.replaceChildren();
     syncAccountNavigation();
     return;
   }
   const ids=[...new Set([...directory.map(p=>p.id),...rows.map(row=>row.platform_id),...(activePlatform?[activePlatform]:[])])].filter(id=>id!=='douyin');
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
       if(!ready||closed)return;
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
   if(!platformNavigation.contains(accountPanel))platformNavigation.append(accountPanel);
   if(!ids.length){const p=document.createElement('p');p.className='help';OAUI.set(p,'暂无可用平台');platformNavigation.append(p);}
   syncAccountNavigation();
 }
 let refreshTask=null;
 function refresh({afterWrite=false}={}){
   if(!ready||closed||launching)return Promise.resolve();
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
   accountRead=false;guide?.render();refreshing=true;buttons();notice('正在读取账号…');openAhoyBoard.loading();
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
     accountRead=true;newsSources.accountsChanged();
     workbench.paintAccounts(rows,directory,value.platform_reads);
     openAhoyBoard.update(directory,rows,value.platform_reads);
     if(directoryChanged){renderPlatforms();if(view==='platform')showSettings(activePlatform);}
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
     if(closed)return;
     openAhoyBoard.failed();
     workbench.accountsUnavailable();
     if(sameView()){
       notice(error.message==='HOST_TIMEOUT'?'账号刷新超时，仍显示上次读取结果。':'账号刷新失败，仍显示上次读取结果。',true);
       OAUI.set($('homeStatus'),'暂时无法读取平台。');
     }
   }
 }
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
 let xToolsOrigin=null;
 $('xWorkspaceTools').onclick=()=>{
   closeXTools();xToolsOrigin=$('xWorkspaceTools');document.body.classList.add('oa-x-tools');$('xWorkspaceBack').focus();
 };
 $('xWorkspaceBilling').onclick=()=>{
   closeXTools();xToolsOrigin=$('xWorkspaceBilling');document.body.classList.add('oa-x-tools','oa-x-billing-view');xManagement.openBilling();
 };
 $('xConnectOwnApplication').onclick=()=>openXDeveloper(current());
 let xDeveloperKey='';
 function closeXTools(){
   xDeveloperKey='';$('xDeveloperSettings').hidden=true;$('xBilling').hidden=true;
   xManagement.closeAuthorization();xToolsOrigin=null;document.body.classList.remove('oa-x-tools','oa-x-developer-open','oa-x-billing-view');
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
   xDeveloperKey=key(row);document.body.classList.add('oa-x-tools','oa-x-developer-open');$('xBilling').hidden=false;
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
 const xBack=document.createElement('button');xBack.id='xWorkspaceBack';OAUI.set(xBack,'返回内容配置');xBack.className='oa-x-tools-back';xBack.onclick=()=>{const origin=xToolsOrigin;closeXTools();(origin||$('xWorkspaceTools')).focus();};$('xSettings').prepend(xBack);
 const xCapabilities=document.createElement('section');xCapabilities.className='oa-capability-details';xCapabilities.append($('xCapabilities'));$('xWorkspaceBack').after(xCapabilities);
 const xRecovery=document.createElement('section');xRecovery.className='oa-capability-details';
 const xRecoveryTitle=document.createElement('h3');xRecoveryTitle.className='oa-content-heading';OAUI.set(xRecoveryTitle,'查询原 X 任务');
 const xRecoveryFields=document.createElement('div');xRecoveryFields.className='oa-x-recovery';
 const xRecoveryKind=document.createElement('select');OAUI.attr(xRecoveryKind,'aria-label','任务类型');
 for(const [value,label] of [['upload','上传'],['post','帖子'],['reply','回复'],['readback','核对原帖']]){
   const option=document.createElement('option');option.value=value;OAUI.set(option,label);xRecoveryKind.append(option);
 }
 const xRecoveryId=document.createElement('input');xRecoveryId.required=true;xRecoveryId.maxLength=128;
 xRecoveryId.pattern='[A-Za-z0-9_\\-]+';OAUI.attr(xRecoveryId,'aria-label','原任务 ID');OAUI.attr(xRecoveryId,'placeholder','原任务 ID');
 const xRecoveryGo=document.createElement('button');xRecoveryGo.type='button';OAUI.set(xRecoveryGo,'查询');
 const xRecoveryResult=document.createElement('output');xRecoveryResult.setAttribute('role','status');
 xRecoveryFields.append(xRecoveryKind,xRecoveryId,xRecoveryGo,xRecoveryResult);
 xRecovery.append(xRecoveryTitle,xRecoveryFields);xCapabilities.after(xRecovery);
 let xRecoveryOwner='';
 function clearXRecovery(){
   const row=activePlatform==='x'?current():null;
   const owner=row?JSON.stringify([row.connection_id,row.account_id,row.binding_revision]):'';
   if(owner===xRecoveryOwner)return;
   xRecoveryOwner=owner;xRecoveryId.value='';OAUI.raw(xRecoveryResult,'');
 }
 xRecoveryGo.onclick=async()=>{
   if(xRecoveryGo.disabled||!xRecoveryId.reportValidity())return;
   const row=current(),origin=platformEpoch,selection=selectEpoch;
   if(activePlatform!=='x'||!row){OAUI.set(xRecoveryResult,'请选择一个已绑定的 X 账号。');return;}
   const kind=xRecoveryKind.value,attempt_id=xRecoveryId.value;
   xRecoveryGo.disabled=true;OAUI.set(xRecoveryResult,'正在查询…');
   try{
     const args={connection_id:row.connection_id,attempt_id};
     const result=await xPanelRead('RECOVERY',{tool:kind==='readback'?'x.posts.readback':'x.attempt.status',
       arguments:kind==='readback'?args:{...args,kind}});
     if(origin===platformEpoch&&selection===selectEpoch&&current()===row){
       const status=[result.state||result.status,result.readback_state,
         result.result?.post_id||result.result?.media_id||result.post_id||result.media_id].filter(Boolean).join(' · ');
       OAUI.raw(xRecoveryResult,status||OAUI.format('已读回原任务。'));
     }
   }catch(problem){
     if(origin===platformEpoch&&selection===selectEpoch&&current()===row)OAUI.raw(xRecoveryResult,problem.message);
   }finally{xRecoveryGo.disabled=false;}
 };
 xRecoveryId.addEventListener('keydown',event=>{
   if(event.key==='Enter'&&!event.isComposing){event.preventDefault();xRecoveryGo.click();}
 });
 $('contextSettingsTab').addEventListener('click',()=>{closeXTools();contextOpen=true;showSettings(activePlatform);xManagement.deactivate();xhsManagement.deactivate();$('xCapabilities').hidden=activePlatform!=='x';projectContext.activate();});
 $('platformSettingsTab').addEventListener('click',()=>{contextOpen=false;projectContext.deactivate();showSettings(activePlatform);if(activePlatform==='x')xManagement.activate();if(activePlatform==='xiaohongshu')xhsManagement.activate();});
 async function openXAuthorization(existing){
   closeXTools();
   contextOpen=false;projectContext.deactivate();showSettings('x');document.body.classList.add('oa-x-tools');
   xManagement.openAuthorization(existing,existing);await xManagement.activate();
 }
 const componentDialog=$('wechatComponentDialog');
 const componentStart=$('wechatComponentStart'),componentCheck=$('wechatComponentCheck');
 const componentCancel=$('wechatComponentCancel');
 let componentTarget=null,profileReturnPage='settings';
 const componentActive=new Set(['STARTING','PENDING','START_UNKNOWN','EXCHANGING','EXCHANGE_UNKNOWN','START_RECOVERY_REQUIRED']);
 let componentBusy=false,componentState='IDLE',componentTrigger=null;
 const componentInfo=key=>OAUI.set($('wechatComponentStatus'),key);
 const paintComponent=()=>{
   componentStart.disabled=componentBusy;
   componentCheck.hidden=false;
   componentCheck.disabled=componentBusy;
   componentCancel.disabled=componentBusy;
   OAUI.set(componentCancel,['STARTING','PENDING'].includes(componentState)?'取消授权':'关闭');
 };
 function closeComponent(){
   if(componentDialog.open)componentDialog.close();
   if(componentTrigger?.isConnected)componentTrigger.focus();
   else if(componentTarget&&isWechat()){
     const account=Array.from(accountList.children).find(el=>el.dataset.accountKey===key({platform_id:wechatPlatform,...componentTarget}));
     (account?.querySelector('summary')||addWechatAccount).focus();
   }
 }
 async function componentAction(operation){
   if(componentBusy)return;
   componentBusy=true;paintComponent();
   try{
     const reply=await tool('wce.ui.wechat.component_binding',{operation,
       ...(componentTarget&&operation!=='WORKSPACE_STATUS'?{connection_id:componentTarget.connection_id}:{})});
     const value=reply?.isError?{status:reply.structuredContent?.error||'WECHAT_COMPONENT_SERVICE_UNAVAILABLE'}:content(reply);
     const previous=componentState;
     componentState=value.status;
     if(['WORKSPACE_CONFLICT','WECHAT_COMPONENT_SERVICE_UNAVAILABLE'].includes(value.status)&&componentActive.has(previous))
       componentState=previous;
     const messages={
       STARTING:'微信正在准备扫码授权。请检查原授权结果。',
       PENDING:'等待公众号管理员扫码。完成后可在这里检查授权结果。',
       EXCHANGING:'微信授权已返回，正在核对公众号资料。',
       START_UNKNOWN:'微信预授权结果未确认，请保留原授权并检查结果。',
       EXCHANGE_UNKNOWN:'微信换码结果未确认。请保留原授权，不另发扫码。',
       START_RECOVERY_REQUIRED:'发起结果尚未收到。再点打开微信扫码会按原请求恢复。',
       CANCELLED:'已取消本次授权。',EXPIRED:'扫码已过期，可以重新发起。',
       REJECTED:'微信授权未获同意，可以重新发起。',REVOKED:'公众号已撤回这次授权。',
       IDLE:'当前没有待检查的扫码。',
       REAUTH_TARGET_UNAVAILABLE:'这个公众号的绑定身份暂不可核对。请刷新账号后重试。',
       REAUTH_INTENT_CONFLICT:'本工作区已有其他扫码请求。请回到发起扫码的账号查看结果。',
       TARGET_UNVERIFIED:'此工作区尚未核实这个公众号的归属。请核对当前工作区和所选公众号后重试。',
       TARGET_BUSY:'微信正在更新这个公众号的授权。请稍后从本号重试。',
       TARGET_STALE:'本号授权已变化，请刷新账号后再试。',
       REAUTH_TARGET_UNCONFIRMED:'微信尚未确认目标公众号。请检查本次授权结果。',
       REAUTH_ACCOUNT_MISMATCH:'扫码结果与所选公众号不符。请使用原公众号的管理员微信重试。',
       WORKSPACE_PROOF_NOT_CONFIGURED:'此工作区尚未建立扫码授权凭据。',
       WORKSPACE_NOT_REGISTERED:'此工作区尚未获准使用公众号扫码服务。',
       WORKSPACE_CONFLICT:'官网已有待处理授权或该公众号已归属另一工作区。请检查原授权。',
       TICKET_OR_COMPONENT_UNAVAILABLE:'公众号扫码暂不可用，官网尚未取得可用微信平台票据或组件凭证。',
       WECHAT_WORKSPACE_KEYCHAIN_UNAVAILABLE:'系统暂时无法读取此工作区的扫码凭据。'
     };
     if(operation==='CANCEL'&&['CANCELLED','IDLE'].includes(value.status)){closeComponent();return;}
     if(value.status==='WORKSPACE_READ'){
       await refresh();
       OAUI.set($('wechatComponentStatus'),'已核对本工作区授权，当前有效公众号 {0} 个。',value.active_count);
       return;
     }
     if(value.status==='BOUND'){
       if(componentTarget&&(componentTarget.account_id!==value.account_id||componentTarget.connection_id!==value.connection_id)){
         componentInfo(messages.REAUTH_ACCOUNT_MISMATCH);return;
       }
       const results=await refresh({afterWrite:true});
       const row=results?.find(item=>item.platform_id===wechatPlatform&&item.account_id===value.account_id&&
         (!componentTarget||item.connection_id===componentTarget.connection_id));
       if(!row||!isWechat()){componentInfo('授权已读回，请刷新账号列表。');return;}
       closeComponent();
       await showWechatStatus(row);
       return;
     }
     componentInfo(value.status==='EXCHANGING'&&value.cancel_requested?'已请求取消，正在核对原扫码结果。请检查本次授权。':
       messages[value.status]||'公众号扫码服务暂时不可用。');
     if(operation==='BEGIN'&&value.status==='PENDING'&&value.authorization_url){
       const url=new URL(value.authorization_url);
       if(url.origin!=='https://www.readysteadysound.com'||url.pathname!=='/jiusera/api/oauth/wechat/authorize'||
         !/^[a-f0-9]{48}$/.test(url.searchParams.get('transaction')||'')||url.hash||
         [...url.searchParams.keys()].length!==1)throw Error('WECHAT_COMPONENT_RESPONSE_INVALID');
       await openXLink(url.href);
     }
   }catch(error){
     componentInfo(componentActive.has(componentState)?'授权仍可检查。若浏览器没有打开，请再次点击打开微信扫码。':
       '公众号扫码服务暂时不可用。');
   }finally{componentBusy=false;paintComponent();}
 }
 componentStart.onclick=()=>void componentAction('BEGIN');
 componentCheck.onclick=()=>void componentAction(!componentTarget&&componentState==='TICKET_OR_COMPONENT_UNAVAILABLE'
   ?'WORKSPACE_STATUS':'STATUS');
 componentCancel.onclick=()=>{if(componentBusy)return;
   if(['STARTING','PENDING'].includes(componentState))void componentAction('CANCEL');else closeComponent();
 };
 componentDialog.addEventListener('cancel',event=>{event.preventDefault();componentCancel.click();});
 async function showWechatStatus(row){
   if(wechatPage!=='profile')profileReturnPage=wechatPage;
   await select(key(row));
   if(!isWechat()||current()?.connection_id!==row.connection_id||current()?.account_id!==row.account_id)return;
   $('wechatProfileFeedback').textContent='';
   wechatConnection=row.connection_id;setWechatPage('profile');$('wechatStatusBack').focus({preventScroll:true});
 }
 async function refreshWechatProfile(){
   const row=current(),trigger=$('wechatProfileRefresh');
   if(!row||trigger.disabled||!isWechat()||wechatPage!=='profile')return;
   const epoch=++profileReadIntent;trigger.disabled=true;
   const visible=()=>epoch===profileReadIntent&&isWechat()&&wechatPage==='profile'&&current()?.connection_id===row.connection_id;
   try{
     const result=await tool('wce.ui.wechat.component_binding',{operation:'PROFILE_STATUS',connection_id:row.connection_id});
     if(!visible())return;
     if(result.isError||content(result).status!=='PROFILE_READ')throw Error();
     await refresh();
     if(visible())OAUI.set($('wechatProfileFeedback'),'已刷新本号官方资料。');
   }catch(_){if(visible())OAUI.set($('wechatProfileFeedback'),'本次未能读取官方资料。请稍后重试。');}
   finally{if(epoch===profileReadIntent)trigger.disabled=false;}
 }
 $('wechatProfileRefresh').onclick=refreshWechatProfile;
 $('wechatStatusBack').onclick=()=>{
   setWechatPage(profileReturnPage);
   accountList.querySelector('.is-selected .account-select')?.focus({preventScroll:true});
 };
 async function openWechatBinding(row=null,trigger=document.activeElement){
   if(!ready||refreshing||componentBusy||componentDialog.open)return;
   componentTarget=row?{connection_id:row.connection_id,account_id:row.account_id}:null;
   componentTrigger=trigger;componentState='IDLE';
   OAUI.set($('wechatComponentTitle'),row?'重新绑定公众号':'绑定公众号');
   const target=$('wechatComponentTarget');
   target.hidden=!row;target.textContent=row?[name(row),row.account_id].filter(Boolean).join(' · '):'';
   componentInfo('');componentDialog.showModal();paintComponent();
   await componentAction('BEGIN');
 }
 async function secure(){
   if(!ready||!bindingPlatform()?.binding_supported)return;
   if(activePlatform==='xiaohongshu'){await xhsManagement.begin();return;}
   if(activePlatform==='x'){await openXAuthorization(false);return;}
   if(activePlatform===wechatPlatform)await openWechatBinding();
 }
 async function manageBoardAccount(id,row,reauthorize=false){
   if(id===douyinPlatform){
     await openView(id,{user:true,focus:true,connection:row?.connection_id||''});
     return;
   }
   if(id===wechatPlatform||id===xPlatform){
     boardEntry={platform:id,connection:row?.connection_id||''};
     await openView(id,{user:true,focus:true,connection:boardEntry.connection});
     if(id===wechatPlatform&&reauthorize&&row&&isWechat()&&current()?.connection_id===row.connection_id)
       await openWechatBinding(current());
     if(id===xPlatform&&reauthorize&&row&&isXWorkspace()&&current()?.connection_id===row.connection_id)
       await openXAuthorization(true);
     return;
   }
   if(!platform(id)?.binding_supported||closed)return;
   await openView(id,{user:true,focus:!row});
   const matches=item=>item&&key(item)===key(row)&&item.account_id===row.account_id&&item.binding_revision===row.binding_revision;
   if(!row||closed||view!=='platform'||activePlatform!==id||!rows.some(matches))return;
   await select(key(row));
   if(closed||activePlatform!==id||!matches(current()))return;
   if(!reauthorize){accountList.querySelector('.is-selected .account-select')?.focus();return;}
   if(id==='x')await openXAuthorization(true);
   else if(id==='xiaohongshu')await xhsManagement.reconnect(row.connection_id);
 }
 const openAhoyBoard=OAOpenAhoyBoard({
   ui:OAUI,wechatName:name,decorate:(node,id,label,presentation)=>OAPlatformBranding.decorate(node,id,label,OAUI,presentation),
   avatar,manage:manageBoardAccount,reload:refresh,openLink:openXLink,
   checkService:async service=>content(await tool('wce.ui.openahoy.mcp.check',{service})),
   
   selectDouyin:connection=>{if(view===douyinPlatform)updateAccountURL(douyinPlatform,connection);},
   handoff:sendChatRequest,
 });
 async function readAnalytics(args){
   const result=await tool('wce.ui.wechat.analytics',args);
   if(result?.isError){
     const code=result.structuredContent?.error||result.content?.[0]?.text;
     throw new Error(typeof code==='string'&&/^[A-Z0-9_]{1,96}$/.test(code)?code:'WECHAT_ANALYTICS_UNAVAILABLE');
   }
   return content(result);
 }
 async function xPanelRead(operation,args){
   const result=await tool('x.ui.action',{operation,arguments:args});
   if(result?.isError){
     const code=result.structuredContent?.error||result.content?.[0]?.text;
     throw new Error(typeof code==='string'&&/^X_[A-Z0-9_]{1,94}$/.test(code)?code:'X_READ_UPSTREAM_UNKNOWN');
   }
   return content(result);
 }
 const analytics=OAWechatAnalytics(readAnalytics,openXLink);
 const workbench=OAWorkbench({open:target=>openView(target,{user:true,focus:true}),
   readAnalytics,readActivity:()=>mediaTool('wce.ui.studio',{action:'home_activity'}),
   openActivity:item=>item.type==='video-request'
     ?openView('jiusera-canvas',{user:true,focus:true,shot:{scope:item.scope}})
     :openView('l-unify',{user:true,focus:true,musicSelection:{project:item.project,song:item.song,version:item.version}}),
   openLink:openXLink,platformName,platformDirectoryIcon:(node,id,label)=>OAPlatformBranding.decorate(node,id,label,OAUI),
   accountName:row=>name(row)||row.label||row.account_id||''});
 const video = OAVideoCredential((name,args)=>mediaTool(name,args),()=>ready&&!closed,paintModelCredential);
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
 let audioMode='',audioModel='';
 const modelDialog=$('wbModelDialog');
 const modelEditors=[...modelDialog.querySelectorAll('[data-model-editor]')];
 const vidmuseModel=OAVidMuse(args=>mediaTool('wce.ui.video.vidmuse',args),openXLink,paintModelCredential);
 function syncModelHint(){
   const mask=modelTiles.get(activeModel)?.querySelector('[data-model-mask]').textContent||'';
   $('wbModelDetailHint').hidden=!mask;
   $('wbModelDetailMask').textContent=mask;
 }
 function paintModelCredential(provider,label,mask='',state=''){
   const tile=modelTiles.get(provider);
   OAUI.set(tile.querySelector('[data-model-status]'),label);
   const value=tile.querySelector('[data-model-mask]');
   value.textContent=mask;
   value.hidden=!mask;
   tile.dataset.state=state;
   if(provider===activeModel)syncModelHint();
 }
 function modelTitle(){
   OAUI.raw($('wbModelDialogTitle'),modelTiles.get(activeModel)?.querySelector('[data-model-name]').textContent||'');
 }
 OAUI.onChange(()=>{if(activeModel)modelTitle();});
 const oauthStatuses=['已连接','未连接','暂时无法读取 Suno 连接。','暂时无法读取 ACE Music 连接。'];
 for(const [provider,id] of [['suno','sunoState'],['ace-music','aceState']]){
   const source=$(id);
   new MutationObserver(()=>{
     if(audioMode!=='models'||audioModel!==provider)return;
     const key=oauthStatuses.find(label=>OAUI.format(label)===source.textContent);
     if(key)OAUI.set(modelTiles.get(provider).querySelector('[data-model-status]'),key);
   }).observe(source,{childList:true,characterData:true,subtree:true});
 }
 function syncModelWorkspace(){
   const showing=view==='models';
   const selected=showing?activeModel:'';
   const group=modelTiles.get(selected)?.dataset.modelGroup;
   $('wbModels').hidden=!showing;
   if(showing)modelLayout.paint(modelDetailTrigger?undefined:selected);
   $('wbAudioWork').hidden=view!=='audio-workspace';
   video.setPage(showing);
   video.selectProvider(selected);
   vidmuseModel.open(selected==='vidmuse');
   for(const [id,pane] of modelSections)pane.hidden=id!==group;
   for(const editor of modelEditors)editor.hidden=editor.dataset.modelEditor!==selected;
   const nextAudio=group==='music'?'models':view==='audio-workspace'?'production':'';
   const nextAudioModel=group==='music'?selected:'';
   if(nextAudio!==audioMode||nextAudioModel!==audioModel){
     if(audioMode)audioWorkspace.close();
     audioMode=nextAudio;
     audioModel=nextAudioModel;
     const surface=$('audioWorkspace');
     surface.hidden=!audioMode;
     surface.dataset.modelDetail=audioModel;
     if(audioMode){
       (audioMode==='models'?modelSections.get('music'):$('wbAudioWorkBody')).append(surface);
       audioWorkspace.open(null,{mode:audioMode,provider:audioModel});
     }
   }
   if(selected){
     modelTitle();
     syncModelHint();
     if(!modelDialog.open){
       modelDialog.showModal();
       $('wbModelDialogTitle').focus({preventScroll:true});
     }
   }else if(modelDialog.open)modelDialog.close();
 }
 function restoreModelFocus(tile){
   const trigger=modelDetailTrigger;
   modelDetailTrigger=null;
   (trigger?.isConnected?trigger:tile)?.focus();
 }
 function closeModelDetail(){
   const tile=modelTiles.get(activeModel);
   if(!tile)return;
   if(history.state?.jiuseraModelDetail===activeModel){history.back();return;}
   activeModel='';
   updateModelsURL(modelGroup,'',{replace:true});
   syncModelWorkspace();
   restoreModelFocus(tile);
 }
 function openModelDetail(provider,trigger){
   if(view!=='models'||activeModel)return;
   modelDetailTrigger=trigger;
   activeModel=provider;
   updateModelsURL(modelGroup,provider,{layer:true});
   syncModelWorkspace();
 }
 $('wbModelClose').onclick=closeModelDetail;
 modelDialog.addEventListener('cancel',event=>{event.preventDefault();closeModelDetail();});
 for(const [provider,tile] of modelTiles)tile.onclick=()=>openModelDetail(provider,tile);
 for(const trigger of $('wbModels').querySelectorAll('[data-promo-provider]'))
   trigger.onclick=()=>openModelDetail(trigger.dataset.promoProvider,trigger);
 for(const link of $('wbModels').querySelectorAll('.wb-model-link,.wb-model-external'))link.addEventListener('click',event=>{
   if(!hostCapabilities.openLinks)return;
   event.preventDefault();
   openXLink(link.href).catch(()=>notice('无法打开官网链接。'));
 });
 const studioEntries=$('jiuseraEntries'), studioParent=$('openMediaStudio'), assetKinds=$('directorAssetKinds');
 const studioSound=OAStudioPreviewSound($('directorSound'));
 let studioExpanded=false,mediaView='',mainStudio='desk',assetKind='';
 const assetRoute=kind=>kind||'jiusera-assets';
 function updateAssetURL(target,project,{push=false}={}){
   try{
     if(!['http:','https:','file:'].includes(location.protocol))return;
     const url=new URL(location.href);
     const old=routeFromURL();
     if(!target&&studioRoutes.get(old)?.section!=='assets')return;
     clearAccountQuery(url);
     if(studioRoutes.get(url.searchParams.get('view'))?.section==='assets')url.searchParams.delete('view');
     if(project!==undefined){if(project)url.searchParams.set('project',project);else url.searchParams.delete('project');}
     url.hash=target?'view='+target:'';
     if(url.href!==location.href)history[push&&old!==target?'pushState':'replaceState'](history.state,'',url);
   }catch(_){}
 }
 const paintAssetKind=kind=>{
   const active=mediaView==='assets';
   assetKind=active?kind:'';
   assetKinds.hidden=!active||!!kind;
   $('directorAssetBack').hidden=!active||!kind;
   $('articleWritingRules').hidden=!active||kind!=='articles';
   $('audioWorkOpen').hidden=!active||kind!=='audio';
   if(active){
     OAUI.set($('directorTitle'),assetLabels[kind]||'资产库');
     $('directorSound').hidden=!['video','audio'].includes(kind);
   }
 };
 const imageAssets=OAImageAssets(mediaTool);
 const newsSources=OASourceLibrary(mediaTool,openXLink,()=>accountRead?rows.filter(row=>row.platform_id===wechatPlatform)
   .map(row=>({id:row.connection_id,label:(name(row)||row.label||row.connection_id)+' · '+row.connection_id.slice(-6)})):null);
 const monitor=OAMediaMonitor((action,args)=>mediaTool('wce.ui.video.workspace',{action,...args}),sendChatRequest,
   {musicCall:mediaTool,musicShot:scope=>enterStudio('desk',{shot:{scope},user:true,focus:true}),sound:studioSound,canAttach:row=>director.canAttach(row),attach:row=>director.attach(row),
    typeChanged:kind=>{if(mediaView==='assets'){paintAssetKind(kind);updateAssetURL(assetRoute(kind));}}});
 const gallery=OAAssetGallery(assetKinds,mediaTool,studioSound);
 function selectStudioProject(project){
   gallery.setProject(project);
   if(!['http:','https:','file:'].includes(location.protocol))return;
   try{
     const url=new URL(location.href);
     if((url.searchParams.get('project')||'')===project)return;
     if(project)url.searchParams.set('project',project);else url.searchParams.delete('project');
     for(const field of ['work','scene','shot','revision','tab'])url.searchParams.delete(field);
     history.replaceState(history.state,'',url);
   }catch(_){}
 }
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
 for(const control of assetKinds.querySelectorAll('[data-asset-kind]'))
   control.onclick=event=>{
     if(event.metaKey||event.ctrlKey||event.shiftKey||event.altKey)return;
     event.preventDefault();
     const kind=control.dataset.assetKind;
     const asset=kind==='articles'?gallery.selectedArticle():null;
     enterStudio('assets',{kind,asset,user:true,focus:true});
     if(asset)$('directorTitle').focus({preventScroll:true});
   };
 $('directorAssetBack').onclick=()=>{
   const wasSources=assetKind==='sources';
   const previous=Array.from(assetKinds.querySelectorAll('[data-asset-kind]'))
     .find(control=>control.dataset.assetKind===assetKind);
   enterStudio('assets',{user:true,focus:true});
   const origin=wasSources?$('wbAssetSources'):previous;
   origin?.focus({preventScroll:true});
 };
 async function openProjectSettings(){
   await openView(activePlatform||'wechat_official_account',{focus:true});
   setWechatPage('settings');
   $('contextSettingsTab').click();
 }
 const characters=OACharacterLibrary(mediaTool,openProjectSettings,sendChatRequest,()=>!!hostCapabilities.message?.text);
 const director=OADirector(mediaTool,sendChatRequest,()=>!!hostCapabilities.message?.text,{
    guideChanged:()=>guide?.render(),imwWork:showIMWWork,
    imwChoose:scope=>{if(imwOn){imwIntent++;imwPending=null;imwTarget=scope;imwKnown=null;imwCurrent='';imwSong=null;updateIMWBinding(null,null,null);}},
    vidmuse:vidmuseModel,
    vidmuseSettings:()=>{openView('models',{user:true,focus:true});openModelDetail('vidmuse');},
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
    project:openProjectSettings,projectSelected:selectStudioProject,openLink:openXLink,
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
   if(imwOn&&!(view==='l-unify'&&section==='monitor'))disableIMW();
   const before=mediaView;
   if(!before&&!section)return;
   if(before!==section){
     navigationEpoch++;
     if(before==='assets'){
       gallery.close();characters.close();monitor.close();imageAssets.close();newsSources.close();$('articleAssetLibrary').hidden=true;
       document.dispatchEvent(new CustomEvent('jiusera:asset-category',{detail:{kind:'',asset:null}}));
     }
     if(before==='tasks')monitor.close();
   }
   mediaView=section;
   $('mediaStudio').hidden=!section||imwOn;
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
 }
 function paintStudioNavigation(){
   studioParent.setAttribute('aria-expanded',String(studioExpanded));
   studioEntries.hidden=!studioExpanded;
   for(const button of studioEntries.querySelectorAll('[data-studio-page]'))
     button.setAttribute('aria-current',mediaView&&mainStudio===button.dataset.studioPage?'page':'false');
 }
 function enterStudio(section,{kind,asset,shot,user=false,focus=false,routeTarget}={}){
   if(closed||!ready)return;
   if(section==='monitor')return openView('l-unify',{imwVideo:true,shot,user,focus});
   if(view!=='studio'){
     platformEpoch++;selectionIntent++;selectEpoch++;
     closeFloatingMenus();notice('');view='studio';
   }
   studioExpanded=true;
   if(section in studioURLs)mainStudio=section;
   if(user){
     explicitNavigation=true;
     if(section==='assets')updateAssetURL(routeTarget||assetRoute(kind),gallery.project(),{push:true});
     else if(section==='desk'||section==='monitor')updateWorkspaceURL(studioURLs[section],shot);
   }
   showMedia(section,{kind,asset,shot});renderView();renderPlatforms();
   if(focus&&!asset)$('directorTitle').focus({preventScroll:true});
 }
 function updateWorkspaceURL(target,shot){
   if((!shot&&routeFromURL()===target)||!['http:','https:','file:'].includes(location.protocol))return;
   try{
     const url=new URL(location.href);
     clearAccountQuery(url);
     const params=new URLSearchParams({view:target});
     if(target==='jiusera-monitor'&&shot?.kind==='mv-work'){
       params.set('project',shot.scope.project_id);
       params.set('work',shot.scope.work_id);
     }
     if(target==='jiusera-canvas'&&shot){
       for(const field of ['project','work','scene','shot','revision'])params.set(field,shot.scope[field+'_id']);
       if(shot.tab)params.set('tab',shot.tab);
     }
     url.hash=params.toString();
     if(url.href!==location.href)history.pushState(history.state,'',url);
   }catch(_){}
 }
 function updateModelsURL(group,provider='',{replace=false,layer=false}={}){
   if(!['http:','https:','file:'].includes(location.protocol))return;
   try{
     const url=new URL(location.href);
     clearAccountQuery(url);
     const fragment=new URLSearchParams({view:'models'});
     if(group)fragment.set('group',group);
     if(provider)fragment.set('provider',provider);
     url.hash=fragment.toString();
     if(url.href!==location.href)
       history[replace?'replaceState':'pushState']({...history.state,jiuseraModelDetail:layer?provider:''},'',url);
   }catch(_){}
 }
 function updateLunifyURL(target,selection,musicProject,musicFeature,video=false,videoScope=null,replace=false){
   if(!['http:','https:','file:'].includes(location.protocol))return;
   try{
     const url=new URL(location.href);
     clearAccountQuery(url);
     if(target!=='l-unify'&&routeFromURL()===target&&!selection&&!musicProject&&!musicFeature)return;
     const fragment=new URLSearchParams({view:target});
     if(target==='l-unify'&&selection){
       for(const field of lunifyFields)if(selection[field])fragment.set(field,selection[field]);
     }
     if(target==='l-unify-songs'&&musicProject)fragment.set('project',musicProject);
     if(target==='l-unify'&&musicFeature)fragment.set('feature',musicFeature);
     if(target==='l-unify'&&(video||videoScope)){
       if(video)fragment.set('video','1');
       if(videoScope?.project_id)fragment.set('project',videoScope.project_id);
       if(videoScope?.work_id)fragment.set('work',videoScope.work_id);
     }
     if(url.hash.slice(1)===fragment.toString())return;
     url.hash=fragment.toString();
     history[replace?'replaceState':'pushState'](history.state,'',url);
   }catch(_){}
 }
 addEventListener('popstate',()=>{
   const launch=launchFromURL();
   const target=launch.target||homeView;
   const section=studioRoutes.get(target)?.section;
   if(section==='assets')gallery.setProject(new URLSearchParams(location.search).get('project')||'');
   void openView(target,{...launch,focus:true});
 });
 function renderView(){
   document.body.classList.toggle('oa-platform-view',view==='platform');
   document.body.classList.toggle('oa-x-workspace',isXWorkspace());
   $('xPlatformBack').hidden=$('xAccountPicker').hidden=!isXWorkspace();
   renderWechatWorkspace();
   syncIntro();
   $('openAhoyHome').hidden=view!=='about';
   syncModelWorkspace();
   $('nativeWorkspace').hidden=view!=='platform';
   const screen=view==='studio'?(mediaView==='desk'?'canvas':mediaView):view;
   const previous=document.body.dataset.workbench;
   if(previous==='l-unify'&&screen!==previous){globalThis.OAIMWVideo?.forgetFolded?.();OAStudio.closeStudio();}
   if(previous!==screen&&['l-unify-home','l-unify-songs'].includes(previous))OAStudio.closeHome(screen);
   workbench.paint(screen,{showCanvas:screen==='canvas'});
   paintStudioNavigation();
   guide?.render();
 }
 const lunifyCall=args=>mediaTool('wce.ui.studio',args);
 const lunifyProductionIntent={
   prepare:'与我沟通这首歌的创作意图，整理制作稿。',
   generate:'为这首歌准备或接续官方 Suno 生成。先读原任务与授权。',
   archive:'查原曲与已授权的音频，按原版本接续归档。',
   stems:'读回并导入这首歌此版本的已有分轨，缺失时说明实际拆分选择。'
 };
 const lunifyId=/^[A-Za-z0-9_][A-Za-z0-9_-]{0,95}$/;
 const lunifyHandoffs=new Map();
 function lunifyCanHandoff(){return ready&&!closed&&!!hostCapabilities.message?.text;}
 function lunifyMVInstruction(selection,receipt){
   const request={project:selection.project,song:selection.song,version:selection.version,
     work_id:receipt.work_id,timeline_version:receipt.timeline_version,source:receipt.source,window:receipt.window};
   return '在当前 Codex 对话继续制作这版歌曲的 MV。使用 $wechat-ecosystem:video-director；L-unify IMW 已经保存剪辑草稿。'+
     '按精确项目与 work_id 读 video.director.read action=timeline，保留手调及已采用的画面、切点和音轨。'+
     '使用 own.music.production 的 lookup 读这版歌词，按选定的歌曲时间窗做分镜并回到同一作品。'+
     '沿当前对话已有授权推进，本按钮未增加付费生成授权。'+
     '\n'+JSON.stringify(request);
 }
 let imwOn=false,imwIntent=0,imwTarget=null,imwCurrent='',imwSong=null,imwKnown=null,imwPending=null;
 const imwSound=$('directorSound'),soundHome=imwSound.parentElement,soundNext=imwSound.nextSibling;
 const imwHistory=new Map();
 let imwLastClosed=null;
 const imwAudioContext=selection=>JSON.stringify(lunifyFields.map(k=>selection?.[k]||''));
 const imwSongKey=selection=>selection&&lunifyFields.every(k=>lunifyId.test(selection[k]||''))?
   JSON.stringify(lunifyFields.map(k=>selection[k])):'';
 const imwScopeKey=scope=>[scope?.project_id,scope?.work_id].every(id=>/^[a-f0-9]{32}$/.test(id||''))?scope.project_id+':'+scope.work_id:'';
 function updateIMWBinding(scope,selection,sha,state){
   const body=document.body.dataset;
   for(const key of ['imwProject','imwWork','imwSong','imwSongVersion','imwMusicSha','imwBindingState'])delete body[key];
   if(state)body.imwBindingState=state;
   if(scope?.project_id)body.imwProject=scope.project_id;
   if(scope?.work_id)body.imwWork=scope.work_id;
   if(selection&&imwSongKey(selection)&&selection.project===scope?.project_id){
     body.imwSong=selection.song;body.imwSongVersion=selection.version;
     if(/^[a-f0-9]{64}$/.test(sha||''))body.imwMusicSha=sha;
   }
   document.dispatchEvent(new CustomEvent('jiusera:imw-binding'));
 }
 function setIMWOpening(opening){
   const studio=$('wbMusic').querySelector('lus-studio');
   if(studio&&opening!==studio.hasAttribute('data-imw-opening')){
     const animate=!imwOn&&opening;
     const from=animate?studio.disclosure.takeHeight():0;
     studio.toggleAttribute('data-imw-opening',opening);
     if(animate)void studio.disclosure.reveal(from);
   }
   $('imw-video-toggle')?.setAttribute('aria-expanded',String(opening||imwOn));
 }
 function expandIMW(shot,binding){
   if(view!=='l-unify')return;
   enableIMW(shot,binding);
   updateLunifyURL('l-unify',binding?.selection,null,null,true,shot?.scope,true);
 }
 function disableIMW(){
   imwIntent++;imwPending=null;
   $('wbMusic').querySelector('lus-studio')?.disclosure?.reset();
   setIMWOpening(false);
   if(!imwOn)return;
   OAStudio.setVideoMode(false);
   imwOn=false;imwCurrent='';imwTarget=null;imwKnown=null;imwSong=null;
   delete document.body.dataset.imwVideo;
   updateIMWBinding(null,null,null);
   soundHome.insertBefore(imwSound,soundNext);
 }
 function showIMWWork(project,work){
   if(!imwOn||view!=='l-unify')return;
   if(!work||work.inbox||work.kind==='article'){
     if(project&&!imwTarget)OAStudio.setVideoProject(project,null);
     if(imwCurrent){imwCurrent='';imwSong=null;updateIMWBinding(null,null,null);}
     return;
   }
   const scope={project_id:project,work_id:work.id},key=imwScopeKey(scope);
   if(imwTarget&&(imwTarget.project_id!==project||imwTarget.work_id&&imwTarget.work_id!==work.id))return;
   if(key===imwCurrent)return;
   imwTarget=null;imwCurrent=key;
   const known=imwKnown&&imwScopeKey(imwKnown.scope)===key?imwKnown:null;
   imwSong=known?.selection||null;
   OAStudio.setVideoProject(project,imwSong);
   updateIMWBinding(scope,imwSong,known?.sha,known?.sha?null:'pending');
   imwHistory.set(imwSongKey(imwSong)||project,scope);imwHistory.set('video',scope);
   updateLunifyURL('l-unify',imwSong,null,null,true,scope,true);
   if(known?.sha)return;
   const intent=imwIntent;
   // Resolve the take inside the open project. Only the original bound take inherits a score window.
   const current=()=>imwOn&&intent===imwIntent&&imwCurrent===key;
   void (async()=>{
     const binding=await lunifyCall({action:'mv_binding',project,work_id:work.id});
     if(!current())return;
     if(binding.project!==project||binding.work_id!==work.id)throw Error('IMW_BINDING_CHANGED');
     const linked=binding.bound?{project,song:binding.song,version:binding.version}:null;
     const studio=$('wbMusic').querySelector('lus-studio');
     const selection=known?.selection||linked||await studio?.imwProjectSelection(project);
     if(!current())return;
     if(!selection){updateIMWBinding(scope,null,null);return;}
     if(!imwSongKey(selection)||selection.project!==project)throw Error('IMW_BINDING_CHANGED');
     const sha=linked&&imwSongKey(linked)===imwSongKey(selection)?binding.source?.sha256:null;
     imwSong=selection;imwKnown={scope,selection,sha};
     OAStudio.setVideoProject(project,selection);updateIMWBinding(scope,selection,sha);
     imwHistory.set(imwSongKey(selection),scope);
     OAStudio.open($('wbMusic'),lunifyCall,selection);
     updateLunifyURL('l-unify',selection,null,null,true,scope,true);
   })().catch(problem=>{
     if(current()){updateIMWBinding(scope,null,null,'error');notice(problem.message,true);}
   });
 }
 function enableIMW(shot,binding){
   globalThis.OAIMWVideo?.forgetFolded?.();
   imwLastClosed=null;imwOn=true;mainStudio='monitor';imwCurrent='';imwTarget=shot?.scope||null;
   imwKnown=binding||null;imwSong=binding?.selection||null;
   document.body.dataset.imwVideo='true';
   updateIMWBinding(null,null,null,'pending');
   if(imwTarget?.project_id)OAStudio.setVideoProject(imwTarget.project_id,imwSong);
   OAStudio.setVideoMode(true);
   $('daWork').before(imwSound);
   if(mediaView==='monitor'&&shot){
     director.close();mediaView='';
   }
   showMedia('monitor',{shot});
 }
 async function openLunifyMV(receipt,selection){
   const scope={project_id:receipt.project_id,work_id:receipt.work_id};
   if(!imwSongKey(selection)||selection.project!==scope.project_id||!imwScopeKey(scope))return;
   return openView('l-unify',{user:true,focus:true,imwVideo:true,musicSelection:selection,
     shot:{kind:'mv-work',scope},imwBinding:{scope,selection,sha:receipt.source?.sha256}});
 }
 async function toggleIMW(enabled,selection,remember=true){
   if(view!=='l-unify')return;
   const editor=$('wbMusic').querySelector('lus-studio');
   if(!editor)return;
   if(enabled&&editor.disclosure.reversing()){
     ++imwIntent;
     const height=editor.disclosure.takeHeight();
     if(imwOn){
       void editor.disclosure.reveal(height);
       $('imw-video-toggle').setAttribute('aria-expanded','true');
       return;
     }
     imwPending=null;setIMWOpening(false);
   }
   if(!enabled){
     const requestedScope=imwTarget;
     const intent=++imwIntent;
     if(imwOn||editor.hasAttribute('data-imw-opening')){
       globalThis.OAIMWVideo?.pause?.();
       $('imw-video-toggle').setAttribute('aria-expanded','false');
       if(!await editor.disclosure.collapse()||intent!==imwIntent||view!=='l-unify')return;
     }
     editor.disclosure.reset();
     const {imwProject:project_id,imwWork:work_id}=document.body.dataset;
     const scope=imwScopeKey({project_id,work_id})?{project_id,work_id}:requestedScope;
     imwLastClosed=remember&&imwScopeKey(scope)?{audio:imwAudioContext(selection),scope}:null;
     globalThis.OAIMWVideo?.retainFolded?.(remember?scope:null,selection);
     const foldedScope=remember&&scope&&globalThis.OAIMWVideo?.detachedAudio?.()?.rows?.length?scope:null;
     disableIMW();showMedia('');updateLunifyURL('l-unify',selection,null,null,false,foldedScope,true);return;
   }
   const key=imwSongKey(selection),project=selection?.project;
   const remembered=imwLastClosed?.audio===imwAudioContext(selection)?
     imwLastClosed.scope:imwHistory.get(key||project||'video');
   imwLastClosed=null;
   if(remembered)return expandIMW({kind:'mv-work',scope:remembered},
     key&&selection.project===remembered.project_id?{scope:remembered,selection}:null);
   if(!key)return expandIMW(/^[a-f0-9]{32}$/.test(project||'')?{kind:'imw-project',scope:{project_id:project}}:undefined);
   if(imwPending===key)return;
   const intent=++imwIntent;imwPending=key;setIMWOpening(true);
   try{
     const receipt=await lunifyCall({action:'start_mv',...selection,window:'whole_song'});
     const studio=$('wbMusic').querySelector('lus-studio');
     const current=studio&&{project:studio.project?.id,song:studio.song?.id,version:studio.version?.id};
     if(intent===imwIntent&&view==='l-unify'&&imwSongKey(current)===key){
       const scope={project_id:receipt.project_id,work_id:receipt.work_id};
       if(scope.project_id===project&&imwScopeKey(scope))
         expandIMW({kind:'mv-work',scope},{scope,selection,sha:receipt.source?.sha256});
     }
   }catch(problem){
     if(intent!==imwIntent||view!=='l-unify')return;
     if(['music_mv_full_mix_required','music_mv_compatible_mix_required','music_mv_audio_unavailable'].includes(problem.message))
       expandIMW({kind:'imw-project',scope:{project_id:selection.project}});
     else notice(problem.message,true);
   }finally{if(intent===imwIntent){imwPending=null;setIMWOpening(false);}}
 }
 document.addEventListener('jiusera:imw-video-toggle',event=>void toggleIMW(event.detail.enabled,event.detail.selection));
 document.addEventListener('jiusera:imw-selection-changed',event=>{
   if(!imwOn||imwSongKey(imwSong)===imwSongKey(event.detail))return;
   void toggleIMW(false,event.detail,false);
 });
 function lunifyProductionRequest(action,selection){
   if(!lunifyCanHandoff())return Promise.reject(new Error('HOST_MESSAGE_UNAVAILABLE'));
   if(!Object.hasOwn(lunifyProductionIntent,action)||!selection||
      !lunifyFields.every(field=>typeof selection[field]==='string'&&lunifyId.test(selection[field])))
     return Promise.reject(new Error('LUNIFY_SELECTION_INVALID'));
   const scope=Object.fromEntries(lunifyFields.map(field=>[field,selection[field]]));
   const request=JSON.stringify({action,...scope});
   if(lunifyHandoffs.has(request))return lunifyHandoffs.get(request);
   const text='使用 Jiusera 的 $wechat-ecosystem:lunify-music-production。'+lunifyProductionIntent[action]+
     '\n按下列 L-unify 目标读回真实歌卡和原任务，保留原词。任何需要扣额度的动作按我在聊天中给出的授权处理。'+
     '\n'+request;
   const sent=sendChatRequest(text).finally(()=>lunifyHandoffs.delete(request));
   lunifyHandoffs.set(request,sent);
   return sent;
 }
 const lunifyNavigation={
   canStartProduction:lunifyCanHandoff,
   mvInstruction:lunifyMVInstruction,
   openMV:openLunifyMV,
   sendMV:sendChatRequest,
   startProduction:lunifyProductionRequest,
   openHome:()=>openView('l-unify-home',{user:true,focus:true}),
   openSongs:musicProject=>openView('l-unify-songs',{user:true,focus:true,musicProject}),
   openStudio:(musicSelection,musicFeature)=>openView('l-unify',{user:true,focus:true,musicSelection,musicFeature}),
   openAssets:()=>openView('audio',{user:true,focus:true})
 };
 async function openView(target,{user=false,focus=false,shot,connection='',page,modelSection,modelProvider,musicSelection,musicProject,musicFeature,imwVideo=false,imwBinding,foldedScope}={}){
   if(target==='jiusera-monitor'||target==='media'){target='l-unify';imwVideo=true;}
   imwIntent++;imwPending=null;setIMWOpening(false);
   closeFloatingMenus();
   if(closed||!ready)return;
   const previousModel=view==='models'?activeModel:'';
   const wasWechat=isWechat();
   const wasX=isXWorkspace();
   const douyinReturn=view===douyinPlatform&&target==='openahoy'?launchFromURL():null;
   if(user&&target==='l-unify'&&view==='l-unify-songs'&&!musicSelection)
     musicSelection=OAStudio.homeSelection()||undefined;
   if(user&&lunifyRoutes.has(target))updateLunifyURL(target,musicSelection,musicProject,musicFeature,imwVideo,shot?.scope);
   if(target==='music-recipes'){
     enterStudio('assets',{kind:'audio',user,focus,routeTarget:target});
     void monitor.openRecipes(focus);
     return;
   }
   if(studioRoutes.has(target)){
     const {section,kind}=studioRoutes.get(target);
     enterStudio(section,{kind,user,focus,shot});
     return;
   }
   if(activePlatform!==target||view!=='platform')notice('');
   if(user)explicitNavigation=true;
   if(['about','models','audio-workspace','published','openahoy','profile',douyinPlatform].includes(target)||lunifyRoutes.has(target)){
     if(target==='models'){
       modelGroup=modelGroupOf(modelSection);
       activeModel=modelId(modelProvider);
       if(user)updateModelsURL(modelGroup,activeModel);
     }else if(user&&target===douyinPlatform)updateAccountURL(target,connection,undefined,{push:view!==target});
     else if(user&&!lunifyRoutes.has(target))updateWorkspaceURL(target);
     platformEpoch++;selectionIntent++;selectEpoch++;navigationEpoch++;
     closeXTools();xManagement.deactivate();xhsManagement.deactivate();projectContext.deactivate();
     view=target;
     if(!imwVideo||target!=='l-unify')showMedia('');
     else if(mediaView&&mediaView!=='monitor')showMedia('');
     renderView();renderPlatforms();
     if(target===douyinPlatform)openAhoyBoard.showDouyin(connection);
     if(target==='l-unify-home')OAStudio.openHome($('wbMusicHome'),lunifyCall,lunifyNavigation);
     if(target==='l-unify-songs')OAStudio.openSongs($('wbMusicSongs'),lunifyCall,lunifyNavigation,musicProject);
     if(target==='l-unify'){
       OAStudio.open($('wbMusic'),lunifyCall,musicSelection,musicFeature);
       if(imwVideo)enableIMW(shot,imwBinding||(imwSongKey(musicSelection)&&musicSelection.project===shot?.scope?.project_id?
         {scope:shot.scope,selection:musicSelection}:null));
       else if(foldedScope&&musicSelection?.project===foldedScope.project_id){
         const intent=imwIntent,epoch=navigationEpoch;
         const current=()=>view==='l-unify'&&!imwOn&&intent===imwIntent&&epoch===navigationEpoch;
         imwLastClosed={audio:imwAudioContext(musicSelection),scope:foldedScope};
         void lunifyCall({action:'mv_binding',project:foldedScope.project_id,work_id:foldedScope.work_id}).then(binding=>
           globalThis.OAIMWVideo?.restoreFolded?.(foldedScope,musicSelection,binding,current)
         ).catch(problem=>{if(current())notice(problem.message,true);});
       }
     }
     if(target==='models'&&!activeModel&&(focus||modelGroup||previousModel)){
       const tile=modelTiles.get(previousModel)||[...modelTiles.values()].find(card=>card.dataset.modelGroup===modelGroup);
       restoreModelFocus(tile||$('wbModelsTitle'));
     }else if(target!=='models')modelDetailTrigger=null;
     if(focus&&target!=='models')$({about:'homeTitle','audio-workspace':'wbAudioWorkTitle',published:'wbPublishedTitle',openahoy:'wbOpenAhoyTitle',profile:'wbProfileTitle',douyin:'wbDouyinTitle',
       'l-unify-home':'wbMusicHomeTitle','l-unify-songs':'wbMusicSongsTitle','l-unify':'wbMusicTitle'}[target])?.focus();
     if(focus&&douyinReturn)openAhoyBoard.focusAccount(douyinPlatform,douyinReturn.connection);
     return;
   }
   if(view==='platform'&&activePlatform===target&&!(wasWechat&&(connection||page))&&!(wasX&&connection!==xConnection))return;
   view='platform';
   if(user){
     if(target===wechatPlatform||target===xPlatform)updateAccountURL(target,connection,page,{push:!(wasWechat||wasX)||activePlatform!==target});
     else updateWorkspaceURL(target);
   }
   await selectPlatform(target,{focus,user,connection,page});
 }
 async function returnToBoard(){
   const launch=launchFromURL();
   const origin=boardEntry?.platform===activePlatform?boardEntry:{platform:activePlatform,connection:launch.connection};
   boardEntry=null;
   await openView('openahoy',{user:true,focus:true});
   if(view==='openahoy')openAhoyBoard.focusAccount(origin.platform,origin.connection);
 }
 $('wechatBack').onclick=$('xPlatformBack').onclick=returnToBoard;
 guide=OAWorkflowGuide({
   status(){
     const row=accountRead&&view==='platform'&&current();
     return {work:(view==='studio'||imwOn)?director.guideContext():null,platform:view==='platform'?activePlatform:'',
       account:row?{id:row.connection_id,label:name(row)||row.label||row.account_id||'',state:accountState(row)}:null};
   },
   async locate(target,step,currentRequest,scope,tab='text'){
     if(!ready||closed||(step===4&&!platform(target)))return false;
     await openView(target,{user:true});
     if(!currentRequest()||closed)return false;
     let control;
     if(step===4){
       if(view!=='platform'||activePlatform!==target)return false;
       accountsExpanded=true;syncAccountNavigation();revealSelectedAccount();
       control=accountList.querySelector('.is-selected .account-select')||platformButton();
     }else{
       if((view!=='studio'&&!imwOn)||mediaView!==studioRoutes.get(target).section)return false;
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
 addWechatAccount.type='button';
 addWechatAccount.className='oa-wechat-add-account';
 const addWechatIcon=document.createElement('span'),addWechatLabel=document.createElement('span');
 addWechatIcon.textContent='＋';addWechatIcon.setAttribute('aria-hidden','true');
 OAUI.set(addWechatLabel,'添加公众号');addWechatAccount.append(addWechatIcon,addWechatLabel);
 addWechatAccount.addEventListener('click',secure);
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
 $('accountImport').addEventListener('click',()=>{$('accountCreate').click();});
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
   hostCapabilities=host.hostCapabilities;ready=true;OAWorkspaceTheme.host(host.hostContext);projectContext.setReady(true,!!hostCapabilities.message?.text);bridge.postMessage({jsonrpc:'2.0',method:'ui/notifications/initialized'},'*');
   const launch=addressLaunch.target?addressLaunch:hostLaunch;
   void openView(launch?.target||homeView,launch||{});
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
    from .button_feedback import STYLE as pressure_style, SCRIPT as pressure_script
    from .management_interactions import STYLE as interaction_style, SCRIPT as interaction_script
    from .workflow_guide_ui import STYLE as guide_style, SCRIPT as guide_script
    from .workbench_ui import STYLE as workbench_style, SCRIPT as workbench_script, relief_style, trend_resource
    from .openahoy_board_ui import STYLE as openahoy_board_style, SCRIPT as openahoy_board_script
    from .studio_ui import resource as studio_resource
    from .writing_workflow_ui import SCRIPT as writing_rules_script
    from .own_wechat_management import settings_html, settings_script
    from .video_inline_ui import SCRIPT as video_script
    from .audio_workspace_ui import STYLE as audio_style, SCRIPT as audio_script
    from .wechat_analytics_ui import STYLE as stats_style, SCRIPT as stats_script
    from .wechat_workspace_ui import STYLE as wechat_workspace_style
    from .wechat_setup_home import STYLE as wechat_setup_style
    from .wechat_setup_preview import STYLE as wechat_setup_preview_style
    from .wechat_article_page import STYLE as wechat_articles_style, SCRIPT as wechat_articles_script
    from .wechat_account_desk import STYLE as wechat_desk_style, SCRIPT as wechat_desk_script
    from .video_provider_ui import STYLE as provider_style, SCRIPT as provider_script
    from .openai_gif_ui import STYLE as gif_style
    from .video_workspace_ui import STYLE as video_style
    from .media_monitor_ui import STYLE as monitor_style, SCRIPT as monitor_script
    from .video_director_canvas_ui import STYLE as canvas_style, SCRIPT as canvas_script
    from .video_director_ui import STYLE as director_style, SCRIPT as director_script
    from .video_vidmuse_ui import SCRIPT as vidmuse_script
    from .model_overview_layout import STYLE as model_layout_style, SCRIPT as model_layout_script
    from .video_director_monitor_ui import STYLE as review_style, SCRIPT as review_script
    review_style = review_style.replace('#videoDirectorDesk', ':is(#videoDirectorDesk,#wbMusic lus-studio[data-imw-video])')
    from .character_library_ui import STYLE as characters_style, SCRIPT as characters_script
    from .character_turntable_ui import SCRIPT as character_turntable_script
    from .asset_catalog_ui import STYLE as assets_style, SCRIPT as assets_script
    from .model_overview_ui import image_source
    offline_disk = image_source('management/asset-disk-offline.webp')
    assets_style += f'\n#directorAssetKinds{{--jiu-asset-offline-art:url("{offline_disk}");}}'
    from .source_library_ui import STYLE as sources_style, SCRIPT as sources_script
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
        + '<style>' + studio_resource('css') + font_style() + NATIVE_FINISH_STYLE + video_style + provider_style + audio_style + stats_style + gif_style + HOME_STYLE + frame_style + monitor_style + director_style + review_style + characters_style + canvas_style + interaction_style + wechat_workspace_style + wechat_setup_style + wechat_setup_preview_style + wechat_articles_style + PLATFORM_ACCOUNT_NAV_STYLE + guide_style + workbench_style + openahoy_board_style + assets_style + sources_style + trend_resource('css') + relief_style() + model_layout_style + '</style>'
        + mark_chrome(native_page_body(LOGO, settings_html(templates=True) + x_html + xhs_html + project_html))
        + '<style>' + wechat_desk_style + pressure_style + '</style>'
        + '<script>' + pressure_script + WORKSPACE_THEME + locale_script() + platform_branding_script() + settings_script(compact=True) + wechat_articles_script + wechat_desk_script + video_script + frame_script + provider_script + vidmuse_script + audio_script + stats_script + monitor_script + canvas_script + review_script + director_script + character_turntable_script + characters_script + assets_script + sources_script + x_script + xhs_script + schedule_script + operating_script + project_script + interaction_script + guide_script + trend_resource('js') + workbench_script + openahoy_board_script + writing_rules_script + studio_resource('js') + model_layout_script + SCRIPT + '</script></body></html>')
    return {'contents': [{'uri': RESOURCE, 'mimeType': MIME, 'text': html,
        '_meta': {'ui': {'csp': {'connectDomains': [], 'resourceDomains': ['https://pbs.twimg.com', 'https://wx.qlogo.cn', 'https://thirdwx.qlogo.cn', 'https://mmbiz.qpic.cn', 'https://mmbiz.qlogo.cn', 'https://cdn1.suno.ai',
                                                                 'https://cdn2.suno.ai', 'https://suno-data-uploads.s3.amazonaws.com', 'https://acemusic.ai'], 'frameDomains': []}},
                  'openai/ui': {'availableDisplayModes': ['inline', 'fullscreen'], 'preferredDisplayMode': 'inline'}}}]}


class NativeManagement:
    def resource(self):
        return resource()

    def close(self):
        pass  # The native view owns no HTTP listener or account session.
