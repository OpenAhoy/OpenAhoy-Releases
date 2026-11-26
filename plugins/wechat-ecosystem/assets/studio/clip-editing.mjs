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

function bind(control, {action, read, geometry, constraints, enabled, select, preview, commit, cancel}) {
  const moving = action === "move";
  let drag;
  const editable = () => !control.disabled && (!enabled || enabled());
  const same = (a,b) => Object.keys(a).every(key => a[key] === b[key]);
  function finish(event, accept) {
    if (!drag || (event?.pointerId != null && drag.id !== event.pointerId)) return;
    const { original, proposed, id, length } = drag;
    drag = undefined;
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
    select?.(event);
    drag = { id:event.pointerId, x:event.clientX, original:read(), width,length };
    control.setPointerCapture(event.pointerId);
  }
  function move(event) {
    if (!drag || drag.id !== event.pointerId) return;
    if (!editable()) return finish(event,false);
    const distance = event.clientX - drag.x;
    if (!drag.proposed && (moving ? Math.abs(distance) < 3 : distance === 0)) return;
    const seconds = distance/drag.width*drag.length;
    const delta = moving ? Math.round(seconds*4)/4 : seconds;
    if (drag.delta === delta) return;
    drag.delta = delta;
    drag.proposed = change(drag.original,action,delta,constraints());
    preview?.(drag.proposed,{action,original:drag.original,length:drag.length,event});
  }
  function up(event) {
    move(event);
    finish(event,true);
  }
  const abort = event => finish(event,false);
  const listeners = {keydown,pointerdown:down,pointermove:move,pointerup:up,pointercancel:abort,lostpointercapture:abort};
  for (const [name,listener] of Object.entries(listeners)) control.addEventListener(name,listener);
  return () => {
    finish(null,false);
    for (const [name,listener] of Object.entries(listeners)) control.removeEventListener(name,listener);
  };
}

export const clipEditing = Object.freeze({change,bind});
