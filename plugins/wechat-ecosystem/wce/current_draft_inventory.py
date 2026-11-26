"""Read the current remote draft inventory under the existing draft_read grant.

Inventory observations never authorize publication or repair an old ADD. The
ordinary account broker owns the token, cancellation and connection checks.
"""
import os
import secrets
import time
import re
from hashlib import sha256
from dataclasses import dataclass
from pathlib import Path

from .contracts import WCEError
from .http_transport import HTTPSender
from .own_bootstrap_security import path_check
from .own_connection_policy import atomic_write
from . import draft_group_wire as wire
from .publication_contract import binding, stable_account
from .publication_store import read_file
from .bounded_file import file_state

METHOD = 'own.drafts.inventory'
PROFILE = 'CURRENT_REMOTE_DRAFT_INVENTORY_V1'
INDEX_MAX = 512 * 1024
SNAPSHOT_MAX = wire.MAX_BODY + 16384
HANDLE = re.compile(r'inventory-[a-f0-9]{48}\Z')
CURSOR = re.compile(r'(inventory-[a-f0-9]{48})-([1-9][0-9]{0,8})\Z')
CHUNK_MAX = 512 * 1024
MAX_PAGES = 4096
PAGE_PROFILE = 'CURRENT_INVENTORY_PAGE_V1'
CHECKPOINT_PROFILE = 'CURRENT_INVENTORY_CHECKPOINT_V1'
NAME = re.compile(r'inventory-[a-f0-9]{48}-(?:page-[0-9]{1,4}\.json|chunk-[a-f0-9]{32}-[0-9]{1,2}\.bin)\Z')


def fail(code):
    raise WCEError(code)


@dataclass(frozen=True)
class CurrentListPage:
    offset: int
    response_json: str
    response_sha256: str

    def value(self):
        from .publication_contract import strict_json
        if (type(self.offset) is not int or self.offset < 0 or self.offset % 20
                or type(self.response_sha256) is not str
                or not re.fullmatch('[a-f0-9]{64}', self.response_sha256)):
            fail('CURRENT_DRAFT_LIST_UNVERIFIED')
        value = strict_json(self.response_json.encode(), maximum=wire.MAX_BODY)
        if type(value) is not dict or not {'total_count', 'item_count', 'item'} <= set(value):
            fail('CURRENT_DRAFT_LIST_UNVERIFIED')
        total, count, items = value['total_count'], value['item_count'], value['item']
        if (type(value.get('errcode', 0)) is not int or value.get('errcode', 0) != 0
                or type(total) is not int or not 0 <= total < 2**31
                or type(count) is not int or not 0 <= count <= 20
                or type(items) is not list or len(items) != count
                or count != min(20, max(0, total - self.offset))
                or total and self.offset >= total or not total and self.offset != 0):
            fail('CURRENT_DRAFT_LIST_UNVERIFIED')
        refs = []
        for item in items:
            if (type(item) is not dict or not {'media_id', 'update_time'} <= set(item)
                    or type(item['update_time']) is not int
                    or not 0 <= item['update_time'] < 2**63):
                fail('CURRENT_DRAFT_LIST_UNVERIFIED')
            wire._reference(item['media_id'], False)
            refs.append(item['media_id'])
        if len(set(refs)) != len(refs):
            fail('CURRENT_DRAFT_INVENTORY_DUPLICATE')
        return value


def parse_page(response, token, offset):
    from hashlib import sha256
    value = wire.response_value(response, token, list_response=True)
    page = CurrentListPage(offset, wire.canonical(value), sha256(response.body).hexdigest())
    page.value()
    return page


def scan(read_page, read_draft, guard, *, offset=0, expected_total=None, max_pages=10):
    """Bounded read orchestration; callbacks supply observations, not grants.

    One pagination walk identifies this request's inventory. Every listed
    object requires its own full GET. An unrelated later inventory change is
    not a prerequisite for submitting an independently frozen target.
    """
    pages = []
    items = []
    total = expected_total
    if (type(offset) is not int or offset < 0 or offset % 20
            or type(max_pages) is not int or not 1 <= max_pages <= 10):
        fail('CURRENT_DRAFT_LIST_UNVERIFIED')
    first_offset = offset
    for offset in range(first_offset, first_offset + max_pages * 20, 20):
        guard()
        page = read_page(offset)
        if type(page) is not CurrentListPage:
            fail('CURRENT_DRAFT_LIST_UNVERIFIED')
        value = page.value()
        if page.offset != offset:
            fail('CURRENT_DRAFT_LIST_OFFSET_CHANGED')
        if total is None:
            total = value['total_count']
        if total != value['total_count']:
            fail('CURRENT_DRAFT_INVENTORY_CHANGED')
        pages.append(page)
        items.extend(value['item'])
        if first_offset + len(items) >= total:
            break
    guard()
    if total is None:
        fail('CURRENT_DRAFT_INVENTORY_PARTIAL')
    refs = [item['media_id'] for item in items]
    if len(set(refs)) != len(refs):
        fail('CURRENT_DRAFT_INVENTORY_DUPLICATE')
    targets = []
    for item in items:
        guard()
        snapshot = read_draft(item['media_id'])
        if (type(snapshot) is not wire.GroupSnapshot
                or snapshot.reference != item['media_id']):
            fail('CURRENT_DRAFT_GET_UNVERIFIED')
        projection = wire.baseline_projection(snapshot)
        targets.append({'reference': snapshot.reference,
            'listed_update_time': item['update_time'],
            'projection': projection,
            'projection_sha256': wire.digest(projection),
            'response_sha256': snapshot.response_sha256})
        guard()
    return {'profile': PROFILE, 'platform_atomic': False,
        'coverage': ('COMPLETE_OBSERVED_PAGINATION' if first_offset + len(items) == total
                     else 'PARTIAL_CONTINUATION_REQUIRED'),
        'list_response_sha256': [p.response_sha256 for p in pages],
        'total_groups': total, 'targets': targets,
        'next_offset': first_offset + len(items),
        'requests': {'list': len(pages), 'get': len(targets)},
        'publication_authority': False}


def _bytes(value):
    return wire.canonical(value).encode('utf-8')


def _read_blob(directory, name, maximum, guard):
    if type(name) is not str or NAME.fullmatch(name) is None:
        fail('CURRENT_DRAFT_SNAPSHOT_CHANGED')
    guard()
    pin = path_check(directory, True)
    path = directory / name
    before = path_check(path)
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    try:
        first = os.fstat(fd)
        if file_state(first) != before or not 0 < first.st_size <= maximum:
            fail('CURRENT_DRAFT_SNAPSHOT_CHANGED')
        chunks, size = [], 0
        while size < first.st_size:
            guard()
            chunk = os.read(fd, min(65536, first.st_size - size))
            if not chunk:
                fail('CURRENT_DRAFT_SNAPSHOT_CHANGED')
            chunks.append(chunk)
            size += len(chunk)
        if (file_state(os.fstat(fd)) != before or path_check(path) != before
                or path_check(directory, True) != pin):
            fail('CURRENT_DRAFT_SNAPSHOT_CHANGED')
        guard()
        return b''.join(chunks)
    finally:
        os.close(fd)


def _write_once(directory, name, raw, maximum, guard):
    if (type(name) is not str or NAME.fullmatch(name) is None or type(raw) is not bytes
            or not 0 < len(raw) <= maximum):
        fail('CURRENT_DRAFT_SNAPSHOT_LIMIT')
    guard()
    pin = path_check(directory, True)
    parent = os.open(directory, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    temporary = '.inventory-' + secrets.token_hex(16)
    try:
        if (os.fstat(parent).st_dev, os.fstat(parent).st_ino) != pin:
            fail('CURRENT_DRAFT_SNAPSHOT_CHANGED')
        fd = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW,
                     0o600, dir_fd=parent)
        try:
            with os.fdopen(fd, 'wb', closefd=False) as output:
                output.write(raw)
                output.flush()
                os.fsync(fd)
        finally:
            os.close(fd)
        guard()
        if path_check(directory, True) != pin:
            fail('CURRENT_DRAFT_SNAPSHOT_CHANGED')
        # The final name is immutable and never replaces a previous page.
        os.link(temporary, name, src_dir_fd=parent, dst_dir_fd=parent, follow_symlinks=False)
        os.unlink(temporary, dir_fd=parent)
        os.fsync(parent)
        if _read_blob(directory, name, maximum, guard) != raw:
            fail('CURRENT_DRAFT_SNAPSHOT_CHANGED')
    finally:
        try:
            os.unlink(temporary, dir_fd=parent)
        except FileNotFoundError:
            pass
        os.close(parent)


def _page_name(handle, number):
    if type(number) is not int or not 0 <= number < MAX_PAGES:
        fail('CURRENT_DRAFT_CURSOR_INVALID')
    return handle + '-page-' + str(number) + '.json'


def _read_page(directory, handle, number, expected_sha, binding_sha, guard):
    from .publication_contract import strict_json
    raw = _read_blob(directory, _page_name(handle, number), CHUNK_MAX, guard)
    if sha256(raw).hexdigest() != expected_sha:
        fail('CURRENT_DRAFT_SNAPSHOT_CHANGED')
    page = strict_json(raw, CHUNK_MAX)
    expected = {'profile','handle','page','binding_sha256','previous_sha256',
                'total_groups','next_offset','coverage','list_response_sha256','targets','observed_ms'}
    if (type(page) is not dict or set(page) != expected or page['profile'] != PAGE_PROFILE
            or page['handle'] != handle or page['page'] != number
            or page['binding_sha256'] != binding_sha or type(page['targets']) is not list
            or len(page['targets']) > 20 or type(page['observed_ms']) is not int
            or page['observed_ms'] <= 0):
        fail('CURRENT_DRAFT_SNAPSHOT_CHANGED')
    targets = []
    for item in page['targets']:
        if (type(item) is not dict or set(item) != {'reference','snapshot_sha256','chunks'}
                or type(item['chunks']) is not list or not 1 <= len(item['chunks']) <= 5
                or type(item['snapshot_sha256']) is not str):
            fail('CURRENT_DRAFT_SNAPSHOT_CHANGED')
        blob_parts = []
        for chunk in item['chunks']:
            if type(chunk) is not dict or set(chunk) != {'name','sha256'}:
                fail('CURRENT_DRAFT_SNAPSHOT_CHANGED')
            if not chunk['name'].startswith(handle + '-chunk-'):
                fail('CURRENT_DRAFT_SNAPSHOT_CHANGED')
            block = _read_blob(directory, chunk['name'], CHUNK_MAX, guard)
            if sha256(block).hexdigest() != chunk['sha256']:
                fail('CURRENT_DRAFT_SNAPSHOT_CHANGED')
            blob_parts.append(block)
        blob = b''.join(blob_parts)
        if len(blob) > SNAPSHOT_MAX or sha256(blob).hexdigest() != item['snapshot_sha256']:
            fail('CURRENT_DRAFT_SNAPSHOT_CHANGED')
        target = strict_json(blob, SNAPSHOT_MAX)
        if (type(target) is not dict or set(target) != {'reference','listed_update_time',
                'projection','projection_sha256','response_sha256'}
                or target['reference'] != item['reference']
                or wire.digest(target['projection']) != target['projection_sha256']):
            fail('CURRENT_DRAFT_SNAPSHOT_CHANGED')
        targets.append(target)
    return page, targets


def _read_chain(directory, checkpoint, binding_sha, guard, wanted_page=None):
    handle = checkpoint['inventory_handle']
    head = checkpoint['head_page']
    if (type(head) is not int or not 0 <= head < MAX_PAGES
            or type(checkpoint['head_sha256']) is not str):
        fail('CURRENT_DRAFT_SNAPSHOT_CHANGED')
    expected_sha = checkpoint['head_sha256']
    selected = None
    seen = set()
    total = checkpoint['total_groups']
    for number in range(head, -1, -1):
        page, targets = _read_page(directory, handle, number, expected_sha, binding_sha, guard)
        if any(t['reference'] in seen for t in targets):
            fail('CURRENT_DRAFT_INVENTORY_DUPLICATE')
        seen.update(t['reference'] for t in targets)
        observed = number * 20 + len(targets)
        if (page['total_groups'] != total or page['next_offset'] != observed
                or page['coverage'] != ('COMPLETE_OBSERVED_PAGINATION' if observed == total
                    else 'PARTIAL_LIMIT_REACHED' if number + 1 == MAX_PAGES
                    else 'PARTIAL_CONTINUATION_REQUIRED')
                or (number < head and len(targets) != 20)
                or (number == head and (checkpoint['observed_groups'] != observed
                    or checkpoint['coverage'] != page['coverage']))):
            fail('CURRENT_DRAFT_SNAPSHOT_CHANGED')
        if number == wanted_page:
            selected = (page, targets)
        expected_sha = page['previous_sha256']
    if expected_sha is not None:
        fail('CURRENT_DRAFT_SNAPSHOT_CHANGED')
    if wanted_page is not None and selected is None:
        fail('CURRENT_DRAFT_SNAPSHOT_CHANGED')
    return selected, seen


def execute(service, arguments, deadline, cancel_guard=None, *, current_authority=None):
    """Normal account broker only; serial lock and original admission deadline held."""
    policy = service.policy
    if (type(arguments) is not dict or set(arguments) - {'connection_id', 'cursor'}
            or arguments.get('connection_id') != policy.data['connection_id']):
        fail('CONNECTION_SCOPE_MISMATCH')
    if 'draft_read' not in policy.value['capabilities']:
        fail('OWN_ACCESS_DENIED')
    initial_binding = binding(policy.data)
    account_key = stable_account(policy.data)

    def guard():
        service.guard(deadline)
        if cancel_guard is not None:
            cancel_guard()
        if (time.monotonic() >= deadline or binding(policy.data) != initial_binding
                or stable_account(policy.data) != account_key
                or 'draft_read' not in policy.value['capabilities']):
            fail('CURRENT_DRAFT_SCOPE_CHANGED')

    guard()
    if current_authority is not None:
        fail('LEGACY_CASE_NOT_DISTRIBUTED')
    directory = policy.root / 'current-draft-publication'
    if not directory.exists():
        directory.mkdir(mode=0o700)
        fd = os.open(policy.root, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
        try: os.fsync(fd)
        finally: os.close(fd)
    path_check(directory, True)
    cursor = arguments.get('cursor')
    previous, seen = None, set()
    if cursor is not None:
        match = CURSOR.fullmatch(cursor) if type(cursor) is str else None
        if match is None:
            fail('CURRENT_DRAFT_CURSOR_INVALID')
        handle, number = match[1], int(match[2])
        previous = read_file(directory / (handle + '.json'), INDEX_MAX)
        if (type(previous) is not dict or previous.get('profile') != CHECKPOINT_PROFILE
                or previous.get('inventory_handle') != handle
                or previous.get('binding_sha256') != initial_binding
                or previous.get('account_key') != account_key
                or previous.get('connection_id') != policy.data['connection_id']):
            fail('CURRENT_DRAFT_CURSOR_CHANGED')
        if previous.get('current_source') is not None and (current_authority is None
                or previous['current_source'] != current_authority.configuration_ref):
            fail('CURRENT_PUBLICATION_INVENTORY_SOURCE_CHANGED')
        guard()
        selected, seen = _read_chain(directory, previous, initial_binding, guard,
                                     wanted_page=number if number <= previous['head_page'] else None)
        if number <= previous['head_page']:
            page, targets = selected
            result = public_result(handle, policy.data['connection_id'], page, targets)
            if current_authority is not None: current_authority.fence()
            guard()
            return result
        if number != previous['head_page'] + 1 or previous['coverage'] != 'PARTIAL_CONTINUATION_REQUIRED':
            fail('CURRENT_DRAFT_CURSOR_INVALID')
    else:
        handle, number = 'inventory-' + secrets.token_hex(24), 0

    page_path = directory / _page_name(handle, number)
    if os.path.lexists(page_path):
        # Page commit happened but its checkpoint/result was not acknowledged.
        raw = _read_blob(directory, page_path.name, CHUNK_MAX, guard)
        page_sha = sha256(raw).hexdigest()
        page, targets = _read_page(directory, handle, number, page_sha, initial_binding, guard)
        if (previous is None or page['previous_sha256'] != previous['head_sha256']
                or page['total_groups'] != previous['total_groups']
                or page['next_offset'] != previous['observed_groups'] + len(targets)
                or any(t['reference'] in seen for t in targets)):
            fail('CURRENT_DRAFT_SNAPSHOT_CHANGED')
    else:
        token = service.tokens.get(guard)
        sender = service.workflow.sender
        if type(sender) is not HTTPSender or not sender.enabled:
            fail('OWN_HTTP_DISABLED')

        def send(request):
            if current_authority is not None: current_authority.fence()
            guard()
            if not service.tokens.valid(token):
                fail('OWN_TOKEN_UNAVAILABLE')
            remaining = min(30.0, deadline - time.monotonic(), token.wall_deadline - time.time())
            if remaining <= 0:
                fail('CONNECTION_QUEUE_EXPIRED')
            response = sender.send(request, remaining)
            guard()
            if current_authority is not None: current_authority.fence()
            return response

        def get_page(offset):
            request = wire._encode('batchget', {'offset': offset, 'count': 20, 'no_content': 1}, token.token)
            return parse_page(send(request), token.token, offset)

        def get_draft(reference):
            return wire.parse_get(send(wire.encode_get(reference, token.token)), token.token, reference,
                                  allow_picture=True)

        value = scan(get_page, get_draft, guard, offset=previous['observed_groups'] if previous else 0,
                     expected_total=previous['total_groups'] if previous else None, max_pages=1)
        targets = value['targets']
        if any(t['reference'] in seen for t in targets):
            fail('CURRENT_DRAFT_INVENTORY_DUPLICATE')
        records = []
        for target in targets:
            raw = _bytes(target)
            if not 0 < len(raw) <= SNAPSHOT_MAX:
                fail('CURRENT_DRAFT_SNAPSHOT_LIMIT')
            nonce = secrets.token_hex(16)
            chunks = []
            for position in range(0, len(raw), CHUNK_MAX):
                block = raw[position:position + CHUNK_MAX]
                name = handle + '-chunk-' + nonce + '-' + str(position // CHUNK_MAX) + '.bin'
                _write_once(directory, name, block, CHUNK_MAX, guard)
                chunks.append({'name': name, 'sha256': sha256(block).hexdigest()})
            records.append({'reference': target['reference'], 'snapshot_sha256': sha256(raw).hexdigest(),
                            'chunks': chunks})
        coverage = value['coverage']
        if coverage != 'COMPLETE_OBSERVED_PAGINATION' and number + 1 == MAX_PAGES:
            coverage = 'PARTIAL_LIMIT_REACHED'
        page = {'profile': PAGE_PROFILE, 'handle': handle, 'page': number,
                'binding_sha256': initial_binding,
                'previous_sha256': previous['head_sha256'] if previous else None,
                'total_groups': value['total_groups'], 'next_offset': value['next_offset'],
                'coverage': coverage, 'list_response_sha256': value['list_response_sha256'][0],
                'observed_ms': int(time.time() * 1000),
                'targets': records}
        raw = _bytes(page)
        _write_once(directory, page_path.name, raw, CHUNK_MAX, guard)
        page_sha = sha256(raw).hexdigest()
        page, targets = _read_page(directory, handle, number, page_sha, initial_binding, guard)

    checkpoint = {'profile': CHECKPOINT_PROFILE, 'inventory_handle': handle,
        'connection_id': policy.data['connection_id'], 'binding_sha256': initial_binding,
        'account_key': account_key, 'head_page': number, 'head_sha256': page_sha,
        'total_groups': page['total_groups'], 'observed_groups': page['next_offset'],
        'coverage': page['coverage']}
    if current_authority is not None:
        current_authority.fence()
        checkpoint['current_source'] = dict(current_authority.configuration_ref)
    # Validate the entire new chain before exposing or committing its checkpoint.
    _read_chain(directory, checkpoint, initial_binding, guard)
    guard()
    atomic_write(directory / (handle + '.json'), checkpoint, maximum=16384)
    _read_chain(directory, checkpoint, initial_binding, guard)
    result = public_result(handle, policy.data['connection_id'], page, targets)
    if current_authority is not None: current_authority.fence()
    guard()
    return result


def public_result(handle, connection_id, page, targets):
    from .wechat_article_safety import image_url
    groups = [{'index': page['page'] * 20 + i,
        'article_count': len(target['projection']['response']['news_item']),
        'titles': [row['title'] for row in target['projection']['response']['news_item']],
        'covers': [image_url(row.get('thumb_url')) for row in target['projection']['response']['news_item']],
        'update_time': target['listed_update_time'],
        'projection_sha256': target['projection_sha256']}
        for i, target in enumerate(targets)]
    for group, target in zip(groups, targets):
        rows = target['projection']['response']['news_item']
        if any(row.get('article_type') == 'newspic' for row in rows):
            group['article_types'] = [row.get('article_type', 'news') for row in rows]
    return {'inventory_handle': handle, 'profile': PROFILE,
        'connection_id': connection_id,
        'coverage': page['coverage'], 'platform_atomic': False,
        'total_groups': page['total_groups'], 'observed_groups': page['next_offset'],
        'groups': groups,
        'cursor': (handle + '-' + str(page['page'] + 1)
                   if page['coverage'] == 'PARTIAL_CONTINUATION_REQUIRED' else None),
        'requests': {'list': page['page'] + 1, 'get': page['next_offset']},
        'requests_scope': 'COMMITTED_PAGES_ONLY_NOT_TOTAL_ATTEMPTS',
        'publication_authority': False}


def load_complete(policy, handle, guard):
    """Host-only checked inventory; no caller-supplied remote IDs or paths."""
    if type(handle) is not str or HANDLE.fullmatch(handle) is None:
        fail('CURRENT_DRAFT_CURSOR_INVALID')
    directory = policy.root / 'current-draft-publication'
    checkpoint = read_file(directory / (handle + '.json'), INDEX_MAX)
    if (checkpoint.get('profile') != CHECKPOINT_PROFILE
            or checkpoint.get('inventory_handle') != handle
            or checkpoint.get('connection_id') != policy.data['connection_id']
            or checkpoint.get('account_key') != stable_account(policy.data)
            or checkpoint.get('binding_sha256') != binding(policy.data)
            or checkpoint.get('coverage') != 'COMPLETE_OBSERVED_PAGINATION'
            or checkpoint.get('observed_groups') != checkpoint.get('total_groups')):
        fail('CURRENT_DRAFT_INVENTORY_INCOMPLETE')
    _read_chain(directory, checkpoint, binding(policy.data), guard)
    guard()
    return checkpoint


def frozen_targets(policy, checkpoint, guard):
    directory = policy.root / 'current-draft-publication'
    expected = checkpoint['head_sha256']
    for number in range(checkpoint['head_page'], -1, -1):
        page, targets = _read_page(directory, checkpoint['inventory_handle'], number,
            expected, binding(policy.data), guard)
        for index, target in enumerate(targets):
            yield page, index, expected, target
        expected = page['previous_sha256']
    if expected is not None:
        fail('CURRENT_DRAFT_SNAPSHOT_CHANGED')
    guard()
