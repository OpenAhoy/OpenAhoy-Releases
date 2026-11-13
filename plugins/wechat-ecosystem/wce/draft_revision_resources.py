"""Read and reuse the original saved draft's verified image/proof chain.

Only called by the trusted revision registrar/service under existing account
locks. No media-id argument, grants, token use, upload, save or deletion exists
here. The caller validates the current policy and frozen revision source.
"""
from copy import deepcopy
from dataclasses import dataclass,field
from .contracts import WCEError
from .service import digest


def hold(code='DRAFT_REVISION_ORIGINAL_PROOF_HOLD'):
    raise WCEError(code)


@dataclass(frozen=True)
class OriginalSavedDraft:
    step_id:str
    manifest_digest:str
    intent_digest:str
    result_digest:str
    reference:str=field(repr=False)
    manifest:dict=field(repr=False)
    mappings:dict=field(repr=False)
    upload_snapshots:list=field(repr=False)
    lineage:str=field(default=None,repr=False)


def original_saved(workflow,db,profile,save_key, *, history_locators=None):
    """Actual old OwnWorkflow validators, not status flags or supplied media ID."""
    workflow._resource(db,profile, history_locators=history_locators)
    row=workflow._history(db,profile,save_key, history_locators=history_locators)
    if row is None or row['operation']!='add' or row['state']!='SUCCEEDED':hold()
    intent,result=workflow._step(db,profile,row, history_locators=history_locators)
    if result.get('completion_origin')!='ORIGINAL_RESPONSE_ARCHIVE':hold('DRAFT_REVISION_ORIGINAL_ARCHIVE_REQUIRED')
    selector=intent['selector']
    manifest,checksum=workflow._bundle(db,profile,selector['bundle_id'],selector['version'])
    if checksum!=row['manifest_digest']:hold()
    count=1 if manifest['schema']==1 else len(manifest['document']['articles'])
    if count!=1:hold('DRAFT_REVISION_EXACT_SINGLE_CASE_REQUIRED')
    mappings,snapshots=workflow._uploads(db,profile,manifest,checksum, history_locators=history_locators)
    if snapshots!=intent['uploads']:hold()
    from .own_lineage import seal
    lineage=seal(db,manifest)['lineage']
    return OriginalSavedDraft(row['id'],checksum,row['intent_digest'],row['result_digest'],
        result['reference'],deepcopy(manifest),deepcopy(mappings),deepcopy(snapshots),lineage)


def target_basis(original,new_manifest,source_relation=None):
    from .own_lineage import members
    from .draft_revision_state import checksum
    if type(original) is not OriginalSavedDraft or not checksum(original.lineage):hold()
    manifests=sorted({original.manifest_digest,digest(new_manifest)})
    sources=set(manifests)
    for m in (original.manifest,new_manifest):
        if m['schema'] in (2,3):
            for article in m['document']['articles']:
                value=article.get('provenance',{}).get('source_sha256')
                if value is not None:sources.add(value)
    if source_relation is not None:
        keys=('old_source_sha256','new_source_sha256','old_transport_html_sha256','new_transport_html_sha256')
        if type(source_relation) is not dict or any(not checksum(source_relation.get(k)) for k in keys):hold()
        sources.update(source_relation[k] for k in ('old_source_sha256','new_source_sha256',
            'old_transport_html_sha256','new_transport_html_sha256'))
    result={'MANIFEST':manifests,'LINEAGE':[original.lineage],
        'CONTENT':sorted({digest(x) for m in (original.manifest,new_manifest) for x in members(m)}),
        'PRODUCER_ARTIFACT':sorted(sources)}
    from .draft_revision_store import required_targets
    required_targets({'target_basis':result,'target':digest(original.reference),'original_step':digest(original.step_id)})
    return result


def render_reuse(original,new_manifest,*,source_relation=None,image_upload=None):
    """Both manifests must already pass actual _bundle byte/content validation.

    Pair ordered role+transport bytes; never call _uploads on a new manifest
    digest and never invent new platform media values. The new document may
    change its article id/slot spelling, but image bytes and order cannot change.
    """
    from .own_workflow import projection
    if type(original) is not OriginalSavedDraft or type(new_manifest) is not dict:hold()
    old=original.manifest
    if new_manifest.get('binding')!=old['binding']:hold('DRAFT_REVISION_IMAGE_BINDING_CHANGED')
    if new_manifest.get('schema') not in (1,2,3):hold()
    count=1 if new_manifest['schema']==1 else len(new_manifest['document']['articles'])
    if count!=1:hold('DRAFT_REVISION_EXACT_SINGLE_CASE_REQUIRED')
    before,after=old['assets'],new_manifest['assets']
    if len(before)!=len(after):hold('DRAFT_REVISION_IMAGES_CHANGED')
    from .draft_revision_materialized_image import PROFILE as BOUND_IMAGE
    changed=(type(source_relation) is dict and source_relation.get('profile')==BOUND_IMAGE)
    if changed:
        if type(image_upload) is not dict or set(image_upload)!={'pending','upload'}:hold()
        pending=image_upload['pending'];upload=image_upload['upload'];index=source_relation.get('changed_index')
        from .upload_wire import api_reference_reason
        if (type(index) is not int or not 0<=index<len(before)-1 or type(pending) is not dict or type(upload) is not dict
                or pending.get('profile')!='DIRECT_SAFE_HTML_ONE_IMAGE_PENDING_V1' or upload.get('state')!='SUCCEEDED'
                or digest(pending)!=source_relation.get('pending_sha256') or digest(upload)!=source_relation.get('upload_sha256')
                or upload.get('proposal_sha256')!=digest(pending) or upload.get('image_sha256')!=pending.get('source_sha256')
                or api_reference_reason(upload.get('url')) is not None):hold()
    elif image_upload is not None:hold()
    mappings={};relations=[]
    fields=('role','declared_type','sha256','size')
    for position,(source,target) in enumerate(zip(before,after)):
        replacement=changed and position==index+1
        if source['slot'] not in original.mappings or target['slot'] in mappings:hold('DRAFT_REVISION_IMAGES_CHANGED')
        if replacement:
            if (source['role']!='body' or target['role']!='body' or source['slot']!=target['slot']
                    or target['sha256']!=pending['source_sha256'] or target['size']!=pending['source_size']
                    or target['declared_type']!=pending['mime'] or digest(target)!=source_relation['new_asset_sha256']):hold('DRAFT_REVISION_IMAGES_CHANGED')
            mappings[target['slot']]={'url':upload['url']}
        else:
            if tuple(source[k] for k in fields)!=tuple(target[k] for k in fields):hold('DRAFT_REVISION_IMAGES_CHANGED')
            mappings[target['slot']]=deepcopy(original.mappings[source['slot']])
        relation={'old_slot':source['slot'],'new_slot':target['slot'],
            **{key:source[key] for key in fields},'original_result_sha':digest(original.mappings[source['slot']])}
        if replacement:relation.update(replacement_asset_sha=target['sha256'],replacement_result_sha=digest(mappings[target['slot']]))
        relations.append(relation)
    rendered=projection(new_manifest,mappings)
    rows=rendered['articles'] if 'articles' in rendered else [rendered]
    if len(rows)!=1 or rows[0].get('article_type','news')!='news':hold('DRAFT_REVISION_EXACT_SINGLE_CASE_REQUIRED')
    # The later current-GET payload supplies author/comments/cover/crop/source.
    # Here only the explicitly allowed changed content fields are proposed.
    row=rows[0]
    old_rendered=projection(old,original.mappings)
    old_rows=old_rendered['articles'] if 'articles' in old_rendered else [old_rendered]
    if len(old_rows)!=1:hold()
    # An unchanged local title/digest is not permission to overwrite a fresh
    # platform value with its stale local predecessor.
    changes={key:row[key] for key in ('title','content','digest')
        if key in row and row[key]!=old_rows[0].get(key)}
    from .draft_revision_direct_artifact import PROFILE as DIRECT_PROFILE
    direct=type(source_relation) is dict and source_relation.get('profile') in (DIRECT_PROFILE,BOUND_IMAGE)
    if not changes or ('content' not in changes and not direct):hold('DRAFT_REVISION_CONTENT_UNCHANGED')
    value={'profile':'VERIFIED_DRAFT_REVISION_INPUT_V1','binding':digest(old['binding']),
        'changes':changes,'image_relations':relations,'original_step_sha':digest(original.step_id),
        'original_manifest_sha':original.manifest_digest,'new_manifest_sha':digest(new_manifest),
        'original_uploads_sha':digest(original.upload_snapshots),'reference_sha':digest(original.reference),
        'original_intent_sha':original.intent_digest,'original_result_sha':original.result_digest,
        'target_basis':target_basis(original,new_manifest,source_relation)}
    if source_relation is not None:
        from .draft_revision_artifact import PROFILE as SOURCE_PROFILE
        from .draft_revision_preservation import PreservationPlan,ChangedImagePlan
        if (type(source_relation) is not dict or source_relation.get('profile') not in (SOURCE_PROFILE,DIRECT_PROFILE,BOUND_IMAGE)
                or source_relation.get('original_manifest_sha256')!=original.manifest_digest
                or source_relation.get('new_manifest_sha256')!=digest(new_manifest)):hold()
        if direct:
            from .draft_revision_state import checksum
            keys={'profile','old_source_sha256','new_source_sha256','old_transport_html_sha256',
                'new_transport_html_sha256','metadata_sha256','metadata_changes','images',
                'original_manifest_sha256','new_manifest_sha256'}
            if changed:keys|={'changed_index','pending_sha256','upload_sha256','new_asset_sha256'}
            if (set(source_relation)!=keys or not checksum(source_relation['metadata_sha256'])
                    or type(source_relation['images']) is not list
                    or len(source_relation['images'])!=len(before)-1):hold()
            for position,(image,asset) in enumerate(zip(source_relation['images'],before[1:])):
                if changed and position==index:asset=after[position+1]
                if (type(image) is not dict or set(image)!={'source_sha256','transport_sha256','source_size','transport_size','mime'}
                        or not checksum(image['source_sha256']) or not checksum(image['transport_sha256'])
                        or type(image['source_size']) is not int or not 0<image['source_size']<=2097152
                        or image['transport_sha256']!=asset['sha256'] or image['transport_size']!=asset['size']
                        or image['mime']!=asset['declared_type']):hold()
            old_article=old['document']['articles'][0];new_article=new_manifest['document']['articles'][0]
            local_changes={k:deepcopy(new_article.get('content_html' if k=='content' else k,''))
                for k in ('title','content','digest') if new_article.get('content_html' if k=='content' else k,'')
                !=old_article.get('content_html' if k=='content' else k,'')}
            if source_relation['metadata_changes']!=local_changes:hold()
        old_row=old_rows[0]
        urls=tuple(original.mappings[a['slot']]['url'] for a in old['assets'] if a['role']=='body')
        plan=ChangedImagePlan(old_row['content'],urls,index,upload['url']) if changed else PreservationPlan(old_row['content'],urls)
        value.update(profile='VERIFIED_DRAFT_REVISION_INPUT_V2',
            source_relation=deepcopy(source_relation),preservation=plan.evidence())
        if changed:value['image_upload']=deepcopy(image_upload)
    return value
