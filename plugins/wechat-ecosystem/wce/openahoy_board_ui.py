"""Local account inventory and evidence for the OpenAhoy workspace."""

HTML = '''
  <h1 id="wbOpenAhoyTitle" tabindex="-1">OpenAhoy</h1>
  <div id="homeFeatures" class="ob-columns" role="region" aria-label="发布平台" tabindex="0"></div>
  <div class="ob-tools">
   <p id="homeStatus" class="help" role="status"></p>
   <div class="ob-steps">
    <button id="obPrevious" type="button" aria-label="上一个平台" aria-controls="homeFeatures">‹</button>
    <button id="obNext" type="button" aria-label="下一个平台" aria-controls="homeFeatures">›</button>
   </div>
  </div>
  <dialog id="obPlatformDetails" aria-labelledby="obPlatformTitle">
   <header><h2 id="obPlatformTitle"></h2><button id="obPlatformClose" type="button">关闭</button></header>
   <div id="obPlatformBody"></div>
   <p id="obPlatformStatus" class="help" role="status"></p>
  </dialog>
'''

STYLE = '''
#wbOpenAhoy .oa-home-features{
 --ob-gap:16px;--ob-edge:12px;--ob-card-limit:220px;
 display:flex;flex-direction:column;width:100%;height:100%;min-height:0;
 max-width:calc(7 * var(--ob-card-limit) + 6 * var(--ob-gap) + 2 * var(--ob-edge))
}
.oa-native #wbOpenAhoy{
 overflow:hidden;padding-inline:clamp(34px,2vw,40px);
 padding-block-start:calc(var(--wb-top) - var(--wb-board-card-inset))
}
.ob-tools{
 display:flex;align-items:center;gap:8px;min-width:0;flex:none;
 margin:2px var(--ob-edge) 0
}
#wbOpenAhoy #homeStatus{min-width:0;margin:0;overflow-wrap:anywhere}
#wbOpenAhoy #homeStatus:empty{display:none}
@media(max-width:600px){
 .oa-native #wbOpenAhoy{padding-inline:12px 46px}
}

.oa-management .ob-button{display:inline-flex;align-items:center;justify-content:center;gap:5px;min-height:34px;
 padding:5px 8px;font-size:12px;line-height:16px;font-weight:650;white-space:nowrap;-webkit-tap-highlight-color:transparent}
.ob-button:active{filter:brightness(.91)}
.ob-button svg{width:14px;height:14px;flex:0 0 14px}
.ob-button:focus-visible,.ob-account-name:focus-visible{outline:2px solid var(--accent);outline-offset:-2px}
.ob-steps{margin-inline-start:auto;display:flex;gap:4px}
.oa-management .ob-steps button{width:32px;min-height:32px;padding:0;font-size:17px}
.ob-columns{display:grid;grid-template-columns:repeat(7,minmax(156px,1fr));grid-template-rows:minmax(0,1fr);
 align-items:start;flex:0 1 auto;min-height:0;gap:8px;overflow:auto hidden;padding:2px 2px 9px;
 overscroll-behavior-inline:contain;scrollbar-width:thin}
.ob-columns:focus-visible{outline:2px solid var(--accent);outline-offset:-2px}
.ob-column{display:flex;flex-direction:column;gap:9px;min-width:0;padding:10px;border:1px solid var(--wb-line);
 border-radius:14px;background:var(--wb-float);overflow-wrap:anywhere;max-height:100%;overflow:auto;
 overscroll-behavior-block:contain;scrollbar-width:thin}
.ob-column>*{flex:none}
.ob-column-head{display:grid;align-content:start;gap:7px}
.ob-title{display:grid;place-items:center;min-height:54px;margin:0}
.oa-management.oa-native[data-workbench=openahoy] #wbOpenAhoy button.ob-platform-entry{
 display:grid;place-items:center;width:56px;height:54px;min-height:54px;padding:0;
 background:transparent;border:0;border-radius:11px;box-shadow:none;cursor:pointer;
 -webkit-tap-highlight-color:transparent
}
.oa-management.oa-native[data-workbench=openahoy] #wbOpenAhoy button.ob-platform-entry:active{
 background:transparent;box-shadow:none;opacity:.8
}
.oa-native #wbOpenAhoy .ob-title .oa-platform-mark{
 width:50px;height:50px;padding:0;background:none;border:0;justify-content:center
}
.oa-native #wbOpenAhoy .ob-title .oa-platform-logo{
 width:auto;height:var(--ob-mark-height,39px);max-width:100%;object-fit:contain
}
.ob-title [data-brand=wechat_official_account]{--ob-mark-height:40px}
.ob-title [data-brand=x]{--ob-mark-height:33px}
.ob-title [data-brand=bilibili]{--ob-mark-height:42px}
.oa-native #wbOpenAhoy .ob-title [data-brand=xiaohongshu] .oa-platform-logo{border-radius:10%}
.oa-management.oa-native[data-workbench=openahoy] #wbOpenAhoy [data-platform=tiktok] .ob-platform-entry{
 width:min(100%,172px)
}
.oa-native #wbOpenAhoy [data-platform=tiktok] .ob-title .oa-platform-mark{width:100%}
.ob-title [data-brand=wechat_official_account] .oa-platform-logo{
 filter:brightness(0) saturate(100%) invert(42%) sepia(87%) saturate(974%) hue-rotate(113deg) brightness(105%) contrast(101%)}
.ob-column :is(p,small){margin:0;color:var(--muted);font-size:11px;line-height:1.45}
.ob-accounts{display:grid;gap:4px;border-top:1px solid var(--wb-line);padding-top:5px}
.ob-account{min-width:0}
.ob-account .avatar{width:22px;height:22px;font-size:11px;border-radius:50%}
.oa-management .ob-account-name{min-width:0;width:100%;min-height:32px;display:grid;
 grid-template-columns:22px minmax(0,1fr) max-content;align-items:center;gap:5px;
 padding:0 2px;background:transparent;border:0;border-radius:5px;box-shadow:none;
 color:var(--wb-ink);font-size:12px;font-weight:640;line-height:16px;text-align:start;-webkit-tap-highlight-color:transparent}
.ob-account-label{min-width:0;white-space:normal;overflow-wrap:anywhere}
.ob-account-name:hover .ob-account-label{text-decoration:underline;text-underline-offset:2px}
.ob-workspace-column{position:relative}
.ob-workspace-column .ob-platform-entry::after{
 content:"";position:absolute;inset:0;border-radius:inherit
}
.ob-workspace-column .ob-platform-entry:focus-visible::after{
 outline:2px solid var(--accent);outline-offset:-3px
}
.oa-management #wbOpenAhoy .ob-workspace-column .ob-account-name{position:relative;z-index:1}
.ob-state{display:inline-flex;align-items:center;gap:3px;min-width:0;margin:0;color:var(--wb-ink);
 font-size:10px;line-height:14px;font-weight:625;white-space:nowrap}
.ob-state::before{content:"";width:5px;height:5px;flex:none;border-radius:50%;background:var(--muted)}
.ob-state[data-tone=ready]::before{background:#278262}
.ob-state[data-tone=attention]::before{background:#c3732c}
.ob-state[data-tone=attention]{color:var(--error,var(--wb-ink))}
.ob-actions{display:flex;align-items:center;gap:4px;flex-wrap:wrap}
.oa-management .ob-actions .ob-primary{background:var(--oa-selection,var(--soft));color:var(--oa-selected-ink,var(--wb-ink))}
.ob-details-meta{color:var(--muted);font-size:12px}
#obPlatformDetails{width:min(470px,calc(100% - 24px));max-height:calc(100dvh - 80px);
 background:var(--wb-float);color:var(--wb-ink);border:1px solid var(--wb-line);border-radius:14px;padding:16px}
#obPlatformDetails::backdrop{background:#0006}
#obPlatformDetails>header{display:flex;align-items:center;justify-content:space-between;gap:8px}
#obPlatformDetails h3{margin:11px 0 1px}
#obPlatformDetails p{margin:3px 0}
#obPlatformDetails .ob-actions{margin:8px 0}
.ob-more{border:1px solid var(--wb-line);padding:4px 10px 8px;border-radius:10px}
.oa-management .ob-more>summary{cursor:pointer;min-height:32px;padding-top:7px;font-weight:650;color:var(--wb-ink)}
.ob-service{padding:10px 0;border-top:1px solid var(--wb-line);margin-top:10px}
.ob-service h3{margin-top:0!important}
.ob-service ol{padding-inline-start:19px;margin:7px 0}
.ob-service li{margin:3px 0;line-height:1.45}
.ob-service .help{overflow-wrap:anywhere}
@media(max-width:600px){
 .ob-columns{grid-template-columns:repeat(7,minmax(188px,72%));scroll-snap-type:x proximity}
 .ob-column{scroll-snap-align:start}
 .oa-management .ob-steps button{min-width:44px;min-height:44px}
 .oa-management .ob-button,.oa-management .ob-account-name{min-height:44px}
}
'''

STYLE += '''
/* One surface and one light direction for the board and its platform routes. */
body.oa-management.oa-native:is([data-workbench=openahoy],[data-workbench=platform]){
 --oh-surface:light-dark(#f5f4f1,#292929);
 --oh-highlight:light-dark(#f9f8f6,#343434);
 --oh-inset-light:light-dark(#fdfcfa,#383838);
 --oh-shadow:light-dark(#cbc8c3,#171717);
 --oh-text:light-dark(#242424,#f3f3f3);
 --oh-muted:light-dark(#555,#c7c7c7);
 --oh-focus:light-dark(#215f9b,#a5ceff);
 --oh-selected:light-dark(#14575a,#a3e1d5);
 --oh-error:light-dark(#8f2c38,#ffadb9);
 --oh-edge:light-dark(#d9d9d9,#515151);
 --oh-lift:6px 7px 16px var(--oh-shadow),-4px -4px 15px var(--oh-highlight);
 --oh-press:inset 3px 3px 7px var(--oh-shadow),inset -3px -3px 7px var(--oh-inset-light);
 --oh-control:3px 3px 7px var(--oh-shadow),-3px -3px 7px var(--oh-highlight),
   inset 0 0 0 var(--oh-shadow),inset 0 0 0 var(--oh-highlight);
 --oh-control-down:0 0 0 var(--oh-shadow),0 0 0 var(--oh-highlight),
   inset 3px 3px 6px var(--oh-shadow),inset -3px -3px 6px var(--oh-highlight);
 background:var(--oh-surface)
}
body.oa-management.oa-native:is([data-workbench=openahoy],[data-workbench=platform]) .oa-shell,
body.oa-management.oa-native:is([data-workbench=openahoy],[data-workbench=platform]) .oa-shell>.oa-content{
 background:var(--oh-surface)
}
body.oa-management.oa-native:is([data-workbench=openahoy],[data-workbench=platform])
 :is(#wbOpenAhoy,#nativeWorkspace,#inlineBinding,.oa-sidebar){
 --bg:var(--oh-surface);--surface:var(--oh-surface);--soft:var(--oh-surface);
 --oa-fill:var(--oh-surface);--oa-selection:var(--oh-surface);--oa-selected-ink:var(--oh-selected);
 --oa-hover:var(--oh-surface);--ink:var(--oh-text);--wb-ink:var(--oh-text);--muted:var(--oh-muted);
 --accent:var(--oh-focus);--error:var(--oh-error);--line:var(--oh-edge);
 --wb-float:var(--oh-surface);--wb-line:var(--oh-edge);
 --field-shadow:var(--oh-press);--raised:var(--oh-lift);
 color:var(--oh-text)
}
.oa-management.oa-native[data-workbench=openahoy] #homeFeatures{
 gap:var(--ob-gap);padding:var(--wb-board-card-inset) var(--ob-edge) 16px;scroll-padding-inline:var(--ob-edge)
}
.oa-management.oa-native[data-workbench=openahoy] #homeFeatures .ob-column{
 gap:12px;padding:13px;border-color:transparent;border-radius:18px;
 background:var(--oh-surface);box-shadow:var(--oh-lift)
}
.oa-management.oa-native[data-workbench=openahoy] .ob-column-head{gap:8px}
.oa-management.oa-native[data-workbench=openahoy] .ob-actions{gap:8px}
.oa-management.oa-native[data-workbench=openahoy] .ob-steps{gap:8px}
.oa-management.oa-native[data-workbench=openahoy] .ob-accounts{
 gap:8px;padding:8px;border:0;border-radius:10px;
 background:var(--oh-surface);box-shadow:var(--oh-press)
}
.oa-management.oa-native[data-workbench=openahoy] .ob-account-name{
 background:transparent;box-shadow:none;padding-inline:0
}
.oa-management.oa-native[data-workbench=openahoy] .ob-account-name:active{
 color:var(--oh-selected);box-shadow:var(--oh-press);filter:none
}
body.oa-management.oa-native:is([data-workbench=openahoy],[data-workbench=platform])
 :is(#wbOpenAhoy,#nativeWorkspace,#inlineBinding,.oa-sidebar)
 :is(button:not(.ob-account-name,.account-select,.ob-platform-entry), .oa-more-settings>summary, .ob-more>summary){
 border-color:var(--oh-edge);background:var(--oh-surface);color:var(--oh-text);
 box-shadow:var(--oh-control);filter:none;
 transition:box-shadow .16s ease,color .16s ease;-webkit-tap-highlight-color:transparent
}
body.oa-management.oa-native:is([data-workbench=openahoy],[data-workbench=platform])
 :is(#wbOpenAhoy,#nativeWorkspace,#inlineBinding,.oa-sidebar)
 :is(button.primary,.ob-actions .ob-primary){color:var(--oh-selected)}
.oa-management.oa-native[data-workbench=openahoy] #wbOpenAhoy :is(.ob-button,.ob-steps button){
 border-radius:999px;border-color:transparent
}
body.oa-management.oa-native:is([data-workbench=openahoy],[data-workbench=platform])
 :is(#wbOpenAhoy,#nativeWorkspace,#inlineBinding,.oa-sidebar)
 :is(button.danger,.oa-account-remove){color:var(--oh-error)}
body.oa-management.oa-native:is([data-workbench=openahoy],[data-workbench=platform])
 :is(#wbOpenAhoy,#nativeWorkspace,#inlineBinding,.oa-sidebar)
 :is(button:not(:disabled,.ob-platform-entry):is(:active,[aria-pressed=true],[aria-selected=true],[aria-current=page],.is-selected),
 details:is(.oa-more-settings,.ob-more)[open]>summary,summary:active){
 background:var(--oh-surface);box-shadow:var(--oh-control-down);color:var(--oh-selected);filter:none
}
body.oa-management.oa-native:is([data-workbench=openahoy],[data-workbench=platform])
 :is(#wbOpenAhoy,#nativeWorkspace,#inlineBinding,.oa-sidebar) button:disabled{
 border-color:transparent;background:var(--oh-surface);box-shadow:none;
 color:var(--oh-muted);opacity:.74;cursor:not-allowed
}
body.oa-management.oa-native:is([data-workbench=openahoy],[data-workbench=platform])
 :is(#wbOpenAhoy,#nativeWorkspace,#inlineBinding,.oa-sidebar)
 :is(button,input,select,textarea,summary,a,[tabindex]):focus-visible{
 outline:2px solid var(--oh-focus);outline-offset:-3px
}
.oa-management.oa-native[data-workbench=openahoy] #obPlatformDetails,
.oa-management.oa-native[data-workbench=platform] :is(#nativeWorkspace,#inlineBinding)
 :is(dialog,.oa-task-sheet,.oa-x-production,.oa-x-binding-step,#xDeveloperSettings,#xhsSettings){
 border:1px solid var(--oh-edge);background:var(--oh-surface);color:var(--oh-text);
 border-radius:16px;box-shadow:var(--oh-lift)
}
.oa-management.oa-native[data-workbench=openahoy] #obPlatformDetails .ob-more{
 margin-block:8px;border:0;padding:4px;border-radius:9px
}
.oa-management.oa-native[data-workbench=openahoy] #obPlatformDetails .ob-more summary{
 padding:7px 9px;border-radius:8px;cursor:pointer
}
.oa-management.oa-native[data-workbench=openahoy] #obPlatformDetails .ob-more[open]>:not(summary){
 margin:8px 7px
}
.oa-management.oa-native[data-workbench=platform] #accountPanel #accounts,
.oa-management.oa-native[data-workbench=platform] :is(#nativeWorkspace,#inlineBinding)
 :is(input:not([type=checkbox],[type=radio],[type=file]),select,textarea){
 background:var(--oh-surface);border-color:var(--oh-edge);box-shadow:var(--oh-press);color:var(--oh-text)
}
.oa-management.oa-native[data-workbench=platform] #accountPanel #accounts{
 padding:4px;gap:4px;border-radius:10px
}
.oa-management.oa-native[data-workbench=platform] #accountPanel #accounts>.account.is-selected{
 background:var(--oh-surface);box-shadow:var(--oh-press);color:var(--oh-selected)
}
.oa-management.oa-native[data-workbench=platform] #nativeWorkspace :is(.actions,.oa-task-rows){
 gap:8px
}
@media(max-width:600px){
 body.oa-management.oa-native:is([data-workbench=openahoy],[data-workbench=platform]){
  --oh-lift:4px 5px 11px var(--oh-shadow),-3px -3px 11px var(--oh-highlight);
  --oh-press:inset 2px 2px 5px var(--oh-shadow),inset -2px -2px 5px var(--oh-inset-light)
 }
 .oa-management.oa-native[data-workbench=openahoy] #homeFeatures{
  padding-block-end:14px
 }
 #wbOpenAhoy .oa-home-features{--ob-gap:12px;--ob-edge:9px}
 .oa-management.oa-native[data-workbench=openahoy] #homeFeatures .ob-column{padding:11px}
 .oa-management.oa-native[data-workbench=openahoy] .ob-account-name{min-height:44px}
}
@media(prefers-reduced-motion:reduce){
 body.oa-management.oa-native:is([data-workbench=openahoy],[data-workbench=platform])
  :is(#wbOpenAhoy,#nativeWorkspace,#inlineBinding,.oa-sidebar) :is(button,summary){transition:none}
}
'''

STYLE += '''
body.oa-management.oa-native.oa-platform-view.oa-x-workspace .oa-shell{display:block;height:100dvh;overflow:hidden;padding:0}
body.oa-management.oa-native.oa-platform-view.oa-x-workspace .oa-sidebar{display:none}
.oa-management.oa-native.oa-x-workspace .oa-content{display:block;width:100%;max-width:none;height:100%;overflow:auto;
 padding:var(--wb-top) calc(var(--wb-side-width) + 12px) var(--wb-dock)}
.oa-management.oa-native.oa-x-workspace #nativeWorkspace{width:min(100%,1030px);height:auto;margin-inline:auto;overflow:visible}
.oa-management.oa-native.oa-x-workspace .oa-account-header{display:flex;flex-wrap:wrap;align-items:center;gap:10px}
.oa-management.oa-native.oa-x-workspace #xPlatformBack:not([hidden]){display:inline-flex;align-items:center;gap:5px;min-height:44px}
.oa-management.oa-native.oa-x-workspace #accountPanel{position:static;width:100%;max-width:none;max-height:none;margin:8px 0;padding:0}
.oa-management.oa-native.oa-x-workspace #accounts{display:grid;grid-template-columns:repeat(auto-fit,minmax(min(100%,170px),1fr));
 gap:7px;padding:5px;max-height:170px;overflow:auto}
.oa-management.oa-native.oa-x-workspace .account-select{min-height:44px}
.oa-management.oa-native.oa-x-workspace #xAccountPicker .oa-list-head{display:none}
.oa-management.oa-native.oa-x-workspace #xAccountEvidence:not([hidden]){display:flex;flex-wrap:wrap;gap:4px 14px;
 padding:8px 10px;margin:3px 0;font-size:12px;line-height:1.5;overflow-wrap:anywhere}
#xAccountEvidence p{margin:0;min-width:0}
.ob-douyin-sr{position:absolute;width:1px;height:1px;overflow:hidden;clip-path:inset(50%);margin:0}
#wbDouyin{min-height:0;flex:1;overflow:auto;padding:
 var(--wb-top) calc(var(--wb-side-width) + 12px) var(--wb-dock)}
.ob-douyin-layout{display:grid;grid-template-columns:minmax(180px,280px) minmax(0,1fr);gap:clamp(16px,3vw,44px);
 align-items:start;max-width:1240px;margin-inline:auto;color:var(--wb-ink)}
.ob-douyin-layout :is(aside,section){min-width:0}
.ob-douyin-layout h2{margin:0 0 12px;font-size:16px}
.ob-douyin-layout h3{margin:0;font-size:14px}
.ob-douyin-layout p{margin:0;font-size:13px;line-height:1.55;overflow-wrap:anywhere}
.ob-douyin-list,.ob-douyin-main{display:grid;gap:12px}
.ob-douyin-layout .ob-douyin-choice{display:grid;grid-template-columns:24px minmax(0,1fr) auto;
 align-items:center;gap:8px;min-height:44px;padding:8px 10px;text-align:start;white-space:normal}
.ob-douyin-choice .avatar{width:24px;height:24px;font-size:11px}
.ob-douyin-choice[aria-pressed=true]{box-shadow:var(--wb-dock-inset)}
.ob-douyin-panel{padding:clamp(12px,2vw,22px);display:grid;gap:10px;border-radius:14px;
 background:var(--wb-surface);box-shadow:var(--wb-depth);border:1px solid var(--wb-line)}
.ob-douyin-panel .ob-actions{display:flex;flex-wrap:wrap;gap:8px}
.ob-douyin-panel .ob-button{min-height:42px;white-space:normal}
.ob-douyin-panel dl{display:grid;grid-template-columns:max-content minmax(0,1fr);gap:8px 15px;
 margin:0;font-size:13px;align-items:baseline}
.ob-douyin-panel dd{margin:0;overflow-wrap:anywhere}
.ob-douyin-panel dt{font-weight:650}
.ob-douyin-identity{display:flex;align-items:center;gap:12px;min-width:0}
.ob-douyin-identity .avatar{width:48px;height:48px;flex:none}
.ob-douyin-identity strong{overflow-wrap:anywhere}
@media(max-width:700px){
 .oa-management.oa-native.oa-x-workspace .oa-content{padding-inline:14px calc(var(--wb-side-width) + 12px)}
 #wbDouyin{padding-inline:14px calc(var(--wb-side-width) + 12px)}
 .ob-douyin-layout{grid-template-columns:minmax(0,1fr)}
 .ob-douyin-panel .ob-button{min-height:44px}
}
'''

SCRIPT = r'''
function OAOpenAhoyBoard({ui,decorate,avatar,manage,reload,openLink,checkService,selectDouyin,handoff,wechatName}){
 const wechat='wechat_official_account',douyin='douyin';
 const workspaces={
   [wechat]:['nativeWorkspace','打开公众号配置','打开公众号账号 {0}'],
   x:['nativeWorkspace','打开 X 账号页','打开 X 账号 {0}'],
   [douyin]:['wbDouyin','打开抖音账号页','打开抖音账号 {0}']
 };
 const $=id=>document.getElementById(id),board=$('homeFeatures'),dialog=$('obPlatformDetails');
 const douyinPage=$('obDouyinPage'),douyinList=el('aside'),douyinMain=el('div'),douyinIdentity=el('section');
 const links={
   wechat_official_account:[['腾讯公众号开放接口','https://developers.weixin.qq.com/doc/subscription/api/']],
   x:[['X 官方 API','https://docs.x.com/x-api/posts/create-post'],['X 媒体接口','https://docs.x.com/x-api/media/quickstart']],
   xiaohongshu:[['小红书创作服务平台','https://creator.xiaohongshu.com/']],
   douyin:[['抖音内容发布接入方案','https://developer.open-douyin.com/docs/resource/zh-CN/dop/operation-standard/platform-capabilities/useclue'],
           ['网站应用授权登录','https://developer.open-douyin.com/docs/resource/zh-CN/dop/develop/sdk/web-app/web/permission'],
           ['抖音平台能力使用规范','https://developer.open-douyin.com/docs/resource/zh-cn/dop/operation-standard/platform-capabilities/usage-spec'],
           ['生活服务行业角色认证','https://developer.open-douyin.com/docs/resource/zh-CN/developer/join/Role']],
   tiktok:[['TikTok 内容发布 API','https://developers.tiktok.com/products/content-posting-api/']],
   bilibili:[['哔哩哔哩开放平台','https://open.bilibili.com/doc/']],
   instagram:[['Meta 内容发布','https://developers.facebook.com/documentation/instagram-platform/content-publishing']],
 };
 const platforms=[
   ['wechat_official_account','微信公众号','图文、草稿、普通发表与群发接口','已接入公众号草稿、普通发表及适用账号的群发。','发布权限取决于公众号类型和接口授权。'],
   ['x','X','帖子、媒体上传、作品查询','已接入发帖、媒体上传及读回。','发帖、媒体和读取各需对应 OAuth 权限；额度和平台状态另行核验。'],
   ['xiaohongshu','小红书','创作服务平台支持图文和视频笔记','已接入隔离浏览器登录、图文笔记操作及读回。','会话由浏览器保存，需打开创作后台才能核实登录及发布能力。'],
   ['douyin','抖音','OpenAPI 支持图片和视频发布；MCP 广场提供检索。','首期仅支持测试账号身份绑定。','普通网站应用由 Jiusera 运营方申请并通过审核，创作者使用自己的抖音号授权。'],
   ['tiktok','TikTok','Content Posting API 支持照片和视频。Social 与广告各有独立 MCP。','','需要应用审核和用户授权。'],
   ['bilibili','哔哩哔哩','官方 Open API 支持视频及专栏投稿。','','需要应用通过审核并取得账号授权。'],
   ['instagram','Instagram','Meta API 支持专业账号发布图片、视频、Reels 和轮播。','','需要专业账号及内容发布权限。'],
 ];
 const mcpServices={
   douyin:[{
     id:'douyin',name:'抖音官方 MCP',guide:'https://developer.open-douyin.com/docs/resource/zh-CN/dop/ability/mcp-service/mcp-service-desc',
     endpoint:'https://open.douyin.com/sse',scope:'抖音应用工具与账号工具',
     verification:'使用相应凭据建立 SSE 连接，先运行 initialize 和 tools/list。检索工具仅在已获准且确认只读时调用。',
     steps:['运营方用同一个 Jiusera 移动或网站应用申请服务，创作者无需各自注册开发者应用。',
       '选择视频或图文检索等所需工具，提交申请并等待审批。',
       '应用服务使用 client_token；账号服务使用该账号授权的 access_token。应用服务不计入创作者账号。',
       '凭据由受管客户端提供。接入页和聊天只使用无凭据的公开地址。'],
   }],
   tiktok:[{
     id:'tiktok_social',name:'TikTok Social MCP',guide:'https://business-api.tiktok.com/portal/docs/mcp-authorization/v1.3',
     scope:'TikTok 账号的自然内容能力',
     verification:'读取实际工具目录。用已授权的只读工具核对所选账号或该账号的作品数据。',
     steps:['走 Social MCP 的客户端登记和授权流程，选择正确的 TikTok 账号。',
       '在授权页核对权限；回调和令牌由支持此服务的客户端处理。',
       '普通作品发布走独立的 Content Posting API；以实际授权和可用工具为准。'],
   },{
     id:'tiktok_ads',name:'TikTok for Business MCP',guide:'https://business-api.tiktok.com/portal/docs/how-to-connect-chatgpt-to-tiktok-for-business-mcp-server/v1.3',
     endpoint:'https://business-api.tiktok.com/open_mcp/tt-ads-mcp-layer',scope:'TikTok 广告账号',
     verification:'先读取已授权广告账号或报告。广告授权不计入 TikTok 创作者账号。',
     steps:['使用 TikTok for Business 账号，在支持 OAuth 的客户端添加官方服务。',
       '到 TikTok 官方页登录，选择广告账号并核对权限；到期后用同一账号授权。',
       '逐个确认应使用的广告账号。'],
   }],
   instagram:[{
     id:'meta_ads',name:'Meta Ads MCP',guide:'https://developers.facebook.com/documentation/ads-commerce/ads-ai-connectors/ads-mcp-server/ads-mcp-server-get-started',
     endpoint:'https://mcp.facebook.com/ads',scope:'Meta 广告账号',
     verification:'先读取已授权广告账号或报告。广告授权不计入 Instagram 创作者账号。',
     steps:['在支持 OAuth 的客户端添加 Meta 官方广告服务，通过 Facebook Login for Business 授权。',
       '核对所选广告账号及 ads_mcp_management、ads_read 或 ads_management 权限。',
       'Instagram 作品发布走独立的 Meta 内容发布 API。'],
   }],
 };
 const knownScope=['tweet.read','users.read','tweet.write','media.write','offline.access'];
 const writeScopes=['tweet.read','users.read','tweet.write'];
 const healthy=new Set(['BOUND','BOUND_IDLE','CONNECTED','BUSY']);
 const icons={
   go:'M3 8h9m-4-4 4 4-4 4', chevron:'m6 4 4 4-4 4',
   list:'M6 4h7M6 8h7m-7 4h7M3 4h.01M3 8h.01M3 12h.01',
   link:'M6 10 10 6m-3-2 1-1a3 3 0 0 1 4 4l-1 1m-2 4-1 1a3 3 0 0 1-4-4l1-1',
   external:'M8 3h5v5m0-5-6 6m4 0v4H3V5h4',
   refresh:'M13 8a5 5 0 1 0-1.5 3.5M13 3v5H8',
   check:'m3 8 3 3 7-7', close:'m4 4 8 8m0-8-8 8',
 };
 let data={directory:[],rows:[],reads:{}},loaded=false,loading=false;
 let douyinSelection='';
 function el(tag,key,...args){
   const node=document.createElement(tag);if(key)ui.set(node,key,...args);return node;
 }
 function icon(name){
   const ns='http://www.w3.org/2000/svg';
   const svg=document.createElementNS(ns,'svg'),path=document.createElementNS(ns,'path');
   svg.setAttribute('viewBox','0 0 16 16');svg.setAttribute('aria-hidden','true');
   path.setAttribute('d',icons[name]);path.setAttribute('fill','none');path.setAttribute('stroke','currentColor');
   path.setAttribute('stroke-width','1.5');path.setAttribute('stroke-linecap','round');path.setAttribute('stroke-linejoin','round');
   svg.append(path);return svg;
 }
 function decorateButton(node,key,glyph){
   node.classList.add('ob-button');node.replaceChildren(icon(glyph),el('span',key));
 }
 function button(key,glyph,action,short){
   const node=el('button');node.type='button';node.onclick=action;
   decorateButton(node,short||key,glyph);
   if(short)ui.attr(node,'aria-label',key);
   return node;
 }
 function timeLine(label,value){
   if(!Number.isFinite(value)||value<=0)return el('p',label,'—');
   const ts=new Date(value*1000);if(Number.isNaN(ts.valueOf()))return el('p',label,'—');
   return el('p',label,ts.toLocaleString(document.documentElement.lang,{dateStyle:'medium',timeStyle:'short'}));
 }
 function model(id){
   const adapter=data.directory.find(p=>p.id===id);
   const read=data.reads[id];
   const state=read?.state??(adapter?(loaded?'READ':'PENDING'):platforms.findIndex(p=>p[0]===id)<3&&!loaded?'PENDING':'UNSUPPORTED');
   const accounts=new Map();
   for(const row of data.rows){
     if(row.platform_id!==id||row.connection_id==='x-unavailable'||row.state==='DISCONNECTED')continue;
     const identity=row.account_id||row.connection_id,prior=accounts.get(identity);
     if(!prior||(!healthy.has(prior.state)&&healthy.has(row.state)))accounts.set(identity,row);
   }
   return {adapter,state,read,accounts:[...accounts.values()]};
 }
 function status(row){
   if(row.platform_id==='douyin')return '本机已绑定抖音身份';
   if(row.authorization?.state==='REFRESH_DUE')return '访问令牌已到期，待刷新';
   if(row.authorization?.state==='ACTION_REQUIRED'||row.error==='XHS_LOGIN_REQUIRED')return '需要重新授权';
   if(row.authorization?.state==='UNKNOWN')return 'OAuth 状态待核验';
   if(row.state==='ACTION_REQUIRED')return '需要处理';
   if(healthy.has(row.state))return row.platform_id==='xiaohongshu'?'浏览器会话已登记，登录待核验':'本机已绑定';
   return '连接状态待核验';
 }
 function accountLabel(row){
   return (row.platform_id===wechat&&wechatName(row))||row.presentation?.display_name||row.label||row.username||'';
 }
 function compactStatus(row,stale){
   if(stale)return ['上次记录','unknown'];
   if(row.platform_id==='douyin')return ['已绑定','ready'];
   if(row.authorization?.state==='REFRESH_DUE')return ['已到期','attention'];
   if(row.authorization?.state==='ACTION_REQUIRED'||row.error==='XHS_LOGIN_REQUIRED')return ['待重连','attention'];
   if(row.state==='ACTION_REQUIRED')return ['需处理','attention'];
   if(row.authorization?.state==='UNKNOWN'||row.platform_id==='xiaohongshu'||!healthy.has(row.state))return ['待核验','unknown'];
   if(Array.isArray(row.authorization?.scopes)&&knownScope.some(scope=>!row.authorization.scopes.includes(scope)))return ['缺权限','attention'];
   return ['已绑定','ready'];
 }
 function account(row,stale){
   const node=el('article');node.className='ob-account';
   const image=avatar(row);image.setAttribute('aria-hidden','true');
   const action=el('button');action.type='button';action.className='ob-account-name';
   const name=el('span');name.className='ob-account-label';
   if(accountLabel(row))ui.raw(name,accountLabel(row));else ui.set(name,'账号名称待核验');
   const [label,tone]=compactStatus(row,stale);
   const connection=el('span',label);connection.className='ob-state';connection.dataset.tone=tone;
   ui.attr(connection,'title',stale?'上次记录 · {0}':status(row),ui.format(status(row)));
   const display=accountLabel(row)||ui.format('账号名称待核验');
   action.title=display;
   action.append(image,name,connection);
   const workspace=workspaces[row.platform_id];
   if(workspace){
     const sameName=model(row.platform_id).accounts.filter(item=>accountLabel(item)===accountLabel(row));
     const ordinal=sameName.length>1?' ('+(sameName.indexOf(row)+1)+')':'';
     action.setAttribute('aria-controls',workspace[0]);
     ui.attr(action,'aria-label',workspace[2],display+ordinal+' · '+ui.format(label));
     action.onclick=()=>void manage(row.platform_id,row);
   }else{
     action.setAttribute('aria-haspopup','dialog');
     ui.attr(action,'aria-label','查看账号 {0}',display+' · '+ui.format(label));
     action.onclick=()=>accountDetails(row,stale);
   }
   node.append(action);return node;
 }
 function appendAccountEvidence(node,row,stale){
   const auth=row.authorization?.state;
   node.append(el('p',stale?'上次记录 · {0}':status(row),ui.format(status(row))));
   if(Array.isArray(row.authorization?.scopes)){
     const missing=knownScope.filter(scope=>!row.authorization.scopes.includes(scope));
     if(missing.length)node.append(el('p','缺少权限：{0}',missing.join(', ')));
     if(auth==='RECORDED'&&!stale){
       const granted=new Set(row.authorization.scopes),checks=[
         ['读取帖子',['tweet.read','users.read']],['发布文字',writeScopes],
         ['发布带媒体帖子',[...writeScopes,'media.write']],
       ];
       const recorded=checks.filter(([,requirements])=>requirements.every(key=>granted.has(key)));
       if(recorded.length)node.append(el('p','已登记的授权能力：{0}',recorded.map(([key])=>ui.format(key)).join(' · ')));
       else if(!missing.length)node.append(el('p','所需 OAuth 权限已登记'));
     }else if(!missing.length)node.append(el('p','远端权限未核验'));
   }else node.append(el('p','权限待核验'));
   node.append(Number.isFinite(row.last_verified_at)?timeLine('最近远端核验：{0}',row.last_verified_at):el('p','最近远端核验：未记录'));
 }
 function accountDetails(row,stale){
   const node=el('div');
   const name=accountLabel(row);
   if(name)ui.raw($('obPlatformTitle'),name);else ui.set($('obPlatformTitle'),'账号名称待核验');
   if(row.platform_id==='x'&&row.username){
     const handle=el('p');handle.className='ob-details-meta';ui.raw(handle,'@'+row.username);node.append(handle);
   }
   appendAccountEvidence(node,row,stale);
   if(!stale){
     const actions=el('div');actions.className='ob-actions';
     const action=button('管理账号','go',()=>goToAccount(row), '管理');
     actions.append(action);
     if(row.binding_revision&&row.account_id&&(row.authorization?.state==='ACTION_REQUIRED'||
        row.error==='XHS_LOGIN_REQUIRED'||row.platform_id==='x'&&row.authorization?.state==='REFRESH_DUE')){
       actions.append(button('重新授权','refresh',()=>goToAccount(row,true)));
     }
     node.append(actions);
   }
   $('obPlatformBody').replaceChildren(node);openDetails();
 }
 function goToAccount(row,reauthorize=false){
   dialog.close();void manage(row.platform_id,row,reauthorize);
 }
 function openDetails(){
   ui.raw($('obPlatformStatus'),'');
   if(!dialog.open)dialog.showModal();
   dialog.scrollTop=0;
   $('obPlatformClose').focus({preventScroll:true});
 }
 function paintDouyin(){
   if($('wbDouyin').hidden)return;
   ui.set($('wbDouyinTitle'),'抖音账号');
   const {accounts,state}=model(douyin);
   const stale=state==='FAILED';
   const row=douyinSelection?accounts.find(item=>item.connection_id===douyinSelection):accounts[0];
   const focus=douyinList.contains(document.activeElement)?document.activeElement.dataset.connection:null;
   douyinList.replaceChildren(el('h2','抖音账号'));
   if(stale)douyinList.append(el('p','账号读取失败'));
   else if(!loaded)douyinList.append(el('p','正在读取账号…'));
   else if(!accounts.length)douyinList.append(el('p','尚未绑定抖音账号'));
   for(const item of accounts){
     const [label,tone]=compactStatus(item,stale),accountName=accountLabel(item);
     const name=el('span');
     if(accountName)ui.raw(name,accountName);
     else ui.set(name,'账号名称待核验');
     if(accounts.some(other=>other!==item&&accountLabel(other)===accountName)&&item.masked_open_id)
       ui.raw(name,(accountName||ui.format('账号名称待核验'))+' · '+item.masked_open_id);
     const stateLabel=el('span',label);stateLabel.className='ob-state';stateLabel.dataset.tone=tone;
     const pick=el('button');pick.type='button';pick.className='ob-douyin-choice';pick.dataset.connection=item.connection_id;
     pick.setAttribute('aria-pressed',String(row===item));pick.append(avatar(item),name,stateLabel);
     pick.onclick=()=>{douyinSelection=item.connection_id;selectDouyin(douyinSelection);paintDouyin();};
     douyinList.append(pick);
   }
   if(focus)[...douyinList.querySelectorAll('button')].find(node=>node.dataset.connection===focus)?.focus({preventScroll:true});
   douyinIdentity.replaceChildren(el('h3','账号身份'));
   if(row){
     const identity=el('div'),display=el('strong');
     identity.className='ob-douyin-identity';
     if(accountLabel(row))ui.raw(display,accountLabel(row));
     else ui.set(display,'账号名称待核验');
     identity.append(avatar(row),display);
     douyinIdentity.append(identity,el('p',stale?'上次记录 · {0}':status(row),ui.format(status(row))),
       el('p','本应用 OpenID：{0}',row.masked_open_id||'—'),
       timeLine('最近远端核验：{0}',row.last_verified_at));
   }else if(douyinSelection&&loaded)douyinIdentity.append(el('p','当前工作区没有此抖音账号。'));
   else douyinIdentity.append(el('p',loaded?'当前版本未开放抖音账号绑定。':'正在读取账号…'));
   ui.set(douyinProfileState,row?.presentation?.avatar&&accountLabel(row)?'已读回抖音公开资料':'待读取公开资料');
 }
 function details(item){
   const [id,name,official,implementation,requirements]=item,current=model(id);
   ui.set($('obPlatformTitle'),name);
   const body=$('obPlatformBody');body.replaceChildren();
   const capabilities=el('details');capabilities.className='ob-more';capabilities.open=Boolean(current.adapter);
   capabilities.append(el('summary','平台能力与账号条件'),el('p',official),
     el('p',implementation&&current.adapter?implementation:'本机尚无接入适配器'),el('p',requirements));
   if(current.state==='FAILED')capabilities.append(el('p','账号读取失败'));
   if(current.read?.read_at)capabilities.append(timeLine('本机清单读取：{0}',current.read.read_at));
   body.append(capabilities);
   for(const service of mcpServices[id]||[])body.append(serviceSection(service));
   const actions=el('div');actions.className='ob-actions';
   if(current.adapter&&current.state!=='FAILED'){
     actions.append(button('前往账号管理','go',()=>{
       dialog.close();
       void manage(id);
     },'账号管理'));
   }
   for(const [label,url] of links[id])actions.append(button(label,'external',async()=>{
     try{await openLink(url);ui.raw($('obPlatformStatus'),'');}
     catch(_){ui.set($('obPlatformStatus'),'当前宿主无法打开链接，请从平台官方入口访问。');}
   }));
   body.append(actions);openDetails();
 }
 function serviceSection(service){
   const section=el('section');section.className='ob-service';section.dataset.service=service.id;
   section.append(el('h3',service.name),el('p',service.scope));
   const instructions=el('details');instructions.className='ob-more';
   const steps=el('ol');for(const step of service.steps)steps.append(el('li',step));
   instructions.append(el('summary','接入步骤'),steps,el('p','授权后只读验证：{0}',ui.format(service.verification)));
   const status=el('p','待通过官方授权');status.className='help';status.setAttribute('role','status');section.append(status);
   const endpointStatus=el('p');endpointStatus.className='help';endpointStatus.setAttribute('role','status');
   const probeTime=el('div');section.append(endpointStatus,probeTime);
   const actions=el('div');actions.className='ob-actions';
   actions.append(button('官方接入指南','external',async()=>{
     try{await openLink(service.guide);}catch(_){ui.set(status,'当前宿主无法打开链接，请从平台官方入口访问。');}
   },'官方指南'));
   if(service.endpoint){
     const probe=button('检查官方端点','refresh',async()=>{
       const labels={AUTH_REQUIRED:'官方端点要求授权',REFUSED:'官方端点拒绝本次检查',RATE_LIMITED:'官方端点限流',
         REACHABLE:'官方端点有响应，授权状态待核验',UNAVAILABLE:'暂时无法确认官方端点'};
       probe.disabled=true;ui.set(endpointStatus,'正在检查官方端点…');
       try{
         const result=await checkService(service.id);
         if(result?.service===service.id&&result.verification==='PUBLIC_ENDPOINT_ONLY'&&labels[result.state]){
           ui.set(endpointStatus,labels[result.state]);probeTime.replaceChildren(timeLine('本次检查：{0}',result.checked_at));
         }else ui.set(endpointStatus,'暂时无法确认官方端点');
       }catch(_){ui.set(endpointStatus,'暂时无法确认官方端点');}
       finally{probe.disabled=false;}
     },'查端点');
     actions.append(probe);
   }
   actions.append(button('在 Codex 接续授权','link',async event=>{
     const action=event.currentTarget;action.disabled=true;
     const parts=[ui.format('继续配置 {0}，官方指南 {1}。',[service.name,service.guide]),
       service.endpoint?ui.format('已核对的公开端点是 {0}。',[service.endpoint]):ui.format('请在官方文档核对当前服务端点。'),
       ui.format(service.verification),
       ui.format('先确认宿主支持及已有配置，使用官方授权页面，凭据只留在受管客户端。授权完成后只验证工具目录或已授权范围内的只读账号。请分别回报成功、待授权、取消、拒绝或过期；不要调用发表、投放或其他写入工具。')];
     try{await handoff(parts.join(' '));ui.set(status,'已交给 Codex 核对，等待官方授权结果。');}
     catch(_){ui.set(status,'当前宿主无法接续，请打开官方接入指南。');}
     finally{action.disabled=false;}
   },'接续授权'));
   actions.append(button('在 Codex 只读核验','check',async event=>{
     const action=event.currentTarget;action.disabled=true;
     const parts=[ui.format('只读核验已授权的 {0}。官方指南 {1}。',[service.name,service.guide]),
       ui.format(service.verification),
       ui.format('这次只检查现有连接。缺授权、取消、拒绝、过期或宿主无法发现时，请如实回报，不新建连接或发起写入。')];
     try{await handoff(parts.join(' '));ui.set(status,'只读请求已交给 Codex，等待结果。');}
     catch(_){ui.set(status,'当前宿主无法接续，请打开官方接入指南。');}
     finally{action.disabled=false;}
   },'只读核验'));
   section.append(actions,instructions);return section;
 }
 function paint(){
   $('openAhoyBoardRefresh').disabled=loading;
   $('openAhoyBoardRefresh').setAttribute('aria-busy',String(loading));
   const scroll=board.scrollLeft,columns=[];
   const priorScroll=new Map([...board.children].map(column=>[column.dataset.platform,column.scrollTop]));
   const focused=board.contains(document.activeElement)?document.activeElement:null;
   const focusKey=focused?.dataset.focusKey;
   for(const item of platforms){
     const [id,name]=item,current=model(id);
     const workspace=workspaces[id];
     const section=el('section');section.className='ob-column';section.dataset.platform=id;section.dataset.read=current.state;
     if(workspace)section.classList.add('ob-workspace-column');
     const header=el('header');header.className='ob-column-head';
     const title=el('h2');title.id='ob-title-'+id;title.className='ob-title';ui.attr(title,'aria-label',name);
     const entry=el('button');entry.type='button';entry.className='ob-platform-entry';
     entry.dataset.focusKey=id+':details';
     if(workspace){
       entry.setAttribute('aria-controls',workspace[0]);entry.onclick=()=>void manage(id);
     }else{
       entry.setAttribute('aria-haspopup','dialog');
       entry.setAttribute('aria-controls','obPlatformDetails');entry.onclick=()=>details(item);
     }
     decorate(entry,id,name,'board');entry.lastElementChild.hidden=true;
     ui.attr(entry,'aria-label',workspace?workspace[1]:name);
     title.append(entry);
     section.setAttribute('aria-labelledby',title.id);header.append(title);
     section.append(header);
     if(current.accounts.length){
       const list=el('div');list.className='ob-accounts';
       for(const row of current.accounts){
         const line=account(row,current.state==='FAILED');
         line.querySelector('button').dataset.focusKey=id+':'+row.connection_id;
         list.append(line);
       }
       section.append(list);
     }
     columns.push(section);
   }
   board.replaceChildren(...columns);board.scrollLeft=scroll;
   for(const column of columns)column.scrollTop=priorScroll.get(column.dataset.platform)||0;
   if(focusKey)[...board.querySelectorAll('button[data-focus-key]')].find(node=>node.dataset.focusKey===focusKey)?.focus({preventScroll:true});
   syncArrows();
 }
 function syncArrows(){
   $('obPrevious').disabled=board.scrollLeft<=1;
   $('obNext').disabled=board.scrollLeft+board.clientWidth>=board.scrollWidth-1;
 }
 function step(direction){
   const width=board.firstElementChild?.getBoundingClientRect().width||board.clientWidth;
   const gap=parseFloat(getComputedStyle(board).columnGap)||0;
   board.scrollBy({left:direction*(width+gap),
     behavior:matchMedia('(prefers-reduced-motion: reduce)').matches?'instant':'smooth'});
 }
 $('obPrevious').onclick=()=>step(-1);$('obNext').onclick=()=>step(1);
 board.addEventListener('keydown',event=>{
   if(event.target!==board)return;
   if(event.key==='ArrowLeft'||event.key==='ArrowRight'){event.preventDefault();step(event.key==='ArrowLeft'?-1:1);}
   if(event.key==='Home'||event.key==='End'){
     event.preventDefault();
     board.scrollTo({left:event.key==='Home'?0:board.scrollWidth,behavior:'instant'});
   }
 });
 board.addEventListener('scroll',syncArrows,{passive:true});
 new ResizeObserver(syncArrows).observe(board);
 ui.attr(board,'aria-label','发布平台');
 ui.attr($('obPrevious'),'aria-label','上一个平台');
 ui.attr($('obNext'),'aria-label','下一个平台');
 decorateButton($('obPlatformClose'),'关闭','close');
 decorateButton($('openAhoyBoardRefresh'),'刷新连接状态','refresh');
 ui.attr($('openAhoyBoardRefresh'),'aria-label','刷新连接状态');
 ui.attr($('openAhoyBoardRefresh'),'title','刷新连接状态');
 $('obPlatformClose').onclick=()=>dialog.close();
 $('openAhoyBoardRefresh').onclick=()=>void reload();
 douyinList.className='ob-douyin-list';douyinMain.className='ob-douyin-main';
 douyinIdentity.className='ob-douyin-panel';
 const douyinCapabilities=el('section');
 douyinCapabilities.className='ob-douyin-panel';
 const capabilityList=el('dl');
 const douyinProfileState=el('dd','待读取公开资料');
 capabilityList.append(el('dt','昵称与头像'),douyinProfileState);
 for(const [feature,state] of [['作品与统计','需要对应数据权限'],['内容投稿','待平台审核与接入']])
   capabilityList.append(el('dt',feature),el('dd',state));
 const docFeedback=el('p');docFeedback.setAttribute('role','status');docFeedback.hidden=true;
 const accessLinks=el('div');accessLinks.className='ob-actions';
 for(const [label,url] of [...links[douyin].slice(0,2),['抖音 MCP 官方指南',mcpServices[douyin][0].guide]])accessLinks.append(button(label,'external',async()=>{
   try{await openLink(url);docFeedback.hidden=true;}
   catch(_){ui.set(docFeedback,'当前宿主无法打开链接，请从平台官方入口访问。');docFeedback.hidden=false;}
 }));
 douyinCapabilities.append(el('h3','平台能力与账号条件'),capabilityList,accessLinks,docFeedback);
 const douyinMcp=el('details');douyinMcp.className='ob-douyin-panel';
 douyinMcp.append(el('summary','抖音 MCP 接入与只读核验'),serviceSection(mcpServices[douyin][0]));
 douyinMain.append(douyinIdentity,douyinCapabilities,douyinMcp);douyinPage.append(douyinList,douyinMain);
 ui.onChange(()=>{if(loaded)paint();paintDouyin();});
 paint();
 return {
   readState(id){return model(id).state;},
   connectionState(row){return compactStatus(row,model(row.platform_id).state==='FAILED');},
   paintAccountEvidence(node,row){
     node.replaceChildren();node.hidden=!row;
     if(row)appendAccountEvidence(node,row,model(row.platform_id).state==='FAILED');
   },
   showDouyin(connection){
     douyinSelection=connection;paintDouyin();
   },
   focusAccount(id,connection){
     const column=[...board.children].find(node=>node.dataset.platform===id);
     const focusKey=connection?id+':'+connection:id+':details';
     ([...column?.querySelectorAll('button[data-focus-key]')||[]].find(node=>node.dataset.focusKey===focusKey)||
       column?.querySelector('button.ob-platform-entry'))?.focus();
   },
   loading(){loading=true;$('openAhoyBoardRefresh').disabled=true;$('openAhoyBoardRefresh').setAttribute('aria-busy','true');},
   update(directory,rows,reads){
     const incoming=Object.fromEntries(directory.map(({id})=>[id,{
       state:reads?.[id]?.state==='FAILED'?'FAILED':'READ',read_at:reads?.[id]?.read_at
     }]));
     const failed=Object.keys(incoming).filter(id=>incoming[id].state==='FAILED');
     for(const id of failed)incoming[id].read_at=data.reads[id]?.read_at;
     data={directory,rows:[...rows.filter(row=>!failed.includes(row.platform_id)),
       ...data.rows.filter(row=>failed.includes(row.platform_id))],reads:incoming};
     loaded=true;loading=false;paint();paintDouyin();
   },
   failed(){
     const ids=new Set([...platforms.slice(0,3).map(([id])=>id),...data.directory.map(({id})=>id)]);
     data.reads=Object.fromEntries([...ids].map(id=>[id,{state:'FAILED',read_at:data.reads[id]?.read_at}]));
     loading=false;paint();paintDouyin();
   }
 };
}
'''
