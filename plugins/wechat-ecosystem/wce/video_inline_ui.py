"""Native management card. Credential text stays inside the app frame."""

SCRIPT = r'''
const OAVideoCredential = (call, ready) => {
 const $ = id => document.getElementById(id);
 const provider = $('videoCredentialProvider'), origin = $('videoRelayOrigin');
 const direct = {input:$('videoCredential'), button:$('videoCredentialSave'), status:$('videoModelState'), epoch:0};
 const relay = {input:$('videoRelayCredential'), button:$('videoRelaySave'), status:$('videoRelayState'), epoch:0};
 const gif = {input:$('videoOpenAIGifCredential'), button:$('videoOpenAIGifSave'), status:$('videoOpenAIGifState'), epoch:0};
 const cards=[direct,relay,gif];
 const siteFor=card=>card===gif?'openai_gif':card===relay?'relay':provider.value;
 const rpc = args => call('wce.ui.video.credential', args);
 const notice = (card, text) => OAUI.set(card.status, text);
 const usable = () => globalThis.isSecureContext === true && !!globalThis.crypto?.subtle;
 const labels = {CONFIGURED:'已保存，尚未验证调用',NOT_CONFIGURED:'未配置 API Key',
                 ACTION_REQUIRED:'需要钥匙串访问权限'};
 let busy = false, section = '', session = '';
 const active=card=>section===(card===gif?'gif':'video');
 function controls(){
   const disabled = !ready() || busy || !usable();
   provider.disabled = origin.disabled = disabled || section!=='video';
   for(const card of cards)card.input.disabled = card.button.disabled = disabled || !active(card);
 }
 function cancel(value){
   if(value && ready())rpc({action:'cancel',session:value}).catch(()=>{});
 }
 function reset(){
   for(const card of cards){
     card.epoch++;
     card.input.value = '';
   }
   origin.value = '';
   busy = false;
   const original = session;
   session = '';
   cancel(original);
 }
 async function refresh(card){
   if(!ready() || !active(card))return;
   const epoch = ++card.epoch;
   notice(card,'正在读取配置…');
   if(!usable()){notice(card,'当前面板无法安全输入 API Key');return;}
   const site = siteFor(card);
   try{
     const result = site==='ark'?await call('video.ark.connection.status',{}):await rpc({action:'status',provider:site});
     if(epoch!==card.epoch)return;
     if(card===relay && !origin.value){
       if(result.state==='CONFIGURED' && result.base_url)origin.value=result.base_url;
       if(result.state==='NOT_CONFIGURED')origin.value=origin.dataset.defaultOrigin;
     }
     const label=card===gif&&result.state==='CONFIGURED'?'已保存，GIF 权限未验证':card===relay&&result.state==='NOT_CONFIGURED'?'未配置中转站':labels[result.state];
     notice(card,label || '无法读取配置状态');
   }catch(_){if(epoch===card.epoch)notice(card,'无法读取配置状态');}
 }
 function setOpen(value, page='video'){
   if(!value&&section!==page)return;
   const next=value?page:'';
   if(section===next)return;
   reset();
   section=next;
   controls();
   for(const card of cards)if(active(card))void refresh(card);
 }
 provider.addEventListener('change',()=>{
   direct.input.value='';
   void refresh(direct);
 });
 async function save(card,event){
   event.preventDefault();
   if(!event.isTrusted || !ready() || !active(card) || busy || !usable())return;
   const isRelay=card===relay;
   let key=card.input.value.trim();
   card.input.value='';
   if(!/^[!-~]{1,4096}$/.test(key)){
     notice(card,isRelay?'中转站 Token 格式无效':'API Key 格式无效');return;
   }
   const site=siteFor(card);
   const base=isRelay?origin.value.trim().replace(/\/$/,'').toLowerCase():'';
   if(isRelay && !/^https:\/\/[a-z0-9.-]+$/.test(base)){
     notice(card,'请输入中转站 HTTPS 地址');return;
   }
   const epoch=++card.epoch;
   busy=true;
   controls();
   try{
     let purpose;
     if(isRelay){
       const digest=await crypto.subtle.digest('SHA-256',new TextEncoder().encode(base));
       const hex=Array.from(new Uint8Array(digest),byte=>byte.toString(16).padStart(2,'0')).join('');
       purpose='openahoy:video:comfyui-relay:key:v1:'+hex;
     }else if(card===gif){
       purpose='openahoy:image:openai:gif:key:v1';
     }else{
       purpose=site==='ark'?'openahoy:video:ark:cn-beijing:key:v1':'openahoy:video:minimax:'+site+':key:v1';
     }
     if(epoch!==card.epoch)return;
     const result=await rpc(isRelay?{action:'begin_relay',base_url:base}:{action:'begin',provider:site});
     if(epoch!==card.epoch){cancel(result.session);return;}
     session=result.session;
     if(result.state!=='READY' || result.purpose!==purpose
       || !/^[a-f0-9]{64}$/.test(session))throw new Error('INVALID_CHALLENGE');
     const jwe=await OASealCredential(result.challenge,result.purpose,key);
     key='';
     if(epoch!==card.epoch)return;
     const saved=await rpc({action:'submit',session,jwe});
     if(epoch===card.epoch){
       if(isRelay&&saved.base_url)origin.value=saved.base_url;
       notice(card,card===gif&&saved.state==='CONFIGURED'?'已保存，GIF 权限未验证':labels[saved.state] || '未确认保存结果');
     }
   }catch(_){if(epoch===card.epoch)notice(card,'未确认保存结果');}
   finally{
     key='';
     if(epoch===card.epoch){
       cancel(session);
       session='';
       busy=false;
       controls();
     }
   }
 }
 for(const card of cards){
   card.button.addEventListener('click',event=>save(card,event));
   card.input.addEventListener('keydown',event=>{if(event.key==='Enter'&&!event.isComposing)save(card,event);});
 }
 return {dispose:()=>setOpen(false,section), setOpen};
};
'''
