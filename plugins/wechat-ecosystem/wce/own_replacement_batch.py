"""Reject imported private replacement histories; normal new accounts use schema5.

This distribution has no specialized replacement send or legacy spent registry.
Existing ordinary UNKNOWN and original-key protection stay in OwnStore/workflow.
"""
from contextlib import contextmanager
from pathlib import Path
import os
from .contracts import WCEError
from .own_bootstrap_security import path_check
DIRECTORY = 'lineage-body-replacements'
MARKER = 'replacement-registry.json'
def _clean(registry):
    parent=Path(registry).parent
    if os.path.lexists(parent):
        path_check(parent, True)
        for name in (DIRECTORY, 'lineage-body5-recovery'):
            if os.path.lexists(parent/name):
                raise WCEError('LEGACY_HISTORY_NOT_DISTRIBUTED')
@contextmanager
def maintenance_gate(registry):
    _clean(registry)
    yield
    _clean(registry)
def check_account_claims(db, source_kind, history_policy=None, *, history=None):
    if db.execute('PRAGMA user_version').fetchone()[0] != 5:
        raise WCEError('LEGACY_HISTORY_NOT_DISTRIBUTED')
    root=Path(db.execute('PRAGMA database_list').fetchone()[2]).parent
    path_check(root, True)
    if os.path.lexists(root/MARKER):
        raise WCEError('LEGACY_HISTORY_NOT_DISTRIBUTED')
    if history_policy is not None:
        if history_policy.root != root:
            raise WCEError('CONNECTION_SCOPE_MISMATCH')
        registry=history_policy.value.get('registry_path')
        if registry is not None: _clean(registry)
def known_key(policy, request_key):
    if os.path.lexists(policy.root/MARKER):
        raise WCEError('LEGACY_HISTORY_NOT_DISTRIBUTED')
    registry=policy.value.get('registry_path')
    if registry is not None: _clean(registry)
    return False

@contextmanager
def revocation_gate(policy, reason="REVOKED"):
    # This profile has no replacement executor. Revocation must remain available
    # even when unsupported foreign history blocks new business/maintenance.
    # The caller still holds its original policy lock and writes the same seal.
    yield
