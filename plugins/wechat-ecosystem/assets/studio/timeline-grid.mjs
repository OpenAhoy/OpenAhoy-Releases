// All ticks and divisions resolve to seconds on the same lane as the clips.
export function timelineGrid({ length, width, bpm, meter }) {
  const pixels = width / length;
  if (bpm > 0 && meter?.beats > 0 && meter?.note > 0) {
    const beat = 60 / bpm * 4 / meter.note;
    const bar = meter.beats * beat;
    const stride = Math.max(1, Math.ceil(41 / (bar * pixels)));
    const subdivisions = beat * pixels >= 70 ? 4 : beat * pixels >= 32 ? 2 : 1;
    const labels = [];
    for (let index = 0; index * bar < length; index += stride) {
      labels.push({ at: index * bar, label: String(index + 1) });
    }
    return {
      unit: "小节", labels, major: bar * pixels >= 9 ? bar : bar * stride,
      beat: beat * pixels >= 8 ? beat : 0,
      detail: subdivisions > 1 ? beat / subdivisions : 0,
    };
  }

  const step = [1, 2, 5, 10, 15, 30, 60, 120].find(seconds => seconds * pixels >= 44) ?? 120;
  const labels = [];
  for (let second = 0; second < length; second += step) {
    const minute = Math.floor(second / 60);
    labels.push({ at: second, label: minute + ":" + String(second % 60).padStart(2, "0") });
  }
  return { unit: "时间", labels, major: step, beat: step / 5 * pixels >= 9 ? step / 5 : 0, detail: 0 };
}


export function sampleGrid({ length, width, sampleRate }) {
  const end = length * sampleRate;
  const minimum = Math.max(1, 86 * end / width);
  const scale = 10 ** Math.floor(Math.log10(minimum));
  const steps = [1, 2, 5, 10].map(n => n * scale);
  let stride = steps.find(n => n >= minimum);
  if (width >= 120 && stride >= end) stride = steps.reverse().find(n => n < end) ?? stride;
  const major = stride / sampleRate;
  const labels = [];
  for (let sample = 0; sample < end; sample += stride) {
    labels.push({ at: sample / sampleRate, label: String(sample) });
  }
  const beat = stride >= 5 && major * width / length >= 50 ? major / 5 : 0;
  return { labels, major, beat, detail: 0 };
}
