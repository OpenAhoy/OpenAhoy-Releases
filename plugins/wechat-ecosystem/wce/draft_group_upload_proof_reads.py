"""Actual nonsecret proof-read receipts; integrity evidence, never permission.

Only the original upload-history helper runs while collection is active. The
two fixed IO leaves report bytes they actually read. No path comes from a
descriptor, and no additional credential/file lookup is performed.
"""
from contextvars import ContextVar
from hashlib import sha256
from pathlib import Path
import weakref
from .contracts import WCEError

_ACTIVE=ContextVar('original_group_upload_proof_reads',default=None)
_RECEIPTS=weakref.WeakKeyDictionary()
MAX_FILES=16
MAX_BYTES=2*1024*1024


def hold():raise WCEError('GROUP_UPLOAD_PROOF_READ_HOLD')


class ProofReadReceipt:
    def __init__(self):hold()
    def collective_fence(self):
        record=_RECEIPTS.get(self)
        if record is None:hold()
        root,root_pin,entries,poisoned=record
        if poisoned:hold()
        from .own_bootstrap_security import path_check
        try:
            if path_check(root,True)!=root_pin:hold()
            for path,pin,_,_ in entries:
                if path.parent!=root or path_check(path)!=pin:hold()
        except BaseException:
            _RECEIPTS[self]=(root,root_pin,entries,True)
            raise
        return None


def _observe(path,raw,pin,*,replacement):
    active=_ACTIVE.get()
    if active is None:return
    path=Path(path)
    prefixes=(('replacement-proof-','replacement-index-') if replacement else
              ('response-','reconciliation-'))
    if not path.name.startswith(prefixes):
        return
    root,_,entries=active
    if (path.parent!=root or type(raw)is not bytes or not 1<=len(raw)<=MAX_BYTES
            or type(pin)is not tuple or len(pin)!=6 or any(type(v)is not int for v in pin)
            or len(entries)>=MAX_FILES):hold()
    entries.append((path,pin,sha256(raw).hexdigest(),len(raw)))


def observe_private_read(path,raw,pin):
    _observe(path,raw,pin,replacement=False)


def observe_replacement_read(path,raw,pin):
    _observe(path,raw,pin,replacement=True)


def read_original_upload_success_with_proofs_in(workflow,db,profile,step_id, *, history_locators=None):
    from .own_bootstrap_security import path_check
    from .own_step_history import read_original_upload_success_in
    from .own_validation_scope import OwnedConnection,_transaction_marker
    if (_ACTIVE.get() is not None or type(db)is not OwnedConnection
            or _transaction_marker(db)is None):hold()
    root=Path(workflow.db.path).parent
    root_pin=path_check(root,True);entries=[]
    token=_ACTIVE.set((root,root_pin,entries))
    try:
        facts=read_original_upload_success_in(workflow,db,profile,step_id, history_locators=history_locators)
    finally:_ACTIVE.reset(token)
    receipt=object.__new__(ProofReadReceipt)
    _RECEIPTS[receipt]=(root,root_pin,tuple(entries),False)
    receipt.collective_fence()
    facts['proof_files']=sorted([{'sha256':checksum,'size':size}for _,_,checksum,size in entries],
                               key=lambda item:(item['sha256'],item['size']))
    return facts,receipt
