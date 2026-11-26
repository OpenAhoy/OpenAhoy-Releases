"""Director desk in the native Jiusera media workspace."""
from .video_director_canvas_ui import HTML as CANVAS_HTML
from .character_library_ui import PAGE as CHARACTER_PAGE
from .asset_catalog_ui import HTML as ASSET_CATALOG
from .media_monitor_ui import HTML as ASSET_MEDIA
from .video_director_monitor_ui import HTML as MONITOR_HTML
from .article_work_ui import STYLE as ARTICLE_STYLE, SCRIPT as ARTICLE_SCRIPT

HTML = '''
<section id="videoDirectorDesk" aria-labelledby="directorTitle" hidden>
 <header class="dd-toolbar">
  <h1 id="directorTitle" tabindex="-1">视频剪辑</h1>
  <div class="dd-actions">
   <button id="directorSound" type="button" aria-label="预览声音" aria-pressed="false">声音关</button>
   <button id="directorToolBack" type="button" hidden>返回</button>
   <button id="directorAssetBack" type="button" hidden>返回资产库</button>
   <details id="directorMore" class="dd-more"><summary>
      <svg class="oa-icon" viewBox="0 0 24 24" aria-hidden="true"><path d="M3 6h5m4 0h9M3 12h11m4 0h3M3 18h2m4 0h12"/><circle cx="10" cy="6" r="2"/><circle cx="16" cy="12" r="2"/><circle cx="7" cy="18" r="2"/></svg>
      <span id="directorMoreLabel">作品工具</span></summary>
    <div class="dd-more-menu">
     <button type="button" id="directorChatWorkMenu">在 Codex 开始创作</button>
     <button type="button" id="directorRefreshMenu">刷新</button>
     <button type="button" id="directorNewWork">手动新建作品</button>
     <button type="button" id="directorRecoverWork">找回聊天作品</button>
     <button type="button" id="directorStopFollowing" hidden>停止等待聊天结果</button>
     <button type="button" id="directorProjectSettings">登记项目</button>
     <button type="button" id="directorCardsLink">提示词库</button>
    </div>
   </details>
  </div>
 </header>
 <div class="dd-workbar" id="directorWorkbar">
  <div class="dd-projects">
   <label>项目 <select id="directorProject"></select></label>
   <label>作品 <select id="directorWork"></select></label>
   <button type="button" id="directorChatWork" class="primary">在 Codex 开始创作</button>
  </div>
  <div class="dd-actions">
   <button type="button" id="directorWorkSettings">作品约定</button>
   <button type="button" id="directorRefresh">刷新</button>
  </div>
 </div>
 <p id="directorWorkHint" class="dd-work-hint" hidden></p>
 ''' + MONITOR_HTML + '''
 <section id="articleWork" aria-label="图文作品" hidden></section>
 <div id="directorBoard" class="dd-board" hidden>
  ''' + CANVAS_HTML + '''
  <div id="wbCanvasDetails" aria-label="镜头详情">
  <aside class="dd-panel dd-scenes" aria-label="场次">
   <div class="dd-heading"><h2>场次</h2><button id="directorNewScene" type="button">新建场次</button></div>
   <label class="dd-scene-select">当前场 <select id="directorSceneSelect"></select></label>
   <div id="directorSceneList"></div>
  </aside>
  <section class="dd-view" aria-label="取景器">
   <div class="dd-heading"><h2 id="directorSceneTitle"></h2><div class="dd-actions">
    <button id="directorPrevious" type="button">上一场</button><button id="directorNext" type="button">下一场</button>
   </div></div>
   <button id="directorNewShot" type="button">新建镜头</button>
   <details class="dd-shot-shelf"><summary>本场镜头</summary><div id="directorShots" aria-label="本场镜头条"></div></details>
  </section>
  <aside class="dd-panel dd-inspector" aria-labelledby="directorShotTitle">
   <header><div id="directorShotStatus"></div><h2 id="directorShotTitle"></h2><p id="directorShotPurpose"></p></header>
   <figure id="directorStage"><div id="directorImageFrame"></div><figcaption id="directorCaption"></figcaption></figure>
   <nav id="directorTabs" aria-label="当前镜头">
    <button type="button" data-tab="text">文字</button><button type="button" data-tab="images">图片</button>
    <button type="button" data-tab="versions">版本</button><button type="button" data-tab="generation">生成配置</button>
    <button type="button" data-tab="whitebox">白模</button><button type="button" data-tab="stage" hidden>场景</button>
   </nav>
   <div id="directorInspector"></div>
   <details id="directorHandoff"><summary>交给 Codex 修改</summary>
    <label>要改什么<textarea id="directorInstruction" rows="2" placeholder="例如：把这一镜改成从门外侧跟，落幅保留人物与窗。"></textarea></label>
    <div class="dd-actions"><button type="button" id="directorSendText">交给 Codex 改文字</button>
      <button type="button" id="directorSendImage">交给 Codex 改图片</button><button type="button" id="directorCopyContext">复制上下文</button></div>
   </details>
  </aside>
  </div>
 </div>
 <section id="directorCardPage" class="dd-card-page" aria-label="提示词库" hidden>
  <div class="dd-toolbar">
   <input type="search" id="directorCardQuery" aria-label="搜索提示词卡" placeholder="搜索镜头、焦距、构图或用途">
   <label>类型 <select id="directorCardCategory"><option value="">全部</option><option value="movement">运镜</option><option value="lens">焦距</option><option value="sequence">组合</option><option value="style">风格</option></select></label>
   <label>模型 <select id="directorCardModel"><option value="">全部</option><option value="ark">方舟</option><option value="minimax">MiniMax</option></select></label>
   <label>主体 <select id="directorCardSubjects"><option value="">全部</option><option value="1">单人或单主体</option><option value="2">双人</option></select></label>
  </div>
  <div class="dd-card-grid"><div id="directorCardList"></div><article id="directorCardDetail" class="dd-panel"></article></div>
 </section>
 ''' + ASSET_CATALOG + CHARACTER_PAGE + ASSET_MEDIA + '''
 <footer class="dd-footer">
  <p id="directorStatus" role="status" aria-live="polite"></p>
  <textarea id="directorCopy" rows="3" aria-label="可复制内容" readonly hidden></textarea>
 </footer>
 <dialog id="directorDialog" aria-labelledby="directorDialogTitle">
  <div id="directorDialogForm"><h2 id="directorDialogTitle"></h2><div id="directorDialogBody"></div>
   <div class="dd-actions"><button id="directorDialogSave" type="button" class="primary">保存</button><button id="directorCancel" type="button">取消</button></div>
  </div>
 </dialog>
</section>
'''

STYLE = ARTICLE_STYLE + '''
#videoDirectorDesk[hidden],#videoDirectorDesk [hidden]{display:none!important}
#videoDirectorDesk{display:flex;min-height:0;min-width:0;flex:1;flex-direction:column;gap:10px;overflow:auto;
 color:var(--ink);font-size:13px;scrollbar-gutter:stable}
#videoDirectorDesk :is(h1,h2,h3,p,figure){margin:0}
#videoDirectorDesk h2{font-size:15px;font-weight:650}
#videoDirectorDesk h3{font-size:13px}
#videoDirectorDesk :is(input,textarea,select){width:100%;min-width:0;margin:0}
.dd-more{position:relative}
.dd-more summary{display:flex;align-items:center;gap:6px;cursor:pointer;min-height:32px;padding:3px 8px;
 border:1px solid var(--line);border-radius:7px;background:var(--surface);list-style:none}
.dd-more summary::after{content:'⌄';color:var(--muted)}
.dd-more summary::-webkit-details-marker{display:none}
.dd-more-menu{position:absolute;z-index:5;inset-inline-end:0;top:calc(100% + 4px);display:grid;min-width:max-content;
 gap:4px;padding:5px;border-radius:8px;border:1px solid var(--line);background:var(--surface);box-shadow:var(--raised)}
.dd-canvas-edit .dd-more-menu{inset-inline:0 auto}
#directorAssetKinds{display:flex;align-items:center;gap:5px;flex-wrap:wrap}
#directorSound[aria-pressed=true],#directorAssetKinds button[aria-pressed=true]{background:var(--oa-selection,var(--tint));border-color:var(--line)}
#videoDirectorDesk #mediaMonitor{flex:1 0 auto}
#videoDirectorDesk #monitorSearch{width:auto}
@media(max-width:690px){
 #videoDirectorDesk .mm-columns{min-height:320px}
 #videoDirectorDesk #monitorList,#videoDirectorDesk #monitorDetail{max-height:none;height:auto}
}
#videoDirectorDesk :is(input,select,textarea,button){font-size:12px}
#videoDirectorDesk :is(button,select,input){min-height:30px}
#videoDirectorDesk textarea{resize:vertical}
#videoDirectorDesk label{display:grid;gap:3px;margin:0;color:var(--muted);font-size:12px}
#videoDirectorDesk label:has(input[type=checkbox]){display:flex;align-items:center;gap:6px}
#videoDirectorDesk input[type=checkbox]{inline-size:auto;min-height:0}
.dd-toolbar,.dd-workbar,.dd-heading,.dd-projects,.dd-actions,#directorViews,#directorTabs{display:flex;align-items:center;flex-wrap:wrap;gap:6px}
.dd-toolbar,.dd-workbar,.dd-heading{justify-content:space-between}
.dd-toolbar,.dd-workbar{flex:none}
.dd-projects label,.dd-card-page .dd-toolbar label{display:flex!important;align-items:center}
.dd-projects select{width:clamp(100px,12vw,220px)!important}
#directorViews button[aria-pressed=true],#directorTabs button[aria-pressed=true],#directorSceneList button[aria-pressed=true],.dd-shot[aria-pressed=true],#directorCardList button[aria-pressed=true]{
 background:var(--oa-selection,var(--tint));color:var(--accent);border-color:var(--accent)}
.dd-board{display:grid;grid-template-columns:clamp(150px,14%,212px) minmax(0,1fr) clamp(285px,25%,360px);gap:10px;flex:1;min-height:0;align-items:start}
.dd-panel{min-width:0;min-height:0;padding:10px;border:1px solid var(--line);border-radius:12px;background:var(--surface)}
.dd-scenes,.dd-inspector,.dd-card-page,#directorCardDetail{overflow:auto;overscroll-behavior:contain}
.dd-scenes,.dd-inspector{max-height:100%}
.dd-scene-select{display:none!important}
#directorSceneList{display:grid;gap:4px;margin-top:8px}
#directorSceneList button{display:grid;grid-template-columns:minmax(0,1fr) auto;gap:3px 7px;text-align:start;width:100%;padding:6px 8px}
#directorSceneList button strong{overflow-wrap:anywhere}
#directorSceneList button small{color:var(--muted);grid-column:1/-1}
.dd-view{display:flex;flex-direction:column;gap:8px;min-width:0;min-height:0}
#directorStage{flex:0 1 clamp(240px,47vh,490px);min-height:200px;display:grid;grid-template-rows:minmax(0,1fr) auto;
 overflow:hidden;border:1px solid var(--line);border-radius:10px;background:var(--soft,var(--surface))}
#directorImageFrame{display:grid;place-items:center;min-height:0;color:var(--muted);padding:0;overflow:hidden}
#directorImageFrame img{width:100%;height:100%;min-height:0;object-fit:contain}
#directorCaption{color:var(--muted);font-size:11px;padding:4px 8px;background:var(--surface)}
#directorShots{display:grid;grid-auto-columns:clamp(100px,24%,158px);grid-auto-flow:column;gap:5px;overflow:auto;
 padding:2px 2px 6px;align-content:start;flex:none}
#directorShots .dd-shot{display:grid;grid-template-rows:58px auto auto;text-align:start;min-width:0;padding:3px;overflow:hidden}
.dd-shot span,.dd-shot strong{overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.dd-shot img{width:100%;height:100%;object-fit:cover;border-radius:4px}
.dd-shot-cover{background:var(--soft,var(--surface));display:grid;place-items:center;min-height:0;overflow:hidden}
.dd-shot-cover img{min-width:0;min-height:0;display:block}
.dd-shot small,#directorShotStatus,#directorShotPurpose{color:var(--muted);font-size:11px;overflow-wrap:anywhere}
.dd-inspector header{display:grid;gap:4px}
#directorTabs{margin-top:8px;padding-block-end:5px;border-bottom:1px solid var(--line)}
#directorTabs button{padding-inline:5px!important;min-height:27px!important}
#directorInspector{display:grid;gap:7px;padding-block:8px}
.dd-inspector details{border-top:1px solid var(--line);padding-top:7px}
.dd-inspector :is(summary,button){cursor:pointer}
.dd-form,.dd-pairs,.dd-version-list,.dd-asset-list{display:grid;gap:6px;min-width:0}
.dd-pairs{grid-template-columns:repeat(2,minmax(0,1fr))}
.dd-summary{display:grid;gap:7px}
.dd-summary dt{color:var(--muted);font-size:11px;margin-bottom:2px}
.dd-summary dd{margin:0;white-space:pre-wrap;overflow-wrap:anywhere}
.dd-version,.dd-asset-row{display:grid;grid-template-columns:minmax(0,1fr) auto;gap:5px;padding:5px 0;border-bottom:1px solid var(--line)}
.dd-version>div,.dd-asset-row>div{min-width:0;overflow-wrap:anywhere}
.dd-form label:has(textarea){min-width:0}
.dd-work-hint{flex:none;margin:0;color:var(--muted);font-size:12px;overflow-wrap:anywhere}
.dd-footer{display:grid;gap:4px;flex:none}
.dd-footer p{color:var(--muted);min-height:1em;font-size:12px}
.dd-footer p:empty{display:none}
#directorStatus[data-error=true]{color:var(--danger,var(--accent))}
#directorDialog{max-width:min(690px,calc(100% - 20px));width:100%;max-height:85vh}
#directorDialogForm{display:grid;gap:8px}
#directorDialogBody{display:grid;gap:7px}
.dd-card-page{display:flex;flex-direction:column;gap:8px;flex:1;min-height:0}
.dd-card-page .dd-toolbar{justify-content:start}
#directorCardQuery{width:min(280px,100%)!important}
.dd-card-grid{display:grid;grid-template-columns:minmax(225px,32%) minmax(0,1fr);gap:10px;min-height:0;flex:1}
#directorCardList{overflow:auto;display:grid;align-content:start;gap:4px}
#directorCardList button{text-align:start}
#directorCardDetail{display:grid;align-content:start;gap:8px}
#directorCardDetail p{white-space:pre-wrap;overflow-wrap:anywhere}
#directorInspector .oa-frame-player .oa-frame-screen{max-height:190px}
@media(max-width:1100px){
 .dd-board{grid-template-columns:minmax(0,1fr) minmax(265px,34%);grid-template-rows:auto minmax(0,1fr)}
 .dd-scenes{grid-column:1/-1;display:flex;gap:10px;align-items:center;overflow:visible;padding:3px 7px}
 .dd-scenes .dd-heading{justify-content:start}
 .dd-scene-select{display:flex!important;align-items:center;white-space:nowrap}
 #directorSceneList{display:none}
}
@media(max-width:700px){
 #videoDirectorDesk{overflow:auto}
 .dd-board{display:flex;flex-direction:column;align-items:stretch;flex:none}
 #directorStage{flex:0 0 clamp(165px,36vh,330px);min-height:0}
 .dd-inspector{overflow:visible}
 .dd-card-grid{display:grid;grid-template-columns:1fr}
 #directorCardList{max-height:180px}
}
'''

SCRIPT = ARTICLE_SCRIPT + r'''
function OADirector(tool, send, canSend, navigation){
 const $=id=>document.getElementById(id);
 const root=$('videoDirectorDesk'), project=$('directorProject'), workSelect=$('directorWork');
 const board=$('directorBoard'), inspector=$('directorInspector'), stage=$('directorImageFrame');
 const read=(action,args={})=>tool('video.director.read',{action,...args});
 const pendingWrites=new Map();
 const intentKey=(action,args)=>JSON.stringify([action,args]);
 async function edit(action,args,awaitReadback=false){
   const key=intentKey(action,args);
   if(!pendingWrites.has(key))pendingWrites.set(key,randomID());
   try{
     const result=await tool('video.director.edit',{action,operation_id:pendingWrites.get(key),...args});
     if(!awaitReadback)pendingWrites.delete(key);
     return result;
   }catch(problem){
     if(!/^HOST_/.test(problem?.message||'')&&!(awaitReadback&&problem?.message==='DIRECTOR_SAVE_NOT_VERIFIED'))
       pendingWrites.delete(key);
     throw problem;
   }
 }
 const media=(action,args)=>tool('wce.ui.video.director.media',{action,...args});
 const txt=OAUI.format;
 const language={
  purpose:'这镜要做什么',subjects:'人物与道具',opening:'起幅',action:'动作与节奏',ending:'落幅',
  transition:'前后镜衔接',composition:'构图',camera:'机位与运动',lens:'焦距观感',focus:'焦点',
  lighting:'灯光',color:'色彩',sound:'声音与台词',review:'回看检查',notes:'修订说明',
  brief:'创意概要',platform:'发布平台',audience:'受众',tone:'叙事语气',references:'角色、场景和道具参考',
  style:'视觉风格',caption_safe_area:'字幕安全区',whitebox:'白模',prompt:'完整生成提示词'
 };
 const modeLabels={text:'文生视频',first:'首帧',last:'尾帧',frames:'首尾帧',reference:'多图参考',edit:'修改画面',extend:'延长镜头'};
 const providers={ark:'火山方舟',ark_global:'方舟国际站 · BytePlus ModelArk',cn:'MiniMax 中国站',global:'MiniMax 国际站',tokenhex:'Token Hex',sand:'Sand AI',vidmuse:'VidMuse'};
 const roles={composition:'构图预览',first:'首帧',last:'尾帧',subject:'主体参考',environment:'环境参考',reference:'其他参考'};
 const cardKinds={movement:'运镜',lens:'焦距',sequence:'组合',style:'风格'};
 const codes={
  DIRECTOR_IMAGE_IMPORT_INVALID:'请选择可读取的 PNG 或 JPEG 图片。',
  DIRECTOR_CANVAS_CHANGED:'画布在另一个窗口已更新，请刷新后再继续。',
  DIRECTOR_ASSET_CHANGED:'原素材的身份或文件已经变化。',
  DIRECTOR_STALE_REVISION:'这个版本已变更，请刷新并查看最新修订。',
  DIRECTOR_ASSET_OUTSIDE_PROJECT:'请选择当前项目内的相对路径。',
  DIRECTOR_ASSET_WRONG_PROJECT:'素材不属于当前项目。',
  DIRECTOR_ASSET_CHANGED:'素材内容已变化，请重新核对文件和摘要。',
  VIDEO_FRAME_OUTSIDE_PROJECT:'请选择当前项目内的相对路径。',
  VIDEO_FRAME_CHANGED:'图片内容已变化，请重新选图。',
  VIDEO_FRAME_INVALID:'图片需要是可读的 PNG 或 JPEG，且符合本机视频输入规格。',
  INVALID_LOCAL_FILE:'无法读取项目文件，请核对实际路径。',
  DIRECTOR_CONFIGURATION_REQUIRED:'先为当前镜头保存生成配置。',
  DIRECTOR_PROMPT_REQUIRED:'先填写完整生成提示词。',
  DIRECTOR_PROMPT_TOO_LONG:'生成提示词超出了当前工具可提交的长度。',
  DIRECTOR_REFERENCE_IMAGES_REQUIRED:'请添加该模型支持数量内的参考图片。',
  DIRECTOR_INPUT_FRAMES_REQUIRED:'缺少所选模式要求的首帧或尾帧。',
  VIDEO_MODE_UNSUPPORTED:'模型不支持所选模式。',
  VIDEO_OUTPUT_UNSUPPORTED:'所选模型不支持这个分辨率或音频选项。',
  VIDEO_OUTPUT_INVALID:'所选模型不支持当前画幅或分辨率组合。',
  VIDEO_DURATION_INVALID:'当前时长不符合所选模型与分辨率。',
  VIDEO_MODE_PARAMETERS_INVALID:'当前模式与所填参数不匹配。',
  VIDEO_REFERENCE_SOURCE_UNAVAILABLE:'请为编辑或续写选择本项目有效的原成片。',
  VIDEO_REFERENCE_DURATION_INVALID:'原成片时长不符合所选模式。',
  DIRECTOR_WHITEBOX_FILE_REQUIRED:'请关联项目内的白模 MP4。',
  DIRECTOR_WHITEBOX_MP4_REQUIRED:'白模预览需要 MP4。',
  DIRECTOR_TIME_RANGE_INVALID:'结束时间必须大于或等于开始时间。',
  HOST_TIMEOUT:'宿主响应超时，请刷新后核对是否保存。',
  DIRECTOR_PROJECT_NOT_REGISTERED:'这个项目尚未登记。',
  DIRECTOR_PROJECT_UNAVAILABLE:'原项目目录不可用。',
  DIRECTOR_PROJECT_CHANGED:'项目已切换，请核对当前选择。',
  DIRECTOR_WORK_NOT_FOUND:'找不到这部作品，请核对原请求或项目。',
  PROJECT_OPERATION_CONFLICT:'这次请求已关联其他项目或作品，请核对聊天中的原请求。',
 };
 let mode='',tab='text',data=null,context=null,sceneID=null,projects=[],modelData=null,cardData=null,cardID='';
 let engineDraft=null,engineDirty=false,workspaceTimer=null,workspaceBusy=false;
 const polled=new Map(),workspaceRows=new Map(),preferredWorks=new Map(),preferredShots=new Map();
 const workKey=scope=>scope.project_id+':'+scope.work_id;
 const engineModes={...modeLabels,subject:'主体参考',workflow:'多图多音频工作流'};
 const engineChannel={...providers,relay:'AutoDL'};
 const legacyWorkflow='minimax_h3_zm_nono';
 const workflowLabels={reference_images:'参考图片公开 HTTPS 链接',reference_audio:'参考音频公开 HTTPS 链接',
   first_frame:'首帧公开 HTTPS 链接',last_frame:'尾帧公开 HTTPS 链接',reference_video:'参考视频公开 HTTPS 链接',
   duration:'时长（秒）',audio_duration:'音频时长（秒）',resolution:'分辨率',seed:'随机种子',
   quality_mode:'画质模式',style_preset:'风格预设',video_subject_to_replace:'要替换的视频主体'};
 const exactSeedHint='这个种子超出面板的精确整数范围。请在 Codex 聊天通过 MCP 设置原始整数。';
 const engineName=engine=>engine.model+' · '+txt(engineChannel[engine.provider]||engine.provider||'渠道未记录');
 let watch=null,watchTimer=null,player=null,reading=0,visual=0,writing=false,dialogWrite=null;
 let explicitProject='',selection=0,projectLoad=0,chatRequest=null,readingRequest=false,ticking=false;
 const pid=()=>project.value;
 const present=()=>data?.work;
 const currentScene=()=>present()?.scenes.find(row=>row.id===sceneID);
 const currentShot=()=>currentScene()?.shots.find(row=>row.id===context?.shot_id);
 const exact=(ctx=context)=>ctx&&({project_id:ctx.project_id,work_id:ctx.work_id,scene_id:ctx.scene_id,
                                shot_id:ctx.shot_id,revision_id:ctx.revision.id});
 const workScope=()=>({project_id:pid(),work_id:present().id});
 function randomID(){return [...crypto.getRandomValues(new Uint8Array(16))].map(x=>x.toString(16).padStart(2,'0')).join('');}
 function say(message,error=false,raw=false){
   const status=$('directorStatus');status.dataset.error=String(error);
   if(raw)OAUI.raw(status,message);else OAUI.set(status,message);
 }
 function error(problem){say(codes[problem?.message]||'操作未完成。请刷新或核对当前镜头。',true);}
 function node(tag,cls){const el=document.createElement(tag);if(cls)el.className=cls;return el;}
 function label(tag,message,cls){const el=node(tag,cls);OAUI.set(el,message);return el;}
 function raw(tag,value,cls){const el=node(tag,cls);OAUI.raw(el,value??'');return el;}
 function button(message,click,cls){const el=label('button',message,cls);el.type='button';el.onclick=click;return el;}
 function pair(parent,caption,input){
   const el=node('label');OAUI.attr(input,'aria-label',caption);el.append(OAUI.label(caption),input);parent.append(el);return input;
 }
 function select(parent,caption,options,value){
   const el=node('select');optionsFor(el,options,value);return pair(parent,caption,el);
 }
 function optionsFor(el,options,value){
   el.replaceChildren(...options.map(([key,text,translate=true])=>{
     const option=new Option('',key);
     if(translate)OAUI.set(option,text);else OAUI.raw(option,text);
     return option;
   }));
   if(options.some(([key])=>key===value))el.value=value;
 }
 function input(parent,caption,value='',type='text',limits={}){
   const el=node('input');el.type=type;el.value=value;
   for(const [key,setting] of Object.entries(limits))el[key]=setting;
   return pair(parent,caption,el);
 }
 function textarea(parent,caption,value='',rows=2){
   const el=node('textarea');el.rows=rows;el.value=value||'';return pair(parent,caption,el);
 }
 function clearPreview(){if(player){player.close();player=null;}stage.replaceChildren();}
 function stopWatch(){clearTimeout(watchTimer);watchTimer=null;watch=null;}
 function scopeKey(ctx=context){return ctx&&JSON.stringify(exact(ctx));}
 function visible(key){return mode==='desk'&&scopeKey()===key;}
 function clock(ms){
   if(!Number.isSafeInteger(ms))return '';
   const s=Math.floor(ms/1000),pad=n=>String(n).padStart(2,'0');
   return (s>=3600?Math.floor(s/3600)+':':'')+pad(Math.floor(s/60)%60)+':'+pad(s%60);
 }
 function range(row){return row.start_ms===row.end_ms?'':clock(row.start_ms)+'–'+clock(row.end_ms);}
 function seconds(ms){return (ms||0)/1000;}
 function applyMS(el){return Math.round(Number(el.value||0)*1000);}
 function preferred(scene){
   const chosen=scene?.shots.find(shot=>shot.adopted_revision&&shot.cover_revision)||
                scene?.shots.find(shot=>shot.cover_revision)||scene?.shots[0];
   return chosen&&{scene_id:scene.id,shot_id:chosen.id,revision_id:chosen.adopted_revision||chosen.head_revision};
 }
 async function write(action,args,after,message='已保存并读回。'){
   if(writing)return false;
   writing=true;
   try{
     const result=await edit(action,args,true);
     if(result.state!=='SAVED'||result.project_id!==args.project_id)throw Error('DIRECTOR_SAVE_NOT_VERIFIED');
     if(mode&&pid()===args.project_id&&after)await after(result);
     pendingWrites.delete(intentKey(action,args));
     if(mode&&pid()===args.project_id)say(message);
     return true;
   }catch(problem){if(mode&&pid()===args.project_id)error(problem);return false;}
   finally{writing=false;}
 }
 let readingWork=0,guideRead=0,guideWorkChoice=null;
 function readChosenWork(work,overview){
   guideWorkChoice={project:pid(),work};
   return readWork({work,overview});
 }
 async function readWork(options={}){
   const token=reading+1;guideRead=0;readingWork++;
   navigation.guideChanged?.();
   try{
     const loaded=await loadWork(options);
     if(loaded&&reading===token)guideRead=token;
     return loaded;
   }finally{readingWork--;navigation.guideChanged?.();}
 }
 function guideContext(){
   const work=present();
   if(!mode||!guideRead||guideRead!==reading||data?.project_id!==pid()||!work||work.inbox)return null;
   if(chatRequest?.selection===selection)return null;
   // A refresh or late save can still read the previous work after a failed switch.
   if(guideWorkChoice&&guideWorkChoice.project===pid()&&guideWorkChoice.work!==work.id)return null;
   const shot=context?.project_id===pid()&&context?.work_id===work.id?context.shot_id:'';
   const stored=shot&&context.revision.images.find(
     row=>row.asset_version&&row.file.project_id===pid()&&/^[a-f0-9]{64}$/.test(row.file.sha256));
   return {project:pid(),work:work.id,title:work.title,scenes:work.scenes.length,
     shots:work.scenes.reduce((sum,scene)=>sum+scene.shots.length,0),shot,asset:stored?.asset_version||''};
 }
 async function loadWork({work,focus,scene,keep=false,overview}){
   const token=++reading, id=pid();
   if(!id){data=null;context=null;sceneID=null;render();return false;}
   const requested=work||(keep?present()?.id:preferredWorks.get(id));
   const result=overview||await read('overview',{project_id:id,...(requested?{work_id:requested}:{})});
   if(token!==reading||!mode||pid()!==id)return false;
   if(result.project_id!==id)throw Error('DIRECTOR_PROJECT_CHANGED');
   if(requested&&(result.work?.id!==requested||!result.works.some(row=>row.id===requested)))throw Error('DIRECTOR_WORK_NOT_FOUND');
   const active=result.work, scope=active&&{project_id:id,work_id:active.id};
   const picked=focus||(!scene&&scope&&preferredShots.get(workKey(scope)))||active?.selection;
   const sceneRow=active?.scenes.find(row=>row.id===(scene||picked?.scene_id))||active?.scenes[0];
   const target=picked?.shot_id&&picked.scene_id===sceneRow?.id?picked:preferred(sceneRow);
   let view=null;
   if(active&&target)view=await read('context',{project_id:id,work_id:active.id,...target});
   if(token!==reading||!mode||pid()!==id)return false;
   if(view&&(view.project_id!==id||view.work_id!==active.id||view.scene_id!==target.scene_id||
             view.shot_id!==target.shot_id||view.revision.id!==target.revision_id))
      throw Error('DIRECTOR_REVISION_NOT_FOUND');
   data=result;sceneID=sceneRow?.id||null;context=view;
   if(scope)preferredWorks.set(id,scope.work_id);
   if(active&&!active.inbox&&mainView()){
     try{localStorage.setItem('jiusera.workbench.last-work',JSON.stringify({project:id,work:active.id}));}catch(_){}
   }
   if(scope&&target)preferredShots.set(workKey(scope),target);
   render();if(mode==='cards'&&cardData)renderCards();
   if(!overview&&(mode==='monitor'||mode==='desk'))await syncWorkspace();
   return true;
 }
 async function selectShot(scene,shot,revision){
   if(!scene||!shot||!revision||!present())return;
   stopWatch();engineDirty=false;engineDraft=null;
   const fields={...workScope(),scene_id:scene,shot_id:shot,revision_id:revision};
   await write('select_revision',fields,()=>readWork({keep:true,focus:{
      scene_id:scene,shot_id:shot,revision_id:revision}}),'');
 }
 async function selectScene(id){
   if(!id||sceneID===id)return;
   const row=present()?.scenes.find(item=>item.id===id),picked=preferred(row);
   if(picked){await selectShot(id,picked.shot_id,picked.revision_id);return;}
   stopWatch();
   await write('select_scene',{...workScope(),scene_id:id},()=>readWork({keep:true,scene:id}),'');
 }
 function render(){
   if(mode!=='desk'&&mode!=='monitor')return;
   const editing=mode==='desk',imw=mode==='monitor'&&document.body.dataset.imwVideo==='true';
   const work=imw&&present()?.kind==='article'?null:present(),article=work?.kind==='article';
   if(mode==='monitor')navigation.imwWork?.(pid(),work);
   document.body.toggleAttribute('data-workbench-has-work',!!work&&!work.inbox);
   const workbar=$('directorWorkbar'),context=$('dmWorkContext');
   if(!editing&&!article){
     if(workbar.parentElement!==context)context.append(workbar);
   }else if(workbar.parentElement===context){
     $('directorWorkHint').before(workbar);
   }
   workbar.hidden=false;
   $('directorWorkSettings').hidden=!editing||article;
   board.hidden=!editing||article;
   $('directorMonitor').hidden=editing||article;
   $('directorSound').hidden=article;
   document.body.toggleAttribute('data-workbench-article',article);
   const works=(data?.works||[]).filter(row=>!imw||row.kind!=='article');
   optionsFor(workSelect,[[ '',works.length?'选择作品':'暂无作品'],
     ...works.map(row=>[row.id,row.kind==='article'?[row.title,
       row.account_label&&row.account_label+' · '+row.account_hint].filter(Boolean).join(' / '):row.title,!!row.inbox])],work?.id||'');
   workSelect.disabled=!works.length;
   $('directorNewWork').disabled=!pid();
   const pending=chatRequest&&chatRequest.selection===selection;
   $('directorStopFollowing').hidden=!pending;
   $('directorChatWork').disabled=!!pending||!canSend();
   $('directorChatWorkMenu').disabled=$('directorChatWork').disabled;
   OAUI.set($('directorChatWork'),pending?'等待聊天中的作品':'在 Codex 开始创作');
   const hint=$('directorWorkHint');
   hint.hidden=!!work&&!pending;
   OAUI.set(hint,pending?'已保留原请求，作品就绪后会显示在这里。':
     canSend()?'从当前聊天开始，也可在画布工具中手动新建。':'当前宿主无法发送聊天请求，可在画布工具中手动新建。');
   const scope=work&&workScope(),cached=scope&&workspaceRows.get(workKey(scope));
   if(article){
     review.clear();canvas.suspend();
     void articleStage.show(scope,mode);
     return;
   }
   articleStage.hide();
   if(editing){
     canvas.render(scope?workKey(scope):'',work,context?.shot_id,context?.revision||null);
     if(cached)canvas.setDeliveries(workKey(scope),cached.cards,cached.version);
   }else review.render({work,scope,context,cards:cached?.cards||[],workVersion:data?.version});
   $('directorCanvasEngine').disabled=!context;
   const editable=!!work&&!work.inbox;
   $('directorWorkSettings').disabled=!editable;
   for(const id of ['directorCanvasNote','directorCanvasImage','directorNewScene'])$(id).disabled=!editable;
   if(!editing)return;
   const scene=currentScene();
   const start=$('wbCanvasStart');
   const action=editable?(scene?'新建镜头':'新建场次'):canSend()?'在 Codex 开始创作':pid()?'手动新建作品':'登记项目';
   OAUI.attr(start,'aria-label',action);OAUI.attr(start,'title',action);
   start.disabled=!editable&&!!pending;
   start.onclick=()=>{
     const id=editable?(scene?'directorNewShot':'directorNewScene'):
       canSend()?'directorChatWork':pid()?'directorNewWork':'directorProjectSettings';
     $(id).click();
   };
   const scenes=work?.scenes||[];
   const at=scenes.indexOf(scene);
   $('directorPrevious').disabled=at<=0;$('directorNext').disabled=at<0||at>=scenes.length-1;
   $('directorNewShot').disabled=!editable||!scene;
   OAUI.raw($('directorSceneTitle'),scene?scene.title:txt('还没有场次'));
   optionsFor($('directorSceneSelect'),scenes.map(row=>[row.id,row.title,false]),sceneID);
   $('directorSceneSelect').disabled=!scenes.length;
   const sceneList=$('directorSceneList');sceneList.replaceChildren();
   for(const row of scenes){
     const pick=button('',()=>selectScene(row.id));pick.setAttribute('aria-pressed',String(sceneID===row.id));
     pick.append(raw('strong',row.title),raw('span',row.shots.filter(s=>s.adopted_revision).length+'/'+row.shots.length),
        raw('small',range(row)));
     sceneList.append(pick);
   }
   renderShots();
   renderInspector();
   renderImage();
 }
 function attachImage(target,value,thumbnail=false){
   if(value.mime_type!=='image/jpeg'||typeof value.data!=='string'||!value.data.startsWith('/9j/'))
      throw Error('DIRECTOR_PREVIEW_UNAVAILABLE');
   const img=node('img');img.alt='';img.src='data:image/jpeg;base64,'+value.data;
   if(thumbnail)img.loading='lazy';
   target.replaceChildren(img);
 }
 function renderShots(){
   const list=$('directorShots');list.replaceChildren();
   const scene=currentScene();
   if(!scene)return;
   for(const shot of scene.shots){
     const chosen=shot.adopted_revision||shot.head_revision,rev=shot.revisions.find(row=>row.id===chosen);
     const pick=button('',()=>selectShot(scene.id,shot.id,chosen),'dd-shot');
     pick.setAttribute('aria-pressed',String(context?.shot_id===shot.id));pick.dataset.shotId=shot.id;
     const cover=label('div',shot.cover_revision?'载入图片…':'文字分镜','dd-shot-cover');
     pick.append(cover,raw('strong',rev.title),raw('small',[range(rev),shot.adopted_revision?txt('已采用'):''].filter(Boolean).join(' · ')));
     list.append(pick);
     if(shot.cover_revision)void media('image',{...workScope(),scene_id:scene.id,shot_id:shot.id,
       revision_id:shot.cover_revision,thumbnail:true}).then(value=>{
          if(pick.isConnected)attachImage(cover,value,true);
        }).catch(()=>{if(pick.isConnected)OAUI.set(cover,'图片不可用');});
   }
 }
 function renderImage(index){
   clearPreview();
   const token=++visual, snap=exact();
   if(!snap){
     if(present()&&!present().inbox)stage.append(label('p',currentScene()?'创建本场第一个镜头':'先新建场次'));
     OAUI.set($('directorCaption'),'');return;
   }
   const revision=context.revision;
   OAUI.raw($('directorCaption'),[txt('图片分镜'),'v'+revision.number,range(revision)].filter(Boolean).join(' · '));
   if(!revision.images.length){
     stage.append(label('p','这镜还没有图片'));return;
   }
   stage.append(label('p','正在读取图片…'));
   void media('image',{...snap,...(index===undefined?{}:{index})}).then(value=>{
     if(token===visual&&mode==='desk')attachImage(stage,value);
   }).catch(()=>{if(token===visual&&mode==='desk')stage.replaceChildren(label('p','当前图片不可用'));});
 }
 function revise(fields,message='已保存新修订并读回。'){
   const ctx=context;
   if(!ctx||ctx.revision.id!==ctx.head_revision){error(Error('DIRECTOR_STALE_REVISION'));return;}
   const {revision_id,...target}=exact(ctx);
   return write('revise',{...target,base_revision:revision_id,fields,origin:'panel'},
     result=>readWork({work:ctx.work_id,focus:{scene_id:ctx.scene_id,shot_id:ctx.shot_id,revision_id:result.revision_id}}),message);
 }
 function renderInspector(){
   releaseVoicePreview();
   if(player){player.close();player=null;}
   inspector.replaceChildren();
   const tabs=$('directorTabs'),headline=$('directorShotTitle'),status=$('directorShotStatus');
   tabs.hidden=!context;$('directorHandoff').hidden=!context;
   if(!context){
     OAUI.set(headline,'当前镜头');
     OAUI.set(status,'');OAUI.set($('directorShotPurpose'),'');
     inspector.append(label('p','添加镜头后可在这里编辑和采用修订。'));return;
   }
   const rev=context.revision,fresh=rev.id===context.head_revision;
   OAUI.raw(headline,rev.title);
   OAUI.set(status,'v{0} · {1}',rev.number,OAUI.message(rev.id===context.adopted_revision?'已采用':fresh?'最新修订':'历史修订'));
   OAUI.raw($('directorShotPurpose'),rev.purpose);
   for(const item of tabs.querySelectorAll('button'))item.setAttribute('aria-pressed',String(item.dataset.tab===tab));
   $('directorSendText').disabled=!fresh;$('directorSendImage').disabled=!fresh;
   if(tab==='text')renderText(rev,fresh);
   if(tab==='images')renderImages(rev,fresh);
   if(tab==='versions')renderVersions(rev);
   if(tab==='generation')void renderConfig(rev,fresh);
   tabs.querySelector('[data-tab=stage]').hidden=!rev.stage;
   if(tab==='whitebox')renderWhitebox(rev,fresh);
   if(tab==='stage'){
     if(rev.stage)void renderStage(rev.stage);
     else inspector.append(label('p','这个修订还没有锁定场景。'));
   }
 }
 async function renderStage(stage){
   const scope=exact(),key=scopeKey(),pane=node('section','dd-asset-list');
   pane.dataset.pinnedStage='';pane.dataset.sceneVersion=stage.scene.version_id;pane.dataset.objectVersion=stage.object.version_id;
   const picture=node('div','dd-asset-list'),status=label('p','正在读取锁定的场景预览…');
   const row=(title,detail)=>{const element=node('div');element.append(label('strong',title),raw('p',detail));return element;};
   const dims=(data)=>data.map(n=>String(n/1000)).join(', ');
   const paths=node('div','dd-actions');
   paths.append(button('复制演播室原件路径',()=>copy(context.project_root+'/'+stage.scene.file.path)),
                button('复制话筒原件路径',()=>copy(context.project_root+'/'+stage.object.file.path)));
   pane.append(picture,status,paths,row('场景原件',stage.scene.title+' · '+stage.scene.version_id),
      row('物品原件',stage.object.title+' · '+stage.object.version_id),
      row('相机位置（米）',dims(stage.camera.location_mm)),row('相机旋转（度）',dims(stage.camera.rotation_mdeg)),
      row('焦距（毫米）',String(stage.camera.lens_um/1000)),
      row('物品位置（米）',dims(stage.placement.location_mm)),row('物品旋转（度）',dims(stage.placement.rotation_mdeg)));
   inspector.append(pane);
   try{
     const preview=await media('stage_preview',scope);
     if(!pane.isConnected||tab!=='stage'||scopeKey()!==key)return;
     if(preview.sha256!==stage.preview.sha256||preview.mime_type!=='image/jpeg'||!preview.data.startsWith('/9j/'))
       throw Error('DIRECTOR_STAGE_FILE_CHANGED');
     const source='data:image/jpeg;base64,'+preview.data,small=node('img');
     OAUI.attr(small,'alt','锁定场景预览');small.style.width='100%';small.style.borderRadius='8px';
     small.src=source;picture.append(small);status.hidden=true;
     picture.append(button('查看场景大图',()=>{
       const dialog=$('directorCanvasPreview'),large=node('img');
       OAUI.raw($('directorCanvasPreviewTitle'),stage.scene.title+' · '+stage.scene.version_id);
       $('directorCanvasNoteEdit').hidden=true;
       const container=$('directorCanvasPreviewBody');
       OAUI.attr(large,'alt','锁定场景预览');large.style.maxWidth='100%';large.src=source;
       container.replaceChildren(large);
       if(!dialog.open)dialog.showModal();
     }));
   }catch(_){
     if(pane.isConnected)OAUI.set(status,'场景预览暂不可用，请核对锁定的原件与依赖。');
   }
 }
 function renderText(rev,fresh){
   const fields=['purpose','opening','action','ending','transition','subjects','composition','camera','lens',
                 'focus','lighting','color','sound','review','notes'];
   const summary=node('dl','dd-summary');
   for(const key of fields)if(rev[key]){
     const row=node('div');row.append(label('dt',language[key]),raw('dd',rev[key]));summary.append(row);
   }
   if(!summary.childElementCount)summary.append(label('dd','为这一镜补上起幅、动作和落幅。'));
   inspector.append(summary);
   if(!fresh)return;
   inspector.append(button('编辑文字分镜',()=>{
     const pane=node('div','dd-form'),time=node('div','dd-pairs');
     const title=input(pane,'镜头名称',rev.title,'text',{required:true});
     const start=input(time,'开始秒数',seconds(rev.start_ms),'number',{min:0,step:'0.001'});
     const end=input(time,'结束秒数',seconds(rev.end_ms),'number',{min:0,step:'0.001'});
     pane.append(time);
     const ratio=select(pane,'画幅',['16:9','9:16','1:1','4:3','3:4','21:9','adaptive'].map(k=>[k,k]),rev.ratio);
     const inputs={};for(const key of fields) inputs[key]=textarea(pane,language[key],rev[key]);
     pane.append(button('保存为新修订',()=>revise({title:title.value,start_ms:applyMS(start),end_ms:applyMS(end),
       ratio:ratio.value,...Object.fromEntries(Object.entries(inputs).map(([k,input])=>[k,input.value]))}),'primary'));
     inspector.replaceChildren(pane);
   }));
 }
 function fileInputs(pane,pathValue='',shaValue='',accept='image/png,image/jpeg',canImport=false){
   const file=input(pane,'选择本机文件','','file',{accept});
   const path=input(pane,'项目内相对路径',pathValue,'text',{placeholder:'例如 storyboard/shot-01.png'});
   const sha=input(pane,'SHA-256',shaValue);
   const read=()=>({project_id:pid(),path:path.value.trim(),sha256:sha.value.trim().toLowerCase()});
   file.onchange=async()=>{
     if(!file.files?.[0]||canImport)return;
     const picked=file.files[0];
     try{
       const result=await crypto.subtle.digest('SHA-256',await picked.arrayBuffer());
       sha.value=[...new Uint8Array(result)].map(x=>x.toString(16).padStart(2,'0')).join('');
       if(!path.value||!path.value.includes('/'))path.value=picked.name;
       say('已读取文件摘要。请核对项目内相对路径。');
     }catch(problem){error(problem);}
   };
   async function prepare(){
     const picked=canImport&&file.files?.[0];
     if(!picked)return read();
     const scope=workScope(),code='DIRECTOR_IMAGE_IMPORT_INVALID';
     if(!picked.size||picked.size>=30000000)throw Error(code);
     const bytes=new Uint8Array(await picked.arrayBuffer());
     const sum=await crypto.subtle.digest('SHA-256',bytes);
     const digest=[...new Uint8Array(sum)].map(x=>x.toString(16).padStart(2,'0')).join('');
     for(let offset=0;offset<bytes.length;offset+=262144){
       if(pid()!==scope.project_id||present()?.id!==scope.work_id)throw Error('DIRECTOR_PROJECT_CHANGED');
       const slice=bytes.subarray(offset,offset+262144),strings=[];
       for(let i=0;i<slice.length;i+=8192)strings.push(String.fromCharCode(...slice.subarray(i,i+8192)));
       const result=await media('import_image_chunk',{...scope,sha256:digest,total:bytes.length,
                              offset,data:btoa(strings.join(''))});
       if(result.state==='IMPORTED'&&result.file?.project_id===scope.project_id&&result.file.sha256===digest){
         file.value='';return result.file;
       }
       if(result.state!=='RECEIVING'||result.received<offset+slice.length)throw Error(code);
     }
     throw Error(code);
   }
   return {path,sha,read,prepare,filename:()=>file.files?.[0]?.name};
 }
 let imageDraft=null,voiceURL=null,voiceElement=null;
 function releaseVoicePreview(){
   if(voiceElement){voiceElement.pause();voiceElement.removeAttribute('src');voiceElement=null;}
   if(voiceURL){URL.revokeObjectURL(voiceURL);voiceURL=null;}
 }
 function renderImages(rev,fresh){
   const initial=scopeKey(),draft=fresh&&imageDraft?.scope===initial?imageDraft:null;
   const list=node('div','dd-asset-list'),images=draft?draft.images:structuredClone(rev.images);
   let voice=draft?draft.voice:structuredClone(rev.voice??null);
   const pendingLooks=draft?.pendingLooks||new Map();
   const keep=()=>{imageDraft={scope:initial,images,voice,pendingLooks};};
   function draw(){
     list.replaceChildren();
     if(!images.length)list.append(label('p','这个修订还没有图片。'));
     images.forEach((row,index)=>{
       const part=node('div','dd-asset-row'),left=node('div'),right=node('div','dd-actions');
       left.append(raw('strong',row.file.path),label('p',roles[row.role]));
       if(row.asset_version){
         const version=node('p');OAUI.set(version,'形象版本：{0}',row.asset_version);left.append(version);
         if(row.character_reference){
           const pinned=row.character_reference;
           left.append(raw('p',pinned.character_id+' · '+(pinned.form_id==='normal'?'常态':pinned.form_id)));
           if(pinned.crop)left.append(raw('p',`裁切 ${pinned.crop.x}, ${pinned.crop.y} · ${pinned.crop.width} × ${pinned.crop.height}`));
         }
       }
       if(fresh){
         const choice=select(left,'图片用途',Object.entries(roles),row.role);
         choice.onchange=()=>{row.role=choice.value;keep();};
         if(index>0)right.append(button('上移',()=>{[images[index-1],images[index]]=[images[index],images[index-1]];keep();draw();}));
         if(index+1<images.length)right.append(button('下移',()=>{[images[index+1],images[index]]=[images[index],images[index+1]];keep();draw();}));
         right.append(button('从此版移除',()=>{images.splice(index,1);keep();draw();}));
       }
       const stored=rev.images.findIndex(item=>item.file.path===row.file.path&&item.file.sha256===row.file.sha256);
       if(stored>=0)right.prepend(button('预览',()=>renderImage(stored)));
       part.append(left,right);list.append(part);
     });
   }
   const voiceSection=node('section','dd-asset-list');
   voiceSection.dataset.shotVoice='';
   function drawVoice(){
     releaseVoicePreview();
     const heading=label('strong','镜头声音');
     voiceSection.replaceChildren(heading);
     if(voice){
       const pinned=voice.character_reference;
       const name=raw('p',pinned?`${pinned.character_id} · ${pinned.form_id} · ${voice.asset_version}`:voice.asset_version);
       name.dataset.voiceVersion=voice.asset_version;
       const row=voice,feedback=label('p',''),actions=node('div','dd-actions');
       const listen=button('试听锁定声音',async()=>{
         listen.disabled=true;
         const alive=()=>listen.isConnected&&voice===row&&scopeKey()===initial&&tab==='images';
         try{
           const blob=await navigation.readCharacterOriginal({use:'voice',id:row.asset_version,file:row.file},alive);
           if(!blob||!alive())return;
           releaseVoicePreview();voiceURL=URL.createObjectURL(blob);
           voiceElement=node('audio');voiceElement.controls=true;voiceElement.preload='metadata';
           OAUI.attr(voiceElement,'aria-label','锁定声音播放器');voiceElement.src=voiceURL;
           voiceSection.append(voiceElement);
           voiceElement.play().catch(()=>{});
         }catch(problem){if(alive()){OAUI.set(feedback,'声音原件暂不可播放。');listen.disabled=false;}}
       });
       actions.append(listen);
       if(fresh)actions.append(button('移除此声音',()=>{voice=null;keep();drawVoice();}));
       voiceSection.append(name,actions,feedback);
     }
     if(fresh){
       const pickVoice=button(voice?'更换镜头声音':'从形象库选择声音',()=>navigation.chooseCharacter(pid(),asset=>{
         if(scopeKey()!==initial||tab!=='images')throw Error('DIRECTOR_STALE_REVISION');
         voice={file:structuredClone(asset.file),asset_version:asset.id};keep();drawVoice();
       },pickVoice,context.work_id,'audio'));
       voiceSection.append(pickVoice);
     }
   }
   draw();drawVoice();inspector.append(list,voiceSection);
   if(!fresh)return;
   const add=node('details');add.append(label('summary','关联项目图片'));
   const form=node('div','dd-form'),role=select(form,'图片用途',Object.entries(roles),'composition');
   const file=fileInputs(form,'','','image/png,image/jpeg',true);
   const addButton=button('加入图片列表',async()=>{
     const initial=scopeKey();addButton.disabled=true;
     try{
       const spec=await file.prepare();
       if(scopeKey()!==initial)return;
       if(!spec.path||!(/^[a-f0-9]{64}$/).test(spec.sha256)){say('请填写项目相对路径和完整 SHA-256。',true);return;}
       images.push({role:role.value,file:spec});keep();file.path.value='';file.sha.value='';draw();add.open=false;
     }catch(problem){error(problem);}
     finally{addButton.disabled=false;}
   });
   form.append(addButton);
   const pick=button('从形象库选择',()=>navigation.chooseCharacter(pid(),asset=>{
     if(scopeKey()!==initial||tab!=='images')throw Error('DIRECTOR_STALE_REVISION');
     const assets=Array.isArray(asset)?asset:[asset];
     for(const item of assets){
       const file=structuredClone(item.file),group=item.appearance?.group;
       if(group&&(['hair','wardrobe','accessories'].includes(group)||group==='base'&&assets.length>1)){
         const character=item.character.id,form=item.form?.id||'normal';
         const match=images.findIndex(row=>{
           const pinned=row.character_reference||pendingLooks.get(row.asset_version);
           return pinned?.appearance?.group===group&&pinned.character_id===character&&pinned.form_id===form;
         });
         if(match>=0){
           pendingLooks.delete(images[match].asset_version);
           images.splice(match,1);
         }
         pendingLooks.set(item.id,{character_id:character,form_id:form,appearance:item.appearance});
       }
       if(!images.some(row=>row.asset_version===item.id&&row.file.sha256===file.sha256))
         images.push({role:'reference',file,asset_version:item.id});
     }
     keep();draw();
   },pick,context.work_id,'image'));
   add.append(form);inspector.append(pick,add,button('保存图片修订',async()=>{
     const fields={images};
     if(JSON.stringify(voice)!==JSON.stringify(rev.voice??null))fields.voice=voice??{mode:'none'};
     const saved=await revise(fields);
     if(saved&&imageDraft?.scope===initial)imageDraft=null;
   },'primary'));
 }
 function renderVersions(rev){
   const shot=currentShot(),list=node('div','dd-version-list');
   if(!shot)return;
   for(const version of [...shot.revisions].reverse()){
     const row=node('div','dd-version'),body=node('div'),actions=node('div','dd-actions');
     body.append(raw('strong','v'+version.number+' · '+version.title));
     body.append(raw('p',[txt(version.origin==='codex'?'Codex 修订':'页面修订'),
       version.id===shot.adopted_revision?txt('已采用'):'',version.id===shot.head_revision?txt('最新修订'):''].filter(Boolean).join(' · ')));
     if(version.notes)body.append(raw('p',version.notes));
     const show=button('查看',()=>selectShot(sceneID,shot.id,version.id));show.disabled=rev.id===version.id;
     actions.append(show);
     if(version.id!==shot.adopted_revision)actions.append(button('采用此版',()=>{
       const {revision_id,...target}=exact();
       const args={...target,revision_id:version.id,base_revision:shot.head_revision};
       if(shot.adopted_revision)args.expected_adopted=shot.adopted_revision;
       void write('adopt',args,()=>readWork({keep:true}),'已采用该修订。');
     }));
     row.append(body,actions);list.append(row);
   }
   inspector.append(list);
   if(rev.result)inspector.append(button('预览已关联成片',()=>previewVideo('result')));
   if(rev.id===context.head_revision)inspector.append(button('关联已有成片',()=>pickResult()));
 }
 async function projectVideos(id){
   const value=await tool('wce.ui.video.workspace',{action:'history',project_id:id});
   return value.versions.filter(v=>v.state==='ASSET_READY'&&v.asset?.sha256);
 }
 async function pickResult(){
   const key=scopeKey();
   try{
     const rows=await projectVideos(pid());
     if(!visible(key)||tab!=='versions')return;
     if(!rows.length){say('当前项目没有可关联的成片。');return;}
     const panel=node('div','dd-form');
     const pick=select(panel,'本项目成片',rows.map(v=>[v.generation_attempt_id,v.name||v.generation_attempt_id,false]),context.revision.result?.attempt_id);
     panel.append(button('保存成片关联',()=>{
       const row=rows.find(v=>v.generation_attempt_id===pick.value);
       return revise({result:{project_id:pid(),attempt_id:row.generation_attempt_id,sha256:row.asset.sha256}});
     },'primary'));
     inspector.append(panel);
   }catch(problem){if(visible(key))error(problem);}
 }
 async function previewVideo(kind){
   const target=exact(),key=scopeKey(),currentTab=tab;
   try{
     const facts=await media(kind,target);
     if(!visible(key)||currentTab!==tab)return;
     if(player)player.close();
     const holder=node('div','oa-frame-player');inspector.append(holder);
     player=OAFramePlayer(holder,start=>media(kind+'_frames',{...target,start}),facts.seconds,{
       failed:()=>say('项目视频暂时无法预览。',true)
     });
     player.first();
   }catch(problem){if(visible(key))error(problem);}
 }
 function renderWhitebox(rev,fresh){
   const current=rev.whitebox||{mode:'none'},form=node('div','dd-form');
   const type=select(form,'预演方式',[['none','不使用'],['plan','规划白模'],['import','导入项目白模']],current.mode);
   const camera=textarea(form,'机位路径',current.camera_path),subject=textarea(form,'人物动线',current.subject_path),
         points=textarea(form,'关键点与空间锚点',current.key_points);
   const source=node('div','dd-form'),file=fileInputs(source,current.file?.path,current.file?.sha256,'video/mp4');
   form.append(source);
   const update=()=>{source.hidden=type.value!=='import';};type.onchange=update;update();
   for(const control of form.querySelectorAll('input,textarea,select'))control.disabled=!fresh;
   if(fresh)form.append(button('保存白模计划',()=>revise({whitebox:{mode:type.value,camera_path:camera.value,
      subject_path:subject.value,key_points:points.value,...(type.value==='import'?{file:file.read()}:{})}}),'primary'));
   if(current.file)form.append(button('预览当前白模',()=>previewVideo('whitebox')));
   inspector.append(form,label('p','白模渲染尚未接入。已关联的项目白模可在这里预演。'));
 }
 async function engineData(refresh=false){
   if(!modelData||refresh)modelData=await read('models',refresh?{refresh_tokenhex:true}:{});
   return modelData;
 }
 function vidmuseCatalog(catalog,snapshot){
   const profiles={};
   const byMode=new Map();
   for(const entry of snapshot.models||[]){
     const group=byMode.get(entry.mode)||[];group.push(entry);byMode.set(entry.mode,group);
   }
   for(const [mode,entries] of byMode){
     if(entries.length!==1)continue;
     const entry=entries[0];
     profiles[mode]={resolutions:Object.fromEntries(entry.resolution.map(size=>[size,entry.duration])),
       ratios:entry.ratio,local_roles:[],reference_count:entry.reference_count,audio:entry.audio.includes(true),
       vidmuseAudio:entry.audio};
   }
   const modes=Object.keys(profiles);
   catalog.models.vidmuse=modes.length?[{id:'magi-2',name:'MAGI-2',modes,profiles,visibility:'VISIBLE'}]:[];
   catalog.vidmuse=snapshot;
 }
 async function pickEngine(){
   if(!context)return;
   if(context.revision.id!==context.head_revision){
     await selectShot(context.scene_id,context.shot_id,context.head_revision);
   }
   if(!context||context.revision.id!==context.head_revision)return;
   const target=scopeKey(),picker=node('div','dd-form dd-engine-picker');
   const search=input(picker,'查找型号或渠道','','search'),status=label('p',''),cards=node('div','dd-engine-grid');
   const dialogNode=$('directorDialog'),save=$('directorDialogSave');
   const refresh=button('核对 Token Hex 可见型号',async()=>{
      refresh.disabled=true;
      try{await engineData(true);if(dialogNode.open&&scopeKey()===target)paint();}
      catch(problem){if(scopeKey()===target)error(problem);}
      finally{refresh.disabled=false;}
   });
   const vidmuseRefresh=button('读取 VidMuse 的 MAGI-2',async()=>{
     vidmuseRefresh.disabled=true;
     try{
       vidmuseCatalog(modelData,await navigation.vidmuse.get(true));
       if(dialogNode.open&&scopeKey()===target)paint();
     }finally{vidmuseRefresh.disabled=false;}
   });
   picker.append(refresh,vidmuseRefresh,status,cards);
   function paint(){
     if(!modelData)return;
     const needle=search.value.trim().toLowerCase();
     cards.replaceChildren();
     for(const [provider,list] of Object.entries(modelData.models)){
       for(const model of list){
         const name=model.name||model.id,channel=txt(engineChannel[provider]);
         if(!(`${name} ${model.id} ${channel}`.toLowerCase().includes(needle)))continue;
         const tile=button('',()=>{
           if(scopeKey()!==target)return;
           engineDraft={key:target,provider,model:model.id};engineDirty=true;
           dialogNode.close();tab='generation';renderInspector();
         },'dd-engine-option');
         tile.dataset.engine=provider+':'+model.id;
         tile.disabled=model.visibility==='NOT_VISIBLE';
         tile.append(raw('strong',name),raw('small',channel),raw('span',model.modes.map(m=>txt(engineModes[m])).join(' · ')));
         if(provider==='tokenhex')tile.append(label('small',model.visibility==='VISIBLE'?'账号可见':
            model.visibility==='NOT_VISIBLE'?'当前账号不可见':'账号可见性待核'));
         cards.append(tile);
       }
     }
     if(!cards.childElementCount)cards.append(label('p','未找到匹配型号'));
     OAUI.set(status,{NOT_CHECKED:'',MODELS_VISIBLE:'已读到 Token Hex 账号目录',
       NOT_CONFIGURED:'Token Hex 连接未配置',NO_SUPPORTED_MODELS:'此账号无本插件支持的型号',
       EMPTY_CATALOG:'账号目录为空',AUTH_REQUIRED:'Token Hex 连接需要授权',
       CHECK_UNAVAILABLE:'Token Hex 目录暂不可读'}[modelData.tokenhex_catalog?.state]||
       (modelData.vidmuse?navigation.vidmuse.text(modelData.vidmuse.state):''));
   }
   try{
     await engineData();
     if(scopeKey()!==target||mode!=='desk')return;
     search.oninput=paint;paint();
     dialog('选择视频引擎',picker,null);
     save.hidden=true;
     dialogNode.addEventListener('close',()=>{save.hidden=false;},{once:true});
     search.focus();
   }catch(problem){if(scopeKey()===target)error(problem);}
 }
 async function renderConfig(rev,fresh){
   const key=scopeKey();inspector.append(label('p','正在读取模型与连接…'));
   try{
     const catalog=await engineData();
     if(!visible(key)||tab!=='generation')return;
     const config=rev.configuration||{},draft=engineDraft?.key===key?engineDraft:null,
       pane=node('div','dd-form'),cols=node('div','dd-pairs');
     const provider=select(cols,'供应商',Object.entries(engineChannel),draft?.provider||config.provider);
     const pickedModel=select(cols,'模型',[],config.model),kind=select(cols,'模式',[],config.mode);
     const workflow=select(cols,'AutoDL 工作流',[],config.workflow_id||'');
     workflow.dataset.engineField='workflow_id';
     const duration=select(cols,'时长（秒）',[],config.duration);
     const resolution=select(cols,'分辨率',[],config.resolution);
     const ratio=select(cols,'画幅',[],config.ratio);
     const audio=input(cols,'生成音频','','checkbox');audio.checked=!!config.audio;
     for(const [field,control] of Object.entries({provider,model:pickedModel,mode:kind,duration,resolution,ratio,audio}))
       control.dataset.engineField=field;
     const sourceArea=node('div','dd-form');
     const source=select(sourceArea,'本项目原成片',[],config.source?.attempt_id);
     const asset=input(sourceArea,'资产引用（可选）',config.source?.reference_asset||'','text',{placeholder:'asset://…'});
     const direction=select(sourceArea,'续写方向',[['before','向前'],['after','向后']],config.direction||'after');
     const urls=node('div','dd-form'),
       imagesUrl=textarea(urls,'参考图片公开 HTTPS 链接',config.reference_images?.join('\n')||'',3),
       audioUrl=textarea(urls,'参考音频公开 HTTPS 链接',config.reference_audio?.join('\n')||'',2),
       subjectUrl=input(urls,'主体图片公开 HTTPS 链接',config.subject_image_url||'','url');
     const inputArea=node('div','dd-form'),workflowForm=node('div','dd-pairs'),connection=label('p',''),hint=label('p','');
     const rowName=label('h3',''),vidmuseControls=node('div','dd-actions');
     const vidmuseRefresh=button('读取 VidMuse 的 MAGI-2',()=>loadVidMuse(true));
     vidmuseControls.append(vidmuseRefresh,button('VidMuse 连接设置',navigation.vidmuseSettings));
     let originals=[],sourcePending=false,localFields=[],workflowFields=[],previousWorkflow='',workflowChoice=config.workflow_id||'';
     const workflowDrafts=new Map();
     const split=value=>value.split(/\r?\n/).map(line=>line.trim()).filter(Boolean);
     pane.append(rowName,connection,vidmuseControls,cols,inputArea,sourceArea,urls,workflowForm,hint);
     pane.oninput=pane.onchange=()=>{engineDirty=true;};
     const modelRow=()=>catalog.models[provider.value]?.find(row=>row.id===pickedModel.value);
     const profile=()=>modelRow()?.profiles?.[kind.value];
     function show(control,enabled){control.disabled=!fresh||!enabled;control.parentElement.hidden=!enabled;}
     const files=new Map();
     let referenceRows=rev.images.filter(row=>['subject','environment','reference'].includes(row.role));
     const fileKey=file=>JSON.stringify([file.path,file.sha256]);
     for(const entry of rev.images)files.set(fileKey(entry.file),entry.file);
     for(const entry of Object.values(present().canvas.nodes)){
       if(entry.kind==='image')files.set(fileKey(entry.file),entry.file);
     }
     function localInputs(){
       inputArea.replaceChildren();localFields=[];
       const current=profile();
       for(const role of current?.local_roles||[]){
         const prior=rev.images.find(row=>row.role===role);
         const control=select(inputArea,roles[role],[['','选择项目图片'],...Array.from(files,([id,file])=>[id,file.path,false])],
            prior?fileKey(prior.file):'');
         control.dataset.engineField=role;control.disabled=!fresh;localFields.push({role,control});
       }
       if(current?.reference_count){
         const group=node('div','dd-form'),items=node('div','dd-asset-list');
         const choices=[['','选择项目图片'],...Array.from(files,([id,file])=>[id,file.path,false])];
         const available=select(group,'添加参考图片',choices,'');
         available.disabled=!fresh;
         const add=button('连接参考图片',()=>{
           if(!files.has(available.value)||referenceRows.length>=current.reference_count)return;
           engineDirty=true;
           referenceRows.push({role:'reference',file:files.get(available.value)});
           available.value='';drawReferences();
         });
         function drawReferences(){
           items.replaceChildren();
           referenceRows.forEach((image,index)=>{
             const line=node('div','dd-asset-row'),buttons=node('div','dd-actions');
             if(fresh){
               if(index>0)buttons.append(button('上移',()=>{
                 engineDirty=true;
                 [referenceRows[index-1],referenceRows[index]]=[referenceRows[index],referenceRows[index-1]];
                 drawReferences();
               }));
               buttons.append(button('从此版移除',()=>{
                 engineDirty=true;referenceRows.splice(index,1);drawReferences();
               }));
             }
             line.append(raw('small',String(index+1)+'. '+image.file.path),buttons);
             items.append(line);
           });
           add.disabled=!fresh||referenceRows.length>=current.reference_count;
         }
         group.append(add,items);
         drawReferences();inputArea.append(group);
       }
     }
     async function addSources(){
       if(originals.length||sourcePending)return;
       sourcePending=true;
       try{
         const rows=await projectVideos(pid());
         if(!visible(key)||tab!=='generation')return;
         originals=rows.filter(v=>v.model.startsWith('doubao-')&&!v.provider);
         optionsFor(source,[['','选择原成片'],...originals.map(v=>[v.generation_attempt_id,v.generation_attempt_id,false])],config.source?.attempt_id);
       }catch(problem){if(visible(key))error(problem);}
       finally{sourcePending=false;}
     }
     function durations(){
       const active=profile(),values=Object.values(active?.resolutions||{});
       const choices=active?.resolutions?.[resolution.value]||values[0]||[];
       const keep=duration.value||String(config.duration??'');
       optionsFor(duration,[...(active?.optional_output?[['','服务商默认']]:[]),
         ...choices.map(n=>[String(n),n===-1?'自适应时长':String(n),n===-1])],keep);
       show(duration,!!choices.length);
     }
     const sameSavedEngine=()=>provider.value===config.provider&&pickedModel.value===config.model&&kind.value===config.mode;
     function workflowList(){
       return (profile()?.workflows||[]).filter(item=>item.id!==legacyWorkflow||item.id===config.workflow_id);
     }
     function explicitWorkflow(){
       return profile()?.url_inputs==='relay'&&(workflow.value||(!workflow.options.length&&sameSavedEngine()&&config.workflow_id)||'');
     }
     const hasLargeSavedSeed=id=>sameSavedEngine()&&id===config.workflow_id&&
       config.seed!=null&&!Number.isSafeInteger(Number(config.seed));
     function showWorkflowFields(){
       if(previousWorkflow)workflowDrafts.set(previousWorkflow,Object.fromEntries(workflowFields.map(({name,control})=>[name,control.value])));
       const active=profile(),id=explicitWorkflow(),entry=workflowList().find(item=>item.id===id);
       workflowForm.replaceChildren();workflowFields=[];previousWorkflow=id;
       workflowForm.hidden=!entry;
       show(prompt,!entry||Boolean(entry.fields.prompt));
       const saved=workflowDrafts.get(id)||(id===config.workflow_id?config:{});
       for(const [name,field] of Object.entries(entry?.fields||{})){
         if(!Object.hasOwn(workflowLabels,name))continue;
         const caption=workflowLabels[name];
         const value=saved[name];
         const defaultLabel=field.default==null?'服务商默认':'服务商默认 '+String(field.default);
         const numeric=field.type==='integer'||field.type==='number';
         const largeSeed=name==='seed'&&hasLargeSavedSeed(id);
         let control;
         if(field.enum?.length){
           control=select(workflowForm,caption,[['',defaultLabel],...field.enum.map(choice=>[String(choice),String(choice),false])],String(value??''));
         }else if(field.type==='array'){
           control=textarea(workflowForm,caption,Array.isArray(value)?value.join('\n'):value,2);
         }else{
           const url=['first_frame','last_frame','reference_video'].includes(name);
           const limits=Object.fromEntries(Object.entries({min:field.minimum,max:field.maximum}).filter(([,limit])=>limit!=null));
           if(numeric)limits.step=field.type==='integer'?'1':'any';
           if(largeSeed)limits.placeholder=txt('使用 Codex 设置原始整数');
           else if(field.default!=null)limits.placeholder=String(field.default);
           control=input(workflowForm,caption,largeSeed?'':value??'',url?'url':numeric?'number':'text',limits);
         }
         control.dataset.engineField=name;
         if(field.required)control.setAttribute('aria-required','true');
         control.disabled=!fresh||largeSeed;
         control.oninput=()=>control.setCustomValidity('');
         workflowFields.push({name,control,field});
       }
       if(entry?.fields?.seed&&entry.fields.seed.maximum>Number.MAX_SAFE_INTEGER){
         workflowForm.append(label('small',largeSavedSeedHint(id)));
       }
       show(imagesUrl,active?.url_inputs==='relay'&&!id);show(audioUrl,active?.url_inputs==='relay'&&!id);
       show(subjectUrl,active?.url_inputs==='subject');
       urls.hidden=!active?.url_inputs||Boolean(id);
       durations();
       if(id)show(duration,false);
       show(resolution,!id&&!!Object.keys(active?.resolutions||{}).length);
     }
     const largeSavedSeedHint=id=>hasLargeSavedSeed(id)?exactSeedHint:'超大整数种子可在 Codex 聊天通过 MCP 设置。';
     function outputs(){
       const row=modelRow(),active=profile(),sizes=Object.keys(active?.resolutions||{});
       optionsFor(resolution,[...(active?.optional_output?[['','服务商默认']]:[]),...sizes.map(value=>[value,value,false])],resolution.value||config.resolution);
       optionsFor(ratio,(active?.ratios||[]).map(value=>[value,value==='adaptive'?'自适应':value,value==='adaptive']),ratio.value||config.ratio);
       show(ratio,!!active?.ratios.length);show(audio,!!active?.audio);
       if(!active?.audio)audio.checked=false;
       localInputs();
       sourceArea.hidden=!active?.source;direction.parentElement.hidden=!active?.direction;
       if(active?.source)void addSources();
       const list=active?.url_inputs==='relay'?workflowList():[];
       const options=list.map(item=>[item.id,item.name||item.id,false]);
       if(list.length&&sameSavedEngine()&&config.workflow_id&&!list.some(item=>item.id===config.workflow_id))
         options.push([config.workflow_id,config.workflow_id,false]);
       optionsFor(workflow,options.length?[['','默认参考工作流'],...options]:[],workflowChoice);
       show(workflow,!!options.length);
       showWorkflowFields();
       OAUI.raw(rowName,row?engineName({provider:provider.value,model:row.id}):'');
       OAUI.set(hint,provider.value==='sand'&&kind.value==='reference'?
         '使用当前项目的 PNG 或 JPEG 作为画面参考，最多 10 张。':
         active?.url_inputs?'使用已有公开链接。链接和模型账号的访问尚未核验。':'');
       vidmuseControls.hidden=provider.value!=='vidmuse';
       if(provider.value==='vidmuse'){
         const state=catalog.vidmuse?.state;
         OAUI.set(connection,state?navigation.vidmuse.text(state):'尚未检查 VidMuse 连接。');
         if(active?.vidmuseAudio?.length===1){
           audio.checked=active.vidmuseAudio[0];audio.disabled=true;
         }
         return;
       }
       OAUI.set(connection,provider.value==='tokenhex'&&row?.visibility!=='VISIBLE'?'Token Hex 型号可见性待核':
         catalog.connections[provider.value]==='CONFIGURED'?
          (provider.value==='sand'?'密钥已保存，模型调用权限未核验':'本机已配置连接'):
          '本机连接未配置或暂不可读');
     }
     function modes(preferred){
       const row=modelRow();
       optionsFor(kind,(row?.modes||[]).map(value=>[value,engineModes[value]]),preferred??(kind.value||config.mode));
       outputs();
     }
     function modelsForProvider(preferred){
       optionsFor(pickedModel,(catalog.models[provider.value]||[]).filter(row=>row.visibility!=='NOT_VISIBLE'||row.id===config.model&&provider.value===config.provider)
         .map(row=>[row.id,row.name||row.id,false]),preferred??(pickedModel.value||config.model));
       modes();
     }
     async function loadVidMuse(force){
       vidmuseRefresh.disabled=true;
       try{
         const snapshot=await navigation.vidmuse.get(force);
         if(!visible(key))return;
         vidmuseCatalog(catalog,snapshot);
         if(provider.value==='vidmuse')modelsForProvider('magi-2');
       }finally{vidmuseRefresh.disabled=false;}
     }
     provider.onchange=()=>{
       modelsForProvider();
       if(provider.value==='vidmuse'&&!catalog.vidmuse)loadVidMuse(false);
     };
     pickedModel.onchange=()=>modes();kind.onchange=outputs;resolution.onchange=durations;
     workflow.onchange=()=>{workflowChoice=workflow.value;showWorkflowFields();};
     const prompt=textarea(pane,'完整生成提示词',rev.prompt,5);
     modelsForProvider(draft?.model);
     for(const control of pane.querySelectorAll('input,textarea,select'))if(!fresh)control.disabled=true;
     if(fresh)pane.append(button('保存提示词与配置',async()=>{
       const active=profile();
       if(!active)return;
       const link=originals.find(row=>row.generation_attempt_id===source.value);
       const request={provider:provider.value,model:pickedModel.value,mode:kind.value};
       const workflowID=explicitWorkflow();
       if(!workflowID&&duration.value!=='')request.duration=Number(duration.value);
       if(!workflowID&&resolution.value)request.resolution=resolution.value;
       if(active.ratios.length&&ratio.value)request.ratio=ratio.value;
       if(active.audio)request.audio=audio.checked;
       if(active.source&&link)request.source={project_id:pid(),attempt_id:link.generation_attempt_id,
         sha256:link.asset.sha256,...(asset.value.trim()?{reference_asset:asset.value.trim()}:{})};
       if(active.direction)request.direction=direction.value;
       if(active.url_inputs==='subject'&&subjectUrl.value.trim())request.subject_image_url=subjectUrl.value.trim();
       if(workflowID){
         if(hasLargeSavedSeed(workflowID)){say(exactSeedHint,true);return;}
         const known=workflowList().some(item=>item.id===workflowID);
         if(!known&&sameSavedEngine()&&workflowID===config.workflow_id)Object.assign(request,config);
         request.workflow_id=workflowID;
         for(const {name,control,field} of workflowFields){
           const value=control.value.trim();
           if(!value)continue;
           control.setCustomValidity('');
           if(field.type==='integer'&&!Number.isSafeInteger(Number(value)))control.setCustomValidity(txt(exactSeedHint));
           if(field.type==='array'){
             const urls=split(value);
             if(urls.length<(field.minItems??0)||urls.length>(field.maxItems??Infinity))
               control.setCustomValidity(txt('请核对链接数量')+` (${field.minItems??0}–${field.maxItems??'∞'})`);
             request[name]=urls;
           }
           if(!control.reportValidity())return;
           if(field.type==='integer'||field.type==='number')request[name]=Number(value);
           else if(field.type!=='array')request[name]=value;
         }
       }else if(active.url_inputs==='relay'){
         if(split(imagesUrl.value).length)request.reference_images=split(imagesUrl.value);
         if(split(audioUrl.value).length)request.reference_audio=split(audioUrl.value);
       }
       const fields={prompt:prompt.value,configuration:request};
       if(localFields.length){
         fields.images=rev.images.filter(row=>!localFields.some(({role})=>role===row.role));
         for(const {role,control} of localFields)if(control.value)fields.images.push({role,file:files.get(control.value)});
       }
       if(active.reference_count){
         fields.images=rev.images.filter(row=>!['subject','environment','reference'].includes(row.role)).concat(referenceRows);
       }
       const saved=await revise(fields);
       if(saved){engineDraft=null;engineDirty=false;}
     },'primary'));
     const actions=node('div','dd-actions');
     actions.append(button('预检已保存配置',()=>preflight(key)),button('复制提示词',()=>copy(rev.prompt)));
     if(fresh&&rev.configuration){
       actions.append(rev.configuration.provider==='vidmuse'
         ?button('获取 VidMuse 积分报价',event=>vidmuseQuote(key,event.currentTarget),'primary')
         :button('交给 Codex 生成',()=>handoffGeneration(key)));
     }
     if(!fresh)actions.append(button('查看最新修订',()=>selectShot(context.scene_id,context.shot_id,context.head_revision)));
     pane.append(actions);inspector.replaceChildren(pane);
     if(provider.value==='vidmuse'&&!catalog.vidmuse)loadVidMuse(false);
   }catch(problem){if(visible(key)&&tab==='generation'){inspector.replaceChildren(label('p','模型目录暂不可读。'));error(problem);}}
 }
 async function vidmuseQuote(key,trigger){
   if(engineDirty){say('请先保存当前提示词与配置。',true);return;}
   const target=exact(),panel=$('directorDialog'),defaultSave=$('directorDialogSave');
   trigger.disabled=true;
   const showError=problem=>{
     const messages={VIDMUSE_PRICE_UNAVAILABLE:'官方目录缺少本次参数的积分报价。',
       VIDMUSE_BALANCE_UNAVAILABLE:'暂时无法读取 VidMuse 积分。',
       VIDMUSE_QUOTE_CHANGED:'VidMuse 账号、参数或积分报价已变化，请重新报价。',
       VIDMUSE_QUOTE_EXPIRED:'积分报价已过期，请重新报价。',
       VIDMUSE_ORIGINAL_ATTEMPT_CHANGED:'原任务状态已变化，请先检查原任务。',
       VIDMUSE_MODEL_AMBIGUOUS:'当前参数对应多个 VidMuse 型号，请核对目录。',
       VIDMUSE_REVISION_CHANGED:'镜头已修改，请使用最新修订。'};
     return messages[problem.message]||navigation.vidmuse.text(problem.message.replace(/^VIDMUSE_/,''));
   };
   const credits=(amount,balance)=>OAUI.format('本次预计积分')+' '+amount+' · '+OAUI.format('可用积分')+' '+balance;
   const stateText=result=>result.attempt_state==='SUBMIT_UNKNOWN'||result.state==='SUBMIT_UNKNOWN'
     ?'VidMuse 原请求结果待确认，未自动重发。':'VidMuse 原任务已登记到当前镜头。';
   try{
     const quote=await navigation.vidmuse.call({action:'quote',...target});
     if(!visible(key))return;
     if(quote.state==='ORIGINAL_ATTEMPT'){say(stateText(quote));await readWork({keep:true});return;}
     if(quote.state==='INSUFFICIENT_CREDITS'){say(txt('VidMuse 积分不足。')+' '+credits(quote.estimate,quote.balance),true);return;}
     if(quote.state!=='QUOTED')throw Error('VIDMUSE_PRICE_UNAVAILABLE');
     const content=node('div','dd-form');
     const summary=quote.shot+' · '+quote.model_name+' · '+quote.duration+' s · '+quote.resolution+' · '+quote.ratio+
       ' · '+OAUI.format(quote.mode==='text'?'文字生成':'图片参考')+' ('+quote.references+') · '+OAUI.format(quote.audio?'生成音频':'关闭音频');
     const notice=raw('p',credits(quote.estimate,quote.balance));
     notice.setAttribute('role','status');
     content.append(raw('p',summary),raw('p',OAUI.format('VidMuse 账号')+' '+quote.account),notice);
     const confirm=button('确认提交 VidMuse 任务',async()=>{
       if(!visible(key))return;
       confirm.disabled=true;
       OAUI.set(notice,'正在确认并提交 VidMuse 任务…');
       try{
         const result=await navigation.vidmuse.call({action:'confirm',quote_id:quote.quote_id});
         if(result.state==='INSUFFICIENT_CREDITS'){
           OAUI.raw(notice,txt('VidMuse 积分不足。')+' '+credits(result.estimate,result.balance));return;
         }
         if(panel.open&&content.isConnected)panel.close();
         if(visible(key)){say(stateText(result));await readWork({keep:true});}
       }catch(problem){OAUI.set(notice,showError(problem));}
     },'primary');
     content.append(confirm);
     dialog('确认 VidMuse 积分与任务',content,null);
     defaultSave.hidden=true;
     panel.addEventListener('close',()=>{defaultSave.hidden=false;},{once:true});
     confirm.focus();
   }catch(problem){if(visible(key))say(showError(problem),true);}
   finally{trigger.disabled=false;}
 }
 async function handoffGeneration(key){
   const target=exact();
   try{
     const result=await read('preflight',target);
     if(!visible(key))return;
     if(result.state!=='PREFLIGHT_VALID')throw Error('DIRECTOR_PREVIEW_UNAVAILABLE');
     const instruction='为这个精确镜头生成视频。镜头定位 '+JSON.stringify(target)+
       '。按用户本次授权，用 video.director.generation.submit 传该定位和稳定唯一的 generation_attempt_id。'+
       '提交后使用同一项目和 attempt 查询原状态。保留聊天内原成片播放交付和 Jiusera 作品中的原候选。'+
       '若另有已完成的本地剪辑 MP4，用 register_work_video 登记到准确作品，勿用整片覆盖镜头原片。';
     if(canSend()){await send(instruction);if(visible(key))say('已发送镜头与原引擎到当前 Codex。');}
     else await copy(instruction);
   }catch(problem){if(visible(key))error(problem);}
 }
 async function preflight(key){
   try{
     const result=await read('preflight',exact());
     if(!visible(key))return;
     if(result.state!=='PREFLIGHT_VALID'||result.revision_id!==context.revision.id)throw Error('DIRECTOR_PREVIEW_UNAVAILABLE');
     say(result.connection==='CONFIGURED'?'本地参数与输入已通过预检。实际模型访问尚未核验。':'本地参数与输入已通过预检。可继续整理分镜，连接在模型设置里配置。');
   }catch(problem){if(visible(key))error(problem);}
 }
 function dialog(title,body,commit){
   if(writing)return;
   dialogWrite=commit;OAUI.set($('directorDialogTitle'),title);
   $('directorDialogBody').replaceChildren(body);
   $('directorDialog').showModal();
 }
 async function submitDialog(){
   if(!dialogWrite||writing)return;
   if([...$('directorDialogBody').querySelectorAll('input')].some(input=>!input.reportValidity()))return;
   const save=$('directorDialogSave');
   save.disabled=true;
   try{if(await dialogWrite())$('directorDialog').close();}
   finally{save.disabled=false;}
 }
 function workDialog(existing){
   const projectID=pid(),version=data?.version,body=node('div','dd-form'),grid=node('div','dd-pairs');
   const title=input(body,'作品名称',existing?.title||'','text',{required:true,maxLength:240});
   const ratio=select(grid,'画幅',['16:9','9:16','1:1','4:3','3:4','21:9','adaptive'].map(k=>[k,k]),existing?.ratio);
   const duration=input(grid,'目标时长（秒）',seconds(existing?.duration_ms),'number',{min:0,step:'0.001'});
   body.append(grid);
   const fields={};for(const field of ['brief','platform','audience','tone','references','style','caption_safe_area','sound'])
     fields[field]=textarea(body,language[field],existing?.[field]);
   dialog(existing?'作品约定':'新建作品',body,()=>{
     const values={title:title.value,ratio:ratio.value,duration_ms:applyMS(duration),
       ...Object.fromEntries(Object.entries(fields).map(([k,el])=>[k,el.value]))};
     if(existing)return write('edit_work',{project_id:projectID,work_id:existing.id,expected_version:version,fields:values},
       ()=>readWork({keep:true}));
     const intent=selection;
     return write('create_work',{project_id:projectID,fields:values},result=>
       intent===selection?readChosenWork(result.work_id):readWork({work:result.work_id}));
   });
 }
 function entityDialog(kind){
   if(!present())return;
   const scope=workScope(),scene=currentScene(),body=node('div','dd-form');
   const title=input(body,kind==='scene'?'场次名称':'镜头名称','','text',{required:true,maxLength:240});
   if(kind==='scene'){
     const initial=present().scenes.at(-1)?.end_ms||0;
     const start=input(body,'开始秒数',seconds(initial),'number',{min:0,step:'0.001'});
     const end=input(body,'结束秒数',seconds(initial),'number',{min:0,step:'0.001'});
     dialog('新建场次',body,()=>write('create_scene',{...scope,title:title.value,start_ms:applyMS(start),end_ms:applyMS(end)},
       async result=>{
         const selection=await edit('select_scene',{...scope,scene_id:result.scene_id});
         if(selection.state!=='SAVED')throw Error('DIRECTOR_SAVE_NOT_VERIFIED');
         await readWork({keep:true,scene:result.scene_id});
       }));
   }else if(scene){
     dialog('新建镜头',body,()=>write('create_shot',{...scope,scene_id:scene.id,title:title.value,origin:'panel'},
       result=>readWork({keep:true,focus:{scene_id:scene.id,shot_id:result.shot_id,revision_id:result.revision_id}})));
   }
 }
 async function copy(text){
   if(!text)return;
   const field=$('directorCopy');
   field.value=text;
   try{
     await navigator.clipboard.writeText(text);
     field.hidden=true;say('已复制。');
   }catch(_){
     field.hidden=false;field.focus();field.select();say('可从文本框复制。');
   }
 }
 function handoffText(kind){
   const ctx=context,snapshot=exact(),instruction=$('directorInstruction').value.trim();
   const task=kind==='image'?'给该镜制作或选择一张项目内图片分镜，保留已采用的其他图片及角色。':
      '修改该镜的文字分镜，保留与请求无关的字段和现有素材。';
   return '请按 Jiusera 随包 video-director Skill 接手当前分镜。'+task+'\n'
     +(instruction?'我的修改要求：'+instruction+'\n':'')
     +'作品：'+ctx.work.title+'｜场次：'+ctx.scene.title+'｜镜头：'+ctx.revision.title+'\n'
     +'用 video.director.read action=context 读取以下精确定位，再核对当前 head_revision。\n'
     +JSON.stringify(snapshot)+'\n'
     +'只在原镜头仍是此修订时，用 video.director.edit action=revise、origin=codex、新的 operation_id 和 base_revision 保存。'
     +' 图片须是项目目录内可读的 PNG/JPEG，传实际相对路径、相同 project_id 和 SHA-256。'
     +' 完成后按工具回执的具体修订 ID 回读名称、文字与素材。不要提交视频生成。';
 }
 async function askCodex(kind,onlyCopy=false){
   if(!context)return;
   const message=handoffText(kind),target=exact(),key=scopeKey();
   if(onlyCopy){await copy(message);return;}
   if(!canSend()){
     $('directorCopy').value=message;$('directorCopy').hidden=false;
     $('directorCopy').focus();$('directorCopy').select();
     say('当前宿主未提供聊天发送能力，可复制下方上下文。');return;
   }
   if(watch?.key===key){say('已交给 Codex，正在等待该镜头的新修订。');return;}
   const text=$('directorSendText'),image=$('directorSendImage');
   text.disabled=image.disabled=true;
   try{
     const receipt=await send(message);
     if(receipt.isError||!visible(key))return;
     say('已交给 Codex，正在等待该镜头的新修订。');
     watch={target,key};
     watchTimer=setTimeout(checkHandoff,2500);
   }catch(_){
     if(visible(key)){
       const field=$('directorCopy');field.value=message;field.hidden=false;
       say('未收到宿主确认。请先核对当前聊天，可复制下方上下文。',true);
     }
   }finally{
     if(visible(key))text.disabled=image.disabled=context.revision.id!==context.head_revision;
   }
 }
 async function checkHandoff(){
   const pending=watch;
   if(!pending||!visible(pending.key)){stopWatch();return;}
   try{
     const previous=await read('context',pending.target);
     if(watch!==pending||!visible(pending.key))return;
     if(previous.head_revision!==pending.target.revision_id){
       const next=await read('context',{...pending.target,revision_id:previous.head_revision});
       if(watch!==pending||!visible(pending.key))return;
       if(next.revision.origin==='codex'&&next.revision.parent_revision===pending.target.revision_id){
         stopWatch();
         await readWork({work:next.work_id,focus:{scene_id:next.scene_id,shot_id:next.shot_id,revision_id:next.revision.id}});
         say('已读回 Codex 的新修订。');return;
       }
       stopWatch();
       say('当前镜头已有其他变更，请刷新核对。');return;
     }
   }catch(_){
     if(watch!==pending)return;
     say('暂未读到修订，可刷新分镜继续核对。',true);
   }
   if(watch===pending)watchTimer=setTimeout(checkHandoff,2500);
 }
 async function loadCards(){
   if(!cardData)cardData=await read('cards');
   if(mode==='cards')renderCards();
 }
 function renderCards(){
   const list=$('directorCardList'),detail=$('directorCardDetail');
   const phrase=$('directorCardQuery').value.trim().toLocaleLowerCase(),
       category=$('directorCardCategory').value,subject=$('directorCardSubjects').value,model=$('directorCardModel').value;
   const cards=(cardData?.cards||[]).filter(c=>(!category||c.category===category)&&
      (!subject||c.reference_subjects.includes(Number(subject)))&&(!model||c.suggested_for.includes(model))&&
      [c.title,c.effect,c.writing,c.example,c.subjects].join(' ').toLocaleLowerCase().includes(phrase));
   const chosen=cards.find(row=>row.id===cardID)||cards[0];
   cardID=chosen?.id||'';list.replaceChildren();detail.replaceChildren();
   for(const card of cards){
     const row=button('',()=>{cardID=card.id;renderCards();});
     row.setAttribute('aria-pressed',String(card.id===cardID));
     row.append(raw('strong',card.title),raw('span',' · '+txt(cardKinds[card.category])));
     list.append(row);
   }
   if(!chosen){detail.append(label('p','没有找到匹配的提示词卡。'));return;}
   detail.append(raw('h2',chosen.title),raw('p',chosen.effect),
     raw('p',chosen.subjects+' · v'+chosen.version+' · '+txt('写作示例，模型效果待实测')));
   for(const [caption,key] of [['写法','writing'],['原创示例','example'],['常见问题与修法','fix']])
     detail.append(label('h3',caption),raw('p',chosen[key]));
   const actions=node('div','dd-actions');
   actions.append(button('复制写法与示例',()=>copy(chosen.writing+'\n\n'+chosen.example)),
     button('打开参考来源',async()=>{try{await navigation.source(chosen.source);}catch(problem){error(problem);}}));
   if(context&&context.revision.id===context.head_revision){
     const included=context.revision.cards.some(c=>c.id===chosen.id&&c.version===chosen.version);
     const use=button(included?'已关联当前镜头':'关联到当前镜头',async()=>{
       const cards=[...context.revision.cards,{id:chosen.id,version:chosen.version}];
       if(await revise({cards},'已将卡片关联到当前镜头。'))renderCards();
     });
     use.disabled=included;actions.append(use);
   }
   detail.append(actions);
 }
 function view(target){
   if(mode===target)return;
   if(mode==='desk'){
     canvas.suspend();clearPreview();releaseVoicePreview();stopWatch();visual++;
     if($('directorCanvasPreview').open)$('directorCanvasPreview').close();
     if($('directorDialog').open)$('directorDialog').close();
   }
   if(mode==='monitor')review.clear();
   mode=target;root.scrollTop=0;
   const main=mode==='desk'||mode==='monitor';
   OAUI.set($('directorTitle'),({monitor:'视频剪辑',desk:'工作画布',assets:'资产库',cards:'提示词库',
     tasks:'任务详情'})[mode]);
   $('directorMore').open=false;
   OAUI.set($('directorMoreLabel'),mode==='desk'?'画布工具':'作品工具');
   $('directorMore').hidden=!main;
   $('directorToolBack').hidden=!['cards','tasks'].includes(mode);
   $('directorCardPage').hidden=mode!=='cards';
   $('directorWorkbar').hidden=!main;
   if(mode!=='desk')board.hidden=true;
   if(mode!=='monitor')$('directorMonitor').hidden=true;
   if(!main){
     $('directorSound').hidden=true;
     $('directorWorkHint').hidden=true;
     articleStage.hide();
     document.body.removeAttribute('data-workbench-article');
   }
   if(mode==='cards')void loadCards().catch(error);
   if(main){render();void tickWorkspace();}
 }
 const mainView=()=>mode==='monitor'||mode==='desk';
 function setProjectList(list,current){
   projects=list;
   optionsFor(project,[['',list.length?'选择项目':'暂无项目'],
     ...list.map(row=>[row.id,row.label||row.name,false])],current||'');
   project.disabled=!list.length;
   project.title=list.find(row=>row.id===project.value)?.label||'';
 }
 async function refreshProjects({restore=false,imwScope}={}){
   guideRead=0;navigation.guideChanged?.();
   const epoch=++projectLoad,intent=selection,current=pid(),{projects:list}=await read('projects');
   if(epoch!==projectLoad||intent!==selection||!mode)return;
   if(imwScope){
     const id=list.some(row=>row.id===imwScope.project_id)?imwScope.project_id:'';
     resetWork();setProjectList(list,id);explicitProject=id;render();
     if(!id){render();return;}
     if(imwScope.work_id){await readWork({work:imwScope.work_id});return;}
     const overview=await read('overview',{project_id:id});
     if(epoch!==projectLoad||intent!==selection||mode!=='monitor'||pid()!==id)return;
     const eligible=overview.works.find(row=>row.kind!=='article'&&!row.inbox);
     if(overview.work?.kind==='article'&&eligible){await readWork({work:eligible.id});return;}
     await readWork({overview});return;
   }
   let saved=null;
   if(restore&&!current&&mainView()){
     try{saved=JSON.parse(localStorage.getItem('jiusera.workbench.last-work'));}catch(_){}
   }
   const remembered=saved&&list.some(row=>row.id===saved.project)?saved.project:'';
   const initial=current||remembered||(restore&&mainView()&&list.length===1?list[0].id:'');
   setProjectList(list,initial);
   if(remembered&&typeof saved.work==='string'){
     const request=reading+1;
     try{await readWork({work:saved.work});return;}
     catch(problem){
       if(problem.message!=='DIRECTOR_WORK_NOT_FOUND')throw problem;
       if(request!==reading||intent!==selection||pid()!==remembered||!mode)return;
       preferredWorks.delete(remembered);
       resetWork();
     }
   }
   await readWork({keep:true});
 }
 function resetWork(){
   reading++;stopWatch();engineDraft=null;engineDirty=false;data=null;context=null;sceneID=null;
 }
 async function openShot(shot){
   const {project_id,work_id,scene_id,shot_id,revision_id}=shot.scope;
   if(mode==='monitor'&&shot.kind==='mv-work'){
     if(![project_id,work_id].every(value=>/^[a-f0-9]{32}$/.test(value||''))||
       !projects.some(row=>row.id===project_id))return;
     project.value=project_id;explicitProject=project_id;
     if(await readWork({work:work_id})&&mode==='monitor'&&present()?.id===work_id){
       root.scrollTop=0;
       $('dmScreenTitle').setAttribute('tabindex','-1');
       $('dmScreenTitle').focus({preventScroll:true});
     }
     return;
   }
   if(mode!=='desk'||![project_id,work_id,scene_id,shot_id,revision_id].every(value=>/^[a-f0-9]{32}$/.test(value||''))||
      !projects.some(row=>row.id===project_id))return;
   project.value=project_id;
   if(!await readWork({work:work_id,focus:{scene_id,shot_id,revision_id}}))return;
   const preferred=shot.tab;
   if(preferred==='images'||preferred==='stage'&&context?.revision.stage)tab=preferred;
   renderInspector();
   const toggle=$('wbShot');
   if(toggle&&toggle.getAttribute('aria-expanded')!=='true')toggle.click();
 }
 async function open(target='monitor',shot){
   if(target==='monitor'&&shot?.scope){resetWork();review.clear();}
   root.hidden=false;
   view(target);
   if(!workspaceTimer)workspaceTimer=setInterval(tickWorkspace,2600);
   const intent=selection;
   try{
     const imwScope=target==='monitor'&&['mv-work','imw-project'].includes(shot?.kind)?shot.scope:undefined;
     await refreshProjects({restore:true,imwScope});
     if(shot&&!imwScope&&selection===intent&&mode===target)await openShot(shot);
     await checkChatRequest();
   }
   catch(problem){if(mode)error(problem);}
 }
 function startPrompt(id){
   return '请使用 $wechat-ecosystem:video-director，在当前聊天开始或继续我正在构思的作品。原操作 operation_id='+id+
     '。先按 DIRECTOR_DESK 核对本聊天的真实工作区绝对根路径并与 own.projects.read catalog 精确匹配，必要时用 own.projects.sync 关联该真实目录。'+
     '根或创作意图不明确时请在当前聊天指出具体缺项。依我的明确意图复用原作品或新建。'+
     '先查 video.director.read action=work_request 的同一 operation_id，然后用 video.director.edit action=start_work 和同一原键完成。'+
     '用精确 project_id/work_id 读回 overview 并报告结果。不要用当前页面的下拉、缓存、同名项目、其他聊天或插件目录推断归属。'+
     '不要因面板已发送便认定已建作品，也不要自动发起付费生成或发表。';
 }
 async function startChatWork(){
   if(!mainView()||!canSend()||(chatRequest&&chatRequest.selection===selection))return;
   const request={id:randomID(),selection};
   chatRequest=request;render();navigation.guideChanged?.();
   try{
     await send(startPrompt(request.id));
     if(chatRequest===request&&request.selection===selection&&mainView())say('请求已发往当前聊天。');
   }catch(_){
     if(chatRequest===request&&request.selection===selection&&mainView())
       say('宿主未确认发送。请查看当前聊天，面板会继续核对原请求。',true);
   }
   await checkChatRequest();
 }
 async function checkChatRequest(){
   const request=chatRequest;
   if(!request||request.selection!==selection||!mainView()||readingRequest||writing)return;
   const current=()=>chatRequest===request&&request.selection===selection&&mainView();
   readingRequest=true;
   try{
     const receipt=await read('work_request',{operation_id:request.id});
     if(!current()||receipt.state!=='READY'||receipt.operation_id!==request.id)return;
     const {project_id,work_id}=receipt;
     const [{projects:list},overview]=await Promise.all([read('projects'),read('overview',{project_id,work_id})]);
     if(!current())return;
     if(!list.some(row=>row.id===project_id)||overview.project_id!==project_id||overview.work?.id!==work_id||
        overview.work.inbox||!overview.works.some(row=>row.id===work_id))throw Error('DIRECTOR_WORK_NOT_FOUND');
     projectLoad++;explicitProject=project_id;
     resetWork();setProjectList(list,project_id);
     if(await readChosenWork(work_id,overview)&&current()){
       chatRequest=null;render();say('已读回聊天中的作品。');navigation.guideChanged?.();
     }
   }catch(problem){if(current())error(problem);}
   finally{readingRequest=false;}
 }
 function recoverChatWork(){
   const body=node('div','dd-form');
   const operation=input(body,'聊天中的原操作编号','','text',{required:true,pattern:'[a-f0-9]{32}',maxLength:32});
   dialog('找回聊天作品',body,async()=>{
     chatRequest={id:operation.value,selection};
     render();navigation.guideChanged?.();await checkChatRequest();
     if(chatRequest)say('尚未读到这次请求的作品，请核对聊天中的原操作编号。');
     return true;
   });
 }
 async function followFirstWork(){
   if(!mainView()||!explicitProject||pid()!==explicitProject||chatRequest?.selection===selection||
      readingWork||writing||data?.project_id!==explicitProject||data.works.some(row=>!row.inbox))return;
   const id=explicitProject,intent=selection,epoch=reading;
   const result=await read('overview',{project_id:id});
   if(!mainView()||intent!==selection||epoch!==reading||result.project_id!==id)return;
   const works=result.works.filter(row=>!row.inbox);
   if(works.length===1){
     const work=works[0].id;
     await readWork({work,overview:result.work?.id===work?result:undefined});
   }else if(works.length>1){
     data={...data,works:result.works};render();
   }
 }
 async function tickWorkspace(){
   if(!mainView()||document.hidden||ticking)return;
   ticking=true;
   try{
     await checkChatRequest();
     try{await followFirstWork();}catch(_){/* Leave the verified view available. */}
     if(mode==='monitor'&&present()&&!present().inbox&&present().kind!=='article'){
       const scope=workScope(),cached=workspaceRows.get(workKey(scope));
       const stamp=await review.checkTimelineRevision().catch(()=>null);
       if(stamp&&stamp.project_id===pid()&&stamp.work_id===present()?.id&&
          stamp.version===data?.version&&cached?.version===stamp.version&&
          cached.cards.every(card=>['ASSET_READY','FAILED','CANCELLED'].includes(card.state)))return;
     }
     await syncWorkspace();
   }finally{ticking=false;}
 }
 const checkOnReturn=()=>{if(mode==='monitor'&&!document.hidden)void tickWorkspace();};
 window.addEventListener('focus',checkOnReturn);
 document.addEventListener('visibilitychange',checkOnReturn);
 function close(){
   navigation.closeCharacterPicker();imageDraft=null;releaseVoicePreview();canvas.suspend();review.clear();articleStage.hide();
   document.body.removeAttribute('data-workbench-article');
   clearInterval(workspaceTimer);workspaceTimer=null;polled.clear();engineDraft=null;engineDirty=false;
   mode='';root.hidden=true;projectLoad++;reading++;visual++;clearPreview();stopWatch();say('');
   if($('directorCanvasPreview').open)$('directorCanvasPreview').close();
   if($('directorDialog').open)$('directorDialog').close();
   $('directorCopy').hidden=true;
 }
 project.onchange=()=>{
   navigation.imwChoose?.({project_id:pid()});navigation.projectSelected?.(pid());
   selection++;explicitProject=pid();
   try{
     if(explicitProject)localStorage.setItem('jiusera.workbench.last-work',JSON.stringify({project:explicitProject}));
     else localStorage.removeItem('jiusera.workbench.last-work');
   }catch(_){}
   guideWorkChoice=null;
   project.title=projects.find(row=>row.id===pid())?.label||'';
   resetWork();render();
   void readWork().catch(error);
 };
 workSelect.onchange=()=>{
   const chosen=workSelect.value;
   if(!chosen){render();return;}
   navigation.imwChoose?.({project_id:pid(),work_id:chosen});selection++;stopWatch();engineDraft=null;engineDirty=false;
   if(mode==='monitor'&&document.body.dataset.imwVideo==='true'){resetWork();review.clear();render();}
   void readChosenWork(chosen).catch(error);
 };
 $('directorSceneSelect').onchange=()=>selectScene($('directorSceneSelect').value);
 $('directorPrevious').onclick=()=>{const scenes=present().scenes;return selectScene(scenes[scenes.indexOf(currentScene())-1]?.id);};
 $('directorNext').onclick=()=>{const scenes=present().scenes;return selectScene(scenes[scenes.indexOf(currentScene())+1]?.id);};
 $('directorDialogSave').onclick=submitDialog;
 $('directorDialogBody').onkeydown=event=>{
   if(event.key==='Enter'&&event.target instanceof HTMLInputElement){
     event.preventDefault();void submitDialog();
   }
 };
 $('directorCancel').onclick=()=>$('directorDialog').close();
 $('directorCanvasPreviewClose').onclick=()=>$('directorCanvasPreview').close();
 $('directorCanvasAssets').onclick=navigation.library;
 $('directorCanvasEngine').onclick=pickEngine;
 function noteDialog(existing){
   const form=node('div','dd-form'),
         title=input(form,'标题',existing?.title||'','text',{required:true,maxLength:240}),
         text=textarea(form,'文字内容',existing?.text||'',4);
   dialog(existing?'编辑文字卡':'新建文字卡',form,()=>existing?
     canvas.editNote(existing.id,title.value,text.value):
     canvas.add({kind:'note',title:title.value,text:text.value,...shotLink()}));
 }
 $('directorCanvasNote').onclick=()=>noteDialog();
 $('directorCanvasImage').onclick=()=>{
   const form=node('div','dd-form'),title=input(form,'图片名称','','text',{maxLength:240});
   const file=fileInputs(form,'','','image/png,image/jpeg',true);
   dialog('添加项目图片',form,async()=>{
     const filename=file.filename(),link=shotLink();
     try{
       const spec=await file.prepare();
       return await canvas.add({kind:'image',title:(title.value.trim()||filename||spec.path.split('/').at(-1)||txt('图片')).slice(0,240),
                                file:spec,...link});
     }catch(problem){error(problem);return false;}
   });
 };
 $('directorChatWork').onclick=startChatWork;
 $('directorChatWorkMenu').onclick=()=>{$('directorMore').open=false;void startChatWork();};
 $('directorRefreshMenu').onclick=()=>{$('directorMore').open=false;$('directorRefresh').click();};
 $('directorRecoverWork').onclick=recoverChatWork;
 $('directorStopFollowing').onclick=()=>{chatRequest=null;render();say('');navigation.guideChanged?.();};
 $('directorProjectSettings').onclick=navigation.project;
 $('directorNewWork').onclick=()=>{if(pid())workDialog();};
 $('directorWorkSettings').onclick=()=>workDialog(present());
 $('directorNewScene').onclick=()=>entityDialog('scene');
 $('directorNewShot').onclick=()=>entityDialog('shot');
 $('directorRefresh').onclick=async()=>{
   if(writing)return;
   if(mode==='desk'){stopWatch();engineDirty=false;engineDraft=null;}
   try{await refreshProjects();say('');await checkChatRequest();await syncWorkspace({poll:true});}
   catch(problem){error(problem);}
 };
 $('directorSendText').onclick=()=>askCodex('text');
 $('directorSendImage').onclick=()=>askCodex('image');
 $('directorCopyContext').onclick=()=>askCodex('text',true);
 $('directorCardsLink').onclick=()=>navigation.go('cards');
 $('directorToolBack').onclick=navigation.back;
 $('directorTabs').querySelectorAll('button').forEach(pick=>pick.onclick=()=>{tab=pick.dataset.tab;renderInspector();});
 for(const id of ['directorCardQuery','directorCardCategory','directorCardSubjects','directorCardModel'])$(id).oninput=renderCards;
 async function goToArticle(row){
   const checked=await read('overview',{project_id:row.project_id,work_id:row.work_id});
   if(checked.project_id!==row.project_id||checked.work?.id!==row.work_id||checked.work.kind!=='article')
     throw Error('ARTICLE_WORK_NOT_FOUND');
   selection++;explicitProject=row.project_id;setProjectList(projects,row.project_id);
   await navigation.go('desk');
   await readChosenWork(row.work_id,checked);
 }
 function shotLink(){return context?.shot_id?{shot_id:context.shot_id}:{};}
 function canAttach(row){return mode==='assets'&&!!present()&&!present().inbox&&row.project===pid()&&!!row.asset?.sha256;}
 async function attach(row){
   if(!canAttach(row))return false;
   const node={kind:'asset',title:row.title.slice(0,240),...shotLink(),
     asset:{family:row.family,media_kind:row.kind,project_id:row.project,attempt_id:row.attempt,sha256:row.asset.sha256}};
   navigation.go('desk');
   const saved=await canvas.add(node);
   if(!saved&&mode==='desk')navigation.asset({family:row.family,kind:row.kind,project:row.project,
     attempt:row.attempt,sha256:row.asset.sha256});
   return saved;
 }
 async function canvasCommit(action,args,saved){
   const [project_id,work_id]=saved.key.split(':');
   const target={project_id,work_id};
   const current=()=>!!mode&&pid()===project_id&&data?.project_id===project_id&&present()?.id===work_id;
   const send=async version=>{
     const request={...target,expected_canvas_version:version,...args};
     const result=await edit(action,request,action==='canvas_view');
     if(result.state!=='SAVED'||result.project_id!==project_id||result.work_id!==work_id||
        result.canvas_version!==version+1)throw Error('DIRECTOR_SAVE_NOT_VERIFIED');
     saved.version=Math.max(saved.version,result.canvas_version);
     pendingWrites.delete(intentKey(action,request));
     return result.canvas_version;
   };
   if(action==='canvas_view'){
     const waitForOriginal=async()=>{
       const result=await read('overview',target);
       if(result.project_id!==project_id||result.work?.id!==work_id)throw Error('DIRECTOR_SAVE_NOT_VERIFIED');
       const latest=result.work.canvas;
       saved.version=Math.max(saved.version,latest.version);
       const view=latest.viewport;
       const matched=['x','y','scale'].every(name=>view[name]===args.viewport[name]);
       return {matched,version:latest.version};
     };
     const version=saved.version;
     if(saved.inbox)return {state:'saved',version};
     try{return {state:'saved',version:await send(version)};}
     catch(problem){
       const conflict=problem.message==='DIRECTOR_CANVAS_CHANGED';
       const unknown=/^HOST_|^DIRECTOR_SAVE_NOT_VERIFIED$/.test(problem.message||'');
       if(!conflict&&!unknown)return {state:'unsaved'};
       try{
         const latest=await waitForOriginal();
         if(latest.matched&&latest.version>=version)return {state:'saved',version:latest.version};
         if(conflict&&current()&&latest.version>version&&saved.viewport===args.viewport){
           try{return {state:'saved',version:await send(latest.version)};}
           catch(second){
             if(!/^HOST_|^DIRECTOR_SAVE_NOT_VERIFIED$/.test(second.message||''))return {state:'unsaved'};
             const previous=await waitForOriginal();
             if(previous.matched&&previous.version>latest.version)return {state:'saved',version:previous.version};
             return {state:'unknown'};
           }
         }
       }catch(_){return {state:conflict?'unsaved':'unknown'};}
       return {state:conflict?'unsaved':'unknown'};
     }
   }
   try{
     await send(saved.version);
   }catch(problem){
     if(current()){error(problem);await readWork({work:work_id}).catch(()=>{});}
     return false;
   }
   if(current()){
     const value=exact();
     const focus=value&&{scene_id:value.scene_id,shot_id:value.shot_id,revision_id:value.revision_id};
     try{await readWork({work:work_id,focus});if(current())say('画布已保存。');}
     catch(problem){if(current())error(problem);}
   }
   return true;
 }
 async function canvasImage(row,thumbnail){
   const scope=workScope();
   const response=row.kind==='shot_reference'?await media('image',{...scope,scene_id:row.scene,
       shot_id:row.shot_id,revision_id:row.revision,thumbnail}):
       await media('canvas_image',{...scope,node_id:row.id,thumbnail});
   if(response.sha256!==(row.sha256||row.file?.sha256))throw Error('DIRECTOR_ASSET_CHANGED');
   return response;
 }
 async function canvasPicture(row){
   const slot=node('div');
   attachImage(slot,await canvasImage(row,true),true);
   return slot.firstChild;
 }
 function playCanvasVideo(slot,row,scope=workScope(),statusTarget=null){
   const args={...scope,delivery_id:row.id,sha256:(row.asset||row).sha256};
   return OAVideoPreview(slot,row.asset||row,{
     lazy:true,sound:navigation.sound,statusTarget,
     chunk:offset=>media('canvas_video_chunk',{...args,offset}),
     frames:start=>media('canvas_video_frames',{...args,start}),
   });
 }
 async function adoptCanvasVideo(row){
   const scope=workScope();
   const args={...scope,scene_id:row.scene_id,shot_id:row.shot_id,candidate_id:row.id,sha256:row.asset.sha256};
   if(row.adopted_candidate_id)args.expected_candidate_id=row.adopted_candidate_id;
   return write('adopt_video',args,async result=>{
     if(result.adopted_video?.candidate_id!==row.id||result.adopted_video.sha256!==row.asset.sha256)
       throw Error('DIRECTOR_SAVE_NOT_VERIFIED');
     const payload=await read('deliveries',scope);
     if(payload.project_id!==scope.project_id||payload.work_id!==scope.work_id||
          !payload.cards.some(item=>item.id===row.id&&item.adopted))throw Error('DIRECTOR_SAVE_NOT_VERIFIED');
     acceptDeliveries(scope,payload);
   },'已采用此视频。');
 }
 async function selectCanvasNode(row){
   await selectShot(row.scene,row.shot_id||row.id,row.revision);
   if(row.kind==='engine'&&context?.shot_id===row.shot_id){tab='generation';renderInspector();}
 }
 let canvasPreviewRead=0;
 async function showCanvasNode(row){
   if(row.kind==='asset'){
     const asset=row.asset;
     navigation.asset({family:asset.family,kind:asset.media_kind||asset.family,project:asset.project_id,attempt:asset.attempt_id,sha256:asset.sha256});
     return;
   }
   const preview=$('directorCanvasPreview'),body=$('directorCanvasPreviewBody');
   const readID=++canvasPreviewRead,scope=workKey(workScope());
   const current=()=>readID===canvasPreviewRead&&preview.open&&mode==='desk'&&present()&&workKey(workScope())===scope;
   OAUI.raw($('directorCanvasPreviewTitle'),row.title);
   const editNote=$('directorCanvasNoteEdit');
   editNote.hidden=row.kind!=='note';
   editNote.onclick=()=>{preview.close();noteDialog(row);};
   body.replaceChildren(row.kind==='note'?raw('p',row.text):label('p','正在读取图片…'));
   preview.showModal();
   if(row.kind==='image'||row.kind==='shot_reference'){
     try{
       const rendered=await canvasImage(row,false);
       if(current())attachImage(body,rendered);
     }catch(problem){if(current()){body.replaceChildren(label('p','当前图片不可用'));error(problem);}}
   }
 }
 function acceptDeliveries(scope,payload){
   if(payload.project_id!==scope.project_id||payload.work_id!==scope.work_id||!Array.isArray(payload.cards))return false;
   const key=workKey(scope),old=workspaceRows.get(key);
   if(old&&payload.version<old.version)return false;
   workspaceRows.set(key,payload);
   if(pid()===scope.project_id&&present()?.id===scope.work_id){
     if(mode==='desk')canvas.setDeliveries(key,payload.cards,payload.version);
     if(mode==='monitor')review.render({work:present(),scope,context,cards:payload.cards,workVersion:payload.version});
   }
   return true;
 }
 async function syncWorkspace({poll=false}={}){
   if(!['desk','monitor'].includes(mode)||!present()||document.hidden||workspaceBusy)return;
   const scope=workScope(),key=workKey(scope),shot=exact(),readEpoch=reading;
   const current=()=>['desk','monitor'].includes(mode)&&pid()===scope.project_id&&present()?.id===scope.work_id;
   workspaceBusy=true;
   try{
     if(present()?.kind==='article'){await articleStage.show(scope,mode);return;}
     const payload=await read('deliveries',scope);
     if(!current()||!acceptDeliveries(scope,payload))return;
     const idle=()=>current()&&!writing&&!watch&&!readingWork&&reading===readEpoch;
     if(idle()&&payload.version>data.version){
       let focus;
       if(shot&&context?.head_revision===shot.revision_id){
         const observed=await read('context',shot);
         if(!idle()||scopeKey()!==JSON.stringify(shot))return;
         if(engineDirty&&observed.head_revision!==shot.revision_id)
           say('Codex 已更新这个镜头。刷新可查看最新修订。');
         focus={scene_id:shot.scene_id,shot_id:shot.shot_id,revision_id:observed.head_revision};
       }
       if(!engineDirty)await readWork({work:scope.work_id,focus});
     }
     if(!current()||!poll||mode!=='desk')return;
     const next=payload.cards.find(row=>row.pollable&&Date.now()-(polled.get(key+row.attempt_id)||0)>=18000);
     if(next){
       polled.set(key+next.attempt_id,Date.now());
       const updated=await tool('video.director.edit',{action:'poll_delivery',...scope,attempt_id:next.attempt_id});
       if(current())acceptDeliveries(scope,updated);
     }
   }catch(_){/* Keep the last verified visible cards across a temporary read failure. */}
   finally{workspaceBusy=false;}
 }
 OAArticleLibrary($('articleAssetLibrary'),read,media,navigation.openLink,goToArticle);
 const articleStage=OAArticleWork($('articleWork'),read,media,navigation.openLink);
 const canvas=OADirectorCanvas(canvasCommit,selectCanvasNode,showCanvasNode,canvasPicture,engineName,
   playCanvasVideo,adoptCanvasVideo);
 const review=OADirectorMonitor({
   timelineOptions:{read,edit,send,canSend,uid:randomID,sound:navigation.sound,
     masterChunk:(selection,offset)=>tool('wce.ui.studio',{action:'media',...selection,asset:'wav',offset}),
     chunk:(scope,clip,offset)=>media('canvas_video_chunk',{...scope,delivery_id:clip.delivery_id,sha256:clip.sha256,offset}),
     exactFrame:(scope,clip,time_us)=>media('canvas_video_frame',{...scope,delivery_id:clip.delivery_id,sha256:clip.sha256,time_us}),
     frames:(scope,clip,start)=>media('canvas_video_frames',{...scope,delivery_id:clip.delivery_id,sha256:clip.sha256,start}),
     audioChunk:(scope,song,offset)=>tool('wce.ui.video.workspace',{action:'audio_chunk',project_id:scope.project_id,attempt_id:song.attempt_id,offset}),
     onExport:async(scope,result)=>{
       const payload=await read('deliveries',scope);
       if(!payload.cards.some(row=>row.id===result.delivery_id&&row.state==='ASSET_READY'))throw Error('DIRECTOR_EXPORT_NOT_VERIFIED');
       acceptDeliveries(scope,payload);
     }},

   chooseShot:async(scene_id,shot_id,revision_id)=>{
     const scope=workScope(),key=workKey(scope),focus={scene_id,shot_id,revision_id};
     const previous=preferredShots.get(key);
     // The row comes from this work's verified overview. Keep the local choice
     // even if project navigation supersedes its asynchronous context read.
     preferredShots.set(key,focus);
     try{return await readWork({work:scope.work_id,focus});}
     catch(problem){
       if(preferredShots.get(key)===focus){
         if(previous)preferredShots.set(key,previous);
         else preferredShots.delete(key);
       }
       if(mode==='monitor'&&pid()===scope.project_id&&present()?.id===scope.work_id)error(problem);
       return false;
     }
   },
   goCanvas:()=>{
     navigation.go('desk');
     canvas.focusShot(context?.shot_id);
   },
   openTasks:()=>navigation.go('tasks'),
   picture:async(target,thumbnail=false)=>{
     const response=await media('image',{...target,thumbnail});
     const slot=node('div');attachImage(slot,response,thumbnail);return slot.firstChild;
   },
   play:(slot,row,scope)=>playCanvasVideo(slot,row,scope,$('dmSourceStatus')),
 });
 return {open,close,view,canAttach,attach,guideContext,goToArticle,openShot};
}
'''
