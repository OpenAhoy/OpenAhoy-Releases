"""Select immutable lock-proof semantics from the saved recovery contract."""
from . import own_replacement_contract as contracts


def _module(manifest):
    contracts.validate_cases(manifest)
    if manifest['contract_sha'] == contracts.B5_CONTRACT_SHA:
        from . import own_body5_context as selected
    elif manifest['contract_sha'] == contracts.R3_CONTRACT_SHA:
        from . import own_replacement_unrelated_v3 as selected
    elif manifest['contract_sha'] == contracts.R2_CONTRACT_SHA:
        from . import own_replacement_unrelated_v2 as selected
    else:
        from . import own_replacement_unrelated as selected
    return selected


def build(registry, cases, receipt_sha, contract_sha):
    manifest = {'cases': cases, 'contract_sha': contract_sha}
    return _module(manifest).build(registry, cases, receipt_sha)


def immutable(registry, manifest, *, history=None):
    from .own_history_locators import checked
    history = checked(history, registry)
    selected = _module(manifest)
    if manifest['contract_sha'] == contracts.B5_CONTRACT_SHA:
        return selected.immutable(registry, manifest, history=history)
    return selected.immutable(registry, manifest)


def current(registry, manifest):
    return _module(manifest).current(registry, manifest)


def allowed(manifest, connection_id, kind):
    return _module(manifest).allowed(manifest, connection_id, kind)
