"""Small optional update strip sharing the existing native MCP Apps RPC."""
from copy import deepcopy
import json

from .contracts import WCEError
from .management_locale import FALLBACK, mark_chrome

STYLE = """
#softwareUpdateSlot:empty{display:none}
.oa-management .oa-software-update{--update-text:#075536;--update-bg:#d9f4e5;--update-hover:#c5ecd7;display:grid;gap:8px;min-width:0;padding:10px;border:0;border-radius:10px;background:var(--soft);box-shadow:none;font-size:11px;line-height:1.45}
body.oa-management[data-color-scheme=dark] .oa-software-update{--update-text:#b7f5d2;--update-bg:#18392b;--update-hover:#234d38}
@media(prefers-color-scheme:dark){body.oa-management:not([data-color-scheme=light]) .oa-software-update{--update-text:#b7f5d2;--update-bg:#18392b;--update-hover:#234d38}}
#wbHomeUpdateStatus{position:absolute;width:1px;height:1px;overflow:hidden;clip-path:inset(50%);white-space:nowrap;pointer-events:none}
.oa-management[data-workbench] .wb-dock>#wbHomeUpdate[data-update=available]{color:light-dark(#08704a,#8aebba)}
.oa-management[data-workbench] .wb-dock>#wbHomeUpdate:is([data-update=error],[data-update=recovery],[data-update=restart]){
 color:light-dark(#925311,#f1b977)
}
.oa-update-version{font-size:12px;font-weight:700;color:var(--ink)}
.oa-update-versions{margin:0;display:grid;gap:4px;font-variant-numeric:tabular-nums}
.oa-update-versions div{display:flex;flex-wrap:wrap;justify-content:space-between;gap:1px 8px}
.oa-update-versions dt{color:var(--muted)}.oa-update-versions dd{margin:0;font-weight:600;overflow-wrap:anywhere}
.oa-update-status,.oa-update-job{margin:0;overflow-wrap:anywhere}
.oa-update-status:empty,.oa-update-job:empty{display:none}
.oa-update-status{color:var(--ink)}
.oa-software-update[data-discovery="UPDATE_AVAILABLE"] .oa-update-status{color:var(--update-text);font-weight:650}
.oa-update-job{color:var(--ink);border-top:1px solid var(--line);padding-top:7px}
.oa-update-technical,.oa-update-history{margin:0;color:var(--muted);overflow-wrap:anywhere}
.oa-update-actions{display:flex;flex-wrap:wrap;align-items:center;gap:3px 8px}
.oa-management .oa-software-update .oa-update-actions button{min-width:0;max-width:100%;min-height:26px;padding:3px 4px;border:0;background:transparent;color:var(--ink);font-size:11px;line-height:1.35;text-align:left;white-space:normal;box-shadow:none}
.oa-management .oa-software-update .oa-update-actions button:not(:disabled):hover{text-decoration:underline}
.oa-management .oa-software-update .oa-update-actions button:disabled{opacity:1;color:var(--muted);cursor:default}
.oa-management .oa-software-update .oa-update-actions button.oa-update-start{width:100%;padding:5px 8px;background:var(--update-bg)!important;color:var(--update-text)!important;font-weight:700;text-align:center;border-radius:6px}
.oa-management .oa-software-update .oa-update-actions button.oa-update-start:not(:disabled):hover{background:var(--update-hover)!important;text-decoration:none}
.oa-management .oa-software-update .oa-update-actions button:focus-visible{outline:2px solid var(--update-text);outline-offset:2px}
@media(max-width:799px),(max-height:599px){.oa-management .oa-sidebar #softwareUpdateSlot{width:100%;min-width:0}}
@media(max-width:420px){.oa-management .oa-sidebar #softwareUpdateSlot{grid-column:1/-1;grid-row:2}}
"""

UPDATE_HTML = """
<strong class="oa-update-version">Jiusera</strong>
<dl class="oa-update-versions">
 <div><dt>当前运行</dt><dd class="oa-update-running"></dd></div>
 <div class="oa-update-installed-row" hidden><dt>已安装</dt><dd></dd></div>
 <div><dt>最新稳定版</dt><dd class="oa-update-latest"></dd></div>
</dl>
<p class="oa-update-status" role="status">正在连接更新检查…</p>
<p class="oa-update-job" role="status"></p>
<details class="oa-update-technical" hidden><summary>技术详情</summary><p class="oa-update-check-detail"></p><p class="oa-update-job-detail"></p></details>
<details class="oa-update-history" hidden><summary>更新历史</summary><span></span></details>
<div class="oa-update-actions">
 <button type="button" class="oa-update-start" hidden disabled>立即升级</button>
 <button type="button" class="oa-update-check" disabled>检查更新</button>
 <button type="button" class="oa-update-receipt" hidden disabled>查看升级状态</button>
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
 const status=node('status'),jobStatus=node('job'),checkButton=node('check'),startButton=node('start'),receiptButton=node('receipt');
 const stable=node('latest'),installedRow=node('installed-row'),helpButton=node('help'),history=node('history');
 const home=document.getElementById('wbHomeUpdate');
 const homeStatus=document.getElementById('wbHomeUpdateStatus');
 const technical=node('technical'),checkDetail=node('check-detail'),jobDetail=node('job-detail');
 if(slot.closest('.wb-settings-board')){
  const version=document.createElement('section');version.className='wb-setting-version';
  const title=node('version');ui.set(title,'关于 Jiusera');version.append(title,node('versions'),status);
  const details=document.createElement('div');details.className='wb-setting-update-details';details.append(jobStatus,technical,history);
  box.prepend(version);box.append(details);
 }
 ui.set(stable,'待检查');
 ui.raw(node('running'),installed);
 const pendingKey='OpenAhoy.softwareUpdate.pending.'+installed;
 const discoveryKey='Jiusera.softwareUpdate.discovery.'+installed;
 const requestPattern=/^[0-9a-f]{32}$/;
 const recheckAfter=30*60*1000;
 let ready=false,closed=false,checking=false,starting=false,reading=false,latest=null,job='STATUS_UNAVAILABLE',pollTimer;
 let pendingRequest=null,canOpenLinks=false,blurred=false,lastCheckAt=null,lastStable=null,automatic=false;
 let jobHelp=false,readJob=false,stableCheckedAt=0;
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
 function buttons(){
  const busy=starting||active.has(job);
  checkButton.disabled=!ready||closed||checking;
  receiptButton.hidden=job==='IDLE';
  receiptButton.disabled=!ready||closed||reading||starting;
  startButton.hidden=!latest||busy||terminal.has(job)||Boolean(pendingRequest);
  startButton.disabled=!ready||closed||checking||reading||startButton.hidden;
  helpButton.hidden=!canOpenLinks||!(jobHelp||box.dataset.discovery==='CHECK_UNAVAILABLE');
  if(!home)return;
  let state='unknown',label='检查更新',values=[];
  if(job==='INSTALLED_RELOAD_REQUIRED'){
   state='restart';label='需重启';
  }else if(busy){
   state='updating';label='升级中';
  }else if(checking||reading||(!readJob&&ready)){
   state='checking';label='正在检查稳定版本…';
  }else if(terminal.has(job)||pendingRequest){
   state='recovery';label='查看升级状态';
  }else if(job==='FAILED'||job==='START_REJECTED'){
   state='error';label=latest?'重试升级 v{0}':'检查失败';values=latest?[latest.latest_version]:[];
  }else if(latest&&!startButton.hidden){
   state='available';label='升级 v{0}';values=[latest.latest_version];
  }else if(box.dataset.discovery==='CHECK_UNAVAILABLE'){
   state='error';label='检查失败';
  }else if(['UP_TO_DATE','DEVELOPMENT_AHEAD'].includes(box.dataset.discovery)){
   state='current';label=box.dataset.discovery==='UP_TO_DATE'?'当前已是最新版本':'当前运行的是较新的开发版本。';
  }
  const detail=[status.textContent,jobStatus.textContent].filter(Boolean).join(' ');
  if(homeStatus&&homeStatus.textContent!==detail)ui.raw(homeStatus,detail);
  const hasUpdate=Boolean(latest||pendingRequest||busy)||
    ['INSTALLED_RELOAD_REQUIRED','INSTALL_UNKNOWN','FAILED','INTERRUPTED','DOWNLOADED_NOT_INSTALLED','BUSY'].includes(job);
  home.hidden=!hasUpdate;
  home.dataset.update=state;
  home.disabled=!ready||closed||checking||reading||busy||!readJob;
  ui.attr(home,'aria-label',label,...values);
  ui.attr(home,'title',label,...values);
 }
 function sayJob(text,state,...values){ui.set(jobStatus,text,...values);box.dataset.state=state;paintAvailable();buttons();}
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
  ui.set(status,known?checkErrors[code]:'暂时无法检查更新，请稍后重试。');
  detail(checkDetail,known?code:'UPDATE_CHECK_FAILED');
 }
 function showDiscovery(value){
  lastStable=value.latest_version;ui.raw(stable,lastStable);detail(checkDetail,null);
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
 async function check(){
  if(!ready||closed||checking)return;
  checking=true;lastCheckAt=Date.now();latest=null;
  box.dataset.discovery='CHECKING';
  ui.set(status,'正在检查稳定版本…');buttons();
  try{
   const reply=await rpc('tools/call',{name:'wce.ui.updates.check',arguments:{}});if(closed)return;
   const value=reply?.structuredContent;if(reply?.isError||!valid(value))throw new Error('UPDATE_CHECK_FAILED');
   if(value.state==='CHECK_UNAVAILABLE'){checkUnavailable(value.diagnostic?.code);return;}
   if(lastStable&&compare(value.latest_version,lastStable)<0){checkUnavailable('RELEASE_CHANNEL_CHANGED');return;}
   showDiscovery(value);cacheDiscovery(value);
  }catch(_){if(!closed)checkUnavailable();}
  finally{checking=false;if(!closed)buttons();}
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
  const cacheFailure=job==='FAILED'&&Object.hasOwn(cacheFailures,code);
  jobHelp=job==='INSTALL_UNKNOWN'||job==='FAILED';
  const failedPhase={
   CHECKING:'核对发行版本',DOWNLOADING:'下载更新',VERIFYING:'校验更新文件',
   STAGED:'准备安装',WAITING_FOR_IDLE:'核对业务状态',INSTALLING:'安装和回读'
  }[value.failed_phase];
  if(job==='INSTALL_UNKNOWN'&&code==='UPDATE_CACHE_OLD_LAUNCH_RESTORE'){
   sayJob('旧会话入口尚未核实。请查看原升级状态。',job);
  }else if(job==='INSTALL_UNKNOWN'&&code==='UPDATE_CLI_ACTION_TIMEOUT'){
   sayJob('Codex 安装操作超时。请先检查原安装结果。',job);
  }else if(job==='FAILED'&&code==='UPDATE_CLI_LIST_TIMEOUT'){
   sayJob('Codex 查询插件市场超时。请重试或查看升级指引。',job);
  }else if(cacheFailure){
   sayJob(cacheFailures[code],job);
  }else if(job==='FAILED'&&code==='CONNECTION_NOT_COMMITTED'){
   sayJob('公众号绑定校验未通过。可从原 Codex 市场升级。',job);
  }else if(job==='FAILED'&&code==='UPDATE_ACTIVITY_UNVERIFIED'){
   sayJob('暂时无法确认后台是否空闲。',job);
  }else if(job==='DOWNLOADING'&&Number.isSafeInteger(value.total)&&value.total>0&&
     Number.isSafeInteger(value.downloaded)&&value.downloaded>=0&&value.downloaded<=value.total){
   sayJob('正在下载更新 {0}%',job,Math.floor(value.downloaded*100/value.total));
  }else if(job==='LOADED'&&historyText[old?.code]&&versionPattern.test(old?.version)&&compare(old.version,installed)>0){
   sayJob('已核对当前运行版本 {0}。',job,installed);
  }else if(job==='FAILED'&&code==='UPDATE_ADVERTISEMENT_CHANGED'){
   latest=null;
   try{localStorage.removeItem(discoveryKey);}catch(_){}
   sayJob('稳定版已有变化。请核对最新版本后再升级。',job);
  }else if(job==='FAILED'&&code==='UPDATE_CHECK_UNAVAILABLE'){
   checkUnavailable('RELEASE_CHANNEL_UNAVAILABLE');
   sayJob('暂时无法核对安装目标。可重新检查更新。',job);
  }else if(job==='FAILED'&&failedPhase){
   sayJob('升级停在「{0}」。请查看技术详情或升级指引。',job,ui.message(failedPhase));
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
  sayJob(pendingRequest?'升级请求的结果尚未确认。可查看原请求状态。':'暂时无法读取升级进度。',job);
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
  if(!event.isTrusted||!ready||closed||startButton.disabled||startButton.hidden||!latest)return;
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
 checkButton.addEventListener('click',()=>void check());
 receiptButton.addEventListener('click',()=>void statusPoll());
 startButton.addEventListener('click',start);
 function activate(event){
  if(!event.isTrusted||event.currentTarget.disabled)return;
  if(terminal.has(job)||pendingRequest){void statusPoll();return;}
  if(latest&&!startButton.hidden){void start(event);return;}
  void check();
 }
 home?.addEventListener('click',activate);
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
    page['text'] = text.replace('<script>', '<style>'+STYLE+'</style><script>'+script, 1)
    page['uri'] = uri
    return result
