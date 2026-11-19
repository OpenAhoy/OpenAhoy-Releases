"""Director desk in the native OpenAhoy media workspace."""
from .video_director_canvas_ui import HTML as CANVAS_HTML

HTML = '''
<section id="videoDirectorDesk" aria-labelledby="directorTitle" hidden>
 <header class="dd-toolbar">
  <h1 id="directorTitle" tabindex="-1">导演台</h1>
  <nav id="directorViews" aria-label="Jiusera工具">
   <button type="button" data-view="desk">分镜</button><button type="button" data-view="cards">提示词库</button>
   <button type="button" id="directorLibrary">任务与资产</button><button type="button" id="directorSettings">供应商设置</button>
  </nav>
 </header>
 <div class="dd-workbar" id="directorWorkbar">
  <div class="dd-projects">
   <label>项目 <select id="directorProject"></select></label>
   <label>作品 <select id="directorWork"></select></label>
   <button type="button" id="directorNewWork" class="primary">新建作品</button>
  </div>
  <div class="dd-actions">
   <button type="button" id="directorWorkSettings">作品约定</button>
   <button type="button" id="directorRefresh">刷新分镜</button>
  </div>
 </div>
 <div id="directorBoard" class="dd-board" hidden>
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
   ''' + CANVAS_HTML + '''
   <details class="dd-shot-shelf"><summary>本场镜头</summary><div id="directorShots" aria-label="本场镜头条"></div></details>
  </section>
  <aside class="dd-panel dd-inspector" aria-labelledby="directorShotTitle">
   <header><div id="directorShotStatus"></div><h2 id="directorShotTitle"></h2><p id="directorShotPurpose"></p></header>
   <figure id="directorStage"><div id="directorImageFrame"></div><figcaption id="directorCaption"></figcaption></figure>
   <nav id="directorTabs" aria-label="当前镜头">
    <button type="button" data-tab="text">文字</button><button type="button" data-tab="images">图片</button>
    <button type="button" data-tab="versions">版本</button><button type="button" data-tab="generation">生成配置</button>
    <button type="button" data-tab="whitebox">白模</button>
   </nav>
   <div id="directorInspector"></div>
   <details id="directorHandoff"><summary>交给 Codex 修改</summary>
    <label>要改什么<textarea id="directorInstruction" rows="2" placeholder="例如：把这一镜改成从门外侧跟，落幅保留人物与窗。"></textarea></label>
    <div class="dd-actions"><button type="button" id="directorSendText">交给 Codex 改文字</button>
      <button type="button" id="directorSendImage">交给 Codex 改图片</button><button type="button" id="directorCopyContext">复制上下文</button></div>
   </details>
  </aside>
 </div>
 <div id="directorEmpty" class="dd-panel dd-empty" hidden></div>
 <section id="directorCardPage" class="dd-card-page" aria-label="提示词库" hidden>
  <div class="dd-toolbar">
   <input type="search" id="directorCardQuery" aria-label="搜索提示词卡" placeholder="搜索镜头、焦距、构图或用途">
   <label>类型 <select id="directorCardCategory"><option value="">全部</option><option value="movement">运镜</option><option value="lens">焦距</option><option value="sequence">组合</option><option value="style">风格</option></select></label>
   <label>模型 <select id="directorCardModel"><option value="">全部</option><option value="ark">方舟</option><option value="minimax">MiniMax</option></select></label>
   <label>主体 <select id="directorCardSubjects"><option value="">全部</option><option value="1">单人或单主体</option><option value="2">双人</option></select></label>
  </div>
  <div class="dd-card-grid"><div id="directorCardList"></div><article id="directorCardDetail" class="dd-panel"></article></div>
 </section>
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

STYLE = '''
#videoDirectorDesk[hidden],#videoDirectorDesk [hidden]{display:none!important}
#videoDirectorDesk{display:flex;min-height:0;min-width:0;flex:1;flex-direction:column;gap:10px;overflow:auto;
 color:var(--ink);font-size:13px;scrollbar-gutter:stable}
#videoDirectorDesk :is(h1,h2,h3,p,figure){margin:0}
#videoDirectorDesk h2{font-size:15px;font-weight:650}
#videoDirectorDesk h3{font-size:13px}
#videoDirectorDesk :is(input,textarea,select){width:100%;min-width:0;margin:0}
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
.dd-empty{display:grid;gap:8px;align-content:start;justify-items:start;padding:18px}
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
 .dd-board{display:flex;flex-direction:column;flex:none}
 #directorStage{flex:0 0 clamp(165px,36vh,330px);min-height:0}
 .dd-inspector{overflow:visible}
 .dd-card-grid{display:grid;grid-template-columns:1fr}
 #directorCardList{max-height:180px}
}
'''

SCRIPT = r'''
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
     if(!/^HOST_/.test(problem?.message||''))pendingWrites.delete(key);
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
 const providers={ark:'火山方舟',cn:'MiniMax 中国站',global:'MiniMax 国际站',tokenhex:'Token Hex'};
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
 };
 let mode='',tab='text',data=null,context=null,sceneID=null,projects=[],modelData=null,cardData=null,cardID='';
 let engineDraft=null,engineDirty=false,workspaceTimer=null,workspaceBusy=false;
 const polled=new Map();
 const engineModes={...modeLabels,subject:'主体参考',workflow:'多图多音频工作流'};
 const engineChannel={...providers,relay:'AutoDL'};
 const engineName=engine=>engine.model+' · '+txt(engineChannel[engine.provider]||engine.provider||'渠道未记录');
 let watch=null,watchTimer=null,player=null,reading=0,visual=0,writing=false,dialogWrite=null;
 const pid=()=>project.value;
 const present=()=>data?.work;
 const currentScene=()=>present()?.scenes.find(row=>row.id===sceneID);
 const currentShot=()=>currentScene()?.shots.find(row=>row.id===context?.shot_id);
 const projectKey=()=>sessionStorage.getItem('OpenAhoy.director.project');
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
 async function readWork({work,focus,scene,keep=false}={}){
   const token=++reading, id=pid();
   if(!id){data=null;context=null;sceneID=null;render();return;}
   const requested=work||(keep?present()?.id:undefined);
   const result=await read('overview',{project_id:id,...(requested?{work_id:requested}:{})});
   if(token!==reading||!mode||pid()!==id)return;
   if(result.project_id!==id)throw Error('DIRECTOR_PROJECT_CHANGED');
   const active=result.work;
   const picked=focus||active?.selection;
   const sceneRow=active?.scenes.find(row=>row.id===(scene||picked?.scene_id))||active?.scenes[0];
   const target=picked?.shot_id&&picked.scene_id===sceneRow?.id?picked:preferred(sceneRow);
   let view=null;
   if(active&&target)view=await read('context',{project_id:id,work_id:active.id,...target});
   if(token!==reading||!mode||pid()!==id)return;
   if(view&&(view.project_id!==id||view.work_id!==active.id||view.scene_id!==target.scene_id||
             view.shot_id!==target.shot_id||view.revision.id!==target.revision_id))
      throw Error('DIRECTOR_REVISION_NOT_FOUND');
   data=result;sceneID=sceneRow?.id||null;context=view;
   render();if(mode==='cards'&&cardData)renderCards();
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
   if(mode!=='desk')return;
   $('directorWorkbar').hidden=false;
   board.hidden=!present();$('directorEmpty').hidden=!!present();
   canvas.render(present()?pid()+':'+present().id:'',present(),context?.shot_id);
   optionsFor(workSelect,(data?.works||[]).map(row=>[row.id,row.title,false]),present()?.id);
   workSelect.disabled=!data?.works.length;
   $('directorNewWork').disabled=!pid();
   $('directorCanvasEngine').disabled=!context;
   $('directorWorkSettings').disabled=!present();
   if(!present()){
     const hint=$('directorEmpty');hint.replaceChildren(
       label('h2',pid()?'创建第一部作品':'选择一个已登记的项目'),
       label('p',pid()?'建立作品、场次和镜头后即可制作分镜。':'先在项目与 Skills 中登记你的创作目录。'),
       button(pid()?'新建作品':'登记项目',pid()?()=>workDialog():navigation.project,'primary'));
     return;
   }
   const scene=currentScene();
   const scenes=present().scenes;
   const at=scenes.indexOf(scene);
   $('directorPrevious').disabled=at<=0;$('directorNext').disabled=at<0||at>=scenes.length-1;
   $('directorNewShot').disabled=!scene;
   OAUI.raw($('directorSceneTitle'),scene?scene.title:txt('还没有场次'));
   optionsFor($('directorSceneSelect'),scenes.map(row=>[row.id,row.title,false]),sceneID);
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
     stage.append(label('p',currentScene()?'创建本场第一个镜头':'先新建场次'));
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
   if(tab==='whitebox')renderWhitebox(rev,fresh);
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
 function renderImages(rev,fresh){
   const list=node('div','dd-asset-list'),images=structuredClone(rev.images);
   function draw(){
     list.replaceChildren();
     if(!images.length)list.append(label('p','这个修订还没有图片。'));
     images.forEach((row,index)=>{
       const part=node('div','dd-asset-row'),left=node('div'),right=node('div','dd-actions');
       left.append(raw('strong',row.file.path),label('p',roles[row.role]));
       if(fresh){
         const choice=select(left,'图片用途',Object.entries(roles),row.role);
         choice.onchange=()=>{row.role=choice.value;};
         if(index>0)right.append(button('上移',()=>{[images[index-1],images[index]]=[images[index],images[index-1]];draw();}));
         if(index+1<images.length)right.append(button('下移',()=>{[images[index+1],images[index]]=[images[index],images[index+1]];draw();}));
         right.append(button('从此版移除',()=>{images.splice(index,1);draw();}));
       }
       const stored=rev.images.findIndex(item=>item.file.path===row.file.path&&item.file.sha256===row.file.sha256);
       if(stored>=0)right.prepend(button('预览',()=>renderImage(stored)));
       part.append(left,right);list.append(part);
     });
   }
   draw();inspector.append(list);
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
       images.push({role:role.value,file:spec});file.path.value='';file.sha.value='';draw();add.open=false;
     }catch(problem){error(problem);}
     finally{addButton.disabled=false;}
   });
   form.append(addButton);
   add.append(form);inspector.append(add,button('保存图片修订',()=>revise({images}),'primary'));
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
   picker.append(refresh,status,cards);
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
       CHECK_UNAVAILABLE:'Token Hex 目录暂不可读'}[modelData.tokenhex_catalog?.state]||'');
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
     const inputArea=node('div','dd-form'),connection=label('p',''),hint=label('p','');
     const rowName=label('h3','');
     let originals=[],sourcePending=false,localFields=[];
     pane.append(rowName,connection,cols,inputArea,sourceArea,urls,hint);
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
     function outputs(){
       const row=modelRow(),active=profile(),sizes=Object.keys(active?.resolutions||{});
       optionsFor(resolution,[...(active?.optional_output?[['','服务商默认']]:[]),...sizes.map(value=>[value,value,false])],resolution.value||config.resolution);
       optionsFor(ratio,(active?.ratios||[]).map(value=>[value,value==='adaptive'?'自适应':value,value==='adaptive']),ratio.value||config.ratio);
       show(resolution,!!sizes.length);show(ratio,!!active?.ratios.length);show(audio,!!active?.audio);
       if(!active?.audio)audio.checked=false;
       durations();localInputs();
       sourceArea.hidden=!active?.source;direction.parentElement.hidden=!active?.direction;
       if(active?.source)void addSources();
       show(imagesUrl,active?.url_inputs==='relay');show(audioUrl,active?.url_inputs==='relay');
       show(subjectUrl,active?.url_inputs==='subject');
       urls.hidden=!active?.url_inputs;
       OAUI.raw(rowName,row?engineName({provider:provider.value,model:row.id}):'');
       OAUI.set(hint,active?.url_inputs?'使用已有公开链接。链接和模型账号的访问尚未核验。':'');
       OAUI.set(connection,provider.value==='tokenhex'&&row?.visibility!=='VISIBLE'?'Token Hex 型号可见性待核':
         catalog.connections[provider.value]==='CONFIGURED'?'本机已配置连接':'本机连接未配置或暂不可读');
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
     provider.onchange=()=>modelsForProvider();pickedModel.onchange=()=>modes();kind.onchange=outputs;resolution.onchange=durations;
     modelsForProvider(draft?.model);
     const prompt=textarea(pane,'完整生成提示词',rev.prompt,5);
     for(const control of pane.querySelectorAll('input,textarea,select'))if(!fresh)control.disabled=true;
     const split=value=>value.split(/\r?\n/).map(line=>line.trim()).filter(Boolean);
     if(fresh)pane.append(button('保存提示词与配置',async()=>{
       const active=profile();
       if(!active)return;
       const link=originals.find(row=>row.generation_attempt_id===source.value);
       const request={provider:provider.value,model:pickedModel.value,mode:kind.value};
       if(duration.value!=='')request.duration=Number(duration.value);
       if(resolution.value)request.resolution=resolution.value;
       if(active.ratios.length&&ratio.value)request.ratio=ratio.value;
       if(active.audio)request.audio=audio.checked;
       if(active.source&&link)request.source={project_id:pid(),attempt_id:link.generation_attempt_id,
         sha256:link.asset.sha256,...(asset.value.trim()?{reference_asset:asset.value.trim()}:{})};
       if(active.direction)request.direction=direction.value;
       if(active.url_inputs==='subject'&&subjectUrl.value.trim())request.subject_image_url=subjectUrl.value.trim();
       if(active.url_inputs==='relay'){
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
     if(fresh&&rev.configuration)actions.append(button('交给 Codex 生成',()=>handoffGeneration(key)));
     if(!fresh)actions.append(button('查看最新修订',()=>selectShot(context.scene_id,context.shot_id,context.head_revision)));
     pane.append(actions);inspector.replaceChildren(pane);
   }catch(problem){if(visible(key)&&tab==='generation'){inspector.replaceChildren(label('p','模型目录暂不可读。'));error(problem);}}
 }
 async function handoffGeneration(key){
   const target=exact();
   try{
     const result=await read('preflight',target);
     if(!visible(key))return;
     const route={ark:'video.ark.generation.submit',cn:'video.minimax.generation.submit',
       global:'video.minimax.generation.submit',relay:'video.relay.generation.submit',tokenhex:'video.tokenhex.generation.submit'}[result.request.provider];
     const instruction='为这个精确镜头使用已保存的视频引擎。镜头定位 '+JSON.stringify(target)+
       '。先用 video.director.read 的 preflight 读取此修订，核对当前视频生成授权，选择稳定且唯一的 generation_attempt_id。'+
       '用 video.director.edit action=track_generation，传同一个 attempt_id、精确镜头定位和新的 operation_id。'+
       '保持所选型号和渠道，经 '+route+' 提交一次。'
       +(result.request.provider==='tokenhex'?'遵循现有 Token Hex 工具域，使用项目相对 paths 及 audio 配置，省略原生配置不接收的 ratio。':'')+
       '查询原状态，保留聊天内原成片播放交付。'+
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
     return write('create_work',{project_id:projectID,fields:values},result=>readWork({work:result.work_id}));
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
   return '请按 OpenAhoy 随包 video-director Skill 接手当前分镜。'+task+'\n'
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
   mode=target;
   for(const pick of $('directorViews').querySelectorAll('[data-view]'))
     pick.setAttribute('aria-pressed',String(pick.dataset.view===mode));
   $('directorCardPage').hidden=mode!=='cards';
   $('directorWorkbar').hidden=mode!=='desk';
   if(mode==='cards'){
     canvas.suspend();board.hidden=true;$('directorEmpty').hidden=true;clearPreview();stopWatch();
     void loadCards().catch(error);
   }else{
     render();
   }
 }
 async function open(target='desk'){
   root.hidden=false;
   view(target);
   if(!workspaceTimer)workspaceTimer=setInterval(syncWorkspace,2600);
   $('directorTitle').focus();
   const token=++reading;
   try{
     const {projects:list}=await read('projects');
     if(token!==reading||!mode)return;
     projects=list;
     let stored='';
     try{stored=projectKey()||'';}catch(_){}
     optionsFor(project,projects.map(row=>[row.id,row.name,false]),project.value||stored);
     project.disabled=!projects.length;
     await readWork();
   }catch(problem){if(mode)error(problem);}
 }
 function close(){
   canvas.suspend();
   clearInterval(workspaceTimer);workspaceTimer=null;polled.clear();engineDraft=null;engineDirty=false;
   mode='';root.hidden=true;reading++;visual++;clearPreview();stopWatch();say('');
   if($('directorCanvasPreview').open)$('directorCanvasPreview').close();
   if($('directorDialog').open)$('directorDialog').close();
   $('directorCopy').hidden=true;
 }
 project.onchange=()=>{
   stopWatch();engineDraft=null;engineDirty=false;data=null;context=null;sceneID=null;render();
   try{sessionStorage.setItem('OpenAhoy.director.project',pid());}catch(_){}
   void readWork().catch(error);
 };
 workSelect.onchange=()=>{
   stopWatch();engineDraft=null;engineDirty=false;const chosen=workSelect.value;
   void write('select_work',{project_id:pid(),work_id:chosen},()=>readWork({work:chosen}),'');
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
 $('directorNewWork').onclick=()=>workDialog();
 $('directorWorkSettings').onclick=()=>workDialog(present());
 $('directorNewScene').onclick=()=>entityDialog('scene');
 $('directorNewShot').onclick=()=>entityDialog('shot');
 $('directorRefresh').onclick=async()=>{if(writing)return;stopWatch();engineDirty=false;engineDraft=null;try{await readWork({keep:true});say('已刷新分镜。');}catch(problem){error(problem);}};
 $('directorSendText').onclick=()=>askCodex('text');
 $('directorSendImage').onclick=()=>askCodex('image');
 $('directorCopyContext').onclick=()=>askCodex('text',true);
 $('directorLibrary').onclick=navigation.library;
 $('directorSettings').onclick=navigation.settings;
 $('directorViews').querySelectorAll('[data-view]').forEach(pick=>pick.onclick=()=>view(pick.dataset.view));
 $('directorTabs').querySelectorAll('button').forEach(pick=>pick.onclick=()=>{tab=pick.dataset.tab;renderInspector();});
 for(const id of ['directorCardQuery','directorCardCategory','directorCardSubjects','directorCardModel'])$(id).oninput=renderCards;
 function shotLink(){return context?.shot_id?{shot_id:context.shot_id}:{};}
 function canAttach(row){return mode==='desk'&&!!present()&&row.project===pid()&&!!row.asset?.sha256;}
 async function attach(row){
   if(!canAttach(row))return false;
   const result=await canvas.add({kind:'asset',title:row.title.slice(0,240),...shotLink(),
      asset:{family:row.family,media_kind:row.kind,project_id:row.project,attempt_id:row.attempt,sha256:row.asset.sha256}});
   if(result)navigation.closeLibrary();
   return result;
 }
 async function canvasCommit(action,args,saved){
   const [project_id,work_id]=saved.key.split(':');
   const current=()=>!!mode&&pid()===project_id&&data?.project_id===project_id&&present()?.id===work_id;
   try{
     const result=await edit(action,{project_id,work_id,expected_canvas_version:saved.version,...args});
     if(result.state!=='SAVED'||result.project_id!==project_id||result.work_id!==work_id||
        result.canvas_version!==saved.version+1)throw Error('DIRECTOR_SAVE_NOT_VERIFIED');
     saved.version=result.canvas_version;
     if(current()){
       const value=exact();
       const focus=value&&{scene_id:value.scene_id,shot_id:value.shot_id,revision_id:value.revision_id};
       await readWork({work:work_id,focus});
       say(action==='canvas_view'?'画布视图已保存。':'画布已保存。');
     }
     return true;
   }catch(problem){
     if(current()){
       error(problem);
       await readWork({work:work_id}).catch(()=>{});
     }
     return false;
   }
 }
 async function canvasPicture(row){
   const response=row.kind==='shot'?await media('image',{...workScope(),scene_id:row.scene,
       shot_id:row.id,revision_id:row.cover,thumbnail:true}):
       await media('canvas_image',{...workScope(),node_id:row.id,thumbnail:true});
   const slot=node('div');attachImage(slot,response,true);return slot.firstChild;
 }
 function playCanvasVideo(slot,row){
   const args={...workScope(),delivery_id:row.id,sha256:(row.asset||row).sha256};
   return OAVideoPreview(slot,row.asset||row,{
     lazy:true,
     chunk:offset=>media('canvas_video_chunk',{...args,offset}),
     frames:start=>media('canvas_video_frames',{...args,start}),
   });
 }
 async function adoptCanvasVideo(row){
   const scope=workScope(),key=scope.project_id+':'+scope.work_id;
   const args={...scope,scene_id:row.scene_id,shot_id:row.shot_id,candidate_id:row.id,sha256:row.asset.sha256};
   if(row.adopted_candidate_id)args.expected_candidate_id=row.adopted_candidate_id;
   return write('adopt_video',args,async result=>{
     if(result.adopted_video?.candidate_id!==row.id||result.adopted_video.sha256!==row.asset.sha256)
       throw Error('DIRECTOR_SAVE_NOT_VERIFIED');
     const payload=await read('deliveries',scope);
     if(payload.project_id!==scope.project_id||payload.work_id!==scope.work_id||
          !payload.cards.some(item=>item.id===row.id&&item.adopted))throw Error('DIRECTOR_SAVE_NOT_VERIFIED');
     canvas.setDeliveries(key,payload.cards,payload.version);
   },'已采用此视频。');
 }
 async function selectCanvasNode(row){
   await selectShot(row.scene,row.shot_id||row.id,row.revision);
   if(row.kind==='engine'&&context?.shot_id===row.shot_id){tab='generation';renderInspector();}
 }
 async function showCanvasNode(row){
   if(row.kind==='asset'){
     const asset=row.asset;
     navigation.asset({family:asset.family,project:asset.project_id,attempt:asset.attempt_id,sha256:asset.sha256});
     return;
   }
   const preview=$('directorCanvasPreview'),body=$('directorCanvasPreviewBody');
   OAUI.raw($('directorCanvasPreviewTitle'),row.title);
   const editNote=$('directorCanvasNoteEdit');
   editNote.hidden=row.kind!=='note';
   editNote.onclick=()=>{preview.close();noteDialog(row);};
   body.replaceChildren(row.kind==='note'?raw('p',row.text):label('p','正在读取图片…'));
   preview.showModal();
   if(row.kind==='image'){
     try{
       const rendered=await media('canvas_image',{...workScope(),node_id:row.id});
       if(preview.open)attachImage(body,rendered);
     }catch(problem){if(preview.open){body.replaceChildren(label('p','当前图片不可用'));error(problem);}}
   }
 }
 async function syncWorkspace(){
   if(mode!=='desk'||!present()||document.hidden||workspaceBusy)return;
   const scope=workScope(),key=scope.project_id+':'+scope.work_id,shot=exact();
   const current=()=>mode==='desk'&&pid()===scope.project_id&&present()?.id===scope.work_id;
   workspaceBusy=true;
   try{
     const payload=await read('deliveries',scope);
     if(!current()||payload.project_id!==scope.project_id||payload.work_id!==scope.work_id)return;
     canvas.setDeliveries(key,payload.cards,payload.version);
     if(shot&&!writing&&!watch&&context?.head_revision===shot.revision_id){
       const observed=await read('context',shot);
       if(current()&&scopeKey()===JSON.stringify(shot)&&observed.head_revision!==shot.revision_id){
         if(engineDirty){say('Codex 已更新这个镜头。刷新可查看最新修订。');}
         else await readWork({work:scope.work_id,focus:{scene_id:shot.scene_id,shot_id:shot.shot_id,
            revision_id:observed.head_revision}});
       }
     }
     if(!current())return;
     const next=payload.cards.find(row=>row.pollable&&Date.now()-(polled.get(key+row.attempt_id)||0)>=18000);
     if(next){
       polled.set(key+next.attempt_id,Date.now());
       const updated=await tool('video.director.edit',{action:'poll_delivery',...scope,attempt_id:next.attempt_id});
       if(current()&&updated.project_id===scope.project_id&&updated.work_id===scope.work_id)
         canvas.setDeliveries(key,updated.cards,updated.version);
     }
   }catch(_){/* Keep the last verified visible cards across a temporary read failure. */}
   finally{workspaceBusy=false;}
 }
 const canvas=OADirectorCanvas(canvasCommit,selectCanvasNode,showCanvasNode,canvasPicture,engineName,
   playCanvasVideo,adoptCanvasVideo);
 return {open,close,canAttach,attach};
}
'''
