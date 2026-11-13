"""Bounded, side-effect-free projection for the host's native settings view.

This is not a connection-health or platform-capability check. It never uses
broker, token or credential APIs and never opens or creates a settings page.
"""
from contextlib import ExitStack
import os
from pathlib import Path
import re

from .contracts import WCEError
from .own_bootstrap_security import path_check
from .own_connection_policy import code_scope, load_policy, locked, read_registry, registry_path
from .own_connection_registry import check_member, revoked
from .own_presentation import display_name, project
from .service import digest

UNAVAILABLE = '账号资料不可用 · 状态待检查'
PENDING = '资料待设置 · 状态待检查'
LIST_UNAVAILABLE = '公众号名单暂时不可用，请稍后重试。'
EMPTY = '暂无已绑定公众号，可选择“添加公众号”。'


def _read_lock(path):
    # No O_CREAT and no writable descriptor; lock itself is a short shared
    # nonblocking advisory read, validated both on entry and on exit.
    return locked(path, nonblocking=True, shared=True, existing=True, readonly=True)


def _name(presentation, identifiers, identities_complete):
    state = presentation.get('state')
    if state in {'MISSING', 'LEGACY'}:
        return '未设置名称'
    if state != 'SAVED' or presentation.get('name_source') != 'LOCAL_USER':
        return '账号资料不可用'
    name = presentation.get('display_name')
    try:
        if display_name(name) != name:
            return '未设置名称'
    except WCEError:
        return '未设置名称'
    # Every registered identity must be known before any free text is shown:
    # otherwise a different, unreadable account's ID could appear as a name.
    if not identities_complete:
        return '名称不可用'
    folded = name.casefold()
    if (any(identifier and identifier in folded for identifier in identifiers)
            or re.search(r'wx[0-9a-f]{16}', folded)
            or re.search(r'[0-9a-f]{32,}', folded)
            or re.search(r'(?:[a-z][a-z0-9+.-]*://|www\.)', folded)
            or any(char in name for char in '；;·|/\\\r\n\u2028\u2029')
            or any(status in name for status in (
                '已绑定', '已断开', '连接待恢复', '状态待检查',
                '资料待设置', '账号资料不可用', '名称不可用', '未设置名称'))):
        return '名称不可用'
    return name


def _fresh_empty(registry):
    """Only the completely absent container is a confirmed fresh empty state."""
    parent = registry.parent
    if os.path.lexists(parent):
        return False
    ancestor = parent.parent
    try:
        if ancestor.resolve(strict=True) != ancestor or not ancestor.is_dir():
            return False
        before = ancestor.stat()
        if before.st_uid != os.getuid():
            return False
        if os.path.lexists(parent):
            return False
        after = ancestor.stat()
        return (before.st_dev, before.st_ino, before.st_mtime_ns, before.st_ctime_ns) == (
            after.st_dev, after.st_ino, after.st_mtime_ns, after.st_ctime_ns)
    except OSError:
        return False


def names_description(registry=None):
    """Project current names and honest local binding state; never expose IDs.

    `registry` is internal dependency injection only, not a public tool argument.
    A globally invalid registry is unavailable, never an empty account list.
    Each registered account whose own locks/proof/presentation fail gets an
    independent safe placeholder, provided the global registry remains valid.
    """
    registry = Path(registry) if registry is not None else registry_path()
    if _fresh_empty(registry):
        return EMPTY
    global_lock = registry.parent / 'connections.lock'
    held = []
    try:
        with _read_lock(global_lock):
            initial = read_registry(registry)
            parent_pin = path_check(registry.parent, True)
        connections = initial['connections']
        if not connections:
            with _read_lock(global_lock):
                if read_registry(registry) != initial or path_check(registry.parent, True) != parent_pin:
                    return LIST_UNAVAILABLE
            return EMPTY
        # Match presentation-save order; never wait when another actor is active.
        # Hold all acquired per-account locks through the final registry/proof
        # recheck. A broken account cannot retain a partial lock set.
        with ExitStack() as all_locks:
            for cid in sorted(connections):
                policy_path = Path(connections[cid])
                account = {'cid': cid, 'path': policy_path, 'available': False, 'missing_display_lock': False}
                display_lock = policy_path.parent / 'presentation.lock'
                if not os.path.lexists(display_lock):
                    account['missing_display_lock'] = True
                local = ExitStack()
                try:
                    local.enter_context(_read_lock(display_lock))
                    local.enter_context(_read_lock(policy_path.parent / 'connection-policy.lock'))
                    all_locks.enter_context(local.pop_all())
                    account['available'] = True
                except (OSError, WCEError, ValueError):
                    local.close()
                held.append(account)
            with _read_lock(global_lock):
                current = read_registry(registry)
                if current != initial or path_check(registry.parent, True) != parent_pin:
                    return LIST_UNAVAILABLE
                scope = code_scope()
                rows = []
                verified = []
                identifiers = {cid.casefold() for cid in connections}
                for item in held:
                    if not item['available']:
                        # Missing local presentation + its never-created lock is
                        # an expected fresh-account case, not an empty registry.
                        root = item['path'].parent
                        missing = (item['missing_display_lock'] and
                                   not os.path.lexists(root / 'presentation.lock') and
                                   not os.path.lexists(root / 'presentation.json'))
                        rows.append(PENDING if missing else UNAVAILABLE)
                        continue
                    cid, path = item['cid'], item['path']
                    try:
                        policy = load_policy(path, active=False)
                        if (policy.data['connection_id'] != cid or
                                current['connections'].get(cid) != str(path)):
                            raise WCEError('CONNECTION_REGISTRY_CONFLICT')
                        entry = None
                        if current['schema'] == 2:
                            if policy.value.get('registry_path') != str(registry):
                                raise WCEError('CONNECTION_REGISTRY_CONFLICT')
                            entry = check_member(policy, revocation=False, readonly=True)
                        binding = digest({'registry': str(registry), 'identity': policy.data,
                                          'owner_digest': policy.value.get('owner_digest')})
                        presented = project(policy, binding, entry)
                        is_revoked = revoked(policy) if policy.value['schema'] == 2 else False
                        state = ('已断开' if is_revoked or not policy.value['enabled'] else
                                 '已绑定，连接待恢复' if policy.value['candidate_scope'] != scope else
                                 '已绑定')
                        identifiers.update(str(policy.data[key]).casefold() for key in
                                           ('appid', 'resource_id', 'connection_id'))
                        identifiers.update(value.casefold() for value in
                                           policy.data['actor'].values())
                        rows.append((presented, state))
                        verified.append((policy, entry, binding, presented, is_revoked))
                    except (OSError, WCEError, KeyError, TypeError, ValueError):
                        rows.append(UNAVAILABLE)
                # Recheck registry, policy pins, member proof, presentation and
                # revocation under exactly the same retained locks. Fail closed
                # globally when a previously accepted snapshot has drifted.
                if read_registry(registry) != initial or code_scope() != scope:
                    return LIST_UNAVAILABLE
                for policy, entry, binding, presented, was_revoked in verified:
                    if load_policy(policy.path, active=False) != policy:
                        return LIST_UNAVAILABLE
                    if policy.value['schema'] == 2:
                        if check_member(policy, revocation=False, readonly=True) != entry or revoked(policy) != was_revoked:
                            return LIST_UNAVAILABLE
                    if project(policy, binding, entry) != presented:
                        return LIST_UNAVAILABLE
                if read_registry(registry) != initial or path_check(registry.parent, True) != parent_pin:
                    return LIST_UNAVAILABLE
                complete = len(verified) == len(connections)
                return '；'.join(
                    row if isinstance(row, str) else
                    _name(row[0], identifiers, complete) + ' · ' + row[1]
                    for row in rows)
    except (OSError, WCEError, KeyError, TypeError, ValueError):
        return LIST_UNAVAILABLE
