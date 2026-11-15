"""Native binding view; the parent bridge receives only a JWE, never form secrets."""
from .management_locale import FALLBACK

HTML = '''<section id="inlineBinding" class="oa-binding panel" hidden aria-labelledby="inlineBindingTitle">
<div class="drawer-head"><h2 id="inlineBindingTitle">绑定公众号</h2><button id="bindingBack" type="button" class="quiet">返回账号管理</button></div>
<form id="inlineBindingForm" autocomplete="off">
<label id="bindingPendingLabel" for="bindingPending" hidden>继续待完成的绑定</label><select id="bindingPending" hidden><option value="">选择原账号</option></select>
<label for="bindingAppID">AppID</label><input id="bindingAppID" required autocomplete="off" spellcheck="false" placeholder="wx…" pattern="wx[a-fA-F0-9]{16}">
<label for="bindingSecret">AppSecret</label><input id="bindingSecret" type="password" required maxlength="4096" autocomplete="new-password" spellcheck="false">
<details><summary>名称（可选，可稍后设置）</summary><label for="bindingLabel">账号显示名称</label><input id="bindingLabel" maxlength="64" autocomplete="off"></details>
<p class="help">凭据仅在本机验证并存入系统钥匙串。允许此账号执行你明确请求的素材和草稿操作，可随时断开；不会自动发表。</p>
<div class="actions"><button id="bindingSubmit" class="primary" type="submit">绑定公众号</button><button id="bindingCancel" type="button">取消</button><button id="bindingQuery" type="button" hidden>查询原操作</button><button id="bindingRetry" type="button" hidden>重新验证并继续绑定</button><button id="bindingResume" type="button" hidden>完成原绑定</button></div>
<p id="bindingNotice" class="notice" role="status" aria-live="polite"></p>
</form></section>'''

SEAL_SCRIPT = r'''
const OASealCredential = (() => {
  const b64=bytes=>{let s='';for(const v of new Uint8Array(bytes))s+=String.fromCharCode(v);return btoa(s).replace(/=/g,'').replace(/\+/g,'-').replace(/\//g,'_');};
  return async function seal(challenge,appid,secret){
   const enc=new TextEncoder(),head=b64(enc.encode(JSON.stringify({alg:'RSA-OAEP-256',enc:'A256GCM',kid:challenge.kid,typ:'openahoy-binding+jwe'})));
   const der=Uint8Array.from(atob(challenge.publicSPKI.replace(/-/g,'+').replace(/_/g,'/')),c=>c.charCodeAt(0));
   const rsa=await crypto.subtle.importKey('spki',der,{name:'RSA-OAEP',hash:'SHA-256'},false,['encrypt']);
   const aes=await crypto.subtle.generateKey({name:'AES-GCM',length:256},true,['encrypt']),iv=crypto.getRandomValues(new Uint8Array(12));
   const key=await crypto.subtle.exportKey('raw',aes),plain=enc.encode(JSON.stringify({appid,intent:challenge.intent,nonce:challenge.nonce,secret}));
   try{
    const wrapped=await crypto.subtle.encrypt({name:'RSA-OAEP'},rsa,key);
    const raw=new Uint8Array(await crypto.subtle.encrypt({name:'AES-GCM',iv,additionalData:enc.encode(head),tagLength:128},aes,plain));
    return [head,b64(wrapped),b64(iv),b64(raw.slice(0,-16)),b64(raw.slice(-16))].join('.');
   }finally{plain.fill(0);new Uint8Array(key).fill(0);}
  };
})();
'''

SCRIPT = FALLBACK + SEAL_SCRIPT + r'''
const OAInlineBinding = {
 mount(call,{enter,leave,complete}){
  const $=id=>document.getElementById(id);let view='',operation='',generation=0,busy=false,timer=null,visible=false,checked=false,revalidating=false,mayRevalidate=false,pendingBindings=[],selectionLocked=false,rebindTarget=null;
  const ui=globalThis.OAUI||globalThis.OAPlainUI;
  const note=(text,...values)=>ui.set($('bindingNotice'),text,...values);
  const clear=()=>{$('bindingSecret').value='';clearTimeout(timer);timer=null;};
  const supported=()=>globalThis.isSecureContext===true&&!!globalThis.crypto?.subtle;
  function controls(){
   $('bindingSubmit').disabled=busy||!view||!checked||!supported();$('bindingAppID').disabled=busy||revalidating||!!rebindTarget;
   $('bindingSecret').disabled=busy||!checked||!supported();$('bindingLabel').disabled=busy||revalidating||!!rebindTarget;
   $('bindingRetry').disabled=!mayRevalidate||!view||!checked||!supported();
   ui.set($('bindingSubmit'),rebindTarget?'重新绑定':revalidating?'重新验证并继续绑定':'绑定公众号');
   $('bindingPending').disabled=selectionLocked||revalidating;
  }
  async function status(epoch=generation){
   if(!visible||!view||!operation||epoch!==generation)return;
   try{await display(await call(rebindTarget?'REBIND_STATUS':'BINDING_STATUS',{view,operation}),epoch);}
   catch(_){if(epoch===generation){busy=true;selectionLocked=false;note('原操作状态暂不可用，请查询原操作；不要重复绑定。');$('bindingQuery').hidden=false;controls();}}
  }
  async function display(result,epoch){
   if(epoch!==generation||!visible)return;
   selectionLocked=result.state==='IN_PROGRESS';
   if(result.operation)operation=result.operation;
   $('bindingQuery').hidden=true;$('bindingResume').hidden=true;$('bindingRetry').hidden=true;mayRevalidate=false;
   if(result.binding_result==='COMMITTED'||result.state==='BOUND_IDLE'||result.state==='ALREADY_BOUND'){clear();busy=false;visible=false;$('inlineBinding').hidden=true;await complete(result.connection_id,result.state==='ALREADY_BOUND',result.state);return;}
   if(rebindTarget&&result.state==='REJECTED'){
    busy=false;operation='';note('重新绑定未完成，请检查凭据或账号是否正在使用。');controls();return;
   }
   if(result.state==='IN_PROGRESS'){
    busy=true;note(result.cancel_requested?'已请求取消，正在确认原操作结果…':'正在检查凭据、白名单并保存，请稍候…');
    clearTimeout(timer);timer=setTimeout(()=>status(epoch),1000);
   }else if(result.state==='IP_DENIED'){
    busy=false;note('微信拒绝当前出口 IP'+(result.observed_ip?'：'+result.observed_ip:'')+'。请在微信开发配置完成白名单设置，再在这里重新填写密钥并点击绑定；将沿原拒绝记录继续。');
   }else if(result.state==='READY'||result.state==='NOT_SENT'||result.state==='CANCELLED'){
    busy=false;note(result.validation_attempts>1?'本次新校验尚未发送，上一次未知记录已保留。请填写密钥后继续。':'原操作尚未请求微信。请重新填写密钥后提交，将安全继续原操作。');
   }else if(result.state==='STORED'){
    busy=true;note('凭据已验证并保存，原绑定尚待完成；继续不会再次请求微信。');$('bindingResume').hidden=false;
   }else{
    const reasons={
     BOOTSTRAP_TOKEN_CREDENTIAL_REJECTED:'微信未接受这组 AppID / AppSecret。',
     BOOTSTRAP_TOKEN_QUOTA_DENIED:'微信返回校验额度或频率限制。',
     BOOTSTRAP_TOKEN_ADMIN_PENDING:'微信返回管理员确认待处理。',
     BOOTSTRAP_TOKEN_ADMIN_DENIED:'微信未批准本次验证。',
     BOOTSTRAP_TOKEN_HTTP_FAILED:'微信校验未收到成功 HTTP 响应。',
     BOOTSTRAP_TOKEN_INVALID_RESPONSE:'校验响应未通过解析，不能确认凭据有效。',
     BOOTSTRAP_INVALID_JSON:'校验响应未能作为有效 JSON 读取。',
     CONNECTION_TOKEN_TIME_INVALID:'本机未能确认校验凭据的有效时间。',
     CONNECTION_REVIEW_CHANGED:'绑定期间本机账号记录发生变化。',
     CONNECTION_ENROLLMENT_CHANGED:'绑定期间本机原账号文件发生变化。',
     CONNECTION_KEYCHAIN_STORE_UNDETERMINED:'本机钥匙串保存结果未能确认。'
    },kinds={TIMEOUT:'校验连接超时。',TLS_ERROR:'校验 TLS 连接失败。',DNS_ERROR:'校验域名解析失败。',CONNECTION_ERROR:'校验连接失败。'};
    const detail=reasons[result.diagnostic?.reason]||reasons[result.error]||kinds[result.diagnostic?.kind]||'具体失败原因未记录，无法还原上次校验结果。';
    busy=true;note('未能确认原绑定结果。'+detail+' 原记录已保留；查询不会重新发送或重新绑定。');$('bindingQuery').hidden=false;
    if(result.pending_storage_changed===true)note('原绑定结果仍未知。本机存储身份无法核对，请先修复原记录，再继续验证。');
    if(result.can_revalidate===true){mayRevalidate=true;$('bindingRetry').hidden=false;note($('bindingNotice').textContent+' 密钥未保存；可选择重新验证，需本人在本页重新输入一次，旧未知记录不会改写。');}
   }
   controls();
  }
  async function cancel(){
   const oldView=view,oldOperation=operation,oldRebind=rebindTarget;rebindTarget=null;generation++;visible=false;clear();view='';operation='';busy=false;checked=false;revalidating=false;mayRevalidate=false;$('inlineBinding').hidden=true;leave();
   if(oldView){try{await call(oldRebind&&oldOperation?'REBIND_CANCEL':'BINDING_CANCEL',{view:oldView,operation:oldOperation||oldView});}catch(_){/* The original operation remains recoverable; no success claim. */}}
  }
  $('inlineBindingForm').addEventListener('submit',async event=>{
   event.preventDefault();if(busy||!view||!checked||!supported()||(rebindTarget&&!event.isTrusted))return;
   const appid=$('bindingAppID').value.trim().toLowerCase(),label=$('bindingLabel').value.trim();let secret=$('bindingSecret').value;
   if(!/^wx[a-f0-9]{16}$/.test(appid)||!secret.length||secret.length>4096||[...secret].some(c=>c.charCodeAt(0)<33||c.charCodeAt(0)>126)){note('请检查 AppID 与 AppSecret 格式。');return;}
   const epoch=generation,originalView=view,expected=rebindTarget;busy=true;selectionLocked=true;controls();$('bindingSecret').value='';note('正在准备本机安全提交…');
   try{
    const newValidation=revalidating;revalidating=false;
    const ready=expected
      ?await call('REBIND_BEGIN',{view:originalView,appid,...expected})
      :await call('BINDING_BEGIN',{view:originalView,appid,...(label?{label}:{}),...(newValidation?{revalidate_unknown:true}:{})});
    if(ready.operation)operation=ready.operation;
    if(epoch!==generation){if(ready.operation)await call(expected?'REBIND_CANCEL':'BINDING_CANCEL',{view:originalView,operation:ready.operation});return;}
    if(ready.state!=='READY'){await display(ready,epoch);return;}
    const jwe=await OASealCredential(ready.challenge,appid,secret);secret='';
    if(epoch!==generation){await call(expected?'REBIND_CANCEL':'BINDING_CANCEL',{view:originalView,operation:ready.operation});return;}
    await display(await call(expected?'REBIND_SUBMIT':'BINDING_SUBMIT',{view:originalView,operation:ready.operation,jwe}),epoch);
   }catch(_){
    if(epoch===generation){
     if(operation)await status(epoch);
     else{busy=false;note('未能准备本机安全绑定。请检查 AppID 或已有绑定；没有提交微信请求。');controls();}
    }
   }finally{secret='';}
  });
  $('bindingBack').addEventListener('click',cancel);$('bindingCancel').addEventListener('click',cancel);
  $('bindingQuery').addEventListener('click',()=>status());
  async function choosePending(appid,epoch=generation){
   if(!visible||epoch!==generation||selectionLocked)return;
   if(appid===''){
    generation++;clear();operation='';busy=false;revalidating=false;mayRevalidate=false;selectionLocked=false;
    $('bindingAppID').value='';$('bindingLabel').value='';
    for(const id of ['bindingQuery','bindingRetry','bindingResume'])$(id).hidden=true;
    note('原待完成记录已保留。现在可以填写另一个新账号，不会取消或重发原请求。');controls();$('bindingAppID').focus();return;
   }
   const target=pendingBindings.find(row=>row.appid===appid);if(!target)return;
   epoch=++generation;clear();operation='';busy=true;selectionLocked=true;revalidating=false;controls();$('bindingAppID').value=target.appid;$('bindingLabel').value=target.label||'';
   try{await display(await call('BINDING_BEGIN',{view,appid:target.appid}),epoch);}
   catch(_){if(epoch===generation){busy=true;selectionLocked=false;note('原绑定状态未能读取，尚未提交新的校验；请稍后重新打开。');controls();}}
  }
  $('bindingPending').addEventListener('change',()=>choosePending($('bindingPending').value));
  $('bindingRetry').addEventListener('click',()=>{
   if(!mayRevalidate||!view||!checked||!supported())return;
   mayRevalidate=false;revalidating=true;busy=false;$('bindingRetry').hidden=true;
   note('请重新输入一次 AppSecret 后提交。这是新的凭据校验，旧未知记录和账号归属保留，不会重放旧请求。');controls();$('bindingSecret').focus();
  });
  $('bindingResume').addEventListener('click',async()=>{
   const epoch=generation,originalView=view,originalOperation=operation;
   try{await display(await call('BINDING_RESUME',{view:originalView,operation:originalOperation}),epoch);}
   catch(_){if(epoch===generation)note('原绑定仍待本机确认，没有重新请求微信。');}
  });
  return {
   async open(target=null){
    rebindTarget=target?{connection_id:target.connection_id,binding_revision:target.binding_revision}:null;
    ui.set($('inlineBindingTitle'),target?'重新绑定公众号':'绑定公众号');
    $('bindingAppID').value=target?.account_id||'';
    $('bindingLabel').value='';
    generation++;const epoch=generation;clear();operation='';view='';visible=true;busy=false;checked=false;revalidating=false;mayRevalidate=false;selectionLocked=false;pendingBindings=[];$('bindingRetry').hidden=true;$('bindingPending').hidden=true;$('bindingPendingLabel').hidden=true;
    delete $('inlineBindingForm').dataset.channelEnvelopeSha256;
    enter();$('inlineBinding').hidden=false;controls();
    if(!supported()){note('当前内嵌环境尚未提供受支持的安全加密能力，未接收或提交密钥。');return;}
    let checkingView='';
    try{const value=await call('OPEN_BINDING',{});
     if(value.state!=='INLINE_BINDING_VIEW'||!/^([a-f0-9]{64})$/.test(value.view))throw new Error('NO_BINDING_VIEW');
     if(epoch!==generation){await call('BINDING_CANCEL',{view:value.view,operation:value.view});return;}
     const activeView=value.view;checkingView=activeView;view=activeView;note('正在建立本机安全连接…');
     pendingBindings=Array.isArray(value.pending_bindings)?value.pending_bindings.filter(row=>/^wx[a-f0-9]{16}$/.test(row.appid)&&typeof row.label==='string'):[];
     const ready=await call('BINDING_CHECK',{view:activeView});
     if(epoch!==generation)return;
     if(ready.state!=='BINDING_CHANNEL_READY')throw new Error('NO_CHANNEL_CHALLENGE');
     const jwe=await OASealCredential(ready.challenge,'wx0000000000000000','OPENAHOY_PUBLIC_CHANNEL_CHECK_V1');
     if(epoch!==generation)return;
     const expected=[...new Uint8Array(await crypto.subtle.digest('SHA-256',new TextEncoder().encode(jwe)))].map(v=>v.toString(16).padStart(2,'0')).join('');
     if(epoch!==generation)return;
     const verified=await call('BINDING_CHECK',{view:activeView,jwe});
     if(epoch!==generation)return;
     if(verified.state!=='BINDING_CHANNEL_VERIFIED'||verified.envelope_sha256!==expected)throw new Error('CHANNEL_NOT_VERIFIED');
     checked=true;$('inlineBindingForm').dataset.channelEnvelopeSha256=expected;
     if(pendingBindings.length&&!target){
      const select=$('bindingPending');select.replaceChildren();const empty=document.createElement('option');empty.value='';ui.set(empty,'选择原账号');select.append(empty);
      for(const row of pendingBindings){const option=document.createElement('option');option.value=row.appid;option.textContent=(row.label||row.appid)+' · '+row.appid;select.append(option);}
      select.hidden=false;$('bindingPendingLabel').hidden=false;
      if(pendingBindings.length===1){select.value=pendingBindings[0].appid;await choosePending(select.value,epoch);return;}
     }
     if(target){note('仅重新验证当前公众号的 AppSecret。');controls();$('bindingSecret').focus();return;}
     note(value.pending_storage_changed?'安全连接已就绪。部分原绑定记录的本机存储身份已变化，请先修复原记录，再继续验证。':value.pending_unavailable?'安全连接已就绪，但部分历史绑定记录暂不可读；它们不会自动重发。可填写新的账号，原账号请先检查诊断。':'安全连接已就绪。填写后点击一次“绑定公众号”即可。');controls();$('bindingAppID').focus();
    }catch(_){
     if(epoch===generation){checked=false;view='';note('本机安全连接暂不可用，未接收密钥；现有账号不受影响。');controls();}
     if(checkingView)try{await call('BINDING_CANCEL',{view:checkingView,operation:checkingView});}catch(_){/* Owner timer bounds a lost cancellation. */}
    }
   },dispose(){
    const oldView=view,oldOperation=operation,oldRebind=rebindTarget;rebindTarget=null;generation++;visible=false;clear();view='';operation='';busy=false;checked=false;
    if(oldView)void call(oldRebind&&oldOperation?'REBIND_CANCEL':'BINDING_CANCEL',{view:oldView,operation:oldOperation||oldView}).catch(()=>{});
   }
  };
 }
};
'''
