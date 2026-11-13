"""Narrow, explicitly observed image-URI representation for NEWS revision.

No fetching or image-byte/visual verification occurs. Outgoing HTML retains
the exact verified upload-response URLs. Only incoming src/data-src spelling
and the separately checked initial QPIC URI representation are projected.
"""
from copy import deepcopy
from dataclasses import dataclass,field
from hashlib import sha256
from urllib.parse import urlsplit

from .contracts import WCEError
from .html_document import Fragment,css
from .import_styles import POLICY as HTML_POLICY,inline_style
from .service import canonical,digest

PROFILE='OBSERVED_QPIC_RENDER_PRESERVATION_V1'
ONE_CHANGED_PROFILE='OBSERVED_QPIC_ONE_CHANGED_IMAGE_V1'


def hold():raise WCEError('DRAFT_REVISION_IMAGE_PRESERVATION_HOLD')


def associated(original,observed):
    """One HTML attribute decode has already happened. No URL unquoting."""
    from .documents import safe_url
    if type(original) is not str or type(observed) is not str:hold()
    safe_url(original);safe_url(observed)
    if original==observed:return True
    try:
        before,after=urlsplit(original),urlsplit(observed)
        if (before.hostname!='mmbiz.qpic.cn' or after.hostname!=before.hostname
                or before.netloc!=after.netloc or before.port!=after.port
                or before.username is not None or before.password is not None
                or not original.startswith('http://') or not observed.startswith('https://')
                or before.scheme!='http' or after.scheme!='https'
                or before.query!=after.query or before.fragment or after.fragment):return False
        left,sep,last=before.path.rpartition('/');right,sep2,end=after.path.rpartition('/')
        return bool(sep and sep2 and left and left==right and last=='0' and end=='640')
    except ValueError:return False


class _ObservedFragment(Fragment):
    def __init__(self,source,expected_urls,*,allow_observed):
        self.expected_urls=expected_urls;self.image_uris=[];self.allow_observed=allow_observed
        super().__init__(source,policy=HTML_POLICY)
        if len(self.image_uris)!=len(expected_urls):hold()

    def _validated_style(self,value,tag,position):
        # Existing saved drafts use either of the two finite wire languages.
        # Validate the whole attribute in one language; never merge individual
        # declarations or tolerate CSS-equivalent representations. The exact
        # original attribute string is restored below for tree comparison.
        try:return inline_style(value,tag,position)
        except WCEError as error:
            if error.code!='HTML_IMPORT_CSS_UNSUPPORTED':raise
        return css(value,tag,position)

    def handle_starttag(self,tag,attrs):
        if tag=='img':
            names=[key for key,_ in attrs]
            if len(set(names))!=len(names) or set(names)-{'src','data-src','alt','style'}:hold()
            sources=[(key,value) for key,value in attrs if key in {'src','data-src'}]
            index=len(self.image_uris)
            if len(sources)!=1 or index>=len(self.expected_urls):hold()
            uri=sources[0][1];expected=self.expected_urls[index]
            if (not associated(expected,uri) if self.allow_observed else uri!=expected):hold()
            self.image_uris.append(uri)
            attrs=[('src','wce-asset:revision'+str(index+1)) if key in {'src','data-src'} else (key,value)
                for key,value in attrs]
        # Fragment validates the closed language/CSS but normalizes attribute
        # spellings. Preserve the once-HTML-decoded original values for exact
        # comparison; only the explicitly scoped image source name/value above
        # is represented by a slot. No CSS-equivalence tolerance is implied.
        raw_values=dict(attrs);parent=self.stack[-1]
        super().handle_starttag(tag,attrs)
        parent['children'][-1]['attrs']=raw_values


@dataclass(frozen=True)
class ImageObservation:
    """Scoped private evidence, not a remote-byte proof or permission."""
    upload_urls:tuple=field(repr=False)
    current_uris:tuple=field(repr=False)
    old_body_sha256:str
    profile:str=PROFILE


@dataclass(frozen=True)
class PreservationPlan:
    """Host-derived from original verified uploads; confers no permission."""
    original_html:str=field(repr=False)
    upload_urls:tuple=field(repr=False)

    def evidence(self):
        # Parsing also verifies count/order and exact original URL values.
        _ObservedFragment(self.original_html,self.upload_urls,allow_observed=False)
        return {'profile':PROFILE,'original_body_sha256':sha256(self.original_html.encode()).hexdigest(),
            'upload_urls_sha256':digest(list(self.upload_urls))}

@dataclass(frozen=True)
class ChangedImagePlan:
    """One real uploaded response replaces exactly one old body image."""
    original_html:str=field(repr=False)
    upload_urls:tuple=field(repr=False)
    changed_index:int
    new_url:str=field(repr=False)
    def evidence(self):
        _ObservedFragment(self.original_html,self.upload_urls,allow_observed=False)
        from .upload_wire import api_reference_reason
        if (type(self.changed_index) is not int or not 0<=self.changed_index<len(self.upload_urls)
                or api_reference_reason(self.new_url) is not None or self.new_url in self.upload_urls):hold()
        return {'profile':ONE_CHANGED_PROFILE,'original_body_sha256':sha256(self.original_html.encode()).hexdigest(),
            'upload_urls_sha256':digest(list(self.upload_urls)),'changed_index':self.changed_index,
            'new_url_sha256':digest(self.new_url)}


def observe_original(original_html,current_html,upload_urls):
    if (type(upload_urls) is not tuple or not 1<=len(upload_urls)<=5
            or len(set(upload_urls))!=len(upload_urls)):hold()
    original=_ObservedFragment(original_html,upload_urls,allow_observed=False)
    current=_ObservedFragment(current_html,upload_urls,allow_observed=True)
    if original.root!=current.root:hold()
    return ImageObservation(upload_urls,tuple(current.image_uris),digest(current.root))


def expected_projection(raw_projection,new_wire_html,observation):
    """Freeze exact first-GET URIs and new full safe AST, preserving metadata."""
    if type(observation) is not ImageObservation or observation.profile!=PROFILE:hold()
    if type(raw_projection) is not dict or len(raw_projection.get('response',{}).get('news_item',[]))!=1:hold()
    fresh=_ObservedFragment(raw_projection['response']['news_item'][0]['content'],
        observation.current_uris,allow_observed=False)
    if tuple(fresh.image_uris)!=observation.current_uris or digest(fresh.root)!=observation.old_body_sha256:hold()
    new=_ObservedFragment(new_wire_html,observation.upload_urls,allow_observed=False)
    expected=deepcopy(raw_projection)
    # Body comparison is a full AST, including every non-image node/attribute.
    # Other response values and presence remain exact in the outer projection.
    expected['response']['news_item'][0]['content']={'profile':PROFILE,'tree':new.root,
        'image_uris':list(observation.current_uris)}
    return expected

def expected_one_changed_projection(raw_projection,new_wire_html,observation,plan):
    if type(plan) is not ChangedImagePlan or type(observation) is not ImageObservation:hold()
    plan.evidence()
    if (observation.upload_urls!=plan.upload_urls or type(raw_projection) is not dict
            or len(raw_projection.get('response',{}).get('news_item',[]))!=1):hold()
    fresh=_ObservedFragment(raw_projection['response']['news_item'][0]['content'],observation.current_uris,allow_observed=False)
    if tuple(fresh.image_uris)!=observation.current_uris or digest(fresh.root)!=observation.old_body_sha256:hold()
    desired=list(plan.upload_urls);desired[plan.changed_index]=plan.new_url
    new=_ObservedFragment(new_wire_html,tuple(desired),allow_observed=False)
    expected=deepcopy(raw_projection);uris=list(observation.current_uris);uris[plan.changed_index]=plan.new_url
    expected['response']['news_item'][0]['content']={'profile':ONE_CHANGED_PROFILE,'tree':new.root,
        'image_uris':uris,'changed_index':plan.changed_index}
    return expected


def effect_matches(actual,expected):
    """Strict by default; never discard arbitrary URLs or unknown attributes."""
    from .draft_revision_wire import PROFILE as WIRE_PROFILE,PRESERVATION_FIELDS,_article
    from .own_draft_wire import reference_valid
    from .html_document import serialize
    def valid(value,structured=False):
        if type(value) is not dict or value.get('profile')!=WIRE_PROFILE or not reference_valid(value.get('reference'),True):return False
        response=value.get('response')
        if type(response) is not dict or type(response.get('news_item')) is not list or len(response['news_item'])!=1:return False
        row=response['news_item'][0]
        if type(row) is not dict or not PRESERVATION_FIELDS<=set(row):return False
        try:
            checked=deepcopy(row)
            if type(checked['content']) is dict:
                expected_keys={'profile','tree','image_uris'}
                if checked['content'].get('profile')==ONE_CHANGED_PROFILE:expected_keys|={'changed_index'}
                if (not structured or set(checked['content'])!=expected_keys
                        or checked['content']['profile'] not in (PROFILE,ONE_CHANGED_PROFILE)):return False
                checked['content']='<p>Validated structured expectation</p>'
            _article(checked,synthetic=True)
        except (WCEError,TypeError,ValueError):return False
        if 'errcode' in response and (type(response['errcode']) is not int or response['errcode']!=0):return False
        return True
    if not valid(actual) or not valid(expected,structured=True):return False
    target=expected['response']['news_item'][0]['content']
    if type(target) is not dict or target.get('profile') not in (PROFILE,ONE_CHANGED_PROFILE):return actual==expected
    changed=target.get('profile')==ONE_CHANGED_PROFILE
    if set(target)!=({'profile','tree','image_uris','changed_index'} if changed else {'profile','tree','image_uris'}):hold()
    if len(actual.get('response',{}).get('news_item',[]))!=1:return False
    uris=target['image_uris']
    if type(uris) is not list or not 1<=len(uris)<=5 or any(type(u)is not str for u in uris):hold()
    if changed and (type(target['changed_index']) is not int or not 0<=target['changed_index']<len(uris)):hold()
    try:
        # Validate the stored expected AST through the same closed language.
        expected_html=serialize(target['tree'],{'revision'+str(i+1):uri for i,uri in enumerate(uris)})
        validated=_ObservedFragment(expected_html,tuple(uris),allow_observed=False)
        if validated.root!=target['tree']:return False
        parsed=_ObservedFragment(actual['response']['news_item'][0]['content'],tuple(uris),allow_observed=changed)
        if changed and any(uri!=uris[i] for i,uri in enumerate(parsed.image_uris) if i!=target['changed_index']):return False
    except (WCEError,KeyError,TypeError,ValueError,AttributeError,RecursionError):return False
    value=deepcopy(actual)
    value['response']['news_item'][0]['content']={'profile':target['profile'],'tree':parsed.root,'image_uris':list(uris) if changed else parsed.image_uris}
    if changed:value['response']['news_item'][0]['content']['changed_index']=target['changed_index']
    return value==expected
