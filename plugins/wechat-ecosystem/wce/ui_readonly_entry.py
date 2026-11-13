"""Exact zero-data UI entry contract, separate from normal business delegation."""
from copy import deepcopy
import base64
from hashlib import sha256
from pathlib import Path
from .contracts import WCEError
from .service import canonical, digest
from .prepared_contracts import strict_validate
from .own_body5_upgrade import bounded_contract, read_bounded

CONTRACT_SHA = 'f351a0dd84350e2fee010555603685ef55d71025f27560fade358258254edec7'
NORMAL_ACTUAL_SHA = 'd2292a55e79dd29eb1444abe317d49f908c1858b608e4f03c577f0ccd0b56b92'
NORMAL_AUTHORITY_SHA = 'd2292a55e79dd29eb1444abe317d49f908c1858b608e4f03c577f0ccd0b56b92'
NAMES = frozenset(('wce.ui.show_management', 'wce.ui.open_management_page'))
VIEW_READY = {'state': 'MANAGEMENT_VIEW_READY'}


def fail():
    raise WCEError('UI_ENTRY_CONTRACT_HOLD')


def contract():
    raw = read_bounded(Path(__file__).resolve().parents[1] / 'contracts/ui-readonly-entry.json')
    if sha256(raw).hexdigest() != CONTRACT_SHA:
        fail()
    value = bounded_contract(raw)
    if (type(value) is not dict or type(value.get('schema')) is not int or value['schema'] != 1
            or value.get('profile') != 'WCE_READONLY_UI_ENTRIES_V1'
            or value.get('platform_authority') is not False or value.get('account_data_output') is not False
            or value.get('normal_actual_descriptor_sha256') != NORMAL_ACTUAL_SHA
            or value.get('normal_authority_descriptor_sha256') != NORMAL_AUTHORITY_SHA
            or type(value.get('tools')) is not list
            or {row['name'] for row in value['tools']} != NAMES):
        fail()
    return value


def descriptors():
    return deepcopy(contract()['tools'])


def call(name, arguments):
    specs = {row['name']: row['inputSchema'] for row in descriptors()}
    if name not in NAMES:
        fail()
    strict_validate(arguments, specs[name])
    return dict(VIEW_READY)


def normal_authority_projection(actual):
    from .own_native_management_contract import previous_catalog
    return [row for row in previous_catalog(actual) if row['name'] not in NAMES]
