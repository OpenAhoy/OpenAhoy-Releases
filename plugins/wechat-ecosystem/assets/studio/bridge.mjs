let call;

export function connectStudio(callTool) {
  call = callTool;
}

function response(value) {
  return new Response(JSON.stringify(value), {
    status: value?.status ?? 200,
    headers: { "Content-Type": "application/json" },
  });
}

function base64Bytes(value) {
  if (typeof Uint8Array.fromBase64 === "function") return Uint8Array.fromBase64(value);
  const binary = atob(value);
  const result = new Uint8Array(binary.length);
  for (let i = 0; i < binary.length; i++) result[i] = binary.charCodeAt(i);
  return result;
}

async function sourceBytes(part, signal) {
  const bytes = base64Bytes(part.bytes);
  if (!Number.isSafeInteger(part.offset) || !Number.isSafeInteger(part.size) || part.size < 1 || part.size > 768 * 1024)
    throw Error("音轨分片大小无效");
  if (part.coding === "identity" && bytes.length === part.size) return bytes;
  if (part.coding !== "deflate") throw Error("音轨分片编码无效");
  const reader = new Blob([bytes]).stream().pipeThrough(new DecompressionStream("deflate")).getReader();
  const output = new Uint8Array(part.size);
  let offset = 0;
  try {
    for (;;) {
      signal?.throwIfAborted();
      const { done, value } = await reader.read();
      if (done) break;
      output.set(value, offset);
      offset += value.length;
    }
  } finally {
    await reader.cancel().catch(() => {});
    reader.releaseLock();
  }
  if (offset !== output.length) throw Error("音轨分片大小无效");
  return output;
}

function file(args, signal) {
  return mediaResponse(offset => call({ action: "media", ...args, offset }), signal);
}

function sourceFile(args, signal) {
  const coding = typeof DecompressionStream === "function" ? "deflate" : "identity";
  return mediaResponse(offset => call({ action: "source_chunk", ...args, offset, coding }),
    signal, undefined, sourceBytes);
}

export async function mediaResponse(read, signal, expectedHash, decode = part => base64Bytes(part.bytes ?? part.data)) {
  let offset = 0, total, type, hash;
  const parts = [];
  do {
    signal?.throwIfAborted();
    const part = await read(offset);
    signal?.throwIfAborted();
    if (part.error) return response(part);
    if (offset === 0) {
      ({ total, mime: type, sha256: hash } = part);
      if (!Number.isSafeInteger(total) || total < 1 || total > 1024 * 1024 * 1024) throw Error("音频文件大小无效");
    }
    if (expectedHash && part.sha256 !== expectedHash) throw Error("音源已变化");
    const bytes = await decode(part, signal);
    signal?.throwIfAborted();
    if (!bytes.length || part.total !== total || (part.offset !== undefined && part.offset !== offset) || hash !== part.sha256 ||
        offset + bytes.length > total) throw Error("音频文件已变化");
    offset += bytes.length;
    parts.push(bytes);
  } while (offset < total);
  return new Response(new Blob(parts, { type }));
}

export async function studioWaveform(path, signal) {
  const [, mode, project, song, version, asset, extra] = new URL(path, "https://studio.internal").pathname.split("/");
  if (mode !== "source" || !project || !song || !version || !asset || extra) return null;
  signal.throwIfAborted();
  const preview = await call({ action: "source_waveform", project, song, version, asset });
  signal.throwIfAborted();
  return preview.available ? preview : null;
}

export async function studioFetch(path, options = {}) {
  const url = new URL(path, "https://studio.internal");
  const args = Object.fromEntries(url.searchParams);
  switch (url.pathname) {
    case "/catalog":
      return response((await call({ action: "catalog" })).projects);
    case "/draft":
      return response(await call(options.method === "POST"
        ? { action: "save_draft", ...args, draft: JSON.parse(options.body) }
        : { action: "draft", ...args }));
    case "/master-adopt":
      return response(await call({ action: "adopt", ...JSON.parse(options.body) }));
  }
  const [, mode, project, song, version, first, second, extra] = url.pathname.split("/");
  if (!song && mode === "project-cover" && project)
    return file({ action: "project_cover", project }, options.signal);
  if (!first && mode === "cover" && project && song && version)
    return file({ action: "cover", project, song, version }, options.signal);
  if (!second && mode === "song-preview" && project && song && version && first)
    return file({ action: "song_preview", project, song, version, asset: first }, options.signal);
  if (!extra && mode === "monitor-file" && project && song && version && first && second)
    return file({ action: "monitor_media", project, song, version, analysis: first, asset: second }, options.signal);
  if (!second && project && song && version && first) {
    const lookup = { project, song, version, asset: first };
    if (mode === "source") return sourceFile(lookup, options.signal);
    if (mode === "master-file") return file(lookup, options.signal);
  }
  return response({ error: "studio_action_unavailable", status: 404 });
}

export async function studioAction(args) {
  const result = await call(args);
  if (result.error) throw Object.assign(Error(result.error), { status: result.status });
  return result;
}

export async function studioCover(source, signal) {
  if (!source.startsWith("/cover/") && !source.startsWith("/project-cover/")) return null;
  const reply = await studioFetch(source, { signal });
  if (!reply.ok) return null;
  const blob = await reply.blob();
  if (signal.aborted) return null;
  return URL.createObjectURL(blob);
}
