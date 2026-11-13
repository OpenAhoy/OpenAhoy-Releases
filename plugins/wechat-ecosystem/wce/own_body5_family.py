"""Fixed single-case recovery namespace. Locator and budget facts, never a grant."""
from pathlib import Path
import os
import re
from .contracts import WCEError
from .own_bootstrap_security import path_check
from .service import digest
from . import own_replacement_files as files, own_replacement_contract as contracts

DIRECTORY = 'lineage-body5-recovery'
ANCHOR = 'body5-recovery-anchor.json'
PREFIX = 'replacement-body5-'


def fail():
    raise WCEError('OWN_BODY5_NAMESPACE_HOLD')


def is_body5_id(batch_id):
    return type(batch_id) is str and re.fullmatch(PREFIX + '[a-f0-9]{32}', batch_id) is not None


def root(registry):
    registry = Path(registry)
    if not registry.is_absolute() or registry.name != 'connections.json': fail()
    path_check(registry.parent, True)
    return registry.parent / DIRECTORY


def anchor(registry, *, required=False, history=None):
    registry = Path(registry)
    from .own_history_locators import checked
    history = checked(history, registry)
    folder = root(registry); target = registry.parent / ANCHOR
    exists = os.path.lexists(folder); recorded = os.path.lexists(target)
    if not exists and not recorded and not required: return None
    if not exists or not recorded: fail()
    value, checksum = files.read(target, 16384)
    expected = {'schema': 1, 'registry': str(registry),
        'registry_parent': list(path_check(registry.parent, True)), 'directory': DIRECTORY,
        'root_identity': list(path_check(folder, True)), 'case_id': contracts.B5_CASE_ID,
        'original_step_id': contracts.B5_CONTRACT['original_step_id']}
    physical = {'registry_parent', 'root_identity'}
    if (type(value) is not dict or set(value) != set(expected) or type(value.get('schema')) is not int
            or any(value[k] != v for k,v in expected.items() if k not in physical)): fail()
    if any(value[k] != expected[k] for k in physical):
        if history is None or not history.anchor(target, value): fail()
    files.folder(folder/'spent'); files.folder(folder/'stops')
    return value, checksum


def initialize(registry):
    """Trusted maintenance only; interrupted genesis is HOLD, never repaired."""
    registry = Path(registry)
    if anchor(registry) is not None: return
    # Caller holds the original shared execution lock and has checked all rows.
    folder = root(registry)
    files.folder(folder, create=True)
    files.folder(folder/'spent', create=True); files.folder(folder/'stops', create=True)
    value = {'schema': 1, 'registry': str(registry),
        'registry_parent': list(path_check(registry.parent, True)), 'directory': DIRECTORY,
        'root_identity': list(path_check(folder, True)), 'case_id': contracts.B5_CASE_ID,
        'original_step_id': contracts.B5_CONTRACT['original_step_id']}
    files.exclusive(registry.parent/ANCHOR, value)
    anchor(registry, required=True)


def check_id_contract(batch_id, contract_sha):
    old = (contracts.LEGACY_CONTRACT_SHA, contracts.R2_CONTRACT_SHA, contracts.R3_CONTRACT_SHA)
    if contract_sha == contracts.B5_CONTRACT_SHA:
        if not is_body5_id(batch_id): fail()
    elif contract_sha in old:
        if type(batch_id) is not str or re.fullmatch('replacement-batch-[a-f0-9]{32}', batch_id) is None: fail()
    else: fail()


def check_case(case):
    """Every production and synthetic case must bind the exact compiled original."""
    c = contracts.B5_CONTRACT; original = case.get('original', {})
    expected = {'original_step_id': c['original_step_id'], 'original_request_key': c['original_request_key'],
        'original_row_sha': c['original_row_sha'], 'original_intent_digest': c['original_intent_sha'],
        'selector': c['selector'], 'asset': c['asset'], 'lineage': c['lineage'], 'slot': c['asset']['slot']}
    if (case.get('case_id') != contracts.B5_CASE_ID or case.get('connection_id') != c['connection_id']
            or any(original.get(k) != v for k,v in expected.items())
            or digest(original.get('binding')) != c['binding_sha']
            or case.get('manifest_sha') != c['selector']['content_digest']
            or case.get('source_counts') != {'succeeded': 5, 'unsent': 0}): fail()


def old_pending(registry):
    from .own_replacement_batch import base
    folder = base(registry)
    from .own_body5_prepare import verify_old_source
    verify_old_source(registry)
    # This bounded recovery refuses every old active/history batch. A claim
    # without such a batch is an orphan, never a foreign allowance to ignore.
    files.folder(folder/'spent')
    if list((folder/'spent').iterdir()): fail()
    if (os.path.lexists(folder/'active-batch.json')
            or any(p.name.startswith('replacement-batch-') for p in folder.iterdir())): fail()
