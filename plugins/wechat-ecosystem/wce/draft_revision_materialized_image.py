"""Pure projection for a one-image revision; confers no send authority.

Callers must separately verify the actual local asset and durable upload event.
"""
from copy import deepcopy
from hashlib import sha256
from .contracts import WCEError
from .service import digest

PROFILE='DIRECT_SAFE_HTML_ONE_IMAGE_BOUND_V1'
def hold():raise WCEError('DRAFT_REVISION_MATERIALIZED_IMAGE_HOLD')

def derive(original,old_source,new_source,source_images,transport_images,new_images,metadata_raw,metadata_sha,
        *,image_names,changed_index,proposal,upload,asset):
    from .draft_revision_direct_artifact import _derive,pending_image
    from .upload_wire import api_reference_reason
    core=pending_image(original,old_source,new_source,source_images,transport_images,new_images,
        metadata_raw,metadata_sha,image_names=image_names,changed_index=changed_index)
    if (type(proposal) is not dict or any(proposal.get(k)!=v for k,v in core.items())
            or type(upload) is not dict or upload.get('state')!='SUCCEEDED'
            or upload.get('proposal_sha256')!=digest(proposal)
            or upload.get('image_sha256')!=core['source_sha256']
            or api_reference_reason(upload.get('url')) is not None
            or type(asset) is not dict):hold()
    revised,relation=_derive(original,old_source,new_source,source_images,transport_images,metadata_raw,metadata_sha,
        image_names=image_names,current_images=new_images)
    old_asset=original.manifest['assets'][changed_index+1]
    if (set(asset)!=set(old_asset) or asset.get('slot')!=old_asset['slot'] or asset.get('role')!='body'
            or asset.get('declared_type')!=core['mime'] or asset.get('sha256')!=core['source_sha256']
            or asset.get('size')!=core['source_size'] or asset.get('asset_ref')==old_asset['asset_ref']):hold()
    article=revised['document']['articles'][0];article['image_slots'][changed_index]['asset_ref']=asset['asset_ref']
    revised['assets'][changed_index+1]=deepcopy(asset)
    from .documents import normalize
    from .html_document import DERIVED
    for key in DERIVED:article.pop(key,None)
    revised['document']=normalize(revised['document'])
    relation.update(profile=PROFILE,new_manifest_sha256=digest(revised),changed_index=changed_index,
        pending_sha256=digest(proposal),upload_sha256=digest(upload),new_asset_sha256=digest(asset))
    relation['images'][changed_index]={'source_sha256':core['source_sha256'],
        'transport_sha256':core['source_sha256'],'source_size':core['source_size'],
        'transport_size':core['source_size'],'mime':core['mime']}
    return revised,relation
