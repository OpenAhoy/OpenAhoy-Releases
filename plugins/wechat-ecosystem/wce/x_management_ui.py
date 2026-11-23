"""X adapter for the accepted native management workspace."""
from .x_schedule_ui import HTML as SCHEDULE_HTML
from .x_operating_ui import HTML as OPERATING_HTML

from .management_locale import FALLBACK

HTML = '''<style>
.oa-x-capabilities{flex:none;padding:12px 14px;margin-bottom:12px;border:1px solid var(--line,#dce4e1);border-radius:12px;background:var(--surface,#fff);font-size:12px;line-height:1.5}
.oa-x-capabilities h2{font-size:14px;margin:0 0 8px}.oa-x-features{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:8px;margin:0;padding:0;list-style:none}.oa-x-features li{min-width:0;padding:7px 9px;border-radius:7px;background:var(--bg,#f6f8fa)}.oa-x-features strong,.oa-x-features span{display:block}.oa-x-features span,.oa-x-capabilities p{color:var(--muted,#61746c)}.oa-x-capabilities p{margin:8px 0 0}.oa-native #settingsPanel:has(#xSettings:not([hidden])){overflow:auto}
@media(max-width:560px){.oa-x-features{grid-template-columns:repeat(2,minmax(0,1fr))}}
.oa-x-app-fields,.oa-x-balance{display:grid;grid-template-columns:repeat(auto-fit,minmax(min(100%,145px),1fr));gap:8px}
.oa-x-app-fields input{box-sizing:border-box;width:100%}.oa-x-balance>div{padding:8px 10px;border-radius:8px;background:var(--tint)}
.oa-x-balance dt{color:var(--muted);font-size:12px}.oa-x-balance dd{margin:4px 0 0;font-weight:600;font-variant-numeric:tabular-nums}
.oa-x-developer{padding:10px 12px;border-radius:12px;background:var(--oa-fill,var(--bg));margin-bottom:6px}
.oa-x-developer h3,.oa-x-developer p{margin:0 0 7px}
.oa-x-developer .actions{display:flex;gap:6px;flex-wrap:wrap}
.oa-management.oa-native.oa-x-developer-open #xSettings>:not(#xDeveloperSettings,#xBilling,#xAuthorization,#xWorkspaceBack){display:none!important}
.oa-management.oa-native.oa-x-developer-open #xSettings>#xBilling:not([hidden]){display:block!important}
.oa-management.oa-native.oa-x-developer-open #xAuthorization>:is(h3,#xBindingTarget){display:none}
.oa-management.oa-native.oa-x-developer-open #settingsPanel>:is(#platformTitle,#platformHelp,.oa-context-tabs){display:none}
.oa-management.oa-native.oa-x-developer-open #xWorkspaceBack{margin-bottom:6px;align-self:flex-start}
@media(max-width:799px){
 .oa-management.oa-native.oa-x-developer-open .oa-sidebar,
 .oa-management.oa-native.oa-x-developer-open .oa-account-header,
 .oa-management.oa-native.oa-x-developer-open .oa-footer{display:none}
 .oa-management.oa-native.oa-x-developer-open .oa-content{padding-block:8px}
}
#xManualSetup:not([open])>:not(summary){display:none}
.oa-x-binding-step{margin:6px 0;padding:8px 12px;border-radius:10px;background:var(--oa-fill,var(--bg))}
.oa-x-binding-step h4{margin:0 0 6px;font-size:13px}
.oa-management.oa-native #xSettings:has(>#xAuthorization:not([hidden])),.oa-management.oa-native.oa-x-developer-open #xSettings{max-inline-size:620px}
#xAuthorization p:empty,#xDeveloperNotice:empty{display:none}
#xAuthorization details.oa-x-setup-help{margin:4px 0;font-size:11px}
#xAuthorization #xSaveApplication{margin-top:5px}
.oa-management.oa-native .oa-x-binding-step input{background:var(--surface)}
.oa-management.oa-native:not(.oa-x-developer-open) #xSettings:has(>#xAuthorization:not([hidden]))>:not(#xAuthorization,#xWorkspaceBack){display:none!important}
.oa-x-callback{display:block;overflow-wrap:anywhere}.oa-x-billing-actions{display:flex;gap:8px;flex-wrap:wrap}
</style><section id="xCapabilities" class="oa-x-capabilities" aria-label="X 平台能力" hidden>
<h2>X 平台能力</h2><ul class="oa-x-features"><li><strong>账号与帖子</strong><span>授权、资料、原文上下文</span></li><li><strong>主动发现</strong><span>人物、主题、交友、指定回复</span></li><li><strong>文字、图片、GIF 与视频</strong><span>官方上传、异步处理、发帖与独立读回；实际格式和权益由 X 核验</span></li><li><strong>按原帖回复</strong><span>官方条件允许时执行、关系读回</span></li></ul>
<p>以上为已实现接口；实际可用性以本号授权、宿主工具和 X 返回为准。</p><p>“项目与 Skills”可设置主题、创作方法与回复风格；保存不自动开启互动。X 官方不允许自动点赞；AI 自动回复须事先获得 X 书面批准。</p></section>
<section id="xSettings" class="panel" data-platform-id="x" hidden>
<section id="xDeveloperSettings" class="oa-x-developer" hidden aria-labelledby="xDeveloperHeading">
<h3 id="xDeveloperHeading" tabindex="-1">X 开发者设置</h3>
<p id="xDeveloperIdentity"></p><p id="xDeveloperState" class="help"></p>
<div class="actions"><button id="xDeveloperConnect" type="button">连接自己的 X 开发者应用</button>
<button id="xDeveloperConsole" type="button">打开 X Developer Console</button></div>
<p id="xDeveloperNotice" class="help" role="status"></p></section>
<section aria-label="X 内容生产与发布" class="oa-x-production"><h3>内容生产与发布</h3>
<p id="xProductionAccount" class="help">选择已绑定的 X 账号。</p>
<div id="xProductionPreferences" class="oa-x-production-preferences"></div>
<p id="xProductionConfigStatus" class="help" role="status"></p>
<div class="actions"><button id="xProduceNow" class="primary" disabled>立即生产并发布</button><button id="xProductionResult" hidden>查看原任务结果</button><button id="xProductionSchedule" disabled>配置定时生产发布</button><button id="xProductionEdit">编辑内容配置</button></div>
<p id="xProductionStatus" class="notice" role="status">一次启动由当前 Codex 完成新文字、新配图、公开发布及真实链接读回。</p>
<details id="xProductionResume" hidden>
 <summary>接续原 X 请求</summary>
 <dl><dt>X 账号</dt><dd><span id="xResumeAccount"></span> <code id="xResumeConnection"></code></dd>
 <dt>原上传 ID</dt><dd><code id="xResumeUpload"></code></dd>
 <dt>原发帖 ID</dt><dd><code id="xResumePost"></code></dd></dl>
 <p class="help">把接续指令粘贴到具备 X 工具的 Codex 聊天。先查询原任务，结果未知时只查回执。</p>
 <button id="xResumeCopy" type="button">复制接续指令</button>
 <p id="xResumeStatus" class="help" role="status"></p>
 <textarea id="xResumeText" rows="5" readonly hidden aria-label="原 X 请求接续指令"></textarea>
</details>
<p class="help">使用已保存的本号配置。未关联项目或选填项为空时沿默认方法；保存配置不会启动任务。发送后请查看当前聊天，重新打开本页不代表原任务已结束。</p></section>
<section id="xAuthorization" hidden><h3 id="xBindingTitle">绑定 X 账号</h3><p id="xBindingTarget" class="help"></p>
<section class="oa-x-binding-step"><h4>1. 配置 X Developer Console 应用</h4>
<div class="actions"><button id="xSetupAssist" type="button">让 Codex 协助创建 X 应用</button><button id="xBindingConsole" type="button">打开 X Developer Console</button></div>
<p id="xSetupStatus" class="help" role="status"></p>
<details id="xManualSetup" open><summary>应用资料</summary>
<details class="oa-x-setup-help"><summary>回调地址与应用要求</summary>
<p class="help">使用启用读写权限的 Native App。X 费用由该应用的开发者账户承担。</p>
<code class="oa-x-callback" id="xCallback"></code>
</details>
<div class="oa-x-app-fields"><label>应用名称<input id="xApplicationName" maxlength="80"></label><label>OAuth 2.0 Client ID<input id="xClientId" maxlength="4096" spellcheck="false" autocomplete="off"></label></div>
<div class="actions"><button id="xSaveApplication" type="button">保存应用资料</button></div>
</details>
<p id="xSaveApplicationStatus" class="help" role="status"></p>
</section><section class="oa-x-binding-step"><h4>2. 在 X 授权发文</h4>
<p id="xAuthorizationHint" class="help"></p>
<div class="actions"><button id="xSwitchAccount" type="button" hidden>前往 X 切换账号</button><button id="xReauthorizeCurrent" class="primary" type="button" hidden>重新授权原应用</button><button id="xAuthorize" type="button">授权已保存的应用</button><button id="xCheck">检查授权结果</button><button id="xCancel" hidden>取消本次授权</button></div>
<p id="xStatus" class="notice" role="status">正在读取 X 设置…</p>
</section></section>
<details id="xBilling"><summary>账单与余额</summary>
<p id="xBillingApplication" class="help"></p><p class="help">余额属于开发者账户。同一应用上的多个 X 账号共用余额。</p>
<dl id="xBillingBalance" class="oa-x-balance" hidden><div><dt>总余额</dt><dd id="xTotalBalance"></dd></div><div><dt>预付余额</dt><dd id="xPrepaidBalance"></dd></div><div><dt>免费额度</dt><dd id="xFreeBalance"></dd></div></dl>
<ul id="xFreeGrants" hidden></ul><p id="xBillingStatus" class="notice" role="status"></p>
<div class="oa-x-billing-actions"><button id="xRefreshBilling" type="button">刷新余额</button><button id="xOpenConsole" type="button">去 X 充值 / 查看账单</button></div></details></section>'''
HTML = HTML.replace('<section id="xAuthorization" hidden>', SCHEDULE_HTML + '<section id="xAuthorization" hidden>')
HTML = HTML.replace('<details id="xSchedulePanel"', OPERATING_HTML + '<details id="xSchedulePanel"')

SCRIPT = FALLBACK + r'''
window.OAXManagement = {
 mount(call,openLink,onBound,{captureSelection=()=>null,selectedAccount=()=>null,sendChatRequest,canSendChatRequest=()=>!!sendChatRequest,onStatusChange=()=>{}}={}){
  const $=id=>document.getElementById(id);let busy=false,ready=false,generation=0,timer=null,waiting=false,readAgain=false,lastBound='',authorizationHandle=null,bindingSelection=null;
  const capability=$('xCapabilities');
  const billingPanel=$('xBilling'), appName=$('xApplicationName'),clientId=$('xClientId');
  const format=()=>globalThis.OAUI||globalThis.OAPlainUI;
  let connections=[],billingEpoch=0,billingBusy=false,billingTarget=null,lastBillingCheck=null;
  let setup=null,setupTimer=null,filled=null,target=null,authorizationTarget=null,authorizationForm=null,saved=null;
  const fields=()=>({application_name:appName.value.trim(),client_id:clientId.value.trim()});
  const matchesSaved=()=>saved&&Object.entries(fields()).every(([key,value])=>saved.draft[key]===value);
  const accountArgs=request=>request.cid?{connection_id:request.cid}:{};
  const handle=value=>typeof value==='string'&&/^[A-Za-z0-9_]{1,15}$/.test(value)?value:'';
  const say=(text,error=false,...values)=>{(globalThis.OAUI||globalThis.OAPlainUI).set($('xStatus'),text,...values);$('xStatus').className='notice'+(error?' error':'');};
  const buttons=()=>{for(const id of ['xCheck','xCancel'])$(id).disabled=!ready||busy;
   const hasFields=!!appName.value.trim()&&!!clientId.value.trim();
   $('xSaveApplication').disabled=!ready||busy||!target||target.loading||!hasFields||!!matchesSaved();
   $('xAuthorize').disabled=!ready||busy||!target||waiting||!matchesSaved();
   $('xReauthorizeCurrent').hidden=!target?.cid;
   $('xReauthorizeCurrent').disabled=!ready||busy||!target?.cid||waiting;
   $('xSwitchAccount').hidden=!target?.cid;
   $('xSwitchAccount').disabled=!ready||busy||waiting;
   $('xBindingConsole').disabled=!ready||busy||!target;
   const assist=$('xSetupAssist');assist.hidden=!sendChatRequest;assist.disabled=!ready||busy||!!setup||!!target?.loading;
  };
  const errors={X_OWN_CLIENT_ID_REQUIRED:'请输入你自己应用的 OAuth 2.0 Client ID。',X_APPLICATION_NAME_INVALID:'请输入有效的应用名称。',X_SELECT_EXISTING_ACCOUNT:'这个账号已绑定。请选择该账号，再点击「为当前账号切换应用」。',X_APPLICATION_CHANGED:'应用已切换，请刷新后检查当前账号。',X_APPLICATION_REQUIRED:'Jiusera 的 X 接入暂未就绪，请联系产品维护者。',X_CALLBACK_PORT_BUSY:'本机已有 X 授权正在进行，请回到原授权页面完成或取消。',X_AUTHORIZATION_IN_PROGRESS:'本机已有 X 授权正在进行，请在原页面完成或取消。',X_AUTHORIZATION_SESSION_MISMATCH:'此页面不是原授权会话，未取消其他授权。',X_AUTHORIZATION_ACCOUNT_MISMATCH:'重新授权返回的账号与所选账号不同，原绑定未替换。',X_AUTHORIZATION_DENIED:'你已在 X 页面取消授权。',X_AUTHORIZATION_SCOPES_INVALID:'X 未授予所需权限，请重新核对官方授权。',X_KEYCHAIN_ACCESS_REQUIRED:'请在系统钥匙串授权提示中处理访问请求。'};
  async function action(op,args={}){const current=generation,result=await call(op,args);if(!ready||current!==generation)throw new Error('X_VIEW_CLOSED');if(result?.isError||!result?.structuredContent)throw new Error(result?.structuredContent?.error||result?.content?.[0]?.text||'X_UNAVAILABLE');return result.structuredContent;}
  function stop(){if(timer!==null)clearTimeout(timer);timer=null;}
  function schedule(){stop();if(ready&&waiting&&document.visibilityState!=='hidden')timer=setTimeout(()=>{timer=null;requestRead();},1500);}
  function selected(){return connections.find(row=>row.connection_id===selectedAccount());}
  function updateBilling(){
   if(!billingPanel)return;
   const row=selected(),app=row?.application,target=row?.connection_id+':'+app?.selection;
   $('xConnectOwnApplication').hidden=!row;
   if(row)format().set($('xConnectOwnApplication'),row.application?.mode==='OWN_APP'?'管理自己的 X 开发者应用':'连接自己的 X 开发者应用');
   if(target===billingTarget)return;
   billingTarget=target;billingEpoch++;billingBusy=false;lastBillingCheck=null;
   $('xBillingBalance').hidden=true;$('xFreeGrants').hidden=true;$('xFreeGrants').replaceChildren();
   $('xRefreshBilling').disabled=app?.mode!=='OWN_APP';
   $('xOpenConsole').hidden=app?.mode!=='OWN_APP';
   format().set($('xBillingApplication'),app?.mode==='OWN_APP'?'应用 {0} · Client ID 尾号 {1}':app?'现有应用':'选择已绑定的 X 账号。',app?.name||'',app?.client_id_suffix||'');
   format().set($('xBillingStatus'),app?.mode==='OWN_APP'?'点击刷新，从 X 获取余额。':app?'切换到自己的开发者应用后可查看余额。':'');
  }
  async function readBilling(){
   updateBilling();
   const row=selected(),app=row?.application;
   if(!ready||billingBusy||app?.mode!=='OWN_APP')return;
   const epoch=billingEpoch;billingBusy=true;$('xRefreshBilling').disabled=true;
   const status=$('xBillingStatus');format().set(status,'正在读取 X 余额…');
   const isCurrent=()=>ready&&epoch===billingEpoch&&selectedAccount()===row.connection_id;
   try{
    const result=await action('BILLING',{connection_id:row.connection_id,expected_application:app.selection});
    if(!isCurrent())return;
    if(result.state!=='AVAILABLE'||result.connection_id!==row.connection_id||result.application!==app.selection||result.source!=='X_API'||result.currency!=='USD')throw new Error('X_APPLICATION_CHANGED');
    const money=new Intl.NumberFormat(document.documentElement.lang,{style:'currency',currency:'USD',maximumFractionDigits:6});
    for(const [id,key] of [['xTotalBalance','total_balance'],['xPrepaidBalance','prepaid_balance'],['xFreeBalance','free_balance']])$(id).textContent=money.format(result[key]);
    const grants=$('xFreeGrants');grants.replaceChildren();
    for(const grant of result.free_grants){
     const item=document.createElement('li');
     format().set(item,grant.expires_at?'免费额度 {0} · 到期 {1}':'免费额度 {0} · X 未提供到期日',
      money.format(grant.amount),grant.expires_at?new Date(grant.expires_at).toLocaleString(document.documentElement.lang):'');
     grants.append(item);
    }
    grants.hidden=!grants.childElementCount;$('xBillingBalance').hidden=false;
    lastBillingCheck=new Date(result.checked_at*1000).toLocaleString(document.documentElement.lang);
    format().set(status,'来源为 X API · {0}',lastBillingCheck);
   }catch(error){
    if(isCurrent()){
     $('xBillingBalance').hidden=true;$('xFreeGrants').hidden=true;
     const message=error.message==='X_HTTP_402'?'请在 X Developer Console 核对当前应用的余额和用量（402）。'
       :['X_HTTP_401','X_HTTP_403','X_REAUTHORIZATION_REQUIRED'].includes(error.message)
         ?'X 未授权读取余额，可在 X Developer Console 查看。':'暂时无法读取额度，请在 X Developer Console 查看。';
     format().set(status,message);
     if(lastBillingCheck){
      const previous=document.createElement('span');format().set(previous,'上次从 X API 读取 · {0}',lastBillingCheck);status.append(document.createElement('br'),previous);
     }
    }
   }finally{if(isCurrent()){billingBusy=false;$('xRefreshBilling').disabled=false;}}
  }
  async function load(){const value=await action('READ',authorizationHandle?{authorization_handle:authorizationHandle}:{});
   connections=value.connections||[];if($('xCallback'))$('xCallback').textContent=value.callback_uri||'';updateBilling();
   const status=value.authorization?.state;
   waiting=['AWAITING_AUTHORIZATION','EXCHANGING'].includes(status);
   $('xCancel').hidden=!waiting||target!==authorizationForm;
   if(!waiting)authorizationTarget=null;
   onStatusChange();
   if(waiting)lastBound='';
   if(status==='BOUND'){
    const bound=value.authorization?.result,cid=bound?.connection_id;
    if(target===authorizationForm){
     const username=handle(bound?.profile?.username);
     if(username)say('X 已核对并绑定：@{0}',false,username);
     else say('X 已授权并绑定：{0}',false,bound?.profile?.name||'');
    }
    if(cid&&cid!==lastBound){const current=generation;await onBound(cid,bindingSelection);if(ready&&current===generation)lastBound=cid;}
   }
   else if(target!==authorizationForm)say('');
   else if(['FAILED','DENIED'].includes(status)){
    const result=value.authorization?.result;
    const expected=handle(result?.expected_username)||handle(target?.username),returned=handle(result?.returned_username);
    if(result?.error==='X_AUTHORIZATION_ACCOUNT_MISMATCH'&&expected&&returned)
     say('目标是 @{0}，X 实际授权了 @{1}。原绑定已保留。请切换到目标账号，再发起一次授权。',true,expected,returned);
    else say(errors[result?.error]||'X 授权未完成，请核对官方应用、权限和 API 资格。',true);
   }
   else if(status==='AWAITING_AUTHORIZATION'&&target?.username)say('请在 X 授权页确认显示 @{0}，再点授权。',false,target.username);
   else if(status==='AWAITING_AUTHORIZATION')say('请在 X 官方页面核对账号并授权，完成后会自动显示账号。');
   else if(status==='EXCHANGING')say('正在与 X 核对授权结果，完成后自动刷新。');
   else if(status==='EXPIRED')say('本次授权已过期。请核对 X 登录账号，再从这里发起新的授权。',true);
   else if(status==='CANCELLED')say('已取消本次授权。');
   else say('');
  }
  async function run(fn){if(!ready||busy)return;const current=generation;busy=true;stop();buttons();try{await fn();}catch(e){if(ready&&current===generation){readAgain=false;say(errors[e.message]||'操作未完成（'+String(e.message).replace(/[^A-Z0-9_]/g,'').slice(0,80)+'），可手动检查连接状态。',true);}}finally{if(ready&&current===generation){busy=false;buttons();if(readAgain){readAgain=false;queueMicrotask(requestRead);}else schedule();}}}
  function requestRead(){if(!ready)return;if(busy){readAgain=true;return;}void run(load);}
  function returned(){if(ready&&document.visibilityState!=='hidden')requestRead();}
  function visibility(){if(document.visibilityState==='hidden')stop();else returned();}
  function closeAuthorization(){
   if(!target)return;
   target=null;filled=null;saved=null;
   stopSetup();appName.value='';clientId.value='';$('xAuthorization').hidden=true;
  }
  async function openAuthorization(existing=false, compact=false){
   const cid=existing?selectedAccount():null;
   if(existing&&!cid)return false;
   let requestToLoad;
   if(!target||target.cid!==cid){
    closeAuthorization();target={cid,selection:captureSelection(),loading:true,username:cid?handle(selected()?.profile?.username):''};
    requestToLoad=target;
    format().set($('xSaveApplicationStatus'),'');
    format().set($('xSetupStatus'),'');say('');
   }else if(target.loadFailed){
    target.loading=true;target.loadFailed=false;requestToLoad=target;
   }
   format().set($('xBindingTitle'),cid?'连接自己的 X 开发者应用':'绑定 X 账号');
   const user=target.username;
   if(cid)format().set($('xBindingTarget'),user?'当前账号：@{0}':'当前账号：{0}',user||cid);
   else format().set($('xBindingTarget'),'绑定新的 X 账号');
   format().set($('xAuthorizationHint'),target.username
    ?'授权目标：@{0}。请先在浏览器的 X 头像菜单切换到该账号。':'',target.username);
   $('xAuthorization').hidden=false;$('xManualSetup').open=!compact||!!clientId.value||!!appName.value;
   buttons();
   if($('xManualSetup').open)appName.focus();
   else if(!$('xSetupAssist').hidden&&!$('xSetupAssist').disabled)$('xSetupAssist').focus();
   else $('xManualSetup').querySelector('summary').focus();
   if(!requestToLoad)return !!target&&!target.loading;
   try{
    const value=await action('APP_DRAFT_READ',accountArgs(requestToLoad));
    if(target!==requestToLoad||!sameSetup(requestToLoad))return false;
    if(value.draft&&value.revision){
     saved=value;
     if(!appName.value&&!clientId.value){
      appName.value=value.draft.application_name;
      clientId.value=value.draft.client_id;
      $('xManualSetup').open=true;
     }
     showSaveStatus();
    }
    return true;
   }catch(_){
    if(target===requestToLoad){
     target.loadFailed=true;$('xManualSetup').open=true;
     format().set($('xSaveApplicationStatus'),'暂时无法读取已保存的应用资料，请重新打开应用设置。');
    }
    return false;
   }finally{
    if(target===requestToLoad){target.loading=false;buttons();}
   }
  }
  function showSaveStatus(){
   format().set($('xSaveApplicationStatus'),matchesSaved()
    ?'应用资料已保存。可单独前往 X 授权。'
    :appName.value||clientId.value?'应用资料尚未保存。':'');
  }
  async function saveApplication(event){
   if(!event.isTrusted||!target||target.loading||!sameSetup(target))return;
   const request=target;
   const input=fields();
   if(!input.application_name||!input.client_id)return;
   const userId=filled?.draft.client_id===input.client_id?filled.draft.user_id
    :saved?.draft.client_id===input.client_id?saved.draft.expected_user_id:null;
   await run(async()=>{
    $('xSaveApplication').setAttribute('aria-busy','true');
    format().set($('xSaveApplicationStatus'),'正在保存应用资料…');
    try{
     const value=await action('APP_DRAFT_SAVE',{...accountArgs(request),...input,...(userId?{expected_user_id:userId}:{})});
     if(target!==request||!sameSetup(request))return;
     if(!value.revision||!value.draft)throw new Error('X_APPLICATION_SAVE_UNCONFIRMED');
     saved=value;showSaveStatus();
    }catch(_){
     if(target===request)format().set($('xSaveApplicationStatus'),'未确认保存。可重试，或重新打开应用设置检查。');
    }finally{$('xSaveApplication').removeAttribute('aria-busy');}
   });
  }
  function openBilling(){billingPanel.open=true;billingPanel.querySelector('summary').focus();billingPanel.scrollIntoView({block:'nearest'});}
  function sameSetup(request){
   const current=captureSelection();
   return ready&&target?.cid===request.cid&&(!request.cid||selectedAccount()===request.cid)
     &&current?.epoch===request.selection?.epoch
     &&current?.intent===request.selection?.intent&&current?.platform===request.selection?.platform;
  }
  function stopSetup(message){
   clearTimeout(setupTimer);setupTimer=null;
   const previous=setup;setup=null;
   if(previous?.key)void call('SETUP_CANCEL',{panel_key:previous.key}).catch(()=>{});
   if(message)format().set($('xSetupStatus'),message);
   buttons();
  }
  function setupTargetChanged(){
   if(target&&!sameSetup(target)){closeAuthorization();return;}
   if(setup&&!sameSetup(setup))stopSetup('账号或页面已切换。请在目标账号重新发起，或粘贴公开 Client ID。');
   if(filled&&!sameSetup(filled)){
    if(clientId.value===filled.draft.client_id)clientId.value='';
    if(appName.value===filled.draft.application_name)appName.value='';
    filled=null;
    format().set($('xSetupStatus'),'账号或页面已切换。请在目标账号重新发起，或粘贴公开 Client ID。');
   }
  }
  function pollSetup(request){
   if(setup!==request)return;
   setupTimer=setTimeout(async()=>{
    if(setup!==request)return;
    if(!sameSetup(request)||Date.now()>=request.until){
     stopSetup('回填已结束。可粘贴公开 Client ID 继续。');return;
    }
    if(document.visibilityState==='hidden'){pollSetup(request);return;}
    try{
     const result=await action('SETUP_READ',{panel_key:request.key,...(request.cid?{connection_id:request.cid}:{})});
     if(setup!==request)return;
     if(!sameSetup(request)){setupTargetChanged();return;}
     if(result.state==='WAITING'){pollSetup(request);return;}
     if(result.state!=='READY'||!result.draft){stopSetup('回填已结束。可粘贴公开 Client ID 继续。');return;}
     if(appName.value||clientId.value){
      stopSetup('已保留表单内容。请核对后按需粘贴公开 Client ID。');return;
     }
     const draft=result.draft;
     if(request.cid&&request.cid!=='x-'+draft.user_id)throw new Error('X_AUTHORIZATION_ACCOUNT_MISMATCH');
     appName.value=draft.application_name;clientId.value=draft.client_id;
     $('xManualSetup').open=true;
     filled={...request,draft};
     showSaveStatus();
     stopSetup('应用资料已填好。请核对后保存。');
    }catch(_){if(setup===request)stopSetup('回填已结束。可粘贴公开 Client ID 继续。');}
   },1500);
  }
  async function startSetup(event){
    if(!event.isTrusted||!target||target.loading||!sameSetup(target)||setup)return;
    const cid=target.cid,status=$('xSetupStatus');
    if(appName.value||clientId.value){
     if(!filled)format().set(status,'已保留表单内容。请核对后按需粘贴公开 Client ID。');
     return;
    }
    if(!canSendChatRequest()){
     $('xManualSetup').open=true;
     format().set(status,'当前宿主无法发起聊天任务。可打开 X Developer Console 手动配置。');
     return;
    }
    if(waiting){
     format().set(status,errors.X_AUTHORIZATION_IN_PROGRESS);
     return;
    }
    const request={cid,selection:target.selection};setup=request;buttons();
    const accountHint=/^x-[0-9]{1,19}$/.test(cid)?'当前选中的已有 X 连接 ID 为 '+cid+'。':'当前没有指定已有连接。';
    format().set(status,'正在交给当前聊天…');
    let dispatchStarted=false;
    try{
     const opened=await action('SETUP_BEGIN',cid?{connection_id:cid}:{});
     request.key=opened.panel_key;request.until=Date.now()+opened.expires_in*1000;
     if(setup!==request||!sameSetup(request)){
      void call('SETUP_CANCEL',{panel_key:request.key}).catch(()=>{});return;
     }
     dispatchStarted=true;
     await sendChatRequest('请使用 $wechat-ecosystem:x-developer-app-setup，在 Codex 内置浏览器协助我创建或继续配置自己的 X Developer Native App。'+accountHint+
      '请使用插件提供的公开账号资料及回调配置，先核对官方 Developer Console 的当前账号，再帮我填写表单。一次性回填标识：'+opened.handoff);
     if(setup===request&&sameSetup(request)){
      format().set(status,'已交给当前聊天，可在聊天中继续。');pollSetup(request);
     }else if(setup===request)setupTargetChanged();
    }catch(error){
     if(setup!==request)return;
     $('xManualSetup').open=true;
     if(error.message==='HOST_MESSAGE_UNAVAILABLE'){
      stopSetup('当前宿主无法发起聊天任务。可打开 X Developer Console 手动配置。');
     }else{
      stopSetup(dispatchStarted?'暂未确认交接。请先查看聊天，再决定是否手动发起。':'暂时无法启动辅助设置。可重试或打开 X Developer Console。');
     }
    }
  }
  $('xSetupAssist').onclick=startSetup;
  async function authorize(reuseCurrent=false){await run(async()=>{
   if(!target||!sameSetup(target)||waiting||(reuseCurrent?!target.cid:!matchesSaved()))return;
   const request=target;
   const current=generation;
   const value=reuseCurrent?await action('AUTHORIZE',{expected_connection_id:request.cid})
     :await action('APP_DRAFT_AUTHORIZE',{...accountArgs(request),revision:saved.revision});
   bindingSelection=request.selection;lastBound='';authorizationHandle=value.authorization_handle;
   authorizationTarget=request.cid;authorizationForm=request;waiting=true;onStatusChange();
   if(target!==request||!sameSetup(request)){
    await call('CANCEL',{authorization_handle:authorizationHandle});await load();return;
   }
   const u=new URL(value.authorization_url);
   if(u.origin!=='https://x.com'||u.pathname!=='/i/oauth2/authorize')throw new Error('X_AUTHORIZATION_URL_INVALID');
   try{await openLink(value.authorization_url);}
   catch(error){await load();throw error;}
   if(!ready||generation!==current)throw new Error('X_VIEW_CLOSED');
   await load();
  });}
  if(billingPanel){
   $('xRefreshBilling').onclick=readBilling;
   $('xOpenConsole').onclick=async()=>{try{await openLink('https://console.x.com/');}catch(_){format().set($('xBillingStatus'),'当前宿主无法打开 X Developer Console。');}};
  }
  $('xBindingConsole').onclick=async()=>{
   const request=target;
   if(!request)return;
   try{
    await openLink('https://console.x.com/');
    if(target===request&&sameSetup(request)&&selected()?.profile?.username)
     format().set($('xSetupStatus'),'请在 X Developer Console 核对或切换到 @{0}。',selected().profile.username);
   }
   catch(_){if(target===request)format().set($('xSetupStatus'),'当前宿主无法打开 X Developer Console。');}
  };
  $('xSaveApplication').onclick=saveApplication;
  $('xAuthorize').onclick=event=>{if(event.isTrusted)void authorize();};$('xCheck').onclick=requestRead;
  $('xReauthorizeCurrent').onclick=event=>{if(event.isTrusted)void authorize(true);};
  $('xSwitchAccount').onclick=async event=>{
   const request=target;
   if(!event.isTrusted||!request?.cid||!sameSetup(request)||waiting)return;
   try{
    await openLink('https://x.com/home');
    if(target===request&&sameSetup(request)&&request.username)
     say('请在 X 左侧头像菜单切换到 @{0}，再回这里授权。',false,request.username);
   }catch(_){if(target===request)say('宿主未能打开 X。请在同一浏览器打开 X 并切换账号。',true);}
  };
  for(const input of [appName,clientId])input.addEventListener('input',()=>{showSaveStatus();buttons();});
  $('xCancel').onclick=()=>run(async()=>{await action('CANCEL',{authorization_handle:authorizationHandle});await load();});
  addEventListener('focus',returned);document.addEventListener('visibilitychange',visibility);
  function deactivate(){generation++;billingEpoch++;billingTarget=null;ready=false;busy=false;waiting=false;readAgain=false;stop();setupTargetChanged();capability.hidden=true;buttons();}
  return {async activate(){ready=true;capability.hidden=false;buttons();await run(load);},authorize,reauthorize:()=>authorize(true),openAuthorization,startSetup,openBilling,updateBilling,setupTargetChanged,closeAuthorization,deactivate,
   pendingAuthorization:cid=>authorizationTarget===cid&&waiting,
   dispose(){deactivate();removeEventListener('focus',returned);document.removeEventListener('visibilitychange',visibility);}};
 }
};
'''
