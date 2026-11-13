"""Same-intent local source-review recovery. No network or authority creation.

Only the trusted, qualified publisher calls the private write engine. Ordinary
revision calls keep the journal's exact orphan rejection. Recovery accepts at
most this intent's one proof and one external event, never a missing old file.
"""
from contextlib import contextmanager
from copy import deepcopy
from dataclasses import dataclass,field
from hashlib import sha256
import os,sqlite3
from .contracts import WCEError
from .service import canonical,digest
from .own_connection_policy import locked,atomic_write
from .draft_revision_state import reduce,checksum
from . import draft_revision_files as files

_SEAL=object()


def hold():raise WCEError('DRAFT_REVISION_SOURCE_REVIEW_HOLD')


def _need(value):
    if not value:hold()


def event_data(proof,proof_sha):
    return {'review_id':proof['review_id'],'previous_review_sha':proof['previous_review_sha'],
        'proof_sha':proof_sha,'review_manifest_sha':proof['manifest_sha'],
        'origin_binding_sha':proof['case_sha']}


@dataclass(frozen=True)
class SourceReviewRecoveryFrame:
    case_id:str
    manifest_sha:str
    review_id:str
    proof_json:object=field(repr=False)
    proof_sha:object
    _seal:object=field(repr=False,compare=False)

    def __post_init__(self):
        _need(self._seal is _SEAL and all(checksum(v)
            for v in (self.case_id,self.manifest_sha,self.review_id)))
        _need((self.proof_json is None)==(self.proof_sha is None))

    @property
    def proof_name(self):return f'source-review-{self.case_id}-{self.review_id}.json'

    @property
    def proof(self):
        if self.proof_json is None:return None
        from .publication_contract import strict_json
        return strict_json(self.proof_json.encode(),maximum=2*1024*1024)

    def expected_event(self,store):
        from .draft_revision_store import PROFILE
        proof=self.proof
        _need(proof is not None)
        return {'schema':1,'profile':PROFILE,'binding':store.binding,
            'seq':proof['creation']['journal_seq']+1,
            'previous_sha':proof['creation']['journal_sha'],'case_id':self.case_id,
            'type':'SOURCE_REVIEW','data':event_data(proof,self.proof_sha)}

    def verify_sidecars(self,store,states,head,expected_events,expected_proofs,
                        actual_events,actual_proofs):
        _need(self.case_id in states)
        state=states[self.case_id];proof=self.proof
        _need(not expected_events-actual_events and not expected_proofs-actual_proofs)
        if proof is None:
            _need(actual_events==expected_events and actual_proofs==expected_proofs
                and state.get('source_review') is None)
            return
        from .draft_revision_review_value import validate_review_proof
        validate_review_proof(proof,self.proof_sha,state['case'],state['registration'])
        _need(proof['case_id']==self.case_id and proof['manifest_sha']==self.manifest_sha
            and proof['review_id']==self.review_id)
        current,actual=files.read(store.root/'proofs'/self.proof_name)
        _need(actual==self.proof_sha and current==proof)
        committed=state.get('source_review')
        if committed is not None:
            _need(committed==event_data(proof,self.proof_sha)
                and actual_events==expected_events and actual_proofs==expected_proofs)
            return
        row=state['revision']
        _need(row['state']=='PREPARING' and row['reads']==row['writes']==0
            and state['read_claims']==[] and proof['creation']['journal_seq']==head['seq']
            and proof['creation']['journal_sha']==head['event_sha']
            and actual_proofs==expected_proofs|{self.proof_name})
        event=self.expected_event(store);name=str(event['seq']).zfill(16)+'.json'
        extra=actual_events-expected_events
        _need(extra in (set(),{name}))
        if extra:
            existing,_=files.read(store.root/'events'/name)
            _need(canonical(existing)==canonical(event))


def _frame(store,case_id,manifest_sha):
    from .draft_revision_review_value import review_id
    ident=review_id(case_id,manifest_sha)
    name=f'source-review-{case_id}-{ident}.json';path=store.root/'proofs'/name
    proof=proof_sha=None
    if os.path.lexists(path):
        proof,proof_sha=files.read(path)
        proof=canonical(proof)
    return SourceReviewRecoveryFrame(case_id,manifest_sha,ident,proof,proof_sha,_SEAL)


@contextmanager
def _database(store,*,write):
    from .draft_revision_store import APP_ID,DDL
    store.history_guard();store._pins(store.history_guard)
    db=sqlite3.connect(store.path.as_uri()+('?mode=rw' if write else '?mode=ro'),
        uri=True,timeout=1,isolation_level=None)
    db.row_factory=sqlite3.Row
    try:
        db.execute('PRAGMA trusted_schema=OFF');db.execute('PRAGMA foreign_keys=ON')
        if write:db.execute('PRAGMA synchronous=FULL')
        else:db.execute('PRAGMA query_only=ON')
        actual=tuple(row[0] for row in db.execute(
            "SELECT sql FROM sqlite_master WHERE name NOT LIKE 'sqlite_%' ORDER BY sql"))
        _need(db.execute('PRAGMA application_id').fetchone()[0]==APP_ID
            and db.execute('PRAGMA user_version').fetchone()[0] in (4,5)
            and actual==tuple(sorted(DDL)))
        db.execute('BEGIN IMMEDIATE' if write else 'BEGIN')
        yield db
    except sqlite3.DatabaseError:hold()
    finally:
        try:db.rollback()
        finally:db.close()


def _inspect(store,db,frame):
    from .draft_revision_store import PROFILE
    anchor=store._pins(store.history_guard)
    rows=db.execute('SELECT * FROM meta').fetchall()
    _need(len(rows)==1);meta=dict(rows[0])
    _need(set(meta)=={'id','profile','binding','seq','event_sha'} and meta['id']==1
        and meta['profile']==PROFILE and meta['binding']==store.binding
        and type(meta['seq']) is int and meta['seq']>=1 and checksum(meta['event_sha']))
    same=anchor['seq']==meta['seq'] and anchor['event_sha']==meta['event_sha']
    ahead=(anchor['seq']==meta['seq']+1 and anchor['confirmed_seq']==meta['seq'])
    _need(same or ahead)
    effective=dict(anchor,seq=meta['seq'],event_sha=meta['event_sha'],confirmed_seq=meta['seq'])
    states=store._verify(db,effective,allow_pending=True,pending_review=frame)
    state=states[frame.case_id];committed=state.get('source_review') is not None
    event=None if frame.proof is None else frame.expected_event(store)
    if ahead:
        _need(not committed and event is not None and anchor['event_sha']==digest(event)
            and os.path.lexists(store.root/'events'/(str(event['seq']).zfill(16)+'.json')))
    if committed:
        if anchor['confirmed_seq']==anchor['seq']:
            status='COMMITTED'
        else:
            # This helper never confirms a later business claim/result head.
            _need(event is not None and meta['seq']==event['seq']
                and meta['event_sha']==digest(event))
            status='COMMITTED_UNCONFIRMED'
    elif frame.proof is None:
        _need(same and anchor['confirmed_seq']==anchor['seq'])
        status='NOT_PUBLISHED'
    elif ahead:status='HEAD_AHEAD_NOT_COMMITTED'
    elif event is not None and os.path.lexists(store.root/'events'/(str(event['seq']).zfill(16)+'.json')):
        _need(anchor['confirmed_seq']==anchor['seq'])
        status='EVENT_ONLY_NOT_COMMITTED'
    else:
        _need(anchor['confirmed_seq']==anchor['seq'])
        status='PROOF_ONLY_NOT_PUBLISHED'
    return {'state':status,'review_id':frame.review_id,'manifest_sha':frame.manifest_sha,
        'proof_sha':frame.proof_sha,'storage_version':db.execute('PRAGMA user_version').fetchone()[0],
        'original':deepcopy(state),'anchor':anchor,'sql_head':effective}


def query(store,case_id,manifest_sha):
    """Same fixed intent only. No confirmation, source refresh or write."""
    with locked(store.account/'draft-revision-journal.lock',shared=True,existing=True,
                readonly=True,nonblocking=True):
        frame=_frame(store,case_id,manifest_sha)
        with _database(store,write=False) as db:
            result=_inspect(store,db,frame)
            store.history_guard()
            _need(store._pins(store.history_guard)==result['anchor'])
            return result


def _publish_under_lock(store,proof,proof_sha,fence):
    """Local protocol engine; its caller must qualify the actual host authority.

    A no-op callback is useful only in isolated journal-component tests. There
    is no MCP route to this engine, and the trusted wrapper requires its sealed
    qualifier, exact current Gate, source/artifacts and external review pins.
    """
    from .draft_revision_store import PROFILE
    from .draft_revision_review_value import validate_review_proof
    _need(callable(fence));case_id=proof['case_id'];manifest_sha=proof['manifest_sha']
    with locked(store.account/'draft-revision-journal.lock',nonblocking=True):
        frame=_frame(store,case_id,manifest_sha)
        with _database(store,write=True) as db:
            status=_inspect(store,db,frame);state=status['original'];case=state['case']
            validate_review_proof(proof,proof_sha,case,state['registration'])
            if status['state'].startswith('COMMITTED'):
                _need(frame.proof_sha==proof_sha and frame.proof==proof)
            else:
                row=state['revision']
                _need(row['state']=='PREPARING' and row['reads']==row['writes']==0
                    and state['read_claims']==[] and state.get('source_review') is None
                    and proof['creation']['journal_seq']==status['sql_head']['seq']
                    and proof['creation']['journal_sha']==status['sql_head']['event_sha'])
                _need(fence() is True)
                if status['storage_version']==4:
                    # Only the SQLite format marker changes. Origin V4 hashes,
                    # DDL, rows, external events/proofs and budget stay intact.
                    db.execute('PRAGMA user_version=5');db.commit()
                    store.fault('source_review_migration_after_commit')
                    db.execute('BEGIN IMMEDIATE')
                    again=_inspect(store,db,frame)
                    _need(again['original']==state and again['sql_head']==status['sql_head'])
                if frame.proof is None:
                    actual=files.exclusive(store.root/'proofs'/frame.proof_name,proof)
                    _need(actual==proof_sha)
                    store.fault('source_review_proof_before_event')
                    frame=_frame(store,case_id,manifest_sha)
                else:_need(frame.proof_sha==proof_sha and frame.proof==proof)
                event=frame.expected_event(store);data=event['data'];head=status['sql_head']
                updated=reduce(state,'SOURCE_REVIEW',data)
                store._event_proofs(state,updated,'SOURCE_REVIEW',data,event_head=head)
                db.execute('UPDATE cases SET value=?,value_sha=? WHERE id=?',
                    (canonical(updated),digest(updated),case_id))
                db.execute('INSERT INTO events VALUES(?,?,?)',
                    (event['seq'],canonical(event),digest(event)))
                db.execute('UPDATE meta SET seq=?,event_sha=? WHERE id=1',
                    (event['seq'],digest(event)))
                event_path=store.root/'events'/(str(event['seq']).zfill(16)+'.json')
                if os.path.lexists(event_path):_need(canonical(files.read(event_path)[0])==canonical(event))
                else:files.exclusive(event_path,event)
                store.fault('source_review_event_before_head')
                target=dict(status['anchor'],seq=event['seq'],event_sha=digest(event),
                    confirmed_seq=head['seq'])
                if status['anchor']!=target:atomic_write(store.anchor,target)
                store.fault('source_review_head_before_commit')
                _need(fence() is True)
                db.commit();store.fault('source_review_after_commit')
                db.execute('BEGIN IMMEDIATE')
            current=_inspect(store,db,frame)
            _need(current['state'] in {'COMMITTED','COMMITTED_UNCONFIRMED'})
            if current['state']=='COMMITTED_UNCONFIRMED':
                _need(fence() is True)
                store.fault('source_review_before_confirm')
                atomic_write(store.anchor,dict(current['anchor'],
                    confirmed_seq=current['anchor']['seq']))
            db.commit()
            final=_inspect(store,db,frame)
            _need(final['state']=='COMMITTED')
            return final
