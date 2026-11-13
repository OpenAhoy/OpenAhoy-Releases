"""Private, zero-write Group journal readers; not wired to MCP.

Host-selected policy/actor only. No AccountService, token, provider, migration,
ordinary writer-lock creation, grant or execution owner. Production wrappers
fix OPERATOR_ATTESTED. The private synthetic helper is only for local fixtures.
"""
from contextlib import ExitStack, contextmanager
from functools import wraps
from hashlib import sha256
import math
import os
from pathlib import Path
import sqlite3
import stat

from .bounded_file import file_state, identity
from .contracts import Actor, WCEError
from .draft_group_contracts import canonical
from .draft_revision_guard import historical_identity_guard, policy_binding
from .own_bootstrap_security import path_check
from .own_connection_policy import ConnectionPolicy, locked, load_policy
from .own_store import OwnStore
from .own_validation_scope import OwnedConnection
from .publication_lock import MARKER, _marker
from .service import digest

_PATH_TYPE=type(Path('/'))
_EXCEPTION_DICT=BaseException.__dict__['__dict__']
_PUBLIC_ERRORS=frozenset(('GROUP_LOCAL_IDENTITY_HOLD','GROUP_LOCAL_STATE_HOLD',
    'GROUP_LOCAL_READER_BUSY','GROUP_LOCAL_CHANGED','GROUP_LOCAL_SIDECAR_HOLD',
    'GROUP_LOCAL_SCHEMA_HOLD','GROUP_LOCAL_PROJECTION_BOUND'))
_OP_STATES=frozenset(('PLANNED','WAITING','BASELINES_OBSERVED','ADD_ADMITTED',
    'NEW_OBSERVED','NEW_VERIFIED','OLD_BASELINES_RECHECKED','SWITCHED_OLD_RETAINED',
    'RETIRING','UNKNOWN','HOLD','COMPLETE','CANCELLED_BEFORE_ADMISSION'))
_OLD_STATES=frozenset(('RETAINED','DELETE_ADMITTED','DELETE_ACK_OK','DELETE_UNKNOWN',
    'DELETE_KNOWN_REJECTED','INVALIDATED_OBSERVED','RETIREMENT_VERIFIED'))

def fail(code='GROUP_LOCAL_STATE_HOLD'):raise WCEError(code)

def _bounded(fn):
    @wraps(fn)
    def call(*args,**kwargs):
        try:return fn(*args,**kwargs)
        except Exception as error:
            code=None
            if type(error) is WCEError:
                value=_EXCEPTION_DICT.__get__(error,BaseException)
                code=dict.get(value,'code') if type(value) is dict else None
            if type(code) is str:
                if code=='CONNECTION_BUSY':code='GROUP_LOCAL_READER_BUSY'
                if code in _PUBLIC_ERRORS:raise WCEError(code) from None
            raise WCEError('GROUP_LOCAL_STATE_HOLD') from None
    return call

def _plain(value,depth=0,counter=None):
    if counter is None:counter=[16384]
    counter[0]-=1
    if counter[0]<0 or depth>32:fail('GROUP_LOCAL_IDENTITY_HOLD')
    kind=type(value)
    if kind is dict:
        if any(type(k) is not str for k in value):fail('GROUP_LOCAL_IDENTITY_HOLD')
        for key,item in value.items():_plain(key,depth+1,counter);_plain(item,depth+1,counter)
    elif kind is list:
        for item in value:_plain(item,depth+1,counter)
    elif kind is str:
        if len(value)>16384:fail('GROUP_LOCAL_IDENTITY_HOLD')
    elif kind is float:
        if not math.isfinite(value):fail('GROUP_LOCAL_IDENTITY_HOLD')
    elif kind not in (int,bool,type(None)):fail('GROUP_LOCAL_IDENTITY_HOLD')

def _id(value):
    from .draft_group_contracts import identifier
    return identifier(value)

def _hash(value):
    from .draft_group_contracts import sha
    return sha(value)

def _int(value,maximum=2**63-1):
    if type(value) is not int or not 0<=value<=maximum:fail()
    return value

def _authorize(policy,actor):
    if type(policy) is not ConnectionPolicy or type(actor) is not Actor:fail('GROUP_LOCAL_IDENTITY_HOLD')
    if type(policy.path) is not _PATH_TYPE or policy.path.name!='connection-policy.json':fail('GROUP_LOCAL_IDENTITY_HOLD')
    _plain(policy.value)
    if type(policy.value.get('schema')) is not int or policy.value['schema'] not in (1,2):fail('GROUP_LOCAL_IDENTITY_HOLD')
    for pin,length in ((policy.pin,6),(policy.root_pin,2),(policy.image_pin,2),(policy.database_pin,6)):
        if type(pin) is not tuple or len(pin)!=length or any(type(v) is not int for v in pin):fail('GROUP_LOCAL_IDENTITY_HOLD')
    actual=policy.actor
    for name in ('tenant_id','principal_id','client_id','session_id'):
        left=getattr(actor,name);right=getattr(actual,name)
        if type(left) is not str or type(right) is not str or left!=right:fail('GROUP_LOCAL_IDENTITY_HOLD')
    current=load_policy(policy.path,active=False)
    # The old historical helper compares dictionaries with Python equality.
    # Bind exact identity bytes too: True must not alias generation/epoch 1.
    if digest(current.data)!=digest(policy.data):fail('GROUP_LOCAL_IDENTITY_HOLD')
    guard=historical_identity_guard(policy)
    guard()
    return guard

def _pin_file(path,maximum):
    """Read only a fixed metadata/proof file, with descriptor and path pins."""
    if not os.path.lexists(path):return None
    before=path_check(path);parent=path_check(path.parent,True)
    directory=os.open(path.parent,os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW|os.O_NONBLOCK)
    fd=None
    try:
        if identity(os.fstat(directory))!=parent:fail('GROUP_LOCAL_CHANGED')
        fd=os.open(path.name,os.O_RDONLY|os.O_NOFOLLOW|os.O_NONBLOCK,dir_fd=directory)
        info=os.fstat(fd)
        if file_state(info)!=before or not 0<info.st_size<=maximum:fail('GROUP_LOCAL_CHANGED')
        checksum=sha256();used=0
        while True:
            chunk=os.read(fd,min(65536,maximum+1-used))
            if not chunk:break
            used+=len(chunk)
            if used>maximum:fail('GROUP_LOCAL_CHANGED')
            checksum.update(chunk)
        if (used!=info.st_size or file_state(os.fstat(fd))!=before
                or path_check(path)!=before or path_check(path.parent,True)!=parent):fail('GROUP_LOCAL_CHANGED')
        return (before,checksum.hexdigest())
    finally:
        if fd is not None:os.close(fd)
        os.close(directory)

def _metadata(policy):
    root=policy.root
    result={'root':path_check(root,True),'images':path_check(root/'images',True)}
    paths=((policy.path,16384),(root/MARKER,16384),
        (root/'draft-restore-migration.json',512*1024),(root/'replacement-registry.json',16384),
        (root/'group-schema-migration.json',8192),(root/'group-schema-checkpoint.json',64*1024*1024))
    paths+=((root/'group-prerequisite6-migration.json',8192),
        (root/'group-prerequisite6-checkpoint.json',64*1024*1024),
        (root/'group-prerequisite6-proof.json',16384))
    if policy.value['schema']==2:
        registry=Path(policy.value['registry_path']);transaction=policy.value['transaction']
        paths+=((registry,512*1024),(registry.parent/'connection-owner.json',16384),
            (registry.parent/'connection-transactions'/(transaction+'.json'),512*1024),
            (root/'profile.json',16384))
    for path,maximum in paths:result[str(path)]=_pin_file(path,maximum)
    return result

def _no_sidecars(path):
    if any(os.path.lexists(Path(str(path)+tail)) for tail in ('-wal','-shm','-journal')):
        fail('GROUP_LOCAL_SIDECAR_HOLD')

def _rollback_header(path,pin):
    # A ro SQLite WAL opener may need/create shared-memory sidecars. Reject its
    # persistent header *before* connecting, including when WAL files are absent.
    fd=os.open(path,os.O_RDONLY|os.O_NOFOLLOW|os.O_NONBLOCK)
    try:
        if file_state(os.fstat(fd))!=pin:fail('GROUP_LOCAL_CHANGED')
        header=os.read(fd,100)
        if len(header)!=100 or header[:16]!=b'SQLite format 3\x00':fail('GROUP_LOCAL_SCHEMA_HOLD')
        if header[18:20]!=b'\x01\x01':fail('GROUP_LOCAL_SIDECAR_HOLD')
        if file_state(os.fstat(fd))!=pin or path_check(path)!=pin:fail('GROUP_LOCAL_CHANGED')
    finally:os.close(fd)

def _fd_current(path,fd,pin):
    info=os.fstat(fd)
    if (not stat.S_ISREG(info.st_mode) or info.st_uid!=os.getuid()
            or stat.S_IMODE(info.st_mode)!=0o600 or info.st_nlink!=1 or info.st_size!=0
            or file_state(info)!=pin or path_check(path)!=pin):fail('GROUP_LOCAL_CHANGED')

def _coordination(policy):
    value=_marker(policy.root,policy.data['appid'])
    if value is not None:
        if (type(value) is not dict or type(value['schema']) is not int or value['schema']!=1
                or type(value['anchor_identity']) is not list or len(value['anchor_identity'])!=2
                or any(type(v) is not int for v in value['anchor_identity'])):fail()
        _hash(value['account_key'])
    return value

@contextmanager
def _readonly_locks(policy):
    """Existing shared locks in the exact stable-account→local writer order."""
    root=policy.root;initial=_coordination(policy);descriptors=[]
    with ExitStack() as stack:
        if initial is not None:
            anchor=Path(initial['anchor']);pin=path_check(anchor,True)
            path=anchor/'publication.lock'
            fd=stack.enter_context(locked(path,nonblocking=True,shared=True,existing=True,readonly=True))
            descriptors.append((path,fd,file_state(os.fstat(fd))))
        else:anchor=None;pin=None
        path=root/'publication-dispatch.lock'
        fd=stack.enter_context(locked(path,nonblocking=True,shared=True,existing=True,readonly=True))
        descriptors.append((path,fd,file_state(os.fstat(fd))))
        def current():
            if _coordination(policy)!=initial:fail('GROUP_LOCAL_CHANGED')
            if anchor is not None and path_check(anchor,True)!=pin:fail('GROUP_LOCAL_CHANGED')
            for path,fd,expected in descriptors:_fd_current(path,fd,expected)
        current()
        yield initial,current
        current()

@contextmanager
def _readonly_database(policy):
    """Normal owned RO snapshot, with one H through every caller fence."""
    from .own_history_source import owned_connection
    from .own_history_locators import history_scope
    path=policy.root/'state.sqlite3';parent=path_check(path.parent,True)
    before=path_check(path);_no_sidecars(path)
    if before[:2]!=policy.database_pin[:2]:fail('GROUP_LOCAL_CHANGED')
    _rollback_header(path,before)
    with owned_connection(path,readonly=True,isolation_level=None,timeout=0) as db:
        db.row_factory=sqlite3.Row
        try:
            db.execute('PRAGMA query_only=ON');db.execute('PRAGMA trusted_schema=OFF')
            db.execute('PRAGMA foreign_keys=ON');db.execute('BEGIN')
            if path_check(path)!=before:fail('GROUP_LOCAL_CHANGED')
            if db.execute('PRAGMA journal_mode').fetchone()[0].lower()=='wal':fail('GROUP_LOCAL_SIDECAR_HOLD')
            _no_sidecars(path)
            from .draft_group_history_context import history_policy_context
            with history_policy_context(path,db,policy):
                with history_scope(policy,db) as history_locators:
                    yield db,history_locators
                    _no_sidecars(path)
                    if path_check(path)!=before or path_check(path.parent,True)!=parent:fail('GROUP_LOCAL_CHANGED')
        finally:
            if db.in_transaction:db.rollback()

def _base(kind,key):
    return {'schema':1,'kind':kind,'handle':key,'state':'NOT_FOUND','lookup':'NOT_FOUND',
        'reason':None,'pool_capacity_known':False,'counts':None,'caps':None,'remaining':None,
        'route':'OFF','authority':'NONE_LOCAL_OBSERVATION','platform_verified':False,'titles':[]}

def _counts(op):
    used={k:sum(claim['kind']==k for claim in op['claims']) for k in ('GET','ADD','DELETE')}
    budget=op['plan']['budget'];caps={'GET':budget['get_cap'],'ADD':budget['add_cap'],'DELETE':budget['delete_cap']}
    for k in used:
        _int(used[k]);_int(caps[k])
        if used[k]>caps[k]:fail()
    return used,caps,{k:caps[k]-used[k] for k in used}

def _status_projection(state,key):
    result=_base('STATUS',key)
    if state is None or state['pool'] is None:
        result.update(state='POOL_NOT_INITIALIZED',reason='GROUP_POOL_NOT_INITIALIZED');return result
    op=state['operations'].get(key)
    if op is None:return result
    if type(op['state']) is not str or op['state'] not in _OP_STATES:fail()
    used,caps,remaining=_counts(op);plan=op['plan'];batch=state['batches'][op['batch_id']]
    olds=[]
    for old in op['old_refs']:
        if type(old['state']) is not str or old['state'] not in _OLD_STATES:fail()
        olds.append({'old_index':_int(old['old_index'],7),'state':old['state'],'ref_sha':_hash(old['ref_sha'])})
    if len(olds)>8:fail('GROUP_LOCAL_PROJECTION_BOUND')
    from .draft_group_store import _sticky_read_failure
    failure=_sticky_read_failure(op)
    reason=('GROUP_RESULT_UNKNOWN' if failure['outcome']=='UNKNOWN' else 'GROUP_SOURCE_DRIFT') if failure is not None else None
    if reason is None:
        if op['cancelled']:reason='GROUP_CANCELLED'
        elif op['state']=='UNKNOWN' or any(c['state'] in ('UNKNOWN','CONSUMED_UNKNOWN') for c in op['claims']):reason='GROUP_RESULT_UNKNOWN'
        elif op['state']=='HOLD':reason='GROUP_LOCAL_JOURNAL_HOLD'
    result.update(state=op['state'],lookup='FOUND',reason=reason,counts=used,caps=caps,remaining=remaining,
        cancelled=op['cancelled'],ordinal=_int(op['ordinal'],63),next_ordinal=_int(batch['next_ordinal'],63),
        member_count=_int(plan['member_count'],8),members_sha=digest(plan['members']),
        batch_sha=digest(op['batch_id']),pool_head_sha=_hash(state['pool']['head']),old_references=olds)
    return result

def _preview_projection(state,key):
    result=_base('PREVIEW',key)
    if state is None:
        result.update(state='POOL_NOT_INITIALIZED',reason='GROUP_POOL_NOT_INITIALIZED');return result
    preview=state['previews'].get(key)
    if preview is None:return result
    ledgers=[]
    for gid,grant in state['preview_grants'].items():
        reg=grant['registration']
        if reg['scope_sha']!=preview['scope_sha']:continue
        used={api:sum(c['api']==api for c in grant['claims']) for api in ('LIST','GET')}
        caps={'LIST':reg['list_cap'],'GET':reg['get_cap']}
        for api in used:
            _int(used[api]);_int(caps[api])
            if used[api]>caps[api]:fail()
        ledgers.append({'grant_sha':_hash(gid),'phase':reg['phase'],'state':'HOLD' if grant['hold'] else 'RECORDED',
            'counts':used,'caps':caps,'remaining':{api:caps[api]-used[api] for api in used}})
    if len(ledgers)>64:fail('GROUP_LOCAL_PROJECTION_BOUND')
    result.update(state='PREVIEW_LOCAL',lookup='FOUND',input_sha=_hash(preview['input_sha']),
        scope_sha=_hash(preview['scope_sha']),evidence_sha=_hash(preview['evidence_sha']),
        candidate_sha=digest(preview['candidate']),read_ledgers=sorted(ledgers,key=lambda x:x['grant_sha']))
    return result

def _batch_projection(state,key):
    """Expose existing operation handles, never a candidate or a new plan."""
    result=_base('PLAN',key)
    if state is None or state['pool'] is None:
        result.update(state='POOL_NOT_INITIALIZED',reason='GROUP_POOL_NOT_INITIALIZED');return result
    batch=state['batches'].get(key)
    if batch is None:return result
    candidate=batch['candidate']
    if (candidate['batch_id']!=key or type(batch['state']) is not str
            or batch['state'] not in ('PLANNED','ACTIVE','HOLD','UNKNOWN','COMPLETE','CANCELLED_BEFORE_ADMISSION',
                                      'CANCELLED_WITH_RESIDUE')):fail()
    children=candidate['children']
    if type(children) is not list or not 1<=len(children)<=64:fail('GROUP_LOCAL_PROJECTION_BOUND')
    operations=[]
    for ordinal,child in enumerate(children):
        operation_id=_id(child['operation_id'])
        op=state['operations'].get(operation_id)
        if op is None or op['batch_id']!=key or op['ordinal']!=ordinal:fail()
        projection=_status_projection(state,operation_id)
        operations.append({name:projection[name] for name in
            ('handle','state','reason','ordinal','member_count','members_sha','counts','caps','remaining')})
    result.update(state=batch['state'],lookup='FOUND',cancelled=batch['cancelled'],
        next_ordinal=_int(batch['next_ordinal'],63),operation_count=len(operations),operations=operations,
        pool_head_sha=_hash(state['pool']['head']))
    return result

@_bounded
def _validated_projection(db,policy,key,kind,source_kind,version, *, history_locators=None):
    # Normalize unexpected validator exceptions here, while still *inside* the
    # read transaction. Contextmanager unwinding must see only our exact error,
    # rather than invoking arbitrary exception-subclass attribute hooks.
    OwnStore.check(db,source_kind,policy, history=history_locators)
    if version<9:
        owner=object.__new__(OwnStore);owner.path=policy.root/'state.sqlite3';owner.history_policy=policy
        owner._check_legacy_history(db,source_kind, history=history_locators)
        result=_base(kind,key);result.update(state='POOL_NOT_INITIALIZED',reason='GROUP_POOL_NOT_INITIALIZED')
        return result
    from .draft_group_store import _load
    state,_,_=_load(db,digest(policy_binding(policy,source_kind)))
    if kind=='STATUS':
        result=_status_projection(state,key)
        result['parent_registration']='ABSENT'
        if result['lookup']=='FOUND':
            # Full schema9 integrity above has already run. Use the sole B
            # historical Parent reader, never infer permission from PLAN alone.
            from .draft_group_parent import check_parent_records_in
            history=check_parent_records_in(db,history_policy=policy, history_locators=history_locators)
            execution=history['executions'].get(key)
            if execution is not None:
                operation=state['operations'][key];batch=state['batches'][operation['batch_id']]
                parent=execution['parent'];plan=execution['plan_event']['payload']
                if (parent['binding_sha']!=state['binding_sha']
                    or parent['batch_id']!=operation['batch_id']
                    or digest(parent)!=batch['execution']['parent_grant_sha']
                    or canonical(plan['execution'])!=canonical(batch['execution'])
                    or canonical(execution['child'])!=canonical(operation['plan'])):fail()
                result['parent_registration']='REGISTERED_HISTORICAL'
        return result
    if kind=='PLAN':return _batch_projection(state,key)
    return _preview_projection(state,key)

def _read(policy,actor,key,kind,source_kind):
    """Private fixture seam. Production wrappers below supply the fixed kind."""
    _id(key)
    if type(kind) is not str or kind not in ('STATUS','PREVIEW','PLAN'):fail()
    if type(source_kind) is not str or source_kind not in ('OPERATOR_ATTESTED','SYNTHETIC_SETUP'):fail()
    guard=_authorize(policy,actor);before=_metadata(policy)
    with _readonly_locks(policy) as (coordination,locks_current):
        guard();locks_current()
        if _metadata(policy)!=before:fail('GROUP_LOCAL_CHANGED')
        with _readonly_database(policy) as (db, history_locators):
            version=db.execute('PRAGMA user_version').fetchone()[0]
            if type(version) is not int or version not in (4,5,6,7,8,9):fail('GROUP_LOCAL_SCHEMA_HOLD')
            if version>=7 and coordination is None:fail('GROUP_LOCAL_STATE_HOLD')
            result=_validated_projection(db,policy,key,kind,source_kind,version, history_locators=history_locators)
            if _metadata(policy)!=before:fail('GROUP_LOCAL_CHANGED')
            guard();locks_current()
        guard();locks_current()
        if _metadata(policy)!=before:fail('GROUP_LOCAL_CHANGED')
    guard()
    if _metadata(policy)!=before:fail('GROUP_LOCAL_CHANGED')
    return result

@_bounded
def read_status(policy,host_actor,operation_id):
    return _read(policy,host_actor,operation_id,'STATUS','OPERATOR_ATTESTED')

@_bounded
def read_preview(policy,host_actor,preview_id):
    return _read(policy,host_actor,preview_id,'PREVIEW','OPERATOR_ATTESTED')

@_bounded
def read_plan(policy,host_actor,batch_handle,request_key):
    _id(request_key)
    _authorize(policy,host_actor)()
    expected='group-batch-'+digest({'binding_sha':digest(policy_binding(policy,'OPERATOR_ATTESTED')),
                                  'request_key':request_key})
    if type(batch_handle) is not str or batch_handle!=expected:fail('GROUP_LOCAL_IDENTITY_HOLD')
    return _read(policy,host_actor,batch_handle,'PLAN','OPERATOR_ATTESTED')
