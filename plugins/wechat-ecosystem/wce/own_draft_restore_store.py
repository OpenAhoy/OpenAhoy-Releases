"""Additive schema8 restoration journal. Caller owns locks and transactions.

This module neither grants authority, obtains credentials nor sends requests.
The parent successful step is immutable history; a new restoration is separate.
"""
from .own_draft_restore_contract import fail, stored, EMPTY, CONTRACT_SHA, V1_CONTRACT_SHA, SUPPORTED_CONTRACTS, POLICY, V1_POLICY, parent_pin, clear_event_id, check_clear_order
from .service import digest

SCHEMA = """
CREATE TABLE own_draft_clear_events(
 id TEXT PRIMARY KEY, tenant TEXT NOT NULL, principal TEXT NOT NULL,
 connection TEXT NOT NULL, resource TEXT NOT NULL, body TEXT NOT NULL,
 body_digest TEXT NOT NULL, created REAL NOT NULL,
 FOREIGN KEY(tenant,resource) REFERENCES own_resources(tenant,resource));
CREATE TABLE own_draft_restore_grants(
 id TEXT PRIMARY KEY, event_id TEXT NOT NULL REFERENCES own_draft_clear_events(id),
 parent_step_id TEXT NOT NULL REFERENCES own_steps(id), version TEXT NOT NULL REFERENCES own_articles(version),
 tenant TEXT NOT NULL, principal TEXT NOT NULL, connection TEXT NOT NULL, resource TEXT NOT NULL,
 body TEXT NOT NULL, body_digest TEXT NOT NULL, created REAL NOT NULL, expires REAL NOT NULL,
 UNIQUE(event_id,parent_step_id,version,resource),
 FOREIGN KEY(tenant,resource) REFERENCES own_resources(tenant,resource));
CREATE TABLE own_draft_restores(
 id TEXT PRIMARY KEY, grant_id TEXT NOT NULL UNIQUE REFERENCES own_draft_restore_grants(id),
 parent_step_id TEXT NOT NULL REFERENCES own_steps(id), request_key TEXT NOT NULL,
 tenant TEXT NOT NULL, principal TEXT NOT NULL, connection TEXT NOT NULL, resource TEXT NOT NULL,
 lineage TEXT NOT NULL, owner TEXT NOT NULL, intent TEXT NOT NULL, intent_digest TEXT NOT NULL,
 state TEXT NOT NULL CHECK(state IN ('RESULT_UNKNOWN','SUCCEEDED')),
 result TEXT NOT NULL DEFAULT '{}', result_digest TEXT NOT NULL DEFAULT '44136fa355b3678a1146ad16f7e8649e94fb4fc21fe77e8310c060f61caaff8a',
 proof_name TEXT, proof_sha TEXT, created REAL NOT NULL, completed REAL,
 readback TEXT NOT NULL DEFAULT 'UNVERIFIED' CHECK(readback IN ('UNVERIFIED','MATCHED')),
 UNIQUE(tenant,principal,connection,request_key),
 FOREIGN KEY(tenant,resource) REFERENCES own_resources(tenant,resource),
 CHECK((state='RESULT_UNKNOWN' AND result='{}' AND completed IS NULL AND proof_name IS NULL AND proof_sha IS NULL AND readback='UNVERIFIED') OR
       (state='SUCCEEDED' AND result!='{}' AND completed IS NOT NULL AND proof_name IS NOT NULL AND proof_sha IS NOT NULL)));
CREATE TABLE own_draft_restore_locks(
 tenant TEXT NOT NULL, resource TEXT NOT NULL, lineage TEXT NOT NULL,
 restore_id TEXT NOT NULL UNIQUE REFERENCES own_draft_restores(id),
 PRIMARY KEY(tenant,resource,lineage));
CREATE TABLE own_draft_restore_reads(
 restore_id TEXT NOT NULL REFERENCES own_draft_restores(id), ordinal INTEGER NOT NULL CHECK(ordinal BETWEEN 1 AND 5),
 state TEXT NOT NULL CHECK(state IN ('CLAIMED','DONE','UNKNOWN')), created REAL NOT NULL,
 response_sha TEXT, comparison TEXT NOT NULL DEFAULT 'UNVERIFIED' CHECK(comparison IN ('UNVERIFIED','MATCHED')),
 PRIMARY KEY(restore_id,ordinal));
CREATE TRIGGER draft_restore_reads_no_delete BEFORE DELETE ON own_draft_restore_reads
 BEGIN SELECT RAISE(ABORT,'DRAFT_RESTORE_READ_SPENT_IMMUTABLE'); END;
CREATE TRIGGER draft_restore_reads_pins BEFORE UPDATE ON own_draft_restore_reads WHEN
 NEW.restore_id<>OLD.restore_id OR NEW.ordinal<>OLD.ordinal OR NEW.created<>OLD.created OR OLD.state='DONE'
 BEGIN SELECT RAISE(ABORT,'DRAFT_RESTORE_READ_SPENT_IMMUTABLE'); END;
CREATE TRIGGER draft_clear_no_update BEFORE UPDATE ON own_draft_clear_events
 BEGIN SELECT RAISE(ABORT,'DRAFT_RESTORE_SOURCE_IMMUTABLE'); END;
CREATE TRIGGER draft_clear_no_delete BEFORE DELETE ON own_draft_clear_events
 BEGIN SELECT RAISE(ABORT,'DRAFT_RESTORE_SOURCE_IMMUTABLE'); END;
CREATE TRIGGER draft_restore_grant_no_update BEFORE UPDATE ON own_draft_restore_grants
 BEGIN SELECT RAISE(ABORT,'DRAFT_RESTORE_SOURCE_IMMUTABLE'); END;
CREATE TRIGGER draft_restore_grant_no_delete BEFORE DELETE ON own_draft_restore_grants
 BEGIN SELECT RAISE(ABORT,'DRAFT_RESTORE_SOURCE_IMMUTABLE'); END;
CREATE TRIGGER draft_restore_no_delete BEFORE DELETE ON own_draft_restores
 BEGIN SELECT RAISE(ABORT,'DRAFT_RESTORE_SPENT_IMMUTABLE'); END;
CREATE TRIGGER draft_restore_pins BEFORE UPDATE ON own_draft_restores WHEN
 NEW.id<>OLD.id OR NEW.grant_id<>OLD.grant_id OR NEW.parent_step_id<>OLD.parent_step_id OR
 NEW.request_key<>OLD.request_key OR NEW.tenant<>OLD.tenant OR NEW.principal<>OLD.principal OR
 NEW.connection<>OLD.connection OR NEW.resource<>OLD.resource OR NEW.lineage<>OLD.lineage OR
 NEW.owner<>OLD.owner OR NEW.intent<>OLD.intent OR NEW.intent_digest<>OLD.intent_digest OR NEW.created<>OLD.created
 BEGIN SELECT RAISE(ABORT,'DRAFT_RESTORE_SPENT_IMMUTABLE'); END;
CREATE TRIGGER draft_restore_success BEFORE UPDATE ON own_draft_restores WHEN OLD.state='SUCCEEDED' AND
 (NEW.state<>OLD.state OR NEW.result<>OLD.result OR NEW.result_digest<>OLD.result_digest OR
  NEW.proof_name<>OLD.proof_name OR NEW.proof_sha<>OLD.proof_sha OR NEW.completed<>OLD.completed)
 BEGIN SELECT RAISE(ABORT,'DRAFT_RESTORE_SUCCESS_IMMUTABLE'); END;
"""


def version(db):
    return db.execute('PRAGMA user_version').fetchone()[0]


from contextvars import ContextVar
_CURRENT_RESTORE = ContextVar('trusted_restore_execution',default=None)


def check_write(db, tenant, resource, lineage=None, own_restore_id=None):
    own_restore_id = own_restore_id or _CURRENT_RESTORE.get()
    if version(db) not in (8,9):
        return
    for row in db.execute('SELECT lineage,restore_id FROM own_draft_restore_locks WHERE tenant=? AND resource=?', (tenant,resource)):
        # An empty lineage denotes an original legacy resource-level lock.
        if row['restore_id'] != own_restore_id and (not row['lineage'] or lineage is None or lineage == row['lineage']):
            fail('DRAFT_RESTORE_RESULT_UNKNOWN')


def validate(db, source_kind, policy=None):
    """Structural references plus exact stored pins; detailed proof is mandatory.

    The service verifier is used for all nonempty history, including on reads.
    No successful row may be consumed without its independent host proof index.
    """
    events = {}
    for row in db.execute('SELECT * FROM own_draft_clear_events'):
        body = stored(row['body'],row['body_digest'])
        if (type(body.get('schema')) is not int or body['schema'] != 1 or body.get('contract_sha') not in SUPPORTED_CONTRACTS
                or body.get('event_id') != row['id'] or body.get('source_kind') != 'TRUSTED_HUMAN_REVIEW'
                or body.get('binding',{}).get('account') != row['resource']
                or body.get('binding',{}).get('tenant') != row['tenant']
                or body.get('binding',{}).get('principal') != row['principal']
                or body.get('binding',{}).get('connection') != row['connection']):
            fail()
        if body['event_id']!=clear_event_id(body.get('source_reference_sha'),body.get('clear_window')):fail('DRAFT_RESTORE_SOURCE_INVALID')
        events[row['id']] = body
    grants = {}
    for row in db.execute('SELECT * FROM own_draft_restore_grants'):
        body = stored(row['body'],row['body_digest'])
        parent = db.execute('SELECT * FROM own_steps WHERE id=?',(row['parent_step_id'],)).fetchone()
        if (row['event_id'] not in events or parent is None or parent['operation'] != 'add'
                or parent['state'] != 'SUCCEEDED' or body.get('contract_sha') not in SUPPORTED_CONTRACTS
                or body.get('grant_id') != row['id'] or body.get('event_id') != row['event_id']
                or body.get('parent_step_sha') != parent_pin(parent)
                or body.get('version') != row['version'] or row['expires'] <= row['created']
                or body.get('event_sha') != digest(events.get(row['event_id']))
                or body.get('binding') != body.get('context',{}).get('binding')
                or any(parent[key] != row[key] for key in ('tenant','principal','connection','resource'))):
            fail()
        if (type(body.get('schema')) is not int or body['schema']!=1
                or body['contract_sha']!=events[row['event_id']]['contract_sha']
                or body.get('policy')!=(POLICY if body['contract_sha']==CONTRACT_SHA else V1_POLICY)):
            fail('DRAFT_RESTORE_AUTHORITY_INVALID')
        if body.get('clear_window')!=events[row['event_id']]['clear_window']:fail()
        check_clear_order(body['context'],body['clear_window'])
        # The source seal is created only by the trusted page after admission;
        # database rows alone are never restoration authority.
        from pathlib import Path
        from .publication_store import read_file
        name=db.execute('PRAGMA database_list').fetchone()[2]
        if name:
            seal=read_file(Path(name).parent/'draft-restore-authority'/(row['id']+'.json'))
            if seal != {'schema':1,'origin':'TRUSTED_SETTINGS_ADMISSION','body':body,'body_sha':digest(body)}:
                fail('DRAFT_RESTORE_SOURCE_INVALID')
        if body['contract_sha']==CONTRACT_SHA:
            from .own_draft_restore_metadata import verify
            verify(body['context'])
        grants[row['id']] = body
    expected = {}
    for row in db.execute('SELECT * FROM own_draft_restores'):
        grant = grants.get(row['grant_id'])
        intent = stored(row['intent'],row['intent_digest'])
        if (grant is None or row['parent_step_id'] != grant.get('parent_step_id')
                or intent.get('grant_sha') != digest(grant) or intent.get('contract_sha') != grant.get('contract_sha')
                or intent.get('restore_id') != row['id'] or intent.get('request_key') != row['request_key']):
            fail()
        if grant['contract_sha']==CONTRACT_SHA:
            context=grant['context']
            if (intent.get('schema')!=2 or any(intent.get(k)!=context[k] for k in ('original_payload_sha','restore_payload_sha','comment_policy_sha'))
                    or intent.get('payload_sha')!=context['restore_payload_sha']): fail('DRAFT_RESTORE_METADATA_INVALID')
        elif intent.get('schema')!=1: fail('DRAFT_RESTORE_METADATA_INVALID')
        if row['state'] == 'RESULT_UNKNOWN':
            if row['result_digest'] != EMPTY:
                fail()
            key=(row['tenant'],row['resource'],row['lineage'])
            if key in expected: fail()
            expected[key]=row['id']
        else:
            if policy is None:
                fail('DRAFT_RESTORE_PROOF_CONTEXT_REQUIRED')
            # Implemented in the execution/proof layer, never accept a row-only
            # success from a cache or a caller-supplied boolean.
            from .own_draft_restore_proof import validate_success
            validate_success(db,row,policy,source_kind)
    actual={(row['tenant'],row['resource'],row['lineage']):row['restore_id']
            for row in db.execute('SELECT * FROM own_draft_restore_locks')}
    if actual != expected: fail()


def check_external(db):
    """A restored old DB cannot erase an already admitted restoration attempt."""
    from pathlib import Path
    from .publication_store import read_file
    name = db.execute('PRAGMA database_list').fetchone()[2]
    if not name:
        return  # :memory: structural fixtures have no external durability claim.
    root = Path(name).parent
    path = root / 'draft-restore-spent.json'
    import os
    exists = os.path.lexists(path)
    has_table = db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='own_draft_restores'").fetchone() is not None
    rows = [dict(row) for row in db.execute('SELECT * FROM own_draft_restores ORDER BY id')] if has_table else []
    if not exists:
        if rows: fail('DRAFT_RESTORE_SPENT_PROOF_REQUIRED')
        return
    expected = read_file(path, 2 * 1024 * 1024)
    if (type(expected) is not dict or set(expected) != {'schema','contract_sha','claims'}
            or expected['schema'] != 1 or expected['contract_sha'] not in SUPPORTED_CONTRACTS
            or type(expected['claims']) is not dict):
        fail('DRAFT_RESTORE_SPENT_PROOF_INVALID')
    actual = {row['id']: spend_pin(row) for row in rows}
    if expected['claims'] != actual:
        fail('DRAFT_RESTORE_ROLLBACK_HOLD')


def spend_pin(row):
    keys=('id','grant_id','parent_step_id','request_key','tenant','principal','connection',
          'resource','lineage','owner','intent_digest','created')
    return digest({key:row[key] for key in keys})


def append_spent(db, row, root):
    """Caller owns account lock and uncommitted INSERT; write-before-commit."""
    from .publication_store import read_file
    from .own_connection_policy import atomic_write
    from pathlib import Path
    import os
    if not db.in_transaction:fail('DRAFT_RESTORE_TRANSACTION_REQUIRED')
    path=Path(root)/'draft-restore-spent.json'
    value=read_file(path,2*1024*1024) if os.path.lexists(path) else {
        'schema':1,'contract_sha':CONTRACT_SHA,'claims':{}}
    if set(value) != {'schema','contract_sha','claims'} or value['schema'] != 1 or value['contract_sha'] != CONTRACT_SHA:
        fail('DRAFT_RESTORE_SPENT_PROOF_INVALID')
    claims=dict(value['claims'])
    if row['id'] in claims:fail('DRAFT_RESTORE_ALREADY_SPENT')
    claims[row['id']]=spend_pin(row)
    actual={current['id']:spend_pin(current) for current in db.execute('SELECT * FROM own_draft_restores')}
    if claims != actual:fail('DRAFT_RESTORE_ROLLBACK_HOLD')
    atomic_write(path,dict(value,claims=claims),maximum=2*1024*1024)


def _read_claims(db):
    result={}
    for row in db.execute('SELECT restore_id,ordinal,created FROM own_draft_restore_reads ORDER BY restore_id,ordinal'):
        key=row['restore_id']+':'+str(row['ordinal'])
        result[key]=digest(dict(row))
    return result


def check_read_spent(db,root):
    from pathlib import Path
    import os
    from .publication_store import read_file
    path=Path(root)/'draft-restore-read-spent.json'
    actual=_read_claims(db)
    if not os.path.lexists(path):
        if actual:fail('DRAFT_RESTORE_READ_BUDGET_HOLD')
        return
    value=read_file(path,2*1024*1024)
    if (type(value) is not dict or value.get('contract_sha') not in SUPPORTED_CONTRACTS
            or value!={'schema':1,'contract_sha':value['contract_sha'],'claims':actual}):
        fail('DRAFT_RESTORE_READ_BUDGET_HOLD')


def append_read_spent(db,root,restore_id,ordinal):
    from pathlib import Path
    import os
    from .publication_store import read_file
    from .own_connection_policy import atomic_write
    path=Path(root)/'draft-restore-read-spent.json'
    value=read_file(path,2*1024*1024) if os.path.lexists(path) else {
        'schema':1,'contract_sha':CONTRACT_SHA,'claims':{}}
    actual=_read_claims(db);key=restore_id+':'+str(ordinal)
    if key not in actual or key in value.get('claims',{}):fail('DRAFT_RESTORE_READ_BUDGET_HOLD')
    previous=dict(actual);previous.pop(key)
    if value!={'schema':1,'contract_sha':CONTRACT_SHA,'claims':previous}:
        fail('DRAFT_RESTORE_READ_BUDGET_HOLD')
    atomic_write(path,{'schema':1,'contract_sha':CONTRACT_SHA,'claims':actual},maximum=2*1024*1024)
