"""Global help UI; raw free text is projected before it reaches the host bridge."""
from copy import deepcopy
from .support_privacy import javascript
from .contracts import WCEError

STYLE='''
.oa-support-toast{position:fixed;right:20px;bottom:20px;max-width:calc(100vw - 40px);padding:10px 16px;border-radius:9px;background:var(--ink,#263b35);color:#fff;font-size:13px;z-index:10000;box-shadow:0 4px 20px #0002}.oa-support-links{display:grid;gap:6px;margin-top:auto;padding-top:12px;border-top:1px solid var(--line,#ddd)}.oa-support-links button{text-align:left;justify-content:flex-start;font-size:12px;min-height:32px;background:transparent}
.oa-support-dialog{width:min(760px,calc(100vw - 36px));max-height:calc(100dvh - 40px);padding:0;border:1px solid var(--line,#ddd);border-radius:14px;color:var(--ink,#263b35);background:var(--surface,#fff);box-shadow:0 16px 80px #0003}.oa-support-dialog::backdrop{background:#0005}.oa-support-header,.oa-support-footer{display:flex;align-items:center;justify-content:space-between;gap:12px;padding:16px 20px;border-bottom:1px solid var(--line,#ddd)}.oa-support-header h2{margin:0;font-size:19px}.oa-support-body{padding:18px 20px;overflow:auto;max-height:calc(100dvh - 210px)}.oa-support-body label{display:block;font-size:13px;margin:12px 0 5px}.oa-support-body input,.oa-support-body textarea,.oa-support-body select{box-sizing:border-box;width:100%;font:inherit;border:1px solid var(--line,#ddd);border-radius:8px;padding:9px;background:#fff;color:#263b35}.oa-support-body textarea{min-height:70px;resize:vertical;font-size:13px}.oa-support-body .oa-support-preview{min-height:220px;font:12px/1.6 ui-monospace,monospace}.oa-support-body .oa-support-confirm{display:flex;gap:8px;align-items:start}.oa-support-confirm input{width:auto;flex:none;margin-top:3px}.oa-support-footer{border-bottom:0;border-top:1px solid var(--line,#ddd);justify-content:flex-start;flex-wrap:wrap}.oa-support-footer button{min-height:34px;font-size:12px}.oa-support-body p{font-size:12px;line-height:1.6;color:var(--muted,#61746c)}.oa-support-status{white-space:pre-wrap;overflow-wrap:anywhere}.oa-support-body .oa-support-result{display:block;font-size:13px;overflow-wrap:anywhere;margin-top:10px}
'''
HTML='''
<dialog id="oaSupportDialog" class="oa-support-dialog" aria-labelledby="oaSupportTitle"><header class="oa-support-header"><h2 id="oaSupportTitle">反馈问题</h2><button id="oaSupportClose">关闭</button></header><div class="oa-support-body"><p id="oaSupportPrivacy"></p><section id="oaSupportPendingPanel" hidden><label for="oaSupportPending">待确认的原反馈</label><select id="oaSupportPending"></select><button id="oaSupportNew">填写另一条反馈</button></section><section id="oaSupportForm"><label for="oaSupportDescription">哪里不对劲？（可不填）</label><textarea id="oaSupportDescription" maxlength="4000" placeholder="例如：点了没反应、账号没有显示。直接提交也可以。"></textarea><p>版本、系统及最近的脱敏诊断会自动附上，无需找日志或填写技术信息。</p></section><details id="oaSupportReview"><summary id="oaSupportReviewTitle">查看自动附加的信息（可选）</summary><label for="oaSupportPreview">脱敏内容</label><textarea id="oaSupportPreview" class="oa-support-preview" readonly></textarea></details><p id="oaSupportStatus" role="status" class="oa-support-status"></p><a id="oaSupportResult" class="oa-support-result" hidden target="_blank" rel="noopener noreferrer"></a></div><footer class="oa-support-footer"><button id="oaSupportSend" class="primary">提交反馈并附诊断</button><button id="oaSupportQuery" hidden>查询原提交</button><button id="oaSupportCopy" hidden>复制内容</button><button id="oaSupportExport" hidden>导出诊断日志</button></footer></dialog>
'''

SCRIPT=r'''
window.OASupport={mount(rpc){
 'use strict';
 SANITIZER
 const $=id=>document.getElementById(id),box=$('oaSupportDialog'),links=document.createElement('section');links.className='oa-support-links';links.setAttribute('aria-label','帮助与反馈');
 let ready=false,busy=false,mode='feedback',report=null,exportPending=false,pendingRows=[],openLinks=false,toast=null,toastTimer=null;
 function submittedNotice(){if(toastTimer)clearTimeout(toastTimer);if(!toast){toast=document.createElement('div');toast.className='oa-support-toast';toast.setAttribute('role','status');document.body.append(toast);}toast.textContent='反馈已提交，诊断信息已自动附上。';toast.hidden=false;toastTimer=setTimeout(()=>{toast.hidden=true;toastTimer=null;},5000);}
 const feedback=document.createElement('button'),diagnostics=document.createElement('button');feedback.textContent='反馈问题';diagnostics.textContent='诊断日志';links.append(feedback,diagnostics);document.querySelector('.oa-sidebar').append(links);
 const say=t=>{$('oaSupportStatus').textContent=t;};
 const scope=()=>{const id=document.querySelector('#platformNavigation [aria-current="page"]')?.dataset.platformId;return id==='x'?'x':id==='wechat_official_account'?'wechat':'general';};
 function buttons(){feedback.disabled=diagnostics.disabled=!ready;for(const id of ['oaSupportQuery','oaSupportCopy','oaSupportExport','oaSupportNew'])$(id).disabled=busy;$('oaSupportSend').hidden=mode!=='feedback';$('oaSupportSend').disabled=busy||!!report&&report.state!=='PREPARED';}
 async function call(operation,args={}){if(!ready)throw Error('NOT_READY');const r=await rpc('tools/call',{name:'wce.ui.support.action',arguments:{operation,arguments:args}});if(r?.isError||!r?.structuredContent)throw Error('SUPPORT_UNAVAILABLE');return r.structuredContent;}
 const identity=()=>({report_id:report.report_id,digest:report.digest});
 function reset(){report=null;exportPending=false;$('oaSupportResult').hidden=true;$('oaSupportResult').removeAttribute('href');$('oaSupportResult').textContent='';$('oaSupportQuery').hidden=true;}
 function show(value){reset();report=value;$('oaSupportPreview').value=value.body;$('oaSupportForm').hidden=mode!=='feedback'||value.state!=='PREPARED';$('oaSupportCopy').hidden=false;$('oaSupportExport').hidden=mode!=='diagnostics';buttons();}
 async function run(work){if(busy)return;busy=true;buttons();try{await work();}catch(_){say('本次操作未确认完成。发送结果待确认时只查询原提交，不会自动重发。');}finally{busy=false;buttons();}}
 async function prepare(){if(report)return report;const fields={description:supportRedact($('oaSupportDescription').value),steps:'',expected:'',actual:''};show(await call('PREVIEW',{fields,platform:scope()}));say('诊断信息已自动准备，点击提交才会发送。');return report;}
 async function resume(row){show(await call('OPEN',{report_id:row.report_id,digest:row.digest}));await result(report);}
 async function open(which){
  if(!ready||busy)return;const retained=mode==='feedback'&&report&&['PENDING','WEB_DRAFT'].includes(report.state)?report:null;
  mode=which;reset();$('oaSupportTitle').textContent=which==='feedback'?'反馈问题':'诊断日志';$('oaSupportForm').hidden=which!=='feedback';$('oaSupportReview').open=which==='diagnostics';$('oaSupportPreview').value='展开后自动生成脱敏信息，不会发送。';$('oaSupportCopy').hidden=true;$('oaSupportExport').hidden=which!=='diagnostics';$('oaSupportPendingPanel').hidden=true;
  $('oaSupportPrivacy').textContent=which==='feedback'?'提交时自动附上版本、系统和脱敏诊断，发往公开的 OpenAhoy GitHub 反馈仓库。不会发送密钥、账号资料或文章；请勿在描述里填写这些内容。':'日志只保存在本机，不含密钥、账号ID、文章正文、原始响应或宿主日志，不会自动上传。';say('');box.showModal();
  if(which==='diagnostics')await run(async()=>{show(await call('DIAGNOSTICS'));say('已读取本机脱敏诊断快照，尚未导出或上传。');});
  else {if(retained){show(retained);$('oaSupportQuery').hidden=false;}await run(async()=>{const value=await call('READ');pendingRows=value.pending||[];$('oaSupportPending').replaceChildren();for(const [index,row]of pendingRows.entries()){const option=document.createElement('option');option.value=String(index);option.textContent=row.title;$('oaSupportPending').append(option);}$('oaSupportPendingPanel').hidden=!pendingRows.length;if(pendingRows.length)await resume(pendingRows[0]);});}
  buttons();
 }
 async function result(value,{openDraft=false}={}){$('oaSupportResult').hidden=true;$('oaSupportResult').removeAttribute('href');$('oaSupportResult').textContent='';const confirmed=value?.state==='SUBMITTED'&&report&&value.report_id===report.report_id&&value.digest===report.digest&&/^https:\/\/github\.com\/OpenAhoy\/OpenAhoy-Feedback\/issues\/[1-9][0-9]*$/.test(value.url||'');if(value?.state==='SUBMITTED'&&!confirmed){say('提交回执未匹配原反馈，只查询原提交，不会重复发送。');$('oaSupportQuery').hidden=false;return;}report={...report,...value};$('oaSupportQuery').hidden=!['PENDING','WEB_DRAFT'].includes(value.state);if(value.state==='SUBMITTED'){say('反馈已提交，诊断信息已自动附上。');$('oaSupportResult').href=value.url;$('oaSupportResult').textContent=value.url;$('oaSupportResult').hidden=false;if(confirmed&&mode==='feedback'){box.close();submittedNotice();}}
 else if(value.state==='WEB_DRAFT'){say('已准备好包含诊断信息的 GitHub 反馈草稿，请在 GitHub 页面提交；当前尚未创建 Issue。');$('oaSupportResult').href=value.url;$('oaSupportResult').textContent='打开已填写的 GitHub 反馈';$('oaSupportResult').hidden=false;if(openDraft&&openLinks){try{await rpc('ui/open-link',{url:value.url});}catch(_){say('宿主未确认打开，请使用上方已填写的官方反馈链接；尚未确认提交。');}}}
 else if(value.state==='REJECTED')say('GitHub 明确拒绝了提交（HTTP '+value.http_status+'），不会自动重试。');
 else if(value.state==='PREPARED')say('诊断信息已自动准备，点击提交才会发送。');
 else say('提交结果待确认，只查询原反馈，不会重复发送。');}
 $('oaSupportResult').addEventListener('click',e=>{if(!openLinks)return;e.preventDefault();void run(async()=>{const url=$('oaSupportResult').href;if(!url.startsWith('https://github.com/OpenAhoy/OpenAhoy-Feedback/issues/'))return;const r=await rpc('ui/open-link',{url});if(!r||r.isError)say('宿主未确认打开 GitHub 页面，请使用上方链接。');});});
 feedback.addEventListener('click',()=>open('feedback'));diagnostics.addEventListener('click',()=>open('diagnostics'));$('oaSupportClose').addEventListener('click',()=>box.close());$('oaSupportPending').addEventListener('change',()=>run(()=>resume(pendingRows[Number($('oaSupportPending').value)])));$('oaSupportNew').addEventListener('click',()=>{reset();$('oaSupportForm').hidden=false;$('oaSupportReview').open=false;$('oaSupportCopy').hidden=true;say('原待确认反馈仍可从上方查询，不会重发原请求。');buttons();});
 $('oaSupportReview').addEventListener('toggle',()=>{if(box.open&&mode==='feedback'&&$('oaSupportReview').open&&!report)void run(prepare);});
 $('oaSupportDescription').addEventListener('input',()=>{reset();$('oaSupportPreview').value='描述已更新，提交时会自动附上新的脱敏信息。';$('oaSupportCopy').hidden=true;buttons();});
 $('oaSupportSend').addEventListener('click',()=>run(async()=>{await prepare();if(report?.state==='PREPARED'){report.state='PENDING';$('oaSupportQuery').hidden=false;$('oaSupportForm').hidden=true;await result(await call('SEND',identity()),{openDraft:true});}}));$('oaSupportQuery').addEventListener('click',()=>run(async()=>{if(report)await result(await call('STATUS',identity()));}));
 $('oaSupportCopy').addEventListener('click',()=>run(async()=>{try{await navigator.clipboard.writeText($('oaSupportPreview').value);say('已复制当前脱敏内容。');}catch(_){$('oaSupportPreview').focus();$('oaSupportPreview').select();say('已选中内容，请使用系统复制快捷键。');}}));
 $('oaSupportExport').addEventListener('click',()=>run(async()=>{if(!report)return;const action=exportPending?'query':'write';exportPending=true;const v=await call('EXPORT',{...identity(),action});if(v.state==='EXPORTED'&&v.destination==='Downloads'){exportPending=false;say('已保存到本机下载文件夹（~/Downloads）：'+v.filename+'。文件已独立读回核对。');}else if(v.state==='EXPORT_NOT_FOUND'){exportPending=false;say('没有找到原导出文件，未自动重写；可再次点击导出。');}else say('导出结果待确认，再次点击只查询原文件。');}));
 buttons();return {ready(caps){openLinks=!!caps?.openLinks;ready=true;buttons();},dispose(){ready=false;buttons();box.close();if(toastTimer)clearTimeout(toastTimer);toast?.remove();}};
}};
'''



def decorate(value):
    result=deepcopy(value);page=result['contents'][0];text=page['text']
    seams={"const $=id=>document.getElementById(id),bridge=window.parent,pending=new Map();":"const $=id=>document.getElementById(id),bridge=window.parent,pending=new Map();\n const support=OASupport.mount(rpc);",
        'function dispose(){':'function dispose(){support.dispose();',
        'buttons();await refresh();':'buttons();await refresh();support.ready(hostCapabilities);'}
    for before,after in seams.items():
        if text.count(before)!=1:raise WCEError('SUPPORT_RESOURCE_INCOMPATIBLE')
        text=text.replace(before,after,1)
    if text.count('<script>')!=1 or text.count('</body>')!=1:raise WCEError('SUPPORT_RESOURCE_INCOMPATIBLE')
    script=SCRIPT.replace('SANITIZER',javascript())
    page['text']=text.replace('<script>',HTML+'<style>'+STYLE+'</style><script>'+script,1)
    return result
