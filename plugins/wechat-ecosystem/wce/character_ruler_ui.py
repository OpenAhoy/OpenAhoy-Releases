"""Read-only proportions and same-frame reference comparison for character assets."""

STYLE = r'''
.cl-browse-photo{position:relative}
.cl-ruler-options[hidden],.cl-ruler-summary[hidden],.cl-ruler-compare[hidden],
.cl-ruler-compare-tools[hidden],.cl-ruler-compare-tools select[hidden],.cl-ruler-status[hidden]{display:none!important}
.cl-ruler-options,.cl-ruler-compare-tools{display:flex;align-items:center;flex-wrap:wrap;gap:4px 7px}
.cl-ruler-options{padding:2px 8px;min-height:25px}
.cl-ruler-options label{display:inline-flex;align-items:center;gap:4px;font-size:11px}
#characterDetail .cl-ruler-options :is(button,select){min-height:23px;max-width:100%;padding:2px 5px;font-size:11px;box-shadow:none}
#characterDetail .cl-ruler-options input{width:auto;min-height:0;margin:0;accent-color:var(--cl-accent)}
#characterDetail button[data-ruler-toggle][aria-pressed=true],
#characterDetail .cl-browse-controls button[aria-controls="clRulerComparison"][aria-expanded=true],
#characterDetail .cl-ruler-options button[aria-pressed=true]{
 background:var(--cl-tint);color:var(--cl-accent);border-color:var(--cl-accent)
}
.cl-ruler-status{padding:2px 8px;font-size:11px;color:var(--cl-gray)}
.cl-ruler-compare{
 position:absolute;inset:0;z-index:2;display:grid;place-content:center;grid-template-columns:repeat(2,minmax(0,1fr));
 gap:3px;background:var(--cl-frame)
}
#characterDetail .cl-browse-stage[data-ruler-compare] :is(.cl-browse-photo,.cl-wardrobe-exhibit,.cl-shelf-return){visibility:hidden}
.cl-ruler-compare figure{position:relative;margin:0;min-width:0;display:grid;justify-items:center;gap:3px}
.cl-ruler-compare-frame{
 position:relative;overflow:hidden;isolation:isolate;display:grid;place-items:center;
 width:min(100%,calc(100cqw * var(--cl-ruler-ratio,1)));
 aspect-ratio:var(--cl-ruler-ratio,1);border-radius:5px;background:var(--cl-card)
}
.cl-ruler-compare-frame img{width:100%;height:100%;position:absolute;inset:0;object-fit:contain}
.cl-ruler-compare-frame>span{padding:6px;text-align:center;font-size:11px}
.cl-ruler-compare figcaption{
 position:absolute;z-index:1;bottom:2px;right:3px;padding:1px 3px;border-radius:2px;
 background:#261f28db;color:white;font-size:clamp(7px,1.35cqw,11px);line-height:1.2
}
.cl-ruler-switch{display:none}
.cl-ruler-overlay[hidden]{display:none!important}
.cl-ruler-overlay.cl-ruler-inline{inset:auto;left:50%;top:50%;transform:translate(-50%,-50%)}
.cl-browse-stage[data-display-open=true] .cl-ruler-inline{--cl-ruler-start:20%;--cl-ruler-end:19%}
.cl-ruler-inline :is(.cl-ruler-fixed,.cl-ruler-rail){transition:left .46s cubic-bezier(.22,.72,.25,1)}
.cl-browse-stage[data-display-open=true] .cl-ruler-inline .cl-ruler-marks{right:20%}
.cl-ruler-overlay{position:absolute;inset:0;pointer-events:none;overflow:hidden;color:#fff}
.cl-ruler-fixed,.cl-ruler-marks,.cl-ruler-axis,.cl-ruler-rail{position:absolute}
.cl-ruler-axis,.cl-ruler-rail{border-left:1px solid #fffc;box-shadow:1px 0 0 #251c2360}
.cl-ruler-axis{height:100%;top:0;border-left-style:dotted;opacity:.47;box-shadow:none}
.cl-ruler-rail{left:var(--cl-ruler-start,6%);opacity:.84}
.cl-ruler-fixed{left:var(--cl-ruler-start,6%);right:var(--cl-ruler-end,6%);font-size:10px;line-height:1.1;transform:translateY(-50%)}
.cl-ruler-fixed::before,.cl-ruler-marks::before{
 content:'';position:absolute;inset:50% 0 auto;border-top:1px solid #ffef;filter:drop-shadow(0 1px 0 #30212684)
}
.cl-ruler-fixed[data-joint]::before{border-top-style:dashed;opacity:.8}
.cl-ruler-fixed span,.cl-ruler-marks span{
 position:relative;padding:1px 4px;border-radius:3px;background:#261f28dd;color:#fff;font-variant-numeric:tabular-nums
}
.cl-ruler-marks{right:5%;width:24%;height:12px;text-align:right;transform:translateY(-50%);font-size:9px}
.cl-ruler-marks::before{border-color:#ceffe9;border-top-width:2px}
.cl-ruler-marks span{background:#103e36e8;color:#e7fff4;white-space:nowrap}
.cl-ruler-compare .cl-ruler-marks{width:29%}
.cl-ruler-summary{display:grid;gap:6px;margin-top:9px;font-size:12px}
.cl-ruler-summary h3,.cl-ruler-summary p{margin:0}
.cl-ruler-summary p{line-height:1.4;color:var(--cl-gray)}
.cl-ruler-summary summary{cursor:pointer;font-weight:630}
.cl-ruler-table-wrap{max-width:100%;overflow:auto}
.cl-ruler-summary table{width:100%;border-collapse:collapse;font-size:11px;font-variant-numeric:tabular-nums}
.cl-ruler-summary td,.cl-ruler-summary th{padding:4px 2px;border-bottom:1px solid var(--cl-line);text-align:center}
.cl-ruler-summary tbody th{text-align:start;white-space:nowrap}
.cl-ruler-summary td[data-missing]{color:var(--cl-gray)}
@media(prefers-reduced-motion:reduce){
 .cl-ruler-inline :is(.cl-ruler-fixed,.cl-ruler-rail){transition:none}
}
@media(max-width:825px){
 .cl-ruler-compare{grid-template-columns:minmax(0,1fr)}
 .cl-ruler-compare[data-side=current] figure[data-side=older],
 .cl-ruler-compare[data-side=older] figure[data-side=current]{display:none}
 .cl-ruler-switch{display:inline-flex;gap:3px}
}
@media(max-width:720px){
 .cl-ruler-options,.cl-ruler-status{padding-inline:4px}
 .cl-ruler-summary{margin-top:7px}
}
'''

SCRIPT = r'''
function OACharacterRuler(model,{title,formName,stage,photo,findImage,loadImage,viewLabel}){
 const el=(tag,cls='',label)=>{const node=document.createElement(tag);node.className=cls;if(label)OAUI.set(node,label);return node;};
 const button=(label,action)=>{
   const control=el('button','',label);control.type='button';control.onclick=action;return control;
 };
 const labels={crown:'头顶',shoulder:'肩',hip:'胯',knee:'膝',ankle:'踝',sole:'脚底'};
 const axis=['crown','shoulder','hip','knee','ankle','sole'];
 const names={faceless:'无面正面',headless:'无头正面',wardrobe:'礼服正面'};
 const kind={original:'原件预览',comparison_preview:'对照预览'};
 const toolbar=el('div','cl-ruler-options'), notice=el('p','cl-ruler-status');
 notice.setAttribute('role','status');
 const overlay=el('div','cl-ruler-overlay cl-ruler-inline');overlay.id='clProportionRuler';
 overlay.setAttribute('aria-hidden','true');overlay.hidden=true;
 const stageCompare=el('section','cl-ruler-compare');
 stageCompare.hidden=true;stageCompare.id='clRulerComparison';
 OAUI.attr(stageCompare,'aria-label','版本对比');
 stageCompare.style.setProperty('--cl-ruler-ratio',String(model.width/model.height));
 stage.append(stageCompare);

 const comparisonTools=el('div','cl-ruler-compare-tools'), revisions=el('select');
 OAUI.attr(revisions,'aria-label','对照版本');
 const switcher=el('span','cl-ruler-switch');
 const mobileOlder=button('',()=>showSide('older')),mobileCurrent=button('',()=>showSide('current'));
 OAUI.raw(mobileCurrent,title);
 switcher.append(mobileOlder,mobileCurrent);
 comparisonTools.append(revisions,switcher);
 const comparisonButton=button('版本对比',()=>setCompare(!comparing));
 comparisonButton.setAttribute('aria-controls',stageCompare.id);
 comparisonButton.setAttribute('aria-expanded','false');
 const pixel=button('px',()=>setUnit('px')),centimeter=button('cm',()=>setUnit('cm'));
 OAUI.attr(pixel,'aria-label','原图像素');OAUI.attr(centimeter,'aria-label','按设定身高换算');
 const calibrated=!!model.height_cm&&model.fixed.crown!==undefined&&model.fixed.sole!==undefined;
 centimeter.disabled=!calibrated;
 function toggle(label,initial){
   const input=el('input'),wrap=el('label');
   input.type='checkbox';input.checked=initial;input.onchange=paintMarks;
   wrap.append(input,el('span','',label));return [input,wrap];
 }
 const [joints,jointSwitch]=toggle('关节参考',false),[points,pointSwitch]=toggle('本图标记',false);
 toolbar.append(pixel,centimeter,jointSwitch,pointSwitch,comparisonTools);

 const summary=el('section','cl-ruler-summary'), scope=el('p'),dimensions=el('p'),basis=el('p'),source=el('p');
 const details=el('details'), wrap=el('div','cl-ruler-table-wrap'),table=el('table'),head=el('thead'),rows=el('tbody');
 table.append(head,rows);wrap.append(table);
 details.append(el('summary','','测点明细'),wrap,el('p','','差值为正表示在图中更靠下'));
 summary.append(el('h3','','比例标定'),scope,dimensions,basis,source,details);
 OAUI.set(dimensions,'标定画布 {0} · 基准中轴 x={1}',model.width+' × '+model.height+' px',model.axis_x);
 if(calibrated)OAUI.set(basis,'设定身高 {0} cm · 脚底为 0 · {1}',model.height_cm,model.height_basis);
 else OAUI.set(basis,model.height_cm?'缺少头脚标定 · 仅显示像素':'暂无设定身高 · 仅显示像素');
 OAUI.set(source,'标定来源 · {0}',model.source);
 let active=false,comparing=false,epoch=0,unit='px',view=null,current=null,older=null,panels=[];
 let chosenRevision='',side='current';
 const ratio=y=>(100*y/model.height)+'%';
 const raw=(tag,text)=>{const node=el(tag);OAUI.raw(node,String(text));return node;};
 const fits=(img,ref)=>img instanceof HTMLImageElement&&img.naturalHeight>0&&
   Math.abs(img.naturalWidth-img.naturalHeight*ref.width/ref.height)<=1;

 function fitOverlay(){
   if(overlay.hidden)return;
   const width=Math.min(photo.clientWidth,photo.clientHeight*model.width/model.height);
   overlay.style.width=width+'px';overlay.style.height=width*model.height/model.width+'px';
 }
 const observer=new ResizeObserver(fitOverlay);
 observer.observe(photo);
 function setUnit(value){
   unit=value;pixel.setAttribute('aria-pressed',String(unit==='px'));
   centimeter.setAttribute('aria-pressed',String(unit==='cm'));paintMarks();
 }
 function showSide(value){
   side=value;stageCompare.dataset.side=side;
   mobileCurrent.setAttribute('aria-pressed',String(side==='current'));
   mobileOlder.setAttribute('aria-pressed',String(side==='older'));
 }
 function displayValue(y){
   return unit==='cm'?((model.fixed.sole-y)*model.height_cm/(model.fixed.sole-model.fixed.crown)).toFixed(1)+' cm':y+' px';
 }
 function mark(layer,key,y,isPoint=false){
   const marker=el('span',isPoint?'cl-ruler-marks':'cl-ruler-fixed');
   marker.style.top=ratio(y);marker.dataset.point=key;marker.dataset.pixel=String(y);
   if(!isPoint&&key!=='crown'&&key!=='sole')marker.dataset.joint='';
   const value=el('span');
   OAUI.set(value,'{0} {1}',OAUI.message(labels[key]||'可见上缘'),displayValue(y));
   marker.append(value);layer.append(marker);
 }
 function draw(layer,image){
   const rail=el('span','cl-ruler-rail'),center=el('span','cl-ruler-axis');
   layer.replaceChildren();
   if(model.fixed.crown!==undefined&&model.fixed.sole!==undefined){
     rail.style.top=ratio(model.fixed.crown);rail.style.height=ratio(model.fixed.sole-model.fixed.crown);
     layer.append(rail);
   }
   center.style.left=(100*model.axis_x/model.width)+'%';layer.append(center);
   for(const key of axis){
     const y=model.fixed[key];
     if(y!==undefined&&(key==='crown'||key==='sole'||joints.checked))mark(layer,key,y);
   }
   if(points.checked){
     if(image.visible_top!==undefined)mark(layer,'visible_top',image.visible_top,true);
     for(const [joint,value] of Object.entries(image.points))mark(layer,joint,value,true);
   }
 }
 function paintMarks(){
   if(view&&!overlay.hidden)draw(overlay,view.image);
   for(const {layer,image} of panels)draw(layer,image);
 }
 function tableContents(){
   const header=el('tr'),signed=value=>value>0?'+'+value:value<0?'−'+Math.abs(value):'0';
   const headings=[el('th','','测点'),el('th','','固定线 px'),raw('th',title),el('th','','较固定线 Δ')];
   if(older){headings.splice(2,0,raw('th',older.title));headings.push(el('th','','两版 Δ'));}
   for(const th of headings){th.scope='col';header.append(th);}
   head.replaceChildren(header);
   rows.replaceChildren(...axis.slice(1,-1).map(key=>{
     const row=el('tr'),name=el('th','',labels[key]);row.dataset.point=key;name.scope='row';row.append(name);
     const fixed=model.fixed[key],actual=view.image.points[key],before=older?.image.points[key];
     const cell=(value,role)=>{
       const td=value===undefined?el('td','','未标注／遮挡'):raw('td',value);
       td.dataset.value=role;if(value===undefined)td.dataset.missing='';return td;
     };
     row.append(cell(fixed,'fixed'));
     if(older)row.append(cell(before,'older'));
     row.append(cell(actual,'current'),cell(actual===undefined||fixed===undefined?undefined:signed(actual-fixed),'fixed-delta'));
     if(older)row.append(cell(actual===undefined||before===undefined?undefined:signed(actual-before),'revision-delta'));
     return row;
   }));
 }
 function comparePanel(image,revision,panelSide,ticket){
   const figure=el('figure'),frame=el('div','cl-ruler-compare-frame'),layer=el('div','cl-ruler-overlay');
   figure.dataset.side=panelSide;frame.dataset.state='loading';layer.setAttribute('aria-hidden','true');
   const status=el('span','','正在读取原图…');status.setAttribute('role','status');frame.append(status);
   const caption=el('figcaption');
   OAUI.set(caption,'{0} · {1} · {2}',revision,OAUI.message(kind[image.display_kind]),image.width+' × '+image.height);
   figure.append(frame,caption);panels.push({layer,image});
   const finish=img=>{
     if(!comparing||ticket!==epoch)return;
     OAUI.attr(img,'alt','{0} · {1}',revision,OAUI.message(names[view.angle]||viewLabel(view.angle)));
     frame.replaceChildren(img,layer);frame.dataset.state='ready';
     frame.dataset.version=image.version;frame.dataset.sha=image.sha256;
   };
   if(panelSide==='current'){
     finish(current.cloneNode(false));
   }else{
     const row=findImage(image);
     Promise.resolve().then(async()=>{
       if(!row)throw Error('missing');
       const img=await loadImage(row);
       if(!fits(img,image))throw Error('frame');
       finish(img);
     }).catch(()=>{
       if(ticket===epoch&&comparing){frame.dataset.state='unavailable';OAUI.set(status,'标尺图像暂不可读');}
     });
   }
   return figure;
 }
 function paintComparison(){
   epoch++;
   panels=[];
   comparisonTools.hidden=!comparing;
   comparisonButton.setAttribute('aria-expanded',String(comparing));
   stage.toggleAttribute('data-ruler-compare',comparing);
   stageCompare.hidden=!comparing;
   if(comparing){
     const choices=view.comparisons;
     older=choices.find(row=>row.revision===chosenRevision)||choices[0];
     chosenRevision=older.revision;
     revisions.hidden=choices.length<2;
     revisions.replaceChildren(...choices.map(row=>{
       const choice=raw('option',row.title);choice.value=row.revision;return choice;
     }));
     revisions.value=chosenRevision;OAUI.raw(mobileOlder,older.title);showSide(side);
     stageCompare.replaceChildren(comparePanel(older.image,older.title,'older',epoch),
       comparePanel(view.image,title,'current',epoch));
   }else{
     older=null;stageCompare.replaceChildren();
   }
   if(view)tableContents();
   paintMarks();
 }
 function setCompare(next){
   if(next&&(!active||!current||!view?.comparisons.length))return;
   if(next===comparing)return;
   comparing=next;side='current';paintComparison();
 }
 function selectCompared(){
   chosenRevision=revisions.value;paintComparison();
 }
 revisions.onchange=selectCompared;

 function refresh(){
   const canMark=active&&!!view;
   toolbar.hidden=!canMark;
   comparisonButton.hidden=!canMark||!view?.comparisons.length;
   summary.hidden=!canMark;
   notice.hidden=!active||canMark;
   if(!notice.hidden)OAUI.set(notice,current?'这张图未登记比例标定':'等待当前图像');
   overlay.hidden=!canMark;
   if(canMark&&overlay.parentNode!==photo)photo.append(overlay);
   if(canMark){
     overlay.dataset.version=view.image.version;fitOverlay();
     OAUI.set(scope,'{0} · {1} · {2}',OAUI.message(formName),title,OAUI.message(names[view.angle]||viewLabel(view.angle)));
   }
   if(comparing&&!view?.comparisons.length)comparing=false;
   paintComparison();
 }
 function selectImage(row,img){
   const modelView=row&&model.views.find(item=>row.id===item.image.version&&row.file.sha256===item.image.sha256);
   view=modelView&&fits(img,modelView.image)?modelView:null;
   current=img;
   refresh();
 }
 setUnit('px');refresh();
 return {toolbar,notice,summary,comparisonButton,selectImage,setCompare,
   setActive(value){active=value;if(!active)comparing=false;refresh();},
   isComparing:()=>comparing,
   dispose(){epoch++;comparing=false;observer.disconnect();},
 };
}
'''
