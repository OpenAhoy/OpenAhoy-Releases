import stylesheet from "./transport-shadow.css";
const icons = {
  begin: '<path d="M4 5v14m15-13-10 6 10 6z"/>',
  end: '<path d="M20 5v14M5 6l10 6-10 6z"/>',
  back: '<path d="m13 6-8 6 8 6m6-12-8 6 8 6"/>',
  forward: '<path d="m5 6 8 6-8 6m6-12 8 6-8 6"/>',
  play: '<path d="M8 5v14l11-7z" fill="currentColor" stroke="none"/>',
  pause: '<path d="M9 5v14m6-14v14" stroke-width="3"/>',
  stop: '<rect x="6" y="6" width="12" height="12" rx="2" fill="currentColor" stroke="none"/>',
  loop: '<path d="M20 8h-13a3 3 0 0 0-3 3m16-3-3-3m3 3-3 3m-13 5h13a3 3 0 0 0 3-3m-16 3 3 3m-3-3 3-3"/>',
  metronome: '<path d="M9 4h6l4 15H5L9 4Zm3 12 7-11M9 19h6"/>',
  more: '<path d="M5 12h.01M12 12h.01M19 12h.01" stroke-width="3"/>',
  volume: '<path d="M4 9v6h4l5 4V5L8 9H4Zm12 0a4 4 0 0 1 0 6m2-8a7 7 0 0 1 0 10"/>',
  range: '<path d="M9 5H5v14h4m6-14h4v14h-4M9 12h6"/>',
};

function icon(key) {
  return '<svg viewBox="0 0 24 24" aria-hidden="true" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">' + icons[key] + "</svg>";
}
const button = (id, key, label, attributes = "") =>
  '<button id="' + id + '" type="button" aria-label="' + label + '" title="' + label + '" ' + attributes + '>' + icon(key) + '</button>';

function createDockTransport() {
  const nav = document.querySelector(".wb-dock");
  const entries = nav.querySelector(".wb-dock-entries");
  const home = entries.querySelector('.wb-lunify-entry > [data-wb-route="l-unify-home"]');
  const entry = home ?? entries.querySelector('[data-wb-route="l-unify"]');
  const anchor = home?.closest(".wb-lunify-entry") ?? entry;
  const transport = document.createElement("lus-transport");
  transport.setAttribute("role", "group");
  transport.hidden = true;
  const root = transport.attachShadow({ mode: "open" });
  root.innerHTML = `<style>${stylesheet}</style>
    <div class="controls">
      <div id="shuttle" class="cluster" role="group" aria-label="定位">
        ${button("reset", "begin", "回到开头")}
        ${button("prev", "back", "上一个片段边界", 'class="studio-only"')}
        ${button("next", "forward", "下一个片段边界", 'class="studio-only"')}
        ${button("finish", "end", "到结尾")}
      </div>
      <div class="cluster playback" role="group" aria-label="播放与停止">
        ${button("play", "play", "播放", "disabled")}
        ${button("stop", "stop", "停止", "disabled")}
      </div>
      <div class="readout">
        <output id="time" aria-label="播放位置" aria-live="off">00:00.0</output>
        <div id="output-meter" class="studio-only" role="meter" aria-label="主输出峰值" aria-valuemin="-60" aria-valuemax="0"
             aria-valuenow="-60" aria-valuetext="静音" title="主输出峰值（dBFS）"><i></i></div>
        <span id="video-meter-note" hidden title="视频预览暂无主输出电平" aria-label="视频预览暂无主输出电平">—</span>
        <input id="song-seek" class="songs-only" type="range" min="0" max="1" step="0.01" value="0" aria-label="歌曲播放位置" disabled>
        <output id="song-duration" class="songs-only" aria-label="歌曲总时长">—</output>
      </div>
      <div class="cluster modes" role="group" aria-label="播放选项">
        ${button("loop", "loop", "循环", 'class="studio-only" aria-pressed="false" disabled')}
        ${button("click", "metronome", "节拍器", 'class="desktop studio-only" aria-pressed="false" disabled')}
        ${button("more", "more", "更多播放控制", 'aria-controls="options" aria-expanded="false"')}
      </div>
    </div>
    <div id="options" class="options" hidden>
      <div id="shuttle-slot"></div>
      <div class="video-only video-position">
        <button id="video-rewind" type="button" aria-label="后退五秒" title="后退五秒">−5s</button>
        <input id="video-seek" type="range" min="0" max="1" step="1" value="0" aria-label="视频播放位置">
        <button id="video-forward" type="button" aria-label="前进五秒" title="前进五秒">+5s</button>
      </div>
      ${button("click-mobile", "metronome", "节拍器", 'class="handheld studio-only" aria-pressed="false" disabled')}
      <label class="volume">${icon("volume")}<input id="volume" type="range" min="0" max="100" value="85" aria-label="主音量" title="主音量"></label>
      <div class="loop-range studio-only">
        ${icon("loop")}
        <input id="loop-in" type="number" min="0" step="0.25" aria-label="循环起点（秒）" title="循环起点（秒）">
        <span aria-hidden="true">–</span>
        <input id="loop-out" type="number" min="0.25" step="0.25" aria-label="循环终点（秒）" title="循环终点（秒）">
        ${button("loop-clip", "range", "以选中片段设置循环范围", "disabled")}
      </div>
    </div>`;
  const $ = id => root.getElementById(id);
  const narrow = matchMedia("(max-width: 820px)");
  const adapt = () => {
    const focus = root.activeElement;
    if (narrow.matches) {
      (home ? nav : entries).append(transport);
      $("shuttle-slot").append($("shuttle"));
    } else {
      anchor.after(transport);
      root.querySelector(".controls").insertBefore($("shuttle"), root.querySelector(".playback"));
    }
    if (focus?.getClientRects().length) focus.focus({ preventScroll: true });
    else if (focus) $("more").focus({ preventScroll: true });
  };
  adapt();
  narrow.addEventListener("change", adapt);

  const open = value => {
    $("more").setAttribute("aria-expanded", String(value));
    $("options").hidden = !value;
  };
  $("more").onclick = () => open($("options").hidden);
  root.addEventListener("keydown", event => {
    if (event.key !== "Escape" || $("options").hidden) return;
    event.stopPropagation();
    open(false);
    $("more").focus();
  });
  let source = null;
  root.addEventListener("click", () => {
    if (!$("options").hidden) source?.closeDrawer?.();
  });
  for (const id of ["play", "stop", "reset", "finish", "prev", "next", "loop", "click", "click-mobile", "loop-clip", "video-rewind", "video-forward"]) {
    $(id).onclick = event => source?.[id]?.(event);
  }
  $("song-seek").oninput = event => source?.seek?.(Number(event.target.value));
  $("video-seek").oninput = event => source?.videoSeek?.(Number(event.target.value), event);
  $("volume").oninput = event => source?.volume(Number(event.target.value) / 100, event);
  for (const id of ["loop-in", "loop-out"]) {
    $(id).onchange = event => {
      if ($("loop-in").value && $("loop-out").value) source?.setLoop?.(Number($("loop-in").value), Number($("loop-out").value), event);
    };
  }

  document.addEventListener("jiusera:imw-transport-state", event => source?.videoState?.(event.detail));
  return {
    $,
    isActive: owner => source === owner,
    activate(owner) {
      if (source === owner) return;
      source = owner;
      open(false);
      transport.hidden = false;
      transport.toggleAttribute("data-songs", owner.songs === true);
      transport.toggleAttribute("data-video", owner.video === true);
      $("output-meter").hidden = false;
      $("video-meter-note").hidden = true;
      for (const id of ["reset", "finish", "song-seek"]) $(id).removeAttribute("aria-disabled");
      for (const id of ["click","click-mobile"]) $(id).title = "节拍器";
      transport.setAttribute("aria-label", owner.songs ? "L-unify 歌曲试听控制器" : "L-unify IMW 播放控制器");
      $("volume").value = Math.round(owner.level() * 100);
    },
    deactivate(owner) {
      if (source !== owner) return;
      source = null;
      open(false);
      transport.hidden = true;
    },
    close: () => open(false),
    meterVisible: () => !narrow.matches,
    playback({ playing, loading, cancelLoading = false, canPlay, canStop, unavailable }) {
      const active = playing === true || cancelLoading;
      if (transport.hasAttribute("data-playing") !== active) {
        transport.toggleAttribute("data-playing", active);
        $("play").innerHTML = icon(active ? "pause" : "play");
      }
      $("play").disabled = !canPlay;
      if ($("play").getAttribute("aria-pressed") !== String(active)) $("play").setAttribute("aria-pressed", String(active));
      const label = cancelLoading ? "取消本次试听" : loading ? "正在连接音频输出" : playing ? "暂停" : unavailable || "播放";
      if ($("play").title !== label) {
        $("play").title = label;
        $("play").setAttribute("aria-label", label);
      }
      $("stop").disabled = !canStop;
    },
    peak(db) {
      const meter = $("output-meter");
      const rounded = Math.round(db);
      if (meter.getAttribute("aria-valuenow") === String(rounded)) return;
      meter.setAttribute("aria-valuenow", String(rounded));
      meter.setAttribute("aria-valuetext", rounded <= -60 ? "静音" : rounded + " dBFS");
      meter.style.setProperty("--peak-fill", (rounded + 60) / 60);
      meter.toggleAttribute("data-hot", rounded >= -6);
    },
  };
}

let shared;
function dockTransport() {
  return shared ??= createDockTransport();
}

export function mountTransport(studio) {
  const dock = dockTransport();
  const { $ } = dock;
  const owner = {
    play: () => studio.toggle(), stop: () => studio.stopTransport(),
    reset: () => studio.seek(0), finish: () => studio.seek(studio.length),
    prev: () => studio.step(-1), next: () => studio.step(1),
    loop: () => studio.toggleLoop(),
    click: () => studio.toggleClick(), "click-mobile": () => studio.toggleClick(),
    "loop-clip": () => studio.loopSelection(),
    level: () => studio.level,
    volume: value => studio.volume(value),
    closeDrawer: () => studio.drawer(false),
    setLoop(start, end) {
      studio.setLoop(start, end);
      studio.transport.sync();
    },
  };
  const video = videoControls(dock, studio);
  const active = () => dock.isActive(owner);
  const close = () => { if (active()) dock.close(); };
  studio.addEventListener("studio-drawer", event => { if (event.detail) close(); });
  return {
    activate: () => { dock.activate(owner); dock.peak(-60); },
    activateVideo() {
      dock.activate(video);
      video.videoState({ ready: false, durationMs: 0, cursorMs: 0, loop: false });
      video.request();
    },
    deactivate: () => { dock.deactivate(owner); dock.deactivate(video); },
    close,
    meterVisible: () => active() && dock.meterVisible(),
    peak: db => { if (active()) dock.peak(db); },
    time: label => { if (active()) $("time").textContent = label; },
    sync() {
      studio.syncSongAudition();
      if (!active()) return;
      dock.playback({ playing: studio.playing, loading: !!studio.startup,
        canPlay: studio.canPlayAudio && !studio.startup,
        canStop: studio.canPlayAudio && (studio.startPoint != null || !!studio.startup) });
      $("loop").setAttribute("aria-pressed", String(studio.loopEnabled));
      const hasTempo = studio.song?.bpm > 0;
      for (const id of ["click", "click-mobile"]) {
        $(id).disabled = !hasTempo;
        $(id).setAttribute("aria-pressed", String(hasTempo && studio.clickEnabled));
      }
      for (const id of ["reset", "finish", "prev", "next", "loop", "loop-in", "loop-out"]) $(id).disabled = !studio.version;
      $("loop-clip").disabled = !studio.selected || !studio.clip(studio.selected, studio.selectedPart);
      for (const id of ["loop-in", "loop-out"]) $(id).max = studio.length;
      $("loop-in").value = studio.loop.start;
      $("loop-out").value = studio.loop.end;
    },
  };
}

function videoControls(dock, studio) {
  const { $ } = dock;
  let level = 1, controlsKey = "";
  function send(action, inputEvent, values = {}) {
    document.dispatchEvent(new CustomEvent("jiusera:imw-transport-command", {
      detail: { action, inputEvent, ...values },
    }));
  }
  const commands = {
    play: "play", stop: "stop", reset: "first", finish: "last", prev: "previous-cut",
    next: "next-cut", loop: "loop", "loop-clip": "loop-clip",
    "video-rewind": "rewind", "video-forward": "forward",
    click: "metronome", "click-mobile": "metronome",
  };
  const video = {
    video: true,
    level: () => level,
    request: () => send("request-state"),
    volume: (value, event) => send("volume", event, { level: value }),
    videoSeek: (ms, event) => send("seek", event, { cursorMs: ms }),
    closeDrawer: () => studio.drawer(false),
    setLoop: (start, end, event) => send("loop-range", event, {
      inMs: Math.round(start * 1000), outMs: Math.round(end * 1000),
    }),
    videoState(state) {
      if (!state || !dock.isActive(video)) return;
      const duration = Math.max(0, Number(state.durationMs) || 0);
      const cursor = Math.max(0, Math.min(duration, Number(state.cursorMs) || 0));
      const ready = state.active !== false && state.ready && duration > 0;
      const pending = !!(state.pending || state.loading);
      const time = songTime(cursor / 1000);
      if ($("time").textContent !== time) $("time").textContent = time;
      const seek = $("video-seek");
      seek.disabled = !ready;
      if (seek.max !== String(duration || 1)) seek.max = String(duration || 1);
      if (Number(seek.value) !== cursor) seek.value = String(cursor);
      const seekLabel = time + " / " + songTime(duration / 1000);
      if (seek.getAttribute("aria-valuetext") !== seekLabel) seek.setAttribute("aria-valuetext", seekLabel);
      const measured = Number.isFinite(state.peakDb);
      if (measured) dock.peak(Math.max(-60, Math.min(0, state.peakDb)));
      const key = [ready, pending, state.playing, state.canStop, cursor === 0, cursor >= duration,
        duration, state.loop, state.canLoopClip, state.loopInMs, state.loopOutMs,
        state.level, state.canClick, state.metronome, measured].join("/");
      if (key === controlsKey) return;
      controlsKey = key;
      dock.playback({ playing: !!state.playing, loading: pending, cancelLoading: pending && !state.playing,
        canPlay: ready || pending, canStop: !!state.canStop || pending, unavailable: ready ? "" : "暂无可播放的视频" });
      for (const id of ["reset", "prev", "video-rewind"]) $(id).disabled = !ready || cursor <= 0;
      for (const id of ["finish", "next", "video-forward"]) $(id).disabled = !ready || cursor >= duration;
      $("loop").disabled = !ready || duration < 250;
      $("loop").setAttribute("aria-pressed", String(!!state.loop));
      $("loop-clip").disabled = !ready || !state.canLoopClip;
      for (const [id, ms] of [["loop-in", state.loopInMs], ["loop-out", state.loopOutMs]]) {
        const control = $(id);
        control.disabled = !ready || !Number.isFinite(ms) || duration < 250;
        control.max = duration / 1000;
        if (!control.matches(":focus")) control.value = Number.isFinite(ms) ? ms / 1000 : "";
      }
      for (const id of ["click", "click-mobile"]) {
        $(id).disabled = !ready || !state.canClick;
        $(id).setAttribute("aria-pressed", String(!!state.metronome));
        $(id).title = state.canClick ? "节拍器" : "音频模式可使用节拍器";
      }
      if (Number.isFinite(state.level)) level = Math.max(0, Math.min(1, state.level));
      $("volume").value = Math.round(level * 100);
      $("output-meter").hidden = !measured;
      $("video-meter-note").hidden = measured;
    },
  };
  for (const [key, action] of Object.entries(commands)) video[key] = event => send(action, event);
  return video;
}

function songTime(seconds) {
  const tenths = Math.max(0, Math.floor(seconds * 10));
  const minutes = String(Math.floor(tenths / 600)).padStart(2, "0");
  const second = String(Math.floor(tenths / 10) % 60).padStart(2, "0");
  return minutes + ":" + second + "." + tenths % 10;
}

export function mountSongTransport({ audio, toggle, stop }) {
  const dock = dockTransport();
  const { $ } = dock;
  const seek = $("song-seek");
  const seekControls = [$("reset"), $("finish"), seek];
  const durationOfSource = () => Number.isFinite(audio.duration) && audio.duration > 0 ? audio.duration : 0;
  const owner = {
    songs: true,
    play: toggle,
    stop,
    reset: () => owner.seek(0),
    finish: () => owner.seek(audio.duration),
    seek: value => {
      if (durationOfSource()) audio.currentTime = value;
      else seek.value = "0";
    },
    level: () => audio.volume,
    volume: value => { audio.volume = value; },
  };
  return {
    activate: () => dock.activate(owner),
    deactivate: () => dock.deactivate(owner),
    sync({ available, loading }) {
      if (!dock.isActive(owner)) return;
      const duration = durationOfSource();
      const time = duration ? audio.currentTime : 0;
      const timeLabel = songTime(time);
      dock.playback({ playing: !audio.paused, cancelLoading: loading, canPlay: available || loading,
        canStop: loading || Boolean(duration && (!audio.paused || audio.currentTime > 0)),
        unavailable: available ? "" : "当前选择无可用试听" });
      if ($("time").textContent !== timeLabel) $("time").textContent = timeLabel;
      const totalLabel = duration ? "/ " + songTime(duration).slice(0, -2) : "—";
      if ($("song-duration").textContent !== totalLabel) $("song-duration").textContent = totalLabel;
      // Keep focus and the native range's appearance while the new source has no seekable duration.
      for (const control of seekControls) {
        control.disabled = !duration && !loading;
        if (!duration && loading) control.setAttribute("aria-disabled", "true");
        else control.removeAttribute("aria-disabled");
      }
      seek.max = String(duration || 1);
      seek.value = String(time);
      seek.setAttribute("aria-valuetext", timeLabel);
    },
  };
}
