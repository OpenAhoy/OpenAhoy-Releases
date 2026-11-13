"""Private legacy-case implementation is not distributed. No recovery grant."""
from .contracts import WCEError
def _unavailable(*args, **kwargs):
    raise WCEError("LEGACY_CASE_NOT_DISTRIBUTED")
BASELINE = None
BASELINE_ATTESTATION_SHA = None
def fail(*args, **kwargs):
    return _unavailable(*args, **kwargs)
def authority_from(*args, **kwargs):
    return _unavailable(*args, **kwargs)
def validate_authority(*args, **kwargs):
    return _unavailable(*args, **kwargs)
