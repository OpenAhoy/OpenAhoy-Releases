"""Private legacy-case implementation is not distributed. No recovery grant."""
from .contracts import WCEError
def _unavailable(*args, **kwargs):
    raise WCEError("LEGACY_CASE_NOT_DISTRIBUTED")
POLICY = None
SOURCE = None
VALUES = None
def seal(*args, **kwargs):
    return _unavailable(*args, **kwargs)
def verify(*args, **kwargs):
    return _unavailable(*args, **kwargs)
def decorate(*args, **kwargs):
    return _unavailable(*args, **kwargs)
def reject_legacy_for_new_grant(*args, **kwargs):
    return _unavailable(*args, **kwargs)
def compare(*args, **kwargs):
    return _unavailable(*args, **kwargs)
