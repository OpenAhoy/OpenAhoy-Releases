"""Durable per-account admitted disable actions, no credentials or network.

Only trusted SettingsBackend.admit may create an operation; no MCP entry. The
immutable initial receipt is established before disable can run. Indeterminate
operations remain blocked until the exact original event can be verified.
"""
from pathlib import Path
import os
import re
import time
from .contracts import WCEError
from .own_bootstrap_security import path_check
from .own_connection_policy import locked, read_optional
from .own_connection_enrollment import exclusive
from .own_connection_registry import container, sync
from .publication_contract import CONTRACT_SHA
from .service import digest

DIR = 'publication-settings-ops'
LOCK = 'publication-settings-ops.lock'
MAX_RECORDS = 1024
NAME = re.compile(r'op-(pub-setting-[a-f0-9]{32})\.json')
RESULT = re.compile(r'result-(pub-setting-[a-f0-9]{32})\.json')


def _error(code='PUBLICATION_SETTING_JOURNAL_INVALID'):
    raise WCEError(code)


def _op(value):
    if type(value) is not str or re.fullmatch(r'pub-setting-[a-f0-9]{32}', value) is None:
        _error('PUBLICATION_SETTING_OPERATION_INVALID')
    return value


def _folder(policy, create=False):
    path_check(policy.root, True)
    path = Path(policy.root) / DIR
    if not os.path.lexists(path):
        if not create:
            return None
        path = container(policy.root, DIR)
    path_check(path, True)
    return path


def _validate_policy(value):
    if value is None:
        return
    if (type(value) is not dict or set(value) != {'policy_id','revision','policy_sha','contract_sha','enabled'} or
            type(value['policy_id']) is not str or not re.fullmatch(r'pub-policy-[a-f0-9]{32}', value['policy_id']) or
            type(value['revision']) is not int or value['revision'] < 1 or
            type(value['enabled']) is not bool or
            any(type(value[k]) is not str or re.fullmatch('[a-f0-9]{64}', value[k]) is None for k in ('policy_sha','contract_sha')) or
            value['contract_sha'] != CONTRACT_SHA):
        _error()


def _validate(value, policy, store):
    fields = {'schema','operation_id','connection_id','account_key','binding_sha','policy_digest',
              'root_pin','database_pin','contract_sha','publication_expected_policy',
              'human_review_sha','confirmed_at_ms'}
    if type(value) is not dict or set(value) != fields or type(value['schema']) is not int or value['schema'] != 1:
        _error()
    _op(value['operation_id']);_validate_policy(value['publication_expected_policy'])
    if (value['connection_id'] != policy.data['connection_id'] or value['account_key'] != store.key or
            value['binding_sha'] != store.binding_sha or value['policy_digest'] != policy.fingerprint or
            value['root_pin'] != list(policy.root_pin) or value['database_pin'] != list(policy.database_pin[:2]) or
            value['contract_sha'] != CONTRACT_SHA or
            type(value['human_review_sha']) is not str or re.fullmatch('[a-f0-9]{64}',value['human_review_sha']) is None or
            type(value['confirmed_at_ms']) is not int or value['confirmed_at_ms'] <= 0):
        _error('PUBLICATION_SETTING_BINDING_CHANGED')
    return value


def _entries(policy, store):
    folder = _folder(policy)
    if folder is None:
        return []
    names = []
    with os.scandir(folder) as entries:
        for entry in entries:
            if len(names) >= MAX_RECORDS * 2:
                _error('PUBLICATION_SETTING_JOURNAL_LIMIT')
            names.append(entry.name)
    names.sort()
    ops, results = {}, {}
    for name in names:
        match = NAME.fullmatch(name) or RESULT.fullmatch(name)
        if not match:
            _error()
        target = ops if NAME.fullmatch(name) else results
        target[match.group(1)] = name
    if set(results) - set(ops) or len(ops) > MAX_RECORDS:
        _error()
    values = []
    for op_id,name in sorted(ops.items()):
        value = _validate(read_optional(folder/name), policy, store)
        if value['operation_id'] != op_id:
            _error()
        receipt = read_optional(folder/results[op_id]) if op_id in results else None
        if receipt is not None:
            if receipt != {'schema':1,'operation_id':op_id,'operation_sha':digest(value), 'state':'NO_CHANGE'}:
                _error()
            # Confirm any intact recovered no-change file is now durable. The
            # admission file was already synced before the operation ran.
            sync(folder/results[op_id]);sync(folder, directory=True)
        values.append((value,receipt))
    return values


def inspect(policy, store):
    """Read only plus fsync of an existing receipt; never creates/executes."""
    pending = []
    for value, receipt in _entries(policy, store):
        op_id = value['operation_id']
        if receipt is not None:
            continue
        try:
            event = store.operation_result(op_id)
        except Exception:
            event = None
        if event != {'operation_id':op_id,'state':'COMMITTED','operation':'DISABLE'}:
            pending.append(value)
    if len(pending) > 1:
        _error('PUBLICATION_SETTING_MULTIPLE_PENDING')
    return pending[0] if pending else None


def admit(policy, store, reviewed, guard):
    """Called after the original human review is verified; never calls disable."""
    op_id = _op(reviewed['proposed']['transaction'])
    expected = reviewed['publication_expected_policy'];_validate_policy(expected)
    with locked(Path(policy.root)/LOCK, nonblocking=True):
        guard()
        if inspect(policy,store) is not None:
            _error('PUBLICATION_DISABLE_RESULT_UNKNOWN')
        if store.setting_policy() != expected:
            _error('PUBLICATION_AUTHORITY_CHANGED')
        folder = _folder(policy,create=True)
        if len(_entries(policy,store)) >= MAX_RECORDS:
            _error('PUBLICATION_SETTING_JOURNAL_LIMIT')
        value = {'schema':1,'operation_id':op_id,'connection_id':policy.data['connection_id'],
            'account_key':store.key,'binding_sha':store.binding_sha,'policy_digest':policy.fingerprint,
            'root_pin':list(policy.root_pin),'database_pin':list(policy.database_pin[:2]),
            'contract_sha':CONTRACT_SHA,'publication_expected_policy':expected,
            'human_review_sha':digest({'display_sha':reviewed['publication_display_sha'],
                'nonce_sha':digest({'id':reviewed['id'],'approval':reviewed['approval']}),
                'confirmed_at':reviewed['confirmed_at']}),
            'confirmed_at_ms':int(reviewed['confirmed_at']*1000)}
        _validate(value,policy,store)
        exclusive(folder/('op-'+op_id+'.json'), value, path_check(folder,True))
        # Expiry here leaves the original admitted operation discoverable.
        guard()
        return value


def no_change(policy, store, reviewed, result):
    """Record only a direct synchronous no-change result, bound to admission."""
    op_id = _op(reviewed['proposed']['transaction'])
    if (result.get('state') != 'OFF' or result.get('enabled') is not False or
            result.get('operation_id') != op_id or
            result.get('durable') != {'state':'NO_CHANGE','publication':'DISABLE'}):
        _error()
    with locked(Path(policy.root)/LOCK, nonblocking=True):
        folder = _folder(policy)
        if folder is None:
            _error()
        operation = _validate(read_optional(folder/('op-'+op_id+'.json')),policy,store)
        expected = operation['publication_expected_policy']
        if expected is not None and expected['enabled'] is not False:
            _error('PUBLICATION_AUTHORITY_CHANGED')
        exclusive(folder/('result-'+op_id+'.json'),
                  {'schema':1,'operation_id':op_id,'operation_sha':digest(operation),'state':'NO_CHANGE'},
                  path_check(folder,True))


def result(policy, store, operation_id):
    op_id = _op(operation_id)
    found = [v for v in _entries(policy,store) if v[0]['operation_id'] == op_id]
    if len(found) != 1:
        _error('PUBLICATION_SETTING_OPERATION_UNKNOWN')
    operation, receipt = found[0]
    if receipt is not None:
        return {'state':'NO_CHANGE','operation_id':op_id}
    try:
        event = store.operation_result(op_id)
    except Exception:
        event = None
    return {'state':'OFF_CONFIRMED' if event == {'operation_id':op_id,'state':'COMMITTED','operation':'DISABLE'} else 'UNKNOWN',
            'operation_id':op_id}


def recent(policy, store):
    """Read the latest original operation after a page/process restart."""
    entries = _entries(policy, store)
    if not entries:
        return None
    operation, _ = max(entries, key=lambda pair:(pair[0]['confirmed_at_ms'],pair[0]['operation_id']))
    return result(policy, store, operation['operation_id'])
