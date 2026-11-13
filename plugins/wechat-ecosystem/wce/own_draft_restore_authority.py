"""Grant construction only after the existing trusted human page admission.

No model tool can invoke this module or supply a human/source approval boolean.
The active SettingsBackend owns the one-shot review and its exact prepared set.
"""
from dataclasses import dataclass
from hashlib import sha256
import time
from uuid import uuid4
from .contracts import WCEError
from .service import canonical, digest
from .own_connection_policy import atomic_write
from .publication_store import read_file, sync_directory
from .own_draft_restore_contract import fail, stored, CONTRACT_SHA, POLICY, clear_event_id, check_clear_order

_SEAL=object()

@dataclass(frozen=True)
class AdmittedRestoreReview:
    payload: dict
    _seal: object


def admitted_review(backend, reviewed, guard):
    from .own_settings_backend import SettingsBackend
    guard()
    if (type(backend) is not SettingsBackend or reviewed.get('intent') != 'RESTORE_DRAFTS'
            or backend.state != 'ACTIVE' or backend.review is not None
            or reviewed['generation'] != backend.generation or reviewed['target'] != backend.selected
            or type(reviewed.get('confirmed_at')) not in (int,float)
            or reviewed.get('restore_prepared_sha') != digest(reviewed.get('restore_prepared'))
            or reviewed.get('restore_display_sha') != digest(reviewed.get('restore_display'))):
        fail('DRAFT_RESTORE_HUMAN_REVIEW_REQUIRED')
    prepared=reviewed['restore_prepared']
    if (type(prepared) is not dict or prepared.get('contract_sha') != CONTRACT_SHA
            or prepared.get('scope') != 'KNOWN_SUCCEEDED_REMOVED_ONLY'
            or not prepared.get('parents') or not prepared.get('exclusion_source_sha')):
        fail('DRAFT_RESTORE_REVIEW_CHANGED')
    value={'schema':1,'contract_sha':CONTRACT_SHA,'prepared':prepared,
        'confirmed_at':reviewed['confirmed_at'],
        'human_review_sha':digest({'id':reviewed['id'],'approval':reviewed['approval'],
            'display_sha':reviewed['restore_display_sha'],'confirmed_at':reviewed['confirmed_at']})}
    guard()
    return AdmittedRestoreReview(value,_SEAL)


def require_admitted(value):
    if type(value) is not AdmittedRestoreReview or value._seal is not _SEAL:
        fail('DRAFT_RESTORE_HUMAN_REVIEW_REQUIRED')
    return value.payload


def source_event(admitted, policy, context):
    value=require_admitted(admitted);prepared=value['prepared']
    if context not in prepared['parents'] or context['binding']['connection'] != policy.data['connection_id']:
        fail('DRAFT_RESTORE_REVIEW_CHANGED')
    # The event key is prepared once per actual clear statement, never from a
    # new approval nonce or an assistant-selected request alias.
    event_id=prepared['clear_event_id']
    if event_id != clear_event_id(prepared['clear_source_sha'],prepared['clear_window']):
        fail('DRAFT_RESTORE_SOURCE_INVALID')
    check_clear_order(context,prepared['clear_window'])
    body={'schema':1,'event_id':event_id,'contract_sha':CONTRACT_SHA,
        'source_kind':'TRUSTED_HUMAN_REVIEW','binding':context['binding'],
        'clear_statement':prepared['clear_statement'],
        'source_reference_sha':prepared['clear_source_sha'],
        'covered_parent_steps':[parent['parent_step_id'] for parent in prepared['parents']],
        'observed_at':value['confirmed_at'],'clear_window':prepared['clear_window'],
        'human_review_sha':value['human_review_sha'],
        'exclusion_source_sha':prepared['exclusion_source_sha']}
    return body


def publish(service, registry, admitted, guard, *, fault=lambda phase:None):
    """Trusted page execution only; creates no upload/save request."""
    from .own_draft_restore_schema import trusted_initialize
    from .own_draft_restore_context import parent_context
    from .own_replacement_files import folder, exclusive
    from .publication_store import PublicationStore
    policy=service.policy;review=require_admitted(admitted)
    guard();policy.check()
    trusted_initialize(policy,registry,admitted,guard,fault=fault)
    store=PublicationStore(policy,registry)
    outputs=[]
    with store.dispatch_lock():
        guard();policy.check()
        for prepared in review['prepared']['parents']:
            if prepared['binding']['connection'] != policy.data['connection_id']:
                continue
            with _history_transaction(service.workflow.db) as (db, history_locators):
                from .own_draft_restore_metadata import decorate, reject_legacy_for_new_grant
                reject_legacy_for_new_grant(db)
                actual=decorate(parent_context(service,db,prepared['parent_step_id'], history_locators=history_locators))
                if actual != prepared:fail('DRAFT_RESTORE_REVIEW_CHANGED')
                event=source_event(admitted,policy,actual)
                existing=db.execute('SELECT * FROM own_draft_clear_events WHERE id=?',(event['event_id'],)).fetchone()
                if existing is not None:
                    prior=stored(existing['body'],existing['body_digest'])
                    if (prior['source_reference_sha'] != event['source_reference_sha']
                            or prior['binding'] != event['binding']
                            or prior['clear_window'] != event['clear_window']
                            or actual['parent_step_id'] not in prior['covered_parent_steps']):
                        fail('DRAFT_RESTORE_SOURCE_CHANGED')
                    event=prior
                grant_id='restore-grant-'+digest({'event':event['event_id'],
                    'parent':actual['parent_step_id'],'version':actual['version'],
                    'resource':actual['binding']['resource']})
                existing_grant=db.execute('SELECT * FROM own_draft_restore_grants WHERE id=?',(grant_id,)).fetchone()
                if existing_grant is not None:
                    if stored(existing_grant['body'],existing_grant['body_digest']).get('contract_sha') != CONTRACT_SHA:
                        fail('DRAFT_RESTORE_LEGACY_HISTORY_HOLD')
                    outputs.append({'restore_handle':grant_id,'state':'ALREADY_PREPARED'})
                    continue
            now=time.time();expires=min(review['prepared']['expires_at'],review['confirmed_at']+24*3600)
            if not now < expires:fail('DRAFT_RESTORE_AUTHORITY_EXPIRED')
            grant={'schema':1,'policy':POLICY,'contract_sha':CONTRACT_SHA,'grant_id':grant_id,
                'event_id':event['event_id'],'event_sha':digest(event),'clear_window':event['clear_window'],
                'parent_step_id':actual['parent_step_id'],'parent_step_sha':actual['parent_step_sha'],
                'version':actual['version'],'binding':actual['binding'],'context':actual,
                'delegation':policy.delegation(),
                'exclusion_source_sha':review['prepared']['exclusion_source_sha'],
                'published_exclusions':review['prepared']['published_exclusions'],'queue_sha':review['prepared']['queue_sha'],
                'human_review_sha':review['human_review_sha'],'created_at':now,'expires_at':expires}
            target=policy.root/'draft-restore-authority';folder(target,create=True)
            # Qualified settings call first durably seals its exact grant. An
            # interrupted setup may leave an orphan, never a business permission.
            exclusive(target/(grant_id+'.json'),{'schema':1,'origin':'TRUSTED_SETTINGS_ADMISSION',
                'body':grant,'body_sha':digest(grant)})
            fault('restore_authority_file_before_db')
            with _history_transaction(service.workflow.db, write=True) as (db, history_locators):
                guard();policy.check()
                reject_legacy_for_new_grant(db)
                if decorate(parent_context(service,db,actual['parent_step_id'], history_locators=history_locators)) != actual:
                    fail('DRAFT_RESTORE_PARENT_CHANGED')
                b=actual['binding']
                if existing is None:
                    db.execute('INSERT INTO own_draft_clear_events VALUES(?,?,?,?,?,?,?,?)',
                        (event['event_id'],b['tenant'],b['principal'],b['connection'],b['resource'],
                         canonical(event),digest(event),now))
                db.execute('INSERT INTO own_draft_restore_grants VALUES(?,?,?,?,?,?,?,?,?,?,?,?)',
                    (grant_id,event['event_id'],actual['parent_step_id'],actual['version'],
                     b['tenant'],b['principal'],b['connection'],b['resource'],
                     canonical(grant),digest(grant),now,expires))
                guard();policy.check()
            outputs.append({'restore_handle':grant_id,'state':'PREPARED_NOT_SENT'})
    return {'state':'DRAFT_RESTORE_GRANTED','grants':outputs,'new_business_requests':0}


from .draft_group_history_context import history_transaction as _history_transaction
