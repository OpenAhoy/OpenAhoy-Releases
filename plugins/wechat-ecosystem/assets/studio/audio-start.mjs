// A successful resume() reports policy/state, not whether samples are moving.
export async function confirmOutput(context, destination, player, signal, budget) {
  const wallStart = performance.now();
  const audioStart = context.currentTime;
  const mediaStart = player?.currentTime ?? 0;
  const minimum = 256 / context.sampleRate;
  const prime = context.createBufferSource();
  prime.buffer = context.createBuffer(1, Math.ceil(context.sampleRate * .1), context.sampleRate);
  prime.connect(destination);
  let rejection;
  let started = false;
  try {
    void context.resume().catch(error => { rejection = error; });
    if (player) void player.play().catch(error => { rejection = error; });
    // A brief zero-filled buffer establishes an output render pass without
    // scheduling project media or changing the user's audio device.
    prime.start(audioStart);
    started = true;
    while (!signal.aborted) {
      if (rejection) throw rejection;
      const rendered = context.state === "running" && context.currentTime - audioStart >= minimum;
      const delivered = !player || (!player.paused && player.currentTime > mediaStart);
      if (rendered && delivered) return true;
      if (context.state === "closed" || performance.now() - wallStart >= budget) return false;
      await new Promise(resolve => setTimeout(resolve, 24));
    }
    return false;
  } finally {
    if (started) prime.stop();
    prime.disconnect();
  }
}
