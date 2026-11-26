import { readPreference, rememberPreference } from "./home.mjs";

const choices = new Map([
  ["auto", "跟随素材"], ["24000/1001", "23.976"], ["24/1", "24"], ["25/1", "25"],
  ["30000/1001", "29.97 NDF"], ["30000/1001 DF", "29.97 DF"], ["30/1", "30"],
  ["50/1", "50"], ["60000/1001", "59.94 NDF"], ["60000/1001 DF", "59.94 DF"], ["60/1", "60"],
]);

export function frameRate(value) {
  const parts = /^(\d{1,8})\/(\d{1,8})( DF)?$/.exec(value ?? "");
  const n = Number(parts?.[1]), d = Number(parts?.[2]);
  if (!d || n / d < 1 || n / d > 240) return { n: 30, d: 1, nominal: 30, drop: 0 };
  const nominal = Math.round(n / d);
  const drop = parts[3] && (nominal === 30 || nominal === 60) && n * 1001 === nominal * 1000 * d
    ? nominal / 15 : 0;
  return { n, d, nominal, drop };
}

export function frameLabel(frame, rate) {
  let count = Math.max(0, Math.floor(frame));
  const { nominal, drop } = rate;
  if (drop) {
    const minute = nominal * 60 - drop, ten = minute * 10 + drop;
    count += drop * (9 * Math.floor(count / ten) + Math.max(0, Math.floor((count % ten - drop) / minute)));
  }
  const seconds = Math.floor(count / nominal);
  const two = number => String(number).padStart(2, "0");
  return [Math.floor(seconds / 3600), Math.floor(seconds / 60) % 60, seconds % 60].map(two).join(":")
    + (drop ? ";" : ":") + two(count % nominal);
}

// The video transport stores integer milliseconds. Recognize a rounded frame boundary within half a millisecond.
export function frameAt(seconds, rate) {
  return Math.max(0, Math.floor((seconds + 0.000500001) * rate.n / rate.d));
}

export function mountFrameRuler(studio) {
  const $ = studio.$, ruler = $("ruler"), seek = $("seek"), menu = $("imw-frame-rate");
  const lane = $("lane");
  const grid = document.createElementNS("http://www.w3.org/2000/svg", "svg");
  const lines = document.createElementNS(grid.namespaceURI, "path");
  grid.setAttribute("class", "frame-marks");
  grid.setAttribute("aria-hidden", "true");
  grid.append(lines);
  ruler.append(grid);
  const originalTitle = ruler.title;
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
    if (studio.rulerScale() !== "timecode") {rendered = "";return;}
    const scale = studio.imw?.enabled() ? rate : frameRate();
    const width = lane.getBoundingClientRect().width;
    const pixelsPerFrame = width * scale.d / (axis * scale.n);
    if (pixelsPerFrame <= 0) return;
    const viewport = Math.max(1, scroll.clientWidth);
    const page = Math.floor(scroll.scrollLeft / viewport);
    const signature = [width, axis, scale.n, scale.d, scale.drop, viewport, page].join("/");
    if (signature === rendered) return;
    rendered = signature;
    // Only materialize frame boundaries near the viewport. Each line is located on the rational time grid.
    const firstFrame = Math.max(0, Math.floor((page - 1) * viewport / pixelsPerFrame));
    const origin = firstFrame * pixelsPerFrame;
    const lastFrame = Math.min(Math.ceil(axis * scale.n / scale.d), Math.ceil((page + 3) * viewport / pixelsPerFrame));
    grid.style.left = origin + "px";
    grid.style.width = Math.max(0, Math.min(width, lastFrame * pixelsPerFrame) - origin) + "px";
    const divisions = [];
    // Thin only subpixel marks. Every visible tick remains on the exact source frame grid.
    const stride = Math.max(1,Math.ceil(2/pixelsPerFrame));
    for (let i = Math.ceil(firstFrame/stride)*stride; i < lastFrame; i+=stride) {
      const height = i % scale.nominal === 0 ? 14 : i % 5 === 0 ? 10 : 6;
      divisions.push("M"+((i-firstFrame)*pixelsPerFrame+.5).toFixed(3)+" 0v"+height);
    }
    lines.setAttribute("d", divisions.join(""));
    let step = [1, 2, 5, 10, scale.nominal, scale.nominal * 2, scale.nominal * 5]
      .sort((a,b) => a-b).find(frames => frames * pixelsPerFrame >= 95);
    if (!step) step = scale.nominal * 10 * Math.ceil(95 / (scale.nominal * 10 * pixelsPerFrame));
    const ticks = [];
    const start = Math.max(0, Math.floor((page - 1) * viewport / (step * pixelsPerFrame)) * step);
    const end = Math.min(width - 78, (page + 3) * viewport);
    for (let frame = start; frame * pixelsPerFrame < end; frame += step) {
      const tick = document.createElement("span");
      tick.style.left = 100 * frame * scale.d / (axis * scale.n) + "%";
      tick.textContent = frameLabel(frame, scale);
      ticks.push(tick);
    }
    $("ticks").replaceChildren(...ticks);
    // Use only coarse time divisions across the media rows.
    const second = scale.nominal * pixelsPerFrame;
    const coarse = second >= 8 ? second : second * Math.ceil(95 / second);
    lane.style.setProperty("--major-step", coarse + "px");
    lane.removeAttribute("data-detail");
    lane.removeAttribute("data-beat");
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
    if (fps !== rateKey) {
      cancelGesture();
      rateKey = fps;
      rate = frameRate(fps);
      rendered = "";
      const origin = source ? (rate.n / rate.d).toFixed(3).replace(/\.?0+$/, "") : "默认 30";
      menu.options[0].text = selected === "auto" ? "跟随素材（" + origin + " fps）" : "跟随素材";
      ruler.title = "点击定位，拖动划定时间选区，← / → 逐帧";
    }
    document.addEventListener("keydown", stepWithKeyboard);
    draw(studio.imw.displayLength(next));
    updateLabel();
  }

  function updateLabel() {
    if (!clock) return;
    const label = studio.rulerLabel(clock.seconds || 0);
    if (seek.getAttribute("aria-valuetext") !== label) seek.setAttribute("aria-valuetext", label);
  }

  function clampFrame(frame) {
    const last = Math.max(0, Math.ceil(clock.length * rate.n / rate.d - 1e-8) - 1);
    return Math.max(0, Math.min(last, frame));
  }

  function seekFrame(frame, scrubbing = false) {
    const target = clampFrame(frame) * rate.d / rate.n;
    const engine = globalThis.OAIMWVideo;
    const seekTo = (scrubbing && engine?.scrubFrame) || engine?.seekFrame || engine?.seek;
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
    if (!studio.isConnected || !studio.imw?.enabled() || studio.closest("[hidden]") || !clock?.ready || !clock.length ||
        gesture || event.defaultPrevented || event.isComposing || event.altKey || event.metaKey || event.ctrlKey || event.shiftKey) return;
    if (event.key !== "ArrowLeft" && event.key !== "ArrowRight") return;
    const target = event.composedPath()[0];
    if (target !== seek && (target.isContentEditable || target.closest?.("#ruler-scales,#regions .clip-group,.trim-handle,input,textarea,select,[role=slider],[role=spinbutton],[role=menu],[role=listbox],[role=tablist],[role=separator],dialog,[popover]:popover-open"))) return;
    event.preventDefault();
    const current = globalThis.OAIMWVideo?.state?.()?.seconds ?? clock.seconds;
    seekFrame(frameAt(current, rate) + (event.key === "ArrowRight" ? 1 : -1));
  }

  zoom.onchange = () => {
    if (!clock) return;
    if (zoomed()) savedScroll = scroll.scrollLeft;
    studio.toggleAttribute("data-frame-zoom", zoomed());
    rendered = "";
    studio.drawRuler();
    scroll.scrollLeft = zoomed() ? Math.max(0, clock.seconds / axis * $("lane").clientWidth - scroll.clientWidth / 2) : savedScroll;
    studio.paint();
  };
  scroll.addEventListener("scroll", () => {
    if (studio.rulerScale() !== "timecode" || scrollFrame) return;
    scrollFrame = requestAnimationFrame(() => {scrollFrame = 0; if (studio.rulerScale() === "timecode") draw(axis);});
  }, {passive:true});
  menu.onchange = () => {
    if (!clock || !scope) return;
    selected = menu.value;
    rememberPreference("frame-rate/" + scope, selected);
    sync(clock);
  };
  // Keep the slider focused for scrubbing and transport keys. Tab navigation retains its focus cue.
  seek.addEventListener("blur", () => ruler.removeAttribute("data-pointer-seek"));
  ruler.addEventListener("pointerdown", event => {
    if (!studio.imw?.enabled() || !clock?.ready || !clock.length || !event.isPrimary || event.button !== 0) return;
    event.preventDefault();
    cancelGesture();
    const frame = pointerFrame(event);
    gesture = { id:event.pointerId, next:frame, shown:frame, moved:false };
    ruler.setPointerCapture(event.pointerId);
    ruler.setAttribute("data-pointer-seek", "");
    seek.focus({preventScroll:true});
    seekFrame(frame);
  });
  ruler.addEventListener("pointermove", event => {
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
  ruler.addEventListener("click", event => {
    if (!studio.imw?.enabled() || !clock?.ready || !clock.length) return;
    // Pointer down/up already positioned the cursor. Suppress the native audio ruler click.
    event.stopImmediatePropagation();
    if (!event.detail && event.clientX) seekFrame(pointerFrame(event));
  }, true);
  return { draw, sync, updateLabel, current:seconds=>frameAt(seconds,rate)*rate.d/rate.n, snap:seconds=>Math.round(seconds*rate.n/rate.d)*rate.d/rate.n,
    label(seconds){
      const scale = studio.imw?.enabled() ? rate : frameRate();
      return frameLabel(frameAt(seconds,scale),scale);
    }, audioScroll:() => zoomed() ? savedScroll : scroll.scrollLeft, reset() {
    cancelGesture();
    document.removeEventListener("keydown", stepWithKeyboard);
    rendered = ""; rateKey = ""; ruler.title = originalTitle;
    lane.style.removeProperty("--frame-zoom-width");
    studio.removeAttribute("data-frame-zoom"); zoom.value = "audio";
  } };
}
