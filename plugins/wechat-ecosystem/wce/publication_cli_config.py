"""Private legacy CLI review runner is not a distribution capability."""
from .contracts import WCEError
VERSION = None
LAUNCHER = None
NATIVE = None
COMMAND = None
LAUNCHER_SHA = None
NATIVE_SHA = None
SELECTORS = None
CHOICES = None
FIXED = None
def canonical(*args, **kwargs):
    raise WCEError("LEGACY_CASE_NOT_DISTRIBUTED")
def digest(*args, **kwargs):
    raise WCEError("LEGACY_CASE_NOT_DISTRIBUTED")
def _identity(*args, **kwargs):
    raise WCEError("LEGACY_CASE_NOT_DISTRIBUTED")
def read_regular(*args, **kwargs):
    raise WCEError("LEGACY_CASE_NOT_DISTRIBUTED")
def project_user_selectors(*args, **kwargs):
    raise WCEError("LEGACY_CASE_NOT_DISTRIBUTED")
def _toml_value(*args, **kwargs):
    raise WCEError("LEGACY_CASE_NOT_DISTRIBUTED")
def build_exec_argv(*args, **kwargs):
    raise WCEError("LEGACY_CASE_NOT_DISTRIBUTED")
def inspect_runtime(*args, **kwargs):
    raise WCEError("LEGACY_CASE_NOT_DISTRIBUTED")
