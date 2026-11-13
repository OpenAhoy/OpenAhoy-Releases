"""Private staging of qualified complete slots; no platform requests.

All Source and workflow evidence is supplied by the private host provider.
Fresh platform observations happen during dispatch, never during this stage.
"""
from .publication_contract import digest,fail,member_claims
from .current_publication_continuation import _ContinuationSession
from .current_publication_service import content_claims


def _expected_claims(projection):
    # An expected-only visual hash must never impersonate an observed remote
    # HTML hash. BODY and MEMBER_FULL still use their established domains.
    return [('EXPECTED_VISUAL' if kind == 'REMOTE_VISUAL' else kind, value)
            for kind,value in content_claims({'response':{'news_item':projection['articles']}})]


def _legacy_conflicts(session,reference,claims):
    """Read already-verified original publication intents under the account lock."""
    from .publication_store import _history_scope
    legacy=session.index.old.legacy
    with legacy.connection() as db, _history_scope(session.index.old.policy,db) as history:
        if not legacy.exists(db,history_locators=history):
            return []
        legacy._verify(db,history_locators=history)
        owners={r[0] for r in db.execute(
            'SELECT intent_id FROM publication_intents WHERE account_key=? AND draft_media_id=?',
            (legacy.key,reference))}
        for kind,fingerprint in claims:
            owners.update(r[0] for r in db.execute(
                'SELECT intent_id FROM publication_claims WHERE account_key=? AND kind=? AND fingerprint=?',
                (legacy.key,kind,fingerprint)))
        return sorted(owners)


def stage(session,source,guard):
    from .slot_source_provider import CompletedSlot
    if type(session) is not _ContinuationSession or type(source) is not CompletedSlot or not callable(guard):
        fail('CURRENT_PUBLICATION_SLOT_SOURCE_REQUIRED')
    session._check_active();source.fence();guard()
    value=source.value
    if type(value) is not dict or type(value.get('logical')) is not dict or type(value.get('content')) is not dict:
        fail('CURRENT_PUBLICATION_SLOT_SOURCE_REQUIRED')
    logical=value['logical'];groups=value['content'].get('groups');evidence=value.get('frozen_evidence')
    policy=session.index.old.policy.data
    if (type(groups) is not list or not groups or type(evidence) is not dict
            or logical.get('appid')!=policy['appid'] or logical.get('principal')!=policy['actor']['principal_id']
            or logical.get('tenant')!=policy['actor']['tenant_id']):
        fail('CURRENT_PUBLICATION_SLOT_SOURCE_REQUIRED')
    identity={'principal_id':logical['principal'],'tenant_id':logical['tenant'],
        **{k:logical[k] for k in ('producer_role','channel','schedule_id','day','slot')}}
    key=session.slot_key(identity);existing=session._slot(key)
    if existing is not None:
        if existing['source_sha']!=source.sha256 or existing.get('completed_slot_handle')!=value.get('handle'):fail('CURRENT_PUBLICATION_SLOT_SOURCE_CHANGED')
        source.fence();guard()
        return {'state':'SLOT_FROZEN_WITH_CONFLICTS' if existing.get('conflicts') else 'SLOT_FROZEN','slot_key':key,'handles':[g['handle'] for g in existing['groups']],
                'group_order':existing.get('group_order'),'conflicts':existing.get('conflicts',[])}
    if len({g.get('reference') for g in groups if type(g) is dict})!=len(groups):
        fail('CURRENT_PUBLICATION_SLOT_SOURCE_REQUIRED')
    prepared=[];conflicts=[];order=[]
    for ordinal,group in enumerate(groups):
        if (type(group) is not dict or type(group.get('reference')) is not str
                or type(group.get('members')) is not list or not 1<=len(group['members'])<=8):
            fail('CURRENT_PUBLICATION_SLOT_SOURCE_REQUIRED')
        source.fence();guard()
        expected=source.expected_group(group['reference'])
        fields={'profile','group_index','reference','selector','members','content_members','expected_projection',
                'expected_projection_sha256','save_sha','get_sha','get_proof_policy',
                'normal_get_receipt_sha256','actual_snapshot','actual_snapshot_sha256','dispatch_protocol'}
        if (type(expected) is not dict or set(expected)!=fields
                or expected['profile']!='SLOT_EXPECTED_GROUP_V1'
                or expected['group_index']!=group['group_index'] or expected['reference']!=group['reference']
                or expected['selector']!=group['selector'] or expected['members']!=group['members']
                or type(expected['content_members']) is not list
                or len(expected['content_members'])!=len(group['members'])
                or expected['expected_projection_sha256']!=digest(expected['expected_projection'])
                or group.get('expected_projection_sha256')!=expected['expected_projection_sha256']
                or expected['get_proof_policy'] not in {'NORMAL_DRAFT_GET_OBSERVED_V1','NORMAL_GET_MATCHED_JOURNAL_V1'}
                or (expected['get_proof_policy']=='NORMAL_DRAFT_GET_OBSERVED_V1'
                    and expected['normal_get_receipt_sha256']!=expected['get_sha'])
                or (expected['get_proof_policy']=='NORMAL_GET_MATCHED_JOURNAL_V1'
                    and expected['normal_get_receipt_sha256'] is not None
                    and (type(expected['normal_get_receipt_sha256']) is not str
                         or len(expected['normal_get_receipt_sha256'])!=64
                         or any(c not in '0123456789abcdef' for c in expected['normal_get_receipt_sha256'])))
                or expected['actual_snapshot'] is not None or expected['actual_snapshot_sha256'] is not None
                or expected['dispatch_protocol']!='SLOT_DISPATCH_BARRIER_V1'):
            fail('CURRENT_PUBLICATION_SLOT_SOURCE_REQUIRED')
        projection=expected['expected_projection']
        if type(projection) is not dict or set(projection)!={'articles'} or type(projection['articles']) is not list \
                or len(projection['articles'])!=len(group['members']):
            fail('CURRENT_PUBLICATION_SLOT_SOURCE_REQUIRED')
        if any(type(member) is not dict or type(original) is not dict or type(article) is not dict
               or original.get('id')!=member.get('article_id') or original.get('title')!=article.get('title')
               for member,original,article in zip(group['members'],expected['content_members'],projection['articles'])):
            fail('CURRENT_PUBLICATION_SLOT_SOURCE_REQUIRED')
        claims=sorted(set(_expected_claims(projection)) | set(member_claims(expected['content_members'])))
        handle='current-pub-'+digest({'slot_key':key,'ordinal':ordinal,'reference':group['reference']})[:48]
        row={'intent_handle':handle,'account_key':session.index.account,'binding_sha256':session.index.binding,
            'reference':group['reference'],'batch_source_sha':source.sha256,'state':'READY','submit_count':0,
            'task':None,'reply':None,'queries':0,'article_count':len(group['members']),
            'titles':[a['title'] for a in projection['articles']],
            'content_claims':[list(item) for item in claims], 'projection_sha256':None,
            'completed_slot_handle':value['handle'],'projection_observation':'UNOBSERVED_AT_FREEZE','expected_projection_sha256':expected['expected_projection_sha256'],
            'get_proof_policy':expected['get_proof_policy'],'normal_get_receipt_sha256':expected['normal_get_receipt_sha256'],
            'slot_key':key,'save_sha':expected['save_sha'],'get_sha':expected['get_sha'],
            'content_sha':digest(claims),'dispatch_protocol':expected['dispatch_protocol']}
        fingerprints=[('DRAFT_REF',digest(row['reference'])),*claims];owners=set()
        for kind,fingerprint in fingerprints:
            for table in ('old_claims','target_claims'):
                owners.update(r[0] for r in session.db.execute(
                    'SELECT handle FROM '+table+' WHERE kind=? AND fingerprint=?',(kind,fingerprint)) if r[0]!=handle)
        staged_in_this_batch={r['intent_handle'] for r in prepared}
        for previous in prepared:
            previous_claims={('DRAFT_REF',digest(previous['reference'])),*(tuple(c) for c in previous['content_claims'])}
            if any(tuple(pair) in previous_claims for pair in fingerprints):
                owners.add(previous['intent_handle'])
        for owner in owners-staged_in_this_batch:session._row(owner)
        legacy_owners=_legacy_conflicts(session,row['reference'],claims)
        group_sha=digest(group)
        if owners or legacy_owners:
            order.append({'kind':'ORIGINAL','index':len(conflicts),'group_sha':group_sha})
            conflicts.append({'reference':row['reference'],'reference_sha':digest(row['reference']),
                'claims':[list(item) for item in claims],
                'original_handles':sorted(owners),'legacy_intents':legacy_owners})
        else:
            order.append({'kind':'READY','index':len(prepared),'group_sha':group_sha})
            prepared.append(row)
    source.fence();guard()
    for row in prepared:session.stage_target(row)
    descriptor={'identity':identity,'source_sha':source.sha256,'binding_sha':session.index.binding,
        'standing_sha':evidence['standing_sha256'],'control_sha':digest(evidence['control']),
        'producer_sha':evidence['producer_text_sha256'],'qa_sha':digest(evidence['production_qa']),
        'groups':[{'handle':row['intent_handle'],**{k:row[k] for k in ('save_sha','get_sha','content_sha')}} for row in prepared],
        'profile':'SLOT_UNOBSERVED_MANIFEST_V1','completed_slot_handle':value['handle'],'group_order':order,'conflicts':conflicts}
    source.fence();guard();result=session.freeze_slot(descriptor);source.fence();guard()
    return {'state':'SLOT_FROZEN_WITH_CONFLICTS' if conflicts else 'SLOT_FROZEN','slot_key':key,'handles':[row['intent_handle'] for row in prepared],
            'group_order':order,'conflicts':conflicts}
