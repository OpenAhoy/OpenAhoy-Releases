"""Closed single-Case model tools. Registration and grants are host-only."""
from copy import deepcopy
from .contracts import WCEError
from .own_connection_policy import resolve,registry_path
from .prepared_contracts import ID,string,strict_validate
from .tools import schema

PREFIX='own.drafts.revisions.'
HASH=string(64,r'^[a-f0-9]{64}$')
ARTIFACT=string(82,r'^revision-artifact-[a-f0-9]{64}$')
SPECS={PREFIX+'prepare':schema({'connection_id':ID,'original_save_key':ID,'revision_artifact_handle':ARTIFACT})}
SPECS.update({PREFIX+name:schema({'connection_id':ID,'revision_id':HASH})
    for name in ('execute','status','readback')})
NETWORK=frozenset(set(SPECS)-{PREFIX+'status'})


def validate(name,args):
    if name not in SPECS:raise WCEError('TOOL_NOT_IMPLEMENTED')
    strict_validate(args,SPECS[name])


def descriptors():
    return [{'name':name,'inputSchema':deepcopy(spec),'description':
        'Correct only a host-registered original single draft. Legacy cases remain content-only with no upload. '
        'A separately qualified exact current correction may change only its registered title, digest and content, '
        'and may upload at most its one registered new body image after the original target is held. '
        'Prepare reads the baseline and writes local reservation state only; execute may upload that one image and update once; status is local; readback shares the same read budget. '
        'No new draft, deletion or publication is granted by these tools.'}
        for name,spec in SPECS.items()]


def call(name,args,registry=None,launcher=None):
    validate(name,args)
    policy=resolve(args['connection_id'],registry_path() if registry is None else registry,
        active=name!=PREFIX+'status')
    from .draft_revision_runtime import local_status
    # Prove an existing Case or a host-persisted exact pending proposal before
    # broker startup/token access. No model-created proposal is accepted.
    try:status=local_status(policy,args)
    except WCEError as error:
        if error.code!='DRAFT_REVISION_REGISTERED_CASE_REQUIRED':raise
        from .draft_revision_pending_runtime import selected,local_status as pending_status
        selected(policy,args,registry)
        if name==PREFIX+'status':return pending_status(policy,args,registry)
    else:
        if name==PREFIX+'status':return status
    from .own_connection_broker import ensure_started,call as broker_call
    from pathlib import Path
    launcher=launcher or Path(__file__).resolve().parents[1]/'scripts'/'wce_connection.py'
    ensure_started(policy,launcher)
    return broker_call(policy,name,args)
