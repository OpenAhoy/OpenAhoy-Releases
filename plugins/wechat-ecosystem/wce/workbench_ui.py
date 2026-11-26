"""Presentation for the embedded Jiusera work surfaces."""

from .own_branding import _PACKAGE, jiusera_header, l_unify_symbol, openahoy_symbol
from .home_overview import ACTIVITY, introductory_cards


def trend_resource(suffix):
    return '\n'.join((_PACKAGE / 'assets' / 'management' / (name + '.' + suffix)).read_text(encoding='utf-8')
                     for name in ('workbench-trend', 'workbench-home', 'workbench-overview'))


def relief_style():
    return (_PACKAGE / 'assets' / 'management' / 'workbench-relief.css').read_text(encoding='utf-8')

NOTCH_PATH = "M0 0H288Q278 0 278 10V24Q278 38 264 38H24Q10 38 10 24V10Q10 0 0 0Z"


def chrome(icon):
    side_icons = ''.join(f'<span data-side-icon="{key}" aria-hidden="true">{icon(key)}</span>'
                         for key in ('refresh', 'settings', 'arrow', 'audio', 'accounts'))
    openahoy_logo = (_PACKAGE / 'assets/openahoy-v1/openahoy-horizontal-color.svg').read_text(encoding='utf-8')
    # Center the visible OpenAhoy artwork within its SVG canvas.
    openahoy_logo = (openahoy_logo.partition('?>')[2].strip()
                     .replace('fill="#0B1C2F"', 'fill="currentColor"')
                     .replace('viewBox="0 0 1580 380"', 'viewBox="-23.25 0 1580 380"'))

    def dock_option(button_id, text, target, glyph, *, selected=False):
        pressed = 'true' if selected else 'false'
        return (f'<button id="{button_id}" type="button" aria-label="{text}" '
                f'aria-pressed="{pressed}" aria-controls="{target}">{icon(glyph)}</button>')

    return '''<header class="wb-titlebar">
 <button id="wbBrand" type="button" aria-label="关于 Jiusera">
  <svg class="wb-notch-shell" viewBox="0 0 288 38" preserveAspectRatio="none" aria-hidden="true" focusable="false">
   <path d="'''+NOTCH_PATH+'''"/>
  </svg>
  <span class="wb-brand-stack" aria-hidden="true">
   <span data-wb-brand-mark="jiusera">'''+jiusera_header(color_only=True)+'''</span>
   <span data-wb-brand-mark="openahoy">'''+openahoy_logo+'''</span>
   <span data-wb-brand-mark="lunify">'''+l_unify_symbol()+'''<span>L-unify</span></span>
  </span>
 </button>
</header>
<div id="wbSideActions" class="wb-side-notch" data-collapsed>
 <svg class="wb-notch-shell" viewBox="0 0 38 288" preserveAspectRatio="none" aria-hidden="true" focusable="false">
  <path transform="translate(38 0) rotate(90)" d="'''+NOTCH_PATH+'''"/>
 </svg>
 <button id="openAhoyBoardRefresh" class="wb-side-tool" type="button" hidden>刷新连接状态</button>
 <div id="wbWechatTools" role="group" aria-label="公众号工作区" hidden></div>
 <button id="wbSideTool" class="wb-side-tool" type="button" hidden>'''+side_icons+'''</button>
</div>
 <div id="wbCanvasControls" class="wb-context" hidden>
  <button id="wbProject" aria-expanded="false" aria-controls="directorWorkbar" type="button">项目与作品</button>
  <button id="wbShot" aria-expanded="false" aria-controls="wbCanvasDetails" type="button">镜头</button>
 </div>
<div class="wb-dock-wrap">
 <nav class="wb-dock" aria-label="Jiusera 工作台导航">
  <button class="wb-person" data-wb-route="profile" type="button" aria-label="个人资料" title="个人资料">'''+icon('person')+'''</button>
  <div class="wb-dock-entries" id="wbDockEntries">
  <button class="wb-dock-brand" data-wb-route="published" type="button" aria-label="Jiusera 作品首页" title="Jiusera 作品首页">'''+jiusera_header(color_only=True)+'''</button>
  <div class="wb-canvas-entry">
  <button data-wb-route="jiusera-canvas" type="button" aria-label="画布" title="画布">'''+icon('settings')+'''<span>画布</span></button>
  </div>
  <div class="wb-lunify-entry">
  <button data-wb-route="l-unify-home" type="button" aria-label="L-unify" title="L-unify" aria-expanded="false" aria-controls="wbLunifyNavigation">'''+l_unify_symbol()+'''<span>L-unify</span></button>
  </div>
  <div class="wb-openahoy-entry">
  <button class="wb-openahoy" data-wb-route="openahoy" type="button" aria-label="OpenAhoy" title="OpenAhoy" aria-expanded="false" aria-controls="wechatWorkspaceNavigation">'''+openahoy_symbol()+'''<span>OpenAhoy</span></button>
  </div>
  <div class="wb-asset-entry">
  <button data-wb-route="jiusera-assets" type="button" aria-label="资产" title="资产" aria-expanded="false" aria-controls="wbAssetNavigation">'''+icon('accounts')+'''<span>资产</span></button>
  </div>
  <button data-wb-route="about" type="button" aria-label="设置" title="设置">'''+icon('gear')+'''<span>设置</span></button>
  </div>
  <button class="wb-dock-step" type="button" aria-controls="wbDockEntries" aria-label="查看后面的入口" title="查看后面的入口">
   <svg aria-hidden="true" viewBox="0 0 16 16" width="16" height="16" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round"><path d="m6 4 4 4-4 4"/></svg>
  </button>
 <button id="wbHomeUpdate" type="button" aria-label="检查更新" hidden disabled aria-describedby="wbHomeUpdateStatus">'''+icon('refresh')+'''</button>
 <button id="oaLocale" type="button" aria-label="切换到中文">
  <span lang="zh-CN" aria-hidden="true">中文</span><span lang="en" aria-hidden="true">EN</span>
 </button>
 <div id="wbAssetNavigation" class="wb-dock-expansion" role="group" aria-label="资产导航" hidden>
  <div class="wb-dock-expansion-items">
  '''+dock_option('wbAssetSources', '信源库', 'sourceLibrary', 'source_library')+'''
  </div>
 </div>
 <div id="wbLunifyNavigation" class="wb-dock-expansion" role="group" aria-label="L-unify 导航" hidden>
  <div class="wb-dock-expansion-items">
  '''+dock_option('wbLunifySongs', '歌曲列表', 'wbMusicSongs', 'song_list')+'''
  '''+dock_option('wbLunifyStudio', 'IMW', 'wbMusic', 'audio')+'''
  <button id="imw-video-toggle" type="button" aria-label="展开视频" title="展开视频" aria-expanded="false">'''+icon('video')+'''</button>
  <button id="imw-settings-toggle" type="button" aria-label="工作站设置" title="工作站设置" aria-expanded="false">'''+icon('gear')+'''</button>
  </div>
 </div>
 <div id="wechatWorkspaceNavigation" class="wb-dock-expansion" role="group" aria-label="公众号工作区" hidden>
  <div class="wb-dock-expansion-items">
  '''+dock_option('wechatArticlesTab', '文章与草稿', 'wechatArticlesPage', 'source_library')+'''
  '''+dock_option('wechatMediaTab', '公众号素材', 'settingsPanel', 'accounts')+'''
  '''+dock_option('wechatReadersTab', '读者与消息', 'settingsPanel', 'account_permissions')+'''
  '''+dock_option('wechatCommerceTab', '经营工具', 'wechatAccountDesk', 'analytics')+'''
  '''+dock_option('wechatConfigTab', '公众号配置', 'settingsPanel', 'gear')+'''
  </div>
 </div>
 </nav>
 <span id="wbDockTip" class="wb-dock-tip" aria-hidden="true" hidden></span>
 <span id="wbHomeUpdateStatus" class="jh-screenreader" role="status"></span>
</div>'''


SURFACES = '''
<section id="wbStartup" aria-label="Jiusera">
 <div class="wb-startup-center">
  <h1 id="wbStartupTitle">Jiusera</h1>
  <p id="wbStartupStatus" role="status">正在连接工作台…</p>
 </div>
</section>
<section id="wbPublished" aria-labelledby="wbPublishedTitle" hidden>
 <div class="jh jho">
  <h1 id="wbPublishedTitle" class="jh-screenreader" tabindex="-1">Jiusera 首页</h1>
  '''+introductory_cards()+'''
  <div class="jho-second">
   '''+ACTIVITY+'''
   <section class="jho-panel jho-stats" aria-labelledby="wbHomeStatsTitle">
    <header class="jho-section-head">
     <div><h2 id="wbHomeStatsTitle">内容数据</h2><p id="wbHomeStatsRange" class="jho-note">近 7 天</p></div>
     <button id="wbPublishedRefresh" type="button" disabled>读取统计</button>
    </header>
    <div id="wbOverview" class="jh-strip">
     <div class="jh-scope">
      <div id="wbPlatformCoverage" class="jh-platforms" aria-label="筛选平台"></div>
      <select id="wbPublishedPlatform" aria-label="筛选平台" hidden></select>
      <select id="wbPublishedAccount" aria-label="筛选账号" hidden></select>
      <span id="wbCoverage" class="jh-screenreader" role="status"></span>
     </div>
     <button id="wbClearScope" type="button" hidden>全部账号</button>
    </div>
    <div class="jho-metric">
     <p>账号日阅读人数合计</p>
     <strong id="wbHomeReadValue">—</strong>
     <p id="wbHomeStatsState" class="jho-note" role="status">正在读取账号…</p>
     <p id="wbHomeMetricBasis" class="jho-note" hidden>按账号相加，未跨账号去重。</p>
    </div>
    <details class="jho-more jho-trend-detail">
     <summary>日阅读趋势</summary>
     <section id="wbComparisonTrend" class="jh-trend" aria-label="日阅读趋势"></section>
    </details>
    <details class="jho-more">
     <summary>作品排行</summary>
     <section class="jh-works" aria-labelledby="wbRankTitle">
      <header class="jh-works-head">
       <div class="jh-works-heading"><h3 id="wbRankTitle">按平台排行</h3><span class="jh-work-meta" id="wbRankPeriod"></span></div>
       <div class="jh-works-nav">
        <button type="button" class="jh-work-step" data-platform-prev>‹</button>
        <button type="button" class="jh-work-step" data-platform-next>›</button>
       </div>
      </header>
      <div id="wbPublishedCards" class="jh-platform-board" data-platform-works aria-label="分平台作品排行"></div>
      <p id="wbPublishedState" class="jh-empty" role="status"></p>
     </section>
    </details>
   </section>
  </div>
 </div>
</section>
'''


STYLE = '''
body.oa-management.oa-native[data-workbench]{
 --wb-surface:#f1f1f0;--wb-float:#fbfbfaed;--wb-ink:#232624;--wb-line:#2222;
 --wb-depth:0 7px 28px #00000015;--wb-dock:70px;--wb-notch-width:clamp(164px,calc(100vw - 176px),288px);--wb-notch-height:38px;--wb-top:calc(var(--wb-notch-height) + clamp(12px,1vw,16px));--wb-top-tools-clearance:108px;
 --wb-board-card-inset:12px;
 --wb-side-width:44px;
 --wb-tool-gutter:calc(var(--wb-side-width) + clamp(8px,1vw,16px));
 --wb-dock-surface:#e8ebf0;--wb-dock-ink:#272e39;--wb-dock-active:#76314f;--wb-dock-focus:#245e9e;
 --wb-dock-light:color-mix(in srgb,var(--wb-dock-surface) 22%,white);
 --wb-dock-shade:color-mix(in srgb,var(--wb-dock-surface) 72%,#4e596b);
 --wb-dock-raised:-2px -2px 4px var(--wb-dock-light),2px 3px 5px var(--wb-dock-shade);
 --wb-dock-inset:inset 2px 2px 5px var(--wb-dock-shade),inset -2px -2px 4px var(--wb-dock-light);
 --wb-dock-float:-3px -3px 8px var(--wb-dock-light),5px 7px 17px var(--wb-dock-shade);
}
body.oa-management.oa-native[data-color-scheme=dark][data-workbench]{
 --wb-surface:#202122;--wb-float:#292a2bef;--wb-ink:#f2f3f2;--wb-line:#fff2;
 --wb-depth:0 7px 28px #0007;
 --wb-dock-surface:#242830;--wb-dock-ink:#edf0f5;--wb-dock-active:#f5bed8;--wb-dock-focus:#a2c9ff;
 --wb-dock-light:color-mix(in srgb,var(--wb-dock-surface) 82%,#8a9dbb);
 --wb-dock-shade:color-mix(in srgb,var(--wb-dock-surface) 34%,#080a0d);
}
@media(prefers-color-scheme:dark){
 body.oa-management.oa-native:not([data-color-scheme])[data-workbench]{
  --wb-surface:#202122;--wb-float:#292a2bef;--wb-ink:#f2f3f2;--wb-line:#fff2;--wb-depth:0 7px 28px #0007;
  --wb-dock-surface:#242830;--wb-dock-ink:#edf0f5;--wb-dock-active:#f5bed8;--wb-dock-focus:#a2c9ff;
  --wb-dock-light:color-mix(in srgb,var(--wb-dock-surface) 82%,#8a9dbb);
  --wb-dock-shade:color-mix(in srgb,var(--wb-dock-surface) 34%,#080a0d);
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
/* The inverse shoulders attach the floating surface to the top edge. */
.wb-titlebar{
 --wb-notch-logo:82px;
 position:fixed;z-index:20;inset:0 0 auto;margin-inline:auto;width:var(--wb-notch-width);height:var(--wb-notch-height);
 display:grid;place-items:center;pointer-events:none;isolation:isolate
}
@media(max-width:390px){.wb-titlebar{--wb-notch-logo:72px}}
.wb-notch-shell{
 position:absolute;inset:0;width:100%;height:100%;overflow:visible;
 fill:var(--wb-panel,var(--wb-surface));filter:drop-shadow(0 2px 2px #00000023)
}
.oa-management.oa-native[data-workbench] .wb-titlebar #wbBrand{
 position:relative;display:grid;place-items:center;width:100%;height:100%;min-height:0;
 padding:0;border:0;box-shadow:none;background:transparent;pointer-events:none
}
.oa-native .wb-titlebar #wbBrand .wb-notch-shell path{pointer-events:visiblePainted;cursor:pointer}
.wb-brand-stack{display:grid;place-items:center;position:absolute;inset:0;pointer-events:none}
.wb-brand-stack>[data-wb-brand-mark]{
 grid-area:1/1;display:flex;align-items:center;justify-content:center;gap:6px;opacity:0
}
#wbBrand[data-brand="jiusera"] [data-wb-brand-mark="jiusera"],
#wbBrand[data-brand="openahoy"] [data-wb-brand-mark="openahoy"],
#wbBrand[data-brand="lunify"] [data-wb-brand-mark="lunify"]{opacity:1}
.wb-brand-stack [data-wb-brand-mark="openahoy"]{
 width:calc(var(--wb-notch-logo) + 10px);color:light-dark(#0b1c2f,#f2f3f2)
}
.wb-brand-stack [data-wb-brand-mark="openahoy"] svg{display:block;width:100%;height:auto}
.wb-brand-stack [data-wb-brand-mark="lunify"]{font-size:14px;font-weight:700;color:var(--wb-ink)}
.wb-brand-stack .wb-unify-mark{width:17px;height:17px}
@media(prefers-reduced-motion:no-preference){
 #wbBrand[data-brand-ready] [data-wb-brand-mark]{transition:opacity 190ms ease}
}
.oa-native .wb-titlebar #wbBrand .oa-brand-logo{position:relative;width:var(--wb-notch-logo);margin:0}
.oa-management.oa-native[data-workbench] .wb-titlebar #wbBrand:focus-visible{outline:0}
.oa-native .wb-titlebar #wbBrand:focus-visible path{
 stroke:var(--wb-focus);stroke-width:2px;vector-effect:non-scaling-stroke
}
.oa-native .wb-titlebar #wbBrand img{display:block}
.oa-native[data-color-scheme=dark] .wb-titlebar #wbBrand img{filter:brightness(1.33)}
.wb-side-notch{
 position:fixed;z-index:18;inset-inline-end:0;inset-block-start:50%;transform:translateY(-50%);
 display:grid;place-items:center;width:var(--wb-side-width);height:98px;pointer-events:none;transform-origin:right center
}
.wb-side-notch[data-collapsed],
.oa-native.oa-wechat-view:has(#inlineBinding:not([hidden])) #wbSideActions{transform:translateY(-50%) scaleX(0)}
@media(prefers-reduced-motion:no-preference){
 .wb-side-notch{transition:transform 220ms ease,height 220ms ease}
 #wbSideTool [data-side-icon]{transition:opacity 150ms ease}
}
.wb-side-notch .wb-notch-shell{filter:drop-shadow(-2px 0 2px #00000023)}
.oa-native[data-workbench=openahoy] .wb-side-notch .wb-notch-shell{fill:var(--oh-surface)}
.oa-management.oa-native[data-workbench] .wb-side-notch .wb-side-tool{
 position:relative;pointer-events:auto;display:grid;place-items:center;
 width:var(--wb-side-width);height:44px;min-height:44px;padding:0;border:0;border-radius:0;
 background:transparent;box-shadow:none;color:var(--wb-ink)
}
.oa-management.oa-native .wb-side-tool svg{width:17px;height:17px}
#wbSideTool [data-side-icon]{position:absolute;display:grid;place-items:center;inset:0;opacity:0;pointer-events:none}
#wbSideTool [data-side-icon][data-active]{opacity:1}
#wbSideTool [data-side-icon=arrow] svg{transform:rotate(180deg)}
#openAhoyBoardRefresh span,.wb-side-notch[hidden],
.oa-management.oa-native[data-workbench] .wb-side-notch [hidden]{display:none}
.oa-management.oa-native .wb-side-tool:focus-visible::after{
 position:absolute;inset-inline-end:100%;width:max-content;padding:5px 8px;border-radius:6px;
 background:var(--wb-ink);color:var(--wb-surface);content:attr(aria-label)
}
.wb-context{display:flex;align-items:center;flex-wrap:wrap;gap:5px}
#wbCanvasControls{position:fixed;z-index:19;inset:var(--wb-top) 13px auto auto;justify-content:end}
.oa-native :is(.wb-context,.wb-published-tools) button{
 min-height:32px;padding:4px 9px;font-size:12px;border-radius:10px;
 color:var(--wb-ink);border:1px solid var(--wb-line);background:var(--wb-float);box-shadow:none
}
.oa-management.oa-native.oa-platform-view .oa-shell{padding-top:var(--wb-top)}
/* Generic platform navigation and its adjacent workspace share the shell inset. */
body.oa-management.oa-native.oa-platform-view:not(.oa-wechat-view,.oa-x-workspace) .oa-shell>:is(.oa-sidebar,.oa-content){padding-block-start:0}
.oa-management.oa-native.oa-platform-view .oa-sidebar .oa-brand{display:none}
.oa-native.oa-platform-view .oa-content{padding-block-end:var(--wb-dock)}
.oa-management.oa-native.oa-x-developer-open.oa-platform-view .oa-content{padding-bottom:var(--wb-dock)}
.oa-native.oa-platform-view .oa-sidebar :is(#jiuseraNav,#openWorkflowGuide,#wechatCompactUpdates){display:none!important}
@media(max-width:560px){
 body.oa-management.oa-native.oa-platform-view:not(.oa-wechat-view,.oa-x-workspace) .oa-sidebar>div:has(#platformNavigation){grid-row:1}
 .oa-management.oa-native.oa-platform-view:not(.oa-x-developer-open):has([data-platform-id="x"][aria-current="page"]) .oa-shell{
  display:grid;grid-template-columns:minmax(0,1fr);grid-template-rows:auto minmax(0,1fr);height:100dvh;min-height:0;overflow:hidden
 }
 .oa-management.oa-native.oa-platform-view:not(.oa-x-developer-open):has([data-platform-id="x"][aria-current="page"]) .oa-content{
  min-width:0;min-height:0;overflow:auto;overscroll-behavior:contain
 }
}
#oaLocale[data-language="zh-CN"] [lang="zh-CN"],#oaLocale[data-language="en"] [lang="en"]{display:none}
.wb-dock-wrap{
 position:fixed;z-index:40;inset:auto 0 max(8px,env(safe-area-inset-bottom));width:max-content;max-width:calc(100% - 16px);margin-inline:auto
}
.wb-dock{
 --wb-dock-edge:36px;--wb-dock-tail:var(--wb-dock-edge);--wb-primary-width:96px;--wb-dock-child:28px;--wb-dock-gap:6px;
 --wb-dock-slot:40px;--wb-dock-group-surface:var(--wb-dock-surface);
 --wb-dock-group-raised:var(--wb-dock-raised);--wb-dock-group-inset:var(--wb-dock-inset);
 --wb-dock-child-raised:-1px -1px 2px var(--wb-highlight),1px 2px 3px var(--wb-shadow);
 display:grid;grid-template-columns:var(--wb-dock-edge) minmax(0,1fr) var(--wb-dock-tail);align-items:center;gap:7px;padding:6px;
 border:1px solid var(--wb-dock-surface);border-radius:16px;color:var(--wb-dock-ink);
 background:var(--wb-dock-surface);box-shadow:var(--wb-dock-float)
}
.wb-dock:has(>#wbHomeUpdate:not([hidden])){--wb-dock-tail:repeat(2,var(--wb-dock-edge))}
.wb-dock-entries{display:flex;min-width:0;align-items:center;gap:var(--wb-dock-gap)}
.wb-dock lus-transport{display:none}
.wb-openahoy-entry,.wb-asset-entry,.wb-canvas-entry,.wb-lunify-entry{
 display:flex;flex:none;align-items:center;scroll-snap-align:start
}
.oa-management.oa-native .wb-dock .wb-dock-expansion[hidden]{display:none}
.oa-management.oa-native .wb-dock button{
 display:flex;justify-content:center;align-items:center;box-sizing:border-box;width:100%;min-width:0;
 height:36px;min-height:36px;gap:6px;padding:0 3px;border:1px solid transparent;border-radius:9px;
 color:inherit;background:var(--wb-dock-surface);box-shadow:var(--wb-dock-raised);
 font-size:11px;font-weight:650;line-height:16px;white-space:nowrap
}
.oa-management.oa-native[data-workbench] .wb-dock>button:is(.wb-person,#oaLocale,#wbHomeUpdate){
 flex:none;width:var(--wb-dock-edge);height:var(--wb-dock-edge);min-height:var(--wb-dock-edge);
 border-radius:50%;justify-self:center
}
.oa-management.oa-native[data-workbench] .wb-dock>#oaLocale{grid-column-end:-1}
.oa-management.oa-native[data-workbench] .wb-dock>#wbHomeUpdate[hidden]{display:none}
.oa-management.oa-native .wb-dock .wb-dock-step{display:none}
.oa-management .wb-dock .wb-dock-brand .oa-brand-logo{flex:none;width:61px;margin:0}
.oa-management.oa-native .wb-dock .wb-dock-brand .oa-brand-logo img{display:block}
.oa-native[data-color-scheme=dark] .wb-dock-brand .oa-brand-logo img{filter:brightness(1.33)}
.oa-management .wb-dock-entries :is(.oa-icon,.wb-openahoy-mark,.wb-unify-mark){
 display:block;width:16px;height:16px;flex:0 0 16px
}
.wb-unify-mark{
 display:block;background:currentColor;mask:var(--wb-unify-mask) center/contain no-repeat
}
.oa-management .wb-dock-entries button>span:last-child:not(.oa-brand-logo){
 font:inherit;line-height:inherit
}
/* The rendered ink sits above the line-box center for these labels. */
.oa-management .wb-dock-entries :is([data-wb-route=jiusera-canvas],[data-wb-route=openahoy],[data-wb-route=jiusera-assets])>span:last-child,
.oa-management:lang(zh) .wb-dock-entries [data-wb-route=about]>span:last-child,
.oa-management .wb-dock>#oaLocale>span{translate:0 1px}
body.oa-management.oa-native[data-workbench] .wb-dock button{transition:none}
body.oa-management.oa-native[data-workbench] .wb-dock button:not(:where([data-wb-disclosure] button)):hover:not(:disabled):not([aria-disabled=true]){
 color:var(--wb-dock-active);background:var(--wb-dock-surface);box-shadow:var(--wb-dock-raised)
}
body.oa-management.oa-native[data-workbench] .wb-dock button:not(:where([data-wb-disclosure] button)):is([aria-current=page],:active):not(:disabled):not([aria-disabled=true]){
 color:var(--wb-dock-active);background:var(--wb-dock-surface);box-shadow:var(--wb-dock-inset)
}
.oa-management.oa-native .wb-dock button:focus-visible{outline:2px solid var(--wb-dock-focus);outline-offset:-2px}
.wb-dock-tip{
 position:fixed;z-index:1;pointer-events:none;white-space:nowrap;background:var(--wb-panel);color:var(--wb-ink);
 padding:5px 9px;border-radius:8px;box-shadow:var(--wb-raised);font-size:12px;line-height:16px
}
.wb-dock-tip[hidden]{display:none}
.oa-management #oaLocale:focus-visible{outline:2px solid var(--accent);outline-offset:-2px}
.oa-native :is(#wbProfile,#wbMusic,#wbMusicHome,#wbMusicSongs){
 height:100%;min-height:0;overflow:auto;padding:var(--wb-top) clamp(14px,5vw,54px) var(--wb-dock);
}
:is(#wbProfile,#wbMusic)>div,#wbOpenAhoy .oa-home-features{max-width:1030px;margin-inline:auto}
.oa-native :is(#wbProfileTitle,#wbMusicTitle,#wbMusicHomeTitle,#wbMusicSongsTitle,#wbOpenAhoyTitle,#homeTitle,#directorTitle,#dmScreenTitle){
 position:absolute;width:1px;height:1px;min-width:0;min-height:0;margin:0;padding:0;border:0;
 clip-path:inset(50%);overflow:hidden;white-space:nowrap
}
body.oa-management.oa-native #wbMusic #wbMusicTitle{width:1px;min-height:0}
.wb-music-links{display:flex;flex-wrap:wrap;gap:6px;margin-top:14px}
.oa-management .wb-music-links button{min-height:34px;font-weight:600}
.wb-openahoy-mark{display:inline-grid;flex:none;place-items:center;width:16px;height:16px}
.wb-openahoy-mark img{display:block;width:100%;height:100%;object-fit:contain}
.wb-openahoy-mark img+img{display:none}
body[data-color-scheme=dark] .wb-openahoy-mark img:first-child{display:none}
body[data-color-scheme=dark] .wb-openahoy-mark img+img{display:block}
#wbOpenAhoy{height:100%;min-height:0;overflow:auto;padding:var(--wb-top) clamp(14px,5vw,54px) var(--wb-dock)}
#wbOpenAhoy .oa-home-features{margin-block-start:0}
.oa-native :is(#platformNavigation,#wbPlatformCoverage) .oa-platform-mark[data-brand=x]{
 background:transparent;border-color:transparent
}
#wbOpenAhoy [role=status]{margin:0}
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
.oa-management.oa-native[data-workbench=canvas]:not(.oa-platform-view) #videoDirectorDesk{padding:0;overflow:visible}
.oa-management.oa-native[data-workbench=monitor] #videoDirectorDesk{
 display:flex;flex-direction:column;overflow:hidden;gap:6px
}
[data-workbench=monitor] #articleWork:not([hidden]){flex:1;min-height:0;height:100%}
.oa-management.oa-native[data-workbench=monitor]:not(.oa-platform-view) #videoDirectorDesk{overflow:auto}
[data-workbench=monitor] #directorMonitor:not([hidden]){flex:1 0 auto;grid-template-rows:1fr auto}
@media(min-width:901px){
 [data-workbench=monitor] #directorMonitor .dm-sidebar,[data-workbench=monitor] #dmCutSettings{
  min-height:0;max-height:max(300px,calc(100dvh - 255px));overflow:auto;scrollbar-width:thin}
}
@media(min-width:901px) and (min-height:580px){
 .oa-native[data-workbench=monitor] #directorMonitor:not([hidden]){flex:1 1 0;min-height:0;grid-template-rows:minmax(0,1fr) auto}
 [data-workbench=monitor] #directorMonitor :is(.dm-main,.dm-sidebar,#dmCutSettings){min-height:0;max-height:none}
 [data-workbench=monitor] #directorMonitor :is(#dmScreen,#dmCutPreview){container-type:size;min-height:0}
}
@media(max-height:480px) and (orientation:landscape){
 .oa-native[data-workbench=monitor]:not([data-workbench-article]) #videoDirectorDesk>.dd-toolbar{
  position:absolute;inset-block-start:0;inset-inline-end:12px;z-index:2;min-height:var(--wb-notch-height)}
 .oa-native[data-workbench=monitor] #directorMonitor .dm-main{gap:2px;padding-block:4px}
 [data-workbench=monitor] #directorMonitor .dm-heading-copy :is(#dmNow,#dmPlaybackState){display:inline}
}
[data-workbench=monitor] #videoDirectorDesk .dd-footer:has(#directorStatus:empty):has(#directorCopy[hidden]){display:none}
[data-workbench=canvas][data-workbench-article] #directorBoard{display:none}
@media(max-width:840px){
 [data-workbench=monitor] #directorMonitor:not([hidden]){grid-template-rows:auto}
}
#directorChatWorkMenu,#directorRefreshMenu{display:none}
[data-workbench=monitor] #directorMore :is(#directorNewWork,#directorRecoverWork,#directorProjectSettings,#directorCardsLink){display:none}
@media(min-width:651px){[data-workbench=monitor] #directorMore{display:none}}
#videoDirectorDesk>.dd-toolbar .dd-actions #directorMore{margin:0}
#videoDirectorDesk>.dd-toolbar .dd-actions :is(button:not(.dd-more-menu button),#directorMore summary){
 min-height:32px;line-height:16px;font-weight:600
}
@media(max-width:650px){
 .oa-management.oa-native[data-workbench=monitor]:not(.oa-platform-view) #videoDirectorDesk{
   padding-top:var(--wb-top);padding-bottom:max(60px,var(--wb-dock));gap:5px
 }
 [data-workbench=monitor] #videoDirectorDesk .dd-workbar{display:block;margin:0;padding:0}
 [data-workbench=monitor] #videoDirectorDesk .dd-projects{
   display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:6px
 }
 [data-workbench=monitor] #videoDirectorDesk .dd-projects label{
   display:grid!important;grid-template-columns:minmax(0,1fr);gap:3px;min-width:0
 }
 [data-workbench=monitor] #videoDirectorDesk .dd-projects select{width:100%!important}
 [data-workbench=monitor] #directorChatWork,[data-workbench=monitor] #directorRefresh{display:none!important}
 [data-workbench=monitor] #directorChatWorkMenu,[data-workbench=monitor] #directorRefreshMenu{display:block}
 [data-workbench=monitor] #directorWorkbar>.dd-actions{display:none}
}
.oa-native[data-workbench=canvas] #videoDirectorDesk > .dd-toolbar{
 position:fixed;inset:auto 13px calc(var(--wb-dock) + 4px) auto;z-index:12;justify-content:flex-end;
}
.oa-native[data-workbench=canvas] #directorWorkHint{
 position:absolute;width:1px;height:1px;padding:0;clip-path:inset(50%);white-space:nowrap;overflow:hidden
}
.oa-native[data-workbench=canvas] #videoDirectorDesk .dd-toolbar .dd-actions{gap:4px}
.oa-native[data-workbench=canvas] #directorMore:not([hidden]){margin:0}
.oa-native[data-workbench=canvas] #directorMore .dd-more-menu{top:auto;bottom:calc(100% + 4px)}
.oa-native[data-workbench=canvas] #directorWorkbar,.oa-native[data-workbench=canvas] #wbCanvasDetails{
 position:fixed;z-index:15;top:var(--wb-top);right:12px;width:min(382px,calc(100% - 24px));
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
.oa-native[data-workbench=canvas] .dd-canvas-toolbar>.dd-actions:first-child{left:50%;top:var(--wb-top);transform:translateX(-50%)}
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
 padding:var(--wb-top) var(--wb-tool-gutter) var(--wb-dock)
}
.wb-about-card{border:1px solid var(--wb-line);border-radius:16px;padding:17px;background:var(--wb-float)}
.wb-entry-card{max-width:1030px}
.wb-settings-heading{display:flex;align-items:center;justify-content:flex-start;min-height:var(--wb-notch-height)}
.oa-management .wb-settings-heading button{min-height:34px;font-weight:600}
.wb-about-card p{margin-block:5px;color:var(--muted)}
.wb-settings-board{
 --wb-settings-square:clamp(158px,19vw,232px);--wb-settings-gap:12px;
 display:grid;gap:var(--wb-settings-gap);align-items:stretch;
 grid-template-columns:var(--wb-settings-square) repeat(8,minmax(0,1fr));
 grid-template-rows:repeat(2,minmax(calc((var(--wb-settings-square) - var(--wb-settings-gap))/2),auto)) auto;
 grid-template-areas:"models version version version version version check check check"
  "models feedback feedback diagnostics diagnostics diagnostics guide guide canvas"
  "details details details details details details details details details"
}
.oa-native #openAhoyHome :is(#softwareUpdateSlot,#wbSupportSlot,.oa-support-links,.oa-software-update){display:contents}
.wb-settings-board .wb-setting-version{grid-area:version}
.wb-settings-board .oa-update-actions{grid-area:check}
.wb-settings-board .wb-setting-feedback{grid-area:feedback}
.wb-settings-board .wb-setting-log{grid-area:diagnostics}
.wb-settings-board .wb-setting-guide{grid-area:guide}
.wb-settings-board .wb-setting-canvas{grid-area:canvas}
.wb-settings-board .wb-setting-update-details{grid-area:details}
.oa-native #openAhoyHome :is(.wb-model-banner,.wb-setting-action,.wb-setting-version,.wb-setting-update-details,.oa-update-actions){
 border:1px solid var(--wb-line);border-radius:15px;background:var(--wb-surface);
 box-shadow:var(--wb-dock-raised);min-width:0;color:var(--wb-ink);
}
.oa-native #openAhoyHome .wb-model-banner{
 grid-area:models;box-sizing:border-box;aspect-ratio:1;width:100%;height:auto;min-height:0;align-self:start;
 position:relative;display:flex;align-items:center;justify-content:flex-start;white-space:normal;text-align:start;
 padding:clamp(12px,1.8vw,24px);border-color:light-dark(#d9c5bc,#64504b);
 background:linear-gradient(148deg,light-dark(#f1ede9,#362b29),var(--wb-surface) 80%);
}
.oa-native #openAhoyHome :is(.wb-model-banner,.wb-setting-action):not(:disabled):active{box-shadow:var(--wb-dock-inset)}
.oa-native #openAhoyHome :is(.wb-model-banner,.wb-setting-action):focus-visible{outline:2px solid var(--wb-focus,var(--wb-dock-focus));outline-offset:3px}
.wb-model-banner-copy{display:grid;gap:7px;min-width:0;text-align:start}
.wb-model-banner-mark{color:light-dark(#9d332b,#f19b89);fill:none;stroke:currentColor;stroke-width:1.4}
#wbModelBannerTitle{font-size:clamp(18px,2vw,29px);letter-spacing:-.035em;line-height:1.12;font-weight:760}
#wbModelBannerFeature{color:var(--muted);font-size:clamp(11px,1vw,13px);line-height:1.35;font-weight:550;overflow-wrap:anywhere}
.wb-model-banner-action{position:absolute;inset:16px 16px auto auto;display:grid;place-items:center;color:var(--wb-ink)}
.oa-native #openAhoyHome .wb-setting-action{
 display:flex;align-items:center;justify-content:space-between;gap:7px;
 min-height:52px;padding:12px clamp(10px,1.15vw,18px);white-space:normal;text-align:start;font-weight:670;line-height:1.25
}
.wb-setting-action:not(:disabled)::after,.oa-update-actions button:not(:disabled)::after{
 content:"";flex:none;width:6px;height:6px;border:solid currentColor;border-width:1.5px 1.5px 0 0;rotate:45deg;opacity:.72
}
.wb-setting-version{display:grid;align-content:center;gap:4px;padding:13px clamp(10px,1.15vw,18px);font-size:12px;line-height:1.35}
.wb-setting-version .oa-update-version{font-size:13px}
.wb-setting-version .oa-update-versions{gap:2px;max-width:310px}
.wb-setting-version .oa-update-status{margin:2px 0 0}
.oa-native #openAhoyHome .oa-update-actions{display:grid;align-content:center;gap:1px;padding:4px}
.oa-native #openAhoyHome .oa-update-actions button{
 width:100%;min-height:40px;display:flex;align-items:center;justify-content:space-between;
 padding:7px clamp(9px,1.15vw,16px);font-family:inherit;font-size:13px;font-weight:650;line-height:1.25
}
.wb-setting-update-details{padding:8px 14px}
.wb-setting-update-details:not(:has(.oa-update-job:not(:empty),details:not([hidden]))){display:none}
.wb-setting-update-details details+details{margin-top:5px}
@media(max-width:760px){
 .wb-settings-board{--wb-settings-square:clamp(112px,34vw,156px);--wb-settings-gap:9px;
  grid-template-columns:var(--wb-settings-square) minmax(0,1fr);grid-template-rows:auto;
  grid-template-areas:"models version" "check check" "feedback diagnostics" "guide canvas" "details details"
 }
 .oa-native #openAhoyHome .wb-model-banner{padding:12px}
 .wb-model-banner-copy{gap:4px}
 .wb-model-banner-mark{width:23px;height:23px}
 .wb-model-banner-action{inset:11px 9px auto auto}
 .wb-model-banner-action svg{width:15px;height:15px}
 #wbModelBannerTitle{font-size:16px}
 #wbModelBannerFeature{font-size:11px;line-height:1.28}
 .wb-setting-version{align-self:stretch;font-size:11px}
}
.oa-native :is(#wbModels,#wbAudioWork){width:100%;min-width:0;flex:1;min-height:0;overflow:auto;
 padding:var(--wb-top) calc(var(--wb-side-width) + 12px) var(--wb-dock)}
.wb-settings-content{max-width:1030px;margin-inline:auto;min-width:0}
.oa-native #wbModels{padding-inline:var(--wb-tool-gutter)}
#wbModels .wb-settings-content{max-width:none;container-type:inline-size}
.wb-settings-content .wb-settings-heading{justify-content:space-between;gap:8px;margin-bottom:14px;flex-wrap:wrap}
.wb-settings-content h1{margin:0;font-size:clamp(19px,2vw,24px);line-height:1.2}
#wbModels .wb-settings-heading button,#wbModelDialog>header button{min-height:44px}
.wb-model-layout{display:grid;grid-template-columns:minmax(0,1fr) minmax(330px,36%);
 gap:clamp(18px,2.25vw,36px);align-items:start}
.wb-model-grid{--wb-model-card-edge:180px;display:grid;min-width:0;
 grid-template-columns:repeat(auto-fill,min(var(--wb-model-card-edge),100%));
 max-width:1140px;align-content:start;gap:12px}
.wb-model-card{display:grid;grid-template-rows:minmax(0,1fr) auto;min-width:0;min-height:0;aspect-ratio:1;
 background:var(--wb-surface);border-radius:14px;box-shadow:var(--wb-dock-raised)}
.wb-model-card .wb-model-link{display:flex;align-items:center;justify-content:space-between;
 gap:5px;margin:0 5px 5px;padding:4px 7px;min-height:36px;min-width:0;border-radius:8px;
 color:var(--wb-ink);font-size:12px;font-weight:650;line-height:1.2;text-decoration:none}
.wb-model-link svg{flex:none}
.wb-model-link:is(:hover,:active){box-shadow:var(--wb-dock-inset)}
@media(pointer:coarse){.wb-model-card .wb-model-link{min-height:44px}}
.oa-native #wbModelGrid .wb-model-tile{
 display:grid;grid-template-rows:auto 1fr auto;align-items:start;gap:3px;justify-content:stretch;
 width:100%;min-width:0;min-height:0;padding:8px 12px 4px;text-align:start;white-space:normal;
 color:var(--wb-ink);background:transparent;border:0;border-radius:14px;box-shadow:none
}
.oa-native #wbModelGrid .wb-model-tile:active{box-shadow:var(--wb-dock-inset)}
#wbModels :is(.wb-model-tile,.wb-model-link,.wb-model-external,[data-promo-provider]):focus-visible,
#wbModelDialog>header button:focus-visible{
 outline:2px solid var(--wb-focus,var(--wb-dock-focus));outline-offset:2px
}
.wb-model-tile-top{display:flex;align-items:center;justify-content:space-between;gap:7px}
.wb-model-symbol{position:relative;display:grid;place-items:center;flex:0 0 28px;height:28px}
.wb-model-symbol img{display:block;width:24px;height:24px;object-fit:contain}
.wb-model-tile[data-model-id=tokenhex] .wb-model-symbol img{width:27px;height:27px;border-radius:7px}
.wb-model-tile[data-model-id=openai_gif] .wb-model-symbol img{position:absolute;inset:auto;width:39px;height:39px;max-width:none}
.wb-model-symbol .wb-model-logo-dark,
[data-color-scheme=dark] .wb-model-symbol img:has(+.wb-model-logo-dark){display:none}
[data-color-scheme=dark] .wb-model-symbol .wb-model-logo-dark{display:block}
@media(prefers-color-scheme:dark){
 body:not([data-color-scheme]) .wb-model-symbol img:has(+.wb-model-logo-dark){display:none}
 body:not([data-color-scheme]) .wb-model-symbol .wb-model-logo-dark{display:block}
}
.wb-model-category{color:var(--muted);font-size:11px;text-align:end;overflow-wrap:anywhere}
.wb-model-tile-main{display:grid;gap:3px;min-width:0;overflow-wrap:anywhere}
.wb-model-tile-main strong{font-size:14px;line-height:1.15}
.wb-model-spec{color:var(--muted);font-size:11px;line-height:1.15}
.wb-model-tile-foot{display:flex;align-items:baseline;justify-content:space-between;flex-wrap:wrap;
 gap:2px 6px;min-width:0;font-size:11px;line-height:1.2;color:var(--muted);overflow-wrap:anywhere}
.wb-model-tile-foot [data-model-status]{min-width:0;white-space:normal;overflow-wrap:anywhere}
.wb-model-tile[data-state=CONFIGURED] [data-model-status]{color:light-dark(#245b48,#a0dfbd)}
.wb-model-credential{display:flex;gap:2px 7px;align-items:baseline;flex-wrap:wrap;min-width:0}
.wb-model-credential code,.wb-model-detail-hint code{font-size:12px;font-variant-numeric:tabular-nums;color:var(--wb-ink)}
.wb-model-credential code{white-space:nowrap;font-size:11px}
.wb-model-credential code[hidden],.wb-model-detail-hint[hidden],#wbModelDialog [data-model-editor][hidden]{display:none}
#wbModelDialog{width:min(720px,calc(100% - 24px));max-width:none;max-height:calc(100dvh - 28px);
 box-sizing:border-box;overflow:auto;padding:clamp(14px,2.2vw,24px);color:var(--wb-ink);
 background:var(--wb-surface);border:1px solid var(--wb-line);border-radius:18px;box-shadow:var(--wb-dock-raised)}
#wbModelDialog::backdrop{background:#18171673}
#wbModelDialog>header{display:flex;align-items:center;justify-content:space-between;gap:12px;margin-bottom:10px}
#wbModelDialog>header h2{margin:0;font-size:20px;overflow-wrap:anywhere}
.wb-model-detail-hint{display:flex;align-items:baseline;gap:10px;margin:8px 0 12px;color:var(--muted);font-size:13px}
#wbModelDialog [data-model-pane]{min-width:0}
#wbModelDialog .oa-provider-grid{display:block;padding:3px 3px 8px}
#wbModelDialog :is(.oa-provider-grid>.panel,.oa-gif-key){
 background:var(--wb-surface);border:1px solid var(--wb-line);border-radius:14px;box-shadow:var(--wb-dock-raised)
}
#wbModelDialog .oa-gif-key{max-width:none;padding:15px}
#wbModelDialog .oa-gif-key-controls{flex-wrap:wrap}
#wbModelDialog .oa-gif-key-controls input{flex:1 1 150px}
#wbModelDialog #audioWorkspace,#wbAudioWork #audioWorkspace{overflow:visible}
#wbModelDialog #audioWorkspace .oa-audio-dashboard{grid-template-columns:minmax(0,1fr)}
#wbModelDialog #audioWorkspace[data-model-detail=suno] #audioAceCard,
#wbModelDialog #audioWorkspace[data-model-detail=ace-music] #audioSunoCard{display:none}
#wbModelNewsTitle{position:absolute;width:1px;height:1px;margin:0;padding:0;overflow:hidden;
 clip-path:inset(50%);white-space:nowrap}
.wb-model-promo,.wb-model-story{min-width:0;border-radius:14px}
.wb-model-promo{position:relative;isolation:isolate;display:grid;align-items:center;min-height:210px;
 overflow:hidden;padding:clamp(16px,1.8vw,28px);color:#f7f8ff;background:#15202d;
 border:1px solid light-dark(#b8c1c9,#465467)}
.wb-model-hero-art{position:absolute;inset:0;width:100%;height:100%;object-fit:cover;object-position:50% 53%;z-index:-2}
.wb-model-promo::before{content:"";position:absolute;inset:0;z-index:-1;
 background:linear-gradient(90deg,#0b1520 0%,#0b1520ea 21%,#0b1520be 54%,#0b152054 78%,#0b152014 100%),
 linear-gradient(0deg,#0b152069 0%,transparent 55%)}
.wb-model-promo>.wb-model-symbol{position:absolute;inset:12px 12px auto auto;width:35px;height:35px;
 border-radius:9px;background:#f1f5fb;border:1px solid #d0deff}
.wb-model-promo>.wb-model-symbol img{width:23px;height:23px}
.wb-model-promo-body{position:relative;display:grid;justify-items:start;gap:8px;width:min(74%,345px)}
.wb-model-promo-body h3,.wb-model-promo-body p{margin:0}
.wb-model-promo-body h3{font-size:clamp(22px,2.15vw,31px);font-weight:760;line-height:1.1;text-wrap:balance}
.wb-model-promo-body p{max-width:265px;font-size:12px;line-height:1.45;color:#f0f2ff;text-wrap:pretty}
.wb-model-promo .wb-model-eyebrow{font-weight:700;color:#ffcd9a}
#wbModels #wbModelPromoSetup{gap:8px;min-height:40px;padding:5px 10px;white-space:normal;text-align:start;
 color:#122137;background:#f1f5fb;border:1px solid #b6c7db;border-radius:9px;box-shadow:none}
#wbModels #wbModelPromoSetup:hover{background:#fff}
.wb-model-story{display:grid;grid-template-columns:minmax(91px,27%) minmax(0,1fr);align-items:center;
 gap:clamp(9px,1.15vw,15px);padding:9px 13px 9px 9px;border:1px solid var(--wb-line);background:var(--wb-surface)}
.wb-model-story-art{width:100%;display:block;aspect-ratio:1.22;object-fit:cover;border-radius:9px;background:var(--wb-line)}
.wb-model-story-body{display:grid;gap:5px;min-width:0}
.wb-model-story p,.wb-model-story h3{margin:0}
.wb-model-story h3{font-size:14px;line-height:1.25}
.wb-model-story p{color:var(--muted);font-size:12px;line-height:1.4}
.wb-model-story-meta,.wb-model-story-foot{display:flex;align-items:center;justify-content:space-between;
 gap:3px 10px;flex-wrap:wrap}
.wb-model-story-meta time{font-variant-numeric:tabular-nums;white-space:nowrap}
.wb-model-story-foot{color:var(--muted);font-size:11px}
.wb-model-story-actions{display:flex;align-items:center;flex-wrap:wrap;gap:0 10px}
#wbModels .wb-model-inline-setup{min-height:30px;padding:2px 6px;border-radius:6px;white-space:nowrap;
 background:light-dark(#e6edf6,#26374a);color:light-dark(#21497e,#c2dafe);border:0;box-shadow:none;font-size:11px}
#wbModels .wb-model-inline-setup:hover{box-shadow:var(--wb-dock-inset)}
.wb-model-external{display:inline-flex;align-items:center;gap:3px;min-height:30px;padding:3px 0;
 color:light-dark(#224e8d,#a6c7ff);text-decoration:underline;text-underline-offset:2px}
@media(pointer:coarse){
 #wbModels :is(#wbModelPromoSetup,.wb-model-inline-setup),.wb-model-external{min-height:44px}
}
#articleWritingRules{min-width:0}
#articleWritingRules .wb-about-card{padding:8px 12px}
#articleWritingRules #writingRules{margin-top:5px}
@media(max-width:600px){
 .oa-native #wbAudioWork{padding-inline:14px calc(var(--wb-side-width) + 12px)}
}
 .oa-management #wbPlatformCoverage button{gap:4px;flex:none;padding:2px 6px;min-height:23px;
  border-radius:6px;background:transparent;box-shadow:none;border:1px solid var(--line);font-size:10px}
 #wbPlatformCoverage button[aria-pressed=true]{color:var(--accent);border-color:var(--accent)}
 #wbPlatformCoverage .oa-platform-mark{width:14px;height:14px;flex-basis:14px;padding:2px}
 #wbPlatformCoverage .oa-platform-logo{width:10px;height:10px}
 #wbPublished .jh-platform-work .jh-rank-scope>div{max-height:140px}
/* A wide page can use both sides of the fixed central notch for its first row. */
@media(min-width:1024px){
 .oa-native:is([data-workbench=monitor],[data-workbench=assets]) #videoDirectorDesk>.dd-toolbar{
  display:flex;justify-content:flex-end;min-height:var(--wb-notch-height)
 }
 .oa-native[data-workbench=monitor] #videoDirectorDesk>.dd-toolbar{
  padding-inline-end:var(--wb-top-tools-clearance)
 }
 #wbCanvasControls{
  inset-block-start:3px;inset-inline-end:calc(13px + var(--wb-top-tools-clearance));
  max-width:calc((100% - var(--wb-notch-width))/2 - var(--wb-top-tools-clearance) - 24px)
 }
}
@media(max-width:699px){
 .oa-native[data-workbench=canvas] .dd-canvas-toolbar>.dd-actions:last-child{bottom:calc(var(--wb-dock) + 38px)}
 .oa-native[data-workbench=canvas]:not([data-workbench-has-work]) .dd-canvas-toolbar>.dd-actions:last-child{bottom:calc(var(--wb-dock) + 4px)}
 .oa-native[data-workbench=canvas] .dd-footer{bottom:calc(var(--wb-dock) + 78px)}
 .oa-native[data-workbench=canvas] #directorCanvasFeedback{bottom:calc(var(--wb-dock) + 103px)}
}
@media(max-width:380px){
 .wb-context{gap:2px}
 .oa-native .wb-context button{font-size:11px;padding-inline:5px}
}
@media(max-width:1020px){
 .wb-dock-wrap{width:calc(100% - 12px)}
 .wb-dock{--wb-dock-edge:44px;--wb-dock-child:36px;--wb-dock-slot:44px;grid-template-columns:var(--wb-dock-edge) minmax(0,1fr) 28px var(--wb-dock-tail);padding:4px}
 .wb-dock-entries{
  padding:4px;scroll-padding-inline:4px;overflow-x:auto;overscroll-behavior-x:contain;scroll-snap-type:x mandatory;scrollbar-width:none
 }
 .wb-dock-entries::-webkit-scrollbar{display:none}
 .wb-dock-entries:has(:focus-visible){scroll-snap-type:none}
 .oa-management.oa-native .wb-dock button{height:44px;min-height:44px;scroll-snap-align:start}
 .oa-management.oa-native .wb-dock .wb-dock-step{display:grid;place-items:center}
 .wb-dock-step[data-direction=back] svg{transform:rotate(180deg)}
}
/* The editing engine still updates its original controls for native commands. */
#dmCutTransport,body:not([data-workbench=l-unify]) #wbLunifyNavigation :is(#imw-video-toggle,#imw-settings-toggle){display:none!important}
body:not([data-workbench=l-unify]) .wb-lunify-entry[data-wb-disclosure]{--wb-group-slots:3!important}
.oa-native[data-imw-video=true] #wbSideActions{display:none}
/* The L-unify transport stays in the dock alongside the L-unify destinations. */
.oa-native:is([data-workbench=l-unify],[data-workbench=l-unify-songs],[data-workbench=l-unify-home]) .wb-dock lus-transport{display:block;min-width:0}
.oa-native #wbMusicHome.lh-project-home{position:relative}
#wbMusicHome.lh-project-home>.lh-status:not(:empty):has(+.lh-content>.lh-project-layout){
 position:absolute;inset:auto 0 calc(var(--wb-dock) - 2px);margin:0;
 text-align:center;font-size:11px;line-height:14px;pointer-events:none
}
@media(min-width:821px) and (max-width:1280px){
 .oa-management.oa-native:is([data-workbench=l-unify],[data-workbench=l-unify-songs],[data-workbench=l-unify-home]){--wb-dock:106px}
 .oa-native:is([data-workbench=l-unify],[data-workbench=l-unify-songs],[data-workbench=l-unify-home]) .wb-dock{align-items:start}
 .oa-native:is([data-workbench=l-unify],[data-workbench=l-unify-songs],[data-workbench=l-unify-home]) .wb-dock-entries{
  display:grid;grid-template-columns:repeat(6,max-content);justify-content:safe center;padding-block:0
 }
 .oa-native:is([data-workbench=l-unify],[data-workbench=l-unify-songs],[data-workbench=l-unify-home]) .wb-dock-entries>:not(lus-transport){grid-row:1}
 .oa-native:is([data-workbench=l-unify],[data-workbench=l-unify-songs],[data-workbench=l-unify-home]) .wb-dock lus-transport{
  grid-column:1/-1;grid-row:2;display:flex;justify-content:center
 }
}
@media(max-width:820px){
 .oa-management.oa-native:is([data-workbench=l-unify],[data-workbench=l-unify-songs],[data-workbench=l-unify-home]){--wb-dock:106px}
 .oa-native:is([data-workbench=l-unify],[data-workbench=l-unify-songs],[data-workbench=l-unify-home]) .wb-dock-wrap{width:min(620px,calc(100% - 16px))}
 .oa-native:is([data-workbench=l-unify],[data-workbench=l-unify-songs],[data-workbench=l-unify-home]) .wb-dock>lus-transport{grid-column:1/-1}
}
.wb-dock lus-transport[hidden]{display:none}
.oa-management.oa-native .wb-dock-entries button[data-wb-route]{
 flex:none;width:var(--wb-primary-width);padding-inline:12px
}
.wb-dock-entries [data-wb-disclosure]{
 --wb-group-width:max(calc(var(--wb-primary-width) + 8px),calc(var(--wb-dock-slot) * var(--wb-group-slots)));
 --wb-group-slot:calc(var(--wb-group-width) / var(--wb-group-slots));
 flex:0 0 auto;width:var(--wb-primary-width);height:var(--wb-dock-edge);border-radius:999px;
 background:var(--wb-dock-group-surface);box-shadow:var(--wb-dock-group-raised)
}
.wb-dock-entries [data-wb-disclosure][data-open]{
 width:var(--wb-group-width);background:transparent;box-shadow:none
}
.wb-dock-entries [data-wb-disclosure]:not([data-open]):has(>button[aria-current=page]){
 box-shadow:var(--wb-dock-group-inset)
}
body.oa-management.oa-native[data-workbench] .wb-dock [data-wb-disclosure] button{
 background:transparent;box-shadow:none;border:0
}
body.oa-management.oa-native[data-workbench] .wb-dock [data-wb-disclosure]>button{
 height:var(--wb-dock-edge);width:var(--wb-primary-width);padding:0;border-radius:999px
}
body.oa-management.oa-native[data-workbench] .wb-dock [data-wb-disclosure]>button:is(:hover,:active,[aria-current=page]){
 color:var(--wb-dock-active)
}
body.oa-management.oa-native[data-workbench] .wb-dock [data-wb-disclosure][data-open]>button{
 width:var(--wb-group-slot);gap:0
}
.wb-dock [data-wb-disclosure]>button>span:last-child{
 min-width:0;max-width:var(--wb-primary-width);overflow:hidden;opacity:1
}
.wb-dock [data-wb-disclosure][data-open]>button>span:last-child{max-width:0;opacity:0}
body.oa-management.oa-native[data-workbench] .wb-dock [data-wb-disclosure][data-open]
 >button[aria-current=page]:not(:hover){color:inherit}
.oa-management.oa-native .wb-dock-expansion{
 display:flex;align-items:center;flex:1;min-width:0;height:100%;overflow:hidden;opacity:0;pointer-events:none
}
.oa-management.oa-native .wb-dock-expansion[data-open]{
 opacity:1;pointer-events:auto
}
.wb-dock-expansion-items{
 display:grid;grid-auto-flow:column;grid-auto-columns:var(--wb-group-slot);place-items:center;flex:none
}
@media(prefers-reduced-motion:no-preference){
 .wb-dock-entries [data-wb-disclosure],
 body.oa-management.oa-native[data-workbench] .wb-dock [data-wb-disclosure]>button{
  transition:width 220ms cubic-bezier(.2,.72,.24,1),gap 220ms cubic-bezier(.2,.72,.24,1)
 }
 .wb-dock-entries [data-wb-disclosure]{transition:width 220ms cubic-bezier(.2,.72,.24,1),box-shadow 110ms ease,background-color 110ms ease}
 .wb-dock [data-wb-disclosure]>button>span:last-child{transition:max-width 200ms ease,opacity 100ms ease}
 .oa-management.oa-native .wb-dock-expansion{transition:opacity 150ms ease}
}
body.oa-management.oa-native[data-workbench] .wb-dock [data-wb-disclosure] .wb-dock-expansion button{
 flex:none;width:var(--wb-dock-child);height:var(--wb-dock-child);min-height:var(--wb-dock-child);
 border-radius:8px;padding:0;background:var(--wb-dock-group-surface);box-shadow:var(--wb-dock-child-raised)
}
body.oa-management.oa-native[data-workbench] .wb-dock [data-wb-disclosure] .wb-dock-expansion
 button:is(:hover,[aria-pressed=true],:active){
 background:color-mix(in srgb,var(--wb-dock-active) 10%,var(--wb-dock-group-surface));color:var(--wb-dock-active)
}
@media(max-width:600px){
 body.oa-management.oa-native[data-workbench]{--wb-board-card-inset:9px}
}

'''

SCRIPT = r'''
function OAWorkbenchDockDisclosure(trigger,options,focusOption){
 const dock=options.closest('.wb-dock');
 const motion=matchMedia('(prefers-reduced-motion: no-preference)');
 const group=trigger.parentElement;
 group.dataset.wbDisclosure='';
 group.style.setProperty('--wb-group-slots',options.querySelectorAll('button').length+1);
 trigger.after(options);
 let collapseTimer;
 function show(open){
   trigger.setAttribute('aria-expanded',String(open));
   if(options.hasAttribute('data-open')===open)return;
   clearTimeout(collapseTimer);
   options.inert=!open;
   if(open){
     options.hidden=false;
     if(motion.matches)group.getBoundingClientRect();
   }
   group.toggleAttribute('data-open',open);
   options.toggleAttribute('data-open',open);
   if(!open){
     const collapse=()=>{options.hidden=true;};
     if(motion.matches)collapseTimer=setTimeout(collapse,240);
     else collapse();
   }
 }
 dock.addEventListener('keydown',event=>{
   if(!options.hasAttribute('data-open'))return;
   if(event.key==='Escape'&&options.contains(event.target)){
     event.preventDefault();trigger.focus();
   }else if(event.target===trigger&&event.key==='ArrowDown'){
     event.preventDefault();focusOption()?.focus();
   }
 });
 return {show};
}

function OAWorkbench({open, readAnalytics, readActivity, openActivity, openLink, accountName, platformName, platformDirectoryIcon}){
 const $=id=>document.getElementById(id),body=document.body,home=$('wbBrand');
 const dock=document.querySelector('.wb-dock');
 const side=$('wbSideActions'),sideTool=$('wbSideTool'),boardRefresh=$('openAhoyBoardRefresh');
 const assetOptions=$('wbAssetNavigation'),assetSource=$('wbAssetSources');
 const mainTool=key=>dock.querySelector('[data-wb-route="'+key+'"]');
 const assetDock=OAWorkbenchDockDisclosure(mainTool('jiusera-assets'),assetOptions,()=>assetSource);
 const lunifySongs=$('wbLunifySongs'),lunifyStudio=$('wbLunifyStudio');
 const lunifyDock=OAWorkbenchDockDisclosure(mainTool('l-unify-home'),$('wbLunifyNavigation'),
   ()=>surface==='l-unify'?lunifyStudio:lunifySongs);
 lunifySongs.onclick=()=>open('l-unify-songs');
 lunifyStudio.onclick=()=>open('l-unify');
 assetSource.onclick=()=>open('sources');
 const sideTargets={
   published:()=>['refresh','刷新统计',$('wbPublishedRefresh')],
   monitor:()=>['refresh','刷新',$('directorRefresh')],
   canvas:()=>['settings','项目与作品',$('wbProject')],
   assets:()=>!$('directorAssetBack').hidden?['arrow','返回资产库',$('directorAssetBack')]:null,
   'l-unify-home':()=>['audio','音乐配方',null,'music-recipes'],
   'l-unify':()=>['audio','音乐配方',null,'music-recipes'],
   about:()=>['arrow','返回工作画布',null,'jiusera-canvas'],
   models:()=>['arrow','返回设置',null,'about'],
   'audio-workspace':()=>['arrow','返回音频资产',null,'audio'],
   profile:()=>['arrow','Jiusera 作品首页',null,'published'],
   douyin:()=>['arrow','返回 OpenAhoy',null,'openahoy'],
   platform:()=>body.classList.contains('oa-wechat-view')?null:['refresh','刷新账号',$('refresh')]
 };
 let sideAction=null;
 const syncSideState=()=>{
   const target=sideAction?.[2];
   sideTool.disabled=Boolean(target?.disabled);
   for(const name of ['aria-busy','aria-expanded']){
     const value=target?.getAttribute(name);
     if(value===null||value===undefined)sideTool.removeAttribute(name);
     else sideTool.setAttribute(name,value);
   }
 };
 const sideState=new MutationObserver(syncSideState);
 function paintSide(next){
   assetSource.setAttribute('aria-pressed',String(next==='assets'&&!$('sourceLibrary').hidden));
   const action=sideTargets[next]?.()||null;
   if(sideAction?.[2]!==action?.[2]){
     sideState.disconnect();
     if(action?.[2])sideState.observe(action[2],{attributes:true,attributeFilter:['disabled','aria-busy','aria-expanded']});
   }
   sideAction=action;
   side.toggleAttribute('data-collapsed',next!=='openahoy'&&!action&&!body.classList.contains('oa-wechat-view'));
   boardRefresh.hidden=next!=='openahoy';
   sideTool.hidden=!action;
   if(!action)return;
   const [icon,label]=action;
   for(const node of sideTool.querySelectorAll('[data-side-icon]'))node.toggleAttribute('data-active',node.dataset.sideIcon===icon);
   OAUI.attr(sideTool,'aria-label',label);
   OAUI.attr(sideTool,'title',label);
   syncSideState();
 }
 sideTool.onclick=()=>{
   if(!sideAction)return;
   const [,,target,route]=sideAction;
   if(target)target.click();else if(route)open(route);
 };
 document.addEventListener('jiusera:asset-category',()=>{if(surface==='assets')paintSide(surface);});
 OAUI.attr(home,'aria-label','关于 Jiusera');
 OAUI.attr(home,'title','关于 Jiusera');
 const dockEntries=$('wbDockEntries'),dockStep=dock.querySelector('.wb-dock-step');
 const dockTip=$('wbDockTip');
 let tipButton;
 function placeDockTip(){
   if(!tipButton)return;
   const button=tipButton.getBoundingClientRect(),track=dockEntries.getBoundingClientRect();
   dockTip.hidden=!tipButton.closest('.wb-dock-expansion[data-open]')||
     button.right<=track.left||button.left>=track.right;
   if(dockTip.hidden)return;
   dockTip.textContent=tipButton.getAttribute('aria-label');
   const view=document.documentElement.clientWidth;
   dockTip.style.left=Math.max(8,Math.min(view-dockTip.offsetWidth-8,
     (Math.max(button.left,track.left)+Math.min(button.right,track.right)-dockTip.offsetWidth)/2))+'px';
   dockTip.style.top=(button.top-dockTip.offsetHeight-9)+'px';
 }
 function targetDockTip(button){
   tipButton=button;
   if(button)placeDockTip();
   else dockTip.hidden=true;
 }
 const dockOption=target=>target?.closest?.('.wb-dock-expansion[data-open] button');
 dockEntries.addEventListener('pointerover',event=>{
   if(event.pointerType==='mouse'&&dockOption(event.target))targetDockTip(dockOption(event.target));
 });
 dockEntries.addEventListener('pointerout',event=>{
   if(dockOption(event.target)===tipButton&&dockOption(event.relatedTarget)!==tipButton){
     targetDockTip(dockOption(document.activeElement));
   }
 });
 dockEntries.addEventListener('focusin',event=>{
   if(dockOption(event.target)&&event.target.matches(':focus-visible'))targetDockTip(event.target);
 });
 dockEntries.addEventListener('focusout',event=>{
   if(event.target===tipButton)targetDockTip(null);
 });
 dockEntries.addEventListener('scroll',placeDockTip,{passive:true});
 dockEntries.addEventListener('transitionend',event=>{
   if(event.propertyName!=='width'||!event.target.matches('[data-wb-disclosure][data-open]'))return;
   const parent=event.target.firstElementChild;
   if(parent.getAttribute('aria-current')==='page')revealDockEntry(parent);
   placeDockTip();
 });
 function revealDockEntry(entry){
   if(!entry||!dockEntries.contains(entry)||dockEntries.scrollWidth<=dockEntries.clientWidth)return;
   const track=dockEntries.getBoundingClientRect();
   const group=entry.closest('.wb-openahoy-entry,.wb-asset-entry,.wb-canvas-entry,.wb-lunify-entry');
   if(group&&getComputedStyle(group).display!=='contents'&&group.getBoundingClientRect().width<=track.width)entry=group;
   const button=entry.getBoundingClientRect();
   const offset=button.left<track.left?button.left-track.left:Math.max(0,button.right-track.right);
   if(Math.abs(offset)>.5)dockEntries.scrollBy({left:offset,behavior:'instant'});
 }
 function updateDockStep(){
   const back=dockEntries.scrollLeft>0&&dockEntries.scrollLeft+dockEntries.clientWidth>=dockEntries.scrollWidth-1;
   dockStep.dataset.direction=back?'back':'forward';
   const label=back?'查看前面的入口':'查看后面的入口';
   OAUI.attr(dockStep,'aria-label',label);
   OAUI.attr(dockStep,'title',label);
 }
 dockEntries.addEventListener('scroll',updateDockStep,{passive:true});
 OAUI.onChange(()=>{
   revealDockEntry(dockEntries.querySelector('[aria-current=page]'));
   updateDockStep();
   placeDockTip();
 });
 dockEntries.addEventListener('focusin',event=>requestAnimationFrame(()=>{
   if(document.activeElement===event.target)revealDockEntry(event.target);
 }));
 new ResizeObserver(()=>{
   revealDockEntry(dockEntries.querySelector('[aria-current=page]'));
   updateDockStep();
   placeDockTip();
 }).observe(dockEntries);
 dockStep.addEventListener('click',()=>{
   const next=dockStep.dataset.direction==='back'?-1:1;
   dockEntries.scrollBy({left:next*dockEntries.clientWidth,
     behavior:matchMedia('(prefers-reduced-motion: reduce)').matches?'instant':'smooth'});
 });
 const selector=$('wbPublishedAccount'),platformSelector=$('wbPublishedPlatform');
 const state=$('wbPublishedState');
 const overview=JiuseraOverview({readActivity,openActivity});
 const trend=JiuseraTrend($('wbComparisonTrend'),key=>OAUI.format(key));
 const gallery=JiuseraPlatformWorks($('wbPublished'),{render:renderWork,
   meta:row=>OAUI.format('阅读 {0}',[formatCount(row.traffic)]),t:key=>OAUI.format(key)});
 const supported=new Set(['BOUND','BOUND_IDLE','CONNECTED','BUSY']);
 const newElement=(tag,text)=>{const node=document.createElement(tag);if(text)OAUI.set(node,text);return node;};
 let surface='startup',bound=[],platforms=new Map(),checkedAccounts=false,accountsFailed=false,accountKey='';
 let renderFrame=0,workers=0,platformMarkup='',trendMarkup='',rankingMarkup='';
 const reports=new Map(), pending=new Set(), queue=[];
 const periodDays=7;
 const validCount=value=>Number.isFinite(value)&&value>=0;
 const datePattern=/^\d{4}-\d{2}-\d{2}$/;
 const dayLabel=value=>value.slice(5).replace('-','/');
 const clock=new Intl.DateTimeFormat('en-US',{timeZone:'Asia/Shanghai',year:'numeric',month:'2-digit',day:'2-digit',
   hour:'2-digit',minute:'2-digit',hourCycle:'h23'});
 const key=row=>JSON.stringify([row.platform_id,row.connection_id,row.account_id,row.binding_revision]);
 const selected=()=>bound.find(row=>key(row)===accountKey);
 const canRead=row=>row?.platform_id==='wechat_official_account'&&supported.has(row.state);
 const scoped=()=>selected()?[selected()]:bound.filter(row=>!platformSelector.value||row.platform_id===platformSelector.value);
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

 function panel(key=''){
   body.dataset.workbenchPanel=key;
   $('wbProject').setAttribute('aria-expanded',String(key==='project'));
   $('wbShot').setAttribute('aria-expanded',String(key==='shot'));
 }
 for(const [id,target] of [['wbProject','project'],['wbShot','shot']]){
   $(id).onclick=()=>{panel(body.dataset.workbenchPanel===target?'':target);};
 }
 home.onclick=()=>{if(surface!=='about')open('about');};
 document.addEventListener('click',event=>{
   const current=body.dataset.workbenchPanel;
   if(current&&!event.target.closest('#wbCanvasControls,#directorWorkbar,#wbCanvasDetails,#wbSideActions,dialog'))panel();
 });
 document.addEventListener('keydown',event=>{
   if(event.key!=='Escape'||event.defaultPrevented||document.querySelector('dialog[open]'))return;
   if(body.dataset.workbenchPanel){event.preventDefault();const trigger=body.dataset.workbenchPanel==='project'?'wbProject':'wbShot';panel();$(trigger).focus();}
 });
 const dockSurfaces={
   'jiusera-canvas':'canvas',
   'jiusera-assets':'assets',
   'l-unify-home':'l-unify-home'
 };
 document.addEventListener('click',event=>{
   const route=event.target.closest('[data-wb-route]')?.dataset.wbRoute;
   if(route&&surface===dockSurfaces[route]&&!(route==='jiusera-assets'&&!$('directorAssetBack').hidden))return;
   if(route)open(route);
 });

 function paint(next,{showCanvas=false}={}){
   if(surface!==next){
     panel();
     targetDockTip(null);
     if(next!=='published')gallery.pause();
   }
   surface=next;
   body.dataset.workbench=next;
   if(next!=='startup'){
     const brand=['openahoy','platform','douyin'].includes(next)?'openahoy':
       ['l-unify-home','l-unify-songs','l-unify'].includes(next)?'lunify':'jiusera';
     if(!home.dataset.brand)requestAnimationFrame(()=>requestAnimationFrame(()=>{home.dataset.brandReady='';}));
     if(home.dataset.brand!==brand)home.dataset.brand=brand;
   }
   $('wbStartup').hidden=next!=='startup';
   $('wbPublished').hidden=next!=='published';
   $('wbOpenAhoy').hidden=next!=='openahoy';
   $('wbDouyin').hidden=next!=='douyin';
   $('wbProfile').hidden=next!=='profile';
   $('wbMusic').hidden=next!=='l-unify';
   $('wbMusicHome').hidden=next!=='l-unify-home';
   $('wbMusicSongs').hidden=next!=='l-unify-songs';
   lunifyDock.show(['l-unify-home','l-unify-songs','l-unify'].includes(next));
   lunifySongs.setAttribute('aria-pressed',String(next==='l-unify-songs'));
   lunifyStudio.setAttribute('aria-pressed',String(next==='l-unify'));
   $('wbCanvasControls').hidden=!showCanvas;
   assetDock.show(next==='assets');
   paintSide(next);
   const previousActive=dock.querySelector('[aria-current=page]');
   for(const button of dock.querySelectorAll('[data-wb-route]')){
     const active={canvas:'jiusera-canvas',monitor:'jiusera-canvas',published:'published',assets:'jiusera-assets',openahoy:'openahoy',platform:'openahoy',douyin:'openahoy',profile:'profile','l-unify-home':'l-unify-home','l-unify-songs':'l-unify-home','l-unify':'l-unify-home',about:'about',models:'about','audio-workspace':'jiusera-assets'}[next];
     if(button.dataset.wbRoute===active)button.setAttribute('aria-current','page');else button.removeAttribute('aria-current');
   }
   const currentActive=dock.querySelector('[aria-current=page]');
   if(currentActive!==previousActive)revealDockEntry(currentActive);
   if(next==='published'){restoreAccount();schedulePaint();}
   overview.show(next==='published');
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
   selector.hidden=!accounts.length;
   selector.disabled=!accounts.length;
 }
 function paintAccounts(rows,directory,platformReads){
   const before=selected();
   checkedAccounts=true;
   accountsFailed=Object.values(platformReads||{}).some(part=>part?.state==='FAILED');
   bound=rows;
   platforms=new Map(directory.map(row=>[row.id,row.name]));
   for(const row of bound)if(!platforms.has(row.platform_id))platforms.set(row.platform_id,row.platform_id);
   const live=new Set(bound.filter(canRead).map(key));
   for(const id of reports.keys())if(!live.has(id))reports.delete(id);
   if(before&&!selected()){clearAccount();rememberAccount();}
   overview.accounts(bound.length,accountsFailed);
   if(surface==='published'){restoreAccount();schedulePaint();}
 }
 function accountsUnavailable(){
   accountsFailed=true;
   overview.accounts(checkedAccounts?bound.length:null,true);
   schedulePaint();
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
   rememberAccount();options();schedulePaint();
 }
 platformSelector.onchange=()=>{clearAccount();rememberAccount();options();schedulePaint();};
 selector.onchange=()=>chooseAccount(bound.find(row=>key(row)===selector.value));
 $('wbClearScope').onclick=()=>{
   platformSelector.value='';chooseAccount();
   $('wbPublishedRefresh').focus({preventScroll:true});
 };

 const platformMark={wechat_official_account:'公',x:'X',xiaohongshu:'红'};
 const styleKey=row=>JSON.stringify([row.platform_id,row.connection_id,row.account_id]);
 function windowDays(end){
   if(!end||!datePattern.test(end))return [];
   const finish=Date.parse(end+'T00:00:00Z');
   return Number.isFinite(finish)?Array.from({length:periodDays},(_,index)=>
     new Date(finish-(periodDays-1-index)*86400000).toISOString().slice(0,10)):[];
 }
 function workDays(accounts,field){
   const end=accounts.map(row=>reports.get(key(row))?.[field]?.span.end).filter(Boolean).sort().at(-1);
   return {end,days:windowDays(end)};
 }
 function accountStatus(row,report,busy){
   const source=report?.trend||report?.works;
   const state=!canRead(row)?(row.platform_id==='wechat_official_account'?'unavailable':'unsupported'):
     busy?'reading':report?.failed?'failed':report?.partial?'partial':
     !report?'unread':report.trend?.data.some(day=>validCount(day.read_user))?'ready':'missing';
   const labels={unsupported:'暂不支持统计',unavailable:'账号暂不可读',reading:source?'读取中 · 旧数据':'正在读取…',
     failed:source?'读取失败 · 旧数据':'读取失败',partial:report?.stale?'部分失败 · 含旧数据':'部分失败',
     unread:'未读取',ready:'',missing:'未回报日阅读'};
   const formatSource=part=>part?.span?dayLabel(part.span.start)+'–'+dayLabel(part.span.end):'';
   const time=source?.readAt?Object.fromEntries(clock.formatToParts(source.readAt*1000).map(part=>[part.type,part.value])):null;
   const when=time?time.month+'/'+time.day+' '+time.hour+':'+time.minute:'';
   const title=time?OAUI.format('上次成功读取 {0}（北京时间）',[time.year+'/'+when]):'';
   const coverage=source?formatSource(source):report?.requested?formatSource({span:report.requested}):
     canRead(row)?OAUI.format('近 7 天'):'';
   const details=[state==='ready'?'':OAUI.format(labels[state]),coverage, title].filter(Boolean).join(' · ');
   return {state,label:labels[state]?OAUI.format(labels[state]):'',coverage,when,
     title:details,retry:!busy&&(state==='failed'||state==='partial')};
 }
 function summary(){
   const scope=scoped();
   const byAccount=scope.map(row=>[row,reports.get(key(row))]);
   OAUI.set($('wbCoverage'),checkedAccounts?'{0} 个账号 · {1} 个已查询':'正在读取账号…',
     scope.length,byAccount.filter(([,value])=>value?.trend||value?.works).length);
   const container=$('wbPlatformCoverage');
   const definitions=[...new Set(bound.map(row=>row.platform_id))].map(id=>[id,OAUI.format(platformLabel(id))]);
   const markup=JSON.stringify(definitions);
   if(platformMarkup!==markup){
     platformMarkup=markup;
     container.replaceChildren(...definitions.map(([id])=>{
       const chip=newElement('button');chip.type='button';chip.dataset.platform=id;
       platformDirectoryIcon(chip,id,platformLabel(id));
       chip.onclick=()=>{platformSelector.value=platformSelector.value===id?'':id;platformSelector.onchange();};
       return chip;
     }));
   }
   for(const chip of container.children)chip.setAttribute('aria-pressed',String(platformSelector.value===chip.dataset.platform));
   $('wbClearScope').hidden=!accountKey&&!platformSelector.value;
   const {days,end}=workDays(scope,'trend');
   const relevant=byAccount.filter(([row])=>canRead(row));
   const readings=relevant.flatMap(([,report])=>[...new Map((report?.trend?.data||[]).map(day=>[day.date,day])).values()]);
   const latest=readings.map(item=>item.date).sort().at(-1);
   const known=latest?readings.filter(item=>item.date===latest):[];
   const busy=relevant.some(([row])=>pending.has(key(row)));
   const attempted=relevant.filter(([,report])=>report);
   const historyEnd=end||workDays(scope,'works').end;
   OAUI.set($('wbHomeStatsRange'),historyEnd?'统计窗口 {0} 至 {1}':'近 7 天',windowDays(historyEnd).at(0),historyEnd);
   $('wbHomeMetricBasis').hidden=known.length<2;
   OAUI.raw($('wbHomeReadValue'),known.length?formatCount(known.reduce((total,item)=>total+item.read_user,0)):'—');
   const note=known.length?(busy?'正在读取 · 显示上次数据':'{0} · {1}/{2} 个账号回报'):
     busy?'正在读取…':!checkedAccounts?(accountsFailed?'账号读取失败':'正在读取账号…'):
     !relevant.length?(accountsFailed&&!scope.length?'账号读取失败':scope.length?'所选范围暂无可读统计':'绑定账号后可查看内容数据。'):
     attempted.some(([,report])=>report.failed||report.partial)?'统计读取失败，可重试。':
     attempted.length<relevant.length?'统计尚未读取':'暂无已回报的日序列。';
   OAUI.set($('wbHomeStatsState'),note,latest,known.length,relevant.length);
   const accounts=byAccount.map(([row,value])=>{
     const timeline=new Map((value?.trend?.data||[]).map(day=>[day.date,day.read_user]));
     const id=key(row);
     return {id,styleKey:styleKey(row),
       label:accountName(row),platform:row.platform_id,platformLabel:OAUI.format(platformLabel(row.platform_id)),
       mark:platformMark[row.platform_id],values:days.map(date=>timeline.get(date)??null),
       status:accountStatus(row,value,pending.has(id))};
   });
   const model={title:OAUI.format('日阅读趋势'),hint:OAUI.format(end?'断线为缺报':'读取统计后显示公众号日报。'),
     dates:days,account:accounts,identities:bound.map(row=>({platform:row.platform_id,styleKey:styleKey(row)})),selected:accountKey};
   const nextMarkup=JSON.stringify(model);
   if(trendMarkup===nextMarkup)return;
   trendMarkup=nextMarkup;
   trend.update({...model,select:id=>{
       const row=bound.find(account=>key(account)===id);
       if(row&&accountKey!==id){chooseAccount(row);$('wbClearScope').focus({preventScroll:true});}
       else if(accountKey===id)$('wbClearScope').click();
     },retry:id=>{
       const row=bound.find(account=>key(account)===id);
       if(canRead(row)&&!pending.has(id))enqueue([row],true);
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
 function renderRanking(){
   const scope=scoped();
   const {days,end}=workDays(scope,'works');
   const start=days.at(0);
   const ids=new Set(scope.map(row=>row.platform_id));
   const period=$('wbRankPeriod');
   if(start&&end)OAUI.raw(period,start.slice(-5).replace('-','/')+'–'+end.slice(-5).replace('-','/'));
   else OAUI.set(period,'近 7 天');
   const groups=[...ids].map(id=>{
     const connected=scope.filter(row=>row.platform_id===id);
     const records=connected.flatMap(row=>(reports.get(key(row))?.works?.data||[]).map((item,index)=>({...item,
       id:JSON.stringify([key(row),item.published,item.url||item.title,index]),
       account:accountName(row),traffic:item.read_user})));
     const ranked=start&&end?JiuseraRank(records,start,end):{known:[],missing:[]};
     const eligible=connected.filter(canRead);
     const reported=eligible.filter(row=>reports.get(key(row))?.works).length;
     const note=eligible.length?OAUI.format('已读 {0}/{1} 个公众号。单号最多回读 4 个发表日、40 条；数值为截至各稿统计日的累计阅读人数。',[reported,eligible.length]):
       OAUI.format('当前没有可用于排名的作品流量来源。');
     return {id,label:OAUI.format(platformLabel(id)),...ranked,note,
       empty:OAUI.format(!eligible.length?'暂无可读作品流量':reported?'暂无已报流量作品':'读取统计后查看作品排行')};
   });
   const markup=JSON.stringify(groups);
   if(rankingMarkup!==markup){rankingMarkup=markup;gallery.setPlatforms(groups);}
   state.hidden=groups.length>0;
   if(!groups.length)OAUI.set(state,accountsFailed?'账号读取失败':checkedAccounts?'绑定账号后可查看作品表现。':'正在读取账号…');
 }
 function paintPublished(){
   const eligible=scoped().filter(canRead);
   const busy=eligible.some(row=>pending.has(key(row)));
   const complete=eligible.every(row=>{const item=reports.get(key(row));return item&&!item.partial&&!item.failed;});
   $('wbPublishedRefresh').disabled=!eligible.length||busy;
   OAUI.set($('wbPublishedRefresh'),busy?'正在读取…':complete&&eligible.length?'刷新统计':'读取统计');
   summary();
   renderRanking();
 }
 function schedulePaint(){
   if(surface!=='published'||renderFrame)return;
   renderFrame=requestAnimationFrame(()=>{
     renderFrame=0;
     if(surface==='published')paintPublished();
   });
 }
 OAUI.onChange(schedulePaint);
 function readPart(value,kind,rows,span,previous){
   const states=value.status?.[kind]?.states;
   const hasStates=Array.isArray(states)&&states.length>0;
   const failed=hasStates?states.some(state=>!['EMPTY','READY'].includes(state)):!rows.length;
   const evidence=value.coverage?.[kind];
   const dates=new Set(Array.isArray(evidence?.confirmed_dates)?evidence.confirmed_dates:[]);
   if(failed&&!rows.length&&!dates.size)return {failed,stale:Boolean(previous),data:previous};
   const dayOf=row=>row.date||row.published;
   for(const row of rows)dates.add(dayOf(row));
   const retained=failed?(previous?.data||[]).filter(row=>{
     const day=dayOf(row);return day>=span.start&&day<=span.end&&!dates.has(day);
   }):[];
   const readAt=evidence?.last_success_at??(!failed?value.read_at:null);
   return {failed,stale:retained.length>0,data:{span,data:[...rows,...retained],
     readAt:readAt>0&&Number.isFinite(new Date(readAt*1000).getTime())?readAt:previous?.readAt}};
 }
 const live=id=>bound.some(row=>key(row)===id&&canRead(row));
 async function readScopedAccount(row,refresh){
   const expected=key(row);
   const previous=reports.get(expected);
   try{
     const value=await readAnalytics({connection_id:row.connection_id,days:periodDays,refresh,
       ...(row.binding_revision?{binding_revision:row.binding_revision}:{})});
     if(!live(expected))return;
     const days=windowDays(value?.end);
     if(value?.connection_id!==row.connection_id||value?.days!==periodDays||days[0]!==value?.start||
       (row.binding_revision&&value.binding_revision!==row.binding_revision)||!Array.isArray(value?.articles)||
       !Array.isArray(value?.timeline))throw Error('INVALID_PUBLISHED_RESULT');
     const requested={start:value.start,end:value.end};
     const series=value.timeline.filter(day=>days.includes(day?.date)&&validCount(day.read_user))
       .map(day=>({date:day.date,read_user:day.read_user}));
     const items=value.articles.filter(item=>typeof item?.title==='string'&&days.includes(item.published));
     const daily=readPart(value,'getbizsummary',series,requested,previous?.trend);
     const works=readPart(value,'getarticletotaldetail',items,requested,previous?.works);
     reports.set(expected,{requested,trend:daily.data,works:works.data,
       partial:daily.failed||works.failed,failed:daily.failed&&works.failed&&!daily.data&&!works.data,
       stale:daily.stale||works.stale});
   }catch(_){
     if(live(expected))reports.set(expected,{...previous,failed:true});
   }
 }
 function enqueue(rows,refresh){
   for(const row of rows){
     const id=key(row);
     if(pending.has(id))continue;
     pending.add(id);queue.push({row,id,refresh:refresh||reports.has(id)});
   }
   schedulePaint();
   while(workers<3&&queue.length){
     workers++;
     void runQueue();
   }
 }
 async function runQueue(){
   try{
     while(queue.length){
       const {row,id,refresh}=queue.shift();
       if(live(id))await readScopedAccount(row,refresh);
       pending.delete(id);schedulePaint();
     }
   }finally{
     workers--;
   }
 }
 $('wbPublishedRefresh').onclick=()=>{
   const scope=scoped().filter(canRead);
   if(scope.some(row=>pending.has(key(row))))return;
   const missing=scope.filter(row=>{const item=reports.get(key(row));return !item||item.failed||item.partial;});
   enqueue(missing.length?missing:scope,!missing.length);
 };
 return {paint,paintAccounts,accountsUnavailable,
   failed(){OAUI.set($('wbStartupStatus'),'当前宿主管理工具桥不可用。');}};
}
'''
