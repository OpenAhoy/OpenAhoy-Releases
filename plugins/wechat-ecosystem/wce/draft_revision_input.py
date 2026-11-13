"""Trusted host current-input acquisition, without Case registration or grant.

Paths, native cursors and semantic source pins are fixed by reviewed host
maintenance, never supplied by a draft tool caller. All files/old proofs/source
events are revalidated; no credential, token, upload or platform API is used.
The resulting object remains evidence until a separately reviewed registrar
binds the actual human single-draft scope and account to a durable Case.
"""
from copy import deepcopy
from dataclasses import dataclass,field
from hashlib import sha256
from pathlib import Path
import re
import math

from .bounded_file import FileSource
from .contracts import WCEError
from .draft_revision_native_lookup import NativeThreadLookup
from .draft_revision_native_source import registration_digest
from .draft_revision_source_observer import SourceWindow,observe_window,fence_window,release_window
from .draft_revision_resources import original_saved,render_reuse
from .draft_revision_artifact import derive
from .draft_revision_preservation import PreservationPlan,ChangedImagePlan
from .own_workflow import projection
from .service import canonical,digest

_SEAL=object()
_FAILED_OBSERVATION=object()

def hold():raise WCEError('DRAFT_REVISION_CURRENT_INPUT_HOLD')

def checksum(value):
    return type(value) is str and re.fullmatch('[a-f0-9]{64}',value) is not None

@dataclass(frozen=True)
class ImageSelection:
    relative_path:str
    sha256:str

@dataclass(frozen=True)
class ArtifactSelection:
    root:Path=field(repr=False)
    old_relative_path:str
    old_sha256:str
    new_relative_path:str
    new_sha256:str
    images:tuple=field(repr=False)

    def __post_init__(self):
        if (not isinstance(self.root,Path) or not checksum(self.old_sha256) or not checksum(self.new_sha256)
                or type(self.images) is not tuple or not 1<=len(self.images)<=5
                or any(type(i) is not ImageSelection or not checksum(i.sha256) for i in self.images)
                or len({i.relative_path for i in self.images})!=len(self.images)):hold()

@dataclass(frozen=True)
class DirectArtifactSelection(ArtifactSelection):
    """Private exact-file selection; it is evidence and grants no action."""
    metadata_relative_path:str
    metadata_sha256:str
    image_names:tuple=field(repr=False)

    def __post_init__(self):
        super().__post_init__()
        if (type(self.metadata_relative_path) is not str or not self.metadata_relative_path
                or not checksum(self.metadata_sha256) or type(self.image_names) is not tuple
                or len(self.image_names)!=len(self.images)
                or any(type(n) is not str or not n or n in ('.','..') or '/' in n or chr(92) in n
                    for n in self.image_names) or len(set(self.image_names))!=len(self.image_names)):hold()

@dataclass(frozen=True)
class PendingImageSelection(DirectArtifactSelection):
    """Exact author-side image, before a remote image reference exists."""
    new_image_relative_path:str
    new_image_sha256:str
    changed_index:int
    def __post_init__(self):
        super().__post_init__()
        if (type(self.new_image_relative_path) is not str or not self.new_image_relative_path
                or not checksum(self.new_image_sha256) or type(self.changed_index) is not int
                or not 0<=self.changed_index<len(self.images)
                or self.new_image_sha256==self.images[self.changed_index].sha256):hold()

@dataclass(frozen=True)
class MaterializedImageSelection(PendingImageSelection):
    """Exact local asset and current-ledger handle after a successful upload."""
    current_handle:str
    new_asset_ref:str
    def __post_init__(self):
        super().__post_init__()
        if (type(self.current_handle) is not str or re.fullmatch(r'current-pub-[a-f0-9]{48}',self.current_handle) is None
                or type(self.new_asset_ref) is not str or re.fullmatch(r'own-asset-[a-f0-9]{32}',self.new_asset_ref) is None):hold()

@dataclass(frozen=True)
class VerifiedRevisionInput:
    """Detached read evidence only. Not an execution permit or review result."""
    capsule_json:str=field(repr=False)
    source_sha256:str
    original:object=field(repr=False)
    derived:dict=field(repr=False)
    observations:tuple=field(repr=False)
    preservation:PreservationPlan=field(repr=False)
    _seal:object=field(repr=False)
    def __post_init__(self):
        if self._seal is not _SEAL:hold()
    @property
    def authority(self):return False
    @property
    def capsule(self):
        from .publication_contract import strict_json
        return strict_json(self.capsule_json.encode(),maximum=2*1024*1024)

@dataclass(frozen=True)
class VerifiedPendingImage:
    """Only local source evidence; no Case, token, upload grant or URL."""
    proposal_json:str=field(repr=False)
    original:object=field(repr=False)
    observations:tuple=field(repr=False)
    _seal:object=field(repr=False)
    def __post_init__(self):
        if self._seal is not _SEAL:hold()
    @property
    def proposal(self):
        from .publication_contract import strict_json
        return strict_json(self.proposal_json.encode(),maximum=2*1024*1024)
    @property
    def authority(self):return False
    @property
    def source_sha256(self):return self.proposal['human_source_sha256']

@dataclass(frozen=True)
class _ComputedPending:
    artifacts:tuple=field(repr=False)
    transports:tuple=field(repr=False)
    image:bytes=field(repr=False)
    proposal_json:str=field(repr=False)
    _seal:object=field(repr=False)
    def __post_init__(self):
        if (self._seal is not _SEAL or type(self.artifacts) is not tuple or len(self.artifacts) not in (4,5)
                or type(self.transports) is not tuple or type(self.image) is not bytes
                or type(self.proposal_json) is not str):hold()

@dataclass(frozen=True)
class _ComputedInputs:
    """Exact bytes behind pure derivation; never substitutes a current read."""
    artifacts:tuple=field(repr=False)
    transports:tuple=field(repr=False)
    derived_json:str=field(repr=False)
    capsule_json:str=field(repr=False)
    preservation_html:str=field(repr=False)
    preservation_urls:tuple=field(repr=False)
    _seal:object=field(repr=False)
    changed_index:object=field(default=None,repr=False)
    new_url:object=field(default=None,repr=False)
    def __post_init__(self):
        if (self._seal is not _SEAL or type(self.artifacts) is not tuple
                or len(self.artifacts) not in (3,4,5) or type(self.transports) is not tuple
                or type(self.derived_json) is not str or type(self.capsule_json) is not str
                or type(self.preservation_html) is not str
                or type(self.preservation_urls) is not tuple
                or any(type(v) is not str for v in self.preservation_urls)
                or any(type(v) is not bytes for v in self.artifacts[:2])
                or type(self.artifacts[2]) is not tuple
                or any(type(v) is not bytes for v in self.artifacts[2]+self.transports)
                or (len(self.artifacts)>=4 and type(self.artifacts[3]) is not bytes)
                or (len(self.artifacts)==5 and type(self.artifacts[4]) is not bytes)
                or ((self.changed_index is None)!=(self.new_url is None))
                or (self.changed_index is not None and (type(self.changed_index) is not int or type(self.new_url) is not str))):hold()

class RevisionInputAdapter:
    def __init__(self,service,lookup,windows,selection,original_save_key,deadline,
                 *,expected_capsule_sha=None,expected_source_sha=None,source_review=None):
        from .own_connection_broker import AccountService
        if (type(service) is not AccountService or type(lookup) is not NativeThreadLookup
                or type(windows) is not tuple or not 1<=len(windows)<=2
                or any(type(w) is not SourceWindow for w in windows)
                or type(selection) not in (ArtifactSelection,DirectArtifactSelection,PendingImageSelection,MaterializedImageSelection) or type(original_save_key) is not str
                or not original_save_key or len(original_save_key)>128
                or type(deadline) not in (float,int) or not math.isfinite(deadline) or deadline<=0
                or any(v is not None and not checksum(v) for v in (expected_capsule_sha,expected_source_sha))):hold()
        if lookup.allowed_threads!=frozenset(w.source.thread_id for w in windows):hold()
        if type(selection) in (DirectArtifactSelection,PendingImageSelection,MaterializedImageSelection):
            from .draft_revision_source_observer import HumanPin
            if any(type(window.pins) is not tuple or any(type(pin) is not HumanPin for pin in window.pins) for window in windows):hold()
        purposes=[p.purpose for w in windows for p in w.pins]
        if type(selection) in (DirectArtifactSelection,PendingImageSelection,MaterializedImageSelection):
            from .draft_revision_source_views import validate_direct_windows
            validate_direct_windows(windows)
        elif purposes.count('initial_edit')!=1 or purposes.count('resume_same_case')!=1:hold()
        self.service,self.lookup,self.windows,self.selection=service,lookup,windows,selection
        self.original_save_key,self.deadline=original_save_key,deadline
        self.expected_capsule_sha,self.expected_source_sha=expected_capsule_sha,expected_source_sha
        if source_review is not None:
            from .draft_revision_review import SourceReviewWitness
            if (type(source_review) is not SourceReviewWitness
                    or source_review.service is not service or source_review.deadline!=deadline):hold()
        self.source_review=source_review
        self.files=FileSource(selection.root)

    def _guard(self):
        self.service.guard(self.deadline)
        return True

    def _source_binding(self):
        # Observation generations may change; the reviewed source registrations
        # and exact USER pins remain the immutable Case binding.
        if type(self.selection) is ArtifactSelection:
            stable={'profile':'NATIVE_SINGLE_REVISION_SOURCE_EVIDENCE_V1',
                'owner_thread':self.lookup.owner_thread,
                'windows':[{'registration_sha256':registration_digest(w.source),
                    'pins':[vars(p) for p in w.pins]} for w in self.windows]}
            source_sha=digest(stable)
        else:
            from .draft_revision_source_views import source_binding
            source_sha=source_binding(self.lookup.owner_thread,self.windows)
        if self.expected_source_sha is not None and source_sha!=self.expected_source_sha:hold()
        return source_sha

    def _source_cache(self,guard):
        from .draft_revision_scan import RevisionScanGuard
        from .draft_revision_gate import _ACTIVE,_SOURCE_OBSERVATIONS
        active=_ACTIVE.get();scope=_SOURCE_OBSERVATIONS.get()
        if type(guard) is not RevisionScanGuard:return None
        guard.full()
        if (active is not guard.active or type(scope) is not tuple or len(scope)!=2
                or scope[0] is not active or type(scope[1]) is not dict):hold()
        return scope[1]

    def _discard_sources(self):
        from .draft_revision_gate import _SOURCE_OBSERVATIONS
        scope=_SOURCE_OBSERVATIONS.get()
        if type(scope) is tuple and len(scope)==2 and type(scope[1]) is dict:
            # Drop all old evidence and poison this epoch: a provider may catch
            # the failure to archive UNKNOWN, but must not silently re-observe
            # and continue inside the same execution gate afterward.
            scope[1][self]=_FAILED_OBSERVATION

    def _source_cache_binding(self):
        lookup=self.lookup
        base=(lookup,lookup.guard,lookup.state_path,lookup.session_root,
            lookup.owner_thread,lookup.allowed_threads,lookup.deadline,self.windows)
        if self.source_review is None:return base
        return base+(self.source_review,id(self.source_review),self.source_review.reference)

    def _sources(self):
        from .draft_revision_scan import for_adapter,full
        guard=for_adapter(self);full(guard)
        review=self.source_review
        if review is not None:review.check()
        source_sha=self._source_binding();cache=self._source_cache(guard)
        cached=cache.get(self) if cache is not None else None
        if cached is None and cache is not None and type(self.selection) in (PendingImageSelection,MaterializedImageSelection):
            cached=cache.get(('pending',self))
        if cached is _FAILED_OBSERVATION:
            from .draft_revision_native_source import SourceHold
            raise SourceHold('REVISION_SOURCE_GATE_INVALIDATED')
        if cached is not None:
            if (type(cached) is not tuple or len(cached)!=3
                    or cached[0]!=self._source_cache_binding()
                    or type(cached[1]) not in (VerifiedRevisionInput,VerifiedPendingImage)
                    or cached[1]._seal is not _SEAL or cached[1].source_sha256!=source_sha
                    or len(cached[1].observations)!=len(self.windows)
                    or type(cached[2]) not in (_ComputedInputs,_ComputedPending)
                    or (type(cached[1]),type(cached[2])) not in ((VerifiedRevisionInput,_ComputedInputs),(VerifiedPendingImage,_ComputedPending))
                    or cached[2]._seal is not _SEAL):hold()
            observations=cached[1].observations
            if review is not None and any(o.value.get('review')!=review.reference
                    or o.value.get('gate_epoch')!=review.epoch() for o in observations):hold()
            # Reuse only the completely checked generation from an earlier
            # successful inspect in this exact Gate entry. Any append, rewrite,
            # rotation or index change still fails before the result is used.
            for window,observation in zip(self.windows,observations):
                fence_window(self.lookup,window,observation,guard)
        else:
            if review is None:
                observations=tuple(observe_window(self.lookup,w,guard) for w in self.windows)
            else:
                observations=tuple(observe_window(self.lookup,w,guard,source_review=review)
                    for w in self.windows)
        if type(self.selection) is not ArtifactSelection:
            from .draft_revision_source_views import verify_observations
            verify_observations(self.windows,observations)
        full(guard)
        return source_sha,observations

    def _read(self,relative,expected,*,html=False):
        self._guard();raw=self.files.read_html(relative) if html else self.files.read(relative)
        if sha256(raw).hexdigest()!=expected:hold()
        self._guard();return raw

    def _original(self):
        w=self.service.workflow;p=self.service.profile()
        with _history_transaction(w.db) as (db, history_locators):
            original=original_saved(w,db,p,self.original_save_key, history_locators=history_locators)
            transports=[]
            for asset in original.manifest['assets']:
                meta,raw=w._asset(db,p.binding(),asset['asset_ref'],asset['role'])
                if meta!={k:asset[k] for k in meta}:hold()
                if asset['role']=='body':transports.append(raw)
        return original,tuple(transports)

    def _artifacts(self):
        selected=self.selection
        old_raw=self._read(selected.old_relative_path,selected.old_sha256,html=True)
        new_raw=self._read(selected.new_relative_path,selected.new_sha256,html=True)
        source_images=tuple(self._read(i.relative_path,i.sha256) for i in selected.images)
        if type(selected) is MaterializedImageSelection:
            return old_raw,new_raw,source_images,self._read(selected.metadata_relative_path,selected.metadata_sha256),self._read(selected.new_image_relative_path,selected.new_image_sha256)
        if type(selected) in (DirectArtifactSelection,PendingImageSelection):
            return old_raw,new_raw,source_images,self._read(selected.metadata_relative_path,selected.metadata_sha256)
        return old_raw,new_raw,source_images

    def _materialized_evidence(self,original,artifacts):
        from .draft_revision_gate import _ACTIVE,RevisionExecutionGate
        from .current_publication_store import Store
        from .own_connection_policy import registry_path
        from .draft_revision_pending_upload import validate as validate_upload
        selected=self.selection;active=_ACTIVE.get()
        if (type(selected) is not MaterializedImageSelection or active is None
                or type(active[0]) is not RevisionExecutionGate or active[0].service is not self.service
                or active[0].deadline!=self.deadline or active[0].held() is not True):hold()
        pending=self.inspect_pending()
        if pending.original!=original:hold()
        policy=self.service.policy;registry=Path(policy.value.get('registry_path') or registry_path())
        store=Store(policy,registry,guard=self._guard);value,row=store.target(selected.current_handle)
        locked=value.get('revision_pending_images',{}).get(selected.current_handle)
        baseline=value.get('revision_pending_baselines',{}).get(selected.current_handle)
        upload=value.get('revision_pending_uploads',{}).get(selected.current_handle)
        if (type(locked) is not dict or locked['proposal']!=pending.proposal
                or row['reference']!=original.reference or type(upload) is not dict
                or upload.get('state')!='SUCCEEDED'):hold()
        validate_upload(upload,locked,baseline)
        p=self.service.profile();w=self.service.workflow;proposal=pending.proposal
        extension='.png' if proposal['mime']=='image/png' else '.jpg'
        staged='import-'+proposal['source_sha256']+extension
        parameters={'path_digest':sha256(staged.encode()).hexdigest(),'role':'body','mime':proposal['mime']}
        with _history_transaction(w.db) as (db,locators):
            w._resource(db,p,history_locators=locators)
            key='revision-asset-'+locked['proposal_sha256']
            value=w._old_input(db,p,'asset',key,parameters)
            meta,raw=w._asset(db,p.binding(),selected.new_asset_ref,'body')
            if value!=meta|{'request_key':key,'input_state':'COMMITTED'} or raw!=artifacts[4] or sha256(raw).hexdigest()!=proposal['source_sha256']:hold()
        original_asset=original.manifest['assets'][selected.changed_index+1]
        asset=dict(original_asset,**meta)
        if active[0].held() is not True:hold()
        return pending.proposal,upload,asset

    def inspect(self):
        if type(self.selection) is PendingImageSelection:hold()
        try:return self._inspect()
        except BaseException:
            self._discard_sources()
            raise

    def _inspect(self):
        self._guard();source_sha,observations=self._sources()
        original,transports=self._original()
        artifacts=self._artifacts()
        old_raw,new_raw,source_images=artifacts[:3]
        materialized=(self._materialized_evidence(original,artifacts)
            if type(self.selection) is MaterializedImageSelection else None)
        # Read only the map already checked by _sources. Adding another guard
        # callback here would move the established final-fence ordering.
        from .draft_revision_gate import _ACTIVE,_SOURCE_OBSERVATIONS
        scope=_SOURCE_OBSERVATIONS.get();cache=None
        if scope is not None:
            if (type(scope) is not tuple or len(scope)!=2 or scope[0] is not _ACTIVE.get()
                    or type(scope[1]) is not dict):hold()
            cache=scope[1]
        cached=cache.get(self) if cache is not None else None
        if cached is not None:
            # _sources has freshly fenced this exact Gate's sealed observation.
            # Both current proof/image objects and every selected file byte have
            # just been read again. Only deterministic HTML work is reused.
            if (cached is _FAILED_OBSERVATION or type(cached) is not tuple
                    or len(cached)!=3 or cached[0]!=self._source_cache_binding()
                    or type(cached[1]) is not VerifiedRevisionInput
                    or cached[1]._seal is not _SEAL
                    or cached[1].source_sha256!=source_sha
                    or cached[1].observations!=observations
                    or cached[1].original!=original
                    or cached[2].artifacts!=artifacts or cached[2].transports!=tuple(transports)
                    or canonical(cached[1].derived)!=cached[2].derived_json
                    or cached[1].capsule_json!=cached[2].capsule_json
                    or type(cached[1].preservation) not in (PreservationPlan,ChangedImagePlan)
                    or cached[1].preservation.original_html!=cached[2].preservation_html
                    or cached[1].preservation.upload_urls!=cached[2].preservation_urls
                    or getattr(cached[1].preservation,'changed_index',None)!=cached[2].changed_index
                    or getattr(cached[1].preservation,'new_url',None)!=cached[2].new_url):hold()
            from .publication_contract import strict_json
            derived=strict_json(cached[2].derived_json.encode(),maximum=2*1024*1024)
            capsule=cached[1].capsule
            if materialized is not None:
                if capsule.get('image_upload')!={'pending':materialized[0],'upload':materialized[1]}:hold()
                plan=ChangedImagePlan(cached[2].preservation_html,cached[2].preservation_urls,cached[2].changed_index,cached[2].new_url)
            else:plan=PreservationPlan(cached[2].preservation_html,cached[2].preservation_urls)
        else:
            if type(self.selection) is MaterializedImageSelection:
                from .draft_revision_materialized_image import derive as derive_materialized
                images=list(source_images);images[self.selection.changed_index]=artifacts[4]
                derived,relation=derive_materialized(original,old_raw,new_raw,source_images,tuple(transports),tuple(images),
                    artifacts[3],self.selection.metadata_sha256,image_names=self.selection.image_names,
                    changed_index=self.selection.changed_index,proposal=materialized[0],upload=materialized[1],asset=materialized[2])
            elif type(self.selection) is DirectArtifactSelection:
                from .draft_revision_direct_artifact import derive as derive_direct
                derived,relation=derive_direct(original,old_raw,new_raw,source_images,tuple(transports),
                    artifacts[3],self.selection.metadata_sha256,image_names=self.selection.image_names)
            else:derived,relation=derive(original,old_raw,new_raw,source_images,tuple(transports))
            capsule=render_reuse(original,derived,source_relation=relation,
                image_upload=({'pending':materialized[0],'upload':materialized[1]} if materialized is not None else None))
            capsule['source_binding_sha']=source_sha
            rendered=projection(original.manifest,original.mappings)
            rows=rendered['articles'] if 'articles' in rendered else [rendered]
            if len(rows)!=1:hold()
            urls=tuple(original.mappings[a['slot']]['url'] for a in original.manifest['assets'] if a['role']=='body')
            plan=(ChangedImagePlan(rows[0]['content'],urls,self.selection.changed_index,materialized[1]['url'])
                if materialized is not None else PreservationPlan(rows[0]['content'],urls))
            if plan.evidence()!=capsule['preservation']:hold()
        if self.expected_capsule_sha is not None and digest(capsule)!=self.expected_capsule_sha:hold()
        after,observations=self._sources()
        if source_sha!=after:hold()
        # Source observation can be long. Reopen every selected artifact and
        # original proof after it, rather than returning stale earlier evidence.
        if self._original()!=(original,transports) or self._artifacts()!=artifacts:hold()
        for window,observation in zip(self.windows,observations):
            fence_window(self.lookup,window,observation,self._guard)
        self._guard()
        verified=VerifiedRevisionInput(canonical(capsule),source_sha,original,deepcopy(derived),
            observations,plan,_SEAL)
        # Publish only after both complete source observations, artifact/proof
        # reopens and final fences succeeded. Gate exit always clears the map.
        from .draft_revision_scan import for_adapter
        cache=self._source_cache(for_adapter(self))
        # No callbacks/guards after this final all-window fence: a late guard
        # can append to an earlier window while checking a later one.
        for window,observation in zip(self.windows,observations):
            release_window(window,observation)
        if cache is not None:
            computed=_ComputedInputs(artifacts,tuple(transports),canonical(derived),
                verified.capsule_json,plan.original_html,plan.upload_urls,_SEAL,
                getattr(plan,'changed_index',None),getattr(plan,'new_url',None))
            cache[self]=(self._source_cache_binding(),verified,computed)
        return verified

    def inspect_pending(self):
        """Acquire local evidence only; no Case, baseline, upload or grant."""
        if type(self.selection) not in (PendingImageSelection,MaterializedImageSelection):hold()
        try:return self._inspect_pending()
        except BaseException:
            self._discard_sources()
            raise

    def _inspect_pending(self):
        self._guard();source_sha,observations=self._sources()
        original,transports=self._original();artifacts=self._artifacts()
        image=self._read(self.selection.new_image_relative_path,self.selection.new_image_sha256)
        from .draft_revision_scan import for_adapter
        cache=self._source_cache(for_adapter(self));cached=cache.get(('pending',self)) if cache is not None else None
        if cached is not None:
            if (type(cached) is not tuple or len(cached)!=3 or cached[0]!=self._source_cache_binding()
                    or type(cached[1]) is not VerifiedPendingImage or cached[1]._seal is not _SEAL
                    or cached[1].source_sha256!=source_sha or cached[1].observations!=observations
                    or cached[1].original!=original or type(cached[2]) is not _ComputedPending
                    or cached[2]._seal is not _SEAL or cached[2].artifacts!=artifacts
                    or cached[2].transports!=tuple(transports) or cached[2].image!=image
                    or cached[2].proposal_json!=cached[1].proposal_json):hold()
            proposal=cached[1].proposal
        else:
            images=list(artifacts[2]);images[self.selection.changed_index]=image
            from .draft_revision_direct_artifact import pending_image
            proposal=pending_image(original,artifacts[0],artifacts[1],artifacts[2],tuple(transports),
                tuple(images),artifacts[3],self.selection.metadata_sha256,
                image_names=self.selection.image_names,changed_index=self.selection.changed_index)
            proposal.update(human_source_sha256=source_sha,binding_sha256=digest(original.manifest['binding']),
                reference_sha256=digest(original.reference),original_step_sha256=digest(original.step_id),
                original_intent_sha256=original.intent_digest,original_result_sha256=original.result_digest)
        after,observations=self._sources()
        if (source_sha!=after or self._original()!=(original,transports) or self._artifacts()!=artifacts
                or self._read(self.selection.new_image_relative_path,self.selection.new_image_sha256)!=image):hold()
        for window,observation in zip(self.windows,observations):
            fence_window(self.lookup,window,observation,self._guard)
        self._guard();verified=VerifiedPendingImage(canonical(proposal),original,observations,_SEAL)
        cache=self._source_cache(for_adapter(self))
        for window,observation in zip(self.windows,observations):release_window(window,observation)
        if cache is not None:
            cache[('pending',self)]=(self._source_cache_binding(),verified,
                _ComputedPending(artifacts,tuple(transports),image,verified.proposal_json,_SEAL))
        return verified

    def current(self):return self.inspect().capsule

    def claim_source_review(self,case_id):
        if self.source_review is None:return None
        if self.source_review.manifest['origin']['case_id']!=case_id:hold()
        from .draft_revision_review import claim_evidence
        return claim_evidence(self,self.inspect())

    def matches_snapshot(self,snapshot):
        from .draft_revision_wire import RevisionSnapshot
        if type(snapshot) is not RevisionSnapshot:return False
        return self._matches_observed_snapshot(snapshot,self.inspect())

    def matches_pending_snapshot(self,snapshot):
        from .draft_revision_wire import RevisionSnapshot
        if type(self.selection) not in (PendingImageSelection,MaterializedImageSelection):hold()
        if type(snapshot) is not RevisionSnapshot:return False
        return self._matches_observed_snapshot(snapshot,self.inspect_pending())

    def _matches_observed_snapshot(self,snapshot,observed):
        from .draft_revision_wire import RevisionSnapshot
        from .draft_revision_preservation import observe_original
        if type(snapshot) is not RevisionSnapshot:return False
        original=observed.original
        if snapshot.reference!=original.reference:return False
        projected=projection(original.manifest,original.mappings)
        rows=projected['articles'] if 'articles' in projected else [projected]
        actual=snapshot.rows()
        if len(actual)!=1 or actual[0]['thumb_media_id']!=rows[0]['thumb_media_id']:return False
        if type(self.selection) in (DirectArtifactSelection,PendingImageSelection,MaterializedImageSelection):
            # Compare only metadata present in the verified original send; do
            # not invent absent optional fields or overwrite current values.
            workflow=self.service.workflow;profile=self.service.profile()
            with _history_transaction(workflow.db) as (db,history_locators):
                row=workflow._history(db,profile,self.original_save_key,history_locators=history_locators)
                if row is None or row['id']!=original.step_id:return False
                intent,_=workflow._step(db,profile,row,history_locators=history_locators)
            projected=intent.get('projection')
            saved=projected.get('articles') if type(projected) is dict and 'articles' in projected else [projected]
            if type(saved) is not list or len(saved)!=1 or type(saved[0]) is not dict:return False
            for key in ('title','author','digest','content_source_url','thumb_media_id',
                    'need_open_comment','only_fans_can_comment','cover_info'):
                if key in saved[0] and (key not in actual[0] or actual[0][key]!=saved[0][key]):return False
        # The exact original ref, cover and complete body identify this case.
        # Fresh title/author/digest/comment/crop metadata is retained from GET;
        # only content is allowed to change under this registration profile.
        urls=tuple(original.mappings[a['slot']]['url'] for a in original.manifest['assets'] if a['role']=='body')
        observe_original(rows[0]['content'],actual[0]['content'],urls)
        return True


from .draft_group_history_context import history_transaction as _history_transaction
