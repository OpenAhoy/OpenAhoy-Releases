"""Private extra-send recovery is unavailable in the clean distribution."""
from .contracts import WCEError
METHOD = '_wce.replacement.execute.v1'
def validate(*args, **kwargs):
    raise WCEError('LEGACY_CASE_NOT_DISTRIBUTED')
execute = reconcile = validate
