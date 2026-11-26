import copy
import json
from io import BytesIO
from pathlib import Path
import sys
import tempfile
from time import time
import unittest
from unittest.mock import Mock, patch

WORK = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(WORK / 'plugins/wechat-ecosystem'))
from wce.contracts import WCEError
from wce.own_connection_policy import atomic_write
from wce.own_connection_registry import container, owner_value
from wce.own_production_rules import RulesStore
from wce.own_production_rules_protocol import update_account
from wce.project_context_protocol import DISCONNECT, SPECS
from wce.service import digest
from wce.wechat_authorized_drafts import account as drafts_account
from wce.wechat_component_binding import BASE, OVERVIEW, TOOL, WECHAT, ComponentBinding, ComponentBindingRouter, WorkspaceBroker, _cid

A, B = ('wx' + c * 16 for c in 'ab')
CA, CB = map(_cid, (A, B))
NOW = int(time())
TX = 'a' * 48
ALIAS = 'fixture-direct'
INFO = {'verifiedAt':NOW,'nickname':'同名公众号','avatarUrl':'https://wx.qlogo.cn/fixture/picture','alias':'demo',
        'serviceTypeId':2,'verifyTypeId':0,'injected_secret':'untrusted-discarded'}

def grant(app, generation=1, **kw):
    return dict({'appid':app,'verifiedAt':NOW,'originalId':'gh_scope'+app[-1], 'state':'ACTIVE',
           'generation':generation,'funcInfo':[7,11],'expiresAt':NOW+3600,'refreshState':'CURRENT'}, **kw)

def response(target, state, **kw):
    v = {'state':state, 'transaction':TX, 'expiresAt':NOW+600}
    if target:
        v['expected_authorizer_appid'] = target
    if state == 'PENDING':
        v['authorizeUrl'] = BASE+'/authorize?transaction='+TX
    return {**v, **kw}

class Transport:
    def __init__(self):
        self.log = []
        self.preflight = (200, {'state':'TARGET_READY','expected_authorizer_appid':A})
        self.workspace = [grant(A), grant(B)]
        self.start = self.status = response(A, 'PENDING')
        self.cancel = response(A,'CANCELLED')
        self.profile = (200,{'state':'ACTIVE','appid':A,'originalId':'gh_scopea','generation':1,'authorizerInfo':INFO})
    def request(self, path, proof, **options):
        self.log.append((path, options))
        if path == 'status' and 'profile' in options: return copy.deepcopy(self.profile)
        if path == 'status' and 'target' in options: return copy.deepcopy(self.preflight)
        if path == 'status' and not options: return 200, {'bindings':copy.deepcopy(self.workspace)}
        value = getattr(self,path)
        if isinstance(value, Exception): raise value
        return 200, copy.deepcopy(value)

class Inner:
    def __init__(self):
        self.rows=[]; self.writes=0; self.fail=None
    def list_tools(self):return [{'name':DISCONNECT,'inputSchema':SPECS[DISCONNECT]}]
    def call(self,name,args):
        if name in (OVERVIEW,'own.connections.list'):return {'connections':copy.deepcopy(self.rows)}
        if name != DISCONNECT: raise AssertionError(name)
        self.writes+=1
        if self.fail == 'before':raise WCEError('REMOVAL_UNKNOWN')
        r = next(r for r in self.rows if r['connection_id']==args['connection_id'])
        assert r['account_id']==args['account_id'] and r['binding_revision']==args['binding_revision']
        r['state']='DISCONNECTED'
        if self.fail == 'after':raise WCEError('REMOVAL_UNKNOWN')
        return {'state':'DISCONNECTED','connection_id':r['connection_id']}

class Rebind(unittest.TestCase):
    def setUp(self):
        self.folder=tempfile.TemporaryDirectory()
        self.addCleanup(self.folder.cleanup)
        self.path=Path(self.folder.name);self.registry=self.path/'connections.json'
        owner=owner_value(self.registry,{'principal_id':'fixture-person','tenant_id':'fixture-workspace'})
        atomic_write(self.path/'connection-owner.json',owner)
        atomic_write(self.registry,{'schema':2,'owner_digest':digest(owner),'connections':{},'entries':{}})
        for name in ('connections.lock','connection-setup.lock'): (self.path/name).touch(mode=0o600)
        self.proof=Mock();self.transport=Transport();self.inner=Inner();self.reload()
        self.assertEqual(self.act('WORKSPACE_STATUS')['binding_count'],2)
        self.transport.log.clear()
    def reload(self):
        self.binding=ComponentBinding(self.registry,transport=self.transport,workspace_proof=self.proof,clock=lambda:NOW)
        self.router=ComponentBindingRouter(self.inner,self.registry,self.binding)
    def act(self,op,cid=None):
        args={'operation':op}
        if cid:args['connection_id']=cid
        return self.router.call(TOOL,args)
    def collection(self):return self.router.call(OVERVIEW,{})['connections']
    def remove_args(self,app):
        row=next(r for r in self.collection() if r['account_id']==app and r['state']!='DISCONNECTED')
        args={k:row[k] for k in ('platform_id','account_id','connection_id','binding_revision')}
        if row.get('component_grant'):args['expected_grant_generation']=row['component_grant']['generation']
        return args
    def direct(self):
        self.inner.rows=[{'platform_id':WECHAT,'account_id':A,'connection_id':ALIAS,'binding_revision':'r1','state':'BOUND_IDLE'}]
    def begin(self): self.assertEqual(self.act('BEGIN',CA)['status'],'PENDING')
    def bind(self,gen=2):
        self.transport.status=response(A,'BOUND',appid=A,binding=grant(A,gen,authorizerInfo=INFO))
        return self.act('STATUS',CA)

    def test_preflight_fails_closed_old_broker_wrong_target_and_unverified(self):
        for check in ((200,{'bindings':[]}), (200,{'state':'TARGET_READY','expected_authorizer_appid':B}),
                      (404,{'state':'TARGET_UNVERIFIED'})):
            self.transport.preflight=check
            self.assertEqual(self.act('BEGIN',CA)['status'],'TARGET_UNVERIFIED' if check[0]==404 else 'REAUTH_TARGET_UNCONFIRMED')
        self.assertEqual(self.act('BEGIN','not-connected')['status'],'REAUTH_TARGET_UNAVAILABLE')
        self.assertFalse(any(op=='start' for op,_ in self.transport.log))
    def test_same_request_only_across_reopen_cancel_and_two_accounts(self):
        self.begin(); self.reload()
        self.assertEqual(self.act('BEGIN',CA)['status'],'PENDING')
        for op in ('STATUS','BEGIN','CANCEL'):
            for cid in (CB,None):
                self.assertEqual(self.act(op,cid)['status'],'REAUTH_INTENT_CONFLICT')
        self.assertEqual(self.act('CANCEL',CA)['status'],'CANCELLED')
        self.assertEqual(self.act('STATUS',CB)['status'],'IDLE')
        self.assertEqual(sum(op=='start' for op,_ in self.transport.log),1)
        self.assertEqual(sum(op=='cancel' for op,_ in self.transport.log),1)
    def test_unknown_start_reuses_persisted_key_and_target(self):
        self.transport.start=WCEError('WECHAT_COMPONENT_SERVICE_UNAVAILABLE')
        self.assertEqual(self.act('BEGIN',CA)['status'],'WECHAT_COMPONENT_SERVICE_UNAVAILABLE')
        self.reload()
        self.assertEqual(self.act('STATUS',CA)['status'],'START_RECOVERY_REQUIRED')
        self.assertEqual(self.act('BEGIN',CB)['status'],'REAUTH_INTENT_CONFLICT')
        self.transport.start=response(A,'PENDING');self.begin()
        starts=[opts for op,opts in self.transport.log if op=='start']
        self.assertEqual(starts[0],starts[1]);self.assertEqual(starts[0]['target'],A)
    def test_generic_add_keeps_legacy_contract(self):
        self.transport.start=response(None,'PENDING')
        self.assertEqual(self.act('BEGIN')['status'],'PENDING')
        self.assertEqual(self.act('STATUS',CA)['status'],'REAUTH_INTENT_CONFLICT')
        self.assertEqual([op for op,v in self.transport.log],['start'])
        self.assertEqual(set(self.transport.log[0][1]),{'idempotency'})
    def test_echo_required_and_wrong_callback_not_written(self):
        self.begin(); orig=self.binding._cache()
        self.transport.status=response(None,'BOUND',appid=A,binding=grant(A,3))
        self.assertEqual(self.act('STATUS',CA)['status'],'REAUTH_TARGET_UNCONFIRMED')
        self.transport.status=response(A,'BOUND',appid=B,binding=grant(B,10))
        self.assertEqual(self.act('STATUS',CA)['status'],'REAUTH_ACCOUNT_MISMATCH')
        self.assertEqual(self.binding._cache(),orig)
    def test_correct_account_configuration_unchanged_after_restart(self):
        store=RulesStore(self.registry);status=store.summary(CA,'account')
        self.assertTrue(update_account(store,{'connection_id':CA,'expected_store_revision':status['store_revision'],
            'expected_scope_revision':status['scope_revision'],'changes':{'audience_topics':'家庭录音','author':'本号署名'}})['readback_matches'])
        before={c:store.summary(c,'account',effective=True)['fields'] for c in (CA,CB)}
        self.begin();v=self.bind()
        self.assertEqual((v['status'],v['account_id'],v['connection_id']),('BOUND',A,CA))
        self.reload();self.assertEqual(before,{c:RulesStore(self.registry).summary(c,'account',effective=True)['fields'] for c in (CA,CB)})
        p=self.collection()[0]['official_profile']
        self.assertEqual((p['nickname'],p['avatar_url'],p['generation']),('同名公众号',INFO['avatarUrl'],2))
    def test_direct_alias_returned_and_unknown_rejected_by_site(self):
        policy=Mock();policy.data={'appid':A}
        with patch('wce.own_connection_policy.resolve',return_value=policy):
            self.transport.preflight=(404,{'state':'TARGET_UNVERIFIED'})
            self.assertEqual(self.act('BEGIN',ALIAS)['status'],'TARGET_UNVERIFIED')
            self.transport.preflight=(200,{'state':'TARGET_READY','expected_authorizer_appid':A})
            self.assertEqual(self.act('BEGIN',ALIAS)['status'],'PENDING')
            self.assertEqual(self.act('STATUS',CA)['status'],'REAUTH_INTENT_CONFLICT')
            self.transport.status=response(A,'BOUND',appid=A,binding=grant(A,2))
            self.assertEqual(self.act('STATUS',ALIAS)['connection_id'],ALIAS)
            policy.check.assert_called_with(readonly=True)
    def test_completed_old_status_cannot_rewind_newer_or_reinstate_removed(self):
        self.begin();self.bind()
        self.transport.workspace=[grant(A,3),grant(B)]
        self.act('WORKSPACE_STATUS')
        self.assertEqual(self.act('STATUS',CA)['status'],'TARGET_STALE')
        self.assertEqual(self.binding._cache()['rows'][0]['generation'],3)
        args=self.remove_args(A);self.router.call(DISCONNECT,args)
        self.assertEqual(self.act('STATUS',CA)['status'],'REAUTH_TARGET_UNAVAILABLE')
        self.assertFalse(any(r['account_id']==A for r in self.collection()))
    def test_pending_result_older_than_workspace_returns_stale(self):
        self.begin()
        self.transport.workspace=[grant(A,3),grant(B)];self.act('WORKSPACE_STATUS')
        self.assertEqual(self.bind(2)['status'],'TARGET_STALE')
        self.assertEqual(self.collection()[0]['component_grant']['generation'],3)
    def test_profile_single_account_does_not_refresh_grant_or_other_accounts(self):
        stale=NOW-90000
        self.binding._save_bindings([grant(A),grant(B)],checked_at=stale)
        self.assertEqual(self.act('PROFILE_STATUS',CA)['status'],'PROFILE_READ')
        self.assertEqual(self.binding._cache()['checked_at'],stale)
        self.assertTrue(all(r['state']=='ACTION_REQUIRED' for r in self.collection()))
        self.assertEqual(self.collection()[0]['official_profile']['nickname'],'同名公众号')
        self.assertNotIn('nickname',self.collection()[1]['official_profile'])
        self.assertNotIn('injected_secret',(self.binding.root/'workspace-bindings.json').read_text())
        self.act('WORKSPACE_STATUS')
        self.assertEqual(self.collection()[0]['official_profile']['nickname'],'同名公众号')
        for g in (grant(A,2),grant(A,1,originalId='gh_changed'),grant(A,1,state='REVOKED')):
            self.binding._save_bindings([grant(A,authorizerInfo=INFO),grant(B)])
            self.transport.workspace=[g,grant(B)];self.act('WORKSPACE_STATUS')
            self.assertNotIn('nickname',self.collection()[0]['official_profile'])
    def test_profile_mismatch_never_applies(self):
        orig=self.binding._cache();good=self.transport.profile[1]
        for update in ({'appid':B},{'originalId':'gh_wrong'},{'generation':2},{'state':'REVOKED'}):
            self.transport.profile=(200,dict(good,**update))
            self.assertEqual(self.act('PROFILE_STATUS',CA)['status'],'PROFILE_UNAVAILABLE')
        self.assertEqual(orig,self.binding._cache())
    def test_removal_rejects_account_revision_and_generation_substitutions(self):
        args=self.remove_args(A)
        for key,value in (('connection_id',CB),('account_id',B),('binding_revision','wrong'),('expected_grant_generation',2)):
            with self.assertRaises(WCEError):self.router.call(DISCONNECT,dict(args,**{key:value}))
        self.assertEqual(len(self.collection()),2)
    def test_scanned_detach_refresh_reopen_old_deeplink_denied_other_ok(self):
        args=self.remove_args(A)
        self.assertEqual(self.router.call(DISCONNECT,args)['remote_revocation'],'NOT_REQUESTED')
        self.assertEqual(self.router.call(DISCONNECT,args)['state'],'DISCONNECTED')
        self.reload()
        self.assertEqual(self.act('WORKSPACE_STATUS')['binding_count'],1)
        self.assertEqual([r['connection_id'] for r in self.collection()],[CB])
        with self.assertRaises(WCEError):drafts_account(self.binding,self.inner,CA)
        self.assertEqual(drafts_account(self.binding,self.inner,CB)['appid'],B)
        self.assertEqual(self.inner.writes,0)
        self.assertFalse(any(op!='status' for op,_ in self.transport.log))
        self.transport.start=response(None,'PENDING');self.act('BEGIN')
        self.transport.status=response(None,'BOUND',appid=A,binding=grant(A,2))
        self.assertEqual(self.act('STATUS')['status'],'BOUND')
        self.assertCountEqual([r['connection_id'] for r in self.collection()],[CA,CB])
    def test_removal_refuses_unfinished_same_account_authorization(self):
        args=self.remove_args(A);self.begin()
        with self.assertRaises(WCEError):self.router.call(DISCONNECT,args)
        self.assertEqual(len(self.collection()),2)
    def test_direct_remove_alone(self):
        self.transport.workspace=[grant(B)]
        self.act('WORKSPACE_STATUS');self.direct();args=self.remove_args(A)
        self.assertNotIn('expected_grant_generation',args)
        self.assertEqual(self.router.call(DISCONNECT,args)['state'],'DISCONNECTED')
        self.assertEqual(self.inner.writes,1);self.assertEqual([r['connection_id'] for r in self.collection()],[CB])
    def test_mixed_removal_lost_response_recovers_without_second_direct_write(self):
        self.direct();args=self.remove_args(A);self.inner.fail='after'
        with self.assertRaises(WCEError):self.router.call(DISCONNECT,args)
        self.reload();self.inner.fail=None
        self.assertEqual(self.router.call(DISCONNECT,args)['state'],'DISCONNECTED')
        self.assertEqual(self.inner.writes,1)
        self.act('WORKSPACE_STATUS');self.assertEqual([r['connection_id'] for r in self.collection()],[CB])
    def test_mixed_removal_failure_before_direct_write_recoverable(self):
        self.direct();args=self.remove_args(A);self.inner.fail='before'
        with self.assertRaises(WCEError):self.router.call(DISCONNECT,args)
        self.reload();self.inner.fail=None
        self.assertFalse(any(r['appid']==A for r in self.binding._cache()['rows']))
        self.assertEqual(self.router.call(DISCONNECT,args)['state'],'DISCONNECTED')
        self.assertEqual(self.inner.writes,2)
    def actual_legacy_direct(self):
        from wce.own_connection_policy import CAPABILITIES, POLICY
        from wce.own_settings_protocol import native_overview
        from wce.project_context_protocol import ProjectContextRouter
        root=self.path/'legacy';root.mkdir(mode=0o700)
        (root/'images').mkdir(mode=0o700)
        (root/'state.sqlite3').touch(mode=0o600)
        data={'actor':{'principal_id':'fixture','tenant_id':'fixture','client_id':'fixture','session_id':'fixture'},
              'resource_id':A,'appid':A,'connection_id':ALIAS,'generation':1,'epoch':0,'private_directory':str(root)}
        item={'schema':1,'policy':POLICY,'id':'original-connection','revision':1,'identity':data,
              'candidate_scope':'f'*64,'capabilities':CAPABILITIES,'duration':'UNTIL_DISCONNECTED',
              'enabled':True,'confirmed_at':NOW}
        policy_path=root/'connection-policy.json'
        atomic_write(policy_path,item);atomic_write(self.registry,{'schema':1,'connections':{ALIAS:str(policy_path)}})
        class Native:
            def call(_, name, args):
                assert name==OVERVIEW
                return {'connections':[dict(x,platform_id=WECHAT) for x in native_overview(self.registry)['connections']]}
        real=ProjectContextRouter(Native(),registry=self.registry)
        self.router=ComponentBindingRouter(real,self.registry,self.binding)
        return real, policy_path, item

    def test_actual_legacy_direct_policy_alias_rebind_mixed_detach_and_restart(self):
        from wce.own_connection_policy import load_policy
        real,policy_path,item = self.actual_legacy_direct()
        self.assertEqual(self.act('BEGIN',ALIAS)['status'],'PENDING')
        self.transport.status=response(A,'BOUND',appid=A,binding=grant(A,2,authorizerInfo=INFO))
        self.assertEqual(self.act('STATUS',ALIAS)['connection_id'],ALIAS)
        self.assertEqual(load_policy(policy_path).value,item)
        args=self.remove_args(A)
        self.assertEqual(args['expected_grant_generation'],2)
        self.assertEqual(self.router.call(DISCONNECT,args)['state'],'DISCONNECTED')
        self.assertFalse(load_policy(policy_path,active=False).value['enabled'])
        self.reload();self.router=ComponentBindingRouter(real,self.registry,self.binding)
        self.act('WORKSPACE_STATUS')
        self.assertEqual([x['connection_id'] for x in self.collection()],[CB])
        self.assertIsNone(self.binding._target(ALIAS))

    def first_direct(self):
        from hashlib import sha256
        from wce.own_bootstrap_security import path_check
        from wce.own_connection_enrollment import published_entry
        from wce.own_connection_registry import transaction_path
        real,path,policy = self.actual_legacy_direct()
        # A well-formed synthetic committed legacy enrollment, checked by the
        # actual owner/membership rules store, original policy and inode pins.
        root=path.parent
        owner=owner_value(self.registry,policy['identity']['actor'])
        atomic_write(self.path/'connection-owner.json',owner)
        policy=policy | {'schema':2,'transaction':'txn-'+'e'*32,
                         'registry_path':str(self.registry),'owner_digest':digest(owner)}
        atomic_write(path,policy)
        registry={'schema':2,'owner_digest':digest(owner),'connections':{ALIAS:str(path)},
                  'entries':{ALIAS:published_entry(policy,'测试号')}}
        atomic_write(self.registry,registry)
        txn=transaction_path(self.registry,policy['transaction'])
        txn.parent.mkdir(mode=0o700);txn.with_suffix('.lock').touch(mode=0o600)
        atomic_write(root/'profile.json',dict(policy['identity'],schema=1,source_kind='OPERATOR_ATTESTED',expires_at=1))
        pins={'root':list(path_check(root,True)),'images':list(path_check(root/'images',True)),
              'database':list(path_check(root/'state.sqlite3')[:2]),
              'profile_sha256':sha256((root/'profile.json').read_bytes()).hexdigest(),'revoked':False}
        atomic_write(txn,{'schema':1,'id':policy['transaction'],'state':'COMMITTED','owner':owner,'registry':str(self.registry),
                          'journal_parent':list(path_check(txn.parent,True)),'policies':{str(path):{'after':policy,'pins':pins}},
                          'after':registry})
        self.transport.workspace=[grant(B)]
        self.act('WORKSPACE_STATUS')
        self.transport.preflight=(200,{'state':'LEGACY_TARGET_READY','expected_authorizer_appid':A})
        self.transport.log.clear()
        return real,path,policy

    def test_first_legacy_scope_no_server_claim_before_verified_active_grant(self):
        real,path,policy=self.first_direct()
        store=RulesStore(self.registry)
        status=store.summary(ALIAS,'account')
        self.assertTrue(update_account(store,{'connection_id':ALIAS,'expected_store_revision':status['store_revision'],
            'expected_scope_revision':status['scope_revision'],'changes':{'audience_topics':'录音听众','author':'旧号署名'}})['readback_matches'])
        before=store.summary(ALIAS,'account',effective=True)['fields']
        self.assertEqual(self.act('TARGET_STATUS',ALIAS),{'status':'LEGACY_TARGET_READY','http_status':200,'connection_id':ALIAS,'account_id':A})
        self.assertIsNone(self.binding._load_flow())
        self.assertEqual(self.act('PROFILE_STATUS',ALIAS)['status'],'PROFILE_UNAVAILABLE')
        with self.assertRaises(WCEError):drafts_account(self.binding,self.inner,ALIAS)
        self.assertEqual(self.act('BEGIN',ALIAS)['status'],'PENDING')
        self.reload();self.router=ComponentBindingRouter(real,self.registry,self.binding)
        self.assertEqual(self.act('BEGIN',ALIAS)['status'],'PENDING')
        row=next(r for r in self.collection() if r['account_id']==A)
        self.assertNotIn('component_grant',row)
        self.transport.status=response(A,'BOUND',appid=A,binding=grant(A,1,authorizerInfo=INFO))
        bound=self.act('STATUS',ALIAS)
        self.assertEqual((bound['status'],bound['account_id'],bound['connection_id']),('BOUND',A,ALIAS))
        self.assertEqual(self.act('STATUS',ALIAS)['connection_id'],ALIAS)
        self.assertEqual(next(r for r in self.collection() if r['account_id']==A)['component_grant']['generation'],1)
        self.assertEqual(store.summary(ALIAS,'account',effective=True)['fields'],before)
        self.assertEqual(json.loads(path.read_bytes()),policy)
        self.assertEqual(sum(op=='start' for op,v in self.transport.log),1)
        self.assertEqual(self.act('TARGET_STATUS',ALIAS)['status'],'REAUTH_TARGET_UNCONFIRMED')
        self.assertEqual(self.act('TARGET_STATUS',CA)['status'],'REAUTH_TARGET_UNCONFIRMED')

    def test_legacy_wrong_target_and_cross_workspace_do_not_create_membership(self):
        self.first_direct();before=self.binding._cache()
        self.transport.preflight=(200,{'state':'LEGACY_TARGET_READY','expected_authorizer_appid':B})
        self.assertEqual(self.act('BEGIN',ALIAS)['status'],'REAUTH_TARGET_UNCONFIRMED')
        self.transport.preflight=(200,{'state':'LEGACY_TARGET_READY','expected_authorizer_appid':A})
        self.assertEqual(self.act('BEGIN',ALIAS)['status'],'PENDING')
        self.transport.status=response(A,'BOUND',appid=B,binding=grant(B,2))
        self.assertEqual(self.act('STATUS',ALIAS)['status'],'REAUTH_ACCOUNT_MISMATCH')
        self.assertEqual(self.binding._cache(),before)
        self.assertEqual(self.act('BEGIN',ALIAS)['status'],'PENDING')
        self.transport.status=response(A,'WORKSPACE_CONFLICT')
        self.assertEqual(self.act('STATUS',ALIAS)['status'],'WORKSPACE_CONFLICT')
        self.assertEqual(self.binding._cache(),before)
        self.assertEqual(self.act('PROFILE_STATUS',ALIAS)['status'],'PROFILE_UNAVAILABLE')

    def test_raw_appid_or_revoked_local_direct_policy_cannot_enter_first_grant(self):
        real,path,policy=self.first_direct()
        self.assertEqual(self.act('BEGIN',A)['status'],'REAUTH_TARGET_UNAVAILABLE')
        self.assertEqual(self.act('BEGIN',CA)['status'],'REAUTH_TARGET_UNAVAILABLE')
        atomic_write(path,policy | {'enabled':False})
        self.assertEqual(self.act('BEGIN',ALIAS)['status'],'REAUTH_TARGET_UNAVAILABLE')
        self.assertEqual(self.transport.log,[])
        self.assertIsNone(self.binding._load_flow())

    def test_target_status_read_only_exact_target_and_busy(self):
        self.assertEqual(self.act('TARGET_STATUS',CA),{'status':'TARGET_READY','http_status':200,'connection_id':CA,'account_id':A})
        self.transport.preflight=(409,{'state':'TARGET_BUSY','expected_authorizer_appid':A})
        self.assertEqual(self.act('TARGET_STATUS',CA)['status'],'TARGET_BUSY')
        self.transport.preflight=(200,{'state':'TARGET_READY','expected_authorizer_appid':B})
        self.assertEqual(self.act('TARGET_STATUS',CA)['status'],'REAUTH_TARGET_UNCONFIRMED')
        self.assertIsNone(self.binding._load_flow())
        self.assertEqual([op for op,v in self.transport.log],['status','status','status'])
    def test_cancel_during_exchange_then_confirm_original(self):
        self.begin();self.transport.cancel=response(A,'EXCHANGING',cancelRequested=True)
        pending=self.act('CANCEL',CA)
        self.assertEqual((pending['status'],pending['cancel_requested']),('EXCHANGING',True))
        self.reload();self.transport.status=response(A,'EXCHANGE_UNKNOWN',cancelRequested=True)
        self.assertEqual(self.act('BEGIN',CA)['status'],'EXCHANGE_UNKNOWN')
        self.assertEqual(self.act('BEGIN',CB)['status'],'REAUTH_INTENT_CONFLICT')
        self.transport.status=response(A,'CANCELLED',cancelRequested=True)
        self.assertEqual(self.act('STATUS',CA)['status'],'CANCELLED')
        self.assertEqual(sum(op=='start' for op,v in self.transport.log),1)

    def test_unreadable_direct_registry_does_not_commit_partial_scan_only_removal(self):
        args=self.remove_args(A)
        for rows,reads in (([],{WECHAT:{'state':'FAILED'}}),([{'platform_id':WECHAT,'connection_id':ALIAS,
                   'recovery':{'registered_appid':A},'state':'ACTION_REQUIRED'}],{})):
            with patch.object(self.inner,'call',return_value={'connections':rows,'platform_reads':reads}):
                with self.assertRaises(WCEError):self.router.call(DISCONNECT,args)
            self.assertEqual(self.binding._removals(),{})
    def test_wire_contract_target_and_profile(self):
        requests=[]
        class Reply(BytesIO):
            status=200
            def geturl(self):return requests[-1].full_url
        def opener(req,timeout):
            requests.append(req);return Reply(b'{}')
        broker=WorkspaceBroker(opener);proof=Mock();proof.reveal_for_adapter.return_value='fixture-only'
        broker.request('status',proof,target=A);broker.request('start',proof,target=A,idempotency='a'*43)
        broker.request('status',proof,transaction=TX);broker.request('cancel',proof,transaction=TX)
        broker.request('status',proof,profile=A)
        self.assertEqual(requests[0].full_url,BASE+'/status?expected_authorizer_appid='+A)
        self.assertEqual(json.loads(requests[1].data),{'expected_authorizer_appid':A})
        self.assertEqual(requests[2].full_url,BASE+'/status?transaction='+TX)
        self.assertEqual(json.loads(requests[3].data),{'transaction':TX})
        self.assertEqual(requests[4].full_url,BASE+'/status?profile_appid='+A)

if __name__=='__main__':unittest.main(verbosity=2)
