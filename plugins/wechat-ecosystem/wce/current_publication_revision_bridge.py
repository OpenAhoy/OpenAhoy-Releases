"""Private revision-to-current bridge, called only inside the real account gate.

No MCP constructor, new authority, token, HTTP or external path is accepted.
An existing current publication Authorization is freshly reconstructed and the
same account/reference/source READY target is uniquely resolved from its ledger.
"""
from pathlib import Path
from .contracts import WCEError

def hold():raise WCEError('CURRENT_REVISION_BRIDGE_HOLD')

class DirectPublicationBridge:
    def __init__(self,service,adapter,gate,case,deadline):
        from .own_connection_broker import AccountService
        from .draft_revision_gate import RevisionExecutionGate
        from .draft_revision_input import RevisionInputAdapter,DirectArtifactSelection,MaterializedImageSelection
        if (type(service) is not AccountService or type(adapter) is not RevisionInputAdapter
                or type(adapter.selection) not in (DirectArtifactSelection,MaterializedImageSelection) or adapter.service is not service
                or type(gate) is not RevisionExecutionGate or gate.service is not service
                or gate.deadline!=deadline or adapter.deadline!=deadline
                or type(case) is not dict):hold()
        self.service,self.adapter,self.gate,self.case,self.deadline=service,adapter,gate,case,deadline

    def _context(self):
        from .own_connection_policy import registry_path
        from .current_publication_store import Store
        from .current_publication_source import Authorization
        from .draft_revision_scan import for_adapter
        from .publication_contract import binding
        from .service import digest
        if self.gate.held() is not True:hold()
        service=self.service;policy=service.policy;scope=binding(policy.data)
        def guard():
            service.guard(self.deadline)
            if self.gate.held() is not True or binding(policy.data)!=scope:hold()
            return True
        registry=Path(policy.value.get('registry_path') or registry_path())
        scan=for_adapter(self.adapter)
        guard();store=Store(policy,registry,guard=guard)
        authority=Authorization(policy,registry,guard,self.deadline,native_guard=scan)
        from .draft_revision_publication_window import require_authorization_window
        require_authorization_window(self.adapter,authority)
        value=store.read();candidates=[]
        for handle,row in value['targets'].items():
            if (row.get('batch_source_sha')==authority.source_sha
                    and digest(row.get('reference'))==self.case['target']
                    and 'revision_successor_of' not in row):candidates.append(handle)
        if len(candidates)!=1:hold()
        handle=candidates[0];guard();return store,authority,guard,handle

    def reserve(self):
        from .current_publication_revision_reservation import reserve
        store,authority,guard,handle=self._context()
        return reserve(store,handle,self.case['id'],self.gate,authority,guard)

    def complete(self):
        from .current_publication_revision_successor import stage,activate
        store,authority,guard,handle=self._context()
        stage(store,handle,self.case['id'],self.gate,authority,guard)
        return activate(store,handle,self.gate,authority,guard)
