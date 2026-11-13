"""Private legacy-case implementation is not distributed. No recovery grant."""
from .contracts import WCEError
def _unavailable(*args, **kwargs):
    raise WCEError("LEGACY_CASE_NOT_DISTRIBUTED")
def _history(*args, **kwargs):
    return _unavailable(*args, **kwargs)
def capture(*args, **kwargs):
    return _unavailable(*args, **kwargs)
def _put(*args, **kwargs):
    return _unavailable(*args, **kwargs)
def verify_old_source(*args, **kwargs):
    return _unavailable(*args, **kwargs)
def prepare_proposal(*args, **kwargs):
    return _unavailable(*args, **kwargs)
