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
from .own_connection_policy import atomic_write, locked, read_optional, registry_path
from .own_connection_registry import container
from .prepared_contracts import strict_validate
from .tools import schema
from .wechat_workspace_proof import FORMAT as PROOF_FORMAT, WorkspaceProof

BASE = 'https://www.readysteadysound.com/jiusera/api/oauth/wechat'
TOOL = 'wce.ui.wechat.component_binding'
OVERVIEW = 'wce.ui.management.overview'
WECHAT = 'wechat_official_account'
APP = re.compile(r'wx[a-f0-9]{16}')
TX = re.compile(r'[a-f0-9]{48}')
PUBLIC_STATES = frozenset({'STARTING', 'PENDING', 'EXPIRED', 'CANCELLED',
    'TICKET_OR_COMPONENT_UNAVAILABLE', 'START_UNKNOWN', 'EXCHANGING', 'EXCHANGE_UNKNOWN',
    'REJECTED', 'WORKSPACE_CONFLICT', 'BOUND', 'REVOKED'})
ACTIVE = frozenset({'STARTING', 'PENDING', 'START_UNKNOWN', 'EXCHANGING', 'EXCHANGE_UNKNOWN'})
MAX_BODY = 256 * 1024
SPEC = schema({'operation': {'type': 'string', 'enum': ['BEGIN', 'STATUS', 'CANCEL', 'WORKSPACE_STATUS']}})


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

    def request(self, path, proof, *, transaction=None, idempotency=None):
        payload = None
        headers = {'Accept': 'application/json', 'Authorization': 'Bearer ' + proof.reveal_for_adapter()}
        if path == 'start':
            if type(idempotency) is not str or not PROOF_FORMAT.fullmatch(idempotency):
                _bad()
            headers['Idempotency-Key'] = idempotency
            payload = b'{}'
        elif path == 'cancel':
            if type(transaction) is not str or not TX.fullmatch(transaction):
                _bad()
            payload = json.dumps({'transaction': transaction}).encode('ascii')
        elif path != 'status':
            _bad()
        if payload is not None:
            headers['Content-Type'] = 'application/json'
        url = BASE + '/' + path
        if path == 'status' and transaction is not None:
            if type(transaction) is not str or not TX.fullmatch(transaction):
                _bad()
            url += '?' + urlencode({'transaction': transaction})
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

        if len(data) > MAX_BODY:
            _bad()
        try:
            value = json.loads(data)
        except (ValueError, RecursionError):
            raise WCEError('WECHAT_COMPONENT_SERVICE_UNAVAILABLE') from None
        if type(value) is not dict:
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

    def _cache(self):
        if not os.path.lexists(self.root):
            return None
        path_check(self.root, True)
        value = read_optional(self.root / 'workspace-bindings.json', MAX_BODY)
        if value is None:
            return None
        if value.get('schema') != 1 or not _timestamp(value.get('checked_at')):
            _bad()
        return {'checked_at': value['checked_at'], 'rows': _bindings(value.get('bindings'))}

    def _save_bindings(self, rows):
        atomic_write(self.root / 'workspace-bindings.json', {
            'schema': 1, 'checked_at': int(self.clock()), 'bindings': rows}, MAX_BODY)

    def _load_flow(self):
        saved = read_optional(self.root / 'workspace-flow.json')
        if saved is None:
            return None
        key, transaction = saved.get('request_key'), saved.get('transaction')
        if (saved.get('schema') != 1 or not isinstance(key, str) or not PROOF_FORMAT.fullmatch(key)
                or transaction is not None and (type(transaction) is not str or not TX.fullmatch(transaction))
                or type(saved.get('state')) is not str
                or saved['state'] not in PUBLIC_STATES | {'START_RECOVERY_REQUIRED'}):
            _bad()
        return saved

    def _save_flow(self, saved):
        atomic_write(self.root / 'workspace-flow.json', {'schema': 1, **saved})

    def _project_status(self, code, value, action):
        if code == 200:
            return None
        if code == 403:
            return {'status': 'WORKSPACE_NOT_REGISTERED', 'http_status': code}
        if code == 409:
            return {'status': 'WORKSPACE_CONFLICT', 'http_status': code}
        if action == 'start' and code == 503 and value.get('state') == 'WECHAT_TICKET_OR_UPSTREAM_UNAVAILABLE':
            return {'status': 'TICKET_OR_COMPONENT_UNAVAILABLE', 'http_status': code}
        return {'status': 'WECHAT_COMPONENT_SERVICE_UNAVAILABLE', 'http_status': code}

    def _workspace_status(self, proof):
        code, value = self.transport.request('status', proof)
        failure = self._project_status(code, value, 'status')
        if failure is not None:
            return failure
        rows = _bindings(value.get('bindings'))
        self._save_bindings(rows)
        return {'status': 'WORKSPACE_READ', 'http_status': code, 'binding_count': len(rows),
                'active_count': sum(row['state'] == 'ACTIVE' for row in rows)}

    def _flow_status(self, proof, saved, action):
        tx = saved['transaction']
        code, value = self.transport.request(action, proof, transaction=tx)
        failure = self._project_status(code, value, action)
        if failure is not None:
            return failure
        result = _flow(value, tx)
        self._save_flow({'request_key': saved['request_key'], 'transaction': result['transaction'],
                         'state': result['status']})
        account = result.get('binding')
        if account is not None:
            # Update the confirmed account immediately, then read the authoritative
            # workspace list on the next explicit refresh.
            records = self._cache()
            by_app = {row['appid']: row for row in records['rows']} if records else {}
            by_app[account['appid']] = account
            self._save_bindings(list(by_app.values()))
        result['http_status'] = code
        return result

    def _action(self, operation, proof):
        if operation == 'WORKSPACE_STATUS':
            return self._workspace_status(proof)
        saved = self._load_flow()
        active = saved is not None and (saved['state'] in ACTIVE or saved['state']=='START_RECOVERY_REQUIRED')
        if operation == 'STATUS':
            if active and saved['transaction'] is not None:
                return self._flow_status(proof, saved, 'status')
            if active:
                return {'status': 'START_RECOVERY_REQUIRED'}
            return self._workspace_status(proof)
        if operation == 'CANCEL':
            if active and saved['transaction'] is not None:
                return self._flow_status(proof, saved, 'cancel')
            return {'status': 'START_RECOVERY_REQUIRED' if active else 'IDLE'}
        if active and saved['transaction'] is not None:
            return self._flow_status(proof, saved, 'status')

        key = saved['request_key'] if active else secrets.token_urlsafe(32)
        self._save_flow({'request_key': key, 'transaction': None, 'state': 'START_RECOVERY_REQUIRED'})
        code, value = self.transport.request('start', proof, idempotency=key)
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
            pending = {'request_key': key, 'transaction': transaction, 'state': 'EXCHANGING'}
            self._save_flow(pending)
            return self._flow_status(proof, pending, 'status')
        result = _flow(value)
        self._save_flow({'request_key': key, 'transaction': result['transaction'], 'state': result['status']})
        result['http_status'] = code
        return result

    def action(self, operation):
        with self._lock:
            try:
                proof = self.proof.read(create=operation == 'BEGIN')
                if proof is None:
                    return {'status': 'WORKSPACE_PROOF_NOT_CONFIGURED'}
                # Scoped lock prevents two app/server processes from replacing the original.
                container(self.registry.parent, self.root.name)
                with locked(self.root / 'workspace-flow.lock'):
                    return self._action(operation, proof)
            except WCEError as error:
                if error.code in {'WECHAT_COMPONENT_SERVICE_UNAVAILABLE', 'WECHAT_WORKSPACE_KEYCHAIN_UNAVAILABLE',
                                  'WECHAT_WORKSPACE_PROOF_INVALID'}:
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
            rows.append({'platform_id': WECHAT, 'connection_id': cid, 'account_id': row['appid'],
                         'state': 'ACTION_REQUIRED' if revoked or not recent else 'BOUND_IDLE',
                         'binding_provider': 'WECHAT_THIRD_PARTY',
                         'binding_revision': sha256(f'{cid}:{row["generation"]}:{row["state"]}'.encode()).hexdigest(),
                         'official_profile': profile,
                         'presentation': {'display_name': row['originalId'], 'state': 'SAVED',
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
        return self.inner.list_tools() + [descriptor(), {
            'name': TOOL, 'title': '公众号管理员扫码绑定', 'inputSchema': SPEC,
            'description': 'Start, check or cancel the administrator QR authorization in this workspace.',
            'annotations': {'openWorldHint': True}, '_meta': {'ui': {'visibility': ['app']}},
        }]

    def call(self, name, args):
        from . import wechat_authorized_drafts as drafts
        if name == drafts.TOOL:
            strict_validate(args,drafts.SPEC)
            permissions=frozenset((7,)) if args['action'].endswith('published') else frozenset((11,100))
            linked=drafts.account(self.component_binding,self.inner,args['connection_id'],permissions)
            return drafts.read(self.component_binding,linked,args)
        if name == TOOL:
            strict_validate(args, SPEC)
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
            value['wechat_component_read'] = status
        return value
