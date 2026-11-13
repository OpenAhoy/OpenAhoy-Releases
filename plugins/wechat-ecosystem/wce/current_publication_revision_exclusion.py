"""Current-request-only negative revision exclusion, never a grant.

Caller must already hold the existing same-account publication coordination
locks. The existing shared revision writer/publication guards remain strict.
"""
import sqlite3

from .contracts import WCEError
from .publication_contract import binding, digest
from .own_connection_policy import ConnectionPolicy
from .draft_revision_guard import policy_binding
from .draft_revision_store import RevisionStore


def _hold():
    raise WCEError('CURRENT_PUBLICATION_REVISION_EXCLUSION_HOLD')


def _current(policy, authority, guard, source_sha):
    from .current_publication_source import Authorization, PURPOSE, _SEAL, is_current, CURRENT_SCOPE
    from .single_publication_source import is_single, is_authority, PURPOSE as SINGLE_PURPOSE
    from .saved_groups_publication_source import is_saved_groups, PURPOSE as SAVED_GROUPS_PURPOSE
    def identity():
        if (type(policy) is not ConnectionPolicy or not is_authority(authority) or not callable(guard)
                or type(source_sha) is not str or authority.source_sha != source_sha
                or authority.policy is not policy or authority.policy_binding != binding(policy.data)
                or authority.connection_id != policy.data['connection_id']):
            _hold()
        value = authority.value
        if is_saved_groups(authority):
            if (type(value) is not dict or value.get('purpose') != SAVED_GROUPS_PURPOSE
                    or authority.request_identity != source_sha
                    or digest({'purpose': SAVED_GROUPS_PURPOSE,
                        'event': {k: value.get(k) for k in
                            ('source_thread','turn_id','message_id','text_sha256')},
                        'principal': policy.data['actor']['principal_id'],
                        'tenant': policy.data['actor']['tenant_id']}) != source_sha):
                _hold()
            return
        if is_single(authority):
            if value.get('purpose') != SINGLE_PURPOSE or authority.request_identity != source_sha:
                _hold()
            return
        if (type(value) is not dict or value.get('purpose') != PURPOSE
                or any(key not in value for key in
                    ('source_thread','turn_id','message_id','text_sha256','connections'))):
            _hold()
        source_identity = {'purpose': PURPOSE, 'event': {k: value[k] for k in
            ('source_thread','turn_id','message_id','text_sha256')},
            'connections': value['connections']}
        if is_current(authority):
            if value.get('scope') != CURRENT_SCOPE:
                _hold()
            # Schema2 current Source binds its closed inventory scope into the
            # identity. Other authority profiles keep their original formula.
            source_identity['scope'] = value.get('scope')
        if digest(source_identity) != source_sha:
            _hold()
    identity()
    if guard() is not True:
        _hold()
    authority.fence()
    if guard() is not True or policy.check() is not True:
        _hold()
    identity()
    if guard() is not True:
        _hold()


def exclude_reference(policy, authority, guard, source_sha, reference):
    """Check only the original DRAFT_REF; no permission/positive result."""
    if type(reference) is not str or not reference:
        _hold()
    _current(policy, authority, guard, source_sha)
    from .draft_revision_guard import guard_claims
    bound = policy_binding(policy, 'OPERATOR_ATTESTED')
    claims = [('DRAFT_REF', digest(reference))]
    if policy.value.get('schema') == 1:
        guard_claims(policy, bound, claims)
    elif policy.value.get('schema') == 2:
        try:
            RevisionStore(policy.root, digest(bound), guard).guard_targets_readonly(policy, claims)
        except (OSError, sqlite3.Error):
            raise WCEError('DRAFT_REVISION_SAFETY_STATE_HOLD') from None
    else:
        _hold()
    _current(policy, authority, guard, source_sha)


def exclude_completed_reference(policy, authority, guard, source_sha, reference, case_id):
    """Exclude one exact proven successor case, never any other Case."""
    if (type(reference) is not str or not reference or type(case_id) is not str
            or len(case_id)!=64 or any(c not in '0123456789abcdef' for c in case_id)
            or policy.value.get('schema')!=2):_hold()
    _current(policy,authority,guard,source_sha)
    bound=policy_binding(policy,'OPERATOR_ATTESTED')
    try:
        journal=RevisionStore(policy.root,digest(bound),guard)
        with journal._readonly_connection(policy) as (db,head):
            rows=db.execute("SELECT case_id FROM targets WHERE kind='DRAFT_REF' AND fingerprint=?",
                (digest(reference),)).fetchall()
            if len(rows)!=1 or rows[0][0]!=case_id:_hold()
            state=journal._state(db,case_id)
            if state['case']['target']!=digest(reference):_hold()
    except (OSError,sqlite3.Error):
        raise WCEError('DRAFT_REVISION_SAFETY_STATE_HOLD') from None
    _current(policy,authority,guard,source_sha)
