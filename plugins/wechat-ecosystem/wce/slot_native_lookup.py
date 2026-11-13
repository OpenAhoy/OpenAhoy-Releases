"""Registered producer identity for incremental facts, never human authority.

The private host selects a registered producer. Its native creator must match
its own current index row and metadata; it need not be the standing request's
creator. No tool argument may select this lookup's root or producer.
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


class ProducerThreadLookup:
    def __init__(self, state_path, session_root, producer_thread, guard, *, deadline=None):
        valid_thread(producer_thread)
        self.thread = producer_thread
        self.guard = guard
        # This comparison proves the producer's own observed index identity.
        # It does not transfer the producer's creator or text into authority.
        self._index = NativeThreadLookup(state_path, session_root, producer_thread,
            guard, allowed_threads=(producer_thread,), deadline=deadline)

    def locate(self):
        path, owner = self._index._row(self.thread)
        try:
            info = path.lstat()
            temporary = RegisteredSource('native-producer-header', path, info.st_dev,
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
            source_id = 'native-producer-' + digest({'thread': self.thread,
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
