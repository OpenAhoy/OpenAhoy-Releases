"""Exact presentation-only catalog delta, independent of account authority."""
from copy import deepcopy
from hashlib import sha256
import json
from pathlib import Path

from .contracts import WCEError
from .service import digest

RESOURCE = 'ui://wechat-ecosystem/management-v5.html'
OVERVIEW = 'wce.ui.management.overview'
ACTION = 'wce.ui.platform.action'
ENTRIES = ('wce.settings.manage', 'wce.ui.show_management', 'wce.ui.open_management_page')
CONTRACT_SHA = 'feea82b9865f41c435ab945e52e847f4c2c425ceb2ea47f336ae7e62daf66679'


def contract():
    raw = (Path(__file__).resolve().parents[1] / 'contracts/native-management-v4.json').read_bytes()
    if sha256(raw).hexdigest() != CONTRACT_SHA:
        raise WCEError('NATIVE_UI_CONTRACT_HOLD')
    return json.loads(raw)


def present(rows):
    value = contract()
    if digest(sorted(rows, key=lambda r: r['name'])) != value['before_descriptor_sha256']:
        raise WCEError('NATIVE_UI_CONTRACT_HOLD')
    result = deepcopy(rows)
    for row in result:
        if row['name'] in ENTRIES:
            if row['_meta']['ui']['resourceUri'] != value['previous_resource_uri']:
                raise WCEError('NATIVE_UI_CONTRACT_HOLD')
            row['_meta']['ui']['resourceUri'] = RESOURCE
            row['title'] = value['entry_titles'][row['name']]['current']
        if row['name'] in value['entry_icons']:
            change = value['entry_icons'][row['name']]
            if row.get('icons') != change['previous']:
                raise WCEError('NATIVE_UI_CONTRACT_HOLD')
            row['icons'] = deepcopy(change['current'])
    result.append(deepcopy(value['overview_tool']))
    result.append(deepcopy(value['action_tool']))
    if digest(sorted(result, key=lambda r: r['name'])) != value['after_descriptor_sha256']:
        raise WCEError('NATIVE_UI_CONTRACT_HOLD')
    return result


def previous_catalog(rows):
    """Validate the entire new catalog before projecting its exact UI delta."""
    value = contract()
    actual = digest(sorted(rows, key=lambda r: r['name']))
    if actual == value['before_descriptor_sha256']:
        return rows
    if actual != value['after_descriptor_sha256']:
        raise WCEError('NATIVE_UI_CONTRACT_HOLD')
    result = [deepcopy(row) for row in rows if row['name'] not in {OVERVIEW, ACTION}]
    for row in result:
        if row['name'] in ENTRIES:
            if row['_meta']['ui']['resourceUri'] != RESOURCE:
                raise WCEError('NATIVE_UI_CONTRACT_HOLD')
            row['_meta']['ui']['resourceUri'] = value['previous_resource_uri']
            row['title'] = value['entry_titles'][row['name']]['previous']
        if row['name'] in value['entry_icons']:
            change = value['entry_icons'][row['name']]
            if row.get('icons') != change['current']:
                raise WCEError('NATIVE_UI_CONTRACT_HOLD')
            row['icons'] = deepcopy(change['previous'])
    if digest(sorted(result, key=lambda r: r['name'])) != value['before_descriptor_sha256']:
        raise WCEError('NATIVE_UI_CONTRACT_HOLD')
    return result


def overview_descriptor():
    return deepcopy(contract()['overview_tool'])
