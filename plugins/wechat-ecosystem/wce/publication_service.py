"""Ordinary-publication execution; every public path gates before tokens/HTTP."""
from dataclasses import asdict
from hashlib import sha256
import os
from pathlib import Path
import re
import time
from uuid import uuid4

from .contracts import WCEError
from .http_transport import HTTPSender, HTTPRequest
from .service import canonical, digest
from .own_connection_token import TokenCache, ContinuousClock
from .own_connection_policy import atomic_write
from .own_group_json import read as stored_manifest
from .publication_contract import (CONTRACT_SHA, QUALITY_PROFILE, WIRE_PROFILE,
    exact, fail, strict_json, member_claims, binding)
from .publication_store import PublicationStore, insert, commit_event
from . import publication_quota as quota
from .publication_producer import RegisteredRoot, document_members, check_baseline
from .publication_quality import compare
from .publication_wire import DraftMediaID, TaskID, ArticleID, encode, parse


class PublicationService:
    def __init__(self, policy, registry, *, sender=None, tokens=None, reviewer=None,
                 wall=time.time, clock=None, fault=lambda phase:None, quota_provider=None):
        self.policy, self.registry = policy, Path(registry)
        self.wall, self.clock, self.fault = wall, clock or ContinuousClock(), fault
        self.execution_fence = None
        self.store = PublicationStore(policy,registry,wall=wall,fault=fault)
        self.sender, self.tokens, self.reviewer = sender, tokens, reviewer
        self.synthetic = False
        self.quota_provider = quota_provider

    def status(self, intent_id=None):
        if intent_id is not None: return self.store.local_intent(intent_id)
        return self.store.state() | {'mass':'UNAVAILABLE_PENDING_HUMAN_SOURCE_AND_ADMISSION',
            'public_platform_verified':False,'qa_runtime':'REVIEW_RUNTIME_UNAVAILABLE',
            'qa_reason':'STARTUP_MCP_COMPLETE_ISOLATION_UNPROVEN',
            'quota':'QUOTA_TRUSTED_SOURCE_UNAVAILABLE',
            'producer':'TRUSTED_REGISTRATION_REQUIRED'}

    def _current(self):
        self._execution_current()
        self.policy.check()
        with self.store.connection() as db:
            if not self.store.exists(db): fail('PUBLICATION_OFF')
            row,value = self.store.current(db)
            self.store.admission(db)
            return row,value

    def _execution_current(self, token=None):
        fence = getattr(self, 'execution_fence', None)
        if fence is not None:
            elapsed, wall_elapsed = self.clock() - fence[1], self.wall() - fence[0]
            if (not 0 <= elapsed < 300 or not 0 <= wall_elapsed < 300
                    or abs(elapsed - wall_elapsed) >= 5):
                fail('PUBLICATION_EXECUTION_EXPIRED')
        if token is not None and (self.tokens is None or not self.tokens.valid(token)):
            fail('PUBLICATION_TOKEN_EXPIRED')

    def _quota_apply(self, method, *args, **kwargs):
        try: return method(*args, **kwargs)
        except quota.QuotaHold as exc: fail(str(exc))

    def _quota_clock(self):
        return dict(wall_ms=int(self.wall()*1000), mono_ms=int(self.clock()*1000),
                    boot_id='synthetic-boot')

    def _quota_args(self, candidate_id, attempt):
        if not self.synthetic or type(self.quota_provider) is not quota.SyntheticProvider:
            fail('QUOTA_TRUSTED_SOURCE_UNAVAILABLE')
        return dict(account_key=self.store.key, binding_sha=self.store.binding_sha,
                    candidate_id=candidate_id, attempt=attempt,
                    shared_accounting_verified=True, **self._quota_clock())

    def _quota_observe(self, path):
        if not self.synthetic or type(self.quota_provider) is not quota.SyntheticProvider:
            fail('QUOTA_TRUSTED_SOURCE_UNAVAILABLE')
        now=self._quota_clock()
        observation=self.quota_provider.observe(self.store.key, self.store.binding_sha,
            path, now['wall_ms'], now['mono_ms'])
        data={'api_path':path}
        def apply(db, seq):
            data['observation_sha']=self._quota_apply(quota.record_observation, db, observation,
                verify_source=self.quota_provider.verify, **now)
        commit_event(self.store,'QUOTA_OBSERVATION',data,apply)
        return data['observation_sha']

    def _quota_initial(self, candidate_id):
        self._group_new_current()
        obs=self._quota_observe(quota.DRAFT)
        with self.store.connection() as db:
            attempt=db.execute("SELECT COALESCE(MAX(attempt),0)+1 FROM publication_quota_claims WHERE account_key=? AND candidate_id=? AND step='INITIAL'", (self.store.key,candidate_id)).fetchone()[0]
        data={'candidate_id':candidate_id,'attempt':attempt,'observation_sha':obs}
        def apply(db, seq, *, history_locators=None):
            from .draft_group_store import check_account_writer
            check_account_writer(db, history_locators=history_locators)
            self._quota_apply(quota.claim, db, **self._quota_args(candidate_id,attempt),intent_id=None,
                        step='INITIAL',ordinal=attempt,observation_sha=obs)
        commit_event_with_history(self.store,'QUOTA_INITIAL',data,apply)
        return attempt

    def _quota_final(self,candidate_id,intent_id,attempt):
        self._group_new_current()
        draft=self._quota_observe(quota.DRAFT)
        submit=self._quota_observe(quota.SUBMIT)
        data={'candidate_id':candidate_id,'intent_id':intent_id,'attempt':attempt,
              'draft_observation_sha':draft,'submit_observation_sha':submit}
        def apply(db,seq, *, history_locators=None):
            from .draft_group_store import check_account_writer
            check_account_writer(db, history_locators=history_locators)
            self._quota_apply(quota.reserve_final_submit, db, **self._quota_args(candidate_id,attempt),
                intent_id=intent_id,draft_observation_sha=draft,submit_observation_sha=submit)
        commit_event_with_history(self.store,'QUOTA_FINAL_RESERVATION',data,apply)
        return submit

    def _get_token(self, guard):
        # Instantiating TokenCache can never be the admission check.
        guard()
        if getattr(self, 'execution_fence', None) is None:
            self.execution_fence = (self.wall(), self.clock())
        if self.tokens is None: self.tokens = TokenCache(self.policy)
        token = self.tokens.get(guard)
        guard()
        self._execution_current(token)
        return token

    def _send(self, request, token, guard, timeout=10):
        guard()
        self._execution_current(token)
        if self.sender is None: self.sender = HTTPSender(enabled=True)
        if self.sender.mode == 'live':
            with self.store.connection() as db:
                if db.execute('SELECT source_kind FROM own_config WHERE id=1').fetchone()[0] != 'OPERATOR_ATTESTED':
                    fail('PUBLICATION_SYNTHETIC_NOT_LIVE')
        if isinstance(request,HTTPRequest):
            if type(request) is not HTTPRequest or type(request.path) is not str:
                fail('PUBLICATION_REQUEST_UNVERIFIED')
            if request.path.split('?',1)[0]=='/cgi-bin/freepublish/submit':
                group_started=self.clock()
                self._group_new_current()
                guard()
                self._execution_current(token)
                elapsed=self.clock()-group_started
                if not 0<=elapsed<timeout:fail('PUBLICATION_SNAPSHOT_EXPIRED')
                timeout-=elapsed
        elif type(self.sender) is HTTPSender:
            fail('PUBLICATION_REQUEST_UNVERIFIED')
        result = self.sender.send(request,min(10,timeout))
        # Caller retains historical response facts even if authority just expired.
        return result

    def _group_new_current(self):
        # The existing caller retains dispatch_lock's real stable/local FDs.
        # A normal ro BEGIN snapshot is closed here before any HTTP call.
        with self.store.connection() as db, _history_scope(self.policy,db) as history_locators:
            db.execute('BEGIN')
            try:
                from .draft_group_store import check_account_writer
                check_account_writer(db, history_locators=history_locators)
            finally:db.rollback()


    def _legacy(self, db, request_key, *, history_locators=None):
        from .own_store import OwnStore
        source = db.execute('SELECT source_kind FROM own_config WHERE id=1').fetchone()[0]
        OwnStore.check(db,source,self.policy, history=history_locators)
        owner = object.__new__(OwnStore)
        owner.path,owner.history_policy = self.store.path,self.policy
        owner._check_legacy_history(db,source, history=history_locators)
        row = db.execute('SELECT * FROM own_steps WHERE tenant=? AND principal=? AND connection=? AND request_key=?',
            (self.policy.data['actor']['tenant_id'],self.policy.data['actor']['principal_id'],
             self.policy.data['connection_id'],request_key)).fetchone()
        if row is None or row['operation'] != 'add' or row['state'] != 'SUCCEEDED':
            fail('PUBLICATION_SAVED_DRAFT_REQUIRED')
        intent = strict_json(row['intent'].encode())
        result = strict_json(row['result'].encode())
        if digest(intent)!=row['intent_digest'] or digest(result)!=row['result_digest']:
            fail()
        mrow = db.execute('SELECT * FROM own_articles WHERE version=?',(intent['selector']['version'],)).fetchone()
        if mrow is None: fail()
        manifest = stored_manifest(mrow['manifest'],mrow['digest'])
        if manifest['schema'] not in (2,3): fail('PUBLICATION_DOCUMENT_FORMAT_UNSUPPORTED')
        expected = self.policy.data
        b=manifest['binding'];actor=expected['actor']
        values={'tenant':actor['tenant_id'],'principal':actor['principal_id'],'client':actor['client_id'],
            'session':actor['session_id'],'connection':expected['connection_id'],'account':expected['appid'],
            'resource':expected['resource_id'],'generation':expected['generation'],'epoch':expected['epoch']}
        if any(b[k]!=v for k,v in values.items()): fail('PUBLICATION_BINDING_UNVERIFIED')
        from .own_lineage import check_relations, seal
        check_relations(db,manifest)
        lineage=seal(db,manifest)
        from .own_draft_restore_store import check_write as check_restores
        check_restores(db, actor['tenant_id'], expected['resource_id'], None if lineage['legacy'] else lineage['lineage'])
        assets=[]
        for meta in manifest['assets']:
            asset=db.execute('SELECT * FROM own_assets WHERE id=?',(meta['asset_ref'],)).fetchone()
            if asset is None or sha256(asset['data']).hexdigest()!=meta['sha256']:
                fail('PUBLICATION_IMAGE_UNVERIFIED')
            if not 0<len(asset['data'])<1000000:
                fail('PUBLICATION_IMAGE_LIMIT')
            assets.append((meta,bytes(asset['data'])))
        return dict(row),intent,result,manifest,lineage,assets

    def _draft_get(self, reference, manifest, token, guard):
        from .own_wire import encode_draft, parse_group_get
        request=encode_draft('get',{'media_id':reference},token.token)
        response=self._send(request,token,guard)
        indices=tuple(i for i,a in enumerate(manifest['document']['articles']) if 'cover_info' in a)
        reply=parse_group_get(response,token.token,self.synthetic,reference,requested_cover_indices=indices)
        guard()
        if reply.result is None: fail('PUBLICATION_CURRENT_DRAFT_UNVERIFIED')
        return reply.result

    def _register(self, handle, policy_row, policy_value):
        with self.store.dispatch_lock():
            return self._register_locked(handle, policy_row, policy_value)

    def _register_locked(self, handle, policy_row, policy_value):
        with self.store.connection() as db:
            channel=db.execute('SELECT * FROM publication_channels WHERE account_key=? AND channel_id=?',
                (self.store.key,policy_value['channel_id'])).fetchone()
            if channel is None or channel['state']!='REGISTERED': fail('PUBLICATION_CHANNEL_UNAVAILABLE')
            channel=dict(channel)
        root_identity=strict_json(channel['root_identity_json'].encode())
        with RegisteredRoot(root_identity['path'],root_identity) as source:
            candidate=source.candidate(handle)
            if candidate['manifest']['intent']=='HUMAN_EXPLICIT_MASS':
                # This branch never silently falls through to ordinary publication.
                fail('PUBLICATION_MASS_HUMAN_SOURCE_UNAVAILABLE')
            with self.store.connection() as db, _history_scope(self.policy,db) as history_locators:
                check_baseline(db, self.store.key, channel['channel_id'], policy_value)
                legacy=self._legacy(db,candidate['manifest']['draft_request_key'], history_locators=history_locators)
                row,intent,result,m,lineage,assets=legacy
                from .draft_revision_guard import guard_manifest
                guard_manifest(self.policy,db,m,step_id=row['id'],reference=result['reference'])
                if candidate['document']!=m['document']: fail('PUBLICATION_DOCUMENT_VERSION_CHANGED')
                claims=member_claims(document_members(m, db))
                # Registration time is not evidence of document creation time.
                baseline_guards = claims + [('VERSION', m['version']), ('ROOT', lineage['lineage'])]
                for kind,fp in baseline_guards:
                    if db.execute('SELECT 1 FROM publication_baseline_members WHERE account_key=? AND channel_id=? AND kind=? AND fingerprint=?',
                        (self.store.key,channel['channel_id'],kind,fp)).fetchone():
                        fail('PUBLICATION_PRE_ENABLE_CONTENT')
                for kind,fp in claims:
                    if db.execute('SELECT 1 FROM publication_claims WHERE account_key=? AND kind=? AND fingerprint=?',
                        (self.store.key,kind,fp)).fetchone(): fail('PUBLICATION_ALREADY_CLAIMED')
                original=db.execute('SELECT * FROM publication_candidates WHERE account_key=? AND version=? AND draft_media_id=?',
                    (self.store.key,m['version'],result['reference'])).fetchone()
                if original is not None:
                    saved=strict_json(original['frozen_manifest_json'].encode())
                    if saved['pins']!=candidate['pins']: fail('PUBLICATION_PRODUCER_INPUT_CHANGED')
                    return dict(original),candidate,legacy,claims
                seq=db.execute('SELECT COALESCE(MAX(event_seq),0)+1 FROM publication_candidates WHERE account_key=?',(self.store.key,)).fetchone()[0]
            source.unchanged(candidate['pins'])
        artifact_id='pub-artifact-'+uuid4().hex
        frozen={'pins':candidate['pins'],'manifest_sha':digest(m),'binding_sha':self.store.binding_sha,
            'source_sha':digest(candidate['sources']),'root_identity':root_identity}
        values={'account_key':self.store.key,'artifact_id':artifact_id,'channel_id':channel['channel_id'],
            'policy_id':policy_row['policy_id'],'activation_epoch':policy_row['activation_epoch'],
            'owner_epoch':channel['owner_epoch'],'event_seq':seq,'input_sha':digest(frozen),
            'bundle_id':m['bundle_id'],'version':m['version'],'lineage_root':lineage['lineage'],
            'draft_step_id':row['id'],'draft_media_id':result['reference'],'route_intent':'FREEPUBLISH',
            'human_intent_id':None,'frozen_manifest_json':canonical(frozen),'frozen_sha':digest(frozen),
            'registered_ms':int(self.wall()*1000),'state':'FROZEN'}
        self._current()
        def apply(db,event_seq, *, history_locators=None):
            from .draft_group_store import check_account_writer
            check_account_writer(db, history_locators=history_locators)
            insert(db,'publication_candidates',values)
        commit_event_with_history(self.store,'REGISTER',{'artifact_id':artifact_id,'input_sha':digest(frozen)},apply)
        return values,candidate,legacy,claims

    def _freeze_review(self, artifact, candidate, legacy, current, policy_row, policy_value, diagnostic):
        from .own_bootstrap_security import path_check
        from .publication_render.publication_renderer import render_current, RenderUnavailable
        row,intent,result,manifest,lineage,assets=legacy
        base=self.policy.root/'publication-inputs'
        if not base.exists(): base.mkdir(mode=0o700)
        path_check(base,True)
        folder=base/(artifact['artifact_id']+'-'+uuid4().hex)
        def guard():
            active,_=self._current()
            if active['policy_id']!=policy_row['policy_id']:
                fail('PUBLICATION_AUTHORITY_CHANGED')
            with RegisteredRoot(candidate['root_identity']['path'],candidate['root_identity']) as source:
                source.unchanged(candidate['pins'])
            return True
        try:
            with self.store.connection() as db:
                rendered=render_current(intent['projection'],current,manifest,policy_value,
                    manifest['binding'],db,folder,guard,allowed_root=base)
        except RenderUnavailable as error:
            fail(error.code)
        articles=[]
        for index,actual in enumerate(rendered.articles):
            images=[{'id':'a'+str(index+1)+'-image-'+str(i+1),
                'path':str(folder/image['file']),'sha256':image['sha256']}
                for i,image in enumerate(actual['image_metadata'])]
            sources=[{'id':'a'+str(index+1)+'-'+source['id'],'text':source['text']}
                for source in candidate['sources']]
            articles.append({'id':actual['id'],'title':actual['title'],'text':actual['actual_text'],
                'actual_summary':actual['actual_summary'],'actual_html':actual['actual_html'],
                'actual_html_sha256':actual['actual_html_sha256'],
                'actual_html_path':actual['actual_html_path'],
                'originality_intent':policy_value['originality'],'sources':sources,'images':images,
                'previews':[{'id':'a'+str(index+1)+'-full-frame','path':actual['frame_path'],
                    'sha256':actual['frame']['sha256']}]})
        return {'schema':'PUBLICATION_REVIEW_INPUT_V2','profile_sha':digest({'profile':QUALITY_PROFILE}),
            'current_draft_sha':digest(current),'policy_epoch':policy_row['activation_epoch'],
            'owner_epoch':artifact['owner_epoch'],'expires_ms':int((self.wall()+600)*1000),
            'deterministic_pass':True,'frozen_root':str(folder),
            'render_receipt':{'path':rendered.receipt_path,'sha256':rendered.receipt_sha256},
            'difference_rules':sorted({d['rule'] for d in diagnostic['differences']}),'articles':articles}

    def _review_ready(self):
        if self.reviewer is None:
            from .publication_qa import ReviewRunner
            root=self.policy.root/'publication-runtime'
            self.reviewer=ReviewRunner(root)
        runtime=getattr(self.reviewer,'runtime',None)
        if runtime is None: fail('REVIEW_RUNTIME_UNAVAILABLE')
        surface=runtime.inspect_runtime()
        if not surface.get('runtime_ready') and not (self.synthetic and getattr(runtime,'synthetic',False)):
            fail(surface.get('error','REVIEW_RUNTIME_UNAVAILABLE'))

    def _history(self, intent_key):
        with self.store.connection() as db:
            if not self.store.exists(db): return None
            self.store._verify(db)
            row=db.execute('SELECT intent_id FROM publication_intents WHERE account_key=? AND intent_key=?',
                (self.store.key,intent_key)).fetchone()
            return row['intent_id'] if row else None

    def _intent(self, intent_id):
        with self.store.connection() as db:
            self.store._verify(db)
            row=db.execute('SELECT * FROM publication_intents WHERE account_key=? AND intent_id=?',
                (self.store.key,intent_id)).fetchone()
            if row is None: fail('PUBLICATION_INTENT_NOT_FOUND')
            return dict(row)

    @staticmethod
    def _unclaimed(row):
        return row['submit_count']==0 and row['state'] in {'PREPARED','HOLD'}

    def dispatch(self, artifact_handle, intent_key):
        state=self.status()
        if not state['enabled']: return state
        if type(intent_key) is not str or not re.fullmatch('[A-Za-z0-9._:-]{1,128}',intent_key):
            fail('PUBLICATION_INTENT_KEY_INVALID')
        original=self._history(intent_key)
        if original and not self._unclaimed(self._intent(original)):
            return self.status(original)
        policy_row,policy_value=self._current()
        with self.store.connection() as db:
            self.synthetic=(db.execute('SELECT source_kind FROM own_config WHERE id=1').fetchone()[0]=='SYNTHETIC_SETUP'
                and self.sender is not None and self.sender.mode=='SYNTHETIC_PUBLICATION')
        try: quota.require_provider(self.quota_provider, synthetic_context=self.synthetic)
        except quota.QuotaHold: fail('QUOTA_TRUSTED_SOURCE_UNAVAILABLE')
        self._review_ready()  # No token, current-draft GET or registration before this gate.
        artifact,candidate,legacy,claims=self._register(artifact_handle,policy_row,policy_value)
        with self.store.connection() as db:
            existing=db.execute('SELECT * FROM publication_intents WHERE account_key=? AND artifact_id=?',
                (self.store.key,artifact['artifact_id'])).fetchone()
            if existing is not None:
                if existing['intent_key']!=intent_key:
                    # A new alias never makes a second intent for an old artifact.
                    fail('PUBLICATION_ORIGINAL_INTENT_REQUIRED')
                if not self._unclaimed(existing): return self.status(existing['intent_id'])
                if existing['policy_id']!=policy_row['policy_id']:
                    fail('PUBLICATION_AUTHORITY_CHANGED')
                original=existing['intent_id']
        def guard():
            current,value=self._current()
            if current['policy_id']!=policy_row['policy_id'] or current['revision']!=policy_row['revision']:
                fail('PUBLICATION_AUTHORITY_CHANGED')
            with RegisteredRoot(candidate['root_identity']['path'],candidate['root_identity']) as source:
                source.unchanged(candidate['pins'])
            from .draft_revision_guard import guard_claims,manifest_claims
            old_row,_,old_result,old_manifest,old_lineage,_=legacy
            guard_claims(self.policy,old_manifest['binding'],manifest_claims(old_manifest,
                lineage=old_lineage['lineage'],step_id=old_row['id'],reference=old_result['reference']))
            return True
        token=self._get_token(guard)
        row,old_intent,result,manifest,lineage,assets=legacy
        # First actual snapshot is independently reviewed. A second, final
        # bounded GET below must match it exactly before the sole submission.
        with self.store.dispatch_lock():
            guard()
            attempt=self._quota_initial(artifact['artifact_id'])
            current=self._draft_get(result['reference'],manifest,token,guard)
            diagnostic=compare(old_intent['projection'],current,manifest['document'],policy_value)
        snapshot=self._freeze_review(artifact,candidate,legacy,current,policy_row,policy_value,diagnostic)
        project_root=self.reviewer.root
        runs=project_root/'_local'/'work'
        for directory in (project_root,project_root/'_local',runs):
            if not directory.exists(): directory.mkdir(mode=0o700)
        outcome=self.reviewer.run(snapshot,runs/('qa-'+uuid4().hex),guard)
        if outcome.verdict!='PASS' or outcome.receipt is None:
            fail(outcome.code)
        receipt=outcome.receipt
        usable=receipt.usable_for_publication
        if not usable and not (self.synthetic and receipt.payload.get('origin')=='SYNTHETIC'):
            fail('PUBLICATION_REAL_QA_REQUIRED')
        guard()
        if (digest(receipt.payload)!=receipt.sha256 or receipt.payload['snapshot_sha']!=digest(current)
                or receipt.payload['policy_epoch']!=policy_row['activation_epoch']
                or receipt.payload['owner_epoch']!=artifact['owner_epoch']
                or self.wall()*1000>=receipt.payload['expires_ms']):
            fail('PUBLICATION_REVIEW_BINDING_INVALID')
        review_id='pub-review-'+uuid4().hex
        intent_id=original or 'pub-intent-'+uuid4().hex
        payload={'media_id':result['reference']}
        payload_sha=digest(payload)
        with self.store.dispatch_lock():
            guard()
            raced=self._history(intent_key)
            if raced:
                existing=self._intent(raced)
                if not self._unclaimed(existing): return self.status(raced)
                if (existing['artifact_id']!=artifact['artifact_id']
                        or existing['policy_id']!=policy_row['policy_id']
                        or existing['payload_sha']!=payload_sha):
                    fail('PUBLICATION_ORIGINAL_INTENT_REQUIRED')
                intent_id=raced
            def prepare(db,seq, *, history_locators=None):
                from .draft_group_store import check_account_writer
                check_account_writer(db, history_locators=history_locators)
                insert(db,'publication_reviews',{'account_key':self.store.key,'review_id':review_id,
                    'artifact_id':artifact['artifact_id'],'profile_sha':snapshot['profile_sha'],
                    'input_sha':artifact['input_sha'],'current_draft_sha':digest(current),
                    'owner_epoch':artifact['owner_epoch'],'runtime_receipt_sha':receipt.payload['runtime_surface_sha'],
                    'verdict':'PASS','receipt_json':canonical(receipt.payload),'receipt_sha':receipt.sha256,
                    'created_ms':receipt.payload['created_ms'],'expires_ms':receipt.payload['expires_ms']})
                values={'account_key':self.store.key,'intent_id':intent_id,
                    'intent_key':intent_key,'artifact_id':artifact['artifact_id'],'policy_id':policy_row['policy_id'],
                    'policy_revision':policy_row['revision'],'route':'FREEPUBLISH','audience':'NO_PUSH',
                    'draft_media_id':result['reference'],'lineage_root':lineage['lineage'],'payload_sha':payload_sha,
                    'review_id':review_id,'snapshot_sha':digest(current),'state':'PREPARED'}
                previous=db.execute('SELECT * FROM publication_intents WHERE account_key=? AND intent_id=?',
                    (self.store.key,intent_id)).fetchone()
                if previous is None:
                    insert(db,'publication_intents',values)
                elif (not self._unclaimed(previous) or previous['artifact_id']!=artifact['artifact_id']
                        or previous['intent_key']!=intent_key or previous['policy_id']!=policy_row['policy_id']
                        or previous['payload_sha']!=payload_sha):
                    fail('PUBLICATION_ORIGINAL_INTENT_REQUIRED')
                else:
                    db.execute("UPDATE publication_intents SET review_id=?,snapshot_sha=?,state='PREPARED' "
                        "WHERE account_key=? AND intent_id=? AND submit_count=0 AND state IN ('PREPARED','HOLD')",
                        (review_id,digest(current),self.store.key,intent_id))
            commit_event_with_history(self.store,'PREPARE',{'intent_id':intent_id,'review_sha':receipt.sha256},prepare)
            guard()
            submit_quota=self._quota_final(artifact['artifact_id'],intent_id,attempt)
            final_started=self.clock();final_wall=self.wall()
            final=self._draft_get(result['reference'],manifest,token,guard)
            if final!=current: fail('PUBLICATION_CURRENT_DRAFT_CHANGED')
            # Re-evaluate the full quality profile on the final current object.
            compare(old_intent['projection'],final,manifest['document'],policy_value)
            def deadline_guard():
                guard()
                self._execution_current(token)
                elapsed=self.clock()-final_started;wall_elapsed=self.wall()-final_wall
                if (elapsed<0 or wall_elapsed<0 or elapsed>=10 or abs(elapsed-wall_elapsed)>=5
                        or self.wall()*1000>=receipt.payload['expires_ms']):
                    fail('PUBLICATION_SNAPSHOT_EXPIRED')
                return True
            deadline_guard()
            all_claims=[('EVENT',digest({'event':artifact['event_seq']})),('ROOT',lineage['lineage'])]+claims
            def claim(db,seq, *, history_locators=None):
                deadline_guard()
                from .current_publication_store import guard_legacy_dispatch
                guard_legacy_dispatch(self.policy, self.registry, result['reference'], claims,
                    guard=deadline_guard)
                from .draft_group_store import check_account_writer
                check_account_writer(db, history_locators=history_locators)
                self._quota_apply(quota.claim, db, **self._quota_args(artifact['artifact_id'],attempt),
                    intent_id=intent_id, step='SUBMIT', ordinal=1, observation_sha=submit_quota)
                # All conflict checks are inside the same transaction and account lock.
                for kind,fp in all_claims:
                    insert(db,'publication_claims',{'account_key':self.store.key,'kind':kind,
                        'fingerprint':fp,'intent_id':intent_id})
                cursor=db.execute("UPDATE publication_intents SET state='SUBMITTING',submit_count=1,submit_claim_seq=?,submit_ms=? "
                    "WHERE account_key=? AND intent_id=? AND submit_count=0 AND state='PREPARED'",
                    (seq,int(self.wall()*1000),self.store.key,intent_id))
                if cursor.rowcount!=1: fail('PUBLICATION_ALREADY_CLAIMED')
            commit_event_with_history(self.store,'SUBMIT_CLAIM',{'intent_id':intent_id,'payload_sha':payload_sha,
                'claims':all_claims,'binding_sha':self.store.binding_sha},claim)
            self.fault('claim_before_http')
            try:
                deadline_guard()
                request=encode('freepublish.submit',{'media_id':DraftMediaID(result['reference'],self.store.key,intent_id)},
                    token.token,account_key=self.store.key,intent_id=intent_id)
                response=self._send(request,token,deadline_guard,timeout=max(.01,10-(self.clock()-final_started)))
                from .publication_receipt import capture_submit
                capture=capture_submit(request,response,token.token,
                    account_key=self.store.key,intent_id=intent_id)
                self._record_reply(intent_id,capture.reply,query_seq=None,capture=capture)
            except Exception:
                self._unknown(intent_id)
                raise WCEError('PUBLICATION_RESULT_UNKNOWN_QUERY_ORIGINAL') from None
        return self.status(intent_id)

    def _unknown(self,intent_id):
        def apply(db,seq):
            db.execute("UPDATE publication_intents SET state='RESULT_UNKNOWN' WHERE account_key=? AND intent_id=? AND submit_count=1 AND task_digits IS NULL",
                (self.store.key,intent_id))
        commit_event(self.store,'RESULT_UNKNOWN',{'intent_id':intent_id},apply)

    def _record_reply(self,intent_id,reply,query_seq,capture=None):
        result=reply.result
        task=result.get('task') if result else None
        def json_projection(value):
            if type(value) in (TaskID, ArticleID):
                if value.account_key != self.store.key or value.intent_id != intent_id:
                    fail('PUBLICATION_RESPONSE_SCOPE_MISMATCH')
                return json_projection(asdict(value))
            if type(value) is dict:
                return {k: json_projection(v) for k, v in value.items()}
            if type(value) in (tuple, list):
                return [json_projection(v) for v in value]
            if value is None or type(value) in (str, int, bool):
                return value
            fail('PUBLICATION_RESPONSE_UNVERIFIED')
        projected=json_projection(result)
        proof={'schema':'PUBLICATION_PROOF_V1','origin':'OWN_OFFICIAL_WIRE' if not self.synthetic else 'SYNTHETIC_PUBLICATION',
            'account_key':self.store.key,'binding_sha':self.store.binding_sha,'contract_sha':CONTRACT_SHA,
            'intent_id':intent_id,'query_seq':query_seq,'http_status':reply.http_status,
            'response_sha':reply.response_sha,'wire_profile':WIRE_PROFILE,'result':projected,
            'error_code':reply.error_code,'reason':reply.reason,'created_ms':int(self.wall()*1000)}
        with self.store.connection() as db:
            row=db.execute('SELECT * FROM publication_intents WHERE account_key=? AND intent_id=?',(self.store.key,intent_id)).fetchone()
            if row is None or row['submit_count']!=1: fail()
            proof['pins']={k:row[k] for k in ('policy_id','policy_revision','artifact_id','review_id','snapshot_sha',
                'route','audience','draft_media_id','lineage_root','payload_sha','submit_claim_seq')}
        proof_dir=self.store.anchor/'proofs'
        if not proof_dir.exists(): proof_dir.mkdir(mode=0o700)
        target=proof_dir/('proof-'+uuid4().hex+'.json')
        atomic_write(target,proof,maximum=512*1024)
        if query_seq is None and reply.result is not None:
            from .publication_receipt import stage_submit_receipt
            stage_submit_receipt(self.store,target.name,capture)
        self.fault('proof_before_result_commit')
        if type(task) is TaskID and task.kind == 'PUBLISH_TASK':
            from .current_publication_store import guard_legacy_task
            guard_legacy_task(self.policy, self.registry, task,
                guard=lambda: self._execution_current())
        def apply(db,seq):
            current=db.execute('SELECT * FROM publication_intents WHERE account_key=? AND intent_id=?',(self.store.key,intent_id)).fetchone()
            if current is None or current['payload_sha']!=proof['pins']['payload_sha']: fail()
            if query_seq is None:
                if result is not None:
                    db.execute("UPDATE publication_intents SET state='ACCEPTED',task_kind=?,task_digits=?,task_wire_type=?,task_raw_token=?,last_proof_sha=? WHERE account_key=? AND intent_id=? AND task_digits IS NULL",
                        (task.kind,task.digits,task.wire_type,task.raw_token,digest(proof),self.store.key,intent_id))
                else:
                    db.execute('UPDATE publication_intents SET state=?,last_proof_sha=? WHERE account_key=? AND intent_id=?',
                        ('REJECTED_LOCKED' if reply.error_code else 'RESULT_UNKNOWN',digest(proof),self.store.key,intent_id))
            else:
                if current['query_seq']!=query_seq: fail('PUBLICATION_QUERY_STALE')
                db.execute("UPDATE publication_query_claims SET state=?,proof_sha=? WHERE account_key=? AND intent_id=? AND seq=? AND state='ACTIVE'",
                    ('DONE' if result is not None else 'UNKNOWN',digest(proof),self.store.key,intent_id,query_seq))
                if result is not None:
                    status=result['platform_status']
                    states={0:'PUBLISHED',1:'PROCESSING',2:'PLATFORM_FAILED',3:'PLATFORM_FAILED',4:'PLATFORM_FAILED',5:'PLATFORM_DELETED',6:'PLATFORM_BLOCKED'}
                    old=current['platform_status']
                    if old is not None and old!='1' and status==1: return
                    db.execute('UPDATE publication_intents SET state=?,platform_status=?,effect=?,url_evidence=?,last_proof_sha=? WHERE account_key=? AND intent_id=?',
                        (states[status],str(status),result.get('effect'),result.get('url_evidence'),digest(proof),self.store.key,intent_id))
                    article_id=result.get('article_id')
                    if article_id is not None:
                        if type(article_id) is not ArticleID:
                            fail('PUBLICATION_RESPONSE_UNVERIFIED')
                        if article_id.account_key != self.store.key or article_id.intent_id != intent_id:
                            fail('PUBLICATION_RESPONSE_SCOPE_MISMATCH')
                    for index, url in result.get('article_urls', ()):
                        db.execute('INSERT OR REPLACE INTO publication_articles VALUES(?,?,?,?,?,?,?)',
                            (self.store.key,intent_id,index,article_id.value if article_id else None,url,digest(proof),result.get('url_evidence','INCOMPLETE')))
        commit_event(self.store,'QUERY_RESULT' if query_seq is not None else 'SUBMIT_RESULT',
            {'intent_id':intent_id,'proof_name':target.name,'proof_sha':digest(proof)},apply)

    def poll(self,intent_id):
        policy_row,policy_value=self._current()
        def guard(): self._current();return True
        with self.store.dispatch_lock():
            guard()
            with self.store.connection() as db:
                self.synthetic=(db.execute('SELECT source_kind FROM own_config WHERE id=1').fetchone()[0]=='SYNTHETIC_SETUP'
                    and self.sender is not None and self.sender.mode=='SYNTHETIC_PUBLICATION')
                try: quota.require_provider(self.quota_provider,synthetic_context=self.synthetic)
                except quota.QuotaHold: fail('QUOTA_TRUSTED_SOURCE_UNAVAILABLE')
                row=db.execute('SELECT * FROM publication_intents WHERE account_key=? AND intent_id=?',(self.store.key,intent_id)).fetchone()
                if row is None: fail('PUBLICATION_INTENT_NOT_FOUND')
                row=dict(row)
                if row['route']!='FREEPUBLISH': fail('PUBLICATION_MASS_NOT_IMPLEMENTED')
                if row['state'] in {'PUBLISHED','PLATFORM_FAILED','PLATFORM_DELETED','PLATFORM_BLOCKED','REJECTED_LOCKED'}:
                    return self.status(intent_id)
                if row['task_digits'] is None: return self.status(intent_id)
                if row['query_used']>=5: return self.status(intent_id)|{'query_state':'BUDGET_EXHAUSTED'}
                proof_event=db.execute("SELECT event_json FROM publication_events WHERE account_key=? AND intent_id=? AND event_type='SUBMIT_RESULT' ORDER BY seq DESC LIMIT 1",(self.store.key,intent_id)).fetchone()
                if proof_event is None: fail('PUBLICATION_TASK_PROOF_REQUIRED')
                event=strict_json(proof_event['event_json'].encode())
                from .publication_store import read_file
                proof=read_file(self.store.anchor/'proofs'/event['data']['proof_name'])
                if digest(proof)!=event['data']['proof_sha'] or proof['intent_id']!=intent_id or proof['binding_sha']!=self.store.binding_sha:
                    fail('PUBLICATION_TASK_PROOF_REQUIRED')
                task=TaskID(**proof['result']['task'])
                if task.digits!=row['task_digits'] or task.kind!='PUBLISH_TASK': fail('PUBLICATION_TASK_PROOF_REQUIRED')
                candidate=db.execute('SELECT frozen_manifest_json,version FROM publication_candidates WHERE account_key=? AND artifact_id=?',(self.store.key,row['artifact_id'])).fetchone()
                mrow=db.execute('SELECT manifest,digest FROM own_articles WHERE version=?',(candidate['version'],)).fetchone()
                manifest=stored_manifest(mrow['manifest'],mrow['digest']);count=len(manifest['document']['articles'])
                qrow=db.execute("SELECT attempt FROM publication_quota_claims WHERE account_key=? AND candidate_id=? AND intent_id=? AND step='SUBMIT'",(self.store.key,row['artifact_id'],intent_id)).fetchone()
                if qrow is None: fail('QUOTA_SUBMIT_REQUIRED')
                attempt=qrow[0]
            from .current_publication_store import guard_legacy_task
            guard_legacy_task(self.policy, self.registry, task, guard=guard)
            poll_quota=self._quota_observe(quota.POLL)
            seq=row['query_seq']+1
            def claim(db,event_seq):
                self._quota_apply(quota.claim, db, **self._quota_args(row['artifact_id'],attempt),
                    intent_id=intent_id, step='POLL', ordinal=seq, observation_sha=poll_quota)
                db.execute("UPDATE publication_query_claims SET state='UNKNOWN' WHERE account_key=? AND intent_id=? AND state='ACTIVE'",(self.store.key,intent_id))
                insert(db,'publication_query_claims',{'account_key':self.store.key,'intent_id':intent_id,'seq':seq,
                    'state':'ACTIVE','started_ms':int(self.wall()*1000)})
                db.execute('UPDATE publication_intents SET query_seq=?,query_used=query_used+1 WHERE account_key=? AND intent_id=?',(seq,self.store.key,intent_id))
            commit_event(self.store,'QUERY_CLAIM',{'intent_id':intent_id,'query_seq':seq},claim)
            token=self._get_token(guard)
            try:
                request=encode('freepublish.get',{'task_id':task},token.token,account_key=self.store.key,intent_id=intent_id)
                response=self._send(request,token,guard)
                reply=parse('freepublish.get',response,token.token,account_key=self.store.key,intent_id=intent_id,expected_task=task,article_count=count)
                self._record_reply(intent_id,reply,seq)
            except Exception:
                # An unknown read never consumes or reopens a submission permit.
                return self.status(intent_id)|{'query_state':'QUERY_UNVERIFIED'}
        return self.status(intent_id)


from .draft_group_history_context import locator_scope as _history_scope


from .publication_store import commit_event_with_history
