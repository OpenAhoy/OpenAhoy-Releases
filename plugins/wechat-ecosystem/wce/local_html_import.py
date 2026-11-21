"""Bounded, trusted-host full-page acquisition. No account or MCP file route."""
import base64
from copy import deepcopy
from hashlib import sha256
from html import escape
from html.parser import HTMLParser
import re

from .bounded_file import FileSource, MAX_ASSET_BYTES, MAX_SOURCE_HTML_BYTES
from .contracts import WCEError
from .documents import safe_url
from .html_document import Fragment, serialize, check_tokens, check_entities, clean_text, transformation
from .import_styles import POLICY, TAGS, INHERITED, INLINE_FONT, stylesheet, computed, inline_style, figure_width, declarations

MAX_BODY_IMAGES = 5


def fail(code='HTML_IMPORT_STRUCTURE',position=(1,0)):
    error=WCEError(code);error.line,error.column=position[0],position[1]+1
    raise error


class Page(HTMLParser):
    def __init__(self,raw,metadata_title=None,*,normal=False):
        super().__init__(convert_charrefs=False)
        self.normal=normal
        if type(raw) is not bytes or not raw or (not normal and len(raw)>MAX_SOURCE_HTML_BYTES): fail('HTML_IMPORT_LIMIT')
        try: text=raw.decode('utf-8',errors='strict')
        except UnicodeError: fail('HTML_IMPORT_ENCODING')
        if not text.startswith('<!doctype html>'): fail()
        clean_text(text,(1,0));check_tokens(text[len('<!doctype html>'):]);check_entities(text,(1,0))
        self.root={'tag':'','attrs':{},'children':[]};self.stack=[self.root];self.nodes=0;self.declared=False
        self.feed(text);self.close()
        if len(self.stack)!=1 or not self.declared:fail()
        outer=self.elements(self.root)
        if len(outer)!=1 or outer[0]['tag']!='html':fail()
        html=outer[0]
        if html['attrs']!={'lang':'zh-CN'}:fail()
        children=self.elements(html);self.differences=[]
        explicit_head=bool(children and children[0]['tag']=='head')
        if explicit_head:
            head=self.elements(children.pop(0))
        else:
            self.differences.append('implicit_head');head=[]
            while children and children[0]['tag'] in ('meta','title','style'):head.append(children.pop(0))
        self.inline_body=False;self.inline_article=False
        if (not explicit_head and [n['tag'] for n in head]==['meta'] and head[0]['attrs']=={'charset':'utf-8'}
                and len(children)==1 and children[0]['tag']=='body' and 'style' in children[0]['attrs']):
            self._inline_page(children[0],metadata_title)
            return
        tags=[n['tag'] for n in head]
        if explicit_head and tags==['meta','meta','title']:
            if (head[0]['attrs']!={'charset':'utf-8'} or head[1]['attrs'].get('name')!='viewport'
                    or set(head[1]['attrs'])!={'name','content'}
                    or not re.fullmatch(r'width=device-width, *initial-scale=1',head[1]['attrs']['content'])
                    or len(children)!=1 or children[0]['tag']!='body'):
                fail()
            self._inline_article_page(head[2],children[0],metadata_title)
            return
        if tags==['meta','meta','title','style']:
            if head[1]['attrs']!={'name':'viewport','content':'width=device-width,initial-scale=1'}:fail()
            title_index=2
        elif tags==['meta','title','style']:
            title_index=1
            self.differences.append('missing_viewport_fixed_390_projection')
        else:fail()
        if head[0]['attrs']!={'charset':'utf-8'}:fail()
        self.source_title=self.only_text(head[title_index]);self.sheet=self.only_text(head[title_index+1])
        if metadata_title is None:
            self.title=self.source_title
        else:
            if (type(metadata_title) is not str or not metadata_title.strip()
                    or len(metadata_title)>32 or len(metadata_title.encode())>128
                    or not self.source_title.strip() or len(self.source_title)>128 or len(self.source_title.encode())>512):
                fail('HTML_IMPORT_TITLE')
            clean_text(metadata_title,(1,0))
            self.title=metadata_title
        if not self.title.strip() or len(self.title)>32 or len(self.title.encode())>128:fail('HTML_IMPORT_TITLE')
        if len(children)==1 and children[0]['tag']=='body':children=self.elements(children[0])
        else:self.differences.append('implicit_body')
        if len(children)!=1 or children[0]['tag']!='article':fail()
        self.article=children[0]
        self._stylesheet_attributes(html)
        self.differences+=['mobile_viewport_390_padding16_not_responsive','article_vertical_auto_margin_to_zero',
                           'article_to_section','body_to_outer_section','stylesheet_cascade_to_inline',
                           'platform_css_retention_and_word_visual_unverified']

    @staticmethod
    def _stylesheet_attributes(node):
        """The inline form's attributes never widen the original page form."""
        pending=[node]
        while pending:
            item=pending.pop()
            if isinstance(item,str):continue
            tag=item['tag'];attrs=item['attrs']
            if tag in ('body','article','p','h2','img') and 'style' in attrs:fail(position=item['position'])
            if tag=='img' and set(attrs)!={'src','alt'}:fail(position=item['position'])
            pending.extend(item['children'])

    @staticmethod
    def _fixed_inline_style(node,expected,*,normal=False):
        raw=node['attrs'].get('style')
        if type(raw) is not str or not raw or (not normal and len(raw.encode())>8192):fail()
        parts=raw.split(';')
        if not parts[-1].strip():parts.pop()
        if not 1<=len(parts)<=32:fail('HTML_IMPORT_CSS_UNSUPPORTED',node['position'])
        values={}
        for part in parts:
            if part.count(':')!=1:fail()
            key,value=(p.strip() for p in part.split(':',1))
            if key in values:fail()
            values[key]=value
        if values!=expected:fail('HTML_IMPORT_CSS_UNSUPPORTED',node['position'])

    def _inline_page(self,body,metadata_title):
        """One finite inline source form; no permissive parser fallback."""
        if type(metadata_title) is not str or not metadata_title.strip() or len(metadata_title)>32 or len(metadata_title.encode())>128:
            fail('HTML_IMPORT_TITLE')
        clean_text(metadata_title,(1,0))
        if body['attrs'].keys()!={'style'}:fail()
        self._fixed_inline_style(body,{'max-width':'680px','margin':'auto','color':'#273536',
            'font-family':INLINE_FONT,'font-size':'16px','line-height':'1.8'},normal=self.normal)
        children=self.elements(body)
        if not children:fail()
        for node in children:
            tag=node['tag'];attrs=node['attrs']
            if tag in ('h2','p'):
                if set(attrs)!={'style'}:fail(position=node['position'])
                self.only_text(node)
                self._fixed_inline_style(node,{'color':'#173f51','font-size':'21px'} if tag=='h2' else {'margin':'1.2em 0'},normal=self.normal)
            elif tag=='img':
                if set(attrs)!={'src','style'} or node['children']:fail(position=node['position'])
                self._fixed_inline_style(node,{'width':'100%'},normal=self.normal)
            else:fail(position=node['position'])
        style_bytes=sum(len(node['attrs']['style'].encode()) for node in (body,*children))
        # The fixed body has nine expanded declarations. Every paragraph has
        # four margin sides; headings and images have two and one respectively.
        expanded=9+sum({'h2':2,'p':4,'img':1}[node['tag']] for node in children)
        if not self.normal and (style_bytes>8192 or expanded>256):fail('HTML_IMPORT_CSS_UNSUPPORTED')
        self.inline_body=True;self.body=body;self.article=body
        self.title=metadata_title;self.source_title='';self.sheet=''
        self.differences+=['inline_fullpage_fixed_390_projection','body_vertical_auto_margin_to_zero',
            'body_to_outer_section','inline_p_1.2em_at_16px_to_19.2px','missing_source_title_uses_metadata_title',
            'missing_image_alt_to_empty','platform_css_retention_and_word_visual_unverified']

    def inline_projection(self,node):
        if self.inline_article:return deepcopy(self.inline_styles[id(node)])
        if node['tag']=='body':
            return {'max-width':'680px','margin-top':'0','margin-bottom':'0','margin-left':'auto',
                'margin-right':'auto','color':'#273536','font-family':INLINE_FONT,'font-size':'16px','line-height':'1.8'}
        if node['tag']=='h2':return {'color':'#173f51','font-size':'21px'}
        if node['tag']=='p':return {'margin-top':'19.2px','margin-bottom':'19.2px','margin-left':'0','margin-right':'0'}
        if node['tag']=='img':return {'width':'100%'}
        fail()

    def _inline_article_page(self,title,body,metadata_title):
        """Finite fully inline source form, with no stylesheet fallback."""
        source_title=self.only_text(title)
        if (not source_title.strip() or len(source_title)>128 or len(source_title.encode())>512):
            fail('HTML_IMPORT_TITLE')
        selected=source_title if metadata_title is None else metadata_title
        if (type(selected) is not str or not selected.strip() or len(selected)>32
                or len(selected.encode())>128):fail('HTML_IMPORT_TITLE')
        clean_text(selected,(1,0))
        children=self.elements(body)
        if (set(body['attrs'])!={'style'} or len(children)!=1 or children[0]['tag']!='article'
                or set(children[0]['attrs'])!={'style'}):fail()
        article=children[0];styles={};style_bytes=0;expanded=0
        def visit(node):
            nonlocal style_bytes,expanded
            if isinstance(node,str):return
            tag=node['tag'];attrs=node['attrs']
            allowed={'src','alt','style'} if tag=='img' else {'href'} if tag=='a' else {'style'}
            if set(attrs)-allowed or (tag=='img' and not {'src','alt'}<=set(attrs)):
                fail(position=node['position'])
            if tag=='article' and node is not article:fail(position=node['position'])
            values={}
            if 'style' in attrs:
                text=attrs['style'];pairs=declarations(text,tag,node['position'],normal=self.normal)
                if len({key for key,_ in pairs})!=len(pairs):fail('HTML_IMPORT_CSS_UNSUPPORTED',node['position'])
                values=dict(pairs);style_bytes+=len(text.encode());expanded+=len(pairs)
                # Recheck the same canonical language, including paired flex
                # declarations and the complete declaration/length bounds.
                inline_style(''.join(key+':'+val+';' for key,val in sorted(values.items())),
                    'section' if tag in ('article','body') else tag,node['position'])
            styles[id(node)]=values
        pending=[body]
        while pending:
            current=pending.pop();visit(current)
            if not isinstance(current,str):pending.extend(reversed(current['children']))
        if not self.normal and (style_bytes>8192 or expanded>256):fail('HTML_IMPORT_CSS_UNSUPPORTED')
        self.inline_body=True;self.inline_article=True;self.inline_styles=styles
        self.body=body;self.article=article;self.title=selected;self.source_title=source_title;self.sheet=''
        self.differences+=['inline_article_fullpage_fixed_390_projection','validated_inline_css_expanded',
            'article_vertical_auto_margin_to_zero','article_to_section','body_to_outer_section',
            'platform_css_retention_and_word_visual_unverified']

    @staticmethod
    def elements(node):
        if any(isinstance(n,str) and n.strip() for n in node['children']):fail()
        return [n for n in node['children'] if not isinstance(n,str)]

    @staticmethod
    def only_text(node):
        if any(not isinstance(n,str) for n in node['children']):fail()
        return ''.join(node['children'])

    def add(self,node):
        self.nodes+=1
        if not self.normal and self.nodes>512:fail('HTML_DOM_LIMIT',self.getpos())
        self.stack[-1]['children'].append(node)

    def handle_starttag(self,tag,attrs):
        if tag not in {'html','head','meta','title','style','body',*TAGS-{'section'}}:fail(position=self.getpos())
        names=[x for x,_ in attrs]
        if len(names)>3 or len(set(names))!=len(names):fail(position=self.getpos())
        allowed={'lang'} if tag=='html' else {'charset','name','content'} if tag=='meta' else {'src','alt','style'} if tag=='img' else {'href'} if tag=='a' else {'class','style'} if tag in ('p','h2') else {'class','style'} if tag=='figure' else {'style'} if tag in ('body','article') else set()
        if set(names)-allowed or any(v is None for _,v in attrs):fail(position=self.getpos())
        values=dict(attrs)
        if tag=='p' and values.get('class','') not in ('','source','caption','backend'):fail(position=self.getpos())
        if tag=='h2' and values.get('class','') not in ('','sources-title'):fail(position=self.getpos())
        if tag=='figure':
            if self.stack[-1]['tag']!='article' or values.get('class','') not in ('','narrow'):fail(position=self.getpos())
            if 'style' in values:
                if values.get('class')!='narrow':fail(position=self.getpos())
                figure_width(values['style'],self.getpos())
        if tag=='figcaption' and self.stack[-1]['tag']!='figure':fail(position=self.getpos())
        if tag=='a':
            if set(values)!={'href'}:fail(position=self.getpos())
            safe_url(values['href'])
        if tag=='img' and ('src' not in values or len(values.get('alt','').encode())>1024):fail(position=self.getpos())
        if tag=='meta' and self.stack[-1]['tag'] not in ('html','head'):fail()
        if tag in ('title','style') and self.stack[-1]['tag'] not in ('html','head'):fail()
        image_paragraph = (tag=='img' and self.stack[-1]['tag']=='p'
                           and len(self.stack)>=2 and self.stack[-2]['tag']=='article')
        if (self.stack[-1]['tag'] in ('p','h1','h2','h3','span','strong','em','a')
                and tag not in ('span','strong','em','a','br') and not image_paragraph):fail()
        if tag=='a' and any(n['tag']=='a' for n in self.stack):fail()
        node={'tag':tag,'attrs':values,'children':[],'position':self.getpos()};self.add(node)
        if tag not in ('meta','img','br'):
            if not self.normal and len(self.stack)>=17:fail('HTML_DEPTH_LIMIT',self.getpos())
            self.stack.append(node)

    def handle_startendtag(self,tag,attrs):
        if tag not in ('meta','img','br'):fail()
        self.handle_starttag(tag,attrs)

    def handle_endtag(self,tag):
        if len(self.stack)==1 or self.stack[-1]['tag']!=tag:fail(position=self.getpos())
        if tag=='p':
            children=self.stack[-1]['children']
            if any(isinstance(child,dict) and child['tag']=='img' for child in children):
                content=[child for child in children if not isinstance(child,str) or child.strip()]
                if len(content)!=1 or not isinstance(content[0],dict) or content[0]['tag']!='img':
                    fail(position=self.getpos())
        self.stack.pop()

    def handle_data(self,data):
        clean_text(data,self.getpos())
        if data:self.add(data)
    def handle_entityref(self,name):
        from .html_document import entity_value
        self.handle_data(entity_value(name,self.getpos()))
    def handle_charref(self,name): self.handle_entityref('#'+name)
    def handle_decl(self,data):
        if self.declared or self.root['children'] or data!='doctype html':fail()
        self.declared=True
    def handle_comment(self,data):fail()
    def unknown_decl(self,data):fail()
    def handle_pi(self,data):fail()


def convert(raw,images,*,metadata_title=None,layout_profile='source',relative_image_paths=None):
    """Pure parser. `images` contains previously acquired exact authorized bytes."""
    from .reading_layout import apply, PROFILE, PARAMETER_SHA256
    if (type(images) not in (list,tuple) or not 1<=len(images)<=MAX_BODY_IMAGES
            or any(type(image) is not dict or image.get('mime') not in ('image/png','image/jpeg')
                or type(image.get('raw')) is not bytes or not 0<len(image['raw'])<=MAX_ASSET_BYTES
                for image in images)):
        fail('HTML_IMPORT_IMAGE')
    if relative_image_paths is not None:
        if (type(relative_image_paths) is not tuple or len(relative_image_paths)!=len(images)
                or any(type(path) is not str for path in relative_image_paths)
                or len(set(relative_image_paths))!=len(relative_image_paths)):
            fail('HTML_IMPORT_SOURCE_BINDING')
        for path in relative_image_paths:
            if (type(path) is not str or not path or len(path)>4096 or path.startswith('/')
                    or ':' in path or '\\' in path or any(ord(c)<32 or ord(c)==127 for c in path)
                    or len(path.split('/'))>16 or any(part in {'','.','..'} for part in path.split('/'))):
                fail('HTML_IMPORT_SOURCE_BINDING')
    page=Page(raw,metadata_title);rules=[] if page.inline_body else stylesheet(page.sheet,390)
    body=page.body if page.inline_body else {'tag':'body','attrs':{},'children':[]}
    body_style=apply(body,page.inline_projection(body) if page.inline_body else computed(body,[],{},rules),layout_profile)
    root={'tag':'section','attrs':{'style':inline_style(''.join(p+':'+v+';' for p,v in sorted(body_style.items())),'section')},'children':[]}
    used=[]; text=[]
    def visit(node,parent_style,ancestors):
        if isinstance(node,str):text.append(node);return node
        if node['tag'] not in TAGS-{'body','section'}:fail(position=node['position'])
        if node['tag']=='article' and ancestors!=[body]:fail(position=node['position'])
        styled={'tag':'p','attrs':{'class':'caption'}} if node['tag']=='figcaption' else node
        style=computed(node,ancestors,parent_style,rules)
        if page.inline_body:
            if not page.inline_article and node['tag']=='p' and parent_style.get('font-size')!='16px':fail('HTML_IMPORT_CSS_UNSUPPORTED',node['position'])
            style.update(page.inline_projection(node))
        style=apply(styled,style,layout_profile)
        tag='section' if node['tag'] in ('article','figure') else 'p' if node['tag']=='figcaption' else node['tag']
        # UA declarations on headings, links and emphasis must not override inheritance.
        explicit=node['tag'] in ('h1','h2','h3','a','strong','em')
        written={p:v for p,v in style.items() if p not in INHERITED or explicit or parent_style.get(p)!=v}
        attrs={}
        if written:attrs['style']=inline_style(''.join(p+':'+v+';' for p,v in sorted(written.items())),tag,node['position'])
        if tag=='a':attrs['href']=node['attrs']['href']
        if tag=='img':
            src=node['attrs']['src'];match=re.fullmatch(r'data:(image/(?:png|jpeg));base64,([A-Za-z0-9+/]*={0,2})',src)
            index=len(used)
            if index>=MAX_BODY_IMAGES or index>=len(images):fail('HTML_IMPORT_IMAGE',node['position'])
            if match:
                encoded=match[2]
                if not encoded or len(encoded)%4 or len(encoded)>4*((MAX_ASSET_BYTES+2)//3):
                    fail('HTML_IMPORT_IMAGE',node['position'])
                decoded_size=len(encoded)//4*3-(len(encoded)-len(encoded.rstrip('=')))
                if not 0<decoded_size<=MAX_ASSET_BYTES:fail('HTML_IMPORT_IMAGE',node['position'])
                try:data=base64.b64decode(match[2],validate=True)
                except ValueError:fail('HTML_IMPORT_IMAGE',node['position'])
                if base64.b64encode(data).decode()!=match[2] or not 0<len(data)<=2097152:fail('HTML_IMPORT_IMAGE',node['position'])
                if (match[1],data)!=(images[index]['mime'],images[index]['raw']):fail('HTML_IMPORT_SOURCE_BINDING',node['position'])
            elif relative_image_paths is None or src!=relative_image_paths[index]:
                fail('HTML_IMPORT_SOURCE_BINDING',node['position'])
            slot='body'+str(index+1);used.append(slot)
            attrs.update(src='wce-asset:'+slot,alt=node['attrs'].get('alt',''))
        return {'tag':tag,'attrs':attrs,'children':[visit(n,style,[*ancestors,node]) for n in node['children']]}
    root['children']=([visit(n,body_style,[body]) for n in page.body['children']] if page.inline_body
                      else [visit(page.article,body_style,[body])])
    if any('figure'==n['tag'] for n in page.article['children'] if isinstance(n,dict)):
        page.differences+=['figure_to_section','figcaption_to_caption_paragraph','bounded_figure_width_resolved']
    if len(used)!=len(images) or not 1<=len(used)<=MAX_BODY_IMAGES or len(''.join(text).encode())>12000:fail('HTML_IMPORT_LIMIT')
    fragment=serialize(root);parsed=Fragment(fragment,policy=POLICY)
    provenance={'schema':1,'source_sha256':sha256(raw).hexdigest(),'stylesheet_sha256':sha256(page.sheet.encode()).hexdigest(),
                'viewport_width':390,'images':[]}
    for i,(slot,image) in enumerate(zip(['cover',*used],[images[0],*images])):
        provenance['images'].append({'slot':slot,'role':'cover' if i==0 else 'body','source_sha256':sha256(image['raw']).hexdigest(),
            'source_mime':image['mime'],'source_size':len(image['raw']),'transport_sha256':sha256(image['raw']).hexdigest(),
            'transport_mime':image['mime'],'transport_size':len(image['raw'])})
    if layout_profile!= 'source':
        provenance.update(layout_profile=PROFILE,layout_profile_sha256=PARAMETER_SHA256)
    provenance['transform_sha256']=transformation(provenance,fragment)
    output={'title':page.title,'fragment':fragment,'provenance':provenance,'differences':page.differences,
            'images':[{**image,'slot':slot} for slot,image in zip(used,images)],'node_count':parsed.count}
    if metadata_title is not None:output['source_title']=page.source_title
    return output


def acquire(root,relative_html,expected_sha256,image_specs,scratch,*,metadata_title=None,layout_profile='source'):
    """The trusted host fixes all paths+digests; not exposed as a model tool."""
    if not re.fullmatch('[a-f0-9]{64}',expected_sha256) or not 1<=len(image_specs)<=MAX_BODY_IMAGES:fail('HTML_IMPORT_SOURCE_BINDING')
    source=FileSource(root);raw=source.read_html(relative_html)
    if sha256(raw).hexdigest()!=expected_sha256:fail('HTML_IMPORT_SOURCE_CHANGED')
    images=[]
    for spec in image_specs:
        if set(spec)!={'relative_path','sha256','mime'} or spec['mime'] not in ('image/png','image/jpeg'):fail('HTML_IMPORT_IMAGE')
        data=source.read(spec['relative_path'])
        if sha256(data).hexdigest()!=spec['sha256']:fail('HTML_IMPORT_SOURCE_CHANGED')
        images.append({'mime':spec['mime'],'raw':data})
    if len({sha256(i['raw']).hexdigest() for i in images})!=len(images) or sum(len(i['raw']) for i in images)>8388608:fail('HTML_IMPORT_LIMIT')
    from .import_images import decode
    decoded=[decode(i['raw'],i['mime'],scratch).fingerprint() for i in images]
    if sum(i['width']*i['height'] for i in decoded)>16777216:fail('HTML_IMPORT_LIMIT')
    result=convert(raw,images,metadata_title=metadata_title,layout_profile=layout_profile,
        relative_image_paths=tuple(spec['relative_path'] for spec in image_specs))
    result['image_decode_checks']=decoded
    return result


def with_transports(result,transports,scratch):
    """Return a new content binding; never reuse the original-image fingerprint."""
    copy=deepcopy(result)
    if set(transports)!={i['slot'] for i in copy['images']}:fail('HTML_IMPORT_SOURCE_BINDING')
    for index,(image,record) in enumerate(zip(copy['images'],copy['provenance']['images'][1:])):
        mime,raw=transports[image['slot']]
        if mime not in ('image/png','image/jpeg') or not 0<len(raw)<1000000:fail('HTML_IMPORT_IMAGE')
        from .import_images import decode
        raster=decode(raw,mime,scratch,_generated=mime=='image/jpeg')
        original=copy['image_decode_checks'][index]
        if (raster.width,raster.height)!=(original['width'],original['height']):fail('HTML_IMPORT_IMAGE')
        image.update(mime=mime,raw=raw)
        record.update(transport_sha256=sha256(raw).hexdigest(),transport_mime=mime,transport_size=len(raw))
    # The cover uses the same reviewed transport as the article's first image.
    # Source provenance remains unchanged even when this transport is lossy.
    first=copy['provenance']['images'][1]
    copy['provenance']['images'][0].update({k:first[k] for k in
        ('transport_sha256','transport_mime','transport_size')})
    copy['provenance']['transform_sha256']=transformation(copy['provenance'],copy['fragment'])
    return copy


def bind_assets(result,article_id,cover_ref,body_refs,*,metadata=None):
    if set(body_refs)!={i['slot'] for i in result['images']}:fail('HTML_IMPORT_SOURCE_BINDING')
    records=result['provenance']['images']
    if any(not 0<r['transport_size']<1000000 for r in records):fail('HTML_IMPORT_IMAGE')
    if any(records[0][k]!=records[1][k] for k in ('transport_sha256','transport_mime','transport_size')):
        fail('HTML_IMPORT_SOURCE_BINDING')
    from .documents import normalize
    selected_policy=result.get('policy',POLICY)
    value={'format':3,'policy':selected_policy,'articles':[{'id':article_id,'title':result['title'],
        'cover_asset_ref':cover_ref,'style_policy':selected_policy,'provenance':deepcopy(result['provenance']),
        'content_html':result['fragment'],'image_slots':[{'slot':i['slot'],'asset_ref':body_refs[i['slot']]} for i in result['images']]}]}
    if metadata is not None:
        if type(metadata) is not dict or set(metadata)-{'author','digest','source_url','cover_info','cover_dimensions','editorial_intent'}:
            fail('HTML_IMPORT_EDITORIAL_METADATA')
        value['articles'][0].update(deepcopy(metadata))
    normalize(value)
    return value


def preview(result,originals=False):
    """Sanitized-only mobile preview. External anchors become inert spans."""
    mapping={i['slot']:'data:'+i['mime']+';base64,'+base64.b64encode(i['raw']).decode() for i in result['images']}
    tree=Fragment(result['fragment'],policy=POLICY).root
    content=serialize(tree,mapping,preview=True)
    Fragment(content,set(mapping.values()),POLICY)
    return ('<!doctype html><html lang="zh-CN"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">'
        '<title>Jiusera · 手机导入预览</title><style>body{margin:0;background:#eee}.notice{padding:16px;font:13px system-ui;background:#eef5ef;color:#294c36}.mobile{max-width:390px;margin:auto;background:white}</style>'
        '<header class="notice">Jiusera · 390px 手机样式投影 · '+('原图片' if originals else '传输候选')+'<br>原文与图片顺序保留；响应式已固定。微信保留样式情况及与Word对照须本人验收。<br>'+escape(result['title'])+'</header>'
        '<main class="mobile">'+content+'</main></html>').encode()
