"""Pure, bounded platform representation observation; never authority or CAS.

Only the caller supplies the resolved original projection and ordered original
successful body URLs. No filesystem, SDK, HTTP, DOM or script execution.
"""
from html.parser import HTMLParser
from urllib.parse import urlsplit, unquote
import json
import math
import re
import struct
from decimal import Decimal
from hashlib import sha256

PROFILE = 'ORDINARY_DRAFT_PLATFORM_REPRESENTATION_V1'
MAX_ARTICLES = 8
MAX_CONTENT_CHARS = 20000
MAX_RESPONSE_BYTES = 2 * 1024 * 1024
MAX_TOKENS = 2 * MAX_CONTENT_CHARS
_FIELDS = {'article_type','title','content','thumb_media_id','author','digest',
           'content_source_url','cover_info','need_open_comment','only_fans_can_comment'}
_VOID = frozenset(('area','base','br','col','embed','hr','img','input','link','meta','param','source','track','wbr'))
_NAME = re.compile(r'<\s*/?\s*([A-Za-z][A-Za-z0-9:_-]*)')
_ATTRIBUTE = re.compile(r'''\s*([^\s=/>]+)(?:\s*=\s*(?:"[^"]*"|'[^']*'|[^\s>]*))?''')
_COORD = re.compile(r'(?:0(?:\.[0-9]{1,12})?|1(?:\.0{1,12})?)\Z')

class _Invalid(ValueError):
    pass

def _need(value):
    if not value:
        raise _Invalid()

class _HTML(HTMLParser):
    def __init__(self, raw):
        super().__init__(convert_charrefs=True)
        self.raw=raw;self.tokens=[];self.images=[];self.visible=[];self.stack=[]
        _need(type(raw)is str and len(raw)<=MAX_CONTENT_CHARS and len(raw.encode('utf-8'))<=1_000_000
              and re.search(r'[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]',raw)is None)
        self.offsets=[0]
        for line in raw.splitlines(keepends=True):self.offsets.append(self.offsets[-1]+len(line))
        self.feed(raw);self.close();_need(not self.stack)
    def add(self,token):
        self.tokens.append(token);_need(len(self.tokens)<=MAX_TOKENS)
    def name(self):
        line,col=self.getpos();match=_NAME.match(self.raw[self.offsets[line-1]+col:])
        _need(match is not None);return match.group(1)
    def start(self,tag,attrs,closed):
        _need(len(attrs)==len({k for k,_ in attrs}) and all(type(k)is str and(type(v)is str or v is None)for k,v in attrs))
        name=self.name();_need(name==tag)  # no unreviewed case folding
        raw=self.get_starttag_text();head=_NAME.match(raw);pos=head.end();names=[]
        while pos<len(raw):
            if raw[pos:].strip()in('>','/>'):break
            match=_ATTRIBUTE.match(raw,pos);_need(match is not None and match.end()>pos)
            names.append(match.group(1));pos=match.end()
        _need(names==[key for key,_ in attrs])
        index=len(self.tokens);self.add(('empty'if closed else'start',name,tuple(attrs)))
        if tag=='img':self.images.append((index,tuple(attrs)))
        if not closed and tag not in _VOID:self.stack.append(tag)
    def handle_starttag(self,tag,attrs):self.start(tag,attrs,False)
    def handle_startendtag(self,tag,attrs):self.start(tag,attrs,True)
    def handle_endtag(self,tag):
        name=self.name();_need(name==tag and self.stack and self.stack[-1]==tag)
        self.stack.pop();self.add(('end',name))
    def handle_data(self,data):
        self.add(('data',data))
        if not any(tag in('style','script')for tag in self.stack):self.visible.append(data)
    def handle_comment(self,data):self.add(('comment',data))
    def handle_decl(self,decl):self.add(('declaration',decl))
    def handle_pi(self,data):self.add(('pi',data))
    def unknown_decl(self,data):self.add(('unknown_declaration',data))
    def handle_entityref(self,name):raise _Invalid()
    def handle_charref(self,name):raise _Invalid()

def _urls(original,actual):
    _need(type(original)is str and type(actual)is str)
    def safe(value):
        _need(not any(ord(c)<33 or ord(c)==127 for c in value))
        parsed=urlsplit(value)
        _need(parsed.scheme in('http','https') and parsed.netloc=='mmbiz.qpic.cn'
              and parsed.hostname=='mmbiz.qpic.cn' and parsed.username is None and parsed.password is None
              and parsed.port is None and not parsed.fragment and parsed.path.startswith('/')
              and not re.search(r'(?:^|[?&])(?:access_token|token|auth|signature|secret)=',parsed.query,re.I))
        _need(not any(unquote(part.split('=',1)[0]).lower()in{'access_token','token','auth','signature','secret'}for part in parsed.query.split('&')))
        return parsed
    before=safe(original);safe(actual)
    if actual==original:return True
    if before.scheme!='http'or before.query!='from=appmsg'or not before.path.endswith('/0'):return False
    cut=original.find('?')
    expected='https'+original[4:cut-2]+'/640'+original[cut:]
    return actual==expected


def _html(expected,actual,bindings):
    before,after=_HTML(expected),_HTML(actual)
    _need(type(bindings)is list and all(type(u)is str for u in bindings))
    image_observations=[]
    images=len(before.images);fields={'text':True,'structure':True,'attributes':True,'image_bindings':True}
    if len(after.images)!=images or len(bindings)!=images:fields['image_bindings']=False
    if len(before.tokens)!=len(after.tokens):fields['structure']=False
    if ''.join(before.visible)!=''.join(after.visible):fields['text']=False
    image_number=0
    for left,right in zip(before.tokens,after.tokens):
        if left[0]not in('start','empty')or left[1]!='img':
            if left!=right:
                if left[0]=='data' and right[0]=='data':fields['text']=False
                else:fields['structure']=False
            continue
        if right[:2]!=left[:2]:fields['structure']=False;continue
        original_attrs=list(left[2]);seen_attrs=list(right[2]);wanted=[];actual_url=None;original_url=None
        for key,value in original_attrs:
            if key=='src':original_url=value
        # Each original img must bind the successful URL at that exact article/index.
        if (original_url is None or any(k=='data-src'for k,_ in original_attrs)
                or image_number>=len(bindings)or bindings[image_number]!=original_url):fields['image_bindings']=False
        for key,value in seen_attrs:
            if key in('src','data-src'):
                if actual_url is not None:fields['image_bindings']=False
                actual_url=value
                wanted.append(('src',value))
            else:wanted.append((key,value))
        if len(wanted)!=len(original_attrs):fields['attributes']=False
        for (lk,lv),(rk,rv)in zip(original_attrs,wanted):
            if lk!=rk or(lk!='src'and lv!=rv):fields['attributes']=False
        address_keys=[key for key,_ in seen_attrs if key in('src','data-src')]
        url_match=original_url is not None and actual_url is not None and _urls(original_url,actual_url)
        url_match=url_match and address_keys==(['src']if actual_url==original_url else['data-src'])
        if not url_match:fields['image_bindings']=False
        transforms=[]
        if url_match:
            if urlsplit(original_url).scheme!=urlsplit(actual_url).scheme:transforms.append('HTTP_TO_HTTPS')
            if urlsplit(original_url).path!=urlsplit(actual_url).path:transforms.append('ZERO_TO_640')
            if any(key=='data-src'for key,_ in seen_attrs):transforms.append('SRC_TO_DATA_SRC')
        image_observations.append({'index':image_number,'representation':transforms or['EXACT']if url_match else['UNVERIFIED']})
        image_number+=1
    return fields, ''.join(before.visible), images, image_observations

def _float32_9(value):
    _need(type(value)is str and _COORD.fullmatch(value)is not None)
    number=struct.unpack('!f',struct.pack('!f',float(value)))[0]
    _need(math.isfinite(number))
    return format(number,'.9f').rstrip('0').rstrip('.')

def _crop(expected,actual):
    _need(type(expected)is dict and type(actual)is dict)
    if set(expected)!= {'crop_percent_list'}or set(actual)!=set(expected):return False
    a,b=expected['crop_percent_list'],actual['crop_percent_list']
    if type(a)is not list or type(b)is not list or len(a)!=2 or len(b)!=2:return False
    if {row.get('ratio')for row in a if type(row)is dict}!={'2.35_1','1_1'}:return False
    for x,y in zip(a,b):
        if type(x)is not dict or type(y)is not dict or set(x)!={'ratio','x1','y1','x2','y2'}or set(y)!=set(x):return False
        for row in(x,y):
            if any(_COORD.fullmatch(row[key])is None for key in('x1','y1','x2','y2')):return False
            if not(Decimal(row['x1'])<Decimal(row['x2'])and Decimal(row['y1'])<Decimal(row['y2'])):return False
        for key in x:
            if type(x[key])is not str or type(y[key])is not str:return False
            if key=='x2'and x['ratio']=='1_1':
                if y[key]not in(x[key],_float32_9(x[key])):return False
            elif x[key]!=y[key]:return False
    return True

def _bounded_inputs(left,right,bindings):
    used=0
    def text(value,maximum):
        nonlocal used
        _need(type(value)is str and len(value)<=maximum)
        used+=len(value.encode('utf-8'));_need(used<=3*MAX_RESPONSE_BYTES)
    limits={'article_type':16,'title':128,'content':MAX_CONTENT_CHARS,'thumb_media_id':128,
            'author':16,'digest':120,'content_source_url':1024}
    for rows in(left,right):
        _need(type(rows)is list and 1<=len(rows)<=MAX_ARTICLES)
        for row in rows:
            _need(type(row)is dict and len(row)<=len(_FIELDS)and set(row)<=_FIELDS)
            for key,value in row.items():
                if key in limits:text(value,limits[key])
                elif key in('need_open_comment','only_fans_can_comment'):
                    _need(type(value)is int and value in(0,1))
                else:
                    _need(type(value)is dict and set(value)=={'crop_percent_list'})
                    crops=value['crop_percent_list'];_need(type(crops)is list and len(crops)==2)
                    for crop in crops:
                        _need(type(crop)is dict and set(crop)=={'ratio','x1','y1','x2','y2'})
                        for item in crop.values():text(item,32)
    _need(type(bindings)is list and len(bindings)==len(left))
    for article in bindings:
        _need(type(article)is list and len(article)<=MAX_CONTENT_CHARS)
        for url in article:text(url,MAX_CONTENT_CHARS)


def compare_platform_representation(expected_projection,actual_projection,successful_image_urls):
    """Return closed observations only. No change to original strict/CAS state.

    URL bindings are list[article][img position], never a global URL allowlist.
    Parse/input failure returns fixed UNVERIFIED data without exception strings.
    """
    result={'profile':PROFILE,'authority':False,'state':'UNVERIFIED','byte_exact':False,
            'platform_representation_match':False,'reason':'INPUT_INVALID','articles':[],
            'projection_digests':{'algorithm':'CANONICAL_JSON_UTF8_SORTED_COMPACT_V1','expected_sha256':None,'actual_sha256':None}}
    try:
        _need(type(expected_projection)is dict and type(actual_projection)is dict
              and len(expected_projection)==len(actual_projection)==1
              and set(expected_projection)==set(actual_projection)=={'articles'})
        left,right=expected_projection['articles'],actual_projection['articles']
        _need(type(left)is list and type(right)is list and 1<=len(left)<=MAX_ARTICLES
              and type(successful_image_urls)is list and len(successful_image_urls)==len(left))
        _bounded_inputs(left,right,successful_image_urls)
        expected_raw=json.dumps(expected_projection,sort_keys=True,separators=(',',':'),ensure_ascii=False,allow_nan=False).encode('utf-8')
        actual_raw=json.dumps(actual_projection,sort_keys=True,separators=(',',':'),ensure_ascii=False,allow_nan=False).encode('utf-8')
        result['projection_digests'].update(expected_sha256=sha256(expected_raw).hexdigest(),actual_sha256=sha256(actual_raw).hexdigest())
        result['byte_exact']=expected_raw==actual_raw
        if len(left)!=len(right):result['reason']='ARTICLE_COUNT';return result
        for index,(expected,actual,bindings)in enumerate(zip(left,right,successful_image_urls)):
            _need(type(expected)is dict and type(actual)is dict and set(expected)<=_FIELDS and set(actual)==set(expected)
                  and {'article_type','title','content','thumb_media_id','digest'}<=set(expected))
            fields={}
            for key in expected:
                if key in('content','digest','cover_info'):continue
                valid=(type(expected[key])is int and expected[key]in(0,1)and type(actual[key])is int)if key in('need_open_comment','only_fans_can_comment')else type(expected[key])is type(actual[key])is str
                fields[key]=bool(valid and expected[key]==actual[key])
            html,visible,image_count,image_observations=_html(expected['content'],actual['content'],bindings)
            fields.update(content_text=html['text'],html_structure=html['structure'],html_attributes=html['attributes'],image_bindings=html['image_bindings'])
            _need(type(expected['digest'])is str and type(actual['digest'])is str)
            fields['digest']=actual['digest']==expected['digest']or(expected['digest']==''and actual['digest']==visible[:54])
            # A recognized server default establishes representation only. It
            # does not satisfy the separate blank-or-manually-edited summary
            # requirement used by this ordinary draft product.
            summary_editorial_state=('SUMMARY_EDITORIAL_MATCHED'
                if actual['digest']==expected['digest'] else
                'SUMMARY_EDITORIAL_NOT_MET' if expected['digest']==''
                    and actual['digest']==visible[:54] else 'SUMMARY_EDITORIAL_UNVERIFIED')
            if 'cover_info'in expected:fields['cover_info']=_crop(expected['cover_info'],actual['cover_info'])
            representations={'digest':('EXACT'if expected['digest']==actual['digest']else'AUTO_DERIVED_54')if fields['digest']else'UNVERIFIED',
                             'images':image_observations}
            if 'cover_info'in expected:
                representations['cover_info']=('EXACT'if expected['cover_info']==actual['cover_info']else'BINARY32_9')if fields['cover_info']else'UNVERIFIED'
            matched=all(fields.values())
            result['articles'].append({'index':index,'matched':matched,'image_count':image_count,
                'fields':fields,'representations':representations,
                'summary_editorial_state':summary_editorial_state})
        result['platform_representation_match']=all(row['matched']for row in result['articles'])
        result['state']='PLATFORM_REPRESENTATION_MATCHED'if result['platform_representation_match']else'UNVERIFIED'
        result['reason']='ALLOWED_DETERMINISTIC_REPRESENTATION'if result['platform_representation_match']else'FIELD_MISMATCH'
        return result
    except (ValueError,TypeError,KeyError,IndexError,OverflowError,RecursionError,UnicodeError,AssertionError):
        result.update(state='UNVERIFIED',platform_representation_match=False,reason='INPUT_INVALID',articles=[])
        return result
