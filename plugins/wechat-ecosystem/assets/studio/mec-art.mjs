// Original, self-contained default project artwork. No catalog-wide asset reads.
export function projectArtwork(key) {
  let seed=2166136261;
  for(const char of String(key))seed=Math.imul(seed^char.charCodeAt(0),16777619)>>>0;
  const palettes=[['#eef7fb','#c7e5f2','#4c9fc4'],['#f0f6f3','#cee4da','#59a18e'],['#fbf5ed','#eddcc0','#b58c52'],['#f4f5f8','#d5dce8','#788dad'],['#f8f1f1','#ecd5d4','#b77d81'],['#eef6f6','#c5e3e1','#529b9f']];
  const [paper,tint,ink]=palettes[seed%palettes.length];
  const id='art'+seed.toString(16),turn=(seed%70)-35;
  return `<svg viewBox="0 0 600 360" xmlns="http://www.w3.org/2000/svg" aria-hidden="true" focusable="false">
  <defs><linearGradient id="${id}bg" x2="1" y2="1"><stop stop-color="${paper}"/><stop offset="1" stop-color="${tint}"/></linearGradient><radialGradient id="${id}disc" cx=".32" cy=".23" r=".8"><stop stop-color="#fff"/><stop offset=".38" stop-color="${tint}"/><stop offset=".7" stop-color="${ink}" stop-opacity=".6"/><stop offset="1" stop-color="${paper}"/></radialGradient><linearGradient id="${id}ribbon" x2="0" y2="1"><stop stop-color="#fff"/><stop offset=".55" stop-color="${tint}"/><stop offset="1" stop-color="${ink}"/></linearGradient></defs>
  <rect width="600" height="360" fill="url(#${id}bg)"/>
  <g fill="none" stroke="${ink}" stroke-opacity=".12">${[0,1,2,3,4].map(i=>`<path d="M-40 ${155+i*16} Q125 ${35+i*18} 305 ${167+i*13} T650 ${110+i*19}"/>`).join('')}</g>
  <ellipse cx="316" cy="295" rx="132" ry="16" fill="${ink}" opacity=".12"/>
  <g transform="translate(302 171) rotate(${turn})"><circle r="108" fill="url(#${id}disc)" stroke="#fff" stroke-opacity=".8" stroke-width="2"/>
  ${[93,80,67,54].map(r=>`<circle r="${r}" fill="none" stroke="#fff" stroke-opacity=".36" stroke-width="1.3"/>`).join('')}
  <circle r="30" fill="${paper}" stroke="#fff" stroke-width="2"/><circle r="7" fill="${ink}" opacity=".55"/>
  <path d="M-146 64 C-72 110 72 -120 152 -48" fill="none" stroke="${ink}" stroke-opacity=".2" stroke-width="25"/>
  <path d="M-146 56 C-72 102 72 -128 152 -56" fill="none" stroke="url(#${id}ribbon)" stroke-width="24"/>
  <path d="M-146 47 C-72 93 72 -137 152 -65" fill="none" stroke="#fff" stroke-opacity=".9" stroke-width="2"/></g>
  <g fill="${ink}" opacity=".48"><circle cx="104" cy="99" r="3"/><circle cx="491" cy="242" r="3"/><path d="M481 79v15m-7-7h14" stroke="${ink}" stroke-width="1.6"/></g>
  </svg>`;
}
