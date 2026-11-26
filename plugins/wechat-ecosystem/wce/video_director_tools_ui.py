"""Director's collapsible tool shelf. The active tool uses the existing inspector column."""
from .workbench_ui import NOTCH_PATH
from . import video_director_caption_tools_ui as captions

# A line icon and compact tab label remain visible at the edge of the preview.
TOOLS = (
    ('media','素材','Media','M3 5h18v14H3z M6 15l4-4 3 3 3-4 3 5'),
    ('audio','音频','Audio','M9 17V6l11-2v11 M9 8l11-2 M9 17a3 2 0 1 1-3-2h3 M20 15a3 2 0 1 1-3-2h3'),
    ('edit','剪辑','Edit','M4 4l16 16 M4 20l16-16 M8 6a3 3 0 1 1-6 0a3 3 0 1 1 6 0 M8 18a3 3 0 1 1-6 0a3 3 0 1 1 6 0'),
    ('text','文字','Text','M3 7V4h18v3 M12 4v16 M8 20h8'),
    ('captions','歌词与字幕','Lyrics and captions','M2 5h20v14H2z M5 11h5m3 0h6 M5 15h9'),
    ('effect','特效','Effects','M12 2l2.4 7.5L22 12l-7.6 2.5L12 22l-2.4-7.5L2 12l7.6-2.5z'),
    ('transition','转场','Transitions','M3 5h18v14H3z M16 5L8 19 M13 9l4 5'),
    ('filter','滤镜','Filters','M9 4a6 6 0 1 0 .1 0 M15 8a6 6 0 1 0 .1 0'),
    ('adjust','调节','Adjust','M3 6h6m4 0h8 M3 12h13m4 0h1 M3 18h3m4 0h11 M9 3v6 M16 9v6 M6 15v6'),
    ('frame','画面','Frame','M3 8V3h5m8 0h5v5m0 8v5h-5m-8 0H3v-5 M8 8h8v8H8z'),
    ('speed','变速','Speed','M3 17a9 9 0 1 1 18 0 M12 15l5-7 M5 13h2m10 0h2'),
    ('sound','音效','Sound FX','M2 10v4m4-8v12m4-15v18m4-14v10m4-12v14m4-9v4'),
    ('motion','动画','Motion','M3 12l5-5 5 5-5 5z M14 6h7m-5 6h5m-7 6h7'),
)


def icon(path):
    return f'<svg viewBox="0 0 24 24" aria-hidden="true" focusable="false"><path d="{path}"/></svg>'


def tab(tool):
    key, zh, en, path = tool
    return (f'<button type="button" data-dt-tab="{key}" data-en="{en}" title="{zh}" aria-pressed="false" '
            f'aria-controls="dtPanel dmCutSettings">{icon(path)}<span>{zh}</span></button>')


EDIT_TOOLS = ('edit', 'frame', 'speed', 'adjust', 'sound')
ADD_TOOLS = ('media', 'audio', 'text', 'captions', 'filter', 'effect', 'transition', 'motion')


def rail(side, keys, label, path, transform):
    options = {tool[0]: tool for tool in TOOLS}
    title = '剪辑工具' if side == 'Edit' else '添加内容与效果'
    return (f'<aside id="dt{side}Rail" class="dt-rail" aria-label="{title}">'
            '<svg class="wb-notch-shell" viewBox="0 0 38 288" preserveAspectRatio="none" aria-hidden="true" focusable="false">'
            f'<path transform="{transform}" d="{NOTCH_PATH}"/></svg>'
            f'<button class="dt-toggle" type="button" aria-expanded="false" aria-controls="dt{side}List" title="{title}">'
            f'{icon(path)}<span>{label}</span></button><div id="dt{side}List" class="dt-list" hidden>'
            + ''.join(tab(options[key]) for key in keys) + '</div></aside>')


EDIT_RAIL = rail('Edit', EDIT_TOOLS, '工具', 'M4 7h9m4 0h3 M4 16h3m4 0h9 M13 4v6 M7 13v6', 'translate(0 288) rotate(-90)')
ADD_RAIL = rail('Add', ADD_TOOLS, '添加', 'M12 4v16M4 12h16', 'translate(38 0) rotate(90)')
PANEL = '''
 <section id="dtPanel" class="dm-panel" hidden aria-labelledby="dtTitle">
 <header class="dm-heading"><h2 id="dtTitle"></h2><button type="button" id="dtClose">×</button></header>
 <p id="dtSelection"></p><div id="dtBody"></div><p id="dtStatus" role="status"></p>
 <footer id="dtSave"><output id="dtSaveState" role="status"></output> <button type="button" id="dtRetry" hidden></button></footer>
 </section>'''

STYLE = '''
#directorMonitor .dt-rail{position:fixed;z-index:18;top:calc(50% - 12px);transform:translateY(-50%);
 display:flex;flex-direction:column;align-items:stretch;width:var(--wb-side-width);max-height:calc(100dvh - 145px);
 padding:12px 3px 12px 0;box-sizing:border-box;isolation:isolate}
#dtEditRail{left:0}
#dtAddRail{right:0}
#directorMonitor #dtAddRail{padding-inline:3px 0}
#dtAddRail .wb-notch-shell{filter:drop-shadow(-2px 1px 2px #0003)}
.oa-native[data-workbench=monitor]:has(#directorMonitor:not([hidden])) #wbSideActions{display:none}
.dt-rail .wb-notch-shell{z-index:-1;pointer-events:none;filter:drop-shadow(2px 1px 2px #0003)}
#videoDirectorDesk #directorMonitor .dt-rail button{display:flex;flex-direction:column;justify-content:center;align-items:center;gap:2px;
 width:100%;min-width:0;min-height:39px;padding:3px 0;margin:0;border:0;box-shadow:none;background:transparent;
 color:var(--wb-ink);border-radius:6px;font:500 10px/1.1 system-ui;cursor:pointer}
.dt-rail button svg{width:17px;height:17px;fill:none;stroke:currentColor;stroke-width:1.6;stroke-linecap:round;stroke-linejoin:round}
#videoDirectorDesk #directorMonitor .dt-rail button:hover,#videoDirectorDesk #directorMonitor .dt-rail button[aria-pressed=true]{background:var(--wb-dock-inset-color,var(--soft));color:var(--accent)}
#videoDirectorDesk #directorMonitor .dt-rail button[aria-pressed=true]{box-shadow:inset 2px 0 currentColor}
.dt-rail .dt-list{min-height:0;overflow-y:auto;scrollbar-width:none;overscroll-behavior:contain}
.dt-rail .dt-list[hidden],#directorMonitor #dtPanel[hidden],#dtSelection:empty,#dtStatus:empty{display:none}
.dt-rail .dt-toggle{flex-shrink:0}
.dt-rail .dt-list button span{max-width:100%;overflow:hidden;text-overflow:ellipsis}
#dtPanel{grid-area:settings;min-height:0;overflow:auto;align-self:stretch;display:flex;flex-direction:column;gap:10px}
#dtPanel .dm-heading{border-bottom:1px solid var(--line);padding-bottom:7px}
#dtPanel .dm-heading button{min-width:30px;min-height:28px;padding:0;font-size:18px}
#dtPanel #dtSave,#dtPanel #dtSelection,#dtPanel #dtStatus{font-size:11px;color:var(--muted)}
#dtPanel #dtSave{align-self:start;margin-top:auto}
#dtPanel #dtRetry[hidden]{display:none}
#dtBody{display:grid;gap:10px}
#dtBody textarea{resize:vertical;min-height:54px}
#dtBody .dt-options{display:grid;grid-template-columns:repeat(auto-fit,minmax(min(65px,100%),1fr));gap:6px}
#dtBody button{min-width:0;overflow-wrap:anywhere}
#dtBody button[aria-pressed=true]{background:var(--accent);color:var(--panel,Canvas)}
#dtBody .dt-field{display:grid;gap:4px}
#dtBody .dt-actions{display:flex;flex-wrap:wrap;align-items:center;gap:5px}
#dtBody .dt-range{display:grid;grid-template-columns:minmax(0,1fr) 4ch;align-items:center;gap:5px}
#dtBody .dt-range output{font-variant-numeric:tabular-nums;text-align:end}
#directorMonitor[data-dt-custom] #dmCutSettings{display:none}
#directorMonitor[data-dt-view=media] #dmCutSettings>:not(header,.dc-toolbar,.dc-delivery),
#directorMonitor[data-dt-view=audio] #dmCutSettings>:not(header,.dc-music,.dc-inspector,.dc-delivery){display:none}
#directorMonitor[data-dt-view=audio] .dc-inspector>label:not(:last-child){display:none}
@media(max-height:600px){#videoDirectorDesk #directorMonitor .dt-rail button{min-height:34px}}
'''

SCRIPT = captions.SCRIPT + r"""
function OADirectorTools(timeline,read,edit,getScope){
 const $=id=>document.getElementById(id),desk=$('directorMonitor'),rails=[...desk.querySelectorAll('.dt-rail')];
 const panel=$('dtPanel'),body=$('dtBody'),status=$('dtStatus'),selection=$('dtSelection');
 const tabs=[...desk.querySelectorAll('[data-dt-tab]')], original=new Map(tabs.map(b=>[b,b.textContent.trim()]));
 const en=()=>document.documentElement.lang.toLowerCase().startsWith('en'), t=(zh,eng)=>en()?eng:zh;
 const tabName=b=>en()?b.dataset.en:original.get(b);
 let active='',stamp='',generation=0,loading=false,updateFields=()=>{};
 const elt=(tag,cls='')=>{const el=document.createElement(tag);if(cls)el.className=cls;return el;};
 function control(parent,name,act,cls=''){
   const b=elt('button',cls);b.type='button';b.textContent=name;b.onclick=act;parent.append(b);return b;
 }
 function group(cls='dt-actions'){const el=elt('div',cls);body.append(el);return el;}
 function field(name,input){const l=elt('label','dt-field'),s=elt('span');s.textContent=name;l.append(s,input);body.append(l);}
 function message(value){status.textContent=value;}
 function savedAction(fn){
   const clip=timeline.getToolClip();if(!clip||clip.busy)return;
   try{if(fn(clip)===false)message(t('请选择可编辑的片段','Select an editable clip'));}
   catch(err){message(err.message);}
 }
 function commit(patch){savedAction(c=>timeline.setToolLook(patch,c.id));}
 function choices(key,options){
   const g=group('dt-options'), items=[];
   for(const [val,zh,eg] of options){
     const b=control(g,t(zh,eg),()=>commit({[key]:val}));items.push([b,val]);
   }
   return clip=>items.forEach(([b,val])=>b.setAttribute('aria-pressed',String((clip?.look?.[key]??null)===val)));
 }
 function range(key,label,english,min,max,base){
   const line=elt('div','dt-range'),input=elt('input'),out=elt('output');
   const l=elt('label','dt-field');const s=elt('span');s.textContent=t(label,english);
   input.type='range';input.min=min;input.max=max;input.step=1;input.setAttribute('aria-label',s.textContent);
   input.oninput=()=>{out.value=input.value+'%';};
   input.onchange=()=>commit({[key]:Number(input.value)});
   line.append(input,out);l.append(s,line);body.append(l);
   return clip=>{input.value=clip?.look?.[key]??(key==='zoom_end'?clip?.look?.zoom:undefined)??base;out.value=input.value+'%';};
 }
 function editor(key,label,english,limit){
   const box=elt('textarea');box.maxLength=limit;field(t(label,english),box);const g=group();
   let composing=false,owner='';
   const apply=()=>{if(!composing&&owner&&timeline.getToolClip()?.id===owner)commit({[key]:box.value.trim()?box.value:null});};
   box.addEventListener('compositionstart',()=>{composing=true;});
   box.addEventListener('compositionend',()=>{composing=false;apply();});
   box.addEventListener('input',apply);
   control(g,t('移除','Remove'),()=>commit({[key]:null}));
   let prior;return c=>{owner=c?.id||'';const value=c?.look?.[key]??'',sig=JSON.stringify([owner,value]);
     if(sig!==prior){if(!composing&&box.value!==value)box.value=value;prior=sig;}
   };
 }
 function captionLineEditor(){
   const group=elt('section'),picker=elt('select'),box=elt('textarea');
   const pickLabel=elt('label','dt-field'),editLabel=elt('label','dt-field');
   pickLabel.append(t('已定时的歌词与字幕','Timed lyrics and captions'),picker);
   editLabel.append(t('校对文字','Correct text'),box);
   box.maxLength=400;group.append(pickLabel,editLabel);body.append(group);
   let snapshot=[],lines=[],index=0,signature='',editing=false;
   function display(){
     const row=lines[index];
     if(row)box.value=row.text;
   }
   function load(){
     const clips=timeline.getToolClips(),next=OADirectorCaptions.existing(clips),key=JSON.stringify(next);
     if(editing)return;
     snapshot=clips;group.hidden=!next.length;
     if(signature===key)return;
     signature=key;lines=next;index=Math.max(0,Math.min(index,lines.length-1));
     picker.replaceChildren(...lines.map((line,i)=>new Option((line.in_ms/1000).toFixed(2)+' s · '+line.text,String(i))));
     picker.value=String(index);display();
   }
   picker.onchange=()=>{index=Number(picker.value);display();};
   box.onfocus=()=>{load();editing=true;};
   box.onblur=()=>{
     if(!editing)return;
     const line=lines[index];editing=false;
     if(!line)return;
     try{OADirectorCaptions.correctLine(timeline,snapshot,line,box.value);}
     catch(err){message(err.message);}
     load();display();
   };
   return load;
 }
 function captionTools(){
   const lines=captionLineEditor();
   const basic=editor('caption','片段字幕','Clip caption',200);
   const source=elt('textarea');source.setAttribute('spellcheck','false');
   field(t('定时字幕 · SRT / LRC','Timed captions · SRT / LRC'),source);
   let transcript=null;const row=group(),file=elt('input');file.type='file';file.accept='.srt,.lrc,text/plain';file.hidden=true;row.append(file);
   control(row,t('读取文件','Read file'),()=>file.click());
   file.onchange=async()=>{const f=file.files[0],g=generation;file.value='';if(!f)return;
     if(f.size>1024*1024){message(t('字幕文件上限 1 MB','Caption files must be under 1 MB'));return;}
     try{const text=await f.text();if(g===generation){source.value=text;transcript=null;message(f.name);}}catch(e){if(g===generation)message(e.message);}};
   control(row,t('应用字幕','Apply captions'),()=>{try{let n;
     if(transcript){
       const {receipt,start,clips}=transcript;
       const parsed=OADirectorCaptions.parse(source.value,clips),delta=start-receipt.start_ms;
       if(parsed.cues.some(c=>c.in_ms<start||c.out_ms>start+receipt.end_ms-receipt.start_ms))throw Error(t('校对字幕须在识别时段内','Edited cues must stay within the transcribed range'));
       n=OADirectorCaptions.importTranscript({...receipt,cues:parsed.cues.map(c=>({...c,in_ms:c.in_ms-delta,out_ms:c.out_ms-delta}))},start,timeline,clips);
       transcript=null;
     }else n=OADirectorCaptions.importText(source.value,timeline);
     message(t('已应用字幕','Captions applied')+(typeof n==='number'?' · '+n:''));}catch(e){message(e.message);}});
   control(row,t('导出 SRT','Export SRT'),()=>{try{OADirectorCaptions.download(timeline.getToolClips());}catch(e){message(e.message);}});
   const origin=elt('select');for(const [v,z,e] of [['original','当前片段原声','Clip audio'],['song','配乐','Music track']]){const op=elt('option');op.value=v;op.textContent=t(z,e);origin.append(op);}
   origin.value=timeline.getToolMusic()?'song':'original';field(t('识别音源','Transcription source'),origin);
   const lang=elt('select');for(const [v,z,e] of [['auto','自动','Auto'],['zh','中文','Chinese'],['en','英语','English']]){
     const op=elt('option');op.value=v;op.textContent=t(z,e);lang.append(op);}
   field(t('识别语言','Recognition language'),lang);
   const asr=control(group(),t('本地识别（最多 30 秒）','Transcribe audio (up to 30 s)'),async()=>{
     const clip=timeline.getToolClip(),scope=getScope(),g=generation;if(!clip||!scope||loading)return;
     const clips=timeline.getToolClips(),index=clips.findIndex(x=>x.id===clip.id);if(index<0)return;
     let start=clips.slice(0,index).reduce((n,c)=>n+c.out_ms-c.in_ms,0);
     const snapshot=JSON.stringify(clips),music=origin.value==='song'?timeline.getToolMusic():null;
     if(origin.value==='song'&&!music){message(t('请先选择配乐','Select a music track first'));return;}
     const media=music||clip,sourceArgs=music?{attempt_id:music.attempt_id}:{delivery_id:clip.delivery_id};
     if(music)start=music.start_ms;
     const end=Math.min(media.out_ms,media.in_ms+30000,media.in_ms+clips.reduce((n,c)=>n+c.out_ms-c.in_ms,0)-start);
     if(end<=media.in_ms){message(t('音源在时间线以外','Audio lies outside the timeline'));return;}
     loading=true;asr.disabled=true;message(t('正在本机识别…','Transcribing locally…'));
     try{const result=await read('timeline_transcribe',{...scope,...sourceArgs,sha256:media.sha256,start_ms:media.in_ms,
       end_ms:end,language:lang.value});
       if(g!==generation)return;
       if(timeline.getToolClip()?.id!==clip.id||JSON.stringify(timeline.getToolClips())!==snapshot||(music&&JSON.stringify(timeline.getToolMusic())!==JSON.stringify(music))){message(t('片段已变更，请重新识别','Clip changed. Transcribe again.'));return;}
       if(!result.cues?.length){message(t('选区内未识别到语音','No speech detected in this range'));return;}
       transcript={receipt:result,start,clips};source.value=OADirectorCaptions.transcriptSRT(result,start);
       message(t('识别完成，可校对后应用','Transcription ready for review'));
     }catch(e){if(g===generation)message(t('本机识别未完成','Local transcription unavailable')+' · '+e.message);}
     finally{if(g===generation){loading=false;asr.disabled=!timeline.getToolClip();}}
   });
   return clip=>{lines();basic(clip);asr.disabled=loading||!clip||clip.busy;};
 }
 function buttons(rows){const g=group();return rows.map(([key,zh,eg])=>{
   const button=control(g,t(zh,eg),()=>timeline.runToolCommand(key));
   const mac=/Mac|iPad|iPhone/i.test(navigator.platform),mod=mac?'⌘':'Ctrl+';
   const hint={undo:mod+'Z',redo:mod+(mac?'⇧':'Shift+')+'Z',split:mod+'B',delete:'Delete'}[key];
   if(hint)button.title=button.textContent+' · '+hint;
   return ()=>{button.disabled=!timeline.getToolState().can[key];};
 });}
 const variants={speed:[['slow','半速','0.5× speed'],['fast','倍速','2× speed'],['reverse','倒放','Reverse'],['freeze','定格','Freeze frame']],
   sound:[['denoise','降噪','Denoise'],['voice','人声均衡','Voice EQ'],['normalize','音量标准化','Normalize loudness']]};
 const variantPending=new Set();
 function variantTools(){
   const mode=elt('select');for(const [value,zh,eg] of variants[active]){const op=elt('option');op.value=value;op.textContent=t(zh,eg);mode.append(op);}
   field(t('处理方式','Processing'),mode);
   const hint=elt('small');hint.textContent=t('从片段选区生成独立素材，最长 10 秒。','Create a separate asset from a selection of up to 10 seconds.');body.append(hint);
   let pendingKey='';
   const button=control(group(),t('生成新素材','Create new asset'),async()=>{
     const c=timeline.getToolClip(),scope=getScope(),g=generation;if(!c||!scope||c.out_ms-c.in_ms>10000||variantPending.has(pendingKey))return;
     const key=pendingKey;variantPending.add(key);button.disabled=true;message(t('正在处理…','Processing…'));
     try{const result=await edit('create_clip_variant',{...scope,delivery_id:c.delivery_id,sha256:c.sha256,in_ms:c.in_ms,out_ms:c.out_ms,mode:mode.value});
       if(g!==generation)return;
       if(!await timeline.selectToolSource(result.delivery_id))throw Error(t('请刷新素材以读取结果','Refresh sources to see the result'));
       if(g===generation)choose('media',true);
     }catch(e){if(g===generation)message(e.message);}
     finally{variantPending.delete(key);if(g===generation)sync();}
   });
   return c=>{pendingKey=JSON.stringify([getScope(),c?.id]);button.disabled=!c||c.busy||c.out_ms-c.in_ms>10000||variantPending.has(pendingKey);};
 }
 const presets={
   filter:[[null,'原色','Original'],['mono','黑白','Mono'],['warm','暖调','Warm'],['cool','冷调','Cool']],
   effect:[[null,'无','None'],['vignette','暗角','Vignette'],['blur','模糊','Blur']],
   transition:[[null,'无','None'],['fade','黑场淡入','Fade from black'],['white','白场淡入','Fade from white']]
 };
 function populate(){
   body.replaceChildren();let up=[];
   if(variants[active])up.push(variantTools());
   if(active==='frame'){
     up.push(choices('rotation',[[null,'原角度','Original'],[90,'90°','90°'],[180,'180°','180°'],[270,'270°','270°']]),
       choices('mask',[[null,'无遮罩','No mask'],['circle','圆形蒙版','Circle'],['letterbox','宽银幕遮幅','Letterbox']]));
   }
   if(presets[active])up.push(choices(active,presets[active]));
   if(active==='text')up.push(editor('title','标题文字','Title text',80));
   if(active==='captions')up.push(captionTools());
   if(active==='adjust')up.push(range('brightness','亮度','Brightness',-100,100,0),range('contrast','对比度','Contrast',-100,100,0));
   if(active==='motion'){
     up.push(range('zoom','起始缩放','Start zoom',100,200,100),range('zoom_end','结束缩放','End zoom',100,200,100));
     control(group(),t('移除缩放动画','Remove zoom animation'),()=>commit({zoom:null,zoom_end:null}));
   }
   if(active==='edit'){
     up.push(...buttons([['split','在此分割','Split here'],['left','左移','Move left'],['right','右移','Move right'],['delete','移除','Remove'],['undo','撤销','Undo'],['redo','重做','Redo']]));
     const g=group();control(g,t('修剪入点与出点','Trim in and out'),()=>choose('trim',true));control(g,t('复制片段','Duplicate clip'),()=>savedAction(c=>timeline.duplicateToolClip(c.id)));
     const mirror=control(g,t('水平镜像','Mirror'),()=>savedAction(c=>timeline.setToolLook({mirror:!c.look?.mirror},c.id)));
     up.push(c=>mirror.setAttribute('aria-pressed',String(!!c?.look?.mirror)));
   }
   updateFields=c=>up.forEach(fn=>fn(c));
 }
 function sync(){
   if(!active||panel.hidden)return;
   const c=timeline.getToolClip(),signature=c?.id||'';
   if(signature!==stamp){stamp=signature;message('');generation++;loading=false;if(active==='captions')populate();}
   selection.textContent=c?((c.index+1)+' · '+c.title):t('请先将视频素材加入时间线','Add a video clip to the timeline first');
   for(const el of body.querySelectorAll('button,textarea,input,select'))el.disabled=!c||c.busy;
   updateFields(c);
   const state=timeline.getToolState();$('dtSaveState').textContent=state.saveLabel;$('dtRetry').hidden=!state.can.retry;
 }
 function choose(key,scroll=false){
   generation++;loading=false;stamp='';active=key;const chosen=tabs.find(b=>b.dataset.dtTab===key);
   if(chosen)expand(chosen.closest('.dt-rail'),true);
   if(key){
     const target=key==='trim'||chosen?.closest('#dtEditRail')?$('dmEditFields'):$('dmAddFields');
     if(panel.parentElement!==target)target.append($('daManualBack'),panel,$('dmCutSettings'));
   }
   const custom=!!key&&!['media','audio','trim'].includes(key);
   desk.toggleAttribute('data-dt-custom',custom);desk.dataset.dtView=key;
   panel.hidden=!custom;tabs.forEach(b=>b.setAttribute('aria-pressed',String(b===chosen)));
   $('dmCutSettingsTitle').textContent=key==='trim'?t('修剪片段','Trim clip'):chosen&&!custom?tabName(chosen):t('剪辑设置','Edit settings');
   if(custom){
     $('dtTitle').textContent=tabName(chosen);message('');populate();sync();
     const clip=timeline.getToolClip();
     if(clip&&!clip.busy&&$('dmCutPreview').hidden&&!variants[key])timeline.previewToolClip(clip.id,false);
   }
   if(scroll&&chosen&&matchMedia('(max-width:900px)').matches)
     (custom?panel:$('dmCutSettings')).scrollIntoView({block:'nearest'});
 }
 function expand(rail,value){
   rail.querySelector('.dt-list').hidden=!value;rail.querySelector('.dt-toggle').setAttribute('aria-expanded',String(value));
   if(!value&&active&&rail.querySelector('[data-dt-tab="'+active+'"]'))choose('');
 }
 function labels(){
   tabs.forEach(b=>{const n=tabName(b);b.querySelector('span').textContent=n;b.title=n;b.setAttribute('aria-label',n);});
   for(const rail of rails){
     const left=rail.id==='dtEditRail',toggle=rail.querySelector('.dt-toggle');
     toggle.querySelector('span').textContent=left?t('工具','Tools'):t('添加','Add');
     toggle.title=left?t('剪辑工具','Editing tools'):t('添加内容与效果','Add media and effects');
     toggle.setAttribute('aria-label',toggle.title);rail.setAttribute('aria-label',toggle.title);
   }
   $('dtClose').title=t('返回剪辑设置','Back to edit settings');$('dtClose').setAttribute('aria-label',$('dtClose').title);
   $('dtRetry').textContent=t('重试','Retry');if(active)choose(active);
 }
 $('dtRetry').onclick=()=>timeline.runToolCommand('retry');
 for(const rail of rails)rail.querySelector('.dt-toggle').onclick=()=>expand(rail,rail.querySelector('.dt-list').hidden);
 tabs.forEach(b=>b.onclick=()=>choose(active===b.dataset.dtTab?'':b.dataset.dtTab,true));
 $('dtClose').onclick=()=>{const old=tabs.find(b=>b.dataset.dtTab===active);choose('');old?.focus();};
 document.addEventListener('keydown',e=>{
   if(e.key!=='Escape'||desk.hidden)return;
   const rail=e.target.closest?.('.dt-rail')||(panel.contains(e.target)&&tabs.find(b=>b.dataset.dtTab===active)?.closest('.dt-rail'));
   if(rail){expand(rail,false);rail.querySelector('.dt-toggle').focus();}
 });
 document.addEventListener('jiusera:cut-tools-change',sync);
 new MutationObserver(labels).observe(document.documentElement,{attributes:true,attributeFilter:['lang']});
 function reset(){
   choose('');for(const rail of rails)expand(rail,matchMedia('(min-width:761px)').matches);
 }
 labels();reset();
 return {close:()=>choose(''),reset};
}
"""
