"""Small optional update strip sharing the existing native MCP Apps RPC."""
from copy import deepcopy
import json

from .contracts import WCEError

STYLE = '''
#softwareUpdateSlot:empty{display:none}.oa-software-update{display:flex;flex-direction:column;gap:8px;padding:10px 0;margin:0;border-block:1px solid var(--line,#dce4e1);font-size:11px;line-height:1.5;min-width:0}
.oa-update-copy{min-width:0;display:flex;flex-direction:column;gap:4px}.oa-update-version{font-weight:600;white-space:nowrap}.oa-update-status{color:var(--muted,#61746c);overflow-wrap:anywhere}.oa-software-update[data-state="UPDATE_AVAILABLE"]{border-color:var(--accent,#026364)}
.oa-update-actions{display:flex;flex-direction:column;gap:6px}.oa-update-actions button{width:100%;font-size:11px;min-height:30px;padding:4px 8px;white-space:nowrap}.oa-update-actions .oa-update-start{background:var(--accent,#026364);color:#fff;border-color:transparent}
@media(max-width:799px),(max-height:599px){.oa-sidebar{display:grid;grid-template-columns:112px minmax(0,1fr);align-items:start}.oa-sidebar #softwareUpdateSlot{width:100%}.oa-sidebar>div:last-child{grid-column:1/-1}.oa-software-update{padding:8px 0}.oa-update-actions{flex-direction:row;flex-wrap:wrap}.oa-update-actions button{width:auto}}
'''

SCRIPT = r'''
window.OASoftwareUpdates={mount(rpc,installed){
 'use strict';
 const repository='OpenAhoy/OpenAhoy-Releases',versionPattern=/^(0|[1-9][0-9]{0,8})\.(0|[1-9][0-9]{0,8})\.(0|[1-9][0-9]{0,8})$/;
 const box=document.createElement('section');box.className='oa-software-update';box.setAttribute('aria-label','OpenAhoy 软件更新');box.dataset.state='NOT_CHECKED';
 box.innerHTML='<div class="oa-update-copy"><span class="oa-update-version"></span><span class="oa-update-status" role="status" aria-live="polite">正在连接更新检查…</span></div><div class="oa-update-actions"><button type="button" class="oa-update-check" disabled>检查更新</button><button type="button" class="oa-update-start" hidden disabled>发起升级</button></div>';
 const slot=document.getElementById('softwareUpdateSlot');if(!slot)throw new Error('UPDATE_VIEW_UNAVAILABLE');slot.append(box);
 const version=box.querySelector('.oa-update-version'),status=box.querySelector('.oa-update-status'),checkButton=box.querySelector('.oa-update-check'),startButton=box.querySelector('.oa-update-start');
 version.textContent='OpenAhoy '+installed;
 let ready=false,closed=false,checking=false,messageText=false,sendState='NOT_SENT',latest=null;
 const compare=(a,b)=>{const x=a.split('.').map(Number),y=b.split('.').map(Number);for(let i=0;i<3;i++){if(x[i]!==y[i])return x[i]>y[i]?1:-1;}return 0;};
 function buttons(){checkButton.disabled=!ready||closed||checking||sendState==='SENDING';startButton.hidden=!latest;startButton.disabled=!ready||closed||checking||!latest||!messageText||sendState!=='NOT_SENT';}
 function say(text,state){status.textContent=text;box.dataset.state=state;buttons();}
 function valid(value){
  if(!value||typeof value!=='object'||Array.isArray(value)||value.repository!==repository||value.installed_version!==installed)return false;
  if(value.state==='CHECK_UNAVAILABLE')return true;
  if(!versionPattern.test(value.latest_version)||!versionPattern.test(installed)||value.tag!=='v'+value.latest_version||typeof value.advertised_revision!=='string'||!/^([0-9a-f]{40}|[0-9a-f]{64})$/.test(value.advertised_revision))return false;
  const order=compare(value.latest_version,installed),expected=order>0?'UPDATE_AVAILABLE':order===0?'UP_TO_DATE':'DEVELOPMENT_AHEAD';return value.state===expected;
 }
 async function check(){
  if(!ready||closed||checking||sendState==='SENDING')return;checking=true;buttons();
  if(sendState==='NOT_SENT')say('正在检查稳定版本…','CHECKING');
  try{
   const reply=await rpc('tools/call',{name:'wce.ui.updates.check',arguments:{}});if(closed)return;
   const value=reply?.structuredContent;if(reply?.isError||!valid(value))throw new Error('UPDATE_CHECK_FAILED');
   latest=value.state==='UPDATE_AVAILABLE'?value:null;
   if(sendState!=='NOT_SENT')return;
   if(value.state==='UPDATE_AVAILABLE')say('新版本 '+value.latest_version+' 可用'+(messageText?'':'；当前宿主未提供聊天消息能力，暂不能一键发起。'),'UPDATE_AVAILABLE');
   else if(value.state==='UP_TO_DATE')say('已是最新稳定版','UP_TO_DATE');
   else if(value.state==='DEVELOPMENT_AHEAD')say('当前版本高于稳定版 '+value.latest_version+'，不会降级。','DEVELOPMENT_AHEAD');
   else {const codes={SOURCE_REWRITTEN:'Git 配置改变了更新源地址',NETWORK_TIMEOUT:'连接更新源超时',NETWORK_DNS:'更新源域名解析失败',NETWORK_CONNECT:'无法连接更新源',AUTH_REQUIRED:'当前 Git 访问需要登录',ACCESS_UNAVAILABLE:'当前 Git 身份无法访问更新源',TLS_FAILED:'更新源证书校验失败',REDIRECT_REFUSED:'更新源已重定向，需切换到官方新地址',NO_STABLE_TAGS:'未读到稳定版本标签',INVALID_TAG_RESPONSE:'版本标签响应不完整',GIT_UNAVAILABLE:'本机 Git 不可用',GIT_FAILED:'Git 更新查询失败',CARRIER_LIMIT:'更新响应过大',INVALID_VERSION:'已安装版本信息无效',PROCESS_TIMEOUT:'本机更新查询超时',LOCAL_PROCESS_ERROR:'本机更新进程不可用',UNAVAILABLE:'更新查询暂不可用'};const code=value.diagnostic?.code;say((Object.hasOwn(codes,code)?codes[code]+'（'+code+'）':'暂时无法检查更新')+'。可在“诊断日志”查看安全记录。','CHECK_UNAVAILABLE');}
  }catch(_){if(!closed){latest=null;if(sendState==='NOT_SENT')say('暂时无法检查更新，请稍后重试。','CHECK_UNAVAILABLE');}}
  finally{checking=false;if(!closed)buttons();}
 }
 function request(value){
  return '请将本机 OpenAhoy 升级到公开发行仓库 '+repository+' 的稳定标签 '+value.tag+'。这是用户从 OpenAhoy 内嵌页面发起的本插件软件升级请求。先使用本机已有授权核对原分发源和该标签实际指向的 commit（本次版本广告 revision：'+value.advertised_revision+'），读取该固定标签的 UPDATE_PROMPT.md、RELEASE.json 和 package-manifest.json 并核验；不一致则说明具体问题，不切换其他来源。按本机实际支持的 Codex 官方插件命令完成升级，核对已安装版本和本聊天实际原生加载。保留全部既有账号绑定、系统钥匙串、个人配置、历史及原稿/UNKNOWN任务，只在业务安全点更新；不重绑、不覆盖资料、不卸载插件或手改供应商缓存，不借升级生产、上传或发表文章。使用原有权限，不索取任何 Secret；只有确需重开 Codex 且没有单插件刷新能力时，才集中提示用户一次。完成后报告实际安装、加载和账号/配置保全结果。';
 }
 async function start(){
  if(!ready||closed||checking||!latest||!messageText||sendState!=='NOT_SENT')return;
  const chosen=latest;sendState='SENDING';say('正在向当前聊天发起升级…','SENDING');
  try{
   const result=await rpc('ui/message',{role:'user',content:[{type:'text',text:request(chosen)}]});if(closed)return;
   if(!result||typeof result!=='object'||Array.isArray(result)||(result.isError!==undefined&&typeof result.isError!=='boolean'))throw new Error('UPDATE_MESSAGE_UNKNOWN');
   if(result.isError){sendState='REJECTED';say('宿主未接受升级请求；未确认执行安装。','REJECTED');return;}
   sendState='SENT';say('升级请求已发送到当前聊天，请查看 Codex 的执行结果。','SENT');
  }catch(error){
   if(closed)return;
   if(error.message==='HOST_ERROR'){sendState='REJECTED';say('宿主未接受升级请求；未确认执行安装。','REJECTED');}
   else{sendState='UNKNOWN';say('发送结果未知，请先查看当前聊天；本页不会重复发起。','UNKNOWN');}
  }finally{if(!closed)buttons();}
 }
 checkButton.addEventListener('click',check);startButton.addEventListener('click',start);
 return {ready(capabilities){
   if(closed)return;const message=capabilities?.message;
   messageText=!!message&&typeof message==='object'&&!Array.isArray(message)&&!!message.text&&typeof message.text==='object'&&!Array.isArray(message.text);
   ready=true;buttons();void check();
  },dispose(){closed=true;ready=false;buttons();}};
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
    page['text'] = text.replace('<script>', '<style>'+STYLE+'</style><script>'+SCRIPT, 1)
    page['uri'] = uri
    return result
