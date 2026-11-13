"""Private legacy-case implementation is not distributed. No recovery grant."""
from .contracts import WCEError
def _unavailable(*args, **kwargs):
    raise WCEError("LEGACY_CASE_NOT_DISTRIBUTED")
LEGACY_CONTRACT_SHA = None
R2_CASE_IDS = None
R2_EXCLUDED_STEP_IDS = None
R2_PREDECESSOR_SHA = None
R2_CONTRACT = None
R2_CONTRACT_SHA = None
R3_ADDITIONAL_STEPS = None
R3_LEGACY_BODY_PIN = None
R3_CONTRACT = None
R3_CONTRACT_SHA = None
B5_CONTRACT = None
B5_CONTRACT_SHA = None
B5_CASE_ID = None
def proposal_name(*args, **kwargs):
    return _unavailable(*args, **kwargs)
def proposal_schema(*args, **kwargs):
    return _unavailable(*args, **kwargs)
def fail(*args, **kwargs):
    return _unavailable(*args, **kwargs)
def count(*args, **kwargs):
    return _unavailable(*args, **kwargs)
def risk_phrase(*args, **kwargs):
    return _unavailable(*args, **kwargs)
def validate_r2_cases(*args, **kwargs):
    return _unavailable(*args, **kwargs)
def validate_cases(*args, **kwargs):
    return _unavailable(*args, **kwargs)
