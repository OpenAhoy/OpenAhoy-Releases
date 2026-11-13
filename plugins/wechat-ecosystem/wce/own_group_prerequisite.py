"""Neutral business6→8 component. No grant, network, discovery, or SQL commit.

Caller is the independently qualified maintenance producer and keeps its real
writer/policy exclusion and backup. These data/functions do not confer authority.
"""
from contextlib import closing, contextmanager
from contextvars import ContextVar
from hashlib import sha256
import os
from pathlib import Path
import sqlite3

from .contracts import WCEError
from .service import canonical, digest

PROFILE='NEUTRAL_OWN_SCHEMA6_TO8_V1'
CHECKPOINT='group-prerequisite6-checkpoint.json'
MARKER='group-prerequisite6-migration.json'
PROOF='group-prerequisite6-proof.json'
_SCOPE=ContextVar('group_neutral_prerequisite_scope',default=None)


def fail(): raise WCEError('GROUP_PREREQUISITE_UNVERIFIED')

def _g():
    from . import own_group_schema
    return own_group_schema


def _version(db):
    from .own_store import APP_ID
    v=db.execute('PRAGMA user_version').fetchone()[0]
    if db.execute('PRAGMA application_id').fetchone()[0]!=APP_ID or v not in (6,7,8,9):fail()
    return v


def _schema6():
    from .own_store import SCHEMA
    from .own_lineage import SCHEMA as L
    from .own_lineage_replacement import SCHEMA as R
    return SCHEMA+L+R


def contract_sha():
    return digest({'profile':PROFILE,'base':6,'target':8,'ddl6':sha256(_schema6().encode()).hexdigest(),
        'ddl8':sha256(_g().legacy_schema().encode()).hexdigest(),'old_marker':'ABSENT_OR_EXACT_ROLLED_BACK6',
        'authority':False,'delta':'FROZEN033_LEGACY_TYPED_PINS_AND_MONOTONE_RESULTS_V1'})


def _inventory6(db):return _g()._inventory_for_schema(db,_schema6())


def _layout(db,source,version):
    from .own_store import APP_ID
    if type(source) is not str or source not in ('SYNTHETIC_SETUP','OPERATOR_ATTESTED'):fail()
    if _version(db)!=version or version not in (6,8):fail()
    script=_schema6() if version==6 else _g().legacy_schema()
    with closing(sqlite3.connect(':memory:')) as expected:
        expected.executescript(script)
        if _g()._fingerprint(db)!=_g()._fingerprint(expected):fail()
    rows=db.execute('SELECT * FROM own_config').fetchall()
    if len(rows)!=1 or dict(rows[0])!={'id':1,'source_kind':source}:fail()
    if db.execute('PRAGMA foreign_key_check').fetchone():fail()


def _old_marker(db):
    path=_g()._root(db)/'draft-restore-migration.json'
    if not os.path.lexists(path):return None
    from .own_bootstrap_security import private_read
    from .prepared_draft_fixture import decode_json
    from .own_draft_restore_contract import SUPPORTED_CONTRACTS
    raw,_=private_read(path)
    v=decode_json(raw,16384,max_nodes=100)
    keys={'schema','contract_sha','review_sha','base_version','target_version','phase'}
    if (type(v) is not dict or set(v)!=keys or type(v['schema']) is not int or v['schema']!=1
        or type(v['base_version']) is not int or v['base_version']!=6
        or type(v['target_version']) is not int or v['target_version']!=8
        or type(v['phase']) is not str or v['phase']!='ROLLED_BACK'):fail()
    _g()._hash(v['contract_sha']);_g()._hash(v['review_sha'])
    if v['contract_sha'] not in SUPPORTED_CONTRACTS:fail()
    return {'sha256':sha256(raw).hexdigest(),'phase':'ROLLED_BACK'}


def _binding(v,source,policy,db):
    _g()._binding(v,source,policy,db)


def _strict(v):
    keys={'schema','profile','operation_id','source_kind','binding_sha','code_scope','contract_sha',
        'source_sha','backup_sha','base_version','target_version','ddl6_sha','ddl8_sha','inventory',
        'old_restore_marker','coordination'}
    if type(v) is not dict or set(v)!=keys:fail()
    if type(v['schema']) is not int or v['schema']!=1 or type(v['profile']) is not str or v['profile']!=PROFILE:fail()
    _g()._id(v['operation_id'])
    if type(v['source_kind']) is not str or v['source_kind'] not in ('SYNTHETIC_SETUP','OPERATOR_ATTESTED'):fail()
    for k in ('binding_sha','code_scope','contract_sha','source_sha','backup_sha','ddl6_sha','ddl8_sha'):_g()._hash(v[k])
    if (type(v['base_version']) is not int or v['base_version']!=6 or type(v['target_version']) is not int
        or v['target_version']!=8 or v['contract_sha']!=contract_sha()
        or v['ddl6_sha']!=sha256(_schema6().encode()).hexdigest()
        or v['ddl8_sha']!=sha256(_g().legacy_schema().encode()).hexdigest() or type(v['inventory']) is not dict):fail()
    old=v['old_restore_marker']
    if old is not None:
        if type(old) is not dict or set(old)!={'sha256','phase'} or type(old['phase']) is not str or old['phase']!='ROLLED_BACK':fail()
        _g()._hash(old['sha256'])
    c=v['coordination']
    if type(c) is not dict or set(c)!={'anchor','parent_identity','before'} or type(c['anchor']) is not str:fail()
    a=Path(c['anchor'])
    if not a.is_absolute() or '..' in a.parts or a.parent.name!='publication-anchors':fail()
    if type(c['parent_identity']) is not list or len(c['parent_identity'])!=2 or any(type(x) is not int for x in c['parent_identity']):fail()
    _strict_coord(c['before'],allow_none=True)
    return v


def _strict_coord(c,*,allow_none=False):
    if allow_none and c is None:return
    if type(c) is not dict or set(c)!={'pin_sha','head_sha','anchor_identity'}:fail()
    _g()._hash(c['pin_sha']);_g()._hash(c['head_sha'])
    if type(c['anchor_identity']) is not list or len(c['anchor_identity'])!=2 or any(type(x) is not int for x in c['anchor_identity']):fail()


def _files(db,*,allow_missing_marker=False):
    root=_g()._root(db);v,h=_g()._read_json(root/CHECKPOINT,_g().MAXIMUM);_strict(v)
    if canonical(v['old_restore_marker'])!=canonical(_old_marker(db)):fail()
    m=None
    if os.path.lexists(root/MARKER):
        m,_=_g()._read_json(root/MARKER,8192)
        if (type(m) is not dict or set(m)!={'schema','operation_id','checkpoint_sha','phase','completion_proof_sha'}
            or type(m['schema']) is not int or m['schema']!=1 or type(m['phase']) is not str
            or m['phase'] not in ('PREPARED','COMMITTED','ROLLED_BACK')):fail()
        _g()._id(m['operation_id']);_g()._hash(m['checkpoint_sha'])
        if m['operation_id']!=v['operation_id'] or m['checkpoint_sha']!=h:fail()
        if m['completion_proof_sha'] is not None:_g()._hash(m['completion_proof_sha'])
        if m['phase']=='COMMITTED' and m['completion_proof_sha'] is None:fail()
        if m['phase']=='ROLLED_BACK' and m['completion_proof_sha'] is not None:fail()
    elif not allow_missing_marker:fail()
    proof=None;proof_sha=None
    if os.path.lexists(root/PROOF):
        proof,proof_sha=_g()._read_json(root/PROOF,16384)
        _strict_proof(proof,v,h)
    if m is not None:
        if m['completion_proof_sha'] is not None and m['completion_proof_sha']!=proof_sha:fail()
        if m['phase']=='ROLLED_BACK' and proof is not None:fail()
        if m['phase']=='COMMITTED' and proof is None:fail()
    elif proof is not None:fail()
    return v,h,m,proof,proof_sha


def _strict_proof(p,v,h):
    keys={'schema','profile','origin','operation_id','binding_sha','source_kind','checkpoint_sha','contract_sha',
        'source_sha','base_version','target_version','inventory_sha','ddl8_sha','old_restore_marker','coordination','phase'}
    if type(p) is not dict or set(p)!=keys:fail()
    expected={'schema':1,'profile':PROFILE,'origin':'NEUTRAL_GROUP_LAYOUT_COMPLETION','operation_id':v['operation_id'],
        'binding_sha':v['binding_sha'],'source_kind':v['source_kind'],'checkpoint_sha':h,'contract_sha':v['contract_sha'],
        'source_sha':v['source_sha'],'base_version':6,'target_version':8,'inventory_sha':digest(v['inventory']),
        'ddl8_sha':v['ddl8_sha'],'old_restore_marker':v['old_restore_marker'],'coordination':p['coordination'],'phase':'COMMITTED'}
    if canonical(expected)!=canonical(p):fail()
    _strict_coord(p['coordination'])


def _coord(db,v,policy,*,strict,allow_absent=False):
    """Fixed pin-derived anchor; no runtime caller chooses a file or account."""
    from .own_bootstrap_security import path_check,private_read
    from .publication_lock import _marker
    from .publication_contract import stable_account
    from .publication_store import PublicationStore
    if policy is None:fail()
    if policy.root!=_g()._root(db):fail()
    anchor=Path(v['coordination']['anchor'])
    if (anchor.name!=stable_account(policy.data)
        or list(path_check(anchor.parent.parent,True))!=v['coordination']['parent_identity']):fail()
    for directory in (anchor.parent,anchor):
        if os.path.lexists(directory):path_check(directory,True)
    pinpath=policy.root/'publication-coordination.json'
    if not os.path.lexists(pinpath):
        if allow_absent and v['coordination']['before'] is None:return None
        fail()
    pin=_marker(policy.root,policy.data['appid'])
    if pin is None or pin['anchor']!=str(anchor):fail()
    raw,_=private_read(pinpath);headraw,_=private_read(anchor/'head.json')
    store=PublicationStore(policy,anchor.parent.parent/'registry-unused.json')
    head=store._head()
    if strict:
        if (head['seq']!=0 or head['confirmed_seq']!=0 or head['activation_epoch']!=0 or head['event_sha']!='0'*64):fail()
        allowed={'head.json','publication.lock'}
        if any(f.name not in allowed for f in anchor.iterdir()):fail()
    elif _version(db) in (8,9):
        from .publication_lock import verify_pin
        verify_pin(store,required=True)
        store._verify_records_in(db)
    result={'pin_sha':sha256(raw).hexdigest(),'head_sha':sha256(headraw).hexdigest(),'anchor_identity':list(path_check(anchor,True))}
    _strict_coord(result)
    before=v['coordination']['before']
    if before is not None:
        if (result['pin_sha']!=before['pin_sha'] or result['anchor_identity']!=before['anchor_identity']
            or strict and result['head_sha']!=before['head_sha']):fail()
    return result


def _empty_added(db):
    old=set(_inventory6(db)); all8=_g()._inventory(db)
    if any(v['rows'] for k,v in all8.items() if k not in old):fail()


def _snapshot(db,source,policy,v,*,strict):
    version=_version(db)
    if version not in (6,8):fail()
    _layout(db,source,version)
    if strict:
        if canonical(_inventory6(db))!=canonical(v['inventory']):fail()
        if version==8:_empty_added(db)
    else:_g().verify_legacy_delta(v,db,current_inventory=_inventory6(db))
    return _coord(db,v,policy,strict=strict,allow_absent=version==6)


@contextmanager
def _scope(db,v,h,mode,policy):
    # Only fixed migrate/query functions create this object. No public setter,
    # supplied context, callback or ordinary current action can borrow it.
    coord=_coord(db,v,policy,strict=True,allow_absent=_version(db)==6)
    stamp=(id(db),v['operation_id'],h,mode,canonical(_files(db,allow_missing_marker=True)),
        policy,canonical(coord),digest(_inventory6(db)))
    token=_SCOPE.set(stamp)
    try:yield
    finally:_SCOPE.reset(token)


def _scoped(db):
    s=_SCOPE.get()
    if type(s) is not tuple or len(s)!=8 or s[0]!=id(db):return False
    v,h,_,_,_=_files(db,allow_missing_marker=True)
    if s[1]!=v['operation_id'] or s[2]!=h or s[4]!=canonical(_files(db,allow_missing_marker=True)):fail()
    version=_version(db)
    if (canonical(_coord(db,v,s[5],strict=True,allow_absent=version==6))!=s[6]
        or digest(_inventory6(db))!=s[7]):fail()
    if version==8:_empty_added(db)
    if s[3]=='MIGRATE':
        if not db.in_transaction or version not in (6,7,8):fail()
    elif s[3]=='READ':
        if version not in (6,8) or not db.in_transaction or db.execute('PRAGMA query_only').fetchone()[0]!=1:fail()
    else:fail()
    return True


def _role_root(db):
    path=db.execute('PRAGMA database_list').fetchone()[2]
    if not path:return None
    root=Path(path).parent
    if not any(os.path.lexists(root/n) for n in (CHECKPOINT,MARKER,PROOF)):return None
    return _g()._root(db)


def check_pending(db):
    root=_role_root(db)
    if root is None:return
    roles=[os.path.lexists(root/name) for name in (CHECKPOINT,MARKER,PROOF)]
    if not any(roles):return
    if not roles[0]:fail()
    v,h,m,p,ps=_files(db,allow_missing_marker=True);version=_version(db)
    if _scoped(db):return
    if m is None or m['phase']=='PREPARED':fail()
    if m['phase']=='ROLLED_BACK':
        if version!=6 or p is not None:fail()
        return
    if version not in (8,9) or p is None:fail()


def check_restore_bridge(db,marker_sha):
    if _role_root(db) is None:fail()
    v,h,m,p,ps=_files(db,allow_missing_marker=True)
    old=v['old_restore_marker']
    if old is None or old['sha256']!=marker_sha:fail()
    if _scoped(db):return
    if m is None or m['phase']!='COMMITTED' or p is None or _version(db) not in (8,9):fail()
    if _version(db)==9:
        core,_,_=_g()._files(db)
        if core['prerequisite_proof_sha']!=ps or core['operation_id']!=v['operation_id'] or core['binding_sha']!=v['binding_sha']:fail()


def check_ancestry(db,source,policy):
    root=_role_root(db)
    if root is None:return None
    v,h,m,p,ps=_files(db,allow_missing_marker=True);_binding(v,source,policy,db)
    if _scoped(db):return None
    if m is None:fail()
    version=_version(db)
    if m['phase']=='ROLLED_BACK':
        if version!=6:fail()
        _snapshot(db,source,policy,v,strict=False)
        return None
    if m['phase']!='COMMITTED' or p is None or version not in (8,9):fail()
    # No OwnStore call here: invoked from its complete validator, avoiding
    # check_marker→ancestor→OwnStore recursion. SQL9 layout is checked by core.
    if version==8:_layout(db,source,8)
    _g().verify_legacy_delta(v,db,current_inventory=_inventory6(db))
    coord=_coord(db,v,policy,strict=False)
    if coord['pin_sha']!=p['coordination']['pin_sha'] or coord['anchor_identity']!=p['coordination']['anchor_identity']:fail()
    return ps


def classify_for_core(db,source,policy,operation_id):
    root=_g()._root(db)
    if not any(os.path.lexists(root/n) for n in (CHECKPOINT,MARKER,PROOF)):return None
    v,h,m,p,ps=_files(db);_binding(v,source,policy,db)
    if m['phase']!='COMMITTED' or p is None or v['operation_id']!=operation_id:fail()
    if check_ancestry(db,source,policy)!=ps:fail()
    return ps


def verify_core_reference(db,core,source,policy):
    actual=classify_for_core(db,source,policy,core['operation_id'])
    if actual!=core['prerequisite_proof_sha']:fail()


def prepare_checkpoint(db,source,*,operation_id,binding_sha,code_scope,source_sha,backup_sha,guard,history_policy,registry, history_locators=None):
    _require_maintenance_history(history_policy,db,history_locators)
    from .own_store import OwnStore
    from .publication_store import PublicationStore
    from .own_bootstrap_security import path_check
    guard();_g()._id(operation_id)
    if not db.in_transaction or _version(db)!=6:fail()
    for x in (binding_sha,code_scope,source_sha,backup_sha):_g()._hash(x)
    _old_marker(db)
    OwnStore.check(db,source,history_policy,history=history_locators);_g()._legacy_history(db,source,history_policy,history=history_locators)
    root=_g()._root(db)
    if any(os.path.lexists(root/n) for n in (CHECKPOINT,MARKER,PROOF)):fail()
    store=PublicationStore(history_policy,registry)
    v={'schema':1,'profile':PROFILE,'operation_id':operation_id,'source_kind':source,'binding_sha':binding_sha,
        'code_scope':code_scope,'source_sha':source_sha,'backup_sha':backup_sha,'contract_sha':contract_sha(),
        'base_version':6,'target_version':8,'ddl6_sha':sha256(_schema6().encode()).hexdigest(),
        'ddl8_sha':sha256(_g().legacy_schema().encode()).hexdigest(),'inventory':_inventory6(db),'old_restore_marker':_old_marker(db),
        'coordination':{'anchor':str(store.anchor),'parent_identity':list(path_check(store.anchor_root.parent,True)),'before':None}}
    v['coordination']['before']=_coord(db,v,history_policy,strict=True,allow_absent=True)
    if v['coordination']['before'] is None:
        # Before checkpoint, only an absent or empty expected directory is legal.
        for d in (store.anchor_root,store.anchor):
            if os.path.lexists(d):
                path_check(d,True)
                if d==store.anchor:
                    for f in d.iterdir():
                        if f.name!='publication.lock':fail()
                        path_check(f)
    _strict(v);_binding(v,source,history_policy,db);guard()
    _g()._write_new(root/CHECKPOINT,v);h=sha256((canonical(v)+'\n').encode()).hexdigest();guard()
    expected_marker={'schema':1,'operation_id':operation_id,'checkpoint_sha':h,'phase':'PREPARED','completion_proof_sha':None}
    _g()._write_new(root/MARKER,expected_marker);guard()
    actual=_files(db)
    if actual[1]!=h or canonical(actual[2])!=canonical(expected_marker):fail()
    return h



def prepare_coordination(db,source,*,operation_id,checkpoint_sha,guard,history_policy,registry, history_locators=None):
    """No lock acquisition here: caller owns setup→stable→local→policy locks."""
    _require_maintenance_history(history_policy,db,history_locators)
    from .publication_store import PublicationStore
    from .publication_lock import install_pin
    _g()._id(operation_id);_g()._hash(checkpoint_sha)
    guard();v,h,m,p,ps=_files(db);_binding(v,source,history_policy,db)
    if (v['operation_id']!=operation_id or h!=checkpoint_sha or _version(db)!=6 or m['phase']!='PREPARED'
        or p is not None or not db.in_transaction):fail()
    _layout(db,source,6)
    if canonical(_inventory6(db))!=canonical(v['inventory']):fail()
    from .own_store import OwnStore
    with _scope(db,v,h,'MIGRATE',history_policy):
        OwnStore.check(db,source,history_policy,history=history_locators);_g()._legacy_history(db,source,history_policy,history=history_locators)
    guard()
    store=PublicationStore(history_policy,registry)
    if str(store.anchor)!=v['coordination']['anchor']:fail()
    if v['coordination']['before'] is None:
        from .publication_contract import CONTRACT_SHA
        expected_head={'schema':1,'account_key':store.key,'binding_sha':store.binding_sha,'contract_sha':CONTRACT_SHA,
            'activation_epoch':0,'seq':0,'event_sha':'0'*64,'confirmed_seq':0}
        if os.path.lexists(store.anchor):
            if any(f.name not in ('publication.lock','head.json') for f in store.anchor.iterdir()):fail()
            if os.path.lexists(store.head_path) and canonical(store._head())!=canonical(expected_head):fail()
        store._make_anchor();guard();install_pin(store);guard()
    result=_coord(db,v,history_policy,strict=True)
    guard()
    fresh=_files(db)
    if fresh[1]!=h or canonical(fresh[2])!=canonical(m) or canonical(_coord(db,v,history_policy,strict=True))!=canonical(result):fail()
    return result



def migrate_in(db,source,*,operation_id,checkpoint_sha,guard,history_policy,fault=lambda phase:None, history_locators=None):
    _require_maintenance_history(history_policy,db,history_locators)
    from .own_store import OwnStore
    from .publication_schema import migrate_to_7
    from .own_draft_restore_schema import migrate
    _g()._id(operation_id);_g()._hash(checkpoint_sha)
    guard();v,h,m,p,ps=_files(db);_binding(v,source,history_policy,db)
    if (v['operation_id']!=operation_id or h!=checkpoint_sha or _version(db)!=6
        or not db.in_transaction or m['phase']!='PREPARED' or p is not None):fail()
    _snapshot(db,source,history_policy,v,strict=True)
    if _coord(db,v,history_policy,strict=True) is None:fail()
    with _scope(db,v,h,'MIGRATE',history_policy):
        OwnStore.check(db,source,history_policy,history=history_locators)
        migrate_to_7(db,source,guard,history_policy=history_policy,fault=fault,history_locators=history_locators)
        migrate(db,source,guard,history_policy=history_policy,fault=fault,history_locators=history_locators)
        _snapshot(db,source,history_policy,v,strict=True)
        OwnStore.check(db,source,history_policy,history=history_locators);_g()._legacy_history(db,source,history_policy,history=history_locators)
        guard();fault('neutral_prerequisite_before_commit')
        if not _scoped(db):fail()
        OwnStore.check(db,source,history_policy,history=history_locators);_g()._legacy_history(db,source,history_policy,history=history_locators)



def query(db,source,*,operation_id,checkpoint_sha,guard,history_policy, history_locators=None):
    _g()._id(operation_id);_g()._hash(checkpoint_sha)
    try:
        _require_maintenance_history(history_policy,db,history_locators)
        guard()
        if not db.in_transaction or db.execute('PRAGMA query_only').fetchone()[0]!=1:fail()
        _g()._no_sidecars(_g()._root(db)/'state.sqlite3')
        v,h,m,p,ps=_files(db,allow_missing_marker=True);_binding(v,source,history_policy,db)
        if v['operation_id']!=operation_id or h!=checkpoint_sha:fail()
        initial=canonical((v,h,m,p,ps));version=_version(db)
        initial_coord=None
        if version==6:
            if p is not None or m is not None and m['phase']=='COMMITTED':fail()
            initial_coord=_snapshot(db,source,history_policy,v,strict=m is None or m['phase']!='ROLLED_BACK')
        elif version==8:
            if m is None or m['phase']=='ROLLED_BACK':fail()
            initial_coord=_snapshot(db,source,history_policy,v,strict=m['phase']=='PREPARED')
        elif version==9:
            if m is None or m['phase']!='COMMITTED' or p is None:fail()
        else:fail()
        from .own_store import OwnStore
        if version in (6,8) and (m is None or m['phase']=='PREPARED'):
            with _scope(db,v,h,'READ',history_policy):
                OwnStore.check(db,source,history_policy,history=history_locators);_g()._legacy_history(db,source,history_policy,history=history_locators)
        else:OwnStore.check(db,source,history_policy,history=history_locators)
        guard()
        if canonical(_files(db,allow_missing_marker=True))!=initial:fail()
        if version in (6,8):
            final_coord=_snapshot(db,source,history_policy,v,strict=m is None or m['phase']=='PREPARED')
            if canonical(final_coord)!=canonical(initial_coord):fail()
        return {'state':'NOT_COMMITTED' if version==6 else 'COMMITTED','operation_id':operation_id}
    except (WCEError,sqlite3.Error,OSError,ValueError,TypeError,KeyError):
        return {'state':'UNDETERMINED','operation_id':operation_id}




def _confirm_proof(path,expected_sha):
    # Existing valid bytes may have survived an earlier fsync failure. Confirm
    # THIS fixed inode/content plus directory before publishing its marker.
    from .bounded_file import FileSource,file_state,identity
    from .own_bootstrap_security import path_check
    source=FileSource(path.parent);fds=[];chain=[]
    try:
        directory=source._root(fds,chain)
        if identity(os.fstat(directory))!=path_check(path.parent,True):fail()
        fd=os.open(path.name,os.O_RDONLY|os.O_NOFOLLOW|os.O_NONBLOCK,dir_fd=directory);fds.append(fd)
        before=os.fstat(fd)
        if path_check(path)!=file_state(before):fail()
        raw=bytearray()
        while len(raw)<=16384:
            chunk=os.read(fd,min(4096,16385-len(raw)))
            if not chunk:break
            raw.extend(chunk)
        if len(raw)>16384 or sha256(raw).hexdigest()!=expected_sha:fail()
        if file_state(before)!=file_state(os.fstat(fd)) or file_state(before)!=file_state(os.stat(path.name,dir_fd=directory,follow_symlinks=False)):fail()
        os.fsync(fd);os.fsync(directory);source._check_chain(chain)
        if _g()._read_json(path,16384)[1]!=expected_sha:fail()
    finally:source._close(fds)


def finish(db,source,*,operation_id,checkpoint_sha,guard,history_policy, history_locators=None):
    _require_maintenance_history(history_policy,db,history_locators)
    from .own_connection_policy import atomic_write
    kw=dict(operation_id=operation_id,checkpoint_sha=checkpoint_sha,guard=guard,history_policy=history_policy,history_locators=history_locators)
    result=query(db,source,**kw)
    if result['state']=='UNDETERMINED':fail()
    v,h,m,p,ps=_files(db,allow_missing_marker=True);before=canonical((v,h,m,p,ps));root=_g()._root(db)
    if m is not None and m['phase']!='PREPARED':
        if m['phase']=='COMMITTED':_confirm_proof(root/PROOF,ps)
        _confirm_proof(root/MARKER,sha256((canonical(m)+'\n').encode()).hexdigest())
        guard()
        if query(db,source,**kw)!=result:fail()
        return result
    guard()
    if query(db,source,**kw)!=result or canonical(_files(db,allow_missing_marker=True))!=before:fail()
    if result['state']=='COMMITTED':
        if p is None:
            if m is None or m['completion_proof_sha'] is not None:fail()
            p={'schema':1,'profile':PROFILE,'origin':'NEUTRAL_GROUP_LAYOUT_COMPLETION','operation_id':operation_id,
                'binding_sha':v['binding_sha'],'source_kind':source,'checkpoint_sha':h,'contract_sha':v['contract_sha'],
                'source_sha':v['source_sha'],'base_version':6,'target_version':8,'inventory_sha':digest(v['inventory']),
                'ddl8_sha':v['ddl8_sha'],'old_restore_marker':v['old_restore_marker'],
                'coordination':_coord(db,v,history_policy,strict=True),'phase':'COMMITTED'}
            _strict_proof(p,v,h);_g()._write_new(root/PROOF,p)
            ps=sha256((canonical(p)+'\n').encode()).hexdigest()
        target={'schema':1,'operation_id':operation_id,'checkpoint_sha':h,'phase':'COMMITTED','completion_proof_sha':ps}
    else:target={'schema':1,'operation_id':operation_id,'checkpoint_sha':h,'phase':'ROLLED_BACK','completion_proof_sha':None}
    guard()
    fresh=_files(db,allow_missing_marker=True)
    if fresh[1]!=h or canonical(fresh[2])!=canonical(m):fail()
    if result['state']=='COMMITTED':
        if fresh[4]!=ps:fail()
        _confirm_proof(root/PROOF,ps)
        if query(db,source,**kw)!=result or canonical(_files(db,allow_missing_marker=True)[2])!=canonical(m):fail()
    if m is None:_g()._write_new(root/MARKER,target)
    else:atomic_write(root/MARKER,target)
    guard()
    if query(db,source,**kw)!=result:fail()
    return result



def _require_maintenance_history(policy,db,history_locators):
    """Formal maintenance borrows its real SQL owner's H; never opens one."""
    from .own_connection_policy import ConnectionPolicy
    if type(policy)is ConnectionPolicy and policy.value.get('schema')==2:
        from .draft_group_history_context import require_history
        require_history(policy,db,history_locators)
