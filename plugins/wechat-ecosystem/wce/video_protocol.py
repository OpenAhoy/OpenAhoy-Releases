"""OpenAhoy video tools with credential entry in the embedded management card."""
from copy import deepcopy

from .prepared_contracts import strict_validate
from .tools import schema
from .video_jobs import Jobs
from .video_inline_credential import InlineVideoCredential
from .video_keychain import status
from .video_seedance import MODEL, SUPPORTED_MODELS

CONNECTION = 'video.ark.connection.status'
SUBMIT = 'video.ark.generation.submit'
STATUS = 'video.ark.generation.status'
CREDENTIAL = 'wce.ui.video.credential'
WORKSPACE = 'wce.ui.video.workspace'
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
    action('submit', JOB | {
        'model': {'type': 'string', 'enum': list(SUPPORTED_MODELS)}, 'prompt': PROMPT,
        'mode': {'type': 'string', 'enum': ['frames', 'text', 'reference', 'edit', 'extend']},
        'duration': DURATION,
        'resolution': {'type': 'string', 'enum': ['480p', '720p', '1080p']},
        'audio': {'type': 'boolean'},
        'paths': {'type': 'array', 'minItems': 0, 'maxItems': 2,
                  'items': {'type': 'string', 'minLength': 1, 'maxLength': 4096}},
    }, {'source_attempt_id': ATTEMPT, 'source_sha256': HANDLE,
        'reference_asset': {'type': 'string', 'pattern': '^asset://[A-Za-z0-9_-]{1,128}$'},
        'direction': {'type': 'string', 'enum': ['before', 'after']}}),
]}
SPECS = {
    CONNECTION: schema({}),
    CREDENTIAL: {'oneOf': [
        schema({'action': {'type': 'string', 'const': 'begin'}}),
        schema({'action': {'type': 'string', 'const': 'submit'}, 'session': HANDLE,
                'jwe': {'type': 'string', 'minLength': 1, 'maxLength': 16384,
                        'pattern': r'^[A-Za-z0-9_-]+(?:\.[A-Za-z0-9_-]+){4}$'}}),
        schema({'action': {'type': 'string', 'const': 'cancel'}, 'session': HANDLE}),
    ]},
    WORKSPACE: WORKSPACE_SPECS,
    SUBMIT: schema(JOB | {'first_frame': FRAME, 'last_frame': FRAME, 'prompt': PROMPT},
                   {'model': {'type': 'string', 'enum': list(SUPPORTED_MODELS)}, 'duration': DURATION}),
    STATUS: schema(JOB, {'poll': {'type': 'boolean'}}),
}
DESCRIPTIONS = {
    CONNECTION: 'Read local Ark credential configuration state. Does not verify model access or return the API Key.',
    CREDENTIAL: 'App-only local Ark Key configuration. Accepts only a one-use encrypted envelope, never a plaintext Key.',
    WORKSPACE: 'App-only project-scoped video workspace, including playback bytes and user-dispatched generation.',
    SUBMIT: 'Submit one authorized billable Seedance task using two ordered PNG/JPEG originals from the registered project and their SHA-256 hashes. Default: Seedance 2.5, 5 seconds. Seedance 2.5 accepts 4–30 seconds or -1 for automatic duration. Other supported models use 5 seconds. Reuse the original generation_attempt_id, model and duration. Never submit a replacement after SUBMIT_UNKNOWN.',
    STATUS: 'Read the original Ark job receipt. With poll=true, query only the original provider task ID, check its recorded model and save its verified MP4 if ready. Does not submit generation or publish.',
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
                                   'idempotentHint': name != CREDENTIAL, 'openWorldHint': name in {SUBMIT, STATUS, WORKSPACE}}}
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
            if action == 'begin':
                return self.video_credential.begin()
            if action == 'cancel':
                return self.video_credential.cancel(arguments['session'])
            return self.video_credential.submit(arguments['session'], arguments['jwe'])
        if name == WORKSPACE:
            return self.workspace(arguments)
        attempt, project = arguments['generation_attempt_id'], arguments['project_id']
        if name == SUBMIT:
            row = self.video_jobs.submit(attempt, project, arguments['first_frame'],
                                          arguments['last_frame'], arguments['prompt'],
                                          model=arguments.get('model', MODEL), duration=arguments.get('duration', 5))
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
                     'source_attempt_id', 'source_sha256', 'reference_asset', 'direction') if key in arguments}
        workspace['paths'] = arguments['paths']
        row = job.submit(attempt, project, None, None, arguments['prompt'],
                         model=arguments['model'], workspace=workspace)
        return job.workspace_row(row)
