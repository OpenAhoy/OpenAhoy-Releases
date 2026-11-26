"""Archive a Suno-authorized file without exposing the temporary provider URL."""
from hashlib import sha256
from http.client import HTTPException
import os
from pathlib import Path
from time import monotonic
from urllib.error import HTTPError
from urllib.parse import urlsplit
from urllib.request import ProxyHandler, Request, build_opener
from uuid import uuid4

from .audio_jobs import AUDIO_DIR
from .bounded_file import FileSource
from .contracts import WCEError
from .http_transport import NoRedirect
from .own_connection_policy import locked
from .service import digest
from .suno_panel import HTTPS_AUDIO_HOST, HANDLE, UUID, codex_client, profile, url_from

FORMATS = {'mp3': {'audio/mpeg', 'audio/mp3'}, 'wav': {'audio/wav', 'audio/x-wav', 'audio/wave'}}
MAX_BYTES = 256 * 1024 * 1024
BYTE_CHUNK = 64 * 1024


def capture(url, output, audio_format):
    opener = build_opener(ProxyHandler({}), NoRedirect())
    types = FORMATS[audio_format] | {'application/octet-stream'}
    request = Request(url, headers={'Accept': ', '.join(sorted(types)), 'Accept-Encoding': 'identity'})
    deadline = monotonic() + 70
    measured = sha256()
    size = 0
    try:
        with opener.open(request, timeout=15) as response:
            if (response.status != 200 or response.headers.get_content_type() not in types or
                    response.headers.get('Content-Encoding', 'identity').lower() != 'identity'):
                raise WCEError('SUNO_DOWNLOAD_CONTENT_INVALID')
            length = response.headers.get('Content-Length')
            if length is not None and (not length.isascii() or not length.isdecimal() or
                                       len(length) > 10 or not 0 < int(length) <= MAX_BYTES):
                raise WCEError('SUNO_DOWNLOAD_LENGTH_INVALID')
            while monotonic() < deadline:
                chunk = response.read(BYTE_CHUNK)
                if not chunk:
                    break
                size += len(chunk)
                if size > MAX_BYTES:
                    raise WCEError('SUNO_DOWNLOAD_LENGTH_INVALID')
                measured.update(chunk)
                output.write(chunk)
            else:
                raise WCEError('SUNO_DOWNLOAD_TIMEOUT')
            if not size or (length is not None and size != int(length)):
                raise WCEError('SUNO_DOWNLOAD_LENGTH_INVALID')
    except HTTPError as error:
        error.close()
        raise WCEError('SUNO_DOWNLOAD_SOURCE_UNAVAILABLE') from None
    except (OSError, HTTPException, ValueError):
        raise WCEError('SUNO_DOWNLOAD_SOURCE_UNAVAILABLE') from None
    return measured.hexdigest()


def source_url(result, audio_format):
    url = url_from(result.get('url'), {HTTPS_AUDIO_HOST})
    if (result.get('status') not in ('ok', 'ready') or result.get('format') != audio_format or
            not url or not urlsplit(url).path.startswith('/studio/uploads/')):
        raise WCEError('SUNO_DOWNLOAD_SOURCE_UNAVAILABLE')
    return url


def download_into_project(audio, project, clip, title, attempt, audio_format, url):
    source = FileSource(project['root'])
    directory = audio.videos._project_video_folder(project, list(source.root_identity),
                                                  create=True, components=AUDIO_DIR)
    stage = f'.suno-intake-{uuid4().hex}.{audio_format}'
    try:
        fd = os.open(stage, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600, dir_fd=directory)
        try:
            with os.fdopen(fd, 'wb') as output:
                checksum = capture(url, output, audio_format)
            item = {'path': Path(*AUDIO_DIR, stage).as_posix(), 'sha256': checksum}
            audio.ingest(attempt, project['id'], title, item, 'suno', clip)
        finally:
            os.unlink(stage, dir_fd=directory)
    finally:
        os.close(directory)


def fetch_and_import(audio, project, clip, expected_handle, title, format='mp3'):
    """Use existing official OAuth with no download confirmation and no URL receipt."""
    if (type(clip) is not str or UUID.fullmatch(clip) is None or
            type(expected_handle) is not str or HANDLE.fullmatch(expected_handle) is None or
            type(format) is not str or format not in FORMATS):
        raise WCEError('SUNO_DOWNLOAD_TARGET_INVALID')
    registered = audio.project(project)
    attempt = 'suno-' + digest([project, clip, expected_handle, format])[:40]
    try:
        audio.init()
        with locked(audio.root / 'suno-intake.lock'):
            try:
                previous = audio.read(attempt, project)
            except WCEError as error:
                if error.code != 'AUDIO_ASSET_NOT_READY':
                    raise
            else:
                if previous.get('provider') != 'suno' or previous.get('provider_id') != clip:
                    raise WCEError('SUNO_ARCHIVE_IDENTITY_MISMATCH')
                source, _ = audio.file(previous)
                audio.pin(source, previous)
                return {'state': 'ready', 'attempt': attempt}

            with codex_client() as tool:
                if profile(tool)['handle'] != expected_handle:
                    raise WCEError('SUNO_CODEX_ACCOUNT_CHANGED')
                result = tool('audio-download', {'id': clip, 'format': format})
            if result.get('status') in ('processing', 'requires_credit'):
                return {'state': result['status']}
            url = source_url(result, format)
            download_into_project(audio, registered, clip, title, attempt, format, url)
            return {'state': 'ready', 'attempt': attempt}
    except WCEError as error:
        return {'state': 'unavailable', 'code': error.code}
    except OSError:
        return {'state': 'unavailable', 'code': 'SUNO_PROJECT_DOWNLOAD_FAILED'}
