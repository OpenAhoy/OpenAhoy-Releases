"""Connection management without article storage or Group authority.

This domain never upgrades a warm owner into an article executor. Article
requests continue to require the separately authenticated fixed Group entry.
"""
import argparse
from pathlib import Path
import threading
import time

from .contracts import WCEError
from .own_fd_domain import regular_fd_domain

DOMAIN = 'CONNECTION_BASE_V1'
RPC_NAMES = frozenset({'own.preflight', 'own.connections.status',
                       'own.connections.connect'})
TOOL_NAMES = RPC_NAMES | {'own.connections.list'}
GROUP_NAMES = frozenset('own.draft_groups.' + suffix
                        for suffix in ('plan', 'status', 'execute', 'readback'))


def require_method(name):
    if type(name) is not str or name not in RPC_NAMES:
        raise WCEError('ARTICLE_DOMAIN_NOT_READY')


def is_base_runtime(runtime):
    return (type(runtime) is dict and runtime.get('schema') == 3
            and runtime.get('domain') == DOMAIN)


class BaseAccountService:
    """Only the original per-account token cache; no workflow or business DB."""
    def __init__(self, policy):
        from .own_connection_token import TokenCache
        self.policy = policy
        self.tokens = TokenCache(policy)
        self.serial = threading.Lock()
        self.live_guard = None

    def set_guard(self, guard):
        self.live_guard = guard

    def guard(self, deadline, cancel_guard=None):
        if cancel_guard is not None:
            cancel_guard()
        self.policy.check()
        if self.live_guard is not None:
            self.live_guard()
        if time.monotonic() >= deadline:
            raise WCEError('CONNECTION_QUEUE_EXPIRED')

    def call(self, name, arguments, deadline, *, cancel_guard=None):
        require_method(name)
        from .own_connection_tools import validate
        validate(name, arguments)
        if arguments.get('connection_id') != self.policy.data['connection_id']:
            raise WCEError('CONNECTION_SCOPE_MISMATCH')
        with regular_fd_domain(deadline=deadline):
            remaining = deadline - time.monotonic()
            if remaining <= 0 or not self.serial.acquire(timeout=min(60, remaining)):
                raise WCEError('CONNECTION_QUEUE_EXPIRED')
            try:
                self.guard(deadline, cancel_guard)
                if name == 'own.connections.connect':
                    self.tokens.get(lambda: self.guard(deadline, cancel_guard))
                self.guard(deadline, cancel_guard)
                return self.tokens.status()
            finally:
                self.serial.release()


def router(registry=None):
    from .own_connection_tools import ConnectionRouter

    class BaseConnectionRouter(ConnectionRouter):
        base_only = True

        def __init__(self):
            launcher = Path(__file__).resolve().parents[1] / 'scripts' / 'wce_base_connection.py'
            super().__init__(launcher=launcher, registry=registry)

        def call(self, name, arguments):
            if type(name) is str and name in GROUP_NAMES:
                # Separate authenticated Group process; the base owner never
                # receives or acquires article execution capabilities.
                from .own_business_channel import call_business
                return call_business(name, arguments)
            if type(name) is not str or name not in TOOL_NAMES:
                raise WCEError('ARTICLE_DOMAIN_NOT_READY')
            return super().call(name, arguments)

    return BaseConnectionRouter()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('mode', choices=['broker'])
    parser.add_argument('--policy', required=True)
    args = parser.parse_args()
    from .own_connection_policy import load_policy
    from .own_connection_broker import Broker
    policy = load_policy(args.policy)
    policy.check()
    broker = Broker(policy, BaseAccountService(policy))
    broker.runtime = broker.runtime | {'schema': 3, 'domain': DOMAIN}
    broker.serve()
