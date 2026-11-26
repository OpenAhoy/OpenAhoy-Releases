"""Trusted local regular-file acquisition; no URL, decoding or model entry point."""
from contextlib import contextmanager
import os
from pathlib import Path
import stat
import time

from .contracts import WCEError

MAX_ASSET_BYTES = 2 * 1024 * 1024
MAX_WECHAT_VIDEO_BYTES = 10 * 1024 * 1024
# Full delivered HTML can contain several bounded base64 images. This fixed
# capability is used only by the trusted full-page importer, never a tool max.
MAX_SOURCE_HTML_BYTES = 4 * 1024 * 1024
MAX_COMPONENTS = 32
READ_SECONDS = 2.0
CHUNK_BYTES = 64 * 1024


def identity(info):
    return (info.st_dev, info.st_ino)


def file_state(info):
    return identity(info) + (info.st_size, info.st_mtime_ns, info.st_ctime_ns, info.st_nlink)


class FileSource:
    """A trusted administrator selects an absolute, nonsymlink local root.

    Descriptor-relative traversal pins each opened directory and checks its
    parent entry again before accepting bytes. Bounds apply to actual bytes.
    O_NONBLOCK prevents FIFO opens from hanging; the cooperative deadline does
    not promise interruption of a hostile filesystem's blocking system call.
    """
    def __init__(self, root):
        self.root = Path(root)
        if (not self.root.is_absolute() or len(self.root.parts) - 1 > MAX_COMPONENTS
                or any(part == ".." for part in self.root.parts)):
            raise WCEError("INVALID_LOCAL_ROOT")
        descriptors, chain = [], []
        try:
            fd = self._root(descriptors, chain)
            self.root_identity = identity(os.fstat(fd))
            self._check_chain(chain)
        except OSError:
            raise WCEError("INVALID_LOCAL_ROOT") from None
        finally:
            self._close(descriptors)

    @staticmethod
    def _close(descriptors):
        for fd in reversed(descriptors):
            os.close(fd)

    @staticmethod
    def _check_chain(chain):
        for parent, name, fd in chain:
            current = os.stat(name, dir_fd=parent, follow_symlinks=False)
            if not stat.S_ISDIR(current.st_mode) or identity(current) != identity(os.fstat(fd)):
                raise WCEError("LOCAL_FILE_CHANGED")

    def _directory(self, parent, name, descriptors, chain):
        fd = os.open(name, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_NONBLOCK,
                     dir_fd=parent)
        descriptors.append(fd)
        chain.append((parent, name, fd))
        return fd

    def _root(self, descriptors, chain):
        fd = os.open("/", os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
        descriptors.append(fd)
        for name in self.root.parts[1:]:
            fd = self._directory(fd, name, descriptors, chain)
        return fd

    @contextmanager
    def open_directory(self, parts):
        """Pin a project directory for read-only enumeration by its descriptor."""
        if len(parts) > MAX_COMPONENTS or any(p in {'', '.', '..'} or '/' in p for p in parts):
            raise WCEError('INVALID_LOCAL_FILE')
        descriptors, chain = [], []
        try:
            fd = self._root(descriptors, chain)
            if identity(os.fstat(fd)) != self.root_identity:
                raise WCEError('LOCAL_FILE_CHANGED')
            for name in parts:
                fd = self._directory(fd, name, descriptors, chain)
            if os.fstat(fd).st_uid != os.getuid():
                raise WCEError('INVALID_LOCAL_FILE')
            yield fd
            self._check_chain(chain)
        except OSError:
            raise WCEError('INVALID_LOCAL_FILE') from None
        finally:
            self._close(descriptors)

    def read(self, relative_path):
        return self._read(relative_path, MAX_ASSET_BYTES)

    def read_html(self, relative_path):
        """Trusted source-page envelope; image and generic reads stay 2MiB."""
        return self._read(relative_path, MAX_SOURCE_HTML_BYTES)

    def read_wechat_video(self, relative_path):
        return self._read(relative_path, MAX_WECHAT_VIDEO_BYTES)

    @contextmanager
    def open_pinned(self, relative_path, *, expected_state=None):
        """Open a seekable regular file and recheck its identity on successful use."""
        if (type(relative_path) is not str or not relative_path or len(relative_path)>4096
                or relative_path.startswith('/') or ':' in relative_path or "\x00" in relative_path):
            raise WCEError('INVALID_LOCAL_FILE')
        parts=relative_path.split('/')
        if len(parts)>MAX_COMPONENTS or any(p in {'','.','..'} for p in parts):
            raise WCEError('INVALID_LOCAL_FILE')
        descriptors,chain=[],[]
        try:
            parent=self._root(descriptors,chain)
            if identity(os.fstat(parent))!=self.root_identity:raise WCEError('LOCAL_FILE_CHANGED')
            for name in parts[:-1]:parent=self._directory(parent,name,descriptors,chain)
            fd=os.open(parts[-1],os.O_RDONLY|os.O_NOFOLLOW|os.O_NONBLOCK,dir_fd=parent)
            descriptors.append(fd);before=os.fstat(fd)
            if (not stat.S_ISREG(before.st_mode) or before.st_nlink!=1
                    or before.st_uid!=os.getuid() or before.st_size<=0):raise WCEError('INVALID_LOCAL_FILE')
            if expected_state is not None and tuple(expected_state)!=file_state(before):raise WCEError('LOCAL_FILE_CHANGED')
            yield fd, before
            after=os.fstat(fd);entry=os.stat(parts[-1],dir_fd=parent,follow_symlinks=False)
            if file_state(before)!=file_state(after) or file_state(after)!=file_state(entry):
                raise WCEError('LOCAL_FILE_CHANGED')
            self._check_chain(chain)
        except OSError:
            raise WCEError('INVALID_LOCAL_FILE') from None
        finally:self._close(descriptors)

    def iter_html(self, relative_path, *, guard=lambda: None, expected_state=None, offset=0, length=None):
        """Normal HTML source stream; total image/page bytes are not a quota."""
        with self.open_pinned(relative_path, expected_state=expected_state) as (fd,before):
            if type(offset)is not int or not 0<=offset<=before.st_size:raise WCEError('INVALID_LOCAL_FILE')
            if length is not None and (type(length) is not int or not 0 <= length <= before.st_size - offset):
                raise WCEError('LOCAL_FILE_CHANGED')
            end = before.st_size if length is None else offset + length
            os.lseek(fd,offset,os.SEEK_SET)
            total=offset
            while total < end:
                guard()
                if file_state(os.fstat(fd))!=file_state(before):raise WCEError('LOCAL_FILE_CHANGED')
                chunk=os.read(fd,min(CHUNK_BYTES,end-total))
                if not chunk:break
                total+=len(chunk);yield chunk
            if total!=end:
                raise WCEError('LOCAL_FILE_CHANGED')
        guard()

    def _read(self, relative_path, maximum):
        if type(maximum) is not int or maximum not in (MAX_ASSET_BYTES, MAX_SOURCE_HTML_BYTES, MAX_WECHAT_VIDEO_BYTES):
            raise WCEError("LOCAL_FILE_LIMIT")
        if (not isinstance(relative_path, str) or not relative_path or len(relative_path) > 4096
                or relative_path.startswith("/") or ":" in relative_path or "\x00" in relative_path):
            raise WCEError("INVALID_LOCAL_FILE")
        parts = relative_path.split("/")
        if len(parts) > MAX_COMPONENTS or any(p in {"", ".", ".."} for p in parts):
            raise WCEError("INVALID_LOCAL_FILE")
        descriptors, chain = [], []
        try:
            parent = self._root(descriptors, chain)
            if identity(os.fstat(parent)) != self.root_identity:
                raise WCEError("LOCAL_FILE_CHANGED")
            for name in parts[:-1]:
                parent = self._directory(parent, name, descriptors, chain)
            fd = os.open(parts[-1], os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=parent)
            descriptors.append(fd)
            before = os.fstat(fd)
            if not stat.S_ISREG(before.st_mode) or before.st_nlink != 1:
                raise WCEError("INVALID_LOCAL_FILE")
            if not 0 < before.st_size <= maximum:
                raise WCEError("LOCAL_FILE_LIMIT")
            deadline = time.monotonic() + READ_SECONDS
            data = bytearray()
            while True:
                if time.monotonic() > deadline:
                    raise WCEError("LOCAL_FILE_LIMIT")
                chunk = os.read(fd, min(CHUNK_BYTES, maximum + 1 - len(data)))
                if not chunk:
                    break
                data.extend(chunk)
                if len(data) > maximum:
                    raise WCEError("LOCAL_FILE_LIMIT")
            after = os.fstat(fd)
            entry = os.stat(parts[-1], dir_fd=parent, follow_symlinks=False)
            if (not stat.S_ISREG(entry.st_mode) or file_state(before) != file_state(after)
                    or file_state(after) != file_state(entry) or len(data) != after.st_size):
                raise WCEError("LOCAL_FILE_CHANGED")
            self._check_chain(chain)
            if time.monotonic() > deadline:
                raise WCEError("LOCAL_FILE_LIMIT")
            return bytes(data)
        except OSError:
            raise WCEError("INVALID_LOCAL_FILE") from None
        finally:
            self._close(descriptors)
