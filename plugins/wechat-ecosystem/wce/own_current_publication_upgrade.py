"""Private legacy-case implementation is not distributed. No recovery grant."""
from .contracts import WCEError
def _unavailable(*args, **kwargs):
    raise WCEError("LEGACY_CASE_NOT_DISTRIBUTED")
MODE = None
BEFORE_SHA = None
AFTER_SHA = None
REQUEST_SHA = None
TOOL_NAMES = None
def fail(*args, **kwargs):
    return _unavailable(*args, **kwargs)
def capability(*args, **kwargs):
    return _unavailable(*args, **kwargs)
def extension(*args, **kwargs):
    return _unavailable(*args, **kwargs)
def full_contracts(*args, **kwargs):
    return _unavailable(*args, **kwargs)
def authority_from(*args, **kwargs):
    return _unavailable(*args, **kwargs)
def validate_authority(*args, **kwargs):
    return _unavailable(*args, **kwargs)
