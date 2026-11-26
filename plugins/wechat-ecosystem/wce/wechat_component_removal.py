"""Remove a local WeChat connection while retaining the remote grant and operation history."""
from hashlib import sha256

from .contracts import WCEError
from .own_connection_policy import locked
from .own_connection_registry import container
from .project_context_protocol import DISCONNECT, SPECS, validate

GENERATION = 'expected_grant_generation'


def _direct_rows(inner, appid, cid):
    from .wechat_component_binding import OVERVIEW, WECHAT
    snapshot = inner.call(OVERVIEW, {})
    if snapshot.get('platform_reads', {}).get(WECHAT, {}).get('state') == 'FAILED':
        raise WCEError('WECHAT_LOCAL_DISCONNECT_UNCONFIRMED')
    rows = []
    for row in snapshot['connections']:
        if row.get('platform_id') != WECHAT:
            continue
        account = row.get('account_id')
        if account is None:
            # A missing policy or unreachable registry must not be mistaken
            # for evidence that the selected account is QR-only.
            registered = (row.get('recovery') or {}).get('registered_appid')
            if row.get('connection_id') == cid or registered in (None, appid):
                raise WCEError('WECHAT_LOCAL_DISCONNECT_UNCONFIRMED')
        elif account == appid:
            rows.append(row)
    return rows


def disconnect(binding, inner, args):
    from .wechat_component_binding import ACTIVE, _cid
    base = {key: value for key, value in args.items() if key != GENERATION}
    validate(base, SPECS[DISCONNECT])
    generation = args.get(GENERATION)
    if GENERATION in args and (type(generation) is not int or not 0 < generation < 2**53):
        raise WCEError('PROJECT_ACCOUNT_MISMATCH')
    appid = base['account_id']
    cid = base['connection_id']
    revision = base['binding_revision']

    with binding._lock:
        container(binding.registry.parent, binding.root.name)
        with locked(binding.root / 'workspace-flow.lock'):
            flow = binding._load_flow()
            if (flow and flow['state'] in ACTIVE | {'START_RECOVERY_REQUIRED'}
                    and flow.get('expected_authorizer_appid') in (None, appid)):
                raise WCEError('WECHAT_AUTHORIZATION_IN_PROGRESS')
            records = binding._removals()
            saved = records.get(appid)
            cache = binding._cache(include_removed=True)
            grant = next((row for row in (cache or {}).get('rows', []) if row['appid'] == appid), None)
            rows = _direct_rows(inner, appid, cid)
            active = [row for row in rows if row.get('state') != 'DISCONNECTED']
            if len(active) > 1:
                raise WCEError('PROJECT_ACCOUNT_MISMATCH')
            direct = active[0] if active else None
            if direct and (direct['connection_id'] != cid or direct.get('binding_revision') != revision):
                raise WCEError('PROJECT_ACCOUNT_MISMATCH')

            # A new direct binding can reuse an old slot. Its revision must be
            # selected explicitly before its removal can replace the old record.
            matching = saved and saved['connection_id'] == cid and saved['revision'] == revision
            if saved and not matching and (saved['state'] == 'PENDING' or not direct):
                raise WCEError('PROJECT_ACCOUNT_MISMATCH')
            if matching:
                if generation is not None and saved['generation'] != generation:
                    raise WCEError('PROJECT_ACCOUNT_MISMATCH')
            else:
                visible = None if saved else grant
                expected_generation = visible['generation'] if visible else None
                if generation != expected_generation:
                    raise WCEError('PROJECT_ACCOUNT_MISMATCH')
                if not direct:
                    if not visible or cid != _cid(appid):
                        raise WCEError('PROJECT_ACCOUNT_MISMATCH')
                    expected = sha256(f"{cid}:{generation}:{visible['state']}".encode()).hexdigest()
                    if expected != revision:
                        raise WCEError('PROJECT_ACCOUNT_MISMATCH')
                saved = {'generation': grant['generation'] if grant else 0, 'connection_id': cid,
                         'revision': revision, 'state': 'PENDING', 'direct': bool(direct)}
                records[appid] = saved
                binding._write_removals(records)
            if direct:
                result = inner.call(DISCONNECT, base)
                if result.get('state') != 'DISCONNECTED' or result.get('connection_id') != cid:
                    raise WCEError('WECHAT_LOCAL_DISCONNECT_UNCONFIRMED')
            elif saved['state'] == 'PENDING' and saved['direct']:
                confirmed = any(row.get('connection_id') == cid and row['state'] == 'DISCONNECTED' for row in rows)
                if not confirmed:
                    raise WCEError('WECHAT_LOCAL_DISCONNECT_UNCONFIRMED')
            if saved['state'] != 'DISCONNECTED':
                saved['state'] = 'DISCONNECTED'
                binding._write_removals(records)
            return {'state': 'DISCONNECTED', 'connection_id': cid, 'remote_revocation': 'NOT_REQUESTED'}
