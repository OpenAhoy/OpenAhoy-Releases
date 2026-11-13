"""X adapter for the accepted native management workspace."""
from .x_schedule_ui import HTML as SCHEDULE_HTML
from .x_operating_ui import HTML as OPERATING_HTML

HTML = '''<style>
.oa-x-capabilities{flex:none;padding:12px 14px;margin-bottom:12px;border:1px solid var(--line,#dce4e1);border-radius:12px;background:var(--surface,#fff);font-size:12px;line-height:1.5}
.oa-x-capabilities h2{font-size:14px;margin:0 0 8px}.oa-x-features{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:8px;margin:0;padding:0;list-style:none}.oa-x-features li{min-width:0;padding:7px 9px;border-radius:7px;background:var(--bg,#f6f8fa)}.oa-x-features strong,.oa-x-features span{display:block}.oa-x-features span,.oa-x-capabilities p{color:var(--muted,#61746c)}.oa-x-capabilities p{margin:8px 0 0}.oa-native #settingsPanel:has(#xSettings:not([hidden])){overflow:auto}
@media(max-width:560px){.oa-x-features{grid-template-columns:repeat(2,minmax(0,1fr))}}
</style><section id="xCapabilities" class="oa-x-capabilities" aria-label="X 平台能力" hidden>
<h2>X 平台能力</h2><ul class="oa-x-features"><li><strong>账号与帖子</strong><span>授权、资料、原文上下文</span></li><li><strong>主动发现</strong><span>人物、主题、交友、指定回复</span></li><li><strong>文字、图片、GIF 与视频</strong><span>官方上传、异步处理、发帖与独立读回；实际格式和权益由 X 核验</span></li><li><strong>按原帖回复</strong><span>官方条件允许时执行、关系读回</span></li></ul>
<p>以上为已实现接口；实际可用性以本号授权、宿主工具和 X 返回为准。</p><p>“项目与 Skills”可设置主题、创作方法与回复风格；保存不自动开启互动。X 官方不允许自动点赞；AI 自动回复须事先获得 X 书面批准。</p></section>
<section id="xSettings" class="panel" data-platform-id="x" hidden>
<section aria-label="X 内容生产与发布" class="oa-x-production"><h3>内容生产与发布</h3>
<p id="xProductionAccount" class="help">选择已绑定的 X 账号。</p>
<div id="xProductionPreferences" class="oa-x-production-preferences"></div>
<p id="xProductionConfigStatus" class="help" role="status"></p>
<div class="actions"><button id="xProduceNow" class="primary" disabled>立即生产并发布</button><button id="xProductionResult" hidden>查看原任务结果</button><button id="xProductionSchedule" disabled>配置定时生产发布</button><button id="xProductionEdit">编辑内容配置</button></div>
<p id="xProductionStatus" class="notice" role="status">一次启动由当前 Codex 完成新文字、新配图、公开发布及真实链接读回。</p>
<p class="help">使用已保存的本号配置。未关联项目或选填项为空时沿默认方法；保存配置不会启动任务。发送后请查看当前聊天，重新打开本页不代表原任务已结束。</p></section>
<details><summary>账号授权</summary><h3>绑定 X 账号</h3><p class="help">使用 OpenAhoy 连接你自己的 X 账号。前往 X 官方页面登录并授权，名称和头像会自动读取，无需注册开发者账号或填写密钥。</p>
<div class="actions"><button id="xAuthorize" class="primary">绑定 X 账号</button><button id="xCheck">检查授权结果</button><button id="xCancel" hidden>取消本次授权</button></div>
<p id="xStatus" class="notice" role="status">正在读取 X 设置…</p>
<p class="help">仅请求资料、帖子读取、图片上传、发帖及刷新授权。可在 X 官方设置中撤销授权；服务可用性受 X 平台权限与额度影响。</p></details></section>'''
HTML = HTML.replace('<details><summary>账号授权', SCHEDULE_HTML + '<details><summary>账号授权')
HTML = HTML.replace('<details id="xSchedulePanel"', OPERATING_HTML + '<details id="xSchedulePanel"')

SCRIPT = r'''
window.OAXManagement = {
 mount(call,openLink,onBound,{captureSelection=()=>null}={}){
  const $=id=>document.getElementById(id);let busy=false,ready=false,generation=0,timer=null,waiting=false,readAgain=false,lastBound='',authorizationHandle=null,bindingSelection=null;
  const capability=$('xCapabilities');
  const say=(text,error=false)=>{$('xStatus').textContent=text;$('xStatus').className='notice'+(error?' error':'');};
  const buttons=()=>{for(const id of ['xAuthorize','xCheck','xCancel'])$(id).disabled=!ready||busy;};
  const errors={X_APPLICATION_REQUIRED:'OpenAhoy 的 X 接入暂未就绪，请联系产品维护者。',X_CALLBACK_PORT_BUSY:'本机已有 X 授权正在进行，请回到原授权页面完成或取消。',X_AUTHORIZATION_IN_PROGRESS:'本机已有 X 授权正在进行，请在原页面完成或取消。',X_AUTHORIZATION_SESSION_MISMATCH:'此页面不是原授权会话，未取消其他授权。',X_AUTHORIZATION_ACCOUNT_MISMATCH:'重新授权返回的账号与所选账号不同，原绑定未替换。',X_AUTHORIZATION_DENIED:'你已在 X 页面取消授权。',X_AUTHORIZATION_SCOPES_INVALID:'X 未授予所需权限，请重新核对官方授权。',X_KEYCHAIN_ACCESS_REQUIRED:'请在系统钥匙串授权提示中处理访问请求。'};
  async function action(op,args={}){const current=generation,result=await call(op,args);if(!ready||current!==generation)throw new Error('X_VIEW_CLOSED');if(result?.isError||!result?.structuredContent)throw new Error(result?.structuredContent?.error||result?.content?.[0]?.text||'X_UNAVAILABLE');return result.structuredContent;}
  function stop(){if(timer!==null)clearTimeout(timer);timer=null;}
  function schedule(){stop();if(ready&&waiting&&document.visibilityState!=='hidden')timer=setTimeout(()=>{timer=null;requestRead();},1500);}
  async function load(){const value=await action('READ',authorizationHandle?{authorization_handle:authorizationHandle}:{});
   const status=value.authorization?.state;$('xCancel').hidden=!['AWAITING_AUTHORIZATION','EXCHANGING'].includes(status);
   waiting=['AWAITING_AUTHORIZATION','EXCHANGING'].includes(status);
   if(waiting)lastBound='';
   if(status==='BOUND'){
    const bound=value.authorization?.result,cid=bound?.connection_id;
    say('X 已授权并绑定：'+(bound?.profile?.name||''));
    if(cid&&cid!==lastBound){const current=generation;await onBound(cid,bindingSelection);if(ready&&current===generation)lastBound=cid;}
   }
   else if(['FAILED','DENIED'].includes(status))say(errors[value.authorization?.result?.error]||'X 授权未完成，请核对官方应用、权限和 API 资格。',true);
   else if(status==='AWAITING_AUTHORIZATION')say('请在 X 官方页面核对账号并授权，完成后会自动显示账号。');
   else if(status==='EXCHANGING')say('正在与 X 核对授权结果，完成后自动刷新。');
   else if(status==='EXPIRED')say('本次授权已过期，未自动重新发起授权。',true);
   else if(value.connections?.length)say('已绑定 '+value.connections.length+' 个 X 账号，可继续添加账号。');
   else say(value.client_id?'点击“绑定 X 账号”，在 X 官方页面完成授权。':'OpenAhoy 的 X 接入暂未配置，请联系产品维护者。');
  }
  async function run(fn){if(!ready||busy)return;const current=generation;busy=true;stop();buttons();try{await fn();}catch(e){if(ready&&current===generation){waiting=false;readAgain=false;say(errors[e.message]||'操作未完成（'+String(e.message).replace(/[^A-Z0-9_]/g,'').slice(0,80)+'），可手动检查连接状态。',true);}}finally{if(ready&&current===generation){busy=false;buttons();if(readAgain){readAgain=false;queueMicrotask(requestRead);}else schedule();}}}
  function requestRead(){if(!ready)return;if(busy){readAgain=true;return;}void run(load);}
  function returned(){if(ready&&document.visibilityState!=='hidden')requestRead();}
  function visibility(){if(document.visibilityState==='hidden')stop();else returned();}
  async function authorize(){await run(async()=>{const selection=captureSelection(),current=generation,value=await action('AUTHORIZE');bindingSelection=selection;lastBound='';authorizationHandle=value.authorization_handle;const u=new URL(value.authorization_url);if(u.origin!=='https://x.com'||u.pathname!=='/i/oauth2/authorize')throw new Error('X_AUTHORIZATION_URL_INVALID');await openLink(value.authorization_url);if(!ready||generation!==current)throw new Error('X_VIEW_CLOSED');await load();});}
  $('xAuthorize').onclick=authorize;$('xCheck').onclick=requestRead;
  $('xCancel').onclick=()=>run(async()=>{await action('CANCEL',{authorization_handle:authorizationHandle});await load();});
  addEventListener('focus',returned);document.addEventListener('visibilitychange',visibility);
  function deactivate(){generation++;ready=false;busy=false;waiting=false;readAgain=false;stop();capability.hidden=true;buttons();}
  return {async activate(){ready=true;capability.hidden=false;buttons();await run(load);},authorize,deactivate,
   dispose(){deactivate();removeEventListener('focus',returned);document.removeEventListener('visibilitychange',visibility);}};
 }
};
'''
