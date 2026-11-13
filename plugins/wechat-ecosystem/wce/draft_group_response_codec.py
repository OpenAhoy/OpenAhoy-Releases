"""Closed Group response matrix and semantic snapshot codecs, never authority."""
from dataclasses import dataclass, field
from hashlib import sha256
import json
import re
from .contracts import WCEError
from .http_transport import HTTPResponse,MAX_BODY
from . import draft_group_wire as wire
from . import draft_group_discovery as discovery
from .draft_group_input_files import _binding,_hash,_int,_id,_closed,_plain,_canonical
from .prepared_draft_fixture import decode_json
from .upload_wire import contains_secret

PROFILE='GROUP_ADMITTED_RESPONSE_MINIMAL_V1'
PARSERS={'LIST':'GROUP_LIST_METADATA_V1','GET':'GROUP_GET_FULL_NEWS_V1',
         'DELETE':'GROUP_DELETE_EXPLICIT_ACK_V1','ADD':'GROUP_ADD_REFERENCE_V1'}
ENDPOINTS={'LIST':'BATCHGET','GET':'GET','DELETE':'DELETE','ADD':'ADD'}
CREDENTIAL_KEYS=frozenset(('access_token','refresh_token','appsecret','app_secret','secret',
    'password','cookie','authorization','client_secret','session_key','private_key'))


def fail():raise WCEError('GROUP_RESPONSE_PROOF_HOLD')


def _eq(a,b):return type(a) is type(b) and _canonical(a)==_canonical(b)


def _snapshot_safe(value):
    _plain(value)
    stack=[value];count=0
    while stack:
        item=stack.pop();count+=1
        if count>16384:fail()
        if type(item) is dict:
            for key in item:
                if key.lower() in CREDENTIAL_KEYS:fail()
                if key=='errmsg' and (type(item[key]) is not str or item[key] not in ('','ok')):fail()
            stack.extend(item.values())
        elif type(item) is list:stack.extend(item)
    if 'errmsg' in value and (type(value['errmsg']) is not str or value['errmsg'] not in ('','ok')):fail()


def snapshot_bytes(api,parsed,*,synthetic=False):
    if api=='LIST' and type(parsed) is discovery.ListPage:
        value=parsed.value(synthetic=synthetic);projection=wire.digest(value)
    elif api=='GET' and type(parsed) is wire.GroupSnapshot:
        value=parsed.value();projection=wire.digest(wire.baseline_projection(parsed,synthetic=synthetic))
    else:fail()
    _snapshot_safe(value)
    raw=(wire.canonical(value)+'\n').encode('utf-8')
    if not 1<=len(raw)<=MAX_BODY:fail()
    return raw,projection


def read_snapshot(raw,primary,*,reference=None,list_offset=None):
    if type(raw) is not bytes or not 1<=len(raw)<=MAX_BODY:fail()
    value=decode_json(raw,MAX_BODY,max_nodes=16384)
    if type(value) is not dict or (wire.canonical(value)+'\n').encode()!=raw:fail()
    _snapshot_safe(value)
    admission=primary['admission'];obs=primary['observation']
    if len(raw)!=obs['snapshot_bytes'] or sha256(raw).hexdigest()!=obs['snapshot_file_sha']:fail()
    synthetic=primary['binding']['source_kind']=='SYNTHETIC_SETUP'
    response_sha=primary['transport']['response_body_sha']
    if admission['api']=='LIST':
        if type(list_offset) is not int:fail()
        parsed=discovery.ListPage(list_offset,wire.canonical(value),response_sha)
    elif admission['api']=='GET':
        if reference is None:fail()
        if wire.reference_sha(reference,synthetic=synthetic)!=admission['subject_sha']:fail()
        parsed=wire.GroupSnapshot(reference,wire.canonical(value),response_sha)
    else:fail()
    checked,projection=snapshot_bytes(admission['api'],parsed,synthetic=synthetic)
    if checked!=raw or projection!=obs['projection_sha']:fail()
    return value


@dataclass(frozen=True,slots=True)
class ClassifiedResponse:
    observation: dict = field(repr=False)
    snapshot: bytes|None = field(default=None,repr=False)


def classify_response(api,ledger_kind,slot,response,secret,*,claim_at_ms,completed_at_ms,
                      reference=None,list_offset=None,expected_projection_sha=None,synthetic=False):
    if api not in PARSERS or ledger_kind not in ('PREVIEW','CHILD') or ledger_kind=='PREVIEW' and api not in ('LIST','GET') or ledger_kind=='CHILD' and api=='LIST':fail()
    _int(claim_at_ms)
    timing='COMPLETED_MS' if type(completed_at_ms) is int and claim_at_ms<=completed_at_ms<2**63 else 'UNQUALIFIED'
    obs={'outcome':'UNKNOWN','code':None,'response_reason':'PARSER_UNSUPPORTED',
        'snapshot_file_sha':None,'snapshot_bytes':None,'projection_sha':None,'reference':None,
        'observed_at_ms':completed_at_ms if timing=='COMPLETED_MS' else claim_at_ms,'timing':timing}
    snap=None
    if response is None:
        obs['response_reason']='NO_COMPLETE_TRANSPORT'
        return ClassifiedResponse(obs)
    if type(response) is not HTTPResponse or type(response.status) is not int or type(response.body) is not bytes or len(response.body)>MAX_BODY:fail()
    if not 200<=response.status<300:
        obs['response_reason']='HTTP_NON_SUCCESS'
    else:
        value=None
        try:
            # Raw and decoded reflection checks happen before semantic parsing.
            if contains_secret(response.body,secret):
                obs['response_reason']='SECRET_REFLECTION'
            else:
                value=wire.response_value(response,secret,list_response=api=='LIST')
                code=value.get('errcode',0)
                if type(code) is not int or not -(2**31)<=code<2**31:fail()
                if code:
                    obs.update(code=code,response_reason='INVALID_REFERENCE_OBSERVED' if api=='GET' and code==40007 else 'API_REJECTED',
                        outcome='UNKNOWN' if api=='ADD' else 'INVALID_REF' if api=='GET' and ledger_kind=='CHILD' and slot.startswith('OLD_INVALID:') and code==40007 else 'KNOWN_REJECTED')
                elif api=='ADD' and response.status!=200:
                    obs['response_reason']='ADD_HTTP_STATUS_UNSUPPORTED'
                elif api=='ADD':
                    parsed=wire.parse_add(response,secret,synthetic=synthetic)
                    obs.update(outcome='KNOWN_SUCCESS',response_reason='ADD_REFERENCE_OBSERVED',reference=parsed.reference)
                elif api=='DELETE':
                    wire.parse_delete(response,secret,reference,synthetic=synthetic)
                    obs.update(outcome='ACK_OK',code=0,response_reason='DELETE_EXPLICIT_ACK')
                else:
                    parsed=discovery.parse_list(response,secret,list_offset,synthetic=synthetic) if api=='LIST' else wire.parse_get(response,secret,reference,synthetic=synthetic)
                    try:snap,projection=snapshot_bytes(api,parsed,synthetic=synthetic)
                    except Exception:obs['response_reason']='SNAPSHOT_UNSAFE'
                    else:
                        obs.update(snapshot_file_sha=sha256(snap).hexdigest(),snapshot_bytes=len(snap),projection_sha=projection)
                        if ledger_kind=='PREVIEW':obs.update(outcome='OBSERVED',response_reason='LIST_PAGE_OBSERVED' if api=='LIST' else 'PREVIEW_NEWS_OBSERVED')
                        else:
                            _hash(expected_projection_sha)
                            equal=projection==expected_projection_sha
                            obs.update(outcome='MATCHED' if equal else 'MISMATCH',response_reason='CHILD_NEWS_MATCHED' if equal else 'CHILD_NEWS_MISMATCH')
        except Exception as error:
            # Only this fixed safe code can influence reflection classification;
            # never parse errmsg, URL or arbitrary exception text.
            if getattr(error,'code',None)=='RESPONSE_SECRET_REFLECTION':obs['response_reason']='SECRET_REFLECTION'
    if timing=='UNQUALIFIED':
        if obs['code'] is not None and obs['code']!=0:
            obs['response_reason']='TIMING_UNQUALIFIED_REJECTION'
            if obs['outcome']=='INVALID_REF':obs['outcome']='UNKNOWN'
        elif obs['outcome']=='KNOWN_SUCCESS':obs['response_reason']='ADD_REFERENCE_TIMING_UNQUALIFIED'
        elif obs['outcome']=='ACK_OK':obs['response_reason']='DELETE_ACK_TIMING_UNQUALIFIED'
        elif snap is not None:obs.update(outcome='UNKNOWN',response_reason='TIMING_UNQUALIFIED_WITH_SNAPSHOT')
        elif response is not None:obs.update(outcome='UNKNOWN',response_reason='TIMING_UNQUALIFIED')
    return ClassifiedResponse(obs,snap)


def _matrix_match(row,proof,*,expected_projection_sha=None):
    a=proof['admission'];o=proof['observation'];t=proof['transport']
    if row['ledger_kind'] not in ('ANY',a['ledger_kind']) or row['api'] not in ('ANY',a['api']):return False
    if (row['outcome']!=o['outcome'] or row['response_reason']!=o['response_reason']
            or row['parser_profile'] not in ('API_PROFILE',proof['archive_context']['parser_profile'])):return False
    slot=row['slot_rule'];old=a['slot'].startswith('OLD_INVALID:')
    if slot=='OLD_INVALID_ONLY' and not old or slot=='NON_OLD_INVALID_ONLY' and old:return False
    code=o['code'];rule=row['code_rule']
    if rule=='NULL' and code is not None:return False
    if rule=='EXACT_0' and (type(code) is not int or code!=0):return False
    if rule=='EXACT_40007' and (type(code) is not int or code!=40007):return False
    if rule.startswith('NONZERO_S32') and (type(code) is not int or not -(2**31)<=code<2**31 or code==0 or rule.endswith('EXCEPT_40007') and code==40007):return False
    snap=row['snapshot_rule'];has=o['snapshot_file_sha'] is not None
    if (snap=='NULL')==has:return False
    if snap=='GET_MATCHED' and o['projection_sha']!=expected_projection_sha:return False
    if snap=='GET_MISMATCHED' and (expected_projection_sha is None or o['projection_sha']==expected_projection_sha):return False
    ref=row['reference_rule']
    if ref=='NULL' and o['reference'] is not None:return False
    if ref!='NULL' and o['reference'] is None:return False
    timing=row['timing_rule']
    if timing!='COMPLETED_OR_UNQUALIFIED' and o['timing']!=timing:return False
    status=t['http_status'];rule=row['http_status_rule']
    if rule=='NULL' and status is not None:return False
    if rule=='2XX' and not (type(status) is int and 200<=status<300):return False
    if rule=='NON_2XX' and not (type(status) is int and 100<=status<=599 and not 200<=status<300):return False
    if rule in ('EXACT_200','200') and (type(status) is not int or status!=200):return False
    if rule=='2XX_EXCEPT_200' and not (type(status) is int and 200<status<300):return False
    if rule in ('COMPLETE_STATUS','COMPLETE_ANY_STATUS') and not (type(status) is int and 100<=status<=599):return False
    complete=t['origin']!='NO_QUALIFIED_RESPONSE'
    if (row['transport_rule']=='COMPLETE')!=complete:return False
    return True


def validate_primary(value,*,claim_at_ms=None,expected_projection_sha=None):
    _plain(value)
    _closed(value,('schema','profile','provenance','binding','account_root_identity_sha','admission','transport','observation','archive_context'))
    if type(value['schema']) is not int or value['schema']!=1 or value['profile']!=PROFILE:fail()
    _binding(value['binding']);_hash(value['account_root_identity_sha'])
    a=value['admission'];t=value['transport'];o=value['observation'];c=value['archive_context']
    _closed(a,('ledger_kind','family_id','purpose_key','gid','operation_id','claim_id','api','slot','ordinal','subject_sha','request_sha','admission_event_sha','admission_payload_sha','own_step_pin'))
    if a['ledger_kind'] not in ('PREVIEW','CHILD') or a['api'] not in PARSERS or type(a['slot']) is not str:fail()
    if a['ledger_kind']=='PREVIEW':
        if a['api'] not in ('LIST','GET') or a['operation_id'] is not None or a['own_step_pin'] is not None:fail()
        _hash(a['gid'])
    else:
        if a['api']=='LIST' or a['gid'] is not None:fail()
        if type(a['operation_id']) is not str or not a['operation_id']:fail()
        if a['api']=='ADD':
            if type(a['own_step_pin']) is not dict:fail()
        elif a['own_step_pin'] is not None:fail()
    _id(a['purpose_key'])
    for k in ('family_id','claim_id','subject_sha','request_sha','admission_event_sha','admission_payload_sha'):_hash(a[k])
    _int(a['ordinal'],1,200)
    if a['ledger_kind']=='PREVIEW':
        if a['slot']!='PREVIEW_'+a['api']+':'+str(a['ordinal']) or a['api']=='LIST' and a['ordinal']>20:fail()
    elif a['api']=='ADD':
        if a['slot']!='ADD':fail()
        from .own_response_archive import _FIELDS
        _closed(a['own_step_pin'],_FIELDS)
        if any(type(a['own_step_pin'][k]) is not str for k in _FIELDS if k!='created') or type(a['own_step_pin']['created']) is not float:fail()
    elif a['api']=='DELETE':
        if re.fullmatch(r'DELETE:[0-7]',a['slot']) is None:fail()
    elif a['slot'] not in ('NEW','FINAL_NEW','RECOVERY_NEW','RECOVERY_OLD') and re.fullmatch(r'(?:OLD_BASELINE|OLD_PRE_SWITCH|NEW_REFRESH|OLD_REFRESH|OLD_INVALID):[0-7]',a['slot']) is None:fail()
    _closed(t,('origin','endpoint','request_body_sha','http_status','response_body_sha'))
    if t['endpoint']!=ENDPOINTS[a['api']] or t['request_body_sha']!=a['request_sha']:fail()
    synthetic=value['binding']['source_kind']=='SYNTHETIC_SETUP'
    expected_provenance='SYNTHETIC_GROUP_WIRE' if synthetic else 'OWN_OFFICIAL_GROUP_WIRE'
    origin='SYNTHETIC_GROUP_TRANSPORT_V1' if synthetic else 'OFFICIAL_GROUP_PREPARED_TLS_V1'
    if value['provenance']!=expected_provenance or t['origin'] not in (origin,'NO_QUALIFIED_RESPONSE'):fail()
    if t['origin']=='NO_QUALIFIED_RESPONSE':
        if t['http_status'] is not None or t['response_body_sha'] is not None:fail()
    else:_int(t['http_status'],100,599);_hash(t['response_body_sha'])
    _closed(o,('outcome','code','response_reason','snapshot_file_sha','snapshot_bytes','projection_sha','reference','observed_at_ms','timing'))
    _int(o['observed_at_ms'])
    if o['timing'] not in ('COMPLETED_MS','UNQUALIFIED'):fail()
    if claim_at_ms is not None:
        _int(claim_at_ms)
        if o['timing']=='UNQUALIFIED' and o['observed_at_ms']!=claim_at_ms or o['timing']=='COMPLETED_MS' and o['observed_at_ms']<claim_at_ms:fail()
    if o['snapshot_file_sha'] is None:
        if o['snapshot_bytes'] is not None or o['projection_sha'] is not None:fail()
    else:_hash(o['snapshot_file_sha']);_hash(o['projection_sha']);_int(o['snapshot_bytes'],1,MAX_BODY)
    if o['reference'] is not None and not wire.reference_valid(o['reference'],synthetic):fail()
    _closed(c,('contract_sha','parser_profile','group_input_sha','source_qualification_sha','source_qualification_locator','source_epoch'))
    for k in ('contract_sha','group_input_sha','source_qualification_sha','source_epoch'):_hash(c[k])
    loc=c['source_qualification_locator'];_closed(loc,('account_key','event_seq','event_sha','preview_id','evidence_sha'))
    for k in ('account_key','event_sha','preview_id','evidence_sha'):_hash(loc[k])
    _int(loc['event_seq'],1)
    if c['source_qualification_sha']!=loc['evidence_sha']:fail()
    if c['parser_profile']!=('NONE' if t['origin']=='NO_QUALIFIED_RESPONSE' else PARSERS[a['api']]):fail()
    if not any(_matrix_match(row,value,expected_projection_sha=expected_projection_sha) for row in MATRIX_ROWS):fail()
    return value


def encode_primary(value,**kwargs):
    validate_primary(value,**kwargs)
    raw=(_canonical(value)+'\n').encode('utf-8')
    if len(raw)>16384:fail()
    return raw


def decode_primary(raw,**kwargs):
    if type(raw) is not bytes or not 1<=len(raw)<=16384:fail()
    value=decode_json(raw,16384,max_nodes=4096)
    if encode_primary(value,**kwargs)!=raw:fail()
    return value


# Exact 55-row adopted design matrix, no runtime file dependency.
MATRIX_ROWS = [{'ledger_kind': 'PREVIEW', 'api': 'LIST', 'slot_rule': 'ANY_ALLOWED', 'outcome': 'OBSERVED', 'response_reason': 'LIST_PAGE_OBSERVED', 'parser_profile': 'GROUP_LIST_METADATA_V1', 'code_rule': 'NULL', 'snapshot_rule': 'LIST_FULL', 'reference_rule': 'NULL', 'timing_rule': 'COMPLETED_MS', 'http_status_rule': '2XX', 'transport_rule': 'COMPLETE'}, {'ledger_kind': 'PREVIEW', 'api': 'LIST', 'slot_rule': 'ANY_ALLOWED', 'outcome': 'KNOWN_REJECTED', 'response_reason': 'API_REJECTED', 'parser_profile': 'GROUP_LIST_METADATA_V1', 'code_rule': 'NONZERO_S32', 'snapshot_rule': 'NULL', 'reference_rule': 'NULL', 'timing_rule': 'COMPLETED_MS', 'http_status_rule': '2XX', 'transport_rule': 'COMPLETE'}, {'ledger_kind': 'PREVIEW', 'api': 'GET', 'slot_rule': 'ANY_ALLOWED', 'outcome': 'OBSERVED', 'response_reason': 'PREVIEW_NEWS_OBSERVED', 'parser_profile': 'GROUP_GET_FULL_NEWS_V1', 'code_rule': 'NULL', 'snapshot_rule': 'GET_FULL', 'reference_rule': 'NULL', 'timing_rule': 'COMPLETED_MS', 'http_status_rule': '2XX', 'transport_rule': 'COMPLETE'}, {'ledger_kind': 'PREVIEW', 'api': 'GET', 'slot_rule': 'ANY_ALLOWED', 'outcome': 'KNOWN_REJECTED', 'response_reason': 'INVALID_REFERENCE_OBSERVED', 'parser_profile': 'GROUP_GET_FULL_NEWS_V1', 'code_rule': 'EXACT_40007', 'snapshot_rule': 'NULL', 'reference_rule': 'NULL', 'timing_rule': 'COMPLETED_MS', 'http_status_rule': '2XX', 'transport_rule': 'COMPLETE'}, {'ledger_kind': 'PREVIEW', 'api': 'GET', 'slot_rule': 'ANY_ALLOWED', 'outcome': 'KNOWN_REJECTED', 'response_reason': 'API_REJECTED', 'parser_profile': 'GROUP_GET_FULL_NEWS_V1', 'code_rule': 'NONZERO_S32_EXCEPT_40007', 'snapshot_rule': 'NULL', 'reference_rule': 'NULL', 'timing_rule': 'COMPLETED_MS', 'http_status_rule': '2XX', 'transport_rule': 'COMPLETE'}, {'ledger_kind': 'CHILD', 'api': 'GET', 'slot_rule': 'ANY_ALLOWED', 'outcome': 'MATCHED', 'response_reason': 'CHILD_NEWS_MATCHED', 'parser_profile': 'GROUP_GET_FULL_NEWS_V1', 'code_rule': 'NULL', 'snapshot_rule': 'GET_MATCHED', 'reference_rule': 'NULL', 'timing_rule': 'COMPLETED_MS', 'http_status_rule': '2XX', 'transport_rule': 'COMPLETE'}, {'ledger_kind': 'CHILD', 'api': 'GET', 'slot_rule': 'ANY_ALLOWED', 'outcome': 'MISMATCH', 'response_reason': 'CHILD_NEWS_MISMATCH', 'parser_profile': 'GROUP_GET_FULL_NEWS_V1', 'code_rule': 'NULL', 'snapshot_rule': 'GET_MISMATCHED', 'reference_rule': 'NULL', 'timing_rule': 'COMPLETED_MS', 'http_status_rule': '2XX', 'transport_rule': 'COMPLETE'}, {'ledger_kind': 'CHILD', 'api': 'GET', 'slot_rule': 'OLD_INVALID_ONLY', 'outcome': 'INVALID_REF', 'response_reason': 'INVALID_REFERENCE_OBSERVED', 'parser_profile': 'GROUP_GET_FULL_NEWS_V1', 'code_rule': 'EXACT_40007', 'snapshot_rule': 'NULL', 'reference_rule': 'NULL', 'timing_rule': 'COMPLETED_MS', 'http_status_rule': '2XX', 'transport_rule': 'COMPLETE'}, {'ledger_kind': 'CHILD', 'api': 'GET', 'slot_rule': 'NON_OLD_INVALID_ONLY', 'outcome': 'KNOWN_REJECTED', 'response_reason': 'INVALID_REFERENCE_OBSERVED', 'parser_profile': 'GROUP_GET_FULL_NEWS_V1', 'code_rule': 'EXACT_40007', 'snapshot_rule': 'NULL', 'reference_rule': 'NULL', 'timing_rule': 'COMPLETED_MS', 'http_status_rule': '2XX', 'transport_rule': 'COMPLETE'}, {'ledger_kind': 'CHILD', 'api': 'GET', 'slot_rule': 'ANY_ALLOWED', 'outcome': 'KNOWN_REJECTED', 'response_reason': 'API_REJECTED', 'parser_profile': 'GROUP_GET_FULL_NEWS_V1', 'code_rule': 'NONZERO_S32_EXCEPT_40007', 'snapshot_rule': 'NULL', 'reference_rule': 'NULL', 'timing_rule': 'COMPLETED_MS', 'http_status_rule': '2XX', 'transport_rule': 'COMPLETE'}, {'ledger_kind': 'CHILD', 'api': 'DELETE', 'slot_rule': 'ANY_ALLOWED', 'outcome': 'ACK_OK', 'response_reason': 'DELETE_EXPLICIT_ACK', 'parser_profile': 'GROUP_DELETE_EXPLICIT_ACK_V1', 'code_rule': 'EXACT_0', 'snapshot_rule': 'NULL', 'reference_rule': 'NULL', 'timing_rule': 'COMPLETED_MS', 'http_status_rule': '2XX', 'transport_rule': 'COMPLETE'}, {'ledger_kind': 'CHILD', 'api': 'DELETE', 'slot_rule': 'ANY_ALLOWED', 'outcome': 'KNOWN_REJECTED', 'response_reason': 'API_REJECTED', 'parser_profile': 'GROUP_DELETE_EXPLICIT_ACK_V1', 'code_rule': 'NONZERO_S32', 'snapshot_rule': 'NULL', 'reference_rule': 'NULL', 'timing_rule': 'COMPLETED_MS', 'http_status_rule': '2XX', 'transport_rule': 'COMPLETE'}, {'ledger_kind': 'CHILD', 'api': 'ADD', 'slot_rule': 'ANY_ALLOWED', 'outcome': 'KNOWN_SUCCESS', 'response_reason': 'ADD_REFERENCE_OBSERVED', 'parser_profile': 'GROUP_ADD_REFERENCE_V1', 'code_rule': 'NULL', 'snapshot_rule': 'NULL', 'reference_rule': 'VALID_REFERENCE', 'timing_rule': 'COMPLETED_MS', 'http_status_rule': 'EXACT_200', 'transport_rule': 'COMPLETE'}, {'ledger_kind': 'CHILD', 'api': 'ADD', 'slot_rule': 'ANY_ALLOWED', 'outcome': 'UNKNOWN', 'response_reason': 'API_REJECTED', 'parser_profile': 'GROUP_ADD_REFERENCE_V1', 'code_rule': 'NONZERO_S32', 'snapshot_rule': 'NULL', 'reference_rule': 'NULL', 'timing_rule': 'COMPLETED_MS', 'http_status_rule': '2XX', 'transport_rule': 'COMPLETE'}, {'ledger_kind': 'PREVIEW', 'api': 'LIST', 'slot_rule': 'ANY_ALLOWED', 'outcome': 'UNKNOWN', 'response_reason': 'HTTP_NON_SUCCESS', 'parser_profile': 'GROUP_LIST_METADATA_V1', 'code_rule': 'NULL', 'snapshot_rule': 'NULL', 'reference_rule': 'NULL', 'timing_rule': 'COMPLETED_MS', 'http_status_rule': 'NON_2XX', 'transport_rule': 'COMPLETE'}, {'ledger_kind': 'PREVIEW', 'api': 'LIST', 'slot_rule': 'ANY_ALLOWED', 'outcome': 'UNKNOWN', 'response_reason': 'PARSER_UNSUPPORTED', 'parser_profile': 'GROUP_LIST_METADATA_V1', 'code_rule': 'NULL', 'snapshot_rule': 'NULL', 'reference_rule': 'NULL', 'timing_rule': 'COMPLETED_MS', 'http_status_rule': '2XX', 'transport_rule': 'COMPLETE'}, {'ledger_kind': 'PREVIEW', 'api': 'LIST', 'slot_rule': 'ANY_ALLOWED', 'outcome': 'UNKNOWN', 'response_reason': 'SECRET_REFLECTION', 'parser_profile': 'GROUP_LIST_METADATA_V1', 'code_rule': 'NULL', 'snapshot_rule': 'NULL', 'reference_rule': 'NULL', 'timing_rule': 'COMPLETED_MS', 'http_status_rule': '2XX', 'transport_rule': 'COMPLETE'}, {'ledger_kind': 'PREVIEW', 'api': 'LIST', 'slot_rule': 'ANY_ALLOWED', 'outcome': 'UNKNOWN', 'response_reason': 'NO_COMPLETE_TRANSPORT', 'parser_profile': 'NONE', 'code_rule': 'NULL', 'snapshot_rule': 'NULL', 'reference_rule': 'NULL', 'timing_rule': 'COMPLETED_OR_UNQUALIFIED', 'http_status_rule': 'NULL', 'transport_rule': 'NO_QUALIFIED_RESPONSE'}, {'ledger_kind': 'PREVIEW', 'api': 'LIST', 'slot_rule': 'ANY_ALLOWED', 'outcome': 'UNKNOWN', 'response_reason': 'SNAPSHOT_UNSAFE', 'parser_profile': 'GROUP_LIST_METADATA_V1', 'code_rule': 'NULL', 'snapshot_rule': 'NULL', 'reference_rule': 'NULL', 'timing_rule': 'COMPLETED_MS', 'http_status_rule': '2XX', 'transport_rule': 'COMPLETE'}, {'ledger_kind': 'PREVIEW', 'api': 'LIST', 'slot_rule': 'ANY_ALLOWED', 'outcome': 'UNKNOWN', 'response_reason': 'TIMING_UNQUALIFIED_WITH_SNAPSHOT', 'parser_profile': 'GROUP_LIST_METADATA_V1', 'code_rule': 'NULL', 'snapshot_rule': 'LIST_FULL', 'reference_rule': 'NULL', 'timing_rule': 'UNQUALIFIED', 'http_status_rule': '2XX', 'transport_rule': 'COMPLETE'}, {'ledger_kind': 'PREVIEW', 'api': 'LIST', 'slot_rule': 'ANY_ALLOWED', 'outcome': 'UNKNOWN', 'response_reason': 'TIMING_UNQUALIFIED', 'parser_profile': 'GROUP_LIST_METADATA_V1', 'code_rule': 'NULL', 'snapshot_rule': 'NULL', 'reference_rule': 'NULL', 'timing_rule': 'UNQUALIFIED', 'http_status_rule': 'COMPLETE_ANY_STATUS', 'transport_rule': 'COMPLETE'}, {'ledger_kind': 'PREVIEW', 'api': 'LIST', 'slot_rule': 'ANY_ALLOWED', 'outcome': 'KNOWN_REJECTED', 'response_reason': 'TIMING_UNQUALIFIED_REJECTION', 'parser_profile': 'GROUP_LIST_METADATA_V1', 'code_rule': 'NONZERO_S32', 'snapshot_rule': 'NULL', 'reference_rule': 'NULL', 'timing_rule': 'UNQUALIFIED', 'http_status_rule': '2XX', 'transport_rule': 'COMPLETE'}, {'ledger_kind': 'PREVIEW', 'api': 'GET', 'slot_rule': 'ANY_ALLOWED', 'outcome': 'UNKNOWN', 'response_reason': 'HTTP_NON_SUCCESS', 'parser_profile': 'GROUP_GET_FULL_NEWS_V1', 'code_rule': 'NULL', 'snapshot_rule': 'NULL', 'reference_rule': 'NULL', 'timing_rule': 'COMPLETED_MS', 'http_status_rule': 'NON_2XX', 'transport_rule': 'COMPLETE'}, {'ledger_kind': 'PREVIEW', 'api': 'GET', 'slot_rule': 'ANY_ALLOWED', 'outcome': 'UNKNOWN', 'response_reason': 'PARSER_UNSUPPORTED', 'parser_profile': 'GROUP_GET_FULL_NEWS_V1', 'code_rule': 'NULL', 'snapshot_rule': 'NULL', 'reference_rule': 'NULL', 'timing_rule': 'COMPLETED_MS', 'http_status_rule': '2XX', 'transport_rule': 'COMPLETE'}, {'ledger_kind': 'PREVIEW', 'api': 'GET', 'slot_rule': 'ANY_ALLOWED', 'outcome': 'UNKNOWN', 'response_reason': 'SECRET_REFLECTION', 'parser_profile': 'GROUP_GET_FULL_NEWS_V1', 'code_rule': 'NULL', 'snapshot_rule': 'NULL', 'reference_rule': 'NULL', 'timing_rule': 'COMPLETED_MS', 'http_status_rule': '2XX', 'transport_rule': 'COMPLETE'}, {'ledger_kind': 'PREVIEW', 'api': 'GET', 'slot_rule': 'ANY_ALLOWED', 'outcome': 'UNKNOWN', 'response_reason': 'NO_COMPLETE_TRANSPORT', 'parser_profile': 'NONE', 'code_rule': 'NULL', 'snapshot_rule': 'NULL', 'reference_rule': 'NULL', 'timing_rule': 'COMPLETED_OR_UNQUALIFIED', 'http_status_rule': 'NULL', 'transport_rule': 'NO_QUALIFIED_RESPONSE'}, {'ledger_kind': 'PREVIEW', 'api': 'GET', 'slot_rule': 'ANY_ALLOWED', 'outcome': 'UNKNOWN', 'response_reason': 'SNAPSHOT_UNSAFE', 'parser_profile': 'GROUP_GET_FULL_NEWS_V1', 'code_rule': 'NULL', 'snapshot_rule': 'NULL', 'reference_rule': 'NULL', 'timing_rule': 'COMPLETED_MS', 'http_status_rule': '2XX', 'transport_rule': 'COMPLETE'}, {'ledger_kind': 'PREVIEW', 'api': 'GET', 'slot_rule': 'ANY_ALLOWED', 'outcome': 'UNKNOWN', 'response_reason': 'TIMING_UNQUALIFIED_WITH_SNAPSHOT', 'parser_profile': 'GROUP_GET_FULL_NEWS_V1', 'code_rule': 'NULL', 'snapshot_rule': 'GET_FULL', 'reference_rule': 'NULL', 'timing_rule': 'UNQUALIFIED', 'http_status_rule': '2XX', 'transport_rule': 'COMPLETE'}, {'ledger_kind': 'PREVIEW', 'api': 'GET', 'slot_rule': 'ANY_ALLOWED', 'outcome': 'UNKNOWN', 'response_reason': 'TIMING_UNQUALIFIED', 'parser_profile': 'GROUP_GET_FULL_NEWS_V1', 'code_rule': 'NULL', 'snapshot_rule': 'NULL', 'reference_rule': 'NULL', 'timing_rule': 'UNQUALIFIED', 'http_status_rule': 'COMPLETE_ANY_STATUS', 'transport_rule': 'COMPLETE'}, {'ledger_kind': 'PREVIEW', 'api': 'GET', 'slot_rule': 'ANY_ALLOWED', 'outcome': 'KNOWN_REJECTED', 'response_reason': 'TIMING_UNQUALIFIED_REJECTION', 'parser_profile': 'GROUP_GET_FULL_NEWS_V1', 'code_rule': 'NONZERO_S32', 'snapshot_rule': 'NULL', 'reference_rule': 'NULL', 'timing_rule': 'UNQUALIFIED', 'http_status_rule': '2XX', 'transport_rule': 'COMPLETE'}, {'ledger_kind': 'CHILD', 'api': 'GET', 'slot_rule': 'ANY_ALLOWED', 'outcome': 'UNKNOWN', 'response_reason': 'HTTP_NON_SUCCESS', 'parser_profile': 'GROUP_GET_FULL_NEWS_V1', 'code_rule': 'NULL', 'snapshot_rule': 'NULL', 'reference_rule': 'NULL', 'timing_rule': 'COMPLETED_MS', 'http_status_rule': 'NON_2XX', 'transport_rule': 'COMPLETE'}, {'ledger_kind': 'CHILD', 'api': 'GET', 'slot_rule': 'ANY_ALLOWED', 'outcome': 'UNKNOWN', 'response_reason': 'PARSER_UNSUPPORTED', 'parser_profile': 'GROUP_GET_FULL_NEWS_V1', 'code_rule': 'NULL', 'snapshot_rule': 'NULL', 'reference_rule': 'NULL', 'timing_rule': 'COMPLETED_MS', 'http_status_rule': '2XX', 'transport_rule': 'COMPLETE'}, {'ledger_kind': 'CHILD', 'api': 'GET', 'slot_rule': 'ANY_ALLOWED', 'outcome': 'UNKNOWN', 'response_reason': 'SECRET_REFLECTION', 'parser_profile': 'GROUP_GET_FULL_NEWS_V1', 'code_rule': 'NULL', 'snapshot_rule': 'NULL', 'reference_rule': 'NULL', 'timing_rule': 'COMPLETED_MS', 'http_status_rule': '2XX', 'transport_rule': 'COMPLETE'}, {'ledger_kind': 'CHILD', 'api': 'GET', 'slot_rule': 'ANY_ALLOWED', 'outcome': 'UNKNOWN', 'response_reason': 'NO_COMPLETE_TRANSPORT', 'parser_profile': 'NONE', 'code_rule': 'NULL', 'snapshot_rule': 'NULL', 'reference_rule': 'NULL', 'timing_rule': 'COMPLETED_OR_UNQUALIFIED', 'http_status_rule': 'NULL', 'transport_rule': 'NO_QUALIFIED_RESPONSE'}, {'ledger_kind': 'CHILD', 'api': 'GET', 'slot_rule': 'ANY_ALLOWED', 'outcome': 'UNKNOWN', 'response_reason': 'SNAPSHOT_UNSAFE', 'parser_profile': 'GROUP_GET_FULL_NEWS_V1', 'code_rule': 'NULL', 'snapshot_rule': 'NULL', 'reference_rule': 'NULL', 'timing_rule': 'COMPLETED_MS', 'http_status_rule': '2XX', 'transport_rule': 'COMPLETE'}, {'ledger_kind': 'CHILD', 'api': 'GET', 'slot_rule': 'ANY_ALLOWED', 'outcome': 'UNKNOWN', 'response_reason': 'TIMING_UNQUALIFIED_WITH_SNAPSHOT', 'parser_profile': 'GROUP_GET_FULL_NEWS_V1', 'code_rule': 'NULL', 'snapshot_rule': 'GET_FULL', 'reference_rule': 'NULL', 'timing_rule': 'UNQUALIFIED', 'http_status_rule': '2XX', 'transport_rule': 'COMPLETE'}, {'ledger_kind': 'CHILD', 'api': 'GET', 'slot_rule': 'ANY_ALLOWED', 'outcome': 'UNKNOWN', 'response_reason': 'TIMING_UNQUALIFIED', 'parser_profile': 'GROUP_GET_FULL_NEWS_V1', 'code_rule': 'NULL', 'snapshot_rule': 'NULL', 'reference_rule': 'NULL', 'timing_rule': 'UNQUALIFIED', 'http_status_rule': 'COMPLETE_ANY_STATUS', 'transport_rule': 'COMPLETE'}, {'ledger_kind': 'CHILD', 'api': 'GET', 'slot_rule': 'NON_OLD_INVALID_ONLY', 'outcome': 'KNOWN_REJECTED', 'response_reason': 'TIMING_UNQUALIFIED_REJECTION', 'parser_profile': 'GROUP_GET_FULL_NEWS_V1', 'code_rule': 'NONZERO_S32', 'snapshot_rule': 'NULL', 'reference_rule': 'NULL', 'timing_rule': 'UNQUALIFIED', 'http_status_rule': '2XX', 'transport_rule': 'COMPLETE'}, {'ledger_kind': 'CHILD', 'api': 'DELETE', 'slot_rule': 'ANY_ALLOWED', 'outcome': 'UNKNOWN', 'response_reason': 'HTTP_NON_SUCCESS', 'parser_profile': 'GROUP_DELETE_EXPLICIT_ACK_V1', 'code_rule': 'NULL', 'snapshot_rule': 'NULL', 'reference_rule': 'NULL', 'timing_rule': 'COMPLETED_MS', 'http_status_rule': 'NON_2XX', 'transport_rule': 'COMPLETE'}, {'ledger_kind': 'CHILD', 'api': 'DELETE', 'slot_rule': 'ANY_ALLOWED', 'outcome': 'UNKNOWN', 'response_reason': 'PARSER_UNSUPPORTED', 'parser_profile': 'GROUP_DELETE_EXPLICIT_ACK_V1', 'code_rule': 'NULL', 'snapshot_rule': 'NULL', 'reference_rule': 'NULL', 'timing_rule': 'COMPLETED_MS', 'http_status_rule': '2XX', 'transport_rule': 'COMPLETE'}, {'ledger_kind': 'CHILD', 'api': 'DELETE', 'slot_rule': 'ANY_ALLOWED', 'outcome': 'UNKNOWN', 'response_reason': 'SECRET_REFLECTION', 'parser_profile': 'GROUP_DELETE_EXPLICIT_ACK_V1', 'code_rule': 'NULL', 'snapshot_rule': 'NULL', 'reference_rule': 'NULL', 'timing_rule': 'COMPLETED_MS', 'http_status_rule': '2XX', 'transport_rule': 'COMPLETE'}, {'ledger_kind': 'CHILD', 'api': 'DELETE', 'slot_rule': 'ANY_ALLOWED', 'outcome': 'UNKNOWN', 'response_reason': 'NO_COMPLETE_TRANSPORT', 'parser_profile': 'NONE', 'code_rule': 'NULL', 'snapshot_rule': 'NULL', 'reference_rule': 'NULL', 'timing_rule': 'COMPLETED_OR_UNQUALIFIED', 'http_status_rule': 'NULL', 'transport_rule': 'NO_QUALIFIED_RESPONSE'}, {'ledger_kind': 'CHILD', 'api': 'DELETE', 'slot_rule': 'ANY_ALLOWED', 'outcome': 'UNKNOWN', 'response_reason': 'TIMING_UNQUALIFIED', 'parser_profile': 'GROUP_DELETE_EXPLICIT_ACK_V1', 'code_rule': 'NULL', 'snapshot_rule': 'NULL', 'reference_rule': 'NULL', 'timing_rule': 'UNQUALIFIED', 'http_status_rule': 'COMPLETE_ANY_STATUS', 'transport_rule': 'COMPLETE'}, {'ledger_kind': 'CHILD', 'api': 'DELETE', 'slot_rule': 'ANY_ALLOWED', 'outcome': 'ACK_OK', 'response_reason': 'DELETE_ACK_TIMING_UNQUALIFIED', 'parser_profile': 'GROUP_DELETE_EXPLICIT_ACK_V1', 'code_rule': 'EXACT_0', 'snapshot_rule': 'NULL', 'reference_rule': 'NULL', 'timing_rule': 'UNQUALIFIED', 'http_status_rule': '2XX', 'transport_rule': 'COMPLETE'}, {'ledger_kind': 'CHILD', 'api': 'DELETE', 'slot_rule': 'ANY_ALLOWED', 'outcome': 'KNOWN_REJECTED', 'response_reason': 'TIMING_UNQUALIFIED_REJECTION', 'parser_profile': 'GROUP_DELETE_EXPLICIT_ACK_V1', 'code_rule': 'NONZERO_S32', 'snapshot_rule': 'NULL', 'reference_rule': 'NULL', 'timing_rule': 'UNQUALIFIED', 'http_status_rule': '2XX', 'transport_rule': 'COMPLETE'}, {'ledger_kind': 'CHILD', 'api': 'ADD', 'slot_rule': 'ANY_ALLOWED', 'outcome': 'UNKNOWN', 'response_reason': 'HTTP_NON_SUCCESS', 'parser_profile': 'GROUP_ADD_REFERENCE_V1', 'code_rule': 'NULL', 'snapshot_rule': 'NULL', 'reference_rule': 'NULL', 'timing_rule': 'COMPLETED_MS', 'http_status_rule': 'NON_2XX', 'transport_rule': 'COMPLETE'}, {'ledger_kind': 'CHILD', 'api': 'ADD', 'slot_rule': 'ANY_ALLOWED', 'outcome': 'UNKNOWN', 'response_reason': 'PARSER_UNSUPPORTED', 'parser_profile': 'GROUP_ADD_REFERENCE_V1', 'code_rule': 'NULL', 'snapshot_rule': 'NULL', 'reference_rule': 'NULL', 'timing_rule': 'COMPLETED_MS', 'http_status_rule': '2XX', 'transport_rule': 'COMPLETE'}, {'ledger_kind': 'CHILD', 'api': 'ADD', 'slot_rule': 'ANY_ALLOWED', 'outcome': 'UNKNOWN', 'response_reason': 'SECRET_REFLECTION', 'parser_profile': 'GROUP_ADD_REFERENCE_V1', 'code_rule': 'NULL', 'snapshot_rule': 'NULL', 'reference_rule': 'NULL', 'timing_rule': 'COMPLETED_MS', 'http_status_rule': '2XX', 'transport_rule': 'COMPLETE'}, {'ledger_kind': 'CHILD', 'api': 'ADD', 'slot_rule': 'ANY_ALLOWED', 'outcome': 'UNKNOWN', 'response_reason': 'NO_COMPLETE_TRANSPORT', 'parser_profile': 'NONE', 'code_rule': 'NULL', 'snapshot_rule': 'NULL', 'reference_rule': 'NULL', 'timing_rule': 'COMPLETED_OR_UNQUALIFIED', 'http_status_rule': 'NULL', 'transport_rule': 'NO_QUALIFIED_RESPONSE'}, {'ledger_kind': 'CHILD', 'api': 'ADD', 'slot_rule': 'ANY_ALLOWED', 'outcome': 'UNKNOWN', 'response_reason': 'TIMING_UNQUALIFIED', 'parser_profile': 'GROUP_ADD_REFERENCE_V1', 'code_rule': 'NULL', 'snapshot_rule': 'NULL', 'reference_rule': 'NULL', 'timing_rule': 'UNQUALIFIED', 'http_status_rule': 'COMPLETE_ANY_STATUS', 'transport_rule': 'COMPLETE'}, {'ledger_kind': 'CHILD', 'api': 'ADD', 'slot_rule': 'ANY_ALLOWED', 'outcome': 'KNOWN_SUCCESS', 'response_reason': 'ADD_REFERENCE_TIMING_UNQUALIFIED', 'parser_profile': 'GROUP_ADD_REFERENCE_V1', 'code_rule': 'NULL', 'snapshot_rule': 'NULL', 'reference_rule': 'VALID_REFERENCE', 'timing_rule': 'UNQUALIFIED', 'http_status_rule': 'EXACT_200', 'transport_rule': 'COMPLETE'}, {'ledger_kind': 'CHILD', 'api': 'ADD', 'slot_rule': 'ANY_ALLOWED', 'outcome': 'UNKNOWN', 'response_reason': 'TIMING_UNQUALIFIED_REJECTION', 'parser_profile': 'GROUP_ADD_REFERENCE_V1', 'code_rule': 'NONZERO_S32', 'snapshot_rule': 'NULL', 'reference_rule': 'NULL', 'timing_rule': 'UNQUALIFIED', 'http_status_rule': '2XX', 'transport_rule': 'COMPLETE'}, {'ledger_kind': 'CHILD', 'api': 'ADD', 'slot_rule': 'ANY_ALLOWED', 'outcome': 'UNKNOWN', 'response_reason': 'ADD_HTTP_STATUS_UNSUPPORTED', 'parser_profile': 'GROUP_ADD_REFERENCE_V1', 'code_rule': 'NULL', 'snapshot_rule': 'NULL', 'reference_rule': 'NULL', 'timing_rule': 'COMPLETED_MS', 'http_status_rule': '2XX_EXCEPT_200', 'transport_rule': 'COMPLETE'}, {'ledger_kind': 'CHILD', 'api': 'GET', 'slot_rule': 'OLD_INVALID_ONLY', 'outcome': 'KNOWN_REJECTED', 'response_reason': 'TIMING_UNQUALIFIED_REJECTION', 'parser_profile': 'GROUP_GET_FULL_NEWS_V1', 'code_rule': 'NONZERO_S32_EXCEPT_40007', 'snapshot_rule': 'NULL', 'reference_rule': 'NULL', 'timing_rule': 'UNQUALIFIED', 'http_status_rule': '2XX', 'transport_rule': 'COMPLETE'}, {'ledger_kind': 'CHILD', 'api': 'GET', 'slot_rule': 'OLD_INVALID_ONLY', 'outcome': 'UNKNOWN', 'response_reason': 'TIMING_UNQUALIFIED_REJECTION', 'parser_profile': 'GROUP_GET_FULL_NEWS_V1', 'code_rule': 'EXACT_40007', 'snapshot_rule': 'NULL', 'reference_rule': 'NULL', 'timing_rule': 'UNQUALIFIED', 'http_status_rule': '2XX', 'transport_rule': 'COMPLETE'}]
