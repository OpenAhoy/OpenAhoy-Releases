"""Private transport of one already-qualified complete Slot group.

This module never creates a Source or publishes a tool. The host must create
an actual checked session and CompletedSlot under the account lock. Synthetic
session callbacks and fake Source types are tests, not authorization.
"""
import time
from .contracts import WCEError
from .http_transport import HTTPSender
from .publication_contract import digest,fail
from .publication_wire import DraftMediaID,encode
from . import draft_group_wire as draft_wire
from .current_publication_continuation import _ContinuationSession
from .current_publication_service import content_claims
from .service import canonical


def _observe(session,source,row,snapshot,actual):
    """Append the actual GET hashes while retaining the original claim row."""
    import inspect
    frame=inspect.currentframe()
    try:
        if frame.f_back.f_code is not dispatch.__code__:fail('CURRENT_PUBLICATION_SLOT_SOURCE_REQUIRED')
    finally:del frame
    if (type(snapshot) is not draft_wire.GroupSnapshot or snapshot.reference!=row['reference']
            or type(snapshot.response_sha256) is not str or len(snapshot.response_sha256)!=64
            or any(c not in '0123456789abcdef' for c in snapshot.response_sha256)
            or actual != {'reference':snapshot.reference,'projection':draft_wire.baseline_projection(snapshot,synthetic=True)}):
        fail('CURRENT_PUBLICATION_CURRENT_DRAFT_CHANGED')
    source.fence();session._guard('claim' if row['state']=='READY' else 'send',row)
    meta=session.index._meta(session.db,session.identity);seq=meta['seq']+1
    event={'profile':'CURRENT_PUBLICATION_CONTINUATION_FOUNDATION_V1','account':session.index.account,
        'seq':seq,'previous_sha':meta['event_sha'],'kind':'SLOT_GET_OBSERVED',
        'handle':row['intent_handle'],'source_sha':source.sha256,'reference_sha':digest(row['reference']),
        'projection_sha':digest(actual['projection']),'response_sha':snapshot.response_sha256}
    event_sha=digest(event)
    session.db.execute('BEGIN IMMEDIATE')
    try:
        session.db.execute('INSERT INTO events VALUES(?,?,?,?)',(seq,meta['event_sha'],event_sha,canonical(event)))
        session.db.execute('INSERT INTO slot_observations VALUES(?,?,?,?,?,?)',
            (seq,row['intent_handle'],source.sha256,event['reference_sha'],event['projection_sha'],event['response_sha']))
        session.db.execute('UPDATE meta SET seq=?,event_sha=? WHERE id=1',(seq,event_sha))
        source.fence();session._guard('claim' if row['state']=='READY' else 'send',row)
        session.db.execute('COMMIT')
    except BaseException:
        if session.db.in_transaction:session.db.execute('ROLLBACK')
        raise
    session.index._head(session.db,session.identity,recover=True)
    return event_sha


def dispatch(service, session, handle, source, deadline, guard):
    """One draft.get then one submit, with no WCE quota-preflight request."""
    if type(session) is not _ContinuationSession or not callable(guard):
        fail('CURRENT_PUBLICATION_SLOT_SOURCE_REQUIRED')
    session._check_active();row=session.target(handle)
    entry=session.db.execute('SELECT origin FROM target_overlays WHERE handle=?',(handle,)).fetchone()
    if entry is None or entry['origin']!='SLOT':fail('CURRENT_PUBLICATION_SLOT_SOURCE_REQUIRED')
    if row.get('dispatch_protocol') != 'SLOT_DISPATCH_BARRIER_V1':
        fail('CURRENT_PUBLICATION_SLOT_BARRIER_REQUIRED')
    from . import current_publication_slot_barrier as barrier
    reservation=barrier.reservation(session,handle)
    if row.get('state')=='READY' and row.get('submit_count')==0:
        if reservation is not None:fail('CURRENT_PUBLICATION_SLOT_BARRIER_HOLD')
        needs_claim=True
    elif row.get('state')=='SUBMIT_CLAIMED' and row.get('submit_count')==1:
        if reservation is None or reservation['phase'] not in {'RESERVED','UNSENT'}:
            return row
        needs_claim=False
    else:
        return row
    from .slot_source_provider import CompletedSlot
    if type(source) is not CompletedSlot:
        fail('CURRENT_PUBLICATION_SLOT_SOURCE_REQUIRED')
    source.fence()
    value=source.value
    groups=value.get('content',{}).get('groups',[]) if type(value) is dict else []
    matches=[group for group in groups if type(group) is dict and group.get('reference')==row['reference']]
    if (len(matches)!=1 or source.sha256!=row.get('batch_source_sha')
            or type(matches[0].get('members')) is not list
            or len(matches[0]['members']) != row.get('article_count')):
        fail('CURRENT_PUBLICATION_SLOT_SOURCE_REQUIRED')
    slot=session._slot(row.get('slot_key'))
    if (slot is None or handle not in [group['handle'] for group in slot['groups']]
            or slot.get('source_sha') != row.get('batch_source_sha')
            or slot.get('completed_slot_handle') != row.get('completed_slot_handle')
            or source.value.get('handle') != row.get('completed_slot_handle')):
        fail('CURRENT_PUBLICATION_SLOT_SOURCE_REQUIRED')
    logical=value.get('logical') if type(value) is dict else None
    policy=session.index.old.policy.data;identity=slot.get('identity',{})
    if (type(logical) is not dict or logical.get('appid') != policy['appid']
            or logical.get('principal') != policy['actor']['principal_id']
            or logical.get('tenant') != policy['actor']['tenant_id']
            or any(logical.get(k) != identity.get(k) for k in ('producer_role','channel','schedule_id','day','slot'))):
        fail('CURRENT_PUBLICATION_SLOT_SOURCE_REQUIRED')
    # The private provider owns these callbacks and must revalidate the actual
    # Source, original save/GET and complete slot before each boundary.
    session._guard('claim' if needs_claim else 'send',row);guard()
    sender=service.workflow.sender
    if type(sender) is not HTTPSender or not sender.enabled:fail('OWN_HTTP_DISABLED')
    token=service.tokens.get(guard)
    def send(request):
        guard()
        if not service.tokens.valid(token):fail('OWN_TOKEN_UNAVAILABLE')
        timeout=min(30.0,deadline-time.monotonic(),token.wall_deadline-time.time())
        if timeout<=0:fail('CURRENT_PUBLICATION_DEADLINE')
        return sender.send(request,timeout)
    observed=draft_wire.parse_get(send(draft_wire.encode_get(row['reference'],token.token)),token.token,row['reference'])
    guard()
    actual=source.validate_remote_snapshot(observed)
    if (type(actual) is not dict or set(actual)!={'reference','projection'}
            or actual['reference']!=row['reference']):
        fail('CURRENT_PUBLICATION_CURRENT_DRAFT_CHANGED')
    _observe(session,source,row,observed,actual)
    source.fence();session._guard('claim' if needs_claim else 'send',row);guard()
    if needs_claim:session.claim(handle,quota=None)
    try:
        request=encode('freepublish.submit',{'media_id':DraftMediaID(row['reference'],session.index.account,handle)},
                       token.token,account_key=session.index.account,intent_id=handle)
        ticket=session.submit_ticket(handle,request,token.token)
        with barrier.attempt(session,ticket) as attempt:
            barrier.started(attempt)
            try:
                source.fence();session._guard('send',session._row(handle));guard()
                if not service.tokens.valid(token):fail('OWN_TOKEN_UNAVAILABLE')
                timeout=min(30.0,deadline-time.monotonic(),token.wall_deadline-time.time())
                if timeout<=0:fail('CURRENT_PUBLICATION_DEADLINE')
            except Exception:
                # Only this still-live original ticket/stack can attest that
                # sender was never entered; a crash leaves STARTED uncertain.
                barrier.unsent(attempt)
                raise
            barrier.entered(attempt)
            response=sender.send(request,timeout)
            session.stage_submit_reply(ticket,response,token.token)
            return session.adopt_staged_submit(handle)
    except Exception:
        try:
            latest=session.target(handle)
            state=barrier.reservation(session,handle)
            if latest.get('state')=='SUBMIT_CLAIMED' and state is not None and state['phase']=='STARTED':
                receipts=session.db.execute("SELECT 1 FROM return_receipts WHERE handle=? AND method='freepublish.submit'",(handle,)).fetchone()
                if receipts is None:session.mark_submit_unknown(handle)
                raise WCEError('CURRENT_PUBLICATION_UNKNOWN_QUERY_ORIGINAL')
        except WCEError as error:
            if error.code=='CURRENT_PUBLICATION_UNKNOWN_QUERY_ORIGINAL':raise
        raise
