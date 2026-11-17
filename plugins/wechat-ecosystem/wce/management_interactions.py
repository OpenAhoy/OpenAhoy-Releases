"""Presentation for the native management app's existing controls."""

STYLE = '''
body.oa-management.oa-native {
  --oa-hover-ring: light-dark(#20202425, #fff3);
  --oa-pressed-ring: light-dark(#20202445, #fff5);
  --oa-tip-bg: light-dark(#252328, #f2edf3);
  --oa-tip-ink: light-dark(#fff, #231f26);
}
.oa-management.oa-native :is(button, summary, .account[role=option]) {
  transition: background-color 120ms ease, box-shadow 100ms ease, color 120ms ease;
}
@media (hover:hover) and (pointer:fine) {
  .oa-management.oa-native :is(button,summary,.account[role=option]):hover:not(:disabled):not([aria-disabled=true]) {
    box-shadow: inset 0 0 0 1px var(--oa-hover-ring);
  }
  .oa-management.oa-native :is(#accounts .account[role=option]:not(.is-selected), #mediaMonitor .mm-row:not([aria-current=true])):hover {
    background: var(--oa-fill,var(--soft));
  }
}
.oa-management.oa-native :is(button, summary, .account[role=option]):active:not(:disabled):not([aria-disabled=true]) {
  translate: none;
  box-shadow: inset 0 1px 3px var(--oa-pressed-ring);
}
.oa-management.oa-native :is(.oa-nav button[aria-current=page], #mediaMonitor .mm-row[aria-current=true],
    #mediaMonitor nav button[aria-pressed=true], #monitorProviderTabs button[aria-pressed=true]) {
  background: var(--oa-selection,var(--tint));
  color: var(--oa-selected-ink,var(--ink));
}
.oa-management.oa-native :is(button,summary,a,input,select,textarea,.account[role=option]):focus-visible {
  outline: 2px solid var(--oa-focus,var(--accent));
  outline-offset: 2px;
}
.oa-management.oa-native :is(.mm-row,#accounts .account[role=option]):focus-visible {
  outline-offset: -2px;
}
.oa-management.oa-native button[aria-busy=true] {
  box-shadow: inset 0 -2px var(--oa-focus,var(--accent));
  cursor: progress;
  opacity: .76;
}
.oa-management.oa-native [role=status]:is(.error,[data-state=error]) {
  color: var(--danger,light-dark(#a53c46,#ffabb6));
  overflow-wrap: anywhere;
}
.oa-management #oaTooltip {
  position: fixed;
  z-index: 2000;
  inset: auto;
  margin: 0;
  padding: 5px 8px;
  max-width: min(260px, calc(100vw - 16px));
  max-height: calc(100dvh - 16px);
  box-sizing: border-box;
  border: 0;
  border-radius: 6px;
  background: var(--oa-tip-bg);
  color: var(--oa-tip-ink);
  box-shadow: 0 3px 10px #0003;
  font: 500 12px/1.42 system-ui,sans-serif;
  overflow: auto;
  overflow-wrap: anywhere;
}
@keyframes oa-control-enter {
  from { opacity: .86; }
  to { opacity: 1; }
}
@media (prefers-reduced-motion:no-preference) {
  .oa-management.oa-native :is(.oa-more-settings[open]>.oa-more-popover,
      .oa-account-menu[open]>div,.oa-task-menu[open]>.actions,
      .mm-facts[open]>:not(summary),dialog[open],#monitorBody>.mm-heading,#oaTooltip:popover-open) {
    animation: oa-control-enter 125ms ease-out both;
  }
}
@media (prefers-reduced-motion:reduce) {
  .oa-management.oa-native :is(button,summary, .account[role=option]) { transition: none !important; }
}
.oa-management.oa-native[data-oa-document-hidden] * {
  animation-play-state: paused !important;
  transition: none !important;
}
'''

SCRIPT = r'''
function mountOpenAhoyHints(){
  const tooltip=document.createElement('div');
  tooltip.id='oaTooltip';
  tooltip.setAttribute('role','tooltip');
  const canPopover=typeof tooltip.showPopover==='function';
  if(canPopover)tooltip.setAttribute('popover','manual');
  tooltip.hidden=true;
  document.body.append(tooltip);
  const sources='[data-oa-overflow],[data-oa-hint]';
  let anchor=null,timeout=0,visible=false;
  function hide(){
    clearTimeout(timeout);timeout=0;
    if(visible&&canPopover)tooltip.hidePopover();
    visible=false;tooltip.hidden=true;anchor=null;
  }
  function describe(el){
    if(!el||el.matches(':disabled,[aria-disabled=true]')||
       el.closest('[hidden],[inert],input,textarea,select,[contenteditable=true],details.oa-account-menu[open] > summary'))return '';
    if(el.dataset.oaOverflow!==undefined){
      const label=el.dataset.oaOverflow?el.querySelector(el.dataset.oaOverflow):el;
      if(!label||label.scrollWidth<=label.clientWidth+1)return '';
      return el.dataset.oaFullName||label.textContent.trim();
    }
    return el.getAttribute('aria-label')||el.dataset.oaHint||'';
  }
  function position(target){
    if(!target.isConnected||document.hidden||!target.getClientRects().length){hide();return;}
    const edge=8,gap=7,rect=target.getBoundingClientRect();
    if(rect.right<=0||rect.left>=innerWidth||rect.bottom<=0||rect.top>=innerHeight){hide();return;}
    const bounds=tooltip.getBoundingClientRect();
    const below=rect.bottom+gap;
    const top=below+bounds.height<=innerHeight-edge?below:rect.top-gap-bounds.height;
    tooltip.style.top=Math.max(edge,Math.min(innerHeight-edge-bounds.height,top))+'px';
    tooltip.style.left=Math.max(edge,Math.min(innerWidth-edge-bounds.width,rect.left+(rect.width-bounds.width)/2))+'px';
  }
  function schedule(el,delay){
    if(anchor===el)return;
    hide();
    if(!describe(el))return;
    anchor=el;
    timeout=setTimeout(()=>{
      const content=describe(el);
      if(!content||!el.isConnected||document.hidden){hide();return;}
      tooltip.textContent=content;tooltip.hidden=false;
      if(canPopover)tooltip.showPopover();
      visible=true;position(el);
    },delay);
  }
  function source(el){return el instanceof Element?el.closest(sources):null;}
  document.addEventListener('pointerover',event=>{
    if(event.pointerType==='mouse'||event.pointerType==='pen'){
      if(tooltip.contains(event.target)){clearTimeout(timeout);return;}
      const target=source(event.target);
      if(target&&source(event.relatedTarget)!==target)schedule(target,420);
    }
  });
  document.addEventListener('pointerout',event=>{
    if(!anchor||event.pointerType==='touch')return;
    if(event.target instanceof Node&&(anchor.contains(event.target)||tooltip.contains(event.target))&&
       !(event.relatedTarget instanceof Node&&(anchor.contains(event.relatedTarget)||tooltip.contains(event.relatedTarget)))){
      clearTimeout(timeout);
      if(visible)timeout=setTimeout(hide,180);else hide();
    }
  });
  document.addEventListener('focusin',event=>{
    const target=source(event.target);
    if(target?.matches(':focus-visible'))schedule(target,160);else if(anchor!==target)hide();
  });
  document.addEventListener('focusout',event=>{if(anchor?.contains(event.target))hide();});
  document.addEventListener('keydown',event=>{
    if(event.key==='Escape'&&anchor){if(visible){event.preventDefault();event.stopPropagation();}hide();}
  },true);
  document.addEventListener('pointerdown',hide,true);
  document.addEventListener('scroll',hide,true);
  addEventListener('resize',hide);
  addEventListener('pagehide',hide);
  document.addEventListener('visibilitychange',()=>{
    document.body.toggleAttribute('data-oa-document-hidden',document.hidden);
    if(document.hidden)hide();
  });
}
'''
