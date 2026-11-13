"""Publish an original saved group under the existing human standing grant.

Calling dispatch declares production complete. Actual save and normal GET are
checked in the account store. A producer's final message is not a prerequisite.
"""
from datetime import datetime, timezone
from dataclasses import replace
from pathlib import Path
import json
import os
import re
import time

from .publication_contract import binding, digest, fail
from .saved_groups_publication_source import SavedGroupsAuthorization
from .slot_saved_draft_source import SavedDraftReader
from .slot_standing_source import StandingSource, adopt_seed
from .slot_control_cache import HumanControlCache
from .slot_source_provider import _directory
from .slot_source_files import private_json, save_json

PURPOSE = 'STANDING_PRODUCTION_SAVED_GROUP_FREEPUBLISH_NO_PUSH_V1'
QUALITY = 'ORIGINAL_PRODUCTION_SAVE_AND_NORMAL_GET_VERIFIED'
_SEAL = object()
STEP = re.compile(r'own-step-[0-9a-f]{32}\Z')


def is_production(value):
    return type(value) is ProductionAuthorization and getattr(value, '_production_seal', None) is _SEAL


def _group(service, step_id, guard):
    """Derive selectors from the account's original step, never caller claims."""
    from .draft_group_history_context import readonly_history_snapshot, require_history
    from .own_store import OwnStore
    workflow, profile = service.workflow, service.profile()
    guard()
    with readonly_history_snapshot(workflow.policy, workflow.db.path) as (db, history):
        require_history(workflow.policy, db, history)
        OwnStore._check_layout(db, profile.source_kind, db.execute('PRAGMA user_version').fetchone()[0])
        workflow._resource_identity(db, profile)
        row = db.execute('SELECT * FROM own_steps WHERE tenant=? AND principal=? AND connection=? AND id=?',
                         workflow._scope(profile) + (step_id,)).fetchone()
        if row is None or row['operation'] != 'add' or row['state'] != 'SUCCEEDED':
            fail('PRODUCTION_PUBLICATION_SUCCESSFUL_SAVE_REQUIRED')
        intent, result = workflow._step(db, profile, row, history_locators=history)
        selector = intent['selector']
        manifest, content_digest = workflow._bundle(db, profile, selector['bundle_id'], selector['version'])
        if content_digest != selector['content_digest'] or manifest['schema'] not in (2, 3):
            fail('PRODUCTION_PUBLICATION_SAVED_VERSION_CHANGED')
        articles = manifest['document']['articles']
        group = dict(selector, save_request_key=row['request_key'], articles=[{
            'article_id': article['id'], 'article_sha256': digest(article),
            'source_html_sha256': article.get('provenance', {}).get('source_sha256')
        } for article in articles])
        if not 1 <= len(articles) <= 8:
            fail('PRODUCTION_PUBLICATION_GROUP_CHANGED')
    guard()
    return group


class ProductionAuthorization(SavedGroupsAuthorization):
    quality_source = QUALITY

    def __init__(self, service, registry, guard, deadline, *, native_guard=None,
                 step_id=None, request_identity=None):
        self.policy, self.registry = service.policy, Path(registry)
        self.guard, self.deadline = guard, deadline
        self.connection_id = self.policy.data['connection_id']
        profile = service.profile()
        if profile.connection_id != self.connection_id or profile.account_id != self.policy.data['appid']:
            fail('PRODUCTION_PUBLICATION_ACCOUNT_MISMATCH')
        self.policy_binding = binding(self.policy.data)
        self.root = self.registry.parent
        self.directory = _directory(self.root, 'production-publication')
        self.enrollment = None
        scan = guard if native_guard is None else native_guard
        self.standing = StandingSource(self.policy, registry,
            _directory(_directory(self.root, 'slot-sources'), 'standing'), guard, scan_guard=scan)
        seed = self.standing.advance()
        if seed['state'] != 'SEED_VERIFIED':
            fail('PRODUCTION_PUBLICATION_STANDING_INPUT_PENDING')
        if step_id is None:
            if not re.fullmatch(r'[0-9a-f]{64}', request_identity or ''):
                fail('PRODUCTION_PUBLICATION_ORIGINAL_SELECTION_REQUIRED')
            name = 'selection-' + request_identity + '.json'
            if not os.path.lexists(self.directory / name):
                fail('PRODUCTION_PUBLICATION_ORIGINAL_SELECTION_REQUIRED')
            selected, _ = private_json(self.directory, name, guard)
            step_id = selected.get('step_id')
        if type(step_id) is not str or STEP.fullmatch(step_id) is None:
            fail('PRODUCTION_PUBLICATION_ORIGINAL_SAVE_REQUIRED')
        group = _group(service, step_id, guard)
        self.proofs = (SavedDraftReader(service.workflow, service.profile(), guard,
                                       registered_drafts=True).read(group),)
        identity = {'purpose': PURPOSE, 'binding_sha256': self.policy_binding,
            'standing_sha256': self.standing.standing_sha, 'step_id': step_id}
        self.request_identity = digest(identity)
        if request_identity is not None and request_identity != self.request_identity:
            fail('PRODUCTION_PUBLICATION_ORIGINAL_SELECTION_REQUIRED')
        self.source_sha = self.request_identity
        self.path = self.directory / ('selection-' + self.request_identity + '.json')
        selected_at_ms = int(time.time() * 1000)
        if os.path.lexists(self.path):
            existing, _ = private_json(self.directory, self.path.name, guard)
            selected_at_ms = existing.get('selected_at_ms')
        if type(selected_at_ms) is not int or selected_at_ms <= 0:
            fail('PRODUCTION_PUBLICATION_ORIGINAL_SELECTION_REQUIRED')
        self.selection = dict(identity, schema=1, group=group, selected_at_ms=selected_at_ms)
        if not os.path.lexists(self.path):
            save_json(self.directory, self.path.name, self.selection, guard)
        if private_json(self.directory, self.path.name, guard)[0] != self.selection:
            fail('PRODUCTION_PUBLICATION_ORIGINAL_SELECTION_REQUIRED')
        self.config_sha = digest(self.selection)
        self.enrollment_path = self.directory / ('request-' + self.request_identity + '.json')
        # This tag selects the existing scoped-draft verifier. It is not a
        # route registration or a new grant.
        self.registered_handle = step_id
        value = self.standing.value
        self.value = dict(value, groups=[group], target_context={
            'date': self._source_date(), 'slot_id': step_id})
        self.review = {'profile': QUALITY, 'saved_proofs': [p.sha256 for p in self.proofs]}
        self.contract_scope = self.standing.scope
        self.request_ms = self._request_ms
        self.observed_ms = int(time.time() * 1000)
        self.control_context = replace(self._context(), standing_sha256=self.standing.standing_sha)
        self.controls = HumanControlCache(_directory(self.directory, 'controls-' + self.request_identity),
            self.control_context.owner_sha256, guard, lambda fact: self.control_context, scan_guard=scan)
        adopt_seed(self.controls, self.standing.boundary)
        self._production_seal = _SEAL
        self.fence()
        self.evidence_observation_sha256 = self.observation_sha

    def _source_date(self):
        pins = json.loads(self.standing.boundary.pin_proofs_json)
        pin = pins[self.standing.slot_id]
        created = pin['fact']['created']
        if type(created) in (int, float):
            moment = datetime.fromtimestamp(created, timezone.utc)
        elif type(created) is str:
            moment = datetime.fromisoformat(created.replace('Z', '+00:00'))
        else:
            fail('PRODUCTION_PUBLICATION_HUMAN_TIME_REQUIRED')
        if moment.tzinfo is None:
            fail('PRODUCTION_PUBLICATION_HUMAN_TIME_REQUIRED')
        self._request_ms = int(moment.timestamp() * 1000)
        return datetime.fromtimestamp(self.selection['selected_at_ms'] / 1000).astimezone().date().isoformat()

    def fence(self):
        self.guard()
        if time.monotonic() >= self.deadline or binding(self.policy.data) != self.policy_binding:
            fail('PRODUCTION_PUBLICATION_SCOPE_CHANGED')
        self.standing.boundary.fence()
        if private_json(self.directory, self.path.name, self.guard)[0] != self.selection:
            fail('PRODUCTION_PUBLICATION_ORIGINAL_SELECTION_REQUIRED')
        from .draft_revision_native_source import SourceHold
        while True:
            self.guard()
            if time.monotonic() >= self.deadline:
                fail('PRODUCTION_PUBLICATION_CONTROL_INPUT_PENDING')
            observed = self.controls.advance(self.standing.lookup)
            if observed['state'] == 'SCANNING':
                continue
            if observed['state'] != 'CURRENT':
                fail('PRODUCTION_PUBLICATION_CONTROL_INPUT_PENDING')
            try:
                self.controls.fence(self.standing.lookup, observed)
            except SourceHold as error:
                if error.code != 'SLOT_HUMAN_REOBSERVE_REQUIRED':
                    raise
                continue
            break
        for target in self.control_context.targets:
            decision = self.controls.decision({'connection_id': target.connection_id,
                'date': target.date, 'group_id': target.group_id})
            if decision['state'] == 'RESTRICTED':
                fail('PRODUCTION_PUBLICATION_HUMAN_RESTRICTED')
        for proof in self.proofs:
            proof.fence()
        if self.enrollment is not None and private_json(self.directory, self.enrollment_path.name, self.guard)[0] != self.enrollment:
            fail('PRODUCTION_PUBLICATION_ORIGINAL_SELECTION_REQUIRED')
        self.observation_sha = digest(observed)
        self.guard()

    def _descriptor(self, checkpoint, targets):
        return dict(super()._descriptor(checkpoint, targets), purpose=PURPOSE)

    def evidence(self):
        if self.enrollment is None:
            fail('SAVED_GROUPS_ENROLLMENT_REQUIRED')
        return {'purpose': PURPOSE, 'source_sha256': self.source_sha,
            'request_identity': self.request_identity, 'enrollment_sha256': digest(self.enrollment),
            **{key: self.standing.value[key] for key in ('source_thread', 'turn_id', 'message_id', 'text_sha256')},
            'native_observation_sha256': self.evidence_observation_sha256, 'request_ms': self.request_ms,
            'observed_ms': self.observed_ms, 'code_scope_sha256': self.contract_scope['code_scope_sha256'],
            'quality_source': QUALITY, 'ai_qa': 'PRODUCER_REVIEW_WITH_TECHNICAL_SAVE_GET_CHECK',
            'route': 'FREEPUBLISH', 'audience': 'NO_PUSH'}
