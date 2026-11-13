"""Only bounded document locations and closed technical rules cross processes."""
from .contracts import WCEError


def location(error):
    result={}
    if error.code.startswith('HTML_') or error.code.startswith('DOCUMENT_MARKDOWN_'):
        for key in ('line','column'):
            value=getattr(error,key,None)
            if type(value) is int and 1<=value<=12001:result[key]=value
    from .html_technical_standard import safe_diagnostic
    technical=safe_diagnostic(getattr(error,'technical_rule',None),error.code)
    if technical is not None:result['technical_rule']=technical
    return result


def restore(code, fields):
    error=WCEError(code)
    if type(fields) is not dict or set(fields)-{'line','column','technical_rule'}:
        raise WCEError('CONNECTION_RESULT_UNDETERMINED')
    for key,value in fields.items():setattr(error,key,value)
    if location(error)!=fields:
        raise WCEError('CONNECTION_RESULT_UNDETERMINED')
    return error
