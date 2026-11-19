"""The work's single canvas, embedded in the existing OpenAhoy app."""

HTML = '''
<section class="dd-canvas-area" aria-label="导演画布">
 <div class="dd-canvas-toolbar">
  <div class="dd-actions">
   <button id="directorCanvasNote" type="button">文字卡</button>
   <button id="directorCanvasImage" type="button">添加图片</button>
   <button id="directorCanvasAssets" type="button">媒体资产</button>
   <button id="directorCanvasRemove" type="button" hidden>移出画布</button>
  </div>
  <div class="dd-actions" aria-label="画布缩放">
   <button id="directorCanvasOut" type="button" aria-label="缩小画布">−</button>
   <button id="directorCanvasReset" type="button" aria-label="复位画布">100%</button>
   <button id="directorCanvasIn" type="button" aria-label="放大画布">＋</button>
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
#videoDirectorDesk .dd-canvas-card button{border:0;box-shadow:none;background:transparent;
 color:inherit;width:100%;text-align:left;min-height:104px;display:flex;flex-direction:column;align-items:stretch;
 padding:8px 10px;gap:5px;overflow:hidden;cursor:inherit}
.dd-canvas-card button span,.dd-canvas-card button strong{overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.dd-canvas-card .dd-canvas-kind{align-self:flex-start;max-width:100%;padding:2px 6px;border-radius:5px;
 font-size:10px;font-weight:700;background:color-mix(in srgb,var(--dd-tone) 22%,var(--surface));color:var(--text)}
.dd-canvas-card[data-kind=shot]{--dd-tone:#789aff}.dd-canvas-card[data-kind=image]{--dd-tone:#54b896}
.dd-canvas-card[data-kind=video]{--dd-tone:#9c80df}.dd-canvas-card[data-kind=audio]{--dd-tone:#df9e51}
.dd-canvas-card[data-kind=gif]{--dd-tone:#d8759e}.dd-canvas-card[data-kind=note]{--dd-tone:#abb0bf}
.dd-canvas-card img{width:100%;height:60px;object-fit:cover;border-radius:5px}
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
function OADirectorCanvas(commit, select, show, picture){
 const $=id=>document.getElementById(id);
 const viewport=$('directorCanvas'),plane=$('directorCanvasPlane'),nodes=$('directorCanvasNodes');
 const edge=$('directorCanvasEdges'),empty=$('directorCanvasEmpty');
 const actions={remove:$('directorCanvasRemove'),reset:$('directorCanvasReset')};
 const labels={shot:'镜头',note:'文字卡',image:'图片',video:'视频',gif:'动图',audio:'音频'};
 let scope={key:'',version:0},selected='',work=null,view={x:28,y:28,scale:100},cards=new Map(),gesture=null,timer=null,pending=Promise.resolve();
 function clamp(value,low,high){return Math.max(low,Math.min(high,value));}
 const point=value=>clamp(Math.round(value),-1000000,1000000);
 function transform(){
   plane.style.transform='translate('+view.x+'px,'+view.y+'px) scale('+(view.scale/100)+')';
   viewport.style.setProperty('--dd-step',18*view.scale/100+'px');
   viewport.style.backgroundPosition=view.x+'px '+view.y+'px';
   OAUI.raw(actions.reset,view.scale+'%');
 }
 function queue(action,args){
   const captured=scope;
   pending=pending.then(()=>captured.key?commit(action,args,captured):false).catch(()=>false);
   return pending;
 }
 function setView(next,save=true){
   view={x:point(next.x),y:point(next.y),scale:clamp(Math.round(next.scale),25,250)};transform();
   if(save){clearTimeout(timer);timer=setTimeout(flush,200);}
 }
 function flush(){
   if(timer===null)return pending;
   clearTimeout(timer);timer=null;
   return queue('canvas_view',{viewport:{...view}});
 }
 function zoom(by,atX=viewport.clientWidth/2,atY=viewport.clientHeight/2){
   const scale=clamp(view.scale+by,25,250),ratio=scale/view.scale;
   setView({x:atX-(atX-view.x)*ratio,y:atY-(atY-view.y)*ratio,scale});
 }
 function location(){
   const x=point((12-view.x)*100/view.scale),y=point((12-view.y)*100/view.scale);
   const columns=Math.max(1,Math.floor((viewport.clientWidth-18)*100/view.scale/184));
   const available=Array.from(cards.values(),card=>card.position);
   for(let i=0;i<=available.length*4;i++){
     const next={x:point(x+(i%columns)*184),y:point(y+Math.floor(i/columns)*144)};
     if(!available.some(p=>Math.abs(p.x-next.x)<172&&Math.abs(p.y-next.y)<128))return next;
   }
   return {x,y};
 }
 function refreshSelection(shot){
   actions.remove.hidden=!work?.canvas.nodes[selected];
   for(const [id,card] of cards)card.element.dataset.current=String(id===(selected||shot));
 }
 function collect(w){
   const found=[];let serial=0;
   for(const scene of w.scenes){
     for(const shot of scene.shots){
       const revision=shot.adopted_revision||shot.head_revision;
       const meta=shot.revisions.find(row=>row.id===revision);
       found.push({kind:'shot',id:shot.id,title:meta.title,scene:scene.id,revision,
                   cover:shot.cover_revision,position:{x:(serial%3)*184,y:Math.floor(serial/3)*140}});
       serial++;
     }
   }
   return found.concat(Object.values(w.canvas.nodes));
 }
 function redrawLinks(){
   const linked=[...cards.values()].filter(card=>cards.has(card.row.shot_id));
   edge.hidden=!linked.length;
   if(!linked.length)return;
   const pts=linked.flatMap(card=>[card.position,cards.get(card.row.shot_id).position]);
   const x=Math.min(...pts.map(p=>p.x))+82,y=Math.min(...pts.map(p=>p.y))+48;
   const width=Math.max(...pts.map(p=>p.x))+84-x,height=Math.max(...pts.map(p=>p.y))+50-y;
   edge.style.left=x+'px';edge.style.top=y+'px';
   // Use a bounded drawing surface even when cards are spread far apart.
   const resolution=Math.min(1,1800/Math.max(width,height));
   edge.width=Math.max(1,Math.ceil(width*resolution));edge.height=Math.max(1,Math.ceil(height*resolution));
   edge.style.width=width+'px';edge.style.height=height+'px';
   const line=edge.getContext('2d');line.strokeStyle=getComputedStyle(edge).color;
   line.lineWidth=2*resolution;line.setLineDash([6*resolution,4*resolution]);
   for(const card of linked){
     const source=cards.get(card.row.shot_id).position;
     line.beginPath();line.moveTo((source.x+83-x)*resolution,(source.y+49-y)*resolution);
     line.lineTo((card.position.x+83-x)*resolution,(card.position.y+49-y)*resolution);line.stroke();
   }
 }
 function position(card,value){
   card.position=value;card.element.style.left=value.x+'px';card.element.style.top=value.y+'px';
 }
 function activate(card,currentShot){
   selected=card.row.id;refreshSelection(currentShot);
   if(card.row.kind==='shot')void select(card.row);
   else void show(card.row);
 }
 function render(key,model,shot){
   if(key!==scope.key){
     void flush();scope={key,version:model?.canvas.version||0};selected='';gesture=null;
   }else if(model)scope.version=Math.max(scope.version,model.canvas.version);
   work=model;nodes.replaceChildren();cards=new Map();
   if(!work){empty.hidden=true;edge.hidden=true;return;}
   if(timer===null&&!gesture){
     const saved=model.canvas.viewport;
     setView({...saved,scale:saved.scale??100},false);
   }
   const rows=collect(model);
   empty.hidden=!!rows.length;
   for(const row of rows){
     const type=row.kind==='asset'?(row.asset.family==='audio'&&row.asset.media_kind==='video'?'video':row.asset.family):row.kind;
     const wrapper=document.createElement('article'),pick=document.createElement('button');
     wrapper.dataset.kind=type;wrapper.dataset.nodeId=row.id;wrapper.className='dd-canvas-card';
     pick.type='button';
     const badge=document.createElement('span');badge.className='dd-canvas-kind';OAUI.set(badge,labels[type]);
     const name=document.createElement('strong');OAUI.raw(name,row.title);
     pick.append(badge,name);
     const card={row,element:wrapper};
     position(card,model.canvas.positions[row.id]||row.position);
     pick.onclick=()=>activate(card,shot);
     pick.onkeydown=event=>{
       const offset={ArrowLeft:[-12,0],ArrowUp:[0,-12],ArrowRight:[12,0],ArrowDown:[0,12]}[event.key];
       if(!offset)return;
       event.preventDefault();flush();
       const pos={x:point(card.position.x+offset[0]),y:point(card.position.y+offset[1])};
       position(card,pos);redrawLinks();void queue('canvas_move',{node_id:row.id,position:pos});
     };
     if(row.cover||type==='image'){
       void picture(row).then(img=>{if(wrapper.isConnected)pick.append(img);}).catch(()=>{});
     }else if(row.text){const excerpt=document.createElement('small');OAUI.raw(excerpt,row.text);pick.append(excerpt);}
     wrapper.append(pick);nodes.append(wrapper);cards.set(row.id,card);
   }
   if(!cards.has(selected))selected='';
   refreshSelection(shot);redrawLinks();
 }
 viewport.addEventListener('pointerdown',event=>{
   if(event.button!==0||event.isPrimary===false)return;
   const target=event.target.closest('[data-node-id]'),card=cards.get(target?.dataset.nodeId);
   gesture={pointer:event.pointerId,x:event.clientX,y:event.clientY,view:{...view},card,moved:false};
   if(card)gesture.position={...card.position};
 });
 viewport.addEventListener('pointermove',event=>{
   if(gesture?.pointer!==event.pointerId)return;
   const g=gesture,dx=(event.clientX-g.x),dy=(event.clientY-g.y);
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
   if(!g.moved)return;
   if(cancel){
     if(g.card){position(g.card,g.position);redrawLinks();}else setView(g.view,false);
   }else if(g.card){flush();void queue('canvas_move',{node_id:g.card.row.id,position:g.card.position});}
   else setView(view);
 }
 viewport.addEventListener('pointerup',event=>release(event));
 viewport.addEventListener('pointercancel',event=>release(event,true));
 viewport.addEventListener('wheel',event=>{
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
 actions.remove.onclick=()=>{if(work?.canvas.nodes[selected]){flush();void queue('canvas_remove',{node_id:selected});}};
 return {render,flush,add(node){flush();return queue('canvas_add',{node,position:location()});},
         editNote(node_id,title,text){flush();return queue('canvas_note_edit',{node_id,title,text});}};
}
'''
