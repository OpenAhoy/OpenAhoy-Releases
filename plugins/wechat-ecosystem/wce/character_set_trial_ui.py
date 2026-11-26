"""Character rehearsal panel hosted inside the existing character detail."""
import json

from .character_set_trial import STAGES

STYLE = '''
#clSetTrial{box-sizing:border-box;width:min(610px,calc(100vw - 28px));max-height:calc(100dvh - 36px);
 padding:18px;border:1px solid var(--line);border-radius:16px;color:var(--ink);background:var(--surface);
 box-shadow:var(--raised);overflow:auto}
#clSetTrial::backdrop{background:#16191978}
#clSetTrial header,#clSetTrial footer{display:flex;align-items:center;gap:8px;flex-wrap:wrap}
#clSetTrial header{justify-content:space-between}
#clSetTrial h2{margin:0;font-size:19px}
#clSetTrial .cl-trial-ref-list{display:grid;grid-template-columns:repeat(auto-fit,minmax(min(100%,114px),1fr));
 gap:8px;max-height:240px;overflow:auto;padding:5px}
#clSetTrial .cl-trial-ref-list button{display:flex;min-width:0;flex-direction:column;align-items:stretch;
 gap:4px;white-space:normal;overflow-wrap:anywhere;text-align:start}
#clSetTrial .cl-trial-ref-list button[aria-pressed="true"]{box-shadow:var(--inset);color:var(--accent)}
#clSetTrial .cl-trial-ref-list img{width:100%;height:82px;object-fit:contain;border-radius:6px}
#clSetTrial .cl-trial-selected{display:flex;align-items:center;gap:12px;margin:8px 0}
#clSetTrial .cl-trial-selected img{max-width:100px;height:96px;object-fit:contain}
#clSetTrial :is(code,output){overflow-wrap:anywhere}
#clSetTrial output{display:block;line-height:1.5}
#clSetTrial :is(ol,p){margin:7px 0}
#clSetTrial footer{margin-top:10px}
'''

SCRIPT = r'''
function OACharacterSetTrial({tool,sendChat,canSend,thumbnail,make,button}){
 const ui=globalThis.OAUI;
 const dialog=make('dialog');dialog.id='clSetTrial';dialog.setAttribute('aria-labelledby','clSetTrialTitle');
 const title=make('h2','','零生图演练');title.id='clSetTrialTitle';
 const head=make('header'),dismiss=button('关闭',()=>dialog.close());
 dismiss.autofocus=true;head.append(title,dismiss);
 const target=make('p'),refs=make('div','cl-trial-ref-list');
 refs.setAttribute('role','group');ui.attr(refs,'aria-label','选择演练原图');
 const chosen=make('div','cl-trial-selected'),hero=make('img'),identity=make('div'),sourceName=make('strong'),digest=make('code');
 hero.alt='';identity.append(sourceName,make('br'),digest);chosen.append(hero,identity);
 const description=make('p','','本次只记录演练，新生成 0 张、调用 0 次、扣费 0。');
 const stages=make('ol'),receipt=make('p'),planDigest=make('code'),status=make('output');
 status.setAttribute('role','status');
 const footer=make('footer'),prepare=button('准备演练单',()=>void start()),cancel=button('取消这张演练单',()=>void cancelTask());
 const refresh=button('查看原单结果',()=>void check());
 const next=button('另开一张演练单',()=>void newTask());
 prepare.id='clSetTrialPrepare';cancel.id='clSetTrialCancel';refresh.id='clSetTrialRefresh';
 prepare.className='primary';footer.append(prepare,refresh,cancel,next);
 dialog.append(head,target,refs,chosen,description,stages,receipt,planDigest,status,footer);
 document.body.append(dialog);
 let selection=null,task=null,trigger=null,busy=false,announced=false,generation=0,interval=null;
 const ids=new Map(),states={PREPARED:'已准备演练单，等候原生确认。',WAITING_FOR_NATIVE_FORM:'已打开 Codex 原生确认。',
   COMPLETED:'演练已完成一次，生成与扣费均为 0。',CANCELLED:'这张演练单已取消。',
   DECLINED:'已拒绝这张演练单。',EXPIRED:'这张演练单已过期。',REFERENCE_CHANGED:'原图已更改或不可读取，演练未完成。',
   HOST_RESPONSE_UNAVAILABLE:'原生确认未返回有效结果，演练未完成。'};
 const controls=()=>{
   const pending=!task||['PREPARED','WAITING_FOR_NATIVE_FORM'].includes(task.state);
   prepare.disabled=busy||!selection||announced||(!!task&&(!canSend()||task.state!=='PREPARED'));
   refresh.hidden=!task;refresh.disabled=busy;
   cancel.hidden=!task||!pending;cancel.disabled=busy;next.hidden=!task||pending;next.disabled=busy;
   for(const ref of refs.children)ref.disabled=busy;
 };
 const key=row=>JSON.stringify([row.file.project_id,row.id,row.file.sha256]);
 function workId(row){
   const ref=key(row);
   if(ids.has(ref))return ids.get(ref);
   const store='Jiusera.character-rehearsal.'+ref;
   let value;
   try{value=sessionStorage.getItem(store);}catch(_){}
   if(!/^[a-f0-9]{32}$/.test(value||'')){
     value=Array.from(crypto.getRandomValues(new Uint8Array(16)),v=>v.toString(16).padStart(2,'0')).join('');
     try{sessionStorage.setItem(store,value);}catch(_){}
   }
   ids.set(ref,value);return value;
 }
 const call=(action,task_id,extra={})=>tool('wce.ui.characters.dry_run',{action,task_id,...extra});
 const current=seq=>dialog.open&&generation===seq;
 function paint(value){
   task=value;
   stages.replaceChildren(...value.plan.steps.map(label=>make('li','',label)));
   ui.raw(receipt,'ID '+value.task_id);ui.raw(planDigest,'SHA-256 '+value.plan_sha256);
   ui.set(status,states[value.state]||'原单状态未知。');
   if(value.state==='PREPARED'&&!canSend())ui.set(status,'演练单已保留。当前宿主没有提供 Codex 对话通道。');
   if(!['PREPARED','WAITING_FOR_NATIVE_FORM'].includes(value.state)){clearInterval(interval);interval=null;}
   controls();
 }
 async function choose(row){
   const seq=++generation;selection=row;busy=false;task=null;announced=false;
   clearInterval(interval);interval=null;
   ui.raw(sourceName,row.label);ui.raw(digest,row.file.sha256);hero.removeAttribute('src');
   for(const ref of refs.children)ref.setAttribute('aria-pressed',String(ref.dataset.version===row.id));
   stages.replaceChildren(...__TRIAL_STAGES__.map(label=>make('li','',label)));receipt.textContent='';planDigest.textContent='';ui.set(status,'选择的原图将固定到本次演练。');
   controls();
   void thumbnail(row).then(src=>{if(current(seq))hero.src=src;}).catch(()=>{if(current(seq))ui.set(status,'暂时无法读取所选原图。');});
   const old=ids.get(key(row));
   let previous=old;
   if(!previous)try{previous=sessionStorage.getItem('Jiusera.character-rehearsal.'+key(row));}catch(_){}
   if(previous)try{const value=await call('status',previous);if(current(seq))paint(value);}catch(_){}
 }
 function newTask(){
   if(!selection||next.hidden||busy)return;
   const ref=key(selection);
   ids.delete(ref);
   try{sessionStorage.removeItem('Jiusera.character-rehearsal.'+ref);}catch(_){}
   const row=selection;
   void choose(row);
   prepare.focus();
 }
 async function start(){
   if(prepare.disabled)return;
   const seq=generation,row=selection;
   busy=true;controls();
   try{
     const value=await call('prepare',workId(row),{project_id:row.file.project_id,version_id:row.id,sha256:row.file.sha256});
     if(!current(seq))return;
     paint(value);
     if(value.state!=='PREPARED'||!canSend())return;
     announced=true;
     await sendChat('请用 Jiusera 已准备的原单核对零生图演练，任务 '+value.task_id+
       '。先调用 own.characters.dry_run review 查看同一原图和固定计划，然后使用 confirm 和返回的计划摘要向我显示原生表单。只有原表单回答可结算，禁止调用任何生成工具。');
     if(!current(seq))return;
     ui.set(status,'已交给当前 Codex 核对，正在等候同一张原单的结果。');
     interval=setInterval(()=>void check(),1600);
   }catch(problem){
     if(current(seq))ui.set(status,announced?'未能确认当前聊天收到消息。请先查看原单结果，避免重复发起。':
       '暂时无法准备演练。请核对选定原图和项目。');
   }finally{
     if(current(seq)){busy=false;controls();}
   }
 }
 async function check(){
   if(!task||busy)return;
   const seq=generation;busy=true;controls();
   try{const value=await call('status',task.task_id);if(current(seq))paint(value);}
   catch(_){if(current(seq))ui.set(status,'原单暂时无法读取。');}
   finally{if(current(seq)){busy=false;controls();}}
 }
 async function cancelTask(){
   if(!task||busy)return;
   const seq=generation;busy=true;controls();
   try{const value=await call('cancel',task.task_id);if(current(seq))paint(value);}
   catch(_){if(current(seq))ui.set(status,'取消未确认，请查看原单结果。');}
   finally{if(current(seq)){busy=false;controls();}}
 }
 dialog.addEventListener('close',()=>{
   generation++;clearInterval(interval);interval=null;
   if(trigger?.isConnected)trigger.focus();
 });
 return {
   open(state,origin){
     trigger=origin;
     const rows=state.form.rows.filter(row=>row.file?.sha256&&!row.browseArchived&&row.use!=='voice'&&row.use!=='model');
     const unique=rows.filter((row,index)=>rows.findIndex(other=>other.file.sha256===row.file.sha256)===index);
     if(!unique.length)return;
     ui.raw(target,[state.person.projectName,state.person.character.name,state.form.name].filter(Boolean).join(' · '));
     refs.replaceChildren(...unique.map(row=>{
       const pick=button(undefined,()=>void choose(row));pick.dataset.version=row.id;pick.dataset.characterTrialReference='';
       const image=make('img');image.alt='';image.loading='lazy';const name=make('span');ui.raw(name,row.label);
       pick.append(image,name);
       void thumbnail(row).then(src=>{image.src=src;}).catch(()=>{image.hidden=true;});
       return pick;
     }));
     ui.set(prepare,canSend()?'发到当前 Codex 核单':'准备演练单');
     dialog.showModal();
     void choose(unique.find(row=>row.file.sha256===state.displayed?.row?.file.sha256)||unique[0]);
     dismiss.focus();
   },
   close(){if(dialog.open)dialog.close();}
 };
}
'''.replace('__TRIAL_STAGES__', json.dumps(STAGES, ensure_ascii=False))
