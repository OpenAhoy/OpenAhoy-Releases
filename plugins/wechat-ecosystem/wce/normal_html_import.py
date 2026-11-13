"""One selected self-contained HTML per article, without external image specs.

Only local preparation is performed. Extracted bytes cannot grant account rights,
start uploads or select another file. Legacy import policies are unchanged.
"""
import base64
import codecs
from copy import deepcopy
from hashlib import sha256
import os
from pathlib import Path
import re

from .bounded_file import FileSource, MAX_ASSET_BYTES
from .contracts import WCEError
from .html_document import Fragment, serialize, transformation
from .import_styles import TAGS, INHERITED, stylesheet, computed, inline_style
from .local_html_import import Page, fail
from .normal_html_limits import POLICY, FRAGMENT_BYTES, IMAGE_POSITIONS

_CHUNK = 64 * 1024
_DATA = ('data:image/png;base64,', 'data:image/jpeg;base64,')


class Extractor:
    """Tokenize quoted attributes while base64 is decoded in fixed work blocks."""
    def __init__(self, scratch, guard=lambda: None):
        self.root=Path(scratch);self.guard=guard
        self.parts=[];self.tag=None;self.quote=None;self.src_start=None
        self.image=None;self.images=[];self.quartets='';self.padded=False
        self.inside=0;self.skeleton_bytes=0

    def emit(self, text):
        self.skeleton_bytes+=len(text.encode())
        # Source formatting and inherited CSS can be much larger than emitted
        # HTML. Only the final projection, not this skeleton's MB, is a quota.
        self.parts.append(text)

    def start_image(self, mime):
        if len(self.images)>=IMAGE_POSITIONS:fail('HTML_IMPORT_LIMIT')
        name='embedded-'+str(len(self.images)+1)+('.png' if mime=='image/png' else '.jpg')
        fd=os.open(self.root/name,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o600)
        self.image={'path':str(self.root/name),'mime':mime,'sha':sha256(),'size':0,'fd':fd,'relative':name}
        self.quartets='';self.padded=False
        self.tag=self.tag[:self.src_start]+name

    def encoded(self, text):
        if not text:return
        if self.padded or any(c not in 'ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/=' for c in text):
            fail('HTML_IMPORT_IMAGE')
        self.quartets+=text
        count=len(self.quartets)//4*4
        if not count:return
        block,self.quartets=self.quartets[:count],self.quartets[count:]
        try:data=base64.b64decode(block,validate=True)
        except ValueError:fail('HTML_IMPORT_IMAGE')
        if base64.b64encode(data).decode()!=block:fail('HTML_IMPORT_IMAGE')
        self.padded='=' in block
        item=self.image;item['size']+=len(data)
        if item['size']>MAX_ASSET_BYTES:fail('HTML_IMPORT_IMAGE')
        item['sha'].update(data)
        view=memoryview(data)
        while view:
            written=os.write(item['fd'],view)
            if written<=0:raise OSError('short image write')
            view=view[written:]

    def end_image(self):
        if self.quartets or not self.image['size']:fail('HTML_IMPORT_IMAGE')
        item=self.image
        os.fsync(item['fd']);os.close(item.pop('fd'))
        item['sha256']=item.pop('sha').hexdigest()
        self.images.append(item);self.image=None;self.src_start=None

    def feed(self, text):
        # Base64 is handled in spans, not one syscall/decoder invocation per byte.
        self.guard();i=0
        while i<len(text):
            if self.image is not None:
                end=text.find(self.quote,i)
                if end<0:self.encoded(text[i:]);return
                self.encoded(text[i:end]);self.end_image()
                self.tag+=self.quote;self.quote=None;i=end+1;continue
            char=text[i];i+=1
            if self.tag is None:
                end=text.find('<',i-1)
                if end<0:end=len(text)
                plain=text[i-1:end]
                if self.inside or plain.strip():self.emit(plain)
                i=end
                if i<len(text):self.tag='<';i+=1
                continue
            self.tag+=char
            if self.quote:
                if self.src_start is not None:
                    value=self.tag[self.src_start:]
                    if value in _DATA:
                        self.start_image('image/png' if value==_DATA[0] else 'image/jpeg');continue
                    if not any(prefix.startswith(value) for prefix in _DATA):fail('HTML_IMPORT_IMAGE')
                if char==self.quote:self.quote=None
            elif char in ('"',"'"):
                self.quote=char
                if re.match(r'<img\s',self.tag) and re.search(r'\bsrc\s*=\s*["\']$',self.tag):
                    self.src_start=len(self.tag)
            elif char=='>':
                match=re.match(r'<(/?)([a-zA-Z][a-zA-Z0-9]*)\b',self.tag)
                if match and match[2] in ('article','body'):
                    self.inside+=-1 if match[1] else 1
                self.emit(self.tag);self.tag=None

    def finish(self):
        if self.tag is not None or self.image is not None or not self.images:fail('HTML_IMPORT_STRUCTURE')
        return ''.join(self.parts).encode()

    def close(self):
        if self.image is not None and 'fd' in self.image:
            os.close(self.image.pop('fd'))


def acquire(root, relative_html, expected_sha256, scratch, *, metadata_title=None,
            layout_profile='source', guard=lambda: None):
    """Read exactly the selected file; scratch is host-owned and private."""
    if type(expected_sha256) is not str or re.fullmatch('[a-f0-9]{64}',expected_sha256) is None:
        fail('HTML_IMPORT_SOURCE_BINDING')
    extractor=Extractor(scratch,guard);fingerprint=sha256();decoder=codecs.getincrementaldecoder('utf-8')('strict')
    try:
        for chunk in FileSource(root).iter_html(relative_html,guard=guard):
            fingerprint.update(chunk)
            try:extractor.feed(decoder.decode(chunk))
            except UnicodeError:fail('HTML_IMPORT_ENCODING')
        try:extractor.feed(decoder.decode(b'',final=True))
        except UnicodeError:fail('HTML_IMPORT_ENCODING')
        if fingerprint.hexdigest()!=expected_sha256:fail('HTML_IMPORT_SOURCE_CHANGED')
        skeleton=extractor.finish()
        from .import_images import decode
        for image in extractor.images:
            guard();data=FileSource(Path(image['path']).parent).read(Path(image['path']).name)
            if sha256(data).hexdigest()!=image['sha256']:fail('HTML_IMPORT_SOURCE_CHANGED')
            image['decode']=decode(data,image['mime'],scratch).fingerprint()
            from .html_technical_standard import validate_upload
            validate_upload('article_body', image['mime'], data)
            del data
        return convert(skeleton,extractor.images,expected_sha256,metadata_title=metadata_title,
                       layout_profile=layout_profile,guard=guard)
    finally:extractor.close()


def convert(skeleton, images, source_sha256, *, metadata_title=None, layout_profile='source', guard=lambda: None):
    """Project the existing finite HTML/CSS grammar, preserving every position."""
    from .reading_layout import apply, PROFILE, PARAMETER_SHA256
    page=Page(skeleton,metadata_title,normal=True)
    rules=[] if page.inline_body else stylesheet(page.sheet,390,normal=True)
    body=page.body if page.inline_body else {'tag':'body','attrs':{},'children':[]}
    base=apply(body,page.inline_projection(body) if page.inline_body else computed(body,[],{},rules),layout_profile)
    root={'tag':'section','attrs':{'style':inline_style(''.join(p+':'+v+';' for p,v in sorted(base.items())),'section')},'children':[]}
    source=page.body['children'] if page.inline_body else [page.article]
    pending=[(n,base,[body],root) for n in reversed(source)];used=[]
    visited=0;guard()
    while pending:
        visited+=1
        if visited%64==0:guard()
        node,parent_style,ancestors,parent=pending.pop()
        if isinstance(node,str):parent['children'].append(node);continue
        if node['tag'] not in TAGS-{'body','section'}:fail(position=node['position'])
        if node['tag']=='article' and ancestors!=[body]:fail(position=node['position'])
        styled={'tag':'p','attrs':{'class':'caption'}} if node['tag']=='figcaption' else node
        style=computed(node,ancestors,parent_style,rules)
        if page.inline_body:style.update(page.inline_projection(node))
        style=apply(styled,style,layout_profile)
        tag='section' if node['tag'] in ('article','figure') else 'p' if node['tag']=='figcaption' else node['tag']
        explicit=node['tag'] in ('h1','h2','h3','a','strong','em')
        written={p:v for p,v in style.items() if p not in INHERITED or explicit or parent_style.get(p)!=v}
        attrs={}
        if written:attrs['style']=inline_style(''.join(p+':'+v+';' for p,v in sorted(written.items())),tag,node['position'])
        if tag=='a':attrs['href']=node['attrs']['href']
        if tag=='img':
            i=len(used)
            if i>=len(images) or node['attrs']['src']!=images[i]['relative']:fail('HTML_IMPORT_SOURCE_BINDING')
            slot='body'+str(i+1);used.append(slot)
            attrs.update(src='wce-asset:'+slot,alt=node['attrs'].get('alt',''))
        out={'tag':tag,'attrs':attrs,'children':[]};parent['children'].append(out)
        pending.extend((n,style,[*ancestors,node],out) for n in reversed(node['children']))
    guard()
    if len(used)!=len(images):fail('HTML_IMPORT_SOURCE_BINDING')
    fragment=serialize(root);parsed=Fragment(fragment,policy=POLICY)
    # Empty src supplies a necessary lower bound, never a substitute for the
    # final official-length check with actual returned platform URLs.
    lower=serialize(parsed.root,{slot:'' for slot in used})
    from .normal_html_limits import final_content
    final_content(lower)
    provenance={'schema':2,'source_sha256':source_sha256,'stylesheet_sha256':sha256(page.sheet.encode()).hexdigest(),
                'viewport_width':390,'images':[]}
    for i,(slot,image) in enumerate(zip(['cover',*used],[images[0],*images])):
        provenance['images'].append({'slot':slot,'role':'cover' if i==0 else 'body',
            'source_sha256':image['sha256'],'source_mime':image['mime'],'source_size':image['size'],
            'transport_sha256':image['sha256'],'transport_mime':image['mime'],'transport_size':image['size']})
    if layout_profile!='source':provenance.update(layout_profile=PROFILE,layout_profile_sha256=PARAMETER_SHA256)
    provenance['transform_sha256']=transformation(provenance,fragment)
    return {'title':page.title,'fragment':fragment,'provenance':provenance,'policy':POLICY,
        'differences':page.differences,'images':[dict(image,slot=slot) for slot,image in zip(used,images)],'node_count':parsed.count}


def bind_assets(result,article_id,cover_ref,body_refs,*,metadata=None):
    from .local_html_import import bind_assets as old_bind
    # Reuse the existing metadata allowlist/role binding, selecting only the
    # explicit new document policy. No policy change for old result objects.
    return old_bind(result,article_id,cover_ref,body_refs,metadata=metadata)
