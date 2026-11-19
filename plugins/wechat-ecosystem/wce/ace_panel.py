"""ACE Music panel reads and OAuth via the official local Codex client."""
import atexit
import fcntl
import os
from pathlib import Path
import re
import stat
import subprocess
from tempfile import TemporaryDirectory, gettempdir
from threading import Lock, Thread
from urllib.parse import urlsplit

from .contracts import WCEError
from .suno_panel import MusicMcp, codex_binary, codex_client, public_string, scoped_configuration

ACE = MusicMcp('ace-music', 'https://acemusic.ai/mcp', 'ACE',
               frozenset(('get_account', 'list_songs')))
ORIGIN = 'https://acemusic.ai'
SONG_ID = re.compile(r'[A-Za-z0-9_-]{1,96}')
AUTH_SCOPES = 'songs:read,songs:create'
AUTH_TIMEOUT = 300
PAGE_SIZE = 12


def official_url(value):
    if not isinstance(value, str) or not value or len(value) > 4000 or any(
            ord(char) <= 32 or char == '\\' for char in value):
        return ''
    try:
        url = urlsplit(value)
    except ValueError:
        return ''
    if url.scheme == 'https' and url.netloc == 'acemusic.ai' and url.path.startswith('/') and not url.fragment:
        return value
    return ''


def account_view(data):
    if not isinstance(data, dict) or data.get('error'):
        raise WCEError('ACE_ACCOUNT_UNAVAILABLE')
    value = {}
    for key in ('display_name', 'username'):
        if label := public_string(data.get(key), 100):
            value[key] = label
    plan = data.get('plan')
    if label := public_string(data.get('plan_name') or plan, 100):
        value['plan'] = label
    for remote, local in (('credits', 'credits'), ('credits_per_create_song', 'generation_cost')):
        amount = data.get(remote)
        if type(amount) is int and amount >= 0:
            value[local] = amount
    models = data.get('models')
    if isinstance(models, list):
        value['models'] = []
        for model in models[:30]:
            if not isinstance(model, dict):
                continue
            if label := public_string(model.get('name') or model.get('id'), 100):
                row = {'name': label}
                cost = model.get('credits_per_create_song')
                if type(cost) is int and cost >= 0:
                    row['cost'] = cost
                value['models'].append(row)
    downloads = data.get('can_download')
    if plan == 'free':
        # ACE publishes this MCP restriction even though free web playback is available.
        value['can_download'] = False
    elif type(downloads) is bool:
        value['can_download'] = downloads
    return value


def library_args(descriptor, cursor):
    schema = descriptor.get('inputSchema', {})
    props = schema.get('properties', {})
    args = {}
    if props.get('limit', {}).get('type') == 'integer':
        spec = props['limit']
        args['limit'] = max(spec.get('minimum', 1), min(PAGE_SIZE, spec.get('maximum', PAGE_SIZE)))
    if cursor:
        if props.get('cursor', {}).get('type') != 'string':
            raise WCEError('ACE_LIBRARY_UNAVAILABLE')
        args['cursor'] = cursor
    if set(schema.get('required', ())) - args.keys():
        raise WCEError('ACE_LIBRARY_UNAVAILABLE')
    return args


def library_view(data, *, can_page, can_download=None):
    songs = data.get('songs', data.get('items'))
    if not isinstance(songs, list) or data.get('error'):
        raise WCEError('ACE_LIBRARY_UNAVAILABLE')
    view = {'items': []}
    for song in songs:
        if not isinstance(song, dict):
            continue
        key = song.get('song_id', song.get('id'))
        if not isinstance(key, str) or not SONG_ID.fullmatch(key):
            continue
        page = official_url(song.get('song_page'))
        if page and not urlsplit(page).path.startswith('/song/'):
            page = ''
        track = {'id': key, 'title': public_string(song.get('title'), 180),
                 'status': public_string(song.get('status'), 40), 'page': page,
                 'play': official_url(song.get('playback_url'))}
        permission = song.get('can_download')
        if can_download is False or permission is False:
            track['can_download'] = False
        elif can_download is True or permission is True:
            track['can_download'] = True
        view['items'].append(track)
    cursor = data.get('next_cursor')
    if can_page and isinstance(cursor, str) and 0 < len(cursor) <= 512:
        view['cursor'] = cursor
    return view


def snapshot(cursor=None):
    try:
        with codex_client(ACE) as tool:
            if 'get_account' not in tool.catalog:
                raise WCEError('ACE_CODEX_TOOL_UNAVAILABLE')
            account = account_view(tool('get_account', {}))
            library = None
            if 'list_songs' in tool.catalog:
                try:
                    descriptor = tool.catalog['list_songs']
                    arguments = library_args(descriptor, cursor)
                    can_page = descriptor.get('inputSchema', {}).get('properties', {}).get('cursor', {}).get('type') == 'string'
                    library = library_view(tool('list_songs', arguments), can_page=can_page,
                                           can_download=account.get('can_download'))
                except (WCEError, TypeError, AttributeError):
                    pass
            return {'state': 'CONNECTED', 'account': account, 'library': library}
    except (OSError, WCEError) as error:
        return {'state': 'UNAVAILABLE', 'code': getattr(error, 'code', 'ACE_CODEX_CLIENT_UNAVAILABLE')}


class Authorizer:
    """One application-owned login listener at a time, including across panel processes."""

    def __init__(self, *, lock_path=None, popen=subprocess.Popen, timeout=AUTH_TIMEOUT):
        self.path = lock_path or Path(gettempdir()).resolve() / f'openahoy-ace-oauth-{os.getuid()}.lock'
        self.popen = popen
        self.timeout = timeout
        self.guard = Lock()
        self.process = None
        self.state = 'IDLE'

    def status(self):
        with self.guard:
            return {'state': self.state}

    def begin(self):
        with self.guard:
            if self.process is not None:
                return {'state': self.state}
            fd = None
            scope = None
            try:
                fd = os.open(self.path, os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW | os.O_NONBLOCK, 0o600)
                info = os.fstat(fd)
                if not stat.S_ISREG(info.st_mode) or info.st_uid != os.getuid() or info.st_nlink != 1 or info.st_mode & 0o077:
                    raise OSError('unsafe ACE login lock')
                try:
                    fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
                except BlockingIOError:
                    return {'state': 'AUTHORIZING_ELSEWHERE'}
                scope = TemporaryDirectory(prefix='openahoy-ace-oauth-')
                binary = codex_binary(ACE)
                process = self.popen(
                    [str(binary), 'mcp', 'login', ACE.name, '--scopes', AUTH_SCOPES, *scoped_configuration(ACE)],
                    cwd=scope.name, env=dict(os.environ, CODEX_HOME=scope.name),
                    stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                    pass_fds=(fd,),
                )
                self.process = process
                self.state = 'AUTHORIZING'
                Thread(target=self._finish, args=(process, scope, fd), daemon=True).start()
                scope = fd = None
            except (OSError, WCEError):
                self.state = 'AUTH_FAILED'
            finally:
                if fd is not None:
                    os.close(fd)
                if scope is not None:
                    scope.cleanup()
            return {'state': self.state}

    @staticmethod
    def _stop(process):
        if process.poll() is None:
            process.terminate()
            try:
                process.wait(timeout=1)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait()

    def _finish(self, process, scope, fd):
        try:
            state = 'AUTHORIZED' if process.wait(timeout=self.timeout) == 0 else 'AUTH_FAILED'
        except subprocess.TimeoutExpired:
            self._stop(process)
            state = 'AUTH_EXPIRED'
        finally:
            os.close(fd)
            scope.cleanup()
        with self.guard:
            if self.process is process:
                self.process = None
                self.state = 'CANCELLED' if self.state == 'CANCELLING' and state != 'AUTHORIZED' else state

    def cancel(self):
        with self.guard:
            process = self.process
            if process is None or process.poll() is not None:
                return {'state': self.state}
            self.state = 'CANCELLING'
            self._stop(process)
            return {'state': self.state}


AUTH = Authorizer()
atexit.register(AUTH.cancel)


def run(action, arguments):
    if action == 'ace_snapshot':
        return snapshot(**arguments)
    if action == 'ace_oauth_begin':
        return AUTH.begin()
    if action == 'ace_oauth_cancel':
        return AUTH.cancel()
    if action == 'ace_oauth_status':
        return AUTH.status()
    raise WCEError('ACE_ACTION_UNAVAILABLE')
