"""Exactly one fixed, reviewed Group bootstrap process; no generic retry."""
import os
from pathlib import Path
import socket
import subprocess
import sys
import time
from .draft_group_runtime_host import need,PinnedFile,hold
from .draft_group_pin_resources import close_all
from .contracts import WCEError


_SPAWN_RECEIPTS={}

def start_fixed_child_once(policy,pins,deadline,launcher,*,name,arguments):
    from .draft_group_child_control import make_public_start,validate_public_result
    from .own_connection_policy import ConnectionPolicy
    need(type(policy) is ConnectionPolicy,'GROUP_FIXED_POLICY_REQUIRED')
    request=make_public_start(policy.data['connection_id'],pins.configuration_sha,name,arguments,deadline)
    from .own_connection_broker import _StartupStream,_startup_remaining
    # Preserve the original 60-second startup cap, but apply it once to the
    # complete frame rather than granting another timeout for every fragment.
    startup_deadline=min(deadline,time.monotonic()+60)
    _startup_remaining(startup_deadline)
    key=(str(policy.path),pins.configuration_sha)
    need(key not in _SPAWN_RECEIPTS,'GROUP_STARTUP_RESULT_UNKNOWN')
    from .group_host_external_loader import process_loader_anchor
    loader_anchor=process_loader_anchor()
    # The caller's generic launcher is deliberately not executed. The compiled
    # armed helper is the only reviewed child program and carries fixed account
    # selection. It receives no free path, content, authority or budget argument.
    pin=PinnedFile(pins.armed_path,pins.armed_sha,2*1024*1024)
    try:
        parent,child=socket.socketpair(socket.AF_UNIX,socket.SOCK_STREAM)
        try:
            parent.settimeout(_startup_remaining(startup_deadline))
            from .own_bootstrap_ipc import peer,send,receive
            pid,uid=peer(parent)
            need(uid==os.getuid(),'GROUP_STARTUP_PEER')
            _startup_remaining(startup_deadline)
            process=subprocess.Popen([sys.executable,'-I','-B',str(pins.armed_path)],cwd=str(pins.armed_path.parent),
                env={'PATH':'/usr/bin:/bin','PYTHONDONTWRITEBYTECODE':'1','WCE_GROUP_STARTUP_FD':str(child.fileno())},
                pass_fds=(child.fileno(),),stdin=subprocess.DEVNULL,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,
                close_fds=True,start_new_session=True)
            _SPAWN_RECEIPTS[key]={'pid':process.pid,'deadline':deadline,'state':'SPAWNED_UNDETERMINED','process':process,'helper_sha':pins.armed_sha}
            child.close()
            need(process_loader_anchor()==loader_anchor,'GROUP_FIXED_CHILD_CATALOG_CHANGED')
            pin.check()
            stream=_StartupStream(parent,startup_deadline)
            from .group_host_jobs import wrap_child_start_request
            send(stream,wrap_child_start_request(request))
            result=receive(stream)
            value,runtime=validate_public_result(result,request)
            from .own_connection_broker import read_runtime
            actual,_=read_runtime(policy)
            need(actual==runtime and actual['pid']==process.pid,'GROUP_STARTUP_RESULT_UNKNOWN')
            _startup_remaining(startup_deadline)
            _SPAWN_RECEIPTS[key]['state']='COMPLETE_SERVICE_RETURNED'
            # An unknown/timeout does not terminate foreign workers, retry,
            # respawn, delete endpoints or route through ordinary startup.
        finally:
            close_all((parent.close,child.close),sys.exc_info()[1])
    except WCEError as error:
        if error.code=='CONNECTION_START_PENDING' and key in _SPAWN_RECEIPTS:
            # Once Popen returned, a technical timeout cannot be presented as
            # a known pre-start wait. Keep the original receipt unresolved.
            raise WCEError('GROUP_STARTUP_RESULT_UNKNOWN') from None
        raise
    finally:close_all((pin.close,),sys.exc_info()[1])
    return value
