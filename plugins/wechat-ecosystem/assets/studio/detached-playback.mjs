import { mediaResponse, studioAction } from "./bridge.mjs";

// The folded work borrows the Studio clock. Its audio never enters the song draft.
export function detachedPlayback(studio, signal) {
  let cache, prepared, sourceBus, scoreBus, signature = "", stopped = false;
  const nodes = new Map();
  function snapshot() {
    if (studio.imw?.enabled()) return null;
    const scope = studio.detachedTracks?.scope();
    if (!scope) return null;
    const data = globalThis.OAIMWVideo?.detachedAudio?.();
    return data?.project === scope.project && data.work === scope.work && data.rows?.length ? data : null;
  }
  function key(data) {
    return data ? JSON.stringify([data.project,data.work,studio.song?.id,studio.version?.id]) : "";
  }
  function mixKey(data) {
    return data ? JSON.stringify([key(data),data.offsetSeconds,data.rows.map(r=>[r.id,r.sha256,r.start_ms,r.in_ms,r.out_ms,r.volume])]) : "";
  }
  function stopNodes() {
    for (const [node,gain] of nodes) {node.onended = null; try {node.stop();} catch {} node.disconnect();gain.disconnect();}
    nodes.clear();
  }
  function reset() {
    cache?.controller.abort();cache = null;prepared = null;signature = "";
    stopNodes();
  }
  function close() {
    reset(); sourceBus?.disconnect(); scoreBus?.disconnect();sourceBus = scoreBus = null;
  }
  function connect(ctx, master) {
    sourceBus = ctx.createGain();
    scoreBus = ctx.createGain();
    scoreBus.gain.value = studio.version?.previewGain ?? 1;
    sourceBus.connect(master);scoreBus.connect(master);
    return scoreBus;
  }
  function levels() {
    if (!sourceBus || !scoreBus) return;
    const data = snapshot(), hasSolo = !!studio.soloTrack ||
      !!studio.version?.tracks.some(row=>studio.trackMonitorState(row.id).solo);
    const source = !!data && data.sourceAudible !== false && (!hasSolo || !!data.sourceSolo);
    const score = data?.scoreAudible !== false;
    const now = sourceBus.context.currentTime;
    sourceBus.gain.setTargetAtTime(Number(source),now,.001);
    scoreBus.gain.setTargetAtTime(Number(score) * (studio.version?.previewGain ?? 1),now,.001);
  }
  async function load() {
    const data = snapshot(), ctx = studio.context;
    if (!data || !ctx) {reset();levels();return;}
    const identity = key(data);
    if (cache?.key !== identity || cache.context !== ctx) {
      reset();
      cache = {key:identity,context:ctx,controller:new AbortController(),buffers:new Map()};
    }
    const owner = cache, abort = owner.controller.signal, shape = mixKey(data);
    signature = shape;
    const inputs = data.rows.filter(row=>row.volume > 0).map(row=>({
      row,sha:row.sha256,read:offset=>globalThis.OAIMWVideo.detachedChunk(row.id,offset)
    }));
    if (studio.version.mastered && studio.version.masterAudioSha) {
      const version = studio.version;
      const args = {action:"media",project:data.project,song:studio.song.id,version:version.id,asset:"wav"};
      inputs.push({master:true,sha:version.masterAudioSha,read:offset=>studioAction({...args,offset})});
    }
    const used = new Set(inputs.map(item=>item.sha));
    for (const hash of owner.buffers.keys()) if (!used.has(hash)) owner.buffers.delete(hash);
    const voices = [];
    // Sequential reads also keep the local MCP channel responsive for edits.
    for (const input of inputs) {
      if (cache !== owner || signature !== shape || abort.aborted) return;
      let entry = owner.buffers.get(input.sha);
      if (!entry) {
        entry = (async () => {
          const response = await mediaResponse(input.read,abort,input.sha);
          if (!response.ok) throw Error("无法读取分离音频");
          const bytes = await response.arrayBuffer();
          abort.throwIfAborted();
          return ctx.decodeAudioData(bytes);
        })();
        owner.buffers.set(input.sha,entry);
      }
      let buffer;
      try {buffer = await entry;}
      catch (error) {
        if (owner.buffers.get(input.sha) === entry) owner.buffers.delete(input.sha);
        if (cache !== owner || signature !== shape || abort.aborted) return;
        throw error;
      }
      voices.push({...input,buffer});
    }
    if (cache === owner && signature === shape && mixKey(snapshot()) === shape) {
      prepared = {voices,offset:data.offsetSeconds || 0,shape};
      levels();
    }
  }
  async function prepare(signal) {
    // A fold, trim or song change can finish while a media chunk is in flight.
    signal.addEventListener("abort",reset,{once:true});
    try {
      do {
        signal.throwIfAborted();
        await load();
        signal.throwIfAborted();
      } while (snapshot() && prepared?.shape !== mixKey(snapshot()));
    } finally {
      signal.removeEventListener("abort",reset);
    }
  }
  function schedule(from,to,at) {
    if (!prepared) return;
    for (const {row,master,buffer} of prepared.voices) {
      const start = master ? 0 : row.start_ms / 1000 - prepared.offset;
      const source = master ? 0 : row.in_ms / 1000;
      const end = start + (master ? buffer.duration : (row.out_ms-row.in_ms)/1000);
      const head = Math.max(from,start), offset = source + head-start;
      const duration = Math.min(to-head,end-head,buffer.duration-offset);
      if (duration<=0) continue;
      const node = studio.context.createBufferSource(), gain = studio.context.createGain();
      node.buffer = buffer;gain.gain.value = master ? 1 : row.volume/100;
      node.connect(gain);gain.connect(master ? scoreBus : sourceBus);
      nodes.set(node,gain);
      node.onended = () => {nodes.delete(node);node.disconnect();gain.disconnect();};
      node.start(at+head-from,offset,duration);
    }
  }
  function changed() {
    const data=snapshot();
    levels();
    if (signature === mixKey(data)) return;
    const wasPlaying=studio.playing && !studio.imw.enabled();
    if (wasPlaying) studio.stopAndRemember();
    if (!data) reset();
    else {prepared=null;signature=mixKey(data);}
    studio.transport.sync();
    if (wasPlaying && !stopped) void studio.toggle();
  }
  document.addEventListener("jiusera:detached-audio-change",changed,{signal});
  signal.addEventListener("abort",()=>{stopped=true;close();},{once:true});
  return {available:()=>!!snapshot(),programOutput:()=>scoreBus,connect,prepare,schedule,levels,stopNodes,close};
}
