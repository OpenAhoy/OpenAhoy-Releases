"""Pure source-to-existing-transport binding for a reviewed single HTML revision.

The trusted host acquires and pins all input bytes. This module neither reads
paths nor uploads, decodes, encodes, registers authority or modifies artifacts.
Only the previously saved transport bytes may be reused.
"""
import base64
from copy import deepcopy
from hashlib import sha256

from .contracts import WCEError
from .local_html_import import convert, bind_assets
from .documents import normalize
from .service import digest

PROFILE='SAME_SOURCE_IMAGES_EXISTING_JPEG_TRANSPORT_V1'


def hold():
    raise WCEError('DRAFT_REVISION_ARTIFACT_RELATION_HOLD')


def strip_app1_app13(raw):
    """Exact historical pre-SOS segment removal; no image similarity claim."""
    if type(raw) is not bytes or not 0<len(raw)<=2097152 or raw[:2]!=b'\xff\xd8':hold()
    out=[raw[:2]];offset=2;count=0
    while offset<len(raw):
        count+=1
        if count>1024 or raw[offset]!=255:hold()
        start=offset;offset+=1
        while offset<len(raw) and raw[offset]==255:offset+=1
        if offset>=len(raw):hold()
        marker=raw[offset];offset+=1
        if marker in (0xd8,0xd9,0x01) or 0xd0<=marker<=0xd7:hold()
        if offset+2>len(raw):hold()
        size=int.from_bytes(raw[offset:offset+2],'big');end=offset+size
        if size<2 or end>len(raw):hold()
        if marker==0xda:
            out.append(raw[start:]);result=b''.join(out)
            from .import_images import jpeg
            # The existing strict parser validates the complete retained scans.
            jpeg(result)
            return result
        if marker not in (0xe1,0xed):out.append(raw[start:end])
        offset=end
    hold()


def transport_html(raw,source_images,transport_images):
    if type(raw) is not bytes or type(source_images) is not tuple or type(transport_images) is not tuple:
        hold()
    if not 1<=len(source_images)==len(transport_images)<=5:hold()
    if len({sha256(x).digest() for x in source_images})!=len(source_images):hold()
    # These two spelling-only changes are part of the original import relation.
    out=raw.replace(b'letter-spacing:.5px',b'letter-spacing:0.5px')
    out=out.replace(b'letter-spacing:0}',b'letter-spacing:0px}')
    for original,transport in zip(source_images,transport_images):
        if strip_app1_app13(original)!=transport:hold()
        token=base64.b64encode(original)
        if out.count(token)!=1:hold()
        out=out.replace(token,base64.b64encode(transport))
    return out


def derive(original,old_source,new_source,source_images,transport_images):
    """OriginalSavedDraft comes from actual old proof validators, not caller IDs.

    Each source image is already exact-byte pinned by host acquisition. Both
    full pages must embed that ordered tuple, and the entire old derived page
    must reproduce the old saved document/provenance. The raw new SHA is kept
    separately from its derived transmission SHA.
    """
    from .draft_revision_resources import OriginalSavedDraft
    if type(original) is not OriginalSavedDraft:hold()
    old=original.manifest
    if old.get('schema')!=3 or len(old['document']['articles'])!=1:hold()
    article=old['document']['articles'][0]
    if article.get('provenance',{}).get('layout_profile')!='reading-spacious-v1':hold()
    images=[{'mime':'image/jpeg','raw':b} for b in transport_images]
    raw_images=[{'mime':'image/jpeg','raw':b} for b in source_images]
    # Validate complete embedded image bindings before any token substitution.
    # The CSS parser requires the historical numeric spellings first.
    def css(raw):return raw.replace(b'letter-spacing:.5px',b'letter-spacing:0.5px').replace(b'letter-spacing:0}',b'letter-spacing:0px}')
    source_titles=[]
    for raw in (old_source,new_source):
        parsed=convert(css(raw),raw_images,metadata_title=article['title'],layout_profile='reading-spacious-v1')
        source_titles.append(parsed['source_title'])
    if source_titles[0]!=source_titles[1]:hold()
    old_wire=transport_html(old_source,source_images,transport_images)
    new_wire=transport_html(new_source,source_images,transport_images)
    if sha256(old_wire).hexdigest()!=article['provenance']['source_sha256']:hold()
    assets=old['assets']
    if (len(assets)!=len(images)+1 or assets[0]['role']!='cover'
            or any(a['role']!='body' for a in assets[1:])):hold()
    for asset,raw in zip(assets,(transport_images[0],*transport_images)):
        if asset['declared_type']!='image/jpeg' or asset['sha256']!=sha256(raw).hexdigest() or asset['size']!=len(raw):hold()
    metadata={key:deepcopy(article[key]) for key in
        ('author','digest','source_url','cover_info','cover_dimensions','editorial_intent') if key in article}
    def document(raw):
        result=convert(raw,images,metadata_title=article['title'],layout_profile='reading-spacious-v1')
        return normalize(bind_assets(result,article['id'],assets[0]['asset_ref'],
            {s['slot']:a['asset_ref'] for s,a in zip(article['image_slots'],assets[1:])},metadata=metadata))
    if document(old_wire)!=old['document']:hold()
    # A private derived rendering input has no bundle/version/revision identity.
    # It cannot impersonate the immutable old registered bundle or be looked up
    # by _bundle. The revision registrar binds it as a separate Case artifact.
    revised={'schema':3,'binding':deepcopy(old['binding']),
        'assets':deepcopy(old['assets']),'document':document(new_wire)}
    relation={'profile':PROFILE,'old_source_sha256':sha256(old_source).hexdigest(),
        'new_source_sha256':sha256(new_source).hexdigest(),'old_transport_html_sha256':sha256(old_wire).hexdigest(),
        'new_transport_html_sha256':sha256(new_wire).hexdigest(),
        'images':[{'source_sha256':sha256(a).hexdigest(),'transport_sha256':sha256(b).hexdigest(),
            'source_size':len(a),'transport_size':len(b)} for a,b in zip(source_images,transport_images)],
        'original_manifest_sha256':original.manifest_digest,'new_manifest_sha256':digest(revised)}
    return revised,relation
