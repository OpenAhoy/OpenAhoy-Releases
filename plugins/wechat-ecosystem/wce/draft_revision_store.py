"""Account-private revision journal with SQL/immutable-file agreement.

This component confers no authority and never calls a network/provider. A trusted
service must hold the existing account dispatch/policy locks and validate Case,
source, images and current credentials. The local lock serializes journal-only
updates. Both local domains rolled back together are not detectable here.
"""
from contextlib import closing, contextmanager
from copy import deepcopy
from dataclasses import dataclass, field
from hashlib import sha256
from pathlib import Path
import os
import sqlite3
import stat

from .contracts import WCEError
from .service import canonical, digest
from . import draft_revision_files as files
from .own_connection_policy import atomic_write, locked
from .draft_revision_state import reduce, checksum as _hash, claim_review, ZERO

APP_ID = 0x57435256
PROFILE = 'EXACT_DRAFT_REVISION_JOURNAL_V4'
LIMIT = 2*1024*1024
KINDS = frozenset({'DRAFT_REF','SAVE_STEP','LINEAGE','MANIFEST','CONTENT','PRODUCER_ARTIFACT'})
DDL = (
    "CREATE TABLE meta(id INTEGER PRIMARY KEY CHECK(id=1), profile TEXT NOT NULL, binding TEXT NOT NULL, seq INTEGER NOT NULL CHECK(seq>=0), event_sha TEXT NOT NULL)",
    "CREATE TABLE cases(id TEXT PRIMARY KEY, source_key TEXT NOT NULL UNIQUE, original_step TEXT NOT NULL UNIQUE, target TEXT NOT NULL UNIQUE, value TEXT NOT NULL, value_sha TEXT NOT NULL)",
    "CREATE TABLE targets(case_id TEXT NOT NULL REFERENCES cases(id), kind TEXT NOT NULL, fingerprint TEXT NOT NULL, PRIMARY KEY(case_id,kind,fingerprint))",
    "CREATE INDEX target_lookup ON targets(kind,fingerprint)",
    "CREATE TABLE events(seq INTEGER PRIMARY KEY, value TEXT NOT NULL, value_sha TEXT NOT NULL)",
    "CREATE TRIGGER immutable_events_update BEFORE UPDATE ON events BEGIN SELECT RAISE(ABORT,'immutable'); END",
    "CREATE TRIGGER immutable_events_delete BEFORE DELETE ON events BEGIN SELECT RAISE(ABORT,'immutable'); END",
)
CASE_FIELDS = frozenset({'profile','id','source_key','binding','target','original_step',
    'source_sha','registration_proof_sha','input_sha','targets','maximum_reads','maximum_updates','provider_profile','target_basis'})
SYNTHETIC_PROVIDER='SYNTHETIC_REVISION_V1'
OFFICIAL_PROVIDER='OFFICIAL_OWN_NEWS_REVISION_V1'
_INFER_REVIEW=object()


def hold(code='DRAFT_REVISION_JOURNAL_HOLD'):
    raise WCEError(code)


def _decode(raw):
    from .publication_contract import strict_json
    return strict_json(raw,maximum=LIMIT)


def _encode(value):
    raw=(canonical(value)+'\n').encode()
    if len(raw)>LIMIT:hold('DRAFT_REVISION_PROOF_BOUND')
    return raw


def _sync(directory):
    from .bounded_file import FileSource
    source=FileSource(directory);fds=[];chain=[]
    try:
        fd=source._root(fds,chain);os.fsync(fd);source._check_chain(chain)
    finally:source._close(fds)


def case_value(value,binding):
    if (type(value) is not dict or set(value)!=CASE_FIELDS or value['profile']!=PROFILE
            or value['binding']!=binding or type(value['maximum_reads']) is not int
            or value['maximum_reads']!=5 or type(value['maximum_updates']) is not int
            or value['maximum_updates']!=1
            or value['provider_profile'] not in {SYNTHETIC_PROVIDER,OFFICIAL_PROVIDER}):hold('DRAFT_REVISION_CASE_INVALID')
    for key in CASE_FIELDS-{'profile','targets','maximum_reads','maximum_updates','provider_profile','target_basis'}:
        if not _hash(value[key]):hold('DRAFT_REVISION_CASE_INVALID')
    targets=value['targets']
    if type(targets) is not list or not 1<=len(targets)<=64:hold('DRAFT_REVISION_CASE_INVALID')
    seen=set()
    for row in targets:
        if (type(row) is not dict or set(row)!={'kind','fingerprint'} or row['kind'] not in KINDS
                or not _hash(row['fingerprint']) or (row['kind'],row['fingerprint']) in seen):hold('DRAFT_REVISION_CASE_INVALID')
        seen.add((row['kind'],row['fingerprint']))
    if targets!=required_targets(value):hold('DRAFT_REVISION_COMPLETE_TARGETS_REQUIRED')
    key=digest({'profile':PROFILE,'binding':binding,'original_step':value['original_step'],'source_sha':value['source_sha']})
    case_id=digest({'profile':PROFILE,'source_key':key,'input_sha':value['input_sha'],
        'registration_proof_sha':value['registration_proof_sha'],'provider_profile':value['provider_profile'],
        'target_basis_sha':digest(value['target_basis'])})
    if value['source_key']!=key or value['id']!=case_id:hold('DRAFT_REVISION_CASE_SELECTOR_INVALID')
    return deepcopy(value)


def required_targets(value):
    basis=value.get('target_basis')
    limits={'MANIFEST':(2,2),'CONTENT':(1,16),'LINEAGE':(1,1),'PRODUCER_ARTIFACT':(2,8)}
    if type(basis) is not dict or set(basis)!=set(limits):hold('DRAFT_REVISION_TARGET_BASIS_REQUIRED')
    result=[{'kind':'DRAFT_REF','fingerprint':value['target']},
        {'kind':'SAVE_STEP','fingerprint':value['original_step']}]
    for kind in sorted(limits):
        items=basis[kind];low,high=limits[kind]
        if (type(items) is not list or not low<=len(items)<=high or any(not _hash(x) for x in items)
                or items!=sorted(set(items))):hold('DRAFT_REVISION_TARGET_BASIS_REQUIRED')
        result += [{'kind':kind,'fingerprint':fp} for fp in items]
    return result


@dataclass(frozen=True)
class Admission:
    case_id:str
    revision_id:str
    kind:str
    ordinal:int
    proof_sha:str
    _nonce:object=field(repr=False,compare=False)
    source_review:object=field(default=None,repr=False,compare=False)


class RevisionStore:
    def __init__(self,account_root,binding,guard,*,history_guard=None,fault=lambda phase:None):
        if not _hash(binding) or not callable(guard) or not callable(fault):hold()
        if history_guard is not None and not callable(history_guard):hold()
        self.account=Path(account_root);self.root=self.account/'draft-revisions'
        self.path=self.root/'revision.sqlite3';self.anchor=self.account/'draft-revision-safety-anchor.json'
        self.binding,self.guard,self.fault=binding,guard,fault
        self.history_guard=guard if history_guard is None else history_guard
        self._admission=None;self._inflight={}
        self.review_observer=None

    def initialize(self):
        """Reviewed maintenance only; no registered Case means no permission."""
        self.guard();files.folder(self.account)
        if os.path.lexists(self.anchor) or os.path.lexists(self.root):
            with self.connection():pass
            return
        files.folder(self.root,create=True)
        for name in ('proofs','events'):files.folder(self.root/name,create=True)
        fd=os.open(self.path,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o600);os.close(fd)
        with closing(sqlite3.connect(self.path)) as db:
            db.execute('PRAGMA journal_mode=DELETE');db.execute('PRAGMA synchronous=FULL')
            db.execute('PRAGMA application_id='+str(APP_ID));db.execute('PRAGMA user_version=4')
            for statement in DDL:db.execute(statement)
            db.execute('INSERT INTO meta VALUES(1,?,?,0,?)',(PROFILE,self.binding,ZERO));db.commit()
        with self.path.open('rb') as stream:os.fsync(stream.fileno())
        _sync(self.root)
        pin=self.path.lstat()
        files.exclusive(self.anchor,{'schema':1,'profile':PROFILE,'binding':self.binding,
            'root':list(files.folder(self.root)),'database':[pin.st_dev,pin.st_ino],
            'sql_sha':digest(sorted(DDL)),'seq':0,'event_sha':ZERO,'confirmed_seq':0})
        self.guard()
        with self.connection():pass

    def _head(self,guard=None):
        (self.guard if guard is None else guard)();files.folder(self.account)
        anchor,_=files.read(self.anchor,16384)
        info=self.path.lstat()
        fixed={'schema':1,'profile':PROFILE,'binding':self.binding,
            'root':list(files.folder(self.root)),'database':[info.st_dev,info.st_ino],
            'sql_sha':digest(sorted(DDL))}
        if (type(anchor) is not dict or set(anchor)!=set(fixed)|{'seq','event_sha','confirmed_seq'}
                or any(type(anchor[k]) is not list or len(anchor[k])!=2
                    or any(type(v) is not int or v<0 for v in anchor[k]) for k in ('root','database'))
                or any(canonical(anchor[k])!=canonical(v) for k,v in fixed.items() if k not in {'root','database'}) or type(anchor['seq']) is not int
                or anchor['seq']<0 or type(anchor['confirmed_seq']) is not int
                or anchor['confirmed_seq'] not in {anchor['seq'],anchor['seq']-1}
                or not _hash(anchor['event_sha']) or not stat.S_ISREG(info.st_mode)
                or info.st_uid!=os.getuid() or info.st_nlink!=1
                or stat.S_IMODE(info.st_mode)!=0o600 or not 0<info.st_size<=1024*1024*1024):hold()
        if any(os.path.lexists(str(self.path)+suffix) for suffix in ('-wal','-shm','-journal')):
            hold('DRAFT_REVISION_SIDECAR_HOLD')
        for name in ('proofs','events'):files.folder(self.root/name)
        return anchor,fixed

    def _pins(self,guard=None,*,_readonly_frame=None,_readonly_db=None):
        anchor,fixed=self._head(guard)
        if any(canonical(anchor[k])!=canonical(fixed[k]) for k in ('root','database')):
            from .own_revision_history import checked
            if _readonly_frame is None:hold()
            checked(_readonly_frame,self.account,_readonly_db).anchor(
                self.account,_readonly_db,anchor,self.binding)
        else:
            from .own_revision_relocation import verify_current_head
            verify_current_head(self.account,self.binding,anchor,
                reestablish_durability=(_readonly_frame is None))
        return anchor

    @contextmanager
    def _readonly_connection(self,policy):
        """Internal ordinary-target/inventory read only; all write paths stay strict."""
        from .own_connection_policy import ConnectionPolicy
        from .draft_revision_guard import identity_binding
        from .own_history_source import owned_connection
        from .own_revision_history import revision_read_scope
        if (type(policy) is not ConnectionPolicy or policy.root!=self.account
                or digest(identity_binding(policy.data,'OPERATOR_ATTESTED'))!=self.binding):hold()
        with locked(self.account/'draft-revision-journal.lock',shared=True,
                    existing=True,readonly=True,nonblocking=True):
            self.guard();policy.check(readonly=True)
            self._head()  # All nonphysical and safe-path conditions precede SQLite.
            with owned_connection(self.path,readonly=True,timeout=1,isolation_level=None,_revision_header=True) as db:
                db.row_factory=sqlite3.Row
                with revision_read_scope(policy,db) as frame:
                    head=self._pins(_readonly_frame=frame,_readonly_db=db)
                    try:
                        db.execute('PRAGMA trusted_schema=OFF');db.execute('PRAGMA foreign_keys=ON')
                        db.execute('PRAGMA query_only=ON')
                        actual=tuple(row[0] for row in db.execute(
                            "SELECT sql FROM sqlite_master WHERE name NOT LIKE 'sqlite_%' ORDER BY sql"))
                        if (db.execute('PRAGMA application_id').fetchone()[0]!=APP_ID
                                or db.execute('PRAGMA user_version').fetchone()[0] not in (4,5)
                                or actual!=tuple(sorted(DDL))):hold()
                        db.execute('BEGIN')
                        self._verify(db,head)
                        yield db,head
                        self.guard();policy.check(readonly=True)
                        if self._pins(_readonly_frame=frame,_readonly_db=db)!=head:hold()
                        db.rollback()
                    except BaseException as error:
                        try:db.rollback()
                        except sqlite3.Error:pass
                        if isinstance(error,sqlite3.DatabaseError):hold('DRAFT_REVISION_DATABASE_HOLD')
                        raise

    @contextmanager
    def connection(self,*,write=False,allow_pending=False,guard=None,orphan_response=None):
        # No long-lived SQL transaction spans network or token access.
        with locked(self.account/'draft-revision-journal.lock',nonblocking=True):
            check=self.guard if guard is None else guard
            head=self._pins(check)
            db=sqlite3.connect(self.path.as_uri()+('?mode=rw' if write else '?mode=ro'),uri=True,
                timeout=1,isolation_level=None)
            db.row_factory=sqlite3.Row
            try:
                db.execute('PRAGMA trusted_schema=OFF');db.execute('PRAGMA foreign_keys=ON')
                if not write:db.execute('PRAGMA query_only=ON')
                else:db.execute('PRAGMA synchronous=FULL')
                actual=tuple(row[0] for row in db.execute("SELECT sql FROM sqlite_master WHERE name NOT LIKE 'sqlite_%' ORDER BY sql"))
                if (db.execute('PRAGMA application_id').fetchone()[0]!=APP_ID
                        or db.execute('PRAGMA user_version').fetchone()[0] not in (4,5)
                        or actual!=tuple(sorted(DDL))):hold()
                db.execute('BEGIN IMMEDIATE' if write else 'BEGIN')
                self._verify(db,head,allow_pending=allow_pending,orphan_response=orphan_response)
                yield db
                if write:self.fault('before_commit')
                check()
                if write:
                    db.commit();self.fault('after_commit')
                    pending=self._pins(check)
                    self._verify(db,pending,allow_pending=True)
                    if pending['confirmed_seq']!=pending['seq']:
                        self.fault('before_confirm')
                        atomic_write(self.anchor,dict(pending,confirmed_seq=pending['seq']))
                    self._verify(db,self._pins(check))
                else:db.rollback()
            except BaseException as error:
                try:db.rollback()
                except sqlite3.Error:pass
                if isinstance(error,sqlite3.DatabaseError):hold('DRAFT_REVISION_DATABASE_HOLD')
                raise
            finally:db.close()

    def _proof(self,name,value,case,*,source_review=None):
        proof={'schema':1 if source_review is None else 2,'profile':PROFILE,'binding':self.binding,
            'case_id':case['id'],'case_sha':digest(case),'target':case['target'],
            'revision_id':digest({'case':case['id'],'profile':PROFILE}),**value}
        if source_review is not None:proof['source_review']=claim_review(source_review)
        if os.path.lexists(self.root/'proofs'/name):hold('DRAFT_REVISION_PROOF_CONFLICT')
        checksum=files.exclusive(self.root/'proofs'/name,proof)
        self.fault('proof_before_event')
        return checksum

    def _load_proof(self,name,checksum,case,*,source_review=_INFER_REVIEW):
        value,actual=files.read(self.root/'proofs'/name,LIMIT)
        if actual!=checksum:hold('DRAFT_REVISION_PROOF_CHANGED')
        schema=value.get('schema') if type(value) is dict else None
        if type(schema) is not int or schema not in (1,2):hold()
        identity={'schema':schema,'profile':PROFILE,'binding':self.binding,
            'case_id':case['id'],'case_sha':digest(case),'target':case['target'],
            'revision_id':digest({'case':case['id'],'profile':PROFILE})}
        if type(value) is not dict or any(value.get(k)!=v for k,v in identity.items()):hold()
        if schema==2:
            if set(value)!=set(identity)|{'data','source_review'}:hold()
            claim_review(value['source_review'])
        if source_review is not _INFER_REVIEW:
            if source_review is None:
                if schema!=1:hold()
            elif schema!=2 or value['source_review']!=claim_review(source_review):hold()
        return value

    def _verify(self,db,head,*,allow_pending=False,orphan_response=None,pending_review=None):
        if pending_review is not None:
            from .draft_revision_review_store import SourceReviewRecoveryFrame
            if type(pending_review) is not SourceReviewRecoveryFrame or orphan_response is not None:hold()
        if not allow_pending and head['confirmed_seq']!=head['seq']:hold('DRAFT_REVISION_HEAD_PENDING')
        meta=db.execute('SELECT * FROM meta').fetchall()
        if len(meta)!=1 or dict(meta[0])!={'id':1,'profile':PROFILE,'binding':self.binding,
                'seq':head['seq'],'event_sha':head['event_sha']}:hold('DRAFT_REVISION_HEAD_HOLD')
        states={};previous=ZERO;proof_names=set();seq=0
        events=db.execute('SELECT * FROM events ORDER BY seq')
        for row in events:
            seq+=1
            event=_decode(row['value'].encode())
            if (row['seq']!=seq or row['value']!=canonical(event) or digest(event)!=row['value_sha']
                    or set(event)!={'schema','profile','binding','seq','previous_sha','case_id','type','data'}
                    or event['schema']!=1 or event['profile']!=PROFILE or event['binding']!=self.binding
                    or event['seq']!=seq or event['previous_sha']!=previous or not _hash(event['case_id'])):hold()
            external,_=files.read(self.root/'events'/(str(seq).zfill(16)+'.json'),LIMIT)
            if canonical(external)!=canonical(event):hold('DRAFT_REVISION_EVENT_CHANGED')
            case_id=event['case_id'];old=states.get(case_id)
            if event['type']=='SOURCE_REVIEW' and db.execute('PRAGMA user_version').fetchone()[0]!=5:hold()
            new=reduce(old,event['type'],event['data'])
            case=case_value(new['case'],self.binding)
            if case['id']!=case_id:hold()
            names=self._event_proofs(old,new,event['type'],event['data'],
                event_head={'seq':seq-1,'event_sha':previous})
            proof_names.update(names)
            states[case_id]=new;previous=row['value_sha']
        if seq!=head['seq'] or previous!=head['event_sha']:hold()
        expected_events={str(i).zfill(16)+'.json' for i in range(1,seq+1)}
        actual_events={p.name for p in (self.root/'events').iterdir()}
        actual_proofs={p.name for p in (self.root/'proofs').iterdir()}
        if pending_review is not None:
            pending_review.verify_sidecars(self,states,head,expected_events,proof_names,
                actual_events,actual_proofs)
        elif actual_events!=expected_events:hold('DRAFT_REVISION_ORPHAN_EVENT')
        elif actual_proofs!=proof_names:
            if (not _hash(orphan_response) or orphan_response not in states
                    or actual_proofs-proof_names!={f'response-{orphan_response}.json'}
                    or proof_names-actual_proofs):hold('DRAFT_REVISION_ORPHAN_PROOF')
            # One fixed original response file can be reconciled under the
            # original claim only. No read/update claim or event gap is waived.
            current=states[orphan_response]
            data=self._response_archive_data(current)
            self._event_proofs(current,reduce(current,'UPDATE_RESPONSE',data),'UPDATE_RESPONSE',data)
        actual_cases={row['id']:dict(row) for row in db.execute('SELECT * FROM cases')}
        expected_cases={key:{'id':key,'source_key':value['case']['source_key'],'original_step':value['case']['original_step'],'target':value['case']['target'],
            'value':canonical(value),'value_sha':digest(value)} for key,value in states.items()}
        if actual_cases!=expected_cases:hold('DRAFT_REVISION_CASE_PROJECTION_HOLD')
        expected_targets={(key,row['kind'],row['fingerprint']) for key,value in states.items() for row in value['case']['targets']}
        if {tuple(row) for row in db.execute('SELECT * FROM targets')}!=expected_targets:hold('DRAFT_REVISION_TARGET_PROJECTION_HOLD')
        return states

    def _response_archive_data(self,current):
        case_id=current['case']['id']
        proof,checksum=files.read(self.root/'proofs'/f'response-{case_id}.json',LIMIT)
        payload=proof.get('data') if type(proof) is dict else None
        if type(payload) is not dict or set(payload)!={'kind','http_status','claim_sha','request_sha',
                'response_state','errcode','response_raw_sha','transport'}:hold()
        data={key:payload[key] for key in ('response_state','errcode','response_raw_sha')}
        return dict(data,proof_sha=checksum)

    def _event_proofs(self,old,new,kind,data,*,event_head=None):
        """Validate every immutable proof, not just the current database row."""
        case=new['case'];case_id=case['id'];names=[]
        if kind=='REGISTER':
            if case['provider_profile']==OFFICIAL_PROVIDER:
                from .draft_revision_registration import validate_record
                validate_record(data['registration'],case)
            elif data['registration'] is not None:hold()
            return names
        if kind=='ADOPT_PENDING_BASELINE':
            from .draft_revision_pending_adoption import source as adoption_source
            witness=data['witness']
            anchor={'sequence':witness['source_head_sequence'],'sha256':witness['source_head_sha256']}
            if adoption_source(self,case,new['registration'],self.history_guard,anchor=anchor)!=witness:
                hold('DRAFT_REVISION_PENDING_ADOPTION_HOLD')
            return names
        if kind=='SOURCE_REVIEW':
            from .draft_revision_review_value import validate_review_proof
            name=f"source-review-{case_id}-{data['review_id']}.json"
            proof,actual=files.read(self.root/'proofs'/name,LIMIT)
            if actual!=data['proof_sha']:hold('DRAFT_REVISION_PROOF_CHANGED')
            validate_review_proof(proof,actual,case,new['registration'])
            if (proof['review_id']!=data['review_id']
                    or proof['previous_review_sha']!=data['previous_review_sha']
                    or proof['manifest_sha']!=data['review_manifest_sha']
                    or proof['case_sha']!=data['origin_binding_sha']
                    or type(event_head) is not dict
                    or proof['creation']['journal_seq']!=event_head['seq']
                    or proof['creation']['journal_sha']!=event_head['event_sha']):hold()
        elif kind=='READ_CLAIM':
            name=f"read-{case_id}-{data['ordinal']}.json"
            proof=self._load_proof(name,data['proof_sha'],case,
                source_review=data.get('source_review'))
            if proof.get('data')!={'kind':'GET_CLAIM','ordinal':data['ordinal'],'phase':data['phase']}:hold()
        elif kind=='READ_RESULT':
            ordinal=data['ordinal'];name=f'result-{case_id}-{ordinal}.json'
            proof=self._load_proof(name,data['proof_sha'],case,
                source_review=old['read_claims'][ordinal-1].get('source_review'))
            expected={'kind':'GET_RESULT','ordinal':ordinal,'claim_sha':old['read_claims'][ordinal-1]['claim_sha'],
                'status':data['status'],'snapshot':proof.get('data',{}).get('snapshot'),
                'transport':proof.get('data',{}).get('transport')}
            if proof.get('data')!=expected:hold()
            snapshot=self._snapshot(proof)
            if (snapshot.evidence_sha() if snapshot else None)!=data['snapshot_sha']:hold()
            from .draft_revision_transport import validate as validate_transport
            validate_transport(expected['transport'],case['provider_profile'],
                body_sha=None if snapshot is None else snapshot.response_sha,
                request_sha=None if snapshot is None else digest({'media_id':snapshot.reference}))
        elif kind=='PREPARED':
            name=f'prepared-{case_id}.json';proof=self._load_proof(name,data['proof_sha'],case,
                source_review=old['read_claims'][data['ordinal']-1].get('source_review'))
            payload=proof.get('data',{})
            if (set(payload)!={'kind','ordinal','baseline','expected'} or payload['kind']!='PREPARED'
                    or payload['ordinal']!=data['ordinal'] or digest(payload['baseline'])!=data['baseline_sha']
                    or digest(payload['expected'])!=data['expected_sha']):hold()
            snapshot=self._read_snapshot(old,data['ordinal'])
            from .draft_revision_wire import baseline_projection
            if baseline_projection(snapshot)!=payload['baseline']:hold('DRAFT_REVISION_BASELINE_HOLD')
        elif kind=='UPDATE_CLAIM':
            name=f'claim-{case_id}.json';proof=self._load_proof(name,data['proof_sha'],case,
                source_review=data.get('source_review'))
            if proof.get('data')!={'kind':'UPDATE_CLAIM','ordinal':data['ordinal'],
                    'baseline_sha':old['revision']['baseline_sha'],'expected_sha':old['revision']['expected_sha'],
                    'preparation_sha':old['revision']['preparation_sha'],'request_sha':data['request_sha']}:hold()
            from .draft_revision_wire import baseline_projection
            if digest(baseline_projection(self._read_snapshot(old,data['ordinal'])))!=old['revision']['baseline_sha']:hold('DRAFT_REVISION_BASELINE_CHANGED')
        elif kind=='UPDATE_RESPONSE':
            name=f'response-{case_id}.json';proof=self._load_proof(name,data['proof_sha'],case,
                source_review=old['revision'].get('claim_source_review'))
            payload=proof.get('data')
            if payload!={'kind':'ORIGINAL_UPDATE_RESPONSE_ARCHIVE','claim_sha':old['revision']['claim_sha'],
                    'request_sha':old['revision']['request_sha'],
                    'http_status':payload.get('http_status') if type(payload) is dict else None,
                    'transport':payload.get('transport') if type(payload) is dict else None,
                    **{key:data[key] for key in ('response_state','errcode','response_raw_sha')}}:hold()
            from .draft_revision_transport import validate as validate_transport
            validate_transport(payload['transport'],case['provider_profile'],body_sha=data['response_raw_sha'],
                request_sha=old['revision']['request_sha'])
            status=payload['http_status']
            if data['response_state']=='RESULT_UNKNOWN':
                if status is not None:hold()
            elif type(status) is not int or not 200<=status<300:hold()
        elif kind=='READ_EFFECT':
            from .draft_revision_wire import baseline_projection
            from .draft_revision_preservation import effect_matches
            snapshot=self._read_snapshot(old,data['ordinal'])
            prepared=self._load_proof(f'prepared-{case_id}.json',old['revision']['preparation_sha'],case)
            matched=effect_matches(baseline_projection(snapshot),prepared['data']['expected'])
            if data['matched']!=matched:hold()
            return names
        else:hold()
        names.append(name)
        return names

    def _snapshot(self,proof):
        from .draft_revision_wire import RevisionSnapshot, PROFILE as WIRE_PROFILE, baseline_projection
        raw=proof['data']['snapshot']
        if raw is None:return None
        if (type(raw) is not dict or set(raw)!={'reference','canonical_json','response_sha','profile'}
                or raw['profile']!=WIRE_PROFILE or not _hash(raw['response_sha'])):hold()
        snapshot=RevisionSnapshot(**raw)
        # Full presence-aware codec validation was performed by the trusted
        # service on the real response. Reopening verifies bounded canonical
        # data and exact target; it never fabricates an HTTP receipt.
        if digest(snapshot.reference)!=proof['target']:hold('DRAFT_REVISION_TARGET_CHANGED')
        baseline_projection(snapshot)
        return snapshot

    def _read_snapshot(self,state,ordinal):
        if type(ordinal) is not int or not 1<=ordinal<=len(state['read_claims']):hold()
        read=state['read_claims'][ordinal-1]
        if read['state']!='OBSERVED':hold('DRAFT_REVISION_OBSERVATION_REQUIRED')
        if read.get('pending_origin')=='CURRENT_PENDING_BASELINE_ADOPTED_V1':
            witness=state.get('pending_adoption')
            if type(witness) is not dict or witness['reads'][-1]['ordinal']!=ordinal:hold()
            snapshot=self._snapshot({'data':{'snapshot':witness['snapshot']},'target':state['case']['target']})
            if snapshot is None or snapshot.evidence_sha()!=read['snapshot_sha']:hold()
            return snapshot
        proof=self._load_proof(f"result-{state['case']['id']}-{ordinal}.json",read['result_sha'],state['case'])
        return self._snapshot(proof)

    def _state(self,db,case_id):
        if not _hash(case_id):hold('DRAFT_REVISION_CASE_MISSING')
        row=db.execute('SELECT * FROM cases WHERE id=?',(case_id,)).fetchone()
        if row is None:hold('DRAFT_REVISION_CASE_MISSING')
        return _decode(row['value'].encode())

    def _event(self,db,case_id,kind,data,*,guard=None):
        check=self.guard if guard is None else guard
        if kind=='SOURCE_REVIEW' and db.execute('PRAGMA user_version').fetchone()[0]!=5:hold()
        head=self._pins(check);old=None if kind=='REGISTER' else self._state(db,case_id)
        state=reduce(old,kind,data)
        self._event_proofs(old,state,kind,data,event_head={'seq':head['seq'],'event_sha':head['event_sha']})
        case=case_value(state['case'],self.binding)
        if kind=='REGISTER':
            if case['id']!=case_id:hold()
            db.execute('INSERT INTO cases VALUES(?,?,?,?,?,?)',(case_id,case['source_key'],case['original_step'],case['target'],canonical(state),digest(state)))
            db.executemany('INSERT INTO targets VALUES(?,?,?)',[(case_id,r['kind'],r['fingerprint']) for r in case['targets']])
        else:db.execute('UPDATE cases SET value=?,value_sha=? WHERE id=?',(canonical(state),digest(state),case_id))
        event={'schema':1,'profile':PROFILE,'binding':self.binding,'seq':head['seq']+1,
            'previous_sha':head['event_sha'],'case_id':case_id,'type':kind,'data':data}
        db.execute('INSERT INTO events VALUES(?,?,?)',(event['seq'],canonical(event),digest(event)))
        db.execute('UPDATE meta SET seq=?,event_sha=? WHERE id=1',(event['seq'],digest(event)))
        check();files.exclusive(self.root/'events'/(str(event['seq']).zfill(16)+'.json'),event)
        self.fault('event_before_head')
        atomic_write(self.anchor,dict(head,seq=event['seq'],event_sha=digest(event),confirmed_seq=head['seq']))
        self.fault('head_before_commit')

    def register(self,value,*,registration=None):
        """Private trusted registrar; ordinary MCP arguments cannot create Case."""
        value=case_value(value,self.binding);self.guard()
        record=None
        if value['provider_profile']==OFFICIAL_PROVIDER:
            from .draft_revision_registration import QualifiedRegistration,validate_qualified
            if type(registration) is not QualifiedRegistration or registration.case!=value:hold('DRAFT_REVISION_QUALIFIED_REGISTRATION_REQUIRED')
            record=validate_qualified(registration,self)
        elif registration is not None:hold()
        def current_registration():
            self.guard()
            if value['provider_profile']==OFFICIAL_PROVIDER:validate_qualified(registration,self)
        with self.connection(write=True,guard=current_registration) as db:
            old=db.execute('SELECT value FROM cases WHERE id=?',(value['id'],)).fetchone()
            if old:
                if self._state(db,value['id'])['case']!=value:hold('DRAFT_REVISION_CASE_CONFLICT')
            else:
                if db.execute('SELECT 1 FROM cases WHERE source_key=? OR target=? OR original_step=?',
                        (value['source_key'],value['target'],value['original_step'])).fetchone():hold('DRAFT_REVISION_CASE_CONFLICT')
                self._event(db,value['id'],'REGISTER',{'case':value,'registration':record},guard=current_registration)
        return digest({'case':value['id'],'profile':PROFILE})

    def adopt_pending_baseline(self,publication,handle,case_id,gate,authority,guard):
        """Transfer original counted pending GETs; never emits a network call."""
        from .draft_revision_pending_adoption import adopt
        return adopt(self,publication,handle,case_id,gate,authority,guard)

    def state(self,case_id):
        with self.connection() as db:
            state=self._state(db,case_id)
            return deepcopy(state['revision'])|{'provider_profile':state['case']['provider_profile']}

    def source_review_proof(self,case_id):
        """Historical local proof only; no source refresh or send permission."""
        with self.connection() as db:
            state=self._state(db,case_id);head=state.get('source_review')
            if head is None:return None
            name=f"source-review-{case_id}-{head['review_id']}.json"
            proof,actual=files.read(self.root/'proofs'/name,LIMIT)
            if actual!=head['proof_sha']:hold('DRAFT_REVISION_PROOF_CHANGED')
            return deepcopy(proof),actual

    def _claim_context(self,case_id):
        evidence=None
        if self.review_observer is not None:
            if not callable(self.review_observer):hold()
            evidence=self.review_observer(case_id)
        if evidence is not None:
            from .draft_revision_review import SourceReviewClaimEvidence
            if type(evidence) is not SourceReviewClaimEvidence:hold()
        def check():
            self.guard()
            if evidence is not None:evidence.fence()
            return True
        check()
        return evidence,check

    def _claim_linkage(self,current,evidence):
        head=current.get('source_review')
        if head is None:
            if evidence is not None:hold()
            return None
        if evidence is None:hold('DRAFT_REVISION_SOURCE_REVIEW_HOLD')
        if evidence.witness.manifest['origin']['case_id']!=current['case']['id']:hold()
        return claim_review(evidence.value,head)

    def allocate_read(self,case_id,phase):
        if self._admission is not None:hold('DRAFT_REVISION_ADMISSION_OUTSTANDING')
        evidence,check=self._claim_context(case_id)
        with self.connection(write=True,guard=check) as db:
            current=self._state(db,case_id);ordinal=current['revision']['reads']+1
            linkage=self._claim_linkage(current,evidence)
            data={'ordinal':ordinal,'phase':phase,'proof_sha':ZERO}
            if linkage is not None:data['source_review']=linkage
            if ordinal>5:hold('DRAFT_REVISION_READ_BUDGET_EXHAUSTED')
            # Validate transition before publishing any proof.
            reduce(current,'READ_CLAIM',data)
            checksum=self._proof(f'read-{case_id}-{ordinal}.json',
                {'data':{'kind':'GET_CLAIM','ordinal':ordinal,'phase':phase}},
                current['case'],source_review=linkage)
            self._event(db,case_id,'READ_CLAIM',dict(data,proof_sha=checksum),guard=check)
        saved=self.state(case_id)
        self._admission=Admission(case_id,saved['id'],'GET',ordinal,checksum,object(),deepcopy(linkage))
        return self._admission

    def consume_admission(self,admission):
        if type(admission) is not Admission or admission is not self._admission:hold('DRAFT_REVISION_EPHEMERAL_ADMISSION_REQUIRED')
        # Clear even if the final current guard fails: no later stack may reuse.
        self._admission=None;self.guard()
        with self.connection() as db:
            current=self._state(db,admission.case_id);row=current['revision']
            if admission.revision_id!=row['id']:hold()
            if admission.ordinal!=row['reads']:hold('DRAFT_REVISION_ADMISSION_SUPERSEDED')
            if admission.kind=='UPDATE':
                if row['state']!='CLAIMED' or row['claim_sha']!=admission.proof_sha or row['writes']!=1:hold()
                if row.get('claim_source_review')!=admission.source_review:hold()
            elif admission.kind=='GET':
                read=current['read_claims'][admission.ordinal-1]
                if read['state']!='ALLOCATED' or read['claim_sha']!=admission.proof_sha:hold()
                if read.get('source_review')!=admission.source_review:hold()
            else:hold()
        self._inflight[(admission.case_id,admission.kind,admission.ordinal)]=admission
        return True

    def _take_inflight(self,case_id,kind,admission):
        if type(admission) is not Admission or admission.kind!=kind or admission.case_id!=case_id:
            hold('DRAFT_REVISION_ADMITTED_STACK_REQUIRED')
        key=(case_id,kind,admission.ordinal)
        if self._inflight.get(key) is not admission:hold('DRAFT_REVISION_ADMITTED_STACK_REQUIRED')
        # A forged/wrong admission never consumes another stack's capability.
        self._inflight.pop(key)

    def record_read(self,case_id,admission,snapshot=None,*,transport=None):
        """Called only by trusted bounded GET+codec service; None means UNKNOWN."""
        self._take_inflight(case_id,'GET',admission)
        ordinal=admission.ordinal
        from .draft_revision_wire import RevisionSnapshot
        if snapshot is not None and type(snapshot) is not RevisionSnapshot:hold()
        raw=None if snapshot is None else dict(reference=snapshot.reference,canonical_json=snapshot.canonical_json,response_sha=snapshot.response_sha,profile=snapshot.profile)
        with self.connection(write=True,guard=self.history_guard) as db:
            current=self._state(db,case_id)
            if type(ordinal) is not int or not 1<=ordinal<=len(current['read_claims']):hold()
            read=current['read_claims'][ordinal-1]
            if read.get('source_review')!=admission.source_review:hold()
            from .draft_revision_transport import evidence
            capture=evidence(current['case'],admission,transport,None if snapshot is None else snapshot.response_sha)
            status='UNKNOWN' if snapshot is None else 'OBSERVED'
            data={'ordinal':ordinal,'status':status,'snapshot_sha':None if snapshot is None else snapshot.evidence_sha(),'proof_sha':ZERO}
            reduce(current,'READ_RESULT',data)
            checksum=self._proof(f'result-{case_id}-{ordinal}.json',{'data':{'kind':'GET_RESULT','ordinal':ordinal,'claim_sha':read['claim_sha'],'status':status,'snapshot':raw,'transport':capture}},current['case'],
                source_review=admission.source_review)
            self._event(db,case_id,'READ_RESULT',dict(data,proof_sha=checksum),guard=self.history_guard)

    def prepared(self,case_id,ordinal,expected):
        from .draft_revision_wire import baseline_projection
        _encode(expected)
        with self.connection(write=True) as db:
            current=self._state(db,case_id)
            baseline=baseline_projection(self._read_snapshot(current,ordinal))
            data={'ordinal':ordinal,'baseline_sha':digest(baseline),'expected_sha':digest(expected),'proof_sha':ZERO}
            reduce(current,'PREPARED',data)
            checksum=self._proof(f'prepared-{case_id}.json',{'data':{'kind':'PREPARED','ordinal':ordinal,'baseline':baseline,'expected':expected}},current['case'],
                source_review=current['read_claims'][ordinal-1].get('source_review'))
            self._event(db,case_id,'PREPARED',dict(data,proof_sha=checksum))

    def claim_update(self,case_id,ordinal,request_sha):
        if self._admission is not None:hold('DRAFT_REVISION_ADMISSION_OUTSTANDING')
        evidence,check=self._claim_context(case_id)
        with self.connection(write=True,guard=check) as db:
            current=self._state(db,case_id);row=current['revision']
            linkage=self._claim_linkage(current,evidence)
            data={'ordinal':ordinal,'request_sha':request_sha,'proof_sha':ZERO}
            if linkage is not None:data['source_review']=linkage
            reduce(current,'UPDATE_CLAIM',data)
            from .draft_revision_wire import baseline_projection
            if digest(baseline_projection(self._read_snapshot(current,ordinal)))!=row['baseline_sha']:
                hold('DRAFT_REVISION_BASELINE_CHANGED')
            checksum=self._proof(f'claim-{case_id}.json',{'data':{'kind':'UPDATE_CLAIM','ordinal':ordinal,
                'baseline_sha':row['baseline_sha'],'expected_sha':row['expected_sha'],'preparation_sha':row['preparation_sha'],
                'request_sha':request_sha}},current['case'],source_review=linkage)
            self._event(db,case_id,'UPDATE_CLAIM',dict(data,proof_sha=checksum),guard=check)
        confirmed=self.state(case_id)
        self._admission=Admission(case_id,confirmed['id'],'UPDATE',ordinal,checksum,object(),deepcopy(linkage))
        return self._admission

    def record_response(self,case_id,admission,response,secret,*,transport=None):
        """Qualified minimal original result; never persist HTTP body or secrets.

        Only the exact same-stack consumed UPDATE admission can archive a result.
        Reopening validates this sealed result, not a nonexistent raw HTTP log.
        Historical guards may preserve an admitted result after later revocation;
        they never confer a new network admission or bypass current write guards.
        """
        self._take_inflight(case_id,'UPDATE',admission)
        from .draft_revision_wire import parse_update
        result={'response_state':'RESULT_UNKNOWN','errcode':None,'response_raw_sha':None}
        status=None
        if response is not None:
            try:
                parsed=parse_update(response,secret)
                result={'response_state':parsed['response_state'],'errcode':parsed['errcode'],
                    'response_raw_sha':sha256(response.body).hexdigest()}
                status=response.status
            except WCEError:pass  # No unsafe/malformed body is written to disk.
        data={**result,'proof_sha':ZERO}
        with self.connection(write=True,guard=self.history_guard) as db:
            current=self._state(db,case_id);reduce(current,'UPDATE_RESPONSE',data)
            row=current['revision']
            if row['claim_sha']!=admission.proof_sha:hold()
            if row.get('claim_source_review')!=admission.source_review:hold()
            from .draft_revision_transport import evidence
            capture=evidence(current['case'],admission,transport,
                None if response is None else sha256(response.body).hexdigest())
            checksum=self._proof(f'response-{case_id}.json',{'data':{'kind':'ORIGINAL_UPDATE_RESPONSE_ARCHIVE',
                'http_status':status,'claim_sha':row['claim_sha'],'request_sha':row['request_sha'],'transport':capture,**result}},current['case'],
                source_review=admission.source_review)
            self._event(db,case_id,'UPDATE_RESPONSE',dict(data,proof_sha=checksum),guard=self.history_guard)

    def record_effect(self,case_id,ordinal):
        from .draft_revision_wire import baseline_projection
        from .draft_revision_preservation import effect_matches
        with self.connection(write=True) as db:
            current=self._state(db,case_id)
            proof=self._load_proof(f'prepared-{case_id}.json',current['revision']['preparation_sha'],current['case'])
            matched=effect_matches(baseline_projection(self._read_snapshot(current,ordinal)),proof['data']['expected'])
            self._event(db,case_id,'READ_EFFECT',{'ordinal':ordinal,'matched':matched})

    def recover_response_archive(self,case_id):
        """Reconcile the same qualified minimal result; zero HTTP and no grant."""
        if not _hash(case_id):hold()
        with self.connection(write=True,guard=self.history_guard,orphan_response=case_id) as db:
            current=self._state(db,case_id)
            if current['revision']['response_sha'] is None:
                data=self._response_archive_data(current)
                self._event(db,case_id,'UPDATE_RESPONSE',data,guard=self.history_guard)
        return {'state':'ORIGINAL_RESPONSE_ARCHIVE_RECORDED_LOCAL_ONLY'}

    def recover_committed_head(self):
        """Metadata-only confirmation; never recreates a lost admission or HTTP."""
        # Verification, commit/no-op and confirmation share the journal lock.
        with self.connection(write=True,allow_pending=True):pass
        return {'state':'HEAD_CONFIRMED_LOCAL_ONLY'}

    def _guard_targets(self,db,claims):
        if type(claims) is not list or len(claims)>64:hold()
        for kind,checksum in claims:
            if kind not in KINDS or not _hash(checksum):hold()
            if db.execute('SELECT 1 FROM targets WHERE kind=? AND fingerprint=?',(kind,checksum)).fetchone():hold('DRAFT_REVISION_TARGET_WRITE_HOLD')

    def guard_targets(self,claims):
        if type(claims) is not list or len(claims)>64:hold()
        with self.connection() as db:self._guard_targets(db,claims)

    def guard_targets_readonly(self,policy,claims):
        if type(claims) is not list or len(claims)>64:hold()
        with self._readonly_connection(policy) as (db,head):self._guard_targets(db,claims)
