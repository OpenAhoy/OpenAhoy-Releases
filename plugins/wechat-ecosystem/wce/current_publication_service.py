"""Ordinary saved-draft publication, independent of private historical requests."""
from pathlib import Path
from .contracts import WCEError
PREFIX = 'own.publications.current.'
METHODS = frozenset(PREFIX + action for action in ('dispatch', 'status', 'poll'))
def local_status(policy, registry, handle):
    from .ordinary_publication import local_status as read
    return read(policy, registry, handle)
def execute(service, name, arguments, deadline, cancel_guard=None):
    if name not in METHODS:
        raise WCEError('TOOL_NOT_IMPLEMENTED')
    from .own_connection_policy import registry_path
    from .ordinary_publication import execute as run
    registry = Path(service.policy.value.get('registry_path') or registry_path())
    return run(service, name, arguments, registry, deadline, cancel_guard)
