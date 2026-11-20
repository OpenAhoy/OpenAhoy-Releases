"""Native Codex and MCP App entry points for the project-local director desk."""
from copy import deepcopy
from functools import lru_cache, partial
import json
from pathlib import Path
import tempfile

from .contracts import WCEError
from .prepared_contracts import strict_validate
from .tools import schema
from .video_director import Director, canvas_state, lookup, require
from . import video_director_delivery as delivery
from . import character_library as characters
from .video_director_media import (CATALOG, IMAGE_CHUNK, IMAGE_ROLES, compute_request, import_image_chunk, models, preview_image,
                                   preview_result, preview_whitebox, validate_revision)
from .video_protocol import ATTEMPT, FRAME, FRAME_INDEX, HANDLE, PROJECT, RELAY_URL, RELAY_IMAGES, RELAY_AUDIO, action
from .video_seedance import MAX_REFERENCE_IMAGES
from .video_jobs import FRAME_LIMIT

READ = 'video.director.read'
EDIT = 'video.director.edit'
MEDIA = 'wce.ui.video.director.media'
PROJECT_ARG = {'project_id': PROJECT}
WORK_ARG = PROJECT_ARG | {'work_id': PROJECT}
SCENE_ARG = WORK_ARG | {'scene_id': PROJECT}
SHOT_ARG = SCENE_ARG | {'shot_id': PROJECT}
TARGET = SHOT_ARG | {'revision_id': PROJECT}
WRITE = {'operation_id': PROJECT}
MS = {'type': 'integer', 'minimum': 0, 'maximum': 2**53 - 1}
ORDINAL = {'type': 'integer', 'minimum': 0}
TEXT = {'type': 'string', 'maxLength': 65536}
TITLE = {'type': 'string', 'minLength': 1, 'maxLength': 240, 'x-wce-maxUtf8Bytes': 960}
RATIO = {'type': 'string', 'enum': ['adaptive', '21:9', '16:9', '4:3', '1:1', '3:4', '9:16']}
SOURCE = schema(PROJECT_ARG | {'attempt_id': ATTEMPT, 'sha256': HANDLE})
FILE = schema(PROJECT_ARG | FRAME['properties'])
NAME_FIELDS = {'title': TITLE}
WORK_TEXT = ('brief', 'platform', 'audience', 'tone', 'references', 'style', 'caption_safe_area', 'sound')
WORK_OPTIONS = {key: TEXT for key in WORK_TEXT} | {'duration_ms': MS, 'ratio': RATIO}
ORIGIN = {'type': 'string', 'enum': ['panel', 'codex']}
CARD = schema({'id': {'type': 'string', 'pattern': '^[a-z0-9-]+$', 'maxLength': 80},
               'version': {'type': 'integer', 'minimum': 1}})
CONFIG = schema({
    'provider': {'type': 'string', 'enum': ['ark', 'cn', 'global', 'relay', 'tokenhex']},
    'model': {'type': 'string', 'maxLength': 160, 'minLength': 1},
    'mode': {'type': 'string', 'enum': ['text', 'first', 'last', 'frames', 'reference', 'edit', 'extend', 'subject', 'workflow']},
}, {'duration': {'type': 'integer', 'minimum': -1, 'maximum': 30},
    'resolution': {'type': 'string', 'maxLength': 20, 'minLength': 1}, 'ratio': RATIO,
    'subject_image_url': RELAY_URL, 'reference_images': RELAY_IMAGES, 'reference_audio': RELAY_AUDIO, 'audio': {'type': 'boolean'}, 'direction': {'type': 'string', 'enum': ['before', 'after']},
    'source': schema(SOURCE['properties'], {'reference_asset': {
        'type': 'string', 'pattern': '^asset://[A-Za-z0-9_-]{1,128}$', 'maxLength': 136}})})
WHITEBOX = schema({'mode': {'type': 'string', 'enum': ['none', 'plan', 'import']}},
                  {key: TEXT for key in ('camera_path', 'subject_path', 'key_points')} | {'file': FILE})
REVISION_TEXT = ('purpose', 'subjects', 'opening', 'action', 'ending', 'transition', 'composition',
                 'camera', 'lens', 'focus', 'lighting', 'color', 'sound', 'review', 'prompt', 'notes')
REVISION_OPTIONS = {key: TEXT for key in REVISION_TEXT} | {
    'title': TITLE, 'start_ms': MS, 'end_ms': MS, 'ratio': RATIO,
    'cards': {'type': 'array', 'items': CARD},
    'images': {'type': 'array', 'items': schema({
        'role': {'type': 'string', 'enum': list(IMAGE_ROLES)}, 'file': FILE}, {'asset_version': characters.ID})},
    'configuration': CONFIG, 'whitebox': WHITEBOX, 'result': SOURCE,
}

POSITION = schema({
    'x': {'type': 'integer', 'minimum': -1000000, 'maximum': 1000000},
    'y': {'type': 'integer', 'minimum': -1000000, 'maximum': 1000000},
})
VIEWPORT = schema(POSITION['properties'] | {'scale': {'type': 'integer', 'minimum': 10, 'maximum': 250}})
CANVAS_WRITE = WORK_ARG | WRITE | {'expected_canvas_version': ORDINAL}
FAMILY = {'type': 'string', 'enum': ['video', 'gif', 'audio']}
CANVAS_NODE = {'oneOf': [
    schema({'kind': {'const': 'note', 'type': 'string'}, 'title': TITLE, 'text': TEXT}, {'shot_id': PROJECT}),
    schema({'kind': {'const': 'image', 'type': 'string'}, 'title': TITLE, 'file': FILE}, {'shot_id': PROJECT}),
    schema({'kind': {'const': 'asset', 'type': 'string'}, 'title': TITLE,
            'asset': schema(SOURCE['properties'] | {'family': FAMILY}, {
                'media_kind': {'type': 'string', 'enum': ['video', 'gif', 'audio']}})}, {'shot_id': PROJECT}),
]}


SPECS = {
    READ: {'oneOf': [
        action('projects', {}),
        action('character_library', {}),
        action('character_import_preview', PROJECT_ARG | {'source': characters.SOURCE}),
        action('overview', PROJECT_ARG, {'work_id': PROJECT}),
        action('context', TARGET),
        action('deliveries', WORK_ARG),
        action('preflight', TARGET),
        action('models', {}, {'refresh_tokenhex': {'type': 'boolean'}}),
        action('cards', {}, {'card_id': CARD['properties']['id']}),
    ]},
    EDIT: {'oneOf': [
        action('character_import', PROJECT_ARG | {'source': characters.SOURCE, 'expected_revision': ORDINAL}),
        action('character_set_current', PROJECT_ARG | characters.SELECTOR, {'expected_current': characters.ID}),
        action('create_work', PROJECT_ARG | WRITE | {'fields': schema(NAME_FIELDS, WORK_OPTIONS)}),
        action('edit_work', WORK_ARG | WRITE | {'expected_version': ORDINAL,
                                              'fields': schema({}, NAME_FIELDS | WORK_OPTIONS)}),
        action('select_work', WORK_ARG | WRITE),
        action('poll_delivery', WORK_ARG | {'attempt_id': ATTEMPT}),
        action('track_generation', TARGET | WRITE | {'attempt_id': ATTEMPT}),
        action('register_work_video', WORK_ARG | WRITE | {'file': FILE, 'title': TITLE}),
        action('adopt_video', SHOT_ARG | WRITE | {'candidate_id': PROJECT, 'sha256': HANDLE},
               {'expected_candidate_id': PROJECT}),
        action('canvas_view', CANVAS_WRITE | {'viewport': VIEWPORT}),
        action('canvas_add', CANVAS_WRITE | {'node': CANVAS_NODE, 'position': POSITION}),
        action('canvas_note_edit', CANVAS_WRITE | {'node_id': PROJECT, 'title': TITLE, 'text': TEXT}),
        action('canvas_move', CANVAS_WRITE | {'node_id': PROJECT, 'position': POSITION}),
        action('canvas_remove', CANVAS_WRITE | {'node_id': PROJECT}),
        action('create_scene', WORK_ARG | WRITE | NAME_FIELDS | {'start_ms': MS, 'end_ms': MS}),
        action('select_scene', SCENE_ARG | WRITE),
        action('create_shot', SCENE_ARG | WRITE | NAME_FIELDS, {'origin': ORIGIN}),
        action('revise', SHOT_ARG | WRITE | {'base_revision': PROJECT,
                                           'fields': schema({}, REVISION_OPTIONS)}, {'origin': ORIGIN}),
        action('select_revision', TARGET | WRITE),
        action('adopt', TARGET | WRITE | {'base_revision': PROJECT}, {'expected_adopted': PROJECT}),
    ]},
    MEDIA: {'oneOf': [
        action('character_thumbnail', PROJECT_ARG | characters.SELECTOR | {'sha256': HANDLE}),
        action('character_original', PROJECT_ARG | characters.SELECTOR | {'sha256': HANDLE, 'offset': ORDINAL}),
        action('work_video_chunk', WORK_ARG | {'delivery_id': PROJECT, 'offset': MS}),
        action('canvas_video_chunk', WORK_ARG | {'delivery_id': PROJECT, 'sha256': HANDLE, 'offset': MS}),
        action('canvas_video_frames', WORK_ARG | {'delivery_id': PROJECT, 'sha256': HANDLE, 'start': FRAME_INDEX}),
        action('import_image_chunk', WORK_ARG | {
            'sha256': HANDLE, 'offset': {'type': 'integer', 'minimum': 0, 'maximum': FRAME_LIMIT-1},
            'total': {'type': 'integer', 'minimum': 1, 'maximum': FRAME_LIMIT-1},
            'data': {'type': 'string', 'minLength': 4, 'maxLength': 4*((IMAGE_CHUNK+2)//3)},
        }),
        action('canvas_image', WORK_ARG | {'node_id': PROJECT}, {'thumbnail': {'type': 'boolean'}}),
        action('image', TARGET, {'index': ORDINAL, 'thumbnail': {'type': 'boolean'}}),
        action('whitebox', TARGET),
        action('whitebox_frames', TARGET | {'start': FRAME_INDEX}),
        action('result', TARGET),
        action('result_frames', TARGET | {'start': FRAME_INDEX}),
    ]},
}
DESCRIPTIONS = {
    READ: 'Read project storyboards, one exact shot revision, shared model/channel options, original-work delivery status, local preflight, built-in video-director cards, or registered character reference versions. Refresh Token Hex only when explicitly requested. Preflight only validates local input and encoding; no generation.',
    EDIT: 'Create or revise a storyboard in a registered local project. Manage canvas layout, exact shot generation bindings and work-level local MP4 delivery. Character_import records a verified project-local JSON index. Character_set_current changes one role pointer using the observed version. Adopt_video selects an exact verified take for one shot without changing its storyboard revision. Read deliveries for candidate IDs and the current adoption. Poll_delivery may query the original provider and save its result. Other actions are local. No action submits generation. Use a fresh operation_id, and for revise give the exact current base_revision. Set origin=codex for chat changes. Use project-relative files with project_id and SHA-256.',
    MEDIA: 'App-only local image import and verified storyboard image, whitebox or completed clip previews.',
}


@lru_cache(maxsize=1)
def prompt_cards():
    return json.loads(CATALOG.read_bytes())


class DirectorRouter:
    def __init__(self, inner):
        self.inner = inner
        self.jobs = inner.video_jobs
        self.director = Director(self.jobs.projects)
        self.characters = characters.CharacterLibrary(self.director)

    def __getattr__(self, name):
        return getattr(self.inner, name)

    @property
    def _inline_probe_meta(self):
        return self.inner._inline_probe_meta

    @_inline_probe_meta.setter
    def _inline_probe_meta(self, value):
        self.inner._inline_probe_meta = value

    def list_tools(self):
        descriptions = []
        for name, spec in SPECS.items():
            row = {'name': name, 'description': DESCRIPTIONS[name], 'inputSchema': deepcopy(spec),
                   'annotations': {'readOnlyHint': name == READ, 'destructiveHint': False,
                                   'idempotentHint': True, 'openWorldHint': name in (READ, EDIT)}}
            if name == MEDIA:
                row['_meta'] = {'ui': {'visibility': ['app']}}
            descriptions.append(row)
        return self.inner.list_tools() + descriptions

    def call(self, name, args):
        if name not in SPECS:
            return self.inner.call(name, args)
        strict_validate(args, SPECS[name])
        command = args['action']
        if command == 'character_library':
            return self.characters.list()
        if command == 'character_import_preview':
            return self.characters.preview(args['project_id'], args['source'])
        if command in ('character_import', 'character_set_current'):
            return self.characters.edit(args)
        if command in ('character_thumbnail', 'character_original'):
            return self.characters.media(args)
        if name == EDIT and command != 'poll_delivery':
            return self.director.edit(args, partial(validate_revision, self.jobs), self.verify_canvas_node, self.jobs)
        if command == 'projects':
            return {'projects': self.director.registered()}
        if command == 'overview':
            return self.director.overview(args['project_id'], args.get('work_id'))
        if command == 'cards':
            catalog = prompt_cards()
            if 'card_id' not in args:
                return deepcopy(catalog)
            card = next((row for row in catalog['cards'] if row['id'] == args['card_id']), None)
            require(card, 'DIRECTOR_UNKNOWN_CARD')
            return deepcopy(card)
        if command == 'models':
            if args.get('refresh_tokenhex'):
                try:
                    return models(self.jobs.tokenhex_check())
                except (WCEError, OSError):
                    return models({'state': 'CHECK_UNAVAILABLE', 'models': []})
            return models()
        if command == 'import_image_chunk':
            try:
                return import_image_chunk(self.director, args)
            except OSError:
                raise WCEError('DIRECTOR_IMAGE_IMPORT_UNAVAILABLE') from None
        if command in ('deliveries', 'poll_delivery', 'work_video_chunk', 'canvas_video_chunk', 'canvas_video_frames'):
            project = args['project_id']
            root, pin = self.director.project(project)
            state = self.director.load(project, self.director.storage(root, pin))
            work = lookup(state['works'], args['work_id'], 'DIRECTOR_WORK_NOT_FOUND')
            if command == 'work_video_chunk':
                return delivery.chunk(root, work, args)
            if command in ('canvas_video_chunk', 'canvas_video_frames'):
                return delivery.playback(self.jobs, root, work, args)
            return {'project_id': project, 'work_id': work['id'], 'version': state['version'],
                    'cards': delivery.collect(self.jobs, root, project, work, poll_attempt=args.get('attempt_id'))}
        if command == 'canvas_image':
            root, pin = self.director.project(args['project_id'])
            state = self.director.load(args['project_id'], self.director.storage(root, pin))
            work = lookup(state['works'], args['work_id'], 'DIRECTOR_WORK_NOT_FOUND')
            node = lookup(canvas_state(work)['nodes'], args['node_id'], 'DIRECTOR_CANVAS_NODE_NOT_FOUND')
            require(node['kind'] == 'image' and node['file']['project_id'] == args['project_id'],
                    'DIRECTOR_ASSET_WRONG_PROJECT')
            return preview_image(root, node['file'], args.get('thumbnail', False))
        context = self.director.context(args)
        if command == 'context':
            return context
        root, _ = self.director.project(args['project_id'])
        if command == 'preflight':
            with tempfile.TemporaryDirectory(prefix='openahoy-director-') as folder:
                request = compute_request(self.jobs, context, root, Path(folder))
            provider = request['provider']
            connected = models()['connections'][provider]
            return {'state': 'PREFLIGHT_VALID', 'connection': connected, 'project_id': args['project_id'],
                    'revision_id': args['revision_id'], 'request': request,
                    'provider_access_verified': False}
        revision = context['revision']
        if command == 'image':
            images = revision['images']
            require(images, 'DIRECTOR_IMAGE_UNAVAILABLE')
            index = args.get('index', next((i for i, row in enumerate(images)
                                          if row['role'] == 'composition'), 0))
            require(0 <= index < len(images), 'DIRECTOR_IMAGE_UNAVAILABLE')
            spec = images[index]['file']
            require(spec['project_id'] == args['project_id'], 'DIRECTOR_ASSET_WRONG_PROJECT')
            return preview_image(root, spec, args.get('thumbnail', False))
        if command in ('whitebox', 'whitebox_frames'):
            spec = (revision['whitebox'] or {}).get('file')
            require(spec and spec['project_id'] == args['project_id'], 'DIRECTOR_WHITEBOX_FILE_REQUIRED')
            return preview_whitebox(root, spec, args.get('start'))
        spec = revision['result']
        require(spec and spec['project_id'] == args['project_id'], 'DIRECTOR_RESULT_UNAVAILABLE')
        return preview_result(self.jobs, args['project_id'], spec, args.get('start'))

    def verify_canvas_node(self, node, root, project_id):
        if node['kind'] == 'note':
            from .project_context import text as project_text
            project_text(node['text'])
            return
        if node['kind'] == 'image':
            require(node['file']['project_id'] == project_id, 'DIRECTOR_ASSET_WRONG_PROJECT')
            preview_image(root, node['file'], True)
            return
        spec = node['asset']
        require(spec['project_id'] == project_id, 'DIRECTOR_ASSET_WRONG_PROJECT')
        attempt, family = spec['attempt_id'], spec['family']
        if family == 'video':
            _, media, _ = self.jobs._playable(attempt, project_id)
        elif family == 'gif':
            row, _, _ = self.inner.gif_jobs.available(attempt, project_id)
            media = row['asset']
        else:
            audio = self.inner.audio_jobs
            media = audio.read(attempt, project_id)
            source, _ = audio.file(media)
            audio.pin(source, media)
        kind = 'video' if family == 'audio' and media['kind'] != 'song' else family
        require(media['sha256'] == spec['sha256'] and spec.get('media_kind', kind) == kind,
                'DIRECTOR_ASSET_CHANGED')
