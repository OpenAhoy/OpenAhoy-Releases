"""Private same-Case source witnesses. No MCP registration or permission API.

Historical proof validation never refreshes a source, policy or execution epoch.
The trusted publisher qualifies its exact external maintenance pins separately.
These Python seals are integrity boundaries within this host, not an OS sandbox.
"""
from copy import deepcopy
from dataclasses import dataclass,field
import re,threading
from .contracts import WCEError
from .service import canonical,digest

_SEAL=object()
REVIEW_PROFILE='SOURCE_REVIEW_CONTINUATION_V1'
CLAIM_PROFILE='SOURCE_REVIEWED_CLAIM_V1'


def hold():raise WCEError('DRAFT_REVISION_SOURCE_REVIEW_HOLD')


@dataclass(frozen=True)
class SourceReviewWitness:
    service:object=field(repr=False,compare=False)
    deadline:float
    manifest_json:str=field(repr=False)
    asset_json:str=field(repr=False)
    review_id:str
    review_sha:str
    manifest_sha:str
    published:bool
    _head_guard:object=field(repr=False,compare=False)
    _seal:object=field(repr=False,compare=False)

    def __post_init__(self):
        if (self._seal is not _SEAL or type(self.published) is not bool
                or not callable(self._head_guard)
                or any(type(v) is not str or re.fullmatch('[a-f0-9]{64}',v) is None
                    for v in (self.review_id,self.review_sha,self.manifest_sha))):hold()

    @property
    def manifest(self):
        from .publication_contract import strict_json
        return strict_json(self.manifest_json.encode(),maximum=2*1024*1024)

    @property
    def asset(self):
        from .publication_contract import strict_json
        return strict_json(self.asset_json.encode(),maximum=16384)

    @property
    def reference(self):
        return {'profile':REVIEW_PROFILE,'review_id':self.review_id,
            'review_sha':self.review_sha,'manifest_sha':self.manifest_sha,
            'published':self.published}

    def epoch(self):
        from .draft_revision_gate import _ACTIVE,RevisionExecutionGate
        active=_ACTIVE.get()
        if (active is None or type(active[0]) is not RevisionExecutionGate
                or active[0].service is not self.service
                or active[0].deadline!=self.deadline
                or active[1]!=threading.get_ident() or not active[0].held()
                or active is not active[0]._active_entry
                or type(active[0].entry_id) is not str
                or re.fullmatch('[a-f0-9]{32}',active[0].entry_id) is None):hold()
        return active[0].entry_id

    def check(self):
        self.epoch()
        self.service.guard(self.deadline)
        if self._head_guard() is not True:hold()
        self.epoch()
        return True


@dataclass(frozen=True)
class SourceReviewClaimEvidence:
    """Current, same-entry observation; its fence never reopens this journal."""
    witness:SourceReviewWitness=field(repr=False)
    value_json:str=field(repr=False)
    _fence:object=field(repr=False,compare=False)
    _seal:object=field(repr=False,compare=False)

    def __post_init__(self):
        if (self._seal is not _SEAL or type(self.witness) is not SourceReviewWitness
                or not self.witness.published or not callable(self._fence)):hold()
        from .draft_revision_state import claim_review
        claim_review(self.value)

    @property
    def value(self):
        from .publication_contract import strict_json
        return strict_json(self.value_json.encode(),maximum=4096)

    def fence(self):
        # The caller holds the journal lock and compares its current head with
        # this descriptor. Do not invoke _head_guard here and recursively lock
        # the journal. Actual artifacts/source/index/policy are still checked.
        value=self.value
        if self.witness.epoch()!=value['gate_epoch']:hold()
        if self._fence() is not True:hold()
        if self.witness.epoch()!=value['gate_epoch']:hold()
        return True


def witness_from_proof(service,store,case,registration,proof,proof_sha,deadline,*,published,
                       pending_head_guard=None):
    """Called by the registered runtime or externally pinned publisher only."""
    from .draft_revision_review_value import validate_review_proof
    from .draft_revision_registration import validate_record
    validate_record(registration,case)
    parsed=validate_review_proof(proof,proof_sha,case,registration)
    fixed=deepcopy(case)
    def current_head():
        with store.connection() as db:
            state=store._state(db,fixed['id'])
            if state['case']!=fixed or state['registration']!=registration:hold()
            head=state.get('source_review')
            if published:
                if (type(head) is not dict or head['proof_sha']!=proof_sha
                        or head['review_id']!=proof['review_id']
                        or head['review_manifest_sha']!=proof['manifest_sha']):hold()
            elif (head is not None or state['revision']['reads']!=0
                    or state['revision']['writes']!=0
                    or state['revision']['state']!='PREPARING'):hold()
        return True
    if pending_head_guard is not None:
        if published or not callable(pending_head_guard):hold()
        current_head=pending_head_guard
    return SourceReviewWitness(service,deadline,canonical(parsed['manifest']),
        canonical(parsed['asset']),proof['review_id'],proof_sha,proof['manifest_sha'],
        published,current_head,_SEAL)


def observed_fence(adapter,observed):
    """Same-entry source/artifact fence, without reentrant journal reads."""
    from .draft_revision_input import RevisionInputAdapter,VerifiedRevisionInput
    from .draft_revision_source_observer import fence_window,release_window
    if type(adapter) is not RevisionInputAdapter or type(observed) is not VerifiedRevisionInput:hold()
    review=adapter.source_review
    if type(review) is not SourceReviewWitness:hold()
    review.check();epoch=review.epoch();reference=review.reference
    if any(o.value.get('review')!=reference or o.value.get('gate_epoch')!=epoch
            for o in observed.observations):hold()
    def fence():
        if adapter.source_review is not review or review.epoch()!=epoch:hold()
        adapter._guard()
        original,_=adapter._original()
        if original!=observed.original:hold()
        adapter._artifacts()  # Existing exact selection hashes, without a grant.
        for window,observation in zip(adapter.windows,observed.observations):
            fence_window(adapter.lookup,window,observation,adapter._guard)
        adapter._guard()
        for window,observation in zip(adapter.windows,observed.observations):
            release_window(window,observation)
        return True
    fence()
    return fence


def claim_evidence(adapter,observed):
    """Only the exact concrete adapter may bind its inspected fixed input."""
    fence=observed_fence(adapter,observed)
    review=adapter.source_review
    if not review.published:hold()
    epoch=review.epoch();reference=review.reference
    value={'profile':CLAIM_PROFILE,'review_id':review.review_id,
        'review_sha':review.review_sha,'manifest_sha':review.manifest_sha,
        'observation_sha':digest({'profile':'SOURCE_REVIEWED_OBSERVATION_V1',
            'case_id':review.manifest['origin']['case_id'],'review':reference,
            'gate_epoch':epoch,'sources':[o.sha256 for o in observed.observations]}),
        'gate_epoch':epoch}
    result=SourceReviewClaimEvidence(review,canonical(value),fence,_SEAL)
    result.fence()
    return result
