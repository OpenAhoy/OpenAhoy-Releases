"""Bounded, non-recursive sealed media evidence for two retained add records.

capture() requires the caller's existing read transaction and real historical
workflow validators. validate_add() is pure and never opens any file or database.
Neither routine grants authority or sends a request.
"""
from copy import deepcopy
from hashlib import sha256
from .contracts import WCEError
from .service import canonical,digest
from .prepared_contracts import ID,DIGEST,strict_validate
from .prepared_draft_fixture import decode_json
from .own_auth import APIS,finite
from .own_workflow import binding_validate,projection,_defaults_projection,stored
from . import own_response_archive as archive,own_wire as wire
from .upload_wire import BODY_API_REFERENCE_POLICY,COVER_RESPONSE_POLICY,api_reference_reason

POLICY='SEALED_ADD_MEDIA_LEAVES_V1'
STEP_FIELDS={'id','tenant','principal','connection','resource','request_key','operation','slot','manifest_digest','target','approval_id','approval_digest','intent','intent_digest','owner','state','result','result_digest','created','completed','readback'}
APPROVAL_FIELDS={'id','tenant','principal','connection','resource','binding_fence','manifest_digest','body','body_digest','expires','cancelled'}
INTENT_FIELDS={'schema','binding','profile_fence','selector','operation','slot','asset','projection','uploads','approval_id','approval_digest'}
BASE_APPROVAL={'schema','binding','fence','bundle_id','version','content_digest','slots','apis','expires','delegated'}
SNAPSHOT_FIELDS=('id','intent_digest','target','result_digest')
MAXIMUM=2*1024*1024

def fail(code='OWN_REPLACEMENT_MEDIA_INVALID'): raise WCEError(code)
def exact(value,fields):
    if type(value) is not dict or set(value)!=set(fields):fail()
def _json_bytes(obj,limit,nodes=32768):
    try:
        raw=canonical(obj).encode('utf-8')
        if len(raw)>limit or decode_json(raw,limit,max_nodes=nodes)!=obj:fail('OWN_REPLACEMENT_MEDIA_LIMIT')
        return raw
    except (TypeError,ValueError,UnicodeError) as exc:
        raise WCEError('OWN_REPLACEMENT_MEDIA_LIMIT') from exc

def _manifest(binding,m,checksum,lineage):
    if type(m) is not dict:fail()
    binding_validate(binding)
    exact(m,{'schema','binding','bundle_id','version','revision','document' if m.get('schema') in (2,3) else 'article','assets'})
    if (type(m['schema']) is not int or m['schema'] not in (1,2,3) or type(m['revision']) is not int or m['revision']<1
            or m['binding']!=binding or digest(m)!=checksum or type(m['assets']) is not list or not 1<=len(m['assets'])<=40):fail()
    strict_validate(checksum,DIGEST)
    from .own_contracts import SPECS
    strict_validate(m['bundle_id'],SPECS['own.articles.read']['properties']['bundle_id'])
    strict_validate(m['version'],SPECS['own.articles.read']['properties']['version'])
    if (m['schema'] in (2,3) and
            (type(m['document']) is not dict or m['document'].get('format')!=m['schema'])):
        fail()
    from .own_group_json import read,_manifest_fields
    if read(canonical(m),checksum)!=m or not _manifest_fields(m):fail()
    from .own_lineage import root_id,POLICY as LP
    exact(lineage,{'tenant','resource','lineage','root_version','normalization_policy','legacy'})
    if (lineage['tenant']!=binding['tenant'] or lineage['resource']!=binding['resource'] or type(lineage['legacy']) is not int
        or lineage['legacy']!=0 or lineage['normalization_policy']!=LP):fail()
    for k in ('lineage',):strict_validate(lineage[k],DIGEST)
    strict_validate(lineage['root_version'],ID)
    # Root manifest may be an earlier same-bundle revision, verified by the
    # containing entry/current path; only a self-root can be recomputed here.
    if lineage['root_version']==m['version'] and root_id(m,m['version'],False)!=lineage['lineage']:fail()
    slots=set();refs=set();ref_metadata={}
    for asset in m['assets']:
        if asset['slot'] in slots or (m['schema']==1 and asset['asset_ref'] in refs):fail()
        metadata=(asset['role'],asset['sha256'],asset['declared_type'],asset['size'])
        previous=ref_metadata.setdefault(asset['asset_ref'],metadata)
        if previous!=metadata:fail()
        slots.add(asset['slot']);refs.add(asset['asset_ref'])
    if m['schema'] in (2,3):
        from . import documents
        if documents.normalize(m['document'])!=m['document']:fail()
        descriptors=list(documents.assets(m['document']))
        sizes={}
        for asset in m['assets']:
            article_id=asset['slot'].split('--',1)[0]
            sizes[article_id]=sizes.get(article_id,0)+asset['size']
        if sum(sizes.values())>32*1024*1024 or any(n>8*1024*1024 for n in sizes.values()):fail()
        from .import_styles import POLICY as IMPORT_POLICY
        if m['document'].get('policy')==IMPORT_POLICY:
            declared={a['id']+'--'+entry['slot']:entry for a in m['document']['articles'] for entry in a['provenance']['images']}
            for asset in m['assets']:
                record=declared.get(asset['slot'])
                if record is None or (asset['role'],asset['sha256'],asset['declared_type'],asset['size']) != (
                        record['role'],record['transport_sha256'],record['transport_mime'],record['transport_size']):fail()
    else:
        article=m['article'];strict_validate(article,SPECS['own.articles.prepare']['properties']['article'])
        if len(article['title'])>32 or not any(b['type']!='image' for b in article['blocks']):fail()
        descriptors=[('cover',article['cover_asset_ref'],'cover')]+[(x['slot'],x['asset_ref'],'body') for x in article['blocks'] if x['type']=='image']
        if len(m['assets'])>5 or sum(a['size'] for a in m['assets'])>8*1024*1024:fail()
    if [(a['slot'],a['asset_ref'],a['role']) for a in m['assets']]!=descriptors:fail()

def _approval(row,binding,m,checksum,lineage):
    exact(row,APPROVAL_FIELDS)
    for key in ('id',):strict_validate(row[key],ID)
    if (any(row[k]!=binding[k] for k in ('tenant','principal','connection','resource'))
            or row['manifest_digest']!=checksum or not finite(row['expires'])
            or type(row['cancelled']) is not int or row['cancelled'] not in (0,1)):fail()
    body=stored(row['body'],row['body_digest']);exact(body,BASE_APPROVAL)
    if canonical(body)!=row['body'] or type(body['schema']) is not int or body['schema']!=7:fail()
    if (body['binding']!=binding or body['fence']!=row['binding_fence'] or body['bundle_id']!=m['bundle_id']
            or body['version']!=m['version'] or body['content_digest']!=checksum or body['slots']!=m['assets']
            or body['apis']!=list(APIS) or body['expires']!=row['expires'] or not finite(body['expires'])):fail()
    delegated=body['delegated'];original={'policy','lineage','lineage_digest','response_policy'}
    if type(delegated) is not dict or set(delegated) not in (original,original|{'schema','cover_response_policy'},original|{'schema','cover_response_policy','article_metadata'}):fail()
    if 'schema' in delegated:
        n=3 if 'article_metadata' in delegated else 2
        if type(delegated['schema']) is not int or delegated['schema']!=n or delegated['cover_response_policy']!=COVER_RESPONSE_POLICY:fail()
    if 'article_metadata' in delegated:
        from .own_draft_defaults import validate_defaults_metadata
        count=len(m['document']['articles']) if m['schema'] in (2,3) else 1
        validate_defaults_metadata(delegated['article_metadata'],expected_binding_sha=digest(binding),article_count=count)
    pol=delegated['policy'];exact(pol,{'id','revision','policy_digest','candidate_scope'})
    strict_validate(pol['id'],ID)
    if type(pol['revision']) is not int or pol['revision']<1:fail()
    for k in ('policy_digest','candidate_scope'):strict_validate(pol[k],DIGEST)
    if delegated['lineage']!=lineage or delegated['lineage_digest']!=digest(lineage) or delegated['response_policy']!=BODY_API_REFERENCE_POLICY:fail()
    return body

def _step_common(row,intent,binding,m,checksum):
    exact(row,STEP_FIELDS)
    if (any(row[k]!=binding[k] for k in ('tenant','principal','connection','resource')) or not finite(row['created'])
            or row['readback'] not in ('UNVERIFIED','MATCHED')):fail()
    for k in ('id','request_key','owner'):strict_validate(row[k],ID)
    if type(intent) is not dict or type(intent.get('schema')) is not int or intent['schema'] not in (1,2):fail()
    exact(intent,INTENT_FIELDS|({'article_metadata'} if intent['schema']==2 else set()))
    if (canonical(intent)!=row['intent'] or digest(intent)!=row['intent_digest'] or intent['binding']!=binding
            or intent['operation']!=row['operation'] or intent['slot']!=row['slot'] or intent['approval_id']!=row['approval_id']
            or intent['approval_digest']!=row['approval_digest'] or row['manifest_digest']!=checksum
            or intent['selector']!={'bundle_id':m['bundle_id'],'version':m['version'],'content_digest':checksum}
            or row['target']!=digest({'tenant':binding['tenant'],'resource':binding['resource'],'manifest_digest':checksum,'operation':row['operation'],'slot':row['slot']})):fail()
    strict_validate(row['approval_digest'],DIGEST);strict_validate(row['intent_digest'],DIGEST);strict_validate(row['result_digest'],DIGEST)

def _packed_approval(row):
    exact(row,APPROVAL_FIELDS);body=stored(row['body'],row['body_digest'])
    if canonical(body)!=row['body'] or 'slots' not in body:fail()
    return {'row_without_body':{k:v for k,v in row.items() if k!='body'},
        'body_without_slots':{k:v for k,v in body.items() if k!='slots'},'slots_ref':'PARENT_ASSETS','row_sha256':digest(row)}

def _unpack(packed,assets):
    exact(packed,{'row_without_body','body_without_slots','slots_ref','row_sha256'})
    if packed['slots_ref']!='PARENT_ASSETS' or type(packed['body_without_slots']) is not dict or 'slots' in packed['body_without_slots']:fail()
    exact(packed['row_without_body'],APPROVAL_FIELDS-{'body'})
    row=dict(packed['row_without_body'],body=canonical(dict(packed['body_without_slots'],slots=assets)))
    if digest(row)!=packed['row_sha256'] or digest(dict(packed['body_without_slots'],slots=assets))!=row.get('body_digest'):fail()
    return row

def _proof(binding,row,result,bundle):
    exact(bundle,{'proof','proof_sha256','index','index_sha256'})
    if type(bundle['proof']) is not str or type(bundle['index']) is not str:fail()
    raw=bundle['proof'].encode('utf-8');idx=bundle['index'].encode('utf-8')
    if sha256(raw).hexdigest()!=bundle['proof_sha256'] or sha256(idx).hexdigest()!=bundle['index_sha256']:fail()
    index=decode_json(idx,1024);proof=decode_json(raw,8192)
    exact(index,{'schema','row_sha256','proof_sha256'});exact(proof,{'schema','policy','provenance','binding','row','request_sha256','response_sha256','result'})
    if (type(index['schema']) is not int or index['schema']!=1 or index['row_sha256']!=digest(archive.row_pin(row))
       or index['proof_sha256']!=sha256(raw).hexdigest() or (canonical(index)+'\n').encode()!=idx
       or type(proof['schema']) is not int or proof['schema']!=1 or proof['policy']!=archive.POLICY
       or proof['binding']!=binding or proof['row']!=archive.row_pin(row)
       or proof['provenance']!=('SYNTHETIC_OWN_WIRE' if binding['source_kind']=='SYNTHETIC_SETUP' else 'OWN_OFFICIAL_WIRE')
       or (canonical(proof)+'\n').encode()!=raw):fail()
    for k in ('request_sha256','response_sha256'):strict_validate(proof[k],DIGEST)
    x=proof['result'];exact(x,{'url'} if row['operation']=='body' else {'url','media_id'})
    synthetic=binding['source_kind']=='SYNTHETIC_SETUP'
    if (not wire.image_url(x['url'],synthetic) or (row['operation']=='body' and api_reference_reason(x['url']) is not None)
        or ('media_id' in x and not wire.identifier(x['media_id'],synthetic))):fail()
    if archive.completed(proof,raw,row)!=result:fail()

def validate_add(binding,manifest,manifest_sha,add_row,add_intent,add_approval,lineage,dependencies):
    """Validate sealed dependencies and UNKNOWN add entirely offline."""
    _json_bytes(dependencies,MAXIMUM);_manifest(binding,manifest,manifest_sha,lineage)
    exact(dependencies,{'schema','policy','binding_sha','manifest_sha','approvals','leaves'})
    if (type(dependencies['schema']) is not int or dependencies['schema']!=1 or dependencies['policy']!=POLICY
        or dependencies['binding_sha']!=digest(binding) or dependencies['manifest_sha']!=manifest_sha
        or type(dependencies['approvals']) is not list or not 1<=len(dependencies['approvals'])<=40
        or type(dependencies['leaves']) is not list or len(dependencies['leaves'])!=len(manifest['assets'])):fail()
    body=_approval(add_approval,binding,manifest,manifest_sha,lineage);_step_common(add_row,add_intent,binding,manifest,manifest_sha)
    if (add_row['operation']!='add' or add_row['slot']!='draft' or add_row['state']!='RESULT_UNKNOWN'
        or add_row['completed'] is not None or add_row['readback']!='UNVERIFIED' or add_row['result']!='{}'
        or add_row['result_digest']!=digest({}) or add_intent['asset'] is not None
        or add_approval['id']!=add_row['approval_id'] or add_approval['body_digest']!=add_row['approval_digest']
        or add_approval['binding_fence']!=add_intent['profile_fence']):fail()
    approvals={}
    for packed in dependencies['approvals']:
        a=_unpack(packed,manifest['assets']);key=a['id']+':'+a['body_digest']
        if key in approvals:fail()
        _approval(a,binding,manifest,manifest_sha,lineage);approvals[key]=a
    used=set();seen_ids=set();mappings={};snapshots=[]
    for asset,leaf in zip(manifest['assets'],dependencies['leaves']):
        exact(leaf,{'slot','operation','row','intent','result','approval_ref','snapshot','origin','proof_bundle'})
        op='cover' if asset['role']=='cover' else 'body';row=leaf['row'];intent=leaf['intent'];result=leaf['result']
        if leaf['slot']!=asset['slot'] or leaf['operation']!=op or leaf['origin']!=archive.ORIGIN:fail('UNSUPPORTED_MEDIA_DEPENDENCY')
        _step_common(row,intent,binding,manifest,manifest_sha)
        if (intent['schema']!=1 or row['id'] in seen_ids or row['id']==add_row['id'] or row['operation']!=op or row['slot']!=asset['slot']
            or row['state']!='SUCCEEDED' or row['readback']!='UNVERIFIED' or not finite(row['completed']) or row['completed']<row['created']
            or intent['asset']!=asset or intent['projection'] is not None or intent['uploads']!=[] or canonical(result)!=row['result']
            or digest(result)!=row['result_digest'] or stored(row['result'],row['result_digest'],4096)!=result):fail()
        key=row['approval_id']+':'+row['approval_digest'];approval=approvals.get(key)
        if key!=leaf['approval_ref'] or approval is None or approval['binding_fence']!=intent['profile_fence']:fail()
        _proof(binding,row,result,leaf['proof_bundle'])
        snapshot={k:row[k] for k in SNAPSHOT_FIELDS}
        if snapshot!=leaf['snapshot']:fail()
        used.add(key);seen_ids.add(row['id']);snapshots.append(snapshot);mappings[asset['slot']]=result
    if used!=set(approvals) or add_intent['uploads']!=snapshots:fail()
    projected=projection(manifest,mappings);delegated=body['delegated']
    if add_intent['schema']==2:
        if (type(delegated.get('schema')) is not int or delegated['schema']!=3
                or canonical(add_intent['article_metadata'])!=canonical(delegated.get('article_metadata'))):fail()
        projected=_defaults_projection(projected,add_intent['article_metadata'],binding)
        if canonical(projected)!=canonical(add_intent['projection']):fail()
    elif delegated.get('schema')==3 or projected!=add_intent['projection']:fail()
    return {'mappings':mappings,'snapshots':snapshots}

def capture(workflow,db,profile,manifest,manifest_sha,add_row,add_intent,add_approval, *, history_locators=None):
    """Capture only supported complete leaves inside an existing read transaction.

    Every source is classified before any add _step; unsupported, UNKNOWN or
    replacement sources cannot enter the legacy recursive mapping code.
    """
    if not db.in_transaction:fail('OWN_REPLACEMENT_READ_TRANSACTION_REQUIRED')
    binding=profile.binding();add_row=dict(add_row);add_approval=dict(add_approval)
    from .own_lineage import seal
    m,d=workflow._bundle(db,profile,manifest['bundle_id'],manifest['version'])
    if m!=manifest or d!=manifest_sha:fail()
    lineage=seal(db,m)
    if type(add_intent.get('uploads')) is not list or len(add_intent['uploads'])!=len(manifest['assets']):fail('UNSUPPORTED_MEDIA_DEPENDENCY')
    rows=[];ids=set()
    for asset,snapshot in zip(manifest['assets'],add_intent['uploads']):
        exact(snapshot,SNAPSHOT_FIELDS)
        if snapshot['id'] in ids or snapshot['id']==add_row['id']:fail('UNSUPPORTED_MEDIA_DEPENDENCY')
        row=db.execute('SELECT * FROM own_steps WHERE id=?',(snapshot['id'],)).fetchone()
        if row is None:fail('UNSUPPORTED_MEDIA_DEPENDENCY')
        row=dict(row);op='cover' if asset['role']=='cover' else 'body'
        if row['state']!='SUCCEEDED' or row['operation']!=op or row['slot']!=asset['slot'] or {k:row[k] for k in SNAPSHOT_FIELDS}!=snapshot:
            fail('UNSUPPORTED_MEDIA_DEPENDENCY')
        # Classify origin before _step or any add recursion.
        result=stored(row['result'],row['result_digest'],4096)
        if type(result) is not dict or result.get('completion_origin')!=archive.ORIGIN:fail('UNSUPPORTED_MEDIA_DEPENDENCY')
        target_row=db.execute('SELECT id FROM own_steps WHERE target=?',(row['target'],)).fetchone()
        if target_row is None or target_row['id']!=row['id']:fail('UNSUPPORTED_MEDIA_DEPENDENCY')
        rows.append((asset,row,snapshot));ids.add(row['id'])
    # Explicit original target and identity, then actual full historical checks.
    current=db.execute('SELECT * FROM own_steps WHERE id=?',(add_row['id'],)).fetchone()
    if current is None or dict(current)!=add_row:fail()
    actual_approval=workflow._approval(db,profile,m,d,add_row['approval_id'],False)
    if dict(actual_approval)!=add_approval:fail()
    approvals={};leaves=[]
    from .own_bootstrap_security import private_read
    for asset,row,snapshot in rows:
        intent,result=workflow._step(db,profile,row, history_locators=history_locators)
        approval=dict(workflow._approval(db,profile,m,d,row['approval_id'],False))
        proof,raw,_=archive._read(workflow,profile,row)
        path=workflow.db.path.parent/('response-index-'+row['id']+'-'+row['owner']+'.json')
        idx,_=private_read(path)
        key=approval['id']+':'+approval['body_digest'];packed=_packed_approval(approval)
        if key in approvals and approvals[key]!=packed:fail()
        approvals[key]=packed
        leaves.append({'slot':asset['slot'],'operation':row['operation'],'row':row,'intent':intent,'result':result,
            'approval_ref':key,'snapshot':snapshot,'origin':archive.ORIGIN,
            'proof_bundle':{'proof':raw.decode('utf-8'),'proof_sha256':sha256(raw).hexdigest(),
                'index':idx.decode('utf-8'),'index_sha256':sha256(idx).hexdigest()}})
    actual_intent,actual_result=workflow._step(db,profile,current, history_locators=history_locators)
    if actual_intent!=add_intent or actual_result!={}:fail()
    result={'schema':1,'policy':POLICY,'binding_sha':digest(binding),'manifest_sha':manifest_sha,
        'approvals':list(approvals.values()),'leaves':leaves}
    validate_add(binding,manifest,manifest_sha,add_row,add_intent,add_approval,lineage,result)
    return result
