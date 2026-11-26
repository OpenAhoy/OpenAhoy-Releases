"""Asset categories and the project-scoped image browser."""

from .source_library_ui import HTML as source_library_html
from .writing_workflow_ui import HTML as writing_rules_html

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
        '<div class="ja-exhibit-media"></div>'
        f'<a class="ja-category" href="#view={key}" data-asset-kind="{key}" aria-controls="{target}">'
        f'<span>{title}</span></a></article>'
    )


HTML = (
    """
<section id="directorAssetKinds" aria-label="资产展示" hidden>
 <div class="ja-gallery-bounds"><div class="ja-gallery">
""" + gallery_tile('characters', *KINDS['characters'][:2]) + gallery_tile('video', *KINDS['video'][:2]) + """
 <div class="ja-visual-collection">
""" + gallery_tile('images', *KINDS['images'][:2]) + """
 <div class="ja-media-collection">
""" + gallery_tile('gif', *KINDS['gif'][:2]) + gallery_tile('audio', *KINDS['audio'][:2]) + """
 </div></div>
""" + gallery_tile('articles', *KINDS['articles'][:2]) + """
 </div></div>
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
<div id="articleWritingRules" hidden>''' + writing_rules_html + '''</div>
<section id="articleAssetLibrary" aria-label="文章资产" hidden></section>
''' + source_library_html
)

STYLE = '''
body.oa-management.oa-native:is([data-workbench=assets],[data-workbench=monitor]):not(.oa-platform-view) #videoDirectorDesk {
 padding-inline:var(--wb-tool-gutter);scrollbar-gutter:auto
}
.oa-management.oa-native[data-workbench=assets]:not(.oa-platform-view) #videoDirectorDesk {
 overflow:hidden;gap:10px
}
[data-workbench=assets] #videoDirectorDesk>.dd-toolbar {flex:none}
[data-workbench=assets] #videoDirectorDesk #mediaMonitor,
[data-workbench=assets] #characterLibrary,
[data-workbench=assets] #imageAssetLibrary,
[data-workbench=assets] #articleAssetLibrary {flex:1 1 0;min-height:0;min-width:0}
[data-workbench=assets] #articleAssetLibrary {overflow:auto;overscroll-behavior:contain}
[data-workbench=assets] #directorAssetKinds {
 flex:1;min-height:0;min-width:0;display:grid;align-items:stretch;grid-template-rows:minmax(0,1fr);
 --ja-paper:light-dark(#f5eee1,#342d29);
 --ja-paper-ink:light-dark(#352623,#f3e9db);
}
[data-workbench=assets]:has(#directorAssetKinds:not([hidden])) #videoDirectorDesk .dd-footer{display:none}
.oa-management.oa-native[data-workbench=assets]:has(#directorAssetKinds:not([hidden])) #videoDirectorDesk{
 padding-block-start:var(--wb-top)
}
[data-workbench=assets]:has(#directorAssetKinds:not([hidden])) #videoDirectorDesk>.dd-toolbar{display:none}
.ja-gallery-bounds{min-width:0;min-height:0;container-type:size}
.ja-gallery{
 display:grid;height:100%;min-height:0;min-width:0;gap:9px;
 --ja-portrait-size:min(25cqw,51cqh);
 grid-template-columns:var(--ja-portrait-size) minmax(0,1.94fr) minmax(0,1.12fr);
 grid-template-rows:var(--ja-portrait-size) minmax(0,1fr);
 grid-template-areas:"characters video articles" "collection collection articles"
}
.ja-visual-collection,.ja-media-collection{display:grid;min-width:0;min-height:0;gap:9px}
.ja-visual-collection{
 grid-area:collection;
 --ja-default-image-width:calc(var(--ja-portrait-size) + (100% - var(--ja-portrait-size) - 9px)*.51546);
 grid-template-columns:var(--ja-fit-images,var(--ja-default-image-width)) minmax(0,1fr);
 grid-template-areas:"images media"
}
.ja-media-collection{grid-area:media;grid-template-rows:repeat(2,minmax(0,1fr));grid-template-areas:"gif" "audio"}
.ja-visual-collection[data-returned] .ja-media-collection,.ja-media-collection[data-tight-gif]{
 grid-template-columns:var(--ja-fit-gif,minmax(0,1.55fr)) minmax(0,1fr);
 grid-template-rows:minmax(0,1fr);grid-template-areas:"gif audio"
}
.ja-exhibit{
 min-width:0;min-height:0;position:relative;isolation:isolate;overflow:hidden;border-radius:13px;
 color:var(--ink);background:var(--soft)
}
.ja-exhibit[data-kind=characters]{grid-area:characters;background:light-dark(#e0d9d7,#383235)}
.ja-exhibit[data-kind=video]{grid-area:video;background:light-dark(#e5e5e2,#252628)}
.ja-exhibit[data-kind=images]{grid-area:images;background:light-dark(#e7e4de,#31302e)}
.ja-exhibit[data-kind=gif]{grid-area:gif;background:light-dark(#e2e5e1,#2b3331)}
.ja-exhibit[data-kind=audio]{grid-area:audio;background:light-dark(#e8ebdf,#24302c)}
.ja-exhibit[data-kind=articles]{grid-area:articles;background:var(--ja-paper);color:var(--ja-paper-ink)}
#directorAssetKinds .ja-category{
 position:absolute;inset:0;z-index:2;display:block;border-radius:inherit;
 color:inherit;text-decoration:none;outline-offset:-3px
}
#directorAssetKinds .ja-category:focus-visible{outline:2px solid var(--wb-focus,var(--accent))}
.ja-category span{
 position:absolute;inset:6px auto auto 7px;display:block;padding:4px 7px;border-radius:5px;
 color:light-dark(#201e1c,#f7f4ef);background:light-dark(#fbfaf7,#242323);
 font-size:11px;font-weight:680;line-height:1.15;white-space:nowrap
}
.ja-category:hover span{text-decoration:underline;text-underline-offset:2px}
.ja-exhibit-media{position:absolute;inset:0;overflow:hidden}
.ja-exhibit:is([data-kind=images],[data-kind=gif],[data-kind=articles]) .ja-exhibit-media{inset-block-start:29px}
.ja-exhibit-frame{
 position:absolute;inset:0;display:grid;place-items:center;opacity:1;
 transition:opacity .54s ease
}
.ja-exhibit-frame.is-entering,.ja-exhibit-frame.is-leaving{opacity:0}
.ja-exhibit-frame.is-leaving.is-underlay{opacity:1}
.ja-exhibit[data-kind=images]{--ja-mosaic-ground:light-dark(#e7e4de,#31302e)}
.ja-exhibit[data-kind=gif]{--ja-mosaic-ground:light-dark(#e2e5e1,#2b3331)}
#directorAssetKinds .ja-exhibit[data-snug]{
 overflow:visible;background:transparent;box-shadow:none
}
#directorAssetKinds .ja-exhibit[data-snug] .ja-category{
 inset:0 auto auto 0;width:var(--ja-snug-width);height:var(--ja-snug-height)
}
.ja-exhibit[data-snug] .ja-exhibit-media{overflow:visible}
.ja-exhibit[data-snug] .ja-exhibit-frame::before{
 content:"";position:absolute;inset:calc(0px - var(--ja-mosaic-caption)) auto auto 0;
 width:var(--ja-frame-width);height:calc(var(--ja-frame-height) + var(--ja-mosaic-caption));
 background:var(--ja-mosaic-ground);border-radius:inherit;box-shadow:var(--wb-raised);z-index:-1
}
.ja-exhibit-frame{border-radius:inherit}
.ja-exhibit{--ja-mosaic-caption:29px}
.ja-exhibit[data-snug] .ja-exhibit-frame>p{
 position:absolute;inset:calc(var(--ja-frame-height) - 24px) auto auto 0;
 margin:0;width:max-content;max-width:var(--ja-frame-width)
}

.ja-exhibit-frame>img,.ja-exhibit-frame>video{width:100%;height:100%;min-height:0;display:block;object-fit:cover}
.ja-exhibit[data-kind=characters] .ja-exhibit-frame>img{object-fit:contain}
.ja-exhibit[data-kind=video] .ja-exhibit-frame>video{object-fit:contain}
.ja-exhibit-frame>p{margin:6px;max-width:77%;text-align:center;font-size:12px;line-height:1.3}
.ja-exhibit[data-state=partial] .ja-exhibit-frame>p{background:var(--soft);border-radius:6px;padding:4px 7px}
.ja-mosaic-piece{position:absolute;overflow:hidden;border-radius:4px}
.ja-mosaic-piece :is(img,canvas){display:block;width:100%;height:100%}
.ja-mosaic-piece [hidden]{display:none!important}
.ja-exhibit-frame>.ja-article-sheet{
 place-self:start stretch;min-width:0;padding:clamp(10px,2.05cqw,37px);
 padding-top:clamp(13px,3cqh,33px);overflow:hidden;max-height:100%
}
#directorAssetKinds .ja-article-sheet h2{
 margin:0 0 .62em;font:650 clamp(19px,2.28cqw,46px)/1.19 ui-serif,Georgia,"Songti SC",serif;
 letter-spacing:-.025em;overflow-wrap:anywhere
}
.ja-article-copy{
 color:inherit;font:400 clamp(12px,1.24cqw,19px)/1.62 ui-serif,Georgia,"Songti SC",serif;
 overflow:hidden;overflow-wrap:anywhere
}
.ja-article-copy p{margin:0}
.ja-article-copy p+p{margin-block-start:1lh}
#directorAssetKinds .ja-preview-btn{
 position:absolute;z-index:3;inset:auto 7px 7px auto;border-radius:50%;width:38px;height:38px;
 min-width:0;min-height:0;padding:0;display:grid;place-items:center;border:0;
 background:light-dark(#f8f7f4,#29292b);color:light-dark(#222,#fff);box-shadow:0 2px 8px #1614103d;
 font-size:14px;line-height:1
}
#directorAssetKinds .ja-preview-sound{inset-inline-end:50px;width:29px;height:29px;inset-block-end:11px}
.ja-preview-sound[aria-pressed=true] .ja-sound-mute,
.ja-preview-sound[aria-pressed=false] .ja-sound-wave{display:none}
#directorAssetKinds .ja-preview-btn:hover{filter:brightness(1.12)}
#directorAssetKinds .ja-preview-btn:focus-visible{outline:2px solid var(--wb-focus,var(--accent));outline-offset:-2px}
.ja-player{display:grid;width:100%;height:100%;place-items:center;overflow:hidden}
.ja-player video{display:block;width:100%;height:100%;object-fit:contain}
.ja-player audio{display:none}
.ja-record{
 place-self:center;aspect-ratio:1;width:min(58%,22cqh);max-height:92%;border-radius:50%;
 background:radial-gradient(circle,#302625 0 3%,#eee1ac 4% 12%,#b6704c 13% 23%,transparent 24%),
   repeating-radial-gradient(circle,#24292a 0 2px,#343a38 3px,#222728 4px);
 box-shadow:0 6px 16px #10221b40
}
.ja-exhibit[data-kind=audio][data-playing=true] .ja-record{animation:ja-spin 14s linear infinite}
@keyframes ja-spin{to{transform:rotate(1turn)}}
@media(prefers-reduced-motion:reduce){
 .ja-exhibit-frame{transition:none}
 .ja-record{animation:none!important}
}
@media(max-width:710px){
 .oa-management.oa-native[data-workbench=assets]:has(#directorAssetKinds:not([hidden])) #videoDirectorDesk{
   padding-bottom:max(var(--wb-dock),calc(60px + env(safe-area-inset-bottom)))
 }
 .ja-gallery{gap:5px;--ja-portrait-size:min(calc((100cqw - 10px)/3),40cqh);
   grid-template-columns:minmax(0,1fr) minmax(0,1fr) var(--ja-portrait-size);
   grid-template-rows:var(--ja-portrait-size) repeat(2,minmax(0,1fr));
   grid-template-areas:"video video characters" "images images articles" "gif audio articles"}
 .ja-visual-collection,.ja-media-collection{display:contents}
 .ja-gallery[data-single-portrait]{
   grid-template-rows:var(--ja-portrait-size) minmax(0,1.3fr) repeat(2,minmax(0,1fr));
   grid-template-areas:"video video characters" "images articles articles" "gif articles articles" "audio articles articles"
 }
 .ja-exhibit{border-radius:9px;--ja-mosaic-caption:21px}
 .ja-category span{inset:4px auto auto 4px;padding:3px 5px;font-size:10px}
 .ja-exhibit:is([data-kind=images],[data-kind=gif],[data-kind=articles]) .ja-exhibit-media{inset-block-start:21px}
 .ja-exhibit-frame>p{font-size:10px}
 .ja-exhibit-frame>.ja-article-sheet{padding:6px 7px}
 #directorAssetKinds .ja-article-sheet h2{font-size:clamp(13px,4.15cqw,21px);margin-bottom:.55em}
 .ja-article-copy{font-size:clamp(11px,3.1cqw,14px);line-height:1.45}
 #directorAssetKinds .ja-preview-btn{width:34px;height:34px;inset:auto 5px 5px auto}
 #directorAssetKinds .ja-preview-sound{inset:auto 42px 9px auto;width:26px;height:26px}
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
function OAGalleryMosaic(pieces,width,height,gap){
 // Each slicing layout has height = slope * width + intercept, including the real gutter.
 const ranks=new Map(pieces.map((piece,index)=>[piece,index])),cache=new Map();
 function trees(items){
   if(items.length===1)return [{piece:items[0],a:1/items[0].ratio,b:0}];
   const key=items.map(piece=>ranks.get(piece)).join(',');
   if(cache.has(key))return cache.get(key);
   const out=[];
   for(let i=1;i<items.length;i++){
     for(const one of trees(items.slice(0,i)))for(const two of trees(items.slice(i))){
       out.push({one,two,axis:'y',a:one.a+two.a,b:one.b+two.b+gap});
       const a=1/(1/one.a+1/two.a);
       out.push({one,two,axis:'x',a,b:a*(one.b/one.a+two.b/two.a-gap)});
     }
   }
   cache.set(key,out);return out;
 }
 function boxes(tree,x,y,w,rows){
   const h=tree.a*w+tree.b;
   if(w<=0||h<=0)return false;
   if(tree.piece){rows.push({piece:tree.piece,x,y,w,h});return true;}
   const {one,two,axis}=tree;
   if(axis==='y')return boxes(one,x,y,w,rows)&&boxes(two,x,y+one.a*w+one.b+gap,w,rows);
   const first=(h-one.b)/one.a;
   return boxes(one,x,y,first,rows)&&boxes(two,x+first+gap,y,w-first-gap,rows);
 }
 if(!pieces.length||width<1||height<1)return [];
 let best=[],rank=-Infinity;
 // Cyclic ordering avoids making a single panorama dictate every possible division.
 for(let i=0;i<pieces.length;i++)for(const tree of trees(pieces.slice(i).concat(pieces.slice(0,i)))){
   const w=Math.min(width,(height-tree.b)/tree.a),h=tree.a*w+tree.b;
   const rows=[];
   if(!boxes(tree,(width-w)/2,(height-h)/2,w,rows))continue;
   const coverage=rows.reduce((sum,row)=>sum+row.w*row.h,0)/(width*height);
   const smallest=Math.min(...rows.map(row=>Math.min(row.w,row.h)));
   const value=coverage+Math.min(smallest/Math.min(width,height),.35)*.45;
   if(value>rank){rank=value;best=rows;}
 }
 return best;
}
function OAGalleryExtent(boxes){
 if(!boxes.length)return {x:0,y:0,w:0,h:0,area:0};
 const x=Math.min(...boxes.map(box=>box.x)),y=Math.min(...boxes.map(box=>box.y));
 return {x,y,w:Math.max(...boxes.map(box=>box.x+box.w))-x,h:Math.max(...boxes.map(box=>box.y+box.h))-y,
   area:boxes.reduce((sum,box)=>sum+box.w*box.h,0)};
}
function OAAssetGallery(root,tool,sound){
 const find=selector=>root.querySelector(selector);
 const gallery=find('.ja-gallery'),collection=find('.ja-visual-collection');
 const mediaCollection=find('.ja-media-collection');
 const narrow=matchMedia('(max-width: 710px)');
 const tiles=new Map(Array.from(root.querySelectorAll('.ja-exhibit'),node=>[node.dataset.kind,{
   node, media:node.querySelector('.ja-exhibit-media'), kind:node.dataset.kind,
   rows:[], index:0, generation:0, visible:true, layers:new Set(), failed:new Set(),
 }]));
 const read=(action,fields={})=>tool('video.director.read',{action,...fields});
 const media=(action,fields={})=>tool('wce.ui.video.director.media',{action,...fields});
 const workspace=(action,fields={})=>tool('wce.ui.video.workspace',{action,...fields});
 const element=(tag,label)=>{const node=document.createElement(tag);if(label)OAUI.set(node,label);return node;};
 const motion=matchMedia('(prefers-reduced-motion: reduce)');
 const buffer=new Map(),positions=new Map();
 const params=new URLSearchParams(location.search);
 let project=params.get('project')||'';
 const account=params.get('connection_id')||'';
 const platform=params.get('platform')||'wechat_official_account';
 let accountKey='',epoch=0,active=false,data=null,timer=0,currentPlayer=null;
 const groupLimit={images:4,gif:3};
 const mediaScope=row=>({project_id:row.project,[row.family==='audio'?'attempt_id':'generation_attempt_id']:row.attempt});
 const actions={audio:'audio_chunk',gif:'gif_chunk',video:'playback'};
 const mime={audio:'audio/wav',gif:'image/gif',video:'video/mp4'};
 const chunk=(row,offset)=>workspace(actions[row.family],{...mediaScope(row),offset});
 const canMove=tile=>active&&tile.visible&&!document.hidden&&!motion.matches;
 const hover=matchMedia('(hover: hover)');
 const canRotate=tile=>canMove(tile)&&!tile.node.matches(':focus-within')&&!(hover.matches&&tile.node.matches(':hover'));
 function inProject(id){return !project||project===id;}
 const ownedProject=id=>inProject(id)&&(!account||!!project);
 async function readBlob(item,current){
   const row=item.value,total=row.asset.bytes;
   if(!Number.isSafeInteger(total)||total<=0)throw Error('ASSET_CHANGED');
   const parts=[];
   for(let offset=0;offset<total;){
     if(!current())return null;
     const part=await chunk(row,offset);
     if(!current())return null;
     // Audio chunks identify the span by next rather than repeating the requested offset.
     if(part.total!==total||(part.offset??(row.family==='audio'&&Number.isSafeInteger(part.next)?offset:-1))!==offset||
        (part.sha256&&part.sha256!==item.digest))throw Error('ASSET_CHANGED');
     const bytes=Uint8Array.from(atob(part.bytes??part.data),character=>character.charCodeAt(0));
     const next=offset+bytes.length;
     if(next<=offset||next>total||(part.next??next)!==next)throw Error('ASSET_CHANGED');
     parts.push(bytes);offset=next;
   }
   return new Blob(parts,{type:row.asset.mime||mime[row.family]});
 }
 function imageAddress(part,digest){
   if(part.mime_type!=='image/jpeg'||part.sha256!==digest||typeof part.data!=='string')throw Error('ASSET_CHANGED');
   return 'data:image/jpeg;base64,'+part.data;
 }
 const imageFields=item=>({project_id:item.project,sha256:item.digest,
   ...(item.kind==='characters'?{version_id:item.value.id}:{}),
   ...(item.kind==='images'&&account?{connection_id:account}:{})});
 async function loadPreview(action,item,current){
   let src=buffer.get(item.key);
   if(!src)src=imageAddress(await media(action,imageFields(item)),item.digest);
   if(!current())return null;
   const picture=element('img');picture.alt='';picture.src=src;await picture.decode();
   if(!current())return null;
   if(buffer.has(item.key))buffer.delete(item.key);
   if(buffer.size>=16)buffer.delete(buffer.keys().next().value);
   buffer.set(item.key,src);
   return picture;
 }
 function removeLayer(tile,layer){
   clearTimeout(layer.timer);
   layer.node.remove();
   layer.release?.();
   tile.layers.delete(layer);
 }
 function clear(tile){
   tile.generation++;tile.loading=false;tile.item=null;tile.index=0;
   if(currentPlayer===tile)currentPlayer=null;
   tile.stop?.();tile.stop=null;tile.pause=null;
   tile.control?.remove();tile.control=null;
   delete tile.node.dataset.playing;
   for(const layer of tile.layers)removeLayer(tile,layer);
   tile.layer=null;tile.target=0;tile.failed.clear();
   tile.node.removeAttribute('data-snug');
   if(tile.kind==='images')resetCollection();
   if(tile.kind==='gif')resetMediaCollection();
   delete tile.node.dataset.portraitVersion;
   delete tile.node.dataset.articleWork;
 }
 function resetCollection(){
   collection.removeAttribute('data-returned');
   collection.style.removeProperty('--ja-fit-images');
   gallery.removeAttribute('data-single-portrait');
 }
 function imageReference(){
   const width=collection.getBoundingClientRect().width;
   const portrait=tiles.get('characters').node.getBoundingClientRect().width;
   return Math.min(width-68,portrait+Math.max(0,width-portrait-9)*.51546);
 }
 function adaptImages(tile,pieces){
   gallery.toggleAttribute('data-single-portrait',pieces.length===1&&pieces[0].ratio<1);
   if(narrow.matches)return;
   const width=imageReference(),height=tile.media.getBoundingClientRect().height;
   const {w}=OAGalleryExtent(OAGalleryMosaic(pieces,width,height,width<250?3:5));
   if(w>0&&w<width*.86){
     const returned=width-w;
     const target=Math.max(76,Math.min(width,Math.ceil(w)));
     const value=target+'px';
     if(collection.style.getPropertyValue('--ja-fit-images')!==value)collection.style.setProperty('--ja-fit-images',value);
     collection.toggleAttribute('data-returned',returned>100);
   }else{
     collection.removeAttribute('data-returned');
     collection.style.removeProperty('--ja-fit-images');
   }
 }
 function resetMediaCollection(){
   mediaCollection.removeAttribute('data-tight-gif');
   mediaCollection.style.removeProperty('--ja-fit-gif');
 }
 function adaptGif(tile,pieces){
   const width=mediaCollection.getBoundingClientRect().width;
   if(narrow.matches||width<260){resetMediaCollection();return;}
   const together=collection.hasAttribute('data-returned')||pieces.length===1;
   mediaCollection.toggleAttribute('data-tight-gif',together);
   if(!together){mediaCollection.style.removeProperty('--ja-fit-gif');return;}
   const candidate=(width-9)*.61,height=tile.media.getBoundingClientRect().height;
   const {w}=OAGalleryExtent(OAGalleryMosaic(pieces,candidate,height,candidate<250?3:5));
   if(w>0&&w<candidate*.86){
     const value=Math.max(76,Math.ceil(w))+'px';
     if(mediaCollection.style.getPropertyValue('--ja-fit-gif')!==value)mediaCollection.style.setProperty('--ja-fit-gif',value);
   }else mediaCollection.style.removeProperty('--ja-fit-gif');
 }
 function fit(tile,layer){
   if(layer.pieces){
     const {width:w,height:h}=tile.media.getBoundingClientRect();
     if(w<1||h<1)return;
     const boxes=OAGalleryMosaic(layer.pieces,w,h,w<250?3:5),bounds=OAGalleryExtent(boxes);
     if(!boxes.length)return;
     const snug=layer.pieces.length===1||bounds.w<w*.86||bounds.h<h*.83;
     const insetX=snug?bounds.x:0,insetY=snug?bounds.y:0;
     if(tile.layer===layer){
       tile.node.toggleAttribute('data-snug',snug);
       if(snug){
         const floor=Math.min(w,75);
         tile.node.style.setProperty('--ja-snug-width',Math.max(bounds.w,floor)+'px');
         tile.node.style.setProperty('--ja-snug-height','calc('+bounds.h+'px + var(--ja-mosaic-caption))');
       }
     }
     layer.node.style.setProperty('--ja-frame-width',Math.max(bounds.w,Math.min(w,75))+'px');
     layer.node.style.setProperty('--ja-frame-height',bounds.h+'px');
     for(const {piece,x,y,w:width,h:height} of boxes){
       Object.assign(piece.slot.style,{left:(x-insetX)+'px',top:(y-insetY)+'px',width:width+'px',height:height+'px'});
     }
   }
   if(layer.sheet){
     const text=layer.sheet.lastElementChild;
     const line=parseFloat(getComputedStyle(text).lineHeight);
     if(line>0)text.style.maxHeight=(Math.max(1,Math.floor((tile.media.clientHeight-text.offsetTop-
         parseFloat(getComputedStyle(layer.sheet).paddingBottom))/line))*line)+'px';
   }
 }
 function state(tile,phase,contents,label='',extra={}){
   tile.node.dataset.state=phase;
   if(!extra.pieces){
     tile.node.removeAttribute('data-snug');
     if(tile.kind==='images')resetCollection();
     if(tile.kind==='gif')resetMediaCollection();
   }
   const node=element('div');
   node.className='ja-exhibit-frame';
   if(contents)node.append(contents);
   if(label){const note=element('p',label);note.setAttribute('role','status');node.append(note);}
   const before=tile.layer;
   for(const layer of tile.layers)if(layer!==before)removeLayer(tile,layer);
   const layer={node,phase,...extra};
   if(before&&before.phase!=='loading'&&canMove(tile)&&phase!=='loading'){
     node.classList.add('is-entering');
     before.node.classList.add('is-leaving');
     if(extra.pieces&&before.pieces)before.node.classList.add('is-underlay');
     before.node.setAttribute('aria-hidden','true');
     before.timer=setTimeout(()=>removeLayer(tile,before),590);
   }else if(before)removeLayer(tile,before);
   tile.media.append(node);tile.layers.add(layer);tile.layer=layer;
   if(tile.kind==='images'&&extra.pieces)adaptImages(tile,extra.pieces);
   if(tile.kind==='gif'&&extra.pieces)adaptGif(tile,extra.pieces);
   for(const item of tile.layers)fit(tile,item);
   if(node.classList.contains('is-entering'))requestAnimationFrame(()=>requestAnimationFrame(()=>node.classList.remove('is-entering')));
 }
 function previewControl(tile,item,poster){
   const row=item.value,video=tile.kind==='video';
   const holder=element('div');holder.className='ja-player';
   const player=element(video?'video':'audio');player.preload='none';player.playsInline=true;
   if(video)player.poster=poster;
   else{const record=element('i');record.className='ja-record';record.setAttribute('aria-hidden','true');holder.append(record);}
   holder.append(player);
   state(tile,'ready',holder);
   const volume=element('button');volume.type='button';volume.className='ja-preview-btn ja-preview-sound';volume.hidden=true;
   volume.innerHTML='<svg viewBox="0 0 24 24" width="15" height="15" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M11 5 6 9H3v6h3l5 4z"/><path class="ja-sound-wave" d="M15 9a4 4 0 0 1 0 6m3-9a8 8 0 0 1 0 12"/><path class="ja-sound-mute" d="m15 9 6 6m0-6-6 6"/></svg>';
   OAUI.attr(volume,'aria-label','预览声音');
   volume.onclick=sound.toggle;
   const release=sound.bindMedia(player,(_audible,enabled)=>{
     volume.setAttribute('aria-pressed',String(enabled));
     OAUI.attr(volume,'title',enabled?'声音开':'声音关');
   });
   const control=element('button');control.type='button';control.className='ja-preview-btn';
   const label=playing=>video?(playing?'暂停视频':'播放视频'):(playing?'暂停试听':'试听');
   function status(playing){
     OAUI.attr(control,'aria-label',label(playing));OAUI.attr(control,'title',label(playing));
     control.textContent=playing?'Ⅱ':'▶';tile.node.dataset.playing=String(playing);
     if(!playing&&document.activeElement===volume)control.focus({preventScroll:true});
     volume.hidden=!playing;
   }
   let url='',loading=false;
   const current=()=>active&&tile.control===control;
   status(false);
   tile.control=control;tile.node.append(control,volume);
   player.addEventListener('play',()=>{if(current())status(true);});
   for(const name of ['pause','ended'])player.addEventListener(name,()=>{if(current())status(false);});
   function failed(){
     if(!current())return;
     tile.stop();tile.stop=null;tile.control=null;tile.pause=null;
     if(currentPlayer===tile)currentPlayer=null;
     state(tile,'unavailable',null,'原件暂不可读');
   }
   player.addEventListener('error',failed);
   tile.pause=()=>player.pause();
   tile.stop=()=>{
     release();control.remove();volume.remove();player.pause();player.removeAttribute('src');player.load();
     if(url)URL.revokeObjectURL(url);
   };
   control.onclick=async event=>{
     sound.unlock(event);
     if(loading)return;
     if(!player.paused){player.pause();return;}
     if(currentPlayer!==tile)currentPlayer?.pause?.();
     currentPlayer=tile;
     if(!url){
       loading=true;control.disabled=true;control.textContent='…';
       try{
         const blob=await readBlob(item,current);
         if(!blob||!current())return;
         url=URL.createObjectURL(blob);player.src=url;
       }catch(_){failed();return;}
       finally{loading=false;if(current()){control.disabled=false;status(false);}}
     }
     if(current()&&currentPlayer===tile&&!document.hidden)await player.play().catch(failed);
   };
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
       const image=await loadPreview('character_preview',item,current);
       if(!image)return;
       const frame=portraitCrop(image,box);
       if(frame!==image){image.src=frame.toDataURL('image/jpeg',.92);await image.decode();}
       if(!current())return;
       tile.node.dataset.portraitVersion=row.id;
       state(tile,'ready',image);return;
     }catch(_){if(!current())return;}
   }
   delete tile.node.dataset.portraitVersion;
   state(tile,person.candidates.length?'unavailable':'empty',null,
         person.candidates.length?'头像原件暂不可读':'暂无合适头像');
 }
 function showMotion(tile){
   for(const layer of tile.layers)for(const piece of layer.pieces||[])if(piece.still){
     const play=canMove(tile);
     piece.image.hidden=!play;piece.still.hidden=play;
   }
 }
 async function mosaicPiece(tile,item,current){
   let picture,url='';
   try{
     if(tile.kind==='gif'){
       const blob=await readBlob(item,current);
       if(!blob)return null;
       url=URL.createObjectURL(blob);picture=element('img');picture.alt='';picture.src=url;await picture.decode();
     }else picture=await loadPreview('asset_image_thumbnail',item,current);
     if(!picture||!current()){if(url)URL.revokeObjectURL(url);return null;}
     const slot=element('div');slot.className='ja-mosaic-piece';slot.append(picture);
     let still;
     if(url){
       still=element('canvas');
       still.width=picture.naturalWidth;still.height=picture.naturalHeight;
       still.getContext('2d').drawImage(picture,0,0);
       slot.append(still);
     }
     slot.dataset.assetKey=item.key;
     return {slot,image:picture,still,url,key:item.key,ratio:picture.naturalWidth/picture.naturalHeight};
   }catch(error){if(url)URL.revokeObjectURL(url);throw error;}
 }
 async function renderMosaic(tile,index,current,turn){
   const pieces=[],unavailable=tile.failed;
   const rows=tile.rows,needed=entriesPerFrame(tile);
   let offset=0;
   const release=()=>{for(const piece of pieces)if(piece.url)URL.revokeObjectURL(piece.url);};
   async function fill(count){
     while(current()&&pieces.length<count&&offset<rows.length){
       const batch=[];
       while(batch.length<count-pieces.length&&offset<rows.length){
         const item=rows[(index+offset++)%rows.length];
         if(!unavailable.has(item.key))batch.push(item);
       }
       const results=await Promise.allSettled(batch.map(item=>mosaicPiece(tile,item,current)));
       for(let i=0;i<results.length;i++){
         const result=results[i];
         if(result.status==='fulfilled'&&result.value)pieces.push(result.value);
         else if(current()&&result.status==='rejected')unavailable.add(batch[i].key);
       }
     }
   }
   await fill(needed);
   if(current()&&pieces.length>=2&&tile.kind==='images'&&!narrow.matches){
     const w=imageReference(),h=tile.media.getBoundingClientRect().height;
     // Add up to two distinct portraits when the usual batch is too narrow for a wide shelf.
     if(w>620&&h>0){
       const before=OAGalleryExtent(OAGalleryMosaic(pieces,w,h,5));
       if(before.w<w*.85&&before.area<w*h*.73){
         const initial=pieces.length;
         await fill(needed+2);
         if(current()&&pieces.length>initial){
           const after=OAGalleryExtent(OAGalleryMosaic(pieces,w,h,5));
           if(after.w<before.w||after.area<=before.area)pieces.splice(initial);
         }
       }
     }
   }
   if(!current()||(turn&&tile.layer?.pieces&&!canRotate(tile))){release();return;}
   if(!pieces.length){
     release();state(tile,'unavailable',null,'原件暂不可读');return;
   }
   tile.target=needed;tile.index=index;positions.set(project+':'+tile.kind,rows[index].key);
   const keys=new Set(pieces.map(piece=>piece.key));
   if(tile.layer?.pieces?.length===keys.size&&tile.layer.pieces.every(piece=>keys.has(piece.key))){
     release();return;
   }
   const group=document.createDocumentFragment();
   for(const piece of pieces)group.append(piece.slot);
   state(tile,unavailable.size?'partial':'ready',group,
         unavailable.size?'部分原件暂不可读':'',{pieces,release});
   showMotion(tile);
 }
 function entriesPerFrame(tile){
   if(tile.kind==='gif')return tile.media.clientWidth<165||tile.media.clientHeight<77?2:groupLimit.gif;
   if(tile.kind==='images'){
     const width=narrow.matches?tile.media.clientWidth:imageReference();
     return width<205||tile.media.clientHeight<100?3:groupLimit.images;
   }
   return 1;
 }
 async function drawTile(tile,index=0,turn=false){
   tile.loading=true;
   const rows=tile.rows,generation=++tile.generation;
   const current=()=>active&&generation===tile.generation;
   const item=rows[index];
   try{
     if(!item){
       const phase=tile.unavailable?'unavailable':tile.waiting?'pending':'empty';
       state(tile,phase,null,tile.unavailable?'原件暂不可读':tile.waiting?'暂无可预览资产':'暂无已登记资产');
       return;
     }
     if(!tile.layer)state(tile,'loading',null,'正在读取…');
     if(groupLimit[tile.kind]){await renderMosaic(tile,index,current,turn);return;}
     tile.item=item;tile.index=index;positions.set(project+':'+tile.kind,item.key);
     if(tile.kind==='characters'){await renderPortrait(tile,item,current);return;}
     if(tile.kind==='articles'){
       const sheet=element('div');sheet.className='ja-article-sheet';
       const title=element('h2'),text=element('div');text.className='ja-article-copy';
       title.textContent=item.value.title;
       const sentences=(item.value.excerpt||'').match(/[^。！？.!?]+[。！？.!?]*|[。！？.!?]+/gu)||[];
       for(const sentence of sentences){
         let paragraph=text.lastElementChild;
         if(!paragraph||paragraph.textContent.length>=76){paragraph=element('p');text.append(paragraph);}
         paragraph.append(sentence);
       }
       sheet.append(title,text);tile.node.dataset.articleWork=item.value.work_id;
       state(tile,'ready',sheet,'',{sheet});return;
     }
     let poster='';
     if(tile.kind==='video'){
       const row=item.value;
       const batch=row.family==='audio'
         ?await workspace('audio_preview_frames',{...mediaScope(row),start:0,sha256:row.asset.sha256})
         :await workspace('preview_frames',{...mediaScope(row),start:0});
       const data=batch.frames?.[0];
       if(typeof data!=='string'||!data.startsWith('/9j/'))throw Error('NO_POSTER');
       poster='data:image/jpeg;base64,'+data;
     }
     if(current())previewControl(tile,item,poster);
   }catch(_){if(current())state(tile,'unavailable',null,'原件暂不可读');}
   finally{if(current())tile.loading=false;}
 }
 function stopClock(){clearTimeout(timer);timer=0;}
 function cycleSize(tile){return tile.layer?.pieces?.length??entriesPerFrame(tile);}
 function hasMore(tile){
   return (groupLimit[tile.kind]||['characters','articles'].includes(tile.kind))&&
     tile.rows.length-tile.failed.size>cycleSize(tile);
 }
 function tick(){
   timer=0;
   for(const tile of tiles.values()){
     if(!hasMore(tile)||!canRotate(tile)||tile.loading)continue;
     const index=tile.index+cycleSize(tile);
     void drawTile(tile,index>=tile.rows.length?0:index,true);
   }
   schedule();
 }
 function schedule(){
   if(!timer&&active&&!document.hidden&&!motion.matches&&[...tiles.values()].some(hasMore))timer=setTimeout(tick,6300);
 }
 motion.addEventListener('change',()=>{stopClock();for(const tile of tiles.values())showMotion(tile);schedule();});
 document.addEventListener('visibilitychange',()=>{
   if(document.hidden)currentPlayer?.pause?.();
   stopClock();for(const tile of tiles.values())showMotion(tile);schedule();
 });
 const view=new IntersectionObserver(entries=>{
   for(const entry of entries){
     const tile=tiles.get(entry.target.dataset.kind);
     tile.visible=entry.isIntersecting;
     showMotion(tile);
   }
   schedule();
 });
 const size=new ResizeObserver(entries=>{
   for(const entry of entries){
     const tile=tiles.get(entry.target.parentElement.dataset.kind);
     for(const layer of tile.layers)fit(tile,layer);
     if(tile.kind==='images'&&tile.layer?.pieces)adaptImages(tile,tile.layer.pieces);
     if(tile.kind==='gif'&&tile.layer?.pieces)adaptGif(tile,tile.layer.pieces);
     // Re-evaluate the group only when resizing changes its target count, not on accordion reflow.
     if(active&&groupLimit[tile.kind]&&tile.layer?.pieces&&!tile.loading&&
        tile.target!==entriesPerFrame(tile))void drawTile(tile,tile.index);
   }
 });
 function representative(kind,value,projectId,title,owner,digest,suffix){
   return {kind,value,project:projectId,title,owner,digest,key:JSON.stringify([kind,projectId,suffix,digest])};
 }
 function apply(){
   if(!data)return;
   const [characters,images,articles,mediaRows]=data;
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
     ||a.title.localeCompare(b.title,'zh-CN')||a.key.localeCompare(b.key));
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
     else if(row.asset?.sha256&&row.asset?.bytes>0&&row.state==='ASSET_READY'&&
         (row.kind!=='gif'||row.asset.bytes<=12*1024*1024)){
       values[row.kind]?.push(representative(row.kind,row,row.project,row.title,row.account_label||row.project_label,
         row.asset.sha256,row.family+':'+row.attempt));
     }else waiting.add(row.kind);
   }
   for(const [kind,tile] of tiles){
     clear(tile);
     tile.rows=groupLimit[kind]?Array.from(new Map(values[kind].map(item=>[item.digest,item])).values()):values[kind];
     tile.waiting=waiting.has(kind);tile.unavailable=unavailable[kind];
     const saved=tile.rows.findIndex(item=>item.key===positions.get(project+':'+kind));
     void drawTile(tile,Math.max(0,saved));
   }
   schedule();
 }
 async function refresh(){
   const ticket=++epoch;
   stopClock();
   for(const tile of tiles.values()){
     clear(tile);tile.rows=[];state(tile,'loading',null,'正在读取…');
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
   accountKey=scopeKey;buffer.clear();data=responses.map(result=>result.status==='fulfilled'?result.value:null);
   apply();
 }
 return {
   project:()=>project,
   setProject(value){
     if(project===value)return;
     project=value;
     if(active&&data)apply();
   },
   selectedArticle(){const item=tiles.get('articles').item;return item?{project_id:item.project,work_id:item.value.work_id}:null;},
   open(){
     if(active)return;
     active=true;for(const tile of tiles.values()){view.observe(tile.node);size.observe(tile.media);}
     void refresh();
   },
   close(){
     active=false;epoch++;data=null;stopClock();buffer.clear();view.disconnect();size.disconnect();
     for(const tile of tiles.values()){clear(tile);tile.rows=[];}
   }
 };
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
