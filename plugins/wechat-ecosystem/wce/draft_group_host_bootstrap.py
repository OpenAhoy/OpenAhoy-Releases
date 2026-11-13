"""Private same-entry cold/warm Group controller. No ordinary-start fallback."""
from .own_fd_domain import regular_fd_domain, owned_lifetime
from contextlib import ExitStack
from dataclasses import dataclass
import json
import os
import socket
import time

from .draft_group_runtime_host import (need,hold,BootstrapAccountCore,GroupExecutionGate,
    qualify_bootstrap_storage,from_verified_bootstrap,_TIME,_MONOTONIC)
from .draft_group_host_review import GroupRuntimeHost,FixedHostPins
from .own_connection_broker import Broker,AccountService
from .own_connection_policy import locked

LOCAL_NAMES=frozenset(('own.draft_groups.plan','own.draft_groups.status'))
NETWORK_NAMES=frozenset(('own.draft_groups.execute','own.draft_groups.readback'))
PRIVATE_METHOD='_wce.group.fixed_bootstrap.v1'


@dataclass(frozen=True,eq=False)
class CompleteBootstrapBinding:
    entry: object
    broker: object
    service: object
    listener: object
    runtime_pin: tuple
    socket_pin: tuple


def _bind_listener(entry,broker,service,listener):
    entry.held_pure()
    need(type(broker) is Broker and type(service) is AccountService and broker.service is service
         and entry.service is service and entry.broker is broker and type(listener) is socket.socket,'GROUP_BOOTSTRAP_LISTENER')
    broker.guard()
    guard=service.workflow.live_guard
    need(getattr(guard,'__self__',None) is broker and getattr(guard,'__func__',None) is Broker.guard,'GROUP_BOOTSTRAP_GUARD')
    binding=CompleteBootstrapBinding(entry,broker,service,listener,broker.runtime_pin,broker.socket_pin)
    entry._mechanical_pins.bind_runtime(broker)
    entry.listener_bound=True;entry.issued[id(binding)]=binding
    return binding


def run_fixed_bootstrap(policy,pins=None,*,request_name=None,request_arguments=None,received_deadline=None,native_cancel=None,startup_stream=None,startup_request_sha=None):
    """Fixed trusted child entry; caller fields contain no path, scope or budget.

    Production calls select pins from the fixed job table. Explicit pins are
    accepted only by this private component entry and still undergo the complete
    external review/arm and actual native/history qualification before storage.
    """
    deadline=_MONOTONIC()+300 if received_deadline is None else received_deadline
    with regular_fd_domain(deadline=deadline):
        from .group_host_jobs import load_fixed_host_pins
        selected=load_fixed_host_pins(policy)
        if pins is not None:
            from .draft_group_operator_review_chain import FixedOperatorHostPins
            need(type(pins) in (FixedHostPins,FixedOperatorHostPins) and pins==selected,'GROUP_FIXED_JOB_CHANGED')
        pins=selected
        need(type(request_name) in (str,type(None)) and (request_name is None or request_name in NETWORK_NAMES),'GROUP_BOOTSTRAP_REQUEST')
        # Fixed package existence/hash/expiry checks precede all constructors. Full
        # source retention/QA parsing runs only while the child's original FDs hold.
        from .draft_group_runtime_host import PinnedFile
        check=PinnedFile(pins.configuration_path,pins.configuration_sha,2*1024*1024)
        try:configuration=json.loads(check.raw)
        finally:check.close()
        check=PinnedFile(pins.source_path,pins.source_sha,2*1024*1024)
        try:source=json.loads(check.raw)
        finally:check.close()
        need(_TIME()<source['expires_policy']['not_after'],'GROUP_BOOTSTRAP_SOURCE_EXPIRED')
        policy.check()
        result=None
    with owned_lifetime(locked(policy.root/'connection.lock',nonblocking=True), deadline=deadline):
        with ExitStack() as resources:
            with regular_fd_domain(deadline=deadline):
                broker=Broker(policy);core=BootstrapAccountCore(policy)
                with GroupExecutionGate(core,deadline,native_cancel,broker=broker) as entry:
                    host=GroupRuntimeHost(entry,pins)
                    from .draft_group_first_control import time06_action_scope
                    with time06_action_scope(host,request_name or PRIVATE_METHOD,request_arguments or {},deadline,native_cancel):
                        qualification=qualify_bootstrap_storage(host,core,entry)
                        service=from_verified_bootstrap(core,entry,qualification)
                        need(broker.service is None,'GROUP_BOOTSTRAP_SERVICE_ALREADY_BOUND');broker.service=service
                        listener=resources.enter_context(broker._listener_initialized())
                        binding=_bind_listener(entry,broker,service,listener)
                        GroupExecutionGate.from_bound_bootstrap(entry,binding)
                        host.qualify_current_group_source()
                        from .draft_group_runtime_service import call_in_entry
                        # Bootstrap local producer is fixed, not a caller callback.
                        result=call_in_entry(host,request_name or PRIVATE_METHOD,request_arguments or {},deadline,native_cancel)
                    if startup_stream is not None:
                        from .own_bootstrap_ipc import send
                        if startup_request_sha is not None:
                            from .draft_group_child_control import make_public_result
                            response=make_public_result(startup_request_sha,result,broker.runtime)
                        else:response={'state':'GROUP_FIXED_BOOTSTRAP_COMPLETE','result':result,'runtime':broker.runtime}
            if startup_stream is not None:
                from .own_bootstrap_ipc import send
                send(startup_stream,response)
            # Listening and complete worker shutdown never hold the domain.
            broker.guard();broker._accept_loop(listener)
    return result


def dispatch_warm_group(service,name,arguments,deadline,cancel_guard):
    need(type(service) is AccountService and name in NETWORK_NAMES|{PRIVATE_METHOD},'GROUP_WARM_DISPATCH')
    from .group_host_jobs import load_fixed_host_pins
    guard=service.workflow.live_guard;broker=getattr(guard,'__self__',None)
    need(type(broker) is Broker and broker.service is service and getattr(guard,'__func__',None) is Broker.guard,'GROUP_WARM_BROKER_REQUIRED')
    pins=load_fixed_host_pins(service.policy)
    with GroupExecutionGate(service,deadline,cancel_guard,broker=broker) as entry:
        host=GroupRuntimeHost(entry,pins)
        from .draft_group_first_control import time06_action_scope
        with time06_action_scope(host,name,arguments,deadline,cancel_guard):
            host.qualify_current_group_source()
            from .draft_group_runtime_service import call_in_entry
            return call_in_entry(host,name,arguments,deadline,cancel_guard)


def call_group(policy,name,arguments,launcher):
    need(name in LOCAL_NAMES|NETWORK_NAMES,'GROUP_METHOD_UNKNOWN')
    if name in LOCAL_NAMES:
        from .draft_group_runtime_service import call_local
        return call_local(policy,name,arguments)
    from .draft_group_runtime_service import require_registered_operation_local
    from .own_business_temporal import bound_deadline,deadline_scope
    deadline=bound_deadline(_MONOTONIC()+300)
    with deadline_scope(deadline),regular_fd_domain(deadline=deadline):
        require_registered_operation_local(policy,name,arguments)
    # Never call ensure_started. An existing owner cannot be displaced or retried
    # as cold following a runtime refusal. The reviewed no-arg child is the sole
    # missing-owner start path, selected below under connection-start.lock.
    from .own_connection_broker import call,read_runtime,_startup_has_owner,_startup_gate,stale_endpoint
    with _startup_gate(policy,deadline):
        if _startup_has_owner(policy):
            from .own_bootstrap_ipc import socket_pin
            from .own_connection_broker import SOCKET
            expected_runtime=(*read_runtime(policy),socket_pin(policy.root/SOCKET))
        else:
            stale_endpoint(policy)
            from .group_host_jobs import load_fixed_host_pins
            pins=load_fixed_host_pins(policy)
            from .draft_group_fixed_child import start_fixed_child_once
            return start_fixed_child_once(policy,pins,deadline,launcher,name=name,arguments=arguments)
    return _call_group_existing(policy,name,arguments,deadline,expected_runtime=expected_runtime)


def _call_group_existing(policy,name,arguments,absolute_deadline,*,private_invocation=None,expected_runtime=None):
    from .own_connection_broker import read_runtime,SOCKET,RUNTIME,socket_address,_StartupStream,_ready_transport
    from .own_bootstrap_ipc import peer,send,receive,socket_pin
    from .own_bootstrap_security import path_check
    from .draft_group_tools import validate
    if name==PRIVATE_METHOD:
        need(type(arguments)is dict and not arguments,'GROUP_FIXED_BOOTSTRAP_ARGUMENTS')
        from .group_host_external_loader import check_private_preparation
        need(absolute_deadline==check_private_preparation(private_invocation,policy,consume=True),'GROUP_DEADLINE')
    else:
        need(private_invocation is None,'GROUP_PRIVATE_INVOCATION_SCOPE')
        need(name in NETWORK_NAMES,'GROUP_METHOD_UNKNOWN')
        validate(name,arguments)
        need(arguments['connection_id']==policy.data['connection_id'],'GROUP_CONNECTION_SCOPE')
    from .group_host_external_loader import process_loader_anchor,check_process_loader_anchor
    anchor=process_loader_anchor()
    runtime,pin=read_runtime(policy)
    endpoint=policy.root/SOCKET;endpoint_pin=socket_pin(endpoint)
    need(expected_runtime is not None and (runtime,pin,endpoint_pin)==expected_runtime,'GROUP_RUNTIME_CHANGED')
    with _ready_transport(policy,runtime,pin,endpoint_pin,absolute_deadline,absolute_stream=True) as (client,stream):
        need(_MONOTONIC()<absolute_deadline,'GROUP_DEADLINE')
        send(stream,{'runtime':runtime,'sequence':1,'name':name,'arguments':arguments,'group_absolute_deadline':absolute_deadline,'group_loader_anchor':anchor})
        response=receive(stream);policy.check();check_process_loader_anchor(anchor)
        if name==PRIVATE_METHOD:check_private_preparation(private_invocation,policy)
        actual,actual_pin=read_runtime(policy)
        need(actual==runtime and actual_pin==pin and socket_pin(endpoint)==endpoint_pin,'GROUP_RUNTIME_CHANGED')
        need(type(response) is dict and response.get('sequence')==1,'GROUP_RESULT_UNKNOWN')
        if 'error' in response:hold(response['error'])
        need(set(response)=={'sequence','result'} and type(response['result']) is dict,'GROUP_RESULT_UNKNOWN')
        return response['result']


def prepare_group_existing(policy,invocation):
    """Trusted fixed F technical mode; no cold start or public Parent issuer."""
    from .group_host_external_loader import check_private_preparation
    from .own_connection_broker import read_runtime,_startup_has_owner,_startup_gate
    from .group_host_jobs import publish_fixed_host_job
    deadline=check_private_preparation(invocation,policy)
    with _startup_gate(policy,deadline):
        need(_startup_has_owner(policy),'GROUP_PRIVATE_EXISTING_OWNER_REQUIRED')
        # Do not clear stale endpoints, ensure_started, spawn H or displace an
        # owner. An uncertain request remains in the original read/Parent ledger.
        runtime,pin=read_runtime(policy)
        from .own_bootstrap_ipc import socket_pin
        from .own_connection_broker import SOCKET
        endpoint_pin=socket_pin(policy.root/SOCKET)
        check_private_preparation(invocation,policy)
        publish_fixed_host_job(policy)
        need(read_runtime(policy)==(runtime,pin) and socket_pin(policy.root/SOCKET)==endpoint_pin,'GROUP_RUNTIME_CHANGED')
    return _call_group_existing(policy,PRIVATE_METHOD,{},deadline,private_invocation=invocation,expected_runtime=(runtime,pin,endpoint_pin))
