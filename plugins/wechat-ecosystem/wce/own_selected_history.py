"""Tokenless, read-only prepared-request history; not an acceptance issuer.

This leaf can verify a previously committed prepare under a real Owned/H
snapshot. It never constructs AccountService, OwnStore, a live OwnProfile,
sender, approval, Group source, or token. A future fixed private Operator
ingress must independently authenticate an exact request before it can use
these facts to issue its own short-lived witness.
"""
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
import os
import threading

from .contracts import Actor, WCEError
from .own_connection_policy import ConnectionPolicy
from .own_prepared_history import PreparedHistoryValidation, binding_validate, stored
from .service import canonical, digest


def _hold():
    raise WCEError('GROUP_OPERATOR_PREPARED_HISTORY_HOLD')


@dataclass(frozen=True)
class _HistoryStoreView:
    """Historical path/policy only; deliberately no connect/write operations."""
    path: Path
    history_policy: ConnectionPolicy


@dataclass(frozen=True)
class _HistoricalBinding:
    """Original identity only, with no invented credentials or expiry."""
    _encoded: str
    actor: Actor
    connection_id: str
    account_id: str
    resource_id: str
    source_kind: str

    @classmethod
    def from_value(cls, value):
        binding_validate(value)
        return cls(canonical(value),
            Actor(value['tenant'], value['principal'], value['client'], value['session']),
            value['connection'], value['account'], value['resource'], value['source_kind'])

    def binding(self):
        # A detached identity cannot change through a returned nested object.
        import json
        return json.loads(self._encoded)


def _policy_binding(policy, source_kind):
    identity = policy.data
    actor = identity['actor']
    return {'tenant': actor['tenant_id'], 'principal': actor['principal_id'],
        'client': actor['client_id'], 'session': actor['session_id'],
        'connection': identity['connection_id'], 'account': identity['appid'],
        'resource': identity['resource_id'], 'epoch': identity['epoch'],
        'generation': identity['generation'], 'source_kind': source_kind}


class _PreparedHistoryReader(PreparedHistoryValidation):
    """Live only inside the owning read-only SQL/H transaction."""
    def __init__(self, policy, db, history):
        from .own_history_source import connection_source
        from .own_validation_scope import _transaction_marker
        self.policy, self.sql, self.history = policy, db, history
        self.db = _HistoryStoreView(policy.root / 'state.sqlite3', policy)
        self.source = connection_source(db)
        self.owner = (os.getpid(), threading.get_ident())
        self.transaction = _transaction_marker(db)
        self.policy_snapshot = (canonical(policy.data), canonical(policy.value), policy.path)
        self.closed = False
        self.check()
        source_kind = db.execute('SELECT source_kind FROM own_config WHERE id=1').fetchone()
        if source_kind is None or source_kind[0] not in ('OPERATOR_ATTESTED', 'SYNTHETIC_SETUP'):
            _hold()
        self.profile = _HistoricalBinding.from_value(_policy_binding(policy, source_kind[0]))
        self._check_all_history()

    def check(self):
        from .draft_group_history_context import current_history_policy, require_history
        from .own_history_source import connection_source
        from .own_validation_scope import OwnedConnection, _transaction_marker
        if (self.closed or type(self.policy) is not ConnectionPolicy
                or self.owner != (os.getpid(), threading.get_ident())
                or type(self.sql) is not OwnedConnection or not self.sql.in_transaction
                or self.transaction is None
                or self.source is None or self.source.readonly is not True
                or connection_source(self.sql) is not self.source
                or self.transaction != _transaction_marker(self.sql)
                or current_history_policy(self.sql) is not self.policy
                or self.policy_snapshot != (canonical(self.policy.data),
                                             canonical(self.policy.value), self.policy.path)
                or self.sql.execute('PRAGMA query_only').fetchone()[0] != 1):
            _hold()
        self.source.guard()
        require_history(self.policy, self.sql, self.history)
        # Reuse the actual entered H reader, including its aggregate budgets
        # and final reread. Do not open an unrelated proof-reader lifetime for
        # every selected member inside the same Owned transaction.
        proof_reader = None if self.history is None else self.history.reader
        self.policy.check(readonly=True, proof_reader=proof_reader)

    def _check_all_history(self):
        from .own_store import OwnStore, _check_legacy_history_in
        self.check()
        OwnStore.check(self.sql, self.profile.source_kind, self.policy, history=self.history)
        _check_legacy_history_in(self.sql, self.profile.source_kind, self.db, history=self.history)
        resource = self.sql.execute('SELECT * FROM own_resources WHERE tenant=? AND resource=?',
            (self.profile.actor.tenant_id, self.profile.resource_id)).fetchone()
        if (resource is None or resource['account'] != self.profile.account_id
                or resource['source_kind'] != self.profile.source_kind):
            _hold()
        self.check()

    def prepared_relation(self, *, prepare_request_key, selector):
        """Return history-only refs; missing approval is not manufactured."""
        from .prepared_contracts import ID, DIGEST, strict_validate
        self.check()
        strict_validate(prepare_request_key, ID)
        if type(selector) is not dict or set(selector) != {'bundle_id', 'version', 'content_digest'}:
            _hold()
        strict_validate(selector['bundle_id'], ID)
        strict_validate(selector['version'], ID)
        strict_validate(selector['content_digest'], DIGEST)
        p, db = self.profile, self.sql
        previous = self._old_input(db, p, 'prepare', prepare_request_key)
        if previous is None or any(previous[key] != value for key, value in selector.items()):
            _hold()
        manifest, manifest_sha = self._bundle_full(db, p, selector['bundle_id'], selector['version'])
        if manifest_sha != selector['content_digest']:
            _hold()
        original = db.execute('SELECT * FROM own_inputs WHERE tenant=? AND principal=? AND '
            'connection=? AND kind=? AND request_key=?',
            self._scope(p) + ('prepare', prepare_request_key)).fetchone()
        # _old_input validated the full stored parameters, normalized content,
        # original assets, revision and result against this exact bundle.
        if original is None:
            _hold()
        approvals = []
        for row in db.execute('SELECT * FROM own_approvals WHERE tenant=? AND principal=? AND '
                'connection=? AND resource=? AND manifest_digest=? ORDER BY id',
                self._scope(p) + (p.resource_id, manifest_sha)):
            # Explicit original id is essential: identifier=None filters by
            # current clock even when active=False in the original validator.
            checked = self._approval(db, p, manifest, manifest_sha,
                                     identifier=row['id'], active=False)
            body = stored(checked['body'], checked['body_digest'])
            approvals.append({'id': checked['id'], 'body_sha256': checked['body_digest'],
                'original_expires': checked['expires'], 'cancelled': checked['cancelled'],
                'delegation_sha256': None if body.get('delegated') is None else digest(body['delegated'])})
        from .own_lineage import seal
        lineage = seal(db, manifest)
        facts = {'profile': 'OPERATOR_PREPARED_RELATION_FACT_V1',
            'authority': False, 'qualification': 'NOT_ASSERTED',
            'binding_sha256': digest(p.binding()), 'selector': dict(selector),
            'prepare_request_key': prepare_request_key,
            'input_id': original['id'], 'parameters_sha256': original['fingerprint'],
            'result_sha256': original['result_digest'], 'lineage_sha256': digest(lineage),
            'approval_state': 'ABSENT_VERIFIED' if not approvals else 'HISTORY_ONLY',
            'historical_approvals': approvals,
            'assets': [dict(asset) for asset in manifest['assets']]}
        self.check()
        return facts

    def _approval(self, db, p, manifest, content_digest, identifier=None, active=True,
                  allow_local_adoption=False, allow_draft_read=False):
        # This facade must never accidentally enter an active/current branch
        # inherited from the shared parser, including its implicit clock query.
        self.check()
        if (db is not self.sql or p is not self.profile or identifier is None
                or active is not False or allow_local_adoption is not False
                or allow_draft_read is not False):
            _hold()
        row = super()._approval(db, p, manifest, content_digest,
            identifier=identifier, active=False,
            allow_local_adoption=False, allow_draft_read=False)
        self.check()
        return row

    def close(self):
        self.closed = True


@contextmanager
def readonly_prepared_history(policy):
    """Borrow actual existing RO/H machinery without a Group schema9 gate.

    This is an internal history reader, not a public MCP/CLI entry. There is
    intentionally no way to arm an Operator acceptance issuer here.
    """
    if type(policy) is not ConnectionPolicy:
        _hold()
    policy.check(readonly=True)
    from .draft_group_history_context import readonly_history_snapshot
    reader = None
    with readonly_history_snapshot(policy, policy.root / 'state.sqlite3') as (db, history):
        try:
            reader = _PreparedHistoryReader(policy, db, history)
            yield reader
            reader._check_all_history()
        finally:
            if reader is not None:
                reader.close()
