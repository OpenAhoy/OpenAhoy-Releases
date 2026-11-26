"""Account-bound X configuration editor; no scheduler or publication calls."""
import json
from .x_operating_config import blank, METHODS, SPEC
from .account_starter_ui import entry as starter_entry
from .management_workspace_ui import workspace

from .management_locale import FALLBACK

HTML = '<section id="xOperatingPanel" class="oa-x-config" aria-label="X 运营配置与创作 Skill">' + workspace('xConfig',
 '配置 X 的内容定位、表达风格、栏目节奏与创作偏好。',
 '<p id="xConfigTarget" class="help"></p>' + starter_entry('xConfig') + '<nav id="xConfigTabs" class="actions" aria-label="X 配置分类" hidden></nav><div id="xConfigSections"></div><details id="xConfigConflicts" hidden><summary>并发修改：核对冲突字段</summary><pre id="xConfigConflictText" class="x-config-skill"></pre></details>',
 '<p id="xConfigStatus" class="notice" role="status"></p><button id="xConfigSave" class="primary">保存并应用</button><button id="xConfigQuery" hidden>查询原保存结果</button>',
 '<details class="oa-task-menu"><summary>导入 / 下载</summary><div class="actions"><button id="xConfigImport">加载配置</button><button id="xConfigExport">下载配置</button><button id="xConfigSkillExport">下载 Skill</button><button id="xConfigReload">读取已保存配置</button><button id="xConfigNew">新建空白配置</button></div></details><button id="xConfigPreview">查看完整 Skill</button>',
 '<p class="help">保存配置不会启用定时或自动互动。</p><button type="button" data-workspace-project>项目与 Skills</button><button type="button" id="xWorkspaceTools">生产、定时与账号</button><button type="button" id="xWorkspaceBilling">账单与余额</button><button type="button" id="xConnectOwnApplication" hidden>连接自己的 X 开发者应用</button>'
) + '<input type="file" id="xConfigFile" accept=".json,application/json" hidden></section>'

STYLE = r'''
.oa-x-config{border:1px solid var(--line);border-radius:10px;padding:10px 12px;margin:12px 0}.oa-x-config>summary{font-weight:600;cursor:pointer}.oa-x-config>.actions{flex-wrap:wrap;margin:8px 0}.oa-x-config label{font-size:12px}.oa-x-config textarea{min-height:65px;resize:vertical}.oa-x-config select,.oa-x-config input:not([type=checkbox]){width:100%}.x-config-grid{display:grid;grid-template-columns:1fr 1fr;gap:10px 16px}.x-config-methods{display:flex;flex-wrap:wrap;gap:7px 14px}.x-config-methods label{display:flex;align-items:center;gap:5px}.oa-x-config [aria-selected=true]{background:var(--tint);color:var(--accent)}.x-config-column{border-top:1px solid var(--line);padding:8px 0}.x-config-column>summary{cursor:pointer;font-size:12px}.x-config-skill{white-space:pre-wrap;overflow-wrap:anywhere;max-height:330px;overflow:auto;font:12px/1.65 ui-monospace,monospace;background:var(--soft);padding:10px;border-radius:8px}.x-config-fields{max-height:390px;overflow:auto;padding:4px}.x-config-fields[hidden]{display:none}@media(max-width:600px){.x-config-grid{grid-template-columns:1fr}}
'''

SCRIPT = FALLBACK + r'''
const OAXOperating=(()=>{
 const blank=__BLANK__,methods=__METHODS__,spec=__SPEC__,clone=x=>JSON.parse(JSON.stringify(x));
 function validateClient(v,s){
  const fail=()=>{throw new Error('X_CONFIG_INVALID');};
  if(s.type==='object'){if(!v||typeof v!=='object'||Array.isArray(v)||Object.keys(v).length!==Object.keys(s.properties).length||!Object.keys(s.properties).every(k=>Object.hasOwn(v,k)))fail();for(const [k,x]of Object.entries(v))validateClient(x,s.properties[k]);}
  else if(s.type==='array'){if(!Array.isArray(v))fail();for(const x of v)validateClient(x,s.items);}
  else if(s.type==='integer'){if(!Number.isInteger(v))fail();}
  else if(s.type==='string'){
   if(typeof v!=='string'||/[\x00-\x08\x0b\x0c\x0e-\x1f\x7f-\x9f]/.test(v)||[...v].some(c=>{const n=c.codePointAt(0);return n>=0xd800&&n<=0xdfff;}))fail();
   if(/(?:appsecret|access[_ -]?token|api[_ -]?key|password|密码|密钥)\s*[:=：]\s*\S+/i.test(v)||/(?:(?:client[_ -]?secret|refresh[_ -]?token|id[_ -]?token|session[_ -]?token|authorization|cookie|bearer)\s*["']?\s*[:=：]\s*\S+|-----BEGIN (?:[A-Z0-9]+ )*PRIVATE KEY-----)/i.test(v))throw new Error('PROJECT_SECRET_NOT_ALLOWED');
  }else fail();
  if(Object.hasOwn(s,'const')&&v!==s.const)fail();if(s.enum&&!s.enum.includes(v))fail();
 }
 return {mount(call,{downloadArtifact,onSaved}={}){
  const $=id=>document.getElementById(id),buffers=new Map();let row=null,ready=false,closed=false,epoch=0,tab=0,importEpoch=0,workspace=null,readState='';
  const ui=globalThis.OAUI||globalThis.OAPlainUI;
  const b=()=>row?buffers.get(row.connection_id):null;
  const op=prefix=>prefix+[...crypto.getRandomValues(new Uint8Array(16))].map(v=>v.toString(16).padStart(2,'0')).join('');
  const say=(s,e=false,...values)=>{ui.set($('xConfigStatus'),s,...values);$('xConfigStatus').className='notice'+(e?' error':'');};
  const equal=(a,b)=>JSON.stringify(a)===JSON.stringify(b);
  function merge(base,local,remote,path='',conflicts=[]){if(equal(local,base))return clone(remote);if(equal(remote,base)||equal(local,remote))return clone(local);if(base&&local&&remote&&typeof base==='object'&&!Array.isArray(base)&&typeof local==='object'&&!Array.isArray(local)&&typeof remote==='object'&&!Array.isArray(remote)){return Object.fromEntries(Object.keys(remote).map(k=>[k,merge(base[k],local[k],remote[k],path?path+'.'+k:k,conflicts)]));}conflicts.push({field:path,current:remote,local});return clone(local);}
  const current=(cid,t)=>!closed&&ready&&row?.connection_id===cid&&epoch===t;
  async function invoke(operation,arguments_){if(['X_CONFIG_PREVIEW','X_CONFIG_SAVE','X_CONFIG_EXPORT'].includes(operation))validateClient(uniqueJSON(arguments_.configuration_text||arguments_.configuration),spec);const r=await call(operation,arguments_);if(r?.isError||!r?.structuredContent)throw new Error(r?.structuredContent?.error||'X_CONFIG_UNAVAILABLE');return r.structuredContent;}
  const starter=globalThis.OAAccountStarter&&$('xConfigStarter')?.append
    ? OAAccountStarter.mount($('xConfigStarter'),'x',{
      read(key){const [section,field]=key.split('.');return b()?.config.profile[section][field]??'';},
      write(key,value){const [section,field]=key.split('.');b().config.profile[section][field]=value;},
      empty(key,value){const [section,field]=key.split('.');return !value.trim()&&!b()?.base.profile[section][field].trim();},
      onChange(){changed();render();}
    }) : null;
  let choiceEditors=[];
  function buttons(){const v=b(),blocked=!ready||closed||!row||!v||v.busy||!!v.pending;
   for(const id of ['xConfigNew','xConfigImport','xConfigReload','xConfigSave','xConfigPreview'])$(id).disabled=blocked;
   for(const id of ['xConfigExport','xConfigSkillExport'])$(id).disabled=blocked;
   ui.set($('xConfigReload'),v?.dirty?'合并最新配置（保留填写）':'读取已保存配置');
   ui.set($('xConfigSave'),v?.conflicts?.length?'应用合并（冲突采用本页值）':'保存并应用本号');
   $('xConfigQuery').hidden=!v?.pending;$('xConfigQuery').disabled=!ready||closed||!v||v.busy;
   for(const e of $('xConfigSections').querySelectorAll('input,textarea,select,button'))e.disabled=blocked;
   for(const choice of choiceEditors)choice.refresh();
   starter?.update(v?row.connection_id:'',blocked);
  }
  function changed(){const v=b();if(!v)return;v.dirty=true;v.skill='';say('有未保存修改，尚未应用到本号。');workspace?.refresh();buttons();}
  const sections=[],tabs=[];
  for(const [i,title] of ['内容定位','表达与关注','栏目与节奏','配图与素材','项目与 Skill'].entries()){
   const button=document.createElement('button');button.type='button';ui.set(button,title);button.setAttribute('aria-selected',String(i===0));$('xConfigTabs').append(button);tabs.push(button);
   const section=document.createElement('section');section.className='x-config-fields';section.hidden=i!==0;$('xConfigSections').append(section);sections.push(section);
   button.onclick=()=>{tab=i;sections.forEach((s,j)=>s.hidden=i!==j);tabs.forEach((t,j)=>t.setAttribute('aria-selected',String(i===j)));};
  }
  if(globalThis.OATaskWorkspace)workspace=OATaskWorkspace.mount('xConfig',['内容定位','表达与关注','栏目与节奏','配图与素材','项目与 Skill'].map((title,i)=>({title,
    show:shown=>{sections[i].hidden=!shown;tabs[i].setAttribute('aria-selected',String(shown));if(shown)tab=i;},
    summary:()=>{const p=b()?.config.profile;if(!p)return [readState];return [p.positioning.topics||['按内容选择主题'],p.positioning.voice||(p.growth.methods.length?['{0}',ui.list(p.growth.methods)]:['按内容选择表达']),['{0} 个栏目 · {1}',p.columns.length,p.timezone],p.images.style||p.images.subject||['按主题选择画面'],['保留原项目与 Skills']][i];}
  })));
  function area(parent,label,get,set,type='textarea',choiceLabel=null){
   const l=document.createElement('label'),caption=document.createElement('span');ui.set(caption,label);const e=document.createElement(type);ui.attr(e,'aria-label',label);
   if(type==='textarea')e.rows=2;else e.type='text';e.value=get()||'';e.oninput=()=>{set(e.value);changed();};l.append(caption);
   if(choiceLabel&&globalThis.OAAccountStarter){
    const choice=OAAccountStarter.choices(e,[choiceLabel],{canEdit:()=>!e.disabled,commit:()=>e.oninput()});
    choiceEditors.push(choice);
    const field=document.createElement('div');
    field.append(l,choice.root);
    parent.append(field);
   }else{l.append(e);parent.append(l);}
   return e;
  }
  const grid=parent=>{const g=document.createElement('div');g.className='x-config-grid';parent.append(g);return g;};
  function renderColumns(parent,p){
   parent.replaceChildren();area(parent,'栏目时区',()=>p.timezone,v=>p.timezone=v,'input');
   const help=document.createElement('p');help.className='help';ui.set(help,'{0} 个内容栏目，未因此开启任何时段任务。时刻按当地日历日期解释；素材不具备时按本栏目缺料策略处理。',p.columns.length);parent.append(help);
   p.columns.forEach((c,i)=>{const d=document.createElement('details');d.className='x-config-column';const s=document.createElement('summary');s.textContent=c.time+' · '+(c.name||'未命名栏目');d.append(s);const g=grid(d);
    for(const [k,label]of [['time','当地时刻'],['name','栏目名称'],['purpose','栏目目的'],['selection','选材方法'],['missing','缺料处理'],['assets','素材来源']])area(g,label,()=>c[k],v=>{c[k]=v;s.textContent=c.time+' · '+(c.name||'未命名栏目');},['time','name'].includes(k)?'input':'textarea');
    const l=document.createElement('label');l.append(ui.label('内容形式'));const select=document.createElement('select');ui.attr(select,'aria-label','内容形式');for(const [v,t]of [['text','纯文字'],['image','图文'],['auto','按内容自选']]){const opt=new Option(t,v);ui.set(opt,t);select.add(opt);};select.value=c.format;select.onchange=()=>{c.format=select.value;changed();};l.append(select);g.append(l);
    const remove=document.createElement('button');ui.set(remove,'删除此栏目');remove.onclick=()=>{p.columns.splice(i,1);changed();renderColumns(parent,p);buttons();};d.append(remove);parent.append(d);
   });
   const add=document.createElement('button');ui.set(add,'添加栏目');add.onclick=()=>{p.columns.push({time:'09:00',name:'',purpose:'',format:'auto',selection:'',missing:'',assets:''});changed();renderColumns(parent,p);buttons();};parent.append(add);
  }
  function paintTarget(){
   const label=row&&(row.presentation?.display_name||row.label||row.username||row.connection_id);
   ui.set($('xConfigTarget'),row?'目标账号：{0}':'选择已绑定的 X 账号。',row?[label,row.username?'@'+row.username:''].filter(Boolean).join(' · '):'');
  }
  function render(){const v=b();if(!v)return;const p=v.config.profile;
   $('xConfigConflicts').hidden=!v.conflicts?.length;$('xConfigConflicts').open=!!v.conflicts?.length;$('xConfigConflictText').textContent=v.conflicts?.length?JSON.stringify(v.conflicts,null,2):'';
   paintTarget();
   sections.forEach(s=>s.replaceChildren());choiceEditors=[];const g=grid(sections[0]);
   for(const [k,label,group]of [['topics','主题领域','主题'],['readers','目标读者','读者'],['allowed','允许内容','内容形式'],['language','语言','语言']])
    area(g,label,()=>p.positioning[k],s=>p.positioning[k]=s,'textarea',group);
   const advanced=document.createElement('details'),advancedLabel=document.createElement('summary');
   ui.set(advancedLabel,'身份、排除内容与事实要求');advanced.append(advancedLabel);sections[0].append(advanced);
   for(const [k,label]of [['background','身份与品牌背景'],['excluded','排除内容'],['facts','事实表述']])
    area(advanced,label,()=>p.positioning[k],s=>p.positioning[k]=s);
   area(sections[1],'文风',()=>p.positioning.voice,s=>p.positioning.voice=s,'textarea','表达');
   const title=document.createElement('h4');ui.set(title,'吸引关注的方式（可多选）');sections[1].append(title);const picks=document.createElement('div');picks.className='x-config-methods';sections[1].append(picks);
   for(const m of [...new Set([...methods,...p.growth.methods])]){const label=document.createElement('label'),input=document.createElement('input');input.type='checkbox';input.checked=p.growth.methods.includes(m);input.onchange=()=>{p.growth.methods=p.growth.methods.filter(x=>x!==m);if(input.checked)p.growth.methods.push(m);changed();};label.append(input,methods.includes(m)?ui.label(m):document.createTextNode(m));picks.append(label);}
   for(const [k,label]of [['reason','希望因为什么被关注'],['custom','自定义关注方式'],['cta','行动号召']])area(sections[1],label,()=>p.growth[k],s=>p.growth[k]=s,'textarea',k==='reason'?'目标':null);
   renderColumns(sections[2],p);const images=grid(sections[3]);
   for(const [k,label]of [['subject','画面题材'],['characters','人物或物件'],['style','画面风格'],['aspect_ratio','图片比例'],['color','色彩'],['text_brand','图中文字与品牌'],['method','图片质量方法']])area(images,label,()=>p.images[k],s=>p.images[k]=s,'textarea',k==='subject'?'配图':null);
   area(sections[3],'本机素材与系列说明',()=>p.materials,s=>p.materials=s);area(sections[4],'其他约定',()=>p.notes,s=>p.notes=s);
   const pre=document.createElement('pre');pre.id='xConfigSkill';pre.className='x-config-skill';if(v.skill)ui.raw(pre,v.skill);else ui.set(pre,'点击“预览创作 Skill”查看当前填写的完整方法。未保存的预览不会生效。');sections[4].append(pre);workspace?.restore();buttons();
  }
  async function load(){if(!ready||closed||!row)return;const cid=row.connection_id,t=++epoch,old=b();
   if(old?.dirty||old?.pending||old?.busy){const renamed=!old.pending&&old.config.account_name!==row.presentation.display_name;if(renamed){old.config.account_name=row.presentation.display_name;old.dirty=true;old.skill='';}render();say(old.pending?'原保存待确认，请查询原操作。':renamed?'显示名已同步到未保存草稿，其他填写保留；保存后更新 Skill。':'本号未保存填写已保留。');return;}
   readState='读取本号配置…';workspace?.refresh();
   try{const r=await invoke('X_CONFIG_READ',{connection_id:cid});if(!current(cid,t))return;if(r.connection_id!==cid)throw new Error('X_CONFIG_ACCOUNT_MISMATCH');const config=clone(r.configuration||blank),renamed=!!r.configuration&&config.account_name!==row.presentation.display_name;if(!r.configuration||renamed)config.account_name=row.presentation.display_name;if(!r.configuration)config.profile.timezone=Intl.DateTimeFormat().resolvedOptions().timeZone;
    buffers.set(cid,{config,base:clone(r.configuration||config),revision:r.revision,dirty:renamed,saved:!!r.configuration,skill:renamed?'':r.skill.text,busy:false,pending:null,conflicts:[]});render();say(renamed?'账号显示名已变化；已保留运营内容并填写新显示名，保存后同步更新 Skill。':r.configuration?'已读取本号已保存配置及完整创作 Skill。':'尚无运营配置；可以新建或加载，原补充偏好仍保留。');
   }catch(e){if(current(cid,t)){readState='本号配置未读到';workspace?.refresh();say('配置读取未完成：'+e.message+'；可再次读取，原配置未变。',true);}}finally{if(!closed&&row?.connection_id===cid)buttons();}
  }
  async function preview(){const v=b();if(!v)return;const cid=row.connection_id,t=epoch;v.busy=true;buttons();try{const r=await invoke('X_CONFIG_PREVIEW',{connection_id:cid,configuration_text:JSON.stringify(v.config)});if(!current(cid,t))return;v.skill=r.skill.text;$('xConfigSkill').textContent=v.skill;tabs[4].click();workspace?.show(4);say(v.dirty?'预览已生成，尚未保存应用。':'当前已保存配置的完整创作 Skill。');}catch(e){if(current(cid,t))say('预览未完成：'+e.message,true);}finally{v.busy=false;if(!closed&&row?.connection_id===cid)buttons();}}
  async function save(){const v=b();if(!v||v.busy||v.pending||!ready)return;const cid=row.connection_id,t=epoch;v.busy=true;const a={connection_id:cid,configuration_text:JSON.stringify(v.config),expected_revision:v.revision,operation_id:op('project-')};v.pending=a;buttons();
   try{const r=await invoke('X_CONFIG_SAVE',a);if(r.state!=='SAVED'||r.operation_id!==a.operation_id||r.connection_id!==cid)throw new Error('X_CONFIG_SAVE_UNKNOWN');starter?.forget(cid);v.pending=null;v.dirty=false;v.saved=true;v.revision=r.revision;v.busy=false;if(!closed&&row?.connection_id===cid){await load();onSaved?.();}}
   catch(e){if(['PROJECT_REVISION_CONFLICT','PROJECT_INVALID_REQUEST','PROJECT_SECRET_NOT_ALLOWED','X_CONFIG_ACCOUNT_MISMATCH','X_CONFIG_INVALID','X_CONFIG_TIMEZONE_INVALID','X_CONFIG_COLUMN_FORMAT','X_CONFIG_COLUMN_TIME','X_CONFIG_DUPLICATE_METHOD'].includes(e.message))v.pending=null;if(current(cid,t))say(e.message==='PROJECT_REVISION_CONFLICT'?'生效配置已变化，填写已保留。请先读取最新配置版本再保存。':'保存未完成：'+e.message+'。未知结果查询原保存，不重发。',true);}
   finally{v.busy=false;if(!closed&&row?.connection_id===cid)buttons();}
  }
  async function query(){const v=b();if(!v?.pending||v.busy)return;const cid=row.connection_id,t=epoch;v.busy=true;buttons();try{const r=await invoke('OPERATION',{operation_id:v.pending.operation_id});if(r.state==='SAVED'&&r.connection_id===cid){starter?.forget(cid);v.pending=null;v.dirty=false;v.saved=true;v.revision=r.revision;v.busy=false;if(!closed&&row?.connection_id===cid){await load();onSaved?.();}}else if(r.state==='NOT_FOUND'){v.pending=null;if(current(cid,t))say('原保存未写入，填写已保留。');}}catch(e){if(current(cid,t))say('原保存仍待确认：'+e.message,true);}finally{v.busy=false;if(!closed&&row?.connection_id===cid)buttons();}}
  function uniqueJSON(raw){const value=JSON.parse(raw),stack=[];for(const token of raw.match(/"(?:\\.|[^"\\])*"|[{}\[\]:,]/g)||[]){if(token==='{'||token==='['){stack.push({object:token==='{',key:true,seen:new Set()});continue;}if(token==='}'||token===']'){stack.pop();continue;}const top=stack.at(-1);if(!top?.object)continue;if(token===','){top.key=true;continue;}if(token.startsWith('"')&&top.key){const k=JSON.parse(token);if(top.seen.has(k))throw new Error('X_CONFIG_DUPLICATE_KEY');top.seen.add(k);top.key=false;}}return value;}
  $('xConfigImport').onclick=()=>{$('xConfigFile').value='';importEpoch=epoch;$('xConfigFile').click();};
  $('xConfigFile').onchange=async()=>{const file=$('xConfigFile').files?.[0],v=b(),cid=row?.connection_id,t=importEpoch;if(!file||!v||!current(cid,t))return;v.busy=true;buttons();try{const raw=new TextDecoder('utf-8',{fatal:true}).decode(await file.arrayBuffer()),config=uniqueJSON(raw);if(!current(cid,t))return;if(config.account_name==='')config.account_name=row.presentation.display_name;
    const r=await invoke('X_CONFIG_PREVIEW',{connection_id:cid,configuration_text:JSON.stringify(config)});if(!current(cid,t))return;starter?.forget(cid);v.config=r.configuration;v.skill=r.skill.text;v.dirty=true;render();say('已加载 '+v.config.profile.columns.length+' 个栏目。请核对各分类和 Skill，点击“保存并应用本号”后才生效；未启用定时。');
   }catch(e){if(current(cid,t))say('配置加载失败，原填写已保留：'+e.message,true);}finally{v.busy=false;if(!closed&&row?.connection_id===cid)buttons();}};
  const exports=new Map();
  async function download(artifact){const v=b();if(!ready||closed||!v||v.pending||v.busy)return;const cid=row.connection_id,t=epoch,k=cid+':'+artifact;v.busy=true;buttons();let a=exports.get(k);try{
    if(!a){
     const configuration=JSON.stringify(v.config,null,2)+'\n';
     const preview=await invoke('X_CONFIG_PREVIEW',{connection_id:cid,configuration_text:configuration});if(!current(cid,t))return;
     if(preview.connection_id!==cid||preview.skill?.complete!==true||typeof preview.skill.text!=='string'||!preview.skill.text)throw new Error('X_CONFIG_PREVIEW_INVALID');
     a={connection_id:cid,configuration,export_id:op('config-'),artifact,raw:artifact==='skill'?preview.skill.text:configuration};exports.set(k,a);
    }
    const filename=artifact==='skill'?'Jiusera-X-SKILL.md':'Jiusera-X-运营配置.json',raw=a.raw;
    validateClient(uniqueJSON(a.configuration),spec);const r=await downloadArtifact(raw,filename,{...a,queryOnly:!!a.sent,onDispatch:()=>{a.sent=true;}});
    if(r.state==='CONFIG_EXPORT_NOT_FOUND'){exports.delete(k);if(current(cid,t))say('原下载未写入，可再次点击发起。');}
    else if(r.state==='CONFIG_EXPORTED'){
     if(r.destination!=='Downloads'||typeof r.filename!=='string'||!r.filename)throw new Error('X_CONFIG_DOWNLOAD_UNKNOWN');
     exports.delete(k);if(current(cid,t))say('已保存到本机“下载”文件夹（~/Downloads）：'+r.filename+'。未因此保存或应用到账号。');
    }else if(r.state==='HOST_DOWNLOADED'){exports.delete(k);if(current(cid,t))say('宿主已接受下载，请查看宿主下载记录。未因此保存或应用到账号。');}
    else if(current(cid,t))say('下载仍待确认；再次点击只查询原下载快照，不包含之后的修改。');
   }catch(e){if(current(cid,t))say('下载未完成：'+e.message+'；未切换其他下载通路。',true);}finally{v.busy=false;if(!closed&&row?.connection_id===cid)buttons();}}
  $('xConfigNew').onclick=()=>{const v=b();if(!v)return;starter?.forget(row.connection_id);v.config=clone(blank);v.config.account_name=row.presentation.display_name;v.config.profile.timezone=Intl.DateTimeFormat().resolvedOptions().timeZone;changed();render();};
  $('xConfigReload').onclick=async()=>{const v=b();if(!v||v.pending||v.busy)return;if(!v.dirty){await load();return;}const cid=row.connection_id,t=epoch;v.busy=true;buttons();try{const r=await invoke('X_CONFIG_READ',{connection_id:cid});if(!current(cid,t))return;if(r.connection_id!==cid)throw new Error('X_CONFIG_ACCOUNT_MISMATCH');const remote=clone(r.configuration||blank);if(!r.configuration){remote.account_name=row.presentation.display_name;remote.profile.timezone=v.base.profile.timezone;}const conflicts=[];starter?.forget(cid);v.config=merge(v.base,v.config,remote,'',conflicts);v.base=remote;v.conflicts=conflicts;v.revision=r.revision;v.skill='';render();say(conflicts.length?'已合并不冲突的最新修改。请核对下方冲突原值；保存会明确采用本页冲突值。':'已合并其他页面的新修改，并保留本页填写；尚未保存。');}catch(e){if(current(cid,t))say('最新配置未读到，填写保留：'+e.message,true);}finally{v.busy=false;if(!closed&&row?.connection_id===cid)buttons();}};
  $('xConfigSave').onclick=save;$('xConfigPreview').onclick=preview;$('xConfigQuery').onclick=query;$('xConfigExport').onclick=()=>download('configuration');$('xConfigSkillExport').onclick=()=>download('skill');
  function target(value){
   const changed=row?.connection_id!==value?.connection_id;
   row=value;
   paintTarget();
   if(changed){
    epoch++;
    readState=row?'读取本号配置…':'';
    if(b())render();
    else{
     sections.forEach(section=>section.replaceChildren());
     choiceEditors=[];
     $('xConfigConflicts').hidden=true;$('xConfigConflicts').open=false;$('xConfigConflictText').textContent='';
     workspace?.refresh();
    }
    say(row?'读取本号配置…':'');
   }
   buttons();if(ready&&row)void load();
  }
  buttons();return {ready(value){ready=value;if(value)void load();buttons();},target,dispose(){closed=true;ready=false;epoch++;buttons();}};
 }};
})();
'''.replace('__BLANK__', json.dumps(blank(), ensure_ascii=False)).replace('__METHODS__', json.dumps(METHODS, ensure_ascii=False)).replace('__SPEC__', json.dumps(SPEC, ensure_ascii=False))
