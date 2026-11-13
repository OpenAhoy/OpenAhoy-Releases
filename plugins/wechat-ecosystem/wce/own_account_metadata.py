"""Private account metadata carrier: actual extent, no account/history quota.

Callers still validate their closed typed schema and authority. Reading a private
JSON file never grants connection, enrollment, recovery or publication rights.
"""
from hashlib import sha256
import os
from pathlib import Path
import stat

from .contracts import WCEError
from .own_bootstrap_security import decode, path_check
from .own_identity_checkpoint import Reader, file_metadata


def decode_metadata(raw):
    # Duplicate keys, non-JSON constants and invalid UTF-8 remain rejected by
    # the original decoder. Its size argument is this captured carrier only.
    return decode(raw,len(raw))


def read_at(parent,name,guard=lambda:None):
    fd=os.open(name,os.O_RDONLY|os.O_NOFOLLOW|os.O_NONBLOCK,dir_fd=parent)
    try:
        before=os.fstat(fd);pin=file_metadata(before)
        if (not stat.S_ISREG(before.st_mode) or before.st_uid!=os.getuid()
                or stat.S_IMODE(before.st_mode)!=0o600 or before.st_nlink!=1 or before.st_size<=0
                or file_metadata(os.stat(name,dir_fd=parent,follow_symlinks=False))!=pin):
            raise WCEError('CONNECTION_METADATA_INVALID')
        parts=[];length=0;hasher=sha256()
        while length<before.st_size:
            guard();block=os.read(fd,min(65536,before.st_size-length))
            if not block:raise WCEError('CONNECTION_PATH_CHANGED')
            parts.append(block);length+=len(block);hasher.update(block)
        if (os.read(fd,1) or file_metadata(os.fstat(fd))!=pin
                or file_metadata(os.stat(name,dir_fd=parent,follow_symlinks=False))!=pin):
            raise WCEError('CONNECTION_PATH_CHANGED')
        guard()
        return pin|{'sha256':hasher.hexdigest()},b''.join(parts)
    finally:os.close(fd)


def metadata_bytes(path,*,optional=False,guard=lambda:None):
    path=Path(path)
    if optional and not os.path.lexists(path):return None
    path_check(path)
    reader=Reader(path.parent)
    with reader.directory(path.parent) as parent:
        return read_at(parent,path.name,guard)


def read_metadata(path):
    result=metadata_bytes(path,optional=True)
    return None if result is None else decode_metadata(result[1])


def raw_metadata(path,*,optional=False,guard=lambda:None):
    result=metadata_bytes(path,optional=optional,guard=guard)
    return None if result is None else result[1]


class AccountMetadataReader(Reader):
    def read(self,path,keep=False,optional=False):
        # Preserve Reader(private_root)'s ancestor policy. A temporary Reader
        # rooted at path.parent would silently discard the caller's base.
        path=Path(path)
        with self.directory(path.parent) as parent:
            if optional:
                try:os.stat(path.name,dir_fd=parent,follow_symlinks=False)
                except FileNotFoundError:return None,None
            try:meta,raw=read_at(parent,path.name)
            except FileNotFoundError:
                raise WCEError('CONNECTION_RELOCATION_SOURCE_MISSING') from None
            except OSError:
                raise WCEError('CONNECTION_RELOCATION_UNSAFE_PATH') from None
            return meta,raw if keep else None


def decode_metadata_strict(raw):
    from .prepared_draft_fixture import decode_json
    return decode_json(raw,len(raw),max_nodes=len(raw))


def account_carrier(path,base):
    """Known aggregate locations only; this predicate conveys no authority."""
    import re
    path,base=Path(path),Path(base)
    return (path==base/'connections.json'
        or path.parent==base/'connection-transactions' and re.fullmatch(r'txn-[a-f0-9]{32}\.json',path.name) is not None
        or path.parent==base/'compatible-upgrades' and re.fullmatch(r'cup-[a-f0-9]{32}\.json',path.name) is not None)
