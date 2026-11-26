// The host supplies studioAction. One AudioContext owns the transport, metronome and monitor gain.
const MAX_CHUNK = 32768;
const READ_AHEAD = .72;

function decode(context, packet, expected, frames, rate) {
  if (packet.encoding !== "f32le" || packet.channels !== 2 || packet.sampleRate !== rate ||
      packet.start !== expected || packet.frames !== frames || typeof packet.bytes !== "string" ||
      packet.bytes.length !== 4 * Math.ceil(frames * 8 / 3)) throw Error("studio_monitor_invalid");
  const binary = atob(packet.bytes);
  if (binary.length !== frames * 8) throw Error("studio_monitor_invalid");
  const bytes = new Uint8Array(binary.length);
  for (let i = 0; i < bytes.length; i++) bytes[i] = binary.charCodeAt(i);
  const data = new DataView(bytes.buffer);
  const buffer = context.createBuffer(2, frames, rate);
  for (let ch = 0; ch < 2; ch++) {
    const samples = buffer.getChannelData(ch);
    for (let i = 0; i < frames; i++) samples[i] = data.getFloat32((i * 2 + ch) * 4, true);
  }
  return buffer;
}

export class BusMonitor {
  constructor(call) { this.call = call; }

  stop() {
    const run = this.run;
    if (!run) return;
    this.run = null;
    clearTimeout(run.timer);
    for (const node of run.nodes) {
      node.onended = null;
      node.stop();
      node.disconnect();
    }
    run.nodes.clear();
    if (run.token) this.release(run.scope, run.token);
  }

  setBypass(bypass) {
    if (!this.run || this.run.bypass === bypass) return;
    this.run.bypass = bypass;
    this.run.loopBlocks?.clear();
  }

  release(scope, stream) {
    // Idle timeout and connection EOF also retire the child if the frame is already gone.
    void this.call({ action: "monitor_close", ...scope, stream }).catch(() => {});
  }

  async start({ context, destination, scope, profile, bypass, from, end = profile.frames,
                loop = null, onStart, onBlock, onEnd, onError }) {
    this.stop();
    const rate = profile.sampleRate, analysis = profile.analysis;
    const chunkSize = Math.min(MAX_CHUNK, Math.round(rate / 3));
    if (!Number.isSafeInteger(from) || !Number.isSafeInteger(end) ||
        from < 0 || from >= end || end > profile.frames ||
        (loop !== null && (!Number.isSafeInteger(loop) || loop < 0 || loop > from || end - loop < rate / 4))) {
      throw Error("studio_monitor_range");
    }
    const run = { scope: { ...scope }, nodes: new Set(), cursor: from, firstTime: null, emitted: 0, bypass };
    // Keep short loops in a bounded Web Audio buffer cache. Deep exact seeks replay the prefix only once.
    if (loop !== null && end - loop <= 1024 * 1024) run.loopBlocks = new Map();
    this.run = run;
    const active = () => this.run === run;
    const clock = () => run.firstTime + run.emitted / rate;
    const finish = error => {
      if (!active()) return;
      this.stop();
      if (error) onError?.(error);
      else onEnd?.();
    };
    const open = async () => {
      const desired = run.bypass;
      const reply = await this.call({ action: "monitor_open", ...scope, analysis, frame: run.cursor, bypass: desired });
      if (!active()) { this.release(scope, reply.stream); return false; }
      run.token = reply.stream;
      if (reply.start !== run.cursor || reply.sampleRate !== rate || reply.frames !== profile.frames ||
          reply.bypass !== desired) throw Error("studio_monitor_invalid");
      return true;
    };
    const next = async () => {
      if (!active()) return;
      const start = run.cursor;
      const n = Math.min(chunkSize, end - start);
      let buffer = run.token ? null : run.loopBlocks?.get(start);
      if (!buffer) {
        if (!run.token && !await open()) return;
        const desired = run.bypass;
        const packet = await this.call({ action: "monitor_read", ...scope, analysis, stream: run.token,
                                         frame: start, frames: n, bypass: desired });
        if (!active()) return;
        if (packet.bypass !== desired || packet.eof !== (start + n === profile.frames)) throw Error("studio_monitor_invalid");
        buffer = decode(context, packet, start, n, rate);
        if (run.loopBlocks && desired === run.bypass && start >= loop && (start - loop) % chunkSize === 0)
          run.loopBlocks.set(start, buffer);
      }
      if (run.firstTime === null) run.firstTime = context.currentTime + .06;
      const at = clock();
      if (at < context.currentTime) throw Error("studio_monitor_underrun");
      const node = context.createBufferSource();
      node.buffer = buffer;
      node.connect(destination);
      run.nodes.add(node);
      node.onended = () => { node.disconnect(); run.nodes.delete(node); };
      node.start(at);
      // The transport's existing click track follows these same block boundaries.
      onBlock?.({ from: start / rate, to: (start + n) / rate, at });
      if (run.emitted === 0) onStart?.({ at, from: start / rate });
      run.emitted += n;
      run.cursor += n;
      if (run.cursor === end) {
        if (run.token) {
          this.release(scope, run.token);
          run.token = null;
        }
        if (loop === null) {
          // AudioContext time can pause independently of wall time and rAF.
          const ended = node.onended;
          node.onended = () => { ended(); finish(); };
          return;
        }
        run.cursor = loop;
      }
      const ahead = clock() - context.currentTime;
      // Pause acquisition while the prior blocks are ahead of the device clock.
      const pump = () => {
        if (!active()) return;
        const wait = clock() - context.currentTime - READ_AHEAD;
        if (wait > .02) run.timer = setTimeout(pump, Math.min(wait, .4) * 1000);
        else void next().catch(finish);
      };
      if (ahead < READ_AHEAD) void next().catch(finish);
      else run.timer = setTimeout(pump, 20);
    };
    try { await next(); }
    catch (error) { finish(error); }
  }
}
