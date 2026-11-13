"""Host-only Standing/SourceProvider, separate from old inventory Authorization.

Root's normal broker adapter supplies current policy/real workflow and CUP role
pin. There is no public caller source/path/producer/approved argument here.
"""
from dataclasses import dataclass
from pathlib import Path
from hashlib import sha256
import json,os
from .draft_revision_native_source import canonical,require,checked_guard,registration_digest,SourceHold
from .slot_standing_source import StandingSource,adopt_seed
from .slot_producer_roles import RoleRegistry
from .slot_control_cache import HumanControlCache
from .slot_control_semantics import Context,Account,Target
from .slot_fact_cache import FactCache
from .slot_completion_source import declaration
from .slot_saved_draft_source import SavedDraftReader
from .slot_source_store import SlotStore,fingerprint
from .own_connection_registry import mkdir

_SEAL=object()


def _directory(parent,name):
    path=parent/name
    if not os.path.lexists(path):mkdir(parent,name)
    from .own_bootstrap_security import path_check
    path_check(path,True);return path


@dataclass(frozen=True)
class CompletedSlot:
    frozen_json:bytes
    current_verification_json:bytes
    _revalidate:object
    _snapshot_validation:object
    _expected_group:object
    _seal:object
    def __post_init__(self):require(self._seal is _SEAL,'SLOT_UNCHECKED_COMPLETED_SOURCE')
    @property
    def dispatch_protocol(self):return 'SLOT_DISPATCH_BARRIER_V1'
    @property
    def value(self):return json.loads(self.frozen_json)
    @property
    def sha256(self):return sha256(self.frozen_json).hexdigest()
    def fence(self):self._revalidate();return True
    revalidate=fence
    def current_observation(self):return self._revalidate()
    def expected_group(self,reference):
        self.fence();return self._expected_group(reference)
    def validate_remote_snapshot(self,snapshot):
        self.fence();return self._snapshot_validation(snapshot)


class SourceProvider:
    def __init__(self,policy,registry,workflow,profile,adopted_role_sha,guard,*,scan_guard=None):
        self.policy,self.registry,self.workflow,self.profile,self.guard=policy,Path(registry),workflow,profile,guard
        self.scan_guard=guard if scan_guard is None else scan_guard
        root=_directory(self.registry.parent,'slot-sources')
        self.standing=StandingSource(policy,registry,_directory(root,'standing'),guard,scan_guard=self.scan_guard)
        self.roles=RoleRegistry(self.standing,adopted_role_sha,guard)
        owner=fingerprint({'principal':policy.data['actor']['principal_id'],'tenant':policy.data['actor']['tenant_id']})
        self.owner=owner;self.root=root;self.store=SlotStore(_directory(root,'slots'),owner,guard)
        self.reader=SavedDraftReader(workflow,profile,guard)
        require(profile.connection_id==policy.data['connection_id'] and profile.account_id==policy.data['appid']
            and profile.actor.principal_id==policy.data['actor']['principal_id']
            and profile.actor.tenant_id==policy.data['actor']['tenant_id'],'SLOT_PROFILE_BINDING_CHANGED')
        self.control=None;self.controls_observed=None;self.sources={}

    def _context(self,targets=()):
        accounts=tuple(Account(cid,tuple(dict.fromkeys([cid,*self.roles.aliases.get(cid,[])])))for cid in self.standing.value['connections'])
        return Context(self.owner,self.standing.standing_sha,accounts,tuple(targets),self.standing.config_sha)

    def _control(self,targets=(),**work):
        boundary=self.standing.boundary;require(boundary is not None,'SLOT_STANDING_INPUT_PENDING')
        cache=HumanControlCache(_directory(self.root,'control-'+boundary.standing_sha256),self.owner,self.guard,
            lambda fact:self._context(targets),scan_guard=self.scan_guard)
        adopt_seed(cache,boundary);observed=cache.advance(self.standing.lookup,**work)
        self.control,self.controls_observed=cache,observed
        if observed['state']=='CURRENT':cache.fence(self.standing.lookup,observed)
        return observed

    def _targets(self,complete,proofs):
        targets=[]
        for group,proof in zip(complete.value['groups'],proofs):
            gid=fingerprint([complete.value['schedule_id'],complete.value['day'],complete.value['slot'],group['group_index'],proof.value['reference']])
            for member,article in zip(proof.value['members'],proof.value['projection']['articles']):
                aliases=tuple(dict.fromkeys((member['article_id'],article['title'])))
                targets.append(Target(self.profile.connection_id,complete.value['day'],complete.value['slot'],gid,
                    gid+':'+member['article_id'],group['version'],aliases,(proof.sha256,)))
        return targets

    def discover(self,*,cursor=None,**work):
        checked_guard(self.guard);seed=self.standing.advance(**work)
        if seed['state']!='SEED_VERIFIED':return {'authority':False,'state':'INPUT_PENDING','standing':seed,'completed':[]}
        roles=self.roles.roles();pending=[];found=[];candidates=[];limit=work.get('work_records',50000)
        from .contracts import WCEError
        from .slot_native_evidence import completion_text
        from .slot_producer_seed import for_role,SeedNotApplicable
        from .slot_visible_projection import PROFILE as projection_profile
        for role in roles:
            if self.policy.data['connection_id']not in role.value['connections']:continue
            original_key=fingerprint([role.value['producer_role'],role.value['producer_thread']])
            seed=for_role(role,self.guard)
            seed_key=original_key if seed is None else fingerprint([original_key,seed.value['profile'],seed.sha256])
            key=fingerprint([seed_key,projection_profile])
            cache=FactCache(_directory(self.root,'producer-'+key),self.owner,self.guard,
                scan_guard=self.scan_guard,seed=seed,projection_profile=projection_profile)
            cache.initialize()
            try:observed=cache.advance(role.lookup,**work)
            except SeedNotApplicable:
                # A terminal alone is not global quiescence. Preserve the
                # original strict lane and its durable cache, never reset it.
                key=fingerprint([original_key,projection_profile]);seed=None
                cache=FactCache(_directory(self.root,'producer-'+key),self.owner,self.guard,
                    scan_guard=self.scan_guard,projection_profile=projection_profile)
                cache.initialize();observed=cache.advance(role.lookup,**work)
            role.fence()
            if observed['state']!='CURRENT':pending.append({'role':role.value['producer_role'],'state':observed['state']});continue
            registration=registration_digest(role.lookup.locate());scan_cursor=self.store.cursor(key,registration)
            with cache._database()as db:
                page=db.execute('SELECT rowid,fact_json FROM completions WHERE rowid>? AND thread_id=? ORDER BY rowid LIMIT ?',
                    (scan_cursor,role.value['producer_thread'],limit)).fetchall()
            queued=[];after=scan_cursor
            for rowid,encoded in page:
                fact=json.loads(encoded);after=rowid
                if fact['terminal_ordinal']<role.value['activation']['after_ordinal']:continue
                text=completion_text(role.lookup,fact,self.guard)
                if 'WCE_SLOT_DELIVERY_V1\n'in text:queued.append(fact)
            self.store.record_scan(key,registration,scan_cursor,after,queued)
            if len(page)==limit:pending.append({'role':role.value['producer_role'],'state':'INPUT_PENDING'})
            pending_keys=list(dict.fromkeys([original_key,seed_key,key]))
            for fact_key,fact in [(k,f)for k in pending_keys for f in self.store.pending(k,limit)]:
                complete=declaration(role,fact,self.guard)
                if complete.value['connection_id']!=self.policy.data['connection_id']:continue
                try:proofs=[self.reader.read(group)for group in complete.value['groups']]
                except (WCEError,SourceHold) as error:
                    if error.code not in {'SLOT_SAVE_NOT_COMPLETE','SLOT_NORMAL_GET_NOT_MATCHED','NORMAL_GET_RECEIPT_UNAVAILABLE'}:raise
                    pending.append({'role':role.value['producer_role'],'state':'INPUT_PENDING','reason':error.code});continue
                candidates.append((fact_key,complete,proofs,self._targets(complete,proofs)))
        all_targets=tuple(target for _,_,_,targets in candidates for target in targets)
        control=self._control(all_targets,**work)
        if control['state']!='CURRENT':
            pending.append({'state':control['state']})
        else:
            for key,complete,proofs,targets in candidates:
                decisions=[self.control.decision({'connection_id':t.connection_id,'date':t.date,'group_id':t.group_id})for t in targets]
                if any(r['state']=='RESTRICTED'for r in decisions):
                    pending.append({'role':complete.role.value['producer_role'],'state':'CONTROL_RESTRICTED','reasons':decisions});continue
                result=self._freeze(complete,proofs,targets,control);found.append(result)
                self.store.finish_fact(key,complete.fact['item_id'],result['completed_slot_handle'])
        # FROZEN is durable production state, not a consumed discovery reply.
        # Recover the original handle even when an earlier reply was lost.
        data=self.policy.data
        account={'appid':data['appid'],'principal':data['actor']['principal_id'],'tenant':data['actor']['tenant_id']}
        page=self.store.frozen_page(account,cursor);listed=[];visible=[]
        for item in page['items']:
            original=item['frozen'];handle=original['handle']
            try:
                source=self.completed(handle,**work);source.fence();logical=source.value['logical']
                result={'completed_slot_handle':handle,'source_sha256':source.sha256,
                    'connection_id':self.profile.connection_id,'day':logical['day'],'slot':logical['slot'],
                    'groups':len(source.value['content']['groups']),'state':'VERIFIED_SOURCE_ONLY'}
                visible.append(result);listed.append(result)
            except (WCEError,SourceHold) as error:
                # Denial is visible for this original item, never a verified
                # Source. Recheck global authority rather than swallow revoke.
                checked_guard(self.guard);self.standing.base_fence()
                listed.append({'completed_slot_handle':handle,'state':'SOURCE_RESTRICTED','reason':error.code})
        return {'authority':False,'state':'INPUT_PENDING'if pending else'CURRENT','completed':visible,'pending':pending,
            'items':listed,'has_more':page['has_more'],'next_cursor':page['next_cursor']}

    def _freeze(self,complete,proofs,targets,observed):
        role=complete.role.value;v=complete.value;data=self.policy.data
        logical={'appid':data['appid'],'principal':data['actor']['principal_id'],'tenant':data['actor']['tenant_id'],
            'producer_role':role['producer_role'],'channel':role['channel'],'schedule_id':v['schedule_id'],'day':v['day'],'slot':v['slot']}
        groups=[{'group_index':g['group_index'],'selector':p.value['selector'],'save_request_key':g['save_request_key'],
            'reference':p.value['reference'],'members':p.value['members'],'expected_projection_sha256':p.value['projection_sha256']}
            for g,p in zip(v['groups'],proofs)]
        content={'groups':groups}
        verification={'standing_sha256':self.standing.standing_sha,'config_sha256':self.standing.config_sha,
            'role_manifest_sha256':complete.role.manifest_sha256,'producer_fact':complete.fact,
            'producer_text_sha256':complete.text_sha256,'draft_proof_sha256':[p.sha256 for p in proofs],
            'production_qa':v['production_qa'],'control':observed,'binding':data,
            'slot_declaration_origin':'REGISTERED_PRODUCER_NATIVE_FINAL','producer_root_task':complete.fact['root_turn_id']}
        frozen=self.store.freeze(logical,content,verification);cache=self.control
        def check():
            nonlocal observed,cache
            from .slot_index_witness import _source_fence_scope
            with _source_fence_scope(self):
                checked_guard(self.guard);self.standing.boundary.fence();complete.fence()
                for proof in proofs:proof.fence()
                from .contracts import WCEError
                try:cache.fence(self.standing.lookup,observed)
                except (WCEError,SourceHold) as error:
                    if error.code!='SLOT_HUMAN_REOBSERVE_REQUIRED':raise
                    latest=self._control(targets)
                    require(latest['state']=='CURRENT','SLOT_STANDING_INPUT_PENDING')
                    cache,observed=self.control,latest
                    cache.fence(self.standing.lookup,observed)
                require(all(cache.decision({'connection_id':t.connection_id,'date':t.date,'group_id':t.group_id})['state']!='RESTRICTED'
                    for t in targets),'SLOT_CONTROL_RESTRICTED')
                require(self.store.read(frozen['handle'])==frozen,'SLOT_FROZEN_RECORD_CHANGED');checked_guard(self.guard)
                return {'authority':False,'handle':frozen['handle'],'source_sha256':fingerprint(frozen),
                        'standing_sha256':self.standing.standing_sha,'control':observed}
        def validate_snapshot(snapshot):
            for proof in proofs:
                if snapshot.reference==proof.value['reference']:return proof.validate_remote_snapshot(snapshot)
            require(False,'SLOT_REMOTE_SNAPSHOT_UNBOUND')
        def expected_group(reference):
            matches=[(index,proof)for index,proof in enumerate(proofs)if proof.value['reference']==reference]
            require(len(matches)==1,'SLOT_REMOTE_SNAPSHOT_UNBOUND')
            index,proof=matches[0];proof.fence();p=proof.value
            return {'profile':'SLOT_EXPECTED_GROUP_V1','group_index':index,'reference':reference,
                'selector':p['selector'],'members':p['members'],'content_members':p['content_members'],'expected_projection':p['projection'],
                'expected_projection_sha256':p['projection_sha256'],'save_sha':p['save_sha256'],
                'get_sha':p['get_proof_sha256'],'get_proof_policy':p['get_proof_origin'],
                'normal_get_receipt_sha256':p['normal_get_receipt_sha256'],
                'actual_snapshot':None,'actual_snapshot_sha256':None,'dispatch_protocol':'SLOT_DISPATCH_BARRIER_V1'}
        check();result=CompletedSlot(canonical(frozen),canonical(verification),check,validate_snapshot,expected_group,_SEAL)
        self.sources[frozen['handle']]=result
        return {'completed_slot_handle':frozen['handle'],'source_sha256':result.sha256,
            'connection_id':self.profile.connection_id,'day':v['day'],'slot':v['slot'],'groups':len(groups),'state':'VERIFIED_SOURCE_ONLY'}

    def completed(self,handle,**work):
        frozen=self.store.read(handle);logical=frozen['logical'];evidence=frozen['frozen_evidence']
        seed=self.standing.advance(**work);require(seed['state']=='SEED_VERIFIED','SLOT_STANDING_INPUT_PENDING')
        roles=self.roles.roles()
        role=next((r for r in roles if r.value['producer_role']==logical['producer_role']
            and r.value['channel']==logical['channel'] and r.value['schedule_id']==logical['schedule_id']),None)
        require(role is not None,'SLOT_ROLE_REVOKED')
        complete=declaration(role,evidence['producer_fact'],self.guard)
        proofs=[self.reader.read(group)for group in complete.value['groups']];targets=self._targets(complete,proofs)
        observed=self._control(targets,**work);require(observed['state']=='CURRENT','SLOT_STANDING_INPUT_PENDING')
        result=self._freeze(complete,proofs,targets,observed)
        require(result['completed_slot_handle']==handle,'SLOT_FROZEN_RECORD_CHANGED')
        value=self.sources[handle];value.fence();return value
