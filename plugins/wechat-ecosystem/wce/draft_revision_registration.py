"""Private reviewed-host registration for one original-draft content correction.

There is no MCP registration/grant method. The maintenance host pins its reviewed
helper and source semantics; native USER observations alone confer no authority.
The immutable registration contains the full original/derived proof projection,
so replay recomputes the target basis instead of trusting a self-consistent list.
Same-UID malicious Python/file replacement is outside this integrity model.
"""
from copy import deepcopy
from dataclasses import asdict,dataclass,field
from hashlib import sha256
from pathlib import Path

from .bounded_file import FileSource
from .contracts import WCEError
from .service import canonical,digest
from .draft_revision_input import RevisionInputAdapter,VerifiedRevisionInput,checksum
from .draft_revision_resources import OriginalSavedDraft,render_reuse

PROFILE='HOST_REVIEWED_ORIGINAL_NEWS_CONTENT_CORRECTION_V1'
DIRECT_PROFILE='HOST_REVIEWED_EXACT_DIRECT_REVISION_V1'
BOUND_IMAGE_PROFILE='HOST_REVIEWED_EXACT_DIRECT_ONE_IMAGE_REVISION_V1'
_SEAL=object()


def hold():raise WCEError('DRAFT_REVISION_REGISTRATION_HOLD')


@dataclass(frozen=True)
class TrustedRevisionPins:
    """Constructed only by the externally reviewed maintenance helper."""
    helper_path:Path=field(repr=False)
    helper_sha256:str
    dependencies:tuple=field(repr=False)
    review_path:Path=field(repr=False)
    review_sha256:str
    binding:str
    original_save_key:str
    new_source_sha256:str
    human_pins:tuple=field(repr=False)


@dataclass(frozen=True)
class QualifiedRegistration:
    case_json:str=field(repr=False)
    record_json:str=field(repr=False)
    _seal:object=field(repr=False)
    _adapter:object=field(repr=False)
    _gate:object=field(repr=False)
    _pins:object=field(repr=False)
    def __post_init__(self):
        if self._seal is not _SEAL:hold()
    @property
    def case(self):
        from .publication_contract import strict_json
        return strict_json(self.case_json.encode(),maximum=2*1024*1024)
    @property
    def record(self):
        from .publication_contract import strict_json
        return strict_json(self.record_json.encode(),maximum=2*1024*1024)


def _read_pin(path,expected):
    if not isinstance(path,Path) or not path.is_absolute() or not checksum(expected):hold()
    if sha256(FileSource(path.parent).read(path.name)).hexdigest()!=expected:hold()


def verify_pins(pins,adapter):
    if type(pins) is not TrustedRevisionPins or type(adapter) is not RevisionInputAdapter:hold()
    for value in (pins.binding,pins.new_source_sha256):
        if not checksum(value):hold()
    if (type(pins.dependencies) is not tuple or len(pins.dependencies)>32
            or type(pins.human_pins) is not tuple or not 2<=len(pins.human_pins)<=8
            or pins.original_save_key!=adapter.original_save_key
            or pins.new_source_sha256!=adapter.selection.new_sha256
            or pins.binding!=digest(adapter.service.profile().binding())):hold()
    from .draft_revision_source_views import classify,canonical_pins,RELATION
    from .draft_revision_input import ArtifactSelection
    if type(adapter.selection) is ArtifactSelection:
        actual=tuple(sorted((p.thread_id,p.turn_id,p.message_id,p.text_sha256,p.purpose)
            for w in adapter.windows for p in w.pins))
        relation=None
    else:
        relation=classify(adapter.windows);actual=canonical_pins(adapter.windows)
    if (tuple(sorted(pins.human_pins))!=actual
            or (relation==RELATION and pins.human_pins!=actual)):hold()
    _read_pin(pins.helper_path,pins.helper_sha256);_read_pin(pins.review_path,pins.review_sha256)
    for row in pins.dependencies:
        if type(row) is not tuple or len(row)!=2:hold()
        _read_pin(*row)
    adapter._guard()


def acquisition_spec(adapter):
    """Private immutable selectors, never accepted as tool-supplied JSON."""
    lookup=adapter.lookup;selected=adapter.selection
    artifacts={'root':str(selected.root),'old_relative_path':selected.old_relative_path,
        'old_sha256':selected.old_sha256,'new_relative_path':selected.new_relative_path,
        'new_sha256':selected.new_sha256,'images':[asdict(i) for i in selected.images]}
    from .draft_revision_input import DirectArtifactSelection,PendingImageSelection,MaterializedImageSelection
    if type(selected) in (DirectArtifactSelection,PendingImageSelection,MaterializedImageSelection):
        artifacts.update(profile='DIRECT_SAFE_HTML_MIXED_REUSE_V1',
            metadata_relative_path=selected.metadata_relative_path,metadata_sha256=selected.metadata_sha256,
            image_names=list(selected.image_names))
    if type(selected) in (PendingImageSelection,MaterializedImageSelection):
        artifacts.update(profile='DIRECT_SAFE_HTML_ONE_IMAGE_PENDING_V1',
            new_image_relative_path=selected.new_image_relative_path,
            new_image_sha256=selected.new_image_sha256,changed_index=selected.changed_index)
    if type(selected) is MaterializedImageSelection:
        artifacts.update(profile='DIRECT_SAFE_HTML_ONE_IMAGE_BOUND_V1',
            current_handle=selected.current_handle,new_asset_ref=selected.new_asset_ref)
    result={'owner_thread':lookup.owner_thread,'state_path':str(lookup.state_path),
        'session_root':str(lookup.session_root),'windows':[
            {'source':dict(asdict(w.source),path=str(w.source.path)),
             'pins':[asdict(p) for p in w.pins]} for w in adapter.windows],
        'artifact_root_identity':list(adapter.files.root_identity),
        'artifacts':artifacts,
        'original_save_key':adapter.original_save_key}
    from .draft_revision_input import ArtifactSelection
    if type(selected) is not ArtifactSelection:
        from .draft_revision_source_views import classify,RELATION
        if classify(adapter.windows)==RELATION:result['view_relation']=RELATION
    return result



def validate_record(record,case):
    """Replay historical immutable registration, never acquire a new grant."""
    from .draft_revision_store import OFFICIAL_PROVIDER
    keys={'profile','scope','source_sha','input','original','derived','acquisition','review'}
    if (type(record) is not dict or set(record)!=keys or record['profile'] not in (PROFILE,DIRECT_PROFILE,BOUND_IMAGE_PROFILE)
            or type(record['input']) is not dict or type(record['input'].get('changes')) is not dict
            or case['provider_profile']!=OFFICIAL_PROVIDER
            or digest(record)!=case['registration_proof_sha']
            or record['source_sha']!=case['source_sha']):hold()
    fields=sorted(record['input']['changes'])
    if record['profile']==PROFILE:
        if fields!=['content']:hold()
    else:
        from .draft_revision_direct_artifact import PROFILE as DIRECT_SOURCE
        from .draft_revision_materialized_image import PROFILE as BOUND_SOURCE
        relation=record['input'].get('source_relation')
        if (not fields or not set(fields)<={'content','title','digest'}
                or type(relation) is not dict or relation.get('profile')!=(BOUND_SOURCE if record['profile']==BOUND_IMAGE_PROFILE else DIRECT_SOURCE)):hold()
    if record['scope']!={'fields':fields,'get_maximum':5,'update_maximum':1,
        'add_maximum':0,'upload_maximum':1 if record['profile']==BOUND_IMAGE_PROFILE else 0,'delete_maximum':0,'publish_maximum':0}:hold()
    original=record['original']
    if type(original) is not dict or set(original)!=set(OriginalSavedDraft.__dataclass_fields__):hold()
    original=OriginalSavedDraft(**deepcopy(original))
    value=record['input']
    if type(value) is not dict or (record['profile']==PROFILE and set(value.get('changes',{}))!={'content'}):hold()
    reconstructed=render_reuse(original,record['derived'],source_relation=value.get('source_relation'),
        image_upload=value.get('image_upload') if record['profile']==BOUND_IMAGE_PROFILE else None)
    reconstructed['source_binding_sha']=record['source_sha']
    if (reconstructed!=value or digest(value)!=case['input_sha'] or value['binding']!=case['binding']
            or value['reference_sha']!=case['target'] or value['original_step_sha']!=case['original_step']
            or value['target_basis']!=case['target_basis']):hold()
    spec=record['acquisition'];review=record['review']
    if (type(spec) is not dict or set(spec) not in ({'owner_thread','state_path','session_root','windows','artifacts','original_save_key','artifact_root_identity'}, {'owner_thread','state_path','session_root','windows','artifacts','original_save_key','artifact_root_identity','view_relation'})
            or type(review) is not dict or set(review)!={'helper_sha256','review_sha256','dependencies_sha256','original_save_key','human_pins_sha256'}
            or spec['original_save_key']!=review.get('original_save_key')
            or any(not checksum(review[k]) for k in ('helper_sha256','review_sha256','dependencies_sha256','human_pins_sha256'))
            or spec['artifacts']['new_sha256']!=value['source_relation']['new_source_sha256']):hold()
    # Every recorded native selector is revalidated by the concrete runtime
    # adapter. This structural roundtrip rejects extra fields at replay as well.
    windows,selection=adapter_spec(spec,check_files=False)
    from .draft_revision_source_views import RELATION,canonical_pins,source_binding
    if spec.get('view_relation')==RELATION:
        if (source_binding(spec['owner_thread'],windows)!=record['source_sha']
                or digest(canonical_pins(windows))!=review['human_pins_sha256']):hold()
    from .draft_revision_input import ArtifactSelection,DirectArtifactSelection,MaterializedImageSelection
    if record['profile'] in (DIRECT_PROFILE,BOUND_IMAGE_PROFILE):
        if (type(selection) is not (MaterializedImageSelection if record['profile']==BOUND_IMAGE_PROFILE else DirectArtifactSelection)
                or selection.metadata_sha256!=value['source_relation']['metadata_sha256']):hold()
    elif type(selection) is not ArtifactSelection:hold()
    if any(type(n) is not int for n in record['scope'].values() if not isinstance(n,list)):hold()
    if len((canonical(record)+'\n').encode())>2*1024*1024:hold()
    return deepcopy(record)


def qualify(adapter,pins,gate):
    from .draft_revision_gate import RevisionExecutionGate
    from .draft_revision_store import PROFILE as JOURNAL,OFFICIAL_PROVIDER,required_targets,case_value
    if (type(gate) is not RevisionExecutionGate or gate.service is not adapter.service or not gate.held()):hold()
    verify_pins(pins,adapter);observed=adapter.inspect()
    if type(observed) is not VerifiedRevisionInput or observed.authority:hold()
    value=observed.capsule
    from .draft_revision_input import DirectArtifactSelection,MaterializedImageSelection
    from .draft_revision_direct_artifact import PROFILE as DIRECT_SOURCE
    from .draft_revision_materialized_image import PROFILE as BOUND_SOURCE
    bound=type(adapter.selection) is MaterializedImageSelection
    direct=type(adapter.selection) in (DirectArtifactSelection,MaterializedImageSelection)
    fields=sorted(value['changes'])
    relation=value.get('source_relation')
    if (not fields or not set(fields)<={'content','title','digest'}
            or (not direct and fields!=['content'])
            or (direct and (type(relation) is not dict or relation.get('profile')!=(BOUND_SOURCE if bound else DIRECT_SOURCE)))):hold()
    record={'profile':BOUND_IMAGE_PROFILE if bound else DIRECT_PROFILE if direct else PROFILE,'scope':{'fields':fields,'get_maximum':5,'update_maximum':1,
        'add_maximum':0,'upload_maximum':1 if bound else 0,'delete_maximum':0,'publish_maximum':0},
        'source_sha':observed.source_sha256,'input':value,'original':asdict(observed.original),
        'derived':deepcopy(observed.derived),'acquisition':acquisition_spec(adapter),
        'review':{'helper_sha256':pins.helper_sha256,'review_sha256':pins.review_sha256,
            'dependencies_sha256':digest([(str(p),s) for p,s in pins.dependencies]),
            'original_save_key':pins.original_save_key,'human_pins_sha256':digest(pins.human_pins)}}
    case={'profile':JOURNAL,'binding':value['binding'],'target':value['reference_sha'],
        'original_step':value['original_step_sha'],'source_sha':observed.source_sha256,
        'registration_proof_sha':digest(record),'input_sha':digest(value),
        'maximum_reads':5,'maximum_updates':1,'provider_profile':OFFICIAL_PROVIDER,
        'target_basis':deepcopy(value['target_basis'])}
    case['targets']=required_targets(case)
    case['source_key']=digest({k:case[k] for k in ('profile','binding','original_step','source_sha')})
    case['id']=digest({'profile':JOURNAL,'source_key':case['source_key'],'input_sha':case['input_sha'],
        'registration_proof_sha':case['registration_proof_sha'],'provider_profile':OFFICIAL_PROVIDER,
        'target_basis_sha':digest(case['target_basis'])})
    case_value(case,value['binding']);validate_record(record,case);verify_pins(pins,adapter)
    if adapter.inspect().capsule!=value or not gate.held():hold()
    return QualifiedRegistration(canonical(case),canonical(record),_SEAL,adapter,gate,pins)


def validate_qualified(qualified,store):
    from .draft_revision_gate import RevisionExecutionGate
    if (type(qualified) is not QualifiedRegistration or type(qualified._gate) is not RevisionExecutionGate
            or not qualified._gate.held() or qualified._gate.service is not qualified._adapter.service
            or store.account!=qualified._adapter.service.policy.root):hold()
    verify_pins(qualified._pins,qualified._adapter)
    observed=qualified._adapter.inspect();record=validate_record(qualified.record,qualified.case)
    if (record['input']!=observed.capsule or record['original']!=asdict(observed.original)
            or record['derived']!=observed.derived or record['acquisition']!=acquisition_spec(qualified._adapter)):hold()
    return record


def adapter_spec(spec,*,check_files=True):
    from .draft_revision_native_source import RegisteredSource
    from .draft_revision_source_observer import SourceWindow,HumanPin
    from .draft_revision_input import ArtifactSelection,DirectArtifactSelection,PendingImageSelection,MaterializedImageSelection,ImageSelection
    try:
        windows=[]
        for item in spec['windows']:
            if set(item)!={'source','pins'}:hold()
            source=dict(item['source']);source['path']=Path(source['path'])
            windows.append(SourceWindow(RegisteredSource(**source),tuple(HumanPin(**p) for p in item['pins'])))
        item=dict(spec['artifacts']);item['root']=Path(item['root'])
        item['images']=tuple(ImageSelection(**i) for i in item['images'])
        profile=item.pop('profile',None)
        if profile is None:selection=ArtifactSelection(**item)
        elif profile=='DIRECT_SAFE_HTML_MIXED_REUSE_V1':
            item['image_names']=tuple(item['image_names']);selection=DirectArtifactSelection(**item)
        elif profile=='DIRECT_SAFE_HTML_ONE_IMAGE_PENDING_V1':
            item['image_names']=tuple(item['image_names']);selection=PendingImageSelection(**item)
        elif profile=='DIRECT_SAFE_HTML_ONE_IMAGE_BOUND_V1':
            item['image_names']=tuple(item['image_names']);selection=MaterializedImageSelection(**item)
        else:hold()
        from .draft_revision_source_views import validate_direct_windows,RELATION
        relation=None if type(selection) is ArtifactSelection else validate_direct_windows(tuple(windows))
        if (spec.get('view_relation')!=relation
                or ('view_relation' in spec and relation!=RELATION)):hold()
        pin=spec['artifact_root_identity']
        if type(pin) is not list or len(pin)!=2 or any(type(n) is not int or n<0 for n in pin):hold()
        if check_files and list(FileSource(selection.root).root_identity)!=pin:hold()
        return tuple(windows),selection
    except (TypeError,KeyError,ValueError):hold()


def restore_adapter(service,record,case,deadline,*,source_review=None):
    """Restore selectors only; the action Gate must inspect before any send.

    This returns no verified input or authority. The full reopen helper below
    retains its observation contract for other maintenance callers.
    """
    from .draft_revision_native_lookup import NativeThreadLookup
    validate_record(record,case);spec=record['acquisition'];windows,selection=adapter_spec(spec)
    lookup=NativeThreadLookup(Path(spec['state_path']),Path(spec['session_root']),spec['owner_thread'],
        lambda: (service.guard(deadline) or True),allowed_threads=tuple(dict.fromkeys(w.source.thread_id for w in windows)),
        deadline=deadline)
    adapter=RevisionInputAdapter(service,lookup,windows,selection,spec['original_save_key'],deadline,
        expected_capsule_sha=case['input_sha'],expected_source_sha=case['source_sha'],
        source_review=source_review)
    return adapter


def reopen_adapter(service,record,case,deadline,*,source_review=None):
    adapter=restore_adapter(service,record,case,deadline,source_review=source_review)
    observed=adapter.inspect()
    if asdict(observed.original)!=record['original'] or observed.derived!=record['derived']:hold()
    return adapter
