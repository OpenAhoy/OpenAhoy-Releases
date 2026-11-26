(() => {
  // assets/studio/bridge.mjs
  var call;
  function connectStudio(callTool) {
    call = callTool;
  }
  function response(value) {
    return new Response(JSON.stringify(value), {
      status: value?.status ?? 200,
      headers: { "Content-Type": "application/json" }
    });
  }
  function file(args, signal) {
    return mediaResponse((offset) => call({ action: "media", ...args, offset }), signal);
  }
  async function mediaResponse(read, signal, expectedHash) {
    let offset = 0, total, type, hash;
    const parts = [];
    do {
      signal?.throwIfAborted();
      const part = await read(offset);
      signal?.throwIfAborted();
      if (part.error) return response(part);
      if (offset === 0) {
        ({ total, mime: type, sha256: hash } = part);
        if (!Number.isSafeInteger(total) || total < 1 || total > 1024 * 1024 * 1024) throw Error("\u97F3\u9891\u6587\u4EF6\u5927\u5C0F\u65E0\u6548");
      }
      if (expectedHash && part.sha256 !== expectedHash) throw Error("\u97F3\u6E90\u5DF2\u53D8\u5316");
      const bytes = Uint8Array.from(atob(part.bytes ?? part.data), (item) => item.charCodeAt(0));
      if (!bytes.length || part.total !== total || part.offset !== void 0 && part.offset !== offset || hash !== part.sha256 || offset + bytes.length > total) throw Error("\u97F3\u9891\u6587\u4EF6\u5DF2\u53D8\u5316");
      offset += bytes.length;
      parts.push(bytes);
    } while (offset < total);
    return new Response(new Blob(parts, { type }));
  }
  async function studioFetch(path, options = {}) {
    const url = new URL(path, "https://studio.internal");
    const args = Object.fromEntries(url.searchParams);
    switch (url.pathname) {
      case "/catalog":
        return response((await call({ action: "catalog" })).projects);
      case "/draft":
        return response(await call(options.method === "POST" ? { action: "save_draft", ...args, draft: JSON.parse(options.body) } : { action: "draft", ...args }));
      case "/master-adopt":
        return response(await call({ action: "adopt", ...JSON.parse(options.body) }));
    }
    const [, mode, project, song, version, first, second, extra] = url.pathname.split("/");
    if (!song && mode === "project-cover" && project)
      return file({ action: "project_cover", project }, options.signal);
    if (!first && mode === "cover" && project && song && version)
      return file({ action: "cover", project, song, version }, options.signal);
    if (!second && mode === "song-preview" && project && song && version && first)
      return file({ action: "song_preview", project, song, version, asset: first }, options.signal);
    if (!extra && mode === "monitor-file" && project && song && version && first && second)
      return file({ action: "monitor_media", project, song, version, analysis: first, asset: second }, options.signal);
    if (!second && (mode === "source" || mode === "master-file") && project && song && version && first)
      return file({ project, song, version, asset: first }, options.signal);
    return response({ error: "studio_action_unavailable", status: 404 });
  }
  async function studioAction(args) {
    const result = await call(args);
    if (result.error) throw Object.assign(Error(result.error), { status: result.status });
    return result;
  }
  async function studioCover(source, signal) {
    if (!source.startsWith("/cover/") && !source.startsWith("/project-cover/")) return null;
    const reply = await studioFetch(source, { signal });
    if (!reply.ok) return null;
    const blob = await reply.blob();
    if (signal.aborted) return null;
    return URL.createObjectURL(blob);
  }

  // assets/studio/detached-playback.mjs
  function detachedPlayback(studio, signal) {
    let cache, prepared, sourceBus, scoreBus, signature = "", stopped = false;
    const nodes = /* @__PURE__ */ new Map();
    function snapshot() {
      if (studio.imw?.enabled()) return null;
      const scope = studio.detachedTracks?.scope();
      if (!scope) return null;
      const data = globalThis.OAIMWVideo?.detachedAudio?.();
      return data?.project === scope.project && data.work === scope.work && data.rows?.length ? data : null;
    }
    function key(data) {
      return data ? JSON.stringify([data.project, data.work, studio.song?.id, studio.version?.id]) : "";
    }
    function mixKey(data) {
      return data ? JSON.stringify([key(data), data.offsetSeconds, data.rows.map((r) => [r.id, r.sha256, r.start_ms, r.in_ms, r.out_ms, r.volume])]) : "";
    }
    function stopNodes() {
      for (const [node2, gain] of nodes) {
        node2.onended = null;
        try {
          node2.stop();
        } catch {
        }
        node2.disconnect();
        gain.disconnect();
      }
      nodes.clear();
    }
    function reset() {
      cache?.controller.abort();
      cache = null;
      prepared = null;
      signature = "";
      stopNodes();
    }
    function close() {
      reset();
      sourceBus?.disconnect();
      scoreBus?.disconnect();
      sourceBus = scoreBus = null;
    }
    function connect(ctx, master) {
      sourceBus = ctx.createGain();
      scoreBus = ctx.createGain();
      scoreBus.gain.value = studio.version?.previewGain ?? 1;
      sourceBus.connect(master);
      scoreBus.connect(master);
      return scoreBus;
    }
    function levels() {
      if (!sourceBus || !scoreBus) return;
      const data = snapshot(), hasSolo = !!studio.soloTrack || !!studio.version?.tracks.some((row) => studio.trackMonitorState(row.id).solo);
      const source = !!data && data.sourceAudible !== false && (!hasSolo || !!data.sourceSolo);
      const score = data?.scoreAudible !== false;
      const now = sourceBus.context.currentTime;
      sourceBus.gain.setTargetAtTime(Number(source), now, 1e-3);
      scoreBus.gain.setTargetAtTime(Number(score) * (studio.version?.previewGain ?? 1), now, 1e-3);
    }
    async function load() {
      const data = snapshot(), ctx = studio.context;
      if (!data || !ctx) {
        reset();
        levels();
        return;
      }
      const identity = key(data);
      if (cache?.key !== identity || cache.context !== ctx) {
        reset();
        cache = { key: identity, context: ctx, controller: new AbortController(), buffers: /* @__PURE__ */ new Map() };
      }
      const owner = cache, abort = owner.controller.signal, shape = mixKey(data);
      signature = shape;
      const inputs = data.rows.filter((row) => row.volume > 0).map((row) => ({
        row,
        sha: row.sha256,
        read: (offset) => globalThis.OAIMWVideo.detachedChunk(row.id, offset)
      }));
      if (studio.version.mastered && studio.version.masterAudioSha) {
        const version = studio.version;
        const args = { action: "media", project: data.project, song: studio.song.id, version: version.id, asset: "wav" };
        inputs.push({ master: true, sha: version.masterAudioSha, read: (offset) => studioAction({ ...args, offset }) });
      }
      const used = new Set(inputs.map((item) => item.sha));
      for (const hash of owner.buffers.keys()) if (!used.has(hash)) owner.buffers.delete(hash);
      const voices = [];
      for (const input of inputs) {
        if (cache !== owner || signature !== shape || abort.aborted) return;
        let entry = owner.buffers.get(input.sha);
        if (!entry) {
          entry = (async () => {
            const response2 = await mediaResponse(input.read, abort, input.sha);
            if (!response2.ok) throw Error("\u65E0\u6CD5\u8BFB\u53D6\u5206\u79BB\u97F3\u9891");
            const bytes = await response2.arrayBuffer();
            abort.throwIfAborted();
            return ctx.decodeAudioData(bytes);
          })();
          owner.buffers.set(input.sha, entry);
        }
        let buffer;
        try {
          buffer = await entry;
        } catch (error) {
          if (owner.buffers.get(input.sha) === entry) owner.buffers.delete(input.sha);
          if (cache !== owner || signature !== shape || abort.aborted) return;
          throw error;
        }
        voices.push({ ...input, buffer });
      }
      if (cache === owner && signature === shape && mixKey(snapshot()) === shape) {
        prepared = { voices, offset: data.offsetSeconds || 0, shape };
        levels();
      }
    }
    async function prepare(signal2) {
      signal2.addEventListener("abort", reset, { once: true });
      try {
        do {
          signal2.throwIfAborted();
          await load();
          signal2.throwIfAborted();
        } while (snapshot() && prepared?.shape !== mixKey(snapshot()));
      } finally {
        signal2.removeEventListener("abort", reset);
      }
    }
    function schedule(from, to, at) {
      if (!prepared) return;
      for (const { row, master, buffer } of prepared.voices) {
        const start = master ? 0 : row.start_ms / 1e3 - prepared.offset;
        const source = master ? 0 : row.in_ms / 1e3;
        const end = start + (master ? buffer.duration : (row.out_ms - row.in_ms) / 1e3);
        const head = Math.max(from, start), offset = source + head - start;
        const duration = Math.min(to - head, end - head, buffer.duration - offset);
        if (duration <= 0) continue;
        const node2 = studio.context.createBufferSource(), gain = studio.context.createGain();
        node2.buffer = buffer;
        gain.gain.value = master ? 1 : row.volume / 100;
        node2.connect(gain);
        gain.connect(master ? scoreBus : sourceBus);
        nodes.set(node2, gain);
        node2.onended = () => {
          nodes.delete(node2);
          node2.disconnect();
          gain.disconnect();
        };
        node2.start(at + head - from, offset, duration);
      }
    }
    function changed() {
      const data = snapshot();
      levels();
      if (signature === mixKey(data)) return;
      const wasPlaying = studio.playing && !studio.imw.enabled();
      if (wasPlaying) studio.stopAndRemember();
      if (!data) reset();
      else {
        prepared = null;
        signature = mixKey(data);
      }
      studio.transport.sync();
      if (wasPlaying && !stopped) void studio.toggle();
    }
    document.addEventListener("jiusera:detached-audio-change", changed, { signal });
    signal.addEventListener("abort", () => {
      stopped = true;
      close();
    }, { once: true });
    return { available: () => !!snapshot(), programOutput: () => scoreBus, connect, prepare, schedule, levels, stopNodes, close };
  }

  // assets/studio/mec-art.mjs
  function projectArtwork(key) {
    let seed = 2166136261;
    for (const char of String(key)) seed = Math.imul(seed ^ char.charCodeAt(0), 16777619) >>> 0;
    const palettes = [["#eef7fb", "#c7e5f2", "#4c9fc4"], ["#f0f6f3", "#cee4da", "#59a18e"], ["#fbf5ed", "#eddcc0", "#b58c52"], ["#f4f5f8", "#d5dce8", "#788dad"], ["#f8f1f1", "#ecd5d4", "#b77d81"], ["#eef6f6", "#c5e3e1", "#529b9f"]];
    const [paper, tint, ink] = palettes[seed % palettes.length];
    const id = "art" + seed.toString(16), turn = seed % 70 - 35;
    return `<svg viewBox="0 0 600 360" xmlns="http://www.w3.org/2000/svg" aria-hidden="true" focusable="false">
  <defs><linearGradient id="${id}bg" x2="1" y2="1"><stop stop-color="${paper}"/><stop offset="1" stop-color="${tint}"/></linearGradient><radialGradient id="${id}disc" cx=".32" cy=".23" r=".8"><stop stop-color="#fff"/><stop offset=".38" stop-color="${tint}"/><stop offset=".7" stop-color="${ink}" stop-opacity=".6"/><stop offset="1" stop-color="${paper}"/></radialGradient><linearGradient id="${id}ribbon" x2="0" y2="1"><stop stop-color="#fff"/><stop offset=".55" stop-color="${tint}"/><stop offset="1" stop-color="${ink}"/></linearGradient></defs>
  <rect width="600" height="360" fill="url(#${id}bg)"/>
  <g fill="none" stroke="${ink}" stroke-opacity=".12">${[0, 1, 2, 3, 4].map((i) => `<path d="M-40 ${155 + i * 16} Q125 ${35 + i * 18} 305 ${167 + i * 13} T650 ${110 + i * 19}"/>`).join("")}</g>
  <ellipse cx="316" cy="295" rx="132" ry="16" fill="${ink}" opacity=".12"/>
  <g transform="translate(302 171) rotate(${turn})"><circle r="108" fill="url(#${id}disc)" stroke="#fff" stroke-opacity=".8" stroke-width="2"/>
  ${[93, 80, 67, 54].map((r) => `<circle r="${r}" fill="none" stroke="#fff" stroke-opacity=".36" stroke-width="1.3"/>`).join("")}
  <circle r="30" fill="${paper}" stroke="#fff" stroke-width="2"/><circle r="7" fill="${ink}" opacity=".55"/>
  <path d="M-146 64 C-72 110 72 -120 152 -48" fill="none" stroke="${ink}" stroke-opacity=".2" stroke-width="25"/>
  <path d="M-146 56 C-72 102 72 -128 152 -56" fill="none" stroke="url(#${id}ribbon)" stroke-width="24"/>
  <path d="M-146 47 C-72 93 72 -137 152 -65" fill="none" stroke="#fff" stroke-opacity=".9" stroke-width="2"/></g>
  <g fill="${ink}" opacity=".48"><circle cx="104" cy="99" r="3"/><circle cx="491" cy="242" r="3"/><path d="M481 79v15m-7-7h14" stroke="${ink}" stroke-width="1.6"/></g>
  </svg>`;
  }

  // assets/studio/transport-shadow.css
  var transport_shadow_default = ':host{--button:32px;display:block;color:var(--wb-dock-ink);font:12px system-ui,sans-serif;position:relative}\n*{box-sizing:border-box}\n[hidden],.handheld,#shuttle-slot:empty{display:none!important}\n:host(:not([data-songs])) .songs-only,:host([data-songs]) .studio-only{display:none!important}\n.controls,.cluster,.options,.volume,.loop-range,.readout{display:flex;align-items:center}\n.controls{gap:5px}\n.cluster{gap:1px;padding:2px;background:var(--wb-dock-surface);border:1px solid transparent;box-shadow:var(--wb-dock-inset);border-radius:8px}\nbutton{display:grid;place-items:center;flex:none;width:var(--button);height:var(--button);color:inherit;background:var(--wb-dock-surface);border:0;border-radius:6px;\ncursor:pointer;padding:0;box-shadow:var(--wb-dock-raised)}\nbutton svg,.options svg{width:17px;height:17px;flex:none}\nbutton:hover:not(:disabled){color:var(--wb-dock-active)}\nbutton:active:not(:disabled){box-shadow:var(--wb-dock-inset)}\nbutton[aria-pressed=true],button[aria-expanded=true]{background:var(--wb-dock-surface);color:var(--wb-dock-active);box-shadow:var(--wb-dock-inset)}\nbutton:disabled{opacity:.38;cursor:default}\n[aria-disabled=true]{pointer-events:none}\nbutton:focus-visible,input:focus-visible{outline:2px solid var(--wb-dock-focus);outline-offset:-2px}\n#play{color:var(--wb-dock-active)}\n:host([data-playing]) #play{box-shadow:var(--wb-dock-inset)}\n.readout{gap:7px;padding:0 5px}\noutput{display:block;min-width:58px;text-align:center;white-space:nowrap;font:650 13px ui-monospace,monospace}\n:host([data-playing]) output{color:var(--wb-dock-active)}\n#output-meter{position:relative;width:39px;height:6px;overflow:hidden;border-radius:2px;background:var(--wb-dock-surface);box-shadow:var(--wb-dock-inset)}\n#output-meter i{display:block;height:100%;background:var(--wb-dock-ink);transform:scaleX(var(--peak-fill,0));transform-origin:left}\n#output-meter[data-hot] i{background:var(--wb-dock-active)}\n#song-seek{margin:0;width:clamp(56px,7.5vw,108px);min-width:32px;cursor:pointer}\n#song-seek:disabled{opacity:.38;cursor:default}\n/* Reserve "/ mm:ss" before metadata so the centered dock keeps its position. */\n#song-duration{inline-size:7ch;min-inline-size:0;flex:none;font-size:11px;color:var(--wb-dock-ink)}\n.options{justify-content:center;flex-wrap:wrap;position:absolute;bottom:calc(100% + 9px);right:0;width:max-content;max-width:min(360px,calc(100vw - 24px));padding:8px;gap:7px;border:1px solid var(--line);border-radius:10px;background:var(--wb-dock-surface);box-shadow:var(--wb-dock-float)}\n.volume{gap:3px;padding-inline:5px}\n.volume input{width:76px}\ninput{font:inherit;color:inherit;accent-color:var(--wb-dock-active)}\n.loop-range{gap:3px}\n.loop-range input{width:50px;border:1px solid var(--line);border-radius:5px;padding:5px 2px 5px 5px;background:var(--wb-dock-surface);box-shadow:var(--wb-dock-inset)}\n.loop-range input::-webkit-inner-spin-button{margin:0}\n@media(prefers-reduced-motion:no-preference){\n  button{transition:background-color 90ms ease-out,color 90ms ease-out}\n}\n@media(max-width:820px){\n  :host{--button:39px}\n  .controls{justify-content:center;gap:7px;border:0;padding:0}\n  .options{right:0;left:0;margin-inline:auto}\n  .desktop,#output-meter{display:none}\n  .handheld{display:grid!important}\n  :host([data-songs]) .readout{min-width:0;gap:4px;padding:0 2px}\n  :host([data-songs]) #song-seek{width:clamp(40px,16vw,94px)}\n}\n@media(max-width:380px){\n  :host([data-songs]) .controls{gap:4px}\n}\n\n:host(:not([data-video])) .video-only {display:none!important}\n.video-position {display:flex;align-items:center;gap:4px}\n.video-position button {font:600 10px ui-monospace,monospace}\n#video-seek {width:88px;accent-color:var(--wb-dock-active)}\n#video-meter-note {width:39px;text-align:center;opacity:.65}\n@media(max-width:820px){#video-meter-note{display:none}}\n';

  // assets/studio/transport.mjs
  var icons = {
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
    range: '<path d="M9 5H5v14h4m6-14h4v14h-4M9 12h6"/>'
  };
  function icon(key) {
    return '<svg viewBox="0 0 24 24" aria-hidden="true" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">' + icons[key] + "</svg>";
  }
  var button = (id, key, label, attributes = "") => '<button id="' + id + '" type="button" aria-label="' + label + '" title="' + label + '" ' + attributes + ">" + icon(key) + "</button>";
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
    root.innerHTML = `<style>${transport_shadow_default}</style>
    <div class="controls">
      <div id="shuttle" class="cluster" role="group" aria-label="\u5B9A\u4F4D">
        ${button("reset", "begin", "\u56DE\u5230\u5F00\u5934")}
        ${button("prev", "back", "\u4E0A\u4E00\u4E2A\u7247\u6BB5\u8FB9\u754C", 'class="studio-only"')}
        ${button("next", "forward", "\u4E0B\u4E00\u4E2A\u7247\u6BB5\u8FB9\u754C", 'class="studio-only"')}
        ${button("finish", "end", "\u5230\u7ED3\u5C3E")}
      </div>
      <div class="cluster playback" role="group" aria-label="\u64AD\u653E\u4E0E\u505C\u6B62">
        ${button("play", "play", "\u64AD\u653E", "disabled")}
        ${button("stop", "stop", "\u505C\u6B62", "disabled")}
      </div>
      <div class="readout">
        <output id="time" aria-label="\u64AD\u653E\u4F4D\u7F6E" aria-live="off">00:00.0</output>
        <div id="output-meter" class="studio-only" role="meter" aria-label="\u4E3B\u8F93\u51FA\u5CF0\u503C" aria-valuemin="-60" aria-valuemax="0"
             aria-valuenow="-60" aria-valuetext="\u9759\u97F3" title="\u4E3B\u8F93\u51FA\u5CF0\u503C\uFF08dBFS\uFF09"><i></i></div>
        <span id="video-meter-note" hidden title="\u89C6\u9891\u9884\u89C8\u6682\u65E0\u4E3B\u8F93\u51FA\u7535\u5E73" aria-label="\u89C6\u9891\u9884\u89C8\u6682\u65E0\u4E3B\u8F93\u51FA\u7535\u5E73">\u2014</span>
        <input id="song-seek" class="songs-only" type="range" min="0" max="1" step="0.01" value="0" aria-label="\u6B4C\u66F2\u64AD\u653E\u4F4D\u7F6E" disabled>
        <output id="song-duration" class="songs-only" aria-label="\u6B4C\u66F2\u603B\u65F6\u957F">\u2014</output>
      </div>
      <div class="cluster modes" role="group" aria-label="\u64AD\u653E\u9009\u9879">
        ${button("loop", "loop", "\u5FAA\u73AF", 'class="studio-only" aria-pressed="false" disabled')}
        ${button("click", "metronome", "\u8282\u62CD\u5668", 'class="desktop studio-only" aria-pressed="false" disabled')}
        ${button("more", "more", "\u66F4\u591A\u64AD\u653E\u63A7\u5236", 'aria-controls="options" aria-expanded="false"')}
      </div>
    </div>
    <div id="options" class="options" hidden>
      <div id="shuttle-slot"></div>
      <div class="video-only video-position">
        <button id="video-rewind" type="button" aria-label="\u540E\u9000\u4E94\u79D2" title="\u540E\u9000\u4E94\u79D2">\u22125s</button>
        <input id="video-seek" type="range" min="0" max="1" step="1" value="0" aria-label="\u89C6\u9891\u64AD\u653E\u4F4D\u7F6E">
        <button id="video-forward" type="button" aria-label="\u524D\u8FDB\u4E94\u79D2" title="\u524D\u8FDB\u4E94\u79D2">+5s</button>
      </div>
      ${button("click-mobile", "metronome", "\u8282\u62CD\u5668", 'class="handheld studio-only" aria-pressed="false" disabled')}
      <label class="volume">${icon("volume")}<input id="volume" type="range" min="0" max="100" value="85" aria-label="\u4E3B\u97F3\u91CF" title="\u4E3B\u97F3\u91CF"></label>
      <div class="loop-range studio-only">
        ${icon("loop")}
        <input id="loop-in" type="number" min="0" step="0.25" aria-label="\u5FAA\u73AF\u8D77\u70B9\uFF08\u79D2\uFF09" title="\u5FAA\u73AF\u8D77\u70B9\uFF08\u79D2\uFF09">
        <span aria-hidden="true">\u2013</span>
        <input id="loop-out" type="number" min="0.25" step="0.25" aria-label="\u5FAA\u73AF\u7EC8\u70B9\uFF08\u79D2\uFF09" title="\u5FAA\u73AF\u7EC8\u70B9\uFF08\u79D2\uFF09">
        ${button("loop-clip", "range", "\u4EE5\u9009\u4E2D\u7247\u6BB5\u8BBE\u7F6E\u5FAA\u73AF\u8303\u56F4", "disabled")}
      </div>
    </div>`;
    const $ = (id) => root.getElementById(id);
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
    const open = (value) => {
      $("more").setAttribute("aria-expanded", String(value));
      $("options").hidden = !value;
    };
    $("more").onclick = () => open($("options").hidden);
    root.addEventListener("keydown", (event) => {
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
      $(id).onclick = (event) => source?.[id]?.(event);
    }
    $("song-seek").oninput = (event) => source?.seek?.(Number(event.target.value));
    $("video-seek").oninput = (event) => source?.videoSeek?.(Number(event.target.value), event);
    $("volume").oninput = (event) => source?.volume(Number(event.target.value) / 100, event);
    for (const id of ["loop-in", "loop-out"]) {
      $(id).onchange = (event) => {
        if ($("loop-in").value && $("loop-out").value) source?.setLoop?.(Number($("loop-in").value), Number($("loop-out").value), event);
      };
    }
    document.addEventListener("jiusera:imw-transport-state", (event) => source?.videoState?.(event.detail));
    return {
      $,
      isActive: (owner) => source === owner,
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
        for (const id of ["click", "click-mobile"]) $(id).title = "\u8282\u62CD\u5668";
        transport.setAttribute("aria-label", owner.songs ? "L-unify \u6B4C\u66F2\u8BD5\u542C\u63A7\u5236\u5668" : "L-unify IMW \u64AD\u653E\u63A7\u5236\u5668");
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
        const label = cancelLoading ? "\u53D6\u6D88\u672C\u6B21\u8BD5\u542C" : loading ? "\u6B63\u5728\u8FDE\u63A5\u97F3\u9891\u8F93\u51FA" : playing ? "\u6682\u505C" : unavailable || "\u64AD\u653E";
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
        meter.setAttribute("aria-valuetext", rounded <= -60 ? "\u9759\u97F3" : rounded + " dBFS");
        meter.style.setProperty("--peak-fill", (rounded + 60) / 60);
        meter.toggleAttribute("data-hot", rounded >= -6);
      }
    };
  }
  var shared;
  function dockTransport() {
    return shared ??= createDockTransport();
  }
  function mountTransport(studio) {
    const dock = dockTransport();
    const { $ } = dock;
    const owner = {
      play: () => studio.toggle(),
      stop: () => studio.stopTransport(),
      reset: () => studio.seek(0),
      finish: () => studio.seek(studio.length),
      prev: () => studio.step(-1),
      next: () => studio.step(1),
      loop: () => studio.toggleLoop(),
      click: () => studio.toggleClick(),
      "click-mobile": () => studio.toggleClick(),
      "loop-clip": () => studio.loopSelection(),
      level: () => studio.level,
      volume: (value) => studio.volume(value),
      closeDrawer: () => studio.drawer(false),
      setLoop(start, end) {
        studio.setLoop(start, end);
        studio.transport.sync();
      }
    };
    const video = videoControls(dock, studio);
    const active = () => dock.isActive(owner);
    const close = () => {
      if (active()) dock.close();
    };
    studio.addEventListener("studio-drawer", (event) => {
      if (event.detail) close();
    });
    return {
      activate: () => {
        dock.activate(owner);
        dock.peak(-60);
      },
      activateVideo() {
        dock.activate(video);
        video.videoState({ ready: false, durationMs: 0, cursorMs: 0, loop: false });
        video.request();
      },
      deactivate: () => {
        dock.deactivate(owner);
        dock.deactivate(video);
      },
      close,
      meterVisible: () => active() && dock.meterVisible(),
      peak: (db) => {
        if (active()) dock.peak(db);
      },
      time: (label) => {
        if (active()) $("time").textContent = label;
      },
      sync() {
        studio.syncSongAudition();
        if (!active()) return;
        dock.playback({
          playing: studio.playing,
          loading: !!studio.startup,
          canPlay: studio.canPlayAudio && !studio.startup,
          canStop: studio.canPlayAudio && (studio.startPoint != null || !!studio.startup)
        });
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
      }
    };
  }
  function videoControls(dock, studio) {
    const { $ } = dock;
    let level = 1, controlsKey = "";
    function send(action, inputEvent, values = {}) {
      document.dispatchEvent(new CustomEvent("jiusera:imw-transport-command", {
        detail: { action, inputEvent, ...values }
      }));
    }
    const commands = {
      play: "play",
      stop: "stop",
      reset: "first",
      finish: "last",
      prev: "previous-cut",
      next: "next-cut",
      loop: "loop",
      "loop-clip": "loop-clip",
      "video-rewind": "rewind",
      "video-forward": "forward",
      click: "metronome",
      "click-mobile": "metronome"
    };
    const video = {
      video: true,
      level: () => level,
      request: () => send("request-state"),
      volume: (value, event) => send("volume", event, { level: value }),
      videoSeek: (ms, event) => send("seek", event, { cursorMs: ms }),
      closeDrawer: () => studio.drawer(false),
      setLoop: (start, end, event) => send("loop-range", event, {
        inMs: Math.round(start * 1e3),
        outMs: Math.round(end * 1e3)
      }),
      videoState(state) {
        if (!state || !dock.isActive(video)) return;
        const duration = Math.max(0, Number(state.durationMs) || 0);
        const cursor = Math.max(0, Math.min(duration, Number(state.cursorMs) || 0));
        const ready = state.active !== false && state.ready && duration > 0;
        const pending = !!(state.pending || state.loading);
        const time2 = songTime(cursor / 1e3);
        if ($("time").textContent !== time2) $("time").textContent = time2;
        const seek = $("video-seek");
        seek.disabled = !ready;
        if (seek.max !== String(duration || 1)) seek.max = String(duration || 1);
        if (Number(seek.value) !== cursor) seek.value = String(cursor);
        const seekLabel = time2 + " / " + songTime(duration / 1e3);
        if (seek.getAttribute("aria-valuetext") !== seekLabel) seek.setAttribute("aria-valuetext", seekLabel);
        const measured = Number.isFinite(state.peakDb);
        if (measured) dock.peak(Math.max(-60, Math.min(0, state.peakDb)));
        const key = [
          ready,
          pending,
          state.playing,
          state.canStop,
          cursor === 0,
          cursor >= duration,
          duration,
          state.loop,
          state.canLoopClip,
          state.loopInMs,
          state.loopOutMs,
          state.level,
          state.canClick,
          state.metronome,
          measured
        ].join("/");
        if (key === controlsKey) return;
        controlsKey = key;
        dock.playback({
          playing: !!state.playing,
          loading: pending,
          cancelLoading: pending && !state.playing,
          canPlay: ready || pending,
          canStop: !!state.canStop || pending,
          unavailable: ready ? "" : "\u6682\u65E0\u53EF\u64AD\u653E\u7684\u89C6\u9891"
        });
        for (const id of ["reset", "prev", "video-rewind"]) $(id).disabled = !ready || cursor <= 0;
        for (const id of ["finish", "next", "video-forward"]) $(id).disabled = !ready || cursor >= duration;
        $("loop").disabled = !ready || duration < 250;
        $("loop").setAttribute("aria-pressed", String(!!state.loop));
        $("loop-clip").disabled = !ready || !state.canLoopClip;
        for (const [id, ms] of [["loop-in", state.loopInMs], ["loop-out", state.loopOutMs]]) {
          const control = $(id);
          control.disabled = !ready || !Number.isFinite(ms) || duration < 250;
          control.max = duration / 1e3;
          if (!control.matches(":focus")) control.value = Number.isFinite(ms) ? ms / 1e3 : "";
        }
        for (const id of ["click", "click-mobile"]) {
          $(id).disabled = !ready || !state.canClick;
          $(id).setAttribute("aria-pressed", String(!!state.metronome));
          $(id).title = state.canClick ? "\u8282\u62CD\u5668" : "\u97F3\u9891\u6A21\u5F0F\u53EF\u4F7F\u7528\u8282\u62CD\u5668";
        }
        if (Number.isFinite(state.level)) level = Math.max(0, Math.min(1, state.level));
        $("volume").value = Math.round(level * 100);
        $("output-meter").hidden = !measured;
        $("video-meter-note").hidden = measured;
      }
    };
    for (const [key, action] of Object.entries(commands)) video[key] = (event) => send(action, event);
    return video;
  }
  function songTime(seconds) {
    const tenths = Math.max(0, Math.floor(seconds * 10));
    const minutes = String(Math.floor(tenths / 600)).padStart(2, "0");
    const second = String(Math.floor(tenths / 10) % 60).padStart(2, "0");
    return minutes + ":" + second + "." + tenths % 10;
  }
  function mountSongTransport({ audio, toggle, stop }) {
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
      seek: (value) => {
        if (durationOfSource()) audio.currentTime = value;
        else seek.value = "0";
      },
      level: () => audio.volume,
      volume: (value) => {
        audio.volume = value;
      }
    };
    return {
      activate: () => dock.activate(owner),
      deactivate: () => dock.deactivate(owner),
      sync({ available, loading }) {
        if (!dock.isActive(owner)) return;
        const duration = durationOfSource();
        const time2 = duration ? audio.currentTime : 0;
        const timeLabel = songTime(time2);
        dock.playback({
          playing: !audio.paused,
          cancelLoading: loading,
          canPlay: available || loading,
          canStop: loading || Boolean(duration && (!audio.paused || audio.currentTime > 0)),
          unavailable: available ? "" : "\u5F53\u524D\u9009\u62E9\u65E0\u53EF\u7528\u8BD5\u542C"
        });
        if ($("time").textContent !== timeLabel) $("time").textContent = timeLabel;
        const totalLabel = duration ? "/ " + songTime(duration).slice(0, -2) : "\u2014";
        if ($("song-duration").textContent !== totalLabel) $("song-duration").textContent = totalLabel;
        for (const control of seekControls) {
          control.disabled = !duration && !loading;
          if (!duration && loading) control.setAttribute("aria-disabled", "true");
          else control.removeAttribute("aria-disabled");
        }
        seek.max = String(duration || 1);
        seek.value = String(time2);
        seek.setAttribute("aria-valuetext", timeLabel);
      }
    };
  }

  // assets/studio/home-output-master-hero.webp
  var home_output_master_hero_default = "data:image/webp;base64,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";

  // assets/studio/home-feature-signal.json
  var home_feature_signal_default = { master: { bypass: { bars: [41, 37, 49, 46, 33, 36, 30, 25, 36, 25, 31, 29, 28, 41, 37, 41, 43, 31, 44, 38, 29, 38, 31, 39, 37, 29, 35, 31, 26, 36, 28, 40, 36, 27, 44, 33, 44, 44, 32, 32, 27, 17], peak: -11.2 }, wet: { bars: [91, 77, 100, 93, 62, 72, 57, 50, 74, 48, 60, 55, 52, 87, 74, 85, 90, 61, 94, 78, 57, 79, 60, 79, 76, 56, 73, 62, 49, 76, 55, 82, 73, 52, 90, 63, 89, 88, 62, 63, 52, 28], peak: -4 } }, stems: [[69, 100, 100, 84, 70, 70, 51, 49, 33, 60, 59, 84, 95, 88, 88, 66, 57, 40, 53, 35, 60, 93, 90, 91, 73, 80, 56, 55, 32], [80, 94, 86, 79, 68, 59, 52, 70, 82, 97, 88, 82, 58, 47, 70, 73, 93, 80, 80, 70, 69, 66, 58, 80, 87, 100, 82, 73, 44]] };

  // assets/studio/home.mjs
  var keyPrefix = "jiusera.lus.project.";
  var takeKey = (project, song) => "version-" + project + "/" + song;
  var unsavedPreferences = /* @__PURE__ */ new Map();
  function readPreference(key, fallback) {
    if (unsavedPreferences.has(key)) return unsavedPreferences.get(key);
    try {
      return JSON.parse(localStorage.getItem(keyPrefix + key)) ?? fallback;
    } catch {
      return fallback;
    }
  }
  function rememberPreference(key, value) {
    try {
      localStorage.setItem(keyPrefix + key, JSON.stringify(value));
      unsavedPreferences.delete(key);
    } catch {
      unsavedPreferences.set(key, value);
    }
  }
  function preferredVersion(project, song) {
    if (!song) return null;
    const saved = readPreference(takeKey(project.id, song.id), "");
    return song.versions.find((version) => version.id === saved) ?? song.versions.find((version) => version.id === song.adopted) ?? song.versions[0] ?? null;
  }
  function selection(project, song, version) {
    return project && song && version ? { project: project.id, song: song.id, version: version.id } : null;
  }
  function savedProject(projects) {
    const wanted = readPreference("recent-project", "");
    return projects.find((project) => project.id === wanted) ?? null;
  }
  function savedSong(project) {
    const wanted = readPreference("song-" + project.id, "");
    return project.songs.find((song) => song.id === wanted) ?? null;
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
  function button2(text, invoke, className) {
    const element = node("button", text, className);
    element.type = "button";
    element.onclick = invoke;
    return element;
  }
  async function catalog() {
    const reply = await studioFetch("/catalog");
    if (!reply.ok) throw Error("\u76EE\u5F55\u4E0D\u53EF\u8BFB\u53D6");
    const projects = await reply.json();
    if (!Array.isArray(projects)) throw Error("\u9879\u76EE\u76EE\u5F55\u65E0\u6548");
    return projects;
  }
  var MusicPage = class {
    constructor(container, title, titleId, navigation, audio) {
      this.container = container;
      this.navigation = navigation;
      this.projects = [];
      this.coverRequests = /* @__PURE__ */ new Set();
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
      this.status.textContent = "\u6B63\u5728\u8BFB\u53D6\u767B\u8BB0\u9879\u76EE\u2026";
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
        this.status.textContent = "\u6682\u65F6\u65E0\u6CD5\u8BFB\u53D6\u97F3\u4E50\u9879\u76EE\u3002";
        this.content.append(button2("\u91CD\u8BD5", () => void this.activate(this.navigation)));
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
      } catch {
      }
    }
    assetAction() {
      return button2("\u6253\u5F00\u97F3\u9891\u8D44\u4EA7", () => this.navigation.openAssets?.());
    }
  };
  function featureSelection(projects, feature) {
    const current = savedProject(projects);
    const ordered = current ? [current, ...projects.filter((project) => project !== current)] : projects;
    for (const project of ordered) {
      const saved = savedSong(project);
      const songs2 = saved ? [saved, ...project.songs.filter((song) => song !== saved)] : project.songs;
      for (const song of songs2) {
        const preferred = preferredVersion(project, song);
        const options = [preferred, ...song.versions.filter((version2) => version2 !== preferred)];
        const version = options.find((item) => item && !item.mastered && !item.paintOnly && !item.pending && item.tracks.length >= (feature === "solo" ? 2 : 1));
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
    const action = button2(title, () => navigation.openStudio?.(target, key), "lh-feature-link");
    action.disabled = !target;
    if (!target) action.title = "\u8BF7\u5148\u767B\u8BB0\u53EF\u7528\u7684\u97F3\u4E50\u9879\u76EE";
    return action;
  }
  function masterPromotion(navigation, projects) {
    const card = node("article", "", "lh-feature lh-master-promo");
    const art = new Image();
    art.alt = "";
    art.src = home_output_master_hero_default;
    art.className = "lh-master-art";
    const copy = node("div", "", "lh-master-copy");
    copy.append(
      node("p", "Stereo Out", "lh-master-path"),
      node("h3", "Output Master"),
      node("p", "\u6BD4\u8F83\u5904\u7406\u524D\u540E\uFF0C\u6838\u9A8C\u8BD5\u542C\u4E0E\u4EA4\u4ED8\u3002", "lh-master-summary"),
      promoAction(navigation, projects, "master", "\u6253\u5F00\u6BCD\u5E26\u5DE5\u4F5C\u53F0")
    );
    const scope = node("div", "", "lh-master-scope");
    scope.setAttribute("aria-label", "\u540C\u4E00\u6BB5\u5408\u6210\u97F3\u9891\u7684\u5B9E\u9645\u6BCD\u5E26\u5904\u7406\u524D\u540E");
    scope.append(node("p", "\u793A\u4F8B\u4FE1\u53F7", "lh-scope-label"));
    for (const [mode, label] of [["bypass", "\u5904\u7406\u524D"], ["wet", "\u5904\u7406\u540E"]]) {
      const reading = home_feature_signal_default.master[mode];
      const row = node("div", "", "lh-scope-row lh-scope-" + mode);
      row.append(
        node("span", label),
        waveStrip(reading.bars),
        node("span", reading.peak.toFixed(1).replace("-", "\u2212") + " dBTP")
      );
      scope.append(row);
    }
    card.append(art, copy, scope);
    return card;
  }
  function soloPromotion(navigation, projects) {
    const card = node("article", "", "lh-feature lh-solo-promo");
    const copy = node("div", "", "lh-solo-copy");
    copy.append(
      node("h3", "\u9010\u8F68\u72EC\u542C"),
      node("p", "\u72EC\u542C\u65CB\u5F8B\uFF0C\u9759\u97F3\u5176\u4F59\u8F68\u9053\u3002"),
      promoAction(navigation, projects, "solo", "\u6253\u5F00\u5206\u8F68\u63A7\u5236")
    );
    const timeline = node("div", "", "lh-solo-timeline");
    timeline.setAttribute("aria-hidden", "true");
    for (const [index, peaks] of home_feature_signal_default.stems.entries()) {
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
    const control = button2(label, invoke, "lh-feature-link");
    control.disabled = !enabled;
    copy.append(node("h3", title), node("p", description), control);
    const visual = kind === "trim" ? waveStrip(home_feature_signal_default.stems[0]) : node("span", "", "lh-take-sheets");
    visual.setAttribute("aria-hidden", "true");
    card.append(copy, visual);
    return card;
  }
  var moduleBanners = [
    { feature: "master", title: "Output Master", detail: "\u8BD5\u542C\u6BCD\u5E26\u5904\u7406\u524D\u540E" },
    { feature: "solo", title: "\u9010\u8F68\u72EC\u542C", detail: "\u5355\u72EC\u542C\u6E05\u7F16\u6392\u4E2D\u7684\u6BCF\u6761\u8F68\u9053" }
  ];
  function recentSongs(projects) {
    const rows = [];
    for (const project of projects) {
      for (const song of project.songs) {
        let newest;
        for (const version of song.versions) {
          const date = version.generatedAt ?? version.archivedAt;
          const path = previewPath(version);
          if (!version.mastered && !version.sourceVersion && path && Number.isFinite(date) && date > 0 && (!newest || date > newest.date || date === newest.date && version.id < newest.version.id)) {
            newest = { project, song, version, date, path };
          }
        }
        if (newest) rows.push(newest);
      }
    }
    return rows.sort((a, b) => b.date - a.date || a.path.localeCompare(b.path));
  }
  var Overview = class extends MusicPage {
    constructor(container, navigation, audition2) {
      super(container, "L-unify", "wbMusicHomeTitle", navigation);
      this.container.classList.add("lh-project-home");
      this.projectOffset = 0;
      this.recentOffset = 0;
      this.audition = audition2;
    }
    auditionChoice() {
      return this.audition.choice;
    }
    auditionChanged() {
      for (const control of this.recentCards?.children ?? []) {
        const chosen = control.dataset.path === this.audition.choice?.path;
        const playing = chosen && !this.audition.audio.paused;
        const loading = chosen && this.audition.pending;
        control.toggleAttribute("data-chosen", chosen);
        control.setAttribute("aria-pressed", String(Boolean(playing)));
        const state = loading ? "\u6B63\u5728\u8BFB\u53D6" : playing ? "\u6682\u505C\u8BD5\u542C" : "\u8BD5\u542C";
        control.setAttribute("aria-label", state + " " + control.dataset.songLabel);
        control.querySelector(".lh-recent-play").textContent = loading ? "\u2026" : playing ? "\u2161" : "\u25B6";
      }
    }
    renderBanner() {
      const config = this.navigation.homeBanners ?? moduleBanners;
      const slides = Array.isArray(config) && config.filter((item) => item && ["master", "solo"].includes(item.feature) && typeof item.title === "string" && item.title.trim() && typeof item.detail === "string");
      if (!slides?.length) return null;
      const banner = node("section", "", "lh-banner");
      banner.setAttribute("aria-label", "L-unify \u529F\u80FD\u52A8\u6001");
      const panels = node("div", "", "lh-banner-panels");
      const controls = node("div", "", "lh-banner-controls");
      let index = 0;
      const select = (value) => {
        index = value;
        for (const [at, panel] of [...panels.children].entries()) panel.hidden = at !== index;
        for (const [at, control] of [...controls.children].entries()) control.setAttribute("aria-pressed", String(at === index));
      };
      for (const [at, slide] of slides.entries()) {
        const target = featureSelection(this.projects, slide.feature);
        const panel = target ? button2("", () => this.navigation.openStudio?.(target, slide.feature)) : node("div");
        panel.className = "lh-banner-slide";
        panel.dataset.feature = slide.feature;
        const message = node("span", "", "lh-banner-message");
        message.append(node("strong", slide.title), node("span", slide.detail));
        panel.append(message, waveStrip(slide.feature === "master" ? home_feature_signal_default.master.wet.bars : home_feature_signal_default.stems[0]));
        panels.append(panel);
        if (slides.length > 1) {
          const dot = button2("", () => select(at));
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
      const card = button2("", () => {
        this.status.textContent = "";
        rememberChoice(row.project, row.song, row.version);
        void this.audition.toggle(row);
      }, "lh-recent-card");
      card.dataset.path = row.path;
      card.dataset.songLabel = row.song.name + " \xB7 " + row.project.name + " \xB7 " + row.version.name;
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
      text.append(node("strong", row.song.name), node("small", row.project.name + " \xB7 " + row.version.name));
      const play = node("span", "", "lh-recent-play");
      play.setAttribute("aria-hidden", "true");
      card.append(art, text, play);
      return card;
    }
    mountRecent(section, rows) {
      const heading = node("header", "", "lh-recent-heading");
      heading.append(node("h2", "\u6700\u8FD1\u751F\u6210"));
      section.append(heading);
      if (!rows.length) {
        section.append(node("p", "\u6682\u65E0\u53EF\u8BD5\u542C\u7684\u65B0\u66F2\u3002", "lh-recent-empty"));
        this.recentCards = null;
        return;
      }
      const gallery = this.recentCards = node("div", "", "lh-recent-grid");
      this.recentCovers = /* @__PURE__ */ new Set();
      gallery.id = "lh-recent-grid";
      const pager = node("nav", "", "lh-recent-pages");
      pager.setAttribute("aria-label", "\u6700\u8FD1\u751F\u6210\u5206\u9875");
      const readout = node("span");
      readout.setAttribute("aria-live", "polite");
      let page = 0, capacity = 1, shown = "";
      const turn = (direction) => {
        const offset = (page + direction) * capacity;
        if (offset < 0 || offset >= rows.length) return;
        this.recentOffset = offset;
        layout();
      };
      const previous = button2("\u2039", () => turn(-1)), next = button2("\u203A", () => turn(1));
      for (const [control, label] of [[previous, "\u4E0A\u4E00\u9875\u65B0\u66F2"], [next, "\u4E0B\u4E00\u9875\u65B0\u66F2"]]) {
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
        const rowsIn = (room) => Math.max(1, Math.min(3, Math.floor((room + gap) / (46 + gap))));
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
        const label = page + 1 + " / " + pages;
        if (readout.textContent !== label) readout.textContent = label;
        if (shown === start + ":" + end) return;
        shown = start + ":" + end;
        const focusedPath = gallery.contains(document.activeElement) && document.activeElement.dataset.path;
        this.releaseCovers(this.recentCovers);
        gallery.replaceChildren(...rows.slice(start, end).map((row) => this.recentCard(row)));
        if (focusedPath) {
          const replacement = Array.from(gallery.children).find((card) => card.dataset.path === focusedPath);
          (replacement ?? gallery.firstElementChild)?.focus({ preventScroll: true });
        }
        this.auditionChanged();
      };
      this.recentSize = new ResizeObserver(layout);
      this.recentSize.observe(section);
    }
    projectCard(project) {
      const card = button2("", () => this.navigation.openSongs?.(project.id), "lh-project-card");
      card.dataset.project = project.id;
      card.setAttribute("aria-label", "\u8FDB\u5165\u9879\u76EE " + project.name);
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
      if (style && project.songs.every((song) => song.category === style)) names.append(node("small", style));
      title.append(names, node("span", project.songs.length + " \u9996", "lh-project-track-count"));
      card.append(picture, title);
      return card;
    }
    mountGallery(projects, heading) {
      const gallery = node("div", "", "lh-project-grid");
      gallery.id = "lh-project-grid";
      const pager = node("nav", "", "lh-project-pages");
      pager.setAttribute("aria-label", "\u97F3\u4E50\u9879\u76EE\u5206\u9875");
      const pageLabel = node("span");
      pageLabel.setAttribute("aria-live", "polite");
      let page = 0, capacity = 1, paintedStart = -1, paintedEnd = -1;
      const move = (direction) => {
        const next2 = (page + direction) * capacity;
        if (next2 < 0 || next2 >= this.projects.length) return;
        this.projectOffset = next2;
        layout();
      };
      const previous = button2("\u2039", () => move(-1));
      const next = button2("\u203A", () => move(1));
      for (const [control, name] of [[previous, "\u4E0A\u4E00\u9875\u9879\u76EE"], [next, "\u4E0B\u4E00\u9875\u9879\u76EE"]]) {
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
        projects.style.setProperty(
          "--lh-project-ideal",
          heading.offsetHeight + idealRows * (142 + gap) + (this.projects.length > columns * idealRows ? 38 + gap : 0) + "px"
        );
        const rowsIn = (height2) => Math.max(1, Math.min(maxRows, Math.floor((height2 + gap) / (minCardHeight + gap))));
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
        pageLabel.textContent = page + 1 + " / " + pages;
        if (start === paintedStart && end === paintedEnd) return;
        paintedStart = start;
        paintedEnd = end;
        const focusedProject = gallery.contains(document.activeElement) && document.activeElement.dataset.project;
        this.releaseCovers();
        gallery.replaceChildren(...this.projects.slice(start, end).map((project) => this.projectCard(project)));
        if (focusedProject) {
          const replacement = Array.from(gallery.children).find((card) => card.dataset.project === focusedProject);
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
        const project = this.projects.find((row) => row.id === current.project.id);
        const song = project?.songs.find((row) => row.id === current.song.id);
        const version = song?.versions.find((row) => row.id === current.version.id);
        if (previewPath(version) !== current.path) this.audition.clear();
      }
      const page = node("section", "", "lh-project-layout");
      page.dataset.pane = "projects";
      const projects = node("section", "", "lh-projects");
      projects.id = "lh-projects-pane";
      const heading = node("div", "", "lh-project-heading");
      const title = node("h2", "\u6211\u7684\u9879\u76EE");
      title.append(node("span", String(this.projects.length), "lh-project-count"));
      heading.append(title, button2("\u5237\u65B0", () => void this.activate(this.navigation), "lh-project-refresh"));
      projects.append(heading);
      const updates = node("aside", "", "lh-feature-list");
      updates.id = "lh-features-pane";
      updates.append(node("h2", "IMW \u529F\u80FD"));
      const mosaic = node("div", "", "lh-feature-grid");
      mosaic.id = "lh-feature-grid";
      mosaic.dataset.feature = "master";
      const trim = featureSelection(this.projects, "trim");
      const inUse = savedProject(this.projects);
      const forSongs = inUse?.songs.length ? inUse : this.projects.find((project) => project.songs.length);
      mosaic.append(
        masterPromotion(this.navigation, this.projects),
        soloPromotion(this.navigation, this.projects),
        compactPromotion(
          "trim",
          "\u9009\u533A\u526A\u8F91",
          "\u4ECE\u4E24\u7AEF\u81EA\u7531\u88C1\u9009\u533A",
          "\u6253\u5F00\u7F16\u8F91\u5668",
          () => this.navigation.openStudio?.(trim),
          trim
        ),
        compactPromotion(
          "versions",
          "\u6B4C\u66F2\u7248\u672C",
          "\u5207\u6362\u8BD5\u542C\u4E0E\u5206\u8F68\u7248\u672C",
          "\u67E5\u770B\u7248\u672C",
          () => this.navigation.openSongs?.(forSongs.id),
          forSongs
        )
      );
      const featurePages = node("nav", "", "lh-feature-pages");
      featurePages.setAttribute("aria-label", "IMW \u529F\u80FD\u5206\u9875");
      for (const [key, label] of [["master", "\u6BCD\u5E26"], ["solo", "\u72EC\u542C"], ["trim", "\u526A\u8F91"], ["versions", "\u7248\u672C"]]) {
        const toggle = button2(label, () => {
          mosaic.dataset.feature = key;
          for (const item of featurePages.children) item.setAttribute("aria-pressed", String(item === toggle));
        });
        toggle.setAttribute("aria-controls", mosaic.id);
        toggle.setAttribute("aria-pressed", String(mosaic.dataset.feature === key));
        featurePages.append(toggle);
      }
      updates.append(featurePages, mosaic);
      const sections = node("nav", "", "lh-home-sections");
      sections.setAttribute("aria-label", "L-unify \u9996\u9875\u533A\u57DF");
      const library = node("div", "", "lh-home-library");
      const recent = node("section", "", "lh-recent");
      recent.id = "lh-recent-pane";
      const rows = recentSongs(this.projects);
      library.toggleAttribute("data-new-songs", rows.length > 0);
      library.append(projects, recent);
      for (const [key, label, panel] of [["projects", "\u9879\u76EE", projects], ["recent", "\u6700\u8FD1\u751F\u6210", recent], ["features", "IMW \u529F\u80FD", updates]]) {
        const toggle = button2(label, () => {
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
      else projects.append(node("p", "\u5C1A\u65E0\u767B\u8BB0\u7684\u97F3\u4E50\u9879\u76EE\u3002", "mec-empty"), this.assetAction());
      this.mountRecent(recent, rows);
    }
    close() {
      this.gallerySize?.disconnect();
      this.recentSize?.disconnect();
      clearInterval(this.bannerTimer);
      this.releaseCovers(this.recentCovers);
      super.close();
    }
  };
  function previewPath(version) {
    if (!version || version.pending || version.paintOnly) return "";
    if (version.previewAAC) return version.previewAAC;
    const track = version.tracks.length === 1 && version.tracks[0];
    if (!track || track.start !== 0 || track.sourceIn !== 0) return "";
    return track.mediaType === "audio/wav" ? track.url.replace(/^\/source\//, "/song-preview/") : track.url;
  }
  var SongAudition = class {
    constructor(document2) {
      this.audio = document2.createElement("audio");
      this.audio.preload = "none";
      this.audio.hidden = true;
      this.audio.setAttribute("aria-hidden", "true");
      for (const event of ["loadedmetadata", "timeupdate", "pause", "play", "ended", "seeked"]) {
        this.audio.addEventListener(event, () => {
          if (this.url) this.sync();
        });
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
        }
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
      if (!path || path === this.choice?.path && this.pending) return;
      const failed = (choice2) => {
        if (this.page && choice2 === this.choice) this.page.status.textContent = "\u6682\u65F6\u65E0\u6CD5\u8BD5\u542C\u6B64\u7248\u672C\u3002";
      };
      if (path === this.choice?.path && this.audio.hasAttribute("src")) {
        const choice2 = this.choice;
        if (!this.audio.paused) this.audio.pause();
        else await this.audio.play().catch(() => failed(choice2));
        return;
      }
      this.pending?.abort();
      const choice = this.choice = { project, song, version, path };
      const request = this.pending = new AbortController();
      this.releaseSource();
      this.sync();
      try {
        const response2 = await studioFetch(path, { signal: request.signal });
        if (!response2.ok) throw Error("\u9884\u89C8\u4E0D\u53EF\u8BFB");
        const blob = await response2.blob();
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
  };
  var songSorts = [
    ["original", "\u539F\u987A\u5E8F"],
    ["recent", "\u6700\u8FD1\u66F4\u65B0"],
    ["oldest", "\u6700\u65E9\u66F4\u65B0"],
    ["name", "\u540D\u79F0 A\u2013Z"],
    ["reverse", "\u540D\u79F0 Z\u2013A"]
  ];
  var byName = new Intl.Collator("zh-CN", { numeric: true });
  function selectField(id, label, options) {
    const field = node("select");
    field.id = id;
    field.setAttribute("aria-label", label);
    for (const [value, title] of options) field.add(new Option(title, value));
    return field;
  }
  var SongLibrary = class extends MusicPage {
    constructor(container, navigation, audition2) {
      super(container, "\u6B4C\u66F2\u5217\u8868", "wbMusicSongsTitle", navigation, audition2.audio);
      this.container.classList.add("mec-song-library");
      this.audition = audition2;
      this.openedProject = readPreference("mec-library-project", "");
      this.songOrder = "original";
      this.query = "";
      this.category = "";
    }
    current() {
      if (this.switchingProject) return {};
      const project = this.projects.find((item) => item.id === this.openedProject);
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
      const requested = this.projects.find((item) => item.id === this.requestedProject);
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
      else this.content.append(node("p", "\u5C1A\u65E0\u767B\u8BB0\u7684\u97F3\u4E50\u9879\u76EE\u3002", "mec-empty"), this.assetAction());
      this.audition.sync();
    }
    renderWorkspace(project, song, version, focus) {
      const heading = node("div", "", "mec-workspace-heading");
      const back = button2("\u2039", () => this.navigation.openHome?.(), "project-pill mec-back");
      back.setAttribute("aria-label", "\u8FD4\u56DE L-unify \u9879\u76EE\u9996\u9875");
      heading.append(
        back,
        node("h2", project.name),
        node("span", project.songs.length + " \u9996\u6B4C\u66F2"),
        button2("\u5237\u65B0\u6B4C\u5355", () => void this.activate(this.navigation), "project-pill")
      );
      const workspace = node("section", "", "workspace");
      workspace.id = "studioWorkspace";
      const sidebar = node("nav");
      sidebar.id = "studioSidebar";
      sidebar.setAttribute("aria-label", "\u9879\u76EE\u5217\u8868");
      for (const item of this.projects) {
        const entry = button2(item.name, () => {
          if (item !== project) this.openProject(item);
        }, "project-pill");
        entry.dataset.project = item.id;
        entry.setAttribute("aria-pressed", String(item === project));
        sidebar.append(entry);
      }
      const list = node("section", "", "song-workspace");
      const filters = node("div", "", "workspace-controls");
      const switcher = selectField("studioProjectSelect", "\u5207\u6362\u9879\u76EE", this.projects.map((item) => [item.id, item.name]));
      switcher.value = project.id;
      switcher.onchange = () => this.openProject(this.projects.find((item) => item.id === switcher.value));
      const projectControls = node("div", "", "mec-mobile-project");
      const lyricsJump = button2("\u6B4C\u8BCD", () => {
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
      search.placeholder = "\u641C\u7D22\u5F53\u524D\u9879\u76EE\u6B4C\u66F2\u6216\u6B4C\u8BCD";
      search.setAttribute("aria-label", "\u641C\u7D22\u6B4C\u66F2");
      const sort = selectField("studioSongSort", "\u6B4C\u66F2\u6392\u5E8F", songSorts);
      sort.value = this.songOrder;
      const sortLabel = node("label", "\u6392\u5E8F", "song-sort");
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
      search.oninput = () => {
        this.query = search.value;
        this.renderSongs(project, song);
      };
      sort.onchange = () => {
        this.songOrder = sort.value;
        this.renderSongs(project, song);
      };
      this.renderSongs(project, song);
      if (song) this.renderDetails(project, song, version);
      if (focus?.id === "lh-version") this.details.querySelector("#lh-version")?.focus({ preventScroll: true });
      else if (focus?.closest(".lh-card")) {
        const id = focus.closest(".lh-card").dataset.song;
        const card = [...this.cards.children].find((item) => item.dataset.song === id);
        card?.querySelector(focus.classList.contains("lh-cover") ? ".lh-cover" : ".lh-song-pick")?.focus({ preventScroll: true });
      }
    }
    categoryControls(project, draw) {
      const bar = node("div");
      bar.id = "studioCategories";
      const categories = [...new Set(project.songs.map((song) => song.category).filter(Boolean))];
      const chips = [["", "\u5168\u90E8"], ...categories.map((label) => ["c:" + label, label])];
      if (project.songs.some((song) => song.versions.some((take) => take.lyrics))) chips.push(["lyrics", "\u6709\u6B4C\u8BCD"]);
      if (project.songs.some((song) => song.versions.some((take) => previewPath(take)))) chips.push(["audio", "\u6709\u97F3\u9891"]);
      if (project.songs.some((song) => song.versions.some((take) => take.cover))) chips.push(["cover", "\u6709\u5C01\u9762"]);
      if (chips.length === 1) return bar;
      for (const [value, label] of chips) {
        const chip = button2(label, () => {
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
      const songs2 = project.songs.filter((song) => {
        const version = preferredVersion(project, song);
        const hasQuery = !query || [song.name, version?.lyrics].some((value) => value?.toLocaleLowerCase().includes(query));
        return hasQuery && (this.category === "" || this.category === "c:" + song.category || this.category === "lyrics" && Boolean(version?.lyrics) || this.category === "audio" && Boolean(previewPath(version)) || this.category === "cover" && Boolean(version?.cover));
      });
      if (this.songOrder === "name" || this.songOrder === "reverse") {
        const direction = this.songOrder === "name" ? 1 : -1;
        songs2.sort((a, b) => direction * byName.compare(a.name, b.name));
      } else if (this.songOrder === "recent" || this.songOrder === "oldest") {
        const direction = this.songOrder === "oldest" ? 1 : -1;
        songs2.sort((a, b) => a.updatedAt && b.updatedAt ? direction * (a.updatedAt - b.updatedAt) : Number(Boolean(b.updatedAt)) - Number(Boolean(a.updatedAt)));
      }
      this.cards.replaceChildren(...songs2.map((song) => this.createCard(project, song, song === selectedSong)));
      if (!songs2.length) {
        this.cards.append(node("p", project.songs.length ? "\u6CA1\u6709\u627E\u5230\u7B26\u5408\u6761\u4EF6\u7684\u6B4C\u66F2\u3002" : "\u6B64\u9879\u76EE\u6682\u65E0\u6B4C\u66F2\u3002", "mec-empty"));
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
      const play = button2("", () => select(true), "lh-cover embedded-cover");
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
      const icon2 = node("span", "", "lh-play-icon");
      icon2.setAttribute("aria-hidden", "true");
      play.append(icon2);
      const title = button2(song.name, select, "lh-song-pick");
      title.setAttribute("aria-pressed", String(current));
      const details = node("div", "", "lh-song-content embedded-song-info");
      const origin = version?.source || (version?.localImport ? "\u672C\u5730\u5BFC\u5165" : "");
      const reference = song.reference ?? (/^song-[a-f0-9]{32}$/.test(song.id) ? "" : song.id);
      if (reference) details.append(node("small", reference));
      details.append(title);
      if (version) details.append(node("p", origin && !version.name.startsWith(origin) ? origin + " \xB7 " + version.name : version.name));
      if (song.credits) details.append(node("p", song.credits));
      card.append(play, details);
      if (song.note) card.append(node("p", song.note, "embedded-note"));
      card.onclick = (event) => {
        if (!event.target.closest("button")) select();
      };
      return card;
    }
    renderDetails(project, song, version) {
      this.details.append(node("h2", song.name));
      if (!version) return;
      if (song.credits) this.details.append(node("p", song.credits, "credits"));
      const field = node("label", "\u7248\u672C", "lh-version");
      const select = node("select");
      select.id = "lh-version";
      for (const take of song.versions) select.add(new Option(take.name + (song.explicit === take.id ? " \xB7 \u5DF2\u91C7\u7528" : ""), take.id));
      select.value = version.id;
      select.onchange = () => {
        const target = song.versions.find((take) => take.id === select.value);
        if (!target) return;
        this.audition.clear();
        this.choose(project, song, target);
        this.render();
      };
      field.append(select);
      const launch = button2("\u8FDB\u5165 IMW", () => this.navigation.openStudio?.(selection(project, song, version)));
      this.details.append(field, launch, this.mvAction(project, song, version));
      if (version.stemState === "partial") this.details.append(node("p", "\u90E8\u5206\u5206\u8F68\u53EF\u7528", "lh-stems-status"));
      this.details.append(this.productionActions(project, song, version));
      if (version.lyrics) this.details.append(node("pre", version.lyrics, "lh-lyrics"));
    }
    mvAction(project, song, version) {
      const box = node("div", "", "lh-mv-action");
      const target = selection(project, song, version);
      const scope = selectField("lh-mv-scope", "MV \u8303\u56F4", [["all", "\u6574\u9996"], ["window", "\u9009\u53D6\u7247\u6BB5"]]);
      const tracks = version.tracks ?? [];
      const available = !version.pending && tracks.length > 0;
      const limit = Math.round(tracks.reduce((end2, track) => Math.max(end2, track.start + track.duration), 0) * 1e3);
      const range = node("div", "", "lh-mv-range");
      const secondsField = (title, value) => {
        const label = node("label", title);
        const input = node("input");
        input.type = "number";
        input.min = "0";
        input.max = String(limit / 1e3);
        input.step = "0.001";
        input.value = String(value);
        label.append(input);
        range.append(label);
        return input;
      };
      const start = secondsField("\u4ECE\uFF08\u79D2\uFF09", 0);
      const end = secondsField("\u5230\uFF08\u79D2\uFF09", limit / 1e3);
      range.hidden = true;
      scope.onchange = () => {
        range.hidden = scope.value !== "window";
      };
      const notice = node("p");
      notice.setAttribute("role", "status");
      const create = button2("\u7528\u8FD9\u7248\u505A MV", async () => {
        const request = this.request;
        const current = () => activePage === this && request === this.request && create.isConnected;
        const window2 = scope.value === "window" ? {
          start_ms: Math.round(start.valueAsNumber * 1e3),
          end_ms: Math.round(end.valueAsNumber * 1e3)
        } : null;
        if (window2 && !(start.validity.valid && end.validity.valid && Number.isSafeInteger(window2.start_ms) && Number.isSafeInteger(window2.end_ms) && window2.start_ms >= 0 && window2.end_ms <= limit && window2.start_ms < window2.end_ms)) {
          notice.textContent = "\u8BF7\u9009\u62E9\u6B4C\u66F2\u65F6\u957F\u5185\u7684\u7247\u6BB5\uFF0C\u7EC8\u70B9\u987B\u665A\u4E8E\u8D77\u70B9\u3002";
          return;
        }
        create.disabled = true;
        notice.textContent = "\u6B63\u5728\u6838\u5BF9\u97F3\u9891\u5E76\u6253\u5F00\u89C6\u9891\u526A\u8F91\u2026";
        try {
          const result = await studioAction({ action: "start_mv", ...target, window: window2 ?? "whole_song" });
          if (!current()) return;
          if (result.project_id !== target.project || !/^[a-f0-9]{32}$/.test(result.work_id) || !(result.timeline_version > 0)) throw Error("music_mv_timeline_unconfirmed");
          await this.navigation.openMV(result, target);
        } catch (error) {
          if (current()) notice.textContent = {
            studio_media_changed: "\u8FD9\u7248\u97F3\u9891\u5DF2\u53D8\u5316\uFF0C\u8BF7\u5237\u65B0\u5E76\u6838\u5BF9\u7248\u672C\u3002",
            music_mv_full_mix_required: "\u8BF7\u9009\u5B8C\u6574\u6DF7\u97F3\u6216\u5DF2\u8F93\u51FA\u7684\u6BCD\u5E26\u7248\u672C\u3002",
            music_mv_range_invalid: "\u7247\u6BB5\u8D85\u51FA\u672C\u673A\u6B4C\u66F2\u65F6\u957F\u3002",
            music_mv_compatible_mix_required: "\u8BF7\u9009\u672C\u5730 MP3\u3001M4A \u6216 WAV \u5B8C\u6574\u6DF7\u97F3\u3002"
          }[error.message] || "\u6682\u65F6\u65E0\u6CD5\u786E\u8BA4\u526A\u8F91\u5DF2\u4FDD\u5B58\u3002\u8BF7\u6838\u5BF9\u672C\u673A\u97F3\u9891\u540E\u7528\u540C\u4E00\u7248\u672C\u91CD\u8BD5\u3002";
        } finally {
          create.disabled = false;
        }
      });
      create.disabled = !available;
      if (available) box.append(scope, range);
      else notice.textContent = version.pending ? "\u97F3\u9891\u5C31\u7EEA\u540E\u53EF\u4EE5\u5236\u4F5C MV\u3002" : "\u8BF7\u5148\u5F52\u6863\u8FD9\u7248\u97F3\u9891\u3002";
      box.append(create, notice);
      return box;
    }
    productionActions(project, song, version) {
      const menu = node("details", "", "lh-production");
      menu.append(node("summary", "\u5728 Codex \u4E2D\u5236\u4F5C"));
      const controls = node("div");
      const notice = node("p");
      notice.setAttribute("role", "status");
      const fallback = node("code");
      fallback.hidden = true;
      const target = selection(project, song, version);
      const actions = [["prepare", "\u6574\u7406\u5236\u4F5C\u7A3F"], ["generate", "\u751F\u6210\u6216\u7EED\u67E5"]];
      if (version.providerClip && !version.sourceVersion) actions.push(["archive", "\u67E5\u8BE2\u6216\u63A5\u7EED\u5F52\u6863"]);
      if (version.provider === "suno" && version.providerClip && !version.sourceVersion) actions.push(["stems", "\u5BFC\u5165\u5DF2\u6709\u5206\u8F68"]);
      for (const [action, title] of actions) {
        const control = button2(title, async () => {
          fallback.hidden = true;
          const handoff = this.navigation.canStartProduction?.() && this.navigation.startProduction;
          if (!handoff) {
            notice.textContent = "\u53EF\u628A\u8FD9\u6761\u6307\u4EE4\u5E26\u5230 Codex \u804A\u5929\u3002";
            fallback.textContent = "\u4F7F\u7528 $wechat-ecosystem:lunify-music-production " + JSON.stringify({ action, ...target });
            fallback.hidden = false;
            return;
          }
          for (const entry of controls.children) entry.disabled = true;
          notice.textContent = "\u6B63\u5728\u4EA4\u7ED9 Codex\u2026";
          try {
            await this.navigation.startProduction(action, target);
            notice.textContent = "\u5DF2\u4EA4\u7ED9 Codex\uFF0C\u7ED3\u679C\u53EF\u4ECE\u6B4C\u5355\u5237\u65B0\u8BFB\u56DE\u3002";
          } catch {
            notice.textContent = "\u804A\u5929\u4EA4\u63A5\u6682\u4E0D\u53EF\u7528\u3002\u8BF7\u5728 Codex \u804A\u5929\u4F7F\u7528\u4E0B\u65B9\u6307\u4EE4\u3002";
            fallback.textContent = "\u4F7F\u7528 $wechat-ecosystem:lunify-music-production " + JSON.stringify({ action, ...target });
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
        const state = control.disabled ? "\u53EF\u8FDB\u5165 IMW \u67E5\u770B" : playing ? "\u6682\u505C\u8BD5\u542C" : loading ? "\u6B63\u5728\u8BFB\u53D6" : "\u8BD5\u542C";
        control.setAttribute("aria-label", state + " " + control.dataset.title);
        control.setAttribute("aria-pressed", String(Boolean(playing)));
        control.title = state + " " + control.dataset.title;
        control.querySelector(".lh-play-icon").textContent = playing ? "\u2161" : loading ? "\u2026" : control.disabled ? "\xB7" : "\u25B6";
      }
    }
  };
  var overview;
  var songs;
  var activePage;
  var audition;
  function songAudition(container) {
    const document2 = container.ownerDocument;
    audition ??= new SongAudition(document2);
    const mount = document2.getElementById("wbMusicSongs") ?? container;
    if (audition.audio.parentNode !== mount) mount.append(audition.audio);
    return audition;
  }
  function switchPage(page, navigation) {
    if (activePage && activePage !== page) activePage.close();
    activePage = page;
    audition.activate(page);
    void page.activate(navigation);
  }
  function openHome(container, navigation = {}) {
    if (overview?.container !== container) overview = new Overview(container, navigation, songAudition(container));
    switchPage(overview, navigation);
  }
  function openSongs(container, navigation = {}, project) {
    if (songs?.container !== container) songs = new SongLibrary(container, navigation, songAudition(container));
    if (!project && activePage !== songs) project = audition.choice?.project.id;
    if (activePage !== songs || songs.switchingProject || project && project !== songs.openedProject) {
      songs.prepareProject(project);
    }
    switchPage(songs, navigation);
  }
  function homeSelection() {
    return activePage === songs ? songs?.selected() ?? null : null;
  }
  function closeHome(next) {
    activePage?.close();
    activePage = null;
    if (next !== "l-unify-home" && next !== "l-unify-songs") audition?.deactivate();
  }

  // assets/studio/frame-ruler.mjs
  var choices = /* @__PURE__ */ new Map([
    ["auto", "\u8DDF\u968F\u7D20\u6750"],
    ["24000/1001", "23.976"],
    ["24/1", "24"],
    ["25/1", "25"],
    ["30000/1001", "29.97 NDF"],
    ["30000/1001 DF", "29.97 DF"],
    ["30/1", "30"],
    ["50/1", "50"],
    ["60000/1001", "59.94 NDF"],
    ["60000/1001 DF", "59.94 DF"],
    ["60/1", "60"]
  ]);
  function frameRate(value) {
    const parts = /^(\d{1,8})\/(\d{1,8})( DF)?$/.exec(value ?? "");
    const n = Number(parts?.[1]), d = Number(parts?.[2]);
    if (!d || n / d < 1 || n / d > 240) return { n: 30, d: 1, nominal: 30, drop: 0 };
    const nominal = Math.round(n / d);
    const drop = parts[3] && (nominal === 30 || nominal === 60) && n * 1001 === nominal * 1e3 * d ? nominal / 15 : 0;
    return { n, d, nominal, drop };
  }
  function frameLabel(frame, rate) {
    let count = Math.max(0, Math.floor(frame));
    const { nominal, drop } = rate;
    if (drop) {
      const minute = nominal * 60 - drop, ten = minute * 10 + drop;
      count += drop * (9 * Math.floor(count / ten) + Math.max(0, Math.floor((count % ten - drop) / minute)));
    }
    const seconds = Math.floor(count / nominal);
    const two = (number) => String(number).padStart(2, "0");
    return [Math.floor(seconds / 3600), Math.floor(seconds / 60) % 60, seconds % 60].map(two).join(":") + (drop ? ";" : ":") + two(count % nominal);
  }
  function frameAt(seconds, rate) {
    return Math.max(0, Math.floor((seconds + 500001e-9) * rate.n / rate.d));
  }
  function mountFrameRuler(studio) {
    const $ = studio.$, ruler = $("ruler"), seek = $("seek"), menu = $("imw-frame-rate");
    const lane = $("lane");
    const grid = document.createElementNS("http://www.w3.org/2000/svg", "svg");
    const lines = document.createElementNS(grid.namespaceURI, "path");
    grid.setAttribute("class", "frame-grid");
    grid.setAttribute("aria-hidden", "true");
    grid.append(lines);
    lane.prepend(grid);
    const cursor = document.createElement("span");
    cursor.className = "frame-time";
    const originalTitle = ruler.title;
    $("ruler-unit").before(cursor);
    menu.replaceChildren(...Array.from(choices, ([value, label]) => new Option(label, value)));
    const scroll = $("scroll"), zoom = $("imw-frame-zoom");
    let savedScroll = 0, scrollFrame = 0;
    const zoomed = () => zoom.value === "frame";
    let clock, scope = "", selected = "auto", rate = frameRate(), rateKey = "", rendered = "", axis = 0;
    let gesture, moveFrame = 0;
    function draw(length) {
      axis = length || 1;
      if (zoomed()) {
        const value = Math.max(scroll.clientWidth, axis * rate.n / rate.d * 12) + "px";
        if (lane.style.getPropertyValue("--frame-zoom-width") !== value) lane.style.setProperty("--frame-zoom-width", value);
      }
      const width = lane.getBoundingClientRect().width;
      const pixelsPerFrame = width * rate.d / (axis * rate.n);
      if (pixelsPerFrame <= 0) return;
      const viewport = Math.max(1, scroll.clientWidth);
      const page = Math.floor(scroll.scrollLeft / viewport);
      const signature = [width, lane.clientHeight, axis, rateKey, viewport, page].join("/");
      if (signature === rendered) return;
      rendered = signature;
      const firstFrame = Math.max(0, Math.floor((page - 1) * viewport / pixelsPerFrame));
      const origin = firstFrame * pixelsPerFrame;
      const lastFrame = Math.min(Math.ceil(axis * rate.n / rate.d), Math.ceil((page + 3) * viewport / pixelsPerFrame));
      grid.style.left = origin + "px";
      grid.style.width = Math.max(0, Math.min(width, lastFrame * pixelsPerFrame) - origin) + "px";
      const divisions = [];
      if (pixelsPerFrame >= 2) {
        for (let i = firstFrame; i < lastFrame; ++i) {
          if (i % rate.nominal) divisions.push("M" + ((i - firstFrame) * pixelsPerFrame + 0.5).toFixed(3) + " 0V" + lane.clientHeight);
        }
      }
      lines.setAttribute("d", divisions.join(""));
      let step = [1, 2, 5, 10, rate.nominal, rate.nominal * 2, rate.nominal * 5].sort((a, b) => a - b).find((frames) => frames * pixelsPerFrame >= 95);
      if (!step) step = rate.nominal * 10 * Math.ceil(95 / (rate.nominal * 10 * pixelsPerFrame));
      const ticks = [];
      const start = Math.max(0, Math.floor((page - 1) * viewport / (step * pixelsPerFrame)) * step);
      const end = Math.min(width - 78, (page + 3) * viewport);
      for (let frame = start; frame * pixelsPerFrame < end; frame += step) {
        const tick = document.createElement("span");
        tick.style.left = 100 * frame * rate.d / (axis * rate.n) + "%";
        tick.textContent = frameLabel(frame, rate);
        ticks.push(tick);
      }
      $("ticks").replaceChildren(...ticks);
      const second = rate.nominal * pixelsPerFrame;
      lane.style.setProperty("--major-step", (second >= 8 ? second : step * pixelsPerFrame) + "px");
      lane.style.setProperty("--frame-pitch", pixelsPerFrame + "px");
      lane.toggleAttribute("data-frame-grid", pixelsPerFrame >= 2);
      lane.removeAttribute("data-detail");
      lane.removeAttribute("data-beat");
      $("ruler-unit").textContent = "\u65F6\u95F4";
    }
    function sync(next) {
      if (!next) return;
      clock = next;
      const key = next.project && next.work ? next.project + "/" + next.work : "";
      if (key !== scope) {
        cancelGesture();
        scope = key;
        const saved = scope && readPreference("frame-rate/" + scope, "auto");
        selected = choices.has(saved) ? saved : "auto";
        menu.value = selected;
      }
      const source = next.frameRate;
      const fps = selected === "auto" ? source || "30/1" : selected;
      if (fps !== rateKey || !cursor.getAttribute("data-shown")) {
        cancelGesture();
        rateKey = fps;
        rate = frameRate(fps);
        rendered = "";
        const origin = source ? (rate.n / rate.d).toFixed(3).replace(/\.?0+$/, "") : "\u9ED8\u8BA4 30";
        menu.options[0].text = selected === "auto" ? "\u8DDF\u968F\u7D20\u6750\uFF08" + origin + " fps\uFF09" : "\u8DDF\u968F\u7D20\u6750";
        ruler.title = "\u70B9\u51FB\u5B9A\u4F4D\uFF0C\u6309\u4F4F\u62D6\u52A8\u626B\u7247\uFF0C\u2190 / \u2192 \u9010\u5E27\uFF0C\u7A7A\u683C\u64AD\u653E\u6216\u6682\u505C";
        cursor.setAttribute("data-shown", "true");
      }
      document.addEventListener("keydown", stepWithKeyboard);
      draw(studio.imw.displayLength(next));
      const label = frameLabel(frameAt(next.seconds || 0, rate), rate);
      if (cursor.textContent !== label) cursor.textContent = label;
      seek.setAttribute("aria-valuetext", label);
    }
    function clampFrame(frame) {
      const last = Math.max(0, Math.ceil(clock.length * rate.n / rate.d - 1e-8) - 1);
      return Math.max(0, Math.min(last, frame));
    }
    function seekFrame(frame, scrubbing = false) {
      const target = clampFrame(frame) * rate.d / rate.n;
      const engine2 = globalThis.OAIMWVideo;
      const seekTo = scrubbing && engine2?.scrubFrame || engine2?.seekFrame || engine2?.seek;
      seekTo?.(target);
    }
    function pointerFrame(event) {
      const rect = ruler.getBoundingClientRect();
      const seconds = (event.clientX - rect.left) * axis / Math.max(1, rect.width);
      return clampFrame(Math.round(seconds * rate.n / rate.d));
    }
    function cancelGesture() {
      cancelAnimationFrame(moveFrame);
      moveFrame = 0;
      const previous = gesture;
      gesture = null;
      if (previous && ruler.hasPointerCapture(previous.id)) ruler.releasePointerCapture(previous.id);
    }
    function stepWithKeyboard(event) {
      if (!studio.isConnected || !studio.imw?.enabled() || studio.closest("[hidden]") || !clock?.ready || !clock.length || gesture || event.defaultPrevented || event.isComposing || event.altKey || event.metaKey || event.ctrlKey || event.shiftKey) return;
      if (event.key !== "ArrowLeft" && event.key !== "ArrowRight") return;
      const target = event.composedPath()[0];
      if (target !== seek && (target.isContentEditable || target.closest?.("#regions .clip-group,.trim-handle,input,textarea,select,[role=slider],[role=spinbutton],[role=menu],[role=listbox],[role=tablist],[role=separator],dialog,[popover]:popover-open"))) return;
      event.preventDefault();
      const current = globalThis.OAIMWVideo?.state?.()?.seconds ?? clock.seconds;
      seekFrame(frameAt(current, rate) + (event.key === "ArrowRight" ? 1 : -1));
    }
    zoom.onchange = () => {
      if (!clock) return;
      if (zoomed()) savedScroll = scroll.scrollLeft;
      studio.toggleAttribute("data-frame-zoom", zoomed());
      rendered = "";
      draw(studio.imw.displayLength(clock));
      scroll.scrollLeft = zoomed() ? Math.max(0, clock.seconds / axis * $("lane").clientWidth - scroll.clientWidth / 2) : savedScroll;
      studio.paint();
    };
    scroll.addEventListener("scroll", () => {
      if (!studio.imw?.enabled() || scrollFrame) return;
      scrollFrame = requestAnimationFrame(() => {
        scrollFrame = 0;
        if (studio.imw.enabled()) draw(axis);
      });
    }, { passive: true });
    menu.onchange = () => {
      if (!clock || !scope) return;
      selected = menu.value;
      rememberPreference("frame-rate/" + scope, selected);
      sync(clock);
    };
    seek.addEventListener("blur", () => ruler.removeAttribute("data-pointer-seek"));
    ruler.addEventListener("pointerdown", (event) => {
      if (!studio.imw?.enabled() || !clock?.ready || !clock.length || !event.isPrimary || event.button !== 0) return;
      event.preventDefault();
      cancelGesture();
      const frame = pointerFrame(event);
      gesture = { id: event.pointerId, next: frame, shown: frame, moved: false };
      ruler.setPointerCapture(event.pointerId);
      ruler.setAttribute("data-pointer-seek", "");
      seek.focus({ preventScroll: true });
      seekFrame(frame);
    });
    ruler.addEventListener("pointermove", (event) => {
      if (gesture?.id !== event.pointerId) return;
      gesture.next = pointerFrame(event);
      if (moveFrame || gesture.next === gesture.shown) return;
      moveFrame = requestAnimationFrame(() => {
        moveFrame = 0;
        if (!gesture || gesture.next === gesture.shown) return;
        gesture.shown = gesture.next;
        gesture.moved = true;
        seekFrame(gesture.shown, true);
      });
    });
    function finishGesture(event) {
      if (gesture?.id !== event.pointerId) return;
      const frame = event.type === "pointerup" ? pointerFrame(event) : gesture.next;
      const settle = gesture.moved || frame !== gesture.shown;
      cancelGesture();
      if (settle) seekFrame(frame);
    }
    for (const type of ["pointerup", "pointercancel", "lostpointercapture"]) ruler.addEventListener(type, finishGesture);
    ruler.addEventListener("click", (event) => {
      if (!studio.imw?.enabled() || !clock?.ready || !clock.length) return;
      event.stopImmediatePropagation();
      if (!event.detail && event.clientX) seekFrame(pointerFrame(event));
    }, true);
    return { draw, sync, audioScroll: () => zoomed() ? savedScroll : scroll.scrollLeft, reset() {
      cancelGesture();
      document.removeEventListener("keydown", stepWithKeyboard);
      rendered = "";
      ruler.title = originalTitle;
      cursor.removeAttribute("data-shown");
      $("lane").removeAttribute("data-frame-grid");
      $("lane").style.removeProperty("--frame-zoom-width");
      studio.removeAttribute("data-frame-zoom");
      zoom.value = "audio";
    } };
  }

  // assets/studio/clip-editing.mjs
  var frameEpsilon = 1e-6;
  var ceilFrame = (frame) => Math.ceil(frame - frameEpsilon);
  function change(original, action, delta, {
    rate,
    frames,
    left = 0,
    right = Infinity,
    timelineLimit,
    startLimit = timelineLimit,
    reserveTail = false,
    minFrames = 1
  }) {
    const changed = { ...original };
    if (action === "move") {
      const rightMargin = reserveTail ? Math.max(original.tail, original.silenceTail) : original.silenceTail;
      const lastStart = Math.min(startLimit, timelineLimit - original.duration - rightMargin, right - original.duration);
      changed.start = Math.max(left + original.silenceHead, Math.min(lastStart, original.start + delta));
      return changed;
    }
    if (!rate || !frames || !delta) return changed;
    const isHead = action === "head";
    const silence = isHead ? "silenceHead" : "silenceTail";
    if (original[silence] > 0) {
      const inward = Math.max(0, isHead ? delta : -delta);
      const removed = Math.min(original[silence], Math.round(inward * rate) / rate);
      changed[silence] -= removed;
      if (changed[silence] > 0) return changed;
      delta += isHead ? -original[silence] : original[silence];
      if ((isHead ? delta : -delta) <= 0) return changed;
    }
    const start = original.sourceIn;
    const end = start + original.duration;
    const sourceStart = start - original.head;
    const sourceEnd = end + original.tail;
    const edge = isHead ? start : end;
    const least = isHead ? Math.max(sourceStart, start + (left - original.start)) : start + minFrames / rate;
    const most = isHead ? Math.min(end, frames / rate) - minFrames / rate : Math.min(sourceEnd, end + (Math.min(right, timelineLimit) - (original.start + original.duration)));
    const lowFrame = Math.max(0, ceilFrame(least * rate));
    const highFrame = Math.min(frames, Math.floor(Math.min(
      most,
      isHead ? start + (startLimit - original.start) : Infinity
    ) * rate + frameEpsilon));
    if (lowFrame > highFrame) return changed;
    const next = Math.max(lowFrame, Math.min(highFrame, Math.round((edge + delta) * rate))) / rate;
    if (Math.abs(next - edge) * rate <= frameEpsilon) return changed;
    if (isHead) {
      changed.start = Math.max(left, original.start + (next - start));
      changed.sourceIn = next;
      changed.duration = end - next;
      changed.head = Math.max(0, next - sourceStart);
    } else {
      changed.duration = next - start;
      changed.tail = Math.max(0, sourceEnd - next);
    }
    return changed;
  }
  function bind(control, { action, read, geometry, constraints, enabled, select, preview, commit, cancel }) {
    const moving = action === "move";
    let drag;
    const editable = () => !control.disabled && (!enabled || enabled());
    const same = (a, b) => Object.keys(a).every((key) => a[key] === b[key]);
    function finish(event, accept) {
      if (!drag || event?.pointerId != null && drag.id !== event.pointerId) return;
      const { original, proposed, id, length } = drag;
      drag = void 0;
      if (control.hasPointerCapture?.(id)) control.releasePointerCapture(id);
      if (!proposed) return;
      const detail = { action, original, length, event };
      if (accept && editable() && !same(original, proposed)) commit(proposed, detail);
      else cancel?.(original, detail);
    }
    function keydown(event) {
      if (event.key === "Escape" && drag) {
        event.preventDefault();
        finish(event, false);
        return;
      }
      if (!editable() || drag || !["ArrowLeft", "ArrowRight"].includes(event.key)) return;
      event.preventDefault();
      const limits = constraints(), rate = limits.rate;
      if (!moving && !rate) return;
      const step = moving ? event.shiftKey ? 1 : 0.25 : (event.shiftKey ? Math.round(rate / 100) : 1) / rate;
      const original = read();
      const next = change(original, action, event.key === "ArrowLeft" ? -step : step, limits);
      if (!same(original, next)) commit(next, { action, original, event });
    }
    function down(event) {
      if (event.button !== 0 || drag || !editable()) return;
      const { width, length } = geometry();
      if (!(width > 0 && length > 0)) return;
      select?.(event);
      drag = { id: event.pointerId, x: event.clientX, original: read(), width, length };
      control.setPointerCapture(event.pointerId);
    }
    function move(event) {
      if (!drag || drag.id !== event.pointerId) return;
      if (!editable()) return finish(event, false);
      const distance = event.clientX - drag.x;
      if (!drag.proposed && (moving ? Math.abs(distance) < 3 : distance === 0)) return;
      const seconds = distance / drag.width * drag.length;
      const delta = moving ? Math.round(seconds * 4) / 4 : seconds;
      if (drag.delta === delta) return;
      drag.delta = delta;
      drag.proposed = change(drag.original, action, delta, constraints());
      preview?.(drag.proposed, { action, original: drag.original, length: drag.length, event });
    }
    function up(event) {
      move(event);
      finish(event, true);
    }
    const abort = (event) => finish(event, false);
    const listeners = { keydown, pointerdown: down, pointermove: move, pointerup: up, pointercancel: abort, lostpointercapture: abort };
    for (const [name, listener] of Object.entries(listeners)) control.addEventListener(name, listener);
    return () => {
      finish(null, false);
      for (const [name, listener] of Object.entries(listeners)) control.removeEventListener(name, listener);
    };
  }
  var clipEditing = Object.freeze({ change, bind });

  // assets/studio/track-colors.mjs
  var anchorHues = [0, 32, 53, 130, 225, 275];
  var weights = [0.2126, 0.7152, 0.0722];
  var minimumBrightness = 0.24;
  function luminance(rgb) {
    return rgb.reduce((total, channel, i) => {
      const value = channel / 255;
      const light = value <= 0.04045 ? value / 12.92 : ((value + 0.055) / 1.055) ** 2.4;
      return total + light * weights[i];
    }, 0);
  }
  function vividColor(hue) {
    const fullColor = [5, 3, 1].map((offset) => {
      const sector = (offset + hue / 60) % 6;
      return 255 * (1 - Math.max(0, Math.min(sector, 4 - sector, 1)));
    });
    const rgbAt = (lift) => fullColor.map((channel) => Math.round(channel + (255 - channel) * lift / 255));
    let low = 0;
    let high = 255;
    while (low < high) {
      const lift = Math.floor((low + high) / 2);
      if (luminance(rgbAt(lift)) >= minimumBrightness) high = lift;
      else low = lift + 1;
    }
    return "#" + rgbAt(low).map((channel) => channel.toString(16).padStart(2, "0")).join("");
  }
  var remainingHues = Array.from({ length: 360 }, (_, i) => i * 137 % 360).filter((hue) => !anchorHues.includes(hue));
  var palette = [...anchorHues, ...remainingHues].map(vividColor);
  function trackColor(slot) {
    return palette[slot % palette.length];
  }
  function trackColorSlots(tracks, saved) {
    const slots = /* @__PURE__ */ new Map();
    const used = /* @__PURE__ */ new Set();
    for (const entry of Array.isArray(saved) ? saved : []) {
      if (!Array.isArray(entry)) continue;
      const [id, slot] = entry;
      if (typeof id !== "string" || !Number.isSafeInteger(slot) || slot < 0 || slots.has(id) || used.has(slot)) continue;
      slots.set(id, slot);
      used.add(slot);
    }
    let next = 0;
    for (const { id } of tracks) {
      if (slots.has(id)) continue;
      while (used.has(next)) next++;
      slots.set(id, next);
      used.add(next);
    }
    return slots;
  }

  // assets/studio/detached-tracks.mjs
  var engine = () => globalThis.OAIMWVideo;
  var time = (ms) => (ms / 1e3).toFixed(3) + " \u79D2";
  var keyOf = (data) => JSON.stringify([data.project, data.work]);
  var laneKey = (row) => JSON.stringify([row.clip_id, row.delivery_id, row.sha256]);
  function mountDetachedTracks(studio) {
    const heads = studio.$("detached-heads"), lanes = studio.$("detached-lanes");
    const tracks = /* @__PURE__ */ new Map(), clips = /* @__PURE__ */ new Map();
    const events = new AbortController();
    let retained, renderedScope = "", lastSelected = "", editFocus = false, geometryStamp = "";
    const snapshot = () => engine()?.detachedAudio?.();
    function scope(data = snapshot()) {
      if (!data?.project || !data.work) return null;
      const { project, work } = data;
      if (studio.imw.enabled()) {
        const body = document.body.dataset;
        if (project === body.imwProject && work === body.imwWork)
          return { project, work, offset: Number(data.offsetSeconds) || 0 };
      } else if (data.folded && Array.isArray(data.selection) && data.selection.length === 3 && data.selection[0] === project && project === studio.project?.id && data.selection[1] === (studio.song?.id || "") && data.selection[2] === (studio.version?.id || "")) {
        return { project, work, offset: Number(data.offsetSeconds) || 0 };
      } else if (retained && retained.project === project && retained.work === work && studio.project?.id === project && (studio.song?.id || "") === retained.song && (studio.version?.id || "") === retained.version) {
        return { project, work, offset: retained.offset };
      }
      return null;
    }
    function remember() {
      const current = scope();
      retained = current && { ...current, song: studio.song?.id || "", version: studio.version?.id || "" };
    }
    function selectionChanged() {
      if (!studio.imw.enabled() && retained && (studio.project?.id !== retained.project || (studio.song?.id || "") !== retained.song || (studio.version?.id || "") !== retained.version)) retained = null;
      refresh();
    }
    function controlsEnabled() {
      const data = snapshot();
      return !!scope(data) && keyOf(data) === renderedScope && !data.busy;
    }
    function edit(id, value) {
      if (!controlsEnabled()) return;
      editFocus = true;
      return engine().editDetached(id, value);
    }
    function cursorMs() {
      return studio.imw.enabled() ? Math.round(1e3 * (engine()?.state?.()?.seconds || 0)) : Math.round(1e3 * (studio.seconds + (scope()?.offset || 0)));
    }
    function split(id) {
      if (id) edit(id, { split_at_ms: cursorMs() });
    }
    function extent() {
      const data = snapshot(), current = scope(data);
      if (!current || !data.rows?.length) return 0;
      const end = Math.max(data.pictureMs || 0, ...data.rows.map((row) => row.start_ms + row.out_ms - row.in_ms));
      return Math.max(0, end / 1e3 - current.offset);
    }
    function displayLength() {
      return studio.imw.enabled() ? studio.imw.displayLength() : studio.rulerLength;
    }
    function place(node2, start, duration, length = displayLength()) {
      if (!(length > 0)) return;
      const offset = studio.imw.enabled() ? 0 : scope()?.offset || 0;
      node2.style.left = 100 * (start - offset) / length + "%";
      node2.style.width = 100 * duration / length + "%";
    }
    function layout() {
      const length = displayLength(), current = scope();
      const stamp = JSON.stringify([renderedScope, length, studio.imw.enabled(), current?.offset]);
      if (stamp === geometryStamp) return;
      geometryStamp = stamp;
      for (const { group, row } of clips.values()) place(group, row.start_ms / 1e3, (row.out_ms - row.in_ms) / 1e3, length);
    }
    function createTrack(key, row, index) {
      const lane = document.createElement("div");
      lane.className = "track-row detached-row";
      lane.setAttribute("role", "group");
      const name = row.title ? "\u539F\u58F0 \xB7 " + row.title : "\u5206\u79BB\u539F\u58F0";
      lane.setAttribute("aria-label", name);
      const activeId = () => {
        const id = snapshot()?.selected;
        return clips.get(id)?.trackKey === key ? id : lane.firstElementChild?.dataset.detachedId;
      };
      const controls = studio.makeTrackHead({
        id: "detached-" + row.id,
        name,
        row: lane,
        expanded: false,
        expand: () => {
        },
        select: () => edit(activeId(), "select"),
        shortcuts: [["\u5728\u64AD\u653E\u5934\u5206\u5272", () => split(activeId())], ["\u79FB\u9664\u7247\u6BB5", () => edit(activeId(), "remove")]]
      });
      const actions = controls.head.querySelector(".track-actions");
      const volume = document.createElement("input");
      volume.type = "range";
      volume.min = "0";
      volume.max = "100";
      volume.step = "1";
      const label = document.createElement("label");
      label.textContent = "\u97F3\u91CF";
      volume.setAttribute("aria-label", name + "\u97F3\u91CF");
      label.append(volume);
      actions.append(label);
      volume.oninput = () => volume.setAttribute("aria-valuetext", volume.value + "%");
      volume.onchange = () => edit(activeId(), { volume: Number(volume.value) });
      lane.style.setProperty("--tone", trackColor(index + 3));
      controls.head.classList.add("detached-head");
      controls.head.style.setProperty("--tone", trackColor(index + 3));
      lanes.append(lane);
      heads.append(controls.head);
      return { lane, head: controls.head, label: controls.label, actions, volume, activeId };
    }
    function createClip(row, track, trackKey) {
      const group = document.createElement("div"), button3 = document.createElement("button"), wave = document.createElement("span");
      group.className = "clip-group";
      group.dataset.detachedId = row.id;
      button3.type = "button";
      button3.className = "clip";
      wave.className = "detached-wave";
      button3.append(wave);
      group.append(button3);
      const item = { row, group, button: button3, wave, trackKey, waveKey: "", dispose: [] };
      const owner = renderedScope;
      const enabled = () => owner === renderedScope && clips.get(row.id) === item && controlsEnabled();
      const value = () => {
        const r = item.row;
        return {
          start: r.start_ms / 1e3,
          sourceIn: r.in_ms / 1e3,
          duration: (r.out_ms - r.in_ms) / 1e3,
          head: r.in_ms / 1e3,
          tail: Math.max(0, r.source_ms - r.out_ms) / 1e3,
          silenceHead: 0,
          silenceTail: 0
        };
      };
      function bind2(control, action) {
        item.dispose.push(clipEditing.bind(control, {
          action,
          enabled,
          read: value,
          geometry: () => ({ width: lanes.getBoundingClientRect().width, length: displayLength() }),
          constraints: () => ({ rate: 1e3, frames: item.row.source_ms, timelineLimit: Infinity }),
          select: () => edit(row.id, "select"),
          preview: (v) => place(group, v.start, v.duration),
          cancel: () => {
            const v = value();
            place(group, v.start, v.duration);
          },
          commit: (v) => {
            if (enabled()) edit(row.id, { start_ms: Math.round(v.start * 1e3), in_ms: Math.round(v.sourceIn * 1e3), out_ms: Math.round((v.sourceIn + v.duration) * 1e3) });
            refresh();
          }
        }));
      }
      button3.onclick = () => edit(row.id, "select");
      bind2(button3, "move");
      for (const [edge, label] of [["head", "\u88C1\u5207\u5165\u70B9"], ["tail", "\u88C1\u5207\u51FA\u70B9"]]) {
        const handle = document.createElement("button");
        handle.type = "button";
        handle.className = "trim-handle " + edge;
        handle.setAttribute("aria-label", label + " \xB7 " + (row.title || "\u5206\u79BB\u539F\u58F0"));
        group.append(handle);
        bind2(handle, edge);
      }
      track.lane.append(group);
      return item;
    }
    function clearClip(id, item) {
      for (const unbind of item.dispose) unbind();
      item.group.remove();
      clips.delete(id);
    }
    function refresh() {
      const data = snapshot(), current = scope(data);
      const next = current ? keyOf(current) : "";
      if (next !== renderedScope) {
        renderedScope = next;
        lastSelected = "";
        editFocus = false;
        for (const [id, item] of clips) clearClip(id, item);
        for (const { lane, head } of tracks.values()) {
          lane.remove();
          head.remove();
        }
        tracks.clear();
      }
      const rows = current ? data.rows || [] : [];
      const ids = new Set(rows.map((row) => row.id)), keys = new Set(rows.map(laneKey));
      for (const [id, item] of clips) if (!ids.has(id)) clearClip(id, item);
      for (const [key, t] of tracks) if (!keys.has(key)) {
        t.lane.remove();
        t.head.remove();
        tracks.delete(key);
      }
      for (const row of rows) {
        const key = laneKey(row);
        if (!tracks.has(key)) tracks.set(key, createTrack(key, row, tracks.size));
        const t = tracks.get(key);
        if (!clips.has(row.id)) clips.set(row.id, createClip(row, t, key));
        const item = clips.get(row.id);
        item.row = row;
        const waveKey = JSON.stringify([row.delivery_id, row.sha256, row.in_ms, row.out_ms, row.volume]);
        if (item.waveKey !== waveKey) {
          item.waveKey = waveKey;
          const wave = document.createElement("span");
          wave.className = "detached-wave";
          item.wave.replaceWith(wave);
          item.wave = wave;
          engine().detachedWave(wave, row.id);
        }
        const selected = data.selected === row.id;
        item.group.toggleAttribute("data-selected", selected);
        item.button.setAttribute("aria-pressed", String(selected));
        item.button.setAttribute("aria-label", (row.title || "\u5206\u79BB\u539F\u58F0") + " \xB7 " + time(row.start_ms) + " \xB7 \u65F6\u957F " + time(row.out_ms - row.in_ms));
        item.button.title = item.button.getAttribute("aria-label");
      }
      for (const t of tracks.values()) {
        const selected = clips.get(data?.selected)?.group.parentElement === t.lane;
        t.head.toggleAttribute("data-selected", selected);
        t.label.setAttribute("aria-pressed", String(selected));
        t.label.toggleAttribute("data-selected", selected);
        const row = clips.get(t.activeId())?.row;
        if (row && studio.shadowRoot.activeElement !== t.volume) t.volume.value = row.volume;
        t.volume.setAttribute("aria-valuetext", t.volume.value + "%");
        t.lane.toggleAttribute("data-monitor-muted", data.sourceAudible === false || row?.volume === 0);
      }
      studio.toggleAttribute("data-detached-audio", !!rows.length);
      geometryStamp = "";
      layout();
      if (data?.selected && data.selected !== lastSelected && clips.has(data.selected)) {
        const panel = studio.$("track-scroll-panel"), row = clips.get(data.selected).group.parentElement;
        requestAnimationFrame(() => {
          if (!row.isConnected || !current || keyOf(current) !== renderedScope) return;
          const box = row.getBoundingClientRect(), viewport = panel.getBoundingClientRect();
          if (box.bottom > viewport.bottom) panel.scrollTop += box.bottom - viewport.bottom;
          else if (box.top < viewport.top) panel.scrollTop += box.top - viewport.top;
        });
      }
      lastSelected = data?.selected || "";
    }
    document.addEventListener("jiusera:detached-audio-change", () => {
      if (!studio.isConnected) return;
      refresh();
      if (!studio.imw.enabled() && extent() > studio.length) studio.grid();
    }, { signal: events.signal });
    document.addEventListener("jiusera:imw-binding", refresh, { signal: events.signal });
    document.addEventListener("keydown", (e) => {
      if (studio.imw.enabled() || !editFocus || !studio.isConnected || !studio.getClientRects().length || !controlsEnabled() || e.defaultPrevented || e.isComposing || e.altKey || !(e.metaKey || e.ctrlKey)) return;
      const target = e.composedPath()[0];
      if (target.closest?.('input,textarea,select,[contenteditable="true"],dialog')) return;
      const key = e.key.toLowerCase();
      if (key !== "z" && key !== "y") return;
      e.preventDefault();
      e.stopPropagation();
      edit(snapshot()?.selected, e.shiftKey || key === "y" ? "redo" : "undo");
    }, { capture: true, signal: events.signal });
    studio.shadowRoot.addEventListener("pointerdown", (e) => {
      editFocus = !!e.target.closest?.("#detached-heads,#detached-lanes");
    }, true);
    studio.shadowRoot.addEventListener("keydown", (e) => {
      if (e.isComposing || e.defaultPrevented || !controlsEnabled() || e.target.closest?.('input, textarea, [contenteditable="true"]')) return;
      const id = e.target.closest?.("[data-detached-id]")?.dataset.detachedId || snapshot()?.selected;
      const command = e.ctrlKey || e.metaKey;
      const onClip = !!e.target.closest?.("#detached-lanes");
      if (onClip && (command && !e.shiftKey && e.key.toLowerCase() === "b" || !command && !e.altKey && e.key.toLowerCase() === "b")) {
        e.preventDefault();
        e.stopPropagation();
        split(id);
        return;
      }
      if (!studio.imw.enabled() && (onClip || e.target.closest?.("#detached-heads")) && e.code === "Space" && !command && !e.altKey && !e.shiftKey) {
        e.preventDefault();
        e.stopPropagation();
        if (!e.repeat) void studio.toggle();
        return;
      }
      if (onClip && !command && !e.altKey) {
        if (e.key === "Delete" || e.key === "Backspace") {
          e.preventDefault();
          e.stopPropagation();
          edit(id, "remove");
        }
      }
    }, true);
    return { scope, extent, refresh, layout, remember, selectionChanged, dispose: () => events.abort() };
  }

  // assets/studio/imw-view.mjs
  function mountVideoView(studio) {
    const $ = studio.$;
    const original = /* @__PURE__ */ new Map();
    let showOriginal = false, activeTrack = "";
    let boundKey = "", lastScale = "", selectedLane = "";
    let audioViewport = 0, viewportGain = 0;
    const audioScale = () => audioViewport * (studio.draft?.zoom || 1) / studio.fitLength;
    const laneHeaders = /* @__PURE__ */ new Map();
    const originalTrack = "@video-original";
    let observer, sourceObserver, projectObserver, resize, frame = 0, sourceFrame = 0;
    let videoProject = "", videoSong = null, archivedInert = false;
    function syncProject() {
      if (!enabled()) return;
      const source = document.getElementById("directorProject");
      const project = videoProject || source?.value || "";
      const option = source && [...source.options].find((o) => o.value === project);
      const name = option?.text || studio.projects?.find((p) => p.id === project)?.name;
      const button3 = $("imw-project");
      button3.textContent = name || (project ? "\u89C6\u9891\u9879\u76EE" : "\u9009\u62E9\u89C6\u9891\u9879\u76EE");
      button3.dataset.project = project;
      button3.title = name ? "\u5207\u6362\u89C6\u9891\u9879\u76EE \xB7 " + name : "\u5207\u6362\u89C6\u9891\u9879\u76EE";
      const s = selection2();
      const matches = videoSong && s && videoSong.project === project && s.project === project && videoSong.song === s.song && videoSong.version === s.version;
      studio.toggleAttribute("data-imw-song", !!matches);
      if (!matches && $("songs").classList.contains("open")) studio.drawer(false);
    }
    function setProject(project, song) {
      videoProject = project || "";
      videoSong = song || null;
      syncProject();
      if (enabled()) updateRows();
    }
    function createLaneHeaders() {
      if (laneHeaders.size) return;
      const seek = () => engine2()?.seek?.(0);
      const definitions = [
        ["video", "\u89C6\u9891", "dmCutStrip", null, [
          ["\u5B9A\u4F4D\u8D77\u70B9", seek]
        ]],
        ["original", "\u955C\u5934\u539F\u58F0", "imw-original-track", "source", [
          ["\u5B9A\u4F4D\u8D77\u70B9", seek],
          ["\u6536\u8D77\u6B64\u8F68", () => {
            showOriginal = false;
            updateRows();
          }]
        ]]
      ];
      for (const [id, name, rowID, bus, shortcuts] of definitions) {
        const row = $(rowID) || document.getElementById(rowID) || $("imw-folded-video");
        const controls = studio.makeTrackHead({
          id: "imw-" + id,
          name,
          row,
          shortcuts,
          expanded: false,
          monitor: bus ? (action) => engine2()?.toggleMonitor?.(bus, action) : null,
          expand: (value) => {
            if (id !== "original") studio.style.setProperty(
              "--imw-" + id + "-row-height",
              value ? "calc(var(--track-height) + var(--track-action-height))" : "var(--track-height)"
            );
            scheduleMeasure();
          },
          select: () => selectLane(id)
        });
        controls.head.id = id === "video" ? "imw-video-label" : "imw-" + id + "-head";
        controls.bus = bus;
        laneHeaders.set(id, controls);
        if (id === "video") {
          controls.label.onclick = () => videoToggle?.click();
          controls.label.setAttribute("aria-controls", "imw-screen");
          controls.label.setAttribute("aria-expanded", "false");
          controls.head.querySelector(".track-actions").hidden = true;
          $("imw-video-header").append(controls.head);
        } else $("imw-lane-labels").append(controls.head);
      }
      for (const [name, slot] of [["video", 4], ["source", 5]])
        studio.style.setProperty("--imw-" + name + "-tone", trackColor(slot));
    }
    function paintSelection() {
      for (const [id, { label }] of laneHeaders) {
        label.toggleAttribute("data-selected", id === selectedLane);
        label.setAttribute("aria-pressed", String(id === selectedLane));
      }
      if (selectedLane) for (const label of studio.trackHeads?.values() || []) {
        label.removeAttribute("data-selected");
        label.setAttribute("aria-pressed", "false");
      }
    }
    function selectLane(id) {
      selectedLane = id;
      paintSelection();
    }
    function monitorHeaders() {
      if (!enabled()) return;
      for (const { bus, solo, mute, ...parts } of laneHeaders.values()) {
        if (!bus) continue;
        const state = engine2()?.monitorState?.(bus);
        const audio = !!document.querySelector("#dmCutStrip .dc-source-wave");
        solo.disabled = mute.disabled = !audio || !state;
        studio.paintTrackMonitor({ ...parts, solo, mute }, state || { audible: true, mute: false, solo: false });
      }
    }
    function sourceRow() {
      sourceFrame = 0;
      if (!enabled()) return;
      const clips = [...document.querySelectorAll("#dmCutStrip button[data-clip]")];
      const available = clips.some((clip) => clip.querySelector(".dc-source-wave"));
      const show = available && showOriginal;
      laneHeaders.get("original").head.hidden = $("imw-original-track").hidden = !show;
      const row = $("imw-original-track");
      row.replaceChildren();
      if (show) {
        let start = 0;
        for (const clip of clips) {
          const width = parseFloat(clip.closest(".clip-group")?.style.width || clip.style.width) || 0;
          const group = document.createElement("div");
          group.className = "clip-group";
          group.style.left = start + "%";
          group.style.width = width + "%";
          group.style.setProperty("--tone", "var(--imw-source-tone)");
          start += width;
          const wave = clip.querySelector(".dc-source-wave");
          const item = document.createElement("button");
          item.className = "clip";
          item.type = "button";
          item.ariaLabel = clip.title || "\u5B9A\u4F4D\u955C\u5934";
          item.onclick = () => {
            clip.click();
            selectLane("original");
          };
          if (wave) {
            const shape = wave.querySelector("svg")?.cloneNode(true);
            if (shape) item.append(shape);
            else item.textContent = wave.textContent;
            item.title = wave.title;
          }
          group.append(item);
          row.append(group);
        }
      }
      const choice = $("imw-add-track");
      choice.hidden = !available || show;
      if (!choice.options.length) choice.add(new Option("\uFF0B \u663E\u793A\u955C\u5934\u539F\u58F0", ""));
      if (choice.options.length === 1) choice.add(new Option("\u955C\u5934\u539F\u58F0", originalTrack));
      choice.value = "";
      monitorHeaders();
    }
    const enabled = () => studio.hasAttribute("data-imw-video");
    const engine2 = () => globalThis.OAIMWVideo;
    const selection2 = () => studio.project && {
      project: studio.project.id,
      song: studio.song?.id,
      version: studio.version?.id
    };
    function trackSelection() {
      const current = selection2();
      return enabled() && videoSong && current?.project === videoProject && videoSong.project === current.project && videoSong.song === current.song && videoSong.version === current.version ? current : null;
    }
    function scoreWindow(clock) {
      const music = clock?.music;
      const source = engine2()?.audioBinding?.();
      const take = trackSelection();
      return music && document.body.dataset.imwMusicSha === music.sha256 && source && take && source.project === take.project && source.song === take.song && source.version === take.version ? music : null;
    }
    const offset = (clock) => {
      const window2 = scoreWindow(clock);
      return window2 ? (window2.start_ms - window2.in_ms) / 1e3 : 0;
    };
    function measures() {
      if (!enabled()) return;
      const cut = document.getElementById("dmCut");
      const monitorHeight = $("imw-screen").clientHeight;
      const extraHeight = $("imw-original-track").getBoundingClientRect().height;
      if (monitorHeight > 0) studio.style.setProperty(
        "--imw-frame-fit",
        (100 * monitorHeight / (monitorHeight + extraHeight)).toFixed(3) + "cqw"
      );
      studio.toggleAttribute("data-imw-empty-video", cut.hidden || document.getElementById("dmCutTracks").hidden);
    }
    function selectStem(track) {
      if (!track) return;
      activeTrack = track.id;
      selectLane("");
      for (const [id, label] of studio.trackHeads || [])
        label.parentElement.toggleAttribute("data-imw-current", id === activeTrack);
    }
    function currentKey() {
      return JSON.stringify([document.body.dataset.imwWork, trackSelection()]);
    }
    function updateRows() {
      if (!enabled()) return;
      const key = currentKey(), changed = boundKey !== key;
      if (changed) {
        showOriginal = false;
        boundKey = key;
        selectedLane = "";
        activeTrack = "";
      }
      const tracks = trackSelection() ? studio.version?.tracks || [] : [];
      const ids = new Set(tracks.map((track) => track.id));
      if (!ids.has(activeTrack)) activeTrack = tracks[0]?.id || "";
      for (const el of studio.shadowRoot.querySelectorAll("[data-track-row]")) {
        const id = el.dataset.trackRow;
        el.toggleAttribute("data-imw-track", ids.has(id));
        if (el.classList.contains("track-head")) el.toggleAttribute("data-imw-current", id === activeTrack);
      }
      studio.toggleAttribute("data-imw-stems", !!tracks.length);
      studio.toggleAttribute("data-imw-compact", tracks.length > 1);
      studio.toggleAttribute("data-imw-dense", tracks.length >= 12);
      $("regions").style.setProperty("--imw-parts", String(tracks.length || 1));
      $("imw-empty-tracks").hidden = !!tracks.length;
      if (tracks.length && (!studio.selected || studio.selected.id !== activeTrack)) {
        studio.selected = tracks.find((track) => track.id === activeTrack);
        studio.selectedPart = 0;
        studio.updateSelection();
      }
      sourceRow();
      paintSelection();
      syncClock(engine2()?.state?.());
      scheduleMeasure();
    }
    function scheduleMeasure() {
      if (!frame) frame = requestAnimationFrame(() => {
        frame = 0;
        measureAxis();
        syncClock(engine2()?.state?.());
        measures();
        if (enabled()) studio.paint();
      });
    }
    function measureAxis() {
      if (!enabled()) return;
      const reference = $("imw-audio-fit");
      const nativeWidth = reference.lastElementChild.getBoundingClientRect().width;
      const labelWidth = reference.firstElementChild.getBoundingClientRect().width;
      if (!(nativeWidth > 0 && labelWidth > 0)) return;
      const value = labelWidth + "px";
      if (studio.style.getPropertyValue("--imw-label-width") !== value)
        studio.style.setProperty("--imw-label-width", value);
      audioViewport = nativeWidth;
      viewportGain = Math.max(0, $("scroll").getBoundingClientRect().width - nativeWidth);
    }
    function extendDisplayLength(base) {
      return audioViewport > 0 && trackSelection() ? base + viewportGain / audioScale() : base;
    }
    function displayLength(clock = engine2()?.state?.()) {
      const film = Number(clock?.displayLength || clock?.length) || 0;
      const source = studio.rulerLength + Math.max(0, offset(clock));
      return trackSelection() ? Math.max(film, extendDisplayLength(Math.max(source, Number(clock?.length) || 0))) : film;
    }
    function syncClock(clock) {
      if (!enabled() || !clock) return;
      if (boundKey !== currentKey()) return updateRows();
      const length = displayLength(clock);
      const start = offset(clock);
      const scale = [length, start, studio.rulerLength, audioScale()].join(":");
      if (lastScale !== scale) {
        lastScale = scale;
        if (trackSelection() && audioViewport > 0) $("lane").style.width = length * audioScale() + "px";
        else $("lane").style.width = "100%";
        studio.drawRuler();
        if (length > 0) {
          $("regions").style.width = 100 * studio.rulerLength / length + "%";
          $("regions").style.left = 100 * start / length + "%";
        }
        engine2()?.syncGeometry?.();
        studio.detachedTracks?.layout();
      }
      if (length > 0) {
        $("playhead").style.left = 100 * clock.seconds / length + "%";
        $("seek").max = clock.length;
        $("seek").value = clock.seconds;
        $("seek").setAttribute("aria-valuetext", clock.seconds.toFixed(2) + " \u79D2");
      }
      studio.frameRuler?.sync(clock);
    }
    function togglePanel(tab) {
      const node2 = document.querySelector('[data-dt-tab="' + tab + '"]');
      if (!node2) return;
      if (node2.getAttribute("aria-pressed") !== "true") node2.click();
      studio.setAttribute("data-imw-inspector", "");
      $("imw-inspect").setAttribute("aria-expanded", "true");
    }
    $("imw-project").onclick = () => {
      const work = document.getElementById("daWork"), select = document.getElementById("directorProject");
      if (!work || !select) return;
      studio.setAttribute("data-imw-inspector", "");
      $("imw-inspect").setAttribute("aria-expanded", "true");
      work.open = true;
      select.focus();
    };
    const videoToggle = document.getElementById("imw-video-toggle");
    if (videoToggle) videoToggle.onclick = () => document.dispatchEvent(new CustomEvent("jiusera:imw-video-toggle", {
      detail: { enabled: studio.disclosure.reversing() || !enabled() && !studio.hasAttribute("data-imw-opening"), selection: selection2() }
    }));
    $("imw-folded-video").onclick = () => {
      if (enabled()) togglePanel("media");
      else videoToggle?.click();
    };
    createLaneHeaders();
    const audioTab = document.querySelector('#directorMonitor [data-dt-tab="audio"]');
    function openTrackSettings(event) {
      if (!enabled()) return;
      event?.preventDefault();
      event?.stopImmediatePropagation();
      const label = trackSelection() && studio.trackHeads?.get(activeTrack);
      if (!label) {
        $("imw-empty-tracks").focus({ preventScroll: true });
        return;
      }
      if (label.getAttribute("aria-expanded") !== "true") label.click();
      label.focus({ preventScroll: true });
    }
    $("imw-score-settings").onclick = openTrackSettings;
    $("imw-captions").onclick = () => {
      studio.drawer(false);
      togglePanel("captions");
    };
    $("imw-inspect").onclick = () => $("imw-inspect").setAttribute(
      "aria-expanded",
      String(studio.toggleAttribute("data-imw-inspector"))
    );
    document.addEventListener("jiusera:imw-monitor", monitorHeaders);
    studio.addEventListener("click", (e) => {
      if (!enabled()) return;
      const el = e.composedPath()[0];
      if (el.closest?.("#dmCutStrip")) selectLane("video");
      if (el.matches?.(".track-row[data-imw-track]")) {
        const track = studio.version.tracks.find((t) => t.id === el.dataset.trackRow);
        if (track) studio.selectClip(track);
      }
    });
    studio.shadowRoot.addEventListener("focusin", (event) => {
      if (!enabled()) return;
      const group = event.target.closest?.("#regions .clip-group");
      const track = group && studio.version?.tracks.find((t) => t.id === group.dataset.track);
      if (track && (studio.selected !== track || studio.selectedPart !== Number(group.dataset.part))) {
        studio.selectClip(track, Number(group.dataset.part));
      }
    });
    $("imw-add-track").onchange = (e) => {
      if (e.target.value === originalTrack) showOriginal = true;
      updateRows();
    };
    document.addEventListener("jiusera:imw-clock", (e) => syncClock(e.detail));
    document.addEventListener("jiusera:imw-binding", () => {
      if (enabled()) {
        syncProject();
        updateRows();
        engine2()?.refreshMix?.();
      }
    });
    studio.shadowRoot.addEventListener("keydown", (event) => {
      if (!enabled() || event.defaultPrevented || event.isComposing || event.key !== " " || event.altKey || event.ctrlKey || event.metaKey || event.shiftKey) return;
      const target = event.composedPath()[0];
      if (target?.isContentEditable || target?.closest?.("textarea,[role=textbox],dialog[open],input:not([type=range]):not([type=button])")) return;
      event.preventDefault();
      if (!event.repeat && engine2()?.state?.()?.ready) engine2().toggle(event);
    });
    function move(id, name) {
      const el = typeof id === "string" ? document.getElementById(id) : id, mark = document.createComment(name);
      el.before(mark);
      original.set(el, mark);
      el.slot = name;
      studio.append(el);
    }
    function setMode(on) {
      if (on === enabled()) return;
      if (on && (!document.getElementById("directorMonitor") || !document.getElementById("dmCut"))) return;
      const clock = engine2()?.state?.();
      const previousHeight = studio.disclosure.takeHeight();
      const scrollLeft = studio.frameRuler.audioScroll();
      if (on) {
        studio.stopAndRemember();
        studio.$("master-aac-player").pause();
        studio.trackEditor.closeMenu();
        studio.trackEditor.foldForVideo(true);
        move("directorMonitor", "imw-video");
        move("dmCut", "imw-timeline");
        move("dmCutMusicLane", "imw-archived-score");
        const fields = document.querySelector("#dmCutSettings > .dc-music");
        if (fields) move(fields, "imw-archived-score-settings");
        if (audioTab?.getAttribute("aria-pressed") === "true") audioTab.click();
        audioTab?.addEventListener("click", openTrackSettings, true);
        const archived = document.getElementById("dmCutMusicLane");
        archivedInert = archived.inert;
        archived.inert = true;
        studio.setAttribute("data-imw-video", "");
        measureAxis();
        laneHeaders.get("video").label.setAttribute("aria-expanded", "true");
        $("imw-folded-video").setAttribute("aria-expanded", "true");
        $("imw-folded-video").setAttribute("aria-label", "\u6DFB\u52A0\u89C6\u9891\u7D20\u6750");
        $("imw-folded-video").firstElementChild.textContent = "\u6DFB\u52A0\u89C6\u9891\u7D20\u6750";
        studio.transport.activateVideo();
        syncProject();
        const projects = document.getElementById("directorProject");
        if (projects) {
          projectObserver = new MutationObserver(syncProject);
          projectObserver.observe(projects, { childList: true, subtree: true, attributes: true, attributeFilter: ["title"] });
        }
        observer = new MutationObserver(updateRows);
        observer.observe($("regions"), { childList: true });
        resize = new ResizeObserver(scheduleMeasure);
        resize.observe($("imw-audio-fit"));
        resize.observe($("scroll"));
        resize.observe($("regions"));
        resize.observe($("imw-screen"));
        for (const id of ["dmCut", "dmCutStrip"])
          resize.observe(document.getElementById(id));
        sourceObserver = new MutationObserver(() => {
          if (!sourceFrame) sourceFrame = requestAnimationFrame(sourceRow);
        });
        sourceObserver.observe(document.getElementById("dmCutStrip"), { childList: true, subtree: true });
        updateRows();
      } else {
        studio.detachedTracks.remember();
        engine2()?.pause?.();
        const musicBound = !!trackSelection();
        observer?.disconnect();
        resize?.disconnect();
        sourceObserver?.disconnect();
        projectObserver?.disconnect();
        videoProject = "";
        videoSong = null;
        studio.removeAttribute("data-imw-song");
        cancelAnimationFrame(sourceFrame);
        sourceFrame = 0;
        cancelAnimationFrame(frame);
        frame = 0;
        studio.removeAttribute("data-imw-video");
        studio.removeAttribute("data-imw-inspector");
        $("imw-inspect").setAttribute("aria-expanded", "false");
        audioTab?.removeEventListener("click", openTrackSettings, true);
        document.getElementById("dmCutMusicLane").inert = archivedInert;
        for (const [el, mark] of original) {
          el.removeAttribute("slot");
          mark.replaceWith(el);
        }
        audioViewport = 0;
        viewportGain = 0;
        studio.style.removeProperty("--imw-label-width");
        original.clear();
        showOriginal = false;
        activeTrack = "";
        boundKey = "";
        lastScale = "";
        selectedLane = "";
        paintSelection();
        studio.removeAttribute("data-imw-dense");
        studio.removeAttribute("data-imw-compact");
        $("regions").style.removeProperty("--imw-parts");
        $("imw-empty-tracks").hidden = true;
        studio.removeAttribute("data-imw-stems");
        studio.removeAttribute("data-imw-empty-video");
        laneHeaders.get("video").label.setAttribute("aria-expanded", "false");
        $("imw-folded-video").setAttribute("aria-expanded", "false");
        $("imw-folded-video").setAttribute("aria-label", "\u5C55\u5F00\u89C6\u9891");
        $("imw-folded-video").firstElementChild.textContent = "\u5C55\u5F00\u89C6\u9891";
        studio.frameRuler?.reset();
        studio.setLaneExtent(studio.rulerLength);
        studio.drawRuler();
        $("seek").max = studio.length;
        $("regions").style.removeProperty("width");
        $("regions").style.removeProperty("left");
        $("regions").style.removeProperty("clip-path");
        studio.trackEditor.foldForVideo(false);
        studio.transport.activate();
        if (musicBound && Number.isFinite(clock?.seconds)) studio.seek(clock.seconds - offset(clock));
        studio.position();
        studio.transport.sync();
        studio.paint();
      }
      studio.detachedTracks.refresh();
      if (!on && studio.detachedTracks.extent() > studio.length) studio.grid();
      $("scroll").scrollLeft = scrollLeft;
      if (on) document.body.dataset.imwAspect = studio.dataset.imwAspect || "landscape";
      else delete document.body.dataset.imwAspect;
      if (videoToggle) {
        videoToggle.setAttribute("aria-expanded", String(on));
        videoToggle.setAttribute("aria-label", on ? "\u6536\u8D77\u89C6\u9891" : "\u5C55\u5F00\u89C6\u9891");
        videoToggle.title = on ? "\u6536\u8D77\u89C6\u9891" : "\u5C55\u5F00\u89C6\u9891";
      }
      studio.$("imw-settings")?.hidePopover();
      if (on) void studio.disclosure.reveal(previousHeight);
    }
    function selectionChanged() {
      if (enabled()) {
        updateRows();
        document.dispatchEvent(new CustomEvent("jiusera:imw-selection-changed", { detail: selection2() }));
      }
    }
    return {
      setMode,
      setProject,
      syncProject,
      enabled,
      displayLength,
      extendDisplayLength,
      selectionChanged,
      updateRows,
      paintSelection,
      trackSelection,
      selectStem,
      loopStem(start, end) {
        const clock = engine2()?.state?.();
        if (!clock?.length || !trackSelection()) return;
        const window2 = scoreWindow(clock), shift = offset(clock);
        const inMs = Math.max(0, Math.round(1e3 * (Math.max(start, (window2?.in_ms || 0) / 1e3) + shift)));
        const outMs = Math.min(Math.round(clock.length * 1e3), Math.round(1e3 * (Math.min(end, (window2?.out_ms ?? Infinity) / 1e3) + shift)));
        if (outMs - inMs < 250) return studio.status("\u53EF\u5FAA\u73AF\u7684\u7247\u6BB5\u81F3\u5C11\u9700\u8981 0.25 \u79D2\u3002");
        const send = (detail) => document.dispatchEvent(new CustomEvent("jiusera:imw-transport-command", { detail }));
        let state;
        const receive = (event) => {
          state = event.detail;
        };
        document.addEventListener("jiusera:imw-transport-state", receive, { once: true });
        send({ action: "loop-range", inMs, outMs });
        document.removeEventListener("jiusera:imw-transport-state", receive);
        if (state?.ready && !state.loop) send({ action: "loop" });
      },
      seek(sourceTime) {
        engine2()?.seek?.(sourceTime + offset(engine2()?.state?.()));
      },
      dragWidth() {
        return $("regions").getBoundingClientRect().width;
      },
      fit() {
        lastScale = "";
        syncClock(engine2()?.state?.());
      }
    };
  }

  // assets/studio/track-monitor.mjs
  var TrackMonitor = class {
    constructor() {
      this.sessions = /* @__PURE__ */ new Map();
      this.select(null, null, null);
    }
    select(project, song, version) {
      const key = JSON.stringify([project?.id, song?.id, version?.id]);
      this.ids = new Set((version?.mastered ? [] : version?.tracks ?? []).map((track) => track.id));
      this.selection = this.sessions.get(key) ?? { solo: /* @__PURE__ */ new Set(), mute: /* @__PURE__ */ new Set() };
      this.key = key;
      for (const group of [this.selection.solo, this.selection.mute]) {
        for (const id of group) if (!this.ids.has(id)) group.delete(id);
      }
    }
    toggle(name, id) {
      if (!this.ids.has(id)) return false;
      const group = this.selection[name];
      if (!group.delete(id)) group.add(id);
      if (this.filtered()) this.sessions.set(this.key, this.selection);
      else this.sessions.delete(this.key);
      return true;
    }
    filtered(editorId) {
      return !!editorId || this.selection.solo.size > 0 || this.selection.mute.size > 0;
    }
    state(id, editorId) {
      const solo = this.selection.solo.has(id), mute = this.selection.mute.has(id);
      const editorSolo = id === editorId;
      const selected = editorId ? editorSolo : !this.selection.solo.size || solo;
      return { solo, mute, editorSolo, audible: !mute && selected };
    }
  };
  var MonitorGains = class {
    constructor(context, master) {
      this.context = context;
      this.lanes = /* @__PURE__ */ new Map();
      this.stems = context.createGain();
      this.native = context.createGain();
      this.stems.connect(master);
      this.native.connect(master);
      this.native.gain.value = 0;
      this.useNative = false;
    }
    lane(id, audible) {
      if (!this.lanes.has(id)) {
        const node2 = this.context.createGain();
        node2.gain.value = Number(audible);
        node2.connect(this.stems);
        this.lanes.set(id, { node: node2, audible });
      }
      return this.lanes.get(id).node;
    }
    update(useNative, audible, immediate = false) {
      const now = this.context.currentTime, edge = now + 3e-3;
      for (const [id, lane] of this.lanes) {
        const value = audible(id);
        if (!immediate && lane.audible === value) continue;
        lane.audible = value;
        const gain = lane.node.gain;
        if (immediate) {
          gain.cancelScheduledValues(now);
          gain.setValueAtTime(Number(value), now);
        } else {
          gain.cancelAndHoldAtTime(now);
          gain.linearRampToValueAtTime(Number(value), edge);
        }
      }
      if (!immediate && this.useNative === useNative) return;
      this.useNative = useNative;
      const off = (useNative ? this.stems : this.native).gain;
      const on = (useNative ? this.native : this.stems).gain;
      if (immediate) {
        for (const param of [off, on]) param.cancelScheduledValues(now);
        off.setValueAtTime(0, now);
        on.setValueAtTime(1, now);
      } else {
        off.cancelAndHoldAtTime(now);
        on.cancelAndHoldAtTime(now);
        off.linearRampToValueAtTime(0, edge);
        on.setValueAtTime(on.value, edge);
        on.linearRampToValueAtTime(1, edge + 3e-3);
      }
    }
    clearLanes() {
      for (const { node: node2 } of this.lanes.values()) node2.disconnect();
      this.lanes.clear();
    }
    close() {
      this.clearLanes();
      this.native.disconnect();
      this.stems.disconnect();
    }
  };

  // assets/studio/live-monitor.mjs
  var MAX_CHUNK = 32768;
  var READ_AHEAD = 0.72;
  function decode(context, packet, expected, frames, rate) {
    if (packet.encoding !== "f32le" || packet.channels !== 2 || packet.sampleRate !== rate || packet.start !== expected || packet.frames !== frames || typeof packet.bytes !== "string" || packet.bytes.length !== 4 * Math.ceil(frames * 8 / 3)) throw Error("studio_monitor_invalid");
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
  var BusMonitor = class {
    constructor(call2) {
      this.call = call2;
    }
    stop() {
      const run = this.run;
      if (!run) return;
      this.run = null;
      clearTimeout(run.timer);
      for (const node2 of run.nodes) {
        node2.onended = null;
        node2.stop();
        node2.disconnect();
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
      void this.call({ action: "monitor_close", ...scope, stream }).catch(() => {
      });
    }
    async start({
      context,
      destination,
      scope,
      profile,
      bypass,
      from,
      end = profile.frames,
      loop = null,
      onStart,
      onBlock,
      onEnd,
      onError
    }) {
      this.stop();
      const rate = profile.sampleRate, analysis = profile.analysis;
      const chunkSize = Math.min(MAX_CHUNK, Math.round(rate / 3));
      if (!Number.isSafeInteger(from) || !Number.isSafeInteger(end) || from < 0 || from >= end || end > profile.frames || loop !== null && (!Number.isSafeInteger(loop) || loop < 0 || loop > from || end - loop < rate / 4)) {
        throw Error("studio_monitor_range");
      }
      const run = { scope: { ...scope }, nodes: /* @__PURE__ */ new Set(), cursor: from, firstTime: null, emitted: 0, bypass };
      if (loop !== null && end - loop <= 1024 * 1024) run.loopBlocks = /* @__PURE__ */ new Map();
      this.run = run;
      const active = () => this.run === run;
      const clock = () => run.firstTime + run.emitted / rate;
      const finish = (error) => {
        if (!active()) return;
        this.stop();
        if (error) onError?.(error);
        else onEnd?.();
      };
      const open = async () => {
        const desired = run.bypass;
        const reply = await this.call({ action: "monitor_open", ...scope, analysis, frame: run.cursor, bypass: desired });
        if (!active()) {
          this.release(scope, reply.stream);
          return false;
        }
        run.token = reply.stream;
        if (reply.start !== run.cursor || reply.sampleRate !== rate || reply.frames !== profile.frames || reply.bypass !== desired) throw Error("studio_monitor_invalid");
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
          const packet = await this.call({
            action: "monitor_read",
            ...scope,
            analysis,
            stream: run.token,
            frame: start,
            frames: n,
            bypass: desired
          });
          if (!active()) return;
          if (packet.bypass !== desired || packet.eof !== (start + n === profile.frames)) throw Error("studio_monitor_invalid");
          buffer = decode(context, packet, start, n, rate);
          if (run.loopBlocks && desired === run.bypass && start >= loop && (start - loop) % chunkSize === 0)
            run.loopBlocks.set(start, buffer);
        }
        if (run.firstTime === null) run.firstTime = context.currentTime + 0.06;
        const at = clock();
        if (at < context.currentTime) throw Error("studio_monitor_underrun");
        const node2 = context.createBufferSource();
        node2.buffer = buffer;
        node2.connect(destination);
        run.nodes.add(node2);
        node2.onended = () => {
          node2.disconnect();
          run.nodes.delete(node2);
        };
        node2.start(at);
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
            const ended = node2.onended;
            node2.onended = () => {
              ended();
              finish();
            };
            return;
          }
          run.cursor = loop;
        }
        const ahead = clock() - context.currentTime;
        const pump = () => {
          if (!active()) return;
          const wait = clock() - context.currentTime - READ_AHEAD;
          if (wait > 0.02) run.timer = setTimeout(pump, Math.min(wait, 0.4) * 1e3);
          else void next().catch(finish);
        };
        if (ahead < READ_AHEAD) void next().catch(finish);
        else run.timer = setTimeout(pump, 20);
      };
      try {
        await next();
      } catch (error) {
        finish(error);
      }
    }
  };

  // assets/studio/studio-live-transport.mjs
  function audibleState(studio) {
    const d = studio.draft;
    return JSON.stringify([d.offsets, d.trims, d.padding, d.splits, d.trackMix, d.masterGain]);
  }
  function playStudioBus(studio) {
    const profile = studio.masterAnalysis;
    if (!profile) return false;
    const rate = profile.sampleRate;
    let from = Math.round(studio.seconds * rate);
    const end = studio.loopEnabled ? Math.min(profile.frames, Math.round(studio.loop.end * rate)) : profile.frames;
    const loop = studio.loopEnabled ? Math.round(studio.loop.start * rate) : null;
    if (loop !== null && (end - loop < rate / 4 || from < loop)) {
      studio.status("\u5FAA\u73AF\u533A\u95F4\u8D85\u51FA\u5DF2\u5206\u6790\u7684\u8282\u76EE\u8303\u56F4\u3002");
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
    void monitor.start({
      context: studio.context,
      destination: studio.monitorGains.native,
      scope: profile.scope,
      profile,
      from,
      end,
      loop,
      bypass: !!studio.busBypass,
      onStart({ at, from: from2 }) {
        studio.busPending = false;
        studio.clock = at - from2;
        const tick = () => {
          if (!studio.playing || !monitor.run) return;
          studio.seconds = studio.context.currentTime < at ? from2 : studio.clockPosition();
          studio.sampleOutput(studio.context.currentTime);
          studio.position();
          studio.animation = requestAnimationFrame(tick);
        };
        tick();
      },
      onBlock(window2) {
        studio.monitorBlock(window2);
      },
      onEnd() {
        studio.stop();
        studio.seconds = end / rate;
        studio.position();
        studio.changed();
      },
      onError(error) {
        studio.stopAndRemember();
        studio.status(error.message === "analysis_changed" ? "\u5206\u8F68\u5DF2\u53D8\u5316\uFF0C\u8BF7\u91CD\u65B0\u5206\u6790\u3002" : "\u603B\u7EBF\u76D1\u542C\u4E2D\u65AD\uFF0C\u8BF7\u4ECE\u5F53\u524D\u4F4D\u7F6E\u91CD\u8BD5\u3002");
      }
    }).catch(() => {
      studio.stop();
      studio.status("\u65E0\u6CD5\u542F\u52A8 Stereo Out \u76D1\u542C\u3002");
    });
    return true;
  }

  // assets/studio/studio.css
  var studio_default = '/* Neutral workbench surfaces frame the track colors and playhead. */\n:host {\n  --canvas: var(--wb-surface);\n  --panel: var(--surface);\n  --layer: var(--soft);\n  --raised: var(--oa-fill);\n  --grid-major: color-mix(in srgb,var(--ink) 16%,transparent);\n  --grid-beat: color-mix(in srgb,var(--ink) 8%,transparent);\n  --grid-detail: color-mix(in srgb,var(--ink) 4%,transparent);\n  --accent: var(--oa-selected-ink);\n  --selected: var(--oa-selection);\n  --head: var(--oa-focus);\n  --loop: color-mix(in srgb,var(--selected) 68%,transparent);\n  --focus: var(--oa-focus);\n  --clip-ink: var(--wb-ink);\n  --head-surface: var(--canvas);\n  --relief-light: var(--lus-highlight);\n  --relief-shadow: var(--lus-shade);\n  --soft-raise: var(--lus-raised);\n  --soft-inset: var(--lus-inset);\n  --depth: var(--lus-floating);\n  --wave-peak-alpha: var(--lus-wave-peak-alpha,.78);\n  --wave-rms-alpha: var(--lus-wave-rms-alpha,.96);\n  --track-height: 108px;\n  --imw-video-row-height:100px;\n  --track-action-height: 39px;\n  --ruler-height: 34px;\n  font: 12px/1.45 system-ui, sans-serif;\n  color: var(--ink);\n}\n*, *::before, *::after { box-sizing: border-box; }\n[hidden], .mobile { display: none !important; }\n.studio { height: 100%; min-height: 0; display: flex; flex-direction: column; background: var(--canvas); }\n.toolbar, .toolbar-end, .current-take, .songs-heading, .editor-footer { display:flex; align-items:center; min-width:0; }\n.toolbar { min-height: 46px; gap: 12px; padding: 5px 12px; background: var(--panel); box-shadow:var(--soft-raise); z-index:6; }\n.toolbar-end { margin-left:auto; gap:9px; flex:none; }\n.field { display:flex; align-items:center; gap:5px; color:var(--muted); white-space:nowrap; min-width:0; }\n.current-take { gap:7px; padding-inline-start:12px; border-inline-start:1px solid var(--line); }\n#song-title { overflow:hidden; white-space:nowrap; text-overflow:ellipsis; font-weight:680; }\n#version { min-width:0; max-width:min(25vw,164px); }\n#project { max-width:min(28vw,184px); }\n#tempo { color:var(--muted); font:11px ui-monospace,monospace; white-space:nowrap; }\nbutton,select {\n  color:var(--ink); font:inherit; background:var(--raised); border:1px solid transparent;\n  border-radius:7px; min-height:28px; padding:3px 8px;\n  box-shadow:var(--soft-raise);\n}\nselect { max-width:100%; min-width:0; box-shadow:var(--soft-inset); }\nbutton { cursor:pointer; }\n#cut-quiet,#undo-cut { white-space:nowrap; }\nbutton:where(:hover:not(:disabled)):not(:where(.clip,.track-name,.song,.song-cover,.trim-handle)),\nselect:where(:hover:not(:disabled)) { color:var(--accent); background:var(--oa-hover); }\nbutton:where(:active:not(:disabled)):not(:where(.clip,.track-name,.song,.song-cover,.trim-handle)) {\n  color:var(--accent); background:var(--selected); box-shadow:var(--soft-inset);\n}\nbutton:disabled { opacity:.6; cursor:default; }\nbutton:focus-visible,select:focus-visible,.ruler:not([data-pointer-seek]):has(input:focus-visible) {\n  outline:2px solid var(--focus); outline-offset:-2px;\n}\n.body { display:grid; grid-template-columns:minmax(0,1fr) clamp(230px,23%,288px); flex:1; min-height:0; position:relative; }\n.editor { position:relative; display:flex; min-width:0; min-height:0; flex-direction:column; }\n.arrangement {\n  display:grid; grid-template-columns:clamp(112px,16%,159px) minmax(0,1fr);\n  position:relative; isolation:isolate; flex:1; min-height:0; overflow:auto; scrollbar-width:thin;\n}\n.track-head,.track-row {\n  --action-space:0px;\n  height:calc(var(--track-height) + var(--action-space));\n}\n:is(.track-head,.track-row)[data-expanded] { --action-space:var(--track-action-height); }\n.track-head {\n  --head-ink:var(--ink);\n  --key-light:color-mix(in srgb,var(--canvas) 93%,white);\n  --key-shade:color-mix(in srgb,var(--canvas) 73%,black);\n  --key-up:-1px -1px 3px var(--key-light),2px 2px 4px var(--key-shade);\n  --key-down:inset 1px 1px 3px var(--key-shade),inset -1px -1px 2px var(--key-light);\n  position:relative; color:var(--head-ink);\n  display:grid; grid-template-columns:minmax(0,1fr) auto;\n  grid-template-rows:var(--track-height) auto; align-items:center;\n  padding-inline:5px; column-gap:6px;\n}\n.track-list { position:relative; z-index:2; background:var(--canvas); }\n.track-heading,.track-name { display:flex; align-items:center; width:100%; text-align:start; }\n.track-heading {\n  justify-content:space-between; height:var(--ruler-height); padding-inline:10px;\n  color:var(--muted); font-size:10px; background:var(--canvas);\n}\n.track-name {\n  grid-column:1; min-width:0; height:calc(var(--track-height) - 16px); min-height:0; gap:4px; padding-inline:7px;\n  border:0; border-radius:7px; background:var(--canvas); color:inherit;\n  box-shadow:var(--key-up); outline-offset:-2px;\n}\n.track-name[data-selected] {box-shadow:var(--key-down);color:var(--accent)}\n.track-name[data-selected] .track-label {font-weight:750}\n.track-head:not(:has(.track-monitor-controls)) .track-name {grid-column:1/-1}\n.track-monitor-controls {\n  grid-column:2; display:flex; flex-direction:column; position:relative; align-items:center; gap:5px;\n}\n.track-monitor-controls button {\n  width:27px; height:26px; min-height:24px; padding:0; border-radius:6px;\n  border:0; color:var(--ink); font:650 11px/1 system-ui,sans-serif;\n  background:var(--canvas); box-shadow:var(--key-up);\n}\n.track-monitor-controls button:is(:active,[aria-pressed="true"]) {\n  color:var(--accent); background:var(--canvas); box-shadow:var(--key-down); font-weight:800;\n}\n.track-monitor-controls button:focus-visible {outline:2px solid var(--focus);outline-offset:1px}\n.track-head[data-monitor-inherited] [data-track-monitor="mute"] {border:1px dashed currentColor}\n.track-monitor-status {position:absolute;inset:100% 0 auto auto;white-space:nowrap;color:var(--ink);font-size:9px}\n.track-row[data-monitor-muted] .clip canvas { opacity:.45; }\n#monitor-route {\n  flex:none; padding:3px 10px; background:var(--layer); color:var(--ink);\n  border-bottom:1px solid var(--line); font-size:11px;\n}\n.track-name:focus-visible { outline-color:var(--focus); }\n.track-name:hover .track-chevron,.track-name[aria-expanded=true] .track-chevron { opacity:1; }\n.track-label { min-width:0; font-size:12px; font-weight:650; white-space:nowrap; overflow:hidden; text-overflow:ellipsis; }\n.track-offline { font-size:9px; color:var(--muted); white-space:nowrap; order:1; }\n.track-chevron {\n  width:6px; height:6px; flex:none; margin-inline-start:auto; margin-inline-end:2px; order:2;\n  border:solid currentColor; border-width:0 1.5px 1.5px 0;\n  transform:rotate(45deg) translateY(-2px); opacity:.63;\n}\n.track-name[aria-expanded=true] .track-chevron { transform:rotate(225deg) translateY(-1px); }\n.timeline { position:relative; z-index:1; min-width:0; margin-inline:4px; overflow:auto hidden; scrollbar-width:thin; }\n.lane {\n  --beat-ink:transparent; --detail-ink:transparent;\n  position:relative; min-height:100%; isolation:isolate;\n  background-image:\n    linear-gradient(to right,var(--grid-major) 1px,transparent 1px),\n    linear-gradient(to right,var(--beat-ink) 1px,transparent 1px),\n    linear-gradient(to right,var(--detail-ink) 1px,transparent 1px);\n  background-size:var(--major-step,20%) 100%,var(--beat-step,100%) 100%,var(--detail-step,100%) 100%;\n}\n.lane[data-beat] { --beat-ink:var(--grid-beat); }\n.lane[data-detail] { --detail-ink:var(--grid-detail); }\n.ruler {\n  height:var(--ruler-height); position:relative; cursor:crosshair; color:var(--ink);\n  font:600 11px ui-monospace,monospace; border-bottom:1px solid var(--line);\n  background:var(--layer);\n}\n.ruler span { position:absolute; top:7px; padding-inline-start:5px; pointer-events:none; }\n.ruler input { position:absolute; width:1px; height:1px; padding:0; opacity:0; inset:0; pointer-events:none; }\n.track-row { position:relative; }\n.track-actions {\n  grid-column:1/-1; align-self:start; display:flex; flex-wrap:wrap; align-items:flex-start; gap:4px; padding-inline:12px;\n}\n.track-actions button {\n  min-height:25px; padding-inline:5px; border:0; font-size:10px;\n  color:var(--head-ink);\n}\n.track-actions button:focus-visible { outline-color:var(--focus); }\n#loop-band { position:absolute; z-index:0; inset-block:0; pointer-events:none; background:var(--loop); border-inline:1px solid color-mix(in srgb,var(--head) 55%,transparent); }\n#loop-band::before { content:""; display:block; height:2px; background:var(--head); }\n.playhead { pointer-events:none; position:absolute; z-index:4; inset-block:0; width:1px; background:var(--head); }\n.playhead::before {\n  content:""; width:9px; height:8px; position:absolute; top:0; left:-4px;\n  background:var(--head); clip-path:polygon(0 0,100% 0,50% 100%);\n}\n.editor-footer {\n  position:absolute; inset:auto 0 var(--wb-dock,70px); z-index:3;\n  min-height:0; gap:7px; padding:0 9px; color:var(--muted); font-size:10px;\n  pointer-events:none;\n}\n.editor-footer slot { display:block; margin-inline-start:auto; flex:none; pointer-events:auto; }\n.editor-footer button { min-height:24px; padding-inline:5px; font-size:10px; pointer-events:auto; }\n#status { min-width:0; }\n#status:not(:empty) { background:var(--panel); padding:3px 6px; border-radius:5px; }\n#empty {\n  position:absolute; inset:0; padding:var(--ruler-height) 12px 0 100px; z-index:3; display:grid;\n  place-content:center; justify-items:center; pointer-events:none; color:var(--muted);\n}\n#empty button { pointer-events:auto; }\naside {\n  min-height:0; overflow:auto; background:var(--layer); border-inline-start:1px solid var(--line);\n  scrollbar-width:thin; padding-bottom:var(--wb-dock,70px);\n}\n.songs-heading {\n  min-height:42px; gap:7px; padding:5px 12px; position:sticky; top:0; z-index:1; background:var(--layer);\n}\n.songs-heading h2 { font-size:12px; margin:0; font-weight:720; }\n.songs-heading span { font-size:10px; color:var(--muted); }\n#songs-refresh { margin-inline-start:auto; min-width:28px; padding-inline:0; font-size:16px; line-height:1; }\n#playlist-status { margin:0 12px 8px; color:var(--muted); }\n#song-list { padding:5px 11px 12px; display:grid; gap:10px; }\n.song-card {\n  display:grid; grid-template-columns:50px minmax(0,1fr); align-items:center; gap:6px 10px;\n  padding:8px; border-radius:11px; background:var(--panel); box-shadow:var(--soft-raise);\n}\n.song-card[data-current] { background:var(--selected); box-shadow:var(--soft-inset); }\n.song { display:grid; gap:2px; text-align:start; min-width:0; padding:0; border:0; background:none; box-shadow:none; }\n.song:not([aria-pressed="true"]):hover .song-name { color:var(--accent); }\n.song-card .song:active { box-shadow:none; }\n.song[aria-pressed="true"] .song-name { color:var(--accent); }\n.song-name { overflow:hidden; text-overflow:ellipsis; white-space:nowrap; font-size:12px; }\n.song-source,.song-version { display:block; color:var(--muted); font-size:10px; line-height:1.3; }\n.song-cover {\n  display:grid; place-items:center; position:relative; border:0; width:50px; height:50px;\n  border-radius:8px; padding:0; overflow:hidden;\n}\n.song-cover img { position:absolute; inset:0; width:100%; height:100%; object-fit:cover; }\n.song-icon {\n  position:relative; display:grid; place-items:center; width:25px; height:25px; font-size:10px;\n  border-radius:50%; color:var(--ink); background:var(--raised); box-shadow:var(--soft-inset);\n}\n.song-cover:has(img) .song-icon {\n  color:var(--oa-action-ink); background:color-mix(in srgb,var(--oa-action) 92%,transparent); box-shadow:none;\n}\n.song-cover[aria-pressed="true"] .song-icon { background:var(--selected); color:var(--accent); }\n.song-cover:focus-visible { outline-offset:-2px; z-index:1; }\n.song-cover:disabled { box-shadow:var(--soft-inset); }\n.adopt-take { grid-column:2; justify-self:start; font-size:10px; min-height:24px; }\n#inspector {\n  margin:1px 11px 10px; padding-top:8px; border-radius:11px; background:var(--panel); box-shadow:var(--soft-inset);\n}\n.inspector-switch { display:flex; gap:8px; margin-inline:10px; }\n.inspector-switch button { min-height:27px; padding-inline:9px; color:var(--muted); }\n.inspector-switch button[aria-pressed="true"] {\n  color:var(--accent); background:var(--selected); box-shadow:var(--soft-inset); font-weight:650;\n}\n#lyrics,#clip-details { padding:11px 12px; }\n#lyrics p { margin:0; color:var(--muted); line-height:1.8; white-space:pre-line; }\n#clip-details strong { font-size:12px; }\n#clip-details dl { margin:8px 0 0; display:grid; gap:1px; }\n#clip-details dl div { display:grid; grid-template-columns:max-content 1fr; gap:7px; border-bottom:1px solid var(--line); padding:4px 0; }\n#clip-details dt { color:var(--muted); }\n#clip-details dd { margin:0; text-align:end; font:10px ui-monospace,monospace; white-space:nowrap; }\n@media (max-width:680px) {\n  :host { --track-height:96px; --imw-video-row-height:88px; --track-action-height:65px; --ruler-height:32px; }\n  .mobile { display:inline-flex!important; align-items:center; }\n  .body { display:block; }\n  .editor { height:100%; padding-block-end:calc(var(--wb-dock,70px) + 28px); }\n  .arrangement { grid-template-columns:112px minmax(0,1fr); }\n  .toolbar { display:grid; grid-template-columns:auto minmax(0,1fr) auto; gap:5px; padding-inline:7px; }\n  .field { gap:3px; font-size:10px; }\n  .current-take { padding-inline-start:5px; gap:4px; flex-wrap:wrap; }\n  #song-title { font-size:10px; }\n  #project,#version,.toolbar-end select { font-size:10px; padding-inline:3px; }\n  .toolbar-end { gap:4px; }\n  .toolbar-end #tempo { display:none; }\n  .zoom span { display:none; }\n  #songs-toggle,#cut-quiet,#undo-cut { padding-inline:4px; }\n  #cut-quiet,#undo-cut { font-size:10px; }\n  .track-heading,.track-name { padding-inline:7px; gap:4px; }\n  .track-head { padding-inline:4px; column-gap:5px; }\n  .track-actions { display:grid; grid-template-columns:1fr; gap:3px; padding-inline:8px; }\n  .track-chevron { width:5px; height:5px; margin-inline-end:0; }\n  .track-label { font-size:11px; }\n  aside { position:absolute; inset:0 0 0 auto; width:min(292px,84%); z-index:5; display:none; box-shadow:var(--depth); }\n  aside.open { display:block; }\n}\n@media (max-width:380px) {\n  .current-take { border:0; padding:0; }\n  .toolbar .field:first-child { font-size:0; }\n  .toolbar-end { gap:3px; }\n}\n\n@media (prefers-reduced-motion:no-preference) {\n  .song-cover, .adopt-take { transition:color 90ms ease-out; }\n}\n\n.clip-menu {\n  min-width:150px; position:fixed; z-index:10000; padding:5px;\n  background:var(--panel); border:1px solid var(--line); border-radius:8px;\n  box-shadow:var(--depth);\n}\n.clip-menu button {\n  display:block; width:100%; text-align:left; border:0; background:none; box-shadow:none;\n  min-height:29px; white-space:nowrap;\n}\n.clip-menu button:hover,.clip-menu button:focus-visible { box-shadow:var(--soft-inset); }\n.studio[data-track-edit] .body { grid-template-columns:minmax(0,1fr); }\n.studio[data-track-edit] #songs,.studio[data-track-edit] #songs-toggle,\n.studio[data-track-edit] #cut-quiet,.studio[data-track-edit] #undo-cut { display:none!important; }\n.arrangement.single-track { flex:0 0 auto; max-height:180px; }\n.track-editor { flex:1; min-height:0; overflow:auto; padding:8px 14px 90px; }\n.track-editor-header,.track-tools,.track-form,.vocal-result { display:flex; align-items:center; flex-wrap:wrap; gap:8px; }\n.track-editor-header { margin-bottom:12px; padding-bottom:7px; border-bottom:1px solid var(--line); }\n.track-editor-header h2 { margin:0; font-size:15px; }\n.track-tools { margin-left:auto; }\n.track-tools [aria-pressed=true] { box-shadow:var(--soft-inset); color:var(--accent); }\n.track-pane { min-width:0; }\n.track-pane input { width:100%; min-width:0; font:inherit; color:var(--ink); background:var(--raised); border:1px solid var(--line); border-radius:7px; padding:4px 6px; box-shadow:var(--soft-inset); }\n.track-form input { display:inline-block; width:70px; }\n.track-pane a { color:var(--ink); padding:4px; }\n.track-form label { color:var(--muted); }\n#track-score-preview { overflow:auto; margin-top:10px; background:var(--layer); border:1px solid var(--line); }\n#track-note-roll { display:block; height:180px; min-width:100%; color:var(--head); border-color:var(--line); }\n#track-editor-status { color:var(--muted); min-height:18px; margin:8px 0 0; }\n.vocal-fields { display:grid; grid-template-columns:repeat(auto-fit,minmax(min(100%,235px),1fr)); gap:8px; align-items:start; }\n.vocal-fields fieldset { min-width:0; border:1px solid var(--line); border-radius:6px; display:grid; grid-template-columns:1fr 1fr; gap:6px; }\n.vocal-fields label { color:var(--muted); }\n.vocal-fields button { justify-self:start; grid-column:1/-1; }\n.vocal-result { margin-top:12px; }\n.vocal-result audio { display:block; max-width:100%; height:32px; }\n.vocal-commands { grid-column:1/-1; display:flex; align-items:center; flex-wrap:wrap; gap:5px; }\n.vocal-commands:empty { display:none; }\n.vocal-commands button[aria-pressed=true],#track-solo[aria-pressed=true] { box-shadow:var(--soft-inset); color:var(--accent); }\n#track-score-preview { background:none; border:0; }\n#track-score-layout { margin-block:8px; }\n#track-roll-scroll { overflow:auto; border:1px solid var(--line); background:var(--layer); }\n#track-notation { overflow:auto; padding-bottom:6px; }\n#track-notation .score { width:max-content; min-width:100%; margin:0 0 12px; padding:18px 20px 9px; background:#fcfbf8; color:#252525; }\n#track-notation .canvas { position:relative; margin-inline:auto; }\n#track-notation .score-title { text-align:center; font-size:19px; font-weight:700; }\n#track-notation .score-head { font-size:12px; margin:8px 18px 4px; }\n#track-notation .meta-tempo { margin-left:10px; }\n#track-notation [class^="el-"],#track-notation .slur-layer { position:absolute; color:#252525; }\n#track-notation .el-num { display:grid; place-items:center; font:18px Georgia,serif; }\n#track-notation .el-ul { height:1px; background:#252525; }\n#track-notation .el-dot { background:#252525; border-radius:50%; }\n#track-notation .el-bar { width:1px; background:#252525; }\n#track-notation .el-cursor { display:none; }\n#track-notation .score-pageno { text-align:center; color:#72716f; font-size:11px; }\n\n#download-master { color:var(--accent); font:inherit; font-size:12px; white-space:nowrap; }\n\n#master-settings { position:relative; }\n#master-settings > summary { cursor:pointer; white-space:nowrap; font-size:12px; }\n.master-popover { position:absolute; top:calc(100% + 8px); right:0; width:min(340px,84vw);\n  box-sizing:border-box; padding:12px; background:var(--panel); color:var(--ink); border:1px solid var(--line);\n  border-radius:10px; box-shadow:var(--soft-raise); }\n#master-values { margin:0; padding:0; border:0; display:grid; gap:6px 12px; grid-template-columns:repeat(2,minmax(0,1fr)); }\n#master-values label { display:flex; flex-direction:column; font-size:11px; gap:3px; }\n#master-values input, #master-values select { box-sizing:border-box; min-width:0; width:100%; max-width:100%;\n  height:28px; font:inherit; color:inherit; background:var(--panel); border:1px solid var(--line); border-radius:4px; }\n#master-values input[type=checkbox] { width:18px; align-self:flex-start; }\n#master-saved { display:block; margin-top:5px; }\n@media (max-width:600px) {\n  .toolbar { position:relative; }\n  #master-settings { position:static; }\n  .master-popover { left:8px; right:8px; width:auto; top:calc(100% + 4px); }\n}\n\n#master-delivery-info {font-size:12px;line-height:1.45;margin-bottom:8px;}\n#master-aac-player {width:100%;height:32px;}\n#download-aac {color:var(--accent);font-size:12px;white-space:nowrap;}\n\n#master-audition {display:flex;align-items:center;gap:6px;flex-wrap:wrap}\n#master-audition[hidden]{display:none}\n#master-bypass[aria-pressed=true]{font-weight:700;outline:2px solid currentColor}\n\n@media (max-width:680px) {\n  .toolbar { position:relative; grid-template-columns:minmax(0,max-content) minmax(0,1fr); gap:3px 5px; padding-block:3px }\n  .toolbar-end {\n    grid-column:1/-1;justify-self:stretch;margin:0;min-width:0;flex-wrap:wrap;\n    padding-top:2px;border-top:1px solid var(--line)\n  }\n  .current-take { flex-wrap:nowrap }\n  #song-title { flex:1;min-width:0;overflow:hidden;text-overflow:ellipsis;white-space:nowrap }\n  #version { max-width:54% }\n  #master-settings > summary { padding:5px 1px }\n  .master-popover { max-height:calc(100dvh - 220px);overflow:auto;overscroll-behavior:contain }\n}\n@media (min-width:360px) and (max-width:680px) {\n  #songs-toggle {\n    position:absolute; inset-inline-end:0;\n    inset-block-start:calc((28px - var(--lus-heading-height)) / 2 - 28px);\n    min-inline-size:30px; justify-content:center;\n  }\n}\n@media (max-width:430px) {\n  .master-settings-name { display:none; }\n}\n\n/* Picture and sound share the same horizontal viewport and fit-to-work scale. */\n#imw-screen,#imw-lane-labels,#imw-cut-lanes,#imw-inspect,#imw-captions,\n#imw-add-track,#imw-score-settings { display:none; }\n:host([data-imw-video]) #imw-score-settings {display:inline-flex}\n/* Keep a zero-height native arrangement in the audio grid column as the video scale reference. */\n#imw-audio-fit {display:none}\n:host([data-imw-video]) #imw-audio-fit {\n  display:grid;grid-area:1/1;align-self:start;height:0;visibility:hidden;overflow:hidden;pointer-events:none\n}\n:host([data-imw-video]) .editor {grid-column:1/-1;grid-row:1}\n@media(max-width:680px) {\n  :host([data-imw-video]) .body {display:grid;grid-template-columns:minmax(0,1fr)}\n}\n:host([data-imw-video]) .editor {\n  height:100%;padding:0 0 calc(var(--wb-dock,70px) + 5px);overflow:hidden;\n}\n:host([data-imw-video]) #imw-screen {\n  display:flex;flex:1 1 0;position:relative;width:100%;min-width:0;min-height:80px;overflow:hidden;\n}\n:host([data-imw-video]) #track-scroll-panel {\n  flex:0 1 auto; min-height:1.5em;max-height:62%; overflow:auto; align-content:start;\n  grid-template-columns:var(--imw-label-width) minmax(0,1fr);\n}\n/* Keep the original track-list column and timeline gutter in both modes. */\n:host([data-imw-video]) #lane {min-height:0;overflow:hidden}\n:host([data-imw-video]) #regions {position:relative;}\n:host([data-imw-video]) :is(#loop-band,#empty,#monitor-route,\n  #cut-quiet,#undo-cut,#master-settings,#output-master,.zoom,#tempo,.editor-footer) {display:none!important}\n:host([data-imw-video]) .track-list {z-index:1;min-width:0;}\n:host([data-imw-video]) #imw-lane-labels {display:block}\n:host([data-imw-video]) #imw-cut-lanes {display:block}\n:host([data-imw-video]) #playhead{z-index:3;pointer-events:none}\n:host([data-imw-video]) [data-track-row]:not([data-imw-track]),\n:host([data-imw-video]) .track-head[data-track-row]:not([data-imw-current]) {display:none}\n:host([data-imw-video]:not([data-imw-stems])) #imw-lane-labels::before {\n  content:"";display:block;height:var(--track-height)\n}\n#imw-empty-tracks {height:var(--track-height);margin:0;padding:0 10px;align-content:center;color:var(--muted);font-size:11px}\n:host([data-imw-video][data-imw-stems]) #regions {\n  display:grid;grid-template-rows:repeat(var(--imw-parts),minmax(0,1fr));height:var(--track-height)\n}\n:host([data-imw-video]) #regions .track-row[data-imw-track] {height:100%;min-height:0}\n:host([data-imw-video]) .track-head[data-imw-current] {height:var(--track-height)}\n:host([data-imw-video]) .track-head[data-imw-current][data-expanded] {grid-template-rows:minmax(0,1fr) auto}\n:host([data-imw-video]) .track-head[data-imw-current][data-expanded] .track-name {height:calc(100% - 5px)}\n:host([data-imw-video]) .track-head[data-imw-current][data-expanded] .track-monitor-controls {grid-area:1 / 2 / span 2}\n:host([data-imw-video]) .track-head[data-imw-current][data-expanded] .track-actions {\n  display:flex;grid-column:1;grid-row:2;flex-wrap:nowrap;gap:2px;padding:0 0 3px\n}\n:host([data-imw-video]) .track-head[data-imw-current][data-expanded] .track-actions button {\n  flex:1 1 0;min-width:0;min-height:19px;padding:1px;font-size:9px\n}\n:host([data-imw-compact]) #regions .track-row {box-shadow:inset 0 -1px color-mix(in srgb,var(--line) 55%,transparent)}\n:host([data-imw-compact]) #regions .clip-group {top:min(2px,5%);height:max(1px,90%);--clip-radius:min(6px,45%)}\n:host([data-imw-compact]) #regions .clip {min-height:0}\n:host([data-imw-compact]) #regions .clip canvas {top:4%;height:92%}\n:host([data-imw-compact]) #regions .trim-handle {inset-block:0}\n:host([data-imw-compact]) #regions .trim-handle::before {height:min(80%,13px)}\n:host([data-imw-compact]) #regions .clip-group[data-tight] .trim-handle.head {inset-block:0 50%}\n:host([data-imw-compact]) #regions .clip-group[data-tight] .trim-handle.tail {inset-block:50% 0}\n:host([data-imw-compact]) #regions .clip::after {bottom:0}\n:host([data-imw-dense]) #regions .track-row {box-shadow:none}\n:host([data-imw-dense]) #regions .clip-group {\n  top:0;height:100%;--clip-radius:0;border:0;box-shadow:none\n}\n:host([data-imw-dense]) #regions .clip-group::after,\n:host([data-imw-dense]) #regions .clip canvas,\n:host([data-imw-dense]) #regions .clip::after {display:none}\n:host([data-imw-dense]) #regions .clip:not(:disabled) {\n  top:0;height:calc(100% - 1px);border:0;border-radius:0;box-shadow:none;background:var(--tone)\n}\n:host([data-imw-dense]) #regions .track-row[data-monitor-muted] .clip:not(:disabled) {opacity:.45}\n:host([data-imw-dense]) #regions .clip-group:is([data-selected],:focus-within) .clip:not(:disabled) {\n  box-shadow:inset 0 0 0 1px var(--ink)\n}\n:host([data-imw-dense]) #regions .trim-handle::before {height:100%}\n:is(#imw-frame-rate-field,#imw-frame-zoom-field) {display:none}\n:host([data-imw-video]) :is(#imw-frame-rate-field,#imw-frame-zoom-field) {display:inline-flex;align-items:center;gap:5px}\n:host([data-imw-video]) {--ruler-height:20px}\n:host([data-imw-video]) .track-heading,:host([data-imw-video]) .ruler {height:var(--ruler-height)}\n.frame-time {display:none}\n:host([data-imw-video]) .ruler {overflow:hidden;touch-action:none;user-select:none;-webkit-user-select:none;}\n:host([data-imw-video]) .track-heading > span:first-child {display:none}\n:host([data-imw-video]) .track-heading .frame-time {\n  display:inline; font:600 10px/1 ui-monospace,monospace; font-variant-numeric:tabular-nums;\n  color:var(--ink); white-space:nowrap\n}\n:host([data-imw-video]) .ruler span {top:50%;transform:translateY(-50%);white-space:nowrap}\n\n:host([data-imw-video]) #imw-add-track:not([hidden]) {display:block;max-width:calc(100% - 8px);margin:4px;min-height:24px;font-size:10px;}\n:host([data-imw-video]) #imw-captions {display:inline-flex;margin-bottom:6px}\n:host([data-imw-video]) .toolbar #imw-video-toggle {background:var(--selected);color:var(--accent);box-shadow:var(--soft-inset);}\n:host([data-imw-video]) #songs {\n  display:none;position:absolute;z-index:8;inset:0 0 0 auto;width:min(300px,86%);box-shadow:var(--depth)\n}\n:host([data-imw-video]) #songs.open {display:block}\n:host([data-imw-video]) :is(#songs-toggle,#songs-close) {display:inline-flex!important}\n@media(max-width:760px) {\n  :host([data-imw-video]) #imw-inspect {display:inline-flex}\n}\n#imw-original-track {display:none}\n:host([data-imw-video]) #imw-original-track:not([hidden]) {display:block}\n#imw-original-track .clip svg {position:absolute;inset:6px 0;width:100%;height:calc(100% - 12px);color:var(--tone)}\n#imw-original-track[data-monitor-muted] .clip svg {opacity:.45}\n\n:host([data-imw-video]) .studio[data-track-edit] #track-editor:not([hidden]) {\n  position:absolute;z-index:6;inset:0 0 auto;max-height:55%;overflow:auto;background:var(--panel)\n}\n\n#imw-project {display:none}\n:host([data-imw-video]) #audio-project-field,\n:host([data-imw-video]:not([data-imw-song])) :is(.current-take,#songs-toggle,#songs) {display:none!important}\n:host([data-imw-video]) #imw-project {\n  display:block;max-width:min(45vw,300px);min-width:0;text-overflow:ellipsis;white-space:nowrap;overflow:hidden\n}\n\n/* The workstation settings live above the dock and take no row from the timeline. */\n#imw-settings {\n  position:fixed; inset:auto max(var(--wb-tool-gutter,16px),env(safe-area-inset-right)) calc(var(--wb-dock,70px) + 8px) auto;\n  margin:0; padding:14px; width:min(330px,calc(100vw - 32px)); max-height:calc(100dvh - var(--wb-dock,70px) - 54px);\n  overflow:auto; overscroll-behavior:contain; border:1px solid var(--line); border-radius:12px;\n  background:var(--panel); color:var(--ink); box-shadow:var(--depth);\n}\n#imw-settings:popover-open {display:grid;gap:12px}\n.imw-settings-heading,.imw-settings-actions {display:flex;align-items:center;gap:8px}\n.imw-settings-heading {justify-content:space-between}\n.imw-settings-heading button {width:26px;padding:0;font-size:18px}\n.imw-settings-actions {flex-wrap:wrap}\n#imw-settings .current-take {padding:0;border:0}\n#imw-settings :is(#project,#version) {max-width:100%;min-width:0}\n#imw-settings #audio-project-field select {flex:1}\n#imw-settings #songs-toggle {position:static}\n#imw-settings #master-settings {flex-basis:100%;position:static}\n#imw-settings .master-popover {position:static;width:100%;max-height:none;overflow:visible;box-shadow:none}\n@media(max-width:680px) {#imw-settings{inset-inline-end:max(8px,env(safe-area-inset-right))}}\n\n#imw-opening {display:none}\n:host([data-imw-opening]:not([data-imw-video])) #imw-screen {display:grid;place-items:center;min-height:20dvh;color:var(--muted)}\n:host([data-imw-opening]:not([data-imw-video])) #imw-opening {display:block}\n\n/* The picture lane retains its position and identity above the time ruler. */\n#imw-video-header,.track-list #imw-lane-labels {padding:0}\n:host(:not([data-imw-video])) #imw-video-header .track-head,\n#imw-folded-video {height:calc(var(--track-height) / 2);min-height:0}\n:host(:not([data-imw-video])) #imw-video-header .track-head {grid-template-rows:1fr}\n:host(:not([data-imw-video])) #imw-video-header .track-name {grid-column:1/-1;height:calc(var(--track-height) / 2 - 8px)}\n:host(:not([data-imw-video])) #imw-video-header .track-monitor-controls {display:none}\n#imw-folded-video {\n  display:block;position:relative;width:100%;border:0;border-radius:0;background:transparent;\n  color:var(--muted);font-size:10px;text-align:left;padding:0 9px;box-shadow:none\n}\n#imw-folded-video:hover,#imw-folded-video:focus-visible {background:var(--selected);color:var(--accent)}\n:host([data-imw-video]) #imw-folded-video {display:none}\n:host([data-imw-video]) #imw-video-label {--track-height:var(--imw-video-row-height)}\n:host([data-imw-empty-video]) #imw-folded-video {display:block;height:var(--imw-video-row-height)}\n#imw-picture-lane {position:relative;}\n#imw-video-header .track-head .track-label {font-size:12px}\n\n#imw-picture-lane,#imw-video-header {height:calc(var(--track-height) / 2);overflow:clip}\n:host([data-imw-video]) :is(#imw-picture-lane,#imw-video-header) {height:var(--imw-video-row-height,var(--track-height))}\n\n:host([data-imw-video][data-frame-zoom]) #lane {width:var(--frame-zoom-width)!important}\n.frame-grid {display:none;position:absolute;top:0;height:100%;overflow:hidden;pointer-events:none}\n:host([data-imw-video]) #lane[data-frame-grid] > .frame-grid {display:block}\n.frame-grid path {fill:none;stroke:color-mix(in srgb,var(--ink) 24%,transparent);stroke-width:1;stroke-dasharray:2 3;shape-rendering:crispEdges}\n:host([data-imw-video]) #lane[data-frame-grid] .ruler::after {\n  content:"";position:absolute;inset:auto 0 0;height:3px;pointer-events:none;\n  background:repeating-linear-gradient(to right,var(--grid-beat) 0 1px,transparent 1px var(--frame-pitch));\n}\n\n/* Until the shared disclosure animation settles, fading heads occupy their own original track positions. */\n:host([data-imw-track-motion]) .track-head[data-imw-track]:not([data-imw-current]),\n:host([data-imw-track-motion]) .track-head[data-imw-track] {display:grid;overflow:clip;min-height:0}\n\n:host([data-imw-track-motion][data-imw-dense]) #regions .clip canvas {display:block}\n\n#detached-lanes {position:relative}\n.detached-wave,.detached-wave svg {position:absolute;inset:7% 0;width:100%;height:86%;pointer-events:none;color:var(--tone)}\n.detached-wave svg {inset:0;height:100%}\n.detached-row[data-monitor-muted] .detached-wave {opacity:.45}\n.detached-head .track-actions {padding-inline:4px}\n.detached-head .track-actions label {display:inline-flex;align-items:center;gap:4px;min-width:0;max-width:100%;font-size:10px}\n.detached-head .track-actions input {width:60px;max-width:100%;accent-color:var(--tone)}\n:host([data-detached-audio]) :is(#empty,#imw-empty-tracks) {display:none!important}\n:host([data-detached-audio][data-imw-video]:not([data-imw-stems])) #imw-lane-labels::before {display:none}\n:host([data-detached-audio]) .arrangement.single-track {max-height:none;flex:1}\n';

  // assets/studio/studio-clips.css
  var studio_clips_default = '.clip-group {\n  position:absolute; top:6px; height:calc(var(--track-height) - 12px); z-index:1;\n  --clip-radius:min(10px,50%);\n}\n.clip-group:not(.offline)::after {\n  content:""; position:absolute; inset:0; pointer-events:none;\n  border-radius:var(--clip-radius);\n  box-shadow:inset 2px 3px 7px var(--relief-shadow),inset -2px -3px 6px var(--relief-light);\n}\n.clip {\n  position:absolute; inset:0;\n  width:100%; height:100%; padding:0; cursor:grab;\n  color:var(--clip-ink); background:transparent; box-shadow:none;\n  border:0; border-radius:var(--clip-radius); overflow:hidden; touch-action:none;\n}\n:host([data-paint-only]) .clip:disabled { opacity:1; cursor:default; }\n.clip-silence { position:absolute; inset-block:0; pointer-events:none; }\n.clip-silence.head { left:0; width:var(--silence-head,0%); }\n.clip-silence.tail { right:0; width:var(--silence-tail,0%); }\n.clip:active { cursor:grabbing; }\n.clip canvas {\n  position:absolute; top:8px; left:var(--silence-head,0%);\n  width:calc(100% - var(--silence-head,0%) - var(--silence-tail,0%));\n  height:calc(100% - 16px); color:var(--tone); background:transparent; pointer-events:none;\n}\n.clip-group[data-selected] { z-index:2; }\n.clip-group[data-tight] .clip { min-width:1px; }\n.clip-group[data-tight] .trim-handle.head { inset-block:2px 50%; }\n.clip-group[data-tight] .trim-handle.tail { inset-block:50% 2px; }\n.clip:focus-visible { outline:none; }\n.clip-group[data-selected] > .clip::after,.clip:focus-visible::after {\n  content:""; position:absolute; inset-inline:0; bottom:4px; margin-inline:auto;\n  width:min(16px,36%); height:2px; background:var(--focus); border-radius:1px;\n}\n.clip:focus-visible::after { height:3px; }\n.clip-group.offline .clip {\n  color:var(--muted); opacity:1; border:1px dashed var(--muted);\n  background:repeating-linear-gradient(135deg,var(--panel) 0 6px,var(--layer) 6px 10px);\n}\n.trim-handle {\n  position:absolute; inset-block:2px; z-index:1; min-height:0; width:14px; padding:0;\n  border:0; background:transparent; border-radius:3px; touch-action:none; cursor:ew-resize; color:var(--clip-ink);\n  box-shadow:none!important;\n}\n.trim-handle.head { left:-7px; }\n.trim-handle.tail { right:-7px; }\n.trim-handle::before {\n  content:""; position:absolute; top:50%; left:50%; transform:translate(-50%,-50%);\n  height:13px; width:2px; background:currentColor; border-radius:1px; opacity:0;\n}\n.clip-group:is(:hover,:focus-within,[data-selected]) .trim-handle::before { opacity:1; }\n.trim-handle:disabled { visibility:hidden; }\n.trim-handle:focus-visible { outline:none; }\n.trim-handle:focus-visible::before { width:3px; height:17px; }\n@media (hover:none) {\n  .trim-handle::before { opacity:.42; }\n}\n';

  // assets/studio/imw-disclosure.mjs
  function mountVideoDisclosure(studio) {
    const panel = studio.$("imw-screen"), regions = studio.$("regions");
    const reduce = matchMedia("(prefers-reduced-motion: reduce)");
    const timing = { duration: 320, easing: "cubic-bezier(.32,0,.2,1)", fill: "both" };
    let animation = null, trackAnimations = [], before = /* @__PURE__ */ new Map();
    const pictureRows = [studio.$("imw-picture-lane"), studio.$("imw-video-header")];
    function reset() {
      animation?.cancel();
      for (const run of trackAnimations) run.cancel();
      animation = null;
      trackAnimations = [];
      studio.removeAttribute("data-imw-motion");
      studio.removeAttribute("data-imw-track-motion");
      studio.style.removeProperty("--imw-reveal-height");
    }
    function takeHeight() {
      const height = panel.getBoundingClientRect().height;
      before = new Map([...pictureRows, ...studio.shadowRoot.querySelectorAll("[data-track-row]")].map((el) => [el, el.getBoundingClientRect().height]));
      reset();
      return height;
    }
    function animateHeight(el, start, end) {
      trackAnimations.push(el.animate([{ height: start + "px" }, { height: end + "px" }], timing));
    }
    function animateTracks(direction) {
      const opened = studio.hasAttribute("data-imw-video");
      if (!opened) return;
      const closing = direction === "closing";
      for (const el of pictureRows) {
        const current = el.getBoundingClientRect().height;
        const end2 = closing ? parseFloat(getComputedStyle(el).getPropertyValue("--track-height")) / 2 : current;
        animateHeight(el, before.get(el) ?? current, end2);
      }
      if (!studio.imw?.trackSelection()) return;
      const rows = [...regions.querySelectorAll(".track-row[data-imw-track]")];
      if (rows.length < 2) return;
      const start = [], end = [];
      const heads = [];
      for (const row of rows) {
        const head = studio.trackHeads.get(row.dataset.trackRow)?.parentElement;
        if (!head) return;
        const style = getComputedStyle(row);
        const normal = parseFloat(style.getPropertyValue("--track-height"));
        const expanded = row.hasAttribute("data-expanded") ? parseFloat(style.getPropertyValue("--track-action-height")) : 0;
        start.push(before.get(row) ?? row.getBoundingClientRect().height);
        end.push(closing ? normal + expanded : normal / rows.length);
        heads.push([
          head,
          before.get(head) ?? head.getBoundingClientRect().height,
          closing ? normal + expanded : head.hasAttribute("data-imw-current") ? normal : 0
        ]);
      }
      const tracks = (heights) => ({
        height: heights.reduce((sum, value) => sum + value, 0) + "px",
        gridTemplateRows: heights.map((value) => value + "px").join(" ")
      });
      studio.setAttribute("data-imw-track-motion", "");
      trackAnimations.push(regions.animate([tracks(start), tracks(end)], timing));
      for (const [el, from, to] of heads) animateHeight(el, from, to);
      if (studio.hasAttribute("data-imw-dense")) {
        const normal = parseFloat(getComputedStyle(rows[0]).getPropertyValue("--track-height"));
        const compact = normal / rows.length;
        const visibility = Math.max(0, Math.min(1, (start[0] - compact) / (normal - compact)));
        const target = closing ? 1 : 0;
        for (const canvas of regions.querySelectorAll(".clip:not(:disabled) canvas")) {
          const tone = getComputedStyle(canvas).color;
          const background = (wave) => `color-mix(in srgb,${tone} ${(1 - wave) * 100}%,transparent)`;
          trackAnimations.push(canvas.animate([{ opacity: visibility }, { opacity: target }], timing));
          trackAnimations.push(canvas.closest(".clip").animate([
            { backgroundColor: background(visibility) },
            { backgroundColor: background(target) }
          ], timing));
        }
        studio.paint(normal);
      }
    }
    function move(from, to, direction) {
      if (reduce.matches || typeof panel.animate !== "function" || Math.abs(to - from) < 1) return Promise.resolve(true);
      studio.dataset.imwMotion = direction;
      studio.style.setProperty("--imw-reveal-height", Math.max(from, to) + "px");
      const keyframe = (height) => ({ flexGrow: 0, flexShrink: 0, flexBasis: height + "px", minHeight: "0px", height: height + "px" });
      const run = panel.animate([keyframe(from), keyframe(to)], timing);
      animation = run;
      animateTracks(direction);
      const instant = document.timeline.currentTime;
      if (instant !== null) for (const step of [run, ...trackAnimations]) step.startTime = instant;
      return run.finished.then(() => {
        if (animation !== run) return false;
        if (direction !== "closing") {
          reset();
          studio.paint();
        }
        return true;
      }, () => false);
    }
    return {
      takeHeight,
      reset,
      reveal(from) {
        return move(from, panel.getBoundingClientRect().height, "opening");
      },
      collapse() {
        return move(takeHeight(), 0, "closing");
      },
      reversing() {
        return studio.dataset.imwMotion === "closing";
      }
    };
  }

  // assets/studio/output-master.mjs
  async function mountMasterControls(studio) {
    try {
      const { parameters } = await studioAction({ action: "parameters" });
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
          control.step = [2, 5, 6, 7].includes(p.id) ? "0.1" : "1";
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
    return studio.masterParameters.map((p) => {
      const field = studio.$("master-param-" + p.id);
      if (p.id !== 11 && !field.reportValidity()) throw Error("\u8BF7\u68C0\u67E5\u6BCD\u5E26\u53C2\u6570");
      return p.id === 11 ? Number(field.checked) : Number(field.value);
    });
  }
  function sourceNote(sources) {
    if (!sources?.length) return "\u539F\u59CB\u7D20\u6750\u6765\u6E90\u672A\u6838\u5B9E\u3002";
    const bits = [...new Set(sources.map((s) => s.bits))];
    const rates = [...new Set(sources.map((s) => s.rate))];
    const hz = rates.map((n) => n ? n / 1e3 + " kHz" : "\u672A\u77E5\u91C7\u6837\u7387").join("\u3001");
    const depth = bits.map((n) => n ? n + " \u4F4D" : "\u672A\u77E5\u4F4D\u6DF1").join("\u3001");
    return (sources.length > 1 ? "\u539F\u59CB\u5206\u8F68 " : "\u539F\u59CB\u97F3\u9891 ") + depth + "\uFF0C" + hz + "\u3002";
  }
  function rateReason(mode) {
    return {
      project: "\u5DE5\u7A0B\u58F0\u660E",
      uniform_sources: "\u97F3\u6E90\u91C7\u6837\u7387\u4E00\u81F4",
      chosen_project_rate: "\u7528\u6237\u9009\u62E9\u7684\u5DE5\u7A0B\u91C7\u6837\u7387",
      mixed_sources: "\u591A\u79CD\u539F\u59CB\u91C7\u6837\u7387\uFF0C\u8BF7\u9009\u62E9\u5DE5\u7A0B\u91C7\u6837\u7387",
      unknown_sources: "\u90E8\u5206\u97F3\u6E90\u91C7\u6837\u7387\u672A\u77E5\uFF0C\u8BF7\u9009\u62E9\u5DE5\u7A0B\u91C7\u6837\u7387"
    }[mode] ?? "\u6765\u6E90\u672A\u77E5";
  }
  function showDelivery(studio, version) {
    studio.disposeBus?.();
    const monitor = studio.$("master-audition");
    monitor.hidden = !version.mastered || !version.previewAAC;
    const form = studio.$("master-rate-choice"), rate = studio.$("master-rate");
    const info = studio.$("master-delivery-info"), player = studio.$("master-aac-player");
    player.pause();
    player.removeAttribute("src");
    player.hidden = true;
    if (!monitor.hidden) setupAudition(studio, version);
    studio.$("master-export").hidden = true;
    studio.masterAnalysis = null;
    form.hidden = true;
    if (version.mastered) {
      if (!version.delivery) {
        info.textContent = "\u5386\u53F2\u6BCD\u5E26 \xB7 \u539F\u59CB\u683C\u5F0F";
        return;
      }
      info.textContent = sourceNote(version.sourceMedia) + "\u5DE5\u7A0B " + version.sampleRate / 1e3 + " kHz\uFF08" + rateReason(version.rateBasis) + "\uFF09\uFF0C\u6DF7\u97F3\u6BCD\u5E26\u5904\u7406\u540E\u5BFC\u51FA 24 \u4F4D PCM\u3002\u54CD\u5EA6\u76EE\u6807 " + version.settings[2] + " LUFS \u7531\u9879\u76EE\u81EA\u5B9A\u3002\u672A\u63D0\u4F9B Apple Digital Masters \u539F\u59CB\u9AD8\u5206\u8FA8\u7387\u6765\u6E90\u8BC1\u660E\u6216\u8BA4\u8BC1\u3002";
      const qc = version.deliveryQC;
      if (qc?.pcm && qc.aac) info.textContent += " PCM " + qc.pcm.integrated_lufs + " LUFS-I / " + qc.pcm.true_peak_dbtp + " dBTP\uFF0CAAC \u89E3\u7801\u540E " + qc.aac.true_peak_dbtp + " dBTP\uFF0C\u524A\u6CE2 " + (qc.aac.on_sample + qc.aac.inter_sample) + "\u3002\u4EA4\u4ED8\u589E\u76CA " + qc.gain_trim_db + " dB\u3002";
      return;
    }
    const layout = version.masterRate;
    if (!layout) {
      info.textContent = "\u5F53\u524D\u7F16\u6392\u7F3A\u5C11\u5A92\u4F53\u4FE1\u606F\u3002";
      return;
    }
    const lower = layout.rate && !layout.supported.includes(layout.rate);
    info.textContent = sourceNote(layout.sources) + rateReason(layout.basis) + "\u3002" + (lower ? "\u6B64\u539F\u59CB\u91C7\u6837\u7387\u4E0D\u6EE1\u8DB3\u5F53\u524D\u4EA4\u4ED8\u89C4\u683C\u3002" : "\u5BFC\u51FA\u7ACB\u4F53\u58F0 24 \u4F4D PCM\uFF0C\u5E76\u6838\u9A8C AAC \u8BD5\u542C\u7248\u3002\u9ED8\u8BA4 \u221214 LUFS \u662F\u9879\u76EE\u81EA\u5B9A\u54CD\u5EA6\u3002");
    if (!layout.rate && ["mixed_sources", "unknown_sources"].includes(layout.basis)) {
      form.hidden = false;
      rate.replaceChildren(new Option("\u9009\u62E9\u91C7\u6837\u7387", ""), ...layout.supported.map((n) => new Option(n / 1e3 + " kHz", String(n))));
    }
  }
  function syncMasterControls(studio) {
    const button3 = studio.$("output-master"), version = studio.version;
    button3.hidden = !version || !!version.mastered || !!version.paintOnly || !!version.pending;
    button3.disabled = !!studio.masterBusy || !studio.draft || !!studio.recoveryConflict;
    const panel = studio.$("master-settings");
    panel.hidden = !studio.masterParameters || !version?.tracks.length || !!version.pending || !!version.paintOnly;
    button3.disabled ||= !studio.masterParameters || !!(version?.masterRate?.rate && !version.masterRate.supported.includes(version.masterRate.rate));
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
      studio.$("master-saved").textContent = missingSnapshot ? "\u6B64\u5386\u53F2\u7248\u672A\u8BB0\u5F55\u53C2\u6570\u3002" : version.mastered ? "\u6B64\u7248\u672C\u4F7F\u7528\u7684\u8BBE\u7F6E" : "";
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
    adopt.textContent = adopt.disabled ? "\u5DF2\u91C7\u7528" : "\u91C7\u7528\u6B64\u6BCD\u5E26";
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
      aacLink.onclick = (event) => {
        event.preventDefault();
        void downloadFile(studio, aacLink, version.previewAAC);
      };
      aacLink.download = studio.song.name + " - AAC.m4a";
    } else {
      aacLink.removeAttribute("href");
    }
    if (version?.mastered) {
      download.textContent = version.delivery ? "\u4E0B\u8F7D 24 \u4F4D WAV" : "\u4E0B\u8F7D\u6BCD\u5E26 WAV";
      download.href = "#";
      download.onclick = (event) => {
        event.preventDefault();
        void downloadFile(studio, download, version.tracks[0].url);
      };
      download.download = studio.song.name + " - " + version.name + ".wav";
    } else {
      download.removeAttribute("href");
    }
  }
  function clearAnalysis(studio, { continueStems = false } = {}) {
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
    studio.$("master-saved").textContent = "\u8BBE\u7F6E\u5DF2\u53D8\u66F4\u3002\u5206\u6790\u540E\u53EF\u4EE5\u8BD5\u542C\u548C\u5BFC\u51FA\u3002";
    if (resume && (studio.loopEnabled || studio.seconds < studio.length)) studio.play({ clock });
  }
  async function finishJob(studio, session, scope, request) {
    let result = request;
    for (let checks = 0; result.state === "running" && checks < 900; checks++) {
      await new Promise((resolve) => setTimeout(resolve, 850));
      if (session !== studio.load || session.signal.aborted) return null;
      result = await studioAction({ action: "master_status", ...scope, job: request.job });
    }
    if (result.state !== "ready") throw Error(result.error ?? "studio_master_unconfirmed");
    return result;
  }
  function reportFailure(studio, error) {
    studio.status({
      draft_changed: "\u8349\u7A3F\u5DF2\u53D8\u5316\u3002\u4FDD\u5B58\u5F53\u524D\u7F16\u8F91\u540E\u518D\u5206\u6790\u3002",
      analysis_changed: "\u5206\u8F68\u6216\u526A\u8F91\u5DF2\u53D8\u66F4\uFF0C\u8BF7\u91CD\u65B0\u5206\u6790\u5F53\u524D\u7F16\u6392\u3002",
      studio_media_changed: "\u5206\u8F68\u539F\u4EF6\u5DF2\u53D8\u5316\uFF0C\u8BF7\u68C0\u67E5\u9879\u76EE\u7D20\u6750\u3002",
      studio_master_busy: "\u672C\u673A\u5DF2\u6709\u6BCD\u5E26\u4EFB\u52A1\u8FDB\u884C\u4E2D\u3002",
      choose_project_rate: "\u8BF7\u5728\u6BCD\u5E26\u8BBE\u7F6E\u4E2D\u9009\u62E9\u5DE5\u7A0B\u91C7\u6837\u7387\u3002",
      studio_master_unconfirmed: "\u6BCD\u5E26\u4ECD\u5728\u5904\u7406\uFF0C\u5237\u65B0\u6B4C\u5355\u53EF\u68C0\u67E5\u7ED3\u679C\u3002"
    }[error.message] ?? "\u6BCD\u5E26\u5904\u7406\u5931\u8D25\uFF0C\u539F\u5206\u8F68\u548C\u5DF2\u91C7\u7528\u7248\u672C\u4ECD\u53EF\u67E5\u770B\u3002");
  }
  async function renderStudioMaster(studio) {
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
      const scope = { project: project.id, song: song.id, version: version.id };
      const fieldset = studio.$("master-values");
      const settings = selectedSettings(studio), snapshot = audibleState(studio);
      fieldset.disabled = true;
      studio.$("master-rate").disabled = true;
      studio.status("\u6B63\u5728\u5206\u6790 " + version.tracks.length + " \u8F68\u7F16\u6392\u7684 Stereo Out\u2026");
      const request = await studioAction({ action: "start_analysis", ...scope, revision: draft.revision, rate, settings });
      const result = await finishJob(studio, session, scope, request);
      if (!result || session !== studio.load || snapshot !== audibleState(studio)) return;
      const resume = studio.playing;
      if (resume) studio.stopAndRemember();
      studio.masterAnalysis = {
        id: result.id,
        analysis: result.id,
        session,
        scope,
        snapshot,
        frames: result.frames,
        sampleRate: result.sampleRate
      };
      studio.busBypass = false;
      studio.syncTrackMonitorControls?.();
      const monitor = studio.$("master-audition"), exportButton = studio.$("master-export");
      monitor.hidden = false;
      exportButton.hidden = false;
      studio.$("master-listen").onclick = () => void studio.toggle();
      const bypass = studio.$("master-bypass");
      bypass.disabled = false;
      bypass.setAttribute("aria-pressed", "false");
      bypass.onclick = () => {
        studio.busBypass = !studio.busBypass;
        bypass.setAttribute("aria-pressed", String(studio.busBypass));
        studio.liveMonitor?.setBypass(studio.busBypass);
        studio.syncTrackMonitorControls?.();
      };
      if (resume) void studio.toggle();
      exportButton.onclick = () => void exportMaster(studio);
      studio.$("master-saved").textContent = "\u5DF2\u5206\u6790\u5F53\u524D\u7F16\u6392";
      studio.status("Output Master \u5DF2\u5C31\u7EEA\uFF0C\u53EF\u8BD5\u542C\u6E7F\u58F0\u3001\u65C1\u8DEF\u6216\u5BFC\u51FA");
    } catch (error) {
      if (studio.load === session) reportFailure(studio, error);
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
    const button3 = studio.$("master-export");
    button3.disabled = true;
    studio.masterBusy = true;
    syncMasterControls(studio);
    try {
      if (!await studio.save() || prepared.session !== studio.load) return;
      studio.status("\u6B63\u5728\u5BFC\u51FA\u539F\u751F\u7387 24 \u4F4D WAV\uFF0C\u5E76\u6838\u9A8C Apple AAC\u2026");
      const response2 = await studioAction({
        action: "start_master",
        ...prepared.scope,
        revision: studio.draft.revision,
        analysis: prepared.id
      });
      const result = await finishJob(studio, prepared.session, prepared.scope, response2);
      if (!result || prepared.session !== studio.load) return;
      await studio.refreshCatalog();
      if (prepared.session !== studio.load) return;
      await studio.change(prepared.scope.project, prepared.scope.song, result.id);
      studio.$("master-settings").open = true;
      studio.status("Output Master \xB7 24 \u4F4D WAV \u548C AAC \u5DF2\u6838\u9A8C");
    } catch (error) {
      if (studio.load === prepared.session) reportFailure(studio, error);
    } finally {
      button3.disabled = false;
      studio.masterBusy = false;
      syncMasterControls(studio);
    }
  }
  async function downloadFile(studio, link, path) {
    if (link.dataset.busy) return;
    const session = studio.load;
    const old = link.textContent;
    link.dataset.busy = "true";
    link.textContent = "\u8BFB\u53D6\u6587\u4EF6\u4E2D\u2026";
    try {
      const result = await studioFetch(path, { signal: session.signal });
      if (!result.ok) throw Error();
      const url = URL.createObjectURL(await result.blob());
      const download = document.createElement("a");
      download.href = url;
      download.download = link.download;
      studio.shadowRoot.append(download);
      download.click();
      download.remove();
      setTimeout(() => URL.revokeObjectURL(url), 6e4);
    } catch {
      if (!session.signal.aborted) studio.status("\u65E0\u6CD5\u8BFB\u53D6\u4E0B\u8F7D\uFF0C\u8BF7\u91CD\u8BD5\u3002");
    } finally {
      delete link.dataset.busy;
      if (studio.load === session) link.textContent = old;
    }
  }
  function setupAudition(studio, version) {
    studio.$("master-listen").textContent = "\u8BD5\u542C\u603B\u7EBF";
    const player = studio.$("master-aac-player"), listen = studio.$("master-listen"), bypass = studio.$("master-bypass");
    const controller = new AbortController();
    const sources = /* @__PURE__ */ new Map();
    let epoch = 0, dry = false, desired = false;
    bypass.setAttribute("aria-pressed", "false");
    bypass.disabled = !version.bypassAAC;
    player.onplay = () => {
      if (studio.playing) studio.pause();
    };
    async function choose(next, autoplay) {
      const observed = ++epoch;
      desired = next;
      const offset = player.currentTime || 0;
      try {
        const url = next ? version.bypassAAC : version.previewAAC;
        if (!sources.has(url)) {
          const reply = await studioFetch(url, { signal: controller.signal });
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
          try {
            await player.play();
          } catch {
            studio.status("\u8BF7\u70B9\u64AD\u653E\u5668\u7684\u64AD\u653E\u952E\u5F00\u59CB\u8BD5\u542C\u3002");
          }
        }
      } catch {
        if (observed === epoch && !controller.signal.aborted) {
          desired = dry;
          studio.status("\u8BD5\u542C\u6587\u4EF6\u6682\u4E0D\u53EF\u7528\u3002");
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

  // assets/studio/wave-peaks.mjs
  var blockSize = 128;
  function buildWaveIndex(channels) {
    const frames = channels[0].length;
    const blocks = Math.ceil(frames / blockSize);
    const lows = new Float32Array(blocks);
    const highs = new Float32Array(blocks);
    const energy = new Float64Array(blocks);
    for (let block = 0; block < blocks; block++) {
      const from = block * blockSize;
      const to = Math.min(frames, from + blockSize);
      let low = Infinity;
      let high = -Infinity;
      let squares = 0;
      for (const samples of channels) {
        for (let frame = from; frame < to; frame++) {
          const value = samples[frame];
          if (value < low) low = value;
          if (value > high) high = value;
          squares += value * value;
        }
      }
      lows[block] = low;
      highs[block] = high;
      energy[block] = squares;
    }
    return { lows, highs, energy };
  }
  function wavePeaks(channels, start, visible, width, rms, index) {
    const result = new Float32Array(width * 2);
    const frames = channels[0].length;
    for (let x = 0; x < width; x++) {
      const from = Math.max(0, Math.floor(start + x * visible / width));
      const to = Math.min(frames, Math.max(from + 1, Math.floor(start + (x + 1) * visible / width)));
      let min = Infinity;
      let max = -Infinity;
      let squares = 0;
      const first = index ? Math.ceil(from / blockSize) : 0;
      const last = index ? Math.floor(to / blockSize) : 0;
      const leftEnd = first < last ? first * blockSize : to;
      const rightStart = first < last ? last * blockSize : to;
      for (let block = first; block < last; block++) {
        min = Math.min(min, index.lows[block]);
        max = Math.max(max, index.highs[block]);
        if (rms) squares += index.energy[block];
      }
      for (const samples of channels) {
        for (let frame = from; frame < leftEnd; frame++) {
          const value = samples[frame];
          if (value < min) min = value;
          if (value > max) max = value;
          if (rms) squares += value * value;
        }
        for (let frame = rightStart; frame < to; frame++) {
          const value = samples[frame];
          if (value < min) min = value;
          if (value > max) max = value;
          if (rms) squares += value * value;
        }
      }
      if (from < to) {
        result[x * 2] = min;
        result[x * 2 + 1] = max;
        if (rms) rms[x] = Math.sqrt(squares / ((to - from) * channels.length));
      }
    }
    return result;
  }
  function cutQuietRanges(channels, sampleRate, sourceIn, duration, index) {
    const first = Math.round(sourceIn * sampleRate);
    const last = Math.min(channels[0].length, Math.round((sourceIn + duration) * sampleRate));
    const span = last - first;
    if (span <= 0) return { ranges: [[0, duration]], count: 0 };
    const windowSize = Math.round(0.02 * sampleRate);
    const alignedStart = Math.min(last, Math.ceil(first / windowSize) * windowSize);
    const alignedEnd = Math.max(alignedStart, Math.floor(last / windowSize) * windowSize);
    const windows = Math.floor((alignedEnd - alignedStart) / windowSize);
    const threshold = 10 ** (-48 / 20);
    const minimumFrames = Math.ceil(0.12 * sampleRate);
    const ranges = [];
    let retained = first;
    let quietStart = null;
    let count = 0;
    const endQuiet = (end) => {
      if (quietStart !== null && end - quietStart >= minimumFrames) {
        if (quietStart > retained) ranges.push([(retained - first) / sampleRate, (quietStart - first) / sampleRate]);
        retained = end;
        count++;
      }
      quietStart = null;
    };
    const inspect = (low, high, at) => {
      if (Math.max(-low, high) < threshold) quietStart ??= at;
      else endQuiet(at);
    };
    if (alignedStart > first) {
      const edge = wavePeaks(channels, first, alignedStart - first, 1, void 0, index);
      inspect(edge[0], edge[1], first);
    }
    if (windows) {
      const peaks = wavePeaks(channels, alignedStart, windows * windowSize, windows, void 0, index);
      for (let window2 = 0; window2 < windows; window2++) {
        inspect(peaks[2 * window2], peaks[2 * window2 + 1], alignedStart + window2 * windowSize);
      }
    }
    if (last > alignedEnd) {
      const edge = wavePeaks(channels, alignedEnd, last - alignedEnd, 1, void 0, index);
      inspect(edge[0], edge[1], alignedEnd);
    }
    endQuiet(last);
    if (retained < last) ranges.push([(retained - first) / sampleRate, duration]);
    return { ranges, count };
  }

  // assets/studio/timeline-grid.mjs
  function timelineGrid({ length, width, bpm, meter }) {
    const pixels = width / length;
    if (bpm > 0 && meter?.beats > 0 && meter?.note > 0) {
      const beat = 60 / bpm * 4 / meter.note;
      const bar = meter.beats * beat;
      const stride = Math.max(1, Math.ceil(41 / (bar * pixels)));
      const subdivisions = beat * pixels >= 70 ? 4 : beat * pixels >= 32 ? 2 : 1;
      const labels2 = [];
      for (let index = 0; index * bar < length; index += stride) {
        labels2.push({ at: index * bar, label: String(index + 1) });
      }
      return {
        unit: "\u5C0F\u8282",
        labels: labels2,
        major: bar * pixels >= 9 ? bar : bar * stride,
        beat: beat * pixels >= 8 ? beat : 0,
        detail: subdivisions > 1 ? beat / subdivisions : 0
      };
    }
    const step = [1, 2, 5, 10, 15, 30, 60, 120].find((seconds) => seconds * pixels >= 44) ?? 120;
    const labels = [];
    for (let second = 0; second < length; second += step) {
      const minute = Math.floor(second / 60);
      labels.push({ at: second, label: minute + ":" + String(second % 60).padStart(2, "0") });
    }
    return { unit: "\u65F6\u95F4", labels, major: step, beat: step / 5 * pixels >= 9 ? step / 5 : 0, detail: 0 };
  }

  // assets/studio/audio-start.mjs
  async function confirmOutput(context, destination, player, signal, budget) {
    const wallStart = performance.now();
    const audioStart = context.currentTime;
    const mediaStart = player?.currentTime ?? 0;
    const minimum = 256 / context.sampleRate;
    const prime = context.createBufferSource();
    prime.buffer = context.createBuffer(1, Math.ceil(context.sampleRate * 0.1), context.sampleRate);
    prime.connect(destination);
    let rejection;
    let started = false;
    try {
      void context.resume().catch((error) => {
        rejection = error;
      });
      if (player) void player.play().catch((error) => {
        rejection = error;
      });
      prime.start(audioStart);
      started = true;
      while (!signal.aborted) {
        if (rejection) throw rejection;
        const rendered = context.state === "running" && context.currentTime - audioStart >= minimum;
        const delivered = !player || !player.paused && player.currentTime > mediaStart;
        if (rendered && delivered) return true;
        if (context.state === "closed" || performance.now() - wallStart >= budget) return false;
        await new Promise((resolve) => setTimeout(resolve, 24));
      }
      return false;
    } finally {
      if (started) prime.stop();
      prime.disconnect();
    }
  }

  // assets/studio/track-score/model.mjs
  var Model = /* @__PURE__ */ (() => {
    let _uid = 1;
    function uid() {
      return _uid++;
    }
    function makeNote(degree, octave = 0) {
      return {
        id: uid(),
        type: degree === 0 ? "rest" : "note",
        degree,
        octave,
        accidental: "",
        dur: 4,
        // 默认四分音符
        dots: 0,
        lyric: ""
        // 该音符下方对应的一个音节(空字符串=无词占位)
      };
    }
    function makeBarline(subtype) {
      return { id: uid(), type: "barline", subtype: subtype || "normal" };
    }
    function makeTimeSig(timeSig) {
      return { id: uid(), type: "timesig", time: timeSig || "4/4" };
    }
    function underlines(dur) {
      if (dur <= 4) return 0;
      return Math.round(Math.log2(dur / 4));
    }
    function dashes(dur) {
      if (dur === 2) return 1;
      if (dur === 1) return 3;
      return 0;
    }
    function beats(note) {
      if (!note || note.type === "barline" || note.type === "timesig") return 0;
      let b = 4 / note.dur;
      if (note.dots === 1) b *= 1.5;
      if (note.dots === 2) b *= 1.75;
      return b;
    }
    function barCapacity(timeSig) {
      const m = /^(\d+)\s*\/\s*(\d+)$/.exec(timeSig || "4/4");
      if (!m) return 4;
      const numer = parseInt(m[1], 10), denom = parseInt(m[2], 10);
      return numer * (4 / denom);
    }
    function applyAction(note, act) {
      if (!note || note.type === "barline") return false;
      switch (act) {
        case "octaveUp":
          note.octave = Math.min(2, note.octave + 1);
          return true;
        case "octaveDown":
          note.octave = Math.max(-2, note.octave - 1);
          return true;
        case "durHalf":
          note.dur = 2;
          note.dots = 0;
          return true;
        case "durQuarter":
          note.dur = 4;
          note.dots = 0;
          return true;
        case "durEighth":
          note.dur = 8;
          note.dots = 0;
          return true;
        case "durSixteenth":
          note.dur = 16;
          note.dots = 0;
          return true;
        case "dot":
          note.dots = note.dots ? 0 : 1;
          return true;
        // 切换附点
        case "sharp":
          note.accidental = note.accidental === "sharp" ? "" : "sharp";
          return true;
        case "flat":
          note.accidental = note.accidental === "flat" ? "" : "flat";
          return true;
        case "natural":
          note.accidental = note.accidental === "natural" ? "" : "natural";
          return true;
        default:
          return false;
      }
    }
    const KEY_TONIC = {
      "C": 0,
      "G": 7,
      "D": 2,
      "A": 9,
      "E": 4,
      "B": 11,
      "F": 5,
      "bC": 11,
      "bB": 10,
      "bE": 3,
      "bA": 8,
      "bD": 1,
      "bG": 6,
      "F#": 6,
      "C#": 1,
      "G#": 8,
      "D#": 3,
      "A#": 10
    };
    function formatKeyName(key) {
      return String(key || "C").replace(/^b/, "\u266D").replace(/#$/, "\u266F");
    }
    const DEGREE_SEMI = { 1: 0, 2: 2, 3: 4, 4: 5, 5: 7, 6: 9, 7: 11 };
    function pitchToMidi(note, key) {
      if (!note || note.type !== "note") return null;
      const tonic = KEY_TONIC[key] != null ? KEY_TONIC[key] : 0;
      const deg = DEGREE_SEMI[note.degree];
      if (deg == null) return null;
      let acc = 0;
      if (note.accidental === "sharp") acc = 1;
      else if (note.accidental === "flat") acc = -1;
      return 60 + tonic + deg + acc + (note.octave || 0) * 12;
    }
    function midiToNotation(midi, key, preferFlat = false) {
      const tonic = KEY_TONIC[key] != null ? KEY_TONIC[key] : 0;
      const diff = Math.round(Number(midi)) - (60 + tonic);
      const semi = (diff % 12 + 12) % 12;
      const natural = Object.entries(DEGREE_SEMI).find(([, value]) => value === semi);
      let degree;
      let accidental = "";
      if (natural) {
        degree = Number(natural[0]);
      } else if (preferFlat) {
        const upper = Object.entries(DEGREE_SEMI).find(([, value]) => value === (semi + 1) % 12);
        degree = Number(upper[0]);
        accidental = "flat";
      } else {
        const lower = Object.entries(DEGREE_SEMI).find(([, value]) => value === semi - 1);
        degree = Number(lower[0]);
        accidental = "sharp";
      }
      return {
        degree,
        accidental,
        octave: Math.max(-2, Math.min(2, Math.floor(diff / 12)))
      };
    }
    function midiToFreq(midi) {
      return 440 * Math.pow(2, (midi - 69) / 12);
    }
    function degreeToFreq(degree, octave, key) {
      const midi = pitchToMidi({ type: "note", degree, octave: octave || 0, accidental: "" }, key);
      return midi == null ? null : midiToFreq(midi);
    }
    return {
      makeNote,
      makeBarline,
      makeTimeSig,
      underlines,
      dashes,
      beats,
      barCapacity,
      applyAction,
      uid,
      pitchToMidi,
      midiToNotation,
      midiToFreq,
      degreeToFreq,
      formatKeyName,
      KEY_TONIC,
      DEGREE_SEMI
    };
  })();

  // assets/studio/track-score/xml.mjs
  var XmlImport = /* @__PURE__ */ (() => {
    const STEP_SEMI = { C: 0, D: 2, E: 4, F: 5, G: 7, A: 9, B: 11 };
    const MAJOR_KEYS = {
      "-7": "bC",
      "-6": "bG",
      "-5": "bD",
      "-4": "bA",
      "-3": "bE",
      "-2": "bB",
      "-1": "F",
      "0": "C",
      "1": "G",
      "2": "D",
      "3": "A",
      "4": "E",
      "5": "B",
      "6": "F#",
      "7": "C#"
    };
    const MINOR_KEYS = {
      "-7": "bA",
      "-6": "bE",
      "-5": "bB",
      "-4": "F",
      "-3": "C",
      "-2": "G",
      "-1": "D",
      "0": "A",
      "1": "E",
      "2": "B",
      "3": "F#",
      "4": "C#",
      "5": "G#",
      "6": "D#",
      "7": "A#"
    };
    function keyInfoFromFifths(fifths, mode) {
      const normalizedMode = String(mode || "major").trim().toLowerCase() === "minor" ? "minor" : "major";
      const tonalName = (normalizedMode === "minor" ? MINOR_KEYS : MAJOR_KEYS)[String(fifths)] || (normalizedMode === "minor" ? "A" : "C");
      const name = MAJOR_KEYS[String(fifths)] || "C";
      const tonic = Model.KEY_TONIC[name] != null ? Model.KEY_TONIC[name] : 0;
      return { name, tonic, mode: normalizedMode, tonalName };
    }
    const SEMI_TO_DEGREE = { 0: 1, 2: 2, 4: 3, 5: 4, 7: 5, 9: 6, 11: 7 };
    function semiToDegree(semi, preferFlat) {
      semi = (semi % 12 + 12) % 12;
      if (SEMI_TO_DEGREE[semi] != null) return { degree: SEMI_TO_DEGREE[semi], accidental: "" };
      if (preferFlat) return { degree: SEMI_TO_DEGREE[(semi + 1) % 12], accidental: "flat" };
      return { degree: SEMI_TO_DEGREE[semi - 1], accidental: "sharp" };
    }
    const TYPE_QL = {
      "breve": 8,
      "whole": 4,
      "half": 2,
      "quarter": 1,
      "eighth": 0.5,
      "16th": 0.25,
      "32nd": 0.125,
      "64th": 0.0625
    };
    const SINGLE_TABLE = [
      { ql: 3, dur: 2, dots: 1 },
      // 附点二分(number — ·)
      { ql: 2, dur: 2, dots: 0 },
      // 二分(number —)
      { ql: 1.5, dur: 4, dots: 1 },
      // 附点四分
      { ql: 1, dur: 4, dots: 0 },
      // 四分
      { ql: 0.75, dur: 8, dots: 1 },
      // 附点八分
      { ql: 0.5, dur: 8, dots: 0 },
      // 八分
      { ql: 0.375, dur: 16, dots: 1 },
      // 附点十六
      { ql: 0.25, dur: 16, dots: 0 },
      // 十六
      { ql: 0.1875, dur: 32, dots: 1 },
      // 附点三十二
      { ql: 0.125, dur: 32, dots: 0 }
      // 三十二
    ];
    const BINARY_TABLE = [
      { ql: 2, dur: 2, dots: 0 },
      { ql: 1, dur: 4, dots: 0 },
      { ql: 0.5, dur: 8, dots: 0 },
      { ql: 0.25, dur: 16, dots: 0 },
      { ql: 0.125, dur: 32, dots: 0 }
    ];
    const TOL = 0.02;
    function nearestSingle(ql) {
      let best = SINGLE_TABLE[SINGLE_TABLE.length - 1], bestErr = Infinity;
      for (const t of SINGLE_TABLE) {
        const e = Math.abs(t.ql - ql);
        if (e < bestErr) {
          bestErr = e;
          best = t;
        }
      }
      return { dur: best.dur, dots: best.dots };
    }
    function splitDuration(ql) {
      if (ql <= 0) return [{ dur: 4, dots: 0 }];
      for (const t of SINGLE_TABLE) {
        if (Math.abs(t.ql - ql) < TOL) return [{ dur: t.dur, dots: t.dots }];
      }
      const pieces = [];
      let rem = ql;
      let guard = 0;
      while (rem > TOL && guard++ < 64) {
        let pick = null;
        for (const t of BINARY_TABLE) {
          if (t.ql <= rem + TOL) {
            pick = t;
            break;
          }
        }
        if (!pick) {
          pick = BINARY_TABLE[BINARY_TABLE.length - 1];
        }
        pieces.push({ dur: pick.dur, dots: pick.dots });
        rem -= pick.ql;
      }
      return pieces.length ? pieces : [{ dur: 4, dots: 0 }];
    }
    const REST_TABLE = [
      { ql: 1, dur: 4, dots: 0 },
      { ql: 0.5, dur: 8, dots: 0 },
      { ql: 0.25, dur: 16, dots: 0 },
      { ql: 0.125, dur: 32, dots: 0 }
    ];
    function splitRest(ql) {
      if (ql <= 0) return [{ dur: 4, dots: 0 }];
      const pieces = [];
      let rem = ql, guard = 0;
      while (rem > TOL && guard++ < 128) {
        let pick = null;
        for (const t of REST_TABLE) {
          if (t.ql <= rem + TOL) {
            pick = t;
            break;
          }
        }
        if (!pick) pick = REST_TABLE[REST_TABLE.length - 1];
        pieces.push({ dur: pick.dur, dots: pick.dots });
        rem -= pick.ql;
      }
      return pieces.length ? pieces : [{ dur: 4, dots: 0 }];
    }
    function firstChildText(el, tag) {
      const c = el && el.querySelector(tag);
      return c ? c.textContent.trim() : null;
    }
    function parse(xmlText) {
      const doc = new DOMParser().parseFromString(xmlText, "application/xml");
      if (doc.querySelector("parsererror")) throw new Error("XML \u89E3\u6790\u5931\u8D25,\u6587\u4EF6\u53EF\u80FD\u635F\u574F");
      const out = { title: "", key: "C", mode: "major", time: "4/4", tempo: "", notes: [], slurs: [] };
      const workTitle = doc.querySelector("work-title, movement-title");
      if (workTitle) out.title = workTitle.textContent.trim();
      const parts = Array.from(doc.querySelectorAll("part"));
      let mainPart = null;
      for (const p of parts) {
        if (p.querySelector("measure")) {
          mainPart = p;
          break;
        }
      }
      if (!mainPart) throw new Error("\u672A\u5728\u6587\u4EF6\u4E2D\u627E\u5230\u4E50\u8C31\u58F0\u90E8(part)");
      let fifths = 0;
      const fifthsEl = mainPart.querySelector("key fifths") || doc.querySelector("key fifths");
      if (fifthsEl) fifths = parseInt(fifthsEl.textContent, 10) || 0;
      const modeEl = mainPart.querySelector("key mode") || doc.querySelector("key mode");
      const keyInfo = keyInfoFromFifths(fifths, modeEl ? modeEl.textContent : "major");
      out.key = keyInfo.name;
      out.mode = keyInfo.mode;
      const tonic = keyInfo.tonic;
      const preferFlat = fifths < 0;
      const beats0 = mainPart.querySelector("time beats");
      const beatType0 = mainPart.querySelector("time beat-type");
      if (beats0 && beatType0) out.time = `${beats0.textContent.trim()}/${beatType0.textContent.trim()}`;
      let bpm = null;
      const soundTempo = mainPart.querySelector("sound[tempo]") || doc.querySelector("sound[tempo]");
      if (soundTempo) {
        const t = parseFloat(soundTempo.getAttribute("tempo"));
        if (t > 0) bpm = Math.round(t);
      }
      if (bpm == null) {
        const perMin = mainPart.querySelector("metronome per-minute") || doc.querySelector("metronome per-minute");
        if (perMin) {
          const t = parseInt(perMin.textContent, 10);
          if (t > 0) bpm = t;
        }
      }
      if (bpm != null) out.tempo = `\u2669=${bpm}`;
      const measures = Array.from(mainPart.querySelectorAll("measure"));
      let divisions = 0;
      let curTimeStr = out.time;
      let mainVoice = null;
      let nextBeamGroup = 1;
      let currentBeamGroup = null;
      let melismaStart = null, melismaEnd = null;
      const openSlurs = {};
      let openTieFrom = null;
      function closeMelisma() {
        if (melismaStart != null && melismaEnd != null && melismaEnd > melismaStart) {
          out.slurs.push({ from: melismaStart, to: melismaEnd });
        }
        melismaStart = null;
        melismaEnd = null;
      }
      function emitPitched(degree, oct, accidental, ql, lyric, hasTimeMod, beamGroup) {
        const pieces = hasTimeMod ? [nearestSingle(ql)] : splitDuration(ql);
        const idxs = [];
        pieces.forEach((p, i) => {
          const nt = Model.makeNote(degree, oct);
          nt.accidental = accidental;
          nt.dur = p.dur;
          nt.dots = p.dots;
          if (i === 0 && beamGroup != null) nt.beamGroup = beamGroup;
          if (i === 0 && lyric) nt.lyric = lyric;
          out.notes.push(nt);
          idxs.push(out.notes.length - 1);
        });
        if (idxs.length > 1) out.slurs.push({ from: idxs[0], to: idxs[idxs.length - 1] });
        return { first: idxs[0], last: idxs[idxs.length - 1], count: idxs.length };
      }
      function emitRest(ql, beamGroup) {
        const pieces = splitRest(ql);
        pieces.forEach((p, index) => {
          const r = Model.makeNote(0, 0);
          r.dur = p.dur;
          r.dots = p.dots;
          if (index === 0 && beamGroup != null) r.beamGroup = beamGroup;
          out.notes.push(r);
        });
        return pieces.length;
      }
      function durationQl(el) {
        const durText = firstChildText(el, "duration");
        const durTicks = durText ? parseInt(durText, 10) : NaN;
        if (divisions > 0 && durTicks > 0) return durTicks / divisions;
        const typeEl = el.querySelector("type");
        const durName = typeEl ? typeEl.textContent.trim() : "quarter";
        let ql = TYPE_QL[durName] != null ? TYPE_QL[durName] : 1;
        const dots = el.querySelectorAll("dot").length;
        if (dots === 1) ql *= 1.5;
        else if (dots === 2) ql *= 1.75;
        return ql;
      }
      function beamGroupForEvent(noteEl) {
        const beam = Array.from(noteEl.querySelectorAll("beam")).find((el) => !el.getAttribute("number") || el.getAttribute("number") === "1");
        if (!beam) return null;
        const marker = beam.textContent.trim().toLowerCase();
        if (marker === "begin" || currentBeamGroup == null) currentBeamGroup = nextBeamGroup++;
        const group = currentBeamGroup;
        if (marker === "end") currentBeamGroup = null;
        return group;
      }
      measures.forEach((measure, mi) => {
        currentBeamGroup = null;
        const divText = firstChildText(measure, "attributes divisions");
        if (divText) {
          const d = parseInt(divText, 10);
          if (d > 0) divisions = d;
        }
        const mb = measure.querySelector("time beats");
        const mbt = measure.querySelector("time beat-type");
        if (mb && mbt) {
          const ts = `${mb.textContent.trim()}/${mbt.textContent.trim()}`;
          if (mi === 0) {
            out.time = ts;
            curTimeStr = ts;
          } else if (ts !== curTimeStr) {
            out.notes.push(Model.makeTimeSig(ts));
            curTimeStr = ts;
          }
        }
        const cap = Model.barCapacity(curTimeStr) || 4;
        const musicEvents = Array.from(measure.children).filter((el) => {
          const tag = (el.localName || el.tagName || "").toLowerCase();
          return tag === "note" || tag === "forward" || tag === "backup";
        });
        let addedInThisMeasure = 0;
        for (const ev of musicEvents) {
          const tag = (ev.localName || ev.tagName || "").toLowerCase();
          if (tag === "backup") {
            closeMelisma();
            continue;
          }
          if (tag === "forward") {
            const voice2 = firstChildText(ev, "voice");
            if (mainVoice != null && voice2 && voice2 !== mainVoice) continue;
            closeMelisma();
            addedInThisMeasure += emitRest(durationQl(ev));
            continue;
          }
          const n = ev;
          if (n.querySelector("grace")) continue;
          if (n.querySelector("chord")) continue;
          const voiceEl = n.querySelector("voice");
          const voice = voiceEl ? voiceEl.textContent.trim() : "1";
          if (mainVoice == null) mainVoice = voice;
          if (voice !== mainVoice) continue;
          const restEl = n.querySelector("rest");
          const isRest = !!restEl;
          const beamGroup = beamGroupForEvent(n);
          if (isRest && restEl.getAttribute("measure") === "yes") {
            closeMelisma();
            addedInThisMeasure += emitRest(cap);
            continue;
          }
          const ql = durationQl(n);
          const hasTimeMod = !!n.querySelector("time-modification");
          if (isRest) {
            closeMelisma();
            addedInThisMeasure += emitRest(ql, beamGroup);
            continue;
          }
          const stepEl = n.querySelector("pitch step");
          const octEl = n.querySelector("pitch octave");
          if (!stepEl || !octEl) {
            closeMelisma();
            addedInThisMeasure += emitRest(ql, beamGroup);
            continue;
          }
          const step = stepEl.textContent.trim();
          const octave = parseInt(octEl.textContent, 10);
          const alterEl = n.querySelector("pitch alter");
          const alter = alterEl ? parseInt(alterEl.textContent, 10) : 0;
          const absSemi = STEP_SEMI[step] + alter + (octave + 1) * 12;
          const tonicAbs = tonic + (4 + 1) * 12;
          const diff = absSemi - tonicAbs;
          if (!isFinite(diff)) {
            closeMelisma();
            addedInThisMeasure += emitRest(ql, beamGroup);
            continue;
          }
          const { degree, accidental } = semiToDegree((diff % 12 + 12) % 12, preferFlat);
          let oct = Math.floor(diff / 12);
          oct = Math.max(-2, Math.min(2, oct));
          const lyricEl = n.querySelector("lyric");
          const lyricTextEl = lyricEl ? lyricEl.querySelector("text") : null;
          const syllable = lyricTextEl ? lyricTextEl.textContent.trim() : "";
          const hasExtend = !!(lyricEl && lyricEl.querySelector("extend"));
          const { first, last } = emitPitched(
            degree,
            oct,
            accidental,
            ql,
            syllable,
            hasTimeMod,
            beamGroup
          );
          addedInThisMeasure++;
          if (syllable) {
            closeMelisma();
            if (hasExtend) {
              melismaStart = first;
              melismaEnd = last;
            }
          } else if (melismaStart != null) {
            melismaEnd = last;
          }
          n.querySelectorAll("slur").forEach((sl) => {
            const type = sl.getAttribute("type");
            const num = sl.getAttribute("number") || "1";
            if (type === "start") openSlurs[num] = first;
            else if (type === "stop") {
              const f = openSlurs[num];
              if (f != null && last > f) out.slurs.push({ from: f, to: last });
              delete openSlurs[num];
            }
          });
          const tieEls = [
            ...Array.from(n.querySelectorAll("tie")),
            ...Array.from(n.querySelectorAll("tied"))
          ];
          let tieStart = false, tieStop = false;
          tieEls.forEach((t) => {
            const ty = t.getAttribute("type");
            if (ty === "start") tieStart = true;
            else if (ty === "stop") tieStop = true;
          });
          if (tieStop && openTieFrom != null && first > openTieFrom) {
            out.slurs.push({ from: openTieFrom, to: first });
            openTieFrom = null;
          }
          if (tieStart) openTieFrom = last;
        }
        if (addedInThisMeasure === 0) {
          closeMelisma();
          emitRest(cap);
        }
        if (mi < measures.length - 1) out.notes.push(Model.makeBarline());
      });
      closeMelisma();
      const seen = /* @__PURE__ */ new Set();
      out.slurs = out.slurs.filter((s) => {
        if (s.from == null || s.to == null || s.to <= s.from) return false;
        const k = s.from + "-" + s.to;
        if (seen.has(k)) return false;
        seen.add(k);
        return true;
      });
      if (out.notes.filter((n) => n.type !== "barline" && n.type !== "timesig").length === 0) {
        throw new Error("\u672A\u5728\u6587\u4EF6\u4E2D\u627E\u5230\u97F3\u7B26");
      }
      return out;
    }
    return { parse, keyInfoFromFifths };
  })();

  // assets/studio/track-score/layout.mjs
  var Layout = /* @__PURE__ */ (() => {
    const CFG = {
      PAGE_W: 740,
      // A4 谱面可用总宽(对应 .score 内容宽,随排版收窄字号)
      MARGIN_X: 28,
      // 左右边距(强制相等)
      BASE_Y: 40,
      // 音符数字中心所在的基线 y
      ROW_H: 96,
      // 行高(下一行整体下移多少)
      BARS_PER_ROW: 4,
      // 每行固定小节数 → 也是每行的等分格数
      NOTE_FS: 16,
      // 音符数字字号(←19→16,整体缩小)
      NOTE_W: 17,
      // 一个音符"数字框"的标称宽度(←20)
      CELL_PAD: 8,
      // 小节格内左右内缩
      MIN_NOTE_GAP: 15,
      // 格内相邻音符中心的最小间距(←18)
      FIRST_LAST_DX: 16,
      // 铁律:首/末"单元"离小节线的固定距离(左右相等、恒定不变)
      TIMESIG_W: 20,
      // 小节显示拍号时,左侧为拍号预留的额外宽度
      NEED_PER_NOTE: 14,
      // 每个音符大致需要的"身体宽度"(←17)
      CELL_W_MIN: 44,
      // 单格最小宽度(←52)
      CELL_W_MAX: 240,
      // 单格最大宽度(←260)
      OCT_DOT_R: 1.3,
      // 八度点半径(←1.6)
      OCT_GAP_1: 9,
      // 第一个八度点离数字中心的距离(←11)
      OCT_GAP_N: 5,
      // 后续八度点之间的距离(←6)
      ACC_DX: -9,
      // 升降号相对数字中心的 x 偏移(←-11)
      ACC_DY: -7,
      // 升降号相对数字中心的 y 偏移(←-8)
      DASH_GAP: 5,
      // 增时线之间的水平间距(←7)
      DASH_DX: 28,
      // 第一条增时线离音符中心的偏移(≈NOTE_W*1.65,让增时线居中于音符间的空间中)
      UL_GAP: 3,
      // 减时线之间的垂直间距(保持)
      UL_FIRST_DY: 12,
      // 第一条减时线离基线的垂直距离(←14)
      BEAM_INSET: 3,
      // 连梁端点向内收(保持)
      BEAM_GAP_MIN: 5,
      // 相邻梁段最小空隙(←6)
      DOT_AUG_DX: 10,
      // 附点离数字中心的 x 偏移(←12)
      LYRIC_FS: 11,
      // 歌词字号(←13)
      LYRIC_DY: 28,
      // 歌词中心相对音符基线向下的距离(←34)
      SLUR_DY: -16,
      // 弧线顶点相对音符基线向上的距离(负=在上方)
      SLUR_END_DY: -11,
      // 弧线两端离音符基线的向上距离(端点比顶点低,形成拱形)
      SLUR_PAD_X: 4,
      // 弧线端点相对首/末音符中心向内(外)的水平微调
      SLUR_ROW_EXT: 30,
      // 跨行弧线:前半段延伸到行右、后半段从行左起的水平长度
      // 挂件字符半宽估算(用于防溢出小节线):
      DASH_CHAR_HW: 5,
      // "—" 字宽≈10px → 半宽≈5
      AUG_CHAR_HW: 4,
      // "·" 字宽≈8px  → 半宽≈4
      ACC_CHAR_HW: 6
      // "♯" 字宽≈12px → 半宽≈6(←ACC_FS=12)
    };
    function decorations(note) {
      const decos = [];
      if (note.octave > 0) {
        for (let i = 0; i < note.octave; i++)
          decos.push({ kind: "octdot", dx: 0, dy: -(CFG.OCT_GAP_1 + i * CFG.OCT_GAP_N) });
      } else if (note.octave < 0) {
        for (let i = 0; i < -note.octave; i++)
          decos.push({ kind: "octdot", dx: 0, dy: CFG.OCT_GAP_1 + i * CFG.OCT_GAP_N });
      }
      if (note.accidental === "sharp") decos.push({ kind: "acc", text: "\u266F", dx: CFG.ACC_DX, dy: CFG.ACC_DY });
      if (note.accidental === "flat") decos.push({ kind: "acc", text: "\u266D", dx: CFG.ACC_DX, dy: CFG.ACC_DY });
      if (note.accidental === "natural") decos.push({ kind: "acc", text: "\u266E", dx: CFG.ACC_DX, dy: CFG.ACC_DY });
      if (note.dots >= 1) decos.push({ kind: "augdot", dx: CFG.DOT_AUG_DX, dy: 2 });
      if (note.dots >= 2) decos.push({ kind: "augdot", dx: CFG.DOT_AUG_DX + 6, dy: 2 });
      return decos;
    }
    function fillRests(bar, remBeats, insertAt) {
      if (remBeats <= 1e-6) return;
      const STD = [[1, 4], [0.5, 8], [0.25, 16], [0.125, 32]];
      let rem = remBeats;
      let guard = 0;
      while (rem > 1e-6 && guard++ < 64) {
        const pick = STD.find(([b]) => b <= rem + 1e-6);
        if (!pick) break;
        bar.notes.push({
          note: { type: "rest", degree: 0, octave: 0, accidental: "", dur: pick[1], dots: 0, lyric: "" },
          index: null,
          filler: true,
          // 合成占位休止符:淡色、不可选、用户输入会自动顶掉
          insertAt
          // 点击该 0 时,光标定位到 state.notes 的这个数组位置(在此输入即顶替)
        });
        rem -= pick[0];
      }
    }
    function splitBars(notes, cap0) {
      const bars = [];
      let cap = cap0;
      let pendingTimeSig = null;
      let cur = { notes: [], manualBar: false, rightBar: "normal", leftBar: null, cap, showTimeSig: null };
      let acc = 0;
      let barInsertAt = 0;
      function closeBar(manual, rightSub) {
        if (cur.notes.length === 0 && acc <= 1e-6) {
          const previous = bars[bars.length - 1];
          if (previous) {
            previous.manualBar = previous.manualBar || !!manual;
            if (rightSub && rightSub !== "normal") previous.rightBar = rightSub;
          }
          return false;
        }
        fillRests(cur, cap - acc, barInsertAt);
        cur.manualBar = manual;
        if (rightSub) cur.rightBar = rightSub;
        bars.push(cur);
        cur = { notes: [], manualBar: false, rightBar: "normal", leftBar: null, cap, showTimeSig: null };
        acc = 0;
        return true;
      }
      notes.forEach((note, index) => {
        if (note.type === "timesig") {
          if (cur.notes.length > 0) closeBar(false);
          cap = Model.barCapacity(note.time);
          cur.cap = cap;
          cur.showTimeSig = note.time;
          return;
        }
        if (note.type === "barline") {
          const sub = note.subtype || "normal";
          if (sub === "repeatStart") {
            if (cur.notes.length > 0) closeBar(true, "normal");
            cur.leftBar = "repeatStart";
          } else {
            closeBar(true, sub);
          }
          return;
        }
        const nb = Model.beats(note);
        if (acc > 1e-6 && acc + nb > cap + 1e-6) {
          closeBar(false);
        }
        cur.notes.push({ note, index });
        barInsertAt = index + 1;
        acc += nb;
        if (acc >= cap - 1e-6) closeBar(false);
      });
      if (cur.notes.length > 0) closeBar(false);
      return bars;
    }
    function barUnitCount(bar) {
      let u = 0;
      bar.notes.forEach((bn) => {
        u += 1 + Model.dashes(bn.note.dur);
      });
      return Math.max(1, u);
    }
    function distributeInCell(barNotes, cellLeft, cellRight, leftInset) {
      const n = barNotes.length;
      if (n === 0) return { noteX: [], dashX: [] };
      const units = [];
      barNotes.forEach((bn, k) => {
        units.push({ k, isDash: false });
        const d = Model.dashes(bn.note.dur);
        for (let j = 0; j < d; j++) units.push({ k, isDash: true });
      });
      const U = units.length;
      const innerL = cellLeft + CFG.FIRST_LAST_DX + (leftInset || 0);
      const innerR = cellRight - CFG.FIRST_LAST_DX;
      const centers = [];
      if (U === 1) {
        centers.push((innerL + cellRight - CFG.FIRST_LAST_DX) / 2);
      } else {
        const step = (innerR - innerL) / (U - 1);
        for (let i = 0; i < U; i++) centers.push(innerL + i * step);
      }
      const noteX = new Array(n).fill(0);
      const dashX = barNotes.map(() => []);
      units.forEach((u, i) => {
        if (u.isDash) dashX[u.k].push(centers[i]);
        else noteX[u.k] = centers[i];
      });
      return { noteX, dashX };
    }
    function compute(notes, state) {
      const items = [];
      const cap = Model.barCapacity(state.time);
      const bars = splitBars(notes, cap);
      if (bars.length > 0 && !bars[0].showTimeSig) bars[0].showTimeSig = state.time;
      const usableW = CFG.PAGE_W - CFG.MARGIN_X * 2;
      const FULL = CFG.BARS_PER_ROW;
      function rowCellWidths(rowBars, isFullRow) {
        const need = rowBars.map((b) => {
          const u = barUnitCount(b);
          const minByGap = (u - 1) * CFG.MIN_NOTE_GAP + CFG.FIRST_LAST_DX * 2;
          const raw = Math.max(u * CFG.NEED_PER_NOTE + CFG.CELL_PAD * 2, minByGap);
          return Math.min(CFG.CELL_W_MAX, Math.max(CFG.CELL_W_MIN, raw));
        });
        const sum = need.reduce((a, b) => a + b, 0);
        if (isFullRow) {
          const scale2 = usableW / sum;
          return need.map((w) => w * scale2);
        }
        const avgCell = usableW / FULL;
        const targetSum = avgCell * rowBars.length;
        const scale = targetSum / sum;
        return need.map((w) => w * scale);
      }
      const rowsArr = [];
      for (let i = 0; i < bars.length; i += FULL) {
        rowsArr.push(bars.slice(i, i + FULL));
      }
      const cellGeom = [];
      rowsArr.forEach((rowBars, row) => {
        const isFullRow = rowBars.length === FULL;
        const widths = rowCellWidths(rowBars, isFullRow);
        let x = CFG.MARGIN_X;
        rowBars.forEach((_, col) => {
          const cellLeft = x;
          const cellRight = x + widths[col];
          cellGeom.push({
            row,
            col,
            cellLeft,
            cellRight,
            isRowEnd: col === rowBars.length - 1,
            isFullRow
          });
          x = cellRight;
        });
      });
      const HARD_LEFT = CFG.MARGIN_X;
      const HARD_RIGHT = CFG.PAGE_W - CFG.MARGIN_X;
      const rowMeta = [];
      let rows = 0;
      bars.forEach((bar, barIdx) => {
        const g = cellGeom[barIdx];
        const row = g.row, col = g.col;
        rows = Math.max(rows, row + 1);
        const cellLeft = g.cellLeft;
        const cellRight = g.cellRight;
        const yy = CFG.BASE_Y + row * CFG.ROW_H;
        if (col === 0) rowMeta[row] = {
          y: yy,
          leftX: cellLeft,
          rightX: cellRight,
          leftSub: bar.leftBar || "normal",
          rightSub: "normal",
          barNo: barIdx + 1
        };
        if (g.isRowEnd && rowMeta[row]) {
          rowMeta[row].rightX = cellRight;
          rowMeta[row].rightSub = bar.rightBar || "normal";
        }
        const leftInset = bar.showTimeSig ? CFG.TIMESIG_W : 0;
        const { noteX, dashX } = distributeInCell(bar.notes, cellLeft, cellRight, leftInset);
        if (bar.showTimeSig) {
          items.push({
            type: "timesig",
            index: null,
            x: cellLeft + CFG.FIRST_LAST_DX / 2 + CFG.TIMESIG_W / 2,
            y: yy,
            time: bar.showTimeSig
          });
        }
        const beats = bar.notes.map((bn) => Model.beats(bn.note));
        let accBeat = 0;
        const beatIdxOf = bar.notes.map((bn, k) => {
          const idx = Math.floor(accBeat + 1e-6);
          accBeat += beats[k];
          return idx;
        });
        function canBeam(bn) {
          return !bn.filler && (bn.note.type === "note" || bn.note.type === "rest") && Model.underlines(bn.note.dur) > 0;
        }
        const beamGroupId = new Array(bar.notes.length).fill(-1);
        let gid = 0;
        for (let k = 0; k < bar.notes.length; k++) {
          if (!canBeam(bar.notes[k])) {
            continue;
          }
          const prevK = k - 1;
          const explicit = bar.notes[k].note.beamGroup;
          const previousExplicit = prevK >= 0 ? bar.notes[prevK].note.beamGroup : null;
          const joinsPrevious = prevK >= 0 && canBeam(bar.notes[prevK]) && beamGroupId[prevK] >= 0 && (explicit != null ? previousExplicit != null && String(previousExplicit) === String(explicit) : previousExplicit == null && beatIdxOf[prevK] === beatIdxOf[k]);
          if (joinsPrevious) {
            beamGroupId[k] = beamGroupId[prevK];
          } else {
            beamGroupId[k] = gid++;
          }
        }
        bar.notes.forEach((bn, k) => {
          const note = bn.note;
          const d = Model.dashes(note.dur);
          const dashXs = dashX[k] || [];
          items.push({
            type: note.type,
            index: bn.index,
            x: noteX[k],
            y: yy,
            w: CFG.NOTE_W,
            note,
            filler: !!bn.filler,
            // 自动补拍的占位休止符:淡色、不可选
            insertAt: bn.insertAt,
            // filler 专用:点击它时光标应定位到的 state.notes 位置
            underlines: Model.underlines(note.dur),
            dashes: d,
            dashXs,
            // 增时线的精确 x 坐标数组
            decos: decorations(note),
            lyric: note.lyric || "",
            lyricY: yy + CFG.LYRIC_DY,
            beamId: beamGroupId[k] >= 0 ? row * 1e3 + barIdx * 100 + beamGroupId[k] : null
          });
        });
        const isRowEnd = g.isRowEnd;
        if (!isRowEnd) {
          let sub = bar.rightBar || "normal";
          const nextBar = bars[barIdx + 1];
          if (sub === "normal" && nextBar && nextBar.leftBar === "repeatStart") sub = "repeatStart";
          items.push({
            type: "barline",
            index: null,
            x: cellRight,
            y: yy,
            w: 0,
            manual: bar.manualBar,
            subtype: sub
          });
        }
      });
      rowMeta.forEach((rm) => {
        if (!rm) return;
        if (rm.barNo != null) {
          items.push({ type: "rownum", index: null, x: rm.leftX, y: rm.y, barNo: rm.barNo });
        }
        items.push({
          type: "barline",
          index: null,
          x: rm.leftX,
          y: rm.y,
          w: 0,
          edge: true,
          subtype: rm.leftSub === "repeatStart" ? "repeatStart" : "normal"
        });
        items.push({
          type: "barline",
          index: null,
          x: rm.rightX,
          y: rm.y,
          w: 0,
          edge: true,
          subtype: rm.rightSub || "normal"
        });
      });
      const width = CFG.PAGE_W;
      const height = rows * CFG.ROW_H + 20;
      const beams = [];
      const groups = {};
      items.forEach((it) => {
        if (it.beamId == null) return;
        (groups[it.beamId] = groups[it.beamId] || []).push(it);
      });
      const half = CFG.NOTE_W / 2;
      Object.values(groups).forEach((grp) => {
        grp.sort((a, b) => a.x - b.x);
        const maxUl = Math.max(...grp.map((g) => g.underlines));
        const y0 = grp[0].y;
        const solo = grp.length === 1;
        for (let k = 1; k <= maxUl; k++) {
          let i = 0;
          while (i < grp.length) {
            if (grp[i].underlines < k) {
              i++;
              continue;
            }
            let j = i;
            while (j + 1 < grp.length && grp[j + 1].underlines >= k) j++;
            let x1, x2;
            if (solo) {
              x1 = grp[i].x - half + 3;
              x2 = grp[i].x + half - 3;
            } else {
              x1 = grp[i].x - half + CFG.BEAM_INSET;
              x2 = grp[j].x + half - CFG.BEAM_INSET;
            }
            if (x2 > x1) beams.push({ y: y0 + CFG.UL_FIRST_DY + (k - 1) * CFG.UL_GAP, x1, x2 });
            i = j + 1;
          }
        }
      });
      const byRow = {};
      beams.forEach((b) => {
        (byRow[Math.round(b.y)] = byRow[Math.round(b.y)] || []).push(b);
      });
      Object.values(byRow).forEach((arr) => {
        arr.sort((a, b) => a.x1 - b.x1);
        for (let i = 1; i < arr.length; i++) {
          const minLeft = arr[i - 1].x2 + CFG.BEAM_GAP_MIN;
          if (arr[i].x1 < minLeft) arr[i].x1 = Math.min(minLeft, arr[i].x2 - 1);
        }
      });
      const slurArcs = [];
      const noteItemByIndex = {};
      items.forEach((it) => {
        if (it.type === "barline") return;
        if (it.index == null) return;
        noteItemByIndex[it.index] = it;
      });
      (state.slurs || []).forEach((s) => {
        const a = noteItemByIndex[s.from];
        const b = noteItemByIndex[s.to];
        if (!a || !b) return;
        let lft = a, rgt = b;
        if (a.index > b.index) {
          lft = b;
          rgt = a;
        }
        const sameRow = Math.abs(lft.y - rgt.y) < 1e-6;
        if (sameRow) {
          slurArcs.push(makeArc(lft.x, rgt.x, lft.y, rgt.y, lft, rgt));
        } else {
          const rightEdgeOfLft = CFG.PAGE_W - CFG.MARGIN_X;
          const leftEdgeOfRgt = CFG.MARGIN_X;
          slurArcs.push(makeArc(lft.x, rightEdgeOfLft, lft.y, lft.y, lft, null));
          slurArcs.push(makeArc(leftEdgeOfRgt, rgt.x, rgt.y, rgt.y, null, rgt));
        }
      });
      return { items, beams, slurArcs, width, height, cfg: CFG };
    }
    function makeArc(x0, x1, y0, y1, endL, endR) {
      const span = Math.abs(x1 - x0);
      const topGap = CFG.NOTE_FS / 2 + 4;
      const octLift = (it) => {
        if (!it || !it.note) return 0;
        const o = it.note.octave;
        return o > 0 ? CFG.OCT_GAP_1 + (o - 1) * CFG.OCT_GAP_N + 3 : 0;
      };
      const lift0 = topGap + octLift(endL);
      const lift1 = topGap + octLift(endR);
      const p0y = y0 - lift0;
      const p1y = y1 - lift1;
      const arch = Math.max(8, Math.min(26, span * 0.12 + 8));
      const cx = (x0 + x1) / 2;
      const cy = Math.min(p0y, p1y) - arch;
      return { x0, y0: p0y, cx, cy, x1, y1: p1y };
    }
    return { compute, partitionBars: splitBars, CFG };
  })();

  // assets/studio/track-score/render.mjs
  var Render = /* @__PURE__ */ (() => {
    const FIRST_PAGE_ROWS = 9;
    const OTHER_PAGE_ROWS = 10;
    const BAR_H = 36;
    function centerEl(cls, cx, cy) {
      const d = document.createElement("div");
      d.className = cls;
      d.style.left = cx + "px";
      d.style.top = cy + "px";
      d.style.transform = "translate(-50%, -50%)";
      return d;
    }
    function escapeHtml(s) {
      return String(s).replace(/[&<>"]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" })[c]);
    }
    function buildMeta(state) {
      const meta = document.createElement("div");
      meta.className = "score-meta";
      const credits = [
        state.lyricist ? `\u4F5C\u8BCD:${escapeHtml(state.lyricist)}` : "",
        state.composer ? `\u4F5C\u66F2:${escapeHtml(state.composer)}` : "",
        state.arranger ? `\u5236\u8C31:${escapeHtml(state.arranger)}` : ""
      ].filter(Boolean).map((t) => `<div>${t}</div>`).join("");
      meta.innerHTML = `
      <div class="score-title">${escapeHtml(state.title || "")}</div>
      <div class="score-head">
        <div class="score-head-left">
          <span class="meta-key-time">1=${escapeHtml(Model.formatKeyName(state.key))}&nbsp;&nbsp;${escapeHtml(state.time)}</span>
          ${state.tempo ? `<span class="meta-tempo">${escapeHtml(state.tempo)}</span>` : ""}
          ${state.expression ? `<span class="score-expr">${escapeHtml(state.expression)}</span>` : ""}
        </div>
        <div class="score-head-right">${credits}</div>
      </div>`;
      return meta;
    }
    function draw(container, notes, state) {
      container.innerHTML = "";
      const L = Layout.compute(notes, state);
      const CFG = Layout.CFG;
      const BASE_Y = CFG.BASE_Y, ROW_H = CFG.ROW_H;
      const rowOf = (y) => Math.max(0, Math.round((y - BASE_Y) / ROW_H));
      let maxRow = 0;
      L.items.forEach((it) => {
        if (it.y != null) maxRow = Math.max(maxRow, rowOf(it.y));
      });
      const totalRows = maxRow + 1;
      const pages = [];
      let r = 0;
      while (r < totalRows) {
        const capRows = pages.length === 0 ? FIRST_PAGE_ROWS : OTHER_PAGE_ROWS;
        pages.push({ startRow: r, endRow: Math.min(totalRows, r + capRows) });
        r += capRows;
      }
      if (pages.length === 0) pages.push({ startRow: 0, endRow: 1 });
      const cur = cursorTarget(L, notes, state);
      pages.forEach((pg, pi) => {
        const yOff = pg.startRow * ROW_H;
        const rowsOnPage = pg.endRow - pg.startRow;
        const inPage = (y) => {
          const rr = rowOf(y);
          return rr >= pg.startRow && rr < pg.endRow;
        };
        const page = document.createElement("div");
        page.className = "score" + (pi > 0 ? " score-cont" : "");
        if (pi === 0) page.appendChild(buildMeta(state));
        const canvas = document.createElement("div");
        canvas.className = "canvas";
        canvas.style.width = L.width + "px";
        canvas.style.height = rowsOnPage * ROW_H + 20 + "px";
        L.items.forEach((item) => {
          if (item.y == null || !inPage(item.y)) return;
          drawItem(canvas, shiftItem(item, yOff), state);
        });
        if (L.beams) {
          L.beams.forEach((b) => {
            if (!inPage(b.y)) return;
            const line = document.createElement("div");
            line.className = "el-ul";
            line.style.left = b.x1 + "px";
            line.style.top = b.y - yOff + "px";
            line.style.width = b.x2 - b.x1 + "px";
            canvas.appendChild(line);
          });
        }
        if (L.slurArcs && L.slurArcs.length) {
          const svgNS = "http://www.w3.org/2000/svg";
          const svg = document.createElementNS(svgNS, "svg");
          svg.setAttribute("class", "slur-layer");
          svg.setAttribute("width", L.width);
          svg.setAttribute("height", rowsOnPage * ROW_H + 20);
          let any = false;
          L.slurArcs.forEach((arc) => {
            if (!inPage(arc.y0) && !inPage(arc.y1)) return;
            any = true;
            const path = document.createElementNS(svgNS, "path");
            path.setAttribute(
              "d",
              `M ${arc.x0} ${arc.y0 - yOff} Q ${arc.cx} ${arc.cy - yOff} ${arc.x1} ${arc.y1 - yOff}`
            );
            path.setAttribute("class", "slur-path");
            svg.appendChild(path);
          });
          if (any) canvas.appendChild(svg);
        }
        if (cur && inPage(cur.cy)) {
          const c = document.createElement("div");
          c.className = "el-cursor";
          c.style.left = cur.cx + "px";
          c.style.top = cur.cy - yOff - 16 + "px";
          canvas.appendChild(c);
        }
        page.appendChild(canvas);
        const foot = document.createElement("div");
        foot.className = "score-pageno";
        foot.textContent = pi + 1 + " / " + pages.length;
        page.appendChild(foot);
        container.appendChild(page);
      });
    }
    function shiftItem(item, dy) {
      if (!dy) return item;
      const out = Object.assign({}, item);
      if (out.y != null) out.y -= dy;
      if (out.lyricY != null) out.lyricY -= dy;
      return out;
    }
    function drawItem(canvas, item, state) {
      if (item.type === "barline") {
        drawBarline(canvas, item);
        return;
      }
      if (item.type === "rownum") {
        const rn = document.createElement("div");
        rn.className = "el-rownum";
        rn.textContent = String(item.barNo);
        rn.style.left = item.x - 4 + "px";
        rn.style.top = item.y - Layout.CFG.ROW_H / 2 + "px";
        canvas.appendChild(rn);
        return;
      }
      if (item.type === "timesig") {
        const m = /^(\d+)\s*\/\s*(\d+)$/.exec(item.time || "4/4");
        const numer = m ? m[1] : "4";
        const denom = m ? m[2] : "4";
        const ts = centerEl("el-timesig", item.x, item.y);
        ts.innerHTML = `<span class="ts-num">${numer}</span><span class="ts-den">${denom}</span>`;
        canvas.appendChild(ts);
        return;
      }
      const isSel = !item.filler && state.selected === item.index;
      const num = centerEl("el-num" + (isSel ? " selected" : "") + (item.filler ? " filler" : ""), item.x, item.y);
      if (!item.filler) num.dataset.index = item.index;
      if (item.filler && item.insertAt != null) num.dataset.insertAt = item.insertAt;
      num.style.fontSize = Layout.CFG.NOTE_FS + "px";
      num.style.width = Layout.CFG.NOTE_W + "px";
      num.style.height = Layout.CFG.NOTE_FS + 6 + "px";
      num.textContent = item.type === "rest" ? "0" : String(item.note.degree);
      canvas.appendChild(num);
      item.decos.forEach((dc) => {
        if (dc.kind === "octdot") {
          const dot = centerEl("el-octdot", item.x + dc.dx, item.y + dc.dy);
          const d = Layout.CFG.OCT_DOT_R * 2;
          dot.style.width = d + "px";
          dot.style.height = d + "px";
          canvas.appendChild(dot);
        } else if (dc.kind === "acc") {
          const a = centerEl("el-acc", item.x + dc.dx, item.y + dc.dy);
          a.textContent = dc.text;
          canvas.appendChild(a);
        } else if (dc.kind === "augdot") {
          const a = centerEl("el-augdot", item.x + dc.dx, item.y + dc.dy);
          a.textContent = "\xB7";
          canvas.appendChild(a);
        }
      });
      if (item.underlines > 0 && item.beamId == null) {
        for (let k = 1; k <= item.underlines; k++) {
          const ulY = item.y + Layout.CFG.UL_FIRST_DY + (k - 1) * Layout.CFG.UL_GAP;
          const line = document.createElement("div");
          line.className = "el-ul";
          line.style.left = item.x - Layout.CFG.NOTE_W / 2 + 3 + "px";
          line.style.top = ulY + "px";
          line.style.width = Layout.CFG.NOTE_W - 6 + "px";
          canvas.appendChild(line);
        }
      }
      if (item.dashes > 0 && item.dashXs) {
        for (const dx of item.dashXs) {
          const dash = centerEl("el-dash", dx, item.y);
          dash.textContent = "\u2014";
          canvas.appendChild(dash);
        }
      }
      if (!item.filler) {
        if (state.lyricEdit === item.index) {
          const inp = document.createElement("input");
          inp.className = "el-lyric-input";
          inp.dataset.lyricIndex = item.index;
          inp.value = item.lyric || "";
          inp.style.left = item.x + "px";
          inp.style.top = item.lyricY + "px";
          inp.style.fontSize = Layout.CFG.LYRIC_FS + "px";
          inp.style.height = Layout.CFG.LYRIC_FS + 8 + "px";
          canvas.appendChild(inp);
        } else {
          const ly = centerEl("el-lyric" + (item.lyric ? "" : " empty"), item.x, item.lyricY);
          ly.dataset.lyricIndex = item.index;
          ly.style.fontSize = Layout.CFG.LYRIC_FS + "px";
          ly.style.width = Layout.CFG.LYRIC_FS + 6 + "px";
          ly.style.height = Layout.CFG.LYRIC_FS + 8 + "px";
          ly.textContent = item.lyric || "\u8BCD";
          canvas.appendChild(ly);
        }
      }
    }
    function drawBarline(canvas, item) {
      const sub = item.subtype || "normal";
      const baseCls = item.edge ? "el-bar edge" : "el-bar" + (item.manual ? "" : " auto");
      function stroke(kind, dx) {
        const bar = centerEl(baseCls + (kind === "thick" ? " thick" : ""), item.x + dx, item.y);
        bar.style.height = BAR_H + "px";
        if (item.index != null) bar.dataset.index = item.index;
        canvas.appendChild(bar);
      }
      function dots(dx) {
        [-5, 5].forEach((dy) => {
          const d = centerEl("el-repeat-dot", item.x + dx, item.y + dy);
          canvas.appendChild(d);
        });
      }
      if (sub === "final") {
        stroke("thin", -3);
        stroke("thick", 1);
      } else if (sub === "repeatStart") {
        stroke("thick", -3);
        stroke("thin", 1);
        dots(6);
      } else if (sub === "repeatEnd") {
        dots(-6);
        stroke("thin", -1);
        stroke("thick", 3);
      } else {
        stroke("thin", 0);
      }
    }
    function cursorTarget(L, notes, state) {
      let cx, cy;
      if (state.cursor >= notes.length) {
        const last = [...L.items].reverse().find((it) => it.x != null);
        if (last) {
          cx = last.x + (last.w || 24);
          cy = last.y;
          const rightEdge = Layout.CFG.PAGE_W - Layout.CFG.MARGIN_X;
          if (cx > rightEdge - 4) {
            cx = Layout.CFG.MARGIN_X + Layout.CFG.FIRST_LAST_DX;
            cy = last.y + Layout.CFG.ROW_H;
          }
        }
      } else {
        const target = L.items.find((it) => it.index === state.cursor);
        if (target) {
          cx = target.x - (target.w || 24) / 2 - 4;
          cy = target.y;
        }
      }
      if (cx == null) {
        cx = Layout.CFG.MARGIN_X;
        cy = Layout.CFG.BASE_Y;
      }
      return { cx, cy };
    }
    return { draw };
  })();

  // assets/studio/track-editor.mjs
  var trackEditorMarkup = `
<section id="track-editor" class="track-editor" aria-label="\u5355\u8F68\u7F16\u8F91" hidden>
  <header class="track-editor-header">
    <button id="track-back" type="button">\u2039 \u8FD4\u56DE\u7F16\u6392</button>
    <h2 id="track-editor-name"></h2>
    <button id="track-solo" type="button" aria-pressed="false">\u72EC\u542C</button>
    <div class="track-tools" role="group" aria-label="\u5355\u8F68\u5DE5\u5177">
      <button id="track-score-tab" type="button" aria-pressed="true">\u51FA\u8C31</button>
      <button id="track-vocal-tab" type="button" aria-pressed="false">Vocal \u53D1\u97F3</button>
    </div>
  </header>
  <section id="track-score-pane" class="track-pane">
    <form id="track-score-form" class="track-form">
      <label>\u8C31\u9762 BPM <input name="tempo" type="number" min="30" max="300" step=".01" required></label>
      <button id="track-generate-score" type="button">\u751F\u6210\u65CB\u5F8B\u8C31</button>
      <a id="track-midi" hidden download="\u65CB\u5F8B.mid">MIDI</a>
      <a id="track-xml" hidden download="\u65CB\u5F8B.musicxml">MusicXML</a>
    </form>
    <div id="track-score-preview" hidden>
      <div id="track-score-layout" class="track-tools" role="group" aria-label="\u8C31\u9762\u89C6\u56FE">
        <button id="track-notation-tab" type="button" aria-pressed="true">\u7B80\u8C31</button>
        <button id="track-roll-tab" type="button" aria-pressed="false">\u94A2\u7434\u5377\u5E18</button>
      </div>
      <div id="track-notation" aria-label="\u8BC6\u522B\u7B80\u8C31"></div>
      <div id="track-roll-scroll" hidden><canvas id="track-note-roll" aria-label="\u8BC6\u522B\u97F3\u7B26\u9884\u89C8"></canvas></div>
    </div>
  </section>
  <section id="track-vocal-pane" class="track-pane" hidden>
    <form id="track-vocal-form" class="vocal-fields">
      <fieldset>
        <legend>\u539F\u5531\u4E0E\u76EE\u6807</legend>
        <label>\u539F\u5531\u77ED\u53E5 <input name="line" maxlength="40" required></label>
        <label>\u7B2C\u51E0\u4E2A\u5B57 <input name="character" type="number" min="1" max="40" step="1" value="1" required></label>
        <label>\u65B0\u5B57\u6216\u62FC\u97F3 <input name="reading" maxlength="12" placeholder="\u4F8B\uFF1A\u7834 \u6216 po4" required></label>
        <label>\u539F\u53D1\u97F3\uFF08\u53EF\u9009\uFF09 <input name="actual" maxlength="12" placeholder="\u4F8B\uFF1Akai1"></label>
      </fieldset>
      <fieldset>
        <legend>\u6E90\u97F3\u9891\u65F6\u95F4\uFF08\u79D2\uFF09</legend>
        <label>\u77ED\u53E5\u8D77\u70B9 <input name="lineStart" type="number" step=".001" min="0" required></label>
        <label>\u77ED\u53E5\u7EC8\u70B9 <input name="lineEnd" type="number" step=".001" min="0" required></label>
        <label>\u5B57\u8D77\u70B9 <input name="wordStart" type="number" step=".001" min="0" required></label>
        <label>\u5B57\u7EC8\u70B9 <input name="wordEnd" type="number" step=".001" min="0" required></label>
      </fieldset>
      <fieldset>
        <legend>\u540C\u8F68\u53C2\u8003\u77ED\u53E5</legend>
        <label>\u53C2\u8003\u6B4C\u8BCD <input name="reference" maxlength="40" required></label>
        <label>\u53C2\u8003\u8D77\u70B9 <input name="refStart" type="number" step=".001" min="0" required></label>
        <label>\u53C2\u8003\u7EC8\u70B9 <input name="refEnd" type="number" step=".001" min="0" required></label>
      </fieldset>
      <div class="vocal-commands">
        <button id="track-align" type="button">\u5BF9\u9F50\u8FD9\u53E5</button>
        <button id="track-generate-vocal" type="button">\u751F\u6210\u53D1\u97F3\u5019\u9009</button>
      </div>
      <div id="track-aligned-words" aria-label="\u5B57\u7EA7\u65F6\u95F4" class="vocal-commands"></div>
    </form>
    <div id="track-vocal-result" class="vocal-result" hidden>
      <label>\u539F\u58F0 <audio id="track-vocal-original" controls preload="none"></audio></label>
      <label>\u65B0\u53D1\u97F3 <audio id="track-vocal-candidate" controls preload="none"></audio></label>
      <a id="track-vocal-download" download="\u53D1\u97F3\u5019\u9009.wav">\u4E0B\u8F7D\u5019\u9009 WAV</a>
    </div>
  </section>
  <p id="track-editor-status" role="status"></p>
</section>
<div id="clip-menu" class="clip-menu" role="menu" aria-label="\u97F3\u9891\u6761\u83DC\u5355" hidden>
  <button type="button" role="menuitem" id="clip-open-track">\u8FDB\u5165\u5355\u8F68\u7F16\u8F91</button>
  <button type="button" role="menuitem" id="clip-seek-start">\u5B9A\u4F4D\u5230\u7247\u6BB5\u8D77\u70B9</button>
  <button type="button" role="menuitem" id="clip-score">\u51FA\u8C31</button>
  <button type="button" role="menuitem" id="clip-vocal">Vocal \u53D1\u97F3</button>
</div>`;
  var messageText = {
    busy: "\u672C\u673A\u5DF2\u6709\u5904\u7406\u4EFB\u52A1\uFF0C\u8BF7\u7B49\u5B83\u5B8C\u6210\u540E\u91CD\u8BD5\u3002",
    score_empty: "\u8BE5\u8F68\u6CA1\u6709\u68C0\u6D4B\u5230\u53EF\u51FA\u8C31\u7684\u4E3B\u65CB\u5F8B\u97F3\u7B26\u3002",
    score_unavailable: "\u672C\u673A Audio to MIDI \u672A\u5C31\u7EEA\u3002",
    vocal_unavailable: "\u672C\u673A Vocalis \u672A\u5C31\u7EEA\u3002",
    score_input: "\u8BF7\u68C0\u67E5\u8C31\u9762 BPM \u548C\u5F53\u524D\u97F3\u9891\u9009\u533A\u3002",
    align_input: "\u8BF7\u586B\u5199\u6B63\u786E\u6B4C\u8BCD\u548C\u4E0D\u8D85\u8FC7 10 \u79D2\u7684\u77ED\u53E5\u8303\u56F4\u3002",
    MODEL_PHONEME_CONTRACT: "Vocalis \u7684\u672C\u673A\u97F3\u7D20\u5E93\u4E0D\u652F\u6301\u8FD9\u4E2A\u62FC\u97F3\u6216\u58F0\u8C03\u3002",
    vocal_input: "\u8BF7\u786E\u8BA4\u6B4C\u8BCD\u3001\u6240\u9009\u5B57\u8FB9\u754C\u548C\u540C\u8F68\u53C2\u8003\u65F6\u95F4\u3002\u53C2\u8003\u77ED\u53E5\u987B\u4E0E\u5F85\u6539\u77ED\u53E5\u5206\u5F00\u3002",
    source_changed: "\u8349\u7A3F\u5DF2\u66F4\u65B0\uFF0C\u8BF7\u91CD\u65B0\u6253\u5F00\u8BE5\u5DE5\u7A0B\u540E\u5904\u7406\u3002",
    MODEL_ALIGNMENT_REVIEW_REQUIRED: "Vocalis \u65E0\u6CD5\u53EF\u9760\u5BF9\u9F50\u8FD9\u6BB5\u8BCD\uFF0C\u8BF7\u6838\u5BF9\u539F\u5531\u548C\u53C2\u8003\u6B4C\u8BCD\uFF0C\u5E76\u7F29\u77ED\u8303\u56F4\u3002",
    GENERATION_CONTEXT_LIMIT: "\u539F\u5531\u77ED\u53E5\u987B\u5728 10 \u79D2\u4EE5\u5185\u3002",
    MODEL_BUSY: "Vocalis \u6B63\u5FD9\uFF0C\u8BF7\u7A0D\u540E\u91CD\u8BD5\u3002"
  };
  var isVocal = (track) => track.role === "vocal" || /主唱|和声|人声|vocals?|voice/i.test(track.name);
  var canScore = (track) => !/鼓组|打击|drums?|percussion/i.test(track.name);
  function mountTrackEditor(studio) {
    const $ = studio.$;
    const panel = $("track-editor");
    const menu = $("clip-menu");
    const status = $("track-editor-status");
    const scoreForm = $("track-score-form");
    const vocalForm = $("track-vocal-form");
    let focused, menuTarget, returnFocus, arrangementScroll, job;
    let folded = false;
    const clearAudition = () => {
      for (const id of ["track-vocal-original", "track-vocal-candidate"]) {
        $(id).pause();
        $(id).removeAttribute("src");
        $(id).load();
      }
    };
    function syncRows() {
      studio.$("track-scroll-panel").classList.toggle("single-track", !!focused && !folded);
      for (const node2 of studio.shadowRoot.querySelectorAll("[data-track-row]")) {
        node2.hidden = !!focused && !folded && node2.dataset.trackRow !== focused.id;
      }
    }
    function switchTool(tool) {
      if (!focused) return;
      const vocal = tool === "vocal";
      $("track-score-pane").hidden = vocal;
      $("track-vocal-pane").hidden = !vocal;
      $("track-score-tab").setAttribute("aria-pressed", String(!vocal));
      $("track-vocal-tab").setAttribute("aria-pressed", String(vocal));
      if (!vocal) clearAuditionIfPlaying();
      status.textContent = job ? "\u6B63\u5728\u672C\u673A\u5904\u7406\u2026" : !vocal && !canScore(focused) ? "\u9F13\u7EC4\u4E0E\u6253\u51FB\u4E50\u6682\u4E0D\u652F\u6301\u5355\u65CB\u5F8B\u51FA\u8C31\u3002" : "";
    }
    function clearAuditionIfPlaying() {
      $("track-vocal-original").pause();
      $("track-vocal-candidate").pause();
    }
    function foldForVideo(value) {
      if (!focused || folded === value) return;
      folded = value;
      if (folded) clearAuditionIfPlaying();
      panel.hidden = folded;
      studio.shadowRoot.querySelector(".studio").toggleAttribute("data-track-edit", !folded);
      syncRows();
    }
    function close(restore = false) {
      if (!focused) return;
      focused = null;
      folded = false;
      studio.setSolo(null);
      panel.hidden = true;
      studio.shadowRoot.querySelector(".studio").removeAttribute("data-track-edit");
      clearAudition();
      syncRows();
      if (restore && arrangementScroll !== void 0) studio.$("track-scroll-panel").scrollTop = arrangementScroll;
      if (restore) returnFocus?.focus({ preventScroll: true });
      job?.abort();
      job = null;
    }
    function open(track, part = 0, tool, origin) {
      if (!studio.buffers.has(track.id)) return;
      if (focused !== track) close(false);
      else foldForVideo(false);
      if (!focused) {
        returnFocus = origin;
        arrangementScroll = studio.$("track-scroll-panel").scrollTop;
        focused = track;
        $("track-editor-name").textContent = track.name;
        $("track-solo").setAttribute("aria-pressed", "false");
        $("track-aligned-words").replaceChildren();
        $("track-vocal-tab").hidden = !isVocal(track);
        $("track-score-tab").disabled = !canScore(track);
        scoreForm.reset();
        vocalForm.reset();
        scoreForm.elements.tempo.value = studio.song?.bpm ?? 120;
        const selected = studio.clip(track, part);
        if (selected) {
          vocalForm.elements.lineStart.value = selected.sourceIn.toFixed(3);
          vocalForm.elements.lineEnd.value = Math.min(selected.sourceIn + selected.duration, selected.sourceIn + 8).toFixed(3);
        }
        for (const id of ["track-midi", "track-xml", "track-score-preview", "track-vocal-result"]) $(id).hidden = true;
        panel.hidden = false;
        studio.shadowRoot.querySelector(".studio").setAttribute("data-track-edit", "");
        syncRows();
        studio.$("track-scroll-panel").scrollTop = 0;
      }
      studio.selectClip(track, part);
      $("track-generate-score").disabled = !canScore(track) || !studio.clips(track).length;
      switchTool(isVocal(track) && tool === "vocal" ? "vocal" : "score");
      $("track-back").focus({ preventScroll: true });
    }
    function closeMenu(restore = false) {
      if (!menuTarget) return;
      const target = menuTarget;
      menuTarget = null;
      menu.hidden = true;
      if (restore) target.origin.focus({ preventScroll: true });
    }
    function showMenu(event, track, part, origin) {
      if (!studio.buffers.has(track.id)) return;
      event.preventDefault();
      studio.selectClip(track, part);
      menuTarget = { track, part, origin };
      $("clip-vocal").hidden = !isVocal(track);
      $("clip-seek-start").hidden = !studio.clip(track, part);
      $("clip-score").hidden = !canScore(track);
      menu.hidden = false;
      const anchor = origin.getBoundingClientRect();
      const x = event.type === "keydown" ? anchor.left : event.clientX;
      const y = event.type === "keydown" ? anchor.bottom : event.clientY;
      menu.style.left = Math.max(5, Math.min(x, innerWidth - menu.offsetWidth - 5)) + "px";
      menu.style.top = Math.max(5, Math.min(y, innerHeight - menu.offsetHeight - 5)) + "px";
      $("clip-open-track").focus({ preventScroll: true });
    }
    for (const [id, tool] of [["clip-open-track", void 0], ["clip-score", "score"], ["clip-vocal", "vocal"]]) {
      $(id).onclick = () => {
        const { track, part, origin } = menuTarget;
        closeMenu();
        open(track, part, tool, origin);
      };
    }
    $("clip-seek-start").onclick = () => {
      const { track, part } = menuTarget;
      const clip = studio.clip(track, part);
      closeMenu(true);
      studio.seek(clip.start - clip.silenceHead);
    };
    studio.shadowRoot.addEventListener("pointerdown", (event) => {
      if (!event.composedPath().includes(menu)) closeMenu();
    });
    menu.addEventListener("keydown", (event) => {
      if (!["ArrowUp", "ArrowDown"].includes(event.key)) return;
      event.preventDefault();
      const items = [...menu.querySelectorAll("button:not([hidden])")];
      const i = items.indexOf(studio.shadowRoot.activeElement);
      items[(i + (event.key === "ArrowUp" ? -1 : 1) + items.length) % items.length].focus();
    });
    $("track-back").onclick = () => close(true);
    $("track-solo").onclick = () => {
      const next = studio.soloTrack ? null : focused;
      studio.setSolo(next);
      $("track-solo").setAttribute("aria-pressed", String(!!next));
    };
    $("track-score-tab").onclick = () => switchTool("score");
    $("track-vocal-tab").onclick = () => switchTool("vocal");
    function notationView(showNotation) {
      $("track-notation").hidden = !showNotation;
      $("track-roll-scroll").hidden = showNotation;
      $("track-notation-tab").setAttribute("aria-pressed", String(showNotation));
      $("track-roll-tab").setAttribute("aria-pressed", String(!showNotation));
    }
    $("track-notation-tab").onclick = () => notationView(true);
    $("track-roll-tab").onclick = () => notationView(false);
    function drawScore(result) {
      const preview = $("track-score-preview");
      preview.hidden = false;
      const canvas = $("track-note-roll");
      const width = Math.max(400, Math.ceil(result.duration * 32));
      const height = 180;
      canvas.width = width;
      canvas.height = height;
      const paint = canvas.getContext("2d");
      const pitches = result.notes.map((note) => note[2]);
      const min = Math.min(...pitches) - 1;
      const max = Math.max(...pitches) + 1;
      const row = height / (max - min + 1);
      const beat = 60 / result.tempo;
      paint.strokeStyle = getComputedStyle(canvas).borderTopColor;
      for (let at = 0; at < result.duration; at += beat) {
        const x = at / result.duration * width;
        paint.beginPath();
        paint.moveTo(x, 0);
        paint.lineTo(x, height);
        paint.stroke();
      }
      paint.fillStyle = getComputedStyle(canvas).color;
      for (const [start, end, pitch] of result.notes) {
        paint.fillRect(
          start / result.duration * width,
          (max - pitch) * row,
          Math.max(1, (end - start) / result.duration * width),
          Math.max(1, row - 1)
        );
      }
    }
    async function run(event, kind) {
      event.preventDefault();
      if (!focused || job) return;
      if (!studio.project?.trackProcessing) {
        status.textContent = "\u6B64\u9879\u76EE\u672A\u63A5\u5165\u5355\u8F68\u51FA\u8C31\u6216 Vocalis\u3002";
        return;
      }
      const track = focused;
      const form = kind === "score" ? scoreForm : vocalForm;
      if (kind === "score" && (!canScore(track) || !studio.clips(track).length)) return;
      if (kind !== "align" && !form.reportValidity()) return;
      const request = Object.fromEntries(new FormData(form));
      const controller = new AbortController();
      job = controller;
      status.textContent = {
        score: "Audio to MIDI \u6B63\u5728\u8BC6\u522B\u65CB\u5F8B\u2026",
        vocal: "Vocalis \u6B63\u5728\u751F\u6210\u53D1\u97F3\u5019\u9009\u2026",
        align: "Vocalis \u6B63\u5728\u5BF9\u9F50\u8FD9\u4E00\u53E5\u2026"
      }[kind];
      const buttons = [$("track-generate-score"), $("track-generate-vocal"), $("track-align")];
      buttons.forEach((button3) => {
        button3.disabled = true;
      });
      if (kind === "vocal") {
        clearAuditionIfPlaying();
        studio.pause();
      }
      try {
        if (!await studio.save()) throw Error("source_changed");
        if (job !== controller) return;
        const endpoint = studio.endpoint().replace("/draft?", "/track-process?") + "&track=" + encodeURIComponent(track.id) + "&kind=" + kind;
        const response2 = await studioFetch(endpoint, {
          method: "POST",
          signal: controller.signal,
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ ...request, revision: studio.draft?.revision ?? 0 })
        });
        const result = await response2.json();
        if (job !== controller) return;
        if (!response2.ok) throw Error(result.error);
        if (kind === "score") {
          drawScore(result);
          $("track-notation").replaceChildren();
          notationView(false);
          for (const type of ["midi", "xml"]) {
            $("track-" + type).href = result[type];
            $("track-" + type).hidden = false;
          }
          let scoreReady = false;
          try {
            const file2 = await studioFetch(result.xml, { signal: controller.signal });
            if (!file2.ok) throw Error("score");
            const parsed = XmlImport.parse(await file2.text());
            if (job !== controller) return;
            Render.draw(
              $("track-notation"),
              parsed.notes,
              { ...parsed, title: studio.song.name + " \xB7 " + track.name, selected: -1, cursor: 0, lyricEdit: -1 }
            );
            notationView(true);
            scoreReady = true;
          } catch {
            if (job !== controller) return;
          }
          status.textContent = result.notes.length + " \u4E2A\u97F3\u7B26 \xB7 " + result.tempo + " BPM \xB7 " + result.meter + " \xB7 \u4E3B\u65CB\u5F8B" + (scoreReady ? "" : " \xB7 \u7B80\u8C31\u9884\u89C8\u672A\u80FD\u7ED8\u5236");
        } else if (kind === "align") {
          $("track-aligned-words").replaceChildren(...result.words.map((word, index) => {
            const button3 = document.createElement("button");
            button3.type = "button";
            button3.textContent = word.char;
            button3.title = word.start + "\u2013" + word.end + " \u79D2";
            button3.setAttribute("aria-pressed", "false");
            button3.onclick = () => {
              for (const item of button3.parentElement.children) item.setAttribute("aria-pressed", String(item === button3));
              vocalForm.elements.character.value = index + 1;
              vocalForm.elements.wordStart.value = word.start;
              vocalForm.elements.wordEnd.value = word.end;
            };
            return button3;
          }));
          status.textContent = "\u8BF7\u9009\u62E9\u8981\u6539\u53D1\u97F3\u7684\u5B57\uFF0C\u5E76\u8BD5\u542C\u6838\u5BF9\u8FB9\u754C\u3002";
        } else {
          $("track-vocal-original").src = result.original;
          $("track-vocal-candidate").src = result.candidate;
          $("track-vocal-download").href = result.full;
          $("track-vocal-result").hidden = false;
          status.textContent = result.actual + " \u2192 " + result.target + " \xB7 \u8BF7\u5BF9\u542C\u786E\u8BA4";
        }
      } catch (error) {
        if (job === controller) status.textContent = messageText[error.message] ?? "\u672C\u673A\u5904\u7406\u672A\u5B8C\u6210\uFF0C\u539F\u8F68\u5DF2\u4FDD\u7559\u3002";
      } finally {
        if (job === controller) {
          job = null;
          buttons.forEach((button3) => {
            button3.disabled = false;
          });
        }
      }
    }
    $("track-align").onclick = (event) => void run(event, "align");
    vocalForm.elements.line.oninput = () => $("track-aligned-words").replaceChildren();
    for (const id of ["lineStart", "lineEnd"]) vocalForm.elements[id].oninput = vocalForm.elements.line.oninput;
    for (const [kind, form] of [["score", scoreForm], ["vocal", vocalForm]]) {
      $("track-generate-" + kind).onclick = (event) => void run(event, kind);
      form.addEventListener("keydown", (event) => {
        if (event.key === "Enter" && !event.isComposing && event.target instanceof HTMLInputElement) void run(event, kind);
      });
    }
    $("track-vocal-original").onplay = () => $("track-vocal-candidate").pause();
    $("track-vocal-candidate").onplay = () => $("track-vocal-original").pause();
    return {
      close,
      closeMenu,
      syncRows,
      foldForVideo,
      escape() {
        if (menuTarget) {
          closeMenu(true);
          return true;
        }
        if (focused && !folded) {
          close(true);
          return true;
        }
        return false;
      },
      bind(element, track, part) {
        element.ondblclick = () => open(track, part, void 0, element);
        element.oncontextmenu = (event) => showMenu(event, track, part, element);
        element.addEventListener("keydown", (event) => {
          if (event.key === "ContextMenu" || event.key === "F10" && event.shiftKey) {
            showMenu(event, track, part, element);
          }
        });
      }
    };
  }

  // assets/studio/studio.mjs
  var markup = `
<style>${studio_default}
${studio_clips_default}</style>
<div class="studio">
  <section id="imw-settings" popover="auto" aria-label="\u5DE5\u4F5C\u7AD9\u8BBE\u7F6E">
    <div class="imw-settings-heading"><strong>\u5DE5\u4F5C\u7AD9\u8BBE\u7F6E</strong><button id="imw-settings-close" type="button" aria-label="\u5173\u95ED\u5DE5\u4F5C\u7AD9\u8BBE\u7F6E">\xD7</button></div>
    <label id="audio-project-field" class="field">\u9879\u76EE <select id="project"></select></label>
    <button id="imw-project" class="field" type="button" aria-controls="directorProject">\u9009\u62E9\u89C6\u9891\u9879\u76EE</button>
    <label id="imw-frame-zoom-field" class="field">\u65F6\u95F4\u8F74\u7F29\u653E<select id="imw-frame-zoom" aria-label="\u89C6\u9891\u65F6\u95F4\u8F74\u7F29\u653E"><option value="audio">\u8DDF\u968F\u97F3\u8F68</option><option value="frame">\u9010\u5E27</option></select></label>
    <div class="current-take">
      <strong id="song-title"></strong>
      <select id="version" aria-label="\u66F2\u76EE\u7248\u672C"></select>
    </div>
    <div class="imw-settings-actions">
      <label id="imw-frame-rate-field" class="field">\u6807\u5C3A\u5E27\u7387<select id="imw-frame-rate" aria-label="\u6807\u5C3A\u5E27\u7387"></select></label>
      <button id="imw-inspect" type="button" aria-expanded="false">\u89C6\u9891\u8BBE\u7F6E</button>
      <button id="imw-score-settings" type="button" aria-controls="tracks">\u97F3\u8F68\u8BBE\u7F6E</button>
      <span id="tempo"></span>
      <label class="field zoom" title="\u65F6\u95F4\u8F74\u7F29\u653E"><span aria-hidden="true">\u7F29\u653E</span><select id="zoom" aria-label="\u65F6\u95F4\u8F74\u7F29\u653E"><option value="1">\u9002\u5408</option><option value="2">2\xD7</option><option value="4">4\xD7</option></select></label>
      <button id="output-master" type="button" hidden>\u5206\u6790 Stereo Out</button>
      <a id="download-master" hidden>\u4E0B\u8F7D\u6BCD\u5E26 WAV</a>
      <details id="master-settings" hidden><summary aria-label="Stereo Out \xB7 Output Master">Stereo Out<span class="master-settings-name"> \xB7 Output Master</span></summary>
        <div class="master-popover"><div id="master-delivery-info"></div>
        <label id="master-rate-choice" hidden>\u672C\u6B21\u5DE5\u7A0B\u91C7\u6837\u7387 <select id="master-rate"><option value="">\u9009\u62E9\u91C7\u6837\u7387</option></select></label>
        <button type="button" id="master-export" hidden>\u5BFC\u51FA\u6BCD\u5E26</button><div id="master-audition" hidden>
          <button type="button" id="master-listen">\u8BD5\u542C\u603B\u7EBF</button>
          <button type="button" id="master-bypass" aria-pressed="false">\u65C1\u8DEF</button>
          <audio id="master-aac-player" controls preload="none" aria-label="\u8BD5\u542C Stereo Out" hidden></audio>
        </div>
        <a id="download-aac" hidden>\u4E0B\u8F7D AAC</a><button type="button" id="master-adopt" hidden>\u91C7\u7528\u6B64\u6BCD\u5E26</button>
        <fieldset id="master-values" aria-label="\u6BCD\u5E26\u53C2\u6570"></fieldset>
        <small id="master-engine-note" hidden>\u5F53\u524D\u673A\u5668\u7684 Output Master \u5F15\u64CE\u4E0D\u53EF\u7528\u3002</small><small id="master-saved"></small></div>
      </details>
      <button id="cut-quiet" type="button" aria-label="\u5207\u9664\u4F4E\u97F3\u91CF" title="\u5207\u9664\u6240\u6709\u8F68\u9053\u4E2D\u8FDE\u7EED\u81F3\u5C11 120 \u6BEB\u79D2\u3001\u5CF0\u503C\u4F4E\u4E8E \u221248 dBFS \u7684\u6BB5\u843D">\u5207\u9664\u4F4E\u97F3\u91CF</button>
      <button id="undo-cut" type="button" aria-label="\u64A4\u9500\u5207\u9664" title="\u64A4\u9500\u4E0A\u6B21\u5207\u9664\u4F4E\u97F3\u91CF" hidden>\u64A4\u9500</button>
      <button id="songs-toggle" class="mobile" aria-expanded="false" aria-controls="songs">\u6B4C\u5355</button>
    </div>
  </section>
  <div class="body">
    <div id="imw-audio-fit" class="arrangement" aria-hidden="true" inert><i></i><i class="timeline"></i></div>
    <main class="editor" aria-label="\u97F3\u4E50\u65F6\u95F4\u8F74">
      <div id="imw-screen" role="region" aria-label="\u89C6\u9891\u76D1\u770B"><span id="imw-opening" role="status">\u6B63\u5728\u6253\u5F00\u89C6\u9891\u2026</span><slot name="imw-video"></slot></div>
      <div id="monitor-route" role="status" hidden></div>
      <div id="track-scroll-panel" class="arrangement">
        <div class="track-list">
          <div id="tracks"><div id="imw-video-header"></div><div class="track-heading"><span>\u8F68\u9053</span><span id="ruler-unit"></span></div><div id="imw-lane-labels"></div></div><div id="detached-heads"></div><select id="imw-add-track" aria-label="\u663E\u793A\u5DE5\u7A0B\u5206\u8F68" hidden></select>
        </div>
        <div id="scroll" class="timeline">
          <div id="lane" class="lane">
            <div id="imw-picture-lane">
              <button id="imw-folded-video" type="button" aria-label="\u5C55\u5F00\u89C6\u9891" aria-expanded="false" aria-controls="imw-screen"><span>\u5C55\u5F00\u89C6\u9891</span></button>
              <div id="imw-cut-lanes"><slot name="imw-timeline"></slot></div>
            </div>
            <div id="ruler" class="ruler">
              <div id="ticks" aria-hidden="true"></div>
              <input id="seek" aria-label="\u5B9A\u4F4D\u64AD\u653E\u4F4D\u7F6E" type="range" min="0" max="30" step="0.1" value="0">
            </div>
            <div id="regions"></div>
            <p id="imw-empty-tracks" role="status" tabindex="-1" hidden>\u6B64\u4F5C\u54C1\u8FD8\u6CA1\u6709\u53EF\u7F16\u8F91\u7684\u97F3\u8F68\u3002</p>
            <div id="imw-original-track" class="track-row" role="group" aria-label="\u955C\u5934\u539F\u58F0" hidden></div>
            <div id="detached-lanes"></div>
            <div id="loop-band" hidden></div>
            <div id="playhead" class="playhead"></div>
          </div>
        </div>
        <section id="empty" hidden>
          <p>\u8FD9\u4E2A\u9879\u76EE\u8FD8\u6CA1\u6709\u6B4C\u66F2\u3002</p>
          <button id="library">\u6253\u5F00\u97F3\u9891\u8D44\u4EA7</button>
        </section>
      </div>
      ${trackEditorMarkup}
      <div class="editor-footer">
        <span id="status" role="status">\u6B63\u5728\u8BFB\u53D6\u767B\u8BB0\u9879\u76EE\u2026</span>
        <button id="retry" hidden>\u91CD\u8BD5\u4FDD\u5B58</button>
        <slot name="tools"></slot>
      </div>
    </main>
    <aside id="songs" aria-label="\u6B4C\u66F2\u4E0E\u9009\u533A\u8BE6\u60C5">
      <div class="songs-heading"><h2>\u9879\u76EE\u6B4C\u5355</h2><span id="count"></span><button id="songs-refresh" type="button" aria-label="\u5237\u65B0\u6B4C\u5355" title="\u5237\u65B0\u6B4C\u5355">\u27F3</button><button id="songs-close" class="mobile">\u5173\u95ED</button></div>
      <div id="song-list"></div><p id="playlist-status" role="status" hidden></p>
      <section id="inspector" aria-label="\u66F2\u76EE\u8BE6\u60C5">
        <div class="inspector-switch">
          <button id="show-lyrics" type="button" aria-controls="lyrics" aria-pressed="true">\u6B4C\u8BCD</button>
          <button id="show-clip" type="button" aria-controls="clip-details" aria-pressed="false">\u7247\u6BB5</button>
        </div>
        <section id="lyrics"><button id="imw-captions" type="button">\u6B4C\u8BCD\u4E0E\u5B57\u5E55</button><p id="lyric-text"></p></section>
        <section id="clip-details" hidden>
          <strong id="clip-name"></strong>
          <dl>
            <div><dt>\u65F6\u95F4\u8F74</dt><dd id="clip-timeline"></dd></div>
            <div><dt>\u6E90\u97F3\u9891\u9009\u533A</dt><dd id="clip-source"></dd></div>
            <div id="clip-sample-row" hidden><dt>\u6E90\u91C7\u6837\u70B9\uFF08\u7EC8\u70B9\u4E0D\u542B\uFF09</dt><dd id="clip-samples"></dd></div>
            <div><dt>\u64AD\u653E\u957F\u5EA6</dt><dd id="clip-duration"></dd></div>
            <div><dt>\u97F3\u9891</dt><dd id="clip-format"></dd></div>
          </dl>
        </section>
      </section>
    </aside>
  </div>
</div>`;
  var sameDraft = (a, b) => ["offsets", "trims", "padding", "splits", "cutUndo", "seconds", "zoom", "scroll"].every(
    (key) => JSON.stringify(a[key]) === JSON.stringify(b[key])
  );
  var zoomSteps = [1, 2, 4];
  var roundTimeline = (end) => Math.ceil(end / 5) * 5;
  function sourceFrames(clip, rate, count) {
    const first = Math.max(0, Math.min(count, Math.round(clip.sourceIn * rate)));
    const last = Math.max(first, Math.min(count, Math.round((clip.sourceIn + clip.duration) * rate)));
    return { first, last };
  }
  var detailTime = (seconds) => {
    const micros = Math.round(seconds * 1e6);
    const minutes = Math.floor(micros / 6e7);
    const remainder = micros % 6e7 / 1e6;
    return String(minutes).padStart(2, "0") + ":" + remainder.toFixed(6).padStart(9, "0");
  };
  var clipBounds = (clip) => ({
    start: clip.start - clip.silenceHead,
    end: clip.start + clip.duration + clip.silenceTail
  });
  var format = (seconds) => {
    const tenths = Math.floor(seconds * 10);
    return String(Math.floor(tenths / 600)).padStart(2, "0") + ":" + String(Math.floor(tenths / 10) % 60).padStart(2, "0") + "." + tenths % 10;
  };
  var fixtureSampleRate = 128;
  var makeFixtureSamples = () => Float32Array.from({ length: 40 * fixtureSampleRate }, (_, i) => {
    const t = i / fixtureSampleRate;
    const pulse = Math.exp(-(t * 3.2 % 1) * 3);
    const envelope = 0.18 + 0.45 * pulse * (0.65 + 0.35 * Math.sin(t * 1.58));
    return envelope * (Math.sin(i * 1.72) + 0.16 * Math.sin(i * 0.37));
  });
  async function json(url, options) {
    const response2 = await studioFetch(url, options);
    if (!response2.ok) throw Object.assign(Error("\u672C\u673A\u5DE5\u7A0B\u8BF7\u6C42\u5931\u8D25"), { status: response2.status });
    return response2.json();
  }
  var Studio = class extends HTMLElement {
    connectedCallback() {
      const root = this.attachShadow({ mode: "open" });
      root.innerHTML = markup;
      this.$ = (id) => root.getElementById(id);
      this.frameRuler = mountFrameRuler(this);
      this.length = 30;
      this.fitLength = this.length;
      this.rulerLength = this.length;
      this.seconds = 0;
      this.buffers = /* @__PURE__ */ new Map();
      this.trackColors = /* @__PURE__ */ new Map();
      this.waveIndexes = /* @__PURE__ */ new WeakMap();
      this.expandedTracks = /* @__PURE__ */ new Set();
      this.sources = [];
      this.clipSources = /* @__PURE__ */ new Map();
      this.trackMonitor = new TrackMonitor();
      this.busWindows = [];
      this.loop = { start: 0, end: 8 };
      this.loopEnabled = false;
      this.clickEnabled = false;
      this.level = 0.85;
      this.transport = mountTransport(this);
      this.transport.activate();
      this.trackEditor = mountTrackEditor(this);
      this.disclosure = mountVideoDisclosure(this);
      this.imw = mountVideoView(this);
      this.detachedTracks = mountDetachedTracks(this);
      const settings = this.$("imw-settings");
      const settingsToggle = document.getElementById("imw-settings-toggle");
      if (settingsToggle) settingsToggle.onclick = () => settings.togglePopover();
      settings.addEventListener("toggle", () => {
        settingsToggle?.setAttribute("aria-expanded", String(settings.matches(":popover-open")));
      });
      this.$("imw-settings-close").onclick = () => {
        settings.hidePopover();
        settingsToggle?.focus({ preventScroll: true });
      };
      for (const id of ["imw-project", "imw-inspect", "imw-score-settings", "songs-toggle"]) {
        this.$(id).addEventListener("click", () => settings.hidePopover(), { capture: true });
      }
      const aspect = document.getElementById("imwFrameAspect");
      if (aspect) {
        const applyAspect = (value) => {
          const mode = value === "portrait" ? "portrait" : "landscape";
          aspect.value = mode;
          this.dataset.imwAspect = mode;
          if (this.imw.enabled()) document.body.dataset.imwAspect = mode;
        };
        applyAspect(readPreference("monitor-aspect", "landscape"));
        aspect.onchange = () => {
          applyAspect(aspect.value);
          rememberPreference("monitor-aspect", aspect.value);
        };
      }
      this.transport.sync();
      this.drawer(false);
      this.$("project").onchange = (e) => {
        void this.change(e.target.value, void 0, void 0, true);
        void this.refreshCatalog();
      };
      this.$("version").onchange = (e) => void this.change(this.project.id, this.song.id, e.target.value, true);
      this.$("songs-refresh").onclick = () => void this.refreshCatalog();
      const refreshVisibleArchive = () => {
        if (this.project?.completionReplay && !document.hidden && !this.closest("#wbMusic").hidden)
          void this.refreshCatalog();
      };
      this.archiveListeners = new AbortController();
      this.workAudio = detachedPlayback(this, this.archiveListeners.signal);
      window.addEventListener("focus", refreshVisibleArchive, { signal: this.archiveListeners.signal });
      this.archiveTimer = window.setInterval(refreshVisibleArchive, 4e3);
      this.$("songs-toggle").onclick = () => this.drawer(!this.$("songs").classList.contains("open"));
      this.$("songs-close").onclick = () => this.drawer(false, true);
      root.addEventListener("keydown", (e) => {
        if (e.key === "Escape" && !this.trackEditor.escape()) this.drawer(false, true);
      });
      this.$("library").onclick = () => document.querySelector("#wbMusic [data-wb-route=audio]").click();
      this.$("seek").oninput = (e) => this.imw.enabled() ? globalThis.OAIMWVideo?.seek(Number(e.target.value)) : this.seek(Number(e.target.value), false);
      this.$("seek").onchange = () => {
        if (!this.imw.enabled()) this.changed();
      };
      this.$("ruler").onclick = (e) => {
        const bounds = e.currentTarget.getBoundingClientRect();
        const fraction = (e.clientX - bounds.left) / bounds.width;
        if (this.imw.enabled()) globalThis.OAIMWVideo?.seek(fraction * this.imw.displayLength());
        else this.seek(fraction * this.rulerLength);
      };
      this.$("zoom").onchange = (e) => this.setZoom(Number(e.target.value), this.$("scroll").clientWidth / 2);
      let wheelMotion = 0;
      let lastWheel = -Infinity;
      this.$("scroll").addEventListener("wheel", (event) => {
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
      document.addEventListener("keydown", (event) => {
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
        const saved = readPreference("recent-project", "");
        const project = this.projects.find((item) => item.id === saved) ?? this.projects[0];
        if (project) await this.change(project.id, readPreference("song-" + project.id, ""));
        else {
          this.$("empty").hidden = false;
          this.$("inspector").hidden = true;
          this.status("\u8BF7\u5148\u5173\u8054\u6709\u5206\u8F68\u7684\u9879\u76EE\u3002");
        }
      } catch {
        this.status("\u65E0\u6CD5\u8BFB\u53D6\u5DF2\u767B\u8BB0\u9879\u76EE\u3002\u8BF7\u70B9\u5237\u65B0\u6B4C\u5355\u91CD\u8BD5\u3002");
      }
    }
    projectOptions() {
      this.$("project").replaceChildren(...this.projects.map((project) => new Option(project.name, project.id)));
      this.imw?.syncProject();
    }
    async imwProjectSelection(projectId) {
      if (!projectId) return null;
      if (this.project?.id === projectId && this.song?.id && this.version?.id)
        return { project: projectId, song: this.song.id, version: this.version.id };
      const projects = this.projects ?? await json("/catalog");
      const project = projects.find((item) => item.id === projectId);
      if (!project) return null;
      const remembered = readPreference("song-" + projectId, "");
      const songs2 = project.songs || [];
      const preferred = songs2.find((song) => song.id === remembered);
      for (const song of preferred ? [preferred, ...songs2.filter((item) => item !== preferred)] : songs2) {
        const saved = readPreference("version-" + projectId + "/" + song.id, "");
        const version = song.versions?.find((item) => item.id === saved) ?? song.versions?.find((item) => item.id === song.adopted);
        if (version) return { project: projectId, song: song.id, version: version.id };
      }
      return null;
    }
    hasHomeTarget({ project, song, version }) {
      return this.projects.find((item) => item.id === project)?.songs.find((item) => item.id === song)?.versions.some((item) => item.id === version);
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
          this.status("\u8BE5\u6B4C\u66F2\u6216\u7248\u672C\u6682\u4E0D\u53EF\u7528\uFF0C\u8BF7\u8FD4\u56DE\u6B4C\u66F2\u5217\u8868\u5237\u65B0\u3002");
          return;
        }
        if (this.project?.id !== target.project || this.song?.id !== target.song || this.version?.id !== target.version) {
          await this.change(target.project, target.song, target.version);
        }
        this.showHomeFeature();
      } catch {
        if (!this.homeTarget || this.homeTarget === target) this.status("\u6682\u65F6\u65E0\u6CD5\u5207\u6362\u5230\u9009\u4E2D\u7684\u6B4C\u66F2\u3002");
      }
    }
    showHomeFeature() {
      const feature = this.homeFeature;
      if (!feature || this.closest("#wbMusic").hidden || !this.version) return;
      const { selection: selection2, key } = feature;
      if (selection2 && (this.project.id !== selection2.project || this.song.id !== selection2.song || this.version.id !== selection2.version)) return;
      const details = this.$("master-settings");
      const control = key === "master" ? !details.hidden && details.querySelector("summary") : this.shadowRoot.querySelector("[data-track-monitor=solo]:not(:disabled)");
      if (!control) return;
      this.homeFeature = null;
      if (key === "master") {
        this.$("imw-settings").showPopover();
        details.open = true;
      }
      control.focus();
    }
    drawer(open, restore = false) {
      const panel = this.$("songs");
      const wasOpen = panel.classList.toggle("open", open);
      const button3 = this.$("songs-toggle");
      const previous = button3.getAttribute("aria-expanded") === "true";
      button3.setAttribute("aria-expanded", String(open));
      this.dispatchEvent(new CustomEvent("studio-drawer", { detail: open }));
      if (wasOpen && !previous) {
        this.$("songs-close").focus();
        if (this.project) void this.refreshCatalog();
      }
      if (!open && previous && restore) button3.focus();
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
      this.load?.abort();
      this.trackEditor.closeMenu();
      this.trackEditor.close();
      const load = new AbortController();
      this.load = load;
      this.project = this.projects.find((item) => item.id === projectId);
      this.song = this.project.songs.find((item) => item.id === (songId || readPreference("song-" + projectId, ""))) ?? this.project.songs[0];
      const targetTake = versionId || readPreference("version-" + projectId + "/" + this.song?.id, "");
      this.version = this.song?.versions.find((item) => item.id === targetTake) ?? this.song?.versions.find((item) => item.id === this.song.adopted);
      this.detachedTracks.selectionChanged();
      this.soloTrack = null;
      this.trackMonitor.select(this.project, this.song, this.version);
      this.monitorGains?.clearLanes();
      this.volume(this.level);
      this.toggleAttribute("data-paint-only", this.version?.paintOnly === true);
      this.buffers = /* @__PURE__ */ new Map();
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
      this.fitLength = roundTimeline(Math.max(10, ...(this.version?.tracks ?? []).map((track) => track.start + track.duration)));
      this.length = this.fitLength;
      this.rulerLength = this.length;
      this.$("scroll").scrollLeft = 0;
      this.$("retry").hidden = true;
      this.selectors();
      this.tracks();
      this.syncTrackMonitorControls?.();
      rememberPreference("recent-project", projectId);
      if (this.song) rememberPreference("song-" + projectId, this.song.id);
      if (this.version && versionId) rememberPreference("version-" + projectId + "/" + this.song.id, this.version.id);
      this.switching = false;
      this.imw.syncProject();
      if (userSelected) this.imw.selectionChanged();
      if (this.homeTarget) {
        const pending2 = this.homeTarget;
        queueMicrotask(() => {
          if (this.homeTarget === pending2) void this.openHomeTarget(pending2);
        });
      }
      if (!this.version) {
        this.status(this.project.state ? "\u672C\u9879\u76EE\u7684\u5206\u8F68\u6E05\u5355\u4E0D\u53EF\u8BFB\u3002" : "");
        return;
      }
      if (this.version.pending) {
        this.status("\u8FD9\u7248\u5DF2\u5B8C\u6210\uFF0C\u97F3\u9891\u5F85\u5F52\u6863");
        return;
      }
      if (this.version.paintOnly) {
        this.status(this.version.tracks.length + " \u8F68\u7ED8\u5236\u6837\u4EF6");
        return;
      }
      this.status("\u6B63\u5728\u8BFB\u53D6\u6240\u9009\u7248\u672C\u7684\u97F3\u8F68\u2026");
      const { signal } = load;
      const version = this.version;
      const endpoint = this.endpoint();
      const stored = json(endpoint, { signal }).catch(() => null);
      const decodeTrack = async (track) => {
        const response2 = await studioFetch(track.url, { signal });
        if (!response2.ok) throw Error("\u97F3\u8F68\u4E0D\u53EF\u7528");
        this.decoder ??= new OfflineAudioContext(1, 1, Number(this.dataset.decodeRate));
        const buffer = await this.decoder.decodeAudioData(await response2.arrayBuffer());
        if (track.sourceIn + track.duration > buffer.duration + 0.01) throw Error("\u97F3\u8F68\u957F\u5EA6\u4E0D\u5339\u914D");
        return [track.id, buffer];
      };
      const decodeTracks = async () => {
        const results = [];
        const batch = version.localImport ? 2 : version.tracks.length;
        for (let start = 0; start < version.tracks.length && !signal.aborted; start += batch) {
          results.push(...await Promise.allSettled(version.tracks.slice(start, start + batch).map(decodeTrack)));
        }
        return results;
      };
      const disk = await stored;
      if (signal.aborted) return;
      const pending = readPreference(endpoint, null);
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
        rememberPreference(endpoint, null);
      }
      syncMasterControls(this);
      this.seconds = disk ? this.draft.seconds : 0;
      this.tracks();
      this.$("scroll").scrollLeft = this.draft?.scroll ?? 0;
      const media = version.mastered ? [] : await decodeTracks();
      if (signal.aborted) return;
      this.buffers = new Map(media.filter((item) => item.status === "fulfilled").map((item) => item.value));
      this.audioReady = !version.mastered && this.buffers.size > 0;
      this.loadingTracks = false;
      this.tracks();
      if (this.imw.enabled()) globalThis.OAIMWVideo?.refreshMix?.();
      this.showHomeFeature();
      this.transport.sync();
      this.status(!disk ? "\u8349\u7A3F\u8BFB\u53D6\u5931\u8D25\u3002\u53EF\u8BD5\u542C\uFF0C\u7F16\u8F91\u9700\u91CD\u65B0\u6253\u5F00\u5DE5\u7A0B\u3002" : this.recoveryConflict ? "\u78C1\u76D8\u8349\u7A3F\u5DF2\u66F4\u65B0\u3002\u5F85\u6062\u590D\u7F16\u8F91\u4FDD\u7559\u5728\u672C\u673A\uFF0C\u5F53\u524D\u7248\u672C\u6682\u4E3A\u53EA\u8BFB\u3002" : !version.mastered && this.buffers.size < version.tracks.length ? "\u6709\u97F3\u8F68\u7F3A\u5931\uFF0C\u8BD5\u542C\u4EC5\u4F7F\u7528\u53EF\u7528\u97F3\u8F68\u3002" : this.dirty ? "\u5DF2\u6062\u590D\u672A\u4FDD\u5B58\u7684\u8349\u7A3F\u3002" : version.localImport ? "\u5DF2\u8F7D\u5165 " + version.tracks.length + " \u6761\u672C\u673A\u5206\u8F68" : version.mastered ? "Output Master \xB7 \u7ACB\u4F53\u58F0\u6BCD\u5E26" : version.archive ? "\u672C\u673A\u5F52\u6863 \xB7 " + version.source : "\u672C\u673A\u5408\u6210\u6837\u4EF6");
      if (this.dirty) void this.save();
      return load;
    }
    endpoint() {
      return "/draft?" + new URLSearchParams({
        project: this.project.id,
        song: this.song.id,
        version: this.version.id
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
      this.$("tempo").textContent = bpm > 0 ? bpm + " BPM" + (meter ? "  \xB7  " + meter.beats + "/" + meter.note : "") : this.song ? "\u901F\u5EA6\u672A\u6807\u6CE8" : "";
      this.$("show-clip").disabled = true;
      this.showInspector("lyrics");
      this.renderSongCards();
    }
    versionOptions() {
      const versions = this.$("version");
      versions.replaceChildren(...(this.song?.versions ?? []).map((item) => new Option(this.takeLabel(this.song, item), item.id)));
      versions.disabled = !this.song;
      versions.value = this.version?.id ?? "";
    }
    takeLabel(song, version) {
      if (!song.archive && !song.hasMasters) return version.name;
      if (version.pending) return version.name + " \xB7 \u5F85\u5F52\u6863";
      if (song.explicit === version.id) return version.name + " \xB7 \u5DF2\u91C7\u7528";
      return version.name + (song.adopted === version.id ? " \xB7 \u9ED8\u8BA4" : "");
    }
    async refreshCatalog() {
      if (this.catalogRefresh) return this.catalogRefresh;
      this.catalogRefresh = this.loadCatalog();
      try {
        await this.catalogRefresh;
      } finally {
        this.catalogRefresh = null;
      }
    }
    async loadCatalog() {
      try {
        const projects = await json("/catalog");
        const project = projects.find((item) => item.id === this.project?.id);
        if (!project) return;
        const song = project.songs.find((item) => item.id === this.song?.id);
        const different = JSON.stringify(project.songs) !== JSON.stringify(this.project.songs);
        this.projects = projects;
        this.project = project;
        this.song = song;
        this.$("playlist-status").hidden = true;
        if (different && !this.switching) {
          const version = song?.versions.find((item) => item.id === this.version?.id);
          if (this.version?.pending && version && !version.pending) {
            await this.change(project.id, song.id, version.id);
          } else {
            this.versionOptions();
            this.renderSongCards();
          }
        }
      } catch {
        const status = this.$("playlist-status");
        status.textContent = "\u6682\u65F6\u65E0\u6CD5\u5237\u65B0\u6B4C\u5355";
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
      this.$("count").textContent = this.project.songs.length + " \u9996";
      list.replaceChildren(...this.project.songs.map((song) => this.songCard(song)));
      if (focusSong && focusControl) {
        const card = [...list.children].find((item) => item.dataset.song === focusSong);
        card?.querySelector('[data-card-control="' + focusControl + '"]')?.focus({ preventScroll: true });
      }
      this.syncSongAudition();
    }
    songCard(song) {
      const project = this.project.id;
      const current = song.id === this.song?.id;
      const remembered = readPreference("version-" + project + "/" + song.id, "");
      const version = song.versions.find((item) => item.id === (current ? this.version?.id : remembered)) ?? song.versions.find((item) => item.id === song.adopted);
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
      cover.dataset.label = song.name + " \xB7 " + version.name;
      if (version.cover) {
        const art = new Image();
        art.alt = "";
        art.draggable = false;
        art.onerror = () => art.remove();
        cover.append(art);
        const signal = this.coverController.signal;
        void studioCover(version.cover, signal).then((url) => {
          if (!url) return;
          if (signal.aborted || !card.isConnected) URL.revokeObjectURL(url);
          else {
            signal.addEventListener("abort", () => URL.revokeObjectURL(url), { once: true });
            art.src = url;
          }
        }).catch(() => {
        });
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
      const source = version.source || (version.localImport ? "\u672C\u5730\u5BFC\u5165" : "\u672C\u673A\u6837\u4EF6");
      select.append(Object.assign(document.createElement("span"), {
        className: "song-source",
        textContent: source + (song.simulated ? " \xB7 \u6A21\u62DF" : "")
      }));
      const adopted = song.versions.find((item) => item.id === song.adopted);
      const label = song.archive || song.hasMasters ? this.takeLabel(song, version) + (version.pending ? "" : adopted.id === version.id ? " \xB7 \u53EF\u8BD5\u542C" : " \xB7 \u53EF\u8BD5\u542C \xB7 " + (song.explicit ? "\u5DF2\u91C7\u7528 " : "\u9ED8\u8BA4 ") + adopted.name) : version.paintOnly ? "\u7ED8\u5236\u6837\u4EF6" : version.name;
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
        adopt.textContent = "\u91C7\u7528 " + version.name;
        adopt.onclick = async () => {
          await this.adoptVersion(project, song.id, version.id);
          if (!adopt.isConnected && this.project.id === project && this.song?.id === song.id && !this.shadowRoot.activeElement) this.$("version").focus();
        };
        card.append(adopt);
      }
      return card;
    }
    syncSongAudition() {
      for (const card of this.$("song-list").children) {
        const button3 = card.querySelector(".song-cover");
        const current = card.dataset.song === this.song?.id && card.dataset.version === this.version?.id;
        const playing = current && this.playing;
        const warm = current && this.startup;
        const state = button3.disabled ? "\u97F3\u9891\u4E0D\u53EF\u7528" : playing ? "\u6682\u505C\u8BD5\u542C" : warm ? "\u6B63\u5728\u51C6\u5907\u8BD5\u542C" : "\u8BD5\u542C";
        const label = state + " " + button3.dataset.label;
        if (button3.title === label) continue;
        button3.title = label;
        button3.setAttribute("aria-label", label);
        button3.setAttribute("aria-pressed", String(Boolean(playing)));
        button3.lastElementChild.textContent = button3.disabled ? "\xB7" : playing ? "\u2161" : warm ? "\u2026" : "\u25B6";
      }
    }
    async adoptVersion(project, song, version) {
      if (this.adopting) return false;
      this.adopting = true;
      try {
        await json("/master-adopt", { method: "POST", body: JSON.stringify({ project, song, version }) });
        await this.refreshCatalog();
        syncMasterControls(this);
        return true;
      } catch {
        this.status("\u91C7\u7528\u5931\u8D25\uFF0C\u8349\u7A3F\u4E0E\u5F53\u524D\u7248\u672C\u5DF2\u4FDD\u7559");
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
      label.setAttribute("aria-label", "\u67E5\u770B\u8F68\u9053 " + name);
      label.append(Object.assign(document.createElement("span"), { className: "track-label", textContent: name }));
      if (missing) {
        label.classList.add("offline");
        label.append(Object.assign(document.createElement("span"), { className: "track-offline", textContent: missing }));
      }
      const arrow = document.createElement("span");
      arrow.className = "track-chevron";
      arrow.setAttribute("aria-hidden", "true");
      label.append(arrow);
      head.append(label);
      const result = { head, label, row };
      if (monitor) {
        const controls = document.createElement("div");
        controls.className = "track-monitor-controls";
        controls.setAttribute("role", "group");
        controls.setAttribute("aria-label", name + "\u76D1\u542C");
        for (const [action, symbol, description] of [["solo", "S", "\u72EC\u594F"], ["mute", "M", "\u9759\u97F3"]]) {
          const key = document.createElement("button");
          key.type = "button";
          key.dataset.trackMonitor = action;
          key.textContent = symbol;
          key.title = name + " \xB7 " + description;
          key.setAttribute("aria-label", key.title);
          key.disabled = !available;
          key.onclick = () => monitor(action);
          controls.append(key);
          result[action] = key;
        }
        result.status = document.createElement("span");
        result.status.className = "track-monitor-status";
        result.status.setAttribute("aria-hidden", "true");
        controls.append(result.status);
        head.append(controls);
      }
      const actions = document.createElement("div");
      actions.className = "track-actions";
      actions.id = "track-actions-" + id;
      actions.setAttribute("aria-label", name + "\u5FEB\u6377\u529F\u80FD");
      actions.setAttribute("role", "group");
      label.setAttribute("aria-controls", actions.id);
      for (const [text, run, disabled] of shortcuts) {
        const control = document.createElement("button");
        control.type = "button";
        control.textContent = text;
        control.disabled = !!disabled;
        control.onclick = run;
        actions.append(control);
      }
      const setExpanded = (value) => {
        head.toggleAttribute("data-expanded", value);
        row.toggleAttribute("data-expanded", value);
        actions.hidden = !value;
        label.setAttribute("aria-expanded", String(value));
      };
      setExpanded(expanded);
      label.onclick = (event) => {
        if (event.detail < 2) {
          const value = !head.hasAttribute("data-expanded");
          setExpanded(value);
          expand(value);
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
      this.groups = /* @__PURE__ */ new Map();
      this.trackHeads = /* @__PURE__ */ new Map();
      this.trackMonitorControls = /* @__PURE__ */ new Map();
      const tracks = this.version?.tracks ?? [];
      const colors = this.colorsFor(tracks);
      for (const track of tracks) {
        const tone = trackColor(colors.get(track.id));
        const available = this.buffers.has(track.id);
        const offline = !!this.draft && !available && !this.version.mastered;
        const row = document.createElement("div");
        row.className = "track-row";
        row.dataset.trackRow = track.id;
        const noClip = !available && !this.version.paintOnly || !this.clips(track).length;
        const controls = this.makeTrackHead({
          id: track.id,
          name: track.name,
          row,
          available,
          missing: offline ? this.loadingTracks ? "\u8F7D\u5165\u4E2D" : "\u7F3A\u8F68" : "",
          monitor: !this.version.mastered && !this.version.pending ? (action) => {
            if (action === "solo") this.toggleTrackSolo(track.id);
            else this.toggleTrackMute(track.id);
          } : null,
          shortcuts: [
            ["\u5B9A\u4F4D\u8D77\u70B9", () => {
              const first = this.clips(track)[0];
              if (first) this.seek(clipBounds(first).start);
            }, noClip],
            ["\u5FAA\u73AF\u7247\u6BB5", () => {
              this.selectClip(track);
              this.loopSelection();
            }, noClip]
          ],
          expanded: this.expandedTracks.has(track.id),
          expand: (value) => {
            if (value) this.expandedTracks.add(track.id);
            else this.expandedTracks.delete(track.id);
          },
          select: () => this.selectClip(track)
        });
        const { head, label } = controls;
        head.dataset.trackRow = track.id;
        this.trackHeads.set(track.id, label);
        if (controls.solo) this.trackMonitorControls.set(track.id, controls);
        this.trackEditor.bind(label, track, 0);
        tracksNode.append(head);
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
    paintTrackMonitor({ head, row, label, solo, mute, status }, state) {
      const suppressed = !state.audible;
      const inherited = suppressed && !state.mute;
      head.toggleAttribute("data-monitor-muted", suppressed);
      row.toggleAttribute("data-monitor-muted", suppressed);
      head.toggleAttribute("data-monitor-inherited", inherited);
      solo.setAttribute("aria-pressed", String(state.solo));
      mute.setAttribute("aria-pressed", String(state.mute));
      const reason = state.mute ? "\u5DF2\u624B\u52A8\u9759\u97F3" : inherited ? this.soloTrack ? "\u56E0\u7F16\u8F91\u5668\u72EC\u542C\u800C\u6682\u65F6\u9759\u97F3" : "\u56E0\u5176\u4ED6\u8F68\u9053\u72EC\u594F\u800C\u6682\u65F6\u9759\u97F3" : state.editorSolo ? "\u7F16\u8F91\u5668\u72EC\u542C" : state.solo ? "\u5DF2\u72EC\u594F" : "";
      status.textContent = suppressed ? "\u9759\u97F3" : state.editorSolo ? "\u72EC\u542C" : "";
      status.title = reason;
      for (const node2 of [label, solo, mute]) {
        if (reason) node2.setAttribute("aria-description", reason);
        else node2.removeAttribute("aria-description");
      }
      mute.title = mute.getAttribute("aria-label") + (inherited ? "\uFF08" + reason + "\uFF09" : "");
    }
    syncTrackMonitorControls() {
      for (const [id, controls] of this.trackMonitorControls ?? [])
        this.paintTrackMonitor(controls, this.trackMonitorState(id));
      const route = this.monitorRoute();
      const filtered = !!this.masterAnalysis && route === "filtered";
      const status = this.$("monitor-route");
      status.hidden = !this.masterAnalysis;
      const text = !this.masterAnalysis ? "" : filtered ? "\u539F\u5206\u8F68\u76D1\u542C \xB7 \u72EC\u594F / \u9759\u97F3" : route === "bypass" ? "\u603B\u7EBF\u76D1\u542C \xB7 Stereo Out \u65C1\u8DEF" : "\u603B\u7EBF\u76D1\u542C \xB7 Output Master \u6E7F\u58F0";
      if (status.textContent !== text) status.textContent = text;
      this.$("master-listen").textContent = filtered ? "\u8BD5\u542C\u539F\u5206\u8F68" : "\u8BD5\u542C\u603B\u7EBF";
      const bypass = this.$("master-bypass");
      bypass.textContent = filtered ? "\u8FD4\u56DE\u603B\u7EBF\u540E\u65C1\u8DEF" : "\u65C1\u8DEF";
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
      const label = track.name + "\u7247\u6BB5" + (this.draft?.splits?.[track.id] ? " " + (part + 1) : "");
      region.setAttribute("aria-label", label + (offline ? "\uFF0C\u97F3\u9891\u4E0D\u53EF\u7528" : ""));
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
        handle.setAttribute("aria-label", (edge === "head" ? "\u88C1\u526A\u8D77\u70B9" : "\u88C1\u526A\u7EC8\u70B9") + " \xB7 " + (this.draft?.splits?.[track.id] ? label : track.name));
        handle.disabled = region.disabled;
        this.bindClipControl(handle, group, track, part, edge);
        group.append(handle);
      }
      return group;
    }
    colorsFor(tracks) {
      if (!this.song) return /* @__PURE__ */ new Map();
      const key = "track-colors/" + JSON.stringify([this.project.id, this.song.id]);
      const saved = readPreference(key, null) ?? this.trackColors.get(key);
      const slots = trackColorSlots(tracks, saved);
      const entries = [...slots];
      this.trackColors.set(key, entries);
      if (JSON.stringify(entries) !== JSON.stringify(saved)) rememberPreference(key, entries);
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
        silenceTail
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
        if (seconds) part.setAttribute("aria-label", (edge === "head" ? "\u524D\u7F6E" : "\u540E\u7F6E") + "\u9759\u97F3 " + seconds + " \u79D2");
      }
    }
    sizeLane(length) {
      this.rulerLength = length;
      this.detachedTracks?.layout();
      if (this.imw?.enabled()) return this.imw.fit();
      this.setLaneExtent(length);
    }
    setLaneExtent(length) {
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
    bindClipControl(control, group, track, part, action) {
      const constraints = () => {
        const parts = this.draft.splits[track.id];
        const before = parts?.[part - 1], after = parts?.[part + 1];
        const buffer = this.buffers.get(track.id);
        const timelineLimit = this.version.timelineLimit ?? 180;
        return {
          left: before ? clipBounds(before).end : 0,
          right: after ? clipBounds(after).start : Infinity,
          timelineLimit,
          startLimit: this.version.timelineLimit ?? (parts ? timelineLimit : 120),
          reserveTail: !!parts || this.version.localImport,
          rate: buffer?.sampleRate,
          frames: buffer?.length
        };
      };
      const commit = (clip) => {
        const previous = this.clip(track, part);
        if (Object.keys(previous).every((key) => previous[key] === clip[key])) return;
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
        action,
        constraints,
        read: () => this.clip(track, part),
        commit,
        geometry: () => ({
          width: this.imw.enabled() ? this.imw.dragWidth() : this.$("lane").getBoundingClientRect().width,
          length: this.imw.enabled() ? this.rulerLength : this.length
        }),
        select: () => this.selectClip(track, part),
        preview: (clip, { length }) => {
          this.showDragPreview(group, clip, Math.max(length, roundTimeline(clipBounds(clip).end)));
          if (action !== "move") {
            this.paintClip(track, clip, group);
            if (this.selected === track && this.selectedPart === part) this.updateClipDetails(clip);
          }
        },
        cancel: () => this.grid()
      });
    }
    updateQuietControls() {
      const editable = this.draft && !this.recoveryConflict;
      this.$("cut-quiet").disabled = !editable || !this.buffers.size;
      this.$("undo-cut").hidden = !editable || !this.draft.cutUndo;
    }
    cutQuiet() {
      if (!this.draft || this.recoveryConflict) return;
      const changed = /* @__PURE__ */ new Map();
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
          count += cut.count + Number(clip.silenceHead > 0 && cut.ranges[0]?.[0] === 0) + Number(clip.silenceTail > 0 && cut.ranges.at(-1)?.[1] === clip.duration);
          for (const [from, to] of cut.ranges) {
            parts.push({
              start: clip.start + from,
              sourceIn: clip.sourceIn + from,
              duration: to - from,
              head: 0,
              tail: 0,
              silenceHead: 0,
              silenceTail: 0
            });
          }
        }
        if (count) {
          before[track.id] = this.draft.splits[track.id] ?? null;
          changed.set(track, parts);
          removed += count;
        }
      }
      if (!removed) {
        this.status("\u6CA1\u6709\u7B26\u5408 \u221248 dBFS \u6761\u4EF6\u7684\u4F4E\u97F3\u91CF\u6BB5");
        return;
      }
      this.draft.cutUndo = before;
      this.applySplits(changed, "\u5DF2\u5207\u9664 " + removed + " \u6BB5\u4F4E\u97F3\u91CF");
    }
    undoQuiet() {
      if (!this.draft?.cutUndo || this.recoveryConflict) return;
      const before = this.draft.cutUndo;
      const changed = new Map(this.version.tracks.filter((track) => Object.hasOwn(before, track.id)).map((track) => [track, before[track.id]]));
      delete this.draft.cutUndo;
      this.applySplits(changed, "\u5DF2\u64A4\u9500\u5207\u9664");
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
      let end = Math.max(this.length, this.imw.enabled() ? 0 : this.detachedTracks.extent());
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
          const { start, end: end2 } = clipBounds(clip);
          const times = format(start) + "\u2013" + format(end2);
          const source = format(clip.sourceIn) + "\u2013" + format(clip.sourceIn + clip.duration);
          const body = group.querySelector(".clip");
          body.title = track.name + " \xB7 " + times + " \xB7 \u6E90 " + source + " \xB7 \u5DE6\u53F3\u65B9\u5411\u952E\u79FB\u52A8";
          for (const edge of ["head", "tail"]) {
            const control = group.querySelector(".trim-handle." + edge);
            const at = edge === "head" ? start : end2;
            control.title = "\u64AD\u653E" + (edge === "head" ? "\u8D77\u70B9 " : "\u7EC8\u70B9 ") + detailTime(at) + " \xB7 \u62D6\u52A8\u88C1\u526A \xB7 \u65B9\u5411\u952E 1 \u6837\u672C \xB7 Shift + \u65B9\u5411\u952E 10 \u6BEB\u79D2";
            control.setAttribute("aria-description", control.title);
          }
        }
      }
      this.updateQuietControls();
      if (this.loop.end > this.length) {
        this.loop.end = this.length;
        this.loop.start = Math.min(this.loop.start, this.length - 0.25);
      }
      this.paintLoop();
      this.updateSelection();
      this.transport.sync();
      this.paint();
    }
    drawRuler(length = this.rulerLength) {
      const lane = this.$("lane");
      if (!lane.clientWidth) return;
      if (this.imw?.enabled()) return this.frameRuler.draw(this.imw.displayLength() || 1);
      const { labels, unit, major, beat, detail } = timelineGrid({
        length,
        width: lane.clientWidth,
        bpm: this.song?.bpm,
        meter: this.song?.meter
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
        const selected = group.dataset.head ? group.dataset.head === this.selected?.id : group.dataset.track === this.selected?.id && Number(group.dataset.part) === this.selectedPart;
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
      this.$("clip-timeline").textContent = detailTime(start) + "\u2013" + detailTime(end);
      this.$("clip-source").textContent = detailTime(clip.sourceIn) + "\u2013" + detailTime(clip.sourceIn + clip.duration);
      this.$("clip-duration").textContent = detailTime(end - start);
      const buffer = this.buffers.get(this.selected.id);
      this.$("clip-sample-row").hidden = !buffer;
      if (buffer) {
        const { first, last } = sourceFrames(clip, buffer.sampleRate, buffer.length);
        this.$("clip-samples").textContent = first + "\u2013" + last + "\uFF08" + (last - first) + "\uFF09";
      }
      const formatLabel = buffer ? "WAV \xB7 " + (buffer.numberOfChannels === 1 ? "\u5355\u58F0\u9053" : buffer.numberOfChannels + " \u58F0\u9053") + " \xB7 " + buffer.sampleRate / 1e3 + " kHz" : "\u7F3A\u5931\u97F3\u9891";
      this.$("clip-format").textContent = this.version.paintOnly ? "\u4EC5\u7ED8\u5236" : formatLabel;
    }
    paintLoop(length = this.rulerLength) {
      const band = this.$("loop-band");
      band.hidden = !this.loopEnabled || !this.version;
      band.style.left = 100 * this.loop.start / length + "%";
      band.style.width = 100 * (this.loop.end - this.loop.start) / length + "%";
    }
    paint(waveHeight) {
      if (this.hasAttribute("data-imw-track-motion") && waveHeight === void 0) return;
      for (const track of this.version?.tracks ?? []) {
        for (const [part, group] of this.groups.get(track.id).entries()) {
          this.paintClip(track, this.clip(track, part), group, waveHeight);
        }
      }
    }
    waveIndex(buffer, channels) {
      if (!buffer || buffer.duration <= 60) return void 0;
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
      const channels = drawingOnly ? [fixtureSamples] : Array.from({ length: buffer.numberOfChannels }, (_, channel) => buffer.getChannelData(channel));
      const rms = new Float32Array(width);
      if (last <= first) return;
      const data = wavePeaks(channels, first, last - first, width, rms, this.waveIndex(buffer, channels));
      const context = canvas.getContext("2d");
      context.fillStyle = color;
      for (let x = 0; x < width; x++) {
        const low = data[2 * x];
        const high = data[2 * x + 1];
        const top = height * (0.5 - high * 1.35);
        const size = height * (high - low) * 1.35;
        context.globalAlpha = peakAlpha;
        context.fillRect(x, top, 1, Math.max(size, 1));
        const innerLow = Math.max(low, -rms[x]);
        const innerHigh = Math.min(high, rms[x]);
        if (innerHigh <= innerLow) continue;
        context.globalAlpha = rmsAlpha;
        context.fillRect(
          x,
          height * (0.5 - innerHigh * 1.35),
          1,
          height * (innerHigh - innerLow) * 1.35
        );
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
      const edges = this.version?.tracks.flatMap((track) => this.clips(track).flatMap((clip) => {
        const { start, end } = clipBounds(clip);
        return [start, end];
      })) ?? [];
      const position = this.playing ? this.clockPosition() : this.seconds;
      const ahead = edges.filter((edge) => direction * (edge - position) > 0.04);
      const target = ahead.length ? direction > 0 ? Math.min(...ahead) : Math.max(...ahead) : position + direction * 5;
      this.seek(target);
    }
    setLoop(start, end) {
      if (!Number.isFinite(start) || !Number.isFinite(end) || start < 0 || end > this.length || end - start < 0.25) {
        this.status("\u5FAA\u73AF\u8D77\u7EC8\u70B9\u987B\u4F4D\u4E8E\u65F6\u95F4\u8F74\u5185\uFF0C\u533A\u95F4\u81F3\u5C11 0.25 \u79D2\u3002");
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
      if (this.master) this.master.gain.setTargetAtTime(level, this.context.currentTime, 0.015);
    }
    get canPlayAudio() {
      return this.audioReady || this.workAudio?.available();
    }
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
        if (!ready && !request.signal.aborted) this.status("\u6D4F\u89C8\u5668\u97F3\u9891\u8F93\u51FA\u672A\u5C31\u7EEA\u3002");
      } catch {
        ready = false;
        if (!request.signal.aborted) this.status("\u97F3\u9891\u672A\u80FD\u5F00\u59CB\u64AD\u653E\uFF0C\u8BF7\u91CD\u8BD5\u3002");
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
            this.context = new AudioContext(bridge ? { sinkId: { type: "none" } } : { latencyHint: "playback" });
            this.output = this.context.destination;
            if (bridge) {
              this.output = this.context.createMediaStreamDestination();
              this.player = new Audio();
              this.player.srcObject = this.output.stream;
            }
            this.master = this.context.createGain();
            this.master.gain.value = this.level;
            this.master.connect(this.output);
            this.monitorGains = new MonitorGains(this.context, this.workAudio.connect(this.context, this.master));
            this.clickBuffers = /* @__PURE__ */ new Map();
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
        this.output.stream.getTracks().forEach((track) => track.stop());
        this.player = null;
      }
      this.output = null;
      if (context.state === "closed") return;
      let timer;
      try {
        await Promise.race([
          context.close(),
          new Promise((resolve) => {
            timer = setTimeout(resolve, 200);
          })
        ]);
      } catch {
      } finally {
        clearTimeout(timer);
      }
    }
    queueBuffer(buffer, time2, offset, duration, trackId, fadeIn = false) {
      const source = this.context.createBufferSource();
      source.buffer = buffer;
      if (trackId) {
        const gain = this.context.createGain();
        if (fadeIn) {
          gain.gain.setValueAtTime(0, time2);
          gain.gain.linearRampToValueAtTime(1, time2 + Math.min(8e-3, duration));
        }
        source.connect(gain).connect(this.monitorGains.lane(trackId, this.trackMonitorState(trackId).audible));
        this.clipSources.set(source, { trackId, gain, start: time2, end: time2 + duration });
      } else {
        source.connect(this.workAudio.programOutput());
      }
      source.start(time2, offset, duration);
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
        const buffer = this.context.createBuffer(1, Math.ceil(rate * 0.03), rate);
        const samples = buffer.getChannelData(0);
        for (let index = 0; index < samples.length; index++) {
          const time2 = index / rate;
          samples[index] = Math.sin(2 * Math.PI * (accent ? 1550 : 1050) * time2) * Math.min(1, time2 / 2e-3) * Math.exp(-time2 * 155) * (accent ? 0.45 : 0.32);
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
      this.monitorGains?.update(
        route === "master" || route === "bypass",
        (id) => this.trackMonitorState(id).audible,
        immediate
      );
    }
    monitorSelectionChanged() {
      if (this.imw.enabled()) globalThis.OAIMWVideo?.refreshMix?.();
      if (this.liveMonitor?.run && this.monitorRoute() === "filtered")
        for (const window2 of this.busWindows) this.queueMonitorStems(window2);
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
      this.busWindows = this.busWindows.filter((w) => w.at + w.to - w.from > now);
      const window2 = { from, to, at, stems: false };
      this.busWindows.push(window2);
      if (this.monitorRoute() === "filtered") this.queueMonitorStems(window2);
      this.workAudio.schedule(from, to, at);
      this.scheduleClicks(from, to, at);
    }
    queueMonitorStems(window2) {
      if (window2.stems) return;
      window2.stems = true;
      const at = Math.max(window2.at, this.context.currentTime);
      const from = window2.from + (at - window2.at);
      if (from >= window2.to) return;
      for (const track of this.version.tracks) this.scheduleClip(track, from, window2.to, at);
    }
    scheduleClip(track, from, to, at, fadeIn = false) {
      this.queueTrackClips(track, from, to, at, (buffer, time2, offset, duration, trackId, fade) => {
        this.queueBuffer(buffer, time2, offset, duration, trackId, fade);
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
        const time2 = at + Math.max(0, start - from + skipped / rate);
        queue(buffer, time2, offset / rate, (past - offset) / rate, track.id, fadeIn && start < from);
      }
    }
    schedule(from, to, at) {
      for (const track of this.version.tracks) this.scheduleClip(track, from, to, at);
      this.workAudio.schedule(from, to, at);
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
      const at = this.context.currentTime + 0.018;
      for (const [source, voice] of this.clipSources) {
        if (voice.trackId !== track.id || voice.retired || voice.end <= at) continue;
        voice.retired = true;
        if (voice.start < at) {
          const fadeStart = Math.max(voice.start, at - 8e-3);
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
      if (at >= this.nextRun) return;
      const { start, end } = this.loop;
      this.scheduleClip(track, from, end, at, true);
      const duration = end - start;
      for (let cycle = at + end - from; cycle < this.nextRun - 1e-6; cycle += duration) {
        this.scheduleClip(track, start, end, cycle);
      }
    }
    clockPosition(time2 = this.context.currentTime) {
      if (this.busPending) return this.seconds;
      const raw = Math.max(0, time2 - this.clock);
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
          this.status("\u97F3\u9891\u8F93\u51FA\u6CA1\u6709\u542F\u52A8\u3002\u518D\u6B21\u70B9\u51FB\u64AD\u653E\u53EF\u91CD\u8FDE\u3002");
          return;
        }
        if (this.loopEnabled && this.nextRun < now + 0.18) {
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
        this.outputMonitor = { analyser, samples: new Float32Array(analyser.fftSize), at: now - 0.05, peak: 0 };
      }
      const meter = this.outputMonitor;
      const elapsed = now - meter.at;
      if (elapsed < 0.04) return;
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
    pause() {
      this.stopAndRemember();
    }
    seek(seconds, persist = true) {
      if (this.imw.enabled()) return this.imw.seek(seconds);
      const position = Math.max(0, Math.min(this.length, seconds));
      const withinLoop = !this.loopEnabled || position >= this.loop.start && position < this.loop.end;
      const continuePlaying = this.playing && position < this.length && withinLoop;
      this.stop(continuePlaying);
      this.seconds = position;
      this.position();
      if (continuePlaying) this.play();
      if (persist) this.changed();
    }
    status(text) {
      this.$("status").textContent = text;
    }
    snapshot() {
      if (!this.draft || this.recoveryConflict) return false;
      this.draft.seconds = Math.round(this.seconds * 10) / 10;
      this.draft.scroll = this.frameRuler.audioScroll();
      this.dirty = true;
      return true;
    }
    journal() {
      if (this.dirty) rememberPreference(this.endpoint(), this.draft);
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
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify(candidate)
          });
          this.dirty = !sameDraft(this.draft, candidate);
          this.draft.revision = result.revision;
          rememberPreference(endpoint, this.dirty ? this.draft : null);
          this.status(this.editNotice ?? "\u8349\u7A3F\u5DF2\u4FDD\u5B58");
          this.editNotice = null;
          this.$("retry").hidden = true;
          return true;
        } catch (error) {
          this.status(error.status === 409 ? "\u8349\u7A3F\u5DF2\u5728\u5176\u4ED6\u7A97\u53E3\u66F4\u65B0\u3002\u5F53\u524D\u7F16\u8F91\u5DF2\u4FDD\u7559\uFF0C\u8BF7\u4FDD\u7559\u6B64\u7A97\u53E3\u3002" : "\u4FDD\u5B58\u5931\u8D25\uFF0C\u5F53\u524D\u7F16\u8F91\u5DF2\u4FDD\u7559\u3002\u91CD\u8BD5\u540E\u53EF\u5207\u6362\u3002");
          this.$("retry").hidden = false;
          return false;
        } finally {
          this.saving = null;
        }
      })();
      const success = await this.saving;
      return success && (!this.dirty || await this.save());
    }
  };
  customElements.define("lus-studio", Studio);
  globalThis.OAStudio = {
    clipEditing,
    openHome(container, call2, navigation) {
      connectStudio(call2);
      openHome(container, navigation);
    },
    openSongs(container, call2, navigation, project) {
      connectStudio(call2);
      openSongs(container, navigation, project);
    },
    homeSelection,
    closeHome,
    async imwProjectSelection(project) {
      return await document.querySelector("lus-studio")?.imwProjectSelection(project) ?? null;
    },
    setVideoProject(project, selection2) {
      document.querySelector("lus-studio")?.imw?.setProject(project, selection2);
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
    open(container, call2, selection2, feature) {
      connectStudio(call2);
      const homeFeature = feature ? { key: feature, selection: selection2 } : null;
      const mounted = container.querySelector("lus-studio");
      if (mounted) {
        mounted.homeFeature = homeFeature;
        if (!mounted.imw.enabled()) mounted.transport.activate();
        mounted.transport.time(format(mounted.seconds));
        mounted.transport.sync();
        if (selection2) queueMicrotask(() => void mounted.openHomeTarget(selection2));
        else if (feature) queueMicrotask(() => mounted.showHomeFeature());
        return;
      }
      const studio = document.createElement("lus-studio");
      studio.homeTarget = selection2;
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
      if (studio) {
        studio.stop();
        studio.transport.deactivate();
        clearAnalysis(studio);
        studio.coverController?.abort();
        studio.disposeBus?.();
        void studio.closeOutput();
      }
    }
  };
})();
