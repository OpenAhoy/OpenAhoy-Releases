"""Send a task with its current selection through the host’s current Codex chat."""

SCRIPT = r"""
function OADirectorBrief({prepare,canSend,send}){
 const t=(zh,en)=>document.documentElement.lang.toLowerCase().startsWith('en')?en:zh;
 let pending=false;
 function build(intent,instruction,ctx){
   const task={
     mv:t('用选定的歌曲制作 MV。按歌曲段落安排镜头，先用现有素材剪出一版。缺镜头时列出时间段和画面要求。',
          'Make a music video from the selected song. Arrange the shots by song section and assemble a first cut from existing footage. Identify missing shots and their time ranges.'),
     score:t('给当前视频配乐。按画面切点安排音乐入点、对白避让和结尾。优先使用已有音轨，把配乐放进这版剪辑。',
             'Score the current video. Time the music entrance, dialogue ducking and ending to the footage. Use existing audio where available and place the music in this edit.'),
     edit:t('按我的要求修改当前剪辑。','Revise the current edit as requested.')
   }[intent];
   const context={
     project_id:ctx.project_id,work_id:ctx.work_id,timeline_version:ctx.timeline_version,
     playhead_ms:ctx.playhead_ms
   };
   const pick=(obj,keys)=>Object.fromEntries(keys.filter(k=>obj[k]!==undefined&&obj[k]!==null).map(k=>[k,obj[k]]));
   if(ctx.clip)context.selected_clip=pick(ctx.clip,['id','delivery_id','sha256','title','in_ms','out_ms']);
   if(ctx.source)context.selected_video=pick(ctx.source,['delivery_id','sha256','title','duration_ms']);
   if(ctx.music)context.music=pick(ctx.music,['attempt_id','sha256','title','duration_ms','in_ms','out_ms','start_ms']);
   return [
     task,instruction&&t('我的要求','My direction')+'\n'+instruction,
     t('在 Jiusera 中用 video.director.read 的 timeline 操作核对以下作品、素材和剪辑版本。如有更新，先核对差异。修改完成后回读新版，并说明改动的时间段。',
       'In Jiusera, use the timeline action of video.director.read to verify the work, assets and timeline version below. If the version has changed, reconcile the difference first. Read back the revised edit and report the affected time ranges.'),
     JSON.stringify(context),
     t('需要付费生成新素材时，沿用当前对话已有的费用授权。','For paid generation, use the spending authorization already established in this chat.')
   ].filter(Boolean).join('\n\n');
 }
 async function submit({intent,instruction='',song}={}){
   const useChat=()=>({state:'unavailable',message:t('请在当前 Codex 对话里说出剪辑要求。','Describe the edit in the current Codex chat.')});
   if(!canSend())return useChat();
   if(pending)return {state:'busy',message:t('正在交接剪辑指令。','Preparing the editing brief.')};
   if(!['mv','score','edit'].includes(intent)||typeof instruction!=='string'||
      (intent==='edit'&&!instruction.trim()))return {state:'blocked',message:t('请写下要修改的内容。','Describe the change you want.')};
   pending=true;
   const unavailable=()=>({state:'blocked',message:t('请核对当前作品与保存状态，再提交指令。','Check the current work and its save status, then try again.')});
   try{
     const ctx=await prepare({intent,instruction,song});
     if(!ctx?.isCurrent?.()||!ctx.project_id||!ctx.work_id||!Number.isSafeInteger(ctx.timeline_version)||
        ctx.timeline_version<0||!Number.isSafeInteger(ctx.playhead_ms)||ctx.playhead_ms<0)return unavailable();
     if(intent==='mv'&&(!ctx.music?.attempt_id||!ctx.music.sha256))return {state:'blocked',message:t('先选一首歌曲。','Choose a song first.')};
     if(intent==='score'&&!ctx.clip?.delivery_id&&!ctx.source?.delivery_id)return {state:'blocked',message:t('先选一个视频。','Choose a video first.')};
     if(song&&((typeof song==='string'?song:song.attempt_id)!==ctx.music?.attempt_id||
        (song.sha256&&song.sha256!==ctx.music?.sha256)))return unavailable();
     const text=build(intent,instruction.trim(),ctx);
     if(!ctx.isCurrent())return unavailable();
     if(!canSend())return useChat();
     try{
       const receipt=await send(text);
       if(!receipt||typeof receipt!=='object'||Array.isArray(receipt)||
          (receipt.isError!==undefined&&receipt.isError!==false))throw Error('HOST_MESSAGE_NOT_CONFIRMED');
     }
     catch(_){return {state:'unconfirmed',message:t('发送结果未确认，请查看当前 Codex 对话。','Delivery is unconfirmed. Check the current Codex chat.')};}
     return {state:'sent',message:t('已交给当前 Codex 对话。','Sent to the current Codex chat.')};
   }catch(_){return unavailable();}
   finally{pending=false;}
 }
 return {submit};
}
"""
