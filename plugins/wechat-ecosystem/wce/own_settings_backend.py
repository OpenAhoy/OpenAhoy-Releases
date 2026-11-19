"""Human-browser management adapter over the original enrollment transaction."""
import hmac
import os
from pathlib import Path
import secrets
import threading
import time

from .contracts import WCEError
from .own_connection_enrollment import enroll, enable_existing, upgrade_existing
from .own_enrollment_checked import enroll_checked, propose_checked, validate_record
from .own_connection_check import fresh_check, CheckBudget
from .own_bootstrap_security import CheckedTokenRejected
from .own_connection_policy import CAPABILITIES, registry_path, resolve, disconnect
from .own_connection_registry import (check_snapshot, metadata, prepare_default_registry,
                                      propose, snapshot, transaction_path)
from .own_connection_tools import ConnectionRouter
from .own_settings_http import safe_error
from .own_settings_protocol import overview
from . import own_cover_authority as cover_authority
from .own_workflow import encoded


RECOVERY_INTENT = 'RECOVER_BODY_BATCH_V1'
BODY5_INTENT = 'RECOVER_BODY5_ONCE_V1'
RECOVERY_INTENTS = {RECOVERY_INTENT,BODY5_INTENT}
RISK_ACK = '同意三图各额外上传一次'


class SettingsBackend:
    def __init__(self, registry=None, enrollment=enroll_checked, wall=time.time, clock=time.monotonic,
                 checker=fresh_check, required_budget=None, replacement_adapter=None, replacement_runner=None,
                 base_only=False):
        if type(base_only) is not bool:
            raise WCEError('SETTINGS_INVALID_REQUEST')
        self.base_only = base_only
        self.registry = Path(registry) if registry is not None else registry_path()
        self.default_registry = registry is None
        self.enrollment = enrollment
        self.checker, self.required_budget = checker, required_budget
        self.wall, self.clock = wall, clock
        self.lock = threading.RLock()
        self.closed = False
        self.state = 'READY'
        self.review = None
        self.result = {'state': 'NOT_SUBMITTED'}
        self.result_intent = None
        self.selected = None
        self.generation = 0
        self.diagnostic = None
        self.replacement_adapter, self.replacement_runner = replacement_adapter, replacement_runner
        self.pending_recovery = None
        self.pending_publication = None
        # A local, short-lived navigation is not an account operation. While
        # it is pending, old target-changing requests must not overtake it.
        self.navigation_pending = False

    def clear_target(self):
        self.review = None
        self.diagnostic = None
        self.generation += 1

    def close(self):
        # Register cancellation first; stop-intent writing must never acquire
        # the executor outer gate. No backend/session -> outer lock inversion.
        with self.lock:
            self.closed = True
            pending = self.pending_recovery
            if self.base_only:
                self.clear_target()
                return
            if pending is not None:
                pending['cancelled'].set()
            self.clear_target()
        if pending is not None:
            try:
                self.recovery_api().request_stop(self.registry, batch_id=pending['batch_id'], reason='PAGE_CLOSED')
            except Exception:
                pass  # The in-memory cancellation remains set; no sender is rebuilt.

    def check(self, check_session):
        check_session()
        if self.closed:
            raise WCEError('SETTINGS_EXPIRED')

    def call(self, path, value, check_session, *, history_locators=None):
        with self.lock:
            self.check(check_session)
            if self.base_only:
                self._base_admission(path, value)
                if path == '/result':
                    # A management refresh must not discover, adopt or resume
                    # a pending article/publication operation.
                    return dict(self.result)
            if self.navigation_pending and path in {
                    '/select', '/continue', '/review', '/commit', '/cancel',
                    '/presentation', '/publication-status', '/restore-status'}:
                raise WCEError('SETTINGS_BUSY')
            if path in {'/overview', '/result', '/cancel', '/cover-recoveries', '/continue', '/diagnostic'} and value:
                raise WCEError('SETTINGS_INVALID_REQUEST')
            if path in {'/continue', '/select'}:
                if self.state == 'ACTIVE':
                    raise WCEError('SETTINGS_BUSY')
                if path == '/select':
                    if set(value) != {'connection_id'} or value['connection_id'] is not None and type(value['connection_id']) is not str:
                        raise WCEError('SETTINGS_INVALID_REQUEST')
                    if value['connection_id'] is not None:
                        resolve(value['connection_id'], self.registry, active=False)
                    self.selected = value['connection_id']
                self.clear_target()
                if path == '/select':
                    # The durable account-scoped journal retains any prior
                    # pending operation; current page selection is independent.
                    self.pending_publication = None
                self.state = 'READY'
                self.result = {'state': 'NOT_SUBMITTED'}
                self.result_intent = None
                return {'state': 'READY', 'generation': self.generation, 'connection_id': self.selected}
            if path == '/diagnostic':
                if self.state == 'RESULT' and self.diagnostic is not None:
                    return dict(self.diagnostic)
                return {'state': 'NONE'}
            if path == '/overview':
                if self.base_only:
                    from .own_base_domain import router
                    return overview(router(self.registry))
                return overview(ConnectionRouter(registry=self.registry))
            if path == '/cover-recoveries':
                return {'targets': cover_authority.candidates(self.registry, history_locators=history_locators)}
            if path == '/presentation':
                if self.state not in {'READY', 'RESULT'}:
                    raise WCEError('SETTINGS_BUSY')
                from .own_presentation import save
                return save(value, self.registry, lambda: self.check(check_session))
            if path == '/publication-status':
                if self.state not in {'READY', 'RESULT'} or set(value) != {'connection_id'} or value['connection_id'] != self.selected or not self.selected:
                    raise WCEError('SETTINGS_INVALID_REQUEST')
                from .publication_settings import status
                return status(self, self.selected, check_session)
            if path == '/restore-status':
                if self.state not in {'READY', 'RESULT'} or set(value) != {'connection_id'} or value['connection_id'] != self.selected or not self.selected:
                    raise WCEError('SETTINGS_INVALID_REQUEST')
                from .own_draft_restore_settings import status
                return status(self, self.selected, check_session)
            if path == '/result':
                if self.state == 'RESULT' and self.result_intent == 'RESTORE_DRAFTS':
                    return dict(self.result)
                if self.state != 'ACTIVE' and self.pending_publication is None and self.selected:
                    from .publication_settings import recover_pending
                    self.pending_publication = recover_pending(self, self.selected, check_session)
                if self.state != 'ACTIVE' and self.pending_publication is not None:
                    from .publication_settings import durable_state
                    try:
                        durable = durable_state(self, self.pending_publication)
                        if durable.get('state') in {'OFF_CONFIRMED','NO_CHANGE'}:
                            self.result = {'state': ('PUBLICATION_DISABLE_COMMITTED' if durable['state']=='OFF_CONFIRMED' else 'PUBLICATION_ALREADY_OFF'), 'durable': durable}
                            self.pending_publication = None
                        else:
                            self.result = {'state': 'STOPPED', 'error': 'PUBLICATION_DISABLE_RESULT_UNKNOWN', 'durable': durable}
                    except Exception:
                        self.result = {'state': 'STOPPED', 'error': 'PUBLICATION_DISABLE_RESULT_UNKNOWN',
                                       'durable': {'state': 'UNAVAILABLE'}}
                    return dict(self.result)
                if self.state != 'ACTIVE' and (self.pending_recovery is not None or self.result.get('state') == 'NOT_SUBMITTED'):
                    return self.recovery_status()
                return dict(self.result)
            if path == '/cancel':
                if self.state == 'ACTIVE':
                    return {'state': 'ALREADY_ADMITTED', 'message': '已发出的请求无法撤回。'}
                self.clear_target()
                if self.state != 'RESULT':
                    self.state = 'READY'
                return {'state': 'CANCELLED'}
            if path == '/review':
                return self.prepare(value, check_session, history_locators=history_locators)
            if path != '/commit':
                raise WCEError('SETTINGS_INVALID_REQUEST')
            reviewed = self.admit(value, check_session, history_locators=history_locators)
        # No network/storage lock is held by this GUI admission lock. Closure
        # prevents new actions immediately, but cannot undo a dispatched request.
        return self.execute(reviewed, value, check_session, history_locators=history_locators)

    def _base_admission(self, path, value):
        paths = {'/overview', '/select', '/continue', '/diagnostic',
                 '/presentation', '/cancel', '/review', '/commit', '/result'}
        intents = {'ADD', 'UPGRADE_ONLY', 'ENABLE', 'DISCONNECT', 'CHECK_CONNECTION'}
        if (type(path) is not str or path not in paths or type(value) is not dict
                or self.pending_recovery is not None or self.pending_publication is not None):
            raise WCEError('ARTICLE_DOMAIN_NOT_READY')
        if path == '/review' and value.get('intent') not in intents:
            raise WCEError('ARTICLE_DOMAIN_NOT_READY')
        if path == '/commit' and (type(self.review) is not dict
                                 or self.review.get('intent') not in intents):
            raise WCEError('ARTICLE_DOMAIN_NOT_READY')
        if path == '/result' and (value or self.result_intent not in intents | {None}):
            raise WCEError('ARTICLE_DOMAIN_NOT_READY')

    def prepare(self, value, check_session=lambda: None, *, history_locators=None):
        if self.base_only:
            self._base_admission('/review', value)
        if self.state != 'READY':
            raise WCEError('SETTINGS_BUSY')
        intent = value.get('intent')
        if intent == 'RESTORE_DRAFTS':
            if set(value) != {'intent', 'connection_id'} or not self.selected or value['connection_id'] != self.selected:
                raise WCEError('SETTINGS_INVALID_REQUEST')
            from .own_draft_restore_settings import prepare
            return prepare(self, value, check_session)
        if intent in {'PUBLICATION_ENABLE', 'PUBLICATION_DISABLE'}:
            if self.pending_publication is not None and self.pending_publication.get('target') == value.get('connection_id'):
                raise WCEError('PUBLICATION_DISABLE_RESULT_UNKNOWN')
            from .publication_settings import prepare
            return prepare(self, value, check_session)
        if intent in RECOVERY_INTENTS:
            return self.prepare_recovery(value, check_session)
        keys = ({'intent', 'appid', 'label'} if intent == 'ADD' else
                {'intent', 'connection_id'} if intent in {'ENABLE', 'DISCONNECT', 'CHECK_CONNECTION'} else
                {'intent', 'targets'} if intent == 'RECOVER_COVERS' else {'intent'})
        if set(value) != keys or intent not in {'ADD', 'UPGRADE_ONLY', 'ENABLE', 'DISCONNECT', 'RECOVER_COVERS', 'CHECK_CONNECTION'}:
            raise WCEError('SETTINGS_INVALID_REQUEST')
        recovery = []
        if intent == 'RECOVER_COVERS':
            targets = value['targets']
            if type(targets) is not list or not 1 <= len(targets) <= 2:
                raise WCEError('SETTINGS_INVALID_REQUEST')
            from .prepared_contracts import ID, strict_validate
            seen = set()
            for target in targets:
                if type(target) is not dict or set(target) != {'connection_id', 'request_key'}:
                    raise WCEError('SETTINGS_INVALID_REQUEST')
                for field in target.values():
                    strict_validate(field, ID)
                cid = target['connection_id']
                if cid in seen:
                    raise WCEError('SETTINGS_INVALID_REQUEST')
                seen.add(cid)
                policy = resolve(cid, self.registry, active=False)
                recovery.append({'connection_id': cid,
                    'proposal': cover_authority.proposal(policy, target['request_key'], history_locators=history_locators)})
        if intent == 'ADD':
            if self.default_registry:
                prepare_default_registry()
            proposed = propose_checked(value['appid'], value['label'], self.registry, self.wall)
        else:
            base = snapshot(self.registry)
            if not base['policies']:
                raise WCEError('CONNECTION_NOT_BOUND')
            proposed = {'base': base, 'transaction': 'txn-' + secrets.token_hex(16)}
            if intent == 'ENABLE':
                proposed['reenable'] = value['connection_id']
            elif intent in {'UPGRADE_ONLY', 'RECOVER_COVERS'}:
                proposed['intent'] = 'UPGRADE_ONLY'
            elif intent == 'CHECK_CONNECTION':
                policy = resolve(value['connection_id'], self.registry)
                if policy.value['schema'] != 2:
                    raise WCEError('CONNECTION_UPGRADE_REVIEW_REQUIRED')
                budget = CheckBudget(self.registry, self.required_budget)
                if budget.pins is not None:
                    self.required_budget = dict(budget.pins)
                proposed['check_connection'] = value['connection_id']
            else:
                proposed['disconnect'] = value['connection_id']
            if intent in {'ENABLE', 'DISCONNECT', 'CHECK_CONNECTION'} and value['connection_id'] not in base['registry_value']['connections']:
                raise WCEError('CONNECTION_NOT_BOUND')
        base = proposed['base']
        accounts = []
        for old in base['policies'].values():
            p = old['value']
            cid = p['identity']['connection_id']
            enabled = p['enabled'] and not old['revoked']
            after = (False if intent == 'DISCONNECT' and cid == value['connection_id'] else
                     True if intent == 'ENABLE' and cid == value['connection_id'] else enabled)
            changed = ((intent == 'DISCONNECT' and cid == value['connection_id']) or
                       (intent not in {'DISCONNECT', 'CHECK_CONNECTION'} and (p['schema'] == 1 or
                        p['candidate_scope'] != base['scope'] or intent == 'ENABLE' and cid == value['connection_id'])))
            label = (base['registry_value'] or {}).get('entries', {}).get(cid, {}).get('label', cid)
            accounts.append({'connection_id': cid, 'appid': p['identity']['appid'], 'label': label,
                'previous_scope': p['candidate_scope'], 'enabled_before': enabled,
                'revoked_before': old['revoked'], 'enabled_after': after, 'will_change': changed})
        display = {'intent': intent, 'candidate_scope': base['scope'],
            'transaction': proposed['transaction'], 'existing_accounts': accounts,
            'capabilities': CAPABILITIES, 'duration': 'UNTIL_DISCONNECTED',
            'ordinary_requests': 1 if intent in {'ADD', 'CHECK_CONNECTION'} else 0,
            'automatic_retry': False, 'public_publication': False,
            'new_account_result': 'BOUND_IDLE' if intent == 'ADD' else None}
        if intent == 'ADD':
            display['new_account'] = {'appid': proposed['identity']['appid'], 'label': proposed['label'],
                                      'connection_id': proposed['identity']['connection_id']}
            if 'resume' in proposed:
                display['retry_sequence'] = proposed['resume']['next_sequence']
        else:
            display['selected_connection'] = value.get('connection_id')
        if recovery:
            display['cover_recovery'] = {
                'targets': recovery, 'budget_per_account': dict(cover_authority.BUDGET),
                'maximum_execution_seconds': cover_authority.MAX_SECONDS,
                'start_within_seconds': cover_authority.START_SECONDS,
                'pixel_policy': cover_authority.png_policy(),
                'jpeg_match_policy': cover_authority.jpeg_policy(),
                'one_attempt_per_target': True, 'business_writes': 0,
                'interrupted_attempt_is_spent': True}
        self.clear_target()
        self.selected = proposed['identity']['connection_id'] if intent == 'ADD' else value.get('connection_id')
        self.review = {'id': secrets.token_urlsafe(24), 'approval': secrets.token_urlsafe(32),
            'proposed': proposed, 'intent': intent, 'created': self.clock(), 'wall': self.wall(),
            'recovery': recovery, 'generation': self.generation, 'target': self.selected}
        self.state = 'REVIEW'
        return {'review_id': self.review['id'], 'approval': self.review['approval'],
                'expires_in_seconds': 120, 'review': display}

    def recovery_api(self):
        if self.replacement_adapter is None:
            from . import own_replacement_batch
            self.replacement_adapter = own_replacement_batch
        return self.replacement_adapter

    def recovery_runner(self):
        if self.replacement_runner is None:
            from . import own_replacement_executor
            self.replacement_runner = own_replacement_executor
        return self.replacement_runner

    @staticmethod
    def recovery_display(value, batch_id):
        # The adapter owns full proposal/history validation. This independent
        # display gate bounds browser allocations and permits DATA, never HTML.
        import base64
        import re
        from copy import deepcopy
        from .own_replacement_contract import count, validate_r2_cases, validate_cases, R3_CONTRACT_SHA, B5_CONTRACT_SHA
        size=count(value)
        if (type(value) is not dict or value.get('batch_id') != batch_id
                or value.get('maximum_new_sends') != size or type(value.get('maximum_new_sends')) is not int
                or value.get('per_case_new_sends') != 1 or type(value.get('per_case_new_sends')) is not int
                or value.get('duplicate_image_risk') is not True
                or type(value.get('retained_unrelated_locks')) is not int
                or (value['retained_unrelated_locks'] != 4 if value.get('contract_sha')==B5_CONTRACT_SHA else value['retained_unrelated_locks'] != 5 if value.get('contract_sha')==R3_CONTRACT_SHA
                    else (value['retained_unrelated_locks'] not in (0,2) if size==3
                          else not 0<=value['retained_unrelated_locks']<=3))
                or (value.get('contract_sha')==R3_CONTRACT_SHA and (type(value.get('retained_unknown_adds')) is not int or value['retained_unknown_adds'] != 2))
                or type(value.get('cases')) is not list or len(value['cases']) != size):
            raise WCEError('R1_PREVIEW_INVALID')
        if size==1:
            validate_cases(value)
            from .own_replacement_contract import B5_CONTRACT
            c=value['cases'][0];fixed=B5_CONTRACT
            expected={'asset_sha256':fixed['asset']['sha256'],'asset_bytes':fixed['asset']['size'],
                'asset_mime':fixed['asset']['declared_type'],'slot':fixed['asset']['slot'],
                'original_attempt_id':fixed['original_step_id'],'original_request_key':fixed['original_request_key'],
                'version':fixed['selector']['version'],'ordered_manifest_sha':fixed['selector']['content_digest'],
                'source_counts':{'succeeded':5,'unsent':0},'article_count':1,'original_admitted_attempts':1,'new_budget':1}
            if (any(c.get(k)!=v for k,v in expected.items())
                    or type(c.get('new_budget')) is not int
                    or type(c.get('source_counts')) is not dict
                    or set(c['source_counts'])!={'succeeded','unsent'}
                    or any(type(v) is not int for v in c['source_counts'].values())):
                raise WCEError('R1_PREVIEW_INVALID')
        if size==2:
            validate_r2_cases(value['cases'])
        seen = set()
        for case in value['cases']:
            if type(case) is not dict:
                raise WCEError('R1_PREVIEW_INVALID')
            for key, maximum in [('case_id', 128), ('label', 128), ('title', 128), ('slot', 128)]:
                if type(case.get(key)) is not str or not 0 < len(case[key]) <= maximum:
                    raise WCEError('R1_PREVIEW_INVALID')
            if case['case_id'] in seen or type(case.get('asset_sha256')) is not str or not re.fullmatch('[a-f0-9]{64}', case['asset_sha256']):
                raise WCEError('R1_PREVIEW_INVALID')
            seen.add(case['case_id'])
            if size in (1,2) and (type(case.get('asset_bytes')) is not int or not 0<case['asset_bytes']<1000000
                    or case.get('asset_mime') not in ('image/png','image/jpeg')
                    or type(case.get('article_count')) is not int or not 1<=case['article_count']<=8
                    or case.get('original_admitted_attempts')!=1 or type(case.get('original_admitted_attempts')) is not int
                    or type(case.get('original_attempt_id')) is not str
                    or re.fullmatch('own-step-[a-f0-9]{32}',case['original_attempt_id']) is None):
                raise WCEError('R1_PREVIEW_INVALID')
            image = case.get('preview')
            if (type(image) is not dict or set(image) != {'width', 'height', 'rgba'}
                    or type(image['width']) is not int or type(image['height']) is not int
                    or not 1 <= image['width'] <= 640 or not 1 <= image['height'] <= 640
                    or type(image['rgba']) is not str
                    or len(image['rgba']) > 4*((640*640*4+2)//3)):
                raise WCEError('R1_PREVIEW_INVALID')
            try:
                raw = base64.b64decode(image['rgba'], validate=True)
                if len(raw) != image['width'] * image['height'] * 4:
                    raise ValueError()
            except (ValueError, TypeError):
                raise WCEError('R1_PREVIEW_INVALID') from None
        return deepcopy(value)

    def prepare_recovery(self, value, check_session):
        from copy import deepcopy
        from .service import digest
        if set(value) != {'intent'}:
            raise WCEError('SETTINGS_INVALID_REQUEST')
        def guard():
            self.check(check_session)
        if value['intent']==BODY5_INTENT:
            from .own_replacement_contract import B5_CONTRACT_SHA
            prepared=deepcopy(self.recovery_api().prepare(self.registry,guard,B5_CONTRACT_SHA))
            if prepared.get('contract_sha')!=B5_CONTRACT_SHA: raise WCEError('R1_REVIEW_CHANGED')
        else:
            prepared = deepcopy(self.recovery_api().prepare(self.registry, guard))
        if (type(prepared) is not dict or type(prepared.get('batch_id')) is not str
                or not 1 <= len(prepared['batch_id']) <= 128):
            raise WCEError('R1_REVIEW_CHANGED')
        shown = self.recovery_display(self.recovery_api().display(prepared), prepared['batch_id'])
        from .own_replacement_contract import B5_CONTRACT_SHA
        if (shown.get('contract_sha')!=prepared.get('contract_sha')
                or (value['intent']==BODY5_INTENT)!=(prepared.get('contract_sha')==B5_CONTRACT_SHA)):
            raise WCEError('R1_REVIEW_CHANGED')
        guard()
        self.clear_target()
        self.review = {'id': secrets.token_urlsafe(24), 'approval': secrets.token_urlsafe(32),
            'intent': value['intent'], 'prepared': prepared, 'batch_id': prepared['batch_id'],
            'proposal_sha': digest(prepared), 'display_sha': digest(shown),
            'created': self.clock(), 'wall': self.wall(), 'generation': self.generation,
            'target': self.selected}
        self.state = 'REVIEW'
        return {'review_id': self.review['id'], 'approval': self.review['approval'],
            'expires_in_seconds': 120, 'review': {'intent': value['intent'],
                'existing_accounts': [], 'body_recovery': shown}}

    def recovery_status(self):
        from .service import canonical
        import json
        api = self.recovery_api()
        batch_id = (self.pending_recovery['batch_id'] if self.pending_recovery is not None
                    else api.find_batch(self.registry))
        if batch_id is None:
            return {'state': 'NOT_SUBMITTED'}
        result = api.query(self.registry, batch_id)
        raw = canonical(result)
        if type(result) is not dict or len(raw.encode()) > 65536:
            raise WCEError('R1_STATUS_INVALID')
        def validate(item):
            if type(item) is dict:
                if {'owner', 'owner_capability', 'token', 'secret', 'approval', 'csrf',
                        'session', 'bootstrap', 'url', 'raw'} & set(item):
                    raise WCEError('R1_STATUS_INVALID')
                for child in item.values(): validate(child)
            elif type(item) is list:
                for child in item: validate(child)
        validate(result)
        return json.loads(raw)

    def execute_recovery(self, reviewed, check_session):
        pending = reviewed['pending_recovery']
        def guard():
            with self.lock:
                self.check(check_session)
                if (self.pending_recovery is not pending or pending['cancelled'].is_set()
                        or reviewed['generation'] != self.generation
                        or reviewed['target'] != self.selected):
                    raise WCEError('R1_REVIEW_CHANGED')
        owner = None
        try:
            guard()
            owner = self.recovery_api().commit(reviewed['prepared'], reviewed['confirmed_at'],
                reviewed['human_review_sha'], guard, pending['cancelled'], self.registry)
            guard()
            # RunOwner is a memory-only capability. It is never returned, stored
            # on the backend or rendered, even if the runner raises.
            self.recovery_runner().run(owner, self.registry, guard)
            guard()
            result = self.recovery_status()
            guard()
        except Exception as error:
            pending['cancelled'].set()
            try:
                self.recovery_api().request_stop(self.registry, batch_id=pending['batch_id'],
                    reason='UI_EXECUTION_STOPPED')
            except Exception:
                pass
            result = {'state': 'STOPPED', 'error': safe_error(error)}
        finally:
            owner = None
        with self.lock:
            if not self.closed:
                self.state, self.result = 'RESULT', result
        return dict(result)

    def admit(self, value, check_session, *, history_locators=None):
        if self.base_only:
            self._base_admission('/commit', value)
        current = self.review
        if self.state != 'REVIEW' or current is None:
            raise WCEError('SETTINGS_REVIEW_REQUIRED')
        keys = ({'review_id', 'approval', 'risk_ack'} if current['intent'] in RECOVERY_INTENTS else
                {'review_id', 'approval', 'secret'} if current['intent'] == 'ADD' else {'review_id', 'approval'})
        if set(value) != keys:
            raise WCEError('SETTINGS_INVALID_REQUEST')
        for key, expected in (('review_id', current['id']), ('approval', current['approval'])):
            if type(value[key]) is not str or not hmac.compare_digest(value[key], expected):
                raise WCEError('SETTINGS_ACCESS_DENIED')
        self.check(check_session)
        if current['intent'] == 'RESTORE_DRAFTS' and (current['generation'] != self.generation or current['target'] != self.selected):
            raise WCEError('SETTINGS_REVIEW_CHANGED')
        if current['intent'] in RECOVERY_INTENTS:
            from .service import digest
            from .own_replacement_contract import risk_phrase
            if value['risk_ack'] != risk_phrase(current['prepared']) or type(value['risk_ack']) is not str:
                raise WCEError('R1_RISK_ACK_REQUIRED')
            if digest(current['prepared']) != current['proposal_sha']:
                raise WCEError('R1_REVIEW_CHANGED')
        else:
            check_snapshot(current['proposed']['base'])
        for item in current.get('recovery', []):
            policy = resolve(item['connection_id'], self.registry, active=False)
            actual = cover_authority.proposal(policy, item['proposal']['target']['request_key'], history_locators=history_locators)
            if encoded(actual) != encoded(item['proposal']):
                raise WCEError('COVER_READ_SNAPSHOT_CHANGED')
        # Filesystem snapshot validation can take time. Expiry and page closure
        # must be checked AFTER it, immediately before the one-shot admission.
        elapsed, wall_elapsed = self.clock() - current['created'], self.wall() - current['wall']
        if (not 0 <= elapsed < 120 or not 0 <= wall_elapsed < 120
                or abs(elapsed - wall_elapsed) >= 5):
            self.review = None
            raise WCEError('SETTINGS_EXPIRED')
        self.check(check_session)
        current['confirmed_at'] = self.wall()
        if current['intent'] == 'PUBLICATION_DISABLE':
            # Consume the verified human review first. Persist its exact
            # operation before any business effect, including NO_CHANGE.
            self.review = None
            self.state = 'ACTIVE'
            self.result = {'state': 'IN_PROGRESS'}
            self.pending_publication = current
            try:
                from .publication_settings import admit_disable
                admit_disable(self, current, check_session)
            except Exception:
                self.state = 'RESULT'
                self.result = {'state':'STOPPED','error':'PUBLICATION_DISABLE_RESULT_UNKNOWN',
                    'durable':{'state':'UNKNOWN','operation_id':current['proposed']['transaction']}}
                raise WCEError('PUBLICATION_DISABLE_RESULT_UNKNOWN') from None
            return current
        if current['intent'] in RECOVERY_INTENTS:
            from .service import digest
            from .own_replacement_contract import risk_phrase, count, R3_CONTRACT_SHA, B5_CONTRACT_SHA
            pending = {'batch_id': current['batch_id'], 'generation': current['generation'],
                'proposal_sha': current['proposal_sha'], 'cancelled': threading.Event()}
            self.pending_recovery = pending
            current['pending_recovery'] = pending
            current['human_review_sha'] = digest({'schema': ('B5_TRUSTED_SETTINGS_REVIEW_V1' if current['prepared'].get('contract_sha')==B5_CONTRACT_SHA else 'R3_TRUSTED_SETTINGS_REVIEW_V1' if current['prepared'].get('contract_sha')==R3_CONTRACT_SHA
                    else 'R2_TRUSTED_SETTINGS_REVIEW_V1' if count(current['prepared'])==2 else 'R1_TRUSTED_SETTINGS_REVIEW_V1'),
                'batch_id': current['batch_id'], 'proposal_sha': current['proposal_sha'],
                'display_sha': current['display_sha'], 'risk_ack': risk_phrase(current['prepared']),
                'confirmed_at': current['confirmed_at'], 'nonce_sha': digest({'id': current['id'], 'approval': current['approval']})})
        self.review = None
        self.state = 'ACTIVE'
        self.result = {'state': 'IN_PROGRESS'}
        return current

    def durable_state(self, reviewed):
        """Only the operation's own non-secret finite state, never arbitrary data."""
        if reviewed['intent'] == 'RESTORE_DRAFTS':
            from .own_draft_restore_settings import durable_state
            return durable_state(self, reviewed)
        if reviewed['intent'] in {'PUBLICATION_ENABLE', 'PUBLICATION_DISABLE'}:
            from .publication_settings import durable_state
            return durable_state(self, reviewed)
        proposed = reviewed['proposed']
        result = {}
        if reviewed['intent'] == 'ADD':
            path = self.registry.parent / 'connection-enrollments' / (proposed['identity']['appid'] + '.json')
            record = metadata(path)
            if record and record.get('schema') in {2,3}:
                validate_record(record)
                current = record['attempts'][-1]
                if current['review']['transaction'] == proposed['transaction']:
                    result.update(attempt=current['state'], credential=current['credential'],
                                  binding=current['binding'], attempt_count=len(record['attempts']))
            if record and record.get('review', {}).get('transaction') == proposed['transaction']:
                for key, choices in {
                    'attempt': {'NOT_SENT', 'SPENT_RESULT_UNKNOWN', 'VALIDATED'},
                    'credential': {'NOT_STORED', 'STORE_ATTEMPT_UNKNOWN', 'STORED'},
                    'binding': {'NOT_COMMITTED', 'COMMITTED'},
                }.items():
                    if record.get(key) in choices:
                        result[key] = record[key]
        path = transaction_path(self.registry, proposed['transaction'])
        if os.path.lexists(path):
            record = metadata(path)
            if record and record.get('state') in {'PREPARED', 'COMMITTED', 'ROLLED_BACK'}:
                result['publication'] = record['state']
        return result

    def execute(self, reviewed, value, check_session=lambda: None, *, history_locators=None):
        if self.base_only:
            self._base_admission('/review', {'intent': reviewed.get('intent')})
        if reviewed['intent'] in RECOVERY_INTENTS:
            return self.execute_recovery(reviewed, check_session)
        proposed, intent = reviewed['proposed'], reviewed['intent']
        granted = []
        diagnostic = None
        def guard():
            with self.lock:
                self.check(check_session)
                if reviewed['generation'] != self.generation or reviewed['target'] != self.selected:
                    raise WCEError('SETTINGS_REVIEW_CHANGED')
        try:
            if intent == 'RESTORE_DRAFTS':
                from .own_draft_restore_settings import execute
                result = execute(self, reviewed, check_session)
            elif intent in {'PUBLICATION_ENABLE', 'PUBLICATION_DISABLE'}:
                from .publication_settings import execute
                result = execute(self, reviewed, check_session)
            elif intent == 'ADD':
                arguments = {'guard': guard} if self.enrollment is enroll_checked else {}
                policy, cached, retained, _ = self.enrollment(proposed, lambda: value['secret'], **arguments)
                try:
                    result = {'state': 'BOUND_IDLE', 'connection_id': policy.data['connection_id'],
                              'message': '已验证并绑定。当前空闲；本页面不会自动建立持续连接。'}
                finally:
                    cached = None
                    retained.close()
            elif intent == 'CHECK_CONNECTION':
                policy = resolve(proposed['check_connection'], self.registry)
                result = self.checker(policy, proposed['transaction'], guard,
                                      required_budget=self.required_budget)
            elif intent == 'UPGRADE_ONLY':
                result = upgrade_existing(proposed)
            elif intent == 'RECOVER_COVERS':
                upgrade_existing(proposed)
                for item in reviewed['recovery']:
                    policy = resolve(item['connection_id'], self.registry)
                    grant = cover_authority.publish(policy, item['proposal'],
                        proposed['transaction'], reviewed['confirmed_at'], history_locators=history_locators)
                    granted.append({'connection_id': item['connection_id'],
                        'request_key': item['proposal']['target']['request_key'], 'grant_id': grant})
                result = {'state': 'READ_RECOVERY_GRANTED', 'grants': granted,
                    'message': '原封面的一次只读核对已授权；程序可继续检查，尚未执行素材读取。'}
            elif intent == 'ENABLE':
                policy = enable_existing(proposed)
                result = {'state': 'BOUND_IDLE', 'connection_id': policy.data['connection_id']}
            else:
                check_snapshot(proposed['base'])
                policy = resolve(proposed['disconnect'], self.registry, active=False)
                result = disconnect(policy)
        except Exception as error:
            result = {'state': 'STOPPED', 'error': safe_error(error)}
            if type(error) is CheckedTokenRejected:
                result['retry_available'] = intent == 'ADD' and error.proof is not None
                diagnostic = {'state': 'IP_DENIED', 'observed_ip': error.observed_ip,
                    'connection_id': reviewed['target'], 'generation': reviewed['generation']}
                if error.code != 'BOOTSTRAP_TOKEN_IP_DENIED':
                    diagnostic = None
            if intent == 'RECOVER_COVERS':
                # Each account has its own durable grant. Never claim a batch
                # rollback or retry an account whose publication was uncertain.
                result['grants_confirmed_before_stop'] = granted
        finally:
            value.pop('secret', None)
        try:
            result['durable'] = self.durable_state(reviewed)
            if intent == 'PUBLICATION_DISABLE':
                durable = result['durable']
                if durable.get('state') == 'OFF_CONFIRMED':
                    result = {'state': 'PUBLICATION_DISABLE_COMMITTED', 'durable': durable}
                elif durable.get('state') == 'NO_CHANGE':
                    result = {'state': 'PUBLICATION_ALREADY_OFF', 'durable': durable}
                else:
                    result = {'state': 'STOPPED', 'error': 'PUBLICATION_DISABLE_RESULT_UNKNOWN',
                              'durable': durable}
            if result.get('retry_available'):
                result['retry_available'] = (result['durable'].get('attempt') == 'REJECTED_IP'
                    and result['durable'].get('credential') == 'NOT_STORED'
                    and result['durable'].get('binding') == 'NOT_COMMITTED')
        except Exception:
            result['durable'] = {'state': 'UNAVAILABLE'}
            if intent == 'PUBLICATION_DISABLE':
                result = {'state': 'STOPPED', 'error': 'PUBLICATION_DISABLE_RESULT_UNKNOWN',
                          'durable': {'state': 'UNAVAILABLE'}}
            if 'retry_available' in result:
                result['retry_available'] = False
        with self.lock:
            try:
                guard()
            except Exception:
                self.diagnostic = None
                raise
            self.state, self.result = 'RESULT', result
            self.result_intent = intent
            if intent == 'PUBLICATION_DISABLE' and result.get('error') == 'PUBLICATION_DISABLE_RESULT_UNKNOWN':
                self.pending_publication = reviewed
            elif intent == 'PUBLICATION_DISABLE':
                self.pending_publication = None
            self.diagnostic = diagnostic
        return dict(result)
