"""Private legacy-case implementation is not distributed. No recovery grant."""
from .contracts import WCEError
def _unavailable(*args, **kwargs):
    raise WCEError("LEGACY_CASE_NOT_DISTRIBUTED")
POLICY = None
RELATION_MODULE_SHA = None
RECEIPT_PREFIX = None
_IGNORED_KEYS = None
def fail(*args, **kwargs):
    return _unavailable(*args, **kwargs)
FIXED_RETAINED = None
def _case_groups(*args, **kwargs):
    return _unavailable(*args, **kwargs)
def _context_value(*args, **kwargs):
    return _unavailable(*args, **kwargs)
def _verify_receipt(*args, **kwargs):
    return _unavailable(*args, **kwargs)
def _receipt(*args, **kwargs):
    return _unavailable(*args, **kwargs)
def build(*args, **kwargs):
    return _unavailable(*args, **kwargs)
def immutable(*args, **kwargs):
    return _unavailable(*args, **kwargs)
def current(*args, **kwargs):
    return _unavailable(*args, **kwargs)
def allowed(*args, **kwargs):
    return _unavailable(*args, **kwargs)
