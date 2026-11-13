"""Verify original normal save/GET facts; never perform GET or mint a grant."""
from dataclasses import dataclass
from hashlib import sha256
import json,os
from .draft_revision_native_source import require,canonical,checked_guard
from .service import digest
from .slot_source_files import private_json

_SEAL=object()


@dataclass(frozen=True)
class SavedDraftProof:
    canonical_bytes:bytes
    _revalidate:object
    _snapshot_validation:object
    _seal:object
    def __post_init__(self):require(self._seal is _SEAL,'SLOT_UNCHECKED_DRAFT_PROOF')
    @property
    def value(self):return json.loads(self.canonical_bytes)
    @property
    def sha256(self):return sha256(self.canonical_bytes).hexdigest()
    def fence(self):self._revalidate();return True
    def validate_remote_snapshot(self,snapshot):
        self.fence();return self._snapshot_validation(snapshot)


class SavedDraftReader:
    def __init__(self,workflow,profile,guard,*,registered_drafts=False):
        from .own_connection_workflow import PersistentWorkflow
        require(type(workflow)is PersistentWorkflow,'SLOT_REAL_WORKFLOW_REQUIRED')
        self.workflow=workflow;self.profile=profile;self.guard=guard
        self.registered_drafts=registered_drafts

    def _read(self,group):
        from .draft_group_history_context import readonly_history_snapshot
        from .own_workflow import _body_projection
        from .own_normal_get_receipt import load,filename
        from .own_draft_wire import reference_valid
        w,p=self.workflow,self.profile
        checked_guard(self.guard);w.policy.check()
        require(w._profile(p.actor,p.connection_id).binding()==p.binding(),'SLOT_DRAFT_BINDING_CHANGED')
        with readonly_history_snapshot(w.policy,w.db.path)as(db,h):
            if self.registered_drafts:
                # The scoped route checks this saved step, its approval and the
                # referenced uploads below. It does not replay unrelated drafts.
                from .draft_group_history_context import require_history
                from .own_store import OwnStore
                require_history(w.policy,db,h)
                version=db.execute('PRAGMA user_version').fetchone()[0]
                OwnStore._check_layout(db,p.source_kind,version)
                w._resource_identity(db,p)
                row=db.execute(
                    'SELECT * FROM own_steps WHERE tenant=? AND principal=? AND connection=? AND request_key=?',
                    w._scope(p)+(group['save_request_key'],)).fetchone()
            else:
                w._resource(db,p,history_locators=h)
                row=w._history(db,p,group['save_request_key'],history_locators=h)
            require(row is not None and row['operation']=='add'and row['state']=='SUCCEEDED','SLOT_SAVE_NOT_COMPLETE')
            intent,result=w._step(db,p,row,history_locators=h)
            require(reference_valid(result.get('reference'),p.source_kind=='SYNTHETIC_SETUP')
                and intent['selector']=={k:group[k]for k in ('bundle_id','version','content_digest')},'SLOT_SAVE_IDENTITY_CHANGED')
            m,d=w._bundle(db,p,group['bundle_id'],group['version'])
            require(d==group['content_digest'] and m['schema']in(2,3),'SLOT_SAVE_IDENTITY_CHANGED')
            articles=m['document']['articles']
            members=[{'article_id':a['id'],'article_sha256':digest(a),
                'source_html_sha256':a.get('provenance',{}).get('source_sha256')}for a in articles]
            require(members==group['articles'],'SLOT_SAVE_MEMBERS_CHANGED')
            from .publication_producer import document_members
            content_members=document_members(m,db)
            normal=None;normal_sha=None
            if os.path.lexists(w.db.path.parent/filename(row['id'])):
                normal,normal_sha=load(w,p,row,intent,result)
            strict=row['readback']=='MATCHED'
            observed=False
            if normal is not None:
                rep=normal['platform_representation']
                if rep is not None:
                    require(rep['expected_projection_sha256']==digest(intent['projection'])
                        and rep['actual_response_sha256']==normal['response_sha256']
                        and rep['byte_exact']==(rep['expected_projection_sha256']==rep['actual_projection_sha256'])
                        and (normal['readback_state']!='MATCHED'or rep['byte_exact']),
                        'SLOT_GET_RECEIPT_INCONSISTENT')
                    observed=(rep['state']=='PLATFORM_REPRESENTATION_MATCHED'
                              and rep['platform_representation_match']is True)
                    require(observed==(rep['state']=='PLATFORM_REPRESENTATION_MATCHED')
                        and observed==rep['platform_representation_match'],'SLOT_GET_RECEIPT_INCONSISTENT')
            require(strict or observed,'SLOT_NORMAL_GET_NOT_MATCHED')
            # The first parsed receipt is immutable, including UNVERIFIED. A
            # later real strict MATCHED must retain its journal provenance; an
            # earlier unmatched response cannot become the matched GET proof.
            receipt_proves_match=normal is not None and (normal['readback_state']=='MATCHED' or observed)
            save_sha=digest({k:row[k]for k in ('id','owner','tenant','principal','connection','resource','request_key','intent_digest','result_digest','manifest_digest','created','completed')})
            journal_get={'profile':'NORMAL_GET_MATCHED_JOURNAL_V1','step_id':row['id'],'save_sha256':save_sha,
                         'binding_sha256':digest(p.binding()),'reference_sha256':digest(result['reference']),'readback':row['readback']}
            value={'schema':1,'authority':False,'connection_id':p.connection_id,'account_id':p.account_id,
                'binding':p.binding(),'selector':intent['selector'],'step_id':row['id'],
                'intent_sha256':row['intent_digest'],'result_sha256':row['result_digest'],
                'manifest_sha256':row['manifest_digest'],'reference':result['reference'],'save_sha256':save_sha,
                'get_proof_sha256':normal_sha if receipt_proves_match else digest(journal_get),
                'get_proof_origin':'NORMAL_DRAFT_GET_OBSERVED_V1'if receipt_proves_match else'NORMAL_GET_MATCHED_JOURNAL_V1',
                'projection_sha256':digest(intent['projection']),'projection':intent['projection'],'members':members,
                'content_members':content_members,
                'get_policy':'STRICT_JOURNAL_MATCHED'if strict else 'NORMAL_GET_PLATFORM_REPRESENTATION_V1',
                'latest_strict_state':row['readback'],'normal_get_receipt_sha256':normal_sha,
                'normal_get_response_sha256':None if normal is None else normal['response_sha256'],
                'raw_response_retained':False,'platform_current_version_proven':False}
            checked_guard(self.guard);w.policy.check()
            return value

    def read(self,group):
        checked=self._read(group)
        def revalidate():
            require(self._read(group)==checked,'SLOT_DRAFT_PROOF_CHANGED')
        def validate_snapshot(snapshot):
            from .draft_group_wire import GroupSnapshot,baseline_projection
            from .own_platform_representation import compare_platform_representation,_HTML
            require(type(snapshot)is GroupSnapshot and snapshot.reference==checked['reference'],
                    'SLOT_REMOTE_SNAPSHOT_UNBOUND')
            expected=checked['projection'];rows=snapshot.rows()
            require(len(rows)==len(expected['articles']),'SLOT_REMOTE_SNAPSHOT_CHANGED')
            actual={'articles':[]};urls=[]
            for wanted,seen in zip(expected['articles'],rows):
                actual['articles'].append({key:seen.get(key,'news')if key=='article_type'else seen[key]
                    for key in wanted if key in seen or key=='article_type'})
                urls.append([dict(attrs)['src']for _,attrs in _HTML(wanted['content']).images])
            observed=compare_platform_representation(expected,actual,urls)
            require(observed['state']=='PLATFORM_REPRESENTATION_MATCHED'
                and observed['platform_representation_match']is True,'SLOT_REMOTE_SNAPSHOT_CHANGED')
            return {'reference':snapshot.reference,
                    'projection':baseline_projection(snapshot,synthetic=self.profile.source_kind=='SYNTHETIC_SETUP')}
        return SavedDraftProof(canonical(checked),revalidate,validate_snapshot,_SEAL)
