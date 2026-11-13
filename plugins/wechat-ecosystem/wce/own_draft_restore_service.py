"""One explicitly granted new save after a known successful parent was removed."""
from .own_history_source import owned_connection
from contextlib import contextmanager
from hashlib import sha256
import re
import time
from uuid import uuid4
from .contracts import WCEError
from .service import canonical,digest
from .own_connection_token import ContinuousClock
from .publication_store import PublicationStore
from .own_draft_restore_contract import fail,stored,CONTRACT_SHA,V1_CONTRACT_SHA,ORIGIN,check_clear_order
from .own_draft_restore_context import parent_context
from .own_draft_restore_store import append_spent,spend_pin,_CURRENT_RESTORE
from .own_draft_restore_proof import validate_success,index_name
from .own_replacement_files import folder,exclusive
from . import own_wire as wire


class DraftRestoreService:
    def __init__(self, account_service, registry, *, wall=time.time, clock=None, fault=lambda phase:None):
        self.service=account_service;self.policy=account_service.policy
        self.registry=registry;self.wall=wall;self.clock=clock or ContinuousClock();self.fault=fault
        self.store=PublicationStore(self.policy,registry,wall=wall)

    def _grant(self,db,handle,active=True, *, history_locators=None):
        if type(handle) is not str or re.fullmatch(r'restore-grant-[a-f0-9]{64}',handle) is None:fail()
        row=db.execute('SELECT * FROM own_draft_restore_grants WHERE id=?',(handle,)).fetchone()
        if row is None:fail('DRAFT_RESTORE_GRANT_REQUIRED')
        value=stored(row['body'],row['body_digest'])
        if (value['binding']['connection'] != self.policy.data['connection_id']
                or value['binding']['resource'] != self.policy.data['resource_id']
                or value['binding']['tenant'] != self.policy.actor.tenant_id
                or value['binding']['principal'] != self.policy.actor.principal_id):
            fail('DRAFT_RESTORE_SCOPE_MISMATCH')
        if active:
            if value.get('contract_sha')==V1_CONTRACT_SHA:fail('DRAFT_RESTORE_LEGACY_HISTORY_HOLD')
            from .own_draft_restore_metadata import verify
            verify(value['context'])
            check_clear_order(value['context'],value['clear_window'])
            from .publication_store import read_file
            proposal=read_file(self.registry.parent/'draft-restore-proposal.json',2*1024*1024)
            if digest(proposal)!=value['queue_sha']:fail('DRAFT_RESTORE_PROPOSAL_CHANGED')
            for excluded in value['published_exclusions']:
                if (excluded['connection_id']==value['binding']['connection'] and
                        (excluded['parent_step_id']==value['parent_step_id']
                         or excluded['version']==value['version']
                         or excluded['lineage']==value['context']['lineage']['lineage'])):
                    fail('DRAFT_RESTORE_ALREADY_SUBMITTED_OR_PUBLISHED')
        if active and (not row['created'] <= self.wall() < row['expires']
                or value['delegation'] != self.policy.delegation()):
            fail('DRAFT_RESTORE_AUTHORITY_EXPIRED')
        if active:
            from .draft_revision_guard import guard_original_step
            guard_original_step(self.service,db,value['parent_step_id'], history_locators=history_locators)
        return value

    def status(self,handle):
        self.policy.check()
        with _history_transaction(self.service.workflow.db) as (db, history_locators):
            self.service.workflow._resource(db,self.service.profile(), history_locators=history_locators)
            self._grant(db,handle,active=False, history_locators=history_locators)
            row=db.execute('SELECT * FROM own_draft_restores WHERE grant_id=?',(handle,)).fetchone()
            if row is None:return {'restore_handle':handle,'state':'PREPARED_NOT_SENT','parent_unchanged':True}
            value={'restore_handle':handle,'state':row['state'],'readback_state':row['readback'],
                'request_key':row['request_key'],'parent_unchanged':True,'write_attempts':1}
            if row['state']=='SUCCEEDED':
                source=db.execute('SELECT source_kind FROM own_config WHERE id=1').fetchone()[0]
                result=validate_success(db,row,self.policy,source)
                value['reference']=result['reference']
            self.policy.check()
            return value

    @contextmanager
    def _execution(self,handle,restore_id=None):
        start_wall,start=self.wall(),self.clock()
        cached=[None]
        old=self.service.workflow.live_guard
        token=_CURRENT_RESTORE.set(restore_id)
        def guard(db=None,*,history_locators=None):
            self.policy.check()
            elapsed,wall_elapsed=self.clock()-start,self.wall()-start_wall
            if (not 0 <= elapsed < 300 or not 0 <= wall_elapsed < 300
                    or abs(elapsed-wall_elapsed)>=5):fail('DRAFT_RESTORE_EXECUTION_EXPIRED')
            if old is not None:old()
            if cached[0] is not None and not self.service.tokens.valid(cached[0]):
                fail('DRAFT_RESTORE_TOKEN_EXPIRED')
            if db is None:
                with _history_transaction(self.service.workflow.db) as (current_db,history_locators):self._grant(current_db,handle,history_locators=history_locators)
            else:self._grant(db,handle,history_locators=history_locators)
            return True
        self.service.workflow.live_guard=guard
        try:yield guard,cached
        finally:
            self.service.workflow.live_guard=old
            _CURRENT_RESTORE.reset(token)

    def execute(self,handle):
        self.policy.check()
        with self.store.dispatch_lock():
            old=self.status(handle)
            if old['state'] != 'PREPARED_NOT_SENT':return old
            with self._execution(handle) as (guard,cached):
                guard();cached[0]=self.service.tokens.get(guard);guard()
                p=self.service.profile(cached[0]);w=self.service.workflow
                w.activate(p,cached[0],time.monotonic()+300)
                with _history_transaction(w.db) as (db, history_locators):
                    grant=self._grant(db,handle, history_locators=history_locators)
                    from .own_draft_restore_metadata import decorate
                    context=decorate(parent_context(self.service,db,grant['parent_step_id'], history_locators=history_locators))
                    if context != grant['context']:fail('DRAFT_RESTORE_PARENT_CHANGED')
                restore_id='restore-'+uuid4().hex;owner=uuid4().hex
                request_key='restore-save-'+digest({'grant_id':handle})
                intent={'schema':2,'contract_sha':CONTRACT_SHA,'restore_id':restore_id,
                    'request_key':request_key,'grant_sha':digest(grant),'binding':context['binding'],
                    'parent_step_sha':context['parent_step_sha'],'payload_sha':context['restore_payload_sha'],
                    'original_payload_sha':context['original_payload_sha'],'restore_payload_sha':context['restore_payload_sha'],
                    'comment_policy_sha':context['comment_policy_sha']}
                request=wire.encode_draft('add',context['restore_payload'],cached[0].token)
                with _history_transaction(w.db, write=True) as (db, history_locators):
                    guard(db,history_locators=history_locators)
                    if decorate(parent_context(self.service,db,grant['parent_step_id'], history_locators=history_locators)) != context:
                        fail('DRAFT_RESTORE_PARENT_CHANGED')
                    if db.execute('SELECT 1 FROM own_draft_restores WHERE grant_id=?',(handle,)).fetchone():
                        fail('DRAFT_RESTORE_ALREADY_SPENT')
                    b=context['binding'];lineage='' if context['lineage']['legacy'] else context['lineage']['lineage']
                    from .draft_group_store import check_account_writer
                    check_account_writer(db, history_locators=history_locators)
                    db.execute('INSERT INTO own_draft_restores(id,grant_id,parent_step_id,request_key,tenant,principal,connection,resource,lineage,owner,intent,intent_digest,state,created) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)',
                        (restore_id,handle,context['parent_step_id'],request_key,b['tenant'],b['principal'],b['connection'],b['resource'],lineage,
                         owner,canonical(intent),digest(intent),'RESULT_UNKNOWN',self.wall()))
                    db.execute('INSERT INTO own_draft_restore_locks VALUES(?,?,?,?)',(b['tenant'],b['resource'],lineage,restore_id))
                    row=dict(db.execute('SELECT * FROM own_draft_restores WHERE id=?',(restore_id,)).fetchone())
                    append_spent(db,row,self.policy.root)
                    self.fault('restore_spent_before_db_commit')
                    guard(db,history_locators=history_locators)
                self.fault('restore_claim_before_http')
                token=_CURRENT_RESTORE.set(restore_id)
                try:
                    guard()
                    with _history_transaction(w.db) as (db, history_locators):
                        if decorate(parent_context(self.service,db,grant['parent_step_id'], history_locators=history_locators)) != context:
                            fail('DRAFT_RESTORE_PARENT_CHANGED')
                    response=w._send(p,w._lease(p),request,'draft.add',True)
                    reply=wire.parse('add',response,cached[0].token,p.source_kind=='SYNTHETIC_SETUP')
                    if reply.result is not None:self._record_success(row,grant,reply.result,response,p.source_kind)
                finally:_CURRENT_RESTORE.reset(token)
                guard()
        return self.status(handle)

    def _record_success(self,row,grant,result,response,source_kind):
        target=self.policy.root/'draft-restore-proofs';folder(target,create=True)
        proof={'schema':1,'origin':ORIGIN,
            'provenance':'OWN_OFFICIAL_WIRE' if source_kind=='OPERATOR_ATTESTED' else 'SYNTHETIC_RESTORE',
            'contract_sha':CONTRACT_SHA,'row_pin_sha':spend_pin(row),
            'grant_sha':digest(grant),'binding':grant['binding'],
            'payload_sha':grant['context']['restore_payload_sha'],'result':result,
            'http_status':response.status,'response_sha':sha256(response.body).hexdigest(),
            'observed_at':self.wall(),'observed_clock_kind':'LOCAL_WALL_NOT_PLATFORM_TIME'}
        name='proof-'+uuid4().hex+'.json';exclusive(target/name,proof)
        exclusive(target/index_name(row['id']),{'schema':1,'restore_id':row['id'],
            'row_pin_sha':spend_pin(row),'proof_name':name,'proof_sha':digest(proof)})
        self.fault('restore_proof_before_result_commit')
        with self.service.workflow.db.transaction(write=True) as db:
            current=db.execute('SELECT * FROM own_draft_restores WHERE id=?',(row['id'],)).fetchone()
            if current is None or spend_pin(current)!=spend_pin(row):fail('DRAFT_RESTORE_INPUT_CHANGED')
            if current['state']=='SUCCEEDED':return
            changed=db.execute("UPDATE own_draft_restores SET state='SUCCEEDED',result=?,result_digest=?,proof_name=?,proof_sha=?,completed=? WHERE id=? AND owner=? AND state='RESULT_UNKNOWN'",
                (canonical(result),digest(result),name,digest(proof),proof['observed_at'],row['id'],row['owner'])).rowcount
            if changed!=1:fail('DRAFT_RESTORE_INPUT_CHANGED')
            db.execute('DELETE FROM own_draft_restore_locks WHERE restore_id=?',(row['id'],))
            final=db.execute('SELECT * FROM own_draft_restores WHERE id=?',(row['id'],)).fetchone()
            validate_success(db,final,self.policy,source_kind)


    def reconcile(self,handle):
        """Original response index only; no HTTP, token or new submit permit."""
        self.policy.check()
        from .publication_store import read_file
        with self.store.dispatch_lock():
            with _history_transaction(self.service.workflow.db) as (db, history_locators):
                self._grant(db,handle,active=False, history_locators=history_locators)
                row=db.execute('SELECT * FROM own_draft_restores WHERE grant_id=?',(handle,)).fetchone()
                if row is None:fail('DRAFT_RESTORE_NOT_SENT')
                if row['state']=='SUCCEEDED':return self.status(handle)
                row=dict(row);source=db.execute('SELECT source_kind FROM own_config WHERE id=1').fetchone()[0]
                path=self.policy.root/'draft-restore-proofs'
                index=read_file(path/index_name(row['id']))
                name=index.get('proof_name')
                if type(name) is not str or re.fullmatch(r'proof-[a-f0-9]{32}\.json',name) is None:fail('DRAFT_RESTORE_PROOF_INVALID')
                proof=read_file(path/name)
                hypothetical=dict(row,state='SUCCEEDED',result=canonical(proof.get('result')),
                    result_digest=digest(proof.get('result')),proof_name=name,proof_sha=digest(proof),
                    completed=proof.get('observed_at'))
                result=validate_success(db,hypothetical,self.policy,source)
            with self.service.workflow.db.transaction(write=True) as db:
                self.policy.check()
                current=db.execute('SELECT * FROM own_draft_restores WHERE id=?',(row['id'],)).fetchone()
                if current is None or spend_pin(current)!=spend_pin(row):fail('DRAFT_RESTORE_INPUT_CHANGED')
                if current['state']=='SUCCEEDED':return self.status(handle)
                changed=db.execute("UPDATE own_draft_restores SET state='SUCCEEDED',result=?,result_digest=?,proof_name=?,proof_sha=?,completed=? WHERE id=? AND owner=? AND state='RESULT_UNKNOWN'",
                    (hypothetical['result'],hypothetical['result_digest'],name,digest(proof),proof['observed_at'],row['id'],row['owner'])).rowcount
                if changed!=1:fail('DRAFT_RESTORE_INPUT_CHANGED')
                db.execute('DELETE FROM own_draft_restore_locks WHERE restore_id=?',(row['id'],))
                final=db.execute('SELECT * FROM own_draft_restores WHERE id=?',(row['id'],)).fetchone()
                validate_success(db,final,self.policy,source)
        return self.status(handle)

    def readback(self,handle):
        self.policy.check()
        with self.store.dispatch_lock():
            status=self.status(handle)
            if status['state']!='SUCCEEDED':fail('DRAFT_RESTORE_SUCCESS_REQUIRED')
            with self._execution(handle) as (guard,cached):
                guard();cached[0]=self.service.tokens.get(guard);guard()
                p=self.service.profile(cached[0]);w=self.service.workflow
                w.activate(p,cached[0],time.monotonic()+300)
                with _history_transaction(w.db, write=True) as (db, history_locators):
                    guard(db,history_locators=history_locators);grant=self._grant(db,handle, history_locators=history_locators)
                    row=db.execute('SELECT * FROM own_draft_restores WHERE grant_id=?',(handle,)).fetchone()
                    result=validate_success(db,row,self.policy,p.source_kind)
                    parent=db.execute('SELECT * FROM own_steps WHERE id=?',(row['parent_step_id'],)).fetchone()
                    old_intent,old_result=w._step(db,p,parent, history_locators=history_locators)
                    from .own_draft_restore_store import check_read_spent,append_read_spent
                    check_read_spent(db,self.policy.root)
                    ordinal=db.execute('SELECT COALESCE(MAX(ordinal),0)+1 FROM own_draft_restore_reads WHERE restore_id=?',(row['id'],)).fetchone()[0]
                    if ordinal>5:fail('DRAFT_RESTORE_READ_BUDGET_EXHAUSTED')
                    db.execute("UPDATE own_draft_restore_reads SET state='UNKNOWN' WHERE restore_id=? AND state='CLAIMED'",(row['id'],))
                    db.execute("INSERT INTO own_draft_restore_reads(restore_id,ordinal,state,created) VALUES(?,?,'CLAIMED',?)",(row['id'],ordinal,self.wall()))
                    append_read_spent(db,self.policy.root,row['id'],ordinal)
                self.fault('restore_read_claim_before_http')
                with w.db.transaction() as db:check_read_spent(db,self.policy.root)
                request=wire.encode_draft('get',{'media_id':result['reference']},cached[0].token)
                response=w._send(p,w._lease(p),request,'draft.get')
                grouped='articles' in old_intent['projection']
                crops=tuple(i for i,article in enumerate(old_intent['projection']['articles']) if 'cover_info' in article) if grouped else ()
                reply=wire.parse_group_get(response,cached[0].token,p.source_kind=='SYNTHETIC_SETUP',
                    result['reference'],requested_cover_indices=crops) if grouped else wire.parse(
                    'get',response,cached[0].token,p.source_kind=='SYNTHETIC_SETUP',result['reference'])
                from .own_workflow import _body_projection
                expected=_body_projection(old_intent) if old_intent['schema']==2 else old_intent['projection']
                matched=reply.result==expected
                comments=None
                if grant['contract_sha']==CONTRACT_SHA:
                    from .own_draft_restore_metadata import compare
                    matched,comments=compare(grant['context'],expected,reply.result,getattr(reply,'comment_observation',None))
                elif old_intent['schema']==2:
                    from .own_draft_wire import comment_comparison
                    metadata=old_intent['article_metadata']
                    comments=comment_comparison([dict(metadata['comment_settings']) for _ in range(metadata['article_count'])],
                        getattr(reply,'comment_observation',None))
                    matched=matched and comments['count_match'] and all(item['state']=='VERIFIED' for item in comments['articles'])
                guard()
                with w.db.transaction(write=True) as db:
                    guard(db,history_locators=history_locators)
                    fresh=db.execute('SELECT * FROM own_draft_restores WHERE id=?',(row['id'],)).fetchone()
                    if fresh['result_digest']!=row['result_digest']:fail('DRAFT_RESTORE_INPUT_CHANGED')
                    check='MATCHED' if matched else 'UNVERIFIED'
                    response_sha=sha256(response.body).hexdigest() if response is not None else None
                    db.execute("UPDATE own_draft_restore_reads SET state=?,response_sha=?,comparison=? WHERE restore_id=? AND ordinal=? AND state='CLAIMED'",
                        ('DONE' if reply.result is not None else 'UNKNOWN',response_sha,check,row['id'],ordinal))
                    db.execute('UPDATE own_draft_restores SET readback=? WHERE id=?',(check,row['id']))
                # Pure diagnostics over this exact already-parsed response.
                # Keep guards outside the exception boundary and preserve the
                # original strict/comment result even if diagnostics fail.
                try:
                    from .nonvisual_audit import restore_readback_report
                    nonvisual=restore_readback_report(expected,reply.result,check,p.source_kind,
                        comments_separate=grant['contract_sha']==CONTRACT_SHA or old_intent['schema']==2)
                except Exception:
                    nonvisual={'policy':'RESTORE_NONVISUAL_DIAGNOSTIC_V1',
                        'comparison':{'state':'UNVERIFIED','reason':'DIAGNOSTIC_UNAVAILABLE'},
                        'visual':'NOT_VERIFIED','strict_readback_unchanged':True,
                        'remote_pixels_verified':False,'authorizes_send':False}
                guard()
        return self.status(handle)|{'readback_state':check,'read_attempt':ordinal,
            'nonvisual_diagnostic':nonvisual,'comments':comments,
            'parent_reference_unchanged':True,'public_publication':False}


def local_status(policy,handle):
    """Pure read-only status, no AccountService, broker, cache or migration."""
    import sqlite3
    from .own_bootstrap_security import path_check
    from .own_store import OwnStore
    policy.check();path=policy.root/'state.sqlite3';path_check(path)
    if type(handle) is not str or re.fullmatch(r'restore-grant-[a-f0-9]{64}',handle) is None:fail()
    with owned_connection(path, readonly=True, timeout=5) as db, _history_scope(policy,db) as history_locators:
        db.row_factory=sqlite3.Row
        db.execute('BEGIN')
        source=db.execute('SELECT source_kind FROM own_config WHERE id=1').fetchone()[0]
        OwnStore.check(db,source,policy, history=history_locators)
        if db.execute('PRAGMA user_version').fetchone()[0] not in (8,9):
            return {'restore_handle':handle,'state':'NOT_PREPARED','parent_unchanged':True}
        grant_row=db.execute('SELECT * FROM own_draft_restore_grants WHERE id=?',(handle,)).fetchone()
        if grant_row is None:fail('DRAFT_RESTORE_GRANT_REQUIRED')
        grant=stored(grant_row['body'],grant_row['body_digest']);b=grant['binding']
        actor=policy.actor
        if (b['connection']!=policy.data['connection_id'] or b['resource']!=policy.data['resource_id']
                or b['tenant']!=actor.tenant_id or b['principal']!=actor.principal_id):
            fail('DRAFT_RESTORE_SCOPE_MISMATCH')
        row=db.execute('SELECT * FROM own_draft_restores WHERE grant_id=?',(handle,)).fetchone()
        if row is None:result={'restore_handle':handle,'state':'PREPARED_NOT_SENT','parent_unchanged':True}
        else:
            result={'restore_handle':handle,'state':row['state'],'readback_state':row['readback'],
                'request_key':row['request_key'],'parent_unchanged':True,'write_attempts':1}
            if row['state']=='SUCCEEDED':result['reference']=validate_success(db,row,policy,source)['reference']
        policy.check()
        return result


def local_list(policy,registry):
    """Discover already granted handles for the current registered batch only."""
    import sqlite3,os
    from pathlib import Path
    from .publication_store import read_file
    from .own_store import OwnStore
    policy.check()
    proposal=Path(registry).parent/'draft-restore-proposal.json'
    if not os.path.lexists(proposal):
        return {'connection_id':policy.data['connection_id'],'state':'NO_CURRENT_PROPOSAL','grants':[]}
    value=read_file(proposal,2*1024*1024);event=value.get('clear_event_id')
    if type(event) is not str or re.fullmatch(r'draft-clear-[a-f0-9]{64}',event) is None:fail()
    with owned_connection(policy.root/'state.sqlite3', readonly=True, timeout=5) as db, _history_scope(policy,db) as history_locators:
        db.row_factory=sqlite3.Row
        db.execute('BEGIN')
        source=db.execute('SELECT source_kind FROM own_config WHERE id=1').fetchone()[0]
        OwnStore.check(db,source,policy, history=history_locators)
        if db.execute('PRAGMA user_version').fetchone()[0] not in (8,9):
            result={'connection_id':policy.data['connection_id'],'state':'NOT_PREPARED','grants':[]}
        else:
            rows=db.execute('SELECT id FROM own_draft_restore_grants WHERE event_id=? AND connection=? ORDER BY created,id LIMIT 65',
                (event,policy.data['connection_id'])).fetchall()
            if len(rows)>64:fail('DRAFT_RESTORE_BATCH_BOUND_EXCEEDED')
            result={'connection_id':policy.data['connection_id'],'state':'CURRENT_REGISTERED_CLEAR_EVENT',
                'clear_event_id':event,'grants':[local_status(policy,row['id']) for row in rows]}
        policy.check();return result


from .draft_group_history_context import history_transaction as _history_transaction


from .draft_group_history_context import locator_scope as _history_scope
