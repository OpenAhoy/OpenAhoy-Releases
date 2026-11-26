const anchorHues = [0, 32, 53, 130, 225, 275];
const weights = [.2126, .7152, .0722];
const minimumBrightness = .24;

function luminance(rgb) {
  return rgb.reduce((total, channel, i) => {
    const value = channel / 255;
    const light = value <= .04045 ? value / 12.92 : ((value + .055) / 1.055) ** 2.4;
    return total + light * weights[i];
  }, 0);
}

function vividColor(hue) {
  // Start at full hue and raise the two darker channels only as far as needed.
  const fullColor = [5, 3, 1].map(offset => {
    const sector = (offset + hue / 60) % 6;
    return 255 * (1 - Math.max(0, Math.min(sector, 4 - sector, 1)));
  });
  const rgbAt = lift => fullColor.map(channel => Math.round(channel + (255 - channel) * lift / 255));
  let low = 0;
  let high = 255;
  while (low < high) {
    const lift = Math.floor((low + high) / 2);
    if (luminance(rgbAt(lift)) >= minimumBrightness) high = lift;
    else low = lift + 1;
  }
  return "#" + rgbAt(low).map(channel => channel.toString(16).padStart(2, "0")).join("");
}

// A 137° step spreads neighboring slots across the wheel before filling intermediate hues.
const remainingHues = Array.from({ length: 360 }, (_, i) => i * 137 % 360)
  .filter(hue => !anchorHues.includes(hue));
const palette = [...anchorHues, ...remainingHues].map(vividColor);

export function trackColor(slot) {
  return palette[slot % palette.length];
}

export function trackColorSlots(tracks, saved) {
  const slots = new Map();
  const used = new Set();
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
