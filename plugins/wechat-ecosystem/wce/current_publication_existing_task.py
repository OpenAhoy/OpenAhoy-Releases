"""Continue an already-submitted publication by original intent only.

Private host path: no caller-selected task, source, new publication grant,
quota preflight, or submit route. Historical status remains a separate read.
"""
from pathlib import Path
import os
import time

from .contracts import WCEError
from .http_transport import HTTPSender
from .publication_contract import binding, fail
from .publication_wire import TaskID, _task, encode
from .current_publication_store import Store, HANDLE, public_target
from .current_publication_continuation import ContinuationIndex


def readonly_head(index, db, identity):
    """Verify a committed, anchor-ahead gap without changing any file."""
    import json
    from .current_publication_continuation import PROFILE, _SCHEMA_NAMES
    from .publication_store import read_file
    from .service import digest
    names={row[0] for row in db.execute("SELECT name FROM sqlite_master WHERE name NOT LIKE 'sqlite_%'")}
    if names!=_SCHEMA_NAMES or db.execute('PRAGMA user_version').fetchone()[0]!=1 or db.execute('PRAGMA application_id').fetchone()[0]!=0x57434543:
        fail('CONTINUATION_HISTORY_HOLD')
    meta=index._meta(db,identity)
    marker={'profile':PROFILE,'account':index.account,'baseline_sha':meta['baseline_sha'],'state':'ACTIVE'}
    if read_file(index.marker_path,16384)!=marker or read_file(index.enrollment_path,16384)!=marker:
        fail('CONTINUATION_HISTORY_HOLD')
    head=read_file(index.head_path,16384)
    expected={'profile':PROFILE,'account':index.account,'identity':list(identity),
              'baseline_sha':meta['baseline_sha'],'seq':meta['seq'],'event_sha':meta['event_sha']}
    if head==expected:
        index._head(db,identity,recover=False)
        return expected,False
    if (type(head) is not dict or set(head)!=set(expected)
            or any(head.get(k)!=expected[k] for k in ('profile','account','identity','baseline_sha'))
            or type(head.get('seq')) is not int or not 1<=meta['seq']-head['seq']<=256):
        fail('CONTINUATION_HISTORY_HOLD')
    previous=head.get('event_sha')
    for sequence in range(head['seq']+1,meta['seq']+1):
        index.old.runtime_guard()
        event=db.execute('SELECT previous_sha,event_sha,event_json FROM events WHERE seq=?',(sequence,)).fetchone()
        if event is None or event['previous_sha']!=previous:
            fail('CONTINUATION_HISTORY_HOLD')
        value=json.loads(event['event_json'])
        if value.get('seq')!=sequence or value.get('previous_sha')!=previous or digest(value)!=event['event_sha']:
            fail('CONTINUATION_HISTORY_HOLD')
        previous=event['event_sha']
    if previous!=meta['event_sha']:
        fail('CONTINUATION_HISTORY_HOLD')
    index.old.runtime_guard()
    if read_file(index.head_path,16384)!=head:
        fail('CONTINUATION_HISTORY_HOLD')
    return expected,True


def _current(policy, guard, expected):
    guard()
    policy.check()
    if (binding(policy.data) != expected or policy.value.get('enabled') is not True
            or 'draft_read' not in policy.value.get('capabilities',())):
        fail('CURRENT_PUBLICATION_READ_PERMISSION_REQUIRED')
    guard()


def _row_check(row, handle, account, scope):
    if (type(handle) is not str or HANDLE.fullmatch(handle) is None
            or type(row) is not dict or row.get('intent_handle') != handle
            or row.get('account_key') != account or row.get('binding_sha256') != scope
            or type(row.get('submit_count')) is not int or row['submit_count'] not in (0,1)):
        fail('CURRENT_PUBLICATION_ORIGINAL_TASK_REQUIRED')
    if row.get('task') is not None:
        try:
            task=TaskID(**row['task']);_task(task,'PUBLISH_TASK',account,handle)
        except Exception:
            fail('CURRENT_PUBLICATION_ORIGINAL_TASK_REQUIRED')
        if row['submit_count'] != 1 or task.source_method != 'freepublish.submit':
            fail('CURRENT_PUBLICATION_ORIGINAL_TASK_REQUIRED')
    return row


def poll(service, registry, handle, deadline, guard):
    """Poll only the persisted original task, under its original account lock."""
    policy=service.policy;scope=binding(policy.data)
    if type(handle) is not str or HANDLE.fullmatch(handle) is None:
        fail('CURRENT_PUBLICATION_INTENT_INVALID')
    store=Store(policy,Path(registry),guard=guard);index=ContinuationIndex(store)
    paths=(index.enrollment_path,index.marker_path,index.db_path,index.head_path)
    present=[os.path.lexists(path) for path in paths]
    if any(present) and not all(present):
        fail('CONTINUATION_HISTORY_HOLD')
    def check():_current(policy,guard,scope)
    check()
    if not any(present):
        # Only a proven original task permits initializing the local
        # continuation. An unknown/READY row cannot create a new grant.
        with store.legacy.dispatch_lock():
            check();value,row=store.target(handle);_row_check(row,handle,index.account,scope)
            if row.get('task') is None:
                if row['state'] not in {'SUBMIT_CLAIMED','UNKNOWN'} or row['submit_count'] != 1:
                    return public_target(row)
                staged=store._staged_submit(value,row,guard,check_conflict=True)
                if staged.get('state')!='ORIGINAL_TASK_STAGED_LOCAL_ONLY':
                    result=public_target(row);result['original_receipt_state']=staged['state']
                    return result
            elif row['state'] not in {'ACCEPTED','PROCESSING','PUBLISHED_URLS_INCOMPLETE'}:
                return public_target(row)
        check();index.bootstrap();check()
        return poll(service,registry,handle,deadline,guard)
    def network(row, claim, make_ticket, record):
        task=TaskID(**row['task']);_task(task,'PUBLISH_TASK',index.account,handle)
        sender=service.workflow.sender
        if type(sender) is not HTTPSender or not sender.enabled:
            fail('OWN_HTTP_DISABLED')
        token=service.tokens.get(guard)
        check()
        if not service.tokens.valid(token):fail('OWN_TOKEN_UNAVAILABLE')
        claim()
        request=encode('freepublish.get',{'task_id':task},token.token,
                       account_key=index.account,intent_id=handle)
        ticket=make_ticket(request,token.token)
        try:
            check()
            if not service.tokens.valid(token):fail('OWN_TOKEN_UNAVAILABLE')
            timeout=min(30.0,deadline-time.monotonic(),token.wall_deadline-time.time())
            if timeout<=0:fail('CURRENT_PUBLICATION_DEADLINE')
            response=sender.send(request,timeout)
            return record(request,response,token.token,ticket)
        except Exception:
            raise WCEError('CURRENT_PUBLICATION_QUERY_UNDETERMINED_ORIGINAL_TASK_ONLY') from None
    if all(present):
        def permit(action,row):
            if action not in {'read','recover','query','query_recover'}:
                return False
            check();_row_check(row,handle,index.account,scope);return True
        def conflicts(action,row):
            if action!='task':return False
            check();_row_check(row,handle,index.account,scope)
            return not store._legacy_task_conflict(TaskID(**row['task']))
        with index.session(permit,conflicts) as session:
            row=_row_check(session.target(handle),handle,index.account,scope)
            if row['state'] in {'SUBMIT_CLAIMED','UNKNOWN'} and row.get('task') is None:
                recovered=session.adopt_staged_submit(handle)
                if recovered.get('state')=='ORIGINAL_RECEIPT_NOT_FOUND':
                    original=store._read_legacy()['targets'].get(handle)
                    if original == row and original.get('state') in {'SUBMIT_CLAIMED','UNKNOWN'}:
                        recovered=session.adopt_old_staged_submit(handle)
                if recovered.get('state') in {'ORIGINAL_RECEIPT_NOT_FOUND','ORIGINAL_RECEIPT_UNDETERMINED'}:
                    return public_target(row)
                row=_row_check(recovered,handle,index.account,scope)
            if row.get('task') is None or row['state'] not in {'ACCEPTED','PROCESSING','PUBLISHED_URLS_INCOMPLETE'}:
                return public_target(row)
            if row.get('query_pending'):
                recovered=session.apply_staged_query(handle)
                if recovered.get('state')!='ORIGINAL_RECEIPT_NOT_FOUND':
                    return public_target(recovered)
                session.mark_query_unknown(handle)
            def claim():session.claim_query(handle)
            def ticket(request,token):return session.query_ticket(handle,request,token)
            def record(request,response,token,ticket):
                session.stage_query_reply(ticket,response,token)
                return session.apply_staged_query(handle)
            try:row=network(row,claim,ticket,record)
            except WCEError:
                latest=session.target(handle)
                if latest.get('query_pending'):
                    receipt=session._query_receipt(handle,latest,latest.get('query_claim_seq'))[0]
                    if receipt is None:session.mark_query_unknown(handle)
                raise
            check();return public_target(row)
