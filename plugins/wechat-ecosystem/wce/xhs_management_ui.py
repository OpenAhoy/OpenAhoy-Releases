"""App-only human login controls. No publication button or exposed QR secret."""
from .management_locale import FALLBACK

HTML='''<section id="xhsSettings" class="panel" data-platform-id="xiaohongshu" hidden>
<h2>登录状态</h2>
<p id="xhsStatus" class="notice" role="status">读取本机接入状态后可开始。</p>
<div class="actions"><button id="xhsReconnect" hidden>重新登录当前账号</button><button id="xhsCheck" hidden>检查登录结果</button><button id="xhsCancel" hidden>关闭登录窗口</button></div>
<details><summary>小红书平台能力</summary><p class="help">本人扫码绑定 · 本号资料与笔记读取 · 原生图文发布 · 原笔记链接读回</p>
<p class="help">通过本机标准 Chrome 的正常页面操作，不代表已取得官方发布 API。Codex 负责标题、正文、图片和话题；这里不使用公众号 HTML。</p>
<p class="help">登录在插件独立的 Chrome 窗口中完成，不读取你的其他浏览器账号。验证码、风控或协议确认请本人在官方页面处理。项目与 Skills 可保留本平台自己的创作偏好。</p></details></section>'''

SCRIPT=FALLBACK + r'''
const OAXHSManagement={mount(call,onBound,selectedConnection=()=>null,onState=()=>{}){
 const $=id=>document.getElementById(id);let ready=false,busy=false,waiting=false,needsCheck=false,timer=null,epoch=0,bindingId=null;
 const say=text=>(globalThis.OAUI||globalThis.OAPlainUI).set($('xhsStatus'),text);
 const canBegin=()=>ready&&!busy&&!waiting;
 const buttons=()=>{$('xhsReconnect').hidden=waiting||!selectedConnection();$('xhsReconnect').disabled=!canBegin();$('xhsCheck').hidden=!waiting&&!needsCheck;$('xhsCheck').disabled=!ready||busy;$('xhsCancel').disabled=!ready||busy;$('xhsCancel').hidden=!waiting;onState();};
 function stop(){clearTimeout(timer);timer=null;}
 async function action(operation,args){const r=await call(operation,{...args,...(bindingId?{binding_id:bindingId}:{})});if(r?.isError||!r?.structuredContent)throw new Error('XHS_UNAVAILABLE');return r.structuredContent;}
 async function show(value){
  if(value.binding_id)bindingId=value.binding_id;
  if(value.state==='BOUND_IDLE'){waiting=false;say('已读取真实账号并完成绑定。');await onBound();}
  else if(value.state==='AWAITING_HUMAN_LOGIN'||value.state==='LOGIN_PENDING'||value.state==='LOGIN_PRESENT'){waiting=true;say('请在独立 Chrome 窗口扫码登录，完成后这里会自动刷新账号。');}
  else if(value.state==='HUMAN_ACTION_REQUIRED'){waiting=true;say('请在小红书页面完成验证，再检查登录结果。');}
  else if(value.runtime_available===false){waiting=false;say('本机缺少可用的标准浏览器运行时。未安装依赖或更改现有账号。');}
  else{waiting=false;say(value.connections?.length?'已绑定账号。登录失效时可重新登录。':'请点击上方按钮扫码绑定。');}
 }
 async function run(operation,args={}){if(!ready||busy)return;const token=epoch;busy=true;stop();buttons();try{const value=await action(operation,args);if(ready&&token===epoch){needsCheck=false;await show(value);}}catch(_){if(token===epoch){waiting=false;needsCheck=true;say('未能确认登录状态，请检查登录结果。');}}finally{if(ready&&token===epoch){busy=false;buttons();if(waiting&&document.visibilityState!=='hidden')timer=setTimeout(()=>run('POLL'),2000);}}}
 $('xhsReconnect').onclick=()=>{const cid=selectedConnection();if(cid&&canBegin())run('BEGIN',{connection_id:cid});};$('xhsCheck').onclick=()=>run(waiting?'POLL':'READ');$('xhsCancel').onclick=()=>run('CANCEL');
 function deactivate(){epoch++;ready=false;busy=false;stop();buttons();}
 return {activate(){ready=true;return run('READ');},begin(){if(canBegin())return run('BEGIN');},canBegin,updateControls:buttons,deactivate,dispose:deactivate};
}};
'''
