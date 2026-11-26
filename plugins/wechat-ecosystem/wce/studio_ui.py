"""L-unify Studio assets for the normal, self-contained MCP management page."""
from functools import lru_cache
from pathlib import Path

ASSETS = Path(__file__).resolve().parents[1] / 'assets' / 'studio'
STYLE = """
body.oa-native[data-workbench=l-unify] #wbMusic {
 padding:max(var(--wb-top),env(safe-area-inset-top)) var(--wb-tool-gutter) 0;overflow:hidden
}
body.oa-native[data-workbench] #wbMusic>.lus-workspace {
 max-width:none;height:100%;display:flex;flex-direction:column;gap:0
}
#wbMusic .wb-music-links { margin:0;flex-wrap:wrap;gap:4px;justify-content:flex-end }
#wbMusic .wb-music-links button { min-height:24px;font-size:11px;padding:3px 6px;white-space:nowrap }
#wbMusic lus-studio { flex:1;min-height:0;display:block }
/* Slotted controls remain in light DOM so the native media host and command handlers retain them. */
#wbMusic lus-studio[data-imw-video] > #directorMonitor {
 --imw-picture-ratio:16/9;--imw-picture-width:177.77778cqh;
 width:100%;height:100%;padding:0;min-width:0;min-height:0;gap:clamp(6px,1vw,16px);overflow:hidden;
 grid-template-columns:minmax(0,1fr) minmax(0,min(57%,960px)) minmax(0,1fr);
 grid-template-rows:minmax(0,1fr);grid-template-areas:"tools monitor assistant";
}
#wbMusic lus-studio[data-imw-aspect=portrait] > #directorMonitor {
 --imw-picture-ratio:9/16;--imw-picture-width:56.25cqh;
 grid-template-columns:minmax(0,30%) repeat(2,minmax(0,1fr));grid-template-areas:"monitor tools assistant";
}
#wbMusic lus-studio[data-imw-video] #directorMonitor .dm-main {
 container-type:size;position:relative;display:grid;min-height:0;padding:0;border:0;border-radius:0;
 background:transparent;box-shadow:none;align-items:center;justify-items:center;overflow:hidden;
}
#wbMusic lus-studio[data-imw-video] #dmScreenTitle {
 position:absolute;width:1px;height:1px;overflow:hidden;clip-path:inset(50%);
}
#wbMusic lus-studio[data-imw-video] #directorMonitor .dm-main :is(#dmScreen,#dmCutPreview) {
 box-sizing:border-box;display:grid;position:relative;place-content:stretch;place-items:center;
 grid-template: minmax(0,1fr) / minmax(0,1fr);min-height:0;
 width:min(var(--imw-frame-fit,100cqw),var(--imw-picture-width));height:auto;aspect-ratio:var(--imw-picture-ratio);
 overflow:hidden;background:#151619;border-radius:6px;
}
#wbMusic lus-studio[data-imw-aspect=portrait] #directorMonitor .dm-main {justify-items:start}
#wbMusic lus-studio[data-imw-video] #directorMonitor .dm-main :is(#dmScreen,#dmCutPreview)
 :is(.oa-frame-player,.oa-inline-video-player,.oa-frame-screen,video,.oa-video-poster,.dm-screen-empty),
#wbMusic lus-studio[data-imw-video] #directorMonitor .dm-main #dmScreen[data-kind=image]>img {
 box-sizing:border-box;width:100%;height:100%;max-height:none;aspect-ratio:auto;object-fit:contain;border-radius:0;
}
#wbMusic lus-studio[data-imw-video] #directorMonitor .dm-main .oa-video-poster {background-size:contain}
#wbMusic lus-studio[data-imw-video] #directorMonitor :is(#dmEditColumn,.dm-sidebar) {
 min-height:0;min-width:0;max-height:100%;height:auto;align-self:start;display:flex;flex-direction:column;
 gap:8px;padding:0 2px 4px;border:0;background:transparent;box-shadow:none;
 overflow:auto;overscroll-behavior:contain;scrollbar-width:thin;
}
#wbMusic lus-studio[data-imw-video] #dmEditColumn {grid-area:tools}
#wbMusic lus-studio[data-imw-video] #directorMonitor :is(#dtEditRail,#dtAddRail) {
 position:static;inset:auto;transform:none;display:grid;isolation:auto;width:100%;max-height:none;padding:0;gap:4px;
}
#wbMusic lus-studio[data-imw-video] #directorMonitor .dt-rail :is(.wb-notch-shell,.dt-toggle) {
 position:fixed;inset:auto;top:47%;transform:translateY(-50%);z-index:8;
 box-sizing:border-box;width:var(--wb-side-width);height:clamp(92px,17dvh,152px);margin:0;
}
#wbMusic lus-studio[data-imw-video] #directorMonitor .dt-rail .wb-notch-shell {display:block;pointer-events:none}
#wbMusic lus-studio[data-imw-video] #directorMonitor #dtEditRail :is(.wb-notch-shell,.dt-toggle) {left:0}
#wbMusic lus-studio[data-imw-video] #directorMonitor #dtAddRail :is(.wb-notch-shell,.dt-toggle) {right:0}
#wbMusic lus-studio[data-imw-video] #directorMonitor .dt-rail .dt-list {
 display:grid;grid-template-columns:repeat(auto-fill,minmax(min(60px,100%),1fr));gap:3px;overflow:visible;
}
#wbMusic lus-studio[data-imw-video] #directorMonitor .dt-rail button {
 width:100%;height:auto;min-height:30px;display:flex;align-items:center;justify-content:flex-start;gap:5px;padding:4px;
 flex-direction:row;text-align:start;font-size:11px;
}
#wbMusic lus-studio[data-imw-video] #directorMonitor .dt-rail .dt-toggle {
 position:fixed;z-index:9;width:var(--wb-side-width);height:clamp(92px,17dvh,152px);
 flex-direction:column;justify-content:center;gap:4px;border:0;border-radius:0;font-size:11px;font-weight:600;
}
#wbMusic lus-studio[data-imw-video] #directorMonitor .imw-aspect-field {
 order:-1;display:flex;flex-wrap:wrap;align-items:center;justify-content:space-between;gap:4px 8px;padding:4px;
 font-size:12px;
}
#wbMusic lus-studio[data-imw-video] #imwFrameAspect {width:auto;min-width:0;max-width:100%;padding:3px 5px}
#wbMusic lus-studio[data-imw-video] #directorMonitor .dm-sidebar>details {padding:5px 4px}
#wbMusic lus-studio[data-imw-video] #directorMonitor #daComposer {display:grid;gap:7px;padding:7px 0}
#wbMusic lus-studio[data-imw-video] #directorMonitor #daTitle {display:none}
#wbMusic lus-studio[data-imw-video] #directorMonitor[data-dt-view]:not([data-dt-view=""]) #dmCodexDetails {display:none}
#wbMusic lus-studio[data-imw-video] #directorMonitor :is(#dmEditFields,#dmAddFields):empty {display:none}
#wbMusic lus-studio[data-imw-video] #directorMonitor :is(#dtPanel,#dmCutSettings) {
 grid-area:auto;border:0;background:transparent;box-shadow:none;margin:0;padding:4px;
}
#wbMusic lus-studio[data-imw-video] #directorMonitor #daManualBack {margin:0 0 6px}
#wbMusic lus-studio[data-imw-video] #directorMonitor .dm-sidebar>.dc-delivery {padding:5px 4px}
#wbMusic lus-studio[data-imw-video] #dmCut {
 display:block;box-sizing:border-box;width:100%;padding:0;border:0;box-shadow:none;border-radius:0
}
#wbMusic lus-studio[data-imw-video] #dmCutTracks {
 box-sizing:border-box;border:0;border-radius:0;background:transparent
}
#wbMusic lus-studio[data-imw-video] #dmCut {background:transparent}
#wbMusic lus-studio[data-imw-video] #dmCut :is(#dmCutRuler,#dmCutVideoHeight,#dmCutAudioHeight,#dmCutNeedle),
#wbMusic lus-studio[data-imw-stems] #dmCutMusicLane{display:none!important}
#wbMusic lus-studio[data-imw-video] :is(#dmCut .track-row,#dmCutMusicLane.track-row) {
 display:block;position:relative;overflow:visible;border:0;padding:0;min-height:0;
 background:transparent;box-sizing:border-box;
}
/* Adjacent video regions share an edit point. Give each side its own half of the handle. */
#wbMusic lus-studio[data-imw-video] #dmCutStrip .trim-handle.head {left:-10px;width:20px;clip-path:inset(0 0 0 50%)}
#wbMusic lus-studio[data-imw-video] #dmCutStrip .trim-handle.tail {right:-10px;width:20px;clip-path:inset(0 50% 0 0)}
#wbMusic lus-studio[data-imw-video] #dmCutStrip {--track-height:var(--imw-video-row-height,100px);--imw-thumb-width:min(40%,132px);height:var(--track-height);--tone:var(--imw-video-tone,var(--focus))}
#wbMusic lus-studio[data-imw-video] #dmCutMusicLane {height:var(--imw-score-row-height,var(--track-height,62px));--tone:var(--imw-score-tone,var(--focus))}
#wbMusic lus-studio[data-imw-video] :is(#dmCut[data-imw-clips],#dmCutMusicLane.track-row) .clip {min-width:0;min-height:0;outline:0}
#wbMusic lus-studio[data-imw-video] :is(#dmCut[data-imw-clips],#dmCutMusicLane.track-row) .clip-group {background:transparent;border:0;padding:0;overflow:visible}
#wbMusic lus-studio[data-imw-video] :is(#dmCut[data-imw-clips],#dmCutMusicLane.track-row) .clip-group :is(.dc-frame,.dc-song-wave,.dc-source-wave) {
 position:absolute;pointer-events:none;min-width:0;
}
#wbMusic lus-studio[data-imw-video] #dmCutStrip .clip {
 --wave-height:0px; overflow:hidden; isolation:isolate;
}
#wbMusic lus-studio[data-imw-video] #dmCutStrip .clip:has(.dc-source-wave) {
 --wave-height:clamp(15px,26%,30px);
}
#wbMusic lus-studio[data-imw-video] #dmCutStrip .clip .dc-film {
 position:absolute;inset:0 0 var(--wave-height);overflow:hidden;pointer-events:none;
}
#wbMusic lus-studio[data-imw-video] #dmCutStrip .dc-film .dc-frame {
 position:absolute;inset:0 auto auto 0;height:100%;max-width:none;object-fit:cover;opacity:1;
}
#wbMusic lus-studio[data-imw-video] #dmCutStrip .dc-frame:not([src]) {visibility:hidden}
#wbMusic lus-studio[data-imw-video] #dmCutStrip .clip strong {
 position:absolute;inset:0 0 auto;padding:2px 5px;max-width:none;text-align:start;
 color:white;background:linear-gradient(#000a,transparent);white-space:nowrap;text-overflow:ellipsis;
 overflow:hidden;font:550 11px/1.3 system-ui;pointer-events:none;
}
#wbMusic lus-studio[data-imw-video] #dmCutStrip .clip small {display:none}
#wbMusic lus-studio[data-imw-video] #dmCutStrip .clip .dc-source-wave {
 position:absolute;inset:auto 0 0;width:100%;height:var(--wave-height);color:var(--tone);
 background:color-mix(in srgb,var(--tone) 15%,var(--bg));
}
#wbMusic lus-studio[data-imw-video] :is(#dmCut[data-imw-clips],#dmCutMusicLane.track-row) .clip .dc-song-wave {
 inset:8px 0;width:100%;height:calc(100% - 16px);color:var(--tone);
}
#wbMusic lus-studio[data-imw-video] :is(#dmCut[data-imw-clips],#dmCutMusicLane.track-row) .trim-handle {
 box-sizing:border-box;min-width:0;min-height:0;
}
#wbMusic lus-studio[data-imw-video] :is(#dmCut[data-imw-clips],#dmCutMusicLane.track-row) .clip-group[data-tight] :is(strong,small){display:none}
#wbMusic lus-studio[data-imw-video] :is(#dmCut[data-imw-clips],#dmCutMusicLane.track-row) #dmCutMusicSpan {bottom:auto;cursor:grab}
#wbMusic lus-studio[data-imw-video]:has(#dmCutMusicSpan:focus-within) #dmCutStrip .clip::after{visibility:hidden}
#wbMusic lus-studio[data-imw-video] :is(#dmCut,#directorMonitor) [hidden],
#wbMusic lus-studio[data-imw-video] :is(#dmCut,#dmCutMusicLane,#directorMonitor)[hidden]{display:none!important}
@media(max-width:760px){
 #wbMusic lus-studio[data-imw-video] > #directorMonitor {
  grid-template-columns:repeat(2,minmax(0,1fr));grid-template-rows:minmax(0,1fr) minmax(0,min(34%,138px));
  grid-template-areas:"monitor monitor" "tools assistant";gap:5px 8px;
 }
 #wbMusic lus-studio[data-imw-aspect=portrait] > #directorMonitor {
  grid-template-columns:minmax(0,43%) minmax(0,1fr);grid-template-rows:repeat(2,minmax(0,1fr));
  grid-template-areas:"monitor tools" "monitor assistant";
 }
 #wbMusic lus-studio[data-imw-video] #directorMonitor .dt-rail .dt-list {
  grid-template-columns:repeat(auto-fill,minmax(min(56px,100%),1fr));
 }
}
"""


STYLE += "\n#wbMusic lus-studio[data-imw-motion] > #directorMonitor {height:var(--imw-reveal-height,100%)}\n"

@lru_cache(maxsize=2)
def resource(kind):
    if kind == 'css':
        raw = (ASSETS / 'transport-shell.css').read_text()
        clip_rules = (ASSETS / 'studio-clips.css').read_text()
        scoped_clips = '#wbMusic lus-studio[data-imw-video] :is(#dmCut[data-imw-clips],#dmCutMusicLane.track-row) {\n' + clip_rules + '\n}'
        return raw + scoped_clips + STYLE + (ASSETS / 'home.css').read_text()
    return (ASSETS / 'studio.bundle.js').read_text().replace('</script', '<\\/script')
