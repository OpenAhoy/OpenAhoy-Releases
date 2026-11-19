"""Verify project media and preflight existing vendor encoders without submitting."""
from base64 import b64decode, b64encode
from contextlib import ExitStack
import ctypes
from functools import lru_cache
from hashlib import sha256
import os
import stat
from pathlib import Path
import subprocess
import tempfile

from .bounded_file import FileSource, file_state, identity
from .contracts import WCEError
from .own_bootstrap_security import path_check
from .own_connection_policy import locked
from .own_connection_registry import mkdir
from .project_context import text as project_text
from .video_director import ROOT_NAME, require
from .video_jobs import FRAME_LIMIT, image, media_facts, probe
from .video_keychain import configured_item, status
from .video_minimax import SITES, V1_MODELS, h3_body, subject_body, v1_body
from .video_engine_catalog import CHANNELS, REFERENCE, mode_profiles, validate_config
from .video_relay import RELAY_MODEL, workflow_body
from .video_relay_keychain import RelayKeychain
from .video_provider_ui import directory as provider_directory
from .video_seedance import ARK_MODELS, request_body
from .video_tokenhex import TokenHexKeychain

IMAGE_ROLES = ('composition', 'first', 'last', 'subject', 'environment', 'reference')
CATALOG = Path(__file__).resolve().parents[1] / 'skills/video-director/references/SHOT_CARDS.json'
IMAGE_CHUNK = 256 * 1024
IMAGE_SUFFIX = {'public.png': 'png', 'public.jpeg': 'jpg'}


def local_file(root, spec):
    relative = project_text(spec['path'])
    parts = relative.split('/')
    if len(parts) == 3 and parts[:2] == [ROOT_NAME, 'images']:
        require(parts[2] in {spec['sha256'] + '.' + ext for ext in IMAGE_SUFFIX.values()},
                'DIRECTOR_ASSET_OUTSIDE_PROJECT')
        path_check(root / ROOT_NAME / 'images', True)
        path_check(root / relative)
        return root / relative
    require('\\' not in relative and ':' not in relative and
            not any(part in ('', '.', '..', ROOT_NAME, '.git') for part in parts),
            'DIRECTOR_ASSET_OUTSIDE_PROJECT')
    return root / relative


def import_image_chunk(director, args):
    """The app sends one user-selected image. Publish only the checked original."""
    from .video_director import lookup

    project = args['project_id']
    root, pin = director.project(project)
    location = director.storage(root, pin)
    require(location.is_dir(), 'DIRECTOR_WORK_NOT_FOUND')
    with locked(location / 'writer.lock'), ExitStack() as opened_files:
        state = director.load(project, location)
        lookup(state['works'], args['work_id'], 'DIRECTOR_WORK_NOT_FOUND')
        require(director.project(project) == (root, pin), 'DIRECTOR_PROJECT_CHANGED')
        image_root = location / 'images'
        if not os.path.lexists(image_root):
            mkdir(location, 'images')
        directory_pin = path_check(image_root, True)
        directory = os.open(image_root, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
        opened_files.callback(os.close, directory)
        require(identity(os.fstat(directory)) == directory_pin, 'DIRECTOR_PROJECT_CHANGED')
        digest, total, offset = args['sha256'], args['total'], args['offset']
        try:
            data = b64decode(args['data'], validate=True)
        except ValueError:
            raise WCEError('DIRECTOR_IMAGE_IMPORT_INVALID') from None
        require(0 < len(data) <= IMAGE_CHUNK and offset + len(data) <= total < FRAME_LIMIT,
                'DIRECTOR_IMAGE_IMPORT_INVALID')

        def spec(path):
            return {'state': 'IMPORTED', 'file': {'project_id': project,
                    'path': path.relative_to(root).as_posix(), 'sha256': digest}}

        for suffix in IMAGE_SUFFIX.values():
            final = image_root / (digest + '.' + suffix)
            if os.path.lexists(final):
                final_pin = path_check(final)
                require(final_pin[2] == total, 'DIRECTOR_ASSET_CHANGED')
                original = b''.join(FileSource(image_root).iter_html(final.name, expected_state=final_pin))
                require(len(original) == total and sha256(original).hexdigest() == digest
                        and original[offset:offset+len(data)] == data
                        and path_check(image_root, True) == directory_pin,
                        'DIRECTOR_ASSET_CHANGED')
                os.fsync(directory)
                return spec(final)

        temporary = image_root / ('.' + digest + '.part')
        existing = path_check(temporary) if os.path.lexists(temporary) else None
        flags = os.O_RDWR | os.O_NOFOLLOW
        if existing is None:
            require(offset == 0, 'DIRECTOR_IMAGE_IMPORT_OFFSET')
            flags |= os.O_CREAT | os.O_EXCL
        fd = os.open(temporary.name, flags, 0o600, dir_fd=directory)
        try:
            opened = os.fstat(fd)
            require(stat.S_ISREG(opened.st_mode) and stat.S_IMODE(opened.st_mode) == 0o600
                    and opened.st_uid == os.getuid() and opened.st_nlink == 1
                    and (existing is None or existing == file_state(opened))
                    and path_check(image_root, True) == directory_pin,
                    'DIRECTOR_ASSET_CHANGED')
            size = opened.st_size
            require(offset <= size <= total, 'DIRECTOR_IMAGE_IMPORT_OFFSET')
            overlap = min(size-offset, len(data))
            require(os.pread(fd, overlap, offset) == data[:overlap], 'DIRECTOR_IMAGE_IMPORT_CONFLICT')
            if offset+len(data) > size:
                os.lseek(fd, size, os.SEEK_SET)
                with os.fdopen(fd, 'wb', closefd=False) as output:
                    output.write(data[overlap:])
                    output.flush()
                    os.fsync(fd)
                size = offset + len(data)
            staged = file_state(os.fstat(fd))
            require(path_check(temporary) == staged, 'DIRECTOR_ASSET_CHANGED')
        finally:
            os.close(fd)
        if size < total:
            return {'state': 'RECEIVING', 'received': size}
        original = b''.join(FileSource(image_root).iter_html(temporary.name, expected_state=staged))
        try:
            require(len(original) == total and sha256(original).hexdigest() == digest, 'DIRECTOR_ASSET_CHANGED')
            with tempfile.NamedTemporaryFile(prefix='.director-image-') as check:
                check.write(original)
                check.flush()
                facts = probe('image', check.name, error='DIRECTOR_IMAGE_IMPORT_INVALID')
            suffix = IMAGE_SUFFIX.get(facts.get('type'))
            require(suffix, 'DIRECTOR_IMAGE_IMPORT_INVALID')
        except WCEError:
            if path_check(temporary) == staged:
                os.unlink(temporary.name, dir_fd=directory)
            raise
        require(director.project(project) == (root, pin)
                and path_check(image_root, True) == directory_pin, 'DIRECTOR_PROJECT_CHANGED')
        require(path_check(temporary) == staged, 'DIRECTOR_ASSET_CHANGED')
        final = image_root / (digest + '.' + suffix)
        rename_image(directory, temporary.name, final.name)
        os.fsync(directory)
        require(path_check(image_root, True) == directory_pin and path_check(final)[:4] == staged[:4],
                'DIRECTOR_ASSET_CHANGED')
        return spec(final)


def rename_image(directory, source, target):
    from .own_update_package import RENAME_EXCL
    rename = ctypes.CDLL(None, use_errno=True).renameatx_np
    rename.argtypes = [ctypes.c_int, ctypes.c_char_p, ctypes.c_int, ctypes.c_char_p, ctypes.c_uint]
    rename.restype = ctypes.c_int
    if rename(directory, os.fsencode(source), directory, os.fsencode(target), RENAME_EXCL):
        error = ctypes.get_errno()
        raise OSError(error, os.strerror(error))


def source_image(root, spec, scratch, *, h3=False):
    path = local_file(root, spec)
    return image(path, root, spec['sha256'], scratch, h3=h3)


def import_whitebox(root, spec, scratch):
    """Adopt a verified copy into the same project's private media directory."""
    original = local_file(root, spec)
    require(original.suffix.lower() == '.mp4', 'DIRECTOR_WHITEBOX_MP4_REQUIRED')
    media = scratch / 'media'
    try:
        mkdir(scratch, media.name)
    except FileExistsError:
        path_check(media, True)
    target = media / (spec['sha256'] + '.mp4')
    checksum = sha256()
    with tempfile.TemporaryDirectory(prefix='.whitebox-', dir=media) as folder:
        copy = Path(folder) / 'verified.mp4'
        with os.fdopen(os.open(copy, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600), 'wb') as safe:
            for chunk in FileSource(root).iter_html(original.relative_to(root).as_posix()):
                checksum.update(chunk)
                safe.write(chunk)
            require(checksum.hexdigest() == spec['sha256'], 'DIRECTOR_ASSET_CHANGED')
            safe.flush()
            os.fsync(safe.fileno())
        media_facts(copy)
        if not os.path.lexists(target):
            os.replace(copy, target)
            descriptor = os.open(media, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
            try:
                os.fsync(descriptor)
            finally:
                os.close(descriptor)
    preview_whitebox(root, spec)


@lru_cache(maxsize=8)
def verified_whitebox(path, pin, expected):
    checksum = sha256()
    for chunk in FileSource(path.parent).iter_html(path.name, expected_state=pin):
        checksum.update(chunk)
    require(checksum.hexdigest() == expected, 'DIRECTOR_ASSET_CHANGED')
    return media_facts(path)


def validate_revision(jobs, values, patch, root, scratch, project_id):
    if 'images' in patch:
        roles = [row['role'] for row in values['images']]
        require(roles.count('first') <= 1 and roles.count('last') <= 1, 'DIRECTOR_DUPLICATE_FRAME_ROLE')
        seen = set()
        for row in values['images']:
            file = row['file']
            require(file['project_id'] == project_id, 'DIRECTOR_ASSET_WRONG_PROJECT')
            key = (file['path'], file['sha256'])
            if key not in seen:
                source_image(root, file, scratch)
                seen.add(key)
    if 'whitebox' in patch:
        whitebox = values['whitebox']
        for key in ('camera_path', 'subject_path', 'key_points'):
            if key in whitebox:
                project_text(whitebox[key])
        require((whitebox['mode'] == 'import') == ('file' in whitebox), 'DIRECTOR_WHITEBOX_FILE_REQUIRED')
        if 'file' in whitebox:
            require(whitebox['file']['project_id'] == project_id, 'DIRECTOR_ASSET_WRONG_PROJECT')
            import_whitebox(root, whitebox['file'], scratch)
    if 'configuration' in patch:
        config = values['configuration']
        validate_config(config, project_id)
        if 'source' in config:
            if 'reference_asset' in config['source']:
                project_text(config['source']['reference_asset'])
    if 'result' in patch:
        result = values['result']
        require(result['project_id'] == project_id, 'DIRECTOR_ASSET_WRONG_PROJECT')
        _, asset, _ = jobs._playable(result['attempt_id'], project_id)
        require(asset['sha256'] == result['sha256'], 'DIRECTOR_ASSET_CHANGED')
    if 'cards' in patch:
        from .video_director_protocol import prompt_cards
        known = {(row['id'], row['version']) for row in prompt_cards()['cards']}
        for card in values['cards']:
            require((card['id'], card['version']) in known, 'DIRECTOR_UNKNOWN_CARD')


def preview_image(root, spec, small):
    with tempfile.TemporaryDirectory(prefix='openahoy-director-') as folder:
        scratch = Path(folder)
        _, data = source_image(root, spec, scratch)
        original, thumbnail = scratch / 'original', scratch / 'preview.jpg'
        original.write_bytes(data)
        try:
            subprocess.run(['/usr/bin/sips', '-Z', '240' if small else '1360',
                            '-s', 'format', 'jpeg', '-s', 'formatOptions', '75',
                            str(original), '--out', str(thumbnail)],
                           stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                           check=True, timeout=12)
            content = thumbnail.read_bytes()
            require(content.startswith(b'\xff\xd8\xff'), 'DIRECTOR_PREVIEW_UNAVAILABLE')
        except (OSError, subprocess.SubprocessError):
            raise WCEError('DIRECTOR_PREVIEW_UNAVAILABLE') from None
    return {'mime_type': 'image/jpeg', 'data': b64encode(content).decode('ascii'), 'sha256': spec['sha256']}


def preview_whitebox(root, spec, start=None):
    artifact = root / ROOT_NAME / 'media' / (spec['sha256'] + '.mp4')
    pin = path_check(artifact)
    facts = verified_whitebox(artifact, pin, spec['sha256'])
    if start is None:
        return facts
    require(start < facts['seconds'] * 8, 'VIDEO_ASSET_OFFSET_INVALID')
    frames = probe('frames', str(artifact), str(start), error='DIRECTOR_PREVIEW_UNAVAILABLE')
    require(path_check(artifact) == pin, 'DIRECTOR_ASSET_CHANGED')
    return {'start': start, **frames}


def preview_result(jobs, project_id, spec, start=None):
    _, asset, _ = jobs._playable(spec['attempt_id'], project_id)
    require(asset['sha256'] == spec['sha256'], 'DIRECTOR_ASSET_CHANGED')
    if start is None:
        return {key: value for key, value in asset.items() if key != 'path'}
    return jobs.preview_frames(start, spec['attempt_id'], project_id)


def configured_connection(keychain):
    try:
        return 'CONFIGURED' if configured_item(keychain(), keychain.scope) else 'NOT_CONFIGURED'
    except Exception:
        return 'ACTION_REQUIRED'


def models(tokenhex=None):
    catalog = provider_directory()
    observed = tokenhex or {'state': 'NOT_CHECKED', 'models': []}
    available = set(observed['models'])
    verified = observed['state'] in ('MODELS_VISIBLE', 'NO_SUPPORTED_MODELS', 'EMPTY_CATALOG')
    candidates = {'ark': catalog['ark'], 'cn': catalog['minimax'], 'global': catalog['minimax'],
                  'relay': [{'id': RELAY_MODEL, 'name': 'MiniMax H3', 'version': 'workflow'}],
                  'tokenhex': catalog['ark']}
    rows = {}
    for channel, entries in candidates.items():
        results = []
        for row in entries:
            profiles = mode_profiles(channel, row['id'])
            if not profiles:
                continue
            visibility = 'UNVERIFIED' if channel != 'tokenhex' or not verified else (
                'VISIBLE' if row['id'] in available else 'NOT_VISIBLE')
            results.append(dict(row, modes=list(profiles), profiles=profiles, visibility=visibility))
        rows[channel] = results
    return {'models': rows, 'channels': CHANNELS,
            'connections': {provider: status(provider=provider)['state'] for provider in ('ark', *SITES)}
            | {'relay': configured_connection(RelayKeychain), 'tokenhex': configured_connection(TokenHexKeychain)},
            'tokenhex_catalog': {'state': observed['state'], 'models': [r['id'] for r in rows['tokenhex']
                                                                       if r['visibility'] == 'VISIBLE']}
                                | {k: observed[k] for k in ('selected_model', 'native_verified') if k in observed}}


def compute_request(jobs, context, root, scratch):
    """Use the adapters' actual validation and serialization, then discard their body."""
    revision = context['revision']
    config = revision['configuration']
    prompt = revision['prompt']
    require(config, 'DIRECTOR_CONFIGURATION_REQUIRED')
    require(prompt.strip(), 'DIRECTOR_PROMPT_REQUIRED')
    pid = context['project_id']
    profile = validate_config(config, pid, ready=True)
    provider, model, mode = (config[k] for k in ('provider', 'model', 'mode'))
    limit, byte_limit = (20000, 80000) if provider == 'relay' else (4096, 16384)
    require(len(prompt) <= limit and len(prompt.encode()) <= byte_limit, 'DIRECTOR_PROMPT_TOO_LONG')
    receipt = {'provider': provider, 'model': model, 'mode': mode, 'configuration': config, 'prompt': prompt}
    if mode == 'subject':
        url = config['subject_image_url']
        subject_body(prompt, url)
        return receipt | {'inputs': [{'role': 'subject', 'url': url}]}
    if mode == 'workflow':
        workflow_body({'prompt': prompt, **{k: config[k] for k in (
            'reference_images', 'reference_audio', 'duration', 'resolution') if k in config}})
        return receipt | {'inputs': [{'role': role, 'url': url}
                                      for field, role in (('reference_images', 'reference_image'),
                                                          ('reference_audio', 'reference_audio'))
                                      for url in config.get(field, [])]}
    roles = profile['local_roles']
    if profile['reference_count']:
        inputs = [row for row in revision['images'] if row['role'] in REFERENCE]
        require(1 <= len(inputs) <= profile['reference_count'], 'DIRECTOR_REFERENCE_IMAGES_REQUIRED')
    else:
        inputs = [row for role in roles for row in revision['images'] if row['role'] == role]
        require(len(inputs) == len(roles), 'DIRECTOR_INPUT_FRAMES_REQUIRED')
    is_minimax = provider in SITES
    frames = [source_image(root, row['file'], scratch, h3=is_minimax) for row in inputs]
    params = {k: config[k] for k in ('mode', 'duration', 'resolution', 'ratio')}
    if is_minimax:
        encoder = v1_body if model in V1_MODELS else h3_body
        encoder(prompt, frames, model=model, **params)
    else:
        reference = None
        if source := config.get('source'):
            original = jobs.status(source['attempt_id'], pid)
            request = original.get('request', {})
            require(request.get('model') in ARK_MODELS and not request.get('provider'),
                    'VIDEO_REFERENCE_SOURCE_UNAVAILABLE')
            facts = preview_result(jobs, pid, source)
            require((4 if mode == 'edit' else 2) <= facts['seconds'] <= 30, 'VIDEO_REFERENCE_DURATION_INVALID')
            reference = source.get('reference_asset') or 'asset://openahoy-preflight'
        request_body(prompt, frames, model=model, reference=reference,
                     audio=config.get('audio', False), direction=config.get('direction'), **params)
    return receipt | {'inputs': inputs}
