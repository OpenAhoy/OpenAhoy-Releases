"""Two fixed claim-key Group roles over the reviewed shared FD IO leaf.

Identity evidence never grants current/source/network authority. Same-round
first pins are collective and sticky; restart proves content, not old inodes.
"""
from dataclasses import dataclass,field
from hashlib import sha256
import os
from .draft_group_input_files import _FixedFileIO,_hash,_pin,_plain,_binding
from . import draft_group_response_codec as codec
from .contracts import WCEError

ROLES={
    'group_response':('group-proofs','group-response-',codec.PROFILE,16384),
    'group_response_snapshot':('group-proofs','group-response-snapshot-','GROUP_RESPONSE_SNAPSHOT_BYTES_V1',codec.MAX_BODY),
}
_LOCATORS={}
_PACKS={}


def fail():raise WCEError('GROUP_RESPONSE_FILE_HOLD')


@dataclass(frozen=True,slots=True)
class OriginalClaimLocator:
    account_key: str
    claim_id: str
    admission_json: str = field(repr=False)
    context_json: str = field(repr=False)
    binding_json: str = field(repr=False)
    claim_at_ms: int
    expected_proof_sha: str|None
    expected_projection_sha: str|None
    reference: str|None = field(repr=False)
    list_offset: int|None
    authority: bool=False


def _register_locator(locator,db):
    # Only fixed history replay calls this after matching the actual event.
    from .own_validation_scope import OwnedConnection
    if type(db) is not OwnedConnection or not db.in_transaction:fail()
    if type(locator) is not OriginalClaimLocator or locator.authority is not False:fail()
    _hash(locator.account_key);_hash(locator.claim_id)
    _LOCATORS[id(locator)]=(locator,db,__import__('threading').get_ident())
    return locator


def _validate_locator(locator):
    import threading
    record=_LOCATORS.get(id(locator))
    if record is None or record[0] is not locator or record[2]!=threading.get_ident():fail()
    return locator


@dataclass(frozen=True,slots=True)
class GroupResponseEvidence:
    role: str
    key: str
    sha256: str
    size: int
    raw: bytes=field(repr=False)
    authority: bool=False
    expected_projection_sha: str|None=None
    @property
    def value(self):
        if self.role!='group_response':fail()
        return codec.decode_primary(self.raw,expected_projection_sha=self.expected_projection_sha)


class ArrivedPack:
    __slots__=('locator','primary_raw','snapshot_raw','primary_sha')
    def __repr__(self):return '<GroupArrivedPack>'


def _issue_arrived_pack(locator,primary,snapshot_raw,arrival,expected_prepared,expected_pending):
    _validate_locator(locator)
    from .draft_group_transport import validate_arrival_for_archive
    validate_arrival_for_archive(arrival,primary,expected_prepared,expected_pending)
    raw=codec.encode_primary(primary,claim_at_ms=locator.claim_at_ms,expected_projection_sha=locator.expected_projection_sha)
    if snapshot_raw is not None:
        codec.read_snapshot(snapshot_raw,primary,reference=locator.reference,list_offset=locator.list_offset)
    elif primary['observation']['snapshot_file_sha'] is not None:fail()
    pack=ArrivedPack();pack.locator=locator;pack.primary_raw=raw;pack.snapshot_raw=snapshot_raw;pack.primary_sha=sha256(raw).hexdigest()
    _PACKS[id(pack)]=(pack,raw,snapshot_raw,pack.primary_sha)
    return pack


def _validate_pack(pack):
    record=_PACKS.get(id(pack))
    if (record is None or record[0] is not pack or pack.primary_raw!=record[1]
            or pack.snapshot_raw!=record[2] or pack.primary_sha!=record[3]):fail()
    return _validate_locator(pack.locator)


class GroupResponseFiles(_FixedFileIO):
    def __init__(self,policy,context):
        from .draft_group_response_history import GroupReplayFileContext,validate_replay_file_context
        if type(context) is GroupReplayFileContext:validate_replay_file_context(policy,context)
        else:
            from .draft_group_runtime_host import validate_history_context
            validate_history_context(policy,context)
        self._history_context=context
        self._round_pins={};self._primary_checked={};self._locators={};self._poisoned=False;self._aux_pins={}
        super().__init__(policy,self._fixed_history_guard)

    @classmethod
    def from_history_context(cls,actual_history_policy,actual_writer_context):
        return cls(actual_history_policy,actual_writer_context)

    def _fixed_history_guard(self):
        if self._poisoned:fail()
        from .draft_group_read_family_store import _history_file_guard
        from .draft_group_response_history import GroupReplayFileContext,validate_replay_file_context
        _history_file_guard(self.policy)
        if type(self._history_context) is GroupReplayFileContext:validate_replay_file_context(self.policy,self._history_context)
        else:
            from .draft_group_runtime_host import validate_history_context
            validate_history_context(self.policy,self._history_context)

    def _config(self,role):
        if type(role) is not str or role not in ROLES:fail()
        return ROLES[role]

    def _allowed_directories(self):return ('group-proofs',)
    def initialize(self):
        with self._directory('group-proofs',create=True):pass

    def _remember(self,role,key,pin):
        previous=self._round_pins.get((role,key))
        if previous is not None and previous!=pin:
            self._poisoned=True;fail()
        self._round_pins[(role,key)]=pin

    def _evidence(self,role,key,raw,expected_sha=None):
        self._config(role);_hash(key)
        if expected_sha is not None:_hash(expected_sha)
        locator=self._locators.get(key)
        if locator is None:fail()
        _validate_locator(locator)
        checksum=sha256(raw).hexdigest()
        if expected_sha is not None and checksum!=expected_sha:fail()
        if role=='group_response':
            primary=codec.decode_primary(raw,claim_at_ms=locator.claim_at_ms,expected_projection_sha=locator.expected_projection_sha)
            a=primary['admission'];c=primary['archive_context']
            from .draft_group_wire import canonical
            if (a['claim_id']!=key or canonical(a)!=locator.admission_json
                    or canonical(c)!=locator.context_json or canonical(primary['binding'])!=locator.binding_json):fail()
            self._primary_checked[key]=primary
        else:
            primary=self._primary_checked.get(key)
            if primary is None:fail()
            codec.read_snapshot(raw,primary,reference=locator.reference,list_offset=locator.list_offset)
        return GroupResponseEvidence(role,key,checksum,len(raw),raw,False,locator.expected_projection_sha)

    def _entry(self,role,key,*,expected_sha=None):
        evidence,pin=super()._entry(role,key,expected_sha=expected_sha)
        self._remember(role,key,pin)
        return evidence,pin

    def _bind(self,locator):
        _validate_locator(locator)
        existing=self._locators.get(locator.claim_id)
        if existing is not None and existing!=locator:fail()
        self._locators[locator.claim_id]=locator

    def publish_snapshot(self,arrived_pack):
        loc=_validate_pack(arrived_pack);self._bind(loc)
        # Validate primary in memory first, but it is not considered durable.
        self._evidence('group_response',loc.claim_id,arrived_pack.primary_raw,arrived_pack.primary_sha)
        if arrived_pack.snapshot_raw is None:return None
        raw=arrived_pack.snapshot_raw
        evidence,pin=self._publish_bytes_observed('group_response_snapshot',loc.claim_id,raw,sha256(raw).hexdigest())
        self._remember('group_response_snapshot',loc.claim_id,pin)
        self.collective_fence()
        return evidence

    def publish_primary(self,arrived_pack):
        loc=_validate_pack(arrived_pack);self._bind(loc)
        if arrived_pack.snapshot_raw is not None:
            # Must already have been durably published and independently read.
            primary=codec.decode_primary(arrived_pack.primary_raw,claim_at_ms=loc.claim_at_ms,expected_projection_sha=loc.expected_projection_sha)
            self._primary_checked[loc.claim_id]=primary
            self._entry('group_response_snapshot',loc.claim_id,expected_sha=primary['observation']['snapshot_file_sha'])
        evidence,pin=self._publish_bytes_observed('group_response',loc.claim_id,arrived_pack.primary_raw,arrived_pack.primary_sha)
        self._remember('group_response',loc.claim_id,pin);self.collective_fence()
        return evidence

    def read_primary(self,original_claim_locator,*,expected_proof_sha=None):
        self._bind(original_claim_locator)
        expected=original_claim_locator.expected_proof_sha
        if expected is not None and expected_proof_sha not in (None,expected):fail()
        return self._entry('group_response',original_claim_locator.claim_id,expected_sha=expected or expected_proof_sha)[0]

    def read_snapshot(self,original_claim_locator,checked_primary):
        self._bind(original_claim_locator)
        if type(checked_primary) is not GroupResponseEvidence or checked_primary.role!='group_response' or checked_primary.key!=original_claim_locator.claim_id:fail()
        primary=self._evidence('group_response',checked_primary.key,checked_primary.raw,checked_primary.sha256).value
        if primary['observation']['snapshot_file_sha'] is None:return None
        return self._entry('group_response_snapshot',original_claim_locator.claim_id,expected_sha=primary['observation']['snapshot_file_sha'])[0]

    def redurable_original(self,locator,checked_primary,checked_snapshot):
        self._bind(locator)
        for evidence in (checked_snapshot,checked_primary):
            if evidence is None:continue
            if type(evidence) is not GroupResponseEvidence or evidence.key!=locator.claim_id:fail()
            folder,name=self._name(evidence.role,evidence.key)
            with self._directory(folder) as (fd,fence):
                pin=self._confirm_at(fd,name,fence,evidence.raw,self._config(evidence.role)[3])
                self._remember(evidence.role,evidence.key,pin)
                if self._read_at(fd,name,fence,self._config(evidence.role)[3])!=evidence.raw:fail()
            self.collective_fence()
        return None

    def _remember_own_archive_file(self,row,name,pin):
        from .own_response_archive import filename
        from .own_bootstrap_security import path_check
        allowed=(filename(row),'response-index-'+row['id']+'-'+row['owner']+'.json')
        if name not in allowed:fail()
        if not hasattr(self,'_aux_pins'):self._aux_pins={}
        previous=self._aux_pins.get(name)
        if previous is not None and previous!=pin:self._poisoned=True;fail()
        self._aux_pins[name]=pin
        if path_check(self.root/name)!=pin:self._poisoned=True;fail()

    def collective_fence(self):
        self._fixed_history_guard()
        try:
            self._pure_entries(tuple((role,key,pin) for (role,key),pin in self._round_pins.items()))
            from .own_bootstrap_security import path_check
            for name,pin in getattr(self,'_aux_pins',{}).items():
                if path_check(self.root/name)!=pin:fail()
        except Exception:
            self._poisoned=True;raise

    def query_original(self,original_claim_locator):
        self._bind(original_claim_locator)
        try:
            role='group_response';folder,name=self._name(role,original_claim_locator.claim_id)
            with self._directory(folder) as (fd,fence):
                raw=self._read_at(fd,name,fence,self._config(role)[3],missing=True)
                if raw is None:return {'state':'ABSENT','authority':False}
            evidence=self.read_primary(original_claim_locator)
            self.read_snapshot(original_claim_locator,evidence);self.collective_fence()
            return {'state':'COMMITTED','proof_sha':evidence.sha256,'authority':False}
        except (WCEError,OSError,ValueError):return {'state':'UNDETERMINED','authority':False}
