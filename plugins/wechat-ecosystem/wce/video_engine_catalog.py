"""Director options projected from the existing video submission adapters."""
from urllib.parse import parse_qsl

from .contracts import WCEError
from . import video_autodl_catalog as autodl
from .project_context import text as project_text
from .video_minimax import H3_MODES, H3_MODELS, RATIOS, SITES, SUBJECT_MODEL, V1_MODELS
from .video_relay import RELAY_MODEL, RESOLUTIONS, https_url
from .video_seedance import ARK_MODELS, ARK_RATIOS, MAX_REFERENCE_IMAGES

CHANNELS = {'ark': '火山方舟', 'cn': 'MiniMax 中国站', 'global': 'MiniMax 国际站',
            'relay': 'AutoDL', 'tokenhex': 'Token Hex'}
HEX_MODES = ('text', 'frames', 'reference')
LOCAL_ROLES = {'first': ('first',), 'last': ('last',), 'frames': ('first', 'last')}
REFERENCE = ('subject', 'environment', 'reference')
PUBLIC_CREDENTIAL_KEYS = {'accesskey', 'accesskeyid', 'apikey', 'authorization', 'credential', 'key',
                          'password', 'policy', 'secret', 'sig', 'signature', 'token', 'accesstoken',
                          'securitytoken', 'sessiontoken', 'refreshtoken', 'ossaccesskeyid'}


def require(condition, code):
    if not condition:
        raise WCEError(code)


def h3_ratios(model, mode):
    if mode in LOCAL_ROLES:
        return ('adaptive',)
    if mode == 'text' or model == 'MiniMax-H3-Lite':
        return RATIOS
    return ('adaptive', *RATIOS)


def v1_durations(size):
    return (6, 10) if size in ('512P', '768P') else (6,)


def params(sizes, durations, ratios, **inputs):
    return {'resolutions': {size: list(durations(size)) for size in sizes},
            'ratios': list(ratios), 'local_roles': list(LOCAL_ROLES.get(inputs.get('mode'), ())),
            'reference_count': inputs.get('reference_count', 0), 'audio': inputs.get('audio', False),
            'source': inputs.get('mode') in ('edit', 'extend'), 'direction': inputs.get('mode') == 'extend'}


def mode_profiles(provider, model):
    if provider in ('ark', 'tokenhex') and model in ARK_MODELS:
        modes, minimum, maximum, sizes, audio = ARK_MODELS[model]
        if provider == 'tokenhex':
            modes = tuple(mode for mode in modes if mode in HEX_MODES)
        ratios = ('adaptive', *ARK_RATIOS) if provider == 'ark' else ('adaptive',)
        def durations(mode):
            if mode == 'edit':
                return (-1,)
            return (*range(minimum, maximum+1), *((-1,) if audio else ()))
        return {mode: params(sizes, lambda _size: durations(mode), ratios, mode=mode, audio=audio,
                             reference_count=MAX_REFERENCE_IMAGES if mode == 'reference' else 0)
                for mode in modes}
    if provider in SITES:
        if model == SUBJECT_MODEL:
            return {'subject': params((), None, ()) | {'url_inputs': 'subject'}}
        if model in H3_MODELS:
            minimum, sizes = H3_MODELS[model]
            return {mode: params(sizes, lambda _size: range(minimum, 16), h3_ratios(model, mode), mode=mode,
                                 reference_count=9 if mode == 'reference' else 0)
                    for mode in H3_MODES}
        if model in V1_MODELS:
            return {mode: params(sizes, v1_durations, ('adaptive',), mode=mode)
                    for mode, sizes in V1_MODELS[model].items()}
    if provider == 'relay' and model == RELAY_MODEL:
        return {'workflow': params(RESOLUTIONS, lambda _size: range(1, 16), ())
                | {'url_inputs': 'relay', 'optional_output': True, 'image_urls': 9, 'audio_urls': 3,
                   'workflows': autodl.options()}}
    return {}


def public_media_url(value):
    """Only public input URLs belong in project revisions. Never fetch here."""
    parts = https_url(project_text(value), 'DIRECTOR_INPUT_URL_INVALID')
    require(parts.path not in ('', '/') or parts.query, 'DIRECTOR_INPUT_URL_INVALID')
    for key, _ in parse_qsl(parts.query, keep_blank_values=True):
        field = ''.join(c for c in key.lower() if c.isalnum())
        require(field not in PUBLIC_CREDENTIAL_KEYS and not field.startswith(('xamz', 'xgoog', 'xoss', 'xcos')),
                'PROJECT_SECRET_NOT_ALLOWED')
    return value


def validate_config(config, project_id, *, ready=False):
    modes = mode_profiles(config['provider'], config['model'])
    require(modes, 'VIDEO_MODEL_UNSUPPORTED')
    profile = modes.get(config['mode'])
    require(profile, 'VIDEO_MODE_UNSUPPORTED')
    url_kind = profile.get('url_inputs')
    relay_fields = set(autodl.FIELDS) - {'duration', 'resolution'}
    require(url_kind == 'relay' or not relay_fields & config.keys(), 'VIDEO_MODE_PARAMETERS_INVALID')
    if url_kind == 'relay' and 'workflow_id' in config:
        require(not ({'ratio', 'audio', 'direction', 'source', 'subject_image_url'} & config.keys()),
                'VIDEO_MODE_PARAMETERS_INVALID')
        relay_config = {key: config[key] for key in autodl.FIELDS if key in config}
        autodl.validate(relay_config, partial=True)
        required = {key for key, rule in autodl.profile(config['workflow_id'])['fields'].items()
                    if rule['required']} - {'prompt'}
        require(not ready or required <= relay_config.keys(), 'DIRECTOR_INPUT_URL_REQUIRED')
        for _, url in autodl.media(relay_config):
            public_media_url(url)
        return profile
    sizes = profile['resolutions']
    optional = profile.get('optional_output', False)
    size = config.get('resolution')
    length = config.get('duration')
    ratios = profile['ratios']
    require((size in sizes or optional and size is None) if sizes else size is None, 'VIDEO_OUTPUT_UNSUPPORTED')
    choices = sizes.get(size, next(iter(sizes.values()), []))
    require((length in choices or optional and length is None) if choices else length is None,
            'VIDEO_DURATION_INVALID')
    require(config.get('ratio') in ratios if ratios else 'ratio' not in config, 'VIDEO_OUTPUT_INVALID')
    require(profile['audio'] or not config.get('audio'), 'VIDEO_OUTPUT_UNSUPPORTED')
    source = config.get('source')
    require(not source or profile['source'], 'VIDEO_REFERENCE_SOURCE_UNAVAILABLE')
    if source:
        require(source['project_id'] == project_id, 'DIRECTOR_ASSET_WRONG_PROJECT')
    if ready and profile['source']:
        require(source, 'VIDEO_REFERENCE_SOURCE_UNAVAILABLE')
    require(profile['direction'] == ('direction' in config), 'VIDEO_MODE_PARAMETERS_INVALID')
    require(url_kind == 'subject' or 'subject_image_url' not in config, 'VIDEO_MODE_PARAMETERS_INVALID')
    if url_kind == 'relay':
        require(not (relay_fields - {'reference_images', 'reference_audio'}) & config.keys(),
                'VIDEO_MODE_PARAMETERS_INVALID')
    if url_kind == 'subject':
        if ready:
            require(config.get('subject_image_url'), 'DIRECTOR_INPUT_URL_REQUIRED')
        if 'subject_image_url' in config:
            public_media_url(config['subject_image_url'])
    if url_kind == 'relay':
        if ready:
            require(config.get('reference_images'), 'DIRECTOR_INPUT_URL_REQUIRED')
        for value in (*config.get('reference_images', []), *config.get('reference_audio', [])):
            public_media_url(value)
    return profile
