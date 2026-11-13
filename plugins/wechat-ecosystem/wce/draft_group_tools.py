"""Closed Group tool descriptions; handlers are installed by the runtime.

No registration, grant, identity override, path, reference, budget or enablement
is accepted here. This module alone neither exposes a route nor grants access.
"""
from copy import deepcopy
from .contracts import WCEError
from .prepared_contracts import ID, string, strict_validate
from .tools import schema

PREFIX = 'own.draft_groups.'
BATCH = string(76, r'^group-batch-[a-f0-9]{64}$')
SPECS = {
    PREFIX+'plan': schema({'connection_id': ID, 'batch_handle': BATCH, 'request_key': ID}),
    PREFIX+'status': schema({'connection_id': ID, 'operation_id': ID}),
    PREFIX+'execute': schema({'connection_id': ID, 'operation_id': ID}),
    PREFIX+'readback': schema({'connection_id': ID, 'operation_id': ID,
        'phase': {'type': 'string', 'enum': ['QUALIFY', 'DISCOVER', 'NEW', 'RETIRE', 'FINAL']}}),
}
NETWORK = frozenset((PREFIX+'execute', PREFIX+'readback'))


def validate(name, arguments):
    if type(name) is not str or name not in SPECS:
        raise WCEError('TOOL_NOT_IMPLEMENTED')
    strict_validate(arguments, SPECS[name])


def descriptors():
    descriptions = {
        'plan': 'Inspect a host-registered ordered batch locally; no platform call or execution grant.',
        'status': 'Read the original Group journal locally without a token or platform call.',
        'execute': 'Use only an existing exact parent grant and current active child; default OFF, never resend unknown writes.',
        'readback': 'Use the original registered phase and bounded read ledger; no supplied references or new grant.',
    }
    return [{'name': name, 'inputSchema': deepcopy(spec),
        'description': descriptions[name[len(PREFIX):]]} for name, spec in SPECS.items()]


def call(name, arguments, registry=None, launcher=None):
    """Route only closed Group calls through the fixed runtime bridge."""
    validate(name, arguments)
    from .own_connection_policy import resolve
    from .draft_group_host_bootstrap import call_group
    policy = resolve(arguments['connection_id'], registry,
                     active=name != PREFIX + 'status')
    return call_group(policy, name, arguments, launcher)
