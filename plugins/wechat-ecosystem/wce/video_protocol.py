"""OpenAhoy video tools with credential entry in the embedded management card."""
from copy import deepcopy

from .contracts import WCEError
from .prepared_contracts import strict_validate
from .tools import schema
from .video_jobs import Jobs
from .video_inline_credential import InlineVideoCredential
from .video_keychain import PROVIDERS, status
from .video_minimax import H3, H3_MODES, RATIOS, SITES
from .video_seedance import MAX_REFERENCE_IMAGES, MODEL, SUPPORTED_MODELS

CONNECTION = 'video.ark.connection.status'
SUBMIT = 'video.ark.generation.submit'
STATUS = 'video.ark.generation.status'
CREDENTIAL = 'wce.ui.video.credential'
WORKSPACE = 'wce.ui.video.workspace'
H3_SUBMIT = 'video.minimax.generation.submit'
SITE = {'type': 'string', 'enum': list(SITES)}
RATIO = {'type': 'string', 'enum': ['adaptive', *RATIOS]}
HANDLE = {'type': 'string', 'pattern': '^[a-f0-9]{64}$'}
ATTEMPT = {'type': 'string', 'pattern': '^[A-Za-z0-9_-]{1,96}$'}
PROJECT = {'type': 'string', 'pattern': '^[a-f0-9]{32}$'}
FRAME_INDEX = {'type': 'integer', 'minimum': 0, 'maximum': 479}
FRAME = schema({'path': {'type': 'string', 'minLength': 1, 'maxLength': 4096},
                'sha256': {'type': 'string', 'pattern': '^[a-f0-9]{64}$'}})
JOB = {'generation_attempt_id': ATTEMPT, 'project_id': PROJECT}
PROMPT = {'type': 'string', 'minLength': 1, 'maxLength': 4096, 'x-wce-maxUtf8Bytes': 16384}
DURATION = {'oneOf': [{'type': 'integer', 'minimum': -1, 'maximum': -1},
                      {'type': 'integer', 'minimum': 4, 'maximum': 30}]}
def action(name, required, optional=None):
    return schema({'action': {'type': 'string', 'const': name}, **required}, optional)


ARK_OPTIONS = {
    'mode': {'type': 'string', 'enum': ['frames', 'text', 'reference', 'edit', 'extend']},
    'duration': DURATION,
    'resolution': {'type': 'string', 'enum': ['480p', '720p', '1080p']},
    'audio': {'type': 'boolean'},
    'paths': {'type': 'array', 'minItems': 0, 'maxItems': MAX_REFERENCE_IMAGES,
              'items': {'type': 'string', 'minLength': 1, 'maxLength': 4096}},
}
SOURCE_OPTIONS = {
    'source_attempt_id': ATTEMPT,
    'source_sha256': HANDLE,
    'reference_asset': {'type': 'string', 'pattern': '^asset://[A-Za-z0-9_-]{1,128}$'},
    'direction': {'type': 'string', 'enum': ['before', 'after']},
}
FRAME_OPTIONS = {
    'first_frame': FRAME, 'last_frame': FRAME,
    'reference_images': {'type': 'array', 'minItems': 1, 'maxItems': MAX_REFERENCE_IMAGES, 'items': FRAME},
    'duration': DURATION,
}
ARK_GENERATION = JOB | {'prompt': PROMPT}
ARK_MODEL = {'model': {'type': 'string', 'enum': list(SUPPORTED_MODELS)}}


WORKSPACE_SPECS = {'oneOf': [
    action('history', {}, {'project_id': PROJECT}),
    action('select', {'project_id': PROJECT, 'primary': ATTEMPT}, {'compare': ATTEMPT}),
    action('playback', JOB | {'offset': {'type': 'integer', 'minimum': 0}}),
    action('preview_frames', JOB | {'start': FRAME_INDEX}),
    action('intro_frames', {'start': FRAME_INDEX}),
    action('export', JOB),
    action('rename', JOB | {'name': {'type': 'string', 'minLength': 1, 'maxLength': 120}}),
    action('trash', JOB),
    action('restore', JOB),
    action('copy', JOB),
    action('status', JOB),
    action('submit', JOB | ARK_OPTIONS | {
        'model': {'type': 'string', 'enum': [*SUPPORTED_MODELS, H3]}, 'prompt': PROMPT,
        'mode': {'type': 'string', 'enum': [*H3_MODES, 'edit', 'extend']},
        'resolution': {'type': 'string', 'enum': ['480p', '720p', '1080p', '768P', '2K']},
    }, SOURCE_OPTIONS | {'provider_site': SITE, 'ratio': RATIO}),
]}
SPECS = {
    CONNECTION: schema({}),
    CREDENTIAL: {'oneOf': [
        action('begin', {}, {'provider': {'type': 'string', 'enum': list(PROVIDERS)}}),
        action('status', {'provider': {'type': 'string', 'enum': list(PROVIDERS)}}),
        schema({'action': {'type': 'string', 'const': 'submit'}, 'session': HANDLE,
                'jwe': {'type': 'string', 'minLength': 1, 'maxLength': 16384,
                        'pattern': r'^[A-Za-z0-9_-]+(?:\.[A-Za-z0-9_-]+){4}$'}}),
        schema({'action': {'type': 'string', 'const': 'cancel'}, 'session': HANDLE}),
    ]},
    WORKSPACE: WORKSPACE_SPECS,
    SUBMIT: schema(ARK_GENERATION, ARK_MODEL | FRAME_OPTIONS | {
        'configuration': schema(ARK_OPTIONS, SOURCE_OPTIONS),
    }),
    STATUS: schema(JOB, {'poll': {'type': 'boolean'}}),
    H3_SUBMIT: schema(JOB | {'prompt': PROMPT, 'provider_site': SITE, 'ratio': RATIO,
        'mode': {'type': 'string', 'enum': list(H3_MODES)},
        'duration': {'type': 'integer', 'minimum': 4, 'maximum': 15},
        'resolution': {'type': 'string', 'enum': ['768P', '2K']},
        'paths': {'type': 'array', 'minItems': 0, 'maxItems': 9,
                  'items': {'type': 'string', 'minLength': 1, 'maxLength': 4096}}}),
}
DESCRIPTIONS = {
    CONNECTION: 'Read local Ark credential configuration state. Does not verify model access or return the API Key.',
    CREDENTIAL: 'App-only local Ark Key configuration. Accepts only a one-use encrypted envelope, never a plaintext Key.',
    WORKSPACE: 'App-only project video history, previews, library and export. Supports legacy panel requests.',
    SUBMIT: 'Submit one authorized billable Seedance task. Supply either first_frame and last_frame or, for Seedance 2.5, 1–30 ordered reference_images. Each image needs a project-local original PNG/JPEG path and SHA-256 hash. Default: Seedance 2.5, 5 seconds. Seedance 2.5 accepts 4–30 seconds or -1 for Auto. For explicit mode, resolution or audio use configuration with mode, paths (ordered project-relative PNG/JPEG), duration, resolution and audio. Seedance 2.5 also supports text, edit and extend; edit/extend require the original source_attempt_id and source_sha256 in the same project. Reuse the original generation_attempt_id and identical inputs. Never submit a replacement after SUBMIT_UNKNOWN.',
    STATUS: 'Read the original video receipt (Ark or MiniMax). With poll=true, query only the original provider task and save its verified MP4 if ready.',
    H3_SUBMIT: 'Submit one authorized billable MiniMax H3 generation. Choose the site where the user configured a Key. Pass ordered project-relative PNG/JPEG paths: text=0, first/last=1, frames=2, reference=1–9. Text requires a concrete ratio; frame modes use adaptive. Query the original attempt with video.ark.generation.status.',
}


class VideoRouter:
    def __init__(self, inner, registry=None):
        self.inner = inner
        self.video_jobs = Jobs(registry)
        self.video_credential = InlineVideoCredential()

    def __getattr__(self, name):
        return getattr(self.inner, name)

    @property
    def _inline_probe_meta(self):
        return self.inner._inline_probe_meta

    @_inline_probe_meta.setter
    def _inline_probe_meta(self, value):
        self.inner._inline_probe_meta = value

    def list_tools(self):
        rows = self.inner.list_tools()
        for name, spec in SPECS.items():
            local_read = name == CONNECTION
            row = {'name': name, 'inputSchema': deepcopy(spec), 'description': DESCRIPTIONS[name],
                   'annotations': {'readOnlyHint': local_read, 'destructiveHint': False,
                                   'idempotentHint': name != CREDENTIAL, 'openWorldHint': name in {SUBMIT, STATUS, WORKSPACE, H3_SUBMIT}}}
            if name in (CREDENTIAL, WORKSPACE):
                row['_meta'] = {'ui': {'visibility': ['app']}}
            rows.append(row)
        return rows

    def call(self, name, arguments):
        if name not in SPECS:
            return self.inner.call(name, arguments)
        strict_validate(arguments, SPECS[name])
        if name == CONNECTION:
            return dict(status(), model=MODEL, supported_models=list(SUPPORTED_MODELS),
                        model_access='UNVERIFIED')
        if name == CREDENTIAL:
            action = arguments['action']
            if action == 'status':
                return status(provider=arguments['provider'])
            if action == 'begin':
                return self.video_credential.begin(arguments.get('provider', 'ark'))
            if action == 'cancel':
                return self.video_credential.cancel(arguments['session'])
            return self.video_credential.submit(arguments['session'], arguments['jwe'])
        if name == WORKSPACE:
            return self.workspace(arguments)
        attempt, project = arguments['generation_attempt_id'], arguments['project_id']
        if name == H3_SUBMIT:
            workspace = {k: arguments[k] for k in ('mode', 'duration', 'resolution', 'ratio', 'provider_site', 'paths')}
            row = self.video_jobs.submit(attempt, project, None, None, arguments['prompt'], model=H3, workspace=workspace)
        elif name == SUBMIT and 'configuration' in arguments:
            configuration = arguments['configuration']
            if FRAME_OPTIONS.keys() & arguments.keys() or ('direction' in configuration and configuration['mode'] != 'extend'):
                raise WCEError('VIDEO_MODE_PARAMETERS_INVALID')
            row = self.video_jobs.submit(attempt, project, None, None, arguments['prompt'],
                                         model=arguments.get('model', MODEL), workspace=configuration)
        elif name == SUBMIT:
            first, last = arguments.get('first_frame'), arguments.get('last_frame')
            images = arguments.get('reference_images')
            if (images is None and not (first and last)) or (images is not None and (first or last)):
                raise WCEError('VIDEO_MODE_PARAMETERS_INVALID')
            row = self.video_jobs.submit(attempt, project, first, last, arguments['prompt'],
                                         model=arguments.get('model', MODEL), duration=arguments.get('duration', 5),
                                         reference_images=images)
        else:
            row = self.video_jobs.status(attempt, project, arguments.get('poll', False))
        return {key: value for key, value in row.items()
                if key not in {'recipe', 'project_video_root', 'project_video_copy'}}

    def workspace(self, arguments):
        job = self.video_jobs
        command = arguments['action']
        project = arguments.get('project_id')
        attempt = arguments.get('generation_attempt_id')
        if command == 'history':
            return job.history(project)
        if command == 'select':
            return job.select_versions(project, arguments['primary'], arguments.get('compare'))
        if command == 'playback':
            return job.playback(attempt, project, arguments['offset'])
        if command in {'preview_frames', 'intro_frames'}:
            return job.preview_frames(arguments['start'], attempt, project)
        if command == 'export':
            return job.export(attempt, project)
        if command in {'rename', 'trash', 'restore', 'copy'}:
            return job.library_action(command, attempt, project, arguments.get('name'))
        if command == 'status':
            row = job.status(attempt, project, True)
            return row if row['state'] == 'NOT_FOUND' else job.workspace_row(row)
        workspace = {key: arguments[key] for key in ('mode', 'duration', 'resolution', 'audio',
                     'source_attempt_id', 'source_sha256', 'reference_asset', 'direction', 'provider_site', 'ratio') if key in arguments}
        workspace['paths'] = arguments['paths']
        row = job.submit(attempt, project, None, None, arguments['prompt'],
                         model=arguments['model'], workspace=workspace)
        return job.workspace_row(row)
