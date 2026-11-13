"""Host-only successful-submit receipt staging and local task recovery.

No JSON import endpoint, sender, token cache, new submit, or grant is exposed.
The private receipt directory shares the existing non-malicious same-UID trust
boundary; this is not a signature or a hostile-local-code sandbox.
"""
from dataclasses import asdict, is_dataclass, dataclass
from hashlib import sha256
import os
import re

from .publication_contract import CONTRACT_SHA, WIRE_PROFILE, exact, fail
from .publication_store import read_file as _read_file, commit_event, sync_directory
from .contracts import WCEError
from .http_transport import HTTPRequest
from .own_connection_policy import atomic_write
from .own_bootstrap_security import path_check
from .service import digest, canonical
from .publication_wire import parse, TaskID, _task

PINS = ('policy_id','policy_revision','artifact_id','review_id','snapshot_sha',
        'route','audience','draft_media_id','lineage_root','payload_sha','submit_claim_seq')
_SEAL = object()


@dataclass(frozen=True)
class HostCapture:
    reply: object
    account_key: str
    intent_id: str
    request_payload_sha: str
    response_projection_sha: str
    _seal: object

    def __post_init__(self):
        if self._seal is not _SEAL: fail('PUBLICATION_CAPTURE_REQUIRED')


def capture_submit(request, response, token, *, account_key, intent_id):
    """Must be called at the host's actual HTTP-return boundary, not on a file."""
    if (type(request) is not HTTPRequest or request.method!='POST'
            or request.path.split('?',1)[0]!='/cgi-bin/freepublish/submit'):
        fail('PUBLICATION_CAPTURE_REQUIRED')
    from .publication_contract import strict_json
    payload=strict_json(request.body)
    exact(payload,'media_id')
    reply = parse('freepublish.submit', response, token, account_key=account_key, intent_id=intent_id)
    return HostCapture(reply, account_key, intent_id, digest(payload), digest(_project(reply.result)), _SEAL)


def read_file(path):
    try: return _read_file(path)
    except (OSError,WCEError): fail('PUBLICATION_RECEIPT_HOLD')


def _project(value):
    if is_dataclass(value): return _project(asdict(value))
    if type(value) is dict: return {k: _project(v) for k,v in value.items()}
    if type(value) in (tuple,list): return [_project(v) for v in value]
    return value


def _row_and_claim(store, db, intent_id, allow_pending=False):
    store._verify(db,allow_pending=allow_pending)
    row=db.execute('SELECT * FROM publication_intents WHERE account_key=? AND intent_id=?',
                   (store.key,intent_id)).fetchone()
    if row is None or row['submit_count'] != 1 or row['submit_claim_seq'] is None:
        fail('PUBLICATION_RECEIPT_HOLD')
    claim=db.execute("SELECT * FROM publication_events WHERE account_key=? AND seq=? AND event_type='SUBMIT_CLAIM' AND intent_id=?",
                     (store.key,row['submit_claim_seq'],intent_id)).fetchone()
    if claim is None: fail('PUBLICATION_RECEIPT_HOLD')
    from .publication_contract import strict_json
    event=strict_json(claim['event_json'].encode())
    if (event['data'].get('payload_sha')!=row['payload_sha']
            or event['data'].get('binding_sha')!=store.binding_sha):
        fail('PUBLICATION_RECEIPT_HOLD')
    return dict(row),dict(claim)


def _proof(store, proof, row):
    exact(proof,'schema origin account_key binding_sha contract_sha intent_id query_seq http_status response_sha wire_profile result error_code reason created_ms pins')
    if (proof['schema']!='PUBLICATION_PROOF_V1' or proof['account_key']!=store.key
            or proof['binding_sha']!=store.binding_sha or proof['contract_sha']!=CONTRACT_SHA
            or proof['intent_id']!=row['intent_id'] or proof['query_seq'] is not None
            or type(proof['http_status']) is not int or proof['http_status']!=200
            or proof['wire_profile']!=WIRE_PROFILE or proof['reason']!='PARSED_SUCCESS'
            or proof['error_code'] is not None or type(proof['created_ms']) is not int
            or type(proof['response_sha']) is not str or not re.fullmatch('[a-f0-9]{64}',proof['response_sha'])
            or proof['pins']!={k:row[k] for k in PINS}
            or row['route']!='FREEPUBLISH' or row['audience']!='NO_PUSH'
            or type(proof['result']) is not dict or type(proof['result'].get('task')) is not dict):
        fail('PUBLICATION_RECEIPT_HOLD')
    try:
        task=TaskID(**proof['result']['task'])
        _task(task,'PUBLISH_TASK',store.key,row['intent_id'])
    except Exception:
        fail('PUBLICATION_RECEIPT_HOLD')
    if task.source_method!='freepublish.submit' or task.response_sha!=proof['response_sha']:
        fail('PUBLICATION_RECEIPT_HOLD')
    return task


def _origin(db):
    source=db.execute('SELECT source_kind FROM own_config WHERE id=1').fetchone()[0]
    if source=='OPERATOR_ATTESTED': return 'OWN_OFFICIAL_WIRE'
    if source=='SYNTHETIC_SETUP': return 'SYNTHETIC_PUBLICATION'
    fail('PUBLICATION_RECEIPT_HOLD')


def _context(store,db,row):
    """Bind the original durable policy/candidate/QA context, not file claims."""
    from .publication_contract import strict_json
    policy=db.execute('SELECT * FROM publication_policy WHERE account_key=? AND policy_id=?',
        (store.key,row['policy_id'])).fetchone()
    candidate=db.execute('SELECT * FROM publication_candidates WHERE account_key=? AND artifact_id=?',
        (store.key,row['artifact_id'])).fetchone()
    review=db.execute('SELECT * FROM publication_reviews WHERE account_key=? AND review_id=?',
        (store.key,row['review_id'])).fetchone()
    if (policy is None or candidate is None or review is None
            or policy['revision']!=row['policy_revision'] or policy['contract_sha']!=CONTRACT_SHA
            or candidate['policy_id']!=row['policy_id'] or review['artifact_id']!=row['artifact_id']
            or candidate['draft_media_id']!=row['draft_media_id']
            or candidate['lineage_root']!=row['lineage_root']
            or review['current_draft_sha']!=row['snapshot_sha']
            or digest(strict_json(policy['policy_json'].encode()))!=policy['policy_sha']
            or digest(strict_json(candidate['frozen_manifest_json'].encode()))!=candidate['frozen_sha']
            or digest(strict_json(review['receipt_json'].encode()))!=review['receipt_sha']):
        fail('PUBLICATION_RECEIPT_HOLD')
    return {'identity_sha':digest(strict_json(policy['identity_json'].encode())),
        'policy':{k:policy[k] for k in ('policy_id','revision','activation_epoch','contract_sha','policy_sha','trusted_source_sha')},
        'candidate':{k:candidate[k] for k in ('artifact_id','channel_id','activation_epoch','owner_epoch','event_seq','input_sha','bundle_id','version','frozen_sha','draft_step_id')},
        'review':{k:review[k] for k in ('review_id','profile_sha','input_sha','current_draft_sha','owner_epoch','runtime_receipt_sha','receipt_sha','created_ms','expires_ms')}}


def index_path(store,intent_id):
    return store.anchor/'submit-receipts'/(sha256(intent_id.encode()).hexdigest()+'.json')


def stage_submit_receipt(store, proof_name, capture):
    """Caller holds dispatch_lock; proof has already been file+dir fsynced.

    Must run BEFORE proof_before_result_commit fault injection. A random proof
    file alone is never enough to establish a task after restart.
    """
    if (type(capture) is not HostCapture or capture._seal is not _SEAL
            or capture.account_key!=store.key or capture.reply.result is None
            or type(proof_name) is not str or not re.fullmatch('proof-[a-f0-9]{32}\\.json',proof_name)):
        fail('PUBLICATION_CAPTURE_REQUIRED')
    proof=read_file(store.anchor/'proofs'/proof_name)
    # The proof file writer fsynced this directory; fsync its parent as well so
    # a freshly mkdir'ed proofs directory cannot vanish after result commit.
    sync_directory(store.anchor/'proofs')
    sync_directory(store.anchor)
    with store.connection() as db:
        row,claim=_row_and_claim(store,db,capture.intent_id)
        _proof(store,proof,row)
        context=_context(store,db,row)
        if (proof['origin']!=_origin(db) or proof['result']!=_project(capture.reply.result)
                or proof['pins']['payload_sha']!=capture.request_payload_sha
                or digest(_project(capture.reply.result))!=capture.response_projection_sha
                or proof['response_sha']!=capture.reply.response_sha
                or proof['http_status']!=capture.reply.http_status
                or proof['reason']!=capture.reply.reason or capture.reply.error_code is not None):
            fail('PUBLICATION_CAPTURE_REQUIRED')
    index={'schema':'PUBLICATION_SUBMIT_RECEIPT_V1','account_key':store.key,
        'binding_sha':store.binding_sha,'contract_sha':CONTRACT_SHA,'intent_id':row['intent_id'],
        'submit_claim_seq':row['submit_claim_seq'],'claim_event_sha':claim['event_sha'],
        'proof_name':proof_name,'proof_sha':digest(proof),'pins_sha':digest(proof['pins']),
        'context':context,'context_sha':digest(context),'http_method':'POST',
        'api_path':'/cgi-bin/freepublish/submit','wire_profile':WIRE_PROFILE,
        'request_payload_sha':capture.request_payload_sha,'response_sha':capture.reply.response_sha}
    path=index_path(store,row['intent_id'])
    if not path.parent.exists(): path.parent.mkdir(mode=0o700)
    path_check(path.parent,True)
    sync_directory(path.parent.parent)
    if os.path.lexists(path):
        if read_file(path)!=index: fail('PUBLICATION_RECEIPT_HOLD')
    else:
        atomic_write(path,index)
    # Atomic writer verifies file+directory durability; read it back now too.
    if read_file(path)!=index: fail('PUBLICATION_RECEIPT_HOLD')
    return {'state':'SUBMIT_RECEIPT_STAGED','receipt_sha':digest(index)}


def _recovery_material(store,db,intent_id,allow_pending=False):
    index=read_file(index_path(store,intent_id))
    exact(index,'schema account_key binding_sha contract_sha intent_id submit_claim_seq claim_event_sha proof_name proof_sha pins_sha context context_sha http_method api_path wire_profile request_payload_sha response_sha')
    if (index['schema']!='PUBLICATION_SUBMIT_RECEIPT_V1' or index['account_key']!=store.key
            or index['binding_sha']!=store.binding_sha or index['contract_sha']!=CONTRACT_SHA
            or index['intent_id']!=intent_id or type(index['proof_name']) is not str
            or not re.fullmatch('proof-[a-f0-9]{32}\\.json',index['proof_name'])):
        fail('PUBLICATION_RECEIPT_HOLD')
    proof=read_file(store.anchor/'proofs'/index['proof_name'])
    row,claim=_row_and_claim(store,db,intent_id,allow_pending=allow_pending)
    task=_proof(store,proof,row)
    context=_context(store,db,row)
    if (index['proof_sha']!=digest(proof) or index['pins_sha']!=digest(proof['pins'])
            or index['context']!=context or index['context_sha']!=digest(context)
            or index['http_method']!='POST' or index['api_path']!='/cgi-bin/freepublish/submit'
            or index['wire_profile']!=WIRE_PROFILE
            or index['request_payload_sha']!=row['payload_sha'] or index['response_sha']!=proof['response_sha']
            or index['claim_event_sha']!=claim['event_sha']
            or index['submit_claim_seq']!=row['submit_claim_seq'] or proof['origin']!=_origin(db)):
        fail('PUBLICATION_RECEIPT_HOLD')
    return row,task,index,proof


def _set_task(store,db,row,task,proof):
    if row['state'] not in {'SUBMITTING','RESULT_UNKNOWN'}: fail('PUBLICATION_RECEIPT_HOLD')
    cursor=db.execute("UPDATE publication_intents SET state='ACCEPTED',task_kind=?,task_digits=?,task_wire_type=?,task_raw_token=?,last_proof_sha=? WHERE account_key=? AND intent_id=? AND submit_count=1 AND task_digits IS NULL AND state IN ('SUBMITTING','RESULT_UNKNOWN')",
        (task.kind,task.digits,task.wire_type,task.raw_token,digest(proof),store.key,row['intent_id']))
    if cursor.rowcount!=1: fail('PUBLICATION_RECEIPT_HOLD')


def _recover_pending_result(store,intent_id):
    """Rebuild only an exact already-anchored result from its staged receipt."""
    head=store._head(allow_pending=True)
    if head['confirmed_seq']!=head['seq']-1: fail('PUBLICATION_RECEIPT_HOLD')
    event=read_file(store.anchor/(str(head['seq']).zfill(16)+'.json'))
    if (type(event) is not dict or type(event.get('data')) is not dict
            or event.get('event_type')!='SUBMIT_RESULT' or event['data'].get('intent_id')!=intent_id
            or digest(event)!=head['event_sha']):
        fail('PUBLICATION_RECEIPT_HOLD')
    with store.connection(write=True) as db:
        last=db.execute('SELECT COALESCE(MAX(seq),0) FROM publication_events WHERE account_key=?',(store.key,)).fetchone()[0]
        if last!=head['seq']-1: fail('PUBLICATION_RECEIPT_HOLD')
        # Uncommitted insertion allows the same complete chain verifier to
        # validate the pending original event, before restoring any task state.
        db.execute('INSERT INTO publication_events VALUES(?,?,?,?,?,?,?)',
            (store.key,head['seq'],'SUBMIT_RESULT',intent_id,event['previous_sha'],canonical(event),digest(event)))
        store._verify(db,allow_pending=True)
        # Recovery material verification needs the just-validated pending head;
        # it does not create a new event or replay an external action.
        row,task,index,proof=_recovery_material(store,db,intent_id,allow_pending=True)
        if event['data'].get('proof_name')!=index['proof_name'] or event['data'].get('proof_sha')!=index['proof_sha']:
            fail('PUBLICATION_RECEIPT_HOLD')
        _set_task(store,db,row,task,proof)
    store.confirm(head)
    return {'state':'TASK_RECOVERED_ORIGINAL_ANCHOR_LOCAL_ONLY','submit_count':1}


def recover_submit_receipt(store,intent_id):
    """Caller holds dispatch_lock. Local historical task recovery, never POST."""
    try: store.recover_committed_head()
    except WCEError: return _recover_pending_result(store,intent_id)
    with store.connection() as db:
        row,task,index,proof=_recovery_material(store,db,intent_id)
        if row['task_digits'] is not None:
            if (row['task_kind'],row['task_digits'],row['task_wire_type'],row['task_raw_token']) != (task.kind,task.digits,task.wire_type,task.raw_token):
                fail('PUBLICATION_RECEIPT_HOLD')
            return {'state':'TASK_ALREADY_RECORDED','submit_count':1}
        if row['state'] not in {'SUBMITTING','RESULT_UNKNOWN'}: fail('PUBLICATION_RECEIPT_HOLD')
    def apply(db,seq):
        current,original=_row_and_claim(store,db,intent_id)
        _proof(store,proof,current)
        _set_task(store,db,current,task,proof)
    commit_event(store,'SUBMIT_RESULT',{'intent_id':intent_id,'proof_name':index['proof_name'],
        'proof_sha':index['proof_sha'],'completion_origin':'ORIGINAL_RECEIPT_LOCAL_RECOVERY'},apply)
    return {'state':'TASK_RECOVERED_LOCAL_ONLY','submit_count':1}
