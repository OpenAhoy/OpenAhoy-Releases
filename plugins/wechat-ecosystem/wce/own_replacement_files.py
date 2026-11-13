"""Private, bounded replacement records. Hashes are pins, not signatures."""
from hashlib import sha256
import os
from pathlib import Path
import re
import stat
import time

from .bounded_file import FileSource, file_state, identity
from .contracts import WCEError
from .own_bootstrap_security import path_check
from .own_connection_policy import atomic_write
from .prepared_draft_fixture import decode_json
from .service import canonical, digest

MAXIMUM = 2 * 1024 * 1024
ZERO = '0' * 64


def fail(code='OWN_REPLACEMENT_RECORD_HOLD'):
    raise WCEError(code)


def name(value):
    if type(value) is not str or re.fullmatch('[A-Za-z0-9_.-]{1,160}',value) is None:
        fail()
    return value


def folder(path, create=False):
    path = Path(path)
    if create:
        parent = path_check(path.parent,True)
        fd = os.open(path.parent,os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW)
        try:
            if identity(os.fstat(fd)) != parent: fail()
            try: os.mkdir(path.name,0o700,dir_fd=fd)
            except FileExistsError: pass
            os.fsync(fd)
        finally: os.close(fd)
    return path_check(path,True)


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
        value=decode_json(bytes(raw),maximum,max_nodes=32768)
        if (canonical(value)+'\n').encode()!=bytes(raw): fail()
        from .draft_group_upload_proof_reads import observe_replacement_read
        observe_replacement_read(path,bytes(raw),file_state(after))
        return value,sha256(raw).hexdigest()
    except (OSError,ValueError):
        fail()
    finally: source._close(descriptors)


def stored(raw,checksum):
    """New R1 tables only; legacy/group readers retain their original bounds."""
    if type(raw) is not str: fail()
    value=decode_json(raw.encode(),MAXIMUM,max_nodes=32768)
    if canonical(value)!=raw or digest(value)!=checksum: fail()
    return value


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


def durable(path):
    """Re-fsync already qualified files before a recovery CAS, never a send."""
    path=Path(path);before=read(path)
    parent=folder(path.parent)
    directory=os.open(path.parent,os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW)
    try:
        if identity(os.fstat(directory))!=parent: fail()
        fd=os.open(path.name,os.O_RDONLY|os.O_NOFOLLOW|os.O_NONBLOCK,dir_fd=directory)
        try: os.fsync(fd)
        finally: os.close(fd)
        os.fsync(directory)
        if read(path)!=before or folder(path.parent)!=parent: fail()
    finally: os.close(directory)
    return before


def state(batch):
    pointer,_=read(Path(batch)/'state.json',16384)
    if type(pointer) is not dict or set(pointer)!={'seq','event_sha'}: fail()
    seq=pointer['seq']
    if type(seq) is not int or not 1<=seq<=32: fail()
    paths=sorted(p.name for p in Path(batch).iterdir() if p.name.startswith('state-event-'))
    expected=['state-event-'+str(i).zfill(4)+'.json' for i in range(1,seq+1)]
    if paths!=expected: fail()
    previous=ZERO;last=None
    for index,filename in enumerate(expected,1):
        event,_=read(Path(batch)/filename,65536)
        if (type(event) is not dict or set(event)!={'schema','seq','previous','payload'}
                or event['schema']!=1 or event['seq']!=index or event['previous']!=previous
                or type(event['payload']) is not dict): fail()
        previous=digest(event);last=event['payload']
    if previous!=pointer['event_sha']: fail()
    return last,pointer


def transition(batch,payload,expected=None):
    batch=Path(batch)
    if os.path.lexists(batch/'state.json'):
        current,head=state(batch)
        if expected is not None and current!=expected: fail('OWN_REPLACEMENT_STATE_CHANGED')
    else:
        if any(p.name.startswith('state-event-') for p in batch.iterdir()): fail()
        if expected is not None: fail()
        head={'seq':0,'event_sha':ZERO}
    if head['seq']>=32: fail()
    event={'schema':1,'seq':head['seq']+1,'previous':head['event_sha'],'payload':payload}
    exclusive(batch/('state-event-'+str(event['seq']).zfill(4)+'.json'),event)
    atomic_write(batch/'state.json',{'seq':event['seq'],'event_sha':digest(event)})
    if state(batch)[0]!=payload: fail()
    return digest(event)
