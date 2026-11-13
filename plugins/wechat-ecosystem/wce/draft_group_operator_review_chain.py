"""Isolated Operator static review-chain proposal; no source/current issuer.

Exact held materials are bound under a real GroupExecutionGate. History uses
an actual Owned/H context and the fixed catalog producer, never a fake Gate.
Neither validated JSON nor this chain issues W1, W2, QA, Parent or HTTP rights.
"""
from . import draft_group_operator_time_v2 as time06
from contextlib import contextmanager
from dataclasses import dataclass
from hashlib import sha256
import ast
import json
from pathlib import Path
import sys
import time
import threading
import os
import stat
from types import FunctionType
from weakref import WeakKeyDictionary

from . import draft_group_operator_source_codec as codec
from .draft_group_runtime_host import (GroupExecutionGate, PinnedFile, need, hold,
    OwnedConnection, _transaction_marker, _assert_fixed_references)
from .draft_group_input_files import _artifact
from .draft_group_read_family_store import prepared_binding, _origin
from .draft_group_read_family_values import decode as decode_family
from .draft_group_pin_resources import PinPool, close_all, path_value, full
from .own_connection_policy import ConnectionPolicy
from .publication_contract import stable_account

MAXIMUM = 2*1024*1024
CONFIG_PROFILE = 'GROUP_OPERATOR_HOST_CONFIGURATION_V1'
REVIEW_PROFILE = 'GROUP_OPERATOR_HOST_REVIEW_ACCEPTANCE_V1'
ARM_PROFILE = 'GROUP_OPERATOR_HOST_ARM_RECEIPT_V1'
QA_PROFILE = 'GROUP_OPERATOR_CURRENT_QA_SET_V1'
CONFIG_KEYS = ('schema','profile','authority','content_source_type','binding',
    'registry_descriptor','artifact_root_descriptors','semantic_adoption_sha',
    'source_material_sha','original_root_evidence_sha','first_covenant_sha',
    'read_contract_sha','candidate_scope','enabled_routes','source_review_policy',
    'runtime_source_policy_sha','qa_set_sha','artifact_inventory_sha')
REVIEW_KEYS = ('schema','profile','authority','content_source_type',
    'configuration_sha','semantic_adoption_sha','source_material_sha',
    'runtime_source_policy_sha','qa_set_sha','artifact_inventory_sha',
    'original_root_evidence_sha','first_covenant_sha','read_contract_sha',
    'candidate_scope','unarmed_sha','helper_dependencies','retention_evidence','permitted_arm')
ARM_KEYS = ('schema','profile','authority','unarmed_sha','review_sha','armed_sha','ast_diff')
QA_KEYS = ('schema','profile','authority','selection_ref','artifact_roots_ref',
    'member_projection_ref','dossier_ref','acceptance_ref','binding_projection_sha256')
_FILE_NAMES = ('configuration','semantic','source','review','arm_receipt','unarmed',
    'armed','runtime_source_policy','first_covenant','original_root_evidence',
    'qa_set','artifact_inventory')
_MATERIALS = WeakKeyDictionary()


def _json(raw):
    need(type(raw) is bytes and 0<len(raw)<=MAXIMUM,'GROUP_OPERATOR_MATERIAL_BOUND')
    try:value=json.loads(raw.decode('utf-8'),object_pairs_hook=codec._unique,
                         parse_constant=lambda _:hold('GROUP_OPERATOR_MATERIAL_JSON'))
    except (ValueError,UnicodeError,RecursionError,OverflowError):
        hold('GROUP_OPERATOR_MATERIAL_JSON')
    need(codec.canonical(value)+b'\n'==raw,'GROUP_OPERATOR_MATERIAL_CANONICAL')
    return value


def _header(value,keys,profile,*,content=False):
    need(type(value) is dict and set(value)==set(keys)
         and type(value['schema']) is int and value['schema']==1
         and value['profile']==profile and value['authority'] is False,
         'GROUP_OPERATOR_MATERIAL_PROFILE')
    if content:need(value['content_source_type']==codec.CONTENT_SOURCE_TYPE,
                    'GROUP_OPERATOR_MATERIAL_PROFILE')


@dataclass(frozen=True)
class FixedOperatorHostPins:
    """Compiled fixed-catalog data, not a source/QA/permission object.

    Native registrations/lookups/role threads deliberately do not exist here.
    Root's fixed catalog producer is responsible for constructing this table.
    """
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
    runtime_source_policy_path: Path
    runtime_source_policy_sha: str
    first_covenant_path: Path
    first_covenant_sha: str
    original_root_evidence_path: Path
    original_root_evidence_sha: str
    qa_set_path: Path
    qa_set_sha: str
    artifact_inventory_path: Path
    artifact_inventory_sha: str
    helper_files: tuple
    artifact_roots: tuple
    retention_evidence: tuple


def _pins(pins):
    need(type(pins) is FixedOperatorHostPins,'GROUP_OPERATOR_FIXED_PINS_REQUIRED')
    paths=[]
    for role in _FILE_NAMES:
        path=getattr(pins,role+'_path');checksum=getattr(pins,role+'_sha')
        need(type(path) is type(Path('/')),'GROUP_OPERATOR_FIXED_PIN_PATH')
        path_value(path);codec._sha(checksum);paths.append(path)
    need(len(set(paths))==len(paths),'GROUP_OPERATOR_FIXED_PIN_ALIAS')
    for pairs in (pins.helper_files,pins.retention_evidence):
        need(type(pairs) is tuple and 0<len(pairs)<=128,'GROUP_OPERATOR_FIXED_DEPENDENCIES')
        for pair in pairs:
            need(type(pair) is tuple and len(pair)==2 and type(pair[0]) is type(Path('/')),
                 'GROUP_OPERATOR_FIXED_DEPENDENCIES')
            path_value(pair[0]);codec._sha(pair[1])
        need(len({path for path,_ in pairs})==len(pairs),'GROUP_OPERATOR_FIXED_DEPENDENCIES')
    need(type(pins.artifact_roots) is tuple and 0<len(pins.artifact_roots)<=128,
         'GROUP_OPERATOR_ARTIFACT_ROOTS')
    for pair in pins.artifact_roots:
        need(type(pair) is tuple and len(pair)==2 and type(pair[1]) is type(Path('/')),
             'GROUP_OPERATOR_ARTIFACT_ROOTS')
        codec._sha(pair[0]);path_value(pair[1])
    need(len(dict(pins.artifact_roots))==len(pins.artifact_roots)
         and len({path for _,path in pins.artifact_roots})==len(pins.artifact_roots),
         'GROUP_OPERATOR_ARTIFACT_ROOTS')


def _read_files(pins,pool,owner):
    _pins(pins);files={};held=[]
    try:
        for role in _FILE_NAMES:
            pin=PinnedFile(getattr(pins,role+'_path'),getattr(pins,role+'_sha'),
                           MAXIMUM,pool=pool,owner=owner)
            files[role]=pin;held.append(pin)
        for index,(path,checksum) in enumerate(pins.helper_files+pins.retention_evidence):
            pin=PinnedFile(path,checksum,MAXIMUM,pool=pool,owner=owner)
            files['dependency:'+str(index)]=pin;held.append(pin)
        source=codec.decode(files['source'].raw,expected_profile=codec.SOURCE_PROFILE)
        semantic=codec.decode(files['semantic'].raw,expected_profile=codec.SEMANTIC_PROFILE)
        refs={'selection':source['selection_ref'],
              'prepared_relations':source['prepared_relation_inventory_ref'],
              'postupload_mapping':source['postupload_mapping_ref'],
              'execution_slots':semantic['semantic_scope']['execution_slots_ref']}
        qa=_json(files['qa_set'].raw);_header(qa,QA_KEYS,QA_PROFILE)
        codec._sha(qa['binding_projection_sha256'])
        for name in ('selection','artifact_roots','member_projection','dossier','acceptance'):
            reference=qa[name+'_ref'];codec._ref(reference)
            role='qa:'+name;pin=PinnedFile(Path(reference['path']),reference['sha256'],
                                         reference['size'],pool=pool,owner=owner)
            need(len(pin.raw)==reference['size'],'GROUP_OPERATOR_REFERENCE_SIZE')
            files[role]=pin;held.append(pin)
        need(qa['selection_ref']==source['selection_ref'],'GROUP_OPERATOR_QA_SELECTION')
        for role,reference in refs.items():
            codec._ref(reference)
            pin=PinnedFile(Path(reference['path']),reference['sha256'],reference['size'],
                           pool=pool,owner=owner)
            need(len(pin.raw)==reference['size'],'GROUP_OPERATOR_REFERENCE_SIZE')
            files[role]=pin;held.append(pin)
        return files,tuple(held)
    except BaseException as original:
        close_all([pin.close for pin in reversed(held)],original);raise


def _validate(pins,files,policy,*,live):
    """Static identities only. Actual source/QA/RootClosure checks stay outside."""
    _pins(pins)
    for pin in files.values():pin.check()
    c=_json(files['configuration'].raw);_header(c,CONFIG_KEYS,CONFIG_PROFILE,content=True)
    r=_json(files['review'].raw);_header(r,REVIEW_KEYS,REVIEW_PROFILE,content=True)
    a=_json(files['arm_receipt'].raw);_header(a,ARM_KEYS,ARM_PROFILE)
    s=codec.decode(files['source'].raw,expected_profile=codec.SOURCE_PROFILE)
    m=codec.decode(files['semantic'].raw,expected_profile=codec.SEMANTIC_PROFILE)
    try:
        hint=_json(files['runtime_source_policy'].raw)
        if type(hint) is dict and hint.get('profile')==time06.POLICY_PROFILE_V2:
            p=time06.decode_runtime_policy_v2(files['runtime_source_policy'].raw)
        else:p=codec.decode(files['runtime_source_policy'].raw,expected_profile=codec.POLICY_PROFILE)
    except (codec.OperatorSourceCodecError,time06.OperatorTimeCodecError):
        need(False,'GROUP_OPERATOR_RUNTIME_POLICY')
    inventory=_json(files['artifact_inventory'].raw)
    need(type(inventory) is list and 0<len(inventory)<=3072,'GROUP_OPERATOR_ARTIFACT_INVENTORY')
    for artifact in inventory:_artifact(artifact)
    need(len({(x['root_sha'],x['relative_path']) for x in inventory})==len(inventory),
         'GROUP_OPERATOR_ARTIFACT_INVENTORY')
    root=_json(files['original_root_evidence'].raw);_origin(root)
    covenant=decode_family('covenant',files['first_covenant'].raw)
    qa=_json(files['qa_set'].raw);_header(qa,QA_KEYS,QA_PROFILE)
    codec.validate_binding(c['binding'])
    need(c['binding']==m['binding']==p['binding'] and s['binding_sha']==codec.digest(c['binding']),
         'GROUP_OPERATOR_MATERIAL_BINDING')
    need(m['stable_owner']=={'tenant':policy.actor.tenant_id,'principal':policy.actor.principal_id}
         and m['platform_account_sha']==stable_account(policy.data)
         and c['binding']['connection']==policy.data['connection_id']
         and c['binding']['account']==policy.data['appid']
         and c['binding']['resource']==policy.data['resource_id'],'GROUP_OPERATOR_ACCOUNT')
    if live:
        need(c['binding']==prepared_binding(policy,'OPERATOR_ATTESTED')
             and c['candidate_scope']==policy.value['candidate_scope'],
             'GROUP_OPERATOR_CURRENT_POLICY')
    expected={'configuration_sha':pins.configuration_sha,'semantic_adoption_sha':pins.semantic_sha,
        'source_material_sha':pins.source_sha,'runtime_source_policy_sha':pins.runtime_source_policy_sha,
        'qa_set_sha':pins.qa_set_sha,'artifact_inventory_sha':codec.digest(inventory),
        'original_root_evidence_sha':codec.digest(root),'first_covenant_sha':pins.first_covenant_sha,
        'read_contract_sha':c['read_contract_sha'],'candidate_scope':c['candidate_scope'],
        'unarmed_sha':pins.unarmed_sha,'helper_dependencies':[[str(path),checksum] for path,checksum in pins.helper_files],
        'retention_evidence':[[str(path),checksum] for path,checksum in pins.retention_evidence],
        'permitted_arm':{'REVIEW_PATH':str(pins.review_path),'REVIEW_SHA':'FIXED_REVIEW_BYTES_SHA256'}}
    need(all(r[key]==value for key,value in expected.items()),'GROUP_OPERATOR_REVIEW_BINDING')
    need(c['semantic_adoption_sha']==pins.semantic_sha and c['source_material_sha']==pins.source_sha
         and c['runtime_source_policy_sha']==pins.runtime_source_policy_sha
         and c['qa_set_sha']==pins.qa_set_sha and c['artifact_inventory_sha']==codec.digest(inventory)
         and c['original_root_evidence_sha']==m['original_root_evidence_sha']==codec.digest(root)
         and m['artifact_inventory_sha']==codec.digest(inventory)
         and c['first_covenant_sha']==pins.first_covenant_sha
         and c['read_contract_sha']==m['read_contract_sha']==covenant['read_contract_sha']
         and c['enabled_routes']==m['semantic_scope']['permitted_routes']==['NEW_ONLY_EXISTING_DELEGATION']
         and c['source_review_policy']=='EXACT_FAMILY_COMMITTED_REVIEW_CHAIN_V1',
         'GROUP_OPERATOR_STATIC_BINDING')
    need(s['semantic_scope_sha']==p['semantic_scope_sha']==codec.semantic_scope_sha(m)
         and p['core_scope_sha']==c['candidate_scope'] and p['source_material_sha']==pins.source_sha
         and s['qa_set_ref']==m['qa_set_ref']
         and s['qa_set_ref']['path']==str(pins.qa_set_path)
         and s['qa_set_ref']['sha256']==pins.qa_set_sha
         and s['qa_set_ref']['size']==len(files['qa_set'].raw), 'GROUP_OPERATOR_STATIC_SOURCE')
    for key in ('original_queue_sha','operator_request_identity_sha','original_request_set_sha','account_partition_sha'):
        need(s[key]==p[key]==m[key],'GROUP_OPERATOR_ORIGINAL_REQUEST')
    need(s['allowed_read_scope']==p['allowed_read_scope']
         and s['allowed_read_scope']['member_ids']==m['semantic_scope']['authorized_member_ids']
         and p['selection_sha']==s['selection_ref']['sha256']
         and p['qa_set_sha']==pins.qa_set_sha
         and p['prepared_relations_sha']==s['prepared_relation_inventory_ref']['sha256']
         and p['postupload_mapping_sha']==s['postupload_mapping_ref']['sha256']
         and p['source_rights_expiry']==m['source_rights_expiry'], 'GROUP_OPERATOR_STATIC_POLICY')
    anchor=dict(schema=1,profile=codec.ANCHOR_PROFILE,authority=False,
        content_source_type=codec.CONTENT_SOURCE_TYPE,**{key:m[key] for key in codec.REQUEST_FIELDS},
        request_identity_sha=m['operator_request_identity_sha'],purpose=codec.PURPOSE)
    family=codec.family_anchor(anchor)
    need(s['allowed_read_scope']['family_anchor_sha']==covenant['family_anchor_id']==family
         and covenant['request_identity_sha']==root['origin_request_identity_sha']==m['operator_request_identity_sha']
         and covenant['stable_owner']==root['origin_stable_owner']==m['stable_owner']
         and root['origin_prepared_binding_sha']==codec.digest(c['binding'])
         and covenant['platform_account_sha']==m['platform_account_sha']
         and covenant['original_scope_sha']==s['semantic_scope_sha']
         and covenant['source_rights_expiry']==m['source_rights_expiry']
         and covenant['allowed_routes']==c['enabled_routes']
         and covenant['qualify_subjects']==m['semantic_scope']['qualify_subjects']
         and _json(files['execution_slots'].raw)==covenant['branches'][0]['execution_slots'],
         'GROUP_OPERATOR_FIRST_ROOT_BINDING')
    # Import the unchanged algorithm after this module is fully initialized;
    # Host's fixed-reference snapshot must not capture a partial chain module.
    from .draft_group_host_review import _arm_ast
    before,left=_arm_ast(files['unarmed'].raw);after,right=_arm_ast(files['armed'].raw)
    need(before==after and all(type(value) is ast.Constant and value.value is None for value in left.values())
         and all(type(value) is ast.Constant for value in right.values())
         and right['REVIEW_PATH'].value==str(pins.review_path) and right['REVIEW_SHA'].value==pins.review_sha,
         'GROUP_OPERATOR_ARM_AST')
    need(a['unarmed_sha']==pins.unarmed_sha and a['review_sha']==pins.review_sha
         and a['armed_sha']==pins.armed_sha and a['ast_diff']==['REVIEW_PATH','REVIEW_SHA'],
         'GROUP_OPERATOR_ARM_RECEIPT')
    if live:
        now=time.time()*1000
        caps=[s['expires_policy']['not_after']*1000,p['original_input_not_after_ms']]
        if m['source_rights_expiry']['not_after'] is not None:caps.append(m['source_rights_expiry']['not_after'])
        need(now<min(caps),'GROUP_OPERATOR_SOURCE_EXPIRED')
        registry=Path(policy.value['registry_path']);stat=registry.stat(follow_symlinks=False);parent=registry.parent.stat(follow_symlinks=False)
        need(c['registry_descriptor']=={'registry_id':'own-connections',
            'path_utf8_sha256':sha256(str(registry).encode()).hexdigest(),'device':stat.st_dev,'inode':stat.st_ino,
            'parent_device':parent.st_dev,'parent_inode':parent.st_ino},'GROUP_OPERATOR_REGISTRY_DESCRIPTOR')
        descriptors=[]
        for checksum,path in pins.artifact_roots:
            stat=path.stat(follow_symlinks=False)
            descriptors.append({'root_sha':checksum,'path_utf8_sha256':sha256(str(path).encode()).hexdigest(),
                                'device':stat.st_dev,'inode':stat.st_ino})
        need(c['artifact_root_descriptors']==descriptors,'GROUP_OPERATOR_ARTIFACT_ROOT_DESCRIPTOR')
    need({x['root_sha'] for x in inventory}=={checksum for checksum,_ in pins.artifact_roots},
         'GROUP_OPERATOR_ARTIFACT_ROOTS')
    for pin in files.values():pin.check()
    # These two original selected-input files use the selected-source codec's
    # canonical bytes without LF. New Group materials use canonical+LF. Never
    # rewrite an accepted original file to fit the new container serialization.
    from .own_preupload_sources import _json as original_canonical_object
    from .draft_group_operator_materials import projection as selected_projection
    from .draft_group_selected_source_codec import decode_manifest
    projection=selected_projection(original_canonical_object(files['qa:member_projection'].raw))
    selection,_,selection_sha=decode_manifest(files['selection'].raw,
        expected_member_projection=tuple(tuple(row) for row in projection['member_projection']))
    need(selection_sha==s['selection_ref']['sha256'],'GROUP_OPERATOR_SELECTION_CHANGED')
    return dict(config=c,semantic=m,source=s,runtime_policy=p,review=r,arm=a,
        artifact_inventory=inventory,original_root_evidence=root,first_covenant=covenant,
        qa_set=qa,selection=selection,
        prepared_relations=_json(files['prepared_relations'].raw),
        postupload_mapping=_json(files['postupload_mapping'].raw),
        execution_slots=_json(files['execution_slots'].raw))


def _operator_view(values):
    from .draft_group_operator_semantics import member_identities_from_values,build_operator_view
    selected=values['selection'];prepared=values['prepared_relations'];mapped=values['postupload_mapping']
    need(type(selected) is dict and type(selected.get('members')) is list
         and type(prepared) is dict and type(prepared.get('rows')) is list
         and type(mapped) is dict and type(mapped.get('rows')) is list,
         'GROUP_OPERATOR_STATIC_MEMBER_ROWS')
    semantic=values['semantic']
    identities=member_identities_from_values(selected['members'],prepared['rows'],mapped['rows'],
        authorized_member_ids=semantic['semantic_scope']['authorized_member_ids'],
        binding_sha=codec.digest(semantic['binding']))
    return build_operator_view(semantic,values['source'],
        artifact_inventory=values['artifact_inventory'],
        original_root_evidence=values['original_root_evidence'],
        member_identities=identities,execution_slots=values['execution_slots'])


def _descriptor(pins,values,current_binding_sha):
    codec._sha(current_binding_sha)
    s=values['source'];m=values['semantic']
    value=dict(configuration_sha=pins.configuration_sha,
        semantic_adoption_sha=pins.semantic_sha,qa_adoption_sha=pins.qa_set_sha,
        artifact_inventory_sha=codec.digest(values['artifact_inventory']),
        content_source_type=codec.CONTENT_SOURCE_TYPE,selection_sha=s['selection_ref']['sha256'],
        operator_request_set_sha=s['original_request_set_sha'],
        prepared_relations_sha=s['prepared_relation_inventory_ref']['sha256'],
        postupload_mapping_sha=s['postupload_mapping_ref']['sha256'],
        operator_observation_profile=codec.OBSERVATION_PROFILE,
        runtime_source_policy_sha=pins.runtime_source_policy_sha,current_binding_sha=current_binding_sha)
    try:
        if values['runtime_policy']['profile']==time06.POLICY_PROFILE_V2:
            value['operator_observation_profile']=time06.OBSERVATION_PROFILE_V2
            return time06.validate_descriptor_v2(value)
        return codec.validate_descriptor(value)
    except (codec.OperatorSourceCodecError,time06.OperatorTimeCodecError):
        need(False,'GROUP_OPERATOR_DESCRIPTOR')


class FixedOperatorReviewChain:
    def __init__(self,pins,entry):
        need(type(entry) is GroupExecutionGate,'GROUP_OPERATOR_ACTUAL_ENTRY_REQUIRED')
        entry.held_pure();_pins(pins)
        self.pins,self.entry=pins,entry
        self._root_fds=[]
        for _,path in pins.artifact_roots:
            fd=entry.pin_pool.directory(path,owner=entry)
            info=os.fstat(fd)
            need(stat.S_ISDIR(info.st_mode),'GROUP_OPERATOR_ARTIFACT_ROOTS')
            self._root_fds.append((path,fd,full(info)))
        self.files,held=_read_files(pins,entry.pin_pool,entry)
        entry.pins.extend(held)
        self.helpers=tuple(self.files['dependency:'+str(index)] for index in
                           range(len(pins.helper_files)+len(pins.retention_evidence)))
        self.runtime_policy_file=self.files['runtime_source_policy']
        self._original_helpers=self.helpers
        self._original_files=tuple(self.files.items())
        self._original_raw={role:pin.raw for role,pin in self.files.items()}
        self._values=_validate(pins,self.files,entry.policy,live=True)
        for key,value in self._values.items():setattr(self,key,value)
        need(getattr(entry,'source_kind','OPERATOR_ATTESTED')=='OPERATOR_ATTESTED','GROUP_OPERATOR_SOURCE_KIND_CHANGED')
        entry.source_kind='OPERATOR_ATTESTED'
        self.qa_files={role:self.files['qa:'+role] for role in
                       ('selection','artifact_roots','member_projection','dossier','acceptance')}
        self.check()

    def check(self):
        need(type(self.entry) is GroupExecutionGate,'GROUP_OPERATOR_ACTUAL_ENTRY_REQUIRED')
        self.entry.held_pure()
        for path,fd,pin in self._root_fds:
            need(full(os.fstat(fd))==pin==full(path.lstat()),'GROUP_OPERATOR_ARTIFACT_ROOT_CHANGED')
        need(tuple(self.files.items())==self._original_files
             and self.helpers==self._original_helpers
             and self.runtime_policy_file is self.files['runtime_source_policy'],
             'GROUP_OPERATOR_MATERIAL_OWNER_CHANGED')
        for role,pin in self.files.items():
            need(type(pin) is PinnedFile,'GROUP_OPERATOR_PIN_REQUIRED')
            pin.check();need(pin.raw==self._original_raw[role],'GROUP_OPERATOR_MATERIAL_CHANGED')
        values=_validate(self.pins,self.files,self.entry.policy,live=True)
        need(set(values)==set(self._values) and all(codec.canonical(value)==codec.canonical(self._values[key])
             for key,value in values.items()),'GROUP_OPERATOR_MATERIAL_OBJECT_CHANGED')
        for key,value in self._values.items():
            need(codec.canonical(getattr(self,key))==codec.canonical(value),'GROUP_OPERATOR_MATERIAL_OBJECT_CHANGED')
        self.entry.held_pure()
        return self

    @property
    def operator_semantics(self):
        self.check()
        return _operator_view(self._values)

    def descriptor(self,current_binding_sha):
        self.check()
        return _descriptor(self.pins,self._values,current_binding_sha)


@dataclass(frozen=True,eq=False,init=False)
class OperatorReviewHistoryMaterials:
    """Only the actual Owned/H+fixed-catalog reader creates this retained set."""
    authority: bool=False
    def __init__(self,*args,**kwargs):hold('GROUP_OPERATOR_HISTORY_ISSUER_REQUIRED')
    def collective_fence(self):
        record=_MATERIALS.get(self)
        need(record is not None,'GROUP_OPERATOR_HISTORY_MATERIALS_CLOSED')
        db,policy,history,marker,thread,pool,owner,files,values,pins,owns,lease,artifacts,image=record
        need(thread==threading.get_ident() and type(db) is OwnedConnection and db.in_transaction
             and _transaction_marker(db)==marker,'GROUP_OPERATOR_HISTORY_TRANSACTION_CHANGED')
        from .draft_group_host_history import _context
        from .draft_group_history_context import require_history
        _context(db,policy);require_history(policy,db,history)
        if lease is not None:lease.check()
        for item in files.values():item.check()
        need(self.authority is False,'GROUP_OPERATOR_HISTORY_MATERIAL_CHANGED')
        for key,value in image:
            actual=getattr(self,key)
            need(type(actual) is type(value) and actual==value,'GROUP_OPERATOR_HISTORY_MATERIAL_CHANGED')
        for key,value in values.items():
            need(codec.canonical(getattr(self,key))==codec.canonical(value),'GROUP_OPERATOR_HISTORY_MATERIAL_CHANGED')
        return self
    @property
    def operator_semantics(self):
        self.collective_fence()
        return _operator_view(_MATERIALS[self][8])
    def descriptor(self,current_binding_sha):
        self.collective_fence();record=_MATERIALS[self]
        return _descriptor(record[9],record[8],current_binding_sha)
    def close(self,*,original=None):
        record=_MATERIALS.pop(self,None)
        if record is not None:
            callbacks=[item.close for item in reversed(tuple(record[7].values()))]
            if record[10]:
                callbacks.extend((lambda:record[12].close(original=original),
                    lambda:record[5].close(owner=record[6],original=original)))
            close_all(callbacks,original)


def read_operator_review_materials_in(db,policy,configuration_sha,*,history_locators=None):
    """No Gate/current/Native. Fixed catalog producer is a required real seam.

    Root must integrate group_host_jobs.operator_pins_for_history before the
    positive path is available. Missing producer fails explicitly; no callback,
    free pins/path or bool substitutes for catalog authenticity.
    """
    from .draft_group_host_history import _context
    from .draft_group_history_context import require_history,current_physical_material_resources
    _context(db,policy);require_history(policy,db,history_locators)
    need(type(db) is OwnedConnection and db.in_transaction and _transaction_marker(db) is not None,
         'GROUP_OPERATOR_HISTORY_OWNED_REQUIRED');codec._sha(configuration_sha)
    from . import group_host_jobs as jobs
    producer=getattr(jobs,'operator_pins_for_history',None)
    need(type(producer) is FunctionType and producer.__module__==jobs.__name__,
         'HOLD_OPERATOR_FIXED_CATALOG_UNIMPLEMENTED')
    # Load reviewed code only, without constructing a Host/Gate or Native read.
    from . import draft_group_host_review as reviewed_host
    _assert_fixed_references()
    from . import draft_group_runtime_host as gate
    frozen=[(original,code) for module,functions,_ in gate._HOST_NATIVE_TCB if module is jobs
            for name,original,code in functions if name=='operator_pins_for_history']
    need(len(frozen)==1 and frozen[0]==(producer,producer.__code__),
         'HOLD_OPERATOR_FIXED_CATALOG_UNIMPLEMENTED')
    pins=producer(policy,configuration_sha);_pins(pins)
    need(pins.configuration_sha==configuration_sha,'GROUP_OPERATOR_HISTORY_FIXED_LOCATOR')
    lease=current_physical_material_resources(db,policy)
    if lease is None:
        from .draft_group_artifact_resources import ArtifactResources
        owner=object();pool=PinPool(owner);artifacts=ArtifactResources(pool,owner=owner);owns=True
    else:pool,owner,artifacts=lease.check();owns=False
    files={};result=None
    try:
        files,_=_read_files(pins,pool,owner)
        values=_validate(pins,files,policy,live=False)
        selection=artifacts.selection(values['artifact_inventory'],pins.artifact_roots)
        for index,spec in enumerate(values['artifact_inventory']):
            pin=artifacts.acquire(selection,index,4*1024*1024 if spec['media_type']=='text/html' else MAXIMUM)
            need(len(pin.raw)==spec['size'],'GROUP_OPERATOR_HISTORY_ARTIFACT_SIZE')
            files['artifact:'+str(index)]=pin
        result=object.__new__(OperatorReviewHistoryMaterials)
        for key,value in values.items():object.__setattr__(result,key,value)
        attributes={'configuration_sha':pins.configuration_sha,'semantic_sha':pins.semantic_sha,
            'source_sha':pins.source_sha,'source_raw':files['source'].raw,'review_sha':pins.review_sha,
            'runtime_policy_sha':pins.runtime_source_policy_sha,
            'configuration_raw':files['configuration'].raw,'semantic_raw':files['semantic'].raw,
            'runtime_policy_raw':files['runtime_source_policy'].raw,'review_raw':files['review'].raw,
            'arm_raw':files['arm_receipt'].raw}
        for key,value in attributes.items():object.__setattr__(result,key,value)
        _MATERIALS[result]=(db,policy,history_locators,_transaction_marker(db),threading.get_ident(),
                            pool,owner,files,values,pins,owns,lease,artifacts,tuple(attributes.items()))
        result.collective_fence();return result
    except BaseException as original:
        if result is not None:_MATERIALS.pop(result,None)
        callbacks=[pin.close for pin in reversed(tuple(files.values()))]
        if owns:callbacks.extend((lambda:artifacts.close(original=original),
                                 lambda:pool.close(owner=owner,original=original)))
        close_all(callbacks,original);raise


@contextmanager
def operator_material_scope(materials):
    need(type(materials) is OperatorReviewHistoryMaterials,'GROUP_OPERATOR_HISTORY_MATERIALS_REQUIRED')
    try:
        materials.collective_fence()
        yield materials
    finally:materials.close(original=sys.exc_info()[1])
