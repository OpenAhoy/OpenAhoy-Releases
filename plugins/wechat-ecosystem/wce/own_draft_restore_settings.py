"""Trusted-page review of a staged, non-authorizing recovery proposal."""
from .own_history_source import owned_connection
import os
import math
import re
import secrets
import sqlite3
from .contracts import WCEError
from .own_connection_policy import resolve
from .own_connection_registry import snapshot,check_snapshot,read_registry
from .publication_store import read_file
from .own_draft_restore_contract import CONTRACT,CONTRACT_SHA,fail,clear_window,clear_event_id,check_clear_order
from .service import digest

INTENT='RESTORE_DRAFTS'


def queue_path(backend):
    return backend.registry.parent/'draft-restore-proposal.json'


def queue(backend):
    path=queue_path(backend)
    if not os.path.lexists(path):return None
    value=read_file(path,2*1024*1024)
    keys={'schema','kind','queue_id','clear_event_id','clear_statement','clear_source_sha',
        'exclusion_source_sha','published_exclusions','targets','expires_at','clear_window'}
    if (type(value) is not dict or set(value)!=keys or value['schema']!=1
            or value['kind']!='PROPOSAL_NOT_AUTHORIZATION'
            or type(value['targets']) is not list or not 1<=len(value['targets'])<=8
            or type(value['clear_statement']) is not str or not 1<=len(value['clear_statement'])<=2000
            or type(value['expires_at']) not in (int,float) or not math.isfinite(value['expires_at']) or not backend.wall()<value['expires_at']
            or type(value['published_exclusions']) is not list or len(value['published_exclusions'])>128
            ):
        fail('DRAFT_RESTORE_PROPOSAL_INVALID')
    window=clear_window(value['clear_window'])
    if not window['not_after'] <= backend.wall():fail('DRAFT_RESTORE_CLEAR_TIME_REQUIRED')
    for name in ('clear_source_sha','exclusion_source_sha'):
        if type(value[name]) is not str or re.fullmatch('[a-f0-9]{64}',value[name]) is None:fail()
    if value['clear_event_id']!=clear_event_id(value['clear_source_sha'],window):fail('DRAFT_RESTORE_SOURCE_INVALID')
    for excluded in value['published_exclusions']:
        if (type(excluded) is not dict or set(excluded)!={'connection_id','parent_step_id','version','lineage','title'}
                or any(type(v) is not str or not 1<=len(v)<=512 for v in excluded.values())):fail('DRAFT_RESTORE_EXCLUSION_INVALID')
    seen=set()
    for item in value['targets']:
        if (type(item) is not dict or set(item)!={'connection_id','parent_step_ids','qualified_source_sha'}
                or type(item['connection_id']) is not str or item['connection_id'] in seen
                or type(item['parent_step_ids']) is not list or not 1<=len(item['parent_step_ids'])<=8
                or len(set(item['parent_step_ids']))!=len(item['parent_step_ids'])
                or any(type(x) is not str or re.fullmatch('own-step-[a-f0-9]{32}',x) is None for x in item['parent_step_ids'])
                or type(item['qualified_source_sha']) is not str
                or re.fullmatch('[a-f0-9]{64}',item['qualified_source_sha']) is None):fail()
        seen.add(item['connection_id'])
    return value


def account(backend,cid):
    from .own_connection_broker import AccountService
    return AccountService(resolve(cid,backend.registry))


def proposal_progress(backend, proposal):
    """Pure local reconciliation: an admitted batch is never a fresh review."""
    from .own_store import OwnStore
    from .own_draft_restore_contract import stored
    total=sum(len(target['parent_step_ids']) for target in proposal['targets'])
    recorded=0;orphaned=0
    for target in proposal['targets']:
        policy=resolve(target['connection_id'],backend.registry,active=False)
        path=policy.root/'state.sqlite3'
        from .own_bootstrap_security import path_check
        path_check(path)
        with owned_connection(path, readonly=True, timeout=5) as db, _history_scope(policy,db) as history_locators:
            db.row_factory=sqlite3.Row
            db.execute('BEGIN')
            source=db.execute('SELECT source_kind FROM own_config WHERE id=1').fetchone()[0]
            OwnStore.check(db,source,policy, history=history_locators)
            version=db.execute('PRAGMA user_version').fetchone()[0]
            for parent_id in target['parent_step_ids']:
                parent=db.execute('SELECT * FROM own_steps WHERE id=?',(parent_id,)).fetchone()
                if parent is None:fail('DRAFT_RESTORE_PARENT_NOT_QUALIFIED')
                intent=stored(parent['intent'],parent['intent_digest'])
                grant='restore-grant-'+digest({'event':proposal['clear_event_id'],'parent':parent_id,
                    'version':intent['selector']['version'],'resource':policy.data['resource_id']})
                found=db.execute('SELECT 1 FROM own_draft_restore_grants WHERE id=?',(grant,)).fetchone() if version in (8,9) else None
                if found:recorded+=1
                elif os.path.lexists(policy.root/'draft-restore-authority'/(grant+'.json')):orphaned+=1
            policy.check()
    return {'total':total,'recorded':recorded,'orphaned':orphaned}


def status(backend,cid,check_session):
    backend.check(check_session)
    if backend.selected!=cid:raise WCEError('SETTINGS_REVIEW_CHANGED')
    resolve(cid,backend.registry,active=False)
    try:
        value=queue(backend)
        if value is None:
            result={'state':'NO_PROPOSAL','candidate_count':0,
                'message':'尚无已核准来源的恢复候选；不会自动换键重建旧稿。'}
        else:
            progress=proposal_progress(backend,value)
            if progress['recorded'] or progress['orphaned']:
                backend.check(check_session)
                return {'connection_id':cid,'state':'HOLD','candidate_count':progress['total'],
                    'message':'本批已有全部、部分或未决的恢复许可；请读取原许可结果，不重复审核提交。'}
            result={'state':'AVAILABLE','candidate_count':sum(len(x['parent_step_ids']) for x in value['targets']),
                'message':'恢复审核覆盖已登记批次中的账号与稿件；确认前会重新核对每个原成功对象，尚未授权或保存。'}
    except WCEError as exc:
        result={'state':'HOLD','candidate_count':0,'message':'恢复候选暂不可用：'+exc.code}
    backend.check(check_session)
    return {'connection_id':cid}|result


def prepare(backend,value,check_session):
    backend.check(check_session)
    if backend.state!='READY' or backend.pending_recovery is not None:raise WCEError('SETTINGS_BUSY')
    if type(value) is not dict or set(value)!={'intent','connection_id'} or value['intent']!=INTENT:
        raise WCEError('SETTINGS_INVALID_REQUEST')
    cid=value['connection_id']
    if cid!=backend.selected:raise WCEError('SETTINGS_REVIEW_CHANGED')
    proposal=queue(backend)
    if proposal is None:fail('DRAFT_RESTORE_PROPOSAL_REQUIRED')
    progress=proposal_progress(backend,proposal)
    if progress['recorded'] or progress['orphaned']:fail('DRAFT_RESTORE_BATCH_ALREADY_ADMITTED_OR_UNKNOWN')
    base=snapshot(backend.registry);parents=[];display=[]
    selected=resolve(cid,backend.registry)
    for target in proposal['targets']:
        service=account(backend,target['connection_id'])
        if service.policy.actor.tenant_id!=selected.actor.tenant_id or service.policy.actor.principal_id!=selected.actor.principal_id:
            fail('DRAFT_RESTORE_SCOPE_MISMATCH')
        from .own_draft_restore_context import parent_context
        for parent_id in target['parent_step_ids']:
            with _history_transaction(service.workflow.db) as (db, history_locators):
                from .own_draft_restore_metadata import decorate, reject_legacy_for_new_grant
                reject_legacy_for_new_grant(db)
                context=decorate(parent_context(service,db,parent_id, history_locators=history_locators))
            check_clear_order(context,proposal['clear_window'])
            for excluded in proposal['published_exclusions']:
                if (excluded['connection_id']==target['connection_id'] and
                        (excluded['parent_step_id']==parent_id or excluded['version']==context['version']
                         or excluded['lineage']==context['lineage']['lineage'])):
                    fail('DRAFT_RESTORE_ALREADY_SUBMITTED_OR_PUBLISHED')
            parents.append(context)
            entry=base['registry_value']['entries'].get(target['connection_id'],{})
            display.append({'account_label':entry.get('label',target['connection_id']),
                'account_id':service.policy.data['appid'],'titles':context['titles'],
                'old_reference':context['parent_reference'],
                'clear_source':proposal['clear_statement'],'clear_window':proposal['clear_window'],
                'version':context['version'],'payload_sha':context['payload_sha'],
                'original_payload_sha':context['original_payload_sha'],
                'restore_payload_sha':context['restore_payload_sha'],
                'comment_policy':context['comment_policy'],'comment_policy_sha':context['comment_policy_sha'],
                'comments_by_article':[{'index':i,'original':{k:({'present':True,'value':row[k]} if k in row else {'present':False,'value':None}) for k in ('need_open_comment','only_fans_can_comment')},
                    'restore':{'need_open_comment':1,'only_fans_can_comment':0}} for i,row in enumerate(context['payload']['articles'])],
                'quality_source_sha':target['qualified_source_sha'],
                'prior_restoration_count':len(context['prior_restorations'])})
    backend.check(check_session);check_snapshot(base)
    if queue(backend)!=proposal:fail('DRAFT_RESTORE_PROPOSAL_CHANGED')
    prepared={'schema':1,'contract_sha':CONTRACT_SHA,'scope':'KNOWN_SUCCEEDED_REMOVED_ONLY',
        'queue_sha':digest(proposal),'parents':parents,
        'clear_event_id':proposal['clear_event_id'],'clear_statement':proposal['clear_statement'],'clear_window':proposal['clear_window'],
        'clear_source_sha':proposal['clear_source_sha'],'exclusion_source_sha':proposal['exclusion_source_sha'],
        'expires_at':proposal['expires_at'],'published_exclusions':proposal['published_exclusions']}
    restore_display={'clear_window':proposal['clear_window'],'candidates':display,'published_exclusions':proposal['published_exclusions'],
        'max_saves_per_object':1,'max_reads_per_object':5,'new_uploads':0}
    backend.clear_target();backend.selected=cid
    proposed={'base':base,'transaction':'restore-setting-'+secrets.token_hex(16)}
    backend.review={'id':secrets.token_urlsafe(24),'approval':secrets.token_urlsafe(32),
        'intent':INTENT,'proposed':proposed,'created':backend.clock(),'wall':backend.wall(),
        'generation':backend.generation,'target':cid,'restore_prepared':prepared,
        'restore_prepared_sha':digest(prepared),'restore_display':restore_display,
        'restore_display_sha':digest(restore_display)}
    backend.state='REVIEW'
    return {'review_id':backend.review['id'],'approval':backend.review['approval'],
        'expires_in_seconds':120,'review':{'intent':INTENT,'connection_id':cid,
        'contract':CONTRACT,'contract_sha':CONTRACT_SHA,'restore_drafts':restore_display}}


def execute(backend,reviewed,check_session):
    def guard():
        with backend.lock:
            backend.check(check_session)
            if (backend.state!='ACTIVE' or backend.generation!=reviewed['generation']
                    or backend.selected!=reviewed['target']):raise WCEError('SETTINGS_REVIEW_CHANGED')
            current=queue(backend)
            if current is None or digest(current)!=reviewed['restore_prepared']['queue_sha']:
                fail('DRAFT_RESTORE_PROPOSAL_CHANGED')
    from .own_draft_restore_authority import admitted_review,publish
    admitted=admitted_review(backend,reviewed,guard)
    outputs=[]
    cids=sorted({x['binding']['connection'] for x in reviewed['restore_prepared']['parents']})
    for cid in cids:
        result=publish(account(backend,cid),backend.registry,admitted,guard)
        outputs.extend(result['grants'])
    guard()
    return {'state':'DRAFT_RESTORE_GRANTED','grants':outputs,'new_business_requests':0,
        'message':'本批恢复许可已建立，尚未上传或保存；程序可按每个原恢复句柄执行一次保存及独立读取。'}


def durable_state(backend,reviewed):
    # Local permission rows only; never map the old enrollment transaction here.
    counts={'prepared':0,'absent':0};grants=[]
    for context in reviewed['restore_prepared']['parents']:
        cid=context['binding']['connection'];policy=resolve(cid,backend.registry,active=False)
        grant_id='restore-grant-'+digest({'event':reviewed['restore_prepared']['clear_event_id'],
            'parent':context['parent_step_id'],'version':context['version'],'resource':context['binding']['resource']})
        path=policy.root/'state.sqlite3'
        with owned_connection(path, readonly=True, timeout=5, isolation_level='') as db, _history_scope(policy,db) as history_locators:
            db.row_factory=sqlite3.Row
            from .own_store import OwnStore
            source=db.execute('SELECT source_kind FROM own_config WHERE id=1').fetchone()[0]
            OwnStore.check(db,source,policy, history=history_locators)
            found=db.execute('SELECT id FROM own_draft_restore_grants WHERE id=?',(grant_id,)).fetchone() if db.execute('PRAGMA user_version').fetchone()[0] in (8,9) else None
            counts['prepared' if found else 'absent']+=1
            if found:grants.append({'connection_id':cid,'restore_handle':grant_id})
    return {'state':'GRANTS_RECORDED' if counts['absent']==0 else 'PARTIAL_OR_NOT_GRANTED',
        'counts':counts,'grants':grants,'saved':False}


from .draft_group_history_context import history_transaction as _history_transaction


from .draft_group_history_context import locator_scope as _history_scope
