"""Project-local, versioned music recipes aided by the existing audio library."""
from copy import deepcopy
from hashlib import sha256
import json
import os
from pathlib import Path
import re

from . import music_preferences
from .contracts import WCEError
from .own_bootstrap_security import path_check
from .own_connection_policy import atomic_write, locked, read_optional
from .prepared_contracts import strict_validate
from .service import canonical, digest
from .tools import schema

TOOL = 'audio.project.presets'
FORMAT = 'jiusera.music-preset'
FOLDER = ('JiuseraAssets', 'Audio', 'Presets')
LIMIT = 131072
PROJECT = {'type': 'string', 'pattern': r'[a-f0-9]{32}'}
ID = {'type': 'string', 'pattern': r'[a-z0-9][a-z0-9_-]{0,63}'}
ATTEMPT = {'type': 'string', 'pattern': r'[A-Za-z0-9_-]{1,96}'}
REV = {'type': 'integer', 'minimum': 1, 'maximum': 999999}
EXPECTED = REV | {'minimum': 0}
SHA = {'type': 'string', 'pattern': r'[a-f0-9]{64}'}
BOOL = {'type': 'boolean'}
PROVIDER = {'type': 'string', 'enum': list(music_preferences.PROVIDERS)}


def string(limit, minimum=0):
    return {'type': 'string', 'minLength': minimum, 'maxLength': limit,
            'x-wce-maxUtf8Bytes': limit * 4}


def choices(*values):
    return {'type': 'string', 'enum': list(values)}


def array(spec, maximum):
    return {'type': 'array', 'items': spec, 'maxItems': maximum}


def action(name, required, optional=None):
    return schema({'action': {'type': 'string', 'const': name}, 'project_id': PROJECT, **required}, optional)


MODE = {'type': 'string', 'const': 'custom'}
ACE_ARGS = schema({'style': string(1000, 1)}, {
    'title': string(80, 1), 'lyrics': string(5000),
    'model': choices('acemusic-v1', 'acemusic-v1.1'),
    'duration_sec': {'type': 'integer', 'minimum': 30, 'maximum': 600},
})
SUNO_ARGS = schema({'title': string(120, 1), 'style': string(1000, 1), 'instrumental': BOOL},
                   {'lyrics': string(5000), 'negative_style': string(1000, 1), 'model': string(120, 1)})
DIRECTIONS = schema({
    'suno': schema({'mode': MODE} | {key: SUNO_ARGS['properties'][key] for key in SUNO_ARGS['required']},
                   {key: SUNO_ARGS['properties'][key] for key in ('lyrics', 'negative_style', 'model')}),
    'ace-music': schema({'mode': MODE, 'style': ACE_ARGS['properties']['style']},
                       {key: ACE_ARGS['properties'][key] for key in ('title', 'lyrics', 'model', 'duration_sec')}),
})
BRIEF = schema({'scene': string(2000), 'sound': string(2000, 1),
                'vocals': choices('instrumental', 'lyrics'), 'cueNotes': array(string(480, 1), 16)})
RECIPE = {'name': string(120, 1), 'use': choices('video_score', 'song'), 'brief': BRIEF,
          'providerDirections': DIRECTIONS}
SHOT = schema({key: PROJECT for key in ('work_id', 'scene_id', 'shot_id', 'revision_id')})
VARIANT = schema({'id': ID, 'audio_attempt': ATTEMPT}, {
    'model': string(120, 1), 'actual_input': {'oneOf': [SUNO_ARGS, ACE_ARGS]},
})
FEEDBACK = {'variant_id': ID, 'rating': choices('liked', 'adjust', 'adopted'),
            'note': string(1000, 1), 'source': choices('user', 'test')}
SCOPE = {'id': ID}
SPEC = {'oneOf': [
    action('list', {}),
    action('read', SCOPE, {'revision': REV}),
    action('save', SCOPE | {'expected_revision': EXPECTED, 'recipe': schema(RECIPE)},
           {'variants': array(VARIANT, 16)}),
    action('import', SCOPE | {'preset_text': string(22000, 1)}),
    action('feedback', SCOPE | {'expected_revision': REV, **FEEDBACK}),
    action('use', SCOPE | {'expected_revision': REV, 'variant_id': ID, 'shot': SHOT}),
    action('restore', SCOPE | {'expected_revision': REV, 'revision': REV}),
    action('payload', SCOPE, {'revision': REV, 'provider': PROVIDER}),
    action('export', SCOPE, {'revision': REV, 'include_lyrics': BOOL}),
]}
PORTABLE_STATUS = choices('example', 'shareable')
PRIVATE_TEXT = re.compile(r'(?i)(?:file://|(?:^|[\s"=(])(?:/(?:Users|Volumes|private|home|var|tmp)/|~[/\\]|[a-z]:[\\/]))')


def require(ok, code='MUSIC_PRESET_INVALID'):
    if not ok:
        raise WCEError(code)


def provider_payload(recipe, provider, *, allow_missing_lyrics=False):
    supplied = {key: value for key, value in recipe['providerDirections'][provider].items()
                if key != 'mode'}
    instrumental = recipe['brief']['vocals'] == 'instrumental'
    if provider == 'suno':
        require(supplied['instrumental'] == instrumental)
    if instrumental:
        require(not supplied.pop('lyrics', '').strip())
    else:
        require(allow_missing_lyrics or supplied.get('lyrics', '').strip(), 'MUSIC_PRESET_LYRICS_REQUIRED')
    if provider == 'ace-music':
        require('duration_sec' not in supplied or supplied.get('model', 'acemusic-v1') == 'acemusic-v1',
                'MUSIC_PRESET_ACE_DURATION_REQUIRES_V1')
    strict_validate(supplied, SUNO_ARGS if provider == 'suno' else ACE_ARGS)
    return supplied


def verify_recipe(recipe, *, allow_missing_lyrics=False):
    strict_validate(recipe, schema(RECIPE))
    for provider in music_preferences.PROVIDERS:
        provider_payload(recipe, provider, allow_missing_lyrics=allow_missing_lyrics)


def portable_read(text):
    def unique(items):
        result = dict(items)
        require(len(result) == len(items))
        return result
    try:
        row = json.loads(text, object_pairs_hook=unique)
    except (ValueError, RecursionError):
        raise WCEError('MUSIC_PRESET_INVALID') from None
    require(type(row) is dict and row.get('format') == FORMAT)
    require(type(row.get('formatVersion')) is int and row['formatVersion'] == 1,
            'MUSIC_PRESET_FORMAT_UNSUPPORTED')
    require(set(row) == set(RECIPE) | {'format', 'formatVersion', 'id', 'revision', 'status',
                                     'feedback', 'approvedVariants', 'preview'})
    strict_validate(row['id'], ID)
    strict_validate(row['revision'], REV)
    strict_validate(row['status'], PORTABLE_STATUS)
    require(row['preview'] is None and row['feedback'] == [] and row['approvedVariants'] == [])
    recipe = {field: row[field] for field in RECIPE}
    verify_recipe(recipe, allow_missing_lyrics=True)
    return recipe


class Presets:
    def __init__(self, router):
        self.audio = router.inner.audio_jobs
        self.director = router.director

    def folder(self, project, extra=(), *, create=False):
        root, pin = self.director.project(project)
        path = root.joinpath(*FOLDER, *extra)
        try:
            descriptor = self.audio.videos._project_video_folder(
                {'root': str(root)}, list(pin), create=create, components=FOLDER + extra)
        except FileNotFoundError:
            if not create:
                return None
            raise WCEError('MUSIC_PRESET_PROJECT_UNAVAILABLE') from None
        except OSError:
            raise WCEError('MUSIC_PRESET_PROJECT_UNAVAILABLE') from None
        os.close(descriptor)
        return path

    def read(self, folder, identifier, revision=None):
        if folder is None:
            return None
        if revision is None:
            latest = max((int(match[1]) for path in folder.glob('v*.jmusic')
                          if (match := re.fullmatch(r'v([1-9][0-9]{0,5})\.jmusic', path.name))), default=0)
            if not latest:
                return None
            revision = latest
        stored = read_optional(folder / f'v{revision}.jmusic', LIMIT)
        if stored is None:
            return None
        require(type(stored) is dict and stored.get('format') == FORMAT
                and stored.get('formatVersion') == 1, 'MUSIC_PRESET_FORMAT_UNSUPPORTED')
        require(stored.get('id') == identifier and stored.get('revision') == revision)
        return stored

    def variants(self, project, requested):
        rows = []
        require(len({item['id'] for item in requested}) == len(requested))
        require(len({item['audio_attempt'] for item in requested}) == len(requested))
        for item in requested:
            audio = self.audio.read(item['audio_attempt'], project)
            require(audio['mime'].startswith('audio/'), 'MUSIC_PRESET_AUDIO_REQUIRED')
            source, _ = self.audio.file(audio)
            self.audio.pin(source, audio)
            if 'actual_input' in item:
                require(audio.get('provider') in music_preferences.PROVIDERS)
                strict_validate(item['actual_input'], SUNO_ARGS if audio['provider'] == 'suno' else ACE_ARGS)
            rows.append(item | {key: audio.get(key) for key in
                               ('provider', 'provider_id', 'sha256', 'title', 'mime', 'seconds', 'bytes')})
        return rows

    def run(self, args):
        strict_validate(args, SPEC)
        command, project = args['action'], args['project_id']
        if command == 'list':
            base = self.folder(project)
            presets = []
            if base is not None:
                for child in sorted(base.iterdir()):
                    if child.name != 'exports' and re.fullmatch(ID['pattern'], child.name):
                        folder = self.folder(project, (child.name,))
                        row = self.read(folder, child.name)
                        if row is not None:
                            presets.append({key: row[key] for key in ('id', 'revision', 'name', 'use')})
            return {'state': 'MUSIC_PRESETS', 'presets': presets}
        identifier = args['id']
        require(identifier != 'exports')
        if command in ('read', 'payload', 'export'):
            folder = self.folder(project, (identifier,))
            row = self.read(folder, identifier, args.get('revision'))
            require(row is not None, 'MUSIC_PRESET_NOT_FOUND')
            if command == 'read':
                return {'state': 'MUSIC_PRESET_READ', 'preset': row, 'sha256': digest(row)}
            if command == 'payload':
                return self.payload(row, args.get('provider'))
            return self.export(project, row, args.get('include_lyrics', False))

        expected = args.get('expected_revision', 0)
        folder = self.folder(project, (identifier,), create=expected == 0)
        require(folder is not None, 'MUSIC_PRESET_NOT_FOUND')
        with locked(folder / 'presets.lock'):
            pin = path_check(folder, True)
            current = self.read(folder, identifier)
            request = digest(args)
            if current and current.get('request_sha256') == request:
                return {'state': 'MUSIC_PRESET_SAVED', 'preset': current, 'sha256': digest(current)}
            require(expected == (current['revision'] if current else 0), 'MUSIC_PRESET_STALE_REVISION')
            if command in ('save', 'import'):
                recipe = args['recipe'] if command == 'save' else portable_read(args['preset_text'])
                verify_recipe(recipe, allow_missing_lyrics=command == 'import')
                variants = self.variants(project, args['variants']) if 'variants' in args else (current or {}).get('variants', [])
                retained = {item['id']: item for item in variants}
                # Names remain permanent candidate identities once a candidate is recorded.
                require(all(retained.get(item['id']) == item for item in (current or {}).get('variants', [])),
                        'MUSIC_PRESET_CANDIDATE_CHANGED')
                row = (current or {'feedback': [], 'uses': []}) | recipe | {'variants': variants}
            elif command == 'restore':
                row = self.read(folder, identifier, args['revision'])
                require(row is not None, 'MUSIC_PRESET_NOT_FOUND')
                # Restore the editable recipe while retaining candidate/feedback history.
                row = current | {key: row[key] for key in RECIPE}
            else:
                row = deepcopy(current)
                if command == 'feedback':
                    candidate = next((item for item in row['variants'] if item['id'] == args['variant_id']), None)
                    require(candidate is not None, 'MUSIC_PRESET_CANDIDATE_NOT_FOUND')
                    row['feedback'].append({key: args[key] for key in FEEDBACK}
                                           | {'audio_sha256': candidate['sha256'], 'at_revision': expected})
                else:
                    candidate = next((item for item in row['variants'] if item['id'] == args['variant_id']), None)
                    require(candidate is not None, 'MUSIC_PRESET_CANDIDATE_NOT_FOUND')
                    live = self.audio.read(candidate['audio_attempt'], project)
                    require(live['sha256'] == candidate['sha256'], 'MUSIC_PRESET_AUDIO_CHANGED')
                    source, _ = self.audio.file(live)
                    self.audio.pin(source, live)
                    self.director.context({'project_id': project, **args['shot']})
                    link = dict(args['shot'], variant_id=candidate['id'], audio_attempt=candidate['audio_attempt'],
                                audio_sha256=candidate['sha256'], preset_revision=expected)
                    if link not in row['uses']:
                        row['uses'].append(link)
            revision = expected + 1
            strict_validate(revision, REV)
            row.update(format=FORMAT, formatVersion=1, id=identifier, revision=revision,
                       status='private', request_sha256=request)
            atomic_write(folder / f'v{revision}.jmusic', row, LIMIT, expected_parent=pin)
            return {'state': 'MUSIC_PRESET_SAVED', 'preset': row, 'sha256': digest(row)}

    def payload(self, row, provider):
        choice = music_preferences.read(self.audio.videos.projects.root)
        if provider is None:
            require(choice['state'] == 'READY', 'MUSIC_PREFERENCES_UNAVAILABLE')
            provider = choice['provider']
        return {'state': 'MUSIC_PRESET_PAYLOAD', 'provider': provider, 'revision': row['revision'],
                'tool_name': 'audio_create' if provider == 'suno' else 'create_song',
                'arguments': provider_payload(row, provider)}

    def export(self, project, row, include_lyrics):
        portable = deepcopy({key: row[key] for key in (*RECIPE, 'format', 'formatVersion', 'id', 'revision')})
        # Shareable lyrics are an explicit separate choice. If removed, the recipe
        # remains a usable songwriting brief and can be completed after import.
        for provider in portable['providerDirections'].values():
            if not include_lyrics:
                provider.pop('lyrics', None)
        private_tokens = {entry['provider_id'] for entry in row['variants'] if entry['provider_id']}
        private_tokens.update(entry['audio_attempt'] for entry in row['variants'])
        private_tokens.add(project)
        private_tokens.update(ref[key] for ref in row['uses']
                              for key in ('work_id', 'scene_id', 'shot_id', 'revision_id'))
        text = canonical({key: portable[key] for key in ('name', 'brief', 'providerDirections')})
        # Very short local attempts can also be ordinary prose (e.g. "song").
        require(not PRIVATE_TEXT.search(text)
                and not any(re.search(r'(?<![\w-])' + re.escape(token) + r'(?![\w-])', text)
                            for token in private_tokens if len(token) >= 12),
                'MUSIC_PRESET_EXPORT_CONTAINS_PRIVATE_REFERENCE')
        portable.update(status='shareable', feedback=[], approvedVariants=[], preview=None)
        base = self.folder(project, ('exports',), create=True)
        suffix = 'with-lyrics' if include_lyrics and row['brief']['vocals'] == 'lyrics' else 'recipe'
        name = f"{row['id']}-v{row['revision']}-{suffix}.jmusic"
        with locked(base / 'presets.lock'):
            file = base / name
            existing = read_optional(file, LIMIT)
            require(existing in (None, portable), 'MUSIC_PRESET_EXPORT_CONFLICT')
            if existing is None:
                atomic_write(file, portable, LIMIT)
        return {'state': 'MUSIC_PRESET_EXPORTED', 'relative_path': str(Path(*FOLDER, 'exports', name)),
                'sha256': sha256((canonical(portable) + '\n').encode()).hexdigest(),
                'official_status': 'NOT_SELECTED'}
