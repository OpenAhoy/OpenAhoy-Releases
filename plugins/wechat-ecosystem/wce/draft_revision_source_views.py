"""Private legacy-case implementation is not distributed. No recovery grant."""
from .contracts import WCEError
def _unavailable(*args, **kwargs):
    raise WCEError("LEGACY_CASE_NOT_DISTRIBUTED")
RELATION = None
_THREAD = None
WORKFLOW_PINS = None
PUBLICATION_PINS = None
def hold(*args, **kwargs):
    return _unavailable(*args, **kwargs)
def pin_value(*args, **kwargs):
    return _unavailable(*args, **kwargs)
def classify(*args, **kwargs):
    return _unavailable(*args, **kwargs)
def validate_direct_windows(*args, **kwargs):
    return _unavailable(*args, **kwargs)
def canonical_pins(*args, **kwargs):
    return _unavailable(*args, **kwargs)
def source_binding(*args, **kwargs):
    return _unavailable(*args, **kwargs)
def verify_observations(*args, **kwargs):
    return _unavailable(*args, **kwargs)
