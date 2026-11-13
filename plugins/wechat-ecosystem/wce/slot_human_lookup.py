"""Host-selected same-owner human thread, not a publication capability.

The host fixes the standing human owner and one observed thread. The actual
index worker compares their creators before any USER text is interpreted.
A producer lookup or caller role string cannot substitute for this identity.
"""
from hashlib import sha256
import os

from .draft_revision_native_lookup import NativeThreadLookup, valid_thread
from .draft_revision_native_source import (
    RegisteredSource, SourceHold, checked_guard, digest, require, strict_json,
    _open_source, _first_line)


def metadata_origin(meta, thread):
    """Validate native pagination provenance without a lifetime ordinal cap."""
    require(type(meta) is dict and meta.get('type') == 'session_meta'
            and type(meta.get('ordinal')) is int and meta['ordinal'] >= 0
            and type(meta.get('payload')) is dict and meta['payload'].get('id') == thread,
            'SOURCE_META_INVALID')
    ordinal = meta['ordinal']
    if ordinal:
        payload = meta['payload']
        base = payload.get('history_base')
        require(payload.get('history_mode') == 'paginated' and type(base) is dict
                and set(base) == {'end_byte_offset', 'end_ordinal_exclusive', 'thread_id'}
                and base['thread_id'] == thread
                and type(base['end_ordinal_exclusive']) is int
                and base['end_ordinal_exclusive'] == ordinal
                and type(base['end_byte_offset']) is int and base['end_byte_offset'] >= 0,
                'SOURCE_HISTORY_BASE_UNVERIFIED')
    return ordinal


class HumanThreadLookup:
    def __init__(self, state_path, session_root, human_owner_thread, observed_thread, guard, *, deadline=None):
        valid_thread(human_owner_thread)
        valid_thread(observed_thread)
        self.thread = observed_thread
        self.guard = guard
        # One observer per host-selected source: no aggregate thread/pin quota.
        # Ownership is anchored to the standing human thread, not producer self.
        self._index = NativeThreadLookup(state_path, session_root, human_owner_thread,
            guard, allowed_threads=(observed_thread,), deadline=deadline)

    def locate(self):
        path, owner = self._index._row(self.thread)
        try:
            info = path.lstat()
            temporary = RegisteredSource('native-human-header', path, info.st_dev,
                info.st_ino, self.thread, 0, 0, sha256(b'').hexdigest(), '0' * 64)
            fd, parent, name, descriptors, chain = _open_source(temporary)
            try:
                first = _first_line(fd, os.fstat(fd).st_size, self.guard)
                current = os.stat(name, dir_fd=parent, follow_symlinks=False)
                require((current.st_dev, current.st_ino) == (info.st_dev, info.st_ino),
                        'HOST_NATIVE_SOURCE_CHANGED')
            finally:
                for descriptor in reversed(descriptors):
                    os.close(descriptor)
            meta = strict_json(first, maximum=32 * 1024 * 1024)
            ordinal = metadata_origin(meta, self.thread)
            payload = meta['payload']
            require((payload.get('creator_user_id'), payload.get('creator_account_id')) == owner,
                    'HOST_NATIVE_METADATA_MISMATCH')
            meta_sha = sha256(first).hexdigest()
            source_id = 'native-human-' + digest({'thread': self.thread,
                'path_sha256': sha256(str(path).encode()).hexdigest(),
                'device': info.st_dev, 'inode': info.st_ino,
                'metadata_sha256': meta_sha, 'metadata_ordinal': ordinal})[:48]
            result = RegisteredSource(source_id, path, info.st_dev, info.st_ino,
                self.thread, 0, ordinal, sha256(b'').hexdigest(), meta_sha, ordinal)
            require(self._index._row(self.thread) == (path, owner), 'HOST_NATIVE_POINTER_CHANGED')
        except OSError:
            raise SourceHold('HOST_NATIVE_SOURCE_HOLD') from None
        checked_guard(self.guard)
        return result
