"""Momentary feedback for app-owned actions. Activation belongs to each control."""

STYLE = """
:root {
  --jiu-pressure: inset 0 2px 5px rgb(25 23 21 / 32%), inset 0 0 0 1px rgb(100 94 87 / 30%),
                  inset 0 -1px 1px rgb(255 255 255 / 40%);
}
:where(button, summary, a[href], input:is([type=button],[type=submit],[type=reset]),
       [role=button], [role=option], [role=tab], [role=switch], [role=menuitem]) {
  transition: box-shadow 110ms ease-out;
}
[data-jiu-pressed]:not(:where(:disabled,[aria-disabled=true],[aria-busy=true],
    lus-studio > [slot=imw-video] *,lus-studio > [slot=imw-timeline] *,.ob-platform-entry)) {
  box-shadow: var(--jiu-pressure) !important;
}
.ob-workspace-column:has(.ob-platform-entry[data-jiu-pressed]) {
  box-shadow: var(--jiu-pressure) !important;
}
@media (prefers-reduced-motion: reduce) {
  :where(button,summary,a[href],input,[role=button],[role=option],[role=tab],[role=switch],[role=menuitem],
         .ob-workspace-column) { transition-duration: 0s !important; }
}
@media (forced-colors: active) {
  [data-jiu-pressed]:not(:disabled) { outline: 2px dashed Highlight; outline-offset:-3px; }
}
"""

# The immutable document preview forbids scripts. Its own summaries are siblings
# of the submitted article content, so no selector enters the author's markup.
PREVIEW_STYLE = """
body > main > details > summary {transition:box-shadow 110ms ease-out}
body > main > details > summary:active {box-shadow:inset 0 2px 5px #24262055}
body > main > details > summary:focus-visible {outline:2px solid currentColor;outline-offset:-2px}
@media(prefers-reduced-motion:reduce){body > main > details > summary{transition:none}}
"""

SCRIPT = r"""
;(() => {
  const action = 'button,summary,a[href],input:is([type=button],[type=submit],[type=reset],[type=checkbox],[type=radio]),[role=button],[role=link],[role=tab],[role=switch],[role=checkbox],[role=radio],[role=option],[role=menuitem],[role=menuitemradio],[role=menuitemcheckbox]';
  const input = 'input,textarea,select,[contenteditable]:not([contenteditable=false]),video[controls],audio[controls],[role=slider]';
  const mark = 'data-jiu-pressed';
  let held = null;

  function target(event) {
    const path = event.composedPath().filter(node => node instanceof Element);
    if (path.some(node => node.matches('[inert],:disabled,[aria-disabled=true]') || node.isContentEditable)) return null;
    for (const node of path) {
      if (node.matches(action)) return node;
      // Label text activates the associated checkable input on release.
      if (node instanceof HTMLLabelElement && node.control?.matches('input:is([type=checkbox],[type=radio])')) {
        return node.control.matches(':disabled,[aria-disabled=true]') ? null : node.control;
      }
      // The song list also selects the song when its card's metadata is clicked.
      if (node.matches('article.lh-card.embedded-song[data-song]')) return node;
      if (node.matches(input)) return null;
    }
    return null;
  }

  function clear() {
    if (held) held.node.removeAttribute(mark);
    held = null;
  }

  function press(node, source) {
    clear();
    held = {node, ...source};
    node.setAttribute(mark, '');
  }

  const observe = {capture:true, passive:true};
  document.addEventListener('pointerdown', event => {
    if (!event.isPrimary || event.button !== 0) return;
    clear();
    const node = target(event);
    if (node) press(node, {id:event.pointerId, x:event.clientX, y:event.clientY});
  }, observe);
  document.addEventListener('pointermove', event => {
    if (!held || held.id !== event.pointerId) return;
    if (event.pointerType !== 'mouse' && Math.hypot(event.clientX-held.x, event.clientY-held.y) > 10) clear();
    else if (event.pointerType === 'mouse' && target(event) !== held.node) clear();
  }, observe);
  for (const name of ['pointerup','pointercancel','lostpointercapture','pointerout']) {
    window.addEventListener(name, event => {
      if (held && held.id === event.pointerId && (name !== 'pointerout' || !event.relatedTarget)) clear();
    }, observe);
  }
  document.addEventListener('keydown', event => {
    if (event.repeat || event.isComposing || event.altKey || event.ctrlKey || event.metaKey ||
        (event.key !== 'Enter' && event.key !== ' ')) return;
    const node = target(event);
    if (!node || (event.key === ' ' && node.matches('a[href],[role=link]'))) return;
    press(node, {key:event.key});
  }, observe);
  window.addEventListener('keyup', event => { if (held && held.key === event.key) clear(); }, observe);
  document.addEventListener('focusout', event => {
    if (held && held.key && event.composedPath().includes(held.node)) clear();
  }, observe);
  window.addEventListener('blur', clear);
  window.addEventListener('pagehide', clear);
  document.addEventListener('visibilitychange', () => { if (document.hidden) clear(); });
})();
"""
