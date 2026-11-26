import { studioAction } from "./bridge.mjs";
import { BusMonitor } from "./live-monitor.mjs";

export function audibleState(studio) {
  const d = studio.draft;
  return JSON.stringify([d.offsets, d.trims, d.padding, d.splits, d.trackMix, d.masterGain]);
}

// Return true only when this transport owns audio. The caller then skips its lane scheduler.
export function playStudioBus(studio) {
  const profile = studio.masterAnalysis;
  if (!profile) return false;
  const rate = profile.sampleRate;
  let from = Math.round(studio.seconds * rate);
  const end = studio.loopEnabled ? Math.min(profile.frames, Math.round(studio.loop.end * rate)) : profile.frames;
  const loop = studio.loopEnabled ? Math.round(studio.loop.start * rate) : null;
  if (loop !== null && (end - loop < rate / 4 || from < loop)) {
    studio.status("循环区间超出已分析的节目范围。");
    return true;
  }
  if (from >= end) {
    from = loop ?? 0;
    studio.seconds = from / rate;
  }
  const monitor = studio.liveMonitor ||= new BusMonitor(studioAction);
  studio.playing = true;
  studio.busPending = true;
  studio.transport.sync();
  void monitor.start({ context: studio.context, destination: studio.monitorGains.native, scope: profile.scope,
    profile, from, end, loop, bypass: !!studio.busBypass,
    onStart({ at, from }) {
      studio.busPending = false;
      studio.clock = at - from;
      const tick = () => {
        if (!studio.playing || !monitor.run) return;
        studio.seconds = studio.context.currentTime < at ? from : studio.clockPosition();
        studio.sampleOutput(studio.context.currentTime);
        studio.position();
        studio.animation = requestAnimationFrame(tick);
      };
      tick();
    },
    onBlock(window) { studio.monitorBlock(window); },
    onEnd() {
      studio.stop();
      studio.seconds = end / rate;
      studio.position();
      studio.changed();
    },
    onError(error) {
      studio.stopAndRemember();
      studio.status(error.message === "analysis_changed"
        ? "分轨已变化，请重新分析。" : "总线监听中断，请从当前位置重试。");
    },
  }).catch(() => { studio.stop(); studio.status("无法启动 Stereo Out 监听。"); });
  return true;
}
