"""Jiusera video tools with credential entry in the embedded management card."""
from copy import deepcopy

from .contracts import WCEError
from .media_library import LIBRARY_ID
from . import music_preferences
from .audio_jobs import AudioJobs
from .openai_gif_jobs import GifJobs
from .openai_gif_keychain import PROVIDER as GIF_PROVIDER, status as gif_status
from .prepared_contracts import strict_validate
from .tools import schema
from .video_jobs import Jobs
from .video_inline_credential import InlineVideoCredential
from .video_keychain import PROVIDERS, status
from .video_minimax import H3, H3_MODELS, SUBJECT_MODEL, V1_MODELS, H3_MODES, RATIOS, SITES
from .video_relay import RESOLUTIONS
from . import video_autodl_catalog as autodl
from .video_provider_ui import directory as provider_directory
from .video_relay_keychain import relay_status
from .video_tokenhex import TOKENHEX_PROVIDER, tokenhex_status
from .video_seedance import MAX_REFERENCE_IMAGES, MODEL, SUPPORTED_MODELS

CONNECTION = 'video.ark.connection.status'
SUBMIT = 'video.ark.generation.submit'
STATUS = 'video.ark.generation.status'
CREDENTIAL = 'wce.ui.video.credential'
WORKSPACE = 'wce.ui.video.workspace'
H3_SUBMIT = 'video.minimax.generation.submit'
RELAY_SUBMIT = 'video.relay.generation.submit'
TOKENHEX_CHECK = 'video.tokenhex.connection.check'
TOKENHEX_SUBMIT = 'video.tokenhex.generation.submit'
GIF_SUBMIT = 'image.openai.gif.submit'
GIF_STATUS = 'image.openai.gif.status'
GIF_CONFIG = 'image.openai.gif.configuration.status'
AUDIO_IMPORT='audio.project.import'
AUDIO_MIX='audio.project.mix'
MEDIA_PREPARE = 'media.library.prepare'
AUDIO_COVER='audio.project.cover_video'
AUDIO_HISTORY='audio.project.history'
MUSIC_PROVIDER='audio.music.provider.read'
AUDIO_VIDEO='audio.project.video.inspect'
KEY_PROVIDERS = [*PROVIDERS, GIF_PROVIDER]
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
                      {'type': 'integer', 'minimum': 2, 'maximum': 30}]}
AUDIO_SCOPE={'attempt_id':ATTEMPT,'project_id':PROJECT}
MS={'type':'integer','minimum':0,'maximum':3_600_000}
AUDIO_TIMELINE=schema({'video_start_ms':MS,'music_offset_ms':MS,'fade_in_ms':MS,'fade_out_ms':MS,
   'volume_percent':{'type':'integer','minimum':0,'maximum':200},'keep_original':{'type':'boolean'}},
   {'duck':{'type':'array','maxItems':32,'items':schema({'start_ms':MS,'end_ms':MS,
      'gain_percent':{'type':'integer','minimum':0,'maximum':100}})}})
def action(name, required, optional=None):
    return schema({'action': {'type': 'string', 'const': name}, **required}, optional)


ARK_OPTIONS = {
    'mode': {'type': 'string', 'enum': ['frames', 'first', 'text', 'reference', 'edit', 'extend']},
    'duration': DURATION,
    'resolution': {'type': 'string', 'enum': ['480p', '720p', '1080p', '4k']},
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
    action('media_monitor', {}, {'include_scope': {'type':'boolean'}}),
    action('media_monitor_task', JOB),
    action('audio_library', {}),
    action('music_provider_read', {}),
    action('music_provider_save', {'provider': {'type': 'string', 'enum': list(music_preferences.PROVIDERS)},
                                  'expected_revision': {'type': 'integer', 'minimum': 0,
                                                        'maximum': music_preferences.MAX_REVISION}}),
    action('suno_snapshot', {}, {'downloaded': {'type': 'boolean'},
                                 'cursor': {'type': 'string', 'maxLength': 2048},
                                 'expected': {'type': 'string', 'maxLength': 80},
                                 'library_only': {'type': 'boolean'}}),
    action('suno_playback', {'track': {'type': 'string', 'pattern': r'^[a-f0-9-]{36}$'},
                             'expected': {'type': 'string', 'maxLength': 80}},
                            {'cursor': {'type': 'string', 'maxLength': 2048}}),
    action('ace_snapshot', {}, {'cursor': {'type': 'string', 'minLength': 1, 'maxLength': 512}}),
    action('ace_oauth_begin', {}),
    action('ace_oauth_status', {}),
    action('ace_oauth_cancel', {}),
    action('provider_catalog', {}),
    action('audio_history', {}, {'project_id': PROJECT}),
    action('audio_chunk', AUDIO_SCOPE | {'offset': {'type':'integer','minimum':0}}),
    action('audio_export', AUDIO_SCOPE),
    action('audio_preview_frames', AUDIO_SCOPE | {'start': FRAME_INDEX, 'sha256': HANDLE}),
    action('history', {}, {'project_id': PROJECT}),
    action('select', {'project_id': PROJECT, 'primary': ATTEMPT}, {'compare': ATTEMPT}),
    action('playback', JOB | {'offset': {'type': 'integer', 'minimum': 0}}),
    action('preview_frames', JOB | {'start': FRAME_INDEX}),
    action('intro_frames', {'start': FRAME_INDEX}),
    action('export', JOB),
    action('gif_history', {}, {'project_id': PROJECT}),
    action('gif_chunk', JOB | {'offset': {'type': 'integer', 'minimum': 0}}),
    action('gif_export', JOB),
    action('rename', JOB | {'name': {'type': 'string', 'minLength': 1, 'maxLength': 120}}),
    action('trash', JOB),
    action('restore', JOB),
    action('copy', JOB),
    action('status', JOB),
    action('submit', JOB | ARK_OPTIONS | {
        'model': {'type': 'string', 'enum': [*SUPPORTED_MODELS, *H3_MODELS, *V1_MODELS]}, 'prompt': PROMPT,
        'mode': {'type': 'string', 'enum': [*H3_MODES, 'edit', 'extend']},
        'resolution': {'type': 'string', 'enum': ['480p', '720p', '1080p', '4k', '480P', '768P', '2K']},
    }, SOURCE_OPTIONS | {'provider_site': SITE, 'ratio': RATIO}),
]}
RELAY_URL = {'type': 'string', 'minLength': 1, 'maxLength': 8192}
RELAY_IMAGES = {'type': 'array', 'minItems': 1, 'maxItems': 9, 'items': RELAY_URL}
RELAY_AUDIO = {'type': 'array', 'minItems': 0, 'maxItems': 3, 'items': RELAY_URL}
RELAY_PROMPT = {'type': 'string', 'minLength': 1, 'maxLength': 20000, 'x-wce-maxUtf8Bytes': 80000}
RELAY_OPTIONS = {'reference_audio': RELAY_AUDIO,
                 'duration': {'type': 'integer', 'minimum': 1, 'maximum': 15},
                 'resolution': {'type': 'string', 'enum': list(RESOLUTIONS)}}

SPECS = {
    AUDIO_IMPORT: schema(AUDIO_SCOPE | {'title':PROMPT,'audio':FRAME},
         {'provider':{'type':'string','enum':['suno','ace-music']},'provider_id':ATTEMPT,'source_project_id':PROJECT}),
    AUDIO_MIX: schema(AUDIO_SCOPE | {'title':PROMPT,'video_attempt_id':ATTEMPT,'song_attempt_id':ATTEMPT,
        'timeline':AUDIO_TIMELINE}, {'score_plan':PROMPT, 'song_project_id':PROJECT, 'video_project_id':PROJECT}),
    AUDIO_COVER: schema(AUDIO_SCOPE | {'title':PROMPT, 'song_attempt_id':ATTEMPT, 'cover':FRAME},
                       {'song_project_id':PROJECT, 'cover_project_id':PROJECT}),
    MEDIA_PREPARE: schema({}, {'source_project_id':PROJECT, 'target':schema({
        'kind': {'type':'string','const':'audio'}, 'attempt_id':ATTEMPT,
    }, {'account':schema({'platform_id':{'type':'string','enum':['wechat_official_account','x','xiaohongshu']},
                          'connection_id':{'type':'string','minLength':1,'maxLength':128}})})}),
    MUSIC_PROVIDER: schema({}),
    AUDIO_HISTORY: schema({'project_id':PROJECT}),
    AUDIO_VIDEO: schema(JOB, {'frame_start': FRAME_INDEX, 'include_audio_evidence': {'type':'boolean'}}),

    TOKENHEX_CHECK: schema({}),
    TOKENHEX_SUBMIT: schema(ARK_GENERATION | ARK_MODEL | {'configuration': schema(ARK_OPTIONS | {
        'mode': {'type': 'string', 'enum': ['text', 'frames', 'reference']}})}),
    CONNECTION: schema({}),
    GIF_SUBMIT: schema(JOB | {'reference_image': FRAME, 'prompt': PROMPT}),
    GIF_STATUS: schema(JOB),
    GIF_CONFIG: schema({}),
    RELAY_SUBMIT: {'oneOf': [
        schema(JOB | {'prompt': RELAY_PROMPT, 'reference_images': RELAY_IMAGES}, RELAY_OPTIONS),
        *[schema(
            JOB | {'workflow_id': {'type': 'string', 'const': row['id']}}
            | {key: rule for key, rule in row['fields'].items() if rule['required']},
            {key: rule for key, rule in row['fields'].items() if not rule['required']})
          for row in autodl.options()],
    ]},
    CONNECTION: schema({}),
    CREDENTIAL: {'oneOf': [
        action('begin', {}, {'provider': {'type': 'string', 'enum': KEY_PROVIDERS}}),
        action('begin_tokenhex', {}),
        action('tokenhex_select', ARK_MODEL),
        action('begin_relay', {'base_url': {'type': 'string', 'minLength': 1, 'maxLength': 512}}),
        action('status', {'provider': {'type': 'string', 'enum': [*KEY_PROVIDERS, 'relay', TOKENHEX_PROVIDER]}}),
        schema({'action': {'type': 'string', 'const': 'submit'}, 'session': HANDLE,
                'jwe': {'type': 'string', 'minLength': 1, 'maxLength': 16384,
                        'pattern': r'^[A-Za-z0-9_-]+(?:\.[A-Za-z0-9_-]+){4}$'}}),
        schema({'action': {'type': 'string', 'const': 'cancel'}, 'session': HANDLE}),
    ]},
    WORKSPACE: WORKSPACE_SPECS,
    SUBMIT: schema(ARK_GENERATION, ARK_MODEL | FRAME_OPTIONS | {
        'configuration': schema(ARK_OPTIONS, SOURCE_OPTIONS | {'ratio': RATIO}),
    }),
    STATUS: schema(JOB, {'poll': {'type': 'boolean'}}),
    H3_SUBMIT: {'oneOf': [schema(JOB | {'prompt': PROMPT, 'provider_site': SITE, 'ratio': RATIO,
        'mode': {'type': 'string', 'enum': list(H3_MODES)},
        'duration': {'type': 'integer', 'minimum': 4, 'maximum': 15},
        'resolution': {'type': 'string', 'enum': ['480P', '512P', '720P', '768P', '1080P', '2K']},
        'paths': {'type': 'array', 'minItems': 0, 'maxItems': 9,
                  'items': {'type': 'string', 'minLength': 1, 'maxLength': 4096}}}, {'model': {'type': 'string', 'enum': [*H3_MODELS, *V1_MODELS]}}),
        schema(JOB | {'prompt': PROMPT, 'provider_site': SITE,
            'mode': {'type': 'string', 'const': 'subject'}, 'model': {'type': 'string', 'const': SUBJECT_MODEL},
            'subject_image_url': {'type': 'string', 'minLength': 1, 'maxLength': 8192}}),
    ]},
}
DESCRIPTIONS = {
    MEDIA_PREPARE: 'Prepare the unified local audio library. Optionally record a known project and a bound account for the original audio attempt. Omit unknown context. Does not contact the platform.',
    AUDIO_IMPORT: 'Copy and decode an existing WAV, MP3 or M4A from the registered project. Requires a relative path and SHA-256. Provider and ID link a confirmed official download. Runs locally without calling any provider.',
    AUDIO_MIX: 'Create a new local soundtrack MP4 for a completed video, reusing imported project audio. Timeline positions and fades are milliseconds; gain is a percentage. Original media is retained. A different mix uses a new local attempt; uses no provider credits.',
    AUDIO_COVER: 'Create a local H.264/AAC MP4 from a project song and a project PNG or JPEG cover. Requires the cover SHA-256. Returns its project-relative file; does not publish it.',
    MUSIC_PROVIDER: 'Read the current device-wide Jiusera default music provider (Suno or ACE Music). Call before planning new songs or newly generated video scores when the user did not name a provider. Apply only the returned provider. If unavailable, or if that provider is disconnected, surface the issue and do not fall back or generate. Existing assets and explicit provider choices are independent.',
    AUDIO_HISTORY: 'List the songs and soundtrack assets already saved in a project.',
    AUDIO_VIDEO: 'Read facts for a specific project video and its SHA-256. Pass frame_start to receive up to four timecoded JPEGs as images, at 8 fps. Set include_audio_evidence for optional first-track RMS timings. Levels do not identify dialogue. No supplier upload.',
    TOKENHEX_CHECK: 'Read supported model IDs visible under the locally configured Token Hex video credential using GET /v1/models. Read only. Visibility does not verify the native video route.',
    TOKENHEX_SUBMIT: 'Submit one expressly authorized billable Token Hex Doubao native generation for a supported Seedance model selected in video model settings. Use the same project, attempt and documented Seedance mode. Query the same attempt through video.ark.generation.status. Never replace an unknown submission.',
    GIF_SUBMIT: 'When the user requests an animated GIF with their configured OpenAI Key, submit one authorized billable GPT-Image-2.6 Flare image edit for a registered project. Provide a selected original static PNG/JPEG/WebP project-relative path, its SHA-256, and a motion/loop prompt. Reuse the exact attempt and arguments only to read its existing result or finish an interrupted local copy. Never resubmit an unknown request. Use image.openai.gif.status to read the local receipt; there is no remote poll.',
    GIF_STATUS: 'Read the original local animated GIF receipt. ASSET_READY returns the exact project file path and its SHA-256. This tool does not call OpenAI.',
    GIF_CONFIG: 'Read whether the separate OpenAI GIF Key is configured. Does not verify GIF preview access or return the Key.',
    RELAY_SUBMIT: 'Submit one authorized billable AutoDL video workflow. Read video.director.read action=models for exact workflow IDs, media roles and options. Set workflow_id for new intent-based requests: text, ordered single/multiple references, paired first_frame and last_frame, lip sync, multi-image/audio or motion transfer. The published catalogue has no standalone first-frame-only workflow. Use HTTPS input URLs. Omission keeps the legacy reference workflow for existing clients. Query video.ark.generation.status with the original project and attempt. Never replace an unknown submission.',
    CONNECTION: 'Read local Ark credential configuration state. Does not verify model access or return the API Key.',
    CREDENTIAL: 'App-only local video and OpenAI GIF Key configuration. Accepts only a one-use encrypted envelope, never a plaintext Key.',
    WORKSPACE: 'App-only project video history, previews, library and export. Supports legacy panel requests.',
    SUBMIT: 'Submit one authorized billable Seedance task. Supply either first_frame and last_frame or, for Seedance 2.5, 1–30 ordered reference_images. Each image needs a project-local original PNG/JPEG path and SHA-256 hash. Default: Seedance 2.5, 5 seconds. Seedance 2.5 accepts 4–30 seconds or -1 for Auto. For explicit mode, resolution or audio use configuration with mode, paths (ordered project-relative PNG/JPEG), duration, resolution and audio. Seedance 2.5 also supports text, edit and extend; edit/extend require the original source_attempt_id and source_sha256 in the same project. Reuse the original generation_attempt_id and identical inputs. Never submit a replacement after SUBMIT_UNKNOWN.',
    STATUS: 'Read the original video receipt (Ark, MiniMax or video relay). With poll=true, query only the original provider task and save its verified MP4 if ready.',
    H3_SUBMIT: 'Submit one authorized billable MiniMax video generation. H3 uses V2; Hailuo/T2V/I2V use V1. Select the site matching the configured Key. For S2V-01 use mode=subject and a public HTTPS subject_image_url for one character. No paths, duration, resolution or ratio are sent for S2V. For the other modes use project-relative PNG/JPEG paths and model-appropriate duration, resolution and ratio. Poll the original attempt with video.ark.generation.status.',
}


class VideoRouter:
    def __init__(self, inner, registry=None):
        self.inner = inner
        self.video_jobs = Jobs(registry)
        self.gif_jobs = GifJobs(self.video_jobs)
        self.audio_jobs = AudioJobs(self.video_jobs)
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
            local_read = name in {CONNECTION, GIF_CONFIG, GIF_STATUS, TOKENHEX_CHECK, AUDIO_HISTORY, AUDIO_VIDEO, MUSIC_PROVIDER}
            row = {'name': name, 'inputSchema': deepcopy(spec), 'description': DESCRIPTIONS[name],
                   'annotations': {'readOnlyHint': local_read, 'destructiveHint': False,
                                   'idempotentHint': name != CREDENTIAL, 'openWorldHint': name in {SUBMIT, STATUS, WORKSPACE, H3_SUBMIT, RELAY_SUBMIT, GIF_SUBMIT, TOKENHEX_CHECK, TOKENHEX_SUBMIT}}}
            if name in (CREDENTIAL, WORKSPACE):
                row['_meta'] = {'ui': {'visibility': ['app']}}
            rows.append(row)
        return rows

    def call(self, name, arguments):
        if name not in SPECS:
            return self.inner.call(name, arguments)
        strict_validate(arguments, SPECS[name])
        if name == MUSIC_PROVIDER:
            return music_preferences.read(self.video_jobs.projects.root)
        if name == MEDIA_PREPARE:
            media = self.audio_jobs.media
            source = arguments.get('source_project_id')
            label = self.audio_jobs.project(source)['name'] if source else None
            target = arguments.get('target')
            if target is not None:
                selected = target.get('account')
                account = None
                if selected is not None:
                    platform, connection = selected['platform_id'], selected['connection_id']
                    overview = self.inner.call('wce.ui.management.overview', {})
                    rows = [row for row in overview['connections'] if row['platform_id'] == platform
                            and row['connection_id'] == connection
                            and row['state'] in {'BOUND', 'BOUND_IDLE', 'BUSY', 'CONNECTED'}]
                    if len(rows) != 1:
                        raise WCEError('MEDIA_ACCOUNT_UNAVAILABLE')
                    presentation = rows[0].get('presentation') or {}
                    account = media.attribution(platform, connection, presentation.get('display_name') or platform)
                media.reserve('audio', target['attempt_id'], account, project_label=label)
            project = media.project(create=True)
            return {'state':'READY','project_id':project['id'],'root':project['root']}
        if name == AUDIO_HISTORY:
            return self.audio_jobs.history(arguments['project_id'])
        if name == AUDIO_VIDEO:
            return self.audio_jobs.inspect_video(arguments['generation_attempt_id'], arguments['project_id'],
                                                 arguments.get('frame_start'),
                                                 arguments.get('include_audio_evidence', False))
        if name == AUDIO_IMPORT:
            return self.audio_jobs.ingest(arguments['attempt_id'],arguments['project_id'],arguments['title'],
                arguments['audio'],arguments.get('provider'),arguments.get('provider_id'),
                source_project_id=arguments.get('source_project_id'))
        if name in {AUDIO_COVER, AUDIO_MIX} and arguments['project_id'] == LIBRARY_ID:
            media = self.audio_jobs.media
            song_project = arguments.get('song_project_id', arguments['project_id'])
            inherited = media.account('audio', arguments['song_attempt_id'], song_project)
            if name == AUDIO_MIX:
                video_project = arguments.get('video_project_id', arguments['project_id'])
                video_account = media.account('video', arguments['video_attempt_id'], video_project)
                if video_account and inherited and inherited.get('account_key') != video_account.get('account_key'):
                    inherited = {}
                elif video_account:
                    inherited = inherited or video_account
            label = inherited.get('project_label')
            if not label and song_project != LIBRARY_ID:
                label = self.audio_jobs.project(song_project)['name']
            media.reserve('audio', arguments['attempt_id'], inherited=inherited, project_label=label)
        if name == AUDIO_COVER:
            return self.audio_jobs.cover_video(arguments['attempt_id'], arguments['project_id'],
                                               arguments['song_attempt_id'], arguments['title'], arguments['cover'],
                                               song_project_id=arguments.get('song_project_id'),
                                               cover_project_id=arguments.get('cover_project_id'))
        if name == AUDIO_MIX:
            settings=arguments['timeline']
            timeline={key.removesuffix('_ms'):value/1000 for key,value in settings.items() if key.endswith('_ms')}
            timeline.update(volume=settings['volume_percent']/100,keep_original=settings['keep_original'])
            if 'duck' in settings:
                timeline['duck'] = settings['duck']
            return self.audio_jobs.mix(arguments['attempt_id'],arguments['project_id'],arguments['video_attempt_id'],
                arguments['song_attempt_id'],arguments['title'],timeline,arguments.get('score_plan'),
                song_project_id=arguments.get('song_project_id'),video_project_id=arguments.get('video_project_id'))
        if name == GIF_CONFIG:
            return gif_status()
        if name == GIF_STATUS:
            return self.gif_jobs.status(arguments['generation_attempt_id'], arguments['project_id'])
        if name == GIF_SUBMIT:
            return self.gif_jobs.submit(arguments['generation_attempt_id'], arguments['project_id'],
                                        arguments['reference_image'], arguments['prompt'])
        if name == CONNECTION:
            return dict(status(), model=MODEL, supported_models=list(SUPPORTED_MODELS),
                        model_access='UNVERIFIED')
        if name == TOKENHEX_CHECK:
            return self.video_jobs.tokenhex_check()
        if name == CREDENTIAL:
            action = arguments['action']
            if action == 'status':
                if arguments['provider'] == GIF_PROVIDER:
                    return gif_status()
                if arguments['provider'] == TOKENHEX_PROVIDER:
                    return tokenhex_status()
                return relay_status() if arguments['provider'] == 'relay' else status(provider=arguments['provider'])
            if action == 'tokenhex_select':
                return self.video_jobs.tokenhex_select(arguments['model'])
            if action == 'begin_tokenhex':
                return self.video_credential.begin(TOKENHEX_PROVIDER)
            if action == 'begin_relay':
                return self.video_credential.begin('relay', base_url=arguments['base_url'])
            if action == 'begin':
                return self.video_credential.begin(arguments.get('provider', 'ark'))
            if action == 'cancel':
                return self.video_credential.cancel(arguments['session'])
            return self.video_credential.submit(arguments['session'], arguments['jwe'])
        if name == WORKSPACE:
            return self.workspace(arguments)
        attempt, project = arguments['generation_attempt_id'], arguments['project_id']
        if name == TOKENHEX_SUBMIT:
            row = self.video_jobs.submit(attempt, project, None, None, arguments['prompt'],
                                         model=arguments['model'], workspace=arguments['configuration'], tokenhex=True)
        elif name == RELAY_SUBMIT:
            inputs = {key: arguments[key] for key in ('prompt', *autodl.FIELDS) if key in arguments}
            row = self.video_jobs.submit_relay(attempt, project, inputs)
        elif name == H3_SUBMIT and arguments.get('model') == SUBJECT_MODEL:
            row = self.video_jobs.submit_subject(attempt, project, arguments['provider_site'],
                                                 arguments['prompt'], arguments['subject_image_url'])
        elif name == H3_SUBMIT:
            workspace = {k: arguments[k] for k in ('mode', 'duration', 'resolution', 'ratio', 'provider_site', 'paths')}
            row = self.video_jobs.submit(attempt, project, None, None, arguments['prompt'], model=arguments.get('model', H3), workspace=workspace)
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
                if key not in {'recipe', 'project_video_root', 'project_video_copy', 'relay_connection', 'tokenhex_connection'}}

    def workspace(self, arguments):
        job = self.video_jobs
        command = arguments['action']
        project = arguments.get('project_id')
        attempt = arguments.get('generation_attempt_id')
        if command in {'suno_snapshot', 'suno_playback'}:
            from .suno_panel import run
            return run(command, {key: value for key, value in arguments.items() if key != 'action'})
        if command in {'ace_snapshot', 'ace_oauth_begin', 'ace_oauth_status', 'ace_oauth_cancel'}:
            from .ace_panel import run
            return run(command, {key: value for key, value in arguments.items() if key != 'action'})
        if command == 'media_monitor_task':
            return job.monitor_task(attempt, project)
        if command == 'media_monitor':
            from .media_monitor import collect
            return collect(job, self.gif_jobs, self.audio_jobs, include_scope=arguments.get('include_scope', False))
        if command == 'music_provider_read':
            return music_preferences.read(job.projects.root)
        if command == 'music_provider_save':
            return music_preferences.save(job.projects.root, arguments['provider'], arguments['expected_revision'])
        if command == 'audio_library':
            return self.audio_jobs.history(unified=True)
        if command == 'audio_history':
            return self.audio_jobs.history(project)
        if command == 'audio_chunk':
            return self.audio_jobs.chunk(arguments['attempt_id'],project,arguments['offset'])
        if command == 'audio_preview_frames':
            return self.audio_jobs.preview_video(arguments['attempt_id'],project,arguments['start'],arguments['sha256'])
        if command == 'audio_export':
            return self.audio_jobs.export(arguments['attempt_id'],project)
        if command == 'provider_catalog':
            return provider_directory()
        if command == 'history':
            return job.history(project)
        if command == 'gif_history':
            if project is None:
                return {'projects': [{'id': row['id'], 'name': row['name']} for row in job.projects.view()['projects']]}
            return {'gifs': self.gif_jobs.history(project)}
        if command == 'select':
            return job.select_versions(project, arguments['primary'], arguments.get('compare'))
        if command == 'playback':
            return job.playback(attempt, project, arguments['offset'])
        if command in {'preview_frames', 'intro_frames'}:
            return job.preview_frames(arguments['start'], attempt, project)
        if command == 'export':
            return job.export(attempt, project)
        if command == 'gif_chunk':
            return self.gif_jobs.chunk(attempt, project, arguments['offset'])
        if command == 'gif_export':
            return self.gif_jobs.export(attempt, project)
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
