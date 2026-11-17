"""Read Suno via the user's official Codex MCP client, without handling OAuth tokens."""
from contextlib import contextmanager
import json
import os
from pathlib import Path
import re
import select
import subprocess
from tempfile import TemporaryDirectory
from time import monotonic, time
from urllib.parse import urlsplit

from .contracts import WCEError
from .own_update_install import BUNDLED_CLI

SERVER = 'suno'
ENDPOINT = 'https://api.suno.com/mcp'
HTTPS_AUDIO_HOST = 'suno-data-uploads.s3.amazonaws.com'
AVATAR_HOSTS = {'cdn1.suno.ai', 'cdn2.suno.ai'}
PAGE_SIZE = 12
APP_SERVER_TIMEOUT = 27
MAX_RESPONSE = 2_000_000
PRESENCE_TIMEOUT = 3
UUID = re.compile(r'[a-f0-9]{8}(?:-[a-f0-9]{4}){3}-[a-f0-9]{12}')
HANDLE = re.compile(r'[A-Za-z0-9_.-]{1,80}')
READ_TOOLS = frozenset(('account-me', 'account-usage', 'library-list', 'audio-download'))


def scoped_configuration():
    allow = json.dumps(sorted(READ_TOOLS), separators=(',', ':'))
    return ['-c', f'mcp_servers.suno.url="{ENDPOINT}"',
            '-c', 'mcp_oauth_credentials_store="keyring"',
            '-c', f'mcp_servers.suno.enabled_tools={allow}',
            '-c', 'features.plugins=false']


def require_existing_oauth(binary, scope):
    # The CLI list inspects the credential store. It never opens a browser
    # or owns a callback. Check before starting an MCP connection.
    try:
        process = subprocess.run([str(binary), 'mcp', 'list', *scoped_configuration(), '--json'],
                                 cwd=scope, env=dict(os.environ, CODEX_HOME=str(scope)),
                                 stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
                                 timeout=PRESENCE_TIMEOUT, check=True)
        rows = json.loads(process.stdout)
    except (OSError, ValueError, subprocess.SubprocessError):
        raise WCEError('SUNO_CODEX_AUTH_CHECK_UNAVAILABLE') from None
    if not isinstance(rows, list) or len(rows) != 1 or not isinstance(rows[0], dict):
        raise WCEError('SUNO_CODEX_SCOPE_MISMATCH')
    row = rows[0]
    transport = row.get('transport')
    if (row.get('name') != SERVER or row.get('enabled') is not True or not isinstance(transport, dict)
            or transport.get('url') != ENDPOINT):
        raise WCEError('SUNO_CODEX_SCOPE_MISMATCH')
    if row.get('auth_status') != 'o_auth':
        raise WCEError('SUNO_CODEX_AUTH_REQUIRED')


@contextmanager
def codex_client():
    binary = next((path for path in (BUNDLED_CLI, Path('/opt/homebrew/bin/codex'),
                                    Path('/usr/local/bin/codex')) if path.is_file()), None)
    if binary is None:
        raise WCEError('SUNO_CODEX_CLIENT_UNAVAILABLE')
    with TemporaryDirectory(prefix='openahoy-suno-client-') as location:
        # The official Keychain store is independent of CODEX_HOME. A fresh
        # workspace isolates all other registered MCPs, hooks and plugins.
        scope = Path(location).resolve()
        require_existing_oauth(binary, scope)
        with scoped_client(binary, scope) as tool:
            yield tool


@contextmanager
def scoped_client(binary, scope):
    deadline = monotonic() + APP_SERVER_TIMEOUT
    process = subprocess.Popen(
        [str(binary), 'app-server', *scoped_configuration(), '--listen', 'stdio://'],
        cwd=scope, env=dict(os.environ, CODEX_HOME=str(scope)), stdin=subprocess.PIPE,
        stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
    )
    counter = 0
    buffer = b''

    def rpc(method, args, *, notify=False):
        nonlocal counter, buffer
        counter += 1
        message = {'method': method, 'params': args}
        if not notify:
            message['id'] = counter
        process.stdin.write(json.dumps(message).encode() + b'\n')
        process.stdin.flush()
        if notify:
            return None
        while monotonic() < deadline:
            line, sep, remaining = buffer.partition(b'\n')
            if sep:
                buffer = remaining
                reply = json.loads(line)
                if reply.get('id') != counter or 'method' in reply:
                    continue
                if 'result' not in reply:
                    raise WCEError('SUNO_CODEX_RPC_UNAVAILABLE')
                return reply['result']
            if len(buffer) >= MAX_RESPONSE:
                raise WCEError('SUNO_CODEX_RESPONSE_INVALID')
            if not select.select([process.stdout], [], [], max(0, deadline-monotonic()))[0]:
                break
            payload = os.read(process.stdout.fileno(), 65536)
            if not payload:
                raise WCEError('SUNO_CODEX_RPC_UNAVAILABLE')
            buffer += payload
        raise WCEError('SUNO_CODEX_READ_TIMEOUT')

    try:
        rpc('initialize', {'clientInfo': {'name': 'openahoy-suno-panel', 'version': '1'},
                           'capabilities': {'experimentalApi': True}})
        rpc('initialized', {}, notify=True)
        thread = rpc('thread/start', {'cwd': str(scope), 'ephemeral': True,
                                     'approvalPolicy': 'never', 'sandbox': 'read-only'})['thread']['id']
        response = rpc('mcpServerStatus/list', {'detail': 'full', 'threadId': thread})
        rows = response['data']
        if [row.get('name') for row in rows] != [SERVER]:
            raise WCEError('SUNO_CODEX_SCOPE_MISMATCH')
        server = rows[0]
        if not set(server.get('tools', {})) <= READ_TOOLS:
            raise WCEError('SUNO_CODEX_SCOPE_MISMATCH')
        if server.get('authStatus') != 'oAuth':
            raise WCEError('SUNO_CODEX_AUTH_REQUIRED')

        def tool(name, args):
            if name not in READ_TOOLS or (name == 'audio-download' and set(args) != {'id', 'format'}):
                raise WCEError('SUNO_CODEX_TOOL_NOT_ALLOWED')
            if name not in server.get('tools', {}):
                raise WCEError('SUNO_CODEX_TOOL_UNAVAILABLE')
            reply = rpc('mcpServer/tool/call', {'threadId': thread, 'server': SERVER, 'tool': name, 'arguments': args})
            if not reply.get('isError'):
                data = reply.get('structuredContent')
                if isinstance(data, dict):
                    return data
                for block in reply.get('content', ()):
                    if block.get('type') == 'text':
                        data = json.loads(block['text'])
                        if isinstance(data, dict):
                            return data
            raise WCEError('SUNO_TOOL_READ_FAILED')

        yield tool
    except (OSError, ValueError, TypeError, KeyError):
        raise WCEError('SUNO_CODEX_RESPONSE_INVALID') from None
    finally:
        if process.poll() is None:
            process.terminate()
            try:
                process.wait(timeout=1)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait()
        process.stdin.close()
        process.stdout.close()


def public_string(value, limit):
    return value[:limit] if isinstance(value, str) else ''


def url_from(value, hosts):
    if not isinstance(value, str) or len(value) > 6000:
        return ''
    try:
        parsed = urlsplit(value)
        if parsed.scheme == 'https' and parsed.netloc in hosts and not parsed.fragment:
            return value
    except ValueError:
        pass
    return ''


def profile(tool):
    value = tool('account-me', {})
    handle = value.get('handle')
    if not isinstance(handle, str) or not HANDLE.fullmatch(handle):
        raise WCEError('SUNO_CODEX_IDENTITY_UNAVAILABLE')
    avatar = url_from(value.get('avatar_url'), AVATAR_HOSTS)
    if avatar and (urlsplit(avatar).query or not urlsplit(avatar).path):
        avatar = ''
    return {'handle': handle, 'display_name': public_string(value.get('display_name'), 100),
            'avatar_url': avatar}


def usage_projection(result):
    account = result.get('suno_account')
    if not isinstance(account, dict):
        return None
    value = {key: number for key in ('credits_remaining', 'download_credits_remaining', 'monthly_limit', 'monthly_usage')
             if type(number := account.get(key)) is int and number >= 0}
    plan = account.get('plan')
    if isinstance(plan, dict):
        value['plan'] = public_string(plan.get('name'), 100)
        value['period'] = public_string(plan.get('period'), 25)
    for name in ('renews_on', 'cancel_on'):
        if label := public_string(account.get(name), 40):
            value[name] = label
    models = result.get('allowed_models')
    if isinstance(models, list):
        value['models'] = [model[:40] for model in models[:30] if isinstance(model, str)]
    features = result.get('features')
    if isinstance(features, list):
        value['features'] = [name[:80] for name in features[:30] if isinstance(name, str)]
    return value


def library_page(tool, *, downloaded=False, cursor=None):
    args = {'limit': PAGE_SIZE}
    if downloaded:
        args['downloaded'] = True
    if cursor:
        args['cursor'] = cursor
    result = tool('library-list', args)
    if not isinstance(result.get('items'), list):
        raise WCEError('SUNO_LIBRARY_UNAVAILABLE')
    return result


def library_projection(result):
    items = []
    for value in result['items'][:PAGE_SIZE]:
        if not isinstance(value, dict):
            continue
        track = value.get('id')
        if not isinstance(track, str) or not UUID.fullmatch(track):
            continue
        song = url_from(value.get('song_url'), {'suno.com'})
        if song and song != f'https://suno.com/song/{track}':
            song = ''
        metadata = value.get('metadata')
        model = public_string(metadata.get('model'), 40) if isinstance(metadata, dict) else ''
        items.append({'id': track, 'title': public_string(value.get('title'), 180),
                      'status': public_string(value.get('status'), 25), 'song_url': song, 'model': model})
    cursor = result.get('next_cursor')
    return {'items': items, 'cursor': cursor if isinstance(cursor, str) and 0 < len(cursor) <= 2048 else ''}


def snapshot(tool, *, downloaded=False, cursor=None, expected=None, library_only=False):
    account = profile(tool)
    if expected is not None and expected != account['handle']:
        raise WCEError('SUNO_CODEX_ACCOUNT_CHANGED')
    usage = None
    if not library_only:
        try:
            usage = usage_projection(tool('account-usage', {}))
        except WCEError:
            pass
    try:
        library = library_projection(library_page(tool, downloaded=downloaded, cursor=cursor))
    except WCEError:
        library = None
    return {'state': 'CONNECTED', 'account': account, 'usage': usage, 'library': library,
            'read_at': int(time()), 'usage_checked': not library_only}


def playback(tool, *, track, expected, cursor=None):
    if profile(tool)['handle'] != expected:
        raise WCEError('SUNO_CODEX_ACCOUNT_CHANGED')
    library = library_projection(library_page(tool, downloaded=True, cursor=cursor))
    if not any(row['id'] == track and row['status'] == 'complete' for row in library['items']):
        raise WCEError('SUNO_PREVIOUS_DOWNLOAD_REQUIRED')
    result = tool('audio-download', {'id': track, 'format': 'mp3'})
    if result.get('status') == 'requires_credit':
        raise WCEError('SUNO_PLAYBACK_REQUIRES_CREDIT')
    if result.get('status') == 'processing':
        raise WCEError('SUNO_PLAYBACK_PREPARING')
    url = url_from(result.get('url'), {HTTPS_AUDIO_HOST})
    if (result.get('status') != 'ok' or result.get('format') != 'mp3' or not url
            or not urlsplit(url).path.startswith('/studio/uploads/')):
        raise WCEError('SUNO_PLAYBACK_UNAVAILABLE')
    return {'state': 'PLAYBACK_READY', 'url': url}


def run(action, arguments):
    try:
        with codex_client() as tool:
            return (snapshot if action == 'suno_snapshot' else playback)(tool, **arguments)
    except (OSError, WCEError) as error:
        return {'state': 'UNAVAILABLE', 'code': getattr(error, 'code', 'SUNO_CODEX_CLIENT_UNAVAILABLE')}
