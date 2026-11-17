"""Token Hex's documented New API Doubao native candidate, fixed to one origin."""
from hashlib import sha256
import re
from urllib.request import ProxyHandler, build_opener

from .contracts import WCEError
from .video_relay import PublicHTTPSHandler, https_url
from .video_relay_keychain import load_relay, relay_status, save_relay
from .video_seedance import Ark, NoRedirect, SUPPORTED_MODELS, ark_error_code, validate_model
from .x_keychain import XKeychain

TOKENHEX_ORIGIN = 'https://api.tokenhex.com'
TOKENHEX_PROVIDER = 'tokenhex'
TOKENHEX_PURPOSE = 'openahoy:video:tokenhex:key:v1'
TASK_PATH = '/doubao/api/v3/contents/generations/tasks'
PUBLIC_TASK = re.compile(r'[A-Za-z0-9_-]{1,160}\Z')
REMOTE_STATES = frozenset({'queued', 'running', 'failed', 'expired', 'cancelled', 'succeeded'})


class TokenHexKeychain(XKeychain):
    service = 'com.readysteadyscience.openahoy.video.tokenhex.v1'
    label = 'OpenAhoy · Token Hex · Video'
    scope = sha256(service.encode()).hexdigest()


def tokenhex_status(backend=None):
    value = relay_status(backend, keychain=TokenHexKeychain)
    if value.get('base_url', TOKENHEX_ORIGIN) != TOKENHEX_ORIGIN:
        return {'state': 'ACTION_REQUIRED'}
    return value


def save_tokenhex(token, backend=None):
    return save_relay(TOKENHEX_ORIGIN, token, backend, keychain=TokenHexKeychain)


def load_tokenhex(backend=None):
    connection = load_relay(backend, keychain=TokenHexKeychain)
    if connection is not None and connection[0] != TOKENHEX_ORIGIN:
        raise WCEError('VIDEO_TOKENHEX_ORIGIN_MISMATCH')
    return connection


class TokenHex(Ark):
    def __init__(self, opener=None):
        super().__init__(opener if opener is not None else build_opener(
            ProxyHandler({}), NoRedirect(), PublicHTTPSHandler()))

    def _native(self, key, task=None, body=None):
        tail = ''
        if task is not None:
            if (type(task) is not str or not PUBLIC_TASK.fullmatch(task)
                    or key.reveal_for_adapter() in task):
                raise WCEError('VIDEO_TASK_ID_UNKNOWN')
            tail = '/' + task
        return self._json(TOKENHEX_ORIGIN + TASK_PATH + tail, key, body)

    def models(self, key):
        try:
            response = self._json(TOKENHEX_ORIGIN + '/v1/models', key)
        except WCEError as error:
            if error.code == 'VIDEO_QUERY_AUTH_REQUIRED':
                return {'state': 'AUTH_REQUIRED', 'models': []}
            raise
        if response.get('object') != 'list' or type(response.get('data')) is not list:
            raise WCEError('VIDEO_TOKENHEX_CATALOG_UNRECOGNIZED')
        visible = {row['id'] for row in response['data'] if type(row) is dict and type(row.get('id')) is str}
        models = [model for model in SUPPORTED_MODELS if model in visible]
        state = 'MODELS_VISIBLE' if models else 'NO_SUPPORTED_MODELS' if visible else 'EMPTY_CATALOG'
        return {'state': state, 'models': models}

    def submit(self, key, body):
        task = self._native(key, body=body).get('id')
        if (type(task) is not str or not PUBLIC_TASK.fullmatch(task)
                or key.reveal_for_adapter() in task or task in key.reveal_for_adapter()):
            raise WCEError('VIDEO_TASK_ID_UNKNOWN')
        return task

    def query(self, key, task, *, model):
        validate_model(model)
        value = self._native(key, task=task)
        if value.get('id') != task or value.get('model') != model:
            raise WCEError('VIDEO_TASK_ID_MISMATCH')
        status = value.get('status')
        if type(status) is not str or status not in REMOTE_STATES:
            raise WCEError('VIDEO_TASK_STATUS_UNKNOWN')
        content = value.get('content')
        result = {'status': status, 'usage': value.get('usage')}
        if status == 'succeeded' and type(content) is dict:
            result['content'] = {'video_url':content.get('video_url')}
        if status == 'failed' and (code := ark_error_code(value, key.reveal_for_adapter())):
            result['error'] = {'code': code}
        return result

    def download(self, url, output):
        https_url(url, 'VIDEO_RESULT_SOURCE_INVALID')
        self._download(url, output)
