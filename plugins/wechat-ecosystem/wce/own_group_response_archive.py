"""Group ADD schema2. Primary -> ownproof/index -> same SQL result pair.

Ordinary schema1 writers/readers remain on their original branch. This module
never sends, refreshes tokens or recursively opens OwnStore/full history.
"""
from contextlib import contextmanager
from hashlib import sha256
import json,os,sqlite3
from .contracts import WCEError
from .own_bootstrap_security import private_read,path_check
from .service import canonical,digest
from .prepared_draft_fixture import decode_json
from . import own_response_archive as ordinary
from . import draft_group_response_codec as codec
from .draft_group_response_history import validate_group_add_archive_in

POLICY='ADMITTED_RESPONSE_ARCHIVE_V2_GROUP'


def fail():raise WCEError('GROUP_ADD_ARCHIVE_HOLD')


@contextmanager
def _read_db(w,db):
    from .own_history_source import connection_source,owned_connection
    if db is not None:
        from .own_validation_scope import OwnedConnection,_transaction_marker
        if type(db) is not OwnedConnection or _transaction_marker(db) is None or connection_source(db) is None:fail()
        yield db
    else:
        from .own_connection_policy import ConnectionPolicy
        from .draft_group_read_family_store import _history_file_guard
        from .draft_group_history_context import history_policy_context
        from pathlib import Path
        policy=getattr(w.db,'history_policy',None);path=getattr(w.db,'path',None)
        if type(policy) is not ConnectionPolicy or type(path) is not type(Path('/')) or path!=policy.root/'state.sqlite3':fail()
        try:
            _history_file_guard(policy);before=path_check(path)
            with owned_connection(path,readonly=True,timeout=10,isolation_level=None) as actual:
                actual.row_factory=sqlite3.Row
                try:
                    actual.execute('PRAGMA query_only=ON');actual.execute('BEGIN')
                    if (path_check(path)!=before or actual.execute('PRAGMA database_list').fetchone()[2]!=str(path)
                            or actual.execute('PRAGMA query_only').fetchone()[0]!=1
                            or actual.execute('PRAGMA user_version').fetchone()[0]!=9):fail()
                    with history_policy_context(path,actual,policy):yield actual
                    _history_file_guard(policy)
                    if path_check(path)!=before:fail()
                finally:
                    if actual.in_transaction:actual.rollback()
        except (OSError,sqlite3.Error):fail()


def read_group_archive(w,p,row,proof,raw,pin,db=None):
    keys={'schema','policy','provenance','binding','row','request_sha256','response_sha256','result','group'}
    if (type(proof) is not dict or set(proof)!=keys or type(proof['schema']) is not int or proof['schema']!=2
            or proof['policy']!=POLICY or proof['row']!=ordinary.row_pin(row)
            or proof['binding']!=p.binding() or (canonical(proof)+'\n').encode()!=raw
            or row['operation']!='add' or row['slot']!='draft'
            or proof['provenance']!=('SYNTHETIC_OWN_WIRE' if p.source_kind=='SYNTHETIC_SETUP' else 'OWN_OFFICIAL_WIRE')
            or type(proof['result']) is not dict or set(proof['result'])!={'reference'}):fail()
    g=proof['group']
    if type(g) is not dict or set(g)!={'profile','claim_id','operation_id','group_response_sha'} or g['profile']!='GROUP_ADD_CAPTURE_LINK_V1':fail()
    for value in (proof['request_sha256'],proof['response_sha256'],g['claim_id'],g['group_response_sha']):codec._hash(value)
    path=w.db.path.parent/'group-proofs'/('group-response-'+g['claim_id']+'.json')
    primary_raw,primary_pin=private_read(path)
    if sha256(primary_raw).hexdigest()!=g['group_response_sha']:fail()
    primary=codec.decode_primary(primary_raw)
    if primary['observation']['snapshot_file_sha'] is not None:fail()
    if primary['binding']!=proof['binding']:fail()
    with _read_db(w,db) as actual:
        validate_group_add_archive_in(actual,row,proof,primary,primary_sha=g['group_response_sha'])
    return proof,raw,pin


def require_group_branch_in(db,row,proof):
    if db.execute('PRAGMA user_version').fetchone()[0]!=9:return
    linked=db.execute('SELECT claim_id FROM group_own_step_links WHERE step_id=?',(row['id'],)).fetchall()
    if linked and (len(linked)!=1 or type(proof.get('schema')) is not int or proof.get('schema')!=2):fail()
    if not linked and proof.get('schema')==2:fail()


def make_group_proof(p,row,primary_evidence):
    primary=codec.decode_primary(primary_evidence.raw)
    a=primary['admission'];t=primary['transport'];o=primary['observation']
    if (a['api']!='ADD' or o['outcome']!='KNOWN_SUCCESS' or a['own_step_pin']!=ordinary.row_pin(row)
            or primary['binding']!=p.binding()):fail()
    proof={'schema':2,'policy':POLICY,
        'provenance':'SYNTHETIC_OWN_WIRE' if p.source_kind=='SYNTHETIC_SETUP' else 'OWN_OFFICIAL_WIRE',
        'binding':p.binding(),'row':ordinary.row_pin(row),'request_sha256':a['request_sha'],
        'response_sha256':t['response_body_sha'],'result':{'reference':o['reference']},
        'group':{'profile':'GROUP_ADD_CAPTURE_LINK_V1','claim_id':a['claim_id'],
                 'operation_id':a['operation_id'],'group_response_sha':primary_evidence.sha256}}
    raw=(canonical(proof)+'\n').encode()
    if len(raw)>8192:fail()
    return proof,raw


def publish_group_ownproof(w,p,row,primary_evidence,files):
    proof,raw=make_group_proof(p,row,primary_evidence)
    parent=w.db.path.parent;root_pin=path_check(parent,True)
    path=parent/ordinary.filename(row)
    index_name='response-index-'+row['id']+'-'+row['owner']+'.json'
    index_raw=(canonical({'schema':1,'row_sha256':digest(ordinary.row_pin(row)),
        'proof_sha256':sha256(raw).hexdigest()})+'\n').encode()
    pins={}
    directory=os.open(parent,os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW)
    try:
        if (os.fstat(directory).st_dev,os.fstat(directory).st_ino)!=root_pin:fail()
        for name,body in ((path.name,raw),(index_name,index_raw)):
            files.collective_fence()
            try:fd=os.open(name,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW|os.O_NONBLOCK,0o600,dir_fd=directory)
            except FileExistsError:
                actual,pin=private_read(parent/name)
                if actual!=body:fail()
                fd=os.open(name,os.O_RDONLY|os.O_NOFOLLOW|os.O_NONBLOCK,dir_fd=directory)
            else:
                try:
                    os.fchmod(fd,0o600)
                    count=0
                    while count<len(body):
                        n=os.write(fd,body[count:])
                        if type(n) is not int or n<=0:fail()
                        count+=n
                except BaseException:os.close(fd);raise
            try:
                before=path_check(parent/name)
                if before[:2]!=(os.fstat(fd).st_dev,os.fstat(fd).st_ino):fail()
                os.fsync(fd);files.collective_fence()
                if path_check(parent/name)!=before:fail()
                os.fsync(directory);files.collective_fence()
                actual,pin=private_read(parent/name)
                if actual!=body or pin!=before:fail()
                pins[name]=pin
                files._remember_own_archive_file(row,name,pin)
            finally:os.close(fd)
        files.collective_fence()
        if path_check(parent,True)!=root_pin:fail()
        for name,pin in pins.items():
            if path_check(parent/name)!=pin:fail()
    finally:os.close(directory)
    return proof,raw,pins


def reconcile_group_add_in(db,w,p,row,primary_evidence,proof,raw,*,files, history_locators=None):
    """Caller owns actual result SQL. Own success and ADD_RESULT are atomic."""
    if not db.in_transaction:fail()
    primary=codec.decode_primary(primary_evidence.raw)
    validate_group_add_archive_in(db,row,proof,primary,primary_sha=primary_evidence.sha256)
    result=ordinary.completed(proof,raw,row)
    current=db.execute('SELECT * FROM own_steps WHERE id=?',(row['id'],)).fetchone()
    if current is None or ordinary.row_pin(current)!=ordinary.row_pin(row):fail()
    files.collective_fence()
    if current['state']=='SUCCEEDED':
        if json.loads(current['result'])!=result:fail()
        from .draft_group_store import verify_existing_own_step_result
        verify_existing_own_step_result(db,current,archive_proof_sha=sha256(raw).hexdigest(),result=result, history_locators=history_locators)
        return result
    if current['state']!='RESULT_UNKNOWN' or current['result']!='{}':fail()
    # Validate original immutable own intent/grants/history without asking for
    # current source freshness. The original eligible leaf already uses past
    # approval semantics and same row, not fresh send authority.
    from .draft_group_target_scope import _history_workflow
    history_workflow,_=_history_workflow(w.db.history_policy,w.db.path,p.binding(),db=db,history_locators=history_locators)
    intent,manifest=ordinary.eligible(history_workflow,db,p,current, history_locators=history_locators)
    w._owned_lock(db,p,manifest,row['id'])
    stamp=max(primary['observation']['observed_at_ms']/1000,row['created'])
    changed=db.execute("UPDATE own_steps SET state='SUCCEEDED',result=?,result_digest=?,completed=? WHERE id=? AND owner=? AND state='RESULT_UNKNOWN' AND intent_digest=? AND approval_digest=?",
        (canonical(result),digest(result),stamp,row['id'],row['owner'],row['intent_digest'],row['approval_digest'])).rowcount
    if changed!=1:fail()
    updated=db.execute('SELECT * FROM own_steps WHERE id=?',(row['id'],)).fetchone()
    from .draft_group_store import observe_own_step_result
    observe_own_step_result(db,updated,archive_proof_sha=sha256(raw).hexdigest(),result=result, history_locators=history_locators)
    w._release_lock(db,p,manifest,row['id'])
    files.collective_fence()
    return result


def reconcile_group_archive(w,p,row,proof,raw):
    from .draft_group_runtime_host import response_history_context_in
    from .draft_group_response_files import GroupResponseFiles
    from .draft_group_response_history import load_original_locator_in
    from .draft_group_store import _load
    with _history_transaction(w.db, write=True) as (db, history_locators):
        context=response_history_context_in(db,w.db.history_policy)
        files=GroupResponseFiles.from_history_context(w.db.history_policy,context)
        account=digest(p.binding());state,_,_=_load(db,account)
        locator=load_original_locator_in(files,db,state,proof['group']['claim_id'])
        primary=files.read_primary(locator)
        ordinary._durable(w,row)
        if ordinary._read(w,p,row,db=db)[1]!=raw:fail()
        return reconcile_group_add_in(db,w,p,row,primary,proof,raw,files=files, history_locators=history_locators)


from .draft_group_history_context import history_transaction as _history_transaction
