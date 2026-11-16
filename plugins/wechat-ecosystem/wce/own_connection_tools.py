"""Persistent personal plugin contracts; trusted enablement is not a tool."""
from copy import deepcopy
import os
from pathlib import Path

from .contracts import WCEError
from .own_contracts import SPECS as LEGACY, DOCUMENT_SPECS, validate as validate_legacy
from .own_connection_policy import read_registry, resolve, disconnect
from .own_connection_input import stage
from .own_connection_broker import call, ensure_started, stale_endpoint, SOCKET, RUNTIME
from .prepared_contracts import ID, MIME, ROLE, strict_validate
from .tools import schema

SPECS = deepcopy(LEGACY | DOCUMENT_SPECS)
from .normal_html_entry import ARGUMENTS as HTML_ARGUMENTS
SPECS['own.documents.prepare']={'oneOf':[SPECS['own.documents.prepare'],HTML_ARGUMENTS]}
from .own_editor_preferences import VALUES as EDITOR_VALUES, MAX_REVISION

# Closed original inventory input, retained for historical contract verification.
INVENTORY_PREPARE_SCHEMA=schema({'connection_id': ID,'inventory_handle': {'type': 'string', 'pattern': '^inventory-[a-f0-9]{48}$'}})

SPECS.update({
    'own.publications.current.prepare': {'oneOf': [
        deepcopy(INVENTORY_PREPARE_SCHEMA),
        schema({'connection_id': ID,'completed_slot_handle': {'type': 'string', 'pattern': '^completed-slot-[a-f0-9]{48}$'}})]},
    'own.publications.current.dispatch': schema({'connection_id': ID, 'intent_handle': ID}),
    'own.publications.current.status': schema({'connection_id': ID, 'intent_handle': ID}),
    'own.publications.current.poll': schema({'connection_id': ID, 'intent_handle': ID}),
    'own.publications.slots.discover': schema({'connection_id': ID}, {'cursor': {'type':'string','minLength':1,'maxLength':1024}}),
    'own.drafts.inventory': schema({'connection_id': ID}, {'cursor': {
        'type': 'string', 'maxLength': 96,
        'pattern': '^inventory-[a-f0-9]{48}-[1-9][0-9]{0,8}$'}}),
    'own.editor.preferences.read': schema({'connection_id': ID}),
    'own.editor.preferences.update': schema({'connection_id': ID,
        'expected_revision': {'type': 'integer', 'minimum': 0, 'maximum': MAX_REVISION - 1},
        'preferences': EDITOR_VALUES}),
    'own.connections.list': schema({}),
    'own.connections.status': schema({'connection_id': ID}),
    'own.connections.connect': schema({'connection_id': ID}),
    'own.connections.disconnect': schema({'connection_id': ID}),
    'own.uploads.reconcile': schema({'connection_id': ID, 'request_key': ID}),
    'own.drafts.locate': schema({'connection_id': ID, 'request_key': ID}),
    'own.assets.import': schema({'connection_id': ID, 'request_key': ID, 'role': ROLE,
        'declared_type': MIME, 'absolute_path': {'type': 'string', 'minLength': 1, 'maxLength': 4096}}),
})

for _name in ('own.publications.current.prepare', 'own.publications.slots.discover'):
    SPECS.pop(_name)


def validate(name, args):
    if name not in SPECS: raise WCEError('TOOL_NOT_IMPLEMENTED')
    strict_validate(args, SPECS[name], -16 if name in DOCUMENT_SPECS else 0)
    if (name in LEGACY or name in DOCUMENT_SPECS) and 'html_sources' not in args: validate_legacy(name, args)


def status(connection_id, registry=None):
    policy = resolve(connection_id, registry, active=False, readonly=True)
    base = {'connection_id': connection_id, 'account_id': policy.data['appid'],
        'capabilities': policy.value['capabilities'], 'platform_business_capabilities': 'NOT_VERIFIED',
        'provider_kind': 'OWN_DIRECT', 'label': connection_id}
    if policy.value['schema'] == 2:
        from .own_connection_registry import check_member, revoked
        entry = check_member(policy, revocation=False, readonly=True)
        base['label'] = entry['label']
        if revoked(policy): return base | {'state': 'DISCONNECTED'}
    if not policy.value['enabled']: return base | {'state': 'DISCONNECTED'}
    try: policy.check(readonly=True)
    except WCEError as error: return base | {'state': 'ACTION_REQUIRED', 'error': error.code}
    if not any(os.path.lexists(policy.root / p) for p in (SOCKET, RUNTIME)):
        return base | {'state': 'BOUND_IDLE'}
    try:
        return base | call(policy, 'own.connections.status', {'connection_id': connection_id})
    except WCEError as error:
        if error.code not in {'CONNECTION_RUNTIME_CHANGED', 'CONNECTION_START_PENDING',
                              'CONNECTION_RESULT_UNDETERMINED'}:
            raise
    except (OSError, EOFError):
        pass
    # A broker can disappear or retain pre-restart pins after membership was
    # authenticated. Check membership again before projecting this independently.
    policy.check(readonly=True)
    try:
        stale_endpoint(policy, readonly=True)
    except (WCEError, OSError, EOFError):
        policy.check(readonly=True)
        return base | {'state': 'BOUND', 'broker': 'STATUS_UNVERIFIED'}
    return base | {'state': 'BOUND_IDLE', 'broker': 'STOPPED_OR_STARTING'}


class ConnectionRouter:
    own, prepared = True, None

    def __init__(self, launcher=None, registry=None):
        self.launcher = launcher or Path(__file__).resolve().parents[1] / 'scripts' / 'wce_connection.py'
        self.registry = registry

    def evidence(self):
        return {'runtime': 'personal_account_connection', 'platform_ready': False, 'platform_verified': False}

    def list_tools(self):
        return [{'name': name, 'inputSchema': deepcopy(spec), 'description':
            ('Publish an explicitly requested draft using its original successful save attempt_id; '
             'dispatch submits once without follower push; status is local; poll queries the original task. '
             'Never resend UNKNOWN or infer publication permission from installation.'
             if name.startswith('own.publications.current.') else
             'Discover completed, verified production slots for this connection; no images or draft writes.'
             if name == 'own.publications.slots.discover' else
             'Read current draft inventory using existing draft_read authorization; no publication authorization.'
             if name == 'own.drafts.inventory' else
             'Select one human-enabled personal connection. Explicit user-requested images and drafts only; '
             'no public publication, credentials or enablement tool. Query original keys after uncertain results. '
             'UNKNOWN blocks the original and related article intents; never resend with a new key.')} for name, spec in SPECS.items()]

    def call(self, name, arguments):
        validate(name, arguments)
        if name == 'own.connections.list':
            # Global owner/resource conflicts remain fatal. A bad local policy
            # or broker only affects its own item; listing never starts tokens.
            registered = read_registry(self.registry)
            results = []
            for cid in registered['connections']:
                try:
                    results.append(status(cid, self.registry))
                except (WCEError, OSError, EOFError):
                    results.append({'connection_id': cid, 'provider_kind': 'OWN_DIRECT',
                        'state': 'ACTION_REQUIRED', 'error': 'CONNECTION_ENTRY_UNAVAILABLE'})
            return {'connections': results}
        if name == 'own.preflight' and 'connection_id' not in arguments:
            return self.evidence() | self.call('own.connections.list', {})
        cid = arguments['connection_id']
        if name in {'own.connections.status', 'own.preflight'}:
            return status(cid, self.registry)
        if name == 'own.connections.disconnect':
            return disconnect(resolve(cid, self.registry, active=False))
        if name == 'own.editor.preferences.read':
            from .own_editor_preferences import read
            return read(cid, self.registry)
        if name == 'own.editor.preferences.update':
            from .own_editor_preferences import update
            return update(arguments, self.registry)
        if name == 'own.publications.current.status':
            from .current_publication_service import local_status
            from .own_connection_policy import registry_path
            return local_status(resolve(cid, self.registry, active=False),
                self.registry or registry_path(), arguments['intent_handle'])
        policy = resolve(cid, self.registry)
        if name == 'own.documents.prepare' and 'html_sources' in arguments:
            from .normal_html_entry import prepare
            ensure_started(policy,self.launcher)
            def local_send(method,args):
                try:return call(policy,method,args)
                except (OSError,EOFError):
                    raise WCEError('CONNECTION_RESULT_UNDETERMINED_QUERY_ORIGINAL_KEY') from None
            return prepare(policy,arguments,local_send)
        if name == 'own.assets.import':
            relative = stage(policy, arguments['absolute_path'], arguments['declared_type'])
            arguments = {k: v for k, v in arguments.items() if k != 'absolute_path'} | {'relative_path': relative}
            name = 'own.assets.receive'
        ensure_started(policy, self.launcher)
        try:
            return call(policy, name, arguments)
        except (OSError, EOFError):
            # The request may have reached the journal or remote server. Never
            # reconnect and replay here; the caller must query the original key.
            raise WCEError('CONNECTION_RESULT_UNDETERMINED_QUERY_ORIGINAL_KEY') from None
