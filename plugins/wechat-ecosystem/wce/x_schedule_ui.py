"""Embedded schedule form; standard app tool/message bridges only."""

from .management_locale import FALLBACK

HTML = '''<details id="xSchedulePanel" class="oa-schedule"><summary>定时生产与发布</summary>
<p class="help">到点开始创作，完成后发布；不是保证该分钟已经发出。由 Codex 原生任务运行，无需保持管理页打开。本机任务需要电脑在线、应用运行。</p>
<p id="xScheduleAccount" class="help"></p>
<div class="oa-schedule-grid"><label>重复方式<select id="xScheduleMode"><option value="daily">每日</option><option value="weekly">指定星期</option><option value="once">仅一次</option></select></label>
<label>时区<input id="xScheduleTimezone" placeholder="Asia/Shanghai" autocomplete="off"></label>
<label id="xScheduleTimesLabel">启动时刻<input id="xScheduleTimes" placeholder="09:00, 18:30" autocomplete="off"><span class="help">24 小时制，多个时刻用逗号分隔。</span></label>
<label id="xScheduleOnceLabel" hidden>启动日期和时刻<input id="xScheduleOnce" type="datetime-local"></label></div>
<fieldset id="xScheduleWeekdays" hidden><legend>每周</legend>''' + ''.join(
    '<label><input type="checkbox" value="' + str(i) + '">' + name + '</label>'
    for i, name in enumerate(['周一', '周二', '周三', '周四', '周五', '周六', '周日'], 1)) + '''</fieldset>
<p id="xScheduleDraft" class="help"></p><div class="actions"><button id="xScheduleSave">保存时段</button><button id="xScheduleEnable" class="primary">启用定时</button><button id="xSchedulePause">暂停</button><button id="xScheduleResume">恢复</button><button id="xScheduleCheck">核对原任务</button><button id="xScheduleReload">刷新显示</button></div>
<p id="xScheduleStatus" role="status" class="notice">尚未读取定时设置。</p><details id="xScheduleHostDetails"><summary>原生任务详情</summary><div id="xScheduleTasks" class="help"></div></details>
<p id="xScheduleLastRun" class="help"></p><p class="help">保存时段不会创建任务；“已交给 Codex”不是已启用。暂停只影响后续触发，不撤回已提交的帖子。</p></details>'''

STYLE = '''.oa-schedule{margin-top:14px;border-top:1px solid var(--line,#dce4e1);padding-top:10px}.oa-schedule summary{font-weight:600;cursor:pointer}.oa-schedule-grid{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:10px}.oa-schedule-grid label{display:flex;flex-direction:column;gap:4px;font-size:12px}.oa-schedule input,.oa-schedule select{box-sizing:border-box;max-width:100%;min-width:0}.oa-schedule fieldset{border:0;padding:4px 0;display:flex;flex-wrap:wrap;gap:12px}.oa-schedule fieldset[hidden],.oa-schedule [hidden]{display:none}.oa-schedule fieldset label{display:flex;align-items:center;gap:3px;font-size:12px}.oa-schedule #xScheduleTasks{overflow-wrap:anywhere}@media(max-width:560px){.oa-schedule-grid{grid-template-columns:1fr}}'''

SCRIPT = FALLBACK + r'''
window.OAXSchedule={mount(call,message){
 const $=id=>document.getElementById(id),drafts=new Map(),sent=new Set();let ready=false,closed=false,target=null,epoch=0,busy=false,value=null;
 const shownTime=(t)=>{try{return new Intl.DateTimeFormat('zh-CN',{dateStyle:'medium',timeStyle:'short',timeZone:value?.applied_config?.timezone||value?.config?.timezone||undefined}).format(new Date(t));}catch(_){return t;}};
 const empty=()=>({mode:'daily',times:[],weekdays:[],timezone:Intl.DateTimeFormat().resolvedOptions().timeZone||'',once_at:''});
 const configKey=c=>JSON.stringify([c.mode,c.timezone,c.once_at,[...c.times].sort(),[...c.weekdays].sort()]);
 const valid=c=>{if(!c.timezone)return false;try{new Intl.DateTimeFormat('zh-CN',{timeZone:c.timezone});}catch(_){return false;}return c.mode==='once'?/^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}$/.test(c.once_at):!!c.times.length&&c.times.every(t=>/^(?:[01][0-9]|2[0-3]):[0-5][0-9]$/.test(t))&&new Set(c.times).size===c.times.length&&(c.mode!=='weekly'||!!c.weekdays.length);};
 const cfg=()=>({mode:$('xScheduleMode').value,timezone:$('xScheduleTimezone').value.trim(),times:$('xScheduleMode').value==='once'?[]:$('xScheduleTimes').value.split(/[,，\s]+/).filter(Boolean),weekdays:$('xScheduleMode').value==='weekly'?[...$('xScheduleWeekdays').querySelectorAll('input:checked')].map(x=>Number(x.value)):[],once_at:$('xScheduleMode').value==='once'?$('xScheduleOnce').value:''});
 const ui=globalThis.OAUI||globalThis.OAPlainUI;
 function say(t,error=false,...values){(globalThis.OAUI||globalThis.OAPlainUI).set($('xScheduleStatus'),t,...values);$('xScheduleStatus').className='notice'+(error?' error':'');}
 function fields(c){$('xScheduleMode').value=c.mode;$('xScheduleTimezone').value=c.timezone;$('xScheduleTimes').value=c.times.join(', ');$('xScheduleOnce').value=c.once_at;for(const x of $('xScheduleWeekdays').querySelectorAll('input'))x.checked=c.weekdays.includes(Number(x.value));modes();}
 function modes(){const m=$('xScheduleMode').value;$('xScheduleTimesLabel').hidden=m==='once';$('xScheduleOnceLabel').hidden=m!=='once';$('xScheduleWeekdays').hidden=m!=='weekly';}
 function buttons(){const ok=ready&&!closed&&target?.state==='BOUND_IDLE'&&!busy&&!!value,waiting=!!value?.pending,complete=valid(cfg());
  for(const id of ['xScheduleSave','xScheduleEnable'])$(id).disabled=!ok||waiting||!complete||id==='xScheduleEnable'&&!message;
  $('xSchedulePause').disabled=!ok||waiting||!message||!value?.tasks.some(t=>t.status==='ACTIVE');
  $('xScheduleResume').disabled=!ok||waiting||!message||!value?.applied_config||!value?.tasks.length||value.tasks.some(t=>t.status==='ACTIVE');
  $('xScheduleReload').disabled=!ok;$('xScheduleCheck').disabled=!ok||!message||!waiting&&!value?.tasks.length;
  ui.set($('xScheduleEnable'),value?.tasks.length?'应用时段并启用':'启用定时');ui.set($('xScheduleCheck'),value?.pending?.delivery==='NOT_SENT'?'继续原请求':'核对原任务');
 }
 function render(){
  ui.set($('xScheduleAccount'),target?'目标账号：{0}':'请选择已绑定的 X 账号。',target?(target.presentation?.display_name||target.connection_id)+(target.username?' · @'+target.username:''):'');
  $('xScheduleTasks').replaceChildren();
  if(value){
   const o=value.observed,p=value.pending;
   say(p?(p.delivery==='NOT_SENT'?'原请求尚未发送，可继续：':'原请求待核对：')+p.action+' · '+p.id+'。不会新建重复请求。':o?({ACTIVE:'原生任务最近核对为已启用',PAUSED:'原生任务最近核对为已暂停',FAILED:'原生任务操作失败',NO_CHANGE:'宿主确认此次操作未改变任务',UNKNOWN:'原生任务结果未知',PENDING:'部分任务已记录，等待完整执行'}[o.status]||'任务待核对')+' · '+shownTime(o.checked_at):'尚未启用定时任务。');
   if(o){const p=document.createElement('p');p.textContent='状态来源：Codex 原生任务核对记录'+(o.note?' · '+o.note:'');$('xScheduleTasks').append(p);}
   for(const task of value.tasks){const p=document.createElement('p');p.textContent=task.slot+' · '+(task.status==='ACTIVE'?'已启用':'已暂停')+' · '+task.id+' · 运行聊天 '+task.thread_id+' · 下次运行：'+(task.next_run_at||'宿主未提供');$('xScheduleTasks').append(p);}
   ui.set($('xScheduleDraft'),configKey(cfg())!==configKey(value.config||empty())?'表单有未保存修改。':value.config&&(!value.applied_config||configKey(value.config)!==configKey(value.applied_config))?'时段已保存，尚未应用到原生任务。':'内容规则沿用上方本号已保存配置；每次触发重新读取。');
   const run=value.last_run;$('xScheduleLastRun').textContent=run?'最近实际运行：'+run.state+' · '+shownTime(run.finished_at||run.started_at)+(run.url?' · '+run.url:''):'尚无本功能的实际定时生产记录。';
  }else{$('xScheduleLastRun').textContent='';$('xScheduleDraft').textContent='';say(target?'正在读取本号定时设置…':'请选择已绑定的 X 账号。');}
  buttons();
 }
 async function invoke(op,args){const r=await call(op,args);if(r?.isError||!r?.structuredContent)throw Error(r?.structuredContent?.error||'SCHEDULE_REQUEST_FAILED');return r.structuredContent;}
 async function load({replace=false}={}){const e=++epoch,cid=target?.connection_id;if(!ready||!cid){value=null;buttons();return;}
  try{const v=await invoke('SCHEDULE_READ',{connection_id:cid});if(closed||e!==epoch||cid!==target?.connection_id)return;if(v.connection_id!==cid)throw Error('SCHEDULE_ACCOUNT_MISMATCH');value=v;if(replace||!drafts.has(cid))drafts.set(cid,v.config||empty());fields(drafts.get(cid));render();}
  catch(_){if(e===epoch&&!closed){value=null;say('定时设置暂未读取，原账号和内容配置未改动。',true);buttons();}}
 }
 function prompt(v,check){const p=v.pending;
  return '请处理 OpenAhoy X 本号定时生产发布，connection_id='+v.connection_id+'。这是用户从真实内嵌页发起的'+(check?'核对原任务':'具体定时操作')+'，不要立即发帖。先 own.schedules.read 读取本号原记录；本次原请求 '+(p?.id||v.last_request_id)+'，操作 '+(p?.action||'check')+'，原任务 '+JSON.stringify(v.tasks)+'，所设时段 '+JSON.stringify(p?.config||v.applied_config||v.config)+
  '。仅用正式 automation_update 管理本功能确切原生任务；首次 heartbeat 默认关联发起本请求的当前生产聊天，不硬编码任何聊天/模型；已有任务保持原 thread_id。先按原ID view并核对同号OpenAhoy标记、heartbeat、原聊天和时段（已绑定旧任务不要求含本次新请求ID），再修改/暂停/恢复，不碰其他任务。本版每个时刻对应一个精确原生任务，禁止BYHOUR/BYMINUTE笛卡尔积多发或未登记的合并。时区及一次性COUNT语义须实际支持，不支持则如实报告，不能静默换时区。配置是到点开始生产，成稿后发表，不能承诺准点已发。'+
  (check?'本次仅核对原操作/任务和结果，不新建任务、不重新发送未知create。':'enable可创建或更新本号时段；pause仅暂停原IDs；resume仅恢复本号applied_config对应时段，退役时段保持暂停。')+
  ' 每个原生创建或更新成功后即用 own.schedules.update HOST_RESULT outcome=PENDING 保存实际ID/slot/status/thread_id/kind=heartbeat/真实next_run_at（未返回填空），再继续下一对象；所有期望时段完成才记录ACTIVE/PAUSED。仅在宿主明确拒绝且可证实整个原请求未改变任何任务时，使用HOST_RESULT outcome=NO_CHANGE，传原tasks_before及官方拒绝依据；无回执、查不到对象或有部分写入时保留UNKNOWN。旧任务ID全部保留，已取消时段暂停不删除。中途未知先查原ID或按本请求精确标记定位，找不到也不能推定没创建或换键重建，记录UNKNOWN。宿主ACK不是启用。新任务prompt必须包含同号、原控制请求标记、自己的slot以及以下执行约定：每次真正到点唤起时，读取 own.schedules.read 和本号最新 own.projects.read effective/全部适用Skill，完整读取effective.x_configuration.configuration及skill.text采用本号定位、关注方式、栏目和图片质量方法；临时测试槽不改日常栏目、不硬套所在时刻栏目；用本次宿主稳定occurrence ID调用 own.schedules.update RUN_BEGIN，若宿主只给当前触发turnID则保留原turnID且不声称跨新turn重试严格去重；无法识别原轮次就报告具体缺口，不猜。沿返回原media/post attempt，由当前 Codex 按当轮栏目的内容形式创作。纯文字省略两个 upload 参数，直接调用 x.posts.create 与 x.posts.readback；图文实际制作新图并沿 x.media.upload、x.posts.create、x.posts.readback。每轮只发所委托的一条，MATCHED后RUN_RESULT记录实际URL；UNKNOWN沿原attempt查，不造新键。每轮ID不同，启用id不能固定复用于所有发帖。once测试本轮结束后用automation_update暂停自己的确切任务，再 own.schedules.update CONTROL_REQUEST action=pause 获取原控制请求并HOST_RESULT记PAUSED，无下一次测试发表。不做回复/点赞/关注/私信、公众号写入、模型API服务或其他调度器，不需页面开着。原生工具返回不带ID时，可沿正式工具说明只读定位该精确请求标记的本机automation配置获取原ID，绝不手写配置或私有IPC。完成后报告真实设置、触发、发表各自状态。';
 }
 const newOp=()=> 'project-'+[...crypto.getRandomValues(new Uint8Array(16))].map(v=>v.toString(16).padStart(2,'0')).join('');
 async function dispatch(v,check){
  const p=v.pending,id=p?.id||v.last_request_id,cid=v.connection_id;
  if(check){
   const checkId=cid+':'+id+':check';
   if(sent.has(checkId))return;
   await message(prompt(v,true));
   sent.add(checkId);
   return;
  }
  if(p.delivery!=='NOT_SENT')throw Error('SCHEDULE_ORIGINAL_MESSAGE_PENDING');
  await invoke('SCHEDULE_DELIVERY',{connection_id:cid,request_id:id,delivery:'DISPATCHING',operation_id:newOp(),expected_revision:v.revision});
  let delivery='UNKNOWN';try{await message(prompt(v,false));delivery='ACK';}
  catch(error){if(error.message==='HOST_MESSAGE_UNAVAILABLE')delivery='NOT_SENT';throw error;}
  finally{try{const current=await invoke('SCHEDULE_READ',{connection_id:cid});if(current.pending?.id===id&&current.pending.delivery==='DISPATCHING')await invoke('SCHEDULE_DELIVERY',{connection_id:cid,request_id:id,delivery,operation_id:newOp(),expected_revision:current.revision});}catch(_){/* Unknown state is retained, never cleared to create again. */}}
 }
 async function run(action){if(!ready||busy||!target||!value)return;const cid=target.connection_id,e=epoch;busy=true;buttons();
  try{
   if(action==='check'&&value.pending){await dispatch(value,value.pending.delivery!=='NOT_SENT');const fresh=await invoke('SCHEDULE_READ',{connection_id:cid});if(e===epoch&&cid===target?.connection_id){value=fresh;render();say('原请求已交给 Codex；请等待实际宿主结果。');}return;}
   const id=newOp(),configuration=cfg();
   const result=await invoke('SCHEDULE_REQUEST',{connection_id:cid,action,configuration,operation_id:id,expected_revision:value.revision});
   if(result.connection_id!==cid)throw Error('SCHEDULE_ACCOUNT_MISMATCH');
   const v=await invoke('SCHEDULE_READ',{connection_id:cid});
   if(action==='save'){drafts.delete(cid);if(e===epoch)await load({replace:true});return;}
   if(!v.pending||v.pending.id!==id)throw Error('SCHEDULE_REQUEST_MISMATCH');await dispatch(v,false);
   const fresh=await invoke('SCHEDULE_READ',{connection_id:cid});if(e===epoch&&cid===target?.connection_id){value=fresh;render();say('具体定时请求已交给 Codex；尚未确认原生任务已启用或暂停。');}
  }catch(error){if(e===epoch&&cid===target?.connection_id){await load();say(({SCHEDULE_TIME_PAST:'启动时间已过去，请选择将来的时刻。',SCHEDULE_TIME_NOT_EXIST:'该时区不存在这个夏令时时刻，请调整。',SCHEDULE_TIME_AMBIGUOUS:'该时刻在夏令时切换时重复，请选择明确时刻。',SCHEDULE_CONNECTION_NOT_READY:'账号连接需要处理，未启用新任务。',PROJECT_REVISION_CONFLICT:'设置已变化，已保留填写，请刷新后再试。',SCHEDULE_PENDING_USE_ORIGINAL:'原请求尚未完成，请核对原任务。'})[error.message]||'操作未完成（'+String(error.message).replace(/[^A-Z0-9_]/g,'').slice(0,80)+'）；请核对原请求，不重复新建。',true);}}
  finally{busy=false;buttons();}
 }
 for(const id of ['xScheduleMode','xScheduleTimezone','xScheduleTimes','xScheduleOnce'])$(id).addEventListener('input',()=>{if(target){modes();drafts.set(target.connection_id,cfg());render();}});
 $('xScheduleWeekdays').addEventListener('change',()=>{if(target){drafts.set(target.connection_id,cfg());render();}});
 for(const [id,action]of [['xScheduleSave','save'],['xScheduleEnable','enable'],['xSchedulePause','pause'],['xScheduleResume','resume'],['xScheduleCheck','check']])$(id).addEventListener('click',()=>run(action));
 function open(){if(!ready||!target)return;$('platformSettingsTab').click();$('xSchedulePanel').open=true;void load();}
 $('xScheduleReload').addEventListener('click',()=>load());
 $('xProductionSchedule').addEventListener('click',open);$('projectXSchedule').addEventListener('click',open);
 $('xSchedulePanel').addEventListener('toggle',()=>{if($('xSchedulePanel').open)void load();});
 buttons();return {target(row){if(row?.connection_id===target?.connection_id){const changed=row?.state!==target?.state;target=row;if(changed){epoch++;render();if(ready)void load();}return;}if(target)drafts.set(target.connection_id,cfg());epoch++;target=row;value=null;busy=false;fields(row?(drafts.get(row.connection_id)||empty()):empty());render();if(ready)void load();},ready(ok,canMessage){ready=ok;if(!canMessage)message=null;if(ok&&target)void load();buttons();},dispose(){closed=true;ready=false;epoch++;buttons();}};
}};
'''
