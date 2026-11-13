"""Audited private selectors, fixed publisher and no-argument bootstrap.

A selector's table is compiled with its external acceptance/arm review. A model
cannot add it through MCP. Installation never creates a job or acquires tokens.
The current source12 has no adopted real eight-article entry; the explicit empty
table records that fact rather than guessing real native paths or approvals.
"""
from dataclasses import dataclass
from hashlib import sha256
import json
import os
import sys
from pathlib import Path
from weakref import ref

from .draft_group_runtime_host import need,hold,PinnedFile,canonical,digest
from .own_bootstrap_security import path_check,private_read
from .own_connection_policy import atomic_write,ConnectionPolicy
from .publication_contract import stable_account
from .draft_group_pin_resources import close_all

# Each trusted reviewed helper contributes an exact immutable tuple:
# (selector, stable_account_sha, candidate_scope, ordered_named_fixed_path_sha,
#  native_lookup_descriptors, artifact_root_descriptors, helper_paths, retention_paths).
# Paths never come from a public tool, configuration JSON or job pointer.
FIXED_JOB_TABLE=()
JOB_FILE='group-host-job.json'
_RUNTIME_PINS={}


def _compiled(policy,selector=None):
    need(type(policy) is ConnectionPolicy,'GROUP_FIXED_POLICY_REQUIRED')
    account=stable_account({'appid':policy.data['appid']})
    from .group_host_external_loader import loaded_catalog_rows
    rows=tuple(FIXED_JOB_TABLE)+tuple(item[0]for item in loaded_catalog_rows(policy))
    found=[row for row in rows if type(row) is tuple and len(row)==8 and row[1]==account
           and row[2]==policy.value['candidate_scope'] and (selector is None or row[0]==selector)]
    need(len(found)==1,'HOLD_FIXED_JOB_MISSING')
    return found[0]


def _row_pin(row,role,path,checksum):
    from .group_host_external_loader import _borrow_fixed_row_pin
    pin=_borrow_fixed_row_pin(row,role)
    if pin is None:return PinnedFile(Path(path),checksum,2*1024*1024)
    need(pin.path==Path(path) and pin.sha==checksum,'GROUP_FIXED_CATALOG_ROW_CHANGED')
    return pin


def _materialize(policy,row):
    from .draft_group_host_review import FixedHostPins
    from .draft_revision_native_lookup import NativeThreadLookup
    selector,account,scope,paths,lookup_specs,roots,helpers,retention=row
    named=dict(paths)
    need(set(named)=={'configuration','semantic','source','review','arm_receipt','unarmed','armed'},'GROUP_FIXED_JOB_TABLE')
    selected={}
    for name,(path,checksum) in named.items():
        item=_row_pin(row,name,path,checksum)
        try:selected[name]=(Path(path),checksum)
        finally:close_all((item.close,),sys.exc_info()[1])
    from .group_host_external_loader import loaded_catalog_rows
    extensions=[item[2]for item in loaded_catalog_rows()if item[0]==row and item[2]is not None]
    need(len(extensions)<=1,'GROUP_FIXED_CATALOG_DUPLICATE')
    extension=extensions[0]if extensions else None
    from .group_host_external_loader import OPERATOR_EXTENSION_PROFILE,OPERATOR_EXTENSION_ROLES
    if extension is not None and extension['profile']==OPERATOR_EXTENSION_PROFILE:
        from .draft_group_operator_review_chain import FixedOperatorHostPins
        need(not lookup_specs,'GROUP_OPERATOR_CATALOG_NATIVE_LOOKUP_FORBIDDEN')
        extra={}
        for role in OPERATOR_EXTENSION_ROLES:
            path,checksum=extension[role+'_path'],extension[role+'_sha']
            pin=_row_pin(row,role,path,checksum)
            try:extra[role+'_path']=Path(path);extra[role+'_sha']=checksum
            finally:close_all((pin.close,),sys.exc_info()[1])
        return FixedOperatorHostPins(**{name+suffix:value for name,(path,checksum) in selected.items()
            for suffix,value in (('_path',path),('_sha',checksum))},**extra,
            helper_files=tuple((Path(p),h) for p,h in helpers),
            artifact_roots=tuple((key,Path(p)) for key,p in roots),
            retention_evidence=tuple((Path(p),h) for p,h in retention))
    lookups=[];sources=[]
    for index,sessions,owner,threads in lookup_specs:
        lookup=NativeThreadLookup(Path(index),Path(sessions),owner,_PolicyPreparationGuard(policy),allowed_threads=threads)
        lookups.append(lookup)
        if extension is None:
            for thread in threads:sources.append(lookup.locate(thread))
    pins=FixedHostPins(**{name+suffix:value for name,(path,checksum) in selected.items()
        for suffix,value in (('_path',path),('_sha',checksum))},helper_files=tuple((Path(p),h) for p,h in helpers),
        registrations=tuple(sources),lookups=tuple(lookups),artifact_roots=tuple((key,Path(p)) for key,p in roots),
        retention_evidence=tuple((Path(p),h) for p,h in retention),
        runtime_source_policy=None if extension is None else (Path(extension['runtime_policy_path']),extension['runtime_policy_sha']),
        catalog_runtime_source=None if extension is None else json.loads(canonical(extension)))
    if extension is not None:_remember_runtime_pin(pins,policy.path,row,canonical(extension))
    return pins


def load_fixed_host_pins(policy):
    from .draft_group_rich_syn_fixture import rich_syn_host_pins_for_policy
    synthetic=rich_syn_host_pins_for_policy(policy)
    if synthetic is not None:return synthetic
    row=_compiled(policy)
    path=policy.root/JOB_FILE
    raw,pin=private_read(path)
    try:value=json.loads(raw)
    except (ValueError,UnicodeError):hold('GROUP_FIXED_JOB_POINTER')
    need(type(value) is dict and set(value)=={'schema','profile','authority','selector','account_key','candidate_scope','review_sha','configuration_sha'}
         and value['schema']==1 and type(value['schema']) is int and value['profile']=='GROUP_FIXED_HOST_JOB_V1'
         and value['authority'] is False and value['selector']==row[0] and value['account_key']==row[1]
         and value['candidate_scope']==row[2],'GROUP_FIXED_JOB_POINTER')
    named=dict(row[3]);need(value['review_sha']==named['review'][1] and value['configuration_sha']==named['configuration'][1],'GROUP_FIXED_JOB_POINTER')
    need(path_check(path)==pin,'GROUP_FIXED_JOB_CHANGED')
    return _materialize(policy,row)


def publish_fixed_host_job(policy):
    """Only the already-reviewed fixed helper calls this no-payload publisher.

    The table pins are checked before an idempotent pointer is written. The live
    Group Gate later performs actual native/QA/history qualification; a pointer
    alone never becomes a source seal or permission.
    """
    row=_compiled(policy);pins=_materialize(policy,row);named=dict(row[3])
    # External acceptance is checked against every fixed package byte here;
    # complete source/native/current validation is deliberately left to the Gate.
    selected={}
    for name,(path,checksum) in named.items():
        pin=_row_pin(row,name,path,checksum)
        try:selected[name]=pin.raw
        finally:close_all((pin.close,),sys.exc_info()[1])
    acceptance=json.loads(selected['review']);config=json.loads(selected['configuration'])
    need(acceptance.get('profile')in ('GROUP_HOST_REVIEW_ACCEPTANCE_V1','GROUP_HOST_RUNTIME_POLICY_ACCEPTANCE_V1','GROUP_OPERATOR_HOST_REVIEW_ACCEPTANCE_V1') and acceptance.get('authority') is False
         and acceptance.get('configuration_sha')==named['configuration'][1]
         and acceptance.get('source_material_sha')==named['source'][1]
         and acceptance.get('semantic_adoption_sha')==named['semantic'][1]
         and acceptance.get('unarmed_sha')==named['unarmed'][1]
         and config.get('candidate_scope')==row[2],'GROUP_FIXED_JOB_ACCEPTANCE')
    from .draft_group_host_review import _arm_ast
    left,a=_arm_ast(selected['unarmed']);right,b=_arm_ast(selected['armed'])
    need(left==right,'GROUP_FIXED_JOB_ARM')
    pointer={'schema':1,'profile':'GROUP_FIXED_HOST_JOB_V1','authority':False,'selector':row[0],
        'account_key':row[1],'candidate_scope':row[2],'review_sha':named['review'][1],'configuration_sha':named['configuration'][1]}
    path=policy.root/JOB_FILE
    if path.exists():
        actual,_=private_read(path);need(actual==(canonical(pointer)+'\n').encode(),'GROUP_FIXED_JOB_CONFLICT')
    else:atomic_write(path,pointer)
    load_fixed_host_pins(policy)
    return {'state':'FIXED_JOB_POINTER_PUBLISHED','authority':False,'selector':row[0]}


_CHILD_BODY="""import sys
sys.path.insert(0,CORE_ROOT)
from wce.group_host_jobs import run_fixed
run_fixed()
"""
_CHILD_KEYS=('CORE_ROOT','CORE_SCOPE','POLICY_PATH','POLICY_SHA','CONFIGURATION_PATH','CONFIGURATION_SHA',
    'SEMANTIC_PATH','SEMANTIC_SHA','SOURCE_PATH','SOURCE_SHA','UNARMED_PATH','ARMED_PATH','ARM_RECEIPT_PATH',
    'LOOKUP_SPECS','ARTIFACT_ROOTS','HELPERS','RETENTION','REVIEW_PATH','REVIEW_SHA')
_CHILD_INVOCATIONS={}


def render_unarmed_helper(constants):
    """Maintenance compiler output. Future H/A/U are locators, never hashes."""
    need(type(constants)is dict and set(constants)==set(_CHILD_KEYS),'GROUP_FIXED_UNARMED_CONSTANTS')
    need(constants['REVIEW_PATH']is None and constants['REVIEW_SHA']is None,'GROUP_FIXED_UNARMED_REVIEW')
    from .draft_group_input_files import _plain
    # Technical descriptor tuples are encoded as literal lists before this
    # pure compiler; no caller object may dispatch repr during rendering.
    _plain(constants)
    return (''.join(key+'='+repr(constants[key])+'\n'for key in _CHILD_KEYS)+_CHILD_BODY).encode()


@dataclass(frozen=True)
class _ChildInvocationFacts:
    file:object
    constants:dict
    control:object
    parent_pid:int
    request:dict
    thread:int
    resources:object


class _ChildInvocation:
    def __init__(self,*args,**kwargs):hold('GROUP_FIXED_INVOCATION_ISSUER_REQUIRED')


def validate_child_invocation(value):
    import threading
    from .own_bootstrap_ipc import peer
    facts=_CHILD_INVOCATIONS.get(value)
    need(type(value)is _ChildInvocation and facts is not None and facts.thread==threading.get_ident()
         and peer(facts.control)==(facts.parent_pid,os.getuid())and facts.parent_pid==os.getppid(), 'GROUP_FIXED_CHILD_PEER')
    facts.file.check()
    return facts


def run_fixed():
    """Actual -I absolute H entry, not package POLICY placeholders."""
    import ast,inspect,socket,time,threading,sys
    from .own_bootstrap_ipc import peer,receive
    from .own_connection_broker import _ClientCancellationGuard
    frame=inspect.currentframe().f_back;file=None;invocation=None;control=None;resources=None
    try:
        path=Path(frame.f_code.co_filename)
        need(frame.f_globals.get('__name__')=='__main__' and frame.f_globals.get('__file__')==str(path)
             and Path(sys.argv[0]).absolute()==path,'GROUP_FIXED_CHILD_ORIGIN')
        raw,temporary_pin=private_read(path)
        from .group_host_external_loader import _CatalogResources
        resources=_CatalogResources()
        file=resources.pin(path,sha256(raw).hexdigest(),2*1024*1024)
        need(file.raw==raw and frame.f_code==compile(raw,str(path),'exec'),'GROUP_FIXED_CHILD_CODE')
        tree=ast.parse(raw);constants={}
        for node in tree.body[:len(_CHILD_KEYS)]:
            need(type(node)is ast.Assign and len(node.targets)==1 and type(node.targets[0])is ast.Name,'GROUP_FIXED_CHILD_CONSTANTS')
            key=node.targets[0].id;need(key in _CHILD_KEYS and key not in constants,'GROUP_FIXED_CHILD_CONSTANTS')
            constants[key]=ast.literal_eval(node.value)
        from .draft_group_input_files import _plain
        _plain(constants)
        expected=(''.join(key+'='+repr(constants[key])+'\n'for key in _CHILD_KEYS)+_CHILD_BODY).encode()
        need(raw==expected and constants['ARMED_PATH']==str(path)
             and type(constants['REVIEW_PATH'])is str and type(constants['REVIEW_SHA'])is str,'GROUP_FIXED_CHILD_CODE')
        from .own_body_recovery import code_scope
        need(Path(__file__).absolute()==Path(constants['CORE_ROOT'])/'wce/group_host_jobs.py'
             and code_scope()==constants['CORE_SCOPE'],'GROUP_FIXED_CHILD_CORE')
        fd=os.environ.get('WCE_GROUP_STARTUP_FD');need(type(fd)is str and fd.isdigit(),'GROUP_FIXED_CHILD_CONTROL_REQUIRED')
        control=socket.socket(fileno=int(fd));control.settimeout(60)
        need(peer(control)==(os.getppid(),os.getuid()),'GROUP_FIXED_CHILD_PEER')
        with control,control.makefile('rwb')as stream:
            envelope=receive(stream)
            need(type(envelope)is dict and set(envelope)=={'schema','profile','loader_anchor','request'}
                 and type(envelope['schema'])is int and envelope['schema']==1
                 and envelope['profile']=='GROUP_FIXED_CHILD_CATALOG_ENVELOPE_V1','GROUP_FIXED_CHILD_REQUEST')
            request=envelope['request']
            from .draft_group_child_control import PUBLIC_START
            public_start=type(request)is dict and request.get('profile')==PUBLIC_START
            if not public_start:
                need(type(request)is dict and set(request)=={'schema','profile','selector_sha','absolute_deadline'}
                     and type(request['schema'])is int and request['schema']==1 and request['profile']=='GROUP_FIXED_CHILD_START_V1', 'GROUP_FIXED_CHILD_REQUEST')
            need(type(request)is dict and 'selector_sha'in request and 'absolute_deadline'in request,'GROUP_FIXED_CHILD_REQUEST')
            deadline=request['absolute_deadline'];now=time.monotonic()
            need(type(deadline)in (int,float)and now<deadline<=now+300,'GROUP_FIXED_CHILD_DEADLINE')
            invocation=object.__new__(_ChildInvocation)
            _CHILD_INVOCATIONS[invocation]=_ChildInvocationFacts(file,constants,control,os.getppid(),{'selector_sha':request['selector_sha'],'loader_anchor':envelope['loader_anchor']},threading.get_ident(),resources)
            from .group_host_external_loader import install_child_process_catalog
            install_child_process_catalog(invocation)
            from .own_connection_policy import load_policy
            from .group_host_external_loader import catalog_rows
            matches=[row for row,pair,extension in catalog_rows()if pair==(constants['POLICY_PATH'],constants['POLICY_SHA'])]
            need(len(matches)==1,'GROUP_FIXED_CHILD_INVOCATION_BINDING')
            policy_pin=_row_pin(matches[0],'policy',constants['POLICY_PATH'],constants['POLICY_SHA'])
            try:
                policy=load_policy(Path(constants['POLICY_PATH']));pins=load_fixed_host_pins(policy)
                from .draft_group_host_bootstrap import run_fixed_bootstrap
                if public_start:
                    from .draft_group_child_control import validate_public_start,public_request_sha
                    public=validate_public_start(request,connection_id=policy.data['connection_id'],selector_sha=pins.configuration_sha)
                    return run_fixed_bootstrap(policy,pins,request_name=public['name'],request_arguments=public['arguments'],
                        received_deadline=public['absolute_deadline'],native_cancel=_ClientCancellationGuard(control),
                        startup_stream=stream,startup_request_sha=public_request_sha(public))
                return run_fixed_bootstrap(policy,pins,received_deadline=deadline,native_cancel=_ClientCancellationGuard(control),startup_stream=stream)
            finally:close_all((policy_pin.close,),sys.exc_info()[1])
    finally:
        original=sys.exc_info()[1]
        from .group_host_external_loader import close_process_catalog
        if invocation is not None:_CHILD_INVOCATIONS.pop(invocation,None)
        callbacks=([file.close]if file is not None else [])
        callbacks += ([control.close]if control is not None else [])
        callbacks += [lambda:close_process_catalog(original=original)]
        if resources is not None:callbacks.append(lambda:resources.close(original=original))
        del frame
        close_all(callbacks,original)


def run_fixed_broker():
    from .group_host_external_loader import close_process_catalog
    try:
        from .group_host_external_loader import catalog_rows
        from .own_connection_policy import load_policy
        from .own_body_recovery import code_scope
        rows=[item for item in catalog_rows()if item[0][2]==code_scope()]
        need(len(rows)==1,'GROUP_FIXED_BROKER_SELECTION')
        row,pair,extension=rows[0]
        pin=_row_pin(row,'policy',pair[0],pair[1])
        try:
            policy=load_policy(Path(pair[0]));pins=load_fixed_host_pins(policy)
            from .draft_group_host_bootstrap import run_fixed_bootstrap
            return run_fixed_bootstrap(policy,pins)
        finally:close_all((pin.close,),sys.exc_info()[1])
    finally:close_process_catalog(original=sys.exc_info()[1])


class _PolicyPreparationGuard:
    def __init__(self,policy):self.policy=policy
    def __call__(self):
        from .draft_group_runtime_host import GroupExecutionGate,_ACTIVE,_REGISTRY,_THREAD,_method
        entry=getattr(_ACTIVE,'entry',None)
        if (type(entry) is GroupExecutionGate and entry.policy is self.policy and entry.thread==_THREAD()
                and _REGISTRY.get(entry.id) is entry and not entry.closed):
            need(_method(entry,GroupExecutionGate,'loop_guard') and _method(entry,GroupExecutionGate,'held_pure')
                 and _method(entry,GroupExecutionGate,'full_guard'),'GROUP_HOST_CODE_CHANGED')
            return entry.loop_guard()
        self.policy.check()
        return True



def _forget_runtime_pin(key,reference):
    current=_RUNTIME_PINS.get(key)
    if current is not None and current[0]is reference:_RUNTIME_PINS.pop(key,None)


def _remember_runtime_pin(pins,policy_path,row,extension_raw):
    key=id(pins)
    reference=ref(pins,lambda original:_forget_runtime_pin(key,original))
    _RUNTIME_PINS[key]=(reference,(policy_path,row,extension_raw))


def _runtime_pin_record(pins):
    current=_RUNTIME_PINS.get(id(pins))
    if current is None:return None
    need(current[0]()is pins,'GROUP_NATIVE_V2_FIXED_PIN_IDENTITY_CHANGED')
    return current[1]


def runtime_policy_pin_for(pins,policy):
    original=_runtime_pin_record(pins)
    if original is None:
        from .draft_group_rich_syn_fixture import rich_syn_runtime_policy_pin_for
        synthetic=rich_syn_runtime_policy_pin_for(pins,policy)
        need(synthetic is not None,'GROUP_NATIVE_V2_FIXED_CATALOG_REQUIRED')
        return synthetic
    need(original[0]==policy.path,'GROUP_NATIVE_V2_FIXED_CATALOG_REQUIRED')
    from .group_host_external_loader import loaded_catalog_rows
    selected=[item for item in loaded_catalog_rows()if item[0]==original[1]and canonical(item[2])==original[2]]
    need(len(selected)==1,'GROUP_NATIVE_V2_CATALOG_CHANGED')
    extension=json.loads(original[2]);pair=(Path(extension['runtime_policy_path']),extension['runtime_policy_sha'])
    need(pins.runtime_source_policy==pair and canonical(pins.catalog_runtime_source)==original[2],'GROUP_NATIVE_V2_PIN_CHANGED')
    return pair[0],pair[1],extension


def fixed_history_rows(policy,configuration_sha):
    from .group_host_external_loader import loaded_catalog_rows
    from .publication_contract import stable_account
    rows=tuple(FIXED_JOB_TABLE)+tuple(item[0]for item in loaded_catalog_rows())
    account=stable_account({'appid':policy.data['appid']})
    return [r for r in rows if r[1]==account and dict(r[3])['configuration'][1]==configuration_sha]


def native_v2_pins_for_history(policy,configuration_sha):
    from .draft_group_rich_syn_fixture import rich_syn_native_v2_history_pins
    synthetic=rich_syn_native_v2_history_pins(policy,configuration_sha)
    if synthetic is not None:return synthetic
    rows=fixed_history_rows(policy,configuration_sha)
    need(len(rows)==1,'GROUP_HISTORY_FIXED_LOCATOR_REQUIRED')
    # Materialization for M0 opens only fixed technical files/lookup objects;
    # it does not locate a Native session, read its header, or start S0.
    pins=_materialize(policy,rows[0]);runtime_policy_pin_for(pins,policy)
    return pins


def operator_pins_for_history(policy,configuration_sha):
    """Only an existing authenticated catalog row; never a caller path table."""
    from .group_host_external_loader import loaded_catalog_rows,OPERATOR_EXTENSION_PROFILE
    from .draft_group_operator_review_chain import FixedOperatorHostPins
    rows=fixed_history_rows(policy,configuration_sha)
    selected=[row for row,pair,extension in loaded_catalog_rows()
              if row in rows and extension is not None and extension['profile']==OPERATOR_EXTENSION_PROFILE]
    need(len(selected)==1,'GROUP_OPERATOR_HISTORY_FIXED_LOCATOR_REQUIRED')
    pins=_materialize(policy,selected[0])
    need(type(pins) is FixedOperatorHostPins,'GROUP_OPERATOR_HISTORY_FIXED_LOCATOR_REQUIRED')
    return pins


def wrap_child_start_request(request):
    from .group_host_external_loader import process_loader_anchor
    from .draft_group_input_files import _plain
    _plain(request)
    return {'schema':1,'profile':'GROUP_FIXED_CHILD_CATALOG_ENVELOPE_V1',
        'loader_anchor':process_loader_anchor(),'request':json.loads(canonical(request))}
