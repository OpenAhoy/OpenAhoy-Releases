"""Project audio and soundtrack controls in the existing native app."""
HTML = '''
<section id="audioWorkspace" aria-labelledby="audioPageTitle" hidden>
<header class="oa-video-header">
<h1 id="audioPageTitle" tabindex="-1">音频生成</h1>
<div class="oa-video-header-actions"><label>项目<select id="audioProject"></select></label><button id="audioReload" type="button">刷新</button></div>
</header>
<section class="oa-audio-connection"><div><strong>Suno</strong><span class="help">由 Codex 使用官方 MCP 连接</span></div>
<div class="oa-provider-actions"><button id="audioSuno" type="button">Suno 官方连接说明</button><button id="audioCheck" type="button">检查 Suno 连接</button><button id="audioCreate" class="primary" type="button">创作歌曲</button></div></section>
<textarea id="audioCopy" aria-label="复制 Codex 指令" readonly hidden></textarea>
<div class="oa-audio-workspace">
<section class="oa-video-library" aria-labelledby="audioLibraryTitle"><h2 id="audioLibraryTitle">项目音频与配乐</h2>
<div class="oa-video-library-items"><ul id="audioList"></ul><p id="audioEmpty" class="help"></p></div></section>
<section class="oa-audio-preview panel">
<strong id="audioTitle"></strong>
<audio id="audioPlayer" controls preload="none" hidden></audio>
<video id="audioMixPlayer" controls playsinline preload="none" hidden></video>
<div class="oa-provider-actions" id="audioVersions" hidden><button id="audioOriginal" type="button">原片</button>
<button id="audioMixed" type="button">配乐版</button></div>
<p id="audioNotice" class="help" role="status" aria-live="polite"></p>
<button id="audioDownload" type="button" disabled>下载原文件</button></section>
</div>
</section>
'''

STYLE = '''
#audioWorkspace[hidden],#audioWorkspace [hidden]{display:none!important}
#audioWorkspace{flex:1;min-height:0;min-width:0;display:grid;gap:8px;grid-template-rows:auto auto auto minmax(0,1fr)}
#openAudioWorkspace[aria-current=page]{background:var(--management-selected,var(--line));font-weight:650}
.oa-audio-connection{display:flex;justify-content:space-between;align-items:center;gap:6px;flex-wrap:wrap;padding:5px 10px;border-radius:9px;background:var(--oa-fill,var(--line))}
.oa-audio-connection span{margin-inline-start:8px}
.oa-audio-workspace{display:grid;min-height:0;grid-template-columns:clamp(135px,28%,220px) minmax(0,1fr);gap:8px}
.oa-audio-workspace .oa-video-library{min-height:0}
.oa-audio-workspace #audioList button{width:100%;text-align:start;overflow-wrap:anywhere}
.oa-audio-preview{min-width:0;min-height:0;margin:0;display:grid;gap:6px;align-content:start;overflow:auto}
.oa-audio-preview audio,.oa-audio-preview video{width:100%;max-height:36dvh}
#audioCopy{min-height:66px}
@media(max-width:440px){.oa-audio-workspace{grid-template-columns:minmax(0,1fr);grid-template-rows:105px minmax(0,1fr)}}
'''

SCRIPT = r'''
const OAAudioWorkspace=(call,send,openLink,canSend)=>{
 const $=id=>document.getElementById(id);
 const list=$('audioList'),project=$('audioProject'),download=$('audioDownload'),notice=$('audioNotice');
 const audio=$('audioPlayer'),movie=$('audioMixPlayer'),copy=$('audioCopy');
 let active=false,refreshEpoch=0,selection=0,row=null,sending=false;
 const invoke=(action,args={})=>call('wce.ui.video.workspace',{action,...args});
 function clear(){
   row=null;selection++;download.disabled=true;copy.hidden=true;$('audioVersions').hidden=true;
   for(const player of [audio,movie]){player.pause();player.hidden=true;player.removeAttribute('src');}
   OAUI.raw($('audioTitle'),'');OAUI.set(notice,'');OAUI.set(download,'下载原文件');
 }
 function fields(asset){return {project_id:project.value,attempt_id:asset.attempt_id};}
 async function preview(asset){
   clear();row=asset;const id=selection;const player=asset.kind==='song'?audio:movie;
   OAUI.raw($('audioTitle'),asset.title);
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
   const source={project_id:project.value,generation_attempt_id:asset.video_attempt_id};
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
 async function refresh(initialProject){
   const epoch=++refreshEpoch;clear();list.replaceChildren();
   try{
     const result=await invoke('audio_history');
     if(!active||epoch!==refreshEpoch)return;
     const previous=initialProject||project.value;
     project.replaceChildren(...result.projects.map(item=>new Option(item.name,item.id)));
     if(result.projects.some(item=>item.id===previous))project.value=previous;
     $('audioCreate').disabled=!project.value;
     if(!project.value){OAUI.set($('audioEmpty'),'先在项目与 Skills 中登记项目。');return;}
     const history=await invoke('audio_history',{project_id:project.value});
     if(!active||epoch!==refreshEpoch)return;
     OAUI.set($('audioEmpty'),history.assets.length?'':'这个项目还没有音频。');
     for(const asset of history.assets){
       const li=document.createElement('li'),button=document.createElement('button');
       button.type='button';OAUI.raw(button,asset.title);button.onclick=()=>void preview(asset);li.append(button);list.append(li);
     }
   }catch(_){if(active&&epoch===refreshEpoch)OAUI.set($('audioEmpty'),'暂时无法读取项目音频。');}
 }
 async function request(text,target=notice){
   if(sending)return;
   copy.hidden=true;copy.value='';
   if(!canSend()){copy.value=text;copy.hidden=false;copy.focus();copy.select();return;}
   sending=true;
   try{await send(text);OAUI.set(target,'已发到当前 Codex 聊天。');}
   catch(_){OAUI.set(target,'无法确认聊天收到请求。');}
   finally{sending=false;}
 }
 $('audioCreate').onclick=()=>{
   if(!project.value)return;
   void request('帮我构思一首 Suno 歌曲。先询问主题或沿当前聊天的 brief；保存歌曲方案和独立的标题、风格、歌词、人声字段。只有本轮已明确授权生成时才调用官方 audio-create。项目 '+project.value+'。');
 };
 $('audioCheck').onclick=()=>void request('请用当前聊天的 Suno 官方 MCP 只读核对 account-me 和 account-usage。若工具缺失请提供官方连接步骤，别生成、上传或升级。');
 $('audioSuno').onclick=()=>openLink('https://help.suno.com/en/articles/14551425').catch(()=>OAUI.set(notice,'宿主未能打开官方页面。'));
 $('audioReload').onclick=()=>void refresh();
 project.onchange=()=>void refresh();
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
 return {open(projectId){active=true;void refresh(projectId);},close(){active=false;refreshEpoch++;clear();}};
};
'''
