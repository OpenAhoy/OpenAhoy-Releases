"""Human-only fresh connection checks. No business API, broker or cached token."""
from hashlib import sha256
import os
from pathlib import Path
import re
import time

from .contracts import Secret, WCEError
from .own_bootstrap_security import acquire_checked, finite, path_check, private_read
from .own_connection_enrollment import exclusive
from .own_connection_policy import locked
from .own_connection_registry import container, metadata, transaction_path
from .own_connection_token import ContinuousClock, token_lock
from .own_keychain import KeychainCredential
from .service import canonical, digest

BUDGET_ID = 'NET01_CONNECTION_CHECK_V1'
HEX = re.compile('[a-f0-9]{64}')


class CheckBudget:
    """Explicit historical NET01 pins, never a normal account allowance.

    None selects normal operation and must not discover old exercise files.
    An explicit trusted startup pin retains its original consumed-claim rules.
    """
    def __init__(self, registry, required=None):
        self.registry = Path(registry)
        self.path = self.registry.parent / 'connection-check-budget.json'
        self.directory = self.registry.parent / 'connection-check-budget'
        self.required = required
        self.value = None
        self.pins = None
        self.claimed = None
        if required is not None:
            self.value = metadata(self.path)
            d = self.value
            if (type(d) is not dict or set(d) != {'schema', 'budget_id', 'identities', 'total', 'per_account'}
                    or type(d['schema']) is not int or d['schema'] != 1 or d['budget_id'] != BUDGET_ID
                    or type(d['total']) is not int or d['total'] != 2
                    or type(d['per_account']) is not int or d['per_account'] != 1
                    or type(d['identities']) is not list or len(d['identities']) != 2
                    or len(set(d['identities'])) != 2
                    or any(type(x) is not str or HEX.fullmatch(x) is None for x in d['identities'])):
                raise WCEError('CONNECTION_CHECK_BUDGET_REQUIRED')
            self.pins = {'budget_id': BUDGET_ID,
                'document_sha256': sha256(private_read(self.path)[0]).hexdigest(),
                'identities': d['identities'], 'registry_parent': list(path_check(self.registry.parent, True)),
                'budget_directory': list(path_check(self.directory, True))}
            if required is not None and self.pins != required:
                raise WCEError('CONNECTION_CHECK_BUDGET_REQUIRED')
            self.file_pin = path_check(self.path)
        self.check()

    def check(self):
        if self.value is None:
            if self.required is not None:
                raise WCEError('CONNECTION_CHECK_BUDGET_CHANGED')
            return
        if (metadata(self.path) != self.value or path_check(self.path) != self.file_pin
                or list(path_check(self.registry.parent, True)) != self.pins['registry_parent']
                or list(path_check(self.directory, True)) != self.pins['budget_directory']):
            raise WCEError('CONNECTION_CHECK_BUDGET_CHANGED')
        if self.claimed is not None:
            path, value, pin = self.claimed
            if metadata(path) != value or path_check(path) != pin:
                raise WCEError('CONNECTION_CHECK_BUDGET_CHANGED')

    def claim(self, claim):
        self.check()
        if self.value is None:
            return
        identity = claim['identity_digest']
        if identity not in self.value['identities']:
            raise WCEError('CONNECTION_CHECK_BUDGET_TARGET')
        with locked(self.registry.parent / 'connection-check-budget.lock', nonblocking=True):
            self.check()
            paths = list(self.directory.iterdir())
            if len(paths) >= 2 or os.path.lexists(self.directory / (identity + '.json')):
                raise WCEError('CONNECTION_CHECK_BUDGET_SPENT')
            for p in paths:
                old = metadata(p)
                if (p.name not in {x + '.json' for x in self.value['identities']}
                        or type(old) is not dict or set(old) != set(claim)
                        or old['budget_id'] != BUDGET_ID or old['identity_digest'] + '.json' != p.name):
                    raise WCEError('CONNECTION_CHECK_BUDGET_CHANGED')
            exclusive(self.directory / (identity + '.json'), claim, self.pins['budget_directory'])
            path = self.directory / (identity + '.json')
            self.claimed = (path, dict(claim), path_check(path))
            self.check()


def fresh_check(policy, transaction, guard, required_budget=None, credential_factory=KeychainCredential,
                acquire=acquire_checked, wall=time.time, continuous=None):
    """One consumed human review yields at most one actual ordinary POST."""
    continuous = continuous or ContinuousClock()
    registry = Path(policy.value['registry_path'])
    transaction_path(registry, transaction)

    def current():
        guard()
        policy.check()

    current()
    budget = CheckBudget(registry, required_budget)
    with token_lock(policy.root) as check_lock:
        current(); budget.check()
        directory = container(policy.root, 'connection-checks')
        directory_pin = list(path_check(directory, True))
        paths = list(directory.iterdir())
        now = wall()
        if not finite(now) or now <= 0:
            raise WCEError('CONNECTION_CHECK_TIME_INVALID')
        identity = digest(policy.data)
        for p in paths:
            old = metadata(p)
            if (type(old) is not dict or set(old) != {'schema', 'budget_id', 'identity_digest',
                    'scope', 'transaction', 'claimed_at'} or type(old['schema']) is not int or old['schema'] != 1
                    or old['identity_digest'] != identity or not finite(old['claimed_at'])
                    or old['claimed_at'] <= 0 or old['budget_id'] not in {None, BUDGET_ID}
                    or type(old['scope']) is not str or HEX.fullmatch(old['scope']) is None
                    or p.name != old['transaction'] + '.json'):
                raise WCEError('CONNECTION_CHECK_HISTORY_INVALID')
            transaction_path(registry, old['transaction'])
            if old['budget_id'] == BUDGET_ID and budget.value is not None:
                raise WCEError('CONNECTION_CHECK_BUDGET_SPENT')
            # Only an explicitly pinned historical exercise retains its old
            # spacing condition. Normal explicit checks have no time quota.
            if budget.value is not None and now - old['claimed_at'] < 30:
                raise WCEError('CONNECTION_CHECK_COOLDOWN')
        path = directory / (transaction + '.json')
        if os.path.lexists(path):
            raise WCEError('CONNECTION_CHECK_SPENT')
        claim = {'schema': 1, 'budget_id': BUDGET_ID if budget.value is not None else None,
            'identity_digest': identity, 'scope': policy.value['candidate_scope'],
            'transaction': transaction, 'claimed_at': now}
        budget.claim(claim)
        exclusive(path, claim, directory_pin)

        def admission():
            check_lock(); current(); budget.check()
            if list(path_check(directory, True)) != directory_pin or metadata(path) != claim:
                raise WCEError('CONNECTION_CHECK_HISTORY_INVALID')

        admission()
        secret = credential_factory(policy).load()
        try:
            if type(secret) is not Secret:
                raise WCEError('CONNECTION_KEYCHAIN_ITEM_REQUIRED')
            admission()
            before_wall, before_cont = wall(), continuous()
            token, deadline, _ = acquire(policy.data['appid'], secret.reveal_for_adapter())
            admission()
            after_wall, after_cont = wall(), continuous()
            if (type(token) is not Secret or not 30 < deadline - before_wall <= 7200.1
                    or after_wall + 30 >= deadline or after_cont - before_cont + 30 >= deadline - before_wall
                    or after_wall < before_wall or after_cont < before_cont
                    or abs((after_wall - before_wall) - (after_cont - before_cont)) >= 5):
                raise WCEError('CONNECTION_TOKEN_TIME_INVALID')
            return {'state': 'TOKEN_CHECK_SUCCEEDED', 'connection_id': policy.data['connection_id'],
                    'checked_at': after_wall, 'platform_business_capabilities': 'NOT_VERIFIED'}
        finally:
            secret = None
            token = None
