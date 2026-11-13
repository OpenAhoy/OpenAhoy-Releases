"""Actual Group child approval inside its original ADD admission transaction."""
import time
from contextlib import contextmanager
from .contracts import WCEError
from .service import canonical
from .own_connection_workflow import PersistentWorkflow
from .own_auth import finite
from .own_validation_scope import OwnedConnection,_transaction_marker

_TIME=time.time;_MONOTONIC=time.monotonic


def need(value,code='GROUP_TARGET_APPROVAL_HOLD'):
    if value is not True:raise WCEError(code)


@contextmanager
def authorize_group_add_in(host,scope,db,profile,child,*,prepared, history_locators=None):
    from .draft_group_target_scope import group_approval_in,target_article_metadata
    from .own_lineage import seal
    need(type(db)is OwnedConnection and _transaction_marker(db)is not None,
         'GROUP_TARGET_APPROVAL_TRANSACTION')
    workflow=host.entry.service.workflow
    need(type(workflow)is PersistentWorkflow and type(child)is dict,
         'GROUP_TARGET_APPROVAL_WORKFLOW')
    selector=child['selector']
    manifest,checksum=workflow._bundle(db,profile,selector['bundle_id'],selector['version'])
    need(checksum==selector['content_digest'] and canonical(manifest)==child['manifest_json'],
         'GROUP_TARGET_APPROVAL_MANIFEST_CHANGED')
    current=workflow._profile(profile.actor,profile.connection_id,'local.write')
    need(current is profile,'GROUP_TARGET_APPROVAL_PROFILE_CHANGED')
    arguments=dict(selector,connection_id=profile.connection_id)
    with group_approval_in(host,scope,db,profile,manifest,prepared=prepared, history_locators=history_locators)as actual:
        lineage=seal(db,manifest)
        need(lineage['legacy']==0,'GROUP_TARGET_APPROVAL_LINEAGE')
        delegated=workflow._delegated_request_approval(manifest,lineage,arguments=arguments)
        need(delegated['article_metadata']==target_article_metadata(manifest,child),
             'GROUP_TARGET_APPROVAL_METADATA_CHANGED')
        now=_TIME()
        expires=min(now+300,profile.expires,profile.session_expires,profile.grant_expires,
                    profile.credential_expires,scope.source.not_after,
                    now+max(0,host.entry.deadline-_MONOTONIC()))
        need(finite(expires)and now<expires,'GROUP_TARGET_APPROVAL_EXPIRED')
        body,identifier,d=workflow._prepare_trial_approval_in(db,profile,profile.actor,
            profile.connection_id,selector['bundle_id'],selector['version'],checksum,expires,
            delegated=delegated, history_locators=history_locators)
        actual.check()
        approval_id=workflow._insert_trial_approval_in(db,profile,profile.actor,profile.connection_id,
            d,expires,body,identifier)
        # Keep the actual approval issuer alive through the original admission's
        # network preflight. Its exit must be the fixed pure gap-finalizer; no
        # extra current/file/history work is allowed before the own-step link.
        yield approval_id
