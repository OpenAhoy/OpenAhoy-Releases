"""Private fixed Group input files; integrity evidence, never authority.

No account creation, SQL, native source, grant, token, API or runtime qualified
object exists here. Callers own actual account writer exclusion for mutations.
The supplied guard is invoked, not treated as a proof of locks or permission.
"""
from contextlib import contextmanager
from dataclasses import dataclass, field
from hashlib import sha256
import json
import math
import os
from pathlib import Path
import re
import stat
import time

from .bounded_file import FileSource, file_state, identity, READ_SECONDS, CHUNK_BYTES, MAX_SOURCE_HTML_BYTES, MAX_ASSET_BYTES
from .contracts import WCEError
from .own_bootstrap_security import path_check
from .own_connection_policy import ConnectionPolicy

MAX_TOP=2*1024*1024
MAX_CHILD=512*1024
MAX_HEAD=16*1024
MAX_NODES=131072
MAX_HEAD_CHAIN=4096
_HASH=re.compile(r'[a-f0-9]{64}\Z')
_ID=re.compile(r'[A-Za-z0-9][A-Za-z0-9_.:-]{0,127}\Z')
ROLES={
    'upload_reuse':('group-inputs','reuse-','GROUP_TARGET_UPLOAD_REUSE_MAP_V1',MAX_CHILD),
    'registration':('group-inputs','','GROUP_REGISTERED_BATCH_INPUT_V1',MAX_TOP),
    'source':('group-inputs','source-','GROUP_BATCH_NATIVE_SOURCE_REVIEW_V1',MAX_TOP),
    'execution':('group-inputs','exec-','GROUP_EXECUTION_INPUT_CAPSULE_V1',MAX_TOP),
    'child':('group-inputs','child-','GROUP_EXECUTION_CHILD_V1',MAX_CHILD),
    'proof':('group-proofs','registration-','HOST_VERIFIED_GROUP_REGISTRATION_V1',MAX_TOP),
    'head_history':('group-inputs','head-','GROUP_SELECTED_INPUT_HEAD_V1',MAX_HEAD),
    'reservation':('group-targets','','GROUP_TARGET_RESERVATION_V1',MAX_TOP),
}


def hold(code='GROUP_INPUT_FILE_HOLD'):raise WCEError(code)


def _plain(value):
    remaining=MAX_NODES;stack=[(value,0)]
    while stack:
        item,depth=stack.pop();remaining-=1
        if remaining<0 or depth>40:hold()
        t=type(item)
        if t is dict:
            if len(item)>32768 or any(type(k) is not str for k in item):hold()
            stack.extend((k,depth+1) for k in item)
            stack.extend((v,depth+1) for v in item.values())
        elif t is list:
            if len(item)>32768:hold()
            stack.extend((v,depth+1) for v in item)
        elif t is str:
            if len(item)>MAX_TOP or '\x00' in item:hold()
        elif t is int:
            if not -(2**63)<=item<2**63:hold()
        elif t is float:
            if not math.isfinite(item):hold()
        elif t not in (bool,type(None)):hold()


def _canonical(value):
    _plain(value)
    try:return json.dumps(value,sort_keys=True,separators=(',',':'),ensure_ascii=False,allow_nan=False)
    except (ValueError,UnicodeError,OverflowError,RecursionError):hold()


def _hash(v):
    if type(v) is not str or _HASH.fullmatch(v) is None:hold()
    return v


def _id(v):
    if type(v) is not str or _ID.fullmatch(v) is None:hold()
    return v


def _int(v,lo=0,hi=2**63-1):
    if type(v) is not int or not lo<=v<=hi:hold()
    return v


def _enum(v,choices):
    if type(v) is not str or v not in choices:hold()


def _text(v,maximum=4096):
    if type(v) is not str or not 0<len(v)<=maximum or '\x00' in v:hold()
    try:v.encode('utf-8')
    except UnicodeError:hold()


def _closed(v,keys):
    if type(v) is not dict or any(type(k) is not str for k in v) or set(v)!=set(keys):hold()


def _seq(v,validator,lo=0,hi=64):
    if type(v) is not list or not lo<=len(v)<=hi:hold()
    for x in v:validator(x)


def _maybe(v,validator):
    if v is not None:validator(v)


def _binding(v):
    names=('tenant','principal','client','session','connection','account','resource')
    _closed(v,(*names,'epoch','generation','source_kind'))
    for k in names:_id(v[k])
    _int(v['epoch']);_int(v['generation'],1)
    _enum(v['source_kind'],('SYNTHETIC_SETUP','OPERATOR_ATTESTED'))
    if v['account']!=v['resource']:hold()


def _evidence(v):
    _closed(v,('kind','sha256','size'))
    _enum(v['kind'],('QA','OLD_SAVE','UPLOAD','NATIVE','OPERATOR_SELECTED_SOURCE','ARTIFACT','CHILD','SEMANTIC','METADATA','BUDGET','COVENANT','HELPER_ACCEPTANCE','GENERATION'))
    _hash(v['sha256']);_int(v['size'],1,MAX_TOP)


def _artifact(v):
    _closed(v,('root_sha','relative_path','sha256','size','media_type'))
    _hash(v['root_sha']);_hash(v['sha256'])
    _enum(v['media_type'],('text/html','application/json','image/png','image/jpeg'))
    _int(v['size'],1,MAX_SOURCE_HTML_BYTES if v['media_type']=='text/html' else MAX_ASSET_BYTES)
    _text(v['relative_path'])
    parts=v['relative_path'].split('/')
    if len(parts)>32 or any(x in ('','.','..') for x in parts) or ':' in v['relative_path']:hold()


def _member(v):
    _closed(v,('binding_sha','article_id','version_sha','original_request_sha','source_sha','projection_sha','origin','old_ref_sha','old_position'))
    _id(v['article_id'])
    for k in ('binding_sha','version_sha','original_request_sha','source_sha','projection_sha'):_hash(v[k])
    _enum(v['origin'],('NEW_NOT_SENT','LEGACY_REGISTERED'))
    if v['origin']=='NEW_NOT_SENT':
        if v['old_ref_sha'] is not None or v['old_position'] is not None:hold()
    else:_hash(v['old_ref_sha']);_int(v['old_position'],0,7)


def _selector(v):
    _closed(v,('bundle_id','version','content_digest'))
    _id(v['bundle_id']);_id(v['version']);_hash(v['content_digest'])


def _ref(v):
    _closed(v,('source_id','ordinal','byte_start','byte_end','raw_line_sha256'))
    _id(v['source_id']);_int(v['ordinal']);_int(v['byte_start']);_int(v['byte_end'],1);_hash(v['raw_line_sha256'])
    if v['byte_end']<=v['byte_start']:hold()


def _human(v):
    _closed(v,('thread_id','turn_id','message_id','text_sha256'))
    for k in ('thread_id','turn_id','message_id'):_id(v[k])
    _hash(v['text_sha256'])


def _role_thread(v):
    _closed(v,('role','thread_id','binding_sha'))
    _enum(v['role'],('PRODUCER','COORDINATOR','DEVELOPER'));_id(v['thread_id']);_hash(v['binding_sha'])


def _source_window(v):
    _closed(v,('source_id','thread_id','path_utf8_sha256','device','inode','start_offset','start_ordinal','metadata_ordinal','preceding_sha256','session_meta_sha256','prefix_bytes','prefix_sha256'))
    _id(v['source_id']);_id(v['thread_id'])
    for k in ('device','inode','start_offset','start_ordinal','metadata_ordinal','prefix_bytes'):_int(v[k])
    for k in ('path_utf8_sha256','preceding_sha256','session_meta_sha256','prefix_sha256'):_hash(v[k])
    if v['prefix_bytes']<=v['start_offset'] or v['start_ordinal']<v['metadata_ordinal']:hold()


def _record_binding(v):
    _closed(v,('category','reference','payload_canonical_sha256','safe_projection_sha256'))
    _enum(v['category'],('USER_TYPED','USER_RAW','QA_FACT','ASSISTANT_NON_AUTH','TOOL_NON_AUTH','TASK_CONTROL','CONFIG_NON_AUTH','SESSION_META'))
    _ref(v['reference']);_hash(v['payload_canonical_sha256']);_hash(v['safe_projection_sha256'])


def _pair(v):
    _closed(v,('human','raw','typed','disposition'))
    _human(v['human']);_ref(v['raw']);_ref(v['typed'])
    _enum(v['disposition'],('ORIGINAL_REQUEST','NON_SCOPE_CHANGE','INPUT_FACT','NON_GRANT'))
    if v['raw']['source_id']!=v['typed']['source_id'] or v['raw']['ordinal']>=v['typed']['ordinal']:hold()


def _registration(v,*,unsigned=False):
    keys=('schema','profile','family_id','input_generation','binding','source_material_sha','read_delegation_ids','ordered_members','old_sources','new_sources','qa_evidence','artifacts','previous_registration_sha','scope')
    _closed(v,keys if unsigned else (*keys,'registration_id'))
    _hash(v['family_id']);_int(v['input_generation'],1);_binding(v['binding']);_hash(v['source_material_sha'])
    _seq(v['read_delegation_ids'],_hash,hi=128);_seq(v['ordered_members'],_member,1,64)
    if len({x['article_id'] for x in v['ordered_members']})!=len(v['ordered_members']):hold()
    for k in ('old_sources','new_sources','qa_evidence'):_seq(v[k],_evidence)
    _seq(v['artifacts'],_artifact,hi=3072);_maybe(v['previous_registration_sha'],_hash);_enum(v['scope'],('LOCAL_INPUT',))
    if (v['input_generation']==1)!=(v['previous_registration_sha'] is None):hold()
    if not unsigned:
        _id(v['registration_id'])
        before={k:x for k,x in v.items() if k!='registration_id'}
        if v['registration_id']!='group-registration-'+sha256(_canonical(before).encode()).hexdigest():hold()


def registration_id(unsigned):
    _plain(unsigned);_registration(unsigned,unsigned=True)
    if type(unsigned['schema']) is not int or unsigned['schema']!=1 or type(unsigned['profile']) is not str or unsigned['profile']!=ROLES['registration'][2]:hold()
    return 'group-registration-'+sha256(_canonical(unsigned).encode()).hexdigest()


def _source(v):
    _plain(v)
    if type(v) is dict and (v.get('schema'),v.get('profile'))==(1,'GROUP_BATCH_OPERATOR_SELECTED_SOURCE_V1'):
        from .draft_group_operator_source_codec import validate_source,OperatorSourceCodecError
        try:validate_source(v)
        except OperatorSourceCodecError:hold('GROUP_OPERATOR_SOURCE_CODEC_HOLD')
        return
    if type(v) is dict and (v.get('schema'),v.get('profile'))==(2,'GROUP_BATCH_NATIVE_SOURCE_BASELINE_V2'):
        from .draft_group_native_v2_codec import validate_baseline
        validate_baseline(v)
        return
    _closed(v,('schema','profile','authority','role_threads','original_user_scope','source_windows','retained_bindings','typed_raw_pairs','reviewed_other_records','qa_sources','semantic_scope_sha','allowed_read_scope','expires_policy'))
    if type(v['authority']) is not bool or v['authority'] is not False:hold()
    _seq(v['role_threads'],_role_thread,1,4)
    _closed(v['original_user_scope'],('semantic_scope_sha','human_refs'))
    _hash(v['original_user_scope']['semantic_scope_sha']);_seq(v['original_user_scope']['human_refs'],_human,1,16)
    _seq(v['source_windows'],_source_window,1,4)
    _seq(v['retained_bindings'],_record_binding,hi=16384);_seq(v['typed_raw_pairs'],_pair,hi=1024)
    _seq(v['reviewed_other_records'],_record_binding,hi=16384);_seq(v['qa_sources'],_evidence)
    _hash(v['semantic_scope_sha'])
    if v['semantic_scope_sha']!=v['original_user_scope']['semantic_scope_sha']:hold()
    _closed(v['allowed_read_scope'],('family_anchor_sha','covenant_sha'))
    for x in v['allowed_read_scope'].values():_hash(x)
    _closed(v['expires_policy'],('mode','not_after'));_enum(v['expires_policy']['mode'],('SOURCE_BOUND_CURRENT',))
    _deadline(v['expires_policy']['not_after'])


def _deadline(v):
    if type(v) not in (int,float) or not math.isfinite(v) or v<=0:hold()


def _execution(v):
    _closed(v,('schema','profile','binding','family_id','registration_sha','source_material_sha','preview_core_sha','route_profile','children','old_sources','new_sources','upload_reuse','expected_metadata','read_delegation_ids','execution_budget','artifact_descriptors'))
    _binding(v['binding'])
    for k in ('family_id','registration_sha','source_material_sha','preview_core_sha'):_hash(v[k])
    _enum(v['route_profile'],('CREATE_NEW','REPLACE_SINGLE','MERGE_LEGACY_REFS_V1'))
    _seq(v['children'],_evidence,1,64)
    if any(x['kind']!='CHILD' or x['size']>MAX_CHILD for x in v['children']):hold()
    for k in ('old_sources','new_sources','upload_reuse'):_seq(v[k],_evidence,hi=3072)
    _evidence(v['expected_metadata']);_evidence(v['execution_budget'])
    if v['expected_metadata']['kind']!='METADATA' or v['execution_budget']['kind']!='BUDGET':hold()
    _seq(v['read_delegation_ids'],_hash,hi=128);_seq(v['artifact_descriptors'],_artifact,hi=3072)


def _payload_json(text,expected):
    _text(text,MAX_CHILD);_hash(expected)
    value=_parse(text.encode(),MAX_CHILD)
    if _canonical(value)!=text or sha256(text.encode()).hexdigest()!=expected:hold()


def _child(v):
    _closed(v,('schema','profile','binding','operation_id','selector','manifest_json','manifest_sha','projection_json','projection_sha','members','upload_reuse','expected_metadata','execution_budget','artifact_descriptors'))
    _binding(v['binding']);_id(v['operation_id']);_selector(v['selector'])
    _payload_json(v['manifest_json'],v['manifest_sha']);_payload_json(v['projection_json'],v['projection_sha'])
    if v['selector']['content_digest']!=v['manifest_sha']:hold()
    _seq(v['members'],_member,1,8);_seq(v['upload_reuse'],_evidence,hi=48)
    if len({x['article_id'] for x in v['members']})!=len(v['members']):hold()
    _evidence(v['expected_metadata']);_evidence(v['execution_budget'])
    if v['expected_metadata']['kind']!='METADATA' or v['execution_budget']['kind']!='BUDGET':hold()
    _seq(v['artifact_descriptors'],_artifact,hi=48)


def _proof(v):
    _closed(v,('schema','profile','registration_sha','source_material_sha','read_delegation_proof_shas','artifact_inventory_sha','original_save_evidence_sha','helper_acceptance','qualified_binding','observed_generation','not_after'))
    for k in ('registration_sha','source_material_sha','artifact_inventory_sha','original_save_evidence_sha'):_hash(v[k])
    _seq(v['read_delegation_proof_shas'],_hash,hi=128);_binding(v['qualified_binding'])
    _evidence(v['helper_acceptance']);_evidence(v['observed_generation'])
    if v['helper_acceptance']['kind']!='HELPER_ACCEPTANCE' or v['observed_generation']['kind']!='GENERATION':hold()
    _deadline(v['not_after'])


def _head(v):
    keys=('schema','profile','family_id','seq','registration_sha','previous_head_sha','source_material_sha')
    if type(v.get('schema')) is int and v['schema']==2 and v.get('profile')=='GROUP_SELECTED_INPUT_HEAD_V2':
        _closed(v,(*keys,'registration_proof_sha'))
        _hash(v['registration_proof_sha'])
    else:
        _closed(v,keys)
        if type(v.get('schema')) is not int or v['schema']!=1 or v.get('profile')!='GROUP_SELECTED_INPUT_HEAD_V1':hold()
    for k in ('family_id','registration_sha','source_material_sha'):_hash(v[k])
    _int(v['seq'],1);_maybe(v['previous_head_sha'],_hash)
    if (v['seq']==1)!=(v['previous_head_sha'] is None):hold()


def _reservation(v):
    _closed(v,('schema','profile','binding','manifest_sha','selector','registration_sha','capsule_sha','operation_id','proof_sha'))
    _binding(v['binding']);_selector(v['selector']);_id(v['operation_id'])
    for k in ('manifest_sha','registration_sha','capsule_sha','proof_sha'):_hash(v[k])
    if v['manifest_sha']!=v['selector']['content_digest']:hold()


def _upload_reuse(v):
    from .draft_group_upload_reuse_values import validate_map
    validate_map(v)


_VALIDATORS={'upload_reuse':_upload_reuse,'registration':_registration,'source':_source,'execution':_execution,'child':_child,'proof':_proof,'head_history':_head,'reservation':_reservation}


def _role(role):
    if type(role) is not str or role not in ROLES:hold()
    return ROLES[role]


def encode(role,value):
    config=_role(role);_plain(value)
    if type(value) is not dict or type(value.get('schema')) is not int or type(value.get('profile')) is not str:hold()
    version=(value['schema'],value['profile'])
    accepted=((1,config[2]),)
    if role=='head_history':accepted+=((2,'GROUP_SELECTED_INPUT_HEAD_V2'),)
    if role=='source':accepted+=((2,'GROUP_BATCH_NATIVE_SOURCE_BASELINE_V2'),
                               (1,'GROUP_BATCH_OPERATOR_SELECTED_SOURCE_V1'))
    if version not in accepted:hold()
    _VALIDATORS[role](value)
    raw=(_canonical(value)+'\n').encode('utf-8')
    if not 0<len(raw)<=config[3]:hold('GROUP_INPUT_FILE_LIMIT')
    return raw


def _parse(raw,maximum):
    if type(raw) is not bytes or not 0<len(raw)<=maximum:hold()
    def pairs(items):
        result={}
        for k,v in items:
            if k in result:hold()
            result[k]=v
        return result
    def constant(_):hold()
    try:value=json.loads(raw.decode('utf-8'),object_pairs_hook=pairs,parse_constant=constant)
    except (ValueError,UnicodeError,RecursionError,OverflowError):hold()
    _plain(value);return value


def decode(role,raw):
    maximum=_role(role)[3];value=_parse(raw,maximum)
    if encode(role,value)!=raw:hold()
    return value


@dataclass(frozen=True,slots=True)
class FileEvidence:
    role:str
    key:str
    sha256:str
    size:int
    raw:bytes=field(repr=False)
    @property
    def authority(self):return False
    @property
    def value(self):return decode(self.role,self.raw)


@dataclass(frozen=True,slots=True)
class HeadCASPlan:
    expected_head_sha:str|None
    desired_sha:str
    raw:bytes=field(repr=False)
    root_identity:tuple=field(repr=False)
    @property
    def authority(self):return False


def _pin(info):return file_state(info)+(info.st_uid,info.st_mode)


def _private_directory(info):
    if not stat.S_ISDIR(info.st_mode) or info.st_uid!=os.getuid() or stat.S_IMODE(info.st_mode)!=0o700:hold()


def _private_file(info,maximum,*,empty=False):
    if (not stat.S_ISREG(info.st_mode) or info.st_uid!=os.getuid() or stat.S_IMODE(info.st_mode)!=0o600
        or info.st_nlink!=1 or not (0 if empty else 1)<=info.st_size<=maximum):hold()


class _FixedFileIO:
    def __init__(self,policy,guard):
        if type(policy) is not ConnectionPolicy or not callable(guard):hold()
        if type(policy.path) is not type(Path('/')):hold()
        _plain(policy.value)
        if type(policy.value) is not dict or type(policy.value.get('identity')) is not dict:hold()
        self.policy=policy;self.guard=guard;self.root=policy.root
        if policy.path.name!='connection-policy.json' or type(policy.data.get('private_directory')) is not str or policy.data['private_directory']!=str(self.root):hold()
        self.root_identity=path_check(self.root,True)
        if type(policy.root_pin) is not tuple or len(policy.root_pin)!=2 or any(type(x) is not int for x in policy.root_pin) or policy.root_pin!=self.root_identity:hold()
        self.policy_pin=path_check(policy.path)
        if type(policy.pin) is not tuple or len(policy.pin)!=6 or any(type(x) is not int for x in policy.pin) or policy.pin!=self.policy_pin:hold()
        self._guard()

    def _guard(self):
        result=self.guard()
        if result is not None and result is not True:hold()
        if (self.policy.root!=self.root or path_check(self.root,True)!=self.root_identity
            or path_check(self.policy.path)!=self.policy_pin):hold()

    def _config(self,role):return _role(role)
    def _encode(self,role,value):return encode(role,value)
    def _key(self,role,value,checksum):return value['manifest_sha'] if role=='reservation' else checksum
    def _allowed_directories(self):return ('group-inputs','group-proofs','group-targets','.ROOT')
    def _base_path(self,name):return self.root
    def _base_identity(self,name):return self.root_identity

    @contextmanager
    def _directory(self,name,*,create=False):
        if type(name) is not str or name not in self._allowed_directories():hold()
        self._guard();source=FileSource(self._base_path(name));fds=[];chain=[]
        try:
            fd=source._root(fds,chain)
            if identity(os.fstat(fd))!=self._base_identity(name):hold()
            _private_directory(os.fstat(fd))
            if name!='.ROOT':
                if create:
                    self._guard();source._check_chain(chain)
                    try:os.mkdir(name,0o700,dir_fd=fd)
                    except FileExistsError:pass
                    self._guard();os.fsync(fd)
                fd=source._directory(fd,name,fds,chain)
                _private_directory(os.fstat(fd))
            def fence():
                source._check_chain(chain);_private_directory(os.fstat(fd))
                if path_check(self.root,True)!=self.root_identity:hold()
            self._guard();fence()
            yield fd,fence
            fence()
        except (OSError,ValueError,UnicodeError):hold()
        finally:source._close(fds)

    def initialize(self):
        for name in ('group-inputs','group-proofs','group-targets'):
            with self._directory(name,create=True):pass

    def _name(self,role,key):
        folder,prefix,_,_=self._config(role);_hash(key)
        return folder,prefix+key+'.json'

    def _read_at(self,fd,name,fence,maximum,*,missing=False,with_pin=False):
        self._guard();fence()
        try:opened=os.open(name,os.O_RDONLY|os.O_NOFOLLOW|os.O_NONBLOCK,dir_fd=fd)
        except FileNotFoundError:
            if not missing:hold()
            self._guard();fence()
            try:os.stat(name,dir_fd=fd,follow_symlinks=False)
            except FileNotFoundError:return None
            hold()
        try:
            before=os.fstat(opened);_private_file(before,maximum);raw=bytearray();deadline=time.monotonic()+READ_SECONDS
            while len(raw)<=maximum:
                self._guard();fence()
                if time.monotonic()>deadline:hold()
                part=os.read(opened,min(CHUNK_BYTES,maximum+1-len(raw)))
                if not part:break
                raw.extend(part)
            self._guard();fence()
            after=os.fstat(opened);entry=os.stat(name,dir_fd=fd,follow_symlinks=False)
            _private_file(after,maximum);_private_file(entry,maximum)
            if _pin(before)!=_pin(after) or _pin(after)!=_pin(entry) or len(raw)!=after.st_size:hold()
            return (bytes(raw),_pin(after)) if with_pin else bytes(raw)
        finally:os.close(opened)

    def _evidence(self,role,key,raw,expected_sha=None):
        _maybe(expected_sha,_hash)
        value=decode(role,raw);actual=sha256(raw).hexdigest()
        if role=='reservation':
            if value['manifest_sha']!=key:hold()
            if expected_sha is not None and actual!=_hash(expected_sha):hold()
        elif actual!=key or expected_sha is not None and expected_sha!=key:hold()
        return FileEvidence(role,key,actual,len(raw),raw)

    def _entry(self,role,key,*,expected_sha=None):
        folder,name=self._name(role,key)
        with self._directory(folder) as (fd,fence):
            raw,pin=self._read_at(fd,name,fence,self._config(role)[3],with_pin=True)
            evidence=self._evidence(role,key,raw,expected_sha)
        return evidence,pin

    def read(self,role,key,*,expected_sha=None):
        return self._entry(role,key,expected_sha=expected_sha)[0]

    def _pure_entries(self,entries,head_pin=False):
        # No callback follows the final collective file fence.
        try:
            if path_check(self.root,True)!=self.root_identity or path_check(self.policy.path)!=self.policy_pin:hold()
            for role,key,pin in entries:
                folder,name=self._name(role,key)
                path=self._base_path(folder)/folder/name;path_check(path.parent,True);path_check(path)
                if _pin(path.lstat())!=pin:hold()
            if head_pin is not False:
                path=self.root/'group-input-head.json'
                if head_pin is None:
                    if os.path.lexists(path):hold()
                else:
                    path_check(path)
                    if _pin(path.lstat())!=head_pin:hold()

        except (OSError,ValueError):hold()

    def inspect_publication(self,role,key,expected_sha):
        self._config(role);_hash(key);_hash(expected_sha)
        try:
            folder,name=self._name(role,key)
            with self._directory(folder) as (fd,fence):
                raw=self._read_at(fd,name,fence,self._config(role)[3],missing=True)
                if raw is None:return {'state':'ABSENT','authority':False}
                e=self._evidence(role,key,raw,expected_sha)
                return {'state':'COMMITTED','sha256':e.sha256,'authority':False}
        except (WCEError,OSError,ValueError):return {'state':'UNDETERMINED','authority':False}

    def _confirm_at(self,fd,name,fence,raw,maximum):
        self._guard();fence();opened=os.open(name,os.O_RDONLY|os.O_NOFOLLOW|os.O_NONBLOCK,dir_fd=fd)
        try:
            before=os.fstat(opened);_private_file(before,maximum)
            if self._read_at(fd,name,fence,maximum)!=raw:hold()
            self._guard();fence()
            if _pin(before)!=_pin(os.fstat(opened)) or _pin(before)!=_pin(os.stat(name,dir_fd=fd,follow_symlinks=False)):hold()
            os.fsync(opened);self._guard();fence();os.fsync(fd)
            self._guard();fence()
            if self._read_at(fd,name,fence,maximum)!=raw:hold()
            if _pin(before)!=_pin(os.fstat(opened)) or _pin(before)!=_pin(os.stat(name,dir_fd=fd,follow_symlinks=False)):hold()
            return _pin(before)
        finally:os.close(opened)

    def publish(self,role,value):
        return self._publish_observed(role,value)[0]

    def _publish_observed(self,role,value):
        raw=self._encode(role,value);checksum=sha256(raw).hexdigest()
        key=self._key(role,value,checksum)
        return self._publish_bytes_observed(role,key,raw,checksum)

    def _publish_bytes_observed(self,role,key,raw,checksum):
        folder,name=self._name(role,key);maximum=self._config(role)[3]
        with self._directory(folder) as (fd,fence):
            self._guard();fence()
            try:opened=os.open(name,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW|os.O_NONBLOCK,0o600,dir_fd=fd)
            except FileExistsError:
                if self._read_at(fd,name,fence,maximum)!=raw:hold('GROUP_INPUT_FILE_CONFLICT')
            else:
                try:
                    os.fchmod(opened,0o600);_private_file(os.fstat(opened),maximum,empty=True)
                    created_identity=identity(os.fstat(opened))
                    written=0
                    while written<len(raw):
                        self._guard();fence()
                        count=os.write(opened,raw[written:written+CHUNK_BYTES])
                        if type(count) is not int or count<=0:hold()
                        written+=count
                    self._guard();fence();_private_file(os.fstat(opened),maximum)
                    written_pin=_pin(os.fstat(opened))
                    if identity(os.fstat(opened))!=created_identity or written_pin!=_pin(os.stat(name,dir_fd=fd,follow_symlinks=False)):hold()
                    os.fsync(opened);self._guard();fence()
                    if written_pin!=_pin(os.fstat(opened)) or written_pin!=_pin(os.stat(name,dir_fd=fd,follow_symlinks=False)):hold()
                    os.fsync(fd)
                finally:os.close(opened)
            # Confirms originals after unknown fsync, never repairs bytes.
            confirmed=self._confirm_at(fd,name,fence,raw,maximum)
            actual=self._read_at(fd,name,fence,maximum)
            if _pin(os.stat(name,dir_fd=fd,follow_symlinks=False))!=confirmed:hold()
            evidence=self._evidence(role,key,actual,checksum)
        return evidence,confirmed

class InputFiles(_FixedFileIO):
    def _read_head_bytes(self,*,missing=False,with_pin=False):
        with self._directory('.ROOT') as (fd,fence):
            observed=self._read_at(fd,'group-input-head.json',fence,MAX_HEAD,missing=missing,with_pin=True)
            if observed is not None:decode('head_history',observed[0])
        if observed is None:return None
        return observed if with_pin else observed[0]

    def read_head(self):
        raw,pin=self._read_head_bytes(with_pin=True)
        self._verify_head_chain(raw)
        self._pure_entries([],head_pin=pin)
        return FileEvidence('head_history',sha256(raw).hexdigest(),sha256(raw).hexdigest(),len(raw),raw)

    def _verify_head_chain(self,raw):
        seen=set();total=0;entries=[]
        while True:
            value=decode('head_history',raw);checksum=sha256(raw).hexdigest();total+=len(raw)
            if checksum in seen or len(seen)>=MAX_HEAD_CHAIN or total>MAX_TOP:hold()
            seen.add(checksum)
            archived,pin=self._entry('head_history',checksum);entries.append(('head_history',checksum,pin))
            if archived.raw!=raw:hold()
            if value['previous_head_sha'] is None:
                self._pure_entries(entries);return tuple(entries)
            previous,pin=self._entry('head_history',value['previous_head_sha']);entries.append(('head_history',previous.key,pin))
            if previous.value['seq']+1!=value['seq']:hold()
            if previous.value['schema']==2 and value['schema']!=2:hold('GROUP_INPUT_HEAD_VERSION_DOWNGRADE')
            raw=previous.raw

    def prepare_head(self,value,expected_head_sha):
        return self._prepare_head_observed(value,expected_head_sha)[0]

    def _prepare_head_observed(self,value,expected_head_sha):
        raw=encode('head_history',value);desired=sha256(raw).hexdigest();_maybe(expected_head_sha,_hash)
        registered,reg_pin=self._entry('registration',value['registration_sha']);registration=registered.value
        source,source_pin=self._entry('source',value['source_material_sha'])
        entries=[('registration',registered.key,reg_pin),('source',source.key,source_pin)]
        if (registration['family_id']!=value['family_id'] or registration['source_material_sha']!=source.sha256
            or registration['source_material_sha']!=value['source_material_sha']):hold()
        if value['schema']==2:
            proof,proof_pin=self._entry('proof',value['registration_proof_sha'])
            candidate=proof.value
            if (candidate['registration_sha']!=registered.sha256
                or candidate['source_material_sha']!=source.sha256
                or candidate['qualified_binding']!=registration['binding']):hold('GROUP_INPUT_HEAD_PROOF_CHANGED')
            entries.append(('proof',proof.key,proof_pin))
        observed=self._read_head_bytes(missing=True,with_pin=True)
        current=None if observed is None else observed[0];head_pin=None if observed is None else observed[1]
        if current is not None and current==raw:
            if value['previous_head_sha']!=expected_head_sha:hold('GROUP_INPUT_HEAD_CONFLICT')
            entries.extend(self._verify_head_chain(raw))
            self._pure_entries(entries,head_pin=head_pin)
            return HeadCASPlan(expected_head_sha,desired,raw,self.root_identity),tuple(entries),head_pin
        if current is None:
            if expected_head_sha is not None or value['seq']!=1:hold('GROUP_INPUT_HEAD_CONFLICT')
        else:
            actual=sha256(current).hexdigest()
            if expected_head_sha!=actual:hold('GROUP_INPUT_HEAD_CONFLICT')
            entries.extend(self._verify_head_chain(current));old=decode('head_history',current)
            if value['seq']!=old['seq']+1 or value['previous_head_sha']!=actual:hold()
            if old['schema']==2 and value['schema']!=2:hold('GROUP_INPUT_HEAD_VERSION_DOWNGRADE')
        if value['previous_head_sha']!=expected_head_sha:hold()
        self._pure_entries(entries,head_pin=head_pin)
        return HeadCASPlan(expected_head_sha,desired,raw,self.root_identity),tuple(entries),head_pin

    def inspect_head(self,value,expected_head_sha):
        try:
            plan,entries,head_pin=self._prepare_head_observed(value,expected_head_sha)
            current=self._read_head_bytes(missing=True)
            self._pure_entries(entries,head_pin=head_pin)
            return {'state':'COMMITTED' if current==plan.raw else 'NOT_COMMITTED','sha256':plan.desired_sha,'authority':False}
        except (WCEError,OSError,ValueError):return {'state':'UNDETERMINED','authority':False}

    def commit_head(self,plan):
        """Caller holds REAL account writer exclusion; plan grants nothing."""
        if type(plan) is not HeadCASPlan or type(plan.raw) is not bytes or type(plan.root_identity) is not tuple or len(plan.root_identity)!=2 or any(type(x) is not int for x in plan.root_identity) or plan.root_identity!=self.root_identity:hold()
        value=decode('head_history',plan.raw)
        if sha256(plan.raw).hexdigest()!=_hash(plan.desired_sha):hold()
        current,prepared_entries,prepared_head_pin=self._prepare_head_observed(value,plan.expected_head_sha)
        if current!=plan:hold()
        archived,archive_pin=self._publish_observed('head_history',value)
        commit_entries=(*prepared_entries,('head_history',archived.key,archive_pin))
        with self._directory('.ROOT') as (fd,fence):
            self._guard();fence()
            previous_observed=self._read_at(fd,'group-input-head.json',fence,MAX_HEAD,missing=True,with_pin=True)
            previous=None if previous_observed is None else previous_observed[0]
            previous_pin=None if previous_observed is None else previous_observed[1]
            self._pure_entries(commit_entries,head_pin=prepared_head_pin)
            if previous_pin!=prepared_head_pin:hold()
            if previous==plan.raw:
                confirmed=self._confirm_at(fd,'group-input-head.json',fence,plan.raw,MAX_HEAD)
            else:
                if (None if previous is None else sha256(previous).hexdigest())!=plan.expected_head_sha:hold('GROUP_INPUT_HEAD_CONFLICT')
                name='.group-head-'+plan.desired_sha+'.pending'
                self._guard();fence()
                try:temporary=os.open(name,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW|os.O_NONBLOCK,0o600,dir_fd=fd)
                except FileExistsError:
                    if self._read_at(fd,name,fence,MAX_HEAD)!=plan.raw:hold()
                else:
                    try:
                        os.fchmod(temporary,0o600);_private_file(os.fstat(temporary),MAX_HEAD,empty=True)
                        offset=0
                        while offset<len(plan.raw):
                            self._guard();fence();written=os.write(temporary,plan.raw[offset:])
                            if type(written) is not int or written<=0:hold()
                            offset+=written
                        self._guard();fence();os.fsync(temporary)
                    finally:os.close(temporary)
                confirmed=self._confirm_at(fd,name,fence,plan.raw,MAX_HEAD)
                # The last guard runs BEFORE the final comparison. No callback
                # can replace the compared head between this fence and rename.
                self._guard();fence()
                latest_observed=self._read_at(fd,'group-input-head.json',fence,MAX_HEAD,missing=True,with_pin=True)
                latest=None if latest_observed is None else latest_observed[0]
                latest_pin=None if latest_observed is None else latest_observed[1]
                if latest!=previous or latest_pin!=previous_pin:hold('GROUP_INPUT_HEAD_CONFLICT')
                # No callback occurs after this collective fence. The pending
                # identity is the original _confirm_at pin, never a new baseline.
                fence();self._pure_entries(commit_entries,head_pin=prepared_head_pin)
                if _pin(os.stat(name,dir_fd=fd,follow_symlinks=False))!=confirmed:hold()
                os.replace(name,'group-input-head.json',src_dir_fd=fd,dst_dir_fd=fd)
                moved=_pin(os.stat('group-input-head.json',dir_fd=fd,follow_symlinks=False))
                # Our own rename may advance ctime. Pin that one transition
                # before any guard; inode/content/mtime/link/uid/mode stay fixed.
                if moved[:4]+moved[5:]!=confirmed[:4]+confirmed[5:]:hold()
                confirmed=moved
                self._guard();fence();os.fsync(fd)
                self._guard();fence()
                if self._read_at(fd,'group-input-head.json',fence,MAX_HEAD)!=plan.raw:hold()
                if _pin(os.stat('group-input-head.json',dir_fd=fd,follow_symlinks=False))!=confirmed:hold()
        observed=self.read_head()
        if observed.raw!=plan.raw:hold()
        self._pure_entries(commit_entries,head_pin=confirmed)
        return observed
