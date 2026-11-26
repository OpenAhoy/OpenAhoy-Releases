"""Create a reusable local MP4 variant from an exact source interval without changing its timeline."""
from hashlib import file_digest
import os
from pathlib import Path
import subprocess
from tempfile import TemporaryDirectory
from time import monotonic

from . import video_director_delivery as delivery
from .audio_jobs import binary
from .bounded_file import FileSource, file_state
from .contracts import WCEError
from .own_bootstrap_security import path_check
from .own_connection_policy import locked
from .service import digest
from .video_director import require
from .video_director_export import load_work
from .video_director_timeline import FPS, millis, video_source
from .video_jobs import PROJECT_VIDEO_DIR, probe

NAMES = {'slow': '0.5× 慢放', 'fast': '2× 快放', 'reverse': '倒放', 'freeze': '定格',
         'denoise': '降噪', 'voice': '人声均衡', 'normalize': '响度标准化'}
AUDIO_FILTERS = {'slow': 'atempo=0.5', 'fast': 'atempo=2', 'reverse': 'areverse',
                 'denoise': 'afftdn=nf=-25:tn=1',
                 'voice': 'highpass=f=80,equalizer=f=280:t=q:w=1:g=-3,equalizer=f=3000:t=q:w=1:g=3',
                 'normalize': 'loudnorm=I=-16:LRA=11:TP=-1.5'}
MAX_WINDOW_MS = 10000


def render(source, args, out):
    base, relative, pin, facts = source
    start, end, mode = args['in_ms'], args['out_ms'], args['mode']
    duration = (end - start) / 1000
    target = max(1, round(duration * FPS * {'slow': 2, 'fast': 0.5}.get(mode, 1)))
    seconds = target / FPS
    has_audio = bool(facts.get('audio_tracks'))
    require(has_audio or mode not in ('voice', 'denoise', 'normalize'), 'DIRECTOR_VARIANT_NO_AUDIO')
    # Resize and convert before buffering in reverse. Both portrait and landscape fit a 1280×720 pixel budget.
    scale = ("scale=w='min(iw,if(gte(iw,ih),1280,720))':h='min(ih,if(gte(iw,ih),720,1280))'"
             ":force_original_aspect_ratio=decrease:force_divisible_by=2:reset_sar=1")
    vf = [scale, 'setsar=1', 'format=yuv420p', 'setpts=PTS-STARTPTS', f'fps={FPS}']
    if mode == 'freeze':
        vf.append('trim=end_frame=1')
    elif mode == 'reverse':
        vf += ['reverse', 'setpts=PTS-STARTPTS']
    elif mode in ('slow', 'fast'):
        vf += ['setpts=' + ('2*PTS' if mode == 'slow' else '0.5*PTS'), f'fps={FPS}']
    vf += [f'tpad=stop_mode=clone:stop_duration={seconds:.6f}', f'trim=end_frame={target}', f'setpts=N/({FPS}*TB)']
    audio = ['-an']
    if has_audio and mode != 'freeze':
        af = ['aresample=48000:async=1:first_pts=0', 'aformat=channel_layouts=stereo',
              f'apad=whole_dur={duration:.6f}', f'atrim=duration={duration:.6f}', 'asetpts=PTS-STARTPTS', AUDIO_FILTERS[mode],
              'aresample=48000', f'apad=whole_len={target * 1600}', f'atrim=end_sample={target * 1600}', 'asetpts=PTS-STARTPTS']
        audio = ['-map', '0:a:0', '-af', ','.join(af), '-c:a', 'aac', '-b:a', '160k']
    parts = Path(relative).parts
    with FileSource(base).open_directory(parts[:-1]) as folder:
        fd = os.open(parts[-1], os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=folder)
        try:
            require(file_state(os.fstat(fd)) == tuple(pin), 'DIRECTOR_ASSET_CHANGED')
            deadline = monotonic() + 22
            program = [binary('ffmpeg'), '-v', 'error', '-nostdin', '-filter_threads', '1']
            input_args = ['-threads', '2', '-protocol_whitelist', 'file,pipe', '-ss', f'{start / 1000:.3f}',
                          '-t', f'{duration:.3f}', '-f', 'mov', '-i', f'/dev/fd/{fd}']
            finish = ['-t', f'{seconds:.6f}', '-map_metadata', '-1', '-metadata',
                      f'comment=Jiusera {mode} {start}-{end} {args["sha256"]}', '-movflags', '+faststart']

            def encode(args):
                os.lseek(fd, 0, os.SEEK_SET)
                subprocess.run(program + args, pass_fds=(fd,), stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                               stderr=subprocess.DEVNULL, timeout=max(.1, deadline - monotonic()), check=True)

            with_sound = has_audio and mode != 'freeze'
            picture = out.with_name('picture.mp4') if with_sound else out
            encode(input_args + ['-map', '0:v:0', '-an', '-vf', ','.join(vf), '-c:v', 'libx264', '-threads', '2',
                                 '-preset', 'veryfast', '-crf', '21', '-maxrate', '6M', '-bufsize', '12M',
                                 '-pix_fmt', 'yuv420p', *finish, str(picture)])
            if with_sound:
                # Decode the bounded audio independently; temporal video filters can buffer the whole source.
                encode(input_args + ['-i', str(picture), '-map', '1:v:0', '-c:v', 'copy', *audio, *finish, str(out)])
            require(file_state(os.fstat(fd)) == file_state(os.stat(parts[-1], dir_fd=folder,
                    follow_symlinks=False)) == tuple(pin), 'DIRECTOR_ASSET_CHANGED')
        except subprocess.TimeoutExpired:
            raise WCEError('DIRECTOR_VARIANT_TIMEOUT') from None
        except (OSError, subprocess.SubprocessError):
            raise WCEError('DIRECTOR_VARIANT_RENDER_FAILED') from None
        finally:
            os.close(fd)
    os.chmod(out, 0o600)
    result = probe(str(out), error='DIRECTOR_VARIANT_RENDER_INVALID')
    require(result.get('playable') and bool(result.get('audio_tracks')) == (has_audio and mode != 'freeze')
            and abs(result.get('seconds', 0) - seconds) <= .075, 'DIRECTOR_VARIANT_RENDER_INVALID')


def create(director, jobs, args):
    project = args['project_id']
    root, root_pin = director.project(project)
    storage = director.storage(root, root_pin)
    require(0 <= args['in_ms'] < args['out_ms'] <= args['in_ms'] + MAX_WINDOW_MS, 'DIRECTOR_VARIANT_WINDOW_INVALID')
    # Coalesce retries under a short lease; ordinary edits are free to proceed while FFmpeg runs.
    try:
        with locked(storage / 'variant-render.lock', nonblocking=True):
            current_root, state, work = load_work(director, args)
            require(current_root == root, 'DIRECTOR_PROJECT_CHANGED')
            previous = state['operations'].get(args['operation_id'])
            if previous:
                require(previous['fingerprint'] == digest(args), 'DIRECTOR_OPERATION_CONFLICT')
                return previous['receipt']
            source = video_source(jobs, root, project, work, args)
            require(args['out_ms'] <= millis(source[3]['seconds']), 'DIRECTOR_VARIANT_WINDOW_INVALID')
            with TemporaryDirectory(dir=storage, prefix='variant-') as temp:
                output = Path(temp) / 'derived.mp4'
                render(source, args, output)
                pin = path_check(output)
                with output.open('rb') as handle:
                    checksum = file_digest(handle, 'sha256').hexdigest()
                asset = {'sha256': checksum, 'bytes': pin[2]}
                filename = f'variant-{checksum}.mp4'

                def publish(current, target):
                    require(current == root and director.project(project) == (root, root_pin), 'DIRECTOR_PROJECT_CHANGED')
                    # Revalidate the same immutable candidate in its current work before adding the derived asset.
                    video_source(jobs, current, project, target, args)
                    existing = target.get('films', {}).get(digest(['work_video', target['id'], checksum])[:32])
                    if existing:
                        original = existing['file']
                    else:
                        directory = jobs._project_video_folder({'root': str(root)}, list(root_pin), create=True)
                        try:
                            jobs._copy_original(output, asset, pin, directory, filename, source_root=output.parent)
                        finally:
                            os.close(directory)
                        original = {'project_id': project, 'path': Path(*PROJECT_VIDEO_DIR, filename).as_posix(),
                                    'sha256': checksum}
                    source_name = target.get('films', {}).get(args['delivery_id'], {}).get('title', '镜头')
                    title = f'{source_name[:80]} · {NAMES[args["mode"]]}'
                    result = delivery.register_work_video(root, target, {'project_id': project, 'file': original, 'title': title})
                    return {**result, 'title': title, 'mode': args['mode'], 'sha256': checksum,
                            'source_delivery_id': args['delivery_id'], 'source_sha256': args['sha256'],
                            'in_ms': args['in_ms'], 'out_ms': args['out_ms']}
                return director.edit(args, None, jobs=jobs, publish_timeline=publish)
    except WCEError as error:
        if error.code == 'CONNECTION_BUSY':
            raise WCEError('DIRECTOR_VARIANT_BUSY') from None
        raise
