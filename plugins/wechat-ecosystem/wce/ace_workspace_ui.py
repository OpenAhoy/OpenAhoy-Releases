"""ACE Music's audio-workspace card and provider-specific interactions."""
HTML = """
<section id="audioAceCard" class="oa-audio-card oa-ace-card" aria-labelledby="aceTitle">
 <header class="oa-audio-card-header">
  <span class="oa-ace-brand" aria-hidden="true">ACE</span>
  <div class="oa-suno-title"><h2 id="aceTitle">ACE Music</h2><span id="aceState" class="oa-audio-badge" role="status"></span></div>
  <button id="aceRefresh" type="button">刷新 ACE Music</button>
 </header>
 <div class="oa-audio-actions">
  <button id="aceConnect" type="button">连接 ACE Music</button>
  <button id="aceCancel" type="button" hidden>取消授权等待</button>
  <button id="aceCreate" type="button">用 ACE Music 创作</button>
 </div>
 <div id="aceInfo" hidden>
  <div class="oa-audio-actions"><strong id="aceAccount"></strong><span id="acePlan" class="oa-audio-badge"></span></div>
  <dl id="aceUsage"></dl>
  <details id="aceModels" hidden><summary>可用模型</summary><ul></ul></details>
  <p id="acePermission" class="oa-audio-note"></p>
 </div>
 <details id="aceLibrary" hidden>
  <summary>ACE Music 曲库</summary>
  <p id="aceLibraryState" class="oa-audio-note"></p>
  <ul id="aceTracks"></ul><button id="aceNext" type="button" hidden>下一页</button>
 </details>
 <audio id="acePlayer" controls controlslist="nodownload" preload="none" hidden></audio>
 <p id="aceNotice" class="oa-audio-note" role="status"></p>
 <details id="aceChatConnection">
  <summary>Codex 聊天连接</summary>
  <div class="oa-audio-actions">
   <button id="aceAdd" type="button">在 Codex 中添加 ACE Music</button>
   <button id="aceGuide" type="button">ACE Music 连接说明</button>
  </div>
 </details>
</section>
"""

STYLE = """
.oa-ace-card{background:linear-gradient(150deg,var(--audio-fill),var(--audio-card) 62%)}
.oa-ace-brand{display:grid;place-items:center;flex:none;width:38px;height:38px;border-radius:10px;background:#5635c7;color:white;font-weight:800;font-size:11px;letter-spacing:.04em}
#aceUsage{display:flex;gap:6px 12px;flex-wrap:wrap;margin:6px 0;font-size:12px}
#aceUsage>div{display:flex;gap:4px;align-items:baseline}
#aceUsage dd{margin:0;font-weight:650}
#aceUsage dt{color:var(--audio-muted)}
#aceModels ul,#aceTracks{padding:0;margin:5px 0;list-style:none}
#aceModels li,#aceTracks li{min-width:0;overflow-wrap:anywhere}
#aceTracks{max-height:210px;overflow:auto}
#aceTracks li{display:flex;align-items:center;flex-wrap:wrap;gap:4px 6px;padding:4px 0;border-top:1px solid var(--audio-line)}
#aceTracks li>div:first-child{flex:1 1 120px;display:grid;gap:1px}
#aceTracks small{color:var(--audio-muted)}
"""

SCRIPT = r'''
function OAAcePanel(invoke,request,openLink,stopOther){
 const $=id=>document.getElementById(id);
 const player=$('acePlayer'),notice=$('aceNotice'),info=$('aceInfo'),library=$('aceLibrary');
 const formatter=new Intl.NumberFormat();
 let active=false,epoch=0,poll=null,busy=false,waiting=false,cursor='';
 const set=(id,key,...args)=>OAUI.set($(id),key,...args);
 const stateButtons=()=>{
   $('aceRefresh').disabled=busy||waiting;$('aceConnect').disabled=busy||waiting;
   $('aceCancel').hidden=!waiting;$('aceNext').disabled=busy||waiting;
 };
 function stop(){
   player.pause();player.removeAttribute('src');player.hidden=true;player.load();
 }
 function clear(){
   stop();info.hidden=true;library.hidden=true;cursor='';$('aceTracks').replaceChildren();
   $('aceNext').hidden=true;set('aceNotice','');set('aceConnect','连接 ACE Music');
   OAUI.raw($('aceAccount'),'');OAUI.raw($('acePlan'),'');$('aceUsage').replaceChildren();
   $('aceModels').querySelector('ul').replaceChildren();set('acePermission','');
 }
 const field=(parent,label,value)=>{
   if(!Number.isSafeInteger(value))return;
   const row=document.createElement('div'),key=document.createElement('dt'),amount=document.createElement('dd');
   OAUI.set(key,label);OAUI.raw(amount,formatter.format(value));row.append(key,amount);parent.append(row);
 };
 const link=url=>{
   try{const parsed=new URL(url);return parsed.origin==='https://acemusic.ai'&&
      !parsed.username&&!parsed.password&&!parsed.hash&&parsed.pathname.startsWith('/')?parsed.href:'';}
   catch(_){return '';}
 };
 async function go(url){
   if(url)try{await openLink(url);}catch(_){set('aceNotice','宿主未能打开官方页面。');}
 }
 function button(text,click){
   const item=document.createElement('button');item.type='button';OAUI.set(item,text);item.onclick=click;return item;
 }
 const statusLabel=code=>({
   pending:'等待中',queued:'排队中',running:'生成中',processing:'生成中',generating:'生成中',
   ready:'已完成',completed:'已完成',complete:'已完成',succeeded:'已完成',failed:'生成失败'
 }[code]);
 function show(account,data){
   info.hidden=false;set('aceConnect','重新连接 ACE Music');
   OAUI.raw($('aceAccount'),account.display_name||account.username||'');
   OAUI.raw($('acePlan'),account.plan||'');$('acePlan').hidden=!account.plan;
   const usage=$('aceUsage');usage.replaceChildren();
   field(usage,'剩余 Credits',account.credits);field(usage,'每次生成 Credits',account.generation_cost);
   const models=$('aceModels').querySelector('ul');models.replaceChildren();
   for(const model of account.models||[]){
     const line=document.createElement('li');
     if(Number.isSafeInteger(model.cost))OAUI.set(line,'{0} · {1} Credits',model.name,formatter.format(model.cost));
     else OAUI.raw(line,model.name);
     models.append(line);
   }
   $('aceModels').hidden=!models.childElementCount;
   set('acePermission',account.can_download===false?'此账号的 MCP 下载需要付费套餐。':
       account.can_download===true?'ACE Music 已确认下载权限。':'');
   library.hidden=false;const list=$('aceTracks');list.replaceChildren();
   cursor=data?.cursor||'';$('aceNext').hidden=!cursor;
   set('aceLibraryState',!data?'暂时无法读取 ACE Music 曲库。':data.items.length?'':'没有曲目。');
   for(const track of data?.items||[]){
     const row=document.createElement('li'),label=document.createElement('div'),title=document.createElement('strong'),status=document.createElement('small');
     OAUI.raw(title,track.title||track.id);
     if(statusLabel(track.status))OAUI.set(status,statusLabel(track.status));else OAUI.raw(status,track.status||'');
     label.append(title,status);row.append(label);
     const playback=link(track.play),page=link(track.page);
     if(playback)row.append(button('播放',async()=>{
       if(!active)return;stopOther();stop();player.src=playback;player.hidden=false;
       await player.play().catch(()=>set('aceNotice','音频已就绪，请点击播放器播放。'));
     }));
     if(page)row.append(button('在 ACE Music 打开',()=>void go(page)));
     const ready=statusLabel(track.status)==='已完成'&&/^[A-Za-z0-9_-]{1,96}$/.test(track.id);
     if(ready&&!playback)row.append(button('在 Codex 试听',event=>{
       if(!event.isTrusted||!active)return;
       void request('请用当前聊天独立的 ACE Music（ace-music）官方 MCP，调用只读 show_songs，ids 只传原曲 '+track.id+'，打开该曲官方播放器。若聊天不支持播放器，给出官方返回的歌曲页，或引导我在同一 ACE Music 账号的官网曲库打开。不要生成、下载、分享或改动曲目权限。',notice);
     }));
     if(track.can_download===false){
       const hint=document.createElement('small');OAUI.set(hint,'MCP 下载需要付费套餐');row.append(hint);
     }else if(ready){
       row.append(button('检查权限并导入',event=>{
         if(!event.isTrusted||!active)return;
         void request('请用当前聊天独立的 ACE Music（ace-music）官方 MCP 查询原歌曲 ID '+track.id+'。先调用 get_account 核对当前账号和下载权限，再用 get_song 的 ids 参数核对该 ID、曲名及终态。只有官方允许下载时才对这一原曲调用 download_song 获取 MP3，再将获准文件保存到 media.library.prepare 返回的项目根，用计算的 SHA-256 和项目相对路径调用 audio.project.import，provider 为 ace-music，provider_id 为原曲 ID。报告原曲和本机资产的对应关系。遇到 plan_required、账号不符或没有实际下载文件时停在原曲查看，不转用播放地址保存文件，不生成歌曲、不升级套餐。',notice);
       }));
     }
     list.append(row);
   }
 }
 async function refresh(next=''){
   const here=++epoch;busy=true;stateButtons();set('aceState','正在读取 ACE Music…');set('aceNotice','');
   try{
     const result=await invoke('ace_snapshot',next?{cursor:next}:{});
     if(!active||here!==epoch)return;
     if(result.state==='CONNECTED'){set('aceState','已连接');show(result.account,result.library);return;}
     clear();
     set('aceState',result.code==='ACE_CODEX_AUTH_REQUIRED'?'未连接':'暂时无法读取 ACE Music 连接。');
   }catch(_){if(active&&here===epoch){clear();set('aceState','暂时无法读取 ACE Music 连接。');}}
   finally{if(active&&here===epoch){busy=false;stateButtons();}}
 }
 function trackAuth(result,here){
   if(!active||here!==epoch)return;
   busy=false;waiting=['AUTHORIZING','CANCELLING'].includes(result.state);stateButtons();
   if(result.state==='AUTHORIZED'){void refresh();return;}
   if(result.state==='IDLE'){void refresh();return;}
   if(!waiting){
     set('aceState',{
       AUTHORIZING_ELSEWHERE:'另一个窗口正在等待 ACE Music 授权。',
       CANCELLED:'已取消等待。可重新连接。',
       AUTH_EXPIRED:'授权等待已结束。可重新连接。',
       AUTH_FAILED:'授权未确认。可重新连接或刷新。'
     }[result.state]||'授权未确认。可重新连接或刷新。');
     return;
   }
   set('aceState',result.state==='CANCELLING'?'正在停止授权等待…':'请在 ACE Music 官方页面登录目标账号并完成授权。');
   poll=setTimeout(()=>void auth('ace_oauth_status',here),1200);
 }
 async function auth(action,here){
   try{trackAuth(await invoke(action),here);}
   catch(_){if(active&&epoch===here){busy=waiting=false;stateButtons();set('aceState','授权未确认。可重新连接或刷新。');}}
 }
 $('aceConnect').onclick=event=>{
   if(!event.isTrusted||!active||busy||waiting)return;
   clear();busy=true;stateButtons();set('aceState','正在启动 ACE Music 授权…');
   void auth('ace_oauth_begin',++epoch);
 };
 $('aceCancel').onclick=event=>{
   if(!event.isTrusted||!active||!waiting||busy)return;
   clearTimeout(poll);busy=true;stateButtons();void auth('ace_oauth_cancel',++epoch);
 };
 $('aceRefresh').onclick=event=>{if(event.isTrusted&&active&&!busy&&!waiting)void refresh();};
 $('aceNext').onclick=()=>{if(active&&cursor&&!busy&&!waiting)void refresh(cursor);};
 $('aceGuide').onclick=()=>void go('https://acemusic.ai/help/articles/connect-ace-music-to-your-ai-assistant/');
 $('aceAdd').onclick=event=>{
   if(!event.isTrusted)return;
   void request('请先用官方 Codex MCP 配置核对是否已有独立的 ace-music。仅在该条目不存在时添加固定的 Streamable HTTP 地址 https://acemusic.ai/mcp，保留既有连接；同名若指向其他端点，请先告诉我。使用 Codex 官方支持的会话重载方式，回读当前聊天是否有该服务器工具。有 OAuth 时复用；需要授权时让我本人在 Jiusera「设置 → 模型管理 → L-unify · 音乐」完成。只检查目录和配置；不生成、上传或下载。',notice);
 };
 $('aceCreate').onclick=event=>{
   if(!event.isTrusted)return;
   void request('用当前聊天独立的 ACE Music（ace-music）官方 MCP 策划一首歌。先用 get_skill 的 name=lyrics 读取官方创作要求，调用 get_account 核对方案、剩余 Credits、模型和当前费用。根据当前 brief 准备标题、歌词和制作提示，先给我看方案与官方报价。在我明确授权这次费用后，仅提交一次 create_song，保留返回的全部原歌曲 ID，并用 get_song 的 ids 参数查询这些 ID。失败或结果未知时先核对原任务，不重复生成或新扣费。',notice);
 };
 player.onerror=()=>{if(active&&!player.hidden)set('aceNotice','无法在此面板播放。');};
 return {open({manage}){
   active=true;busy=waiting=false;stateButtons();
   set('aceState',manage?'未确认连接':'点击「刷新 ACE Music」读取已有连接。');
   if(manage)void auth('ace_oauth_status',++epoch);
 },close(){
   active=false;++epoch;clearTimeout(poll);busy=waiting=false;clear();
 },stop};
}
'''
