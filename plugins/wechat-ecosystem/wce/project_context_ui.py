"""Embedded project/Skill preferences. Sources render as text, never HTML."""
from .management_locale import FALLBACK

HTML = r'''
<section id="projectContextPanel" class="panel" hidden aria-label="项目与 Skills">
<div class="project-toolbar"><div><h3>项目与 Skills</h3><p class="help">关联已有项目，复用原规则与创作方法。源文件保留；本页设置作为补充偏好。</p></div>
<div class="actions"><button id="projectXSchedule" hidden>配置定时生产发布</button><button id="projectInitialize">初始化当前项目</button><button id="projectLink">只关联已有规则</button><button id="projectReload">刷新</button></div></div>
<p id="projectInitializationStatus" class="help" role="status">初始化由当前 Codex 确认真实工作区，写入项目生产规范；个人偏好保留，不启用发布或定时。</p>
<p id="projectNotice" class="notice" role="status" aria-live="polite"></p>
<div id="projectForm" class="project-body">
<div class="project-grid"><div class="oa-scope-tabs" role="group" aria-label="设置范围"><button id="projectAccountScope" type="button">本账号</button><button id="projectDefaultScope" type="button">平台默认</button><select id="projectScope" hidden aria-label="内部设置范围"></select></div>
<label>关联项目<select id="projectChoice"><option value="">沿用现有工作流程</option></select></label></div>
<label id="projectInheritLabel"><input type="checkbox" id="projectInherit">继承平台默认的项目与偏好</label>
<p id="projectPath" class="help"></p><p id="projectOrigin" class="help"></p>
<div class="project-editor-columns"><div class="project-methods"><section><h3>选用的 Skills</h3><p class="help">OpenAhoy 平台 Skill 始终配合执行。项目 Skill 可多选，按勾选顺序采用。</p><div id="projectSkills" class="project-skills"></div></section>
<section><h3>规则来源</h3><p class="help">AGENTS 保留职责与任务约定；此处可查看原文和版本。</p><div id="projectSources" class="project-sources"></div></section>
<details id="projectSourcePreview"><summary>查看源文件</summary><p id="projectSourceInfo" class="help"></p><pre id="projectSourceText" class="project-source-text"></pre><div class="actions"><button id="projectSourcePrev">上一段</button><span id="projectSourcePage" class="help"></span><button id="projectSourceNext">下一段</button></div></details>
 </div><div class="project-preferences"><label>补充偏好<select id="projectPreference"><option value="topics">关注主题</option><option value="selection">选题与筛选方式</option><option value="writing">写作与表达</option><option value="reply_style">回复风格</option><option value="notes">其他约定</option></select></label>
<textarea id="projectPreferenceText" rows="4" placeholder="填写本平台或本账号的补充要求，不填写密钥。"></textarea>
<details id="projectXDiscovery" hidden><summary>X 内容生产与发布</summary><p class="help">关注主题决定写什么；选题与筛选方式说明信源、时效和取舍；写作与表达可填写文案语气、语言、配图与构图要求。Codex 读取本号生效配置及适用 AGENTS/Skills，自主完成新文、新图、原生发布和真实链接读回。选填项为空不阻断正常创作。</p><p class="help">立即任务从 X 平台设置页启动。定时只使用 Codex 的任务能力，须明确频率和时区后才建立；保存规则不等于启用任务。本流程不执行回复、点赞、关注或私信。</p></details>
<details><summary>已保存的生效内容</summary><div id="projectEffective" class="help"></div></details>
<p class="help">模型跟随当前 Codex 聊天或任务。保存偏好不会新建任务、开启自动回复或执行发布。</p></div></div></div>
<div class="actions project-save"><button id="projectSave" class="primary">保存设置</button><button id="projectQuery" hidden>查询原保存结果</button><button id="projectDiscard">放弃本页修改</button><button id="projectRefreshSources">刷新来源版本</button></div>
</section>
'''

STYLE = r'''
.project-toolbar{display:flex;align-items:flex-start;justify-content:space-between;gap:12px}.project-toolbar h3{margin:0}.project-toolbar .help{margin:4px 0 0}.project-grid{display:grid;grid-template-columns:1fr 1fr;gap:18px}.project-body{min-height:0;overflow:auto;padding:0 3px 8px}.project-source-text{white-space:pre-wrap;overflow-wrap:anywhere;font:12px/1.65 ui-monospace,monospace;max-height:240px;overflow:auto;background:var(--soft);border-radius:8px;padding:12px}.project-skills label{display:flex;align-items:flex-start;font-weight:400;margin:6px 0}.project-skills .help{display:block;margin:2px 0}.project-sources button{justify-content:flex-start;text-align:left;white-space:normal;font-size:12px;margin:3px 4px 3px 0;overflow-wrap:anywhere}.project-save{padding-top:12px;border-top:1px solid var(--line);margin-top:8px}.project-stale{color:#a14e30}.oa-context-tabs{margin:0 0 10px;flex:none}.oa-context-tabs button[aria-selected=true]{background:var(--tint);color:var(--accent);border-color:#cfddf7}
.project-editor-columns{display:grid;grid-template-columns:1fr 1fr;gap:24px}.project-preferences textarea{min-height:150px}.project-preferences>label{margin-top:16px}.project-body>#projectPath,.project-body>#projectOrigin{margin:3px 0;overflow-wrap:anywhere}
.oa-x-production{margin-bottom:16px}.oa-x-production-preferences{display:grid;grid-template-columns:1fr 1fr;gap:6px 18px;margin:8px 0}.oa-x-production-preferences p{margin:0;white-space:pre-wrap;overflow-wrap:anywhere;font-size:12px;max-height:90px;overflow:auto}.oa-x-production-preferences strong{display:block;margin-bottom:3px}.oa-x-production .actions{flex-wrap:wrap}
@media(min-width:800px) and (min-height:600px){.oa-native #projectContextPanel{display:flex;flex:1;min-height:0;flex-direction:column;overflow:hidden}.project-toolbar,.project-save{flex:none}.project-body{flex:1}}
@media(min-width:800px){.oa-native:has(#projectContextPanel:not([hidden])) #accountPanel{padding:8px 12px;max-height:110px}.oa-native:has(#projectContextPanel:not([hidden])) .oa-account-tools,.oa-native:has(#projectContextPanel:not([hidden])) #wechatBackendHelp{display:none}.oa-native:has(#projectContextPanel:not([hidden])) #xCapabilities{padding:8px 12px}.oa-native:has(#projectContextPanel:not([hidden])) #xCapabilities h2{margin:0 0 4px}.oa-native:has(#projectContextPanel:not([hidden])) #xCapabilities p{margin:4px 0;font-size:11px}.oa-native:has(#projectContextPanel:not([hidden])) .oa-x-features li{padding:3px 7px}.oa-native:has(#projectContextPanel:not([hidden])) #accountPanel .oa-list-head{margin-bottom:2px}.oa-native:has(#projectContextPanel:not([hidden])) #accountPanel .account{padding:4px 8px}.oa-native:has(#projectContextPanel:not([hidden])) #accountPanel .account .help{display:none}}
@media(max-width:799px){.project-grid,.project-editor-columns{grid-template-columns:1fr;gap:4px}.project-toolbar{flex-direction:column}.project-save button{flex:1}.project-source-text{max-height:200px}}
'''

SCRIPT = FALLBACK + r'''
const OAProjectContext=(()=>{
 'use strict';const $=id=>document.getElementById(id),clone=v=>JSON.parse(JSON.stringify(v));
 const ui=globalThis.OAUI||globalThis.OAPlainUI;
 const fields=['topics','selection','writing','reply_style','notes'];
 const fresh=()=>({project_id:'',skills:[],preferences:Object.fromEntries(fields.map(k=>[k,'']))});
 const buffers=new Map(),productionRequests=new Map();let call,message,readPost,scheduleUI=null,operatingUI=null,ready=false,closed=false,platform='',account='',scope='',active=false,epoch=0,previewEpoch=0,productionEpoch=0,accountRows=[],productionEffective=null,productionConfigError='',linkState='NOT_SENT',catalog={revision:0,projects:[]},effective=null,preview=null;
 let initialization={state:'NOT_SENT',id:null};
 function clearPreview(){previewEpoch++;preview=null;$('projectSourcePreview').open=false;$('projectSourceText').textContent='';$('projectSourceInfo').textContent='';}
 const key=()=>JSON.stringify([platform,scope]);const buffer=()=>buffers.get(key());
 const say=(value,error=false,...args)=>{(globalThis.OAUI||globalThis.OAPlainUI).set($('projectNotice'),value,...args);$('projectNotice').className='notice'+(error?' error':'');};
 async function invoke(operation,args){const r=await call(operation,args);if(r?.isError||!r?.structuredContent)throw new Error(r?.structuredContent?.error||'PROJECT_REQUEST_FAILED');return r.structuredContent;}
 const mark=()=>{const b=buffer();if(b){b.dirty=true;say('有未保存修改；切换账号时将保留在本页。');}buttons();};
 const productionTarget=()=>platform==='x'?accountRows.find(r=>r.platform_id==='x'&&r.connection_id===account):null;
 const productionKey=(cid,kind)=>kind+':'+cid;
 function productionSay(text,error=false,...args){(globalThis.OAUI||globalThis.OAPlainUI).set($('xProductionStatus'),text,...args);$('xProductionStatus').className='notice'+(error?' error':'');}
 function productionButtons(){
  const row=productionTarget(),request=productionRequests.get(productionKey(account,'now'));
  const available=ready&&!closed&&!!message&&!!row&&row.state==='BOUND_IDLE';
  $('xProduceNow').disabled=!available||!!request&&request.state!=='MATCHED';ui.set($('xProduceNow'),request?.state==='MATCHED'?'开始下一条并发布':'立即生产并发布');
  $('xProductionSchedule').disabled=!ready||closed||!row;$('projectXSchedule').disabled=!ready||closed||!row;
  $('xProductionResult').hidden=!request||request.state==='SENDING';$('xProductionResult').disabled=!ready||closed||!row||!readPost||!!request?.checking;
  $('xProductionEdit').disabled=!ready||closed||!row;
 }
 function renderProduction(){
  const row=productionTarget();ui.set($('xProductionAccount'),row?'目标账号：{0}':'选择已绑定的 X 账号后启动。',row?(row.presentation?.display_name||row.connection_id)+(row.username?' · @'+row.username:''):'');
  $('xProductionPreferences').replaceChildren();
  const cfg=productionEffective?.x_configuration?.configuration?.profile;
  for(const [title,value]of [['关注主题',cfg?.positioning.topics||productionEffective?.settings?.preferences?.topics],['目标读者',cfg?.positioning.readers],['文案与配图',cfg?.positioning.voice||productionEffective?.settings?.preferences?.writing],['运营配置',cfg?cfg.columns.length+' 个栏目 · '+cfg.growth.methods.join('、'):productionEffective?.settings?.preferences?.notes]]){
   const p=document.createElement('p'),label=document.createElement('strong');ui.set(label,title);p.append(label,value?document.createTextNode(value):ui.label('未设置 · 由 Codex 自主创作'));$('xProductionPreferences').append(p);
  }
  $('xProductionConfigStatus').textContent=productionConfigError||(!row?'无需填写 API Key。':productionEffective?(productionEffective.inherited_from==='account'?'本号配置':'继承平台默认')+' · '+(productionEffective.project?.name||'未关联项目，沿用默认方法')+' · 规则来源：'+productionEffective.sources.map(s=>s.name).join('、'):'正在读取已保存的本号内容配置…');
  const request=productionRequests.get(productionKey(account,'now'));productionSay(request?.notice||'一次启动由当前 Codex 完成新文字、新配图、公开发布及真实链接读回。',request?.state==='UNKNOWN'||request?.state==='REJECTED');productionButtons();
 }
 async function loadProduction(){
  const token=++productionEpoch,cid=account;productionEffective=null;productionConfigError='';renderProduction();if(!ready||closed||!productionTarget())return;
  try{const value=await invoke('READ',{platform_id:'x',connection_id:cid});if(closed||token!==productionEpoch||platform!=='x'||account!==cid)return;
   if(value.platform_id!=='x'||value.connection_id!==cid)throw new Error('PROJECT_ACCOUNT_MISMATCH');productionEffective=value;
  }catch(error){if(closed||token!==productionEpoch||account!==cid)return;productionConfigError='本号配置暂未读到，启动后 Codex 会重新读取；未使用未保存编辑。';}
  if(!closed&&token===productionEpoch)renderProduction();
 }
 function productionPrompt(cid,id,kind){

  return '请立即为 OpenAhoy 已选定的 X 账号 '+cid+' 完成一条新帖的生产与公开发布。这是本人点击“立即生产并发布”的完整一次委托，不再逐步询问主题、配图或发帖确认。启动请求 '+id+'；原上传 attempt_id='+id+'-media，原发帖 attempt_id='+id+'-post。先原生 x.connections.list 核对该真实账号，再 own.projects.read effective(platform_id=x,connection_id='+cid+')并完整读取全部适用来源分块和SHA，以及effective.x_configuration中的完整运营配置和skill.text（complete=true）。采用实际本号定位、关注方式、栏目、图片质量方法与画面偏好；临时发帖任务不因所在时刻套用某个整点栏目。使用已保存的关注主题、选题筛选、文案配图和其他偏好，未关联项目/选填项为空沿正式默认方法，不强制关联开发规则、不保存或覆写配置，不采用本页未保存编辑。由当前聊天/任务的真实 Codex 模型自主选合适内容、核普通事实、写新文。需要配图时用已有工具实际生成并核对，不另索API Key、不编造用户经历、不用占位图或重发旧稿。按本号采用的内容形式与本轮委托处理。纯文字只调用 x.posts.create（省略两个 upload 参数）→ x.posts.readback；带图沿原 x.media.upload → x.posts.create → x.posts.readback。一次公开发表并独立核账号、文字及是否有预期媒体，返回本轮真实新链接；宿主消息ACK不是发表成功。若本启动请求已执行或结果未知，先用这两个原attempt查 x.attempt.status/原readback，不能换键重发。只发本轮一条，不启用定时，不做回复/点赞/关注/私信，不改公众号、凭据或模型设置。完成或真实阻断即报告并停止。';
 }
 async function launchProduction(kind){
  const row=productionTarget();if(!ready||closed||!message||!row||row.state!=='BOUND_IDLE')return;
  const cid=row.connection_id,k=productionKey(cid,kind),prior=productionRequests.get(k);if(prior&&!(kind==='now'&&prior.state==='MATCHED'))return;
  const id='x-production-'+[...crypto.getRandomValues(new Uint8Array(16))].map(v=>v.toString(16).padStart(2,'0')).join('');
  const request={id,cid,state:'SENDING',notice:kind==='now'?'正在把本轮生产发布交给当前 Codex…':'正在把定时生产配置交给当前 Codex…'};productionRequests.set(k,request);renderProduction();
  try{await message(productionPrompt(cid,id,kind));request.state='SENT';request.notice=kind==='now'?'已交给当前 Codex；请在聊天查看实际进展和发布结果。':'定时配置请求已交给 Codex；尚未创建或启用任务。';}
  catch(error){request.state=error.message==='HOST_MESSAGE_UNAVAILABLE'?'REJECTED':'UNKNOWN';request.notice=request.state==='REJECTED'?'宿主未提供消息能力，未发送请求。':'发送结果未知，请先查看当前聊天和原任务；本页不会重复发送。';}
  if(!closed&&platform==='x'&&account===cid)renderProduction();
 }
 async function productionResult(){
  const row=productionTarget(),request=productionRequests.get(productionKey(account,'now'));if(!ready||closed||!row||!request||request.checking||!readPost)return;request.checking=true;productionButtons();
  try{const reply=await readPost(request.cid,request.id+'-post'),value=reply?.structuredContent;if(reply?.isError||!value||value.connection_id!==request.cid||value.attempt_id!==request.id+'-post')throw new Error('X_RESULT_UNAVAILABLE');
   if(value.state==='SUCCEEDED'&&value.readback_state==='MATCHED'&&typeof value.url==='string'&&/^https:\/\/x\.com\/[A-Za-z0-9_]+\/status\/[0-9]+$/.test(value.url)){request.state='MATCHED';request.notice='已发布并独立读回匹配：'+value.url;}
   else request.notice=value.state==='NOT_FOUND'?'原任务尚无发帖记录；请查看当前聊天，未重新派发。':value.state==='SUCCEEDED'?'帖子已创建，等待 Codex 独立读回；未再发新帖。':'原任务状态：'+value.state+'。请在当前聊天继续原请求，不重发。';
  }catch(error){request.notice='暂未读到原任务结果，请查看当前聊天；未重新派发。';}
  finally{request.checking=false;if(!closed&&platform==='x'&&account===request.cid)renderProduction();}
 }
 function buttons(){const b=buffer(),busy=b?.busy||false,pending=!!b?.pending,disabled=!ready||closed||!b||busy||pending,inherit=!!b?.inherit&&!!scope;
  for(const id of ['projectSave','projectDiscard','projectRefreshSources','projectChoice','projectPreference','projectPreferenceText'])$(id).disabled=disabled||(inherit&&['projectChoice','projectPreference','projectPreferenceText'].includes(id));
  $('projectScope').disabled=!ready||closed;
  $('projectAccountScope').disabled=!ready||closed||busy||pending||!account;$('projectDefaultScope').disabled=!ready||closed||busy||pending;
  $('projectAccountScope').setAttribute('aria-pressed',String(!!scope));$('projectDefaultScope').setAttribute('aria-pressed',String(!scope));$('projectReload').disabled=!ready||closed||busy||pending;
  $('projectLink').disabled=!ready||closed||!message||pending||busy||linkState!=='NOT_SENT';$('projectInherit').disabled=disabled;
  $('projectInitialize').disabled=!ready||closed||!message||pending||busy||initialization.state!=='NOT_SENT';
  $('projectXSchedule').hidden=platform!=='x';$('projectXDiscovery').hidden=platform!=='x';productionButtons();
  $('projectQuery').hidden=!pending;$('projectQuery').disabled=!ready||busy||closed;
  for(const input of $('projectSkills').querySelectorAll('input'))input.disabled=disabled||inherit;
  for(const button of $('projectSources').querySelectorAll('button'))button.disabled=!ready||closed||!b;
 }
 function renderSources(){const b=buffer(),project=catalog.projects.find(p=>p.id===b?.settings.project_id);
  ui.raw($('projectSkills'),'');$('projectSources').replaceChildren();
  if(project?.root)ui.raw($('projectPath'),project.root);else ui.set($('projectPath'),'未关联项目：继续使用原平台规则。');
  const sources=project?.sources||[],by=new Map((effective?.sources||[]).map(s=>[s.id,s]));
  const skills=sources.filter(s=>s.kind==='skill');
  for(const row of skills){const label=document.createElement('label'),input=document.createElement('input'),body=document.createElement('span'),title=document.createElement('span'),help=document.createElement('span');input.type='checkbox';input.value=row.id;input.checked=b.settings.skills.includes(row.id);title.textContent=row.name;help.className='help';help.textContent=row.description;body.append(title,help);label.append(input,body);input.addEventListener('change',()=>{b.settings.skills=b.settings.skills.filter(id=>id!==row.id);if(input.checked)b.settings.skills.push(row.id);mark();});$('projectSkills').append(label);}
  if(!skills.length)ui.set($('projectSkills'),'此项目尚无可选 Skill。可从本聊天关联已具备的 Skill。');
  const missing=b.settings.skills.filter(id=>!skills.some(s=>s.id===id));if(missing.length){const p=document.createElement('p');p.className='project-stale';p.textContent='有 '+missing.length+' 个已选 Skill 来源缺失，请刷新来源并核对。';$('projectSkills').append(p);}
  for(const row of [catalog.builtin,...sources].filter(Boolean)){const button=document.createElement('button'),actual=by.get(row.id);button.type='button';button.textContent=(row.kind==='agents'?'AGENTS · ':row.origin==='plugin'?'插件 · ':'Skill · ')+row.name+(actual&&actual.status!=='CURRENT'?' · 来源已变化':'');button.title=row.path+'\nSHA256 '+row.sha256;if(actual&&actual.status!=='CURRENT')button.className='project-stale';button.addEventListener('click',()=>showSource(row,0));$('projectSources').append(button);}
 }
 function render(){const b=buffer();if(!b)return;
  const defaults=new Option('','');ui.set(defaults,'沿用现有工作流程');$('projectChoice').replaceChildren(defaults);for(const project of catalog.projects)$('projectChoice').add(new Option(project.name,project.id));
  if(b.settings.project_id&&!catalog.projects.some(p=>p.id===b.settings.project_id)){const missing=new Option('',b.settings.project_id);ui.set(missing,'项目来源不可用');$('projectChoice').add(missing);}
  $('projectChoice').value=b.settings.project_id;$('projectInheritLabel').hidden=!scope;$('projectInherit').checked=!!b.inherit;
  $('projectPreferenceText').value=b.settings.preferences[$('projectPreference').value]||'';
  $('projectOrigin').textContent=(scope?(b.inherit?'本账号继承平台默认':'本账号单独设置'):'当前平台默认')+' · 来源 revision '+b.revision;
  renderSources();$('projectEffective').replaceChildren();
  for(const [title,value]of [['项目',effective?.project?.root||'未关联'],['生效来源',effective?.inherited_from==='account'?'本账号覆盖':'平台默认'],['已选 Skill',(effective?.sources||[]).filter(s=>s.kind==='skill').map(s=>s.name).join('、')||'OpenAhoy'],...fields.map(k=>[({topics:'关注主题',selection:'筛选方式',writing:'写作表达',reply_style:'回复风格',notes:'其他约定'})[k],effective?.settings?.preferences?.[k]||'未设置'])]){const p=document.createElement('p');p.textContent=title+'：'+value;$('projectEffective').append(p);}
  const warnings=(effective?.sources||[]).filter(s=>s.status!=='CURRENT');if(warnings.length)say('已选来源发生变化或不可读，请刷新来源版本后核对。',true);buttons();
 }
 async function load({discard=false}={}){if(!ready||closed||!platform)return;const token=++epoch,k=key();buttons();say('正在读取项目设置…');
  try{const [list,value]=await Promise.all([invoke('CATALOG',{}),invoke('READ',{platform_id:platform,connection_id:scope})]);if(closed||token!==epoch||k!==key())return;
   catalog=list;effective=value;clearPreview();let b=buffers.get(k);if(!b||discard||(!b.dirty&&!b.pending&&!b.busy)){b={settings:clone(value.settings),inherit:!!scope&&!value.overridden,revision:value.revision,dirty:false,busy:false,pending:null};buffers.set(k,b);}
   render();if(initialization.id)void checkInitialization(token);if(platform==='x')void loadProduction();say(b.pending?'保存结果待确认，请查询原操作。':b.dirty?'已保留本范围未保存修改；保存时会检查版本。':'已读取项目与 Skill 设置。');
  }catch(error){if(token===epoch&&!closed)say('项目设置读取失败：'+error.message,true);}buttons();
 }
 async function checkInitialization(token){
  const id=initialization.id;if(!id||closed)return;
  try{
   const result=await invoke('OPERATION',{operation_id:id});if(closed||token!==epoch||id!==initialization.id)return;
   if(result.state!=='SAVED'){$('projectInitializationStatus').textContent='初始化请求已发送；尚未确认来源登记。请查看当前聊天，不会重复发送。';return;}
   const project=catalog.projects.find(p=>p.id===result.project_id);
   const agents=project?.sources.find(s=>s.kind==='agents'&&s.path===project.root+'/AGENTS.md');
   const skill=project?.sources.find(s=>s.kind==='skill'&&s.path===project.root+'/.agents/skills/openahoy-production/SKILL.md');
   if(!agents||!skill)throw new Error('PROJECT_INIT_SOURCES_UNAVAILABLE');
   const read=async row=>{let body='';for(let index=0;index<row.chunks;index++){const part=await invoke('SOURCE',{project_id:project.id,source_id:row.id,expected_sha256:row.sha256,index});body+=part.text;}return body;};
   const [a,s]=await Promise.all([read(agents),read(skill)]);if(closed||token!==epoch||id!==initialization.id)return;
   if(!a.includes('<!-- OpenAhoy production bridge:begin -->')||!a.includes('<!-- OpenAhoy production bridge:end -->')||!s.includes('name: openahoy-production'))throw new Error('PROJECT_INIT_SOURCES_UNAVAILABLE');
   initialization.state='VERIFIED';$('projectInitializationStatus').textContent='项目来源已登记且实际可读：'+project.root+'。当前聊天是否已完整采用规范，请以 Codex 的读取回报为准。';
  }catch(error){if(!closed&&token===epoch)$('projectInitializationStatus').textContent='初始化结果尚未核实：'+error.message+'。保留原文件，请在当前聊天查询原请求。';}
 }
 async function showSource(row,index){const k=key(),token=epoch,sourceToken=++previewEpoch,pid=buffer().settings.project_id;try{const value=await invoke('SOURCE',{project_id:pid,source_id:row.id,expected_sha256:row.sha256,index});if(closed||!active||k!==key()||token!==epoch||sourceToken!==previewEpoch||pid!==buffer()?.settings.project_id)return;preview={row,index,total:value.chunks};$('projectSourcePreview').open=true;$('projectSourceInfo').textContent=row.path+' · SHA256 '+value.sha256;$('projectSourceText').textContent=value.text;$('projectSourcePage').textContent=(index+1)+' / '+value.chunks;$('projectSourcePrev').disabled=index===0;$('projectSourceNext').disabled=index+1>=value.chunks;}catch(error){if(k===key()&&token===epoch&&sourceToken===previewEpoch)say('来源读取失败：'+error.message+'；原文件未改动。',true);}}
 async function save(){const b=buffer();if(!b||b.busy||b.pending||!ready)return;const k=key(),p=platform,c=scope;b.busy=true;const request={platform_id:p,connection_id:c,settings:clone(b.settings),inherit:!!c&&b.inherit,operation_id:'project-'+[...crypto.getRandomValues(new Uint8Array(16))].map(v=>v.toString(16).padStart(2,'0')).join(''),expected_revision:b.revision};b.pending={request,kind:'save'};buttons();
  try{const result=await invoke('SAVE',request);if(result.operation_id!==request.operation_id||result.state!=='SAVED')throw new Error('PROJECT_SAVE_UNKNOWN');b.pending=null;b.dirty=false;if(!closed&&key()===k)await load({discard:true});}
  catch(error){if(['PROJECT_REVISION_CONFLICT','PROJECT_SKILL_NOT_FOUND','PROJECT_NOT_FOUND','PROJECT_ACCOUNT_MISMATCH','PROJECT_SECRET_NOT_ALLOWED','PROJECT_INVALID_REQUEST'].includes(error.message)){b.pending=null;}if(!closed&&key()===k)say(error.message==='PROJECT_REVISION_CONFLICT'?'其他页面已修改设置。草稿已保留；可刷新查看生效内容，放弃本页修改后再编辑。':'保存未完成：'+error.message+'。未知结果只查询原操作。',true);}
  finally{b.busy=false;if(!closed&&key()===k)buttons();}
 }
 async function query(){const b=buffer(),k=key(),pending=b?.pending;if(!pending||b.busy)return;b.busy=true;buttons();try{const result=await invoke('OPERATION',{operation_id:pending.request.operation_id});if(result.state==='SAVED'){b.pending=null;if(pending.kind==='save')b.dirty=false;if(!closed&&key()===k)await load({discard:!b.dirty});}else if(result.state==='NOT_FOUND'){b.pending=null;if(!closed&&key()===k)say('原操作未写入；修改已保留，可重新保存。');}}catch(error){if(!closed&&key()===k)say('原操作仍待确认：'+error.message,true);}finally{b.busy=false;if(!closed&&key()===k)buttons();}}
 async function refreshSources(){const b=buffer(),pid=b?.settings.project_id,k=key();if(!pid||b.busy||b.pending)return;b.busy=true;const request={project_id:pid,operation_id:'project-'+[...crypto.getRandomValues(new Uint8Array(16))].map(v=>v.toString(16).padStart(2,'0')).join(''),expected_revision:catalog.revision};b.pending={kind:'refresh',request};buttons();try{const result=await invoke('REFRESH',request);if(result.state!=='SAVED'||result.operation_id!==request.operation_id)throw new Error('PROJECT_SAVE_UNKNOWN');b.pending=null;if(!b.dirty)b.revision=result.revision;if(!closed&&key()===k)await load();}catch(error){if(['PROJECT_REVISION_CONFLICT','PROJECT_SOURCE_UNAVAILABLE','PROJECT_SYMLINK_NOT_ALLOWED','PROJECT_SECRET_NOT_ALLOWED'].includes(error.message))b.pending=null;if(!closed&&key()===k)say('来源刷新未完成：'+error.message,true);}finally{b.busy=false;if(!closed&&key()===k)buttons();}}
 function changeTarget(p,c,rows){const changed=platform!==p||account!==c;platform=p;account=c;accountRows=rows;const old=$('projectScope').value,choices=rows.filter(r=>r.platform_id===p);$('projectScope').replaceChildren(new Option('平台默认',''));for(const row of choices)$('projectScope').add(new Option(row.presentation?.display_name||row.connection_id,row.connection_id));scope=changed?c:(choices.some(r=>r.connection_id===old)?old:'');$('projectScope').value=scope;scheduleUI?.target(productionTarget());operatingUI?.target(productionTarget());epoch++;clearPreview();if(changed)$('projectForm').scrollTop=0;void loadProduction();if(active)load();}
 return {mount(tool,send,options={}){call=tool;message=send;readPost=options.readPost;scheduleUI=OAXSchedule.mount(tool,send);operatingUI=OAXOperating.mount(tool,{downloadArtifact:options.downloadArtifact,onSaved:()=>void loadProduction()});
  function chooseScope(value){if(!ready||closed||buffer()?.busy||buffer()?.pending)return false;scope=value;$('projectScope').value=value;epoch++;clearPreview();$('projectForm').scrollTop=0;load();return true;}
  $('projectScope').addEventListener('change',()=>chooseScope($('projectScope').value));
  $('projectAccountScope').addEventListener('click',()=>account&&chooseScope(account));
  $('projectDefaultScope').addEventListener('click',()=>chooseScope(''));
  $('projectChoice').addEventListener('change',()=>{const b=buffer();clearPreview();b.settings.project_id=$('projectChoice').value;b.settings.skills=[];mark();renderSources();buttons();});
  $('projectInherit').addEventListener('change',async()=>{const b=buffer(),k=key(),token=epoch;if(!b)return;const inherit=$('projectInherit').checked;b.inherit=inherit;
   if(inherit){b.beforeInheritance=clone(b.settings);b.busy=true;buttons();try{const value=await invoke('READ',{platform_id:platform,connection_id:''});if(!closed&&k===key()&&token===epoch&&b===buffer()&&b.inherit){b.settings=clone(value.settings);mark();render();}}catch(error){b.inherit=false;if(k===key()&&!closed){render();say('平台默认读取失败，原修改已保留：'+error.message,true);}}finally{b.busy=false;if(k===key()&&!closed)buttons();}}
   else{if(b.beforeInheritance)b.settings=clone(b.beforeInheritance);mark();render();}});
  $('projectPreference').addEventListener('change',()=>{$('projectPreferenceText').value=buffer()?.settings.preferences[$('projectPreference').value]||'';});
  $('projectPreferenceText').addEventListener('input',()=>{buffer().settings.preferences[$('projectPreference').value]=$('projectPreferenceText').value;mark();});
  $('projectSave').addEventListener('click',save);$('projectQuery').addEventListener('click',query);$('projectDiscard').addEventListener('click',()=>{if(!buffer()?.pending)load({discard:true});});$('projectReload').addEventListener('click',()=>load());$('projectRefreshSources').addEventListener('click',refreshSources);
  $('projectSourcePrev').addEventListener('click',()=>preview&&showSource(preview.row,preview.index-1));$('projectSourceNext').addEventListener('click',()=>preview&&showSource(preview.row,preview.index+1));
  $('xProduceNow').addEventListener('click',()=>launchProduction('now'));
  $('xProductionResult').addEventListener('click',productionResult);
  $('xProductionEdit').addEventListener('click',()=>{$('xOperatingPanel').open=true;$('xOperatingPanel').scrollIntoView({block:'nearest'});});
  $('projectLink').addEventListener('click',async()=>{if(!message||!ready||linkState!=='NOT_SENT')return;linkState='SENDING';buttons();try{await message('请将当前聊天实际工作区的 AGENTS.md 与项目 Skills 关联到 OpenAhoy。使用 own.projects.read catalog 读取版本，再用 own.projects.sync 登记本聊天真实 project_root 与明确可用的 Skills；不从插件 cwd 猜路径、不扫描其他聊天或历史目录。不修改原文件、账号、权限、调度或发帖。登记后告知我已关联的项目，我会在页面选择应用范围。');linkState='SENT';say('关联请求已发到当前聊天；登记完成后点击本页刷新。');}catch(error){linkState='UNKNOWN';say('宿主未确认关联请求，请先查看当前聊天，避免重复发送。',true);}finally{buttons();}});
  $('projectInitialize').addEventListener('click',async()=>{
   if(!message||!ready||initialization.state!=='NOT_SENT')return;
   initialization={state:'SENDING',id:'project-'+[...crypto.getRandomValues(new Uint8Array(16))].map(v=>v.toString(16).padStart(2,'0')).join('')};buttons();
   try{await message('请初始化当前聊天的实际运营项目。这是本人点击“初始化当前项目”的明确委托，仅创建项目生产桥接规范，不发布文章。先从本聊天真实工作区核对并说明项目名/绝对路径，不使用插件cwd或账号名猜测；工作区不明确时才询问。完整读取当前OpenAhoy插件Skill及references/PROJECT_INITIALIZATION.md，检查当前适用AGENTS/override、AGENTS.md和.agents/skills/openahoy-production/SKILL.md实际字节与SHA（不存在用MISSING），读取own.projects.read catalog的revision，然后调用own.projects.initialize，固定operation_id='+initialization.id+'，project_root为本聊天真实工作区，传入刚读到的两个文件指纹和revision。保留用户正文、同名Skill、账号和个人配置；冲突停止相关写入，不覆盖、不绕过override。结果未知先查此原operation_id和实际文件，不换键重写。成功后显式完整读取实际AGENTS维护段、桥接Skill及其当前插件/目标平台引用，按全部分块/SHA核对来源，报告实际版本和公众号必须交付真实含图HTML的要求；X按X格式，不套公众号HTML。不要保存账号偏好、改变模型/权限/调度或自动生产发表。最后回报实际文件路径、指纹、来源登记与当前聊天已读/未读状态；消息ACK不代表完成。');
    initialization.state='SENT';$('projectInitializationStatus').textContent='初始化请求已交给当前 Codex，尚未确认文件落盘；完成后点击刷新核对实际项目来源。';
   }catch(error){initialization.state='UNKNOWN';$('projectInitializationStatus').textContent='宿主未确认初始化请求，请先查看当前聊天；本页不会重复发送。';}finally{buttons();}
  });
  buttons();return {setReady(value,canMessage){ready=value;scheduleUI.ready(value,canMessage);operatingUI.ready(value);if(!canMessage)message=null;if(ready){void loadProduction();if(active)load();}buttons();},target:changeTarget,activate(){active=true;load();},deactivate(){active=false;epoch++;clearPreview();if(ready)void loadProduction();},dispose(){scheduleUI.dispose();operatingUI.dispose();closed=true;active=false;epoch++;productionEpoch++;clearPreview();ready=false;buttons();}};
 }};
})();
'''
