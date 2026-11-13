"""Restore response proof validation. No network or arbitrary proof import."""
import re
import math
from pathlib import Path
from .own_draft_restore_contract import fail, stored, CONTRACT_SHA, V1_CONTRACT_SHA, ORIGIN, parent_pin
from .publication_store import read_file
from .own_draft_wire import reference_valid
from .service import digest


def index_name(identifier):
    if type(identifier) is not str or re.fullmatch(r'restore-[a-f0-9]{32}', identifier) is None:
        fail()
    return 'result-' + identifier + '.json'


def validate_success(db, row, policy, source_kind):
    intent = stored(row['intent'],row['intent_digest'])
    result = stored(row['result'],row['result_digest'])
    folder = policy.root / 'draft-restore-proofs'
    name = row['proof_name']
    if type(name) is not str or re.fullmatch(r'proof-[a-f0-9]{32}\.json', name) is None:
        fail('DRAFT_RESTORE_PROOF_INVALID')
    proof = read_file(folder/name)
    index = read_file(folder/index_name(row['id']))
    keys = ('id','grant_id','parent_step_id','request_key','tenant','principal','connection',
            'resource','lineage','owner','intent_digest','created')
    row_pin = digest({key:row[key] for key in keys})
    provenance = 'OWN_OFFICIAL_WIRE' if source_kind == 'OPERATOR_ATTESTED' else 'SYNTHETIC_RESTORE'
    if (index != {'schema':1,'restore_id':row['id'],'row_pin_sha':row_pin,
                  'proof_name':name,'proof_sha':row['proof_sha']}
            or digest(proof) != row['proof_sha'] or proof.get('schema') != 1
            or proof.get('origin') != ORIGIN or proof.get('provenance') != provenance
            or proof.get('contract_sha') != intent.get('contract_sha') or intent.get('contract_sha') not in (V1_CONTRACT_SHA,CONTRACT_SHA) or proof.get('row_pin_sha') != row_pin
            or proof.get('result') != result or proof.get('grant_sha') != intent.get('grant_sha')
            or proof.get('payload_sha') != intent.get('payload_sha')
            or proof.get('binding') != intent.get('binding')
            or type(proof.get('response_sha')) is not str
            or re.fullmatch('[a-f0-9]{64}', proof['response_sha']) is None
            or proof.get('http_status') != 200
            or type(proof.get('observed_at')) not in (int,float) or not math.isfinite(proof['observed_at'])
            or row['completed'] != proof['observed_at']
            or set(result) != {'reference'}
            or not reference_valid(result['reference'],source_kind=='SYNTHETIC_SETUP')):
        fail('DRAFT_RESTORE_PROOF_INVALID')
    grant_row=db.execute('SELECT * FROM own_draft_restore_grants WHERE id=?',(row['grant_id'],)).fetchone()
    if grant_row is None: fail('DRAFT_RESTORE_PROOF_INVALID')
    grant=stored(grant_row['body'],grant_row['body_digest'])
    if digest(grant)!=intent.get('grant_sha') or grant.get('contract_sha')!=intent.get('contract_sha'): fail('DRAFT_RESTORE_PROOF_INVALID')
    if intent.get('contract_sha')==CONTRACT_SHA:
        from .own_draft_restore_metadata import verify
        context=grant['context'];verify(context)
        if (intent.get('schema')!=2 or intent.get('payload_sha')!=context['restore_payload_sha']
                or any(intent.get(k)!=context[k] for k in ('original_payload_sha','restore_payload_sha','comment_policy_sha'))): fail('DRAFT_RESTORE_PROOF_INVALID')
    parent=db.execute('SELECT * FROM own_steps WHERE id=?',(row['parent_step_id'],)).fetchone()
    if parent is None or parent_pin(parent) != intent.get('parent_step_sha'):
        fail('DRAFT_RESTORE_PARENT_CHANGED')
    return result
