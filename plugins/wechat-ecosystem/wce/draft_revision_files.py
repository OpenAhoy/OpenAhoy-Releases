"""Revision-private bounded canonical JSON with existing safe file semantics.

NEWS preservation AST records need the already bounded 32-level parser. Legacy
replacement readers keep their 16-level limit and are not changed here.
"""
from hashlib import sha256
import os,stat,time
from pathlib import Path
from .bounded_file import FileSource,file_state,identity
from .contracts import WCEError
from .own_replacement_files import folder
from .publication_contract import strict_json
from .service import canonical
MAXIMUM=2*1024*1024

def fail():raise WCEError('DRAFT_REVISION_RECORD_HOLD')

def read(path, maximum=MAXIMUM):
    path = Path(path)
    source = FileSource(path.parent)
    descriptors,chain=[],[]
    try:
        root=source._root(descriptors,chain)
        if identity(os.fstat(root)) != folder(path.parent): fail()
        fd=os.open(path.name,os.O_RDONLY|os.O_NOFOLLOW|os.O_NONBLOCK,dir_fd=root)
        descriptors.append(fd);before=os.fstat(fd)
        def pin(info): return file_state(info)+(info.st_uid,info.st_mode)
        if (not stat.S_ISREG(before.st_mode) or before.st_uid!=os.getuid()
                or stat.S_IMODE(before.st_mode)!=0o600 or before.st_nlink!=1
                or not 0<before.st_size<=maximum): fail()
        raw=bytearray();stop=time.monotonic()+2
        while len(raw)<=maximum:
            if time.monotonic()>stop: fail()
            chunk=os.read(fd,min(65536,maximum+1-len(raw)))
            if not chunk: break
            raw.extend(chunk)
        after=os.fstat(fd);entry=os.stat(path.name,dir_fd=root,follow_symlinks=False)
        if pin(before)!=pin(after) or pin(after)!=pin(entry) or len(raw)!=after.st_size: fail()
        source._check_chain(chain)
        value=strict_json(bytes(raw),maximum=maximum)
        if (canonical(value)+'\n').encode()!=bytes(raw): fail()
        return value,sha256(raw).hexdigest()
    except (OSError,ValueError):
        fail()
    finally: source._close(descriptors)


def exclusive(path, value):
    path=Path(path);root=folder(path.parent)
    raw=(canonical(value)+'\n').encode()
    if not 0<len(raw)<=MAXIMUM: fail()
    directory=os.open(path.parent,os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW)
    try:
        if identity(os.fstat(directory))!=root: fail()
        fd=os.open(path.name,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o600,dir_fd=directory)
        with os.fdopen(fd,'wb') as output:
            output.write(raw);output.flush();os.fsync(output.fileno())
        os.fsync(directory)
        if root!=folder(path.parent) or read(path)[0]!=value: fail()
    finally: os.close(directory)
    return sha256(raw).hexdigest()

