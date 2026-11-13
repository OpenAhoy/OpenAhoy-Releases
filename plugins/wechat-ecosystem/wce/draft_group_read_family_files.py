"""Fixed shared-account family files; four roles, no account/head access."""
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass,field
from hashlib import sha256
from pathlib import Path
import os,threading,re
from .contracts import WCEError
from .bounded_file import identity
from .own_bootstrap_security import path_check,private_read
from .own_connection_policy import ConnectionPolicy
from .publication_contract import stable_account,binding as publication_binding
from .publication_store import PublicationStore
from .publication_lock import _marker,verify_pin,_writer_guard
from .draft_group_input_files import _FixedFileIO,_hash,_maybe,_canonical,_plain,_int,_pin,hold
from . import draft_group_read_family_values as values

FOLDER='group-read-families'
PREFIX={'covenant':'covenant-','first_proof':'first-proof-','family_root':'family-','request_witness':'request-'}
ORDER=('request_witness','covenant','first_proof','family_root')
_WRITE=ContextVar('family_actual_writer_fd_scope',default=None)
_OBSERVATIONS=ContextVar('family_same_operation_original_file_pins',default=None)

@dataclass(frozen=True,slots=True)
class FamilyEvidence:
    role:str;key:str;sha256:str;size:int;raw:bytes=field(repr=False)
    @property
    def authority(self):return False
    @property
    def value(self):return values.decode(self.role,self.raw)

@dataclass(frozen=True,slots=True)
class FirstFiles:
    # Immutable bytes are facts, never source/grant authority.
    entries:tuple=field(repr=False)
    @property
    def authority(self):return False
    def entry(self,role):
        if type(role) is not str or type(self.entries) is not tuple or any(type(x) is not FamilyEvidence or type(x.role) is not str for x in self.entries):hold()
        found=[x for x in self.entries if x.role==role]
        if len(found)!=1:hold()
        return found[0]

class FamilyFiles(_FixedFileIO):
    def __init__(self,policy,guard):
        if type(policy) is not ConnectionPolicy:hold()
        _plain(policy.value)
        if type(policy.value) is not dict:hold()
        registry=policy.value.get('registry_path')
        if type(registry) is not str or not Path(registry).is_absolute() or Path(registry).name!='connections.json':hold()
        self.registry=Path(registry);self.publication=PublicationStore(policy,self.registry)
        self.anchor=self.publication.anchor;self.anchor_pin=path_check(self.anchor,True)
        self.parent_pin=path_check(self.registry.parent,True)
        self.registry_pin=path_check(self.registry)
        verify_pin(self.publication,required=True)
        marker=_marker(policy.root,policy.data['appid'])
        if marker is None or marker['anchor']!=str(self.anchor):hold()
        self.coord_raw=private_read(policy.root/'publication-coordination.json')[0]
        self.coord_pin=path_check(policy.root/'publication-coordination.json')
        self.head_raw=private_read(self.anchor/'head.json')[0]
        self.head_pin=path_check(self.anchor/'head.json')
        self.publication._head(allow_pending=False)
        super().__init__(policy,guard)

    def _pure_scope(self):
        if (path_check(self.registry.parent,True)!=self.parent_pin or path_check(self.registry)!=self.registry_pin
            or path_check(self.anchor,True)!=self.anchor_pin
            or self.anchor!=self.registry.parent/'publication-anchors'/stable_account(self.policy.data)
            or private_read(self.root/'publication-coordination.json')[0]!=self.coord_raw
            or path_check(self.root/'publication-coordination.json')!=self.coord_pin
            or private_read(self.anchor/'head.json')[0]!=self.head_raw
            or path_check(self.anchor/'head.json')!=self.head_pin):hold('GROUP_FAMILY_COORDINATION_CHANGED')
        self.publication._head(allow_pending=False)

    def _guard(self):
        super()._guard();self._pure_scope()
        scope=_WRITE.get()
        if scope is not None:
            if scope[0] is not self:hold()
            scope[1]()
    @contextmanager
    def _writing(self):
        held=_writer_guard(self.root,self.policy.data['appid']);held()
        token=_WRITE.set((self,held))
        try:yield;held()
        finally:_WRITE.reset(token)

    @contextmanager
    def _observing(self):
        # Retain the first observed inode/content tuple for the entire operation.
        # This context is integrity only; it never qualifies or authorizes input.
        prior=_OBSERVATIONS.get()
        if prior is not None and prior[0] is self:
            if prior[1]!=threading.get_ident():hold()
            yield
            self._pure_entries([(role,key,pin) for (role,key),pin in prior[2].items()])
            return
        current=(self,threading.get_ident(),{})
        token=_OBSERVATIONS.set(current)
        try:
            yield
            # Pure collective fence after the last external guard/reader callback.
            self._pure_entries([(role,key,pin) for (role,key),pin in current[2].items()])
        finally:_OBSERVATIONS.reset(token)
    def _record_pin(self,role,key,pin):
        current=_OBSERVATIONS.get()
        if current is None:return
        if current[0] is not self or current[1]!=threading.get_ident():hold()
        previous=current[2].setdefault((role,key),pin)
        if previous!=pin:hold('GROUP_FAMILY_FILE_CHANGED')
    def _entry(self,role,key,*,expected_sha=None):
        evidence,pin=super()._entry(role,key,expected_sha=expected_sha)
        self._record_pin(role,key,pin)
        return evidence,pin
    def _publish_observed(self,role,value):
        evidence,pin=super()._publish_observed(role,value)
        self._record_pin(evidence.role,evidence.key,pin)
        return evidence,pin

    def _config(self,role):
        if type(role) is not str or role not in values.PROFILES:hold()
        return FOLDER,PREFIX[role],values.PROFILES[role][1],values.PROFILES[role][2]
    def _encode(self,role,value):return values.encode(role,value)
    def _key(self,role,value,checksum):
        return value['family_anchor_id'] if role=='family_root' else value['request_identity_sha'] if role=='request_witness' else checksum
    def _allowed_directories(self):return (FOLDER,)
    def _base_path(self,name):
        if name!=FOLDER:hold()
        return self.anchor
    def _base_identity(self,name):
        if name!=FOLDER:hold()
        return self.anchor_pin
    def _evidence(self,role,key,raw,expected_sha=None):
        self._config(role);_hash(key);_maybe(expected_sha,_hash)
        value=values.decode(role,raw);actual=sha256(raw).hexdigest()
        if key!=self._key(role,value,actual) or expected_sha is not None and actual!=expected_sha:hold()
        return FamilyEvidence(role,key,actual,len(raw),raw)
    def _pure_entries(self,entries,head_pin=False):
        if head_pin is not False:hold()
        self._pure_scope();super()._pure_entries(entries);self._pure_scope()
    def initialize(self):
        # Real stable+local writer FD is required, never a boolean substitute.
        with self._writing():
            with self._directory(FOLDER,create=True):pass
    def optional(self,role,key,*,expected_sha=None):
        folder,name=self._name(role,key);directory=self.anchor/folder
        self._guard();self._pure_scope()
        if not os.path.lexists(directory):
            self._guard();self._pure_scope()
            if os.path.lexists(directory):hold()
            return None
        with self._directory(folder) as (fd,fence):
            observed=self._read_at(fd,name,fence,self._config(role)[3],missing=True,with_pin=True)
            if observed is None:return None
            raw,pin=observed;self._record_pin(role,key,pin)
            return self._evidence(role,key,raw,expected_sha)
    def _absence_inventory(self,request_identity_sha):
        # Only the fixed four-role domain is examined. A missing W cannot hide
        # its already-published C/P/R before SQL FIRST. Bounds are fail-closed
        # operational limits, not request- or caller-controlled permissions.
        _hash(request_identity_sha);self._guard();directory=self.anchor/FOLDER
        if not os.path.lexists(directory):
            self._guard();snapshot=('MISSING',None);self._pure_absence(snapshot);return snapshot
        with self._directory(FOLDER) as (fd,fence):
            before=_pin(os.fstat(fd));self._guard();fence();names=os.listdir(fd)
            if len(names)>4096:hold('GROUP_FAMILY_INVENTORY_LIMIT')
            total=0
            for name in sorted(names):
                if type(name) is not str:hold()
                matches=[(role,prefix) for role,prefix in PREFIX.items() if re.fullmatch(re.escape(prefix)+r'[0-9a-f]{64}\.json',name)]
                if len(matches)!=1:hold('GROUP_FAMILY_INVENTORY_UNVERIFIED')
                role,prefix=matches[0];key=name[len(prefix):-5]
                info=os.stat(name,dir_fd=fd,follow_symlinks=False);total+=info.st_size
                if total>64*1024*1024:hold('GROUP_FAMILY_INVENTORY_LIMIT')
                raw,pin=self._read_at(fd,name,fence,self._config(role)[3],with_pin=True)
                e=self._evidence(role,key,raw);self._record_pin(role,key,pin)
                if e.value['request_identity_sha']==request_identity_sha:hold('GROUP_FAMILY_WITNESS_MISSING')
            self._guard();fence()
            if _pin(os.fstat(fd))!=before:hold('GROUP_FAMILY_INVENTORY_CHANGED')
            snapshot=('DIRECTORY',before);self._pure_absence(snapshot);return snapshot
    def _pure_absence(self,snapshot):
        # No callback. The caller invokes this after its final current guard.
        self._pure_scope();directory=self.anchor/FOLDER
        if snapshot[0]=='MISSING':
            if os.path.lexists(directory):hold('GROUP_FAMILY_INVENTORY_CHANGED')
        else:
            try:
                path_check(directory,True)
                if _pin(directory.lstat())!=snapshot[1]:hold('GROUP_FAMILY_INVENTORY_CHANGED')
            except OSError:hold()

    def publish(self,role,value):
        with self._writing():return super().publish(role,value)


def validate_pack(pack):
    if type(pack) is not FirstFiles or type(pack.entries) is not tuple or len(pack.entries)!=4 or any(type(x) is not FamilyEvidence for x in pack.entries):hold()
    for x in pack.entries:
        if type(x.role) is not str or x.role not in ORDER or type(x.raw) is not bytes:hold()
        _hash(x.key);_hash(x.sha256);_int(x.size,1,2*1024*1024)
    found={x.role:x for x in pack.entries}
    if set(found)!=set(ORDER):hold()
    for x in found.values():
        checked=values.decode(x.role,x.raw)
        if sha256(x.raw).hexdigest()!=x.sha256 or len(x.raw)!=x.size:hold()
        expected=checked['family_anchor_id'] if x.role=='family_root' else checked['request_identity_sha'] if x.role=='request_witness' else x.sha256
        if expected!=x.key:hold()
    w,c,p,r=(found[x].value for x in ORDER)
    if (w['first_covenant_sha']!=found['covenant'].sha256 or w['first_proof_sha']!=found['first_proof'].sha256
        or w['family_root_sha']!=found['family_root'].sha256 or r['first_covenant_sha']!=found['covenant'].sha256
        or r['first_proof_sha']!=found['first_proof'].sha256 or p['covenant_sha']!=found['covenant'].sha256):hold()
    if len({x['family_anchor_id'] for x in (w,c,p,r)})!=1 or len({x['request_identity_sha'] for x in (w,c,p,r)})!=1:hold()
    for field in ('first_binding','first_directory','coordination'):
        if _canonical(p[field])!=_canonical(r[field]):hold()
    from . import draft_group_operator_source_codec as operator
    if r['profile']==operator.FAMILY_ROOT_PROFILE:
        try:operator.validate_first_pack(r['anchor'],p,w,r,covenant_sha=found['covenant'].sha256)
        except operator.OperatorSourceCodecError:hold('GROUP_OPERATOR_FIRST_PACK')
    else:
        primary={k:r['anchor']['original_human_request_refs'][0][k] for k in ('thread_id','turn_id','message_id')}
        if _canonical(w['primary_human'])!=_canonical(primary):hold()
    if (_canonical(c['stable_owner'])!=_canonical(r['anchor']['stable_owner'])
        or c['platform_account_sha']!=w['platform_account_sha'] or r['coordination']['platform_account_sha']!=w['platform_account_sha']
        or stable_account({'appid':r['first_binding']['account']})!=w['platform_account_sha']
        or r['first_binding']['tenant']!=c['stable_owner']['tenant'] or r['first_binding']['principal']!=c['stable_owner']['principal']):hold()
    return pack


def proposed_pack(anchor,covenant,proof):
    # Pure non-authority construction; a host's actual source qualifier is separate.
    c=values.validate('covenant',covenant);p=values.validate('first_proof',proof)
    family=values.family_anchor(anchor)
    from . import draft_group_operator_source_codec as operator
    is_operator=anchor.get('profile')==operator.ANCHOR_PROFILE
    if is_operator and p['profile']!=operator.FIRST_PROOF_PROFILE:hold('GROUP_OPERATOR_FIRST_PACK')
    if not is_operator and p['profile']!=values.PROFILES['first_proof'][1]:hold()
    r={'schema':1,'profile':operator.FAMILY_ROOT_PROFILE if is_operator else values.PROFILES['family_root'][1],'authority':False,'family_anchor_id':family,'request_identity_sha':anchor['request_identity_sha'],'anchor':anchor,'first_covenant_sha':values.file_sha('covenant',c),'first_proof_sha':values.file_sha('first_proof',p),'first_binding':p['first_binding'],'first_directory':p['first_directory'],'coordination':p['coordination']}
    if is_operator:r['content_source_type']=operator.CONTENT_SOURCE_TYPE
    w={'schema':1,'profile':operator.REQUEST_WITNESS_PROFILE if is_operator else values.PROFILES['request_witness'][1],'authority':False,'request_identity_sha':anchor['request_identity_sha'],'platform_account_sha':anchor['platform_account_sha'],'family_anchor_id':family,'family_root_sha':values.file_sha('family_root',r),'first_covenant_sha':r['first_covenant_sha'],'first_proof_sha':r['first_proof_sha']}
    if is_operator:
        w['content_source_type']=operator.CONTENT_SOURCE_TYPE
        w.update({key:anchor[key] for key in operator.REQUEST_FIELDS})
    else:w['primary_human']={k:anchor['original_human_request_refs'][0][k] for k in ('thread_id','turn_id','message_id')}
    out=[]
    for role,v in zip(ORDER,(w,c,p,r)):
        raw=values.encode(role,v);checksum=sha256(raw).hexdigest();key=v['family_anchor_id'] if role=='family_root' else v['request_identity_sha'] if role=='request_witness' else checksum
        out.append(FamilyEvidence(role,key,checksum,len(raw),raw))
    return validate_pack(FirstFiles(tuple(out)))


def _prepare_first_files(files,pack,*,root_closure,db):
    # No root/authority flag can stand in for the actual same-snapshot closure.
    from .draft_group_read_family_store import require_closure,check_pack_origin
    if type(files) is not FamilyFiles:hold()
    validate_pack(pack);require_closure(root_closure,db,files);check_pack_origin(pack,root_closure)
    files.initialize();pins=[]
    for e in pack.entries:
        # W first, then only its original precomputed dependency bytes.
        with files._writing():actual,pin=files._publish_observed(e.role,e.value)
        if actual.raw!=e.raw:hold()
        pins.append((e.role,e.key,pin))
    files._pure_entries(pins);require_closure(root_closure,db,files)
    return pack


def _read_first_files(files,request_identity_sha):
    if type(files) is not FamilyFiles:hold()
    w,wp=files._entry('request_witness',request_identity_sha);v=w.value
    c,cp=files._entry('covenant',v['first_covenant_sha']);p,pp=files._entry('first_proof',v['first_proof_sha']);r,rp=files._entry('family_root',v['family_anchor_id'],expected_sha=v['family_root_sha'])
    files._pure_entries([(e.role,e.key,pin) for e,pin in ((w,wp),(c,cp),(p,pp),(r,rp))])
    return validate_pack(FirstFiles((w,c,p,r)))


def prepare_first_files(files,pack,*,root_closure,db):
    if type(files) is not FamilyFiles:hold()
    with files._observing():return _prepare_first_files(files,pack,root_closure=root_closure,db=db)


def read_first_files(files,request_identity_sha):
    if type(files) is not FamilyFiles:hold()
    with files._observing():return _read_first_files(files,request_identity_sha)
