"""Closed async binding failure projection; no exception text or frame locals."""
from pathlib import Path
import re
import socket
import ssl
from urllib.error import URLError
from .contracts import WCEError

JOURNAL_ERRORS={'CONNECTION_INVALID_APPID','CONNECTION_RESOURCE_ALREADY_BOUND','CONNECTION_INVALID_LABEL',
 'BOOTSTRAP_CREDENTIAL_INVALID','BOOTSTRAP_TOKEN_IP_DENIED','BOOTSTRAP_TOKEN_REJECTED',
 'CONNECTION_SETUP_BUSY','INLINE_BINDING_CANCELLED','INLINE_BINDING_ENVELOPE_REJECTED',
 'INLINE_BINDING_CRYPTO_UNAVAILABLE','INLINE_BINDING_KEY_EXPIRED'}
SAFE_ERRORS = JOURNAL_ERRORS | {'BOOTSTRAP_TOKEN_CREDENTIAL_REJECTED','BOOTSTRAP_TOKEN_QUOTA_DENIED',
 'BOOTSTRAP_TOKEN_ADMIN_PENDING','BOOTSTRAP_TOKEN_ADMIN_DENIED',
 'BOOTSTRAP_TOKEN_HTTP_FAILED','BOOTSTRAP_TOKEN_INVALID_RESPONSE','BOOTSTRAP_INVALID_JSON',
 'BOOTSTRAP_TOKEN_RESULT_UNKNOWN','BOOTSTRAP_TOKEN_EXPIRED',
 'CONNECTION_TOKEN_TIME_INVALID','CONNECTION_CLOCK_UNAVAILABLE',
 'CONNECTION_REVIEW_CHANGED','CONNECTION_ENROLLMENT_CHANGED',
 'CONNECTION_KEYCHAIN_STORE_UNDETERMINED'}
FAILURE_KINDS={'TIMEOUT','TLS_ERROR','DNS_ERROR','CONNECTION_ERROR','UNCLASSIFIED_ERROR'}


def failure_diagnostic(error):
    """Closed facts only; never stringify an exception or inspect frame locals.

    The asynchronous worker is outside SupportRouter's exception boundary.
    Retain its fixed reason/location without turning a failure into retry proof.
    """
    reason=_reason(error);kind='UNCLASSIFIED_ERROR';site=None;seen=set();current=error
    while current is not None and id(current) not in seen:
        seen.add(id(current))
        item=current.reason if type(current) is URLError else current
        if isinstance(item,TimeoutError):kind='TIMEOUT'
        elif isinstance(item,ssl.SSLError):kind='TLS_ERROR'
        elif isinstance(item,socket.gaierror):kind='DNS_ERROR'
        elif isinstance(item,ConnectionError):kind='CONNECTION_ERROR'
        frame=current.__traceback__
        while frame:
            path=Path(frame.tb_frame.f_code.co_filename)
            function=frame.tb_frame.f_code.co_name
            if (path.parent==Path(__file__).parent and re.fullmatch(r'[a-z_]+\.py',path.name)
                    and re.fullmatch(r'[A-Za-z_][A-Za-z_0-9]{0,63}',function)):
                site={'module':path.name,'function':function,'line':frame.tb_lineno}
            frame=frame.tb_next
        current=current.__cause__ or current.__context__
    return {'reason':reason,'kind':kind,'site':site}


def valid_failure(value):
    if (type(value) is not dict or set(value)!={'reason','kind','site'}
            or type(value['reason']) is not str or value['reason'] not in SAFE_ERRORS|{'INLINE_BINDING_RESULT_UNDETERMINED'}
            or type(value['kind']) is not str or value['kind'] not in FAILURE_KINDS):return False
    site=value['site']
    return site is None or (type(site) is dict and set(site)=={'module','function','line'}
        and type(site['module']) is str and re.fullmatch(r'[a-z_]+\.py',site['module']) is not None
        and type(site['function']) is str and re.fullmatch(r'[A-Za-z_][A-Za-z_0-9]{0,63}',site['function']) is not None
        and type(site['line']) is int and 0<site['line']<100000)


def _reason(error):
    code=error.code if isinstance(error,WCEError) else ''
    return code if type(code) is str and code in SAFE_ERRORS else 'INLINE_BINDING_RESULT_UNDETERMINED'


def _error(error):
    # Authority journal retains the exact 0.6.22 closed vocabulary so a rollback
    # can still read it. Expanded reasons live only in the diagnostic carrier.
    code=_reason(error)
    return code if code in JOURNAL_ERRORS else 'INLINE_BINDING_RESULT_UNDETERMINED'

