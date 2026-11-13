"""Normal broker adapter for checked CompletedSlot sources.

The public input contains only a connection, opaque source handle or original
intent handle. The adapter constructs the Source and callbacks locally.
"""
import os
from copy import deepcopy
from pathlib import Path
from .contracts import WCEError
from .publication_contract import binding,digest,fail
from .current_publication_store import Store,initialize_anchor,public_target
from .current_publication_continuation import ContinuationIndex,_ContinuationSession
from .current_publication_existing_task import readonly_head
from .slot_source_errors import source_errors


def _registered(policy,registry,guard):
    selected=policy.value.get('registry_path')
    if (type(policy.value.get('schema')) is not int or policy.value['schema']!=2
            or type(selected) is not str or not Path(selected).is_absolute()
            or Path(selected)!=Path(registry)):
        fail('CURRENT_PUBLICATION_SLOT_REGISTRY_REQUIRED')
    guard();policy.check();guard()


def _provider(service,registry,guard,scan_guard=None):
    from .slot_cup_adoption import RuntimeAdoption
    from .slot_source_provider import SourceProvider
    _registered(service.policy,registry,guard);adoption=RuntimeAdoption(service.policy,registry,guard)
    role_sha=adoption.role_sha256
    provider=SourceProvider(service.policy,registry,service.workflow,service.profile(),role_sha,guard,scan_guard=scan_guard)
    adoption.fence();guard()
    return provider,adoption


@source_errors
def discover(service,arguments,registry,guard,*,scan_guard=None):
    _registered(service.policy,registry,guard)
    provider,adoption=_provider(service,registry,guard,scan_guard)
    if arguments.get('cursor') is not None:
        import inspect
        if 'cursor' not in inspect.signature(provider.discover).parameters:
            fail('SLOT_CURSOR_NOT_READY')
    result=provider.discover(cursor=arguments.get('cursor'))
    adoption.fence();guard()
    return result


def _slot_info(policy,registry,handle,guard):
    old=Store(policy,registry,guard=guard);index=ContinuationIndex(old)
    paths=(index.enrollment_path,index.marker_path,index.db_path,index.head_path)
    if not any(os.path.lexists(p) for p in paths):return None
    with index._db(readonly=True) as (db,identity):
        db.execute('BEGIN');head,_=readonly_head(index,db,identity)
        index._check_old_index(db,index._meta(db,identity))
        selected=_ContinuationSession(index,db,identity,None,None)
        try:
            entry=db.execute('SELECT origin FROM target_overlays WHERE handle=?',(handle,)).fetchone()
            if entry is None or entry['origin']!='SLOT':return None
            row=selected._row(handle);slot=selected._slot(row.get('slot_key'))
            if (slot is None or row.get('completed_slot_handle')!=slot.get('completed_slot_handle')
                    or handle not in [g['handle'] for g in slot['groups']]):
                fail('CURRENT_PUBLICATION_SLOT_SOURCE_REQUIRED')
            if readonly_head(index,db,identity)[0]!=head:fail('CONTINUATION_HISTORY_HOLD')
            guard();return row
        finally:selected.active=False


@source_errors
def slot_row(policy,registry,handle,guard):
    return _slot_info(policy,registry,handle,guard)


def _revision_exclusion(policy,source,reference,guard):
    """Negative same-target check under the existing account lock, no grant."""
    from .slot_source_provider import CompletedSlot
    from .draft_revision_guard import policy_binding,guard_claims
    from .draft_revision_store import RevisionStore
    if type(source) is not CompletedSlot or type(reference) is not str or not reference:
        fail('CURRENT_PUBLICATION_SLOT_SOURCE_REQUIRED')
    guard();source.fence();bound=policy_binding(policy,'OPERATOR_ATTESTED')
    claims=[('DRAFT_REF',digest(reference))]
    if policy.value.get('schema')==1:
        guard_claims(policy,bound,claims)
    elif policy.value.get('schema')==2:
        RevisionStore(policy.root,digest(bound),guard).guard_targets_readonly(policy,claims)
    else:fail('CURRENT_PUBLICATION_SLOT_SOURCE_REQUIRED')
    source.fence();guard()


def _callbacks(store,source,adoption,guard):
    from .slot_source_provider import CompletedSlot
    from .current_publication_slot_stage import _legacy_conflicts
    from .publication_wire import TaskID
    if type(source) is not CompletedSlot:fail('CURRENT_PUBLICATION_SLOT_SOURCE_REQUIRED')
    scope=binding(store.policy.data);value=source.value;box={}
    def current():
        guard();adoption.fence();source.fence()
        logical=source.value.get('logical',{})
        data=store.policy.data
        if (binding(data)!=scope or source.value.get('handle')!=value.get('handle')
                or source.sha256!=digest(value)
                or logical.get('appid')!=data['appid'] or logical.get('principal')!=data['actor']['principal_id']
                or logical.get('tenant')!=data['actor']['tenant_id']):
            fail('CURRENT_PUBLICATION_SLOT_SOURCE_REQUIRED')
        guard()
    def checked(action,row):
        current()
        logical=value['logical']
        if action=='freeze_slot':
            expected_identity={'principal_id':logical['principal'],'tenant_id':logical['tenant'],
                **{k:logical[k] for k in ('producer_role','channel','schedule_id','day','slot')}}
            if (row.get('source_sha')!=source.sha256 or row.get('completed_slot_handle')!=value.get('handle')
                    or row.get('identity')!=expected_identity):
                fail('CURRENT_PUBLICATION_SLOT_SOURCE_REQUIRED')
        elif action in {'stage','claim','send'}:
            matches=[g for g in value['content']['groups'] if g.get('reference')==row.get('reference')]
            if (row.get('batch_source_sha')!=source.sha256 or row.get('completed_slot_handle')!=value.get('handle')
                    or row.get('binding_sha256')!=scope
                    or len(matches)!=1 or row.get('expected_projection_sha256')!=matches[0]['expected_projection_sha256']
                    or row.get('article_count')!=len(matches[0]['members'])):
                fail('CURRENT_PUBLICATION_SLOT_SOURCE_REQUIRED')
            if action in {'claim','send'}:
                stored=box['session']._row(row['intent_handle'])
                if action=='claim':
                    from .current_publication_store import MUTABLE_TARGET_FIELDS
                    stable=lambda x:{k:v for k,v in x.items() if k not in MUTABLE_TARGET_FIELDS}
                    if (stable(row)!=stable(stored) or row.get('state')!='READY'
                            or row.get('submit_count')!=0
                            or (stored.get('state'),stored.get('submit_count')) not in {('READY',0),('SUBMIT_CLAIMED',1)}):
                        fail('CURRENT_PUBLICATION_SLOT_SOURCE_REQUIRED')
                elif row!=stored:fail('CURRENT_PUBLICATION_SLOT_SOURCE_REQUIRED')
            _revision_exclusion(store.policy,source,row['reference'],guard)
        elif action not in {'read','recover','query','query_recover'}:
            fail('CURRENT_PUBLICATION_SLOT_SOURCE_REQUIRED')
        current();return True
    def conflicts(action,row):
        current()
        if action in {'stage','claim'}:
            if _legacy_conflicts(box['session'],row['reference'],row.get('content_claims',[])):
                fail('CURRENT_PUBLICATION_LEGACY_CONFLICT')
            _revision_exclusion(store.policy,source,row['reference'],guard)
        elif action=='task':
            task=TaskID(**row['task'])
            if store._legacy_task_conflict(task):fail('CURRENT_PUBLICATION_LEGACY_CONFLICT')
        else:fail('CURRENT_PUBLICATION_SLOT_SOURCE_REQUIRED')
        current();return True
    return checked,conflicts,box


@source_errors
def prepare(service,registry,handle,guard,*,scan_guard=None):
    from .current_publication_slot_stage import stage
    _registered(service.policy,registry,guard)
    provider,adoption=_provider(service,registry,guard,scan_guard);source=provider.completed(handle)
    source.fence();guard();old=Store(service.policy,registry,guard=guard)
    index=ContinuationIndex(old)
    paths=(index.enrollment_path,index.marker_path,index.db_path,index.head_path)
    if not any(os.path.lexists(p) for p in paths):
        initialize_anchor(old.legacy)
        with old.legacy.dispatch_lock():
            guard();old.initialize_locked()
        index.bootstrap()
    checked,conflicts,box=_callbacks(old,source,adoption,guard)
    with index.session(checked,conflicts) as session:
        box['session']=session
        return stage(session,source,guard)


@source_errors
def dispatch(service,registry,row,deadline,guard,*,scan_guard=None):
    from .current_publication_slot_execution import dispatch as send
    _registered(service.policy,registry,guard)
    provider,adoption=_provider(service,registry,guard,scan_guard)
    source=provider.completed(row['completed_slot_handle'])
    if source.sha256!=row['batch_source_sha']:fail('CURRENT_PUBLICATION_SLOT_SOURCE_REQUIRED')
    old=Store(service.policy,registry,guard=guard);index=ContinuationIndex(old)
    checked,conflicts,box=_callbacks(old,source,adoption,guard)
    with index.session(checked,conflicts) as session:
        box['session']=session
        result=send(service,session,row['intent_handle'],source,deadline,guard)
        return public_target(result)
