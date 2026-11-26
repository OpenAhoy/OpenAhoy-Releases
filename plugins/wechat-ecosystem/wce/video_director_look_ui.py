"""Composite timeline edits over decoded source frames without changing the original player."""

STYLE = """
#dmCutPreview .oa-frame-screen{position:relative}
.dc-look-canvas{position:absolute;inset:0;margin:auto;overflow:hidden;background:black;isolation:isolate}
.dc-look-image,.dc-look-overlay,.dc-look-fade{position:absolute;inset:0;width:100%;height:100%;pointer-events:none}
#dmCutPreview .dc-look-image img{display:block;width:100%;height:100%;object-fit:contain}
.dc-look-image{background:black}
.dc-look-vignette{position:absolute;inset:0;pointer-events:none;
 background:radial-gradient(ellipse closest-side,transparent 55%,rgba(0,0,0,.58) 100%)}
.dc-look-fade{opacity:0}
"""

SCRIPT = r"""
function OADirectorClipLook(surface){
 const ns='http://www.w3.org/2000/svg';
 const svg=(name,attrs={})=>{
   const el=document.createElementNS(ns,name);
   for(const [k,v] of Object.entries(attrs))el.setAttribute(k,v);
   return el;
 };
 const div=cls=>{const el=document.createElement('div');el.className=cls;return el;};
 const canvas=div('dc-look-canvas'),picture=div('dc-look-image'),shade=div('dc-look-vignette'),fade=div('dc-look-fade');
 const overlay=svg('svg',{class:'dc-look-overlay','aria-hidden':'true',preserveAspectRatio:'none'});
 const defs=svg('defs'),filter=svg('filter',{id:'dmCutLookRGB','color-interpolation-filters':'sRGB',x:0,y:0,width:'100%',height:'100%'});
 const tone=svg('feColorMatrix',{type:'matrix'}),grade=svg('feColorMatrix',{type:'matrix'});
 filter.append(tone,grade);defs.append(filter);overlay.append(defs);canvas.append(picture,shade,overlay,fade);surface.append(canvas);
 let active=null,captionText=null,subtitle=null,canvasWidth=1600,canvasHeight=900;
 let lastOpacity='';
 function size(width,height){
   const aspect=width/height;
   if(!(aspect>0)||!Number.isFinite(aspect))return;
   canvasWidth=width;canvasHeight=height;
   canvas.style.width=Math.min(100,aspect/(16/9)*100)+'%';
   canvas.style.height=Math.min(100,(16/9)/aspect*100)+'%';
   overlay.setAttribute('viewBox','0 0 '+width+' '+height);active=null;
 }
 size(1600,900);
 function matrix(r,g,b,t=0){return [r,0,0,0,t,0,g,0,0,t,0,0,b,0,t,0,0,0,1,0].join(' ');}
 function drawText(node,text,x,baseline,size,isBottom=false){
   node.replaceChildren();
   if(!text)return;
   let paragraphs=text.split(/\r\n|[\n\r\v\f\x1c-\x1e\x85\u2028\u2029]/u);
   if(paragraphs.at(-1)==='')paragraphs.pop();
   if(paragraphs.length>3)paragraphs=[...paragraphs.slice(0,2),paragraphs.slice(2).join(' ')];
   let lines=[];
   do{
     lines=[];const maxWidth=canvasWidth*.86/size;
     for(const paragraph of paragraphs){
       let line='',units=0;
       for(const char of paragraph){
         const full=/[\p{Script=Han}\p{Script=Hiragana}\p{Script=Katakana}\p{Script=Hangul}\u3000-\u303f\uff01-\uff60\uffe0-\uffe6]|\p{Extended_Pictographic}/u.test(char);
         const width=full?1:(/\s/u.test(char)?0.33:0.65);
         if(line&&units+width>maxWidth){lines.push(line);line='';units=0;}
         line+=char;units+=width;
       }
       lines.push(line);
     }
     if(lines.length<=3)break;size*=.9;
   }while(true);
   const lineHeight=size*1.2,y=isBottom?baseline-(lines.length-1)*lineHeight:baseline;
   node.setAttribute('font-size',size);node.setAttribute('stroke-width',size*.08);
   lines.forEach((line,i)=>{const span=svg('tspan',{x:x,y:y+i*lineHeight});span.textContent=line;node.append(span);});
 }
 function textNode(size){
   return svg('text',{'text-anchor':'middle','font-family':'PingFang SC, sans-serif','font-weight':'600',
     'font-size':size,fill:'white',stroke:'#171717','stroke-width':size*.08,'stroke-linejoin':'round','paint-order':'stroke fill'});
 }
 function bind(clip){
   active=clip;captionText=null;
   while(overlay.lastChild!==defs)overlay.lastChild.remove();
   const look=clip.look||{},w=canvasWidth,h=canvasHeight;
   if(look.filter==='mono')tone.setAttribute('values','0.2126 0.7152 0.0722 0 0 0.2126 0.7152 0.0722 0 0 0.2126 0.7152 0.0722 0 0 0 0 0 1 0');
   else{
     const gain=look.filter==='warm'?[1.08,1,.90]:look.filter==='cool'?[.90,1,1.08]:[1,1,1];
     tone.setAttribute('values',matrix(...gain));
   }
   const contrast=1+(look.contrast||0)/100,offset=.5*(1-contrast)+(look.brightness||0)/200;
   grade.setAttribute('values',matrix(contrast,contrast,contrast,offset));
   const filters=[];
   if(look.filter||look.contrast||look.brightness)filters.push('url(#dmCutLookRGB)');
   if(look.effect==='blur')filters.push('blur(calc(var(--dc-look-height) * .009))');
   picture.style.filter=filters.join(' ')||'none';shade.style.display=look.effect==='vignette'?'block':'none';
   if(look.mask==='circle'){
     const r=.48*Math.min(w,h),left=w/2-r,right=w/2+r,cy=h/2;
     const hole='M'+left+' '+cy+' A'+r+' '+r+' 0 1 0 '+right+' '+cy+' A'+r+' '+r+' 0 1 0 '+left+' '+cy+' Z';
     overlay.append(svg('path',{d:'M0 0H'+w+'V'+h+'H0Z '+hole,'fill-rule':'evenodd',fill:'black','data-look':'mask'}));
   }else if(look.mask==='letterbox'){
     const band=Math.max(0,(h-w/2.39)/2);
     overlay.append(svg('path',{d:'M0 0H'+w+'V'+band+'H0Z M0 '+(h-band)+'H'+w+'V'+h+'H0Z',fill:'black','data-look':'mask'}));
   }
   if(look.title){
     const title=textNode(.075*h);title.setAttribute('data-look','title');overlay.append(title);
     drawText(title,look.title,w*.5,h*.19,h*.075);
   }
   subtitle=textNode(.052*h);subtitle.setAttribute('data-look','caption');overlay.append(subtitle);
   fade.style.backgroundColor=look.transition==='white'?'white':'black';lastOpacity='';
 }
 function measure(){canvas.style.setProperty('--dc-look-height',canvas.getBoundingClientRect().height+'px');}
 const observer=typeof ResizeObserver==='function'?new ResizeObserver(measure):null;
 observer?.observe(canvas);
 function update(img,clip,sourceMs,clipFrame,frameCount){
   if(active!==clip)bind(clip);
   if(picture.firstChild!==img)picture.replaceChildren(img);
   const look=clip.look||{};
   const text=look.cues?.length?(look.cues.find(c=>sourceMs>=c.in_ms&&sourceMs<c.out_ms)?.text||''):(look.caption||'');
   if(text!==captionText){drawText(subtitle,text,canvasWidth*.5,canvasHeight*.91,canvasHeight*.052,true);captionText=text;}
   const initial=look.zoom??100,final=look.zoom_end??initial;
   const progress=frameCount>1?clipFrame/(frameCount-1):0;
   const zoom=(initial+(final-initial)*progress)/100;
   const angle=look.rotation||0;
   const fit=angle%180?Math.min(canvasWidth/canvasHeight,canvasHeight/canvasWidth):1;
   const transform=!look.mirror&&!angle&&zoom===1?'none':
     'scale('+(zoom*fit)+') rotate('+angle+'deg) scaleX('+(look.mirror?-1:1)+')';
   if(img.style.transform!==transform)img.style.transform=transform;
   const duration=Math.min(.35,frameCount/30/2);
   const alpha=look.transition&&frameCount>1?Math.max(0,1-clipFrame/(30*duration)):0;
   const opacity=alpha.toFixed(4);
   if(opacity!==lastOpacity){fade.style.opacity=opacity;lastOpacity=opacity;}
 }
 function clear(){picture.replaceChildren();canvas.style.visibility='hidden';active=null;}
 return {size,clear,update(img,c,ms,index,count){canvas.style.visibility='visible';update(img,c,ms,index,count);},
   close(){observer?.disconnect();canvas.remove();}};
}
"""
