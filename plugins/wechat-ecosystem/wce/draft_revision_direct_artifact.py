"""Derive direct SAFE_HTML revisions from pinned source and original proof.

No file IO, account, authority, media identifiers, network or upload. Callers
must independently acquire pinned input bytes and the real original archive.
Source page text/order and image bytes are matched to the complete original
saved document before any changes are derived. Existing safe styles and image
slots remain the actual original document's, never inferred from a new page.
"""
import base64,binascii,re
from copy import deepcopy
from hashlib import sha256
from html.parser import HTMLParser
from .contracts import WCEError
from .documents import normalize
from .html_document import Fragment,serialize,clean_text,DERIVED
from .service import digest
from .draft_revision_exact_metadata import derive as metadata_evidence

PROFILE='DIRECT_SAFE_HTML_MIXED_REUSE_V1'
_DATA=re.compile(r'data:(image/(?:png|jpeg));base64,([A-Za-z0-9+/]*={0,2})\Z')
_VOID={'meta','img'}
_ALLOWED={'html','head','meta','title','style','body','article','h1','h2','p','img'}

def hold():raise WCEError('DRAFT_REVISION_DIRECT_RELATION_HOLD')

def _mime(raw):
    if type(raw) is not bytes or not raw or len(raw)>2097152:hold()
    if raw.startswith(b'\x89PNG\r\n\x1a\n'):
        from .import_images import decode_import_png
        decode_import_png(raw);return 'image/png'
    if raw.startswith(b'\xff\xd8'):
        from .import_images import jpeg
        jpeg(raw);return 'image/jpeg'
    hold()

def _transport(source,transport):
    mime=_mime(source)
    if _mime(transport)!=mime:hold()
    if source!=transport:
        if mime!='image/jpeg':hold()
        from .draft_revision_artifact import strip_app1_app13
        if strip_app1_app13(source)!=transport:hold()
    return mime

class _Page(HTMLParser):
    def __init__(self,raw,images,names):
        if type(raw) is not bytes or not 0<len(raw)<=4*1024*1024:hold()
        try:text=raw.decode('utf-8','strict')
        except UnicodeError:hold()
        super().__init__(convert_charrefs=True)
        self.stack=[];self.events=[];self.current=None;self.images=images;self.names=names
        self.sheet=[];self.body_style=None;self.inline_styles=[];self.seen_html=0;self.seen_body=0
        try:self.feed(text);self.close()
        except WCEError:raise
        except Exception:hold()
        if self.stack or self.current is not None or self.seen_html!=1 or self.seen_body!=1:hold()
        if sum(1 for e in self.events if e[0]=='img')!=len(images):hold()
    def handle_decl(self,decl):
        if decl.lower()!='doctype html':hold()
    def handle_comment(self,data):hold()
    def unknown_decl(self,data):hold()
    def handle_startendtag(self,tag,attrs):
        if tag not in _VOID:hold()
        self.handle_starttag(tag,attrs)
    def handle_starttag(self,tag,attrs):
        if tag not in _ALLOWED or len(attrs)!=len(dict(attrs)):hold()
        attrs=dict(attrs)
        permitted={'html':{'lang'},'head':set(),'meta':{'charset','name','content'},'title':set(),
            'style':set(),'body':{'style'},'article':set(),'h1':set(),'h2':{'style'},
            'p':{'style'},'img':{'src','alt','style'}}
        if set(attrs)-permitted[tag] or any(type(v)is not str for v in attrs.values()):hold()
        if tag=='html':self.seen_html+=1
        if tag=='body':self.seen_body+=1;self.body_style=attrs.get('style','')
        if tag in ('h1','h2','p'):
            if self.current is not None or 'body' not in self.stack:hold()
            self.current=[tag,''];self.events.append(self.current)
        if tag=='img':
            if self.current is not None or 'body' not in self.stack or 'src' not in attrs:hold()
            index=sum(1 for e in self.events if e[0]=='img')
            if index>=len(self.images):hold()
            src=attrs['src'];match=_DATA.fullmatch(src)
            if match:
                try:raw=base64.b64decode(match[2],validate=True)
                except (ValueError,binascii.Error):hold()
                if base64.b64encode(raw).decode()!=match[2] or raw!=self.images[index] or _mime(raw)!=match[1]:hold()
            elif src!=self.names[index]:hold()
            self.events.append(['img',index])
        if tag in ('body','h1','h2','p','img') and 'style' in attrs:
            self.inline_styles.append((tag,attrs['style']))
        if tag not in _VOID:self.stack.append(tag)
    def handle_endtag(self,tag):
        if tag in _VOID:return
        if not self.stack or self.stack[-1]!=tag:hold()
        self.stack.pop()
        if self.current is not None and tag==self.current[0]:self.current=None
    def handle_data(self,data):
        if self.current is not None:self.current[1]+=data
        elif self.stack and self.stack[-1]=='style':self.sheet.append(data)
        elif 'body' in self.stack and data.strip():hold()
    def handle_entityref(self,name):hold()
    def handle_charref(self,name):hold()

def _derive(original,old_source,new_source,source_images,transport_images,metadata_raw,metadata_sha,*,image_names,current_images):
    from .draft_revision_resources import OriginalSavedDraft
    if (type(original) is not OriginalSavedDraft or type(source_images) is not tuple
            or type(transport_images) is not tuple or type(image_names) is not tuple
            or not 1<=len(source_images)==len(transport_images)==len(image_names)<=4
            or any(type(n)is not str or not n or n in ('.','..') or '/' in n or '\\' in n for n in image_names)
            or len(set(image_names))!=len(image_names)):hold()
    old=original.manifest
    if (type(old) is not dict or digest(old)!=original.manifest_digest or old.get('schema')!=3
            or old['document'].get('format')!=3 or old['document'].get('policy')!='WCE_SAFE_HTML_V1'
            or len(old['document'].get('articles',[]))!=1):hold()
    article=old['document']['articles'][0]
    if 'style_policy' in article or 'provenance' in article:hold()
    assets=old['assets']
    if (len(assets)!=len(transport_images)+1 or assets[0]['role']!='cover'
            or len(article['image_slots'])!=len(transport_images)):hold()
    mimes=[]
    for slot,asset,source,transport in zip(article['image_slots'],assets[1:],source_images,transport_images):
        mime=_transport(source,transport);mimes.append(mime)
        if (slot['asset_ref']!=asset['asset_ref'] or asset['slot']!=article['id']+'--'+slot['slot']
                or asset['role']!='body' or asset['declared_type']!=mime
                or asset['sha256']!=sha256(transport).hexdigest() or asset['size']!=len(transport)):hold()
    if len({sha256(x).digest() for x in source_images})!=len(source_images):hold()
    if type(current_images) is not tuple or len(current_images)!=len(source_images):hold()
    prior=_Page(old_source,source_images,image_names);current=_Page(new_source,current_images,image_names)
    if (prior.sheet!=current.sheet or prior.body_style!=current.body_style
            or prior.inline_styles!=current.inline_styles):hold()
    tree=Fragment(article['content_html']).root
    if (len(tree['children'])!=1 or type(tree['children'][0]) is not dict
            or tree['children'][0]['tag']!='section'):hold()
    nodes=tree['children'][0]['children']
    if len(nodes)!=len(prior.events) or any(type(n)is not dict for n in nodes):hold()
    templates={};pictures=[]
    for node,(source_tag,text) in zip(nodes,prior.events):
        if source_tag=='img':
            if node['tag']!='img':hold()
            if node['attrs'].get('src')!='wce-asset:'+article['image_slots'][len(pictures)]['slot']:hold()
            pictures.append(deepcopy(node));continue
        if node['tag']!=('h2' if source_tag=='h1' else source_tag) or len(node['children'])!=1 or type(node['children'][0]) is not str or node['children'][0]!=text:hold()
        shape={'tag':node['tag'],'attrs':deepcopy(node['attrs'])}
        if source_tag in templates and templates[source_tag]!=shape:hold()
        templates[source_tag]=shape
    if len(pictures)!=len(source_images):hold()
    newnodes=[];pic=0
    for tag,text in current.events:
        if tag=='img':
            if pic>=len(pictures):hold()
            newnodes.append(deepcopy(pictures[pic]));pic+=1
        else:
            if tag not in templates or type(text)is not str:hold()
            clean_text(text,(1,0));newnodes.append({**deepcopy(templates[tag]),'children':[text]})
    if pic!=len(pictures):hold()
    newtree=deepcopy(tree);newtree['children'][0]['children']=newnodes
    newhtml=serialize(newtree)
    from .publication_contract import strict_json
    try:new_meta=strict_json(metadata_raw,maximum=131072)
    except Exception:hold()
    if type(new_meta) is not dict or type(new_meta.get('title')) is not str or type(new_meta.get('digest')) is not str:hold()
    doc=deepcopy(old['document']);new_article=doc['articles'][0]
    for key in DERIVED:new_article.pop(key,None)
    new_article['title']=new_meta['title'];new_article['content_html']=newhtml
    if new_meta['digest']!=article.get('digest',''):new_article['digest']=new_meta['digest']
    doc=normalize(doc);new_article=doc['articles'][0]
    proof=metadata_evidence(metadata_raw,metadata_sha,
        {'title':article['title'],'digest':article.get('digest',''),'content':article['content_html']},
        {'title':new_article['title'],'digest':new_article.get('digest',''),'content':new_article['content_html']})
    revised={'schema':3,'binding':deepcopy(old['binding']),'assets':deepcopy(assets),'document':doc}
    relation={'profile':PROFILE,'old_source_sha256':sha256(old_source).hexdigest(),
        'new_source_sha256':sha256(new_source).hexdigest(),
        'old_transport_html_sha256':sha256(article['content_html'].encode()).hexdigest(),
        'new_transport_html_sha256':sha256(newhtml.encode()).hexdigest(),
        'metadata_sha256':metadata_sha,'metadata_changes':proof['changes'],
        'images':[{'source_sha256':sha256(a).hexdigest(),'transport_sha256':sha256(b).hexdigest(),
            'source_size':len(a),'transport_size':len(b),'mime':m} for a,b,m in zip(source_images,transport_images,mimes)],
        'original_manifest_sha256':original.manifest_digest,'new_manifest_sha256':digest(revised)}
    return revised,relation

def derive(original,old_source,new_source,source_images,transport_images,metadata_raw,metadata_sha,*,image_names):
    return _derive(original,old_source,new_source,source_images,transport_images,metadata_raw,metadata_sha,
        image_names=image_names,current_images=source_images)

def pending_image(original,old_source,new_source,source_images,transport_images,new_images,metadata_raw,metadata_sha,*,image_names,changed_index):
    """Describe one exact local change without a remote URL or write permit.

    The content skeleton is hashed only; it is not an executable revision
    manifest. A caller must separately establish its trusted source, baseline,
    durable reservation and a real upload receipt before building a Case.
    """
    if (type(new_images) is not tuple or len(new_images)!=len(source_images)
            or type(changed_index) is not int or not 0<=changed_index<len(source_images)
            or [i for i,(a,b) in enumerate(zip(source_images,new_images)) if a!=b]!=[changed_index]):hold()
    new_bytes=new_images[changed_index];mime=_mime(new_bytes)
    if (len(new_bytes)>=1000000
            or len({sha256(x).digest() for x in new_images})!=len(new_images)):hold()
    revised,relation=_derive(original,old_source,new_source,source_images,transport_images,metadata_raw,metadata_sha,
        image_names=image_names,current_images=new_images)
    slots=original.manifest['document']['articles'][0]['image_slots']
    return {'profile':'DIRECT_SAFE_HTML_ONE_IMAGE_PENDING_V1',
        'original_manifest_sha256':original.manifest_digest,
        'old_source_sha256':relation['old_source_sha256'],'new_source_sha256':relation['new_source_sha256'],
        'metadata_sha256':metadata_sha,'skeleton_sha256':digest(revised),
        'changed_index':changed_index,'slot':slots[changed_index]['slot'],
        'source_sha256':sha256(new_bytes).hexdigest(),'source_size':len(new_bytes),'mime':mime,
        'original_image_sha256':sha256(source_images[changed_index]).hexdigest(),
        'unchanged_source_sha256':[sha256(x).hexdigest() for i,x in enumerate(source_images) if i!=changed_index]}
