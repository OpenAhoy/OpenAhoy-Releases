const blockSize = 128;

// Whole blocks can be combined exactly for extrema and at full precision for RMS.
export function buildWaveIndex(channels) {
  const frames = channels[0].length;
  const blocks = Math.ceil(frames / blockSize);
  const lows = new Float32Array(blocks);
  const highs = new Float32Array(blocks);
  const energy = new Float64Array(blocks);
  for (let block = 0; block < blocks; block++) {
    const from = block * blockSize;
    const to = Math.min(frames, from + blockSize);
    let low = Infinity;
    let high = -Infinity;
    let squares = 0;
    for (const samples of channels) {
      for (let frame = from; frame < to; frame++) {
        const value = samples[frame];
        if (value < low) low = value;
        if (value > high) high = value;
        squares += value * value;
      }
    }
    lows[block] = low;
    highs[block] = high;
    energy[block] = squares;
  }
  return { lows, highs, energy };
}

// Half-open frame bins partition the visible PCM without skipping a sample.
export function wavePeaks(channels, start, visible, width, rms, index) {
  const result = new Float32Array(width * 2);
  const frames = channels[0].length;
  for (let x = 0; x < width; x++) {
    const from = Math.max(0, Math.floor(start + x * visible / width));
    const to = Math.min(frames, Math.max(from + 1, Math.floor(start + (x + 1) * visible / width)));
    let min = Infinity;
    let max = -Infinity;
    let squares = 0;
    const first = index ? Math.ceil(from / blockSize) : 0;
    const last = index ? Math.floor(to / blockSize) : 0;
    const leftEnd = first < last ? first * blockSize : to;
    const rightStart = first < last ? last * blockSize : to;
    for (let block = first; block < last; block++) {
      min = Math.min(min, index.lows[block]);
      max = Math.max(max, index.highs[block]);
      if (rms) squares += index.energy[block];
    }
    for (const samples of channels) {
      for (let frame = from; frame < leftEnd; frame++) {
        const value = samples[frame];
        if (value < min) min = value;
        if (value > max) max = value;
        if (rms) squares += value * value;
      }
      for (let frame = rightStart; frame < to; frame++) {
        const value = samples[frame];
        if (value < min) min = value;
        if (value > max) max = value;
        if (rms) squares += value * value;
      }
    }
    if (from < to) {
      result[x * 2] = min;
      result[x * 2 + 1] = max;
      if (rms) rms[x] = Math.sqrt(squares / ((to - from) * channels.length));
    }
  }
  return result;
}

// A gap must be quiet in every channel for at least 120 ms.
export function cutQuietRanges(channels, sampleRate, sourceIn, duration, index) {
  const first = Math.round(sourceIn * sampleRate);
  const last = Math.min(channels[0].length, Math.round((sourceIn + duration) * sampleRate));
  const span = last - first;
  if (span <= 0) return { ranges: [[0, duration]], count: 0 };
  const windowSize = Math.round(.02 * sampleRate);
  const alignedStart = Math.min(last, Math.ceil(first / windowSize) * windowSize);
  const alignedEnd = Math.max(alignedStart, Math.floor(last / windowSize) * windowSize);
  const windows = Math.floor((alignedEnd - alignedStart) / windowSize);
  const threshold = 10 ** (-48 / 20);
  const minimumFrames = Math.ceil(.12 * sampleRate);
  const ranges = [];
  let retained = first;
  let quietStart = null;
  let count = 0;
  const endQuiet = end => {
    if (quietStart !== null && end - quietStart >= minimumFrames) {
      if (quietStart > retained) ranges.push([(retained - first) / sampleRate, (quietStart - first) / sampleRate]);
      retained = end;
      count++;
    }
    quietStart = null;
  };
  const inspect = (low, high, at) => {
    if (Math.max(-low, high) < threshold) quietStart ??= at;
    else endQuiet(at);
  };
  if (alignedStart > first) {
    const edge = wavePeaks(channels, first, alignedStart - first, 1, undefined, index);
    inspect(edge[0], edge[1], first);
  }
  if (windows) {
    const peaks = wavePeaks(channels, alignedStart, windows * windowSize, windows, undefined, index);
    for (let window = 0; window < windows; window++) {
      inspect(peaks[2 * window], peaks[2 * window + 1], alignedStart + window * windowSize);
    }
  }
  if (last > alignedEnd) {
    const edge = wavePeaks(channels, alignedEnd, last - alignedEnd, 1, undefined, index);
    inspect(edge[0], edge[1], alignedEnd);
  }
  endQuiet(last);
  if (retained < last) ranges.push([(retained - first) / sampleRate, duration]);
  return { ranges, count };
}
