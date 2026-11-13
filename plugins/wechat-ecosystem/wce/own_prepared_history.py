"""Shared original prepared-content and approval validators.

These readers do not accept a request or issue authority. OwnWorkflow retains
its original dynamic/current checks; a source-only reader must additionally
own a real read-only transaction, policy and H context. Method bodies below
are extracted verbatim so the ordinary and source-only paths cannot diverge.
"""
from .contracts import WCEError
from .local_preparation import image_check, sha
from .own_auth import APIS, DRAFT_READ_APIS, finite
from .own_contracts import SPECS, validate
from .prepared_contracts import DIGEST, ID, strict_validate, schema
from .service import canonical
from . import documents, own_group_json


def encoded(value):
    return canonical(value)


def stored(value, fingerprint, maximum=None):
    return own_group_json.read(value, fingerprint, maximum)


def binding_validate(binding):
    spec = schema({k: ID for k in ('tenant', 'principal', 'client', 'session', 'connection', 'account', 'resource')}
        | {k: {'type': 'integer', 'minimum': 1 if k == 'generation' else 0, 'maximum': 2**63 - 1}
           for k in ('generation', 'epoch')}
        | {'source_kind': {'type': 'string', 'enum': ['SYNTHETIC_SETUP', 'OPERATOR_ATTESTED']}})
    strict_validate(binding, spec)



class PreparedHistoryValidation:
    """Original parsing only; not a service, permission or network executor."""

    @staticmethod
    def _scope(p):
        return p.actor.tenant_id, p.actor.principal_id, p.connection_id


    def _asset(self, db, bind, ref, role=None):
        strict_validate(ref, SPECS['own.articles.prepare']['properties']['article']['properties']['cover_asset_ref'])
        binding_validate(bind)
        row = db.execute('SELECT * FROM own_assets WHERE id=?', (ref,)).fetchone()
        if row is None or row['binding'] != encoded(bind):
            raise WCEError('OWN_ACCESS_DENIED')
        data = row['data']
        if (type(row['size']) is not int or type(data) is not bytes or not 0 < len(data) <= 2097152
                or len(data) != row['size'] or sha(data) != row['sha256']
                or row['role'] not in {'cover', 'body'} or row['mime'] not in {'image/png', 'image/jpeg'}):
            raise WCEError('OWN_STATE_CORRUPT')
        strict_validate(row['sha256'], DIGEST)
        image_check(data, row['mime'])
        if role is not None and row['role'] != role:
            raise WCEError('OWN_ASSET_ROLE_MISMATCH')
        return {'asset_ref': ref, 'role': row['role'], 'declared_type': row['mime'],
                'size': row['size'], 'sha256': row['sha256']}, data


    def _content(self, db, bind, article):
        strict_validate(article, SPECS['own.articles.prepare']['properties']['article'])
        if len(article['title']) > 32 or not any(b['type'] != 'image' for b in article['blocks']):
            raise WCEError('OWN_INVALID_ARTICLE')
        cover, _ = self._asset(db, bind, article['cover_asset_ref'], 'cover')
        assets, slots, refs = [cover | {'slot': 'cover'}], {'cover'}, {cover['asset_ref']}
        for b in article['blocks']:
            if b['type'] != 'image':
                continue
            if b['slot'] in slots or b['asset_ref'] in refs or len(assets) >= 5:
                raise WCEError('OWN_INVALID_ARTICLE')
            meta, _ = self._asset(db, bind, b['asset_ref'], 'body')
            assets.append(meta | {'slot': b['slot']})
            slots.add(b['slot']); refs.add(b['asset_ref'])
        if sum(a['size'] for a in assets) > 8 * 1024 * 1024:
            raise WCEError('OWN_IMAGE_LIMIT')
        return assets


    def _document_content(self, db, bind, document):
        normalized = documents.normalize(document)
        if normalized != document:
            raise WCEError('OWN_STATE_CORRUPT')
        assets, group_size = [], 0
        article_by_id = {a['id']: a for a in document['articles']}
        sizes = {}
        for slot, ref, role in documents.assets(document):
            meta, data = self._asset(db, bind, ref, role)
            assets.append(meta | {'slot': slot})
            article_id = slot.split('--', 1)[0]
            if role == 'cover':
                from .editor_contracts import verify_cover
                verify_cover(article_by_id[article_id], data, meta['declared_type'])
            sizes[article_id] = sizes.get(article_id, 0) + meta['size']
            group_size += meta['size']
        from .normal_html_limits import POLICY as NORMAL_POLICY
        if document.get('policy') != NORMAL_POLICY and (group_size > 32 * 1024 * 1024 or any(n > 8 * 1024 * 1024 for n in sizes.values())):
            raise WCEError('OWN_IMAGE_LIMIT')
        from .import_styles import POLICY as IMPORT_POLICY
        if document.get('policy') in (IMPORT_POLICY,NORMAL_POLICY):
            declared = {a['id']+'--'+s['slot']:s for a in document['articles'] for s in a['provenance']['images']}
            for asset in assets:
                record = declared[asset['slot']]
                if (asset['role'],asset['sha256'],asset['declared_type'],asset['size']) != (
                        record['role'],record['transport_sha256'],record['transport_mime'],record['transport_size']):
                    raise WCEError('HTML_IMPORT_SOURCE_BINDING')
        return assets


    def _bundle(self, db, p, bundle, version):
        from .own_validation_scope import bundle_content
        strict_validate(bundle, SPECS['own.articles.read']['properties']['bundle_id'])
        strict_validate(version, SPECS['own.articles.read']['properties']['version'])
        return bundle_content(self.db, db, p.binding(), bundle, version,
                              lambda: self._bundle_full(db, p, bundle, version))


    def _bundle_full(self, db, p, bundle, version):
        strict_validate(bundle, SPECS['own.articles.read']['properties']['bundle_id'])
        strict_validate(version, SPECS['own.articles.read']['properties']['version'])
        row = db.execute('SELECT * FROM own_articles WHERE bundle=? AND version=?', (bundle, version)).fetchone()
        if row is None or row['binding'] != encoded(p.binding()):
            raise WCEError('OWN_ACCESS_DENIED')
        m = stored(row['manifest'], row['digest'])
        if (type(m) is not dict or set(m) != {'schema', 'binding', 'bundle_id', 'version', 'revision', 'document' if m.get('schema') in (2, 3) else 'article', 'assets'}
                or type(m['schema']) is not int or m['schema'] not in (1, 2, 3) or type(m['revision']) is not int
                or m['revision'] != row['revision'] or m['revision'] < 1
                or m['binding'] != p.binding() or m['bundle_id'] != bundle or m['version'] != version):
            raise WCEError('OWN_STATE_CORRUPT')
        binding_validate(m['binding'])
        if m['schema'] in (2, 3) and (type(m['document']) is not dict or m['document'].get('format') != m['schema']):
            raise WCEError('OWN_STATE_CORRUPT')
        if (self._document_content(db, m['binding'], m['document']) if m['schema'] in (2, 3) else
                self._content(db, m['binding'], m['article'])) != m['assets']:
            raise WCEError('OWN_STATE_CORRUPT')
        return m, row['digest']


    def _old_input(self, db, p, kind, key, parameters=None):
        row = db.execute('SELECT * FROM own_inputs WHERE tenant=? AND principal=? AND connection=? AND kind=? AND request_key=?',
                         self._scope(p) + (kind, key)).fetchone()
        if row is None:
            return None
        original = stored(row['parameters'], row['fingerprint'])
        result = stored(row['result'], row['result_digest'])
        if parameters is not None and original != parameters:
            raise WCEError('IDEMPOTENCY_CONFLICT')
        if kind == 'asset':
            if type(original) is not dict or set(original) != {'path_digest', 'role', 'mime'}:
                raise WCEError('OWN_STATE_CORRUPT')
            strict_validate(original['path_digest'], DIGEST)
            actual, _ = self._asset(db, p.binding(), result.get('asset_ref'), original['role'])
            if result != actual or actual['declared_type'] != original['mime']:
                raise WCEError('OWN_STATE_CORRUPT')
        else:
            document = 'document' in original
            validate('own.documents.prepare' if document else 'own.articles.prepare',
                     {'connection_id': p.connection_id, 'request_key': key} | original)
            if (type(result) is not dict or set(result) != {'bundle_id', 'version', 'revision', 'content_digest'}
                    or type(result['revision']) is not int):
                raise WCEError('OWN_STATE_CORRUPT')
            m, d = self._bundle(db, p, result['bundle_id'], result['version'])
            if ((m.get('document') != documents.normalize(original['document']) if document else
                    m.get('article') != original['article']) or d != result['content_digest'] or m['revision'] != result['revision']):
                raise WCEError('OWN_STATE_CORRUPT')
        return result | {'request_key': key, 'input_state': 'COMMITTED'}


    def _approval(self, db, p, m, d, identifier=None, active=True, allow_local_adoption=False, allow_draft_read=False):
        if identifier is None:
            rows = db.execute('SELECT * FROM own_approvals WHERE tenant=? AND principal=? AND connection=? '
                'AND resource=? AND manifest_digest=? AND binding_fence=? AND cancelled=0 AND expires>? ORDER BY rowid DESC',
                self._scope(p) + (p.resource_id, d, p.fence(), self.clock())).fetchall()
            if not rows:
                raise WCEError('OWN_APPROVAL_UNAVAILABLE')
            row = rows[0]
        else:
            row = db.execute('SELECT * FROM own_approvals WHERE id=?', (identifier,)).fetchone()
        if (row is None or any(row[k] != v for k, v in zip(('tenant', 'principal', 'connection'), self._scope(p)))
                or row['resource'] != p.resource_id or row['manifest_digest'] != d
                or not finite(row['expires']) or type(row['cancelled']) is not int or row['cancelled'] not in (0, 1)):
            raise WCEError('OWN_STATE_CORRUPT')
        body = stored(row['body'], row['body_digest'])
        from .normal_html_limits import POLICY as NORMAL_POLICY
        normal = m.get('document',{}).get('policy') == NORMAL_POLICY
        base_fields = ({'normal_html_policy'} if normal else set()) | {'schema', 'binding', 'fence', 'bundle_id', 'version',
                       'content_digest', 'slots', 'apis', 'expires'}
        if type(body) is not dict or type(body.get('schema')) is not int or body['schema'] not in (1, 2, 3, 4, 5, 6, 7):
            raise WCEError('OWN_STATE_CORRUPT')
        pixel = body['schema'] == 2
        extra = {'recovery_policy'} if pixel else {'body_recovery'} if body['schema'] == 3 else {'body_followup'} if body['schema'] == 4 else {'body_attempt'} if body['schema'] == 5 else {'draft_recovery'} if body['schema'] == 6 else {'delegated'} if body['schema'] == 7 else set()
        if (set(body) != base_fields | extra or not finite(body['expires'])
                or normal and body.get('normal_html_policy') != NORMAL_POLICY):
            raise WCEError('OWN_STATE_CORRUPT')
        recovery_policy = None
        if pixel:
            from .own_png import validate_binding
            recovery_policy = validate_binding(body['recovery_policy'])
            covers = [asset for asset in m['assets'] if asset['slot'] == 'cover']
            if (len(covers) != 1 or recovery_policy['asset_sha256'] != covers[0]['sha256']
                    or recovery_policy['asset_size'] != covers[0]['size']):
                raise WCEError('OWN_STATE_CORRUPT')
        body_recovery = None
        if body['schema'] == 3:
            from .own_body_recovery import validate_policy
            body_recovery = body['body_recovery']
            _, old_intent = validate_policy(db, body_recovery)
            if (old_intent['binding'] != p.binding() or old_intent['selector'] != {
                    'bundle_id': m['bundle_id'], 'version': m['version'], 'content_digest': d}):
                raise WCEError('OWN_STATE_CORRUPT')
        body_followup = None
        if body['schema'] == 4:
            from .own_body_followup import validate_policy
            body_followup = body['body_followup']
            _, old_intent = validate_policy(db, body_followup)
            if (old_intent['binding'] != p.binding() or old_intent['selector'] != {
                    'bundle_id': m['bundle_id'], 'version': m['version'], 'content_digest': d}):
                raise WCEError('OWN_STATE_CORRUPT')
        body_attempt = None
        if body['schema'] == 5:
            from .own_body_attempt import validate_policy
            body_attempt = body['body_attempt']
            _, old_intent = validate_policy(db, body_attempt)
            if (old_intent['binding'] != p.binding() or old_intent['selector'] != {
                    'bundle_id': m['bundle_id'], 'version': m['version'], 'content_digest': d}):
                raise WCEError('OWN_STATE_CORRUPT')
        draft_recovery = None
        if body['schema'] == 6:
            from .own_draft_reconcile import validate_policy
            draft_recovery = body['draft_recovery']
            _, old_intent = validate_policy(db, draft_recovery)
            if old_intent['binding'] != p.binding() or old_intent['selector'] != {
                    'bundle_id': m['bundle_id'], 'version': m['version'], 'content_digest': d}:
                raise WCEError('OWN_STATE_CORRUPT')
        local_adoption = ((body_followup is not None and body_followup['action'] == 'ADOPT_OBSERVATION_ONLY')
            or (body_attempt is not None and body_attempt['action'] == 'ADOPT_FINAL_OBSERVATION_ONLY'))
        binding_validate(body['binding'])
        delegated = body.get('delegated')
        if delegated is not None:
            from .own_connection_workflow import validate_delegated
            validate_delegated(db, m, delegated)
        if active:
            if delegated is not None:
                self._validate_delegation(delegated['policy'])
            if draft_recovery is not None:
                from .own_body_recovery import code_scope
                if not allow_draft_read or draft_recovery['candidate_scope'] != code_scope():
                    raise WCEError('OWN_APPROVAL_UNAVAILABLE')
            if local_adoption and not allow_local_adoption:
                raise WCEError('OWN_APPROVAL_UNAVAILABLE')
            if body_attempt is not None:
                from .own_body_recovery import code_scope
                if body_attempt['candidate_scope'] != code_scope():
                    raise WCEError('OWN_RECOVERY_CANDIDATE_CHANGED')
            if body_followup is not None:
                from .own_body_recovery import code_scope
                if body_followup['candidate_scope'] != code_scope():
                    raise WCEError('OWN_RECOVERY_CANDIDATE_CHANGED')
            if body_recovery is not None:
                from .own_body_recovery import code_scope
                if body_recovery['candidate_scope'] != code_scope():
                    raise WCEError('OWN_RECOVERY_CANDIDATE_CHANGED')
            if (row['cancelled'] or row['expires'] <= self.clock() or row['binding_fence'] != p.fence()
                    or body != self._approval_body(p, m, d, row['expires'], recovery_policy, body_recovery, body_followup, body_attempt, draft_recovery, delegated)):
                raise WCEError('OWN_APPROVAL_UNAVAILABLE')
        elif (body['binding'] != m['binding'] or body['fence'] != row['binding_fence']
                or body['bundle_id'] != m['bundle_id'] or body['version'] != m['version']
                or body['content_digest'] != d or body['slots'] != m['assets'] or body['apis'] != ([] if local_adoption else list(DRAFT_READ_APIS) if draft_recovery is not None else list(APIS))
                or body['expires'] != row['expires']):
            raise WCEError('OWN_STATE_CORRUPT')
        return row

