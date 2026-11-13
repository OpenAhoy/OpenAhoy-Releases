"""Original step history validator extracted without authority or business I/O.

The complete original body is preserved modulo dynamic workflow-global lookup.
Only an actual ordinary cover/body row can enter the root-upload leaf below.
"""
import sqlite3
from . import own_workflow as ow


def validate_step_in(self, db, p, row, *, history_locators=None):
    if row is None or any((row[k] != v for k, v in zip(('tenant', 'principal', 'connection'), self._scope(p)))) or row['resource'] != p.resource_id or (row['operation'] not in {'cover', 'body', 'add'}) or (row['state'] not in {'RESULT_UNKNOWN', 'SUCCEEDED'}) or (not ow.finite(row['created'])) or (row['readback'] not in {'UNVERIFIED', 'MATCHED'}):
        raise ow.WCEError('OWN_ACCESS_DENIED')
    for field in ('id', 'request_key', 'owner'):
        ow.strict_validate(row[field], ow.ID)
    i = ow.stored(row['intent'], row['intent_digest'])
    from .normal_html_limits import POLICY as NORMAL_POLICY
    normal_marker = {'normal_html_policy'} if 'normal_html_policy' in i else set()
    intent_fields = normal_marker | {'schema', 'binding', 'profile_fence', 'selector', 'operation', 'slot', 'asset', 'projection', 'uploads', 'approval_id', 'approval_digest'}
    version = i.get('schema') if type(i) is dict else None
    if type(i) is not dict or type(version) is not int or version not in (1, 2) or (set(i) != intent_fields | ({'article_metadata'} if version == 2 else set())) or (version == 2 and row['operation'] != 'add') or (i['binding'] != p.binding()) or (i['operation'] != row['operation']) or (i['slot'] != row['slot']) or (i['approval_id'] != row['approval_id']) or (i['approval_digest'] != row['approval_digest']):
        raise ow.WCEError('OWN_STATE_CORRUPT')
    ow.binding_validate(i['binding'])
    selector = i['selector']
    if type(selector) is not dict or set(selector) != {'bundle_id', 'version', 'content_digest'}:
        raise ow.WCEError('OWN_STATE_CORRUPT')
    m, d = self._bundle(db, p, selector['bundle_id'], selector['version'])
    if (bool(normal_marker) != (row['operation']=='add' and m.get('document',{}).get('policy')==NORMAL_POLICY)
            or normal_marker and i['normal_html_policy']!=NORMAL_POLICY):
        raise ow.WCEError('OWN_STATE_CORRUPT')
    if selector['content_digest'] != d or d != row['manifest_digest'] or row['target'] != self._target(p, d, row['operation'], row['slot']):
        raise ow.WCEError('OWN_STATE_CORRUPT')
    approval = self._approval(db, p, m, d, row['approval_id'], False)
    if db.execute('PRAGMA user_version').fetchone()[0] in (5, 6, 7, 8, 9):
        from .own_lineage import seal
        if bool(seal(db, m)['legacy']) == (ow.json.loads(approval['body'])['schema'] == 7):
            raise ow.WCEError('OWN_LINEAGE_CORRUPT')
    if approval['body_digest'] != row['approval_digest'] or approval['binding_fence'] != i['profile_fence']:
        raise ow.WCEError('OWN_STATE_CORRUPT')
    slots = {a['slot']: a for a in m['assets']}
    if row['operation'] == 'add':
        if row['slot'] != 'draft' or i['asset'] is not None:
            raise ow.WCEError('OWN_STATE_CORRUPT')
        mappings, snapshots = self._uploads(db, p, m, d, history_locators=history_locators)
        body = ow.stored(approval['body'], approval['body_digest'])
        delegated = body.get('delegated', {})
        expected_projection = ow.projection(m, mappings)
        if version == 2:
            if body['schema'] != 7 or type(delegated) is not dict or type(delegated.get('schema')) is not int or (delegated['schema'] != 3) or (ow.canonical(i['article_metadata']) != ow.canonical(delegated.get('article_metadata'))):
                raise ow.WCEError('OWN_STATE_CORRUPT')
            expected_projection = ow._defaults_projection(expected_projection, i['article_metadata'], p.binding())
            same_projection = ow.canonical(i['projection']) == ow.canonical(expected_projection)
        else:
            if delegated.get('schema') == 3:
                raise ow.WCEError('OWN_STATE_CORRUPT')
            same_projection = i['projection'] == expected_projection
        if i['uploads'] != snapshots or not same_projection:
            raise ow.WCEError('OWN_STATE_CORRUPT')
    elif row['slot'] not in slots or i['asset'] != slots[row['slot']] or i['projection'] is not None or (i['uploads'] != []) or ((row['operation'] == 'cover') != (slots[row['slot']]['role'] == 'cover')):
        raise ow.WCEError('OWN_STATE_CORRUPT')
    result = ow.stored(row['result'], row['result_digest'], 4096)
    if type(result) is not dict:
        raise ow.WCEError('OWN_STATE_CORRUPT')
    synthetic = p.source_kind == 'SYNTHETIC_SETUP'
    if row['state'] == 'RESULT_UNKNOWN':
        if result != {} or row['completed'] is not None or row['readback'] != 'UNVERIFIED':
            raise ow.WCEError('OWN_STATE_CORRUPT')
    else:
        if not ow.finite(row['completed']) or row['completed'] < row['created']:
            raise ow.WCEError('OWN_STATE_CORRUPT')
        keys = {'reference'} if row['operation'] == 'add' else {'media_id', 'url'} if row['operation'] == 'cover' else {'url'}
        archived = result.get('completion_origin') == 'ORIGINAL_RESPONSE_ARCHIVE'
        recovered = archived or (row['operation'] in ('cover', 'add') and 'completion_origin' in result)
        if recovered:
            keys |= {'completion_origin', 'reconciliation_proof', 'reconciliation_proof_sha256'}
        if set(result) != keys or ('url' in result and (not ow.wire.image_url(result['url'], synthetic))):
            raise ow.WCEError('OWN_STATE_CORRUPT')
        if row['operation'] == 'body' and ow.json.loads(approval['body'])['schema'] == 7:
            from .upload_wire import api_reference_reason
            if api_reference_reason(result['url']) is not None:
                raise ow.WCEError('OWN_STATE_CORRUPT')
        for key in ('reference', 'media_id'):
            from .own_draft_wire import reference_valid
            validator = reference_valid if key == 'reference' else ow.wire.identifier
            if key in result and (not validator(result[key], synthetic)):
                raise ow.WCEError('OWN_STATE_CORRUPT')
        if recovered:
            ow.strict_validate(result['reconciliation_proof_sha256'], ow.DIGEST)
            if archived:
                from .own_response_archive import validate_proof
            elif row['operation'] == 'add':
                from .own_draft_reconcile import ORDINARY_ORIGIN
                if result.get('completion_origin') == ORDINARY_ORIGIN:
                    from .own_draft_reconcile import validate_ordinary_proof as validate_proof
                else:
                    from .own_draft_reconcile import validate_proof
            else:
                from .own_reconcile import validate_proof
            proof_workflow = self
            if row['operation'] == 'cover' and history_locators is not None:
                # Only this historical proof leaf receives a private H view.
                # ADD/_uploads and all live issuers retain the real workflow.
                from .draft_group_history_context import require_history
                require_history(self.db.history_policy, db, history_locators)
                proof_workflow = object.__new__(ow.OwnWorkflow)
                proof_workflow.db = self.db
                proof_workflow.policy = self.db.history_policy
                proof_workflow.history_locators = history_locators
            validate_proof(proof_workflow, db, p, row, i, result)
    return (i, result)


def validate_original_upload_in(workflow, db, profile, original, *, history_locators=None):
    """Validate actual cover/body history without calling _step or _uploads."""
    if not isinstance(db, sqlite3.Connection):
        raise ow.WCEError('GROUP_UPLOAD_TRANSACTION_REQUIRED')
    if type(original) not in (dict, sqlite3.Row):
        raise ow.WCEError('GROUP_UPLOAD_ROOT_HOLD')
    given = dict(original)
    if (any(type(k) is not str or type(v) not in (str,int,float,bool,type(None))
            for k,v in given.items()) or type(given.get('id')) is not str):
        raise ow.WCEError('GROUP_UPLOAD_ROOT_HOLD')
    ow.strict_validate(given['id'],ow.ID)
    row=db.execute('SELECT * FROM own_steps WHERE id=?',(given['id'],)).fetchone()
    if row is None or dict(row)!=given or row['operation'] not in ('cover','body'):
        raise ow.WCEError('GROUP_UPLOAD_ROOT_HOLD')
    return validate_step_in(workflow,db,profile,row, history_locators=history_locators)


def read_original_upload_success_in(workflow, db, profile, step_id, *, history_locators=None):
    """Return flattened existing ordinary mapping/snapshot, never a new row."""
    if type(step_id) is not str:
        raise ow.WCEError('GROUP_UPLOAD_ROOT_HOLD')
    from .own_connection_workflow import PersistentWorkflow
    if type(workflow) not in (ow.OwnWorkflow,PersistentWorkflow):
        raise ow.WCEError('GROUP_UPLOAD_ROOT_HOLD')
    ow.strict_validate(step_id,ow.ID)
    if not isinstance(db,sqlite3.Connection) or not db.in_transaction:
        raise ow.WCEError('GROUP_UPLOAD_TRANSACTION_REQUIRED')
    row=db.execute('SELECT * FROM own_steps WHERE id=?',(step_id,)).fetchone()
    intent,result=validate_original_upload_in(workflow,db,profile,row, history_locators=history_locators)
    if row['state']=='RESULT_UNKNOWN' and row['operation']=='body':
        from .own_lineage_replacement import mapping as lineage_mapping
        replacement=lineage_mapping(workflow,db,profile,row, history_locators=history_locators)
        if replacement is None:
            from .own_body_recovery import mapping as body_mapping
            replacement=body_mapping(workflow,db,profile,row, history_locators=history_locators)
        if replacement is None:
            raise ow.WCEError('OWN_UPLOADS_INCOMPLETE')
        mapping,snapshot=replacement
    elif row['state']=='SUCCEEDED':
        mapping=result
        snapshot={k:row[k] for k in ('id','intent_digest','target','result_digest')}
    else:
        raise ow.WCEError('OWN_UPLOADS_INCOMPLETE')
    from .own_response_archive import row_pin
    return ow.json.loads(ow.canonical({'authority':False,'selector':intent['selector'],
        'asset':intent['asset'],'operation':row['operation'],'slot':row['slot'],
        'base_step_pin':row_pin(row),'mapping':mapping,'snapshot':snapshot,
        'result_digest':snapshot['result_digest']}))
