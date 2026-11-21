"""Optional walkthrough over the existing management navigation."""

HTML = '''
<section id="workflowGuide" aria-labelledby="guideTitle" hidden>
 <header class="og-header">
  <div><p id="guideProgress"></p><h2 id="guideTitle" tabindex="-1"></h2></div>
  <button type="button" id="guideExit">退出指导</button>
 </header>
 <p id="guideInstruction"></p>
 <div class="og-scope">
  <p id="guideWork" role="status"></p>
  <button type="button" id="guideBind" hidden>关联当前作品</button>
 </div>
 <div id="guidePublish" hidden>
  <label for="guidePlatform">发布平台</label>
  <select id="guidePlatform">
   <option value="">选择平台</option>
   <option value="wechat_official_account">公众号</option>
   <option value="x">X</option>
   <option value="xiaohongshu">小红书</option>
  </select>
  <p id="guideAccount" role="status"></p>
  <p id="guidePublishHint"></p>
  <p id="guideReceipt">尚无可核对的本作品发布回执。请沿原发布流程按原操作编号查询结果。</p>
 </div>
 <p id="guideNavigationStatus" role="status" hidden></p>
 <p id="guideRequirement" role="status"></p>
 <footer class="og-actions">
  <button type="button" id="guideLocate"></button>
  <button type="button" id="guideLocateImages" hidden>定位镜头选图</button>
  <label id="guideReadLabel" hidden><input type="checkbox" id="guideRead"> <span>本步已阅读</span></label>
  <div class="og-travel">
   <button type="button" id="guideRestart">重新开始</button>
   <button type="button" id="guidePrevious">上一步</button>
   <button type="button" id="guideSkip">先跳过</button>
   <button type="button" id="guideNext" class="primary">下一步</button>
  </div>
 </footer>
</section>
'''

STYLE = '''
#workflowGuide[hidden],#workflowGuide [hidden]{display:none!important}
body.oa-native #workflowGuide{
 flex:none;min-width:0;box-sizing:border-box;width:100%;margin:0 0 10px;padding:10px 12px;
 border:1px solid var(--line);border-inline-start:3px solid var(--accent);border-radius:10px;
 background:var(--surface);overflow:auto;max-height:min(65dvh,22rem);overflow-wrap:anywhere
}
#workflowGuide :is(h2,p){margin:0}
#workflowGuide h2{font-size:16px}
#workflowGuide p{margin-block:4px}
#workflowGuide .og-header,#workflowGuide .og-scope,#workflowGuide .og-actions,#workflowGuide .og-travel{
 display:flex;align-items:center;flex-wrap:wrap;gap:4px 8px
}
#workflowGuide .og-header{justify-content:space-between}
#workflowGuide .og-travel{margin-inline-start:auto}
#workflowGuide :is(#guideProgress,#guideWork,#guideAccount,#guideReceipt,#guideNavigationStatus,#guideRequirement){color:var(--muted);font-size:12px}
#workflowGuide #guidePublish{border-block-start:1px solid var(--line);padding-block:6px 4px}
#workflowGuide #guidePlatform{width:auto;max-width:100%;min-width:0;margin:0 0 0 5px}
#workflowGuide .og-actions label{display:inline-flex;align-items:center;gap:4px}
#workflowGuide input[type=checkbox]{width:auto;min-height:0;margin:0}
#workflowGuide button{min-height:30px}
#openWorkflowGuide{white-space:nowrap}
@media(max-width:560px){
 #workflowGuide .og-travel{margin-inline-start:0}
}
'''

SCRIPT = r'''
function OAWorkflowGuide(navigation){
 const $=id=>document.getElementById(id);
 const entry=$('openWorkflowGuide'),panel=$('workflowGuide'),title=$('guideTitle');
 const platform=$('guidePlatform'),read=$('guideRead'),locate=$('guideLocate'),bind=$('guideBind');
 const key='openahoy.workflow-guide.v1';
 const steps=[
   ['在 Codex 开始创作','打开导演台，在原按钮发起创作。用当前聊天的真实项目，等待作品读回后再关联。','定位创作按钮','jiusera-monitor'],
   ['导演台','选择作品并查看监看、镜头和任务。回执在原任务里查看。','打开监看','jiusera-monitor'],
   ['工作画布','打开当前作品的画布，检查场次、镜头和修订。需要调整时使用原编辑按钮。','打开工作画布','jiusera-canvas'],
   ['资产库','查看已登记的形象与媒体。在镜头中选图并保存修订后，核对该修订锁定的版本。','打开资产库','characters'],
   ['发布与读回','选择平台并核对当前账号、内容和草稿。确认后在原流程操作，并按原回执读回结果。','查看平台与账号','']
 ];
 const platformInstructions={
   wechat_official_account:'打开公众号后台或在 Codex 核对该号的草稿。按原发表回执查询状态和文章链接。',
   x:'核对当前 X 账号、待发内容和已有文章草稿。沿原发布流程提交后，使用同一编号读回帖子。',
   xiaohongshu:'核对小红书账号、标题、正文和图片。沿原发布流程提交后，读回该次操作的笔记链接。'
 };
 const initially=()=>({step:0,read:[],scope:null,platform:''});
 const scoped=value=>value&&typeof value.project==='string'&&typeof value.work==='string'
   &&/^[a-f0-9]{32}$/.test(value.project)&&/^[a-f0-9]{32}$/.test(value.work);
 function saved(){
   try{
     const data=JSON.parse(localStorage.getItem(key));
     if(!data||!Number.isInteger(data.step)||!steps[data.step])return null;
     return {step:data.step,read:steps.map((_,i)=>data.read?.[i]===true),
       scope:scoped(data.scope)?{project:data.scope.project,work:data.scope.work}:null,
       platform:Object.hasOwn(platformInstructions,data.platform)?data.platform:''};
   }catch(_){return null;}
 }
 let state=saved(),active=false,navEpoch=0,lastPaint='',reviewedAccount=null;
 function save(){
   try{if(state)localStorage.setItem(key,JSON.stringify(state));else localStorage.removeItem(key);}catch(_){}
 }
 function same(work){return work&&state.scope&&work.project===state.scope.project&&work.work===state.scope.work;}
 function account(page){return state.platform&&page.platform===state.platform?page.account:null;}
 function requirement(page){
   const matched=same(page.work);
   switch(state.step){
     case 0:return matched?'':'读回并关联当前作品后，可以继续。';
     case 1:return !matched?'请先打开并读回已关联的作品。':
       state.read[1]?'':'查看本作品的监看后，请勾选「本步已阅读」。';
     case 2:return !matched?'请先打开并读回已关联的作品。':
       page.work.shot?'':page.work.shots?'请选择并读回本作品的镜头。':'请在画布中新增并读回本作品的镜头。';
     case 3:return !matched?'请先打开并读回已关联的作品。':
       page.work.asset?'':'在当前镜头选图并保存，待修订中的锁定版本读回后继续。';
     case 4:return !account(page)?'请选择发布平台并核对当前账号。':
       reviewedAccount===account(page).id?'':'核对账号并查看发布说明后，请勾选「本步已阅读」。';
   }
 }
 function render(){
   const page=active?navigation.status():null;
   if(active&&state.step===4&&reviewedAccount!==account(page)?.id)reviewedAccount=null;
   const paint=JSON.stringify([active,state,page,reviewedAccount]);
   if(paint===lastPaint)return;
   lastPaint=paint;
   entry.setAttribute('aria-expanded',String(active));
   OAUI.set(entry,active?'指导模式':state?'继续指导':'指导模式');
   panel.hidden=!active;
   if(!active)return;
   const work=page.work,matched=same(work);
   const [heading,instruction,action]=steps[state.step],last=state.step===steps.length-1;
   OAUI.set(title,heading);OAUI.set($('guideProgress'),'指导第 {0} 步，共 {1} 步',state.step+1,steps.length);
   OAUI.set($('guideInstruction'),instruction);
   OAUI.set(locate,action);
   locate.disabled=last&&!state.platform;
   $('guideLocateImages').hidden=state.step!==3||!matched||!work.shot;
   bind.hidden=last||!scoped(work)||!!matched;
   OAUI.set(bind,state.scope?'改用当前作品并重新开始':'关联当前作品');
   if(matched){
     const status=state.step===3&&work.asset?
       OAUI.message('已读回当前修订的锁定图片版本 {0}。',work.asset):
       state.step===3?OAUI.message('当前修订暂无已读回的锁定图片版本。'):
       OAUI.message('已读回 {0} 个场次、{1} 个镜头。',work.scenes,work.shots);
     OAUI.set($('guideWork'),'已核对作品「{0}」。{1}',work.title,status);
   }else{
     OAUI.set($('guideWork'),state.scope?(work?'当前是其他作品。请返回原作品，或关联当前作品重新开始。':
       last?'已保留指导中的作品关联。请分别核对平台账号和发布回执。':'已保留原作品关联，等待重新读回。'):
       '选择并读回作品后，可将指导进度关联到该作品。');
   }
   $('guidePublish').hidden=!last;platform.value=state.platform;
   if(last){
     OAUI.set($('guidePublishHint'),platformInstructions[state.platform]||'');
     const current=account(page);
     if(current){
       OAUI.set($('guideAccount'),'平台当前账号「{0}」 · {1}。',current.label,
         OAUI.message(current.state));
     }else{
       OAUI.set($('guideAccount'),state.platform?'此步骤尚未核对所选平台的账号。':'');
     }
   }
   $('guideReadLabel').hidden=state.step!==1&&!last;
   read.disabled=last?!account(page):!matched;
   read.checked=last?!!reviewedAccount:!!matched&&state.read[1]===true;
   $('guidePrevious').disabled=state.step===0;
   const reason=requirement(page);
   OAUI.set($('guideRequirement'),reason);
   $('guideRequirement').hidden=!reason;
   $('guideNext').disabled=!!reason;
   OAUI.set($('guideNext'),last?'结束指导':'下一步');
   $('guideSkip').hidden=!reason;
   OAUI.set($('guideSkip'),last?'跳过并结束':'先跳过');
 }
 function feedback(message=''){
   const status=$('guideNavigationStatus');
   OAUI.set(status,message);status.hidden=!message;
 }
 function step(index){
   navEpoch++;state.step=index;save();feedback();render();title.focus();
 }
 function close(finished=false){
   navEpoch++;active=false;reviewedAccount=null;
   if(finished){state=null;save();}
   feedback();render();entry.focus();
 }
 entry.onclick=()=>{
   if(active){title.focus();return;}
   state=state||initially();active=true;save();render();title.focus();
 };
 $('guideExit').onclick=()=>close();
 $('guideRestart').onclick=()=>{state=initially();reviewedAccount=null;step(0);};
 $('guidePrevious').onclick=()=>{if(state.step>0)step(state.step-1);};
 function advance(){if(state.step===steps.length-1)close(true);else step(state.step+1);}
 $('guideNext').onclick=()=>{if(active&&!requirement(navigation.status()))advance();};
 $('guideSkip').onclick=()=>{if(active)advance();};
 read.onchange=()=>{
   if(!active)return;
   const page=navigation.status();
   if(state.step===1&&same(page.work)){state.read[1]=read.checked;save();}
   if(state.step===4)reviewedAccount=read.checked?account(page)?.id||null:null;
   lastPaint='';render();
 };
 platform.onchange=()=>{navEpoch++;reviewedAccount=null;state.platform=platform.value;save();feedback();render();};
 bind.onclick=()=>{
   const work=navigation.status().work;
   if(!scoped(work)||same(work))return;
   if(state.scope){state=initially();reviewedAccount=null;}
   state.scope={project:work.project,work:work.work};
   save();render();title.focus();
 };
 async function locateStep(target,step,tab){
   const epoch=++navEpoch;
   if(!target)return;
   feedback();
   const current=()=>active&&epoch===navEpoch;
   try{
     if(!await navigation.locate(target,step,current,state.scope,tab)&&current())
       feedback('当前页面或管理连接暂不可用。可以继续阅读、稍后重试或退出指导。');
   }catch(_){
     if(current())feedback('当前页面或管理连接暂不可用。可以继续阅读、稍后重试或退出指导。');
   }
 }
 locate.onclick=()=>locateStep(steps[state.step][3]||state.platform,state.step);
 $('guideLocateImages').onclick=()=>locateStep('jiusera-canvas',2,'images');
 render();
 return {render};
}
'''
