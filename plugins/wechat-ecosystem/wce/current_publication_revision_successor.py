"""Append-only revision successor evidence; never itself sends a publication.

This stages one proof-bound successor identity. The caller must still resolve
that identity through an explicit publication admission path; this module
must not be interpreted as providing that path or authority.
"""
from .contracts import WCEError
from .publication_contract import digest

PROFILE='CURRENT_REVISION_SUCCESSOR_V1'

def hold():raise WCEError('CURRENT_REVISION_SUCCESSOR_HOLD')

def _record(handle,reservation,effect):
    if (effect['case_id']!=reservation['case_id'] or effect['revision_id']!=reservation['revision_id']
            or effect['binding_sha256']!=reservation['binding_sha256']
            or effect['source_sha256']!=reservation['source_sha256']
            or effect['reference_sha256']!=reservation['reference_sha256']
            or effect['baseline_sha256']!=reservation['baseline_sha256']
            or effect['original_intent']!=handle):hold()
    successor='current-pub-'+digest({'profile':PROFILE,'original_intent':handle,
        'case_id':effect['case_id'],'result_proof_sha256':effect['result_proof_sha256'],
        'projection_sha256':effect['projection_sha256']})[:48]
    return {'profile':PROFILE,'original_intent':handle,'successor_handle':successor,'effect':effect}

def verify_successor(publication,handle,row,reservation,record,guard):
    from .current_publication_revision_proof import _effect
    if (type(record) is not dict or set(record)!={'profile','original_intent','successor_handle','effect'}
            or record.get('profile')!=PROFILE or record.get('original_intent')!=handle
            or type(record.get('effect')) is not dict):hold()
    ordinal=record['effect'].get('read_ordinal')
    effect=_effect(publication,handle,row,reservation['case_id'],guard,ordinal=ordinal)
    if _record(handle,reservation,effect)!=record:hold()

def stage(publication,handle,case_id,gate,authority,guard):
    from .current_publication_store import Store
    from .draft_revision_gate import RevisionExecutionGate
    from .current_publication_revision_proof import verified_effect
    if (type(publication) is not Store or type(gate) is not RevisionExecutionGate
            or gate.service.policy is not publication.policy or not callable(guard)
            or gate.held() is not True):hold()
    guard();value,row=publication.target(handle)
    publication._authority(authority,guard,row['batch_source_sha'])
    reservation=value.get('revision_reservations',{}).get(handle)
    if type(reservation) is not dict or reservation.get('case_id')!=case_id:hold()
    current=value.get('revision_successors',{}).get(handle)
    if current is not None:
        verify_successor(publication,handle,row,reservation,current,guard)
        publication._authority(authority,guard,row['batch_source_sha'])
        if gate.held() is not True:hold()
        return current
    effect=verified_effect(publication,handle,case_id,gate,authority,guard)
    record=_record(handle,reservation,effect)
    used=set(value['targets'])|{v['successor_handle'] for v in value.get('revision_successors',{}).values()}
    if record['successor_handle'] in used:hold()
    value.setdefault('revision_successors',{})[handle]=record;value['sequence']+=1
    publication._authority(authority,guard,row['batch_source_sha'])
    if gate.held() is not True:hold()
    publication.save(value)
    publication._authority(authority,guard,row['batch_source_sha'])
    if gate.held() is not True:hold()
    return record


def activate(publication,handle,gate,authority,guard):
    """Append a target only for an already staged, independently proven effect."""
    from .current_publication_store import Store,_successor_row
    from .draft_revision_gate import RevisionExecutionGate
    if (type(publication) is not Store or type(gate) is not RevisionExecutionGate
            or gate.service.policy is not publication.policy or not callable(guard)
            or gate.held() is not True):hold()
    guard();value,row=publication.target(handle)
    publication._authority(authority,guard,row['batch_source_sha'])
    reservation=value.get('revision_reservations',{}).get(handle)
    record=value.get('revision_successors',{}).get(handle)
    if type(reservation) is not dict or type(record) is not dict:hold()
    verify_successor(publication,handle,row,reservation,record,guard)
    child=record['successor_handle'];existing=value['targets'].get(child)
    if existing is not None:
        expected=_successor_row(row,record)
        from .current_publication_store import MUTABLE_TARGET_FIELDS
        if ({k:v for k,v in existing.items() if k not in MUTABLE_TARGET_FIELDS}
                != {k:v for k,v in expected.items() if k not in MUTABLE_TARGET_FIELDS}):hold()
        publication._authority(authority,guard,row['batch_source_sha'])
        if gate.held() is not True:hold()
        guard()
        return existing
    if value.get('denial') is not None:hold()
    value['targets'][child]=_successor_row(row,record)
    batch=value['batches'][row['batch_source_sha']]
    if child in batch['intent_handles']:hold()
    batch['intent_handles'].append(child);value['sequence']+=1
    publication._authority(authority,guard,row['batch_source_sha'])
    if gate.held() is not True:hold()
    publication.save(value)
    publication._authority(authority,guard,row['batch_source_sha'])
    if gate.held() is not True:hold()
    return value['targets'][child]
