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

function file(args, signal) {
  return mediaResponse(offset => call({ action: "media", ...args, offset }), signal);
}

export async function mediaResponse(read, signal, expectedHash) {
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
    const bytes = Uint8Array.from(atob(part.bytes ?? part.data), item => item.charCodeAt(0));
    if (!bytes.length || part.total !== total || (part.offset !== undefined && part.offset !== offset) || hash !== part.sha256 ||
        offset + bytes.length > total) throw Error("音频文件已变化");
    offset += bytes.length;
    parts.push(bytes);
  } while (offset < total);
  return new Response(new Blob(parts, { type }));
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
  if (!second && (mode === "source" || mode === "master-file") && project && song && version && first)
    return file({ project, song, version, asset: first }, options.signal);
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
