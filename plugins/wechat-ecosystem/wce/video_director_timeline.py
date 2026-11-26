"""Non-destructive work timelines. Renders use verified local inputs and publish a new MP4."""
from fractions import Fraction
from functools import lru_cache
from hashlib import file_digest, sha256
import json
import os
from pathlib import Path
from tempfile import TemporaryDirectory

from . import video_director_delivery as delivery
from . import video_director_look as looks
from .audio_jobs import AudioJobs, invoke
from .contracts import WCEError
from .bounded_file import FileSource, file_state
from .own_bootstrap_security import path_check
from .service import digest
from .video_director import lookup, require
from .video_jobs import PROJECT_VIDEO_DIR, probe

FPS = 30


def saved(work):
    return work.get('timeline', {'timeline_version': 0, 'clips': [], 'music': None})


def export_key(version, mix=None):
    return f'{version}-mix-{digest(mix)}' if mix else str(version)


def millis(seconds):
    return round(seconds * 1000)


@lru_cache(maxsize=512)
def stream_frame_rate(path, pin):
    """Read the first video stream's container metadata once per file generation."""
    try:
        raw = invoke('ffprobe', ['-v', 'error', '-protocol_whitelist', 'file,pipe', '-f', 'mov',
                     '-select_streams', 'v:0', '-show_entries', 'stream=avg_frame_rate,r_frame_rate',
                     '-of', 'json', str(path)], 10)
        stream = json.loads(raw)['streams'][0]
        if file_state(path.lstat()) == pin:
            for field in ('avg_frame_rate', 'r_frame_rate'):
                try:
                    rate = Fraction(stream.get(field, '0/1'))
                except (ValueError, ZeroDivisionError, TypeError):
                    continue
                if rate > 0:
                    return f'{rate.numerator}/{rate.denominator}'
    except (WCEError, OSError, ValueError, IndexError, KeyError):
        pass
    return None


def source_frame_rate(jobs, root, work, card, asset):
    if asset.get('frame_rate'):
        return asset['frame_rate']
    film = work.get('films', {}).get(card['id'])
    try:
        if film:
            path, pin = delivery.local_video_source(root, film['file'])
        elif card.get('attempt_id'):
            _, path = jobs._paths(card['attempt_id'])
            pin = path_check(path)
        else:
            return None
        return stream_frame_rate(path, pin)
    except (WCEError, OSError):
        return None


def read(jobs, root, project, work, export_version=None):
    require(work.get('kind') != 'article', 'ARTICLE_WORK_USE_ARTICLE_TOOLS')
    sources = []
    for card in delivery.collect(jobs, root, project, work):
        if card['state'] != 'ASSET_READY':
            continue
        asset = card.get('asset', card)
        sources.append({'delivery_id': card['id'], 'title': card['title'], 'kind': card['kind'],
                        'sha256': asset['sha256'], 'duration_ms': millis(asset['seconds']),
                        'audio_tracks': asset.get('audio_tracks', 0), 'bytes': asset['bytes'],
                        'frame_rate': source_frame_rate(jobs, root, work, card, asset),
                        **{k: asset[k] for k in ('width', 'height') if k in asset},
                        **{k: card[k] for k in ('scene_id', 'shot_id', 'revision_id', 'adopted') if k in card}})
    audio = AudioJobs(jobs)
    songs = [{'attempt_id': r['attempt_id'], 'title': r['title'], 'sha256': r['sha256'],
              'duration_ms': millis(r['seconds']), 'bytes': r['bytes'], 'mime': r['mime']}
             for r in audio.history(project)['assets']
             if r['kind'] == 'song' and r['state'] == 'ASSET_READY' and audio.source_present(r)]
    exports = work.get('timeline_exports', {})
    selected = saved(work)
    if export_version is not None:
        # All mix variants share the exact film timeline saved at this revision.
        matching = next((entry for entry in exports.values()
                         if entry['cut']['timeline_version'] == export_version), None)
        require(matching is not None, 'DIRECTOR_TIMELINE_EXPORT_NOT_FOUND')
        selected = matching['cut']
    return {'project_id': project, 'work_id': work['id'], **selected,
            'detached_audio': selected.get('detached_audio', []), 'sources': sources, 'songs': songs,
            'current_timeline_version': saved(work)['timeline_version'],
            'exports': [{'timeline_version': entry['cut']['timeline_version'], 'delivery_id': entry['delivery_id'],
                         **({'studio_mix': entry['studio_mix']} if 'studio_mix' in entry else {})}
                        for entry in sorted(exports.values(), key=lambda r: r['cut']['timeline_version'])]}


def video_source(jobs, root, project, work, clip):
    target = clip['delivery_id']
    checksum = clip['sha256']
    if target in work.get('films', {}):
        file, pin, asset = delivery.work_video(root, work, {'project_id': project, 'delivery_id': target})
        require(checksum == file['sha256'], 'DIRECTOR_ASSET_CHANGED')
        return root, file['path'], pin, asset
    spec = delivery.candidate_spec(work, target)
    asset = delivery.verified_candidate(jobs, project, spec, checksum)
    path, _, pin = jobs._playable(spec['attempt_id'], project)
    return path.parent, path.name, pin, asset


def song_source(jobs, project, music):
    audio = AudioJobs(jobs)
    row = audio.read(music['attempt_id'], project)
    require(row['kind'] == 'song' and row['sha256'] == music['sha256'], 'DIRECTOR_ASSET_CHANGED')
    source, _ = audio.file(row)
    return source.root, row['file'], audio.pin(source, row), row


def validate(jobs, root, project, work, clips, music, detached=()):
    require(len({c['id'] for c in clips}) == len(clips), 'DIRECTOR_DUPLICATE_CLIP')
    frame_counts(clips)
    sources = {}
    require(len({item['id'] for item in detached}) == len(detached), 'DIRECTOR_DUPLICATE_AUDIO_REGION')
    for clip in (*clips, *detached):
        key = clip['delivery_id'], clip['sha256']
        if key not in sources:
            sources[key] = video_source(jobs, root, project, work, clip)
        duration = millis(sources[key][3]['seconds'])
        if 'clip_id' in clip:
            require(sources[key][3].get('audio_tracks', 0) > 0, 'DIRECTOR_SOURCE_HAS_NO_AUDIO')
        else:
            looks.validate_cues(clip.get('look', {}), duration)
        require(0 <= clip['in_ms'] < clip['out_ms'] <= duration, 'DIRECTOR_TIME_RANGE_INVALID')
    song = None
    if music:
        song = song_source(jobs, project, music)
        duration = millis(song[3]['seconds'])
        require(0 <= music['in_ms'] < music.get('out_ms', duration) <= duration, 'DIRECTOR_TIME_RANGE_INVALID')
    return sources, song


def save(jobs, root, project, work, args):
    clips, music = args['clips'], args.get('music')
    previous = saved(work)
    detached = args.get('detached_audio', previous.get('detached_audio', []))
    muted = {item['clip_id'] for item in detached}
    if 'detached_audio' not in args:
        # Older clients replace the video array without knowing this per-instance audio state.
        muted.update(c['id'] for c in previous['clips'] if c.get('audio_detached'))
    clips = [dict(c, audio_detached=True) if c['id'] in muted else c for c in clips]
    validate(jobs, root, project, work, clips, music, detached)
    version = previous['timeline_version'] + 1
    work['timeline'] = {'timeline_version': version, 'clips': clips, 'music': music}
    if detached or 'detached_audio' in args or 'detached_audio' in previous:
        work['timeline']['detached_audio'] = detached
    return {'work_id': work['id'], 'timeline_version': version}


def stage(source, destination):
    base, relative, pin, asset = source
    h = sha256()
    with destination.open('xb') as out:
        for block in FileSource(base).iter_html(relative, expected_state=pin):
            h.update(block)
            out.write(block)
    require(h.hexdigest() == asset['sha256'], 'DIRECTOR_ASSET_CHANGED')
    return destination


def canvas_size(path):
    raw = invoke('ffprobe', ['-v', 'error', '-f', 'mov', '-select_streams', 'v:0',
                 '-show_entries', 'stream=width,height,sample_aspect_ratio:stream_side_data=rotation',
                 '-of', 'json', str(path)], 20)
    stream = json.loads(raw)['streams'][0]
    width, height = stream['width'], stream['height']
    sar = stream.get('sample_aspect_ratio', '').split(':')
    if len(sar) == 2 and all(x.isdigit() and int(x) > 0 for x in sar):
        width *= int(sar[0]) / int(sar[1])
    if any(abs(int(side.get('rotation', 0))) % 180 == 90 for side in stream.get('side_data_list', [])):
        width, height = height, width
    factor = min(1, 1920 / max(width, height))
    return tuple(max(2, round(x * factor / 2) * 2) for x in (width, height))


def transcode_segment(path, clip, has_audio, frames, dimensions, out):
    width, height = dimensions
    seconds = frames / FPS
    args = ['-v', 'error', '-nostdin', '-protocol_whitelist', 'file,pipe', '-ss', str(clip['in_ms'] / 1000),
            '-f', 'mov', '-i', str(path)]
    if not has_audio:
        args += ['-f', 'lavfi', '-i', 'anullsrc=r=48000:cl=stereo']
    # Fit each shot without stretching; quantize boundaries cumulatively in render().
    vf = (f'scale={width}:{height}:force_original_aspect_ratio=decrease:force_divisible_by=2:reset_sar=1,'
          f'pad={width}:{height}:(ow-iw)/2:(oh-ih)/2,setsar=1,fps={FPS},'
          f'tpad=stop_mode=clone:stop_duration={seconds},trim=end_frame={frames},setpts=PTS-STARTPTS')
    af = f'aresample=48000,aformat=channel_layouts=stereo,volume={clip["volume"]/100},apad,atrim=duration={seconds},asetpts=PTS-STARTPTS'
    look = clip.get('look', {})
    filters = [vf, *looks.image_filters(look, dimensions, frames, FPS)]
    fade = looks.entry_filter(look, frames, FPS)
    with TemporaryDirectory(dir=out.parent, prefix='layers-') as folder:
        overlay = looks.overlay_input(Path(folder), clip, dimensions, frames, FPS)
        if overlay:
            args += overlay
            layer = 1 if has_audio else 2
            graph = '[0:v:0]' + ','.join(filters) + f'[base];[base][{layer}:v:0]overlay=eof_action=repeat'
            graph += (',' + fade if fade else '') + '[outv]'
            mapping = ['-filter_complex', graph, '-map', '[outv]']
        else:
            if fade:
                filters.append(fade)
            mapping = ['-map', '0:v:0', '-vf', ','.join(filters)]
        invoke('ffmpeg', args + mapping + ['-map', '0:a:0' if has_audio else '1:a:0',
                   '-af', af, '-t', str(seconds), '-c:v', 'libx264', '-preset', 'veryfast',
                   '-pix_fmt', 'yuv420p', '-c:a', 'pcm_s16le', '-map_metadata', '-1', str(out)],
               max(90, int(seconds * 5)))


def frame_counts(clips):
    elapsed_ms = previous = 0
    result = []
    for clip in clips:
        require(clip['out_ms'] > clip['in_ms'], 'DIRECTOR_TIME_RANGE_INVALID')
        elapsed_ms += clip['out_ms'] - clip['in_ms']
        boundary = (elapsed_ms * FPS + 500) // 1000
        require(boundary > previous, 'DIRECTOR_CLIP_SHORTER_THAN_FRAME')
        result.append(boundary - previous)
        previous = boundary
    return result


def render(jobs, root, project, work, folder, progress=None, studio_mix=None):
    timeline = saved(work)
    clips, music = timeline['clips'], timeline['music']
    require(clips, 'DIRECTOR_TIMELINE_EMPTY')
    detached = timeline.get('detached_audio', [])
    sources, song = validate(jobs, root, project, work, clips, None if studio_mix else music, detached)
    source_audio = not studio_mix or studio_mix.get('source_audio', True)
    paths = {key: stage(source, folder / f'source-{i}.mp4')
             for i, (key, source) in enumerate(sources.items())}
    dims = canvas_size(next(iter(paths.values())))
    counts = frame_counts(clips)
    elapsed = sum(c['out_ms'] - c['in_ms'] for c in clips)
    entries = []
    for i, (clip, frames) in enumerate(zip(clips, counts)):
        key = clip['delivery_id'], clip['sha256']
        segment = folder / f'clip-{i}.mov'
        audible_clip = clip if source_audio and not clip.get('audio_detached') else {**clip, 'volume': 0}
        transcode_segment(paths[key], audible_clip, sources[key][3].get('audio_tracks', 0), frames, dims, segment)
        if progress:
            progress(i + 1)
        entries.extend([f"file '{segment.name}'", f'duration {frames / FPS:.9f}'])
    plan = folder / 'sequence.ffconcat'
    plan.write_text('ffconcat version 1.0\n' + '\n'.join(entries) + '\n', encoding='ascii')
    args = ['-v', 'error', '-nostdin', '-protocol_whitelist', 'file,pipe', '-f', 'concat', '-safe', '1',
            '-i', str(plan)]
    filters, labels = [], ['[0:a:0]']
    next_input = 1
    if studio_mix:
        from .studio_mv_audio import render_video_score
        soundtrack = None if studio_mix.get('mode') == 'picture_only' else render_video_score(
            jobs, root, project, work, studio_mix, folder, elapsed)
        if soundtrack:
            args += ['-protocol_whitelist', 'file,pipe', '-f', 'wav', '-i', str(soundtrack)]
            labels.append('[1:a:0]')
            next_input += 1
    elif music and music['start_ms'] < elapsed:
        song_path = stage(song, folder / 'song')
        args += ['-protocol_whitelist', 'file,pipe', '-ss', str(music['in_ms'] / 1000), '-f', song[3]['demuxer'],
                 '-i', str(song_path)]
        length = (music.get('out_ms', millis(song[3]['seconds'])) - music['in_ms']) / 1000
        filters.append(f'[1:a:0]atrim=duration={length},asetpts=PTS-STARTPTS,aresample=48000,'
                       f'volume={music["volume"]/100},adelay={music["start_ms"]}:all=1[score]')
        labels.append('[score]')
        next_input += 1

    inputs = {}
    for index, region in enumerate(detached):
        start = region['start_ms']
        if not source_audio or not region['volume'] or start >= elapsed:
            continue
        key = region['delivery_id'], region['sha256']
        if key not in inputs:
            args += ['-protocol_whitelist', 'file,pipe', '-f', 'mov', '-i', str(paths[key])]
            inputs[key] = next_input
            next_input += 1
        begin = region['in_ms']
        end = min(region['out_ms'], begin + elapsed - start)
        label = f'[detached{index}]'
        filters.append(f'[{inputs[key]}:a:0]atrim=start={begin/1000}:end={end/1000},asetpts=PTS-STARTPTS,'
                       f'aresample=48000,aformat=channel_layouts=stereo,volume={region["volume"]/100},'
                       f'adelay={start}:all=1{label}')
        labels.append(label)
    mapping = ['-map', '0:v:0', '-map', '0:a:0']
    if len(labels) > 1:
        filters.append(''.join(labels) + f'amix=inputs={len(labels)}:duration=first:normalize=0[a]')
        mapping = ['-filter_complex', ';'.join(filters), '-map', '0:v:0', '-map', '[a]']
    output = folder / 'sequence.mp4'
    invoke('ffmpeg', args + mapping + ['-c:v', 'copy', '-c:a', 'aac', '-b:a', '192k', '-t', str(sum(counts)/FPS),
           '-map_metadata', '-1', '-movflags', '+faststart', str(output)], max(90, elapsed // 200))
    os.chmod(output, 0o600)
    return output


def export(director, jobs, args, progress, record_scratch):
    project, target = args['project_id'], args['work_id']
    root, pin = director.project(project)
    storage = director.storage(root, pin)
    state = director.load(project, storage)
    existing = state['operations'].get(args['operation_id'])
    if existing:
        require(existing['fingerprint'] == digest(args), 'DIRECTOR_OPERATION_CONFLICT')
        return existing['receipt']
    work = lookup(state['works'], target, 'DIRECTOR_WORK_NOT_FOUND')
    require(work.get('kind') != 'article', 'ARTICLE_WORK_USE_ARTICLE_TOOLS')
    require(saved(work)['timeline_version'] == args['expected_timeline_version'], 'DIRECTOR_TIMELINE_CHANGED')
    with TemporaryDirectory(dir=storage, prefix='render-' + args['operation_id'] + '-') as temp:
        record_scratch(Path(temp))
        output = render(jobs, root, project, work, Path(temp), progress, args.get('studio_mix'))
        state_pin = path_check(output)
        # Provider downloads have a 64 MiB cap; a local film may combine many such clips.
        with output.open('rb') as handle:
            checksum = file_digest(handle, 'sha256').hexdigest()
        facts = probe(str(output), error='DIRECTOR_RENDER_INVALID')
        expected = sum(c['out_ms'] - c['in_ms'] for c in saved(work)['clips'])
        require(facts.get('playable') and facts.get('audio_tracks', 0) > 0
                and abs(millis(facts['seconds']) - expected) <= 75, 'DIRECTOR_RENDER_INVALID')
        require(path_check(output) == state_pin, 'DIRECTOR_ASSET_CHANGED')
        asset = {'sha256': checksum, 'bytes': state_pin[2]}
        filename = f'cut-{checksum}.mp4'

        def publish(current_root, current_work):
            require(current_root == root and director.project(project) == (root, pin), 'DIRECTOR_PROJECT_CHANGED')
            before = current_work.get('films', {}).get(digest(['work_video', target, checksum])[:32])
            if before:
                original = before['file']
            else:
                directory = jobs._project_video_folder({'root': str(root)}, list(pin), create=True)
                try:
                    jobs._copy_original(output, asset, state_pin, directory, filename, source_root=output.parent)
                finally:
                    os.close(directory)
                original = {'project_id': project, 'path': Path(*PROJECT_VIDEO_DIR, filename).as_posix(),
                            'sha256': checksum}
            result = delivery.register_work_video(root, current_work, {**args, 'file': original})
            version = args['expected_timeline_version']
            archive_key = export_key(version, args.get('studio_mix'))
            current_work.setdefault('timeline_exports', {})[archive_key] = {
                'cut': saved(current_work), 'delivery_id': result['delivery_id'], 'operation_id': args['operation_id'],
                **({'studio_mix': args['studio_mix']} if args.get('studio_mix') else {})}
            return {**result, 'timeline_version': version}
        # Rendering may take minutes. Recheck the exact edit revision inside the normal writer transaction.
        return director.edit(args, None, jobs=jobs, publish_timeline=publish)
