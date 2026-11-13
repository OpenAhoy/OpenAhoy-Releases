"""Revision orchestration for an already registered, trusted single Case.

The concrete current-policy/source registrar and official provider are separate
integration requirements. No public constructor/tool creates Case authority here.
A provider may only send bounded requests to fixed official get/update routes;
its current() is read-only, token() is internal, and send() never retries.
"""
from copy import deepcopy
from dataclasses import dataclass,field
from functools import wraps
from hashlib import sha256

from .contracts import WCEError
from .service import canonical,digest
from . import draft_revision_wire as wire


# Transient diagnostic only: not persisted in schema5 or transport proofs.
_READ_PARSE_CODES = frozenset({
    'TRANSPORT_UNDETERMINED','NON_SUCCESS_HTTP','RESPONSE_SECRET_REFLECTION',
    'DRAFT_INVALID_JSON','INVALID_JSON_SHAPE','DRAFT_CODE_TYPE','UPLOAD_SECRET_UNAVAILABLE',
    'DRAFT_REVISION_GET_REJECTED','DRAFT_REVISION_REFERENCE_UNVERIFIED',
    'DRAFT_REVISION_NEWS_SHAPE','DRAFT_REVISION_PRESERVATION_FIELDS_MISSING',
    'DRAFT_REVISION_ARTICLE_TYPE_UNSUPPORTED','DRAFT_REVISION_COVER_UNVERIFIED',
    'DRAFT_REVISION_CONTENT_UNSUPPORTED','DRAFT_REVISION_TEMPORARY_URL_TYPE',
    'DRAFT_REVISION_COMMENT_UNVERIFIED','DRAFT_REVISION_COMPLEX_PROFILE_UNSUPPORTED',
    'DRAFT_REVISION_CANONICAL_SNAPSHOT_BOUND','DOCUMENT_INVALID_URL',
    'DOCUMENT_EDITORIAL_METADATA','INVALID_TOOL_ARGUMENTS'})
_EXCEPTION_DICT = BaseException.__dict__['__dict__']


def _unknown_read_diagnostic(ordinal):
    return {'phase':'READ_RESPONSE_PARSE','ordinal':ordinal,'reason':'UNDETERMINED',
            'http_status':None,'wechat_code':None}


def _read_failure_diagnostic(error,response,secret,ordinal):
    """Closed pure projection; never text/traceback, alternate parsing or authority."""
    result=_unknown_read_diagnostic(ordinal)
    try:
        if type(error) is WCEError:
            data=_EXCEPTION_DICT.__get__(error,BaseException)
            reason=dict.get(data,'code') if type(data) is dict else None
            if type(reason) is str and reason in _READ_PARSE_CODES:result['reason']=reason
        from .http_transport import HTTPResponse,MAX_BODY
        from .contracts import Secret
        if type(response) is not HTTPResponse:return result
        data=object.__getattribute__(response,'__dict__')
        if type(data) is not dict:return result
        status=dict.get(data,'status');body=dict.get(data,'body')
        if type(status) is int and 100<=status<=599:result['http_status']=status
        if type(body) is not bytes or not 0<len(body)<=MAX_BODY or type(secret) is not Secret:return result
        if type(Secret.__dict__['_Secret__value'].__get__(secret,Secret)) is not str:return result
        # Repeat only the original bounded strict JSON + secret reflection gate.
        # Non-2xx, malformed, reflected or unsupported values release no errcode.
        from .own_draft_wire import response_value
        value=response_value(response,secret)
        code=dict.get(value,'errcode') if type(value) is dict else None
        if type(code) is int and -(2**31)<=code<2**31 and code!=0:result['wechat_code']=code
    except Exception:
        pass
    return result


def hold(code='DRAFT_REVISION_EXECUTION_HOLD'):
    raise WCEError(code)


def bounded_failure(method):
    """No provider/source exception text or chained secret enters MCP output."""
    @wraps(method)
    def call(*args,**kwargs):
        from .draft_revision_native_source import SourceHold
        from .draft_revision_errors import source_failure,SOURCE_OUTCOMES
        try:return method(*args,**kwargs)
        except SourceHold as error:
            raise source_failure(error) from None
        except WCEError as error:
            # Only this module's closed, authored outcomes are released.
            allowed={'DRAFT_REVISION_TRUSTED_CONTEXT_REQUIRED','DRAFT_REVISION_CASE_CHANGED',
                'DRAFT_REVISION_ORIGINAL_DRAFT_CHANGED','DRAFT_REVISION_READ_BUDGET_EXHAUSTED',
                'DRAFT_REVISION_BASELINE_CHANGED','DRAFT_REVISION_INPUT_CHANGED',
                'DRAFT_REVISION_INPUT_BINDING_HOLD','DRAFT_REVISION_CASE_MISSING',
                'DRAFT_REVISION_LIVE_PROVIDER_UNAVAILABLE'} | SOURCE_OUTCOMES
            raise WCEError(error.code if error.code in allowed else 'DRAFT_REVISION_EXECUTION_HOLD') from None
        except Exception:raise WCEError('DRAFT_REVISION_EXECUTION_HOLD') from None
    return call


@dataclass(frozen=True)
class RevisionContext:
    """Private host input, never a model-supplied grant or machine thread ACL."""
    case:dict=field(repr=False)
    reference:str=field(repr=False)
    input_json:str=field(repr=False)
    current:object=field(repr=False)
    initial_matches:object=field(repr=False)
    execution_lock:object=field(repr=False)
    preservation:object=field(default=None,repr=False)
    publication_bridge:object=field(default=None,repr=False)


class DraftRevisionService:
    def __init__(self,store,context,provider):
        if type(context) is not RevisionContext:hold('DRAFT_REVISION_TRUSTED_CONTEXT_REQUIRED')
        self.store,self.context,self.provider=store,context,provider
        self.case_id=context.case['id']
        self.read_diagnostic=None

    def _official(self):
        from .draft_revision_provider import OfficialRevisionProvider
        return (type(self.provider) is OfficialRevisionProvider
            and OfficialRevisionProvider.matches(self.provider,self.store,self.context))

    def _input(self):
        from .publication_contract import strict_json
        value=strict_json(self.context.input_json.encode(),maximum=2*1024*1024)
        fields={'profile','binding','changes','image_relations','original_step_sha',
            'original_manifest_sha','new_manifest_sha','original_uploads_sha',
            'reference_sha','original_intent_sha','original_result_sha','target_basis'}
        profile=value.get('profile') if type(value) is dict else None
        if profile=='VERIFIED_DRAFT_REVISION_INPUT_V2':
            from .draft_revision_preservation import PreservationPlan,ChangedImagePlan
            fields|={'source_relation','preservation','source_binding_sha'}
            from .draft_revision_materialized_image import PROFILE as BOUND_IMAGE
            if type(value.get('source_relation')) is dict and value['source_relation'].get('profile')==BOUND_IMAGE:
                fields.add('image_upload')
            if (type(self.context.preservation) not in (PreservationPlan,ChangedImagePlan)
                    or self.context.preservation.evidence()!=value.get('preservation')):
                hold('DRAFT_REVISION_INPUT_BINDING_HOLD')
            if value['source_binding_sha']!=self.context.case['source_sha']:hold('DRAFT_REVISION_INPUT_BINDING_HOLD')
        elif self.context.preservation is not None:hold('DRAFT_REVISION_INPUT_BINDING_HOLD')
        if (type(value) is not dict or set(value)!=fields or canonical(value)!=self.context.input_json
                or profile not in {'VERIFIED_DRAFT_REVISION_INPUT_V1','VERIFIED_DRAFT_REVISION_INPUT_V2'}
                or digest(value)!=self.context.case['input_sha']
                or value['binding']!=self.context.case['binding']
                or value['reference_sha']!=self.context.case['target']
                or value['target_basis']!=self.context.case['target_basis']
                or sorted({value['original_manifest_sha'],value['new_manifest_sha']})!=value['target_basis']['MANIFEST']
                or value['original_step_sha']!=self.context.case['original_step']):hold('DRAFT_REVISION_INPUT_BINDING_HOLD')
        return value

    def _direct_bridge(self):
        from .draft_revision_direct_artifact import PROFILE as DIRECT_SOURCE
        from .draft_revision_materialized_image import PROFILE as BOUND_IMAGE
        value=self._input();relation=value.get('source_relation')
        if type(relation) is not dict or relation.get('profile') not in (DIRECT_SOURCE,BOUND_IMAGE):return None
        from .current_publication_revision_bridge import DirectPublicationBridge
        bridge=self.context.publication_bridge
        if (type(bridge) is not DirectPublicationBridge or bridge.case!=self.context.case
                or bridge.gate is not self.context.execution_lock
                or getattr(self.context.current,'__self__',None) is not bridge.adapter
                or not self._official() or self.provider.service is not bridge.service):
            hold('DRAFT_REVISION_TRUSTED_CONTEXT_REQUIRED')
        return bridge

    def _require_pending_adoption(self,state):
        from .draft_revision_materialized_image import PROFILE as BOUND_IMAGE
        relation=self._input().get('source_relation')
        if (type(relation) is dict and relation.get('profile')==BOUND_IMAGE
                and type(state.get('pending_adoption')) is not dict):
            hold('DRAFT_REVISION_PENDING_ADOPTION_UNAVAILABLE')

    def _expected(self,snapshot):
        value=self._input();changes=value['changes'];expected=wire.baseline_projection(snapshot)
        if self.context.preservation is not None:
            from .draft_revision_preservation import observe_original,expected_projection,expected_one_changed_projection,ChangedImagePlan
            plan=self.context.preservation
            observation=observe_original(plan.original_html,snapshot.rows()[0]['content'],plan.upload_urls)
            if type(plan) is ChangedImagePlan:
                expected=expected_one_changed_projection(expected,changes.get('content',plan.original_html),observation,plan)
            else:expected=expected_projection(expected,changes.get('content',plan.original_html),observation)
            expected['response']['news_item'][0].update({k:deepcopy(v) for k,v in changes.items() if k!='content'})
        else:expected['response']['news_item'][0].update(deepcopy(changes))
        return expected

    def _current(self):
        expected=self._input()
        if digest(self.context.reference)!=self.context.case['target']:hold()
        if self._official():
            from .draft_revision_provider import OfficialRevisionProvider
            from .draft_revision_store import OFFICIAL_PROVIDER
            result=OfficialRevisionProvider._checked_current(self.provider,self.store,self.context)
            if (type(result) is not tuple or len(result)!=2
                    or type(result[0]) is not dict or result[0]!=expected
                    or type(result[1]) is not dict
                    or result[1]['case']!=self.context.case
                    or result[1]['case']['provider_profile']!=OFFICIAL_PROVIDER):
                hold('DRAFT_REVISION_INPUT_BINDING_HOLD')
            self._require_pending_adoption(result[1])
            # The concrete provider performs the complete fresh source/input,
            # original proof/artifact, policy/token and final journal checks.
            # Repeating that work immediately beforehand adds no later fence.
            return result[1]
        # The concrete trusted adapter must freshly revalidate old proof/image
        # chain and source artifact and return the exact derived frozen input.
        # A no-op guard or a caller's role/source string cannot pass this check.
        if self.context.current()!=expected:hold('DRAFT_REVISION_INPUT_BINDING_HOLD')
        # The Case must already exist. A public prepare can never register it.
        with self.store.connection() as db:
            stored=self.store._state(db,self.case_id)
            if stored['case']!=self.context.case:hold('DRAFT_REVISION_CASE_CHANGED')
        self._require_pending_adoption(stored)
        # A real host-owned provider has exact account/cache/transport types and
        # requires consumed journal admissions. A flag/callback is insufficient.
        if not self._official() and getattr(self.provider,'synthetic',None) is not True:
            hold('DRAFT_REVISION_LIVE_PROVIDER_UNAVAILABLE')
        from .draft_revision_store import OFFICIAL_PROVIDER,SYNTHETIC_PROVIDER
        if stored['case']['provider_profile']!=(OFFICIAL_PROVIDER if self._official() else SYNTHETIC_PROVIDER):
            hold('DRAFT_REVISION_LIVE_PROVIDER_UNAVAILABLE')
        self.provider.current()
        return stored

    def _state(self):
        return self.store.state(self.case_id)

    def _read(self,phase):
        self._current()
        admission=self.store.allocate_read(self.case_id,phase)
        self._current()
        self.store.consume_admission(admission)
        snapshot=None;capture=None;diagnostic=None;parsing=False;response=None;secret=None
        try:
            # Only provider-internal credentials; never persisted or returned.
            if self._official():response,secret,capture=self.provider.read_admitted(admission)
            else:response,secret=self.provider.read(self.context.reference)
            parsing=True
            snapshot=wire.parse_get(response,secret,self.context.reference,
                synthetic=self.provider.synthetic)
        except Exception as error:
            if parsing:
                try:diagnostic=_read_failure_diagnostic(error,response,secret,admission.ordinal)
                except Exception:diagnostic=_unknown_read_diagnostic(admission.ordinal)
            # The consumed ordinal remains UNKNOWN. No raw exception is stored
            # or returned, and this does not create a new automatic GET retry.
            pass
        self.store.record_read(self.case_id,admission,snapshot,transport=capture)
        self._current()
        self.read_diagnostic=diagnostic
        return admission.ordinal,snapshot

    def _operation_result(self,result):
        diagnostic=self.read_diagnostic
        self.read_diagnostic=None
        if diagnostic is None:return result
        return dict(result,read_diagnostic=dict(diagnostic))

    def _prepare_observed(self,ordinal,snapshot):
        if snapshot is None:return self._operation_result(self.status())
        self._current()
        if not self.context.initial_matches(snapshot):hold('DRAFT_REVISION_ORIGINAL_DRAFT_CHANGED')
        # Full current preservation profile must support updating before PREPARED.
        changes=self._input()['changes']
        wire.update_payload(snapshot,changes,synthetic=self.provider.synthetic)
        expected=self._expected(snapshot)
        if len(expected['response']['news_item'])!=1:hold()
        self.store.prepared(self.case_id,ordinal,expected)
        bridge=self._direct_bridge()
        if bridge is not None:bridge.reserve()
        return self.status()

    @bounded_failure
    def prepare(self):
        with self.context.execution_lock():
            self.read_diagnostic=None
            state=self._current();current=state['revision']
            if current['state']=='PREPARING' and type(state.get('pending_adoption')) is dict:
                ordinal=len(state['pending_adoption']['reads'])
                with self.store.connection() as db:
                    checked=self.store._state(db,self.case_id)
                    if checked.get('pending_adoption')!=state['pending_adoption']:hold('DRAFT_REVISION_INPUT_CHANGED')
                    snapshot=self.store._read_snapshot(checked,ordinal)
                return self._prepare_observed(ordinal,snapshot)
            if current['state']!='PREPARING' or current['reads']:
                return self.status()  # Reentry never replenishes or repeats GET.
            ordinal,snapshot=self._read('BASELINE')
            return self._prepare_observed(ordinal,snapshot)

    @bounded_failure
    def execute(self):
        with self.context.execution_lock():
            self.read_diagnostic=None
            current=self._current()['revision']
            bridge=self._direct_bridge()
            if current['state']!='PREPARED' or current['writes']:
                if bridge is not None and type(current.get('effect')) is dict and current['effect'].get('matched') is True:
                    bridge.complete()
                return self.status()
            if bridge is not None:bridge.reserve()
            # Reserve enough of the fixed Case budget for pre-send and post-send.
            if current['reads']>3:hold('DRAFT_REVISION_READ_BUDGET_EXHAUSTED')
            ordinal,snapshot=self._read('PRE_SEND')
            if snapshot is None:return self._operation_result(self.status())
            self._current()
            if digest(wire.baseline_projection(snapshot))!=current['baseline_sha']:
                hold('DRAFT_REVISION_BASELINE_CHANGED')
            changes=self._input()['changes']
            payload=wire.update_payload(snapshot,changes,synthetic=self.provider.synthetic)
            # Revalidate frozen changes against the actual PREPARED expectation.
            with self.store.connection() as db:
                state=self.store._state(db,self.case_id)
                proof=self.store._load_proof(f'prepared-{self.case_id}.json',state['revision']['preparation_sha'],state['case'])
                expected=self._expected(snapshot)
                if expected!=proof['data']['expected']:hold('DRAFT_REVISION_INPUT_CHANGED')
            self._current();secret=self.provider.token();self._current()
            request=wire.encode_update(payload,secret,synthetic=self.provider.synthetic)
            admission=self.store.claim_update(self.case_id,ordinal,sha256(request.body).hexdigest())
            self._current();self.store.consume_admission(admission)
            response=None;capture=None
            try:
                self._current()
                if self._official():
                    capture=self.provider.send_admitted(request,admission);response=capture.response
                else:response=self.provider.send_update(request)
            except Exception:
                pass
            # Historical result is archived before current release guards. It is
            # not a fresh send grant and cannot turn a lost response into zero.
            self.store.record_response(self.case_id,admission,response,secret,transport=capture)
            self._current()
            if self._state()['state']=='REJECTED_RESPONSE':return self.status()
            ordinal,snapshot=self._read('POST_SEND')
            if snapshot is not None:
                self.store.record_effect(self.case_id,ordinal)
                if bridge is not None and self._state()['effect']['matched'] is True:bridge.complete()
            return self._operation_result(self.status())

    @bounded_failure
    def readback(self):
        with self.context.execution_lock():
            self.read_diagnostic=None
            state=self._current();current=state['revision']
            if current['state']=='PREPARING':
                if type(state.get('pending_adoption')) is dict:
                    ordinal=len(state['pending_adoption']['reads'])
                    with self.store.connection() as db:
                        checked=self.store._state(db,self.case_id)
                        if checked.get('pending_adoption')!=state['pending_adoption']:hold('DRAFT_REVISION_INPUT_CHANGED')
                        snapshot=self.store._read_snapshot(checked,ordinal)
                    return self._prepare_observed(ordinal,snapshot)
                ordinal,snapshot=self._read('RECOVERY_BASELINE')
                return self._prepare_observed(ordinal,snapshot)
            bridge=self._direct_bridge()
            if (bridge is not None and type(current.get('effect')) is dict
                    and current['effect'].get('matched') is True):
                bridge.complete()
                return self.status()
            if not current['writes']:return self.status()
            ordinal,snapshot=self._read('RECOVERY_EFFECT')
            if snapshot is not None:
                self.store.record_effect(self.case_id,ordinal)
                if bridge is not None and self._state()['effect']['matched'] is True:bridge.complete()
            return self._operation_result(self.status())

    @bounded_failure
    def status(self):
        # No provider/token/source-files/network access for journal-only status.
        current=self._state()
        return status_value(current,comparison_profile=(self.context.preservation.evidence()['profile']
            if self.context.preservation is not None else wire.PROFILE))


def status_value(current,*,comparison_profile=wire.PROFILE):
    """Journal-only public projection, shared with offline status routing."""
    effect=current['effect']
    from .draft_revision_store import OFFICIAL_PROVIDER
    official=current['provider_profile']==OFFICIAL_PROVIDER
    return {'revision_id':current['id'],'case_id':current['case_id'],'state':current['state'],
        'read_attempts':current['reads'],'remaining_reads':5-current['reads'],
        'write_attempts':current['writes'],'response_state':current['response_state'] or
            ('UNKNOWN_NOT_ARCHIVED' if current['writes'] else 'NOT_SENT'),
        'current_effect':deepcopy(effect),'provenance':('OFFICIAL_DRAFT_REVISION_ADAPTER'
            if official else 'SYNTHETIC_REVISION_COMPONENT'),
        'platform_effect_verified':bool(official and effect is not None and effect['matched']),
        'comparison_profile':comparison_profile,
        'remote_image_bytes_verified':False,'originality':'UNVERIFIED',
        'public_publication':'PROHIBITED_BY_CASE','delete_fallback':'UNAVAILABLE',
        'original_save_history':'UNCHANGED'}
