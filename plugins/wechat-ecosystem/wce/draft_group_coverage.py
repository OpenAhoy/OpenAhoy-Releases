"""Current, entry-issued ACCOUNT observations from original archived claims.

The pure planner Coverage is a display/value object. This issuer additionally
requires an actual Host scope, the complete two scans, every admitted GET, the
original source facts, and the same entry's retained file pins. No network call
or grant is created here.
"""
from dataclasses import dataclass
from contextvars import ContextVar
import json,time,weakref
from .contracts import WCEError
from .draft_group_contracts import Coverage,canonical,digest
from .own_validation_scope import OwnedConnection,_transaction_marker

_TIME=time.time
_RECORDS=weakref.WeakKeyDictionary()
_SUBJECTS=ContextVar('group_current_subject_binding',default=None)


def hold(code='GROUP_ACCOUNT_COVERAGE_HOLD'):
    raise WCEError(code)


def need(value,code='GROUP_ACCOUNT_COVERAGE_HOLD'):
    if value is not True:hold(code)


class AccountCoverage:
    def __init__(self):hold('GROUP_ACCOUNT_COVERAGE_ISSUER_REQUIRED')
    @property
    def observed_at_ms(self):return _record(self).observed_at_ms
    @property
    def proof_sha(self):return _record(self).proof_sha
    @property
    def references(self):return tuple(_record(self).references)
    @property
    def snapshots(self):return tuple(_record(self).snapshots)
    @property
    def candidate(self):return _record(self).candidate


@dataclass(frozen=True)
class _Record:
    host: object
    entry: object
    scope: object
    files: object
    grant_sha: str
    proof_sha: str
    observed_at_ms: int
    references: tuple
    snapshots: tuple
    candidate: Coverage


def _record(value):
    need(type(value) is AccountCoverage,'GROUP_ACCOUNT_COVERAGE_UNISSUED')
    record=_RECORDS.get(value)
    need(record is not None and record.entry.issued.get(id(value)) is value,
         'GROUP_ACCOUNT_COVERAGE_UNISSUED')
    return record


def _require_snapshot(files,db,state,claim,*,reference=None,list_offset=None):
    from .draft_group_response_history import load_original_locator_in
    need(claim['state']=='OBSERVED' and claim['outcome']=='OBSERVED'
         and type(claim['proof_sha']) is str,'GROUP_ACCOUNT_READ_INCOMPLETE')
    locator=load_original_locator_in(files,db,state,claim['id'],reference=reference,list_offset=list_offset)
    primary=files.read_primary(locator);snapshot=files.read_snapshot(locator,primary)
    need(primary.sha256==claim['proof_sha'] and snapshot is not None,'GROUP_ACCOUNT_READ_INCOMPLETE')
    value=primary.value;obs=value['observation']
    need(obs['outcome']=='OBSERVED' and obs['timing']=='COMPLETED_MS'
         and type(obs['observed_at_ms']) is int and obs['observed_at_ms']>=claim['at_ms'],
         'GROUP_ACCOUNT_TIMING_UNQUALIFIED')
    return primary,snapshot


def _scope_state(host,db,scope, *, history_locators=None):
    """Original IDs only; does not recurse through OwnStore/current/source."""
    from .draft_group_runtime_host import validate_admission_scope
    validate_admission_scope(scope, history_locators=None)
    need(scope.host is host and scope.entry is host.entry
         and scope.details['ledger_kind']=='PREVIEW','GROUP_ACCOUNT_SCOPE_REQUIRED')
    need(type(db) is OwnedConnection and _transaction_marker(db) is not None,
         'GROUP_ACCOUNT_OWNED_TRANSACTION_REQUIRED')
    state=host._group_state_in(db);info=host._family_in(db, history_locators=history_locators)
    purpose=[p for p in info['covenant']['purposes']
             if p['source_grant_sha']==scope.details['purpose_key']]
    need(len(purpose)==1 and purpose[0]['purpose'] in
         ('PREVIEW_ACCOUNT','EXECUTION_INITIAL_ACCOUNT','PROMOTION_ACCOUNT'),
         'GROUP_ACCOUNT_PURPOSE_REQUIRED')
    gid=scope.details['gid'];grant=state['preview_grants'].get(gid)
    need(grant is not None and not grant['hold'] and grant['registration']['phase']=='DISCOVER',
         'GROUP_ACCOUNT_READ_INCOMPLETE')
    return state,grant


def _collect_lists(db,state,grant,files):
    from .draft_group_discovery import ListPage,compare_passes
    claims=grant['claims'];lists=[c for c in claims if c['api']=='LIST']
    gets=[c for c in claims if c['api']=='GET']
    need(len(claims)==len(lists)+len(gets) and 2<=len(lists)<=20,
         'GROUP_ACCOUNT_READ_INCOMPLETE')
    synthetic=state['source_kind']=='SYNTHETIC_SETUP'
    pages=[];receipts=[];times=[];page_count=None
    for index,claim in enumerate(lists):
        need(claim['ordinal']==index+1,'GROUP_ACCOUNT_READ_ORDER')
        offset=0 if page_count is None else (index%page_count)*20
        primary,snapshot=_require_snapshot(files,db,state,claim,list_offset=offset)
        page_value=json.loads(snapshot.raw)
        total=page_value.get('total_count')
        need(type(total) is int and 0<=total<=200,'GROUP_ACCOUNT_LIST_BOUND')
        if page_count is None:page_count=max(1,(total+19)//20)
        page=ListPage(offset,canonical(page_value),primary.value['transport']['response_body_sha'])
        page.value(synthetic=synthetic);pages.append(page)
        receipts.append((claim['id'],primary.sha256,snapshot.sha256))
        times.append(primary.value['observation']['observed_at_ms'])
    need(len(pages)==2*page_count,'GROUP_ACCOUNT_READ_INCOMPLETE')
    compared=compare_passes(tuple(pages[:page_count]),tuple(pages[page_count:]),synthetic=synthetic)
    return compared,receipts,times


def _collect(host,db,scope,files, *, history_locators=None):
    from .draft_group_wire import GroupSnapshot,reference_sha,baseline_projection
    state,grant=_scope_state(host,db,scope, history_locators=history_locators)
    compared,receipts,times=_collect_lists(db,state,grant,files)
    references=compared['references'];subjects=compared['subject_shas']
    gets=[c for c in grant['claims']if c['api']=='GET'];synthetic=state['source_kind']=='SYNTHETIC_SETUP'
    need(list(subjects)==grant['subjects'] and len(gets)==len(references),
         'GROUP_ACCOUNT_GET_COVERAGE_INCOMPLETE')
    snapshots=[]
    for index,(claim,reference,subject) in enumerate(zip(gets,references,subjects)):
        need(claim['ordinal']==index+1 and claim['subject_sha']==subject
             and subject==reference_sha(reference,synthetic=synthetic),'GROUP_ACCOUNT_READ_ORDER')
        primary,snapshot=_require_snapshot(files,db,state,claim,reference=reference)
        parsed=GroupSnapshot(reference,canonical(json.loads(snapshot.raw)),
                             primary.value['transport']['response_body_sha'])
        projected=baseline_projection(parsed,synthetic=synthetic)
        need(digest(projected)==primary.value['observation']['projection_sha'],
             'GROUP_ACCOUNT_GET_PROJECTION_CHANGED')
        snapshots.append(parsed);receipts.append((claim['id'],primary.sha256,snapshot.sha256))
        times.append(primary.value['observation']['observed_at_ms'])
    need(len(times)>=2,'GROUP_ACCOUNT_READ_INCOMPLETE')
    files.collective_fence()
    proof={'profile':'GROUP_CURRENT_ACCOUNT_COVERAGE_V1','binding_sha':state['binding_sha'],
           'family_id':scope.details['family_id'],'purpose_key':scope.details['purpose_key'],
           'grant_id':scope.details['gid'],'grant_sha':digest(grant),'items_sha':compared['items_sha'],
           'subjects':list(subjects),'receipts':[list(r)for r in receipts],
           'observed_at_ms':min(times),'latest_observed_at_ms':max(times)}
    return state,proof,tuple(references),tuple(snapshots)


def _list_proof(scope,grant,compared,receipts,times):
    return {'profile':'GROUP_CURRENT_ACCOUNT_SUBJECTS_V1','grant_id':scope.details['gid'],
        'family_id':scope.details['family_id'],'purpose_key':scope.details['purpose_key'],
        'list_claims_sha':digest([c for c in grant['claims']if c['api']=='LIST']),
        'items_sha':compared['items_sha'],'subjects':list(compared['subject_shas']),
        'receipts':[list(r)for r in receipts],
        'observed_at_ms':min(times),'latest_observed_at_ms':max(times)}


def validate_discovery_subjects_in(host,db,details, *, history_locators=None):
    pending=_SUBJECTS.get()
    need(pending is not None and pending[0] is host and pending[1] is db
         and pending[2]==_transaction_marker(db),'GROUP_ACCOUNT_SUBJECT_ISSUER_REQUIRED')
    _,_,_,scope,files,payload=pending
    from .draft_group_runtime_host import validate_admission_scope
    validate_admission_scope(scope,db=db, history_locators=history_locators)
    state,grant=_scope_state(host,db,scope, history_locators=history_locators)
    need(grant['subjects'] is None and not any(c['api']=='GET'for c in grant['claims']),
         'GROUP_ACCOUNT_SUBJECTS_ALREADY_BOUND')
    compared,receipts,times=_collect_lists(db,state,grant,files)
    proof=_list_proof(scope,grant,compared,receipts,times)
    expected={'grant_id':scope.details['gid'],'subjects':list(compared['subject_shas']),
              'proof_sha':digest(proof)}
    need(canonical(details)==canonical(payload)==canonical(expected),'GROUP_ACCOUNT_SUBJECTS_CHANGED')
    files.collective_fence();_fresh_fence(host,proof)
    return None


def bind_account_subjects_in(host,db,qualified_read, *, history_locators=None):
    """Bind only the original completed scans; no GET or new read allowance."""
    from .draft_group_runtime_host import validate_admission_scope,response_history_context_in
    from .draft_group_response_files import GroupResponseFiles
    from .draft_group_store import GroupStore
    validate_admission_scope(qualified_read,db=db, history_locators=history_locators)
    need(type(db)is OwnedConnection and _transaction_marker(db)is not None
         and db.execute('PRAGMA query_only').fetchone()[0]==0,'GROUP_ACCOUNT_WRITE_TRANSACTION_REQUIRED')
    host.current_no_token_in(db,qualified_read.source, history_locators=history_locators)
    state,grant=_scope_state(host,db,qualified_read, history_locators=history_locators)
    files=GroupResponseFiles.from_history_context(host.entry.policy,
        response_history_context_in(db,host.entry.policy))
    compared,receipts,times=_collect_lists(db,state,grant,files)
    proof=_list_proof(qualified_read,grant,compared,receipts,times)
    payload={'grant_id':qualified_read.details['gid'],'subjects':list(compared['subject_shas']),
             'proof_sha':digest(proof)}
    if grant['subjects'] is not None:
        need(grant['subjects']==payload['subjects'] and grant['subjects_proof_sha']==payload['proof_sha'],
             'GROUP_ACCOUNT_SUBJECTS_CHANGED')
        _fresh_fence(host,proof);return tuple(compared['references'])
    need(not any(c['api']=='GET'for c in grant['claims']),'GROUP_ACCOUNT_GET_ORDER')
    token=_SUBJECTS.set((host,db,_transaction_marker(db),qualified_read,files,payload))
    try:
        GroupStore(state['binding_sha'],_history_partial(host.verify_in, history_locators=history_locators)).bind_discovery_subjects_in(db,
            payload['grant_id'],subjects=payload['subjects'],proof_sha=payload['proof_sha'], history_locators=history_locators)
    finally:_SUBJECTS.reset(token)
    return tuple(compared['references'])


def _fresh_fence(host,proof):
    # Complete replaceable preparation precedes this pure fence. Only a fixed
    # original primitive clock is sampled afterwards; no callback follows it.
    host.pure_release_fence()
    now=int(_TIME()*1000)
    need(0<=now-proof['observed_at_ms']<=60000
         and proof['latest_observed_at_ms']<=now,'GROUP_ACCOUNT_COVERAGE_EXPIRED')


def issue_account_coverage_in(host,db,qualified_read, *, history_locators=None):
    from .draft_group_runtime_host import validate_admission_scope,response_history_context_in
    from .draft_group_response_files import GroupResponseFiles
    validate_admission_scope(qualified_read,db=db, history_locators=history_locators)
    need(qualified_read.host is host,'GROUP_ACCOUNT_SCOPE_REQUIRED')
    host.current_no_token_in(db,qualified_read.source, history_locators=history_locators)
    files=GroupResponseFiles.from_history_context(host.entry.policy,
                                                  response_history_context_in(db,host.entry.policy))
    state,proof,refs,snapshots=_collect(host,db,qualified_read,files, history_locators=history_locators)
    pool=state['pool'];generation=0 if pool is None else pool['generation']
    head='0'*64 if pool is None else pool['head']
    candidate=Coverage(state['binding_sha'],'ACCOUNT',digest(proof),generation,head)
    _fresh_fence(host,proof)
    value=object.__new__(AccountCoverage)
    _RECORDS[value]=_Record(host,host.entry,qualified_read,files,proof['grant_sha'],digest(proof),
                           proof['observed_at_ms'],refs,snapshots,candidate)
    host.entry.issued[id(value)]=value
    return value


def verify_account_coverage(value,host,db, *, history_locators=None):
    record=_record(value)
    need(record.host is host and record.entry is host.entry,'GROUP_ACCOUNT_ENTRY_CHANGED')
    host.entry.held_pure()
    state,proof,refs,snapshots=_collect(host,db,record.scope,record.files, history_locators=history_locators)
    need(digest(proof)==record.proof_sha and proof['grant_sha']==record.grant_sha
         and refs==record.references
         and tuple(x.evidence_sha256()for x in snapshots)==
             tuple(x.evidence_sha256()for x in record.snapshots),'GROUP_ACCOUNT_COVERAGE_CHANGED')
    _fresh_fence(host,proof)
    return None


from functools import partial as _history_partial
