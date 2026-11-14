"""Native management card. Credential text stays inside the app frame."""

SCRIPT = r'''
const OAVideoCredential = (call, ready) => {
 const $ = id => document.getElementById(id);
 const card = $('videoModel'), input = $('videoCredential'), button = $('videoCredentialSave');
 const rpc = args => call('wce.ui.video.credential', args);
 const notice = text => OAUI.set($('videoModelState'), text);
 const usable = () => globalThis.isSecureContext === true && !!globalThis.crypto?.subtle;
 const labels = {CONFIGURED:'已保存，尚未验证调用',NOT_CONFIGURED:'未配置 API Key',
                 ACTION_REQUIRED:'需要钥匙串访问权限'};
 let generation = 0, busy = false, session = '';
 function controls(){
   input.disabled = button.disabled = !ready() || !card.open || busy || !usable();
 }
 function cancel(value){
   if(value && ready())rpc({action:'cancel',session:value}).catch(()=>{});
 }
 function resetCard(){
   generation++;
   input.value = '';
   busy = false;
   const original = session;
   session = '';
   cancel(original);
 }
 async function refresh(){
   if(!ready() || !card.open || busy)return;
   const epoch = ++generation;
   controls();
   if(!usable()){notice('当前面板无法安全输入 API Key');return;}
   try{
     const result = await call('video.ark.connection.status',{});
     if(epoch===generation)notice(labels[result.state] || '无法读取配置状态');
   }catch(_){if(epoch===generation)notice('无法读取配置状态');}
 }
 card.addEventListener('toggle',()=>{
   if(card.open)refresh();
   else{resetCard();controls();}
 });
 async function save(event){
   event.preventDefault();
   if(!event.isTrusted || !ready() || !card.open || busy || !usable())return;
   let key = input.value.trim();
   input.value = '';
   if(!/^[!-~]{1,4096}$/.test(key)){notice('API Key 格式无效');return;}
   const epoch = ++generation;
   busy = true;
   controls();
   try{
     const result = await rpc({action:'begin'});
     if(epoch!==generation){cancel(result.session);return;}
     session = result.session;
     if(result.state!=='READY' || result.purpose!=='openahoy:video:ark:cn-beijing:key:v1'
       || !/^[a-f0-9]{64}$/.test(session))throw new Error('INVALID_CHALLENGE');
     const jwe = await OASealCredential(result.challenge,result.purpose,key);
     key = '';
     if(epoch!==generation)return;
     const saved = await rpc({action:'submit',session,jwe});
     if(epoch===generation)notice(labels[saved.state] || '未确认保存结果');
   }catch(_){if(epoch===generation)notice('未确认保存结果');}
   finally{
     key = '';
     if(epoch===generation){
       cancel(session);
       session = '';
       busy = false;
       controls();
     }
   }
 }
 button.addEventListener('click',save);
 input.addEventListener('keydown',event=>{if(event.key==='Enter'&&!event.isComposing)save(event);});
 return {dispose: resetCard, refresh};
};
'''
