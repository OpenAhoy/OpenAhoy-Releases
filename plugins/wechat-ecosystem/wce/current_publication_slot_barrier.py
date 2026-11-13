"""Private same-stack barrier for a new Slot's one original submit claim."""
from contextlib import contextmanager
from contextvars import ContextVar
from hashlib import sha256
import inspect,json,os,threading
from .contracts import WCEError
from .service import canonical,digest
from .current_publication_continuation import _SubmitTicket,_TICKET_SEAL

_ACTIVE=ContextVar('wce_slot_attempt',default=None)

def hold():raise WCEError('CURRENT_PUBLICATION_SLOT_BARRIER_HOLD')

def _caller():
    from .current_publication_slot_execution import dispatch
    frame=inspect.currentframe()
    try:
        if frame.f_back.f_back.f_code is not dispatch.__code__:hold()
    finally:del frame

class _Attempt:
    def __init__(self,session,ticket):
        self.session,self.ticket=session,ticket
        self.pid,self.thread=os.getpid(),threading.get_ident()
        self.entered=False;self.started=False

def attempt(session,ticket):
    _caller()
    if (type(ticket) is not _SubmitTicket or ticket.seal is not _TICKET_SEAL
            or ticket.session is not session or ticket.pid!=os.getpid()
            or ticket.thread!=threading.get_ident() or _ACTIVE.get() is not None):hold()
    @contextmanager
    def held():
        value=_Attempt(session,ticket);token=_ACTIVE.set(value)
        try:yield value
        finally:_ACTIVE.reset(token)
    return held()


def reservation(session,handle):
    session._check_active();row=session._row(handle)
    entry=session.db.execute('SELECT * FROM slot_dispatch_state WHERE handle=?',(handle,)).fetchone()
    if entry is None:return None
    claim=session.db.execute('SELECT event_json,event_sha FROM events WHERE seq=?',(entry['claim_seq'],)).fetchone()
    version=session.db.execute('SELECT row_json,row_sha FROM intent_versions WHERE handle=? AND event_seq=?',(handle,entry['claim_seq'])).fetchone()
    if claim is None or version is None:hold()
    event=json.loads(claim['event_json']);original=json.loads(version['row_json'])
    raw=json.dumps({'media_id':row['reference']},sort_keys=True,separators=(',',':'),ensure_ascii=True).encode('ascii')
    if (digest(event)!=claim['event_sha'] or claim['event_sha']!=entry['claim_sha']
            or event.get('kind')!='SUBMIT_CLAIM' or event.get('handle')!=handle
            or event.get('row_sha')!=version['row_sha'] or digest(original)!=version['row_sha']
            or original.get('dispatch_protocol')!='SLOT_DISPATCH_BARRIER_V1'
            or original.get('batch_source_sha')!=entry['source_sha']
            or row.get('batch_source_sha')!=entry['source_sha']
            or sha256(raw).hexdigest()!=entry['body_sha'] or entry['phase'] not in {'RESERVED','STARTED','UNSENT'}):hold()
    if entry['phase']=='RESERVED':
        if entry['phase_seq']!=entry['claim_seq']:hold()
    else:
        phase=session.db.execute('SELECT event_json,event_sha FROM events WHERE seq=?',(entry['phase_seq'],)).fetchone()
        if phase is None:hold()
        event=json.loads(phase['event_json'])
        if (digest(event)!=phase['event_sha'] or event.get('kind')!='SLOT_DISPATCH_'+entry['phase']
                or event.get('handle')!=handle or event.get('claim_sha')!=entry['claim_sha']
                or event.get('body_sha')!=entry['body_sha'] or event.get('source_sha')!=entry['source_sha']):hold()
    return dict(entry)


def _append(value, phase):
    session,ticket=value.session,value.ticket
    session._check_active()
    if (_ACTIVE.get() is not value or value.pid!=os.getpid() or value.thread!=threading.get_ident()
            or value.entered or phase not in {'STARTED','UNSENT'}):hold()
    entry=reservation(session,ticket.handle)
    if (entry is None or entry['claim_seq']!=ticket.claim_seq or entry['claim_sha']!=ticket.claim_sha
            or entry['body_sha']!=sha256(ticket.request.body).hexdigest()
            or (phase=='STARTED' and entry['phase'] not in {'RESERVED','UNSENT'})
            or (phase=='UNSENT' and (entry['phase']!='STARTED' or not value.started))):hold()
    row=session._row(ticket.handle)
    def local_proof():
        from .own_bootstrap_security import path_check
        from .current_publication_continuation import _owned_file
        session._check_active();path_check(session.index.old.legacy.anchor,True)
        if _owned_file(session.index.db_path)!=session.identity:hold()
        session.index._meta(session.db,session.identity)
    if phase=='STARTED':session._guard('send',row)
    else:local_proof()
    meta=session.index._meta(session.db,session.identity);seq=meta['seq']+1
    event={'profile':'CURRENT_PUBLICATION_CONTINUATION_FOUNDATION_V1','account':session.index.account,
        'seq':seq,'previous_sha':meta['event_sha'],'kind':'SLOT_DISPATCH_'+phase,
        'handle':ticket.handle,'claim_sha':ticket.claim_sha,'body_sha':entry['body_sha'],
        'source_sha':entry['source_sha']}
    event_sha=digest(event)
    session.db.execute('BEGIN IMMEDIATE')
    try:
        session.db.execute('INSERT INTO events VALUES(?,?,?,?)',(seq,meta['event_sha'],event_sha,canonical(event)))
        changed=session.db.execute('UPDATE slot_dispatch_state SET phase=?,phase_seq=? WHERE handle=? AND phase=? AND phase_seq=?',
                 (phase,seq,ticket.handle,entry['phase'],entry['phase_seq'])).rowcount
        if changed!=1:hold()
        session.db.execute('UPDATE meta SET seq=?,event_sha=? WHERE id=1',(seq,event_sha))
        if phase=='STARTED':session._guard('send',row)
        else:local_proof()
        session.db.execute('COMMIT')
    except BaseException:
        if session.db.in_transaction:session.db.execute('ROLLBACK')
        raise
    session.index._head(session.db,session.identity,recover=True)
    if phase=='STARTED':value.started=True
    return reservation(session,ticket.handle)


def started(value):
    _caller();return _append(value,'STARTED')


def unsent(value):
    _caller();return _append(value,'UNSENT')


def entered(value):
    _caller()
    if (_ACTIVE.get() is not value or value.entered or not value.started
            or value.pid!=os.getpid() or value.thread!=threading.get_ident()):hold()
    value.entered=True
