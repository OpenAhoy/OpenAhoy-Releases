import { detachedPlayback } from "./detached-playback.mjs";
import { mountFrameRuler } from "./frame-ruler.mjs";
import { ceilFrame, clipEditing } from "./clip-editing.mjs";
import { mountDetachedTracks } from "./detached-tracks.mjs";
import { mountTimelineSelection } from "./timeline-selection.mjs";
import { mountVideoView } from "./imw-view.mjs";
import { TrackMonitor, MonitorGains } from "./track-monitor.mjs";
import { audibleState, playStudioBus } from "./studio-live-transport.mjs";
import { connectStudio, studioCover, studioFetch as fetch } from "./bridge.mjs";
import { closeHome, homeSelection, openHome, openSongs, readPreference as read,
  rememberPreference as remember } from "./home.mjs";
import stylesheet from "./studio.css";
import clipStyles from "./studio-clips.css";
import { mountVideoDisclosure } from "./imw-disclosure.mjs";
import { clearAnalysis, mountMasterControls, renderStudioMaster, syncMasterControls } from "./output-master.mjs";
import { buildWaveIndex, cutQuietRanges, wavePeaks } from "./wave-peaks.mjs";
import { mountTransport } from "./transport.mjs";
import { timelineGrid } from "./timeline-grid.mjs";
import { confirmOutput } from "./audio-start.mjs";
import { trackColor, trackColorSlots } from "./track-colors.mjs";
import { mountTrackEditor, trackEditorMarkup } from "./track-editor.mjs";

const markup = `
<style>${stylesheet}
${clipStyles}</style>
<div class="studio">
  <section id="imw-settings" popover="auto" aria-label="工作站设置">
    <div class="imw-settings-heading"><strong>工作站设置</strong><button id="imw-settings-close" type="button" aria-label="关闭工作站设置">×</button></div>
    <label id="audio-project-field" class="field">项目 <select id="project"></select></label>
    <button id="imw-project" class="field" type="button" aria-controls="directorProject">选择视频项目</button>
    <label id="imw-frame-zoom-field" class="field">时间轴缩放<select id="imw-frame-zoom" aria-label="视频时间轴缩放"><option value="audio">跟随音轨</option><option value="frame">逐帧</option></select></label>
    <div class="current-take">
      <strong id="song-title"></strong>
      <select id="version" aria-label="曲目版本"></select>
    </div>
    <div class="imw-settings-actions">
      <label id="imw-frame-rate-field" class="field">标尺帧率<select id="imw-frame-rate" aria-label="标尺帧率"></select></label>
      <button id="imw-inspect" type="button" aria-expanded="false">视频设置</button>
      <button id="imw-score-settings" type="button" aria-controls="tracks">音轨设置</button>
      <span id="tempo"></span>
      <label class="field zoom" title="时间轴缩放"><span aria-hidden="true">缩放</span><select id="zoom" aria-label="时间轴缩放"><option value="1">适合</option><option value="2">2×</option><option value="4">4×</option></select></label>
      <button id="output-master" type="button" hidden>分析 Stereo Out</button>
      <a id="download-master" hidden>下载母带 WAV</a>
      <details id="master-settings" hidden><summary aria-label="Stereo Out · Output Master">Stereo Out<span class="master-settings-name"> · Output Master</span></summary>
        <div class="master-popover"><div id="master-delivery-info"></div>
        <label id="master-rate-choice" hidden>本次工程采样率 <select id="master-rate"><option value="">选择采样率</option></select></label>
        <button type="button" id="master-export" hidden>导出母带</button><div id="master-audition" hidden>
          <button type="button" id="master-listen">试听总线</button>
          <button type="button" id="master-bypass" aria-pressed="false">旁路</button>
          <audio id="master-aac-player" controls preload="none" aria-label="试听 Stereo Out" hidden></audio>
        </div>
        <a id="download-aac" hidden>下载 AAC</a><button type="button" id="master-adopt" hidden>采用此母带</button>
        <fieldset id="master-values" aria-label="母带参数"></fieldset>
        <small id="master-engine-note" hidden>当前机器的 Output Master 引擎不可用。</small><small id="master-saved"></small></div>
      </details>
      <button id="cut-quiet" type="button" aria-label="切除低音量" title="切除所有轨道中连续至少 120 毫秒、峰值低于 −48 dBFS 的段落">切除低音量</button>
      <button id="undo-cut" type="button" aria-label="撤销切除" title="撤销上次切除低音量" hidden>撤销</button>
      <button id="songs-toggle" class="mobile" aria-expanded="false" aria-controls="songs">歌单</button>
    </div>
  </section>
  <div class="body">
    <div id="imw-audio-fit" class="arrangement" aria-hidden="true" inert><i></i><i class="timeline"></i></div>
    <main class="editor" aria-label="音乐时间轴">
      <div id="imw-screen" role="region" aria-label="视频监看"><span id="imw-opening" role="status">正在打开视频…</span><slot name="imw-video"></slot></div>
      <div id="monitor-route" role="status" hidden></div>
      <div id="track-scroll-panel" class="arrangement">
        <div class="track-list">
          <div id="tracks"><div id="imw-video-header"></div><div class="track-heading"><span>轨道</span><span id="ruler-unit"></span></div><div id="imw-lane-labels"></div></div><div id="detached-heads"></div><select id="imw-add-track" aria-label="显示工程分轨" hidden></select>
        </div>
        <div id="scroll" class="timeline">
          <div id="lane" class="lane">
            <div id="imw-picture-lane">
              <button id="imw-folded-video" type="button" aria-label="展开视频" aria-expanded="false" aria-controls="imw-screen"><span>展开视频</span></button>
              <div id="imw-cut-lanes"><slot name="imw-timeline"></slot></div>
            </div>
            <div id="ruler" class="ruler">
              <div id="ticks" aria-hidden="true"></div>
              <input id="seek" aria-label="定位播放位置" type="range" min="0" max="30" step="0.1" value="0">
            </div>
            <div id="regions"></div>
            <p id="imw-empty-tracks" role="status" tabindex="-1" hidden>此作品还没有可编辑的音轨。</p>
            <div id="imw-original-track" class="track-row" role="group" aria-label="镜头原声" hidden></div>
            <div id="detached-lanes"></div>
            <div id="loop-band" hidden></div>
            <div id="playhead" class="playhead"></div>
          </div>
        </div>
        <section id="empty" hidden>
          <p>这个项目还没有歌曲。</p>
          <button id="library">打开音频资产</button>
        </section>
      </div>
      ${trackEditorMarkup}
      <div class="editor-footer">
        <span id="status" role="status">正在读取登记项目…</span>
        <button id="retry" hidden>重试保存</button>
        <slot name="tools"></slot>
      </div>
    </main>
    <aside id="songs" aria-label="歌曲与选区详情">
      <div class="songs-heading"><h2>项目歌单</h2><span id="count"></span><button id="songs-refresh" type="button" aria-label="刷新歌单" title="刷新歌单">⟳</button><button id="songs-close" class="mobile">关闭</button></div>
      <div id="song-list"></div><p id="playlist-status" role="status" hidden></p>
      <section id="inspector" aria-label="曲目详情">
        <div class="inspector-switch">
          <button id="show-lyrics" type="button" aria-controls="lyrics" aria-pressed="true">歌词</button>
          <button id="show-clip" type="button" aria-controls="clip-details" aria-pressed="false">片段</button>
        </div>
        <section id="lyrics"><button id="imw-captions" type="button">歌词与字幕</button><p id="lyric-text"></p></section>
        <section id="clip-details" hidden>
          <strong id="clip-name"></strong>
          <dl>
            <div><dt>时间轴</dt><dd id="clip-timeline"></dd></div>
            <div><dt>源音频选区</dt><dd id="clip-source"></dd></div>
            <div id="clip-sample-row" hidden><dt>源采样点（终点不含）</dt><dd id="clip-samples"></dd></div>
            <div><dt>播放长度</dt><dd id="clip-duration"></dd></div>
            <div><dt>音频</dt><dd id="clip-format"></dd></div>
          </dl>
        </section>
      </section>
    </aside>
  </div>
</div>`;

const sameDraft = (a, b) => ["offsets", "trims", "padding", "splits", "cutUndo", "seconds", "zoom", "scroll"].every(
  key => JSON.stringify(a[key]) === JSON.stringify(b[key]),
);
const zoomSteps = [1, 2, 4];
const roundTimeline = end => Math.ceil(end / 5) * 5;

function sourceFrames(clip, rate, count) {
  const first = Math.max(0, Math.min(count, Math.round(clip.sourceIn * rate)));
  const last = Math.max(first, Math.min(count, Math.round((clip.sourceIn + clip.duration) * rate)));
  return { first, last };
}

const detailTime = seconds => {
  const micros = Math.round(seconds * 1e6);
  const minutes = Math.floor(micros / 60e6);
  const remainder = micros % 60e6 / 1e6;
  return String(minutes).padStart(2, "0") + ":" + remainder.toFixed(6).padStart(9, "0");
};
const clipBounds = clip => ({
  start: clip.start - clip.silenceHead,
  end: clip.start + clip.duration + clip.silenceTail,
});
const format = seconds => {
  const tenths = Math.floor(seconds * 10);
  return String(Math.floor(tenths / 600)).padStart(2, "0") + ":"
    + String(Math.floor(tenths / 10) % 60).padStart(2, "0") + "." + tenths % 10;
};

// Render-only input for the palette fixture. It never enters the transport.
const fixtureSampleRate = 128;
const makeFixtureSamples = () => Float32Array.from({ length: 40 * fixtureSampleRate }, (_, i) => {
  const t = i / fixtureSampleRate;
  const pulse = Math.exp(-((t * 3.2) % 1) * 3);
  const envelope = .18 + .45 * pulse * (.65 + .35 * Math.sin(t * 1.58));
  return envelope * (Math.sin(i * 1.72) + .16 * Math.sin(i * .37));
});

async function json(url, options) {
  const response = await fetch(url, options);
  if (!response.ok) throw Object.assign(Error("本机工程请求失败"), { status: response.status });
  return response.json();
}

class Studio extends HTMLElement {
  connectedCallback() {
    const root = this.attachShadow({ mode: "open" });
    root.innerHTML = markup;
    this.$ = id => root.getElementById(id);
    this.frameRuler = mountFrameRuler(this);
    this.length = 30;
    this.fitLength = this.length;
    this.rulerLength = this.length;
    this.seconds = 0;
    this.buffers = new Map();
    this.trackColors = new Map();
    this.waveIndexes = new WeakMap();
    this.expandedTracks = new Set();
    this.sources = [];
    this.clipSources = new Map();
    this.trackMonitor = new TrackMonitor();
    this.busWindows = [];
    this.loop = { start: 0, end: 8 };
    this.loopEnabled = false;
    this.clickEnabled = false;
    this.level = .85;
    this.transport = mountTransport(this);
    this.transport.activate();
    this.trackEditor = mountTrackEditor(this);
    this.disclosure = mountVideoDisclosure(this);
    this.imw = mountVideoView(this);
    this.timelineSelection = mountTimelineSelection(this);
    this.detachedTracks = mountDetachedTracks(this);
    const settings = this.$("imw-settings");
    const settingsToggle = document.getElementById("imw-settings-toggle");
    if (settingsToggle) settingsToggle.onclick = () => settings.togglePopover();
    settings.addEventListener("toggle", () => {
      settingsToggle?.setAttribute("aria-expanded", String(settings.matches(":popover-open")));
    });
    this.$("imw-settings-close").onclick = () => {
      settings.hidePopover();
      settingsToggle?.focus({preventScroll:true});
    };
    for (const id of ["imw-project","imw-inspect","imw-score-settings","songs-toggle"]) {
      this.$(id).addEventListener("click", () => settings.hidePopover(), {capture:true});
    }
    const aspect = document.getElementById("imwFrameAspect");
    if (aspect) {
      const applyAspect = value => {
        const mode = value === "portrait" ? "portrait" : "landscape";
        aspect.value = mode;
        this.dataset.imwAspect = mode;
        if (this.imw.enabled()) document.body.dataset.imwAspect = mode;
      };
      applyAspect(read("monitor-aspect", "landscape"));
      aspect.onchange = () => {
        applyAspect(aspect.value);
        remember("monitor-aspect", aspect.value);
      };
    }
    this.transport.sync();
    this.drawer(false);

    this.$("project").onchange = e => {
      void this.change(e.target.value, undefined, undefined, true);
      void this.refreshCatalog();
    };
    this.$("version").onchange = e => void this.change(this.project.id, this.song.id, e.target.value, true);
    this.$("songs-refresh").onclick = () => void this.refreshCatalog();
    const refreshVisibleArchive = () => {
      if (this.project?.completionReplay && !document.hidden && !this.closest("#wbMusic").hidden)
        void this.refreshCatalog();
    };
    this.archiveListeners = new AbortController();
    this.workAudio = detachedPlayback(this,this.archiveListeners.signal);
    window.addEventListener("focus", refreshVisibleArchive, { signal: this.archiveListeners.signal });
    this.archiveTimer = window.setInterval(refreshVisibleArchive, 4000);
    this.$("songs-toggle").onclick = () => this.drawer(!this.$("songs").classList.contains("open"));
    this.$("songs-close").onclick = () => this.drawer(false, true);
    root.addEventListener("keydown", e => {
      if (e.key === "Escape" && !this.trackEditor.escape()) this.drawer(false, true);
    });
    this.$("library").onclick = () => document.querySelector("#wbMusic [data-wb-route=audio]").click();
    this.$("seek").oninput = e => this.imw.enabled() ? globalThis.OAIMWVideo?.seek(Number(e.target.value)) : this.seek(Number(e.target.value), false);
    this.$("seek").onchange = () => { if (!this.imw.enabled()) this.changed(); };
    this.$("ruler").onclick = e => {
      const bounds = e.currentTarget.getBoundingClientRect();
      const fraction = (e.clientX - bounds.left) / bounds.width;
      if (this.imw.enabled()) globalThis.OAIMWVideo?.seek(fraction*this.imw.displayLength());
      else this.seek(fraction*this.rulerLength);
    };
    this.$("zoom").onchange = e => this.setZoom(Number(e.target.value), this.$("scroll").clientWidth / 2);
    let wheelMotion = 0;
    let lastWheel = -Infinity;
    this.$("scroll").addEventListener("wheel", event => {
      if (!event.metaKey || !event.deltaY || !this.draft || this.recoveryConflict) return;
      event.preventDefault();
      const step = event.deltaY * (event.deltaMode === 0 ? 1 : event.deltaMode === 1 ? 18 : 60);
      if (event.timeStamp - lastWheel > 180 || Math.sign(step) !== Math.sign(wheelMotion)) wheelMotion = 0;
      lastWheel = event.timeStamp;
      wheelMotion += step;
      if (Math.abs(wheelMotion) < 40) return;
      const next = zoomSteps[zoomSteps.indexOf(this.draft.zoom) - Math.sign(wheelMotion)];
      wheelMotion = 0;
      if (next) this.setZoom(next, event.clientX - event.currentTarget.getBoundingClientRect().left);
    }, { passive: false });
    this.$("scroll").onscroll = () => {
      if (!this.imw.enabled() && this.draft && this.draft.scroll !== this.$("scroll").scrollLeft) this.changed();
    };
    this.$("retry").onclick = () => void this.save();
    void mountMasterControls(this);
    this.$("output-master").onclick = () => void renderStudioMaster(this);
    this.$("cut-quiet").onclick = () => this.cutQuiet();
    this.$("undo-cut").onclick = () => this.undoQuiet();
    this.$("show-lyrics").onclick = () => this.showInspector("lyrics");
    this.$("show-clip").onclick = () => this.showInspector("clip");
    new ResizeObserver(() => {
      this.drawRuler();
      this.paint();
    }).observe(this.$("scroll"));
    const container = this.closest("#wbMusic");
    document.addEventListener("keydown", event => {
      if (this.imw.enabled() || container.hidden || !this.canPlayAudio || event.defaultPrevented || event.repeat || event.code !== "Space") return;
      const target = event.composedPath()[0];
      if (target.closest?.("button,input,textarea,select,label,a,summary,[contenteditable],[role=button]")) return;
      event.preventDefault();
      void this.toggle();
    });
    const visibility = () => {
      if (container.hidden) {
        settings.hidePopover();
        this.pause();
        this.transport.close();
        this.$("master-aac-player").pause();
      } else {
        this.drawRuler();
        this.paint();
      }
    };
    new MutationObserver(visibility).observe(container, { attributes: true, attributeFilter: ["hidden"] });
    new MutationObserver(() => this.paint()).observe(document.body, { attributes: true, attributeFilter: ["data-color-scheme"] });
    addEventListener("pagehide", () => {
      if (this.playing) {
        this.stop();
        this.snapshot();
        this.journal();
      }
      this.startup?.abort();
      void this.closeOutput();
    });
    void this.start();
  }

  disconnectedCallback() {
    this.timelineSelection.dispose();
    this.detachedTracks.dispose();
    this.stop();
    clearAnalysis(this);
    void this.closeOutput();
    clearInterval(this.archiveTimer);
    this.archiveListeners?.abort();
    this.coverController?.abort();
    this.transport.deactivate();
  }

  async start() {
    try {
      this.projects = await json("/catalog");
      this.projectOptions();
      const requested = this.homeTarget;
      this.homeTarget = null;
      if (requested && this.hasHomeTarget(requested)) {
        await this.change(requested.project, requested.song, requested.version);
        return;
      }
      const saved = read("recent-project", "");
      const project = this.projects.find(item => item.id === saved) ?? this.projects[0];
      if (project) await this.change(project.id, read("song-" + project.id, ""));
      else {
        this.$("empty").hidden = false;
        this.$("inspector").hidden = true;
        this.status("请先关联有分轨的项目。");
      }
    } catch {
      this.status("无法读取已登记项目。请点刷新歌单重试。");
    }
  }

  projectOptions() {
    this.$("project").replaceChildren(...this.projects.map(project => new Option(project.name, project.id)));
    this.imw?.syncProject();
  }

  async imwProjectSelection(projectId) {
    if (!projectId) return null;
    if (this.project?.id===projectId && this.song?.id && this.version?.id)
      return {project:projectId,song:this.song.id,version:this.version.id};
    const projects=this.projects ?? await json("/catalog");
    const project=projects.find(item=>item.id===projectId);
    if (!project) return null;
    const remembered=read("song-"+projectId,"");
    const songs=project.songs || [];
    const preferred=songs.find(song=>song.id===remembered);
    for (const song of preferred?[preferred,...songs.filter(item=>item!==preferred)]:songs) {
      const saved=read("version-"+projectId+"/"+song.id,"");
      const version=song.versions?.find(item=>item.id===saved) ??
        song.versions?.find(item=>item.id===song.adopted);
      if(version)return {project:projectId,song:song.id,version:version.id};
    }
    return null;
  }

  hasHomeTarget({ project, song, version }) {
    return this.projects.find(item => item.id === project)?.songs.find(item => item.id === song)
      ?.versions.some(item => item.id === version);
  }

  async openHomeTarget(target) {
    this.homeTarget = target;
    if (!this.projects || this.switching) return;
    try {
      if (!this.hasHomeTarget(target)) {
        const projects = await json("/catalog");
        if (this.homeTarget !== target || this.closest("#wbMusic").hidden) return;
        this.projects = projects;
        this.projectOptions();
        this.$("project").value = this.project?.id ?? "";
      }
      if (this.homeTarget !== target || this.switching || this.closest("#wbMusic").hidden) return;
      this.homeTarget = null;
      if (!this.hasHomeTarget(target)) {
        this.status("该歌曲或版本暂不可用，请返回歌曲列表刷新。");
        return;
      }
      if (this.project?.id !== target.project || this.song?.id !== target.song || this.version?.id !== target.version) {
        await this.change(target.project, target.song, target.version);
      }
      this.showHomeFeature();
    } catch {
      if (!this.homeTarget || this.homeTarget === target) this.status("暂时无法切换到选中的歌曲。");
    }
  }

  showHomeFeature() {
    const feature = this.homeFeature;
    if (!feature || this.closest("#wbMusic").hidden || !this.version) return;
    const { selection, key } = feature;
    if (selection && (this.project.id !== selection.project || this.song.id !== selection.song
      || this.version.id !== selection.version)) return;
    const details = this.$("master-settings");
    const control = key === "master"
      ? (!details.hidden && details.querySelector("summary"))
      : this.shadowRoot.querySelector('[data-track-monitor=solo]:not(:disabled)');
    if (!control) return;
    this.homeFeature = null;
    if (key === "master") { this.$("imw-settings").showPopover(); details.open = true; }
    control.focus();
  }

  drawer(open, restore = false) {
    const panel = this.$("songs");
    const wasOpen = panel.classList.toggle("open", open);
    const button = this.$("songs-toggle");
    const previous = button.getAttribute("aria-expanded") === "true";
    button.setAttribute("aria-expanded", String(open));
    this.dispatchEvent(new CustomEvent("studio-drawer", { detail: open }));
    if (wasOpen && !previous) {
      this.$("songs-close").focus();
      if (this.project) void this.refreshCatalog();
    }
    if (!open && previous && restore) button.focus();
  }

  async change(projectId, songId, versionId, userSelected = false) {
    if (this.switching) return;
    this.switching = true;
    this.$("master-aac-player").pause();
    this.stopAndRemember();
    if (!await this.save()) {
      this.$("project").value = this.project.id;
      this.$("version").value = this.version?.id ?? "";
      this.switching = false;
      this.homeTarget = null;
      return;
    }

    this.timelineSelection?.clear();
    this.load?.abort();
    this.trackEditor.closeMenu();
    this.trackEditor.close();
    const load = new AbortController();
    this.load = load;
    this.project = this.projects.find(item => item.id === projectId);
    this.song = this.project.songs.find(item => item.id === (songId || read("song-" + projectId, ""))) ?? this.project.songs[0];
    const targetTake = versionId || read("version-" + projectId + "/" + this.song?.id, "");
    this.version = this.song?.versions.find(item => item.id === targetTake)
      ?? this.song?.versions.find(item => item.id === this.song.adopted);
    this.detachedTracks.selectionChanged();
    this.soloTrack = null;
    this.trackMonitor.select(this.project, this.song, this.version);
    this.monitorGains?.clearLanes();
    this.volume(this.level);
    this.toggleAttribute("data-paint-only", this.version?.paintOnly === true);
    this.buffers = new Map();
    this.audioReady = false;
    this.loadingTracks = !this.version?.mastered;
    syncMasterControls(this);
    this.startPoint = null;
    this.selected = null;
    this.selectedPart = 0;
    this.editNotice = null;
    this.expandedTracks.clear();
    this.loopEnabled = false;
    this.loop = { start: 0, end: 8 };
    this.draft = null;
    this.dirty = false;
    this.seconds = 0;
    this.fitLength = roundTimeline(Math.max(10, ...(this.version?.tracks ?? []).map(track => track.start + track.duration)));
    this.length = this.fitLength;
    this.rulerLength = this.length;
    this.$("scroll").scrollLeft = 0;
    this.$("retry").hidden = true;
    this.selectors();
    this.tracks();
    this.syncTrackMonitorControls?.();
    remember("recent-project", projectId);
    if (this.song) remember("song-" + projectId, this.song.id);
    if (this.version && versionId) remember("version-" + projectId + "/" + this.song.id, this.version.id);
    this.switching = false;
    this.imw.syncProject();
    if (userSelected) this.imw.selectionChanged();
    if (this.homeTarget) {
      const pending = this.homeTarget;
      queueMicrotask(() => {
        if (this.homeTarget === pending) void this.openHomeTarget(pending);
      });
    }
    if (!this.version) {
      this.status(this.project.state ? "本项目的分轨清单不可读。" : "");
      return;
    }

    if (this.version.pending) {
      this.status("这版已完成，音频待归档");
      return;
    }

    // The isolated palette fixture exercises real arrangement rows with no audio I/O.
    if (this.version.paintOnly) {
      this.status(this.version.tracks.length + " 轨绘制样件");
      return;
    }

    this.status("正在读取所选版本的音轨…");
    const { signal } = load;
    const version = this.version;
    const endpoint = this.endpoint();
    const stored = json(endpoint, { signal }).catch(() => null);
    const decodeTrack = async track => {
      const response = await fetch(track.url, { signal });
      if (!response.ok) throw Error("音轨不可用");
      this.decoder ??= new OfflineAudioContext(1, 1, Number(this.dataset.decodeRate));
      const buffer = await this.decoder.decodeAudioData(await response.arrayBuffer());
      if (track.sourceIn + track.duration > buffer.duration + .01) throw Error("音轨长度不匹配");
      return [track.id, buffer];
    };
    const decodeTracks = async () => {
      const results = [];
      // Limit simultaneous WAV fetches and decodes for full-length local stems.
      const batch = version.localImport ? 2 : version.tracks.length;
      for (let start = 0; start < version.tracks.length && !signal.aborted; start += batch) {
        results.push(...await Promise.allSettled(version.tracks.slice(start, start + batch).map(decodeTrack)));
      }
      return results;
    };
    const disk = await stored;
    if (signal.aborted) return;
    const pending = read(endpoint, null);
    for (const draft of [disk, pending]) {
      if (!draft) continue;
      draft.trims ??= {};
      draft.padding ??= {};
      draft.splits ??= {};
    }
    this.draft = disk;
    if (disk && pending && !sameDraft(disk, pending)) {
      if (disk.revision === pending.revision) {
        this.draft = pending;
        this.dirty = true;
      } else {
        this.recoveryConflict = true;
      }
    } else if (disk && pending) {
      remember(endpoint, null);
    }
    syncMasterControls(this);
    this.seconds = disk ? this.draft.seconds : 0;
    this.tracks();
    this.$("scroll").scrollLeft = this.draft?.scroll ?? 0;
    const media = version.mastered ? [] : await decodeTracks();
    if (signal.aborted) return;
    this.buffers = new Map(media.filter(item => item.status === "fulfilled").map(item => item.value));
    this.audioReady = !version.mastered && this.buffers.size > 0;
    this.loadingTracks = false;
    this.tracks();
    if (this.imw.enabled()) globalThis.OAIMWVideo?.refreshMix?.();
    this.showHomeFeature();
    this.transport.sync();
    this.status(!disk ? "草稿读取失败。可试听，编辑需重新打开工程。"
      : this.recoveryConflict ? "磁盘草稿已更新。待恢复编辑保留在本机，当前版本暂为只读。"
      : !version.mastered && this.buffers.size < version.tracks.length ? "有音轨缺失，试听仅使用可用音轨。"
      : this.dirty ? "已恢复未保存的草稿。"
      : version.localImport ? "已载入 " + version.tracks.length + " 条本机分轨"
      : version.mastered ? "Output Master · 立体声母带"
      : version.archive ? "本机归档 · " + version.source : "本机合成样件");
    if (this.dirty) void this.save();
    return load;
  }

  endpoint() {
    return "/draft?" + new URLSearchParams({
      project: this.project.id, song: this.song.id, version: this.version.id,
    });
  }

  selectors() {
    this.recoveryConflict = false;
    this.$("project").value = this.project.id;
    this.versionOptions();
    this.$("empty").hidden = Boolean(this.song);
    this.$("inspector").hidden = !this.song;
    this.$("lyric-text").textContent = this.version?.lyrics ?? "";
    this.$("song-title").textContent = this.song?.name ?? "";
    const meter = this.song?.meter;
    const bpm = this.song?.bpm;
    this.$("tempo").textContent = bpm > 0 ? bpm + " BPM" + (meter ? "  ·  " + meter.beats + "/" + meter.note : "")
      : this.song ? "速度未标注" : "";
    this.$("show-clip").disabled = true;
    this.showInspector("lyrics");
    this.renderSongCards();
  }

  versionOptions() {
    const versions = this.$("version");
    versions.replaceChildren(...(this.song?.versions ?? []).map(item => new Option(this.takeLabel(this.song, item), item.id)));
    versions.disabled = !this.song;
    versions.value = this.version?.id ?? "";
  }

  takeLabel(song, version) {
    if (!song.archive && !song.hasMasters) return version.name;
    if (version.pending) return version.name + " · 待归档";
    if (song.explicit === version.id) return version.name + " · 已采用";
    return version.name + (song.adopted === version.id ? " · 默认" : "");
  }

  async refreshCatalog() {
    if (this.catalogRefresh) return this.catalogRefresh;
    this.catalogRefresh = this.loadCatalog();
    try { await this.catalogRefresh; }
    finally { this.catalogRefresh = null; }
  }

  async loadCatalog() {
    try {
      const projects = await json("/catalog");
      const project = projects.find(item => item.id === this.project?.id);
      if (!project) return;
      const song = project.songs.find(item => item.id === this.song?.id);
      const different = JSON.stringify(project.songs) !== JSON.stringify(this.project.songs);
      this.projects = projects;
      this.project = project;
      this.song = song;
      this.$("playlist-status").hidden = true;
      if (different && !this.switching) {
        const version = song?.versions.find(item => item.id === this.version?.id);
        // A newly available take may load in place. A late sibling must not reset this transport.
        if (this.version?.pending && version && !version.pending) {
          await this.change(project.id, song.id, version.id);
        } else {
          this.versionOptions();
          this.renderSongCards();
        }
      }
    } catch {
      const status = this.$("playlist-status");
      status.textContent = "暂时无法刷新歌单";
      status.hidden = false;
    }
  }

  renderSongCards() {
    const list = this.$("song-list");
    const focus = this.shadowRoot.activeElement;
    const focusSong = focus?.closest(".song-card")?.dataset.song;
    const focusControl = focus?.dataset.cardControl;
    this.coverController?.abort();
    this.coverController = new AbortController();
    this.$("count").textContent = this.project.songs.length + " 首";
    list.replaceChildren(...this.project.songs.map(song => this.songCard(song)));
    if (focusSong && focusControl) {
      const card = [...list.children].find(item => item.dataset.song === focusSong);
      card?.querySelector('[data-card-control="' + focusControl + '"]')?.focus({ preventScroll: true });
    }
    this.syncSongAudition();
  }

  songCard(song) {
    const project = this.project.id;
    const current = song.id === this.song?.id;
    const remembered = read("version-" + project + "/" + song.id, "");
    const version = song.versions.find(item => item.id === (current ? this.version?.id : remembered))
      ?? song.versions.find(item => item.id === song.adopted);
    const playable = !version.paintOnly && !version.pending && version.tracks.length > 0;
    const card = document.createElement("article");
    card.className = "song-card";
    card.dataset.song = song.id;
    card.dataset.version = version.id;
    card.toggleAttribute("data-current", current);

    const cover = document.createElement("button");
    cover.type = "button";
    cover.className = "song-cover";
    cover.dataset.cardControl = "cover";
    cover.disabled = !playable;
    cover.dataset.label = song.name + " · " + version.name;
    if (version.cover) {
      const art = new Image();
      art.alt = "";
      art.draggable = false;
      art.onerror = () => art.remove();
      cover.append(art);
      const signal = this.coverController.signal;
      void studioCover(version.cover, signal).then(url => {
        if (!url) return;
        if (signal.aborted || !card.isConnected) URL.revokeObjectURL(url);
        else {
          signal.addEventListener("abort", () => URL.revokeObjectURL(url), { once: true });
          art.src = url;
        }
      }).catch(() => {});
    }
    const playIcon = document.createElement("span");
    playIcon.className = "song-icon";
    playIcon.setAttribute("aria-hidden", "true");
    cover.append(playIcon);
    cover.onclick = () => this.audition(project, song.id, version.id);

    const select = document.createElement("button");
    select.type = "button";
    select.className = "song";
    select.dataset.cardControl = "song";
    select.setAttribute("aria-pressed", String(current));
    select.setAttribute("aria-label", song.name);
    select.append(Object.assign(document.createElement("strong"), { className: "song-name", textContent: song.name }));
    const source = version.source || (version.localImport ? "本地导入" : "本机样件");
    select.append(Object.assign(document.createElement("span"), {
      className: "song-source", textContent: source + (song.simulated ? " · 模拟" : ""),
    }));
    const adopted = song.versions.find(item => item.id === song.adopted);
    const label = song.archive || song.hasMasters
      ? this.takeLabel(song, version) + (version.pending ? "" : adopted.id === version.id ? " · 可试听"
        : " · 可试听 · " + (song.explicit ? "已采用 " : "默认 ") + adopted.name)
      : version.paintOnly ? "绘制样件" : version.name;
    select.append(Object.assign(document.createElement("span"), { className: "song-version", textContent: label }));
    select.onclick = () => {
      this.drawer(false, true);
      if (!current) void this.change(project, song.id, version.id, true);
    };
    card.append(cover, select);

    if (current && (song.archive || song.hasMasters) && playable && song.explicit !== version.id) {
      const adopt = document.createElement("button");
      adopt.type = "button";
      adopt.className = "adopt-take";
      adopt.dataset.cardControl = "adopt";
      adopt.textContent = "采用 " + version.name;
      adopt.onclick = async () => {
        await this.adoptVersion(project, song.id, version.id);
        if (!adopt.isConnected && this.project.id === project && this.song?.id === song.id
            && !this.shadowRoot.activeElement) this.$("version").focus();
      };
      card.append(adopt);
    }
    return card;
  }

  syncSongAudition() {
    for (const card of this.$("song-list").children) {
      const button = card.querySelector(".song-cover");
      const current = card.dataset.song === this.song?.id && card.dataset.version === this.version?.id;
      const playing = current && this.playing;
      const warm = current && this.startup;
      const state = button.disabled ? "音频不可用" : playing ? "暂停试听" : warm ? "正在准备试听" : "试听";
      const label = state + " " + button.dataset.label;
      if (button.title === label) continue;
      button.title = label;
      button.setAttribute("aria-label", label);
      button.setAttribute("aria-pressed", String(Boolean(playing)));
      button.lastElementChild.textContent = button.disabled ? "·" : playing ? "Ⅱ" : warm ? "…" : "▶";
    }
  }

  async adoptVersion(project, song, version) {
    if (this.adopting) return false;
    this.adopting = true;
    try {
      await json("/master-adopt", {method:"POST",body:JSON.stringify({project,song,version})});
      await this.refreshCatalog();
      syncMasterControls(this);
      return true;
    } catch {
      this.status("采用失败，草稿与当前版本已保留");
      return false;
    } finally {
      this.adopting = false;
    }
  }

  audition(project, song, version) {
    if (this.switching || this.startup) return;
    const same = project === this.project.id && song === this.song?.id && version === this.version?.id;
    if (this.imw.enabled()) {
      if (same) void globalThis.OAIMWVideo?.toggle?.();
      else void this.change(project, song, version, true);
      return;
    }
    if (same && this.version.mastered && !this.workAudio.available()) {
      const player = this.$("master-aac-player");
      if (!player.paused) return player.pause();
      this.$("master-settings").open = true;
      return this.$("master-listen").click();
    }
    if (same) return void this.toggle();
    // Start output preparation in the cover's pointer gesture while the target take loads.
    const target = this.change(project, song, version, true);
    void this.toggle(target);
  }

  makeTrackHead({ id, name, row, available = true, missing = "", monitor, shortcuts, expanded, select, expand }) {
    const head = document.createElement("div");
    head.className = "track-head";
    const label = document.createElement("button");
    label.type = "button";
    label.className = "track-name";
    label.dataset.head = id;
    label.setAttribute("aria-label", "查看轨道 " + name);
    label.append(Object.assign(document.createElement("span"), { className: "track-label", textContent: name }));
    if (missing) {
      label.classList.add("offline");
      label.append(Object.assign(document.createElement("span"), { className: "track-offline", textContent: missing }));
    }
    const arrow = document.createElement("span");
    arrow.className = "track-chevron"; arrow.setAttribute("aria-hidden", "true");
    label.append(arrow); head.append(label);
    const result = { head, label, row };
    if (monitor) {
      const controls = document.createElement("div");
      controls.className = "track-monitor-controls";
      controls.setAttribute("role","group");
      controls.setAttribute("aria-label", name + "监听");
      for (const [action,symbol,description] of [["solo","S","独奏"],["mute","M","静音"]]) {
        const key = document.createElement("button");
        key.type = "button"; key.dataset.trackMonitor = action; key.textContent = symbol;
        key.title = name + " · " + description; key.setAttribute("aria-label",key.title);
        key.disabled = !available; key.onclick = () => monitor(action);
        controls.append(key); result[action] = key;
      }
      result.status = document.createElement("span"); result.status.className = "track-monitor-status";
      result.status.setAttribute("aria-hidden","true"); controls.append(result.status); head.append(controls);
    }
    const actions = document.createElement("div");
    actions.className = "track-actions"; actions.id = "track-actions-" + id;
    actions.setAttribute("aria-label",name + "快捷功能"); actions.setAttribute("role","group");
    label.setAttribute("aria-controls",actions.id);
    for (const [text, run, disabled] of shortcuts) {
      const control = document.createElement("button");
      control.type = "button"; control.textContent = text; control.disabled = !!disabled; control.onclick = run;
      actions.append(control);
    }
    const setExpanded = value => {
      head.toggleAttribute("data-expanded",value); row.toggleAttribute("data-expanded",value);
      actions.hidden = !value; label.setAttribute("aria-expanded",String(value));
    };
    setExpanded(expanded);
    label.onclick = event => {
      if (event.detail < 2) {
        const value = !head.hasAttribute("data-expanded");
        setExpanded(value); expand(value);
      }
      select();
    };
    head.append(actions);
    return result;
  }

  tracks() {
    const tracksNode = this.$("tracks");
    tracksNode.replaceChildren(this.$("imw-video-header"), tracksNode.querySelector(".track-heading"), this.$("imw-lane-labels"));
    const extraHeads = this.$("imw-lane-labels");
    this.$("regions").replaceChildren();
    this.groups = new Map();
    this.trackHeads = new Map();
    this.trackMonitorControls = new Map();
    const tracks = this.version?.tracks ?? [];
    const colors = this.colorsFor(tracks);
    for (const track of tracks) {
      const tone = trackColor(colors.get(track.id));
      const available = this.buffers.has(track.id);
      const offline = !!this.draft && !available && !this.version.mastered;
      const row = document.createElement("div");
      row.className = "track-row"; row.dataset.trackRow = track.id;
      const noClip = (!available && !this.version.paintOnly) || !this.clips(track).length;
      const controls = this.makeTrackHead({
        id:track.id, name:track.name, row, available,
        missing: offline ? (this.loadingTracks ? "载入中" : "缺轨") : "",
        monitor: !this.version.mastered && !this.version.pending ? action => {
          if (action === "solo") this.toggleTrackSolo(track.id);
          else this.toggleTrackMute(track.id);
        } : null,
        shortcuts: [
          ["定位起点", () => {
            const first = this.clips(track)[0]; if (first) this.seek(clipBounds(first).start);
          },noClip],
          ["循环片段", () => { this.selectClip(track); this.loopSelection(); },noClip],
        ],
        expanded:this.expandedTracks.has(track.id),
        expand:value => { if (value) this.expandedTracks.add(track.id); else this.expandedTracks.delete(track.id); },
        select:() => this.selectClip(track),
      });
      const {head,label} = controls;
      head.dataset.trackRow = track.id; this.trackHeads.set(track.id,label);
      if (controls.solo) this.trackMonitorControls.set(track.id,controls);
      this.trackEditor.bind(label,track,0); tracksNode.append(head);
      const groups = this.clips(track).map((_, part) => this.makeClipGroup(track, part, tone, available, offline));
      this.groups.set(track.id, groups);
      row.append(...groups);
      this.$("regions").append(row);
    }
    tracksNode.append(extraHeads);
    this.syncTrackMonitorControls();
    this.trackEditor.syncRows();
    this.$("zoom").value = this.draft?.zoom ?? 1;
    this.$("zoom").disabled = !this.draft || this.recoveryConflict;
    this.grid();
  }

  paintTrackMonitor({head,row,label,solo,mute,status},state) {
    const suppressed = !state.audible;
    const inherited = suppressed && !state.mute;
    head.toggleAttribute("data-monitor-muted", suppressed);
    row.toggleAttribute("data-monitor-muted", suppressed);
    head.toggleAttribute("data-monitor-inherited", inherited);
    solo.setAttribute("aria-pressed", String(state.solo));
    mute.setAttribute("aria-pressed", String(state.mute));
    const reason = state.mute ? "已手动静音" : inherited
      ? (this.soloTrack ? "因编辑器独听而暂时静音" : "因其他轨道独奏而暂时静音")
      : state.editorSolo ? "编辑器独听" : state.solo ? "已独奏" : "";
    status.textContent = suppressed ? "静音" : state.editorSolo ? "独听" : "";
    status.title = reason;
    for (const node of [label, solo, mute]) {
      if (reason) node.setAttribute("aria-description", reason);
      else node.removeAttribute("aria-description");
    }
    mute.title = mute.getAttribute("aria-label") + (inherited ? "（" + reason + "）" : "");
  }

  syncTrackMonitorControls() {
    for (const [id, controls] of this.trackMonitorControls ?? [])
      this.paintTrackMonitor(controls,this.trackMonitorState(id));
    const route = this.monitorRoute();
    const filtered = !!this.masterAnalysis && route === "filtered";
    const status = this.$("monitor-route");
    status.hidden = !this.masterAnalysis;
    const text = !this.masterAnalysis ? "" : filtered ? "原分轨监听 · 独奏 / 静音"
      : route === "bypass" ? "总线监听 · Stereo Out 旁路" : "总线监听 · Output Master 湿声";
    if (status.textContent !== text) status.textContent = text;
    this.$("master-listen").textContent = filtered ? "试听原分轨" : "试听总线";
    const bypass = this.$("master-bypass");
    bypass.textContent = filtered ? "返回总线后旁路" : "旁路";
  }

  makeClipGroup(track, part, tone, available, offline) {
    const group = document.createElement("div");
    group.className = "clip-group";
    group.dataset.track = track.id;
    group.dataset.part = part;
    group.style.setProperty("--tone", tone);
    group.classList.toggle("offline", offline);
    const region = document.createElement("button");
    region.className = "clip";
    const label = track.name + "片段" + (this.draft?.splits?.[track.id] ? " " + (part + 1) : "");
    region.setAttribute("aria-label", label + (offline ? "，音频不可用" : ""));
    region.append(document.createElement("canvas"));
    region.disabled = !this.draft || this.recoveryConflict || !available;
    region.onclick = () => this.selectClip(track, part);
    this.trackEditor.bind(region, track, part);
    this.bindClipControl(region, group, track, part, "move");
    group.append(region);
    for (const edge of ["head", "tail"]) {
      const silence = document.createElement("span");
      silence.className = "clip-silence " + edge;
      silence.hidden = true;
      silence.setAttribute("role", "img");
      group.append(silence);
      const handle = document.createElement("button");
      handle.className = "trim-handle " + edge;
      handle.setAttribute("aria-label", (edge === "head" ? "裁剪起点" : "裁剪终点") + " · " + (this.draft?.splits?.[track.id] ? label : track.name));
      handle.disabled = region.disabled;
      this.bindClipControl(handle, group, track, part, edge);
      group.append(handle);
    }
    return group;
  }

  colorsFor(tracks) {
    if (!this.song) return new Map();
    const key = "track-colors/" + JSON.stringify([this.project.id, this.song.id]);
    const saved = read(key, null) ?? this.trackColors.get(key);
    const slots = trackColorSlots(tracks, saved);
    const entries = [...slots];
    this.trackColors.set(key, entries);
    if (JSON.stringify(entries) !== JSON.stringify(saved)) remember(key, entries);
    return slots;
  }

  clips(track) {
    return this.draft?.splits?.[track.id] ?? [this.clip(track)];
  }

  clip(track, part = 0) {
    const split = this.draft?.splits?.[track.id];
    if (split) return split[part];
    const { head = 0, tail = 0 } = this.draft?.trims?.[track.id] ?? {};
    const { head: silenceHead = 0, tail: silenceTail = 0 } = this.draft?.padding?.[track.id] ?? {};
    return {
      start: this.draft?.offsets[track.id] ?? track.start,
      sourceIn: track.sourceIn + head,
      duration: track.duration - head - tail,
      head,
      tail,
      silenceHead,
      silenceTail,
    };
  }

  placeClip(group, clip, length = this.length) {
    const { start, end } = clipBounds(clip);
    const span = end - start;
    const head = 100 * clip.silenceHead / span;
    const tail = 100 * clip.silenceTail / span;
    group.style.left = 100 * start / length + "%";
    group.style.width = 100 * span / length + "%";
    group.toggleAttribute("data-tight", span / length * this.$("lane").clientWidth < 22);
    group.style.setProperty("--silence-head", head + "%");
    group.style.setProperty("--silence-tail", tail + "%");
    for (const [edge, seconds] of [["head", clip.silenceHead], ["tail", clip.silenceTail]]) {
      const part = group.querySelector(".clip-silence." + edge);
      part.hidden = seconds === 0;
      if (seconds) part.setAttribute("aria-label", (edge === "head" ? "前置" : "后置") + "静音 " + seconds + " 秒");
    }
  }

  sizeLane(length) {
    this.rulerLength = length;
    this.detachedTracks?.layout();
    if (this.imw?.enabled()) return this.imw.fit();
    this.setLaneExtent(length);
  }

  setLaneExtent(length) {
    // A longer arrangement widens the scrollable lane at the same pixels per second.
    this.$("lane").style.width = 100 * (this.draft?.zoom ?? 1) * length / this.fitLength + "%";
  }

  showDragPreview(group, clip, length) {
    if (length !== this.rulerLength) {
      this.sizeLane(length);
      for (const stem of this.version.tracks) {
        for (const [part, region] of this.groups.get(stem.id).entries()) {
          if (region !== group) this.placeClip(region, this.clip(stem, part), length);
        }
      }
      this.drawRuler(length);
      this.paintLoop(length);
      if (!this.imw.enabled()) this.$("playhead").style.left = 100 * this.seconds / length + "%";
    }
    this.placeClip(group, clip, length);
  }

  clipPlayhead() {
    return {
      position: () => {
        if (!this.imw.enabled()) return this.playing && this.context ? this.clockPosition() : this.seconds;
        const clock = globalThis.OAIMWVideo?.state();
        return clock?.ready ? this.frameRuler.current(clock.seconds) : null;
      },
      mark: snapped => this.toggleAttribute("data-playhead-snap", snapped),
    };
  }

  bindClipControl(control, group, track, part, action) {
    const constraints = () => {
      const parts = this.draft.splits[track.id];
      const before = parts?.[part - 1], after = parts?.[part + 1];
      const buffer = this.buffers.get(track.id);
      const timelineLimit = this.version.timelineLimit ?? 180;
      return {
        left: before ? clipBounds(before).end : 0,
        right: after ? clipBounds(after).start : Infinity,
        timelineLimit, startLimit: this.version.timelineLimit ?? (parts ? timelineLimit : 120),
        reserveTail: !!parts || this.version.localImport, rate: buffer?.sampleRate, frames: buffer?.length,
        moveRate: buffer?.sampleRate,
      };
    };
    const commit = clip => {
      const previous = this.clip(track, part);
      if (Object.keys(previous).every(key => previous[key] === clip[key])) return;
      this.selectClip(track, part);
      const previousLength = this.length;
      const split = this.draft.splits[track.id];
      if (split) {
        split[part] = clip;
        if (this.draft.cutUndo && Object.hasOwn(this.draft.cutUndo, track.id)) delete this.draft.cutUndo;
      } else {
        this.draft.offsets[track.id] = clip.start;
        if (action !== "move") {
          this.draft.trims[track.id] = { head: clip.head, tail: clip.tail };
          if (clip.silenceHead || clip.silenceTail)
            this.draft.padding[track.id] = { head: clip.silenceHead, tail: clip.silenceTail };
          else delete this.draft.padding[track.id];
        }
      }
      this.grid();
      if (this.playing) {
        if (previous.start !== clip.start || previous.sourceIn !== clip.sourceIn || previous.duration !== clip.duration) {
          this.refreshClipPlayback(track);
        }
        if (!this.loopEnabled && this.length > previousLength) {
          const from = Math.max(previousLength, this.clockPosition());
          this.scheduleClicks(from, this.length, this.clock + from);
        }
      }
      this.changed({ continueStems: true });
    };
    clipEditing.bind(control, {
      action, constraints, read: () => this.clip(track, part), commit, playhead: this.clipPlayhead(),
      geometry: () => ({
        width: this.imw.enabled() ? this.imw.dragWidth() : this.$("lane").getBoundingClientRect().width,
        length: this.imw.enabled() ? this.rulerLength : this.length,
      }),
      select: () => this.selectClip(track, part),
      preview: (clip, { length }) => {
        this.showDragPreview(group, clip, Math.max(length, roundTimeline(clipBounds(clip).end)));
        if (action !== "move") {
          this.paintClip(track, clip, group);
          if (this.selected === track && this.selectedPart === part) this.updateClipDetails(clip);
        }
      },
      cancel: () => this.grid(),
    });
  }

  updateQuietControls() {
    const editable = this.draft && !this.recoveryConflict;
    this.$("cut-quiet").disabled = !editable || !this.buffers.size;
    this.$("undo-cut").hidden = !editable || !this.draft.cutUndo;
  }

  cutQuiet() {
    if (!this.draft || this.recoveryConflict) return;
    const changed = new Map();
    const before = {};
    let removed = 0;
    for (const track of this.version.tracks) {
      const buffer = this.buffers.get(track.id);
      if (!buffer) continue;
      const channels = Array.from({ length: buffer.numberOfChannels }, (_, channel) => buffer.getChannelData(channel));
      const index = this.waveIndex(buffer, channels);
      const parts = [];
      let count = 0;
      for (const clip of this.clips(track)) {
        const cut = cutQuietRanges(channels, buffer.sampleRate, clip.sourceIn, clip.duration, index);
        if (!cut.count && !clip.silenceHead && !clip.silenceTail) {
          parts.push(clip);
          continue;
        }
        count += cut.count
          + Number(clip.silenceHead > 0 && cut.ranges[0]?.[0] === 0)
          + Number(clip.silenceTail > 0 && cut.ranges.at(-1)?.[1] === clip.duration);
        for (const [from, to] of cut.ranges) {
          parts.push({ start: clip.start + from, sourceIn: clip.sourceIn + from, duration: to - from,
            head: 0, tail: 0, silenceHead: 0, silenceTail: 0 });
        }
      }
      if (count) {
        before[track.id] = this.draft.splits[track.id] ?? null;
        changed.set(track, parts);
        removed += count;
      }
    }
    if (!removed) {
      this.status("没有符合 −48 dBFS 条件的低音量段");
      return;
    }
    this.draft.cutUndo = before;
    this.applySplits(changed, "已切除 " + removed + " 段低音量");
  }

  undoQuiet() {
    if (!this.draft?.cutUndo || this.recoveryConflict) return;
    const before = this.draft.cutUndo;
    const changed = new Map(this.version.tracks
      .filter(track => Object.hasOwn(before, track.id)).map(track => [track, before[track.id]]));
    delete this.draft.cutUndo;
    this.applySplits(changed, "已撤销切除");
  }

  applySplits(changed, notice) {
    for (const [track, parts] of changed) {
      if (parts) this.draft.splits[track.id] = parts;
      else delete this.draft.splits[track.id];
    }
    this.selected = null;
    this.showInspector("lyrics");
    if (this.playing) {
      for (const track of changed.keys()) this.refreshClipPlayback(track);
    }
    this.tracks();
    this.editNotice = notice;
    this.status(notice);
    this.changed();
  }

  setZoom(zoom, anchor) {
    if (!this.draft || this.recoveryConflict || zoom === this.draft.zoom) return;
    const lane = this.$("lane");
    const scroll = this.$("scroll");
    const width = lane.getBoundingClientRect().width;
    const fixedPoint = width ? (scroll.scrollLeft + anchor) / width : 0;
    this.draft.zoom = zoom;
    this.$("zoom").value = zoom;
    this.grid();
    scroll.scrollLeft = fixedPoint * lane.getBoundingClientRect().width - anchor;
    this.changed();
  }

  grid() {
    const tracks = this.version?.tracks ?? [];
    // Keep the existing workspace extent available when a clip is moved back or trimmed.
    let end = Math.max(this.length,this.imw.enabled() ? 0 : this.detachedTracks.extent());
    for (const track of tracks) {
      for (const clip of this.clips(track)) {
        end = Math.max(end, clipBounds(clip).end, clip.start + clip.duration + clip.tail);
      }
    }
    this.length = roundTimeline(end);
    this.sizeLane(this.length);
    this.drawRuler();
    if (!this.imw.enabled()) this.$("seek").max = this.length;
    this.seconds = Math.min(this.seconds, this.length);
    this.position();
    for (const track of tracks) {
      for (const [part, group] of this.groups.get(track.id).entries()) {
        const clip = this.clip(track, part);
        this.placeClip(group, clip);
        const { start, end } = clipBounds(clip);
        const times = format(start) + "–" + format(end);
        const source = format(clip.sourceIn) + "–" + format(clip.sourceIn + clip.duration);
        const body = group.querySelector(".clip");
        body.title = track.name + " · " + times + " · 源 " + source + " · 左右方向键移动";
        for (const edge of ["head", "tail"]) {
          const control = group.querySelector(".trim-handle." + edge);
          const at = edge === "head" ? start : end;
          control.title = "播放" + (edge === "head" ? "起点 " : "终点 ") + detailTime(at)
            + " · 拖动裁剪 · 方向键 1 样本 · Shift + 方向键 10 毫秒";
          control.setAttribute("aria-description", control.title);
        }
      }
    }
    this.updateQuietControls();
    if (this.loop.end > this.length) {
      this.loop.end = this.length;
      this.loop.start = Math.min(this.loop.start, this.length - .25);
    }
    this.paintLoop();
    this.updateSelection();
    this.transport.sync();
    this.paint();
  }

  drawRuler(length = this.rulerLength) {
    this.timelineSelection?.paint();
    const lane = this.$("lane");
    if (!lane.clientWidth) return;
    if (this.imw?.enabled()) return this.frameRuler.draw(this.imw.displayLength() || 1);
    const { labels, unit, major, beat, detail } = timelineGrid({
      length, width: lane.clientWidth, bpm: this.song?.bpm, meter: this.song?.meter,
    });
    this.$("ticks").replaceChildren(...labels.map(({ at, label }) => {
      const tick = document.createElement("span");
      tick.style.left = 100 * at / length + "%";
      tick.textContent = label;
      return tick;
    }));
    for (const [level, seconds] of Object.entries({ major, beat, detail })) {
      lane.style.setProperty("--" + level + "-step", seconds ? 100 * seconds / length + "%" : "100%");
      lane.toggleAttribute("data-" + level, seconds > 0);
    }
    const name = this.$("ruler-unit");
    if (name) name.textContent = unit;
  }

  showInspector(tab) {
    const showingClip = tab === "clip" && !!this.selected && !!this.clip(this.selected, this.selectedPart);
    this.$("show-lyrics").setAttribute("aria-pressed", String(!showingClip));
    this.$("show-clip").setAttribute("aria-pressed", String(showingClip));
    this.$("lyrics").hidden = showingClip;
    this.$("clip-details").hidden = !showingClip;
  }

  selectClip(track, part = 0) {
    this.selected = track;
    if (this.imw.enabled()) this.imw.selectStem(track);
    this.selectedPart = part;
    this.updateSelection();
    this.showInspector("clip");
    this.transport.sync();
  }

  updateSelection() {
    for (const group of this.shadowRoot.querySelectorAll(".clip-group,[data-head]")) {
      const selected = group.dataset.head
        ? group.dataset.head === this.selected?.id
        : group.dataset.track === this.selected?.id && Number(group.dataset.part) === this.selectedPart;
      group.toggleAttribute("data-selected", selected);
      if (group.dataset.head) group.setAttribute("aria-pressed", String(selected));
    }
    if (this.imw.enabled()) this.imw.paintSelection();
    const clip = this.selected && this.clip(this.selected, this.selectedPart);
    this.$("show-clip").disabled = !clip;
    if (clip) this.updateClipDetails(clip);
  }

  updateClipDetails(clip) {
    const { start, end } = clipBounds(clip);
    this.$("clip-name").textContent = this.selected.name;
    this.$("clip-timeline").textContent = detailTime(start) + "–" + detailTime(end);
    this.$("clip-source").textContent = detailTime(clip.sourceIn) + "–" + detailTime(clip.sourceIn + clip.duration);
    this.$("clip-duration").textContent = detailTime(end - start);
    const buffer = this.buffers.get(this.selected.id);
    this.$("clip-sample-row").hidden = !buffer;
    if (buffer) {
      const { first, last } = sourceFrames(clip, buffer.sampleRate, buffer.length);
      this.$("clip-samples").textContent = first + "–" + last + "（" + (last - first) + "）";
    }
    const formatLabel = buffer ? "WAV · " +
      (buffer.numberOfChannels === 1 ? "单声道" : buffer.numberOfChannels + " 声道")
      + " · " + buffer.sampleRate / 1000 + " kHz" : "缺失音频";
    this.$("clip-format").textContent = this.version.paintOnly ? "仅绘制" : formatLabel;
  }

  paintLoop(length = this.rulerLength) {
    const band = this.$("loop-band");
    band.hidden = !this.loopEnabled || !this.version;
    band.style.left = 100 * this.loop.start / length + "%";
    band.style.width = 100 * (this.loop.end - this.loop.start) / length + "%";
  }

  paint(waveHeight) {
    // Stretch the cached bitmap during disclosure instead of re-sampling every track on every frame.
    if (this.hasAttribute("data-imw-track-motion") && waveHeight === undefined) return;
    for (const track of this.version?.tracks ?? []) {
      for (const [part, group] of this.groups.get(track.id).entries()) {
        this.paintClip(track, this.clip(track, part), group, waveHeight);
      }
    }
  }

  waveIndex(buffer, channels) {
    if (!buffer || buffer.duration <= 60) return undefined;
    let index = this.waveIndexes.get(buffer);
    if (!index) {
      index = buildWaveIndex(channels);
      this.waveIndexes.set(buffer, index);
    }
    return index;
  }

  paintClip(track, clip, group, waveHeight) {
    const drawingOnly = this.version.paintOnly;
    const buffer = this.buffers.get(track.id);
    if (!buffer && !drawingOnly) return;
    const fixtureSamples = drawingOnly ? this.fixtureSamples ??= makeFixtureSamples() : null;
    const canvas = group.querySelector("canvas");
    const width = Math.min(this.hasAttribute("data-frame-zoom") ? 8192 : Infinity, Math.floor(canvas.clientWidth * devicePixelRatio));
    const height = Math.floor((waveHeight ?? canvas.clientHeight) * devicePixelRatio);
    const rate = drawingOnly ? fixtureSampleRate : buffer.sampleRate;
    const { first, last } = sourceFrames(clip, rate, drawingOnly ? fixtureSamples.length : buffer.length);
    const style = getComputedStyle(canvas);
    const color = style.color;
    const peakAlpha = Number(style.getPropertyValue("--wave-peak-alpha"));
    const rmsAlpha = Number(style.getPropertyValue("--wave-rms-alpha"));
    const stamp = [width, height, first, last - first, color, peakAlpha, rmsAlpha].join("/");
    if (!width || !height || canvas.dataset.wave === stamp) return;
    canvas.width = width;
    canvas.height = height;
    canvas.dataset.wave = stamp;
    const channels = drawingOnly ? [fixtureSamples] :
      Array.from({ length: buffer.numberOfChannels }, (_, channel) => buffer.getChannelData(channel));
    const rms = new Float32Array(width);
    if (last <= first) return;
    const data = wavePeaks(channels, first, last - first, width, rms, this.waveIndex(buffer, channels));
    const context = canvas.getContext("2d");
    context.fillStyle = color;
    for (let x = 0; x < width; x++) {
      const low = data[2 * x];
      const high = data[2 * x + 1];
      const top = height * (.5 - high * 1.35);
      const size = height * (high - low) * 1.35;
      context.globalAlpha = peakAlpha;
      context.fillRect(x, top, 1, Math.max(size, 1));
      const innerLow = Math.max(low, -rms[x]);
      const innerHigh = Math.min(high, rms[x]);
      if (innerHigh <= innerLow) continue;
      context.globalAlpha = rmsAlpha;
      context.fillRect(x, height * (.5 - innerHigh * 1.35),
        1, height * (innerHigh - innerLow) * 1.35);
    }
    context.globalAlpha = 1;
  }

  position() {
    this.transport.time(format(this.seconds));
    if (!this.imw?.enabled()) {
      this.$("seek").value = this.seconds;
      this.$("seek").setAttribute("aria-valuetext", format(this.seconds));
    }
    for (const track of this.version?.tracks ?? []) {
      let trackSounding = false;
      const playable = this.playing && this.buffers.has(track.id) && this.trackMonitorState(track.id).audible;
      for (const [part, group] of this.groups.get(track.id).entries()) {
        const clip = this.clip(track, part);
        const sounding = playable && this.seconds >= clip.start && this.seconds < clip.start + clip.duration;
        group.toggleAttribute("data-sounding", sounding);
        trackSounding ||= sounding;
      }
      this.trackHeads.get(track.id).toggleAttribute("data-sounding", trackSounding);
    }
    if (!this.imw?.enabled()) this.$("playhead").style.left = 100 * this.seconds / this.rulerLength + "%";
  }

  step(direction) {
    const edges = this.version?.tracks.flatMap(track => this.clips(track).flatMap(clip => {
      const { start, end } = clipBounds(clip);
      return [start, end];
    })) ?? [];
    const position = this.playing ? this.clockPosition() : this.seconds;
    const ahead = edges.filter(edge => direction * (edge - position) > .04);
    const target = ahead.length ? (direction > 0 ? Math.min(...ahead) : Math.max(...ahead)) : position + direction * 5;
    this.seek(target);
  }

  setLoop(start, end) {
    if (!Number.isFinite(start) || !Number.isFinite(end) || start < 0 || end > this.length || end - start < .25) {
      this.status("循环起终点须位于时间轴内，区间至少 0.25 秒。");
      return;
    }
    const current = this.playing ? this.clockPosition() : this.seconds;
    this.loop = { start, end };
    if (this.playing && this.loopEnabled) this.seek(current < start || current >= end ? start : current);
    this.paintLoop();
    this.transport.sync();
  }

  loopSelection() {
    const clip = this.selected && this.clip(this.selected, this.selectedPart);
    if (!clip) return;
    const { start, end } = clipBounds(clip);
    if (this.imw.enabled()) return this.imw.loopStem(start, end);
    this.setLoop(start, end);
    if (!this.loopEnabled) this.toggleLoop();
  }

  toggleLoop() {
    const current = this.playing ? this.clockPosition() : this.seconds;
    this.loopEnabled = !this.loopEnabled;
    if (this.playing) {
      const { start, end } = this.loop;
      this.seek(this.loopEnabled && (current < start || current >= end) ? start : current);
    }
    this.paintLoop();
    this.transport.sync();
  }

  toggleClick() {
    const current = this.playing ? this.clockPosition() : this.seconds;
    this.clickEnabled = !this.clickEnabled;
    if (this.playing) this.seek(current, false);
    this.transport.sync();
  }

  volume(level) {
    this.level = level;
    if (this.master) this.master.gain.setTargetAtTime(level, this.context.currentTime, .015);
  }

  get canPlayAudio() {return this.audioReady || this.workAudio?.available();}

  async toggle(target) {
    if (this.imw.enabled()) return globalThis.OAIMWVideo?.toggle?.();
    if (this.playing && !target) return this.pause();
    if (this.startup) {
      if (!target && this.workAudio.available()) this.startup.abort();
      return;
    }
    if (!target && !this.canPlayAudio) return;
    let load = this.load;
    const request = new AbortController();
    this.startup = request;
    this.transport.sync();
    let ready = false;
    try {
      const [output, selected] = await Promise.all([this.prepareOutput(request.signal), target]);
      ready = output;
      if (target) {
        load = selected;
        if (load && !request.signal.aborted && load === this.load) {
          this.seconds = 0;
          this.position();
        }
      }
      if (ready && !request.signal.aborted) await this.workAudio.prepare(request.signal);
      if (!ready && !request.signal.aborted) this.status("浏览器音频输出未就绪。");
    } catch {
      ready = false;
      if (!request.signal.aborted) this.status("音频未能开始播放，请重试。");
    } finally {
      this.startup = null;
      this.transport.sync();
    }
    if (!ready || !this.canPlayAudio || request.signal.aborted || load !== this.load || this.closest("#wbMusic").hidden) {
      if (target && !this.playing) this.player?.pause();
      return;
    }
    if (this.seconds >= this.length) this.seconds = 0;
    if (this.loopEnabled && (this.seconds < this.loop.start || this.seconds >= this.loop.end)) this.seconds = this.loop.start;
    this.startPoint = this.seconds;
    this.play();
  }

  async prepareOutput(signal) {
    const useMediaStream = "setSinkId" in AudioContext.prototype;
    for (const bridge of useMediaStream ? [true, false] : [false]) {
      if (signal.aborted) return false;
      try {
        if (!this.context) {
          this.context = new AudioContext(bridge
            ? { sinkId: { type: "none" } }
            : { latencyHint: "playback" });
          this.output = this.context.destination;
          if (bridge) {
            // Keep the DAW render clock independent of the hardware sink.
            // The native media element routes the same mix to the default device.
            this.output = this.context.createMediaStreamDestination();
            this.player = new Audio();
            this.player.srcObject = this.output.stream;
          }
          this.master = this.context.createGain();
          this.master.gain.value = this.level;
          this.master.connect(this.output);
          this.monitorGains = new MonitorGains(this.context, this.workAudio.connect(this.context,this.master));
          this.clickBuffers = new Map();
        }
        const budget = this.player ? 800 : 950;
        if (await confirmOutput(this.context, this.output, this.player, signal, budget)) return true;
      } catch (error) {
        if (!bridge || error.name === "NotAllowedError") {
          await this.closeOutput();
          throw error;
        }
      }
      await this.closeOutput();
    }
    return false;
  }

  async closeOutput() {
    const context = this.context;
    if (!context) return;
    this.workAudio.close();
    this.monitorGains?.close();
    this.monitorGains = null;
    this.context = null;
    this.master = null;
    if (this.player) {
      this.player.pause();
      this.player.srcObject = null;
      this.output.stream.getTracks().forEach(track => track.stop());
      this.player = null;
    }
    this.output = null;
    if (context.state === "closed") return;
    // A zero-clock context has no project audio. Wait briefly for its
    // device lease to be released, without leaving startup waiting forever.
    let timer;
    try {
      await Promise.race([
        context.close(),
        new Promise(resolve => { timer = setTimeout(resolve, 200); }),
      ]);
    } catch {
      // A context already closing may reject duplicate shutdown attempts.
    } finally {
      clearTimeout(timer);
    }
  }

  queueBuffer(buffer, time, offset, duration, trackId, fadeIn = false) {
    const source = this.context.createBufferSource();
    source.buffer = buffer;
    if (trackId) {
      const gain = this.context.createGain();
      if (fadeIn) {
        gain.gain.setValueAtTime(0, time);
        gain.gain.linearRampToValueAtTime(1, time + Math.min(.008, duration));
      }
      source.connect(gain).connect(this.monitorGains.lane(trackId, this.trackMonitorState(trackId).audible));
      this.clipSources.set(source, { trackId, gain, start: time, end: time + duration });
    } else {
      source.connect(this.workAudio.programOutput());
    }
    source.start(time, offset, duration);
    this.sources.push(source);
    source.onended = () => {
      this.disconnectSource(source);
      const index = this.sources.indexOf(source);
      if (index >= 0) this.sources.splice(index, 1);
    };
  }

  disconnectSource(source) {
    this.clipSources.get(source)?.gain.disconnect();
    this.clipSources.delete(source);
    source.disconnect();
  }

  clickBuffer(accent) {
    if (!this.clickBuffers.has(accent)) {
      const rate = this.context.sampleRate;
      const buffer = this.context.createBuffer(1, Math.ceil(rate * .03), rate);
      const samples = buffer.getChannelData(0);
      for (let index = 0; index < samples.length; index++) {
        const time = index / rate;
        samples[index] = Math.sin(2 * Math.PI * (accent ? 1550 : 1050) * time)
          * Math.min(1, time / .002) * Math.exp(-time * 155) * (accent ? .45 : .32);
      }
      this.clickBuffers.set(accent, buffer);
    }
    return this.clickBuffers.get(accent);
  }

  trackMonitorState(id) {
    return this.trackMonitor.state(id, this.soloTrack?.id);
  }

  monitorRoute() {
    if (this.trackMonitor.filtered(this.soloTrack?.id)) return "filtered";
    if (!this.masterAnalysis) return "stems";
    return this.busBypass ? "bypass" : "master";
  }

  updateMonitorGains(immediate = false) {
    this.workAudio?.levels();
    const route = this.monitorRoute();
    this.monitorGains?.update(route === "master" || route === "bypass",
      id => this.trackMonitorState(id).audible, immediate);
  }

  monitorSelectionChanged() {
    if (this.imw.enabled()) globalThis.OAIMWVideo?.refreshMix?.();
    // The native cursor keeps running under the filter. Use its published block
    // deadlines to align new stem voices without restarting the transport.
    if (this.liveMonitor?.run && this.monitorRoute() === "filtered")
      for (const window of this.busWindows) this.queueMonitorStems(window);
    this.updateMonitorGains();
    this.syncTrackMonitorControls?.();
    this.position();
  }

  toggleTrackSolo(id) {
    if (this.trackMonitor.toggle("solo", id)) this.monitorSelectionChanged();
  }

  toggleTrackMute(id) {
    if (this.trackMonitor.toggle("mute", id)) this.monitorSelectionChanged();
  }

  setSolo(track) {
    if (this.soloTrack === track) return;
    this.soloTrack = track;
    this.monitorSelectionChanged();
  }

  monitorBlock({ from, to, at }) {
    const now = this.context.currentTime;
    this.busWindows = this.busWindows.filter(w => w.at + w.to - w.from > now);
    const window = { from, to, at, stems: false };
    this.busWindows.push(window);
    if (this.monitorRoute() === "filtered") this.queueMonitorStems(window);
    this.workAudio.schedule(from,to,at);
    this.scheduleClicks(from, to, at);
  }

  queueMonitorStems(window) {
    if (window.stems) return;
    window.stems = true;
    const at = Math.max(window.at, this.context.currentTime);
    const from = window.from + (at - window.at);
    if (from >= window.to) return;
    for (const track of this.version.tracks) this.scheduleClip(track, from, window.to, at);
  }

  scheduleClip(track, from, to, at, fadeIn = false) {
    this.queueTrackClips(track, from, to, at, (buffer, time, offset, duration, trackId, fade) => {
      this.queueBuffer(buffer, time, offset, duration, trackId, fade);
    }, fadeIn);
  }

  queueTrackClips(track, from, to, at, queue, fadeIn = false, buffer = this.buffers.get(track.id), clips = this.clips(track)) {
    if (!buffer) return;
    const rate = buffer.sampleRate;
    for (const clip of clips) {
      const { start, duration } = clip;
      const end = start + duration;
      const head = Math.max(from, start);
      const tail = Math.min(to, end);
      if (tail <= head) continue;
      const { first, last } = sourceFrames(clip, rate, buffer.length);
      const skipped = ceilFrame((head - start) * rate);
      const past = tail === end ? last : Math.min(last, first + ceilFrame((tail - start) * rate));
      const offset = first + skipped;
      if (past <= offset) continue;
      const time = at + Math.max(0, start - from + skipped / rate);
      queue(buffer, time, offset / rate, (past - offset) / rate, track.id, fadeIn && start < from);
    }
  }

  schedule(from, to, at) {
    for (const track of this.version.tracks) this.scheduleClip(track, from, to, at);
    this.workAudio.schedule(from,to,at);
    this.scheduleClicks(from, to, at);
  }

  scheduleClicks(from, to, at) {
    if (this.clickEnabled && this.song.bpm > 0) {
      const beatLength = 60 / this.song.bpm;
      for (let beat = Math.ceil((from - 1e-7) / beatLength); beat * beatLength < to; beat++) {
        const offset = Math.max(0, beat * beatLength - from);
        const click = this.clickBuffer(beat % 4 === 0);
        this.queueBuffer(click, at + offset, 0, Math.min(click.duration, to - from - offset));
      }
    }
  }

  refreshClipPlayback(track) {
    if (this.liveMonitor?.run) return;
    // The edited track switches at a shared audio deadline. Other tracks keep their scheduled nodes.
    const at = this.context.currentTime + .018;
    for (const [source, voice] of this.clipSources) {
      if (voice.trackId !== track.id || voice.retired || voice.end <= at) continue;
      voice.retired = true;
      if (voice.start < at) {
        const fadeStart = Math.max(voice.start, at - .008);
        voice.gain.gain.cancelScheduledValues(fadeStart);
        voice.gain.gain.setValueAtTime(1, fadeStart);
        voice.gain.gain.linearRampToValueAtTime(0, at);
      }
      source.stop(at);
    }

    const from = this.clockPosition(at);
    if (!this.loopEnabled) {
      this.scheduleClip(track, from, this.length, at, true);
      return;
    }
    // Replace only loop passes that were already queued. The normal scheduler owns later passes.
    if (at >= this.nextRun) return;
    const { start, end } = this.loop;
    this.scheduleClip(track, from, end, at, true);
    const duration = end - start;
    for (let cycle = at + end - from; cycle < this.nextRun - 1e-6; cycle += duration) {
      this.scheduleClip(track, start, end, cycle);
    }
  }

  clockPosition(time = this.context.currentTime) {
    if (this.busPending) return this.seconds;
    const raw = Math.max(0, time - this.clock);
    if (this.loopEnabled && raw >= this.loop.end) {
      return this.loop.start + (raw - this.loop.end) % (this.loop.end - this.loop.start);
    }
    return Math.min(this.length, raw);
  }

  play({ clock = null } = {}) {
    this.updateMonitorGains(true);
    if (playStudioBus(this)) return;
    this.playing = true;
    const initialTime = this.context.currentTime;
    const started = performance.now();
    const end = this.loopEnabled ? this.loop.end : this.length;
    this.clock = clock ?? initialTime - this.seconds;
    if (clock !== null) this.seconds = this.clockPosition(initialTime);
    this.schedule(this.seconds, end, initialTime);
    this.nextRun = initialTime + end - this.seconds;
    this.transport.sync();
    const tick = () => {
      const now = this.context.currentTime;
      if (performance.now() - started > 1200 && now === initialTime) {
        this.stop();
        void this.closeOutput();
        this.status("音频输出没有启动。再次点击播放可重连。");
        return;
      }
      if (this.loopEnabled && this.nextRun < now + .18) {
        const duration = this.loop.end - this.loop.start;
        if (this.nextRun + duration <= now) this.nextRun += Math.floor((now - this.nextRun) / duration) * duration;
        const lateness = Math.max(0, now - this.nextRun);
        this.schedule(this.loop.start + lateness, this.loop.end, this.nextRun + lateness);
        this.nextRun += duration;
      }
      this.seconds = this.clockPosition();
      this.sampleOutput(now);
      this.position();
      if (!this.loopEnabled && this.seconds >= this.length) return this.pause();
      this.animation = requestAnimationFrame(tick);
    };
    tick();
  }

  sampleOutput(now) {
    if (!this.transport.meterVisible()) {
      if (this.outputMonitor) this.releaseOutputMonitor();
      return;
    }
    if (!this.outputMonitor) {
      const analyser = this.context.createAnalyser();
      analyser.fftSize = 256;
      this.master.connect(analyser);
      this.outputMonitor = { analyser, samples: new Float32Array(analyser.fftSize), at: now - .05, peak: 0 };
    }
    const meter = this.outputMonitor;
    const elapsed = now - meter.at;
    if (elapsed < .04) return;
    meter.analyser.getFloatTimeDomainData(meter.samples);
    let peak = 0;
    for (const sample of meter.samples) peak = Math.max(peak, Math.abs(sample));
    meter.peak = Math.max(peak, meter.peak * Math.exp(-elapsed * 12));
    meter.at = now;
    const db = Math.min(0, Math.max(-60, 20 * Math.log10(meter.peak)));
    this.transport.peak(db);
  }

  releaseOutputMonitor() {
    if (this.outputMonitor) {
      this.master.disconnect(this.outputMonitor.analyser);
      this.outputMonitor = null;
    }
    this.transport.peak(-60);
  }

  stop(keepOutput = false) {
    this.workAudio?.stopNodes();
    this.busPending = false;
    this.liveMonitor?.stop();
    this.busWindows = [];
    this.startup?.abort();
    if (!this.playing) return;
    this.playing = false;
    cancelAnimationFrame(this.animation);
    this.releaseOutputMonitor();
    for (const source of this.sources) {
      source.onended = null;
      source.stop();
      this.disconnectSource(source);
    }
    this.sources = [];
    if (!keepOutput) this.player?.pause();
    this.position();
    this.transport.sync();
  }

  stopTransport() {
    if (this.startPoint == null && !this.startup) return;
    this.stop();
    if (this.startPoint == null) return;
    this.seconds = this.startPoint;
    this.position();
    this.changed();
  }

  stopAndRemember() {
    this.startup?.abort();
    if (!this.playing) return;
    this.seconds = this.clockPosition();
    this.stop();
    this.position();
    this.changed();
  }

  pause() { this.stopAndRemember(); }

  seek(seconds, persist = true) {
    if (this.imw.enabled()) return this.imw.seek(seconds);
    const position = Math.max(0, Math.min(this.length, seconds));
    const withinLoop = !this.loopEnabled || (position >= this.loop.start && position < this.loop.end);
    const continuePlaying = this.playing && position < this.length && withinLoop;
    this.stop(continuePlaying);
    this.seconds = position;
    this.position();
    if (continuePlaying) this.play();
    if (persist) this.changed();
  }

  status(text) { this.$("status").textContent = text; }

  snapshot() {
    if (!this.draft || this.recoveryConflict) return false;
    this.draft.seconds = Math.round(this.seconds * 10) / 10;
    this.draft.scroll = this.frameRuler.audioScroll();
    this.dirty = true;
    return true;
  }

  journal() {
    if (this.dirty) remember(this.endpoint(), this.draft);
  }

  changed({ continueStems = false } = {}) {
    if (this.imw.enabled() && continueStems) globalThis.OAIMWVideo?.refreshMix?.();
    if (this.masterAnalysis && this.masterAnalysis.snapshot !== audibleState(this)) clearAnalysis(this, { continueStems });
    if (!this.snapshot()) return;
    this.journal();
    clearTimeout(this.saveTimer);
    this.saveTimer = setTimeout(() => void this.save(), 230);
  }

  async save() {
    while (this.saving) {
      if (!await this.saving) return false;
    }
    if (!this.dirty) return true;
    const endpoint = this.endpoint();
    const candidate = structuredClone(this.draft);
    this.saving = (async () => {
      try {
        const result = await json(endpoint, {
          method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(candidate),
        });
        this.dirty = !sameDraft(this.draft, candidate);
        this.draft.revision = result.revision;
        remember(endpoint, this.dirty ? this.draft : null);
        this.status(this.editNotice ?? "草稿已保存");
        this.editNotice = null;
        this.$("retry").hidden = true;
        return true;
      } catch (error) {
        this.status(error.status === 409
          ? "草稿已在其他窗口更新。当前编辑已保留，请保留此窗口。"
          : "保存失败，当前编辑已保留。重试后可切换。");
        this.$("retry").hidden = false;
        return false;
      } finally {
        this.saving = null;
      }
    })();
    const success = await this.saving;
    return success && (!this.dirty || await this.save());
  }
}

customElements.define("lus-studio", Studio);
globalThis.OAStudio = {
  clipEditing,
  openHome(container, call, navigation) {
    connectStudio(call);
    openHome(container, navigation);
  },
  openSongs(container, call, navigation, project) {
    connectStudio(call);
    openSongs(container, navigation, project);
  },
  homeSelection,
  closeHome,
  async imwProjectSelection(project) {
    return await document.querySelector("lus-studio")?.imwProjectSelection(project) ?? null;
  },
  setVideoProject(project, selection) {
    document.querySelector("lus-studio")?.imw?.setProject(project, selection);
  },
  setVideoMode(enabled) {
    document.querySelector("lus-studio")?.imw?.setMode(!!enabled);
  },
  closeStudio() {
    const studio = document.querySelector("lus-studio");
    if (!studio) return;
    studio.imw?.setMode(false);
    studio.stopAndRemember();
    studio.$("master-aac-player").pause();
    studio.homeFeature = null;
    studio.transport.deactivate();
  },
  open(container, call, selection, feature) {
    connectStudio(call);
    const homeFeature = feature ? { key: feature, selection } : null;
    const mounted = container.querySelector("lus-studio");
    if (mounted) {
      mounted.homeFeature = homeFeature;
      if (!mounted.imw.enabled()) mounted.transport.activate();
      mounted.transport.time(format(mounted.seconds));
      mounted.transport.sync();
      if (selection) queueMicrotask(() => void mounted.openHomeTarget(selection));
      else if (feature) queueMicrotask(() => mounted.showHomeFeature());
      return;
    }
    const studio = document.createElement("lus-studio");
    studio.homeTarget = selection;
    studio.homeFeature = homeFeature;
    studio.dataset.decodeRate = "48000";
    const links = container.querySelector(".wb-music-links");
    links.slot = "tools";
    studio.append(links);
    container.querySelector(".lus-workspace").append(studio);
  },
  dispose() {
    closeHome();
    const studio = document.querySelector("lus-studio");
    if (studio) { studio.stop(); studio.transport.deactivate(); clearAnalysis(studio); studio.coverController?.abort(); studio.disposeBus?.(); void studio.closeOutput(); }
  }
};
