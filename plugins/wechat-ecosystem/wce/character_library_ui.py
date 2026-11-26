"""Character reference browser and exact-version storyboard picker."""

from .character_ruler_ui import SCRIPT as RULER_SCRIPT, STYLE as RULER_STYLE
from .character_set_trial_ui import SCRIPT as SET_TRIAL_SCRIPT, STYLE as SET_TRIAL_STYLE

PAGE = '<section id="characterLibrary" aria-label="形象资产库" hidden></section>'

HTML = r'''
<dialog id="characterPicker" aria-label="从形象库选择"><div class="cl-picker-head"><strong>从形象库选择</strong><button type="button" id="clPickerClose">关闭</button></div><section id="clPickerLibrary" aria-label="镜头参考图库"></section></dialog>
<dialog id="characterDetail" aria-labelledby="clDetailTitle"><div id="clDetailContent"></div></dialog>
<dialog id="characterImport" aria-labelledby="clImportTitle"><div id="clImportFields" class="cl-form">
 <div class="cl-dialog-head"><h2 id="clImportTitle">导入形象索引</h2><button type="button" id="clImportClose">关闭</button></div>
 <label>所属项目<select id="clImportProject" required></select></label>
 <div class="cl-actions"><button type="button" id="clImportBrowse">从项目目录选择</button><output id="clImportChosen"></output></div>
 <section id="clImportBrowser" aria-label="项目目录" hidden></section>
 <details><summary>手动指定索引文件和路径</summary>
  <label>项目内的索引文件<input id="clImportFile" type="file" accept=".json,application/json" required></label>
  <label>索引的项目相对路径<input id="clImportPath" required placeholder="例如 references/characters.json"></label>
  <button type="button" id="clImportReview">预览导入</button>
 </details>
 <div class="cl-actions"><button type="button" id="clImportApply" class="primary" disabled>登记索引</button></div>
 <p role="status" id="clImportStatus"></p><ul id="clImportRows"></ul>
</div></dialog>
'''

STYLE = RULER_STYLE + r'''
#characterLibrary,#characterPicker,#characterDetail,#characterImport{
 --cl-bg:var(--bg);--cl-card:var(--surface);--cl-frame:var(--soft);--cl-line:var(--line);
 --cl-accent:var(--accent);--cl-tint:var(--oa-selection,var(--tint));
 --cl-green:light-dark(#27694d,#a6d9c2);--cl-green-bg:light-dark(#e2f3e9,#263c33);
 --cl-gray:var(--muted);--cl-gray-bg:var(--soft)
}
#characterLibrary{min-height:0;flex:1;overflow:hidden}
#characterLibrary .cl-header h1{display:none}
#characterLibrary .cl-header{justify-content:flex-end}
#characterLibrary .cl-card .cl-card-placeholder{display:grid;place-items:center;align-content:center;
 gap:5px;padding:8px;text-align:center;color:var(--cl-gray);background:var(--cl-gray-bg)}
#characterLibrary .cl-card-placeholder svg{width:36px;height:36px;color:inherit;
 --cl-ring-ink:light-dark(#767676,#aeaeae);--cl-ring-fill:light-dark(#e4e4e4,#404040);
 --cl-ring-shadow:light-dark(#bcbcbc,#777)}
#clImportChosen,#clImportBrowser{overflow-wrap:anywhere}
#clImportBrowser{border:1px solid var(--cl-line);border-radius:8px;padding:8px;max-height:210px;overflow:auto}
#clImportBrowser button{display:block;max-width:100%;margin-top:4px;text-align:start}
#clImportBrowser .cl-directory::before{content:'› ';font-weight:650}
.cl-layout{display:grid;grid-template-columns:151px minmax(0,1fr);grid-template-rows:minmax(0,1fr);
 box-sizing:border-box;height:100%;min-width:0;
 background:var(--cl-bg);border:1px solid var(--cl-line);border-radius:14px;color:var(--ink)}
.cl-projects{display:flex;flex-direction:column;align-items:stretch;gap:5px;padding:16px 10px;
 border-right:1px solid var(--cl-line);min-height:0;overflow:auto;overscroll-behavior:contain}
:is(#videoDirectorDesk,#characterPicker) .cl-projects button{display:grid;grid-template-columns:minmax(0,1fr) auto;
 align-items:center;flex-shrink:0;min-width:0;max-width:100%;gap:6px;text-align:start}
.cl-project-label{min-width:0;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.cl-project-count{font-variant-numeric:tabular-nums;white-space:nowrap;color:var(--muted)}
.cl-projects button[aria-pressed=true],.cl-filters button[aria-pressed=true]{background:var(--cl-tint);color:var(--cl-accent)}
.cl-main{min-width:0;min-height:0;padding:clamp(13px,2vw,29px);overflow:auto;
 overscroll-behavior:contain;scrollbar-gutter:stable}
.cl-header{display:flex;justify-content:space-between;align-items:start;gap:12px;flex-wrap:wrap}
.cl-header h1{margin:0;font-size:15px;font-weight:650;line-height:1.35}
.cl-controls,.cl-actions,.cl-filters{display:flex;align-items:center;flex-wrap:wrap;gap:6px}
:is(#videoDirectorDesk,#characterPicker) .cl-controls input[type=search]{margin:0;width:clamp(175px,19vw,255px)}
.cl-filters{margin:16px 0 8px}
:is(#videoDirectorDesk,#characterPicker) .cl-series-filter{
 display:grid;grid-template-columns:auto minmax(0,1fr);align-items:center;gap:6px;
 width:min(100%,235px);margin:0;color:var(--muted);font-size:12px
}
.cl-series-filter select{width:100%;min-width:0;text-overflow:ellipsis}
.cl-count{margin:0 0 12px;color:var(--muted)}
.cl-grid{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:12px}
.oa-native :is(#characterLibrary,#characterPicker) .cl-card{
 display:grid;grid-template-rows:auto 1fr;align-content:stretch;align-items:start;justify-items:stretch;width:100%;
 min-width:0;padding:0;border:1px solid var(--cl-line);
 border-radius:10px;background:var(--cl-card);box-shadow:none;overflow:hidden;text-align:start;font:inherit;color:inherit}
.oa-native :is(#characterLibrary,#characterPicker) .cl-card:is(:hover,:focus-visible){border-color:var(--cl-accent);background:var(--cl-card)}
.cl-picture{display:grid;place-items:center;width:100%;aspect-ratio:1.24;overflow:hidden;background:var(--cl-frame);
 color:var(--cl-gray);font-size:12px;white-space:normal;text-align:center}
.cl-picture img{display:block;width:100%;height:100%;object-fit:contain;min-height:0}
.cl-voice-cover{align-content:center;gap:6px}
.cl-voice-cover strong{font-size:25px;line-height:1;color:var(--cl-accent)}
.cl-detail .cl-picture.cl-voice-preview{min-height:82px;padding:10px;box-sizing:border-box}
.cl-voice-preview audio{width:100%;max-width:480px}
.cl-card-copy{display:grid;align-content:start;gap:5px;padding:10px 11px;min-width:0;white-space:normal}
.cl-card[aria-pressed=true]{outline:2px solid var(--cl-accent);outline-offset:-2px}
.cl-card-copy strong{font-size:16px;line-height:1.2;overflow-wrap:anywhere}
.cl-card-meta{display:flex;align-items:center;flex-wrap:wrap;gap:5px;color:var(--muted);font-size:12px}
.cl-badge{border-radius:5px;background:var(--cl-gray-bg);color:var(--cl-gray);padding:2px 6px;font-size:11px}
.cl-badge[data-status=current]{background:var(--cl-green-bg);color:var(--cl-green)}
.cl-badge[data-status=candidate]{background:var(--cl-tint);color:var(--cl-accent)}
.cl-subtitle,.cl-detail-fields dd{color:var(--muted);overflow-wrap:anywhere;font-size:12px}
#characterPicker,#characterDetail,#characterImport{background:var(--cl-card);color:var(--ink);border:1px solid var(--cl-line);
 border-radius:14px;max-height:92dvh;padding:0;overflow:auto}
#characterPicker{width:min(1180px,96vw)}
#characterDetail{width:min(940px,94vw)}
#characterImport{width:min(520px,94vw)}
#characterPicker::backdrop,#characterDetail::backdrop,#characterImport::backdrop{background:#110c08a0}
#characterPicker .cl-layout{height:min(76dvh,780px);border-radius:0;border:0}
.cl-picker-head,.cl-dialog-head{display:flex;align-items:center;justify-content:space-between;gap:8px}
.cl-picker-head,.cl-detail{padding:14px}
.cl-dialog-head h2{margin:0;font-size:20px;overflow-wrap:anywhere}
.cl-person-caption{display:block;margin-top:4px;color:var(--muted);font-size:12px;overflow-wrap:anywhere}
.cl-forms{display:flex;align-items:center;flex-wrap:wrap;gap:6px;margin:12px 0 0}
.cl-forms button[aria-pressed=true],.cl-asset-choice[aria-pressed=true]{
 background:var(--cl-tint);color:var(--cl-accent)
}
.cl-detail-layout{display:grid;grid-template-columns:minmax(165px,27%) minmax(0,1fr);gap:14px;
 margin-top:12px;align-items:start}
.cl-asset-lists{display:grid;gap:12px;min-width:0;max-height:61dvh;overflow:auto;overscroll-behavior:contain;padding:2px}
.cl-asset-group,.cl-original{display:grid;gap:5px;min-width:0}
.cl-asset-group h3{font-size:12px;margin:0;color:var(--ink)}
.cl-asset-group p,.cl-original p{margin:0}
.cl-asset-list{display:grid;gap:4px;min-width:0}
#characterDetail .cl-asset-choice{display:grid;gap:3px;justify-items:stretch;text-align:start;
  min-width:0;width:100%;white-space:normal}
.cl-asset-label{font-weight:600;line-height:1.3;overflow-wrap:anywhere}
.cl-asset-meta{display:flex;align-items:center;flex-wrap:wrap;gap:4px;line-height:1.3;font-size:11px}
.cl-detail .cl-picture{aspect-ratio:auto;min-height:120px;margin:0;border-radius:8px}
.cl-detail .cl-picture img{max-height:48dvh;width:100%;height:auto}
.cl-shared-note{margin:6px 0 0;color:var(--muted);font-size:12px}
@media(max-width:600px){
 .cl-detail-layout{grid-template-columns:minmax(0,1fr);gap:10px}
 .cl-asset-lists{grid-template-columns:repeat(auto-fit,minmax(min(100%,125px),1fr));max-height:30dvh}
 .cl-detail .cl-picture img{max-height:36dvh}
}
.cl-detail-fields{display:grid;grid-template-columns:auto minmax(0,1fr);gap:4px 12px;margin:12px 0}
.cl-detail-fields dd{margin:0}
.cl-form{display:grid;gap:8px;padding:16px}
.cl-form p,.cl-form ul{margin:0;overflow-wrap:anywhere}
.cl-form ul{padding-left:18px}
@media(max-width:1269px){.cl-grid{grid-template-columns:repeat(3,minmax(0,1fr))}}
@media(max-width:880px){.cl-layout{grid-template-columns:minmax(0,1fr);grid-template-rows:auto minmax(0,1fr)}
 .cl-projects{flex-direction:row;flex-wrap:wrap;align-content:start;max-height:min(30dvh,180px);
  border-right:0;border-bottom:1px solid var(--cl-line);padding:8px}
}
@media(max-width:635px){
 .cl-header,.cl-controls{width:100%}
 .cl-controls{display:grid;grid-template-columns:minmax(0,1fr) auto auto}
 :is(#videoDirectorDesk,#characterPicker) .cl-controls input[type=search]{width:100%;min-width:0}
 .cl-grid{grid-template-columns:repeat(2,minmax(0,1fr));gap:8px}
 .cl-main{padding:12px}
 .cl-layout button{min-height:32px}
 .cl-card-copy{padding:8px}
 .cl-projects button{min-height:35px}
}
@media(max-width:799px){
 .oa-native.oa-character-view .oa-sidebar{
  display:grid;grid-template-columns:minmax(0,1fr) auto;gap:3px;padding:7px 10px
 }
 .oa-native.oa-character-view .oa-sidebar .oa-brand{min-height:28px;display:flex;gap:6px}
 .oa-native.oa-character-view .oa-sidebar #wechatCompactUpdates{grid-area:1/2}
 .oa-native.oa-character-view .oa-sidebar #softwareUpdateSlot:empty{display:none}
 .oa-native.oa-character-view .oa-sidebar > div:has(#platformNavigation){
  display:flex;gap:4px;grid-area:2/1/3/-1;overflow-x:auto;scrollbar-width:thin
 }
 .oa-native.oa-character-view .oa-sidebar .oa-nav{margin:0;flex:none;flex-wrap:nowrap}
 .oa-native.oa-character-view .oa-sidebar .oa-nav button{min-height:34px;padding:4px 7px}

}
.cl-layout.cl-roster{display:flex;border:0;background:transparent}
.cl-roster>.cl-main{width:100%;padding:6px 1px 12px}
#characterLibrary .cl-roster .cl-header{justify-content:flex-start}
.cl-roster .cl-controls{width:100%;justify-content:flex-start;gap:8px}
.cl-roster .cl-controls select{min-width:105px;width:min(25%,225px);margin:0}
.cl-roster .cl-controls input[type=search]{width:min(56%,325px);flex:0 1 auto}
.cl-roster-tools{position:relative;font-size:12px}
.cl-roster-tools>.cl-actions{position:absolute;z-index:2;top:100%;right:0;width:max-content;padding:7px;
 background:var(--cl-card);border:1px solid var(--cl-line);border-radius:8px}
.cl-roster .cl-count{margin:10px 0 8px;font-size:12px}
.cl-roster .cl-grid{grid-template-columns:repeat(auto-fill,minmax(min(100%,143px),1fr));gap:10px}
.cl-roster .cl-card{max-width:225px}
.cl-roster .cl-card-copy{padding:8px 9px}
.cl-roster .cl-card-copy strong{font-size:14px}
.cl-roster .cl-picture{aspect-ratio:1.18}
.cl-roster .cl-picture img{object-fit:cover;object-position:center 34%}
#characterDetail:has(.cl-gear){width:100vw;height:100dvh;max-width:none;max-height:none;margin:0;padding:0;
 border:0;border-radius:0;overflow:hidden;box-sizing:border-box;background:var(--cl-bg)}
.cl-gear{--cl-side:clamp(65px,11vw,145px);box-sizing:border-box;width:100%;height:100%;min-height:0;padding:12px clamp(10px,3vw,44px) 9px;
 display:grid;grid-template-rows:auto auto minmax(0,1fr);gap:8px;position:relative;
 background:radial-gradient(ellipse at 50% 45%,light-dark(#fdfcff,#2c2932) 0,transparent 66%),var(--cl-bg)}
.cl-gear-header{display:grid;grid-template-columns:minmax(0,1fr) auto minmax(0,1fr);align-items:center;gap:8px;min-height:38px}
.cl-gear-header>button{justify-self:start}
.cl-gear-header>h2{margin:0;text-overflow:ellipsis;overflow:hidden;white-space:nowrap;font-size:15px;font-weight:650}
.cl-gear-header .cl-forms{justify-self:end;margin:0;justify-content:flex-end}
.cl-top-slots{min-height:0;display:flex;justify-content:safe center;gap:6px;overflow-x:auto;padding:2px;scrollbar-width:thin}
.cl-top-slots:empty{display:none}
.cl-gear-body{display:grid;grid-template-columns:var(--cl-side) minmax(0,1fr) var(--cl-side);gap:clamp(7px,3vw,50px);
 min-height:0;margin-inline:auto;width:min(100%,1100px)}
.cl-side-slots{display:grid;align-content:center;gap:10px;min-height:0;overflow:auto;padding:2px;
 overscroll-behavior:contain;scrollbar-width:thin}
#characterDetail .cl-slot{display:grid;grid-template-rows:auto auto auto;justify-items:center;place-self:start center;
 align-items:center;min-width:0;text-align:center;gap:3px;white-space:normal;padding:4px;width:min(100%,98px);
 border:1px solid var(--cl-line);border-radius:9px;background:var(--cl-card);box-shadow:none}
#characterDetail .cl-top-slots .cl-slot{flex:0 0 68px;width:68px}
#characterDetail .cl-slot[aria-expanded=true]{border-color:var(--cl-accent);background:var(--cl-tint)}
#characterDetail .cl-slot .cl-slot-art{width:100%;aspect-ratio:1;min-height:0;height:auto;border-radius:5px;margin:0;
 background:var(--cl-frame);overflow:hidden;display:grid;place-items:center}
#characterDetail .cl-slot-art img,#characterDetail .cl-option-thumb img{width:100%;height:100%;object-fit:cover;min-height:0;max-height:none}
.cl-slot-label{font-size:11px;font-weight:600;line-height:1.15}
.cl-equipped-name{max-width:100%;font-size:10px;line-height:1.1;color:var(--cl-gray);overflow-wrap:anywhere}
.cl-equipped-name:empty{display:none}
.cl-gear-middle{display:grid;grid-template-rows:minmax(0,1fr) auto;min-height:0;min-width:0}
.cl-gear-stage{position:relative;min-height:0;min-width:0}
.cl-gear-stage:has(.cl-turntable:not([hidden])[data-feature=""]):after{content:'';position:absolute;left:50%;bottom:6%;
 width:25%;height:8%;background:radial-gradient(ellipse closest-side,#332a6333,transparent);
 transform:translateX(-50%);pointer-events:none;z-index:0}
.cl-turntable{z-index:1}.cl-stage-actions,.cl-stage-legend{z-index:2}
.cl-turntable,.cl-stage-photo{display:block;width:100%;height:100%;position:absolute;inset:0;min-width:0;min-height:0}
.cl-turntable{touch-action:pan-y;cursor:grab;outline-offset:-3px}
.cl-turntable.cl-dragging{cursor:grabbing}
.cl-stage-photo{display:grid;place-items:center;overflow:hidden}
.cl-gear-stage [hidden],.cl-equipment-drawer[hidden]{display:none!important}
.cl-stage-photo img{width:auto;height:94%;max-width:100%;object-fit:contain}
.cl-stage-legend{position:absolute;bottom:2px;left:50%;transform:translateX(-50%);text-align:center;pointer-events:none;
 color:var(--cl-gray);font-size:11px;max-width:100%}
.cl-stage-actions{position:absolute;top:6px;right:4px;display:flex;gap:5px;justify-content:flex-end;flex-wrap:wrap;
 pointer-events:none}
.cl-stage-actions button{pointer-events:auto}
.cl-closeup-tools{display:flex;gap:4px}
.cl-person-profile{text-align:center;padding:8px 3px 3px;line-height:1.35}
.cl-person-profile>strong{font-size:18px}
.cl-person-profile dl{display:flex;align-items:baseline;justify-content:center;flex-wrap:wrap;gap:3px 6px;margin:4px 0 0}
.cl-person-profile dt{color:var(--cl-gray);font-size:11px}
.cl-person-profile dd{font-size:12px;margin:0 6px 0 0}
.cl-equipment-drawer{position:absolute;z-index:2;right:clamp(8px,3vw,38px);width:min(540px,55vw);top:clamp(112px,21dvh,190px);bottom:64px;
 display:grid;grid-template-rows:auto minmax(0,1fr);gap:5px;padding:10px;background:var(--cl-card);
 border:1px solid var(--cl-line);border-radius:12px;box-shadow:0 8px 30px #1a15241a}
.cl-equipment-drawer h3,.cl-equipment-drawer h4{margin:0;font-size:14px}
.cl-equipment-drawer h4{font-size:12px}
.cl-drawer-panes{display:grid;grid-template-columns:minmax(128px,43%) minmax(0,1fr);gap:8px;min-height:0}
.cl-equipment-drawer .cl-asset-lists,.cl-equipment-drawer .cl-original{overflow:auto;max-height:none;
 min-height:0;min-width:0;align-content:start;overscroll-behavior:contain;padding:2px;scrollbar-gutter:stable}
.cl-equipment-drawer .cl-asset-lists{grid-template-columns:minmax(0,1fr);gap:4px}
#characterDetail .cl-equipment-drawer .cl-asset-choice{display:grid;grid-template-columns:32px minmax(0,1fr);gap:3px 6px;
 align-items:center;justify-items:start;white-space:normal;padding:4px;text-align:start;border-radius:6px;border:1px solid transparent}
#characterDetail .cl-equipment-drawer .cl-asset-choice[aria-pressed=true]{border-color:var(--cl-accent)}
.cl-option-thumb{width:32px;height:32px;display:grid;grid-row:span 2;place-items:center;overflow:hidden;background:var(--cl-frame);border-radius:4px}
.cl-equipment-drawer .cl-asset-label{font-size:11px}
.cl-inspector-preview{display:grid;place-items:center;aspect-ratio:1.42;max-height:25dvh;overflow:hidden;
 background:var(--cl-frame);border-radius:7px}
.cl-inspector-preview img{display:block;max-width:100%;max-height:25dvh;object-fit:contain}
.cl-inspector-preview audio{width:100%;height:35px}
.cl-equipment-drawer .cl-detail-fields{margin:4px 0;gap:3px 8px;font-size:11px}
.cl-equipment-drawer .cl-detail-fields dd{font-size:11px}
.cl-equipment-drawer .cl-actions button{min-height:28px;font-size:11px}
@media(max-width:650px){
 .cl-roster .cl-controls{display:flex}.cl-roster .cl-controls input[type=search]{flex:1 1 130px}
 .cl-roster .cl-grid{grid-template-columns:repeat(2,minmax(0,1fr))}
 .cl-gear{--cl-side:63px;gap:5px;padding:7px 7px 8px}
 .cl-gear-header h2{font-size:13px}
 .cl-gear-header button,.cl-stage-actions button{font-size:10px;padding:3px 6px;min-height:26px}
 .cl-top-slots{justify-content:safe center}
 #characterDetail .cl-top-slots .cl-slot{flex-basis:47px;width:47px;padding:3px}
 #characterDetail .cl-slot-label{font-size:9px}
 .cl-side-slots{gap:6px}
 .cl-gear-body{gap:3px}
 .cl-person-profile>strong{font-size:15px}
 .cl-stage-legend{font-size:10px}
 .cl-equipment-drawer{left:7px;right:7px;top:auto;bottom:8px;width:auto;height:min(46dvh,370px);
   box-sizing:border-box;padding:7px}
 .cl-drawer-panes{grid-template-columns:minmax(112px,43%) minmax(0,1fr)}
 .cl-inspector-preview,.cl-inspector-preview img{max-height:19dvh}
}

#characterDetail:has(.cl-browse){
 width:min(1210px,calc(100vw - 32px));height:min(845px,calc(100dvh - 30px));max-width:none;max-height:none;
 padding:0;overflow:hidden;background:var(--cl-bg);border:1px solid var(--cl-line);border-radius:15px
}
.cl-browse{position:relative;height:100%;box-sizing:border-box;display:grid;grid-template-rows:auto minmax(0,1fr);
 padding:12px 16px;gap:10px;min-width:0;min-height:0;color:var(--ink)}
.cl-browse-layout{display:grid;grid-template-columns:minmax(0,1fr) minmax(330px,37%);gap:24px;min-height:0;min-width:0}
.cl-browse-visual{position:relative;display:grid;grid-template-rows:auto minmax(0,1fr);gap:7px;min-width:0;min-height:0}
.cl-browse-header{display:grid;grid-template-columns:minmax(0,1fr) auto;align-items:center;gap:8px}
.cl-browse-header>button{justify-self:start}
#characterDetail .cl-browse-revision{display:flex;align-items:center;gap:6px;min-width:0;margin:0;white-space:nowrap}
#characterDetail .cl-browse-revision select{width:auto;max-width:100%;min-width:0;min-height:30px;padding:4px 6px;font-size:13px}
.cl-browse-header .cl-forms{justify-self:end;margin:0;justify-content:flex-end}
.cl-browse-identity{display:flex;align-items:center;min-width:0;gap:10px}
#characterDetail .cl-browse-identity .cl-picture{width:42px;height:42px;min-height:0;flex:none;border-radius:9px}
.cl-browse-identity .cl-picture img{object-fit:cover}
.cl-browse-identity h2{font-size:19px;margin:0;overflow-wrap:anywhere}
.cl-browse-identity small{display:block;color:var(--cl-gray);font-size:12px;overflow-wrap:anywhere}
.cl-browse-tools,.cl-browse-categories{display:flex;align-items:center;flex-wrap:wrap;gap:4px;min-width:0}
#characterDetail .cl-browse-categories button{
 font-size:15px;font-weight:500;padding:4px 8px;min-height:30px;white-space:nowrap;flex-shrink:0;
 color:light-dark(#34303b,#f0edf4);background:light-dark(#f4f1f6,#292733);box-shadow:none
}
#characterDetail .cl-browse-categories button[aria-pressed=true]{
 background:light-dark(#e9def4,#493a59);color:light-dark(#432565,#faf3ff);
 box-shadow:inset 0 0 0 1px light-dark(#9674b9,#b59bcd)
}
 .cl-browse-info[hidden],.cl-browse-controls button[hidden],
 .cl-ring-edge[hidden]{display:none!important}
.cl-browse-body{display:grid;grid-template-rows:minmax(0,1fr) 91px;gap:7px;min-height:0;min-width:0}
.cl-browse-arena{container-type:size;display:grid;place-items:center start;min-width:0;min-height:0}
.cl-browse-ring{
 --cl-ring-gap:6px;--cl-tile-gap:3px;
 --cl-ring-capacity:10;
 --cl-ring-span:min(100cqw,100cqh);
 --cl-ring-slot:clamp(22px,calc((var(--cl-ring-span) - 2 * var(--cl-ring-gap) - (var(--cl-ring-capacity) - 1) * var(--cl-tile-gap))/(var(--cl-ring-capacity) + 2)),46px);
 --cl-ring-side:max(0px,calc(var(--cl-ring-span) - 2 * (var(--cl-ring-slot) + var(--cl-ring-gap))));
 display:grid;grid-template-columns:var(--cl-ring-slot) var(--cl-ring-side) var(--cl-ring-slot);
 grid-template-rows:var(--cl-ring-slot) var(--cl-ring-side) var(--cl-ring-slot);
 grid-template-areas:". north ." "west stage east" ". south .";gap:var(--cl-ring-gap)
}
.cl-ring-edge{display:flex;align-items:center;justify-content:space-between;gap:var(--cl-tile-gap);
 min-width:0;min-height:0;scrollbar-width:none;overscroll-behavior:contain}
.cl-ring-north{grid-area:north;overflow-x:auto}
.cl-ring-south{grid-area:south;flex-direction:row-reverse;overflow-x:auto}
.cl-ring-east{grid-area:east;flex-direction:column;overflow-y:auto}
.cl-ring-west{grid-area:west;flex-direction:column-reverse;overflow-y:auto}
#characterDetail .cl-browse-tile{
 display:grid;place-items:center;box-sizing:border-box;
 width:var(--cl-ring-slot);height:var(--cl-ring-slot);min-height:0;flex:none;padding:0;
 border:1px solid var(--cl-line);border-radius:9px;background:var(--cl-card);box-shadow:none
}
#characterDetail .cl-browse-tile[aria-pressed=true]{
 background:var(--cl-tint);border-color:var(--cl-accent);color:var(--cl-accent)
}
#characterDetail .cl-browse-tile:focus-visible{outline:2px solid var(--cl-accent);outline-offset:-2px}
#characterDetail .cl-browse-tile:disabled{opacity:.45;cursor:default}
#characterDetail .cl-full-look:not(:disabled):not([aria-pressed=true]){
 color:var(--cl-accent);border-color:color-mix(in srgb,var(--cl-accent) 45%,var(--cl-line))
}
.cl-ring-symbol{
 display:block;width:calc(var(--cl-ring-slot)*.84);aspect-ratio:1;pointer-events:none;
 --cl-ring-ink:light-dark(#503751,#eeddf0);
 --cl-ring-fill:light-dark(#efdfeb,#61465e);
 --cl-ring-shadow:light-dark(#bb87a3,#a981a5);
}
.cl-ring-base,.cl-ring-shade{fill-rule:evenodd}
.cl-ring-base{fill:var(--cl-ring-fill)}
.cl-ring-shade{fill:var(--cl-ring-shadow)}
.cl-ring-ink,.cl-ring-detail{
 fill:none;stroke:var(--cl-ring-ink);stroke-linecap:round;stroke-linejoin:round
}
.cl-ring-ink{stroke-width:1.25}
.cl-ring-detail{stroke-width:1.04}
#characterDetail .cl-browse-tile:is([aria-pressed=true],[aria-expanded=true]) .cl-ring-symbol{
 --cl-ring-fill:light-dark(#fdf3fb,#684e75);
 --cl-ring-shadow:light-dark(#be86b5,#c198ce)
}
#characterDetail .cl-browse-tile[data-located=true]{box-shadow:inset 0 0 0 1px var(--cl-accent)}
#characterDetail .cl-browse-tile[data-missing=true]{
 background:var(--cl-card);border-color:var(--cl-line);cursor:default
}
#characterDetail .cl-browse-tile[data-missing=true] .cl-ring-symbol{
 --cl-ring-ink:light-dark(#767676,#aeaeae);
 --cl-ring-fill:light-dark(#e4e4e4,#404040);
 --cl-ring-shadow:light-dark(#bcbcbc,#777)
}
#characterDetail .cl-browse-tile[data-missing=true][data-located=true]{
 box-shadow:inset 0 0 0 1px light-dark(#767676,#aeaeae)
}
.cl-ring-tooltip{position:fixed;z-index:3;pointer-events:none;max-width:min(210px,calc(100vw - 16px));
 padding:4px 8px;border-radius:6px;background:light-dark(#282534,#f0ecf4);color:light-dark(#fff,#252334);
 font-size:11px;line-height:1.35;text-align:center;overflow-wrap:anywhere;box-shadow:0 2px 9px #0003}
.cl-ring-tooltip[hidden]{display:none}
.cl-browse-stage{grid-area:stage;position:relative;display:grid;min-width:0;min-height:0;container-type:inline-size}
.cl-browse-metadata{width:min(100%,520px);justify-self:start;box-sizing:border-box;
 overflow:auto;overscroll-behavior:contain;scrollbar-width:thin}
.cl-browse-footer-head{display:flex;align-items:center;flex-wrap:wrap;gap:4px 7px;padding:0 8px}
 .cl-browse-stage{
 overflow:hidden;border-radius:7px;background:
 radial-gradient(ellipse at 18% 15%,#c3b8b8 0,transparent 64%),
 linear-gradient(177deg,#a49494,#b5a3a0 69%,#a69896)
}
.cl-browse-photo{
 grid-area:1 / 1;display:grid;place-items:center;min-width:0;min-height:0;overflow:hidden;
 transform:translateX(0) scale(1);transform-origin:center;
 mask-image:linear-gradient(90deg,transparent 0,#000 21%,#000 82%,transparent 100%),
            linear-gradient(0deg,transparent,#000 3%,#000 97%,transparent);
 mask-composite:intersect;mask-repeat:no-repeat;mask-position:center;mask-size:180% 180%;
 transition:transform .46s cubic-bezier(.22,.72,.25,1),mask-size .46s cubic-bezier(.22,.72,.25,1)
}
.cl-browse-photo :is(img,svg){width:100%;height:100%;min-width:0;min-height:0;object-fit:contain}
.cl-browse-photo audio{width:min(95%,430px)}
.cl-browse-stage[data-display-open=true] .cl-browse-photo{transform:translateX(23%) scale(.84);mask-size:100% 100%}
.cl-browse-stage[data-reference=true] .cl-browse-photo :is(img,svg){width:54%;height:88%}
.cl-wardrobe-exhibit{
 position:absolute;inset:0;z-index:1;pointer-events:none;visibility:hidden;
 opacity:0;transform:translateX(-1.5%);
 transition:opacity .42s ease,transform .46s cubic-bezier(.22,.72,.25,1),visibility 0s linear .46s
}
.cl-browse-stage[data-display-open=true] .cl-wardrobe-exhibit{
 visibility:visible;opacity:1;transform:translateX(0);transition-delay:0s
}
.cl-wardrobe-rail{
 position:absolute;left:3.4%;top:9%;width:44%;height:68%;border:1px solid #d4c7c3;
 border-top:2px solid #e4d7ce;border-bottom:0;border-radius:8% 8% 0 0;
 box-shadow:1px 0 0 #726463,0 -1px 0 #887672,1px 2px 8px #40362c23;
 pointer-events:none
}
.cl-wardrobe-plinth{
 position:absolute;left:2.9%;top:78%;width:45%;height:1.3%;
 background:linear-gradient(#d4c5bf,#a6928d);border-radius:40% 44% 4px 4px;
 box-shadow:0 2px 6px #493c3540;pointer-events:none
}
.cl-wardrobe-plinth::after{
 content:"";position:absolute;top:1320%;left:-1%;width:102%;height:37%;
 background:#55463a2e;filter:blur(3px);border-radius:50%
}
.cl-wardrobe-display-group{display:contents}
#characterDetail .cl-exhibit-piece{
 position:absolute;display:grid;place-items:center;min-height:0;min-width:0;
 padding:0;border:0;border-radius:4px;background:transparent;box-shadow:none;
 color:#3f322c;pointer-events:none;touch-action:manipulation
}
.cl-exhibit-hit{pointer-events:none}
.cl-browse-stage[data-display-open=true] .cl-exhibit-piece:not(:disabled) .cl-exhibit-hit{pointer-events:all}
.cl-exhibit-piece svg{
 display:block;width:100%;height:100%;overflow:visible;
 filter:drop-shadow(1px 2px 1px #43343a49);transition:filter .15s ease
}
#characterDetail .cl-exhibit-piece:hover:not(:disabled),
#characterDetail .cl-exhibit-piece[aria-pressed=true]{background:transparent;box-shadow:none}
.cl-exhibit-piece:is(:hover,:focus-visible,[aria-pressed=true]) svg{
 filter:drop-shadow(0 0 1.2px #fff4dd) drop-shadow(0 1px 1px #4b3949a0)
}
#characterDetail .cl-exhibit-piece:focus-visible{outline:1px solid #fff4dc;outline-offset:1px}
.cl-hanger{
 position:absolute;top:calc(-1 * var(--cl-hanger-drop,7%));left:50%;width:min(25%,26px);
 height:calc(var(--cl-hanger-drop,7%) + 11%);transform:translateX(-50%);
 color:#e4c8b3;pointer-events:none
}
.cl-hanger::before{
 content:"";position:absolute;left:calc(50% - .5px);top:0;bottom:6px;width:1px;
 background:currentColor;box-shadow:.5px 0 1px #52413765
}
.cl-hanger::after{
 content:"";position:absolute;left:0;bottom:0;width:100%;height:7px;
 background:linear-gradient(154deg,transparent 46%,currentColor 47% 54%,transparent 55%) left center/50% 100% no-repeat,
            linear-gradient(206deg,transparent 46%,currentColor 47% 54%,transparent 55%) right center/50% 100% no-repeat;
}
.cl-shelf-return[hidden]{display:none!important}
#characterDetail .cl-shelf-return{
 position:absolute;z-index:2;top:7px;right:6px;min-height:24px;padding:3px 6px;
 max-width:45%;font-size:clamp(9px,2.7cqw,11px)
}
@media(prefers-reduced-motion:reduce){
 .cl-browse-photo,.cl-wardrobe-exhibit,.cl-exhibit-piece svg{transition:none}
}

.cl-browse-caption{display:flex;align-items:center;flex-wrap:wrap;gap:5px 7px;min-height:29px;padding:4px 8px}
.cl-browse-caption strong{font-size:12px;overflow-wrap:anywhere}
.cl-browse-kind{font-size:11px;color:var(--cl-gray)}
.cl-browse-controls{display:flex;gap:4px;flex-wrap:wrap}
#characterDetail .cl-browse-controls button{font-size:11px;padding:3px 6px;min-height:25px}
.cl-browse-status{margin:0;min-height:16px;padding:0 8px 3px;color:var(--cl-gray);font-size:11px}
.cl-browse-status[role=status]:empty{display:none}
.cl-browse-info{max-height:min(20dvh,160px);overflow:auto;padding:1px 8px;min-width:0;overscroll-behavior:contain}
.cl-browse-info .cl-detail-fields{margin:3px 0;overflow-wrap:anywhere}
.cl-profile-pane{
 min-width:0;min-height:0;overflow:auto;overscroll-behavior:contain;scrollbar-width:thin;
 padding:14px;background:var(--cl-card);border:1px solid var(--cl-line);border-radius:14px
}
.cl-profile-pane h3{margin:0 0 7px;font-size:14px;font-weight:650}
.cl-profile-pane h3:not(:first-child){margin-top:13px}
.cl-profile-pane dl{margin:0}
.cl-profile-row{display:grid;grid-template-columns:minmax(80px,29%) minmax(0,1fr);gap:2px 8px;
 padding:5px 0;border-bottom:1px solid var(--cl-line);overflow-wrap:anywhere;font-size:13px}
.cl-profile-row dt{color:var(--cl-gray)}
.cl-profile-row dd{margin:0;min-width:0}
.cl-profile-fact{display:flex;align-items:baseline;column-gap:7px;row-gap:3px;flex-wrap:wrap}
.cl-profile-fact strong{font-variant-numeric:tabular-nums;font-weight:650}
.cl-profile-basis{display:block;margin-top:2px;color:var(--cl-gray);font-size:11px;line-height:1.35}
.cl-profile-badge{font-size:10px;border-radius:4px;padding:1px 4px;color:light-dark(#51336d,#f0dffb);background:light-dark(#f0e6f8,#493654)}
.cl-profile-badge[data-confirmation=specified]{color:light-dark(#216046,#c5f2d5);background:light-dark(#e5f4e9,#244736)}
.cl-profile-missing{color:var(--cl-gray);margin:7px 0 0;font-size:11px;line-height:1.4}
@media(max-width:720px){
 #characterDetail:has(.cl-browse){width:calc(100vw - 10px);height:calc(100dvh - 10px);border-radius:10px}
 .cl-browse{padding:6px;gap:5px}
 .cl-browse-layout{display:block;overflow:auto;overscroll-behavior:contain;scrollbar-width:none}
 .cl-browse-visual{display:block}
 .cl-browse-header{gap:4px}
 .cl-browse-header button{min-height:26px;padding:3px 6px;font-size:10px}
 #characterDetail .cl-browse-identity .cl-picture{width:34px;height:34px}
 .cl-browse-tools{gap:2px}
 #characterDetail .cl-browse-categories button{
   min-height:30px;padding:3px 6px
 }
 .cl-browse-body{grid-template-rows:min(585px,calc(100vw - 24px)) 88px;gap:5px}
 .cl-browse-arena{place-items:center}
 .cl-profile-pane{margin-top:10px;padding:11px}
 .cl-browse-caption{padding:3px 4px}
 .cl-browse-caption strong{font-size:11px}
 .cl-browse-footer-head{padding:0 4px}
}
.cl-browse-aux,.cl-look-select[hidden]{display:none}
.cl-browse-aux:has(>section:not([hidden]),>.cl-browse-info:not([hidden])){
 display:block;position:absolute;z-index:2;inset:auto max(6px,19%) 13px;
 background:var(--cl-bg);border:1px solid var(--cl-line);border-radius:9px;box-shadow:0 8px 30px #0003
}
.cl-browse-aux:has(>.cl-browse-info:not([hidden])){inset-block-end:96px}
.cl-look-select{border:1px solid var(--cl-line);background:var(--cl-card);border-radius:9px;padding:5px 7px}
.cl-look-select header{display:flex;align-items:center;justify-content:space-between;gap:7px;margin-bottom:4px}
.cl-look-select header h3{font-size:13px;margin:0}
.cl-look-choices{display:flex;align-items:stretch;gap:6px;max-height:min(22dvh,169px);
 overflow:auto;overscroll-behavior:contain;scrollbar-width:thin;padding:2px}
.cl-look-card{min-width:0;flex:0 0 145px;border:1px solid var(--cl-line);border-radius:6px;padding:3px}
#characterDetail .cl-look-choice{
 display:flex;align-items:center;gap:5px;text-align:start;white-space:normal;width:100%;font-size:11px;
 padding:3px;border:1px solid transparent;border-radius:5px;box-shadow:none
}
#characterDetail .cl-look-choice[aria-pressed=true]{border-color:var(--cl-accent);background:var(--cl-tint)}
#characterDetail .cl-look-choice .cl-picture{
 width:40px;height:38px;min-height:0;flex:none;aspect-ratio:auto;border-radius:4px
}
#characterDetail .cl-look-choice .cl-picture img{width:100%;height:100%;object-fit:contain}
.cl-look-choice span{min-width:0;overflow-wrap:anywhere}
.cl-look-choice .cl-ring-symbol{width:18px}
.cl-look-purpose{display:block;color:var(--cl-gray);font-size:10px;margin-top:2px}
#characterDetail .cl-browse-tile.cl-look-entry{border-style:dashed}
#characterDetail .cl-browse-tile.cl-look-entry[data-selected-version]:not([data-selected-version=""]){background:var(--cl-tint)}
#characterDetail .cl-browse-tile.cl-look-entry[aria-expanded=true]{border-style:solid;border-color:var(--cl-accent);background:var(--cl-tint)}
@media(max-width:720px){
 .cl-look-card{flex-basis:117px}
 .cl-look-choices{max-height:22dvh}
 #characterDetail .cl-look-choice .cl-picture{width:31px;height:32px}
}

.cl-guide-tabs{display:flex;gap:3px;flex-shrink:0}
#characterDetail .cl-guide-tabs button[aria-expanded=true]{background:var(--cl-tint);color:var(--cl-accent)}
.cl-guide-panel{max-height:min(26dvh,185px);overflow:auto;padding:5px 8px;border:1px solid var(--cl-line);
 border-radius:8px;background:var(--cl-card);overscroll-behavior:contain;font-size:11px}
.cl-guide-panel[hidden],.cl-guide-selection[hidden]{display:none!important}
.cl-guide-panel h4{font-size:12px;margin:3px 0}
.cl-guide-note span,.cl-guide-selection{color:var(--cl-gray)}
.cl-guide-note{margin:2px 0 5px}.cl-guide-note strong{margin-right:6px}
.cl-guide-selection{font-size:11px;margin:0;padding:0 8px 4px;overflow-wrap:anywhere}
/* Keep control metrics local to the character detail and its equipment picker. */
#characterDetail :is(.cl-browse,.cl-gear){
 --cl-control-size:12px;--cl-control-height:29px;--cl-control-line:1.25;
 --cl-control-inset:7px;--cl-category-size:15px
}
#characterDetail :is(.cl-browse,.cl-gear) button:where(:not(
 [hidden],.cl-browse-tile,.cl-exhibit-piece,.cl-look-choice,.cl-asset-choice,.cl-slot)){
 display:inline-flex;align-items:center;justify-content:center;column-gap:4px;
 min-height:var(--cl-control-height);padding:3px var(--cl-control-inset);
 font-family:inherit;font-size:var(--cl-control-size);font-weight:550;line-height:var(--cl-control-line);
 text-align:center;white-space:normal;overflow-wrap:anywhere;box-sizing:border-box;box-shadow:none
}
#characterDetail .cl-browse .cl-browse-categories button{
 font-size:var(--cl-category-size);font-weight:550;white-space:nowrap
}
#characterDetail .cl-browse .cl-browse-revision select,
#characterDetail .cl-browse .cl-ruler-options select{
 box-sizing:border-box;max-width:100%;min-height:var(--cl-control-height);width:auto;
 padding:3px var(--cl-control-inset);font-family:inherit;font-size:var(--cl-control-size);
 font-weight:550;line-height:var(--cl-control-line);text-align:center;text-align-last:center
}
#characterDetail :is(.cl-browse,.cl-gear) .cl-look-choice{
 justify-content:center;align-items:center;text-align:center;gap:6px;
 font-family:inherit;font-size:var(--cl-control-size);font-weight:550;line-height:var(--cl-control-line)
}
#characterDetail :is(.cl-browse,.cl-gear) .cl-look-choice>span:last-child{
 min-width:0;max-width:100%;text-align:center;overflow-wrap:anywhere
}
#characterDetail :is(.cl-browse,.cl-gear) .cl-asset-choice{
 align-items:center;justify-items:center;text-align:center;
 font-family:inherit;font-size:var(--cl-control-size);line-height:var(--cl-control-line)
}
#characterDetail :is(.cl-browse,.cl-gear) :is(.cl-slot,.cl-browse-tile,.cl-exhibit-piece){
 align-items:center;justify-items:center;text-align:center;line-height:1
}
#characterDetail .cl-browse-tile .cl-ring-symbol{block-size:auto;margin:auto}
#characterDetail .cl-browse .cl-ruler-options label{
 min-height:var(--cl-control-height);font-family:inherit;font-size:var(--cl-control-size);
 font-weight:550;line-height:var(--cl-control-line);align-items:center;justify-content:center
}
#characterDetail .cl-browse .cl-ruler-options input[type=checkbox]{
 flex:none;inline-size:14px;block-size:14px;margin:0
}
#characterDetail .cl-browse .cl-ruler-summary summary{
 width:fit-content;min-height:23px;padding:3px 3px;font-size:var(--cl-control-size);
 font-weight:600;line-height:var(--cl-control-line)
}
#characterDetail :is(.cl-browse,.cl-gear) :is(button,select,summary,input):where(:not(.cl-browse-tile,.cl-exhibit-piece)):focus-visible{
 outline:2px solid var(--cl-accent);outline-offset:1px
}
#characterDetail :is(.cl-browse,.cl-gear) audio{align-self:center;justify-self:center}
@media(max-width:720px){
 #characterDetail :is(.cl-browse,.cl-gear){
   --cl-control-size:11px;--cl-control-height:28px;--cl-control-inset:6px;--cl-category-size:13px
 }
 #characterDetail .cl-browse .cl-browse-categories button{padding-inline:6px}
 #characterDetail .cl-browse .cl-ruler-options{gap:3px 5px}
}
@media(max-width:380px){
 .cl-browse:has(.cl-guide-tabs) .cl-browse-caption{gap:3px}
}

'''

SCRIPT = RULER_SCRIPT + r'''
function OACharacterLibrary(tool,openProjectSettings,sendChat,canSend){
 const $=id=>document.getElementById(id);
 const page=$('characterLibrary'),picker=$('characterPicker'),detail=$('characterDetail'),importer=$('characterImport');
 const useText={full_body:'标准全身',face:'人脸',expression:'表情',pose:'动作',style:'风格／质感',
   angle:'视角',wardrobe:'服装',accessory:'配饰',voice:'声音参考'};
 const normalForm={id:'normal',name:'常态'};
 const gearGroups=['hair','wardrobe','accessories'];
 const groups={base:'人物基础',features:'五官细节',hair:'发型',wardrobe:'服装',accessories:'配饰',voice:'声音'};
 const viewsOfBody={front:'正面',three_quarter:'四分之三侧面',side:'正侧面',back:'背面',overview:'四视角总览',
   head_front:'正面头部',head_blank:'正面光头无面头模',body_blank:'正面无面全身'};
 const presentations={individual:'独立原图',source_detail:'局部来源图',combined:'配饰合图',full_look:'整身搭配原图'};
 const stateText={current:'当前参考',candidate:'待确认',historical:'历史'};
 const action=(name,args={})=>tool('video.director.read',{action:name,...args});
 const edit=(name,args)=>tool('video.director.edit',{action:name,...args});
 const projectMedia=(name,args)=>tool('wce.ui.video.director.media',{action:name,...args});
 const media=(name,row,extra={})=>tool('wce.ui.video.director.media',{
   action:name,project_id:row.file.project_id,version_id:row.id,sha256:row.file.sha256,...extra});
 const t=(text,...values)=>OAUI.format(text,values);
 function node(tag,cls='',text){
   const el=document.createElement(tag);if(cls)el.className=cls;
   if(text!==undefined)OAUI.set(el,text);return el;
 }
 function button(text,activate){
   const el=node('button','',text);el.type='button';el.onclick=activate;return el;
 }
 const messages={
   DIRECTOR_CHARACTER_MANIFEST_CHANGED:'索引文件已变化，请重新选择。',
   DIRECTOR_CHARACTER_MANIFEST_INVALID:'索引格式有误，请检查文件。',
   DIRECTOR_STALE_REVISION:'镜头修订已更新，请返回新修订重新选择。',
   INVALID_TOOL_ARGUMENTS:'索引格式或输入有误。',
   DIRECTOR_ASSET_OUTSIDE_PROJECT:'索引或图片路径超出项目目录。',
   DIRECTOR_CHARACTER_DUPLICATE:'索引含有重复的版本标识。',
   DIRECTOR_CHARACTER_VERSION_CONFLICT:'这个版本标识已登记给其他内容，请使用新的版本标识。',
   DIRECTOR_CHARACTER_CURRENT_CONFLICT:'当前参考已变化，请刷新后重试。',
   DIRECTOR_CHARACTER_PRIMARY_CONFLICT:'主参考已变化，请刷新后重试。',
   DIRECTOR_CHARACTER_FACE_REFERENCE_REQUIRED:'请选用此形态中能看到人脸的标准资产。',
   DIRECTOR_CHARACTER_WORK_SCOPE_MISMATCH:'该特别资产只用于登记的作品。',
   DIRECTOR_CHARACTER_FORM_CONFLICT:'形态标识与已登记的名称冲突。',
   DIRECTOR_CHARACTER_CROP_INVALID:'裁切范围或原图版本无法核对。',
   DIRECTOR_CHARACTER_STALE_INDEX:'索引已有更新，请重新预览。',
   DIRECTOR_CHARACTER_REFERENCE_MISMATCH:'登记版本或原图指纹已变化，请重新选择。',
   DIRECTOR_ASSET_CHANGED:'原图的内容与登记版本不一致，请恢复原文件或登记新版本。',
   BOOTSTRAP_UNSAFE_PATH:'文件无法读取，请核对原项目路径与文件。',
   DIRECTOR_CHARACTER_ORIGINAL_MISSING:'找不到原图。请核对原项目路径。',
   DIRECTOR_CHARACTER_ORIGINAL_UNAVAILABLE:'无法读取原图。请检查文件后重试。',
   DIRECTOR_CHARACTER_ORIGINAL_PERMISSION:'没有读取原图的权限。',
   DIRECTOR_CHARACTER_IMAGE_DIMENSIONS:'形象图片的宽和高均须在 300–6000 像素之间。',
   DIRECTOR_CHARACTER_IMAGE_DECODE_FAILED:'图片无法解码。请选择完整的单张 PNG 或 JPEG。',
   VIDEO_FRAME_TOO_LARGE:'原图须小于 30 MB。',
   DIRECTOR_CHARACTER_IMAGE_LOAD_FAILED:'图片已返回，当前界面无法解码显示。',
   DIRECTOR_CHARACTER_IMAGE_TRANSFER_FAILED:'原图传输未完成，请重试。',
   DIRECTOR_PREVIEW_UNAVAILABLE:'无法生成原图预览。',
   DIRECTOR_PROJECT_NOT_REGISTERED:'项目登记已变化，请检查项目设置。',
   DIRECTOR_PROJECT_UNAVAILABLE:'项目目录不可用，请核对项目登记。',
   VIDEO_FRAME_CHANGED:'原图的内容与登记版本不一致，请恢复原文件或登记新版本。',
   INVALID_LOCAL_FILE:'文件无法读取，请核对原项目路径与文件。',
 };
 const error=problem=>messages[problem?.message]||'无法读取形象资产，请核对项目登记和原图。';
 function importError(problem){
   const diagnostic=problem?.diagnostic;
   if(!diagnostic?.manifest_field)return t(error(problem));
   const field=diagnostic.manifest_field,position=diagnostic.manifest_position;
   if(field==='use'&&position)return t('第 {0} 项的 use 无效。允许值：{1}',position,(diagnostic.allowed_values||Object.keys(useText)).join(', '));
   return position?t('第 {0} 项的 {1} 有误。{2}',position,field,t(error(problem))):
     t('索引的 {0} 有误。{1}',field,t(error(problem)));
 }
 let projects=[],refreshID=0,pickerSession=null,detailTrigger=null,importPlan=null,importEpoch=0;
 const browserStorage='jiusera.assets.characters';
 let retained={}, restoreBrowser=false, browserDetail=false;
 try{retained=JSON.parse(localStorage.getItem(browserStorage))||{};}catch(_){}
 function keepBrowser(){
   if(page.hidden||restoreBrowser)return;
   retained={project:browser.project,query:browser.search.value,
     scroll:browser.main.scrollTop,detailScroll:browserDetail?detail.scrollTop:0,
     selected:retained.selected,selectedForm:retained.selectedForm,selectedVersion:retained.selectedVersion,
     selectedRevision:retained.selectedRevision,frontLooks:retained.frontLooks,
     show:browserDetail};
   try{localStorage.setItem(browserStorage,JSON.stringify(retained));}catch(_){}
 }
 const exactKey=row=>JSON.stringify([row.file.project_id,row.id,row.file.sha256]);
 const personKey=row=>JSON.stringify([row.file.project_id,row.character.id]);
 const isVoice=row=>row.use==='voice';
 const face=row=>!isVoice(row)&&(row.face_visible??row.use==='face');
 const kind=row=>row.category||'standard';
 const inHistory=row=>!row.primary&&row.status!=='current'&&
   (row.status==='historical'||row.origin_status==='historical');
 const useName=row=>useText[row.use]||row.use;
 const normalize=value=>String(value??'').normalize('NFKC').toLocaleLowerCase();
 function selectable(view,row){
   if(!view.picking)return true;
   if(inHistory(row))return false;
   const filter=pickerSession?.mediaKind;
   if(filter&&filter!==(isVoice(row)?'audio':'image'))return false;
   if(kind(row)==='special')return !!pickerSession?.work&&row.file.project_id===pickerSession.project&&row.work_id===pickerSession.work;
   return !row.crop||row.file.project_id===pickerSession?.project;
 }
 function faceReference(rows){
   return rows.find(row=>row.primary&&face(row)&&kind(row)==='standard')
     ||rows.find(row=>row.status==='current'&&face(row)&&kind(row)==='standard');
 }
 function preferredAsset(rows){
   return faceReference(rows)||rows.find(row=>kind(row)==='standard'&&!isVoice(row))
     ||rows.find(row=>kind(row)==='standard')||rows[0];
 }
 function filterBySearch(row,project,query,picking){
   return !query||[row.character.name,row.character.series,project.name,...row.character.aliases,
     ...(picking?[row.form.name,t(row.form.name),row.label]:[])].some(value=>normalize(value).includes(query));
 }
 function groupCharacters(view,project){
   const characters=new Map();
   const parts=new Set((project.browse_guides||[]).flatMap(guide=>guide.front_layers?.pieces.flatMap(piece=>
     [piece.asset.version,...piece.variants.map(item=>item.asset.version)])||[]));
   for(const asset of project.assets){
     if(view.picking&&parts.has(asset.id))continue;
     if(!selectable(view,asset))continue;
     const row={...asset,form:asset.form||normalForm,projectName:project.name};
     const key=personKey(row);
     if(!characters.has(key))characters.set(key,{key,projectName:project.name,character:row.character,profile:{},forms:new Map()});
     const shape=characters.get(key);
     Object.assign(shape.profile,row.character.profile||{});
     if(!shape.forms.has(row.form.id)){
       const guides=view.picking?[]:(project.browse_guides||[]).filter(candidate=>
         candidate.character===row.character.id&&candidate.form===row.form.id);
       shape.forms.set(row.form.id,{...row.form,rows:[],guides});
     }
     shape.forms.get(row.form.id).rows.push(row);
   }
   const rank={current:0,candidate:1,historical:2};
   for(const person of characters.values()){
     for(const form of person.forms.values())form.rows.sort((a,b)=>{
       return rank[a.status]-rank[b.status]||a.label.localeCompare(b.label)||a.id.localeCompare(b.id);
     });
   }
   return characters;
 }
 const browseImageCache=new Map();
 function cachedCharacterImage(action,row){
   const key=action+':'+exactKey(row);
   const cached=browseImageCache.get(key);
   if(cached){
     browseImageCache.delete(key);browseImageCache.set(key,cached);
     return cached;
   }
   const pending=media(action,row).then(value=>{
     if(value.sha256!==row.file.sha256||value.mime_type!=='image/jpeg'||!value.data?.startsWith('/9j/'))
       throw Error('DIRECTOR_CHARACTER_ORIGINAL_UNAVAILABLE');
     return 'data:image/jpeg;base64,'+value.data;
   }).catch(problem=>{
     if(browseImageCache.get(key)===pending)browseImageCache.delete(key);
     throw problem;
   });
   browseImageCache.set(key,pending);
   if(browseImageCache.size>24)browseImageCache.delete(browseImageCache.keys().next().value);
   return pending;
 }
 const jobs=[];let running=0;
 function drain(){
   while(running<3&&jobs.length){
     const task=jobs.shift();if(!task.figure.isConnected)continue;
     running++;
     cachedCharacterImage('character_thumbnail',task.row).then(src=>{
       if(!task.figure.isConnected)return;
       const img=node('img');img.alt=task.row.character.name;img.src=src;
       if(task.figure.closest('#characterLibrary .cl-card')){
         img.onerror=()=>{if(img.parentElement===task.figure)cardPlaceholder(task.figure,'unreadable');};
       }
       task.figure.replaceChildren(img);
       if(task.figure.closest('#characterLibrary .cl-card'))task.figure.dataset.coverState='available';
     }).catch(problem=>{
       if(!task.figure.isConnected)return;
       if(task.figure.closest('#characterLibrary .cl-card'))cardPlaceholder(task.figure,'unreadable');
       else{task.figure.textContent=t(error(problem));task.figure.dataset.unavailable='true';}
     }).finally(()=>{running--;drain();});
   }
 }
 const observed=new WeakMap();
 const thumbnails=new IntersectionObserver(entries=>{
   for(const entry of entries)if(entry.isIntersecting){
     thumbnails.unobserve(entry.target);jobs.push({figure:entry.target,row:observed.get(entry.target)});
   }
   drain();
 },{rootMargin:'120px'});
 function badge(row){
   const el=node('span','cl-badge',stateText[row.status]);el.dataset.status=row.status;return el;
 }
 function makeView(host,picking){
   const shell=node('div','cl-layout cl-roster'),main=node('div','cl-main');
   const header=node('header','cl-header'),title=node('h1','','形象资产库'),controls=node('div','cl-controls');
   title.tabIndex=-1;
   const search=node('input');search.type='search';
   const searchLabel=picking?'搜索人物、形态或项目':'搜索人物';
   OAUI.attr(search,'placeholder',searchLabel);OAUI.attr(search,'aria-label',searchLabel);
   const projectSelect=node('select');OAUI.attr(projectSelect,'aria-label','按项目筛选');
   const dropdown=node('details','cl-roster-tools'),actions=node('div','cl-actions');
   dropdown.append(node('summary','','管理'),actions);
   actions.append(button('刷新',()=>{dropdown.open=false;void refresh();}));
   if(!picking)actions.append(button('导入索引',()=>{dropdown.open=false;showImport(view);}));
   controls.append(search,projectSelect,dropdown);header.append(title,controls);
   const count=node('p','cl-count'),grid=node('div','cl-grid');
   count.setAttribute('role','status');main.append(header,count,grid);shell.append(main);host.append(shell);
   const view={main,title,search,projectSelect,count,grid,project:'',picking,persons:new Map()};
   projectSelect.onchange=()=>{view.project=projectSelect.value;render(view);};
   search.oninput=()=>render(view);if(!picking)main.onscroll=keepBrowser;return view;
 }
 const browser=makeView(page,false),selection=makeView($('clPickerLibrary'),true),views=[browser,selection];
 function syncProjects(view){
   const select=view.projectSelect,available=[['',t('全部项目')],...projects.map(row=>[row.id,row.label||row.name])];
   if(available.length!==select.options.length||available.some(([id,title],index)=>
      select.options[index].value!==id||select.options[index].textContent!==title)){
     select.replaceChildren(...available.map(([id,title])=>{
       const option=node('option');option.value=id;
       if(id)OAUI.raw(option,title);else OAUI.set(option,'全部项目');
       return option;
     }));
   }
   select.value=view.project;
 }
 function coverFor(forms){
   for(const pick of [row=>row.primary&&face(row)&&kind(row)==='standard',
                      row=>row.status==='current'&&face(row)&&kind(row)==='standard',
                      row=>row.appearance?.format==='source_detail'&&face(row)&&kind(row)==='standard',
                      row=>face(row)&&kind(row)==='standard',
                      row=>!isVoice(row)&&kind(row)==='standard',row=>!isVoice(row),()=>true]){
     for(const form of forms){
       const row=form.rows.find(pick);
       if(row)return row;
     }
   }
 }
 function overviewHead(forms){
   const isHead=row=>!inHistory(row)&&!row.browseArchived&&!row.crop&&kind(row)==='standard'&&
     row.use==='face'&&row.face_visible!==false&&row.appearance?.group==='base'&&
     row.appearance.view==='head_front'&&row.appearance.format==='individual';
   for(const form of forms){
     const rows=form.rows.filter(isHead);
     const row=rows.find(value=>value.primary)||rows.find(value=>value.status==='current')||rows[0];
     if(row)return row;
   }
 }
 function cardPlaceholder(figure,state){
   figure.dataset.coverState=state;figure.classList.add('cl-card-placeholder');
   figure.replaceChildren(ringSymbol('head'),node('span','',state==='missing'?'未登记正面纯人头':'正面纯人头暂无法读取'));
 }
 function standing(rows){
   return rows.find(row=>row.appearance?.group==='base'&&row.appearance.view==='front'&&row.status==='current')
     ||rows.find(row=>row.appearance?.group==='base'&&row.appearance.view==='front')
     ||rows.find(row=>row.use==='full_body'&&row.status==='current')
     ||rows.find(row=>row.use==='full_body')
     ||preferredAsset(rows);
 }
 const guideKey=guide=>guide?.revision||'legacy';
 function trialVersions(guide){
   const layers=guide.front_layers;
   const fits=(guide.front_fits||[]).flatMap(fit=>[fit.result.version,fit.accessory?.version].filter(Boolean));
   if(!layers)return fits;
   return fits.concat(layers.underlays.map(item=>item.asset.version),
     layers.pieces.flatMap(piece=>[piece.asset.version,...piece.variants.map(item=>item.asset.version)]));
 }
 function registeredFullLook(row){
   return !inHistory(row)&&['current','candidate'].includes(row.status)&&kind(row)==='standard'&&!row.crop&&row.use==='full_body'&&
     row.appearance?.format==='full_look'&&!!row.appearance.combination?.length;
 }
 const acceptedFullLook=row=>row.status==='current'&&registeredFullLook(row);
 function accessorySheetKey(row){
   return row.appearance?.group==='accessories'&&row.appearance.format==='combined'?
     JSON.stringify([row.appearance.item_id,row.file.sha256]):'';
 }
 function scopedBrowseForm(form,row,revision){
   const {guides}=form;
   const trial=new Set(guides.flatMap(trialVersions));
   const looks=form.rows.filter(candidate=>!trial.has(candidate.id)&&registeredFullLook(candidate));
   const linked=(guide,look)=>look?.appearance.combination.some(id=>guide.entries.some(ref=>ref.version===id));
   const owns=(guide,id)=>guide.entries.some(ref=>ref.version===id)||guide.archive.some(ref=>ref.version===id)
     ||trialVersions(guide).includes(id)||linked(guide,looks.find(look=>look.id===id));
   const guide=guides.find(value=>guideKey(value)===revision)
     ||guides.find(value=>owns(value,row?.id))||guides[0];
   if(!guide)return {...form,rows:form.rows.map(row=>({...row,browseArchived:inHistory(row)})),looks};
   const notes=new Map(guide.entries.map((entry,order)=>[entry.version,{...entry,order}]));
   const archive=new Set(guide.archive.map(entry=>entry.version));
   const admittedSheets=new Set(form.rows.filter(entry=>notes.has(entry.id)).map(accessorySheetKey).filter(Boolean));
   const permitted=looks.filter(look=>linked(guide,look));
   const rows=form.rows.filter(value=>!trial.has(value.id)&&(notes.has(value.id)||archive.has(value.id)
      ||permitted.some(look=>look.id===value.id)
      ||value.appearance?.details?.length&&admittedSheets.has(accessorySheetKey(value))
      ||!guide.revision&&!guides.some(other=>other!==guide&&owns(other,value.id))))
     .map(value=>({...value,browseNote:notes.get(value.id),browseArchived:archive.has(value.id)||inHistory(value)}));
   return {...form,rows,guide,archive,looks:permitted};
 }
 function browseHome(form,guide=form.guide||form.guides[0]){
   const trial=new Set(form.guides.flatMap(trialVersions));
   const active=form.rows.filter(row=>!trial.has(row.id)&&!row.browseArchived&&!inHistory(row));
   return active.find(row=>row.id===guide?.baseline)
     ||standing(active.filter(row=>row.appearance?.format!=='full_look'))
     ||active.find(acceptedFullLook);
 }
 function render(view){
   if(view.picking&&!picker.open)return;
   if(!view.picking&&page.hidden)return;
   const query=normalize(view.search.value.trim()),visible=[];
   view.persons=new Map();
   for(const project of projects){
     if(view.project&&project.id!==view.project)continue;
     for(const person of groupCharacters(view,project).values()){
       const forms=[...person.forms.values()].sort((a,b)=>
         Number(b.id===normalForm.id)-Number(a.id===normalForm.id)||a.name.localeCompare(b.name));
       const match=forms.find(form=>form.rows.some(row=>filterBySearch(row,project,query,view.picking)));
       if(!match)continue;
       const shown=view.picking?match:forms[0];
       const coverForms=view.picking?forms:forms.map(form=>scopedBrowseForm(form,null,'legacy'));
       const initial=view.picking?standing(shown.rows):browseHome(shown)||shown.rows[0];
       if(!initial)continue;
       const shape={...person,forms,initial,cover:view.picking?coverFor(coverForms):overviewHead(coverForms)};
       view.persons.set(person.key,shape);visible.push(shape);
     }
   }
   const selected=projects.find(row=>row.id===view.project);
   view.count.textContent=visible.length?t('{0} 位人物',visible.length):
     t(selected?.unavailable?'项目目录或索引无法读取，请检查项目设置。':
       projects.some(row=>row.assets.length)?'没有匹配的形象。':'还没有已登记的形象。');
   if(projects.some(project=>project.unavailable)&&!selected)view.count.append(' · '+t('部分项目不可用'));
   const names=new Map();
   for(const shape of visible)names.set(shape.character.name,(names.get(shape.character.name)||0)+1);
   for(const figure of view.grid.querySelectorAll('.cl-picture'))thumbnails.unobserve(figure);
   view.grid.replaceChildren(...visible.map(person=>{
     const {cover,initial}=person;
     const card=button(undefined,()=>showDetail(view,person,initial,card));
     card.className='cl-card';card.dataset.character=person.character.id;card.dataset.version=cover?.id||'';
     card.dataset.exact=person.key;
     if(names.get(person.character.name)>1){
       card.setAttribute('aria-label',[person.character.name,person.projectName,person.character.series].join(' · '));
       card.title=[person.projectName,person.character.series].join(' · ');
     }
     if(!view.picking)card.setAttribute('aria-pressed',String(retained.selected===person.key));
     const figure=node('span','cl-picture','正在读取原图…'),copy=node('span','cl-card-copy'),name=node('strong');
     OAUI.raw(name,person.character.name);copy.append(name);card.append(figure,copy);
     if(!cover)cardPlaceholder(figure,'missing');
     else if(isVoice(cover)){
       figure.classList.add('cl-voice-cover');
       const note=node('strong','','♫');note.setAttribute('aria-hidden','true');
       figure.replaceChildren(note,node('span','','声音参考'));
     }else{
       observed.set(figure,cover);thumbnails.observe(figure);
     }
     return card;
   }));
   if(!view.picking)keepBrowser();
 }
 async function refresh(){
   browseImageCache.clear();
   const id=++refreshID;
   if(!projects.length)for(const view of views)view.count.textContent=t('正在读取形象资产…');
   try{
     const result=await action('character_library');
     if(id!==refreshID)return;
     projects=result.projects;
     if(restoreBrowser&&!page.hidden){
       const query=new URLSearchParams(location.search);
       const explicit=query.get('character')&&query.get('character_project');
       browser.project=explicit?query.get('character_project'):(retained.project||'');
       browser.search.value=explicit?'':(retained.query||'');
     }
     for(const view of views){
       if(!projects.some(row=>row.id===view.project))view.project='';
       syncProjects(view);
       render(view);
     }
     if(restoreBrowser&&!page.hidden){
       const previous=retained;
       browser.main.scrollTop=Number(previous.scroll)||0;
       restoreBrowser=false;
       const launch=new URLSearchParams(location.search);
       const specified=launch.get('character')&&launch.get('character_project');
       if(specified||previous.show){
         const key=specified?JSON.stringify([launch.get('character_project'),launch.get('character')]):previous.selected;
         for(const person of browser.persons.values()){
           const rows=person.forms.flatMap(form=>form.rows);
           if(person.key!==key&&!rows.some(row=>exactKey(row)===key))continue;
           const version=specified?launch.get('character_version'):'';
           const revision=specified?launch.get('character_collection'):previous.selectedRevision;
           const row=(specified?rows.find(row=>row.id===version):
             rows.find(row=>exactKey(row)===(previous.selectedVersion||key))
             ||preferredAsset(person.forms.find(form=>form.id===previous.selectedForm)?.rows||[]))||person.initial;
           const card=[...browser.grid.children].find(entry=>entry.dataset.exact===person.key);
           showDetail(browser,person,row,card,undefined,revision);
           const launchRuler=specified&&launch.get('character_ruler');
           if(['open','compare'].includes(launchRuler)&&gearPage?.ruler){
             gearPage.compareOnLoad=launchRuler==='compare';
             toggleRuler(gearPage,true);
           }
           detail.scrollTop=Number(previous.detailScroll)||0;
           break;
         }
       }
       keepBrowser();
     }
   }catch(problem){
     if(id===refreshID)for(const view of views)view.count.textContent=t(error(problem));
   }
 }
 function closeDetail(){
   disposeGear();if(detail.open)detail.close();
 }
 let backdropPointer=null,backdropTap=false;
 function inBackdrop(event){
   const rect=detail.getBoundingClientRect();
   return event.clientX<rect.left||event.clientX>=rect.right||event.clientY<rect.top||event.clientY>=rect.bottom;
 }
 detail.addEventListener('pointerdown',event=>{
   backdropTap=false;
   backdropPointer=inBackdrop(event)?event.pointerId:null;
 },true);
 detail.addEventListener('pointerup',event=>{
   backdropTap=backdropPointer===event.pointerId&&inBackdrop(event);
   backdropPointer=null;
 },true);
 detail.addEventListener('pointercancel',()=>{backdropPointer=null;backdropTap=false;},true);
 detail.addEventListener('click',event=>{
   if(!backdropTap||event.detail===0)return;
   backdropTap=false;
   // Touch click targeting may snap to an element inside the dialog.
   event.preventDefault();
   event.stopPropagation();
   closeDetail();
 },true);
 detail.addEventListener('close',()=>{
   if(detail.open)return;
   if(browserDetail){browserDetail=false;keepBrowser();}
   disposeGear();
   if(detailTrigger?.isConnected&&!pickerSession?.closing)detailTrigger.focus({preventScroll:true});
   detailTrigger=null;
 });
 async function exactMedia(row,alive,action='character_original'){
   const allowed=isVoice(row)?['audio/wav']:['image/png','image/jpeg'];
   const chunks=[];let total=0,offset=0,mime='';
   do{
     let part;
     try{part=await media(action,row,{offset});}
     catch(problem){
       if(['HOST_ERROR','HOST_TIMEOUT'].includes(problem.message))throw Error('DIRECTOR_CHARACTER_IMAGE_TRANSFER_FAILED');
       throw problem;
     }
     if(!alive())return null;
     if(part.sha256!==row.file.sha256||part.offset!==offset
       ||!Number.isSafeInteger(part.total)||part.total<=0
       ||!allowed.includes(part.mime_type)
       ||(offset&&(part.mime_type!==mime||part.total!==total)))throw Error('DIRECTOR_CHARACTER_IMAGE_TRANSFER_FAILED');
     mime=part.mime_type;total=part.total;
     const bytes=Uint8Array.from(atob(part.data),symbol=>symbol.charCodeAt(0));
     if(!bytes.length||offset+bytes.length>total)throw Error('DIRECTOR_CHARACTER_IMAGE_TRANSFER_FAILED');
     chunks.push(bytes);offset+=bytes.length;
   }while(offset<total);
   const blob=new Blob(chunks,{type:mime});
   if(crypto.subtle){
     const sum=await crypto.subtle.digest('SHA-256',await blob.arrayBuffer());
     if(Array.from(new Uint8Array(sum),v=>v.toString(16).padStart(2,'0')).join('')!==row.file.sha256)
       throw Error('VIDEO_FRAME_CHANGED');
   }
   return alive()?blob:null;
 }
 const groupOf=row=>isVoice(row)?'voice':row.appearance?.group||
   ({face:'features',expression:'features',wardrobe:'wardrobe',accessory:'accessories'})[row.use]||'base';
 const itemOf=row=>row.appearance?.item_name||row.label;
 const rigOf=row=>row?.appearance?.try_on;
 let gearPage=null;
 function collapseDrawer(state,restore=true){
   if(!state||state.drawer.hidden)return;
   if(state.slot)state.positions.set(state.slot,(state.optionScroll||state.options).scrollTop);
   state.drawer.hidden=true;
   for(const button of state.slots.values())button.setAttribute('aria-expanded','false');
   if(restore)state.slotButton?.focus({preventScroll:true});
 }
 function disposeGear(){
   if(!gearPage)return;
   gearPage.selection++;gearPage.stageSelection++;
   gearPage.turntable?.close();gearPage.ruler?.dispose();
   for(const audio of gearPage.root.querySelectorAll('audio')){
     audio.pause();audio.removeAttribute('src');audio.load();
   }
   for(const key of ['photoURL','stageURL'])if(gearPage[key])URL.revokeObjectURL(gearPage[key]);
   gearPage=null;
 }
 detail.addEventListener('cancel',event=>{
   if(gearPage?.ruler?.isComparing()){event.preventDefault();gearPage.ruler.setCompare(false);}
   else if(gearPage?.rulerActive){event.preventDefault();toggleRuler(gearPage,false);}
   else if(gearPage?.drawer&&!gearPage.drawer.hidden){event.preventDefault();collapseDrawer(gearPage);}
   else if(gearPage?.lookPicker&&(!gearPage.lookPicker.hidden||!gearPage.info.hidden||
     !gearPage.supplement.hidden||gearPage.requested?.temporary)){
     event.preventDefault();closeBrowseLayers(gearPage,true);
   }
 });
 function rememberGear(state,row){
   browserDetail=!state.view.picking;
   if(!browserDetail)return;
   retained.selected=state.person.key;retained.selectedForm=state.form.id;retained.selectedVersion=exactKey(row);
   retained.selectedRevision=state.form.guide?guideKey(state.form.guide):undefined;
   for(const card of browser.grid.querySelectorAll('.cl-card'))
     card.setAttribute('aria-pressed',String(card.dataset.exact===retained.selected));
   keepBrowser();
 }
 function updateFields(state,row){
   const look=row.appearance,voice=isVoice(row),value=state.fields;
   const list=[
     ['名称',row.label],
     ['用途',look&&look.view!=='asset'?viewsOfBody[look.view]:useName(row)],
     ['版本',look?.version_label?look.version_label+' · '+row.id:row.id],
     ['来源',row.source||'未注明'],
     [row.origin?'本项目状态':'状态',stateText[row.status]],
     ...(row.origin?[['来源项目状态',stateText[row.origin_status]||'未能核实']]:[]),
     [voice?'原音路径':'原图路径',row.registered_path||row.file.path],
     ...(row.work_title||row.work_id?[['指定作品',row.work_title||row.work_id]]:[]),
     ...(row.description?[['说明',row.description]]:[]),
     ...(row.crop?[['裁切来源版本',row.crop.source_version_id]]:[]),
   ];
   for(const [label,content] of list){
     const term=node('dt','',label),desc=node('dd');
     if(['状态','本项目状态','来源项目状态','用途'].includes(label))OAUI.set(desc,content);else OAUI.raw(desc,content);
     value.append(term,desc);
   }
 }
 function titleOfStyle(row){
   return row.appearance?.version_label?itemOf(row)+' · '+row.appearance.version_label:row.label;
 }
 function toggleRig(state,mode){
   state.canvas.hidden=mode!=='rig';state.stagePhoto.hidden=mode==='rig';
   state.legend.textContent=t(mode==='rig'?'3D 试穿样件 · 横向拖动旋转':'登记参考图');
   state.rigToggle.hidden=!state.turntable;
   if(state.turntable)OAUI.set(state.rigToggle,mode==='rig'?'查看基础原图':'返回 3D 试穿');
   if(mode==='rig')state.turntable?.draw();
 }
 function imageReady(element){
   if(!element.complete){
     return new Promise((resolve,reject)=>{
       element.addEventListener('load',resolve,{once:true});
       element.addEventListener('error',()=>reject(Error('DIRECTOR_CHARACTER_IMAGE_LOAD_FAILED')),{once:true});
     });
   }
   return element.naturalWidth>0?Promise.resolve():Promise.reject(Error('DIRECTOR_CHARACTER_IMAGE_LOAD_FAILED'));
 }
 function imageSource(blob){
   // The MCP App iframe can display inline images without permission to load blob: URLs.
   return new Promise((resolve,reject)=>{
     const reader=new FileReader();
     reader.onload=()=>resolve(reader.result);
     reader.onerror=()=>reject(Error('DIRECTOR_CHARACTER_IMAGE_LOAD_FAILED'));
     reader.readAsDataURL(blob);
   });
 }
 async function picture(state,row,section,ticket,original=false,thumbnail=false){
   const alive=()=>gearPage===state&&detail.open&&state[section]===ticket;
   let url=null;
   try{
     const voice=isVoice(row);
     let element;
     if(voice||original){
       const blob=await exactMedia(row,alive);if(!blob)return null;
       element=node(voice?'audio':'img');
       if(voice){element.controls=true;element.preload='metadata';OAUI.attr(element,'aria-label','试听原音');}
       if(voice){url=URL.createObjectURL(blob);element.src=url;}
       else element.src=await imageSource(blob);
     }else{
       const src=await cachedCharacterImage(section==='stageSelection'&&!thumbnail?'character_preview':'character_thumbnail',row);
       if(!alive())return null;
       element=node('img');element.src=src;
     }
     if(voice){
       await new Promise((resolve,reject)=>{
         if(element.readyState>=1)resolve();
         else{
           element.addEventListener('loadedmetadata',resolve,{once:true});
           element.addEventListener('error',()=>reject(Error('DIRECTOR_CHARACTER_ORIGINAL_UNAVAILABLE')),{once:true});
         }
       });
     }else{
       element.alt=row.label;
       await imageReady(element);
     }
     if(alive())return {element,url};
     if(url)URL.revokeObjectURL(url);
     return null;
   }catch(error){if(url)URL.revokeObjectURL(url);throw error;}
 }
 function setSurface(state,name,container,result,row){
   const audio=container.querySelector('audio');
   if(audio){audio.pause();audio.removeAttribute('src');audio.load();}
   if(state[name])URL.revokeObjectURL(state[name]);
   state[name]=result.url;container.replaceChildren(result.element);
   container.dataset.previewVersion=row.id;container.dataset.previewSha=row.file.sha256;
 }
 function centerImage(state,row,original=false){
   const ticket=++state.stageSelection;
   picture(state,row,'stageSelection',ticket,original).then(result=>{
     if(!result)return;
     setSurface(state,'stageURL',state.stagePhoto,result,row);state.stageRow=row;
     if(!state.turntable||state.canvas.hidden)OAUI.set(state.legend,
       row.appearance?.format==='full_look'?'整身搭配原图':'登记参考图');
   }).catch(problem=>{if(gearPage===state&&ticket===state.stageSelection)OAUI.set(state.legend,error(problem));});
 }
 function slotPicture(tile,row){
   const box=tile.querySelector('.cl-slot-art');
   if(tile.dataset.cover===(row?.id||''))return;
   thumbnails.unobserve(box);
   tile.dataset.cover=row?.id||'';
   box.replaceChildren();
   if(row&&!isVoice(row)){observed.set(box,row);thumbnails.observe(box);}
   else box.append(node('span','',row?'♫':'·'));
 }
 const currentChoice=rows=>rows.find(row=>row.status==='current')||rows[0];
 function updateSlot(state,key){
   const tile=state.slots.get(key);if(!tile)return;
   const group=key.startsWith('view:')?'base':key;
   const choice=state.worn.get(group)||state.pinned.get(group);
   const entry=key.startsWith('view:')?currentChoice(state.form.rows.filter(row=>row.appearance?.view===key.slice(5))):
     choice||currentChoice(state.form.rows.filter(row=>groupOf(row)===group));
   const label=tile.querySelector('.cl-equipped-name');
   label.textContent=choice&&!key.startsWith('view:')?itemOf(choice):'';
   slotPicture(tile,entry);
 }
 function listFor(state,key){
   const [type,view]=key.split(':');
   const rows=state.form.rows.filter(row=>type==='view'?row.appearance?.view===view:groupOf(row)===type);
   const rank={current:0,candidate:1,historical:2};
   return rows.sort((a,b)=>rank[a.status]-rank[b.status]||
     itemOf(a).localeCompare(itemOf(b))||a.label.localeCompare(b.label));
 }
 function drawOptions(state,key){
   const rows=listFor(state,key),list=state.options;
   for(const art of list.querySelectorAll('.cl-option-thumb'))thumbnails.unobserve(art);
   list.replaceChildren();
   const parts=new Map();
   for(const row of rows){
     const ref=row.appearance?.item_id||row.id;
     if(!parts.has(ref))parts.set(ref,[]);
     parts.get(ref).push(row);
   }
   for(const part of parts.values()){
     if(part.length>1)list.append(node('h4','',itemOf(part[0])));
     for(const row of part){
       const option=button(undefined,()=>previewOption(state,row));
       option.className='cl-asset-choice';option.dataset.asset=row.id;
       const thumb=node('span','cl-option-thumb'),copy=node('span','cl-asset-label');
       OAUI.raw(copy,titleOfStyle(row));option.append(thumb,copy,badge(row));list.append(option);
       if(isVoice(row))thumb.textContent='♫';
       else{observed.set(thumb,row);thumbnails.observe(thumb);}
     }
   }
   if(!rows.length)list.append(node('p','cl-subtitle','还没有资产'));
   list.scrollTop=state.positions.get(key)||0;
   return rows;
 }
 function setSelectedOption(state,row){
   for(const option of state.options.querySelectorAll('[data-asset]'))
     option.setAttribute('aria-pressed',String(option.dataset.asset===row.id));
 }
 function focusModel(state,feature){
   collapseDrawer(state,false);toggleRig(state,'rig');state.turntable.focus(feature);
   state.closeupControls.hidden=false;state.closeupControls.querySelector('button:last-child').focus({preventScroll:true});
 }
 async function focusPhoto(state,row,info){
   if(!info?.region)return;
   state.photoBeforeCloseup??=state.stageRow||standing(state.form.rows);
   state.photoLandmarkRow=row;
   const ticket=++state.stageSelection;
   try{
     const photo=await picture(state,row,'stageSelection',ticket,true);
     if(!photo)return;
     collapseDrawer(state,false);toggleRig(state,'photo');
     const view=state.stagePhoto;
     setSurface(state,'stageURL',view,photo,row);
     const img=photo.element,outer=view.getBoundingClientRect(),shown=img.getBoundingClientRect();
     const ratio=Math.min(shown.width/img.naturalWidth,shown.height/img.naturalHeight);
     const width=img.naturalWidth*ratio,height=img.naturalHeight*ratio;
     const region=info.region;
     const focusX=(shown.width-width)/2+width*(region.x+region.width/2)/10000;
     const focusY=(shown.height-height)/2+height*(region.y+region.height/2)/10000;
     const dx=outer.x+outer.width/2-shown.x-focusX,dy=outer.y+outer.height/2-shown.y-focusY;
     const zoom=Math.min(24,outer.width*.72/(width*region.width/10000),
         outer.height*.72/(height*region.height/10000));
     img.style.transformOrigin=focusX+'px '+focusY+'px';
     img.style.transform='translate('+dx+'px,'+dy+'px) scale('+zoom+')';
     OAUI.set(state.legend,'局部来源图');
     state.closeupControls.hidden=false;
     state.closeupControls.querySelector('button:last-child').focus({preventScroll:true});
   }catch(problem){if(gearPage===state&&ticket===state.stageSelection)OAUI.set(state.legend,error(problem));}
 }
 function focusLandmark(state,feature){
   if(state.turntable){focusModel(state,feature);return;}
   const row=state.photoLandmarkRow;
   if(row)void focusPhoto(state,row,row.appearance.details.find(part=>part.focus===feature));
 }
 function restoreFull(state){
   if(state.turntable)state.turntable.restore();
   else if(state.photoBeforeCloseup){
     centerImage(state,state.photoBeforeCloseup);
     state.photoBeforeCloseup=null;
   }
   state.closeupControls.hidden=true;
   const focusTarget=state.turntable?state.canvas:state.slots.get('features');
   focusTarget?.focus({preventScroll:true});
 }
 function addLandmarks(state,row){
   const focus=state.landmarks;focus.replaceChildren();
   for(const info of row.appearance?.details||[]){
     const visibility=info.visibility==='visible'?'':t(info.visibility==='partial'?'局部不完整':'遮挡');
     const label=[info.name,visibility].filter(Boolean).join(' · ');
     if(info.focus&&state.turntable&&info.visibility!=='covered')
       focus.append(button(info.name,()=>focusModel(state,info.focus)));
     else if(info.region)focus.append(button(info.name,()=>void focusPhoto(state,row,info)));
     else focus.append(node('span','cl-subtitle',label));
   }
 }
 function equivalentLook(state){
   const used=[...state.pinned.values()].filter(row=>gearGroups.includes(groupOf(row))).map(row=>row.id).sort();
   return used.length&&state.form.rows.find(row=>{
     const combination=row.appearance?.combination;
     return combination?.length===used.length&&[...combination].sort().every((id,i)=>id===used[i]);
   });
 }
 async function adoptAssets(state,rows,control){
   const session=pickerSession;
   if(!session||!rows.length||control.disabled)return;
   control.disabled=true;
   try{
     const selected=[];
     for(const row of rows){
       if(state.view.picking&&session.project!==row.file.project_id){
         const imported=await edit('character_import_version',{project_id:session.project,
           origin:{project_id:row.file.project_id,version_id:row.id,sha256:row.file.sha256}});
         if(imported.file?.project_id!==session.project||imported.file.sha256!==row.file.sha256||!imported.version_id)
           throw Error('DIRECTOR_CHARACTER_REFERENCE_MISMATCH');
         selected.push({...row,id:imported.version_id,file:imported.file,...(imported.reference||{})});
       }else{
         if(!isVoice(row))await media('character_thumbnail',row);
         selected.push(row);
       }
       if(gearPage!==state||session!==pickerSession||!detail.open)return;
     }
     session.choose(selected.length===1?selected[0]:selected);
     session.closing=true;closeDetail();picker.close();
   }catch(problem){if(gearPage===state)OAUI.set(state.feedback,error(problem));}
   finally{if(gearPage===state)control.disabled=false;}
 }
 function panelControls(state,row){
   const now=state.selection,alive=()=>gearPage===state&&detail.open&&now===state.selection;
   const voice=isVoice(row),group=groupOf(row),actions=state.actions;
   actions.replaceChildren();
   if(!voice){
     const original=button(row.appearance?.format==='source_detail'?'打开来源原图':'打开原图',async()=>{
       original.disabled=true;
       try{
         const result=await picture(state,row,'selection',now,true);
         if(result)setSurface(state,'photoURL',state.preview,result,row);
       }catch(problem){if(alive())OAUI.set(state.feedback,error(problem));}
       finally{if(alive())original.disabled=false;}
     });
     actions.append(original);
   }
   if(gearGroups.includes(group)&&!state.turntable){
     actions.append(button(state.pinned.get(group)?.id===row.id?'移出搭配':'选入搭配',()=>{
       if(state.pinned.get(group)?.id===row.id)state.pinned.delete(group);else state.pinned.set(group,row);
       updateSlot(state,group);panelControls(state,row);
     }));
   }
   const coordinated=equivalentLook(state);
   if(coordinated&&!state.turntable)actions.append(button('查看整身搭配图',()=>centerImage(state,coordinated)));
   if(group==='wardrobe'&&row.appearance?.set_id){
     const mate=state.form.rows.find(asset=>groupOf(asset)==='accessories'&&asset.appearance?.set_id===row.appearance.set_id);
     if(mate)actions.append(button('查看配套配饰',()=>showOptions(state,'accessories',state.slots.get('accessories'),mate)));
   }
   if(state.view.picking){
     const cross=pickerSession?.project!==row.file.project_id;
     const adopt=button(cross?'引入本项目':voice?'用作镜头声音参考':'用作镜头参考',
                        ()=>adoptAssets(state,[row],adopt));
     actions.append(adopt);
   }else{
     const promote=(label,command,args)=>button(label,async()=>{
       const control=document.activeElement;control.disabled=true;
       try{
         await edit(command,{project_id:row.file.project_id,version_id:row.id,...args});
         if(!alive())return;
         await refresh();
         if(!alive())return;
         const person=state.view.persons.get(state.person.key);
         const updated=person?.forms.flatMap(shape=>shape.rows).find(item=>item.id===row.id);
         if(updated)showDetail(state.view,person,updated,
           [...state.view.grid.children].find(card=>card.dataset.exact===person.key),state.slot);
         else closeDetail();
       }catch(problem){if(alive())OAUI.set(state.feedback,error(problem));}
       finally{if(alive())control.disabled=false;}
     });
     if(row.status!=='current')actions.append(promote(voice?'设为当前声音参考':'设为此用途的当前参考',
       'character_set_current',row.current?{expected_current:row.current}:{}));
     if(!row.primary&&kind(row)==='standard'&&face(row))
       actions.append(promote('设为此形态的主参考','character_set_primary',
         row.primary_version_id?{expected_primary:row.primary_version_id}:{}));
   }
   if(row.crop){
     const source=state.person.forms.flatMap(shape=>shape.rows).find(asset=>asset.id===row.crop.source_version_id);
     if(source)actions.append(button('查看裁切原版',()=>{
       if(source.form.id!==state.form.id)showDetail(state.view,state.person,source,state.trigger,groupOf(source));
       else showOptions(state,groupOf(source),state.slots.get(groupOf(source)),source);
     }));
   }
 }
 function updateApply(state){
   if(!state.apply)return;
   const chosen=state.turntable?state.worn:state.pinned;
   state.apply.hidden=!state.view.picking||!chosen.size;
   state.apply.disabled=!chosen.size;
 }
 function previewOption(state,row){
   if(gearPage!==state)return;
   state.requested=row;
   setSelectedOption(state,row);
   rememberGear(state,row);
   const request=++state.selection,group=groupOf(row),rig=rigOf(row);
   OAUI.set(state.feedback,isVoice(row)?'正在核对原音…':'正在核对原图…');
   state.actions.querySelectorAll('button').forEach(button=>button.disabled=true);
   state.landmarks.querySelectorAll('button').forEach(button=>button.disabled=true);
   picture(state,row,'selection',request).then(result=>{
     if(!result)return;
     setSurface(state,'photoURL',state.preview,result,row);
     state.displayed=row;
     if(state.turntable&&gearGroups.includes(group)&&rig?.rig===state.rig.rig){
       state.turntable.equip(group,rig.part);state.worn.set(group,row);updateSlot(state,group);
       toggleRig(state,'rig');updateApply(state);
     }else if(group==='base'&&!isVoice(row)&&row.appearance?.view!=='asset'){
       toggleRig(state,'photo');centerImage(state,row);
     }else if(!state.turntable&&group==='base'){
       centerImage(state,row);
     }
     OAUI.set(state.inspectorTitle,row.appearance?presentations[row.appearance.format]:isVoice(row)?'声音参考':'登记参考图');
     state.fields.replaceChildren();updateFields(state,row);
     state.landmarks.replaceChildren();addLandmarks(state,row);
     panelControls(state,row);OAUI.set(state.feedback,'');
   }).catch(problem=>{
     if(gearPage!==state||request!==state.selection)return;
     OAUI.set(state.feedback,error(problem));
     state.actions.replaceChildren(button('查看项目设置',()=>{
       closeDetail();if(picker.open)picker.close();void openProjectSettings();
     }));
   });
 }
 function showOptions(state,key,trigger,preferred){
   if(!trigger)return;
   if(state.slot&&state.slot!==key)state.positions.set(state.slot,state.options.scrollTop);
   for(const tile of state.slots.values())tile.setAttribute('aria-expanded','false');
   state.drawer.hidden=false;state.slotButton=trigger;trigger.setAttribute('aria-expanded','true');
   const [group,view]=key.split(':');
   OAUI.set(state.drawerTitle,group==='view'?viewsOfBody[view]:groups[group]);
   const shouldDraw=state.slot!==key||!state.options.children.length;
   state.slot=key;
   const rows=shouldDraw?drawOptions(state,key):listFor(state,key);
   const active=preferred||rows.find(row=>row.id===state.requested?.id)||state.worn.get(group)||currentChoice(rows);
   if(active)previewOption(state,active);else{
     state.selection++;state.preview.replaceChildren();state.fields.replaceChildren();state.actions.replaceChildren();
     state.landmarks.replaceChildren();OAUI.set(state.inspectorTitle,'');OAUI.set(state.feedback,'');
   }
 }
 function equipSlot(state,key,parent){
   const group=key.startsWith('view:')?'base':key;
   const label=group===key?groups[key]:viewsOfBody[key.slice(5)];
   const tile=button(undefined,()=>showOptions(state,key,tile));
   tile.className='cl-slot';tile.dataset.slot=key;
   tile.setAttribute('aria-expanded','false');tile.setAttribute('aria-controls','clEquipmentDrawer');
   tile.append(node('span','cl-slot-art cl-picture'),node('span','cl-slot-label',label),node('small','cl-equipped-name'));
   state.slots.set(key,tile);parent.append(tile);updateSlot(state,key);
 }
 function makeGearPage(view,person,form,trigger){
   const root=$('clDetailContent');
   root.replaceChildren();root.className='cl-detail cl-gear';
   const header=node('header','cl-gear-header'),title=node('h2'),forms=node('nav','cl-forms');
   OAUI.attr(forms,'aria-label','人物形态');OAUI.raw(title,person.character.name);title.id='clDetailTitle';
   const back=button('返回人物库',closeDetail);header.append(back,title,forms);root.append(header);
   for(const shape of person.forms){
     if(person.forms.length===1)break;
     const tab=button(shape.name,()=>showDetail(view,person,standing(shape.rows),trigger));
     tab.dataset.form=shape.id;tab.setAttribute('aria-pressed',String(shape.id===form.id));forms.append(tab);
   }
   const top=node('nav','cl-top-slots'),left=node('nav','cl-side-slots'),right=node('nav','cl-side-slots'),
     middle=node('main','cl-gear-middle'),stage=node('div','cl-gear-stage'),
     stagePhoto=node('div','cl-stage-photo'),canvas=node('canvas','cl-turntable'),legend=node('output','cl-stage-legend'),
     bio=node('footer','cl-person-profile'),actionsTop=node('div','cl-stage-actions');
   OAUI.attr(top,'aria-label','人物视图');OAUI.attr(left,'aria-label','人物部位');OAUI.attr(right,'aria-label','服饰与声音');
   OAUI.attr(canvas,'aria-label','3D 人物，左右拖动或方向键旋转');canvas.tabIndex=0;canvas.hidden=true;
   const rigToggle=button('返回 3D 试穿',()=>{if(state.canvas.hidden)toggleRig(state,'rig');else toggleRig(state,'photo');});
   const apply=button('将搭配用作镜头参考',()=>{
     const source=state.turntable?state.worn:state.pinned;
     const basis=state.rigRow||standing(form.rows);
     const rows=[basis,...source.values()].filter((row,index,all)=>row&&!isVoice(row)
       &&all.findIndex(other=>other?.id===row.id)===index);
     void adoptAssets(state,rows,apply);
   });
   const closeupControls=node('div','cl-closeup-tools');
   closeupControls.hidden=true;
   closeupControls.append(button('左眼',()=>focusLandmark(state,'left-eye')),
     button('右眼',()=>focusLandmark(state,'right-eye')),button('全身',()=>restoreFull(state)));
   actionsTop.append(rigToggle,apply,closeupControls);
   stage.append(stagePhoto,canvas,legend,actionsTop);middle.append(stage,bio);
   const heading=node('strong');OAUI.raw(heading,person.character.name);bio.append(heading);
   const data=node('dl'),profile=person.profile;
   for(const [field,label] of Object.entries({height:'身高',blood_type:'血型',zodiac:'星座',mbti:'MBTI',personality:'性格'})){
     if(profile[field]){const note=node('dd');OAUI.raw(note,profile[field]);data.append(node('dt','',label),note);}
   }
   if(data.children.length)bio.append(data);
   const body=node('div','cl-gear-body');body.append(left,middle,right);
   const drawer=node('section','cl-equipment-drawer'),head=node('header','cl-dialog-head'),
     drawerTitle=node('h3'),options=node('div','cl-asset-lists'),inspector=node('div','cl-original'),
     inspectorTitle=node('h4'),preview=node('div','cl-inspector-preview'),fields=node('dl','cl-detail-fields'),
     landmarks=node('div','cl-actions cl-landmarks'),actions=node('div','cl-actions'),
     feedback=node('p','cl-subtitle');
   drawer.id='clEquipmentDrawer';drawer.hidden=true;drawerTitle.id='clEquipmentTitle';
   drawer.setAttribute('aria-labelledby','clEquipmentTitle');
   feedback.setAttribute('role','status');options.tabIndex=-1;
   head.append(drawerTitle,button('收起款式',()=>collapseDrawer(state)));
   const panes=node('div','cl-drawer-panes');
   inspector.append(inspectorTitle,preview,landmarks,fields,feedback,actions);panes.append(options,inspector);
   drawer.append(head,panes);root.append(top,body,drawer);
   const rigRow=form.rows.find(row=>rigOf(row)?.part==='body');
   const state={root,view,person,form,trigger,slots:new Map(),positions:new Map(),drawer,drawerTitle,
     options,preview,fields,landmarks,actions,feedback,inspectorTitle,canvas,stagePhoto,legend,rigToggle,
     selection:0,stageSelection:0,worn:new Map(),pinned:new Map(),apply,closeupControls,rigRow,rig:rigOf(rigRow)};
   for(const key of Object.keys(viewsOfBody))if(form.rows.some(row=>row.appearance?.view===key))
     equipSlot(state,'view:'+key,top);
   for(const group of ['base','features','hair'])equipSlot(state,group,left);
   for(const group of ['wardrobe','accessories','voice'])equipSlot(state,group,right);
   const base=standing(form.rows);
   if(rigRow&&typeof OACharacterTurntable==='function'){
     state.turntable=OACharacterTurntable(canvas);
     const defaults={hair:'hair-silver',wardrobe:'wardrobe-training',accessories:'accessories-none'};
     for(const group of gearGroups){
       const usable=form.rows.filter(row=>groupOf(row)===group&&rigOf(row)?.rig===state.rig.rig);
       const chosen=usable.find(row=>row.status==='current')||usable.find(row=>rigOf(row).part===defaults[group]);
       if(chosen){state.worn.set(group,chosen);state.turntable.equip(group,rigOf(chosen).part);updateSlot(state,group);}
     }
     toggleRig(state,'rig');
     if(base&&!isVoice(base))centerImage(state,base);
   }else{
     toggleRig(state,'photo');
     if(base&&!isVoice(base))centerImage(state,base);
     else if(base)OAUI.set(legend,'声音参考');
   }
   updateApply(state);
   return {state,back};
 }
 const browseGroups={
   base:'人物基础',features:'五官',torso:'躯干',limbs:'四肢',details:'手脚与姿势',voice:'声音'
 };
 const referenceGroup=row=>row.browseNote?.group||(row.use==='pose'&&groupOf(row)==='base'?'details':groupOf(row));
 const browseGroup=row=>row.browseArchived?'history':referenceGroup(row);
 const hasStagePreview=row=>!!row.browseNote?.provenance||registeredFullLook(row);
 function browseKind(row,region){
   if(region||row.crop)return '原图局部';
   if(row.browseNote?.provenance)return row.browseNote.provenance.treatment==='source_upscale'?'原图超分':'生成近照 · 超分';
   if(isVoice(row))return '原音';
   if(row.appearance?.format==='combined')return browseGroup(row)==='accessories'?'配饰合图':'合图';
   return row.appearance?.format==='full_look'?'整身搭配原图':'独立原图';
 }
 function browseEntry(rows,row,part){
   const source=rows.find(value=>value.id===row.crop?.source_version_id)||row;
   return {row,source,key:part?JSON.stringify([row.id,part.name,part.region]):row.id,
     label:part?.name||row.browseNote?.label||row.label,part,region:part?.region||row.crop};
 }
 function browseRegionBox(width,height,region){
   const ratio=region.source_version_id?1:10000;
   const box=region.source_version_id?[region.x,region.y,region.width,region.height]:
     [region.x*width/ratio,region.y*height/ratio,region.width*width/ratio,region.height*height/ratio];
   const [x,y,w,h]=box;
   if(x<0||y<0||w<=0||h<=0||x+w>width+.001||y+h>height+.001)throw Error('DIRECTOR_CHARACTER_CROP_INVALID');
   return box;
 }
 function browseCrop(image,region){
   const {naturalWidth:width,naturalHeight:height}=image;
   const box=browseRegionBox(width,height,region);
   const svg=document.createElementNS('http://www.w3.org/2000/svg','svg');
   svg.setAttribute('viewBox',box.join(' '));svg.setAttribute('role','img');
   svg.setAttribute('aria-label',image.alt);
   const body=document.createElementNS(svg.namespaceURI,'image');
   body.setAttribute('href',image.src);body.setAttribute('width',width);body.setAttribute('height',height);
   svg.append(body);return svg;
 }
 function browseReflect(state){
   const displayed=state.displayed;
   for(const option of state.root.querySelectorAll('[data-choice]'))
     option.setAttribute('aria-pressed',String(option.dataset.choice===(displayed?.figure?.key||displayed?.key)));
   const choice=displayed?.row;
   for(const [type,control] of state.lookTriggers){
     const groups=type==='hair'?['hair']:['wardrobe','accessories'];
     const matches=choice&&groups.includes(browseGroup(choice));
     control.dataset.selectedVersion=matches?choice.id:'';
     if(matches)control.setAttribute('aria-description',itemOf(choice));
     else control.removeAttribute('aria-description');
   }
   paintExhibit(state);
 }
 async function browseSelect(state,entry,whole=false){
   if(gearPage!==state||!entry)return;
   const ticket=++state.stageSelection;
   const alive=()=>gearPage===state&&state.stageSelection===ticket;
   const staged=whole?{...entry,region:null,whole:true}:entry;
   state.requested=entry;
   state.retryWhole=whole;
   state.retryBrowse.hidden=true;
   state.originalButton.hidden=true;state.cropButton.hidden=true;
   if(state.displayed?.key!==entry.key){
     if(state.stageURL)URL.revokeObjectURL(state.stageURL);
     state.stageURL=null;state.stagePhoto.replaceChildren();state.displayed=null;
     state.stagePhoto.removeAttribute('data-preview-version');
     state.stagePhoto.removeAttribute('data-display-kind');
     state.ruler?.selectImage(null);
   }
   OAUI.set(state.feedback,isVoice(entry.row)?'正在读取原音…':'正在读取原图…');
   const voice=isVoice(entry.row);
   const wantsExact=voice||whole||!!staged.region&&!staged.shelfPart||!hasStagePreview(entry.row);
   let landed=false;
   function show(result,exact,problem,pending=false){
     if(!result||!alive())return;
     const width=result.element.naturalWidth,height=result.element.naturalHeight;
     const region=staged.region&&(exact||!staged.region.source_version_id)?staged.region:null;
     if(region)result.element.alt=entry.label;
     const element=region?browseCrop(result.element,region):result.element;
     setSurface(state,'stageURL',state.stagePhoto,{...result,element},staged.source);
     state.stagePhoto.dataset.previewVersion=entry.row.id;
     state.stagePhoto.dataset.sourceVersion=staged.source.id;
     state.stagePhoto.dataset.view=region?'crop':'original';
     state.stagePhoto.dataset.displayKind=voice?'audio':exact?'original':'preview';
     const size=width&&height?width+' × '+height:'';
     state.stagePhoto.dataset.imageSize=size;
     state.displayed=staged;
     state.ruler?.selectImage(staged.region||staged.temporary?null:staged.source,element);
     if(state.compareOnLoad&&!pending){
       state.compareOnLoad=false;
       state.ruler?.setCompare(true);
     }
     if(!staged.temporary)rememberGear(state,staged.figure?.row||entry.row);
     OAUI.set(state.stageTitle,whole?entry.source.browseNote?.label||entry.source.label:entry.label);
     const provenance=entry.row.browseNote?.provenance;
     const badge=entry.row.browseArchived?'历史参考':provenance?.confirmation==='reference'?'原始基准参考':
       provenance?.confirmation==='unconfirmed'||registeredFullLook(entry.row)&&entry.row.status==='candidate'?'待审':stateText[entry.row.status];
     const isBaseline=entry.row.id===state.form.guide?.baseline;
     const purpose=entry.shelfPart?'配饰原图局部':lookPurpose(entry.row);
     const format=voice?'原音':!exact?'预览':whole?'独立原图':browseKind(entry.row,region);
     const labels=[purpose,format,size,badge,isBaseline?'比对基准':null].filter(Boolean);
     OAUI.set(state.stageKind,'{0}',OAUI.list([...new Set(labels)]));
     const note=(whole?entry.source:entry.row).browseNote?.note;
     const origin=entry.region&&!whole?(entry.source.browseNote?.label||entry.source.label):entry.source.source;
     const lines=[origin&&OAUI.message('来源 {0}',origin),note&&(!isBaseline||note!=='比对基准')?note:null].filter(Boolean);
     OAUI.set(state.guideSelection,'{0}',lines);state.guideSelection.hidden=!lines.length;
     const hasHDOriginal=hasStagePreview(entry.row);
     OAUI.set(state.originalButton,provenance?'查看 4K 原件':'查看原图');
     OAUI.set(state.cropButton,hasHDOriginal?'返回预览':'返回局部');
     state.originalButton.hidden=voice||pending||exact&&(!entry.region||whole);
     state.cropButton.hidden=!(entry.region||hasHDOriginal)||!whole;
     if(!state.fields.hidden)browseFields(state,entry.row);
     browseReflect(state);
     if(problem)OAUI.set(state.feedback,'已显示 {0} 预览。{1}',size,OAUI.message(error(problem)));
     else OAUI.set(state.feedback,pending?'正在读取原图，先显示预览。':
       entry.missingLook?'此视角暂无整套图，显示此方向原图。':
       entry.part?.visibility==='partial'?'此部位在原图中有遮挡。':'');
     state.retryBrowse.hidden=!problem;
   }
   const load=exact=>picture(state,staged.source,'stageSelection',ticket,exact);
   let result;
   try{
     if(entry.row.crop&&entry.source===entry.row)throw Error('DIRECTOR_CHARACTER_ORIGINAL_MISSING');
     if(voice){show(await load(true),true);return true;}
     const preview=load(false).catch(problem=>{
       if(!alive())return null;
       return picture(state,staged.source,'stageSelection',ticket,false,true).catch(()=>{throw problem;});
     }).then(value=>({value}),problem=>({problem}));
     if(!wantsExact){
       const {value,problem}=await preview;
       if(!problem){show(value,false);return true;}
       result=await load(true);show(result,true);
       return true;
     }
     void preview.then(({value})=>{if(!landed&&alive()&&value)show(value,false,null,true);}).catch(()=>{});
     try{
       result=await load(true);
       landed=true;
       show(result,true);
     }catch(problem){
       landed=true;
       if(!alive())return;
       const {value}=await preview;
       if(!value)throw problem;
       show(value,false,problem);
     }
     return true;
   }catch(problem){
     if(result?.url&&result.url!==state.stageURL)URL.revokeObjectURL(result.url);
     if(alive()){OAUI.set(state.feedback,error(problem));state.retryBrowse.hidden=false;return false;}
   }
 }
 function browseFields(state,row){
   state.fields.replaceChildren();
   updateFields(state,row);
   if(row.browseNote){
     state.fields.append(node('dt','','附件标注'),node('dd','',row.browseNote.caption),
       node('dt','','校对备注'),node('dd','',row.browseNote.note));
   }
   const provenance=row.browseNote?.provenance;
   if(provenance){
     const pairs=[['处理方式',browseKind(row)],['确认状态',provenance.confirmation==='reference'?'原始基准参考':'待审'],
       ['上游原件',provenance.source_name],['上游原件 SHA-256',provenance.source_sha256],['放大记录',provenance.restoration]];
     if(provenance.source_box)pairs.push(['上游取景（x, y, 宽, 高）',provenance.source_box.join(', ')]);
     for(const [label,value] of pairs)state.fields.append(node('dt','',label),node('dd','',value));
   }
   const components=row.appearance?.details?.filter(part=>!part.region);
   if(components?.length){
     state.fields.append(node('dt','','图中部件'),node('dd','',components.map(part=>part.name).join('、')));
   }
 }
 function browseThumb(row,cls='cl-picture'){
   const thumb=node('span',cls);
   if(row&&!isVoice(row)){observed.set(thumb,row);thumbnails.observe(thumb);}
   else OAUI.set(thumb,row?'♫':'—');
   return thumb;
 }
 const lookLabels={hair:'发型',wardrobe:'服装与配饰'};
 function lookPurpose(row){
   if(acceptedFullLook(row))return '已采用整身造型';
   if(registeredFullLook(row))return '完整造型候选';
   const group=browseGroup(row);
   if(group==='hair')return '发型参考图';
   if(group==='wardrobe')return '服装单品';
   if(group==='accessories')return row.appearance?.format==='combined'?'配饰合图':'配饰单品';
   return '';
 }
 function closeLook(state,focus=true){
   if(!state.lookPicker.hidden){
     state.lookPicker.hidden=true;
     const trigger=state.lookTriggers.get(state.lookType);
     trigger?.setAttribute('aria-expanded','false');
     if(focus){
       state.layout.scrollTop=state.lookScrollTop;
       trigger?.focus({preventScroll:true});
     }
   }
 }
 function showFrontFigure(state){
   const baseline=browseHome(state.form);
   if(baseline)return visitBrowse(state,browseEntry(state.rows,baseline),null);
 }
 const figureAngles=['front','three_quarter','side','back'];
 function figureAngle(entry){
   const row=entry?.row;
   if(!row||entry.region||row.browseArchived||row.use!=='full_body')return '';
   const view=row.appearance?.view;
   return figureAngles.includes(view)?view:entry.fallbackFront===true?'front':'';
 }
 function wardrobeFigures(form,wardrobe){
   return form.looks.filter(row=>row.appearance.combination.includes(wardrobe.id))
     .filter(row=>figureAngles.includes(row.appearance.view))
     .sort((a,b)=>Number(acceptedFullLook(b))-Number(acceptedFullLook(a)));
 }
 function makeLookCard(state,entry){
   const row=entry.row;
   const card=node('section','cl-look-card');
   const action=button(undefined,()=>{
     closeLook(state);
     void visitBrowse(state,entry);
   });
   action.className='cl-look-choice';action.dataset.lookVersion=entry.key;
   action.setAttribute('aria-pressed',String(state.displayed?.key===entry.key));
   const name=entry.label,purpose=lookPurpose(row)||browseKind(row);
   const copy=node('span');copy.append(node('span','',name),node('small','cl-look-purpose',purpose));
   OAUI.attr(action,'aria-label','{0} · {1}',OAUI.message(name),OAUI.message(purpose));
   const art=node('span','cl-picture');
   art.append(ringSymbol(browseGroup(row)==='hair'?'hair':'hand'));
   const cached=browseImageCache.get('character_preview:'+exactKey(row));
   cached?.then(src=>{
     if(!art.isConnected)return;
     const preview=node('img');preview.alt='';preview.src=src;art.replaceChildren(preview);
   }).catch(()=>{});
   action.append(art,copy);card.append(action);
   return card;
 }
 function openLook(state,type){
   if(!state.lookPicker.hidden&&state.lookType===type){closeLook(state);return;}
   closeLook(state,false);
   const entries=state.form.rows.filter(row=>browseGroup(row)==='hair'&&!row.browseArchived).map(row=>browseEntry(state.rows,row));
   const visible=entries.map(entry=>makeLookCard(state,entry));
   state.lookChoices.replaceChildren(...(visible.length?visible:[node('p','cl-subtitle','这类素材尚未登记。')]));
   state.info.hidden=true;state.fields.hidden=true;state.inspect.setAttribute('aria-expanded','false');
   closeBrowseSupplement(state);
   state.lookScrollTop=state.layout.scrollTop;
   state.lookType=type;state.lookPicker.hidden=false;
   state.lookTriggers.get(type)?.setAttribute('aria-expanded','true');
   OAUI.set(state.lookTitle,lookLabels[type]);
   state.lookChoices.querySelector('[aria-pressed=true],button')?.focus({preventScroll:true});
 }
 function basicFigure(state,entry){
   if(entry.row.id!==browseHome(state.form)?.id||entry.row.appearance?.view)return entry;
   return {...entry,fallbackFront:true};
 }
 function presentFigure(state,entry){
   const figure=basicFigure(state,entry),angle=figureAngle(figure);
   const outfit=state.wardrobe;
   const look=outfit&&wardrobeFigures(state.form,outfit).find(row=>row.appearance.view===angle);
   state.figureRequest=figure;
   return browseSelect(state,{...(look?browseEntry(state.rows,look):figure),figure,
     wardrobe:outfit,missingLook:!!outfit&&!look});
 }
 function visitBrowse(state,entry,outfit=state.wardrobe){
   closeBrowseLayers(state);
   state.wardrobe=outfit;
   if(figureAngle(basicFigure(state,entry)))return presentFigure(state,entry);
   state.figureRequest=null;
   state.exhibitOpen=false;paintExhibit(state);
   return browseSelect(state,entry);
 }
 function peekReference(state,entry,shelfPart=false,exhibitItem){
   closeBrowseLayers(state);
   if(!state.figureRequest)return;
   return browseSelect(state,{...entry,figure:state.figureRequest,temporary:true,shelfPart,exhibitItem});
 }
 function chosenOutfit(state){
   return [state.wardrobe,...state.wardrobeRows].find(row=>row&&wardrobeFigures(state.form,row).some(look=>look.appearance.view==='front'));
 }
 function isCompleteLook(entry){
   return !!entry&&!entry.temporary&&figureAngle(entry.figure)==='front'&&registeredFullLook(entry.row);
 }
 function toggleCompleteLook(state){
   const entry=state.figureEntries.find(candidate=>figureAngle(candidate)==='front');
   if(entry&&isCompleteLook(state.requested))return visitBrowse(state,entry,null);
   const outfit=chosenOutfit(state);
   if(outfit&&entry)return visitBrowse(state,entry,outfit);
 }
 function closeBrowseLayers(state,restoreReference=false){
   closeLook(state,false);
   closeBrowseSupplement(state);
   state.info.hidden=true;state.fields.hidden=true;state.inspect.setAttribute('aria-expanded','false');
   state.tooltip.hidden=true;state.tooltipOwner=null;
   if(restoreReference&&state.requested?.temporary&&state.figureRequest)
     void presentFigure(state,state.figureRequest);
 }
 function wardrobeParts(state){
   const choices=state.form.rows.filter(row=>!row.browseArchived);
   state.wardrobeRows=choices.filter(row=>browseGroup(row)==='wardrobe');
   const references=new Map();
   for(const row of choices.filter(row=>browseGroup(row)==='accessories')){
     const key=accessorySheetKey(row)||row.id;
     const record=references.get(key);
     if(record){
       record.parts.push(...(row.appearance?.details||[]));
       if(row.browseNote||row.id===row.appearance?.item_id)record.row=row;
     }else references.set(key,{row,parts:[...(row.appearance?.details||[])]});
   }
   return references;
 }
 let exhibitClipID=0;
 function exhibitArt(item){
   const space='http://www.w3.org/2000/svg';
   const make=name=>document.createElementNS(space,name);
   const svg=make('svg'),picture=make('image'),group=make('g');
   const [x,y,w,h]=item.source_box;
   const cx=x+w/2,cy=y+h/2;
   svg.setAttribute('viewBox',(item.rotate?[cx-h/2,cy-w/2,h,w]:item.source_box).join(' '));
   svg.setAttribute('aria-hidden','true');
   if(item.rotate)group.setAttribute('transform','rotate('+item.rotate+' '+cx+' '+cy+')');
   const hit=make(item.outline?'path':'rect');
   if(item.outline){
     const defs=make('defs'),clip=make('clipPath'),path=make('path');
     const id='character-exhibit-'+(++exhibitClipID);
     clip.id=id;path.setAttribute('d',item.outline);path.setAttribute('clip-rule','evenodd');
     clip.append(path);defs.append(clip);svg.append(defs);
     picture.setAttribute('clip-path','url(#'+id+')');
     hit.setAttribute('d',item.outline);hit.setAttribute('fill-rule','evenodd');
   }else for(const [name,value] of Object.entries({x,y,width:w,height:h}))hit.setAttribute(name,value);
   hit.classList.add('cl-exhibit-hit');
   hit.setAttribute('fill','transparent');hit.setAttribute('stroke','transparent');hit.setAttribute('stroke-width','11');
   picture.setAttribute('width','720');picture.setAttribute('height','720');
   picture.setAttribute('preserveAspectRatio','none');
   group.append(picture,hit);svg.append(group);
   return {svg,picture};
 }
 function buildExhibit(state){
   const references=wardrobeParts(state);
   const display=state.form.guide?.wardrobe_display;
   const groups=state.exhibitGroups;
   const append=(item,row,part)=>{
     const entry={...browseEntry(state.rows,row,part),label:item.label};
     const control=button(undefined,()=>void peekReference(state,entry,!!part,item.id));
     control.className='cl-exhibit-piece';control.dataset.shelfChoice=item.id;
     control.disabled=true;control.setAttribute('aria-pressed','false');
     const [x,y,w,h]=item.display_box.map(value=>value/10+'%');
     Object.assign(control.style,{left:x,top:y,width:w,height:h});
     nameRingButton(state,control,item.label);
     const {svg,picture}=exhibitArt(item);
     if(item.hanger){
       const hanger=node('span','cl-hanger');
       hanger.setAttribute('aria-hidden','true');
       const [,top,,height]=item.display_box;
       hanger.style.setProperty('--cl-hanger-drop',Math.max(0,(top-90)*100/height)+'%');
       control.append(hanger);
     }
     control.append(svg);groups[item.group].append(control);
     state.exhibitItems.push({control,picture,row});
   };
   if(display?.length){
     for(const item of display){
       const row=state.form.rows.find(candidate=>candidate.id===item.asset.version);
       if(!row)continue;
       const part=item.part&&references.get(accessorySheetKey(row)||row.id)?.parts.find(value=>value.name===item.part);
       if(item.part&&!part)continue;
       append(item,row,part||null);
     }
     return;
   }
   const all=state.wardrobeRows.map(row=>({row,group:'wardrobe'}));
   for(const {row,parts} of references.values()){
     const distinct=[...new Map(parts.filter(part=>part.region).map(part=>[part.name,part])).values()];
     if(distinct.length)all.push(...distinct.map(part=>({row,part,group:'accessories'})));
     else all.push({row,group:'accessories'});
   }
   const columns=all.length<5?2:3,rows=Math.ceil(all.length/columns);
   const width=Math.floor(460/columns),height=Math.min(350,Math.floor(790/Math.max(1,rows)));
   all.forEach(({row,part,group},i)=>{
     const region=part?.region;
     const source=region?[region.x,region.y,region.width,region.height].map(value=>value*.072):[0,0,720,720];
     append({id:row.id+(part?'-'+i:''),label:part?.name||itemOf(row),group,source_box:source,
       display_box:[30+(i%columns)*width,135+Math.floor(i/columns)*height,width-10,height-10]},row,part);
   });
 }
 function warmExhibit(state){
   if(state.exhibitWarming)return;
   state.exhibitWarming=true;
   const buckets=new Map();
   for(const item of state.exhibitItems){
     const key=exactKey(item.row);
     if(!buckets.has(key))buckets.set(key,[]);
     buckets.get(key).push(item);
   }
   for(const items of buckets.values()){
     const action=hasStagePreview(items[0].row)?'character_preview':'character_thumbnail';
     cachedCharacterImage(action,items[0].row).then(async src=>{
       const source=node('img');source.src=src;await imageReady(source);
       if(gearPage!==state)return;
       for(const item of items){item.picture.setAttribute('href',src);item.control.dataset.artReady='true';}
     }).catch(()=>{
       if(gearPage===state)state.exhibitWarming=false;
     });
   }
 }
 function paintExhibit(state){
   const shown=state.displayed,angle=figureAngle(shown?.figure);
   const control=state.lookTriggers.get('wardrobe'),ready=!!angle&&!!state.figureRequest&&!!state.exhibitItems.length;
   const active=ready&&state.exhibitOpen;
   control.disabled=!ready&&control.dataset.missing!=='true';
   control.setAttribute('aria-expanded',String(active));
   state.exhibit.inert=!active;
   state.exhibit.setAttribute('aria-hidden',String(!active));
   state.stage.dataset.displayOpen=String(active);
   state.stage.dataset.figureAngle=angle;
   state.stage.dataset.reference=String(!!shown?.temporary);
   state.shelfReturn.hidden=!shown?.temporary;
   state.fullTool.disabled=!chosenOutfit(state);
   state.fullTool.setAttribute('aria-pressed',String(isCompleteLook(shown)));
   for(const item of state.exhibitItems){
     item.control.disabled=!active;
     item.control.setAttribute('aria-pressed',String(shown?.exhibitItem===item.control.dataset.shelfChoice));
   }
   if(ready)warmExhibit(state);
 }
 const ringSides=['north','east','south','west'];
 // The reference views and body regions already used by the character library.
 // Each form keeps these positions even if only some of the sources are registered.
 const ringSlots={
   base:[['正面全身标准','front','front'],['全身斜侧面','three_quarter','three_quarter'],
     ['全身正侧面','side','side'],['全身背面','back','back'],['无面全身','body_blank','body_blank'],
     ['无头正面身体','headless']],
   features:[['独立头部','head','head_front'],['光头无面头模','headBlank','head_blank'],
     ['侧面脸部','profile'],['眼睛','eyes'],['左眼','eye',null,-1],['右眼','eye',null,1],
     ['瞳孔与虹膜','iris'],['鼻子','nose'],['嘴唇','mouth'],
     ['人物右耳（发丝遮挡）','earCovered',null,1],['人物左耳（画面右）','ear',null,-1],
     ['人物右耳（画面左）','ear',null,1]],
   torso:[['上身正面','torso'],['上身背面','torsoBack'],['侧面胸部轮廓','chestSide'],
     ['腹部正面','waist'],['腹部侧面','abdomenSide'],['后腰背面','waistBack'],['侧面臀部轮廓','hip']],
   limbs:[['左臂正面','arm',null,-1],['右臂正面','arm',null,1],
     ['左腿正面','leg',null,-1],['右腿正面','leg',null,1]],
   details:[['人物左手（画面右）','hand',null,-1],['人物右手（画面左）','hand',null,1],
     ['双手手背俯视','handsBack'],['双手手心俯视','handsPalm'],['正面双脚','feetFront'],
     ['双脚脚面俯视','feetTop'],['侧面脚部','foot'],['双脚脚跟背面','heels']],
   voice:[['声音','voice']],
 };
 // Each 32-unit illustration has an outlined silhouette, a shadow shape,
 // and optional engraving lines. The filled forms read at ring size.
 const ringIllustrations={
   front:[
     'M16 2.5c2.7 0 4.1 2 3.7 4.7-.2 1.7-1 2.7-2.1 3.3v1.4l4.4 1.6c1.2.4 1.8 1.6 2 3l1.1 6.1-1.9.6-2.2-5.7-.8 3.2 1 8.6-2.4.3-2.8-7.8-2.8 7.8-2.4-.3 1-8.6-.8-3.2-2.2 5.7-1.9-.6 1.1-6.1c.2-1.4.8-2.6 2-3l4.4-1.6v-1.4c-1.1-.6-1.9-1.6-2.1-3.3-.4-2.7 1-4.7 3.7-4.7Z',
     'M12.3 6.4c0-2.4 1.5-3.9 3.7-3.9 2.3 0 3.7 1.5 3.7 4-2-1.9-4.6-.6-7.4-.1Zm-.5 10.7 4.2-1.2 4.2 1.2-.2 2.1h-8Zm.2 3.2h8l.4 3.4-3.8.4-.6-2.3-.6 2.3-3.8-.4Z',
     'M14.1 7.1h.7m2.4 0h.7m-2.6 1.7h1.4'],
   three_quarter:[
     'M16.7 2.3c2.9-.5 4.6 1.1 5 3.2l1.3 1.8-1.5.6c-.2 1.4-1.1 2.3-2.2 2.6l-.2 1.3 3 1.4c1.3.9 1.8 2.2 1.9 3.9l.8 5-1.9.6-1.7-5-1.6 2.8.8 8.8-2.5.4-2.2-7.2-2.1 5.5-2.9 1.6-1.4-1.8 1.7-1.9 1.3-5.5-.4-3-2.2 5.1-2.1-.9 1.4-6.4c.5-1.8 2-2.6 4.4-3.2l1.5-.4.5-1.5c-1.4-.7-2.6-1.7-2.7-3.3-.5-2.1 1.1-4 4-4.5Z',
     'M12.7 6.6c-.3-2.3 1.4-4 3.9-4.3 2.7-.4 4.2.6 4.9 2.5-2.3-.6-4.6 1.1-5.8 3.7l-.2 1.5c-1.6-.6-2.4-1.6-2.8-3.4ZM11.9 16.6l7.4-2.1 1.9 2.2-1.1 2.7-7.9.7Zm.3 3.7 7.4-.1.4 3.5-4.1.4-.5-1.4-.7 1.8-3.4-.1Z',
     'M19.1 6.6h.9m-1.3 2.1 1 .2'],
   side:[
     'M15.1 2.5c2.7-.2 4.2 1.4 4.4 3.7L22 8l-1.8.8-.1 1.4-2.5.5-.1 1.6c1.6.6 2.6 1.8 3.1 3.4l1.8 4-1.1 1.5-3.4-3.2.7 6.9-.1 2.5 2.5.8.1 1.2h-5.4l-.8-6-.9-2.7-.4 4.2-1.4 3.9H9.6l1.2-3.9.4-6.7c-.7-1.6-1-3.2-.4-4.5.5-1 1.4-1.7 2.6-2.5l.2-1.3c-1.8-.4-2.4-2.2-2.4-3.8 0-2.2 1.4-3.5 3.9-3.6Z',
     'M11.4 6.6c-.3-2.6 1.3-4 3.8-4.1 2.3-.1 3.7 1 4.1 2.9-1.8-.4-2.6.6-3.2 2.5-.5 1.8-1.5 3.4-3.4 4.2l1-2.2c-1.3-.5-2.2-1.6-2.3-3.3ZM11.2 15.8l6.5-1.5 1.9 2.4-2.5 2.1-5.7.6Zm.2 4.7 6.6-.2.3 3.8-3.3.1-1.1-3-.5 3.5-2.4-.2Z',
     'M17.9 6.8h.9'],
   back:[
     'M16 2.3c2.8 0 4.4 1.8 4.4 4.3 0 2-1.1 3.2-2.3 3.9v1.2l5.1 1.2c1.8.5 2 2.5 2.4 4l.8 5.1-2 .6-2.6-5.8-1 3.3 1 8.1-2.5.8-3.3-7.5-3.3 7.5-2.5-.8 1-8.1-1-3.3-2.6 5.8-2-.6.8-5.1c.4-1.5.6-3.5 2.4-4l5.1-1.2v-1.2c-1.2-.7-2.3-1.9-2.3-3.9 0-2.5 1.6-4.3 4.4-4.3Z',
     'M16 2.3c2.8 0 4.4 1.8 4.4 4.3v2l.5 2.1-2.7-.8L16 12l-2.2-2.1-2.7.8.5-2.1v-2c0-2.5 1.6-4.3 4.4-4.3ZM11.1 16.8l4.9 1 4.9-1-.9 2.5-4 .9-4-.9Zm.2 3.9h9.4l.2 3.3-4-.3-.9-2.5-.9 2.5-4 .3Z',
     'M13 6c.3 1.4.9 2.1 1.9 2.7m4-3c0 1.4-.6 2.4-1.6 3.1m-1.3 3.6v4.1m-4.3-3.1 2.1 1m6.5-1-2.1 1'],
   body_blank:[
     'M16 2.4a3.5 3.5 0 0 1 3.5 3.7c0 2-.7 3.2-2 4.2v1l5 1.6c1 0 1.9 1 2 2.2l1.5 8.5-1.9.5-2.8-6.4-1.1 3 1 8.3-2.3.5-3.2-7.4-3.2 7.4-2.3-.5 1-8.3-1.1-3-2.8 6.4-1.9-.5 1.5-8.5c.1-1.2 1-2.2 2-2.2l5-1.6v-1c-1.3-1-2-2.2-2-4.2A3.5 3.5 0 0 1 16 2.4Z',
     'M17 3.1c1.9.6 2.5 2 2.5 3.5-.1 1.7-.8 2.8-2 3.7v1l5 1.6.8 1.3-3.2 2.2-1.3 4.3 1 8.6-.9.2-3.2-7.4.1-5.3 1.6-4.7-.8-2.2c1.1-1.6 1.3-4.4.4-6.8Z',
     'M11.5 15.3c2.7 1.2 6.4 1.2 9 0'],
   headless:[
     'M12 3h8l-.2 2.4 5.2 2.7c1.2.7 1.6 1.8 1.8 3.3l1 8.6-2.3.6-2.4-7-1.6 4.7 2 5.9 1 4.3H7.5l1-4.3 2-5.9L9 13.6l-2.4 7-2.3-.6 1-8.6c.2-1.5.6-2.6 1.8-3.3l5.1-2.7Z',
     'M12 3h8l-.2 2.4a10 10 0 0 1-7.6 0ZM9.3 12.7c2.9-.9 5.7-.6 6.7 1 1-1.6 3.8-1.9 6.7-1l-1.1 4H10.4ZM8.5 24.3h15l1 4.2h-17Z',
     'M12 8.7 16 10l4-1.3m-4 10h.1'],
   body:[
     'M12 4h8l.2 2.8 6 2.5 2.3 9-2.6 1-3.1-4-1.7 5 2 7.4H8.9l2-7.4-1.7-5-3.1 4-2.6-1 2.3-9 6-2.5Z',
     'M20 4l.2 2.8 6 2.5 2.3 9-2.6 1-3.1-4-1.7 5 2 7.4h-4.7l-.9-7.4 2.8-8-4.3-2.5Z',
     'M10.2 14c2-.8 3.7-.5 5.8.5 2.1-1 3.8-1.3 5.8-.5'],
   overview:[
     'M9 5.5c2 0 2.9 1.5 2.7 3.2-.2 1.3-.5 2-1.6 2.5v1.3l3.1 1.2 1.6 6-1.8.6-1.7-3-.4 3.5.9 5.6-2 .2-1-4.8-1.5 4.8-2-.2 1.1-5.6-.6-3.5-1.8 3-1.6-.7 1.7-6 3-1.1v-1.3C6 10.6 5.9 9.8 5.9 8.7 5.9 7 7 5.5 9 5.5ZM23.1 5.5c2.2 0 3.3 1.4 3.4 2.9l1.5 1.4-1 .8-.1 1.2-1.8.1v.9l2.3 2 .2 5.1-1.7.4-.9-3.2-.2 4.2.6 4.2 2 .5v1h-4.5l-1-5.3.2-5.1-1.3 2.8-1.8-.8.1-4.4 2.2-1.4v-1.4c-.9-.4-1.3-1.2-1.3-2.5 0-2.2 1.5-3.4 3.1-3.4Z',
     'M5.9 8.6c.1-1.8 1.3-3.1 3.2-3.1 1.9 0 2.7 1.4 2.6 3-1.9-.8-3.5-.4-5.8.1Zm14.2.4c0-2 1.5-3.5 3.1-3.5 1.9 0 3 1.2 3.3 2.3-1.6-.6-3.1-.3-4.1 1.9l-.7 1.4c-1.1-.6-1.5-1.2-1.6-2.1Z',
     'M16.8 5v22'],
   head:[
     'M16 3.2c5.9 0 9.1 4 9.2 10.2 1.5-.5 2.1.6 1.8 2.4-.2 1.4-1 2.6-2.4 2.6-1 5.9-4.2 9.5-8.6 9.5s-7.6-3.6-8.6-9.5c-1.4 0-2.2-1.2-2.4-2.6-.3-1.8.3-2.9 1.8-2.4.1-6.2 3.3-10.2 9.2-10.2Z',
     'M7 13.6c0-6 3.6-10.4 9-10.4s9 3.7 9.2 10.3c-4.1-.7-7.1-3.2-8.9-6.7C14.2 10.9 11 12.8 7 13.6Zm1.4 6.3c2 3.9 4.8 6 7.6 6s5.6-2.1 7.6-6c-1.3 5-4.3 8-7.6 8s-6.3-3-7.6-8Z',
     'M10 15.7c1.2-.7 2.3-.7 3.4 0m5.2 0c1.1-.7 2.2-.7 3.4 0m-7 3.4 1 .3m-2 3c1.2.4 2.8.4 4 0'],
   headBlank:[
     'M16 3.2c5.1 0 8.5 4 8.7 9.3l.1 4.1c0 4.3-3.9 11.4-8.8 11.4s-8.8-7.1-8.8-11.4l.1-4.1C7.5 7.2 10.9 3.2 16 3.2Z',
     'M17.5 3.4c5.1.7 7.2 4.7 7.3 9.2v4.3c-.3 4.5-3.9 10.2-7.7 10.9 2-2.3 3.6-6.7 3.8-10.4.3-5.7-.6-10.2-3.4-14Z',
     'M10.1 12c.6-2.2 1.9-3.9 3.5-4.7'],
   profile:[
     'M9 25.7v-4.1a10.4 10.4 0 0 1-4-8.4c0-5.5 4-9.6 9.5-9.6 5.3 0 9 3.4 9.1 8.1l3.1 4.7-2.9 1 .2 2-1.2.8.1 1.8c-1 .9-2.6 1.2-4.9.6v4.1l-5.1 1.6Z',
     'M5 13.4c0-6 4.1-9.8 9.5-9.8 4.1 0 7 2 8.4 5.3-2.1-.5-4.5-.6-7 1.6l-1.4 5.7-2.2 1.1-.9 5.6-2.4-1.3a10 10 0 0 1-4-8.2Z',
     'M20.5 13.3h1.9m1.5 5.7-1.7.2m-9.7-4.8c-2-.9-2.5 1.9-.9 3'],
   eye:[
     'M3.4 16.9c3.1-4.7 7.9-6.7 13.4-6.7 5.9 0 9.2 4.9 12 6.2l-3.1.9c-3.3 1.9-6.1 3.7-10 3.7-4.5 0-8.9-1.3-12.3-4.1Z',
     'M5.6 15.9c2.9-3.8 6.8-5.7 11.2-5.7 4.9 0 8.2 3.6 10.2 5.2-3.6-1.7-7.1-2.7-10.7-2.7-4 0-7.5 1.4-10.7 3.2Zm10.4-3.6a3.7 3.7 0 1 1-.1 7.4 3.7 3.7 0 0 1 .1-7.4Z',
     'M5.1 10.4c4.8-2.5 9.6-2.8 14.4-1.7m-3.4 6.8v1.2'],
   eyes:[
     'M2.5 16.4c2.2-3.7 8.6-4.3 12.3-.4-3.2 3.3-8.2 3.9-12.3.4Zm27 0c-2.2-3.7-8.6-4.3-12.3-.4 3.2 3.3 8.2 3.9 12.3.4Z',
     'M8.5 13.8a2.5 2.5 0 1 1 0 5 2.5 2.5 0 0 1 0-5Zm15 0a2.5 2.5 0 1 1 0 5 2.5 2.5 0 0 1 0-5Z',
     'M3.2 11.9c3-1.8 6.6-1.8 10-.7m15.6.7c-3-1.8-6.6-1.8-10-.7'],
   iris:[
     'M16 4.6c6.3 0 11.4 5.1 11.4 11.4s-5.1 11.4-11.4 11.4S4.6 22.3 4.6 16 9.7 4.6 16 4.6Zm0 7a4.4 4.4 0 1 0 0 8.8 4.4 4.4 0 0 0 0-8.8Z',
     'M16 7.8a8.2 8.2 0 1 1 0 16.4 8.2 8.2 0 0 1 0-16.4Zm0 3.8a4.4 4.4 0 1 0 0 8.8 4.4 4.4 0 0 0 0-8.8Z',
     'M16 6.7v1.5m9.3 7.8h-1.5m-7.8 9.3v-1.5M6.7 16h1.5m12.5-5.4 1.8-1.8M9 22.9l1.8-1.8'],
   nose:[
     'M13.5 5.2c1.9-.7 3.2-.7 5 0l.4 5.5c.2 3 2 5.9 4.4 7.9 2.4 2.2 2.1 5-1 5.7a4 4 0 0 1-3-.7 5.5 5.5 0 0 1-6.6 0 4 4 0 0 1-3 .7c-3.1-.7-3.4-3.5-1-5.7 2.4-2 4.2-4.9 4.4-7.9Z',
     'M17.1 5.3l1.4-.1.4 5.5c.2 3 2 5.9 4.4 7.9 2.4 2.2 2.1 5-1 5.7a4 4 0 0 1-3-.7 5.5 5.5 0 0 1-6.6 0 4 4 0 0 1-3 .7l-.8-.3c2-1.7 4.8-2.2 7.1-2.8 1.9-.6 2.2-2.3 1.8-4.6Z',
     'M9.5 21c1.3-.8 2.7-.8 3.7.1m5.6 0c1-.9 2.4-.9 3.7-.1'],
   mouth:[
     'M3 16.8c4.8-.6 7-5.9 10.5-5.3 1 .2 1.9.6 2.5 1.2.6-.6 1.5-1 2.5-1.2 3.5-.6 5.7 4.7 10.5 5.3-4.3 4.1-8.3 5.5-13 5.5S7.3 20.9 3 16.8Z',
     'M3 16.8c4.8-.6 7-5.9 10.5-5.3 1 .2 1.9.6 2.5 1.2.6-.6 1.5-1 2.5-1.2 3.5-.6 5.7 4.7 10.5 5.3-5.4.8-8.4-.7-13 .6-4.6-1.3-7.6.2-13-.6Z',
     'M4 16.8c4.4.7 8.1-.6 12 .6 3.9-1.2 7.6.1 12-.6'],
   ear:[
     'M9.2 13.8c-1.5-5.6 2.1-9.9 7-10.3 5.6-.4 8.5 3.1 8.2 7.6-.2 3.3-2 5.8-4.1 7.1-1.4.9-2.3 1.5-2.6 3.5-.3 2.5-1.9 5.5-4.9 5.5-3.8 0-5.3-2.8-4.3-5.4l1.2-2.5c1-1.7.2-3.5-.5-5.5Z',
     'M12.2 14.7c-1.9-3.7.7-7.6 4.6-7.8 3.6-.2 5.4 2.1 5 5.1-.3 2.5-1.8 4-4.5 5.3-1.1.6-2.6 1.6-2.6 3.4 0 1.5-.9 2.4-2.2 1.8 1.9-2.6 1.5-4.5-.3-7.8Z',
     'M13.1 14.3c-.5-2.9 1.6-4.7 4.1-4.7 2.4 0 2.8 3.4.6 4.7l-2.3 1.4m-5.4 7.7c.6 1.6 1.8 1.9 3.1 1.6'],
   earCovered:[
     'M9 5c3.7-2.3 7.9-2.5 12.4.2 2.5 1.5 3.3 4 3 7.4-.2 2.7-1.8 5.2-4 6.7-1.2.8-2.5 1.4-2.8 3.4-.3 2.3-1.8 4.5-4.2 4.5-2.8 0-4.6-2.2-4.6-4.6L5.4 26c2.6-4.8-1.7-13.9 3.6-21Z',
     'M9 5c3.7-2.3 7.9-2.5 12.4.2-3.9.3-7.6 3.7-7.9 8.2-.2 4.6-2.5 9-8.1 12.6C8 21.2 3.7 12.1 9 5Zm8.5 7.3c2.9-2.5 5 .5 3.1 2.5-1.3 1.5-3 2.3-4.4 2.8Z',
     'M8.3 20c1.9-5.6 1.7-10.5 7.1-14.1m.8 11.7c.7-2 2.7-2 3.6-3.3'],
   torso:[
     'M11 3h10v4l5.3 2.5 2.6 8.2-2.9 1-3.3-5-1.5 5.6 1.6 8H9.2l1.6-8-1.5-5.6L6 18.7l-2.9-1 2.6-8.2L11 7Z',
     'M6.2 10.1 11 7l5 3 5-3 4.8 3.1-3.1 3.6-1.2 3.4c-1.7 1.4-3.2.2-5.5-1.1-2.3 1.3-3.8 2.5-5.5 1.1l-1.2-3.4Z',
     'M9.7 15c2.4-1.5 4.4-.3 6.3.9 1.9-1.2 3.9-2.4 6.3-.9m-6.3 5.4h.1'],
   torsoBack:[
     'M11 3h10v4l5.8 2.2 2.2 9-2.8.9-3.5-5.1-1.5 5.5 1.7 7.7H9.1l1.7-7.7-1.5-5.5-3.5 5.1-2.8-.9 2.2-9L11 7Z',
     'M6 10.1l5-3.1 3.7 2.6-1.1 8.5-3-1.7-1.3-2.4-3.5 5.1-2.8-.9Zm20 0-5-3.1-3.7 2.6 1.1 8.5 3-1.7 1.3-2.4 3.5 5.1 2.8-.9Z',
     'M16 8v15.4m-5.8-11.5 3 3.7m8.6-3.7-3 3.7'],
   chestSide:[
     'M11 3.3h8.8l.7 3.6c.5 3.3 2.9 4 5.1 7.7 1.8 3.2-.2 6.7-3.4 7.3l.5 5.7h-11l-.2-5.4c-.2-2.6-.9-4.6-2-6.5C7.5 12 8.4 6.7 11 3.3Z',
     'M19.8 3.3l.7 3.6c.5 3.3 2.9 4 5.1 7.7 1.8 3.2-.2 6.7-3.4 7.3-3.7.9-5-.4-6.3-1.7 2.7-.2 6.4-1.4 6.4-4.6 0-2.6-2.5-5.3-3-7.5Z',
     'M16 20.2c1.6 1.5 4.5 2 6.2 1.7'],
   waist:[
     'M8.7 5.2c1.8 4.6 2.5 7.5 1.4 11.7-.9 3.5-3 6.5-3.4 10.1 6.1 1.6 12.5 1.6 18.6 0-.4-3.6-2.5-6.6-3.4-10.1-1.1-4.2-.4-7.1 1.4-11.7H8.7Z',
     'M8.7 5.2h14.6l-1.2 3.4c-4.1 2.2-8.1 2.2-12.2 0ZM6.7 27c.2-2 .8-3.6 1.5-5.1 2.7.3 5.4 1.6 7.8 3.2 2.4-1.6 5.1-2.9 7.8-3.2.7 1.5 1.3 3.1 1.5 5.1-6.1 1.6-12.5 1.6-18.6 0Z',
     'M11.3 14.7c.8 1.2 1 2.7.8 4.1m8.6-4.1c-.8 1.2-1 2.7-.8 4.1M16 18v1.4'],
   abdomenSide:[
     'M10.5 5.1h11.8c-1.4 3.8-2.9 7.7-2.1 10.4.6 2.2 2.7 4.8 3.2 6.9.4 1.7.5 3.3-.2 5H8.8c-.4-3.8 1.8-6.5 2-10.3.2-3.9-1.3-7.6-.3-12Z',
     'M22.3 5.1c-1.4 3.8-2.9 7.7-2.1 10.4.6 2.2 2.7 4.8 3.2 6.9.4 1.7.5 3.3-.2 5h-5.7c1.6-3.9 1.9-6.2.7-9.1-1.6-4.2.2-9.6 1-13.2Z',
     'M15.7 17c1.6-.3 3.1.1 4.7 1m-10.8 6.3c2.3-1.2 4.5-1.5 6.5-1.6'],
   waistBack:[
     'M8.4 5.1h15.2c-1.4 4.5-2.1 8.3-1.3 13.1.6 3.2 2.2 6.8 2.7 9.2-5.8 1.2-12.2 1.2-18 0 .5-2.4 2.1-6 2.7-9.2.8-4.8.1-8.6-1.3-13.1Z',
     'M8.4 5.1h4.2c1 3.3 1.4 6.3 1.3 9.3-.2 4 0 7.1-2.4 9.9-1.2 1.4-2.7 2.5-4.3 2.7.6-2.7 1.9-5.1 2.5-8.8.8-4.8.1-8.6-1.3-13.1Zm15.2 0h-4.2c-1 3.3-1.4 6.3-1.3 9.3.2 4 0 7.1 2.4 9.9 1.2 1.4 2.7 2.5 4.3 2.7-.6-2.7-1.9-5.1-2.5-8.8-.8-4.8-.1-8.6 1.3-13.1Z',
     'M16 6.5v15m-3.7 4c1.1-1.5 2.3-1.7 3.7-.6 1.4-1.1 2.6-.9 3.7.6'],
   hip:[
     'M14.7 4.3h8.7c-.7 4-.5 7.9 1 11.3 1 2.5.7 5-.8 7.4l-1.2 5h-8.9l.1-6.6c-3.6-.2-6.3-1.7-6.4-5.1-.1-3 2.1-5.2 5-7.5 1.3-.9 2.1-2.4 2.5-4.5Z',
     'M14.6 4.3h3.6c-.2 3.9-1.2 7.2-4.7 9.3-2.9 1.8-3.7 5.1.1 7.8-3.6-.2-6.3-1.7-6.4-5.1-.1-3 2.1-5.2 5-7.5 1.3-.9 2.1-2.4 2.4-4.5Zm-.9 17.1c3.7-.5 5.5-2.5 7-3.8-.2 3.8-1.6 7.3-4.2 10.4h-3Z',
     'M13.6 21.4c3.7-.5 5.5-2.5 7-3.8'],
   arm:[
     'M22.7 3.1c4.6 2 3.7 6.5.2 11.5l-3.8 4.1c-.7 1.6-2.4 3.5-4.5 4.9L9.3 27l-2.7 1.9-1.9-.7.2-2.7 2.2-2.2 1.1-1.9 1.9.7 3.9-4.7 1.9-5.5c1-3.4 3.1-9.9 6.8-8.8Z',
     'M22.7 3.1c4.6 2 3.7 6.5.2 11.5l-3.8 4.1c-.7 1.6-2.4 3.5-4.5 4.9l-5.3 3.4c1.3-2.7 4.8-5.3 6.4-7.8 1.3-2.2 1.4-5.5 2.6-7.8 1.4-2.6 3.6-4 4.4-8.3Z',
     'M16 15.4c.6 1.3 1.5 2 2.8 2.2m-9 7.4 2.2-2.1'],
   hand:[
     'M12 3h8v5.3c0 2 1.9 3 2.5 5l3.2 7.6c.4 1.3-1.3 2.2-2.1 1l-2.6-4.1.3 8c0 1.5-2.1 1.6-2.3.2l-.6-5.4.1 7.4c0 1.5-2.3 1.7-2.5.2l-.6-7.5-.2 6.6c0 1.5-2.1 1.5-2.3.1l-.5-7.1-.8 4.4c-.2 1.3-2.2 1.3-2.2-.1l.3-8.5c.1-2.1 1.5-5.2 2.3-7Z',
     'M18.8 3H20v5.3c0 2 1.9 3 2.5 5l3.2 7.6c.4 1.3-1.3 2.2-2.1 1l-2.6-4.1-.8 5.6-1.2-3.7-.9-4.7.7-2.9c.6-2.8 0-5.8 0-9.1Z',
     'M13 13.3l-.5 4.7m3.2-5.1.1 5.2m2.3-4.9.7 4.1'],
   handsBack:[
     'M5.3 27.4l.2-4.1C3 20.2 3 17 2.6 14.3c-.2-1.2 1.2-1.4 1.5-.3l1.6 4.3-1-8.9c-.2-1.2 1.3-1.7 1.6-.4l1.6 7.5-.4-10.2c0-1.3 1.5-1.4 1.7-.1l.9 10 1-7.9c.1-1.3 1.7-1.1 1.6.2l-.4 10.6 1.9-3.5c.7-1.1 2-.4 1.5.7l-2.6 5.6-1.5 1.7-.4 3.8Zm21.4 0-.2-4.1c2.5-3.1 2.5-6.3 2.9-9 .2-1.2-1.2-1.4-1.5-.3l-1.6 4.3 1-8.9c.2-1.2-1.3-1.7-1.6-.4l-1.6 7.5.4-10.2c0-1.3-1.5-1.4-1.7-.1l-.9 10-1-7.9c-.1-1.3-1.7-1.1-1.6.2l.4 10.6-1.9-3.5c-.7-1.1-2-.4-1.5.7l2.6 5.6 1.5 1.7.4 3.8Z',
     'M6.9 17.7l1.5 1.2L10 17l1.5.8-1.6 4-1.5 4.8-1.3-1.5 1-4.4Zm18.2 0-1.5 1.2L22 17l-1.5.8 1.6 4 1.5 4.8 1.3-1.5-1-4.4Z',
     'M6.3 11.5h.1m2.5-1.3h.1m3.1 1.5h.1m7.7 0h.1m3.1-1.5h.1m2.5 1.3h.1'],
   handsPalm:[
     'M5.9 27.5l.5-4.5-4.2-5.8c-.7-1.1.6-2.1 1.5-1.2l2.3 2.5-.8-10.1c-.1-1.3 1.6-1.5 1.8-.2l1.1 7.1.1-9.4c0-1.3 1.7-1.4 1.8 0l.4 9.4 1.4-7.7c.2-1.3 1.8-1.1 1.7.2l-.8 8.5 1.7-4.3c.5-1.1 1.8-.6 1.5.6l-1.9 8.1-2.2 2.5-.3 4.3Zm20.2 0-.5-4.5 4.2-5.8c.7-1.1-.6-2.1-1.5-1.2L26 18.5l.8-10.1c.1-1.3-1.6-1.5-1.8-.2l-1.1 7.1-.1-9.4c0-1.3-1.7-1.4-1.8 0l-.4 9.4-1.4-7.7c-.2-1.3-1.8-1.1-1.7.2l.8 8.5-1.7-4.3c-.5-1.1-1.8-.6-1.5.6l1.9 8.1 2.2 2.5.3 4.3Z',
     'M6 18.4c3.1.4 4.2 2 4.2 4.3l-3.8.3Zm20 0c-3.1.4-4.2 2-4.2 4.3l3.8.3Z',
     'M7.8 17.4c1.4-.8 2.7-.8 4.1 0m-5.2 2c1.8.2 3 .8 3.6 2.4m13.9-4.4c-1.4-.8-2.7-.8-4.1 0m5.2 2c-1.8.2-3 .8-3.6 2.4'],
   leg:[
     'M12.6 3.4h10.7c.2 4.7-2.2 9.5-3.1 13.9 0 3-1.8 7.3-3.1 8.8l-.1 1.5 2.7.8v1.2H12l-.2-2.6 1.6-5.2.8-4.5c-1.7-4.4-3-8.8-1.6-13.9Z',
     'M18.1 3.4h5.2c.2 4.7-2.2 9.5-3.1 13.9 0 3-1.8 7.3-3.1 8.8l-.1 1.5 2.7.8v1.2h-4.6l-.4-2.4 1.9-5.6c1.1-6.3 1.9-12 1.5-18.2Z',
     'M14.6 16.2c1.4.8 2.5.9 4 .3m-3.6 2c1 .4 2 .5 2.8.2'],
   foot:[
     'M7.3 4.7h8.6c-.8 4.9-.9 8.2 1.2 10.6 2.8 2.7 5.1 3.3 9.5 5.6 1.9 1 2.8 2.8 1.4 3.9H7.9c-2.5-.3-3.8-2.1-2.9-4.4 1.4-3.6 2.6-6.7 2.3-15.7Z',
     'M10.2 4.7h5.7c-.8 4.9-.9 8.2 1.2 10.6 2.8 2.7 5.1 3.3 9.5 5.6 1.9 1 2.8 2.8 1.4 3.9h-3c-.4-2-4-2.1-7.5-4.4-5.2-3.2-5.6-8.4-7.3-15.7Z',
     'M10.2 17.4c-1.6.1-2.4 1.3-2.2 2.6m14.8 2.1-.6 2.1m3.1-1.2-.4 1.2'],
   feetFront:[
     'M5.4 5h7.5l-.4 6.8c-.2 2 1.2 3.8 1.7 6.1l1.2 5.6c.5 2.4-2 3.2-3 2.4-.7.7-1.8.7-2.4 0-.7.7-1.8.6-2.3-.1-1 .5-1.7.1-2.1-.5-1.3.6-2.3-.4-2.2-1.8l.5-5.2c.4-2.4 1.8-4.5 1.8-6.5Zm21.2 0h-7.5l.4 6.8c.2 2-1.2 3.8-1.7 6.1l-1.2 5.6c-.5 2.4 2 3.2 3 2.4.7.7 1.8.7 2.4 0 .7.7 1.8.6 2.3-.1 1 .5 1.7.1 2.1-.5 1.3.6 2.3-.4 2.2-1.8l-.5-5.2c-.4-2.4-1.8-4.5-1.8-6.5Z',
     'M9.8 5h3.1l-.4 6.8c-.2 2 1.2 3.8 1.7 6.1l1.2 5.6c.3 1.5-.5 2.4-1.6 2.6L10 19.3 9 13.2Zm12.4 0h-3.1l.4 6.8c.2 2-1.2 3.8-1.7 6.1l-1.2 5.6c-.3 1.5.5 2.4 1.6 2.6l3.8-6.8 1-6.1Z',
     'M12.4 25.9l-.8-3m-1.6 3-.6-2.8m10.2 2.8.8-3m1.6 3 .6-2.8'],
   feetTop:[
     'M6.6 28c.8-3.3.7-5.5-.2-7.6C4.2 15.6 4.3 12 4.2 9.6c0-1.1 1.4-1.6 1.8-.5-.1-1.5.8-2.6 1.9-2.2 0-1.7 1.3-2.5 2.3-1.5.3-1.7 2-2 2.7-.4 1-1.7 2.9-.6 2.7 1.1l-.5 5.3c.3 3.1-1.5 6.7-2.3 9.8-.6 2.2.3 4.8.7 6.8Zm18.8 0c-.8-3.3-.7-5.5.2-7.6 2.2-4.8 2.1-8.4 2.2-10.8 0-1.1-1.4-1.6-1.8-.5.1-1.5-.8-2.6-1.9-2.2 0-1.7-1.3-2.5-2.3-1.5-.3-1.7-2-2-2.7-.4-1-1.7-2.9-.6-2.7 1.1l.5 5.3c-.3 3.1 1.5 6.7 2.3 9.8.6 2.2-.3 4.8-.7 6.8Z',
     'M12.9 5c1-1.7 2.9-.6 2.7 1.1l-.5 5.3c.3 3.1-1.5 6.7-2.3 9.8-.6 2.2.3 4.8.7 6.8h-2.3c.1-5.3-.9-6.9.4-11.2.6-2 1.8-6.8 1.3-11.8Zm6.2 0c-1-1.7-2.9-.6-2.7 1.1l.5 5.3c-.3 3.1 1.5 6.7 2.3 9.8.6 2.2-.3 4.8-.7 6.8h2.3c-.1-5.3.9-6.9-.4-11.2-.6-2-1.8-6.8-1.3-11.8Z',
     'M12.9 6v3.3m-2.7-3.5.1 3m8.8-2.8v3.3m2.7-3.5-.1 3'],
   heels:[
     'M5.2 5.1h8.6l-1 7.2c-.3 3.3 2 6.7 2 10.7 0 3.2-2.6 4.3-5.6 4.3-3.2 0-6-1.3-6-4.4 0-4.4 2.5-7 2.5-10.6Zm21.6 0h-8.6l1 7.2c.3 3.3-2 6.7-2 10.7 0 3.2 2.6 4.3 5.6 4.3 3.2 0 6-1.3 6-4.4 0-4.4-2.5-7-2.5-10.6Z',
     'M5.1 21.5c1.6-1.5 6.5-1.6 8.2 0l1.5 1.5c0 3.2-2.6 4.3-5.6 4.3-3.2 0-6-1.3-6-4.4Zm21.8 0c-1.6-1.5-6.5-1.6-8.2 0L17.2 23c0 3.2 2.6 4.3 5.6 4.3 3.2 0 6-1.3 6-4.4Z',
     'M9.1 8.2c1.1 4.6 1.1 7.9 0 11.4m13.8-11.4c-1.1 4.6-1.1 7.9 0 11.4'],
   shoe:[
     'M7.2 6.5H16l1.5 7.6c2.7 3 5 3.5 9.5 5.1 2.1.7 2.8 2.9 1.6 4.4-.7 1-1.9 1.9-4.4 1.9H5.9c-2.6 0-3.8-1.8-3-3.7l1.9-4.6Z',
     'M4 20.7c2.4.9 4.8 1.2 8.4 1.2h11.9c1.6 0 3.2-.3 4.6-1.1.3 1 .1 2.1-.3 2.8-.7 1-1.9 1.9-4.4 1.9H5.9c-2.6 0-3.8-1.8-3-3.7Z',
     'M9.9 10.6h6.5m-7.2 3.8h7.9m-9.3 3.7h11.7'],
   hair:[
     'M16.3 3.7c6.2 0 9.1 4.1 9.6 9.5.3 3.6-.2 7.4 2.7 12.6-4.2-.2-5.3-1.7-6.6-3.6-.1 1.7.3 3.3 1.3 4.8-5.3-1.4-5.4-5.4-4.7-9.5.6-3.9-.5-6-3-7.5-2.6 3.6-4.3 4-5.4 6.8-1.1 2.9 1.8 6 1.1 9.5-1.3-1.4-2-2-3.1-2.6-.4 2.1-2.4 3.1-4.6 3.4 2.2-3 2.2-6.6 1.7-10.5-.8-6.4 3.8-12.9 11-12.9Z',
     'M16.3 3.7c6.2 0 9.1 4.1 9.6 9.5.3 3.6-.2 7.4 2.7 12.6-4.2-.2-5.3-1.7-6.6-3.6-.1 1.7.3 3.3 1.3 4.8-4.7-1.7-4.4-6.2-3.5-10.3.7-3.4 0-7.6-3.5-13Z',
     'M7.6 23c1-2.6-.6-4.7.2-7.2 1.1-3.3 4.8-3.8 6.6-8.6m7.3 3.8c1.8 3.2.4 5.3 1.1 8.3'],
   outfit:[
     'M10.4 12.8l2.4-1.3 3.2 2.1 3.2-2.1 2.4 1.3-1.8 3.2.3 2.6c1.1 2.7 3.3 5.4 4.6 9.5-5.5 1.6-11.9 1.6-17.4 0 1.3-4.1 3.5-6.8 4.6-9.5l.3-2.6Z',
     'M16 13.6l3.2-2.1 2.4 1.3-1.8 3.2.3 2.6c1.1 2.7 3.3 5.4 4.6 9.5l-5.2 1.1c0-3.7-2.1-7.4-2.2-10.9Z',
     'M13.8 5.3a2.2 2.2 0 1 1 3.1 2c-.7.3-.9.6-.9 1.5L4.5 13.6c-.7.3-.5 1.3.3 1.3h4m14.4 0h4c.8 0 1-.9.3-1.3L16 8.8m-4.3 9.8c2.8.7 5.8.7 8.6 0'],
   fullLook:[
     'M16 2.2c2.4 0 3.8 1.7 3.6 4.2-.1 1.5-.7 2.6-1.9 3.3l.1 1.5 4.3 1.4 3.3 7.5-1.7.8-3.9-5.2-1 3.2c1.3 2.5 4 5.5 6.4 9.3-6 1.9-12.4 1.9-18.4 0 2.4-3.8 5.1-6.8 6.4-9.3l-1-3.2-3.9 5.2-1.7-.8 3.3-7.5 4.3-1.4.1-1.5c-1.2-.7-1.8-1.8-1.9-3.3-.2-2.5 1.2-4.2 3.6-4.2Z',
     'M12.4 6.1c0-2.4 1.4-3.9 3.6-3.9 2.1 0 3.5 1.4 3.6 3.5-2.4-.9-4.9-.3-7.2.4Zm-.2 8.8 3.8 1.5 3.8-1.5-1 4c1.3 2.5 4 5.5 6.4 9.3l-6.5 1.4c.2-4.7-2.7-8.6-2.7-10.4 0 1.8-2.9 5.7-2.7 10.4l-6.5-1.4c2.4-3.8 5.1-6.8 6.4-9.3Z',
     'M13.7 11.6 16 13l2.3-1.4m-5.1 7.3c1.8.8 3.8.8 5.6 0m-3.8 8.8 1-5 1 5'],
   jewel:[
     'M5.5 10.8 10.1 5h11.8l4.6 5.8L16 28Z',
     'M5.5 10.8h6.1L16 28Zm10.5 0h10.5L16 28l4.4-17.2Z',
     'M5.5 10.8h21m-14.9 0L16 5l4.4 5.8L16 28Z'],
   voice:[
     'M10.3 11.2h3l6.5-5c.6-.4 1.4 0 1.4.8v18c0 .8-.8 1.2-1.4.8l-6.5-5h-3c-1 0-1.4-.5-1.4-1.4v-6.8c0-.9.4-1.4 1.4-1.4Z',
     'M13.3 11.2l6.5-5c.6-.4 1.4 0 1.4.8v18c0 .8-.8 1.2-1.4.8l-2.2-1.7v-8.7l-4.3 3.9Z',
     'M24.6 12.1c2.6 2.4 2.6 5.4 0 7.8m2.3-11.4c4.4 3.3 4.4 11.7 0 15'],
 };
 function ringSymbol(kind,side=0){
   const space='http://www.w3.org/2000/svg';
   const shell=document.createElementNS(space,'svg'),art=document.createElementNS(space,'g');
   shell.setAttribute('class','cl-ring-symbol');
   shell.setAttribute('viewBox','0 0 32 32');shell.setAttribute('aria-hidden','true');
   shell.setAttribute('focusable','false');shell.dataset.icon=kind;
   if(side===-1)art.setAttribute('transform','translate(32 0) scale(-1 1)');
   const [shape,shade,engraving]=ringIllustrations[kind]||ringIllustrations.body;
   for(const [layer,paths] of [['base',shape],['shade',shade],['ink',shape],['detail',engraving]]){
     if(!paths)continue;
     const path=document.createElementNS(space,'path');
     path.setAttribute('class','cl-ring-'+layer);path.setAttribute('d',paths);
     art.append(path);
   }
   shell.append(art);
   return shell;
 }
 function ringIdentity(entry){
   const title=entry.label.normalize('NFKC'),subject=title.replace(/\([^)]*\)/gu,'');
   const side=/左|\bleft\b/iu.test(subject)?-1:/右|\bright\b/iu.test(subject)?1:0;
   const direction={front:0,three_quarter:1,side:2,back:3,body_blank:4,asset:5};
   const view=entry.row.appearance?.view;
   if(entry.group==='history'){
     const visual=ringIdentity({...entry,group:referenceGroup(entry.row)});
     return {...visual,chapter:0,order:direction[view]??6};
   }
   const shoe=/鞋|靴|shoe|boot/iu.test(title);
   if(entry.group==='base'){
     const kind=/无头|headless/iu.test(title)?'headless':view==='head_front'?'head':view==='head_blank'?'headBlank':Object.hasOwn(ringIllustrations,view)?view:'body';
     return {chapter:0,order:direction[view]??6,kind:shoe?'shoe':kind,side};
   }
   if(entry.group==='features'){
     const mark=[[/侧面脸|profile/iu,'profile',1],[/无面头模|head blank/iu,'headBlank',0],
       [/头部|头模|head/iu,'head',0],
       [/瞳|虹膜|iris/iu,'iris',4],[/眼睛|^eyes$/iu,'eyes',2],
       [/眼|eye/iu,'eye',3],[/鼻|nose/iu,'nose',5],[/嘴|唇|mouth|lip/iu,'mouth',6]];
     if(/耳|\bear\b/iu.test(title))return {chapter:1,order:7+(side===1?.2:0)+(/头模/iu.test(title)?.1:0),
       kind:/遮挡|covered/iu.test(title)?'earCovered':'ear',side};
     const match=mark.find(([test])=>test.test(title));
     return {chapter:1,order:(match?.[2]??8)+(side===1?.2:0)+(/光头/iu.test(title)?.1:0),kind:match?.[1]||'head',side};
   }
   if(entry.group==='torso'){
     const region=/胸|chest/iu.test(title)?1:/腹|abdomen/iu.test(title)?2:/腰|waist/iu.test(title)?3:/臀|hip/iu.test(title)?4:0;
     const angle=/背|rear|back/iu.test(title)?.3:/侧|side/iu.test(title)?.2:/斜|oblique/iu.test(title)?.1:0;
     const order=region+angle;
     const kind=[angle===.3?'torsoBack':'torso','chestSide',angle===.2?'abdomenSide':'waist','waistBack','hip'][region];
     return {chapter:2,order,kind,side};
   }
   if(/脚|足|趾|腿|foot|feet|leg/iu.test(title)){
     const kind=/腿|leg/iu.test(title)?'leg':/脚跟|heel/iu.test(title)?'heels':
       /俯视|top/iu.test(title)?'feetTop':/双脚|feet/iu.test(title)?'feetFront':'foot';
     const order=(kind==='leg'?0:/正面|front/iu.test(title)?1:/俯视|top/iu.test(title)?2:/侧|side/iu.test(title)?3:4)+(side===1?.2:0);
     return {chapter:4,order,kind:shoe?'shoe':kind,side};
   }
   if(entry.group==='limbs'||entry.group==='details'){
     const kind=/臂|arm/iu.test(title)?'arm':
       /双手|hands/iu.test(title)?(/背|back/iu.test(title)?'handsBack':'handsPalm'):'hand';
     const order=(kind==='arm'?0:kind==='hand'?1:/背|back/iu.test(title)?2:3)+(side===1?.2:0);
     return {chapter:3,order,kind:shoe?'shoe':kind,side};
   }
   const kind={voice:'voice',hair:'hair',wardrobe:'outfit',accessories:'jewel'}[entry.group]||'body';
   return {chapter:5,order:0,kind:shoe?'shoe':kind,side};
 }
 function browseRows(state,history=false){
   const rows=state.form.rows.filter(row=>history?row.browseArchived:
     !row.browseArchived&&row.appearance?.format!=='full_look'&&!gearGroups.includes(browseGroup(row)));
   const entries=rows.flatMap(row=>{
     return [browseEntry(state.rows,row),...(row.appearance?.details||[])
       .filter(part=>part.region).map(part=>browseEntry(state.rows,row,part))];
   });
   const home=browseHome(state.form);
   const rank={current:0,candidate:1,historical:2};
   entries.sort((a,b)=>Number(b.row.id===home?.id)-Number(a.row.id===home?.id)||
     (a.row.browseNote?.order??999)-(b.row.browseNote?.order??999)||
     rank[a.row.status]-rank[b.row.status]);
   const unique=new Map();
   for(const entry of entries){
     const {region,source}=entry;
     const box=region?[!!region.source_version_id,region.x,region.y,region.width,region.height]:null;
     const key=JSON.stringify([source.file.project_id,source.file.sha256,box]);
     if(!unique.has(key))unique.set(key,{...entry,group:browseGroup(entry.row)});
   }
   return [...unique.values()].map(entry=>({...entry,symbol:ringIdentity(entry)})).sort((a,b)=>
     a.symbol.chapter-b.symbol.chapter||a.symbol.order-b.symbol.order);
 }
 function ringSections(entries){
   let cursor=0;
   return ringSides.map((_,index)=>{
     const end=cursor+Math.ceil((entries.length-cursor)/(ringSides.length-index));
     const side=entries.slice(cursor,end);cursor=end;return side;
   });
 }
 function locateRing(state){
   const group=state.group;
   for(const tile of state.root.querySelectorAll('.cl-ring-edge [data-asset-group]'))
     tile.dataset.located=String(!!group&&group!=='history'&&tile.dataset.assetGroup===group);
 }
 function nameRingButton(state,option,label,missing=false){
   OAUI.attr(option,'aria-label',label);
   const tip=state.tooltip;
   const hide=()=>{if(state.tooltipOwner===option){tip.hidden=true;state.tooltipOwner=null;}};
   const show=()=>{
     state.tooltipOwner=option;
     OAUI.set(tip,label);tip.hidden=false;
     const rect=option.getBoundingClientRect(),width=tip.offsetWidth,height=tip.offsetHeight;
     tip.style.left=Math.max(8,Math.min(window.innerWidth-width-8,rect.left+(rect.width-width)/2))+'px';
     tip.style.top=(rect.top>=height+14?rect.top-height-6:rect.bottom+6)+'px';
   };
   option.addEventListener('pointerenter',ev=>{if(ev.pointerType==='mouse')show();});
   option.addEventListener('pointerleave',()=>{if(!option.matches(':focus-visible'))hide();});
   option.addEventListener('focus',()=>{if(option.matches(':focus-visible'))show();});
   option.addEventListener('blur',()=>{if(!option.matches(':hover'))hide();});
   option.addEventListener('click',missing?show:hide);
 }
 function markMissingSlot(state,option,label){
   option.dataset.missing='true';
   option.setAttribute('aria-disabled','true');
   nameRingButton(state,option,t('{0} · 未登记资产',t(label)),true);
 }
 function ringTile(state,entry,slot){
   const option=button(undefined,entry?()=>void visitBrowse(state,entry):null);
   const symbol=entry?.symbol||slot;
   option.className='cl-browse-tile';
   option.dataset.assetGroup=slot?.group||entry.group;
   option.dataset.chapter=symbol.chapter??slot.chapter;
   option.dataset.subjectSide=symbol.side;
   if(slot)option.dataset.ringSlot=slot.label;
   if(entry){
     option.dataset.choice=entry.key;
     nameRingButton(state,option,entry.label);
   }else markMissingSlot(state,option,slot.label);
   option.append(ringSymbol(symbol.kind,symbol.side));
   return option;
 }
 function referenceSections(state,entries){
   const unused=new Set(entries);
   const home=browseHome(state.form);
   const slots=Object.entries(ringSlots).flatMap(([group,items],chapter)=>items.map(([label,kind,view,side=0])=>
     ({group,label,kind,view,side,chapter:group==='voice'?5:chapter})));
   const tiles=slots.map(slot=>{
     const candidates=[...unused].filter(entry=>entry.group===slot.group||
       (slot.group==='features'&&entry.group==='base'&&slot.view&&entry.row.appearance?.view===slot.view));
     const entry=candidates.find(item=>normalize(item.label)===normalize(slot.label))
       ||candidates.find(item=>slot.view&&!item.region&&item.row.appearance?.view===slot.view)
       ||candidates.find(item=>slot.view==='head_front'&&normalize(item.label)==='正面脸部近照')
       ||candidates.find(item=>item.symbol.kind===slot.kind&&item.symbol.side===slot.side&&slot.kind!=='head')
       ||candidates.find(item=>item.row===home&&!item.region&&(
         slot.view==='front'&&figureAngle(basicFigure(state,item))==='front'
         ||slot.view==='head_front'&&item.symbol.kind==='head'&&item.row.use==='face'));
     unused.delete(entry);
     return ringTile(state,entry,slot);
   });
   tiles.push(...state.lookTriggers.values());
   const sections=ringSections(tiles);
   for(const entry of unused){
     const index=sections.findIndex(side=>side.some(tile=>tile.dataset.assetGroup===entry.group));
     sections[index===-1?sections.length-1:index].push(ringTile(state,entry));
   }
   if(state.wardrobeRows.length)sections[0].push(state.fullTool);
   return sections;
 }
 function drawRing(state){
   state.tooltip.hidden=true;state.tooltipOwner=null;
   const history=state.group==='history';
   const entries=browseRows(state,history);
   if(!history)state.figureEntries=entries.map(entry=>basicFigure(state,entry)).filter(figureAngle);
   const sections=history?ringSections(entries.map(entry=>ringTile(state,entry))):referenceSections(state,entries);
   state.ring[0].parentElement.style.setProperty('--cl-ring-capacity',Math.max(10,...sections.map(side=>side.length)));
   for(const [index,rail] of state.ring.entries()){
     const items=sections[index];
     rail.replaceChildren(...items);
     rail.hidden=!items.length;
   }
   state.empty.hidden=!!entries.length||(!history&&[...state.lookTriggers.values()].some(tile=>tile.dataset.missing!=='true'));
   browseReflect(state);
   locateRing(state);
 }
 function browseRing(state,key){
   if(!state.slots.has(key)&&key)return;
   if(state.group===key)return;
   const redraw=state.group===undefined||state.group==='history'||key==='history';
   state.group=key;
   closeBrowseLayers(state);
   for(const [group,tile] of state.slots)tile.setAttribute('aria-pressed',String(group===key));
   if(redraw)drawRing(state);else locateRing(state);
 }
 function closeBrowseSupplement(state){
   if(!state.supplement)return;
   state.supplement.hidden=true;
   state.supplementTab?.setAttribute('aria-expanded','false');
 }
 function showBrowseSupplement(state){
   if(!state.supplement.hidden){closeBrowseSupplement(state);return;}
   closeLook(state,false);
   state.info.hidden=true;state.fields.hidden=true;state.inspect.setAttribute('aria-expanded','false');
   closeBrowseSupplement(state);
   const panel=state.supplement;
   panel.replaceChildren();
   const guide=state.form.guide,group=state.group;
   for(const [label,entries] of [['校对备注',guide.reviews],['待补视角',guide.pending]]){
     const scoped=group?entries.filter(row=>row.group===group):entries;
     panel.append(node('h4','',label));
     if(!scoped.length)panel.append(node('p','cl-guide-note','本组暂无登记。'));
     for(const row of scoped){
       const item=node('p','cl-guide-note');
       item.append(node('strong','',row.title),node('span','',row.text));panel.append(item);
     }
   }
   panel.hidden=false;panel.scrollTop=0;
   state.supplementTab.setAttribute('aria-expanded','true');
 }
 const characterProfileLabels={height:'身高',blood_type:'血型',zodiac:'星座',mbti:'MBTI',personality:'性格'};
 function profileRow(list,label,value,field){
   const row=node('div','cl-profile-row'),content=node('dd');
   if(field)row.dataset.profileField=field;
   row.append(node('dt','',label),content);list.append(row);
   if(value)OAUI.raw(content,value);
   return content;
 }
 function measurementRow(list,fact){
   const cell=profileRow(list,fact.label,'');
   cell.parentElement.dataset.measurement=fact.label;
   let basis=fact.basis,code='',label='';
   if(/^用户指定(?:[；，：]|$)/u.test(basis)){
     code='specified';label='用户指定';basis=basis.replace(/^用户指定[；，：]?\s*/u,'');
   }else if(basis.includes('拟定')){
     code='proposed';label='拟定 · 待确认';
     basis=basis.replace(/^拟定[；，：]?\s*/u,'').replace(/，?待确认$/u,'');
   }
   const factLine=node('div','cl-profile-fact'),value=node('strong','',fact.value);
   factLine.append(value);cell.append(factLine);
   if(code){
     const badge=node('span','cl-profile-badge',label);
     badge.dataset.confirmation=code;factLine.append(badge);
   }
   if(basis)cell.append(node('span','cl-profile-basis',basis));
 }
 function characterProfile(person,form,identity){
   const panel=node('aside','cl-profile-pane');
   panel.id='clCharacterProfile';
   panel.setAttribute('aria-labelledby','clProfileHeading');
   const title=node('h3','','人物档案');
   title.id='clProfileHeading';
   const summary=node('dl');
   panel.append(title,identity,summary);
   OAUI.set(profileRow(summary,'人物形态','','form'),form.name);
   if(person.character.series)profileRow(summary,'系列',person.character.series,'series');
   if(person.character.aliases.length)profileRow(summary,'别名',person.character.aliases.join('、'),'aliases');
   const measurements=form.guide?.measurements||[];
   const seen=new Set(measurements.map(fact=>fact.label));
   for(const [field,label] of Object.entries(characterProfileLabels)){
     const value=person.profile[field];
     if(value&&!seen.has(label))profileRow(summary,label,value,field);
   }
   const missing=Object.entries(characterProfileLabels).filter(([field,label])=>
     field!=='height'&&!person.profile[field]&&!seen.has(label)).map(([,label])=>label);
   if(missing.length){
     const row=node('p','cl-profile-missing');
     row.append(OAUI.label('待补资料'),document.createTextNode(' · '));
     missing.forEach((label,index)=>{
       if(index)row.append(document.createTextNode(' / '));
       row.append(OAUI.label(label));
     });
     panel.append(row);
   }
   panel.append(node('h3','','身体测量'));
   if(measurements.length){
     const source=node('p','cl-profile-missing','来源 · 本项目人物浏览指南'),list=node('dl');
     list.dataset.profileMeasurements='true';
     measurements.forEach(fact=>measurementRow(list,fact));
     panel.append(list,source);
   }else panel.append(node('p','cl-profile-missing','暂无已登记测量'));
   return panel;
 }
 function toggleRuler(state,enabled=!state.rulerActive){
   state.rulerActive=enabled;
   state.rulerButton.setAttribute('aria-pressed',String(enabled));
   state.ruler.setActive(enabled);
 }
 function attachRuler(state,profile,metadata,full){
   const model=state.form.guide?.ruler;
   if(!model)return;
   const title=state.form.guide.title||state.form.guide.revision;
   const ruler=OACharacterRuler(model,{title,formName:state.form.name,stage:state.stage,photo:state.stagePhoto,
     viewLabel:angle=>viewsOfBody[angle],
     findImage:ref=>state.rows.find(row=>row.id===ref.version&&row.file.sha256===ref.sha256),
     loadImage:async row=>{
       const image=node('img');
       image.src=await cachedCharacterImage('character_preview',row);
       await imageReady(image);return image;
     },
   });
   const control=button('比例标尺',()=>toggleRuler(state));
   control.dataset.rulerToggle='';control.setAttribute('aria-pressed','false');
   control.setAttribute('aria-controls','clProportionRuler');
   full.after(control,ruler.comparisonButton);
   metadata.firstElementChild.after(ruler.toolbar,ruler.notice);
   profile.children[1].after(ruler.summary);
   state.ruler=ruler;state.rulerButton=control;
 }
 const setTrial=OACharacterSetTrial({tool,sendChat,canSend,make:node,button,
   thumbnail:row=>cachedCharacterImage('character_thumbnail',row)});
 function makeBrowsePage(view,person,form,trigger){
   const root=$('clDetailContent');
   root.replaceChildren();root.className='cl-detail cl-browse';
   const header=node('header','cl-browse-header'),forms=node('nav','cl-forms'),identity=node('div','cl-browse-identity');
   const heading=node('h2'),copy=node('div');
   heading.id='clDetailTitle';OAUI.raw(heading,person.character.name);
   const subtitle=node('small');OAUI.raw(subtitle,person.projectName);
   copy.append(heading,subtitle);identity.append(browseThumb(person.cover),copy);
   const back=button('返回人物库',closeDetail);
   OAUI.attr(forms,'aria-label','人物形态');
   if(person.forms.length>1)for(const shape of person.forms){
     const tab=button(shape.name,()=>showDetail(view,person,browseHome(shape),trigger));
     tab.dataset.form=shape.id;tab.setAttribute('aria-pressed',String(shape.id===form.id));forms.append(tab);
   }
   header.append(back,forms);
   const tools=node('div','cl-browse-tools'),categories=node('nav','cl-browse-categories');
   OAUI.attr(categories,'aria-label','人物资产定位');
   tools.append(categories);
   if(form.guides.length>1){
     const revisionControl=node('label','cl-browse-revision');
     const select=node('select');
     OAUI.attr(select,'aria-label','素材修订');
     for(const guide of form.guides){
       const option=node('option');
       option.value=guideKey(guide);
       if(guide.title)OAUI.raw(option,guide.title);else OAUI.set(option,'上一版');
       select.append(option);
     }
     select.value=guideKey(form.guide);
     select.onchange=()=>{
       const guide=form.guides.find(value=>guideKey(value)===select.value);
       if(!guide)return;
       const sourceForm=person.forms.find(shape=>shape.id===form.id);
       showDetail(view,person,browseHome(sourceForm,guide),trigger,undefined,select.value);
       $('clDetailContent').querySelector('.cl-browse-revision select')?.focus({preventScroll:true});
     };
     revisionControl.append(node('span','','素材修订'),select);
     tools.append(revisionControl);
   }
   const body=node('div','cl-browse-body'),stage=node('section','cl-browse-stage');
   const arena=node('div','cl-browse-arena'),ringFrame=node('div','cl-browse-ring');
   body.id='clBrowseRing';
   const ring=ringSides.map((side,i)=>{
     const area=node('div','cl-ring-edge cl-ring-'+side);area.dataset.edge=side;
     area.setAttribute('role','group');OAUI.attr(area,'aria-label',['上方资产','右侧资产','下方资产','左侧资产'][i]);
     area.hidden=true;return area;
   });
   const stagePhoto=node('div','cl-browse-photo'),caption=node('div','cl-browse-caption');
   const exhibit=node('section','cl-wardrobe-exhibit');exhibit.id='clWardrobeExhibit';exhibit.inert=true;
   OAUI.attr(exhibit,'aria-label','衣饰陈列');
   const rail=node('span','cl-wardrobe-rail'),plinth=node('span','cl-wardrobe-plinth');
   rail.setAttribute('aria-hidden','true');plinth.setAttribute('aria-hidden','true');
   const exhibitGroups={wardrobe:node('div','cl-wardrobe-display-group'),accessories:node('div','cl-wardrobe-display-group')};
   for(const [name,label] of [['wardrobe','衣架'],['accessories','配饰架']]){
     const group=exhibitGroups[name];group.setAttribute('role','group');OAUI.attr(group,'aria-label',label);
   }
   exhibit.append(rail,plinth,...Object.values(exhibitGroups));
   const shelfReturn=button('返回当前全身',()=>{if(state.figureRequest)void presentFigure(state,state.figureRequest);});
   shelfReturn.className='cl-shelf-return';shelfReturn.hidden=true;
   const tooltip=node('div','cl-ring-tooltip');
   tooltip.hidden=true;tooltip.setAttribute('role','tooltip');tooltip.setAttribute('aria-hidden','true');
   stage.append(stagePhoto,exhibit,shelfReturn);
   const stageTitle=node('strong'),stageKind=node('span','cl-browse-kind');
   const controls=node('div','cl-browse-controls'),feedback=node('p','cl-browse-status');
   const empty=node('p','cl-browse-status','这类素材尚未登记。');empty.hidden=true;
   const guideSelection=node('p','cl-guide-selection');guideSelection.hidden=true;
   feedback.setAttribute('role','status');
   const originalButton=button('查看原图',()=>void browseSelect(state,state.requested,true));
   const cropButton=button('返回局部',()=>void browseSelect(state,state.requested));
   originalButton.hidden=true;cropButton.hidden=true;
   const fields=node('dl','cl-detail-fields');
   const aux=node('div','cl-browse-aux'),info=node('div','cl-browse-info');
   info.id='clBrowseAssetInfo';info.hidden=true;info.append(fields);
   const lookPicker=node('section','cl-look-select'),lookHeading=node('header'),lookTitle=node('h3'),lookChoices=node('div','cl-look-choices');
   lookPicker.id='clLookChooser';lookPicker.hidden=true;lookTitle.id='clLookTitle';
   lookPicker.setAttribute('aria-labelledby',lookTitle.id);
   lookHeading.append(lookTitle,button('收起',()=>closeLook(state)));
   const supplement=node('section','cl-guide-panel');
   let supplementTab=null;
   supplement.id='clBrowseSupplement';supplement.hidden=true;
   lookPicker.append(lookHeading,lookChoices);aux.append(info,lookPicker,supplement);
   if(form.guide){
     const extra=node('div','cl-guide-tabs');
     supplementTab=button('待补与校对',()=>showBrowseSupplement(state));
     supplementTab.setAttribute('aria-controls',supplement.id);
     supplementTab.setAttribute('aria-expanded','false');
     extra.append(supplementTab);
     tools.append(extra);
   }
   const inspect=button('资产信息',()=>{
     closeLook(state,false);closeBrowseSupplement(state);
     info.hidden=!info.hidden;fields.hidden=info.hidden;
     if(!info.hidden&&state.displayed)browseFields(state,state.displayed.row);
     inspect.setAttribute('aria-expanded',String(!info.hidden));
   });
   inspect.setAttribute('aria-expanded','false');inspect.setAttribute('aria-controls',info.id);fields.hidden=true;
   const retryBrowse=button('重试预览',()=>void browseSelect(state,state.requested,state.retryWhole));
   retryBrowse.hidden=true;
   const full=button('全身',()=>void showFrontFigure(state));
   controls.append(full,originalButton,cropButton,inspect,retryBrowse);
   caption.append(stageTitle,stageKind);
   const footerHead=node('div','cl-browse-footer-head'),metadata=node('div','cl-browse-metadata');
   footerHead.append(controls);
   metadata.append(footerHead,feedback,caption,guideSelection,empty);
   ringFrame.append(...ring,stage);arena.append(ringFrame);
   body.append(arena,metadata);
   const layout=node('div','cl-browse-layout'),visual=node('section','cl-browse-visual');
   visual.append(tools,body,aux);
   const profile=characterProfile(person,form,identity);
   layout.append(visual,profile);
   root.append(header,layout,tooltip);
   const state={root,layout,view,person,form,trigger,rows:[...form.rows,...person.forms.flatMap(shape=>shape.rows)],slots:new Map(),ring,
     empty,selection:0,stageSelection:0,tooltip,
     info,inspect,lookPicker,lookTitle,lookChoices,lookTriggers:new Map(),
     stage,stagePhoto,stageTitle,stageKind,feedback,fields,originalButton,cropButton,guideSelection,supplement,supplementTab,retryBrowse,
     exhibit,exhibitGroups,exhibitItems:[],exhibitOpen:false,shelfReturn,figureEntries:[]};
   attachRuler(state,profile,metadata,full);
   const makeSet=button('制作整套形象资产',()=>setTrial.open(state,makeSet));
   makeSet.id='clCharacterSetTrial';
   makeSet.disabled=!form.rows.some(row=>row.file?.sha256&&!row.browseArchived&&row.use!=='voice'&&row.use!=='model');
   controls.append(makeSet);
   state.fullTool=button(undefined,()=>void toggleCompleteLook(state));
   state.fullTool.className='cl-browse-tile cl-full-look';
   state.fullTool.dataset.look='complete';
   nameRingButton(state,state.fullTool,'全貌 · 正面完整造型');
   state.fullTool.append(ringSymbol('fullLook'));
   const directory={...browseGroups,...(form.guide?{base:'人物基准',features:'头部与五官',details:'手脚'}:{}),
     ...(form.rows.some(row=>row.browseArchived)?{history:'历史'}:{})};
   for(const [key,label] of [['','全部'],...Object.entries(directory)]){
     const tile=button(label,()=>browseRing(state,key));
     tile.dataset.group=key;tile.setAttribute('aria-pressed','false');tile.setAttribute('aria-controls',body.id);
     categories.append(tile);state.slots.set(key,tile);
   }
   for(const [type,label] of Object.entries(lookLabels)){
     const relevant=type==='hair'?['hair']:['wardrobe','accessories'];
     const available=form.rows.some(row=>relevant.includes(browseGroup(row)));
     const control=button(undefined,available?()=>{
       if(type==='hair'){openLook(state,type);return;}
       closeBrowseLayers(state,true);
       state.exhibitOpen=!state.exhibitOpen;paintExhibit(state);
     }:null);
     control.className='cl-browse-tile cl-look-entry';control.dataset.look=type;
     control.dataset.ringSlot=label;
     control.setAttribute('aria-expanded','false');
     control.setAttribute('aria-controls',type==='hair'?lookPicker.id:exhibit.id);
     if(available)nameRingButton(state,control,label);
     else markMissingSlot(state,control,label);
     control.append(ringSymbol(type==='hair'?'hair':'outfit'));state.lookTriggers.set(type,control);
   }
   buildExhibit(state);
   root.addEventListener('click',event=>{
     if(event.target.closest('button,input,select,textarea,label,a,summary,img,svg,audio,video,.cl-browse-aux'))return;
     closeBrowseLayers(state,true);
   });
   layout.addEventListener('scroll',()=>{tooltip.hidden=true;state.tooltipOwner=null;},true);
   return {state,back};
 }
 function showDetail(view,person,row,trigger,openSlot,revision){
   const sourceForm=person.forms.find(shape=>shape.id===row.form.id);
   if(!sourceForm)return;
   const nextForm=view.picking?sourceForm:scopedBrowseForm(sourceForm,row,revision);
   if(!view.picking){
     const selected=nextForm.rows.find(value=>value.id===row.id);
     const rejected=selected?.appearance?.format==='full_look'&&!acceptedFullLook(selected)&&!selected.browseArchived;
     row=(rejected?null:selected)||browseHome(nextForm);
     if(!row)return;
   }
   disposeGear();
   const {state,back}=(view.picking?makeGearPage:makeBrowsePage)(view,person,nextForm,trigger);
   gearPage=state;detailTrigger=trigger;
   if(!detail.open)detail.showModal();
   if(document.activeElement===document.body||!state.root.contains(document.activeElement))back.focus({preventScroll:true});
   rememberGear(state,row);
   if(!view.picking){
     browseRing(state,row.browseArchived?'history':'');
     void visitBrowse(state,browseEntry(state.rows,row));
   }
   if(openSlot&&state.slots.has(openSlot))showOptions(state,openSlot,state.slots.get(openSlot),row);
 }
 const importProject=$('clImportProject'),importFile=$('clImportFile'),importPath=$('clImportPath'),
   importStatus=$('clImportStatus'),importRows=$('clImportRows'),apply=$('clImportApply'),review=$('clImportReview'),
   browse=$('clImportBrowse'),fileBrowser=$('clImportBrowser'),chosen=$('clImportChosen');
 function resetImport(){
   importEpoch++;importPlan=null;apply.disabled=true;review.disabled=false;
   importRows.replaceChildren();importStatus.textContent='';chosen.textContent='';
 }
 function showImport(view){
   resetImport();importFile.value='';importPath.value='';fileBrowser.hidden=true;
   importProject.replaceChildren(...projects.filter(row=>!row.unavailable).map(row=>{
     const item=node('option','',row.name);item.value=row.id;return item;
   }));
   if(view.project&&projects.some(row=>row.id===view.project&&!row.unavailable))importProject.value=view.project;
   browse.disabled=review.disabled=!importProject.options.length;
   if(review.disabled)importStatus.textContent=t('请先在项目与 Skills 中登记项目。');
   importer.showModal();
 }
 function acceptPlan(project_id,source,plan){
   importPlan={project_id,source,expected_revision:plan.revision};
   chosen.textContent=source.path;
   const available={available:'原图可用',missing:'缺少原图',unavailable:'原图校验失败'},
     entry={new:'新版本',existing:'已登记',conflict:'版本冲突'};
   importRows.replaceChildren(...plan.assets.map(row=>node('li','',
     [row.name,row.id,t(stateText[row.status]),t(messages[row.availability_reason]||available[row.availability]),t(entry[row.entry])].join(' · '))));
   apply.disabled=plan.assets.some(row=>row.entry==='conflict'||(row.status==='current'&&row.entry==='new'&&row.availability!=='available'));
   importStatus.textContent=t(apply.disabled?'请先处理冲突或不可用的当前版本。':'索引预览已就绪。');
 }
 async function browseFolder(directory=''){
   resetImport();
   const token=importEpoch,project_id=importProject.value;
   fileBrowser.hidden=false;
   fileBrowser.replaceChildren(node('p','','正在读取项目目录…'));
   try{
     const result=await projectMedia('character_manifest_files',{project_id,...(directory?{directory}:{})});
     if(token!==importEpoch||!importer.open)return;
     const relative=name=>directory?directory+'/'+name:name;
     const parent=directory.split('/').slice(0,-1).join('/');
     const caption=node('strong');caption.textContent=directory||t('项目根目录');
     const items=[caption];
     if(directory)items.push(button('返回上一级',()=>void browseFolder(parent)));
     for(const name of result.folders){
       const folder=button(name,()=>void browseFolder(relative(name)));
       folder.className='cl-directory';folder.textContent=name;folder.setAttribute('aria-label',name);items.push(folder);
     }
     for(const name of result.files){
       const file=button('',()=>void pickManifest(project_id,relative(name)));
       file.textContent=name;items.push(file);
     }
     if(!result.folders.length&&!result.files.length)items.push(node('p','','此目录没有可选的索引。'));
     fileBrowser.replaceChildren(...items);
   }catch(problem){
     if(token===importEpoch)fileBrowser.replaceChildren(node('p','',importError(problem)));
   }
 }
 async function pickManifest(project_id,path){
   resetImport();const token=importEpoch;chosen.textContent=path;
   try{
     const plan=await projectMedia('character_manifest_pick',{project_id,path});
     if(token!==importEpoch||!importer.open)return;
     if(plan.source?.path!==path)throw Error('DIRECTOR_CHARACTER_MANIFEST_CHANGED');
     fileBrowser.hidden=true;acceptPlan(project_id,plan.source,plan);
   }catch(problem){if(token===importEpoch)importStatus.textContent=importError(problem);}
 }
 browse.onclick=()=>fileBrowser.hidden?void browseFolder():(fileBrowser.hidden=true,resetImport());
 importProject.onchange=()=>{fileBrowser.hidden=true;importFile.value='';importPath.value='';resetImport();};
 importPath.oninput=resetImport;
 importFile.onchange=resetImport;
 $('clImportClose').onclick=()=>importer.close();importer.addEventListener('close',resetImport);
 review.onclick=async()=>{
   if(![importProject,importFile,importPath].every(field=>field.reportValidity()))return;
   resetImport();const token=importEpoch;review.disabled=true;fileBrowser.hidden=true;
   const project_id=importProject.value,path=importPath.value.trim(),file=importFile.files[0];
   try{
     if(!file||!crypto.subtle)throw Error('DIRECTOR_CHARACTER_MANIFEST_INVALID');
     const hash=await crypto.subtle.digest('SHA-256',await file.arrayBuffer());
     const sha256=Array.from(new Uint8Array(hash),v=>v.toString(16).padStart(2,'0')).join('');
     const source={path,sha256};const plan=await action('character_import_preview',{project_id,source});
     if(token!==importEpoch||!importer.open)return;
     acceptPlan(project_id,source,plan);
   }catch(problem){if(token===importEpoch)importStatus.textContent=importError(problem);}
   finally{if(token===importEpoch)review.disabled=false;}
 };
 importPath.addEventListener('keydown',event=>{
   if(event.key==='Enter'&&!review.disabled){event.preventDefault();review.click();}
 });
 apply.onclick=async()=>{
   const plan=importPlan,token=importEpoch;if(!plan)return;apply.disabled=true;
   try{
     const result=await edit('character_import',plan);
     if(token!==importEpoch)return;
     importStatus.textContent=t(result.state==='UNCHANGED'?'这些版本已登记。':'登记完成。');
     await refresh();
   }catch(problem){if(token===importEpoch){importStatus.textContent=importError(problem);apply.disabled=false;}}
 };
 function choose(project,accept,trigger,work,mediaKind){
   pickerSession={project,work,mediaKind,choose:accept,trigger};selection.project=project;selection.search.value='';
   syncProjects(selection);picker.showModal();render(selection);void refresh();
 }
 $('clPickerClose').onclick=()=>picker.close();
 picker.addEventListener('close',()=>{
   if(picker.open)return;
   if(detail.open)closeDetail();
   const trigger=pickerSession?.trigger;pickerSession=null;if(trigger?.isConnected)trigger.focus();
 });
 return {
   open(){
     if(!page.hidden)return;
     restoreBrowser=true;page.hidden=false;void refresh();
   },
   focus(){browser.title.focus();},
   close(){
     if(!page.hidden){keepBrowser();restoreBrowser=false;page.hidden=true;browserDetail=false;}
     setTrial.close();closeDetail();if(picker.open)picker.close();if(importer.open)importer.close();
   },
   closePicker(){if(picker.open){closeDetail();picker.close();}},
   choose,
   readOriginal:exactMedia,
 };
}
'''

STYLE += SET_TRIAL_STYLE
SCRIPT = SET_TRIAL_SCRIPT + SCRIPT
