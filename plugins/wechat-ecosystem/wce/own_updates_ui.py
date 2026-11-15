"""Small optional update strip sharing the existing native MCP Apps RPC."""
from copy import deepcopy
import json

from .contracts import WCEError
from .management_locale import FALLBACK, mark_chrome

STYLE = '''
#softwareUpdateSlot:empty{display:none}.oa-software-update{display:flex;flex-direction:column;gap:8px;padding:10px 0;margin:0;border-block:1px solid var(--line,#dce4e1);font-size:11px;line-height:1.5;min-width:0}
.oa-update-copy{min-width:0;display:flex;flex-direction:column;gap:4px}.oa-update-version{font-weight:600;white-space:nowrap}.oa-update-status{color:var(--muted,#61746c);overflow-wrap:anywhere}.oa-software-update[data-state="UPDATE_AVAILABLE"]{border-color:var(--accent,#026364)}
.oa-update-actions{display:flex;flex-direction:column;gap:6px}.oa-update-actions button{width:100%;font-size:11px;min-height:30px;padding:4px 8px;white-space:nowrap}.oa-update-actions .oa-update-start{background:var(--accent,#026364);color:#fff;border-color:transparent}
@media(max-width:799px),(max-height:599px){.oa-sidebar{display:grid;grid-template-columns:112px minmax(0,1fr);align-items:start}.oa-sidebar #softwareUpdateSlot{width:100%}.oa-sidebar>div:last-child{grid-column:1/-1}.oa-software-update{padding:8px 0}.oa-update-actions{flex-direction:row;flex-wrap:wrap}.oa-update-actions button{width:auto}}
'''

UPDATE_HTML = '''<div class="oa-update-copy"><span class="oa-update-version"></span><span class="oa-update-status" role="status" aria-live="polite">正在连接更新检查…</span></div><div class="oa-update-actions"><button type="button" class="oa-update-check" disabled>检查更新</button><button type="button" class="oa-update-start" hidden disabled>立即升级</button><button type="button" class="oa-update-help" hidden>查看升级与恢复方法</button></div>'''

SCRIPT = FALLBACK + r'''
window.OASoftwareUpdates={mount(rpc,installed){
 'use strict';
 const ui=globalThis.OAUI||globalThis.OAPlainUI;
 const repository='OpenAhoy/OpenAhoy-Releases',versionPattern=/^(0|[1-9][0-9]{0,8})\.(0|[1-9][0-9]{0,8})\.(0|[1-9][0-9]{0,8})$/;
 const box=document.createElement('section');box.className='oa-software-update';ui.attr(box,'aria-label','OpenAhoy 软件更新');box.dataset.state='NOT_CHECKED';
 box.innerHTML=__UPDATE_HTML__;
 const slot=document.getElementById('softwareUpdateSlot');if(!slot)throw new Error('UPDATE_VIEW_UNAVAILABLE');slot.append(box);ui.scan?.(box);
 const version=box.querySelector('.oa-update-version'),status=box.querySelector('.oa-update-status'),checkButton=box.querySelector('.oa-update-check'),startButton=box.querySelector('.oa-update-start');
 version.textContent='OpenAhoy '+installed;
 const helpButton=box.querySelector('.oa-update-help');
 const pendingKey='OpenAhoy.softwareUpdate.pending.'+installed;
 const requestPattern=/^[0-9a-f]{32}$/;
 let ready=false,closed=false,checking=false,starting=false,reading=false,latest=null,job='STATUS_UNAVAILABLE',pollTimer;
 let pendingRequest=null,canOpenLinks=false;
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
  checkButton.disabled=!ready||closed||checking||reading||busy;
  startButton.hidden=!latest||busy||terminal.has(job)||Boolean(pendingRequest);
  startButton.disabled=!ready||closed||checking||reading||startButton.hidden;
 }
 function say(text,state,...values){ui.set(status,text,...values);box.dataset.state=state;buttons();}
 function valid(value){
  if(!value||typeof value!=='object'||Array.isArray(value)||value.repository!==repository||value.installed_version!==installed)return false;
  if(value.state==='CHECK_UNAVAILABLE')return true;
  if(!versionPattern.test(value.latest_version)||!versionPattern.test(installed)||value.tag!=='v'+value.latest_version||typeof value.advertised_revision!=='string'||!/^([0-9a-f]{40}|[0-9a-f]{64})$/.test(value.advertised_revision))return false;
  const order=compare(value.latest_version,installed),expected=order>0?'UPDATE_AVAILABLE':order===0?'UP_TO_DATE':'DEVELOPMENT_AHEAD';return value.state===expected;
 }
 async function check(preserve=false){
  if(!ready||closed||checking||starting||active.has(job))return;checking=true;buttons();
  if(!preserve)say('正在检查稳定版本…','CHECKING');
  try{
   const reply=await rpc('tools/call',{name:'wce.ui.updates.check',arguments:{}});if(closed)return;
   const value=reply?.structuredContent;if(reply?.isError||!valid(value))throw new Error('UPDATE_CHECK_FAILED');
   latest=value.state==='UPDATE_AVAILABLE'?value:null;
   if(preserve||terminal.has(job))return;
   helpButton.hidden=true;
   if(value.state==='UPDATE_AVAILABLE')say('新版本 {0} 可用','UPDATE_AVAILABLE',value.latest_version);
   else if(value.state==='UP_TO_DATE')say('已是最新稳定版','UP_TO_DATE');
   else if(value.state==='DEVELOPMENT_AHEAD')say('当前版本高于稳定版 '+value.latest_version+'，不会降级。','DEVELOPMENT_AHEAD');
   else {const codes={SOURCE_REWRITTEN:'Git 配置改变了更新源地址',NETWORK_TIMEOUT:'连接更新源超时',NETWORK_DNS:'更新源域名解析失败',NETWORK_CONNECT:'无法连接更新源',AUTH_REQUIRED:'当前 Git 访问需要登录',ACCESS_UNAVAILABLE:'当前 Git 身份无法访问更新源',TLS_FAILED:'更新源证书校验失败',REDIRECT_REFUSED:'更新源已重定向，需切换到官方新地址',NO_STABLE_TAGS:'未读到稳定版本标签',INVALID_TAG_RESPONSE:'版本标签响应不完整',GIT_UNAVAILABLE:'本机 Git 不可用',GIT_FAILED:'Git 更新查询失败',CARRIER_LIMIT:'更新响应过大',INVALID_VERSION:'已安装版本信息无效',PROCESS_TIMEOUT:'本机更新查询超时',LOCAL_PROCESS_ERROR:'本机更新进程不可用',UNAVAILABLE:'更新查询暂不可用'};const code=value.diagnostic?.code;say((Object.hasOwn(codes,code)?codes[code]+'（'+code+'）':'暂时无法检查更新')+'。可在“诊断日志”查看安全记录。','CHECK_UNAVAILABLE');}
  }catch(_){if(!closed){latest=null;if(!preserve&&!terminal.has(job))say('暂时无法检查更新，请稍后重试。','CHECK_UNAVAILABLE');}}
  finally{checking=false;if(!closed)buttons();}
 }
 const messages={
  CHECKING:'正在核对已选版本…',DOWNLOADING:'正在下载更新…',VERIFYING:'正在校验更新文件…',
  STAGED:'更新文件已校验，正在准备安装…',
  WAITING_FOR_IDLE:'正在等待 OpenAhoy 业务空闲…',INSTALLING:'正在通过 Codex 安装…',
  INSTALLED_RELOAD_REQUIRED:'升级完成。请结束当前任务后重启 Codex。',
  LOADED:'已加载 OpenAhoy {0}',
  INSTALL_UNKNOWN:'安装结果待核实（{0}）。',
  INTERRUPTED:'升级已中断，可重新检查版本。',
  DOWNLOADED_NOT_INSTALLED:'更新文件已下载，安装尚未开始。可以继续升级。',
  BUSY:'OpenAhoy 正在执行任务，请在任务结束后点击升级。',
  FAILED:'升级未完成（{0}）。',
  START_REJECTED:'升级未启动（{0}）。'
 };
 function renderJob(value){
  if(!value||!(value.state==='IDLE'||Object.hasOwn(messages,value.state)))throw new Error('UPDATE_STATUS_INVALID');
  if(value.state==='INSTALLED_RELOAD_REQUIRED'&&
     (!versionPattern.test(value.version)||compare(value.version,installed)<=0))throw new Error('UPDATE_STATUS_INVALID');
  job=value.state;
  helpButton.hidden=true;
  ui.set(checkButton,terminal.has(job)?'查看升级状态':'检查更新');
  if(job==='IDLE'){buttons();return;}
  const code=typeof value.code==='string'&&/^(UPDATE|CONNECTION)_[A-Z0-9_]{1,65}$/.test(value.code)
    ? value.code : 'UPDATE_STATUS_UNAVAILABLE';
  if(job==='FAILED'&&code==='CONNECTION_NOT_COMMITTED'){
   helpButton.hidden=!canOpenLinks;
   say('公众号绑定校验未通过（{0}）。请查看升级与恢复说明，可从原 Codex 市场登记升级。',job,code);
   return;
  }
  if(job==='DOWNLOADING'&&Number.isSafeInteger(value.total)&&value.total>0&&
     Number.isSafeInteger(value.downloaded)&&value.downloaded>=0&&value.downloaded<=value.total){
   say('正在下载更新 {0}%',job,Math.floor(value.downloaded*100/value.total));
  }else if(job==='FAILED'&&value.downloaded===true){
   say('更新文件已下载，安装未完成（{0}）。',job,code);
  }else{
   const coded=job==='FAILED'||job==='INSTALL_UNKNOWN'||job==='START_REJECTED';
   say(messages[job],job,coded?code:value.version||installed);
  }
 }
 function statusUnavailable(){
  job=pendingRequest?'START_UNCONFIRMED':'STATUS_UNAVAILABLE';
  helpButton.hidden=true;
  ui.set(checkButton,'查看升级状态');
  say(pendingRequest?'升级请求的结果尚未确认。正在查询原请求。':'暂时无法读取升级进度。',job);
 }
 function schedule(delay=650){clearTimeout(pollTimer);if(!closed)pollTimer=setTimeout(()=>void statusPoll(),delay);}
 async function statusPoll(refresh=false){
  if(closed||reading||starting)return;
  clearTimeout(pollTimer);
  reading=true;buttons();
  try{
   const result=await rpc('tools/call',{name:'wce.ui.updates.install',arguments:{action:'status'}});
   if(closed)return;
   if(result?.isError)throw new Error('UPDATE_STATUS_UNAVAILABLE');
   const value=result?.structuredContent;
   if(pendingRequest&&value?.request_id!==pendingRequest){
    statusUnavailable();schedule(3000);return;
   }
   renderJob(value);
   if(pendingRequest)remember(null);
   if(active.has(job))schedule();
   else if(!terminal.has(job)&&(refresh||!latest)){
    await check(job!=='IDLE');
   }
  }catch(_){
   if(closed)return;
   statusUnavailable();schedule(3000);
  }finally{reading=false;if(!closed)buttons();}
 }
 async function start(event){
  if(!event.isTrusted||!ready||closed||checkButton.disabled||!latest||terminal.has(job))return;
  const request=Array.from(crypto.getRandomValues(new Uint8Array(16)),byte=>byte.toString(16).padStart(2,'0')).join('');
  const chosen=latest;
  starting=true;remember(request);job='CHECKING';say(messages.CHECKING,job);
  try{
   const result=await rpc('tools/call',{name:'wce.ui.updates.install',arguments:{
    action:'start',version:chosen.latest_version,revision:chosen.advertised_revision,request_id:request}});
   if(closed)return;
   if(result?.isError)throw new Error('UPDATE_START_UNCONFIRMED');
   const value=result?.structuredContent;
   if(value?.request_id===request){
    renderJob(value);remember(null);
    if(active.has(job))schedule();
   }else{
    // A successful tool reply can return the receipt of an existing worker.
    // Re-read its current state instead of treating it as this request.
    if(!value||!Object.hasOwn(messages,value.state))throw new Error('UPDATE_STATUS_INVALID');
    remember(null);statusUnavailable();schedule();
   }
  }catch(_){if(!closed){statusUnavailable();schedule();}}
  finally{starting=false;if(!closed)buttons();}
 }
 checkButton.addEventListener('click',()=>void statusPoll(true));
 startButton.addEventListener('click',start);
 helpButton.addEventListener('click',event=>{
  if(event.isTrusted&&canOpenLinks)void rpc('ui/open-link',{
   url:'https://github.com/OpenAhoy/OpenAhoy-Releases/blob/main/UPDATE_PROMPT.md'
  }).catch(()=>{});
 });
 return {ready(capabilities){
   if(closed)return;
   canOpenLinks=Boolean(capabilities?.openLinks);
   ready=true;buttons();void statusPoll(true);
  },dispose(){closed=true;ready=false;clearTimeout(pollTimer);buttons();}};

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
        'buttons();await refresh();': 'buttons();await refresh();softwareUpdates.ready(hostCapabilities);',
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
