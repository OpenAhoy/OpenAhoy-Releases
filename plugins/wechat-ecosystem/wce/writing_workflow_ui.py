"""Offline import and explicit rollback in About & Settings."""

HTML = '''
<section class="wb-about-card" aria-labelledby="writingRulesTitle">
 <h2 id="writingRulesTitle">写作规则</h2>
 <details id="writingRules">
  <summary>管理规则版本</summary>
  <p id="writingRulesStatus" role="status"></p>
  <div class="wb-context">
   <select id="writingRulesVersion" aria-label="写作规则版本" disabled></select>
   <button id="writingRulesActivate" type="button" disabled>切换版本</button>
   <button id="writingRulesImport" type="button" disabled>导入并启用规则包</button>
   <input id="writingRulesFile" type="file" accept=".json,application/json" hidden>
  </div>
 </details>
</section>
'''

SCRIPT = r'''
function OAWritingRules(call){
 const $=id=>document.getElementById(id);
 const panel=$('writingRules'),status=$('writingRulesStatus'),versions=$('writingRulesVersion');
 const activate=$('writingRulesActivate'),picker=$('writingRulesFile'),load=$('writingRulesImport');
 let state=null,busy=false;
 const messages={
   WRITING_RULE_DIGEST_MISMATCH:'规则包摘要不匹配。',
   WRITING_RULE_INCOMPATIBLE:'规则包与当前写作系统不兼容。',
   WRITING_RULE_INVALID:'无法读取此规则包。',
   WRITING_RULE_VERSION_CONFLICT:'此版本已有不同的规则内容。',
   WRITING_RULE_SELECTION_CHANGED:'当前版本已在另一页面改变，请重试。',
 };
 function controls(){
   versions.disabled=load.disabled=busy||!state;
   activate.disabled=versions.disabled||versions.value===state.active.version;
 }
 function render(value){
   state=value;
   versions.replaceChildren(...value.versions.map(row=>{
     const option=document.createElement('option');option.value=row.version;option.textContent=row.version;return option;
   }));
   versions.value=value.active.version;
   OAUI.set(status,'当前规则 v{0}',value.active.version);
 }
 async function refresh(request={action:'state'}){
   if(busy)return;
   busy=true;controls();
   try{
     const value=await call(request);
     if(!value||value.state!=='WRITING_RULES_READY')throw Error('WRITING_RULE_INVALID');
     render(value);
   }catch(problem){
     const explanation=messages[problem.message]||'暂时无法读取写作规则。';
     try{render(await call({action:'state'}));}
     catch(_){state=null;versions.replaceChildren();}
     if(state)OAUI.set(status,'{0} 当前规则 v{1}',OAUI.format(explanation),state.active.version);
     else OAUI.set(status,explanation);
   }finally{
     busy=false;controls();
   }
 }
 panel.addEventListener('toggle',()=>{if(panel.open)void refresh();});
 versions.onchange=controls;
 activate.onclick=()=>{
   const reference=state?.versions.find(row=>row.version===versions.value);
   if(!busy&&reference)void refresh({action:'activate',expected:state.active,reference});
 };
 load.onclick=()=>{if(!busy)picker.click();};
 picker.onchange=async()=>{
   const file=picker.files?.[0];
   picker.value='';
   if(!file||busy||!state)return;
   if(file.size>16384){OAUI.set(status,'规则包超过 16 KiB。');return;}
   const expected=state.active;
   busy=true;controls();
   let package_text;
   try{package_text=await file.text();}
   catch(_){OAUI.set(status,'无法读取此规则包。');return;}
   finally{busy=false;controls();}
   await refresh({action:'install',package_text,expected});
 };
}
'''
