"""Non-secret Settings discovery. Enrollment is deliberately not an MCP tool."""
from copy import deepcopy
import threading

from .contracts import WCEError
from .prepared_contracts import ID, strict_validate
from .tools import schema

URI = 'ui://wechat-ecosystem/settings.html'
MIME = 'text/html;profile=mcp-app'
PREFIX = 'wce.settings.'
SAVE_NAME = 'wce.ui.management.save_display_name'
NAME_SPEC = schema({'connection_id': ID, 'account_id': {'type': 'string', 'pattern': '^wx[a-f0-9]{16}$'},
                    'binding_revision': {'type': 'string', 'pattern': '^[a-f0-9]{64}$'},
                    'expected_revision': {'type': 'integer', 'minimum': 0, 'maximum': 2**53 - 2},
                    'display_name': {'type': 'string', 'minLength': 1, 'maxLength': 64}})
SPECS = {
    PREFIX + 'read': schema({}),
    PREFIX + 'update': schema({'set': schema({})}),
    PREFIX + 'manage': schema({}),
    PREFIX + 'open': schema({}),
    PREFIX + 'add': schema({}),
}


def presentation_schema():
    avatar = schema({'width': {'type': 'integer', 'const': 96},
                     'height': {'type': 'integer', 'const': 96},
                     'rgba': {'type': 'string', 'minLength': 49152, 'maxLength': 49152,
                              'pattern': '^[A-Za-z0-9+/]{49152}$'}})
    return schema({
        'display_name': {'type': 'string', 'minLength': 1, 'maxLength': 64},
        'avatar': {'oneOf': [{'type': 'null'}, avatar]},
        'revision': {'oneOf': [{'type': 'null'}, {'type': 'integer', 'minimum': 0,
                                                'maximum': 2**53 - 1}]},
        'state': {'enum': ['MISSING', 'LEGACY', 'INVALID', 'SAVED', 'UNAVAILABLE']},
        'name_source': {'enum': ['REGISTRY_LABEL', 'LOCAL_USER', 'UNSET']},
        'avatar_source': {'enum': ['LOCAL_USER', 'UNSET']},
    })


def settings_value():
    return {'schema': schema({}), 'values': {}, 'layout': []}


def descriptors():
    names = {'read': '读取公众号设置', 'update': '公众号设置空更新',
             'manage': '管理公众号', 'open': '打开本机公众号管理页',
             'add': '添加公众号'}
    result = []
    for name, spec in SPECS.items():
        action = name.removeprefix(PREFIX)
        meta = {'ui': {'visibility': ['app']}}
        if action == 'manage':
            meta['ui']['resourceUri'] = URI
            meta['openai/ui'] = {'entrypoints': [{'type': 'thread'}]}
        if action in {'read', 'update'}:
            output = schema({'schema': {'type': 'object'}, 'values': schema({}),
                             'layout': {'type': 'array', 'items': {'type': 'object'}}})
        elif action == 'manage':
            output = schema({'connections': {'type': 'array', 'items': {
                'type': 'object', 'properties': ({k: {'type': 'string'} for k in
                    ('connection_id', 'account_id', 'label', 'state', 'error')} |
                    {'presentation': presentation_schema()}),
                'required': ['connection_id', 'state'], 'additionalProperties': False}},
                'platform_business_capabilities': {'const': 'NOT_VERIFIED'}})
        elif action == 'open':
            output = {'type': 'object', 'properties': {
                'state': {'enum': ['SETTINGS_OPENED', 'SETTINGS_ALREADY_OPEN']},
                'expires_in_seconds': {'const': 300}},
                'required': ['state'], 'additionalProperties': False}
        else:
            output = {'type': 'object', 'properties': {
                'state': {'enum': ['SETTINGS_ADD_READY', 'SETTINGS_ADD_NOT_CONFIRMED',
                                   'SETTINGS_ADD_UNKNOWN']}},
                'required': ['state'], 'additionalProperties': False}
        result.append({'name': name, 'title': names[action], 'inputSchema': deepcopy(spec),
            'outputSchema': output,
            'description': 'Non-secret plugin settings only. Never accepts credentials, approval or arbitrary URLs.',
            'annotations': {'readOnlyHint': action not in {'open', 'add'}, 'destructiveHint': False,
                            'openWorldHint': False, 'idempotentHint': action not in {'open', 'add'}},
            '_meta': meta})
        if action == 'manage':
            import base64
            from .own_settings_ui import LEGACY_LOGO
            result[-1]['title'] = 'WeChat Ecosystem'
            result[-1]['icons'] = [{
                'src': 'data:image/svg+xml;base64,' + base64.b64encode(LEGACY_LOGO.encode('utf-8')).decode('ascii'),
                'mimeType': 'image/svg+xml', 'sizes': ['any']}]
    return result


def overview(router, *, native=False):
    if native:
        from .own_volume_identity import snapshot_witnesses
        with snapshot_witnesses():
            return native_overview(router.registry)
    from .own_connection_policy import resolve
    from .own_presentation import read
    raw = router.call('own.connections.list', {})
    projected = []
    for item in raw['connections']:
        # Deliberately avoid private roots, dynamic lease details and opaque handles.
        row = {key: item[key] for key in
            ('connection_id', 'account_id', 'label', 'state', 'error') if key in item}
        try:
            policy = resolve(item['connection_id'], router.registry, active=False, readonly=native)
        except (WCEError, OSError, EOFError):
            policy = None
        if policy is not None:
            try:
                row['presentation'] = read(item['connection_id'], router.registry)
            except (WCEError, OSError, EOFError):
                pass
            else:
                projected.append(row)
                continue
        else:
            row['state'] = 'ACTION_REQUIRED'
            row['error'] = 'CONNECTION_ENTRY_UNAVAILABLE'
        row['presentation'] = {
            'display_name': '账号资料不可用', 'avatar': None, 'revision': None,
            'state': 'UNAVAILABLE', 'name_source': 'UNSET', 'avatar_source': 'UNSET'}
        projected.append(row)
    return {'connections': projected, 'platform_business_capabilities': 'NOT_VERIFIED'}


def native_overview(registry):
    """Read the local binding view without queuing behind live business calls."""
    import os
    from pathlib import Path
    from .own_connection_policy import read_registry, registry_path, resolve
    from .own_connection_registry import MembershipProofError, revoked
    from .own_connection_broker import RUNTIME, SOCKET
    from .own_presentation import project
    from .service import digest

    registry = Path(registry) if registry is not None else registry_path()
    registered = read_registry(registry)
    projected = []
    for cid in registered['connections']:
        entry = registered.get('entries', {}).get(cid)
        row = {'connection_id': cid, 'label': entry['label'] if entry else cid}
        try:
            policy = resolve(cid, registry, active=False, readonly=True)
            enabled = policy.value['enabled'] and (policy.value['schema'] != 2 or not revoked(policy))
        except (WCEError, OSError, EOFError) as error:
            check = error.check if isinstance(error, MembershipProofError) else None
            code = getattr(error, 'code', '')
            witness = code in {'CONNECTION_VOLUME_WITNESS_UNVERIFIED', 'INLINE_BINDING_CRYPTO_UNAVAILABLE'}
            storage = check in {'JOURNAL_DIRECTORY', 'ACCOUNT_ROOT', 'IMAGE_DIRECTORY', 'DATABASE'}
            kind = 'CHECK_LOCAL_BINDING'
            if witness:
                kind = 'CHECK_RECOVERY_WITNESS'
            elif storage:
                kind = 'STORAGE_IDENTITY_CHANGED'
            recovery = {'kind': kind}
            if witness:
                recovery['diagnostic'] = code
            if entry:
                recovery['registered_appid'] = entry['appid']
            if check:
                recovery['proof_check'] = check
            row.update(state='ACTION_REQUIRED', error='CONNECTION_ENTRY_UNAVAILABLE', recovery=recovery)
        else:
            endpoints = any(os.path.lexists(policy.root/name) for name in (SOCKET, RUNTIME))
            state = ('BOUND' if endpoints else 'BOUND_IDLE') if enabled else 'DISCONNECTED'
            row.update(state=state, account_id=policy.data['appid'], binding_revision=policy.fingerprint)
            binding = digest({'registry': str(registry), 'identity': policy.data,
                              'owner_digest': policy.value.get('owner_digest')})
            try:
                row['presentation'] = project(policy, binding, entry)
            except (WCEError, OSError, EOFError):
                pass
        row.setdefault('presentation', {'display_name': '账号资料不可用', 'avatar': None, 'revision': None,
                        'state': 'UNAVAILABLE', 'name_source': 'UNSET', 'avatar_source': 'UNSET'})
        projected.append(row)
    return {'connections': projected, 'platform_business_capabilities': 'NOT_VERIFIED'}


class SettingsManager:
    def __init__(self, router, factory=None, opener=None, required_budget=None, focuser=None, *, base_only=None):
        self.router, self.factory, self.opener = router, factory, opener
        self.focuser = focuser
        self.required_budget = required_budget
        self.base_only = base_only
        self.session = None
        self.launch_unknown = False
        self.lock = threading.Lock()

    @staticmethod
    def _untouched_session(session):
        """Only an unused management page can be replaced by another open click."""
        backend = getattr(session, 'backend', None)
        if backend is None:
            return False
        with session.lock:
            with backend.lock:
                navigation = session.navigation
                return (backend.state == 'READY' and backend.selected is None
                        and backend.review is None
                        and backend.pending_recovery is None
                        and backend.pending_publication is None
                        and getattr(backend, 'navigation_pending', True) is False
                        and type(backend.result) is dict
                        and backend.result.get('state') == 'NOT_SUBMITTED'
                        and (navigation is None
                             or navigation.get('state') in {'CANCELLED', 'COMPLETE'}))

    @classmethod
    def _revoke_untouched_session(cls, session):
        backend = getattr(session, 'backend', None)
        if backend is None:
            return False
        with session.lock:
            with backend.lock:
                if not cls._untouched_session(session):
                    return False
                # Keep admission locked until every old UI capability is revoked.
                session.close()
                return True

    def _check_closed_session(self):
        # A closed UI must not hide an applied/unknown navigation or an
        # in-flight backend operation, regardless of which opener is called.
        if self.session and self.session.closed.is_set():
            with self.session.lock:
                with self.session.backend.lock:
                    prior = self.session.navigation
                    if getattr(self.session.backend, 'navigation_pending', True) is not False:
                        raise WCEError('SETTINGS_NAVIGATION_UNKNOWN')
                    if prior and prior.get('state') in {'APPLIED', 'UNKNOWN'}:
                        raise WCEError('SETTINGS_NAVIGATION_UNKNOWN')
                    if (self.session.backend.state == 'ACTIVE'
                            or self.session.backend.pending_recovery is not None
                            or self.session.backend.pending_publication is not None):
                        raise WCEError('SETTINGS_BUSY')

    def open(self):
        with self.lock:
            if self.launch_unknown:
                if (self.session is None or not self.session.closed.is_set()
                        or not self._untouched_session(self.session)):
                    raise WCEError('SETTINGS_LAUNCH_UNKNOWN')
                self._check_closed_session()
                # The former listener and every UI capability are revoked.
                # This is another human page-open request, never an account retry.
                self.launch_unknown = False
            if self.session and not self.session.closed.is_set():
                try:
                    self.session.check()
                except WCEError as error:
                    if error.code != 'SETTINGS_EXPIRED' or not self._revoke_untouched_session(self.session):
                        raise
                # Safari activation cannot restore a closed or hidden tab.
                # Replace only a page revoked under its admission locks.
                if not self.session.closed.is_set() and not self._revoke_untouched_session(self.session):
                    from .own_settings_http import focus_browser
                    (self.focuser or focus_browser)()
                    self.session.check()
                    return {'state': 'SETTINGS_ALREADY_OPEN'}
            self._check_closed_session()
            if self.factory:
                self.session = self.factory()
            else:
                from .own_settings_http import SettingsSession
                from .own_settings_backend import SettingsBackend
                from .own_settings_ui import PAGE, CSP
                from .own_connection_check import CheckBudget
                from .own_connection_policy import registry_path
                registry = self.router.registry if self.router.registry is not None else registry_path()
                budget = CheckBudget(registry, self.required_budget)
                if budget.pins is not None:
                    self.required_budget = dict(budget.pins)
                self.session = SettingsSession(SettingsBackend(self.router.registry,
                    required_budget=self.required_budget,
                    base_only=(getattr(self.router, 'base_only', False) if self.base_only is None else self.base_only)), PAGE, CSP)
            try:
                return self.session.launch(self.opener) if self.opener else self.session.launch()
            except Exception as error:
                self.session.close()
                if isinstance(error, WCEError) and error.code == 'SETTINGS_LAUNCH_UNKNOWN':
                    self.launch_unknown = True
                    raise WCEError('SETTINGS_LAUNCH_UNKNOWN') from None
                raise WCEError('SETTINGS_OPEN_FAILED') from None

    def close(self):
        with self.lock:
            if self.session:
                self.session.close()

    def add(self):
        """Navigate the current trusted page, never perform enrollment."""
        with self.lock:
            if self.launch_unknown:
                return {'state': 'SETTINGS_ADD_UNKNOWN'}
            fresh = not self.session or self.session.closed.is_set()
            if fresh and self.session is not None:
                try:
                    self._check_closed_session()
                except WCEError as error:
                    if error.code == 'SETTINGS_NAVIGATION_UNKNOWN':
                        return {'state': 'SETTINGS_ADD_UNKNOWN'}
                    raise
            if fresh:
                if self.factory:
                    self.session = self.factory()
                else:
                    from .own_settings_http import SettingsSession
                    from .own_settings_backend import SettingsBackend
                    from .own_settings_ui import PAGE, CSP
                    from .own_connection_check import CheckBudget
                    from .own_connection_policy import registry_path
                    registry = self.router.registry if self.router.registry is not None else registry_path()
                    budget = CheckBudget(registry, self.required_budget)
                    if budget.pins is not None:
                        self.required_budget = dict(budget.pins)
                    self.session = SettingsSession(SettingsBackend(self.router.registry,
                        required_budget=self.required_budget,
                        base_only=(getattr(self.router, 'base_only', False) if self.base_only is None else self.base_only)), PAGE, CSP)
            session = self.session
            try:
                sequence = session.prepare_add(fresh=fresh)
                try:
                    if fresh:
                        session.launch(self.opener) if self.opener else session.launch()
                    from .own_settings_http import focus_browser
                    (self.focuser or focus_browser)()
                    session.enable_add(sequence)
                except Exception as error:
                    session.cancel_add(sequence)
                    if fresh:
                        session.close()
                    if isinstance(error, WCEError) and error.code == 'SETTINGS_LAUNCH_UNKNOWN':
                        self.launch_unknown = True
                        return {'state': 'SETTINGS_ADD_UNKNOWN'}
                    return {'state': 'SETTINGS_ADD_NOT_CONFIRMED'}
                return session.wait_add(sequence)
            except WCEError:
                if fresh:
                    session.close()
                raise


class DisplayNameRouter:
    """Add a scoped app-only write outside the frozen settings catalog."""

    def __init__(self, inner):
        self.inner = inner

    def __getattr__(self, key):
        return getattr(self.inner, key)

    def list_tools(self):
        return self.inner.list_tools() + [{
            'name': SAVE_NAME, 'title': '编辑公众号显示名称',
            'description': 'App-only. Updates only the local name of the specified bound WeChat account.',
            'inputSchema': deepcopy(NAME_SPEC), 'outputSchema': schema({
                'state': {'const': 'PRESENTATION_SAVED'}, 'connection_id': ID,
                'revision': {'type': 'integer', 'minimum': 1}}),
            'annotations': {'readOnlyHint': False, 'destructiveHint': False,
                            'openWorldHint': False, 'idempotentHint': False},
            '_meta': {'ui': {'visibility': ['app']}}}]

    def call(self, name, arguments):
        if name == SAVE_NAME:
            from .own_presentation import context, save
            from .own_connection_registry import revoked
            strict_validate(arguments, NAME_SPEC)
            registry = self.inner.original.registry
            cid = arguments['connection_id']

            def check_binding():
                policy, _, entry = context(cid, registry)
                if (entry is None or not policy.value['enabled'] or revoked(policy)
                        or policy.data['appid'] != arguments['account_id']
                        or policy.fingerprint != arguments['binding_revision']):
                    raise WCEError('PRESENTATION_IDENTITY_CHANGED')

            result = save({'connection_id': cid, 'expected_revision': arguments['expected_revision'],
                           'display_name': arguments['display_name'], 'avatar_png': None},
                          registry, check_binding)
            return {'state': result['state'], 'connection_id': cid,
                    'revision': result['presentation']['revision']}
        return self.inner.call(name, arguments)


class SettingsRouter:
    def __init__(self, original, manager=None):
        self.original = original
        self.prepared, self.own = original.prepared, original.own
        self.manager = manager or SettingsManager(original, base_only=True)
        self._inline_probe_meta = None
        from .own_native_management import NativeManagement
        self.management = NativeManagement()
        from .own_inline_binding import InlineBinding
        self.binding = InlineBinding(original.registry)

    def list_tools(self):
        from .own_production_rules_protocol import descriptors as production_descriptors
        from .own_article_status_protocol import descriptors as article_descriptors
        from .ui_readonly_entry import descriptors as ui_descriptors
        actual = self.original.list_tools() + descriptors() + production_descriptors() + article_descriptors() + ui_descriptors()
        from .own_inline_probe_contract import present
        from .own_connection_tools import analytics_descriptor
        return present(actual) + ([analytics_descriptor()] if not getattr(self.original, 'base_only', False) else [])

    def evidence(self):
        return self.original.evidence()

    def call(self, name, arguments):
        from .own_native_management_contract import OVERVIEW, ACTION
        if name == OVERVIEW:
            strict_validate(arguments, schema({}))
            from .own_platform_catalog import WECHAT, platforms
            value = overview(self.original, native=True)
            return dict(value, platforms=platforms(), connections=[dict(row, platform_id=WECHAT)
                for row in value['connections']])
        if name == ACTION:
            from .own_platform_catalog import perform
            return perform(arguments, self)
        from .ui_readonly_entry import NAMES as ui_names, call as ui_call
        if name in ui_names:
            return ui_call(name, arguments)
        from .own_article_status_protocol import READ, call as article_call
        if name==READ:return article_call(name,arguments,self.original.registry)
        from .own_production_rules_protocol import NAMES, call as production_call
        if name in NAMES:
            return production_call(name, arguments, self.original.registry)
        if name not in SPECS:
            return self.original.call(name, arguments)
        strict_validate(arguments, SPECS[name])
        if name in {PREFIX + 'read', PREFIX + 'update'}:
            return settings_value()
        if name == PREFIX + 'manage':
            return overview(self.original)
        if name == PREFIX + 'add':
            return self.manager.add()
        self._inline_probe_meta = None
        return self.manager.open()


def resource(method, params):
    from .mcp_stdio import RPCError
    from .own_inline_probe import configured, current, RESOURCE as PROBE_URI
    if method == 'resources/read' and params == {'uri': PROBE_URI} and configured():
        return current().resource()
    if method == 'resources/list' and not params:
        if configured():
            return {'resources': [{'uri': PROBE_URI, 'name': 'openahoy-management', 'title': 'Jiusera · 公众号管理', 'mimeType': MIME}, {'uri': URI, 'name': 'wechat-ecosystem-settings', 'title': 'Jiusera', 'mimeType': MIME}]}
        return {'resources': [{'uri': URI, 'name': 'wechat-ecosystem-settings',
                               'title': 'Jiusera', 'mimeType': MIME}]}
    if method == 'resources/read' and params == {'uri': URI}:
        from .own_settings_ui import MODAL
        return {'contents': [{'uri': URI, 'mimeType': MIME, 'text': MODAL,
            '_meta': {'ui': {'csp': {'connectDomains': [], 'resourceDomains': [],
                                    'frameDomains': []}},
                      'openai/ui': {'availableDisplayModes': ['inline', 'fullscreen'],
                                    'preferredDisplayMode': 'fullscreen'}}}]}
    raise RPCError(-32602, 'Invalid params')
