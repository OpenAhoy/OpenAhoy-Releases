"""Jiusera's app-only client for the official WeChat workspace broker."""
from hashlib import sha256
import json
import os
from pathlib import Path
import re
from threading import RLock
from time import time
from urllib.error import HTTPError
from urllib.parse import urlencode
from urllib.request import Request, build_opener
import secrets

from .contracts import WCEError
from .openahoy_mcp_status import _NoRedirect
from .own_bootstrap_security import path_check
from .own_connection_policy import atomic_write, locked, read_optional, read_registry, registry_path
from .own_connection_registry import container
from .prepared_contracts import ID, strict_validate
from .tools import schema
from .wechat_component_identity import clean_authorizer_info, official_profile_fields
from .wechat_workspace_proof import FORMAT as PROOF_FORMAT, WorkspaceProof, prepare_local_workspace

BASE = 'https://www.readysteadysound.com/jiusera/api/oauth/wechat'
TOOL = 'wce.ui.wechat.component_binding'
OVERVIEW = 'wce.ui.management.overview'
WECHAT = 'wechat_official_account'
APP = re.compile(r'wx[a-f0-9]{16}')
TX = re.compile(r'[a-f0-9]{48}')
PUBLIC_STATES = frozenset({'STARTING', 'PENDING', 'EXPIRED', 'CANCELLED',
    'TICKET_OR_COMPONENT_UNAVAILABLE', 'START_UNKNOWN', 'EXCHANGING', 'EXCHANGE_UNKNOWN',
    'REJECTED', 'WORKSPACE_CONFLICT', 'BOUND', 'REVOKED', 'TARGET_MISMATCH', 'TARGET_STALE'})
ACTIVE = frozenset({'STARTING', 'PENDING', 'START_UNKNOWN', 'EXCHANGING', 'EXCHANGE_UNKNOWN'})
MAX_BODY = 256 * 1024
SPEC = schema({'operation': {'type': 'string', 'enum': ['BEGIN', 'STATUS', 'CANCEL', 'WORKSPACE_STATUS', 'PROFILE_STATUS', 'TARGET_STATUS']}},
              {'connection_id': ID})


def _bad():
    raise WCEError('WECHAT_COMPONENT_RESPONSE_INVALID')


def _timestamp(value):
    return type(value) is int and 0 < value < 2**40


def _binding(value):
    if type(value) is not dict:
        _bad()
    app, original, state = value.get('appid'), value.get('originalId'), value.get('state')
    generation, stamp = value.get('generation'), value.get('verifiedAt')
    if (type(app) is not str or not APP.fullmatch(app)
            or type(original) is not str or not re.fullmatch(r'gh_[A-Za-z0-9]{1,64}', original)
            or type(state) is not str or state not in {'ACTIVE', 'REVOKED'} or not _timestamp(stamp)
            or type(generation) is not int or not 0 < generation < 2**53):
        _bad()
    row = {'appid': app, 'originalId': original, 'state': state, 'generation': generation, 'verifiedAt': stamp}
    if state == 'ACTIVE':
        scopes, expiry, renew = value.get('funcInfo'), value.get('expiresAt'), value.get('refreshState')
        if (type(scopes) is not list or len(scopes) > 128
                or any(type(entry) is not int or not 0 < entry < 2**31 for entry in scopes)
                or len(scopes) != len(set(scopes)) or not _timestamp(expiry)
                or type(renew) is not str or renew not in {'CURRENT', 'REQUIRED', 'UNCONFIRMED'}):
            _bad()
        info = clean_authorizer_info(value.get('authorizerInfo'))
        if info:
            row['authorizerInfo'] = info
        row.update(funcInfo=sorted(scopes), expiresAt=expiry, refreshState=renew)
    return row


def _bindings(rows):
    if type(rows) is not list or len(rows) > 1024:
        _bad()
    values = [_binding(row) for row in rows]
    if len({row['appid'] for row in values}) != len(values):
        _bad()
    return values


def _flow(value, expected=None):
    if type(value) is not dict:
        _bad()
    state, tx, expiry = value.get('state'), value.get('transaction'), value.get('expiresAt')
    if (type(state) is not str or state not in PUBLIC_STATES or type(tx) is not str or not TX.fullmatch(tx)
            or expected and tx != expected or not _timestamp(expiry)):
        _bad()
    public = {'status': state, 'transaction': tx, 'expires_at': expiry}
    if value.get('cancelRequested') is True:
        public['cancel_requested'] = True
    authorize_url = value.get('authorizeUrl')
    if authorize_url is not None:
        if state != 'PENDING' or authorize_url != BASE + '/authorize?transaction=' + tx:
            _bad()
        public['authorization_url'] = authorize_url
    if state == 'BOUND':
        row = _binding(value.get('binding'))
        if value.get('appid') != row['appid']:
            _bad()
        public.update(binding=row, account_id=row['appid'], connection_id=_cid(row['appid']))
        if row['state'] == 'REVOKED':
            public['status'] = 'REVOKED'
    return public


def _cid(appid):
    return 'wechat-authorized-' + sha256(appid.encode()).hexdigest()[:32]


def configuration_account(registry, connection_id):
    """Resolve a local preferences owner from the last verified workspace status."""
    if not re.fullmatch(r'wechat-authorized-[a-f0-9]{32}', connection_id):
        return None
    return next((row for row in ComponentBinding(registry).overview()
                 if row['connection_id'] == connection_id and row['state'] == 'BOUND_IDLE'), None)


class WorkspaceBroker:
    def __init__(self, opener=None):
        self.open = opener or build_opener(_NoRedirect()).open

    def request(self, path, proof, *, transaction=None, idempotency=None, target=None, profile=None):
        payload = None
        headers = {'Accept': 'application/json', 'Authorization': 'Bearer ' + proof.reveal_for_adapter()}
        if target is not None and (type(target) is not str or not APP.fullmatch(target)):
            _bad()
        if path == 'start':
            if type(idempotency) is not str or not PROOF_FORMAT.fullmatch(idempotency):
                _bad()
            headers['Idempotency-Key'] = idempotency
            payload = json.dumps({'expected_authorizer_appid': target} if target else {}).encode('ascii')
        elif path == 'cancel':
            if type(transaction) is not str or not TX.fullmatch(transaction):
                _bad()
            payload = json.dumps({'transaction': transaction}).encode('ascii')
        elif path == 'enroll':
            payload = b'{"action":"enroll"}'
        elif path not in ('status', 'enrollment'):
            _bad()
        if payload is not None:
            headers['Content-Type'] = 'application/json'
        url = BASE + '/' + ('status' if path in ('enrollment', 'enroll') else path)
        if path == 'enrollment':
            url += '?enrollment=1'
        elif path == 'status' and transaction is not None:
            if type(transaction) is not str or not TX.fullmatch(transaction):
                _bad()
            url += '?' + urlencode({'transaction': transaction})
        elif path == 'status' and profile is not None:
            if type(profile) is not str or not APP.fullmatch(profile):
                _bad()
            url += '?' + urlencode({'profile_appid': profile})
        elif path == 'status' and target:
            url += '?' + urlencode({'expected_authorizer_appid': target})
        request = Request(url, headers=headers, data=payload, method='POST' if payload is not None else 'GET')
        try:
            try:
                response = self.open(request, timeout=6.0)
            except HTTPError as error:
                response = error
            with response:
                status = response.status
                if response.geturl() != url:
                    _bad()
                data = response.read(MAX_BODY + 1)
        except OSError:
            raise WCEError('WECHAT_COMPONENT_SERVICE_UNAVAILABLE') from None

        if status == 401:
            return status, {}
        if len(data) > MAX_BODY:
            _bad()
        try:
            value = json.loads(data)
        except (ValueError, RecursionError):
            if status == 403:
                return status, {}
            raise WCEError('WECHAT_COMPONENT_SERVICE_UNAVAILABLE') from None
        if type(value) is not dict:
            if status == 403:
                return status, {}
            _bad()
        return status, value


class ComponentBinding:
    def __init__(self, registry, *, transport=None, workspace_proof=None, clock=time):
        self.registry = Path(registry or registry_path()).absolute()
        scope = sha256(os.fsencode(self.registry)).hexdigest()[:24]
        self.root = self.registry.parent / ('wechat-component-' + scope)
        self.transport = transport or WorkspaceBroker()
        self.proof = workspace_proof or WorkspaceProof(self.registry)
        self.clock = clock
        self._lock = RLock()

    def _cache(self, *, include_removed=False):
        if not os.path.lexists(self.root):
            return None
        path_check(self.root, True)
        value = read_optional(self.root / 'workspace-bindings.json', MAX_BODY)
        if value is None:
            return None
        if value.get('schema') != 1 or not _timestamp(value.get('checked_at')):
            _bad()
        removed = {} if include_removed else self._removals()
        return {'checked_at': value['checked_at'], 'rows': [row for row in _bindings(value.get('bindings'))
                if row['appid'] not in removed]}

    def _removals(self):
        records = read_optional(self.root / 'removed-bindings.json', MAX_BODY)
        if records is None:
            return {}
        if (type(records) is not dict or any(not APP.fullmatch(app) or type(row) is not dict
                or row.get('state') not in ('PENDING', 'DISCONNECTED')
                or type(row.get('generation')) is not int or not 0 <= row['generation'] < 2**53
                or type(row.get('connection_id')) is not str or type(row.get('revision')) is not str
                or type(row.get('direct')) is not bool for app, row in records.items())):
            _bad()
        return records

    def _write_removals(self, records):
        atomic_write(self.root / 'removed-bindings.json', records, MAX_BODY)

    def _target(self, cid):
        cached = self._cache(include_removed=True)
        grants = (cached or {}).get('rows', [])
        removed = self._removals()
        for row in grants:
            if _cid(row['appid']) == cid and row['appid'] not in removed:
                return row['appid'], False
        from .own_connection_policy import resolve
        try:
            policy = resolve(cid, self.registry, active=False, readonly=True)
            policy.check(readonly=True)
        except WCEError:
            return None
        appid = policy.data['appid']
        if not APP.fullmatch(appid):
            return None
        # Only an existing, verified local direct policy may initiate the
        # first administrator grant. Knowing an AppID is not sufficient.
        has_grant = any(row['appid'] == appid for row in grants) or removed.get(appid, {}).get('generation', 0) > 0
        return appid, not has_grant

    def _save_bindings(self, rows, *, checked_at=None):
        existing = self._cache(include_removed=True)
        previous = {r['appid']: r for r in (existing or {}).get('rows', [])}
        rows = _bindings(rows)
        for row in rows:
            old = previous.get(row['appid'])
            if (old and old['state'] == row['state'] == 'ACTIVE'
                    and old['generation'] == row['generation'] and old['originalId'] == row['originalId']):
                known = old.get('authorizerInfo')
                if known and known['verifiedAt'] > row.get('authorizerInfo', {}).get('verifiedAt', 0):
                    row['authorizerInfo'] = known
        atomic_write(self.root / 'workspace-bindings.json', {
            'schema': 1, 'checked_at': int(self.clock()) if checked_at is None else checked_at,
            'bindings': rows}, MAX_BODY)

    def _load_flow(self):
        saved = read_optional(self.root / 'workspace-flow.json')
        if saved is None:
            return None
        key, transaction = saved.get('request_key'), saved.get('transaction')
        if (saved.get('schema') != 1 or not isinstance(key, str) or not PROOF_FORMAT.fullmatch(key)
                or transaction is not None and (type(transaction) is not str or not TX.fullmatch(transaction))
                or 'expected_authorizer_appid' in saved and (type(saved['expected_authorizer_appid']) is not str
                       or not APP.fullmatch(saved['expected_authorizer_appid']))
                or 'connection_id' in saved and type(saved['connection_id']) is not str
                or type(saved.get('state')) is not str
                or saved['state'] not in PUBLIC_STATES | {'START_RECOVERY_REQUIRED'}):
            _bad()
        return saved

    def _save_flow(self, saved):
        atomic_write(self.root / 'workspace-flow.json', {'schema': 1, **saved})

    def _project_status(self, code, value, action):
        if code == 200:
            return None
        if code == 401:
            return {'status': 'WORKSPACE_AUTHENTICATION_REQUIRED', 'http_status': code}
        if code == 403 and value.get('state') == 'WORKSPACE_REVOKED':
            return {'status': 'WORKSPACE_REVOKED', 'http_status': code}
        if code == 403:
            return {'status': 'WORKSPACE_NOT_REGISTERED', 'http_status': code}
        if code == 429 and value.get('state') == 'WORKSPACE_ENROLLMENT_LIMITED':
            return {'status': 'WORKSPACE_ENROLLMENT_RATE_LIMITED', 'http_status': code}
        if code == 409:
            return {'status': 'WORKSPACE_CONFLICT', 'http_status': code}
        if action == 'start' and code == 503 and value.get('state') == 'WECHAT_TICKET_OR_UPSTREAM_UNAVAILABLE':
            return {'status': 'TICKET_OR_COMPONENT_UNAVAILABLE', 'http_status': code}
        return {'status': 'WECHAT_COMPONENT_SERVICE_UNAVAILABLE', 'http_status': code}

    def _ensure_admitted(self, proof):
        code, value = self.transport.request('enrollment', proof)
        if code == 404 and value.get('state') == 'WORKSPACE_NOT_REGISTERED':
            code, value = self.transport.request('enroll', proof)
            if code == 201 and value.get('state') == 'WORKSPACE_PROVISIONAL':
                return None
        if code == 200 and value.get('state') in ('WORKSPACE_ACTIVE', 'WORKSPACE_PROVISIONAL'):
            return None
        status = self._project_status(code, value, 'enrollment')
        if status and status['status'] != 'WECHAT_COMPONENT_SERVICE_UNAVAILABLE':
            return status
        return {'status': 'WORKSPACE_ENROLLMENT_UNAVAILABLE', 'http_status': code}

    def _workspace_status(self, proof):
        code, value = self.transport.request('status', proof)
        failure = self._project_status(code, value, 'status')
        if failure is not None:
            return failure
        rows = _bindings(value.get('bindings'))
        self._save_bindings(rows)
        rows = self._cache()['rows']
        return {'status': 'WORKSPACE_READ', 'http_status': code, 'binding_count': len(rows),
                'active_count': sum(row['state'] == 'ACTIVE' for row in rows)}

    def _target_status(self, proof, target, cid, first_direct):
        if not target:
            return {'status': 'REAUTH_TARGET_UNAVAILABLE'}
        code, value = self.transport.request('status', proof, target=target)
        state = value.get('state')
        eligible = state == 'TARGET_READY' or (first_direct and state == 'LEGACY_TARGET_READY')
        if code == 200 and eligible and value.get('expected_authorizer_appid') == target:
            return {'status': state, 'http_status': code, 'account_id': target, 'connection_id': cid}
        if code == 409 and state == 'TARGET_BUSY' and value.get('expected_authorizer_appid') == target:
            return {'status': state, 'http_status': code}
        if code == 404 and state == 'TARGET_UNVERIFIED':
            return {'status': state, 'http_status': code}
        if code not in (200, 404):
            return self._project_status(code, value, 'target')
        return {'status': 'REAUTH_TARGET_UNCONFIRMED', 'http_status': code}

    def _profile_status(self, proof, target):
        cache = self._cache()
        row = next((r for r in (cache or {}).get('rows',[]) if r['appid'] == target and r['state'] == 'ACTIVE'), None)
        if row is None:
            return {'status': 'PROFILE_UNAVAILABLE'}
        code, value = self.transport.request('status', proof, profile=target)
        if (code != 200 or value.get('state') != 'ACTIVE' or value.get('appid') != target
                or value.get('originalId') != row['originalId']
                or type(value.get('generation')) is not int or value['generation'] != row['generation']):
            return {'status': 'PROFILE_UNAVAILABLE', 'http_status': code}
        info = clean_authorizer_info(value.get('authorizerInfo'))
        if not info:
            return {'status': 'PROFILE_UNAVAILABLE', 'http_status': code}
        rows = self._cache(include_removed=True)['rows']
        current = next(r for r in rows if r['appid'] == target)
        current['authorizerInfo'] = info
        self._save_bindings(rows, checked_at=cache['checked_at'])
        return {'status': 'PROFILE_READ', 'http_status': code, 'account_id': target}

    def _flow_status(self, proof, saved, action):
        tx = saved['transaction']
        code, value = self.transport.request(action, proof, transaction=tx)
        failure = self._project_status(code, value, action)
        if failure is not None:
            return failure
        return self._accept_flow(value, saved, code)

    def _accept_flow(self, value, saved, code):
        target = saved.get('expected_authorizer_appid')
        if target and value.get('expected_authorizer_appid') != target:
            return {'status': 'REAUTH_TARGET_UNCONFIRMED', 'http_status': code}
        result = _flow(value, saved.get('transaction'))
        if target and result.get('account_id', target) != target:
            self._save_flow(saved | {'transaction': result['transaction'], 'state': 'TARGET_MISMATCH'})
            return {'status': 'REAUTH_ACCOUNT_MISMATCH', 'http_status': code}
        if target and result.get('account_id') == target:
            result['connection_id'] = saved['connection_id']
        terminal = saved | {'transaction': result['transaction'], 'state': result['status']}
        if result['status'] == 'TARGET_MISMATCH':
            self._save_flow(terminal)
            return {'status': 'REAUTH_ACCOUNT_MISMATCH', 'http_status': code}
        account = result.get('binding')
        if account is not None:
            removed = self._removals()
            previous = removed.get(account['appid'])
            records = self._cache(include_removed=True)
            by_app = {row['appid']: row for row in (records or {}).get('rows', [])}
            current = by_app.get(account['appid'])
            if saved['state'] == 'BOUND':
                if (previous or not current or current['state'] != 'ACTIVE'
                        or current['generation'] != account['generation'] or current['originalId'] != account['originalId']):
                    return {'status': 'TARGET_STALE', 'http_status': code}
                result['binding'] = current
                result['http_status'] = code
                return result
            if current and (account['generation'] < current['generation']
                    or account['generation'] == current['generation'] and (
                        current['originalId'] != account['originalId'] or current['state'] == 'REVOKED'
                        or current['verifiedAt'] > account['verifiedAt'])):
                self._save_flow(terminal | {'state':'TARGET_STALE'})
                return {'status': 'TARGET_STALE', 'http_status': code}
            if previous and (previous['state'] == 'PENDING' or account['state'] != 'ACTIVE'
                    or account['generation'] <= previous['generation']):
                return {'status': 'REAUTH_TARGET_UNCONFIRMED', 'http_status': code}
            by_app[account['appid']] = account
            # Only a full workspace inventory can refresh other accounts.
            self._save_bindings(list(by_app.values()), checked_at=(records or {}).get('checked_at'))
            if previous:
                del removed[account['appid']]
                self._write_removals(removed)
        self._save_flow(terminal)
        result['http_status'] = code
        return result

    def _action(self, operation, proof, target=None, cid=None, first_direct=False):
        if target and self._removals().get(target, {}).get('state') == 'PENDING':
            return {'status': 'REAUTH_INTENT_CONFLICT'}
        if operation == 'PROFILE_STATUS':
            return self._profile_status(proof, target) if target else {'status':'PROFILE_UNAVAILABLE'}
        if operation == 'WORKSPACE_STATUS':
            return self._workspace_status(proof)
        saved = self._load_flow()
        active = saved is not None and (saved['state'] in ACTIVE or saved['state']=='START_RECOVERY_REQUIRED')
        if active and (saved.get('expected_authorizer_appid') != target or saved.get('connection_id') != cid):
            return {'status': 'REAUTH_INTENT_CONFLICT'}
        if operation == 'TARGET_STATUS':
            if active:
                return {'status': 'ORIGINAL_AUTHORIZATION_PENDING', 'account_id': target, 'connection_id': cid}
            return self._target_status(proof, target, cid, first_direct)
        if operation == 'STATUS':
            if active and saved['transaction'] is not None:
                return self._flow_status(proof, saved, 'status')
            if active:
                return {'status': 'START_RECOVERY_REQUIRED'}
            if target:
                if saved and saved.get('expected_authorizer_appid') == target and saved.get('connection_id') == cid and saved.get('transaction'):
                    return self._flow_status(proof, saved, 'status')
                return {'status': 'IDLE'}
            return self._workspace_status(proof)
        if operation == 'CANCEL':
            if active and saved['transaction'] is not None:
                return self._flow_status(proof, saved, 'cancel')
            return {'status': 'START_RECOVERY_REQUIRED' if active else 'IDLE'}
        if active and saved['transaction'] is not None:
            return self._flow_status(proof, saved, 'status')

        failure = self._ensure_admitted(proof)
        if failure is not None:
            return failure

        key = saved['request_key'] if active else secrets.token_urlsafe(32)
        intent = {'request_key': key, 'transaction': None, 'state': 'START_RECOVERY_REQUIRED'}
        options = {}
        if target:
            # Positive attestation before POST prevents older brokers which
            # ignore unknown JSON fields from allocating an unrestricted QR.
            ready = self._target_status(proof, target, cid, first_direct)
            if ready['status'] not in ('TARGET_READY', 'LEGACY_TARGET_READY'):
                return ready
            intent['expected_authorizer_appid'] = target
            intent['connection_id'] = cid
            options['target'] = target
        self._save_flow(intent)
        code, value = self.transport.request('start', proof, idempotency=key, **options)
        # The broker checks the existing idempotency key before these exact
        # pre-transaction responses. No new transaction was allocated.
        if target and ((code == 404 and value.get('state') == 'TARGET_UNVERIFIED')
                or (code == 409 and value.get('state') == 'TARGET_BUSY' and value.get('expected_authorizer_appid') == target)):
            self._save_flow(intent | {'state': 'REJECTED'})
            return {'status': value['state'], 'http_status': code}
        failure = self._project_status(code, value, 'start')
        if failure is not None:
            # A bare 503 does not identify the server-side transaction. Keep
            # the key until that exact request returns its persisted outcome.
            return failure
        # Idempotent POST /start gives the transaction view. GET /status
        # supplies its binding when that original response is already BOUND.
        if value.get('state') == 'BOUND' and 'binding' not in value:
            transaction = value.get('transaction')
            if type(transaction) is not str or not TX.fullmatch(transaction):
                _bad()
            if target and value.get('expected_authorizer_appid') != target:
                return {'status': 'REAUTH_TARGET_UNCONFIRMED', 'http_status': code}
            pending = intent | {'transaction': transaction, 'state': 'EXCHANGING'}
            self._save_flow(pending)
            return self._flow_status(proof, pending, 'status')
        return self._accept_flow(value, intent, code)

    def action(self, operation, connection_id=None):
        with self._lock:
            try:
                if connection_id is not None and operation == 'WORKSPACE_STATUS':
                    return {'status': 'REAUTH_INTENT_CONFLICT'}
                begin = operation == 'BEGIN'
                if begin and connection_id is None and not os.path.lexists(self.registry):
                    if os.path.lexists(self.root) and not os.path.lexists(self.registry):
                        return {'status': 'WORKSPACE_LOCAL_STATE_UNAVAILABLE'}
                    try:
                        prepare_local_workspace(self.registry)
                    except (OSError, WCEError):
                        return {'status': 'WORKSPACE_LOCAL_STATE_UNAVAILABLE'}
                if not os.path.lexists(self.registry):
                    return {'status': 'REAUTH_TARGET_UNAVAILABLE' if connection_id else 'WORKSPACE_PROOF_NOT_CONFIGURED'}
                proof = None if begin else self.proof.read()
                if not begin and proof is None:
                    return {'status': 'WORKSPACE_PROOF_NOT_CONFIGURED'}
                # Keep a single workspace proof and original request across windows
                # and across native MCP processes.
                container(self.registry.parent, self.root.name)
                with locked(self.root / 'workspace-flow.lock'):
                    target, first_direct = None, False
                    if connection_id is not None:
                        resolved = self._target(connection_id)
                        if resolved is None:
                            return {'status': 'REAUTH_TARGET_UNAVAILABLE'}
                        target, first_direct = resolved
                    if begin:
                        if connection_id is None:
                            try:
                                read_registry(self.registry)
                            except (OSError, WCEError):
                                return {'status': 'WORKSPACE_LOCAL_STATE_UNAVAILABLE'}
                        proof = self.proof.read()
                        if proof is None:
                            if (self._load_flow() is not None or self._cache(include_removed=True) is not None
                                    or self._removals()):
                                return {'status': 'WORKSPACE_PROOF_RECOVERY_REQUIRED'}
                            proof = self.proof.read(create=True)
                        if proof is None:
                            return {'status': 'WORKSPACE_PROOF_NOT_CONFIGURED'}
                    return self._action(operation, proof, target, connection_id, first_direct)
            except WCEError as error:
                if error.code in {'WECHAT_COMPONENT_SERVICE_UNAVAILABLE', 'WECHAT_WORKSPACE_KEYCHAIN_UNAVAILABLE',
                                  'WECHAT_WORKSPACE_PROOF_INVALID', 'WORKSPACE_LOCAL_STATE_UNAVAILABLE'}:
                    return {'status': error.code}
                raise

    def overview(self):
        """Read the last confirmed server snapshot without network or Keychain access."""
        with self._lock:
            cached = self._cache()
        if not cached:
            return []
        rows = []
        recent = self.clock() < cached['checked_at'] + 86400
        for row in cached['rows']:
            revoked = row['state'] == 'REVOKED'
            cid = _cid(row['appid'])
            profile = {'state': 'REVOKED' if revoked else 'ACTIVE' if recent else 'STALE',
                       'observed_at': row['verifiedAt'], 'original_id': row['originalId'],
                       'generation': row['generation']}
            if not revoked:
                refresh = row['refreshState'] if row['expiresAt'] > self.clock() else 'REQUIRED'
                profile.update(permissions=row['funcInfo'], refresh_state=refresh)
                if row.get('authorizerInfo'):
                    profile.update(official_profile_fields(row['authorizerInfo']))
            rows.append({'platform_id': WECHAT, 'connection_id': cid, 'account_id': row['appid'],
                         'state': 'ACTION_REQUIRED' if revoked or not recent else 'BOUND_IDLE',
                         'binding_provider': 'WECHAT_THIRD_PARTY',
                         'binding_revision': sha256(f'{cid}:{row["generation"]}:{row["state"]}'.encode()).hexdigest(),
                         'official_profile': profile,
                         'presentation': {'display_name': profile.get('nickname') or row['originalId'], 'state': 'SAVED',
                                          'name_source': 'WORKSPACE_AUTHORIZATION'}})
        return rows


class ComponentBindingRouter:
    def __init__(self, inner, registry, binding=None):
        self.inner = inner
        self.component_binding = binding or ComponentBinding(registry)

    def __getattr__(self, name):
        return getattr(self.inner, name)

    def list_tools(self):
        from .wechat_authorized_drafts import descriptor
        from .project_context_protocol import DISCONNECT
        from .wechat_component_removal import GENERATION
        rows = self.inner.list_tools()
        def describe(row):
            if row['name'] != DISCONNECT:
                return row
            spec = row['inputSchema']
            return row | {'inputSchema':spec | {'properties':spec['properties'] | {
                GENERATION:{'type':'integer','minimum':1}}}}
        return [describe(row) for row in rows] + [descriptor(), {
            'name': TOOL, 'title': '公众号管理员扫码绑定', 'inputSchema': SPEC,
            'description': 'Start, check or cancel the administrator QR authorization in this workspace.',
            'annotations': {'openWorldHint': True}, '_meta': {'ui': {'visibility': ['app']}},
        }]

    def call(self, name, args):
        from . import wechat_authorized_drafts as drafts
        from .project_context_protocol import DISCONNECT
        if name == DISCONNECT and args.get('platform_id') == WECHAT:
            from .wechat_component_removal import disconnect
            return disconnect(self.component_binding, self.inner, args)
        if name == drafts.TOOL:
            strict_validate(args,drafts.SPEC)
            permissions=frozenset((7,)) if args['action'].endswith('published') else frozenset((11,100))
            linked=drafts.account(self.component_binding,self.inner,args['connection_id'],permissions)
            return drafts.read(self.component_binding,linked,args)
        if name == TOOL:
            strict_validate(args, SPEC)
            if 'connection_id' in args:
                return self.component_binding.action(args['operation'], args['connection_id'])
            return self.component_binding.action(args['operation'])
        value = self.inner.call(name, args)
        if name == OVERVIEW:
            from .own_settings_protocol import read_platform_overview
            official, status = read_platform_overview(self.component_binding.overview)
            direct = {row.get('account_id'): row for row in value['connections']
                      if row.get('platform_id') == WECHAT and row.get('state') != 'DISCONNECTED'}
            for row in official or []:
                existing = direct.get(row['account_id'])
                authorized = row['official_profile']
                target = row if existing is None else existing
                # Direct official profile metadata can be fresher than the
                # grant. Keep the independently read authorization available.
                target['component_grant'] = {key:authorized[key] for key in
                    ('state','generation','permissions','observed_at') if key in authorized}
                if existing is None:
                    value['connections'].append(row)
                else:
                    original = existing.get('official_profile', {})
                    # Leave independently signed richer metadata intact. Grant and
                    # revocation come from the more recent confirmed authority.
                    if authorized['observed_at'] >= (original.get('observed_at') or 0):
                        existing['official_profile'] = (
                            original | authorized if original.get('state') == authorized['state']=='ACTIVE'
                            else authorized)
            removals, removal_status = read_platform_overview(self.component_binding._removals)
            if removals is None:
                status, removals = removal_status, {}
            value['connections'] = [entry for entry in value['connections'] if not (
                entry.get('platform_id') == WECHAT and entry.get('state') == 'DISCONNECTED'
                and removals.get(entry.get('account_id'), {}).get('connection_id') == entry.get('connection_id'))]
            value['wechat_component_read'] = status
        return value
