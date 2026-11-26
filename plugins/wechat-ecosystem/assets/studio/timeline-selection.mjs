// The lane includes slotted video clips as well as the Studio shadow-DOM audio tracks.
export function mountTimelineSelection(studio) {
  const lane = studio.$("lane"), ruler = studio.$("ruler"), seek = studio.$("seek");
  const picture = studio.$("imw-picture-lane");
  const overlay = document.createElement("output");
  const caption = document.createElement("span");
  overlay.id = "timeline-selection";
  overlay.setAttribute("aria-label","时间选区");
  overlay.hidden = true;
  overlay.append(caption);
  lane.append(overlay);
  const lifetime = new AbortController(), options = {signal:lifetime.signal};
  let range, drag, suppressClick = false;

  function scale() {
    return studio.imw.enabled() ? studio.imw.displayLength() : studio.rulerLength;
  }
  function time(x) {
    const box = lane.getBoundingClientRect();
    const video = studio.imw.enabled();
    const end = video ? globalThis.OAIMWVideo?.state()?.length : studio.length;
    let value = (x-box.left)*scale()/Math.max(1,box.width);
    value = video ? studio.frameRuler.snap(value) : Math.round(value*48000)/48000;
    return Math.max(0,Math.min(end ?? 0,value));
  }
  function liveRow(row) {
    if (row?.isConnected) return row;
    const trackId = row?.dataset.trackRow;
    if (trackId) {
      const replacement = lane.querySelector('.track-row[data-track-row="' + CSS.escape(trackId) + '"]');
      if (replacement) return replacement;
    }
    return lane;
  }
  function paint() {
    overlay.hidden = !range;
    if (!range) {
      caption.textContent = "";
      overlay.removeAttribute("data-video-range");
      delete overlay.dataset.start;
      delete overlay.dataset.end;
      return;
    }
    const length = scale();
    if (!(length>0)) {overlay.hidden = true;return;}
    const box = lane.getBoundingClientRect();
    const first = liveRow(range.first), last = liveRow(range.last);
    const a = first.getBoundingClientRect(), b = last.getBoundingClientRect();
    if (!a.height || !b.height) return;
    range.first = first;
    range.last = last;
    const top = Math.min(a.top,b.top);
    const bottom = Math.max(a.bottom,b.bottom);
    overlay.style.top = (top-box.top)+"px";
    overlay.style.height = (bottom-top)+"px";
    const pictureBox = picture.getBoundingClientRect();
    let filmTop = 0, filmBottom = 0;
    if (studio.imw.enabled() && top < pictureBox.bottom && bottom > pictureBox.top) {
      const strip = studio.querySelector("#dmCutStrip");
      const film = strip?.querySelector(".clip:has(.dc-source-wave) .dc-film") ?? strip?.querySelector(".dc-film");
      if (film) {
        const filmBox = film.getBoundingClientRect();
        filmTop = Math.max(top, filmBox.top);
        filmBottom = Math.min(bottom, filmBox.bottom);
      }
    }
    const hasFilm = filmBottom > filmTop;
    overlay.toggleAttribute("data-video-range", hasFilm);
    if (hasFilm) {
      overlay.style.setProperty("--selection-video-y", (filmTop-top)+"px");
      overlay.style.setProperty("--selection-video-height", (filmBottom-filmTop)+"px");
    }
    overlay.style.left = 100*range.start/length+"%";
    overlay.style.width = 100*(range.end-range.start)/length+"%";
    const label = s => studio.rulerLabel(s);
    caption.textContent = label(range.start)+" – "+label(range.end);
    overlay.dataset.start = range.start;
    overlay.dataset.end = range.end;
  }
  function endGesture() {
    if (!drag) return;
    const {id, target} = drag;
    drag = null;
    if (target.hasPointerCapture(id)) target.releasePointerCapture(id);
  }
  function clear() {
    endGesture();
    range = null;
    paint();
  }
  function rowAt(y, fallback) {
    for (const row of lane.querySelectorAll("#imw-picture-lane,.track-row")) {
      const b = row.getBoundingClientRect();
      if (b.height && y>=b.top && y<b.bottom) return row;
    }
    return fallback;
  }
  function cursor(at, videoClip) {
    if (studio.imw.enabled()) globalThis.OAIMWVideo?.locate?.(at,videoClip);
    else studio.seek(at);
  }
  function modifier(event) {
    studio.toggleAttribute("data-command-grab",!!event.metaKey);
  }
  function down(e) {
    if (e.button!==0 || !e.isPrimary || drag) return;
    modifier(e);
    suppressClick = false;
    const path = e.composedPath();
    if (path.includes(studio.$("imw-folded-video")) || e.pointerType!=="mouse") return;
    const clip = path.find(n=>n.matches?.(".clip,.trim-handle"));
    if (e.metaKey && clip) {clear();return;}
    if (path.some(n=>n.matches?.("button,input,select,textarea") && n!==clip && n!==seek)) return;
    if (!(scale()>0)) return;
    e.preventDefault();
    e.stopImmediatePropagation();
    clear();
    const group = path.find(n=>n.matches?.(".clip-group[data-track]"));
    const track = group && studio.version?.tracks.find(t=>t.id===group.dataset.track);
    if (track) studio.selectClip(track,Number(group.dataset.part)||0);
    // Retain the original click target for keyboard focus and native double-click editing.
    const target = clip || (path.includes(ruler) ? ruler : lane);
    (clip || seek).focus({preventScroll:true});
    const first = path.includes(ruler) ? lane : rowAt(e.clientY,lane);
    const videoClip = path.find(n=>n.dataset?.clip)?.dataset.clip;
    drag = {id:e.pointerId,target,x:e.clientX,start:time(e.clientX),first,videoClip};
    target.setPointerCapture(e.pointerId);
    suppressClick = true;
  }
  function move(e) {
    if (!drag || e.pointerId!==drag.id) return;
    if (!(e.buttons&1)) return finish(e);
    updateRange(e);
  }
  function updateRange(e) {
    if (!drag.moved && Math.abs(e.clientX-drag.x)<3) return;
    drag.moved = true;
    const next = time(e.clientX);
    if (next === drag.start) {
      range = null;
      paint();
      return;
    }
    drag.first = liveRow(drag.first);
    const last = drag.first===lane ? lane : rowAt(e.clientY, liveRow(range?.last || drag.first));
    range = {start:Math.min(drag.start,next),end:Math.max(drag.start,next),first:drag.first,last};
    paint();
  }
  function finish(e) {
    if (!drag || (e?.pointerId != null && e.pointerId!==drag.id)) return;
    // A release can report stale coordinates. Keep the last displayed range.
    if (!drag.moved && e?.type==="pointerup") updateRange(e);
    const {start,videoClip} = drag;
    endGesture();
    cursor(range?.start ?? start, videoClip);
  }
  function lostCapture(e) {
    if (drag?.id!==e.pointerId) return;
    if (e.buttons&1) drag.uncaptured = true;
    else finish(e);
  }
  function interrupt(e) {
    if (!drag || (e?.pointerId != null && e.pointerId!==drag.id)) return;
    if (range) finish(e);
    else clear();
  }
  function key(e) {
    modifier(e);
    if (e.key==="Escape" && (drag||range)) {clear();e.preventDefault();}
  }
  const capture = {capture:true,...options};
  lane.addEventListener("pointerdown",down,capture);
  lane.addEventListener("pointermove",modifier,options);
  document.addEventListener("pointermove",move,capture);
  document.addEventListener("pointerup",finish,capture);
  document.addEventListener("lostpointercapture",lostCapture,capture);
  document.addEventListener("pointercancel",interrupt,capture);
  document.addEventListener("pointerout",e=>{
    if (drag?.uncaptured && e.relatedTarget===null) interrupt(e);
  },capture);
  lane.addEventListener("dragstart",e=>{
    if (drag || (!e.metaKey && !studio.hasAttribute("data-command-grab"))) e.preventDefault();
  },capture);
  lane.addEventListener("click",e=>{
    if (suppressClick && e.detail) {suppressClick=false;e.preventDefault();e.stopImmediatePropagation();}
  },capture);
  document.addEventListener("keydown",key,options);
  document.addEventListener("keyup",modifier,options);
  window.addEventListener("blur",()=>{
    studio.removeAttribute("data-command-grab");
    interrupt();
  },options);
  return {clear,paint,get range(){return range;},dispose(){clear();lifetime.abort();}};
}
