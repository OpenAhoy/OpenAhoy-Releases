"""Read bounded peak envelopes for exact registered timeline sources."""
from functools import lru_cache
from math import ceil
import os
from pathlib import Path
import subprocess
from threading import BoundedSemaphore

from .audio_jobs import AudioJobs, binary
from .bounded_file import FileSource, file_state
from .contracts import WCEError
from .video_director import require
from .video_director_export import load_work
from .video_director_timeline import millis, video_source

WINDOW_MS = 120_000
MAX_BINS = 512
SAMPLE_RATE = 48000
_decoders = BoundedSemaphore(2)


@lru_cache(maxsize=4)
def audio_reader(jobs):
    # AudioJobs verifies the file SHA once per pin and reader.
    return AudioJobs(jobs)


def read(director, jobs, args):
    start, end, bins = args['start_ms'], args['end_ms'], args['bins']
    require(0 <= start < end <= start + WINDOW_MS and 1 <= bins <= MAX_BINS, 'DIRECTOR_WAVEFORM_RANGE_INVALID')
    project = args['project_id']
    root, _, work = load_work(director, args)
    if 'delivery_id' in args:
        root, relative, pin, facts = video_source(jobs, root, project, work, args)
        demuxer = 'mov'
        has_audio = bool(facts.get('audio_tracks'))
    else:
        audio = audio_reader(jobs)
        facts = audio.read(args['attempt_id'], project)
        require(facts['kind'] == 'song' and facts['sha256'] == args['sha256'], 'DIRECTOR_ASSET_CHANGED')
        source, _ = audio.file(facts)
        root, relative, pin = source.root, facts['file'], audio.pin(source, facts)
        demuxer, has_audio = facts['demuxer'], True
    require(end <= millis(facts['seconds']), 'DIRECTOR_WAVEFORM_RANGE_INVALID')
    result = {'start_ms': start, 'end_ms': end, 'sha256': args['sha256']}
    if not has_audio:
        return {**result, 'state': 'no_audio', 'peaks': []}
    peaks, samples_per_bin = envelope(root, relative, tuple(pin), demuxer, start, end, bins)
    return {**result, 'state': 'ready' if any(peaks) else 'silent', 'peaks': list(peaks),
            'sample_rate': SAMPLE_RATE, 'samples_per_bin': samples_per_bin}


@lru_cache(maxsize=96)
def envelope(root, relative, pin, demuxer, start, end, bins):
    count = (end - start) * (SAMPLE_RATE // 1000)
    block = ceil(count / bins)
    # Measure the maximum over channels before mixing, including opposite-polarity stereo.
    # Preserve silence before/after an offset or shorter audio stream on the video clock.
    filters = (f'aresample={SAMPLE_RATE}:async=1:first_pts=0,atrim=end_sample={count},'
               f'apad=whole_len={count},atrim=end_sample={count},asetnsamples=n={block}:p=1,'
               'astats=metadata=1:reset=1:measure_perchannel=none:measure_overall=Peak_level,'
               r"ametadata=print:key=lavfi.astats.Overall.Peak_level:file='pipe\:1'")
    parts = Path(relative).parts
    source = FileSource(root)
    if not _decoders.acquire(timeout=2):
        raise WCEError('DIRECTOR_WAVEFORM_BUSY')
    try:
        with source.open_directory(parts[:-1]) as parent:
            fd = os.open(parts[-1], os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=parent)
            try:
                require(file_state(os.fstat(fd)) == pin, 'DIRECTOR_ASSET_CHANGED')
                result = subprocess.run([binary('ffmpeg'), '-nostdin', '-v', 'error', '-filter_threads', '1',
                    '-protocol_whitelist', 'file,pipe', '-threads', '1', '-ss', f'{start / 1000:.3f}',
                    '-t', f'{(end - start) / 1000:.3f}', '-f', demuxer, '-i', f'/dev/fd/{fd}',
                    '-map', '0:a:0', '-af', filters, '-f', 'null', '-'],
                    pass_fds=(fd,), stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
                    timeout=20, check=True)
                require(file_state(os.fstat(fd)) == file_state(os.stat(parts[-1], dir_fd=parent,
                        follow_symlinks=False)) == pin, 'DIRECTOR_ASSET_CHANGED')
            finally:
                os.close(fd)
    except (OSError, subprocess.SubprocessError):
        raise WCEError('DIRECTOR_WAVEFORM_UNAVAILABLE') from None
    finally:
        _decoders.release()
    values = [float(line.partition(b'=')[2]) for line in result.stdout.splitlines()
              if line.startswith(b'lavfi.astats.Overall.Peak_level=')]
    require(len(values) == ceil(count / block), 'DIRECTOR_WAVEFORM_UNAVAILABLE')
    return bytes(0 if db == float('-inf') else max(1, round(255 * 10 ** (min(db, 0) / 20)))
                 for db in values), block
