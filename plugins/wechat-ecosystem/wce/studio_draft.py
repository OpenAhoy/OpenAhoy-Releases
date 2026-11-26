"""Validation and revision locking for Studio timeline edits."""
import math

from .own_connection_policy import atomic_write, locked
from .studio_projects import StudioError, digest, read_json

MIN_CLIP = 1 / 48000
TIME_EPSILON = 1e-9


def read_draft(folder, key):
    data = read_json(folder / ("draft-" + digest(key) + ".json"), None)
    if data is None:
        return dict(revision=0, offsets={}, trims={}, padding={}, seconds=0, zoom=1, scroll=0)
    return data


def save(folder, key, version, value):
    def number(field, low, high):
        return type(field) in (int, float) and math.isfinite(field) and low <= field <= high

    tracks = {track["id"]: track for track in version["tracks"]}
    timeline_limit = version.get("timelineLimit", 180)
    start_limit = version.get("timelineLimit", 120)
    offsets = value["offsets"]
    trims = value.get("trims", {})
    padding = value.get("padding", {})
    splits = value.get("splits", {})
    undo = value.get("cutUndo", {})
    if (type(value["revision"]) is not int or type(offsets) is not dict
            or not offsets.keys() <= tracks.keys() or any(not number(n, 0, start_limit) for n in offsets.values())
            or type(trims) is not dict or not trims.keys() <= tracks.keys()
            or type(padding) is not dict or not padding.keys() <= tracks.keys()
            or not number(value["seconds"], 0, timeline_limit) or value["zoom"] not in (1, 2, 4)
            or not number(value["scroll"], 0, 32768)):
        raise ValueError("Invalid studio draft")
    for track_id, trim in trims.items():
        duration = tracks[track_id]["duration"]
        if (type(trim) is not dict or trim.keys() != {"head", "tail"}
                or any(not number(seconds, 0, duration) for seconds in trim.values())
                or duration - trim["head"] - trim["tail"] < MIN_CLIP - TIME_EPSILON):
            raise ValueError("Invalid studio trim")
    for track_id, silence in padding.items():
        track = tracks[track_id]
        if (type(silence) is not dict or silence.keys() != {"head", "tail"}
                or any(not number(seconds, 0, timeline_limit) for seconds in silence.values())):
            raise ValueError("Invalid studio silence")
        start = offsets.get(track_id, track["start"])
        trim = trims.get(track_id, {})
        duration = track["duration"] - trim.get("head", 0) - trim.get("tail", 0)
        if silence["head"] > start or start + duration + silence["tail"] > timeline_limit:
            raise ValueError("Studio silence outside timeline")

    if (type(splits) is not dict or not splits.keys() <= tracks.keys()
            or type(undo) is not dict or not undo.keys() <= splits.keys()):
        raise ValueError("Invalid track splits")

    def check_parts(track_id, parts, old):
        if type(parts) is not list or len(parts) > 3000:
            raise ValueError("Invalid track parts")
        track = tracks[track_id]
        previous_end = 0
        for part in parts:
            if (type(part) is not dict or part.keys() !=
                    {"start", "sourceIn", "duration", "head", "tail", "silenceHead", "silenceTail"}
                    or not number(part["start"], 0, timeline_limit)
                    or not number(part["duration"], .000001, track["duration"] + 1e-6)
                    or not number(part["sourceIn"], 0, track["sourceIn"] + track["duration"] + 1e-6)
                    or any(not number(part[edge], 0, track["duration"]) for edge in ("head", "tail"))
                    or part["silenceHead"] != 0 or part["silenceTail"] != 0):
                raise ValueError("Invalid track part")
            if part["duration"] < MIN_CLIP - TIME_EPSILON:
                # Existing sub-sample split rows can be echoed or restored by an older undo.
                if not any(part in (old.get(field, {}).get(track_id) or ()) for field in ("splits", "cutUndo")):
                    raise ValueError("Track part shorter than one sample")
            end = part["start"] + part["duration"]
            source_start = part["sourceIn"] - part["head"]
            source_end = part["sourceIn"] + part["duration"] + part["tail"]
            if (part["start"] + 1e-6 < previous_end or end > timeline_limit + 1e-6
                    or source_start < track["sourceIn"] - 1e-6
                    or source_end > track["sourceIn"] + track["duration"] + 1e-6):
                raise ValueError("Track part outside bounds")
            previous_end = end

    with locked(folder / "state.lock"):
        current = read_draft(folder, key)
        if value["revision"] != current["revision"] or current.get("splits") and "splits" not in value:
            raise StudioError("draft_changed", 409)
        for track_id, parts in splits.items():
            check_parts(track_id, parts, current)
        for track_id, parts in undo.items():
            if parts is not None:
                check_parts(track_id, parts, current)
        candidate = {name: value[name] for name in ("offsets", "seconds", "zoom", "scroll")}
        candidate["trims"] = trims
        candidate["padding"] = padding
        if splits:
            candidate["splits"] = splits
        if undo:
            candidate["cutUndo"] = undo
        candidate["revision"] = current["revision"] + 1
        atomic_write(folder / ("draft-" + digest(key) + ".json"), candidate, maximum=2 * 1024 * 1024)
        return candidate
