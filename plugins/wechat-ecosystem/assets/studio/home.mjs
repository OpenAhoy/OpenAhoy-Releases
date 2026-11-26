import { studioAction, studioCover, studioFetch } from "./bridge.mjs";
import { projectArtwork } from "./mec-art.mjs";
import { mountSongTransport } from "./transport.mjs";
import masterArtwork from "./home-output-master-hero.webp";
import featureSignal from "./home-feature-signal.json";

const keyPrefix = "jiusera.lus.project.";
const takeKey = (project, song) => "version-" + project + "/" + song;
const unsavedPreferences = new Map();
export function readPreference(key, fallback) {
  if (unsavedPreferences.has(key)) return unsavedPreferences.get(key);
  try { return JSON.parse(localStorage.getItem(keyPrefix + key)) ?? fallback; }
  catch { return fallback; }
}
export function rememberPreference(key, value) {
  try {
    localStorage.setItem(keyPrefix + key, JSON.stringify(value));
    unsavedPreferences.delete(key);
  } catch { unsavedPreferences.set(key, value); }
}

function preferredVersion(project, song) {
  if (!song) return null;
  const saved = readPreference(takeKey(project.id, song.id), "");
  return song.versions.find(version => version.id === saved)
    ?? song.versions.find(version => version.id === song.adopted) ?? song.versions[0] ?? null;
}

function selection(project, song, version) {
  return project && song && version ? { project: project.id, song: song.id, version: version.id } : null;
}

function savedProject(projects) {
  const wanted = readPreference("recent-project", "");
  return projects.find(project => project.id === wanted) ?? null;
}

function savedSong(project) {
  const wanted = readPreference("song-" + project.id, "");
  return project.songs.find(song => song.id === wanted) ?? null;
}

function rememberChoice(project, song, version) {
  rememberPreference("recent-project", project.id);
  if (song) rememberPreference("song-" + project.id, song.id);
  if (version) rememberPreference(takeKey(project.id, song.id), version.id);
}

function node(tag, text = "", className = "") {
  const element = document.createElement(tag);
  element.textContent = text;
  if (className) element.className = className;
  return element;
}
function button(text, invoke, className) {
  const element = node("button", text, className);
  element.type = "button";
  element.onclick = invoke;
  return element;
}

async function catalog() {
  const reply = await studioFetch("/catalog");
  if (!reply.ok) throw Error("目录不可读取");
  const projects = await reply.json();
  if (!Array.isArray(projects)) throw Error("项目目录无效");
  return projects;
}

class MusicPage {
  constructor(container, title, titleId, navigation, audio) {
    this.container = container;
    this.navigation = navigation;
    this.projects = [];
    this.coverRequests = new Set();
    const heading = node("h1", title);
    heading.id = titleId;
    heading.tabIndex = -1;
    this.status = node("p", "", "lh-status");
    this.status.setAttribute("role", "status");
    this.content = node("div", "", "lh-content");
    container.classList.add("lh");
    for (const child of [...container.childNodes]) if (child !== audio) child.remove();
    container.prepend(heading, this.status, this.content);
  }

  async activate(navigation) {
    this.navigation = navigation;
    const request = this.request = {};
    this.status.textContent = "正在读取登记项目…";
    try {
      const projects = await catalog();
      if (request !== this.request) return;
      this.projects = projects;
      this.status.textContent = "";
      this.render();
    } catch {
      if (request !== this.request) return;
      this.projects = [];
      this.audition?.clear();
      this.content.replaceChildren();
      this.status.textContent = "暂时无法读取音乐项目。";
      this.content.append(button("重试", () => void this.activate(this.navigation)));
    }
  }

  close() {
    this.request = null;
    this.releaseCovers();
  }

  releaseCovers(requests = this.coverRequests) {
    for (const request of requests) {
      request.abort();
      if (request.url) URL.revokeObjectURL(request.url);
    }
    requests.clear();
  }

  async loadCover(image, source, requests = this.coverRequests) {
    const request = new AbortController();
    requests.add(request);
    try {
      const url = await studioCover(source, request.signal);
      if (!url) return;
      if (request.signal.aborted || !image.isConnected) URL.revokeObjectURL(url);
      else image.src = request.url = url;
    } catch { /* Song artwork is optional. */ }
  }
  assetAction() { return button("打开音频资产", () => this.navigation.openAssets?.()); }
}

function featureSelection(projects, feature) {
  const current = savedProject(projects);
  const ordered = current ? [current, ...projects.filter(project => project !== current)] : projects;
  for (const project of ordered) {
    const saved = savedSong(project);
    const songs = saved ? [saved, ...project.songs.filter(song => song !== saved)] : project.songs;
    for (const song of songs) {
      const preferred = preferredVersion(project, song);
      const options = [preferred, ...song.versions.filter(version => version !== preferred)];
      const version = options.find(item => item && !item.mastered && !item.paintOnly && !item.pending
        && item.tracks.length >= (feature === "solo" ? 2 : 1));
      if (version) return selection(project, song, version);
    }
  }
  return null;
}

function waveStrip(peaks) {
  const waveform = node("span", "", "lh-wave-strip");
  waveform.setAttribute("aria-hidden", "true");
  for (const peak of peaks) {
    const bar = node("i");
    bar.style.height = peak + "%";
    waveform.append(bar);
  }
  return waveform;
}

function promoAction(navigation, projects, key, title) {
  const target = featureSelection(projects, key);
  const action = button(title, () => navigation.openStudio?.(target, key), "lh-feature-link");
  action.disabled = !target;
  if (!target) action.title = "请先登记可用的音乐项目";
  return action;
}

function masterPromotion(navigation, projects) {
  const card = node("article", "", "lh-feature lh-master-promo");
  const art = new Image();
  art.alt = "";
  art.src = masterArtwork;
  art.className = "lh-master-art";
  const copy = node("div", "", "lh-master-copy");
  copy.append(node("p", "Stereo Out", "lh-master-path"), node("h3", "Output Master"),
    node("p", "比较处理前后，核验试听与交付。", "lh-master-summary"),
    promoAction(navigation, projects, "master", "打开母带工作台"));
  const scope = node("div", "", "lh-master-scope");
  scope.setAttribute("aria-label", "同一段合成音频的实际母带处理前后");
  scope.append(node("p", "示例信号", "lh-scope-label"));
  for (const [mode,label] of [["bypass","处理前"],["wet","处理后"]]) {
    const reading = featureSignal.master[mode];
    const row = node("div", "", "lh-scope-row lh-scope-" + mode);
    row.append(node("span", label), waveStrip(reading.bars),
      node("span", reading.peak.toFixed(1).replace("-", "−") + " dBTP"));
    scope.append(row);
  }
  card.append(art, copy, scope);
  return card;
}

function soloPromotion(navigation, projects) {
  const card = node("article", "", "lh-feature lh-solo-promo");
  const copy = node("div", "", "lh-solo-copy");
  copy.append(node("h3", "逐轨独听"), node("p", "独听旋律，静音其余轨道。"),
    promoAction(navigation, projects, "solo", "打开分轨控制"));
  const timeline = node("div", "", "lh-solo-timeline");
  timeline.setAttribute("aria-hidden", "true");
  for (const [index,peaks] of featureSignal.stems.entries()) {
    const row = node("div", "", "lh-solo-row");
    row.append(node("span", index === 0 ? "S" : "M"), waveStrip(peaks));
    timeline.append(row);
  }
  card.append(copy, timeline);
  return card;
}

function compactPromotion(kind, title, description, label, invoke, enabled) {
  const card = node("article", "", "lh-feature lh-compact-promo lh-" + kind + "-promo");
  const copy = node("div", "", "lh-compact-copy");
  const control = button(label, invoke, "lh-feature-link");
  control.disabled = !enabled;
  copy.append(node("h3", title), node("p", description), control);
  const visual = kind === "trim" ? waveStrip(featureSignal.stems[0]) : node("span", "", "lh-take-sheets");
  visual.setAttribute("aria-hidden", "true");
  card.append(copy, visual);
  return card;
}

const moduleBanners = [
  { feature: "master", title: "Output Master", detail: "试听母带处理前后" },
  { feature: "solo", title: "逐轨独听", detail: "单独听清编排中的每条轨道" },
];

function recentSongs(projects) {
  const rows = [];
  for (const project of projects) {
    for (const song of project.songs) {
      let newest;
      for (const version of song.versions) {
        const date = version.generatedAt ?? version.archivedAt;
        const path = previewPath(version);
        if (!version.mastered && !version.sourceVersion && path && Number.isFinite(date) && date > 0
            && (!newest || date > newest.date || date === newest.date && version.id < newest.version.id)) {
          newest = { project, song, version, date, path };
        }
      }
      if (newest) rows.push(newest);
    }
  }
  return rows.sort((a, b) => b.date - a.date || a.path.localeCompare(b.path));
}

class Overview extends MusicPage {
  constructor(container, navigation, audition) {
    super(container, "L-unify", "wbMusicHomeTitle", navigation);
    this.container.classList.add("lh-project-home");
    this.projectOffset = 0;
    this.recentOffset = 0;
    this.audition = audition;
  }

  auditionChoice() { return this.audition.choice; }

  auditionChanged() {
    for (const control of this.recentCards?.children ?? []) {
      const chosen = control.dataset.path === this.audition.choice?.path;
      const playing = chosen && !this.audition.audio.paused;
      const loading = chosen && this.audition.pending;
      control.toggleAttribute("data-chosen", chosen);
      control.setAttribute("aria-pressed", String(Boolean(playing)));
      const state = loading ? "正在读取" : playing ? "暂停试听" : "试听";
      control.setAttribute("aria-label", state + " " + control.dataset.songLabel);
      control.querySelector(".lh-recent-play").textContent = loading ? "…" : playing ? "Ⅱ" : "▶";
    }
  }

  renderBanner() {
    const config = this.navigation.homeBanners ?? moduleBanners;
    const slides = Array.isArray(config) && config.filter(item => item
      && ["master", "solo"].includes(item.feature) && typeof item.title === "string" && item.title.trim()
      && typeof item.detail === "string");
    if (!slides?.length) return null;
    const banner = node("section", "", "lh-banner");
    banner.setAttribute("aria-label", "L-unify 功能动态");
    const panels = node("div", "", "lh-banner-panels");
    const controls = node("div", "", "lh-banner-controls");
    let index = 0;
    const select = value => {
      index = value;
      for (const [at, panel] of [...panels.children].entries()) panel.hidden = at !== index;
      for (const [at, control] of [...controls.children].entries()) control.setAttribute("aria-pressed", String(at === index));
    };
    for (const [at, slide] of slides.entries()) {
      const target = featureSelection(this.projects, slide.feature);
      const panel = target ? button("", () => this.navigation.openStudio?.(target, slide.feature)) : node("div");
      panel.className = "lh-banner-slide";
      panel.dataset.feature = slide.feature;
      const message = node("span", "", "lh-banner-message");
      message.append(node("strong", slide.title), node("span", slide.detail));
      panel.append(message, waveStrip(slide.feature === "master" ? featureSignal.master.wet.bars : featureSignal.stems[0]));
      panels.append(panel);
      if (slides.length > 1) {
        const dot = button("", () => select(at));
        dot.setAttribute("aria-label", slide.title);
        controls.append(dot);
      }
    }
    banner.append(panels, controls);
    select(0);
    if (slides.length > 1) {
      const reduced = matchMedia("(prefers-reduced-motion: reduce)");
      this.bannerTimer = setInterval(() => {
        if (!document.hidden && !reduced.matches && !banner.matches(":hover,:focus-within")) {
          select((index + 1) % slides.length);
        }
      }, 6500);
    }
    return banner;
  }

  recentCard(row) {
    const card = button("", () => {
      this.status.textContent = "";
      rememberChoice(row.project, row.song, row.version);
      void this.audition.toggle(row);
    }, "lh-recent-card");
    card.dataset.path = row.path;
    card.dataset.songLabel = row.song.name + " · " + row.project.name + " · " + row.version.name;
    card.title = card.dataset.songLabel;
    const art = node("span", "", "lh-recent-art");
    art.innerHTML = projectArtwork(row.project.id);
    const cover = row.version.cover ?? row.project.cover;
    if (cover) {
      const image = new Image();
      image.alt = "";
      image.onerror = () => image.remove();
      art.append(image);
      void this.loadCover(image, cover, this.recentCovers);
    }
    const text = node("span", "", "lh-recent-name");
    text.append(node("strong", row.song.name), node("small", row.project.name + " · " + row.version.name));
    const play = node("span", "", "lh-recent-play");
    play.setAttribute("aria-hidden", "true");
    const plane = node("span", "", "lh-recent-plane jiu-card-motion-plane");
    plane.append(art, text, play);
    card.append(plane);
    return card;
  }

  mountRecent(section, rows) {
    const heading = node("header", "", "lh-recent-heading");
    heading.append(node("h2", "最近生成"));
    section.append(heading);
    if (!rows.length) {
      section.append(node("p", "暂无可试听的新曲。", "lh-recent-empty"));
      this.recentCards = null;
      return;
    }
    const gallery = this.recentCards = node("div", "", "lh-recent-grid");
    this.recentCovers = new Set();
    gallery.id = "lh-recent-grid";
    const pager = node("nav", "", "lh-recent-pages");
    pager.setAttribute("aria-label", "最近生成分页");
    const readout = node("span");
    readout.setAttribute("aria-live", "polite");
    let page = 0, capacity = 1, shown = "";
    const turn = direction => {
      const offset = (page + direction) * capacity;
      if (offset < 0 || offset >= rows.length) return;
      this.recentOffset = offset;
      layout();
    };
    const previous = button("‹", () => turn(-1)), next = button("›", () => turn(1));
    for (const [control, label] of [[previous, "上一页新曲"], [next, "下一页新曲"]]) {
      control.setAttribute("aria-label", label);
      control.setAttribute("aria-controls", gallery.id);
    }
    pager.append(previous, readout, next);
    heading.append(pager);
    section.append(gallery);
    const layout = () => {
      const width = section.clientWidth;
      if (!width) return;
      const columns = width >= 510 ? 3 : width >= 320 ? 2 : 1;
      const gap = parseFloat(getComputedStyle(gallery).rowGap);
      const height = section.clientHeight - heading.offsetHeight - gap;
      const rowsIn = room => Math.max(1, Math.min(3, Math.floor((room + gap) / (46 + gap))));
      capacity = columns * rowsIn(height);
      const pages = Math.ceil(rows.length / capacity);
      pager.hidden = pages === 1;
      page = Math.min(pages - 1, Math.floor(this.recentOffset / capacity));
      const start = page * capacity, end = Math.min(rows.length, start + capacity);
      const visibleRows = Math.ceil((end - start) / columns);
      const cardHeight = (height + gap) / visibleRows - gap;
      gallery.style.setProperty("--lh-recent-columns", columns);
      gallery.style.setProperty("--lh-recent-rows", visibleRows);
      gallery.style.setProperty("--lh-recent-cover", Math.max(36, Math.min(72, Math.floor(cardHeight - 12))) + "px");
      previous.setAttribute("aria-disabled", String(page === 0));
      next.setAttribute("aria-disabled", String(page === pages - 1));
      const label = (page + 1) + " / " + pages;
      if (readout.textContent !== label) readout.textContent = label;
      if (shown === start + ":" + end) return;
      shown = start + ":" + end;
      const focusedPath = gallery.contains(document.activeElement) && document.activeElement.dataset.path;
      this.releaseCovers(this.recentCovers);
      gallery.replaceChildren(...rows.slice(start, end).map(row => this.recentCard(row)));
      if (focusedPath) {
        const replacement = Array.from(gallery.children).find(card => card.dataset.path === focusedPath);
        (replacement ?? gallery.firstElementChild)?.focus({ preventScroll: true });
      }
      this.auditionChanged();
    };
    this.recentSize = new ResizeObserver(layout);
    this.recentSize.observe(section);
  }

  projectCard(project) {
    const card = button("", () => this.navigation.openSongs?.(project.id), "lh-project-card");
    card.dataset.project = project.id;
    card.setAttribute("aria-label", "进入项目 " + project.name);
    card.title = project.name;
    const picture = node("span", "", "lh-project-art");
    picture.innerHTML = projectArtwork(project.id);
    picture.firstElementChild.setAttribute("preserveAspectRatio", "xMidYMid slice");
    if (project.cover) {
      const art = new Image();
      art.alt = "";
      art.onerror = () => art.remove();
      picture.append(art);
      void this.loadCover(art, project.cover);
    }
    const title = node("span", "", "lh-project-label");
    const names = node("span", "", "lh-project-name");
    names.append(node("strong", project.name));
    const style = project.songs[0]?.category;
    if (style && project.songs.every(song => song.category === style)) names.append(node("small", style));
    title.append(names, node("span", project.songs.length + " 首", "lh-project-track-count"));
    const plane = node("span", "", "lh-project-plane jiu-card-motion-plane");
    plane.append(picture, title);
    card.append(plane);
    return card;
  }

  mountGallery(projects, heading) {
    const gallery = node("div", "", "lh-project-grid");
    gallery.id = "lh-project-grid";
    const pager = node("nav", "", "lh-project-pages");
    pager.setAttribute("aria-label", "音乐项目分页");
    const pageLabel = node("span");
    pageLabel.setAttribute("aria-live", "polite");
    let page = 0, capacity = 1, paintedStart = -1, paintedEnd = -1;
    const move = direction => {
      const next = (page + direction) * capacity;
      if (next < 0 || next >= this.projects.length) return;
      this.projectOffset = next;
      layout();
    };
    const previous = button("‹", () => move(-1));
    const next = button("›", () => move(1));
    for (const [control, name] of [[previous, "上一页项目"], [next, "下一页项目"]]) {
      control.setAttribute("aria-label", name);
      control.setAttribute("aria-controls", gallery.id);
    }
    pager.append(previous, pageLabel, next);
    projects.append(gallery, pager);

    const layout = () => {
      const width = projects.clientWidth;
      if (!width) return;
      const columns = width >= 540 ? 4 : width >= 410 ? 3 : width >= 190 ? 2 : 1;
      const gap = parseFloat(getComputedStyle(gallery).rowGap);
      const space = projects.clientHeight - heading.offsetHeight - gap;
      const minCardHeight = 112;
      const maxRows = 3;
      const idealRows = Math.min(2, Math.ceil(this.projects.length / columns));
      projects.style.setProperty("--lh-project-ideal",
        heading.offsetHeight + idealRows * (142 + gap) + (this.projects.length > columns * idealRows ? 38 + gap : 0) + "px");
      const rowsIn = height => Math.max(1, Math.min(maxRows, Math.floor((height + gap) / (minCardHeight + gap))));
      const needsPages = this.projects.length > columns * rowsIn(space);
      pager.hidden = !needsPages;
      const cardSpace = space - (needsPages ? pager.offsetHeight + gap : 0);
      capacity = columns * rowsIn(cardSpace);
      const pages = Math.ceil(this.projects.length / capacity);
      page = Math.min(pages - 1, Math.floor(this.projectOffset / capacity));
      const start = page * capacity;
      const end = Math.min(this.projects.length, start + capacity);
      const rows = Math.ceil((end - start) / columns);
      const height = Math.min(142, Math.floor((cardSpace + gap) / rows - gap));
      gallery.style.setProperty("--lh-project-columns", columns);
      gallery.style.setProperty("--lh-project-height", Math.max(0, height) + "px");
      previous.setAttribute("aria-disabled", String(page === 0));
      next.setAttribute("aria-disabled", String(page + 1 === pages));
      pageLabel.textContent = (page + 1) + " / " + pages;
      if (start === paintedStart && end === paintedEnd) return;
      paintedStart = start;
      paintedEnd = end;
      const focusedProject = gallery.contains(document.activeElement) && document.activeElement.dataset.project;
      this.releaseCovers();
      gallery.replaceChildren(...this.projects.slice(start, end).map(project => this.projectCard(project)));
      if (focusedProject) {
        const replacement = Array.from(gallery.children).find(card => card.dataset.project === focusedProject);
        (replacement ?? gallery.firstElementChild)?.focus({ preventScroll: true });
      }
    };
    this.gallerySize = new ResizeObserver(layout);
    this.gallerySize.observe(projects);
  }

  render() {
    this.gallerySize?.disconnect();
    this.recentSize?.disconnect();
    clearInterval(this.bannerTimer);
    this.releaseCovers();
    this.releaseCovers(this.recentCovers);
    const current = this.audition.choice;
    if (current) {
      const project = this.projects.find(row => row.id === current.project.id);
      const song = project?.songs.find(row => row.id === current.song.id);
      const version = song?.versions.find(row => row.id === current.version.id);
      if (previewPath(version) !== current.path) this.audition.clear();
    }
    const page = node("section", "", "lh-project-layout");
    page.dataset.pane = "projects";
    const projects = node("section", "", "lh-projects");
    projects.id = "lh-projects-pane";
    const heading = node("div", "", "lh-project-heading");
    const title = node("h2", "我的项目");
    title.append(node("span", String(this.projects.length), "lh-project-count"));
    heading.append(title, button("刷新", () => void this.activate(this.navigation), "lh-project-refresh"));
    projects.append(heading);
    const updates = node("aside", "", "lh-feature-list");
    updates.id = "lh-features-pane";
    updates.append(node("h2", "IMW 功能"));
    const mosaic = node("div", "", "lh-feature-grid");
    mosaic.id = "lh-feature-grid";
    mosaic.dataset.feature = "master";
    const trim = featureSelection(this.projects, "trim");
    const inUse = savedProject(this.projects);
    const forSongs = inUse?.songs.length ? inUse : this.projects.find(project => project.songs.length);
    const features = [
      ["master", masterPromotion(this.navigation, this.projects)],
      ["solo", soloPromotion(this.navigation, this.projects)],
      ["trim", compactPromotion("trim", "选区剪辑", "从两端自由裁选区", "打开编辑器",
        () => this.navigation.openStudio?.(trim), trim)],
      ["versions", compactPromotion("versions", "歌曲版本", "切换试听与分轨版本", "查看版本",
        () => this.navigation.openSongs?.(forSongs.id), forSongs)],
    ];
    for (const [key, panel] of features) {
      const slot = node("div", "", "lh-feature-slot");
      slot.dataset.feature = key;
      panel.classList.add("jiu-card-motion-plane");
      slot.append(panel);
      mosaic.append(slot);
    }
    const featurePages = node("nav", "", "lh-feature-pages");
    featurePages.setAttribute("aria-label", "IMW 功能分页");
    for (const [key, label] of [["master", "母带"], ["solo", "独听"], ["trim", "剪辑"], ["versions", "版本"]]) {
      const toggle = button(label, () => {
        mosaic.dataset.feature = key;
        for (const item of featurePages.children) item.setAttribute("aria-pressed", String(item === toggle));
      });
      toggle.setAttribute("aria-controls", mosaic.id);
      toggle.setAttribute("aria-pressed", String(mosaic.dataset.feature === key));
      featurePages.append(toggle);
    }
    updates.append(featurePages, mosaic);

    const sections = node("nav", "", "lh-home-sections");
    sections.setAttribute("aria-label", "L-unify 首页区域");
    const library = node("div", "", "lh-home-library");
    const recent = node("section", "", "lh-recent");
    recent.id = "lh-recent-pane";
    const rows = recentSongs(this.projects);
    library.toggleAttribute("data-new-songs", rows.length > 0);
    library.append(projects, recent);
    for (const [key, label, panel] of [["projects", "项目", projects], ["recent", "最近生成", recent], ["features", "IMW 功能", updates]]) {
      const toggle = button(label, () => {
        page.dataset.pane = key;
        for (const item of sections.children) item.setAttribute("aria-pressed", String(item === toggle));
      });
      toggle.setAttribute("aria-controls", panel.id);
      toggle.setAttribute("aria-pressed", String(page.dataset.pane === key));
      toggle.dataset.pane = key;
      sections.append(toggle);
    }
    const banner = this.renderBanner();
    if (banner) page.append(banner);
    page.append(sections, library, updates);
    this.content.replaceChildren(page);
    if (this.projects.length) this.mountGallery(projects, heading);
    else projects.append(node("p", "尚无登记的音乐项目。", "mec-empty"), this.assetAction());
    this.mountRecent(recent, rows);
  }

  close() {
    this.gallerySize?.disconnect();
    this.recentSize?.disconnect();
    clearInterval(this.bannerTimer);
    this.releaseCovers(this.recentCovers);
    super.close();
  }
}

function previewPath(version) {
  if (!version || version.pending || version.paintOnly) return "";
  if (version.previewAAC) return version.previewAAC;
  const track = version.tracks.length === 1 && version.tracks[0];
  if (!track || track.start !== 0 || track.sourceIn !== 0) return "";
  return track.mediaType === "audio/wav" ? track.url.replace(/^\/source\//, "/song-preview/") : track.url;
}

class SongAudition {
  constructor(document) {
    this.audio = document.createElement("audio");
    this.audio.preload = "none";
    this.audio.hidden = true;
    this.audio.setAttribute("aria-hidden", "true");
    for (const event of ["loadedmetadata", "timeupdate", "pause", "play", "ended", "seeked"]) {
      this.audio.addEventListener(event, () => { if (this.url) this.sync(); });
    }
    this.transport = mountSongTransport({
      audio: this.audio,
      toggle: () => {
        if (this.pending) {
          this.clear(true);
          return;
        }
        const choice = this.page?.auditionChoice();
        if (previewPath(choice?.version)) void this.toggle(choice);
      },
      stop: () => {
        if (this.pending) this.clear(true);
        else {
          this.audio.pause();
          if (this.audio.hasAttribute("src")) this.audio.currentTime = 0;
          this.sync();
        }
      },
    });
  }

  activate(page) {
    this.page = page;
    this.transport.activate();
    this.sync();
  }

  deactivate() {
    this.clear();
    this.page = null;
    this.transport.deactivate();
  }

  sync() {
    this.page?.auditionChanged();
    this.transport.sync({ available: Boolean(previewPath(this.page?.auditionChoice()?.version)), loading: Boolean(this.pending) });
  }

  clear(keepChoice = false) {
    this.pending?.abort();
    this.pending = null;
    if (!keepChoice) this.choice = null;
    this.releaseSource();
    this.sync();
  }

  releaseSource() {
    const url = this.url;
    this.url = null;
    if (this.audio.hasAttribute("src")) {
      this.audio.pause();
      this.audio.removeAttribute("src");
      this.audio.load();
    }
    if (url) URL.revokeObjectURL(url);
  }

  async toggle({ project, song, version }) {
    const path = previewPath(version);
    if (!path || (path === this.choice?.path && this.pending)) return;
    const failed = choice => {
      if (this.page && choice === this.choice) this.page.status.textContent = "暂时无法试听此版本。";
    };
    if (path === this.choice?.path && this.audio.hasAttribute("src")) {
      const choice = this.choice;
      if (!this.audio.paused) this.audio.pause();
      else await this.audio.play().catch(() => failed(choice));
      return;
    }
    this.pending?.abort();
    const choice = this.choice = { project, song, version, path };
    const request = this.pending = new AbortController();
    this.releaseSource();
    this.sync();
    try {
      const response = await studioFetch(path, { signal: request.signal });
      if (!response.ok) throw Error("预览不可读");
      const blob = await response.blob();
      if (this.pending !== request) return;
      this.url = URL.createObjectURL(blob);
      this.audio.src = this.url;
      await this.audio.play();
    } catch {
      if (this.pending === request) {
        this.releaseSource();
        failed(choice);
      }
    } finally {
      if (this.pending === request) {
        this.pending = null;
        this.sync();
      }
    }
  }
}

const songSorts = [
  ["original", "原顺序"], ["recent", "最近更新"], ["oldest", "最早更新"],
  ["name", "名称 A–Z"], ["reverse", "名称 Z–A"],
];

const byName = new Intl.Collator("zh-CN", { numeric: true });

function selectField(id, label, options) {
  const field = node("select");
  field.id = id;
  field.setAttribute("aria-label", label);
  for (const [value, title] of options) field.add(new Option(title, value));
  return field;
}

class SongLibrary extends MusicPage {
  constructor(container, navigation, audition) {
    super(container, "歌曲列表", "wbMusicSongsTitle", navigation, audition.audio);
    this.container.classList.add("mec-song-library");
    this.audition = audition;
    this.openedProject = readPreference("mec-library-project", "");
    this.songOrder = "original";
    this.query = "";
    this.category = "";
  }

  current() {
    if (this.switchingProject) return {};
    const project = this.projects.find(item => item.id === this.openedProject);
    const song = project && (savedSong(project) ?? project.songs[0]);
    return { project, song, version: project && preferredVersion(project, song) };
  }

  selected() {
    const { project, song, version } = this.current();
    return selection(project, song, version);
  }

  auditionChoice() {
    const choice = this.audition.choice;
    return this.switchingProject && choice?.project.id === this.requestedProject ? choice : this.current();
  }

  choose(project, song, version) {
    rememberChoice(project, song, version);
  }

  openProject(project) {
    this.navigation.openSongs?.(project.id);
  }

  prepareProject(project) {
    this.requestedProject = project;
    this.switchingProject = true;
    this.releaseCovers();
    this.content.replaceChildren();
    this.cards = null;
    if (this.audition.choice?.project.id !== project) this.audition.clear();
  }

  render() {
    this.releaseCovers();
    const focus = document.activeElement;
    const requested = this.projects.find(item => item.id === this.requestedProject);
    this.requestedProject = null;
    this.switchingProject = false;
    const project = requested ?? this.current().project ?? savedProject(this.projects) ?? this.projects[0];
    if (project && project.id !== this.openedProject) {
      this.openedProject = project.id;
      this.query = "";
      this.category = "";
      this.choose(project);
      rememberPreference("mec-library-project", project.id);
      this.container.scrollTop = 0;
    }
    const { song, version } = this.current();
    if (this.audition.choice && this.audition.choice.path !== previewPath(version)) this.audition.clear();
    this.content.replaceChildren();
    if (project) this.renderWorkspace(project, song, version, focus);
    else this.content.append(node("p", "尚无登记的音乐项目。", "mec-empty"), this.assetAction());
    this.audition.sync();
  }

  renderWorkspace(project, song, version, focus) {
    const heading = node("div", "", "mec-workspace-heading");
    const back = button("‹", () => this.navigation.openHome?.(), "project-pill mec-back");
    back.setAttribute("aria-label", "返回 L-unify 项目首页");
    heading.append(back, node("h2", project.name), node("span", project.songs.length + " 首歌曲"),
      button("刷新歌单", () => void this.activate(this.navigation), "project-pill"));
    const workspace = node("section", "", "workspace");
    workspace.id = "studioWorkspace";
    const sidebar = node("nav");
    sidebar.id = "studioSidebar";
    sidebar.setAttribute("aria-label", "项目列表");
    for (const item of this.projects) {
      const entry = button(item.name, () => { if (item !== project) this.openProject(item); }, "project-pill");
      entry.dataset.project = item.id;
      entry.setAttribute("aria-pressed", String(item === project));
      sidebar.append(entry);
    }
    const list = node("section", "", "song-workspace");
    const filters = node("div", "", "workspace-controls");
    const switcher = selectField("studioProjectSelect", "切换项目", this.projects.map(item => [item.id, item.name]));
    switcher.value = project.id;
    switcher.onchange = () => this.openProject(this.projects.find(item => item.id === switcher.value));
    const projectControls = node("div", "", "mec-mobile-project");
    const lyricsJump = button("歌词", () => {
      this.details.scrollIntoView({ block: "start" });
      this.details.focus({ preventScroll: true });
    }, "project-pill");
    lyricsJump.id = "studioLyricsJump";
    lyricsJump.setAttribute("aria-controls", "studioLyrics");
    lyricsJump.disabled = !song;
    projectControls.append(switcher, lyricsJump);
    const toolbar = node("div", "", "song-list-controls");
    const search = node("input");
    search.id = "studioSearch";
    search.type = "search";
    search.value = this.query;
    search.placeholder = "搜索当前项目歌曲或歌词";
    search.setAttribute("aria-label", "搜索歌曲");
    const sort = selectField("studioSongSort", "歌曲排序", songSorts);
    sort.value = this.songOrder;
    const sortLabel = node("label", "排序", "song-sort");
    sortLabel.append(sort);
    toolbar.append(search, sortLabel);
    filters.append(projectControls, toolbar);
    this.cards = node("div");
    this.cards.id = "studioSongs";
    this.details = node("aside", "", "lh-details");
    this.details.id = "studioLyrics";
    this.details.tabIndex = -1;
    const categories = this.categoryControls(project, () => this.renderSongs(project, song));
    list.append(filters, categories, this.cards);
    workspace.append(sidebar, list, this.details);
    this.content.append(heading, workspace);
    search.oninput = () => { this.query = search.value; this.renderSongs(project, song); };
    sort.onchange = () => { this.songOrder = sort.value; this.renderSongs(project, song); };
    this.renderSongs(project, song);
    if (song) this.renderDetails(project, song, version);
    if (focus?.id === "lh-version") this.details.querySelector("#lh-version")?.focus({ preventScroll:true });
    else if (focus?.closest(".lh-card")) {
      const id = focus.closest(".lh-card").dataset.song;
      const card = [...this.cards.children].find(item => item.dataset.song === id);
      card?.querySelector(focus.classList.contains("lh-cover") ? ".lh-cover" : ".lh-song-pick")?.focus({ preventScroll:true });
    }
  }

  categoryControls(project, draw) {
    const bar = node("div");
    bar.id = "studioCategories";
    const categories = [...new Set(project.songs.map(song => song.category).filter(Boolean))];
    const chips = [["", "全部"], ...categories.map(label => ["c:" + label, label])];
    if (project.songs.some(song => song.versions.some(take => take.lyrics))) chips.push(["lyrics", "有歌词"]);
    if (project.songs.some(song => song.versions.some(take => previewPath(take)))) chips.push(["audio", "有音频"]);
    if (project.songs.some(song => song.versions.some(take => take.cover))) chips.push(["cover", "有封面"]);
    if (chips.length === 1) return bar;
    for (const [value, label] of chips) {
      const chip = button(label, () => {
        this.category = value;
        for (const item of bar.children) item.setAttribute("aria-pressed", String(item === chip));
        draw();
      }, "capsule");
      chip.setAttribute("aria-pressed", String(this.category === value));
      bar.append(chip);
    }
    return bar;
  }

  renderSongs(project, selectedSong) {
    this.releaseCovers();
    const query = this.query.trim().toLocaleLowerCase();
    const songs = project.songs.filter(song => {
      const version = preferredVersion(project, song);
      const hasQuery = !query || [song.name, version?.lyrics].some(value => value?.toLocaleLowerCase().includes(query));
      return hasQuery && (this.category === "" || this.category === "c:" + song.category
        || (this.category === "lyrics" && Boolean(version?.lyrics))
        || (this.category === "audio" && Boolean(previewPath(version)))
        || (this.category === "cover" && Boolean(version?.cover)));
    });
    if (this.songOrder === "name" || this.songOrder === "reverse") {
      const direction = this.songOrder === "name" ? 1 : -1;
      songs.sort((a,b) => direction * byName.compare(a.name, b.name));
    } else if (this.songOrder === "recent" || this.songOrder === "oldest") {
      const direction = this.songOrder === "oldest" ? 1 : -1;
      songs.sort((a,b) => a.updatedAt && b.updatedAt ? direction * (a.updatedAt - b.updatedAt)
        : Number(Boolean(b.updatedAt)) - Number(Boolean(a.updatedAt)));
    }
    this.cards.replaceChildren(...songs.map(song => this.createCard(project, song, song === selectedSong)));
    if (!songs.length) {
      this.cards.append(node("p", project.songs.length ? "没有找到符合条件的歌曲。" : "此项目暂无歌曲。", "mec-empty"));
      if (!project.songs.length) this.cards.append(this.assetAction());
    }
    this.audition.sync();
  }

  createCard(project, song, current) {
    const version = preferredVersion(project, song);
    const card = node("article", "", "lh-card embedded-song");
    card.dataset.song = song.id;
    card.toggleAttribute("data-selected", current);
    const select = (playback = false) => {
      if (!current && !playback) this.audition.clear();
      this.choose(project, song, version);
      if (playback) void this.audition.toggle({ project, song, version });
      if (!current) this.render();
    };
    const play = button("", () => select(true), "lh-cover embedded-cover");
    const path = previewPath(version);
    play.disabled = !path;
    play.dataset.preview = path;
    play.dataset.title = song.name;
    if (version?.cover) {
      const cover = new Image();
      cover.alt = "";
      cover.loading = "lazy";
      cover.onerror = () => cover.remove();
      play.append(cover);
      void this.loadCover(cover, version.cover);
    }
    const icon = node("span", "", "lh-play-icon");
    icon.setAttribute("aria-hidden", "true");
    play.append(icon);
    const title = button(song.name, select, "lh-song-pick");
    title.setAttribute("aria-pressed", String(current));
    const details = node("div", "", "lh-song-content embedded-song-info");
    const origin = version?.source || (version?.localImport ? "本地导入" : "");
    const reference = song.reference ?? (/^song-[a-f0-9]{32}$/.test(song.id) ? "" : song.id);
    if (reference) details.append(node("small", reference));
    details.append(title);
    if (version) details.append(node("p", origin && !version.name.startsWith(origin)
      ? origin + " · " + version.name : version.name));
    if (song.credits) details.append(node("p", song.credits));
    card.append(play, details);
    if (song.note) card.append(node("p", song.note, "embedded-note"));
    card.onclick = event => { if (!event.target.closest("button")) select(); };
    return card;
  }

  renderDetails(project, song, version) {
    this.details.append(node("h2", song.name));
    if (!version) return;
    if (song.credits) this.details.append(node("p", song.credits, "credits"));
    const field = node("label", "版本", "lh-version");
    const select = node("select");
    select.id = "lh-version";
    for (const take of song.versions) select.add(new Option(take.name + (song.explicit === take.id ? " · 已采用" : ""), take.id));
    select.value = version.id;
    select.onchange = () => {
      const target = song.versions.find(take => take.id === select.value);
      if (!target) return;
      this.audition.clear();
      this.choose(project, song, target);
      this.render();
    };
    field.append(select);
    const launch = button("进入 IMW", () => this.navigation.openStudio?.(selection(project, song, version)));
    this.details.append(field, launch, this.mvAction(project, song, version));
    if (version.stemState === "partial") this.details.append(node("p", "部分分轨可用", "lh-stems-status"));
    this.details.append(this.productionActions(project, song, version));
    if (version.lyrics) this.details.append(node("pre", version.lyrics, "lh-lyrics"));
  }

  mvAction(project, song, version) {
    const box = node("div", "", "lh-mv-action");
    const target = selection(project, song, version);
    const scope = selectField("lh-mv-scope", "MV 范围", [["all", "整首"], ["window", "选取片段"]]);
    const tracks = version.tracks ?? [];
    const available = !version.pending && tracks.length > 0;
    const limit = Math.round(tracks.reduce((end, track) => Math.max(end, track.start + track.duration), 0) * 1000);
    const range = node("div", "", "lh-mv-range");
    const secondsField = (title, value) => {
      const label = node("label", title);
      const input = node("input");
      input.type = "number"; input.min = "0"; input.max = String(limit / 1000);
      input.step = "0.001"; input.value = String(value);
      label.append(input); range.append(label);
      return input;
    };
    const start = secondsField("从（秒）", 0);
    const end = secondsField("到（秒）", limit / 1000);
    range.hidden = true;
    scope.onchange = () => { range.hidden = scope.value !== "window"; };
    const notice = node("p");
    notice.setAttribute("role", "status");
    const create = button("用这版做 MV", async () => {
      const request = this.request;
      const current = () => activePage === this && request === this.request && create.isConnected;
      const window = scope.value === "window" ? {
        start_ms: Math.round(start.valueAsNumber * 1000), end_ms: Math.round(end.valueAsNumber * 1000),
      } : null;
      if (window && !(start.validity.valid && end.validity.valid && Number.isSafeInteger(window.start_ms)
          && Number.isSafeInteger(window.end_ms) && window.start_ms >= 0
          && window.end_ms <= limit && window.start_ms < window.end_ms)) {
        notice.textContent = "请选择歌曲时长内的片段，终点须晚于起点。";
        return;
      }
      create.disabled = true;
      notice.textContent = "正在核对音频并打开视频剪辑…";
      try {
        const result = await studioAction({ action: "start_mv", ...target, window: window ?? "whole_song" });
        if (!current()) return;
        if (result.project_id !== target.project || !/^[a-f0-9]{32}$/.test(result.work_id)
            || !(result.timeline_version > 0)) throw Error("music_mv_timeline_unconfirmed");
        await this.navigation.openMV(result, target);
      } catch (error) {
        if (current()) notice.textContent = ({
          studio_media_changed: "这版音频已变化，请刷新并核对版本。",
          music_mv_full_mix_required: "请选完整混音或已输出的母带版本。",
          music_mv_range_invalid: "片段超出本机歌曲时长。",
          music_mv_compatible_mix_required: "请选本地 MP3、M4A 或 WAV 完整混音。",
        })[error.message] || "暂时无法确认剪辑已保存。请核对本机音频后用同一版本重试。";
      } finally { create.disabled = false; }
    });
    create.disabled = !available;
    if (available) box.append(scope, range);
    else notice.textContent = version.pending ? "音频就绪后可以制作 MV。"
      : "请先归档这版音频。";
    box.append(create, notice);
    return box;
  }

  productionActions(project, song, version) {
    const menu = node("details", "", "lh-production");
    menu.append(node("summary", "在 Codex 中制作"));
    const controls = node("div");
    const notice = node("p");
    notice.setAttribute("role", "status");
    const fallback = node("code");
    fallback.hidden = true;
    const target = selection(project, song, version);
    const actions = [["prepare", "整理制作稿"], ["generate", "生成或续查"]];
    if (version.providerClip && !version.sourceVersion) actions.push(["archive", "查询或接续归档"]);
    if (version.provider === "suno" && version.providerClip && !version.sourceVersion) actions.push(["stems", "导入已有分轨"]);
    for (const [action, title] of actions) {
      const control = button(title, async () => {
        fallback.hidden = true;
        const handoff = this.navigation.canStartProduction?.() && this.navigation.startProduction;
        if (!handoff) {
          notice.textContent = "可把这条指令带到 Codex 聊天。";
          fallback.textContent = "使用 $wechat-ecosystem:lunify-music-production " + JSON.stringify({ action, ...target });
          fallback.hidden = false;
          return;
        }
        for (const entry of controls.children) entry.disabled = true;
        notice.textContent = "正在交给 Codex…";
        try {
          await this.navigation.startProduction(action, target);
          notice.textContent = "已交给 Codex，结果可从歌单刷新读回。";
        } catch {
          notice.textContent = "聊天交接暂不可用。请在 Codex 聊天使用下方指令。";
          fallback.textContent = "使用 $wechat-ecosystem:lunify-music-production " + JSON.stringify({ action, ...target });
          fallback.hidden = false;
        } finally {
          for (const entry of controls.children) entry.disabled = false;
        }
      });
      controls.append(control);
    }
    menu.append(controls, notice, fallback);
    return menu;
  }

  auditionChanged() {
    for (const control of this.cards?.querySelectorAll(".lh-cover") ?? []) {
      const active = control.dataset.preview && control.dataset.preview === this.audition.choice?.path;
      const playing = active && !this.audition.audio.paused;
      const loading = active && this.audition.pending;
      const state = control.disabled ? "可进入 IMW 查看" : playing ? "暂停试听" : loading ? "正在读取" : "试听";
      control.setAttribute("aria-label", state + " " + control.dataset.title);
      control.setAttribute("aria-pressed", String(Boolean(playing)));
      control.title = state + " " + control.dataset.title;
      control.querySelector(".lh-play-icon").textContent = playing ? "Ⅱ" : loading ? "…" : control.disabled ? "·" : "▶";
    }
  }
}

let overview, songs, activePage, audition;
function songAudition(container) {
  const document = container.ownerDocument;
  audition ??= new SongAudition(document);
  const mount = document.getElementById("wbMusicSongs") ?? container;
  if (audition.audio.parentNode !== mount) mount.append(audition.audio);
  return audition;
}
function switchPage(page, navigation) {
  if (activePage && activePage !== page) activePage.close();
  activePage = page;
  audition.activate(page);
  void page.activate(navigation);
}
export function openHome(container, navigation = {}) {
  if (overview?.container !== container) overview = new Overview(container, navigation, songAudition(container));
  switchPage(overview, navigation);
}
export function openSongs(container, navigation = {}, project) {
  if (songs?.container !== container) songs = new SongLibrary(container, navigation, songAudition(container));
  if (!project && activePage !== songs) project = audition.choice?.project.id;
  if (activePage !== songs || songs.switchingProject || (project && project !== songs.openedProject)) {
    songs.prepareProject(project);
  }
  switchPage(songs, navigation);
}
export function homeSelection() { return activePage === songs ? songs?.selected() ?? null : null; }
export function closeHome(next) {
  activePage?.close();
  activePage = null;
  if (next !== "l-unify-home" && next !== "l-unify-songs") audition?.deactivate();
}
