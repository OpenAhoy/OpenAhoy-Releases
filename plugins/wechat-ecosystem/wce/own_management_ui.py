"""Jiusera's single-category management workspace. No account I/O here."""
from html import escape
from .own_branding import header as brand_header
from .own_branding import jiusera_header, jiusera_symbols
from .platform_branding import label as platform_label
from .management_workspace_ui import STYLE as WORKSPACE_STYLE


STYLE = r'''
:root{color-scheme:light;--bg:#f7f8fa;--surface:#fff;--soft:#f2f4f7;--ink:#202833;--muted:#627084;--line:#e3e7ee;--accent:#3768c8;--tint:#edf3ff;--raised:0 2px 8px #18334a06;--inset:none;--shadow:var(--raised)}
body.oa-management{margin:0;background:var(--bg);color:var(--ink);font:14px/1.55 -apple-system,BlinkMacSystemFont,"PingFang SC","Microsoft YaHei",sans-serif;-webkit-font-smoothing:antialiased}
.oa-management *,.oa-management *:before,.oa-management *:after{box-sizing:border-box}.oa-management [hidden]{display:none!important}
.oa-shell{min-height:100vh;display:grid;grid-template-columns:156px minmax(0,1fr);margin:auto}
.oa-sidebar{padding:24px 16px;border-right:1px solid var(--line);background:var(--surface);display:flex;flex-direction:column;gap:28px}
.oa-brand{display:flex;align-items:center;min-height:32px}.oa-brand-logo{display:block;width:124px;max-width:100%;line-height:0;flex:none}.oa-brand-logo svg{display:block;width:100%;height:auto}
.oa-sidebar .help{margin:0 0 8px 10px;font-size:12px}.oa-nav{display:grid;gap:4px}.oa-nav button{width:100%;justify-content:flex-start!important;text-align:left;box-shadow:var(--control-shadow);border-color:transparent;background:var(--surface)}
.oa-nav button[aria-current=page]{background:var(--tint);color:var(--accent)}.oa-category{font-size:13px;font-weight:600}
.oa-management .oa-nav button{gap:8px;padding:5px 8px;min-height:40px}.oa-platform-mark{display:inline-flex;align-items:center;justify-content:center;width:30px;height:30px;padding:5px;border-radius:7px;flex:0 0 30px;overflow:hidden}.oa-platform-mark[data-brand=wechat_official_account]{background:#07c160}.oa-platform-mark[data-brand=x]{background:#fff}.oa-platform-logo{display:block;width:20px;height:20px;object-fit:contain}.oa-platform-label{min-width:0;line-height:1.4}.oa-platform-logo--dark{display:none}
@media(prefers-color-scheme:dark){.oa-platform-mark[data-brand=x]{background:#000}.oa-platform-logo--light{display:none}.oa-platform-logo--dark{display:block}}
.oa-content{min-width:0;padding:24px;max-width:1420px;width:100%;margin-inline:auto}.oa-heading{display:flex;align-items:center;justify-content:space-between;gap:16px;margin-bottom:12px}.oa-heading h1{font-size:22px;line-height:1.35;font-weight:650;letter-spacing:-.3px;margin:0}
.oa-management h2{font-size:16px;line-height:1.4;font-weight:650;margin:0}.oa-management h3{font-size:14px;font-weight:600;margin:16px 0 8px}
.oa-management button{min-height:36px;padding:7px 12px;border:1px solid var(--line);border-radius:8px;background:var(--surface);color:var(--ink);box-shadow:var(--control-shadow);font:500 13px/1.5 -apple-system,BlinkMacSystemFont,"PingFang SC",sans-serif;cursor:pointer;display:inline-flex;align-items:center;justify-content:center;gap:6px;transition:box-shadow .16s ease,background .16s ease,border-color .16s ease;white-space:nowrap}
.oa-management button:hover:not(:disabled){background:var(--surface);border-color:var(--control-edge-hover);box-shadow:var(--control-hover)}.oa-management button:active:not(:disabled){background:var(--soft);box-shadow:var(--control-pressed)}.oa-management button:disabled{opacity:.48;cursor:not-allowed;box-shadow:none}.oa-management button.primary{background:var(--surface);color:var(--ink);border-color:var(--accent);font-weight:650;box-shadow:var(--primary-shadow)}.oa-management button.primary:hover:not(:disabled){background:var(--surface);box-shadow:var(--control-hover)}.oa-management button.primary:active:not(:disabled){box-shadow:var(--control-pressed)}.oa-management .quiet{background:transparent}.oa-management .danger{color:#a53c46}
.oa-management :is(button,input,select,textarea,a,summary):focus-visible{outline:2px solid var(--accent);outline-offset:3px}.oa-management svg.oa-icon{display:block;width:16px;height:16px;flex:0 0 16px;stroke:currentColor;fill:none;stroke-width:1.6;stroke-linecap:round;stroke-linejoin:round}
.oa-management .actions{display:flex;align-items:center;gap:8px;flex-wrap:wrap}.oa-management .notice{border:0;background:transparent;margin:0 0 12px;padding:0;color:var(--muted);font-size:12px;line-height:1.5;min-height:18px;box-shadow:none}.oa-management .notice.error{color:#a53c46}
.oa-accounts-layout{display:grid;grid-template-columns:minmax(0,1fr) 252px;gap:16px;align-items:start}.oa-list,.oa-detail,.oa-management .panel{min-width:0;border:1px solid var(--line);background:var(--surface);border-radius:12px;padding:16px;box-shadow:var(--raised)}
.oa-list-head{display:flex;align-items:center;justify-content:space-between;margin-bottom:8px;font-size:12px;color:var(--muted)}.oa-management .count{font-size:12px;font-weight:500;background:transparent;padding:0;margin:0}.oa-management .account{display:flex;align-items:center;min-width:0;gap:12px;border:1px solid transparent;border-radius:8px;background:transparent;padding:10px;margin:0 0 4px;box-shadow:none}.oa-management .account:last-child{margin-bottom:0}.oa-management .account.is-selected{background:var(--tint);border-color:#dce7fb}
.oa-management .avatar{display:flex;align-items:center;justify-content:center;overflow:hidden;flex:0 0 36px;width:36px;height:36px;border:1px solid var(--line);border-radius:9px;background:var(--soft);color:#617086;font-size:17px;box-shadow:none}
.oa-management .account-title,.oa-management .account-select{font-size:14px;line-height:1.5;font-weight:600}.oa-management .account-select{min-height:28px;padding:0;border:0!important;box-shadow:none!important;background:transparent!important;text-align:left;white-space:normal;overflow-wrap:anywhere;justify-content:flex-start}
.oa-management .status{display:block;padding:0;margin-top:2px;background:transparent!important;color:var(--muted);font-size:12px;line-height:1.5;white-space:normal}.oa-management .status.good{color:#3d7661}.oa-management .status:before{content:"";display:inline-block;vertical-align:2px;width:5px;height:5px;border-radius:50%;background:currentColor;margin-right:5px}
.oa-list .account-hint,.oa-list .edit-profile{display:none!important}.oa-management .account-hint{font-size:12px;color:var(--muted);margin-top:4px}.oa-management .edit-profile{font-size:12px;min-height:30px;padding:4px 8px;margin-top:8px}.oa-detail .account{padding:0 0 12px;border-bottom:1px solid var(--line);border-radius:0;margin-bottom:12px}.oa-detail .actions{display:grid;gap:8px}.oa-management .account-id{font-size:12px;overflow-wrap:anywhere;color:var(--muted);margin:8px 0}.oa-detail h2{margin-bottom:12px}
.oa-management label{display:block;font-size:13px;font-weight:500;margin:12px 0 6px}.oa-management input:not([type=checkbox]):not([type=file]),.oa-management select,.oa-management textarea{display:block;width:100%;min-width:0;max-width:100%;border:1px solid #dce2eb;border-radius:8px;background:var(--surface);color:var(--ink);box-shadow:var(--field-shadow);padding:9px 11px;margin-top:6px;font:400 14px/1.6 -apple-system,BlinkMacSystemFont,"PingFang SC",sans-serif}.oa-management input:not([type=checkbox]):not([type=file]),.oa-management select{min-height:38px}.oa-management textarea{min-height:96px;resize:vertical}.oa-management input[type=checkbox]{accent-color:var(--accent);vertical-align:-2px;margin-right:5px}.oa-management .help{font-size:12px;line-height:1.6;color:var(--muted);font-weight:400;margin:6px 0 0}
.oa-management .rule-input{margin-bottom:12px}.oa-management .rule-source{display:block;color:var(--accent);font-size:12px;line-height:1.5;font-weight:400;margin:4px 0}.oa-management .panel{padding:20px;margin-top:16px}.oa-management .panel h2{margin:0 0 6px}.oa-toolbar{display:flex;align-items:center;justify-content:space-between;gap:12px;margin-bottom:16px;flex-wrap:wrap}
.oa-tabs{display:flex;gap:4px;border-bottom:1px solid var(--line);margin-bottom:12px;padding:0 0 8px;width:100%;max-width:100%;flex-wrap:wrap}.oa-tabs button{min-height:34px;padding:6px 12px;border-color:transparent;box-shadow:none;background:transparent;color:var(--muted)}.oa-tabs button[aria-selected=true]{background:var(--tint);color:var(--accent)}
.oa-platform-settings{margin-top:20px;padding-top:16px;border-top:1px solid var(--line)}.oa-platform-settings>h2{margin-bottom:4px}.oa-platform-settings>.help{margin:4px 0 12px}.oa-management #productionRules{margin-top:0}.oa-management #rulesScope{max-width:400px}.oa-management #rulesFields{margin-top:12px}.oa-management #rulesFields>label{border-top:1px solid var(--line);padding-top:12px}.oa-management #rulesFields>label>span:first-child{font-size:14px;font-weight:600}.oa-management #rulesStatus{font-size:12px;line-height:1.5;color:var(--muted);margin:8px 0}
.oa-management details{font-size:13px;margin-top:12px}.oa-management summary{font-size:13px;line-height:1.6;color:var(--muted);cursor:pointer}.oa-management #technicalPanel{overflow-wrap:anywhere}.oa-management #technicalPanel ul{padding-left:20px}.oa-management #technicalPanel li{margin:14px 0;min-width:0}.oa-management #technicalPanel li>p{margin-top:6px}.oa-management #technicalPanel strong{font-size:13px}.oa-management pre{background:var(--soft);border-radius:8px;padding:12px;white-space:pre-wrap;overflow-wrap:anywhere;font:12px/1.7 ui-monospace,monospace}
.oa-management .drawer-head{display:flex;align-items:center;justify-content:space-between;gap:16px}.oa-management #bindingDrawer,.oa-management #review{scroll-margin-top:16px}.oa-management .review-card{padding:16px;background:var(--soft);border:1px solid var(--line);margin-top:16px;box-shadow:none}.oa-management .consent{display:flex;align-items:flex-start;gap:8px;font-weight:400}.oa-management .consent input{flex:none;margin-top:4px}.oa-management #secretLabel input{font-family:ui-monospace,monospace}.oa-management .profile-editor{padding:16px;margin-top:16px;border:1px solid var(--line);border-radius:10px;box-shadow:none}
.oa-management .route-group{margin-top:16px}.oa-management .route-group h3{margin:0 0 4px}.oa-management .route-row{display:grid;grid-template-columns:minmax(0,1fr) 156px;gap:16px;padding:12px 0;border-bottom:1px solid var(--line)}.oa-management .route-row strong{font-size:14px;font-weight:600}.oa-management .route-row p{font-size:12px;line-height:1.6;color:var(--muted);margin-top:4px}.oa-management .route-row code{font-size:12px;overflow-wrap:anywhere}.oa-management .route-aside{display:flex;flex-direction:column;align-items:flex-end;justify-content:center;gap:6px;font-size:12px}.oa-management .route-aside .implemented{color:#3d7661}.oa-management .route-aside a{color:var(--accent);text-decoration:none}.oa-management .route-aside a:hover{text-decoration:underline}
.oa-management .empty{padding:24px 12px;font-size:13px;color:var(--muted);background:transparent;border:0}.oa-footer{display:flex;align-items:center;justify-content:space-between;gap:12px;margin-top:16px;padding-top:12px;border-top:1px solid var(--line);color:var(--muted);font-size:12px}.oa-footer button{min-height:28px;font-size:12px;padding:3px 8px;background:transparent;border:0;box-shadow:none}.oa-management .legacy-only{display:none!important}
/* One bounded workspace; long content scrolls here, never behind the action bar. */
.oa-native .oa-content{padding:20px}.oa-native .oa-account-options{display:grid;grid-template-columns:repeat(auto-fit,minmax(200px,1fr));gap:8px}.oa-native .account{margin:0;padding:8px}.oa-native .account-select{min-height:22px}.oa-native .status{margin-top:0}.oa-native .avatar{width:32px;height:32px;flex-basis:32px}.oa-native .account .help{display:none!important}.oa-native .oa-account-tools{display:flex;align-items:center;justify-content:space-between;gap:12px;margin-top:8px}.oa-native .oa-account-tools details{margin:0}.oa-native #selectedAccount{padding-top:6px}.oa-native .oa-account-tools>.actions{justify-content:flex-end}.oa-native #accountPanel>.help{margin-top:8px}.oa-native .oa-platform-settings>h2,.oa-native #platformHelp{display:none}.oa-native .oa-binding{width:100%;max-width:600px;margin:0 auto;padding:24px}.oa-native .oa-binding .actions{margin-top:20px}.oa-native .oa-binding .notice{margin-top:12px;margin-bottom:0}.oa-native .oa-binding details{margin:12px 0}.oa-native .oa-binding input{font-size:14px}
.oa-native #rulesFields{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));align-content:start;gap:8px}.oa-native .rule-editor{border:1px solid var(--line);border-radius:8px;padding:6px 10px;margin:0;min-width:0;align-self:start;background:var(--surface)}.oa-native .rule-editor summary{width:100%;display:flex;align-items:center;justify-content:space-between;gap:12px;min-height:28px;list-style:none}.oa-native .rule-editor summary:after{content:"+";font-size:16px;color:var(--muted);margin-left:auto}.oa-native .rule-editor[open] summary:after{content:"−"}.oa-native .rule-editor summary strong{font-size:13px;color:var(--ink);font-weight:550;flex:none}.oa-native .rule-summary{font-size:12px;line-height:1.5;color:var(--muted);white-space:nowrap;overflow:hidden;text-overflow:ellipsis;max-width:50%}.oa-native .rule-editor label{margin-top:8px}.oa-native .rule-editor .rule-input{width:100%;margin:8px 0 0;font-size:14px}.oa-native .rule-editor .rule-source{display:block}.oa-native #rulesEditing>label{display:flex;align-items:center;gap:12px;margin:8px 0;flex-wrap:wrap}.oa-native #rulesScope{width:auto;min-width:180px;max-width:100%;margin:0}.oa-native #rulesEditing>details{margin-top:8px}.oa-native #rulesEditing>.actions{margin-top:12px}.oa-native .rules-body>h2{display:none}.oa-native .rules-body>.help{margin:0 0 8px}.oa-native .rules-context{display:flex;align-items:center;justify-content:space-between;gap:12px;flex-wrap:wrap;margin:6px 0}.oa-native .rules-context>label{display:flex;align-items:center;gap:12px;margin:4px 0;flex-wrap:wrap}.oa-native #rulesStatus{margin:4px 0}.oa-native .rules-context>label{margin:0}
.oa-native #nativeWorkspace:has(#rulesCreator:not([hidden]))>.oa-heading,.oa-native #nativeWorkspace:has(#rulesCreator:not([hidden]))>#notice,.oa-native #nativeWorkspace:has(#rulesCreator:not([hidden]))>#accountPanel,.oa-native #nativeWorkspace:has(#rulesCreator:not([hidden]))>.oa-footer,.oa-native #wechatSettings:has(#rulesCreator:not([hidden]))>.oa-tabs{display:none}
.oa-native #nativeWorkspace:has(#rulesCreator:not([hidden]))>#settingsPanel{border:0;padding:0;margin:0}.oa-native #productionRules:has(#rulesCreator:not([hidden])){border:0;padding:0;background:transparent;box-shadow:none}
@media(min-width:800px) and (min-height:600px){.oa-native .oa-shell{height:100dvh;min-height:0;overflow:hidden}.oa-native .oa-content{height:100%;overflow:hidden;display:flex;flex-direction:column}.oa-native #nativeWorkspace{display:flex;flex-direction:column;height:100%;min-height:0}.oa-native #accountPanel{flex:none;max-height:30%;overflow:auto}.oa-native .oa-heading,.oa-native #notice,.oa-native .oa-footer{flex:none}.oa-native .oa-footer{display:none}.oa-native #settingsPanel{display:flex;flex-direction:column;flex:1;min-height:0;margin-top:14px;padding-top:12px}.oa-native #wechatSettings{display:flex;flex:1;min-height:0;flex-direction:column}.oa-native #wechatSettings>.oa-tabs{flex:none}.oa-native #productionRules{flex:1;min-height:0;overflow:hidden;padding:16px}.oa-native #rulesEditing{display:flex;flex-direction:column;height:100%;min-height:0}.oa-native .rules-body{flex:1;min-height:0;overflow:auto;padding:3px}.oa-native #rulesFields{overflow:visible}.oa-native #rulesEditing>.actions{flex:none;border-top:1px solid var(--line);background:var(--surface);padding:12px 0 0;margin:12px 0 0}.oa-native #officialRoutes,.oa-native #technicalPanel{flex:1;min-height:0;overflow:auto;margin-top:0}.oa-native #rulesCreator{height:100%;min-height:0}.oa-native .oa-binding{max-height:100%;overflow:auto}}
@media(max-width:1050px){.oa-content{padding:20px}.oa-accounts-layout{grid-template-columns:1fr}.oa-detail .actions{display:flex;flex-wrap:wrap}.oa-native .oa-account-tools{align-items:flex-start;gap:8px}.oa-native .oa-account-tools>.actions{gap:6px}.oa-native .oa-account-tools button{padding:6px 9px}}
@media(max-width:799px),(max-height:599px){.oa-shell{display:block;min-height:100vh}.oa-sidebar{padding:12px 16px;flex-direction:row;align-items:center;justify-content:space-between;gap:16px;border-right:0;border-bottom:1px solid var(--line)}.oa-brand-logo{width:112px}.oa-sidebar .help{display:none}.oa-nav{display:flex;flex-wrap:wrap}.oa-nav button{width:auto}.oa-content,.oa-native .oa-content{padding:16px}.oa-heading h1{font-size:20px}.oa-native .oa-account-options{grid-template-columns:repeat(auto-fit,minmax(180px,1fr))}.oa-native .oa-account-tools{flex-direction:column}.oa-native .oa-account-tools>.actions{justify-content:flex-start}.oa-native #rulesFields{grid-template-columns:1fr}.oa-management .panel{padding:16px}.oa-native .oa-binding{padding:20px}.oa-native .oa-binding input{font-size:16px}.oa-management button{min-height:40px}.oa-tabs{gap:2px}.oa-tabs button{padding:6px 10px}.oa-native #productionRules:has(#rulesCreator:not([hidden])){padding:0}.oa-native #creatorStatus{overflow-wrap:anywhere}}
@media(max-width:440px){.oa-content,.oa-native .oa-content{padding:12px}.oa-heading{gap:8px;align-items:center}.oa-heading h1{font-size:18px}.oa-heading .actions{gap:6px}.oa-heading button{padding:7px 9px}.oa-heading button span{display:inline}.oa-native .oa-account-options{grid-template-columns:1fr}.oa-native .oa-account-tools>.actions{display:grid;grid-template-columns:1fr 1fr;width:100%}.oa-management .route-row{grid-template-columns:1fr;gap:8px}.oa-management .route-aside{flex-direction:row;align-items:center;justify-content:space-between}.oa-management .drawer-head{align-items:flex-start;gap:12px}.oa-management .drawer-head h2{font-size:16px}.oa-management .drawer-head button{white-space:normal}.oa-native .oa-binding{padding:16px}}
@media(prefers-reduced-motion:reduce){.oa-management button{transition:none}}
'''

STYLE += WORKSPACE_STYLE


def icon(name):
    paths = {'plus':'<path d="M12 5v14M5 12h14"/>',
        'refresh':'<path d="M20 7v5h-5M20 12a8 8 0 1 1-2-6"/>',
        'accounts':'<path d="m12 3 9 5-9 5-9-5 9-5Zm-9 9 9 5 9-5M3 16l9 5 9-5"/>',
        'settings':'<path d="M3 6h5m4 0h9M3 12h11m4 0h3M3 18h2m4 0h12"/><circle cx="10" cy="6" r="2"/><circle cx="16" cy="12" r="2"/><circle cx="7" cy="18" r="2"/>',
        'wechat':'<path d="M17 9a7 6 0 0 0-14 0c0 2 1 3.5 3 4.5L5 16l3-1.5h2"/><path d="M21 15c0-3-2.5-5-6-5s-6 2-6 5 2.5 5 6 5h2l3 1-.7-2.5c1.1-1 1.7-2 1.7-3.5Z"/><path d="M7 8h.01M12 8h.01M13 14h.01M17 14h.01"/>',
        'arrow':'<path d="m9 5 7 7-7 7"/>',
        'audio':'<path d="M4 9v6m4-10v14m4-17v20m4-17v14m4-10v6"/>',
        'image':'<rect x="3" y="4" width="18" height="16" rx="3"/><circle cx="9" cy="9" r="1.4"/><path d="m3 16 5-4 4 3 3-4 6 5"/>',
        'video':'<rect x="3" y="5" width="18" height="14" rx="3"/><path d="m10 9 5 3-5 3z"/>'}
    return '<svg class="oa-icon" viewBox="0 0 24 24" aria-hidden="true">'+paths[name]+'</svg>'


JIUSERA_MARK = '<span class="oa-jiusera-mark" aria-hidden="true"></span>'


def jiusera_sidebar():
    return ('<nav id="jiuseraNav" class="oa-nav" aria-label="Jiusera">'
            '<button id="openMediaStudio" type="button" aria-expanded="false" aria-controls="jiuseraEntries">'
            + JIUSERA_MARK + '<span>Jiusera</span><span class="oa-jiusera-chevron" aria-hidden="true">›</span></button>'
            '<div id="jiuseraEntries" hidden>'
            '<button type="button" data-studio-page="monitor" aria-controls="directorMonitor">导演台</button>'
            '<button type="button" data-studio-page="desk" aria-controls="directorBoard">工作画布</button>'
            '<button type="button" data-studio-page="assets" aria-controls="directorAssetKinds">资产库</button>'
            '</div></nav>')


def platform_sidebar(logo, navigation, *, localized=False):
    brand = brand_header(logo)
    if localized:
        brand = ('<button id="openHome" type="button" aria-label="Jiusera 首页" aria-current="page">'
                 + jiusera_header() + '</button>')
        navigation += (
            '<section id="accountPanel" class="oa-platform-accounts" aria-label="平台账号" hidden>'
            '<div class="oa-list-head"><span>已绑定账号</span><span id="accountCount" class="count">0</span></div>'
            '<div id="accounts" class="oa-account-options"></div></section>'
        )
    return '<aside class="oa-sidebar"><div class="oa-brand">'+brand+'''</div>
'''+('' if localized else '<div id="softwareUpdateSlot"></div>')+'''
<div>'''+(jiusera_sidebar() if localized else '')+'''<p class="help">平台</p><nav id="platformNavigation" class="oa-nav" aria-label="平台导航">'''+navigation+'''</nav></div></aside>'''


def minimax_mark():
    return '<span class="oa-minimax-mark" aria-hidden="true"></span>'


def minimax_cards():
    return ''.join(
        f'''<section id="videoMiniMax{suffix}Card" class="panel" aria-labelledby="videoMiniMax{suffix}Title">
        <div class="oa-video-relay-heading">{minimax_mark()}
        <h2 id="videoMiniMax{suffix}Title">{title}</h2></div>
        <p id="videoMiniMax{suffix}State" role="status"></p><div data-catalog="{site}"></div>
        <div class="oa-provider-actions">
        <button type="button" data-provider-control="{site}" data-action="official">打开官方控制台</button>
        <button type="button" data-provider-control="{site}" data-action="model">模型文档</button>
        <button type="button" data-provider-control="{site}" data-action="assist">让 Codex 帮我开通</button>
        </div><details class="oa-provider-cost"><summary>额度与账单</summary>
        <p class="help">任务用量、套餐额度和已结算账单分别以官方为准。</p>
        <div class="oa-provider-actions"><button type="button" data-provider-control="{site}" data-action="billing">打开官方账单</button>
        <button type="button" data-provider-control="{site}" data-action="usage">核对可用额度</button></div></details>
        <div class="oa-video-key-form"><label for="videoMiniMax{suffix}Credential">API Key</label>
        <input id="videoMiniMax{suffix}Credential" type="password" maxlength="4096" autocomplete="new-password"
               spellcheck="false" autocapitalize="off" required disabled>
        <button id="videoMiniMax{suffix}Save" type="button" class="primary" disabled>保存 API Key</button>
        </div></section>'''
        for site, suffix, title in (('cn', 'CN', 'MiniMax 中国站'), ('global', 'Global', 'MiniMax 国际站'))
    )


def native_page_body(logo, platform_settings):
    """Single native workspace; secret input has its own view in this resource."""
    from .own_inline_binding_ui import HTML as binding_html
    from .video_director_ui import HTML as director_html
    from .workbench_ui import SURFACES, chrome
    from .studio_showcase_ui import HTML as showcase_html
    from .character_library_ui import HTML as characters_html
    from .openai_gif_ui import SETTINGS_HTML as gif_settings
    from .audio_workspace_ui import HTML as audio_html
    from .workflow_guide_ui import HTML as guide_html
    from .own_branding import openahoy_symbol, video_model_mark
    from .writing_workflow_ui import HTML as writing_rules
    home = '''<section id="openAhoyHome" aria-labelledby="homeTitle" hidden>
<header class="wb-about-card">
<h1 id="homeTitle" tabindex="-1">关于与设置</h1>
<p>Jiusera for Codex</p>
<button data-wb-route="jiusera-canvas" type="button">返回工作画布</button>
</header>
<div class="wb-about-grid">
 <section class="wb-about-card" aria-labelledby="wbSoftwareTitle">
  <h2 id="wbSoftwareTitle">版本与更新</h2><div id="softwareUpdateSlot"></div>
 </section>
 <section class="wb-about-card" aria-labelledby="wbHelpTitle">
  <h2 id="wbHelpTitle">帮助与反馈</h2>
  <div id="wbSupportSlot"></div>
  <div class="wb-context"><button id="openWorkflowGuide" type="button" aria-expanded="false" aria-controls="workflowGuide">指导模式</button></div>
 </section>
 ''' + writing_rules + '''
</div>
<section id="homeRecommendations" aria-labelledby="homeRecommendationsTitle" hidden>
<h2 id="homeRecommendationsTitle">推荐插件</h2><div class="oa-home-grid"></div>
</section>
</section>
<section id="wbOpenAhoy" aria-labelledby="wbOpenAhoyTitle" hidden>
 <div class="oa-home-features">
  <h1 id="wbOpenAhoyTitle" tabindex="-1">'''+openahoy_symbol()+'''<span>OpenAhoy</span></h1>
  <p class="help">发布与账号</p>
  <div class="oa-home-grid" id="homeFeatures"></div>
  <p id="homeStatus" class="help" role="status">正在连接管理工具…</p>
 </div>
</section>'''
    mark_style = '<style>.oa-video-relay-heading .oa-minimax-mark{width:70px;aspect-ratio:30/11;border-radius:4px;background:#fff center/contain no-repeat url("' + video_model_mark() + '")}</style>'
    credential = mark_style + '''<div class="oa-provider-grid"><section id="videoArkCard" class="panel"><h2>火山方舟</h2><p class="help">中国站 · 北京</p><p id="videoArkState" role="status"></p><div data-catalog="ark"></div><div class="oa-provider-actions"><button type="button" data-provider-control="ark" data-action="official">打开官方控制台</button><button type="button" data-provider-control="ark" data-action="model">模型文档</button><button type="button" data-provider-control="ark" data-action="assist">让 Codex 帮我开通</button></div><details class="oa-provider-cost"><summary>额度与账单</summary><p class="help">任务用量、套餐额度和已结算账单分别以官方为准。</p><button type="button" data-provider-control="ark" data-action="billing">打开官方账单</button></details><div id="videoArkCredentialForm">
<label id="videoArkCredentialLabel" for="videoArkCredential">API Key</label>
<input id="videoArkCredential" type="password" maxlength="4096" autocomplete="new-password" spellcheck="false" autocapitalize="off" required disabled>
<button id="videoArkCredentialSave" type="button" class="primary" disabled>保存 API Key</button>
</div></section>'''+minimax_cards()+'''
<section id="videoRelayCard" class="panel" aria-labelledby="videoRelayTitle">
<div class="oa-video-relay-heading">'''+minimax_mark()+'''<h2 id="videoRelayTitle">AutoDL · MiniMax H3</h2></div>
<div id="videoRelayForm">
<label for="videoRelayOrigin">中转站 Base URL</label>
<input id="videoRelayOrigin" type="url" maxlength="512" autocomplete="off" spellcheck="false" placeholder="https://" data-default-origin="https://autodl.art" aria-describedby="videoRelayOriginHint" disabled>
<p class="help" id="videoRelayOriginHint">默认使用 AutoDL 官方地址，可改为自己的中转站。</p>
<label for="videoRelayCredential">中转站 Token</label>
<input id="videoRelayCredential" type="password" maxlength="4096" autocomplete="new-password" spellcheck="false" autocapitalize="off" required disabled>
<div class="oa-video-relay-footer"><p id="videoRelayState" role="status" aria-live="polite"></p>
<button id="videoRelaySave" type="button" class="primary" disabled>保存中转站配置</button></div>
</div></section>
<section id="videoTokenHexCard" class="panel" aria-labelledby="videoTokenHexTitle">
<div class="oa-video-relay-heading"><h2 id="videoTokenHexTitle">Token Hex · 方舟视频</h2></div>
<div id="videoTokenHexForm" class="oa-video-tokenhex-form">
<label for="videoTokenHexOrigin">中转站 Base URL</label>
<input id="videoTokenHexOrigin" type="url" value="https://api.tokenhex.com" readonly>
<label for="videoTokenHexCredential">Token Hex Token</label>
<input id="videoTokenHexCredential" type="password" maxlength="4096" autocomplete="new-password" spellcheck="false" autocapitalize="off" disabled>
<div class="oa-video-relay-footer"><p id="videoTokenHexState" role="status" aria-live="polite"></p>
<button id="videoTokenHexSave" type="button" class="primary" disabled>保存 Token Hex 配置</button></div>
<div class="oa-video-relay-footer">
<p id="videoTokenHexModelsState" role="status" aria-live="polite"></p>
<button id="videoTokenHexCheck" type="button" disabled>查询可见模型</button></div>
<div id="videoTokenHexModels" class="oa-video-tokenhex-form" hidden>
<label for="videoTokenHexModel">方舟视频模型</label>
<select id="videoTokenHexModel" disabled></select>
<button id="videoTokenHexSelect" type="button" disabled>选用模型</button>
</div></div></section></div>
<p id="videoProviderNotice" class="help" role="status"></p><textarea id="videoProviderCopy" aria-label="复制 Codex 指令" readonly hidden></textarea>
'''
    from .wechat_analytics_ui import HTML as analytics_html
    return '''<body class="oa-management oa-platform-workspace oa-native" data-workbench="startup">'''+chrome(icon)+'''<div class="oa-shell">
'''+platform_sidebar(logo, '<p class="help">正在读取平台…</p>', localized=True)+'''
<main class="oa-content">'''+guide_html+SURFACES+showcase_html+home+'''<div id="nativeWorkspace" hidden><header class="oa-account-header">
<div class="oa-heading"><div id="accountCurrent"><h1 id="pageTitle" data-oa-overflow>选择平台</h1><small id="accountCaption" hidden></small></div></div>
<div class="actions"><div id="accountTools" class="oa-account-tools"><details class="oa-more-settings"><summary>更多设置</summary><div class="oa-more-popover"><button id="accountRules" disabled>编辑本号配置</button><button id="accountCreate" disabled>快速创建配置</button><button id="accountImport" disabled>加载并保存配置</button><div><button id="accountBackend" disabled>打开公众号后台</button></div><p id="wechatBackendHelp" class="help">使用浏览器现有登录，请核对账号。</p><details><summary>账号信息</summary><div id="selectedAccount"></div></details></div></details></div>
<button id="refresh" aria-label="刷新账号">刷新</button><button id="showAdd" class="primary" aria-label="绑定账号">绑定账号</button></div></header>
<nav id="wechatWorkspaceNavigation" aria-label="公众号工作区" hidden>
<button id="wechatMonitorTab" type="button" aria-pressed="true" aria-controls="wechatAnalytics">数据监控</button>
<button id="wechatConfigTab" type="button" aria-pressed="false" aria-controls="settingsPanel">公众号配置</button>
</nav>
<p id="notice" class="notice" role="status" aria-live="polite">正在连接管理工具…</p>
'''+analytics_html+'''
<section id="settingsPanel" class="oa-platform-settings" aria-label="平台设置"><h2 id="platformTitle">平台设置</h2><p id="platformHelp" class="help"></p>
<div class="actions oa-context-tabs" role="tablist" aria-label="工作区设置"><button id="platformSettingsTab" role="tab" aria-selected="true">平台设置</button><button id="contextSettingsTab" role="tab" aria-selected="false">项目与 Skills</button></div>
<p id="unsupportedSettings" class="empty" hidden>当前平台暂不支持这些设置，未调用其他平台工具。</p>'''+platform_settings+'''</section>
<dialog id="accountNameDialog" class="oa-account-remove-dialog" aria-labelledby="accountNameTitle">
<form id="accountNameForm"><h2 id="accountNameTitle">编辑显示名称</h2>
<label for="accountDisplayName">显示名称</label><input id="accountDisplayName" required maxlength="64" autocomplete="off" autofocus>
<p id="accountNameStatus" role="status"></p>
<div class="actions"><button id="accountNameCancel" type="button">取消</button><button id="accountNameSave" class="primary" type="submit">保存</button></div>
</form></dialog>
<dialog id="accountRemoveDialog" class="oa-account-remove-dialog" aria-labelledby="accountRemoveTitle">
<h2 id="accountRemoveTitle">移除账号</h2>
<p id="accountRemoveTarget"></p>
<p>将断开此账号在 Jiusera 的连接并停止后续自动任务。平台账号、内容、资产和操作记录会保留。</p>
<div class="actions"><button id="accountRemoveCancel" type="button" autofocus>取消</button>
<button id="accountRemoveConfirm" class="danger" type="button">确认移除</button></div>
</dialog>
<dialog id="accountRecoveryDialog" class="oa-account-remove-dialog" aria-labelledby="accountRecoveryTitle">
<h2 id="accountRecoveryTitle">恢复本机绑定</h2>
<p id="accountRecoveryTarget"></p>
<p id="accountRecoveryReason"></p>
<div class="actions"><button id="accountRecoveryClose" type="button" autofocus>关闭</button>
<button id="accountRecoveryAsk" type="button" class="primary" hidden>在 macOS 中确认恢复</button></div>
<p id="accountRecoveryStatus" role="status"></p>
</dialog>
<footer class="oa-footer"><span>Jiusera · 本机账号管理</span></footer></div><section id="mediaStudio" aria-label="Jiusera" hidden>
'''+director_html+'''<div id="monitorComponents" hidden>'''+credential+gif_settings+audio_html+'''</div></section>'''+characters_html+binding_html+'''</main></div>'''


HOME_STYLE = '''
#jiuseraNav{margin-block-end:6px}
#jiuseraEntries[hidden]{display:none!important}
#jiuseraEntries{display:grid;gap:3px;padding-inline-start:19px;min-width:0}
.oa-management .oa-sidebar #jiuseraEntries button{min-height:33px;font-size:12px;gap:4px;padding:5px 8px;
 box-shadow:none;border-color:transparent;background:transparent}
.oa-management .oa-sidebar #jiuseraEntries button[aria-current=page]{
 background:var(--oa-selection,var(--tint));color:var(--accent)}
.oa-management .oa-sidebar #jiuseraEntries button:hover{background:var(--oa-fill,var(--soft))}
.oa-jiusera-chevron{margin-inline-start:auto;color:var(--muted)}
#openMediaStudio[aria-expanded=true] .oa-jiusera-chevron{transform:rotate(90deg)}
@media(max-width:799px),(max-height:599px){
 #jiuseraNav{align-items:center;margin:0}
 #jiuseraEntries{display:flex;flex-wrap:wrap;padding-inline-start:3px;gap:3px}
 .oa-management .oa-sidebar #jiuseraEntries button{min-height:28px;font-size:12px;padding:3px 6px}
}

.oa-management #openHome{width:fit-content;min-height:32px;padding:0;background:transparent;border:0;box-shadow:none}
.oa-management #openHome .oa-brand-logo{display:block}
.oa-jiusera-logo img{display:block;width:100%;height:auto}
.oa-jiusera-logo img+img{display:none}
.oa-management[data-color-scheme="dark"] .oa-jiusera-logo img:first-child{display:none}
.oa-management[data-color-scheme="dark"] .oa-jiusera-logo img+img{display:block}
@media(prefers-color-scheme:dark){
 .oa-management:not([data-color-scheme]) .oa-jiusera-logo img:first-child{display:none}
 .oa-management:not([data-color-scheme]) .oa-jiusera-logo img+img{display:block}
}
.oa-management #openHome:hover:not(:disabled){background:transparent;opacity:.8}
.oa-management #openHome:focus-visible{outline-offset:4px}
#openAhoyHome{width:100%;max-width:1080px;overflow:auto;align-self:center;padding:6px 2px 14px}
#openAhoyHome[hidden],#openAhoyHome [hidden],.oa-management #nativeWorkspace[hidden]{display:none!important}
.oa-home-hero{display:grid;grid-template-columns:minmax(0,1fr) auto;align-items:center;column-gap:20px;padding:clamp(22px,5vw,52px);
 border-radius:20px;background:linear-gradient(124deg,#eef5f2 0%,#f6f8f5 58%,#fcedea 100%);color:#172522}
.oa-home-hero h1{font-size:clamp(32px,5vw,54px);letter-spacing:-.055em;line-height:1.1;align-self:end}
.oa-home-hero p{grid-column:1;max-width:34ch;margin-top:9px;font-size:clamp(13px,1.7vw,17px);color:#45534f;align-self:start}
.oa-home-mark{grid-column:2;grid-row:1/3}
.oa-home-hero img{display:block;width:clamp(52px,12vw,105px);height:auto}
.oa-home-mark img+img{display:none}
.oa-home-features,#homeRecommendations{margin-top:20px}
.oa-home-features h2,#homeRecommendations h2{margin:0 0 9px;font-size:15px}
.oa-home-grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(min(100%,218px),1fr));gap:10px}
.oa-management button.oa-home-card{display:grid;grid-template-columns:minmax(0,1fr) 16px;justify-items:start;align-items:center;gap:4px 8px;text-align:start;
 white-space:normal;padding:12px 13px;min-height:78px;border:0;border-radius:12px;background:var(--oa-fill,var(--soft));box-shadow:var(--raised,0 2px 8px #0001)}
.oa-management button.oa-home-card:hover:not(:disabled){transform:translateY(-1px);background:var(--tint)}
.oa-home-card-title{display:flex;align-items:center;gap:8px;min-width:0;font-weight:650;font-size:14px}
.oa-home-card-title .oa-platform-mark{width:22px;height:22px}
.oa-home-card-description{grid-column:1;font-size:12px;color:var(--muted);line-height:1.4;font-weight:400}
.oa-home-card>.oa-icon{grid-column:2;grid-row:1/3;justify-self:end;color:var(--muted);width:14px}
#homeStatus{margin-top:12px}#homeStatus:empty{display:none}
.oa-management[data-color-scheme="dark"] .oa-home-hero{background:linear-gradient(124deg,#21332d 0%,#282d29 60%,#382829 100%);color:#f3f6f4}
.oa-management[data-color-scheme="dark"] .oa-home-hero p{color:#c9d5cf}
.oa-management[data-color-scheme="dark"] .oa-home-mark img:first-child{display:none}
.oa-management[data-color-scheme="dark"] .oa-home-mark img+img{display:block}
.oa-management[data-color-scheme="dark"] button.oa-home-card{background:#2b2b2f;color:#f3f4f5}
.oa-management[data-color-scheme="dark"] button.oa-home-card:hover:not(:disabled){background:#38383e}
.oa-management[data-color-scheme="dark"] .oa-home-card :is(.oa-home-card-description,svg){color:#c1c2c8}
@media(prefers-color-scheme:dark){
 .oa-management:not([data-color-scheme]) .oa-home-hero{background:linear-gradient(124deg,#21332d 0%,#282d29 60%,#382829 100%);color:#f3f6f4}
 .oa-management:not([data-color-scheme]) .oa-home-hero p{color:#c9d5cf}
 .oa-management:not([data-color-scheme]) .oa-home-mark img:first-child{display:none}
 .oa-management:not([data-color-scheme]) .oa-home-mark img+img{display:block}
 .oa-management:not([data-color-scheme]) button.oa-home-card{background:#2b2b2f;color:#f3f4f5}
 .oa-management:not([data-color-scheme]) button.oa-home-card:hover:not(:disabled){background:#38383e}
 .oa-management:not([data-color-scheme]) .oa-home-card :is(.oa-home-card-description,svg){color:#c1c2c8}
}
@media(max-width:480px){.oa-home-hero{column-gap:10px}.oa-home-features,#homeRecommendations{margin-top:14px}}
'''

_JIUSERA_LIGHT, _JIUSERA_DARK = jiusera_symbols()
HOME_STYLE += f"""
.oa-management{{--oa-jiusera-light:url("{_JIUSERA_LIGHT}");--oa-jiusera-dark:url("{_JIUSERA_DARK}")}}
.oa-jiusera-mark{{width:20px;height:20px;flex:none;background:var(--oa-jiusera-light) center / contain no-repeat}}
.oa-home-card-title .oa-jiusera-mark{{width:22px;height:22px}}
.oa-management[data-color-scheme="dark"] .oa-jiusera-mark{{background-image:var(--oa-jiusera-dark)}}
@media(prefers-color-scheme:dark){{
 .oa-management:not([data-color-scheme]) .oa-jiusera-mark{{background-image:var(--oa-jiusera-dark)}}
}}
"""


def page_body(logo, rules_html, technical_html, routes_html):
    rules_only = rules_html.removeprefix(technical_html).replace('class="card" style="margin-top:24px"', 'class="panel"')
    technical_html = technical_html.replace('微信公众号', '公众号')
    routes_html = routes_html.replace('微信公众号', '公众号')
    rules_only = rules_only.replace('全局默认可按号覆盖', '公众号默认规则可按号覆盖')
    rules_only = rules_only.replace('<option value="">全局默认</option>', '<option value="">公众号默认规则</option>')
    return '''<body class="oa-management oa-platform-workspace"><div class="oa-shell">
'''+platform_sidebar(logo, '<button id="platformWeChat" aria-current="page">'+platform_label('wechat_official_account', '公众号')+'</button>')+'''
<main class="oa-content"><div class="oa-heading"><h1 id="pageTitle">公众号</h1><div class="actions">
<button id="refresh" aria-label="刷新账号">'''+icon('refresh')+'''<span>刷新</span></button>
<button id="showAdd" aria-label="绑定账号">'''+icon('plus')+'''绑定账号</button></div></div>
<p id="notice" class="notice" role="status" aria-live="polite">正在读取公众号…</p>
<section id="accountPanel" aria-label="平台账号"><div id="safeAccountPicker" class="oa-account-cards"><span id="safeAccountCurrent" hidden></span><div class="oa-account-cards-body"><div class="oa-list-head"><span>已绑定账号</span><span id="accountCount" class="count">—</span></div><div id="accounts" class="oa-account-options"></div><div id="selectedAccount"></div><div class="actions"><button id="detailProfile" disabled>显示资料</button><button id="accountRules" disabled>本号规则</button></div><details><summary>连接与账号操作</summary><select id="select" hidden aria-label="所选账号"></select><div class="actions"><button id="checkConnection">检查连接</button><button id="enable">重新启用</button><button id="disconnect" class="danger">断开账号</button></div><p class="help">操作前展示所选账号与影响。绑定状态不代表所有接口权限。</p></details></div></div>
<section id="profileEditor" class="profile-editor" hidden><h3 id="profileTitle">公众号显示资料</h3><div id="profilePreview" class="profile-preview"></div>
<label>公众号名称<input id="profileName" maxlength="64" autocomplete="off"></label><label>公众号头像<input id="profileFile" type="file" accept="image/png,image/jpeg"></label>
<div class="actions"><button id="profileSave" class="primary">保存资料</button><button id="profileCancel">取消</button><button id="profileClear" class="quiet">移除头像</button></div>
<p class="help">仅修改本机显示资料，微信中的名称和头像保持原样。</p></section></section>
<section id="settingsPanel" class="oa-platform-settings" aria-label="平台设置"><h2>平台设置</h2>
<p class="help">默认规则仅用于公众号，可按本号覆盖；不会作用于未来接入的其他平台。</p>
<div class="oa-tabs" role="tablist" aria-label="公众号平台设置">
<button id="settings-rules" role="tab" aria-selected="true">生产规则</button><button id="settings-routes" role="tab" aria-selected="false">官方通路</button>
<button id="settings-technical" role="tab" aria-selected="false">技术格式</button></div>'''+rules_only+'''
<section id="officialRoutes" class="panel" hidden>'''+routes_html+'''</section><section id="technicalPanel" class="panel" hidden>'''+technical_html.replace('<details id="htmlTechnicalStandard">','<details id="htmlTechnicalStandard" open>')+'''</section></section>
<section id="bindingDrawer" class="panel" hidden aria-labelledby="bindingTitle"><div class="drawer-head"><h2 id="bindingTitle">添加公众号</h2><button id="cancelAdding" class="quiet">取消</button></div>
<p class="help">使用公众号 AppID 与 AppSecret 绑定。核对账号后再填写密钥。</p>
<div class="oa-add-fields"><label>AppID<input id="appid" maxlength="18" autocomplete="off" spellcheck="false" placeholder="wx 开头的 AppID"></label>
<label>显示名称<input id="label" maxlength="64" autocomplete="off" placeholder="公众号名称"></label>
<button id="add" class="primary">下一步 · 核对账号</button></div>
<section id="review" class="review-card" hidden><h2 id="reviewTitle" tabindex="-1"></h2><pre id="reviewSummary" class="review-summary"></pre><div id="bodyRecoveryPreview"></div>
<label id="riskLabel" hidden>风险确认短语<input id="riskAck" maxlength="32" autocomplete="off"><span id="riskHelp" class="help"></span></label>
<details class="technical"><summary>完整账号与操作信息</summary><pre id="reviewDetails"></pre></details>
<label id="secretLabel">新号 AppSecret<input id="secret" type="password" maxlength="256" autocomplete="off" spellcheck="false" autocapitalize="off"></label>
<label class="consent"><input id="consent" type="checkbox"><span>我已核对以上账号及本次操作，同意执行。</span></label>
<div class="actions"><button id="commit" class="primary" disabled>确认绑定</button><button id="cancel">取消本次操作</button></div></section>
<p class="help">密钥仅通过本机安全表单提交，验证后存入该号系统钥匙串。</p></section>
<section id="operationPanel" class="panel" hidden aria-live="polite"><h2>操作结果</h2><p id="resultTitle"></p><p id="resultCopy" class="help"></p>
<div class="actions"><button id="readResult">查询原结果</button><button id="continue">继续管理</button></div>
<div id="ipPanel" hidden><p id="ipValue" class="ip-value"></p><button id="copyIP" disabled>复制来源 IP</button></div>
<details><summary>详细回执</summary><pre id="result">尚未提交</pre></details></section>
<div class="legacy-only" hidden><button id="upgrade">升级</button><p id="publicationState"></p><button id="publicationEnable" disabled></button><button id="publicationDisable" disabled></button>
<p id="restoreState"></p><button id="restoreDrafts" disabled></button><button id="loadRecovery"></button><div id="recoveryTargets"></div><button id="recover"></button><button id="recoverBody"></button><button id="recoverBody5"></button></div>
<footer class="oa-footer"><span>Jiusera · 本机账号管理</span><button id="close">结束本次管理</button></footer></main></div>'''


JS = r'''
const OAManagement=(()=>{
 'use strict';const $=id=>document.getElementById(id);let callbacks={},selected='',entries=[],names=new Map(),tab='rules';
 function view(){$('accountPanel').hidden=false;$('settingsPanel').hidden=false;
   $('platformWeChat').setAttribute('aria-current','page');$('pageTitle').textContent='公众号';}
 function settingsTab(name){tab=name;for(const key of ['rules','routes','technical']){
   $('settings-'+key).setAttribute('aria-selected',String(key===name));
   $({rules:'productionRules',routes:'officialRoutes',technical:'technicalPanel'}[key]).hidden=key!==name;}}
 function bind(value){callbacks=value;$('platformWeChat').addEventListener('click',()=>view());
   for(const name of ['rules','routes','technical'])$('settings-'+name).addEventListener('click',()=>settingsTab(name));
   $('showAdd').addEventListener('click',e=>{if(e.isTrusted)callbacks.add(e);});
   $('cancelAdding').addEventListener('click',e=>{if(e.isTrusted)callbacks.cancel(e);});
   $('detailProfile').addEventListener('click',e=>{const row=entries.find(r=>r.connection_id===selected);if(e.isTrusted&&row)callbacks.profile(row);});
   $('accountRules').addEventListener('click',async e=>{if(e.isTrusted&&selected){view();settingsTab('rules');$('settingsPanel').scrollIntoView({block:'start'});await callbacks.rules(selected);}});
 }
 function accounts(rows,choices){entries=rows;names=choices;
   Array.from($('accounts').children).forEach((card,index)=>{
     const row=rows[index];if(!row)return;card.dataset.connectionId=row.connection_id;card.tabIndex=0;card.setAttribute('role','option');
     card.addEventListener('click',e=>{if(e.isTrusted&&!e.target.closest('button,a'))callbacks.choose(row.connection_id,e);});
     card.addEventListener('keydown',e=>{if(e.isTrusted&&e.target===card&&['Enter',' '].includes(e.key)){e.preventDefault();callbacks.choose(row.connection_id,e);}});
     const heading=card.querySelector('.account-title');if(heading){const button=document.createElement('button');button.className='account-title account-select';
       button.textContent=heading.textContent;button.addEventListener('click',e=>{if(e.isTrusted)callbacks.choose(row.connection_id,e);});heading.replaceWith(button);}
     const avatar=card.querySelector('.avatar');if(avatar&&!row.presentation?.avatar){const name=choices.get(row.connection_id)||'公众号';
       avatar.textContent=Array.from(name).slice(-2,-1).join('')||Array.from(name)[0];avatar.setAttribute('aria-label',name+'，未设置头像');}
   });selectedAccount(selected);
 }
 function selectedAccount(id){const picker=$('safeAccountPicker'),caption=$('safeAccountCurrent');if(caption)caption.textContent=id?(names.get(id)||'公众号'):'选择公众号';selected=id;$('accountRules').disabled=!id;for(const card of $('accounts').children){card.classList.toggle('is-selected',card.dataset.connectionId===id);card.setAttribute('aria-selected',String(card.dataset.connectionId===id));}
   if(!id)$('selectedAccount').replaceChildren(Object.assign(document.createElement('p'),{textContent:'选择一个公众号，查看本号设置。'}));
   const row=entries.find(row=>row.connection_id===id);$('detailProfile').disabled=!row||!['MISSING','SAVED'].includes(row.presentation?.state);
   const avatar=$('selectedAccount').querySelector('.avatar');if(row&&avatar&&!row.presentation?.avatar){avatar.textContent=Array.from(names.get(id)||'公众号').slice(-2,-1).join('');const hint=$('selectedAccount').querySelector('.account-hint');if(hint)hint.textContent='未设置头像';}
   if(row?.account_id){const p=document.createElement('p');p.className='account-id';p.textContent='AppID '+row.account_id;$('selectedAccount').append(p);}}
 function reviewing(intent){$('bindingTitle').textContent=intent==='ADD'?'添加公众号':'账号操作';$('bindingDrawer').hidden=false;document.querySelector('.oa-add-fields').hidden=intent!=='ADD';}
 function adding(){reviewing('ADD');view();$('bindingDrawer').hidden=false;$('bindingDrawer').scrollIntoView({block:'start'});$('appid').focus();}
 function cancelled(){$('bindingDrawer').hidden=true;view();}
 function result(value){$('operationPanel').hidden=value.state==='NOT_SUBMITTED';if(['BOUND_IDLE','UPGRADED','DISCONNECTED','TOKEN_CHECK_SUCCEEDED'].includes(value.state))$('bindingDrawer').hidden=true;}
 function busy(value){for(const id of ['showAdd','cancelAdding','platformWeChat','detailProfile','accountRules'])$(id).disabled=value||(['detailProfile','accountRules'].includes(id)&&!selected);$('detailProfile').disabled||=!['MISSING','SAVED'].includes(entries.find(r=>r.connection_id===selected)?.presentation?.state);}
 return {bind,accounts,selected:selectedAccount,adding,reviewing,cancelled,result,busy,view};
})();
'''

