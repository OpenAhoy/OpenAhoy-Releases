"""Read original media metadata and resolve the rate for a Studio music delivery."""
from functools import lru_cache
import json
from pathlib import Path
import subprocess

from .studio_apple_music import NATIVE_RATES as RATES, tool


@lru_cache(maxsize=256)
def probe(path, identity):
    try:
        output = subprocess.run([tool("ffprobe"), "-v", "error", "-protocol_whitelist", "file,pipe",
            "-format_whitelist", "wav,aiff,caf,mp3,aac,mov,flac,ogg",
            "-select_streams", "a:0", "-show_entries",
            "stream=sample_rate,codec_name,bits_per_raw_sample,bits_per_sample", "-of", "json",
            str(path)], timeout=10, check=True, text=True, capture_output=True)
        audio, = json.loads(output.stdout)["streams"]
        codec = audio["codec_name"]
        raw = audio.get("bits_per_raw_sample") or audio.get("bits_per_sample")
        bits = int(raw) if str(raw).isdigit() and int(raw) else None
        return dict(rate=int(audio["sample_rate"]), bits=bits, codec=codec)
    except (ValueError, TypeError, OSError, KeyError, subprocess.SubprocessError):
        return {}


def source_metadata(path):
    if path is None:
        return {}
    path = Path(path)
    try:
        if not path.is_file() or path.resolve() != path:
            return {}
        stat = path.stat()
        return probe(path, (stat.st_dev, stat.st_ino, stat.st_size, stat.st_mtime_ns))
    except OSError:
        return {}


def layout(project, song, version, resolve):
    sources = []
    for track in version["tracks"]:
        sources.append({"track":track["id"], **source_metadata(resolve(track["url"]))})
    rates = {item.get("rate") for item in sources}
    explicit = next((owner[k] for owner in (version, song, project)
                     for k in ("projectSampleRate", "sampleRate") if k in owner), None)
    if explicit is not None:
        choice = explicit if type(explicit) is int else 0
        mode = "project"
    elif len(rates) == 1 and None not in rates:
        choice = next(iter(rates))
        mode = "uniform_sources"
    else:
        choice = 0
        mode = "unknown_sources" if None in rates else "mixed_sources"
    return dict(rate=choice, basis=mode, sources=sources, supported=list(RATES))


def choose(layout, requested):
    value = layout["rate"]
    if value:
        if value not in RATES or (requested is not None and requested != value):
            raise ValueError("unsupported_native_rate")
        return value, layout["basis"]
    if layout["basis"] not in ("mixed_sources", "unknown_sources") or requested not in RATES:
        raise ValueError("choose_project_rate")
    return requested, "chosen_project_rate"
