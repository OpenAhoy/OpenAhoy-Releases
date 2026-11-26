"""Viewport layout for the native WeChat workspace."""
STYLE = """
html:has(body.oa-wechat-view),body.oa-wechat-view{overflow:hidden}
body.oa-management.oa-native.oa-wechat-view .oa-shell {
 display:grid;height:100dvh;min-height:0;grid-template:minmax(0,1fr)/minmax(0,1fr);overflow:hidden
}
body.oa-management.oa-native.oa-platform-view.oa-wechat-view .oa-shell{padding-block-start:0}
body.oa-management.oa-native.oa-wechat-view .oa-sidebar {
 display:none
}
body.oa-management.oa-native.oa-wechat-view .oa-content {
 height:100%;min-height:0;min-width:0;max-width:none;overflow:hidden;
 --wx-list-inset:7px;
 --wx-content-top:var(--wb-top);
 padding:calc(var(--wx-content-top) - var(--wx-list-inset)) max(50px,2.2vw) var(--wb-dock,64px) clamp(12px,2.2vw,32px)
}
.oa-native.oa-wechat-view #nativeWorkspace:not([hidden]) {
 display:flex;flex-direction:column;height:100%;min-height:0;min-width:0;overflow:hidden
}
.oa-native.oa-wechat-view #nativeWorkspace > .oa-footer{display:none}
.oa-management.oa-native.oa-wechat-view #nativeWorkspace>.oa-account-header,
.oa-native.oa-wechat-view #wechatAccountPicker .oa-list-head{display:none}
.oa-management.oa-native.oa-wechat-view #wbSideActions{height:200px}
.oa-native.oa-wechat-view:has(#inlineBinding:not([hidden])) #wechatWorkspaceNavigation{display:none}
#wbWechatTools{position:relative;display:grid;align-content:center;pointer-events:none}
#wbWechatTools[hidden],#wbWechatTools [hidden]{display:none}
.oa-management.oa-native #wbWechatTools :is(#wechatWorkspaceBack,.actions,#accountTools):not([hidden]){
 display:contents
}
.oa-management.oa-native #wbWechatTools .oa-more-settings{position:relative;margin:0}
.oa-management.oa-native #wbWechatTools :is(#wechatBack,#refresh,#showAdd,.oa-more-settings>summary){
 display:grid;place-items:center;width:44px;height:44px;min-height:44px;min-width:0;
 margin:0;padding:0;border:0;border-radius:0;background:transparent;color:var(--wb-ink);
 box-shadow:none;pointer-events:auto;list-style:none
}
.oa-management.oa-native #wbWechatTools :is(#wechatBack,#refresh,#showAdd,.oa-more-settings>summary):hover:not(:disabled){
 color:var(--wb-active);background:transparent;box-shadow:none
}
#wbWechatTools .oa-more-settings>summary::-webkit-details-marker,
#wbWechatTools .oa-more-settings>summary::after{display:none}
#wbWechatTools :is(#wechatBack,#refresh,#showAdd,.oa-more-settings>summary)>span{display:none}
#wbWechatTools .oa-icon{width:17px;height:17px}
#wbWechatTools #wechatBack .oa-icon{transform:rotate(180deg)}
#wbWechatTools .oa-more-popover{pointer-events:auto}
#wbWechatTools .oa-more-settings:not([open])>.oa-more-popover{display:none}
#wbWechatTools .oa-more-popover:not([popover]){
 inset-inline:auto calc(100% + 5px);inset-block-start:0
}
.oa-native.oa-wechat-view #wechatAccountPicker{flex:none;min-width:0;min-height:0;margin:0 0 5px}
body.oa-management.oa-native.oa-wechat-view #wechatAccountPicker #accountPanel{
 display:flex;flex-direction:column;min-height:0;max-height:none;
 margin:0;padding:0;border:0;background:transparent;box-shadow:none
}
body.oa-management.oa-native.oa-wechat-view #wechatAccountPicker #accountPanel #accounts{
 display:grid;grid-template-columns:repeat(auto-fit,minmax(min(100%,148px),1fr));align-content:start;
 gap:10px;width:100%;min-height:0;max-height:min(142px,23dvh);padding:var(--wx-list-inset);
 overflow:auto;overscroll-behavior:contain;scrollbar-width:thin;
 background:transparent;border:0;border-radius:0;box-shadow:none
}
body.oa-management.oa-native.oa-wechat-view #wechatAccountPicker #accountPanel #accounts>.account{
 width:auto;min-width:0;max-width:none;border:0;border-radius:12px;
 background:var(--oh-surface);box-shadow:var(--oh-control);color:var(--oh-text)
}
body.oa-management.oa-native.oa-wechat-view #wechatAccountPicker #accountPanel #accounts>.account.is-selected{
 box-shadow:var(--oh-press);color:var(--oh-selected)
}
.oa-management.oa-native.oa-wechat-view #wechatAccountPicker #accounts .account-select{
 min-height:53px;padding:6px 3px 6px 9px;border-radius:12px;background:transparent;box-shadow:none
}
.oa-management.oa-native.oa-wechat-view #wechatAccountPicker #accounts .oa-account-menu summary{
 width:29px;height:44px;background:transparent;box-shadow:none
}
.oa-management.oa-native.oa-wechat-view #wechatAccountPicker #accounts .oa-account-copy>strong{font-size:13px}
.oa-management.oa-native.oa-wechat-view #wechatAccountPicker #accounts .status{white-space:normal}
.oa-native.oa-wechat-view #accounts .oa-account-id-tail{
 color:var(--oh-muted,var(--muted));font-size:10px;font-variant-numeric:tabular-nums;line-height:1.2
}
.oa-native.oa-wechat-view #accounts>.empty{grid-column:1/-1;margin:0}
.oa-native.oa-wechat-view #nativeWorkspace>.notice{margin:1px 0 5px;min-height:0}
.oa-native.oa-wechat-view #nativeWorkspace>.notice:empty{display:none}
.oa-native.oa-wechat-view #wechatOfficialAccount{
 min-height:0;overflow:auto;overscroll-behavior:contain;padding:4px 2px 10px
}
#wechatOfficialState{margin:0 0 12px;color:var(--oh-muted,var(--muted))}
#wechatOfficialFields{display:grid;grid-template-columns:minmax(max-content,112px) minmax(0,1fr);gap:8px 16px;margin:0}
#wechatOfficialFields dt{font-weight:650}
#wechatOfficialFields dd{margin:0;overflow-wrap:anywhere}
#wechatOfficialGraphic:not(:empty){margin-top:16px}
#wechatOfficialGraphic canvas{width:96px;height:96px;display:block}
#wxOpsReads input{min-height:36px}
#wxOpsCommentIndex{width:65px}
.oa-native.oa-wechat-view #settingsPanel:not([hidden]),
.oa-native.oa-wechat-view #wechatSettings:not([hidden]) {
 display:flex;flex-direction:column;flex:1;min-height:0;min-width:0;overflow:hidden
}
.oa-native.oa-wechat-view #settingsPanel[hidden],
.oa-native.oa-wechat-view #wechatSettings [hidden]{display:none!important}
.oa-native.oa-wechat-view #settingsPanel .oa-context-tabs {flex:none;gap:4px;margin:0 0 4px}
.oa-native.oa-wechat-view #wechatSettings > .oa-tabs {
 display:flex;flex:none;flex-wrap:wrap;gap:3px;padding:2px 2px 5px
}
.oa-native.oa-wechat-view #settingsPanel :is(.oa-context-tabs,.oa-tabs) > button {
 min-height:29px;padding:3px 7px;white-space:normal
}
.oa-native.oa-wechat-view #settingsPanel :is(#officialRoutes,#technicalPanel,#creativeTemplates,#projectContextPanel,#rulesCreator,#wechatPictures,#wxContentTools) {
 flex:1;min-height:0;min-width:0;overflow:auto;overscroll-behavior:contain;margin-top:0
}
body.oa-management.oa-native.oa-wechat-view:has(:is(#wechatPictures,#wxContentTools):not([hidden])) .oa-content {
 padding-block-end:calc(var(--wb-dock,64px) + 4px)
}
:is(#wechatPictures,#wxContentTools) :is(input,textarea,select){box-sizing:border-box;max-width:100%}
:is(#wechatPictures,#wxContentTools) .actions{display:flex;flex-wrap:wrap;gap:5px}
.oa-native.oa-wechat-view #wechatSettings > #productionRules {
 display:flex;flex-direction:column;min-height:0;padding:3px 4px;overflow:hidden
}
.oa-native.oa-wechat-view #rulesEditing {flex:1;min-height:0;height:auto}
.oa-native.oa-wechat-view #rulesWorkspace {height:100%;min-height:0}
.oa-native.oa-wechat-view #rulesWorkspace .oa-task-heading {flex:none}
@media(min-width:1000px) and (min-height:600px){
 .oa-native.oa-wechat-view #rulesWorkspace>.oa-task-summary{
  overflow:auto;overscroll-behavior:contain;scrollbar-width:thin;padding:6px 3px
 }
 .oa-native.oa-wechat-view #rulesWorkspace .oa-task-heading{margin-block:0 6px}
 .oa-native.oa-wechat-view #rulesWorkspace .oa-task-tools{margin-block-end:4px}
}
.oa-native.oa-wechat-view #rulesSheet {
 position:static;display:flex;flex-direction:column;max-height:100%;min-height:0;min-width:0;
 padding:10px 12px;overflow:hidden
}
.oa-native.oa-wechat-view #rulesSheet > *{min-width:0}
.oa-native.oa-wechat-view #rulesSheet .oa-task-sheet-head{margin:0 0 5px;gap:5px}
.oa-native.oa-wechat-view #rulesSheet .oa-task-sheet-head h2{font-size:17px;line-height:1.25}
.oa-native.oa-wechat-view #rulesSheetClose{min-height:28px;padding:2px 6px}
.oa-native.oa-wechat-view #rulesSheet .oa-task-fields {
 flex:1;overflow:auto;min-height:0;overscroll-behavior:contain;padding:3px
}
.oa-native.oa-wechat-view #rulesSheet .oa-task-actions {
 display:flex;flex:none;align-items:center;justify-content:space-between;gap:6px;flex-wrap:nowrap;
 padding:5px 0 0;margin:3px 0 0
}
.oa-native.oa-wechat-view #rulesStatus {
 min-width:0;max-height:38px;overflow:auto;margin:0;line-height:1.4
}
.oa-native.oa-wechat-view #rulesSave {white-space:nowrap;min-height:34px;padding:5px 10px}
.oa-native.oa-wechat-view #rulesCreator {padding-inline:3px}
.oa-native.oa-wechat-view #rulesWorkspace.oa-sheet-closed #rulesSheet {display:none}
@media(max-width:999px),(max-height:599px){
 .oa-native.oa-wechat-view #rulesWorkspace {display:flex;flex-direction:column;gap:4px}
 .oa-native.oa-wechat-view #rulesWorkspace > .oa-task-summary {flex:none;padding:0;opacity:1;pointer-events:auto}
 .oa-native.oa-wechat-view #rulesWorkspace .oa-task-heading {
  display:flex;align-items:center;gap:4px;min-height:0;margin:0
 }
 .oa-native.oa-wechat-view #rulesWorkspace .oa-task-heading h1 {font-size:15px;margin:0}
 .oa-native.oa-wechat-view #rulesWorkspace .oa-task-heading .help,
 .oa-native.oa-wechat-view #rulesWorkspace .oa-task-summary-bottom {display:none}
 .oa-native.oa-wechat-view #rulesWorkspace .oa-task-tools {margin:0 0 0 auto}
 .oa-native.oa-wechat-view #rulesSummary {
  display:flex;min-width:0;flex-wrap:nowrap;gap:4px;overflow:auto;padding:4px 2px;
  scrollbar-width:thin
 }
 .oa-native.oa-wechat-view #rulesSummary > button {width:auto;min-height:29px;flex:none;white-space:nowrap}
 .oa-native.oa-wechat-view #rulesSummary :is(small,.oa-task-row-edit){display:none}
 .oa-native.oa-wechat-view #rulesSheet {flex:1;min-height:0;box-shadow:none}
}
@media(max-width:560px){
 .oa-native.oa-wechat-view #wechatAccountPicker #accounts .avatar{width:19px;height:19px;flex-basis:19px}
}
@media(max-height:640px){
 body.oa-management.oa-native.oa-wechat-view #settingsPanel:not([hidden]){
  overflow:auto;overscroll-behavior:contain;scrollbar-width:thin;padding-inline:2px
 }
 .oa-native.oa-wechat-view #wechatSettings:not([hidden]){flex:none;overflow:visible}
 .oa-native.oa-wechat-view #wechatSettings>#productionRules{min-height:290px}
 .oa-native.oa-wechat-view #rulesWorkspace{min-height:278px}
}
@media(max-width:560px),(max-height:479px){
 .oa-native.oa-wechat-view #rulesSheet{padding:6px 8px}
 .oa-native.oa-wechat-view #rulesWorkspace > .oa-task-summary{display:flex;flex-direction:row;align-items:center;gap:4px}
 .oa-native.oa-wechat-view #rulesWorkspace .oa-task-heading{flex:none;order:1}
 .oa-native.oa-wechat-view #rulesWorkspace .oa-task-heading h1{display:none}
 .oa-native.oa-wechat-view #rulesWorkspace .oa-task-tools summary{white-space:nowrap}
 .oa-native.oa-wechat-view #rulesSummary{flex:1}
}
@media(min-width:900px){
 body.oa-management.oa-native.oa-wechat-view #nativeWorkspace:not([hidden]){
  --wx-account-column:clamp(158px,15vw,205px);--wx-workspace-gap:clamp(14px,2vw,26px);
  display:grid;column-gap:var(--wx-workspace-gap);
  grid-template:"accounts ." var(--wx-list-inset) "accounts missing" auto "accounts status" auto "accounts panel" minmax(0,1fr)/
   var(--wx-account-column) minmax(0,1fr)
 }
 body.oa-management.oa-native.oa-wechat-view #nativeWorkspace>:is(#settingsPanel,#wechatAnalytics,#wechatOfficialAccount,#wechatArticlesPage,#wechatAccountDesk){
  padding-block-start:0
 }
 .oa-native.oa-wechat-view #wechatAccountPicker{grid-area:accounts;display:flex;flex-direction:column;margin:0}
 .oa-native.oa-wechat-view #wechatAccountMissing{grid-area:missing}
 .oa-native.oa-wechat-view #notice{grid-area:status}
 .oa-native.oa-wechat-view :is(#wechatAnalytics,#settingsPanel,#wechatOfficialAccount,#wechatArticlesPage,#wechatAccountDesk){grid-area:panel}
 body.oa-management.oa-native.oa-wechat-view #wechatAccountPicker #accountPanel #accounts{
  grid-template-columns:minmax(0,1fr);max-height:none
 }
}
"""


# Manual task view fills the same account-panel slot as the existing overview.
from .wechat_position_editor import STYLE as POSITION_EDITOR_STYLE

STYLE += POSITION_EDITOR_STYLE + r'''
.wx-manual-index{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:10px;max-width:900px;padding:4px 3px 10px}
.wx-manual-index>button{display:grid;gap:3px;text-align:start;justify-content:start;min-height:58px;white-space:normal}
.wx-manual-index>button span{color:var(--muted);font-size:12px;font-weight:400}
.wx-manual-index .wx-manual-more{grid-column:1/-1;margin:0;padding:6px 0}
.wx-manual-more>div{display:flex;flex-wrap:wrap;gap:8px;margin:8px 0}
.wx-manual-more summary{cursor:pointer;font-weight:600}
#wechatManualToolbar{flex:none;margin:0 0 8px}
#wechatSetupAdvanced>.oa-tabs[hidden]{display:none!important}
#wechatSettings[data-manual-task] #wechatSetupHome,
#wechatSettings[data-manual-task] #wechatSetupAdvanced>summary,
#wechatSettings[data-manual-task] #rulesWorkspace>.oa-task-summary{display:none!important}
.oa-native.oa-wechat-view #settingsPanel #wechatSettings[data-manual-task]:not([hidden]){
 flex:1;min-height:0;overflow:hidden
}
.oa-native.oa-wechat-view #wechatSettings[data-manual-task] #wechatSetupAdvanced[open]{
 flex:1;min-height:0;display:flex;flex-direction:column;margin:0;overflow:hidden;
}
.oa-native.oa-wechat-view #settingsPanel #wechatSettings[data-manual-task] #productionRules:not([hidden]){
 display:flex;flex:1;min-height:0;min-width:0;flex-direction:column;overflow:hidden;margin:0;padding:2px 3px
}
.oa-native.oa-wechat-view #wechatSettings[data-manual-task] #rulesWorkspace{
 display:flex;flex-direction:column;min-height:0
}
.oa-native.oa-wechat-view #wechatSettings[data-manual-task] #rulesSheet{
 flex:1;min-height:0;max-width:none;width:100%;box-sizing:border-box
}
.oa-native.oa-wechat-view #wechatSettings[data-manual-task] #rulesEditing:not([hidden]){
 display:flex;flex:1;min-height:0
}
#wechatSettings[data-manual-task="position"] #rulesStarter,
#wechatSettings[data-manual-task="position"] #rulesSheetClose,
#wechatSettings:not([data-manual-task="position"]) #rulesPositionCancel{display:none!important}
#wechatSettings[data-manual-task="position"] #rulesSheet .oa-task-actions{justify-content:flex-end}
#wechatSettings[data-manual-task="position"] #rulesStatus{margin-inline-end:auto}
#wechatSettings[data-manual-task="position"] #rulesStatus[data-scope-status]{display:none}
#wechatSettings[data-manual-task="position"] .rules-body{max-width:850px}
#wechatSettings[data-manual-task="position"] .rules-body,
#wechatSettings[data-manual-task="position"] #rulesPositionEditor{min-width:0}
#wechatSettings[data-manual-task="position"] #rulesSheet .wx-position-actions :is(button,select){
 min-width:0;width:auto;min-height:36px;font-size:13px;font-weight:500;line-height:1.3
}
#wechatSettings[data-manual-task="position"] .wx-position-scope details{grid-column:1/-1}
@media(max-width:560px){
 .wx-manual-index{grid-template-columns:1fr;gap:7px}
 body.oa-management.oa-native.oa-wechat-view:has(#wechatSettings[data-manual-task="position"])
  #wechatAccountPicker #accountPanel #accounts{grid-template-columns:repeat(2,minmax(0,1fr))}
 #wechatSettings[data-manual-task="position"] #rulesSheet .oa-task-actions{flex-wrap:wrap}
 #wechatSettings[data-manual-task="position"] #rulesStatus{width:100%;margin-block:0;max-height:none}
 #wechatSettings[data-manual-task="position"] #rulesSheetTitle{font-size:16px}
 #wechatSettings[data-manual-task="position"] .wx-position-actions{gap:4px}
 #wechatSettings[data-manual-task="position"] .wx-position-actions button{padding-inline:6px}
}
'''
