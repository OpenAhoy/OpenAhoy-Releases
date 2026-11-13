"""Ephemeral official-response witness, never a secret or model argument.

Only the concrete provider issues this object after its admitted HTTPS call.
The journal checks original object identity and consumes it exactly once before
persisting bounded provenance. This is same-UID integrity, not an OS sandbox.
"""
from dataclasses import dataclass,field
from hashlib import sha256
from .contracts import WCEError
from .http_transport import HTTPResponse

_SEAL=object()

def hold():raise WCEError('DRAFT_REVISION_TRANSPORT_WITNESS_HOLD')

@dataclass(frozen=True)
class CapturedRevisionResponse:
    owner:object=field(repr=False,compare=False)
    admission:object=field(repr=False,compare=False)
    response:HTTPResponse=field(repr=False)
    request_sha:str
    _seal:object=field(repr=False,compare=False)
    def __post_init__(self):
        if self._seal is not _SEAL or type(self.response) is not HTTPResponse:hold()

def _capture(owner,admission,request,response):
    from .draft_revision_provider import OfficialRevisionProvider
    if type(owner) is not OfficialRevisionProvider:hold()
    key=(admission.case_id,admission.kind,admission.ordinal)
    if owner.used.get(key) is not admission:hold()
    result=CapturedRevisionResponse(owner,admission,response,sha256(request.body).hexdigest(),_SEAL)
    owner.issued[id(result)]=result
    return result

def consume(capture,admission,body_sha):
    if (type(capture) is not CapturedRevisionResponse or capture._seal is not _SEAL
            or capture.admission is not admission
            or capture.owner.issued.get(id(capture)) is not capture
            or sha256(capture.response.body).hexdigest()!=body_sha):hold()
    capture.owner.issued.pop(id(capture))
    return {'origin':'OFFICIAL_ADMITTED_HTTPS_RESPONSE_V1','request_sha':capture.request_sha,
        'response_sha':body_sha}

def validate(evidence,provider_profile,*,body_sha=None,request_sha=None):
    from .draft_revision_store import SYNTHETIC_PROVIDER,OFFICIAL_PROVIDER
    if type(evidence) is not dict or set(evidence)!={'origin','request_sha','response_sha'}:hold()
    if evidence['origin']=='SYNTHETIC':
        if provider_profile!=SYNTHETIC_PROVIDER or evidence['request_sha'] is not None or evidence['response_sha'] is not None:hold()
    elif evidence['origin']=='NO_QUALIFIED_RESPONSE':
        if body_sha is not None or evidence['request_sha'] is not None or evidence['response_sha'] is not None:hold()
    elif evidence['origin']=='OFFICIAL_ADMITTED_HTTPS_RESPONSE_V1':
        from .draft_revision_state import checksum
        if (provider_profile!=OFFICIAL_PROVIDER or not checksum(evidence['request_sha'])
                or not checksum(evidence['response_sha']) or body_sha is not None and body_sha!=evidence['response_sha']
                or request_sha is not None and request_sha!=evidence['request_sha']):hold()
    else:hold()
    return evidence

def evidence(case,admission,capture,body_sha):
    from .draft_revision_store import SYNTHETIC_PROVIDER,OFFICIAL_PROVIDER
    if case['provider_profile']==SYNTHETIC_PROVIDER:
        if capture is not None:hold()
        return {'origin':'SYNTHETIC','request_sha':None,'response_sha':None}
    if case['provider_profile']!=OFFICIAL_PROVIDER:hold()
    if capture is None:
        if body_sha is not None:hold()
        return {'origin':'NO_QUALIFIED_RESPONSE','request_sha':None,'response_sha':None}
    actual=sha256(capture.response.body).hexdigest()
    if body_sha is not None and actual!=body_sha:hold()
    return consume(capture,admission,actual)
