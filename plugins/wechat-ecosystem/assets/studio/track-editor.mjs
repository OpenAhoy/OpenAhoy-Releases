import { studioFetch as fetch } from "./bridge.mjs";
import { XmlImport } from "./track-score/xml.mjs";
import { Render } from "./track-score/render.mjs";

export const trackEditorMarkup = `
<section id="track-editor" class="track-editor" aria-label="单轨编辑" hidden>
  <header class="track-editor-header">
    <button id="track-back" type="button">‹ 返回编排</button>
    <h2 id="track-editor-name"></h2>
    <button id="track-solo" type="button" aria-pressed="false">独听</button>
    <div class="track-tools" role="group" aria-label="单轨工具">
      <button id="track-score-tab" type="button" aria-pressed="true">出谱</button>
      <button id="track-vocal-tab" type="button" aria-pressed="false">Vocal 发音</button>
    </div>
  </header>
  <section id="track-score-pane" class="track-pane">
    <form id="track-score-form" class="track-form">
      <label>谱面 BPM <input name="tempo" type="number" min="30" max="300" step=".01" required></label>
      <button id="track-generate-score" type="button">生成旋律谱</button>
      <a id="track-midi" hidden download="旋律.mid">MIDI</a>
      <a id="track-xml" hidden download="旋律.musicxml">MusicXML</a>
    </form>
    <div id="track-score-preview" hidden>
      <div id="track-score-layout" class="track-tools" role="group" aria-label="谱面视图">
        <button id="track-notation-tab" type="button" aria-pressed="true">简谱</button>
        <button id="track-roll-tab" type="button" aria-pressed="false">钢琴卷帘</button>
      </div>
      <div id="track-notation" aria-label="识别简谱"></div>
      <div id="track-roll-scroll" hidden><canvas id="track-note-roll" aria-label="识别音符预览"></canvas></div>
    </div>
  </section>
  <section id="track-vocal-pane" class="track-pane" hidden>
    <form id="track-vocal-form" class="vocal-fields">
      <fieldset>
        <legend>原唱与目标</legend>
        <label>原唱短句 <input name="line" maxlength="40" required></label>
        <label>第几个字 <input name="character" type="number" min="1" max="40" step="1" value="1" required></label>
        <label>新字或拼音 <input name="reading" maxlength="12" placeholder="例：破 或 po4" required></label>
        <label>原发音（可选） <input name="actual" maxlength="12" placeholder="例：kai1"></label>
      </fieldset>
      <fieldset>
        <legend>源音频时间（秒）</legend>
        <label>短句起点 <input name="lineStart" type="number" step=".001" min="0" required></label>
        <label>短句终点 <input name="lineEnd" type="number" step=".001" min="0" required></label>
        <label>字起点 <input name="wordStart" type="number" step=".001" min="0" required></label>
        <label>字终点 <input name="wordEnd" type="number" step=".001" min="0" required></label>
      </fieldset>
      <fieldset>
        <legend>同轨参考短句</legend>
        <label>参考歌词 <input name="reference" maxlength="40" required></label>
        <label>参考起点 <input name="refStart" type="number" step=".001" min="0" required></label>
        <label>参考终点 <input name="refEnd" type="number" step=".001" min="0" required></label>
      </fieldset>
      <div class="vocal-commands">
        <button id="track-align" type="button">对齐这句</button>
        <button id="track-generate-vocal" type="button">生成发音候选</button>
      </div>
      <div id="track-aligned-words" aria-label="字级时间" class="vocal-commands"></div>
    </form>
    <div id="track-vocal-result" class="vocal-result" hidden>
      <label>原声 <audio id="track-vocal-original" controls preload="none"></audio></label>
      <label>新发音 <audio id="track-vocal-candidate" controls preload="none"></audio></label>
      <a id="track-vocal-download" download="发音候选.wav">下载候选 WAV</a>
    </div>
  </section>
  <p id="track-editor-status" role="status"></p>
</section>
<div id="clip-menu" class="clip-menu" role="menu" aria-label="音频条菜单" hidden>
  <button type="button" role="menuitem" id="clip-open-track">进入单轨编辑</button>
  <button type="button" role="menuitem" id="clip-seek-start">定位到片段起点</button>
  <button type="button" role="menuitem" id="clip-score">出谱</button>
  <button type="button" role="menuitem" id="clip-vocal">Vocal 发音</button>
</div>`;

const messageText = {
  busy: "本机已有处理任务，请等它完成后重试。",
  score_empty: "该轨没有检测到可出谱的主旋律音符。",
  score_unavailable: "本机 Audio to MIDI 未就绪。",
  vocal_unavailable: "本机 Vocalis 未就绪。",
  score_input: "请检查谱面 BPM 和当前音频选区。",
  align_input: "请填写正确歌词和不超过 10 秒的短句范围。",
  MODEL_PHONEME_CONTRACT: "Vocalis 的本机音素库不支持这个拼音或声调。",
  vocal_input: "请确认歌词、所选字边界和同轨参考时间。参考短句须与待改短句分开。",
  source_changed: "草稿已更新，请重新打开该工程后处理。",
  MODEL_ALIGNMENT_REVIEW_REQUIRED: "Vocalis 无法可靠对齐这段词，请核对原唱和参考歌词，并缩短范围。",
  GENERATION_CONTEXT_LIMIT: "原唱短句须在 10 秒以内。",
  MODEL_BUSY: "Vocalis 正忙，请稍后重试。",
};

const isVocal = track => track.role === "vocal" || /主唱|和声|人声|vocals?|voice/i.test(track.name);
const canScore = track => !/鼓组|打击|drums?|percussion/i.test(track.name);

export function mountTrackEditor(studio) {
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
    for (const node of studio.shadowRoot.querySelectorAll("[data-track-row]")) {
      node.hidden = !!focused && !folded && node.dataset.trackRow !== focused.id;
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
    status.textContent = job ? "正在本机处理…" : !vocal && !canScore(focused)
      ? "鼓组与打击乐暂不支持单旋律出谱。" : "";
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
    if (restore && arrangementScroll !== undefined) studio.$("track-scroll-panel").scrollTop = arrangementScroll;
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

  for (const [id, tool] of [["clip-open-track", undefined], ["clip-score", "score"], ["clip-vocal", "vocal"]]) {
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
  studio.shadowRoot.addEventListener("pointerdown", event => {
    if (!event.composedPath().includes(menu)) closeMenu();
  });
  menu.addEventListener("keydown", event => {
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
    const pitches = result.notes.map(note => note[2]);
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
      paint.fillRect(start / result.duration * width, (max - pitch) * row,
        Math.max(1, (end - start) / result.duration * width), Math.max(1, row - 1));
    }
  }

  async function run(event, kind) {
    event.preventDefault();
    if (!focused || job) return;
    if (!studio.project?.trackProcessing) {
      status.textContent = "此项目未接入单轨出谱或 Vocalis。";
      return;
    }
    const track = focused;
    const form = kind === "score" ? scoreForm : vocalForm;
    if (kind === "score" && (!canScore(track) || !studio.clips(track).length)) return;
    if (kind !== "align" && !form.reportValidity()) return;
    const request = Object.fromEntries(new FormData(form));
    const controller = new AbortController();
    job = controller;
    status.textContent = {score: "Audio to MIDI 正在识别旋律…", vocal: "Vocalis 正在生成发音候选…",
      align: "Vocalis 正在对齐这一句…"}[kind];
    const buttons = [$("track-generate-score"), $("track-generate-vocal"), $("track-align")];
    buttons.forEach(button => { button.disabled = true; });
    if (kind === "vocal") {
      clearAuditionIfPlaying();
      studio.pause();
    }

    try {
      if (!await studio.save()) throw Error("source_changed");
      if (job !== controller) return;
      const endpoint = studio.endpoint().replace("/draft?", "/track-process?")
        + "&track=" + encodeURIComponent(track.id) + "&kind=" + kind;
      const response = await fetch(endpoint, { method: "POST", signal: controller.signal,
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ ...request, revision: studio.draft?.revision ?? 0 }) });
      const result = await response.json();
      if (job !== controller) return;
      if (!response.ok) throw Error(result.error);
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
          const file = await fetch(result.xml, { signal: controller.signal });
          if (!file.ok) throw Error("score");
          const parsed = XmlImport.parse(await file.text());
          if (job !== controller) return;
          Render.draw($("track-notation"), parsed.notes,
            { ...parsed, title: studio.song.name + " · " + track.name, selected: -1, cursor: 0, lyricEdit: -1 });
          notationView(true);
          scoreReady = true;
        } catch {
          if (job !== controller) return;
        }
        status.textContent = result.notes.length + " 个音符 · " + result.tempo + " BPM · " + result.meter
          + " · 主旋律" + (scoreReady ? "" : " · 简谱预览未能绘制");
      } else if (kind === "align") {
        $("track-aligned-words").replaceChildren(...result.words.map((word, index) => {
          const button = document.createElement("button");
          button.type = "button";
          button.textContent = word.char;
          button.title = word.start + "–" + word.end + " 秒";
          button.setAttribute("aria-pressed", "false");
          button.onclick = () => {
            for (const item of button.parentElement.children) item.setAttribute("aria-pressed", String(item === button));
            vocalForm.elements.character.value = index + 1;
            vocalForm.elements.wordStart.value = word.start;
            vocalForm.elements.wordEnd.value = word.end;
          };
          return button;
        }));
        status.textContent = "请选择要改发音的字，并试听核对边界。";
      } else {
        $("track-vocal-original").src = result.original;
        $("track-vocal-candidate").src = result.candidate;
        $("track-vocal-download").href = result.full;
        $("track-vocal-result").hidden = false;
        status.textContent = result.actual + " → " + result.target + " · 请对听确认";
      }
    } catch (error) {
      if (job === controller) status.textContent = messageText[error.message] ?? "本机处理未完成，原轨已保留。";
    } finally {
      if (job === controller) {
        job = null;
        buttons.forEach(button => { button.disabled = false; });
      }
    }
  }

  $("track-align").onclick = event => void run(event, "align");
  vocalForm.elements.line.oninput = () => $("track-aligned-words").replaceChildren();
  for (const id of ["lineStart", "lineEnd"]) vocalForm.elements[id].oninput = vocalForm.elements.line.oninput;
  for (const [kind, form] of [["score", scoreForm], ["vocal", vocalForm]]) {
    $("track-generate-" + kind).onclick = event => void run(event, kind);
    form.addEventListener("keydown", event => {
      if (event.key === "Enter" && !event.isComposing && event.target instanceof HTMLInputElement) void run(event, kind);
    });
  }
  $("track-vocal-original").onplay = () => $("track-vocal-candidate").pause();
  $("track-vocal-candidate").onplay = () => $("track-vocal-original").pause();

  return {
    close, closeMenu, syncRows, foldForVideo,
    escape() {
      if (menuTarget) { closeMenu(true); return true; }
      if (focused && !folded) { close(true); return true; }
      return false;
    },
    bind(element, track, part) {
      element.ondblclick = () => open(track, part, undefined, element);
      element.oncontextmenu = event => showMenu(event, track, part, element);
      element.addEventListener("keydown", event => {
        if (event.key === "ContextMenu" || (event.key === "F10" && event.shiftKey)) {
          showMenu(event, track, part, element);
        }
      });
    },
  };
}
