"""Closed model entry points. No grant, raw parent key, approval or force field."""
from copy import deepcopy
from .contracts import WCEError
from .own_connection_policy import resolve,registry_path
from .prepared_contracts import ID,string,strict_validate
from .tools import schema

HANDLE=string(78,r'^restore-grant-[a-f0-9]{64}$')
SPECS={name:schema({'connection_id':ID,'restore_handle':HANDLE}) for name in (
    'own.drafts.restore','own.drafts.restore_status','own.drafts.restore_readback','own.drafts.restore_reconcile')}
SPECS['own.drafts.restores']=schema({'connection_id':ID})


def descriptors():
    return [{'name':name,'inputSchema':deepcopy(spec),'description':
        ('Use only a trusted human-reviewed known-success restoration handle. '
         'No old UNKNOWN resend, upload, publication or alias bypass. '
         'Status is local; restore saves once and readback reads the new reference.')}
        for name,spec in SPECS.items()]


def call(name,args,registry=None):
    if name not in SPECS:raise WCEError('TOOL_NOT_IMPLEMENTED')
    strict_validate(args,SPECS[name])
    registry=registry_path() if registry is None else registry
    policy=resolve(args['connection_id'],registry,active=(name not in {'own.drafts.restore_status','own.drafts.restores'}))
    from .own_draft_restore_service import local_status,local_list,DraftRestoreService
    if name=='own.drafts.restores':return local_list(policy,registry)
    status=local_status(policy,args['restore_handle'])
    if name=='own.drafts.restore_status':return status
    if status['state']=='NOT_PREPARED':raise WCEError('DRAFT_RESTORE_GRANT_REQUIRED')
    if name=='own.drafts.restore' and status['state']!='PREPARED_NOT_SENT':return status
    from .own_connection_broker import AccountService
    service=DraftRestoreService(AccountService(policy),registry)
    if name=='own.drafts.restore_reconcile':return service.reconcile(args['restore_handle'])
    return service.execute(args['restore_handle']) if name=='own.drafts.restore' else service.readback(args['restore_handle'])
