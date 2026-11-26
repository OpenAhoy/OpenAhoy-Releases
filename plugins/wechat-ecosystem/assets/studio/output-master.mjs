import { audibleState } from "./studio-live-transport.mjs";
import { studioAction, studioFetch } from "./bridge.mjs";

export async function mountMasterControls(studio) {
  try {
    const {parameters} = await studioAction({action:"parameters"});
    studio.masterParameters = parameters;
    const pane = studio.$("master-values");
    for (const p of studio.masterParameters) {
      const label = document.createElement("label");
      const title = document.createElement("span");
      title.textContent = p.label + (p.unit ? " (" + p.unit + ")" : "");
      const control = document.createElement(p.id === 0 ? "select" : "input");
      control.id = "master-param-" + p.id;
      if (p.id === 0) {
        for (const [i, name] of p.values.entries()) control.add(new Option(name, i + p.minimum));
      } else if (p.id === 11) {
        control.type = "checkbox";
      } else {
        control.type = "number";
        control.min = String(p.minimum);
        control.max = String(p.maximum);
        control.step = [2,5,6,7].includes(p.id) ? "0.1" : "1";
        control.required = true;
      }
      label.append(title, control);
      pane.append(label);
    }
    pane.addEventListener("input", () => clearAnalysis(studio));
    studio.$("master-rate").addEventListener("change", () => clearAnalysis(studio));
    syncMasterControls(studio);
    studio.showHomeFeature();
  } catch {
    studio.$("master-engine-note").hidden = false;
  }
}

function selectedSettings(studio) {
  return studio.masterParameters.map(p => {
    const field = studio.$("master-param-" + p.id);
    if (p.id !== 11 && !field.reportValidity()) throw Error("请检查母带参数");
    return p.id === 11 ? Number(field.checked) : Number(field.value);
  });
}

function sourceNote(sources) {
  if (!sources?.length) return "原始素材来源未核实。";
  const bits = [...new Set(sources.map(s => s.bits))];
  const rates = [...new Set(sources.map(s => s.rate))];
  const hz = rates.map(n => n ? (n/1000) + " kHz" : "未知采样率").join("、");
  const depth = bits.map(n => n ? n + " 位" : "未知位深").join("、");
  return (sources.length > 1 ? "原始分轨 " : "原始音频 ") + depth + "，" + hz + "。";
}

function rateReason(mode) {
  return ({project:"工程声明", uniform_sources:"音源采样率一致", chosen_project_rate:"用户选择的工程采样率",
    mixed_sources:"多种原始采样率，请选择工程采样率",unknown_sources:"部分音源采样率未知，请选择工程采样率"})[mode] ?? "来源未知";
}

function showDelivery(studio, version) {
  studio.disposeBus?.();
  const monitor = studio.$("master-audition");
  monitor.hidden = !version.mastered || !version.previewAAC;
  const form = studio.$("master-rate-choice"), rate = studio.$("master-rate");
  const info = studio.$("master-delivery-info"), player = studio.$("master-aac-player");
  player.pause(); player.removeAttribute("src"); player.hidden = true;
  if (!monitor.hidden) setupAudition(studio, version);
  studio.$("master-export").hidden = true;
  studio.masterAnalysis = null;
  form.hidden = true;
  if (version.mastered) {
    if (!version.delivery) { info.textContent = "历史母带 · 原始格式"; return; }
    info.textContent = sourceNote(version.sourceMedia) + "工程 " + version.sampleRate/1000 + " kHz（" +
      rateReason(version.rateBasis) + "），混音母带处理后导出 24 位 PCM。响度目标 " + version.settings[2] +
      " LUFS 由项目自定。未提供 Apple Digital Masters 原始高分辨率来源证明或认证。";
    const qc = version.deliveryQC;
    if (qc?.pcm && qc.aac) info.textContent += " PCM " + qc.pcm.integrated_lufs + " LUFS-I / " +
      qc.pcm.true_peak_dbtp + " dBTP，AAC 解码后 " + qc.aac.true_peak_dbtp +
      " dBTP，削波 " + (qc.aac.on_sample+qc.aac.inter_sample) + "。交付增益 " + qc.gain_trim_db + " dB。";
    return;
  }
  const layout = version.masterRate;
  if (!layout) { info.textContent = "当前编排缺少媒体信息。"; return; }
  const lower = layout.rate && !layout.supported.includes(layout.rate);
  info.textContent = sourceNote(layout.sources) + rateReason(layout.basis) + "。" + (lower ?
    "此原始采样率不满足当前交付规格。" :
    "导出立体声 24 位 PCM，并核验 AAC 试听版。默认 −14 LUFS 是项目自定响度。");
  if (!layout.rate && ["mixed_sources", "unknown_sources"].includes(layout.basis)) {
    form.hidden = false;
    rate.replaceChildren(new Option("选择采样率",""),...layout.supported.map(n=>new Option(n/1000+" kHz",String(n))));
  }
}

export function syncMasterControls(studio) {
  const button = studio.$("output-master"), version = studio.version;
  button.hidden = !version || !!version.mastered || !!version.paintOnly || !!version.pending;
  button.disabled = !!studio.masterBusy || !studio.draft || !!studio.recoveryConflict;
  const panel = studio.$("master-settings");
  panel.hidden = !studio.masterParameters || !version?.tracks.length || !!version.pending || !!version.paintOnly;
  button.disabled ||= !studio.masterParameters || !!(version?.masterRate?.rate &&
    !version.masterRate.supported.includes(version.masterRate.rate));
  if (!panel.hidden && (studio.masterSelection !== studio.load || studio.masterPanelVersion !== version.id)) {
    studio.masterSelection = studio.load;
    studio.masterPanelVersion = version.id;
    const haveSnapshot = Array.isArray(version.settings);
    const missingSnapshot = version.mastered && !haveSnapshot;
    panel.open = false;
    showDelivery(studio, version);
    const fieldset = studio.$("master-values");
    fieldset.disabled = !!version.mastered;
    fieldset.hidden = !!missingSnapshot;
    studio.$("master-saved").textContent = missingSnapshot ? "此历史版未记录参数。"
      : version.mastered ? "此版本使用的设置" : "";
    for (const p of studio.masterParameters) {
      const value = haveSnapshot ? version.settings[p.id] : p.default;
      const input = studio.$("master-param-" + p.id);
      input.parentElement.hidden = !!version.mastered && (missingSnapshot || p.id >= version.settings.length);
      if (p.id === 11) input.checked = !!value;
      else input.value = String(value);
    }
  }
  const adopt = studio.$("master-adopt");
  adopt.hidden = !version?.mastered;
  adopt.disabled = studio.song?.explicit === version?.id;
  adopt.textContent = adopt.disabled ? "已采用" : "采用此母带";
  adopt.onclick = async () => {
    adopt.disabled = true;
    if (!await studio.adoptVersion(studio.project.id, studio.song.id, version.id)) adopt.disabled = false;
  };
  const download = studio.$("download-master");
  download.hidden = !version?.mastered;
  const aacLink = studio.$("download-aac");
  aacLink.hidden = !version?.previewAAC;
  if (version?.previewAAC) {
    aacLink.href = "#";
    aacLink.onclick = event => { event.preventDefault(); void downloadFile(studio, aacLink, version.previewAAC); };
    aacLink.download = studio.song.name + " - AAC.m4a";
  } else { aacLink.removeAttribute("href"); }
  if (version?.mastered) {
    download.textContent = version.delivery ? "下载 24 位 WAV" : "下载母带 WAV";
    download.href = "#";
    download.onclick = event => { event.preventDefault(); void downloadFile(studio, download, version.tracks[0].url); };
    download.download = studio.song.name + " - " + version.name + ".wav";
  } else {
    download.removeAttribute("href");
  }
}

export function clearAnalysis(studio, { continueStems = false } = {}) {
  if (!studio.masterAnalysis) return;
  const live = studio.liveMonitor?.run;
  const resume = continueStems && live && studio.playing;
  const clock = resume && !studio.busPending ? studio.clock : null;
  studio.masterAnalysis = null;
  studio.syncTrackMonitorControls?.();
  if (resume) {
    studio.seconds = studio.clockPosition();
    studio.stop(true);
  } else if (live) {
    studio.stopAndRemember();
  }
  studio.busBypass = false;
  studio.disposeBus?.();
  studio.$("master-audition").hidden = true;
  studio.$("master-export").hidden = true;
  studio.$("master-saved").textContent = "设置已变更。分析后可以试听和导出。";
  // The old PCM no longer describes the edited arrangement.
  // Keep the timeline anchor while the original lanes take over.
  if (resume && (studio.loopEnabled || studio.seconds < studio.length)) studio.play({ clock });
}

async function finishJob(studio, session, scope, request) {
  let result = request;
  for (let checks = 0; result.state === "running" && checks < 900; checks++) {
    await new Promise(resolve => setTimeout(resolve, 850));
    if (session !== studio.load || session.signal.aborted) return null;
    result = await studioAction({action:"master_status", ...scope, job:request.job});
  }
  if (result.state !== "ready") throw Error(result.error ?? "studio_master_unconfirmed");
  return result;
}

function reportFailure(studio, error) {
  studio.status(({draft_changed:"草稿已变化。保存当前编辑后再分析。",
    analysis_changed:"分轨或剪辑已变更，请重新分析当前编排。",
    studio_media_changed:"分轨原件已变化，请检查项目素材。",
    studio_master_busy:"本机已有母带任务进行中。",
    choose_project_rate:"请在母带设置中选择工程采样率。",
    studio_master_unconfirmed:"母带仍在处理，刷新歌单可检查结果。"})[error.message] ??
    "母带处理失败，原分轨和已采用版本仍可查看。");
}

export async function renderStudioMaster(studio) {
  if (studio.$("output-master").disabled || !studio.draft || studio.version?.mastered) return;
  const session = studio.load;
  studio.masterBusy = true;
  syncMasterControls(studio);
  clearAnalysis(studio);
  try {
    if (!await studio.save() || session !== studio.load) return;
    const { project, song, version, draft } = studio;
    const native = version.masterRate;
    const rate = native?.rate || Number(studio.$("master-rate").value);
    studio.$("master-settings").open = true;
    if (!native?.supported.includes(rate)) {
      studio.$("master-rate").focus();
      throw Error("choose_project_rate");
    }
    const scope = {project:project.id, song:song.id, version:version.id};
    const fieldset = studio.$("master-values");
    const settings = selectedSettings(studio), snapshot = audibleState(studio);
    fieldset.disabled = true;
    studio.$("master-rate").disabled = true;
    studio.status("正在分析 " + version.tracks.length + " 轨编排的 Stereo Out…");
    const request = await studioAction({action:"start_analysis", ...scope, revision:draft.revision, rate, settings});
    const result = await finishJob(studio,session,scope,request);
    if (!result || session !== studio.load || snapshot !== audibleState(studio)) return;
    const resume = studio.playing;
    if (resume) studio.stopAndRemember();
    studio.masterAnalysis = {id:result.id, analysis:result.id, session, scope, snapshot,
      frames:result.frames, sampleRate:result.sampleRate};
    studio.busBypass = false;
    studio.syncTrackMonitorControls?.();
    const monitor = studio.$("master-audition"), exportButton = studio.$("master-export");
    monitor.hidden = false;
    exportButton.hidden = false;
    studio.$("master-listen").onclick = () => void studio.toggle();
    const bypass = studio.$("master-bypass");
    bypass.disabled = false;
    bypass.setAttribute("aria-pressed","false");
    bypass.onclick = () => {
      studio.busBypass = !studio.busBypass;
      bypass.setAttribute("aria-pressed", String(studio.busBypass));
      studio.liveMonitor?.setBypass(studio.busBypass);
      studio.syncTrackMonitorControls?.();
    };
    if (resume) void studio.toggle();
    exportButton.onclick = () => void exportMaster(studio);
    studio.$("master-saved").textContent = "已分析当前编排";
    studio.status("Output Master 已就绪，可试听湿声、旁路或导出");
  } catch (error) {
    if (studio.load === session) reportFailure(studio,error);
  } finally {
    studio.masterBusy = false;
    studio.$("master-rate").disabled = false;
    if (studio.load === session) studio.$("master-values").disabled = !!studio.version.mastered;
    syncMasterControls(studio);
  }
}

async function exportMaster(studio) {
  const prepared = studio.masterAnalysis;
  if (!prepared || prepared.session !== studio.load || studio.masterBusy) return;
  const button = studio.$("master-export");
  button.disabled = true;
  studio.masterBusy = true;
  syncMasterControls(studio);
  try {
    if (!await studio.save() || prepared.session !== studio.load) return;
    studio.status("正在导出原生率 24 位 WAV，并核验 Apple AAC…");
    const response = await studioAction({action:"start_master", ...prepared.scope,
      revision:studio.draft.revision, analysis:prepared.id});
    const result = await finishJob(studio,prepared.session,prepared.scope,response);
    if (!result || prepared.session !== studio.load) return;
    await studio.refreshCatalog();
    if (prepared.session !== studio.load) return;
    await studio.change(prepared.scope.project,prepared.scope.song,result.id);
    studio.$("master-settings").open = true;
    studio.status("Output Master · 24 位 WAV 和 AAC 已核验");
  } catch (error) {
    if (studio.load === prepared.session) reportFailure(studio,error);
  } finally {
    button.disabled = false;
    studio.masterBusy = false;
    syncMasterControls(studio);
  }
}

async function downloadFile(studio, link, path) {
  if (link.dataset.busy) return;
  const session = studio.load;
  const old = link.textContent;
  link.dataset.busy = "true";
  link.textContent = "读取文件中…";
  try {
    const result = await studioFetch(path, {signal:session.signal});
    if (!result.ok) throw Error();
    const url = URL.createObjectURL(await result.blob());
    const download = document.createElement("a");
    download.href = url;
    download.download = link.download;
    studio.shadowRoot.append(download);
    download.click();
    download.remove();
    setTimeout(() => URL.revokeObjectURL(url), 60000);
  } catch {
    if (!session.signal.aborted) studio.status("无法读取下载，请重试。");
  } finally {
    delete link.dataset.busy;
    if (studio.load === session) link.textContent = old;
  }
}

function setupAudition(studio, version) {
  studio.$("master-listen").textContent = "试听总线";
  const player = studio.$("master-aac-player"), listen = studio.$("master-listen"), bypass = studio.$("master-bypass");
  const controller = new AbortController();
  const sources = new Map();
  let epoch = 0, dry = false, desired = false;
  bypass.setAttribute("aria-pressed", "false");
  bypass.disabled = !version.bypassAAC;
  player.onplay = () => { if (studio.playing) studio.pause(); };
  async function choose(next, autoplay) {
    const observed = ++epoch;
    desired = next;
    const offset = player.currentTime || 0;
    try {
      const url = next ? version.bypassAAC : version.previewAAC;
      if (!sources.has(url)) {
        const reply = await studioFetch(url, {signal:controller.signal});
        if (!reply.ok) throw Error();
        const blob = await reply.blob();
        if (controller.signal.aborted) return;
        if (!sources.has(url)) sources.set(url, URL.createObjectURL(blob));
      }
      if (observed !== epoch || controller.signal.aborted) return;
      dry = next;
      bypass.setAttribute("aria-pressed", String(dry));
      player.hidden = false;
      if (player.src !== sources.get(url)) {
        player.src = sources.get(url);
        player.currentTime = offset;
      }
      if (autoplay) {
        try { await player.play(); }
        catch { studio.status("请点播放器的播放键开始试听。"); }
      }
    } catch {
      if (observed === epoch && !controller.signal.aborted) {
        desired = dry;
        studio.status("试听文件暂不可用。");
      }
    }
  }
  listen.onclick = () => void choose(dry, true);
  bypass.onclick = () => void choose(!desired, !player.paused);
  studio.disposeBus = () => {
    controller.abort();
    player.pause();
    player.removeAttribute("src");
    player.load();
    for (const source of sources.values()) URL.revokeObjectURL(source);
  };
}
