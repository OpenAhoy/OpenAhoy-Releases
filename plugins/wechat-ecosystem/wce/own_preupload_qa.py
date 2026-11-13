"""Strict fixed Operator QA-import facts; JSON alone never grants QA authority.

Current task observations are not official signatures, and missing historical
controller packages stay unproven. The import is limited to preupload content;
current Owned history, settings effects and Group rights remain separate.
"""
from hashlib import sha256
import json
import math
import inspect
import os
from pathlib import Path
import re
import threading
import time
import weakref

from .contracts import WCEError

CONTRACT_SHA256 = 'cd29ccbc2b2ee688c69cfdb04e4b50443eaa653729c20712f6f27a3bc5956d9d'
MAX_BYTES = 2 * 1024 * 1024
_HASH = re.compile('[0-9a-f]{64}\\Z')
_ID = re.compile('[A-Za-z0-9][A-Za-z0-9_.:/-]{0,255}\\Z')
_SECRET = re.compile(r'app[_-]?secret|(?:access|refresh)[_-]?token|api[_-]?key|password|authorization|cookie|\bbearer\s+|-----BEGIN .*PRIVATE KEY',re.I)
_Q_KEYS = frozenset(('schema','profile','authority','contract_sha256','assignment_id',
    'assignment_sha256','attempt','task_name','refs','selection_sha256','input_index_sha256',
    'current_rule_set_sha256','member_set_sha256','coverage_relation','not_after_wall','claims'))
_A_KEYS = frozenset(('schema','profile','authority','contract_sha256','dossier_ref','core_scope',
    'consumer_sources','binding_projection_sha256','external_review_ref','observation_assurance',
    'accepted_scope','unresolved','retention_refs','permitted_binding_change'))
_MAIN_REFS = frozenset(('assignment','dispatch','parent_observation','report','coverage',
    'file_audit','metadata_audit','metadata_scope_supplement','metadata_observation','input_index','current_rules'))
_VISUAL_REFS = frozenset(('assignment','dispatch','parent_observation','report','coverage'))
_UNRESOLVED = frozenset(('HISTORICAL_CONTROLLER_PACKAGE_UNPROVEN','SETTINGS_INTENT_PENDING',
    'PLATFORM_EFFECT_NOT_VERIFIED','HTML_FULL_RENDER_NOT_VERIFIED','GROUP_CURRENT_OWNED_PENDING'))
CONSUMER_FILES = (
    'own_preupload_qa.py','own_preupload_entry.py','own_preupload_sources.py',
    'own_preupload_protocol.py','own_preupload_launcher.py','own_preupload_domain.py',
    'own_preupload_inputs.py','own_preupload_journal.py','own_preupload_selected_files.py',
    'own_preupload_derivation.py','draft_group_selected_source_codec.py',
    'own_preupload_child_journal.py',
    'own_selected_history.py','own_prepared_history.py','own_workflow.py',
    'own_connection_broker.py','own_bootstrap_security.py','draft_group_pin_resources.py',
    'local_html_import.py','import_images.py','documents.py','html_document.py',
    'draft_group_source_members.py','own_validation_scope.py','own_content_qa_join.py')


def hold():
    raise WCEError('PREUPLOAD_QA_IMPORT_HOLD')


def need(value):
    if value is not True:hold()


def closed(value, keys):
    need(type(value) is dict and set(value)==set(keys))


def checksum(value):
    need(type(value) is str and _HASH.fullmatch(value) is not None)


def identifier(value):
    need(type(value) is str and _ID.fullmatch(value) is not None)


def wall(value):
    need(type(value) in (int,float) and math.isfinite(value) and 0<value<2**53)


def reference(value):
    closed(value,('path','sha256','bytes'))
    need(type(value['path']) is str)
    path=Path(value['path'])
    need(path.is_absolute() and '..' not in path.parts and len(path.parts)<=32)
    checksum(value['sha256'])
    need(type(value['bytes']) is int and 0<value['bytes']<=MAX_BYTES)


def _plain(value):
    stack=[(value,0)];remaining=65536
    while stack:
        item,depth=stack.pop();remaining-=1
        need(remaining>=0 and depth<=20)
        if type(item) is dict:
            need(len(item)<=4096 and all(type(key) is str for key in item))
            stack.extend((key,depth+1) for key in item)
            stack.extend((child,depth+1) for child in item.values())
        elif type(item) is list:
            need(len(item)<=4096);stack.extend((child,depth+1) for child in item)
        elif type(item) is str:
            need(len(item)<=4096 and not any(ord(char)<32 or ord(char)==127 for char in item)
                 and _SECRET.search(item) is None)
        elif type(item) is int:
            need(0<=item<2**63)
        elif type(item) is float:
            need(math.isfinite(item) and 0<=item<2**53)
        else:
            need(type(item) in (bool,type(None)))


def canonical(value):
    _plain(value)
    try:raw=json.dumps(value,sort_keys=True,separators=(',',':'),ensure_ascii=False,allow_nan=False).encode('utf-8')
    except (TypeError,ValueError,UnicodeError,RecursionError):hold()
    need(0<len(raw)<=MAX_BYTES)
    return raw


def _pairs(rows):
    result={}
    for key,value in rows:
        need(key not in result);result[key]=value
    return result


def _decode(raw,keys,profile):
    need(type(raw) is bytes and 0<len(raw)<=MAX_BYTES)
    try:value=json.loads(raw.decode('utf-8'),object_pairs_hook=_pairs,parse_constant=lambda _:hold())
    except (ValueError,UnicodeError,RecursionError,OverflowError):hold()
    closed(value,keys)
    need(type(value['schema']) is int and value['schema']==1
         and value['profile']==profile and value['authority'] is False
         and value['contract_sha256']==CONTRACT_SHA256 and canonical(value)==raw)
    return value


def _checks(value):
    need(type(value) is list and len(value)>0 and all(type(item) is str for item in value))
    need(len(set(value))==len(value) and all(re.fullmatch(r'C(?:0[1-9]|10)',item) for item in value))


def decode_import_dossier(raw):
    value=_decode(raw,_Q_KEYS,'QA03_OPERATOR_IMPORT_DOSSIER_V1')
    for key in ('assignment_sha256','selection_sha256','input_index_sha256',
                'current_rule_set_sha256','member_set_sha256'):checksum(value[key])
    identifier(value['assignment_id'])
    need(type(value['task_name']) is str and re.fullmatch(r'/root(?:/[a-z0-9_]+){1,8}',value['task_name']) is not None)
    need(type(value['attempt']) is int and 1<=value['attempt']<=109)
    wall(value['not_after_wall'])
    refs=value['refs'];closed(refs,('main','visual_supplement'))
    closed(refs['main'],_MAIN_REFS);closed(refs['visual_supplement'],_VISUAL_REFS)
    for kind,items in refs.items():
        for role,ref in items.items():
            if kind=='main' and role=='current_rules':
                need(type(ref) is list and len(ref)==2)
                for rule in ref:reference(rule)
            else:reference(ref)
    relation=value['coverage_relation']
    closed(relation,('profile','report_claim_type','decision_scope','required_content_check_ids','report_check_mapping_sha256'))
    need(relation['profile']=='QA03_MIXED_CURRENT_COVERAGE_RELATION_V1'
         and relation['report_claim_type']=='CURRENT_ADOPTION_OF_PRIOR_INDEPENDENT_CONTENT_QA_V1'
         and relation['decision_scope']=='PREUPLOAD_CONTENT_ONLY')
    _checks(relation['required_content_check_ids']);checksum(relation['report_check_mapping_sha256'])
    need(value['claims']=={'original_historical_runtime':'NOT_PROVEN',
        'platform_run_origin':'OPERATOR_ATTESTED_CURRENT_TASK','platform_effect':'NOT_ASSERTED',
        'group_authority':'NOT_ASSERTED'})
    return value


def decode_import_acceptance(raw):
    value=_decode(raw,_A_KEYS,'QA03_FIXED_IMPORT_ACCEPTANCE_V1')
    for key in ('core_scope','binding_projection_sha256'):checksum(value[key])
    for key in ('dossier_ref','external_review_ref'):reference(value[key])
    for key in ('consumer_sources','retention_refs'):
        refs=value[key];need(type(refs) is list and 1<=len(refs)<=64)
        for ref in refs:reference(ref)
        need(len({ref['path'] for ref in refs})==len(refs))
    need(value['observation_assurance']=='TRUSTED_OPERATOR_PARENT_OBSERVATION'
         and value['permitted_binding_change']=='ADD_EXACT_QA_REFS')
    scope=value['accepted_scope']
    closed(scope,('purpose','selection_sha256','member_set_sha256','required_check_ids','coverage_mapping_ref','not_after_wall'))
    need(scope['purpose']=='PREUPLOAD_CONTENT_ONLY')
    for key in ('selection_sha256','member_set_sha256'):checksum(scope[key])
    _checks(scope['required_check_ids']);reference(scope['coverage_mapping_ref']);wall(scope['not_after_wall'])
    unresolved=value['unresolved']
    need(type(unresolved) is list and all(type(item) is str and item in _UNRESOLVED for item in unresolved)
         and len(set(unresolved))==len(unresolved)
         and 'HISTORICAL_CONTROLLER_PACKAGE_UNPROVEN' in unresolved
         and 'PLATFORM_EFFECT_NOT_VERIFIED' in unresolved)
    return value


def _evidence_json(resources, ref):
    reference(ref)
    raw=resources.acquire_evidence(ref).raw
    try:value=json.loads(raw.decode('utf-8'),object_pairs_hook=_pairs,parse_constant=lambda _:hold())
    except (ValueError,UnicodeError,RecursionError):hold()
    # Existing reports/observations keep their actual original serialization.
    # Their full held SHA, not re-serialization, binds them to the fixed Q/A.
    need(type(value) is dict)
    return value


def _same_ref(outer, inner):
    need(type(inner) is dict and set(inner)=={'path','sha256'}
         and outer['path']==inner['path'] and outer['sha256']==inner['sha256'])


def _observation(resources, ref, assignment, assignment_ref, task, report_refs, *, visual):
    value=_evidence_json(resources,ref)
    keys={'schema','profile','authority','assignment_id','assignment_sha256','owned_task_name',
        'observed_event_type','observed_terminal','observed_at_wall','exact_platform_finished_at',
        'official_signature','full_tool_trace','cancellation_request','report_refs',
        'formal_runtime_qa_issued','past_deadline_at_collection'}
    keys.add('dispatch_observation' if visual else 'source_scope_supplement')
    closed(value,keys)
    need(type(value['schema']) is int and value['schema']==1 and value['authority'] is False
         and value['profile']=='PLATFORM_CONTROLLER_TERMINAL_OBSERVATION_FACT_V1'
         and value['assignment_id']==assignment['assignment_id']
         and value['assignment_sha256']==assignment_ref['sha256'] and value['owned_task_name']==task
         and value['observed_event_type']=='collaboration automatic FINAL_ANSWER'
         and value['observed_terminal']=='FINAL_ANSWER_RECEIVED'
         and value['exact_platform_finished_at']=='UNAVAILABLE'
         and value['official_signature']=='UNAVAILABLE_NOT_REQUIRED_OR_CLAIMED'
         and value['full_tool_trace']=='UNAVAILABLE_NOT_CLAIMED'
         and value['cancellation_request']=='NOT_SENT_BY_THIS_CONTROLLER'
         and value['formal_runtime_qa_issued'] is False and value['past_deadline_at_collection'] is False)
    for key in ('observed_at_wall',):wall(value[key])
    wall(assignment['assigned_at_wall']);wall(assignment['not_after_wall'])
    need(assignment['assigned_at_wall']<=value['observed_at_wall']<assignment['not_after_wall'])
    for name,ref_value in report_refs.items():_same_ref(ref_value,value['report_refs'][name])
    return value


def check_import_package(resources, *, dossier_ref, acceptance_ref, selection_sha256,
                         binding_projection_sha256, member_ids, selected_roots):
    """Actual PREUPLOAD owner guard; shared join returns facts only."""
    from .own_preupload_sources import _HeldPreuploadSources
    need(type(resources) is _HeldPreuploadSources and not resources.closed)
    resources.guard()
    from .own_content_qa_join import check_import_package_contents
    return check_import_package_contents(resources,dossier_ref=dossier_ref,
        acceptance_ref=acceptance_ref,selection_sha256=selection_sha256,
        binding_projection_sha256=binding_projection_sha256,member_ids=member_ids,
        selected_roots=selected_roots,expected_consumer_files=CONSUMER_FILES)


class QualifiedPreuploadContentQa:
    """A live private service-scoped content result, never an upload grant."""
    def __init__(self,*args,**kwargs):
        raise WCEError('PREUPLOAD_QA_ISSUER_REQUIRED')


_QUALIFIED = weakref.WeakKeyDictionary()


def _issue_preupload_qa(entry,service):
    from . import own_preupload_entry as entries
    from .own_preupload_domain import PreuploadSessionService
    from .draft_group_selected_source_codec import decode_manifest
    need(inspect.currentframe().f_back.f_code is PreuploadSessionService.__init__.__code__
         and type(service) is PreuploadSessionService and service.entry is entry
         and service.qa is None)
    view=entries.require_service_entry(entry,service,service.core)
    record=entries._record(entry)
    resources=record.resources;binding=resources.values()
    selection,_,_=decode_manifest(view.selection_raw,
        expected_member_projection=tuple(tuple(row) for row in binding['member_projection']))
    member_ids=tuple(row['article_id'] for row in selection['members'])
    projection_sha=sha256(canonical({key:value for key,value in binding.items() if key!='qa'})).hexdigest()
    facts=check_import_package(resources,**binding['qa'],selection_sha256=view.selection_sha256,
        binding_projection_sha256=projection_sha,member_ids=member_ids,selected_roots=service.inputs.roots)
    service.inputs.check_current(service)
    result=object.__new__(QualifiedPreuploadContentQa)
    _QUALIFIED[result]={'entry':entry,'service':service,'core':service.core,
        'owner':(os.getpid(),threading.get_ident()),'active':True,
        'policy':canonical(service.policy.value),'facts':canonical(facts),
        'members':canonical({row['article_id']:[image['slot'] for image in row['images']]
            for row in selection['members']})}
    return result


def require_preupload_qa(value,*,entry,service,member_identity=None,slot_identity=None):
    from . import own_preupload_entry as entries
    need(type(value) is QualifiedPreuploadContentQa)
    record=_QUALIFIED.get(value)
    need(record is not None and record['active'] is True and record['entry'] is entry
         and record['service'] is service and record['core'] is service.core
         and service.qa is value
         and record['owner']==(os.getpid(),threading.get_ident())
         and record['policy']==canonical(service.policy.value))
    view=entries.require_service_entry(entry,service,service.core)
    resources=entries._record(entry).resources
    facts=json.loads(record['facts'])
    need(time.time()<facts['not_after_wall'] and facts['selection_sha256']==view.selection_sha256)
    # Every referenced evidence/file/source remains held for this service.
    resources.guard();service.inputs.check_current(service)
    if member_identity is not None:
        members=json.loads(record['members'])
        need(member_identity in members
             and (slot_identity is None or slot_identity in members[member_identity]))
    else:need(slot_identity is None)
    need(time.time()<facts['not_after_wall'] and time.monotonic()<view.deadline)
    return True


def revoke_preupload_qa(value,*,entry,service):
    if value is None:return
    need(type(value) is QualifiedPreuploadContentQa)
    record=_QUALIFIED.get(value)
    need(record is not None and record['entry'] is entry and record['service'] is service
         and record['owner']==(os.getpid(),threading.get_ident()))
    record['active']=False
    del _QUALIFIED[value]
