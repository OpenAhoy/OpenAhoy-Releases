"""Fixed local review chain and current source/input qualification.

JSON remains non-authoritative; exact external review pins, live source streams,
all artifacts, original roots and the host's issued registry are jointly checked.
"""
import ast
from dataclasses import dataclass,field
from hashlib import sha256
import json
from pathlib import Path
import time
from weakref import WeakKeyDictionary

from .draft_group_runtime_host import (PinnedFile,FileSource,need,hold,canonical,digest,QualifiedGroupSource,
    TokenUseScope,GroupCurrentContext,BootstrapSourceInspection,_transaction_marker,_THREAD,OwnedConnection,OwnStore,_check_legacy_history_in,ExistingHistoryStoreView)
from .draft_group_input_files import _closed,_artifact,_human,_plain,_hash,_binding,_ref,decode
from .draft_group_native_source_observer import GroupNativeSourceObserver
from .draft_group_native_message_codec import pair_assistant_records
from .draft_revision_native_source import Record
from .draft_group_read_family_files import FamilyFiles
from .draft_group_read_family_store import original_root_scope,family_scope,prepared_binding,check_family_records_in,_states
from .draft_group_operator_semantics import is_operator, original_root_evidence, artifact_inventory, member_identities

CONFIG_KEYS=('schema','profile','authority','binding','registry_descriptor','role_source_descriptors','artifact_root_descriptors','semantic_adoption_sha','source_material_sha','original_root_evidence_sha','first_covenant_sha','read_contract_sha','candidate_scope','enabled_routes','source_review_policy')
SEMANTIC_KEYS=('schema','profile','authority','platform_account_sha','stable_owner','original_human_refs','original_text_set_sha','semantic_scope','role_assignments','qa_adoptions','artifact_inventory','original_root_evidence','read_contract_sha','source_rights_expiry')
REVIEW_KEYS=('schema','profile','authority','configuration_sha','semantic_adoption_sha','source_material_sha','artifact_inventory_sha','first_covenant_sha','read_contract_sha','candidate_scope','unarmed_sha','helper_dependencies','retention_evidence','permitted_arm')
ARM_KEYS=('schema','profile','authority','unarmed_sha','review_sha','armed_sha','ast_diff')
QA_KEYS=('member_identity','qa_thread_id','qa_turn_id','qa_message_id','raw_record_ref','typed_record_ref','pair_facts_sha','text_sha','task_complete_ref','qa_report_artifact','reviewed_artifact_set_sha','production_rule_sha','decision')
SCOPE_KEYS=('purpose','connection_binding_sha','permitted_routes','authorized_member_identities','qualify_subjects','execution_slots','required_read_purposes','forbidden_actions')
_INSPECTED_INPUTS=WeakKeyDictionary()


def _inspection_image(value):
    need(type(value) is dict and value.get('authority') is False
         and set(value)=={'authority','inventory_sha','members','artifacts','member_derivations'}
         and type(value.get('artifacts')) is tuple and type(value.get('member_derivations')) is tuple
         and all(type(raw) is str for raw in value['member_derivations']),'GROUP_SOURCE_INSPECTION_REQUIRED')
    artifacts=[]
    for item in value['artifacts']:
        need(type(item) is dict and type(item.get('raw')) is bytes,'GROUP_SOURCE_INSPECTION_REQUIRED')
        artifacts.append({'artifact':item['artifact'],'sha256':sha256(item['raw']).hexdigest(),'size':len(item['raw'])})
    pure={'inventory_sha':value['inventory_sha'],'members':value['members'],
          'member_derivations':list(value['member_derivations']),'artifacts':artifacts}
    _plain(pure);return canonical(pure)


def _json(raw,keys,profile):
    def unique(items):
        out={}
        for key,value in items:
            need(key not in out,'GROUP_HOST_JSON_DUPLICATE');out[key]=value
        return out
    need(type(raw) is bytes and 0<len(raw)<=2*1024*1024,'GROUP_HOST_JSON_BOUND')
    try:value=json.loads(raw,object_pairs_hook=unique,parse_constant=lambda _:hold('GROUP_HOST_JSON_NONFINITE'))
    except (ValueError,UnicodeError):hold('GROUP_HOST_JSON')
    _plain(value);_closed(value,keys)
    need(type(value['schema']) is int and value['schema']==1 and value['profile']==profile and value['authority'] is False,'GROUP_HOST_PROFILE')
    need(raw==(canonical(value)+'\n').encode(),'GROUP_HOST_CANONICAL')
    return value


def semantic_scope_sha(value):
    from . import draft_group_operator_source_codec as operator
    if type(value) is dict and value.get('profile')==operator.SEMANTIC_PROFILE:
        try:return operator.semantic_scope_sha(value)
        except operator.OperatorSourceCodecError:hold('GROUP_OPERATOR_SEMANTIC_SCOPE')
    return digest({'profile':'GROUP_SOURCE_SEMANTIC_SCOPE_V1',**{key:value[key] for key in
        ('platform_account_sha','stable_owner','original_human_refs','original_text_set_sha','semantic_scope','read_contract_sha','source_rights_expiry')}})


@dataclass(frozen=True)
class FixedHostPins:
    """Only the reviewed launcher constructs this private compiled table."""
    configuration_path: Path
    configuration_sha: str
    semantic_path: Path
    semantic_sha: str
    source_path: Path
    source_sha: str
    review_path: Path
    review_sha: str
    arm_receipt_path: Path
    arm_receipt_sha: str
    unarmed_path: Path
    unarmed_sha: str
    armed_path: Path
    armed_sha: str
    helper_files: tuple
    registrations: tuple
    lookups: tuple
    artifact_roots: tuple
    retention_evidence: tuple
    runtime_source_policy: tuple|None=None
    catalog_runtime_source: object=None


def _arm_ast(raw):
    try:tree=ast.parse(raw)
    except (SyntaxError,UnicodeError):hold('GROUP_HOST_ARM_AST')
    found={}
    for node in tree.body:
        if type(node) is ast.Assign and len(node.targets)==1 and type(node.targets[0]) is ast.Name and node.targets[0].id in ('REVIEW_PATH','REVIEW_SHA'):
            name=node.targets[0].id;need(name not in found,'GROUP_HOST_ARM_AST');found[name]=node.value;node.value=ast.Constant(None)
    need(set(found)=={'REVIEW_PATH','REVIEW_SHA'},'GROUP_HOST_ARM_AST')
    return ast.dump(tree,include_attributes=False),found


class FixedReviewChain:
    def __init__(self,pins,entry):
        need(type(pins) is FixedHostPins,'GROUP_HOST_FIXED_PINS_REQUIRED')
        self.pins,self.entry=pins,entry;self.files={}
        for role,path,checksum,maximum in (
            ('configuration',pins.configuration_path,pins.configuration_sha,2*1024*1024),
            ('semantic',pins.semantic_path,pins.semantic_sha,2*1024*1024),
            ('source',pins.source_path,pins.source_sha,2*1024*1024),
            ('review',pins.review_path,pins.review_sha,2*1024*1024),
            ('arm',pins.arm_receipt_path,pins.arm_receipt_sha,2*1024*1024),
            ('unarmed',pins.unarmed_path,pins.unarmed_sha,2*1024*1024),
            ('armed',pins.armed_path,pins.armed_sha,2*1024*1024)):
            self.files[role]=PinnedFile(path,checksum,maximum,pool=entry.pin_pool,owner=entry);entry.pins.append(self.files[role])
        self.helpers=[]
        for path,checksum in pins.helper_files+pins.retention_evidence:
            item=PinnedFile(path,checksum,2*1024*1024,pool=entry.pin_pool,owner=entry);self.helpers.append(item);entry.pins.append(item)
        self.config=_json(self.files['configuration'].raw,CONFIG_KEYS,'GROUP_HOST_CONFIGURATION_V1')
        entry.source_kind=self.config['binding']['source_kind']
        self.semantic=_json(self.files['semantic'].raw,SEMANTIC_KEYS,'HOST_GROUP_SEMANTIC_ADOPTION_V1')
        self.source=decode('source',self.files['source'].raw)
        if self.source['profile']=='GROUP_BATCH_NATIVE_SOURCE_BASELINE_V2':
            from .draft_group_native_v2_codec import decode_policy_acceptance
            from .draft_group_host_native_v2 import load_static_chain
            self.review=decode_policy_acceptance(self.files['review'].raw)
            load_static_chain(self)
        else:self.review=_json(self.files['review'].raw,REVIEW_KEYS,'GROUP_HOST_REVIEW_ACCEPTANCE_V1')
        self.arm=_json(self.files['arm'].raw,ARM_KEYS,'GROUP_HOST_ARM_RECEIPT_V1')
        self.check()
    def check(self):
        self.entry.held_pure()
        for item in self.files.values():item.check()
        for item in self.helpers:item.check()
        c,s,p=self.config,self.semantic,self.pins
        need((canonical(c)+'\n').encode()==self.files['configuration'].raw and (canonical(s)+'\n').encode()==self.files['semantic'].raw,'GROUP_HOST_MATERIAL_OBJECT_CHANGED')
        _check_descriptors(self)
        need(c['semantic_adoption_sha']==p.semantic_sha and c['source_material_sha']==p.source_sha,'GROUP_HOST_REVIEW_BINDING')
        from .publication_contract import stable_account
        need(s['platform_account_sha']==stable_account(self.entry.policy.data) and s['stable_owner']=={'tenant':self.entry.policy.actor.tenant_id,'principal':self.entry.policy.actor.principal_id},'GROUP_HOST_SEMANTIC_ACCOUNT')
        _binding(c['binding']);need(canonical(c['binding'])==canonical(prepared_binding(self.entry.policy,c['binding']['source_kind'])),'GROUP_HOST_ACCOUNT_BINDING')
        _closed(s['semantic_scope'],SCOPE_KEYS)
        need(s['semantic_scope']['purpose']=='GROUP08_SAME_REQUEST'
             and s['semantic_scope']['connection_binding_sha']==digest(c['binding'])
             and c['enabled_routes']==s['semantic_scope']['permitted_routes'],'GROUP_HOST_SEMANTIC_SCOPE')
        forbidden=s['semantic_scope']['forbidden_actions']
        need(type(forbidden) is list and {'publish','masssend','unsupported_settings'}<=set(forbidden),'GROUP_HOST_FORBIDDEN_ACTIONS')
        need(c['source_review_policy']=='EXACT_FAMILY_COMMITTED_REVIEW_CHAIN_V1','GROUP_HOST_SOURCE_REVIEW_POLICY')
        need(self.source['semantic_scope_sha']==semantic_scope_sha(s),'GROUP_HOST_SEMANTIC_SHA')
        need(digest(s['original_root_evidence'])==c['original_root_evidence_sha'],'GROUP_HOST_ROOT_EVIDENCE')
        for ref in s['original_human_refs']:_human(ref)
        for artifact in s['artifact_inventory']:_artifact(artifact)
        review=self.review
        need(type(review) is dict and review.get('profile')==('GROUP_HOST_RUNTIME_POLICY_ACCEPTANCE_V1' if self.source['profile']=='GROUP_BATCH_NATIVE_SOURCE_BASELINE_V2' else 'GROUP_HOST_REVIEW_ACCEPTANCE_V1') and review.get('authority') is False,'GROUP_HOST_REVIEW_REQUIRED')
        expected={'configuration_sha':p.configuration_sha,'semantic_adoption_sha':p.semantic_sha,'source_material_sha':p.source_sha,
            'artifact_inventory_sha':digest(s['artifact_inventory']),'first_covenant_sha':c['first_covenant_sha'],'read_contract_sha':c['read_contract_sha'],'candidate_scope':c['candidate_scope'],'unarmed_sha':p.unarmed_sha,
            'helper_dependencies':[[str(x),h] for x,h in p.helper_files]}
        for key,value in expected.items():need(review.get(key)==value,'GROUP_HOST_REVIEW_BINDING')
        need(review.get('permitted_arm')=={'REVIEW_PATH':str(p.review_path),'REVIEW_SHA':'FIXED_REVIEW_BYTES_SHA256'},'GROUP_HOST_ARM_REVIEW')
        before,unarmed=_arm_ast(self.files['unarmed'].raw);after,armed=_arm_ast(self.files['armed'].raw)
        need(before==after and all(type(v) is ast.Constant and v.value is None for v in unarmed.values()),'GROUP_HOST_ARM_AST')
        need(all(type(v) is ast.Constant for v in armed.values()) and armed['REVIEW_PATH'].value==str(p.review_path)
             and armed['REVIEW_SHA'].value==p.review_sha,'GROUP_HOST_ARM_AST')
        need(self.arm.get('profile')=='GROUP_HOST_ARM_RECEIPT_V1' and self.arm.get('authority') is False
             and self.arm.get('unarmed_sha')==p.unarmed_sha and self.arm.get('review_sha')==p.review_sha
             and self.arm.get('armed_sha')==p.armed_sha and self.arm.get('ast_diff')==['REVIEW_PATH','REVIEW_SHA'],'GROUP_HOST_ARM_RECEIPT')
        need(type(p.retention_evidence) is tuple and len(p.retention_evidence)>0,'HOLD_QA_RETENTION_UNPROVEN')
        need(review.get('retention_evidence')==[[str(x),h] for x,h in p.retention_evidence],'HOLD_QA_RETENTION_UNPROVEN')
        expiry=s['source_rights_expiry'];_closed(expiry,('kind','not_after'))
        need(expiry['kind'] in ('PERSISTENT_DELEGATION','EXPLICIT_UNTIL'),'GROUP_HOST_SOURCE_EXPIRY')
        if expiry['kind']=='PERSISTENT_DELEGATION':need(expiry['not_after'] is None,'GROUP_HOST_SOURCE_EXPIRY')
        else:need(type(expiry['not_after']) is int and time.time()*1000<expiry['not_after'],'GROUP_HOST_SOURCE_EXPIRED')
        if self.source['profile']=='GROUP_BATCH_NATIVE_SOURCE_BASELINE_V2':
            from .draft_group_host_native_v2 import check_static_chain
            check_static_chain(self)
        return True


def _check_descriptors(chain):
    c=chain.config;p=chain.pins;policy=chain.entry.policy;material=chain.source
    registry=Path(policy.value['registry_path']);info=registry.stat(follow_symlinks=False);parent=registry.parent.stat(follow_symlinks=False)
    _closed(c['registry_descriptor'],('registry_id','path_utf8_sha256','device','inode','parent_device','parent_inode'))
    need(c['registry_descriptor']=={'registry_id':'own-connections','path_utf8_sha256':sha256(str(registry).encode()).hexdigest(),
        'device':info.st_dev,'inode':info.st_ino,'parent_device':parent.st_dev,'parent_inode':parent.st_ino},'GROUP_HOST_REGISTRY_DESCRIPTOR')
    if material['profile']=='GROUP_BATCH_NATIVE_SOURCE_BASELINE_V2':
        from .draft_group_host_native_v2 import static_role_descriptors
        need(c['role_source_descriptors']==static_role_descriptors(chain),'GROUP_HOST_FULL_SOURCE_DESCRIPTOR')
    else:
        expected=[]
        for role in material['role_threads']:
            matches=[r for r in p.registrations if r.thread_id==role['thread_id']]
            need(len(matches)==1,'GROUP_HOST_ROLE_SOURCE');source=matches[0]
            lookup=[l for l in p.lookups if source.thread_id in l.allowed_threads];need(len(lookup)==1,'GROUP_HOST_ROLE_OWNER');lookup=lookup[0]
            window=[w for w in material['source_windows'] if w['source_id']==source.source_id];need(len(window)==1,'GROUP_HOST_ROLE_WINDOW')
            registered={key:getattr(source,key) for key in ('source_id','device','inode','thread_id','start_offset','start_ordinal','preceding_sha256','session_meta_sha256','metadata_ordinal')}
            registered['path_utf8_sha256']=sha256(str(source.path).encode()).hexdigest()
            expected.append({**role,'owner_thread':lookup.owner_thread,'lookup_state_path_sha256':sha256(str(lookup.state_path).encode()).hexdigest(),
                'lookup_root_path_sha256':sha256(str(lookup.session_root).encode()).hexdigest(),'registered_source':registered,'source_window':window[0]})
        need(c['role_source_descriptors']==expected,'GROUP_HOST_FULL_SOURCE_DESCRIPTOR')
    roots=[]
    for checksum,path in p.artifact_roots:
        info=path.stat(follow_symlinks=False)
        roots.append({'root_sha':checksum,'path_utf8_sha256':sha256(str(path).encode()).hexdigest(),'device':info.st_dev,'inode':info.st_ino})
    need(c['artifact_root_descriptors']==roots,'GROUP_HOST_ARTIFACT_ROOT_DESCRIPTOR')


def _check_role_workspaces(host):
    assignments=host.chain.semantic['role_assignments'];expected=[];records=_records(host.observer)
    for role in host.chain.source['role_threads']:
        registrations=host.observer.registrations if host.chain.source['profile']=='GROUP_BATCH_NATIVE_SOURCE_BASELINE_V2' else host.pins.registrations
        registration=next(r for r in registrations if r.thread_id==role['thread_id'])
        meta=[r for r in records.values() if r.source_id==registration.source_id and r.value['type']=='session_meta']
        need(len(meta)==1,'GROUP_HOST_ROLE_METADATA');cwd=meta[0].value['payload'].get('cwd')
        need(type(cwd) is str and Path(cwd).is_absolute(),'GROUP_ROLE_WORKSPACE_UNPROVEN')
        lookup=next(l for l in host.pins.lookups if role['thread_id'] in l.allowed_threads)
        expected.append({**role,'owner_thread':lookup.owner_thread,'workspace_sha':sha256(cwd.encode()).hexdigest()})
    need(assignments==expected,'GROUP_HOST_ROLE_WORKSPACE_CHANGED')


class GroupInputAdapter:
    def __init__(self,host):
        self.host=host;self.original={};self.pinned={}
        roots=host.pins.artifact_roots
        need(type(roots) is tuple and all(type(x) is tuple and len(x)==2 for x in roots),'GROUP_HOST_ARTIFACT_ROOTS')
        self.roots=dict(roots)
        self.derived_cache=None
        if is_operator(host):
            from .draft_group_pure_derived_cache import EntryDerivedCache
            self.derived_cache=EntryDerivedCache(host.entry,host.chain.config['candidate_scope'],
                (GroupInputAdapter.inspect_in.__code__,))
            host.entry.stack.callback(self.derived_cache.close)
    def inspect_in(self,db_or_ro_snapshot,source_witness):
        h=self.host;h.entry.full_guard();h.chain.check();values=[];derivations=[]
        inventory=artifact_inventory(h)
        need(type(inventory) is list and len(inventory)>0,'GROUP_HOST_ARTIFACTS_REQUIRED')
        selection=h.entry.artifact_resources.selection(inventory,self.roots)
        for artifact_index,spec in enumerate(inventory):
            _artifact(spec);root=self.roots.get(spec['root_sha']);need(type(root) is type(Path('/')),'GROUP_HOST_ARTIFACT_ROOT')
            if self.derived_cache is not None:
                key=(spec['root_sha'],spec['relative_path'])
                _derived_budget(h,spec['size']*(1 if key in self.pinned else 2))
            source=FileSource(root)
            raw=source.read_html(spec['relative_path']) if spec['media_type']=='text/html' else source.read(spec['relative_path'])
            need(len(raw)==spec['size'] and sha256(raw).hexdigest()==spec['sha256'],'GROUP_HOST_ARTIFACT_CHANGED')
            key=(spec['root_sha'],spec['relative_path'])
            if key not in self.pinned:
                pin=h.entry.artifact_resources.acquire(selection,artifact_index,4*1024*1024 if spec['media_type']=='text/html' else 2*1024*1024)
                self.pinned[key]=pin;h.entry.pins.append(pin)
            else:self.pinned[key].check()
            if self.derived_cache is not None:
                held=self.pinned[key].raw
                need(held==raw,'GROUP_HOST_ARTIFACT_CHANGED')
                raw=held  # original and inspection share the actual held bytes.
            if key in self.original:need(self.original[key]==raw,'GROUP_HOST_ARTIFACT_REBASE')
            else:self.original[key]=raw
            values.append({'artifact':spec,'raw':raw})
        # Every image's actual transport must itself be explicitly reviewed.
        reports=[json.loads(v['raw']) for v in values if v['artifact']['media_type']=='application/json']
        members=member_identities(h)
        for member in members:
            match=[r for r in reports if type(r) is dict and r.get('member_identity')==member]
            need(len(match)==1,'GROUP_HOST_MEMBER_INPUT_REQUIRED');report=match[0]
            required={'title','author','digest','cover_crop','comments','originality','html','source_images','transport_images','upload_mapping'}
            need(required<=set(report),'GROUP_HOST_SETTING_INTENT_REQUIRED')
            need(type(report['originality']) is bool and type(report['comments']) is dict,'GROUP_HOST_SETTING_INTENT_REQUIRED')
            bysha={v['artifact']['sha256']:v for v in values}
            need(report['html'] in bysha and bysha[report['html']]['artifact']['media_type']=='text/html','GROUP_HOST_HTML_REQUIRED')
            for checksum in report['source_images']+report['transport_images']:need(checksum in bysha,'GROUP_HOST_IMAGE_REQUIRED')
            for checksum in report['transport_images']:need(len(bysha[checksum]['raw'])<1000000,'GROUP_HOST_TRANSPORT_IMAGE_BOUND')
            need(type(report['upload_mapping']) is list,'GROUP_HOST_UPLOAD_MAP_REQUIRED')
            # Re-run the actual importer and image decoders against the exact
            # source/transport bytes. Only the fixed vendor ImageIO leaf can
            # decode JPEG; its scratch directory stays under this account root.
            from .local_html_import import convert,with_transports
            from .import_images import decode as decode_image
            import tempfile
            source_images=[{'mime':bysha[x]['artifact']['media_type'],'raw':bysha[x]['raw']} for x in report['source_images']]
            def derive():
                normalized=convert(bysha[report['html']]['raw'],source_images,metadata_title=report['title'],layout_profile=report.get('layout_profile','source'))
                need(len(normalized['images'])==len(report['transport_images']),'GROUP_HOST_TRANSPORT_IMAGE_BINDING')
                with tempfile.TemporaryDirectory(prefix='group-source-image-',dir=h.entry.policy.root) as scratch:
                    normalized['image_decode_checks']=[decode_image(x['raw'],x['mime'],scratch).fingerprint() for x in source_images]
                    transports={image['slot']:(bysha[checksum]['artifact']['media_type'],bysha[checksum]['raw'])
                        for image,checksum in zip(normalized['images'],report['transport_images'])}
                    derived=with_transports(normalized,transports,scratch)
                return {key:derived[key] for key in ('title','fragment','provenance')}
            if self.derived_cache is None:
                derived=derive()
            else:
                report_raw=[v['raw'] for v in values if v['artifact']['media_type']=='application/json'
                    and json.loads(v['raw'])==report]
                need(len(report_raw)==1,'GROUP_HOST_MEMBER_INPUT_REQUIRED')
                inputs=(('report','application/json',report_raw[0]),
                    ('html','text/html',bysha[report['html']]['raw']))+tuple(
                    ('source:'+str(i),bysha[x]['artifact']['media_type'],bysha[x]['raw'])
                    for i,x in enumerate(report['source_images']))+tuple(
                    ('transport:'+str(i),bysha[x]['artifact']['media_type'],bysha[x]['raw'])
                    for i,x in enumerate(report['transport_images']))
                def fence():
                    h.entry.full_guard();h.chain.check();self.pure_fence()
                derived=self.derived_cache.resolve(h.entry,digest(member),inputs,
                    {'title':report['title'],'layout_profile':report.get('layout_profile','source')},
                    code_scope=h.chain.config['candidate_scope'],
                    code_token=(GroupInputAdapter.inspect_in.__code__,),fence=fence,
                    reserve=lambda extra:_derived_budget(h,extra),derive=derive)
            if 'normalized_fragment_sha' in report:need(sha256(derived['fragment'].encode()).hexdigest()==report['normalized_fragment_sha'],'GROUP_HOST_NORMALIZATION_CHANGED')
            if 'transform_sha' in report:need(derived['provenance']['transform_sha256']==report['transform_sha'],'GROUP_HOST_TRANSFORM_CHANGED')
            report_rows=[v for v in values if v['artifact']['media_type']=='application/json' and json.loads(v['raw'])==report]
            need(len(report_rows)==1,'GROUP_HOST_MEMBER_INPUT_REQUIRED')
            operator_fields={}
            if is_operator(h):
                from .draft_group_operator_source_codec import CONTENT_SOURCE_TYPE
                from .draft_group_input_files import _id
                _id(report.get('source_article_id'))
                operator_fields={'content_source_type':CONTENT_SOURCE_TYPE,'source_article_id':report['source_article_id']}
            derivations.append(canonical({'member_identity':member,'report_artifact_sha':report_rows[0]['artifact']['sha256'],
                'html_artifact_sha':report['html'],'title':derived['title'],'fragment':derived['fragment'],
                'provenance':derived['provenance'],'report':report,**operator_fields}))
        h.entry.full_guard();result={'authority':False,'inventory_sha':digest(inventory),'members':json.loads(canonical(members)),
            'artifacts':tuple(values),'member_derivations':tuple(derivations)}
        _INSPECTED_INPUTS[self]=(result,_inspection_image(result),None)
        return result
    def validate_qualified_inspection(self,value):
        pin=_INSPECTED_INPUTS.get(self)
        need(pin is not None and pin[0] is value and pin[1]==_inspection_image(value)
             and pin[2] is not None,'GROUP_SOURCE_INSPECTION_UNISSUED')
        if self.host.chain.source['profile']=='GROUP_BATCH_NATIVE_SOURCE_BASELINE_V2':
            from .draft_group_host_native_v2 import validate_inspection
            validate_inspection(self.host,value,pin[2])
        elif is_operator(self.host):
            from .draft_group_host_operator import validate_inspection
            validate_inspection(self.host,value,pin[2])
        else:need(self.host._source is not None and pin[2]==self.host._source.facts_sha,'GROUP_SOURCE_INSPECTION_UNISSUED')
        self.pure_fence();return None
    def pure_fence(self):
        for pin in self.pinned.values():pin.check()


def _derived_budget(host,extra=0):
    from .draft_group_pin_resources import MAX_RAW_BYTES
    from .draft_group_artifact_resources import _QUOTA
    cache=host.adapter.derived_cache
    retained=0 if cache is None else cache.retained_bytes
    # Include the already-existing raw owners. No new FD or pixel raster stays.
    total=host.entry.pin_pool.raw_bytes+_QUOTA.snapshot()['raw']+retained+extra
    from .draft_group_host_operator import _QA
    for resources,(owner,entry) in tuple(_QA.items()):
        if owner is host:
            total+=resources.pool.raw_bytes+resources.evidence_bytes
            if resources.active_files is not None:
                total+=resources.active_files.pool.raw_bytes+resources.active_files.evidence_bytes
    if total>MAX_RAW_BYTES and retained>0:
        cache.clear();total-=retained
    need(total<=MAX_RAW_BYTES,'GROUP_DERIVED_RAW_BOUND')


def _records(observer):
    if type(observer).__module__=='wce.draft_group_native_v2_stream':
        from .draft_group_native_v2_stream import GroupNativeV2SourceObserver
        need(type(observer)is GroupNativeV2SourceObserver,'GROUP_HOST_NATIVE_RECORD')
        out={}
        for record in GroupNativeV2SourceObserver.retained_records(observer):
            need(type(record)is Record,'GROUP_HOST_NATIVE_RECORD')
            key=canonical(record.reference());need(key not in out,'GROUP_HOST_NATIVE_DUPLICATE');out[key]=record
        return out
    out={}
    for observed in observer._entry._observations:
        for record in observed.records:
            need(type(record) is Record,'GROUP_HOST_NATIVE_RECORD')
            key=canonical(record.reference());need(key not in out,'GROUP_HOST_NATIVE_DUPLICATE');out[key]=record
    return out


def _qualify_qa(host,facts,current):
    s=host.chain.semantic;records=_records(host.observer);paired=facts['assistant_facts'];inventory=current['inventory_sha']
    reviewed={canonical(v['reference']) for v in facts['inventory']}
    for qa in s['qa_adoptions']:
        _closed(qa,QA_KEYS);need(qa['decision']=='ADOPT_CURRENT_ARTIFACTS','HOLD_QA_ARTIFACT_BINDING')
        need(qa['reviewed_artifact_set_sha']==inventory,'HOLD_QA_ARTIFACT_BINDING')
        for key in ('raw_record_ref','typed_record_ref','task_complete_ref'):_ref(qa[key]);need(canonical(qa[key]) in reviewed,'HOLD_QA_RETENTION_UNPROVEN')
        raw=records.get(canonical(qa['raw_record_ref']));typed=records.get(canonical(qa['typed_record_ref']));terminal=records.get(canonical(qa['task_complete_ref']))
        need(raw is not None and typed is not None and terminal is not None,'HOLD_QA_RETENTION_UNPROVEN')
        pair=pair_assistant_records(raw,typed,thread_id=qa['qa_thread_id'])
        need(pair['turn_id']==qa['qa_turn_id'] and pair['message_id']==qa['qa_message_id'] and digest(pair)==qa['pair_facts_sha']
             and sha256(''.join(pair['text_parts']).encode()).hexdigest()==qa['text_sha'],'HOLD_QA_PAIR_UNSUPPORTED')
        need(any(v['raw']==qa['raw_record_ref'] and v['typed']==qa['typed_record_ref'] and v['material_category']=='QA_FACT' for v in paired),'HOLD_QA_PAIR_UNSUPPORTED')
        row=terminal.value;payload=row['payload']
        need(row['type']=='event_msg' and payload.get('type')=='task_complete' and payload.get('turn_id')==qa['qa_turn_id']
             and terminal.source_id==raw.source_id==typed.source_id and terminal.byte_start>=max(raw.byte_end,typed.byte_end),'HOLD_QA_TASK_INCOMPLETE')
        for record in records.values():
            p=record.value['payload']
            need(not(record.source_id==raw.source_id and p.get('turn_id')==qa['qa_turn_id'] and p.get('type')=='turn_aborted'),'HOLD_QA_TASK_ABORTED')
        report=[v for v in current['artifacts'] if v['artifact']==qa['qa_report_artifact']]
        need(len(report)==1 and sha256(report[0]['raw']).hexdigest()==qa['qa_report_artifact']['sha256'],'HOLD_QA_REPORT_REQUIRED')
        # The reviewed report and original production-rule artifact are exact bytes,
        # not a PASS substring. External acceptance binds their actual interpretation.
        need(any(v['artifact']['sha256']==qa['production_rule_sha'] for v in current['artifacts']),'HOLD_QA_RULE_REQUIRED')
    need(len(s['qa_adoptions'])==len(s['semantic_scope']['authorized_member_identities']),'HOLD_QA_ARTIFACT_BINDING')
    pin=_INSPECTED_INPUTS.get(host.adapter)
    need(pin is not None and pin[0] is current and pin[1]==_inspection_image(current),'GROUP_SOURCE_INSPECTION_UNISSUED')
    _INSPECTED_INPUTS[host.adapter]=(current,pin[1],digest(facts))


class GroupRuntimeHost:
    def __init__(self,entry,pins):
        self.entry,self.pins=entry,pins;entry.held_pure()
        from .draft_group_operator_review_chain import FixedOperatorHostPins,FixedOperatorReviewChain
        self.chain=FixedOperatorReviewChain(pins,entry) if type(pins) is FixedOperatorHostPins else FixedReviewChain(pins,entry)
        self.observer=None if self.chain.source['profile']=='GROUP_BATCH_NATIVE_SOURCE_BASELINE_V2' or is_operator(self) else GroupNativeSourceObserver(self.chain.files['source'].raw,pins.registrations,pins.lookups,
            binding_sha=digest(self.chain.config['binding']),full=entry.full_guard,loop=entry.loop_guard)
        entry.observer=self.observer;self.adapter=GroupInputAdapter(self);self._source=None;self._busy=False
    def qualify_current_group_source(self,initial=False):
        if is_operator(self):
            from .draft_group_host_operator import qualify_local_source
            return qualify_local_source(self,initial=initial)
        if self.chain.source['profile']=='GROUP_BATCH_NATIVE_SOURCE_BASELINE_V2':
            from .draft_group_host_native_v2 import qualify_local_source
            return qualify_local_source(self,initial=initial)
        need(not self._busy,'GROUP_HOST_REENTRANT');self._busy=True
        try:
            self.entry.full_guard();self.chain.check();facts=self.observer.inspect(self.chain.files['source'].raw).value
            actual=[{k:v[k] for k in ('thread_id','turn_id','message_id','text_sha256')} for v in facts['users'] if v['disposition']=='ORIGINAL_REQUEST']
            need(actual==self.chain.semantic['original_human_refs'],'GROUP_HOST_HUMAN_SCOPE')
            texts=[v['text'] for v in facts['users'] if v['disposition']=='ORIGINAL_REQUEST']
            need(digest(texts)==self.chain.semantic['original_text_set_sha'],'GROUP_HOST_HUMAN_TEXT')
            _check_role_workspaces(self);current=self.adapter.inspect_in(None,facts);_qualify_qa(self,facts,current)
            self.observer.prepare_release(self.chain.files['source'].raw);self.pure_release_fence()
            rights_until_ms=self.chain.semantic['source_rights_expiry']['not_after']
            expiry=min(rights_until_ms/1000 if rights_until_ms is not None else float('inf'),self.chain.source['expires_policy']['not_after'])
            source_type=BootstrapSourceInspection if self.entry.pre_storage else QualifiedGroupSource
            value=source_type(self,self.entry,digest(facts),semantic_scope_sha(self.chain.semantic),expiry)
            self.entry.issued[id(value)]=value;self._source=value;return value
        except BaseException:
            self.entry.poisoned=True;raise
        finally:self._busy=False
    def validate_history_in(self,db, *, history_locators=None):
        self.entry.full_guard();c=self.chain.config;policy=self.entry.policy;kind=c['binding']['source_kind']
        need(type(db) is OwnedConnection and db.in_transaction,'GROUP_HOST_OWNED_TRANSACTION')
        from .draft_group_history_context import require_history
        require_history(policy,db,history_locators)
        from .draft_group_read_family_store import _ROOT_CURRENT,_RootClosure
        original=original_root_evidence(self);active=_ROOT_CURRENT.get()
        if type(active) is _RootClosure and active.active and active.db is db:
            need(active.files.policy is policy and active.history_locators is history_locators and active.source_kind==kind and active.origin_raw==canonical(original).encode(),'GROUP_HOST_ROOT_CONTEXT_CHANGED')
            # Reuse this caller's exact live RootClosure. A nested closure would
            # invalidate the surrounding Family scope while its original event
            # is being checked, so it is neither an optimization nor a new seal.
            active.current()
            _check_legacy_history_in(db,kind,ExistingHistoryStoreView(policy.root/'state.sqlite3',policy), history=history_locators)
        else:
            files=FamilyFiles(policy,self.entry.loop_guard)
            with original_root_scope(db,files,original,source_kind=kind, history_locators=history_locators) as closure:
                _check_legacy_history_in(db,kind,ExistingHistoryStoreView(policy.root/'state.sqlite3',policy), history=history_locators)
                with family_scope(db,files,closure):check_family_records_in(db,_states(db),policy,files=files)
        self.entry.full_guard()
    def current_no_token_in(self,db,source,*,token_use=None,initial=False, history_locators=None):
        if is_operator(self):
            from .draft_group_host_operator import current_no_token_in
            return current_no_token_in(self,db,source,token_use=token_use,initial=initial,history_locators=history_locators)
        if self.chain.source['profile']=='GROUP_BATCH_NATIVE_SOURCE_BASELINE_V2':
            from .draft_group_host_native_v2 import current_no_token_in
            return current_no_token_in(self,db,source,token_use=token_use,initial=initial, history_locators=history_locators)
        self.entry.full_guard();need((type(source) is QualifiedGroupSource or (type(source) is BootstrapSourceInspection and initial and self.entry.pre_storage)) and source.host is self and source.entry is self.entry
            and self.entry.issued.get(id(source)) is source,'GROUP_HOST_SOURCE_UNISSUED')
        self.chain.check();facts=self.observer.inspect(self.chain.files['source'].raw).value
        need(digest(facts)==source.facts_sha,'GROUP_HOST_SOURCE_CHANGED')
        _check_role_workspaces(self);current=self.adapter.inspect_in(db,facts);_qualify_qa(self,facts,current)
        if db is not None:
            self.validate_history_in(db, history_locators=history_locators)
            if token_use is not None or getattr(self,'_active_group_token',None) is not None:self.validate_original_uploads_in(db,current, history_locators=history_locators)
        if token_use is not None:need(type(token_use) is TokenUseScope and token_use.source is source and self.entry.issued.get(id(token_use)) is token_use,'GROUP_TOKEN_USE_UNISSUED')
        self.observer.prepare_release(self.chain.files['source'].raw)
        self.entry.full_guard();return current
    def pure_release_fence(self):
        self.entry.held_pure();self.adapter.pure_fence()
        for pin in self.entry.pins:pin.check()
        for receipt in getattr(self,'_source_upload_receipts',{}).values():receipt.collective_fence()
        if self.observer is not None:self.observer.pure_release_fence()
        self.entry.held_pure()
    def current_context_in(self,db,source,token_use=None, *, history_locators=None):
        need(not self.entry.pre_storage and self.entry.listener_bound,'GROUP_COMPLETE_LISTENER_REQUIRED')
        self.current_no_token_in(db,source,token_use=token_use, history_locators=history_locators)
        need(type(db) is OwnedConnection and _transaction_marker(db) is not None,'GROUP_HOST_OWNED_TRANSACTION')
        c=self.chain.config;s=self.chain.semantic;use=token_use
        value=GroupCurrentContext(self.entry.id,_THREAD(),db,_transaction_marker(db),digest(c['binding']),s['platform_account_sha'],
            digest({'credential_scope':self.entry.policy.data}),source.facts_sha,s['source_rights_expiry'],source.semantic_scope_sha,
            use.family_id if use else '',use.registration_id if use else '',use.purpose_instance_id if use else '',use.phase if use else '',self,source,use)
        self.entry.issued[id(value)]=value;return value
    def verify_in(self,db,action,binding_sha,details, *, history_locators=None):
        candidate=details.get('candidate') if type(details) is dict else None
        effect_action=action in ('PREVIEW_READ','GET_CLAIM','DELETE_CLAIM','ADD_ADMIT','POOL_REGISTER',
            'COVERAGE_REFRESH','PLAN_EXACT_PARENT','SWITCH','COMPLETE')
        effect_profile=action=='PREVIEW'and type(candidate)is dict and candidate.get('profile')in (
            'GROUP_TOKEN_ACQUISITION_CLAIM_V1','GROUP_TOKEN_POST_ARMED_V1','GROUP_TARGET_DESIGNATION_V1',
            'GROUP_INPUT_ADOPTION_V1','GROUP_QUALIFIED_PARENT_GRANT_V1')
        if self.chain.config['binding']['source_kind']=='SYNTHETIC_SETUP'and (effect_action or effect_profile):
            from .draft_group_rich_syn_fixture import require_rich_syn_domain_for_entry
            require_rich_syn_domain_for_entry(self.entry)
        if action in ('PREVIEW_READ_RESULT','GET_RESULT','DELETE_RESULT','ADD_RESULT','ADD_UNKNOWN'):
            hold('GROUP_ARCHIVED_RESULT_VERIFIER_REQUIRED')
        if action=='PREVIEW' and type(candidate) is dict and candidate.get('profile') in ('GROUP_CURRENT_SOURCE_REVIEW_OPERATOR_V1',_operator_time_v2.SOURCE_REVIEW_PROFILE_V2):
            from .draft_group_operator_review import validate_append_scope
            validate_append_scope(self,db,candidate)
            return True
        if action=='PREVIEW'and type(candidate)is dict and candidate.get('profile')=='GROUP_CURRENT_SOURCE_REVIEW_V2':
            from .draft_group_source_review import validate_source_review_v2_append_scope
            validate_source_review_v2_append_scope(self,db,candidate)
            return True
        if action=='PREVIEW' and type(candidate) is dict:
            from .draft_group_runtime_host import _HISTORY_ISSUED
            receipt=next((value for value in _HISTORY_ISSUED.values() if value[1] is db and value[3]==canonical(candidate)),None)
            if receipt is not None:
                need(candidate['profile'] in ('GROUP_TOKEN_OUTCOME_V1','GROUP_TOKEN_CACHE_PUBLISHED_V1'),'GROUP_HISTORY_WRITE_PROFILE')
                self.validate_history_in_minimal(db,history_locators=history_locators);return True
        if self.chain.source['profile']=='GROUP_BATCH_NATIVE_SOURCE_BASELINE_V2':
            from .draft_group_host_native_v2 import _binding,verify_local_family_append_in
            _,phase=_binding(self)
            local_profile=type(candidate)is dict and candidate.get('profile')in ('GROUP_READ_FAMILY_ROOT_V1','GROUP_READ_PURPOSE_ACTIVATION_V1')
            if phase=='COMPLETE_SERVICE_NO_ADMISSION'and ((action=='PREVIEW'and local_profile)or action=='PREVIEW_GRANT'):
                verify_local_family_append_in(self,db,action,binding_sha,details, history_locators=history_locators)
                return True
        if is_operator(self):
            from .draft_group_host_operator import binding_for_host,current_binding_phase,verify_local_family_append_in
            binding=binding_for_host(self,None)
            phase=current_binding_phase(self,binding)
            local_profile=type(candidate) is dict and candidate.get('profile') in ('GROUP_READ_FAMILY_ROOT_V1','GROUP_READ_PURPOSE_ACTIVATION_V1')
            if phase=='COMPLETE_SERVICE_NO_ADMISSION' and ((action=='PREVIEW' and local_profile) or action=='PREVIEW_GRANT'):
                verify_local_family_append_in(self,db,action,binding_sha,details,history_locators=history_locators)
                return True
        target_scope=getattr(self.entry,'target_scope',None)
        if action=='PREVIEW' and type(candidate) is dict and candidate.get('profile')=='GROUP_TARGET_DESIGNATION_V1':
            from .draft_group_target_scope import TargetPreparationScope,validate_target_preparation_scope
            need(type(target_scope) is TargetPreparationScope and target_scope.phase in ('READY','INSERT_REQUIRED')
                 and canonical(candidate)==canonical(target_scope.designation),'GROUP_TARGET_DESIGNATION_UNISSUED')
            validate_target_preparation_scope(target_scope,self.entry.service.workflow,db,candidate['operation_id'])
            return True
        need(self._source is not None and binding_sha==digest(self.chain.config['binding']),'GROUP_HOST_BINDING')
        self.current_no_token_in(db,self._source, history_locators=history_locators)
        if action=='PREVIEW' and type(candidate) is dict and candidate.get('profile') in (
                'GROUP_INPUT_ADOPTION_V1','GROUP_QUALIFIED_PARENT_GRANT_V1'):
            from .draft_group_parent_issuer import validate_parent_append_in
            kind='ADOPTION' if candidate['profile']=='GROUP_INPUT_ADOPTION_V1' else 'PARENT'
            validate_parent_append_in(self,db,kind,candidate,history_locators=history_locators)
            self.pure_release_fence();return True
        if action=='PLAN_EXACT_PARENT':
            from .draft_group_parent_issuer import validate_parent_plan_in
            validate_parent_plan_in(self,db,details,history_locators=history_locators)
            self.pure_release_fence();return True
        if action in ('POOL_REGISTER','COVERAGE_REFRESH'):
            from .draft_group_pool_issuer import validate_pool_transition_in
            validate_pool_transition_in(self,db,action,details, history_locators=history_locators)
            return True
        if action in ('SWITCH','COMPLETE'):
            from .draft_group_local_transition import validate_local_transition_in
            validate_local_transition_in(self,db,action,details, history_locators=history_locators)
            return True
        if action=='PREVIEW_SUBJECTS':
            from .draft_group_coverage import validate_discovery_subjects_in
            validate_discovery_subjects_in(self,db,details, history_locators=history_locators)
            self.pure_release_fence();return True
        if action=='PREVIEW_GRANT':
            from .draft_group_read_family_store import _registration
            info=self._family_in(db, history_locators=history_locators)
            allowed=[p for p in info['covenant']['purposes'] if p['source_grant_sha']==details['source_grant_sha']]
            need(len(allowed)==1 and allowed[0]['source_grant_sha'] in info['activations']
                 and canonical(_registration(allowed[0],info['covenant']))==canonical(details),'GROUP_PREVIEW_GRANT_UNISSUED')
            self.pure_release_fence();return True
        if action in ('PREVIEW_READ','GET_CLAIM','DELETE_CLAIM','ADD_ADMIT'):
            matches=[]
            for ctx,packed in getattr(self.entry,'source_candidates',{}).values():
                if ctx.db is not db:continue
                fact=json.loads(packed);selector=fact['claim_selector']
                if action=='PREVIEW_READ':
                    match=selector['ledger_kind']=='PREVIEW' and fact['gid']==details.get('grant_id') and selector['api']==details.get('api') and selector['request_sha']==details.get('request_sha')
                else:
                    api={'GET_CLAIM':'GET','DELETE_CLAIM':'DELETE','ADD_ADMIT':'ADD'}[action]
                    match=selector['ledger_kind']=='CHILD' and fact['operation_id']==details.get('operation_id') and selector['api']==api
                    if api!='ADD':match=match and selector['request_sha']==details.get('request_sha')
                if match:matches.append(fact)
            need(len(matches)==1,'GROUP_CLAIM_SOURCE_FACT_UNISSUED')
            self.pure_release_fence();return True
        internal=action=='PREVIEW' and type(candidate) is dict and (digest(candidate) in getattr(self.entry,'source_candidates',{}) or digest(candidate) in getattr(self.entry,'token_candidates',{}) or digest(candidate) in getattr(self.entry,'review_candidates',{}) or digest(candidate) in getattr(self.entry,'first_candidates',{}) or digest(candidate) in getattr(self.entry,'family_candidates',{}))
        need(internal or action in self.chain.config['enabled_routes'],'GROUP_HOST_ROUTE_DISABLED')
        self.pure_release_fence();return True


def _group_state_in(self,db):
    from .draft_group_store import _load
    state,seq,head=_load(db,digest(self.chain.config['binding']))
    need(state is not None,'GROUP_FIRST_REQUIRED');return state


def _family_in(self,db, *, history_locators=None):
    from .draft_group_read_family_store import recover_family_in,_ROOT_CURRENT,_RootClosure
    policy=self.entry.policy;original=original_root_evidence(self);kind=self.chain.config['binding']['source_kind']
    active=_ROOT_CURRENT.get()
    if type(active) is _RootClosure and active.active and active.db is db:
        need(active.files.policy is policy and active.history_locators is history_locators and active.source_kind==kind and active.origin_raw==canonical(original).encode(),'GROUP_HOST_ROOT_CONTEXT_CHANGED')
        return recover_family_in(db,active.files,original['origin_request_identity_sha'],root_closure=active,guard=self.entry.full_guard)
    files=FamilyFiles(policy,self.entry.loop_guard)
    with original_root_scope(db,files,original,source_kind=kind, history_locators=history_locators) as closure:
        with family_scope(db,files,closure):
            return recover_family_in(db,files,original['origin_request_identity_sha'],root_closure=closure,guard=self.entry.full_guard)


def _validate_scope_details_in(self,db,details, *, history_locators=None):
    _closed(details,('ledger_kind','account_key','family_id','purpose_key','gid','grant_id','preview_id','operation_id','group_input_sha','source_epoch','qualified_not_after_ms'))
    need(details['account_key']==digest(self.chain.config['binding']) and details['source_epoch']==digest({'profile':'GROUP_ENTRY_EPOCH_V1','entry_id':self.entry.id}),'GROUP_ADMISSION_BINDING')
    need(time.time()*1000<details['qualified_not_after_ms'],'GROUP_ADMISSION_EXPIRED')
    info=self._family_in(db, history_locators=history_locators);need(details['family_id']==info['covenant']['family_anchor_id'],'GROUP_FAMILY_CHANGED')
    state=self._group_state_in(db)
    if details['ledger_kind']=='PREVIEW':
        p=[p for p in info['covenant']['purposes'] if p['source_grant_sha']==details['purpose_key']]
        need(len(p)==1 and details['purpose_key'] in info['activations'] and details['gid']==details['grant_id']
             and details['gid'] in state['preview_grants'] and details['preview_id']=='group-read-purpose-'+details['purpose_key'],'GROUP_PURPOSE_CHANGED')
        claims=state['preview_grants'][details['gid']]['claims']
        need(not any(c['state'] in ('CONSUMED_UNKNOWN','UNKNOWN','KNOWN_REJECTED') for c in claims),'GROUP_RESULT_UNKNOWN')
    elif details['ledger_kind']=='CHILD':
        need(details['operation_id'] in state['operations'] and state['operations'][details['operation_id']]['state'] not in ('UNKNOWN','HOLD'),'GROUP_PARENT_CHANGED')
        from .draft_group_parent import validate_parent_execution_in,validate_issued_parent_execution_in
        execution=validate_parent_execution_in(self,db,details['operation_id'], history_locators=history_locators)
        validate_issued_parent_execution_in(execution,self,db, history_locators=history_locators)
        need(details['group_input_sha']==execution.capsule_sha and details['purpose_key']=='child-'+digest({
            'family':info['covenant']['family_anchor_id'],'operation':execution.operation_id})
             and type(execution.original_not_after_ms) is int
             and details['qualified_not_after_ms']<=execution.original_not_after_ms,'GROUP_PARENT_CHANGED')
    else:hold('GROUP_ADMISSION_KIND')


def bind_registration_in(self,db,registration_evidence,proof_evidence, *, history_locators=None):
    from .draft_group_input_files import InputFiles,FileEvidence
    need(type(registration_evidence) is FileEvidence and type(proof_evidence) is FileEvidence,'GROUP_REGISTRATION_EVIDENCE_REQUIRED')
    need(registration_evidence.role=='registration' and proof_evidence.role=='proof','GROUP_REGISTRATION_EVIDENCE_REQUIRED')
    files=InputFiles(self.entry.policy,self.entry.loop_guard)
    actual=files.read('registration',registration_evidence.key);proof=files.read('proof',proof_evidence.key);head=files.read_head()
    need(actual==registration_evidence and proof==proof_evidence and head.value['registration_sha']==actual.sha256
         and head.value['source_material_sha']==actual.value['source_material_sha'],'GROUP_REGISTRATION_CHANGED')
    reg=actual.value;p=proof.value
    if head.value['schema']==2:need(head.value['registration_proof_sha']==proof.sha256,'GROUP_REGISTRATION_HEAD_PROOF_CHANGED')
    origin_acceptance_sha=None
    if self.chain.source['profile']=='GROUP_BATCH_NATIVE_SOURCE_BASELINE_V2' and reg['source_material_sha']!=self.pins.source_sha:
        from .draft_group_host_native_v2 import local_registration_inspection_in,read_native_v2_review_materials_in
        from .draft_group_read_family_store import read_first_files
        from .draft_group_read_family_files import FamilyFiles
        local_registration_inspection_in(self,db, history_locators=history_locators)
        need(reg['source_material_sha']==self.chain.runtime_policy['origin_source_descriptor']['sha256'],'GROUP_NATIVE_V2_REGISTRATION_ORIGIN')
        materials=read_native_v2_review_materials_in(db,self.entry.policy,None,host=self)
        from .draft_group_host_native_v2 import material_scope
        with material_scope(materials):
            origin=files.read('source',reg['source_material_sha'])
            need(materials.origin_raw==origin.raw,'GROUP_NATIVE_V2_ORIGIN_CHANGED')
            pack=read_first_files(FamilyFiles(self.entry.policy,self.entry.loop_guard),original_root_evidence(self)['origin_request_identity_sha'])
            origin_acceptance_sha=pack.entry('first_proof').value['host_provenance']['pin_review_sha']
            need(p['helper_acceptance']['sha256']==origin_acceptance_sha,'GROUP_NATIVE_V2_ORIGINAL_ACCEPTANCE')
            materials.files.collective_fence();self._current_source_review_sha=None
    elif reg['source_material_sha']!=self.pins.source_sha:
        from .draft_group_source_review import _replay,validate_source_review_binding_in
        heads,bysha=_replay(db,self.entry.policy)
        selected=heads.get(reg['family_id']);need(selected is not None,'GROUP_SOURCE_REVIEW_REQUIRED')
        validate_source_review_binding_in(db,self.entry.policy,selected,actual.sha256,self.pins.source_sha,self.chain.source['semantic_scope_sha'])
        self._current_source_review_sha=selected
    else:
        self_review=None
        if is_operator(self):
            from .draft_group_host_operator import binding_for_host,current_binding_phase
            from .draft_group_operator_review import committed_review_sha
            from .draft_group_source_review import validate_source_review_binding_in
            live=binding_for_host(self,None)
            phase=current_binding_phase(self,live)
            if phase=='ADMISSION_READY':
                previous=getattr(self,'_registration',None)
                need(type(previous) is dict
                     and previous=={'registration_sha':actual.sha256,'registration_proof_sha':proof.sha256,
                         'registration':reg,'proof':p,'head_sha':head.sha256},
                     'GROUP_OPERATOR_CURRENT_REGISTRATION_CHANGED')
                self_review=committed_review_sha(self,live)
                need(self._current_source_review_sha==self_review,'GROUP_OPERATOR_REVIEW_RECEIPT_CHANGED')
                validate_source_review_binding_in(db,self.entry.policy,self_review,actual.sha256,
                    self.pins.source_sha,self.chain.source['semantic_scope_sha'])
            else:need(phase=='COMPLETE_SERVICE_NO_ADMISSION','GROUP_OPERATOR_REVIEW_PHASE_REQUIRED')
        self._current_source_review_sha=self_review
    need(reg['source_material_sha']==p['source_material_sha']
         and p['registration_sha']==actual.sha256 and reg['binding']==self.chain.config['binding']
         and p['qualified_binding']==self.chain.config['binding']
         and p['artifact_inventory_sha']==digest(artifact_inventory(self))
         and (p['helper_acceptance']['sha256']==self.pins.review_sha or self._current_source_review_sha is not None
              or p['helper_acceptance']['sha256']==origin_acceptance_sha),'GROUP_REGISTRATION_BINDING')
    need(reg['artifacts']==artifact_inventory(self),'GROUP_REGISTRATION_ARTIFACTS')
    identities=[{'article_id':m['article_id'],'original_request_sha':m['original_request_sha']} for m in reg['ordered_members']]
    need(identities==member_identities(self),'GROUP_REGISTRATION_MEMBER_SCOPE')
    self.validate_history_in(db, history_locators=history_locators);info=self._family_in(db, history_locators=history_locators)
    need(reg['family_id']==info['covenant']['family_anchor_id'],'GROUP_REGISTRATION_FAMILY')
    self._registration={'registration_sha':actual.sha256,'registration_proof_sha':proof.sha256,
        'registration':reg,'proof':p,'head_sha':head.sha256}
    self._registration_files=files
    return {'state':'REGISTRATION_BOUND_CURRENT_ENTRY','authority':False}


def build_admission_source_fact_in(self,db,scope,claim_selector, *, history_locators=None):
    from .draft_group_runtime_host import validate_admission_scope
    from .draft_group_source_facts import make_source_fact_for_current_in,register_source_fact_in
    from .draft_group_store import GroupStore
    validate_admission_scope(scope,db=db, history_locators=history_locators)
    ctx=self.current_context_in(db,scope.source, history_locators=history_locators)
    candidate=make_source_fact_for_current_in(self,db,ctx,claim_selector,admission_scope=scope, history_locators=history_locators)
    if not hasattr(self.entry,'source_candidates'):self.entry.source_candidates={}
    self.entry.source_candidates[digest(candidate)]=(ctx,canonical(candidate))
    return register_source_fact_in(db,GroupStore(candidate['binding_sha'],_history_partial(self.verify_in, history_locators=history_locators)),ctx,candidate, history_locators=history_locators)


GroupRuntimeHost._group_state_in=_group_state_in
GroupRuntimeHost._family_in=_family_in
GroupRuntimeHost._validate_scope_details_in=_validate_scope_details_in
GroupRuntimeHost.bind_registration_in=bind_registration_in
GroupRuntimeHost.build_admission_source_fact_in=build_admission_source_fact_in


def _validate_history_in_minimal(self,db, *, history_locators=None):
    policy=self.entry.policy;kind=self.chain.config['binding']['source_kind']
    need(type(db) is OwnedConnection and db.in_transaction,'GROUP_HISTORY_OWNED_REQUIRED')
    from .draft_group_history_context import require_history
    require_history(policy,db,history_locators)
    OwnStore.check(db,kind,policy, history=history_locators)
    _check_legacy_history_in(db,kind,ExistingHistoryStoreView(policy.root/'state.sqlite3',policy), history=history_locators)

GroupRuntimeHost.validate_history_in_minimal=_validate_history_in_minimal


def validate_original_uploads_in(self,db,current=None, *, history_locators=None):
    from .draft_group_source_members import validated_source_members_in
    validated_source_members_in(self,db,current, history_locators=history_locators);return None


GroupRuntimeHost.validate_original_uploads_in=validate_original_uploads_in


# Fixed signatures consumed by B/Root. No caller phase/for_network selection.
def validate_native_v2_seal_inputs(host,observer,observation,inspection):
    from .draft_group_runtime_host import _assert_fixed_references
    _assert_fixed_references()
    from .draft_group_host_native_v2 import validate_native_v2_seal_inputs as actual
    return actual(host,observer,observation,inspection)

def local_registration_inspection_in(host,db=None,*,history_locators=None):
    if is_operator(host):
        from .draft_group_host_operator import local_registration_inspection_in as actual
        return actual(host,db,history_locators=history_locators)
    from .draft_group_runtime_host import _assert_fixed_references
    _assert_fixed_references()
    from .draft_group_host_native_v2 import local_registration_inspection_in as actual
    return actual(host,db,history_locators=history_locators)

def establish_current_source_review(host):
    if is_operator(host):
        from .draft_group_host_operator import establish_current_source_review as actual
        return actual(host)
    from .draft_group_runtime_host import _assert_fixed_references
    _assert_fixed_references()
    from .draft_group_host_native_v2 import establish_current_source_review as actual
    return actual(host)

def read_native_v2_review_materials_in(db,policy,candidate,*,states=None,events=None,host=None):
    from .draft_group_runtime_host import _assert_fixed_references
    _assert_fixed_references()
    from .draft_group_host_native_v2 import read_native_v2_review_materials_in as actual
    return actual(db,policy,candidate,states=states,events=events,host=host)

from .draft_group_host_native_v2 import NativeV2ReviewHistoryMaterials


# Captured once during the core import. The actual Gate checks refs/codes and
# class structure before any later source/material/phase leaf can run. Module
# labels alone never identify a fixed issuer.
from types import FunctionType as _NativeFunctionType
from . import draft_group_runtime_host as _native_gate
from . import draft_group_host_native_v2 as _native_host
from . import group_host_jobs as _native_jobs
from . import group_host_external_loader as _native_loader
from . import draft_group_pin_resources as _native_pin_resources
from . import draft_group_artifact_resources as _native_artifact_resources
from . import draft_group_history_context as _native_history_context
from . import draft_group_rich_syn_fixture as _native_rich_fixture
from . import draft_group_input_files as _native_input_files
from . import own_store as _native_own_store
from . import own_workflow as _native_own_workflow
from . import own_connection_workflow as _native_persistent_workflow
from . import own_connection_broker as _native_connection_broker
from . import own_fd_domain as _native_fd_domain
from . import draft_revision_gate as _native_revision_gate
from . import draft_group_host_bootstrap as _native_bootstrap_aliases
import sys as _native_sys
from . import draft_group_host_operator as _operator_host
from . import draft_group_operator_review_chain as _operator_chain
from . import draft_group_operator_source_codec as _operator_codec
from . import draft_group_operator_semantics as _operator_semantics
from . import draft_group_operator_materials as _operator_materials
from . import draft_group_operator_review as _operator_review
from . import draft_group_operator_history as _operator_history
from . import draft_group_host_publisher as _operator_publisher
from . import draft_group_batch_inputs as _operator_batch_inputs
from . import draft_group_source_members as _operator_members
from . import own_content_qa_join as _operator_qa_join
from . import own_preupload_qa as _operator_qa
from . import own_history_locators as _operator_history_locators
from . import draft_group_first_control as _operator_first_control
from . import draft_group_preparent_journal as _operator_preparent
from . import draft_group_batch_bootstrap as _operator_batch_bootstrap
from . import draft_group_runtime_service as _operator_runtime_service
from . import draft_group_registered_execution as _operator_registered_execution
from . import draft_group_pure_derived_cache as _operator_pure_derived_cache
from . import draft_group_operator_time_v2 as _operator_time_v2
from . import draft_group_first_time_values as _operator_first_time_values
_native_modules=(_native_sys.modules[__name__],_native_host,_native_jobs,_native_loader,_native_pin_resources,_native_artifact_resources,_native_history_context,_native_rich_fixture,_native_input_files,_native_gate,_native_own_store,_native_own_workflow,_native_persistent_workflow,_native_connection_broker,_native_fd_domain,_native_revision_gate,_operator_host,_operator_chain,_operator_codec,_operator_semantics,_operator_materials,_operator_review,_operator_history,_operator_publisher,_operator_batch_inputs,_operator_members,_operator_qa_join,_operator_qa,_operator_history_locators,_operator_first_control,_operator_preparent,_operator_batch_bootstrap,_operator_runtime_service,_operator_registered_execution,_operator_pure_derived_cache,_operator_time_v2,_operator_first_time_values)
_native_snapshots=[]
for _module in _native_modules:
    _functions=tuple((name,value,value.__code__)for name,value in vars(_module).items()
        if type(value)is _NativeFunctionType and value.__module__==_module.__name__)
    _classes=[]
    for _name,_value in tuple(vars(_module).items()):
        if type(_value)is type and _value.__module__==_module.__name__:
            _codes=[]
            for _attribute in vars(_value).values():
                _fn=_attribute.__func__ if type(_attribute)in (staticmethod,classmethod)else _attribute
                if type(_fn)is _NativeFunctionType:_codes.append((_fn,_fn.__code__))
                if type(_attribute)is property:
                    for _accessor in (_attribute.fget,_attribute.fset,_attribute.fdel):
                        if type(_accessor)is _NativeFunctionType:_codes.append((_accessor,_accessor.__code__))
            _classes.append((_name,_value,_value.__bases__,_value.__mro__,dict(vars(_value)),tuple(_codes)))
    _native_snapshots.append((_module,_functions,tuple(_classes)))
_native_gate._HOST_NATIVE_TCB=tuple(_native_snapshots)
# New physical/constructor bodies include contextmanager closures. Capture
# actual generators now, before any Group SQL scope can first borrow resources.
_native_pending=[]
for _module in _native_modules:
    for _value in tuple(vars(_module).values()):
        if type(_value) is _NativeFunctionType and _value.__module__==_module.__name__:
            _native_pending.append(_value)
        elif type(_value) is type and _value.__module__==_module.__name__:
            for _attribute in vars(_value).values():
                _fn=_attribute.__func__ if type(_attribute) in (staticmethod,classmethod) else _attribute
                if type(_fn) is _NativeFunctionType:_native_pending.append(_fn)
                elif type(_attribute) is property:
                    _native_pending.extend(fn for fn in (_attribute.fget,_attribute.fset,_attribute.fdel)
                                           if type(fn) is _NativeFunctionType)
_native_seen=set();_native_closures=[]
while _native_pending:
    _fn=_native_pending.pop()
    if id(_fn) in _native_seen:continue
    _native_seen.add(id(_fn))
    _cells=tuple((cell,cell.cell_contents) for cell in (_fn.__closure__ or ()))
    _native_closures.append((_fn,_fn.__code__,_cells))
    _native_pending.extend(value for _,value in _cells if type(value) is _NativeFunctionType)
    _wrapped=getattr(_fn,'__wrapped__',None)
    if type(_wrapped) is _NativeFunctionType:_native_pending.append(_wrapped)
_native_gate._HOST_NATIVE_CLOSURES=tuple(_native_closures)
_native_gate._HOST_FD_DOMAIN_ALIASES=(
    (_native_connection_broker,'regular_fd_domain',_native_fd_domain.regular_fd_domain),
    (_native_connection_broker,'phase_deadline',_native_fd_domain.phase_deadline),
    (_native_connection_broker,'owned_lifetime',_native_fd_domain.owned_lifetime),
    (_native_gate,'regular_fd_domain',_native_fd_domain.regular_fd_domain),
    (_native_revision_gate,'regular_fd_domain',_native_fd_domain.regular_fd_domain),
    (_native_bootstrap_aliases,'regular_fd_domain',_native_fd_domain.regular_fd_domain),
    (_native_bootstrap_aliases,'owned_lifetime',_native_fd_domain.owned_lifetime),
    (_native_fd_domain,'_LOCK',_native_fd_domain._LOCK),
    (_native_fd_domain,'_LOCAL',_native_fd_domain._LOCAL))
del _native_pending,_native_seen,_native_closures,_cells,_wrapped

del _module,_functions,_classes,_name,_value,_attribute,_fn,_codes


from functools import partial as _history_partial
