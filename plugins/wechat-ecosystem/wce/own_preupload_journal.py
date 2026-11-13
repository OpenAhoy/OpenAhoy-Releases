"""Original project-tag preconsumption; never SDK or network authority.

The fixed session must first qualify the original slot in Owned/H. This leaf
only serializes its project once records and holds the two exact new files.
An orphaned intent remains spent. Closing a reservation never removes a file.
"""
from dataclasses import dataclass
from hashlib import sha256
import json
import os
from pathlib import Path
import re
import stat
import threading
from weakref import WeakKeyDictionary

from .contracts import WCEError
from .draft_group_pin_resources import capacity, close_all, full, MAX_RAW_BYTES
from .own_connection_policy import locked
from .own_bootstrap_security import path_check
from .service import canonical

_HASH = re.compile(r'[0-9a-f]{64}\Z')
_TAG = re.compile(r'm(\d{2})-execute-(cover|body(?:[1-9]|[12][0-9]|3[0-2]))\Z')
_RESERVATIONS = WeakKeyDictionary()
_READ_METHODS = frozenset(('own.connections.list','own.connections.status','own.assets.status',
    'own.articles.status','own.articles.read','own.uploads.status'))
_LOCAL_METHODS = frozenset(('own.assets.import','own.documents.prepare'))


def need(value):
    if value is not True:
        raise WCEError('PREUPLOAD_ORIGINAL_ONCE_HOLD')


@dataclass(frozen=True, eq=False, init=False)
class OriginalSlotReservation:
    authority: bool = False

    def __init__(self, *args, **kwargs):
        raise WCEError('PREUPLOAD_RESERVATION_ISSUER_REQUIRED')


class ProjectOnceJournal:
    """Mechanical file owner. Possessing this journal grants no upload right."""
    def __init__(self, root, *, journal_binding_sha256, phase_sha256, resume_id, child_ordinal):
        self.root = Path(root)
        need(self.root.is_absolute() and '..' not in self.root.parts
             and type(journal_binding_sha256) is str and _HASH.fullmatch(journal_binding_sha256) is not None
             and type(phase_sha256) is str and _HASH.fullmatch(phase_sha256) is not None
             and type(resume_id) is str and re.fullmatch(r'preupload-resume-[0-9a-f]{32}', resume_id)
             and type(child_ordinal) is int and 1 <= child_ordinal <= 109)
        self.binding_sha, self.phase_sha = journal_binding_sha256, phase_sha256
        self.resume_id, self.child_ordinal = resume_id, child_ordinal
        self.owner = os.getpid(), threading.get_ident()
        self.active, self.parent = False, None
        self.pin = self.lock_scope = self.lock_fd = None
        self.reservations = []
        self.namespace_cache={}
        self.namespace_aux_cache={}
        self.namespace_bytes=0

    def __enter__(self):
        need(self.parent is None and not self.active)
        capacity(3, persistent=True)  # root + lock + lock-parent transient peak
        path_check(self.root, True)
        self.parent = os.open(self.root, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
        try:
            info = os.fstat(self.parent)
            need(stat.S_ISDIR(info.st_mode) and info.st_uid == os.getuid()
                 and stat.S_IMODE(info.st_mode) == 0o700
                 and full(info) == full(self.root.lstat()))
            self.pin = full(info)[:5]
            self.lock_scope = locked(self.root/'preupload-resume.lock', nonblocking=True)
            self.lock_fd = self.lock_scope.__enter__()
            self.active = True
            self.check()
            return self
        except BaseException as original:
            self.close(original=original)
            raise

    def check(self):
        need(self.active and self.owner == (os.getpid(), threading.get_ident())
             and full(os.fstat(self.parent))[:5] == self.pin == full(self.root.lstat())[:5])
        lock = os.fstat(self.lock_fd)
        need(stat.S_ISREG(lock.st_mode) and lock.st_uid == os.getuid()
             and stat.S_IMODE(lock.st_mode) == 0o600 and lock.st_nlink == 1
             and full(lock) == full((self.root/'preupload-resume.lock').lstat()))

    def _tag(self, tag):
        need(type(tag) is str)
        match = _TAG.fullmatch(tag)
        need(match is not None and 1 <= int(match[1]) <= 28)

    def attempted(self, tag):
        self.check(); self._tag(tag)
        leaves = (tag+'-intent.json', tag+'-result.json', tag+'-unknown.json',
                  tag+'-preupload-claim.json', tag+'-preupload-terminal.json')
        # lexists deliberately treats symlinks/partial leaves as attempted.
        return any(os.path.lexists(self.root/leaf) for leaf in leaves)

    def require_namespace(self,original_arguments,*,child_ordinal,available_raw_bytes):
        """Bounded whole-OUT mutation namespace check, not a send permit.

        Retained read/local-prepare records keep their original meaning. Every
        upload intent must have an original109 tag AND the exact original
        key/selector/connection/slot tuple. Unknown mutation/claim names stop.
        Cached summaries are immutable computations bound to full file pins;
        the directory set and each named stat are rechecked on every call.
        """
        self.check()
        need(type(original_arguments) is dict and 0<len(original_arguments)<=109
             and type(child_ordinal) is int and child_ordinal==self.child_ordinal
             and type(available_raw_bytes) is int and 0<available_raw_bytes<=MAX_RAW_BYTES)
        allowed=json.loads(canonical(original_arguments))
        for tag in allowed:self._tag(tag)
        names=os.listdir(self.parent);need(len(names)<=32768)
        intents={}
        for name in names:
            recognized=(name in ('local-input-preparation.json','preupload-resume.lock','preupload-child-start.lock')
                or re.fullmatch(r'm[0-9]{2}-(pre-import-stage|prepared|upload-report)\.json',name) is not None
                or re.fullmatch(r'(?:m[0-9]{2}-.+|preflight-.+)-(intent|result|unknown)\.json',name) is not None
                or re.fullmatch(r'preupload-child-[0-9]{3}-(claim|created|terminal)\.json',name) is not None
                or re.fullmatch(r'm[0-9]{2}-execute-(?:cover|body[0-9]+)-preupload-(claim|terminal)\.json',name) is not None)
            need(recognized)
            member=re.match(r'm([0-9]+)-',name)
            if member:need(1<=int(member[1])<=28)
            if '-execute-' in name:
                suffixes=('-intent.json','-result.json','-unknown.json',
                          '-preupload-claim.json','-preupload-terminal.json')
                suffix=next((suffix for suffix in suffixes if name.endswith(suffix)),None)
                need(suffix is not None and name[:-len(suffix)] in allowed)
            elif name.startswith('preupload-child-') and name.endswith('.json'):
                match=re.fullmatch(r'preupload-child-([0-9]{3})-(claim|created|terminal)\.json',name)
                need(match is not None and 1<=int(match[1])<=child_ordinal)
            elif name.endswith('-claim.json') or name.endswith('-terminal.json'):
                need(False)
            if not name.endswith('-intent.json'):continue
            info=os.stat(name,dir_fd=self.parent,follow_symlinks=False)
            need(stat.S_ISREG(info.st_mode) and info.st_uid==os.getuid() and info.st_nlink==1
                 and stat.S_IMODE(info.st_mode)==0o600 and 0<info.st_size<=2*1024*1024)
            pin=full(info);cached=self.namespace_cache.get(name)
            need(cached is None or cached[0]==pin)
            if cached is not None and cached[0]==pin:
                summary=json.loads(cached[1])
            else:
                need(self.namespace_bytes+info.st_size<=available_raw_bytes)
                capacity(1,persistent=True)
                fd=os.open(name,os.O_RDONLY|os.O_NOFOLLOW|os.O_NONBLOCK,dir_fd=self.parent)
                original=None
                try:
                    need(full(os.fstat(fd))==pin)
                    raw=os.pread(fd,info.st_size+1,0)
                    need(len(raw)==info.st_size and full(os.fstat(fd))==pin
                         ==full(os.stat(name,dir_fd=self.parent,follow_symlinks=False)))
                    from .own_preupload_qa import _pairs
                    value=json.loads(raw.decode('utf-8'),object_pairs_hook=_pairs,
                        parse_constant=lambda _:need(False))
                    need(type(value) is dict and set(value)=={'state','method','arguments','binding_sha256'}
                         and value['state']=='RESERVED_NO_REPLAY' and value['binding_sha256']==self.binding_sha
                         and type(value['method']) is str
                         and value['method'] in _READ_METHODS|_LOCAL_METHODS|{'own.uploads.execute'})
                    summary={'method':value['method'],'arguments':value['arguments']
                             if value['method']=='own.uploads.execute' else None,
                             'raw_sha256':sha256(raw).hexdigest()}
                except BaseException as error:original=error;raise
                finally:close_all([lambda:os.close(fd)],original)
                encoded=canonical(summary)
                charge=len(encoded.encode())-(0 if cached is None else len(cached[1].encode()))
                need(self.namespace_bytes+charge<=available_raw_bytes)
                self.namespace_cache[name]=(pin,encoded);self.namespace_bytes+=charge
            method=summary['method']
            if method=='own.uploads.execute':
                tag=name[:-len('-intent.json')]
                need(tag in allowed and canonical(summary['arguments'])==canonical(allowed[tag]))
            else:
                need('-execute-' not in name)
                if method in _READ_METHODS:need(re.fullmatch(r'.+-read-[0-9a-f]{16}-intent\.json',name) is not None)
            intents[name[:-len('-intent.json')]]=summary
        for name in names:
            suffix=next((suffix for suffix in ('-unknown.json','-result.json') if name.endswith(suffix)),None)
            if suffix is not None:
                prefix=name[:-len(suffix)]
                need(prefix in intents)
        for name in names:
            if name.endswith('-preupload-claim.json'):
                tag=name[:-len('-preupload-claim.json')]
                need(tag in allowed and tag in intents and intents[tag]['method']=='own.uploads.execute')
                claim=self._namespace_aux(name,available_raw_bytes)
                need(set(claim)=={'schema','profile','authority','resume_id','child_ordinal',
                    'original_phase_sha256','original_tag','intent_sha256','arguments_sha256'}
                    and type(claim['schema']) is int and claim['schema']==1
                    and claim['profile']=='PREUPLOAD_ORIGINAL_SLOT_CLAIM_V1' and claim['authority'] is False
                    and type(claim['child_ordinal']) is int and 1<=claim['child_ordinal']<=child_ordinal
                    and type(claim['resume_id']) is str
                    and re.fullmatch(r'preupload-resume-[0-9a-f]{32}',claim['resume_id']) is not None
                    and claim['original_phase_sha256']==self.phase_sha and claim['original_tag']==tag
                    and claim['intent_sha256']==intents[tag]['raw_sha256']
                    and claim['arguments_sha256']==sha256(canonical(allowed[tag]).encode()).hexdigest())
                active=[reservation for reservation,record in tuple(_RESERVATIONS.items())
                    if record[0] is self and record[2]==tag]
                if active:
                    need(len(active)==1 and claim['resume_id']==self.resume_id
                         and claim['child_ordinal']==self.child_ordinal)
                    self.require(active[0],tag,allowed[tag])
                else:
                    terminal_name=tag+'-preupload-terminal.json'
                    need(terminal_name in names)
                    terminal=self._namespace_aux(terminal_name,available_raw_bytes)
                    result=self._namespace_aux(tag+'-result.json',available_raw_bytes)
                    need(set(terminal)=={'schema','profile','authority','resume_id','child_ordinal','original_tag',
                        'state','result_sha256','proof_facts_sha256','replay_allowed'}
                        and type(terminal['schema']) is int and terminal['schema']==1
                        and terminal['profile']=='PREUPLOAD_ORIGINAL_SLOT_TERMINAL_V1'
                        and terminal['authority'] is False and terminal['resume_id']==claim['resume_id']
                        and type(terminal['child_ordinal']) is int
                        and terminal['child_ordinal']==claim['child_ordinal'] and terminal['original_tag']==tag
                        and terminal['state']=='SDK_SUCCEEDED_INDEPENDENT_READ_MATCHED'
                        and terminal['replay_allowed'] is False and type(terminal['proof_facts_sha256']) is str
                        and _HASH.fullmatch(terminal['proof_facts_sha256']) is not None
                        and terminal['result_sha256']==sha256(self.namespace_aux_cache[tag+'-result.json'][1]).hexdigest()
                        and type(result) is dict and set(result)=={'isError','value'} and result['isError'] is False
                        and type(result['value']) is dict and result['value']['state']=='SUCCEEDED'
                        and result['value']['request_key']==allowed[tag]['request_key']
                        and result['value']['slot']==allowed[tag]['slot'])
            elif name.endswith('-preupload-terminal.json'):
                need(name[:-len('-preupload-terminal.json')]+'-preupload-claim.json' in names)
        need(set(names)==set(os.listdir(self.parent)))
        for name,(pin,_) in self.namespace_cache.items():
            need(name in names and full(os.stat(name,dir_fd=self.parent,follow_symlinks=False))==pin)
        for name,(pin,_) in self.namespace_aux_cache.items():
            need(name in names and full(os.stat(name,dir_fd=self.parent,follow_symlinks=False))==pin)
        self.check()

    def _namespace_aux(self,name,available_raw_bytes):
        """Exact immutable small project claim/result, not an SDK proof reader."""
        self.check()
        info=os.stat(name,dir_fd=self.parent,follow_symlinks=False);pin=full(info)
        need(stat.S_ISREG(info.st_mode) and info.st_uid==os.getuid() and info.st_nlink==1
             and stat.S_IMODE(info.st_mode)==0o600 and 0<info.st_size<=16384)
        cached=self.namespace_aux_cache.get(name)
        if cached is not None:
            need(cached[0]==pin);raw=cached[1]
        else:
            need(self.namespace_bytes+info.st_size<=available_raw_bytes)
            capacity(1,persistent=True)
            fd=os.open(name,os.O_RDONLY|os.O_NOFOLLOW|os.O_NONBLOCK,dir_fd=self.parent)
            original=None
            try:
                need(full(os.fstat(fd))==pin)
                raw=os.pread(fd,info.st_size+1,0)
                need(len(raw)==info.st_size and full(os.fstat(fd))==pin
                     ==full(os.stat(name,dir_fd=self.parent,follow_symlinks=False)))
            except BaseException as error:original=error;raise
            finally:close_all([lambda:os.close(fd)],original)
            self.namespace_aux_cache[name]=(pin,raw);self.namespace_bytes+=len(raw)
        try:
            from .own_preupload_qa import _pairs
            return json.loads(raw.decode('utf-8'),object_pairs_hook=_pairs,parse_constant=lambda _:need(False))
        except (ValueError,UnicodeError,RecursionError):
            raise WCEError('PREUPLOAD_ORIGINAL_ONCE_HOLD') from None

    def _create(self, leaf, value):
        self.check()
        raw = (canonical(value)+'\n').encode('utf-8')
        need(0 < len(raw) <= 16384)
        capacity(1, persistent=True)  # Held through the live reservation.
        fd = os.open(leaf, os.O_RDWR | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600, dir_fd=self.parent)
        try:
            remaining = memoryview(raw)
            while remaining:
                amount = os.write(fd, remaining)
                need(amount > 0)
                remaining = remaining[amount:]
            os.fsync(fd)
            os.fsync(self.parent)
            self.check()
            pin = full(os.fstat(fd))
            need(pin == full(os.stat(leaf, dir_fd=self.parent, follow_symlinks=False)))
            return fd, pin, raw
        except BaseException as original:
            close_all([lambda:os.close(fd)], original)
            raise  # Never unlink or refund the already-created once leaf.

    def reserve(self, tag, arguments):
        """Preconsume original intent first, then its exact technical claim."""
        self.check(); self._tag(tag)
        from .own_connection_tools import validate
        # Snapshot once before IO can release the GIL. Intent, claim and live
        # registry must describe the same tuple even if the caller mutates.
        arguments_raw = canonical(arguments)
        detached = json.loads(arguments_raw)
        validate('own.uploads.execute', detached)
        need(not self.attempted(tag))
        intent = {'state':'RESERVED_NO_REPLAY', 'method':'own.uploads.execute',
                  'arguments':detached, 'binding_sha256':self.binding_sha}
        records = []
        reservation = None
        try:
            records.append(self._create(tag+'-intent.json', intent))
            claim = {'schema':1, 'profile':'PREUPLOAD_ORIGINAL_SLOT_CLAIM_V1', 'authority':False,
                'resume_id':self.resume_id, 'child_ordinal':self.child_ordinal,
                'original_phase_sha256':self.phase_sha, 'original_tag':tag,
                'intent_sha256':sha256(records[0][2]).hexdigest(),
                'arguments_sha256':sha256(arguments_raw.encode()).hexdigest()}
            records.append(self._create(tag+'-preupload-claim.json', claim))
            reservation = object.__new__(OriginalSlotReservation)
            _RESERVATIONS[reservation] = (self, self.owner, tag,
                arguments_raw, tuple(records))
            self.reservations.append(reservation)
            self.require(reservation, tag, detached)
            return reservation
        except BaseException as original:
            # The final fence may fail after registration. Remove its live
            # exception before closing FDs, so outer close cannot close a
            # subsequently reused descriptor number a second time.
            if reservation is not None:
                _RESERVATIONS.pop(reservation, None)
                if reservation in self.reservations:
                    self.reservations.remove(reservation)
            close_all([lambda fd=record[0]:os.close(fd) for record in records], original)
            raise

    def require(self, reservation, tag, arguments):
        self.check()
        need(type(reservation) is OriginalSlotReservation)
        record = _RESERVATIONS.get(reservation)
        need(record is not None and record[0] is self and record[1] == self.owner
             and record[2] == tag and record[3] == canonical(arguments)
             and reservation in self.reservations)
        for suffix, (fd, pin, raw) in zip(('-intent.json', '-preupload-claim.json'), record[4]):
            need(full(os.fstat(fd)) == pin
                 == full(os.stat(tag+suffix, dir_fd=self.parent, follow_symlinks=False))
                 and os.pread(fd, len(raw)+1, 0) == raw)
        return True

    def revoke(self, reservation, *, original=None):
        record = _RESERVATIONS.get(reservation)
        need(record is not None and record[0] is self)
        _RESERVATIONS.pop(reservation)
        self.reservations.remove(reservation)
        close_all([lambda fd=item[0]:os.close(fd) for item in record[4]], original)

    def record_known_success(self,reservation,tag,arguments,value,*,proof_facts_sha256):
        """Audit only after the actual normal SDK and independent current read.

        These files never replace that read/proof on a future request. Archive
        failure remains spent and does not call the SDK again.
        """
        self.require(reservation,tag,arguments)
        need(type(value) is dict and value.get('state')=='SUCCEEDED'
             and value.get('request_key')==arguments['request_key']
             and value.get('slot')==arguments['slot']
             and type(proof_facts_sha256) is str and _HASH.fullmatch(proof_facts_sha256) is not None)
        response={'isError':False,'value':json.loads(canonical(value))}
        fd,pin,raw=self._create(tag+'-result.json',response)
        original=None
        try:
            self.require(reservation,tag,arguments)
            need(full(os.fstat(fd))==pin
                 ==full(os.stat(tag+'-result.json',dir_fd=self.parent,follow_symlinks=False)))
        except BaseException as error:original=error;raise
        finally:close_all([lambda:os.close(fd)],original)
        result_sha=sha256(raw).hexdigest()
        fd,pin,raw=self._create(tag+'-preupload-terminal.json',{
            'schema':1,'profile':'PREUPLOAD_ORIGINAL_SLOT_TERMINAL_V1','authority':False,
            'resume_id':self.resume_id,'child_ordinal':self.child_ordinal,'original_tag':tag,
            'state':'SDK_SUCCEEDED_INDEPENDENT_READ_MATCHED','result_sha256':result_sha,
            'proof_facts_sha256':proof_facts_sha256,'replay_allowed':False})
        original=None
        try:self.require(reservation,tag,arguments)
        except BaseException as error:original=error;raise
        finally:close_all([lambda:os.close(fd)],original)

    def close(self, *, original=None):
        callbacks = []
        for reservation in tuple(self.reservations):
            callbacks.append(lambda reservation=reservation:self.revoke(reservation, original=original))
        # Revoke live exceptions before the lock and directory leave scope.
        callbacks.append(lambda:setattr(self, 'active', False))
        if self.lock_fd is not None:
            callbacks.append(lambda:self.lock_scope.__exit__(None, None, None))
            self.lock_fd = None
        if self.parent is not None:
            fd, self.parent = self.parent, None
            callbacks.append(lambda:os.close(fd))
        close_all(callbacks, original)

    def __exit__(self, kind, value, traceback):
        self.close(original=value)
        return False
