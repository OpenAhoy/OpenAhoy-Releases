"""Read the original immutable save and its same-account media proofs."""
from .own_draft_restore_contract import fail, parent_pin
from .own_workflow import stored
from .own_group_json import read as manifest_read
from .own_lineage import seal, mapping
from .service import digest, canonical


def parent_context(service, db, parent_step_id, *, history_locators=None):
    w,p=service.workflow,service.profile()
    w._resource(db,p, history_locators=history_locators)
    row=db.execute('SELECT * FROM own_steps WHERE id=?',(parent_step_id,)).fetchone()
    if (row is None or row['operation'] != 'add' or row['state'] != 'SUCCEEDED'
            or row['completed'] is None or any(row[k] != v for k,v in (
                ('tenant',p.actor.tenant_id),('principal',p.actor.principal_id),
                ('connection',p.connection_id),('resource',p.resource_id)))):
        fail('DRAFT_RESTORE_PARENT_NOT_QUALIFIED')
    # Uses the existing complete approval/asset/response-origin validator,
    # including original cover read proof and R1 body replacement provenance.
    intent,result=w._step(db,p,row, history_locators=history_locators)
    mrow=db.execute('SELECT * FROM own_articles WHERE version=?',(intent['selector']['version'],)).fetchone()
    if mrow is None:fail()
    m=manifest_read(mrow['manifest'],mrow['digest'])
    lineage=seal(db,m)
    from .own_draft_restore_store import check_write
    check_write(db,p.actor.tenant_id,p.resource_id,None if lineage['legacy'] else lineage['lineage'])
    w._write_gate(db,p,m, history_locators=history_locators)
    # `_step` already reconstructs and compares this projection to all original
    # media records. Do not upload images or mint new mappings for restoration.
    payload=intent['projection'] if m['schema'] in (2,3) else {
        'articles':[{'article_type':'news'}|intent['projection']]}
    if not payload or not isinstance(payload.get('articles'),list):fail()
    if db.execute('PRAGMA user_version').fetchone()[0] >= 7:
        for claim in db.execute("SELECT kind,fingerprint FROM publication_claims WHERE account_key=(SELECT account_key FROM publication_policy LIMIT 1)"):
            if claim['kind']=='ROOT' and claim['fingerprint']==lineage['lineage']:
                fail('DRAFT_RESTORE_ALREADY_SUBMITTED_OR_PUBLISHED')
    related_successes=[]
    for success in db.execute("SELECT * FROM own_steps WHERE operation='add' AND state='SUCCEEDED' AND tenant=? AND resource=? ORDER BY created,id",(p.actor.tenant_id,p.resource_id)):
        if success['id']==row['id']:continue
        success_intent=stored(success['intent'],success['intent_digest'])
        if mapping(db,success_intent['selector']['version'])['lineage']==lineage['lineage']:
            related_successes.append({'step_id':success['id'],'result_sha':success['result_digest'],
                'version':success_intent['selector']['version'],'completed':success['completed']})
    prior=[]
    if db.execute('PRAGMA user_version').fetchone()[0] in (8,9):
        for previous in db.execute("SELECT * FROM own_draft_restores WHERE tenant=? AND resource=? AND (lineage=? OR lineage='') AND state='SUCCEEDED' ORDER BY created,id",(p.actor.tenant_id,p.resource_id,lineage['lineage'])):
            result_value=stored(previous['result'],previous['result_digest'])
            prior.append({'restore_id':previous['id'],'grant_id':previous['grant_id'],
                'result_sha':previous['result_digest'],'reference':result_value['reference'],
                'completed':previous['completed']})
    return {'schema':1,'parent_step_id':row['id'],'parent_step_sha':parent_pin(row),
        'parent_result_sha':row['result_digest'],'parent_reference':result['reference'],
        'binding':p.binding(),'selector':intent['selector'],'version':m['version'],
        'manifest_digest':mrow['digest'],'lineage':lineage,
        'payload':payload,'payload_sha':digest(payload),'uploads':intent['uploads'],
        'completed':row['completed'],'prior_restorations':prior,'related_successes':related_successes,
        'titles':[article['title'] for article in payload['articles']]}
