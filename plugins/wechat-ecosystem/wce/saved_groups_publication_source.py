"""Private legacy-case implementation is not distributed. No recovery grant."""
from .contracts import WCEError
def _unavailable(*args, **kwargs):
    raise WCEError("LEGACY_CASE_NOT_DISTRIBUTED")
PURPOSE = None
QUALITY = None
COVERAGE = None
ACTIVE = None
_ROUTE_HANDLE = None
_HASH = None
_SEAL = None
def _hash(*args, **kwargs):
    return _unavailable(*args, **kwargs)
def _read_input(*args, **kwargs):
    return _unavailable(*args, **kwargs)
def is_saved_groups(*args, **kwargs):
    return _unavailable(*args, **kwargs)
def is_registered_saved_groups(*args, **kwargs):
    return _unavailable(*args, **kwargs)
def active_request(*args, **kwargs):
    return _unavailable(*args, **kwargs)
def registered_inventory_handle(*args, **kwargs):
    return _unavailable(*args, **kwargs)
def registered_request(*args, **kwargs):
    return _unavailable(*args, **kwargs)
class SavedGroupsAuthorization:
    def __init__(self, *args, **kwargs):
        _unavailable()
