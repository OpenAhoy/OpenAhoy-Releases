"""Unarmed fixed first-prepare + normal-Parent-readback proposal.

Only the existing private F/E invocation may reserve/drain/start. The Parent
receipt is issued after the actual normal writer context returns and a distinct
fresh Owned/H replays the same complete Parent and children. No JSON is a grant.
"""
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass,replace
from hashlib import sha256
import inspect
import json
import math
import os
from pathlib import Path
import socket
import stat
import subprocess
import sys
import threading
import time
from weakref import WeakKeyDictionary

from .contracts import WCEError
from .draft_group_contracts import canonical,digest
from .draft_group_preparent_journal import (PreParentJournal,validate_anchor,
    preparation_identity,validate_observation,full,close_all,capacity,HISTORICAL_ATTACHMENT_ORIGIN)

ROOT_NAME='group-first-preparation'
_START=ContextVar('fixed_operator_first_start',default=None)
_WRITE=ContextVar('fixed_operator_first_parent_write',default=None)
_FRESH=ContextVar('fixed_operator_first_parent_readback',default=None)
_RECOVERY=ContextVar('fixed_operator_first_historical_recovery',default=None)
_HOSTS=WeakKeyDictionary();_SUBMITTED=WeakKeyDictionary();_RECEIPTS=WeakKeyDictionary()
_RECOVERY_RECEIPTS=WeakKeyDictionary()
_RECOVERY_SPENT=WeakKeyDictionary()
_RECOVERY_BIND=ContextVar('fixed_group_historical_attachment',default=None)
_CHILDREN={}  # Strong handles survive every unknown in this F; never kill H.
MAPPING_PROFILE='GROUP_OPERATOR_BOUND_REAL_PARENT_MAPPING_V1'
MAPPING_KEYS=('schema','profile','authority','anchor_sha','preparation_identity_sha',
    'binding_sha','operator_request_identity_sha','original_request_set_sha','account_partition_sha',
    'family_id','first_covenant_sha','first_proof_sha','registration_sha','registration_proof_sha',
    'source_material_sha','current_source_review_sha','semantic_scope_sha','preview_sha','settings_sha',
    'parent_sha','parent','children','parent_event','plan_event','not_after_ms')
PLAN_CHILD_KEYS=('schema','state','executable','candidate_activation','ordinal','child_key',
    'operation_id','target_group_id','target_generation','route','member_count','main_article_id',
    'members','old_ref_set','main_changes','budget','settings','digest_projection',
    'retirement_required','platform_completion')


def need(value,code):
    if value is not True:raise WCEError('GROUP_FIRST_'+code)


def _sha(value):
    need(type(value) is str and len(value)==64 and all(c in '0123456789abcdef' for c in value),'HASH')


def _identity(policy):
    from .own_selected_history import _policy_binding
    binding=_policy_binding(policy,'OPERATOR_ATTESTED')
    return {key:binding[key] for key in ('tenant','principal','connection','resource','account')}


def anchor_from_source(policy,source):
    from .draft_group_operator_source_codec import validate_source
    value=validate_source(source)
    return validate_anchor({'schema':1,'profile':'GROUP_OPERATOR_PRE_PARENT_ANCHOR_V1',
        'authority':False,'action':'FIRST_PREPARE','binding_identity':_identity(policy),
        'original_queue_sha':value['original_queue_sha'],
        'original_request_identity_sha':value['operator_request_identity_sha'],
        'original_request_set_sha':value['original_request_set_sha'],
        'account_partition_sha':value['account_partition_sha']})


def _root(policy,*,create):
    """Only the adopted stable account state path; no free path argument."""
    from .own_bootstrap_security import path_check
    before=path_check(policy.root,True)
    need(before[:2]==policy.root_pin,'ACCOUNT_ROOT_CHANGED')
    fd=None;original=None
    try:
        capacity(1)
        fd=os.open(policy.root,os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW|os.O_NONBLOCK)
        need(full(os.fstat(fd))[:2]==policy.root_pin,'ACCOUNT_ROOT_CHANGED')
        if create:
            try:os.mkdir(ROOT_NAME,0o700,dir_fd=fd)
            except FileExistsError:pass
            os.fsync(fd)
        value=policy.root/ROOT_NAME
        info=value.lstat()
        need(stat.S_ISDIR(info.st_mode) and info.st_uid==os.getuid()
             and stat.S_IMODE(info.st_mode)==0o700,'TECHNICAL_ROOT_UNSAFE')
        path_check(value,True)
        if not create:
            # RO consumers do not initialize a missing/partial journal.
            need(os.path.lexists(value/'account.lock')
                 and os.path.lexists(value/'account.json'),'PARTIAL_TECHNICAL_ROOT')
        need(path_check(policy.root,True)==before,'ACCOUNT_ROOT_CHANGED')
        return value
    except BaseException as error:original=error;raise
    finally:
        if fd is not None:close_all([lambda:os.close(fd)],original)


def _observation(policy,pins,source,runtime,deadline):
    wall,mono=time.time(),time.monotonic()
    caps=[source['expires_policy']['not_after']*1000,runtime['original_input_not_after_ms'],
          int((wall+deadline-mono)*1000)]
    rights=runtime['source_rights_expiry']
    if rights['not_after'] is not None:caps.append(rights['not_after'])
    return validate_observation({'candidate_sha':policy.value['candidate_scope'],
        'source_sha':pins.source_sha,'binding_sha':digest(runtime['binding']),
        'policy_sha':digest(policy.value),'epoch':policy.data['epoch'],
        'not_after_ms':min(caps)})


@dataclass
class _Start:
    policy:object
    invocation:object
    pins:object
    anchor:dict
    journal:object
    head_sha:str
    observation:dict
    deadline:float
    loader_anchor:object
    owner:tuple


def _start_check(value):
    need(type(value) is _Start and _START.get() is value
         and value.owner==(os.getpid(),threading.get_ident()),'START_CONTEXT_REQUIRED')
    from .group_host_external_loader import check_private_preparation,check_process_loader_anchor
    need(check_private_preparation(value.invocation,value.policy)==value.deadline,'DEADLINE_CHANGED')
    check_process_loader_anchor(value.loader_anchor)
    need(time.monotonic()<value.deadline
         and time.time()*1000<value.observation['not_after_ms'],'EXPIRED')
    value.journal.check()
    current=value.journal.inspect()[digest(value.anchor)]
    need(current['head_sha']==value.head_sha and current['state']=='NOT_CREATED','TECHNICAL_HEAD_CHANGED')
    return value


def _note_start(value,event):
    _start_check(value)
    result=value.journal.note(value.anchor,expected_head_sha=value.head_sha,event=event,
                              observation=value.observation)
    value.head_sha=result['head_sha'];_start_check(value)


def _lifetime_pin(policy):
    from .own_bootstrap_security import path_check
    path=policy.root/'connection.lock';path_check(path)
    info=path.lstat()
    need(stat.S_ISREG(info.st_mode) and info.st_uid==os.getuid()
         and stat.S_IMODE(info.st_mode)==0o600 and info.st_nlink==1 and info.st_size==0,
         'LIFETIME_LOCK_UNSAFE')
    return full(info)


def _wait_release(value,expected,lifetime_pin):
    from .own_fd_domain import regular_fd_domain
    from .own_connection_policy import locked
    from .own_bootstrap_security import path_check
    from .own_bootstrap_ipc import socket_pin
    from .own_connection_broker import RUNTIME,SOCKET
    policy=value.policy;runtime,pin,endpoint_pin=expected
    while True:
        _start_check(value)
        free=False
        with regular_fd_domain(deadline=value.deadline):
            need(_lifetime_pin(policy)==lifetime_pin,'LIFETIME_LOCK_CHANGED')
            for path,wanted,reader in ((policy.root/RUNTIME,pin,path_check),
                                      (policy.root/SOCKET,endpoint_pin,socket_pin)):
                if os.path.lexists(path):need(reader(path)==wanted,'OWNER_CHANGED')
            try:
                with locked(policy.root/'connection.lock',nonblocking=True,shared=True,
                            existing=True,readonly=True) as fd:
                    need(full(os.fstat(fd))==lifetime_pin==_lifetime_pin(policy),'LIFETIME_LOCK_CHANGED')
                    need(not os.path.lexists(policy.root/RUNTIME)
                         and not os.path.lexists(policy.root/SOCKET),'ENDPOINTS_REMAIN')
                    free=True
            except WCEError as error:
                if error.code!='CONNECTION_BUSY':raise
        if free:return
        # The exact shared lock probe is closed and FD scheduling domain left.
        time.sleep(min(.05,max(0,value.deadline-time.monotonic())))


def _cold_owner_absent(value):
    from .own_connection_policy import locked
    from .own_connection_broker import RUNTIME,SOCKET
    from .own_fd_domain import regular_fd_domain
    _start_check(value);pin=_lifetime_pin(value.policy)
    with regular_fd_domain(deadline=value.deadline):
        with locked(value.policy.root/'connection.lock',nonblocking=True,shared=True,
                    existing=True,readonly=True) as fd:
            need(full(os.fstat(fd))==pin==_lifetime_pin(value.policy),'LIFETIME_LOCK_CHANGED')
            need(not os.path.lexists(value.policy.root/RUNTIME)
                 and not os.path.lexists(value.policy.root/SOCKET),'UNKNOWN_ENDPOINTS')


def make_private_start(selector_sha,deadline):
    _sha(selector_sha)
    now=time.monotonic()
    need(type(deadline) in (int,float) and math.isfinite(deadline)
         and now<deadline<=now+300,'DEADLINE')
    # Existing exact private H protocol, not public NETWORK or a new payload.
    return {'schema':1,'profile':'GROUP_FIXED_CHILD_START_V1',
            'selector_sha':selector_sha,'absolute_deadline':deadline}


def _spawn_first(value):
    _start_check(value);key=digest(value.anchor)
    need(key not in _CHILDREN,'CHILD_UNKNOWN')
    _note_start(value,'SPAWN_MAY_EFFECT')
    from .draft_group_runtime_host import PinnedFile
    from .own_connection_broker import _StartupStream,_startup_remaining,read_runtime
    from .own_bootstrap_ipc import peer,send,receive
    from .group_host_jobs import wrap_child_start_request
    from .group_host_external_loader import check_process_loader_anchor
    # Private H returns only after the full Parent preparation, not an early
    # service-ready handshake. Wait on this original bounded D, never D+60 or a
    # newly created business clock. The old public child 60s cap is unchanged.
    startup_deadline=value.deadline
    pin=None;parent=child=None;original=None
    _CHILDREN[key]={'process':None,'state':'POPEN_MAY_EFFECT','deadline':value.deadline}
    try:
        pin=PinnedFile(value.pins.armed_path,value.pins.armed_sha,2*1024*1024)
        capacity(2);parent,child=socket.socketpair(socket.AF_UNIX,socket.SOCK_STREAM)
        parent.settimeout(_startup_remaining(startup_deadline))
        need(peer(parent)[1]==os.getuid(),'CHILD_PEER')
        _start_check(value);pin.check()
        process=subprocess.Popen([sys.executable,'-I','-B',str(value.pins.armed_path)],
            cwd=str(value.pins.armed_path.parent),
            env={'PATH':'/usr/bin:/bin','PYTHONDONTWRITEBYTECODE':'1',
                 'WCE_GROUP_STARTUP_FD':str(child.fileno())},pass_fds=(child.fileno(),),
            stdin=subprocess.DEVNULL,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,
            close_fds=True,start_new_session=True)
        _CHILDREN[key]['process']=process
        _CHILDREN[key]['state']='SPAWNED_UNDETERMINED'
        child.close();child=None
        check_process_loader_anchor(value.loader_anchor);pin.check()
        stream=_StartupStream(parent,startup_deadline)
        send(stream,wrap_child_start_request(make_private_start(value.pins.configuration_sha,value.deadline)))
        result=receive(stream)
        need(type(result) is dict and set(result)=={'state','result','runtime'}
             and result['state']=='GROUP_FIXED_BOOTSTRAP_COMPLETE'
             and type(result['result']) is dict and type(result['runtime']) is dict,'CHILD_RESULT_UNKNOWN')
        actual,_=read_runtime(value.policy)
        need(actual==result['runtime'] and actual['pid']==process.pid,'CHILD_RESULT_UNKNOWN')
        check_process_loader_anchor(value.loader_anchor);pin.check()
        _startup_remaining(startup_deadline)
        # The child has independently attached only after its real normal
        # Parent commit/readback. A result dictionary cannot substitute for it.
        current=value.journal.inspect()[key]
        need(current['state']=='BOUND_REAL_PARENT','PARENT_ATTACHMENT_REQUIRED')
        _time06_note_complete(value,result,process,pin,current)
        _CHILDREN[key]['state']='COMPLETE_SERVICE_RETURNED'
        return result['result']
    except BaseException as error:
        original=error
        # No terminate/kill/retry/refund. Retain every returned Popen handle.
        raise
    finally:
        callbacks=([parent.close] if parent is not None else [])
        callbacks+=([child.close] if child is not None else [])
        callbacks+=([pin.close] if pin is not None else [])
        close_all(callbacks,original)


def prepare_group_first(policy,invocation):
    from .group_host_external_loader import (check_private_preparation,
        process_loader_anchor,check_process_loader_anchor)
    from .group_host_jobs import _compiled,_materialize,publish_fixed_host_job
    from .draft_group_operator_review_chain import FixedOperatorHostPins
    from .draft_group_operator_source_codec import validate_source,validate_runtime_policy
    from .draft_group_runtime_host import PinnedFile
    deadline=check_private_preparation(invocation,policy)
    pins=_materialize(policy,_compiled(policy))
    need(type(pins) is FixedOperatorHostPins,'OPERATOR_FIXED_PINS_REQUIRED')
    held=[];journal=None;original=None
    try:
        for path,checksum in ((pins.source_path,pins.source_sha),
                              (pins.runtime_source_policy_path,pins.runtime_source_policy_sha)):
            held.append(PinnedFile(path,checksum,2*1024*1024))
        source=validate_source(json.loads(held[0].raw));runtime=_runtime_policy(json.loads(held[1].raw))
        from .own_selected_history import _policy_binding
        need(digest(runtime['binding'])==source['binding_sha']
             and runtime['binding']==_policy_binding(policy,'OPERATOR_ATTESTED'),
             'STATIC_BINDING_CHANGED')
        anchor=anchor_from_source(policy,source)
        loader_anchor=process_loader_anchor()
        check_private_preparation(invocation,policy,consume=True)
        from .own_connection_broker import (_startup_gate,_startup_has_owner,read_runtime,
                                          request_idle_drain,SOCKET)
        from .own_bootstrap_ipc import socket_pin
        from .own_base_domain import is_base_runtime
        with _startup_gate(policy,deadline):
            check_private_preparation(invocation,policy);check_process_loader_anchor(loader_anchor)
            existed=os.path.lexists(policy.root/ROOT_NAME)
            time06=_time06_policy(runtime) is not None
            # New model: no technical mkdir/lock/admin initialization before the
            # full original-root absence scope. Existing records never upgrade.
            if existed or not time06:
                root=_root(policy,create=not existed)
                journal=PreParentJournal(root,binding_identity=anchor['binding_identity'],
                                         existing_only=existed);journal.__enter__()
                existing=journal.inspect()
                if existing:
                    need(set(existing)=={digest(anchor)},'RELATED_PREPARATION_REQUIRED')
                    current=existing[digest(anchor)]
                    if time06:need('time_model' in current,'TIME06_NO_LEGACY_MIGRATION')
                    return _recover_parent_local(policy,invocation,anchor,journal,current,loader_anchor)
            if time06:
                with _time06_unissued_scope(policy,pins,source,runtime,anchor,deadline,loader_anchor) as (absence,observation):
                    if journal is None:
                        root=_root(policy,create=True)
                        journal=PreParentJournal(root,binding_identity=anchor['binding_identity']);journal.__enter__()
                    reservation=journal.reserve_time06(anchor,observation,receipt=absence)
            else:
                observation=_observation(policy,pins,source,runtime,deadline)
                reservation=journal.reserve(anchor,observation)
            need(reservation['created'] is True,'PREPARATION_ALREADY_RESERVED')
            value=_Start(policy,invocation,pins,anchor,journal,reservation['head_sha'],observation,
                         deadline,loader_anchor,(os.getpid(),threading.get_ident()))
            token=_START.set(value)
            try:
                _start_check(value)
                # Only the original reviewed, idempotent pointer publisher.
                publish_fixed_host_job(policy)
                for pin in held:pin.check()
                if _startup_has_owner(policy):
                    runtime_value,pin=read_runtime(policy)
                    expected=(runtime_value,pin,socket_pin(policy.root/SOCKET))
                    need(is_base_runtime(runtime_value),'EXISTING_FULL_OR_UNKNOWN_OWNER')
                    lifetime=_lifetime_pin(policy)
                    _note_start(value,'DRAIN_MAY_EFFECT')
                    result=request_idle_drain(policy,*expected,reviewed_scope=policy.value['candidate_scope'],
                                              timeout=3,absolute_deadline=deadline)
                    if result=={'state':'MAINTENANCE_BUSY'}:
                        _note_start(value,'BUSY_OBSERVED')
                        return {'state':'FIRST_PREPARATION_BUSY_RESERVED','authority':False}
                    need(result=={'state':'DRAIN_ACCEPTED'},'DRAIN_UNKNOWN')
                    _wait_release(value,expected,lifetime)
                    _note_start(value,'LIFETIME_RELEASE_OBSERVED')
                else:
                    _cold_owner_absent(value)
                    _note_start(value,'OWNER_ABSENCE_OBSERVED')
                _start_check(value)
                return _spawn_first(value)
            finally:_START.reset(token)
    except BaseException as error:original=error;raise
    finally:
        close_all(([lambda:journal.close(original=original)] if journal is not None else [])
                  +[pin.close for pin in reversed(held)],original)


class HostFirstPreparation:
    def __new__(cls,*args,**kwargs):raise WCEError('GROUP_FIRST_PRIVATE_HOST_PREPARATION_REQUIRED')
    @property
    def authority(self):return False


class ParentSubmitted:
    def __new__(cls,*args,**kwargs):raise WCEError('GROUP_FIRST_PRIVATE_PARENT_SUBMISSION_REQUIRED')
    @property
    def authority(self):return False


class ParentReadbackReceipt:
    def __new__(cls,*args,**kwargs):raise WCEError('GROUP_FIRST_PRIVATE_PARENT_READBACK_REQUIRED')
    @property
    def authority(self):return False


class ParentRecoveryReadbackReceipt:
    def __new__(cls,*args,**kwargs):raise WCEError('GROUP_FIRST_PRIVATE_PARENT_RECOVERY_READBACK_REQUIRED')
    @property
    def authority(self):return False


@dataclass
class _HostFacts:
    host:object
    entry:object
    anchor:dict
    journal:object
    head_sha:str
    observation:dict
    owner:tuple
    receipt:object


def _host_facts(host):
    from .draft_group_host_operator import _host,binding_for_host,current_binding_phase,validate_current_source_binding
    entry=_host(host);value=_HOSTS.get(host)
    need(type(value) is _HostFacts and value.host is host and value.entry is entry
         and value.owner==(os.getpid(),threading.get_ident())
         and type(value.receipt) is HostFirstPreparation
         and entry.issued.get(id(value.receipt)) is value.receipt,'HOST_PREPARATION_UNISSUED')
    binding=binding_for_host(host,None)
    validate_current_source_binding(host,binding,required_phase=current_binding_phase(host,binding))
    value.journal.check();entry.full_guard()
    return value


def _host_note(value,event):
    _host_facts(value.host)
    result=value.journal.note(value.anchor,expected_head_sha=value.head_sha,event=event,
                              observation=value.observation)
    value.head_sha=result['head_sha']


def begin_first_preparation_in_host(host):
    from .draft_group_host_operator import _host,binding_for_host,validate_current_source_binding
    from .draft_group_runtime_service import call_in_entry
    frame=inspect.currentframe()
    try:need(frame.f_back.f_code is call_in_entry.__code__,'PRIVATE_HOST_ENTRY_REQUIRED')
    finally:del frame
    entry=_host(host);validate_current_source_binding(host,binding_for_host(host,None),
                                                     required_phase='COMPLETE_SERVICE_NO_ADMISSION')
    # Only the original fixed cold H invocation, never a warm generic worker.
    from .group_host_jobs import _CHILD_INVOCATIONS,validate_child_invocation
    active=[value for value,facts in _CHILD_INVOCATIONS.items()
            if facts.thread==threading.get_ident()]
    need(len(active)==1,'ACTUAL_COLD_CHILD_INVOCATION_REQUIRED')
    invocation=validate_child_invocation(active[0])
    need(invocation.constants['POLICY_PATH']==str(entry.policy.path)
         and invocation.request['selector_sha']==host.pins.configuration_sha,'CHILD_SCOPE_CHANGED')
    need(host not in _HOSTS,'HOST_PREPARATION_ALREADY_ENTERED')
    anchor=anchor_from_source(entry.policy,host.chain.source)
    journal=PreParentJournal(_root(entry.policy,create=False),binding_identity=anchor['binding_identity'],
                             existing_only=True)
    journal.__enter__()
    try:
        observed=journal.inspect();need(set(observed)=={digest(anchor)},'RELATED_PREPARATION_REQUIRED')
        current=observed[digest(anchor)]
        need(current['state']=='NOT_CREATED' and 'SPAWN_MAY_EFFECT' in current['events']
             and 'READY_PRE_PARENT' not in current['events'],'FIRST_CHILD_ALREADY_OBSERVED')
        receipt=object.__new__(HostFirstPreparation)
        value=_HostFacts(host,entry,anchor,journal,current['head_sha'],current['records'][-1]['observation'],
                         (os.getpid(),threading.get_ident()),receipt)
        entry.issued[id(receipt)]=receipt
        _HOSTS[host]=value;entry.stack.callback(_close_host,host)
        _host_note(value,'READY_PRE_PARENT')
        # Conservative before this fixed function can reach its actual Token /
        # LIST/GET continuation. It is not a claim that any budget was consumed.
        _host_note(value,'TOKEN_OR_READ_MAY_EFFECT')
        return receipt
    except BaseException as original:
        _HOSTS.pop(host,None);journal.close(original=original);raise


def _close_host(host):
    value=_HOSTS.pop(host,None)
    if value is not None:
        value.entry.issued.pop(id(value.receipt),None)
        value.journal.close()


def _validate_legacy_attachment_mapping(value):
    """Mechanical closed replay only. A persisted mapping is never a permit."""
    need(type(value) is dict and set(value)==set(MAPPING_KEYS),'MAPPING_SHAPE')
    need(type(value['schema']) is int and value['schema']==1 and value['profile']==MAPPING_PROFILE
         and value['authority'] is False,'MAPPING_PROFILE')
    for key in MAPPING_KEYS:
        if key.endswith('_sha'):_sha(value[key])
    need(type(value['not_after_ms']) is int and value['not_after_ms']>0,'MAPPING_EXPIRY')
    from .draft_group_parent import validate_parent,candidate_sha
    parent=validate_parent(value['parent'])
    need(candidate_sha(parent)==value['parent_sha'],'PARENT_SHA_CHANGED')
    for key in ('binding_sha','family_id','registration_sha','registration_proof_sha',
                'source_material_sha','semantic_scope_sha','preview_sha','settings_sha'):
        need(parent[key]==value[key],'MAPPING_PARENT_CHANGED')
    need(parent['read_covenant_sha']==value['first_covenant_sha']
         and value['not_after_ms']<=parent['not_after_ms'],'MAPPING_PARENT_CHANGED')
    need(type(value['children']) is list and len(value['children'])==len(parent['children']),
         'MAPPING_CHILDREN_CHANGED')
    from .draft_group_contracts import Article,identifier
    seen=set()
    for ordinal,(parent_child,child) in enumerate(zip(parent['children'],value['children'])):
        need(type(child) is dict and set(child)=={'parent_child','plan_child'},'MAPPING_CHILD_SHAPE')
        need(canonical(child['parent_child'])==canonical(parent_child)
             and child['plan_child']['operation_id']==parent_child['operation_id']
             and canonical(child['plan_child']['budget'])==canonical(parent_child['budget']),
             'MAPPING_CHILD_CHANGED')
        plan=child['plan_child']
        need(type(plan) is dict and set(plan)==set(PLAN_CHILD_KEYS)
             and type(plan['schema']) is int and plan['schema']==1
             and plan['state']=='LOCAL_CANDIDATE' and plan['executable'] is False
             and type(plan['ordinal']) is int and plan['ordinal']==ordinal
             and plan['candidate_activation']==('PLANNED' if ordinal==0 else 'WAITING')
             and plan['route']=='CREATE_NEW' and plan['old_ref_set']==[]
             and plan['main_changes']==[] and plan['retirement_required'] is False
             and plan['platform_completion']=='NOT_OBSERVED'
             and plan['settings']=='UNVERIFIED_BY_PURE_COMPONENT','MAPPING_PLAN_CHILD')
        _sha(plan['child_key']);identifier(plan['target_group_id'])
        need(plan['operation_id']=='group-op-'+plan['child_key']
             and type(plan['target_generation']) is int and plan['target_generation']>=1
             and type(plan['members']) is list and type(plan['member_count']) is int
             and 1<=len(plan['members'])==plan['member_count']<=8,'MAPPING_PLAN_MEMBERS')
        need(plan['digest_projection']==('EMPTY_FOR_MULTI_KEEP_ORIGINAL_IN_ARCHIVE'
            if len(plan['members'])>1 else 'PRESERVE_EXPLICIT_SINGLE_DIGEST'),'MAPPING_PLAN_SETTINGS')
        for position,member in enumerate(plan['members']):
            need(type(member) is dict and set(member)==set(Article.__slots__)|{'target_position','source_old_index'}
                 and type(member['target_position']) is int and member['target_position']==position
                 and member['source_old_index'] is None,'MAPPING_PLAN_MEMBER_SHAPE')
            article=Article(**{key:member[key] for key in Article.__slots__})
            need(article.binding_sha==parent['binding_sha'] and article.origin=='NEW_NOT_SENT'
                 and article.article_id not in seen,'MAPPING_PLAN_MEMBER_CHANGED')
            seen.add(article.article_id)
        need(plan['main_article_id']==plan['members'][0]['article_id'],'MAPPING_MAIN_CHANGED')
    for key in ('parent_event','plan_event'):
        event=value[key]
        need(type(event) is dict and set(event)=={'seq','event_sha'}
             and type(event['seq']) is int and event['seq']>0,'MAPPING_EVENT_SHAPE')
        _sha(event['event_sha'])
    need(value['parent_event']['seq']<value['plan_event']['seq'],'MAPPING_EVENT_ORDER')
    return json.loads(canonical(value))


def validate_attachment_mapping(value):
    from . import draft_group_first_time_values as t
    if type(value) is dict and value.get('profile')==t.MAPPING_PROFILE:
        return t.validate_mapping(value,MAPPING_KEYS,_validate_legacy_attachment_mapping)
    return _validate_legacy_attachment_mapping(value)


def _mapping_time06(value,first_observation,current_observation):
    from . import draft_group_first_time_values as t
    if not t.is_time06_observation(first_observation):return value
    from .draft_group_operator_time_v2 import validate_observation_v2
    current=validate_observation_v2(current_observation)
    lifetime=min(first_observation['source_lifetime_not_after_ms'],current['source_lifetime_not_after_ms'])
    result=dict(value,schema=2,profile=t.MAPPING_PROFILE,time_model=t.TIME_MODEL,
        source_lifetime_not_after_ms=lifetime,
        original_technical_not_after_ms=first_observation['not_after_ms'],
        first_absence_sha=first_observation['first_absence_sha'],
        not_after_ms=min(value['parent']['not_after_ms'],lifetime))
    return validate_attachment_mapping(result)


def _mapping(host,db,history,parent_json):
    from .draft_group_parent import check_parent_records_in,candidate_sha
    from .draft_group_host_operator import binding_for_host,current_binding_facts
    from .draft_group_operator_review import committed_review_sha
    facts=_host_facts(host);host.current_no_token_in(db,host._source,history_locators=history)
    info=check_parent_records_in(db,history_policy=host.entry.policy,history_locators=history)
    parent=json.loads(parent_json);parent_sha=candidate_sha(parent)
    item=info['parents'].get(parent_sha)
    need(item is not None and canonical(item['candidate'])==parent_json,'ORIGINAL_PARENT_REQUIRED')
    pack=host._first_pack;registration=host._registration;source=host.chain.source
    need(parent['binding_sha']==digest(host.chain.config['binding'])
         and parent['family_id']==source['allowed_read_scope']['family_anchor_sha']
         and parent['registration_sha']==registration['registration_sha']
         and parent['registration_proof_sha']==registration['registration_proof_sha']
         and parent['source_material_sha']==host.pins.source_sha
         and parent['read_covenant_sha']==pack.entry('covenant').sha256,'ORIGINAL_SCOPE_CHANGED')
    ordered=[];plan_event=None
    for child in parent['children']:
        execution=info['executions'].get(child['operation_id'])
        need(execution is not None and execution['parent']==parent,'FULL_PARENT_PLAN_REQUIRED')
        current_event=execution['plan_event']
        need(plan_event is None or current_event==plan_event,'PLAN_EVENT_CHANGED')
        plan_event=current_event
        ordered.append({'parent_child':child,'plan_child':execution['child']})
    need(plan_event is not None,'PLAN_EVENT_REQUIRED')
    binding=binding_for_host(host,'ADMISSION_READY');observed=current_binding_facts(binding)
    value={'schema':1,'profile':MAPPING_PROFILE,'authority':False,
        'anchor_sha':digest(facts.anchor),'preparation_identity_sha':preparation_identity(facts.anchor),
        'binding_sha':parent['binding_sha'],'operator_request_identity_sha':source['operator_request_identity_sha'],
        'original_request_set_sha':source['original_request_set_sha'],'account_partition_sha':source['account_partition_sha'],
        'family_id':parent['family_id'],'first_covenant_sha':pack.entry('covenant').sha256,
        'first_proof_sha':pack.entry('first_proof').sha256,
        'registration_sha':parent['registration_sha'],'registration_proof_sha':parent['registration_proof_sha'],
        'source_material_sha':parent['source_material_sha'],'current_source_review_sha':committed_review_sha(host,binding),
        'semantic_scope_sha':parent['semantic_scope_sha'],'preview_sha':parent['preview_sha'],
        'settings_sha':parent['settings_sha'],'parent_sha':parent_sha,'parent':parent,'children':ordered,
        'parent_event':{key:item['event'][key] for key in ('seq','event_sha')},
        'plan_event':{key:plan_event[key] for key in ('seq','event_sha')},
        'not_after_ms':min(parent['not_after_ms'],observed['qualified_not_after_ms'],
                           facts.observation['not_after_ms'])}
    host.pure_release_fence()
    return validate_attachment_mapping(_mapping_time06(value,facts.observation,observed))


@dataclass
class _WriteFacts:
    host:object
    db:object
    epoch:object
    thread:int
    submitted:object=None
    status:str='WRITING'


@contextmanager
def first_parent_transaction(host):
    facts=_host_facts(host)
    need(_WRITE.get() is None,'PARENT_WRITE_REENTRANT')
    _host_note(facts,'PARENT_COMMIT_MAY_EFFECT')
    from .draft_group_history_context import history_transaction
    from .own_validation_scope import _transaction_marker
    write=None;original=None
    try:
        with facts.journal.hold():
            # The original actual context owns its normal commit and all scope exit.
            with history_transaction(host.entry.service.workflow.db,write=True,
                                     physical_resources=host.entry) as (db,history):
                write=_WriteFacts(host,db,_transaction_marker(db),threading.get_ident())
                token=_WRITE.set(write)
                try:
                    yield db,history
                    need(write.submitted is not None and write.status=='APPENDED','PARENT_SUBMISSION_REQUIRED')
                finally:_WRITE.reset(token)
            # Reached only through normal __exit__; no caller success bool or closed
            # db.in_transaction inference. The writer may now be closed.
            write.status='NORMAL_COMMITTED'
            from .draft_group_runtime_host import cold_history_snapshot_fixed
            with cold_history_snapshot_fixed(host.entry.policy,host.entry) as (fresh,history):
                need(fresh is not write.db,'FRESH_OWNED_REQUIRED')
                token=_FRESH.set((write,fresh,_transaction_marker(fresh),history))
                try:
                    receipt=_issue_parent_readback(write, fresh,history)
                    result=facts.journal.bind_parent(facts.anchor,expected_head_sha=facts.head_sha,receipt=receipt)
                    facts.head_sha=result['head_sha'];write.status='BOUND_REAL_PARENT'
                finally:_FRESH.reset(token)
    except BaseException as error:
        original=error
        if write is not None and write.status!='BOUND_REAL_PARENT':
            close_all([lambda:_host_note(facts,'PARENT_COMMIT_UNKNOWN')],original)
        raise
    finally:
        if write is not None and write.submitted is not None:_SUBMITTED.pop(write.submitted,None)


def append_parent_and_plan(creation,*,history_locators=None):
    from .draft_group_parent_issuer import ParentCreation,_creation
    from .own_validation_scope import _transaction_marker
    write=_WRITE.get();record=_creation(creation)
    need(type(write) is _WriteFacts and write.host is record.host and write.db is record.db
         and write.epoch==_transaction_marker(record.db) and write.thread==threading.get_ident()
         and write.submitted is None and write.status=='WRITING','NORMAL_PARENT_WRITER_REQUIRED')
    result=ParentCreation.append_and_plan(creation,history_locators=history_locators)
    record=_creation(creation);need(record.phase=='FINISHED','PARENT_APPEND_UNDETERMINED')
    mapping=_mapping(record.host,record.db,history_locators,record.parent_json)
    submitted=object.__new__(ParentSubmitted)
    _SUBMITTED[submitted]=(write,record.parent_json,canonical(mapping))
    write.submitted=submitted;write.status='APPENDED'
    return result


def _issue_parent_readback(write,fresh,history):
    from .own_validation_scope import OwnedConnection,_transaction_marker
    context=_FRESH.get()
    need(type(write) is _WriteFacts and write.status=='NORMAL_COMMITTED'
         and context==(write,fresh,_transaction_marker(fresh),history)
         and type(fresh) is OwnedConnection and fresh is not write.db
         and fresh.execute('PRAGMA query_only').fetchone()[0]==1,'NORMAL_COMMIT_FRESH_OWNED_REQUIRED')
    original=_SUBMITTED.get(write.submitted)
    need(original is not None and original[0] is write,'PARENT_SUBMISSION_UNISSUED')
    mapping=_mapping(write.host,fresh,history,original[1])
    need(canonical(mapping)==original[2],'FRESH_PARENT_MAPPING_CHANGED')
    facts=_host_facts(write.host)
    receipt=object.__new__(ParentReadbackReceipt)
    _RECEIPTS[receipt]=(write,fresh,_transaction_marker(fresh),history,canonical(mapping),facts.head_sha,
                        threading.get_ident())
    write.host.entry.issued[id(receipt)]=receipt
    write.host.entry.stack.callback(_release_receipt,write.host,receipt)
    return receipt


def require_parent_readback_receipt(receipt,*,anchor,expected_head_sha):
    if type(receipt) is ParentRecoveryReadbackReceipt:
        return _require_recovery_receipt(receipt,anchor,expected_head_sha)
    need(type(receipt) is ParentReadbackReceipt,'PARENT_READBACK_RECEIPT_REQUIRED')
    record=_RECEIPTS.get(receipt)
    need(record is not None,'PARENT_READBACK_RECEIPT_UNISSUED')
    write,fresh,epoch,history,raw,head_sha,thread=record
    from .own_validation_scope import _transaction_marker
    need(_FRESH.get()==(write,fresh,epoch,history) and thread==threading.get_ident()
         and _transaction_marker(fresh)==epoch and write.status in ('NORMAL_COMMITTED','BOUND_REAL_PARENT')
         and write.host.entry.issued.get(id(receipt)) is receipt,'PARENT_READBACK_LIFETIME_CHANGED')
    facts=_host_facts(write.host);mapping=validate_attachment_mapping(json.loads(raw))
    need(validate_anchor(anchor)==facts.anchor and mapping['anchor_sha']==digest(anchor),
         'PARENT_READBACK_ANCHOR_CHANGED')
    _sha(expected_head_sha)
    need(time.time()*1000<mapping['not_after_ms'],'PARENT_READBACK_EXPIRED')
    write.host.pure_release_fence()
    return {'authority':False,'parent_binding':mapping,'original_head_sha':head_sha}


@dataclass(frozen=True)
class _RecoveryFacts:
    policy:object
    invocation:object
    db:object
    epoch:object
    history:object
    anchor_raw:str
    head_sha:str
    mapping_raw:str
    loader_anchor:object
    owner:tuple
    current_raw:str
    metadata_raw:str
    historical_guard:object
    locks_current:object
    recovery_deadline:object


def _historical_mapping(policy,db,history,info,anchor,current):
    """Original pinned source/request and complete original event graph only."""
    from .draft_group_input_files import InputFiles
    from .draft_group_operator_source_codec import SOURCE_PROFILE,SOURCE_REVIEW_PROFILE
    from .draft_revision_guard import historical_identity_guard,policy_binding
    from .draft_group_parent import candidate_sha
    from .draft_group_read_family_store import FIRST
    from .draft_group_response_history import read_group_replay_snapshot_in,release_group_replay_snapshot_in
    files=InputFiles(policy,historical_identity_guard(policy));matches=[]
    binding_sha=digest(policy_binding(policy,'OPERATOR_ATTESTED'))
    for item in info['parents'].values():
        parent=item['candidate']
        if parent['binding_sha']!=binding_sha:continue
        source=files.read('source',parent['source_material_sha'])
        if source.value['profile']!=SOURCE_PROFILE:continue
        if anchor_from_source(policy,source.value)==anchor:matches.append((item,source))
    need(len(matches)==1,'ORIGINAL_PARENT_ABSENT_OR_AMBIGUOUS')
    item,source=matches[0];parent=item['candidate'];parent_seq=item['event']['seq']
    children=[];plan_event=None
    for child in parent['children']:
        execution=info['executions'].get(child['operation_id'])
        need(execution is not None and execution['parent']==parent,'RECOVERY_FULL_PLAN_REQUIRED')
        need(plan_event is None or plan_event==execution['plan_event'],'RECOVERY_PLAN_EVENT_CHANGED')
        plan_event=execution['plan_event']
        children.append({'parent_child':child,'plan_child':execution['child']})
    need(plan_event is not None,'RECOVERY_PLAN_EVENT_REQUIRED')
    states,events=read_group_replay_snapshot_in(db)
    try:
        original=[];reviews=[]
        for event in events:
            if event['account_key']!=parent['binding_sha'] or event['kind']!='PREVIEW':continue
            candidate=event['payload'].get('candidate')
            if type(candidate) is not dict or event['seq']>=parent_seq:continue
            if candidate.get('profile')==FIRST and candidate.get('family_anchor_id')==parent['family_id']:
                original.append(candidate)
            from .draft_group_operator_time_v2 import SOURCE_REVIEW_PROFILE_V2
            expected_review=SOURCE_REVIEW_PROFILE_V2 if 'time_model' in current else SOURCE_REVIEW_PROFILE
            if candidate.get('profile')==expected_review and candidate.get('family_id')==parent['family_id']:
                if (candidate['registration_sha']==parent['registration_sha']
                    and candidate['original_source_material_sha']==parent['source_material_sha']
                    and candidate['current_source_material_sha']==parent['source_material_sha']):
                    reviews.append((event['seq'],candidate))
        need(len(original)==1 and original[0]['covenant_sha']==parent['read_covenant_sha']
             and bool(reviews),'RECOVERY_ORIGINAL_FIRST_REVIEW_REQUIRED')
        _,review=max(reviews,key=lambda pair:pair[0])
        if 'time_model' in current:
            from .draft_group_operator_time_v2 import validate_review_v2 as validate_review
        else:
            from .draft_group_operator_review import validate as validate_review
        review=validate_review(review)
        review_sha=sha256((canonical(review)+'\n').encode()).hexdigest()
        from .draft_group_source_review import SourceReviewFiles
        checked_review=SourceReviewFiles(policy,historical_identity_guard(policy)).read('source_review',review_sha)
        need(checked_review.value==review,'RECOVERY_ORIGINAL_REVIEW_FILE_CHANGED')
        value={'schema':1,'profile':MAPPING_PROFILE,'authority':False,
            'anchor_sha':digest(anchor),'preparation_identity_sha':preparation_identity(anchor),
            'binding_sha':parent['binding_sha'],
            'operator_request_identity_sha':source.value['operator_request_identity_sha'],
            'original_request_set_sha':source.value['original_request_set_sha'],
            'account_partition_sha':source.value['account_partition_sha'],'family_id':parent['family_id'],
            'first_covenant_sha':original[0]['covenant_sha'],'first_proof_sha':original[0]['first_proof_sha'],
            **{key:parent[key] for key in ('registration_sha','registration_proof_sha',
                 'source_material_sha','semantic_scope_sha','preview_sha','settings_sha')},
            'current_source_review_sha':review_sha,'parent_sha':candidate_sha(parent),
            'parent':parent,'children':children,
            'parent_event':{key:item['event'][key] for key in ('seq','event_sha')},
            'plan_event':{key:plan_event[key] for key in ('seq','event_sha')},
            'not_after_ms':min(parent['not_after_ms'],review['not_after_ms'],current['not_after_ms'])}
        result=validate_attachment_mapping(_mapping_time06(value,current['records'][0]['observation'],review['current_binding'])) if 'time_model' in current else validate_attachment_mapping(value)
        _compare_bound_record(result,info['executions'][parent['children'][0]['operation_id']],info,anchor)
        return result
    finally:release_group_replay_snapshot_in(db,states,events)


def _recovery_history_fence(facts):
    from .own_validation_scope import OwnedConnection,_transaction_marker
    from .draft_group_history_context import require_history
    from .draft_group_local_reader import _metadata
    from .own_store import OwnStore
    from .draft_group_parent import check_parent_records_in
    need(type(facts) is _RecoveryFacts and _RECOVERY.get() is facts
         and facts.owner==(os.getpid(),threading.get_ident()),'RECOVERY_RECEIPT_UNISSUED')
    need(type(facts.recovery_deadline) in (int,float) and math.isfinite(facts.recovery_deadline)
         and time.monotonic()<facts.recovery_deadline,'RECOVERY_DEADLINE')
    need(type(facts.db) is OwnedConnection and _transaction_marker(facts.db)==facts.epoch
         and facts.db.execute('PRAGMA query_only').fetchone()[0]==1,'RECOVERY_RECEIPT_CHANGED')
    facts.historical_guard();facts.locks_current()
    need(canonical(_metadata(facts.policy))==facts.metadata_raw,'RECOVERY_SOURCE_CHANGED')
    require_history(facts.policy,facts.db,facts.history)
    OwnStore.check(facts.db,'OPERATOR_ATTESTED',facts.policy,history=facts.history)
    info=check_parent_records_in(facts.db,history_policy=facts.policy,history_locators=facts.history)
    current=json.loads(facts.current_raw);anchor=json.loads(facts.anchor_raw)
    observed=_historical_mapping(facts.policy,facts.db,facts.history,info,anchor,current)
    need(canonical(observed)==facts.mapping_raw,'RECOVERY_GRAPH_CHANGED')
    facts.historical_guard();facts.locks_current()
    need(canonical(_metadata(facts.policy))==facts.metadata_raw,'RECOVERY_SOURCE_CHANGED')
    return observed


def _recovery_write_guard(facts):
    # This is current local technical permission, never active=False authority.
    from .group_host_external_loader import check_private_preparation,check_process_loader_anchor
    from .draft_revision_guard import policy_binding
    need(facts.invocation is not None and facts.loader_anchor is not None,'RECOVERY_OBSERVATION_ONLY')
    deadline=check_private_preparation(facts.invocation,facts.policy)
    check_process_loader_anchor(facts.loader_anchor);facts.policy.check()
    need(deadline==facts.recovery_deadline and time.monotonic()<deadline,'RECOVERY_DEADLINE')
    original=json.loads(facts.current_raw)['records'][-1]['observation']
    need(type(original['epoch']) is int and original['epoch']==facts.policy.data['epoch']
         and original['binding_sha']==digest(policy_binding(facts.policy,'OPERATOR_ATTESTED')),
         'RECOVERY_EPOCH_BRIDGE_REQUIRED')
    need(_identity(facts.policy)==json.loads(facts.anchor_raw)['binding_identity'],
         'RECOVERY_CURRENT_ACCOUNT_CHANGED')


@contextmanager
def _historical_parent_observation(policy,anchor,journal,current,invocation=None,loader_anchor=None,*,query_deadline=None):
    from .draft_group_local_reader import _authorize,_metadata,_readonly_locks,_readonly_database
    from .own_validation_scope import _transaction_marker
    from .own_store import OwnStore
    from .draft_group_parent import check_parent_records_in
    need(current['state'] in ('NOT_CREATED','BOUND_REAL_PARENT')
         and (current['state']=='BOUND_REAL_PARENT' or 'PARENT_COMMIT_MAY_EFFECT' in current['events']),
         'RESERVED_PREPARATION_UNDETERMINED')
    if invocation is not None:
        from .group_host_external_loader import check_private_preparation
        deadline=check_private_preparation(invocation,policy)
    else:deadline=query_deadline
    need(type(deadline) in (int,float) and math.isfinite(deadline)
         and time.monotonic()<deadline<=time.monotonic()+300,'RECOVERY_DEADLINE')
    original_guard=_authorize(policy,policy.actor)
    def guard():
        need(time.monotonic()<deadline,'RECOVERY_DEADLINE');original_guard()
    guard();before=_metadata(policy)
    # Caller holds startup gate when writing. Every path takes technical account
    # before shared history locks; this never waits for a busy writer.
    with journal.hold():
        rows=journal.inspect();need(set(rows)=={digest(anchor)},'RELATED_PREPARATION_REQUIRED')
        actual=rows[digest(anchor)]
        need(canonical(actual)==canonical(current),'RECOVERY_HEAD_CHANGED')
        with _readonly_locks(policy) as (_,locks_current):
            guard();locks_current();need(_metadata(policy)==before,'RECOVERY_SOURCE_CHANGED')
            with _readonly_database(policy) as (db,history):
                need(db.execute('PRAGMA user_version').fetchone()[0]==9,'RECOVERY_SCHEMA9_REQUIRED')
                OwnStore.check(db,'OPERATOR_ATTESTED',policy,history=history)
                info=check_parent_records_in(db,history_policy=policy,history_locators=history)
                mapping=_historical_mapping(policy,db,history,info,anchor,current)
                if current['state']=='BOUND_REAL_PARENT':
                    need(canonical(mapping)==canonical(validate_attachment_mapping(current['parent_binding'])),
                         'BOUND_FULL_MAPPING_CHANGED')
                facts=_RecoveryFacts(policy,invocation,db,_transaction_marker(db),history,canonical(anchor),
                    current['head_sha'],canonical(mapping),loader_anchor,(os.getpid(),threading.get_ident()),
                    canonical(current),canonical(before),guard,locks_current,deadline)
                token=_RECOVERY.set(facts)
                try:
                    _recovery_history_fence(facts);yield facts,mapping
                    _recovery_history_fence(facts)
                finally:_RECOVERY.reset(token)
            guard();locks_current();need(_metadata(policy)==before,'RECOVERY_SOURCE_CHANGED')


def _recover_parent_local(policy,invocation,anchor,journal,current,loader_anchor):
    from .group_host_external_loader import check_private_preparation
    from .own_fd_domain import regular_fd_domain
    deadline=check_private_preparation(invocation,policy)
    with regular_fd_domain(deadline=deadline):
        with _historical_parent_observation(policy,anchor,journal,current,invocation,loader_anchor) as (facts,mapping):
            if current['state']=='BOUND_REAL_PARENT':
                observed_head=current['head_sha']
                if 'time_model' in current and current.get('prepare_result') is None:
                    observed_head=_time06_recover_known(facts,journal,anchor,current)['head_sha']
                return {'state':'PARENT_ALREADY_BOUND_OBSERVATION_ONLY','authority':False,'created':False,
                    'observation_origin':'HISTORICAL_COMMITTED_GRAPH_OBSERVATION_V1',
                    'operation_ids':[child['parent_child']['operation_id'] for child in mapping['children']],
                    'head_sha':observed_head,'new_network_or_business_budget':0}
            _recovery_write_guard(facts)
            receipt=object.__new__(ParentRecoveryReadbackReceipt);_RECOVERY_RECEIPTS[receipt]=facts
            try:result=journal.bind_parent(anchor,expected_head_sha=current['head_sha'],receipt=receipt)
            finally:_RECOVERY_RECEIPTS.pop(receipt,None)
            _recovery_write_guard(facts)
            if 'time_model' in current:
                result=_time06_recover_known(facts,journal,anchor,journal.inspect()[digest(anchor)])
            return {'state':'ORIGINAL_PARENT_READBACK_BOUND','authority':False,
                'observation_origin':HISTORICAL_ATTACHMENT_ORIGIN,
                'operation_ids':[child['parent_child']['operation_id'] for child in mapping['children']],
                'head_sha':result['head_sha'],'new_network_or_business_budget':0}


def query_group_first_local(policy):
    """Fixed account's existing original head only; facts, never a CAS permit.

    Uses historical identity/Owned-H and creates no root, account file, lock,
    source, attempt, service, Token or Group owner. A missing/partial head holds.
    """
    from .own_business_temporal import phase_deadline
    from .own_fd_domain import regular_fd_domain
    deadline=phase_deadline(300)
    with regular_fd_domain(deadline=deadline), PreParentJournal(
            _root(policy,create=False),binding_identity=_identity(policy),
            existing_only=True,readonly=True) as journal:
        with journal.hold():
            rows=journal.inspect();need(len(rows)==1,'RELATED_PREPARATION_REQUIRED')
            current=next(iter(rows.values()));anchor=validate_anchor(current['anchor'])
            with _historical_parent_observation(policy,anchor,journal,current,query_deadline=deadline) as (_,mapping):
                return {'state':'ORIGINAL_PARENT_HISTORICAL_OBSERVATION_ONLY','authority':False,
                    'observation_origin':HISTORICAL_ATTACHMENT_ORIGIN,
                    'technical_state':current['state'],'head_sha':current['head_sha'],
                    'parent_binding':mapping,'new_network_or_business_budget':0}


def _require_recovery_receipt(receipt,anchor,expected_head_sha):
    facts=_RECOVERY_RECEIPTS.get(receipt)
    need(type(facts) is _RecoveryFacts and _RECOVERY.get() is facts
         and facts.owner==(os.getpid(),threading.get_ident()),'RECOVERY_RECEIPT_UNISSUED')
    need(not _RECOVERY_SPENT.get(receipt,False) or _RECOVERY_BIND.get() is receipt,
         'RECOVERY_RECEIPT_SPENT')
    need(facts.anchor_raw==canonical(validate_anchor(anchor))
         and facts.head_sha==expected_head_sha,'RECOVERY_RECEIPT_CHANGED')
    mapping=_recovery_history_fence(facts);_recovery_write_guard(facts)
    # Preserve the original source/Parent/technical expiry in the mapping.
    # This receipt proves historical commit, not a normal callback or live grant.
    return {'authority':False,'parent_binding':mapping,'original_head_sha':facts.head_sha}


@contextmanager
def attachment_receipt_scope(receipt,*,anchor,expected_head_sha):
    """One actual attachment stack; repeated fences do not reissue a receipt."""
    if type(receipt) is not ParentRecoveryReadbackReceipt:
        checked=require_parent_readback_receipt(receipt,anchor=anchor,expected_head_sha=expected_head_sha)
        def fence():
            value=require_parent_readback_receipt(receipt,anchor=anchor,expected_head_sha=expected_head_sha)
            need(canonical(value)==canonical(checked),'PARENT_READBACK_CHANGED')
        yield checked,fence,None
        return
    need(not _RECOVERY_SPENT.get(receipt,False),'RECOVERY_RECEIPT_SPENT')
    checked=_require_recovery_receipt(receipt,anchor,expected_head_sha)
    _RECOVERY_SPENT[receipt]=True;token=_RECOVERY_BIND.set(receipt)
    try:
        def fence():
            value=_require_recovery_receipt(receipt,anchor,expected_head_sha)
            need(canonical(value)==canonical(checked),'RECOVERY_RECEIPT_CHANGED')
        yield checked,fence,HISTORICAL_ATTACHMENT_ORIGIN
    finally:_RECOVERY_BIND.reset(token)


def _release_receipt(host,receipt):
    _RECEIPTS.pop(receipt,None);host.entry.issued.pop(id(receipt),None)


def _compare_bound_record(mapping,record,history,anchor):
    from .draft_group_parent import candidate_sha
    need(mapping['parent_sha']==candidate_sha(record['parent'])
         and mapping['parent']==record['parent']
         and mapping['operator_request_identity_sha']==anchor['original_request_identity_sha']
         and mapping['original_request_set_sha']==anchor['original_request_set_sha']
         and mapping['account_partition_sha']==anchor['account_partition_sha'],'BOUND_PARENT_MAPPING_CHANGED')
    expected=[]
    for child in record['parent']['children']:
        execution=history['executions'].get(child['operation_id'])
        need(execution is not None and execution['parent']==record['parent']
             and execution['parent_event']==record['parent_event']
             and execution['plan_event']==record['plan_event'],'BOUND_FULL_CHILDREN_REQUIRED')
        expected.append({'parent_child':child,'plan_child':execution['child']})
    need(canonical(expected)==canonical(mapping['children'])
         and mapping['plan_event']=={key:record['plan_event'][key] for key in ('seq','event_sha')}
         and mapping['parent_event']=={key:record['parent_event'][key] for key in ('seq','event_sha')},
         'BOUND_FULL_MAPPING_CHANGED')


def require_bound_parent_in(host,db,operation_id,*,history_locators=None):
    """New Operator public execution/readback fence; not a Parent factory."""
    from .draft_group_host_operator import _host
    from .draft_group_host_review import GroupRuntimeHost
    from .draft_group_runtime_host import GroupExecutionGate,_REGISTRY
    need(type(host) is GroupRuntimeHost and type(host.entry) is GroupExecutionGate
         and _REGISTRY.get(host.entry.id) is host.entry,'ACTUAL_HOST_REQUIRED')
    host.entry.held_pure()
    profile=host.chain.source['profile']
    if profile in ('GROUP_BATCH_NATIVE_SOURCE_REVIEW_V1','GROUP_BATCH_NATIVE_SOURCE_BASELINE_V2'):
        return None  # Explicit original Native path unchanged.
    from .draft_group_operator_source_codec import SOURCE_PROFILE
    need(profile==SOURCE_PROFILE,'UNKNOWN_SOURCE_PROFILE')
    _host(host)
    from .draft_group_parent import check_parent_records_in,candidate_sha
    info=check_parent_records_in(db,history_policy=host.entry.policy,history_locators=history_locators)
    record=info['executions'].get(operation_id);need(record is not None,'REGISTERED_PARENT_REQUIRED')
    anchor=anchor_from_source(host.entry.policy,host.chain.source)
    with PreParentJournal(_root(host.entry.policy,create=False),binding_identity=anchor['binding_identity'],
                          existing_only=True,readonly=True) as journal:
        rows=journal.inspect();need(set(rows)=={digest(anchor)},'RELATED_BOUND_PARENT_REQUIRED')
        value=rows[digest(anchor)];need(value['state']=='BOUND_REAL_PARENT','BOUND_PARENT_REQUIRED')
        mapping=validate_attachment_mapping(value['parent_binding'])
        _compare_bound_record(mapping,record,info,anchor)
        _bound_time_guard(value,mapping)
    host.entry.full_guard()
    return None


def require_bound_operation_local(policy,operation_id):
    """Before public drain/cold start, real registered history plus original map.

    Borrows the original zero-write local reader's locks and Owned/H snapshot;
    it does not construct a service or return an execution permit.
    """
    from .draft_group_local_reader import (_authorize,_readonly_locks,_readonly_database,
                                          _metadata,_validated_projection)
    guard=_authorize(policy,policy.actor);before=_metadata(policy)
    from .draft_group_parent import check_parent_records_in,candidate_sha
    from .draft_group_input_files import InputFiles
    from .draft_group_operator_source_codec import SOURCE_PROFILE
    with _readonly_locks(policy) as (_,locks_current):
        guard();locks_current();need(_metadata(policy)==before,'LOCAL_SOURCE_CHANGED')
        with _readonly_database(policy) as (db,history):
            version=db.execute('PRAGMA user_version').fetchone()[0]
            need(type(version) is int and version==9,'SCHEMA9_REQUIRED')
            observed=_validated_projection(db,policy,operation_id,'STATUS','OPERATOR_ATTESTED',
                                           version,history_locators=history)
            need(observed['lookup']=='FOUND'
                 and observed['parent_registration']=='REGISTERED_HISTORICAL','REGISTERED_PARENT_REQUIRED')
            info=check_parent_records_in(db,history_policy=policy,history_locators=history)
            record=info['executions'].get(operation_id);need(record is not None,'REGISTERED_PARENT_REQUIRED')
            source=InputFiles(policy,guard).read('source',record['parent']['source_material_sha'])
            profile=source.value['profile']
            if profile in ('GROUP_BATCH_NATIVE_SOURCE_REVIEW_V1','GROUP_BATCH_NATIVE_SOURCE_BASELINE_V2'):
                guard();locks_current();return None
            need(profile==SOURCE_PROFILE,'UNKNOWN_SOURCE_PROFILE')
            anchor=anchor_from_source(policy,source.value)
            with PreParentJournal(_root(policy,create=False),binding_identity=anchor['binding_identity'],
                                  existing_only=True,readonly=True) as journal:
                rows=journal.inspect();need(set(rows)=={digest(anchor)},'RELATED_BOUND_PARENT_REQUIRED')
                row=rows[digest(anchor)]
                need(row['state']=='BOUND_REAL_PARENT','BOUND_PARENT_REQUIRED')
                mapping=validate_attachment_mapping(row['parent_binding'])
                _compare_bound_record(mapping,record,info,anchor)
                if 'time_model' in row:
                    from .own_business_temporal import _CEILING
                    current_deadline=_CEILING.get();now=time.monotonic()
                    need(type(current_deadline) in (int,float) and math.isfinite(current_deadline)
                         and now<current_deadline<=now+300,'TIME06_LOCAL_ACTION_DEADLINE_REQUIRED')
                _bound_time_guard(row,mapping)
            guard();locks_current();need(_metadata(policy)==before,'LOCAL_SOURCE_CHANGED')
        guard();locks_current();need(_metadata(policy)==before,'LOCAL_SOURCE_CHANGED')
    return None

# TIME06: explicit, newly issued only. The old model above stays distinct.
_TIME06_FIRST=ContextVar('fixed_time06_first_absence',default=None)
_TIME06_ACTION=ContextVar('fixed_time06_actual_action',default=None)
_TIME06_RESULT=ContextVar('fixed_time06_actual_complete_result',default=None)
_TIME06_CAPTURE=WeakKeyDictionary()


class Time06FirstAbsence:
    __slots__=('__weakref__',)
    def __new__(cls,*a,**kw):need(False,'TIME06_PRIVATE_ABSENCE_REQUIRED')


class Time06CaptureScope:
    __slots__=('__weakref__',)
    def __new__(cls,*a,**kw):need(False,'TIME06_PRIVATE_CAPTURE_REQUIRED')


class Time06PrepareResult:
    __slots__=('__weakref__',)
    def __new__(cls,*a,**kw):need(False,'TIME06_PRIVATE_RESULT_REQUIRED')


@dataclass
class _Time06FirstFacts:
    receipt:object
    policy:object
    pins:object
    source:dict
    runtime:dict
    anchor:dict
    observation:dict
    db:object
    history:object
    closure:object
    guard:object
    image:dict
    owner:tuple
    journal:object=None
    head_sha:object=None


@dataclass(frozen=True)
class _Time06ActionFacts:
    host:object
    name:str
    arguments_raw:str
    deadline:float
    cancel:object
    owner:tuple


def _runtime_policy(value):
    from .draft_group_operator_time_v2 import POLICY_PROFILE_V2,validate_runtime_policy_v2
    if type(value) is dict and value.get('profile')==POLICY_PROFILE_V2:
        return validate_runtime_policy_v2(value)
    from .draft_group_operator_source_codec import validate_runtime_policy
    return validate_runtime_policy(value)


def _time06_policy(value):
    from .draft_group_operator_time_v2 import POLICY_PROFILE_V2,validate_runtime_policy_v2
    if type(value) is dict and value.get('profile')==POLICY_PROFILE_V2:
        return validate_runtime_policy_v2(value)
    return None


def _invocation_sha(parent_pid,loader_anchor,configuration_sha,deadline):
    return digest({'profile':'GROUP_OPERATOR_FIRST_FIXED_INVOCATION_V1',
        'parent_pid':parent_pid,'loader_anchor':loader_anchor,
        'configuration_sha':configuration_sha,'absolute_deadline':deadline})


def _time06_observation(policy,pins,source,runtime,deadline,absence_sha,loader_anchor):
    from . import draft_group_first_time_values as t
    p=_time06_policy(runtime);need(p is not None,'TIME06_POLICY_REQUIRED')
    old=_observation(policy,pins,source,runtime,deadline)
    lifetime=min(p['source_lifetime_not_after_ms'],source['expires_policy']['not_after']*1000)
    old['not_after_ms']=min(old['not_after_ms'],lifetime)
    from .draft_group_preparent_journal import OBSERVATION_KEYS
    return t.validate_observation(dict(old,schema=2,profile=t.OBSERVATION_PROFILE,
        time_model=t.TIME_MODEL,source_lifetime_not_after_ms=lifetime,
        first_absence_sha=absence_sha,issuer_parent_pid=os.getpid(),
        first_invocation_sha=_invocation_sha(os.getpid(),loader_anchor,pins.configuration_sha,deadline)),
        OBSERVATION_KEYS,validate_observation)


@contextmanager
def _time06_unissued_scope(policy,pins,source,runtime,anchor,deadline,loader_anchor):
    """Only called under the original actual F startup gate, before any write."""
    from .draft_group_local_reader import _authorize,_readonly_locks,_readonly_database,_metadata
    from .draft_group_read_family_files import FamilyFiles
    from .draft_group_read_family_store import original_root_scope
    from .draft_group_runtime_host import PinnedFile
    need(_TIME06_FIRST.get() is None,'TIME06_FIRST_REENTRANT')
    guard=_authorize(policy,policy.actor);before=_metadata(policy)
    origin=None;original=None
    try:
        origin=PinnedFile(pins.original_root_evidence_path,pins.original_root_evidence_sha,2*1024*1024)
        evidence=json.loads(origin.raw);guard()
        with _readonly_locks(policy) as (_,locks_current):
            with _readonly_database(policy) as (db,history):
                def current():
                    guard();locks_current();origin.check()
                    need(_metadata(policy)==before and time.monotonic()<deadline,'ABSENCE_FENCE_CHANGED')
                files=FamilyFiles(policy,current)
                with original_root_scope(db,files,evidence,source_kind='OPERATOR_ATTESTED',history_locators=history) as closure:
                    image=_absence_image(policy,db,history,closure,files,source,runtime,current)
                    receipt=object.__new__(Time06FirstAbsence)
                    observation=_time06_observation(policy,pins,source,runtime,deadline,digest(image),loader_anchor)
                    facts=_Time06FirstFacts(receipt,policy,pins,source,runtime,anchor,observation,
                        db,history,closure,current,image,(os.getpid(),threading.get_ident()))
                    token=_TIME06_FIRST.set(facts)
                    try:yield receipt,observation;current();closure.current()
                    finally:_TIME06_FIRST.reset(token)
    except BaseException as error:original=error;raise
    finally:
        if origin is not None:close_all([origin.close],original)


@contextmanager
def time06_first_reservation_scope(receipt,journal,anchor,observation):
    facts=_TIME06_FIRST.get()
    need(type(receipt) is Time06FirstAbsence and type(facts) is _Time06FirstFacts
         and facts.receipt is receipt and facts.anchor==validate_anchor(anchor)
         and facts.owner==(os.getpid(),threading.get_ident())
         and canonical(facts.observation)==canonical(observation)
         and journal.root==facts.policy.root/ROOT_NAME
         and facts.journal is None,'TIME06_ABSENCE_RECEIPT_UNISSUED')
    facts.journal=journal
    def fence(result=None):
        need(_TIME06_FIRST.get() is facts,'TIME06_ABSENCE_SCOPE_CLOSED')
        facts.guard();facts.closure.current()
        files=facts.closure.files
        need(canonical(_absence_image(facts.policy,facts.db,facts.history,facts.closure,files,
            facts.source,facts.runtime,facts.guard))==canonical(facts.image),'ABSENCE_CHANGED')
        rows=journal.inspect();key=digest(anchor)
        if result is None:
            need(not rows,'TIME06_EXISTING_TECHNICAL_RESERVATION')
        else:
            need(result['created'] is True and set(rows)=={key},'TIME06_FIRST_RESERVE_UNKNOWN')
            row=rows[key]
            need(row['head_sha']==result['head_sha'] and row['events']==['RESERVED_PRE_PARENT']
                 and row['records'][0]['observation']==facts.observation,'TIME06_OWN_RESERVATION_CHANGED')
            facts.head_sha=result['head_sha']
    yield fence


def require_time06_reserve_in_progress(journal,anchor,observation):
    facts=_TIME06_FIRST.get()
    need(type(facts) is _Time06FirstFacts and facts.journal is journal
         and facts.head_sha is None and facts.anchor==anchor
         and facts.owner==(os.getpid(),threading.get_ident())
         and canonical(facts.observation)==canonical(observation),
         'TIME06_FIRST_RESERVE_ISSUER_REQUIRED')
    facts.guard();facts.closure.current()


@contextmanager
def time06_action_scope(host,name,arguments,deadline,cancel_guard):
    from .draft_group_host_bootstrap import run_fixed_bootstrap,dispatch_warm_group,PRIVATE_METHOD
    frame=inspect.currentframe()
    try:need(frame.f_back.f_code.co_name=='__enter__' and frame.f_back.f_back.f_code in
             (run_fixed_bootstrap.__code__,dispatch_warm_group.__code__),'TIME06_FIXED_ACTION_CALLER')
    finally:del frame
    from .draft_group_host_operator import _host,is_operator
    if not is_operator(host) or _time06_policy(host.chain.runtime_policy) is None:
        yield
        return
    entry=_host(host)
    need(_TIME06_ACTION.get() is None and deadline==entry.deadline
         and cancel_guard is entry.cancel,'TIME06_ACTION_CONTEXT_CHANGED')
    if name==PRIVATE_METHOD:need(type(arguments) is dict and not arguments,'TIME06_PRIVATE_ARGUMENTS')
    else:
        from .draft_group_tools import validate,NETWORK
        validate(name,arguments);need(name in NETWORK and arguments['connection_id']==entry.policy.data['connection_id'],
                                     'TIME06_ACTION_SCOPE')
    value=_Time06ActionFacts(host,name,canonical(arguments),deadline,cancel_guard,(os.getpid(),threading.get_ident()))
    token=_TIME06_ACTION.set(value)
    try:yield
    finally:_TIME06_ACTION.reset(token)


def _capture_action(host):
    from .draft_group_host_operator import _host
    entry=_host(host);value=_TIME06_ACTION.get()
    need(type(value) is _Time06ActionFacts and value.host is host
         and value.owner==(os.getpid(),threading.get_ident()) and value.deadline==entry.deadline
         and value.cancel is entry.cancel and time.monotonic()<value.deadline,'TIME06_ACTUAL_ACTION_REQUIRED')
    entry.full_guard();host.chain.check()
    return value


def _time06_successor_in(host,db,history,current,action):
    from .draft_group_parent import check_parent_records_in
    from .draft_group_history_context import require_history
    from .draft_group_store import _current_child,_require_read_safety
    from .draft_group_read_family_store import _states
    require_history(host.entry.policy,db,history)
    need(current.get('prepare_result') is not None,'TIME06_ORIGINAL_PREPARE_RESULT_UNKNOWN')
    mapping=validate_attachment_mapping(current['parent_binding'])
    need(time.time()*1000<mapping['not_after_ms'],'TIME06_SOURCE_OR_PARENT_EXPIRED')
    args=json.loads(action.arguments_raw);operation=args['operation_id']
    info=check_parent_records_in(db,history_policy=host.entry.policy,history_locators=history)
    record=info['executions'].get(operation);need(record is not None,'TIME06_PARENT_REQUIRED')
    _compare_bound_record(mapping,record,info,anchor_from_source(host.entry.policy,host.chain.source))
    states=_states(db)
    state=states[host.chain.source['binding_sha']][0]
    op,batch=_current_child(state,operation);_require_read_safety(op)
    need(not any(c['state'] in ('CONSUMED_UNKNOWN','UNKNOWN','KNOWN_REJECTED')
                 or c.get('outcome')=='UNKNOWN' for c in op['claims']),'TIME06_BUSINESS_UNKNOWN')
    need(op['plan']['route']=='CREATE_NEW' and not op['old_refs'],'TIME06_ORIGINAL_NEW_ONLY')
    if action.name.endswith('.readback'):
        slot='NEW' if args['phase']=='NEW' else 'FINAL_NEW'
        expected='NEW_OBSERVED' if slot=='NEW' else 'SWITCHED_OLD_RETAINED'
        need(op['state']==expected and not any(c['slot']==slot for c in op['claims']),
             'TIME06_ORIGINAL_READ_SLOT_NOT_AVAILABLE')
    else:need(op['state'] in ('PLANNED','NEW_OBSERVED','NEW_VERIFIED','SWITCHED_OLD_RETAINED'),
              'TIME06_BUSINESS_PHASE_NOT_ALLOWED')
    # The actual original reducer and later Token/purpose/claim guard still own
    # budgets and admission; this is only eligibility to take a new observation.
    require_history(host.entry.policy,db,history)
    return min(mapping['not_after_ms'],current['source_lifetime_not_after_ms'])


def require_time06_capture_in(host,db,*,history_locators):
    from .draft_group_host_operator import _host
    from .draft_group_history_context import require_history
    from .draft_group_read_family_files import FamilyFiles
    from .draft_group_read_family_store import original_root_scope
    from .draft_group_host_bootstrap import PRIVATE_METHOD
    entry=_host(host);action=_capture_action(host);require_history(entry.policy,db,history_locators)
    runtime=_time06_policy(host.chain.runtime_policy);need(runtime is not None,'TIME06_POLICY_REQUIRED')
    anchor=anchor_from_source(entry.policy,host.chain.source)
    with PreParentJournal(_root(entry.policy,create=False),binding_identity=anchor['binding_identity'],
                          existing_only=True,readonly=True) as journal:
        values=journal.inspect();key=digest(anchor);need(set(values)=={key},'TIME06_RELATED_TECHNICAL_STATE')
        row=values[key];need(row.get('time_model')==runtime['time_model'],'TIME06_NO_LEGACY_MIGRATION')
        first=row['records'][0]['observation']
        need(first['source_sha']==host.pins.source_sha
             and first['binding_sha']==digest(runtime['binding'])
             and first['epoch']==entry.policy.data['epoch'],'TIME06_FIRST_IDENTITY_CHANGED')
        if action.name==PRIVATE_METHOD:
            from .group_host_jobs import _CHILD_INVOCATIONS,validate_child_invocation
            active=[value for value,facts in _CHILD_INVOCATIONS.items() if facts.thread==threading.get_ident()]
            need(len(active)==1,'TIME06_ACTUAL_CHILD_REQUIRED')
            invocation=validate_child_invocation(active[0])
            need(invocation.constants['POLICY_PATH']==str(entry.policy.path)
                 and invocation.request['selector_sha']==host.pins.configuration_sha
                 and invocation.parent_pid==first['issuer_parent_pid']
                 and first['first_invocation_sha']==_invocation_sha(invocation.parent_pid,
                    invocation.request['loader_anchor'],host.pins.configuration_sha,entry.deadline),
                 'TIME06_FIRST_CHILD_SCOPE_CHANGED')
            allowed={'RESERVED_PRE_PARENT','OWNER_ABSENCE_OBSERVED','DRAIN_MAY_EFFECT',
                     'LIFETIME_RELEASE_OBSERVED','SPAWN_MAY_EFFECT'}
            need(row['state']=='NOT_CREATED' and set(row['events'])<=allowed
                 and 'SPAWN_MAY_EFFECT' in row['events']
                 and time.time()*1000<row['original_technical_not_after_ms'],
                 'TIME06_FIRST_TECHNICAL_UNKNOWN_OR_CONSUMED')
            files=FamilyFiles(entry.policy,entry.loop_guard)
            with original_root_scope(db,files,host.chain.original_root_evidence,
                    source_kind='OPERATOR_ATTESTED',history_locators=history_locators) as closure:
                image=_absence_image(entry.policy,db,history_locators,closure,files,
                                     host.chain.source,runtime,entry.loop_guard)
                need(digest(image)==first['first_absence_sha'],'TIME06_CHILD_ABSENCE_CHANGED')
            cap=min(first['source_lifetime_not_after_ms'],runtime['source_lifetime_not_after_ms'])
        else:
            need(row['state']=='BOUND_REAL_PARENT','TIME06_DURABLE_BOUND_REQUIRED')
            _time06_successor_in(host,db,history_locators,row,action)
            # Stable case upper bound in the sealed pass image. Historical
            # effective review A is independently non-increasing in ReviewV2;
            # current QA/rights may tighten it without changing this image.
            cap=min(first['source_lifetime_not_after_ms'],runtime['source_lifetime_not_after_ms'])
        need(time.time()*1000<cap,'TIME06_SOURCE_EXPIRED')
        need(sum(1 for value in _TIME06_CAPTURE.values() if value[1] is entry)<4,
             'TIME06_CAPTURE_SCOPE_CAPACITY')
        receipt=object.__new__(Time06CaptureScope)
        from .own_validation_scope import _transaction_marker
        try:
            _TIME06_CAPTURE[receipt]=(host,entry,db,history_locators,_transaction_marker(db),action,cap,
                                      canonical(row), (os.getpid(),threading.get_ident()))
            entry.issued[id(receipt)]=receipt
            if not getattr(entry,'_time06_capture_cleanup',False):
                entry.stack.callback(_close_time06_capture_entry,entry)
                entry._time06_capture_cleanup=True
            return receipt
        except BaseException:
            close_time06_capture_scope(receipt)
            raise


def time06_capture_guard(scope,host,db,*,history_locators):
    from .own_validation_scope import _transaction_marker
    from .draft_group_history_context import require_history
    need(type(scope) is Time06CaptureScope,'TIME06_CAPTURE_UNISSUED')
    facts=_TIME06_CAPTURE.get(scope)
    need(type(scope) is Time06CaptureScope and facts is not None and facts[0] is host
         and facts[1] is host.entry and facts[2] is db and facts[3] is history_locators
         and facts[1].issued.get(id(scope)) is scope
         and facts[4]==_transaction_marker(db) and facts[5] is _TIME06_ACTION.get()
         and facts[8]==(os.getpid(),threading.get_ident()),'TIME06_CAPTURE_SCOPE_CHANGED')
    require_history(host.entry.policy,db,history_locators);_capture_action(host)
    fresh=require_time06_capture_in(host,db,history_locators=history_locators)
    try:need(_TIME06_CAPTURE[fresh][6:8]==facts[6:8],'TIME06_CAPTURE_FACTS_CHANGED')
    finally:close_time06_capture_scope(fresh)
    return scope


def time06_capture_source_cap(scope):
    need(type(scope) is Time06CaptureScope,'TIME06_CAPTURE_UNISSUED')
    facts=_TIME06_CAPTURE.get(scope);need(facts is not None,'TIME06_CAPTURE_UNISSUED')
    time06_capture_guard(scope,facts[0],facts[2],history_locators=facts[3])
    return facts[6]


def close_time06_capture_scope(scope):
    """Explicit same-H finally + entry abort cleanup. No guard on revocation."""
    need(type(scope) is Time06CaptureScope,'TIME06_CAPTURE_UNISSUED')
    facts=_TIME06_CAPTURE.pop(scope,None)
    if facts is not None:facts[1].issued.pop(id(scope),None)


def _close_time06_capture_entry(entry):
    for scope,facts in tuple(_TIME06_CAPTURE.items()):
        if facts[1] is entry:close_time06_capture_scope(scope)


def time06_current_action_guard(host):
    """No issuance. Existing private binding/QA/H refresh owns current rights.

    In particular, do not re-run first absence after this same attempt has
    legitimately appended FIRST/Review/claim facts, or classify its own active
    dispatch as an earlier unknown re-entry.
    """
    _capture_action(host)
    policy=_time06_policy(host.chain.runtime_policy)
    need(policy is not None and time.time()*1000<min(policy['source_lifetime_not_after_ms'],
        host.chain.source['expires_policy']['not_after']*1000),'TIME06_SOURCE_EXPIRED')
    return None


@contextmanager
def _time06_normal_result_scope(receipt,journal,anchor,current):
    value=_TIME06_RESULT.get()
    need(type(receipt) is Time06PrepareResult and type(value) is tuple and len(value)==5
         and value[0] is receipt and value[1].journal is journal
         and value[1].anchor==anchor and value[1].owner==(os.getpid(),threading.get_ident()),
         'TIME06_RESULT_UNISSUED')
    _,start,result,process,pin=value
    def fence():
        from .group_host_external_loader import check_process_loader_anchor
        from .own_connection_broker import read_runtime
        check_process_loader_anchor(start.loader_anchor);pin.check()
        need(time.monotonic()<start.deadline and time.time()*1000<start.observation['not_after_ms'],
             'TIME06_ORIGINAL_RESULT_EXPIRED')
        actual,_=read_runtime(start.policy)
        need(actual==result['runtime'] and actual['pid']==process.pid
             and _CHILDREN[digest(anchor)]['process'] is process,'TIME06_ORIGINAL_H_CHANGED')
    from . import draft_group_first_time_values as t
    fence();facts=t.validate_result({'schema':1,'profile':t.RESULT_PROFILE,'authority':False,
        'preparation_identity_sha':preparation_identity(anchor),
        'parent_mapping_sha':digest(current['parent_binding']),
        'response_sha':digest(result['result']),'runtime_sha':digest(result['runtime']),
        'service_pid':process.pid,'original_technical_not_after_ms':start.observation['not_after_ms'],
        'observed_at_ms':int(time.time()*1000),'owner_kind':'FIXED_LONG_LIVED_H'})
    yield facts,fence


def _time06_note_complete(start,result,process,pin,current):
    if 'time_model' not in current:return
    receipt=object.__new__(Time06PrepareResult)
    token=_TIME06_RESULT.set((receipt,start,result,process,pin))
    try:start.journal.note_prepare_known(start.anchor,expected_head_sha=current['head_sha'],receipt=receipt)
    finally:_TIME06_RESULT.reset(token)


def _group_issuance_files(policy,guard,family_files):
    """Read fixed Group issuance folders only; unknown grammar/codec is HOLD.

    Ordinary Own prepared/upload stores are neither scanned nor classified as
    Group issuance. All bytes stay transient; facts retain only paths/pins/SHA.
    """
    import re
    from .draft_group_input_files import ROLES,decode as decode_input
    from .draft_group_source_review import validate as validate_review
    from .draft_group_read_family_files import PREFIX as FAMILY_PREFIX,FOLDER
    from .draft_group_read_family_values import decode as decode_family
    from . import draft_group_response_codec as response_codec
    roles=[(folder,prefix,role,maximum) for role,(folder,prefix,_,maximum) in ROLES.items()]
    roles += [('group-proofs','group-source-review-','source_review',2*1024*1024),
              ('group-proofs','group-response-','response',16384),
              ('group-proofs','group-response-snapshot-','response_snapshot',response_codec.MAX_BODY)]
    aliases={'proof':'registration_proof','head_history':'head','upload_reuse':'upload_reuse'}
    result=[];nodes=[];total=0;names_total=0
    def scan(base,folder,entries):
        nonlocal total,names_total
        directory=base/folder
        if not os.path.lexists(directory):return (str(directory),None,[])
        before=full(directory.lstat());held=[];original=None
        try:
            capacity(1);fd=os.open(directory,os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW|os.O_NONBLOCK);held.append(fd)
            need(stat.S_ISDIR(before[2]) and before[3]==os.getuid()
                 and stat.S_IMODE(before[2])==0o700 and full(os.fstat(fd))==before,'ABSENCE_DIRECTORY_UNSAFE')
            names=sorted(os.listdir(fd));names_total+=len(names);need(names_total<=4096,'ABSENCE_FILE_COUNT')
            output=[]
            for name in names:
                guard();matches=[]
                for prefix,role,maximum in entries:
                    match=re.fullmatch(re.escape(prefix)+r'([0-9a-f]{64})\.json',name)
                    if match:matches.append((match[1],role,maximum))
                need(len(matches)==1,'ABSENCE_UNKNOWN_OR_PARTIAL_GROUP_FILE')
                key,role,maximum=matches[0];capacity(1)
                leaf=os.open(name,os.O_RDONLY|os.O_NOFOLLOW|os.O_NONBLOCK,dir_fd=fd);held.append(leaf)
                try:
                    info=os.fstat(leaf);pin=full(info);total+=info.st_size
                    need(stat.S_ISREG(info.st_mode) and info.st_uid==os.getuid()
                         and stat.S_IMODE(info.st_mode)==0o600 and info.st_nlink==1
                         and 0<info.st_size<=maximum and total<=64*1024*1024,'ABSENCE_FILE_BOUND')
                    raw=os.pread(leaf,info.st_size+1,0)
                    need(len(raw)==info.st_size and pin==full(os.fstat(leaf))
                         ==full(os.stat(name,dir_fd=fd,follow_symlinks=False)),'ABSENCE_FILE_CHANGED')
                    sha=sha256(raw).hexdigest()
                    if folder==FOLDER:value=decode_family(role,raw)
                    elif role=='source_review':
                        value=validate_review(json.loads(raw));need(raw==(canonical(value)+'\n').encode(),'ABSENCE_FILE_CANONICAL')
                    elif role=='response':value=response_codec.decode_primary(raw)
                    elif role=='response_snapshot':value={'claim_id':key}
                    else:value=decode_input(role,raw)
                    node_role=aliases.get(role,role)
                    nodes.append((node_role,key,value))
                    # Hashed file references use raw bytes SHA; reservation and
                    # response keys use their own fixed role identity as well.
                    if sha!=key:nodes.append((node_role,sha,value))
                    output.append((name,list(pin),sha))
                finally:
                    def release_leaf():
                        need(held[-1]==leaf,'ABSENCE_FD_OWNER_CHANGED')
                        held.pop() # Transfer ownership before a possibly failing close.
                        os.close(leaf)
                    close_all([release_leaf],sys.exc_info()[1])
            need(before==full(os.fstat(fd))==full(directory.lstat())
                 and names==sorted(os.listdir(fd)),'ABSENCE_DIRECTORY_CHANGED')
            guard();return (str(directory),list(before),output)
        except BaseException as error:original=error;raise
        finally:close_all([lambda fd=fd:os.close(fd) for fd in reversed(held)],original)
    for folder in ('group-inputs','group-proofs','group-targets'):
        result.append(scan(policy.root,folder,[(prefix,role,m) for f,prefix,role,m in roles if f==folder]))
    result.append(scan(family_files.anchor,FOLDER,[(prefix,role,2*1024*1024)
                  for role,prefix in FAMILY_PREFIX.items()]))
    # The selected head is independently decoded and pinned, never ignored.
    head=policy.root/'group-input-head.json'
    if os.path.lexists(head):
        from .own_bootstrap_security import private_read,path_check
        raw,pin=private_read(head)
        need(len(raw)<=16384,'ABSENCE_HEAD_SIZE')
        value=decode_input('head_history',raw)
        need(path_check(head)==pin,'ABSENCE_HEAD_CHANGED')
        nodes.append(('head',sha256(raw).hexdigest(),value));result.append((str(head),list(pin),sha256(raw).hexdigest()))
    else:result.append((str(head),None,None))
    guard();return result,nodes,total


def _time06_related_seeds(policy,db,history,source,guard):
    """Actual H prepared relation supplies cross-profile selector/manifest joins."""
    from .draft_group_runtime_host import PinnedFile
    from .draft_group_selected_source_codec import decode_manifest
    from .draft_group_operator_materials import prepared_relations,projection,qa_set
    from .own_selected_history import _PreparedHistoryReader
    held=[];reader=None;original=None
    def pin(ref):
        value=PinnedFile(ref['path'],ref['sha256'],2*1024*1024);held.append(value)
        need(len(value.raw)==ref['size'],'ABSENCE_FIXED_REF_SIZE');return value.raw
    try:
        q=qa_set(json.loads(pin(source['qa_set_ref'])))
        project=projection(json.loads(pin(q['member_projection_ref'])))
        selected,_,selection_sha=decode_manifest(pin(source['selection_ref']),
            expected_member_projection=tuple(tuple(x) for x in project['member_projection']))
        need(selection_sha==source['selection_ref']['sha256']
             and selected['queue_sha256']==source['original_queue_sha']
             and selected['request_set_sha256']==source['original_request_set_sha'],'ABSENCE_SELECTION_CHANGED')
        relations=prepared_relations(json.loads(pin(source['prepared_relation_inventory_ref'])),source)['rows']
        members=[m for m in selected['members'] if m['binding_sha256']==source['binding_sha']]
        need([m['article_id'] for m in members]==source['allowed_read_scope']['member_ids']
             ==[r['selected_article_id'] for r in relations],'ABSENCE_PARTITION_CHANGED')
        reader=_PreparedHistoryReader(policy,db,history);actual=[]
        for member,row in zip(members,relations):
            guard();need(member['selector']==row['selector'] and member['prepare_request_key']==row['prepare_request_key'],
                         'ABSENCE_PREPARED_SELECTOR_CHANGED')
            relation=reader.prepared_relation(prepare_request_key=row['prepare_request_key'],selector=row['selector'])
            need(digest(relation)==row['prepared_relation_sha256'],'ABSENCE_ACTUAL_PREPARED_CHANGED')
            selector=row['selector'];manifest,manifest_sha=reader._bundle_full(db,reader.profile,selector['bundle_id'],selector['version'])
            need(manifest_sha==selector['content_digest'] and relation['assets']==manifest['assets'],
                 'ABSENCE_ORIGINAL_MANIFEST_CHANGED')
            actual.append({'article_id':member['article_id'],'selector':selector,'manifest_sha':manifest_sha,
                'prepare_request_key':row['prepare_request_key']})
        reader._check_all_history()
        result={'original_queue_sha':source['original_queue_sha'],
            'original_request_set_sha':source['original_request_set_sha'],
            'account_partition_sha':source['account_partition_sha'],
            'operator_request_identity_sha':source['operator_request_identity_sha'],
            'members':actual}
        for value in held:value.check()
        guard();return result
    except BaseException as error:original=error;raise
    finally:close_all(([reader.close] if reader is not None else [])+[x.close for x in reversed(held)],original)


def _absence_image(policy,db,history,closure,files,source,runtime,guard):
    from .draft_group_history_context import require_history
    from .draft_group_read_family_store import query_first_in,_states
    from .draft_group_first_time_values import related_components
    require_history(policy,db,history);closure.current();guard()
    request=json.loads(closure.origin_raw)['origin_request_identity_sha']
    need(request==source['operator_request_identity_sha'],'ABSENCE_ORIGINAL_REQUEST_CHANGED')
    first=query_first_in(db,files,request,root_closure=closure,guard=guard)
    need(first=={'state':'ABSENT','authority':False},'TIME06_FIRST_NOT_ABSENT')
    states=_states(db) # Every pool and original ancestry is replayed.
    seeds=_time06_related_seeds(policy,db,history,source,guard)
    inventory,nodes,file_bytes=_group_issuance_files(policy,guard,files)
    sql=[];used=file_bytes;row_count=0
    tables=[r[0] for r in db.execute("SELECT name FROM sqlite_master WHERE type='table' AND name GLOB 'group_*' ORDER BY name")]
    need(0<len(tables)<=32,'ABSENCE_GROUP_LAYOUT')
    table_roles={'group_batches':'batch','group_operations':'operation','group_claims':'claim',
        'group_previews':'preview','group_preview_read_grants':'purpose','group_preview_read_claims':'claim',
        'group_operation_old_refs':'operation','group_member_origins':'operation','group_queue':'operation',
        'group_own_step_links':'claim','group_active_members':'member'}
    def event_role(value):
        p=value.get('candidate',value);profile=p.get('profile','') if type(p) is dict else ''
        if 'SOURCE_REVIEW' in profile:return 'source_review'
        if 'PARENT' in profile:return 'parent'
        if 'FIRST' in profile:return 'first'
        if 'COVENANT' in profile:return 'covenant'
        if 'REGISTRATION' in profile:return 'registration'
        return 'preview'
    for table in tables:
        need(table.replace('_','').isalnum(),'ABSENCE_GROUP_LAYOUT')
        rows=[]
        for row in db.execute('SELECT * FROM '+table):
            row_count+=1;need(row_count<=500000,'ABSENCE_SQL_LIMIT')
            row=dict(row);used+=len(canonical(row).encode());need(used<=64*1024*1024,'ABSENCE_SQL_LIMIT')
            rows.append(row)
            if table in ('group_pools','group_active_members') or (table=='group_events' and row['kind']=='POOL'):
                continue # Roster/baseline summaries aren't case issuance; all remain in the SQL fence.
            value=json.loads(row['payload']) if 'payload' in row else json.loads(row['value']) if 'value' in row else row
            role=event_role(value) if table=='group_events' else table_roles.get(table)
            need(role is not None,'ABSENCE_UNCLASSIFIED_GROUP_TABLE')
            key=(row.get('operation_id') if role=='operation' else row.get('claim_id') if role=='claim'
                 else row.get('preview_id') if role=='preview' else row.get('batch_id') if role=='batch'
                 else row.get('grant_id') if role=='purpose' else None)
            if key is None:key=digest(value.get('candidate',value)) if type(value) is dict else digest(value)
            nodes.append((role,key,value))
        sql.append((table,sorted(rows,key=canonical)))
    joins=related_components(nodes,seeds)
    need(not joins['related'],'TIME06_RELATED_PRIOR_ISSUANCE')
    need(not joins['unknown'],'TIME06_CROSS_PROFILE_RELATION_UNPROVEN')
    family=files._absence_inventory(request)
    image={'profile':'GROUP_OPERATOR_FIRST_ABSENCE_OBSERVATION_V1','authority':False,
        'anchor':anchor_from_source(policy,source),'source_sha':runtime['source_material_sha'],
        'runtime_policy_sha':digest(runtime),'root_evidence_sha':sha256(closure.origin_raw).hexdigest(),
        'seed_projection_sha':digest(seeds),'related_join_sha':digest(joins),'sql_sha':digest(sql),
        'all_pool_heads':[(key,seq,head) for key,(_,seq,head) in states.items()],
        'group_files':inventory,'family_inventory':family}
    closure.current();files._pure_absence(family);guard();require_history(policy,db,history)
    need(_group_issuance_files(policy,guard,files)[0]==inventory,'ABSENCE_FILES_CHANGED')
    return image


_TIME06_HISTORICAL_RESULT=ContextVar('fixed_time06_historical_graph_known',default=None)


def _bound_time_guard(current,mapping):
    if 'time_model' not in current:
        need(time.time()*1000<min(current['not_after_ms'],mapping['not_after_ms']),'BOUND_PARENT_EXPIRED')
        return
    from . import draft_group_first_time_values as t
    need(mapping['profile']==t.MAPPING_PROFILE and current.get('prepare_result') is not None,
         'TIME06_ORIGINAL_PREPARE_RESULT_UNKNOWN')
    t.validate_result(current['prepare_result'])
    need(time.time()*1000<min(current['source_lifetime_not_after_ms'],mapping['not_after_ms']),
         'TIME06_SOURCE_OR_PARENT_EXPIRED')


def _time06_recover_known(facts,journal,anchor,current):
    # Read-only original graph query resolved the prepare's business effect.
    # This is explicitly not an assertion about the lost original ACK/Popen.
    need('time_model' in current and current['state']=='BOUND_REAL_PARENT'
         and current.get('prepare_result') is None,'TIME06_RECOVERY_STATE')
    _recovery_history_fence(facts);_recovery_write_guard(facts)
    receipt=object.__new__(Time06PrepareResult)
    token=_TIME06_HISTORICAL_RESULT.set((receipt,facts,journal,canonical(current)))
    try:return journal.note_prepare_known(anchor,expected_head_sha=current['head_sha'],receipt=receipt)
    finally:_TIME06_HISTORICAL_RESULT.reset(token)


# Keep original normal-result issuer separate from historical result closure.
@contextmanager
def time06_prepare_result_scope(receipt,journal,anchor,current):
    historical=_TIME06_HISTORICAL_RESULT.get()
    if historical is None:
        with _time06_normal_result_scope(receipt,journal,anchor,current) as value:yield value
        return
    issued,facts,actual_journal,current_raw=historical
    need(type(receipt) is Time06PrepareResult and receipt is issued and actual_journal is journal
         and facts.anchor_raw==canonical(anchor) and current_raw==canonical(current),
         'TIME06_HISTORICAL_RESULT_UNISSUED')
    from . import draft_group_first_time_values as t
    def fence():
        need(_TIME06_HISTORICAL_RESULT.get() is historical,'TIME06_HISTORICAL_RESULT_SCOPE_CLOSED')
        _recovery_write_guard(facts);mapping=_recovery_history_fence(facts)
        need(canonical(mapping)==canonical(current['parent_binding']),'TIME06_RECOVERY_MAPPING_CHANGED')
    fence();mapping=current['parent_binding']
    value=t.validate_result({'schema':2,'profile':t.HISTORY_RESULT_PROFILE,'authority':False,
        'preparation_identity_sha':preparation_identity(anchor),'parent_mapping_sha':digest(mapping),
        'parent_event':mapping['parent_event'],'plan_event':mapping['plan_event'],
        'original_technical_not_after_ms':current['original_technical_not_after_ms'],
        'observed_at_ms':int(time.time()*1000),'observation_origin':HISTORICAL_ATTACHMENT_ORIGIN,
        'original_response':'NOT_ASSERTED','owner_kind':'HISTORICAL_COMPLETE_PARENT_GRAPH'})
    yield value,fence
