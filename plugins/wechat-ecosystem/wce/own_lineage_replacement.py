"""Formal schema6 nonlegacy body replacement history; no live send grant.

Central seal/spent/proof verification belongs to own_replacement_batch. This
module fails closed when that verifier is absent; it does not mint proof PASS.
"""
from contextlib import closing
from dataclasses import dataclass
from hashlib import sha256
import json
from pathlib import Path
import re
import sqlite3
from types import SimpleNamespace

from .contracts import Actor, WCEError
from .service import canonical, digest

VERSION = 6
POLICY = 'EXPLICIT_LINEAGE_BODY_REPLACEMENT_V1'
ORIGIN = 'EXPLICIT_LINEAGE_BODY_REPLACEMENT_RESPONSE_V1'
EMPTY = digest({})
SCHEMA = """
CREATE TABLE own_replacement_batches(
 id TEXT PRIMARY KEY, manifest TEXT NOT NULL, manifest_digest TEXT NOT NULL,
 created REAL NOT NULL, state TEXT NOT NULL CHECK(state='INACTIVE'));
CREATE TABLE own_lineage_replacement_approvals(
 id TEXT PRIMARY KEY, batch_id TEXT NOT NULL REFERENCES own_replacement_batches(id),
 case_id TEXT NOT NULL UNIQUE, original_step_id TEXT NOT NULL UNIQUE REFERENCES own_steps(id),
 tenant TEXT NOT NULL, principal TEXT NOT NULL, connection TEXT NOT NULL, resource TEXT NOT NULL,
 body TEXT NOT NULL, body_digest TEXT NOT NULL, created REAL NOT NULL, expires REAL NOT NULL,
 state TEXT NOT NULL CHECK(state='INACTIVE'),
 FOREIGN KEY(tenant,resource) REFERENCES own_resources(tenant,resource));
CREATE TABLE own_lineage_replacements(
 id TEXT PRIMARY KEY, original_step_id TEXT NOT NULL UNIQUE REFERENCES own_steps(id),
 case_id TEXT NOT NULL UNIQUE, approval_id TEXT NOT NULL UNIQUE REFERENCES own_lineage_replacement_approvals(id),
 tenant TEXT NOT NULL, resource TEXT NOT NULL, owner TEXT NOT NULL,
 intent TEXT NOT NULL, intent_digest TEXT NOT NULL,
 state TEXT NOT NULL CHECK(state IN ('RESULT_UNKNOWN','SUCCEEDED')),
 result TEXT NOT NULL DEFAULT '{}', result_digest TEXT NOT NULL DEFAULT '44136fa355b3678a1146ad16f7e8649e94fb4fc21fe77e8310c060f61caaff8a',
 proof_name TEXT, proof_sha TEXT, created REAL NOT NULL, completed REAL,
 FOREIGN KEY(tenant,resource) REFERENCES own_resources(tenant,resource),
 CHECK((state='RESULT_UNKNOWN' AND result='{}' AND result_digest='44136fa355b3678a1146ad16f7e8649e94fb4fc21fe77e8310c060f61caaff8a'
        AND proof_name IS NULL AND proof_sha IS NULL AND completed IS NULL) OR
       (state='SUCCEEDED' AND result!='{}' AND proof_name IS NOT NULL AND proof_sha IS NOT NULL AND completed IS NOT NULL)));
CREATE TRIGGER replacement_batches_immutable_update BEFORE UPDATE ON own_replacement_batches
 BEGIN SELECT RAISE(ABORT,'OWN_REPLACEMENT_HISTORY_IMMUTABLE'); END;
CREATE TRIGGER replacement_batches_immutable_delete BEFORE DELETE ON own_replacement_batches
 BEGIN SELECT RAISE(ABORT,'OWN_REPLACEMENT_HISTORY_IMMUTABLE'); END;
CREATE TRIGGER replacement_approvals_immutable_update BEFORE UPDATE ON own_lineage_replacement_approvals
 BEGIN SELECT RAISE(ABORT,'OWN_REPLACEMENT_HISTORY_IMMUTABLE'); END;
CREATE TRIGGER replacement_approvals_immutable_delete BEFORE DELETE ON own_lineage_replacement_approvals
 BEGIN SELECT RAISE(ABORT,'OWN_REPLACEMENT_HISTORY_IMMUTABLE'); END;
CREATE TRIGGER replacements_no_delete BEFORE DELETE ON own_lineage_replacements
 BEGIN SELECT RAISE(ABORT,'OWN_REPLACEMENT_SPENT_IMMUTABLE'); END;
CREATE TRIGGER replacements_admission_immutable BEFORE UPDATE ON own_lineage_replacements WHEN
 NEW.id<>OLD.id OR NEW.original_step_id<>OLD.original_step_id OR NEW.case_id<>OLD.case_id OR
 NEW.approval_id<>OLD.approval_id OR NEW.tenant<>OLD.tenant OR NEW.resource<>OLD.resource OR
 NEW.owner<>OLD.owner OR NEW.intent<>OLD.intent OR NEW.intent_digest<>OLD.intent_digest OR NEW.created<>OLD.created
 BEGIN SELECT RAISE(ABORT,'OWN_REPLACEMENT_SPENT_IMMUTABLE'); END;
CREATE TRIGGER replacements_success_immutable BEFORE UPDATE ON own_lineage_replacements WHEN OLD.state='SUCCEEDED'
 BEGIN SELECT RAISE(ABORT,'OWN_REPLACEMENT_SUCCESS_IMMUTABLE'); END;
"""


@dataclass(frozen=True)
class ReplacementEvidence:
    case_id: str
    row_pin_sha: str
    result_sha: str
    proof_sha: str | None
    original_step_sha: str
    batch_sha: str
    origin: str


def fail():
    raise WCEError('OWN_LINEAGE_REPLACEMENT_HOLD')


def stored(raw,checksum):
    from .own_replacement_files import stored as read
    return read(raw,checksum)


def row_pin(row):
    return digest({k:row[k] for k in ('id','original_step_id','case_id','approval_id',
        'tenant','resource','owner','intent','intent_digest','created')})


def _finite(value):
    from .own_auth import finite
    return finite(value)


def proof_name_valid(value):
    return type(value) is str and re.fullmatch(r'[A-Za-z0-9_.-]{1,128}\.json',value) is not None


def stable_case(original,intent):
    return digest({'provider':'WECHAT_OFFICIAL_ACCOUNT','resource':original['resource'],
        'original_step_id':original['id'],'target':original['target'],
        'intent_digest':original['intent_digest'],'slot':original['slot'],
        'asset_sha256':intent['asset']['sha256']})


def original_context(db,original):
    from .own_lineage import seal
    from .own_group_json import read
    from .own_workflow import stored as original_stored
    intent=original_stored(original['intent'],original['intent_digest'])
    if (original['operation']!='body' or original['state']!='RESULT_UNKNOWN'
            or original['result']!='{}' or original['completed'] is not None): fail()
    mrow=db.execute('SELECT * FROM own_articles WHERE version=?',(intent['selector']['version'],)).fetchone()
    if mrow is None: fail()
    manifest=read(mrow['manifest'],mrow['digest']);lineage=seal(db,manifest)
    if lineage['legacy']!=0: fail()
    for table in ('own_body_recoveries','own_body_followups','own_body_attempts'):
        if db.execute('SELECT 1 FROM '+table+' WHERE original_step_id=?',(original['id'],)).fetchone():
            fail()  # A new nonlegacy branch cannot hide old legacy admissions.
    return {'original_step_id':original['id'],'original_request_key':original['request_key'],
        'original_row_sha':digest(dict(original)),'original_target':original['target'],
        'original_owner':original['owner'],'original_intent_digest':original['intent_digest'],
        'original_approval_id':original['approval_id'],'original_approval_digest':original['approval_digest'],
        'binding':intent['binding'],'selector':intent['selector'],'lineage':lineage,
        'slot':intent['slot'],'asset':intent['asset']}


def _history_objects(db,original,history_policy=None):
    from .own_workflow import OwnWorkflow
    from .own_workflow import stored as original_stored
    intent=original_stored(original['intent'],original['intent_digest']);b=intent['binding']
    history=object.__new__(OwnWorkflow)
    history.db=SimpleNamespace(path=Path(db.execute('PRAGMA database_list').fetchone()[2]),history_policy=history_policy)
    if history_policy is not None: history.policy=history_policy
    profile=SimpleNamespace(actor=Actor(b['tenant'],b['principal'],b['client'],b['session']),
        connection_id=b['connection'],account_id=b['account'],resource_id=b['resource'],
        source_kind=b['source_kind'],binding=lambda:dict(b))
    return history,profile


def validate_approval(db,row,source_kind,history_policy=None,*,history=None):
    original=db.execute('SELECT * FROM own_steps WHERE id=?',(row['original_step_id'],)).fetchone()
    batch=db.execute('SELECT * FROM own_replacement_batches WHERE id=?',(row['batch_id'],)).fetchone()
    if original is None or batch is None: fail()
    body=stored(row['body'],row['body_digest']);manifest=stored(batch['manifest'],batch['manifest_digest'])
    context=original_context(db,original)
    if (type(body) is not dict or type(manifest) is not dict or type(manifest.get('registry')) is not str
            or type(manifest.get('schema')) is not int or manifest['schema']!=2): fail()
    from .own_replacement_contract import validate_cases
    validate_cases(manifest)
    from .own_replacement_batch import registry_from_db
    from .own_body5_family import check_id_contract
    registry=registry_from_db(db,history_policy,history=history)
    if registry is None or manifest['registry']!=str(registry): fail()
    check_id_contract(batch['id'],manifest['contract_sha'])
    members=[case for case in manifest['cases'] if case.get('case_id')==row['case_id']]
    if (body.get('contract_sha')!=manifest.get('contract_sha') or len(members)!=1
            or members[0].get('approval_id')!=row['id']
            or members[0].get('original')!=context):
        fail()
    from .own_replacement_context import immutable
    immutable(Path(manifest['registry']),manifest,history=history)
    body_keys={'schema','policy','batch_id','case_id','original','candidate_scope','contract_sha',
        'maximum_new_sends','created','expires','human_review_sha','unrelated_context_sha','unrelated_receipt_sha'}
    if (type(body) is not dict or set(body)!=body_keys or type(body.get('schema')) is not int or body.get('schema')!=2 or body.get('policy')!=POLICY
            or body.get('batch_id')!=batch['id'] or body.get('case_id')!=row['case_id']
            or row['case_id']!=stable_case(original,stored(original['intent'],original['intent_digest']))
            or body.get('original')!=context or body.get('maximum_new_sends')!=1
            or type(body.get('maximum_new_sends')) is not int
            or any(k in body for k in ('active','revoked','current_state','current_expires'))
            or body.get('created')!=row['created'] or body.get('expires')!=row['expires']
            or not _finite(row['created']) or not _finite(row['expires']) or row['expires']<=row['created']
            or body['original']['binding']['source_kind']!=source_kind
            or any(row[k]!=original[k] for k in ('tenant','principal','connection','resource'))
            or row['state']!='INACTIVE' or batch['state']!='INACTIVE'
            or type(manifest) is not dict or manifest.get('batch_id')!=batch['id']
            or not _finite(batch['created'])
            or any(type(body.get(k)) is not str or re.fullmatch('[a-f0-9]{64}',body[k]) is None
                   for k in ('candidate_scope','contract_sha'))
            or body.get('unrelated_context_sha')!=manifest['unrelated_context_sha']
            or body.get('unrelated_receipt_sha')!=manifest['unrelated_context']['receipt_sha']): fail()
    return original,body,batch


def _same_history(history,history_locators):
    """The old physical and new consumer channels carry one entered H."""
    if history is not None and history_locators is not None and history is not history_locators:
        fail()
    return history if history is not None else history_locators


def validate_record(db,row,source_kind,*,w=None,p=None,history_policy=None,history=None, history_locators=None):
    history=history_locators=_same_history(history,history_locators)
    from .own_step_history import validate_original_upload_in
    approval=db.execute('SELECT * FROM own_lineage_replacement_approvals WHERE id=?',(row['approval_id'],)).fetchone()
    if approval is None: fail()
    original,body,batch=validate_approval(db,approval,source_kind,history_policy,history=history)
    if w is None or p is None: w,p=_history_objects(db,original,history_policy)
    # This is a body UNKNOWN, so _step cannot recurse into _uploads/add.
    validate_original_upload_in(w,db,p,original, history_locators=history_locators)
    intent=stored(row['intent'],row['intent_digest']);result=stored(row['result'],row['result_digest'])
    context=body['original']
    expected={'schema':2,'policy':POLICY,'case_id':approval['case_id'],
        'original_step_id':original['id'],'original_row_sha':context['original_row_sha'],
        'approval_id':approval['id'],'approval_digest':approval['body_digest'],
        'batch_id':batch['id'],'binding':context['binding'],'selector':context['selector'],
        'lineage':context['lineage'],'slot':context['slot'],'asset':context['asset'],
        'candidate_scope':body['candidate_scope'],'contract_sha':body['contract_sha'],
        'unrelated_context_sha':body['unrelated_context_sha'],
        'unrelated_receipt_sha':body['unrelated_receipt_sha']}
    if (type(intent) is not dict or type(intent.get('schema')) is not int
            or set(intent)!=set(expected)|{'response_policy','request_sha'}
            or any(intent.get(k)!=v for k,v in expected.items())
            or row['original_step_id']!=original['id'] or row['case_id']!=approval['case_id']
            or any(row[k]!=original[k] for k in ('tenant','resource'))
            or not _finite(row['created']) or row['created']<approval['created']
            or type(row['owner']) is not str or not row['owner']): fail()
    if row['state']=='RESULT_UNKNOWN':
        if result or row['completed'] is not None or row['proof_name'] is not None or row['proof_sha'] is not None: fail()
    elif row['state']=='SUCCEEDED':
        from .upload_wire import api_reference_reason
        if (type(result) is not dict or set(result)!={'url'} or api_reference_reason(result['url']) is not None
                or not _finite(row['completed']) or row['completed']<row['created']
                or not proof_name_valid(row['proof_name'])
                or type(row['proof_sha']) is not str or re.fullmatch('[a-f0-9]{64}',row['proof_sha']) is None): fail()
    else: fail()
    try:
        from .own_replacement_batch import validate_history
    except ImportError:
        fail()
    evidence=validate_history(w,db,p,original,row,approval,batch,history=history)
    expected_evidence=ReplacementEvidence(row['case_id'],row_pin(row),row['result_digest'],
        row['proof_sha'],digest(dict(original)),batch['manifest_digest'],ORIGIN)
    if type(evidence) is not ReplacementEvidence or evidence!=expected_evidence: fail()
    return original,intent,result,evidence


def check_account_claims(db,source_kind,history_policy=None,*,history=None):
    """All formal lineage versions, including a restored old schema5 DB.

    The root batch implementation uses the trusted non-grant registry marker
    or history_policy; this layer never invents a HOME-based location.
    """
    try:
        from .own_replacement_batch import check_account_claims as check
    except ImportError:
        fail()
    check(db,source_kind,history_policy,history=history)


def validate_all(db,source_kind,history_policy=None,*,history=None, history_locators=None):
    # Mandatory even if a restored schema6 DB has zero new rows.
    history=history_locators=_same_history(history,history_locators)
    check_account_claims(db,source_kind,history_policy,history=history)
    batches=list(db.execute('SELECT * FROM own_replacement_batches'))
    for row in batches:
        value=stored(row['manifest'],row['manifest_digest'])
        if (type(value) is not dict or type(value.get('schema')) is not int or value.get('schema')!=2
                or value.get('batch_id')!=row['id'] or row['state']!='INACTIVE' or not _finite(row['created'])): fail()
        from .own_replacement_batch import registry_from_db
        from .own_body5_family import check_id_contract
        registry=registry_from_db(db,history_policy,history=history)
        if registry is None or value.get('registry')!=str(registry): fail()
        check_id_contract(row['id'],value.get('contract_sha'))
        from .own_replacement_context import immutable
        immutable(registry,value,history=history)
    for row in db.execute('SELECT * FROM own_lineage_replacement_approvals'):
        validate_approval(db,row,source_kind,history_policy,history=history)
    successes={}
    for row in db.execute('SELECT * FROM own_lineage_replacements'):
        original,_,_,_=validate_record(db,row,source_kind,history_policy=history_policy,history=history, history_locators=history_locators)
        if row['state']=='SUCCEEDED': successes[original['id']]=row['id']
    return successes


def mapping(w,db,p,original, *, history_locators=None):
    if db.execute('PRAGMA user_version').fetchone()[0] not in (VERSION, 7, 8, 9): return None
    row=db.execute('SELECT * FROM own_lineage_replacements WHERE original_step_id=?',(original['id'],)).fetchone()
    if row is None: return None
    original,intent,result,evidence=validate_record(db,row,p.source_kind,w=w,p=p, history_locators=history_locators)
    if row['state']!='SUCCEEDED': return None
    approval=db.execute('SELECT * FROM own_lineage_replacement_approvals WHERE id=?',(row['approval_id'],)).fetchone()
    body=stored(approval['body'],approval['body_digest'])
    return result,{'source':ORIGIN,'replacement_id':row['id'],'case_id':row['case_id'],
        'original_step_id':original['id'],'original_step_sha':digest(dict(original)),
        'original_intent_digest':original['intent_digest'],'original_result_digest':original['result_digest'],
        'intent_digest':row['intent_digest'],'result_digest':row['result_digest'],
        'proof_sha256':row['proof_sha'],'approval_digest':approval['body_digest'],
        'batch_id':approval['batch_id'],'batch_digest':evidence.batch_sha,
        'unrelated_context_sha':body['unrelated_context_sha'],
        'unrelated_receipt_sha':body['unrelated_receipt_sha']}


def view(w,db,p,original, *, history_locators=None):
    row=db.execute('SELECT * FROM own_lineage_replacements WHERE original_step_id=?',(original['id'],)).fetchone()
    if row is None: return None
    _,_,result,evidence=validate_record(db,row,p.source_kind,w=w,p=p, history_locators=history_locators)
    return {'replacement_id':row['id'],'case_id':row['case_id'],'original_step_id':original['id'],
        'state':row['state'],'completion_origin':ORIGIN if result else 'UNDETERMINED',
        'result_available':bool(result),'proof_sha256':evidence.proof_sha}


def release_success_lock(w,db,p,row, *, history_locators=None):
    """Caller owns the result transaction; one exact original lock CAS only."""
    original,intent,result,evidence=validate_record(db,row,p.source_kind,w=w,p=p, history_locators=history_locators)
    if row['state']!='SUCCEEDED': fail()
    lineage=intent['lineage']['lineage']
    cursor=db.execute('DELETE FROM own_lineage_locks WHERE tenant=? AND resource=? AND lineage=? AND owner_id=?',
        (original['tenant'],original['resource'],lineage,original['id']))
    if cursor.rowcount!=1: fail()
    return evidence


def execute_schema(db):
    statement=''
    for line in SCHEMA.splitlines(keepends=True):
        statement+=line
        if sqlite3.complete_statement(statement):
            db.execute(statement.lstrip());statement=''
    if statement.strip(): fail()


def schema_check(db,source_kind):
    from .own_store import SCHEMA as OLD_SCHEMA,APP_ID
    from .own_lineage import SCHEMA as LINEAGE_SCHEMA
    version=db.execute('PRAGMA user_version').fetchone()[0]
    if version == 9:
        from .own_group_schema import check_layout
        return check_layout(db, source_kind)
    if (version not in (6, 7, 8)
            or db.execute('PRAGMA application_id').fetchone()[0]!=APP_ID): fail()
    def fingerprint(connection):
        from .storage import _normalized_sql
        master=[(r[0],r[1],r[2],_normalized_sql(r[3]) if r[3] is not None else None)
                for r in connection.execute('SELECT type,name,tbl_name,sql FROM sqlite_master ORDER BY type,name')]
        details={}
        for row in connection.execute("SELECT name FROM sqlite_master WHERE type='table'"):
            quoted='"'+row[0].replace('"','""')+'"'
            details[row[0]]={key:[tuple(x) for x in connection.execute('PRAGMA '+key+'('+quoted+')')]
                for key in ('table_info','foreign_key_list','index_list')}
        return master,details
    with closing(sqlite3.connect(':memory:')) as expected:
        expected.executescript(OLD_SCHEMA+LINEAGE_SCHEMA+SCHEMA)
        if version in (7, 8):
            from .publication_store import ALL_SCHEMA as PUBLICATION_SCHEMA
            expected.executescript(PUBLICATION_SCHEMA)
        if version == 8:
            from .own_draft_restore_store import SCHEMA as RESTORE_SCHEMA
            expected.executescript(RESTORE_SCHEMA)
        if fingerprint(db)!=fingerprint(expected): fail()
    config=db.execute('SELECT * FROM own_config').fetchall()
    if len(config)!=1 or config[0]['id']!=1 or config[0]['source_kind']!=source_kind or db.execute('PRAGMA foreign_key_check').fetchone(): fail()


def migrate(db,source_kind,guard,fault=lambda phase:None,history_policy=None, *, history_locators=None):
    """Caller owns BEGIN IMMEDIATE and maintenance locks; never auto-enable."""
    from .own_store import OwnStore
    from .own_connection_policy import ConnectionPolicy
    if type(history_policy) is ConnectionPolicy and history_policy.value.get('schema')==2:
        from .draft_group_history_context import require_history
        require_history(history_policy,db,history_locators)
    guard()
    if not db.in_transaction: fail()
    if db.execute('PRAGMA user_version').fetchone()[0] == 9:
        OwnStore.check(db,source_kind,history_policy, history=history_locators)
        return
    if db.execute('PRAGMA user_version').fetchone()[0] in (6, 7, 8):
        schema_check(db,source_kind);validate_all(db,source_kind,history_policy, history_locators=history_locators)
        return
    if db.execute('PRAGMA user_version').fetchone()[0]!=5: fail()
    OwnStore._check_records(db,source_kind,5,history_policy,history=history_locators)
    owner=object.__new__(OwnStore)
    owner.path=Path(db.execute('PRAGMA database_list').fetchone()[2])
    owner.history_policy=history_policy
    owner._check_legacy_history(db,source_kind, history=history_locators)
    execute_schema(db);db.execute('PRAGMA user_version=6')
    schema_check(db,source_kind);validate_all(db,source_kind,history_policy, history_locators=history_locators)
    owner._check_legacy_history(db,source_kind, history=history_locators)
    guard();fault('replacement_schema_before_commit')
