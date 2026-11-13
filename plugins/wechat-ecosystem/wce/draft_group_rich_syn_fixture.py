"""Private compiled Rich SYN fixture issuer. Production has no enabled row.

A fixture build changes only the literal empty table to one reviewed helper
row. The helper and native binary are outside the production payload. No MCP,
configuration, environment, path/hash argument or caller dictionary enables it.
"""
from contextlib import contextmanager,ExitStack,closing
from dataclasses import dataclass,field,replace
from pathlib import Path
from hashlib import sha256
import ast,importlib.util,os,sqlite3,stat,sys,threading,time,weakref
from .contracts import WCEError
from .draft_group_pin_resources import PinPool,close_all
from . import draft_group_pin_resources as _pin_resources
from types import FunctionType as _ResourceFunctionType

SCENARIO='WCE_RICH_SYN_NEW_ONLY_EMPTY_ACCOUNT_C1_V1'
SEQUENCE=('TOKEN_POST','PREVIEW_ACCOUNT:LIST:1','PREVIEW_ACCOUNT:LIST:2','CHILD:ADD','CHILD:GET:NEW','CHILD:GET:FINAL_NEW')
# scenario, helper path/SHA, dependency path/SHA tuple, project TMP root,
# C resource root, already compiled shim path/SHA. Never filled in packaging.
_FIXTURE_FACTORY_ROWS=()
_DOMAINS=weakref.WeakKeyDictionary();_SESSIONS=weakref.WeakKeyDictionary()
_SESSION_PATHS=weakref.WeakKeyDictionary();_DOMAIN_PATHS=weakref.WeakKeyDictionary()
_ENTRY_DOMAINS={};_SERVICE_DOMAINS=weakref.WeakKeyDictionary();_STORAGE_PERMITS=weakref.WeakKeyDictionary()
_NATIVE_LIBRARIES={};_BACKENDS=weakref.WeakKeyDictionary()
_HISTORY_JOBS={}
_RUNTIME_JOBS={}
_THREAD=threading.get_ident;_MONOTONIC=time.monotonic


def hold(code='GROUP_RICH_SYN_FIXTURE_HOLD'):raise WCEError(code)


def need(value,code='GROUP_RICH_SYN_FIXTURE_HOLD'):
    if value is not True:hold(code)


class RichSYNFixtureDomain:
    __slots__=('__weakref__',)
    def __init__(self):hold('GROUP_RICH_SYN_ISSUER_REQUIRED')


class RichSYNFixtureSession:
    __slots__=('__weakref__',)
    def __init__(self):hold('GROUP_RICH_SYN_ISSUER_REQUIRED')
    @property
    def domain(self):return _session(self)[0]
    @property
    def policy(self):return _record(self.domain).policy
    @property
    def pins(self):return _session(self)[1]['pins']
    @contextmanager
    def open_host(self):
        """Original complete path, after the same fixed local prefix."""
        _select_full_session(self)
        with self._open_host_prefix() as host:
            domain,materials,module=_session(self)
            entry=host.entry;service=entry.service
            # Expected GET bodies derive from original qualified source,
            # never from the later ADD request or a fabricated Parent.
            from .draft_group_source_members import source_members_for_registration_in
            with _history_transaction(service.workflow.db,physical_resources=entry) as (db, history_locators):
                if host.chain.source['profile']=='GROUP_BATCH_NATIVE_SOURCE_BASELINE_V2':
                    from .draft_group_host_review import local_registration_inspection_in
                    inspection=local_registration_inspection_in(host,db,history_locators=history_locators)
                    source_values=source_members_for_registration_in(host,db,inspection, history_locators=history_locators)
                else:source_values=source_members_for_registration_in(host,db, history_locators=history_locators)
            from .draft_group_contracts import budget_for
            budget=budget_for(0)
            need(len(source_values['members'])==len(source_values['source_rows'])==2
                 and all(m['origin']=='NEW_NOT_SENT' for m in source_values['members'])
                 and budget['get_cap']==2 and budget['add_cap']==1 and budget['delete_cap']==0)
            response_fixtures=module.write_c1_response_fixtures(source_values['source_rows'])
            _freeze_responses(domain,response_fixtures)
            from .draft_group_rich_syn_transport import prepare_rich_syn_transport_resources
            transport=prepare_rich_syn_transport_resources(domain)
            need(_record(domain).transport is transport,'GROUP_RICH_SYN_TRANSPORT_UNISSUED')
            from .draft_group_rich_syn_keychain import prepare_rich_syn_keychain
            prepare_rich_syn_keychain(domain)
            _activate(domain,entry,host,service)
            yield host


    @contextmanager
    def open_local_host(self):
        """Issued-only irreversible local path; never prepares effect resources."""
        _select_local_session(self)
        with self._open_host_prefix() as host:
            yield host

    @contextmanager
    def _open_host_prefix(self):
        """Single original cold/storage/listener/source lifecycle; no effects."""
        domain,materials,module=_session(self);record=_record(domain)
        _require_selected_prefix(self,domain,record)
        need(record.entry is None,'GROUP_RICH_SYN_ENTRY_ONCE')
        from .draft_group_runtime_host import (BootstrapAccountCore,GroupExecutionGate,
            qualify_bootstrap_storage,from_verified_bootstrap)
        from .draft_group_host_review import GroupRuntimeHost
        from .draft_group_host_bootstrap import _bind_listener
        from .own_connection_broker import Broker
        from .own_connection_policy import locked
        with locked(record.policy.root/'connection.lock',nonblocking=True):
            broker=Broker(record.policy);core=BootstrapAccountCore(record.policy)
            with GroupExecutionGate(core,record.outer_deadline,None,broker=broker) as entry,ExitStack() as resources:
                _ENTRY_DOMAINS[id(entry)]=(entry,domain)
                _DOMAINS[domain]=replace(record,entry=entry)
                try:
                    host=GroupRuntimeHost(entry,materials['pins'])
                    need(host.chain.config['binding']['source_kind']=='SYNTHETIC_SETUP','GROUP_RICH_SYN_SOURCE_KIND')
                    qualification=qualify_bootstrap_storage(host,core,entry)
                    service=from_verified_bootstrap(core,entry,qualification);broker.service=service
                    listener=resources.enter_context(broker._listener_initialized())
                    binding=_bind_listener(entry,broker,service,listener)
                    GroupExecutionGate.from_bound_bootstrap(entry,binding);host.qualify_current_group_source()
                    yield host

                finally:
                    _ENTRY_DOMAINS.pop(id(entry),None)
                    _close_domain_resources(domain)


@dataclass(frozen=True,slots=True)
class RichSYNDomainFacts:
    policy:object=field(repr=False)
    root_pin:tuple
    scenario_id:str
    sequence:tuple
    max_connection_upper:int
    thread:int
    generation:int
    phase:str
    fixture_root:Path=field(repr=False)
    transport_resource_root:Path=field(repr=False)
    response_fixtures:tuple=field(repr=False)
    authority:bool=False


@dataclass(frozen=True,slots=True)
class _DomainRecord:
    policy:object=field(repr=False)
    root_pin:tuple
    scenario_id:str
    thread:int
    generation:int
    phase:str
    fixture_root:Path=field(repr=False)
    transport_resource_root:Path=field(repr=False)
    shim_path:Path=field(repr=False)
    shim_sha:str
    pins:tuple=field(repr=False)
    fixture_pool:object=field(repr=False)
    fixture_owner:object=field(repr=False)
    cwd_fd:int=field(repr=False)
    cwd_pin:tuple
    outer_deadline:float
    lock:object=field(repr=False)
    entry:object=field(default=None,repr=False)
    transport:object=field(default=None,repr=False)
    response_fixtures:tuple=field(default=(),repr=False)


def _identity(info):return (info.st_dev,info.st_ino,info.st_uid,info.st_gid,stat.S_IMODE(info.st_mode))


def _record(domain):
    assert_rich_syn_fixture_tcb()
    need(type(domain) is RichSYNFixtureDomain,'GROUP_RICH_SYN_ISSUER_REQUIRED')
    record=_DOMAINS.get(domain)
    need(record is not None and record.thread==_THREAD() and record.phase not in ('CLOSED','FAILED'),
         'GROUP_RICH_SYN_DOMAIN_CLOSED')
    return record


def _session(value):
    need(type(value) is RichSYNFixtureSession,'GROUP_RICH_SYN_ISSUER_REQUIRED')
    found=_SESSIONS.get(value);need(found is not None,'GROUP_RICH_SYN_ISSUER_REQUIRED')
    _record(found[0]);return found



def _select_full_session(session):
    domain,_,_=_session(session);record=_record(domain)
    need(session not in _SESSION_PATHS and domain not in _DOMAIN_PATHS
         and record.phase=='PREPARING'and record.entry is None,'GROUP_RICH_SYN_PATH_ALREADY_SELECTED')
    _SESSION_PATHS[session]=('FULL',domain,_THREAD())
    _DOMAIN_PATHS[domain]=('FULL',weakref.ref(session),_THREAD())


def _select_local_session(session):
    domain,_,_=_session(session);record=_record(domain)
    need(session not in _SESSION_PATHS and domain not in _DOMAIN_PATHS
         and record.phase=='PREPARING'and record.entry is None,'GROUP_RICH_SYN_PATH_ALREADY_SELECTED')
    _SESSION_PATHS[session]=('LOCAL',domain,_THREAD())
    _DOMAIN_PATHS[domain]=('LOCAL',weakref.ref(session),_THREAD())
    _DOMAINS[domain]=replace(record,phase='LOCAL_NO_EFFECT')


def _selected_domain_path(domain):
    chosen=_DOMAIN_PATHS.get(domain)
    need(chosen is not None and chosen[0]in ('FULL','LOCAL')and chosen[2]==_THREAD(),'GROUP_RICH_SYN_PATH_REQUIRED')
    session=chosen[1]();issued=None if session is None else _SESSIONS.get(session)
    need(issued is not None and issued[0]is domain
         and _SESSION_PATHS.get(session)==(chosen[0],domain,chosen[2]),'GROUP_RICH_SYN_PATH_CHANGED')
    return chosen[0]


def _require_selected_prefix(session,domain,record):
    path=_selected_domain_path(domain)
    need(_SESSION_PATHS.get(session)==(path,domain,_THREAD())
         and record.phase==('PREPARING'if path=='FULL'else 'LOCAL_NO_EFFECT'), 'GROUP_RICH_SYN_PATH_CHANGED')


def require_rich_syn_full_resources(domain):
    need(_selected_domain_path(domain)=='FULL','GROUP_RICH_SYN_LOCAL_EFFECT_FORBIDDEN')
    return None


def _storage_path(domain,entry):
    record=_record(domain);path=_selected_domain_path(domain)
    need(record.entry is entry and record.phase==('PREPARING'if path=='FULL'else 'LOCAL_NO_EFFECT'),
         'GROUP_RICH_SYN_STORAGE_PATH')
    return record

def validate_rich_syn_domain(domain,*,policy=None,entry=None):
    r=_record(domain)
    need((policy is None or policy is r.policy) and (entry is None or entry is r.entry), 'GROUP_RICH_SYN_DOMAIN_BINDING')
    if r.entry is not None:
        from .draft_group_runtime_host import _REGISTRY
        need(_REGISTRY.get(r.entry.id) is r.entry and not r.entry.closed and r.entry.thread==r.thread
             and r.entry.policy is r.policy,'GROUP_RICH_SYN_DOMAIN_ENTRY')
    if domain in _DOMAIN_PATHS and _selected_domain_path(domain)=='LOCAL':
        need(r.phase=='LOCAL_NO_EFFECT','GROUP_RICH_SYN_LOCAL_DOMAIN_CHANGED')
    if r.phase=='ACTIVE':
        from .draft_group_rich_syn_keychain import validate_native_domain_pure
        validate_native_domain_pure(domain)
    return RichSYNDomainFacts(r.policy,r.root_pin,r.scenario_id,SEQUENCE,6,r.thread,r.generation,r.phase,
        r.fixture_root,r.transport_resource_root,r.response_fixtures)


def require_rich_syn_domain_for_entry(entry):
    pair=_ENTRY_DOMAINS.get(id(entry));need(pair is not None and pair[0] is entry,'GROUP_RICH_SYN_DOMAIN_REQUIRED')
    domain=pair[1];r=_record(domain)
    need(r.phase=='ACTIVE' and r.entry is entry and getattr(entry,'source_kind',None)=='SYNTHETIC_SETUP',
         'GROUP_RICH_SYN_ACTIVE_REQUIRED')
    validate_rich_syn_domain(domain,entry=entry);return domain


def _freeze_responses(domain,fixtures):
    require_rich_syn_full_resources(domain)
    r=_record(domain);need(r.phase=='PREPARING' and not r.response_fixtures and type(fixtures) is tuple and len(fixtures)==6)
    from .draft_group_runtime_host import PinnedFile
    held=list(r.pins)
    for stage,item in zip(SEQUENCE,fixtures,strict=True):
        need(type(item) is tuple and len(item)==4 and item[0]==stage and type(item[1]) is type(Path('/'))
             and item[1].is_relative_to(r.fixture_root) and type(item[2]) is str and type(item[3]) is int)
        pin=PinnedFile(item[1],item[2],2*1024*1024);need(len(pin.raw)==item[3]);held.append(pin)
    _DOMAINS[domain]=replace(r,response_fixtures=fixtures,pins=tuple(held))


def register_rich_syn_transport_binding(domain,binding):
    require_rich_syn_full_resources(domain)
    r=_record(domain);need(r.phase=='PREPARING' and r.transport is None)
    from .draft_group_rich_syn_transport import validate_rich_syn_transport_binding
    validate_rich_syn_transport_binding(binding,domain)
    _DOMAINS[domain]=replace(r,transport=binding)


def _activate(domain,entry,host,service):
    require_rich_syn_full_resources(domain)
    r=_record(domain)
    from .draft_group_runtime_host import QualifiedGroupSource
    need(r.phase=='PREPARING' and r.entry is entry and entry.listener_bound and not entry.pre_storage
         and entry.service is service and host.entry is entry and type(host._source) is QualifiedGroupSource
         and entry.issued.get(id(host._source)) is host._source and r.transport is not None)
    profiles=tuple(service.workflow.registry.profiles.values())
    need(len(profiles)==1 and profiles[0].source_kind=='SYNTHETIC_SETUP')
    if host.chain.source['profile']=='GROUP_BATCH_NATIVE_SOURCE_BASELINE_V2':
        from .draft_group_host_review import local_registration_inspection_in
        local_registration_inspection_in(host,history_locators=None)
    else:host.current_no_token_in(None,host._source, history_locators=None)
    from .draft_group_rich_syn_transport import validate_rich_syn_transport_binding
    validate_rich_syn_transport_binding(r.transport,domain)
    _DOMAINS[domain]=replace(r,phase='ACTIVE')


@contextmanager
def rich_syn_storage_profile_in(service,core,entry,qualification):
    """Actual typed cold qualification only; never an arbitrary source-kind kw."""
    from .draft_group_runtime_host import BootstrapStorageQualification,BootstrapSourceInspection
    pair=_ENTRY_DOMAINS.get(id(entry));need(pair is not None and pair[0] is entry,'GROUP_RICH_SYN_DOMAIN_REQUIRED')
    domain=pair[1];r=_storage_path(domain,entry)
    need(r.entry is entry and type(qualification) is BootstrapStorageQualification
         and qualification.entry is entry and type(qualification.source) is BootstrapSourceInspection
         and entry.issued.get(id(qualification)) is qualification and entry.core is core
         and service.policy is core.policy is r.policy and service.tokens is core.tokens and service.serial is core.serial
         and qualification.source.host.chain.config['binding']['source_kind']=='SYNTHETIC_SETUP')
    need(service not in _STORAGE_PERMITS and service not in _SERVICE_DOMAINS)
    record=(domain,entry,qualification,core,service);_STORAGE_PERMITS[service]=record
    try:
        yield
        need(_STORAGE_PERMITS.get(service) is record)
        _SERVICE_DOMAINS[service]=(domain,entry,core)
    finally:_STORAGE_PERMITS.pop(service,None)


def rich_syn_profile_source_kind(service):
    permit=_STORAGE_PERMITS.get(service);existing=_SERVICE_DOMAINS.get(service)
    if permit is None and existing is None:return 'OPERATOR_ATTESTED'
    domain,entry,core=(permit[0],permit[1],permit[3]) if permit is not None else existing
    r=_record(domain)
    path=_selected_domain_path(domain)
    allowed_phase=('PREPARING','ACTIVE')if path=='FULL'else ('LOCAL_NO_EFFECT',)
    need(r.entry is entry and entry.policy is service.policy is r.policy and service.tokens is core.tokens
         and service.serial is core.serial and r.phase in allowed_phase)
    return 'SYNTHETIC_SETUP'


def rich_syn_socket_address(path):
    """A short expression for the same actual original socket, fixture only."""
    from .draft_group_runtime_host import _ACTIVE
    entry=getattr(_ACTIVE,'entry',None);pair=None if entry is None else _ENTRY_DOMAINS.get(id(entry))
    if pair is None:return None
    need(pair[0] is entry);r=_record(pair[1])
    need(Path(path)==r.policy.root/'connection.sock' and r.entry is entry
         and _identity(os.fstat(r.cwd_fd))==r.cwd_pin==_identity(os.stat('.',follow_symlinks=False)))
    address=os.path.relpath(path,Path.cwd());need('..' not in Path(address).parts and len(os.fsencode(address))<=100)
    need((Path.cwd()/address).absolute()==Path(path).absolute())
    return address


def _load_factory():
    assert_rich_syn_fixture_tcb()
    # The source literal, not mutable mirrors or environment, selects the row.
    tree=ast.parse(Path(__file__).read_bytes());assign=[n for n in tree.body if type(n) is ast.Assign
        and any(type(t) is ast.Name and t.id=='_FIXTURE_FACTORY_ROWS' for t in n.targets)]
    need(len(assign)==1);rows=ast.literal_eval(assign[0].value)
    need(type(rows) is tuple and rows==_FIXTURE_FACTORY_ROWS and len(rows)==1,'GROUP_RICH_SYN_COMPILED_FACTORY_MISSING')
    row=rows[0];need(type(row) is tuple and len(row)==8 and row[0]==SCENARIO and type(row[3]) is tuple)
    from .draft_group_runtime_host import PinnedFile
    helper=Path(row[1]);pins=[];owner=object();pool=PinPool(owner)
    try:
        pins.append(PinnedFile(helper,row[2],2*1024*1024,pool=pool,owner=owner))
        for path,checksum in row[3]:pins.append(PinnedFile(Path(path),checksum,2*1024*1024,pool=pool,owner=owner))
        spec=importlib.util.spec_from_file_location('_wce_compiled_rich_syn_c1',helper);need(spec is not None)
        module=importlib.util.module_from_spec(spec)
        exec(compile(pins[0].raw,str(helper),'exec'),module.__dict__)
        need(Path(module.__file__)==helper and callable(module.prepare_c1_fixture) and callable(module.write_c1_response_fixtures))
        return row,module,tuple(pins),pool,owner
    except BaseException as original:
        close_all([pin.close for pin in pins]+[lambda:_close_fixture_pool(pool,owner,original=original)],original)
        raise


def _close_fixture_pool(pool,owner,*,original=None):
    need(type(pool)is PinPool and pool.owner is owner,'GROUP_RICH_SYN_RESOURCE_OWNER')
    close_all((lambda:pool.check_all(owner=owner),lambda:pool.close(owner=owner,original=original)),original)



@contextmanager
def rich_syn_fixture_session():
    """No arguments. The production literal table is empty and refuses."""
    need(threading.current_thread() is threading.main_thread() and threading.active_count()==1,
         'GROUP_RICH_SYN_STANDALONE_HARNESS_REQUIRED')
    row,module,pins,pool,owner=_load_factory();cwd_fd=None
    domain=None;session=None;current_fd=None
    try:
        cwd_fd=os.open('.',os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW)
        old_cwd_pin=_identity(os.fstat(cwd_fd))
        with module.prepare_c1_fixture() as materials:
            from .own_connection_policy import ConnectionPolicy
            from .own_body_recovery import code_scope
            need(type(materials) is dict and set(materials)=={'policy','pins','fixture_root','harness_cwd'})
            policy=materials['policy'];root=Path(materials['fixture_root']);tmp=Path(row[4]);harness=Path(materials['harness_cwd'])
            need(type(policy) is ConnectionPolicy and root.is_relative_to(tmp) and policy.root.is_relative_to(root)
                 and harness==tmp.parent and policy.value['candidate_scope']==code_scope()
                 and policy.data['appid']==policy.data['resource_id']=='wx0000000000000001'
                 and policy.data['connection_id']=='synthetic-connection')
            policy.check()
            # Creation-time SYN evidence is independently read, not relabelled.
            from .own_validation_scope import OwnedConnection
            with closing(sqlite3.connect((policy.root/'state.sqlite3').as_uri()+'?mode=ro',uri=True,factory=OwnedConnection)) as db,db:
                need(db.execute('SELECT source_kind FROM own_config WHERE id=1').fetchone()[0]=='SYNTHETIC_SETUP')
            _register_history_job(policy,materials['pins'])
            os.chdir(harness);domain=object.__new__(RichSYNFixtureDomain);session=object.__new__(RichSYNFixtureSession)
            try:
                current_fd=os.open('.',os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW)
                record=_DomainRecord(policy,_identity(policy.root.stat()),SCENARIO,_THREAD(),1,'PREPARING',root,Path(row[5]),
                    Path(row[6]),row[7],pins,pool,owner,current_fd,_identity(os.fstat(current_fd)),_MONOTONIC()+300,threading.RLock())
                _DOMAINS[domain]=record;_SESSIONS[session]=(domain,materials,module)
                _register_runtime_source(domain,materials['pins'])
                yield session
            finally:
                original=sys.exc_info()[1]
                def mark_closed():
                    registered=_DOMAINS.get(domain)
                    if registered is not None:_DOMAINS[domain]=replace(registered,phase='CLOSED')
                    _SESSIONS.pop(session,None);_SESSION_PATHS.pop(session,None);_DOMAIN_PATHS.pop(domain,None)
                def close_current_fd():
                    nonlocal current_fd
                    if current_fd is not None:
                        owned,current_fd=current_fd,None
                        os.close(owned)
                registered=_DOMAINS.get(domain)
                close_pins=registered.pins if registered is not None else pins
                callbacks=([lambda:_close_domain_resources(domain)]if registered is not None else [])
                # Same original close order, including a failed partial record
                # or mapping registration; actual fd acquisition is the truth.
                close_all(callbacks+[*[pin.close for pin in close_pins],close_current_fd,mark_closed],original)
    finally:
        original=sys.exc_info()[1]
        callbacks=[]
        if cwd_fd is not None:
            def restore_cwd():
                os.fchdir(cwd_fd);need(_identity(os.stat('.',follow_symlinks=False))==old_cwd_pin)
            callbacks += [restore_cwd,lambda:os.close(cwd_fd)]
        callbacks += [pin.close for pin in pins]
        if current_fd is not None:
            owned,current_fd=current_fd,None
            callbacks.append(lambda fd=owned:os.close(fd))
        callbacks += [lambda:_close_fixture_pool(pool,owner,original=original)]
        close_all(callbacks,original)


def _close_domain_resources(domain):
    r=_DOMAINS.get(domain)
    if r is None or r.phase in ('CLOSED','CLOSING'):return
    _DOMAINS[domain]=replace(r,phase='CLOSING')
    if r.transport is not None:
        from .draft_group_rich_syn_transport import close_rich_syn_transport_resources
        close_rich_syn_transport_resources(r.transport)
    from .draft_group_rich_syn_keychain import close_rich_syn_keychain
    close_rich_syn_keychain(domain)


def _register_history_job(policy,pins):
    from .draft_group_host_review import FixedHostPins
    from .publication_contract import stable_account
    from .draft_group_contracts import canonical
    need(type(pins) is FixedHostPins)
    from .draft_group_runtime_host import PinnedFile
    p=PinnedFile(pins.configuration_path,pins.configuration_sha,2*1024*1024)
    try:
        import json
        value=json.loads(p.raw)
        need(value['binding']['source_kind']=='SYNTHETIC_SETUP' and value['binding']['account']==policy.data['appid'])
    finally:p.close()
    names=('configuration','semantic','source','review','arm_receipt','unarmed','armed')
    paths=tuple((name,(str(getattr(pins,name+'_path')),getattr(pins,name+'_sha')))for name in names)
    lookups=tuple((str(l.state_path),str(l.session_root),l.owner_thread,tuple(l.allowed_threads))for l in pins.lookups)
    row=('rich-syn-c1',stable_account({'appid':policy.data['appid']}),policy.value['candidate_scope'],paths,lookups,
        tuple((key,str(path))for key,path in pins.artifact_roots),tuple((str(p),h)for p,h in pins.helper_files),
        tuple((str(p),h)for p,h in pins.retention_evidence))
    key=(str(policy.root),pins.configuration_sha);old=_HISTORY_JOBS.get(key)
    record=(canonical(policy.data),policy.fingerprint,row,pins)
    need(old is None or old[:3]==record[:3],'GROUP_RICH_SYN_HISTORY_JOB_CHANGED')
    _HISTORY_JOBS[key]=record


def rich_syn_history_row(policy,configuration_sha):
    """Original SYN material locator only; no current/owner or prefix refresh."""
    assert_rich_syn_fixture_tcb()
    from .draft_group_contracts import canonical
    record=_HISTORY_JOBS.get((str(policy.root),configuration_sha))
    if record is None:return None
    need(canonical(policy.data)==record[0] and policy.fingerprint==record[1], 'GROUP_RICH_SYN_HISTORY_POLICY_CHANGED')
    return record[2]


def rich_syn_host_pins_for_policy(policy):
    assert_rich_syn_fixture_tcb()
    found=[(domain,r)for domain,r in _DOMAINS.items() if r.policy is policy and r.thread==_THREAD() and r.phase in ('PREPARING','ACTIVE')]
    if not found:return None
    need(len(found)==1);domain,r=found[0]
    values=[item for (root,_),item in _HISTORY_JOBS.items() if root==str(policy.root) and item[1]==policy.fingerprint]
    need(len(values)==1);return values[0][3]



def _register_runtime_source(domain,pins):
    r=_record(domain)
    values=[value for value in _SESSIONS.values()if value[0]is domain and value[1]['pins']is pins]
    need(len(values)==1 and r.phase=='PREPARING'and r.entry is None,'GROUP_RICH_SYN_RUNTIME_FACTORY_REQUIRED')
    if pins.runtime_source_policy is None:
        need(pins.catalog_runtime_source is None);return
    from .draft_group_native_v2_codec import CATALOG_EXTENSION_KEYS,MODE
    from .draft_group_input_files import _closed
    from .draft_group_contracts import canonical
    pair=pins.runtime_source_policy;extension=pins.catalog_runtime_source
    _closed(extension,CATALOG_EXTENSION_KEYS)
    need(type(pair)is tuple and len(pair)==2 and type(pair[0])is type(Path('/'))
         and pair[0].is_relative_to(r.fixture_root)
         and extension['profile']=='GROUP_CATALOG_RUNTIME_SOURCE_V1'and extension['mode']==MODE
         and extension['native_qualification']=='NOT_ASSERTED'and extension['baseline_source_sha']==pins.source_sha
         and extension['runtime_policy_path']==str(pair[0])and extension['runtime_policy_sha']==pair[1],
         'GROUP_RICH_SYN_RUNTIME_SOURCE_BINDING')
    from .draft_group_runtime_host import PinnedFile
    need(type(r.fixture_pool)is PinPool and r.fixture_pool.owner is r.fixture_owner,'GROUP_RICH_SYN_RESOURCE_OWNER')
    file=PinnedFile(pair[0],pair[1],2*1024*1024,pool=r.fixture_pool,owner=r.fixture_owner)
    _DOMAINS[domain]=replace(r,pins=r.pins+(file,))
    key=(str(r.policy.root),pins.configuration_sha)
    need(key not in _RUNTIME_JOBS,'GROUP_RICH_SYN_RUNTIME_SOURCE_DUPLICATE')
    _RUNTIME_JOBS[key]=(pins,canonical(extension),pair)


def rich_syn_runtime_policy_pin_for(pins,policy):
    assert_rich_syn_fixture_tcb()
    from .draft_group_contracts import canonical
    history=_HISTORY_JOBS.get((str(policy.root),pins.configuration_sha))
    facts=_RUNTIME_JOBS.get((str(policy.root),pins.configuration_sha))
    if facts is None:return None
    need(history is not None and history[3]is pins and history[0]==canonical(policy.data)and history[1]==policy.fingerprint
         and facts[0]is pins and facts[1]==canonical(pins.catalog_runtime_source)and facts[2]==pins.runtime_source_policy,
         'GROUP_RICH_SYN_RUNTIME_SOURCE_CHANGED')
    import json
    return facts[2][0],facts[2][1],json.loads(facts[1])


def rich_syn_native_v2_history_pins(policy,configuration_sha):
    assert_rich_syn_fixture_tcb()
    history=_HISTORY_JOBS.get((str(policy.root),configuration_sha))
    if history is None or (str(policy.root),configuration_sha)not in _RUNTIME_JOBS:return None
    pins=history[3];rich_syn_runtime_policy_pin_for(pins,policy)
    return pins

def _capture_fixture_resources(module):
    functions=tuple((name,value,value.__code__)for name,value in vars(module).items()
        if type(value)is _ResourceFunctionType and value.__module__==module.__name__)
    classes=[];pending=[fn for _,fn,_ in functions]
    for name,cls in tuple(vars(module).items()):
        if type(cls)is type and cls.__module__==module.__name__:
            attrs=dict(type.__getattribute__(cls,'__dict__'));methods=[]
            for value in attrs.values():
                if type(value)is property:methods.extend(fn for fn in (value.fget,value.fset,value.fdel)if fn is not None)
                elif type(value)in (staticmethod,classmethod):methods.append(value.__func__)
                elif type(value)is _ResourceFunctionType:methods.append(value)
            pending.extend(methods)
            classes.append((name,cls,cls.__bases__,cls.__mro__,attrs,tuple((fn,fn.__code__)for fn in methods)))
    seen=set();closures=[]
    while pending:
        fn=pending.pop()
        if type(fn)is not _ResourceFunctionType or id(fn)in seen:continue
        seen.add(id(fn));cells=tuple((cell,cell.cell_contents)for cell in (fn.__closure__ or ()))
        closures.append((fn,fn.__code__,cells))
        pending.extend(value for _,value in cells if type(value)is _ResourceFunctionType)
        wrapped=getattr(fn,'__wrapped__',None)
        if type(wrapped)is _ResourceFunctionType:pending.append(wrapped)
    constants=tuple((name,vars(module)[name])for name in ('TRANSIENT_FDS','MAX_RAW_BYTES'))
    return module,functions,tuple(classes),tuple(closures),constants


def _assert_fixture_resources():
    module,functions,classes,closures,constants=_RESOURCE_TCB
    need(module is _pin_resources,'GROUP_RICH_SYN_RESOURCE_TCB_CHANGED')
    for name,fn,code in functions:
        need(vars(module).get(name)is fn and fn.__code__ is code,'GROUP_RICH_SYN_RESOURCE_TCB_CHANGED')
    for name,cls,bases,mro,attributes,methods in classes:
        need(vars(module).get(name)is cls and cls.__bases__==bases and cls.__mro__==mro
             and dict(type.__getattribute__(cls,'__dict__'))==attributes
             and all(fn.__code__ is code for fn,code in methods),'GROUP_RICH_SYN_RESOURCE_TCB_CHANGED')
    for fn,code,cells in closures:
        need(fn.__code__ is code and all(cell.cell_contents is value for cell,value in cells),
             'GROUP_RICH_SYN_RESOURCE_TCB_CHANGED')
    need(all(vars(module).get(name)==value and type(vars(module).get(name))is type(value)for name,value in constants),
         'GROUP_RICH_SYN_RESOURCE_TCB_CHANGED')


def assert_rich_syn_fixture_tcb():
    # Verify helpers/primitives before calling even the local assertion helper.
    if any(globals().get(name) is not fn or fn.__code__ is not code for name,fn,code in _FUNCTION_PINS):
        raise WCEError('GROUP_RICH_SYN_TCB_CHANGED')
    if any(globals().get(name) is not original for name,original in _PRIMITIVE_PINS):
        raise WCEError('GROUP_RICH_SYN_TCB_CHANGED')
    _assert_fixture_resources()
    for fn,code,cells in _CLOSURE_PINS:
        need(fn.__code__ is code and all(cell.cell_contents is original for cell,original in cells))
    for name,fn,code in _FUNCTION_PINS:
        need(globals().get(name) is fn and fn.__code__ is code)
    for cls,bases,mro,items in _CLASS_PINS:
        attrs=type.__getattribute__(cls,'__dict__')
        need(type.__getattribute__(cls,'__bases__')==bases and type.__getattribute__(cls,'__mro__')==mro
             and tuple(attrs)==tuple(name for name,_,_ in items))
        for name,value,code in items:need(attrs[name] is value and (code is None or value.__code__ is code))


_RESOURCE_TCB=_capture_fixture_resources(_pin_resources)

RICH_FIXTURE_TCB_NAMES=tuple(name for name,value in tuple(globals().items())if getattr(value,'__module__',None)==__name__ and hasattr(value,'__code__'))
_FUNCTION_PINS=tuple((name,globals()[name],globals()[name].__code__)for name in RICH_FIXTURE_TCB_NAMES)
_CLASS_PINS=tuple((cls,type.__getattribute__(cls,'__bases__'),type.__getattribute__(cls,'__mro__'),
    tuple((name,value,getattr(value,'__code__',None)) for name,value in type.__getattribute__(cls,'__dict__').items()))
    for cls in (RichSYNFixtureDomain,RichSYNFixtureSession,RichSYNDomainFacts,_DomainRecord))


# contextmanager wrappers and descriptor functions retain mutable function
# objects. Pin their actual code and closure cells, not merely the wrapper.
def _closure_images():
    from types import FunctionType
    pending=[fn for _,fn,_ in _FUNCTION_PINS]
    for cls,*_ in _CLASS_PINS:
        for value in vars(cls).values():
            if type(value) is property:pending.extend(fn for fn in (value.fget,value.fset,value.fdel) if fn is not None)
            elif type(value) in (staticmethod,classmethod):pending.append(value.__func__)
            elif type(value) is FunctionType:pending.append(value)
    found={};images=[]
    while pending:
        fn=pending.pop()
        if type(fn) is not FunctionType or id(fn) in found:continue
        found[id(fn)]=fn;cells=tuple((cell,cell.cell_contents)for cell in (fn.__closure__ or ()))
        images.append((fn,fn.__code__,cells))
        pending.extend(value for _,value in cells if type(value) is FunctionType)
        wrapped=getattr(fn,'__wrapped__',None)
        if type(wrapped) is FunctionType:pending.append(wrapped)
    return tuple(images)

_CLOSURE_PINS=_closure_images()

_PRIMITIVE_PINS=tuple((name,globals()[name])for name in ('_THREAD', '_MONOTONIC', 'PinPool', 'close_all', '_pin_resources', '_ResourceFunctionType'))


from .draft_group_history_context import history_transaction as _history_transaction
