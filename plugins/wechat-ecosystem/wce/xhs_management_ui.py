"""App-only human login controls. No publication button or exposed QR secret."""
HTML='''<section id="xhsSettings" class="panel" data-platform-id="xiaohongshu" hidden>
<h2>小红书平台能力</h2><p class="help">本人扫码绑定 · 本号资料与笔记读取 · 原生图文发布 · 原笔记链接读回</p>
<p class="help">通过本机标准 Chrome 的正常页面操作，不代表已取得官方发布 API。Codex 负责标题、正文、图片和话题；这里不使用公众号 HTML。</p>
<div class="actions"><button id="xhsLogin" class="primary">扫码绑定小红书</button><button id="xhsReconnect">重新登录当前账号</button><button id="xhsCheck">检查登录结果</button><button id="xhsCancel" hidden>关闭登录窗口</button></div>
<p id="xhsStatus" class="notice" role="status">读取本机接入状态后可开始。</p>
<p class="help">登录在插件独立的 Chrome 窗口中完成，不读取你的其他浏览器账号。验证码、风控或协议确认请本人在官方页面处理。项目与 Skills 可保留本平台自己的创作偏好。</p></section>'''

SCRIPT=r'''
const OAXHSManagement={mount(call,onBound,selectedConnection=()=>null){
 const $=id=>document.getElementById(id);let ready=false,busy=false,waiting=false,timer=null,epoch=0,bindingId=null;
 const say=text=>{$('xhsStatus').textContent=text;};
 const buttons=()=>{$('xhsLogin').disabled=!ready||busy||waiting;$('xhsReconnect').disabled=!ready||busy||waiting||!selectedConnection();$('xhsCheck').disabled=!ready||busy;$('xhsCancel').disabled=!ready||busy;$('xhsCancel').hidden=!waiting;};
 function stop(){clearTimeout(timer);timer=null;}
 async function action(operation,args){const r=await call(operation,{...args,...(bindingId?{binding_id:bindingId}:{})});if(r?.isError||!r?.structuredContent)throw new Error('XHS_UNAVAILABLE');return r.structuredContent;}
 async function show(value){
  if(value.binding_id)bindingId=value.binding_id;
  if(value.state==='BOUND_IDLE'){waiting=false;say('已读取真实账号并完成绑定。');await onBound();}
  else if(value.state==='AWAITING_HUMAN_LOGIN'||value.state==='LOGIN_PENDING'||value.state==='LOGIN_PRESENT'){waiting=true;say('请在独立 Chrome 窗口扫码登录，完成后这里会自动刷新账号。');}
  else if(value.state==='HUMAN_ACTION_REQUIRED'){waiting=true;say('官方页面需要本人处理验证码或风控；请保留该窗口，处理后点击检查登录结果。');}
  else if(value.runtime_available===false){waiting=false;say('本机缺少可用的标准浏览器运行时。未安装依赖或更改现有账号。');}
  else{waiting=false;say(value.connections?.length?'本机账号已绑定；真实会话是否有效以本号读取结果为准。':'点击扫码绑定，在官方页面选择本人的账号。');}
 }
 async function run(operation,args={}){if(!ready||busy)return;const token=epoch;busy=true;stop();buttons();try{const value=await action(operation,args);if(ready&&token===epoch)await show(value);}catch(_){if(token===epoch){waiting=false;say('当前操作未能确认。未自动重新登录或提交图文，请检查本机运行时和官方页面。');}}finally{if(ready&&token===epoch){busy=false;buttons();if(waiting&&document.visibilityState!=='hidden')timer=setTimeout(()=>run('POLL'),2000);}}}
 $('xhsLogin').onclick=()=>run('BEGIN');$('xhsReconnect').onclick=()=>{const cid=selectedConnection();if(cid)run('BEGIN',{connection_id:cid});};$('xhsCheck').onclick=()=>run(waiting?'POLL':'READ');$('xhsCancel').onclick=()=>run('CANCEL');
 function deactivate(){epoch++;ready=false;busy=false;stop();buttons();}
 return {activate(){ready=true;return run('READ');},begin(){ready=true;return run('BEGIN');},deactivate,dispose:deactivate};
}};
'''
