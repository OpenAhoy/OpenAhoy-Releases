"""Private legacy-case implementation is not distributed. No recovery grant."""
from .contracts import WCEError
def _unavailable(*args, **kwargs):
    raise WCEError("LEGACY_CASE_NOT_DISTRIBUTED")
def need(*args, **kwargs):
    return _unavailable(*args, **kwargs)
def original_member_rows(*args, **kwargs):
    return _unavailable(*args, **kwargs)
def derive_document(*args, **kwargs):
    return _unavailable(*args, **kwargs)
