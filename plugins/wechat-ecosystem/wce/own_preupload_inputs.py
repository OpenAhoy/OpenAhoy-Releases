"""Fixed original request scope and read-only slot qualification.

The scope file is a proposal, never a QUALIFIED observation or new budget.
Every first request is requalified against the actual service's Owned/H state.
"""
from dataclasses import dataclass
from hashlib import sha256
import inspect
import json
import os
from pathlib import Path
import threading
import sys
import time

from .contracts import WCEError
from .service import canonical, digest
from .own_selected_history import readonly_prepared_history
from .own_preupload_journal import ProjectOnceJournal
from .draft_group_selected_source_codec import decode_manifest, ORIGINAL_QUEUE_SHA256

KEY_TABLE_SHA = '77ebbe33e4cd32c0928099e4a328820a291c03e5f3fbb6df8675b7e4016a0a21'
JOURNAL_SHA = 'e98ce6340727d5f1f05e4b7d418dfe14912a5a24796396372377f27ccea458f6'
_FIXED_PHASE_SHAS = {
    'v8_driver':'42fb16683c94e9c6bb0eefbc1c6368e59bb02b5789d8e50a10298be668438ee2',
    'phase_runner':'818e62af466903f4fb085befddb8a72a8a99d5dec30129be04bce0346d679dcc',
    'phase_claim':'9c9f9b3f1a275783c94ec48477d72afaff836768e04caed4a8135d5ae6dce4b1',
    'phase_outcome':'e12f07ab6825c333fa24241a2d050be5ce287300e28a8ec98895d732c755f522',
    'prepare_completion':'4dc7ebb48f6bd32ec99a4b2dfd83bfbe6aaed006bee66902e6c23bc7fde33798'}
_LIMITS = {'max_original_upload_keys':109,'max_technical_children':109,
    'maximum_execution_seconds':300,'max_rpc_sequence':512,
    'stop_on_any_error_or_unknown':True,'automatic_replay':False}
_ORIGINAL_KEYS = frozenset(('queue','key_table','flat_manifest','v8_driver','v8_bindings',
    'journal_bindings','v8_adoption','phase_runner','phase_claim','phase_outcome',
    'prepare_completion','prepared_index','role_map','title_adoption','title_mapping','original_out','member_count',
    'role_count','effective_phase_state','journal_binding_sha256'))


def need(value):
    if value is not True:raise WCEError('PREUPLOAD_ORIGINAL_SCOPE_HOLD')


def _read(resources, ref):
    raw=resources.acquire_evidence(ref).raw
    from .own_preupload_qa import _pairs
    try:return json.loads(raw.decode('utf-8'),object_pairs_hook=_pairs,
                          parse_constant=lambda _:need(False))
    except (ValueError,UnicodeError,RecursionError):
        raise WCEError('PREUPLOAD_ORIGINAL_SCOPE_HOLD') from None


def _original_completion(resources, original, loaded, completion_ref):
    """The fixed original synchronous runner's actual wait-before-outcome graph.

    No generic COMPLETED import or process-name/old-PID guess. The new flock
    does not retroactively control the original driver; it is never restarted.
    """
    completion=_read(resources,completion_ref)
    need(set(completion)=={'schema','profile','authority','phase_runner_ref','driver_ref',
        'phase_claim_ref','phase_outcome_ref','original_out','journal_binding_sha256',
        'original_phase_outcome_sha256','owned_execution_terminal','original_phase_replay','completion_basis'}
        and type(completion['schema']) is int and completion['schema']==1
        and completion['profile']=='OPERATOR_OWNED_ORIGINAL_PHASE_COMPLETION_V1'
        and completion['authority'] is False
        and completion['owned_execution_terminal']=='COMPLETED_EXIT_2'
        and completion['original_phase_replay']=='FORBIDDEN'
        and completion['completion_basis']=='FIXED_SYNCHRONOUS_RUNNER_WAIT_BEFORE_OUTCOME_V1'
        and completion['journal_binding_sha256']==JOURNAL_SHA
        and completion['original_out']==original['original_out']
        and completion['original_phase_outcome_sha256']==original['phase_outcome']['sha256'])
    for name,checksum in _FIXED_PHASE_SHAS.items():
        need(original[name]['sha256']==checksum)
        resources.acquire_evidence(original[name])
    for name,origin in (('phase_runner_ref','phase_runner'),('driver_ref','v8_driver'),
                        ('phase_claim_ref','phase_claim'),('phase_outcome_ref','phase_outcome')):
        need(completion[name]==original[origin])
    here=Path(original['v8_driver']['path']).parent
    need(Path(original['phase_runner']['path'])==here/'upload_after_prepared.py'
         and Path(original['phase_claim']['path'])==here/'upload-phase-reserved.json'
         and Path(original['phase_outcome']['path'])==here/'upload-phase-actual.json'
         and Path(original['prepare_completion']['path'])==here/'remaining-prepare-actual.json'
         and Path(original['original_out'])==here.parent/'ordinary28-execution-v6/output'
         and Path(original['journal_bindings']['path'])==Path(original['original_out']).parent/'bindings.json')
    claim,outcome,prepared=(loaded[name] for name in ('phase_claim','phase_outcome','prepare_completion'))
    need(set(claim)=={'state','driver_sha256','prepare_result_sha256','max_original_upload_keys',
        'save','publish','unknown_replay'} and claim['state']=='FIXED109_UPLOAD_PHASE_RESERVED'
        and type(claim['max_original_upload_keys']) is int and claim['max_original_upload_keys']==109
        and all(claim[key] is False for key in ('save','publish','unknown_replay'))
        and claim['driver_sha256']==outcome['driver_sha256']==_FIXED_PHASE_SHAS['v8_driver']
        and claim['prepare_result_sha256']==_FIXED_PHASE_SHAS['prepare_completion']
        and type(outcome['returncode']) is int and outcome['returncode']==2
        and outcome['stderr']=='' and json.loads(outcome['stdout'])=={
            'code':'OWN_HISTORY_LOCATOR_HOLD','exception':'RuntimeError','state':'ORDINARY28_HOLD'}
        and prepared['state']=='REMAINING_LOCAL_PREPARE_COMPLETED'
        and type(prepared['prepared_count']) is int and prepared['prepared_count']==28
        and prepared['no_upload_save_publish'] is True)
    resources.guard()


@dataclass(frozen=True)
class SlotObservation:
    """Detached result only. Cannot substitute for the next live qualification."""
    member_id: str
    slot: str
    request_key: str
    target: str
    decision: str
    state: str | None
    attempt_id: str | None = None
    proof_facts_sha256: str | None = None
    authority: bool = False


class PreuploadInputs:
    def __init__(self,*args,**kwargs):
        raise WCEError('PREUPLOAD_INPUTS_ISSUER_REQUIRED')

    @classmethod
    def from_fixed_entry(cls, entry, policy):
        from . import own_preupload_entry as entries
        from .own_preupload_domain import PreuploadSessionService
        need(cls is PreuploadInputs
             and inspect.currentframe().f_back.f_code is PreuploadSessionService.__init__.__code__)
        view=entries.require_fixed_entry(entry)
        record=entries._record(entry)
        need(record.consumed and record.core is None and record.service is not None
             and policy.path==view.policy_path)
        resources=record.resources
        binding=resources.values()
        projection=tuple(tuple(row) for row in binding['member_projection'])
        selection,_,_=decode_manifest(view.selection_raw,expected_member_projection=projection)
        from .own_preupload_sources import _json
        request=_json(view.resume_raw)
        # A fixed request is intentionally distinct from the later read-only
        # qualification observation; it never asserts SDK eligibility at boot.
        need(set(request)=={'schema','profile','authority','state','new_business_budget',
            'resume_id','child_ordinal','previous_child_terminal_ref','original','partition',
            'limits','owner_completion_ref','artifact_roots'})
        need(type(request['schema']) is int and request['schema']==1
             and request['profile']=='PREUPLOAD_ORIGINAL_PHASE_SCOPE_V1'
             and request['authority'] is False and request['state']=='FIXED_SCOPE_ONLY_NOT_QUALIFIED'
             and type(request['new_business_budget']) is int and request['new_business_budget']==0)
        need(request['limits']==_LIMITS
             and all(type(request['limits'][key]) is type(value) for key,value in _LIMITS.items()))
        original=request['original'];need(type(original) is dict and set(original)==_ORIGINAL_KEYS)
        need(original['queue']['sha256']==ORIGINAL_QUEUE_SHA256
             and original['key_table']['sha256']==KEY_TABLE_SHA
             and original['journal_binding_sha256']==JOURNAL_SHA
             and original['journal_bindings']['sha256']==JOURNAL_SHA
             and original['effective_phase_state']=='STOPPED'
             and type(original['member_count']) is int and original['member_count']==28
             and type(original['role_count']) is int and original['role_count']==109)
        raw_only={'v8_driver','phase_runner'}
        loaded={}
        for name,ref in original.items():
            if type(ref) is not dict:continue
            resources.acquire_evidence(ref)
            if name not in raw_only:loaded[name]=_read(resources,ref)
        need(loaded['phase_claim']['state']=='FIXED109_UPLOAD_PHASE_RESERVED'
             and loaded['phase_claim']['max_original_upload_keys']==109
             and loaded['phase_claim']['unknown_replay'] is False
             and loaded['phase_outcome']['returncode']==2)
        role_map=loaded['role_map']
        need(role_map['profile']=='ORIGINAL109_PROJECT_ROLE_MAP_NOT_QUALIFICATION'
             and role_map['authority'] is False and role_map['SDK_queried'] is False
             and len(role_map['rows'])==109 and role_map['original_out']==original['original_out'])
        # A trusted original-owner completion observation is a required source,
        # not a PID guess or the phase outcome alone. The actual observation
        # contract is checked independently before this input owner is armed.
        _original_completion(resources,original,loaded,request['owner_completion_ref'])
        if request['previous_child_terminal_ref'] is not None:
            resources.acquire_evidence(request['previous_child_terminal_ref'])
        partition=request['partition']
        need(type(partition) is dict and set(partition)=={'connection_id','member_ids','exact_scope_policy'}
             and partition['connection_id']==policy.data['connection_id']
             and partition['exact_scope_policy']=='EXACT_ORIGINAL_CONNECTION_MEMBERS')
        from .own_selected_history import _policy_binding
        current_binding=digest(_policy_binding(policy,'OPERATOR_ATTESTED'))
        members=[member for member in selection['members'] if member['binding_sha256']==current_binding]
        need([member['article_id'] for member in members]==partition['member_ids'] and members)
        keys=loaded['key_table']['members']
        need(len(keys)==28 and len({row['member_id'] for row in keys})==28
             and {row['member_id'] for row in keys}=={member['article_id'] for member in selection['members']})
        by_key={row['member_id']:(index+1,row) for index,row in enumerate(keys)}
        for row in role_map['rows']:
            ordinal,key=by_key[row['member_id']]
            short=row['slot'].split('--',1)[1]
            need(row['member_ordinal']==ordinal and row['prepare_request_key']==key['prepare']
                 and row['request_key']==key['uploads'][short]
                 and row['slot']==key['document_article_id']+'--'+short
                 and row['original_tag']==f'm{ordinal:02d}-execute-{short}')
        role_rows=[row for row in role_map['rows'] if row['connection_id']==policy.data['connection_id']]
        need(set(row['member_id'] for row in role_rows)==set(partition['member_ids'])
             and len({(row['member_id'],row['slot']) for row in role_rows})==len(role_rows))
        obj=object.__new__(cls)
        obj.entry,obj.policy,obj.resources=entry,policy,resources
        obj.owner=(os.getpid(),threading.get_ident())
        obj.policy_snapshot=canonical(policy.value)
        obj.members={member['article_id']:canonical(member) for member in members}
        obj.roles={(row['member_id'],row['slot']):canonical(row) for row in role_rows}
        obj.all_original_arguments={row['original_tag']:{'connection_id':row['connection_id'],
            **row['selector'],'request_key':row['request_key'],'slot':row['slot']}
            for row in role_map['rows']}
        need(len(obj.all_original_arguments)==109)
        from .own_preupload_selected_files import decode_roots
        root_raw=resources.acquire_evidence(request['artifact_roots']).raw
        obj.roots,obj.flat_root=decode_roots(root_raw,selection,loaded['journal_bindings']['flat_root'],
            expected_flat_manifest_ref=original['flat_manifest'])
        from .own_preupload_derivation import original_member_rows
        for key in ('queue','key_table','flat_manifest','title_adoption','title_mapping'):
            need({k:original[key][k] for k in ('path','sha256')}==loaded['v8_bindings'][key])
        original_rows=original_member_rows(loaded['queue'],loaded['key_table'],loaded['flat_manifest'],
            loaded['v8_bindings'],loaded['title_adoption'],loaded['title_mapping'])
        obj.original_rows={key:canonical(value) for key,value in original_rows.items()}
        obj.scratch_root=Path(original['original_out']).parent/'preupload-scratch'
        obj.selection_raw=view.selection_raw
        obj.active_files=None
        obj.derived_documents={}
        obj.derived_bytes=0
        obj.active_reservation=None
        obj.closed=False
        from .own_preupload_child_journal import TechnicalChildJournal
        obj.child_journal=TechnicalChildJournal(original['original_out'],
            ordinal=request['child_ordinal'],resume_id=request['resume_id'],
            phase_sha=original['phase_claim']['sha256'],binding_sha=resources.binding.sha)
        try:
            obj.child_journal.observe_owned_child(binding_sha=resources.binding.sha,
                parent_pid=record.observation.parent_pid,child_pid=os.getpid(),
                previous_terminal_ref=request['previous_child_terminal_ref'])
        except BaseException as error:obj.child_journal.close(original=error);raise
        obj.journal=ProjectOnceJournal(original['original_out'],journal_binding_sha256=JOURNAL_SHA,
            phase_sha256=original['phase_claim']['sha256'],resume_id=request['resume_id'],
            child_ordinal=request['child_ordinal'])
        try:obj.journal.__enter__()
        except BaseException as error:obj.child_journal.close(original=error);raise
        return obj

    def check_current(self, service):
        need(not self.closed and self.owner==(os.getpid(),threading.get_ident())
             and service.entry is self.entry and service.policy is self.policy
             and canonical(self.policy.value)==self.policy_snapshot)
        self.resources.guard();self.policy.check();self.journal.check()
        self.child_journal.check()
        if self.active_files is not None:self.active_files.check()
        from .draft_group_pin_resources import MAX_RAW_BYTES
        raw_other=(self.resources.pool.raw_bytes+self.resources.evidence_bytes+self.derived_bytes
                   +(0 if self.active_files is None else self.active_files.evidence_bytes))
        need(raw_other+self.journal.namespace_bytes<=MAX_RAW_BYTES)
        self.journal.require_namespace(self.all_original_arguments,child_ordinal=self.journal.child_ordinal,
                                      available_raw_bytes=MAX_RAW_BYTES-raw_other)
        if self.active_reservation is not None:
            reservation,tag,arguments=self.active_reservation
            self.journal.require(reservation,tag,arguments)

    def _role(self, member_id, slot):
        need((member_id,slot) in self.roles)
        return json.loads(self.roles[member_id,slot])

    def _original_predecessors_in(self,workflow,db,history,profile,manifest,fingerprint,member_id,slot):
        """Preserve the original v8 key-by-key order, beyond target-only SDK order."""
        from .draft_group_upload_proof_reads import read_original_upload_success_with_proofs_in
        receipts=[]
        slots=[asset['slot'] for asset in manifest['assets']]
        need(slot in slots)
        for asset in manifest['assets'][:slots.index(slot)]:
            prior=self._role(member_id,asset['slot'])
            operation='cover' if asset['role']=='cover' else 'body'
            target=workflow._target(profile,fingerprint,operation,asset['slot'])
            need(prior['selector']==json.loads(self.members[member_id])['selector']
                 and prior['asset']==asset and prior['operation']==operation
                 and prior['project_derived_target_sha256']==target)
            rows=list(db.execute('SELECT * FROM own_steps WHERE request_key=? OR target=? OR '
                '(manifest_digest=? AND operation=? AND slot=?)',
                (prior['request_key'],target,fingerprint,operation,asset['slot'])))
            if not rows:return 'PENDING_PREDECESSOR',receipts
            need(len(rows)==1);row=rows[0]
            need(row['request_key']==prior['request_key'] and row['target']==target
                 and row['tenant']==profile.actor.tenant_id and row['principal']==profile.actor.principal_id
                 and row['connection']==profile.connection_id and row['resource']==profile.resource_id)
            workflow._step(db,profile,row,history_locators=history)
            if row['state']!='SUCCEEDED':return 'BLOCKED_UNKNOWN_PREDECESSOR',receipts
            facts,receipt=read_original_upload_success_with_proofs_in(workflow,db,profile,row['id'],history_locators=history)
            need(facts['selector']==prior['selector'] and facts['slot']==asset['slot']
                 and facts['operation']==operation and facts['asset']==asset
                 and facts['base_step_pin']['id']==row['id'])
            receipt.collective_fence();receipts.append(receipt)
        return None,receipts

    def _observe(self, service, member_id, slot):
        self.check_current(service)
        role=self._role(member_id,slot)
        selected=json.loads(self.members[member_id])
        need(role['selector']==selected['selector']
             and role['prepare_request_key']==selected['prepare_request_key'])
        need(self.active_files is not None and self.active_files.member_raw==canonical(selected))
        workflow=service.workflow
        profile=service.core.profile()
        with readonly_prepared_history(self.policy) as reader:
            relation=reader.prepared_relation(prepare_request_key=role['prepare_request_key'],
                                             selector=role['selector'])
            db,history=reader.sql,reader.history
            predecessor_receipts=[]
            from .own_validation_scope import content_scope
            with content_scope(workflow.db,db):
                attempt_id=proof_sha=None
                manifest,fingerprint=workflow._bundle_full(db,profile,role['selector']['bundle_id'],role['selector']['version'])
                need(fingerprint==role['selector']['content_digest'])
                expected_assets=[{'asset_ref':image['asset_ref'],'role':image['role'],
                    'slot':image['slot'],'declared_type':image['artifact']['media_type'],
                    'size':image['artifact']['size'],'sha256':image['artifact']['sha256']}
                    for image in selected['images']]
                need(manifest['assets']==expected_assets)
                self._require_derivation_in(service,reader,member_id,manifest,relation)
                prior=db.execute("SELECT s.id FROM own_steps s JOIN own_articles a ON a.digest=s.manifest_digest "
                    "WHERE s.operation='add' AND a.bundle=? LIMIT 1",(manifest['bundle_id'],)).fetchone()
                need(prior is None)
                assets=[asset for asset in manifest['assets'] if asset['slot']==slot]
                need(len(assets)==1 and assets[0]==role['asset'])
                operation='cover' if assets[0]['role']=='cover' else 'body'
                need(operation==role['operation'])
                target=workflow._target(profile,fingerprint,operation,slot)
                need(target==role['project_derived_target_sha256'])
                need(db.execute('SELECT 1 FROM own_inputs WHERE request_key=? LIMIT 1',
                                (role['request_key'],)).fetchone() is None)
                # Legal pre-Group schemas have no Group namespace. If the
                # actual checked schema has one, the same original upload key
                # cannot be borrowed from another request family there.
                for table,column in (('group_batches','request_key'),
                        ('group_operations','child_key'),('group_previews','request_key')):
                    if db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name=?",(table,)).fetchone():
                        need(db.execute('SELECT 1 FROM '+table+' WHERE '+column+'=? LIMIT 1',
                                        (role['request_key'],)).fetchone() is None)
                rows=list(db.execute('SELECT * FROM own_steps WHERE request_key=? OR target=? OR '
                    '(manifest_digest=? AND operation=? AND slot=?)',
                    (role['request_key'],target,fingerprint,operation,slot)))
                if rows:
                    need(len(rows)==1)
                    row=rows[0]
                    need(row['request_key']==role['request_key'] and row['target']==target
                         and row['tenant']==profile.actor.tenant_id and row['principal']==profile.actor.principal_id
                         and row['connection']==profile.connection_id and row['resource']==profile.resource_id)
                    workflow._step(db,profile,row,history_locators=history)
                    if row['state']!='SUCCEEDED':
                        decision='BLOCKED_UNKNOWN'
                    else:
                        from .draft_group_upload_proof_reads import read_original_upload_success_with_proofs_in
                        facts,proof_receipt=read_original_upload_success_with_proofs_in(workflow,db,profile,row['id'],history_locators=history)
                        need(facts['selector']==role['selector'] and facts['slot']==slot
                             and facts['operation']==operation and facts['asset']==assets[0])
                        proof_receipt.collective_fence()
                        proof_sha=digest(facts)
                        decision='REUSE_SUCCEEDED'
                    state=row['state']
                    attempt_id=row['id']
                elif self.journal.attempted(role['original_tag']):
                    decision,state='BLOCKED_ATTEMPTED',None
                else:
                    predecessor,predecessor_receipts=self._original_predecessors_in(workflow,db,history,
                        profile,manifest,fingerprint,member_id,slot)
                    if predecessor is not None:decision=predecessor
                    else:
                        workflow._write_gate(db,profile,manifest,history_locators=history)
                        try:
                            workflow._check_upload_order_in(db,profile,manifest,fingerprint,slot,history_locators=history)
                        except WCEError as error:
                            if error.code!='OWN_STEP_ORDER':raise
                            decision='PENDING_PREDECESSOR'
                        else:
                            decision='FIRST_ELIGIBLE'
                    state=None
                for receipt in predecessor_receipts:receipt.collective_fence()
            reader.check()
            for receipt in predecessor_receipts:receipt.collective_fence()
            observation=SlotObservation(member_id,slot,role['request_key'],target,decision,state,attempt_id,proof_sha)
        # Publication of detached facts occurs only after successful H/RO close.
        self.check_current(service)
        return observation,role

    def _require_derivation_in(self, service, reader, member_id, manifest, relation):
        from .own_preupload_derivation import derive_document
        from .bounded_file import FileSource
        from .draft_group_pin_resources import MAX_RAW_BYTES
        import stat
        import tempfile
        # Immutable computation reuse only. Every request still opens/checks
        # the exact full selected bytes/pins and current C, and compares the
        # full current Owned/H document. No cached authorization or SDK state.
        cached=self.derived_documents.get(member_id)
        if cached is None:
            # Fixed original-OUT-relative decoder scratch, never RPC-selected.
            parent=self.resources.pool.directory(self.scratch_root.parent,owner=self.resources)
            try:os.mkdir(self.scratch_root.name,0o700,dir_fd=parent)
            except FileExistsError:pass
            root=self.resources.pool.directory(self.scratch_root,owner=self.resources)
            info=os.fstat(root)
            need(stat.S_ISDIR(info.st_mode) and info.st_uid==os.getuid()
                 and stat.S_IMODE(info.st_mode)==0o700)
            FileSource(self.scratch_root)
            with tempfile.TemporaryDirectory(prefix='member-',dir=self.scratch_root) as scratch:
                document=derive_document(self.active_files,json.loads(self.original_rows[member_id]),
                    scratch=scratch,guard=lambda:self.check_current(service))
            raw=canonical(document)
            need(self.resources.pool.raw_bytes+self.resources.evidence_bytes+self.derived_bytes
                 +self.active_files.evidence_bytes+self.journal.namespace_bytes+len(raw.encode())<=MAX_RAW_BYTES)
        else:
            selected_raw,code_scope,raw=cached
            need(selected_raw==self.active_files.member_raw and code_scope==self.resources.runtime.scope)
            document=json.loads(raw)
        need(canonical(document)==canonical(manifest['document'])
             and relation['selector']==json.loads(self.members[member_id])['selector']
             and relation['assets']==manifest['assets'])
        selected=json.loads(self.members[member_id]);article=document['articles'][0]
        need(relation['parameters_sha256']==selected['import_receipt_sha256']
             and digest({key:article[key] for key in ('title','author','digest','source_url',
                 'cover_dimensions','cover_info','editorial_intent') if key in article})==selected['settings_sha256'])
        # Current H and the exact selected descriptors stay live through the
        # comparison. The derived value alone carries no acceptance authority.
        reader.check();self.check_current(service)
        if cached is None:
            self.derived_documents[member_id]=(self.active_files.member_raw,self.resources.runtime.scope,raw)
            self.derived_bytes+=len(raw.encode())

    def _member_files(self, member_id):
        from .own_preupload_selected_files import SelectedMemberFiles
        need(member_id in self.members and self.active_files is None)
        return SelectedMemberFiles(self.resources,self.roots,json.loads(self.members[member_id]),
            extra_raw_bytes=self.derived_bytes+self.journal.namespace_bytes)

    def accept_selected_in_service(self, service, member_id):
        with self._member_files(member_id) as files:
            self.active_files=files
            try:return self._accept_selected(service,member_id)
            finally:self.active_files=None

    def _accept_selected(self, service, member_id):
        need(member_id in self.members)
        roles=[json.loads(raw) for (member,_),raw in self.roles.items() if member==member_id]
        need(roles)
        observation,_=self._observe(service,member_id,roles[0]['slot'])
        return {'state':'SELECTED_REQUEST_OBSERVED','authority':False,
                'member_id':member_id,'first_slot_decision':observation.decision}

    def original_slot_status(self, service, member_id, slot):
        with self._member_files(member_id) as files:
            self.active_files=files
            try:return self._original_slot_status(service,member_id,slot)
            finally:self.active_files=None

    def _original_slot_status(self, service, member_id, slot):
        observation,_=self._observe(service,member_id,slot)
        return {'state':observation.decision,'authority':False,'member_id':member_id,
                'slot':slot,'request_key':observation.request_key,'target':observation.target}

    def execute_original_slot(self, service, member_id, slot):
        with self._member_files(member_id) as files:
            self.active_files=files
            try:return self._execute_original_slot(service,member_id,slot)
            finally:self.active_files=None

    def _execute_original_slot(self, service, member_id, slot):
        # Deliberately require the real entry-scoped QA object; no JSON PASS.
        from .own_preupload_qa import require_preupload_qa
        require_preupload_qa(service.qa,entry=self.entry,service=service,
                             member_identity=member_id,slot_identity=slot)
        observation,role=self._observe(service,member_id,slot)
        need(observation.decision=='FIRST_ELIGIBLE')
        arguments={'connection_id':self.policy.data['connection_id'],**role['selector'],
                   'request_key':role['request_key'],'slot':slot}
        reservation=self.journal.reserve(role['original_tag'],arguments)
        self.active_reservation=(reservation,role['original_tag'],arguments)
        try:
            service.guard()
            require_preupload_qa(service.qa,entry=self.entry,service=service,
                                 member_identity=member_id,slot_identity=slot)
            # Do not take core.serial here: the normal core owns that lock and
            # every original authorization/admission/UNKNOWN/dispatch gate.
            value=service.core.call('own.uploads.execute',arguments,service.deadline)
            if type(value) is not dict or value.get('state')!='SUCCEEDED':
                raise WCEError('PREUPLOAD_ORIGINAL_RESULT_UNKNOWN')
            current,_=self._observe(service,member_id,slot)
            need(current.decision=='REUSE_SUCCEEDED' and current.attempt_id==value['attempt_id']
                 and current.proof_facts_sha256 is not None)
            service.guard()
            self.journal.record_known_success(reservation,role['original_tag'],arguments,value,
                proof_facts_sha256=current.proof_facts_sha256)
            return value
        finally:
            self.active_reservation=None
            self.journal.revoke(reservation,original=sys.exc_info()[1])

    def close(self, *, original=None):
        if not self.closed:
            self.closed=True
            self.derived_documents.clear();self.derived_bytes=0
            from .draft_group_pin_resources import close_all
            close_all([lambda:self.journal.close(original=original),
                       lambda:self.child_journal.close(original=original)],original)
