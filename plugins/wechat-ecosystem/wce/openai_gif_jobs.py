"""One provider submission, followed by local verification and project storage."""
from base64 import b64encode
from contextlib import ExitStack
from hashlib import sha256
import os
from pathlib import Path
from secrets import token_hex
from threading import Thread
import time

from .bounded_file import FileSource
from .contracts import WCEError
from .openai_gif_api import EditFailure, MAX_INPUT, MODEL, OpenAIImages
from .openai_gif_inspect import gif_facts, reference_mime
from .openai_gif_keychain import load
from .own_bootstrap_security import path_check
from .own_configuration_export import _directory
from .own_connection_policy import atomic_write, locked, read_optional
from .own_connection_registry import mkdir
from .service import canonical
from .video_jobs import ATTEMPT, PLAYBACK_CHUNK
from .video_seedance import MAX_RESULT

PROJECT_GIFS = ('assets', 'openahoy', 'gifs')


class GifJobs:
    def __init__(self, videos, *, api=None, credential=load):
        self.videos = videos
        self.projects = videos.projects
        self.root = self.projects.root / 'openai-gif'
        self.api = api if api is not None else OpenAIImages()
        self.credential = credential
        self.verified = None

    def paths(self, attempt):
        if type(attempt) is not str or not ATTEMPT.fullmatch(attempt):
            raise WCEError('INVALID_TOOL_ARGUMENTS')
        return tuple(self.root / (attempt + ext) for ext in ('.json', '.gif', '.lock'))

    def project(self, project_id):
        project = next((row for row in self.projects.view()['projects'] if row['id'] == project_id), None)
        if project is None:
            raise WCEError('GIF_PROJECT_NOT_REGISTERED')
        return project

    def prepare_directory(self):
        if not os.path.lexists(self.root.parent):
            try:
                os.mkdir(self.root.parent, 0o700)
            except FileExistsError:
                pass
        path_check(self.root.parent, True)
        if not os.path.lexists(self.root):
            try:
                mkdir(self.root.parent, self.root.name)
            except FileExistsError:
                pass
        path_check(self.root, True)

    def source(self, project, selected):
        try:
            source = FileSource(project['root'])
            raw = bytearray()
            for block in source.iter_html(selected['path']):
                if len(raw) + len(block) > MAX_INPUT:
                    raise WCEError('GIF_SOURCE_INVALID')
                raw.extend(block)
        except WCEError as error:
            if error.code == 'LOCAL_FILE_CHANGED':
                raise WCEError('GIF_SOURCE_CHANGED') from None
            raise WCEError('GIF_SOURCE_INVALID') from None
        if sha256(raw).hexdigest() != selected['sha256']:
            raise WCEError('GIF_SOURCE_CHANGED')
        image = bytes(raw)
        return reference_mime(image), image, list(source.root_identity)

    def submit(self, attempt, project_id, selected, prompt):
        if not prompt.strip():
            raise WCEError('INVALID_TOOL_ARGUMENTS')
        receipt, artifact, lock = self.paths(attempt)
        request_hash = sha256(canonical({'project': project_id, 'source': selected, 'prompt': prompt}).encode()).hexdigest()
        self.prepare_directory()
        claim = receipt.with_suffix('.claim')
        with ExitStack() as owner:
            try:
                owner.enter_context(locked(lock, nonblocking=True))
            except WCEError as error:
                if error.code != 'CONNECTION_BUSY':
                    raise
                old = read_optional(claim)
                if old is None:
                    raise WCEError('GIF_ATTEMPT_BUSY') from None
                self.same_request(old, project_id, request_hash)
                return self.project_row(old, active=True)
            old = read_optional(receipt)
            if old is not None:
                self.same_request(old, project_id, request_hash)
                if old['state'] in ('RESULT_RECEIVED', 'SAVE_PENDING') and os.path.lexists(artifact):
                    self.finish_copy(old, receipt, artifact)
                return self.project_row(old)
            if os.path.lexists(artifact):
                raise WCEError('GIF_ARTIFACT_CONFLICT')
            project = self.project(project_id)
            mime, raw, root_id = self.source(project, selected)
            key = self.credential()
            if key is None:
                raise WCEError('GIF_KEY_NOT_CONFIGURED')
            row = {'schema': 1, 'generation_attempt_id': attempt, 'project_id': project_id, 'model': MODEL,
                   'state': 'SUBMIT_UNKNOWN', 'request_sha256': request_hash,
                   'created_at': int(time.time()), 'root_identity': root_id}
            prior = read_optional(claim)
            if prior is None:
                atomic_write(claim, row)
            else:
                self.same_request(prior, project_id, request_hash)
            atomic_write(receipt, row)
            lease = owner.pop_all()
            try:
                worker = Thread(target=self.generate, args=(lease, row, receipt, artifact, key, prompt, mime, raw),
                                name='OpenAhoy GIF generation', daemon=False)
                worker.start()
            except RuntimeError:
                with lease:
                    row.update(state='NOT_SENT', diagnostic={'code': 'GIF_LOCAL_FAILURE'})
                    atomic_write(receipt, row)
                return self.project_row(row)
            return {'state': 'PROCESSING', 'generation_attempt_id': attempt, 'project_id': project_id, 'model': MODEL}

    @staticmethod
    def same_request(row, project_id, request_hash):
        if row['project_id'] != project_id or row['request_sha256'] != request_hash:
            raise WCEError('GIF_ATTEMPT_CONFLICT')

    def generate(self, lease, row, receipt, artifact, key, prompt, mime, raw):
        with lease:
            def noticed(identifier):
                row['provider_request_id'] = identifier
                atomic_write(receipt, row)
            try:
                result = self.api.edit(key, prompt, mime, raw, noticed)
                facts = gif_facts(result)
            except EditFailure as error:
                if error.rejected:
                    row['state'] = 'SUBMIT_REJECTED'
                row['diagnostic'] = error.diagnostic
            except Exception as error:
                safe = error.code if isinstance(error, WCEError) and error.code == 'GIF_RESULT_INVALID' else 'GIF_LOCAL_FAILURE'
                row['diagnostic'] = {'code': safe}
            else:
                row.update(state='RESULT_RECEIVED', asset=dict(facts, sha256=sha256(result).hexdigest(), bytes=len(result)))
                try:
                    atomic_write(receipt, row)
                    self.stage(artifact, result)
                    self.finish_copy(row, receipt, artifact)
                    return
                except (OSError, WCEError):
                    row['diagnostic'] = {'code': 'GIF_FINALIZE_PENDING'}
            try:
                atomic_write(receipt, row)
            except (OSError, WCEError):
                pass  # The previous receipt or staged original remains authoritative.

    def stage(self, artifact, raw):
        folder = _directory(self.root)
        temporary = '.gif-' + token_hex(16)
        try:
            fd = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600, dir_fd=folder)
            try:
                with os.fdopen(fd, 'wb') as stream:
                    stream.write(raw)
                    stream.flush()
                    os.fsync(stream.fileno())
                os.link(temporary, artifact.name, src_dir_fd=folder, dst_dir_fd=folder, follow_symlinks=False)
            finally:
                os.unlink(temporary, dir_fd=folder)
            os.fsync(folder)
        finally:
            os.close(folder)

    def pin_asset(self, artifact, asset):
        pin = path_check(artifact)
        identity = (artifact, pin, asset['sha256'])
        if pin[2] != asset['bytes'] or pin[2] > MAX_RESULT:
            raise WCEError('GIF_ASSET_CHANGED')
        if self.verified != identity:
            digest = sha256()
            for block in FileSource(self.root).iter_html(artifact.name, expected_state=pin):
                digest.update(block)
            if digest.hexdigest() != asset['sha256'] or path_check(artifact) != pin:
                raise WCEError('GIF_ASSET_CHANGED')
            self.verified = identity
        return pin

    def finish_copy(self, row, receipt, artifact):
        row['state'] = 'SAVE_PENDING'
        atomic_write(receipt, row)
        try:
            source = self.pin_asset(artifact, row['asset'])
            project = self.project(row['project_id'])
            filename = self.filename(row)
            def open_folder(create=False):
                return self.videos._project_video_folder(project, row['root_identity'],
                                                         create=create, components=PROJECT_GIFS)
            folder = open_folder(True)
            try:
                def verify_folder():
                    live = open_folder()
                    try:
                        if not os.path.samestat(os.fstat(live), os.fstat(folder)):
                            raise WCEError('GIF_PROJECT_CHANGED')
                    finally:
                        os.close(live)
                copy = self.videos._copy_original(artifact, row['asset'], source, folder, filename,
                                                 before_link=verify_folder, source_root=self.root)
                verify_folder()
                if copy != self.videos._file_identity(os.stat(filename, dir_fd=folder, follow_symlinks=False)):
                    raise WCEError('GIF_PROJECT_CHANGED')
            finally:
                os.close(folder)
        except (OSError, WCEError):
            row['diagnostic'] = {'code': 'GIF_FINALIZE_PENDING'}
        else:
            row.update(state='ASSET_READY', project_copy=copy)
            row.pop('diagnostic', None)
        atomic_write(receipt, row)

    @staticmethod
    def filename(row):
        return f'OpenAhoy-{row["generation_attempt_id"]}-{row["asset"]["sha256"][:12]}.gif'

    def project_row(self, row, *, active=False):
        result = {k: row[k] for k in ('generation_attempt_id', 'project_id', 'state', 'model', 'created_at',
                                      'provider_request_id', 'diagnostic', 'asset') if k in row}
        if row['state'] in ('SUBMIT_UNKNOWN', 'RESULT_RECEIVED', 'SAVE_PENDING') and active:
            result['state'] = 'PROCESSING'
        if row['state'] == 'ASSET_READY':
            project = self.project(row['project_id'])
            name = self.filename(row)
            relative = Path(*PROJECT_GIFS, name)
            try:
                folder = self.videos._project_video_folder(project, row['root_identity'], components=PROJECT_GIFS)
                try:
                    info = os.stat(name, dir_fd=folder, follow_symlinks=False)
                    if self.videos._file_identity(info) != row['project_copy']:
                        raise WCEError('GIF_PROJECT_CHANGED')
                finally:
                    os.close(folder)
            except (OSError, WCEError):
                result['project_file'] = 'UNAVAILABLE'
            else:
                result.update(project_file='SAVED', path=str(Path(project['root']) / relative), filename=name)
        return result

    def status(self, attempt, project_id):
        receipt, artifact, lock = self.paths(attempt)
        if not os.path.lexists(lock):
            return {'state': 'NOT_FOUND'}
        try:
            with locked(lock, existing=True, readonly=True, shared=True, nonblocking=True):
                row = self.read(receipt, project_id)
                if row is None:
                    return {'state': 'NOT_FOUND'}
                if row['state'] == 'RESULT_RECEIVED' and os.path.lexists(artifact):
                    row['state'] = 'SAVE_PENDING'
        except WCEError as error:
            if error.code != 'CONNECTION_BUSY':
                raise
            row = self.read(receipt.with_suffix('.claim'), project_id)
            return self.project_row(row, active=True) if row else {'state': 'NOT_FOUND'}
        return self.project_row(row)

    def read(self, receipt, project_id):
        if not os.path.lexists(self.root):
            return None
        path_check(self.root, True)
        row = read_optional(receipt)
        return row if row is not None and row['project_id'] == project_id else None

    def history(self, project_id):
        if not os.path.lexists(self.root):
            return []
        path_check(self.root, True)
        results = []
        for receipt in self.root.glob('*.json'):
            if not ATTEMPT.fullmatch(receipt.stem):
                continue
            row = self.status(receipt.stem, project_id)
            if row['state'] != 'NOT_FOUND':
                results.append(row)
        return sorted(results, key=lambda row: (row['created_at'], row['generation_attempt_id']), reverse=True)

    def available(self, attempt, project_id):
        receipt, artifact, _ = self.paths(attempt)
        row = self.read(receipt, project_id)
        if row is None or row['state'] != 'ASSET_READY':
            raise WCEError('GIF_ASSET_NOT_READY')
        return row, artifact, self.pin_asset(artifact, row['asset'])

    def chunk(self, attempt, project_id, offset):
        row, artifact, pin = self.available(attempt, project_id)
        size = row['asset']['bytes']
        if not 0 <= offset < size:
            raise WCEError('GIF_ASSET_OFFSET_INVALID')
        end = min(size, offset + PLAYBACK_CHUNK)
        data = bytearray()
        # Exhaust the iterator so that its post-read pin checks always run.
        for block in FileSource(self.root).iter_html(artifact.name, expected_state=pin, offset=offset, length=end-offset):
            data.extend(block)
        if len(data) != end - offset:
            raise WCEError('GIF_ASSET_CHANGED')
        return {'offset': offset, 'next': end, 'total': size, 'data': b64encode(data).decode()}

    def export(self, attempt, project_id, directory=None):
        row, artifact, pin = self.available(attempt, project_id)
        name = self.filename(row)
        folder = _directory(Path(directory) if directory is not None else Path.home() / 'Downloads')
        try:
            self.videos._copy_original(artifact, row['asset'], pin, folder, name, source_root=self.root)
        except (OSError, WCEError):
            raise WCEError('GIF_EXPORT_UNAVAILABLE') from None
        finally:
            os.close(folder)
        return {'state': 'EXPORTED', 'filename': name, 'bytes': row['asset']['bytes'], 'sha256': row['asset']['sha256']}
