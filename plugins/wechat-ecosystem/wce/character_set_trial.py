"""A fixed, image-bound rehearsal. This tool has no generation or asset-write path."""
from copy import deepcopy
from hashlib import sha256
import json
from pathlib import Path
import re
import secrets
from threading import Lock, Timer
import time

from .character_library import ID as VERSION_ID, form_of
from .contracts import WCEError
from .own_bootstrap_security import path_check
from .own_connection_policy import atomic_write, locked, read_optional

APP_TOOL = 'wce.ui.characters.dry_run'
MODEL_TOOL = 'own.characters.dry_run'
ID = {'type': 'string', 'pattern': '^[a-f0-9]{32}$'}
SHA = {'type': 'string', 'pattern': '^[a-f0-9]{64}$'}
STAGES = ('核对身份与基准图', '检查视角与表情槽位', '检查体态、服装与配饰槽位')
TERMINAL = frozenset({'COMPLETED', 'CANCELLED', 'DECLINED', 'EXPIRED', 'REFERENCE_CHANGED',
                      'HOST_RESPONSE_UNAVAILABLE'})


def schema(operations):
    shared = {'action': {'type': 'string', 'enum': list(operations)}, 'task_id': ID}
    fields = shared | {key: value for extra in operations.values() for key, value in extra.items()}
    return {'type': 'object', 'properties': fields, 'required': ['action', 'task_id'],
            'additionalProperties': False}


APP_ACTIONS = {'prepare': {'project_id': ID, 'version_id': VERSION_ID, 'sha256': SHA},
               'status': {}, 'cancel': {}}
MODEL_ACTIONS = {'review': {}, 'confirm': {'plan_sha256': SHA}, 'status': {}}
TOOLS = [
    {'name': APP_TOOL, 'description': 'Prepare, inspect or cancel a local zero-image character rehearsal.',
     'inputSchema': schema(APP_ACTIONS), '_meta': {'ui': {'visibility': ['app']}},
     'annotations': {'openWorldHint': False, 'destructiveHint': False, 'idempotentHint': True}},
    {'name': MODEL_TOOL,
     'description': 'Zero-image rehearsal. Review the exact task. Confirm its plan_sha256 via native form.',
     'inputSchema': schema(MODEL_ACTIONS), '_meta': {'ui': {'visibility': ['model']}},
     'annotations': {'openWorldHint': False, 'destructiveHint': False, 'idempotentHint': True}},
]


def check_args(args, operations):
    action = args.get('action')
    if (not isinstance(action, str) or action not in operations
            or set(args) != {'action', 'task_id', *operations[action]}):
        raise WCEError('CHARACTER_TRIAL_INVALID_ARGUMENTS')
    for name, spec in ({'task_id': ID} | operations[action]).items():
        value = args[name]
        if (type(value) is not str or not 1 <= len(value) <= spec.get('maxLength', 128)
                or ('pattern' in spec and not re.fullmatch(spec['pattern'], value))):
            raise WCEError('CHARACTER_TRIAL_INVALID_ARGUMENTS')
    return action


def tool_result(value, thumbnail=None):
    result = {'content': [{'type': 'text', 'text': json.dumps(value, ensure_ascii=False)}],
              'structuredContent': value, 'isError': False}
    if thumbnail:
        result['content'].append({'type': 'image', 'mimeType': thumbnail['mime_type'],
                                  'data': thumbnail['data']})
    return result


class CharacterSetTrial:
    def __init__(self, characters, registry, *, clock=time.time):
        self.characters = characters
        self.home = Path(registry).parent
        self.directory = self.home / 'character-set-rehearsals'
        self.owner = secrets.token_hex(32)
        self.clock = clock

    def _reference(self, project_id, version_id, digest):
        row = self.characters.index(project_id)['assets'].get(version_id)
        if (not row or row['use'] in {'voice', 'model'} or row['sha256'] != digest):
            raise WCEError('CHARACTER_TRIAL_REFERENCE_CHANGED')
        project = next((item for item in self.characters.director.registered() if item['id'] == project_id), None)
        if project is None:
            raise WCEError('DIRECTOR_PROJECT_NOT_REGISTERED')
        thumbnail = self.characters.media({'action': 'character_thumbnail', 'project_id': project_id,
                                           'version_id': version_id, 'sha256': digest})
        form = form_of(row)
        return {'project_id': project_id, 'project_name': project['name'],
                'character_id': row['character']['id'], 'character_name': row['character']['name'],
                'form_id': form['id'], 'form_name': form['name'],
                'version_id': version_id, 'sha256': digest, 'label': row['label']}, thumbnail

    def _path(self, task_id):
        path_check(self.home, True)
        self.directory.mkdir(mode=0o700, exist_ok=True)
        path_check(self.directory, True)
        return self.directory / (task_id + '.json')

    def _mutate(self, task_id, adjust):
        path = self._path(task_id)
        with locked(self.directory / 'writer.lock'):
            row = read_optional(path)
            original = deepcopy(row)
            if row and row['state'] not in TERMINAL and row['expires_at'] <= self.clock():
                row['state'] = 'EXPIRED'
            row, extra = adjust(row)
            if row != original:
                atomic_write(path, row)
            return self._public(row), extra

    @staticmethod
    def _public(row):
        if not row:
            raise WCEError('CHARACTER_TRIAL_NOT_FOUND')
        return {key: row[key] for key in ('task_id', 'state', 'plan', 'plan_sha256',
                                           'simulated_completions', 'expires_at')} | {
                   'generation_calls': 0, 'billed_units': 0}

    def app(self, args):
        action = check_args(args, APP_ACTIONS)
        task_id = args['task_id']

        def adjust(row):
            if action == 'prepare':
                project, version, digest = (args[name] for name in ('project_id', 'version_id', 'sha256'))
                if row:
                    identity = row['plan']['reference']
                    if (project, version, digest) != (identity['project_id'], identity['version_id'], identity['sha256']):
                        raise WCEError('CHARACTER_TRIAL_REQUEST_CONFLICT')
                    return row, None
                target, _ = self._reference(project, version, digest)
                plan = {'schema_version': 1, 'mode': 'ZERO_IMAGE_REHEARSAL', 'reference': target,
                        'steps': list(STAGES), 'new_images': 0, 'generation_requests': 0}
                encoded = json.dumps(plan, ensure_ascii=False, sort_keys=True, separators=(',', ':')).encode()
                row = {'task_id': task_id, 'owner': self.owner, 'state': 'PREPARED', 'form_id': None,
                       'reviewed': False, 'plan': plan, 'plan_sha256': sha256(encoded).hexdigest(),
                       'simulated_completions': 0, 'expires_at': int(self.clock()) + 900}
            elif action == 'cancel' and row and row['state'] not in TERMINAL:
                row['state'] = 'CANCELLED'
            return row, None

        return tool_result(self._mutate(task_id, adjust)[0])

    def model(self, args):
        action = check_args(args, MODEL_ACTIONS)
        if action == 'confirm':
            raise WCEError('CHARACTER_TRIAL_NATIVE_FORM_REQUIRED')

        def adjust(row):
            if not row:
                raise WCEError('CHARACTER_TRIAL_NOT_FOUND')
            if action == 'review' and row['state'] not in TERMINAL:
                if row['owner'] != self.owner:
                    raise WCEError('CHARACTER_TRIAL_ORIGINAL_SESSION_REQUIRED')
                reference = row['plan']['reference']
                _, image = self._reference(reference['project_id'], reference['version_id'], reference['sha256'])
                row['reviewed'] = True
                return row, image
            return row, None

        value, thumbnail = self._mutate(args['task_id'], adjust)
        return tool_result(value, thumbnail)

    def begin(self, args, form_id):
        def adjust(row):
            if not row:
                raise WCEError('CHARACTER_TRIAL_NOT_FOUND')
            if args['plan_sha256'] != row['plan_sha256']:
                raise WCEError('CHARACTER_TRIAL_PLAN_MISMATCH')
            if row['state'] in TERMINAL:
                return row, False
            if row['owner'] != self.owner:
                raise WCEError('CHARACTER_TRIAL_ORIGINAL_SESSION_REQUIRED')
            if row['state'] == 'WAITING_FOR_NATIVE_FORM':
                return row, False
            if not row.get('reviewed'):
                raise WCEError('CHARACTER_TRIAL_REVIEW_REQUIRED')
            ref = row['plan']['reference']
            try:
                self._reference(ref['project_id'], ref['version_id'], ref['sha256'])
            except (WCEError, OSError):
                row['state'] = 'REFERENCE_CHANGED'
                return row, False
            row['state'], row['form_id'] = 'WAITING_FOR_NATIVE_FORM', form_id
            return row, True

        return self._mutate(args['task_id'], adjust)

    def finish(self, task_id, form_id, outcome):
        def adjust(row):
            if not row:
                raise WCEError('CHARACTER_TRIAL_NOT_FOUND')
            if row['state'] != 'WAITING_FOR_NATIVE_FORM' or row['form_id'] != form_id:
                return row, None
            if outcome == 'COMPLETED':
                ref = row['plan']['reference']
                try:
                    self._reference(ref['project_id'], ref['version_id'], ref['sha256'])
                except (WCEError, OSError):
                    row['state'] = 'REFERENCE_CHANGED'
                    return row, None
                row['simulated_completions'] = 1
            row['state'] = outcome
            return row, None

        return self._mutate(task_id, adjust)[0]


class NativeCharacterForm:
    """Only invoked by the transport, never by a model-supplied response parameter."""
    def __init__(self, trial, *, timeout=180):
        self.trial, self.timeout = trial, timeout
        self.supported = False
        self.pending = {}
        self.lock = Lock()

    def capabilities(self, params):
        cap = params['capabilities'].get('elicitation')
        self.supported = type(cap) is dict and (not cap or type(cap.get('form')) is dict)

    @staticmethod
    def _error(problem):
        return {'content': [{'type': 'text', 'text': problem.code}],
                'structuredContent': {'error': problem.code}, 'isError': True}

    def request(self, request_id, args, send):
        try:
            check_args(args, MODEL_ACTIONS)
            if not self.supported:
                raise WCEError('CHARACTER_TRIAL_HOST_FORM_UNAVAILABLE')
            if not isinstance(request_id, (str, int)) or isinstance(request_id, bool):
                raise WCEError('CHARACTER_TRIAL_INVALID_ARGUMENTS')
            with self.lock:
                if len(self.pending) >= 8:
                    raise WCEError('CHARACTER_TRIAL_HOST_BUSY')
                form_id = 'character-trial-' + secrets.token_hex(16)
                value, opened = self.trial.begin(args, form_id)
                if not opened:
                    return tool_result(value)
                timer = Timer(self.timeout, self.resolve, args=(form_id, 'EXPIRED'))
                timer.daemon = True
                self.pending[form_id] = (request_id, args['task_id'], send, timer)
            ref = value['plan']['reference']
            steps = '、'.join(value['plan']['steps'])
            message = (f"Jiusera 零生图演练\n项目：{ref['project_name']} · 人物：{ref['character_name']} · 形态：{ref['form_name']}\n"
                       f"原图：{ref['label']} · {ref['version_id']} · SHA-256 {ref['sha256']}\n"
                       f"任务：{value['task_id']} · 计划摘要：{value['plan_sha256']}\n"
                       f"检查：{steps}。新生成 0 张，调用 0 次，扣费 0。")
            try:
                send({'jsonrpc': '2.0', 'id': form_id, 'method': 'elicitation/create',
                      'params': {'mode': 'form', 'message': message,
                                 'requestedSchema': {'type': 'object', 'required': ['decision'],
                                     'properties': {'decision': {'type': 'string', 'title': '零生图演练',
                                         'oneOf': [{'const': 'confirm_rehearsal', 'title': '确认仅记录本次演练'},
                                                   {'const': 'cancel_rehearsal', 'title': '取消本次演练'}]}}}}})
            except OSError:
                self.resolve(form_id, 'HOST_RESPONSE_UNAVAILABLE', respond=False)
                raise
            timer.start()
            return None
        except (WCEError, OSError) as problem:
            return self._error(problem if isinstance(problem, WCEError) else WCEError('CHARACTER_TRIAL_STORE_UNAVAILABLE'))

    def resolve(self, form_id, outcome, *, respond=True):
        with self.lock:
            call = self.pending.pop(form_id, None)
        if call is None:
            return
        request_id, task_id, send, timer = call
        timer.cancel()
        try:
            result = tool_result(self.trial.finish(task_id, form_id, outcome))
        except (WCEError, OSError) as problem:
            result = self._error(problem if isinstance(problem, WCEError) else WCEError('CHARACTER_TRIAL_STORE_UNAVAILABLE'))
        if respond:
            try:
                send({'jsonrpc': '2.0', 'id': request_id, 'result': result})
            except OSError:
                pass

    def receive(self, frame):
        if type(frame) is not dict or frame.get('jsonrpc') != '2.0':
            return False
        identifier = frame.get('id')
        if 'method' not in frame and type(identifier) is str and identifier.startswith('character-trial-'):
            result = frame.get('result')
            outcome = 'HOST_RESPONSE_UNAVAILABLE'
            if set(frame) == {'jsonrpc', 'id', 'result'} and type(result) is dict:
                action, content = result.get('action'), result.get('content')
                if action == 'accept' and content == {'decision': 'confirm_rehearsal'}:
                    outcome = 'COMPLETED'
                elif action == 'decline':
                    outcome = 'DECLINED'
                elif action == 'cancel' or (action == 'accept' and content == {'decision': 'cancel_rehearsal'}):
                    outcome = 'CANCELLED'
            self.resolve(identifier, outcome)
            return True
        if frame.get('method') == 'notifications/cancelled' and 'id' not in frame:
            params = frame.get('params')
            if type(params) is dict and type(params.get('requestId')) in {str, int}:
                with self.lock:
                    cancelled = [key for key, call in self.pending.items() if call[0] == params['requestId']]
                for key in cancelled:
                    self.resolve(key, 'CANCELLED', respond=False)
            return False
        return False

    def close(self):
        with self.lock:
            keys = tuple(self.pending)
        for key in keys:
            self.resolve(key, 'HOST_RESPONSE_UNAVAILABLE', respond=False)
