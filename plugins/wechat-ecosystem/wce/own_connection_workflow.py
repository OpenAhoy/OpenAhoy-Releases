"""Draft requests under a separate persistent, human-enabled delegation.

Old operator evidence is neither copied nor renewed. Platform permission remains
an observation from the actual request, distinct from this local delegation.
"""
from .contracts import WCEError
from contextlib import contextmanager
import os
import threading
import time
from .http_transport import HTTPSender
from .own_auth import APIS, READ_APIS, DRAFT_READ_APIS, OwnTokenLease, OwnTokenScope, validate_profile
from .own_store import OwnStore
from .own_workflow import OwnWorkflow, stored
from .prepared_contracts import ID, DIGEST, strict_validate
from .service import digest
from . import own_lineage as lineage
from . import own_wire as wire
from .upload_wire import BODY_API_REFERENCE_POLICY, COVER_RESPONSE_POLICY, inspect_response


def validate_delegated(db, m, value):
    original = {'policy', 'lineage', 'lineage_digest', 'response_policy'}
    v2 = original | {'schema', 'cover_response_policy'}
    v3 = v2 | {'article_metadata'}
    if type(value) is not dict or set(value) not in (original, v2, v3):
        raise WCEError('OWN_DELEGATION_CORRUPT')
    if 'schema' in value and (type(value['schema']) is not int
            or value['schema'] != (3 if set(value) == v3 else 2)
            or value['cover_response_policy'] != COVER_RESPONSE_POLICY):
        raise WCEError('OWN_DELEGATION_CORRUPT')
    if set(value) == v3:
        from .own_draft_defaults import validate_defaults_metadata
        count = len(m['document']['articles']) if m['schema'] in (2, 3) else 1
        validate_defaults_metadata(value['article_metadata'], expected_binding_sha=digest(m['binding']),
                                   article_count=count)
    policy = value['policy']
    if (type(policy) is not dict or set(policy) != {'id', 'revision', 'policy_digest', 'candidate_scope'}
            or type(policy['revision']) is not int or policy['revision'] < 1):
        raise WCEError('OWN_DELEGATION_CORRUPT')
    strict_validate(policy['id'], ID)
    for key in ('policy_digest', 'candidate_scope'):
        strict_validate(policy[key], DIGEST)
    if (value['lineage'] != lineage.seal(db, m) or value['lineage']['legacy'] != 0
            or value['lineage_digest'] != digest(value['lineage'])
            or value['response_policy'] != BODY_API_REFERENCE_POLICY):
        raise WCEError('OWN_DELEGATION_CORRUPT')


class PersistentWorkflow(OwnWorkflow):
    def __init__(self, *args, policy, token_cache, physical_resources=None, **kwargs):
        self.policy, self.token_cache = policy, token_cache
        self.active_lease = None
        self.read_attempt = None
        self.ordinary_draft_read_context = None
        self._ordinary_http_window = None
        self.live_guard = None
        if physical_resources is None:
            super().__init__(*args, **kwargs)
        else:
            super().__init__(*args, physical_resources=physical_resources, **kwargs)
        if self.db is not None:
            p = next(iter(self.registry.profiles.values()))
            self.db = OwnStore(self.db.path, p.source_kind, persistent=True, history_policy=self.policy,
                **({} if physical_resources is None else {"physical_resources":physical_resources}))

    def activate(self, profile, cached_token=None, deadline=None):
        self.policy.check()
        self.registry.profiles = {(profile.actor, profile.connection_id): profile}
        self.active_lease = (OwnTokenLease(OwnTokenScope.from_profile(profile), cached_token.token,
                             min(profile.expires, cached_token.wall_deadline)) if cached_token else None)
        self.active_token = cached_token
        self.execution_deadline = deadline

    def _lease(self, p):
        return self.active_lease

    def _preview_guard(self, p):
        # AccountService rotates call-local credentials even for articles.read.
        # An immutable preview follows the persistent identity and policy, while
        # retaining every deadline captured when that preview was created.
        validate_profile(p, self.clock())
        if 'local.read' not in p.granted_actions:
            raise WCEError('OWN_ACCESS_DENIED')
        current = self._profile(p.actor, p.connection_id)
        if current.binding() != p.binding():
            raise WCEError('OWN_AUTHORIZATION_CHANGED')
        self.policy.check()
        if self.live_guard is not None:
            self.live_guard()

    def _current(self, p, lease, action='local.read'):
        self.policy.check()
        if self.live_guard is not None:
            self.live_guard()
        if self.execution_deadline is not None and time.monotonic() >= self.execution_deadline:
            raise WCEError('CONNECTION_QUEUE_EXPIRED')
        self._profile(p.actor, p.connection_id, action, p)
        if lease is not self.active_lease:
            raise WCEError('OWN_AUTHORIZATION_CHANGED')
        if lease is not None and (lease.scope != OwnTokenScope.from_profile(p)
                or lease.expires_at <= self.clock() or not self.token_cache.valid(self.active_token)):
            raise WCEError('OWN_TOKEN_UNAVAILABLE')

    @contextmanager
    def ordinary_http_call(self):
        """Technical waiting opt-in for the current ordinary broker call only."""
        if self._ordinary_http_window is not None or self.active_lease is None:
            raise WCEError('OWN_AUTHORIZATION_CHANGED')
        self._ordinary_http_window = (os.getpid(), threading.get_ident(),
                                     self.active_lease, self.execution_deadline)
        try:
            yield
        finally:
            self._ordinary_http_window = None

    def _transport_timeout(self, lease):
        timeout = super()._transport_timeout(lease)
        window = self._ordinary_http_window
        if (type(window) is tuple and len(window) == 4
                and window[0] == os.getpid() and window[1] == threading.get_ident()
                and window[2] is lease and window[3] == self.execution_deadline
                and self.execution_deadline is not None and self.read_attempt is None):
            timeout = min(30.0, lease.expires_at - self.clock())
        if self.execution_deadline is not None:
            remaining = self.execution_deadline - time.monotonic()
            if remaining <= 0:
                raise WCEError('CONNECTION_QUEUE_EXPIRED')
            timeout = min(timeout, remaining)
        if timeout <= 0:
            raise WCEError('OWN_TOKEN_UNAVAILABLE')
        return timeout

    def _network(self, p, lease, action, write=False, read_attempt=False):
        self._current(p, lease, action)
        from .own_draft_reconcile import checked_ordinary_context
        ordinary = checked_ordinary_context(self, p, lease)
        if ordinary is not None:
            allowed = not write and read_attempt and action in DRAFT_READ_APIS
        elif self.read_attempt is not None:
            self.read_attempt.current()
            allowed = not write and read_attempt and action in READ_APIS
        else:
            allowed = action in APIS and not read_attempt
        if lease is None or not allowed:
            raise WCEError('OWN_ACCESS_DENIED')
        self._sender_provenance(p,lease,action,write=write,read_attempt=read_attempt)


    def _validate_delegation(self, value):
        if value != self.policy.delegation():
            raise WCEError('OWN_DELEGATION_UNAVAILABLE')

    def _register_article(self, db, manifest):
        lineage.register(db, manifest)

    def _write_gate(self, db, p, m, current_id=None, *, history_locators=None):
        from .draft_revision_guard import guard_manifest_readonly
        guard_manifest_readonly(self.policy,db,m)
        value=lineage.seal(db,m)
        from .own_draft_restore_store import check_write as check_restores
        check_restores(db,p.actor.tenant_id,p.resource_id,None if value['legacy'] else value['lineage'])
        value=lineage.check_write(self, db, p, m, current_id, history_locators=history_locators)
        from .draft_group_store import check_workflow_writer
        check_workflow_writer(db, p.binding(), m, current_id, history_locators=history_locators)
        return value

    def _insert_lock(self, db, p, m, identifier):
        value = lineage.seal(db, m)
        db.execute('INSERT INTO own_lineage_locks VALUES(?,?,?,?)',
                   (p.actor.tenant_id, p.resource_id, value['lineage'], identifier))

    def _release_lock(self, db, p, m, identifier):
        value = lineage.seal(db, m)
        if db.execute('DELETE FROM own_lineage_locks WHERE tenant=? AND resource=? AND lineage=? AND owner_id=?',
                (p.actor.tenant_id, p.resource_id, value['lineage'], identifier)).rowcount != 1:
            raise WCEError('OWN_LINEAGE_CORRUPT')

    def _owned_lock(self, db, p, m, identifier):
        value = lineage.seal(db, m)
        row = db.execute('SELECT owner_id FROM own_lineage_locks WHERE tenant=? AND resource=? AND lineage=?',
                         (p.actor.tenant_id, p.resource_id, value['lineage'])).fetchone()
        if row is None or row['owner_id'] != identifier:
            raise WCEError('OWN_LINEAGE_CORRUPT')

    def authorize_request(self, arguments):
        p = self._profile(self.policy.actor, arguments['connection_id'])
        with _history_transaction(self.db) as (db, history_locators):
            self._resource(db, p, history_locators=history_locators)
            old = self._history(db, p, arguments['request_key'], history_locators=history_locators)
            if old is not None:
                return  # Status/cached history remains subject to exact-key checks.
            m, d = self._bundle(db, p, arguments['bundle_id'], arguments['version'])
            if d != arguments['content_digest']:
                raise WCEError('OWN_SNAPSHOT_CHANGED')
            value = self._write_gate(db, p, m, history_locators=history_locators)
        delegated = self._delegated_request_approval(m, value, arguments=arguments)
        return self.authorize_trial(p.actor, p.connection_id, m['bundle_id'], m['version'], d,
            min(self.clock() + 300, p.expires, p.credential_expires), delegated=delegated)


    def _sender_provenance(self,p,lease,action,*,write,read_attempt):
        if p.source_kind=='SYNTHETIC_SETUP' and type(self.sender) is HTTPSender:
            from .draft_group_provider import current_syn_admitting_database,validate_syn_admitting_prepared_in
            db=current_syn_admitting_database(self)
            validate_syn_admitting_prepared_in(self,db,p,lease,action,write=write,read_attempt=read_attempt)
            return None
        if p.source_kind == 'SYNTHETIC_SETUP':
            if getattr(self.sender, 'mode', None) != 'SYNTHETIC_OWN_WIRE' or type(self.sender) is HTTPSender:
                raise WCEError('OWN_PROVENANCE_MISMATCH')
        elif type(self.sender) is not HTTPSender or not self.sender.enabled:
            raise WCEError('OWN_HTTP_DISABLED')


    @staticmethod
    def _request_draft_metadata(m):
        """Original default metadata values; no policy or database authority."""
        from .own_draft_defaults import POLICY, SOURCE_KIND, VALUES_SHA, validate_defaults_metadata
        count = len(m['document']['articles']) if m['schema'] in (2, 3) else 1
        metadata = {'schema': 1, 'policy': POLICY, 'article_count': count,
            'comment_settings': {'need_open_comment': 1, 'only_fans_can_comment': 0},
            'originality_intent': 'review_required', 'auto_feature_intent': 'review_required',
            'defaults_source': {'kind': SOURCE_KIND, 'binding_sha': digest(m['binding']),
                                'revision': 0, 'values_sha': VALUES_SHA}}
        validate_defaults_metadata(metadata, expected_binding_sha=digest(m['binding']), article_count=count)
        return metadata


    def _delegated_request_approval(self, m, value, *, arguments):
        """Original delegated body material, not an approval or a write grant."""
        delegated = {'policy': self.policy.delegation(), 'lineage': value,
            'lineage_digest': digest(value), 'response_policy': BODY_API_REFERENCE_POLICY,
            'schema': 2, 'cover_response_policy': COVER_RESPONSE_POLICY}
        if 'slot' not in arguments:
            metadata = self._request_draft_metadata(m)
            delegated.update(schema=3, article_metadata=metadata)
        return delegated


    def _response_dispatch_pin(self, p, row, request):
        from .own_response_archive import capture
        return capture(self, p, row, request)

    def _parse_dispatch_response(self, p, row, dispatch, response, token):
        from .own_response_archive import parse_captured_response
        return parse_captured_response(self, p, row, dispatch, response, token)

    def _release_dispatch_pin(self, dispatch):
        from .own_response_archive import release_dispatch
        release_dispatch(dispatch)

    def _archive_response(self, p, row, dispatch, response, reply, token):
        from .own_response_archive import archive
        return archive(self, p, row, dispatch, response, reply, token)

    def _parse_response(self, operation, response, token, synthetic):
        if operation != 'body':
            return super()._parse_response(operation, response, token, synthetic)
        inspected = inspect_response('article_body', response, token,
            policy=BODY_API_REFERENCE_POLICY, production=not synthetic)
        reply = inspected.reply
        return wire.OwnReply({'url': reply.url} if reply.classification == 'PARSED_SUCCESS' else None,
            reply.error_code, reply.requires_credential_update, inspected.reason, inspected)

    def _parse_admitted_response(self, profile, row, response, token):
        # Select from this exact admitted intent, not the process's newest
        # parser default. Old schema7 approvals retain legacy cover semantics.
        with _history_transaction(self.db) as (db, history_locators):
            intent, _ = self._step(db, profile, row, history_locators=history_locators)
            m, d = self._bundle(db, profile, intent['selector']['bundle_id'], intent['selector']['version'])
            approval = self._approval(db, profile, m, d, row['approval_id'], False)
            body = stored(approval['body'], approval['body_digest'])
        delegated = body.get('delegated', {})
        if row['operation'] != 'cover' or delegated.get('cover_response_policy') != COVER_RESPONSE_POLICY:
            return super()._parse_admitted_response(profile, row, response, token)
        inspected = inspect_response('permanent_cover', response, token,
            policy=COVER_RESPONSE_POLICY, production=profile.source_kind != 'SYNTHETIC_SETUP')
        reply = inspected.reply
        return wire.OwnReply({'media_id': reply.media_id, 'url': reply.url}
            if reply.classification == 'PARSED_SUCCESS' else None,
            reply.error_code, reply.requires_credential_update, inspected.reason, inspected)

    def evidence(self):
        return {'runtime': 'personal_account_delegation', 'platform_ready': False,
                'platform_verified': False}


from .draft_group_history_context import history_transaction as _history_transaction
