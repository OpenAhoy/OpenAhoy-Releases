"""Explicit caller-selected image import, without passing image bytes over IPC."""
from hashlib import sha256
import os
from pathlib import Path
import re
import stat

from .bounded_file import FileSource, identity
from .contracts import WCEError
from .local_preparation import image_check
from .own_bootstrap_security import path_check
from .own_connection_policy import locked

NAME = re.compile(r'import-([a-f0-9]{64})\.(png|jpg)')
MEDIA_NAME = re.compile(r'wxmedia-([a-f0-9]{64})\.(jpg|png|gif|amr|mp3|mp4)')


def verify(policy, name, mime):
    policy.check()
    match = NAME.fullmatch(name)
    if match is None or (match[2] == 'png') != (mime == 'image/png'):
        raise WCEError('CONNECTION_INVALID_STAGED_IMAGE')
    path = policy.root / 'images' / name
    before = path_check(path)
    data = FileSource(path.parent).read(name)
    if before != path_check(path) or sha256(data).hexdigest() != match[1]:
        raise WCEError('CONNECTION_STAGED_IMAGE_CHANGED')
    image_check(data, mime)
    policy.check()
    return data


def stage(policy, source, mime):
    policy.check()
    path = Path(source)
    if not path.is_absolute() or '..' in path.parts or mime not in {'image/png', 'image/jpeg'}:
        raise WCEError('INVALID_LOCAL_FILE')
    data = FileSource(path.parent).read(path.name)
    image_check(data, mime)
    name = 'import-' + sha256(data).hexdigest() + ('.png' if mime == 'image/png' else '.jpg')
    root = policy.root / 'images'
    with locked(policy.root / 'connection-import.lock'):
        policy.check()
        if os.path.lexists(root / name):
            if verify(policy, name, mime) != data:
                raise WCEError('CONNECTION_STAGED_IMAGE_CHANGED')
            return name
        # Content-addressed staging is not a lifetime image/business quota.
        # Existing entries are verified/reused above; only this new exact file
        # is written. No unknown referenced history or proof is auto-deleted.
        directory = os.open(root, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
        try:
            if identity(os.fstat(directory)) != policy.image_pin:
                raise WCEError('CONNECTION_PATH_CHANGED')
            fd = os.open(name, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600, dir_fd=directory)
            try:
                with os.fdopen(fd, 'wb', closefd=False) as out:
                    out.write(data); out.flush(); os.fsync(fd)
            finally:
                os.close(fd)
            os.fsync(directory)
        finally:
            os.close(directory)
        if verify(policy, name, mime) != data:
            raise WCEError('CONNECTION_STAGED_IMAGE_CHANGED')
    return name


def _media_read(directory, name, extension):
    source = FileSource(directory)
    return source.read_wechat_video(name) if extension == 'mp4' else source.read(name)


def verify_content_media(policy, name, extension):
    policy.check()
    match = MEDIA_NAME.fullmatch(name)
    if match is None or match[2] != extension:
        raise WCEError('CONNECTION_INVALID_STAGED_MEDIA')
    path = policy.root / 'images' / name
    before = path_check(path)
    data = _media_read(path.parent, name, extension)
    if before != path_check(path) or sha256(data).hexdigest() != match[1]:
        raise WCEError('CONNECTION_STAGED_MEDIA_CHANGED')
    policy.check()
    return data


def stage_content_media(policy, source, extension):
    policy.check()
    path = Path(source)
    if not path.is_absolute() or '..' in path.parts:
        raise WCEError('INVALID_LOCAL_FILE')
    data = _media_read(path.parent, path.name, extension)
    name = 'wxmedia-' + sha256(data).hexdigest() + '.' + extension
    root = policy.root / 'images'
    with locked(policy.root / 'connection-import.lock'):
        policy.check()
        if not os.path.lexists(root / name):
            parent = os.open(root, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
            try:
                if identity(os.fstat(parent)) != policy.image_pin:
                    raise WCEError('CONNECTION_PATH_CHANGED')
                temporary = '.wechat-media-' + os.urandom(12).hex()
                fd = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW,
                             0o600, dir_fd=parent)
                try:
                    with os.fdopen(fd, 'wb') as out:
                        out.write(data)
                        out.flush()
                        os.fsync(out.fileno())
                    os.link(temporary, name, src_dir_fd=parent, dst_dir_fd=parent, follow_symlinks=False)
                finally:
                    os.unlink(temporary, dir_fd=parent)
                os.fsync(parent)
            finally:
                os.close(parent)
        if verify_content_media(policy, name, extension) != data:
            raise WCEError('CONNECTION_STAGED_MEDIA_CHANGED')
    return name
