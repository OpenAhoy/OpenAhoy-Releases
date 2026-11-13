"""Verify a completed original revision before proposing a current successor.

This module is read-only. It does not issue a reservation, authorize UPDATE,
create a successor, or grant/dispatch publication. The caller must hold the
exact active revision execution gate; all evidence is reopened from the real
revision journal and its validated immutable proofs.
"""
from .contracts import WCEError
from .publication_contract import binding, digest


def hold():
    raise WCEError('CURRENT_REVISION_PROOF_UNAVAILABLE')


def _effect(publication, handle, target, case_id, guard, *, ordinal=None):
    """Reopen local immutable history; this helper is not an authorization."""
    from .current_publication_store import Store
    from .draft_revision_guard import policy_binding
    from .draft_revision_store import RevisionStore, OFFICIAL_PROVIDER
    from .draft_revision_wire import baseline_projection as revision_projection
    from .draft_revision_preservation import effect_matches
    from .draft_group_wire import GroupSnapshot, baseline_projection as group_projection
    if (type(publication) is not Store or type(target) is not dict or not callable(guard)
            or type(case_id) is not str or len(case_id)!=64
            or any(c not in '0123456789abcdef' for c in case_id)):
        hold()
    guard()
    revision = RevisionStore(publication.policy.root,
        digest(policy_binding(publication.policy, 'OPERATOR_ATTESTED')), guard)
    with revision.connection() as db:
        state = revision._state(db, case_id)
        case = state['case']
        row = state['revision']
        if (case['id'] != case_id or case['provider_profile'] != OFFICIAL_PROVIDER
                or case['binding'] != revision.binding
                or case['target'] != digest(target['reference'])
                or row['case_id'] != case_id or row['writes'] != 1
                or row['response_state'] != 'SUCCEEDED_RESPONSE'):
            hold()
        if ordinal is None:
            if (type(row['effect']) is not dict or row['effect'].get('matched') is not True
                    or row['effect'].get('origin') != 'ADMITTED_RESPONSE_AND_READBACK'):hold()
            ordinal=row['effect'].get('ordinal')
        if (type(ordinal) is not int or ordinal < 1 or ordinal > len(state['read_claims'])
                or state['read_claims'][ordinal-1]['state'] != 'OBSERVED'
                or state['read_claims'][ordinal-1]['phase'] not in {'POST_SEND','RECOVERY_EFFECT'}):
            hold()
        from .publication_contract import strict_json
        effects=[]
        for event_row in db.execute('SELECT value FROM events ORDER BY seq'):
            event=strict_json(event_row['value'].encode(), maximum=2*1024*1024)
            if (event['case_id']==case_id and event['type']=='READ_EFFECT'
                    and event['data']=={'ordinal':ordinal,'matched':True}):effects.append(event)
        if len(effects)!=1:hold()
        response = revision._load_proof(f'response-{case_id}.json', row['response_sha'], case)
        prepared = revision._load_proof(f'prepared-{case_id}.json', row['preparation_sha'], case)
        snapshot = revision._read_snapshot(state, ordinal)
        if (snapshot is None or snapshot.reference != target['reference']
                or response['data'].get('response_state') != 'SUCCEEDED_RESPONSE'
                or response['data'].get('errcode') != 0
                or response['data'].get('claim_sha') != row['claim_sha']
                or response['data'].get('request_sha') != row['request_sha']
                or digest(prepared['data']['expected']) != row['expected_sha']
                or not effect_matches(revision_projection(snapshot), prepared['data']['expected'])):
            hold()
        observed = group_projection(GroupSnapshot(snapshot.reference, snapshot.canonical_json,
            snapshot.response_sha))
        result = {'profile':'CURRENT_REVISION_EFFECT_PROOF_V1', 'case_id':case_id,
            'revision_id':row['id'], 'binding_sha256':binding(publication.policy.data),
            'reference_sha256':digest(target['reference']),
            'source_sha256':target['batch_source_sha'], 'original_intent':handle,
            'baseline_sha256':row['baseline_sha'], 'expected_sha256':row['expected_sha'],
            'preparation_sha256':row['preparation_sha'], 'claim_sha256':row['claim_sha'],
            'response_proof_sha256':row['response_sha'], 'result_proof_sha256':state['read_claims'][ordinal-1]['result_sha'],
            'read_ordinal':ordinal, 'response_sha256':snapshot.response_sha,
            'projection_sha256':digest(observed), 'projection':observed}
    guard()
    return result


def verified_effect(publication, handle, case_id, gate, authority, guard):
    """Fresh gated completion; no side effects and no new permission."""
    from .current_publication_store import Store
    from .draft_revision_gate import RevisionExecutionGate
    if (type(publication) is not Store or type(gate) is not RevisionExecutionGate
            or gate.service.policy is not publication.policy or not callable(guard)
            or gate.held() is not True):hold()
    _,target=publication.target(handle)
    publication._authority(authority,guard,target['batch_source_sha'])
    result=_effect(publication,handle,target,case_id,guard)
    publication._authority(authority,guard,target['batch_source_sha'])
    if gate.held() is not True:hold()
    guard()
    return result
