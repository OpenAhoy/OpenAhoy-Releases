const frameEpsilon = 1e-6;
export const ceilFrame = frame => Math.ceil(frame - frameEpsilon);

// All positions are seconds. The source grid is PCM samples for stems and milliseconds for a score.
function change(original, action, delta, {
  rate, frames, left = 0, right = Infinity, timelineLimit, startLimit = timelineLimit,
  reserveTail = false, minFrames = 1,
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
  // Consume legacy padding before the corresponding PCM endpoint moves.
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
  const most = isHead
    ? Math.min(end, frames / rate) - minFrames / rate
    : Math.min(sourceEnd, end + (Math.min(right, timelineLimit) - (original.start + original.duration)));
  const lowFrame = Math.max(0, ceilFrame(least * rate));
  const highFrame = Math.min(frames, Math.floor(Math.min(most,
    isHead ? start + (startLimit - original.start) : Infinity) * rate + frameEpsilon));
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

// Threshold in screen pixels, so the gesture feels the same across zoom levels.
const snapPixels = 8;

function playheadDelta(delta, edges, position, secondsPerPixel, accepts = () => true) {
  if (!Number.isFinite(position)) return null;
  const candidates = edges.map(edge => position - edge);
  candidates.sort((a, b) => Math.abs(a - delta) - Math.abs(b - delta));
  return candidates.find(next => Math.abs(next - delta) <= snapPixels * secondsPerPixel && accepts(next)) ?? null;
}

function bounds(clip) {
  return [clip.start - clip.silenceHead, clip.start + clip.duration + clip.silenceTail];
}

function bind(control, {action, read, geometry, constraints, enabled, select, preview, commit, cancel, playhead}) {
  const moving = action === "move";
  let drag;
  const doc = control.ownerDocument;
  const editable = () => !control.disabled && (!enabled || enabled());
  const same = (a,b) => Object.keys(a).every(key => a[key] === b[key]);
  function finish(event, accept) {
    if (!drag || (event?.pointerId != null && drag.id !== event.pointerId)) return;
    const { original, proposed, id, length } = drag;
    drag.listeners.abort();
    playhead?.mark(false);
    drag = undefined;
    if (control.hasPointerCapture?.(id)) control.releasePointerCapture(id);
    if (!proposed || !control.isConnected) return;
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
    if (!editable() || drag || !["ArrowLeft","ArrowRight"].includes(event.key)) return;
    event.preventDefault();
    const limits = constraints(), rate = limits.rate;
    if (!moving && !rate) return;
    const step = moving ? (event.shiftKey ? 1 : .25) : (event.shiftKey ? Math.round(rate/100) : 1) / rate;
    const original = read();
    const next = change(original, action, event.key === "ArrowLeft" ? -step : step, limits);
    if (!same(original, next)) commit(next,{action,original,event});
  }
  function down(event) {
    if (event.button !== 0 || drag || !editable()) return;
    const {width,length} = geometry();
    if (!(width>0 && length>0)) return;
    event.preventDefault();
    control.focus({preventScroll:true});
    select?.(event);
    if (!control.isConnected || !editable()) return;
    const listeners = new AbortController();
    drag = {id:event.pointerId, mouse:event.pointerType === "mouse", x:event.clientX, original:read(), width,length,listeners};
    const options = {capture:true,signal:listeners.signal};
    // Mouse capture can move to the host while a clip is being pulled past the timeline.
    // Follow that one pointer until release, including a release outside its original button.
    doc.addEventListener("pointermove",move,options);
    doc.addEventListener("pointerup",up,options);
    doc.addEventListener("pointercancel",abort,options);
    control.addEventListener("lostpointercapture",lost,options);
    doc.defaultView.addEventListener("blur",blur,{signal:listeners.signal});
    doc.addEventListener("pointerout",leave,options);
    control.setPointerCapture(event.pointerId);
  }
  function move(event) {
    if (!drag || drag.id !== event.pointerId) return;
    if (!editable()) return finish(event,false);
    if (drag.mouse && !(event.buttons & 1) && event.type === "pointermove") return finish(event,true);
    const distance = event.clientX - drag.x;
    if (!drag.proposed && (moving ? Math.abs(distance) < 3 : distance === 0)) return;
    const secondsPerPixel = drag.length / drag.width;
    const seconds = distance * secondsPerPixel;
    const limits = constraints();
    const moveRate = limits.moveRate ?? 4;
    const {original} = drag;
    const sourceEdges = bounds(original);
    const edge = action === "tail" ? 1 : 0;
    const active = event.metaKey && playhead ? playhead.position() : null;
    let snapped = null;
    const exact = playheadDelta(seconds, moving ? sourceEdges : [sourceEdges[edge]], active, secondsPerPixel, delta => {
      const proposed = change(original, action, delta, limits);
      const expected = moving
        ? Math.abs(proposed.start - original.start - delta)
        : Math.abs(bounds(proposed)[edge] - active);
      if (expected > (moving ? 1e-7 : .5 / (limits.rate || 1))) return false;
      snapped = proposed;
      return true;
    });
    const delta = exact ?? (moving ? Math.round(seconds * moveRate) / moveRate : seconds);
    playhead?.mark(exact !== null);
    if (drag.delta === delta && drag.snapped === (exact !== null)) return;
    drag.delta = delta;
    drag.snapped = exact !== null;
    drag.proposed = snapped ?? change(original, action, delta, limits);
    preview?.(drag.proposed,{action,original:drag.original,length:drag.length,event});
  }
  function up(event) {
    // Commit the displayed preview even if mouseup arrives with old coordinates.
    if (!drag?.proposed) move(event);
    finish(event,true);
  }
  function lost(event) {
    if (!drag || drag.id !== event.pointerId) return;
    if (!drag.mouse || !(event.buttons & 1)) finish(event,drag.mouse);
    else drag.uncaptured = true;
  }
  function leave(event) {
    if (drag?.mouse && drag.uncaptured && event.relatedTarget === null) finish(event,true);
  }
  const blur = () => finish(null,!!drag?.mouse);
  // A native mouse handoff ends the gesture at its displayed position. Touch scrolling cancels it.
  const abort = event => finish(event,!!drag?.mouse);
  const listeners = {keydown,pointerdown:down};
  for (const [name,listener] of Object.entries(listeners)) control.addEventListener(name,listener);
  return () => {
    finish(null,false);
    for (const [name,listener] of Object.entries(listeners)) control.removeEventListener(name,listener);
  };
}

export const clipEditing = Object.freeze({change,bind,playheadDelta});
