"""Opt-in perspective for card surfaces and non-interactive content."""

import json

SHARED_STYLE = r'''
@media (any-hover:hover) and (any-pointer:fine) and (prefers-reduced-motion:no-preference){
 .jiu-card-motion-relative{position:relative}
 .jiu-card-motion-host{
  isolation:isolate;
  --jiu-card-motion-projection:perspective(var(--jiu-card-motion-distance,310px)) rotateX(var(--wb-card-pitch,0deg)) rotateY(var(--wb-card-yaw,0deg));
 }
 .jiu-card-motion-host[data-card-hover]>.jiu-card-motion-face{
  position:absolute;inset:0;z-index:-1;box-sizing:border-box;display:block;pointer-events:none;
  border-radius:inherit;transform:var(--jiu-card-motion-projection);transition:transform 135ms ease-out
 }
 .jiu-card-motion-plane{transition:transform 135ms ease-out}
 .jiu-card-motion-host[data-card-hover]>.jiu-card-motion-plane{
  transform:var(--jiu-card-motion-projection)
 }
 .jiu-card-motion-plane>.jiu-card-motion-face{
  position:absolute;inset:0;z-index:2;display:block;pointer-events:none;border-radius:inherit
 }
 .jiu-card-motion-face::before{
  content:"";display:block;position:absolute;inset:0;border-radius:inherit;padding:2px;pointer-events:none;
  background:radial-gradient(circle 74px at var(--wb-card-x) var(--wb-card-y),light-dark(#3a849a,#b6d2ff),transparent 100%);
  mask:linear-gradient(#000 0 0) content-box,linear-gradient(#000 0 0);mask-composite:exclude
 }
 .jiu-card-motion-face::after{
  content:"";display:block;position:absolute;inset:0;border-radius:inherit;pointer-events:none;
  background:radial-gradient(ellipse at var(--wb-card-x) var(--wb-card-y),light-dark(#b0e0ef24,#9ac5ff26),transparent 68%)
 }
 .jiu-card-motion-host[data-card-hover].jiu-card-motion-skin{
  background:transparent!important;border-color:transparent!important;box-shadow:none!important
 }
 .jiu-card-motion-host[data-card-hover].jiu-card-motion-skin:not(.jiu-card-motion-clipped){overflow:visible!important}
 .jiu-card-motion-part{
  transform-origin:var(--wb-card-origin,50% 50%);
  transform:var(--jiu-card-motion-projection,perspective(310px)) translateZ(var(--jiu-card-motion-depth,0px));
  transition:transform 135ms ease-out;pointer-events:none
 }
 .jiu-card-motion-host:is([data-jiu-pressed],:has(.jiu-card-motion-primary[data-jiu-pressed]))>.jiu-card-motion-face{
  box-shadow:var(--jiu-pressure) !important
 }
}
@media (forced-colors:active){
 .jiu-card-motion-face::before,.jiu-card-motion-face::after{display:none}
}
'''

# parts are confined to pictures and labels. Buttons, links, players and their
# hot areas retain their original layout even when their visible content tilts.
FAMILIES = [
    dict(selector="#characterLibrary .cl-card", parts=[(".cl-picture", 9), (".cl-card-copy", 16)], focus=[":self .cl-card-copy strong"]),
    dict(selector="#characterPicker .cl-card", parts=[(".cl-picture", 9), (".cl-card-copy", 16)], focus=[":self .cl-card-copy strong"]),
    dict(selector="#directorAssetKinds .ja-exhibit", parts=[(".ja-category>span", 18), (".ja-exhibit-media", 4)],
         stationary=[".ja-exhibit[data-kind=video] .ja-exhibit-media", ".ja-exhibit[data-kind=audio] .ja-exhibit-media",
                     ".ja-exhibit[data-center-preview] .ja-exhibit-media"], primary=".ja-category", clipped=True,
         focus=[".ja-category >span"]),
    dict(selector="#wbOpenAhoy .ob-column", parts=[(".ob-platform-entry .oa-platform-mark", 24), (".ob-account-name>.avatar", 7),
                                                   (".ob-account-label", 9), (".ob-state", 4)], primary=".ob-platform-entry",
         clipped=True, skin=False, focus=[".ob-platform-entry .oa-platform-mark", ".ob-account-name .ob-account-label"]),
    dict(selector="#wbDouyin .ob-douyin-choice", parts=[(".avatar", 15), (".ob-state", 8)],
         focus=[":self .ob-state"]),
    dict(selector=":is(#accountPanel,#wechatAccountPicker) .account-select", parts=[(".avatar", 13), (".oa-account-copy", 16)], clipped=True,
         focus=[":self .oa-account-copy"]),
    dict(selector="#creativeTemplates .template-card", parts=[(":scope>img", 14), ("h3", 14), ("p", 7)], clipped=True),
    dict(selector="#settingsPanel .wx-setup-feature", parts=[(".wx-setup-art", 14), ("h3", 14), (".wx-setup-type", 8)], clipped=True),
    dict(selector="#wechatArticlesPage .wx-article-card", parts=[(":scope>img", 10), (":scope>span", 13)],
         focus=[":self strong"]),
    dict(selector="#wbPublished .wb-published-card", parts=[(".jh-work-meta", 8), ("h3", 15), (".jh-work-metrics", 8)], clipped=True),
    dict(selector="#wbMusicHome .lh-project-card", parts=[], plane=".lh-project-plane",
         focus=[":self .lh-project-name strong"]),
    dict(selector="#wbMusicHome .lh-recent-card", parts=[], plane=".lh-recent-plane",
         focus=[":self .lh-recent-name strong"]),
    dict(selector="#wbMusicSongs .lh-card.embedded-song", parts=[(".lh-cover img", 12), (".lh-play-icon", 8),
                                                                  (".embedded-song-info>small,.embedded-song-info>p,.embedded-note", 10)],
         clipped=True, skin=False),
    dict(selector="#wbMusicHome .lh-feature-slot", parts=[], plane=".lh-feature"),
    dict(selector="#directorCardList >button", parts=[(":scope>strong", 14), (":scope>span", 8)], focus=[":self strong"]),
    dict(selector="#videoDirectorDesk #directorShots .dd-shot", parts=[(".dd-shot-cover", 8), ("strong", 12)],
         clipped=True, focus=[":self strong"]),
]

# Main keyboard focus is recognisable inside the existing card. Neither the
# base border/selection meaning nor separately led buttons are shared by fiat.
FOCUS_STYLE = '''
#characterLibrary .cl-card[aria-pressed=true]{outline:none}
#characterLibrary .cl-card[aria-pressed=true] .cl-card-copy strong{
 color:var(--cl-accent);font-weight:750
}
.oa-native :is(#characterLibrary,#characterPicker) .cl-card:focus-visible:not(:hover){border-color:var(--cl-line)}
'''
for family in FAMILIES:
    for item in family.get('focus', ()):
        control, label = item.split(' ',1)
        target = family['selector'] if control == ':self' else family['selector'] + ' ' + control
        FOCUS_STYLE += f'''
{target}:focus{{outline:none!important}}
html:not([data-jiu-card-pointer]) {target}:focus-visible {label}{{
 text-decoration:underline;text-decoration-thickness:2px;text-underline-offset:3px
}}
'''
        if control == '.ob-platform-entry':
            FOCUS_STYLE += f'''
{target}:focus-visible::after{{outline:none}}
html:not([data-jiu-card-pointer]) {target}:focus-visible .oa-platform-mark{{
 box-shadow:inset 0 -2px currentColor
}}
'''

STYLE = SHARED_STYLE + FOCUS_STYLE

SCRIPT = (
    'globalThis.JiuseraCardMotion=(()=>{\n'
    ' const style=' + json.dumps(SHARED_STYLE) + ';\n'
    r'''
 const controls='button,a[href],input,select,textarea,summary,video,audio,[contenteditable],[role=button],[role=slider]';
 const guard='(any-hover:hover) and (any-pointer:fine) and (prefers-reduced-motion:no-preference)';
 const pointer={capture:true,passive:true};
 document.addEventListener('pointerdown',()=>document.documentElement.toggleAttribute('data-jiu-card-pointer',true),pointer);
 document.addEventListener('keydown',event=>{
  if(!event.ctrlKey&&!event.metaKey&&!event.altKey)document.documentElement.removeAttribute('data-jiu-card-pointer');
 },true);
 function mount(root,rules){
  const hover=matchMedia(guard),forced=matchMedia('(forced-colors:active)'),signals=new AbortController();
  const options={passive:true,signal:signals.signal};
  const selection=rules.map(rule=>rule.selector).join(',');
  let active=null,pending=null,frame=0;
  const eligible=()=>hover.matches&&!forced.matches;
  const find=node=>node instanceof Element?node.closest(selection):null;
  function reset(){
   if(!active)return;
   const {card,layers,face,primary}=active;
   card.removeAttribute('data-card-hover');
   for(const prop of ['pitch','yaw','x','y'])card.style.removeProperty('--wb-card-'+prop);
   if(face){
    card.style.removeProperty('--jiu-card-motion-distance');
    face.remove();
    primary?.classList.remove('jiu-card-motion-primary');
    card.classList.remove('jiu-card-motion-host','jiu-card-motion-relative','jiu-card-motion-skin','jiu-card-motion-clipped');
   }
   if(face)for(const {node} of layers){
    node.classList.remove('jiu-card-motion-part');
    node.style.removeProperty('--wb-card-origin');
    node.style.removeProperty('--jiu-card-motion-depth');
   }
   active=null;
   lifecycle.disconnect();
  }
  function clear(){
   cancelAnimationFrame(frame);
   pending=null;
   frame=0;
   reset();
  }
  const lifecycle=new MutationObserver(changes=>{
   const card=active?.card,modal=document.querySelector('dialog:modal');
   if(card&&(!card.isConnected||!card.getClientRects().length||card.closest('[hidden],[inert]')||
      (modal&&!modal.contains(card))||changes.some(change=>change.target===card&&
       ['aria-pressed','aria-current','data-playing','data-state'].includes(change.attributeName))))clear();
  });
  function enter(card){
   const rule=rules.find(item=>card.matches(item.selector));
   const layers=rule.parts.flatMap(([selector,depth])=>[...card.querySelectorAll(selector)].flatMap(node=>
    node instanceof HTMLElement&&!node.matches(controls)&&!node.querySelector(controls)&&
      !rule.stationary?.some(s=>node.matches(s)) ? [{node,depth}] : []));
   let face=null,primary=null;
   const plane=rule.plane&&card.querySelector(rule.plane);
   if(plane){
    face=document.createElement('span');
    face.className='jiu-card-motion-face';
    face.setAttribute('aria-hidden','true');
    plane.append(face);
    card.classList.add('jiu-card-motion-host');
   }else if(!rule.model){
    const css=getComputedStyle(card);
    // Check the base paint before moving it. If selected, restore it on exit.
    const skin=rule.skin!==false&&!card.hasAttribute('data-jiu-pressed');
    const positioned=css.position!=='static';
    face=document.createElement('span');
    face.className='jiu-card-motion-face';
    face.setAttribute('aria-hidden','true');
    if(skin){
     face.style.background=css.background;
     face.style.border=css.border;
     face.style.boxShadow=css.boxShadow;
    }
    card.classList.add('jiu-card-motion-host');
    card.classList.toggle('jiu-card-motion-relative',!positioned);
    card.classList.toggle('jiu-card-motion-skin',skin);
    card.classList.toggle('jiu-card-motion-clipped',!!rule.clipped);
    primary=rule.primary?card.querySelector(rule.primary):null;
    primary?.classList.add('jiu-card-motion-primary');
    card.append(face);
    for(const {node,depth} of layers){
     node.classList.add('jiu-card-motion-part');
     node.style.setProperty('--jiu-card-motion-depth',depth+'px');
    }
   }
   active={card,layers,face,primary};
   lifecycle.observe(root,{subtree:true,childList:true,attributes:true,attributeFilter:['hidden','inert','open','aria-pressed','aria-current','data-playing','data-state']});
  }
  function paint(){
   frame=0;
   const {card,clientX,clientY}=pending;
   pending=null;
   const rect=card.getBoundingClientRect();
   if(!eligible()||!card.isConnected||!rect.width||!rect.height){reset();return;}
   if(active?.card!==card){reset();enter(card);}
   const origins=active.layers.map(({node})=>{
    let x=rect.width/2,y=rect.height/2;
    for(let item=node;item&&item!==card;item=item.offsetParent){x-=item.offsetLeft;y-=item.offsetTop;}
    // A scroller is part of the stable layout, not of the transformed plane.
    for(let item=node.parentElement;item&&item!==card;item=item.parentElement){x+=item.scrollLeft;y+=item.scrollTop;}
    return (x+card.scrollLeft)+'px '+(y+card.scrollTop)+'px';
   });
   active.layers.forEach(({node},i)=>{
    if(node.style.getPropertyValue('--wb-card-origin')!==origins[i])node.style.setProperty('--wb-card-origin',origins[i]);
   });
   const x=Math.max(0,Math.min(1,(clientX-rect.left)/rect.width));
   const y=Math.max(0,Math.min(1,(clientY-rect.top)/rect.height));
   const dx=(2*x-1)*1.35,dy=2*y-1;
   // Keep the moving plane readable when the same treatment is used for wide rows.
   const longest=Math.max(rect.width,rect.height);
   const scale=active.face?Math.min(1,230/longest):1;
   if(active.face)card.style.setProperty('--jiu-card-motion-distance',Math.max(310,longest*1.35)+'px');
   const gain=scale/Math.max(1,Math.hypot(dx,dy));
   card.style.setProperty('--wb-card-pitch',(dy*gain*10).toFixed(2)+'deg');
   card.style.setProperty('--wb-card-yaw',(-dx*gain*14).toFixed(2)+'deg');
   card.style.setProperty('--wb-card-x',(x*100).toFixed(1)+'%');
   card.style.setProperty('--wb-card-y',(y*100).toFixed(1)+'%');
   card.setAttribute('data-card-hover','');
  }
  root.addEventListener('pointermove',event=>{
   if(event.pointerType!=='mouse'||!eligible())return;
   const card=find(event.target);
   if(!card||!root.contains(card))return;
   pending={card,clientX:event.clientX,clientY:event.clientY};
   if(!frame)frame=requestAnimationFrame(paint);
  },options);
  root.addEventListener('pointerout',event=>{
   const card=pending?.card||active?.card;
   if(card&&event.pointerType==='mouse'&&find(event.target)===card&&find(event.relatedTarget)!==card)clear();
  },options);
  for(const name of ['pointerleave','pointercancel','lostpointercapture'])root.addEventListener(name,clear,options);
  for(const mode of [hover,forced])mode.addEventListener('change',()=>{if(!eligible())clear();},options);
  root.addEventListener('scroll',clear,{...options,capture:true});
  window.addEventListener('blur',clear,options);
  window.addEventListener('pagehide',clear,options);
  document.addEventListener('visibilitychange',()=>{if(document.hidden)clear();},options);
  return {clear,dispose(){clear();signals.abort();}};
 }
 return {mount,style};
})();
''' +
    'JiuseraCardMotion.mount(document,' + json.dumps([{k:v for k,v in row.items() if k!='focus'} for row in FAMILIES],separators=(',',':')) + ');\n'
)
