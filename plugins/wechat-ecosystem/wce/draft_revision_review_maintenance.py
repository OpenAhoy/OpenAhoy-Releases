"""Externally pinned maintenance for one original Case's source continuation.

Not exposed by MCP or configuration. Trusted host code constructs these pins
after independent review; file hashes alone are not human authorization. The
manifest's known human sources and current account policy remain mandatory.
Same-UID malicious Python replacement is outside this integrity boundary.
"""
from dataclasses import dataclass,field
from hashlib import sha256
from pathlib import Path
import ast,time
from .service import canonical,digest
from .draft_revision_review import hold

_SEAL=object()
_PROFILE='PINNED_SOURCE_REVIEW_MAINTENANCE_V1'


def need(value):
    if not value:hold()


@dataclass(frozen=True)
class TrustedSourceReviewPins:
    """Exact externally reviewed input, never constructed from model arguments."""
    manifest_path:Path=field(repr=False)
    manifest_sha:str
    asset_path:Path=field(repr=False)
    asset_sha:str
    helper_path:Path=field(repr=False)
    helper_sha:str
    dependencies:tuple=field(repr=False)
    review_path:Path=field(repr=False)
    review_sha:str
    unarmed_launcher_path:Path=field(repr=False)
    unarmed_launcher_sha:str
    armed_launcher_path:Path=field(repr=False)
    arm_receipt_path:Path=field(repr=False)
    arm_receipt_sha:str
    candidate_scope:str


def _read(path,expected):
    from .bounded_file import FileSource
    from .draft_revision_state import checksum
    need(isinstance(path,Path) and path.is_absolute() and checksum(expected))
    raw=FileSource(path.parent).read(path.name)
    need(sha256(raw).hexdigest()==expected)
    return raw


def _json(raw):
    from .publication_contract import strict_json
    return strict_json(raw,maximum=2*1024*1024)


def verify_pins(pins,service):
    """Two-stage review/arm pins avoid embedding a file's hash in itself."""
    from .own_body_recovery import code_scope
    from .draft_revision_state import checksum
    need(type(pins) is TrustedSourceReviewPins and checksum(pins.candidate_scope)
        and type(pins.dependencies) is tuple and len(pins.dependencies)<=64)
    need(code_scope()==pins.candidate_scope
        ==service.policy.value['candidate_scope'])
    manifest_raw=_read(pins.manifest_path,pins.manifest_sha)
    asset_raw=_read(pins.asset_path,pins.asset_sha)
    _read(pins.helper_path,pins.helper_sha)
    dependency_rows=[]
    for row in pins.dependencies:
        need(type(row) is tuple and len(row)==2)
        _read(*row);dependency_rows.append([str(row[0]),row[1]])
    need(len({row[0] for row in dependency_rows})==len(dependency_rows))
    acceptance={'helper_sha':pins.helper_sha,'dependencies_sha':digest(dependency_rows),
        'review_sha':pins.review_sha,'unarmed_launcher_sha':pins.unarmed_launcher_sha,
        'arm_receipt_sha':pins.arm_receipt_sha,'candidate_scope':pins.candidate_scope}
    review=_json(_read(pins.review_path,pins.review_sha))
    expected={'schema':1,'profile':_PROFILE,'state':'REVIEW_PASS',
        'manifest_sha':pins.manifest_sha,'asset_sha':pins.asset_sha,
        'helper_sha':pins.helper_sha,'dependencies_sha':acceptance['dependencies_sha'],
        'candidate_scope':pins.candidate_scope,'unarmed_launcher_sha':pins.unarmed_launcher_sha,
        'permitted_arm_assignments':['REVIEW_PATH','REVIEW_SHA']}
    need(canonical(review)==canonical(expected))
    unarmed=_read(pins.unarmed_launcher_path,pins.unarmed_launcher_sha)
    tree=ast.parse(unarmed.decode('utf-8'))
    marked={}
    for node in ast.walk(tree):
        if isinstance(node,(ast.Assign,ast.AnnAssign)):
            targets=node.targets if isinstance(node,ast.Assign) else [node.target]
            for target in targets:
                if isinstance(target,ast.Name) and target.id in {'REVIEW_PATH','REVIEW_SHA'}:
                    need(target.id not in marked and isinstance(node,ast.Assign)
                        and len(targets)==1 and isinstance(node.value,ast.Constant)
                        and node.value.value is None)
                    marked[target.id]=True
    need(set(marked)=={'REVIEW_PATH','REVIEW_SHA'})
    armed=unarmed
    for name,value in [('REVIEW_PATH',str(pins.review_path)),('REVIEW_SHA',pins.review_sha)]:
        old=(name+' = None').encode();new=(name+' = '+repr(value)).encode()
        need(armed.count(old)==1);armed=armed.replace(old,new)
    armed_sha=sha256(armed).hexdigest()
    need(_read(pins.armed_launcher_path,armed_sha)==armed)
    armed_tree=ast.parse(armed.decode('utf-8'));actual={}
    for node in ast.walk(armed_tree):
        if isinstance(node,(ast.Assign,ast.AnnAssign)):
            targets=node.targets if isinstance(node,ast.Assign) else [node.target]
            for target in targets:
                if isinstance(target,ast.Name) and target.id in marked:
                    need(target.id not in actual and isinstance(node,ast.Assign)
                        and len(targets)==1 and isinstance(node.value,ast.Constant))
                    actual[target.id]=node.value.value
    need(actual=={'REVIEW_PATH':str(pins.review_path),'REVIEW_SHA':pins.review_sha})
    receipt=_json(_read(pins.arm_receipt_path,pins.arm_receipt_sha))
    need(canonical(receipt)==canonical({'schema':1,'profile':'SOURCE_REVIEW_ARM_DIFF_V1',
        'state':'ARMED_PIN_DIFF_PASS','review_sha':pins.review_sha,
        'unarmed_launcher_sha':pins.unarmed_launcher_sha,'armed_launcher_sha':armed_sha,
        'only_review_constants':True}))
    return manifest_raw,asset_raw,acceptance


@dataclass(frozen=True)
class QualifiedSourceReview:
    proof_json:str=field(repr=False)
    proof_sha:str
    epoch:str
    _store:object=field(repr=False,compare=False)
    _adapter:object=field(repr=False,compare=False)
    _gate:object=field(repr=False,compare=False)
    _pins:object=field(repr=False,compare=False)
    _fence:object=field(repr=False,compare=False)
    _seal:object=field(repr=False,compare=False)

    def __post_init__(self):
        need(self._seal is _SEAL and callable(self._fence))

    @property
    def proof(self):return _json(self.proof_json.encode())

    def fence(self):
        # Called under the journal writer lock: do not reenter journal query.
        need(self._gate.held() and self._adapter.source_review.epoch()==self.epoch)
        verify_pins(self._pins,self._adapter.service)
        need(self._fence() is True)
        return True

def qualify_source_review(service,store,case_id,pins,gate):
    """Fresh actual input/source qualification while the original Gate is held."""
    from .draft_revision_gate import RevisionExecutionGate
    from .draft_revision_store import RevisionStore,case_value
    from .draft_revision_registration import validate_record,reopen_adapter
    from .draft_revision_review_value import validate_manifest,validate_review_proof,review_id
    from .draft_revision_review import witness_from_proof,observed_fence
    from .draft_revision_review_store import query,_frame
    need(type(store) is RevisionStore and type(gate) is RevisionExecutionGate
        and gate.service is service and gate.held() and store.account==service.policy.root)
    service.guard(gate.deadline)
    raw,asset_raw,acceptance=verify_pins(pins,service)
    before=query(store,case_id,pins.manifest_sha)
    # Committed proofs are queried, never requalified/reissued after claims.
    need(before['state'] in {'NOT_PUBLISHED','PROOF_ONLY_NOT_PUBLISHED',
        'EVENT_ONLY_NOT_COMMITTED','HEAD_AHEAD_NOT_COMMITTED','COMMITTED_UNCONFIRMED'})
    state=before['original'];case=case_value(state['case'],store.binding)
    record=validate_record(state['registration'],case)
    need(state['revision']['state']=='PREPARING'
        and state['revision']['reads']==state['revision']['writes']==0 and not state['read_claims'])
    validate_manifest(raw,asset_raw,pins.manifest_sha,case,record)
    frame=_frame(store,case_id,pins.manifest_sha)
    proof=frame.proof
    if proof is None:
        need(before['state']=='NOT_PUBLISHED')
        proof={'schema':2,'profile':'SOURCE_REVIEW_CONTINUATION_V1',
            'origin_profile':case['profile'],'binding':case['binding'],
            'case_id':case_id,'case_sha':digest(case),
            'revision_id':digest({'case':case_id,'profile':case['profile']}),
            'review_id':review_id(case_id,pins.manifest_sha),'previous_review_sha':None,
            'manifest_raw':raw.decode(),'manifest_sha':pins.manifest_sha,
            'asset_raw':asset_raw.decode(),'acceptance':acceptance,
            'creation':{'journal_seq':before['sql_head']['seq'],
                'journal_sha':before['sql_head']['event_sha'],'reads':0,'writes':0,
                'state':'PREPARING','observed_at':time.time()}}
    else:
        need(proof['manifest_raw'].encode()==raw and proof['asset_raw'].encode()==asset_raw
            and proof['acceptance']==acceptance)
    proof_sha=sha256((canonical(proof)+'\n').encode()).hexdigest()
    validate_review_proof(proof,proof_sha,case,record)
    def pending_head():
        current=query(store,case_id,pins.manifest_sha)
        need(current['state']==before['state'] and current['original']==state
            and current['anchor']==before['anchor'] and current['sql_head']==before['sql_head']
            and current['proof_sha']==before['proof_sha'])
        return True
    witness=witness_from_proof(service,store,case,record,proof,proof_sha,gate.deadline,
        published=False,pending_head_guard=pending_head)
    adapter=reopen_adapter(service,record,case,gate.deadline,source_review=witness)
    observed=adapter.inspect()
    need(observed.capsule==record['input'] and not observed.authority)
    fence=observed_fence(adapter,observed)
    # Captured in the sealed qualifier, not selected by subsequent callers.
    result=QualifiedSourceReview(canonical(proof),proof_sha,witness.epoch(),store,adapter,gate,pins,fence,_SEAL)
    pending_head();result.fence()
    return result


def publish_source_review(qualified):
    """Only this sealed fresh qualifier may reach the local write engine."""
    from .draft_revision_review_store import _publish_under_lock
    need(type(qualified) is QualifiedSourceReview)
    qualified.fence()
    return _publish_under_lock(qualified._store,qualified.proof,
        qualified.proof_sha,qualified.fence)
