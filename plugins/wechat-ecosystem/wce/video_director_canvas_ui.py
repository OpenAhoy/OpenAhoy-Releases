"""The work's single canvas, embedded in the existing OpenAhoy app."""

HTML = '''
<section class="dd-canvas-area" aria-label="导演画布">
 <div class="dd-canvas-toolbar">
  <div class="dd-actions">
   <button id="directorCanvasNote" type="button">文字卡</button>
   <button id="directorCanvasImage" type="button">添加图片</button>
   <button id="directorCanvasAssets" type="button">媒体资产</button>
   <button id="directorCanvasEngine" type="button">选择视频引擎</button>
   <button id="directorCanvasRemove" type="button" hidden>移出画布</button>
  </div>
  <div class="dd-actions" aria-label="画布缩放">
   <button id="directorCanvasOut" type="button" aria-label="缩小画布">−</button>
   <button id="directorCanvasReset" type="button" aria-label="复位画布">100%</button>
   <button id="directorCanvasIn" type="button" aria-label="放大画布">＋</button>
   <button id="directorCanvasFit" type="button">适配画布</button>
  </div>
 </div>
 <div id="directorCanvas" aria-label="混合媒体画布" tabindex="0">
   <div id="directorCanvasPlane"><canvas id="directorCanvasEdges" hidden></canvas><div id="directorCanvasNodes"></div></div>
   <p id="directorCanvasEmpty">新建镜头，或把图片和媒体放到画布上。</p>
 </div>
</section>
<dialog id="directorCanvasPreview" aria-labelledby="directorCanvasPreviewTitle">
 <header class="dd-heading"><h2 id="directorCanvasPreviewTitle"></h2><div class="dd-actions"><button id="directorCanvasNoteEdit" type="button" hidden>编辑文字卡</button><button id="directorCanvasPreviewClose" type="button">关闭</button></div></header>
 <div id="directorCanvasPreviewBody"></div>
</dialog>
'''

STYLE = '''
.dd-engine-grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(180px,1fr));grid-auto-rows:max-content;gap:6px;max-height:50dvh;overflow:auto}
#directorDialog .dd-engine-grid .dd-engine-option{display:grid;align-content:start;gap:3px;height:auto;min-height:76px;
 text-align:left;white-space:normal;overflow-wrap:anywhere;padding:7px 9px}
.dd-engine-option small,.dd-engine-option span{font-size:11px;color:var(--muted)}
#directorCanvasPreviewBody video{display:block;width:100%;max-height:67dvh}

#mediaStudio #videoDirectorDesk{min-height:0;flex:1}
#videoDirectorDesk .dd-board{grid-template-columns:minmax(118px,170px) minmax(0,1fr) minmax(224px,325px)}
#videoDirectorDesk .dd-view{align-self:stretch}
.dd-canvas-area{display:flex;flex:1;flex-direction:column;gap:5px;min-width:0;min-height:220px}
.dd-canvas-toolbar{display:flex;justify-content:space-between;align-items:center;gap:6px;flex-wrap:wrap}
#directorCanvas{--dd-grid:color-mix(in srgb,var(--muted) 28%,transparent);--dd-step:18px;
 position:relative;isolation:isolate;flex:1;min-width:0;min-height:255px;
 overflow:hidden;touch-action:none;cursor:grab;border:1px solid var(--line);border-radius:12px;
 background-color:var(--bg);background-image:radial-gradient(var(--dd-grid) 1px, transparent 1px);
 background-size:var(--dd-step) var(--dd-step)}
#directorCanvas:focus-visible{outline:2px solid var(--accent);outline-offset:2px}
#directorCanvas[data-dragging=true]{cursor:grabbing}
#directorCanvasPlane{position:absolute;inset:0;transform-origin:0 0;pointer-events:none}
#directorCanvasEdges{position:absolute;pointer-events:none;color:var(--accent)}
#directorCanvasEmpty{position:absolute;left:16px;bottom:12px;color:var(--muted);pointer-events:none}
.dd-canvas-card{position:absolute;display:flex;flex-direction:column;width:164px;min-height:104px;
 overflow:hidden;border:1px solid var(--line);border-radius:11px;color:var(--text);background:var(--surface);
 box-shadow:0 4px 16px #0002;pointer-events:auto;user-select:none}
.dd-canvas-card[data-current=true]{border-color:var(--accent);box-shadow:0 0 0 1px var(--accent)}
.dd-canvas-card[data-delivery-kind]{width:296px}
#videoDirectorDesk .dd-canvas-card .dd-canvas-handle{border:0;box-shadow:none;background:transparent;
 color:inherit;width:100%;text-align:left;min-height:104px;display:flex;flex-direction:column;align-items:stretch;
 padding:8px 10px;gap:5px;overflow:hidden;cursor:inherit}
#videoDirectorDesk .dd-canvas-card:is([data-delivery-kind],[data-kind=engine]) .dd-canvas-handle{min-height:0}
.dd-canvas-media{padding:0 8px 8px;display:grid;grid-template-columns:minmax(0,1fr);gap:5px;cursor:auto}
.dd-canvas-video-tools{display:flex;align-items:center;gap:6px;min-width:0}
#videoDirectorDesk .dd-canvas-video-tools select{min-width:0;flex:1;min-height:28px;text-overflow:ellipsis}
#videoDirectorDesk .dd-canvas-video-tools button,#videoDirectorDesk .dd-canvas-media .oa-inline-video-player button{min-height:28px;white-space:nowrap;width:auto}
.dd-canvas-media .oa-frame-controls{display:grid;grid-template-columns:auto 1fr;gap:2px 7px}
.dd-canvas-media .oa-frame-controls output{grid-column:2;grid-row:1;text-align:right}
.dd-canvas-media .oa-frame-controls input{grid-column:1/-1;grid-row:2;width:100%;margin:0}
.dd-canvas-media [role=status]:empty{display:none}
.dd-canvas-adopted{margin:0;font-size:11px;color:var(--muted);white-space:nowrap}
.dd-canvas-card button span,.dd-canvas-card button strong{overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.dd-canvas-card .dd-canvas-kind{align-self:flex-start;max-width:100%;padding:2px 6px;border-radius:5px;
 font-size:10px;font-weight:700;background:color-mix(in srgb,var(--dd-tone) 22%,var(--surface));color:var(--text)}
.dd-canvas-card[data-kind=shot]{--dd-tone:#789aff}.dd-canvas-card[data-kind=image]{--dd-tone:#54b896}
.dd-canvas-card[data-kind=video]{--dd-tone:#9c80df}.dd-canvas-card[data-kind=audio]{--dd-tone:#df9e51}
.dd-canvas-card[data-kind=gif]{--dd-tone:#d8759e}.dd-canvas-card[data-kind=note]{--dd-tone:#abb0bf}
.dd-canvas-card[data-kind=engine]{--dd-tone:#518dab}
.dd-canvas-card .dd-canvas-handle img{width:100%;height:60px;object-fit:cover;border-radius:5px}
.dd-canvas-card .dd-canvas-handle div:empty{display:none}
.dd-canvas-card small{color:var(--muted);overflow:hidden;white-space:nowrap;text-overflow:ellipsis}
#directorCanvasPreview{width:min(860px,calc(100% - 24px));max-height:90dvh}
#directorCanvasPreviewBody{display:grid;place-items:center;padding:9px 0;overflow:auto}
#directorCanvasPreviewBody p{white-space:pre-wrap;overflow-wrap:anywhere;width:100%}
#directorCanvasPreviewBody img{display:block;max-width:100%;max-height:67dvh;object-fit:contain}
#directorMediaDialog{width:min(1060px,calc(100% - 24px));height:min(790px,calc(100% - 24px));max-height:94dvh;
 padding:12px;overflow:hidden;border:1px solid var(--line);background:var(--surface);color:var(--text)}
#directorMediaDialog[open]{display:flex;flex-direction:column;gap:8px}
#directorMediaDialog::backdrop,#directorCanvasPreview::backdrop{background:#10142180}
#directorMediaDialog #mediaMonitor{min-height:0;overflow:auto;flex:1}
#directorMediaDialog #monitorFilters{display:none}
#directorMediaDialog #monitorProviders{overflow:auto;min-height:0}
#videoDirectorDesk .dd-inspector #directorStage{height:130px;min-height:0;margin:8px 0 0}
#videoDirectorDesk .dd-inspector #directorStage:has(#directorImageFrame:empty){display:none}
#videoDirectorDesk .dd-shot-shelf>summary{color:var(--muted);font-size:12px;cursor:pointer;padding:4px 2px}
@media(max-width:1100px){
 #videoDirectorDesk .dd-board{grid-template-columns:minmax(0,1fr) minmax(190px,260px)}
 #videoDirectorDesk .dd-scenes{grid-column:1/-1}
 #videoDirectorDesk .dd-scenes #directorSceneList{display:none}
 #videoDirectorDesk .dd-scenes .dd-scene-select{display:flex}
}
@media(max-width:630px){
 #videoDirectorDesk .dd-board{display:flex;flex-direction:column;align-items:stretch}
 #directorCanvas{min-height:360px}
 #directorMediaDialog{width:calc(100% - 12px);height:calc(100% - 12px);padding:8px}
}
'''

SCRIPT = r'''
function OADirectorCanvas(commit, select, show, picture, engineName, playVideo, adopt){
 const $=id=>document.getElementById(id);
 const viewport=$('directorCanvas'),plane=$('directorCanvasPlane'),nodes=$('directorCanvasNodes');
 const edge=$('directorCanvasEdges'),empty=$('directorCanvasEmpty');
 const actions={remove:$('directorCanvasRemove'),reset:$('directorCanvasReset')};
 const labels={shot:'镜头',engine:'视频引擎',note:'文字卡',image:'图片',video:'视频',gif:'动图',audio:'音频'};
 const states={AWAITING_RECEIPT:'等待原任务回执',SUBMITTED:'已提交',QUEUED:'排队中',RUNNING:'生成中',
   SAVE_PENDING:'正在取件',ASSET_READY:'可播放',SUBMIT_UNKNOWN:'提交结果未知',SUBMIT_REJECTED:'提交被拒绝',
   FAILED:'生成失败',EXPIRED:'已过期',CANCELLED:'已取消',UNAVAILABLE:'原素材不可读',UNKNOWN:'状态未知'};
 const element=(tag,style)=>{const node=document.createElement(tag);if(style)node.className=style;return node;};
 let scope={key:'',version:0,moves:new Map()},selected='',work=null,deliveries=[],focused='';
 let view={x:28,y:28,scale:100},gesture=null,timer=null,pending=Promise.resolve();
 let cards=new Map(),previews={};
 const clamp=(value,low,high)=>Math.max(low,Math.min(high,value));
 const minZoom=10;
 const point=value=>clamp(Math.round(value),-1000000,1000000);
 const stateText=row=>states[row.state]||states.UNKNOWN;
 const previewStore=key=>'OpenAhoy.director.candidates.'+key;
 function transform(){
   plane.style.transform='translate('+view.x+'px,'+view.y+'px) scale('+(view.scale/100)+')';
   viewport.style.setProperty('--dd-step',Math.max(8,18*view.scale/100)+'px');
   viewport.style.backgroundPosition=view.x+'px '+view.y+'px';
   OAUI.raw(actions.reset,view.scale+'%');
 }
 function queue(action,args){
   const captured=scope;
   pending=pending.then(()=>captured.key?commit(action,args,captured):false).catch(()=>false);
   return pending;
 }
 function setView(next,save=true){
   view={x:point(next.x),y:point(next.y),scale:clamp(Math.round(next.scale),minZoom,250)};transform();
   if(save){scope.viewport=view;clearTimeout(timer);timer=setTimeout(flush,200);}
 }
 function flush(){
   if(timer===null)return pending;
   clearTimeout(timer);timer=null;
   const owner=scope,viewport=owner.viewport;
   return queue('canvas_view',{viewport}).then(result=>{
     if(owner.viewport===viewport){delete owner.viewport;if(!result&&owner===scope)render(owner.key,work,focused);}
     return result;
   });
 }
 function zoom(by,atX=viewport.clientWidth/2,atY=viewport.clientHeight/2){
   const scale=clamp(view.scale+by,minZoom,250),ratio=scale/view.scale;
   setView({x:atX-(atX-view.x)*ratio,y:atY-(atY-view.y)*ratio,scale});
 }
 function dimensions(card){
   return {width:card.element.offsetWidth,height:card.element.offsetHeight};
 }
 function fit(){
   if(!cards.size){setView({x:28,y:28,scale:100});return;}
   const rows=Array.from(cards.values(),card=>({...card.position,...dimensions(card)}));
   const left=Math.min(...rows.map(p=>p.x)),top=Math.min(...rows.map(p=>p.y));
   const width=Math.max(...rows.map(p=>p.x+p.width))-left,height=Math.max(...rows.map(p=>p.y+p.height))-top;
   const scale=clamp(Math.floor(100*Math.min((viewport.clientWidth-32)/width,(viewport.clientHeight-32)/height)),minZoom,100);
   setView({x:(viewport.clientWidth-width*scale/100)/2-left*scale/100,
            y:(viewport.clientHeight-height*scale/100)/2-top*scale/100,scale});
 }
 function location(){
   const x=point((12-view.x)*100/view.scale),y=point((12-view.y)*100/view.scale);
   const columns=Math.max(1,Math.floor((viewport.clientWidth-18)*100/view.scale/184));
   const available=Array.from(cards.values(),card=>({...card.position,...dimensions(card)}));
   for(let i=0;i<=available.length*4;i++){
     const next={x:point(x+(i%columns)*184),y:point(y+Math.floor(i/columns)*144)};
     if(!available.some(p=>p.x<next.x+172&&p.x+p.width+8>next.x&&p.y<next.y+128&&p.y+p.height+8>next.y))return next;
   }
   return {x,y};
 }
 function refreshSelection(shot){
   actions.remove.hidden=!work?.canvas.nodes[selected];
   for(const [id,card] of cards)card.element.dataset.current=String(id===(selected||shot));
 }
 function collect(model){
   const rows=[],extras=[];let serial=0;
   for(const scene of model.scenes){
     for(const shot of scene.shots){
       const revision=shot.adopted_revision||shot.head_revision;
       const meta=shot.revisions.find(row=>row.id===revision);
       rows.push({kind:'shot',id:shot.id,title:meta.title,scene:scene.id,revision,
                  cover:shot.cover_revision,engine:shot.engine,position:{x:(serial%3)*184,y:Math.floor(serial/3)*140}});
       if(shot.engine)extras.push({kind:'engine',id:shot.engine_node_id,title:engineName(shot.engine),
         scene:scene.id,shot_id:shot.id,revision:shot.head_revision,engine:shot.engine});
       serial++;
     }
   }
   rows.push(...Object.values(model.canvas.nodes));
   const grouped=new Map();
   for(const response of deliveries){
     if(response.kind==='work_video'){extras.push(response);continue;}
     const shot=rows.find(row=>row.kind==='shot'&&row.id===response.shot_id&&row.scene===response.scene_id);
     if(!shot)continue;
     if(!grouped.has(response.node_id)){
       const group={id:response.node_id,kind:'shot_video',title:shot.title,scene:shot.scene,shot_id:shot.id,candidates:[]};
       grouped.set(response.node_id,group);extras.push(group);
     }
     grouped.get(response.node_id).candidates.push(response);
   }
   let bottom=Math.ceil(serial/3)*144;
   for(const row of rows){
     const p=model.canvas.positions[row.id]||row.position;
     if(p)bottom=Math.max(bottom,p.y+144);
   }
   const occupied=rows.map(row=>{
     const position=model.canvas.positions[row.id]||row.position;
     return {...position,width:164,height:128};
   });
   const assignments=new Map();
   for(const row of extras){
     const saved=model.canvas.positions[row.id]||cards.get(row.id)?.defaultPosition;
     if(saved){
       assignments.set(row.id,saved);
       const measured=cards.get(row.id);
       occupied.push({...saved,width:296,height:Math.max(320,measured?.element.offsetHeight||0)});
     }
   }
   let index=0;
   const columns=Math.max(1,Math.min(3,Math.floor(viewport.clientWidth/316)));
   for(const row of extras){
     let position=assignments.get(row.id);
     if(!position){
       do{
         position={x:(index%columns)*316,y:bottom+Math.floor(index/columns)*340};
         index++;
       }while(occupied.some(p=>p.x<position.x+300&&p.x+p.width>position.x&&p.y<position.y+320&&p.y+p.height>position.y));
       occupied.push({...position,width:296,height:320});
     }
     rows.push({...row,position});
   }
   return rows;
 }
 function redrawLinks(){
   const linked=[...cards.values()].filter(card=>cards.has(card.row.shot_id));
   edge.hidden=!linked.length;
   if(!linked.length)return;
   const center=card=>({x:card.position.x+card.element.offsetWidth/2,y:card.position.y+card.handle.offsetHeight/2});
   const lines=linked.map(card=>[center(cards.get(card.row.shot_id)),center(card)]);
   const pts=lines.flat();
   const x=Math.min(...pts.map(p=>p.x))-3,y=Math.min(...pts.map(p=>p.y))-3;
   const width=Math.max(...pts.map(p=>p.x))+3-x,height=Math.max(...pts.map(p=>p.y))+3-y;
   edge.style.left=x+'px';edge.style.top=y+'px';
   const resolution=Math.min(1,1800/Math.max(width,height));
   edge.width=Math.max(1,Math.ceil(width*resolution));edge.height=Math.max(1,Math.ceil(height*resolution));
   edge.style.width=width+'px';edge.style.height=height+'px';
   const line=edge.getContext('2d');line.strokeStyle=getComputedStyle(edge).color;
   line.lineWidth=2*resolution;line.setLineDash([6*resolution,4*resolution]);
   for(const [source,target] of lines){
     line.beginPath();line.moveTo((source.x-x)*resolution,(source.y-y)*resolution);
     line.lineTo((target.x-x)*resolution,(target.y-y)*resolution);line.stroke();
   }
 }
 function position(card,value){
   card.position=value;card.element.style.left=value.x+'px';card.element.style.top=value.y+'px';
 }
 function move(card,value){
   const owner=scope,id=card.row.id;
   owner.moves.set(id,value);position(card,value);redrawLinks();flush();
   void queue('canvas_move',{node_id:id,position:value}).then(result=>{
     if(owner.moves.get(id)!==value)return;
     owner.moves.delete(id);
     if(!result&&owner===scope)render(owner.key,work,focused);
   });
 }
 function activate(card){
   const row=card.row;
   selected=row.id;refreshSelection(focused);
   if(row.kind==='shot'||row.kind==='engine')void select(row);
   else if(!card.delivery)void show(row);
 }
 function newCard(row){
   const wrapper=element('article','dd-canvas-card'),handle=element('button','dd-canvas-handle');
   const badge=element('span','dd-canvas-kind'),name=element('strong'),caption=element('small'),pictureSlot=element('div');
   handle.type='button';handle.append(badge,name,caption,pictureSlot);wrapper.append(handle);
   const card={element:wrapper,handle,badge,name,caption,pictureSlot,row};
   handle.onclick=()=>activate(card);
   handle.onkeydown=event=>{
     const offset={ArrowLeft:[-12,0],ArrowUp:[0,-12],ArrowRight:[12,0],ArrowDown:[0,12]}[event.key];
     if(!offset)return;
     event.preventDefault();
     move(card,{x:point(card.position.x+offset[0]),y:point(card.position.y+offset[1])});
   };
   nodes.append(wrapper);return card;
 }
 function videoTools(card){
   const group=element('div','dd-canvas-media'),tools=element('div','dd-canvas-video-tools');
   const picker=element('select'),use=element('button'),badge=element('p','dd-canvas-adopted'),slot=element('div');
   group.dataset.canvasControls='true';use.type='button';
   OAUI.attr(picker,'aria-label','镜头视频候选');OAUI.set(use,'采用此视频');
   tools.append(picker,use,badge);group.append(tools,slot);card.element.append(group);
   card.tools={tools,picker,use,badge,slot};
   picker.onchange=()=>{
     previews[card.row.id]=picker.value;
     try{sessionStorage.setItem(previewStore(scope.key),JSON.stringify(previews));}catch(_){}
     updateVideo(card);redrawLinks();
   };
   use.onclick=async()=>{
     const active=card.active;
     if(!active?.asset||active.adopted||use.disabled)return;
     use.disabled=true;
     try{await adopt(active);}
     finally{if(card.element.isConnected){use.disabled=false;updateVideo(card);}}
   };
 }
 function updateVideo(card){
   if(!card.tools)videoTools(card);
   const {tools,picker,use,badge,slot}=card.tools,row=card.row;
   const candidates=row.candidates||[row];
   let active=candidates.find(item=>item.id===previews[row.id])||
     candidates.find(item=>item.adopted)||candidates.find(item=>item.state==='ASSET_READY')||candidates[0];
   if(card.active&&card.active.id!==active.id&&!previews[row.id]){
     active=candidates.find(item=>item.id===card.active.id)||active;
   }
   card.active=active;
   const options=candidates.map((item,index)=>[item.id,index+1,item.engine?engineName(item.engine):'',
     stateText(item),!!item.adopted]);
   const signature=JSON.stringify(options);
   if(card.options!==signature){
     picker.replaceChildren(...options.map(([id,index,engine,state,adopted])=>{
       const option=element('option');option.value=id;
       OAUI.set(option,'候选 {0} · {1}',index,[engine,OAUI.message(state),adopted?OAUI.message('已采用'):null].filter(Boolean));
       return option;
     }));
     card.options=signature;
   }
   picker.value=active.id;picker.hidden=candidates.length<=1;
   tools.hidden=row.kind==='work_video';
   use.hidden=row.kind==='work_video'||active.state!=='ASSET_READY'||active.adopted;
   OAUI.set(badge,active.adopted?'已采用':'');
   badge.hidden=!badge.textContent;
   card.element.dataset.deliveryState=active.state;
   card.element.dataset.candidateId=active.id;
   const asset=active.asset||active;
   const mediaKey=JSON.stringify([active.id,active.state,asset.sha256]);
   if(card.mediaKey===mediaKey)return;
   card.mediaKey=mediaKey;card.player?.close();card.player=null;slot.replaceChildren();
   if(active.state==='ASSET_READY')card.player=playVideo(slot,active);
   else OAUI.set(slot,stateText(active));
 }
 function updateCard(card,row){
   card.row=row;
   const type=row.kind==='shot_video'||row.kind==='work_video'?'video':
     row.kind==='asset'?(row.asset.media_kind||row.asset.family):row.kind;
   card.delivery=row.kind==='shot_video'||row.kind==='work_video';
   card.element.dataset.kind=type;card.element.dataset.nodeId=row.id;
   if(card.delivery)card.element.dataset.deliveryKind=row.kind;
   if(row.engine)card.element.dataset.engine=row.engine.provider+':'+row.engine.model;
   else delete card.element.dataset.engine;
   OAUI.set(card.badge,row.kind==='shot_video'?'镜头视频':row.kind==='work_video'?'作品成片':labels[type]);
   if(card.name.textContent!==row.title)OAUI.raw(card.name,row.title);
   const description=row.kind==='shot'&&row.engine?engineName(row.engine):row.text||'';
   OAUI.raw(card.caption,description);card.caption.hidden=!description;
   if(card.delivery){updateVideo(card);return;}
   const imageKey=(row.cover||row.file?.sha256)||(type==='image'?row.id:'');
   if(imageKey===card.imageKey)return;
   card.imageKey=imageKey;card.pictureSlot.replaceChildren();
   if(imageKey)void picture(row).then(img=>{
     if(card.imageKey===imageKey&&card.element.isConnected)card.pictureSlot.append(img);
   }).catch(()=>{});
 }
 function dispose(card){
   card.player?.close();card.element.remove();
 }
 function render(key,model,shot){
   if(key!==scope.key){
     void flush();scope={key,version:model?.canvas.version||0,moves:new Map()};
     selected='';gesture=null;delete viewport.dataset.dragging;deliveries=[];
     for(const card of cards.values())dispose(card);
     cards.clear();previews={};
     try{previews=JSON.parse(sessionStorage.getItem(previewStore(key)))||{};}catch(_){}
   }else if(model)scope.version=Math.max(scope.version,model.canvas.version);
   work=model;focused=shot;
   if(!work){empty.hidden=true;edge.hidden=true;return;}
   if(!scope.viewport&&!gesture){
     const saved=model.canvas.viewport;
     setView({...saved,scale:saved.scale??100},false);
   }
   const rows=collect(model),ids=new Set(rows.map(row=>row.id));
   empty.hidden=!!rows.length;
   for(const [id,card] of cards)if(!ids.has(id)){dispose(card);cards.delete(id);}
   for(const row of rows){
     if(!cards.has(row.id))cards.set(row.id,newCard(row));
     const card=cards.get(row.id);
     card.defaultPosition=row.position;
     updateCard(card,row);
     if(gesture?.card!==card)position(card,scope.moves.get(row.id)||model.canvas.positions[row.id]||row.position);
   }
   if(!cards.has(selected))selected='';
   refreshSelection(shot);redrawLinks();
 }
 viewport.addEventListener('pointerdown',event=>{
   if(event.button!==0||event.isPrimary===false||event.target.closest('[data-canvas-controls]'))return;
   const target=event.target.closest('[data-node-id]'),card=cards.get(target?.dataset.nodeId);
   gesture={pointer:event.pointerId,x:event.clientX,y:event.clientY,view:{...view},card,moved:false};
   if(card)gesture.position={...card.position};
 });
 viewport.addEventListener('pointermove',event=>{
   if(gesture?.pointer!==event.pointerId)return;
   const g=gesture,dx=event.clientX-g.x,dy=event.clientY-g.y;
   if(!g.moved&&Math.hypot(dx,dy)<4)return;
   if(!g.moved){viewport.setPointerCapture(event.pointerId);g.moved=true;viewport.dataset.dragging='true';}
   if(g.card){
     const unit=100/view.scale;
     position(g.card,{x:point(g.position.x+dx*unit),y:point(g.position.y+dy*unit)});redrawLinks();
   }else setView({...g.view,x:g.view.x+dx,y:g.view.y+dy},false);
 });
 function release(event,cancel=false){
   if(gesture?.pointer!==event.pointerId)return;
   const g=gesture;gesture=null;delete viewport.dataset.dragging;
   if(g.moved){
     if(cancel){
       if(g.card)position(g.card,g.position);else setView(g.view,false);
     }else if(g.card)move(g.card,g.card.position);
     else setView(view);
   }
   render(scope.key,work,focused);
 }
 viewport.addEventListener('pointerup',event=>release(event));
 viewport.addEventListener('pointercancel',event=>release(event,true));
 // The first few pixels are still on the handle before capture starts.
 window.addEventListener('pointerup',event=>release(event));
 viewport.addEventListener('lostpointercapture',event=>release(event,true));
 viewport.addEventListener('wheel',event=>{
   if(event.target.closest('[data-canvas-controls]'))return;
   event.preventDefault();
   const rect=viewport.getBoundingClientRect();
   zoom(event.deltaY>0?-10:10,event.clientX-rect.left,event.clientY-rect.top);
 },{passive:false});
 viewport.addEventListener('keydown',event=>{
   if(event.target!==viewport)return;
   const offset={ArrowLeft:[32,0],ArrowUp:[0,32],ArrowRight:[-32,0],ArrowDown:[0,-32]}[event.key];
   if(offset){event.preventDefault();setView({...view,x:view.x+offset[0],y:view.y+offset[1]});}
   else if(event.key==='+'||event.key==='-'){event.preventDefault();zoom(event.key==='+'?10:-10);}
 });
 $('directorCanvasIn').onclick=()=>zoom(10);
 $('directorCanvasOut').onclick=()=>zoom(-10);
 actions.reset.onclick=()=>setView({x:28,y:28,scale:100});
 $('directorCanvasFit').onclick=fit;
 actions.remove.onclick=()=>{if(work?.canvas.nodes[selected]){flush();void queue('canvas_remove',{node_id:selected});}};
 return {render,flush,setDeliveries(key,rows,version){
     if(key!==scope.key||version<(scope.deliveryVersion??0))return;
     scope.deliveryVersion=version;
     if(JSON.stringify(deliveries)===JSON.stringify(rows))return;
     deliveries=rows;if(!gesture)render(key,work,focused);
   },suspend(){
     void flush();
     gesture=null;delete viewport.dataset.dragging;
     for(const card of cards.values())if(card.player){card.player.close();card.player=null;card.mediaKey='';}
   },add(node){flush();return queue('canvas_add',{node,position:location()});},
   editNote(node_id,title,text){flush();return queue('canvas_note_edit',{node_id,title,text});}};
}
'''
