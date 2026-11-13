"""Typed snapshots of a genuine request's exact already-saved draft set.

There is no batchget/list observation here.  In particular, absent list times
and list-response hashes are never manufactured to resemble a full inventory.
The normal broker supplies the sealed native authorization and HTTP transport.
"""
from hashlib import sha256
from pathlib import Path
import os
import re
import secrets
import time

from .publication_contract import binding, digest, exact, fail, stable_account
from .publication_store import read_file, sync_directory
from .own_bootstrap_security import path_check
from . import current_draft_inventory as legacy
from . import draft_group_wire as wire
from .bounded_file import file_state

PROFILE = 'REQUEST_SCOPED_SAVED_DRAFTS_V1'
PAGE_PROFILE = 'REQUEST_SCOPED_SAVED_DRAFT_PAGE_V1'
COVERAGE = 'COMPLETE_AUTHORIZED_SAVED_TARGETS'
PAGE_SIZE = 20  # A transport/read block, never a publication quota.
_META_NAME = re.compile(r'inventory-[a-f0-9]{48}(?:-request-page-[0-9]+)?\.json\Z')


def _need(value):
    if value is not True:
        fail('REQUESTED_DRAFT_SCOPE_CHANGED')


def _sha(value):
    return type(value) is str and len(value) == 64 and all(c in '0123456789abcdef' for c in value)


def _metadata_bytes(directory, name, maximum, guard):
    _need(type(name) is str and _META_NAME.fullmatch(name) is not None)
    guard(); parent_pin = path_check(directory, True)
    path = directory / name
    pin = path_check(path)
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    try:
        first = os.fstat(fd)
        _need(file_state(first) == pin and 0 < first.st_size <= maximum)
        parts, count = [], 0
        while count < first.st_size:
            guard()
            block = os.read(fd, min(65536, first.st_size - count))
            _need(bool(block)); parts.append(block); count += len(block)
        _need(file_state(os.fstat(fd)) == pin == path_check(path)
              and path_check(directory, True) == parent_pin)
        guard(); return b''.join(parts)
    finally:
        os.close(fd)


def _metadata_once(directory, name, raw, maximum, guard):
    _need(type(name) is str and _META_NAME.fullmatch(name) is not None
          and type(raw) is bytes and 0 < len(raw) <= maximum)
    guard(); pin = path_check(directory, True)
    parent = os.open(directory, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    temporary = '.request-inventory-' + secrets.token_hex(16)
    try:
        _need((os.fstat(parent).st_dev, os.fstat(parent).st_ino) == pin)
        fd = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW,
                     0o600, dir_fd=parent)
        try:
            with os.fdopen(fd, 'wb', closefd=False) as output:
                output.write(raw); output.flush(); os.fsync(fd)
        finally:
            os.close(fd)
        guard(); _need(path_check(directory, True) == pin)
        os.link(temporary, name, src_dir_fd=parent, dst_dir_fd=parent, follow_symlinks=False)
        os.unlink(temporary, dir_fd=parent); os.fsync(parent)
        _need(_metadata_bytes(directory, name, maximum, guard) == raw)
    finally:
        try: os.unlink(temporary, dir_fd=parent)
        except FileNotFoundError: pass
        os.close(parent)



def _durable_metadata(directory, name, maximum, guard):
    """Recover an acknowledged-visible immutable file before consuming it."""
    raw = _metadata_bytes(directory, name, maximum, guard)
    path = directory / name
    pin = path_check(path)
    parent_pin = path_check(directory, True)
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    parent = os.open(directory, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try:
        _need(file_state(os.fstat(fd)) == pin
              and (os.fstat(parent).st_dev, os.fstat(parent).st_ino) == parent_pin)
        guard(); os.fsync(fd); os.fsync(parent); guard()
        _need(path_check(path) == pin and path_check(directory, True) == parent_pin
              and _metadata_bytes(directory, name, maximum, guard) == raw)
    finally:
        os.close(parent); os.close(fd)
    return raw


def _page_name(handle, page):
    _need(type(handle) is str and legacy.HANDLE.fullmatch(handle) is not None
          and type(page) is int and page >= 0)
    return handle + '-request-page-' + str(page) + '.json'


def read_page(directory, handle, number, expected_sha, binding_sha, guard):
    from .publication_contract import strict_json
    _need(_sha(expected_sha))
    raw = _metadata_bytes(Path(directory), _page_name(handle, number), legacy.CHUNK_MAX, guard)
    _need(sha256(raw).hexdigest() == expected_sha)
    page = strict_json(raw, legacy.CHUNK_MAX)
    exact(page, 'profile handle page binding_sha256 request_identity config_sha256 '
          'total_groups observed_ms targets')
    _need(page['profile'] == PAGE_PROFILE and page['handle'] == handle
          and page['page'] == number and page['binding_sha256'] == binding_sha
          and _sha(page['request_identity']) and _sha(page['config_sha256'])
          and type(page['total_groups']) is int and page['total_groups'] > 0
          and type(page['observed_ms']) is int and page['observed_ms'] > 0
          and type(page['targets']) is list and 0 < len(page['targets']) <= PAGE_SIZE)
    targets = []
    for item in page['targets']:
        exact(item, 'reference snapshot_sha256 chunks')
        _need(_sha(item['snapshot_sha256']) and type(item['reference']) is str
              and type(item['chunks']) is list and bool(item['chunks']))
        parts = []
        total = 0
        for chunk in item['chunks']:
            exact(chunk, 'name sha256')
            _need(type(chunk['name']) is str and chunk['name'].startswith(handle + '-chunk-')
                  and _sha(chunk['sha256']))
            block = legacy._read_blob(Path(directory), chunk['name'], legacy.CHUNK_MAX, guard)
            total += len(block)
            _need(total <= legacy.SNAPSHOT_MAX and sha256(block).hexdigest() == chunk['sha256'])
            parts.append(block)
        body = b''.join(parts)
        _need(sha256(body).hexdigest() == item['snapshot_sha256'])
        target = strict_json(body, legacy.SNAPSHOT_MAX)
        exact(target, 'reference listed_update_time projection projection_sha256 response_sha256')
        _need(target['reference'] == item['reference'] and target['listed_update_time'] is None
              and digest(target['projection']) == target['projection_sha256']
              and _sha(target['response_sha256']))
        rows = target['projection'].get('response', {}).get('news_item')
        _need(type(rows) is list and 1 <= len(rows) <= 8)
        targets.append(target)
    guard()
    return page, targets


def _checkpoint(policy, handle, guard):
    _need(type(handle) is str and legacy.HANDLE.fullmatch(handle) is not None)
    directory = policy.root / 'current-draft-publication'
    value = read_file(directory / (handle + '.json'), legacy.INDEX_MAX)
    exact(value, 'profile inventory_handle connection_id binding_sha256 account_key coverage '
          'request_identity config_sha256 saved_proof_sha256 target_references '
          'total_groups observed_groups pages')
    _need(value['profile'] == PROFILE and value['inventory_handle'] == handle
          and value['connection_id'] == policy.data['connection_id']
          and value['binding_sha256'] == binding(policy.data)
          and value['account_key'] == stable_account(policy.data) and value['coverage'] == COVERAGE
          and _sha(value['request_identity']) and _sha(value['config_sha256'])
          and type(value['total_groups']) is int and value['total_groups'] > 0
          and value['observed_groups'] == value['total_groups']
          and type(value['saved_proof_sha256']) is list
          and len(value['saved_proof_sha256']) == value['total_groups']
          and all(_sha(x) for x in value['saved_proof_sha256'])
          and type(value['target_references']) is list
          and len(value['target_references']) == len(set(value['target_references'])) == value['total_groups']
          and all(type(x) is str and x for x in value['target_references'])
          and type(value['pages']) is list
          and len(value['pages']) == (value['total_groups'] + PAGE_SIZE - 1) // PAGE_SIZE)
    for index, page in enumerate(value['pages']):
        exact(page, 'page sha256 count observed_ms')
        _need(page['page'] == index and _sha(page['sha256'])
              and page['count'] == min(PAGE_SIZE, value['total_groups'] - index * PAGE_SIZE)
              and type(page['observed_ms']) is int and page['observed_ms'] > 0)
    guard()
    return value


def frozen_targets(policy, checkpoint, guard):
    directory = policy.root / 'current-draft-publication'
    observed = []
    for entry in checkpoint['pages']:
        page, targets = read_page(directory, checkpoint['inventory_handle'], entry['page'],
                                  entry['sha256'], binding(policy.data), guard)
        _need(page['request_identity'] == checkpoint['request_identity']
              and page['config_sha256'] == checkpoint['config_sha256']
              and page['total_groups'] == checkpoint['total_groups']
              and page['observed_ms'] == entry['observed_ms'] and len(targets) == entry['count'])
        for index, target in enumerate(targets):
            observed.append(target['reference'])
            yield page, index, entry['sha256'], target
    _need(observed == checkpoint['target_references'])
    guard()


def load_complete(policy, handle, guard):
    value = _checkpoint(policy, handle, guard)
    list(frozen_targets(policy, value, guard))
    return value


def matches_source(source, checkpoint):
    from .saved_groups_publication_source import is_saved_groups
    if not is_saved_groups(source) or checkpoint.get('profile') != PROFILE:
        return False
    return (checkpoint.get('coverage') == COVERAGE
        and checkpoint.get('connection_id') == source.connection_id
        and checkpoint.get('binding_sha256') == source.policy_binding
        and checkpoint.get('request_identity') == source.request_identity
        and checkpoint.get('config_sha256') == source.config_sha
        and checkpoint.get('saved_proof_sha256') == [p.sha256 for p in source.proofs]
        and checkpoint.get('target_references') == [p.value['reference'] for p in source.proofs]
        and checkpoint.get('observed_groups') == checkpoint.get('total_groups') == len(source.proofs))


def _public(policy, checkpoint, targets, *, recovered, get_count=0):
    return {'inventory_handle': checkpoint['inventory_handle'], 'profile': PROFILE,
        'connection_id': policy.data['connection_id'], 'coverage': COVERAGE,
        'scope': 'EXACT_NATIVE_REQUEST_SAVED_GROUPS_NOT_ACCOUNT_INVENTORY',
        'total_groups': len(targets), 'observed_groups': len(targets),
        'groups': [{'index': index, 'reference': target['reference'],
                    'article_count': len(target['projection']['response']['news_item']),
                    'titles': [a['title'] for a in target['projection']['response']['news_item']]}
                   for index, target in enumerate(targets)],
        'cursor': None, 'requests': {'list': 0, 'get': get_count},
        'snapshot_reused': recovered, 'publication_authority': False}


def execute(service, arguments, registry, deadline, guard, source):
    """Called only inside the original account broker's exact guarded stack."""
    from .http_transport import HTTPSender
    from .saved_groups_publication_source import is_saved_groups
    _need(is_saved_groups(source))
    policy = service.policy
    _need(source.policy_binding == binding(policy.data)
          and arguments.get('connection_id') == policy.data['connection_id'])
    source.fence()
    directory = policy.root / 'current-draft-publication'
    if not directory.exists():
        directory.mkdir(mode=0o700)
        sync_directory(directory.parent)
    path_check(directory, True)
    guard(); sync_directory(directory.parent); guard()
    handle = 'inventory-' + digest({'profile': PROFILE, 'request': source.request_identity,
        'config': source.config_sha, 'binding': source.policy_binding,
        'proofs': [p.sha256 for p in source.proofs]})[:48]
    cursor = arguments.get('cursor')
    _need(cursor is None)
    if os.path.lexists(directory / (handle + '.json')):
        _durable_metadata(directory, handle + '.json', legacy.INDEX_MAX, guard)
        checkpoint = load_complete(policy, handle, guard)
        _need(matches_source(source, checkpoint))
        targets = [item for _, _, _, item in frozen_targets(policy, checkpoint, guard)]
        for target in targets:
            source.validate_projection(target)
        source.fence()
        return _public(policy, checkpoint, targets, recovered=True)
    sender = service.workflow.sender
    _need(type(sender) is HTTPSender and sender.enabled)
    token = service.tokens.get(guard)
    entries = []
    get_count = 0
    refs = [proof.value['reference'] for proof in source.proofs]
    for number, start in enumerate(range(0, len(refs), PAGE_SIZE)):
        name = _page_name(handle, number)
        wanted = refs[start:start + PAGE_SIZE]
        if os.path.lexists(directory / name):
            page_raw = _durable_metadata(directory, name, legacy.CHUNK_MAX, guard)
            page_sha = sha256(page_raw).hexdigest()
            page, targets = read_page(directory, handle, number, page_sha, binding(policy.data), guard)
            _need(page['request_identity'] == source.request_identity
                  and page['config_sha256'] == source.config_sha and page['total_groups'] == len(refs)
                  and [t['reference'] for t in targets] == wanted)
            for target in targets:
                source.validate_projection(target)
        else:
            targets = []
            for reference in wanted:
                guard(); source.fence()
                _need(service.tokens.valid(token))
                timeout = min(30.0, deadline - time.monotonic(), token.wall_deadline - time.time())
                _need(timeout > 0)
                get_count += 1
                snapshot = wire.parse_get(sender.send(wire.encode_get(reference, token.token), timeout),
                                          token.token, reference)
                target = {'reference': reference, 'listed_update_time': None,
                    'projection': wire.baseline_projection(snapshot),
                    'projection_sha256': digest(wire.baseline_projection(snapshot)),
                    'response_sha256': snapshot.response_sha256}
                source.validate_projection(target)
                targets.append(target)
            records = []
            for target in targets:
                raw = legacy._bytes(target)
                _need(0 < len(raw) <= legacy.SNAPSHOT_MAX)
                nonce = secrets.token_hex(16)
                chunks = []
                for position in range(0, len(raw), legacy.CHUNK_MAX):
                    block = raw[position:position + legacy.CHUNK_MAX]
                    part = handle + '-chunk-' + nonce + '-' + str(position // legacy.CHUNK_MAX) + '.bin'
                    legacy._write_once(directory, part, block, legacy.CHUNK_MAX, guard)
                    chunks.append({'name': part, 'sha256': sha256(block).hexdigest()})
                records.append({'reference': target['reference'],
                    'snapshot_sha256': sha256(raw).hexdigest(), 'chunks': chunks})
            page = {'profile': PAGE_PROFILE, 'handle': handle, 'page': number,
                'binding_sha256': binding(policy.data), 'request_identity': source.request_identity,
                'config_sha256': source.config_sha, 'total_groups': len(refs),
                'observed_ms': int(time.time() * 1000), 'targets': records}
            raw = legacy._bytes(page)
            _metadata_once(directory, name, raw, legacy.CHUNK_MAX, guard)
            page_sha = sha256(raw).hexdigest()
        entries.append({'page': number, 'sha256': page_sha, 'count': len(targets),
                        'observed_ms': page['observed_ms']})
    checkpoint = {'profile': PROFILE, 'inventory_handle': handle,
        'connection_id': policy.data['connection_id'], 'binding_sha256': binding(policy.data),
        'account_key': stable_account(policy.data), 'coverage': COVERAGE,
        'request_identity': source.request_identity, 'config_sha256': source.config_sha,
        'saved_proof_sha256': [p.sha256 for p in source.proofs], 'target_references': refs,
        'total_groups': len(refs), 'observed_groups': len(refs), 'pages': entries}
    source.fence()
    _need(matches_source(source, checkpoint))
    _metadata_once(directory, handle + '.json', legacy._bytes(checkpoint), legacy.INDEX_MAX, guard)
    checked = load_complete(policy, handle, guard)
    all_targets = [item for _, _, _, item in frozen_targets(policy, checked, guard)]
    source.fence()
    return _public(policy, checked, all_targets, recovered=False, get_count=get_count)
