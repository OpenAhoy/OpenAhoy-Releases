"""Host-owned official transport for an already registered exact revision Case.

This is separate from ordinary draft delegation and adds no global API grant.
All credentials remain inside the existing account TokenCache. The provider
requires the original consumed, same-stack journal admission on every HTTP call.
It does not register a Case, choose endpoints, retry or recover a write.
"""
from hashlib import sha256
import math
import sqlite3
import time

from .contracts import Secret,WCEError
from .http_transport import HTTPSender,HTTPRequest
from .own_connection_token import TokenCache
from .service import digest


def hold():raise WCEError('DRAFT_REVISION_OFFICIAL_ADMISSION_HOLD')


class OfficialRevisionProvider:
    synthetic=False
    def __init__(self,account_service,store,context,deadline):
        from .own_connection_broker import AccountService
        from .own_connection_policy import ConnectionPolicy
        from .own_connection_workflow import PersistentWorkflow
        from .draft_revision_store import RevisionStore
        from .draft_revision_service import RevisionContext
        if (type(account_service) is not AccountService or type(store) is not RevisionStore
                or type(context) is not RevisionContext or type(deadline) not in (int,float)
                or not math.isfinite(deadline) or not time.monotonic()<deadline<=time.monotonic()+300
                or type(account_service.policy) is not ConnectionPolicy
                or type(account_service.tokens) is not TokenCache
                or account_service.tokens.policy is not account_service.policy
                or type(account_service.workflow) is not PersistentWorkflow
                or account_service.workflow.policy is not account_service.policy
                or account_service.workflow.token_cache is not account_service.tokens
                or type(account_service.workflow.sender) is not HTTPSender
                or account_service.workflow.sender.enabled is not True):hold()
        self.service,self.store,self.context=account_service,store,context
        self.deadline=deadline;self.cached=None;self.used={};self.issued={}

    def matches(self,store,context):
        return self.store is store and self.context is context

    def _checked_current(self,store,context):
        """Exact implementation result, used immediately by this service only."""
        from types import MethodType
        if (type(self) is not OfficialRevisionProvider
                or not OfficialRevisionProvider.matches(self,store,context)):hold()
        for name in ('current','_current_input','matches'):
            method=getattr(self,name,None)
            if (type(method) is not MethodType or method.__self__ is not self
                    or method.__func__ is not getattr(OfficialRevisionProvider,name)):hold()
        return OfficialRevisionProvider.current(self)

    def _current_input(self):
        from dataclasses import asdict
        from .draft_revision_input import RevisionInputAdapter
        current=self.context.current;initial=self.context.initial_matches
        adapter=getattr(current,'__self__',None)
        if (type(adapter) is not RevisionInputAdapter or adapter.service is not self.service
                or getattr(current,'__func__',None) is not RevisionInputAdapter.current
                or getattr(initial,'__self__',None) is not adapter
                or getattr(initial,'__func__',None) is not RevisionInputAdapter.matches_snapshot
                or adapter.expected_capsule_sha!=self.context.case['input_sha']
                or adapter.expected_source_sha!=self.context.case['source_sha']):hold()
        observed=adapter.inspect()
        with self.store.connection() as db:
            state=self.store._state(db,self.context.case['id']);record=state['registration']
            if (record['input']!=observed.capsule or record['original']!=asdict(observed.original)
                    or record['derived']!=observed.derived):hold()
        return observed.capsule

    def current(self):
        from .own_auth import OwnProfile
        from .draft_revision_store import OFFICIAL_PROVIDER
        from .draft_revision_gate import RevisionExecutionGate
        gate=self.context.execution_lock
        if type(gate) is not RevisionExecutionGate or gate.service is not self.service or not gate.held():hold()
        self.service.guard(self.deadline)
        profile=self.service.profile()
        if (type(profile) is not OwnProfile or profile.source_kind!='OPERATOR_ATTESTED'
                or digest(profile.binding())!=self.context.case['binding']
                or self.store.binding!=self.context.case['binding']
                or self.store.account!=self.service.policy.root
                or digest(self.context.reference)!=self.context.case['target']
                or self.context.case.get('provider_profile')!=OFFICIAL_PROVIDER):hold()
        current=self._current_input()
        if digest(current)!=self.context.case['input_sha']:hold()
        with self.store.connection() as db:
            state=self.store._state(db,self.context.case['id'])
            if state['case']!=self.context.case:hold()
        if self.cached is not None and not self.service.tokens.valid(self.cached):hold()
        self.service.guard(self.deadline)
        # Both values were freshly validated above. No authority is cached;
        # the caller consumes them immediately without a second earlier scan.
        return current,state

    def token(self):
        self.current()
        cached=self.service.tokens.get(guard=self.current)
        if type(cached.token) is not Secret or not self.service.tokens.valid(cached):hold()
        if self.cached is not None and cached is not self.cached:hold()
        self.cached=cached;self.current()
        return cached.token

    def _admitted(self,admission,kind):
        from .draft_revision_store import Admission
        if (type(admission) is not Admission or admission.kind!=kind
                or admission.case_id!=self.context.case['id']):hold()
        key=(admission.case_id,kind,admission.ordinal)
        if self.store._inflight.get(key) is not admission or key in self.used:hold()
        self.current()
        with self.store.connection() as db:
            state=self.store._state(db,admission.case_id);row=state['revision']
            if row['id']!=admission.revision_id or row['reads']!=admission.ordinal:hold()
            if kind=='GET':
                read=state['read_claims'][admission.ordinal-1]
                if read['state']!='ALLOCATED' or read['claim_sha']!=admission.proof_sha:hold()
            elif row['writes']!=1 or row['claim_sha']!=admission.proof_sha or row['state']!='CLAIMED':hold()
        return key,state

    def _send(self,key,admission,request):
        if type(request) is not HTTPRequest or request.test_only:hold()
        self.current()
        if self.cached is None or not self.service.tokens.valid(self.cached):hold()
        # Token acquisition/current-source checks can outlive another read's
        # allocation. Recheck the exact latest ordinal at the final send seam.
        _,state=self._admitted(admission,admission.kind)
        if admission.kind=='GET':
            from .own_wire import encode_draft
            expected=encode_draft('get',{'media_id':self.context.reference},self.cached.token)
        else:
            from .draft_revision_wire import update_payload,encode_update
            # Reconstruct the only permitted body from the actual latest
            # PRE_SEND snapshot and immutable Case input, including metadata.
            snapshot=self.store._read_snapshot(state,admission.ordinal)
            value=self._current_input()
            expected=encode_update(update_payload(snapshot,value['changes'],synthetic=False),
                self.cached.token,synthetic=False)
            if sha256(expected.body).hexdigest()!=state['revision']['request_sha']:hold()
        if request!=expected:hold()
        if admission.kind=='UPDATE':
            from .own_history_source import owned_connection
            from .draft_group_store import check_account_writer
            path=self.service.policy.root/'state.sqlite3'
            with owned_connection(path,readonly=True,timeout=5) as db, _history_scope(self.service.policy,db) as history_locators:
                db.row_factory=sqlite3.Row
                db.execute('BEGIN')
                try:check_account_writer(db, history_locators=history_locators)
                finally:db.rollback()
        # Reconstruction and final journal validation can take time. Only now
        # recheck current source/policy/gate/token and compute the live timeout.
        self.current()
        if not self.service.tokens.valid(self.cached):hold()
        remaining=min(self.deadline-time.monotonic(),
            self.cached.wall_deadline-self.service.tokens.wall(),
            self.cached.continuous_deadline-self.service.tokens.continuous())
        if not 0<remaining:hold()
        # Consume this provider stack before the HTTP call. Failure never makes
        # the same read/write admission reusable, including callback exceptions.
        if key in self.used or self.store._inflight.get(key) is not admission:hold()
        self.used[key]=admission
        response=self.service.workflow.sender.send(request,min(30,remaining))
        from .draft_revision_transport import _capture
        return _capture(self,admission,request,response)

    def read_admitted(self,admission):
        from .own_wire import encode_draft
        key,_=self._admitted(admission,'GET');secret=self.token()
        request=encode_draft('get',{'media_id':self.context.reference},secret)
        capture=self._send(key,admission,request)
        return capture.response,secret,capture

    def send_admitted(self,request,admission):
        from .publication_contract import strict_json
        from .draft_revision_wire import encode_update
        key,state=self._admitted(admission,'UPDATE')
        if self.cached is None:hold()
        payload=strict_json(request.body,maximum=2*1024*1024) if type(request) is HTTPRequest else None
        if (type(payload) is not dict or payload.get('media_id')!=self.context.reference
                or sha256(request.body).hexdigest()!=state['revision']['request_sha']):hold()
        # Re-encode the exact original request with the same internal Secret.
        # No caller-provided path, headers, token or endpoint is authoritative.
        encoded=encode_update(payload,self.cached.token,synthetic=False)
        if request!=encoded:hold()
        return self._send(key,admission,encoded)


from .draft_group_history_context import locator_scope as _history_scope
