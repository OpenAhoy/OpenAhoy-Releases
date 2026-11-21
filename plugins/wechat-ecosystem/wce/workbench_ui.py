"""Presentation for the embedded Jiusera work surfaces."""

from .own_branding import _PACKAGE, jiusera_header


def trend_resource(suffix):
    return '\n'.join((_PACKAGE / 'assets' / 'management' / (name + '.' + suffix)).read_text(encoding='utf-8')
                     for name in ('workbench-trend', 'workbench-home'))


def chrome(icon):
    return '''<header class="wb-titlebar">
 <button id="wbBrand" type="button" aria-label="Jiusera 作品首页">'''+jiusera_header()+'''</button>
 <span class="wb-face" aria-hidden="true"><span>•</span>‿<span>•</span></span>
 <button id="wbHomeUpdate" type="button" hidden disabled aria-describedby="wbHomeUpdateStatus">
  <span id="wbHomeRunning"></span><span id="wbHomeUpdateHint"></span>
 </button>
 <span id="wbHomeUpdateStatus" class="jh-screenreader" role="status"></span>
 <div id="wbCanvasControls" class="wb-context" hidden>
  <button id="wbProject" aria-expanded="false" aria-controls="directorWorkbar" type="button">项目与作品</button>
  <button id="wbShot" aria-expanded="false" aria-controls="wbCanvasDetails" type="button">镜头</button>
 </div>
</header>
<div class="wb-dock-wrap">
 <nav class="wb-dock" aria-label="Jiusera 工作台导航">
  <button class="wb-dock-brand" data-wb-route="published" type="button" aria-label="Jiusera 作品首页">'''+jiusera_header()+'''</button>
  <button data-wb-route="jiusera-monitor" type="button">'''+icon('video')+'''<span>监看</span></button>
  <button data-wb-route="jiusera-canvas" type="button">'''+icon('settings')+'''<span>画布</span></button>
  <button data-wb-route="jiusera-assets" type="button">'''+icon('accounts')+'''<span>资产</span></button>
  <button id="wbMore" type="button" aria-expanded="false" aria-controls="wbMenu"><span aria-hidden="true">···</span><span>更多</span></button>
 </nav>
 <section id="wbMenu" aria-label="更多入口" hidden>
  <button type="button" data-wb-route="about">关于与设置</button>
  <button type="button" data-wb-route="studio-showcase">演播室案例</button>
  <div class="wb-publisher">'''+jiusera_header()+'''<span>发布与账号</span></div>
  <div id="wbPlatformLinks"></div>
 </section>
</div>'''


SURFACES = '''
<section id="wbStartup" aria-label="Jiusera">
 <div class="wb-startup-center">
  <h1 id="wbStartupTitle">Jiusera</h1>
  <p id="wbStartupStatus" role="status">正在连接工作台…</p>
 </div>
</section>
<section id="wbPublished" aria-labelledby="wbPublishedTitle" hidden>
 <div class="jh">
  <h1 id="wbPublishedTitle" class="jh-screenreader" tabindex="-1">Jiusera 作品首页</h1>
  <div id="wbOverview" class="jh-strip">
   <div class="jh-scope">
    <div id="wbPlatformCoverage" class="jh-platforms" aria-label="筛选平台"></div>
    <select id="wbPublishedPlatform" aria-label="筛选平台" hidden></select>
    <select id="wbPublishedAccount" aria-label="筛选账号" hidden></select>
    <span id="wbCoverage" class="jh-screenreader" role="status"></span>
   </div>
   <div class="jh-tools">
    <button id="wbClearScope" type="button" hidden>全部账号</button>
    <button id="wbPublishedRefresh" type="button" disabled>读取统计</button>
   </div>
  </div>
  <section id="wbComparisonTrend" class="jh-trend" aria-label="日阅读趋势"></section>
  <section class="jh-works" aria-labelledby="wbRankTitle">
   <header class="jh-works-head">
    <div class="jh-works-heading"><h2 id="wbRankTitle">近期爆款</h2><span class="jh-work-meta" id="wbRankPeriod"></span></div>
    <div class="jh-works-nav">
      <button type="button" class="jh-work-step" data-platform-prev>‹</button>
      <button type="button" class="jh-work-step" data-platform-next>›</button>
    </div>
   </header>
   <div id="wbPublishedCards" class="jh-platform-board" data-platform-works aria-label="分平台作品排行"></div>
   <p id="wbPublishedState" class="jh-empty" role="status"></p>
  </section>
 </div>
</section>
'''


STYLE = '''
body.oa-management.oa-native[data-workbench]{
 --wb-surface:#f1f1f0;--wb-float:#fbfbfaed;--wb-ink:#232624;--wb-line:#2222;
 --wb-depth:0 7px 28px #00000015;--wb-dock:70px;--wb-top:64px;
}
body.oa-management.oa-native[data-color-scheme=dark][data-workbench]{
 --wb-surface:#202122;--wb-float:#292a2bef;--wb-ink:#f2f3f2;--wb-line:#fff2;
 --wb-depth:0 7px 28px #0007;
}
@media(prefers-color-scheme:dark){
 body.oa-management.oa-native:not([data-color-scheme])[data-workbench]{
  --wb-surface:#202122;--wb-float:#292a2bef;--wb-ink:#f2f3f2;--wb-line:#fff2;--wb-depth:0 7px 28px #0007;
 }
}
.oa-native[data-workbench]:not(.oa-platform-view) .oa-shell{
 display:block;width:100%;height:100dvh;min-height:0;max-width:none;margin:0;overflow:hidden;background:var(--wb-surface)
}
.oa-native[data-workbench]:not(.oa-platform-view) .oa-sidebar{display:none}
.oa-management.oa-native[data-workbench]:not(.oa-platform-view) .oa-content{
 display:flex;flex-direction:column;width:100%;height:100%;min-height:0;max-width:none;margin:0;
 padding:0;overflow:hidden;background:var(--wb-surface)
}
.wb-titlebar{
 position:fixed;z-index:20;inset:9px 13px auto;display:grid;grid-template-columns:1fr auto 1fr;
 align-items:start;gap:8px;pointer-events:none
}
.wb-titlebar>*{pointer-events:auto}
.oa-native .wb-titlebar #wbBrand{
 justify-self:start;padding:4px;min-height:34px;border:0;box-shadow:none;background:transparent
}
.oa-native .wb-titlebar #wbBrand .oa-brand-logo{width:105px;margin:0}
.wb-face{justify-self:center;line-height:34px;letter-spacing:.11em;font-size:18px;color:var(--wb-ink);pointer-events:none;user-select:none}
.wb-face span{display:inline-block;animation:wb-blink 7s infinite}
@keyframes wb-blink{0%,52%,57%,100%{transform:scaleY(1)}54%,55%{transform:scaleY(.16)}}
@media(prefers-reduced-motion:reduce){.wb-face span{animation:none}}
.wb-context{display:flex;align-items:center;flex-wrap:wrap;gap:5px}
#wbCanvasControls{justify-self:end;justify-content:end}
.oa-native :is(.wb-context,.wb-published-tools) button{
 min-height:32px;padding:4px 9px;font-size:12px;border-radius:10px;
 color:var(--wb-ink);border:1px solid var(--wb-line);background:var(--wb-float);box-shadow:none
}
.oa-platform-view .wb-titlebar{display:none}
.oa-native.oa-platform-view .oa-content{padding-block-end:var(--wb-dock)}
.oa-native.oa-platform-view .oa-sidebar :is(#jiuseraNav,#openWorkflowGuide,#wechatCompactUpdates){display:none!important}
.wb-dock-wrap{position:fixed;z-index:30;inset:auto 0 max(12px,env(safe-area-inset-bottom));width:max-content;max-width:calc(100% - 20px);margin-inline:auto}
.wb-dock-wrap:has(#wbMenu:not([hidden])){z-index:1000}
.wb-dock{display:flex;align-items:center;gap:3px;padding:5px;border:1px solid var(--wb-line);border-radius:99px;color:var(--wb-ink);background:var(--wb-float);box-shadow:var(--wb-depth)}
.oa-management .wb-dock .wb-dock-brand .oa-brand-logo{width:63px;margin:0}
.oa-management .wb-dock button{height:36px;min-height:36px;gap:6px;padding:5px 12px;border:0;border-radius:99px;box-shadow:none;color:inherit;background:transparent}
.oa-management .wb-dock button[aria-current=page],.oa-management .wb-dock button[aria-expanded=true],.oa-management .wb-dock button[data-current]{background:var(--oa-selection,var(--soft));color:var(--oa-selected-ink,var(--ink))}
#wbMenu{position:absolute;right:0;bottom:calc(100% + 8px);width:min(260px,calc(100vw - 20px));max-height:65dvh;overflow:auto;padding:9px;border:1px solid var(--wb-line);border-radius:17px;color:var(--wb-ink);background:var(--wb-float);box-shadow:var(--wb-depth)}
.oa-management #wbMenu button{width:100%;justify-content:flex-start;box-shadow:none;border:0;background:transparent}
.wb-publisher{display:flex;align-items:center;gap:9px;margin:7px 0 3px;padding:8px 6px 2px;border-top:1px solid var(--wb-line);font-size:12px}
.wb-publisher .oa-brand-logo{width:73px;margin:0}
.oa-native :is(#wbStartup,#wbPublished){
 position:relative;width:100%;height:100%;min-height:0;min-width:0;background:var(--wb-surface);color:var(--wb-ink)
}
.wb-startup-center{position:absolute;inset:50% auto auto 50%;transform:translate(-50%,-50%);text-align:center}
.wb-startup-center h1{font-size:16px;margin:0}
.wb-startup-center p{color:var(--muted);margin:5px 0}
.oa-management.oa-native[data-workbench]:not(.oa-platform-view) #mediaStudio{
 width:100%;height:100%;min-height:0;max-width:none;margin:0;padding:0
}
.oa-management.oa-native[data-workbench]:not(.oa-platform-view) #videoDirectorDesk{
 width:100%;height:100%;min-height:0;max-width:none;margin:0;
 padding:var(--wb-top) clamp(14px,3vw,38px) var(--wb-dock);overflow:auto;scrollbar-gutter:stable
}
.oa-management.oa-native[data-workbench=canvas] #videoDirectorDesk{padding:0;overflow:visible}
.oa-management.oa-native[data-workbench=monitor] #videoDirectorDesk{
 display:flex;flex-direction:column;overflow:hidden;padding-inline:clamp(8px,1.3vw,20px);gap:6px
}
[data-workbench=monitor] #directorMonitor:not([hidden]),
[data-workbench=monitor] #articleWork:not([hidden]){flex:1;min-height:0;height:100%}
[data-workbench=monitor] #directorMonitor{align-items:stretch;align-content:stretch;grid-template-rows:minmax(0,1fr)}
[data-workbench=monitor] #directorMonitor .dm-main{grid-template-rows:auto auto minmax(0,1fr);min-height:0}
[data-workbench=monitor] #directorMonitor .dm-sidebar{overflow:auto;min-height:0}
[data-workbench=monitor] #dmScreen{grid-row:3;min-height:0;overflow:auto}
[data-workbench=monitor] #dmScreen video,[data-workbench=monitor] #dmScreen .oa-frame-screen,
[data-workbench=monitor] #dmScreen .oa-video-poster,[data-workbench=monitor] #dmScreen[data-kind=image]>img{
 max-height:100%;height:auto;object-fit:contain
}
[data-workbench=monitor] #dmScreen .dm-screen-empty{height:100%;max-height:none;aspect-ratio:auto}
[data-workbench=monitor] #videoDirectorDesk .dd-footer:has(#directorStatus:empty):has(#directorCopy[hidden]){display:none}
[data-workbench=canvas][data-workbench-article] #directorBoard{display:none}
@media(max-width:840px){
 [data-workbench=monitor] #directorMonitor{grid-template-rows:minmax(0,1fr) minmax(55px,24%)}
}
#directorChatWorkMenu,#directorRefreshMenu{display:none}
@media(max-width:650px){
 .oa-management.oa-native[data-workbench=monitor]:not(.oa-platform-view) #videoDirectorDesk{
   padding-top:54px;padding-bottom:60px;gap:5px
 }
 [data-workbench=monitor] #videoDirectorDesk .dd-workbar{display:block;margin:0;padding:0}
 [data-workbench=monitor] #videoDirectorDesk .dd-projects{
   display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:6px
 }
 [data-workbench=monitor] #videoDirectorDesk .dd-projects label{display:flex!important;gap:4px;min-width:0}
 [data-workbench=monitor] #videoDirectorDesk .dd-projects select{flex:1;width:0;min-width:0}
 [data-workbench=monitor] #directorChatWork,[data-workbench=monitor] #directorRefresh{display:none!important}
 [data-workbench=monitor] #directorChatWorkMenu,[data-workbench=monitor] #directorRefreshMenu{display:block}
 [data-workbench=monitor] #directorTitle{font-size:16px}
 [data-workbench=monitor] #directorWorkbar>.dd-actions{display:none}
}
.oa-native[data-workbench=canvas] #videoDirectorDesk > .dd-toolbar{
 position:fixed;inset:auto 13px calc(var(--wb-dock) + 4px) auto;z-index:12;justify-content:flex-end;
}
.oa-native[data-workbench=canvas] #directorTitle,.oa-native[data-workbench=canvas] #directorWorkHint{
 position:absolute;width:1px;height:1px;padding:0;clip-path:inset(50%);white-space:nowrap;overflow:hidden
}
.oa-native[data-workbench=canvas] #videoDirectorDesk .dd-toolbar .dd-actions{gap:4px}
.oa-native[data-workbench=canvas] #directorMore:not([hidden]){margin:0}
.oa-native[data-workbench=canvas] #directorMore .dd-more-menu{top:auto;bottom:calc(100% + 4px)}
.oa-native[data-workbench=canvas] #directorWorkbar,.oa-native[data-workbench=canvas] #wbCanvasDetails{
 position:fixed;z-index:15;top:48px;right:12px;width:min(382px,calc(100% - 24px));
 max-height:calc(100dvh - 130px);overflow:auto;background:var(--wb-float);color:var(--wb-ink);
 border:1px solid var(--wb-line);border-radius:15px;padding:11px;box-shadow:var(--wb-depth)
}
.oa-native[data-workbench=canvas]:not([data-workbench-panel=project]) #directorWorkbar,
.oa-native[data-workbench=canvas]:not([data-workbench-panel=shot]) #wbCanvasDetails{display:none}
.oa-native[data-workbench=canvas] #directorWorkbar .dd-projects{width:100%;display:grid;grid-template-columns:repeat(2,minmax(0,1fr))}
.oa-native[data-workbench=canvas] #directorWorkbar .dd-projects label{display:grid!important;min-width:0}
.oa-native[data-workbench=canvas] #directorWorkbar .dd-projects select{width:100%!important}
.oa-native[data-workbench=canvas] #directorWorkbar #directorChatWork{grid-column:1/-1;justify-self:start}
.oa-native[data-workbench=canvas] #wbCanvasDetails{display:grid;gap:7px}
.oa-native[data-workbench=canvas] #wbCanvasDetails .dd-scenes{display:grid}
.oa-native[data-workbench=canvas] #wbCanvasDetails .dd-view{min-height:unset}
.oa-native[data-workbench=canvas] #wbCanvasDetails .dd-scene-select{display:flex!important}
.oa-native[data-workbench=canvas] #directorSceneList{display:none}
.oa-native[data-workbench=canvas] #directorBoard{display:contents}
.oa-native[data-workbench=canvas] #directorCanvas{
 position:fixed;inset:0;width:100%;height:100%;min-height:0;border:0;border-radius:0;
 background-color:var(--wb-surface);--dd-grid:color-mix(in srgb,var(--wb-ink) 13%,transparent)
}
.oa-native[data-workbench=canvas] #directorCanvasMap{bottom:calc(var(--wb-dock) + 48px)}
.oa-native[data-workbench=canvas] .dd-canvas-toolbar{position:fixed;display:contents}
.oa-native[data-workbench=canvas] .dd-canvas-toolbar>.dd-actions{
 position:fixed;z-index:10;justify-content:center;width:max-content;max-width:calc(100% - 24px);gap:4px;
 padding:4px;border:1px solid var(--wb-line);border-radius:12px;background:var(--wb-float);box-shadow:var(--wb-depth)
}
.oa-native[data-workbench=canvas] .dd-canvas-toolbar>.dd-actions:first-child{left:50%;top:48px;transform:translateX(-50%)}
.oa-native[data-workbench=canvas]:not([data-workbench-has-work]) :is(.dd-canvas-toolbar>.dd-actions:first-child,#wbShot,#directorSound,#directorCanvasLocate,#directorCanvasMapToggle,#directorCanvasHand){display:none}
.oa-native[data-workbench=canvas] .dd-canvas-toolbar>.dd-actions:last-child{left:12px;bottom:calc(var(--wb-dock) + 4px);justify-content:flex-start}
.oa-native[data-workbench=canvas] .dd-canvas-toolbar>.dd-actions button{min-height:28px;font-size:11px;padding:2px 7px;box-shadow:none}
.oa-native[data-workbench=canvas] #wbCanvasEmptyActions{
 position:absolute;display:grid;justify-items:center;gap:5px;margin:0;top:50%;left:50%;transform:translate(-50%,-50%);width:max-content;max-width:85vw;text-align:center
}
.oa-native[data-workbench=canvas] #wbCanvasEmptyActions #directorCanvasEmpty{position:static;margin:0;font-size:12px}
.oa-native[data-workbench=canvas] #wbCanvasStart{
 width:54px;height:54px;padding:0;border-radius:17px;background:var(--wb-float);box-shadow:none;border-color:var(--wb-line);font-size:27px;color:var(--muted)
}
.oa-native[data-workbench=canvas] .dd-footer{position:fixed;z-index:10;left:13px;bottom:calc(var(--wb-dock) + 46px);max-width:min(460px,calc(100% - 26px))}
.oa-native[data-workbench=canvas] #directorStatus:not(:empty){padding:3px 7px;border-radius:7px;background:var(--wb-float)}
.oa-native[data-workbench=canvas] #directorCanvasFeedback{position:fixed;z-index:10;bottom:calc(var(--wb-dock) + 75px);left:13px;background:var(--wb-float);padding:3px 7px;border-radius:7px}
.oa-native #openAhoyHome{
 height:100%;min-height:0;width:100%;max-width:none;align-self:stretch;overflow:auto;
 padding:var(--wb-top) clamp(14px,5vw,54px) var(--wb-dock)
}
.oa-native #openAhoyHome>*{max-width:1030px;margin-inline:auto}
.oa-native #openAhoyHome .oa-home-features{margin-top:13px}
.oa-native #openAhoyHome h1{font-size:25px;margin:0;color:var(--wb-ink)}
.wb-about-card{border:1px solid var(--wb-line);border-radius:16px;padding:17px;background:var(--wb-float)}
.wb-about-card p{margin-block:5px;color:var(--muted)}
.wb-about-grid{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:10px;margin-top:13px}
.wb-about-grid>.wb-about-card{min-width:0}
.wb-about-grid #softwareUpdateSlot{margin-top:7px}
.wb-about-grid #wbSupportSlot .oa-support-links{border:0;padding-top:4px}
 .oa-native #wbPublished{display:block;overflow:clip}
 .oa-native #wbPublished .jh{--jh-head:55px}
 .oa-native #wbPublished .jh-platforms{overflow:auto hidden;scrollbar-width:thin}
 .oa-native #wbPublished .jh-scope{overflow:hidden}
 .oa-management #wbPlatformCoverage button{gap:4px;flex:none;padding:2px 6px;min-height:23px;
  border-radius:6px;background:transparent;box-shadow:none;border:1px solid var(--line);font-size:10px}
 #wbPlatformCoverage button[aria-pressed=true]{color:var(--accent);border-color:var(--accent)}
 #wbPlatformCoverage .oa-platform-mark{width:14px;height:14px;flex-basis:14px;padding:2px}
 #wbPlatformCoverage .oa-platform-logo{width:10px;height:10px}
 #wbPublished .jh-platform-work .jh-rank-scope>div{max-height:140px}
 @media(max-height:550px){.oa-native #wbPublished .jh{--jh-head:43px}}
 @media(max-width:650px){.oa-native #wbPublished .jh{--jh-head:45px}}
@media(max-width:699px){
 .oa-native[data-workbench=canvas] .dd-canvas-toolbar>.dd-actions:last-child{bottom:calc(var(--wb-dock) + 38px)}
 .oa-native[data-workbench=canvas]:not([data-workbench-has-work]) .dd-canvas-toolbar>.dd-actions:last-child{bottom:calc(var(--wb-dock) + 4px)}
 .oa-native[data-workbench=canvas] .dd-footer{bottom:calc(var(--wb-dock) + 78px)}
 .oa-native[data-workbench=canvas] #directorCanvasFeedback{bottom:calc(var(--wb-dock) + 103px)}
 .wb-about-grid{grid-template-columns:1fr}
}
@media(max-width:380px){
 .oa-native .wb-titlebar #wbBrand .oa-brand-logo{width:80px}
 .wb-context{gap:2px}
 .oa-native .wb-context button{font-size:11px;padding-inline:5px}
 .oa-management .wb-dock button{padding-inline:7px}
 .oa-management .wb-dock .wb-dock-brand .oa-brand-logo{width:52px}
}
@media(max-width:470px){
 .oa-management .wb-dock button{padding-inline:7px;font-size:11px}
 .oa-management .wb-dock button .oa-icon{width:13px;height:13px;flex-basis:13px}
}
'''

SCRIPT = r'''
function OAWorkbench({open, readAnalytics, openLink, accountName, platformName, platformDirectoryIcon}){
 const $=id=>document.getElementById(id),body=document.body,home=$('wbBrand');
 const dock=document.querySelector('.wb-dock'), menu=$('wbMenu'), more=$('wbMore');
 const selector=$('wbPublishedAccount'),platformSelector=$('wbPublishedPlatform');
 const state=$('wbPublishedState');
 const trend=JiuseraTrend($('wbComparisonTrend'),key=>OAUI.format(key));
 const gallery=JiuseraPlatformWorks($('wbPublished'),{render:renderWork,
   meta:row=>OAUI.format('阅读 {0}',[formatCount(row.traffic)]),t:key=>OAUI.format(key)});
 const supported=new Set(['BOUND','BOUND_IDLE','CONNECTED','BUSY']);
 const newElement=(tag,text)=>{const node=document.createElement(tag);if(text)OAUI.set(node,text);return node;};
 let surface='startup',bound=[],platforms=new Map(),checkedAccounts=false,accountKey='',activeRead=0,loading=false;
 const reports=new Map();
 const key=row=>JSON.stringify([row.platform_id,row.connection_id,row.account_id,row.binding_revision]);
 const selected=()=>bound.find(row=>key(row)===accountKey);
 const canRead=row=>row?.platform_id==='wechat_official_account'&&supported.has(row.state);
 const scoped=()=>selected()?[selected()]:bound.filter(row=>!platformSelector.value||row.platform_id===platformSelector.value);
 const accountReport=()=>reports.get(accountKey);
 const platformLabel=id=>platformName(id)||platforms.get(id)||id;
 const formatCount=value=>Number.isFinite(value)?new Intl.NumberFormat().format(value):'—';
 const viewStorage='jiusera.workbench.published.';
 const fingerprint=value=>{
   let hash=2166136261;
   for(let index=0;index<value.length;index++)hash=Math.imul(hash^value.charCodeAt(index),16777619);
   return (hash>>>0).toString(36);
 };
 function rememberAccount(){
   try{
     if(accountKey)localStorage.setItem(viewStorage+'active',fingerprint(accountKey));
     else localStorage.removeItem(viewStorage+'active');
   }catch(_){}
 }

 function closeMenu(focus=false){
   menu.hidden=true;more.setAttribute('aria-expanded','false');
   if(focus)more.focus();
 }
 function panel(key=''){
   body.dataset.workbenchPanel=key;
   $('wbProject').setAttribute('aria-expanded',String(key==='project'));
   $('wbShot').setAttribute('aria-expanded',String(key==='shot'));
 }
 for(const [id,target] of [['wbProject','project'],['wbShot','shot']]){
   $(id).onclick=()=>{closeMenu();panel(body.dataset.workbenchPanel===target?'':target);};
 }
 home.onclick=()=>open('published');
 more.onclick=()=>{
   if(!menu.hidden){closeMenu(true);return;}
   panel();menu.hidden=false;more.setAttribute('aria-expanded','true');menu.querySelector('button')?.focus();
 };
 document.addEventListener('click',event=>{
   if(!menu.hidden&&!event.target.closest('.wb-dock-wrap'))closeMenu();
   const current=body.dataset.workbenchPanel;
   if(current&&!event.target.closest('#wbCanvasControls,#directorWorkbar,#wbCanvasDetails,dialog'))panel();
 });
 document.addEventListener('keydown',event=>{
   if(event.key!=='Escape'||event.defaultPrevented||document.querySelector('dialog[open]'))return;
   if(!menu.hidden){event.preventDefault();closeMenu(true);return;}
   if(body.dataset.workbenchPanel){event.preventDefault();const trigger=body.dataset.workbenchPanel==='project'?'wbProject':'wbShot';panel();$(trigger).focus();}
 });
 document.addEventListener('click',event=>{
   const route=event.target.closest('[data-wb-route]')?.dataset.wbRoute;
   if(route){closeMenu();open(route);}
 });

 function paint(next,{showCanvas=false}={}){
   if(surface!==next){
     closeMenu();panel();
     if(next!=='published'&&loading){activeRead++;loading=false;}
     if(next!=='published')gallery.pause();
   }
   surface=next;
   body.dataset.workbench=next;
   $('wbStartup').hidden=next!=='startup';
   $('wbPublished').hidden=next!=='published';
   $('wbHomeUpdate').hidden=next!=='published';
   $('wbCanvasControls').hidden=!showCanvas;
   for(const button of dock.querySelectorAll('[data-wb-route]')){
     const active={canvas:'jiusera-canvas',monitor:'jiusera-monitor',published:'published',assets:'jiusera-assets'}[next];
     if(button.dataset.wbRoute===active)button.setAttribute('aria-current','page');else button.removeAttribute('aria-current');
   }
   more.toggleAttribute('data-current',next==='about'||next==='platform');
   if(next==='published'){restoreAccount();paintPublished();}
 }
 function options(){
   const retained=platformSelector.value;
   const all=newElement('option','全部平台');all.value='';
   platformSelector.replaceChildren(all);
   for(const id of platforms.keys()){
     const item=newElement('option');item.value=id;OAUI.set(item,platformLabel(id));platformSelector.append(item);
   }
   platformSelector.value=platforms.has(retained)?retained:'';
   const accounts=bound.filter(row=>!platformSelector.value||row.platform_id===platformSelector.value);
   const every=newElement('option','全部账号');every.value='';selector.replaceChildren(every);
   for(const row of accounts){
     const option=newElement('option');option.value=key(row);OAUI.raw(option,accountName(row));selector.append(option);
   }
   selector.value=accountKey;
   selector.disabled=!accounts.length;
 }
 function paintAccounts(rows,directory){
   const before=selected();
   checkedAccounts=true;
   bound=rows;
   platforms=new Map(directory.map(row=>[row.id,row.name]));
   for(const row of bound)if(!platforms.has(row.platform_id))platforms.set(row.platform_id,row.platform_id);
   const live=new Set(bound.map(key));
   for(const id of reports.keys())if(!live.has(id))reports.delete(id);
   if(before&&!selected()){clearAccount();rememberAccount();}
   if(surface==='published'){restoreAccount();paintPublished();}
 }
 function restoreAccount(){
   if(accountKey){options();return;}
   try{
     const remembered=localStorage.getItem(viewStorage+'active');
     const row=bound.find(item=>fingerprint(key(item))===remembered);
     if(row){accountKey=key(row);platformSelector.value=row.platform_id;}
   }catch(_){}
   options();
   if(selected()&&platformSelector.value!==selected().platform_id){
     platformSelector.value=selected().platform_id;options();
   }
 }
 function clearAccount(){
   accountKey='';
 }
 function chooseAccount(row){
   clearAccount();
   if(row){
     platformSelector.value=row.platform_id;
     accountKey=key(row);
   }
   rememberAccount();options();paintPublished();
 }
 platformSelector.onchange=()=>{clearAccount();rememberAccount();options();paintPublished();};
 selector.onchange=()=>chooseAccount(bound.find(row=>key(row)===selector.value));
 $('wbClearScope').onclick=()=>{
   platformSelector.value='';chooseAccount();
   $('wbPublishedRefresh').focus({preventScroll:true});
 };

 const platformMark={wechat_official_account:'公',x:'X',xiaohongshu:'红'};
 const styleKey=row=>JSON.stringify([row.platform_id,row.connection_id,row.account_id]);
 function workDays(){
   const end=[...reports.values()].map(value=>value.span?.end).filter(Boolean).sort().at(-1);
   return {end,days:[...reports.values()].find(value=>value.span?.end===end)?.timeline?.map(item=>item.date)||[]};
 }
 function summary(days,end){
   const scope=scoped();
   const byAccount=scope.map(row=>[row,reports.get(key(row))]);
   OAUI.set($('wbCoverage'),checkedAccounts?'{0} 个账号 · {1} 个已查询':'正在读取账号…',
     scope.length,byAccount.filter(([,value])=>!!value).length);
   const container=$('wbPlatformCoverage');
   container.replaceChildren();
   for(const id of new Set(bound.map(row=>row.platform_id))){
     const chip=newElement('button');chip.type='button';
     chip.setAttribute('aria-pressed',String(platformSelector.value===id));
     platformDirectoryIcon(chip,id,platformLabel(id));
     chip.onclick=()=>{platformSelector.value=platformSelector.value===id?'':id;platformSelector.onchange();};
     container.append(chip);
   }
   $('wbClearScope').hidden=!accountKey&&!platformSelector.value;
   const accounts=byAccount.map(([row,value])=>{
     const timeline=value?.span?.end===end?value?.timeline:null;
     return {id:key(row),styleKey:styleKey(row),
       label:accountName(row),platform:row.platform_id,platformLabel:OAUI.format(platformLabel(row.platform_id)),
       mark:platformMark[row.platform_id],values:days.map(date=>{
         const reported=timeline?.find(day=>day.date===date)?.read_user;
         return Number.isFinite(reported)?reported:null;
       })};
   });
   trend.update({title:OAUI.format('日阅读趋势'),
     hint:OAUI.format(end?'断线为缺报':'读取统计后显示公众号日报。'),
     dates:days,account:accounts,identities:bound.map(row=>({platform:row.platform_id,styleKey:styleKey(row)})),selected:accountKey,select:id=>{
       const row=bound.find(account=>key(account)===id);
       if(row&&accountKey!==id){chooseAccount(row);$('wbClearScope').focus({preventScroll:true});}
       else if(accountKey===id)$('wbClearScope').click();
     }});
 }
 function renderWork(row){
   const card=newElement('article');card.className='wb-published-card';
   const copy=newElement('div');copy.className='jh-work-copy';
   const account=newElement('p');account.className='jh-work-meta';OAUI.raw(account,row.account+' · '+row.published);
   const title=newElement('h3');OAUI.raw(title,row.title);
   const metric=newElement('p');metric.className='jh-work-metrics';
   OAUI.set(metric,row.stat_date?'累计阅读人数 {0} · 截至 {1}':'累计阅读人数 {0}',formatCount(row.traffic),row.stat_date);
   copy.append(account,title,metric);
   if(/^https:\/\/mp\.weixin\.qq\.com\/(?:s[/?]|s$)/.test(row.url||'')){
     const link=newElement('button','打开原文');link.type='button';link.className='jh-work-action';
     link.onclick=async()=>{try{await openLink(row.url);}catch(_){OAUI.set(state,'宿主暂时无法打开原文。');state.hidden=false;}};
     copy.append(link);
   }
   card.append(copy);
   return card;
 }
 function renderRanking(days,end){
   const start=days.at(0);
   const ids=new Set(bound.map(row=>row.platform_id));
   const period=$('wbRankPeriod');
   OAUI.raw(period,start&&end?start.slice(-5).replace('-','/')+'–'+end.slice(-5).replace('-','/'):OAUI.format('近 7 天'));
   const groups=[...ids].map(id=>{
     const connected=bound.filter(row=>row.platform_id===id);
     const records=connected.flatMap(row=>(reports.get(key(row))?.items||[]).map((item,index)=>({...item,
       id:JSON.stringify([key(row),item.published,item.url||item.title,index]),
       account:accountName(row),traffic:item.read_user})));
     const ranked=start&&end?JiuseraRank(records,start,end):{known:[],missing:[]};
     const eligible=connected.filter(canRead);
     const reported=eligible.filter(row=>reports.get(key(row))?.articleKnown).length;
     const note=eligible.length?OAUI.format('已读 {0}/{1} 个公众号。单号最多回读 4 个发表日、40 条；数值为截至各稿统计日的累计阅读人数。',[reported,eligible.length]):
       OAUI.format('当前没有可用于排名的作品流量来源。');
     return {id,label:OAUI.format(platformLabel(id)),...ranked,note,
       empty:OAUI.format(!eligible.length?'暂无可读作品流量':loading?'正在读取发表统计…':reported?'暂无已报流量作品':'读取统计后查看作品排行')};
   });
   gallery.setPlatforms(groups);
   state.hidden=groups.length>0;
   if(!groups.length)OAUI.set(state,checkedAccounts?'绑定账号后可查看作品表现。':'正在读取账号…');
 }
 function paintPublished(){
   const eligible=bound.filter(canRead);
   const have=eligible.filter(row=>reports.get(key(row))&&!reports.get(key(row)).error);
   $('wbPublishedRefresh').disabled=!eligible.length||loading;
   OAUI.set($('wbPublishedRefresh'),loading?'正在读取…':have.length===eligible.length&&eligible.length?'刷新统计':'读取统计');
   const {days,end}=workDays();
   summary(days,end);
   renderRanking(days,end);
 }
 async function readScopedAccount(row,refresh,alive){
   const expected=key(row);
   const current=()=>alive()&&bound.some(account=>key(account)===expected&&canRead(account));
   try{
     const value=await readAnalytics({connection_id:row.connection_id,days:7,refresh,
       ...(row.binding_revision?{binding_revision:row.binding_revision}:{})});
     if(!current())return;
     if(value?.connection_id!==row.connection_id||value?.days!==7||
       (row.binding_revision&&value.binding_revision!==row.binding_revision)||!Array.isArray(value?.articles)||
       !Array.isArray(value?.timeline))throw Error('INVALID_PUBLISHED_RESULT');
     const items=value.articles.filter(item=>typeof item?.title==='string'&&typeof item.published==='string');
     const report=value.status?.getarticletotaldetail?.states||[];
     const span=/^\d{4}-\d{2}-\d{2}$/.test(value.end||'')?{end:value.end}:null;
     const articleKnown=items.length>0||(report.length>0&&report.every(item=>['EMPTY','READY'].includes(item)));
     const error=report.some(item=>!['EMPTY','READY'].includes(item));
     const previous=reports.get(expected);
     reports.set(expected,{
       items:!articleKnown&&previous?.articleKnown?previous.items:items,
       articleKnown,span,timeline:value.timeline,readAt:value.read_at,error,
     });
   }catch(_){
     if(current()){const previous=reports.get(expected);reports.set(expected,{...previous,error:true});}
   }
 }
 async function fetchPublished(){
   const eligible=bound.filter(canRead);
   if(!eligible.length||loading)return;
   const missing=eligible.filter(row=>!reports.has(key(row))||reports.get(key(row)).error);
   const queue=(missing.length?missing:eligible).values(),refresh=!missing.length;
   const ticket=++activeRead,alive=()=>ticket===activeRead&&surface==='published';
   loading=true;paintPublished();
   async function readNext(){
     for(const row of queue){
       if(!alive())return;
       await readScopedAccount(row,refresh,alive);
       if(alive())paintPublished();
     }
   }
   try{await Promise.all(Array.from({length:Math.min(3,missing.length||eligible.length)},readNext));}
   finally{if(alive()){loading=false;paintPublished();}}
 }
 $('wbPublishedRefresh').onclick=()=>void fetchPublished();
 return {paint,paintAccounts,
   failed(){OAUI.set($('wbStartupStatus'),'当前宿主管理工具桥不可用。');}};
}
'''
