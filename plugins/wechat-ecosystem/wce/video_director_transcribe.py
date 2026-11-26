"""Recognize a bounded, pinned source selection with an already-installed offline Whisper model."""
import hashlib
import json
import math
import os
from pathlib import Path
import subprocess
import tempfile
from threading import BoundedSemaphore
import wave

from .audio_jobs import binary
from .bounded_file import FileSource, file_state
from .contracts import WCEError
from .video_director import require
from .video_director_export import load_work
from .video_director_timeline import millis, song_source, video_source

# Multilingual tiny.pt published with OpenAI Whisper. An explicit local model path avoids all downloads.
TINY_SHA256 = '65147644a518d12f04e32d6f3b26facc3f8dd46e5390956a9424a650c0ce22b9'
MAX_WINDOW_MS = 30_000
_worker = BoundedSemaphore(1)


def recognize(wav, language):
    try:
        cli = binary('whisper')
        model = (Path.home() / '.cache/whisper/tiny.pt').open('rb')
    except (OSError, WCEError):
        raise WCEError('DIRECTOR_LOCAL_WHISPER_UNAVAILABLE') from None
    with model:
        digest = hashlib.sha256()
        for block in iter(lambda: model.read(1024 * 1024), b''):
            digest.update(block)
        require(digest.hexdigest() == TINY_SHA256, 'DIRECTOR_LOCAL_WHISPER_UNAVAILABLE')
        model.seek(0)
        # Pass the opened, verified model. The CLI treats this path as local and never resolves a model name.
        args = [cli, str(wav), '--model', f'/dev/fd/{model.fileno()}', '--output_dir', str(wav.parent),
                '--output_format', 'json', '--device', 'cpu', '--threads', '3', '--fp16', 'False',
                '--temperature', '0', '--temperature_increment_on_fallback', 'None',
                '--condition_on_previous_text', 'False', '--verbose', 'False']
        if language != 'auto':
            args.extend(['--language', language])
        env = {'PATH': '/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin', 'HOME': str(Path.home()),
               'TMPDIR': str(wav.parent), 'LANG': 'en_US.UTF-8', 'NUMBA_CACHE_DIR': str(wav.parent),
               'XDG_CACHE_HOME': str(wav.parent), 'HF_HUB_OFFLINE': '1', 'PYTHONDONTWRITEBYTECODE': '1'}
        subprocess.run(args, env=env, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                       pass_fds=(model.fileno(),), timeout=24, check=True)
    file = wav.with_suffix('.json')
    require(file.stat().st_size <= 1024 * 1024, 'DIRECTOR_LOCAL_WHISPER_RESULT_INVALID')
    return json.loads(file.read_bytes())['segments']


def extract(source, demuxer, start, end, wav):
    root, relative, pin, _ = source
    parts = Path(relative).parts
    with FileSource(root).open_directory(parts[:-1]) as parent:
        fd = os.open(parts[-1], os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=parent)
        try:
            require(file_state(os.fstat(fd)) == tuple(pin), 'DIRECTOR_ASSET_CHANGED')
            # Keep delayed MP4 audio aligned to its source clock before and after the selected interval.
            count = (end - start) * 16
            filters = f'aresample=16000:async=1:first_pts=0,apad=whole_len={count},atrim=end_sample={count}'
            subprocess.run([binary('ffmpeg'), '-nostdin', '-v', 'error', '-threads', '1', '-protocol_whitelist',
                            'file,pipe', '-ss', f'{start / 1000:.3f}', '-t', f'{(end - start) / 1000:.3f}',
                            '-f', demuxer, '-i', f'/dev/fd/{fd}', '-map', '0:a:0', '-af', filters,
                            '-ac', '1', '-ar', '16000', '-c:a', 'pcm_s16le', '-f', 'wav', str(wav)],
                           pass_fds=(fd,), stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                           timeout=5, check=True)
            require(file_state(os.fstat(fd)) == file_state(os.stat(parts[-1], dir_fd=parent,
                    follow_symlinks=False)) == tuple(pin), 'DIRECTOR_ASSET_CHANGED')
        finally:
            os.close(fd)


def cues(segments, start, end):
    require(isinstance(segments, list) and len(segments) <= 128, 'DIRECTOR_LOCAL_WHISPER_RESULT_INVALID')
    rows = []
    previous = start
    for item in segments:
        times = [item['start'], item['end']]
        require(all(isinstance(t, (float, int)) and math.isfinite(t) for t in times),
                'DIRECTOR_LOCAL_WHISPER_RESULT_INVALID')
        left, right = (round(t * 1000) + start for t in times)
        left, right = max(left, previous), min(right, end)
        text = item['text'].strip()
        if not text or right <= left:
            continue
        require(len(text) <= 200 and all(ord(c) >= 32 or c == '\n' for c in text),
                'DIRECTOR_LOCAL_WHISPER_RESULT_INVALID')
        rows.append({'in_ms': left, 'out_ms': right, 'text': text})
        previous = right
    return rows


def read(director, jobs, args):
    start, end = args['start_ms'], args['end_ms']
    require(start < end <= start + MAX_WINDOW_MS, 'DIRECTOR_TRANSCRIBE_WINDOW_INVALID')
    root, _, work = load_work(director, args)
    if 'delivery_id' in args:
        source = video_source(jobs, root, args['project_id'], work, args)
        require(bool(source[3].get('audio_tracks')), 'DIRECTOR_TRANSCRIBE_NO_AUDIO')
        demuxer = 'mov'
    else:
        source = song_source(jobs, args['project_id'], args)
        demuxer = source[3]['demuxer']
    require(end <= millis(source[3]['seconds']), 'DIRECTOR_TRANSCRIBE_WINDOW_INVALID')
    if not _worker.acquire(blocking=False):
        raise WCEError('DIRECTOR_LOCAL_WHISPER_BUSY')
    try:
        with tempfile.TemporaryDirectory(prefix='jiusera-caption-') as directory:
            wav = Path(directory) / 'audio.wav'
            extract(source, demuxer, start, end, wav)
            with wave.open(str(wav), 'rb') as track:
                silent = not any(track.readframes(track.getnframes()))
            rows = [] if silent else cues(recognize(wav, args.get('language', 'auto')), start, end)
    except subprocess.TimeoutExpired:
        raise WCEError('DIRECTOR_LOCAL_WHISPER_TIMEOUT') from None
    except (OSError, subprocess.SubprocessError, ValueError, KeyError, TypeError, wave.Error):
        raise WCEError('DIRECTOR_LOCAL_WHISPER_FAILED') from None
    finally:
        _worker.release()
    return {'sha256': args['sha256'], 'start_ms': start, 'end_ms': end,
            'state': 'ready' if rows else 'empty', 'cues': rows}
