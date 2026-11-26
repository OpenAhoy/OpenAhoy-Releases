"""Per-work timeline autosave with optimistic versions, readback and local draft recovery."""

SCRIPT = r"""
function OADirectorCutDocument(row){
 return {clips:row.clips,music:row.music||null,detached_audio:row.detached_audio||[]};
}
function OADirectorAutosave({read,edit,uid,equal,valid,notify}){
 const prefix='jiusera.director.draft.v1.',states=new Set();
 const dirty=state=>state.loaded&&JSON.stringify(state.doc)!==state.saved;
 const scopeKey=state=>prefix+state.target.project_id+'.'+state.target.work_id+'.';
 const owner=uid();
 function changed(state){notify(state);}
 function isDoc(doc){
   return Array.isArray(doc?.clips)&&doc.clips.length<=256&&doc.clips.every(c=>c&&typeof c.id==='string'&&
     typeof c.delivery_id==='string'&&typeof c.sha256==='string'&&Number.isSafeInteger(c.in_ms)&&Number.isSafeInteger(c.out_ms)&&
     (c.gap_before_ms===undefined||(Number.isSafeInteger(c.gap_before_ms)&&c.gap_before_ms>=0&&c.gap_before_ms<=3600000))&&
     Number.isInteger(c.volume)&&(!c.look||typeof c.look==='object')&&(!c.look?.cues||Array.isArray(c.look.cues)))&&
     (doc.detached_audio===undefined||(Array.isArray(doc.detached_audio)&&doc.detached_audio.length<=256&&
       doc.detached_audio.every(r=>r&&['id','clip_id','delivery_id','sha256'].every(k=>typeof r[k]==='string')&&
         ['start_ms','in_ms','out_ms','volume'].every(k=>Number.isSafeInteger(r[k])&&r[k]>=0)&&r.out_ms>r.in_ms&&r.volume<=100)))&&
     (!doc.music||(typeof doc.music.attempt_id==='string'&&Number.isSafeInteger(doc.music.start_ms)));
 }
 function parse(key){
   try{
     const row=JSON.parse(localStorage.getItem(key));
     if(row?.format===1&&Number.isInteger(row.version)&&row.version>=0&&isDoc(row.doc)&&
       (!row.intent||(typeof row.intent.id==='string'&&row.intent.version===row.version&&isDoc(row.intent.plan))))return row;
   }catch(_){}
   return null;
 }
 function persist(state){
   const sync=state.sync;
   if(!sync.intent&&!dirty(state)&&!state.conflict){
     if(sync.key){
       try{localStorage.removeItem(sync.key);}catch(_){}
       try{if(sessionStorage.getItem(scopeKey(state))===sync.key)sessionStorage.removeItem(scopeKey(state));}catch(_){}
     }
     sync.key='';sync.durable=true;return;
   }
   try{
     if(!sync.key)sync.key=scopeKey(state)+owner;
     const row={format:1,updated:Date.now(),version:state.version,doc:state.doc,intent:sync.intent};
     localStorage.setItem(sync.key,JSON.stringify(row));sync.durable=true;
     try{sessionStorage.setItem(scopeKey(state),sync.key);}catch(_){}
   }catch(_){sync.durable=false;}
 }
 function journal(state){
   const sync=state.sync,snapshot=JSON.stringify(state.doc);
   if(!state.loaded||snapshot===sync.snapshot)return;
   sync.snapshot=snapshot;sync.error='';sync.retries=0;
   persist(state);schedule(state);
 }
 function schedule(state,delay=650){
   const sync=state.sync;clearTimeout(sync.timer);sync.timer=0;
   if(!state.loaded||sync.running||state.conflict||sync.error||(!sync.intent&&!valid(state.doc))||(!dirty(state)&&!sync.intent))return;
   sync.timer=setTimeout(()=>{sync.timer=0;void flush(state);},delay);
 }
 function forkRecovered(state,key,row,remote){
   const sync=state.sync;state.doc=structuredClone(OADirectorCutDocument(row.doc));sync.intent=row.intent||null;
   sync.snapshot=JSON.stringify(state.doc);
   const version=remote.timeline_version,targetPlan=OADirectorCutDocument(remote);
   const alreadyApplied=version===sync.intent?.version+1&&equal(OADirectorCutDocument(sync.intent.plan),targetPlan);
   if(alreadyApplied||(version>row.version&&equal(state.doc,targetPlan)))sync.intent=null;
   if(!alreadyApplied&&row.version!==version&&!equal(state.doc,targetPlan))state.conflict=true;
   if(state.conflict){sync.intent=null;state.version=row.version;}
   sync.orphan='';sync.error='';sync.retries=0;sync.key='';
   persist(state);
   // Remove exactly the recovered snapshot after a durable replacement or verified server copy.
   if(sync.key!==key&&sync.durable){
     try{const current=parse(key);if(current&&current.updated===row.updated&&equal(current.doc,row.doc))localStorage.removeItem(key);}catch(_){}
   }
   schedule(state);
 }
 function discover(state,remote){
   const sync=state.sync;
   if(sync.discovered)return;
   sync.discovered=true;const base=scopeKey(state);let own='',latestTime=0;
   try{
     own=sessionStorage.getItem(base)||'';
     if(own.startsWith(base)){
       const row=parse(own);if(row){forkRecovered(state,own,row,remote);return;}
     }
     for(let i=0;i<localStorage.length;i++){
       const key=localStorage.key(i);if(!key?.startsWith(base))continue;
       const row=parse(key);if(row&&row.updated>latestTime){sync.orphan=key;latestTime=row.updated;}
     }
   }catch(_){}
 }
 function recover(state,remote){
   const key=state.sync.orphan,row=key&&parse(key);
   if(!row||dirty(state)||state.sync.running)return false;
   forkRecovered(state,key,row,remote);return true;
 }
 function init(state,target){
   state.target={...target};
   state.sync={key:'',intent:null,retries:0,error:'',running:null,timer:0,epoch:0,snapshot:'',durable:true,orphan:'',discovered:false};
   states.add(state);
 }
 function abandon(state){
   const sync=state.sync;clearTimeout(sync.timer);sync.timer=0;
   sync.intent=null;sync.error='';sync.retries=0;sync.orphan='';state.conflict=false;
   sync.snapshot=JSON.stringify(state.doc);persist(state);
 }
 function acknowledge(state,remote,intent){
   const sync=state.sync;
   state.version=remote.timeline_version;
   state.saved=JSON.stringify(OADirectorCutDocument(intent.plan));state.sources=remote.sources;state.songs=remote.songs;
   state.job=null;state.lastDelivery='';sync.intent=null;sync.error='';sync.retries=0;
   sync.epoch++;persist(state);
 }
 function verified(state,row){
   if(row.project_id!==state.target.project_id||row.work_id!==state.target.work_id||
      !Number.isInteger(row.timeline_version)||!Array.isArray(row.clips))throw Error('DIRECTOR_INVALID_READBACK');
   return row;
 }
 function inspect(state,remote,intent){
   const plan=OADirectorCutDocument(remote);
   if(remote.timeline_version===intent.version+1&&equal(OADirectorCutDocument(intent.plan),plan)){acknowledge(state,remote,intent);return true;}
   if(remote.timeline_version!==intent.version){state.conflict=true;state.sync.intent=null;persist(state);throw Error('DIRECTOR_TIMELINE_CHANGED');}
   return false;
 }
 async function saveOne(state){
   const sync=state.sync;
   let intent=sync.intent;
   if(intent){
     const remote=verified(state,await read('timeline',state.target));
     if(inspect(state,remote,intent))return;
     // The previous call has an unknown outcome; submit only its original operation ID.
   }else{
     intent={id:uid(),version:state.version,plan:structuredClone(state.doc)};sync.intent=intent;persist(state);
   }
   const args={...state.target,operation_id:intent.id,expected_timeline_version:intent.version,clips:intent.plan.clips};
   if(intent.plan.music)args.music=intent.plan.music;
   if(intent.plan.detached_audio)args.detached_audio=intent.plan.detached_audio;
   let failure;
   try{await edit('timeline_save',args);}catch(error){failure=error;}
   const remote=verified(state,await read('timeline',state.target));
   if(inspect(state,remote,intent))return;
   // A definitive rejected edit did not advance its base. A changed draft may use a fresh operation.
   if(failure&&!/HOST_|TIMEOUT|NETWORK|RESPONSE_LOST|FETCH|CONNECTION|OFFLINE/i.test(failure.message)){
     sync.intent=null;if(!equal(intent.plan,state.doc))return;
   }
   throw failure||Error('DIRECTOR_SAVE_NOT_VERIFIED');
 }
 function flush(state,manual=false){
   const sync=state.sync;clearTimeout(sync.timer);sync.timer=0;
   if(manual){sync.error='';sync.retries=0;}
   if(sync.running)return sync.running;
   if(state.conflict||(!sync.intent&&!valid(state.doc)))return Promise.resolve(false);
   if(!dirty(state)&&!sync.intent)return Promise.resolve(true);
   if(sync.error)return Promise.resolve(false);
   sync.epoch++;
   sync.running=Promise.resolve().then(async()=>{
     while(!state.conflict&&(sync.intent||dirty(state))&&(sync.intent||valid(state.doc)))await saveOne(state);
     return !state.conflict&&!dirty(state);
   }).catch(error=>{
     if(!state.conflict){
       sync.retries++;
       if(sync.retries>=3||(!sync.intent&&!/HOST_|TIMEOUT|NETWORK|FETCH|CONNECTION|OFFLINE/i.test(error.message)))sync.error=error.message;
     }
     persist(state);return false;
   }).finally(()=>{
     sync.running=null;sync.epoch++;
     if(!state.conflict&&!sync.error&&(sync.intent||dirty(state)))schedule(state,Math.min(12000,1000*(2**sync.retries)));
     changed(state);
   });
   changed(state);return sync.running;
 }
 window.addEventListener('pagehide',()=>{for(const state of states)if(state.loaded&&(state.sync.intent||dirty(state)))persist(state);});
 window.addEventListener('beforeunload',event=>{
   if([...states].some(state=>!state.sync.durable&&(state.sync.intent||dirty(state)))){event.preventDefault();event.returnValue='';}
 });
 window.addEventListener('online',()=>{for(const state of states)if(state.loaded&&!state.conflict&&(state.sync.intent||dirty(state)))void flush(state,true);});
 return {init,journal,discover,recover,abandon,flush,dirty};
}
"""
