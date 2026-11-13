"""Private legacy-case implementation is not distributed. No recovery grant."""
from .contracts import WCEError
def _unavailable(*args, **kwargs):
    raise WCEError("LEGACY_CASE_NOT_DISTRIBUTED")
CONFIG = None
ACTIVE = None
PURPOSE = None
QUALITY = None
REQUEST = None
_SEAL = None
SCOPE_RAW_SHA256 = None
SCOPE_SHA256 = None
def _scope_basis(*args, **kwargs):
    return _unavailable(*args, **kwargs)
TARGET_FIELDS = None
def _durable_enrollment(*args, **kwargs):
    return _unavailable(*args, **kwargs)
def route_selected(*args, **kwargs):
    return _unavailable(*args, **kwargs)
def is_single(*args, **kwargs):
    return _unavailable(*args, **kwargs)
def is_authority(*args, **kwargs):
    return _unavailable(*args, **kwargs)
def selected_targets(*args, **kwargs):
    return _unavailable(*args, **kwargs)
class SingleAuthorization:
    def __init__(self, *args, **kwargs):
        _unavailable()
