"""R203 diagnostics: pure input comparisons, no IO, authority or network.

The caller supplies already-held snapshots; these never establish provenance,
permission, transport dispatch, strict readback, remote pixels, or visual QA.
"""
from html.parser import HTMLParser
from urllib.parse import urlsplit
from hashlib import sha256
import json,re
from . import documents
from .html_document import TAGS,VOID,css,check_tokens
from .own_draft_defaults import validate_defaults_metadata,apply_comment_settings
from .service import digest,canonical

FIELDS=('article_type','title','author','digest','content_source_url','thumb_media_id',
        'cover_info','need_open_comment','only_fans_can_comment')
CONTEXT=('identity','bundle_id','version','content_digest','target')
IDENTITY=('tenant','principal','client','session','connection','account','resource','generation','epoch','source_kind')
MEDIA=('slot','role','asset_ref','source_sha256','transport_sha256','source_mime','transport_mime','source_size','transport_size')

class Unverified(Exception):pass

def same_image(a,b):
    if any(type(u) is not str or not u or any(ord(c)<=32 or ord(c)==127 or c.isspace() for c in u) for u in (a,b)):return False
    if a==b:return True
    try:
        x,y=urlsplit(a),urlsplit(b)
        return (x.hostname==y.hostname=='mmbiz.qpic.cn' and x.scheme in ('http','https') and y.scheme=='https'
                and x.username is None and y.username is None and x.password is None and y.password is None
                and x.port is None and y.port is None and not x.fragment and not y.fragment
                and x.path.endswith('/0') and y.path==x.path[:-1]+'640' and x.query==y.query)
    except (ValueError,TypeError):return False

class Events(HTMLParser):
    """Only bounded supported syntax; all text, links, attributes and order retained."""
    def __init__(self,value,expected_images=None):
        if type(value) is not str or len(value.encode())>1000000:raise Unverified()
        try:check_tokens(value)
        except Exception:raise Unverified() from None
        super().__init__(convert_charrefs=True);self.events=[];self.stack=[];self.images=[];self.expected=expected_images
        try:self.feed(value);self.close()
        except Exception:raise Unverified() from None
        if self.stack:raise Unverified()
    def handle_starttag(self,tag,attrs):
        if tag not in TAGS or len(attrs)!=len(dict(attrs)):raise Unverified()
        values=dict(attrs)
        allowed={'style'}|({'href'} if tag=='a' else set())|({'src','data-src','alt'} if tag=='img' else set())
        if not set(values)<=allowed or any(type(v) is not str for v in values.values()):raise Unverified()
        if tag=='a':
            if any(t=='a' for t in self.stack):raise Unverified()
            if 'href' in values:
                try:documents.safe_url(values['href'])
                except Exception:raise Unverified() from None
        if 'style' in values:
            try:values['style']=css(values['style'],tag,(1,0))
            except Exception:raise Unverified() from None
        if tag=='img':
            if ('src' in values)==('data-src' in values):raise Unverified()
            value=values.pop('data-src',values.get('src'));values['src']=value
            try:documents.safe_url(value)
            except Exception:raise Unverified() from None
            if self.expected is not None:
                idx=len(self.images)
                if idx>=len(self.expected) or not same_image(self.expected[idx],value):
                    # Preserve the differing value for a CONTENT_LOSS result.
                    pass
                else:values['src']=self.expected[idx]
            self.images.append(value)
        self.events.append(('start',tag,tuple(sorted(values.items()))))
        if tag not in VOID:self.stack.append(tag)
    def handle_startendtag(self,tag,attrs):
        self.handle_starttag(tag,attrs)
        if tag not in VOID:self.handle_endtag(tag)
    def handle_endtag(self,tag):
        if tag in VOID or not self.stack or self.stack[-1]!=tag:raise Unverified()
        self.stack.pop();self.events.append(('end',tag))
    def handle_data(self,data):
        if self.events and self.events[-1][0]=='text':self.events[-1]=('text',self.events[-1][1]+data)
        else:self.events.append(('text',data))
    def handle_comment(self,data):raise Unverified()
    def handle_decl(self,data):raise Unverified()
    def unknown_decl(self,data):raise Unverified()

def fields(before,after):
    result={}
    if type(before) is not dict or type(after) is not dict:return {},['ARTICLE_SHAPE']
    for key in FIELDS:
        if key not in before or key not in after:result[key]='UNVERIFIED_MISSING'
        else:result[key]='EXACT' if before[key]==after[key] else 'DIFFERENT'
    extra=(set(before)|set(after))-(set(FIELDS)|{'content'})
    return result,(['UNSUPPORTED_FIELDS'] if extra else [])

def content_details(before,after):
    same_bytes=type(before) is str and type(after) is str and before==after
    try:
        e=Events(before);a=Events(after,e.images)
        if len(e.images)!=len(a.images) or e.events!=a.events:
            return {'state':'CONTENT_LOSS','html_bytes_equal':same_bytes,'rules':[]}
        if same_bytes:return {'state':'EXACT','html_bytes_equal':True,'rules':[]}
        return {'state':'MATCHED_NORMALIZED','html_bytes_equal':False,'rules':['NORMALIZATION_OBSERVED']}
    except Exception:
        return {'state':'UNVERIFIED','html_bytes_equal':same_bytes if type(before) is str and type(after) is str else None,'rules':[]}

def content(before,after):
    return content_details(before,after)['state']

def compare_projection(expected,actual):
    if type(expected) is not dict or type(actual) is not dict or set(expected)!={'articles'} or set(actual)!={'articles'}:return {'state':'UNVERIFIED','reason':'PROJECTION_SHAPE','articles':[]}
    es,rs=expected['articles'],actual['articles']
    if type(es) is not list or type(rs) is not list or not 1<=len(es)<=8:return {'state':'UNVERIFIED','reason':'PROJECTION_SHAPE','articles':[]}
    if len(es)!=len(rs):return {'state':'CONTENT_LOSS','reason':'ARTICLE_COUNT','articles':[]}
    results=[]
    for index,(e,a) in enumerate(zip(es,rs),1):
        f,issues=fields(e,a)
        body_detail=content_details(e.get('content'),a.get('content')) if type(e) is dict and type(a) is dict and 'content' in e and 'content' in a else {'state':'UNVERIFIED','html_bytes_equal':None,'rules':[]}
        body=body_detail['state']
        if body=='CONTENT_LOSS' or any(f.get(k)=='DIFFERENT' for k in ('article_type','title','author','content_source_url','thumb_media_id')):state='CONTENT_LOSS'
        elif body=='UNVERIFIED' or issues or any(v=='UNVERIFIED_MISSING' for v in f.values()):state='UNVERIFIED'
        elif any(v=='DIFFERENT' for v in f.values()):state='UNEXPLAINED_DIFFERENCE'
        elif body=='MATCHED_NORMALIZED':state='MATCHED_NORMALIZED'
        else:state='EXACT'
        results.append({'index':index,'state':state,'fields':f,'content':body,'html_bytes_equal':body_detail['html_bytes_equal'],'rules':body_detail['rules'],'issues':issues})
    state='CONTENT_LOSS' if any(a['state']=='CONTENT_LOSS' for a in results) else 'UNVERIFIED' if any(a['state']=='UNVERIFIED' for a in results) else 'UNEXPLAINED_DIFFERENCE' if any(a['state']=='UNEXPLAINED_DIFFERENCE' for a in results) else 'MATCHED_NORMALIZED' if any(a['state']=='MATCHED_NORMALIZED' for a in results) else 'EXACT'
    return {'state':state,'articles':results}

def audit(context,source,frozen,intent,*,dispatch_evidence=None,readback=None,strict_readback=None):
    result={'binding':'UNVERIFIED','source_to_frozen':{'state':'UNVERIFIED'},'intent':{'state':'UNVERIFIED'},
            'readback':{'state':'UNVERIFIED'},'strict_readback':strict_readback if strict_readback in ('MATCHED','UNVERIFIED',None) else 'UNVERIFIED','visual':'NOT_VERIFIED',
            'remote_pixels_verified':False,'authorizes_send':False,'source_provenance':'UNVERIFIED_CALLER_SUPPLIED',
            'strict_readback_provenance':'UNVERIFIED_CALLER_SUPPLIED'}
    if (type(context) is not dict or set(context)!=set(CONTEXT) or type(context['identity']) is not dict or set(context['identity'])!=set(IDENTITY)
        or any(type(context['identity'][k]) is not str or not context['identity'][k] for k in ('tenant','principal','client','session','connection','account','resource','source_kind'))
        or type(context['identity']['generation']) is not int or context['identity']['generation']<1
        or type(context['identity']['epoch']) is not int or context['identity']['epoch']<0
        or type(context['bundle_id']) is not str or not context['bundle_id'] or type(context['version']) is not str or not context['version']
        or type(context['content_digest']) is not str or re.fullmatch('[a-f0-9]{64}',context['content_digest']) is None
        or type(context['target']) is not dict or set(context['target'])!={'kind','id'}
        or context['target']['kind'] not in ('request_key','restore_handle') or type(context['target']['id']) is not str or not context['target']['id']):
        result['binding']='BINDING_MISMATCH';return result
    for snapshot in (source,frozen,intent,dispatch_evidence,readback):
        if snapshot is not None and (type(snapshot) is not dict or snapshot.get('binding')!=context):
            result['binding']='BINDING_MISMATCH';return result
    result['binding']='MATCHED_CALLER_SUPPLIED'
    try:
        manifest=frozen['manifest']
        if digest(manifest)!=context['content_digest'] or manifest['bundle_id']!=context['bundle_id'] or manifest['version']!=context['version'] or manifest['binding']!=context['identity']:
            result['binding']='BINDING_MISMATCH';return result
        normalized=documents.normalize(source['document'])
        normalized_frozen=documents.normalize(manifest['document'])
        if normalized!=normalized_frozen:result['source_to_frozen']={'state':'CONTENT_LOSS','reason':'DOCUMENT_CHANGED'};return result
        sm,fm=source['media'],frozen['media']
        if type(sm) is not list or type(fm) is not list or sm!=fm:result['source_to_frozen']={'state':'CONTENT_LOSS','reason':'MEDIA_CHANGED'};return result
        expected=list(documents.assets(normalized))
        if len(fm)!=len(expected):result['source_to_frozen']={'state':'CONTENT_LOSS','reason':'SLOT_COUNT'};return result
        for row,(slot,asset,role) in zip(fm,expected):
            if type(row) is not dict or set(row)!=set(MEDIA) or (row['slot'],row['asset_ref'],row['role'])!=(slot,asset,role):raise Unverified()
            if any(type(row[k]) is not str or re.fullmatch('[a-f0-9]{64}',row[k]) is None for k in ('source_sha256','transport_sha256')):raise Unverified()
            if any(type(row[k]) is not int or row[k]<=0 for k in ('source_size','transport_size')) or any(row[k] not in ('image/png','image/jpeg') for k in ('source_mime','transport_mime')):raise Unverified()
        manifest_assets=manifest.get('assets')
        if type(manifest_assets) is not list:raise Unverified()
        expected_assets=[{'slot':row['slot'],'asset_ref':row['asset_ref'],'role':row['role'],
                          'declared_type':row['transport_mime'],'size':row['transport_size'],
                          'sha256':row['transport_sha256']} for row in fm]
        if manifest_assets!=expected_assets:
            result['source_to_frozen']={'state':'CONTENT_LOSS','reason':'MEDIA_MANIFEST_CHANGED'};return result
        result['source_to_frozen']={'state':'MATCHED_NORMALIZED','article_count':len(normalized['articles']),'media_count':len(fm),'media_provenance':'UNVERIFIED_CALLER_SUPPLIED'}
    except Exception:
        result['source_to_frozen']={'state':'UNVERIFIED','reason':'UNSUPPORTED_OR_INCOMPLETE'};return result
    try:
        maps=intent['mappings'];required={x[0] for x in expected}
        if type(maps) is not dict or set(maps)!=required:raise Unverified()
        for row in fm:
            m=maps[row['slot']]
            if type(m) is not dict or set(m)!=({'media_id'} if row['role']=='cover' else {'url'}):raise Unverified()
            if any(type(v) is not str or not v for v in m.values()):raise Unverified()
            if row['role']=='body':documents.safe_url(m['url'])
        expected_payload=documents.render_projection(normalized,maps)
        if intent.get('defaults') is not None:
            md=validate_defaults_metadata(intent['defaults'],expected_binding_sha=digest(context['identity']),article_count=len(normalized['articles']))
            expected_payload=apply_comment_settings(expected_payload,md)
        given=intent['payload'];body_sha=sha256(canonical(given).encode()).hexdigest()
        if expected_payload!=given:
            result['intent']={'state':'CONTENT_LOSS','reason':'PROJECTION_CHANGED','dispatch':'DISPATCH_EVIDENCE_UNAVAILABLE'};return result
        dispatch='DISPATCH_EVIDENCE_UNAVAILABLE'
        if dispatch_evidence is not None:
            dispatch=('CALLER_SUPPLIED_BODY_MATCH_UNVERIFIED' if dispatch_evidence.get('request_body_sha256')==body_sha else 'DISPATCH_EVIDENCE_MISMATCH')
        result['intent']={'state':'INTENT_CONSTRUCTED','body_sha256':body_sha,'dispatch':dispatch,'media_mapping_provenance':'UNVERIFIED_CALLER_SUPPLIED'}
    except Exception:
        result['intent']={'state':'UNVERIFIED','dispatch':'DISPATCH_EVIDENCE_UNAVAILABLE'};return result
    if readback is not None:
        actual=readback.get('actual_projection')
        policy=readback.get('actual_projection_policy')
        if policy=='ACTUAL_DRAFT_PROJECTION_V1':
            if type(actual) is dict and set(actual)=={'title','content','thumb_media_id'} and len(given['articles'])==1:
                actual={'articles':[actual]}
            else:actual=None
        elif policy not in (None,'ACTUAL_DOCUMENT_PROJECTION_V2'):
            actual=None
        if actual is not None:result['readback']=compare_projection(given,actual)
        else:result['readback']={'state':'UNVERIFIED','reason':'ACTUAL_PROJECTION_MISSING'}
    return result


def restore_readback_report(expected,actual,strict_state,source_kind,*,comments_separate=False):
    """Internal new-restoration output only; consumes an already obtained GET.

    This function never acquires proof, sends or repairs data. Its caller has
    validated the original intent and must run its final guard after this call.
    """
    projected=expected if type(expected) is dict and 'articles' in expected else {'articles':[expected]}
    observed=(actual if type(actual) is dict and 'articles' in actual else {'articles':[actual]}) if actual is not None else None
    return {'policy':'RESTORE_NONVISUAL_DIAGNOSTIC_V1',
        'source_input':'UNAVAILABLE_IN_CURRENT_GET',
        'submission':'HOST_VALIDATED_ORIGINAL_STEP_INTENT',
        'expected_projection_kind':'BODY_PROJECTION_WITH_COMMENTS_SEPARATE' if comments_separate else 'ORIGINAL_STEP_COMPARISON_PROJECTION',
        'expected_projection_sha256':digest(expected),'dispatch_evidence':'NOT_EVALUATED',
        'get_projection_state':'CURRENT_GET_PROJECTION_PARSED' if type(actual) is dict else 'CURRENT_GET_PROJECTION_UNAVAILABLE',
        'get_attempt_source':'SYNTHETIC' if source_kind=='SYNTHETIC_SETUP' else 'OWN_OFFICIAL_WIRE_ATTEMPT',
        'comparison':compare_projection(projected,observed),
        'strict_readback':strict_state,'strict_readback_unchanged':True,
        'comment_comparison':'SEPARATE_EXISTING_COMPARISON' if comments_separate else 'NOT_REQUESTED_OR_UNAVAILABLE',
        'visual':'NOT_VERIFIED','remote_pixels_verified':False,'authorizes_send':False}
