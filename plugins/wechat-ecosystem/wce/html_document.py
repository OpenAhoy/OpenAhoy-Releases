"""Closed HTML fragment language. Parsing grants no authority and performs no IO."""
from copy import deepcopy
from functools import lru_cache
from hashlib import sha256
from html import escape
from html.entities import html5
from html.parser import HTMLParser
import json
import re

from .contracts import WCEError
from .documents import ARTICLE, ASSET, SLOT, safe_url
from .prepared_contracts import strict_validate
from .tools import schema
from .import_styles import POLICY as IMPORT_POLICY, inline_style
from .service import canonical, digest
from .editor_contracts import validate as validate_editorial
from .reading_layout import PROFILE as READING_PROFILE, PARAMETER_SHA256
from .normal_html_limits import (POLICY as NORMAL_POLICY, FRAGMENT_CHARS, FRAGMENT_BYTES, IMAGE_POSITIONS, ROLE_POSITIONS)

POLICY = 'WCE_SAFE_HTML_V1'
HTML_ARTICLE = schema({k: deepcopy(ARTICLE['properties'][k]) for k in ('id','title','cover_asset_ref')} | {
    'content_html': {'type':'string','minLength':1,'maxLength':12000},
    'image_slots': {'type':'array','minItems':0,'maxItems':4,'items':schema({'slot':SLOT,'asset_ref':ASSET})}},
    {k:deepcopy(ARTICLE['properties'][k]) for k in ('author','digest','source_url','cover_info','cover_dimensions','editorial_intent')})
DOCUMENT = schema({'format':{'type':'integer','const':3},'policy':{'type':'string','const':POLICY},
    'articles':{'type':'array','minItems':1,'maxItems':8,'items':HTML_ARTICLE}})
HASH={'type':'string','pattern':'^[a-f0-9]{64}$'}
MIME={'type':'string','enum':['image/png','image/jpeg']}
IMAGE_SOURCE=schema({'slot':SLOT,'role':{'type':'string','enum':['cover','body']},
    'source_sha256':HASH,'transport_sha256':HASH,'source_mime':MIME,'transport_mime':MIME,
    'source_size':{'type':'integer','minimum':1,'maximum':2097152},
    'transport_size':{'type':'integer','minimum':1,'maximum':2097152}})
PROVENANCE=schema({'schema':{'type':'integer','const':1},'source_sha256':HASH,'stylesheet_sha256':HASH,
    'viewport_width':{'type':'integer','const':390},'images':{'type':'array','minItems':2,'maxItems':6,'items':IMAGE_SOURCE},
    'transform_sha256':HASH}, {'layout_profile':{'type':'string','const':READING_PROFILE},
                              'layout_profile_sha256':HASH})
IMPORTED_ARTICLE=deepcopy(HTML_ARTICLE)
IMPORTED_ARTICLE['properties'].update(style_policy={'type':'string','const':IMPORT_POLICY},provenance=PROVENANCE)
IMPORTED_ARTICLE['properties']['content_html']['maxLength']=24000
IMPORTED_ARTICLE['properties']['image_slots']['maxItems']=5
IMPORTED_ARTICLE['required']+=['style_policy','provenance']
IMPORTED_DOCUMENT=schema({'format':{'type':'integer','const':3},'policy':{'type':'string','const':IMPORT_POLICY},
    'articles':{'type':'array','minItems':1,'maxItems':8,'items':IMPORTED_ARTICLE}})
NORMAL_ARTICLE=deepcopy(IMPORTED_ARTICLE)
NORMAL_ARTICLE['properties']['style_policy']['const']=NORMAL_POLICY
NORMAL_ARTICLE['properties']['content_html'].update(maxLength=FRAGMENT_CHARS, **{'x-wce-maxUtf8Bytes':FRAGMENT_BYTES})
NORMAL_ARTICLE['properties']['image_slots']['maxItems']=IMAGE_POSITIONS
NORMAL_ARTICLE['properties']['provenance']['properties']['schema']['const']=2
NORMAL_ARTICLE['properties']['provenance']['properties']['images']['maxItems']=ROLE_POSITIONS
NORMAL_DOCUMENT=schema({'format':{'type':'integer','const':3},'policy':{'type':'string','const':NORMAL_POLICY},
    'articles':{'type':'array','minItems':1,'maxItems':8,'items':NORMAL_ARTICLE}})
DERIVED = {'canonical_html','source_sha256','canonical_sha256','canonical_changed'}
TAGS = {'section','p','h2','h3','span','strong','em','br','blockquote','ul','ol','li','hr','a','img'}
VOID = {'br','hr','img'}
INLINE = {'span','strong','em','br','a','img'}
INLINE_PARENTS = {'p','h2','h3','span','strong','em','a'}
# This lexical gate supplements the structural parser. It never removes input.
START = re.compile(r'''<([A-Za-z][A-Za-z0-9]*)(?:[ \t\n]+[A-Za-z][A-Za-z0-9-]*[ \t\n]*=[ \t\n]*(?:"[^"<>]*"|'[^'<>]*'))*[ \t\n]*/?>''')
ENTITY = re.compile(r'&(#x[0-9a-fA-F]+|#[0-9]+|[A-Za-z][A-Za-z0-9]+);')
COLOR = re.compile(r'(?:#[0-9a-f]{3}|#[0-9a-f]{6}|black|white)')


def fail(code='HTML_INVALID', position=(1,0)):
    error=WCEError(code)
    error.line, error.column=min(max(position[0],1),12001),min(max(position[1]+1,1),12001)
    raise error


_TEXT_CONTROL = re.compile(r'[\x00-\x08\x0b-\x1f\x7f-\x9f\ufffd\ud800-\udfff]')


def clean_text(value, position):
    match = _TEXT_CONTROL.search(value)
    if match is not None:
        index = match.start()
        prefix=value[:index];lines=prefix.count('\n')
        actual=(position[0]+lines,len(prefix.rsplit('\n',1)[-1]) if lines else position[1]+index)
        fail('HTML_CONTROL_CHARACTER',actual)
    return value


def entity_value(name,position):
    try:
        if name.startswith(('#x','#X')): value=chr(int(name[2:],16))
        elif name.startswith('#'): value=chr(int(name[1:],10))
        else: value=html5[name+';']
        if '\x00' in value: raise ValueError()
        return clean_text(value,position)
    except (ValueError,KeyError,OverflowError): fail('HTML_ENTITY',position)


def check_entities(raw,position):
    index=0
    while True:
        index=raw.find('&',index)
        if index<0:return
        prefix=raw[:index];lines=prefix.count('\n')
        actual=(position[0]+lines, len(prefix.rsplit('\n',1)[-1]) if lines else position[1]+index)
        match=ENTITY.match(raw,index)
        if not match:fail('HTML_ENTITY',actual)
        entity_value(match[1],actual);index=match.end()


def number(value,low,high,unit='px'):
    pattern=r'(?:0|[1-9][0-9]*)(?:\.[0-9]{1,2})?'
    if unit:
        if not value.endswith(unit):return False
        value=value[:-len(unit)]
    return bool(re.fullmatch(pattern,value)) and low<=float(value)<=high


def css(value,tag,position):
    if len(value.encode())>1024 or any(c in value for c in '\\/@()\"\'<>'):
        fail('HTML_CSS_UNSUPPORTED',position)
    result=[];seen=set()
    declarations=value.split(';')
    if declarations[-1].strip()=='':declarations.pop()
    for declaration in declarations:
        if declaration.count(':')!=1:fail('HTML_CSS_UNSUPPORTED',position)
        prop,val=(v.strip().lower() for v in declaration.split(':',1))
        val=' '.join(val.split())
        if prop in seen:fail('HTML_CSS_DUPLICATE',position)
        seen.add(prop)
        valid=False
        if prop=='font-size':valid=number(val,10,36)
        elif prop=='line-height':valid=number(val,1,3,'') or number(val,12,72)
        elif prop=='letter-spacing':valid=number(val,0,2)
        elif prop in ('color','background-color'):valid=bool(COLOR.fullmatch(val))
        elif prop in ('font-weight','font-style','text-align','text-decoration','white-space','overflow-wrap','word-break'):
            valid=val in {'font-weight':{'normal','bold','400','500','600','700'},'font-style':{'normal','italic'},
                'text-align':{'left','center','right','justify'},'text-decoration':{'none','underline'},
                'white-space':{'normal','pre-wrap'},'overflow-wrap':{'normal','anywhere','break-word'},
                'word-break':{'normal','break-word','break-all'}}[prop]
        elif prop in ('margin','margin-top','margin-bottom','margin-left','margin-right','padding','padding-top','padding-bottom','padding-left','padding-right'):
            values=val.split();valid=1<=len(values)<=(4 if prop in ('margin','padding') else 1)
            # auto only represents horizontal margins; shorthand expands CSS 1..4 rules.
            expanded=(values*4)[:4] if len(values)==1 else [values[0],values[1],values[0],values[1]] if len(values)==2 else [values[0],values[1],values[2],values[1]] if len(values)==3 else values
            for index,item in enumerate(expanded if prop in ('margin','padding') else values):
                valid=valid and (item=='0' or number(item,0,64 if prop.startswith('margin') else 48)
                    or item=='auto' and (prop in ('margin-left','margin-right') or prop=='margin' and index in (1,3)))
        elif prop in ('border','border-left','border-top'):
            pieces=val.split();valid=val=='0' or len(pieces)==3 and number(pieces[0],1,4) and pieces[1]=='solid' and bool(COLOR.fullmatch(pieces[2]))
        elif prop=='border-radius':valid=val=='0' or number(val,0,24)
        elif tag=='img' and prop=='width':valid=number(val,1,100,'%') or number(val,1,1024)
        elif tag=='img' and prop=='max-width':valid=val=='100%'
        elif tag=='img' and prop=='height':valid=val=='auto'
        elif tag=='img' and prop=='display':valid=val in ('block','inline-block')
        if not valid:fail('HTML_CSS_UNSUPPORTED',position)
        result.append(prop+':'+val)
    if not result:fail('HTML_CSS_UNSUPPORTED',position)
    if tag=='a' and not {'color','text-decoration'}<=seen:fail('HTML_LINK_STYLE_REQUIRED',position)
    return ';'.join(result)+';'


def check_tokens(source):
    index=0
    while True:
        index=source.find('<',index)
        if index<0:return
        prefix=source[:index]
        position=(prefix.count('\n')+1,len(prefix.rsplit('\n',1)[-1]))
        match=(re.compile(r'</[A-Za-z][A-Za-z0-9]*[ \t\n]*>').match(source,index)
               if source.startswith('</',index) else START.match(source,index))
        if not match:fail('HTML_SYNTAX',position)
        index=match.end()


class Fragment(HTMLParser):
    def __init__(self,source,allowed_sources=None,policy=POLICY):
        super().__init__(convert_charrefs=False)
        if type(source) is not str:fail()
        try:size=len(source.encode('utf-8'))
        except UnicodeError:fail('HTML_CONTROL_CHARACTER')
        if policy not in (POLICY,IMPORT_POLICY,NORMAL_POLICY):fail()
        self.normal = policy == NORMAL_POLICY
        if not 0<size<=(48*1024*1024 if allowed_sources is not None else FRAGMENT_BYTES if self.normal else 24000 if policy==IMPORT_POLICY else 12000):fail('HTML_LIMIT')
        clean_text(source,(1,0));check_entities(source,(1,0));check_tokens(source)
        self.source=source;self.allowed_sources=allowed_sources;self.policy=policy
        self.root={'tag':'','attrs':{},'children':[]};self.stack=[self.root]
        self.count=0;self.slots=[];self.text=[]
        self.offsets=[0]
        for match in re.finditer('\n',source):self.offsets.append(match.end())
        self.feed(source);self.close()
        if len(self.stack)!=1:fail('HTML_UNCLOSED_TAG',self.getpos())
        if not ''.join(self.text).strip():fail('HTML_EMPTY')

    def add(self,value):
        self.count+=1
        if not self.normal and self.count>512:fail('HTML_DOM_LIMIT',self.getpos())
        self.stack[-1]['children'].append(value)

    def _validated_style(self,value,tag,position):
        return inline_style(value,tag,position) if self.policy in (IMPORT_POLICY,NORMAL_POLICY) else css(value,tag,position)

    def handle_starttag(self,tag,attrs):
        pos=self.getpos();raw=self.get_starttag_text()
        if not START.fullmatch(raw) or tag not in (TAGS|{'h1'} if self.policy in (IMPORT_POLICY,NORMAL_POLICY) else TAGS):fail('HTML_TAG_UNSUPPORTED',pos)
        names=[k for k,_ in attrs]
        if len(attrs)>3 or len(set(names))!=len(names):fail('HTML_ATTRIBUTES',pos)
        allowed={'style'}|({'href'} if tag=='a' else {'src','alt'} if tag=='img' else set())
        if set(names)-allowed:fail('HTML_ATTRIBUTES',pos)
        parent=self.stack[-1]['tag']
        if (parent in INLINE_PARENTS|{'h1'} and tag not in INLINE or tag=='li' and parent not in ('ul','ol')
                or parent in ('ul','ol') and tag!='li' or tag=='a' and any(n['tag']=='a' for n in self.stack)):
            fail('HTML_NESTING',pos)
        values={}
        for key,val in attrs:
            if val is None or len(val.encode())>(3*1024*1024 if key=='src' and self.allowed_sources is not None else 2048 if key=='style' and self.policy in (IMPORT_POLICY,NORMAL_POLICY) else 1024):fail('HTML_ATTRIBUTES',pos)
            clean_text(val,pos)
            if key=='style':val=self._validated_style(val,tag,pos)
            elif key=='href':
                try:safe_url(val)
                except WCEError:fail('HTML_LINK',pos)
            values[key]=val
        if tag=='a' and ('href' not in values or 'style' not in values):fail('HTML_LINK_STYLE_REQUIRED',pos)
        if tag=='img':
            if not {'src','alt'}<=set(values):fail('HTML_IMAGE_BINDING',pos)
            src=values['src']
            if self.allowed_sources is None:
                match=re.fullmatch(r'wce-asset:([A-Za-z0-9_-]{1,32})',src)
                if not match or match[1]=='cover':fail('HTML_IMAGE_BINDING',pos)
                self.slots.append(match[1])
            elif src not in self.allowed_sources:fail('HTML_IMAGE_BINDING',pos)
        node={'tag':tag,'attrs':values,'children':[]};self.add(node)
        if tag not in INLINE:self.text.append(' ')
        if tag=='br':self.text.append(' ')
        if tag not in VOID:
            if not self.normal and len(self.stack)>=17:fail('HTML_DEPTH_LIMIT',pos)
            self.stack.append(node)

    def handle_startendtag(self,tag,attrs):
        if tag not in VOID:fail('HTML_NESTING',self.getpos())
        self.handle_starttag(tag,attrs)

    def handle_endtag(self,tag):
        pos=self.getpos();offset=self.offsets[pos[0]-1]+pos[1]
        end=self.source.find('>',offset)
        raw=self.source[offset:end+1]
        if not re.fullmatch(r'</[A-Za-z][A-Za-z0-9]*[ \t\n]*>',raw):fail('HTML_NESTING',pos)
        if tag in VOID or len(self.stack)==1 or self.stack[-1]['tag']!=tag:fail('HTML_NESTING',pos)
        self.stack.pop()
        if tag not in INLINE:self.text.append(' ')

    def data(self,data,entity=False):
        if '<' in data and not entity:fail('HTML_SYNTAX',self.getpos())
        clean_text(data,self.getpos())
        if self.stack[-1]['tag'] in ('ul','ol') and data.strip():fail('HTML_NESTING',self.getpos())
        if data:self.add(data);self.text.append(data)

    def handle_data(self,data):self.data(data)
    def handle_entityref(self,name):self.data(entity_value(name,self.getpos()),True)
    def handle_charref(self,name):self.data(entity_value('#'+name,self.getpos()),True)
    def handle_comment(self,data):fail('HTML_COMMENT_UNSUPPORTED',self.getpos())
    def handle_decl(self,data):fail('HTML_DECLARATION_UNSUPPORTED',self.getpos())
    def unknown_decl(self,data):fail('HTML_DECLARATION_UNSUPPORTED',self.getpos())
    def handle_pi(self,data):fail('HTML_DECLARATION_UNSUPPORTED',self.getpos())


def serialize(node,urls=None,preview=False):
    # Explicit traversal also serves normal HTML deeper than Python's call stack.
    parts=[];pending=[(node,False)]
    while pending:
        item,closing=pending.pop()
        if isinstance(item,str):parts.append(escape(item,quote=False));continue
        tag=item['tag']
        if closing:
            if tag and tag not in VOID:parts.append('</'+('span' if tag=='a' and preview else tag)+'>')
            continue
        attrs=dict(item['attrs'])
        if tag=='img' and urls is not None:attrs['src']=urls[attrs['src'][len('wce-asset:'):]]
        emitted=tag
        if tag=='a' and preview:emitted='span';attrs.pop('href')
        if tag:
            text=''.join(' '+k+'="'+escape(v,quote=True)+'"' for k,v in sorted(attrs.items()))
            parts.append('<'+emitted+text+'>')
        pending.append((item,True))
        pending.extend((child,False) for child in reversed(item['children']))
    return ''.join(parts)


def _normalize(value):
    original=deepcopy(value);derived=[]
    if type(original) is not dict or type(original.get('articles')) is not list:fail()
    for article in original['articles']:
        if type(article) is not dict:fail()
        present=DERIVED&set(article)
        if present and present!=DERIVED:fail()
        derived.append({k:article.pop(k) for k in present})
    normal=original.get('policy')==NORMAL_POLICY
    imported=original.get('policy') in (IMPORT_POLICY,NORMAL_POLICY)
    strict_validate(original,NORMAL_DOCUMENT if normal else IMPORTED_DOCUMENT if imported else DOCUMENT,-16)
    ids=set();result=deepcopy(original);raw_total=canonical_total=total_nodes=0
    for index,article in enumerate(result['articles']):
        if article['id'] in ids or not article['title'].strip():fail()
        ids.add(article['id'])
        from .html_technical_standard import validate_metadata
        validate_metadata(article,article_count=len(result['articles']))
        validate_editorial(article)
        if article.get('source_url'):safe_url(article['source_url'])
        raw=article['content_html'];parsed=Fragment(raw,policy=NORMAL_POLICY if normal else IMPORT_POLICY if imported else POLICY);normalized=serialize(parsed.root)
        slots=article['image_slots'];names=[s['slot'] for s in slots]
        refs=[article['cover_asset_ref']]+[s['asset_ref'] for s in slots]
        if (len(set(names))!=len(names) or len(set(refs))!=len(refs) or len(set(parsed.slots))!=len(parsed.slots)
                or set(names)!=set(parsed.slots)):fail('HTML_IMAGE_BINDING')
        raw_total+=len(raw.encode());canonical_total+=len(normalized.encode());total_nodes+=parsed.count
        group_limit = 8 * 24000 if imported else 40000
        if (not normal and (len(normalized.encode())>(24000 if imported else 12000) or raw_total>group_limit or canonical_total>group_limit or total_nodes>2048)
                or normal and (len(normalized)>FRAGMENT_CHARS or len(normalized.encode())>FRAGMENT_BYTES)):fail('HTML_LIMIT')
        if normal:
            from .normal_html_limits import final_content
            final_content(serialize(parsed.root,{slot:'' for slot in parsed.slots}))
        if imported:validate_provenance(article,parsed.slots,normalized)
        actual={'canonical_html':normalized,'source_sha256':sha256(raw.encode()).hexdigest(),
            'canonical_sha256':sha256(normalized.encode()).hexdigest(),'canonical_changed':raw!=normalized}
        if derived[index] and (type(derived[index]['canonical_changed']) is not bool or derived[index]!=actual):fail('HTML_CANONICAL_MISMATCH')
        article.update(actual)
    return result


_GROUP_CACHE_JSON_LIMIT = 512 * 1024


def _native_group_json(value):
    """Do not let JSON-coercible Python subclasses bypass strict input types."""
    stack = [(value, 1)]
    nodes = 0
    while stack:
        item, depth = stack.pop()
        nodes += 1
        if nodes > 4096 or depth > 16:
            return False
        kind = type(item)
        if kind is dict:
            stack.extend((x, depth + 1) for x in [*item.keys(), *item.values()])
        elif kind is list:
            stack.extend((x, depth + 1) for x in item)
        elif kind not in (str, int, float, bool, type(None)):
            return False
    return True


@lru_cache(maxsize=2)
def _normalized_group_json(raw):
    # Cache only successful pure normalization, never an identity/DB decision.
    # At most two keys and outputs, each <=512KiB: <=2MiB retained UTF8 data.
    result = canonical(_normalize(json.loads(raw)))
    if len(result.encode()) > _GROUP_CACHE_JSON_LIMIT:
        raise ValueError('UNCACHEABLE_GROUP')
    return result


def normalize(value):
    if (type(value) is dict and value.get('policy') == IMPORT_POLICY
            and type(value.get('articles')) is list and 2 <= len(value['articles']) <= 8
            and _native_group_json(value)):
        try:
            raw = canonical(value)
            if len(raw.encode()) <= _GROUP_CACHE_JSON_LIMIT:
                # A new object prevents a caller from mutating cached state.
                return json.loads(_normalized_group_json(raw))
        except (ValueError, TypeError, RecursionError):
            pass
    return _normalize(value)


def assets(document):
    for article in document['articles']:
        yield article['id']+'--cover',article['cover_asset_ref'],'cover'
        for slot in article['image_slots']:
            yield article['id']+'--'+slot['slot'],slot['asset_ref'],'body'


def transformation(provenance,canonical_html):
    return digest({'policy':NORMAL_POLICY if provenance.get('schema')==2 else IMPORT_POLICY,'canonical_html':canonical_html,
                   'provenance':{k:v for k,v in provenance.items() if k!='transform_sha256'}})


def validate_provenance(article,slots,canonical_html):
    p=article['provenance'];records=p['images']
    if ('layout_profile' in p)!=('layout_profile_sha256' in p) or ('layout_profile' in p and
            (p['layout_profile']!=READING_PROFILE or p['layout_profile_sha256']!=PARAMETER_SHA256)):
        fail('HTML_IMPORT_LAYOUT_PROFILE')
    if ([r['slot'] for r in records]!=['cover',*slots] or
        [s['slot'] for s in article['image_slots']]!=slots or len(records)!=len({r['slot'] for r in records}) or
        records[0]['role']!='cover' or any(r['role']!='body' or r['transport_size']>=1000000 for r in records[1:]) or
        records[0]['source_sha256']!=records[1]['source_sha256'] or
        p['transform_sha256']!=transformation(p,canonical_html)):
        fail('HTML_IMPORT_SOURCE_BINDING')


def visible_text(article):return ''.join(Fragment(article['canonical_html'],policy=article.get('style_policy',POLICY)).text)


def render(article,urls,preview=False):
    policy=article.get('style_policy',POLICY)
    parsed=Fragment(article['canonical_html'],policy=policy)
    mapping={slot:urls[article['id']+'--'+slot] for slot in parsed.slots}
    if not preview:
        for value in mapping.values():safe_url(value)
    result=serialize(parsed.root,mapping,preview)
    # Validate the actual emitted fragment, not only its placeholder input.
    Fragment(result,set(mapping.values()),policy)
    return result
