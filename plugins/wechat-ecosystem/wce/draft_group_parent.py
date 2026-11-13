"""Closed parent/adoption facts; current authority requires the fixed real issuer.

No profile, digest, constructor or historical prefix is a permission. Historical
readers consume the original low-level replay/file primitives, never OwnStore,
GroupStore._load or current qualification recursively.
"""
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass,field
from hashlib import sha256
import json,math,threading,weakref
from .contracts import WCEError
from .draft_group_contracts import canonical,digest,budget_for,Article
from .draft_group_input_files import _plain,_closed,_hash,_id,_int,_enum,_evidence
from .draft_group_read_family_values import ROUTES
from .draft_group_read_family_store import FIRST,ROUTE
from .own_validation_scope import OwnedConnection,_transaction_marker

ADOPTION='GROUP_INPUT_ADOPTION_V1'
PARENT='GROUP_QUALIFIED_PARENT_GRANT_V1'
SELECTION='GROUP_EXACT_HUMAN_SELECTION_V1'
PROFILES=(ADOPTION,PARENT,SELECTION)
KINDS={ADOPTION:'ADOPTION',PARENT:'PARENT',SELECTION:'SELECTION'}
ADOPTION_KEYS=('schema','profile','authority','binding_sha','family_id','registration_sha','registration_proof_sha',
 'source_material_sha','semantic_scope_sha','capsule_sha','preview_sha','settings_sha','route','first_purpose_key',
 'creation_entry_epoch','coverage_grant_id','coverage_proof_sha','coverage_receipts_sha','oldest_observed_at_ms',
 'latest_observed_at_ms','adopted_at_ms','original_source_rights_expiry','original_input_not_after_ms',
 'adoption_kind','selection_receipt_sha','snapshot_preview_sha')
PARENT_KEYS=('schema','profile','authority','binding_sha','family_id','batch_id','request_key','registration_sha',
 'registration_proof_sha','source_material_sha','semantic_scope_sha','source_scope_sha','adoption_sha','preview_sha',
 'settings_sha','route','first_purpose_key','children','read_covenant_sha','created_at_ms',
 'original_source_rights_expiry','original_input_not_after_ms','not_after_ms','selection_receipt_sha','snapshot_preview_sha')
SELECTION_KEYS=('schema','profile','authority','selection_id','binding_sha','family_id','snapshot_preview_sha',
 'source_scope_sha','settings_sha','budget_sha','decision','affected_children','submitted_at_ms','nonce_not_after_ms','trusted_origin')
_MEMBERS=('target_position',*Article.__slots__,'source_old_index')
_OLD=('old_index','ref_sha','group_id','generation','row_version','main_article_id','members_sha',
 'member_count','delete_cap','qualification','required_retirement_profile')
_SCOPE=ContextVar('actual_fixed_parent_append_scope',default=None)
_SCOPES={};_EXECUTIONS=weakref.WeakKeyDictionary();_PLAN_PENDING=weakref.WeakKeyDictionary()


def hold(code='GROUP_PARENT_HOLD'):raise WCEError(code)
def need(value,code='GROUP_PARENT_HOLD'):
 if value is not True:hold(code)
def _copy(value):_plain(value);return json.loads(canonical(value))
def _sha_or_null(value):
 if value is not None:_hash(value)
def _ms(value):return _int(value,1,2**63-1)
def _rights(value):
 _closed(value,('kind','not_after'));_enum(value['kind'],('EXPLICIT_UNTIL','PERSISTENT_DELEGATION'))
 if value['kind']=='EXPLICIT_UNTIL':_ms(value['not_after'])
 elif value['not_after'] is not None:hold('GROUP_PARENT_RIGHTS_UNIT')
 return value

def original_input_expiry_ms(seconds):
 if type(seconds) not in (int,float) or seconds<=0 or seconds>=(2**63)/1000 or not math.isfinite(seconds):hold('GROUP_PARENT_INPUT_EXPIRY')
 value=math.floor(seconds*1000)
 return _ms(value)

def original_not_after_ms(original_input_not_after_ms,rights):
 _ms(original_input_not_after_ms);_rights(rights)
 return min(original_input_not_after_ms,rights['not_after']) if rights['kind']=='EXPLICIT_UNTIL' else original_input_not_after_ms

def _finite_original(c,at_key):
 _rights(c['original_source_rights_expiry']);_ms(c['original_input_not_after_ms']);_ms(c[at_key])
 need(c[at_key]<original_not_after_ms(c['original_input_not_after_ms'],c['original_source_rights_expiry']),
      'GROUP_PARENT_ORIGINAL_EXPIRED')

def _header(c,keys,profile):
 _plain(c);_closed(c,keys)
 need(type(c['schema'])is int and c['schema']==1 and c['profile']==profile and c['authority']is False,'GROUP_PARENT_PROFILE')

def _parent_child(c):
 _closed(c,('operation_id','target_manifest_sha','target_projection_sha','old_reference_shas','budget'));_id(c['operation_id'])
 _hash(c['target_manifest_sha']);_hash(c['target_projection_sha'])
 need(type(c['old_reference_shas'])is list and len(c['old_reference_shas'])<=8)
 for ref in c['old_reference_shas']:_hash(ref)
 need(len(set(c['old_reference_shas']))==len(c['old_reference_shas']))
 need(canonical(c['budget'])==canonical(budget_for(len(c['old_reference_shas']))),'GROUP_PARENT_BUDGET')

def _selection_child(c):
 _closed(c,('operation_id','members','target_manifest_sha','target_projection_sha','old_ref_set','settings_loss_choices'))
 _id(c['operation_id']);_hash(c['target_manifest_sha']);_hash(c['target_projection_sha'])
 need(type(c['members'])is list and 1<=len(c['members'])<=8)
 for position,m in enumerate(c['members']):
  _closed(m,_MEMBERS);_int(m['target_position'],position,position)
  Article(**{k:m[k]for k in Article.__slots__})
  if m['source_old_index']is not None:_int(m['source_old_index'],0,7)
 need(type(c['old_ref_set'])is list and len(c['old_ref_set'])<=8)
 for index,old in enumerate(c['old_ref_set']):
  _closed(old,_OLD);_int(old['old_index'],index,index)
  for k in ('ref_sha','members_sha'):_hash(old[k])
  for k in ('group_id','main_article_id'):_id(old[k])
  for k in ('generation','row_version','member_count'):_int(old[k],1)
  _int(old['delete_cap'],1,1);_enum(old['qualification'],('UNVERIFIED_BY_PURE_COMPONENT',))
  _enum(old['required_retirement_profile'],('DELETE_ACK_AND_INVALIDATED_REFERENCE',))
 # There is no adopted concrete settings-loss choice schema/real UI producer.
 # An arbitrary dictionary must not silently become an accepted choice.
 need(type(c['settings_loss_choices'])is list and not c['settings_loss_choices'],
      'GROUP_PARENT_SETTINGS_LOSS_SCHEMA_REQUIRED')

def validate_adoption(c):
 _header(c,ADOPTION_KEYS,ADOPTION)
 for k in ('binding_sha','family_id','registration_sha','registration_proof_sha','source_material_sha','semantic_scope_sha',
           'capsule_sha','preview_sha','settings_sha','first_purpose_key','creation_entry_epoch','coverage_grant_id',
           'coverage_proof_sha','coverage_receipts_sha'):_hash(c[k])
 _enum(c['route'],ROUTES);_enum(c['adoption_kind'],('AUTO_NEW_ONLY','EXACT_HUMAN_SELECTION'))
 for k in ('oldest_observed_at_ms','latest_observed_at_ms','adopted_at_ms'):_ms(c[k])
 need(c['oldest_observed_at_ms']<=c['latest_observed_at_ms']<=c['adopted_at_ms']<=c['oldest_observed_at_ms']+60000,
      'GROUP_PARENT_COVERAGE_EXPIRED')
 _finite_original(c,'adopted_at_ms')
 if c['adoption_kind']=='AUTO_NEW_ONLY':
  need(c['route']==ROUTES[0] and c['selection_receipt_sha']is None and c['snapshot_preview_sha']is None,'GROUP_PARENT_SELECTION_VARIANT')
 else:
  need(c['route']==ROUTES[1],'GROUP_PARENT_SELECTION_VARIANT');_hash(c['selection_receipt_sha']);_hash(c['snapshot_preview_sha'])
 return c

def validate_parent(c):
 _header(c,PARENT_KEYS,PARENT)
 for k in ('binding_sha','family_id','registration_sha','registration_proof_sha','source_material_sha','semantic_scope_sha',
           'source_scope_sha','adoption_sha','preview_sha','settings_sha','first_purpose_key','read_covenant_sha'):_hash(c[k])
 _id(c['batch_id']);_id(c['request_key']);_enum(c['route'],ROUTES)
 need(type(c['children'])is list and 1<=len(c['children'])<=64)
 for child in c['children']:_parent_child(child)
 need(len({x['operation_id']for x in c['children']})==len(c['children']))
 refs=[r for child in c['children']for r in child['old_reference_shas']]
 need(len(set(refs))==len(refs),'GROUP_PARENT_DUPLICATE_REF')
 _finite_original(c,'created_at_ms');_ms(c['not_after_ms'])
 need(c['not_after_ms']==original_not_after_ms(c['original_input_not_after_ms'],c['original_source_rights_expiry']),
      'GROUP_PARENT_EXPIRY_CHANGED')
 if c['route']==ROUTES[0]:
  need(not refs and all(x['budget']['delete_cap']==0 for x in c['children']) and c['selection_receipt_sha']is None
       and c['snapshot_preview_sha']is None,'GROUP_PARENT_NEW_ONLY')
 else:
  need(bool(refs),'GROUP_PARENT_REPLACEMENT_REQUIRED');_hash(c['selection_receipt_sha']);_hash(c['snapshot_preview_sha'])
 return c

def validate_selection(c):
 _header(c,SELECTION_KEYS,SELECTION);_id(c['selection_id'])
 for k in ('binding_sha','family_id','snapshot_preview_sha','source_scope_sha','settings_sha','budget_sha'):_hash(c[k])
 _enum(c['decision'],('APPROVE_EXACT_REPLACEMENT','CANCEL'))
 _ms(c['submitted_at_ms']);_ms(c['nonce_not_after_ms'])
 need(c['submitted_at_ms']<c['nonce_not_after_ms'],'GROUP_PARENT_SELECTION_LATE')
 need(type(c['affected_children'])is list and 1<=len(c['affected_children'])<=64)
 for child in c['affected_children']:_selection_child(child)
 need(len({x['operation_id']for x in c['affected_children']})==len(c['affected_children']))
 refs=[o['ref_sha']for child in c['affected_children']for o in child['old_ref_set']]
 need(bool(refs)and len(set(refs))==len(refs),'GROUP_PARENT_REPLACEMENT_REQUIRED')
 origin=c['trusted_origin'];_closed(origin,('implementation_profile','server_boot_id','session_id','nonce_sha256','review_scope_sha256'))
 _enum(origin['implementation_profile'],('GROUP_TRUSTED_SETTINGS_SELECTION_V1',))
 _id(origin['server_boot_id']);_id(origin['session_id']);_hash(origin['nonce_sha256']);_hash(origin['review_scope_sha256'])
 return c

def is_parent_profile(profile):
 return type(profile)is str and profile.startswith(('GROUP_INPUT_ADOPTION','GROUP_QUALIFIED_PARENT_GRANT','GROUP_EXACT_HUMAN_SELECTION'))

def validate_candidate(c):
 need(type(c)is dict and type(c.get('profile'))is str,'GROUP_PARENT_PROFILE')
 fn={ADOPTION:validate_adoption,PARENT:validate_parent,SELECTION:validate_selection}.get(c['profile'])
 if fn is None:hold('GROUP_PARENT_PROFILE')
 return fn(c)

def encode_candidate(c):validate_candidate(c);return canonical(c).encode('utf-8')
def candidate_sha(c):return sha256(encode_candidate(c)).hexdigest()

def wrapper_for(candidate,source_kind):
 c=validate_candidate(candidate);_enum(source_kind,('OPERATOR_ATTESTED','SYNTHETIC_SETUP'));sha=candidate_sha(c)
 prefix={ADOPTION:'group-adoption-',PARENT:'group-parent-',SELECTION:'group-selection-'}[c['profile']]
 return {'binding_sha':c['binding_sha'],'source_kind':source_kind,'preview_id':prefix+sha,
  'input_sha':c['capsule_sha']if c['profile']==ADOPTION else c['source_scope_sha'],
  'request_key':prefix+sha,'scope_sha':c['source_scope_sha']if c['profile']==SELECTION else c['semantic_scope_sha'],
  'candidate':_copy(c),'evidence_sha':sha}

def expected_settings_descriptor(children):
 _plain(children);need(type(children)is list and 1<=len(children)<=64)
 for child in children:
  _closed(child,('operation_id','article_metadata'));_id(child['operation_id'])
  need(type(child['article_metadata'])is dict)
 need(len({x['operation_id']for x in children})==len(children))
 raw=(canonical({'profile':'GROUP_PARENT_EXPECTED_SETTINGS_V1','children':children})+'\n').encode()
 return {'kind':'METADATA','sha256':sha256(raw).hexdigest(),'size':len(raw)}

def parent_budget_descriptor(children):
 _plain(children);need(type(children)is list and 1<=len(children)<=64)
 for child in children:
  _closed(child,('operation_id','budget'));_id(child['operation_id']);budget=child['budget']
  need(type(budget)is dict and type(budget.get('delete_cap'))is int)
  need(canonical(budget)==canonical(budget_for(budget['delete_cap'])),'GROUP_PARENT_BUDGET')
 need(len({x['operation_id']for x in children})==len(children))
 raw=(canonical({'profile':'GROUP_PARENT_BUDGET_V1','children':children})+'\n').encode()
 return {'kind':'BUDGET','sha256':sha256(raw).hexdigest(),'size':len(raw)}


def replay_parent_records(events,states):
 """Pure original-event linkage; detached output grants no live permission."""
 need(type(events)is list and type(states)is dict)
 need(all(type(k)is str and type(v)is tuple and len(v)==3 and type(v[0])is dict for k,v in states.items()))
 for state,seq,head in states.values():
  _enum(state['source_kind'],('SYNTHETIC_SETUP','OPERATOR_ATTESTED'));_int(seq,1);_hash(head)
 result={'adoptions':{},'parents':{},'selections':{},'executions':{}}
 by_capsule={};selection_ids=set();batches=set();plans=[]
 for event in events:
  _plain(event);_closed(event,('account_key','seq','kind','payload','event_sha'));_hash(event['account_key']);_int(event['seq'],1);_hash(event['event_sha'])
  payload=event['payload'];need(type(payload)is dict)
  if event['kind']=='PLAN':plans.append(event);continue
  c=payload.get('candidate')if event['kind']=='PREVIEW'else None
  if type(c)is not dict or not is_parent_profile(c.get('profile')):continue
  validate_candidate(c);account=event['account_key'];need(c['binding_sha']==account)
  need(account in states and type(states[account])is tuple and len(states[account])==3)
  source_kind=states[account][0]['source_kind']
  need(canonical(payload)==canonical(wrapper_for(c,source_kind)),'GROUP_PARENT_WRAPPER_CHANGED')
  key=candidate_sha(c);domain={ADOPTION:'adoptions',PARENT:'parents',SELECTION:'selections'}[c['profile']]
  need(key not in result[domain],'GROUP_PARENT_DUPLICATE')
  item={'candidate':_copy(c),'event':_copy(event)};result[domain][key]=item
  if c['profile']==ADOPTION:
   ck=(account,c['family_id'],c['capsule_sha']);need(ck not in by_capsule,'GROUP_PARENT_ADOPTION_REPLACED');by_capsule[ck]=key
  elif c['profile']==PARENT:
   bk=(account,c['batch_id']);need(bk not in batches,'GROUP_PARENT_DUPLICATE_BATCH');batches.add(bk)
  else:
   sk=(account,c['selection_id']);need(sk not in selection_ids,'GROUP_PARENT_DUPLICATE_SELECTION');selection_ids.add(sk)
 for sha,item in result['parents'].items():
  p=item['candidate'];ad=result['adoptions'].get(p['adoption_sha']);need(ad is not None,'GROUP_PARENT_ADOPTION_REQUIRED')
  a=ad['candidate'];need(ad['event']['account_key']==p['binding_sha'] and ad['event']['seq']<item['event']['seq'],'GROUP_PARENT_ORDER')
  shared=('binding_sha','family_id','registration_sha','registration_proof_sha','source_material_sha','semantic_scope_sha',
          'preview_sha','settings_sha','route','first_purpose_key','original_source_rights_expiry','original_input_not_after_ms',
          'selection_receipt_sha','snapshot_preview_sha')
  need(all(canonical(a[k])==canonical(p[k])for k in shared)and a['capsule_sha']==p['source_scope_sha']
       and a['adopted_at_ms']<=p['created_at_ms'],'GROUP_PARENT_ADOPTION_CHANGED')
  if p['selection_receipt_sha']is not None:
   selection=result['selections'].get(p['selection_receipt_sha']);need(selection is not None,'GROUP_PARENT_SELECTION_REQUIRED')
   s=selection['candidate']
   need(selection['event']['account_key']==p['binding_sha'] and selection['event']['seq']<ad['event']['seq']
        and s['decision']=='APPROVE_EXACT_REPLACEMENT' and s['snapshot_preview_sha']==p['snapshot_preview_sha']
        and s['binding_sha']==p['binding_sha'] and s['family_id']==p['family_id'],'GROUP_PARENT_SELECTION_CHANGED')
 for event in plans:
  payload=event['payload'];execution=payload.get('execution');candidate=payload.get('candidate')
  if type(execution)is not dict or execution.get('parent_grant_sha')not in result['parents']:continue
  item=result['parents'][execution['parent_grant_sha']];p=item['candidate'];need(event['account_key']==p['binding_sha'])
  _closed(execution,('parent_grant_sha','preview_sha','settings_sha','source_scope_sha','child_pins'))
  need(item['event']['seq']<event['seq'] and type(candidate)is dict and candidate['batch_id']==p['batch_id']
       and candidate['request_key']==p['request_key'] and candidate['candidate_sha']==p['preview_sha']
       and execution['preview_sha']==p['preview_sha'] and execution['settings_sha']==p['settings_sha']
       and execution['source_scope_sha']==p['source_scope_sha'],'GROUP_PARENT_PLAN_CHANGED')
  need(type(execution['child_pins'])is list and len(execution['child_pins'])==len(p['children'])==len(candidate['children']),
       'GROUP_PARENT_PLAN_CHILDREN_CHANGED')
  adoption=result['adoptions'][p['adoption_sha']]
  for parent_child,child,pins in zip(p['children'],candidate['children'],execution['child_pins']):
   _closed(pins,('operation_id','target_projection_sha','old_projection_shas'))
   need(parent_child['operation_id']==child['operation_id']==pins['operation_id']
        and parent_child['target_projection_sha']==pins['target_projection_sha']
        and parent_child['old_reference_shas']==[o['ref_sha']for o in child['old_ref_set']]
        and canonical(parent_child['budget'])==canonical(child['budget']),'GROUP_PARENT_PLAN_CHILD_CHANGED')
   need(type(pins['old_projection_shas'])is list and len(pins['old_projection_shas'])==len(child['old_ref_set']))
   for old in pins['old_projection_shas']:_hash(old)
   if p['route']==ROUTES[0]:need(child['route']=='CREATE_NEW' and not child['old_ref_set'],'GROUP_PARENT_NEW_ONLY')
   op=child['operation_id'];need(op not in result['executions'],'GROUP_PARENT_DUPLICATE_OPERATION')
   selection=result['selections'].get(p['selection_receipt_sha'])
   result['executions'][op]={'parent':p,'parent_event':item['event'],'adoption':adoption['candidate'],
      'adoption_event':adoption['event'],'selection':None if selection is None else selection['candidate'],
      'selection_event':None if selection is None else selection['event'],'plan_event':event,'child':child}
 return _copy(result)


def _snapshot(db,states=None):
 from .draft_group_response_history import read_group_replay_snapshot_in
 actual,events=read_group_replay_snapshot_in(db)
 try:
  if states is not None:need(canonical(states)==canonical(actual),'GROUP_PARENT_REPLAY_CHANGED')
  return actual,events
 except BaseException:
  from .draft_group_response_history import release_group_replay_snapshot_in
  release_group_replay_snapshot_in(db,actual,events);raise


def _policy(db,policy):
 from .draft_group_history_context import current_history_policy
 from .own_connection_policy import ConnectionPolicy
 need(type(db)is OwnedConnection and _transaction_marker(db)is not None and type(policy)is ConnectionPolicy
      and current_history_policy(db)is policy,'GROUP_PARENT_HISTORY_POLICY_REQUIRED')
 return policy


def _descriptor(kind,value):
 raw=(canonical(value)+'\n').encode();return {'kind':kind,'sha256':sha256(raw).hexdigest(),'size':len(raw)}


def _files_for_parent(db,states,item,policy,files):
 """Original C/H/D/registration/FIRST links, no current or full replay call."""
 from .draft_group_read_family_store import _history_file_guard
 from .draft_group_host_history import read_original_covenant_in
 from .draft_group_target_scope import target_article_metadata
 from .own_group_json import read
 p=item['candidate'];state=states[p['binding_sha']][0]
 capsule=files.read('execution',p['source_scope_sha'],expected_sha=p['source_scope_sha']);c=capsule.value
 registration=files.read('registration',p['registration_sha'],expected_sha=p['registration_sha'])
 proof=files.read('proof',p['registration_proof_sha'],expected_sha=p['registration_proof_sha'])
 source=files.read('source',p['source_material_sha'],expected_sha=p['source_material_sha'])
 need(c['family_id']==p['family_id'] and c['registration_sha']==registration.sha256
      and c['source_material_sha']==source.sha256 and c['preview_core_sha']==p['preview_sha']
      and digest(c['binding'])==p['binding_sha'] and registration.value['family_id']==p['family_id']
      and registration.value['binding']==c['binding'] and registration.value['source_material_sha']==source.sha256
      and proof.value['registration_sha']==registration.sha256 and proof.value['source_material_sha']==source.sha256
      and proof.value['qualified_binding']==c['binding'] and source.value['semantic_scope_sha']==p['semantic_scope_sha'],
      'GROUP_PARENT_INPUT_CHANGED')
 need(original_input_expiry_ms(source.value['expires_policy']['not_after'])==p['original_input_not_after_ms'],
      'GROUP_PARENT_INPUT_EXPIRY_CHANGED')
 roots=[x['candidate']for s,_,_ in states.values()for x in s['previews'].values()
        if type(x.get('candidate'))is dict and x['candidate'].get('profile')==FIRST
        and x['candidate'].get('family_anchor_id')==p['family_id']]
 need(len(roots)==1 and roots[0]['covenant_sha']==p['read_covenant_sha'],'GROUP_PARENT_FIRST_REQUIRED')
 covenant=read_original_covenant_in(db,policy,p['read_covenant_sha']).value
 need(covenant['family_anchor_id']==p['family_id'] and covenant['original_scope_sha']==p['semantic_scope_sha']
      and canonical(covenant['source_rights_expiry'])==canonical(p['original_source_rights_expiry'])
      and p['route']in covenant['allowed_routes'],'GROUP_PARENT_FIRST_CHANGED')
 need(len(c['children'])==len(p['children']),'GROUP_PARENT_CHILDREN_CHANGED')
 settings=[];budgets=[];children=[]
 for spec,expected in zip(c['children'],p['children']):
  child=files.read('child',spec['sha256'],expected_sha=spec['sha256']);h=child.value
  need(spec=={'kind':'CHILD','sha256':child.sha256,'size':len(child.raw)} and h['operation_id']==expected['operation_id']
       and h['manifest_sha']==expected['target_manifest_sha'] and h['projection_sha']==expected['target_projection_sha']
       and h['binding']==c['binding'],'GROUP_PARENT_CHILD_CHANGED')
  manifest=read(h['manifest_json'],h['manifest_sha']);metadata=target_article_metadata(manifest,h)
  target=state['previews'].get('group-target-'+h['manifest_sha']);need(target is not None,'GROUP_PARENT_TARGET_REQUIRED')
  d=target['candidate']
  need(d['profile']=='GROUP_TARGET_DESIGNATION_V1' and d['binding_sha']==p['binding_sha']
       and d['operation_id']==h['operation_id'] and d['manifest_sha']==h['manifest_sha']
       and d['capsule_sha']==capsule.sha256 and d['child_sha']==child.sha256
       and d['registration_sha']==p['registration_sha'] and d['registration_proof_sha']==p['registration_proof_sha'],
       'GROUP_PARENT_TARGET_CHANGED')
  reservation=files.read('reservation',h['manifest_sha'],expected_sha=d['reservation_sha']).value
  need(reservation['operation_id']==h['operation_id'] and reservation['capsule_sha']==capsule.sha256
       and reservation['registration_sha']==registration.sha256 and reservation['proof_sha']==proof.sha256
       and reservation['selector']==h['selector'],'GROUP_PARENT_RESERVATION_CHANGED')
  upload=files.read('upload_reuse',d['upload_map_sha'],expected_sha=d['upload_map_sha'])
  need(upload.value['operation_id']==h['operation_id'],'GROUP_PARENT_UPLOAD_MAP_CHANGED')
  row=db.execute('SELECT manifest,digest FROM own_articles WHERE version=?',(h['selector']['version'],)).fetchone()
  need(row is not None and row['manifest']==h['manifest_json'] and row['digest']==h['manifest_sha'],
       'GROUP_PARENT_TARGET_ROW_REQUIRED')
  need(h['execution_budget']==_descriptor('BUDGET',expected['budget']),'GROUP_PARENT_CHILD_BUDGET_CHANGED')
  settings.append({'operation_id':h['operation_id'],'article_metadata':metadata})
  budgets.append({'operation_id':h['operation_id'],'budget':expected['budget']});children.append(h)
 need(c['expected_metadata']==expected_settings_descriptor(settings) and c['expected_metadata']['sha256']==p['settings_sha']
      and c['execution_budget']==parent_budget_descriptor(budgets),'GROUP_PARENT_AGGREGATE_CHANGED')
 if p['route']==ROUTES[0]:need(c['route_profile']=='CREATE_NEW' and all(not h['old_reference_shas']for h in p['children']),
                             'GROUP_PARENT_NEW_ONLY')
 return files,covenant,c,children


def _coverage_source_material_in(db,policy,fact,adoption,states,events):
 """Facts-only origin bridge; never a live binding or renewed Parent right."""
 if fact['source_material_sha']==adoption['source_material_sha']:
  return
 need(type(fact['schema'])is int and fact['schema']==2,
      'GROUP_PARENT_COVERAGE_SOURCE_CHANGED')
 from .draft_group_source_facts import PROFILE_V2
 from .draft_group_source_review import validate_source_review_binding_for_fact_from_replay_in
 need(fact['profile']==PROFILE_V2 and type(fact['current_source_review_sha'])is str,
      'GROUP_PARENT_COVERAGE_SOURCE_CHANGED')
 review=validate_source_review_binding_for_fact_from_replay_in(db,policy,fact,states,events)
 need(type(review)is dict and review['profile']=='GROUP_CURRENT_SOURCE_REVIEW_V2'
      and review['original_source_material_sha']==adoption['source_material_sha']
      and review['current_source_material_sha']==fact['source_material_sha']
      and review['family_id']==adoption['family_id']
      and review['registration_sha']==adoption['registration_sha']
      and review['semantic_scope_sha']==adoption['semantic_scope_sha'],
      'GROUP_PARENT_COVERAGE_SOURCE_CHANGED')


def _coverage_history(db,states,events,policy,adoption,covenant,kept_files):
 from .draft_group_response_history import read_group_receipt_from_replay_in
 from .draft_group_discovery import ListPage,compare_passes
 from .draft_group_wire import GroupSnapshot,reference_sha,baseline_projection
 from .draft_group_read_family_store import _gid
 a=adoption;state=states[a['binding_sha']][0];purposes=[p for p in covenant['purposes']if p['source_grant_sha']==a['first_purpose_key']]
 need(len(purposes)==1,'GROUP_PARENT_PURPOSE_REQUIRED');purpose=purposes[0]
 wanted='PREVIEW_ACCOUNT'if a['route']==ROUTES[0]else'EXECUTION_INITIAL_ACCOUNT'
 need(purpose['purpose']==wanted and a['coverage_grant_id']==_gid(a['binding_sha'],purpose),
      'GROUP_PARENT_PURPOSE_CHANGED')
 grant=state['preview_grants'].get(a['coverage_grant_id'])
 need(grant is not None and grant['registration']['source_grant_sha']==a['first_purpose_key']
      and grant['registration']['phase']=='DISCOVER' and not grant['hold'],'GROUP_PARENT_COVERAGE_REQUIRED')
 claims=grant['claims'];lists=[c for c in claims if c['api']=='LIST'];gets=[c for c in claims if c['api']=='GET']
 need(len(claims)==len(lists)+len(gets)and 2<=len(lists)<=20,'GROUP_PARENT_COVERAGE_REQUIRED')
 synthetic=state['source_kind']=='SYNTHETIC_SETUP';pages=[];receipts=[];times=[];page_count=None
 from .draft_group_source_facts import replay_source_facts,_locator_in
 from .draft_group_host_history import validate_source_fact_history_from_replay_in
 source_facts=replay_source_facts(events)
 def receipt(claim,*,reference=None,offset=None):
  need(claim['state']=='OBSERVED'and claim['outcome']=='OBSERVED'and type(claim['proof_sha'])is str,
       'GROUP_PARENT_COVERAGE_REQUIRED')
  r=read_group_receipt_from_replay_in(db,states,events,policy,claim['id'],reference=reference,list_offset=offset)
  need(r.snapshot is not None and r.primary.sha256==claim['proof_sha'],'GROUP_PARENT_COVERAGE_REQUIRED')
  v=r.primary.value;obs=v['observation']
  need(obs['outcome']=='OBSERVED'and obs['timing']=='COMPLETED_MS'and type(obs['observed_at_ms'])is int
       and claim['at_ms']<=obs['observed_at_ms']<=a['adopted_at_ms']
       and v['archive_context']['source_epoch']==a['creation_entry_epoch'],'GROUP_PARENT_COVERAGE_EPOCH_CHANGED')
  source_locator=json.loads(r.source_locator_json);fact=_locator_in(source_facts,source_locator)['candidate']
  validate_source_fact_history_from_replay_in(db,fact,policy,states,events)
  _coverage_source_material_in(db,policy,fact,a,states,events)
  need(fact['binding_sha']==a['binding_sha']and fact['family_id']==a['family_id']
       and fact['registration_sha']==a['registration_sha']and fact['registration_proof_sha']==a['registration_proof_sha']
       and fact['original_scope_sha']==a['semantic_scope_sha']
       and fact['purpose_key']==a['first_purpose_key']and a['adopted_at_ms']<=fact['qualified_not_after_ms'],
       'GROUP_PARENT_COVERAGE_SOURCE_CHANGED')
  kept_files.append(r.files);receipts.append([claim['id'],r.primary.sha256,r.snapshot.sha256]);times.append(obs['observed_at_ms'])
  return r
 for index,claim in enumerate(lists):
  need(claim['ordinal']==index+1,'GROUP_PARENT_COVERAGE_ORDER')
  offset=0 if page_count is None else(index%page_count)*20;r=receipt(claim,offset=offset);value=json.loads(r.snapshot.raw)
  total=value.get('total_count');need(type(total)is int and 0<=total<=200,'GROUP_PARENT_COVERAGE_BOUND')
  if page_count is None:page_count=max(1,(total+19)//20)
  page=ListPage(offset,canonical(value),r.primary.value['transport']['response_body_sha']);page.value(synthetic=synthetic);pages.append(page)
 need(len(pages)==2*page_count,'GROUP_PARENT_COVERAGE_INCOMPLETE')
 compared=compare_passes(tuple(pages[:page_count]),tuple(pages[page_count:]),synthetic=synthetic)
 refs=compared['references'];subjects=compared['subject_shas']
 need(grant['subjects']==list(subjects)and len(gets)==len(refs),'GROUP_PARENT_COVERAGE_INCOMPLETE')
 for index,(claim,ref,subject)in enumerate(zip(gets,refs,subjects)):
  need(claim['ordinal']==index+1 and claim['subject_sha']==subject==reference_sha(ref,synthetic=synthetic),
       'GROUP_PARENT_COVERAGE_ORDER')
  r=receipt(claim,reference=ref);snapshot=GroupSnapshot(ref,canonical(json.loads(r.snapshot.raw)),r.primary.value['transport']['response_body_sha'])
  need(digest(baseline_projection(snapshot,synthetic=synthetic))==r.primary.value['observation']['projection_sha'],
       'GROUP_PARENT_COVERAGE_PROJECTION_CHANGED')
 proof={'profile':'GROUP_CURRENT_ACCOUNT_COVERAGE_V1','binding_sha':a['binding_sha'],'family_id':a['family_id'],
  'purpose_key':a['first_purpose_key'],'grant_id':a['coverage_grant_id'],'grant_sha':digest(grant),'items_sha':compared['items_sha'],
  'subjects':list(subjects),'receipts':receipts,'observed_at_ms':min(times),'latest_observed_at_ms':max(times)}
 need(digest(proof)==a['coverage_proof_sha'] and digest(receipts)==a['coverage_receipts_sha']
      and min(times)==a['oldest_observed_at_ms'] and max(times)==a['latest_observed_at_ms'],
      'GROUP_PARENT_COVERAGE_CHANGED')
 return proof


def _adoption_files(db,states,events,policy,a,files):
 """An adoption-only prefix is verified historical data, never executable."""
 if a['route']!=ROUTES[0]:hold('GROUP_PARENT_REPLACEMENT_READER_REQUIRED')
 capsule=files.read('execution',a['capsule_sha'],expected_sha=a['capsule_sha']).value
 roots=[v['candidate']for s,_,_ in states.values()for v in s['previews'].values()
        if type(v.get('candidate'))is dict and v['candidate'].get('profile')==FIRST
        and v['candidate'].get('family_anchor_id')==a['family_id']]
 need(len(roots)==1,'GROUP_PARENT_FIRST_REQUIRED')
 children=[]
 for spec in capsule['children']:
  h=files.read('child',spec['sha256'],expected_sha=spec['sha256']).value
  children.append({'operation_id':h['operation_id'],'target_manifest_sha':h['manifest_sha'],
                   'target_projection_sha':h['projection_sha'],'old_reference_shas':[],'budget':budget_for(0)})
 # These are parameters for a shared fact checker only, never an issued Parent
 # or an event candidate. The persisted prefix remains adoption-only/inactive.
 fields=dict(a,source_scope_sha=a['capsule_sha'],read_covenant_sha=roots[0]['covenant_sha'],children=children)
 return _files_for_parent(db,states,{'candidate':fields},policy,files)



def _adoption_route(events,item,covenant,capsule):
 a=item['candidate']
 routes=[e for e in events if e['account_key']==a['binding_sha']and e['kind']=='PREVIEW'
         and type(e['payload'].get('candidate'))is dict and e['payload']['candidate'].get('profile')==ROUTE
         and e['payload']['candidate'].get('family_anchor_id')==a['family_id']]
 need(len(routes)==1 and routes[0]['seq']<item['event']['seq']and routes[0]['payload']['candidate']['route']==a['route'],
      'GROUP_PARENT_FIRST_ROUTE_REQUIRED')
 need(a['coverage_grant_id']in capsule['read_delegation_ids'],'GROUP_PARENT_CAPSULE_PURPOSE_CHANGED')


def _empty_records():return {'adoptions':{},'parents':{},'selections':{},'executions':{}}

def _has_parent_domain(db):
 for row in db.execute("SELECT payload FROM group_events WHERE kind='PREVIEW'"):
  payload=json.loads(row[0]);c=payload.get('candidate')if type(payload)is dict else None
  if type(c)is dict and is_parent_profile(c.get('profile')):return True
 return False


def check_parent_records_in(db,states=None,history_policy=None, *, history_locators=None):
 """Read-only all-pool validation. No high-level replay/current recursion."""
 if not _has_parent_domain(db):return _empty_records()
 try:
  from .draft_group_response_history import release_group_replay_snapshot_in
  from .draft_group_target_files import PinnedTargetFiles
  from .draft_group_target_scope import read_validated_target_designation_in
  from .draft_group_read_family_store import _history_file_guard
 except ImportError:hold('GROUP_PARENT_FIXED_HISTORY_READER_REQUIRED')
 if history_policy is None:
  from .draft_group_history_context import current_history_policy
  history_policy=current_history_policy(db)
 policy=_policy(db,history_policy);actual,events=_snapshot(db,states)
 kept=[];target_facts=[];files=None
 try:
  from .draft_group_read_family_store import check_family_records_in
  check_family_records_in(db,actual,policy)
  info=replay_parent_records(events,actual)
  if info['selections']:
   # Real protected T1/T0 producer and concrete settings-loss reader are not yet
   # installed. The codec can read ACK times without today's nonce clock, but
   # this full historical domain must not be waived by a generic preview/hash.
   hold('GROUP_PARENT_REPLACEMENT_READER_REQUIRED')
  files=PinnedTargetFiles(policy,lambda:_history_file_guard(policy))
  processed=set()
  for item in info['parents'].values():
   p=item['candidate']
   if p['route']!=ROUTES[0]:hold('GROUP_PARENT_REPLACEMENT_READER_REQUIRED')
   _,covenant,c,children=_files_for_parent(db,actual,item,policy,files)
   for h in children:
    d=actual[p['binding_sha']][0]['previews']['group-target-'+h['manifest_sha']]['candidate']
    target_facts.append(read_validated_target_designation_in(db,d,policy, history_locators=history_locators))
   a=info['adoptions'][p['adoption_sha']]['candidate'];_adoption_route(events,info['adoptions'][p['adoption_sha']],covenant,c)
   _coverage_history(db,actual,events,policy,a,covenant,kept)
   processed.add(p['adoption_sha'])
  for sha,item in info['adoptions'].items():
   if sha in processed:continue
   a=item['candidate'];_,covenant,c,children=_adoption_files(db,actual,events,policy,a,files)
   for h in children:
    d=actual[a['binding_sha']][0]['previews']['group-target-'+h['manifest_sha']]['candidate']
    target_facts.append(read_validated_target_designation_in(db,d,policy, history_locators=history_locators))
   _adoption_route(events,item,covenant,c)
   _coverage_history(db,actual,events,policy,a,covenant,kept)
  # For actual PLAN children, bind original ordered members and old projections
  # to the fixed H files. A prefix without PLAN has no executions entry.
  for record in info['executions'].values():
   p=record['parent'];child=record['child'];state=actual[p['binding_sha']][0]
   expected=next(x for x in p['children']if x['operation_id']==child['operation_id'])
   d=state['previews']['group-target-'+expected['target_manifest_sha']]['candidate']
   h=files.read('child',d['child_sha'],expected_sha=d['child_sha']).value
   members=[{k:v for k,v in m.items()if k not in('target_position','source_old_index')}for m in child['members']]
   need(h['members']==members,'GROUP_PARENT_PLAN_MEMBER_CHANGED')
   op=state['operations'].get(child['operation_id']);batch=state['batches'].get(p['batch_id'])
   need(op is not None and batch is not None and op['batch_id']==p['batch_id']
        and canonical(batch['execution'])==canonical(record['plan_event']['payload']['execution']),
        'GROUP_PARENT_PLAN_PROJECTION_CHANGED')
  for facts in target_facts:
   need(facts.authority is False,'GROUP_PARENT_TARGET_HISTORY_FACTS_REQUIRED')
   facts.files.collective_fence()
   for receipt in facts.proof_receipts:receipt.collective_fence()
  for reader in kept:reader.collective_fence()
  files.collective_fence()
  return info
 except ImportError:hold('GROUP_PARENT_FIXED_HISTORY_READER_REQUIRED')
 finally:release_group_replay_snapshot_in(db,actual,events)


def _fixed_append(host,db,kind,payload,*,history_locators=None):
 try:from .draft_group_parent_issuer import validate_parent_append_in
 except ImportError:hold('GROUP_PARENT_FIXED_ISSUER_REQUIRED')
 validate_parent_append_in(host,db,kind,payload,history_locators=history_locators)


def _fixed_current(host,db,operation_id,parent, *, history_locators=None):
 try:from .draft_group_parent_issuer import validate_parent_current_in
 except ImportError:hold('GROUP_PARENT_FIXED_ISSUER_REQUIRED')
 validate_parent_current_in(host,db,operation_id,parent, history_locators=history_locators)


@contextmanager
def _append_scope(host,db,candidate,*,history_locators=None):
 need(type(db)is OwnedConnection and _transaction_marker(db)is not None,'GROUP_PARENT_OWNED_TRANSACTION_REQUIRED')
 _fixed_append(host,db,KINDS[candidate['profile']],candidate,history_locators=history_locators)
 record=(host,db,_transaction_marker(db),threading.get_ident(),canonical(candidate),[])
 _SCOPES[id(record)]=record;token=_SCOPE.set(record)
 try:yield
 finally:_SCOPE.reset(token);_SCOPES.pop(id(record),None)


def before_event_in(db,account,kind,payload, *, history_locators=None):
 if kind=='PLAN':
  need(type(db)is OwnedConnection and _transaction_marker(db)is not None,'GROUP_PARENT_OWNED_TRANSACTION_REQUIRED')
  pending=_PLAN_PENDING.get(db)
  need(pending is not None and pending[1]==_transaction_marker(db)and pending[2]==threading.get_ident()
       and pending[3]is None,'GROUP_PARENT_PLAN_ISSUER_REQUIRED')
  host=pending[0]();need(host is not None,'GROUP_PARENT_PLAN_ISSUER_REQUIRED')
  info=check_parent_records_in(db, history_locators=history_locators);need(payload['execution']['parent_grant_sha']in info['parents'],'GROUP_PARENT_PLAN_REQUIRED')
  _fixed_append(host,db,'PLAN',payload,history_locators=history_locators)
  _PLAN_PENDING[db]=(pending[0],pending[1],pending[2],digest(payload));return
 c=payload.get('candidate')if kind=='PREVIEW'and type(payload)is dict else None
 if type(c)is not dict or not is_parent_profile(c.get('profile')):return
 validate_candidate(c);scope=_SCOPE.get()
 need(scope is not None and _SCOPES.get(id(scope))is scope and scope[1]is db
      and scope[2]==_transaction_marker(db)and scope[3]==threading.get_ident()and scope[4]==canonical(c)
      and not scope[5] and account==c['binding_sha'],'GROUP_PARENT_ADMISSION_REQUIRED')
 # Complete replaceable history/file work before the final fixed issuer fence.
 check_parent_records_in(db, history_locators=history_locators)
 need(canonical(payload)==canonical(wrapper_for(c,payload['source_kind'])),'GROUP_PARENT_WRAPPER_CHANGED')
 _fixed_append(scope[0],db,KINDS[c['profile']],c,history_locators=history_locators)
 scope[5].append((account,candidate_sha(c)))


def after_event_in(db,*,account=None,kind=None,payload=None, history_locators=None):
 if kind=='PLAN':
  need(type(db)is OwnedConnection and _transaction_marker(db)is not None,'GROUP_PARENT_OWNED_TRANSACTION_REQUIRED')
  pending=_PLAN_PENDING.get(db)
  need(pending is not None and pending[1]==_transaction_marker(db)and pending[2]==threading.get_ident()
       and pending[3]==digest(payload),'GROUP_PARENT_PLAN_ISSUER_REQUIRED')
  info=check_parent_records_in(db, history_locators=history_locators)
  need(all(ch['operation_id']in info['executions']for ch in payload['candidate']['children']),'GROUP_PARENT_PLAN_REQUIRED')
  _PLAN_PENDING.pop(db,None);return
 c=payload.get('candidate')if kind=='PREVIEW'and type(payload)is dict else None
 if type(c)is not dict or not is_parent_profile(c.get('profile')):return
 scope=_SCOPE.get();need(scope is not None and _SCOPES.get(id(scope))is scope and scope[1]is db
   and scope[2]==_transaction_marker(db)and scope[3]==threading.get_ident()and len(scope[5])==1
   and scope[5][0]==(account,candidate_sha(c)),'GROUP_PARENT_ADMISSION_REQUIRED')
 info=check_parent_records_in(db, history_locators=history_locators);domain={ADOPTION:'adoptions',PARENT:'parents',SELECTION:'selections'}[c['profile']]
 need(candidate_sha(c)in info[domain],'GROUP_PARENT_APPEND_MISSING')


def _locator(item):
 e=item['event'];c=item['candidate'];return {'account_key':e['account_key'],'event_seq':e['seq'],
  'event_sha':e['event_sha'],'preview_id':wrapper_for(c,e['payload']['source_kind'])['preview_id'],'evidence_sha':candidate_sha(c)}


def _register(host,db,group_store,candidate,profile, *, history_locators=None):
 validate_candidate(candidate);need(candidate['profile']==profile)
 from .draft_group_store import GroupStore
 need(type(group_store)is GroupStore and group_store.binding_sha==candidate['binding_sha'])
 info=check_parent_records_in(db, history_locators=history_locators);domain={ADOPTION:'adoptions',PARENT:'parents',SELECTION:'selections'}[profile]
 old=info[domain].get(candidate_sha(candidate))
 if old is not None:return _copy(_locator(old))  # historical observation only
 source_kind=db.execute('SELECT source_kind FROM own_config WHERE id=1').fetchone()[0]
 wrapper=wrapper_for(candidate,source_kind);kwargs={k:v for k,v in wrapper.items()if k!='binding_sha'}
 with _append_scope(host,db,candidate,history_locators=history_locators):group_store.register_preview_in(db,**kwargs, history_locators=history_locators)
 info=check_parent_records_in(db, history_locators=history_locators);return _copy(_locator(info[domain][candidate_sha(candidate)]))


def register_adoption_in(host,db,group_store,candidate, *, history_locators=None):return _register(host,db,group_store,candidate,ADOPTION, history_locators=history_locators)
def register_parent_in(host,db,group_store,candidate, *, history_locators=None):
 result=_register(host,db,group_store,candidate,PARENT, history_locators=history_locators)
 _PLAN_PENDING[db]=(weakref.ref(host),_transaction_marker(db),threading.get_ident(),None)
 return result
def register_selection_in(host,db,group_store,candidate, *, history_locators=None):return _register(host,db,group_store,candidate,SELECTION, history_locators=history_locators)


class ValidatedParentExecution:
 __slots__=('operation_id','capsule_sha','parent_grant_sha','first_purpose_key','original_not_after_ms','route','_budget_json','__weakref__')
 def __init__(self):hold('GROUP_PARENT_ISSUED_EXECUTION_REQUIRED')
 @property
 def authority(self):return False
 @property
 def budget(self):return json.loads(self._budget_json)
 @property
 def original_child_budget(self):return json.loads(self._budget_json)
 def __repr__(self):return '<ValidatedParentExecution>'


@dataclass(frozen=True,slots=True)
class _ExecutionRecord:
 host:object=field(repr=False)
 entry:object=field(repr=False)
 db:object=field(repr=False)
 epoch:int
 thread:int
 fields_json:str=field(repr=False)
 parent_json:str=field(repr=False)
 binding_sha:str
 head:tuple


def _execution_fields(value):
 return {'operation_id':value.operation_id,'capsule_sha':value.capsule_sha,'parent_grant_sha':value.parent_grant_sha,
  'first_purpose_key':value.first_purpose_key,'original_not_after_ms':value.original_not_after_ms,'route':value.route,
  'budget_json':value._budget_json}


def _actual_host(host,db):
 try:
  from .draft_group_host_review import GroupRuntimeHost
  from .draft_group_runtime_host import GroupExecutionGate,_REGISTRY
 except ImportError:hold('GROUP_PARENT_FIXED_HOST_REQUIRED')
 need(type(host)is GroupRuntimeHost and type(host.entry)is GroupExecutionGate
      and _REGISTRY.get(host.entry.id)is host.entry,'GROUP_PARENT_ACTUAL_HOST_REQUIRED')
 host.entry.held_pure();need(type(db)is OwnedConnection and _transaction_marker(db)is not None,
                           'GROUP_PARENT_OWNED_TRANSACTION_REQUIRED')
 return host.entry


def _pool_head(db,binding):
 row=db.execute('SELECT seq,head FROM group_pools WHERE account_key=?',(binding,)).fetchone()
 need(row is not None,'GROUP_PARENT_POOL_REQUIRED');return tuple(row)


def validate_parent_execution_in(host,db,operation_id, *, history_locators=None):
 """Only the actual fixed issuer + complete original history can mint this."""
 _id(operation_id);entry=_actual_host(host,db)
 info=check_parent_records_in(db,history_policy=entry.policy, history_locators=history_locators);record=info['executions'].get(operation_id)
 need(record is not None,'GROUP_PARENT_PLAN_REQUIRED');parent=record['parent']
 # Original pure phase/budget gates remain the unique source of child order.
 from .draft_group_store import _current_child
 states,events=_snapshot(db)
 try:
  state=states[parent['binding_sha']][0];_current_child(state,operation_id)
  head=_pool_head(db,parent['binding_sha'])
 finally:
  from .draft_group_response_history import release_group_replay_snapshot_in
  release_group_replay_snapshot_in(db,states,events)
 _fixed_current(host,db,operation_id,parent, history_locators=history_locators)
 need(_pool_head(db,parent['binding_sha'])==head,'GROUP_PARENT_CURRENT_SQL_CHANGED')
 child=next(c for c in parent['children']if c['operation_id']==operation_id)
 value=object.__new__(ValidatedParentExecution)
 value.operation_id=operation_id;value.capsule_sha=parent['source_scope_sha'];value.parent_grant_sha=candidate_sha(parent)
 value.first_purpose_key=parent['first_purpose_key'];value.original_not_after_ms=parent['not_after_ms'];value.route=parent['route']
 value._budget_json=canonical(child['budget'])
 _EXECUTIONS[value]=_ExecutionRecord(weakref.ref(host),weakref.ref(entry),weakref.ref(db),_transaction_marker(db),threading.get_ident(),
  canonical(_execution_fields(value)),canonical(parent),parent['binding_sha'],head)
 entry.issued[id(value)]=value
 return value


def validate_issued_parent_execution_in(value,host,db, *, history_locators=None):
 need(type(value)is ValidatedParentExecution,'GROUP_PARENT_ISSUED_EXECUTION_REQUIRED')
 record=_EXECUTIONS.get(value)
 need(record is not None,'GROUP_PARENT_EXECUTION_UNISSUED')
 entry=_actual_host(host,db)
 need(record is not None and record.host()is host and record.entry()is entry and record.db()is db
      and entry.issued.get(id(value))is value and record.epoch==_transaction_marker(db)
      and record.thread==threading.get_ident(),'GROUP_PARENT_EXECUTION_UNISSUED')
 fields=_execution_fields(value);_plain(fields)
 need(canonical(fields)==record.fields_json and _pool_head(db,record.binding_sha)==record.head,
      'GROUP_PARENT_EXECUTION_CHANGED')
 _fixed_current(host,db,value.operation_id,json.loads(record.parent_json), history_locators=history_locators)
 # The fixed current leaf completes replaceable source/file preparation.
 # Returned mirrors must still equal the original private facts afterwards.
 _plain(_execution_fields(value))
 need(canonical(_execution_fields(value))==record.fields_json,'GROUP_PARENT_EXECUTION_CHANGED')
 need(_pool_head(db,record.binding_sha)==record.head,'GROUP_PARENT_CURRENT_SQL_CHANGED')
 return value


def selection_review_scope_sha(candidate):
 validate_selection(candidate)
 return digest({'profile':'GROUP_EXACT_SELECTION_REVIEW_SCOPE_V1',**{k:candidate[k]for k in
  ('binding_sha','family_id','snapshot_preview_sha','source_scope_sha','settings_sha','budget_sha','affected_children')}})
