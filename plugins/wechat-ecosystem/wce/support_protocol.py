"""Separate app and conversation routes for opt-in support."""
from copy import deepcopy
from pathlib import Path
import time

from .contracts import WCEError
from .own_connection_registry import MembershipProofError
from .prepared_contracts import strict_validate
from .tools import schema
from .support_feedback import Support
from .support_diagnostics import RESULTS, CODES, PRESERVATION_FIELDS, OPERATION_PHASES
from .x_api import X_RESPONSE_ERROR_KINDS, XResponseUnknown

ACTION = 'wce.ui.support.action'
PREVIEW = 'openahoy.feedback.preview'
SEND = 'openahoy.feedback.submit'
STATUS = 'openahoy.feedback.status'
RECEIPT = {'report_id': {'type':'string','pattern':'^[a-f0-9]{32}$'},
           'digest': {'type':'string','pattern':'^[a-f0-9]{64}$'}}
CHAT_SPECS = {
    PREVIEW: schema({'description': {'type':'string','maxLength':4000}},
                    {'platform': {'type':'string','enum':['wechat','x','general','updates']}}),
    SEND: schema(RECEIPT | {'confirmed': {'type':'boolean','const':True}}),
    STATUS: schema(RECEIPT),
}
CHAT_DESCRIPTIONS = {
    PREVIEW: 'Prepare a local OpenAhoy feedback preview with sanitized diagnostics. Use only the relevant issue summary. This does not send anything.',
    SEND: 'Submit the existing OpenAhoy feedback preview. Use only when the user explicitly asked to submit this feedback. May open a public GitHub Issue. Reuse the exact preview receipt. If the result is uncertain, use status.',
    STATUS: 'Check the original conversation feedback receipt. Returns the actual Issue URL, a GitHub draft link, or the current submission state. Does not create an Issue.',
}
# readOnlyHint does not exclude refresh-token rotation or metadata writes.
LOCAL_ONLY_TOOLS=frozenset({PREVIEW,STATUS,'own.connections.list','x.connections.list','own.drafts.current.read','own.drafts.current.status'})


def descriptor():
    return {'name':ACTION,'title':'OpenAhoy 反馈与脱敏诊断',
        'description':'App-only local support preview/export and explicit user-clicked GitHub Issue submission. Never auto-sends logs. No account/configuration/publication mutation.',
        'inputSchema':{'type':'object','properties':{'operation':{'type':'string','enum':['READ','PREVIEW','DIAGNOSTICS','SEND','STATUS','OPEN','EXPORT']},'arguments':{'type':'object'}},'required':['operation','arguments'],'additionalProperties':False},
        'outputSchema':{'type':'object'},'annotations':{'readOnlyHint':False,'destructiveHint':False,'openWorldHint':True,'idempotentHint':False},'_meta':{'ui':{'visibility':['app']}}}


class SupportRouter:
    def __init__(self,inner,*,registry,version=None,support=None,instrument=True):
        self.inner=inner
        self.instrument=instrument
        if version is None:
            from .own_plugin import _server_info
            version=_server_info()['version']
        from .own_connection_policy import registry_path
        self.support=support or Support(Path(registry if registry is not None else registry_path()).parent/'diagnostics',version=version)
        self.tool_names=frozenset(t['name']for t in inner.list_tools())|{ACTION,*CHAT_SPECS}

    def __getattr__(self,name):return getattr(self.inner,name)
    @property
    def _inline_probe_meta(self):return self.inner._inline_probe_meta
    @_inline_probe_meta.setter
    def _inline_probe_meta(self,value):self.inner._inline_probe_meta=value

    def list_tools(self):
        chat = [{'name':name,'description':CHAT_DESCRIPTIONS[name],'inputSchema':deepcopy(spec),
                 'annotations':{'readOnlyHint':False,'destructiveHint':False,
                                'openWorldHint':name!=PREVIEW,'idempotentHint':name!=PREVIEW}}
                for name,spec in CHAT_SPECS.items()]
        return deepcopy(self.inner.list_tools())+[descriptor(),*chat]

    def call(self,name,arguments):
        def invoke():
            if name == ACTION:
                return self._call(arguments)
            if name in CHAT_SPECS:
                return self._chat(name,arguments)
            return self.inner.call(name,arguments)
        return self.observe(name,invoke) if self.instrument else invoke()

    def observe(self,name,invoke,*,protocol_result=False):
        # The outermost formal router supplies the complete trusted descriptor
        # catalog. This function never retains inputs, raw responses or errors.
        effect='NONE' if name in getattr(self,'readonly_tools',()) else 'POSSIBLE'
        kind=None;details={}
        start=time.monotonic();state='RETURNED';code=None;site=None;http_status=None;wechat_code=None
        try:
            original=invoke()
            value=original.get('structuredContent') if protocol_result and type(original)is dict else original
            if protocol_result and type(original)is dict and original.get('isError')is True:state='TOOL_ERROR'
            if type(value)is dict:
                if type(value.get('state'))is str and value['state']in RESULTS:state=value['state']
                diagnostic=value.get('diagnostic')
                if type(diagnostic)is dict:
                    candidate=diagnostic.get('code')or diagnostic.get('reason')
                    if type(candidate)is str and candidate in CODES:code=candidate
                    http_status=diagnostic.get('http_status');wechat_code=diagnostic.get('wechat_code')
            if type(value)is dict:
                projection=outcome(value)
                if projection is not None:state,code=projection
                if type(value.get('error_code'))is int and value['error_code']!=0:wechat_code=value['error_code']
                if code=='PRESERVATION_MISMATCH':kind='LOCAL_COMPARISON';wechat_code=None
                if name in {'x.media.upload', 'x.attempt.status'} and value.get('kind')=='upload':
                    field='query_error_kind' if value.get('query_error') else 'error_kind'
                    failure_kind=value.get(field)
                    if type(failure_kind) is str and failure_kind in X_RESPONSE_ERROR_KINDS:
                        kind=failure_kind
                details=management_details(value)
                if details.get('candidate_created')is True:effect='POSSIBLE'
                if state=='UNKNOWN':effect='POSSIBLE'
            return original
        except Exception as error:
            state='TOOL_ERROR';candidate=getattr(error,'code',None);code=candidate if type(candidate)is str and candidate in CODES else 'UNCLASSIFIED_ERROR'
            kind=('CONTRACT_ERROR' if isinstance(error,WCEError) else 'TIMEOUT' if isinstance(error,TimeoutError) else 'ATTRIBUTE_ERROR' if isinstance(error,AttributeError) else 'TRANSPORT_ERROR' if isinstance(error,(OSError,EOFError)) else 'INTERNAL_ERROR')
            if isinstance(error, MembershipProofError):
                details['proof_check'] = error.check
            if isinstance(error, XResponseUnknown):
                kind=error.kind
            if kind=='TIMEOUT' and code=='UNCLASSIFIED_ERROR':code='PROCESS_TIMEOUT'
            frame=error.__traceback__
            while frame:
                path=Path(frame.tb_frame.f_code.co_filename)
                if path.parent==Path(__file__).parent:
                    site={'module':path.name,'function':frame.tb_frame.f_code.co_name,'line':frame.tb_lineno}
                frame=frame.tb_next
            raise
        finally:
            # This best-effort hook never sees argument values/raw responses.
            if code=='X_HTTP_402':
                http_status=402
            try:
                self.support.logs.emit('mcp','TOOL_CALL',state,
                    tool=name if name in self.tool_names else None,code=code,
                    elapsed_ms=min(3600000,int((time.monotonic()-start)*1000)),site=site,http_status=http_status,wechat_code=wechat_code,error_kind=kind,possible_side_effect=effect,**details)
            except Exception:
                pass

    def _chat(self, name, args):
        strict_validate(args, CHAT_SPECS[name])
        try:
            if name == PREVIEW:
                fields = dict(description=args['description'], steps='', expected='', actual='')
                report = self.support.preview(fields, args.get('platform', 'general'), source='conversation')
                return {key:report[key] for key in ('report_id','digest','state','repository','title','body')}
            operation = self.support.send if name == SEND else self.support.status
            return operation(args['report_id'], args['digest'], source='conversation')
        except ValueError:
            raise WCEError('SUPPORT_REQUEST_INVALID') from None

    def _call(self,value):
        try:
            if type(value)is not dict or set(value)!={'operation','arguments'} or type(value['arguments'])is not dict:
                raise ValueError()
            op=value['operation'];args=value['arguments']
            if op in {'READ','DIAGNOSTICS'} and not args:
                return self.support.read()if op=='READ'else self.support.diagnostics()
            if op=='PREVIEW'and set(args)=={'fields','platform'}:
                if type(args['fields'])is not dict or any(type(v)is not str or len(v)>4000 for v in args['fields'].values()):raise ValueError()
                return self.support.preview(args['fields'],args['platform'])
            if op in {'SEND','STATUS','OPEN'}and set(args)=={'report_id','digest'}:
                return (self.support.send if op=='SEND'else self.support.open_report if op=='OPEN'else self.support.status)(**args)
            if op=='EXPORT'and set(args)=={'report_id','digest','action'}:
                return self.support.export(**args)
            raise ValueError()
        except ValueError:
            raise WCEError('SUPPORT_REQUEST_INVALID')from None

    def update_resource(self,value,uri=None):
        from .support_ui import decorate
        return decorate(self.inner.update_resource(value,uri)if uri else self.inner.update_resource(value))


def outcome(value):
    """Classify fixed result states without copying business fields."""
    state=value.get('state')
    if state in ('REJECTED','FAILED') and value.get('error')=='X_HTTP_402':
        return 'TOOL_ERROR','X_HTTP_402'
    if value.get('media_protocol')=='X_V2_CHUNKED' or value.get('kind')=='upload' and state=='RESULT_UNKNOWN':
        code=value.get('query_error')or value.get('error')
        safe_code=code if type(code)is str and code in CODES else None
        if state=='RESULT_UNKNOWN':return 'UNKNOWN',safe_code or 'X_RESPONSE_UNKNOWN'
        if state=='SOURCE_UNAVAILABLE':return 'TOOL_ERROR','X_MEDIA_SOURCE_UNAVAILABLE'
        if state in {'REJECTED','EXPIRED'}:return 'TOOL_ERROR',safe_code or 'PLATFORM_ERROR'
        if value.get('query_error')is not None:return 'CHECK_UNAVAILABLE',safe_code or 'X_RESPONSE_UNKNOWN'
    unknown={'ADD_UNKNOWN','DELETE_UNKNOWN','RESULT_UNKNOWN','ABSENT_CAUSE_UNDETERMINED','TRANSPORT_UNDETERMINED','INLINE_BINDING_RESULT_UNDETERMINED'}
    failed={'ADD_REJECTED','DELETE_REJECTED','PRESERVATION_MISMATCH','SOURCE_CHANGED','SOURCE_UNAVAILABLE','REJECTED','FAILED'}
    if type(state)is str and state in unknown:return 'UNKNOWN','TRANSPORT_UNDETERMINED'
    if state=='PRESERVATION_MISMATCH':return 'TOOL_ERROR','PRESERVATION_MISMATCH'
    if state=='SOURCE_CHANGED':return 'TOOL_ERROR','CURRENT_DRAFT_SOURCE_CHANGED'
    if state=='SOURCE_UNAVAILABLE':return 'TOOL_ERROR','CURRENT_DRAFT_SOURCE_UNAVAILABLE'
    if type(state)is str and state in failed:return 'TOOL_ERROR','PLATFORM_ERROR'
    if value.get('readback_state')=='MISMATCH':return 'TOOL_ERROR','PLATFORM_ERROR'
    if value.get('isError') is True:return 'TOOL_ERROR','UNCLASSIFIED_ERROR'
    auth=value.get('authorization')
    if type(auth)is dict and auth.get('state')in ('FAILED','DENIED'):
        result=auth.get('result');code=result.get('error')if type(result)is dict else None
        return 'TOOL_ERROR',code if type(code)is str and code in CODES else 'UNCLASSIFIED_ERROR'
    # Fixed local retirement projection only; never inspect arbitrary article data.
    for field in ('source_containers','retirements'):
        for row in value.get(field,[]) if type(value.get(field))is list else []:
            if type(row)is dict and type(row.get('state'))is str and row['state']in unknown:return 'UNKNOWN','TRANSPORT_UNDETERMINED'
    return None


def management_details(value):
    """Fixed technical projection; never retain user-supplied field names."""
    out={}
    phase=value.get('phase')
    if type(phase)is str and phase in OPERATION_PHASES:out['operation_phase']=phase
    candidate=value.get('candidate_created')
    if type(candidate)is bool:out['candidate_created']=candidate
    preservation=value.get('preservation')
    if type(preservation)is dict and type(preservation.get('different_fields'))is list:
        fields=[]
        for item in preservation['different_fields']:
            field=item.split('.',1)[-1]if type(item)is str else 'other'
            fields.append(field if field in PRESERVATION_FIELDS else 'other')
        out.update(different_fields=sorted(set(fields)),difference_count=len(fields))
    rows=value.get('source_containers')
    if type(rows)is list:
        out.update(source_container_count=len(rows),source_retired_count=sum(type(r)is dict and r.get('state')=='DELETED'for r in rows))
    return out
