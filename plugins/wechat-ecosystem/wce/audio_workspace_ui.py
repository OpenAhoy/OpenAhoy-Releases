"""Audio workbench, provider status and playback in the management app."""
from base64 import b64encode
from pathlib import Path

from . import ace_workspace_ui

BRAND = b64encode((Path(__file__).resolve().parents[1] / 'assets/management/suno-favicon.ico').read_bytes()).decode('ascii')

HTML = """
<section id="audioWorkspace" aria-labelledby="audioPageTitle" hidden>
<h2 id="audioPageTitle" class="oa-audio-sr">音乐供应商与曲库</h2>
<p id="audioActionNotice" class="oa-audio-note" role="status" aria-live="polite"></p>
<textarea id="audioCopy" aria-label="复制 Codex 指令" readonly hidden></textarea>

<form id="musicProviderForm" class="oa-audio-card" aria-labelledby="musicProviderTitle">
 <div class="oa-music-setting-heading">
  <label id="musicProviderTitle" for="musicProviderChoice">默认音乐供应商</label>
  <div class="oa-music-controls">
   <select id="musicProviderChoice" disabled>
    <option value="" disabled>请选择</option><option value="suno">Suno</option><option value="ace-music">ACE Music</option>
   </select>
   <button id="musicProviderSave" class="primary" type="button" disabled>保存选择</button>
  </div>
 </div>
 <p class="oa-audio-note">应用于本机所有项目和窗口中未指定供应商的新歌曲与新配乐。</p>
 <p id="musicProviderStatus" class="oa-audio-note" role="status"></p>
</form>
<div id="musicActions">
 <div class="oa-audio-actions">
  <button id="musicCreateDefault" type="button">创作歌曲</button><button id="musicScoreDefault" type="button">视频配乐</button>
 </div>
 <p id="musicProviderRequest" class="oa-audio-note" role="status"></p>
</div>
<nav class="oa-audio-provider-nav" aria-label="音频供应商">
 <button id="audioProviderSuno" type="button" aria-controls="audioSunoCard" aria-pressed="true">Suno</button>
 <button id="audioProviderAce" type="button" aria-controls="audioAceCard" aria-pressed="false">ACE Music</button>
</nav>
<div class="oa-audio-dashboard" data-provider-view="suno">
 <section id="audioSunoCard" class="oa-audio-card oa-suno-card" aria-labelledby="sunoTitle">
  <header class="oa-audio-card-header">
   <img class="oa-suno-brand" src="data:image/x-icon;base64,__SUNO_BRAND__" alt="" width="38" height="38">
   <div class="oa-suno-title"><h2 id="sunoTitle">Suno</h2><span id="sunoState" class="oa-audio-badge" role="status"></span></div>
   <button id="sunoRefresh" type="button">刷新 Suno</button>
  </header>
  <div id="sunoInfo" hidden>
   <div class="oa-suno-identity">
    <img id="sunoAvatar" alt="" width="36" height="36" referrerpolicy="no-referrer" hidden>
    <span id="sunoInitial" aria-hidden="true"></span>
    <div><strong id="sunoAccount"></strong><span id="sunoHandle"></span></div>
    <span id="sunoPlan" class="oa-audio-badge"></span>
   </div>
   <div id="sunoUsage" class="oa-suno-usage"></div>
   <p id="sunoReadAt" class="oa-audio-note"></p>
   <details id="sunoModels" hidden><summary>模型与功能</summary><div></div></details>
  </div>
  <div class="oa-audio-actions"><button id="audioCreate" type="button">用 Suno 创作</button></div>
  <button id="sunoHelp" type="button" hidden>查看 Suno 官方连接说明</button>
  <details id="sunoLibrary" hidden>
   <summary>Suno 曲库</summary>
   <div class="oa-audio-actions oa-suno-actions">
    <button id="sunoAll" type="button" aria-pressed="true">全部曲目</button>
    <button id="sunoPlayable" type="button" aria-pressed="false">曾下载曲目</button>
    <button id="sunoNext" type="button" hidden>下一页</button>
   </div>
   <p id="sunoLibraryState" class="oa-audio-note" role="status"></p>
   <ul id="sunoTracks"></ul>
  </details>
 </section>
 __ACE_CARD__
 <section class="oa-audio-card oa-audio-monitor" aria-labelledby="audioMonitorTitle">
  <h2 id="audioMonitorTitle">任务与用量</h2>
  <p id="audioMonitorLocal"></p><ul id="audioRecent"></ul>
  <p id="audioMonitorRemote" class="oa-audio-note"></p>
  <p class="oa-audio-note">单次扣费以供应商回执为准。当前曲库未提供逐笔扣费。</p>
 </section>
</div>

<div class="oa-audio-workspace">
 <section class="oa-audio-card oa-audio-local" aria-labelledby="audioLibraryTitle">
  <div class="oa-audio-section-heading"><h2 id="audioLibraryTitle">本机音频库</h2><button id="audioReload" type="button">刷新音频库</button></div>
  <ul id="audioList"></ul><p id="audioEmpty" class="oa-audio-note"></p>
 </section>
 <section class="oa-audio-card oa-audio-preview" aria-labelledby="audioPreviewTitle">
  <div class="oa-audio-section-heading"><h2 id="audioPreviewTitle">播放与下载</h2><button id="audioDownload" type="button" disabled>下载原文件</button></div>
  <strong id="audioTitle"></strong>
  <p id="audioEmptyPreview" class="oa-audio-note">选择音频或配乐开始预览。</p>
  <audio id="audioPlayer" controls preload="none" hidden></audio>
  <video id="audioMixPlayer" controls playsinline preload="none" hidden></video>
  <div class="oa-audio-actions" id="audioVersions" hidden><button id="audioOriginal" type="button">原片</button>
   <button id="audioMixed" type="button">配乐版</button></div>
  <p id="audioNotice" class="oa-audio-note" role="status" aria-live="polite"></p>
  <p id="sunoPlaybackState" class="oa-audio-note" role="status"></p>
  <audio id="sunoPlayer" controls controlslist="nodownload" preload="none" hidden></audio>
 </section>
</div>
</section>
""".replace('__SUNO_BRAND__', BRAND).replace('__ACE_CARD__', ace_workspace_ui.HTML)

STYLE = """
#audioWorkspace[hidden],#audioWorkspace [hidden]{display:none!important}
#audioWorkspace .oa-audio-sr{position:absolute;width:1px;height:1px;overflow:hidden;clip-path:inset(50%)}
#audioWorkspace[data-mode=models] :is(#musicActions,#audioCreate,#aceCreate,#sunoLibrary,#aceLibrary,.oa-audio-monitor,.oa-audio-workspace,.oa-audio-provider-nav){display:none}
#audioWorkspace[data-mode=production] :is(#musicProviderForm,#sunoHelp,#aceConnect,#aceCancel,#aceChatConnection){display:none}
#audioWorkspace{--audio-card:var(--surface,#fff);--audio-ink:var(--ink,CanvasText);--audio-muted:var(--muted,#536964);--audio-line:var(--line,#dbe5e1);--audio-fill:var(--oa-fill,#eef5f1);display:flex;flex:1;flex-direction:column;gap:12px;min-width:0;min-height:0;overflow:auto;padding:1px 3px 8px;color:var(--audio-ink);font-family:Inter,"PingFang SC",system-ui,sans-serif;font-size:13px}
#openAudioWorkspace[aria-current=page]{background:var(--management-selected,var(--line));font-weight:650}
#audioWorkspace h1,#audioWorkspace h2,#audioWorkspace p{margin:0}
#audioWorkspace h1{font-size:clamp(20px,2.5vw,27px);letter-spacing:-.03em}
#audioWorkspace h2{font-size:15px;line-height:1.35}
.oa-audio-heading,.oa-audio-actions,.oa-audio-section-heading,.oa-suno-identity,.oa-audio-card-header{display:flex;align-items:center;gap:8px;min-width:0}
.oa-audio-heading,.oa-audio-section-heading{justify-content:space-between}
.oa-audio-heading{gap:12px;padding:3px 0 4px;flex-wrap:wrap}
.oa-audio-heading p,.oa-audio-note{color:var(--audio-muted);font-size:12px;line-height:1.5}
.oa-audio-note:empty,#audioTitle:empty{display:none}
.oa-audio-actions{flex-wrap:wrap}
#audioWorkspace button{min-height:30px;max-width:100%;white-space:normal}
.oa-audio-dashboard,.oa-audio-workspace{display:grid;gap:10px;align-items:stretch}
.oa-audio-dashboard{grid-template-columns:repeat(2,minmax(0,1fr))}
.oa-audio-monitor{grid-column:1/-1}
#musicProviderForm{gap:5px;background:linear-gradient(100deg,var(--audio-fill),var(--audio-card) 75%)}
#musicProviderTitle{font-size:14px;font-weight:650}
.oa-music-setting-heading{display:flex;align-items:center;justify-content:space-between;flex-wrap:wrap;gap:6px}
.oa-music-controls{display:flex;align-items:center;min-width:0;gap:6px}
#musicProviderChoice{min-height:30px;min-width:0;padding:3px 6px}
#musicProviderSave{width:auto;flex:none}
.oa-audio-provider-nav{display:none;gap:5px}
.oa-audio-provider-nav button{flex:1}
.oa-audio-provider-nav button[aria-pressed=true]{background:var(--audio-fill);border-color:var(--accent,var(--audio-line))}
@media(max-width:600px){#audioWorkspace[data-mode=production] .oa-audio-provider-nav{display:flex}
 #audioWorkspace[data-mode=production] :is([data-provider-view=suno] #audioAceCard,[data-provider-view=ace] #audioSunoCard){display:none}}
.oa-audio-workspace{grid-template-columns:minmax(160px,1fr) minmax(0,1.6fr)}
.oa-audio-card{min-width:0;min-height:0;display:flex;flex-direction:column;gap:9px;padding:12px;border:1px solid var(--audio-line);border-radius:12px;background:var(--audio-card)}
.oa-suno-card{background:linear-gradient(150deg,var(--audio-fill),var(--audio-card) 62%)}
.oa-suno-brand{flex:none;object-fit:contain;border-radius:10px}
.oa-suno-title{display:grid;flex:1;gap:3px;min-width:0}
.oa-suno-title h2{font-size:16px}
.oa-audio-badge{align-self:start;width:fit-content;max-width:100%;background:var(--audio-fill);border-radius:5px;padding:2px 6px;color:var(--audio-ink);font-weight:600;font-size:11px;overflow-wrap:anywhere}
.oa-suno-identity{margin-bottom:8px}
.oa-suno-identity img,#sunoInitial{flex:none;border-radius:50%;object-fit:cover}
#sunoInitial{display:grid;place-items:center;width:36px;height:36px;background:var(--audio-fill);font-weight:650}
.oa-suno-identity>div{display:grid;min-width:0;overflow-wrap:anywhere}
.oa-suno-identity .oa-audio-badge{margin-inline-start:auto;align-self:center}
#sunoHandle{color:var(--audio-muted);font-size:11px}
.oa-suno-usage{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:5px;margin-bottom:5px}
.oa-suno-metric{display:grid;gap:1px;padding:5px 7px;border:1px solid var(--audio-line);border-radius:7px;background:var(--audio-card);min-width:0;overflow-wrap:anywhere}
.oa-suno-metric>span{font-size:11px;color:var(--audio-muted)}
.oa-audio-monitor>p:not(.oa-audio-note){font-size:14px;font-weight:600}
#audioRecent{padding:0;margin:0;list-style:none;display:grid;gap:5px;font-size:12px}
#audioRecent li{display:grid;gap:3px;padding:6px 0;border-top:1px solid var(--audio-line);min-width:0;overflow-wrap:anywhere}
.oa-audio-task-heading,.oa-audio-task-facts{display:flex;align-items:baseline;justify-content:space-between;flex-wrap:wrap;gap:3px 7px}
.oa-audio-task-facts{font-size:11px;color:var(--audio-muted)}
.oa-audio-task-heading>strong{flex:1 1 100px;min-width:0}
.oa-audio-task-heading>span{font-size:11px;color:var(--audio-muted)}
#audioWorkspace summary{cursor:pointer;font-weight:600;font-size:12px}
#audioWorkspace details>div{margin-top:6px;overflow-wrap:anywhere}
#audioList,#sunoTracks{padding:0;margin:0;list-style:none;display:grid;gap:4px;max-height:232px;overflow:auto}
#audioList button{display:grid;gap:1px;width:100%;text-align:start;overflow-wrap:anywhere}
#audioList button[aria-pressed=true]{background:var(--audio-fill);border-color:var(--accent,var(--audio-line))}
#audioList span{font-size:11px;color:var(--audio-muted)}
#sunoTracks li{display:flex;align-items:center;gap:4px;flex-wrap:wrap;padding:3px 0}
#sunoTracks li>span{flex:1 1 105px;min-width:0;overflow-wrap:anywhere}
#audioWorkspace :is(audio,video){width:100%;min-width:0;max-height:35dvh}
#audioCopy{width:100%;min-height:66px;resize:vertical}
@media(max-width:600px){.oa-audio-dashboard,.oa-audio-workspace{grid-template-columns:minmax(0,1fr)}}
""" + ace_workspace_ui.STYLE

SCRIPT = ace_workspace_ui.SCRIPT + r'''
const OAMusicRequest=(kind,asset=null)=>{
 const routing='开始规划任何需要新生成的音乐前，调用模型可见的 audio.music.provider.read 读取本机最新默认音乐供应商。若我明确点名供应商，则按本次明确选择。只使用该供应商对应的官方 MCP 和随包 video-director 指引，确认当前聊天可调用，再核对账号、模型和官网费用。若偏好无法读取，或所选服务未连接、工具不可用，告诉我原因和连接入口，停止生成。不要换用另一家。给出方案和实际费用后，只有我明确授权本次提交时才调用一次，后续按原任务查询。';
 if(kind==='song')return '帮我构思一首歌。先沿当前 brief 或确认主题，准备标题、歌词、风格与人声。'+routing;
 const source=asset?' 当前原视频项目 '+asset.project+'，原视频任务 '+asset.attempt+'。':' 请从当前聊天确认原视频。';
 return '帮我给视频配乐。可使用我明确选定的现有曲目，沿原素材 ID、本机统一音频库和 audio.project.mix 混合。跨项目时使用各自实际项目 ID。需要创作新配乐时，先按画面确认节奏、入点和原声处理。'+source+routing;
};
const OAAudioWorkspace=(call,send,openLink,canSend)=>{
 const $=id=>document.getElementById(id);
 const list=$('audioList'),download=$('audioDownload'),notice=$('audioNotice');
 const audio=$('audioPlayer'),movie=$('audioMixPlayer'),copy=$('audioCopy');
 let active=false,refreshEpoch=0,selection=0,row=null,sending=false,videoIntent=null;
 const invoke=(action,args={})=>call('wce.ui.video.workspace',{action,...args});
 const sunoLibrary=$('sunoLibrary'),sunoPlayer=$('sunoPlayer');
 const ace=OAAcePanel(invoke,request,openLink,()=>{stopSuno();clear();});
 const musicChoice=$('musicProviderChoice'),musicSave=$('musicProviderSave'),musicStatus=$('musicProviderStatus');
 let musicEpoch=0,musicBusy=false,musicRecord=null;
 function musicControls(){
   musicChoice.disabled=musicBusy||!musicRecord;
   musicSave.disabled=musicBusy||!musicRecord||musicChoice.value===musicRecord.provider;
 }
 function showMusic(value){
   musicRecord=value?.state==='READY'&&['suno','ace-music'].includes(value.provider)&&Number.isSafeInteger(value.revision)?value:null;
   musicChoice.value=musicRecord?.provider||'';
   musicControls();
 }
 async function syncMusic(change=null){
   if(musicBusy)return;
   const capture=++musicEpoch;
   musicBusy=true;musicControls();
   const current=()=>active&&capture===musicEpoch;
   OAUI.set(musicStatus,change?'正在保存默认供应商…':'正在读取默认供应商…');
   try{
     let value;
     try{
       value=change?await invoke('music_provider_save',change):await invoke('music_provider_read');
     }catch(error){
       if(!change||!current())throw error;
       value={...await invoke('music_provider_read'),save_status:'FAILED'};
     }
     if(!current())return;
     showMusic(value);
     if(!musicRecord)OAUI.set(musicStatus,'无法确认本机默认供应商。');
     else if(value.save_status==='STALE')OAUI.set(musicStatus,'其他窗口已改动。已显示本机当前选择。');
     else if(value.save_status==='FAILED')OAUI.set(musicStatus,'保存未确认。已显示本机当前选择。');
     else if(change)OAUI.set(musicStatus,'已保存到本机');
     else OAUI.set(musicStatus,'');
   }catch(_){
     if(current()){showMusic(null);OAUI.set(musicStatus,'无法确认本机默认供应商。');}
   }finally{
     if(current()){musicBusy=false;musicControls();}
   }
 }
 musicChoice.onchange=musicControls;
 musicSave.onclick=event=>{
   if(event.isTrusted&&active&&!musicSave.disabled)void syncMusic({provider:musicChoice.value,expected_revision:musicRecord.revision});
 };
 function refreshMusicOnFocus(){
   if(active&&!document.hidden&&!musicBusy&&(!musicRecord||musicChoice.value===musicRecord.provider))void syncMusic();
 }
 window.addEventListener('focus',refreshMusicOnFocus);
 document.addEventListener('visibilitychange',refreshMusicOnFocus);
 let sunoEpoch=0,sunoActivity=0,sunoHandle='',sunoCursor='',sunoNext='',sunoDownloaded=false;
 function stopSuno(){
   sunoActivity++;sunoPlayer.pause();sunoPlayer.removeAttribute('src');sunoPlayer.load();sunoPlayer.hidden=true;
   OAUI.set($('sunoPlaybackState'),'');
 }
 function sunoButtons(busy){
   for(const id of ['sunoRefresh','sunoAll','sunoPlayable','sunoNext'])$(id).disabled=busy;
   for(const button of $('sunoTracks').querySelectorAll('button'))button.disabled=busy;
 }
 const sunoError={
  SUNO_CODEX_AUTH_REQUIRED:'没有可用的 Suno 授权。可在 Codex 的 MCP 设置查看连接。',
  SUNO_CODEX_AUTH_CHECK_UNAVAILABLE:'暂时无法核对已有 Suno 授权。',
  SUNO_CODEX_ACCOUNT_CHANGED:'Suno 账号已切换，请刷新。',
  SUNO_PLAYBACK_REQUIRES_CREDIT:'此播放格式需要下载额度，未扣除。',
  SUNO_PLAYBACK_PREPARING:'Suno 正在准备音频，请稍后再试。',
  SUNO_PREVIOUS_DOWNLOAD_REQUIRED:'这首曲目已不在曾下载的列表中，请刷新。'
 };
 const readableDate=seconds=>Number.isFinite(seconds)?new Intl.DateTimeFormat(undefined,{dateStyle:'short',timeStyle:'short'}).format(new Date(seconds*1000)):'';
 const assetName=asset=>[asset.project_label,asset.account_label,asset.title].filter(Boolean).join(' · ');
 const number=n=>Number.isSafeInteger(n)?new Intl.NumberFormat().format(n):OAUI.message('未提供');
 function showSunoUsage(usage, readAt){
   const values=$('sunoUsage');values.replaceChildren();
   const models=$('sunoModels'),plan=$('sunoPlan');
   OAUI.raw(plan,'');plan.hidden=!usage?.plan;
   const unit=usage?.period==='year'?OAUI.message('年付'):usage?.period==='month'?OAUI.message('月付'):usage?.period;
   if(usage?.plan)OAUI.set(plan,'{0}',[usage.plan,unit].filter(Boolean));
   OAUI.set($('sunoReadAt'),readAt?'读回时间 {0}':'',readableDate(readAt));
   if(!usage){OAUI.set(values,'暂时无法读取 Suno 用量。');models.hidden=true;return;}
   function item(label,value){
     const metric=document.createElement('div');metric.className='oa-suno-metric';
     const title=document.createElement('span'),amount=document.createElement('strong');
     OAUI.set(title,label);OAUI.set(amount,'{0}',value);metric.append(title,amount);values.append(metric);
   }
   item('剩余生成额度',number(usage.credits_remaining));
   item('剩余下载额度',number(usage.download_credits_remaining));
   item('本月用量 / 上限',OAUI.message('{0} / {1}',number(usage.monthly_usage),number(usage.monthly_limit)));
   if(usage.cancel_on)item('到期',usage.cancel_on);
   else if(usage.renews_on)item('续订',usage.renews_on);
   const details=models.querySelector('div');details.replaceChildren();
   for(const [key,items] of [['可用模型',usage.models],['可用功能',usage.features]]){
     if(!items?.length)continue;
     const item=document.createElement('p');OAUI.set(item,'{0} · {1}',OAUI.message(key),items.join(' · '));details.append(item);
   }
   models.hidden=!details.childElementCount;
 }
 async function playSuno(track){
   if(!active||!sunoDownloaded||!sunoHandle)return;
   clear();ace.stop();stopSuno();
   const epoch=sunoEpoch,activity=sunoActivity;
   const current=()=>active&&epoch===sunoEpoch&&activity===sunoActivity;
   OAUI.set($('sunoPlaybackState'),'正在准备播放…');
   sunoButtons(true);
   try{
     const value=await invoke('suno_playback',{track:track.id,expected:sunoHandle,...(sunoCursor?{cursor:sunoCursor}:{})});
     if(!current())return;
     if(value.state!=='PLAYBACK_READY'){
       OAUI.set($('sunoPlaybackState'),sunoError[value.code]||'无法取得 Suno 播放音频。');return;
     }
     const url=new URL(value.url);
     if(url.origin!=='https://suno-data-uploads.s3.amazonaws.com'||!url.pathname.startsWith('/studio/uploads/'))throw new Error();
     sunoPlayer.src=url.href;sunoPlayer.hidden=false;$('audioEmptyPreview').hidden=true;
     OAUI.raw($('sunoPlaybackState'),track.title);
     await sunoPlayer.play().catch(error=>{
       if(current()&&error.name==='NotAllowedError')OAUI.set($('sunoPlaybackState'),'音频已就绪，请点击播放器播放。');
       else throw error;
     });
   }catch(_){if(current())OAUI.set($('sunoPlaybackState'),'无法在此面板播放。');}
   finally{if(current())sunoButtons(false);}
 }
 sunoPlayer.addEventListener('error',()=>{if(active&&!sunoPlayer.hidden)OAUI.set($('sunoPlaybackState'),'无法在此面板播放。');});
 function showSunoTracks(library){
   const list=$('sunoTracks');list.replaceChildren();
   sunoNext=library?.cursor||'';$('sunoNext').hidden=!sunoNext;
   OAUI.set($('audioMonitorRemote'),library?'Suno 曲库已读回。进行中的任务以原回执为准。':'等待读取 Suno 曲库。');
   OAUI.set($('sunoLibraryState'),!library?'暂时无法读取 Suno 曲库。':
     !library.items.length?'没有曲目。':sunoDownloaded?'可播放已下载的 MP3，播放不会确认新的额度扣费。':'');
   for(const track of library?.items||[]){
     const li=document.createElement('li'),name=document.createElement('span');
     OAUI.raw(name,track.title||track.id);li.append(name);
     const button=document.createElement('button');button.type='button';
     if(sunoDownloaded&&track.status==='complete'){
       OAUI.set(button,'播放');button.onclick=()=>void playSuno(track);li.append(button);
     }
     if(track.song_url){
       const open=document.createElement('button');open.type='button';
       OAUI.set(open,'在 Suno 打开');open.onclick=()=>void openLink(track.song_url).catch(()=>OAUI.set($('sunoPlaybackState'),'宿主未能打开官方页面。'));
       li.append(open);
     }
     list.append(li);
   }
 }
 async function refreshSuno({downloaded=sunoDownloaded,cursor='',expect=sunoHandle,libraryOnly=false}={}){
   const epoch=++sunoEpoch;stopSuno();sunoButtons(true);
   OAUI.set($('sunoState'),'正在读取 Suno…');
   try{
     const value=await invoke('suno_snapshot',{downloaded,library_only:libraryOnly,...(cursor?{cursor}:{}),...(expect?{expected:expect}:{})});
     if(!active||epoch!==sunoEpoch)return;
     if(value.state!=='CONNECTED'){
       OAUI.set($('sunoState'),sunoError[value.code]||'暂时无法读取 Suno 连接。');
       sunoHandle='';$('sunoInfo').hidden=true;sunoLibrary.hidden=true;$('sunoHelp').hidden=false;showSunoTracks(null);return;
     }
     sunoHandle=value.account.handle;sunoDownloaded=downloaded;sunoCursor=cursor;
     OAUI.set($('sunoState'),'已连接');
     OAUI.raw($('sunoAccount'),value.account.display_name||sunoHandle);
     OAUI.raw($('sunoHandle'),'@'+sunoHandle);
     const avatar=$('sunoAvatar');
     const safeAvatar=/^https:\/\/cdn[12]\.suno\.ai\//.test(value.account.avatar_url||'');
     if(safeAvatar)avatar.src=value.account.avatar_url;else avatar.removeAttribute('src');
     avatar.hidden=!safeAvatar;
     OAUI.raw($('sunoInitial'),(value.account.display_name||sunoHandle).slice(0,1));
     $('sunoInitial').hidden=safeAvatar;
     $('sunoHelp').hidden=true;$('sunoInfo').hidden=false;sunoLibrary.hidden=false;
     $('sunoAll').setAttribute('aria-pressed',String(!downloaded));
     $('sunoPlayable').setAttribute('aria-pressed',String(downloaded));
     if(value.usage_checked!==false)showSunoUsage(value.usage,value.read_at);
     showSunoTracks(value.library);
   }catch(_){
     if(active&&epoch===sunoEpoch){
       OAUI.set($('sunoState'),'暂时无法读取 Suno 连接。');
       sunoHandle='';$('sunoInfo').hidden=true;sunoLibrary.hidden=true;$('sunoHelp').hidden=false;showSunoTracks(null);
     }
   }finally{if(active&&epoch===sunoEpoch)sunoButtons(false);}
 }
 $('sunoRefresh').onclick=event=>{
   if(event.isTrusted&&active&&!$('sunoRefresh').disabled)void refreshSuno({expect:''});
 };
 $('sunoHelp').onclick=()=>void openLink('https://help.suno.com/en/articles/14551425').catch(()=>OAUI.set($('sunoState'),'宿主未能打开官方页面。'));
 $('sunoAvatar').onerror=()=>{$('sunoAvatar').hidden=true;$('sunoInitial').hidden=false;};
 $('sunoAll').onclick=()=>void refreshSuno({downloaded:false,libraryOnly:true});
 $('sunoPlayable').onclick=()=>void refreshSuno({downloaded:true,libraryOnly:true});
 $('sunoNext').onclick=()=>{if(sunoNext)void refreshSuno({cursor:sunoNext,libraryOnly:true});};
 function clear(){
   row=null;selection++;download.disabled=true;copy.hidden=true;$('audioVersions').hidden=true;
   $('audioEmptyPreview').hidden=false;
   for(const player of [audio,movie]){player.pause();player.hidden=true;player.removeAttribute('src');}
   OAUI.raw($('audioTitle'),'');OAUI.set(notice,'');OAUI.set(download,'下载原文件');
 }
 function fields(asset){return {project_id:asset.project_id,attempt_id:asset.attempt_id};}
 async function preview(asset){
   stopSuno();ace.stop();clear();row=asset;const id=selection;const player=asset.kind==='song'?audio:movie;
   $('audioEmptyPreview').hidden=true;
   for(const button of list.querySelectorAll('button'))button.setAttribute('aria-pressed',String(button.dataset.attempt===asset.attempt_id));
   OAUI.raw($('audioTitle'),assetName(asset));
   OAUI.set(notice,'正在加载音频…');
   try{
     let offset=0;
     const parts=[];
     while(offset<asset.bytes){
       const piece=await invoke('audio_chunk',{...fields(asset),offset});
       if(!active||id!==selection)return;
       if(piece.total!==asset.bytes||piece.next<=offset||piece.next>piece.total||typeof piece.data!=='string')
         throw new Error('AUDIO_CHUNK_INVALID');
       parts.push(piece.data);offset=piece.next;
     }
     player.src='data:'+asset.mime+';base64,'+parts.join('');player.hidden=false;download.disabled=false;
     $('audioVersions').hidden=asset.kind!=='soundtrack';
     $('audioOriginal').disabled=false;$('audioMixed').disabled=true;
     OAUI.set(notice,'{0} 秒',asset.seconds.toFixed(2));
   }catch(_){if(id===selection)OAUI.set(notice,'暂时无法预览此文件。');}
 }
 $('audioMixed').onclick=()=>{if(row?.kind==='soundtrack')void preview(row);};
 $('audioOriginal').onclick=async()=>{
   if(row?.kind!=='soundtrack')return;
   const asset=row,id=++selection,parts=[];
   const source={project_id:asset.video_project_id||asset.project_id,generation_attempt_id:asset.video_attempt_id};
   $('audioOriginal').disabled=true;$('audioMixed').disabled=false;movie.pause();
   OAUI.set(notice,'正在加载原片…');
   try{
     let total,offset=0;
     do{
       const part=await invoke('playback',{...source,offset});
       if(!active||id!==selection)return;
       if(part.sha256!==asset.video_sha256||part.offset!==offset||
          (total!==undefined&&total!==part.total))throw new Error('VIDEO_ASSET_CHANGED');
       total=part.total;
       const size=atob(part.bytes).length;
       if(!size||offset+size>total)throw new Error('VIDEO_ASSET_CHANGED');
       offset+=size;parts.push(part.bytes);
     }while(offset<total);
     movie.src='data:video/mp4;base64,'+parts.join('');
     OAUI.set(notice,'原片');
   }catch(_){if(id===selection){$('audioOriginal').disabled=false;OAUI.set(notice,'暂时无法预览此文件。');}}
 };
 async function refresh(){
   const epoch=++refreshEpoch;clear();list.replaceChildren();
   try{
     const history=await invoke('audio_library');
     if(!active||epoch!==refreshEpoch)return;
     OAUI.set($('audioEmpty'),history.assets.length?'':'还没有音频或配乐。');
     OAUI.set($('audioMonitorLocal'),'{0} 条本机资产',history.assets.length);
     const recent=$('audioRecent');recent.replaceChildren();
     for(const asset of history.assets.slice(0,3)){
       const item=document.createElement('li');
       const heading=document.createElement('div'),details=document.createElement('div');
       heading.className='oa-audio-task-heading';details.className='oa-audio-task-facts';
       const title=document.createElement('strong'),status=document.createElement('span');
       OAUI.raw(title,asset.title);OAUI.set(status,'已保存');heading.append(title,status);
       const time=document.createElement('span'),action=document.createElement('span'),charge=document.createElement('span');
       OAUI.raw(time,readableDate(asset.created_at));
       const operation=asset.kind==='song'?'导入音频':asset.kind==='cover'?'生成封面视频':'视频混音';
       const provider={suno:'Suno','ace-music':'ACE Music'}[asset.provider];
       OAUI.set(action,'{0} · {1}',provider||OAUI.message('本机'),OAUI.message(operation));
       OAUI.set(charge,provider?'单笔用量未提供':'本地处理');
       details.append(time,action,charge);item.append(heading,details);recent.append(item);
     }
     for(const asset of history.assets){
       const li=document.createElement('li'),button=document.createElement('button');
       button.type='button';button.dataset.attempt=asset.attempt_id;button.setAttribute('aria-pressed','false');
       const title=document.createElement('strong'),meta=document.createElement('span');
       OAUI.raw(title,assetName(asset));
       OAUI.set(meta,'{0}',[asset.account_label?'':OAUI.message('未标记账号'),
                     OAUI.message(asset.kind==='song'?'歌曲':asset.kind==='cover'?'封面视频':'配乐视频'),
                     readableDate(asset.created_at)].filter(Boolean));
       button.append(title,meta);button.onclick=()=>void preview(asset);li.append(button);list.append(li);
     }
   }catch(_){if(active&&epoch===refreshEpoch)OAUI.set($('audioEmpty'),'暂时无法读取项目音频。');}
 }
 async function request(text,target=$('audioActionNotice')){
   if(sending)return;
   copy.hidden=true;copy.value='';
   if(!canSend()){copy.value=text;copy.hidden=false;copy.focus();copy.select();return;}
   sending=true;
   try{await send(text);OAUI.set(target,'已发到当前 Codex 聊天。');}
   catch(_){OAUI.set(target,'无法确认聊天收到请求。');}
   finally{sending=false;}
 }
 $('audioCreate').onclick=()=>{
   void request('帮我构思一首 Suno 歌曲。先询问主题或沿当前聊天的 brief；保存歌曲方案和独立的标题、风格、歌词、人声字段。仅在本轮明确授权时调用官方 audio-create。需要保存成片时调用 media.library.prepare，使用统一媒体库；已明确账号时用实际平台和连接 ID 标记，未指定就留空。');
 };
 $('musicCreateDefault').onclick=()=>void request(OAMusicRequest('song'),$('musicProviderRequest'));
 $('musicScoreDefault').onclick=()=>void request(OAMusicRequest('score',videoIntent),$('musicProviderRequest'));
 $('audioReload').onclick=()=>{stopSuno();void refresh();};
 function selectProvider(value){
   const dashboard=$('audioWorkspace').querySelector('.oa-audio-dashboard');
   if(dashboard.dataset.providerView!==value){stopSuno();ace.stop();}
   dashboard.dataset.providerView=value;
   $('audioProviderSuno').setAttribute('aria-pressed',String(value==='suno'));
   $('audioProviderAce').setAttribute('aria-pressed',String(value==='ace'));
 }
 $('audioProviderSuno').onclick=()=>selectProvider('suno');
 $('audioProviderAce').onclick=()=>selectProvider('ace');
 download.onclick=async event=>{
   if(!event.isTrusted||!row||download.disabled)return;
   const id=selection,asset=row;download.disabled=true;
   try{
     const res=await invoke('audio_export',fields(asset));
     if(id!==selection)return;
     if(res.state!=='EXPORTED'||res.sha256!==asset.sha256)throw new Error('AUDIO_EXPORT_UNAVAILABLE');
     OAUI.set(download,'已下载');
   }catch(_){if(id===selection)OAUI.set(download,'未确认下载');}
   finally{if(id===selection)download.disabled=false;}
 };
 return {open(intent,{mode='production',provider=''}={}){
   videoIntent=intent&&typeof intent==='object'&&intent.project&&intent.attempt?intent:null;
   $('audioWorkspace').dataset.mode=mode;
   const models=mode==='models';
   active=true;if(!models)void refresh();sunoButtons(false);showSunoTracks(null);
   if(provider!=='suno')ace.open({manage:models});
   $('sunoHelp').hidden=!models;
   showMusic(null);void syncMusic();
   OAUI.set($('sunoState'),'点击「刷新 Suno」读取已有连接。');
 },close(){
   active=false;refreshEpoch++;sunoEpoch++;musicEpoch++;musicBusy=false;showMusic(null);stopSuno();ace.close();clear();
   OAUI.set($('musicProviderRequest'),'');
   sunoHandle='';sunoCursor='';sunoDownloaded=false;videoIntent=null;
   $('sunoInfo').hidden=true;sunoLibrary.hidden=true;sunoLibrary.open=false;
   OAUI.raw($('sunoAccount'),'');showSunoUsage(null);showSunoTracks(null);
 }};
};
'''
