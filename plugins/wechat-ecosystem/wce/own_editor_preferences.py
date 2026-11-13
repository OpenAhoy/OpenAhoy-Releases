"""Per-account editorial defaults; never a grant, draft rewrite or token request."""
from copy import deepcopy
import os
from pathlib import Path
import unicodedata

from .contracts import WCEError
from .own_connection_policy import (read_registry, registry_path, load_policy, locked,
                                    atomic_write)
from .own_connection_registry import publication_locks, metadata
from .own_bootstrap_security import path_check
from .service import digest
from .tools import schema
from .prepared_contracts import ID, strict_validate

FILENAME = 'editor-preferences.json'
MAX_REVISION = 2**53 - 1
VALUES = schema({
    'author': {'type': 'string', 'maxLength': 64},
    'layout_profile': {'type': 'string', 'enum': ['source', 'reading-spacious-v1']},
    'cover_alignment': {'type': 'string', 'enum': ['source', 'left_square']},
    'summary_mode': {'type': 'string', 'enum': ['manual_required', 'custom']},
    'originality_intent': {'type': 'string', 'enum': ['review_required', 'not_requested']}})
DEFAULTS = {'author': '', 'layout_profile': 'reading-spacious-v1',
            'cover_alignment': 'left_square', 'summary_mode': 'manual_required',
            'originality_intent': 'not_requested'}


def validate(value):
    strict_validate(value, VALUES)
    if len(value['author']) > 16 or any(not c.isprintable() or unicodedata.category(c).startswith('C') for c in value['author']):
        raise WCEError('EDITOR_PREFERENCES_INVALID')
    return value


def context(connection_id, registry):
    """Read-only validation does not create a transaction lock or a prefs file."""
    strict_validate(connection_id, ID)
    registry = Path(registry) if registry is not None else registry_path()
    registered = read_registry(registry)
    if registered['schema'] != 2:
        raise WCEError('CONNECTION_UPGRADE_REVIEW_REQUIRED')
    path = registered['connections'].get(connection_id)
    if path is None:
        raise WCEError('CONNECTION_NOT_BOUND')
    policy = load_policy(path, active=False)
    if policy.value['schema'] != 2:
        raise WCEError('CONNECTION_UPGRADE_REVIEW_REQUIRED')
    if policy.data['connection_id'] != connection_id or (policy.value['schema'] == 2 and
            policy.value['registry_path'] != str(registry)):
        raise WCEError('CONNECTION_REGISTRY_CONFLICT')
    policy.check(readonly=True)
    binding = digest({'registry': str(registry), 'identity': policy.data,
                      'owner_digest': policy.value.get('owner_digest')})
    return policy, registry, binding


def value(policy, binding):
    path = policy.root / FILENAME
    if not os.path.lexists(path):
        return {'revision': 0, 'preferences': deepcopy(DEFAULTS)}
    record = metadata(path)
    if (type(record) is not dict or set(record) != {'schema', 'binding', 'revision', 'preferences'}
            or type(record['schema']) is not int or record['schema'] != 1
            or record['binding'] != binding or type(record['revision']) is not int
            or not 1 <= record['revision'] <= MAX_REVISION):
        raise WCEError('EDITOR_PREFERENCES_INVALID')
    validate(record['preferences'])
    return {'revision': record['revision'], 'preferences': deepcopy(record['preferences'])}


def read(connection_id, registry=None):
    policy, _, binding = context(connection_id, registry)
    result = value(policy, binding)
    policy.check(readonly=True)
    return {'connection_id': connection_id, **result, 'applies_to': 'NEW_EXPLICIT_DOCUMENTS_ONLY'}


def update(arguments, registry=None):
    strict_validate(arguments, schema({'connection_id': ID,
        'expected_revision': {'type': 'integer', 'minimum': 0, 'maximum': MAX_REVISION - 1},
        'preferences': VALUES}))
    preferences = validate(arguments['preferences'])
    policy, selected, binding = context(arguments['connection_id'], registry)
    # Same publication lock ordering as identity updates. A live broker is BUSY;
    # it is never signaled or bypassed to write defaults.
    with publication_locks([policy.root], selected), locked(policy.root / 'editor-preferences.lock', nonblocking=True):
        def admit():
            current, _, current_binding = context(arguments['connection_id'], selected)
            if (current_binding != binding or current.pin != policy.pin or current.root_pin != policy.root_pin):
                raise WCEError('CONNECTION_POLICY_CHANGED')
            if value(current, binding)['revision'] != arguments['expected_revision']:
                raise WCEError('EDITOR_PREFERENCES_STALE')
        admit()
        record = {'schema': 1, 'binding': binding, 'revision': arguments['expected_revision'] + 1,
                  'preferences': deepcopy(preferences)}
        admitted = False
        try:
            admit()
            admitted = True
            atomic_write(policy.root / FILENAME, record, expected_parent=policy.root_pin)
            policy.check(readonly=True)
            if value(policy, binding)['preferences'] != preferences or value(policy, binding)['revision'] != record['revision']:
                raise WCEError('EDITOR_PREFERENCES_WRITE_UNKNOWN')
        except Exception:
            if admitted:
                raise WCEError('EDITOR_PREFERENCES_WRITE_UNKNOWN') from None
            raise
    return {'state': 'EDITOR_PREFERENCES_SAVED', **read(arguments['connection_id'], selected)}
