"""Small optional update strip sharing the existing native MCP Apps RPC."""
from copy import deepcopy
import json

from .contracts import WCEError
from .management_locale import FALLBACK, mark_chrome

STYLE = """
#softwareUpdateSlot:empty{display:none}
#wbHomeUpdateStatus{position:absolute;width:1px;height:1px;overflow:hidden;clip-path:inset(50%);white-space:nowrap;pointer-events:none}
body.oa-management.oa-native[data-workbench] .wb-dock>#wbHomeUpdate[data-update]{
 --update-signal:light-dark(#384954,#445661);--update-halo:transparent;
 position:relative;color:white;background:var(--update-signal);
 box-shadow:inset 0 1px 1px #ffffff35,0 2px 4px #0003;
 opacity:1;isolation:isolate;
}
body.oa-management.oa-native[data-workbench] .wb-dock>#wbHomeUpdate[data-update=available]{
 --update-signal:#177750;--update-halo:#359d7365;
}
body.oa-management.oa-native[data-workbench] .wb-dock>#wbHomeUpdate[data-update=restart]{
 --update-signal:#ac2b40;--update-halo:#d34b6365;
}
body.oa-management.oa-native[data-workbench] .wb-dock>#wbHomeUpdate:is([data-update=error],[data-update=recovery]){
 --update-signal:#8a4d18;
}
body.oa-management.oa-native[data-workbench] .wb-dock>#wbHomeUpdate:not([aria-disabled=true]):hover{filter:brightness(1.12)}
#wbHomeUpdate:is([data-update=available],[data-update=restart])::before{
 content:"";position:absolute;inset:-3px;border-radius:inherit;border:2px solid var(--update-halo);
 pointer-events:none;animation:oa-update-halo 2.8s ease-in-out infinite;
}
@keyframes oa-update-halo{0%,100%{opacity:.3;scale:1}50%{opacity:1;scale:1.10}}
@keyframes oa-update-turn{to{rotate:360deg}}
@keyframes oa-update-pulse{50%{opacity:.60;scale:.88}}
.wb-update-face{display:grid;place-items:center;font-size:11px;font-weight:750;font-variant-numeric:tabular-nums;line-height:1}
.wb-update-face svg{display:block;width:17px;height:17px}
#wbHomeUpdate:is([data-update=checking],[data-update=downloading],[data-update=installing]) svg{
 animation:oa-update-turn 1.5s linear infinite
}
#wbHomeUpdate:is([data-update=verifying],[data-update=staged],[data-update=waiting]) svg{
 animation:oa-update-pulse 1.6s ease-in-out infinite
}
@media(prefers-reduced-motion:reduce){
 #wbHomeUpdate::before,#wbHomeUpdate .wb-update-face svg{animation:none!important}
}
.oa-update-versions{margin:0;display:grid;gap:3px;font-variant-numeric:tabular-nums}
.oa-update-versions div{display:flex;flex-wrap:wrap;justify-content:space-between;gap:1px 8px}
.oa-update-versions [hidden]{display:none}
.oa-update-versions dt{color:var(--muted)}.oa-update-versions dd{margin:0;font-weight:650;overflow-wrap:anywhere}
.oa-update-status,.oa-update-job,.oa-update-restart-help{margin:0;overflow-wrap:anywhere}
.oa-update-job:empty,.oa-update-check-detail:empty,.oa-update-job-detail:empty{display:none}
.oa-software-update[data-discovery=UPDATE_AVAILABLE] .oa-update-status{color:light-dark(#096642,#a1ebc5);font-weight:650}
#wbUpdateFeedback[hidden]{display:none}
#wbUpdateFeedback{
 position:absolute;z-index:2;inset:auto 0 calc(100% + 9px) auto;
 box-sizing:border-box;width:min(320px,100%);padding:12px;border:1px solid var(--wb-line);border-radius:14px;
 color:var(--wb-ink);background:var(--wb-panel);box-shadow:var(--wb-dock-float);font-size:13px;
}
.oa-update-feedback-head,.oa-update-feedback-actions{display:flex;align-items:center;gap:7px;flex-wrap:wrap}
.oa-update-feedback-head{justify-content:space-between;margin-bottom:5px}
.oa-update-feedback-actions{margin-top:8px}
.oa-update-feedback-actions:has(>button[hidden] + button[hidden]){display:none}
.oa-update-feedback-head button,.oa-update-feedback-actions button{min-height:32px;padding:4px 9px;}
.oa-update-feedback-head .oa-update-close{min-width:32px}
.oa-update-restart-help,.oa-update-technical,.oa-update-history{margin-top:5px;color:var(--muted)}
.oa-update-history summary,.oa-update-technical summary{cursor:pointer}
.oa-update-technical p{margin:3px 0;overflow-wrap:anywhere}
#wbUpdateFeedback [hidden]{display:none}
"""

UPDATE_HTML = """
<div class="oa-update-version-header">
 <strong class="oa-update-version">当前版本</strong>
 <button type="button" class="oa-update-check" disabled>检查更新</button>
</div>
<dl class="oa-update-versions">
 <div><dt>当前运行</dt><dd class="oa-update-running"></dd></div>
 <div class="oa-update-installed-row" hidden><dt>已安装</dt><dd></dd></div>
 <div><dt>最新稳定版</dt><dd class="oa-update-latest"></dd></div>
</dl>
<p class="oa-update-status" role="status">正在连接更新检查…</p>
<details class="oa-update-history" hidden><summary>更新历史</summary><span></span></details>
"""

FEEDBACK_HTML = """
<div class="oa-update-feedback-head">
 <strong class="oa-update-heading"></strong>
 <button type="button" class="oa-update-close" aria-label="关闭更新提示">×</button>
</div>
<p class="oa-update-job"></p>
<p class="oa-update-restart-help" hidden>结束当前任务后，退出并重新打开 Codex。</p>
<details class="oa-update-technical" hidden><summary>技术详情</summary><p class="oa-update-check-detail" hidden></p><p class="oa-update-job-detail" hidden></p></details>
<div class="oa-update-feedback-actions">
 <button type="button" class="oa-update-operation" hidden></button>
 <button type="button" class="oa-update-help" hidden>查看升级与恢复方法</button>
</div>
"""

SCRIPT = FALLBACK + r'''
window.OASoftwareUpdates={mount(rpc,installed){
 'use strict';
 const ui=globalThis.OAUI||globalThis.OAPlainUI;
 const repository='OpenAhoy/OpenAhoy-Releases',versionPattern=/^(0|[1-9][0-9]{0,8})\.(0|[1-9][0-9]{0,8})\.(0|[1-9][0-9]{0,8})$/;
 const box=document.createElement('section');box.className='oa-software-update';ui.attr(box,'aria-label','Jiusera 软件更新');box.dataset.state='NOT_CHECKED';
 box.innerHTML=__UPDATE_HTML__;
 const slot=document.getElementById('softwareUpdateSlot');if(!slot)throw new Error('UPDATE_VIEW_UNAVAILABLE');slot.append(box);ui.scan?.(box);
 const node=suffix=>box.querySelector('.oa-update-'+suffix);
 const status=node('status'),checkButton=node('check');
 const stable=node('latest'),installedRow=node('installed-row');
 const home=document.getElementById('wbHomeUpdate'),homeStatus=document.getElementById('wbHomeUpdateStatus');
 const face=home?.querySelector('.wb-update-face');
 const feedback=document.createElement('section');feedback.id='wbUpdateFeedback';feedback.hidden=true;
 ui.attr(feedback,'aria-label','设置更新详情');
 feedback.innerHTML=__FEEDBACK_HTML__;
 (home?.closest('.wb-dock')?.parentElement||slot).append(feedback);ui.scan?.(feedback);
 const report=suffix=>feedback.querySelector('.oa-update-'+suffix);
 const heading=report('heading'),jobStatus=report('job'),restartHelp=report('restart-help');
 const operation=report('operation'),helpButton=report('help'),history=node('history'),close=report('close');
 const technical=report('technical'),checkDetail=report('check-detail'),jobDetail=report('job-detail');
 box.classList.add('wb-setting-version');
 ui.set(stable,'待检查');
 ui.raw(node('running'),installed);
 const pendingKey='OpenAhoy.softwareUpdate.pending.'+installed;
 const discoveryKey='Jiusera.softwareUpdate.discovery.'+installed;
 const requestPattern=/^[0-9a-f]{32}$/;
 const recheckAfter=30*60*1000;
 let ready=false,closed=false,checking=false,starting=false,reading=false,latest=null,job='STATUS_UNAVAILABLE',pollTimer;
 let pendingRequest=null,canOpenLinks=false,blurred=false,lastCheckAt=null,lastStable=null,automatic=false;
 let jobHelp=false,readJob=false,stableCheckedAt=0,percent=null,manualCheck=false;
 let feedbackAction=null,jobMessage=null,checkMessage=null;
 try{
  const stored=sessionStorage.getItem(pendingKey);
  if(requestPattern.test(stored))pendingRequest=stored;
 }catch(_){}
 const active=new Set(['CHECKING','DOWNLOADING','VERIFYING','STAGED','WAITING_FOR_IDLE','INSTALLING']);
 const terminal=new Set(['INSTALLED_RELOAD_REQUIRED','INSTALL_UNKNOWN','STATUS_UNAVAILABLE','START_UNCONFIRMED']);
 function remember(id){
  pendingRequest=id;
  try{
   if(id)sessionStorage.setItem(pendingKey,id);
   else sessionStorage.removeItem(pendingKey);
  }catch(_){}
 }
 const compare=(a,b)=>{const x=a.split('.').map(Number),y=b.split('.').map(Number);for(let i=0;i<3;i++){if(x[i]!==y[i])return x[i]>y[i]?1:-1;}return 0;};
 const jobPhases={
  CHECKING:'checking',DOWNLOADING:'downloading',VERIFYING:'verifying',
  STAGED:'staged',WAITING_FOR_IDLE:'waiting',INSTALLING:'installing'
 };
 const issueStates=new Set(['FAILED','START_REJECTED','INTERRUPTED','DOWNLOADED_NOT_INSTALLED',
  'BUSY','START_NOT_RECORDED','START_ARCHIVED']);
 const icons={
  available:'<path d="M8 2v9m-3-3 3 3 3-3M3 13h10"/>',
  restart:'<path d="M8 2v6M4.4 4.1a5.3 5.3 0 1 0 7.2 0"/>',
  checking:'<path d="M13.5 8a5.5 5.5 0 1 1-4-5.3"/>',
  downloading:'<path d="M13.5 8a5.5 5.5 0 1 1-4-5.3"/>',
  verifying:'<path d="M8 2l5 2v4c0 2.2-2.1 4.5-5 6-2.9-1.5-5-3.8-5-6V4zM6 8l1.4 1.4L10 6.5"/>',
  staged:'<path d="M2.5 6.5h11v6a1 1 0 0 1-1 1h-9a1 1 0 0 1-1-1zM2 6.5l2-4h8l2 4M6 9h4"/>',
  waiting:'<path d="M4 2h8M4 14h8M5 2v2.4c0 1.2.7 1.9 3 3.6 2.3 1.7 3 2.4 3 3.6V14m0-12v2.4c0 1.2-.7 1.9-3 3.6-2.3 1.7-3 2.4-3 3.6V14"/>',
  installing:'<path d="M8 2v2m0 8v2M2 8h2m8 0h2M3.8 3.8l1.4 1.4m5.6 5.6 1.4 1.4m0-8.4-1.4 1.4m-5.6 5.6-1.4 1.4"/><circle cx="8" cy="8" r="3"/>',
  error:'<circle cx="8" cy="8" r="5.75"/><path d="M8 5v4m0 2h.01"/>',
  recovery:'<path d="M3 6.2A5.5 5.5 0 1 1 2.7 10M3 2.5v4h4M8 5v3l2 1.4"/>'
 };
 function showFeedback(open,{focus=false}={}){
  if(!open&&feedback.hidden)return;
  feedback.hidden=!open;
  home?.setAttribute('aria-expanded',String(open));
  if(focus)(open?(operation.hidden||operation.disabled?close:operation):home)?.focus();
 }
 function canStart(){
  return ready&&!closed&&!checking&&!reading&&!starting&&!active.has(job)&&
   !terminal.has(job)&&!pendingRequest&&Boolean(latest);
 }
 function buttons(){
  checkButton.disabled=!ready||closed||checking;
  if(!home)return;
  let state='current',label=ui.message('当前已是最新版本'),action=null;
  if(job==='INSTALLED_RELOAD_REQUIRED'){
   state='restart';label=ui.message('重启 Codex');
  }else if(starting||active.has(job)){
   state=jobPhases[job]||'checking';label=jobMessage||ui.message('正在检查…');
  }else if(pendingRequest||job==='INSTALL_UNKNOWN'||(job==='STATUS_UNAVAILABLE'&&readJob)){
   state='recovery';label=ui.message('查询本次结果');action='status';
  }else if(checking&&(manualCheck||issueStates.has(job))){
   state='checking';label=ui.message('正在检查…');
  }else if(issueStates.has(job)||box.dataset.discovery==='CHECK_UNAVAILABLE'){
   state='error';label=ui.message('检查失败');action=latest?'retry':'check';
   if(issueStates.has(job))label=ui.message('升级未完成。');
  }else if(latest){
   state='available';label=ui.message('有更新');
  }
  const visible=ready&&!closed&&state!=='current';
  const blocked=!ready||closed||!readJob||starting||active.has(job)||checking||reading;
  home.hidden=!visible;
  home.disabled=!ready||closed;
  home.setAttribute('aria-disabled',String(blocked));
  home.dataset.update=state;
  ui.attr(home,'aria-label',label.key,...label.values);
  const shownPercent=state==='downloading'?percent:null;
  const drawing=shownPercent===null?state:String(shownPercent);
  if(face.dataset.drawing!==drawing){
   face.dataset.drawing=drawing;
   if(shownPercent!==null)face.textContent=shownPercent+'%';
   else face.innerHTML=icons[state]?
    '<svg viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.65" stroke-linecap="round" stroke-linejoin="round">'+icons[state]+'</svg>':'';
  }
  const phase=visible?(state==='error'?job+':'+box.dataset.discovery:state):job==='LOADED'?'loaded':'idle';
  if(homeStatus&&homeStatus.dataset.phase!==phase){
   homeStatus.dataset.phase=phase;
   const announcement=state==='downloading'?ui.message(messages.DOWNLOADING):
    state==='recovery'||(state==='error'&&issueStates.has(job))?jobMessage||label:
    state==='error'?checkMessage||label:phase==='loaded'?ui.message(messages.LOADED):visible?label:null;
   ui.set(homeStatus,announcement?.key,...(announcement?.values||[]));
  }
  if(!visible||['available','current'].includes(state))showFeedback(false);
  ui.set(heading,label.key,...label.values);
  const feedbackText=issueStates.has(job)||state==='recovery'||state==='restart'?jobMessage:checkMessage;
  ui.set(jobStatus,feedbackText?.key,...(feedbackText?.values||[]));
  restartHelp.hidden=state!=='restart';
  feedbackAction=action;
  operation.hidden=!action;
  operation.disabled=blocked;
  if(action)ui.set(operation,{check:'检查更新',retry:'重试升级',status:'查询本次结果'}[action]);
  helpButton.hidden=!canOpenLinks||!(jobHelp||box.dataset.discovery==='CHECK_UNAVAILABLE');
 }
 function sayJob(text,state,...values){jobMessage=text?ui.message(text,...values):null;box.dataset.state=state;paintAvailable();buttons();}
 function paintAvailable(){
  if(box.dataset.discovery!=='UPDATE_AVAILABLE')return;
  const awaitingRestart=job==='INSTALLED_RELOAD_REQUIRED';
  const installedPending=installedRow.querySelector('dd').textContent;
  const blocked=starting||active.has(job)||terminal.has(job)||Boolean(pendingRequest);
  const text=awaitingRestart&&installedPending===lastStable?'已安装最新稳定版':
    blocked?'发现新版本':'有新版本可升级';
  ui.set(status,text);
 }
 function detail(node,code){
  ui.raw(node,code||'');node.hidden=!code;
  technical.hidden=checkDetail.hidden&&jobDetail.hidden;
  if(technical.hidden)technical.open=false;
 }
 function valid(value){
  if(!value||typeof value!=='object'||Array.isArray(value)||value.repository!==repository||value.installed_version!==installed)return false;
  if(value.state==='CHECK_UNAVAILABLE')return true;
  if(typeof value.latest_version!=='string'||!versionPattern.test(value.latest_version)||!versionPattern.test(installed)||value.tag!=='v'+value.latest_version||typeof value.advertised_revision!=='string'||!/^([0-9a-f]{40}|[0-9a-f]{64})$/.test(value.advertised_revision))return false;
  const order=compare(value.latest_version,installed),expected=order>0?'UPDATE_AVAILABLE':order===0?'UP_TO_DATE':'DEVELOPMENT_AHEAD';return value.state===expected;
 }
 const checkErrors={
  SOURCE_REWRITTEN:'Git 配置改变了更新源地址',NETWORK_TIMEOUT:'连接更新源超时',NETWORK_DNS:'更新源域名解析失败',
  NETWORK_CONNECT:'无法连接更新源',AUTH_REQUIRED:'当前 Git 访问需要登录',ACCESS_UNAVAILABLE:'当前 Git 身份无法访问更新源',
  TLS_FAILED:'更新源证书校验失败',REDIRECT_REFUSED:'更新源已重定向，需切换到官方新地址',NO_STABLE_TAGS:'未读到稳定版本标签',
  INVALID_TAG_RESPONSE:'版本标签响应不完整',GIT_UNAVAILABLE:'本机 Git 不可用',GIT_FAILED:'Git 更新查询失败',
  CARRIER_LIMIT:'更新响应过大',INVALID_VERSION:'已安装版本信息无效',PROCESS_TIMEOUT:'本机更新查询超时',
  RELEASE_CHANNEL_UNAVAILABLE:'暂时无法读取公开稳定发行',
  RELEASE_CHANNEL_INVALID:'公开稳定发行的文件信息未通过校验',
  RELEASE_CHANNEL_CHANGED:'公开发行与版本标签正在同步，请稍后检查',
  LOCAL_PROCESS_ERROR:'本机更新进程不可用',UNAVAILABLE:'更新查询暂不可用'
 };
 function checkUnavailable(code){
  latest=null;
  const known=typeof code==='string'&&Object.hasOwn(checkErrors,code);
  if(lastStable)ui.set(stable,'{0}（上次查到）',lastStable);
  else ui.set(stable,'暂不可获取');
  box.dataset.discovery='CHECK_UNAVAILABLE';
  checkMessage=ui.message(known?checkErrors[code]:'暂时无法检查更新，请稍后重试。');
  ui.set(status,'检查失败');
  detail(checkDetail,known?code:'UPDATE_CHECK_FAILED');
 }
 function showDiscovery(value){
  checkMessage=null;lastStable=value.latest_version;ui.raw(stable,lastStable);detail(checkDetail,null);
  latest=value.state==='UPDATE_AVAILABLE'?value:null;
  box.dataset.discovery=value.state;
  if(latest)paintAvailable();
  else ui.set(status,value.state==='UP_TO_DATE'?'当前已是最新版本':'当前运行的是较新的开发版本。');
 }
 function restoreDiscovery(raw){
  if(!raw||checking||closed)return false;
  try{
   const {checkedAt,value}=JSON.parse(raw),age=Date.now()-checkedAt;
   if(!Number.isSafeInteger(checkedAt)||age<0||age>=recheckAfter||checkedAt<=stableCheckedAt||
      !valid(value)||value.state==='CHECK_UNAVAILABLE'||(lastStable&&compare(value.latest_version,lastStable)<0))return false;
   stableCheckedAt=lastCheckAt=checkedAt;
   showDiscovery(value);buttons();
   return true;
  }catch(_){return false;}
 }
 function cacheDiscovery(value){
  stableCheckedAt=Date.now();
  const {state,latest_version,tag,advertised_revision}=value;
  const snapshot={state,latest_version,tag,advertised_revision,repository,installed_version:installed};
  try{localStorage.setItem(discoveryKey,JSON.stringify({checkedAt:stableCheckedAt,value:snapshot}));}catch(_){}
 }
 function discoveryChanged(event){
  if(event.key===discoveryKey&&box.dataset.discovery!=='CHECK_UNAVAILABLE')restoreDiscovery(event.newValue);
 }
 async function check(showOnDock=false){
  if(!ready||closed||checking)return;
  checking=true;manualCheck=showOnDock;lastCheckAt=Date.now();latest=null;
  box.dataset.discovery='CHECKING';
  ui.set(status,'正在检查稳定版本…');buttons();
  try{
   const reply=await rpc('tools/call',{name:'wce.ui.updates.check',arguments:{}});if(closed)return;
   const value=reply?.structuredContent;if(reply?.isError||!valid(value))throw new Error('UPDATE_CHECK_FAILED');
   if(value.state==='CHECK_UNAVAILABLE'){checkUnavailable(value.diagnostic?.code);return;}
   if(lastStable&&compare(value.latest_version,lastStable)<0){checkUnavailable('RELEASE_CHANNEL_CHANGED');return;}
   showDiscovery(value);cacheDiscovery(value);
  }catch(_){if(!closed)checkUnavailable();}
  finally{checking=false;manualCheck=false;if(!closed)buttons();}
 }
 const messages={
  CHECKING:'正在核对已选版本…',DOWNLOADING:'正在下载更新…',VERIFYING:'正在校验更新文件…',
  STAGED:'更新文件已校验，正在准备安装…',
  WAITING_FOR_IDLE:'正在等待 Jiusera 业务空闲…',INSTALLING:'正在通过 Codex 安装…',
  INSTALLED_RELOAD_REQUIRED:'重启 Codex 后启用 {0}。',
  LOADED:'新版本已启用。',
  INSTALL_UNKNOWN:'上次安装结果待核实。确认后可继续升级。',
  INTERRUPTED:'升级已中断，可重新检查版本。',
  DOWNLOADED_NOT_INSTALLED:'更新文件已下载，安装尚未开始。可以继续升级。',
  BUSY:'升级等待业务空闲后停止。确认任务已结束后，可继续升级。',
  FAILED:'升级未完成。',
  START_REJECTED:'升级未启动。',
  START_NOT_RECORDED:'本机没有受理这次升级。可重新发起。',
  START_ARCHIVED:'这次升级已归档。可核对当前版本。'
 };
 function renderJob(value){
  if(!value||!(value.state==='IDLE'||Object.hasOwn(messages,value.state)))throw new Error('UPDATE_STATUS_INVALID');
  if(value.state==='INSTALLED_RELOAD_REQUIRED'&&
     (!versionPattern.test(value.version)||compare(value.version,installed)<=0))throw new Error('UPDATE_STATUS_INVALID');
  job=value.state;
  percent=job==='DOWNLOADING'&&Number.isSafeInteger(value.total)&&value.total>0&&
   Number.isSafeInteger(value.downloaded)&&value.downloaded>=0&&value.downloaded<=value.total?
   Math.floor(value.downloaded*100/value.total):null;
  installedRow.hidden=job!=='INSTALLED_RELOAD_REQUIRED';
  ui.raw(installedRow.querySelector('dd'),installedRow.hidden?'':value.version);
  jobHelp=false;
  detail(jobDetail,null);
  const old=value.history;
  const historyText={
   CONNECTION_NOT_COMMITTED:'{0} 的一次升级曾因公众号绑定检查停止。',
   UPDATE_BUSINESS_BUSY:'{0} 的一次升级曾停在业务占用检查。',
   CONNECTION_BUSY:'{0} 的一次升级曾停在业务占用检查。',
   CONNECTION_START_PENDING:'{0} 的一次升级曾停在业务占用检查。',
   UPDATE_ACTIVITY_UNVERIFIED:'{0} 的一次升级曾因无法确认后台状态而停止。',
   UPDATE_PREVIOUS_INSTALL_RECEIPT:'已保留 {0} 的原安装回执。',
   UPDATE_INSTALL_READBACK_FAILED:'已保留 {0} 当时未核实的安装结果。',
   UPDATE_OLD_CACHE_RETENTION_FAILED:'已保留 {0} 当时的缓存保全失败记录。'
  };
  history.hidden=!['LOADED','INSTALLED_RELOAD_REQUIRED'].includes(job)||
   !Object.hasOwn(historyText,old?.code)||!versionPattern.test(old?.version);
  if(!history.hidden)ui.set(history.querySelector('span'),historyText[old.code],old.version);
  if(job==='IDLE'){sayJob('',job);return;}
  const code=typeof value.code==='string'&&/^(UPDATE|CONNECTION)_[A-Z0-9_]{1,65}$/.test(value.code)
    ? value.code : null;
  detail(jobDetail,code);
  const cacheFailures={
   UPDATE_OLD_CACHE_INVALID:'旧版缓存完整性校验未通过。',
   UPDATE_OLD_CACHE_UNVERIFIED:'无法从固定发行版本核对旧版缓存。',
   UPDATE_ROLLBACK_PACKAGE_INVALID:'无法准备干净的旧版回退包。',
   UPDATE_OLD_CACHE_RETENTION_FAILED:'无法保全旧版缓存，尚未切换版本。',
   UPDATE_CACHE_ARCHIVE_DIRECTORY:'无法使用旧版归档目录，尚未切换版本。',
   UPDATE_CACHE_STAGE_PREVIOUS:'无法准备可启动的旧版副本，尚未切换版本。',
   UPDATE_CACHE_RECHECK_CHANGED:'旧版文件在保全期间发生变化，尚未切换版本。',
   UPDATE_CACHE_ARCHIVE_SWAP:'无法交换旧版归档目录，尚未切换版本。',
   UPDATE_CACHE_ARCHIVE_VERIFY:'无法确认旧版原目录已归档，尚未切换版本。'
  };
  const updateFailures={
   UPDATE_DOWNLOAD_TIMEOUT:'下载超时。请确认网络连接后重试。',
   UPDATE_ASSET_SIZE_MISMATCH:'下载大小与发行记录不一致。请重试。',
   UPDATE_ASSET_HASH_MISMATCH:'下载文件校验失败。请重试。',
   UPDATE_MANIFEST_MISMATCH:'下载包清单与发行记录不一致。请重新检查更新。',
   UPDATE_PAYLOAD_MISMATCH:'下载包内文件校验失败。请重新检查更新。',
   UPDATE_ARCHIVE_INVALID:'发行压缩包未通过校验。请重新检查更新。',
   UPDATE_PLATFORM_UNSUPPORTED:'此自动升级入口仅支持 Apple 芯片 Mac。',
   UPDATE_CODEX_CLI_UNAVAILABLE:'未找到 Codex 命令行。请从原 Codex 市场更新。',
   UPDATE_INSTALLED_VERSION_CHANGED:'本机安装已变化。请重新打开 Codex 后再检查。',
   UPDATE_INSTALL_REJECTED:'Codex 未接受安装请求。请查看更新指引。'
  };
  const blockedUpdate=job==='FAILED'&&Object.hasOwn(cacheFailures,code);
  jobHelp=job==='INSTALL_UNKNOWN'||job==='FAILED'||job==='START_REJECTED';
  const failedPhase={
   CHECKING:'核对发行版本',DOWNLOADING:'下载更新',VERIFYING:'校验更新文件',
   STAGED:'准备安装',WAITING_FOR_IDLE:'核对业务状态',INSTALLING:'安装和回读'
  }[value.failed_phase];
  if(job==='INSTALL_UNKNOWN'&&code==='UPDATE_CACHE_OLD_LAUNCH_RESTORE'){
   sayJob('旧会话入口尚未核实。请查询本次结果。',job);
  }else if(job==='INSTALL_UNKNOWN'&&code==='UPDATE_CLI_ACTION_TIMEOUT'){
   sayJob('Codex 安装操作超时。请先检查原安装结果。',job);
  }else if(job==='FAILED'&&code==='UPDATE_CLI_LIST_TIMEOUT'){
   sayJob('Codex 查询插件市场超时。请重试或查看升级指引。',job);
  }else if(blockedUpdate){
   sayJob(cacheFailures[code],job);
  }else if(issueStates.has(job)&&Object.hasOwn(updateFailures,code)){
   sayJob(updateFailures[code],job);
  }else if(job==='FAILED'&&code==='CONNECTION_NOT_COMMITTED'){
   sayJob('公众号绑定校验未通过。可从原 Codex 市场升级。',job);
  }else if(job==='FAILED'&&code==='UPDATE_ACTIVITY_UNVERIFIED'){
   sayJob('暂时无法确认后台是否空闲。',job);
  }else if(percent!==null){
   sayJob('正在下载更新 {0}%',job,percent);
  }else if(job==='LOADED'&&historyText[old?.code]&&versionPattern.test(old?.version)&&compare(old.version,installed)>0){
   sayJob('已核对当前运行版本 {0}。',job,installed);
  }else if(job==='FAILED'&&code==='UPDATE_ADVERTISEMENT_CHANGED'){
   latest=null;
   try{localStorage.removeItem(discoveryKey);}catch(_){}
   sayJob('稳定版已有变化。请重新检查更新。',job);
  }else if(job==='FAILED'&&code==='UPDATE_CHECK_UNAVAILABLE'){
   checkUnavailable('RELEASE_CHANNEL_UNAVAILABLE');
   sayJob('暂时无法核对安装目标。可重新检查更新。',job);
  }else if(job==='FAILED'&&failedPhase){
   sayJob('升级停在「{0}」。',job,ui.message(failedPhase));
  }else if(job==='FAILED'&&value.downloaded===true){
   sayJob('更新已下载，安装未完成。可查看升级指引恢复原安装。',job);
  }else{
   sayJob(messages[job],job,value.version||installed);
  }
 }
 function statusUnavailable(){
  // Keep a verified install awaiting restart visible if a later read fails.
  if(job==='INSTALLED_RELOAD_REQUIRED'){
   detail(jobDetail,'UPDATE_STATUS_UNAVAILABLE');return;
  }
  job=pendingRequest?'START_UNCONFIRMED':'STATUS_UNAVAILABLE';
  installedRow.hidden=true;history.hidden=true;
  jobHelp=true;
  detail(jobDetail,'UPDATE_STATUS_UNAVAILABLE');
  sayJob(pendingRequest?'本机尚未确认更新结果。请选择「查询本次结果」。':'暂时无法读取升级进度。',job);
 }
 const visible=()=>document.visibilityState!=='hidden';
 const canPoll=()=>!closed&&visible()&&!blurred;
 function schedule(delay=650){
  clearTimeout(pollTimer);
  if(canPoll())pollTimer=setTimeout(()=>void statusPoll(),delay);
 }
 async function statusPoll(){
  if(closed||reading||starting)return;
  clearTimeout(pollTimer);
  const wasActive=active.has(job);
  reading=true;buttons();
  try{
   const result=await rpc('tools/call',{name:'wce.ui.updates.install',arguments:{action:'status',
    ...(pendingRequest?{request_id:pendingRequest}:{})}});
   if(closed)return;
   if(result?.isError)throw new Error('UPDATE_STATUS_UNAVAILABLE');
   const value=result?.structuredContent;
   if(pendingRequest&&(value?.request_id!==pendingRequest||value.state==='START_UNCONFIRMED')){
    statusUnavailable();return;
   }
   if(pendingRequest&&['START_NOT_RECORDED','START_ARCHIVED'].includes(value.state)){
    // A different worker may own the current receipt. An orphaned request
    // cannot clear its unknown or restart-required state.
    remember(null);
    const current=await rpc('tools/call',{name:'wce.ui.updates.install',arguments:{action:'status'}});
    if(closed)return;
    if(current?.isError)throw new Error('UPDATE_STATUS_UNAVAILABLE');
    if(current?.structuredContent?.state==='IDLE')renderJob(value);
    else renderJob(current?.structuredContent);
    if(active.has(job))schedule();
    return;
   }
   renderJob(value);
   if(pendingRequest)remember(null);
   if(active.has(job))schedule();
   else if(value?.code==='UPDATE_ADVERTISEMENT_CHANGED')void check();
  }catch(_){
   if(closed)return;
   statusUnavailable();
   if(wasActive&&!pendingRequest)schedule(3000);
  }finally{reading=false;readJob=true;if(!closed)buttons();}
 }
 async function start(event){
  if(!event.isTrusted||!canStart())return;
  showFeedback(false);
  const request=Array.from(crypto.getRandomValues(new Uint8Array(16)),byte=>byte.toString(16).padStart(2,'0')).join('');
  const chosen=latest;
  starting=true;remember(request);job='CHECKING';sayJob(messages.CHECKING,job);
  try{
   const result=await rpc('tools/call',{name:'wce.ui.updates.install',arguments:{
    action:'start',version:chosen.latest_version,revision:chosen.advertised_revision,request_id:request}});
   if(closed)return;
   if(result?.isError)throw new Error('UPDATE_START_UNCONFIRMED');
   const value=result?.structuredContent;
   if(value?.request_id===request||(value?.state==='BUSY'&&!value.request_id)){
    renderJob(value);remember(null);
    if(active.has(job))schedule();
   }else{
    // A successful tool reply can return the receipt of an existing worker.
    // Re-read its current state instead of treating it as this request.
    if(!value||!Object.hasOwn(messages,value.state))throw new Error('UPDATE_STATUS_INVALID');
    statusUnavailable();schedule();
   }
  }catch(_){if(!closed){statusUnavailable();schedule();}}
  finally{starting=false;if(!closed)buttons();}
 }
 function resume(){
  if(!ready||closed||!visible()||!automatic)return;
  if(lastCheckAt===null||Date.now()-lastCheckAt>=recheckAfter)void check();
  if(pendingRequest||active.has(job))schedule(0);
 }
 function visibilityChanged(){if(visible())resume();else clearTimeout(pollTimer);}
 function focus(){blurred=false;resume();}
 function blur(){blurred=true;clearTimeout(pollTimer);}
 const listeners=[
  [document,'visibilitychange',visibilityChanged],[window,'pageshow',resume],
  [window,'focus',focus],[window,'blur',blur],[window,'storage',discoveryChanged]
 ];
 checkButton.addEventListener('click',()=>void check(true));
 function activate(event){
  if(!event.isTrusted||home.hidden||home.getAttribute('aria-disabled')==='true')return;
  if(home.dataset.update==='available'){void start(event);return;}
  showFeedback(feedback.hidden,{focus:true});
  if(!feedback.hidden&&home.dataset.update==='restart')void statusPoll();
 }
 home?.addEventListener('click',activate);
 operation.addEventListener('click',event=>{
  if(!event.isTrusted||!feedbackAction||operation.disabled)return;
  if(feedbackAction==='status')void statusPoll();
  else if(feedbackAction==='retry')void start(event);
  else void check(true);
 });
 close.addEventListener('click',()=>showFeedback(false,{focus:true}));
 feedback.addEventListener('keydown',event=>{
  if(event.key==='Escape'){event.stopPropagation();showFeedback(false,{focus:true});}
 });
 document.addEventListener('pointerdown',event=>{
  if(!feedback.hidden&&!feedback.contains(event.target)&&!home?.contains(event.target))showFeedback(false);
 });
 document.querySelectorAll('.wb-about-links a').forEach(link=>link.addEventListener('click',event=>{
  if(!event.isTrusted||!canOpenLinks)return;
  event.preventDefault();void rpc('ui/open-link',{url:link.href}).catch(()=>{});
 }));
 helpButton.addEventListener('click',event=>{
  if(event.isTrusted&&canOpenLinks)void rpc('ui/open-link',{
   url:'https://github.com/OpenAhoy/OpenAhoy-Releases/blob/main/UPDATE_PROMPT.md'
  }).catch(()=>{});
 });
 return {ready(capabilities){
   if(closed||ready)return;
   canOpenLinks=Boolean(capabilities?.openLinks);
   ready=true;
   for(const [target,event,listener] of listeners)target.addEventListener(event,listener);
   buttons();
  },startAutomatic(){
   if(closed||!ready||automatic)return;
   automatic=true;
   try{restoreDiscovery(localStorage.getItem(discoveryKey));}catch(_){}
   void statusPoll();resume();

  },dispose(){
   closed=true;ready=false;clearTimeout(pollTimer);
   for(const [target,event,listener] of listeners)target.removeEventListener(event,listener);
   buttons();
  }};

}};

'''


def decorate(value, installed_version, uri):
    result = deepcopy(value)
    page = result['contents'][0]
    text = page['text']
    # Narrow seams shared by the accepted stable and maintenance resources;
    # no copy of the page, business adapters or its own initialization bridge.
    seams = {
        "const $=id=>document.getElementById(id),bridge=window.parent,pending=new Map();":
            "const $=id=>document.getElementById(id),bridge=window.parent,pending=new Map();\n const softwareUpdates=OASoftwareUpdates.mount(rpc," + json.dumps(installed_version).replace('<', '\\u003c') + ');',
        'function dispose(){': 'function dispose(){softwareUpdates.dispose();',
        'buttons();await refresh();': ('softwareUpdates.ready(hostCapabilities);'
            'buttons();await refresh();requestAnimationFrame(()=>{if(!closed&&ready)softwareUpdates.startAutomatic();});'),
    }
    for before, after in seams.items():
        if text.count(before) != 1:
            raise WCEError('UPDATE_RESOURCE_INCOMPATIBLE')
        text = text.replace(before, after, 1)
    if text.count('<script>') != 1:
        raise WCEError('UPDATE_RESOURCE_INCOMPATIBLE')
    script = SCRIPT.replace("__UPDATE_HTML__", json.dumps(mark_chrome(UPDATE_HTML), ensure_ascii=False))
    script = script.replace("__FEEDBACK_HTML__", json.dumps(mark_chrome(FEEDBACK_HTML), ensure_ascii=False))
    page['text'] = text.replace('<script>', '<style>'+STYLE+'</style><script>'+script, 1)
    page['uri'] = uri
    return result
