"""Fixed Group business entry points. Public local calls never bootstrap."""
from .contracts import WCEError
from .draft_group_tools import PREFIX, validate
from .own_connection_policy import ConnectionPolicy


def fixed_host_job(policy):
    # The compiled host loader owns selectors and exact external review pins.
    # Neither an MCP argument nor this module can supply a path or a grant.
    from .group_host_jobs import load_fixed_host_pins
    return load_fixed_host_pins(policy)


def call_local(policy,name,arguments):
    validate(name,arguments)
    if (type(policy) is not ConnectionPolicy
            or arguments['connection_id']!=policy.data['connection_id']):
        raise WCEError('GROUP_LOCAL_IDENTITY_HOLD')
    from .draft_group_local_reader import read_plan, read_status
    if name==PREFIX+'status':
        return read_status(policy,policy.actor,arguments['operation_id'])
    if name==PREFIX+'plan':
        return read_plan(policy,policy.actor,arguments['batch_handle'],arguments['request_key'])
    raise WCEError('GROUP_NETWORK_ENTRY_REQUIRED')


def require_registered_operation_local(policy,name,arguments):
    """Public network calls cannot create the parent they are missing."""
    from .draft_group_tools import NETWORK
    validate(name,arguments)
    if name not in NETWORK:raise WCEError('GROUP_NETWORK_ENTRY_REQUIRED')
    observed=call_local(policy,PREFIX+'status',{
        'connection_id':arguments['connection_id'],'operation_id':arguments['operation_id']})
    if (observed['lookup']!='FOUND' or observed.get('parent_registration')!='REGISTERED_HISTORICAL'):
        raise WCEError('GROUP_PARENT_REQUIRED')
    from .draft_group_first_control import require_bound_operation_local
    require_bound_operation_local(policy,arguments['operation_id'])
    return observed


def call_in_entry(host,name,arguments,deadline,cancel_guard):
    """Fixed cold/warm dispatcher; caller JSON cannot select its bootstrap."""
    from .draft_group_host_review import GroupRuntimeHost
    from .draft_group_runtime_host import GroupExecutionGate
    from .draft_group_host_bootstrap import PRIVATE_METHOD
    if (type(host) is not GroupRuntimeHost or type(host.entry) is not GroupExecutionGate
            or type(deadline) not in (int,float) or deadline!=host.entry.deadline
            or cancel_guard is not host.entry.cancel):
        raise WCEError('GROUP_ACTUAL_ENTRY_REQUIRED')
    host.entry.full_guard()
    if name==PRIVATE_METHOD:
        if type(arguments) is not dict or arguments:
            raise WCEError('GROUP_FIXED_BOOTSTRAP_ARGUMENTS')
        from .draft_group_batch_bootstrap import prepare_current_batch
        from .draft_group_host_operator import is_operator
        if is_operator(host):
            from .draft_group_first_control import begin_first_preparation_in_host
            begin_first_preparation_in_host(host)
        return prepare_current_batch(host)
    validate(name,arguments)
    if arguments['connection_id']!=host.entry.policy.data['connection_id']:
        raise WCEError('GROUP_LOCAL_IDENTITY_HOLD')
    if name in (PREFIX+'plan',PREFIX+'status'):
        return call_local(host.entry.policy,name,arguments)
    from .draft_group_registered_execution import run_registered_child
    if name==PREFIX+'execute':
        return run_registered_child(host,arguments['operation_id'])
    if name==PREFIX+'readback':
        if arguments['phase'] not in ('NEW','FINAL'):
            raise WCEError('GROUP_READ_PHASE_NOT_APPLICABLE')
        return run_registered_child(host,arguments['operation_id'],readback_phase=arguments['phase'])
    raise WCEError('TOOL_NOT_IMPLEMENTED')
