// Use the panel and original track elements on one document timeline; reversal starts at the painted geometry.
export function mountVideoDisclosure(studio) {
  const panel = studio.$("imw-screen"), regions = studio.$("regions");
  const reduce = matchMedia("(prefers-reduced-motion: reduce)");
  const timing = {duration:320, easing:"cubic-bezier(.32,0,.2,1)", fill:"both"};
  let animation = null, trackAnimations = [], before = new Map();
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
    before = new Map([...pictureRows,...studio.shadowRoot.querySelectorAll("[data-track-row]")].map(el=>[el,el.getBoundingClientRect().height]));
    reset();
    return height;
  }
  function animateHeight(el, start, end) {
    trackAnimations.push(el.animate([{height:start+"px"},{height:end+"px"}],timing));
  }
  function animateTracks(direction) {
    const opened = studio.hasAttribute("data-imw-video");
    if (!opened) return;
    const closing = direction === "closing";
    for (const el of pictureRows) {
      const current = el.getBoundingClientRect().height;
      const end = closing ? parseFloat(getComputedStyle(el).getPropertyValue("--track-height")) / 2 : current;
      animateHeight(el,before.get(el) ?? current,end);
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
      heads.push([head, before.get(head) ?? head.getBoundingClientRect().height,
        closing ? normal + expanded : head.hasAttribute("data-imw-current") ? normal : 0]);
    }
    const tracks = heights => ({
      height:heights.reduce((sum,value)=>sum+value,0)+"px",
      gridTemplateRows:heights.map(value=>value+"px").join(" "),
    });
    studio.setAttribute("data-imw-track-motion","");
    trackAnimations.push(regions.animate([tracks(start),tracks(end)],timing));
    for (const [el,from,to] of heads) animateHeight(el,from,to);
    if (studio.hasAttribute("data-imw-dense")) {
      const normal = parseFloat(getComputedStyle(rows[0]).getPropertyValue("--track-height"));
      const compact = normal / rows.length;
      const visibility = Math.max(0,Math.min(1,(start[0]-compact)/(normal-compact)));
      const target = closing ? 1 : 0;
      for (const canvas of regions.querySelectorAll(".clip:not(:disabled) canvas")) {
        const tone = getComputedStyle(canvas).color;
        const background = wave => `color-mix(in srgb,${tone} ${(1-wave)*100}%,transparent)`;
        trackAnimations.push(canvas.animate([{opacity:visibility},{opacity:target}],timing));
        trackAnimations.push(canvas.closest(".clip").animate([
          {backgroundColor:background(visibility)},{backgroundColor:background(target)},
        ],timing));
      }
      studio.paint(normal);
    }
  }
  function move(from, to, direction) {
    if (reduce.matches || typeof panel.animate !== "function" || Math.abs(to-from) < 1) return Promise.resolve(true);
    studio.dataset.imwMotion = direction;
    studio.style.setProperty("--imw-reveal-height",Math.max(from,to)+"px");
    const keyframe = height => ({flexGrow:0, flexShrink:0, flexBasis:height+"px", minHeight:"0px", height:height+"px"});
    const run = panel.animate([keyframe(from),keyframe(to)],timing);
    animation = run;
    animateTracks(direction);
    const instant = document.timeline.currentTime;
    if (instant !== null) for (const step of [run,...trackAnimations]) step.startTime = instant;
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
    takeHeight, reset,
    reveal(from) { return move(from,panel.getBoundingClientRect().height,"opening"); },
    collapse() { return move(takeHeight(),0,"closing"); },
    reversing() { return studio.dataset.imwMotion === "closing"; },
  };
}
