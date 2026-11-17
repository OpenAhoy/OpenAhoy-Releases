"""Local opt-in support surface; closed event projection, never raw exceptions.

Four 256 KiB files bound diagnostic storage, not platform/account activity.
Failure to record is always isolated from the original tool result.
"""
from datetime import datetime, timezone
import fcntl
import json
import os
from pathlib import Path
import re
import stat
import time
import uuid
from .own_connection_registry import PROOF_CHECKS
from .own_binding_failure import SAFE_ERRORS as BINDING_ERROR_CODES
from .video_relay import SUBMIT_DIAGNOSTIC_CODES, TRANSPORT_PHASES, safe_submit_response
from .openai_gif_api import DIAGNOSTICS as GIF_DIAGNOSTICS, TRANSPORT_PHASES as GIF_TRANSPORT_PHASES

MAX_BYTES = 256 * 1024
FILES = 4
RESULTS = frozenset({'RETURNED', 'TOOL_ERROR', 'CONNECTED', 'BOUND_IDLE', 'DISCONNECTED',
    'ACTION_REQUIRED', 'BUSY', 'UNKNOWN', 'CHECK_UNAVAILABLE', 'UPDATE_AVAILABLE', 'VERIFY_REQUIRED',
    'FAILED', 'LOADED', 'INSTALLED_RELOAD_REQUIRED',
    'UP_TO_DATE', 'DEVELOPMENT_AHEAD', 'PREPARED', 'SUBMITTED', 'WEB_DRAFT', 'PENDING','UPLOADING','PROCESSING','EXPIRED'})
CODES = frozenset({'UNAVAILABLE', 'INVALID_VERSION', 'SOURCE_REWRITTEN', 'NO_STABLE_TAGS',
    'INVALID_TAG_RESPONSE', 'GIT_UNAVAILABLE', 'LOCAL_PROCESS_ERROR', 'PROCESS_TIMEOUT',
    'NETWORK_TIMEOUT', 'NETWORK_DNS', 'NETWORK_CONNECT', 'AUTH_REQUIRED', 'ACCESS_UNAVAILABLE',
    'TLS_FAILED', 'REDIRECT_REFUSED', 'GIT_FAILED', 'CARRIER_LIMIT', 'UNCLASSIFIED_ERROR'})
CODES = CODES | frozenset({'OWN_STATE_CORRUPT','OWN_CONNECTION_UNAVAILABLE','OWN_LEASE_UNAVAILABLE','OWN_REVIEW_REQUIRED','OWN_SOURCE_CHANGED','RULES_VERSION_CONFLICT','RULES_WRITE_RESULT_UNKNOWN','PARSED_SUCCESS','PLATFORM_ERROR','TRANSPORT_UNDETERMINED','NON_SUCCESS_HTTP','NOT_RECORDED'})
CODES = CODES | BINDING_ERROR_CODES | {'INLINE_BINDING_RESULT_UNDETERMINED','X_AUTHORIZATION_ACCOUNT_MISMATCH','X_AUTHORIZATION_SESSION_MISMATCH','X_AUTHORIZATION_IN_PROGRESS','X_AUTHORIZATION_DENIED','X_AUTHORIZATION_RESULT_UNKNOWN','X_DIFFERENT_ACCOUNT_NOT_REPLACED','CURRENT_DRAFT_OPERATION_NOT_FOUND','CONNECTION_NOT_COMMITTED','CONNECTION_COMMITTED_IDENTITY_CHANGED'}
CODES = CODES | {'CONNECTION_ENTRY_UNAVAILABLE','CONNECTION_VOLUME_WITNESS_UNVERIFIED',
                 'CONNECTION_VOLUME_WITNESS_CHANGED','CONNECTION_VOLUME_CHANGED',
                 'CONNECTION_RECOVERY_WITNESS_UNAVAILABLE','UPDATE_ACTIVITY_UNVERIFIED',
                 'UPDATE_BUSINESS_BUSY'}
CODES=CODES|{'PRESERVATION_MISMATCH','CURRENT_DRAFT_SOURCE_CHANGED','CURRENT_DRAFT_SOURCE_UNAVAILABLE','X_MEDIA_PROCESSING_FAILED','X_MEDIA_SOURCE_UNAVAILABLE','X_MEDIA_EXPIRED','X_MEDIA_RESPONSE_INCOMPLETE','X_MEDIA_IDENTITY_MISMATCH','X_MEDIA_SEGMENT_INVALID','X_RESPONSE_UNKNOWN','X_HTTP_400','X_HTTP_401','X_HTTP_402','X_HTTP_403','X_HTTP_408','X_HTTP_413','X_HTTP_415','X_HTTP_422','X_HTTP_429','X_HTTP_500','X_HTTP_502','X_HTTP_503','X_HTTP_504'}
CODES = CODES | SUBMIT_DIAGNOSTIC_CODES | GIF_DIAGNOSTICS
PRESERVATION_FIELDS=frozenset({'article_count','article_type','title','author','digest','content','content_source_url','thumb_media_id','thumb_url','cover_info','need_open_comment','only_fans_can_comment','show_cover_pic','image_info','product_info','other'})
OPERATION_PHASES=frozenset({'PREPARED','READ_SOURCE','ADD','VERIFY_NEW_GROUP','RETIRE_SOURCES','COMPLETED','INIT_UNKNOWN','APPENDING','APPEND_UNKNOWN','FINALIZE_UNKNOWN','PROCESSING','READY'}) | TRANSPORT_PHASES | GIF_TRANSPORT_PHASES
MODULES = frozenset({'mcp', 'updates', 'support', 'binding'})
STAGES = frozenset({'TOOL_CALL', 'SOURCE_CHECK', 'TAG_READ', 'PREVIEW', 'SEND', 'QUERY', 'VALIDATION'})


def private_directory(path):
    path = Path(path)
    if not path.is_absolute() or '..' in path.parts:
        raise ValueError('SUPPORT_DIRECTORY_UNAVAILABLE')
    path.mkdir(mode=0o700, parents=False, exist_ok=True)
    s = path.lstat()
    if not stat.S_ISDIR(s.st_mode) or s.st_uid != os.getuid() or s.st_mode & 0o077:
        raise ValueError('SUPPORT_DIRECTORY_UNAVAILABLE')
    return path


def private_file(path, flags):
    fd = os.open(path, flags | os.O_NOFOLLOW, 0o600)
    try:
        s = os.fstat(fd)
        if not stat.S_ISREG(s.st_mode) or s.st_uid != os.getuid() or s.st_nlink != 1 or s.st_mode & 0o077:
            raise ValueError('SUPPORT_FILE_UNAVAILABLE')
        return fd
    except BaseException:
        os.close(fd)
        raise


class Diagnostics:
    def __init__(self, root):
        self.root = Path(root)

    @staticmethod
    def event(module, stage, result, *, tool=None, code=None, elapsed_ms=None,
              http_status=None, wechat_code=None, site=None, error_kind=None, possible_side_effect=None, operation_phase=None, different_fields=None, difference_count=None, candidate_created=None, source_container_count=None, source_retired_count=None, proof_check=None, relay_response=None):
        if module not in MODULES or stage not in STAGES or result not in RESULTS:
            raise ValueError('SUPPORT_EVENT_INVALID')
        value = {'schema': 1, 'at': datetime.now(timezone.utc).isoformat(),
            'report_id': uuid.uuid4().hex, 'module': module, 'stage': stage, 'result': result}
        # tool is selected from the router's immutable descriptor names.
        if tool is not None:
            if type(tool) is not str or not re.fullmatch(r'(?:(?:own|wce|x|video|image|audio)\.[a-z._]+|openahoy\.feedback\.(?:preview|submit|status))', tool):
                raise ValueError('SUPPORT_EVENT_INVALID')
            value['tool'] = tool
        if code in CODES:
            value['code'] = code
        for key, number, limit in [('elapsed_ms', elapsed_ms, 3600000), ('http_status', http_status, 599)]:
            if type(number) is int and 0 <= number <= limit:
                value[key] = number
        if type(wechat_code) is int and -(2**31) <= wechat_code < 2**31:
            value['wechat_code'] = wechat_code
        if type(site) is dict and set(site)=={'module','function','line'} and type(site['module'])is str and re.fullmatch(r'[a-z_]+\.py',site['module']) and type(site['function'])is str and re.fullmatch(r'[A-Za-z_][A-Za-z_0-9]{0,63}',site['function']) and type(site['line'])is int and 0<site['line']<100000:
            value['site']=site
        if error_kind in {'CONTRACT_ERROR','TIMEOUT','ATTRIBUTE_ERROR','TRANSPORT_ERROR','INTERNAL_ERROR','LOCAL_COMPARISON','RESPONSE_DECODE_ERROR'}:value['error_kind']=error_kind
        if possible_side_effect in {'NONE','POSSIBLE'}:value['possible_side_effect']=possible_side_effect
        if operation_phase in OPERATION_PHASES:value['operation_phase']=operation_phase
        if type(different_fields)is list:
            safe=sorted({field for field in different_fields if type(field)is str and field in PRESERVATION_FIELDS})
            if safe:value['different_fields']=safe
        if type(difference_count)is int and 0<=difference_count<2**31:value['difference_count']=difference_count
        if type(candidate_created)is bool:value['candidate_created']=candidate_created
        for key,number in [('source_container_count',source_container_count),('source_retired_count',source_retired_count)]:
            if type(number)is int and 0<=number<=8:value[key]=number
        if tool in {'video.relay.generation.submit', 'video.ark.generation.status'} and code in SUBMIT_DIAGNOSTIC_CODES:
            if safe := safe_submit_response(relay_response):
                value['relay_response'] = safe
        if type(proof_check) is str and proof_check in PROOF_CHECKS:
            value['proof_check'] = proof_check
        return value

    def emit(self, module, stage, result, **fields):
        try:
            value = self.event(module, stage, result, **fields)
            raw = (json.dumps(value, ensure_ascii=False, separators=(',', ':'))+'\n').encode()
            root = private_directory(self.root)
            lock = private_file(root/'events.lock', os.O_WRONLY | os.O_CREAT)
            try:
                fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
                current = root/'events.jsonl'
                fd = private_file(current, os.O_WRONLY | os.O_APPEND | os.O_CREAT)
                try:
                    rotate = os.fstat(fd).st_size + len(raw) > MAX_BYTES
                finally:
                    os.close(fd)
                if rotate:
                    for index in range(FILES-1, -1, -1):
                        source = root/('events.jsonl' if index == 0 else f'events.{index}.jsonl')
                        if not source.exists() and not source.is_symlink():
                            continue
                        check = private_file(source, os.O_RDONLY); os.close(check)
                        if index == FILES-1:
                            source.unlink()
                        else:
                            source.rename(root/f'events.{index+1}.jsonl')
                fd = private_file(current, os.O_WRONLY | os.O_APPEND | os.O_CREAT)
                try:
                    os.write(fd, raw)
                finally:
                    os.close(fd)
            finally:
                os.close(lock)
            return True
        except Exception:
            return False

    def snapshot(self):
        result = []
        try:
            for index in range(FILES-1, -1, -1):
                p = self.root/('events.jsonl' if index == 0 else f'events.{index}.jsonl')
                if not p.exists() and not p.is_symlink():
                    continue
                fd = private_file(p, os.O_RDONLY)
                try:
                    raw = os.read(fd, MAX_BYTES+1)
                finally:
                    os.close(fd)
                if len(raw) > MAX_BYTES:
                    continue
                for line in raw.splitlines():
                    try:
                        row = json.loads(line)
                        allowed = {'schema','at','report_id','module','stage','result','tool','code','elapsed_ms','http_status','wechat_code','site','error_kind','possible_side_effect','operation_phase','different_fields','difference_count','candidate_created','source_container_count','source_retired_count','proof_check','relay_response'}
                        if type(row) is not dict or set(row)-allowed or row.get('schema') != 1:
                            continue
                        if not re.fullmatch('[a-f0-9]{32}', row['report_id']) or not re.fullmatch(r'[0-9T:.+Z-]{20,40}', row['at']):
                            continue
                        safe = self.event(row['module'],row['stage'],row['result'],
                            **{k:row[k] for k in allowed-{'schema','at','report_id','module','stage','result'} if k in row})
                        safe.update(at=row['at'], report_id=row['report_id']); result.append(safe)
                    except Exception:
                        continue
            # Preserve recent distinct failures across normal polling/chunk reads.
            # Bounded by the same existing files, not a second log or service.
            failures={};failure_ids=set()
            for row in result:
                if row.get('code')not in {None,'PARSED_SUCCESS'} or row['result']in {'TOOL_ERROR','CHECK_UNAVAILABLE','UNKNOWN','ACTION_REQUIRED'}:
                    failure_ids.add(row['report_id'])
                    key=json.dumps({k:row[k]for k in ('module','stage','tool','result','code','http_status','site','error_kind','possible_side_effect','operation_phase','different_fields','candidate_created','relay_response')if k in row},sort_keys=True)
                    failures.pop(key,None);failures[key]=row
            selected={row['report_id']for row in list(failures.values())[-20:]+[row for row in result if row['report_id']not in failure_ids][-180:]}
            return {'schema': 1, 'events': [row for row in result if row['report_id']in selected], 'storage': 'LOCAL_ONLY',
                'excluded': ['credentials','account_ids','article_content','responses','absolute_paths','raw_exceptions']}
        except Exception:
            return {'schema': 1, 'events': [], 'storage': 'UNAVAILABLE'}
