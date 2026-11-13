"""Sticky revision exclusion for all existing writers of the same article.

Only already validated manifests/lineages/original steps enter here. A missing
or inconsistent account sidecar is HOLD, never an empty set. This does not
initialize state or grant update/publication rights and does not inspect titles
alone or fetch any remote objects.
"""
import sqlite3
from pathlib import Path
from .contracts import WCEError
from .service import digest
from .draft_revision_store import RevisionStore


def hold():raise WCEError('DRAFT_REVISION_SAFETY_STATE_HOLD')


def identity_binding(d,source_kind):
    a=d['actor']
    return {'tenant':a['tenant_id'],'principal':a['principal_id'],'client':a['client_id'],
        'session':a['session_id'],'connection':d['connection_id'],'account':d['appid'],
        'resource':d['resource_id'],'generation':d['generation'],'epoch':d['epoch'],'source_kind':source_kind}


def policy_binding(policy,source_kind):return identity_binding(policy.data,source_kind)


def historical_identity_guard(policy):
    """Fixed local journal identity, without live send permission or renewal.

    Used only for status and an already-consumed admission's minimal result.
    Revocation, cancellation and a later code version still block every new
    business admission through the normal policy/service guards.
    """
    from copy import deepcopy
    from .own_connection_policy import ConnectionPolicy,load_policy
    if type(policy) is not ConnectionPolicy:hold()
    expected=deepcopy(policy.data)
    binding=digest(policy_binding(policy,'OPERATOR_ATTESTED'))
    def check():
        current=load_policy(policy.path,active=False)
        if (current.data!=expected or current.root_pin!=policy.root_pin
                or current.image_pin!=policy.image_pin
                or current.database_pin[:2]!=policy.database_pin[:2]
                or digest(policy_binding(current,'OPERATOR_ATTESTED'))!=binding):hold()
        if current.value['schema']==2:
            from .own_connection_registry import check_member
            check_member(current,revocation=False,readonly=True)
        return True
    check()
    return check


def initialize_new_account(identity,guard):
    """Trusted enrollment of a newly created, still unpublished account only.

    Existing-account upgrades use their exact reviewed installer/backup path.
    A missing sidecar of an existing current account is never reset here.
    """
    from .own_connection_policy import validate_identity
    import os
    root=Path(identity['private_directory']);validate_identity(identity,root);guard()
    if os.path.lexists(root/'draft-revisions') or os.path.lexists(root/'draft-revision-safety-anchor.json'):hold()
    RevisionStore(root,digest(identity_binding(identity,'OPERATOR_ATTESTED')),guard).initialize()
    guard()


def manifest_claims(manifest,*,lineage=None,step_id=None,reference=None):
    from .own_lineage import members
    claims=[('MANIFEST',digest(manifest))]
    # Per-member exact known semantic identities also catch a split/reordered
    # old group or the registered new artifact, independently of local IDs.
    claims += [('CONTENT',digest(member)) for member in members(manifest)]
    if manifest.get('schema') in (2,3):
        for article in manifest['document']['articles']:
            source=article.get('provenance',{}).get('source_sha256')
            if source is not None:claims.append(('PRODUCER_ARTIFACT',source))
    if lineage is not None:claims.append(('LINEAGE',lineage))
    if step_id is not None:claims.append(('SAVE_STEP',digest(step_id)))
    if reference is not None:claims.append(('DRAFT_REF',digest(reference)))
    return list(dict.fromkeys(claims))


def _manifest_claims_checked(policy,db,manifest,*,step_id=None,reference=None):
    from .own_connection_policy import ConnectionPolicy
    if type(policy) is not ConnectionPolicy:hold()
    policy.check()
    if manifest.get('binding')!=policy_binding(policy,manifest.get('binding',{}).get('source_kind')):hold()
    lineage=None
    version=manifest.get('version')
    if version is not None:
        row=db.execute('SELECT lineage FROM own_article_lineages WHERE version=?',(version,)).fetchone()
        if row is not None:lineage=row['lineage']
    claims=manifest_claims(manifest,lineage=lineage,step_id=step_id,reference=reference)
    return claims


def guard_manifest(policy,db,manifest,*,step_id=None,reference=None):
    claims=_manifest_claims_checked(policy,db,manifest,step_id=step_id,reference=reference)
    guard_claims(policy,manifest['binding'],claims)


def guard_manifest_readonly(policy,db,manifest):
    """Ordinary draft exclusion only; shared risk/publication callers stay strict."""
    from .own_connection_policy import ConnectionPolicy
    claims=_manifest_claims_checked(policy,db,manifest)
    binding=manifest['binding']
    if type(policy) is not ConnectionPolicy or binding!=policy_binding(policy,binding.get('source_kind')):hold()
    if policy.value['schema']==1 or binding.get('source_kind')=='SYNTHETIC_SETUP':
        # This new exception has no single-account or synthetic provenance route.
        return guard_claims(policy,binding,claims)
    policy.check()
    try:
        RevisionStore(policy.root,digest(binding),policy.check).guard_targets_readonly(policy,claims)
    except (OSError,sqlite3.Error):raise WCEError('DRAFT_REVISION_SAFETY_STATE_HOLD') from None
    policy.check()


def guard_claims(policy,binding,claims):
    from .own_connection_policy import ConnectionPolicy
    if type(policy) is not ConnectionPolicy or binding!=policy_binding(policy,binding.get('source_kind')):hold()
    policy.check()
    try:
        RevisionStore(policy.root,digest(binding),policy.check).guard_targets(claims)
    except (OSError,sqlite3.Error):raise WCEError('DRAFT_REVISION_SAFETY_STATE_HOLD') from None
    policy.check()


def guard_original_step(service,db,step_id, *, history_locators=None):
    """Resolve through original history/proof validators, never a supplied ref."""
    w=service.workflow;p=service.profile();w._resource(db,p, history_locators=history_locators)
    row=db.execute('SELECT * FROM own_steps WHERE id=?',(step_id,)).fetchone()
    if row is None:hold()
    intent,result=w._step(db,p,row, history_locators=history_locators)
    m,_=w._bundle(db,p,intent['selector']['bundle_id'],intent['selector']['version'])
    guard_manifest(service.policy,db,m,step_id=row['id'],reference=result.get('reference'))
