"""Trusted software updater: drain idle brokers before replacing their files.

No token, Keychain, business dispatch, account edits or process signals.
Run from the verified new release, before the official marketplace replacement.
"""
from pathlib import Path
from contextlib import contextmanager, ExitStack
import json
import sys
import time

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from wce.contracts import WCEError
from wce.own_connection_policy import read_registry, resolve
from wce.own_connection_broker import (
    STARTUP_SECONDS, _startup_gate, _startup_has_owner, _replace_idle_software_owner)


@contextmanager
def quiesced(registry=None):
    """The trusted installer keeps these gates held through file replacement."""
    results = []
    with ExitStack() as held:
        for cid in sorted(read_registry(registry)['connections']):
            policy = resolve(cid, registry, active=False)
            if not policy.value['enabled']:
                results.append({'connection_id': cid, 'state': 'DISCONNECTED_PRESERVED'})
                continue
            if policy.value['schema'] == 2:
                from wce.own_connection_registry import revoked
                if revoked(policy):
                    results.append({'connection_id': cid, 'state': 'DISCONNECTED_PRESERVED'})
                    continue
            deadline = time.monotonic() + STARTUP_SECONDS
            held.enter_context(_startup_gate(policy, deadline))
            if _startup_has_owner(policy):
                _replace_idle_software_owner(policy, deadline)
            results.append({'connection_id': cid, 'state': 'IDLE_OWNER_RELEASED'})
        yield {'state': 'BROKERS_QUIESCED', 'connections': results,
               'business_requests': 0, 'account_changes': 0}


def quiesce(registry=None):
    # A standalone check releases its gates on return; installers use quiesced.
    with quiesced(registry) as result:
        return result


if __name__ == '__main__':
    try:
        print(json.dumps(quiesce(), ensure_ascii=False))
    except WCEError as error:
        print(json.dumps({'state': 'UPDATE_NOT_STARTED', 'error': error.code}))
        raise SystemExit(1)
