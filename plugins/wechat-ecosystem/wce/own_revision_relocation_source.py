"""Private legacy-case implementation is not distributed. No recovery grant."""
from .contracts import WCEError
def _unavailable(*args, **kwargs):
    raise WCEError("LEGACY_CASE_NOT_DISTRIBUTED")
CID = None
APPID = None
OWNER = None
SOURCE = None
PURPOSE = None
_SEAL = None
_ACTIVE = None
def need(*args, **kwargs):
    return _unavailable(*args, **kwargs)
class _Source:
    def __init__(self, *args, **kwargs):
        _unavailable()
def checked(*args, **kwargs):
    return _unavailable(*args, **kwargs)
def source_scope(*args, **kwargs):
    return _unavailable(*args, **kwargs)
