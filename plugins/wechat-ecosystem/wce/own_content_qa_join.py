"""Shared QA03 fact join proposal; wrappers must guard their own real resources.

This leaf returns detached authorityfalse facts only, never a QA/runtime issue.
Old exact PREUPLOAD wrapper and new exact Group registry are separate callers.
"""
from hashlib import sha256
from pathlib import Path
from .own_preupload_qa import (need,closed,wall,canonical,CONTRACT_SHA256,
    decode_import_dossier,decode_import_acceptance,_evidence_json,_same_ref,_observation)

def check_import_package_contents(resources, *, dossier_ref, acceptance_ref, selection_sha256,
                         binding_projection_sha256, member_ids, selected_roots, expected_consumer_files):
    """Fixed-resource fact check only; no standalone file-to-permit endpoint."""
    resources.guard()
    q_raw=resources.acquire_evidence(dossier_ref).raw
    a_raw=resources.acquire_evidence(acceptance_ref).raw
    q=decode_import_dossier(q_raw);a=decode_import_acceptance(a_raw)
    from .draft_group_selected_source_codec import decode_manifest
    binding=resources.values()
    selected,_,actual_selection_sha=decode_manifest(resources.selection.raw,
        expected_member_projection=tuple(tuple(row) for row in binding['member_projection']))
    need(actual_selection_sha==selection_sha256
         and tuple(row['article_id'] for row in selected['members'])==tuple(member_ids))
    need(a['dossier_ref']==dossier_ref and a['core_scope']==resources.runtime.scope
         and a['binding_projection_sha256']==binding_projection_sha256
         and a['accepted_scope']['selection_sha256']==q['selection_sha256']==selection_sha256
         and a['accepted_scope']['member_set_sha256']==q['member_set_sha256']
         and sha256(canonical(list(member_ids))).hexdigest()==q['member_set_sha256']
         and len(member_ids)==28 and len(set(member_ids))==28)
    scope=a['accepted_scope'];relation=q['coverage_relation']
    required=tuple(f'C{i:02d}' for i in range(1,11))
    need(tuple(scope['required_check_ids'])==required
         and tuple(relation['required_content_check_ids'])==required
         and scope['coverage_mapping_ref']['sha256']==relation['report_check_mapping_sha256'])
    import time
    need(time.time()<min(q['not_after_wall'],scope['not_after_wall']))
    main,visual=q['refs']['main'],q['refs']['visual_supplement']
    assignment=_evidence_json(resources,main['assignment'])
    v_assignment=_evidence_json(resources,visual['assignment'])
    need(assignment['assignment_id']==q['assignment_id']
         and main['assignment']['sha256']==q['assignment_sha256']
         and assignment['attempt']==q['attempt'] and assignment['members']==list(member_ids)
         and assignment['controller'] not in (q['task_name'],)
         and visual['assignment']['sha256']!=main['assignment']['sha256']
         and v_assignment['not_after_wall']==assignment['not_after_wall'])
    dispatch=_evidence_json(resources,main['dispatch'])
    need(dispatch['tool']=='collaboration.spawn_agent'
         and dispatch['actual_returned_task_name']==q['task_name']
         and dispatch['assignment_sha256']==main['assignment']['sha256']
         and dispatch['formal_runtime_qa_issued'] is False)
    first=_observation(resources,main['parent_observation'],assignment,main['assignment'],q['task_name'],
        {'CURRENT-ADOPTION.md':main['report'],'COVERAGE.json':main['coverage']},visual=False)
    second=_observation(resources,visual['parent_observation'],v_assignment,visual['assignment'],q['task_name'],
        {'REVIEW.md':visual['report'],'COVERAGE.json':visual['coverage']},visual=True)
    v_dispatch=_evidence_json(resources,visual['dispatch'])
    closed(v_dispatch,('schema','profile','authority','assignment_sha256','tool',
        'actual_target_task_name','actual_result','observed_running','exact_dispatch_at',
        'recorded_at_wall','terminal_observation_sha256','formal_runtime_qa_issued'))
    need(type(v_dispatch['schema']) is int and v_dispatch['schema']==1
         and v_dispatch['profile']=='PLATFORM_CONTROLLER_FOLLOWUP_OBSERVATION_FACT_V1'
         and v_dispatch['authority'] is False and v_dispatch['tool']=='collaboration.followup_task'
         and v_dispatch['assignment_sha256']==visual['assignment']['sha256']
         and v_dispatch['actual_target_task_name']==q['task_name']
         and v_dispatch['actual_result']=='TOOL_COMPLETED_WITHOUT_ERROR'
         and v_dispatch['observed_running'] is True
         and v_dispatch['exact_dispatch_at']=='UNAVAILABLE'
         and v_dispatch['terminal_observation_sha256']==visual['parent_observation']['sha256']
         and v_dispatch['formal_runtime_qa_issued'] is False
         and second['dispatch_observation']=='actual collaboration.followup_task completed without error; list_agents observed RUNNING')
    wall(v_dispatch['recorded_at_wall'])
    # Reused canonical agent names are safe only with a non-overlapping owned
    # assignment and a real previous FINAL boundary, not an invented turn UUID.
    need(first['observed_at_wall']<=v_assignment['assigned_at_wall']<=second['observed_at_wall']
         and v_assignment['prior_adoption_report_sha256']==main['report']['sha256']
         and v_assignment['prior_coverage_sha256']==main['coverage']['sha256'])
    supplement=_evidence_json(resources,main['metadata_scope_supplement'])
    _same_ref(main['metadata_scope_supplement'],first['source_scope_supplement'])
    _same_ref(main['metadata_observation'],supplement['additional_ref'])
    need(supplement['assignment_id']==assignment['assignment_id']
         and supplement['deadline_extended'] is False
         and supplement['live_owned_relation']=='NOT_VERIFIED'
         and assignment['assigned_at_wall']<=supplement['observed_at_wall']<=first['observed_at_wall'])
    mapping=_evidence_json(resources,scope['coverage_mapping_ref'])
    main_coverage=_evidence_json(resources,main['coverage'])
    v_coverage=_evidence_json(resources,visual['coverage'])
    index=_evidence_json(resources,main['input_index'])
    file_audit=_evidence_json(resources,main['file_audit'])
    metadata_audit=_evidence_json(resources,main['metadata_audit'])
    metadata_observation=_evidence_json(resources,main['metadata_observation'])
    _same_ref(main['input_index'],assignment['input_index'])
    need(metadata_audit['sourceObservationSha256']==main['metadata_observation']['sha256']
         and len(index['items'])==34
         and main_coverage['contractSha256']==CONTRACT_SHA256
         and main_coverage['inputIndexSha256']==main['input_index']['sha256']
         and {(rule['path'],rule['currentSha256']) for rule in index['currentRuleLocators']}
         =={(rule['path'],rule['sha256']) for rule in main['current_rules']})
    for rule,assigned in zip(main['current_rules'],assignment['rules']):
        need(rule['path']==assigned['path'] and rule['sha256']==assigned['currentSha256'])
    need(len(assignment['rules'])==2
         and {(rule['path'],rule['sha256']) for rule in main['current_rules']}
         =={(rule['path'],rule['sha256']) for rule in main_coverage['currentRules'].values()})
    def keyed(rows,key):
        need(type(rows) is list)
        value={row[key]:row for row in rows}
        need(len(value)==len(rows))
        return value
    indexed=keyed(index['items'],'articleId')
    file_items=keyed(file_audit['items'],'articleId')
    meta_items=keyed(metadata_audit['items'],'articleId')
    observations=keyed(metadata_observation['items'],'article_id')
    need(set(file_items)==set(meta_items)==set(observations)==set(member_ids)
         and file_audit['assignmentId']==assignment['assignment_id'])
    for member,coverage in zip(selected['members'],main_coverage['items']):
        identity=member['article_id'];item=indexed[identity]
        need(identity==coverage['articleId']
             and item['bodySha256']==member['body']['sha256']
             and item['htmlSha256']==member['html']['sha256'])
        selected_files=keyed(item['currentSelectedFiles'],'path')
        audited=keyed(file_items[identity]['files'],'path')
        need(set(selected_files)==set(audited)
             and coverage['currentSelectedFiles']==file_items[identity]['files'])
        for path,wanted in selected_files.items():
            actual=audited[path]
            need(actual['sha256']==actual['expectedSha256']==wanted['expectedSha256']
                 ==wanted['actualSha256'] and wanted['matchesOriginal34'] is True
                 and actual['matches'] is True and actual['name']==wanted['name'])
        for artifact in (member['html'],member['body'],*[image['artifact'] for image in member['images']]):
            root=selected_roots[artifact['root_sha256']]
            need(root['article_id']==identity)
            path=str(Path(root['absolute_path'])/artifact['relative_path'])
            need(path in audited and audited[path]['sha256']==artifact['sha256']
                 and audited[path]['bytes']==artifact['size'])
        observed=observations[identity];meta=meta_items[identity]
        need(observed['prepare_request_key']==member['prepare_request_key']
             and observed['selector']==member['selector']
             and sha256(canonical(observed['binding'])).hexdigest()==member['binding_sha256']
             and coverage['metadataEvidence']==meta and meta['fixedMetadataMatchesObservation'] is True
             and meta['sourceReceipt']['path']==observed['source_receipt']['path']
             and meta['sourceReceipt']['sha256']==meta['sourceReceipt']['expectedSha256']
             ==observed['source_receipt']['sha256'])
        expected_metadata=observed['metadata']
        for audit_key,source_key in (('author','author'),('title','title'),
                ('editorialIntent','editorial_intent'),('coverDimensions','cover_dimensions'),
                ('coverInfo','cover_info'),('sourceSha256','source_sha256'),
                ('canonicalSha256','canonical_sha256'),('stylePolicy','style_policy')):
            need(meta[audit_key]==expected_metadata[source_key])
        need(meta['digestIsIntentionalEmpty'] is True and expected_metadata['digest']=='')
    need(mapping['profile']=='QA03_PREUPLOAD_CURRENT_CHECK_MAPPING_FACT_V1'
         and mapping['authority'] is False and mapping['purpose']=='PREUPLOAD_CONTENT_ONLY'
         and mapping['formal_runtime_qa_issued'] is False
         and mapping['required_check_ids']==list(required)
         and [row['member_id'] for row in mapping['rows']]==list(member_ids)
         and [row['articleId'] for row in main_coverage['items']]==list(member_ids)
         and main_coverage['adopterId']==q['task_name']
         and main_coverage['assignmentSha256']==main['assignment']['sha256']
         and v_coverage['assignmentSha256']==visual['assignment']['sha256']
         and v_coverage['requestedHostFactType']=='PLATFORM_SELECTED_CONTENT_REVIEW_V1')
    visual_images={(row['articleId'],row['path'],row['sha256']):row for row in v_coverage['items']}
    need(len(visual_images)==len(v_coverage['items']))
    assigned_images={(row['article_id'],row['image']['path'],row['image']['sha256'])
        for row in v_assignment['images']}
    need(len(assigned_images)==len(v_assignment['images'])
         and assigned_images==set(visual_images))
    required_visual=set()
    for current,original in zip(mapping['rows'],main_coverage['items']):
        need(current['historical_controller_package']=='NOT_PROVEN'
             and current['group_current_owned']=='NOT_VERIFIED'
             and [cell['check_id'] for cell in current['cells']]==list(required))
        for cell in current['cells']:
            need(cell['decision']=='PASS' and cell['member_id']==current['member_id']
                 and original['checks'][cell['check_id']]['status']=='PASS'
                 and cell['report_ref']=={'path':main['coverage']['path'],'sha256':main['coverage']['sha256']}
                 and cell['source_kind']==('CURRENT_PRESENTED_IMAGE_UNION' if cell['check_id']=='C07'
                     else 'CURRENT_INDEPENDENT_SEMANTIC_ADOPTION'))
        expected=[]
        image_evidence=[]
        for image in original['imageCoverage']:
            if image['embeddedInCurrentHtml'] is not True:continue
            expected.append((image['path'],image['sha256']))
            if image['newActualImageDisplay'] is True:
                need(image['status']=='PASS')
                image_evidence.append(('MAIN_CURRENT_IMAGE_PRESENTATION',main['coverage']['sha256']))
            else:
                required_visual.add((current['member_id'],image['path'],image['sha256']))
                observed=visual_images.get((current['member_id'],image['path'],image['sha256']))
                need(observed is not None and observed['status']=='PASS'
                     and observed['actualDisplay'] is True and observed['hashUnchanged'] is True)
                image_evidence.append(('VISUAL_SUPPLEMENT_CURRENT_PRESENTATION',visual['coverage']['sha256']))
        need([(image['path'],image['sha256']) for image in current['consumed_images']]==expected
             and [(image['evidence_kind'],image['report_sha256']) for image in current['consumed_images']]==image_evidence)
    need(required_visual==assigned_images)
    current_rule_pairs={(rule['path'],rule['sha256']) for rule in main['current_rules']}
    need({(rule['path'],rule['sha256']) for rule in v_coverage['fences']['currentRules']}
         ==current_rule_pairs)
    for rule in v_coverage['fences']['currentRules']:
        need(rule['sha256']==rule['expectedSha256'] and rule['matchesExpected'] is True)
    for image in visual_images.values():
        need({(rule['path'],rule['sha256']) for rule in image['currentRuleRefs']}==current_rule_pairs)
    need(main['input_index']['sha256']==q['input_index_sha256'])
    rules=main['current_rules']
    need(sha256(canonical([ref['sha256'] for ref in rules])).hexdigest()==q['current_rule_set_sha256'])
    # Retain the bounded closure. A's independent technical acceptance, current
    # core and binding graph are all required; files themselves remain facts.
    expected_consumers={str(resources.runtime.root/'wce'/name) for name in expected_consumer_files}
    need({ref['path'] for ref in a['consumer_sources']}==expected_consumers)
    for ref in (a['external_review_ref'],*a['consumer_sources'],*a['retention_refs']):
        resources.acquire_evidence(ref)
    for role,ref in main.items():
        if role=='current_rules':
            for rule in ref:resources.acquire_evidence(rule)
        else:resources.acquire_evidence(ref)
    for ref in visual.values():resources.acquire_evidence(ref)
    resources.guard()
    need(time.time()<min(q['not_after_wall'],scope['not_after_wall']))
    return {'authority':False,'purpose':'PREUPLOAD_CONTENT_ONLY',
        'dossier_sha256':dossier_ref['sha256'],'acceptance_sha256':acceptance_ref['sha256'],
        'selection_sha256':selection_sha256,'member_ids':list(member_ids),
        'not_after_wall':min(q['not_after_wall'],scope['not_after_wall']),
        'coverage_mapping_sha256':scope['coverage_mapping_ref']['sha256']}
