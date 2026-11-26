"""Registered-project receipts for official music takes and authorized local media."""
from copy import deepcopy
import math
from pathlib import Path
from .audio_jobs import AudioJobs, FORMATS
from . import studio_master_bus as master
from .contracts import WCEError
from .own_connection_policy import atomic_write, locked
from .prepared_contracts import strict_validate
from .studio_projects import digest, read_json, require, studio_directory, media_pin
from .suno_panel import HANDLE, UUID
from .suno_project_download import fetch_and_import
from .tools import schema
from .video_jobs import Jobs

TOOL = 'own.music.production'
PROVIDERS = {'suno': 'Suno', 'ace-music': 'ACE'}
ID = {'type': 'string', 'pattern': r'^[A-Za-z0-9_][A-Za-z0-9_-]{0,95}$'}
DOWNLOAD = {'clip': {'type': 'string', 'pattern': UUID.pattern},
            'account': {'type': 'string', 'pattern': HANDLE.pattern},
            'format': {'type': 'string', 'enum': ['mp3', 'wav']}}
TEXT = {'type': 'string', 'maxLength': 8192, 'x-wce-maxUtf8Bytes': 32768}
TITLE = {'type': 'string', 'minLength': 1, 'maxLength': 240, 'x-wce-maxUtf8Bytes': 960}
STAGE = {'type': 'string', 'enum': ['pending', 'complete', 'error']}
BOOL = {'type': 'boolean'}
OPTIONS = schema({}, {'model': ID, 'instrumental': BOOL, 'max_mode': BOOL,
                      'duration': {'type': 'integer', 'minimum': 15, 'maximum': 360},
                      'duration_guidance': BOOL, 'duration_strict': BOOL,
                      'vocal_gender': {'type': 'string', 'enum': ['male', 'female']},
                      'controls': schema({}, {key: {'type': 'number', 'minimum': 0, 'maximum': 1}
                                              for key in ('audio_influence', 'style_influence', 'variety', 'weirdness')})})
SELECTION = {'project': ID, 'song': ID, 'version': ID}
REQUEST = {'project': ID, 'request': ID}
SPLIT = {**SELECTION, 'mode': {'type': 'string', 'enum': ['two', 'twelve']}}
CLIP = schema({'id': ID, 'state': {'type': 'string', 'enum': ['pending', 'streaming', 'complete', 'error']}},
              {'download': {'type': 'string', 'enum': ['processing', 'requires_credit', 'ready', 'unavailable', 'unknown']}})
STEM = schema({'clip': ID, 'take': {'type': 'integer', 'enum': [1, 2]}, 'part': TITLE, 'state': STAGE},
              {'attempt': ID})
FILENAME = 'production.json'
MAX_LEDGER = 2 * 1024 * 1024


def action(name, required=None, optional=None):
    return schema({'action': {'type': 'string', 'const': name}, **(required or {})}, optional)


SPECS = {
    'catalog': action('catalog'),
    'prepare': action('prepare', REQUEST | {'provider': {'type': 'string', 'enum': list(PROVIDERS)},
                      'title': TITLE, 'lyrics': TEXT, 'style': TEXT},
                      {'song': ID, 'version': ID, 'singing_lyrics': TEXT, 'negative_style': TEXT, 'account': DOWNLOAD['account'],
                       'suno_settings': OPTIONS}),
    'status': action('status', REQUEST),
    'lookup': action('lookup', SELECTION),
    'mv_source': action('mv_source', SELECTION),
    'mv_binding': action('mv_binding', {'project': ID, 'work_id': {'type': 'string', 'pattern': '^[0-9a-f]{32}$'}}),
    'start_mv': action('start_mv', SELECTION | {'window': {'oneOf': [
        {'type': 'string', 'const': 'whole_song'}, schema({k: {'type': 'integer', 'minimum': 0} for k in ('start_ms', 'end_ms')})]}}),
    'clips': action('clips', REQUEST | {'clips': {'type': 'array', 'minItems': 1, 'maxItems': 12, 'items': CLIP}}),
    'archive': action('archive', REQUEST | {'clip': ID, 'attempt': ID}),
    'stem_prepare': action('stem_prepare', SPLIT),
    'stems': action('stems', SPLIT | {'group': ID, 'state': {'type': 'string', 'enum': ['pending', 'complete', 'partial', 'error']},
                                    'stems': {'type': 'array', 'maxItems': 24, 'items': STEM}}),
    'suno_download': {'oneOf': [
        action('suno_download', REQUEST | DOWNLOAD),
        action('suno_download', SPLIT | DOWNLOAD | {'group': ID, 'take': STEM['properties']['take']}),
    ]},
}


def descriptor():
    branches = [branch for spec in SPECS.values() for branch in spec.get('oneOf', [spec])]
    return {
        'name': TOOL, 'title': 'L-unify 项目歌曲生产与归档',
        'description': 'Read and update the registered L-unify catalog, prepare an idempotent request, '
                       'resolve an exact song take as local director music with mv_source (no provider call), '
                       'record official clips and attach project audio or stems. The suno_download action asks only '
                       'for free retrieval of an already completed clip from the bound account; never sends confirm. '
                       'Use the same request or stem idempotencyKey when recovering an unknown result.',
        'inputSchema': deepcopy({'oneOf': branches}),
        'annotations': {'readOnlyHint': False, 'destructiveHint': False, 'idempotentHint': True, 'openWorldHint': False},
        '_meta': {'ui': {'visibility': ['model', 'app']}},
    }


def validate(args, kind):
    settings = args.get('suno_settings')
    controls = settings.get('controls') if type(settings) is dict else None
    if controls is None or kind != 'prepare':
        strict_validate(args, SPECS[kind])
        return
    choices = OPTIONS['properties']['controls']['properties']
    require(type(controls) is dict and set(controls) <= set(choices)
            and all(type(value) in (int, float) and 0 <= value <= 1 for value in controls.values()))
    without_controls = {key: value for key, value in settings.items() if key != 'controls'}
    strict_validate(args | {'suno_settings': without_controls}, SPECS[kind])


def ledger(folder):
    value = read_json(folder / FILENAME) if folder else None
    if value is None:
        return {'schema': 1, 'requests': {}, 'splits': {}}
    require(type(value) is dict and value.get('schema') == 1 and
            all(type(value.get(name)) is dict for name in ('requests', 'splits')), 'music_ledger_invalid', 422)
    return value


def take_id(request, clip):
    return 'take-' + digest([request, clip])[:32]


def stem_id(source, group, take):
    return 'stems-' + digest([source, group, take])[:32]


def mix_version(request, clip, receipt_date=None):
    version = {
        'id': take_id(request['request'], clip['id']), 'name': PROVIDERS[request['provider']] + ' · Take ' + str(clip['position']),
        'provider': request['provider'], 'providerClip': clip['id'], 'productionRequest': request['request'],
        'lyrics': request['lyrics'], 'tracks': [clip['track']],
    }
    archived = clip.get('archivedAt')
    if archived is None and receipt_date is not None:
        archived = receipt_date(request, clip)
    if archived is not None:
        version['archivedAt'] = archived
    return version


def stem_versions(state, source, lyrics):
    for split in state['splits'].values():
        if split['version'] != source or not split.get('group'):
            continue
        for take in (1, 2):
            stems = [row for row in split['stems'].values() if row['take'] == take]
            tracks = [row['track'] for row in stems if row.get('track')]
            if tracks:
                expected = 2 if split['mode'] == 'two' else 12
                yield {'id': stem_id(source, split['group'], take),
                       'name': f'Suno 分轨 · Take {take}', 'provider': 'suno',
                       'providerClip': split['sourceClip'], 'sourceVersion': source, 'stemGroup': split['group'],
                       'stemState': 'ready' if len(tracks) == expected else 'partial', 'lyrics': lyrics, 'tracks': tracks}


def merge_catalog(contents, state, receipt_date=None):
    """The existing catalog and production receipts share one project projection."""
    if not state['requests']:
        return contents
    songs = {row['id']: deepcopy(row) for row in contents['songs']}
    base_ids = set(songs)
    for request in sorted(state['requests'].values(), key=lambda row: row['sequence']):
        archived = [clip for clip in request['clips'].values() if clip.get('track')]
        for clip in sorted(archived, key=lambda row: row['position']):
            song = songs.setdefault(request['song'], {'id': request['song'], 'name': request['title'], 'versions': []})
            version = mix_version(request, clip, receipt_date)
            require(not any(row['id'] == version['id'] for row in song['versions']), 'music_version_conflict', 409)
            song['versions'].append(version)
            song['versions'].extend(stem_versions(state, version['id'], version['lyrics']))
            if song['id'] not in base_ids:
                song['adopted'] = version['id']
    return contents | {'songs': list(songs.values())}


class ProductionLibrary:
    def __init__(self, studio, registry, fetch=fetch_and_import):
        self.studio = studio
        self.audio = AudioJobs(Jobs(registry))
        self.fetch = fetch

    def track(self, project, provider, clip, attempt, name, identifier, *, record=None):
        if record is None:
            record = self.audio.read(attempt, project)
        require(record['kind'] == 'song' and record['provider'] == provider and
                record['provider_id'] == clip and record['seconds'] <= 1200, 'music_archive_identity_mismatch', 409)
        source, _ = self.audio.file(record)
        self.audio.pin(source, record)
        return {'id': identifier, 'name': name, 'file': record['file'], 'sha256': record['sha256'],
                'start': 0, 'sourceIn': 0, 'duration': record['seconds']}

    def archived_at(self, request, clip, record=None):
        """Read a legacy take's actual local intake time without rewriting its ledger."""
        if record is None:
            if not clip.get('attempt'):
                return None
            try:
                record = self.audio.read(clip['attempt'], request['project'])
            except (WCEError, OSError, ValueError):
                return None
        date = record.get('created_at')
        track = clip['track']
        if (type(date) in (int, float) and math.isfinite(date) and date > 0 and record.get('kind') == 'song'
                and record.get('provider') == request['provider'] and record.get('provider_id') == clip['id']
                and record.get('file') == track['file'] and record.get('sha256') == track['sha256']):
            return date
        return None

    def mv_source(self, args, resolved=None):
        key = tuple(args[field] for field in ('project', 'song', 'version'))
        root, folder, song, version = resolved or self.studio.bound(key)
        tracks = version['tracks']
        if len(tracks) > 1 or version.get('stemGroup') or tracks[0]['start'] or tracks[0]['sourceIn'] or (not version.get('mastered')
                and Path(tracks[0]['file']).suffix.lower() not in FORMATS):
            from .studio_mv_audio import soundtrack
            original = soundtrack(self.audio, root, folder, key, song, version)
            source, _ = self.audio.file(original)
            self.audio.pin(source, original)
            return {field: args[field] for field in ('project', 'song', 'version')} | {
                'title': song['name'], 'version_name': version['name'], 'provider': version.get('provider'),
                'provider_clip': version.get('providerClip'), 'source_version': version.get('sourceVersion'),
                'attempt_id': original['attempt_id'], 'sha256': original['sha256'],
                'duration_ms': round(original['seconds'] * 1000), 'lyrics': version['lyrics'],
            }
        track = tracks[0]
        if version.get('mastered'):
            receipt = master.artifact(folder, version['id'], key)
            require(receipt and receipt['id'] == version['id'] and receipt['key'][:2] == list(key[:2]),
                    'studio_version_unavailable', 404)
            relative = str((folder / version['id'] / master.MEDIA['wav']).relative_to(root))
            checksum = receipt['files']['wav']
        else:
            relative, checksum = track['file'], track['sha256']
        require(Path(relative).suffix.lower() in FORMATS, 'music_mv_compatible_mix_required')
        media_pin(root, relative, checksum)
        original = None
        if version.get('productionRequest'):
            request = ledger(folder)['requests'].get(version['productionRequest'], {})
            clip = request.get('clips', {}).get(version.get('providerClip'), {})
            if clip.get('attempt'):
                original = self.audio.read(clip['attempt'], key[0])
                require(original['kind'] == 'song' and original['sha256'] == checksum and
                        original['provider'] == version['provider'] and
                        original['provider_id'] == version['providerClip'], 'music_archive_identity_mismatch', 409)
        if original is None:
            attempt = 'mv-' + digest([*key, checksum])[:48]
            try:
                original = self.audio.read(attempt, key[0])
                require(original['kind'] == 'song' and original['sha256'] == checksum and
                        original.get('provider') == version.get('provider') and
                        original.get('provider_id') == version.get('providerClip'),
                        'music_archive_identity_mismatch', 409)
            except WCEError as error:
                if str(error) != 'AUDIO_ASSET_NOT_READY':
                    raise
                original = self.audio.ingest(attempt, key[0], song['name'] + ' · ' + version['name'],
                                             {'path': relative, 'sha256': checksum},
                                             version.get('provider'), version.get('providerClip'))
        source, _ = self.audio.file(original)
        self.audio.pin(source, original)
        return {field: args[field] for field in ('project', 'song', 'version')} | {
            'title': song['name'], 'version_name': version['name'], 'provider': version.get('provider'),
            'provider_clip': version.get('providerClip'), 'source_version': version.get('sourceVersion'),
            'attempt_id': original['attempt_id'], 'sha256': original['sha256'],
            'duration_ms': round(min(original['seconds'], track['duration']) * 1000),
            'lyrics': version['lyrics'],
        }

    def mv_binding(self, args):
        from .video_director_export import load_work
        from .studio_mv_audio import arrangement_key
        scope = {'project_id': args['project'], 'work_id': args['work_id']}
        root, state, work = load_work(self.studio.inner.director, scope)
        empty = {'project': args['project'], 'work_id': args['work_id'], 'bound': False}
        folder_path = root / 'JiuseraAssets' / 'Audio' / 'Studio'
        if not folder_path.is_dir():
            return empty
        folder = studio_directory(root)
        info = read_json(folder / ('mv-link-' + work['id'] + '.json'))
        if info is None:
            # Older works stored the selection in the work and the authenticated creation
            # receipt. Ignore free-form user text unless the same operation owns this work.
            text = work.get('sound', '')
            parts = text.removeprefix('L-unify ').split(' / ') if text.startswith('L-unify ') else []
            score = (work.get('timeline') or {}).get('music') or {}
            if len(parts) != 2 or not all(k in score for k in ('sha256', 'attempt_id', 'in_ms', 'out_ms')):
                return empty
            info = {'project': args['project'], 'song': parts[0], 'version': parts[1],
                    'source': {k: score[k] for k in ('attempt_id', 'sha256')},
                    'window': {'start_ms': score['in_ms'], 'end_ms': score['out_ms']}}
        key = [args['project'], info['song'], info['version'], info['source']['sha256'],
               info['window']['start_ms'], info['window']['end_ms']]
        operation = digest(['lunify-mv', key])[:32]
        if state['operations'].get(operation, {}).get('receipt', {}).get('work_id') != work['id']:
            return empty
        try:
            _, _, _, version = self.studio.bound(tuple(key[:3]))
        except WCEError:
            return empty
        fingerprint = info.get('arrangement')
        if fingerprint and fingerprint != arrangement_key(version):
            return empty
        if not fingerprint and not version.get('mastered') and (len(version['tracks']) != 1
                or version['tracks'][0]['sha256'] != info['source']['sha256']):
            return empty
        return empty | {k: info[k] for k in ('song', 'version', 'source', 'window')} | {'bound': True}

    def start_mv(self, args):
        from . import video_director_protocol as director
        key_selection = tuple(args[k] for k in ('project', 'song', 'version'))
        resolved = self.studio.bound(key_selection)
        music = self.mv_source(args, resolved)
        duration = music['duration_ms']
        cut = {'start_ms': 0, 'end_ms': duration} if args['window'] == 'whole_song' else args['window']
        start, end = cut['start_ms'], cut['end_ms']
        require(0 <= start < end <= duration, 'music_mv_range_invalid')
        key = [music[k] for k in ('project', 'song', 'version', 'sha256')] + [start, end]
        # A repeat click or a lost reply reopens the same cut. A later manual edit wins.
        operation = digest(['lunify-mv', key])[:32]
        scope = {'project_id': music['project']}
        protocol = self.studio.inner
        desk = self.studio.inner.director
        root, pin = desk.project(scope['project_id'])
        previous = desk.load(scope['project_id'], desk.storage(root, pin))['operations'].get(operation)
        if previous is None:
            request = {'action': 'create_work', **scope, 'operation_id': operation,
                       'fields': {'title': (music['title'][:211] + ' · MV'),
                                  'duration_ms': end - start, 'sound': 'L-unify ' + args['song'] + ' / ' + args['version']}}
            created = protocol.call(director.EDIT, request)
        else:
            created = previous['receipt']
        scope['work_id'] = created['work_id']
        timeline = protocol.call(director.READ, {'action': 'timeline', **scope})
        if timeline['timeline_version'] == 0:
            music_ref = {k: music[k] for k in ('attempt_id', 'sha256')}
            protocol.call(director.EDIT, {'action': 'timeline_save', **scope,
                'operation_id': digest(['lunify-mv-music', key])[:32], 'expected_timeline_version': 0, 'clips': [],
                'music': music_ref | {'in_ms': start, 'out_ms': end, 'start_ms': 0, 'volume': 100}})
            timeline = protocol.call(director.READ, {'action': 'timeline', **scope})
            require(timeline['timeline_version'] > 0, 'music_mv_timeline_unconfirmed')
        from .studio_mv_audio import arrangement_key
        _, folder, _, take = resolved
        info = {field: args[field] for field in ('project', 'song', 'version')}
        info.update(source={k: music[k] for k in ('attempt_id', 'sha256')}, window=cut,
                    arrangement=arrangement_key(take))
        link = folder / ('mv-link-' + scope['work_id'] + '.json')
        if read_json(link) != info:
            atomic_write(link, info)
        return scope | {'timeline_version': timeline['timeline_version'], 'music': timeline['music'],
                        'source': {k: music[k] for k in ('attempt_id', 'sha256', 'provider', 'duration_ms')},
                        'window': cut}

    def dispatch(self, args):
        kind = args.get('action') if isinstance(args, dict) else None
        require(type(kind) is str and kind in SPECS)
        validate(args, kind)
        if kind == 'catalog':
            return self.studio.catalog()
        project = args['project']
        registered = next((row for row in self.studio.registered() if row['id'] == project), None)
        require(registered is not None, 'studio_project_not_registered', 404)
        if kind == 'mv_binding':
            return self.mv_binding(args)
        if kind == 'start_mv':
            return self.start_mv(args)
        if kind == 'mv_source':
            return self.mv_source(args)
        if kind == 'suno_download':
            return self.download(registered, args)
        if kind in ('status', 'lookup'):
            _, folder, _ = self.studio.project(registered)
            state = ledger(folder)
            if kind == 'status':
                return self.status(state, args['request'])
            _, _, song, version = self.studio.bound((project, args['song'], args['version']))
            version_ids = {version['id'], version.get('sourceVersion')} - {None}
            requests = [self.status(state, row['request']) for row in state['requests'].values()
                        if row['song'] == song['id'] and (row['sourceVersion'] in version_ids
                        or row['request'] == version.get('productionRequest')
                        or any(take_id(row['request'], clip) in version_ids for clip in row['clips']))]
            splits = [self.split_status(row) for row in state['splits'].values() if row['version'] in version_ids]
            return {'project': project, 'song': song['id'], 'version': version['id'], 'title': song['name'],
                    'lyrics': version['lyrics'], 'providerClip': version.get('providerClip'), 'requests': requests, 'splits': splits}
        root, folder, _ = self.studio.project(registered)
        folder = folder or studio_directory(root, create=True)
        with locked(folder / 'production.lock'):
            state = ledger(folder)
            before = digest(state)
            if kind == 'prepare':
                result = self.prepare(state, project, args)
            elif kind == 'clips':
                result = self.record_clips(state, args)
            elif kind == 'archive':
                result = self.archive(state, args)
            else:
                result = self.split(state, project, args)
            if digest(state) != before:
                self.studio.project(registered, production_state=state)
                atomic_write(folder / FILENAME, state, maximum=MAX_LEDGER)
        return result

    @staticmethod
    def request(state, identifier):
        request = state['requests'].get(identifier)
        require(request is not None, 'music_request_unknown', 404)
        return request

    @classmethod
    def status(cls, state, identifier):
        request = cls.request(state, identifier)
        clips = [{key: value for key, value in row.items() if key not in ('track', 'archivedAt')}
                 | {'version': take_id(identifier, row['id']) if row.get('track') else None}
                 for row in sorted(request['clips'].values(), key=lambda row: row['position'])]
        return cls.production_fields(request) | {'clips': clips}

    @staticmethod
    def production_fields(request):
        return {'singing_lyrics': request['lyrics'], 'negative_style': '', 'suno_settings': {}, 'account': None} | {
            key: value for key, value in request.items() if key not in ('clips', 'sequence')
        }

    def prepare(self, state, project, args):
        request_id, song, version = args['request'], args.get('song'), args.get('version')
        require(args['title'].strip() and (version is None or song is not None))
        intent = {key: args[key] for key in ('provider', 'title', 'lyrics', 'style')}
        intent.update(singing_lyrics=args.get('singing_lyrics', args['lyrics']),
                      negative_style=args.get('negative_style', ''), suno_settings=args.get('suno_settings', {}),
                      account=args.get('account'))
        require(intent['account'] is None or intent['provider'] == 'suno')
        intent.update(project=project, request=request_id, song=song or 'song-' + digest([project, request_id])[:32],
                      sourceVersion=version, idempotencyKey='lunify-' + digest([project, request_id])[:48])
        current = state['requests'].get(request_id)
        if current:
            require(self.production_fields(current) == intent, 'music_request_conflict', 409)
        else:
            if song:
                if version:
                    self.studio.bound((project, song, version))
                else:
                    registered = next(row for row in self.studio.registered() if row['id'] == project)
                    require(any(row['id'] == song for row in self.studio.project(registered)[2]), 'music_song_unknown', 404)
            state['requests'][request_id] = intent | {'clips': {}, 'sequence': len(state['requests'])}
        return self.status(state, request_id)

    def record_clips(self, state, args):
        request = self.request(state, args['request'])
        delivered = args['clips']
        require(len({row['id'] for row in delivered}) == len(delivered))
        owned = {clip for row in state['requests'].values() if row is not request and row['provider'] == request['provider']
                 for clip in row['clips']}
        require(not (owned & {row['id'] for row in delivered}), 'music_clip_ownership_conflict', 409)
        clips = request['clips']
        require(len(clips.keys() | {row['id'] for row in delivered}) <= 12)
        for row in delivered:
            previous = clips.get(row['id'], {'position': len(clips) + 1})
            if previous.get('state') in ('complete', 'error'):
                require(row['state'] == previous['state'], 'music_clip_status_conflict', 409)
            if previous.get('state') == 'streaming' and row['state'] == 'pending':
                continue
            if previous.get('attempt'):
                row = {key: value for key, value in row.items() if key != 'download'}
            clips[row['id']] = previous | row
        return self.status(state, args['request'])

    def archive(self, state, args):
        request = self.request(state, args['request'])
        clip = request['clips'].get(args['clip'])
        require(clip is not None and clip['state'] == 'complete', 'music_clip_not_complete', 409)
        if clip.get('attempt'):
            require(args['attempt'] == clip['attempt'], 'music_archive_conflict', 409)
        record = self.audio.read(args['attempt'], args['project'])
        track = self.track(args['project'], request['provider'], clip['id'], args['attempt'], '完整混音', 'mix', record=record)
        require(clip.get('track', track) == track, 'music_archive_conflict', 409)
        clip.update(attempt=args['attempt'], track=track, download='ready')
        date = self.archived_at(request, clip, record)
        if date is not None:
            clip.setdefault('archivedAt', date)
        return {'project': args['project'], 'song': request['song'], 'version': take_id(request['request'], clip['id']),
                'state': 'archived'}

    @staticmethod
    def split_status(split):
        stems = [{key: value for key, value in row.items() if key != 'track'}
                 for row in sorted(split['stems'].values(), key=lambda row: (row['take'], row['part'].casefold()))]
        versions = {str(take): stem_id(split['version'], split['group'], take) for take in (1, 2)
                    if split.get('group') and any(row['take'] == take and row.get('track') for row in split['stems'].values())}
        return {key: value for key, value in split.items() if key != 'stems'} | {'stems': stems, 'versions': versions}

    def split(self, state, project, args):
        song, version, mode = args['song'], args['version'], args['mode']
        _, _, _, source = self.studio.bound((project, song, version))
        require(source.get('provider') == 'suno' and source.get('providerClip') and
                not source.get('sourceVersion'), 'music_suno_source_required', 422)
        identity = digest([project, song, version, mode])
        splits = state['splits']
        split = splits.setdefault(identity, {'project': project, 'song': song, 'version': version, 'mode': mode,
                                            'sourceClip': source['providerClip'], 'idempotencyKey': 'lunify-stems-' + identity[:40],
                                            'state': 'prepared', 'stems': {}})
        if args['action'] == 'stem_prepare':
            return self.split_status(split)
        require(split.get('group', args['group']) == args['group'] and
                not any(row.get('group') == args['group'] and row is not split for row in splits.values()),
                'music_stem_group_conflict', 409)
        if split['state'] in ('complete', 'partial', 'error'):
            require(split['state'] == args['state'], 'music_stem_group_status_conflict', 409)
        split.update(group=args['group'], state=args['state'])
        group = split['stems']
        incoming = args['stems']
        identifiers = {row['clip'] for row in incoming}
        parts = {(row['take'], row['part'].casefold()) for row in incoming}
        require(len(identifiers) == len(parts) == len(incoming))
        for row in incoming:
            key = digest([row['take'], row['part'].casefold()])
            previous = group.get(key, {})
            require(previous.get('clip', row['clip']) == row['clip'] and
                    not any(other != key and item['clip'] == row['clip'] for other, item in group.items()),
                    'music_stem_identity_conflict', 409)
            if previous.get('state') in ('complete', 'error'):
                require(row['state'] == previous['state'], 'music_stem_status_conflict', 409)
            if 'attempt' in row:
                require(row['state'] == 'complete' and previous.get('attempt', row['attempt']) == row['attempt'],
                        'music_stem_archive_conflict', 409)
                row = row | {'track': self.track(project, 'suno', row['clip'], row['attempt'], row['part'], 'stem-' + key[:20])}
                require(previous.get('track', row['track']) == row['track'], 'music_stem_archive_conflict', 409)
            group[key] = previous | row
        expected = 2 if mode == 'two' else 12
        require(all(sum(row['take'] == take for row in group.values()) <= expected for take in (1, 2)))
        return self.split_status(split)

    def download(self, registered, args):
        project = registered['id']
        _, folder, songs = self.studio.project(registered)
        state = ledger(folder)
        clip = args['clip']
        if 'request' in args:
            request = self.request(state, args['request'])
            row = request['clips'].get(clip)
            require(row and row['state'] == 'complete', 'music_clip_not_complete', 409)
            context = {'project': project, 'request': request['request']}
            title = request['title']
            commit = 'archive'
            target = context | {'clip': clip}
        else:
            song, version, mode = args['song'], args['version'], args['mode']
            identifier = digest([project, song, version, mode])
            split = state['splits'].get(identifier)
            require(split and split.get('group') == args['group'], 'music_stem_group_unknown', 404)
            row = next((item for item in split['stems'].values()
                        if item['clip'] == clip and item['take'] == args['take']), None)
            require(row and row['state'] == 'complete', 'music_clip_not_complete', 409)
            focus = next((item for item in songs if item['id'] == song), None)
            source = next((item for item in focus['versions'] if item['id'] == version), None) if focus else None
            require(source and source.get('providerClip') == split['sourceClip'], 'music_suno_source_required', 422)
            request = self.request(state, source.get('productionRequest'))
            title = row['part']
            commit = 'stems'
            target = {key: split[key] for key in ('project','song','version','mode','group','state')}
        require(request['provider'] == 'suno' and request.get('account') == args['account'],
                'music_suno_account_mismatch', 409)

        result = {'state': 'ready', 'attempt': row['attempt']} if row.get('attempt') else self.fetch(
            self.audio, project, clip, args['account'], title, args['format'])
        if result['state'] != 'ready':
            if commit == 'archive':
                self.dispatch(context | {'action': 'clips', 'clips': [
                    {'id': clip, 'state': 'complete', 'download': result['state']}]})
            return result
        if commit == 'archive':
            archived = self.dispatch(target | {'action': commit, 'attempt': result['attempt']})
        else:
            entry = {key: row[key] for key in ('clip','take','part','state')} | {'attempt': result['attempt']}
            archived = self.dispatch(target | {'action': commit, 'stems': [entry]})
        return result | {'archived': archived}
