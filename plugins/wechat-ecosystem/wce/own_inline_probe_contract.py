"""Explicit V2 display-only test contract; historical V1 catalog remains pinned."""
from copy import deepcopy
from hashlib import sha256
from pathlib import Path
import json
from .contracts import WCEError
from .service import digest

CONTRACT_SHA = '47088d1464dfa3c02c172bbd23536b6aaa0db05fc988a3586f19e095ac1ccf57'

def contract():
    raw=(Path(__file__).resolve().parents[1]/'contracts/ui-inline-account-probe-v2.json').read_bytes()
    if sha256(raw).hexdigest()!=CONTRACT_SHA:raise WCEError('INLINE_UI_CONTRACT_HOLD')
    return json.loads(raw)

def _legacy_present(actual):
    value=contract()
    if digest(sorted(actual,key=lambda x:x['name']))!=value['before_full_descriptor_sha256']:
        raise WCEError('INLINE_UI_CONTRACT_HOLD')
    rows=deepcopy(actual)
    for row in rows:
        if row['name'] in value['migrated_tools']:
            if row['_meta']['ui']['resourceUri']!=value['old_resource_uri']:raise WCEError('INLINE_UI_CONTRACT_HOLD')
            row['_meta']['ui']['resourceUri']=value['new_resource_uri']
    if digest(sorted(rows,key=lambda x:x['name']))!=value['after_full_descriptor_sha256']:raise WCEError('INLINE_UI_CONTRACT_HOLD')
    return rows


def present(actual):
    from .own_native_management_contract import present as native_present
    return native_present(_legacy_present(actual))

def normal_catalog(actual):
    from .own_native_management_contract import previous_catalog
    actual = previous_catalog(actual)
    value=contract()
    if type(actual) is not list or any(type(x) is not dict or type(x.get('name')) is not str for x in actual):raise WCEError('INLINE_UI_CONTRACT_HOLD')
    sha=digest(sorted(actual,key=lambda x:x['name']))
    if sha==value['before_full_descriptor_sha256']:return actual
    if sha!=value['after_full_descriptor_sha256']:raise WCEError('INLINE_UI_CONTRACT_HOLD')
    rows=deepcopy(actual)
    for row in rows:
        if row['name'] in value['migrated_tools']:
            if row['_meta']['ui']['resourceUri']!=value['new_resource_uri']:raise WCEError('INLINE_UI_CONTRACT_HOLD')
            row['_meta']['ui']['resourceUri']=value['old_resource_uri']
    if digest(sorted(rows,key=lambda x:x['name']))!=value['before_full_descriptor_sha256']:raise WCEError('INLINE_UI_CONTRACT_HOLD')
    return rows
