"""Freeze a registered multitrack version into the soundtrack used by a video work."""
from hashlib import file_digest
from pathlib import Path
from tempfile import TemporaryDirectory

from .audio_jobs import invoke
from .contracts import WCEError
from .studio_projects import digest, media_pin
from .video_director_timeline import stage


def arrangement_key(version):
    if version.get('mastered'):
        return digest(['master', version['id']])
    return digest([[t[key] for key in ('id', 'sha256', 'start', 'sourceIn', 'duration')] for t in version['tracks']])


def soundtrack(audio, root, folder, selection, song, version):
    project, _, _ = selection
    tracks = version['tracks']
    attempt = 'imw-' + digest([selection, arrangement_key(version), 'stereo48-v2'])[:48]
    try:
        return audio.read(attempt, project)
    except WCEError as err:
        if str(err) != 'AUDIO_ASSET_NOT_READY':
            raise
    # Decode staged, pinned local inputs. No reference to the user's original is written.
    with TemporaryDirectory(prefix='.imw-mix-', dir=folder) as scratch:
        temp = Path(scratch)
        inputs, filters, labels = [], [], []
        for index, track in enumerate(tracks):
            path, pin = media_pin(root, track['file'], track['sha256'])
            local = stage((root, track['file'], pin, track), temp / (str(index) + path.suffix))
            inputs.extend(['-protocol_whitelist', 'file,pipe', '-format_whitelist', 'wav,aiff,mp3,mov,flac',
                           '-i', str(local)])
            channels = invoke('ffprobe', ['-v', 'error', '-protocol_whitelist', 'file,pipe',
                              '-format_whitelist', 'wav,aiff,mp3,mov,flac', '-select_streams', 'a:0',
                              '-show_entries', 'stream=channels', '-of', 'csv=p=0', str(local)], 15).strip()
            # Web Audio duplicates mono into L and R at unity.
            stereo = 'pan=stereo|c0=c0|c1=c0' if channels == b'1' else 'aformat=channel_layouts=stereo'
            start = round(track['start'] * 48000)
            filters.append(f'[{index}:a:0]atrim=start={track["sourceIn"]}:duration={track["duration"]},'
                           f'asetpts=PTS-STARTPTS,aresample=48000,{stereo},'
                           f'adelay={start}S:all=1[t{index}]')
            labels.append(f'[t{index}]')
        seconds = max(t['start'] + t['duration'] for t in tracks)
        out = temp / 'score.wav'
        filters.append(''.join(labels) + f'amix=inputs={len(labels)}:normalize=0,apad,atrim=duration={seconds}[mix]')
        invoke('ffmpeg', ['-v', 'error', '-nostdin', *inputs, '-filter_complex', ';'.join(filters),
                          '-map', '[mix]', '-c:a', 'pcm_s24le', '-f', 'wav', str(out)], 300)
        with out.open('rb') as stream:
            checksum = file_digest(stream, 'sha256').hexdigest()
        return audio.ingest(attempt, project, song['name'] + ' · ' + version['name'],
                            {'path': out.relative_to(root).as_posix(), 'sha256': checksum})

def mix_identity(version):
    return digest([version['id'], version.get('masterAudioSha'), version.get('previewGain', 1),
                   [[t['id'], t.get('sha256'), t['start'], t['sourceIn'], t['duration']] for t in version['tracks']]])


def render_video_score(jobs, root, project, work, mix, folder, picture_ms):
    """Render just the selected project's saved Studio edit, clipped to the current picture."""
    from types import SimpleNamespace
    from .studio_draft import read_draft
    from .studio_master_bus import MEDIA, clip_specs
    from .studio_protocol import StudioRouter
    from .video_director import Director, require

    studio = StudioRouter(SimpleNamespace(director=Director(jobs.projects)), jobs.projects.registry)
    selection = (project, mix['song'], mix['version'])
    audio_root, studio_folder, _, version = studio.bound(selection)
    require(audio_root == root and mix_identity(version) == mix['identity'], 'STUDIO_MIX_CHANGED')
    tracks = version['tracks']
    if version.get('mastered'):
        # The master is a read-only stereo asset. Its original edit has already been applied.
        master_file = (studio_folder / version['id'] / MEDIA['wav']).relative_to(root).as_posix()
        tracks = [dict(tracks[0], file=master_file, sha256=version['masterAudioSha'])]
        draft = {'revision': 0, 'offsets': {}}
    else:
        draft = read_draft(studio_folder, selection)
    require(draft['revision'] == mix['revision'], 'STUDIO_DRAFT_CHANGED')
    audible = set(mix['audible'])
    require(audible <= {t['id'] for t in version['tracks']}, 'STUDIO_TRACK_CHANGED')
    start, source_in, out, gain = 0, 0, picture_ms, version.get('previewGain', 1)
    if 'window_sha256' in mix:
        music = work.get('timeline', {}).get('music') or {}
        binding = studio.production.mv_binding({'project': project, 'work_id': work['id']})
        require(binding.get('bound') and (binding['song'], binding['version']) == selection[1:]
                and binding['source']['sha256'] == music.get('sha256') == mix['window_sha256'],
                'STUDIO_MIX_BINDING_CHANGED')
        start, source_in = music['start_ms'], music['in_ms']
        out = min(music.get('out_ms', binding['window']['end_ms']), source_in + picture_ms - start)
        gain *= music['volume'] / 100
    if not gain or not audible or start >= picture_ms:
        return None
    inputs, filters, labels = [], [], []
    for track in tracks:
        if track['id'] not in audible:
            continue
        segments = []
        for clip in clip_specs(track, draft):
            begin = max(clip['start'], source_in / 1000)
            end = min(clip['start'] + clip['duration'], out / 1000)
            if end > begin:
                segments.append((clip['sourceIn'] + begin - clip['start'], end - begin,
                                 begin + (start - source_in) / 1000))
        if not segments:
            continue
        index = len(inputs)
        _, pin = media_pin(root, track['file'], track['sha256'])
        local = stage((root, track['file'], pin, track), folder / f'stem-{index}.audio')
        inputs.append(str(local))
        channels = invoke('ffprobe', ['-v', 'error', '-protocol_whitelist', 'file,pipe',
                          '-format_whitelist', 'wav,aiff,mp3,mov,flac', '-select_streams', 'a:0',
                          '-show_entries', 'stream=channels', '-of', 'csv=p=0', str(local)], 15).strip()
        stereo = 'pan=stereo|c0=c0|c1=c0' if channels == b'1' else 'aformat=channel_layouts=stereo'
        for offset, duration, position in segments:
            label = f's{len(labels)}'
            filters.append(f'[{index}:a:0]aresample=48000,atrim=start_sample={round(offset*48000)}:'
                           f'end_sample={round((offset+duration)*48000)},asetpts=PTS-STARTPTS,{stereo},'
                           f'adelay={round(position*48000)}S:all=1[{label}]')
            labels.append(f'[{label}]')
    if not labels:
        return None
    output = folder / 'studio-score.wav'
    filters.append(''.join(labels) + f'amix=inputs={len(labels)}:normalize=0,volume={gain}[score]')
    guarded = []
    for file in inputs:
        guarded.extend(['-protocol_whitelist', 'file,pipe', '-format_whitelist', 'wav,aiff,mp3,mov,flac', '-i', file])
    invoke('ffmpeg', ['-v', 'error', '-nostdin', *guarded, '-filter_complex', ';'.join(filters),
                      '-map', '[score]', '-c:a', 'pcm_f32le', '-f', 'wav', str(output)], 300)
    return output
