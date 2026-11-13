"""Exact current QA derivation → original source rows/proofs. No authority."""
import json
from .contracts import WCEError
from .draft_group_contracts import canonical,digest
from .draft_group_input_files import _plain,_selector
from .draft_group_operator_semantics import member_identities


def need(value,code):
    if value is not True:raise WCEError(code)


def source_member_metadata(report,*,derived_title):
    """Single pure mapping of reviewed editorial intent; no body conversion."""
    _plain(report)
    need(type(report) is dict and {'title','author','digest','cover_crop','comments','originality'}<=set(report),'GROUP_SOURCE_MEMBER_METADATA_REQUIRED')
    need(all(type(report[k]) is str for k in ('title','author','digest')) and type(derived_title) is str
         and report['title']==derived_title,'GROUP_SOURCE_MEMBER_TITLE_CHANGED')
    comments=report['comments']
    need(type(comments) is dict and set(comments)=={'need_open_comment','only_fans_can_comment'}
         and all(type(v) is int and v in (0,1) for v in comments.values())
         and comments=={'need_open_comment':1,'only_fans_can_comment':0},'GROUP_SOURCE_MEMBER_COMMENTS_CHANGED')
    need(type(report['originality']) is bool,'GROUP_SOURCE_MEMBER_ORIGINALITY_REQUIRED')
    source_url=report.get('source_url','');need(type(source_url) is str,'GROUP_SOURCE_MEMBER_SOURCE_URL')
    metadata={'title':derived_title,'author':report['author'],'digest':report['digest'],'source_url':source_url,
        'editorial_intent':{'originality':'review_required' if report['originality'] else 'not_requested',
                            'summary':'custom' if report['digest'] else 'manual_required'}}
    crop=report['cover_crop']
    if crop is not None:
        need(type(crop) is dict and set(crop)=={'cover_info','cover_dimensions'},'GROUP_SOURCE_MEMBER_COVER_SHAPE')
        metadata.update(crop)
    from .editor_contracts import validate
    validate(metadata)
    return json.loads(canonical(metadata))


def read_member_derivation(current,member_identity):
    """Detached facts only. Actual qualification is checked by the producer."""
    _plain(member_identity)
    need(type(current) is dict and type(current.get('member_derivations')) is tuple,'GROUP_SOURCE_MEMBER_DERIVATION_REQUIRED')
    found=[]
    for raw in current['member_derivations']:
        need(type(raw) is str,'GROUP_SOURCE_MEMBER_DERIVATION_REQUIRED');value=json.loads(raw);_plain(value)
        if value['member_identity']==member_identity:found.append(value)
    need(len(found)==1,'GROUP_SOURCE_MEMBER_DERIVATION_REQUIRED')
    return found[0]


def _bind_original_article(manifest,derivation,member):
    from .import_styles import POLICY
    from .documents import assets as document_assets
    report=derivation['report'];metadata=source_member_metadata(report,derived_title=derivation['title'])
    need(manifest['schema']==3 and manifest['document']['format']==3 and manifest['document']['policy']==POLICY,
         'GROUP_SOURCE_MEMBER_FORMAT_REQUIRED')
    from .draft_group_operator_source_codec import CONTENT_SOURCE_TYPE
    if derivation.get('content_source_type')==CONTENT_SOURCE_TYPE:
        source_article_id=derivation.get('source_article_id')
        from .draft_group_input_files import _id
        _id(source_article_id)
        need(report.get('source_article_id')==source_article_id,'GROUP_OPERATOR_SOURCE_ARTICLE_CHANGED')
    else:
        need('content_source_type' not in derivation and 'source_article_id' not in derivation,
             'GROUP_SOURCE_MEMBER_MODE_CHANGED')
        source_article_id=member['article_id']
    matches=[(i,a) for i,a in enumerate(manifest['document']['articles']) if a['id']==source_article_id]
    need(len(matches)==1,'GROUP_SOURCE_UPLOAD_MEMBER_CHANGED');index,article=matches[0]
    need(article['canonical_html'].encode()==derivation['fragment'].encode()
         and canonical(article['provenance'])==canonical(derivation['provenance']), 'GROUP_SOURCE_MEMBER_CONTENT_CHANGED')
    for key,value in metadata.items():
        actual=article.get(key,'') if key in ('author','digest','source_url') else article.get(key)
        need(canonical(actual)==canonical(value),'GROUP_SOURCE_MEMBER_METADATA_CHANGED')
    if report['cover_crop'] is None:
        need('cover_info' not in article and 'cover_dimensions' not in article,'GROUP_SOURCE_MEMBER_COVER_CHANGED')
    refs=list(document_assets({'format':3,'articles':[article]}));records=derivation['provenance']['images']
    need(len(refs)==len(records),'GROUP_SOURCE_MEMBER_SLOTS_CHANGED')
    wanted={}
    for (slot,ref,role),record in zip(refs,records):
        need(slot==source_article_id+'--'+record['slot'] and role==record['role'],'GROUP_SOURCE_MEMBER_SLOTS_CHANGED')
        found=[a for a in manifest['assets'] if a['slot']==slot and a['asset_ref']==ref]
        need(len(found)==1,'GROUP_SOURCE_MEMBER_ASSET_CHANGED');asset=found[0]
        need((asset['role'],asset['sha256'],asset['declared_type'],asset['size'])==(
            role,record['transport_sha256'],record['transport_mime'],record['transport_size']), 'GROUP_SOURCE_MEMBER_ASSET_CHANGED')
        wanted[slot]=asset
    return index,wanted


def _source_member_values_in(host,db,current, *, history_locators=None):
    """Original semantic order, detached exact rows and every original slot fact."""
    from .own_validation_scope import OwnedConnection,_transaction_marker
    from .draft_group_upload_reuse_values import _upload
    from .draft_group_upload_proof_reads import read_original_upload_success_with_proofs_in
    need(type(db) is OwnedConnection and _transaction_marker(db) is not None,'GROUP_SOURCE_UPLOAD_TRANSACTION')
    if current is None:
        current=host.current_no_token_in(None,host._source, history_locators=None)
    host.validate_history_in(db, history_locators=history_locators)
    host.adapter.validate_qualified_inspection(current)
    host.entry.full_guard();host.pure_release_fence()
    workflow=host.entry.service.workflow;profile=next(iter(workflow.registry.profiles.values()))
    from .draft_group_target_scope import _history_workflow
    upload_workflow,_=_history_workflow(host.entry.policy,host.entry.policy.root/'state.sqlite3',profile.binding(),db=db,history_locators=history_locators)
    if not hasattr(host,'_source_upload_receipts'):host._source_upload_receipts={}
    for receipt in host._source_upload_receipts.values():receipt.collective_fence()
    result=[];members=[]
    for member in member_identities(host):
        derived=read_member_derivation(current,member);report=derived['report']
        need('source_manifest_selector' in report,'GROUP_SOURCE_UPLOAD_MEMBER_BINDING_REQUIRED')
        selector=report['source_manifest_selector'];_selector(selector)
        manifest,checksum=workflow._bundle(db,profile,selector['bundle_id'],selector['version'])
        need(checksum==selector['content_digest'],'GROUP_SOURCE_UPLOAD_MANIFEST_CHANGED')
        article_index,wanted=_bind_original_article(manifest,derived,member)
        prior_add=db.execute("SELECT s.id FROM own_steps s JOIN own_articles a ON a.digest=s.manifest_digest WHERE s.operation='add' AND a.bundle=? LIMIT 1",(manifest['bundle_id'],)).fetchone()
        need(prior_add is None,'GROUP_SOURCE_MEMBER_ALREADY_ADMITTED')
        mappings=report['upload_mapping'];need(type(mappings) is list and len(mappings)>0,'GROUP_SOURCE_UPLOAD_PROOFS_REQUIRED')
        uploads=[];seen=set()
        for claimed in mappings:
            _upload(claimed,manifest['binding']['source_kind']=='SYNTHETIC_SETUP')
            need(claimed['selector']==selector,'GROUP_SOURCE_UPLOAD_SELECTOR_CHANGED')
            facts,receipt=read_original_upload_success_with_proofs_in(upload_workflow,db,profile,claimed['base_step_pin']['id'], history_locators=history_locators)
            for key in ('selector','slot','operation','asset','base_step_pin','snapshot','result_digest','proof_files'):
                need(canonical(facts[key])==canonical(claimed[key]),'GROUP_SOURCE_UPLOAD_FACT_CHANGED')
            slot=facts['slot'];need(type(slot) is str and slot in wanted and slot not in seen,'GROUP_SOURCE_UPLOAD_ROLE_CHANGED')
            need(canonical(facts['asset'])==canonical(wanted[slot]),'GROUP_SOURCE_UPLOAD_ROLE_CHANGED');seen.add(slot)
            prior=host._source_upload_receipts.get(claimed['base_step_pin']['id'])
            if prior is None:host._source_upload_receipts[claimed['base_step_pin']['id']]=receipt
            else:prior.collective_fence()
            uploads.append(facts)
        need(seen==set(wanted),'GROUP_SOURCE_UPLOAD_COVERAGE_REQUIRED')
        from .own_connection_workflow import PersistentWorkflow
        from .own_workflow import projection,_defaults_projection
        selected_document=dict(manifest['document'],articles=[manifest['document']['articles'][article_index]])
        selected=dict(manifest,document=selected_document,assets=list(wanted.values()))
        actual_projection=projection(selected,{f['slot']:f['mapping'] for f in uploads})
        actual_projection=_defaults_projection(actual_projection,PersistentWorkflow._request_draft_metadata(selected),manifest['binding'])
        need(len(actual_projection['articles'])==1,'GROUP_SOURCE_MEMBER_PROJECTION_CHANGED')
        original={'binding_sha':digest(manifest['binding']),'article_id':member['article_id'],'version_sha':checksum,
            'original_request_sha':member['original_request_sha'],'source_sha':derived['provenance']['source_sha256'],
            'projection_sha':digest(actual_projection['articles'][0]),'origin':'NEW_NOT_SENT','old_ref_sha':None,'old_position':None}
        from .draft_group_input_files import _member
        _member(original);members.append(original)
        result.append({'article_id':member['article_id'],'original_request_sha':member['original_request_sha'],
            'selector':selector,'source_manifest':manifest,'article_index':article_index,
            'member_evidence_sha':digest(original),'original_uploads':uploads,
            **({'content_source_type':derived['content_source_type'],'source_article_id':manifest['document']['articles'][article_index]['id']}
               if derived.get('content_source_type')=='OPERATOR_ATTESTED_SELECTED_REQUEST_V1' else {})})
    for receipt in host._source_upload_receipts.values():receipt.collective_fence()
    host.adapter.validate_qualified_inspection(current);host.pure_release_fence();host.entry.full_guard()
    return tuple(json.loads(canonical(m)) for m in members),tuple(json.loads(canonical(row)) for row in result)


def source_members_for_registration_in(host,db,current=None, *, history_locators=None):
    """Initial local producer. Never obtains, returns or activates a Token."""
    workflow=host.entry.service.workflow;profile=next(iter(workflow.registry.profiles.values()))
    need(workflow._lease(profile) is None and workflow.active_token is None,'GROUP_SOURCE_REGISTRATION_LOCAL_NO_TOKEN')
    workflow._current(profile,None,'local.write')
    members,rows=_source_member_values_in(host,db,current, history_locators=history_locators)
    need(workflow._lease(profile) is None and workflow.active_token is None,'GROUP_SOURCE_REGISTRATION_LOCAL_NO_TOKEN')
    host.pure_release_fence()
    return {'authority':False,'members':members,'source_rows':rows}


def validated_source_members_in(host,db,current=None, *, history_locators=None):
    """Current validator shares the actual binder; adds exact original Reg."""
    members,rows=_source_member_values_in(host,db,current, history_locators=history_locators)
    need(type(host._registration) is dict,'GROUP_SOURCE_MEMBER_REGISTRATION_REQUIRED')
    registered=host._registration['registration']['ordered_members'];_plain(registered)
    need(canonical(list(members))==canonical(registered),'GROUP_SOURCE_MEMBER_REGISTRATION_CHANGED')
    host.pure_release_fence()
    return rows
