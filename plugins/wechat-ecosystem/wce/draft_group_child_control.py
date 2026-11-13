"""Closed public-cold control observations. No Parent, scope or owner issuer."""
from hashlib import sha256
import json,math,re,time
from .contracts import WCEError
from .draft_group_tools import NETWORK,validate

PUBLIC_START='GROUP_FIXED_CHILD_PUBLIC_START_V2'
PUBLIC_RESULT='GROUP_FIXED_CHILD_PUBLIC_RESULT_V2'
_MONOTONIC=time.monotonic


def need(value,code='GROUP_FIXED_CHILD_REQUEST'):
    if value is not True:raise WCEError(code)


def validate_public_request(connection_id,name,arguments):
    need(type(connection_id) is str and type(name) is str and name in NETWORK)
    need(type(arguments) is dict and all(type(k) is str and type(v) is str for k,v in arguments.items()))
    validate(name,arguments)
    need(arguments['connection_id']==connection_id,'GROUP_CONNECTION_SCOPE')
    return dict(arguments)


def _selector(value):
    need(type(value) is str and re.fullmatch('[a-f0-9]{64}',value) is not None)
    return value


def _deadline(value):
    now=_MONOTONIC()
    need(type(value) in (int,float) and math.isfinite(value) and now<value<=now+300,'GROUP_FIXED_CHILD_DEADLINE')
    return value


def make_public_start(connection_id,selector_sha,name,arguments,absolute_deadline):
    args=validate_public_request(connection_id,name,arguments)
    return {'schema':2,'profile':PUBLIC_START,'selector_sha':_selector(selector_sha),
        'absolute_deadline':_deadline(absolute_deadline),'name':name,'arguments':args}


def validate_public_start(value,*,connection_id,selector_sha):
    need(type(value) is dict and all(type(k) is str for k in value) and set(value)=={'schema','profile','selector_sha','absolute_deadline','name','arguments'})
    need(type(value['schema']) is int and value['schema']==2 and type(value['profile']) is str and value['profile']==PUBLIC_START
         and type(value['selector_sha']) is str
         and value['selector_sha']==_selector(selector_sha))
    return make_public_start(connection_id,selector_sha,value['name'],value['arguments'],value['absolute_deadline'])


def public_request_sha(value):
    return sha256(json.dumps(value,sort_keys=True,separators=(',',':'),ensure_ascii=True,allow_nan=False).encode()).hexdigest()


def make_public_result(request_sha,result,runtime):
    _selector(request_sha)
    need(type(result) is dict and type(runtime) is dict,'GROUP_STARTUP_RESULT_UNKNOWN')
    return {'schema':2,'profile':PUBLIC_RESULT,'state':'GROUP_FIXED_PUBLIC_REQUEST_COMPLETE',
        'request_sha':request_sha,'result':result,'runtime':runtime}


def validate_public_result(value,request):
    need(type(value) is dict and set(value)=={'schema','profile','state','request_sha','result','runtime'},'GROUP_STARTUP_RESULT_UNKNOWN')
    need(type(value['schema']) is int and value['schema']==2 and type(value['profile']) is str and value['profile']==PUBLIC_RESULT
         and type(value['state']) is str and type(value['request_sha']) is str
         and value['state']=='GROUP_FIXED_PUBLIC_REQUEST_COMPLETE'
         and value['request_sha']==public_request_sha(request)
         and type(value['result']) is dict and type(value['runtime']) is dict,'GROUP_STARTUP_RESULT_UNKNOWN')
    _deadline(request['absolute_deadline'])
    return value['result'],value['runtime']
