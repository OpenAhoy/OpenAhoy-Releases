"""Subtitle interchange for the director timeline. Times in the editor are integer milliseconds."""

SCRIPT = r'''
const OADirectorCaptions=(()=>{
 const maxText=200,maxCues=128;
 function error(zh,en){throw Error(typeof document!=='undefined'&&document.documentElement.lang.startsWith('en')?en:zh);}
 const failText=()=>error('每条字幕须为 1–200 字，不能包含控制字符','Each cue needs 1–200 characters without control codes');
 function text(value){
   const v=value.trim();
   if(!v||[...v].length>maxText||/[\x00-\x09\x0b-\x1f\x7f]/.test(v))failText();
   return v;
 }
 function time(value){
   const m=/^(\d{2,}):([0-5]\d):([0-5]\d)[,.](\d{3})$/.exec(value);
   if(!m)error('字幕时间应为 时:分:秒,毫秒','Use HH:MM:SS,mmm subtitle times');
   const ms=((Number(m[1])*60+Number(m[2]))*60+Number(m[3]))*1000+Number(m[4]);
   if(!Number.isSafeInteger(ms))error('字幕时间超出范围','Subtitle time is out of range');
   return ms;
 }
 function srt(value){
   return value.split(/\n[ \t]*\n+/).map((block,i)=>{
     const lines=block.trim().split('\n');
     if(/^\d+$/.test(lines[0].trim()))lines.shift();
     const match=/^(\S+)\s+-->\s+(\S+)\s*$/.exec((lines.shift()||'').trim());
     if(!match)error('第 '+(i+1)+' 段缺少有效 SRT 时间码','Invalid SRT timing in cue '+(i+1));
     return {in_ms:time(match[1]),out_ms:time(match[2]),text:text(lines.join('\n'))};
   });
 }
 function lrc(value,length){
   const rows=[];let offset=0,offsetSeen=false;
   for(const [index,line] of value.split('\n').entries()){
     const v=line.trim();
     if(!v)continue;
     const shift=/^\[offset:([+-]?\d+)\]$/i.exec(v);
     if(shift){if(offsetSeen)error('歌词只能有一个 offset','Only one LRC offset is supported');offset=Number(shift[1]);offsetSeen=true;continue;}
     if(/^\[(?:ar|al|ti|au|by|re|ve|length|tool|language):[^\]]*\]$/i.test(v))continue;
     const times=[];let rest=v,m;
     while((m=/^\[(\d+):([0-5]\d)(?:[.:](\d{1,3}))?\]/.exec(rest))){
       times.push((Number(m[1])*60+Number(m[2]))*1000+Number((m[3]||'').padEnd(3,'0')));
       rest=rest.slice(m[0].length);
     }
     if(!times.length||/<\d+:\d+/.test(rest))error('第 '+(index+1)+' 行需要逐句 LRC 时间码','Expected line-timed LRC at line '+(index+1));
     for(const ms of times)rows.push({ms,lyric:rest.trim()});
   }
   rows.sort((a,b)=>a.ms-b.ms);
   const cues=[];
   for(let i=0;i<rows.length;i++){
     const r=rows[i],start=r.ms-offset,stop=i+1<rows.length?rows[i+1].ms-offset:length;
     if(i&&r.ms===rows[i-1].ms)error('相同时间存在多行歌词，请合并','Combine lyrics sharing a timestamp');
     if(r.lyric&&stop>0)cues.push({in_ms:Math.max(0,start),out_ms:stop,text:text(r.lyric)});
   }
   return cues;
 }
 function ranges(clips){
   let end=0;
   return clips.map(c=>{
     const start=end;end+=c.out_ms-c.in_ms;
     return {c,start,end};
   });
 }
 function validate(cues,total){
   if(!cues.length)error('没有可用的字幕','No timed cues found');
   let last=0;
   for(const q of cues){
     if(!Number.isSafeInteger(q.in_ms)||!Number.isSafeInteger(q.out_ms)||q.in_ms<last||q.out_ms<=q.in_ms||q.out_ms>total)
       error('字幕必须按时间排序、互不重叠，并落在视频时间线内','Cues must be ordered, distinct and inside the video timeline');
     last=q.out_ms;
   }
 }
 function assignments(cues,clips){
   let first=0;
   return ranges(clips).map(({c,start,end})=>{
     while(first<cues.length&&cues[first].out_ms<=start)first++;
     const mapped=[];
     for(let i=first;i<cues.length&&cues[i].in_ms<end;i++){
       const q=cues[i];
       mapped.push({in_ms:c.in_ms+Math.max(start,q.in_ms)-start,out_ms:c.in_ms+Math.min(end,q.out_ms)-start,text:q.text});
     }
     if(mapped.length>maxCues)error('单个片段超过 128 条字幕','A clip can contain up to 128 subtitle cues');
     return {id:c.id,cues:mapped};
   });
 }
 function parse(raw,clips){
   if(!clips.length)error('请先加入视频片段','Add a video clip first');
   if(typeof raw!=='string'||raw.length>1048576)error('字幕文件最大 1 MiB','Subtitle file limit is 1 MiB');
   const v=raw.replace(/^\uFEFF/,'').replace(/\r\n?/g,'\n').trim();
   const total=clips.reduce((sum,c)=>sum+c.out_ms-c.in_ms,0);
   const cues=v.includes('-->')?srt(v):lrc(v,total);
   validate(cues,total);
   return {cues,assignments:assignments(cues,clips)};
 }
 function existing(clips){
   const list=[];
   for(const {c,start} of ranges(clips)){
     const items=c.look?.cues?.length?c.look.cues:c.look?.caption?[{in_ms:c.in_ms,out_ms:c.out_ms,text:c.look.caption}]:[];
     for(const q of items){
       const left=Math.max(q.in_ms,c.in_ms),right=Math.min(q.out_ms,c.out_ms);
       if(right<=left)continue;
       const item={in_ms:start+left-c.in_ms,out_ms:start+right-c.in_ms,text:q.text},previous=list[list.length-1];
       if(previous&&previous.out_ms===item.in_ms&&previous.text===item.text)previous.out_ms=item.out_ms;
       else list.push(item);
     }
   }
   return list;
 }
 function correctLine(timeline,clips,line,value){
   const updated=text(value),changes=[];
   if(updated===line.text)return;
   for(const {c,start,end} of ranges(clips)){
     if(start>=line.out_ms||end<=line.in_ms)continue;
     const cues=c.look?.cues?.length?c.look.cues:c.look?.caption?[{in_ms:c.in_ms,out_ms:c.out_ms,text:c.look.caption}]:[];
     const corrected=cues.map(cue=>{
       const left=start+Math.max(cue.in_ms,c.in_ms)-c.in_ms,right=start+Math.min(cue.out_ms,c.out_ms)-c.in_ms;
       return right>left&&left>=line.in_ms&&right<=line.out_ms&&cue.text===line.text?{...cue,text:updated}:cue;
     });
     if(corrected.some((cue,i)=>cue!==cues[i]))changes.push({id:c.id,cues:corrected});
   }
   if(!changes.length)error('这行字幕已变化，请重新选择','This line has changed. Select it again.');
   commit(timeline,changes,clips);
 }
 function stamp(ms){
   const pad=n=>String(n).padStart(2,'0');
   return pad(Math.floor(ms/3600000))+':'+pad(Math.floor(ms/60000)%60)+':'+pad(Math.floor(ms/1000)%60)+','+String(ms%1000).padStart(3,'0');
 }
 function encode(cues){return cues.map((c,i)=>(i+1)+'\n'+stamp(c.in_ms)+' --> '+stamp(c.out_ms)+'\n'+c.text).join('\n\n')+(cues.length?'\n':'');}
 function toSRT(clips){return encode(existing(clips));}
 function download(clips){
   const data=toSRT(clips);
   if(!data)error('时间线上还没有字幕','No subtitles on the timeline');
   const a=document.createElement('a'),url=URL.createObjectURL(new Blob(['\uFEFF',data],{type:'application/x-subrip;charset=utf-8'}));
   a.href=url;a.download='Jiusera.srt';document.body.append(a);a.click();a.remove();
   setTimeout(()=>URL.revokeObjectURL(url),30000);return true;
 }
 function commit(timeline,rows,old){
   if(!timeline.setToolCaptions(rows,old))error('时间线已变更，请重新核对字幕','Timeline changed. Review subtitles again');
 }
 function importText(raw,timeline){
   const clips=timeline.getToolClips(),result=parse(raw,clips);commit(timeline,result.assignments,clips);return result.cues.length;
 }
 function transcriptCues(receipt,start){
   if(!Number.isSafeInteger(start)||start<0||!receipt||!['ready','empty'].includes(receipt.state)||!Array.isArray(receipt.cues))
     error('识别结果无效','Invalid transcription result');
   if(receipt.cues.length)validate(receipt.cues,receipt.end_ms);
   if(receipt.cues.some(q=>q.in_ms<receipt.start_ms))error('字幕超出识别选区','Cue exceeds transcription range');
   const delta=start-receipt.start_ms;
   return receipt.cues.map(q=>({in_ms:q.in_ms+delta,out_ms:q.out_ms+delta,text:text(q.text)}));
 }
 function transcriptSRT(receipt,start){return encode(transcriptCues(receipt,start));}
 function importTranscript(receipt,start,timeline,clips){
   const recognized=transcriptCues(receipt,start);
   if(!recognized.length)error('未识别到语音','No speech detected');
   const end=start+receipt.end_ms-receipt.start_ms,span=ranges(clips),total=span.at(-1)?.end||0;
   validate(recognized,total);
   const mapped=assignments(recognized,clips),updates=[];
   for(let i=0;i<span.length;i++){
     const r=span[i],c=r.c;
     if(r.start>=end||r.end<=start)continue;
     const left=c.in_ms+Math.max(0,start-r.start),right=c.in_ms+Math.min(r.end,end)-r.start;
     const source=c.look?.cues?.length?c.look.cues:c.look?.caption?[{in_ms:c.in_ms,out_ms:c.out_ms,text:c.look.caption}]:[];
     const kept=[];
     for(const q of source){
       if(q.out_ms<=left||q.in_ms>=right)kept.push(q);
       else{
         if(q.in_ms<left)kept.push({...q,out_ms:left});
         if(q.out_ms>right)kept.push({...q,in_ms:right});
       }
     }
     const cues=kept.concat(mapped[i].cues).sort((a,b)=>a.in_ms-b.in_ms);
     if(cues.length>maxCues)error('单个片段超过 128 条字幕','A clip can contain up to 128 subtitle cues');
     updates.push({id:c.id,cues});
   }
   commit(timeline,updates,clips);return recognized.length;
 }
 return {parse,toSRT,download,importText,transcriptSRT,importTranscript,existing,correctLine};
})();
'''
