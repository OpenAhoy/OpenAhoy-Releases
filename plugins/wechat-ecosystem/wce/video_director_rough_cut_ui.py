"""Arrange registered video against the measured peak envelope of a music selection."""
SCRIPT = r"""
function OADirectorRoughCut({getState,getScope,waves,uid,apply,notify,english}){
 const msg=(zh,en)=>english()?en:zh;
 const minClip=34; // At least one whole output frame at 30 fps for any timeline offset.
 let pending=null;
 function sources(state){
   const seen=new Set(),result=[];
   for(const row of state?.sources||[]){
     if(state.exportIds?.has(row.delivery_id)||seen.has(row.sha256)||row.duration_ms<minClip)continue;
     seen.add(row.sha256);result.push(row);
   }
   return result;
 }
 function getRoughCutState(){
   const state=getState(),songs=state?.songs||[],sourceCount=sources(state).length;
   const busy=!!pending&&pending===getScope();
   return {ready:!!(state?.loaded&&!state.busy&&!state.conflict&&!busy&&sourceCount&&songs.length),busy,
     songs:songs.map(({attempt_id,title,sha256,duration_ms})=>({attempt_id,title,sha256,duration_ms})),
     songId:state?.doc.music?.attempt_id||'',sourceCount,clipCount:state?.doc.clips.length||0};
 }
 async function accents(scope,music,end,valid){
   const events=[];let prior=0,previousRise=0,previousMs=0;
   // About 40 ms per envelope sample keeps transient placement useful on longer songs.
   for(let start=music.in_ms;start<end;start+=20000){
     const stop=Math.min(end,start+20000);
     const part=await waves.request({...scope,sha256:music.sha256,attempt_id:music.attempt_id,
       start_ms:start,end_ms:stop,bins:Math.max(1,Math.ceil((stop-start)/40))},valid);
     if(!valid())throw Error(msg('剪辑或作品已变更，请重新粗剪','The edit or work changed. Start the rough cut again.'));
     if(part.state==='no_audio')throw Error(msg('此歌曲没有可读音轨','This song has no readable audio track'));
     const step=part.samples_per_bin*1000/part.sample_rate;
     for(const [i,level] of part.peaks.entries()){
       const rise=level-prior,ms=music.start_ms+Math.round(start+i*step)-music.in_ms;
       if(previousRise>=6&&rise<previousRise)events.push({ms:previousMs,strength:previousRise});
       prior=level;previousRise=rise;previousMs=ms;
     }
   }
   return events;
 }
 function arrange(rows,length,events){
   const pool=rows.map(row=>({row,offset:0})),clips=[];
   const desired=Math.min(256,Math.max(1,Math.round(length/3000),pool.length>1&&length>=2000?2:1));
   const spacing=length/desired;
   let pos=0,index=0,accentCuts=0,eventIndex=0;
   while(pool.length&&length-pos>=minClip&&clips.length<256){
     const source=pool[index],available=source.row.duration_ms-source.offset,remaining=length-pos;
     const limit=Math.min(available,remaining);
     const goal=Math.min(limit,Math.round(spacing));
     let take=limit,accent=false;
     if(pool.length>1&&remaining>spacing*1.25&&available>=minClip*2){
       const radius=Math.min(700,Math.round(spacing*.25));
       const earliest=pos+Math.max(minClip,goal-radius),latest=pos+Math.min(limit,goal+radius);
       while(eventIndex<events.length&&events[eventIndex].ms<earliest)eventIndex++;
       let score=0;take=goal;
       for(let k=eventIndex;k<events.length&&events[k].ms<=latest;k++){
         const e=events[k],offset=e.ms-pos;
         const weight=e.strength*(1-.45*Math.abs(offset-goal)/Math.max(1,radius));
         if(weight>score){score=weight;take=offset;accent=true;}
       }
     }
     if(remaining-take<minClip&&remaining<=available){accent=accent&&take===remaining;take=remaining;}
     if(available-take<minClip&&available<=remaining){accent=accent&&take===available;take=available;}
     if(take<minClip)break;
     clips.push({delivery_id:source.row.delivery_id,sha256:source.row.sha256,in_ms:source.offset,
       out_ms:source.offset+take,volume:0});
     source.offset+=take;pos+=take;
     if(pos<length&&accent)accentCuts++;
     if(source.row.duration_ms-source.offset<minClip)pool.splice(index,1);else index++;
     if(index>=pool.length)index=0;
   }
   return {clips,durationMs:pos,accentCuts};
 }
 async function applyMusicRoughCut(attemptId){
   const state=getState(),scope=getScope();
   const view=getRoughCutState();
   if(!view.ready)throw Error(msg('请准备好可用的视频和歌曲后再粗剪','Add a video and a song before making a rough cut'));
   const song=state.songs.find(row=>row.attempt_id===(attemptId||view.songId));
   if(!song)throw Error(msg('请选择一首歌曲','Choose a song'));
   const previous=state.doc.music;
   const music=previous?.attempt_id===song.attempt_id&&previous.sha256===song.sha256?{...previous}:
     {attempt_id:song.attempt_id,sha256:song.sha256,in_ms:0,start_ms:0,volume:100};
   const rows=sources(state),songEnd=music.out_ms??song.duration_ms;
   const requestedDurationMs=music.start_ms+songEnd-music.in_ms;
   const length=Math.min(requestedDurationMs,rows.reduce((ms,row)=>ms+row.duration_ms,0));
   if(length-music.start_ms<minClip)throw Error(msg('配乐起点超出可用画面，请调整起点或补充素材','Move the music start earlier or add more footage'));
   const snapshot=JSON.stringify(state.doc),fingerprint=JSON.stringify(rows.map(r=>[r.delivery_id,r.sha256,r.duration_ms]));
   const valid=()=>getScope()===scope&&getState()===state&&!state.busy&&!state.conflict&&JSON.stringify(state.doc)===snapshot;
   pending=scope;notify();
   try{
     // A single uninterrupted shot, or a sub-two-second assembly, has no movable cut.
     const events=rows.length>1&&length>=2000?
       await accents(scope,music,music.in_ms+length-music.start_ms,valid):[];
     if(!valid()||JSON.stringify(sources(state).map(r=>[r.delivery_id,r.sha256,r.duration_ms]))!==fingerprint||
        !state.songs.some(x=>x.attempt_id===song.attempt_id&&x.sha256===song.sha256&&x.duration_ms===song.duration_ms))
       throw Error(msg('素材或剪辑已变更，请重新粗剪','Sources or edit changed. Start the rough cut again.'));
     const plan=arrange(rows,length,events);
     if(!plan.clips.length||plan.durationMs<=music.start_ms)throw Error(msg('有效画面不足，无法对齐这段音乐','Too little usable footage for this music section'));
     const unchanged=JSON.stringify(previous)===JSON.stringify(music)&&state.doc.clips.length===plan.clips.length&&
       plan.clips.every((c,i)=>{const old=state.doc.clips[i];return !old.look&&Object.keys(c).every(k=>old[k]===c[k]);});
     if(!unchanged)apply({music,clips:plan.clips.map(c=>({...c,id:uid()}))});
     return {clipCount:plan.clips.length,durationMs:plan.durationMs,requestedDurationMs,accentCuts:plan.accentCuts,unchanged};
   }finally{if(pending===scope)pending=null;notify();}
 }
 return {getRoughCutState,applyMusicRoughCut};
}
"""
