"""Default-denied own account workflow with durable once-only admissions.

The remote write and business commit are separate. Recovery never sends again.
Trusted setup, proof and trial approval have no model-facing management route.
"""
import json
import time
import threading
from dataclasses import dataclass
from uuid import uuid4

from .contracts import Actor, WCEError
from .bounded_file import identity
from .http_transport import HTTPSender
from .local_preparation import image_check, sha
from .own_auth import (APIS, READ_APIS, DRAFT_READ_APIS, KINDS, OwnProfile, OwnRegistry, OwnTokenScope,
                       ScopedOwnTokenBroker, finite, require_evidence, validate_profile)
from .own_contracts import SPECS, validate
from .own_store import OwnStore
from . import own_wire as wire
from . import documents
from .prepared_contracts import DIGEST, ID, strict_validate, schema
from . import own_group_json
from .prepared_host import ScopedImageDirectory, _path
from .service import canonical, digest
from .own_prepared_history import (PreparedHistoryValidation, encoded, stored, binding_validate)






def roundtrip(value):
    """Use exactly the durable reader before admission, not an estimated budget."""
    try:
        return stored(encoded(value), digest(value))
    except WCEError:
        raise WCEError('DOCUMENT_PERSISTENCE_LIMIT') from None


def projection(manifest, mappings):
    return (documents.render_projection(manifest['document'], mappings) if manifest['schema'] in (2, 3)
            else wire.render(manifest['article'], mappings))


def _defaults_projection(base, metadata, binding):
    """Only an explicitly schema2 add/approved schema3 caller may opt in."""
    from .own_draft_defaults import validate_defaults_metadata, apply_comment_settings
    count = len(base['articles']) if 'articles' in base else 1
    checked = validate_defaults_metadata(metadata, expected_binding_sha=digest(binding), article_count=count)
    return apply_comment_settings(base, checked)


def _body_projection(intent):
    """Detached old projection for body-only parsers; never mutate history."""
    projected = json.loads(canonical(intent['projection']))
    if intent['schema'] == 2:
        rows = projected['articles'] if 'articles' in projected else [projected]
        for article in rows:
            del article['need_open_comment']
            del article['only_fans_can_comment']
    return projected


def _metadata_editorial(metadata, rows=()):
    by_index = {row['index']: dict(row) for row in rows}
    return [by_index.get(i, {'index': i}) | {
        'originality': by_index.get(i, {}).get('originality', 'NOT_SUBMITTED_NO_SUPPORTED_OFFICIAL_PATH'),
        'auto_feature': 'NOT_SUBMITTED_PENDING_PLATFORM_SUPPORT',
        'comment_intent': dict(metadata['comment_settings'])}
        for i in range(metadata['article_count'])]




def check_transmission_size(size):
    """Current policy for a new transmission, separate from historical parsing."""
    if type(size) is not int or not 0 < size < 1000000:
        raise WCEError('OWN_IMAGE_LIMIT')


@dataclass(frozen=True)
class _PrepareCandidate:
    """Canonical local preparation values, never permission or Group proof."""
    request_key: str
    parameters_json: str
    parameters_digest: str
    manifest_json: str
    content_digest: str

    @property
    def manifest(self):
        return _prepare_candidate_values(self)[1]

    @property
    def selector(self):
        manifest = self.manifest
        return {'bundle_id': manifest['bundle_id'], 'version': manifest['version'],
                'content_digest': self.content_digest}


def _prepare_candidate_snapshot(candidate):
    if type(candidate) is not _PrepareCandidate:
        raise WCEError('OWN_PREPARE_CANDIDATE_CHANGED')
    snapshot = _PrepareCandidate(candidate.request_key, candidate.parameters_json,
        candidate.parameters_digest, candidate.manifest_json, candidate.content_digest)
    if any(type(value) is not str for value in vars(snapshot).values()):
        raise WCEError('OWN_PREPARE_CANDIDATE_CHANGED')
    return snapshot


def _prepare_candidate_values(candidate):
    candidate = _prepare_candidate_snapshot(candidate)
    strict_validate(candidate.request_key, ID)
    strict_validate(candidate.parameters_digest, DIGEST)
    strict_validate(candidate.content_digest, DIGEST)
    parameters = stored(candidate.parameters_json, candidate.parameters_digest)
    manifest = stored(candidate.manifest_json, candidate.content_digest)
    if (type(manifest) is not dict or type(manifest.get('schema')) is not int
            or manifest['schema'] not in (1, 2, 3)
            or set(manifest) != {'schema', 'binding', 'bundle_id', 'version', 'revision',
                'document' if manifest['schema'] in (2, 3) else 'article', 'assets'}
            or type(manifest['revision']) is not int or manifest['revision'] < 1
            or encoded(parameters) != candidate.parameters_json or encoded(manifest) != candidate.manifest_json):
        raise WCEError('OWN_PREPARE_CANDIDATE_CHANGED')
    binding_validate(manifest['binding'])
    strict_validate(manifest['bundle_id'], SPECS['own.articles.read']['properties']['bundle_id'])
    strict_validate(manifest['version'], SPECS['own.articles.read']['properties']['version'])
    return parameters, manifest


def coordinated_write(method):
    """Serialize direct approved draft/recovery writes with publication."""
    from functools import wraps
    @wraps(method)
    def invoke(self, actor, connection_id, *args, **kwargs):
        from .publication_lock import draft_writer
        profile = self._profile(actor, connection_id, 'local.write')
        with draft_writer(self.db.path.parent, profile.account_id):
            return method(self, actor, connection_id, *args, **kwargs)
    return invoke


class OwnWorkflow(PreparedHistoryValidation):
    def body_attempt_snapshot(self, actor, connection_id, selector, request_key, draft_request_key,
                              action='SEND_FINAL_ATTEMPT4'):
        p = self._profile(actor, connection_id, 'local.write')
        from .own_body_attempt import snapshot
        with _history_transaction(self.db) as (db, history_locators):
            self._resource(db, p, history_locators=history_locators)
            return snapshot(self, db, p, selector, request_key, draft_request_key, action, history_locators=history_locators)

    @coordinated_write
    def execute_body_attempt(self, actor, connection_id, approval_id):
        p = self._profile(actor, connection_id, 'local.write')
        from .own_body_attempt import execute
        return execute(self, p, self._lease(p), approval_id)

    @coordinated_write
    def adopt_final_body_observation(self, actor, connection_id, approval_id, local_guard=None):
        p = self._profile(actor, connection_id, 'local.write')
        from .own_body_attempt import adopt
        return adopt(self, p, approval_id, local_guard)

    def body_followup_snapshot(self, actor, connection_id, selector, request_key, action='SEND_ONCE'):
        p = self._profile(actor, connection_id, 'local.write')
        from .own_body_followup import snapshot
        with _history_transaction(self.db) as (db, history_locators):
            self._resource(db, p, history_locators=history_locators)
            return snapshot(self, db, p, selector, request_key, action, history_locators=history_locators)

    @coordinated_write
    def execute_body_followup(self, actor, connection_id, approval_id):
        p = self._profile(actor, connection_id, 'local.write')
        from .own_body_followup import execute
        return execute(self, p, self._lease(p), approval_id)

    @coordinated_write
    def adopt_body_observation(self, actor, connection_id, approval_id, local_guard=None):
        p = self._profile(actor, connection_id, 'local.write')
        from .own_body_followup import adopt
        return adopt(self, p, approval_id, local_guard)

    def body_recovery_snapshot(self, actor, connection_id, selector, request_key):
        p = self._profile(actor, connection_id, 'local.write')
        from .own_body_recovery import snapshot
        with _history_transaction(self.db) as (db, history_locators):
            self._resource(db, p, history_locators=history_locators)
            return snapshot(self, db, p, selector, request_key, history_locators=history_locators)

    @coordinated_write
    def execute_body_recovery(self, actor, connection_id, approval_id):
        p = self._profile(actor, connection_id, 'local.write')
        from .own_body_recovery import execute
        return execute(self, p, self._lease(p), approval_id)

    def body_recovery_status(self, actor, connection_id, original_request_key):
        p = self._profile(actor, connection_id)
        from .own_body_recovery import view
        with _history_transaction(self.db) as (db, history_locators):
            self._resource(db, p, history_locators=history_locators)
            original = self._history(db, p, original_request_key, history_locators=history_locators)
            if original is None:
                raise WCEError('OWN_STEP_NOT_FOUND')
            row = db.execute('SELECT * FROM own_body_recoveries WHERE original_step_id=?', (original['id'],)).fetchone()
            if row is None:
                raise WCEError('OWN_BODY_RECOVERY_UNAVAILABLE')
            return view(self, db, p, row, history_locators=history_locators)

    def __init__(self, path=None, registry=None, broker=None, sender=None, image_directory=None, clock=time.time, *, physical_resources=None):
        if registry is not None and type(registry) is not OwnRegistry:
            raise WCEError('OWN_UNCONFIGURED')
        if broker is not None and type(broker) is not ScopedOwnTokenBroker:
            raise WCEError('OWN_UNCONFIGURED')
        if image_directory is not None and type(image_directory) is not ScopedImageDirectory:
            raise WCEError('OWN_UNCONFIGURED')
        self._preview_lock, self._preview_server = threading.RLock(), None
        self.registry, self.broker, self.clock = registry, broker, clock
        self.sender = sender if sender is not None else HTTPSender()
        self.image_directory, self.db = image_directory, None
        if path is not None and registry is not None and registry.profiles:
            profiles = [validate_profile(p, clock()) for p in registry.profiles.values()]
            kinds = {p.source_kind for p in profiles}
            if len(kinds) != 1:
                raise WCEError('OWN_PROVENANCE_MISMATCH')
            self.db = OwnStore(path, next(iter(kinds)), history_policy=getattr(self, "policy", None), **({} if physical_resources is None else {"physical_resources":physical_resources}))
            # Retain the workflow's original state directory identity for later
            # descriptor-relative recovery evidence and admission writes.
            self.state_root_identity = identity(self.db.path.parent.lstat())
            with self.db.transaction(write=True) as db:
                for p in profiles:
                    row = db.execute('SELECT * FROM own_resources WHERE tenant=? AND (resource=? OR account=?)',
                                     (p.actor.tenant_id, p.resource_id, p.account_id)).fetchall()
                    if not row:
                        db.execute('INSERT INTO own_resources VALUES(?,?,?,?)',
                                   (p.actor.tenant_id, p.account_id, p.resource_id, p.source_kind))
                    elif len(row) != 1 or any(row[0][k] != v for k, v in (
                            ('account', p.account_id), ('resource', p.resource_id), ('source_kind', p.source_kind))):
                        raise WCEError('OWN_RESOURCE_MISMATCH')

    def evidence(self):
        return {'runtime': 'own_account_adapter_preparation', 'platform_ready': False,
                'platform_verified': False, 'connected': False}

    def _profile(self, actor, connection, action='local.read', expected=None):
        if self.registry is None or self.db is None:
            raise WCEError('OWN_UNCONFIGURED')
        p = validate_profile(self.registry.resolve(actor, connection), self.clock())
        if action not in p.granted_actions:
            raise WCEError('OWN_ACCESS_DENIED')
        if expected is not None and p.fence() != expected.fence():
            raise WCEError('OWN_AUTHORIZATION_CHANGED')
        return p

    def _resource(self, db, p, *, history_locators=None):
        from .own_connection_policy import ConnectionPolicy
        policy = getattr(self.db, 'history_policy', None)
        if type(policy) is ConnectionPolicy and policy.value.get('schema') == 2:
            from .draft_group_history_context import require_history
            require_history(policy, db, history_locators)
        OwnStore.check(db, p.source_kind, getattr(self.db, 'history_policy', None), history=history_locators)
        self._resource_identity(db, p)

    def _resource_identity(self, db, p):
        row = db.execute('SELECT * FROM own_resources WHERE tenant=? AND resource=?',
                         (p.actor.tenant_id, p.resource_id)).fetchone()
        if row is None or row['account'] != p.account_id or row['source_kind'] != p.source_kind:
            raise WCEError('OWN_RESOURCE_MISMATCH')
        config = db.execute('SELECT source_kind FROM own_config WHERE id=1').fetchone()
        if config is None or config[0] != p.source_kind:
            raise WCEError('OWN_PROVENANCE_MISMATCH')

    def _lease(self, p):
        if self.broker is None:
            raise WCEError('OWN_TOKEN_UNAVAILABLE')
        return self.broker.load(OwnTokenScope.from_profile(p))

    def _current(self, p, lease, action='local.read'):
        self._profile(p.actor, p.connection_id, action, p)
        if not self.broker.current(OwnTokenScope.from_profile(p), lease):
            raise WCEError('OWN_TOKEN_UNAVAILABLE')

    def _network(self, p, lease, action, write=False, read_attempt=False):
        self._current(p, lease, action)
        if read_attempt and (action not in READ_APIS + DRAFT_READ_APIS or write):
            raise WCEError('OWN_ACCESS_DENIED')
        # Only the pinned, human-reviewed host recovery uses this attempt grant.
        # It does not assert that the two new platform permissions were verified.
        needed = {'qualification', 'egress', 'quota', 'token_route'}
        if not read_attempt:
            needed.add(action)
        if write:
            needed |= set(APIS) | {'news_schema_resolution'}
        require_evidence(p, needed, self.clock())
        if p.source_kind == 'SYNTHETIC_SETUP':
            if getattr(self.sender, 'mode', None) != 'SYNTHETIC_OWN_WIRE' or type(self.sender) is HTTPSender:
                raise WCEError('OWN_PROVENANCE_MISMATCH')
        elif type(self.sender) is not HTTPSender or not self.sender.enabled:
            raise WCEError('OWN_HTTP_DISABLED')








    def _input(self, db, p, kind, key, parameters, result):
        if 'document' in parameters:
            roundtrip(parameters); roundtrip(result)
        db.execute('INSERT INTO own_inputs VALUES(?,?,?,?,?,?,?,?,?,?)',
                   ('own-input-' + uuid4().hex,) + self._scope(p) + (kind, key, encoded(parameters),
                    digest(parameters), encoded(result), digest(result)))
        return self._old_input(db, p, kind, key, parameters)

    def _receive(self, p, lease, a):
        if a['declared_type'] not in {'image/png', 'image/jpeg'}:
            raise WCEError('UNSUPPORTED_IMAGE_FORMAT')
        _path(a['relative_path'])
        parameters = {'path_digest': sha(a['relative_path'].encode()), 'role': a['role'], 'mime': a['declared_type']}
        with _history_transaction(self.db) as (db, history_locators):
            self._resource(db, p, history_locators=history_locators)
            old = self._old_input(db, p, 'asset', a['request_key'], parameters)
        if old is not None:
            return old
        self._current(p, lease, 'local.write')
        if type(self.image_directory) is not ScopedImageDirectory:
            raise WCEError('SOURCE_UNCONFIGURED')
        data = self.image_directory.read(p.actor, p.connection_id, p.resource_id, a['relative_path'])
        if type(data) is not bytes or not 0 < len(data) <= 2097152:
            raise WCEError('OWN_IMAGE_LIMIT')
        image_check(data, a['declared_type'])
        meta = {'asset_ref': 'own-asset-' + uuid4().hex, 'role': a['role'],
                'declared_type': a['declared_type'], 'size': len(data), 'sha256': sha(data)}
        with _history_transaction(self.db, write=True) as (db, history_locators):
            self._resource(db, p, history_locators=history_locators); self._current(p, lease, 'local.write')
            old = self._old_input(db, p, 'asset', a['request_key'], parameters)
            if old is not None:
                return old
            from .draft_group_store import check_account_writer
            check_account_writer(db, history_locators=history_locators)
            db.execute('INSERT INTO own_assets VALUES(?,?,?,?,?,?,?)', (meta['asset_ref'], encoded(p.binding()),
                meta['role'], meta['declared_type'], meta['size'], meta['sha256'], data))
            result = self._input(db, p, 'asset', a['request_key'], parameters, meta)
            self._current(p, lease, 'local.write')
        return result

    def _prepare_content_in(self, db, p, a, parameters):
        """Original content checks only; no admission or SQL write authority."""
        is_document = 'document' in a
        document = documents.normalize(a['document']) if is_document else None
        if is_document:
            roundtrip(parameters)
        assets = self._document_content(db, p.binding(), document) if is_document else self._content(db, p.binding(), a['article'])
        return is_document, document, assets

    def _prepare_manifest_from_content_in(self, db, p, a, parameters, is_document, document, assets, *, identity=None):
        """Original identity/manifest tail; fixed callers own transmission checks."""
        if identity is None:
            bundle, revision = a.get('bundle_id', 'own-bundle-' + uuid4().hex), 1
        else:
            bundle, revision = identity[0], 1
            if 'bundle_id' in a and a['bundle_id'] != bundle:
                raise WCEError('OWN_PREPARE_CANDIDATE_CHANGED')
        if 'bundle_id' in a:
            row = db.execute('SELECT version,revision FROM own_articles WHERE bundle=? ORDER BY revision DESC LIMIT 1', (bundle,)).fetchone()
            if row is None or row['version'] != a['expected_version']:
                raise WCEError('OWN_VERSION_CONFLICT')
            old_manifest, _ = self._bundle(db, p, bundle, row['version'])
            if old_manifest['schema'] != (document['format'] if is_document else 1):
                raise WCEError('DOCUMENT_FORMAT_CONFLICT')
            if is_document and old_manifest['document'].get('policy') != document.get('policy'):
                raise WCEError('DOCUMENT_FORMAT_CONFLICT')
            revision = row['revision'] + 1
        version = 'own-version-' + uuid4().hex if identity is None else identity[1]
        m = {'schema': document['format'] if is_document else 1, 'binding': p.binding(), 'bundle_id': bundle, 'version': version,
             'revision': revision, ('document' if is_document else 'article'): document if is_document else a['article'], 'assets': assets}
        if is_document:
            roundtrip(m)
        if len(encoded(m).encode()) > own_group_json.limit(m):
            raise WCEError('OWN_INVALID_ARTICLE')
        candidate = _PrepareCandidate(a['request_key'], encoded(parameters), digest(parameters),
                                      encoded(m), digest(m))
        return m, candidate

    def _prepare_manifest_candidate_in(self, db, p, a, parameters, *, identity=None):
        """Original ordinary path: content, strict transmission, identity tail."""
        is_document, document, assets = self._prepare_content_in(db, p, a, parameters)
        # New admissions obey the current transmission policy; historic
        # manifests and exact input-cache reads retain their original checks.
        for asset in assets:
            check_transmission_size(asset['size'])
        return self._prepare_manifest_from_content_in(db, p, a, parameters,
            is_document, document, assets, identity=identity)

    def _prepare_candidate_in(self, db, p, lease, a, *, history_locators=None):
        """Read-only candidate entry; never writes/commits or opens a transaction.

        End this RO transaction before fsyncing any future host reservation or
        capsule. A returned cached result does not retroactively mark a Group.
        """
        if db.in_transaction is not True:
            raise WCEError('OWN_PREPARE_CANDIDATE_TRANSACTION')
        validate('own.documents.prepare' if 'document' in a else 'own.articles.prepare', a)
        parameters = {k: v for k, v in a.items() if k not in {'connection_id', 'request_key'}}
        self._resource(db, p, history_locators=history_locators)
        old = self._old_input(db, p, 'prepare', a['request_key'], parameters)
        if old is not None:
            return old, None
        self._current(p, lease, 'local.write')
        _, candidate = self._prepare_manifest_candidate_in(db, p, a, parameters)
        return None, candidate

    def _commit_prepare_candidate_in(self, db, p, lease, a, candidate, *, history_locators=None):
        """Revalidate + insert in the caller's short write transaction.

        No file fsync, implicit transaction, commit, grant or writer exception.
        Caller must verify its own pre-SQL durable reservation/capsule pins.
        """
        if db.in_transaction is not True or db.execute('PRAGMA query_only').fetchone()[0] != 0:
            raise WCEError('OWN_PREPARE_CANDIDATE_TRANSACTION')
        validate('own.documents.prepare' if 'document' in a else 'own.articles.prepare', a)
        expected = _prepare_candidate_snapshot(candidate)
        _prepare_candidate_values(expected)
        parameters = {k: v for k, v in a.items() if k not in {'connection_id', 'request_key'}}
        return self._prepare_in(db, p, lease, a, parameters, expected=expected, history_locators=history_locators)

    def _prepare(self, p, lease, a):
        parameters = {k: v for k, v in a.items() if k not in {'connection_id', 'request_key'}}
        with _history_transaction(self.db, write=True) as (db, history_locators):
            return self._prepare_in(db, p, lease, a, parameters, history_locators=history_locators)

    def _prepare_in(self, db, p, lease, a, parameters, *, expected=None, history_locators=None):
        self._resource(db, p, history_locators=history_locators)
        old = self._old_input(db, p, 'prepare', a['request_key'], parameters)
        if old is not None:
            if expected is not None:
                _, manifest = _prepare_candidate_values(expected)
                actual, _ = self._bundle(db, p, old['bundle_id'], old['version'])
                if (expected.request_key != a['request_key'] or expected.parameters_json != encoded(parameters)
                        or expected.manifest_json != encoded(actual)
                        or expected.content_digest != old['content_digest']
                        or manifest['bundle_id'] != old['bundle_id'] or manifest['version'] != old['version']):
                    raise WCEError('OWN_PREPARE_CANDIDATE_CHANGED')
            return old
        self._current(p, lease, 'local.write')
        identity = None
        if expected is not None:
            _, manifest = _prepare_candidate_values(expected)
            identity = manifest['bundle_id'], manifest['version']
        m, candidate = self._prepare_manifest_candidate_in(db, p, a, parameters, identity=identity)
        if expected is not None:
            if (candidate.request_key != expected.request_key or candidate.parameters_json != expected.parameters_json
                    or candidate.parameters_digest != expected.parameters_digest or candidate.manifest_json != expected.manifest_json
                    or candidate.content_digest != expected.content_digest):
                raise WCEError('OWN_PREPARE_CANDIDATE_CHANGED')
            if (db.execute('SELECT 1 FROM own_articles WHERE version=?', (m['version'],)).fetchone() is not None
                    or ('bundle_id' not in a and db.execute('SELECT 1 FROM own_articles WHERE bundle=?',
                                                           (m['bundle_id'],)).fetchone() is not None)):
                raise WCEError('OWN_PREPARE_CANDIDATE_CHANGED')
        from .draft_group_store import check_account_writer
        check_account_writer(db, history_locators=history_locators)
        return self._insert_prepare_records_in(db, p, lease, a, parameters, m)

    def _insert_prepare_records_in(self, db, p, lease, a, parameters, m):
        """Original insertion tail, no resource reentry, BEGIN, commit or fsync.

        Internal use only after the fixed caller's full checks. It creates no
        Group designation, current scope, upload success or send ownership.
        """
        db.execute('INSERT INTO own_articles VALUES(?,?,?,?,?,?)',
                   (m['version'], m['bundle_id'], m['revision'], encoded(p.binding()), encoded(m), digest(m)))
        self._register_article(db, m)
        result = self._input(db, p, 'prepare', a['request_key'], parameters,
            {'bundle_id': m['bundle_id'], 'version': m['version'], 'revision': m['revision'], 'content_digest': digest(m)})
        self._current(p, lease, 'local.write')
        return result

    def _register_article(self, db, manifest):
        if db.execute('PRAGMA user_version').fetchone()[0] in (5, 6, 7, 8, 9):
            from .own_lineage import register
            register(db, manifest, legacy=True)

    def _validate_delegation(self, value):
        raise WCEError('OWN_DELEGATION_UNAVAILABLE')

    @staticmethod
    def _approval_body(p, m, d, expires, recovery_policy=None, body_recovery=None, body_followup=None, body_attempt=None, draft_recovery=None, delegated=None):
        body = {'schema': 1, 'binding': p.binding(), 'fence': p.fence(), 'bundle_id': m['bundle_id'],
                'version': m['version'], 'content_digest': d, 'slots': m['assets'],
                'apis': list(APIS), 'expires': expires}
        if recovery_policy is not None:
            from .own_png import validate_binding
            body.update(schema=2, recovery_policy=validate_binding(recovery_policy))
        if body_recovery is not None:
            if recovery_policy is not None:
                raise WCEError('OWN_APPROVAL_UNAVAILABLE')
            body.update(schema=3, body_recovery=body_recovery)
        if body_followup is not None:
            if recovery_policy is not None or body_recovery is not None:
                raise WCEError('OWN_APPROVAL_UNAVAILABLE')
            body.update(schema=4, body_followup=body_followup)
            if body_followup['action'] == 'ADOPT_OBSERVATION_ONLY':
                body['apis'] = []
        if body_attempt is not None:
            if any(v is not None for v in (recovery_policy, body_recovery, body_followup)):
                raise WCEError('OWN_APPROVAL_UNAVAILABLE')
            body.update(schema=5, body_attempt=body_attempt)
            if body_attempt['action'] == 'ADOPT_FINAL_OBSERVATION_ONLY':
                body['apis'] = []
        if draft_recovery is not None:
            if any(v is not None for v in (recovery_policy, body_recovery, body_followup, body_attempt)):
                raise WCEError('OWN_APPROVAL_UNAVAILABLE')
            body.update(schema=6, draft_recovery=draft_recovery, apis=list(DRAFT_READ_APIS))
        if delegated is not None:
            if any(v is not None for v in (recovery_policy, body_recovery, body_followup, body_attempt, draft_recovery)):
                raise WCEError('OWN_APPROVAL_UNAVAILABLE')
            body.update(schema=7, delegated=delegated)
        from .normal_html_limits import POLICY as NORMAL_POLICY
        if m.get('document',{}).get('policy') == NORMAL_POLICY:
            body['normal_html_policy'] = NORMAL_POLICY
        if m['schema'] in (2, 3):
            if any(v is not None for v in (recovery_policy, body_recovery, body_followup, body_attempt, draft_recovery)):
                raise WCEError('DOCUMENT_RECOVERY_UNSUPPORTED')
            roundtrip(body)
        return body

    @coordinated_write
    def authorize_trial(self, actor, connection_id, bundle_id, version, content_digest, expires_at, *, recovery_policy=None, body_recovery=None, body_followup=None, body_attempt=None, draft_recovery=None, delegated=None):
        """Trusted operator only. There is no corresponding model or CLI tool."""
        p = self._profile(actor, connection_id, 'local.write')
        if not finite(expires_at) or not self.clock() < expires_at <= min(
                p.expires, p.session_expires, p.grant_expires, p.credential_expires):
            raise WCEError('OWN_APPROVAL_UNAVAILABLE')
        with _history_transaction(self.db, write=True) as (db, history_locators):
            identifier = self._authorize_trial_in(db, p, actor, connection_id, bundle_id, version, content_digest, expires_at,
                recovery_policy=recovery_policy, body_recovery=body_recovery, body_followup=body_followup,
                body_attempt=body_attempt, draft_recovery=draft_recovery, delegated=delegated, history_locators=history_locators)
        return identifier

    def _authorize_trial_in(self, db, p, actor, connection_id, bundle_id, version, content_digest, expires_at, *, recovery_policy=None, body_recovery=None, body_followup=None, body_attempt=None, draft_recovery=None, delegated=None, history_locators=None):
        """Original SQL block; caller retains profile/expiry and transaction boundary.

        This is not a Group qualifier, skip flag, or network permission. The
        existing account writer barrier remains mandatory.
        """
        body, identifier, d = self._prepare_trial_approval_in(db, p, actor, connection_id,
            bundle_id, version, content_digest, expires_at, recovery_policy=recovery_policy,
            body_recovery=body_recovery, body_followup=body_followup, body_attempt=body_attempt,
            draft_recovery=draft_recovery, delegated=delegated, history_locators=history_locators)
        from .draft_group_store import check_account_writer
        check_account_writer(db, history_locators=history_locators)
        return self._insert_trial_approval_in(db, p, actor, connection_id, d,
            expires_at, body, identifier)

    def _prepare_trial_approval_in(self, db, p, actor, connection_id, bundle_id, version, content_digest, expires_at, *, recovery_policy=None, body_recovery=None, body_followup=None, body_attempt=None, draft_recovery=None, delegated=None, history_locators=None):
        """Original validation/body prefix; neither insert nor writer permission."""
        self._resource(db, p, history_locators=history_locators)
        m, d = self._bundle(db, p, bundle_id, version)
        if d != content_digest:
            raise WCEError('OWN_SNAPSHOT_CHANGED')
        from .draft_group_target_uploads import guard_target_approval_in
        guard_target_approval_in(self,db,p,m)
        if recovery_policy is not None:
            from .own_png import validate_binding, recovery_binding
            validate_binding(recovery_policy)
            selector = {'bundle_id': bundle_id, 'version': version, 'content_digest': d}
            original = self._history(db, p, recovery_policy['request_key'], 'cover', selector, 'cover', history_locators=history_locators)
            intent, result = self._step(db, p, original, history_locators=history_locators)
            if (original['state'] != 'RESULT_UNKNOWN' or result
                    or recovery_policy != recovery_binding(original, intent)):
                raise WCEError('OWN_APPROVAL_UNAVAILABLE')
        if body_recovery is not None:
            from .own_body_recovery import snapshot
            selector = {'bundle_id': bundle_id, 'version': version, 'content_digest': d}
            if body_recovery != snapshot(self, db, p, selector, body_recovery.get('original_request_key'), history_locators=history_locators):
                raise WCEError('OWN_APPROVAL_UNAVAILABLE')
        if body_followup is not None:
            from .own_body_followup import snapshot
            selector = {'bundle_id': bundle_id, 'version': version, 'content_digest': d}
            if body_followup != snapshot(self, db, p, selector,
                    body_followup.get('original_request_key'), body_followup.get('action'), history_locators=history_locators):
                raise WCEError('OWN_APPROVAL_UNAVAILABLE')
        if body_attempt is not None:
            from .own_body_attempt import snapshot
            selector = {'bundle_id': bundle_id, 'version': version, 'content_digest': d}
            if body_attempt != snapshot(self, db, p, selector, body_attempt.get('original_request_key'),
                    body_attempt.get('draft_request_key'), body_attempt.get('action'), history_locators=history_locators):
                raise WCEError('OWN_APPROVAL_UNAVAILABLE')
        if draft_recovery is not None:
            from .own_draft_reconcile import snapshot
            selector = {'bundle_id': bundle_id, 'version': version, 'content_digest': d}
            if draft_recovery != snapshot(self, db, p, selector, draft_recovery['original']['request_key'], history_locators=history_locators):
                raise WCEError('OWN_APPROVAL_UNAVAILABLE')
        if delegated is not None:
            from .own_connection_workflow import validate_delegated
            validate_delegated(db, m, delegated)
            self._validate_delegation(delegated['policy'])
        body = self._approval_body(p, m, d, expires_at, recovery_policy, body_recovery, body_followup, body_attempt, draft_recovery, delegated)
        identifier = 'own-approval-' + uuid4().hex
        return body, identifier, d

    def _insert_trial_approval_in(self, db, p, actor, connection_id, d, expires_at, body, identifier):
        """Original insert tail; fixed callers must first prove writer admission."""
        db.execute('INSERT INTO own_approvals VALUES(?,?,?,?,?,?,?,?,?,?,0)', (identifier,) + self._scope(p)
            + (p.resource_id, p.fence(), d, encoded(body), digest(body), expires_at))
        self._profile(actor, connection_id, 'local.write', p)
        return identifier


    def cancel_trial(self, approval_id):
        with self.db.transaction(write=True) as db:
            db.execute('UPDATE own_approvals SET cancelled=1 WHERE id=?', (approval_id,))


    @staticmethod
    def _target(p, d, operation, slot):
        return digest({'tenant': p.actor.tenant_id, 'resource': p.resource_id,
                       'manifest_digest': d, 'operation': operation, 'slot': slot})

    def _step(self, db, p, row, *, history_locators=None):
        from .own_connection_policy import ConnectionPolicy
        policy = getattr(self.db, 'history_policy', None)
        if type(policy) is ConnectionPolicy and policy.value.get('schema') == 2:
            from .draft_group_history_context import require_history
            require_history(policy, db, history_locators)
        from .own_step_history import validate_step_in
        return validate_step_in(self, db, p, row, history_locators=history_locators)

    def _uploads(self, db, p, m, d, *, history_locators=None):
        from .draft_group_target_uploads import resolve_target_uploads_in
        reused = resolve_target_uploads_in(self, db, p, m, d, history_locators=history_locators)
        if reused is not None:
            return reused
        mappings, snapshots = {}, []
        for asset in m['assets']:
            op = 'cover' if asset['role'] == 'cover' else 'body'
            row = db.execute('SELECT * FROM own_steps WHERE target=?', (self._target(p, d, op, asset['slot']),)).fetchone()
            if row is not None and row['state'] == 'RESULT_UNKNOWN' and op == 'body':
                from .own_lineage_replacement import mapping as new_mapping
                replacement = new_mapping(self, db, p, row, history_locators=history_locators)
                if replacement is None:
                    from .own_body_recovery import mapping
                    replacement = mapping(self, db, p, row, history_locators=history_locators)
                if replacement is not None:
                    mappings[asset['slot']], snapshot = replacement
                    snapshots.append(snapshot)
                    continue
            if row is None or row['state'] != 'SUCCEEDED':
                raise WCEError('OWN_UPLOADS_INCOMPLETE')
            _, result = self._step(db, p, row, history_locators=history_locators)
            mappings[asset['slot']] = result
            snapshots.append({k: row[k] for k in ('id', 'intent_digest', 'target', 'result_digest')})
        return mappings, snapshots

    def _view(self, p, row):
        with _history_transaction(self.db) as (db, history_locators):
            self._resource(db, p, history_locators=history_locators)
            latest = db.execute('SELECT * FROM own_steps WHERE id=?', (row['id'],)).fetchone()
            intent, result = self._step(db, p, latest, history_locators=history_locators)
            editorial = []
            if latest['operation'] == 'add' and 'articles' in intent['projection']:
                manifest, _ = self._bundle(db, p, intent['selector']['bundle_id'], intent['selector']['version'])
                from .editor_contracts import checks
                editorial = checks(manifest['document'])
            from .own_diagnostics import read
            diagnostic = read(db, latest)
            lineage_replacement = None
            if latest['operation'] == 'body' and db.execute('PRAGMA user_version').fetchone()[0] in (6, 7, 8, 9):
                from .own_lineage_replacement import view as lineage_replacement_view
                lineage_replacement = lineage_replacement_view(self, db, p, latest, history_locators=history_locators)
            replacement = None
            followup = None
            terminal_attempt = None
            if latest['operation'] == 'body':
                r = db.execute('SELECT * FROM own_body_recoveries WHERE original_step_id=?', (latest['id'],)).fetchone()
                if r is not None:
                    from .own_body_recovery import view
                    replacement = view(self, db, p, r, history_locators=history_locators)
                f = db.execute('SELECT * FROM own_body_followups WHERE original_step_id=?', (latest['id'],)).fetchone()
                if f is not None:
                    from .own_body_followup import view as followup_view
                    followup = followup_view(self, db, p, f, history_locators=history_locators)
                t = db.execute('SELECT * FROM own_body_attempts WHERE original_step_id=?', (latest['id'],)).fetchone()
                if t is not None:
                    from .own_body_attempt import view as attempt_view
                    terminal_attempt = attempt_view(self, db, p, t, history_locators=history_locators)
        value = {'attempt_id': latest['id'], 'request_key': latest['request_key'], 'state': latest['state'],
                'operation': latest['operation'], 'slot': latest['slot'], 'resource_id': p.resource_id,
                'result': result, 'readback_state': latest['readback'],
                'completion_origin': result.get('completion_origin', 'OWN_WRITE_RESPONSE') if latest['state'] == 'SUCCEEDED' else 'UNDETERMINED',
                'provenance': 'SYNTHETIC_OWN_WIRE' if p.source_kind == 'SYNTHETIC_SETUP' else 'OWN_OFFICIAL_WIRE',
                'diagnostic': diagnostic['reason'], 'response_diagnostic': diagnostic}
        if intent['schema'] == 2:
            editorial = _metadata_editorial(intent['article_metadata'], editorial)
        if editorial:
            value['editorial_checks'] = editorial
        return value | ({'lineage_body_replacement': lineage_replacement} if lineage_replacement is not None else {}) | ({'replacement': replacement} if replacement is not None else {}) | ({'followup': followup} if followup is not None else {}) | ({'terminal_attempt': terminal_attempt} if terminal_attempt is not None else {})

    def _history(self, db, p, key, operation=None, selector=None, slot=None, *, history_locators=None):
        row = db.execute('SELECT * FROM own_steps WHERE tenant=? AND principal=? AND connection=? AND request_key=?',
                         self._scope(p) + (key,)).fetchone()
        if row is not None:
            i, _ = self._step(db, p, row, history_locators=history_locators)
            if operation is not None and (operation != row['operation'] or selector != i['selector'] or slot != row['slot']):
                raise WCEError('IDEMPOTENCY_CONFLICT')
        return row

    def _transport_timeout(self, lease):
        return min(10.0, lease.expires_at - self.clock())

    def _send(self, p, lease, request, action, write=False, read_attempt=False):
        self._network(p, lease, action, write, read_attempt)
        timeout = self._transport_timeout(lease)
        if write:
            # Every known business writer caller has already left its admission
            # transaction. Retain the common writer scope, close this short read
            # before HTTP, and do not borrow the SQL-only ADD exception.
            with _history_transaction(self.db) as (db, history_locators):
                self._resource(db, p, history_locators=history_locators)
                from .draft_group_store import check_account_writer
                check_account_writer(db, history_locators=history_locators)
            # The added read may outlive a token/profile/deadline. Preserve the
            # original final dynamic check and compute a fresh live timeout.
            self._network(p, lease, action, write, read_attempt)
            timeout = self._transport_timeout(lease)
        try:
            return self.sender.send(request, timeout)
        except Exception:
            return None  # Never output URL, body, errmsg or exception chain.

    def _check_upload_order_in(self, db, p, m, d, slot, *, history_locators=None):
        slots = {s['slot']: s for s in m['assets']}
        if slot not in slots:
            raise WCEError('OWN_INVALID_SLOT')
        order = [s['slot'] for s in m['assets']]
        for previous in order[:order.index(slot)]:
            prevop = 'cover' if slots[previous]['role'] == 'cover' else 'body'
            r = db.execute('SELECT * FROM own_steps WHERE target=?', (self._target(p, d, prevop, previous),)).fetchone()
            if r is not None and r['state'] == 'RESULT_UNKNOWN' and prevop == 'body':
                from .own_lineage_replacement import mapping as new_mapping
                if new_mapping(self, db, p, r, history_locators=history_locators) is not None:
                    continue  # Exact original slot only, no new grant.
            if r is None or r['state'] != 'SUCCEEDED':
                raise WCEError('OWN_STEP_ORDER')
            self._step(db, p, r, history_locators=history_locators)

    def _admit_step_in(self, db, p, lease, a, *, add, op, slot, action, selector, history_locators=None):
        """Admit within the caller-owned transaction; never send or commit here."""
        self._resource(db, p, history_locators=history_locators)
        if add:
            from .own_body_attempt import check_draft_key
            check_draft_key(db, p, selector, a['request_key'])
        m, d = self._bundle(db, p, a['bundle_id'], a['version'])
        if d != a['content_digest']:
            raise WCEError('OWN_SNAPSHOT_CHANGED')
        target = self._target(p, d, op, slot)
        old = self._history(db, p, a['request_key'], op, selector, slot, history_locators=history_locators)
        old = old if old is not None else db.execute('SELECT * FROM own_steps WHERE target=?', (target,)).fetchone()
        if old is not None:
            self._step(db, p, old, history_locators=history_locators)
            cached = old
        else:
            cached = None
            from .draft_group_target_uploads import guard_target_dispatch_in
            guard_target_dispatch_in(self,db,p,m,op,slot, history_locators=history_locators)
            approval = self._approval(db, p, m, d)
            if add and op == 'add' and slot == 'draft':
                from .draft_group_store import _workflow_add_check
                with _workflow_add_check(db, p.binding(), m):
                    self._write_gate(db, p, m, history_locators=history_locators)
            else:
                self._write_gate(db, p, m, history_locators=history_locators)
            slots = {s['slot']: s for s in m['assets']}
            if add:
                mappings, snapshots = self._uploads(db, p, m, d, history_locators=history_locators)
                projected, asset = projection(m, mappings), None
                approval_body = stored(approval['body'], approval['body_digest'])
                delegated = approval_body.get('delegated', {})
                article_metadata = None
                if delegated.get('schema') == 3:
                    if approval_body['schema'] != 7:
                        raise WCEError('OWN_STATE_CORRUPT')
                    article_metadata = delegated['article_metadata']
                    projected = _defaults_projection(projected, article_metadata, p.binding())
                payload = projected if m['schema'] in (2, 3) else {'articles': [{'article_type': 'news'} | projected]}
                from .html_technical_standard import validate_payload
                # _uploads has authenticated same-account original SUCCEEDED
                # results. Compare full URL strings, never host-name guesses.
                validate_payload(payload, uploaded_image_urls={value['url'] for name,value in mappings.items()
                    if name in slots and slots[name]['role']=='body' and 'url' in value})
                request = wire.encode_draft('add', payload, lease.token)
            else:
                if slot not in slots or (op == 'cover') != (slots[slot]['role'] == 'cover'):
                    raise WCEError('OWN_INVALID_SLOT')
                self._check_upload_order_in(db, p, m, d, slot, history_locators=history_locators)
                asset = slots[slot]
                _, data = self._asset(db, p.binding(), asset['asset_ref'])
                check_transmission_size(len(data))
                request = wire.encode_upload('permanent_cover' if op == 'cover' else 'article_body', asset['declared_type'], data, lease.token)
                projected, snapshots = None, []
            intent = {'schema': 1, 'binding': p.binding(), 'profile_fence': p.fence(), 'selector': selector,
                'operation': op, 'slot': slot, 'asset': asset, 'projection': projected, 'uploads': snapshots,
                'approval_id': approval['id'], 'approval_digest': approval['body_digest']}
            if add and article_metadata is not None:
                intent.update(schema=2, article_metadata=json.loads(canonical(article_metadata)))
            from .normal_html_limits import POLICY as NORMAL_POLICY
            if add and m.get('document',{}).get('policy') == NORMAL_POLICY:
                intent['normal_html_policy'] = NORMAL_POLICY
            if m['schema'] in (2, 3):
                roundtrip(intent)
            self._network(p, lease, action, True)
            identifier, owner = 'own-step-' + uuid4().hex, uuid4().hex
            db.execute('INSERT INTO own_steps(id,tenant,principal,connection,resource,request_key,operation,slot,'
                'manifest_digest,target,approval_id,approval_digest,intent,intent_digest,owner,state,created) '
                'VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)', (identifier,) + self._scope(p) + (p.resource_id,
                a['request_key'], op, slot, d, target, approval['id'], approval['body_digest'], encoded(intent),
                digest(intent), owner, 'RESULT_UNKNOWN', self.clock()))
            row = db.execute('SELECT * FROM own_steps WHERE id=?', (identifier,)).fetchone()
            self._insert_lock(db, p, m, identifier)
            self._step(db, p, row, history_locators=history_locators)
            self._resource(db, p, history_locators=history_locators)
        return ((row, request, None, m, d) if cached is None else
                (cached, None, cached, m, d))

    def _execute(self, p, lease, a, add=False):
        op, slot = ('add', 'draft') if add else ('cover' if a['slot'] == 'cover' else 'body', a['slot'])
        if not add:
            with _history_transaction(self.db) as (db, history_locators):
                self._resource(db, p, history_locators=history_locators)
                selected, _ = self._bundle(db, p, a['bundle_id'], a['version'])
                item = next((s for s in selected['assets'] if s['slot'] == slot), None)
                if item is None:
                    raise WCEError('OWN_INVALID_SLOT')
                op = 'cover' if item['role'] == 'cover' else 'body'
        action = {'cover': APIS[0], 'body': APIS[1], 'add': APIS[2]}[op]
        selector = {k: a[k] for k in ('bundle_id', 'version', 'content_digest')}
        with _history_transaction(self.db) as (db, history_locators):
            self._resource(db, p, history_locators=history_locators)
            if add:
                from .own_body_attempt import check_draft_key
                check_draft_key(db, p, selector, a['request_key'])
            old = self._history(db, p, a['request_key'], op, selector, slot, history_locators=history_locators)
        if old is not None:
            return self._view(p, old)
        with self.db.transaction() as db:
            manifest, _ = self._bundle(db, p, a['bundle_id'], a['version'])
            for asset in manifest['assets']:
                check_transmission_size(asset['size'])
        self._network(p, lease, action, True)
        with _history_transaction(self.db, write=True) as (db, history_locators):
            row, request, cached, m, d = self._admit_step_in(
                db, p, lease, a, add=add, op=op, slot=slot, action=action, selector=selector, history_locators=history_locators)
        if cached is not None:
            return self._view(p, cached)
        return self._execute_postcommit(p, lease, row, request, m, d, action)

    def _execute_postcommit(self, p, lease, row, request, m, d, action):
        """Original current-owner continuation, not a grant or recovery entry.

        Caller retains the original writer/runtime scope and passes the exact
        tuple returned by this stack's committed admission. Future Group use
        still requires its real qualified Gate/link; no exception is added here.
        """
        # Only this stack received a committed owner; recovered rows never enter here.
        self._dispatch_guard(p, lease, row, action)
        dispatch_pin = self._response_dispatch_pin(p, row, request)
        try:
            response = self._send(p, lease, request, action, True)
            reply = self._parse_dispatch_response(p, row, dispatch_pin, response, lease.token)
            archived = self._archive_response(p, row, dispatch_pin, response, reply, lease.token)
            from .own_diagnostics import record
            record(self, row, reply, response)
            self._dispatch_guard(p, lease, row, action, succeeded=archived)
            if reply.result is not None and not archived:
                with _history_transaction(self.db, write=True) as (db, history_locators):
                    self._dispatch_guard_in(db, p, lease, row, action, history_locators=history_locators)
                    from .draft_group_archive_guard import require_ordinary_fallback_in
                    require_ordinary_fallback_in(db, row, history_locators=history_locators)
                    changed = db.execute("UPDATE own_steps SET state='SUCCEEDED',result=?,result_digest=?,completed=? "
                        "WHERE id=? AND owner=? AND state='RESULT_UNKNOWN' AND intent_digest=? AND approval_digest=?",
                        (encoded(reply.result), digest(reply.result), self.clock(), row['id'], row['owner'],
                         row['intent_digest'], row['approval_digest'])).rowcount
                    if changed != 1:
                        raise WCEError('OWN_SNAPSHOT_CHANGED')
                    self._release_lock(db, p, m, row['id'])
                    self._write_gate(db, p, m, row['id'], history_locators=history_locators)
                    self._approval(db, p, m, d, row['approval_id'])
                    self._network(p, lease, action, True)
                # Do not undo a committed success if result release authorization changed.
                self._dispatch_guard(p, lease, row, action, succeeded=True)
            view = self._view(p, row)
            code = view['response_diagnostic'].get('wechat_code')
            if code is not None:
                view |= {'error_code': code, 'credential_update_required': reply.credential_update_required}
            # This stack sent once. Its first release still needs the exact approval;
            # cached historical reads returned above keep their independent read grant.
            self._dispatch_guard(p, lease, row, action, succeeded=reply.result is not None)
            return view
        finally:
            self._release_dispatch_pin(dispatch_pin)

    def _response_dispatch_pin(self, p, row, request):
        return None  # Legacy operator paths retain their exact old contract.

    def _parse_dispatch_response(self, p, row, dispatch, response, token):
        # Legacy/operator paths preserve their original parsing contract.
        return self._parse_admitted_response(p, row, response, token)

    def _release_dispatch_pin(self, dispatch):
        return None

    def _archive_response(self, p, row, dispatch, response, reply, token):
        return False

    def _parse_response(self, operation, response, token, synthetic):
        return wire.parse(operation, response, token, synthetic)

    def _parse_admitted_response(self, profile, row, response, token):
        return self._parse_response(row['operation'], response, token,
                                    profile.source_kind == 'SYNTHETIC_SETUP')

    def _write_gate(self, db, p, m, current_id=None, *, history_locators=None):
        from .own_draft_restore_store import check_write as check_restores
        check_restores(db, p.actor.tenant_id, p.resource_id)
        if db.execute('PRAGMA user_version').fetchone()[0] in (5, 6, 7, 8, 9):
            from .own_lineage import seal
            if not seal(db, m)['legacy']:
                raise WCEError('OWN_PERSISTENT_INTENT_REQUIRES_CONNECTION')
        from .own_body_recovery import check_resource_write, check_history_blockers
        if current_id is None:
            check_resource_write(self, db, p, history_locators=history_locators)
        else:
            check_history_blockers(self, db, p, current_id, history_locators=history_locators)
        from .draft_group_store import check_workflow_writer
        check_workflow_writer(db, p.binding(), m, current_id, history_locators=history_locators)

    def _insert_lock(self, db, p, m, identifier):
        db.execute("INSERT INTO own_resource_locks VALUES(?,?,'step',?)",
                   (p.actor.tenant_id, p.resource_id, identifier))

    def _release_lock(self, db, p, m, identifier):
        if db.execute("DELETE FROM own_resource_locks WHERE tenant=? AND resource=? AND kind='step' AND owner_id=?",
                (p.actor.tenant_id, p.resource_id, identifier)).rowcount != 1:
            raise WCEError('OWN_STATE_CORRUPT')

    def _owned_lock(self, db, p, m, identifier):
        lock = db.execute('SELECT kind,owner_id FROM own_resource_locks WHERE tenant=? AND resource=?',
                         (p.actor.tenant_id, p.resource_id)).fetchone()
        if lock is None or tuple(lock) != ('step', identifier):
            raise WCEError('OWN_STATE_CORRUPT')

    def _dispatch_guard_in(self, db, p, lease, original, action, succeeded=False, *, history_locators=None):
        self._network(p, lease, action, True)
        self._resource(db, p, history_locators=history_locators)
        row = db.execute('SELECT * FROM own_steps WHERE id=?', (original['id'],)).fetchone()
        intent, _ = self._step(db, p, row, history_locators=history_locators)
        if (row['owner'] != original['owner'] or row['intent_digest'] != original['intent_digest']
                or row['approval_digest'] != original['approval_digest']
                or row['state'] != ('SUCCEEDED' if succeeded else 'RESULT_UNKNOWN')):
            raise WCEError('OWN_SNAPSHOT_CHANGED')
        m, d = self._bundle(db, p, intent['selector']['bundle_id'], intent['selector']['version'])
        approval = self._approval(db, p, m, d, row['approval_id'])
        if approval['body_digest'] != row['approval_digest']:
            raise WCEError('OWN_SNAPSHOT_CHANGED')
        if not succeeded:
            self._owned_lock(db, p, m, row['id'])
        self._write_gate(db, p, m, row['id'], history_locators=history_locators)

    def _dispatch_guard(self, p, lease, row, action, succeeded=False):
        with _history_transaction(self.db) as (db, history_locators):
            self._dispatch_guard_in(db, p, lease, row, action, succeeded, history_locators=history_locators)
        self._network(p, lease, action, True)

    def _readback_guard_in(self, db, p, lease, original, *, history_locators=None):
        self._network(p, lease, APIS[3])
        self._resource(db, p, history_locators=history_locators)
        current = self._history(db, p, original['request_key'], history_locators=history_locators)
        intent, result = self._step(db, p, current, history_locators=history_locators)
        if (current['state'] != 'SUCCEEDED' or current['id'] != original['id']
                or current['intent_digest'] != original['intent_digest']
                or current['result_digest'] != original['result_digest']):
            raise WCEError('OWN_SNAPSHOT_CHANGED')
        return current, intent, result

    def _readback_guard(self, p, lease, original):
        with _history_transaction(self.db) as (db, history_locators):
            self._readback_guard_in(db, p, lease, original, history_locators=history_locators)
        self._network(p, lease, APIS[3])

    def _readback(self, p, lease, a):
        with _history_transaction(self.db) as (db, history_locators):
            self._resource(db, p, history_locators=history_locators)
            row = self._history(db, p, a['request_key'], history_locators=history_locators)
            if row is None or row['operation'] != 'add':
                raise WCEError('OWN_STEP_NOT_FOUND')
            intent, result = self._step(db, p, row, history_locators=history_locators)
        if row['state'] != 'SUCCEEDED':
            from .own_connection_workflow import PersistentWorkflow
            if (type(self) is PersistentWorkflow
                    and 'draft_read' in self.policy.value.get('capabilities', ())):
                from .own_draft_reconcile import ordinary_reconcile
                return ordinary_reconcile(self, p, lease, row, intent, a)
            return self._view(p, row)
        from .own_draft_reconcile import ORDINARY_ORIGIN
        if result.get('completion_origin') == ORDINARY_ORIGIN:
            from .own_draft_reconcile import ordinary_independent_readback
            return ordinary_independent_readback(self, p, lease, row, intent, result, a)
        if result.get('completion_origin') == 'OFFICIAL_DRAFT_READ_MATCH':
            if a.get('include_projection', False):
                raise WCEError('OWN_READBACK_PROJECTION_ORIGIN_UNSUPPORTED')
            from .own_draft_reconcile import independent_readback
            return independent_readback(self, p, lease, row, intent, result)
        action = APIS[3]
        self._network(p, lease, action)
        request = wire.encode_draft('get', {'media_id': result['reference']}, lease.token)
        self._readback_guard(p, lease, row)
        response = self._send(p, lease, request, action)
        self._network(p, lease, action)
        grouped = 'articles' in intent['projection']
        crop_indices = tuple(i for i, article in enumerate(intent['projection']['articles'])
                             if 'cover_info' in article) if grouped else ()
        parser = (lambda r, t, s, ref: wire.parse_group_get(
            r, t, s, ref, requested_cover_indices=crop_indices)) if grouped else (
                lambda r, t, s, ref: wire.parse('get', r, t, s, ref))
        reply = parser(response, lease.token, p.source_kind == 'SYNTHETIC_SETUP', result['reference'])
        expected_body = _body_projection(intent) if intent['schema'] == 2 else intent['projection']
        comment_comparison = None
        if intent['schema'] == 2:
            from .own_draft_wire import comment_comparison as compare_comments
            metadata = intent['article_metadata']
            comment_comparison = compare_comments(
                [dict(metadata['comment_settings']) for _ in range(metadata['article_count'])],
                getattr(reply, 'comment_observation', None))
        body_equal = reply.result == expected_body
        comments_equal = (comment_comparison is None or (comment_comparison['count_match']
            and all(row['state'] == 'VERIFIED' for row in comment_comparison['articles'])))
        with _history_transaction(self.db, write=True) as (db, history_locators):
            current, actual, value = self._readback_guard_in(db, p, lease, row, history_locators=history_locators)
            if actual != intent or value != result:
                raise WCEError('OWN_SNAPSHOT_CHANGED')
            state = 'MATCHED' if body_equal and comments_equal else 'UNVERIFIED'
            self._network(p, lease, action)
            db.execute('UPDATE own_steps SET readback=? WHERE id=?', (state, row['id']))
        self._readback_guard(p, lease, row)
        view = self._view(p, row)
        self._readback_guard(p, lease, row)
        # A concurrent authorized GET may update the durable latest readback.
        # This call reports the comparison from its own response and commit.
        from .own_diagnostics import projection, readback_comparison
        diagnostic = projection(reply, response)
        output = view | {'readback_state': state, 'readback_diagnostic': diagnostic,
                         'readback_comparison': (wire.group_comparison(expected_body, reply.result) if grouped
                            else readback_comparison(expected_body, reply.result))}
        if comment_comparison is not None:
            output.update(readback_policy='BODY_AND_REQUESTED_COMMENTS_V1',
                body_readback_state='MATCHED' if body_equal else 'UNVERIFIED',
                comment_readback_comparison=comment_comparison)
        if grouped:
            from .editor_contracts import checks, geometry
            with _history_transaction(self.db) as (db, history_locators):
                self._readback_guard_in(db, p, lease, row, history_locators=history_locators)
                manifest, _ = self._bundle(db, p, intent['selector']['bundle_id'], intent['selector']['version'])
            document = manifest['document']
            editorial = checks(document, reply.result)
            if intent['schema'] == 2:
                editorial = _metadata_editorial(intent['article_metadata'], editorial)
            if editorial:
                output['editorial_checks'] = editorial
            if crop_indices:
                actual_rows = reply.result.get('articles', []) if type(reply.result) is dict else []
                output['cover_crop_comparison'] = {'policy': 'GEOMETRY_WITHIN_ONE_PIXEL_ONLY',
                    'strict_readback_unchanged': True, 'articles': [
                        {'index': i, 'geometry_match': i < len(actual_rows) and geometry(
                            intent['projection']['articles'][i]['cover_info'],
                            actual_rows[i].get('cover_info'), document['articles'][i]['cover_dimensions'])}
                        for i in crop_indices]}
            self._readback_guard(p, lease, row)
        if grouped and a.get('include_projection', False):
            output.update(actual_projection_policy='ACTUAL_DOCUMENT_PROJECTION_V2', actual_projection=reply.result)
            self._readback_guard(p, lease, row)
        elif a.get('include_projection', False):
            fields = ('title', 'content', 'thumb_media_id')
            available = (diagnostic['reason'] == 'PARSED_SUCCESS'
                         and type(reply.result) is dict and set(reply.result) == set(fields)
                         and all(type(reply.result[key]) is str for key in fields))
            output.update(actual_projection_policy='ACTUAL_DRAFT_PROJECTION_V1',
                          actual_projection=({key: reply.result[key] for key in fields}
                                             if available else None))
            # Construct the opt-in data before the final authority/snapshot check.
            self._readback_guard(p, lease, row)
        from .own_connection_workflow import PersistentWorkflow
        observed = None
        if (type(self) is PersistentWorkflow and grouped
                and diagnostic.get('reason') == 'PARSED_SUCCESS'
                and type(reply.result) is dict):
            # The same non-authoritative representation observation applies
            # when add already returned a known reference. It does not alter
            # the committed byte comparison or the original response origin.
            from .own_draft_reconcile import _ordinary_observe
            observed = _ordinary_observe(response, lease.token,
                p.source_kind == 'SYNTHETIC_SETUP', result['reference'], intent)
            output['platform_representation'] = observed['platform_representation']
            self._readback_guard(p, lease, row)
        if grouped and type(self) is PersistentWorkflow:
            from .own_body_link_diagnostic import observe as observe_body_links
            links = observe_body_links(self, p, row, intent, result, document,
                observed['projection'] if observed is not None else None)
            if links is not None:
                output['body_link_diagnostic'] = links
                self._readback_guard(p, lease, row)
        if intent['schema'] == 2:
            from .own_connection_workflow import PersistentWorkflow
            if type(self) is PersistentWorkflow:
                from .own_normal_get_receipt import record as record_normal_get
                output.update(record_normal_get(self,p,lease,row,intent,result,output,response,reply.result))
            self._readback_guard(p, lease, row)
        return output

    def preflight(self, actor, a):
        missing = ['actual_host_installation', 'actual_WeChat_upload_add_get_readback']
        result = {'account_candidate': 'CURRENT_ACCOUNT_UNVERIFIED', 'account_candidate_verified': False,
            'supported_images': ['image/png', 'image/jpeg'], 'body_limit_bytes_exclusive': 1000000,
            'transport_limit_bytes_including_multipart': 2097152, 'required_apis': list(APIS),
            'news_policy': 'CONSERVATIVE_SUBSET_SCHEMA_RESOLUTION_REQUIRED', 'preflight_ready': False}
        result['news_content_limits'] = {'rendered_characters_exclusive': wire.NEWS_CONTENT_CHAR_LIMIT,
            'rendered_utf8_bytes_exclusive': wire.NEWS_CONTENT_BYTE_LIMIT,
            'policy': 'LOCAL_LONG_NEWS_CANDIDATE', 'official_add_limit_wording_resolved': False,
            'live_long_news_verified': False}
        if not a.get('connection_id') or self.registry is None or self.db is None:
            missing += ['trusted_profile', 'actual_four_API_capabilities', 'qualification', 'egress', 'quota',
                        'token_route', 'news_schema_resolution', 'memory_token_broker', 'trial_approval', 'dedicated_image_directory']
        else:
            try:
                p = self._profile(actor, a['connection_id'])
                result |= {'connection_id': p.connection_id, 'resource_id': p.resource_id,
                           'source_kind': p.source_kind, 'generation': p.generation}
                found = {e.kind: e for e in p.evidence_tuple}
                result['conditions'] = {k: ('MISSING' if k not in found else
                    ('EXPIRED' if found[k].expires <= self.clock() else found[k].state)) for k in sorted(KINDS)}
                missing += [k for k, v in result['conditions'].items() if v != 'AVAILABLE']
                missing += ['grant:' + k for k in APIS if k not in p.granted_actions]
                if p.source_kind == 'SYNTHETIC_SETUP':
                    missing.append('actual_operator_evidence_not_synthetic')
                if self.broker is None:
                    missing.append('memory_token_broker')
                if type(self.image_directory) is not ScopedImageDirectory:
                    missing.append('dedicated_image_directory')
                if type(self.sender) is not HTTPSender or not self.sender.enabled:
                    missing.append('enabled_trusted_official_sender')
                if 'bundle_id' in a:
                    with _history_transaction(self.db) as (db, history_locators):
                        self._resource(db, p, history_locators=history_locators)
                        m, d = self._bundle(db, p, a['bundle_id'], a['version'])
                        result['trial_preview'] = {'bundle_id': m['bundle_id'], 'version': m['version'],
                            'content_digest': d, **({'document': m['document']} if m['schema'] in (2, 3) else
                                {'title': m['article']['title'], 'blocks': m['article']['blocks']}),
                            'ordered_images': m['assets'], 'scope': 'ONE_NEWS_DRAFT_NO_PUBLICATION'}
                        try:
                            self._approval(db, p, m, d)
                        except WCEError:
                            missing.append('trial_approval')
                else:
                    missing.append('exact_article_and_trial_approval')
                self._profile(actor, p.connection_id, expected=p)
            except WCEError as error:
                missing.append(error.code)
        return result | {'missing': sorted(set(missing))} | self.evidence()

    def close_preview(self):
        with self._preview_lock:
            if self._preview_server is not None:
                self._preview_server.close()
                self._preview_server = None

    def _preview_guard(self, p):
        self._profile(p.actor, p.connection_id, expected=p)
        if getattr(self, 'live_guard', None) is not None:
            self.live_guard()
        if getattr(self, 'policy', None) is not None:
            self.policy.check()

    def _preview(self, p, a):
        # No _lease/_current: these can require a token even for local IO.
        from .document_preview import PreviewServer, html
        def guard():
            self._preview_guard(p)
        guard()
        with _history_transaction(self.db) as (db, history_locators):
            self._resource(db, p, history_locators=history_locators)
            m, d = self._bundle(db, p, a['bundle_id'], a['version'])
            if m['schema'] not in (2, 3):
                raise WCEError('DOCUMENT_FORMAT_CONFLICT')
            images = {item['slot']: (item['declared_type'], self._asset(db, p.binding(), item['asset_ref'])[1])
                      for item in m['assets']}
        artifact = html(m['document'], images)
        guard()
        with self._preview_lock:
            previous = getattr(self, '_preview_server', None)
            if previous is not None:
                previous.close()
            self._preview_server = server = PreviewServer(artifact, guard, min(300, p.expires - self.clock()))
            try:
                guard()
            except Exception:
                server.close()
                raise
        return {'connection_id': p.connection_id, 'preview_url': server.url,
                'document_digest': d, 'artifact_digest': server.digest,
                'expires_in_seconds': min(300, p.expires - self.clock()), 'preview_policy': 'LOCAL_HTML_V3' if m['schema'] == 3 else 'LOCAL_DOCUMENT_V2'} | self.evidence()

    def call(self, actor, name, a):
        validate(name, a)
        if name in {'own.assets.receive', 'own.articles.prepare', 'own.documents.prepare',
                    'own.uploads.execute', 'own.drafts.save', 'own.drafts.readback'}:
            from .publication_lock import draft_writer
            profile = self._profile(actor, a['connection_id'])
            with draft_writer(self.db.path.parent, profile.account_id):
                return self._call_locked(actor, name, a)
        return self._call_locked(actor, name, a)

    def _call_locked(self, actor, name, a):
        validate(name, a)
        if name == 'own.preflight':
            return self.preflight(actor, a)
        p = self._profile(actor, a['connection_id'])
        if name == 'own.documents.preview':
            return self._preview(p, a)
        lease = self._lease(p)
        self._current(p, lease)
        if name == 'own.assets.receive':
            result = self._receive(p, lease, a)
        elif name in {'own.articles.prepare', 'own.documents.prepare'}:
            result = self._prepare(p, lease, a)
        elif name in {'own.assets.status', 'own.articles.status'}:
            kind = 'asset' if name == 'own.assets.status' else 'prepare'
            with _history_transaction(self.db) as (db, history_locators):
                self._resource(db, p, history_locators=history_locators)
                result = self._old_input(db, p, kind, a['request_key'])
            if result is None:
                raise WCEError('OWN_INPUT_NOT_FOUND')
        elif name == 'own.articles.read':
            with _history_transaction(self.db) as (db, history_locators):
                self._resource(db, p, history_locators=history_locators)
                m, d = self._bundle(db, p, a['bundle_id'], a['version'])
                result = m | {'content_digest': d}
        elif name in {'own.uploads.execute', 'own.drafts.save'}:
            result = self._execute(p, lease, a, name == 'own.drafts.save')
        elif name == 'own.drafts.readback':
            result = self._readback(p, lease, a)
        else:
            with _history_transaction(self.db) as (db, history_locators):
                self._resource(db, p, history_locators=history_locators)
                row = self._history(db, p, a['request_key'], history_locators=history_locators)
                if row is None or (name == 'own.uploads.status') == (row['operation'] == 'add'):
                    raise WCEError('OWN_STEP_NOT_FOUND')
            result = self._view(p, row)
        self._current(p, lease)
        return result | {'connection_id': p.connection_id} | self.evidence()



from .draft_group_history_context import history_transaction as _history_transaction
