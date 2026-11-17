"""Recoverable Ark job receipts and immutable private MP4 assets."""
from base64 import b64encode
from contextlib import closing, ExitStack
from hashlib import file_digest, sha256
import json
import os
from pathlib import Path
import re
import stat
import subprocess
import tempfile
import time

from .bounded_file import FileSource
from .contracts import WCEError
from .own_bootstrap_security import path_check
from .own_connection_policy import atomic_write, locked, read_optional
from .own_connection_registry import mkdir
from .project_context import ProjectStore
from .video_keychain import load
from .video_minimax import (H3, H3_MODELS, MINIMAX_MODELS, SUBJECT_MODEL, V1_MODELS, SITES,
                            MiniMax, MiniMaxRejected, h3_body, h3_usage, subject_body, v1_body)
from .video_relay import RELAY_MODEL, Relay, RelaySubmitError, workflow_body
from .video_relay_keychain import load_relay
from .video_tokenhex import TOKENHEX_ORIGIN, TOKENHEX_PROVIDER, TokenHex, load_tokenhex
from .video_seedance import Ark, ArkSubmitRejected, MINI, MODEL, PRO, STANDARD, MAX_REQUEST, MAX_RESULT, ark_error_code, request_body, result_url, validate_model

ATTEMPT = re.compile(r'[A-Za-z0-9_-]{1,96}\Z')
FRAME_LIMIT = 30_000_000
PLAYBACK_CHUNK = 384 * 1024
PROBE = Path(__file__).resolve().parents[1] / 'native' / 'openahoy-video-inspect'
PACKAGE = PROBE.parents[1]
PROMO_DIR = (PACKAGE / 'integrations/codex' if (PACKAGE / 'integrations/codex').is_dir() else PACKAGE) / 'assets/home-video'
PROMO_SHA = '4284baabff6a818d6721c249d80bb7bd938d23d71161929e72a0ec311d44bd90'
PROJECT_VIDEO_DIR = ('assets', 'openahoy', 'videos')
RECEIPT_MAX = 1024 * 1024


def provider_usage(value):
    """Project the documented optional Ark counters, keeping zero distinct from absence."""
    if type(value) is not dict:
        return {}

    def count(number):
        return type(number) is int and 0 <= number <= 2**53 - 1

    usage = {key: value[key] for key in ('completion_tokens', 'total_tokens')
             if count(value.get(key))}
    tools = value.get('tool_usage')
    if type(tools) is dict and count(tools.get('web_search')):
        usage['tool_usage'] = {'web_search': tools['web_search']}
    return usage


def image(path, root, expected, scratch, *, h3=False):
    if not path.is_absolute() or '..' in path.parts or not path.is_relative_to(root):
        raise WCEError('VIDEO_FRAME_OUTSIDE_PROJECT')
    raw = bytearray()
    for chunk in FileSource(root).iter_html(path.relative_to(root).as_posix()):
        raw.extend(chunk)
        if len(raw) >= FRAME_LIMIT:
            raise WCEError('VIDEO_FRAME_TOO_LARGE')
    data = bytes(raw)
    if expected is not None and sha256(data).hexdigest() != expected:
        raise WCEError('VIDEO_FRAME_CHANGED')
    with tempfile.NamedTemporaryFile(prefix='.frame-', dir=scratch) as temporary:
        temporary.write(data)
        temporary.flush()
        facts = probe('image-h3' if h3 else 'image', temporary.name, error='VIDEO_FRAME_INVALID')
    mime = {'public.png': 'image/png', 'public.jpeg': 'image/jpeg'}.get(facts.get('type'))
    if mime is None:
        raise WCEError('VIDEO_FRAME_INVALID')
    return mime, data


def probe(*args, error):
    try:
        result = subprocess.run([str(PROBE), *args], stdin=subprocess.DEVNULL,
                                capture_output=True, check=True, timeout=20)
        facts = json.loads(result.stdout)
        if type(facts) is dict:
            return facts
    except (OSError, ValueError, subprocess.SubprocessError):
        pass
    raise WCEError(error)


def media_facts(path):
    with path.open('rb') as stream:
        head = stream.read(12)
    if head[4:8] != b'ftyp':
        raise WCEError('VIDEO_RESULT_INVALID')
    facts = probe(str(path), error='VIDEO_RESULT_INVALID')
    if (facts.get('playable') is True and type(facts.get('audio_tracks')) is int
            and facts['audio_tracks'] >= 0
            and all(type(facts.get(k)) is int and 0 < facts[k] <= 4096 for k in ('width', 'height'))
            and type(facts.get('seconds')) in (float, int) and 0 < facts['seconds'] <= 60):
        return facts
    raise WCEError('VIDEO_RESULT_INVALID')


class Jobs:
    def __init__(self, registry=None, *, api=None, credential=load, inspect=media_facts,
                 minimax=MiniMax, minimax_credential=load, relay=Relay, relay_credential=load_relay,
                 tokenhex=None, tokenhex_credential=load_tokenhex):
        self.projects = ProjectStore(registry)
        self.root = self.projects.root / 'video-ark'
        self.api = api if api is not None else Ark()
        self.credential = credential
        self.minimax = minimax
        self.minimax_credential = minimax_credential
        self.relay = relay
        self.relay_credential = relay_credential
        self.tokenhex = tokenhex if tokenhex is not None else TokenHex()
        self.tokenhex_credential = tokenhex_credential
        self.inspect = inspect
        self.playback_pin = None

    def _directory(self):
        for path in (self.root.parent, self.root):
            if not os.path.lexists(path):
                try:
                    mkdir(path.parent, path.name) if path == self.root else os.mkdir(path, 0o700)
                except FileExistsError:
                    pass
            path_check(path, True)

    def _paths(self, attempt):
        if type(attempt) is not str or not ATTEMPT.fullmatch(attempt):
            raise WCEError('INVALID_TOOL_ARGUMENTS')
        return tuple(self.root / (attempt + suffix) for suffix in ('.json', '.mp4'))

    def history(self, project_id=None, *, monitor=False):
        projects = self.projects.view()['projects']
        directory = [{'id': item['id'], 'name': item['name']} for item in projects]
        if project_id is None:
            recent = read_optional(self.root / 'selected-project.state')
            return {'projects': directory, 'versions': [], 'recent_project': (recent or {}).get('project_id')}
        project = next((item for item in projects if item['id'] == project_id), None)
        if project is None:
            return {'projects': directory, 'versions': []}
        if not os.path.lexists(self.root):
            return {'projects': directory, 'versions': []}
        path_check(self.root, True)
        selection = read_optional(self.root / ('selection-' + project_id + '.state')) or {}
        versions = []
        library = []
        for receipt in self.root.glob('*.json'):
            if not ATTEMPT.fullmatch(receipt.stem):
                continue
            row = read_optional(receipt, RECEIPT_MAX)
            if row is None or row['request']['project_id'] != project_id:
                continue
            version = self.workspace_row(row, recipe=not monitor)
            if monitor:
                for key in ('provider_task_id', 'updated_at'):
                    if key in row:
                        version[key] = row[key]
                if 'source_sha256' in row['request']:
                    version['source_sha256'] = row['request']['source_sha256']
                diagnostic = next((row[key] for key in ('query_error', 'download_error', 'rejection',
                                                         'failure', 'submit_diagnostic') if key in row), None)
                if isinstance(diagnostic, dict):
                    version['monitor_diagnostic'] = diagnostic.get('code')
                for key in ('query_error', 'download_error', 'rejection', 'failure', 'submit_diagnostic'):
                    version.pop(key, None)
            versions.append(version)
            if row['state'] == 'ASSET_READY':
                library.append(self.library_row(row, project))
        versions.sort(key=lambda row: (row['created_at'], row['generation_attempt_id']), reverse=True)
        library.sort(key=lambda row: (row['created_at'], row['generation_attempt_id']), reverse=True)
        return {'projects': directory, 'versions': versions, 'selection': selection, 'library': library}

    def _library_path(self, attempt):
        return self._paths(attempt)[0].with_suffix('.library')

    @staticmethod
    def _filename(attempt, asset):
        return f'OpenAhoy-{attempt}-{asset["sha256"][:12]}.mp4'

    def library_row(self, row, project):
        attempt, asset = row['generation_attempt_id'], row['asset']
        metadata = read_optional(self._library_path(attempt)) or {}
        filename = self._filename(attempt, asset)
        source = 'READY'
        try:
            info = path_check(self._paths(attempt)[1])
            if info[2] != asset['bytes']:
                source = 'UNAVAILABLE'
        except (OSError, WCEError):
            source = 'UNAVAILABLE'
        value = {'generation_attempt_id': attempt, 'created_at': row['created_at'],
                 'seconds': asset['seconds'], 'name': metadata.get('name') or attempt,
                 'trashed': metadata.get('trashed', False), 'state': source, 'storage': 'HISTORY'}
        if 'project_video_root' in row:
            relative = Path(*PROJECT_VIDEO_DIR, filename)
            value.update(project_path=relative.as_posix(), storage='COPY_PENDING')
            try:
                folder = self._project_video_folder(project, row['project_video_root'])
                try:
                    info = os.stat(filename, dir_fd=folder, follow_symlinks=False)
                    expected = row.get('project_video_copy')
                    value['storage'] = ('SAVED' if self._file_identity(info) == expected
                                        else 'COPY_CONFLICT')
                finally:
                    os.close(folder)
            except FileNotFoundError:
                pass
            except (OSError, WCEError):
                value['storage'] = 'COPY_UNAVAILABLE'
        return value

    def library_action(self, command, attempt, project_id, name=None):
        receipt, _ = self._paths(attempt)
        project = next((item for item in self.projects.view()['projects'] if item['id'] == project_id), None)
        if project is None or not os.path.lexists(self.root):
            raise WCEError('VIDEO_ASSET_NOT_READY')
        with locked(self.root / 'generation.lock'):
            row = read_optional(receipt, RECEIPT_MAX)
            if row is None or row['state'] != 'ASSET_READY' or row['request']['project_id'] != project_id:
                raise WCEError('VIDEO_ASSET_NOT_READY')
            path = self._library_path(attempt)
            metadata = read_optional(path) or {}
            if command == 'copy':
                if metadata.get('trashed') or 'project_video_root' not in row:
                    raise WCEError('VIDEO_PROJECT_COPY_UNAVAILABLE')
                self._save_project_copy(row, receipt, project)
            else:
                if command == 'rename':
                    if (type(name) is not str or not 0 < len(name.strip()) <= 120
                            or any(not char.isprintable() for char in name.strip())):
                        raise WCEError('VIDEO_LIBRARY_NAME_INVALID')
                    metadata['name'] = name.strip()
                elif command in {'trash', 'restore'}:
                    metadata['trashed'] = command == 'trash'
                else:
                    raise WCEError('INVALID_TOOL_ARGUMENTS')
                atomic_write(path, metadata)
            return self.library_row(row, project)

    @staticmethod
    def _file_identity(info):
        return [info.st_dev, info.st_ino, info.st_size, info.st_mtime_ns, info.st_ctime_ns]

    @staticmethod
    def _project_video_folder(project, identity, *, create=False, components=PROJECT_VIDEO_DIR):
        from .own_configuration_export import _directory

        with ExitStack() as stack:
            root = Path(project['root'])
            parent = _directory(root)
            stack.callback(os.close, parent)
            info = os.fstat(parent)
            if [info.st_dev, info.st_ino] != identity:
                raise WCEError('VIDEO_PROJECT_ROOT_CHANGED')
            for name in components:
                if create:
                    try:
                        os.mkdir(name, 0o700, dir_fd=parent)
                    except FileExistsError:
                        pass
                child = os.open(name, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=parent)
                stack.callback(os.close, child)
                info = os.fstat(child)
                if info.st_uid != os.getuid() or info.st_mode & 0o022:
                    raise WCEError('VIDEO_PROJECT_COPY_UNAVAILABLE')
                parent = child
            return os.dup(parent)

    def _save_project_copy(self, row, receipt, project=None):
        if 'project_video_root' not in row:
            return
        try:
            if project is None:
                project = next((p for p in self.projects.view()['projects']
                                if p['id'] == row['request']['project_id']), None)
            if project is None:
                return
            attempt = row['generation_attempt_id']
            source, asset, pin = self._playable(attempt, project['id'])
            filename = self._filename(attempt, asset)
            root_identity = row['project_video_root']
            folder = self._project_video_folder(project, root_identity, create=True)
            try:
                def verify_folder():
                    live = self._project_video_folder(project, root_identity)
                    try:
                        if not os.path.samestat(os.fstat(live), os.fstat(folder)):
                            raise WCEError('VIDEO_PROJECT_COPY_UNAVAILABLE')
                    finally:
                        os.close(live)

                copy = self._copy_original(source, asset, pin, folder, filename, before_link=verify_folder)
                verify_folder()
                if copy != self._file_identity(os.stat(filename, dir_fd=folder, follow_symlinks=False)):
                    raise WCEError('VIDEO_PROJECT_COPY_UNAVAILABLE')
            finally:
                os.close(folder)
            new = dict(row, project_video_copy=copy)
            atomic_write(receipt, new, maximum=RECEIPT_MAX)
            row.update(new)
        except (OSError, WCEError):
            # The verified original and provider receipt are already durable.
            # A missing/unsafe/conflicting project copy never resubmits the job.
            return

    def select_versions(self, project_id, primary, compare=None):
        self._directory()
        with locked(self.root / 'generation.lock'):
            for attempt in filter(None, (primary, compare)):
                row = read_optional(self._paths(attempt)[0], RECEIPT_MAX)
                if row is None or row['request']['project_id'] != project_id:
                    raise WCEError('VIDEO_VERSION_NOT_FOUND')
            atomic_write(self.root / ('selection-' + project_id + '.state'),
                         {'primary': primary, 'compare': compare})
            atomic_write(self.root / 'selected-project.state', {'project_id': project_id})
        return {'state': 'SAVED'}

    def resolve_frames(self, project_id, paths, *, h3=False):
        project = next((row for row in self.projects.view()['projects'] if row['id'] == project_id), None)
        if not project:
            raise WCEError('VIDEO_PROJECT_NOT_REGISTERED')
        self._directory()
        root = Path(project['root'])
        rows = []
        encoded_size = 0
        for relative in paths:
            if Path(relative).is_absolute() or '..' in Path(relative).parts:
                raise WCEError('VIDEO_FRAME_OUTSIDE_PROJECT')
            path = root / relative
            _, data = image(path, root, None, self.root, h3=h3)
            encoded_size += ((len(data) + 2) // 3) * 4
            if encoded_size >= MAX_REQUEST:
                raise WCEError('VIDEO_REQUEST_TOO_LARGE')
            rows.append({'path': str(path), 'sha256': sha256(data).hexdigest()})
        return rows

    @staticmethod
    def workspace_row(row, recipe=False):
        request = row['request']
        value = {key: row[key] for key in ('generation_attempt_id', 'state', 'created_at')}
        value['model'] = request['model']
        if request.get('provider') == TOKENHEX_PROVIDER:
            value['provider'] = TOKENHEX_PROVIDER
        value['mode'] = request.get('mode', 'frames')
        if request['model'] not in (RELAY_MODEL, SUBJECT_MODEL):
            value['duration'] = request.get('duration', 5)
        elif 'duration' in request:
            value['duration'] = request['duration']
        if 'source_attempt_id' in request:
            value['source_attempt_id'] = request['source_attempt_id']
        is_minimax = request['model'] in MINIMAX_MODELS
        usage = (h3_usage(row.get('usage')) if is_minimax else
                 provider_usage({'total_tokens': row.get('total_tokens')}) | provider_usage(row.get('usage')))
        if usage:
            value['usage'] = usage
        if is_minimax:
            value['provider_site'] = request['provider_site']
        if 'asset' in row:
            value['asset'] = {k: v for k, v in row['asset'].items() if k != 'path'}
            if request['model'] == H3 and request['provider_site'] == 'global' and {'output_seconds', 'input_image_count'} <= usage.keys():
                rate = {'768P': 0.08, '2K': 0.13}[request['resolution']]
                value['list_price_usd'] = round(usage['output_seconds'] * rate +
                                                max(0, usage['input_image_count'] - 5) * 0.04, 2)
            tokens = usage.get('completion_tokens', usage.get('total_tokens'))
            resolution = request.get('resolution', '720p')
            video_input = request.get('mode') in ('edit', 'extend')
            # Public Ark China list rates in CNY per million tokens, before billing adjustments.
            rates = {
                MODEL: {'480p': (70, 42), '720p': (70, 42), '1080p': (77, 46)},
                STANDARD: {'720p': (46, 28)}, MINI: {'720p': (23, 14)}, PRO: {'720p': (15, 15)},
            }
            rate = rates.get(value['model'], {}).get(resolution)
            if request.get('provider') != TOKENHEX_PROVIDER and rate and tokens is not None:
                value['list_price_cny'] = (tokens * rate[video_input] + 5_000) // 10_000 / 100
        if recipe and 'recipe' in row:
            value['recipe'] = row['recipe']
        for key in ('rejection', 'failure', 'query_error', 'download_error', 'submit_diagnostic'):
            if key in row:
                value[key] = row[key]
        return value

    def playback(self, attempt, project_id, offset):
        artifact, asset, pin = self._playable(attempt, project_id)
        if not 0 <= offset < asset['bytes']:
            raise WCEError('VIDEO_ASSET_OFFSET_INVALID')
        chunk = bytearray()
        with closing(FileSource(self.root).iter_html(artifact.name, expected_state=pin, offset=offset)) as stream:
            for part in stream:
                chunk.extend(part[:PLAYBACK_CHUNK-len(chunk)])
                if len(chunk) == PLAYBACK_CHUNK:
                    break
        if path_check(artifact) != pin or not chunk:
            raise WCEError('VIDEO_ASSET_CHANGED')
        return {'offset': offset, 'total': asset['bytes'], 'sha256': asset['sha256'],
                'bytes': b64encode(chunk).decode('ascii')}

    def preview_frames(self, start, attempt=None, project_id=None):
        if attempt is None:
            artifact = PROMO_DIR / 'openahoy-intro.mp4'
            try:
                if artifact.is_symlink() or sha256(artifact.read_bytes()).hexdigest() != PROMO_SHA:
                    raise WCEError('VIDEO_ASSET_CHANGED')
            except OSError:
                raise WCEError('VIDEO_PREVIEW_UNAVAILABLE') from None
            asset = {'seconds': 10.5}
        else:
            artifact, asset, pin = self._playable(attempt, project_id)
        if start >= asset['seconds'] * 8:
            raise WCEError('VIDEO_ASSET_OFFSET_INVALID')
        result = probe('frames', str(artifact), str(start), error='VIDEO_PREVIEW_UNAVAILABLE')
        if attempt is not None and path_check(artifact) != pin:
            raise WCEError('VIDEO_ASSET_CHANGED')
        return {'start': start, **result}

    def _playable(self, attempt, project_id):
        receipt, artifact = self._paths(attempt)
        row = read_optional(receipt, RECEIPT_MAX)
        if row is None or row['request']['project_id'] != project_id or row['state'] != 'ASSET_READY':
            raise WCEError('VIDEO_ASSET_NOT_READY')
        asset = row['asset']
        pin = path_check(artifact)
        identity = (attempt, project_id, pin, asset['sha256'], asset['bytes'])
        if self.playback_pin != identity:
            digest, size = self._asset_digest(artifact, pin)
            if (digest, size) != (asset['sha256'], asset['bytes']) or path_check(artifact) != pin:
                raise WCEError('VIDEO_ASSET_CHANGED')
            self.playback_pin = identity
        return artifact, asset, pin

    def export(self, attempt, project_id, *, directory=None):
        from .own_configuration_export import _directory

        source, asset, pin = self._playable(attempt, project_id)
        filename = self._filename(attempt, asset)
        folder = _directory(Path(directory) if directory is not None else Path.home() / 'Downloads')
        try:
            self._copy_original(source, asset, pin, folder, filename)
        except OSError:
            raise WCEError('VIDEO_EXPORT_UNAVAILABLE') from None
        finally:
            os.close(folder)
        return {'state': 'EXPORTED', 'filename': filename, 'bytes': asset['bytes'], 'sha256': asset['sha256']}

    def _copy_original(self, source, asset, pin, folder, filename, *, before_link=None, source_root=None):
        temporary = '.openahoy-video-' + os.urandom(16).hex()
        created = False
        try:
            try:
                fd = os.open(filename, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=folder)
            except FileNotFoundError:
                fd = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600, dir_fd=folder)
                created = True
                digest = sha256()
                with os.fdopen(fd, 'wb') as out:
                    for block in FileSource(self.root if source_root is None else source_root).iter_html(
                            source.name, expected_state=pin):
                        digest.update(block)
                        out.write(block)
                    out.flush()
                    os.fsync(out.fileno())
                if digest.hexdigest() != asset['sha256']:
                    raise WCEError('VIDEO_ASSET_CHANGED')
                if before_link is not None:
                    before_link()
                try:
                    os.link(temporary, filename, src_dir_fd=folder, dst_dir_fd=folder, follow_symlinks=False)
                except FileExistsError:
                    pass
                os.fsync(folder)
                fd = os.open(filename, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=folder)
            if created:
                try:
                    os.unlink(temporary, dir_fd=folder)
                except OSError:
                    os.close(fd)
                    raise
                created = False
            with os.fdopen(fd, 'rb') as copy:
                info = os.fstat(copy.fileno())
                if (not stat.S_ISREG(info.st_mode) or info.st_uid != os.getuid() or info.st_mode & 0o077
                        or info.st_size != asset['bytes'] or file_digest(copy, 'sha256').hexdigest() != asset['sha256']
                        or self._file_identity(os.fstat(copy.fileno())) != self._file_identity(info)):
                    raise WCEError('VIDEO_EXPORT_CONFLICT')
                return self._file_identity(info)
        finally:
            if created:
                os.unlink(temporary, dir_fd=folder)

    def _key(self, site=None):
        key = self.credential() if site is None else self.minimax_credential(provider=site)
        if key is None:
            raise WCEError('VIDEO_KEY_NOT_CONFIGURED')
        return key

    def _tokenhex_connection(self):
        configured = self.tokenhex_credential()
        if configured is None:
            raise WCEError('VIDEO_TOKENHEX_NOT_CONFIGURED')
        origin, connection, key = configured
        if origin != TOKENHEX_ORIGIN:
            raise WCEError('VIDEO_TOKENHEX_ORIGIN_MISMATCH')
        return connection, key

    def _tokenhex_selection(self, connection):
        row = read_optional(self.root / 'tokenhex-selection.state')
        return row if row is not None and row.get('connection') == connection else {}

    def tokenhex_check(self):
        try:
            connection, key = self._tokenhex_connection()
        except WCEError as error:
            if error.code == 'VIDEO_TOKENHEX_NOT_CONFIGURED':
                return {'state': 'NOT_CONFIGURED', 'models': []}
            raise
        result = self.tokenhex.models(key)
        selection = self._tokenhex_selection(connection)
        selected = selection.get('model')
        if selected in result['models']:
            result.update(selected_model=selected, native_verified=bool(selection.get('verified_attempt')))
        return result

    def tokenhex_select(self, model):
        validate_model(model)
        self._directory()
        with locked(self.root / 'generation.lock'):
            connection, key = self._tokenhex_connection()
            if model not in self.tokenhex.models(key)['models']:
                raise WCEError('VIDEO_TOKENHEX_MODEL_NOT_VISIBLE')
            if self._tokenhex_connection()[0] != connection:
                raise WCEError('VIDEO_TOKENHEX_CONNECTION_CHANGED')
            old = self._tokenhex_selection(connection)
            if old.get('model') != model:
                old = {'connection':connection, 'model':model}
                atomic_write(self.root / 'tokenhex-selection.state', old)
        return {'state':'SELECTED', 'selected_model':model, 'native_verified':bool(old.get('verified_attempt'))}

    def _mark_tokenhex_ready(self, row):
        if row['request'].get('provider') != TOKENHEX_PROVIDER or 'project_video_copy' not in row:
            return
        selection = self._tokenhex_selection(row['tokenhex_connection'])
        if selection.get('model') == row['request']['model'] and not selection.get('verified_attempt'):
            atomic_write(self.root / 'tokenhex-selection.state',
                         dict(selection, verified_attempt=row['generation_attempt_id']))

    def submit(self, attempt, project_id, first, last, prompt, *, model=MODEL, duration=5,
               reference_images=None, workspace=None, tokenhex=False):
        is_minimax = model in MINIMAX_MODELS
        if not is_minimax:
            validate_model(model)
        elif workspace is None or workspace.get('provider_site') not in SITES:
            raise WCEError('VIDEO_MODE_PARAMETERS_INVALID')
        if not is_minimax and workspace is not None and 'provider_site' in workspace:
            raise WCEError('VIDEO_MODE_PARAMETERS_INVALID')
        if tokenhex and (is_minimax or workspace is None or workspace['mode'] not in ('text', 'frames', 'reference')):
            raise WCEError('VIDEO_MODE_PARAMETERS_INVALID')
        provider = TOKENHEX_PROVIDER if tokenhex else None
        receipt, _ = self._paths(attempt)
        if not prompt.strip():
            raise WCEError('VIDEO_FRAMES_OR_PROMPT_INVALID')
        recipe = None
        if workspace is not None:
            recipe = dict({k: v for k, v in workspace.items() if k not in ('source_attempt_id', 'source_sha256')},
                          prompt=prompt)
            if os.path.lexists(receipt):
                old = read_optional(receipt, RECEIPT_MAX)
                if old:
                    if (old['request']['project_id'] != project_id or old['request']['model'] != model
                            or old['request'].get('provider') != provider or old.get('recipe') != recipe
                            or any(old['request'].get(k) != workspace.get(k)
                                   for k in ('source_attempt_id', 'source_sha256'))):
                        raise WCEError('VIDEO_ATTEMPT_CONFLICT')
                    return old
        frame_specs = reference_images if reference_images is not None else (first, last)
        if workspace is not None:
            frame_specs = self.resolve_frames(project_id, workspace['paths'], h3=is_minimax)
        identity = {'project_id': project_id, 'model': model, 'frames': [frame['sha256'] for frame in frame_specs],
                    'prompt_sha256': sha256(prompt.encode()).hexdigest()}
        if tokenhex:
            identity['provider'] = provider
        params = {}
        if workspace is None:
            if reference_images is not None:
                params['mode'] = 'reference'
            if duration != 5:
                params['duration'] = duration
            identity.update(params)
        if workspace is not None:
            params = {k: workspace[k] for k in ('mode', 'duration', 'resolution', 'audio', 'direction',
                                               'provider_site', 'ratio')
                      if k in workspace}
            identity.update(params)
            has_source = {'source_attempt_id', 'source_sha256'} & workspace.keys()
            if is_minimax and (params['mode'] in ('edit', 'extend') or params.get('audio') or 'direction' in params
                          or 'ratio' not in params):
                raise WCEError('VIDEO_MODE_PARAMETERS_INVALID')
            editing = params['mode'] in ('edit', 'extend')
            if ((editing and len(has_source) != 2)
                    or (not editing and (has_source or 'reference_asset' in workspace))):
                raise WCEError('VIDEO_MODE_PARAMETERS_INVALID')
            if 'source_attempt_id' in workspace:
                identity['source_attempt_id'] = workspace['source_attempt_id']
                identity['source_sha256'] = workspace['source_sha256']
        self._directory()
        with locked(self.root / 'generation.lock'):
            old = read_optional(receipt, RECEIPT_MAX)
            if old is not None:
                if old['request'] != identity or (recipe is not None and old.get('recipe') != recipe):
                    raise WCEError('VIDEO_ATTEMPT_CONFLICT')
                return old
            project = next((row for row in self.projects.view()['projects'] if row['id'] == project_id), None)
            if not project:
                raise WCEError('VIDEO_PROJECT_NOT_REGISTERED')
            root = Path(project['root'])
            frames = []
            encoded_size = 0
            for frame in frame_specs:
                mime, data = image(Path(frame['path']), root, frame['sha256'], self.root, h3=is_minimax)
                encoded_size += ((len(data) + 2) // 3) * 4
                if encoded_size >= MAX_REQUEST:
                    raise WCEError('VIDEO_REQUEST_TOO_LARGE')
                frames.append((mime, data))
            site = params.get('provider_site')
            if tokenhex:
                connection, key = self._tokenhex_connection()
                if self._tokenhex_selection(connection).get('model') != model:
                    raise WCEError('VIDEO_TOKENHEX_MODEL_NOT_SELECTED')
                api = self.tokenhex
                if model not in api.models(key)['models']:
                    raise WCEError('VIDEO_TOKENHEX_MODEL_NOT_VISIBLE')
                if self._tokenhex_connection()[0] != connection:
                    raise WCEError('VIDEO_TOKENHEX_CONNECTION_CHANGED')
            else:
                key = self._key(site)
                api = self.api if site is None else self.minimax(site)
            reference = None
            if 'source_attempt_id' in identity:
                source_receipt, original = self._paths(identity['source_attempt_id'])
                source = read_optional(source_receipt, RECEIPT_MAX)
                if (source is None or source['state'] != 'ASSET_READY'
                        or source['request']['model'] in (*MINIMAX_MODELS, RELAY_MODEL) or source['request'].get('provider') == TOKENHEX_PROVIDER
                        or source['request']['project_id'] != project_id
                        or source['asset']['sha256'] != workspace['source_sha256']):
                    raise WCEError('VIDEO_REFERENCE_SOURCE_UNAVAILABLE')
                if self._asset_digest(original, path_check(original)) != (source['asset']['sha256'], source['asset']['bytes']):
                    raise WCEError('VIDEO_ASSET_CHANGED')
                length = source['asset']['seconds']
                if not (4 if params['mode'] == 'edit' else 2) <= length <= 30:
                    raise WCEError('VIDEO_REFERENCE_DURATION_INVALID')
                reference = workspace.get('reference_asset')
                if reference is not None and not re.fullmatch(r'asset://[A-Za-z0-9_-]{1,128}', reference):
                    raise WCEError('VIDEO_REFERENCE_SOURCE_UNAVAILABLE')
                if reference is None:
                    try:
                        remote = self.api.query(key, source['provider_task_id'], model=source['request']['model'])
                        if remote.get('status') != 'succeeded':
                            raise WCEError('VIDEO_REFERENCE_SOURCE_UNAVAILABLE')
                        reference = result_url(remote['content']['video_url'])
                    except (WCEError, KeyError, TypeError):
                        raise WCEError('VIDEO_REFERENCE_SOURCE_UNAVAILABLE') from None
            if is_minimax:
                encoder = v1_body if model in V1_MODELS else h3_body
                body = encoder(prompt, frames, model=model,
                               **{k: params[k] for k in ('mode', 'duration', 'resolution', 'ratio')})
            else:
                body = request_body(prompt, frames, model=model, reference=reference, **params)
            row = {'generation_attempt_id': attempt, 'request': identity, 'state': 'SUBMIT_UNKNOWN',
                   'request_sha256': sha256(body).hexdigest(), 'created_at': int(time.time())}
            info = root.stat(follow_symlinks=False)
            row['project_video_root'] = [info.st_dev, info.st_ino]
            if tokenhex:
                row['tokenhex_connection'] = connection
            if workspace is not None:
                row['recipe'] = recipe
            else:
                row['recipe'] = {'mode': params.get('mode', 'frames'), 'duration': duration, 'resolution': '720p',
                                 'audio': False, 'prompt': prompt,
                                 'paths': [str(Path(frame['path']).relative_to(root)) for frame in frame_specs]}
            return self._dispatch(receipt, row, api, key, body)

    def _dispatch(self, receipt, row, api, key, body):
        atomic_write(receipt, row, maximum=RECEIPT_MAX)
        try:
            task = api.submit(key, body)
        except RelaySubmitError as error:
            if error.rejected:
                row['state'] = 'SUBMIT_REJECTED'
            row['submit_diagnostic'] = error.diagnostic
            atomic_write(receipt, row, maximum=RECEIPT_MAX)
            return row
        except WCEError as error:
            if error.code == 'VIDEO_SUBMIT_REJECTED':
                row['state'] = 'SUBMIT_REJECTED'
                if isinstance(error, (ArkSubmitRejected, MiniMaxRejected)):
                    row['rejection'] = error.diagnostic
                atomic_write(receipt, row, maximum=RECEIPT_MAX)
            return row
        row.update(provider_task_id=task, state='SUBMITTED')
        atomic_write(receipt, row, maximum=RECEIPT_MAX)
        return row

    def submit_subject(self, attempt, project_id, site, prompt, image_url):
        if site not in SITES:
            raise WCEError('VIDEO_MODE_PARAMETERS_INVALID')
        body = subject_body(prompt, image_url)
        request_hash = sha256(body).hexdigest()
        identity = {'project_id': project_id, 'model': SUBJECT_MODEL, 'mode': 'subject', 'provider_site': site}
        receipt, _ = self._paths(attempt)
        self._directory()
        with locked(self.root / 'generation.lock'):
            previous = read_optional(receipt, RECEIPT_MAX)
            if previous is not None:
                if previous['request'] != identity or previous['request_sha256'] != request_hash:
                    raise WCEError('VIDEO_ATTEMPT_CONFLICT')
                return previous
            project = next((row for row in self.projects.view()['projects'] if row['id'] == project_id), None)
            if project is None:
                raise WCEError('VIDEO_PROJECT_NOT_REGISTERED')
            info = Path(project['root']).stat(follow_symlinks=False)
            row = {'generation_attempt_id': attempt, 'state': 'SUBMIT_UNKNOWN', 'request': identity,
                   'request_sha256': request_hash, 'created_at': int(time.time()),
                   'project_video_root': [info.st_dev, info.st_ino]}
            return self._dispatch(receipt, row, self.minimax(site), self._key(site), body)

    def submit_relay(self, attempt, project_id, inputs):
        receipt, _ = self._paths(attempt)
        body = workflow_body(inputs)
        request_hash = sha256(body).hexdigest()
        identity = {'project_id': project_id, 'model': RELAY_MODEL, 'mode': 'workflow'}
        if 'duration' in inputs:
            identity['duration'] = inputs['duration']
        self._directory()
        with locked(self.root / 'generation.lock'):
            old = read_optional(receipt, RECEIPT_MAX)
            if old is not None:
                if old['request'] != identity or old['request_sha256'] != request_hash:
                    raise WCEError('VIDEO_ATTEMPT_CONFLICT')
                return old
            project = next((r for r in self.projects.view()['projects'] if r['id'] == project_id), None)
            if project is None:
                raise WCEError('VIDEO_PROJECT_NOT_REGISTERED')
            root = Path(project['root'])
            origin, connection, key = self._relay_connection()
            info = root.stat(follow_symlinks=False)
            row = {'generation_attempt_id': attempt, 'state': 'SUBMIT_UNKNOWN', 'request': identity,
                   'relay_connection': connection, 'request_sha256': request_hash,
                   'created_at': int(time.time()), 'project_video_root': [info.st_dev, info.st_ino]}
            return self._dispatch(receipt, row, self.relay(origin), key, body)

    def _relay_connection(self):
        configured = self.relay_credential()
        if configured is None:
            raise WCEError('VIDEO_RELAY_NOT_CONFIGURED')
        return configured

    def _query_task(self, row, site):
        request = row['request']
        if request['model'] == RELAY_MODEL:
            origin, connection, key = self._relay_connection()
            if connection != row.get('relay_connection'):
                raise WCEError('VIDEO_RELAY_CONNECTION_CHANGED')
            api = self.relay(origin)
        elif request.get('provider') == TOKENHEX_PROVIDER:
            connection, key = self._tokenhex_connection()
            if connection != row.get('tokenhex_connection'):
                raise WCEError('VIDEO_TOKENHEX_CONNECTION_CHANGED')
            api = self.tokenhex
        else:
            api = self.api if site is None else self.minimax(site)
            key = self._key(site)
        return api, api.query(key, row['provider_task_id'], model=request['model'])

    @staticmethod
    def _remote_state(value):
        remote = value.get('status')
        states = {'queued': 'QUEUED', 'running': 'RUNNING', 'failed': 'FAILED', 'expired': 'EXPIRED',
                  'cancelled': 'CANCELLED', 'succeeded': 'SAVE_PENDING'}
        return states.get(remote) if isinstance(remote, str) else None

    def monitor_task(self, attempt, project_id):
        receipt, _ = self._paths(attempt)
        row = read_optional(receipt, RECEIPT_MAX)
        if not row or row['request']['project_id'] != project_id or not row.get('provider_task_id'):
            raise WCEError('VIDEO_TASK_STATUS_UNKNOWN')
        is_minimax = row['request']['model'] in MINIMAX_MODELS
        site = row['request'].get('provider_site') if is_minimax else None
        if is_minimax and site not in SITES:
            raise WCEError('VIDEO_MODE_PARAMETERS_INVALID')
        _, value = self._query_task(row, site)
        state = self._remote_state(value)
        if state is None:
            raise WCEError('VIDEO_TASK_STATUS_UNKNOWN')
        usage = h3_usage(value.get('usage')) if is_minimax else provider_usage(value.get('usage'))
        return {'state': state, 'usage': usage, 'read_at': time.time()}

    def status(self, attempt, project_id, poll=False):
        receipt, artifact = self._paths(attempt)
        if not os.path.lexists(self.root):
            return {'state': 'NOT_FOUND'}
        path_check(self.root, True)
        with locked(self.root / 'generation.lock'):
            row = read_optional(receipt, RECEIPT_MAX)
            if row is None or row['request']['project_id'] != project_id:
                return {'state': 'NOT_FOUND'}
            if row['state'] == 'ASSET_READY':
                asset = row['asset']
                if not os.path.lexists(artifact) or self._asset(artifact, request=row['request']) != asset:
                    raise WCEError('VIDEO_ASSET_CHANGED')
                if poll:
                    if 'project_video_copy' not in row:
                        self._save_project_copy(row, receipt)
                    self._mark_tokenhex_ready(row)
                return row
            if row['state'] == 'SAVE_PENDING' and os.path.lexists(artifact):
                asset = self._asset(artifact, request=row['request'])
                if row.get('download_sha256') != asset['sha256']:
                    raise WCEError('VIDEO_ASSET_CONFLICT')
                row.update(state='ASSET_READY', asset=asset)
                atomic_write(receipt, row, maximum=RECEIPT_MAX)
                self._save_project_copy(row, receipt)
                self._mark_tokenhex_ready(row)
                return row
            recover_failure = row['state'] == 'FAILED' and 'failure' not in row
            if not poll or (row['state'] in {'SUBMIT_UNKNOWN', 'SUBMIT_REJECTED', 'FAILED', 'EXPIRED', 'CANCELLED'}
                            and not recover_failure):
                return row
            request = row['request']
            is_minimax = request['model'] in MINIMAX_MODELS
            site = request.get('provider_site') if is_minimax else None
            if is_minimax and site not in SITES:
                raise WCEError('VIDEO_MODE_PARAMETERS_INVALID')
            is_relay = request['model'] == RELAY_MODEL
            is_tokenhex = request.get('provider') == TOKENHEX_PROVIDER
            try:
                api, value = self._query_task(row, site)
            except WCEError as error:
                return dict(row, query_error=error.code)
            remote = value.get('status')
            if recover_failure and remote != 'failed':
                return dict(row, query_error='VIDEO_TASK_STATUS_UNKNOWN')
            state = self._remote_state(value)
            if state is None:
                return dict(row, query_error='VIDEO_TASK_STATUS_UNKNOWN')
            row['state'] = state
            if remote == 'failed':
                if is_minimax:
                    row['failure'] = {'provider': 'minimax'}
                elif is_relay:
                    row['failure'] = {'provider': 'relay'}
                elif is_tokenhex:
                    row['failure'] = {'provider': TOKENHEX_PROVIDER}
                    if code := ark_error_code(value):
                        row['failure']['ark_error_code'] = code
                elif code := ark_error_code(value):
                    row['failure'] = {'ark_error_code': code}
            parse_usage = h3_usage if is_minimax else provider_usage
            usage = parse_usage(value.get('usage'))
            if usage:
                row['usage'] = parse_usage(row.get('usage')) | usage
                if 'total_tokens' in usage:
                    row['total_tokens'] = usage['total_tokens']
            atomic_write(receipt, row, maximum=RECEIPT_MAX)
            if remote == 'succeeded':
                try:
                    content = value.get('content')
                    url = content.get('video_url') if type(content) is dict else None
                    if request['model'] in H3_MODELS and value.get('resolution') != request['resolution']:
                        raise WCEError('VIDEO_RESULT_INVALID')
                    asset = self._save(artifact, url, receipt, row, api=api)
                    row.update(state='ASSET_READY', asset=asset)
                except WCEError as error:
                    return dict(row, download_error=error.code)
                atomic_write(receipt, row, maximum=RECEIPT_MAX)
                self._save_project_copy(row, receipt)
                self._mark_tokenhex_ready(row)
            return row

    def _save(self, artifact, url, receipt, row, *, api):
        fd, name = tempfile.mkstemp(prefix='.video-', suffix='.mp4', dir=self.root)
        temporary = Path(name)
        try:
            with os.fdopen(fd, 'wb') as out:
                api.download(url, out)
                out.flush()
                os.fsync(out.fileno())
            ready = self._asset(temporary, request=row['request'])
            row['download_sha256'] = ready['sha256']
            atomic_write(receipt, row, maximum=RECEIPT_MAX)
            if os.path.lexists(artifact):
                raise WCEError('VIDEO_ASSET_CONFLICT')
            temporary.rename(artifact)
            directory = os.open(self.root, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
            try:
                os.fsync(directory)
            finally:
                os.close(directory)
            return dict(ready, path=str(artifact))
        except OSError:
            raise WCEError('VIDEO_ASSET_SAVE_FAILED') from None
        finally:
            temporary.unlink(missing_ok=True)

    def _asset(self, path, *, request=None):
        pin = path_check(path)
        digest, size = self._asset_digest(path, pin)
        facts = self.inspect(path)
        request = request or {}
        model = request.get('model')
        if model not in (*MINIMAX_MODELS, RELAY_MODEL) and not request.get('audio', False) and facts['audio_tracks'] != 0:
            raise WCEError('VIDEO_RESULT_INVALID')
        duration = request.get('duration', 5)
        if model not in (RELAY_MODEL, SUBJECT_MODEL) and request.get('mode') != 'extend' and duration != -1:
            delta = facts['seconds'] - duration
            # Ark reports whole seconds rounded down while MP4 timing retains fractional seconds.
            if request.get('model') == MODEL:
                above = delta >= 1
            elif request.get('model') in MINIMAX_MODELS:
                # H3 can return a playable MP4 slightly longer than its billed duration.
                above = delta > 0.5
            else:
                above = delta > 0.25
            if delta < -0.25 or above:
                raise WCEError('VIDEO_RESULT_INVALID')
        if path_check(path) != pin:
            raise WCEError('VIDEO_ASSET_CHANGED')
        prefix = ('tokenhex-' if request.get('provider') == TOKENHEX_PROVIDER else
                  'minimax-' if model in MINIMAX_MODELS else 'relay-' if model == RELAY_MODEL else 'ark-')
        return dict(facts, asset_id=prefix + digest, sha256=digest, bytes=size, path=str(path))

    def _asset_digest(self, path, pin, source_root=None):
        digest = sha256()
        size = 0
        for chunk in FileSource(source_root if source_root is not None else self.root).iter_html(
                path.name, expected_state=pin):
            digest.update(chunk)
            size += len(chunk)
            if size > MAX_RESULT:
                raise WCEError('VIDEO_RESULT_TOO_LARGE')
        return digest.hexdigest(), size
