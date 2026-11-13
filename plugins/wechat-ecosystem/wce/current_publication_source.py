"""Private legacy-case implementation is not distributed. No recovery grant."""
from .contracts import WCEError
def _unavailable(*args, **kwargs):
    raise WCEError("LEGACY_CASE_NOT_DISTRIBUTED")
_SOURCE_REOBSERVE = None
CONFIG = None
CURRENT_CONFIG = None
CURRENT_ARCHIVE = None
REQUEST = None
SLOT_RULE = None
PURPOSE = None
_SEAL = None
CONTRACTS = None
ACCOUNTS = None
CURRENT_SCOPE = None
def current_selected(*args, **kwargs):
    return _unavailable(*args, **kwargs)
def interpret_current_scope(*args, **kwargs):
    return _unavailable(*args, **kwargs)
def _current_file(*args, **kwargs):
    return _unavailable(*args, **kwargs)
def _contract_scope(*args, **kwargs):
    return _unavailable(*args, **kwargs)
class Authorization:
    def __init__(self, *args, **kwargs):
        _unavailable()
def is_current(*args, **kwargs):
    return _unavailable(*args, **kwargs)
