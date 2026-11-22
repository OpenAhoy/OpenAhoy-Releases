"""Asset categories and the project-scoped image browser."""

from .source_library_ui import HTML as source_library_html

KINDS = {
    'characters': ('形象', 'characterLibrary', 'M20 21v-2a4 4 0 0 0-4-4H8a4 4 0 0 0-4 4v2M16 7a4 4 0 1 1-8 0 4 4 0 0 1 8 0Z'),
    'images': ('图片', 'imageAssetLibrary', 'M4 4h16v16H4zM4 16l5-5 4 4 3-3 4 4M14 8h1'),
    'gif': ('动图', 'mediaMonitor', 'M3 4h18v16H3zM8 4v16m8-16v16'),
    'video': ('视频', 'mediaMonitor', 'M3 5h18v14H3zM10 9l5 3-5 3z'),
    'audio': ('音频', 'mediaMonitor', 'M3 12h2m3-4v8m4-12v16m4-12v8m3-4h2'),
    'sources': ('信源库', 'sourceLibrary', 'M10 13a4 4 0 0 0 6 0l3-3a4 4 0 0 0-6-6l-2 2m3 5a4 4 0 0 0-6 0l-3 3a4 4 0 0 0 6 6l2-2'),
    'articles': ('文章', 'articleAssetLibrary', 'M5 3h10l4 4v14H5zM9 11h6m-6 4h6m-6 3h4'),
}


def gallery_tile(key, title, target):
    return (
        f'<article class="ja-exhibit" data-kind="{key}">'
        '<div class="ja-exhibit-media"></div><div class="ja-exhibit-meta">'
        f'<button type="button" class="ja-category" data-asset-kind="{key}" aria-controls="{target}">'
        f'<span>{title}</span><span aria-hidden="true">↗</span></button>'
        '<p class="ja-exhibit-title"></p><p class="ja-exhibit-owner"></p></div>'
        '<button type="button" class="ja-next" hidden><span>换一件</span></button></article>'
    )


HTML = (
    """
<section id="directorAssetKinds" aria-label="资产展示" hidden>
 <div class="ja-gallery-bar">
  <label><span>项目</span><select id="jaGalleryProject" aria-label="选择资产项目"><option value="">全部项目</option></select></label>
  <button type="button" data-asset-kind="sources" aria-controls="sourceLibrary">信源库</button>
  <button type="button" id="jaGalleryRefresh">刷新</button>
 </div>
 <div class="ja-gallery-bounds"><div class="ja-gallery">
""" + ''.join(gallery_tile(key,title,target) for key,(title,target,_) in KINDS.items() if key!='sources') + """
 </div></div>
 <dialog id="jaGalleryDetail" aria-labelledby="jaGalleryDetailTitle">
  <header><h2 id="jaGalleryDetailTitle"></h2><button id="jaGalleryClose" type="button">关闭</button></header>
  <div id="jaGalleryOriginal" class="ja-gallery-original"></div>
  <section id="jaGalleryReader" class="aw-asset-detail" hidden></section>
 </dialog>
</section>
"""
    + '''
<section id="imageAssetLibrary" aria-label="图片资产" hidden>
 <div class="ja-image-tools">
  <label>项目<select id="jaImageProject"></select></label>
  <label>搜索资产<input id="jaImageSearch" type="search"></label>
  <button id="jaImageRefresh" type="button">刷新</button>
 </div>
 <p id="jaImageStatus" role="status"></p>
 <div class="ja-image-columns">
  <div id="jaImageList" aria-label="图片列表"></div>
  <article id="jaImageDetail" tabindex="-1"></article>
 </div>
</section>
<section id="articleAssetLibrary" aria-label="文章资产" hidden></section>
''' + source_library_html
)

STYLE = '''
.oa-management.oa-native[data-workbench=assets]:not(.oa-platform-view) #videoDirectorDesk {
 overflow:hidden;scrollbar-gutter:auto;gap:10px
}
[data-workbench=assets] #videoDirectorDesk>.dd-toolbar {flex:none}
[data-workbench=assets] #videoDirectorDesk #mediaMonitor,
[data-workbench=assets] #characterLibrary,
[data-workbench=assets] #imageAssetLibrary,
[data-workbench=assets] #articleAssetLibrary {flex:1 1 0;min-height:0;min-width:0}
[data-workbench=assets] #articleAssetLibrary {overflow:auto;overscroll-behavior:contain}
[data-workbench=assets] #directorAssetKinds {
 flex:1;min-height:0;min-width:0;display:grid;align-items:stretch;grid-template-rows:auto minmax(0,1fr);gap:9px;
 --ja-paper:light-dark(#f5eee1,#342d29);
 --ja-paper-ink:light-dark(#352623,#f3e9db);
 --ja-on-media:#fff6e9;
}
[data-workbench=assets]:has(#directorAssetKinds:not([hidden])) #videoDirectorDesk{
 padding-inline:clamp(8px,1.2vw,20px);
}
[data-workbench=assets]:has(#directorAssetKinds:not([hidden])) #videoDirectorDesk .dd-footer{display:none}
.ja-gallery-bar{display:flex;align-items:center;gap:6px;min-width:0;min-height:31px}
#directorAssetKinds .ja-gallery-bar label{display:flex;min-width:0;align-items:center;gap:6px;margin-inline-end:auto}
.ja-gallery-bar label span{color:var(--muted);font-size:12px;flex:none}
#directorAssetKinds .ja-gallery-bar select{max-width:min(44vw,320px);min-width:0;width:auto}
.ja-gallery-bar button{min-height:28px;font-size:12px;flex:none}
.ja-gallery-bounds{min-width:0;min-height:0;container-type:size}
.ja-gallery{display:grid;height:100%;min-height:0;min-width:0;gap:9px;
 --ja-portrait-size:min(31cqw,55cqh);
 grid-template-columns:var(--ja-portrait-size) minmax(0,1.1fr) minmax(0,.8fr) minmax(0,1.03fr);
 grid-template-rows:var(--ja-portrait-size) minmax(0,1fr);
 grid-template-areas:"characters video video articles" "images images gif audio"}
.ja-exhibit{min-width:0;min-height:0;isolation:isolate;position:relative;overflow:hidden;
 border-radius:13px;background:var(--soft);color:var(--ink)}
.ja-exhibit[data-kind=characters]{grid-area:characters;background:#393234}
.ja-exhibit[data-kind=video]{grid-area:video;background:#151c22}
.ja-exhibit[data-kind=images]{grid-area:images;background:#313b3c}
.ja-exhibit[data-kind=gif]{grid-area:gif;background:#283138}
.ja-exhibit[data-kind=audio]{grid-area:audio;background:light-dark(#e8ebdf,#24302c)}
.ja-exhibit[data-kind=articles]{grid-area:articles;background:var(--ja-paper);color:var(--ja-paper-ink)}
.ja-exhibit-media{position:absolute;inset:0;min-height:0;display:grid;place-items:stretch;overflow:hidden}
.ja-exhibit-media>img,.ja-exhibit-media>video,.ja-exhibit-media>canvas{width:100%;height:100%;object-fit:cover;display:block}
.ja-exhibit[data-kind=characters]{--ja-portrait-caption:clamp(29px,15cqh,54px)}
.ja-exhibit[data-kind=characters] .ja-exhibit-media>img{
 height:calc(100% - var(--ja-portrait-caption));object-fit:contain;
 object-position:center;align-self:start;background:var(--ja-portrait-ground,#393234)
}
.ja-exhibit[data-kind=video] .ja-exhibit-media>img{object-fit:cover}
.ja-exhibit[data-kind=gif] .ja-exhibit-media>img{object-fit:cover}
.ja-exhibit-meta{position:absolute;z-index:3;inset:auto 0 0;padding:clamp(8px,1.2vw,17px);min-width:0}
.ja-exhibit:is([data-kind=characters],[data-kind=images],[data-kind=video],[data-kind=gif]) .ja-exhibit-meta{
 color:var(--ja-on-media);background:linear-gradient(transparent,#090c10cb);
 padding-top:clamp(19px,3vw,46px);pointer-events:none
}
#directorAssetKinds .ja-exhibit[data-kind=characters] .ja-exhibit-meta{
 box-sizing:border-box;height:var(--ja-portrait-caption);display:flex;flex-direction:column-reverse;
 justify-content:center;align-items:flex-start;gap:0;padding:4px 9px;background:#231d25
}
#directorAssetKinds .ja-exhibit[data-kind=characters]:has(.ja-next:not([hidden])) .ja-exhibit-meta{
 padding-inline-end:66px
}
#directorAssetKinds .ja-exhibit[data-kind=characters] .ja-exhibit-title{
 flex:none;max-width:100%;font-size:clamp(12px,1.35vw,19px);line-height:1.16;
 -webkit-line-clamp:1;margin:0
}
.ja-exhibit[data-kind=characters] .ja-exhibit-owner{display:none}
#directorAssetKinds .ja-exhibit[data-kind=characters]:not([data-state=ready]) .ja-exhibit-meta{background:none;color:var(--ink)}
.ja-exhibit[data-kind=characters] .ja-exhibit-media>p{margin-bottom:var(--ja-portrait-caption)}
#directorAssetKinds .ja-exhibit-title{font-size:clamp(13px,1.3vw,22px);line-height:1.13;font-weight:650;
 margin:2px 0;display:-webkit-box;-webkit-box-orient:vertical;-webkit-line-clamp:2;overflow:hidden;overflow-wrap:anywhere}
#directorAssetKinds .ja-exhibit-owner{margin:4px 0 0;opacity:.76;font-size:11px;line-height:1.1;text-overflow:ellipsis;white-space:nowrap;overflow:hidden}
.ja-exhibit :is(.ja-exhibit-owner,.ja-exhibit-title):empty{display:none}
#directorAssetKinds :is(.ja-category,.ja-next,.ja-preview-btn){
 min-height:25px;min-width:25px;padding:3px 6px;gap:4px;font-size:11px;line-height:1;border:1px solid transparent;
 color:inherit;box-shadow:none;pointer-events:auto
}
#directorAssetKinds .ja-category{background:transparent;padding-inline:0;font-weight:640}
#directorAssetKinds .ja-category:hover{text-decoration:underline;text-underline-offset:3px}
#directorAssetKinds .ja-next{position:absolute;z-index:3;right:7px;top:7px;background:var(--wb-float);color:var(--ink);border-color:var(--wb-line);border-radius:7px}
#directorAssetKinds .ja-exhibit[data-kind=characters] .ja-next{top:auto;bottom:7px}
#directorAssetKinds .ja-exhibit[data-kind=characters] .ja-category{
 flex:none;border:0;min-width:0;min-height:17px;padding:0;gap:3px
}
#directorAssetKinds .ja-preview-btn{
 position:absolute;z-index:2;place-self:center;border-radius:50%;width:43px;height:43px;justify-content:center;
 background:#171d22c9;color:#fff;border-color:#ffffff4c;padding:0;font-size:17px
}
#directorAssetKinds .ja-exhibit[data-kind=images] .ja-preview-btn,
#directorAssetKinds .ja-exhibit[data-kind=characters] .ja-preview-btn,
#directorAssetKinds .ja-exhibit[data-kind=articles] .ja-preview-btn{
 inset:0;width:100%;height:100%;border:0;border-radius:0;background:transparent
}
#directorAssetKinds .ja-exhibit[data-kind=articles] .ja-preview-btn::after{content:'→';position:absolute;bottom:10px;right:11px;
  font-size:19px;color:var(--ja-paper-ink)}
#directorAssetKinds .ja-exhibit:focus-within .ja-category{outline-offset:1px}
.ja-exhibit:has(.ja-preview-btn:focus-visible){outline:2px solid var(--accent);outline-offset:-2px}
#directorAssetKinds .ja-preview-btn:hover{filter:brightness(1.28)}
#directorAssetKinds .ja-exhibit[data-kind=articles] .ja-category{z-index:3;position:relative}
.ja-exhibit[data-kind=articles] .ja-exhibit-meta{inset:0 auto auto 0;top:8%;width:100%;pointer-events:none}
#directorAssetKinds .ja-exhibit[data-kind=articles] .ja-exhibit-title{
 font-family:ui-serif,Georgia,"Songti SC",serif;font-size:clamp(17px,2.25vw,43px);font-weight:640;
 letter-spacing:-.035em;line-height:1.05;margin-block:clamp(3px,1.6vh,13px);
 -webkit-line-clamp:3
}
#directorAssetKinds .ja-exhibit[data-kind=articles] .ja-exhibit-owner{
 white-space:normal;display:-webkit-box;-webkit-box-orient:vertical;-webkit-line-clamp:4;
 font-size:clamp(11px,1.05vw,16px);line-height:1.48;margin-block:3px
}
.ja-exhibit[data-kind=articles] .ja-exhibit-owner:empty{display:none}
.ja-exhibit[data-kind=audio] .ja-exhibit-meta{pointer-events:none;inset:auto 0 0;
 background:linear-gradient(transparent,light-dark(#e8ebdf,#24302c) 31%);padding-top:20px}
.ja-record{
 place-self:center;aspect-ratio:1;width:min(68%,24dvh);max-height:76%;border-radius:50%;
 background:
   radial-gradient(circle,#302625 0 3%,#eee1ac 4% 12%,#b6704c 13% 23%,transparent 24%),
   repeating-radial-gradient(circle,#24292a 0 2px,#343a38 3px,#222728 4px);
 box-shadow:0 8px 20px #10221b40;transform:translateY(-13%);opacity:.97
}
.ja-exhibit[data-kind=audio] .ja-exhibit-media:has(audio[data-playing=true]) .ja-record{animation:ja-spin 14s linear infinite}
@keyframes ja-spin{to{transform:translateY(-13%) rotate(1turn)}}
@media(prefers-reduced-motion:reduce){.ja-record{animation:none!important}}
.ja-exhibit .ja-play-detail{
 display:grid;position:absolute;inset:0;grid-template-rows:minmax(0,1fr) auto auto;z-index:1;color:#fff;
}
.ja-play-detail .oa-frame-player{height:100%;min-height:0;grid-template-rows:minmax(0,1fr) auto}
.ja-play-detail :is(video,.oa-frame-screen,.oa-video-poster){width:100%;height:100%;aspect-ratio:auto;object-fit:contain;min-height:0;border-radius:0}
.ja-play-detail .oa-frame-controls{padding:2px 6px}
.ja-play-detail p[role=status]:empty{display:none}
.ja-exhibit[data-kind=video][data-playing=true] .ja-exhibit-meta{
 top:0;bottom:auto;background:linear-gradient(#090c10b9,transparent);padding-top:5px;padding-bottom:9px;z-index:2;width:max-content;max-width:100%;
}
.ja-exhibit[data-playing=true] .ja-exhibit-title,.ja-exhibit[data-playing=true] .ja-exhibit-owner{display:none}
.ja-exhibit-media>p{place-self:center;text-align:center;margin:6px;max-width:80%;font-size:12px;color:inherit}
.ja-exhibit:not([data-state=ready]){background:light-dark(#edeae5,#292724);color:var(--ink)}
.ja-exhibit:not([data-state=ready]) .ja-exhibit-meta{color:var(--ink);background:none}
.ja-exhibit:not([data-state=ready])[data-kind=articles] .ja-exhibit-meta{top:auto;bottom:0}
#jaGalleryDetail{
 box-sizing:border-box;width:min(92vw,980px);height:min(88dvh,820px);min-height:0;max-height:none;
 color:var(--ink);background:var(--surface);border:1px solid var(--line);border-radius:16px;padding:12px;
}
#jaGalleryDetail[open]{display:grid;grid-template-rows:auto minmax(0,1fr);gap:8px}
#jaGalleryDetail::backdrop{background:#10141bc2}
#jaGalleryDetail>header{display:flex;align-items:center;justify-content:space-between;gap:10px}
#jaGalleryDetail h2{min-width:0;margin:0;font-size:15px;overflow-wrap:anywhere}
.ja-gallery-original{min-height:0;overflow:auto;display:grid;place-items:center}
.ja-gallery-original img{width:100%;height:100%;min-height:0;object-fit:contain}
#jaGalleryReader.aw-asset-detail{min-height:0}
#jaGalleryReader .aw-body{grid-template-rows:minmax(0,1fr)}
#jaGalleryDetail[data-kind=articles]>header{justify-content:flex-end}
#jaGalleryDetail[data-kind=articles] h2#jaGalleryDetailTitle{
 position:absolute;width:1px;height:1px;padding:0;overflow:hidden;clip-path:inset(50%);white-space:nowrap
}
@media(max-width:710px){
 .oa-management.oa-native[data-workbench=assets]:has(#directorAssetKinds:not([hidden])) #videoDirectorDesk{
   padding-top:46px;padding-bottom:max(var(--wb-dock),calc(60px + env(safe-area-inset-bottom)));gap:4px
 }
 [data-workbench=assets] #directorAssetKinds{gap:5px}
 .ja-gallery{gap:5px;--ja-portrait-size:min(calc((100cqw - 10px)/3),42cqh);
   grid-template-columns:minmax(0,1fr) minmax(0,1fr) var(--ja-portrait-size);
   grid-template-rows:var(--ja-portrait-size) repeat(2,minmax(0,1fr));
   grid-template-areas:"video video characters" "images images articles" "gif audio articles"}
 .ja-exhibit[data-kind=characters]{--ja-portrait-caption:36px}
 #directorAssetKinds .ja-exhibit[data-kind=characters] .ja-exhibit-meta{padding:3px 5px}
 #directorAssetKinds .ja-exhibit[data-kind=characters]:has(.ja-next:not([hidden])) .ja-exhibit-meta{padding-inline-end:32px}
 #directorAssetKinds .ja-exhibit[data-kind=characters] .ja-category{min-height:13px;font-size:10px}
 #directorAssetKinds .ja-exhibit[data-kind=characters] .ja-next{
   right:3px;bottom:4px;width:26px;min-width:0;min-height:28px;padding:0;justify-content:center
 }
 #directorAssetKinds .ja-exhibit[data-kind=characters] .ja-next span{display:none}
 #directorAssetKinds .ja-exhibit[data-kind=characters] .ja-next::after{
   content:'';width:6px;height:6px;border:solid currentColor;border-width:1.5px 1.5px 0 0;
   transform:translateX(-1px) rotate(45deg)
 }
 .ja-exhibit{border-radius:9px}
 .ja-exhibit-meta{padding:4px 6px}
 .ja-exhibit:is([data-kind=characters],[data-kind=images],[data-kind=video],[data-kind=gif]) .ja-exhibit-meta{padding-top:10px}
 #directorAssetKinds .ja-exhibit-title{font-size:11px;margin:2px 0}
 .ja-exhibit-owner{display:none}
 .ja-exhibit[data-kind=articles] .ja-exhibit-meta{top:0}
 #directorAssetKinds .ja-exhibit[data-kind=articles] .ja-exhibit-title{font-size:12px;letter-spacing:0;margin:2px 0;-webkit-line-clamp:2}
 #directorAssetKinds .ja-exhibit[data-kind=articles] .ja-exhibit-owner{display:-webkit-box;font-size:10px;-webkit-line-clamp:2;line-height:1.15}
 .ja-gallery-bar button,.ja-gallery-bar select{min-height:25px;font-size:11px}
 #directorAssetKinds .ja-gallery-bar select{min-height:25px;font-size:11px}
 #directorAssetKinds .ja-category,#directorAssetKinds .ja-next{font-size:10px;min-height:22px}
 #directorAssetKinds .ja-next{right:3px;top:3px;padding:3px 4px}
 #directorAssetKinds .ja-preview-btn{width:33px;height:33px;font-size:13px}
 .ja-exhibit-media>p{font-size:10px}
 .ja-record{max-height:57%;width:58%}
 .ja-exhibit[data-kind=audio] .ja-exhibit-meta{padding-top:9px}
 #directorAssetKinds .ja-exhibit[data-kind=articles] .ja-preview-btn::after{right:5px;bottom:3px;font-size:13px}
 [data-workbench=assets]:has(#directorAssetKinds:not([hidden])) .dd-toolbar #directorTitle{font-size:16px}
 [data-workbench=assets]:has(#directorAssetKinds:not([hidden])) .dd-toolbar .dd-actions>button{padding:2px 5px;font-size:11px}
 [data-workbench=assets]:has(#directorAssetKinds:not([hidden])) .dd-toolbar #directorMore>summary{padding:2px 5px;font-size:11px}
 #jaGalleryDetail{width:calc(100vw - 14px);height:calc(100dvh - 24px);padding:8px}
}
#jaImageStatus {color:var(--muted)}
#imageAssetLibrary {display:flex;flex-direction:column;gap:7px}
.ja-image-tools {display:flex;align-items:end;flex-wrap:wrap;gap:7px}
.ja-image-tools label {display:grid;gap:3px;flex:1 1 90px;min-width:0;max-width:240px}
.ja-image-columns {display:grid;grid-template-columns:minmax(145px,30%) minmax(0,1fr);gap:8px;
 flex:1;min-height:0}
#jaImageList,#jaImageDetail {min-width:0;min-height:0;overflow:auto;overscroll-behavior:contain;
 border:1px solid var(--line);border-radius:9px;background:var(--surface);padding:8px}
#jaImageList button {display:grid;width:100%;text-align:start;justify-items:start;gap:2px;
 box-shadow:none;border-color:transparent;background:transparent;overflow-wrap:anywhere}
#jaImageList button[aria-pressed=true] {background:var(--tint)}
#jaImageList small {color:var(--muted)}
#jaImageDetail {display:grid;align-content:start;gap:8px}
#jaImageDetail img {display:block;max-width:100%;height:auto;max-height:60dvh;object-fit:contain}
#jaImageDetail ul {margin:0;padding-inline-start:18px}
#jaImageDetail header {display:flex;align-items:center;justify-content:space-between;gap:6px}
#jaImageListBack {display:none}
@media(max-width:690px) {
 [data-workbench=assets] #videoDirectorDesk .mm-columns {display:grid;grid-template-columns:minmax(0,1fr);
  grid-template-rows:minmax(0,1fr);min-height:0}
 [data-workbench=assets] :is(#monitorList,#monitorDetail) {height:auto;max-height:none}
 .ja-image-columns {grid-template-columns:minmax(0,1fr)}
 #imageAssetLibrary[data-detail=true] #jaImageList,
 #imageAssetLibrary:not([data-detail=true]) #jaImageDetail {display:none}
 #jaImageListBack {display:inline-flex}
}
'''

SCRIPT = r'''
function OAAssetGallery(root, tool, sound, openURL){
 const find=selector=>root.querySelector(selector);
 const filter=find('#jaGalleryProject'),dialog=find('#jaGalleryDetail');
 const original=find('#jaGalleryOriginal'), heading=find('#jaGalleryDetailTitle');
 const tiles=new Map(Array.from(root.querySelectorAll('.ja-exhibit'),node=>[node.dataset.kind,{
   node, media:node.querySelector('.ja-exhibit-media'), title:node.querySelector('.ja-exhibit-title'),
   owner:node.querySelector('.ja-exhibit-owner'), next:node.querySelector('.ja-next'),
   rows:[], item:null, stop:null, generation:0, bad:new Set(),
 }]));
 const read=(action,fields={})=>tool('video.director.read',{action,...fields});
 const media=(action,fields={})=>tool('wce.ui.video.director.media',{action,...fields});
 const workspace=(action,fields={})=>tool('wce.ui.video.workspace',{action,...fields});
 const reader=OAArticleWork(find('#jaGalleryReader'),read,media,openURL);
 const element=(tag,label)=>{const node=document.createElement(tag);if(label)OAUI.set(node,label);return node;};
 const mime={audio:'audio/wav',gif:'image/gif',video:'video/mp4'};
 const actions={audio:'audio_chunk',gif:'gif_chunk',video:'playback'};
 const buffers=new Map(), choices=new Map();
 const nextPerson=tiles.get('characters').next;
 OAUI.set(nextPerson.firstElementChild,'下一位');
 OAUI.attr(nextPerson,'aria-label','下一位人物');
 OAUI.attr(nextPerson,'title','下一位人物');
 const params=new URLSearchParams(location.search);
 let project=params.get('project')||'';
 const account=params.get('connection_id')||'';
 const platform=params.get('platform')||'wechat_official_account';
 let accountKey='', epoch=0, active=false, data=null, fullEpoch=0, fullURL='', currentPlayer=null;
 function inProject(id){return !project||project===id;}
 const ownedProject= id=>inProject(id)&&(!account||!!project);
 function mediaScope(row){
   return {project_id:row.project,[row.family==='audio'?'attempt_id':'generation_attempt_id']:row.attempt};
 }
 const frames=(row,start)=>row.family==='audio'
   ?workspace('audio_preview_frames',{...mediaScope(row),start,sha256:row.asset.sha256})
   :workspace('preview_frames',{...mediaScope(row),start});
 const chunk=(row,offset)=>workspace(actions[row.family],{...mediaScope(row),offset});
 const base64=value=>Uint8Array.from(atob(value),character=>character.charCodeAt(0));
 async function readBlob(get,{sha256,total,mime},current){
   const parts=[];
   for(let offset=0;;){
     if(!current())return null;
     const part=await get(offset);
     if(!current())return null;
     total??=part.total;mime??=part.mime_type||part.mime;
     if(!Number.isSafeInteger(total)||total<=offset||part.total!==total||
        (part.offset??offset)!==offset||(part.sha256&&part.sha256!==sha256))throw Error('ASSET_CHANGED');
     const bytes=base64(part.bytes??part.data),next=offset+bytes.length;
     if(next<=offset||next>total||(part.next??next)!==next)throw Error('ASSET_CHANGED');
     parts.push(bytes);
     if(next===total)return new Blob(parts,{type:mime||'application/octet-stream'});
     offset=next;
   }
 }
 function imageAddress(part,digest){
   if(part.mime_type!=='image/jpeg'||part.sha256!==digest||typeof part.data!=='string')throw Error('ASSET_CHANGED');
   return 'data:image/jpeg;base64,'+part.data;
 }
 const imageFields=item=>({project_id:item.project,sha256:item.digest,
   ...(item.kind==='characters'?{version_id:item.value.id}:{}),
   ...(item.kind==='images'&&account?{connection_id:account}:{})});
 function button(label,glyph,action){
   const control=element('button');control.type='button';control.className='ja-preview-btn';
   OAUI.attr(control,'aria-label',label);OAUI.attr(control,'title',label);
   control.textContent=glyph;control.onclick=action;return control;
 }
 function resetFull(){
   fullEpoch++;reader.hide();original.replaceChildren();original.hidden=true;
   if(fullURL)URL.revokeObjectURL(fullURL);fullURL='';
 }
 function showDetail(item){
   resetFull();dialog.dataset.kind=item.kind;OAUI.raw(heading,item.title);
   dialog.showModal();find('#jaGalleryClose').focus();
   if(item.kind==='articles'){
     void reader.show({project_id:item.project,work_id:item.value.work_id},'assets');
     return;
   }
   original.hidden=false;original.replaceChildren(element('p','正在读取原文件…'));
   const ticket=fullEpoch,current=()=>ticket===fullEpoch&&dialog.open;
   const action=item.kind==='characters'?'character_original':'asset_image_original';
   void readBlob(offset=>media(action,{...imageFields(item),offset}),{sha256:item.digest},current)
     .then(async blob=>{
       if(!blob||!current())return;
       if(!['image/png','image/jpeg','image/webp','image/gif'].includes(blob.type))throw Error('ASSET_CHANGED');
       const picture=element('img');picture.alt=item.title;fullURL=URL.createObjectURL(blob);
       picture.src=fullURL;await picture.decode();if(current())original.replaceChildren(picture);
     }).catch(()=>{if(current())original.replaceChildren(element('p','原件暂不可读'));});
 }
 find('#jaGalleryClose').onclick=()=>dialog.close();
 dialog.addEventListener('close',()=>{if(!dialog.open)resetFull();});
 dialog.addEventListener('click',event=>{
   if(event.target!==dialog)return;
   const bounds=dialog.getBoundingClientRect();
   if(event.clientX<bounds.left||event.clientX>bounds.right||event.clientY<bounds.top||event.clientY>bounds.bottom)
     dialog.close();
 });
 function clean(tile){
   ++tile.generation;
   if(currentPlayer===tile)currentPlayer=null;
   tile.stop?.();tile.stop=null;
   tile.media.replaceChildren();delete tile.node.dataset.playing;
 }
 function state(tile,phase,label=''){
   tile.node.dataset.state=phase;
   if(label){
     const note=element('p',label);note.setAttribute('role','status');tile.media.replaceChildren(note);
   }
 }
 function fields(tile,item){
   OAUI.raw(tile.title,item?.title||'');
   OAUI.raw(tile.owner,item?(item.kind==='articles'?item.value.excerpt:item.owner)||'':'');
 }
 function setAudioLabel(control,playing){
   const label=playing?'暂停试听':'试听';
   OAUI.attr(control,'aria-label',label);OAUI.attr(control,'title',label);
   control.textContent=playing?'Ⅱ':'▶';
 }
 function stopOther(tile){
   const previous=currentPlayer;
   if(previous&&previous!==tile){
     currentPlayer=null;previous.pause?.();
   }
 }
 function showPlayer(tile,item,poster){
   stopOther(tile);currentPlayer=tile;tile.node.dataset.playing='true';
   tile.media.replaceChildren();
   const surface=element('div');surface.className='ja-play-detail';tile.media.append(surface);
   const row=item.value;
   const asset=row.family==='audio'?{...row.asset,audio_tracks:row.asset.audio_tracks??1}:row.asset;
   const player=OAVideoPreview(surface,asset,{run:true,sound,poster,frames:start=>frames(row,start),
     chunk:async offset=>{const part=await chunk(row,offset);return {...part,bytes:part.bytes??part.data};}});
   tile.stop=()=>{player.close();tile.pause=null;};
   tile.pause=()=>{
     if(tile.item!==item)return;
     tile.stop?.();tile.stop=null;delete tile.node.dataset.playing;
     posterControl(tile,item,poster);
   };
 }
 function posterControl(tile,item,src){
   const image=element('img');image.alt='';image.src=src;
   const control=button('播放视频','▶',event=>{sound.unlock(event);showPlayer(tile,item,src);});
   tile.media.replaceChildren(image,control);
 }
 async function render(tile,item,current){
   const row=item.value;
   if(item.kind==='articles'){
     tile.media.replaceChildren(button('阅读文章','',()=>showDetail(item)));return;
   }
   if(item.kind==='audio'){
     const record=element('i');record.className='ja-record';record.setAttribute('aria-hidden','true');
     const player=element('audio');player.preload='none';
     const release=sound.bindMedia(player);
     let url='',loading=false;
     const control=button('试听','▶',async event=>{
       sound.unlock(event);
       if(loading)return;
       if(!player.paused){player.pause();return;}
       stopOther(tile);currentPlayer=tile;
       if(!url){
         loading=true;control.disabled=true;control.textContent='…';
         try{
           const blob=await readBlob(offset=>chunk(row,offset),
             {sha256:item.digest,total:row.asset.bytes,mime:row.asset.mime||mime.audio},current);
           if(!blob||!current())return;
           url=URL.createObjectURL(blob);player.src=url;
         }catch(_){
           if(current())failed(tile,item);
           return;
         }finally{loading=false;control.disabled=false;setAudioLabel(control,false);}
       }
       if(currentPlayer!==tile||!current())return;
       await player.play().catch(()=>{if(current()&&player.error)failed(tile,item);});
     });
     player.addEventListener('play',()=>{player.dataset.playing='true';setAudioLabel(control,true);});
     for(const name of ['pause','ended'])player.addEventListener(name,()=>{
       delete player.dataset.playing;setAudioLabel(control,false);
     });
     player.addEventListener('error',()=>{if(current())failed(tile,item);});
     tile.pause=()=>player.pause();
     tile.stop=()=>{release();player.pause();player.removeAttribute('src');player.load();
       if(url)URL.revokeObjectURL(url);tile.pause=null;};
     tile.media.replaceChildren(record,player,control);
     return;
   }
   let src=buffers.get(item.key);
   let objectURL=false;
   if(!src){
     if(item.kind==='video'){
       const batch=await frames(row,0),data=batch.frames?.[0];
       if(typeof data!=='string'||!data.startsWith('/9j/'))throw Error('NO_POSTER');
       src='data:image/jpeg;base64,'+data;
     }else if(item.kind==='gif'){
       const blob=await readBlob(offset=>chunk(row,offset),
         {sha256:item.digest,total:row.asset.bytes,mime:mime.gif},current);
       if(!blob||!current())return;
       src=URL.createObjectURL(blob);objectURL=true;
       tile.stop=()=>URL.revokeObjectURL(src);
     }else{
       src=imageAddress(await media('asset_image_thumbnail',imageFields(item)),item.digest);
     }
   }
   if(!current())return;
   const image=element('img');image.alt='';image.src=src;await image.decode();
   if(!current())return;
   if(!objectURL&&buffers.size<20)buffers.set(item.key,src);
   if(item.kind==='video'){posterControl(tile,item,src);return;}
   tile.media.replaceChildren(image);
   if(item.kind!=='gif'){
     tile.media.append(button('放大图片','',()=>showDetail(item)));
   }else if(matchMedia('(prefers-reduced-motion: reduce)').matches){
     const still=element('canvas');still.width=image.naturalWidth;still.height=image.naturalHeight;
     still.getContext('2d').drawImage(image,0,0);
     tile.media.replaceChildren(still,button('播放动图','▶',()=>tile.media.replaceChildren(image)));
   }
 }
 function failed(tile,item){
   tile.bad.add(item.key);if(tile.item===item)drawTile(tile,item.key);
 }
 function portraitCandidate(row){
   const appearance=row.appearance||{};
   const label=[row.label,appearance.item_name].filter(Boolean).join(' ').normalize('NFKC');
   if(!row.file?.sha256||row.face_visible===false||row.work_id||row.category==='special'
      ||!['face','full_body','angle'].includes(row.use)||row.crop
      ||['head_blank','body_blank','back','side','overview'].includes(appearance.view)
      ||/(?:无头|无面|无脸|头模|背面|正侧|侧面脸|服装|衣饰|假发|轮廓|剪影|faceless|headless|head[ -]?blank|mannequin|profile view|back view|silhouette)/iu.test(label))
     return null;
   const isPortrait=/头像|肖像|脸部近照|面部近照|(?:正面|斜侧)(?:脸部|面部|头部)|\b(?:portrait|headshot)\b/iu;
   const framed=(appearance.details||[]).find(detail=>detail.visibility==='visible'&&!detail.focus
     &&isPortrait.test(detail.name)&&detail.region);
   if(framed){
     const {x,y,width,height}=framed.region;
     if(width>0&&height>0&&x+width<=10000&&y+height<=10000)
       return {row,box:framed.region,rank:row.primary?0:row.status==='current'?3:5};
   }
   if(row.use!=='face'||['source_detail','combined','full_look'].includes(appearance.format)
      ||/(?:局部|细节|眼|耳|鼻|嘴|唇|瞳|虎牙|眉|下巴|下颌|额头|颈|脖|躯干|四肢|手部|脚部|\b(?:detail|close-up of|eye|eyes|ear|ears|nose|lips|chin|mouth|hand|feet)\b)/iu.test(label))
     return null;
   const specified=isPortrait.test(label)||appearance.view==='head_front'||row.face_visible===true;
   if(row.primary||specified||row.status==='current')
     return {row,rank:row.primary?0:specified?(row.status==='current'?1:2):4};
   return null;
 }
 function portraitCrop(image,region){
   if(!region)return image;
   const x=image.naturalWidth*region.x/10000,y=image.naturalHeight*region.y/10000;
   const w=image.naturalWidth*region.width/10000,h=image.naturalHeight*region.height/10000;
   if(w<16||h<16)throw Error('PORTRAIT_TOO_SMALL');
   const canvas=element('canvas'),scale=Math.min(1,720/Math.max(w,h));
   canvas.width=Math.round(w*scale);canvas.height=Math.round(h*scale);
   canvas.getContext('2d').drawImage(image,x,y,w,h,0,0,canvas.width,canvas.height);
   return canvas;
 }
 async function renderPortrait(tile,person,current){
   for(const candidate of person.candidates){
     const {row,box}=candidate;
     const item=representative('characters',row,person.project,person.title,person.owner,row.file.sha256,row.id);
     try{
       let src=buffers.get(item.key);
       if(!src)src=imageAddress(await media('character_preview',imageFields(item)),item.digest);
       if(!current())return;
       const image=element('img');image.src=src;image.alt='';await image.decode();
       if(!current())return;
       const frame=portraitCrop(image,box);
       if(!buffers.has(item.key)&&buffers.size<20)buffers.set(item.key,src);
       if(frame!==image){image.src=frame.toDataURL('image/jpeg',.92);await image.decode();}
       if(!current())return;
       const sample=element('canvas');sample.width=sample.height=1;
       const context=sample.getContext('2d');
       context.drawImage(image,0,0,1,1,0,0,1,1);
       const [r,g,b]=context.getImageData(0,0,1,1).data;
       tile.node.style.setProperty('--ja-portrait-ground','rgb('+r+' '+g+' '+b+')');
       tile.node.dataset.portraitVersion=row.id;
       tile.media.replaceChildren(image,button('放大图片','',()=>showDetail(item)));
       state(tile,'ready');return;
     }catch(_){
       if(!current())return;
     }
   }
   state(tile,person.candidates.length?'unavailable':'empty',
       person.candidates.length?'头像原件暂不可读':'暂无合适头像');
 }
 function drawTile(tile,after){
   clean(tile);tile.item=null;
   delete tile.node.dataset.portraitVersion;
   tile.node.style.removeProperty('--ja-portrait-ground');
   const rows=tile.rows.filter(item=>!tile.bad.has(item.key));
   tile.next.hidden=rows.length<2;
   const nextIndex=rows.findIndex(item=>item.key===after);
   const item=after?rows[(nextIndex+1)%rows.length]:
     rows.find(item=>item.key===choices.get(project+':'+tile.node.dataset.kind))||rows[0];
   if(!item){
     fields(tile,null);
     const broken=tile.bad.size||tile.unavailable, waiting=!broken&&tile.waiting;
     state(tile,broken?'unavailable':waiting?'pending':'empty',
       broken?'原件暂不可读':waiting?'暂无可预览资产':'暂无已登记资产');
     return;
   }
   tile.item=item;choices.set(project+':'+item.kind,item.key);fields(tile,item);
   const ticket=tile.generation,current=()=>active&&ticket===tile.generation;
   state(tile,'loading','正在读取…');
   if(item.kind==='characters'){void renderPortrait(tile,item,current);return;}
   void render(tile,item,current).then(()=>{if(current())state(tile,'ready');})
     .catch(()=>{if(current())failed(tile,item);});
 }
 function projectOptions(projects){
   const names=new Map(projects.map(value=>[value.id,value.name||value.label||value.id]));
   if(project&&!names.has(project))names.set(project,OAUI.format('当前项目暂不可读'));
   filter.replaceChildren(new Option(OAUI.format('全部项目'),''),...Array.from(names,([id,name])=>new Option(name,id)));
   filter.value=project;
 }
 function representative(kind,value,projectId,title,owner,digest,suffix){
   return {kind,value,project:projectId,title,owner,digest,key:JSON.stringify([kind,projectId,suffix,digest])};
 }
 function apply(){
   if(!data)return;
   const [characters,images,articles,mediaRows]=data;
   const directory=new Map();
   for(const value of [characters,images,articles])for(const row of value?.projects||[])directory.set(row.id,row);
   for(const row of mediaRows?.rows||[])if(!directory.has(row.project))
     directory.set(row.project,{id:row.project,name:row.project_label});
   projectOptions(Array.from(directory.values()));
   const projectMissing=!!project&&!data.some(part=>part?.projects?.some(row=>row.id===project))&&
     !mediaRows?.rows.some(row=>row.project===project);
   const values={
     characters:[],images:[],articles:[],...Object.fromEntries(['video','audio','gif'].map(k=>[k,[]])),
   };
   const unavailable=Object.fromEntries(Array.from(tiles.keys(),key=>[key,projectMissing]));
   const mark=(kind,part)=>unavailable[kind]||=!part||part.projects?.some(row=>inProject(row.id)&&row.unavailable);
   mark('characters',characters);mark('images',images);mark('articles',articles);
   const characterImages=new Set();
   for(const entry of characters?.projects||[])if(ownedProject(entry.id)){
     const people=new Map();
     for(const row of entry.assets){
       if(row.file?.sha256&&row.use!=='voice')characterImages.add(JSON.stringify([entry.id,row.file.sha256]));
       if(!row.character?.id||row.work_id||row.category==='special')continue;
       const id=row.character.id;
       if(!people.has(id))people.set(id,{kind:'characters',project:entry.id,key:JSON.stringify([entry.id,id]),
                                       title:row.character.name,owner:entry.name,candidates:[]});
       const candidate=portraitCandidate(row);
       if(candidate)people.get(id).candidates.push(candidate);
     }
     for(const person of people.values()){
       person.candidates.sort((a,b)=>a.rank-b.rank||Number(b.row.form?.id==='normal')-Number(a.row.form?.id==='normal')
         ||a.row.id.localeCompare(b.row.id));
       values.characters.push(person);
     }
   }
   values.characters.sort((a,b)=>(a.candidates[0]?.rank??9)-(b.candidates[0]?.rank??9)
     ||a.title.localeCompare(b.title)||a.key.localeCompare(b.key));
   for(const entry of images?.projects||[])if(inProject(entry.id)){
     const rows=entry.images.filter(row=>!account||row.uses.some(use=>use.connection_id===account));
     const fromPortrait=row=>characterImages.has(JSON.stringify([entry.id,row.sha256]));
     rows.sort((a,b)=>Number(fromPortrait(a))-Number(fromPortrait(b))||
       Number(b.uses.some(use=>use.role==='cover'))-Number(a.uses.some(use=>use.role==='cover'))||
       a.sha256.localeCompare(b.sha256));
     for(const row of rows)values.images.push(representative('images',row,entry.id,row.title,entry.name,row.sha256,''));
   }
   for(const row of articles?.articles||[])if(inProject(row.project_id)&&(!account||row.connection_id===account)){
     if(row.error){unavailable.articles=true;continue;}
     values.articles.push(representative('articles',row,row.project_id,row.title,row.account_label,row.content_digest,row.work_id));
   }
   const waiting=new Set();
   for(const kind of ['video','gif','audio']){
     if(!mediaRows||mediaRows.unavailable.some(row=>inProject(row.project_id)&&
         (row.family===kind||(kind==='video'&&row.family==='audio'))))unavailable[kind]=true;
   }
   for(const row of mediaRows?.rows||[])if(inProject(row.project)&&(!account||(accountKey&&row.account_key===accountKey))){
     if(row.state==='UNAVAILABLE')unavailable[row.kind]=true;
     else if(row.asset?.sha256&&row.asset?.bytes>0&&row.state==='ASSET_READY'){
       values[row.kind]?.push(representative(row.kind,row,row.project,row.title,row.account_label||row.project_label,
         row.asset.sha256,row.family+':'+row.attempt));
     }else waiting.add(row.kind);
   }
   for(const [kind,tile] of tiles){
     tile.rows=values[kind];tile.bad.clear();tile.waiting=waiting.has(kind);tile.unavailable=unavailable[kind];
     drawTile(tile);
   }
 }
 async function refresh(){
   const ticket=++epoch;
   for(const tile of tiles.values()){
     clean(tile);tile.item=null;fields(tile,null);tile.next.hidden=true;
     state(tile,'loading','正在读取…');
   }
   const reads=[
     read('character_library'),media('asset_image_library'),read('article_catalog',{excerpt:true}),
     workspace('media_monitor',{include_scope:true}),
   ];
   const key=account&&globalThis.crypto?.subtle?
     crypto.subtle.digest('SHA-256',new TextEncoder().encode(platform+'\0'+account))
       .then(bytes=>Array.from(new Uint8Array(bytes),byte=>byte.toString(16).padStart(2,'0')).join('')).catch(()=>''):
     Promise.resolve('');
   const [responses,scopeKey]=await Promise.all([Promise.allSettled(reads),key]);
   if(!active||ticket!==epoch)return;
   accountKey=scopeKey;data=responses.map(result=>result.status==='fulfilled'?result.value:null);
   apply();
 }
 filter.onchange=()=>{project=filter.value;if(data)apply();};
 OAUI.onChange(()=>{
   if(filter.options.length)filter.options[0].textContent=OAUI.format('全部项目');
   if(project&&!data?.some(part=>part?.projects?.some(row=>row.id===project))&&filter.selectedIndex>0)
     filter.options[filter.selectedIndex].textContent=OAUI.format('当前项目暂不可读');
 });
 find('#jaGalleryRefresh').onclick=()=>void refresh();
 for(const tile of tiles.values())tile.next.onclick=()=>drawTile(tile,tile.item?.key);
 return {open(){active=true;void refresh();},close(){
   active=false;epoch++;data=null;
   if(dialog.open)dialog.close();
   resetFull();
   for(const tile of tiles.values())clean(tile);
 }};
}

function OAImageAssets(tool){
 const $=id=>document.getElementById(id), root=$('imageAssetLibrary');
 const list=$('jaImageList'), detail=$('jaImageDetail'), filter=$('jaImageProject');
 const search=$('jaImageSearch'), status=$('jaImageStatus'), refresh=$('jaImageRefresh');
 const storage='jiusera.assets.images';
 let active=false, readTimer=0, imageTimer=0, url='', projects=[], rows=[], selected='';
 let listedScroll=0, detailScroll=0;
 try{
   const saved=JSON.parse(localStorage.getItem(storage));
   selected=typeof saved?.selected==='string'?saved.selected:'';
   listedScroll=Number(saved?.list)||0;detailScroll=Number(saved?.details)||0;
   root.dataset.detail=String(!!saved?.show);
   search.value=typeof saved?.query==='string'?saved.query:'';
   filter.dataset.saved=typeof saved?.project==='string'?saved.project:'';
 }catch(_){}
 function keep(){
   if(!root.hidden){
     if(list.getClientRects().length)listedScroll=list.scrollTop;
     if(detail.getClientRects().length)detailScroll=detail.scrollTop;
   }
   try{localStorage.setItem(storage,JSON.stringify({selected,list:listedScroll,details:detailScroll,
     show:root.dataset.detail==='true',query:search.value,project:filter.value||filter.dataset.saved||''}));}catch(_){}
 }
 function clearImage(){
   imageTimer++;
   if(url)URL.revokeObjectURL(url);
   url='';
 }
 const call=(action,args={})=>tool('wce.ui.video.director.media',{action,...args});
 const rowKey=row=>JSON.stringify([row.project_id,row.sha256]);
 const element=(tag,title,raw=false)=>{const el=document.createElement(tag);if(title!==undefined)(raw?OAUI.raw:OAUI.set)(el,title);return el;};
 function choose(row){
   if(selected!==rowKey(row))detailScroll=0;
   if(list.getClientRects().length)listedScroll=list.scrollTop;
   selected=rowKey(row);root.dataset.detail='true';draw();
   detail.focus({preventScroll:true});keep();
 }
 function draw(){
   const query=search.value.trim().toLocaleLowerCase();
   const visible=rows.filter(row=>(!filter.value||row.project_id===filter.value)&&
     (!query||[row.title,row.project_label,...row.uses.map(use=>use.work)].some(s=>s.toLocaleLowerCase().includes(query))));
   const current=visible.find(row=>rowKey(row)===selected);
   clearImage();list.replaceChildren();detail.replaceChildren();
   for(const row of visible){
     const button=element('button');
     button.type='button';button.setAttribute('aria-pressed',String(row===current));
     button.append(element('strong',row.title,true),element('small',row.project_label,true));
     button.onclick=()=>choose(row);list.append(button);
   }
   if(!visible.length)list.append(element('p','没有已登记的图片。'));
   if(current){
     const title=element('h2',current.title,true),bar=element('header');
     const back=element('button','返回列表');back.type='button';back.id='jaImageListBack';
     back.onclick=()=>{keep();root.dataset.detail='false';list.scrollTop=listedScroll;list.querySelector('[aria-pressed=true]')?.focus();keep();};
     bar.append(title,back);detail.append(bar);
     const preview=element('div');const loading=element('p','正在读取原图…');loading.role='status';
     preview.append(loading);detail.append(preview);
     detail.append(element('p',current.project_label,true),element('h3','使用位置'));
     const usages=element('ul');
     for(const use of current.uses){
       const row=element('li'),label=use.kind==='article'?(use.role==='cover'?'文章封面':'正文配图'):use.kind==='canvas'?'画布':'镜头参考';
       OAUI.set(row,'{0} · {1}',label,[use.work,use.account,use.shot,use.title].filter(Boolean).join(' / '));usages.append(row);
     }
     detail.append(usages);void original(current,preview);
   }else{
     root.dataset.detail='false';
     detail.append(element('p','选择图片查看原图与使用位置。'));
   }
   list.scrollTop=listedScroll;detail.scrollTop=detailScroll;
 }
 async function original(row,preview){
   const ticket=imageTimer;
   const chunks=[];let offset=0,total=0,mime='';
   try{
     do{
       const part=await call('asset_image_original',{project_id:row.project_id,sha256:row.sha256,offset});
       if(ticket!==imageTimer||!active)return;
       if(part.sha256!==row.sha256||part.offset!==offset||!Number.isSafeInteger(part.total)||part.total<=0||
           !['image/png','image/jpeg'].includes(part.mime_type)||(offset&&(part.total!==total||part.mime_type!==mime)))
         throw Error('DIRECTOR_ASSET_CHANGED');
       total=part.total;mime=part.mime_type;
       const bytes=Uint8Array.from(atob(part.data),char=>char.charCodeAt(0));
       if(!bytes.length||offset+bytes.length>total)throw Error('DIRECTOR_ASSET_CHANGED');
       chunks.push(bytes);offset+=bytes.length;
     }while(offset<total);
     const blob=new Blob(chunks,{type:mime});
     if(crypto.subtle){
       const hash=await crypto.subtle.digest('SHA-256',await blob.arrayBuffer());
       if(Array.from(new Uint8Array(hash),n=>n.toString(16).padStart(2,'0')).join('')!==row.sha256)
         throw Error('DIRECTOR_ASSET_CHANGED');
     }
     if(ticket!==imageTimer||!active)return;
     url=URL.createObjectURL(blob);
     const image=element('img');image.alt=row.title;image.src=url;
     image.onerror=()=>{if(ticket===imageTimer&&active)preview.replaceChildren(element('p','无法读取登记原图。'));};
     image.onload=()=>{if(ticket===imageTimer&&active)detail.scrollTop=detailScroll;};
     preview.replaceChildren(image);
   }catch(_){if(ticket===imageTimer&&active)preview.replaceChildren(element('p','无法读取登记原图。'));}
 }
 async function read(){
   const ticket=++readTimer;
   const target=filter.value||filter.dataset.saved||'';
   OAUI.set(status,'正在读取图片…');refresh.disabled=true;
   try{
     const result=await call('asset_image_library');
     if(!active||ticket!==readTimer)return;
     if(!Array.isArray(result.projects))throw Error('DIRECTOR_ASSET_READ_FAILED');
     projects=result.projects;rows=projects.flatMap(project=>project.images);
     filter.replaceChildren(element('option','全部项目'));
     filter.firstElementChild.value='';
     for(const project of projects){
       const option=element('option',project.name,true);option.value=project.id;filter.append(option);
     }
     filter.value=projects.some(project=>project.id===target)?target:'';
     delete filter.dataset.saved;
     OAUI.set(status,projects.some(project=>project.unavailable)?'部分项目无法读取。':'');
     draw();
   }catch(_){if(active&&ticket===readTimer)OAUI.set(status,'无法读取图片资产。');}
   finally{if(ticket===readTimer)refresh.disabled=false;}
 }
 const changed=()=>{listedScroll=0;detailScroll=0;draw();keep();};
 search.oninput=changed;filter.onchange=changed;refresh.onclick=()=>void read();
 list.onscroll=detail.onscroll=()=>{if(active)keep();};
 return {open(){active=true;root.hidden=false;void read();},close(){
   if(!active)return;keep();active=false;readTimer++;clearImage();root.hidden=true;
 }};
}
'''
