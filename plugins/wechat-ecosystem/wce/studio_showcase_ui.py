"""The bundled case is a separate, read-only workbench surface."""

HTML = '''
<section id="studioShowcase" aria-labelledby="scTitle" hidden lang="zh-CN">
 <header class="sc-header">
  <div><p class="sc-kicker">内置演示 · 龟爷爷夜间电台</p><h1 id="scTitle" tabindex="-1">龟爷爷演播室</h1></div>
  <button id="scExit" type="button">退出案例</button>
 </header>
 <nav id="scTabs" aria-label="演播室案例">
  <button data-case-tab="assets" type="button">资产</button>
  <button data-case-tab="monitor" type="button">导演台</button>
  <button data-case-tab="canvas" type="button">画布</button>
 </nav>
 <div id="scContent" aria-label="案例内容"></div>
 <p id="scStatus" role="status" aria-live="polite" hidden></p>
</section>
'''

STYLE = '''
#studioShowcase:not([hidden]) {
 display:grid;grid-template-rows:auto auto minmax(0,1fr) auto;gap:10px;
 height:100%;min-height:0;box-sizing:border-box;
 padding:var(--wb-top) clamp(11px,2.4vw,32px) var(--wb-dock);
}
#studioShowcase [hidden]{display:none!important}
#studioShowcase button{font:inherit;min-height:30px;color:var(--wb-ink);cursor:pointer}
#studioShowcase button[aria-pressed=true]{background:var(--oa-selection,var(--tint));border-color:var(--line)}
#studioShowcase button:focus-visible{outline:2px solid #c68964;outline-offset:1px}
#studioShowcase h1,#studioShowcase h2,#studioShowcase h3,#studioShowcase p{margin:0}
.sc-header{display:flex;align-items:center;justify-content:space-between;gap:12px}
.sc-header h1{font-size:clamp(21px,2.2vw,32px);line-height:1.1}
.sc-kicker{font-size:11px;letter-spacing:.03em;color:var(--muted);margin-bottom:5px!important}
#scTabs,.sc-bar,.sc-links{display:flex;align-items:center;gap:6px;flex-wrap:wrap}
#scContent{min-height:0;min-width:0;overflow:auto;overscroll-behavior:contain}
#scStatus{font-size:12px;color:var(--muted)}
.sc-gallery{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:10px;padding:1px}
#studioShowcase .sc-card{padding:0;overflow:hidden;text-align:start;display:grid;
 gap:0;text-wrap:wrap;min-width:0;background:var(--surface);border-radius:11px;border:1px solid var(--line)}
.sc-card figure{margin:0;aspect-ratio:2.55;background:#27201f;position:relative;overflow:hidden}
.sc-card img{width:100%;height:100%;object-fit:cover;display:block}
.sc-card[data-role=characters] img{object-position:center 22%}
.sc-card small{position:absolute;bottom:7px;right:7px;border-radius:20px;background:#1d1919da;
 color:#fff;padding:3px 7px;font-size:10px}
.sc-card-copy{display:grid;gap:2px;padding:8px 10px;color:var(--wb-ink)}
.sc-card-copy span{font-size:11px;color:var(--muted)}
.sc-layout{min-height:100%;display:grid;grid-template-columns:minmax(0,1fr) minmax(185px,27%);gap:11px;padding:1px}
.sc-main,.sc-aside{min-width:0;background:var(--surface);border:1px solid var(--line);border-radius:11px;padding:11px;
 display:grid;align-content:start;gap:8px}
.sc-stage{min-width:0;display:grid;gap:8px}
.sc-stage :is(video, img){max-width:100%;width:100%;max-height:min(56dvh,560px);
  display:block;object-fit:contain;border-radius:8px;background:#252020}
.sc-stage img:not([src]){visibility:hidden}
.sc-stage video{aspect-ratio:16/9}
.sc-article-wrap{background:var(--soft);border-radius:9px;padding:0 5px;max-height:min(57dvh,625px);overflow:auto}
.sc-article{background:#fff;color:#272722;max-width:418px;margin:auto;padding:16px;min-height:230px}
.sc-article h2{font-size:24px;line-height:1.35;margin-bottom:10px!important}
.sc-article h3{font-size:18px;margin:16px 0 6px!important}
.sc-article p{font-size:14px;line-height:1.7;margin:8px 0!important}
.sc-article figure{margin:11px 0}
.sc-article img{width:100%;height:auto;background:#f0eeea}
.sc-article figcaption{font-size:11px;color:#5b5a55}
.sc-aside p,.sc-caption{font-size:12px;color:var(--muted);line-height:1.6}
.sc-aside h3{font-size:13px}
.sc-selection{font-size:12px;line-height:1.6}
.sc-wave{width:100%;height:65px;display:block;border-radius:8px;background:#28211d}
.sc-stage audio{width:100%}
.sc-canvas{display:grid;gap:12px;min-height:240px;padding:17px;align-content:center;
 background:radial-gradient(circle at 1px 1px,var(--line) 1px,transparent 1px) 0 0/16px 16px;
 border:1px solid var(--line);border-radius:10px}
.sc-canvas-row{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:7px}
#studioShowcase .sc-node{min-height:54px;display:grid;place-content:center;text-align:center;overflow-wrap:anywhere;padding:5px}
.sc-node small{font-size:10px;color:var(--muted)}
@media(max-width:690px){
 #studioShowcase:not([hidden]){padding-top:52px;gap:7px}
 .sc-gallery{grid-template-columns:repeat(2,minmax(0,1fr));gap:7px}
 .sc-card figure{aspect-ratio:2.2}
 .sc-card-copy{padding:6px 7px}
 .sc-layout{grid-template-columns:minmax(0,1fr)}
 .sc-main,.sc-aside{padding:8px}
 .sc-canvas{padding:8px;min-height:126px}
 .sc-article-wrap{max-height:55dvh}
}
'''

SCRIPT = r'''
function OAStudioShowcase(call, exit){
 const root=document.getElementById('studioShowcase'),content=document.getElementById('scContent');
 const status=document.getElementById('scStatus'),tabs=[...root.querySelectorAll('[data-case-tab]')];
 const categories=[
   ['characters','形象','主参考和冷调候选','thumb-character','2 版'],
   ['images','图片','演播室封面与正文配图','thumb-image','2 张'],
   ['gif','动图','演播室灯光循环','thumb-gif','4 秒'],
   ['video','视频','夜间电台片头','thumb-video','2 版'],
   ['audio','音频','四组暖和弦','thumb-audio','6 秒'],
   ['articles','文章','龟爷爷夜间电台制作手记','thumb-article','2 版'],
 ];
 const galleryNames=Object.fromEntries(categories.map(([id,title])=>[id,title]));
 const workNames={film:'夜间电台 · 片头短片',article:'夜间电台 · 制作手记'};
 let active=false, page='assets', kind='', work='film', manifest=null, ready=null;
 let epoch=0, clip=2, article=2, character='character-main', still='cover', node='shot';
 const stored=new Map();
 const current=stamp=>active&&stamp===epoch;
 function el(tag, text='', cls=''){
   const item=document.createElement(tag);
   if(text)item.textContent=text;
   if(cls)item.className=cls;
   return item;
 }
 function button(text, handler, pressed){
   const item=el('button',text);
   item.type='button';item.onclick=handler;
   if(pressed!==undefined)item.setAttribute('aria-pressed',String(pressed));
   return item;
 }
 function setStatus(text){status.textContent=text;status.hidden=!text;}
 function release(){
   for(const asset of stored.values())if(asset.url)URL.revokeObjectURL(asset.url);
   stored.clear();
 }
 function requestIndex(){
   if(manifest)return Promise.resolve(manifest);
   if(!ready)ready=call('showcase_index',{}).then(data=>{
     if(data.schema!==1||!data.media||data.articles?.length!==2)throw Error('STUDIO_SHOWCASE_INDEX_CHANGED');
     manifest=data;return manifest;
   }).finally(()=>{ready=null;});
   return ready;
 }
 function load(id){
   if(stored.has(id))return stored.get(id).promise;
   const asset={url:null,promise:null};
   stored.set(id,asset);
   asset.promise=(async()=>{
     const meta=manifest.media[id], result=new Uint8Array(meta.bytes);
     let offset=0;
     while(offset<result.length){
       if(stored.get(id)!==asset)throw Error('STUDIO_SHOWCASE_CLOSED');
       const part=await call('showcase_blob',{media_id:id,offset});
       if(part.media_id!==id||part.offset!==offset||part.total!==result.length||
          part.sha256!==meta.sha256||part.mime!==meta.mime)throw Error('STUDIO_SHOWCASE_MEDIA_CHANGED');
       const bytes=Uint8Array.from(atob(part.data),ch=>ch.charCodeAt(0));
       if(!bytes.length||part.next!==offset+bytes.length||part.next>result.length)throw Error('STUDIO_SHOWCASE_MEDIA_CHANGED');
       result.set(bytes,offset);offset=part.next;
     }
     if(globalThis.crypto?.subtle){
       const checksum=Array.from(new Uint8Array(await crypto.subtle.digest('SHA-256',result)),
           byte=>byte.toString(16).padStart(2,'0')).join('');
       if(checksum!==meta.sha256)throw Error('STUDIO_SHOWCASE_MEDIA_CHANGED');
     }
     if(stored.get(id)!==asset)throw Error('STUDIO_SHOWCASE_CLOSED');
     const blob=new Blob([result],{type:meta.mime});
     asset.url=URL.createObjectURL(blob);
     return {url:asset.url, bytes:result};
   })().catch(error=>{if(stored.get(id)===asset)stored.delete(id);throw error;});
   return asset.promise;
 }
 function bind(target,id,stamp){
   void load(id).then(asset=>{if(current(stamp))target.src=asset.url;}).catch(()=>{
     if(current(stamp))setStatus('样例素材不可读取。请关闭案例后重新打开。');
   });
   return target;
 }
 function image(id,alt,stamp){
   const item=el('img');item.alt=alt;item.decoding='async';
   return bind(item,id,stamp);
 }
 function link(label, target, section, selectedWork){
   return button(label,()=>go(target,section,selectedWork,true));
 }
 function go(target, section='', selectedWork=work, focus=false){
   page=target;kind=section;work=selectedWork;
   render(focus);
 }
 function group(title, text, commands=[]){
   const side=el('aside','','sc-aside');side.append(el('h3',title));
   if(text)side.append(el('p',text));
   if(commands.length){const row=el('div','','sc-links');row.append(...commands);side.append(row);}
   return side;
 }
 function layout(title, aside){
   const pair=el('div','','sc-layout'),main=el('section','','sc-main');
   const heading=el('h2',title);heading.tabIndex=-1;
   main.append(heading);pair.append(main,aside);content.append(pair);return main;
 }
 function versions(values,get,choose){
   const line=el('div','','sc-bar');
   for(const [id,label] of values)line.append(button(label,()=>{choose(id);render();},id===get()));
   return line;
 }
 function gallery(stamp){
   const grid=el('div','','sc-gallery');
   for(const [id,title,caption,thumb,badge] of categories){
     const card=el('button','','sc-card');card.dataset.role=id;card.type='button';
     card.onclick=()=>go('assets',id,work,true);
     const figure=el('figure'),copy=el('span','','sc-card-copy');
     figure.append(image(thumb,'',stamp),el('small',badge));
     copy.append(el('strong',title),el('span',caption));card.append(figure,copy);grid.append(card);
   }
   content.append(grid);
 }
 function film(stage, stamp){
   const player=el('video');player.controls=true;player.playsInline=true;player.preload='metadata';
   void load('thumb-video').then(asset=>{if(current(stamp))player.poster=asset.url;}).catch(()=>{});
   player.setAttribute('aria-label','夜间电台第 '+clip+' 版片头');
   stage.append(bind(player,'clip-v'+clip,stamp));
 }
 function soundtrack(stage,stamp){
   const waveform=el('canvas','','sc-wave');waveform.width=598;waveform.height=65;
   waveform.setAttribute('aria-label','片头配乐波形');
   const audio=el('audio');audio.controls=true;audio.preload='metadata';audio.setAttribute('aria-label','四组暖和弦');
   stage.append(waveform,bind(audio,'score',stamp));
   void load('score').then(({bytes})=>{
     if(!current(stamp))return;
     // Read the bundled WAV's PCM16 data chunk for the display waveform.
     const view=new DataView(bytes.buffer,bytes.byteOffset,bytes.byteLength);
     let p=12;
     while(p+8<=bytes.length){
       const id=view.getUint32(p),size=view.getUint32(p+4,true);
       if(size>bytes.length-p-8)return;
       if(id===0x64617461){
         const g=waveform.getContext('2d'), step=Math.max(2,2*Math.floor(size/200));
         g.fillStyle='#cf9469';
         for(let start=0,i=0;start+1<size;start+=step,i++){
           let peak=0;
           for(let j=start;j+1<Math.min(size,start+step);j+=2)
             peak=Math.max(peak,Math.abs(view.getInt16(p+8+j,true)));
           const h=3+peak/32768*88;
           g.fillRect(i*waveform.width*step/size,(65-h)/2,3.7,h);
         }
         return;
       }
       p+=8+size+(size%2);
     }
   }).catch(()=>{});
 }
 function articleReader(stage, stamp){
   const result=manifest.articles.find(row=>row.version===article);
   const scroll=el('div','','sc-article-wrap'),reader=el('article','','sc-article');
   reader.append(el('h2',result.title),el('p',result.author+' · 第 '+article+' 版'));
   for(const block of result.blocks){
     if(block.kind==='image'){
       const figure=el('figure');figure.append(image(block.media,block.alt,stamp));
       if(block.caption)figure.append(el('figcaption',block.caption));
       reader.append(figure);
     }else reader.append(el(block.kind==='heading'?'h3':'p',block.text));
   }
   scroll.append(reader);stage.append(scroll);
 }
 function clipVersions(){return versions([[1,'v1 原片'],[2,'v2 配乐版']],()=>clip,id=>{clip=id;});}
 function articleVersions(){return versions([[1,'第 1 版'],[2,'第 2 版']],()=>article,id=>{article=id;});}
 function setupArticle(section,stamp){const stage=el('div','','sc-stage');section.append(articleVersions(),stage);articleReader(stage,stamp);}
 function setupVideo(section,stamp){const stage=el('div','','sc-stage');section.append(clipVersions(),stage);film(stage,stamp);}
 function assets(stamp){
   if(!kind){gallery(stamp);return;}
   const cross=[link('短片导演台','monitor','','film'),link('图文画布','canvas','','article')];
   const description={
     characters:'片头镜头采用暖光主参考。冷调近景作为对照候选。',
     images:'封面与麦克风细节图用于两版图文。点击图片可查看包内原件。',
     gif:'取自夜间电台原片前四秒，循环播放。',
     video:clip===2?'v2 使用「四组暖和弦」作为片头配乐。':'v1 是演播室原片，保留无声版本用于对照。',
     audio:'本地合成配乐，采用于六秒片头短片 v2。',
     articles:'这篇制作手记和短片使用同一演播室画面。两版正文均可读。',
   }[kind];
   if(kind==='video'&&clip===2)cross.unshift(link('查看所用配乐','assets','audio'));
   if(kind==='audio')cross.unshift(button('查看采用片段 v2',()=>{clip=2;go('assets','video','film',true);}));
   if(kind==='articles')cross.unshift(link('图文导演台','monitor','','article'));
   const side=group('作品关系',description,cross);
   const section=layout(galleryNames[kind],side);
   const back=link('返回资产目录','assets','');
   section.append(el('div','','sc-bar'));section.lastElementChild.append(back);
   if(kind==='video'){setupVideo(section,stamp);return;}
   if(kind==='articles'){setupArticle(section,stamp);return;}
   const stage=el('div','','sc-stage');
   if(kind==='characters'){
     section.append(versions([['character-main','暖光主参考'],['character-alt','冷调候选']],()=>character,id=>{character=id;}));
     stage.append(image(character,character==='character-main'?'龟爷爷暖光主参考':'龟爷爷冷调候选',stamp));
   }
   if(kind==='images'){
     section.append(versions([['cover','演播室封面'],['body','正文配图']],()=>still,id=>{still=id;}));
     const full=image(still,still==='cover'?'演播室封面原件':'麦克风和桌面灯光原件',stamp);
     stage.append(full);
     const open=button('查看原图',()=>{
       if(!full.src)return;
       const dialog=el('dialog'),close=button('关闭原图',()=>dialog.close());
       const picture=el('img');picture.src=full.src;picture.alt=full.alt;
       picture.style.cssText='width:100%;max-height:75dvh;object-fit:contain';
       dialog.append(close,picture);root.append(dialog);
       dialog.addEventListener('close',()=>{dialog.remove();open.focus();},{once:true});dialog.showModal();
     });
     stage.append(open);
   }
   if(kind==='gif')stage.append(image('gif','演播室灯光循环 GIF',stamp));
   if(kind==='audio')soundtrack(stage,stamp);
   section.append(stage);
 }
 function workSwitch(){return versions([['film','短片'],['article','图文']],()=>work,
      id=>{work=id;node='shot';});}
 function monitor(stamp){
   const aside=work==='film'?
      group('采用关系','镜头使用龟爷爷暖光主参考。v2 采用四组暖和弦配乐。',[
        link('查看角色','assets','characters'),link('查看配乐','assets','audio'),link('短片画布','canvas','','film')]):
      group('图文素材','文章封面、正文图和两版正文保存在案例中。',[
        link('查看图文画布','canvas','','article'),link('查看配图','assets','images'),link('同源短片','monitor','','film')]);
   const section=layout(workNames[work],aside);section.append(workSwitch());
   if(work==='film')setupVideo(section,stamp);else setupArticle(section,stamp);
 }
 function canvas(stamp){
   const names=work==='film'?
     [['shot','镜头 01','窗影与麦克风'],['reference','主参考','暖光正面'],['output','片头成片','v1 / v2']]:
     [['shot','正文','两版制作手记'],['reference','封面','演播室原图'],['output','正文配图','麦克风细节']];
   const currentNode=names.find(([id])=>id===node)||names[0];
   const side=group('当前选择',currentNode[1]+' · '+currentNode[2],[
     link('去导演台','monitor','',work),link(work==='film'?'角色档案':'图片档案','assets',work==='film'?'characters':'images'),
   ]);
   const section=layout(workNames[work],side);section.append(workSwitch());
   const graph=el('div','','sc-canvas'),row=el('div','','sc-canvas-row');
   for(const [id,label,tag] of names){
     const control=button(label,()=>{node=id;render(true,id);},id===node);
     control.className='sc-node';control.dataset.caseNode=id;control.append(el('small',tag));row.append(control);
   }
   graph.append(row);section.append(graph);
   const stage=el('div','','sc-stage');section.append(stage);
   if(node==='reference')stage.append(image(work==='film'?'character-main':'cover',currentNode[1],stamp));
   else if(work==='film'&&node==='output')setupVideo(section,stamp);
   else if(work==='article'&&node==='shot')setupArticle(section,stamp);
   else if(work==='article')stage.append(image('body',currentNode[1],stamp));
   else stage.append(el('p','桌灯落在镜框与麦克风之间，窗后的蓝色保持轻微流动。','sc-selection'));
 }
 function render(focus=false, selectedNode=''){
   const stamp=++epoch;
   content.replaceChildren();setStatus('');
   if(!active)return;
   for(const tab of tabs)tab.setAttribute('aria-pressed',String(tab.dataset.caseTab===page));
   if(!manifest){
     setStatus('正在读取内置案例…');
     void requestIndex().then(()=>{if(current(stamp))render(focus);}).catch(()=>{
       if(current(stamp))setStatus('内置案例暂不可读。');
     });
     return;
   }
   if(page==='assets')assets(stamp);else if(page==='monitor')monitor(stamp);else canvas(stamp);
   content.scrollTop=0;
   if(focus)(selectedNode?content.querySelector('[data-case-node="'+selectedNode+'"]'):
       content.querySelector('h2')||tabs[0])?.focus({preventScroll:true});
 }
 for(const tab of tabs)tab.onclick=()=>go(tab.dataset.caseTab);
 document.getElementById('scExit').onclick=exit;
 return {
   show(open,focus=false){
     if(active===open)return;
     active=open;root.hidden=!active;
     if(active){
       render();
       if(focus)document.getElementById('scTitle').focus({preventScroll:true});
     }else{
       epoch++;
       for(const dialog of root.querySelectorAll('dialog')){dialog.close();dialog.remove();}
       content.replaceChildren();release();setStatus('');
     }
   },
 };
}
'''
