"""Prepare a stereo PCM release and its Apple AAC audition on a macOS host."""

import json
import math
import os
import re
import shutil
import subprocess
import tempfile
from pathlib import Path


NATIVE_RATES = (44100, 48000, 88200, 96000, 176400, 192000)
DELIVERY_PROFILE = "pcm24-apple-aac-v1"


def tool(name):
    for prefix in ('/opt/homebrew/bin', '/usr/local/bin'):
        path = Path(prefix) / name
        if path.is_file() and os.access(path, os.X_OK):
            return str(path)
    path = shutil.which(name)
    if not path:
        raise FileNotFoundError(name)
    return path


def run(args):
    argv = [tool(args[0]), *args[1:]] if args[0] in ('ffmpeg', 'ffprobe') else args
    result = subprocess.run(argv, capture_output=True, text=True, timeout=600)
    if result.returncode:
        raise RuntimeError(f"{Path(args[0]).name} failed: {result.stderr[-500:]}")
    return result


def audio_format(file):
    streams = json.loads(run(["ffprobe", "-v", "error", "-show_entries",
        "stream=codec_name,sample_rate,channels,duration_ts,time_base", "-of", "json", file]).stdout)["streams"]
    if len(streams) != 1:
        raise ValueError("Expected one audio stream")
    return streams[0]


def check_clips(file, scratch):
    # afclip -q suppresses even the final totals and exits zero for clipped files.
    with tempfile.TemporaryFile(dir=scratch) as log:
        result = subprocess.run(["/usr/bin/afclip", "-x", file], stdout=log, stderr=subprocess.PIPE, timeout=600)
        if result.returncode:
            raise RuntimeError("afclip could not inspect the audio")
        log.seek(max(0, log.tell() - 2048))
        tail = log.read().decode(errors="replace")
    if "-- no samples clipped --" in tail:
        return {"on_sample": 0, "inter_sample": 0}
    rows = re.findall(r"(Left|Right)\s+on-sample:\s*(\d+)\s+inter-sample:\s*(\d+)", tail)
    if len(rows) != 2 or {row[0] for row in rows} != {"Left", "Right"}:
        raise RuntimeError("Unrecognized stereo afclip result")
    return {"on_sample": sum(int(row[1]) for row in rows), "inter_sample": sum(int(row[2]) for row in rows)}


def meter(file):
    log = run(["ffmpeg", "-hide_banner", "-nostdin", "-nostats", "-i", file, "-af",
               "ebur128=peak=true:framelog=verbose", "-f", "null", "-"]).stderr.rsplit("Summary:", 1)[-1]
    def read(name):
        match = re.search(r"^\s*" + name + r":\s*(-?[\d.]+|-inf)\s", log, re.M)
        if not match:
            raise RuntimeError("Incomplete loudness or peak measurement")
        return float(match.group(1))
    return {"integrated_lufs": read("I"), "true_peak_dbtp": read("Peak")}


def prepare_delivery(float_wav, new_wav, new_m4a):
    """Write two new artifacts after passing PCM and Apple-decoded AAC checks."""
    source, delivery, preview = map(Path, (float_wav, new_wav, new_m4a))
    if delivery.parent != preview.parent or delivery == preview or delivery.exists() or preview.exists():
        raise ValueError("Expected two new, distinct files in one output directory")
    stream = audio_format(source)
    rate, frames = int(stream["sample_rate"]), int(stream["duration_ts"])
    if (rate not in NATIVE_RATES or stream["codec_name"] != "pcm_f32le" or stream["channels"] != 2
            or frames < 1 or stream["time_base"] != f"1/{rate}"):
        raise ValueError("Expected a stereo floating-point mix at a supported native session rate")
    preview_rate = min(rate, 48000)
    with tempfile.TemporaryDirectory(dir=delivery.parent, prefix="apple-music-") as tmp:
        work = Path(tmp)
        initial = meter(source)["true_peak_dbtp"]
        if not math.isfinite(initial):
            raise ValueError("The rendered master has no measurable programme")
        gain = min(0.0, -initial - 0.2) if initial >= 0 else 0.0
        for attempt in range(1, 6):
            step = work / str(attempt)
            step.mkdir()
            wav, caf, aac, decoded = (step / name for name in ("master.wav", "encode.caf", "preview.m4a", "decoded.wav"))
            adjusted = source
            if gain:
                adjusted = step / "adjusted.wav"
                run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-nostdin", "-i", source,
                     "-af", f"volume={gain:.3f}dB:precision=double", "-c:a", "pcm_f32le", adjusted])
            run(["/usr/bin/afconvert", adjusted, wav, "-d", "LEI24", "-f", "WAVE", "--dither", "1"])
            actual = audio_format(wav)
            if (actual["codec_name"], actual["channels"], actual["sample_rate"], actual["time_base"],
                    int(actual["duration_ts"])) != ("pcm_s24le", 2, str(rate), f"1/{rate}", frames):
                raise RuntimeError("Delivery PCM format or sample count changed")
            src = ["-d", "0"] if rate == preview_rate else ["-d", f"LEF32@{preview_rate}", "--src-complexity", "bats", "-r", "127"]
            run(["/usr/bin/afconvert", wav, caf, "-f", "caff", "--soundcheck-generate", *src])
            run(["/usr/bin/afconvert", caf, aac, "-d", "aac", "-f", "m4af", "-u", "pgcm", "2",
                 "--soundcheck-read", "-b", "256000", "-q", "127", "-s", "2"])
            run(["/usr/bin/afconvert", aac, decoded, "-d", "LEF32", "-f", "WAVE"])
            decoded_info = audio_format(decoded)
            decoded_frames = int(decoded_info["duration_ts"])
            if (int(decoded_info["sample_rate"]) != preview_rate or decoded_info["channels"] != 2
                    or decoded_info["time_base"] != f"1/{preview_rate}"
                    or abs(decoded_frames - frames * preview_rate / rate) > 1):
                raise RuntimeError("AAC audition duration or format changed")
            pcm_clips, aac_clips = check_clips(wav, step), check_clips(decoded, step)
            pcm_meter, aac_meter = meter(wav), meter(decoded)
            if not any((*pcm_clips.values(), *aac_clips.values())):
                os.link(wav, delivery)
                try:
                    os.link(aac, preview)
                except OSError:
                    delivery.unlink()
                    raise
                return {"profile": DELIVERY_PROFILE, "sample_rate": rate, "bit_depth": 24, "channels": 2,
                        "frames": frames, "preview_rate": preview_rate, "aac_target_kbps": 256,
                        "gain_trim_db": round(gain, 3), "attempts": attempt,
                        "pcm": pcm_meter | pcm_clips, "aac": aac_meter | aac_clips}
            # Apple and EBU use different reconstruction filters. If the Apple
            # check still finds overs, increase headroom even when EBU reads zero.
            gain -= max(0.25 * attempt, 0.25 + max(pcm_meter["true_peak_dbtp"], aac_meter["true_peak_dbtp"]))
        raise RuntimeError("PCM or AAC still clips after adjusting the master")
