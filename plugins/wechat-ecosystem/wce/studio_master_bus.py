"""Pinned native Stereo Out analysis, monitoring and Apple AAC/PCM delivery."""
from functools import lru_cache
from hashlib import file_digest
import json
import math
import shutil
from pathlib import Path
import subprocess
from tempfile import TemporaryDirectory

from . import studio_apple_music as apple
from .bounded_file import file_state
from .own_connection_policy import atomic_write, locked
from .studio_draft import read_draft
from .studio_projects import StudioError, digest, media_pin, read_json, require
from .studio_rates import choose

NATIVE = Path(__file__).resolve().parents[1] / 'native' / 'output-master'
RENDERER = NATIVE / 'render'
COMPONENT = NATIVE / 'Output Master.component'
BINARY = COMPONENT / 'Contents' / 'MacOS' / 'OutputMaster'
MEDIA = {'wav': 'master.wav', 'aac': 'audition.m4a', 'bypass': 'bypass.m4a'}
MONITOR = {'wet': 'wet.m4a', 'bypass': 'bypass.m4a'}
LABELS = ('Character', 'Auto EQ', '目标响度', '声场宽度', 'Excite', '低频增益', '中频增益', '高频增益',
          '低频中心', '中频中心', '高频中心', '手动 EQ')
UNITS = ('', '%', 'LUFS', '%', '%', 'dB', 'dB', 'dB', 'Hz', 'Hz', 'Hz', '')


def checksum(path):
    with path.open('rb') as stream:
        return file_digest(stream, 'sha256').hexdigest()


def checked_settings(params, values):
    require(type(values) is list and len(values) == len(params), 'invalid_master_settings')
    for p, value in zip(params, values):
        require(type(value) in (int, float) and math.isfinite(value) and p['minimum'] <= value <= p['maximum']
                and (p['id'] not in (0, 11) or int(value) == value), 'invalid_master_settings')
    return [float(value) for value in values]


@lru_cache(maxsize=8)
def parameter_manifest(renderer_sha, component_sha):
    raw = subprocess.run([RENDERER, '--parameters', COMPONENT], check=True, capture_output=True, timeout=10)
    items = json.loads(raw.stdout)
    require([row.get('id') for row in items] == list(range(len(LABELS))), 'studio_engine_schema', 503)
    return [{'id': i, 'label': LABELS[i], 'unit': UNITS[i], 'minimum': p['min'],
             'maximum': p['max'], 'values': p.get('values', []), 'default': p['default']}
            for i, p in enumerate(items)]


def engine_identity():
    return checksum(RENDERER), checksum(BINARY)


def parameters():
    return parameter_manifest(*engine_identity())


def clip_specs(track, draft):
    track_id = track['id']
    if track_id in draft.get('splits', {}):
        return draft['splits'][track_id]
    trim = draft.get('trims', {}).get(track_id, {})
    pad = draft.get('padding', {}).get(track_id, {})
    return [{'start': draft['offsets'].get(track_id, track['start']),
             'sourceIn': track['sourceIn'] + trim.get('head', 0),
             'duration': track['duration'] - trim.get('head', 0) - trim.get('tail', 0),
             'silenceTail': pad.get('tail', 0)}]


def frame(second, rate):
    return int(second * rate + .5)


def arrangement(root, version, draft, rate):
    length, tracks, pins = 0, [], []
    sources = {item['track']: item for item in version['masterRate']['sources']}
    for track in version['tracks']:
        path, pin = media_pin(root, track['file'], track['sha256'])
        source_rate = sources[track['id']].get('rate')
        require(type(source_rate) is int and source_rate > 0, 'studio_source_rate_unknown')
        pins.append((path, pin))
        clips = []
        for clip in clip_specs(track, draft):
            start = frame(clip['start'], rate)
            end = frame(clip['start'] + clip['duration'], rate)
            length = max(length, frame(clip['start'] + clip['duration'] + clip.get('silenceTail', 0), rate))
            if end > start:
                clips.append({'start': start, 'sourceStart': frame(clip['sourceIn'], source_rate), 'frames': end-start})
        # Solo and the listener's volume belong to the editor transport.
        tracks.append({'id': track['id'], 'file': track['file'], 'clips': clips})
    require(0 < length <= rate * 1200, 'studio_empty_mix')
    return {'schema': 1, 'sampleRate': rate, 'frames': length, 'mediaRoot': str(root), 'tracks': tracks}, pins


def save_monitor(manifest_file, preset, frames, rate, scratch, dest, *, bypass):
    """Cache the native monitor stream from the same applied AU preset."""
    count = 131072
    requests = [json.dumps({'op': 'read', 'frames': min(count, frames-offset)})
                for offset in range(0, frames, count)]
    requests.append('{"op":"quit"}')
    bridge_file = scratch / 'monitor.pipe-data'
    command = [RENDERER, '--monitor', COMPONENT, manifest_file, '--load-preset', preset]
    if bypass:
        command.append('--bypass')
    with bridge_file.open('xb') as stream:
        subprocess.run(command,
                       input=('\n'.join(requests) + '\n').encode(), stdout=stream, stderr=subprocess.PIPE,
                       check=True, timeout=300)
    raw_file = scratch / 'bypass.f32'
    with bridge_file.open('rb') as bridge, raw_file.open('xb') as raw:
        initial = json.loads(bridge.readline(8192))
        require(initial.get('ready') and initial.get('channels') == 2 and initial.get('encoding') == 'f32le'
                and initial.get('frames') == frames and initial.get('sampleRate') == rate, 'studio_monitor_invalid')
        for offset in range(0, frames, count):
            result = json.loads(bridge.readline(8192))
            n = min(count, frames-offset)
            require(result.get('start') == offset and result.get('frames') == n, 'studio_monitor_invalid')
            block = bridge.read(n * 8)
            require(len(block) == n * 8, 'studio_monitor_invalid')
            raw.write(block)
        require(json.loads(bridge.readline(8192)).get('closed') and not bridge.read(1), 'studio_monitor_invalid')
    # Audition only: retain dynamics while allowing the unprocessed bus to exceed 0 dBFS.
    monitor = scratch / 'monitor.wav'
    apple.run(['ffmpeg', '-v', 'error', '-nostdin', '-f', 'f32le', '-ar', str(rate), '-ac', '2',
               '-i', raw_file, '-c:a', 'pcm_f32le', monitor])
    peak = apple.meter(monitor)['true_peak_dbtp']
    require(math.isfinite(peak), 'studio_empty_mix')
    gain = min(0., -0.5 - peak)
    apple.run(['ffmpeg', '-v', 'error', '-nostdin', '-i', monitor, '-af', f'volume={gain:.4f}dB',
               '-c:a', 'aac', '-b:a', '256k', '-ar', str(min(rate,48000)), '-movflags', '+faststart', dest])
    return {'gain_db': round(gain, 4), 'source_peak_dbtp': peak, 'frames': frames, 'live_engine': True, 'bypass': bypass}


def artifact(folder, identifier, key):
    row = read_json(folder / identifier / 'receipt.json')
    if row and row['key'][:2] == list(key[:2]):
        return row
    return None


def analyze(root, folder, key, version, draft, expected, values, requested, still_current):
    rate, basis = choose(version['masterRate'], requested)
    renderer, unit = engine_identity()
    manifest, pins = arrangement(root, version, draft, rate)
    plan = arrangement_digest(manifest, version)
    identifier = 'analysis-' + digest([key, renderer, unit, plan, values, basis])[:32]

    def recheck():
        verify_source(folder, key, expected, still_current, pins, renderer, unit)

    with locked(folder / 'render.lock', nonblocking=True):
        with locked(folder / 'state.lock'):
            recheck()
            prior = artifact(folder, identifier, key)
            if prior:
                saved = folder / identifier / 'Output Master.aupreset'
                require(not saved.is_symlink() and checksum(saved) == prior['preset_sha256'], 'analysis_changed', 409)
                return prior
        with TemporaryDirectory(dir=folder, prefix='.analysis-') as temp:
            staging = Path(temp)
            destination = staging / 'prepared'
            destination.mkdir(mode=0o700)
            source = staging / 'arrangement.json'
            source.write_text(json.dumps(manifest, ensure_ascii=False), encoding='utf-8')
            preset = destination / 'Output Master.aupreset'
            args = [RENDERER, '--analyze', COMPONENT, source, preset]
            for i, value in enumerate(values):
                args.extend(['--set', str(i), str(value)])
            output = subprocess.run(args, capture_output=True, check=True, timeout=600)
            analysis = json.loads(output.stdout)
            require((analysis['rate'], analysis['frames'], analysis['tracks'], analysis['applied']) ==
                    (rate, manifest['frames'], len(manifest['tracks']), True), 'studio_engine_analysis_invalid')
            preset.chmod(0o600)
            receipt = {'id': identifier, 'key': list(key), 'source_revision': expected, 'frames': manifest['frames'],
                       'sample_rate': rate, 'rate_basis': basis, 'analysis': analysis,
                       'arrangement_sha256': plan, 'settings': values, 'engine_sha256': unit,
                       'renderer_sha256': renderer, 'preset_sha256': checksum(preset), 'files': {}}
            atomic_write(destination / 'receipt.json', receipt, maximum=262144)
            with locked(folder / 'state.lock'):
                recheck()
                destination.rename(folder / identifier)
            return receipt


def arrangement_digest(manifest, version):
    identity = {k: v for k, v in manifest.items() if k != 'mediaRoot'}
    identity['tracks'] = [row | {'sha256': source['sha256']} for row, source in zip(
        identity['tracks'], version['tracks'])]
    return digest(identity)


def verify_source(folder, key, expected, still_current, pins, renderer, unit):
    require(read_draft(folder, key)['revision'] == expected and still_current(), 'draft_changed', 409)
    require(all(file_state(path.lstat()) == pin for path, pin in pins), 'studio_media_changed', 409)
    require(engine_identity() == (renderer, unit), 'studio_engine_changed', 409)


def build(root, folder, key, version, draft, expected, prepared, still_current):
    rate = prepared['sample_rate']
    renderer, unit = engine_identity()
    delivery = checksum(Path(apple.__file__))
    manifest, pins = arrangement(root, version, draft, rate)
    plan = arrangement_digest(manifest, version)
    require((plan, renderer, unit) == (prepared['arrangement_sha256'], prepared['renderer_sha256'],
                                      prepared['engine_sha256']), 'analysis_changed', 409)
    identifier = 'master-' + digest([key, prepared['id'], delivery])[:32]
    analysis_directory = folder / prepared['id']
    preset = analysis_directory / 'Output Master.aupreset'
    require(not preset.is_symlink() and checksum(preset) == prepared['preset_sha256'], 'analysis_changed', 409)

    def recheck():
        verify_source(folder, key, expected, still_current, pins, renderer, unit)
        require(checksum(preset) == prepared['preset_sha256'], 'analysis_changed', 409)

    with locked(folder / 'render.lock', nonblocking=True):
        with locked(folder / 'state.lock'):
            recheck()
            prior = artifact(folder, identifier, key)
            if prior:
                for kind, filename in MEDIA.items():
                    media_pin(root, str((folder / identifier / filename).relative_to(root)), prior['files'][kind])
                return prior
        with TemporaryDirectory(dir=folder, prefix='.render-') as tmp:
            staging = Path(tmp)
            manifest_file = staging / 'arrangement.json'
            manifest_file.write_text(json.dumps(manifest, ensure_ascii=False), encoding='utf-8')
            output = staging / 'output.wav'
            result_dir = staging / 'finished'
            result_dir.mkdir(mode=0o700)
            proc = subprocess.run([RENDERER, '--bus', COMPONENT, manifest_file, output, '--load-preset', preset],
                                  capture_output=True, check=True, timeout=600)
            native = json.loads(proc.stdout)
            require((native['rate'], native['frames'], native['tracks'], native['bypass']) ==
                    (rate, manifest['frames'], len(manifest['tracks']), False), 'studio_engine_render_invalid')
            qc = apple.prepare_delivery(output, result_dir / MEDIA['wav'], result_dir / MEDIA['aac'])
            # Archived versions keep their playable bypass AAC. Generate it only on export.
            dry_monitor = save_monitor(manifest_file, preset, manifest['frames'], rate, staging,
                                       result_dir / MEDIA['bypass'], bypass=True)
            shutil.copyfile(preset, result_dir / preset.name)
            hashes = {name: checksum(result_dir / filename) for name, filename in MEDIA.items()}
            require(checksum(result_dir / preset.name) == prepared['preset_sha256'], 'analysis_changed', 409)
            for filename in (*MEDIA.values(), preset.name):
                (result_dir / filename).chmod(0o600)
            receipt = {'id': identifier, 'key': list(key), 'source_revision': expected, 'frames': manifest['frames'],
                       'sample_rate': rate, 'rate_basis': prepared['rate_basis'],
                       'source_media': version['masterRate']['sources'], 'source_hashes': [t['sha256'] for t in version['tracks']],
                       'arrangement_sha256': plan, 'settings': prepared['settings'], 'engine_sha256': unit,
                       'renderer_sha256': renderer, 'delivery_code': delivery, 'prepared_analysis': prepared['id'],
                       'delivery': apple.DELIVERY_PROFILE, 'preset_sha256': prepared['preset_sha256'],
                       'files': hashes, 'qc': qc, 'analysis': prepared['analysis'], 'native': native,
                       'bypass_monitor': dry_monitor}
            atomic_write(result_dir / 'receipt.json', receipt, maximum=262144)
            with locked(folder / 'state.lock'):
                recheck()
                result_dir.rename(folder / identifier)
            return receipt
