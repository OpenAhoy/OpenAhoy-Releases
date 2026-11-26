"""Task-based controls beside the director monitor."""
HTML = '''
<section id="daComposer" aria-labelledby="daTitle">
 <h2 id="daTitle">AI 剪辑</h2>
 <div class="da-intents" role="group" aria-labelledby="daTitle">
  <button type="button" data-intent="edit" data-en="Edit video">改剪辑</button>
  <button type="button" data-intent="mv" data-en="Music video">歌曲做 MV</button>
  <button type="button" data-intent="score" data-en="Score video">视频配乐</button>
 </div>
 <label id="daSongField" hidden><span data-en="Song">歌曲</span><select id="daSong"></select></label>
 <p id="daSelection"></p>
 <p id="daChatHint"></p>
 <button type="button" id="daSubmit" hidden></button>
 <div id="daLocal" hidden><button type="button" id="daRough"></button><small id="daRoughHint"></small></div>
 <button type="button" id="daLoadRetry" hidden></button>
 <p id="daResult" role="status"></p>
</section>'''

STYLE = '''
#directorMonitor{grid-template-columns:minmax(0,1fr) clamp(292px,27vw,400px);grid-template-areas:"monitor assistant" "timeline timeline"}
#directorMonitor .dm-sidebar{grid-area:assistant;display:flex;flex-direction:column;align-items:stretch;gap:0;
 padding:0;min-width:0;overflow:auto;scrollbar-width:thin}
#directorMonitor .dm-sidebar>details,#directorMonitor .dm-sidebar>#daComposer,#directorMonitor .dm-sidebar>.dc-delivery,
#directorMonitor .dm-sidebar>:is(#dtPanel,#dmCutSettings){padding:14px 16px}
#directorMonitor .dm-sidebar>details{border-bottom:1px solid var(--line)}
#directorMonitor .dm-sidebar summary{cursor:pointer}
#daWork>summary{font-size:14px;font-weight:650;overflow-wrap:anywhere}
#daWork[open]>summary{margin-bottom:10px}
#daWork .dm-panel{border:0;box-shadow:none;padding:6px 0;background:transparent}
#daWork :is(.dm-candidates,#dmCandidateLabel){min-width:0}
#daWork .dm-candidates{margin-top:8px}
#daWork :is(#dmNow,#dmPlaybackState){display:none}
#daWork #dmPlaybackState:is([data-tone=attention],[data-tone=failed]){display:inline-flex}
#daTaskNotice{margin:8px 16px 0;align-self:flex-start}
#directorMonitor .dm-sidebar>#daComposer{display:grid;gap:12px}
#videoDirectorDesk #daTitle{font-size:22px;letter-spacing:-.025em;font-weight:650}
#daComposer .da-intents{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));padding:3px;gap:2px;background:var(--soft);border-radius:8px}
#videoDirectorDesk #daComposer .da-intents button{color:var(--muted);font-size:12px;font-weight:550;white-space:normal;line-height:1.25;
 padding:5px 2px;min-width:0;min-height:31px;background:transparent;border:0;box-shadow:none}
#videoDirectorDesk #daComposer .da-intents button[aria-pressed=true]{color:var(--ink);background:var(--surface);box-shadow:0 1px 3px #0002}
#daComposer #daChatHint{margin:0;font-size:13px;line-height:1.55;color:var(--ink)}
#videoDirectorDesk #daSubmit{justify-self:end;border-radius:7px;background:var(--ink);color:var(--surface);box-shadow:none;
 padding:6px 12px;font-size:12px;font-weight:600;border:0;min-height:30px}
#daComposer :is(#daSongField,#daLocal){display:grid;gap:5px}
#daComposer #daSongField select{width:100%;max-width:100%}
#daComposer :is(#daRoughHint,#daResult){font-size:12px;color:var(--muted);line-height:1.45}
#daSelection{font-size:12px;color:var(--muted);overflow-wrap:anywhere}
#daComposer :is(#daRoughHint,#daResult,#daSelection):empty{display:none}
#directorMonitor[data-dt-view]:not([data-dt-view=""]) #daComposer,
#directorMonitor:not([data-dt-view=media]):not([data-dt-view=audio]):not([data-dt-view=trim]) #dmCutSettings{display:none}
#directorMonitor[data-dt-view=trim] #dmCutSettings>:not(header,.dc-inspector){display:none}
#directorMonitor .dm-sidebar>:is(#dtPanel,#dmCutSettings){grid-area:auto;border:0;background:transparent;box-shadow:none;margin:0}
#directorMonitor .dm-sidebar>.dc-delivery{margin-top:auto;display:flex;flex-wrap:wrap;align-items:center;justify-content:space-between;
 gap:5px;border-top:1px solid var(--line);min-width:0;font-size:11px}
#directorMonitor .dm-sidebar>.dc-delivery:has(#dmCutStatus:not(:empty)) .dc-actions:has(#dmCutExport){flex-wrap:wrap}
#directorMonitor .dc-delivery #dmCutStatus:empty{display:none}
#directorMonitor .dc-delivery #dmCutReceipt{width:100%;overflow-wrap:anywhere}
#directorMonitor #daManualBack{margin:12px 16px 0;align-self:flex-start}
#directorMonitor:not([data-dt-view]),#directorMonitor[data-dt-view=""]{--da-back:none}
#directorMonitor #daManualBack{display:var(--da-back,inline-flex)}
#directorMonitor #dtPanel .dm-heading button,#directorMonitor #dtPanel #dtSave{display:none}
#wbDirectorTransport .dc-more{display:none}
@media(max-width:900px){
 #directorMonitor{grid-template-columns:minmax(0,1fr);grid-template-areas:"monitor" "assistant" "timeline"}
 #directorMonitor .dm-sidebar{max-height:none}
}
'''

SCRIPT = r"""
function OADirectorAssistant(timeline,shelf,{send,canSend},getWork){
 const $=id=>document.getElementById(id), composer=$('daComposer'),song=$('daSong');
 const buttons=[...composer.querySelectorAll('[data-intent]')], button=$('daSubmit'), result=$('daResult');
 const brief=OADirectorBrief({canSend,send,prepare:timeline.prepareBrief});
 const t=(zh,en)=>document.documentElement.lang.startsWith('en')?en:zh;
 const hints={
   edit:['直接在当前 Codex 对话里说想怎么剪，例如「把副歌这段剪快一点」。','Describe the edit in the current Codex chat, for example “Cut faster during the chorus.”'],
   mv:['选好歌曲，在当前 Codex 对话里说想要怎样的画面。','Choose a song, then describe the visuals in the current Codex chat.'],
   score:['在当前 Codex 对话里说希望用什么音乐、从哪里开始。','Tell the current Codex chat what music you want and where it should start.']
 };
 let mode='edit',owner='',epoch=0,busy=false,songList='',chosenSong='',chosenExplicitly=false,pickInitialMode=true,reading=false;
 function clearFeedback(){result.textContent='';}
 function setMode(next){pickInitialMode=false;mode=next;epoch++;busy=false;clearFeedback();sync();}
 function sync(){
   const work=getWork(),scope=work?JSON.stringify(work.scope):'';
   if(scope!==owner){
     owner=scope;mode='edit';epoch++;busy=false;songList='';chosenSong='';chosenExplicitly=false;pickInitialMode=true;reading=false;
     clearFeedback();$('daWork').open=!work;
   }
   const state=timeline.getToolState(),rough=timeline.getRoughCutState();
   const ready=!!work&&!work.work.inbox&&state.saveStatus!=='loading';
   if(ready&&pickInitialMode){
     pickInitialMode=false;
     if(rough.songId&&!rough.clipCount)mode='mv';
   }
   const hasSong=mode==='mv',songs=rough.songs;
   $('daWorkName').textContent=work?.work?.title||t('选择项目与作品','Choose a project and work');
   $('daSongField').hidden=!hasSong;$('daLocal').hidden=!hasSong;
   const sig=JSON.stringify([songs.map(s=>[s.attempt_id,s.title]),document.documentElement.lang]);
   if(sig!==songList){
     songList=sig;song.replaceChildren(new Option(t('选择一首歌','Choose a song'),''),
       ...songs.map(row=>new Option(row.title,row.attempt_id)));
   }
   if(chosenSong&&!songs.some(row=>row.attempt_id===chosenSong)){chosenSong='';chosenExplicitly=false;}
   if(!chosenExplicitly)chosenSong=rough.songId||(songs.length===1?songs[0].attempt_id:'');
   song.value=chosenSong;
   $('daTitle').textContent=t('AI 剪辑','AI editing');
   $('daManualBack').textContent=t('‹ 返回 AI 剪辑','‹ Back to AI editing');
   buttons.forEach(b=>{b.textContent=t(b.dataset.zh,b.dataset.en);b.setAttribute('aria-pressed',String(b.dataset.intent===mode));b.disabled=busy;});
   $('daSongField').firstElementChild.textContent=t('歌曲','Song');
   const clip=timeline.getToolClip();
   $('daSelection').textContent=clip&&mode!=='mv'?t('所选片段','Selected clip')+' · '+(clip.index+1)+' '+clip.title:'';
   $('daChatHint').textContent=t(...hints[mode]);
   button.hidden=mode==='edit'||!canSend();
   button.textContent=hasSong?t('在当前对话制作 MV','Make an MV in this chat'):t('在当前对话为视频配乐','Score this video in this chat');
   const blocked=busy||!ready||['conflict','invalid'].includes(state.saveStatus);
   button.disabled=button.hidden||blocked||(hasSong&&!chosenSong);
   song.disabled=busy||!ready;
   const roughButton=$('daRough');
   roughButton.textContent=rough.clipCount?t('用现有素材重新粗剪','Recut existing footage'):t('用现有素材粗剪','Make a first cut');
   roughButton.disabled=blocked||!rough.ready||!chosenSong;
   $('daRoughHint').textContent=!songs.length?t('先在 L-unify 歌单中为这首歌创建 MV 作品。','Start an MV from a song in L-unify.'):
     !rough.sourceCount?t('加入视频素材后，可以按音乐起伏安排剪点。','Add footage to place cuts along the music.'):
     rough.clipCount?t('按音乐起伏重排当前时间线，可一次撤销。','Recut the timeline to the music. Undo in one step.'):
     t('按音乐起伏安排剪点。','Place cuts along the music.');
   $('daLoadRetry').textContent=t('重新读取剪辑','Reload edit');$('daLoadRetry').hidden=!state.readFailed;
   $('daLoadRetry').disabled=reading;$('daDelivery').hidden=!ready&&!state.readFailed;
 }
 buttons.forEach(b=>{b.dataset.zh=b.textContent;b.onclick=()=>{if(!busy)setMode(b.dataset.intent);};});
 song.onchange=()=>{chosenSong=song.value;chosenExplicitly=true;clearFeedback();sync();};
 button.onclick=async()=>{
   if(button.hidden||button.disabled||!canSend())return;
   const key=++epoch;busy=true;clearFeedback();sync();
   try{
     const selection=mode==='mv'?timeline.getRoughCutState().songs.find(row=>row.attempt_id===chosenSong):null;
     const response=await brief.submit({intent:mode,song:selection});
     if(key===epoch)result.textContent=response.message;
   }catch(e){if(key===epoch)result.textContent=e.message;}
   finally{if(key===epoch){busy=false;sync();}}
 };
 $('daRough').onclick=async()=>{
   if($('daRough').disabled)return;
   const key=++epoch;busy=true;clearFeedback();result.textContent=t('正在读取音乐波形…','Reading the waveform…');sync();
   try{
     const r=await timeline.applyMusicRoughCut(chosenSong);
     if(key!==epoch)return;
     const seconds=(r.durationMs/1000).toFixed(1),partial=r.requestedDurationMs>r.durationMs;
     const summary=r.unchanged?t('当前时间线已是这一版。','This cut is already on the timeline.'):
       t('已粗剪 '+r.clipCount+' 段，共 '+seconds+' 秒。',r.clipCount+' clips, '+seconds+' seconds.');
     result.textContent=summary+(partial?t('已用完可用画面。',' Available footage used.'):'')+
       (r.accentCuts===0&&r.clipCount>1?t('未检测到明显起伏，已均匀分段。',' No clear accents. Cuts are evenly spaced.'):'');
   }catch(e){if(key===epoch)result.textContent=e.message;}
   finally{if(key===epoch){busy=false;sync();}}
 };
 $('daLoadRetry').onclick=async()=>{
   const key=owner;reading=true;sync();
   try{await timeline.reloadTimeline();}finally{if(owner===key){reading=false;sync();}}
 };
 $('daManualBack').onclick=()=>{shelf.close();$('dmCodexDetails').open=true;buttons.find(b=>b.dataset.intent===mode)?.focus({preventScroll:true});};
 document.addEventListener('jiusera:cut-tools-change',sync);
 new MutationObserver(sync).observe(document.documentElement,{attributes:true,attributeFilter:['lang']});
 return {sync};
}
"""
