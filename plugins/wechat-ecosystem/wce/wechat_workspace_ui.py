"""Viewport layout for the native WeChat workspace."""
STYLE = """
html:has(body.oa-wechat-view),body.oa-wechat-view{overflow:hidden}
body.oa-management.oa-native.oa-wechat-view .oa-shell {
 display:grid;height:100dvh;min-height:0;grid-template-rows:minmax(0,1fr);overflow:hidden
}
body.oa-management.oa-native.oa-wechat-view .oa-sidebar {
 min-width:0;min-height:0;overflow:auto;overscroll-behavior:contain
}
body.oa-management.oa-native.oa-wechat-view .oa-content {
 height:100%;min-height:0;min-width:0;overflow:hidden;padding:12px 16px 8px
}
.oa-native.oa-wechat-view #nativeWorkspace:not([hidden]) {
 display:flex;flex-direction:column;height:100%;min-height:0;min-width:0;overflow:hidden
}
.oa-native.oa-wechat-view #nativeWorkspace > .oa-footer{display:none}
.oa-management.oa-native.oa-wechat-view .oa-account-header {
 grid-template-columns:minmax(0,1fr) auto;gap:6px 12px;margin:0 0 6px
}
.oa-management.oa-native.oa-wechat-view .oa-account-header > .oa-heading h1 {
 margin:0;font-size:20px;line-height:1.2
}
.oa-management.oa-native.oa-wechat-view .oa-account-header > .actions {
 gap:4px
}
.oa-management.oa-native.oa-wechat-view .oa-account-header > .actions > button {
 min-height:32px;padding:5px 8px
}
.oa-native.oa-wechat-view #wechatWorkspaceNavigation:not([hidden]) {
 display:flex;flex:none;gap:4px;padding:2px 2px 5px;margin-bottom:6px;border-bottom:1px solid var(--line)
}
.oa-native.oa-wechat-view #wechatWorkspaceNavigation button {
 min-height:32px;padding:5px 10px;font-size:13px;color:var(--muted)
}
.oa-native.oa-wechat-view #wechatWorkspaceNavigation button[aria-pressed=true] {
 background:var(--oa-selection);color:var(--oa-selected-ink);font-weight:650
}
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
 body.oa-management.oa-native.oa-wechat-view .oa-shell {
  grid-template-columns:minmax(0,1fr);grid-template-rows:auto minmax(0,1fr)
 }
 body.oa-management.oa-native.oa-wechat-view .oa-sidebar {
  padding:4px 9px;gap:2px 5px;grid-template-columns:minmax(0,1fr) auto;align-content:start
 }
 body.oa-management.oa-native.oa-wechat-view .oa-content {padding:6px 9px 4px}
 .oa-management.oa-native.oa-wechat-view .oa-account-header{gap:3px 5px}
}
@media(max-width:560px),(max-height:479px){
 .oa-native.oa-wechat-view #rulesSheet{padding:6px 8px}
 .oa-native.oa-wechat-view #rulesWorkspace > .oa-task-summary{display:flex;flex-direction:row;align-items:center;gap:4px}
 .oa-native.oa-wechat-view #rulesWorkspace .oa-task-heading{flex:none;order:1}
 .oa-native.oa-wechat-view #rulesWorkspace .oa-task-heading h1{display:none}
 .oa-native.oa-wechat-view #rulesWorkspace .oa-task-tools summary{white-space:nowrap}
 .oa-native.oa-wechat-view #rulesSummary{flex:1}
}
"""
