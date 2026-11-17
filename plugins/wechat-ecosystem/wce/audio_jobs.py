"""Project audio imports and local soundtracks. This module makes no network request."""
from array import array
from base64 import b64encode
from hashlib import sha256
import json
import math
import os
from pathlib import Path
import subprocess
from sys import byteorder
from tempfile import TemporaryDirectory
from time import time

from .bounded_file import FileSource
from .contracts import WCEError
from .own_bootstrap_security import path_check
from .own_configuration_export import _directory
from .own_connection_policy import atomic_write, locked, read_optional
from .video_jobs import ATTEMPT, PLAYBACK_CHUNK, image

AAC_FORMAT = ('mov,mp4,m4a,3gp,3g2,mj2', 'mov')
FORMATS = {'.wav': ('wav', 'wav', 'audio/wav'), '.mp3': ('mp3', 'mp3', 'audio/mpeg'),
           '.m4a': (*AAC_FORMAT, 'audio/mp4')}
from .media_library import LIBRARY_ID, MediaLibrary

AUDIO_DIR = ('assets', 'openahoy', 'audio')


def binary(name):
    for folder in ('/opt/homebrew/bin', '/usr/local/bin', '/usr/bin'):
        path = Path(folder, name)
        if path.is_file() and os.access(path, os.X_OK):
            return str(path)
    raise WCEError('AUDIO_LOCAL_ENGINE_UNAVAILABLE')


def invoke(program, args, timeout):
    try:
        out = subprocess.run([binary(program), *args], stdin=subprocess.DEVNULL,
                             stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, check=True, timeout=timeout)
        return out.stdout
    except (OSError, subprocess.SubprocessError):
        raise WCEError('AUDIO_LOCAL_PROCESS_FAILED') from None


def inspect(path, demuxer):
    data = invoke('ffprobe', ['-v', 'error', '-protocol_whitelist', 'file,pipe',
        '-f', demuxer, '-show_entries', 'format=duration:stream=codec_type,width,height',
        '-of', 'json', str(path)], 15)
    try:
        value = json.loads(data)
        seconds = float(value['format']['duration'])
        streams = value['streams']
        if not (math.isfinite(seconds) and seconds>0):
            raise ValueError()
        return seconds, streams
    except (ValueError, KeyError, TypeError):
        raise WCEError('AUDIO_FILE_INVALID') from None


class AudioJobs:
    def __init__(self, videos):
        self.videos = videos
        self.media = MediaLibrary(videos.projects)
        self.root = videos.projects.root / 'project-audio'
        self._pinned = None

    def inspect_video(self, attempt, project_id, frame_start=None, include_audio=False):
        path, facts, pin = self.videos._playable(attempt, project_id)
        evidence = {'video':{key: value for key, value in facts.items() if key != 'path'}}
        if include_audio:
            evidence['audio_evidence'] = measure_audio(path, facts['audio_tracks'], facts['seconds'])
        if frame_start is not None:
            evidence['preview'] = self.videos.preview_frames(frame_start, attempt, project_id)
        if path_check(path) != pin:
            raise WCEError('VIDEO_ASSET_CHANGED')
        return evidence

    def project(self, project_id):
        if project_id == LIBRARY_ID:
            row = self.media.project()
            if row is not None:
                return row
        else:
            for row in self.videos.projects.view()['projects']:
                if row['id'] == project_id:
                    return row
        raise WCEError('VIDEO_PROJECT_NOT_REGISTERED')

    def library_projects(self):
        projects = self.videos.projects.view()['projects']
        default = self.media.project()
        return projects + ([default] if default is not None else [])

    def receipt(self, attempt):
        if type(attempt) is not str or not ATTEMPT.fullmatch(attempt):
            raise WCEError('INVALID_TOOL_ARGUMENTS')
        return self.root / (attempt+'.json')

    def init(self):
        # This is a sibling of the existing video directory; use its private parent.
        self.videos._directory()
        try:
            self.root.mkdir(mode=0o700)
        except FileExistsError:
            pass
        path_check(self.root,True)

    def history(self, project_id=None, *, unified=False):
        if unified:
            projects = {row['id']: row['name'] for row in self.library_projects()}
        elif project_id is None:
            return {'projects': [{'id': row['id'], 'name': row['name']}
                                 for row in self.videos.projects.view()['projects']]}
        else:
            projects = {project_id: self.project(project_id)['name']}
        if not self.root.exists():
            return {'assets':[]}
        path_check(self.root,True)
        with locked(self.root/'audio.lock', shared=True):
            rows = [read_optional(p) for p in sorted(self.root.glob('*.json'),reverse=True)]
        assets = [row for row in rows if row and row['project_id'] in projects]
        if unified:
            fields = ('attempt_id', 'project_id', 'kind', 'title', 'created_at', 'bytes', 'sha256',
                      'mime', 'seconds', 'video_attempt_id', 'video_project_id', 'video_sha256', 'provider')
            assets = [{key: row[key] for key in fields if key in row}
                      | {'project_label': row.get('project_label') or projects[row['project_id']],
                         'account_label': row.get('account_label')} for row in assets]
        return {'assets': sorted(assets, key=lambda row: row.get('created_at', 0), reverse=True)}

    def record_asset(self, row, staged, project, facts, extension):
        pin = path_check(staged)
        digest, size = self.videos._asset_digest(staged, pin, source_root=staged.parent)
        attribution = self.media.account('audio', row['attempt_id'], row['project_id'])
        source_project = row.get('source_project_id')
        source_label = self.project(source_project)['name'] if source_project else None
        project_label = attribution.get('project_label') or row.get('project_label') or source_label or project['name']
        account_label = attribution.get('account_label') or row.get('account_label')
        row['project_label'] = project_label
        if account_label:
            row['account_label'] = account_label
        name = self.media.filename(project_label, account_label, row['title'],
                                   row['attempt_id'], digest, extension)
        source=FileSource(project['root'])
        folder=self.videos._project_video_folder(project,list(source.root_identity),create=True,components=AUDIO_DIR)
        try:
            self.videos._copy_original(staged, {'sha256':digest,'bytes':size}, pin, folder, name,
                                       source_root=staged.parent)
        finally:
            os.close(folder)
        row.update(state='ASSET_READY',file=Path(*AUDIO_DIR,name).as_posix(),
                   sha256=digest,bytes=size,created_at=time(),**facts)
        atomic_write(self.receipt(row['attempt_id']),row)
        return row

    def read(self, attempt, project_id):
        self.project(project_id)
        if not self.root.exists():
            raise WCEError('AUDIO_ASSET_NOT_READY')
        path_check(self.root,True)
        row=read_optional(self.receipt(attempt))
        if row is None or row['project_id']!=project_id or row['state']!='ASSET_READY':
            raise WCEError('AUDIO_ASSET_NOT_READY')
        return row

    def ingest(self, attempt, project_id, title, selected, provider=None, provider_id=None, *,
               source_project_id=None):
        project = self.project(project_id)
        source = self.project(source_project_id) if source_project_id else project
        suffix=Path(selected['path']).suffix.lower()
        if suffix not in FORMATS or (provider is None)!=(provider_id is None) or not title.strip():
            raise WCEError('AUDIO_FILE_INVALID')
        row=dict(attempt_id=attempt,project_id=project_id,kind='song',title=title,
                 input_sha256=selected['sha256'],provider=provider,provider_id=provider_id)
        if source_project_id and source_project_id != project_id:
            row['source_project_id'] = source_project_id
        output_format, demuxer, mime=FORMATS[suffix]
        self.init()
        with locked(self.root/'audio.lock'):
            previous=read_optional(self.receipt(attempt))
            if previous:
                self.same(previous,row)
                return previous
            with TemporaryDirectory(dir=self.root) as tmp:
                stage=Path(tmp)/('source'+suffix)
                digest=sha256()
                with os.fdopen(os.open(stage,os.O_CREAT|os.O_EXCL|os.O_WRONLY,0o600),'wb') as out:
                    for chunk in FileSource(source['root']).iter_html(selected['path']):
                        digest.update(chunk);out.write(chunk)
                if digest.hexdigest()!=selected['sha256']:
                    raise WCEError('AUDIO_ASSET_CHANGED')
                seconds,streams=inspect(stage,demuxer)
                if [s['codec_type'] for s in streams]!=['audio']:
                    raise WCEError('AUDIO_FILE_INVALID')
                invoke('ffmpeg',['-v','error','-protocol_whitelist','file,pipe','-f',demuxer,
                                 '-i',str(stage),'-map','0:a:0','-f','null','-'],60)
                return self.record_asset(row,stage,project,{'seconds':seconds,'mime':mime,'demuxer':demuxer},suffix)

    @staticmethod
    def same(previous, row):
        if any(previous.get(k)!=v for k,v in row.items()):
            raise WCEError('AUDIO_ATTEMPT_CONFLICT')

    def file(self, row):
        source=FileSource(self.project(row['project_id'])['root'])
        return source, source.root / row['file']

    def pin(self, source, row):
        path=source.root/row['file']
        state=path_check(path)
        signature=(path,state,row['sha256'])
        if self._pinned==signature:return state
        digest=sha256()
        size=0
        for chunk in source.iter_html(row['file'],expected_state=state):
            digest.update(chunk);size+=len(chunk)
        if digest.hexdigest()!=row['sha256'] or size!=row['bytes']:
            raise WCEError('AUDIO_ASSET_CHANGED')
        self._pinned=signature
        return state

    def mix(self, attempt, project_id, video_id, song_id, title, settings, score_plan=None, *,
            song_project_id=None, video_project_id=None):
        project = self.project(project_id)
        song = self.read(song_id, song_project_id or project_id)
        if song['kind']!='song':
            raise WCEError('AUDIO_FILE_INVALID')
        original, video, pin = self.videos._playable(video_id, video_project_id or project_id)
        seconds=video['seconds']
        start,offset,volume,fade_in,fade_out=(settings[n] for n in ('video_start','music_offset','volume','fade_in','fade_out'))
        length=min(song['seconds']-offset,seconds-start)
        if not title.strip() or min(start,offset,volume,fade_in,fade_out)<0 or length<=0 or fade_in+fade_out>length:
            raise WCEError('AUDIO_TIMELINE_INVALID')
        duck = settings.get('duck', [])
        last = 0
        for interval in duck:
            begin, end = interval['start_ms'], interval['end_ms']
            if not last <= begin < end <= round(seconds * 1000) or not settings['keep_original']:
                raise WCEError('AUDIO_TIMELINE_INVALID')
            last = end
        row=dict(attempt_id=attempt,project_id=project_id,kind='soundtrack',title=title, settings=settings,
                 video_attempt_id=video_id,video_sha256=video['sha256'],song_attempt_id=song_id,song_sha256=song['sha256'])
        if score_plan is not None:
            row['score_plan'] = score_plan
        if song_project_id and song_project_id != project_id:
            row['song_project_id'] = song_project_id
        if video_project_id and video_project_id != project_id:
            row['video_project_id'] = video_project_id
        self.init()
        with locked(self.root/'audio.lock'):
            previous=read_optional(self.receipt(attempt))
            if previous:
                self.same(previous,row)
                return previous
            source,track=self.file(song)
            song_pin=self.pin(source,song)
            filters=f'[1:a:0]atrim=start={offset}:duration={length},asetpts=PTS-STARTPTS,volume={volume}'
            if fade_in:
                filters+=f',afade=t=in:st=0:d={fade_in}'
            if fade_out:
                filters+=f',afade=t=out:st={length-fade_out}:d={fade_out}'
            filters+=f',adelay={round(start*1000)}:all=1,apad'
            for interval in duck:
                low, high = interval['start_ms']/1000, interval['end_ms']/1000
                gain = interval['gain_percent']/100
                filters += f",volume=volume={gain}:enable='gte(t,{low})*lt(t,{high})'"
            filters += '[score]'
            label='score'
            if settings['keep_original'] and video.get('audio_tracks',0):
                filters+=';[0:a:0][score]amix=inputs=2:duration=longest:normalize=0,alimiter=limit=0.98[mixed]'
                label='mixed'
            with TemporaryDirectory(dir=self.root) as tmp:
                staged=Path(tmp)/'mix.mp4'
                invoke('ffmpeg',['-v','error','-nostdin','-protocol_whitelist','file,pipe','-f','mov','-i',str(original),
                    '-protocol_whitelist','file,pipe','-f',song['demuxer'],'-i',str(track),'-filter_complex',filters,
                    '-map','0:v:0','-map',f'[{label}]','-c:v','copy','-c:a','aac','-movflags','+faststart',
                    '-t',str(seconds),str(staged)],180)
                staged.chmod(0o600)
                if path_check(original)!=pin or path_check(track)!=song_pin:
                    raise WCEError('AUDIO_ASSET_CHANGED')
                output_seconds,streams=inspect(staged,'mov')
                sizes=[(s.get('width'),s.get('height')) for s in streams if s['codec_type']=='video']
                if sizes!=[(video['width'],video['height'])] or not any(s['codec_type']=='audio' for s in streams) or abs(output_seconds-seconds)>0.125:
                    raise WCEError('AUDIO_OUTPUT_INVALID')
                return self.record_asset(row,staged,project,{'seconds':output_seconds,'mime':'video/mp4','demuxer':'mov'},'.mp4')

    def cover_video(self, attempt, project_id, song_id, title, cover, *, song_project_id=None,
                    cover_project_id=None):
        project = self.project(project_id)
        song = self.read(song_id, song_project_id or project_id)
        cover_project = self.project(cover_project_id) if cover_project_id else project
        if song['kind'] != 'song' or not title.strip():
            raise WCEError('AUDIO_FILE_INVALID')
        row = dict(attempt_id=attempt, project_id=project_id, kind='cover', title=title,
                   song_attempt_id=song_id, song_sha256=song['sha256'], cover_sha256=cover['sha256'])
        if song_project_id and song_project_id != project_id:
            row['song_project_id'] = song_project_id
        if cover_project_id and cover_project_id != project_id:
            row['cover_project_id'] = cover_project_id
        self.init()
        with locked(self.root / 'audio.lock'):
            previous = read_optional(self.receipt(attempt))
            if previous:
                self.same(previous, row)
                return previous
            source, track = self.file(song)
            song_pin = self.pin(source, song)
            cover_root = Path(cover_project['root'])
            mime, still = image(cover_root / cover['path'], cover_root, cover['sha256'],
                                self.root, h3=True)
            with TemporaryDirectory(dir=self.root) as tmp:
                cover_path = Path(tmp) / ('cover.png' if mime == 'image/png' else 'cover.jpg')
                cover_path.write_bytes(still)
                staged = Path(tmp) / 'cover.mp4'
                invoke('ffmpeg', ['-v', 'error', '-nostdin', '-protocol_whitelist', 'file,pipe',
                    '-f', 'image2', '-pattern_type', 'none', '-loop', '1', '-framerate', '24',
                    '-i', str(cover_path), '-protocol_whitelist', 'file,pipe', '-f', song['demuxer'],
                    '-i', str(track), '-map', '0:v:0', '-map', '1:a:0', '-vf',
                    'scale=1280:720:force_original_aspect_ratio=decrease:force_divisible_by=2,'
                    'pad=1280:720:(ow-iw)/2:(oh-ih)/2,setsar=1', '-pix_fmt', 'yuv420p',
                    '-c:v', 'libx264', '-tune', 'stillimage', '-c:a', 'aac', '-movflags', '+faststart',
                    '-shortest', str(staged)], 180)
                staged.chmod(0o600)
                if path_check(track) != song_pin:
                    raise WCEError('AUDIO_ASSET_CHANGED')
                seconds, streams = inspect(staged, 'mov')
                video_sizes = [(s.get('width'), s.get('height')) for s in streams if s['codec_type'] == 'video']
                if (video_sizes != [(1280, 720)] or not any(s['codec_type'] == 'audio' for s in streams)
                        or abs(seconds - song['seconds']) > 0.125):
                    raise WCEError('AUDIO_OUTPUT_INVALID')
                return self.record_asset(row, staged, project,
                                         {'seconds':seconds, 'mime':'video/mp4', 'demuxer':'mov'}, '.mp4')

    def chunk(self, attempt, project_id, offset):
        row=self.read(attempt,project_id)
        source,_=self.file(row)
        if not 0<=offset<row['bytes']:
            raise WCEError('VIDEO_ASSET_OFFSET_INVALID')
        end=min(offset+PLAYBACK_CHUNK,row['bytes'])
        state=self.pin(source,row)
        raw=b''.join(source.iter_html(row['file'],expected_state=state,offset=offset,length=end-offset))
        if len(raw)!=end-offset:
            raise WCEError('AUDIO_ASSET_CHANGED')
        return {'data':b64encode(raw).decode('ascii'),'next':end,'total':row['bytes']}

    def export(self, attempt, project_id, destination=None):
        row=self.read(attempt,project_id)
        source,path=self.file(row)
        pin=self.pin(source,row)
        folder=_directory(destination if destination is not None else Path.home()/'Downloads')
        try:
            self.videos._copy_original(path,row,pin,folder,path.name,source_root=path.parent)
        finally:
            os.close(folder)
        return {'state':'EXPORTED','filename':path.name,'sha256':row['sha256'],'bytes':row['bytes']}


def measure_audio(path, tracks, seconds):
    evidence = {'tracks': tracks, 'speech': 'UNKNOWN' if tracks else 'NO_AUDIO_TRACK'}
    if not tracks:
        return dict(evidence, state='NO_AUDIO_TRACK')
    rate, window_ms = 8000, 500
    try:
        pcm = invoke('ffmpeg', ['-v', 'error', '-nostdin', '-protocol_whitelist', 'file,pipe', '-f', 'mov',
            '-i', str(path), '-map', '0:a:0', '-af', f'aresample={rate}:async=1:first_pts=0',
            '-ac', '1', '-t', str(seconds), '-f', 's16le', 'pipe:1'], 20)
    except WCEError:
        return dict(evidence, state='UNAVAILABLE')
    if not pcm or len(pcm) % 2:
        return dict(evidence, state='UNAVAILABLE')
    samples = array('h', pcm)
    if byteorder != 'little':
        samples.byteswap()
    step = rate * window_ms // 1000
    windows = []
    for start in range(0, len(samples), step):
        block = samples[start:start+step]
        energy = sum(value * value for value in block)
        rms = round(20 * math.log10(math.sqrt(energy / len(block)) / 32768), 1) if energy else None
        windows.append({'start_ms':start * 1000 // rate, 'end_ms':(start+len(block)) * 1000 // rate,
                        'rms_dbfs':rms, 'digital_silence':not energy})
    return dict(evidence, state='MEASURED', track_index=0, mono_pcm_hz=rate, windows=windows)
