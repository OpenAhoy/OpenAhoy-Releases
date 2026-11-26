"""Timeline controls inside the Jiusera director monitor."""
from . import video_director_autosave_ui as autosave
from . import video_director_look_ui as looks
from . import video_director_waveform_ui as waveform
from . import video_director_rough_cut_ui as rough_cut

SETTINGS_HTML = '''
<section class="dm-panel dc-settings" id="dmCutSettings" aria-labelledby="dmCutSettingsTitle" data-cut-label="剪辑设置" hidden>
 <header class="dm-heading"><h2 id="dmCutSettingsTitle" data-cut="剪辑设置"></h2></header>
 <div class="dc-toolbar">
  <label><span data-cut="视频素材"></span><select id="dmCutSource"></select></label>
  <button type="button" id="dmCutAdd" data-cut="加入时间线"></button>
  <button type="button" id="dmCutRefresh" data-cut="刷新素材"></button>
 </div>
 <div class="dc-inspector" id="dmCutInspector" hidden>
  <label><span data-cut="入点（秒）"></span><input type="number" id="dmCutIn" step=".001" min="0"></label>
  <label><span data-cut="出点（秒）"></span><input type="number" id="dmCutOut" step=".001" min="0"></label>
  <label><span data-cut="原声音量 %"></span><input type="number" id="dmCutVolume" step="1" min="0" max="100"></label>
 </div>
 <div class="dc-music">
  <label><span data-cut="配乐"></span><select id="dmCutSong"></select></label>
  <div class="dc-music-fields" id="dmCutMusicFields" hidden>
   <label><span data-cut="音源入点（秒）"></span><input type="number" id="dmCutMusicIn" step=".001" min="0"></label>
   <label><span data-cut="音源出点（秒）"></span><input type="number" id="dmCutMusicOut" step=".001" min="0"></label>
   <label><span data-cut="配乐起点（秒）"></span><input type="number" id="dmCutMusicStart" step=".001" min="0"></label>
   <label><span data-cut="配乐音量 %"></span><input type="number" id="dmCutMusicVolume" step="1" min="0" max="100"></label>
  </div>
 </div>
 <div class="dc-delivery" id="daDelivery">
  <div class="dc-actions"><output id="dmCutVersion" aria-live="polite"></output>
   <button type="button" id="dmCutRetry" data-cut="重试自动保存" hidden></button>
   <button type="button" id="dmCutRecover" data-cut="恢复本机草稿" hidden></button>
  </div>
  <div class="dc-actions"><button type="button" id="dmCutExport" data-cut="导出 MP4"></button> <small id="dmCutMixNote" hidden></small> <p id="dmCutStatus" role="status"></p></div>
  <details id="dmCutReceipt" hidden><summary data-cut="文件位置"></summary><output id="dmCutPath"></output></details>
  <button type="button" id="dmCutReload" data-cut="放弃本地剪辑并载入新版" hidden></button>
 </div>
</section>
'''

_TRANSPORT_PATHS = {
    'First': 'M5 5v14M18 5l-9 7 9 7z',
    'Prev': 'M6 5v14m11-13-7 6 7 6',
    'Play': 'M7 4.5 19 12 7 19.5z',
    'Stop': 'M6.5 6.5h11v11h-11z',
    'Next': 'M18 5v14M7 6l7 6-7 6',
    'Last': 'M19 5v14M6 5l9 7-9 7z',
    'More': 'M4 12h1m6.5 0h1m6.5 0h1',
}


def _transport_button(key, label):
    extra = ' aria-controls="dmCutMenu" aria-expanded="false"' if key == 'More' else ''
    pause = '<path class="dc-pause-icon" d="M8 5v14m8-14v14"/>' if key == 'Play' else ''
    return (f'<button type="button" id="dmCut{key}" class="dc-icon" data-cut-label="{label}"{extra}>'
            f'<svg viewBox="0 0 24 24" aria-hidden="true" focusable="false">'
            f'<path d="{_TRANSPORT_PATHS[key]}"/>{pause}</svg></button>')


HTML = '''
<section class="dm-panel dm-cut" id="dmCut" hidden data-cut-label="剪辑时间线">
 <div id="dmCutTracks" class="dc-tracks" hidden>
  <div id="dmCutRuler" class="dc-ruler" aria-hidden="true"></div>
  <div id="dmCutStrip" class="dc-strip" role="group"></div>
  <div id="dmCutVideoHeight" class="dc-track-grip" role="separator" aria-orientation="horizontal" aria-controls="dmCutStrip" aria-valuenow="76" tabindex="0" data-cut-label="视频轨高度"></div>
  <div id="dmCutMusicLane" class="dc-music-lane" hidden><div id="dmCutMusicSpan" role="slider" tabindex="0" data-cut-label="配乐位置"></div></div>
  <div id="dmCutAudioHeight" class="dc-track-grip" role="separator" aria-orientation="horizontal" aria-controls="dmCutMusicLane" aria-valuenow="56" tabindex="0" data-cut-label="音频轨高度"></div>
  <div id="dmCutNeedle" class="dc-needle" aria-hidden="true"></div>
 </div>
 <div class="dc-transport" id="dmCutTransport" hidden role="group" data-cut-label="播放控制">
  <div class="dc-transport-buttons">
''' + ''.join(_transport_button(key, text) for key, text in (
    ('First', '跳到开头'), ('Prev', '上一个剪点'), ('Play', '预览剪辑'), ('Stop', '停止'),
    ('Next', '下一个剪点'), ('Last', '跳到结尾'))) + '''
  </div>
  <output id="dmCutClock" aria-live="off"></output>
  <label><span class="dc-sr" data-cut="播放位置"></span><input id="dmCutSeek" type="range" min="0" max="0" value="0" step="1"></label>
  <div class="dc-more">
''' + _transport_button('More', '更多操作') + '''
   <div class="dc-menu" id="dmCutMenu" hidden>
    <button type="button" id="dmCutCodex" data-cut="在 Codex 继续剪辑"></button>
    <button type="button" id="dmCutScore" data-cut="用 Codex 配乐"></button>
   </div>
  </div>
 </div>
 
 
</section>
'''

STYLE = looks.STYLE + waveform.STYLE + '''
.dm-cut{grid-column:1/-1;display:grid;gap:6px;min-width:0}
#videoDirectorDesk :is(.dm-cut,.dc-settings)[hidden],#videoDirectorDesk :is(.dm-cut,.dc-settings) [hidden]{display:none}
.dm-cut output,.dc-strip small{font-variant-numeric:tabular-nums;color:var(--muted);font-size:11px}
.dc-settings{min-width:0;display:grid;align-content:start;gap:12px}
.dc-toolbar,.dc-actions,.dc-music,.dc-transport,.dc-transport-buttons{display:flex;align-items:center;gap:6px;flex-wrap:wrap}
.dc-settings>.dc-inspector,.dc-settings>.dc-music{border-top:1px solid var(--line);padding-top:10px}
.dc-settings .dc-toolbar label,.dc-settings .dc-music>label{width:100%}
.dc-inspector,.dc-music-fields{width:100%;display:grid;grid-template-columns:repeat(auto-fit,minmax(min(100%,94px),1fr));gap:6px}
#videoDirectorDesk :is(.dm-cut,.dc-settings) label{display:grid;gap:2px;min-width:0;font-size:11px;color:var(--muted)}
#videoDirectorDesk .dc-settings :is(input,select){width:100%;min-width:0;box-sizing:border-box}
.dc-transport{position:relative;flex-wrap:nowrap;min-width:0;gap:8px;padding:3px 2px;border-top:1px solid var(--line)}
#wbDirectorTransport>.dc-transport{width:min(490px,calc(100vw - 42px));max-width:100%;box-sizing:border-box;border:0;padding:0}
.dc-transport-buttons{flex-wrap:nowrap;gap:1px}
:is(#videoDirectorDesk,#wbDirectorTransport) .dc-transport button.dc-icon{display:inline-grid;place-items:center;width:30px;height:30px;min-height:30px;padding:0;border:0;box-shadow:none;background:transparent;color:inherit;border-radius:5px}
:is(#videoDirectorDesk,#wbDirectorTransport) .dc-icon:not(:disabled):hover{background:var(--soft)}
.dc-icon:focus-visible,.dc-menu button:focus-visible{outline:2px solid var(--accent);outline-offset:1px}
.dc-icon svg{width:16px;height:16px;fill:none;stroke:currentColor;stroke-width:1.85;stroke-linecap:round;stroke-linejoin:round}
#dmCutPlay svg path:first-child,#dmCutStop svg path{fill:currentColor}
#dmCutMore svg{stroke-width:3}
.dc-pause-icon,#dmCutPlay[aria-pressed=true] svg path:first-child{display:none}
#dmCutPlay[aria-pressed=true] .dc-pause-icon{display:inline;stroke-width:3}
#dmCutTransport label{display:grid;align-content:center;flex:1;min-width:0;height:22px;min-height:0;margin:0;padding:0}
#dmCutTransport[hidden],#dmCutMenu[hidden]{display:none}
:is(#videoDirectorDesk,#wbDirectorTransport) .dc-transport input[type=range]{display:block;width:100%;min-width:0;height:18px;min-height:18px;padding:0;margin:0;accent-color:var(--accent)}
.dc-transport output{white-space:nowrap;font:11px/1.25 ui-monospace,monospace;font-variant-numeric:tabular-nums}
.dc-more{position:relative}
.dc-menu{position:absolute;inset:auto 0 calc(100% + 4px) auto;z-index:8;display:grid;gap:3px;min-width:max-content;padding:5px;background:var(--panel,Canvas);border:1px solid var(--line);border-radius:8px;box-shadow:0 4px 16px #0002}
.dc-menu[data-align=below]{inset:calc(100% + 4px) 0 auto auto}
.dc-menu button{text-align:start}
.dc-tracks{position:relative;min-width:0;border:1px solid var(--line);border-radius:8px;overflow:hidden;padding:0;
 background:var(--soft)}
.dc-ruler{display:flex;justify-content:space-between;padding:2px 4px;color:var(--muted);font:10px/1.5 ui-monospace,monospace;border-bottom:1px solid var(--line)}
.dc-strip{display:flex;min-height:var(--dc-video-height,76px);align-items:stretch}
.dc-track-grip{height:5px;position:relative;cursor:row-resize;touch-action:none;outline-offset:-2px}
.dc-track-grip::after{content:"";position:absolute;left:0;right:0;top:2px;height:1px;background:var(--line)}
.dc-track-grip:focus-visible,.dc-track-grip:hover{background:color-mix(in srgb,var(--accent) 22%,transparent)}
#dmCutVersion{font-size:11px;color:var(--muted)}
#dmCutMusicSpan{cursor:ew-resize;touch-action:none}
.dc-strip:focus-within{z-index:1}
.dc-strip>small{align-self:center;padding-inline:8px}
.dc-delivery{border-top:1px solid var(--line);padding-top:8px;min-width:0}
.dc-delivery #dmCutReceipt{font-size:11px;color:var(--muted);overflow-wrap:anywhere}
.dc-delivery #dmCutReceipt summary{cursor:pointer}
.dc-delivery #dmCutPath{display:block;user-select:all}
.dc-song-wave,.dc-source-wave{display:block;width:100%;min-width:0;overflow:hidden}
.dc-song-wave{height:calc(100% - 16px);color:light-dark(#1d6c4c,#99d7b0)}
#videoDirectorDesk .dc-strip button .dc-source-wave{position:absolute;inset:auto 0 1px;height:clamp(12px,calc(var(--dc-video-height,76px)*.30),54px);pointer-events:none;color:light-dark(#47657b,#8aaac8)}
#videoDirectorDesk .dc-strip button:has(.dc-source-wave){padding-bottom:clamp(14px,calc(var(--dc-video-height,76px)*.30 + 2px),56px)}
.dc-music-lane{height:var(--dc-audio-height,56px);position:relative;border-top:1px solid var(--line)}
.dc-music-lane>div{position:absolute;top:3px;bottom:3px;overflow:hidden;white-space:nowrap;text-overflow:ellipsis;
 background:light-dark(#cfebda,#254737);border:1px solid light-dark(#99c7a8,#438460);color:light-dark(#224e32,#d6f8dc);
 font-size:10px;line-height:16px;border-radius:3px;padding-inline:3px}
.dc-needle{position:absolute;top:0;bottom:0;pointer-events:none;border-left:1px solid var(--accent);z-index:2}
.dc-needle::before{content:"";display:block;position:absolute;left:-4px;border:4px solid transparent;border-top-color:var(--accent)}
.dc-edge{position:absolute;top:0;bottom:0;width:7px;touch-action:none;cursor:ew-resize;z-index:1}
.dc-edge[data-side="in"]{left:0}.dc-edge[data-side="out"]{right:0}
.dc-edge:hover,.dc-strip button[aria-pressed=true] .dc-edge{background:color-mix(in srgb,var(--accent) 28%,transparent)}
.dc-frame{position:absolute;inset:0 auto 0 0;width:min(42%,calc(var(--dc-video-height,76px)*1.25));height:100%;object-fit:cover;opacity:.34;pointer-events:none}
.dc-strip button>*:not(.dc-edge,.dc-frame){position:relative;z-index:0;pointer-events:none;min-width:0}

#videoDirectorDesk .dc-strip button{position:relative;display:grid;align-content:center;min-width:0;overflow:hidden;flex:none;gap:2px;border-radius:3px;
 padding:5px min(1%,9px);text-align:start;background:light-dark(#dce6ee,#2d3945);border-inline-end:1px solid var(--line)}
.dc-strip button strong{max-width:180px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
#videoDirectorDesk .dc-strip button[aria-pressed=true]{outline:2px solid var(--accent);outline-offset:-2px}
#dmCutStatus:empty{display:none}
#dmCutStatus{margin:0;color:var(--muted);overflow-wrap:anywhere}
#dmCutPreview .oa-frame-screen{aspect-ratio:16/9;background:#111;border-radius:8px;max-height:min(59dvh,620px);overflow:hidden}
#dmCutPreview img{width:100%;height:100%;object-fit:contain}
.dc-sr{position:absolute;width:1px;height:1px;clip-path:inset(50%);overflow:hidden}
@media(max-width:550px){.dc-strip button strong{max-width:114px}.dc-tracks{--dc-video-height:60px;--dc-audio-height:46px}
.dc-transport{gap:3px}.dc-transport-buttons{gap:0}
:is(#videoDirectorDesk,#wbDirectorTransport) .dc-transport button.dc-icon{width:24px;height:28px;min-height:28px}
.dc-transport output{font-size:9px}.dm-cut{padding:6px}}
'''

SCRIPT = autosave.SCRIPT + looks.SCRIPT + waveform.SCRIPT + rough_cut.SCRIPT + r'''
function OADirectorTimeline({read,edit,frames,exactFrame,chunk,audioChunk,masterChunk,sound,send,canSend,uid,onExport,showPreview,toggleSourcePlayback}){
 const $=key=>document.getElementById('dmCut'+key),root=$(''),settings=$('Settings'),transport=$('Transport'),strip=$('Strip');
 document.getElementById('wbDirectorTransport')?.append(transport);
 const delivery=$('Export').closest('.dc-delivery'),side=settings.closest('.dm-sidebar');
 if(side)side.append(delivery);
 const panels=root.contains(transport)?[root,settings]:[root,settings,transport];
 if(side)panels.push(delivery);
 const english={'剪辑时间线':'Edit timeline','重试自动保存':'Retry autosave','恢复本机草稿':'Recover local draft','自动保存中':'Saving','等待自动保存':'Autosave pending','自动保存失败':'Autosave failed','版本冲突':'Version conflict','草稿仅在当前窗口':'Draft only in this window','视频轨高度':'Video track height','音频轨高度':'Audio track height','配乐位置':'Music position','文件位置':'File location','剪辑设置':'Edit settings','播放控制':'Playback controls','跳到开头':'Jump to start','上一个剪点':'Previous cut','停止':'Stop','下一个剪点':'Next cut','跳到结尾':'Jump to end','更多操作':'More actions','剪辑台':'Timeline','视频素材':'Video source','加入时间线':'Add to timeline','刷新素材':'Refresh sources',
  '预览剪辑':'Play edit','播放位置':'Playhead','入点（秒）':'Source in (s)','出点（秒）':'Source out (s)',
  '原声音量 %':'Clip audio %','在此分割':'Split here','左移':'Move left','右移':'Move right','移除片段':'Remove clip',
  '配乐':'Music','音源入点（秒）':'Music source in (s)','音源出点（秒）':'Music source out (s)','配乐起点（秒）':'Music starts at (s)','配乐音量 %':'Music level %',
  '撤销':'Undo','重做':'Redo','保存剪辑':'Save edit','导出 MP4':'Export MP4','在 Codex 继续剪辑':'Edit with Codex',
  '用 Codex 配乐':'Score with Codex','无配乐':'No music','暂停':'Pause','放弃本地剪辑并载入新版':'Discard local edits and load new version',
  '未保存':'Unsaved','已保存':'Saved','正在保存…':'Saving…','正在导出…':'Exporting…','导出完成':'Exported','导出失败':'Export failed','导出中断':'Export interrupted','导出配乐':'Export score','导出原声':'Export clip audio',
  '查询导出':'Check export','重试导出':'Retry export','查看导出成片':'View export','导出回执待查':'Export receipt pending',
  '未找到这版剪辑的导出任务':'No export found for this revision',
  '片段不足一个输出帧（30 fps）':'Clip shorter than one output frame (30 fps)',
  '当前作品没有可剪辑的视频':'No editable video in this work','没有片段':'No clips','从右侧「添加」选择视频或配乐':'Choose video or music in Add on the right','读取失败':'Unable to load',
  '操作未完成':'Action failed','已更新':'Updated','其他窗口已保存新版。当前草稿已保留。':'Another edit was saved. Your local draft is preserved.',
  '请检查入点、出点或音量。':'Check trim points and levels.','已发到当前 Codex 聊天':'Sent to the current Codex chat',
  '正在读取音轨…':'Loading audio…','正在缓冲剪辑…':'Buffering preview…','正在读取…':'Loading…','此素材已不可用':'This source is unavailable','当前宿主无法向 Codex 发送消息':'Codex messaging is unavailable in this host',
  '无法预览此片段':'Clip preview unavailable','无法读取所选视频帧':'Selected frame unavailable','此音源无法在宿主试听':'This audio cannot be previewed in this host',
  '已采用':'Adopted','返回原片':'View source','时间线片段':'Timeline clips','从时间线移除，不删除原素材':'Remove from edit; keep the source'};
 const tr=key=>document.documentElement.lang==='en'?(english[key]||key):key;
 let releaseScore,scoreBindingKey='';
 const waves=OADirectorWaveforms(read,()=>document.documentElement.lang==='en');
 const fmt=ms=>(ms/1000).toFixed(3).replace(/\.?0+$/,'')||'0';
 const clock=value=>{const ms=Math.round(value);return Math.floor(ms/60000)+':'+(Math.floor(ms/1000)%60).toString().padStart(2,'0')+'.'+String(ms%1000).padStart(3,'0');};
 const clone=x=>JSON.parse(JSON.stringify(x));
 const drafts=new Map(),thumbs=new Map();let dragID='';
 const observer=typeof IntersectionObserver==='function'?new IntersectionObserver(entries=>{
   for(const entry of entries)if(entry.isIntersecting){observer.unobserve(entry.target);const img=entry.target.querySelector('.dc-frame');if(img)void thumbnail(img);}
 }):null;
 let scope=null,key='',s=null,readSerial=0,lastSignal='',selected='',cursor=0,preview=null,activeDelivery='',playTicket=null;
 let loopEnabled=false,loopIn=0,loopOut=null,transportStart=null,transportLevel=.85;
 const imwActive=()=>document.body.dataset.imwVideo==='true'&&document.body.dataset.workbench==='l-unify';
 const editingVideo=()=>document.body.dataset.workbench==='monitor'||imwActive();
 function audioBinding(){
   const {imwProject:project,imwWork:work,imwSong:song,imwSongVersion:version}=document.body.dataset;
   if(!imwActive()||!song||!version||!project||!work||scope?.project_id!==project||scope?.work_id!==work)return null;
   return {project,song,version};
 }
 function selectedStudio(){
   const binding=audioBinding(),studio=document.querySelector('lus-studio'),selection=studio?.imw?.trackSelection?.();
   return binding&&selection&&['project','song','version'].every(k=>selection[k]===binding[k])&&
     studio.project?.id===binding.project&&studio.song?.id===binding.song&&studio.version?.id===binding.version?studio:null;
 }
 function boundStudio(){
   const studio=selectedStudio();
   return studio&&(studio.version.mastered?!!studio.version.masterAudioSha:studio.audioReady&&!!studio.draft)?studio:null;
 }
 function archivedWindow(){
   const music=s?.doc.music;
   return audioBinding()&&music&&music.sha256===document.body.dataset.imwMusicSha?music:null;
 }
 function trackEnd(studio){
   let end=0;for(const track of studio.version.tracks)for(const clip of (studio.version.mastered?[track]:studio.clips(track)))
     end=Math.max(end,clip.start+clip.duration+(clip.silenceTail||0));
   return Math.round(end*1000);
 }
 // Track headers are monitoring controls. Keep their choices outside the edit and export documents.
 const groupMonitors=new Map();
 function monitorState(track){
   const active=imwActive()&&!!s?.loaded;
   const groups=active?groupMonitors.get(key):null,own=groups?.[track];
   const studio=active&&boundStudio();
   const stemSolo=!!studio&&!studio.version.mastered&&studio.version.tracks.some(row=>{
     const flag=studio.trackMonitorState(row.id);return flag.solo||flag.editorSolo;
   });
   const solo=!!own?.solo,mute=!!own?.mute;
   const selected=solo||(track==='score'&&stemSolo);
   const inherited=!!(groups?.source.solo||groups?.score.solo||stemSolo)&&!selected;
   return {solo,mute,inherited,audible:!mute&&!inherited};
 }
 function signalMonitor(){
   document.dispatchEvent(new CustomEvent('jiusera:imw-monitor',{detail:{
     source:monitorState('source'),score:monitorState('score')
   }}));
 }
 function toggleMonitor(track,action){
   if(!imwActive()||!s?.loaded||!['source','score'].includes(track)||!['solo','mute'].includes(action))return false;
   const groups=groupMonitors.get(key)??{source:{solo:false,mute:false},score:{solo:false,mute:false}};
   groups[track][action]=!groups[track][action];
   if(Object.values(groups).some(row=>row.solo||row.mute))groupMonitors.set(key,groups);else groupMonitors.delete(key);
   preview?.updateMonitors();signalMonitor();return true;
 }
 function showExportSource(){
   if(!s)return;
   const selected=selectedStudio(),studio=boundStudio(),binding=audioBinding(),note=$('MixNote');
   const resolving=imwActive()&&document.body.dataset.imwBindingState;
   const pending=resolving==='pending'||binding&&(!selected||selected.loadingTracks),missing=binding&&!pending&&!studio;
   const partial=studio&&!studio.version.mastered&&studio.buffers.size<studio.version.tracks.length;
   const en=document.documentElement.lang==='en';
   const message=resolving==='error'?(en?'Audio selection could not be verified. Reopen video to retry.':'未能核对当前曲目，请重新打开视频重试。'):
     resolving==='pending'?(en?'Checking the selected audio…':'正在核对当前作品的音轨…'):
     pending?(en?'Loading selected audio tracks…':'正在载入所选曲目的音轨…'):
     missing?(en?'This version has no playable audio.':'所选版本没有可用音源。'):
     partial?(en?'Only the available tracks will be previewed and exported.':'试听和导出仅使用已载入的分轨。'):
     imwActive()&&!binding&&s.doc.music?(en?'Preview and export use camera audio. The earlier film keeps its soundtrack.':'当前试听和导出仅使用镜头原声，历史配乐可在原成片中收听。'):'';
   note.hidden=!message;note.textContent=message;
   $('Export').disabled=!!(s.busy||!s.loaded||!total()||s.conflict||shortClip()>=0||resolving||pending||missing);
   $('Export').title=message||tr('导出 MP4');
 }
 async function exportMix(){
   if(!imwActive())return null;
   if(document.body.dataset.imwBindingState)throw Error('STUDIO_BINDING_NOT_READY');
   const studio=boundStudio(),binding=audioBinding(),work=key;
   if(!binding)return {mode:'picture_only',source_audio:monitorState('source').audible};
   const version=studio?.version;
   if(!studio||studio.loadingTracks||(!version.mastered&&!await studio.save())||
      boundStudio()?.version!==version||key!==work||document.body.dataset.imwBindingState)throw Error('STUDIO_DRAFT_NOT_READY');
   const available=version.mastered?version.tracks:version.tracks.filter(t=>studio.buffers.has(t.id)&&studio.trackMonitorState(t.id).audible);
   const music=archivedWindow();
   return {song:binding.song,version:binding.version,revision:version.mastered?0:studio.draft.revision,identity:version.mixIdentity,
     audible:monitorState('score').audible?available.map(t=>t.id):[],source_audio:monitorState('source').audible,
     ...(music?{window_sha256:music.sha256}:{})};
 }
 function displaySpan(){
   if(!s)return 0;
   const studio=imwActive()&&selectedStudio(),window=studio&&archivedWindow();
   const offset=window?Math.max(0,window.start_ms-window.in_ms):0;
   const base=Math.max(span(),s.scoreViewMs||0,studio?Math.round(1000*studio.rulerLength)+offset:0);
   return studio?.imw?.extendDisplayLength?studio.imw.extendDisplayLength(base/1000)*1000:base;
 }
 function syncGeometry(){
   if(!s||!imwActive())return;
   const extent=displaySpan();
   if(s.paintedExtent===extent)return;
   s.paintedExtent=extent;
   strip.style.setProperty('--imw-ms',100/Math.max(1,extent)+'%');
 }
 function clockState(){
   return {active:imwActive(),ready:!!s?.loaded&&!s.previewOnOpen&&!root.hidden,playing:!!preview?.isPlaying(),
     seconds:cursor/1000,length:s?span()/1000:0,displayLength:displaySpan()/1000,
     frameRate:s?.doc.clips.length?sourceOf(s.doc.clips[0])?.frame_rate??null:null,project:scope?.project_id,work:scope?.work_id,music:(imwActive()?archivedWindow():s?.doc.music)??null};
 }
 function loopWindow(){
   const end=s?Math.min(loopOut??span(),span()):0;
   return {start:loopIn<end?loopIn:0,end};
 }
 function emitTransport(){
   const active=imwActive(),duration=s?span():0,window=loopWindow(),playing=!!preview?.isPlaying();
   document.dispatchEvent(new CustomEvent('jiusera:imw-transport-state',{detail:{
     active,ready:active&&!!s?.loaded&&!s.previewOnOpen&&!root.hidden&&duration>0&&!s.busy,
     playing,cursorMs:Math.round(cursor),durationMs:duration,loop:loopEnabled,loopInMs:window.start,
     loopOutMs:window.end,level:transportLevel,loading:!!playTicket||(playing&&!preview.started()),
     canStop:transportStart!==null||!!playTicket,canLoopClip:!!s?.loaded&&!!cut()&&cut().out_ms-cut().in_ms>=250,canClick:false,
     metronome:false,peakDb:playing?sound?.peakDb?.()??-60:-60
   }}));
 }
 function emitClock(){
   if(imwActive()){
     document.dispatchEvent(new CustomEvent('jiusera:imw-clock',{detail:clockState()}));
     emitTransport();
   }
 }
 const cut=()=>s.doc.clips.find(c=>c.id===selected);
 const sourceOf=c=>s.sources.find(r=>r.delivery_id===c?.delivery_id&&r.sha256===c.sha256);
 const songOf=m=>s.songs.find(r=>r.attempt_id===m?.attempt_id&&r.sha256===m.sha256);
 const gapBefore=clip=>clip.gap_before_ms??0;
 const durationOf=clip=>clip.out_ms-clip.in_ms;
 const total=(clips=s.doc.clips)=>clips.reduce((sum,c)=>sum+gapBefore(c)+durationOf(c),0);
 function positions(clips){
   let end=0;
   return clips.map(clip=>{
     const start=end+gapBefore(clip);
     end=start+durationOf(clip);
     return {clip,start,end};
   });
 }
 function span(){
   const picture=total();if(picture)return picture;
   const detached=(s.doc.detached_audio||[]).reduce((end,row)=>Math.max(end,row.start_ms+row.out_ms-row.in_ms),0);
   if(imwActive()&&!archivedWindow()){const studio=boundStudio();return Math.max(detached,studio?trackEnd(studio):0);}
   const m=s.doc.music;if(!m)return detached;
   return Math.max(detached,m.start_ms+(m.out_ms??songOf(m)?.duration_ms??0)-m.in_ms);
 }
 function startOf(id){return positions(s.doc.clips).find(row=>row.clip.id===id)?.start??total();}
 function displayStatus(message,detail){
   const file=message==='导出完成'?detail:'';
   if($('Path').textContent!==file){$('Path').textContent=file;$('Receipt').open=false;}
   $('Receipt').hidden=!file;
   $('Status').textContent=tr(message)+(detail&&!file?' · '+detail:'');
 }
 function say(k,detail=''){if(s){s.message=k;s.detail=detail;}displayStatus(k,detail);}
 function playState(playing){
   const el=$('Play'),name=tr(playing?'暂停':'预览剪辑');
   el.title=name;el.setAttribute('aria-label',name);el.setAttribute('aria-pressed',String(playing));emitClock();
 }
 function menu(open,focus=false){
   $('Menu').hidden=!open;$('More').setAttribute('aria-expanded',String(open));
   if(open)$('Menu').dataset.align=$('More').getBoundingClientRect().top<$('Menu').offsetHeight+6?'below':'above';
   if(focus)(open?$('Menu').querySelector('button:not(:disabled)'):$('More'))?.focus();
 }
 function localize(){
   for(const panel of panels){
     for(const el of panel.querySelectorAll('[data-cut]'))el.textContent=tr(el.dataset.cut);
     for(const el of [panel,...panel.querySelectorAll('[data-cut-label]')]){
       if(!el.dataset.cutLabel)continue;const name=tr(el.dataset.cutLabel);el.setAttribute('aria-label',name);
       if(el.tagName==='BUTTON')el.title=name;
     }
   }
   playState(!!preview?.isPlaying());$('Return').textContent=tr('返回原片');strip.setAttribute('aria-label',tr('时间线片段'));
   if(s)paint();
 }
 function resetPreview(){
   preview?.close();preview=null;showPreview(false);
   $('Return').hidden=true;playState(false);
 }
 function touch(state=s){
   state.undo.push(clone(state.doc));if(state.undo.length>80)state.undo.shift();state.redo=[];
   state.message='';state.detail='';if(state===s)resetPreview();
 }
 const auto=OADirectorAutosave({read,edit,uid,equal:sameValue,valid:doc=>shortClip(doc)<0,
   notify:state=>{if(s===state){showSaveState();updateDetachButton();notifyTools();}if(state===detachedOwner())detachedChanged();}});
 const dirty=()=>auto.dirty(s);
 const rough=OADirectorRoughCut({getState:()=>s,getScope:()=>scope,waves,uid,notify:notifyTools,
   english:()=>document.documentElement.lang==='en',apply:doc=>{
     touch();s.doc={...doc,detached_audio:s.doc.detached_audio};selected=doc.clips[0].id;cursor=0;paint();previewToolClip(selected);
   }});
 function selectOptions(node,items,value,empty){
   const opts=items.map(([id,label])=>new Option(label,id));
   if(empty)opts.unshift(new Option(empty,''));
   node.replaceChildren(...opts);if(opts.some(o=>o.value===value))node.value=value;
 }
 function sameValue(a,b){
   if(a===b)return true;
   if(!a||!b||typeof a!=='object'||typeof b!=='object'||Array.isArray(a)!==Array.isArray(b))return false;
   const keys=Object.keys(a);return keys.length===Object.keys(b).length&&keys.every(k=>Object.hasOwn(b,k)&&sameValue(a[k],b[k]));
 }
 const frameBoundary=ms=>Math.floor((ms*30+500)/1000);
 function shortClip(doc=s.doc){
   return positions(doc.clips).findIndex(({start,end})=>frameBoundary(end)<=frameBoundary(start));
 }
 let lastSplit=false;
 function canSplit(){
   if(toolBusy()||s.doc.clips.length>=256)return false;
   const c=cut();if(!c)return false;
   const start=startOf(c.id),end=start+c.out_ms-c.in_ms;
   return frameBoundary(cursor)>frameBoundary(start)&&frameBoundary(cursor)<frameBoundary(end)&&cursor>start&&cursor<end;
 }
 function updateCursor(){
   const n=span(),c=cut();cursor=Math.max(0,Math.min(n,cursor));
   const locked=s.busy||!s.loaded||!n;
   $('First').disabled=$('Prev').disabled=locked||cursor===0;
   $('Last').disabled=$('Next').disabled=locked||cursor===n;
   $('Stop').disabled=locked||(!cursor&&!preview?.isPlaying());
   $('Seek').setAttribute('aria-valuetext',clock(cursor)+' / '+clock(n));
   $('Seek').max=n;$('Seek').value=cursor;
   $('Clock').value=clock(cursor)+' / '+clock(n);$('Needle').style.left=(n?100*cursor/n:0)+'%';
   const split=canSplit();if(split!==lastSplit){lastSplit=split;notifyTools();}emitClock();
 }
 // Keep host frame reads bounded across thumbnails, playback and rapid seeks.
 const pictureJobs=[],pictureBatches=new Map();let pictureReads=0,thumbnailReads=0;
 function requestPicture(run,valid,thumbnail=false){
   return new Promise((resolve,reject)=>{pictureJobs.push({run,valid,thumbnail,resolve,reject});pumpPictures();});
 }
 function pumpPictures(){
   for(let i=pictureJobs.length-1;i>=0;i--){
     if(!pictureJobs[i].valid())pictureJobs.splice(i,1)[0].resolve(null);
   }
   while(pictureReads<4&&pictureJobs.length){
     let i=pictureJobs.findIndex(job=>!job.thumbnail);
     if(i<0){if(thumbnailReads)return;i=0;}
     const job=pictureJobs.splice(i,1)[0];pictureReads++;if(job.thumbnail)thumbnailReads++;
     Promise.resolve().then(job.run).then(job.resolve,job.reject).finally(()=>{
       pictureReads--;if(job.thumbnail)thumbnailReads--;pumpPictures();
     });
   }
 }
 function readPictures(target,clip,start,thumbnail=false){
   const owner=JSON.stringify(target),id=JSON.stringify([owner,clip.delivery_id,clip.sha256,start]);
   const cached=pictureBatches.get(id);
   if(cached){
     pictureBatches.delete(id);pictureBatches.set(id,cached);
     return cached;
   }
   const valid=()=>key===owner;
   const job=requestPicture(()=>frames(target,clip,start),valid,thumbnail).then(batch=>{
     if(!batch&&pictureBatches.get(id)===job)pictureBatches.delete(id);
     return batch;
   },error=>{
     if(pictureBatches.get(id)===job)pictureBatches.delete(id);
     throw error;
   });
   pictureBatches.set(id,job);
   if(pictureBatches.size>24)pictureBatches.delete(pictureBatches.keys().next().value);
   return job;
 }
 async function thumbnail(img,target,clip,ms){
   if(!target)({target,clip}=JSON.parse(img.dataset.ref));
   const frame=Math.floor((ms??clip.in_ms)/125);
   const id=JSON.stringify([target,clip.delivery_id,clip.sha256,frame]);
   if(!img.isConnected||!s||key!==JSON.stringify(target))return;
   let entry=thumbs.get(id);
   if(!entry){
     const base=frame-frame%4;
     entry={pending:new Set([img])};
     thumbs.set(id,entry);if(thumbs.size>80)thumbs.delete(thumbs.keys().next().value);
     entry.result=readPictures(target,clip,base,true)
       .then(batch=>batch?.start===base?batch.frames?.[frame-base]:null).catch(()=>null)
       .then(jpeg=>{
         entry.pending.clear();
         if(!jpeg&&thumbs.get(id)===entry)thumbs.delete(id);
         return jpeg;
       });
   }else entry.pending.add(img);
   const jpeg=await entry.result;
   entry.pending.delete(img);
   if(img.isConnected&&typeof jpeg==='string'&&jpeg.startsWith('/9j/')&&jpeg.length<=128000)img.src='data:image/jpeg;base64,'+jpeg;
 }
 // Sample the visible part of each trimmed clip at the timeline's current scale.
 let filmScroll,filmResize,filmRAF=0;
 const films=[];
 function resetFilms(){
   filmScroll?.removeEventListener('scroll',scheduleFilms);
   filmResize?.disconnect();filmScroll=null;
   cancelAnimationFrame(filmRAF);filmRAF=0;films.length=0;
 }
 function scheduleFilms(){
   if(!filmRAF)filmRAF=requestAnimationFrame(drawFilms);
 }
 function drawFilms(){
   filmRAF=0;
   if(!filmScroll)return;
   const view=filmScroll.getBoundingClientRect();
   for(const {band,clip,target} of films){
     const rect=band.getBoundingClientRect();
     const pitch=Math.max(40,Math.round(rect.height*16/9));
     const first=Math.max(0,Math.floor((view.left-rect.left)/pitch));
     const end=Math.min(Math.ceil(rect.width/pitch),Math.ceil((view.right-rect.left)/pitch));
     const keep=new Set();
     for(let i=first;i<end;i++){
       const left=i*pitch;
       const time=clip.in_ms+(clip.out_ms-clip.in_ms)*left/rect.width;
       const index=Math.floor(time/125);
       let img=band.querySelector('[data-cell="'+i+'"]');
       if(img&&Number(img.dataset.sample)!==index){img.remove();img=null;}
       if(!img){
         img=document.createElement('img');img.className='dc-frame';img.alt='';img.draggable=false;
         img.dataset.cell=i;img.dataset.sample=index;band.append(img);
         void thumbnail(img,target,clip,time);
       }
       img.style.left=left+'px';img.style.width=pitch+'px';keep.add(img);
     }
     for(const img of [...band.children])if(!keep.has(img))img.remove();
   }
 }
 function registerFilm(band,clip){
   if(!filmScroll){
     filmScroll=document.querySelector('lus-studio')?.shadowRoot?.getElementById('scroll');
     if(!filmScroll)return;
     filmScroll.addEventListener('scroll',scheduleFilms,{passive:true});
     filmResize=new ResizeObserver(scheduleFilms);
     filmResize.observe(filmScroll);
   }
   films.push({band,target:scope,clip});
   filmResize.observe(band);scheduleFilms();
 }
 function trimHandle(button,clip,side,display){
   const native=imwActive(),edge=document.createElement(native?'button':'span');edge.dataset.side=side;
   if(native){
     edge.type='button';edge.className='trim-handle '+(side==='in'?'head':'tail');
     edge.setAttribute('aria-label',tr(side==='in'?'入点（秒）':'出点（秒）'));
     edge.disabled=button.disabled||!sourceOf(clip);
     edge.onkeydown=e=>{
       if(!['ArrowLeft','ArrowRight'].includes(e.key)||toolBusy())return;
       e.preventDefault();e.stopPropagation();const delta=(e.key==='ArrowLeft'?-1:1)*(e.shiftKey?1000:100);
       const head=side==='in',field=head?'in_ms':'out_ms';
       const next=Math.max(head?0:clip.in_ms+1,Math.min(head?clip.out_ms-1:sourceOf(clip).duration_ms,clip[field]+delta));
       if(next===clip[field])return;
       touch();clip[field]=next;selected=clip.id;cursor=startOf(selected);paint();
       strip.querySelector('.clip-group[data-selected] .'+(head?'head':'tail'))?.focus({preventScroll:true});
     };
   }else{edge.className='dc-edge';edge.setAttribute('aria-hidden','true');}
   edge.onpointerdown=e=>{
     if(s.busy||e.button!==0)return;
     const owner=s,startX=e.clientX,interval=native?displaySpan():total(),duration=sourceOf(clip)?.duration_ms;
     if(!duration||!interval)return;
     const scale=interval/Math.max(strip.clientWidth,1);
     const field=side==='in'?'in_ms':'out_ms',initial=clip[field];
     const min=side==='in'?0:clip.in_ms+1,max=side==='in'?clip.out_ms-1:duration;
     let proposed=initial;
     e.stopPropagation();e.preventDefault();edge.setPointerCapture(e.pointerId);button.draggable=false;
     const change=event=>Math.min(max,Math.max(min,initial+Math.round((event.clientX-startX)*scale)));
     edge.onpointermove=event=>{proposed=change(event);display.textContent=fmt(side==='in'?clip.out_ms-proposed:proposed-clip.in_ms)+' s';};
     const finish=event=>{
       event.stopPropagation();edge.onpointermove=null;edge.onpointerup=edge.onpointercancel=null;button.draggable=!native;
       if(s!==owner||!button.isConnected)return;
       if(event.type==='pointerup'&&change(event)!==initial){touch();clip[field]=change(event);selected=clip.id;cursor=startOf(selected);}
       paint();
     };
     edge.onpointerup=edge.onpointercancel=finish;
   };
   return edge;
 }
 function bindScore(music,song,length,bar,wave,native){
   const lane=$('MusicLane'),owner=s,bindings=[],editor=globalThis.OAStudio.clipEditing;
   const sourceOut=music.out_ms??song.duration_ms,visibleOut=Math.min(sourceOut,music.in_ms+length-music.start_ms);
   const read=()=>({start:music.start_ms/1000,sourceIn:music.in_ms/1000,duration:(visibleOut-music.in_ms)/1000,
     head:music.in_ms/1000,tail:(song.duration_ms-visibleOut)/1000,silenceHead:0,silenceTail:0});
   const geometry=()=>({width:lane.clientWidth,length:length/1000});
   const limits=action=>({rate:1000,frames:song.duration_ms,timelineLimit:action==='move'||!owner.doc.clips.length?Infinity:length/1000,
     startLimit:Math.max(0,length-1)/1000,reserveTail:false});
   const viewWave=waves.region(wave,{...scope,attempt_id:music.attempt_id,sha256:music.sha256,volume:music.volume},
     song.duration_ms,length/Math.max(lane.clientWidth,strip.clientWidth,1));
   function preview(clip,{action}){
     const start=Math.round(clip.start*1000),sourceIn=Math.round(clip.sourceIn*1000);
     const duration=action==='move'?sourceOut-sourceIn:Math.round(clip.duration*1000);
     const visible=owner.doc.clips.length?Math.min(duration,length-start):duration;
     bar.style.left=100*start/length+'%';bar.style.width=100*visible/length+'%';
     viewWave(sourceIn,sourceIn+visible);
   }
   const enabled=()=>s===owner&&!toolBusy()&&bar.isConnected;
   function commit(clip,{action,event}){
     if(!enabled())return;
     const start=Math.round(clip.start*1000),sourceIn=Math.round(clip.sourceIn*1000);
     const out=Math.round((clip.sourceIn+clip.duration)*1000);
     if(action==='tail'?out===visibleOut:start===music.start_ms&&sourceIn===music.in_ms)return;
     touch();
     const target=owner.doc.music;
     if(action==='tail')target.out_ms=out;
     else{target.start_ms=start;if(action==='head')target.in_ms=sourceIn;}
     paint();
     if(event?.type==='keydown'){
       const target=action==='move'?bar:bar.querySelector('.'+action);target?.focus({preventScroll:true});
     }
   }
   function bind(control,action){
     bindings.push(editor.bind(control,{action,read,geometry,constraints:()=>limits(action),enabled,
       select(event){event.preventDefault();control.focus({preventScroll:true});},
       preview,commit,cancel:()=>preview(read(),{action:'move'})}));
   }
   bind(bar,'move');
   function boundary(event){
     if(!enabled()||event.target!==bar||event.metaKey||event.ctrlKey||!['Home','End'].includes(event.key))return;
     event.preventDefault();const original=read(),delta=event.key==='Home'?-length/1000:length/1000;
     commit(editor.change(original,'move',delta,limits('move')),{action:'move',event});
   }
   bar.addEventListener('keydown',boundary);
   if(native)for(const action of ['head','tail']){
     const edge=document.createElement('button');edge.type='button';edge.className='trim-handle '+action;
     edge.setAttribute('aria-label',tr(action==='head'?'音源入点（秒）':'音源出点（秒）'));edge.disabled=toolBusy();
     // The parent is also the focusable move control. Only the edge edits the source endpoints.
     edge.addEventListener('pointerdown',event=>event.stopPropagation());
     edge.addEventListener('keydown',event=>{if(['ArrowLeft','ArrowRight','Home','End'].includes(event.key))event.stopPropagation();});
     bar.append(edge);bind(edge,action);
   }
   preview(read(),{action:'move'});
   releaseScore=()=>{for(const release of bindings)release();bar.removeEventListener('keydown',boundary);};
 }
 function drawTrack(n,music){
   if(audioBinding()&&!s.doc.clips.length){
     const id=JSON.stringify(audioBinding());if(s.scoreViewSource!==id){s.scoreViewSource=id;s.scoreViewMs=0;}
     s.scoreViewMs=Math.max(s.scoreViewMs||0,n);n=s.scoreViewMs;
   }else{s.scoreViewSource='';s.scoreViewMs=0;}
   const ruler=$('Ruler'),lane=$('MusicLane'),bar=$('MusicSpan'),native=imwActive();
   root.toggleAttribute('data-imw-clips',native);strip.classList.toggle('track-row',native);
   lane.classList.toggle('track-row',native);bar.classList.toggle('clip-group',native);
   $('Tracks').hidden=false;ruler.hidden=$('Needle').hidden=!n;ruler.replaceChildren();
   for(const step of [0,1,2,3,4]){const tick=document.createElement('span');tick.textContent=fmt(Math.round(n*step/4))+' s';ruler.append(tick);}
   if(native){lane.hidden=true;$('AudioHeight').hidden=true;releaseScore?.();releaseScore=null;bar.replaceChildren();return;}
   const song=music&&songOf(music),end=music&&Math.min(n,music.start_ms+(music.out_ms??song?.duration_ms??0)-music.in_ms);
   lane.hidden=!song||end<=music.start_ms;$('AudioHeight').hidden=lane.hidden;
   const bindingKey=JSON.stringify([key,n,native,!!s.doc.clips.length,music,song?.title,song?.duration_ms,toolBusy(),
     s.conflict,document.documentElement.lang]);
   if(releaseScore&&scoreBindingKey===bindingKey)return;
   releaseScore?.();releaseScore=null;scoreBindingKey=bindingKey;
   if(music){bar.setAttribute('aria-valuemin','0');bar.setAttribute('aria-valuemax',String(Math.max(0,n-1)));
     bar.setAttribute('aria-valuenow',String(music.start_ms));bar.setAttribute('aria-valuetext',clock(music.start_ms));}
   if(song&&n&&end>music.start_ms){bar.style.left=100*music.start_ms/n+'%';bar.style.width=100*(end-music.start_ms)/n+'%';
     const label=document.createElement('span');label.textContent=song.title;
     const wave=document.createElement('span');wave.className='dc-song-wave';
     if(native){
       const region=document.createElement('span');region.className='clip';label.className='dc-sr';
       region.append(label,wave);bar.replaceChildren(region);
     }else bar.replaceChildren(label,wave);
     bindScore(music,song,n,bar,wave,native);
     bar.title=song.title+' · '+fmt(music.start_ms)+'–'+fmt(end)+' s';}
 }
 function moveTimelineClip(clips,clip,index){
   if(clips.indexOf(clip)===index||s.busy)return;
   touch();clips.splice(clips.indexOf(clip),1);clips.splice(index,0,clip);
   selected=clip.id;cursor=startOf(selected);paint();
 }
 function placeVideoAt(clip,rows,start){
   const end=start+durationOf(clip);
   const ordered=[...rows,{clip,start,end}].sort((a,b)=>a.start-b.start);
   let previous=0;
   const next=ordered.map(row=>{
     const gap=row.start-previous;
     previous=row.end;
     const item={...row.clip};
     if(gap)item.gap_before_ms=gap;else delete item.gap_before_ms;
     return item;
   });
   if(shortClip({clips:next})>=0||sameValue(next,s.doc.clips))return;
   const resume=!!preview?.isPlaying(),position=cursor;
   touch();s.doc.clips=next;selected=clip.id;cursor=position;paint();
   seekTo(position);
   if(resume)preview?.play();
 }
 function bindIMWClipMove(button,clip){
   button.onpointerdown=event=>{
     if(!event.metaKey||event.button!==0||!event.isPrimary||s.busy)return;
     event.preventDefault();button.focus({preventScroll:true});
     const owner=s,id=event.pointerId,start=event.clientX;
     const listeners=new AbortController(),options={signal:listeners.signal};
     const studio=document.querySelector('lus-studio'),playhead=studio.clipPlayhead();
     const geometry=positions(s.doc.clips),original=geometry.find(row=>row.clip===clip);
     const other=geometry.filter(row=>row.clip!==clip),group=button.parentElement;
     let target=null,moved=false,snapped=null;
     function clearTarget(){target?.parentElement.removeAttribute('data-drop');target=null;}
     function showSnap(position){
       snapped=position;
       playhead.mark(position!==null);
       group.toggleAttribute('data-snapped',position!==null);
       group.style.transform=position===null?'':'translateX('+((position-original.start)*strip.clientWidth/displaySpan())+'px)';
     }
     function update(e){
       if(e.pointerId!==id)return;
       if(Math.abs(e.clientX-start)>=3)moved=true;
       clearTarget();
       if(!moved)return;
       const box=strip.getBoundingClientRect();
       if(e.clientY<box.top||e.clientY>=box.bottom){showSnap(null);return;}
       const at=playhead.position();
       const secondsPerPixel=displaySpan()/1000/Math.max(1,strip.clientWidth);
       const delta=(e.clientX-start)*secondsPerPixel;
       const exact=e.metaKey ? globalThis.OAStudio.clipEditing.playheadDelta(delta,
         [original.start/1000,original.end/1000],at,secondsPerPixel,difference=>{
           const left=Math.round(original.start+difference*1000),right=left+durationOf(clip);
           return left>=0&&other.every(row=>right<=row.start||left>=row.end);
         }) : null;
       showSnap(exact===null?null:Math.round(original.start+exact*1000));
       if(snapped!==null)return;
       target=[...strip.querySelectorAll('button[data-clip]')].find(item=>{
         const rect=item.getBoundingClientRect();
         return e.clientX>=rect.left&&e.clientX<rect.right;
       })||null;
       if(target&&target!==button){
         const side=owner.doc.clips.indexOf(clip)<owner.doc.clips.findIndex(c=>c.id===target.dataset.clip)
           ? 'after':'before';
         target.parentElement.setAttribute('data-drop',side);
       }
     }
     function cancel(){
       clearTarget();showSnap(null);listeners.abort();
       if(button.hasPointerCapture(id))button.releasePointerCapture(id);
     }
     button.setPointerCapture(id);
     button.addEventListener('pointermove',update,options);
     button.addEventListener('pointerup',e=>{
       if(e.pointerId!==id)return;
       if(!moved)update(e);
       const position=snapped;
       const index=target?owner.doc.clips.findIndex(c=>c.id===target.dataset.clip):-1;
       cancel();
       if(s!==owner||!button.isConnected)return;
       if(position!==null)placeVideoAt(clip,other,position);
       else if(index>=0)moveTimelineClip(owner.doc.clips,clip,index);
     },options);
     button.addEventListener('lostpointercapture',cancel,options);
     button.addEventListener('pointercancel',cancel,options);
     window.addEventListener('blur',cancel,options);
     document.addEventListener('keydown',e=>{if(e.key==='Escape')cancel();},options);
   };
 }
 function paint(){
   if(!s)return;
   const clips=s.doc.clips,c=cut(),index=clips.indexOf(c),music=s.doc.music,n=total();
   const awaiting=s.busy||!s.loaded||s.previewOnOpen,invalid=shortClip();
   for(const panel of panels)panel.querySelectorAll('button,input,select').forEach(el=>el.disabled=awaiting);
   auto.journal(s);showSaveState();
   const picked=$('Source').value;
   selectOptions($('Source'),s.sources.map(r=>[r.delivery_id,r.title+' · '+fmt(r.duration_ms)+' s · '+r.sha256.slice(0,8)+(r.adopted?' · '+tr('已采用'):'')]),picked||activeDelivery,
     s.sources.length?'':tr('当前作品没有可剪辑的视频'));
   $('Add').disabled=awaiting||!$('Source').value;
   selectOptions($('Song'),s.songs.map(r=>[r.attempt_id,r.title+' · '+r.sha256.slice(0,8)]),music?.attempt_id||'',tr('无配乐'));
   if(music&&!songOf(music)){$('Song').add(new Option(tr('此素材已不可用'),music.attempt_id));$('Song').value=music.attempt_id;}
   observer?.disconnect();resetFilms();strip.replaceChildren();drawTrack(span(),music);syncGeometry();
   if(!clips.length){const p=document.createElement('small');p.textContent=tr(music?'没有片段':'从右侧「添加」选择视频或配乐');strip.append(p);}
   let clipStart=0;
   for(const [i,clip] of clips.entries()){
     const row=sourceOf(clip),button=document.createElement('button'),title=document.createElement('strong'),duration=document.createElement('small');
     button.type='button';button.disabled=awaiting;button.dataset.clip=clip.id;
     button.setAttribute('aria-pressed',String(clip===c));button.draggable=!awaiting&&!imwActive();
     clipStart+=gapBefore(clip);
     const width=100*durationOf(clip)/Math.max(n,1)+'%';
     title.textContent=(i+1)+' · '+(row?.title||tr('此素材已不可用'));duration.textContent=fmt(clip.out_ms-clip.in_ms)+' s';
     const poster=document.createElement('img');poster.className='dc-frame';poster.alt='';poster.hidden=true;
     poster.onload=()=>{poster.hidden=false;};poster.dataset.ref=JSON.stringify({target:scope,clip});
     const head=trimHandle(button,clip,'in',duration),tail=trimHandle(button,clip,'out',duration);
     button.append(poster,title,duration);
     if(imwActive()){
       const group=document.createElement('div');group.className='clip-group';button.className='clip';
       group.style.left='calc(var(--imw-ms) * '+clipStart+')';
       group.style.width='calc(var(--imw-ms) * '+(clip.out_ms-clip.in_ms)+')';
       group.toggleAttribute('data-selected',clip===c);group.classList.toggle('offline',!row);
       group.toggleAttribute('data-tight',strip.clientWidth*(clip.out_ms-clip.in_ms)/Math.max(displaySpan(),1)<28);
       group.append(button,head,tail);strip.append(group);
       if(row){
         const band=document.createElement('span');band.className='dc-film';band.setAttribute('aria-hidden','true');
         poster.replaceWith(band);registerFilm(band,clip);
       }
     }else{button.style.width=width;button.style.marginInlineStart=100*gapBefore(clip)/Math.max(n,1)+'%';button.append(head,tail);strip.append(button);}
     clipStart+=clip.out_ms-clip.in_ms;
     button.title=title.textContent+' · '+duration.textContent;
     if(imwActive())bindIMWClipMove(button,clip);
     else{
       button.ondragstart=event=>{dragID=clip.id;event.dataTransfer.setData('text/plain',dragID);event.dataTransfer.effectAllowed='move';};
     button.ondragover=event=>{if(dragID)event.preventDefault();};
     button.ondrop=event=>{event.preventDefault();if(!dragID||dragID===clip.id||s.busy)return;
       const moved=clips.find(c=>c.id===dragID);dragID='';if(!moved)return;
       moveTimelineClip(clips,moved,i);};
       button.ondragend=()=>{dragID='';};
     }
     button.onclick=()=>previewToolClip(clip.id);
     if(row?.audio_tracks>0&&!clip.audio_detached){
       const wave=document.createElement('span');wave.className='dc-source-wave';button.append(wave);
       waves.attach(wave,{...scope,clipSound:true,delivery_id:clip.delivery_id,sha256:clip.sha256,
         in_ms:clip.in_ms,out_ms:clip.out_ms,volume:clip.volume});
     }
     if(observer&&poster.isConnected)observer.observe(poster.parentElement);
   }
   updateDetachButton();
   if(c?.audio_detached)$('Volume').disabled=true;
   $('Inspector').hidden=!c;
   if(c){$('In').value=fmt(c.in_ms);$('Out').value=fmt(c.out_ms);$('Volume').value=c.volume;}
   const scorePanel=$('MusicFields').parentElement;
   scorePanel.hidden=imwActive()&&!archivedWindow();
   scorePanel.querySelector(':scope>label').hidden=imwActive();
   $('MusicFields').hidden=!music;
   if(music){$('MusicIn').value=fmt(music.in_ms);$('MusicOut').value=fmt(music.out_ms??songOf(music)?.duration_ms??music.in_ms);$('MusicStart').value=fmt(music.start_ms);$('MusicVolume').value=music.volume;}
   showExportSource();
   const job=(!dirty()&&s.job?.timeline_version===s.version)?s.job.state:'';
   $('Export').textContent=tr(({RUNNING:'查询导出',UNKNOWN:'查询导出',FAILED:'重试导出',INTERRUPTED:'重试导出',SAVED:'查看导出成片'})[job]||'导出 MP4');
   $('Play').disabled=awaiting||!span();$('Seek').disabled=awaiting||!span();
   playState(!!preview?.isPlaying());
   $('Codex').disabled=$('Score').disabled=awaiting||s.conflict||invalid>=0||!canSend();
   $('Codex').title=$('Score').title=canSend()?'':tr('当前宿主无法向 Codex 发送消息');
   $('Source').disabled=awaiting||!s.sources.length;
   $('Song').disabled=awaiting||(!s.songs.length&&!music);
   $('Refresh').disabled=s.busy;$('Reload').hidden=!s.conflict;
   displayStatus(s.message,s.detail);
   if(invalid>=0)$('Status').textContent='#'+(invalid+1)+' · '+tr('片段不足一个输出帧（30 fps）');
   updateCursor();notifyTools();detachedChanged();
 }
 function accept(response,state,force){
   const doc=OADirectorCutDocument(response);
   state.sources=response.sources;state.songs=response.songs;
   if(!state.loaded||force||JSON.stringify(state.doc)===state.saved){
     if(force||state.version!==response.timeline_version){state.undo=[];state.redo=[];}
     state.doc=clone(doc);state.saved=JSON.stringify(doc);state.version=response.timeline_version;
     state.loaded=true;state.conflict=false;
   }else if(state.version!==response.timeline_version){state.conflict=true;state.message='其他窗口已保存新版。当前草稿已保留。';state.detail='';}
 }
 function reload(force=false){
   const here=s;if(!here)return Promise.resolve(false);
   here.latestReload=loadLatest(here,scope,++readSerial,force);return here.latestReload;
 }
 async function checkTimelineRevision(afterPending=false){
   const here=s,target=scope;
   if(!here||root.hidden||document.hidden)return null;
   if(here.checking){
     if(!afterPending)return here.checking;
     try{await here.checking;}catch(_){}
     if(s!==here||scope!==target)return null;
   }
   const checking=(async()=>{
     const stamp=await read('timeline_revision',target);
     if(s!==here||scope!==target||stamp.project_id!==target.project_id||stamp.work_id!==target.work_id||
        !Number.isSafeInteger(stamp.timeline_version))return null;
     if(!here.busy&&!here.conflict&&!here.sync.running&&!here.sync.intent&&(!here.loaded||stamp.timeline_version>here.version)){
       let pending=reload();await pending;
       while(s===here&&scope===target&&here.latestReload!==pending){pending=here.latestReload;await pending;}
     }
     return s===here&&scope===target?stamp:null;
   })();
   here.checking=checking;
   try{return await checking;}finally{if(here.checking===checking)here.checking=null;}
 }
 async function loadLatest(here,target,seq,force){
   const epoch=here.sync.epoch;
   try{
     const response=await read('timeline',target);
     if(seq!==readSerial||s!==here||response.project_id!==target.project_id||response.work_id!==target.work_id)return;
     if(here.loaded&&response.timeline_version<here.version)return false;
     here.exportIds=new Set((response.exports||[]).map(row=>row.delivery_id));
     const keepDraft=!force&&here.loaded&&(here.sync.running||here.sync.intent||epoch!==here.sync.epoch);
     if(keepDraft&&!here.previewOnOpen){
       here.sources=response.sources;here.songs=response.songs;paint();return true;
     }
     const incoming=!keepDraft&&here.loaded&&!force&&!here.conflict&&!dirty()&&response.timeline_version>here.version;
     const previous=incoming?here.doc:null,priorVersion=here.version;
     if(!here.loaded||incoming||force)resetPreview();
     if(here.message==='读取失败'||!here.loaded||force){here.message='';here.detail='';}
     if(keepDraft){here.sources=response.sources;here.songs=response.songs;}
     else{
       accept(response,here,force);
       if(force)auto.abandon(here);else auto.discover(here,response);
     }
     const resume=here.previewOnOpen&&!force&&!here.conflict&&here.resumeView?.version===response.timeline_version
       ?here.resumeView:null;
     const opening=here.previewOnOpen;here.previewOnOpen=false;
     if(resume){selected=resume.selected;cursor=Math.min(span(),resume.cursor);}
     syncJob(response);if(!cut())selected=here.doc.clips[0]?.id||'';paint();
     if(incoming&&!dirty()&&!here.conflict&&!sameValue(previous,here.doc)){
       if(!opening&&here.version===priorVersion+1)here.undo=[clone(previous)];
       const index=here.doc.clips.findIndex((clip,i)=>!sameValue(clip,previous.clips[i]));
       if(index>=0)previewToolClip(here.doc.clips[index].id);
       else if(here.doc.clips.length<previous.clips.length&&here.doc.clips.length)previewToolClip(here.doc.clips.at(-1).id);
       else if(span())seekTo(Math.min(span()-1,here.doc.music?.start_ms??cursor));
       notifyTools();
     }
     if(opening){
       if(resume&&span())seekTo(resume.cursor);
       else if(cut()&&!preview)previewToolClip(selected);
     }
     return true;
   }catch(err){if(seq===readSerial&&s===here){
     if(here.previewOnOpen&&here.loaded){
       here.previewOnOpen=false;
       if(here.resumeView){selected=here.resumeView.selected;seekTo(here.resumeView.cursor);}
     }
     say('读取失败',err.message);paint();
   }return false;}
 }
 async function selectToolSource(deliveryId){
   if(!deliveryId||!s||s.busy)return false;
   const here=s,target=scope;
   let request=reload();await request;
   while(s===here&&scope===target&&here.latestReload!==request){request=here.latestReload;await request;}
   if(s!==here||scope!==target||!s.sources.some(row=>row.delivery_id===deliveryId))return false;
   $('Source').value=deliveryId;return $('Source').value===deliveryId;
 }
 function clear(){
   releaseScore?.();releaseScore=null;
   if(s)s.checking=null;
   loopEnabled=false;loopIn=0;loopOut=null;transportStart=null;playTicket=null;waves.reset();displayStatus('','');cancelStatus();observer?.disconnect();resetFilms();thumbs.clear();pictureBatches.clear();dragID='';resetPreview();
   if(s?.loaded&&!s.previewOnOpen)s.resumeView={version:s.version,selected,cursor};
   readSerial++;key='';scope=null;s=null;lastSignal='';root.hidden=settings.hidden=transport.hidden=true;menu(false);selected='';cursor=0;activeDelivery='';updateDetachButton();notifyTools();detachedChanged();
 }
 function workDraft(target){
   const id=JSON.stringify(target);
   if(drafts.has(id))return drafts.get(id);
   const draft={doc:{clips:[],music:null,detached_audio:[]},sources:[],songs:[],loaded:false,version:0,saved:'',busy:false,undo:[],redo:[],
     message:'正在读取…',detail:'',conflict:false};
   auto.init(draft,target);drafts.set(id,draft);return draft;
 }
 function render(state,active){
   if(!state?.work||state.work.inbox||state.work.kind==='article'){if(s)clear();return;}
   const next=JSON.stringify(state.scope),changed=next!==key;
   if(changed){clear();key=next;scope=state.scope;
     s=workDraft(scope);s.previewOnOpen=true;root.hidden=settings.hidden=transport.hidden=false;paint();signalMonitor();}
   const chosen=active?.id||'';
   if(chosen!==activeDelivery){activeDelivery=chosen;if(s.sources.some(r=>r.delivery_id===chosen))$('Source').value=chosen;}
   const signature=JSON.stringify([state.workVersion,state.cards.map(c=>[c.id,c.state])]);
   if(!s.busy&&(changed||signature!==lastSignal)){lastSignal=signature;void reload();}
 }
 function clipIndexAt(ms){
   for(const {clip,start,end} of positions(s.doc.clips)){
     if(ms<start)break;
     if(ms<end)return {clip,startMs:start,sourceMs:clip.in_ms+ms-start};
   }
   return null;
 }
 function restore(from,to){
   if(!s[from].length)return;const wasPreview=!!preview;resetPreview();s[to].push(clone(s.doc));s.doc=s[from].pop();
   if(!cut())selected=s.doc.clips[0]?.id||'';paint();if(wasPreview&&cut())previewToolClip(selected,false);
 }
 $('Add').onclick=()=>{
   const row=s.sources.find(item=>item.delivery_id===$('Source').value);if(!row)return;
   touch();selected=uid();cursor=total();s.doc.clips.push({id:selected,delivery_id:row.delivery_id,sha256:row.sha256,in_ms:0,out_ms:row.duration_ms,volume:s.doc.music?0:100});paint();
 };
 // Detached regions belong to the film edit. Folding keeps its scope only in the same audio workspace.
 let folded=null;
 function currentSelection(){
   const studio=document.querySelector('lus-studio');
   return [studio?.project?.id||'',studio?.song?.id||'',studio?.version?.id||''];
 }
 function detachedOwner(){
   if(imwActive()||document.body.dataset.workbench==='monitor')return s?.loaded?s:null;
   if(document.body.dataset.workbench!=='l-unify'||!folded)return null;
   if(!sameValue(currentSelection(),folded.selection))return null;
   return folded.state;
 }
 function retainFolded(target,selection){
   folded=null;
   if(!target||!s?.loaded||scope?.project_id!==target.project_id||scope.work_id!==target.work_id)return;
   const ids=currentSelection();
   if(selection&&(!sameValue(ids,[selection.project||'',selection.song||'',selection.version||''])))return;
   const music=archivedWindow(),source=monitorState('source');
   folded={state:s,selection:ids,offsetSeconds:music?(music.start_ms-music.in_ms)/1000:0,
     sourceAudible:!source.mute&&(source.solo||!groupMonitors.get(key)?.score.solo),sourceSolo:source.solo,
     scoreAudible:!groupMonitors.get(key)?.score.mute&&(!source.solo||!!groupMonitors.get(key)?.score.solo)};
 }
 async function restoreFolded(target,selection,binding,isCurrent){
   if(!isCurrent()||!target||target.project_id!==selection?.project)return;
   const state=workDraft(target),stamp=state.sync.epoch;
   const response=await read('timeline',target);
   if(!isCurrent()||response.work_id!==target.work_id||response.project_id!==target.project_id)return;
   if(!state.loaded||(!state.sync.running&&!state.sync.intent&&stamp===state.sync.epoch&&response.timeline_version>=state.version)){
     accept(response,state,false);auto.discover(state,response);
   }
   const music=state.doc.music;
   folded={state,selection:[selection.project,selection.song||'',selection.version||''],
     offsetSeconds:music&&binding?.source?.sha256===music.sha256&&binding.song===selection.song&&binding.version===selection.version?
       (music.start_ms-music.in_ms)/1000:0};
   detachedChanged();
 }
 function detachedChanged(){document.dispatchEvent(new CustomEvent('jiusera:detached-audio-change'));}
 function detachedAudio(){
   const state=detachedOwner();if(!state)return {project:'',work:'',rows:[],selected:'',busy:true};
   const active=state===s&&imwActive(),music=active&&archivedWindow();
   return {project:state.target.project_id,work:state.target.work_id,selected:state.selectedAudio||'',
     folded:!active,selection:!active?folded?.selection:undefined,
     scoreAudible:active?monitorState('score').audible:folded?.scoreAudible??true,
     busy:state.busy||state.conflict,canUndo:!!state.undo.length,canRedo:!!state.redo.length,
     saveError:state.conflict?'版本冲突':state.sync.error||'',
     pictureMs:total(state.doc.clips),
     offsetSeconds:active?(music?(music.start_ms-music.in_ms)/1000:0):folded?.offsetSeconds||0,
     sourceAudible:active?monitorState('source').audible:folded?.sourceAudible??true,
     sourceSolo:active?monitorState('source').solo:folded?.sourceSolo??false,
     rows:state.doc.detached_audio.map(row=>{
       const asset=state.sources.find(r=>r.delivery_id===row.delivery_id&&r.sha256===row.sha256);
       return {...row,title:asset?.title||tr('此素材已不可用'),source_ms:asset?.duration_ms||row.out_ms};
     })};
 }
 // Audio lanes survive closing the video monitor, including waveform reads still in flight.
 const laneWaves=OADirectorWaveforms(read,()=>document.documentElement.lang==='en');
 let waveOwner=null;
 function detachedWave(host,id){
   const state=detachedOwner(),row=state?.doc.detached_audio.find(r=>r.id===id);
   if(!row)return;
   if(waveOwner!==state){laneWaves.reset();waveOwner=state;}
   laneWaves.attach(host,{...state.target,delivery_id:row.delivery_id,sha256:row.sha256,
     in_ms:row.in_ms,out_ms:row.out_ms,volume:row.volume});
 }
 async function detachedChunk(id,offset){
   const state=detachedOwner(),row=state?.doc.detached_audio.find(r=>r.id===id);
   if(!row)throw Error('DIRECTOR_ASSET_CHANGED');
   const result=await chunk(state.target,row,offset);
   if(state!==detachedOwner()||!state.doc.detached_audio.some(r=>r.id===id&&r.sha256===row.sha256))
     throw Error('DIRECTOR_ASSET_CHANGED');
   return result;
 }
 function updateDetachButton(){
   const btn=$('Detach'),c=s?.loaded&&cut(),en=document.documentElement.lang==='en';
   const hasAudio=c&&sourceOf(c)?.audio_tracks>0;
   const label=c?.audio_detached?(en?'Audio separated':'音频已分离'):(en?'Detach audio':'分离音频');
   btn.textContent=label;btn.disabled=!hasAudio||!!c.audio_detached||toolBusy()||s.doc.detached_audio.length>=256;
   btn.title=!c?(en?'Select a video clip':'请选择视频片段'):!hasAudio?(en?'No audio stream in this clip':'此片段没有音轨'):label;
 }
 function detachSelected(){
   const c=s?.loaded&&cut();
   if(toolBusy()||!c||c.audio_detached||!sourceOf(c)?.audio_tracks||s.doc.detached_audio.length>=256)return false;
   const row={id:uid(),clip_id:c.id,delivery_id:c.delivery_id,sha256:c.sha256,start_ms:startOf(c.id),
     in_ms:c.in_ms,out_ms:c.out_ms,volume:c.volume};
   const wasPreview=!!preview;
   touch();c.audio_detached=true;s.doc.detached_audio.push(row);s.selectedAudio=row.id;paint();
   if(wasPreview)seekTo(cursor);
   return true;
 }
 $('Detach').onclick=detachSelected;
 function editDetached(id,patch){
   const state=detachedOwner();if(!state||state.busy||state.conflict)return false;
   const rows=state.doc.detached_audio,row=rows.find(r=>r.id===id);
   if(patch==='undo'||patch==='redo'){
     const from=patch,to=patch==='undo'?'redo':'undo';
     if(!state[from].length)return false;
     if(state===s)restore(from,to);
     else{state[to].push(clone(state.doc));state.doc=state[from].pop();auto.journal(state);detachedChanged();}
     return true;
   }
   if(!row)return false;
   if(patch==='select'){
     if(state.selectedAudio!==id){state.selectedAudio=id;detachedChanged();}
     return true;
   }
   let next,tail;
   if(patch==='split'||Number.isSafeInteger(patch?.split_at_ms)){
     const at=patch==='split'?Math.round(cursor):patch.split_at_ms;
     const cutMs=row.in_ms+at-row.start_ms;
     if(cutMs<=row.in_ms||cutMs>=row.out_ms||rows.length>=256)return false;
     next={...row,out_ms:cutMs};tail={...row,id:uid(),in_ms:cutMs,start_ms:at};
   }else if(patch!=='remove'){
     if(!patch||typeof patch!=='object'||!Object.keys(patch).every(k=>['start_ms','in_ms','out_ms','volume'].includes(k)))return false;
     next={...row,...patch};
     const source=state.sources.find(r=>r.delivery_id===row.delivery_id&&r.sha256===row.sha256);
     if(!source||!['start_ms','in_ms','out_ms','volume'].every(k=>Number.isSafeInteger(next[k])&&next[k]>=0)||
       next.in_ms>=next.out_ms||next.out_ms>source.duration_ms||next.volume>100)return false;
     if(sameValue(next,row))return true;
   }
   const wasPreview=state===s&&!!preview;
   touch(state);const index=rows.indexOf(row);
   if(patch==='remove')rows.splice(index,1);else if(tail)rows.splice(index,1,next,tail);else rows[index]=next;
   state.selectedAudio=tail?.id||(patch==='remove'?'':id);
   if(state===s){paint();if(wasPreview)seekTo(cursor);}
   else{auto.journal(state);detachedChanged();}
   return true;
 }
 function getToolState(){
   const c=s&&cut(),index=c?s.doc.clips.indexOf(c):-1,ready=!toolBusy();
   const can={split:canSplit(),left:ready&&index>0,right:ready&&index>=0&&index<s.doc.clips.length-1,
     delete:ready&&index>=0,undo:!!(ready&&s.undo.length),redo:!!(ready&&s.redo.length),retry:!!(s?.sync.error&&!s.conflict)};
   let saveStatus='loading',badge='';
   if(s?.loaded){
     const sync=s.sync;
     saveStatus=s.conflict?'conflict':sync.error?'error':sync.running?'saving':dirty()&&shortClip()>=0?'invalid':(sync.intent||dirty())?'pending':'saved';
     const labels={invalid:'未保存',conflict:'版本冲突',error:'自动保存失败',saving:'自动保存中',pending:'等待自动保存',saved:'已保存'};
     badge='v'+s.version+' · '+tr(labels[saveStatus]);
     if(!sync.durable)badge+=' · '+tr('草稿仅在当前窗口');
   }
   return {can,readFailed:s?.message==='读取失败',version:s?.version??0,saveStatus,saveLabel:badge};
 }
 function showSaveState(){
   if(!s)return;const view=getToolState();
   $('Version').value=view.saveLabel;$('Version').title=s.sync.error||view.saveLabel;
   $('Retry').hidden=!view.can.retry;$('Recover').hidden=!s.sync.orphan||dirty()||!!s.sync.running||s.conflict;
   $('Reload').hidden=!s.conflict;$('Reload').disabled=!!s.sync.running||s.busy;
 }
 function runToolCommand(action){
   if(!getToolState().can[action])return false;
   switch(action){
     case 'split':split();break;
     case 'left':move(-1);break;
     case 'right':move(1);break;
     case 'delete':removeClip();break;
     case 'undo':restore('undo','redo');break;
     case 'redo':restore('redo','undo');break;
     case 'retry':void auto.flush(s,true);break;
     default:return false;
   }
   return true;
 }
 // Own plain Space before a focused control scrolls, activates or toggles itself.
 document.addEventListener('keydown',event=>{
   if((event.code!=='Space'&&event.key!==' ')||event.defaultPrevented||event.isComposing||event.keyCode===229||
      event.altKey||event.ctrlKey||event.metaKey||event.shiftKey||!editingVideo())return;
   const el=event.composedPath()[0];
   if(el?.isContentEditable||el?.closest?.('textarea,[role=textbox]')||
      (el?.tagName==='INPUT'&&['text','search','email','url','tel','password','file'].includes(el.type))||
      [...document.querySelectorAll('dialog[open],[role=dialog],[aria-modal=true]')].some(node=>node.getClientRects().length))return;
   const canPlayCut=s?.loaded&&!root.hidden&&!$('Play').disabled;
   if(!canPlayCut&&!toggleSourcePlayback)return;
   // Swallow auto-repeat too, including the native default of a focused button.
   if(imwActive()&&s?.loaded&&!root.hidden){
     event.preventDefault();event.stopImmediatePropagation();
     if(!event.repeat)document.dispatchEvent(new CustomEvent('jiusera:imw-transport-command',{detail:{action:'play',inputEvent:event}}));
     return;
   }
   if(event.repeat){event.preventDefault();event.stopPropagation();return;}
   if(!s||root.hidden){if(!toggleSourcePlayback?.(event,false))return;}
   else void togglePlayback(event,true);
   event.preventDefault();event.stopPropagation();
 },true);
 document.addEventListener('keydown',event=>{
   if(event.defaultPrevented||event.isComposing||event.altKey||event.repeat||!s?.loaded||
      !editingVideo()||root.hidden||!root.getClientRects().length)return;
   const el=event.composedPath()[0];
   if(el?.isContentEditable||el?.closest?.('input,textarea,select,[role=textbox],[contenteditable=true]')||
      [...document.querySelectorAll('dialog[open],[role=dialog],[aria-modal=true]')].some(node=>node.getClientRects().length))return;
   if(imwActive()&&el?.getRootNode?.().host?.localName==='lus-studio'&&
      el.closest('[data-track-row],#track-editor,#clip-menu,#inspector'))return;
   const key=event.key.toLowerCase(),modifier=event.metaKey||event.ctrlKey;
   if(modifier){
     const action=key==='z'?(event.shiftKey?'redo':'undo'):key==='y'&&event.ctrlKey&&!event.shiftKey?'redo':
       key==='b'&&!event.shiftKey?'split':'';
     if(action&&runToolCommand(action))event.preventDefault();return;
   }
   if(event.shiftKey)return;
   if(key==='backspace'||key==='delete'){
     if(el?.closest?.('.dc-music,#dmCutMusicLane,#dmCutAudioHeight')||
        document.getElementById('videoDirectorDesk')?.dataset.dtView==='audio')return;
     if(runToolCommand('delete'))event.preventDefault();
   }
 });
 function trackHeight(gripName,node,min,max,property){
   const grip=$(gripName),tracks=$('Tracks');
   const current=()=>Math.round(node.getBoundingClientRect().height);
   const apply=value=>{const height=Math.max(min,Math.min(max,Math.round(value)));
     tracks.style.setProperty(property,height+'px');grip.setAttribute('aria-valuenow',height);};
   grip.setAttribute('aria-valuemin',min);grip.setAttribute('aria-valuemax',max);
   grip.onfocus=()=>grip.setAttribute('aria-valuenow',current());
   grip.onpointerdown=e=>{
     if(e.button!==0)return;
     e.preventDefault();const height=current(),y=e.clientY;grip.setPointerCapture(e.pointerId);
     grip.onpointermove=event=>apply(height+event.clientY-y);
     grip.onpointerup=grip.onpointercancel=()=>{grip.onpointermove=grip.onpointerup=grip.onpointercancel=null;};
   };
   grip.onkeydown=e=>{
     if(!['ArrowUp','ArrowDown','Home','End'].includes(e.key))return;
     e.preventDefault();apply(e.key==='Home'?min:e.key==='End'?max:current()+(e.key==='ArrowUp'?-4:4));
   };
 }
 trackHeight('VideoHeight',strip,40,180,'--dc-video-height');
 trackHeight('AudioHeight',$('MusicLane'),30,120,'--dc-audio-height');
 const musicBar=$('MusicSpan');
 musicBar.addEventListener('focusin',()=>musicBar.toggleAttribute('data-selected',true));
 musicBar.addEventListener('focusout',event=>{if(!musicBar.contains(event.relatedTarget))musicBar.removeAttribute('data-selected');});
 function toolBusy(){return !s?.loaded||s.busy||s.conflict;}
 function getToolClips(){return s?.loaded?clone(s.doc.clips):[];}
 function getToolMusic(){
   const music=s?.loaded&&s.doc.music,row=music&&songOf(music);if(!row)return null;
   const available=span()-music.start_ms;
   const out=Math.min(music.out_ms??row.duration_ms,music.in_ms+available);
   return out>music.in_ms?{...clone(music),out_ms:out,title:row.title}:null;
 }
 function getToolClip(){
   const c=s&&cut();if(!c)return null;
   return {...clone(c),look:clone(c.look||{}),index:s.doc.clips.indexOf(c),title:sourceOf(c)?.title||'',
     busy:toolBusy(),canDuplicate:!toolBusy()&&s.doc.clips.length<256};
 }
 function notifyTools(){document.dispatchEvent(new CustomEvent('jiusera:cut-tools-change'));}
 function previewToolClip(id=selected,startAtCut=true){
   if(!s?.loaded||s.busy)return false;
   const c=s.doc.clips.find(row=>row.id===id);if(!c)return false;
   preview?.pause();playState(false);const changed=selected!==id;selected=id;
   const start=startOf(id),end=start+c.out_ms-c.in_ms;
   const pos=startAtCut||cursor<start||cursor>=end?start:cursor;
   if(changed)paint();seekTo(pos);return true;
 }
 function writeLook(c,next){
   if(Object.keys(next).length)c.look=next;else delete c.look;
 }
 function setToolLook(patch,expected=selected){
   const c=s&&cut();if(toolBusy()||!c||c.id!==expected||!patch||typeof patch!=='object')return false;
   const next={...c.look};
   const choices={mask:['circle','letterbox'],filter:['mono','warm','cool'],effect:['vignette','blur'],transition:['fade','white']};
   for(const [field,value] of Object.entries(patch)){
     const known=['rotation','title','caption','brightness','contrast','mirror','zoom','zoom_end'].includes(field)||Object.hasOwn(choices,field);
     if(!known)return false;
     if(field==='caption')delete next.cues;
     if(value===null||value===''||value===undefined){delete next[field];continue;}
     if(field==='title'||field==='caption'){
       if(typeof value!=='string'||Array.from(value).length>(field==='title'?80:200))return false;
     }else if(field==='brightness'||field==='contrast'){
       if(!Number.isInteger(value)||value< -100||value>100)return false;
       if(!value){delete next[field];continue;}
     }else if(field==='zoom'||field==='zoom_end'){
       if(!Number.isInteger(value)||value<100||value>200)return false;
       if(field==='zoom'&&value===100){delete next.zoom;continue;}
     }else if(field==='rotation'){
       if(value===0){delete next.rotation;continue;}
       if(![90,180,270].includes(value))return false;
     }else if(field==='mirror'){
       if(typeof value!=='boolean')return false;
       if(!value){delete next.mirror;continue;}
     }else if(!choices[field].includes(value))return false;
     next[field]=value;
   }
   if(sameValue(next,c.look||{}))return true;
   touch();writeLook(c,next);paint();previewToolClip(selected,false);return true;
 }
 function setToolCaptions(assignments,expected){
   if(toolBusy()||!Array.isArray(assignments)||!assignments.length||
      (expected!==undefined&&!sameValue(expected,s.doc.clips)))return false;
   const targets=new Map(),seen=new Set();
   for(const assignment of assignments){
     if(!assignment||typeof assignment!=='object')return false;const {id,cues}=assignment;
     const c=s.doc.clips.find(clip=>clip.id===id);
     if(!c||seen.has(id)||!Array.isArray(cues)||cues.length>128)return false;seen.add(id);
     let end=0;
     for(const cue of cues){
       if(!cue||!Number.isSafeInteger(cue.in_ms)||!Number.isSafeInteger(cue.out_ms)||
          cue.in_ms<end||cue.out_ms<=cue.in_ms||cue.out_ms>(sourceOf(c)?.duration_ms??Infinity)||typeof cue.text!=='string'||!cue.text.trim()||
          Array.from(cue.text).length>200)return false;
       end=cue.out_ms;
     }
     const next={...c.look};delete next.caption;delete next.cues;
     if(cues.length)next.cues=cues.map(({in_ms,out_ms,text})=>({in_ms,out_ms,text}));
     if(!sameValue(next,c.look||{}))targets.set(c,next);
   }
   if(!targets.size)return true;touch();
   for(const [c,next] of targets)writeLook(c,next);
   paint();previewToolClip(selected,false);return true;
 }
 function duplicateToolClip(expected=selected){
   const c=s&&cut();if(toolBusy()||!c||c.id!==expected||s.doc.clips.length>=256)return false;
   touch();const next={...clone(c),id:uid()};delete next.gap_before_ms;s.doc.clips.splice(s.doc.clips.indexOf(c)+1,0,next);
   selected=next.id;paint();previewToolClip(selected);return true;
 }
 function numbers(){
   const value=(id,scale=1)=>{const el=$(id);if(!el.value.trim()||!el.validity.valid)return NaN;return Math.round(el.valueAsNumber*scale);};
   const c=cut(),m=s.doc.music;
   const inc=value('In',1000),out=value('Out',1000),volume=value('Volume');
   const musicIn=value('MusicIn',1000),musicOut=value('MusicOut',1000),start=value('MusicStart',1000),gain=value('MusicVolume');
   if((c&&(!Number.isSafeInteger(inc)||!Number.isSafeInteger(out)||!Number.isSafeInteger(volume)||inc>=out||out>(sourceOf(c)?.duration_ms??c.out_ms)))||
      (m&&(!Number.isSafeInteger(musicIn)||!Number.isSafeInteger(start)||!Number.isSafeInteger(gain)||!Number.isSafeInteger(musicOut)||musicIn>=musicOut||musicOut>(songOf(m)?.duration_ms??Infinity)))){
     say('请检查入点、出点或音量。');paint();return;
   }
   touch();if(c)Object.assign(c,{in_ms:inc,out_ms:out,volume});
   if(m){Object.assign(m,{in_ms:musicIn,start_ms:start,volume:gain});
     if(m.out_ms!==undefined||musicOut!==songOf(m)?.duration_ms)m.out_ms=musicOut;}paint();
 }
 for(const name of ['In','Out','Volume','MusicIn','MusicOut','MusicStart','MusicVolume'])$(name).onchange=numbers;
 $('Song').onchange=()=>{
   const row=s.songs.find(item=>item.attempt_id===$('Song').value);touch();
   s.doc.music=row?{attempt_id:row.attempt_id,sha256:row.sha256,in_ms:0,start_ms:0,volume:100}:null;paint();
 };
 function split(){
   const c=cut(),at=cursor-startOf(c.id);if(at<=0||at>=c.out_ms-c.in_ms)return;
   touch();const next={...clone(c),id:uid(),in_ms:c.in_ms+at};delete next.gap_before_ms;c.out_ms=next.in_ms;
   s.doc.clips.splice(s.doc.clips.indexOf(c)+1,0,next);selected=next.id;paint();
 };
 function move(direction){
   const clips=s.doc.clips,old=clips.indexOf(cut()),next=old+direction;
   if(old<0||next<0||next>=clips.length)return;touch();
   clips.splice(next,0,clips.splice(old,1)[0]);cursor=startOf(selected);paint();
 }
 function removeClip(){
   const clips=s.doc.clips,i=clips.indexOf(cut());if(i<0)return;touch();
   clips.splice(i,1);selected=clips[Math.min(i,clips.length-1)]?.id||'';cursor=selected?startOf(selected):0;paint();
 };
 $('Refresh').onclick=()=>void reload();$('Reload').onclick=()=>{if(s&&!s.sync.running)void reload(true);};
 $('Retry').onclick=()=>{if(s)void auto.flush(s,true);};
 $('Recover').onclick=async()=>{
   const here=s;if(!here||dirty()||here.sync.running)return;
   const remote=await read('timeline',here.target).catch(()=>null);
   if(!remote||s!==here||dirty()||here.sync.running||remote.project_id!==here.target.project_id||remote.work_id!==here.target.work_id)return;
   accept(remote,here,false);if(auto.recover(here,remote)){resetPreview();if(!cut())selected=here.doc.clips[0]?.id||'';paint();}
 };
 async function prepareBrief({song}){
   if(toolBusy()||shortClip()>=0)return null;
   const here=s,target=scope,clip=cut(),clipId=selected,sourceId=$('Source').value,pos=cursor;
   const snapshot=JSON.stringify(here.doc);
   const valid=()=>editingVideo()&&s===here&&scope===target&&!here.conflict&&!here.busy&&snapshot===JSON.stringify(here.doc)&&
     selected===clipId&&$('Source').value===sourceId;
   if(!await auto.flush(here,true)||!valid())return null;
   const version=here.version,source=here.sources.find(r=>r.delivery_id===sourceId),current=here.doc.music;
   const row=song?here.songs.find(r=>r.attempt_id===song.attempt_id&&r.sha256===song.sha256):current&&songOf(current);
   const music=row?{...row,...(current?.attempt_id===row.attempt_id&&current.sha256===row.sha256?current:{})}:null;
   return {...target,timeline_version:version,playhead_ms:pos,clip:clip&&{...clip,title:sourceOf(clip)?.title},source,music,
     isCurrent:()=>valid()&&here.version===version&&(!row||here.songs.some(r=>r.attempt_id===row.attempt_id&&r.sha256===row.sha256))};
 }
 async function command(kind){
   if(!s||s.busy||s.conflict||shortClip()>=0)return;
   const here=s,target={...scope},clip=cut()&&clone(cut()),playhead=cursor;
   ++readSerial;here.busy=true;
   paint();
   try{
     if(!await auto.flush(here,true)||s!==here)return;
     const title=tr('剪辑台')+' v'+here.version;
     if(kind==='export'){
       const mix=await exportMix();if(s!==here)return;
       await exportCut(here,target,title,mix);
     }else if(kind==='codex'||kind==='score'){
       const task=kind==='score'?'请为这版剪辑拟定配乐方案，按时间码标出入点、对白避让及结尾，优先使用项目已有可用音轨。':'请接续这个导演台剪辑。先读回当前剪辑和我选的片段，按本聊天里我的修改要求继续。';
       await send(task+' 用 video.director.read 的 timeline 操作核对项目、作品和最新版本。'+
         ' project_id='+target.project_id+' work_id='+target.work_id+' timeline_version='+here.version+
         ' playhead_ms='+playhead+(clip?' clip_id='+clip.id+' delivery_id='+clip.delivery_id+' sha256='+clip.sha256:'')+
         '。需要实际生成时沿用当前任务费用授权。');
       if(s===here)say('已发到当前 Codex 聊天');
     }
   }catch(err){if(s===here){
     if(/STALE|CONFLICT|TIMELINE_CHANGED/.test(err.message)){here.conflict=true;say('其他窗口已保存新版。当前草稿已保留。');}
     else say('操作未完成',err.message);
   }}finally{here.busy=false;if(s===here)paint();}
 }
 let exportTimer=0,statusSerial=0;
 function cancelStatus(){clearTimeout(exportTimer);exportTimer=0;statusSerial++;}
 function queueStatus(here,target,version){
   clearTimeout(exportTimer);
   if(s!==here||here.version!==version||document.hidden)return;
   exportTimer=setTimeout(()=>void queryExport(here,target,version),1700);
 }
 async function receiveJob(here,target,version,job,{checkFilm=false,focusFilm=false}={}){
   if(s!==here||here.version!==version)return;
   if(job.project_id!==target.project_id||job.work_id!==target.work_id||job.timeline_version!==version)
     throw Error('DIRECTOR_EXPORT_NOT_VERIFIED');
   if(job.state==='NOT_FOUND'){here.job=null;say('未找到这版剪辑的导出任务');paint();return;}
   here.job=job;
   if(job.state==='RUNNING'){
     say('正在导出…',(job.completed_clips??0)+' / '+(job.total_clips??here.doc.clips.length));
     queueStatus(here,target,version);
   }else if(job.state==='SAVED'){
     if(!job.delivery_id||!job.chat_path)throw Error('DIRECTOR_EXPORT_NOT_VERIFIED');
     if(checkFilm&&(focusFilm||here.lastDelivery!==job.delivery_id)){
       resetPreview();await onExport(target,job);if(s!==here)return;
       here.lastDelivery=job.delivery_id;
     }
     say('导出完成',job.chat_path);
   }else if(['FAILED','INTERRUPTED'].includes(job.state)){
     say(job.state==='FAILED'?'导出失败':'导出中断',typeof job.error==='string'?job.error:'');
   }else throw Error('DIRECTOR_EXPORT_NOT_VERIFIED');
   paint();
 }
 async function queryExport(here,target,version,focusFilm=false){
   if(here!==s||here.version!==version)return;
   clearTimeout(exportTimer);const ticket=++statusSerial;
   try{
     const job=await read('timeline_export_status',{...target,expected_timeline_version:version,...(here.jobMix?{studio_mix:here.jobMix}:{})});
     if(ticket===statusSerial)await receiveJob(here,target,version,job,{checkFilm:true,focusFilm});
   }catch(err){if(ticket===statusSerial&&here===s){
     here.job={state:'UNKNOWN',timeline_version:version};say('导出回执待查',err.message);
     paint();
   }}
 }
 async function exportCut(here,target,title,mix){
   if(JSON.stringify(here.jobMix??null)!==JSON.stringify(mix)){cancelStatus();here.job=null;here.lastDelivery=null;}
   here.jobMix=mix;
   const version=here.version,job=here.job?.timeline_version===version?here.job:null;
   if(job&&['RUNNING','UNKNOWN','SAVED'].includes(job.state)){
     await queryExport(here,target,version,job.state==='SAVED');return;
   }
   const args={...target,expected_timeline_version:version,title,...(mix?{studio_mix:mix}:{})};
   if(job&&['FAILED','INTERRUPTED'].includes(job.state))args.retry=true;
   say('正在导出…');paint();
   let result;
   try{result=await edit('timeline_export',args);}
   catch(err){
     if(!/^HOST_|TIMEOUT|RESPONSE_LOST/.test(err.message))throw err;
     // A timeout is not proof the worker failed to start. Read its durable job
     // before offering a new export or retrying a locally interrupted one.
     here.job={state:'UNKNOWN',timeline_version:version};
     await queryExport(here,target,version);return;
   }
   await receiveJob(here,target,version,result,{checkFilm:true});
 }
 function syncJob(response){
   if(imwActive())return; // A legacy render receipt does not identify a Studio arrangement.
   if(!response.export_job||response.export_job.timeline_version!==s.version)return;
   const job=response.export_job,here=s,active=here.job?.state;
   if(here.job?.operation_id&&job.operation_id===here.job.operation_id&&here.job.state==='SAVED'&&job.state==='RUNNING')return;
   if(job.state==='RUNNING'&&active==='RUNNING'&&exportTimer)return;
   if(job.state==='SAVED'&&here.lastDelivery===job.delivery_id)return;
   void receiveJob(here,scope,here.version,job,{checkFilm:active==='RUNNING'||active==='UNKNOWN'})
     .catch(err=>{if(s===here)say('导出回执待查',err.message);});
 }
 document.addEventListener('visibilitychange',()=>{
   if(!document.hidden&&s?.job?.state==='RUNNING')queueStatus(s,scope,s.version);
 });
 for(const [id,action] of [['Export','export'],['Codex','codex'],['Score','score']])$(id).onclick=()=>void command(action);
 function buildPreview(){
   const target={...scope},state=s,length=span(),stage=$('Preview'),surface=document.createElement('div');
   const buffers=new Map(),voices=new Set(),frameCache=new Map(),sounds=[],monitorOutputs=new Map();
   function groupOutput(ctx,track){
     const output=sound?.output?.(ctx)??ctx.destination;
     if(!imwActive())return output;
     if(!monitorOutputs.has(track)){
       const bus=ctx.createGain();bus.gain.value=Number(monitorState(track).audible);
       bus.connect(output);monitorOutputs.set(track,bus);
     }
     return monitorOutputs.get(track);
   }
   function updateMonitors(){
     for(const [track,bus] of monitorOutputs){
       const level=Number(monitorState(track).audible),now=bus.context.currentTime;
       bus.gain.cancelAndHoldAtTime(now);
       bus.gain.linearRampToValueAtTime(level,now+.004);
     }
   }
   for(const {clip:c,start,end} of positions(state.doc.clips)){
     if(!c.audio_detached&&c.volume&&sourceOf(c)?.audio_tracks>0)sounds.push({sha:c.sha256,load:offset=>chunk(target,c,offset),
       start,end,source:c.in_ms,volume:c.volume});
   }
   for(const row of state.doc.detached_audio||[]){
     if(row.volume>0&&sourceOf(row)?.audio_tracks>0)sounds.push({sha:row.sha256,load:offset=>chunk(target,row,offset),
       start:row.start_ms,end:row.start_ms+row.out_ms-row.in_ms,source:row.in_ms,volume:row.volume});
   }
   const music=state.doc.music,song=music&&songOf(music);
   const score=music?.volume&&song?{sha:music.sha256,load:offset=>audioChunk(target,music,offset)}:null;
   if(score&&!imwActive()){const end=Math.min(length,music.start_ms+(music.out_ms??song.duration_ms)-music.in_ms);
     if(end>music.start_ms)sounds.push({...score,score:true,start:music.start_ms,
       end,source:music.in_ms,volume:music.volume});}
   let closed=false,requested=false,started=false,rewinding=false,allowed=false,epoch=0,soundLease,scheduled=false;
   let base=0,wallStart=0,audioStart=null,raf=0,lastPaint=-1,frameEpoch=0,windowKey='',paintedClip='',failedFrame='';
   let compositor=null,firstAspectKnown=false,preciseMode=false,scrubbing=false,exactRequest=null,exactRunning=false,paintedAt=null;
   if(state.doc.clips.length){
     surface.className='oa-frame-screen';stage.replaceChildren(surface);showPreview(true);$('Return').hidden=false;
     compositor=OADirectorClipLook(surface);
     const first=sourceOf(state.doc.clips[0]);
     if(first?.width>0&&first?.height>0){compositor.size(first.width,first.height);firstAspectKnown=true;}
     else{
       const poster=strip.querySelector('.dc-frame');
       const measure=()=>{if(!closed&&poster?.naturalWidth&&poster.naturalHeight){firstAspectKnown=true;
         compositor.size(poster.naturalWidth,poster.naturalHeight);drawFrame();}};
       if(poster?.complete)queueMicrotask(measure);
       if(poster&&!poster.naturalWidth)poster.addEventListener('load',measure,{once:true});
     }
   }
   function time(){
     if(!started)return cursor;
     const ctx=sound?.context();
     const elapsed=audioStart!==null&&ctx?.state==='running'?(ctx.currentTime-audioStart)*1000:performance.now()-wallStart;
     return Math.min(length,Math.max(0,Math.round(base+elapsed)));
   }
   function stopAudio(){
     for(const node of voices){try{node.stop();}catch(_){}node.disconnect();}
     voices.clear();scheduled=false;
   }
   function bufferFor(row,ctx){
     if(!buffers.has(row.sha))buffers.set(row.sha,(async()=>{
       const parts=[];let offset=0,size;
       do{
         if(closed)return null;
         const part=await row.load(offset);
         if(closed)return null;
         if(part.sha256!==row.sha||(size!==undefined&&size!==part.total)||!Number.isSafeInteger(part.total)||
            part.total<=0||(part.offset!==undefined&&offset!==part.offset))throw Error('AUDIO_ASSET_CHANGED');
         size=part.total;
         const bytes=Uint8Array.from(atob(part.bytes??part.data),c=>c.charCodeAt(0));
         if(!bytes.length||offset+bytes.length>size)throw Error('AUDIO_ASSET_CHANGED');
         offset+=bytes.length;parts.push(bytes);
       }while(offset<size);
       return ctx.decodeAudioData(await new Blob(parts).arrayBuffer());
     })().catch(()=>{if(!closed&&s===state)say('此音源无法在宿主试听');return null;}));
     return buffers.get(row.sha);
   }
   const playbackEnd=()=>imwActive()&&loopEnabled?loopWindow().end:length;
   function schedule(ctx,row,buffer,position,origin){
     if(!buffer||row.end<=position)return;
     const start=Math.max(position,row.start);
     const offset=(row.source+start-row.start)/1000;
     const duration=Math.min((Math.min(row.end,playbackEnd())-start)/1000,buffer.duration-offset);
     if(duration<=0)return;
     const node=ctx.createBufferSource(),gain=ctx.createGain();node.buffer=buffer;gain.gain.value=row.volume/100;
     node.connect(gain);gain.connect(groupOutput(ctx,row.score?'score':'source'));voices.add(node);
     node.onended=()=>{voices.delete(node);node.disconnect();gain.disconnect();};
     node.start(origin+(start-position)/1000,offset,duration);
   }
   function scheduleStudio(studio,ctx,position,origin){
     const window=archivedWindow(),startMs=window?.start_ms??0,inMs=window?.in_ms??0;
     const volume=window?.volume??100;
     if(!volume)return;
     const start=Math.max(position,startMs),end=Math.min(playbackEnd(),
       window?startMs+(window.out_ms??song?.duration_ms??trackEnd(studio))-inMs:playbackEnd());
     if(start>=end)return;
     const from=(inMs+start-startMs)/1000,to=from+(end-start)/1000;
     const at=origin+(start-position)/1000;
     for(const track of studio.version.tracks){
       if(!studio.trackMonitorState(track.id).audible)continue;
       studio.queueTrackClips(track,from,to,at,(buffer,when,offset,duration)=>{
         const node=ctx.createBufferSource(),gain=ctx.createGain();
         node.buffer=buffer;gain.gain.value=volume/100*(studio.version.previewGain??1);
         node.connect(gain);gain.connect(groupOutput(ctx,'score'));voices.add(node);
         node.onended=()=>{voices.delete(node);node.disconnect();gain.disconnect();};
         node.start(when,offset,duration);
       });
     }
   }
   async function activate(){
     const ticket=++epoch,ctx=sound?.context();
     const audible=allowed&&ctx&&(sounds.length>0||!!boundStudio());
     const outputReady=audible&&ctx.state==='suspended'?ctx.resume().catch(()=>{}):null;
     const showingCursor=paintedAt!==null&&Math.abs(paintedAt-cursor)<.001&&paintedClip===frameInfo(cursor)?.c.id;
     const cold=!started&&state.doc.clips.length>0&&!showingCursor;
     if(!started&&(cold||audible))say(cold?'正在缓冲剪辑…':'正在读取音轨…');
     const ready=cold?prepareWindow(cursor,true):null;
     if(ready)void ready.then(()=>{
       if(!closed&&requested&&ticket===epoch&&!started)drawFrame();
     });
     const studio=boundStudio(),version=studio?.version;
     const needed=audible?sounds.filter(row=>row.end>cursor&&!(studio&&row.score)):[];
     if(audible&&version?.mastered){
       const selection=audioBinding(),window=archivedWindow(),at=window?.start_ms??0,from=window?.in_ms??0;
       const end=at+Math.min(window?.out_ms??trackEnd(studio),trackEnd(studio))-from;
       if(end>cursor)needed.push({sha:version.masterAudioSha,load:offset=>masterChunk(selection,offset),score:true,
         start:at,end,source:from,volume:(window?.volume??100)*(version.previewGain??1)});
     }
     // Future clips load after the opening picture and the sounds at the current position.
     const immediate=needed.filter(row=>row.start<=cursor);
     const future=needed.filter(row=>row.start>cursor).sort((a,b)=>a.start-b.start);
     const decoded=await Promise.all(immediate.map(row=>bufferFor(row,ctx)));
     if(ready)await ready;
     if(outputReady)await outputReady;
     if(closed||!requested||ticket!==epoch)return;
     if(version!==boundStudio()?.version){void activate();return;}
     const first=frameInfo(cursor);
     if(first&&frameCache.get(first.key)?.failed&&!started){
       pause();say('无法预览此片段');playState(false);updateCursor();return;
     }
     const position=time(),origin=ctx?.currentTime??0;
     if(!started){started=true;base=position;wallStart=performance.now();
       audioStart=ctx?.state==='running'?origin:null;
       if(s.message==='正在读取音轨…'||s.message==='正在缓冲剪辑…')say('');
       tick();}
     if(closed||!requested||ticket!==epoch)return;
     if(audible&&!scheduled&&ctx.state==='running'){
       scheduled=true;
       immediate.forEach((row,i)=>schedule(ctx,row,decoded[i],position,origin));
       if(studio&&!version?.mastered&&version===boundStudio()?.version)scheduleStudio(studio,ctx,position,origin);
       void loadUpcomingSound();
     }
     async function loadUpcomingSound(){
       for(const row of future){
         if(closed||!requested||ticket!==epoch||row.start>=playbackEnd())return;
         const buffer=await bufferFor(row,ctx);
         if(closed||!requested||ticket!==epoch||ctx.state!=='running')return;
         schedule(ctx,row,buffer,time(),ctx.currentTime);
       }
     }
   }
   soundLease=sound?.register(grant=>{
     if(grant===allowed)return;
     allowed=grant;
     if(!grant){epoch++;stopAudio();}
     if(requested)void activate();
   });
   function frameInfo(ms){
     const current=Math.max(0,Math.min(length-1,ms)),item=clipIndexAt(current);
     if(!item)return null;
     const c=item.clip,index=Math.floor(item.sourceMs/125),start=index-index%4;
     const next=current+Math.min(c.out_ms,(start+4)*125)-item.sourceMs;
     return {c,index,start,next,clipStart:item.startMs,sourceMs:item.sourceMs,key:c.delivery_id+':'+c.sha256+':'+start};
   }
   function loadBatch(info){
     let entry=frameCache.get(info.key);if(entry)return entry;
     entry={images:null,failed:false};frameCache.set(info.key,entry);
     const valid=()=>!closed&&frameCache.get(info.key)===entry;
     entry.ready=readPictures(target,info.c,info.start).then(async result=>{
       if(!valid())return;
       if(result?.start!==info.start||!Array.isArray(result.frames)||!result.frames.length||result.frames.length>4)
         throw Error('VIDEO_PREVIEW_UNAVAILABLE');
       entry.images=await Promise.all(result.frames.map(async jpeg=>{
         if(typeof jpeg!=='string'||jpeg.length>128000||!/^\/9j\/[A-Za-z0-9+/=]+$/.test(jpeg))throw Error('VIDEO_PREVIEW_UNAVAILABLE');
         const img=new Image();img.alt='';img.src='data:image/jpeg;base64,'+jpeg;await img.decode();return img;
       }));
     }).catch(()=>{entry.failed=true;});
     return entry;
   }
   function prepareWindow(ms,cold=false){
     const nextCut=clipIndexAt(ms)?ms:positions(state.doc.clips).find(row=>row.start>=ms)?.start;
     if(nextCut===undefined)return null;
     const first=frameInfo(nextCut);if(!first)return null;
     const key=first.c.id+':'+first.key;
     if(!cold&&windowKey===key)return null;
     windowKey=key;
     const upcoming=[],keep=new Set();let firstReady=null;
     // Load the current half-second batch first. Keep a short window ahead, across gaps.
     const through=Math.min(length,Math.max(ms+2500,nextCut+125));
     for(let at=Math.min(nextCut,length-1);at<through&&upcoming.length<(cold?2:requested?5:1);){
       const info=frameInfo(at);
       if(!info){
         const next=positions(state.doc.clips).find(row=>row.start>at)?.start;
         if(next===undefined)break;
         at=next;continue;
       }
       if(info.next<=at)break;
       if(!keep.has(info.key)){keep.add(info.key);upcoming.push({at,info});}
       at=info.next;
     }
     // Obsolete queued requests must vacate the scheduler when the user seeks.
     for(const [old,entry] of frameCache){
       if(!keep.has(old)&&frameCache.size>24)frameCache.delete(old);
     }
     for(const {at,info} of upcoming){
       const entry=loadBatch(info);
       if(!firstReady)firstReady=entry.ready;
     }
     return cold?firstReady:null;
   }
   function drawFrame(){
     if(closed||preciseMode||!state.doc.clips.length)return;
     const info=frameInfo(cursor);
     if(!info){
       if(paintedClip){compositor.clear();paintedClip='';paintedAt=null;}
       prepareWindow(cursor);return;
     }
     prepareWindow(cursor);
     const entry=frameCache.get(info.key);
     // A frame may be held inside its own cut only. A completed previous
     // request never paints the screen or advances the audio clock.
     if(paintedClip!==info.c.id){compositor.clear();paintedClip=info.c.id;}
     if(!entry?.images){
       if(entry?.failed&&failedFrame!==info.key){failedFrame=info.key;say('无法预览此片段');}
       return;
     }
     const img=entry.images[Math.min(entry.images.length-1,info.index-info.start)];
     paintImage(img,info,cursor);
   }
   function paintImage(img,info,ms){
     paintedAt=ms;paintedClip=info.c.id;
     if(!firstAspectKnown&&info.c===state.doc.clips[0]){compositor.size(img.naturalWidth,img.naturalHeight);firstAspectKnown=true;}
     const count=Math.max(1,frameBoundary(info.clipStart+info.c.out_ms-info.c.in_ms)-frameBoundary(info.clipStart));
     const clipFrame=Math.max(0,Math.min(count-1,Math.floor(ms*30/1000)-frameBoundary(info.clipStart)));
     compositor.update(img,info.c,info.sourceMs,clipFrame,count);
   }
   async function drawExact(){
     if(exactRunning)return;
     exactRunning=true;
     try{
       while(exactRequest&&!closed){
         const {ms,ticket,drag}=exactRequest;exactRequest=null;
         const item=clipIndexAt(Math.max(0,Math.min(length-.001,ms)));
         if(!item)continue;
         const c=item.clip,timeUs=Math.min(c.out_ms*1000-1,Math.round(item.sourceMs*1000));
         const valid=()=>!closed&&s===state&&!requested&&preciseMode&&frameEpoch===ticket;
         try{
           if(drag){
             const info=frameInfo(ms);if(!info)continue;
             // One in-flight batch and one replaceable target. Give an ongoing drag a picture
             // even when the pointer has reached the next batch before the decoder responds.
             const entry=loadBatch(info);await entry.ready;
             const now=frameInfo(cursor);
             if(closed||requested||!scrubbing||s!==state||now?.c.id!==info.c.id||!entry.images)continue;
             const use=now.key===info.key?now:info;
             if(frameCache.size>24){for(const old of frameCache.keys()){if(old!==info.key){frameCache.delete(old);break;}}}
             paintImage(entry.images[Math.min(entry.images.length-1,use.index-use.start)],use,use===now?cursor:ms);
             continue;
           }
           const result=await requestPicture(()=>exactFrame(target,c,timeUs),valid);
           if(!valid())continue;
           if(result?.time_us!==timeUs||result.sha256!==c.sha256||typeof result.jpeg!=='string'||
             result.jpeg.length>1048576||!result.jpeg.startsWith('/9j/'))throw Error('VIDEO_PREVIEW_UNAVAILABLE');
           const image=new Image();image.src='data:image/jpeg;base64,'+result.jpeg;await image.decode();
           if(valid())paintImage(image,{c,clipStart:item.startMs,sourceMs:item.sourceMs},ms);
         }catch(_){if(valid())say('无法读取所选视频帧');}
       }
     }finally{exactRunning=false;}
   }
   function pause(){
     if(started)cursor=time();requested=false;started=false;audioStart=null;epoch++;
     cancelAnimationFrame(raf);stopAudio();soundLease?.release();
   }
   function tick(){
     if(!requested||closed||!started)return;
     cursor=time();
     if(imwActive()&&loopEnabled){
       const {start,end}=loopWindow();
       if(end>start&&cursor>=end){
         rewinding=true;try{jump(start);}finally{rewinding=false;}
         return;
       }
     }
     if(cursor>=length){pause();cursor=length;updateCursor();drawFrame();playState(false);return;}
     const next=frameInfo(cursor),entry=next&&frameCache.get(next.key);
     if(next&&!entry?.images&&cursor-Math.max(paintedAt??next.clipStart,next.clipStart)>375){
       // Freeze the shared clock only after a visible underrun. Resume from the same point.
       started=false;audioStart=null;stopAudio();updateCursor();void activate();
       return;
     }
     if(lastPaint<0||Math.abs(cursor-lastPaint)>=30){lastPaint=cursor;updateCursor();}
     drawFrame();
     raf=requestAnimationFrame(tick);
   }
   function play(){
     if(requested||closed)return;
     preciseMode=false;scrubbing=false;exactRequest=null;requested=true;lastPaint=-1;soundLease?.claim();void activate();
   }
   function jump(ms,precise=imwActive()){
     const resume=requested;
     if(resume||started)pause();
     const token=++frameEpoch;failedFrame='';lastPaint=-1;
     cursor=Math.max(0,Math.min(length,ms));windowKey='';
     const info=frameInfo(cursor);
     if(paintedClip!==info?.c.id){
       compositor?.clear();paintedClip='';paintedAt=null;
       const poster=[...strip.querySelectorAll('button[data-clip]')].find(el=>el.dataset.clip===info?.c.id)?.querySelector('img');
       if(poster?.naturalWidth&&info)paintImage(poster,info,info.clipStart);
     }
     updateCursor();preciseMode=!!(precise&&!resume&&exactFrame&&info);scrubbing=preciseMode&&precise==='scrub';
     if(preciseMode){exactRequest={ms:cursor,ticket:token,drag:scrubbing};void drawExact();return;}
     exactRequest=null;drawFrame();const first=frameInfo(cursor);
     if(first)frameCache.get(first.key)?.ready.then(()=>{if(!closed&&token===frameEpoch&&!started)drawFrame();});
     if(resume)play();
   }
   return {play,pause,jump,updateMonitors,isPlaying:()=>requested||rewinding,started:()=>started||rewinding,refreshMix(){
     if(!requested||closed)return;
     epoch++;stopAudio();void activate();
   },close(){
     pause();closed=true;frameEpoch++;soundLease?.close();
     for(const bus of monitorOutputs.values())bus.disconnect();
     monitorOutputs.clear();buffers.clear();frameCache.clear();compositor?.close();stage.replaceChildren();
   }};
 }
 $('Return').onclick=()=>resetPreview();
 function seekTo(ms,precise=imwActive()){
   if(!s||!span())return;
   if(!preview)preview=buildPreview();
   preview.jump(ms,precise);
 }
 function seekTransport(ms){
   if(!s?.loaded)return;
   const position=Math.max(0,Math.min(span(),ms)),{start,end}=loopWindow();
   if(imwActive()&&preview?.isPlaying()&&(position>=span()||(loopEnabled&&(position<start||position>=end)))){
     preview.pause();playState(false);
   }
   seekTo(position);
 }
 $('Seek').oninput=()=>seekTransport(Number($('Seek').value));
 $('First').onclick=()=>seekTo(0);$('Last').onclick=()=>seekTo(span());
 function stepCut(direction){
   let previous=0;
   for(const {start,end} of positions(s.doc.clips)){
     for(const time of [start,end]){
       if(direction>0&&time>cursor){seekTransport(time);return;}
       if(time<cursor)previous=time;
     }
   }
   seekTransport(direction>0?span():previous);
 }
 $('Prev').onclick=()=>stepCut(-1);$('Next').onclick=()=>stepCut(1);
 $('Stop').onclick=()=>{playTicket=null;preview?.pause();playState(false);seekTo(0);};
 $('More').onclick=()=>menu($('Menu').hidden,true);
 $('Menu').addEventListener('click',event=>{if(event.target.closest('button'))menu(false,true);});
 document.addEventListener('pointerdown',event=>{if(!$('Menu').hidden&&!event.target.closest('.dc-more'))menu(false);});
 transport.addEventListener('keydown',event=>{if(event.key==='Escape'&&!$('Menu').hidden){event.preventDefault();menu(false,true);}});
 async function togglePlayback(event,allowSource=false){
   if(playTicket){playTicket=null;emitClock();return;}
   if(preview?.isPlaying()){preview.pause();playState(false);return;}
   const here=s,target=scope,ticket={imw:imwActive()};playTicket=ticket;sound?.unlock(event);emitClock();
   let stamp=null;
   try{stamp=await checkTimelineRevision(true);}catch(_){/* Local edits stay playable offline. */}
   if(playTicket!==ticket)return;
   // Keep the dock's loading state until this same request starts or exits.
   try{
   if(s!==here||scope!==target||!s||root.hidden||document.hidden||(ticket.imw&&!imwActive()))return;
   if(stamp&&stamp.timeline_version>s.version&&!dirty()&&!s.conflict)return;
   const canPlayCut=s.loaded&&!$('Play').disabled;
   if(allowSource&&(!imwActive()||!canPlayCut)&&toggleSourcePlayback?.(event,canPlayCut))return;
   if(!canPlayCut||!span())return;
   if(!preview)preview=buildPreview();
   if(cursor>=span())cursor=0;
   const {start,end}=loopWindow();
   if(imwActive()&&loopEnabled&&(cursor<start||cursor>=end))cursor=start;
   if(imwActive())transportStart=cursor;
   preview.jump(cursor,false);preview.play();playState(true);updateCursor();
   }finally{if(playTicket===ticket)playTicket=null;emitClock();}
 }
 $('Play').onclick=event=>void togglePlayback(event);
 function setLoopWindow(start,end){
   if(!Number.isFinite(start)||!Number.isFinite(end)||start<0||end>span()||end-start<250)return false;
   loopIn=Math.round(start);loopOut=Math.round(end);
   if(loopEnabled&&preview?.isPlaying()){
     if(cursor<loopIn||cursor>=loopOut)seekTo(loopIn);else preview.refreshMix();
   }
   return true;
 }
 function resetTransport(){
   playTicket=null;preview?.pause();loopEnabled=false;loopIn=0;loopOut=null;transportStart=null;
   sound?.setLevel?.(null);
 }
 let transportActive=false;
 function syncTransportMode(){
   const active=imwActive();
   if(active===transportActive)return;
   transportActive=active;
   if(active){
     const level=document.querySelector('lus-studio')?.level;
     transportLevel=Number.isFinite(level)?level:.85;
     sound?.setLevel?.(transportLevel);
   }else{resetTransport();groupMonitors.clear();}
   signalMonitor();emitTransport();
 }
 new MutationObserver(syncTransportMode).observe(document.body,{attributes:true,attributeFilter:['data-workbench','data-imw-video']});
 document.addEventListener('jiusera:imw-transport-command',event=>{
   if(!imwActive())return;
   syncTransportMode();
   const {action,inputEvent,cursorMs,level,inMs,outMs}=event.detail??{};
   if(action==='request-state'){emitTransport();return;}
   if(action==='volume'){
     if(!Number.isFinite(level))return;
     transportLevel=Math.max(0,Math.min(1,level));sound?.setLevel?.(transportLevel);
     document.querySelector('lus-studio')?.volume?.(transportLevel);
     emitTransport();return;
   }
   if(!s?.loaded||root.hidden)return;
   if(action==='play'){void togglePlayback(inputEvent);return;}
   if(action==='stop'){
     const pending=!!playTicket;playTicket=null;preview?.pause();playState(false);
     if(!pending&&transportStart!==null)seekTo(transportStart);
   }else if(action==='first')seekTransport(0);
   else if(action==='last')seekTransport(span());
   else if(action==='seek'&&Number.isFinite(cursorMs))seekTransport(Math.round(cursorMs));
   else if(action==='previous-cut'||action==='next-cut')stepCut(action==='previous-cut'?-1:1);
   else if(action==='rewind'||action==='forward')seekTransport(cursor+(action==='rewind'?-5000:5000));
   else if(action==='loop'){
     loopEnabled=!loopEnabled;
     const {start,end}=loopWindow();
     if(preview?.isPlaying()){
       if(loopEnabled&&(cursor<start||cursor>=end))seekTo(start);else preview.refreshMix();
     }
   }else if(action==='loop-range')setLoopWindow(inMs,outMs);
   else if(action==='loop-clip'&&cut()){
     const clip=cut(),start=startOf(clip.id);
     if(clip.out_ms-clip.in_ms>=250){
       loopEnabled=true;setLoopWindow(start,start+clip.out_ms-clip.in_ms);
     }
   }else return;
   emitTransport();
 });
 globalThis.OAIMWVideo={
   detachedAudio,editDetached,detachedWave,detachedChunk,retainFolded,restoreFolded,
   forgetFolded(){folded=null;detachedChanged();},
   state:clockState,syncGeometry,scoreRange:getToolMusic,audioBinding,monitorState,toggleMonitor,
   toggle(event){if(imwActive())return togglePlayback(event);},
   pause(){playTicket=null;preview?.pause();playState(false);},
   seek(seconds){if(imwActive()&&Number.isFinite(seconds))seekTo(seconds*1000);},
   locate(seconds,id){
     if(!imwActive()||!s?.loaded||!Number.isFinite(seconds))return;
     if(id&&selected!==id&&s.doc.clips.some(c=>c.id===id)){selected=id;paint();}
     seekTransport(seconds*1000);
   },
   scrubFrame(seconds){
     if(!imwActive()||!Number.isFinite(seconds)||!s?.loaded)return;
     playTicket=null;if(preview?.isPlaying()){preview.pause();playState(false);}
     seekTo(seconds*1000,'scrub');
   },
   seekFrame(seconds){
     if(!imwActive()||!Number.isFinite(seconds)||!s?.loaded)return;
     playTicket=null;preview?.pause();playState(false);seekTo(seconds*1000,true);
   },
   step(direction){if(imwActive()&&s?.loaded)stepCut(direction);},
   refreshMix(){if(imwActive()){showExportSource();preview?.updateMonitors();preview?.refreshMix();signalMonitor();}}
 };
 syncTransportMode();OAUI.onChange(localize);localize();
 return {...rough,prepareBrief,checkTimelineRevision,reloadTimeline:reload,render,clear,returnToSource(){if(s)s.previewOnOpen=false;resetPreview();},getToolState,runToolCommand,getToolClip,getToolClips,getToolMusic,selectToolSource,setToolLook,setToolCaptions,previewToolClip,duplicateToolClip};
}
'''
