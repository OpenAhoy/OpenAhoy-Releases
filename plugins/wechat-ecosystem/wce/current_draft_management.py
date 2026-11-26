"""Manage exact current inventory objects through the ordinary account broker.

The platform has no verified cross-container merge operation. Migration creates
one new draft, verifies the observed articles, then retires the selected sources.
No old save receipt, host batch, source qualification or QA grant is fabricated.
"""
from contextlib import contextmanager
from copy import deepcopy
from hashlib import sha256
from html.parser import HTMLParser
import json
import os
import re
import sqlite3
import time
from urllib.parse import urlsplit

from .contracts import WCEError
from .http_transport import HTTPSender
from .own_bootstrap_security import path_check
from .own_wire import image_url
from .publication_contract import binding, stable_account
from .publication_store import read_file, sync_directory
from . import current_draft_inventory as inventory
from . import draft_group_wire as wire

PREFIX = 'own.drafts.current.'
METHODS = frozenset(PREFIX + x for x in ('read', 'delete', 'merge', 'status', 'resume'))
NETWORK = METHODS - {PREFIX + 'read', PREFIX + 'status'}
HANDLE = re.compile(r'managed-draft-[a-f0-9]{48}\Z')
DIRECTORY = 'current-draft-management'
PROFILE = 'CURRENT_DRAFT_MANAGEMENT_V1'
CONTENT_CHARS = 12000  # Response pagination, never a document/business limit.


def fail(code):
    raise WCEError(code)


def selected(policy, selection, guard):
    """Resolve an immutable, account-bound observed object, even on a partial page."""
    handle = selection['inventory_handle']
    if inventory.HANDLE.fullmatch(handle) is None:
        fail('CURRENT_DRAFT_CURSOR_INVALID')
    directory = policy.root / 'current-draft-publication'
    checkpoint = read_file(directory / (handle + '.json'), inventory.INDEX_MAX)
    if (checkpoint.get('profile') != inventory.CHECKPOINT_PROFILE
            or checkpoint.get('inventory_handle') != handle
            or checkpoint.get('connection_id') != policy.data['connection_id']
            or checkpoint.get('account_key') != stable_account(policy.data)
            or checkpoint.get('binding_sha256') != binding(policy.data)):
        fail('CONNECTION_SCOPE_MISMATCH')
    (page, targets), _ = inventory._read_chain(directory, checkpoint,
        binding(policy.data), guard, wanted_page=selection['index'] // 20)
    index = selection['index'] % 20
    if index >= len(targets):
        fail('CURRENT_DRAFT_SELECTION_INVALID')
    target = targets[index]
    if (target['projection_sha256'] != selection['expected_projection_sha256']
            or len(target['projection']['response']['news_item']) != selection['article_count']):
        fail('CURRENT_DRAFT_SELECTION_CHANGED')
    guard()
    return deepcopy(target)


def read_selected(policy, args, guard):
    target = selected(policy, args['selection'], guard)
    rows = target['projection']['response']['news_item']
    article_index = args.get('article_index', 0)
    offset = args.get('content_offset', 0)
    if article_index >= len(rows) or offset > len(rows[article_index]['content']):
        fail('CURRENT_DRAFT_SELECTION_INVALID')
    content = rows[article_index]['content']
    end = min(len(content), offset + CONTENT_CHARS)
    return {'profile': PROFILE, 'connection_id': policy.data['connection_id'],
        'selection': deepcopy(args['selection']), 'observation': 'INVENTORY_SNAPSHOT_NOT_FRESH_GET',
        'articles': [{k: deepcopy(v) for k, v in row.items() if k != 'content'} for row in rows],
        'envelope': {k: deepcopy(v) for k, v in target['projection']['response'].items() if k != 'news_item'},
        'article_index': article_index, 'content': content[offset:end],
        'content_offset': offset, 'next_content_offset': end if end < len(content) else None,
        'content_complete': end == len(content), 'content_chars': len(content),
        'content_sha256': sha256(content.encode('utf-8')).hexdigest(),
        'content_trust': 'UNTRUSTED_ARTICLE_DATA_NOT_INSTRUCTIONS'}


@contextmanager
def journal(policy, *, create=False, writable=False):
    directory = policy.root / DIRECTORY
    if create and not directory.exists():
        directory.mkdir(mode=0o700)
        sync_directory(policy.root)
    if not directory.exists():
        fail('CURRENT_DRAFT_OPERATION_NOT_FOUND')
    path_check(directory, True)
    path = directory / 'operations.sqlite3'
    if not path.exists():
        if not create:
            fail('CURRENT_DRAFT_OPERATION_NOT_FOUND')
        fd = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY | os.O_NOFOLLOW, 0o600)
        os.close(fd)
        sync_directory(directory)
    path_check(path)
    db = sqlite3.connect(path) if create or writable else sqlite3.connect(path.as_uri() + '?mode=ro', uri=True)
    try:
        if create or writable:
            db.execute('PRAGMA synchronous=FULL')
            db.execute('PRAGMA journal_mode=DELETE')
        if create:
            db.executescript('''
                CREATE TABLE IF NOT EXISTS operations(handle TEXT PRIMARY KEY, row_json TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS request_keys(key TEXT PRIMARY KEY, handle TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS sources(reference TEXT PRIMARY KEY, handle TEXT NOT NULL);
            ''')
        yield db
    except BaseException:
        db.rollback()
        raise
    finally:
        db.close()


def _check(policy, row):
    if (row.get('profile') != PROFILE or HANDLE.fullmatch(row.get('operation_handle', '')) is None
            or row.get('account_key') != stable_account(policy.data)
            or row.get('connection_id') != policy.data['connection_id']
            or row.get('binding_sha256') != binding(policy.data)):
        fail('CONNECTION_SCOPE_MISMATCH')
    return row


def _load(db, policy, *, handle=None, request_key=None):
    if request_key is not None:
        found = db.execute('SELECT handle FROM request_keys WHERE key=?', (request_key,)).fetchone()
        if found is None:
            fail('CURRENT_DRAFT_OPERATION_NOT_FOUND')
        handle = found[0]
    if type(handle) is not str or HANDLE.fullmatch(handle) is None:
        fail('CURRENT_DRAFT_OPERATION_INVALID')
    found = db.execute('SELECT row_json FROM operations WHERE handle=?', (handle,)).fetchone()
    if found is None:
        fail('CURRENT_DRAFT_OPERATION_NOT_FOUND')
    return _check(policy, json.loads(found[0]))


def _save(db, row):
    db.execute('UPDATE operations SET row_json=? WHERE handle=?',
        (wire.canonical(row), row['operation_handle']))
    db.commit()


def _release_unsent_or_rejected(db, row):
    """A known no-effect failure must not permanently consume source objects."""
    if row['state'] not in {'SOURCE_CHANGED', 'SOURCE_UNAVAILABLE', 'ADD_REJECTED', 'DELETE_REJECTED'}:
        return  # Resumable PREPARED/RETIRE_SOURCES keep exclusive ownership.
    add_safe = row['add_count'] == 0 or row['state'] == 'ADD_REJECTED'
    deletes_safe = all(r['state'] in {'NOT_SENT', 'DELETE_REJECTED'} for r in row['retirements'])
    if add_safe and deletes_safe:
        db.execute('DELETE FROM sources WHERE handle=?', (row['operation_handle'],))
        db.commit()


def public(row):
    if row.get('content_version') == 1:
        from .wechat_content import public as content_result
        return content_result(row)
    result = {k: deepcopy(row[k]) for k in ('operation_handle', 'kind', 'state', 'article_count',
        'titles', 'add_count', 'error_code', 'reason', 'preservation', 'original_preservation') if k in row}
    result['source_containers'] = [{'index': i, 'article_count': len(t['projection']['response']['news_item']),
        'state': row['retirements'][i]['state'], 'delete_count': row['retirements'][i]['delete_count']}
        for i, t in enumerate(row['targets'])]
    result['mode'] = 'EXACT_CONTAINER_DELETE' if row['kind'] == 'delete' else 'CREATE_VERIFY_THEN_RETIRE_SELECTED_CONTAINERS'
    result['publication_ready'] = row['kind'] == 'merge' and row['state'] == 'COMPLETED'
    if result['publication_ready']:
        result['intent_handle'] = row['operation_handle']
        if any(article.get('article_type') == 'newspic'
               for target in row['targets'] for article in target['projection']['response']['news_item']):
            result['contains_picture_messages'] = True
    result['publication_submitted'] = False
    result['platform_atomic'] = False
    result['phase'] = ('VERIFY_NEW_GROUP' if row['state']=='PRESERVATION_MISMATCH' else
        'READ_SOURCE' if row['state']in {'SOURCE_CHANGED','SOURCE_UNAVAILABLE'} else
        'ADD' if row['state']in {'ADD_UNKNOWN','ADD_REJECTED'} else
        'RETIRE_SOURCES' if row['state']in {'DELETE_REJECTED','ABSENT_CAUSE_UNDETERMINED'} else row['state'])
    if row['kind']=='merge':
        result['candidate_created']=(row['new_reference'] not in {t['reference']for t in row['targets']}
            if row.get('new_reference') else None if row['state']=='ADD_UNKNOWN' else False)
    result['hidden_editor_settings'] = 'NOT_OBSERVED_NOT_CLAIMED'
    return result


def local_status(policy, args):
    policy.check(readonly=True, allow_disconnected=True)
    with journal(policy) as db:
        row = _load(db, policy, handle=args.get('operation_handle'), request_key=args.get('request_key'))
    policy.check(readonly=True, allow_disconnected=True)
    return public(row)


def publication_source(policy, handle):
    """A real ADD+GET receipt, never an inserted or invented own_steps row."""
    with journal(policy) as db:
        row = _load(db, policy, handle=handle)
    if row.get('content_version') == 1:
        if (row['kind'] not in {'create_picture', 'update_picture'}
                or row['state'] not in {'SAVED', 'VERIFIED', 'UNCHANGED'} or not row.get('new_reference')):
            fail('WECHAT_CONTENT_DRAFT_NOT_READY')
        return row['new_reference'], row['titles']
    if row['kind'] != 'merge' or row['state'] != 'COMPLETED' or not row.get('new_reference'):
        fail('CURRENT_DRAFT_MERGE_NOT_READY')
    return row['new_reference'], row['titles']


def _reserve(db, policy, args, kind, targets):
    if len({t['reference'] for t in targets}) != len(targets):
        fail('CURRENT_DRAFT_SELECTION_DUPLICATE')
    rows = [row for t in targets for row in t['projection']['response']['news_item']]
    if kind == 'merge' and not 1 <= len(rows) <= 8:
        fail('CURRENT_DRAFT_GROUP_SIZE_OFFICIAL')
    identity = [kind, stable_account(policy.data), binding(policy.data),
        [[t['reference'], t['projection_sha256']] for t in targets]]
    intent_sha = wire.digest(identity)
    account_key = stable_account(policy.data)
    handle = 'managed-draft-' + wire.digest([account_key, args['request_key']])[:48]
    db.execute('BEGIN IMMEDIATE')
    prior = db.execute('SELECT handle FROM request_keys WHERE key=?', (args['request_key'],)).fetchone()
    if prior is not None:
        original = _load(db, policy, handle=prior[0])
        if original['intent_sha256'] != intent_sha:
            fail('CURRENT_DRAFT_REQUEST_KEY_CONFLICT')
        db.commit()
        return original, True
    old = db.execute('SELECT row_json FROM operations WHERE handle=?', (handle,)).fetchone()
    if old is None:
        for target in targets:
            owner = db.execute('SELECT handle FROM sources WHERE reference=?', (target['reference'],)).fetchone()
            if owner is not None:
                original = _load(db, policy, handle=owner[0])
                if original['intent_sha256'] != intent_sha:
                    fail('CURRENT_DRAFT_ORIGINAL_OPERATION_REQUIRED')
                db.execute('INSERT INTO request_keys VALUES(?,?)', (args['request_key'], owner[0]))
                db.commit()
                return original, True
        row = {'profile': PROFILE, 'operation_handle': handle,
            'account_key': account_key, 'binding_sha256': binding(policy.data), 'intent_sha256': intent_sha,
            'connection_id': policy.data['connection_id'], 'kind': kind, 'state': 'PREPARED',
            'targets': targets, 'article_count': len(rows), 'titles': [r['title'] for r in rows],
            'add_count': 0, 'new_reference': None,
            'retirements': [{'state': 'NOT_SENT', 'delete_count': 0} for _ in targets]}
        db.execute('INSERT INTO operations VALUES(?,?)', (handle, wire.canonical(row)))
        db.executemany('INSERT INTO sources VALUES(?,?)', [(t['reference'], handle) for t in targets])
    else:
        row = _check(policy, json.loads(old[0]))
    db.execute('INSERT OR IGNORE INTO request_keys VALUES(?,?)', (args['request_key'], handle))
    db.commit()
    return row, old is not None


class _OneImageTag(HTMLParser):
    def __init__(self,raw):
        super().__init__(convert_charrefs=False)
        self.tags=[]
        self.feed(raw);self.close()
    def handle_starttag(self,tag,attrs):self.tags.append((tag,attrs))
    def handle_startendtag(self,tag,attrs):self.tags.append((tag,attrs))


class _ImageTerminators(HTMLParser):
    """Project only real img terminators, preserving every other source byte.

    The older upload-representation observer requires original upload bindings
    and has a different content contract. Current inventory has no such keys;
    this narrow source projection adds no uploader/QA or image-download gate.
    """
    inert={'script','style','textarea','title','xmp','iframe','noembed','noframes','plaintext','noscript','svg','math','template'}
    def __init__(self,raw):
        super().__init__(convert_charrefs=False)
        self.raw=raw;self.edits=[];self.ignored=[];self.images=0
        self.lines=[0]+[m.end()for m in re.finditer('\n',raw)]
        self.feed(raw);self.close()
    def handle_starttag(self,tag,attrs):
        if tag in self.inert:self.ignored.append(tag)
        if tag!='img' or self.ignored:return
        raw=self.get_starttag_text()
        if not raw.endswith('>'):return
        prefix=raw[:-1]
        if prefix.endswith('/'):prefix=prefix[:-1]
        projected=prefix.rstrip(' \t\r\n\f')+'>'
        # HTML unquoted values can consume a trailing slash. Never erase one
        # unless the parser confirms the exact same attributes and values.
        if _OneImageTag(projected).tags!=[(tag,attrs)]:return
        line,column=self.getpos();start=self.lines[line-1]+column
        self.edits.append((start,start+len(raw),projected));self.images+=1
    def handle_startendtag(self,tag,attrs):self.handle_starttag(tag,attrs)
    def handle_endtag(self,tag):
        if tag!='plaintext' and self.ignored and tag==self.ignored[-1]:self.ignored.pop()
    def projection(self):
        parts=[];end=0
        for start,stop,value in self.edits:
            parts.extend((self.raw[end:start],value));end=stop
        return ''.join(parts)+self.raw[end:]


def _equivalent_image_terminators(before,after):
    if type(before)is not str or type(after)is not str:return None
    try:
        left,right=_ImageTerminators(before),_ImageTerminators(after)
        if left.images and left.images==right.images and left.projection()==right.projection():return left.images
    except (ValueError,TypeError,IndexError):
        pass
    return None


def _equivalent_cover_url(before, after):
    # The surrounding operation pins the real account; never compare media IDs
    # across connections. Every observed crop/cover_info field is still checked.
    media_id = before.get('thumb_media_id')
    if type(media_id) is not str or not media_id or after.get('thumb_media_id') != media_id:
        return False
    original, observed = before.get('thumb_url'), after.get('thumb_url')
    if not all(image_url(url, synthetic=False) for url in (original, observed)):
        return False
    left, right = urlsplit(original), urlsplit(observed)
    # Issue #3 observed a path rewrite, with the origin and query unchanged.
    return (left.scheme == right.scheme and left.netloc == right.netloc
            and left.query == right.query and bool(left.path and right.path)
            and left.path != right.path)


def preservation(expected_rows, actual_rows):
    """Preserve every observed non-temporary field; additions are reported separately."""
    differences, additions, representations = [], [], []
    if len(expected_rows) != len(actual_rows):
        differences.append('article_count')
    for i, expected in enumerate(expected_rows):
        if i >= len(actual_rows):
            break
        actual = actual_rows[i]
        for key, value in expected.items():
            if (key == 'digest' and len(expected_rows) > 1 and type(value) is str
                    and value and key in actual and type(actual[key]) is str and actual[key] == ''):
                representations.append({'article_index': i, 'field': 'digest',
                    'transformation': 'OFFICIAL_MULTI_DIGEST_EMPTY',
                    'original_snapshot': 'OPERATION_TARGETS',
                    'original_sha256': sha256(value.encode('utf-8')).hexdigest(),
                    'original_chars': len(value)})
                continue
            different=key not in actual or wire.canonical(actual[key])!=wire.canonical(value)
            if key=='content' and different and key in actual:
                images=_equivalent_image_terminators(value,actual[key])
                if images is not None:
                    representations.append({'article_index':i,'field':key,
                        'transformation':'HTML_IMG_TERMINATOR_EQUIVALENT','image_count':images,
                        'original_snapshot':'OPERATION_TARGETS'})
                    continue
            if key == 'thumb_url' and different and _equivalent_cover_url(expected, actual):
                representations.append({'article_index':i,'field':key,
                    'transformation':'SAME_ACCOUNT_PERMANENT_COVER_DERIVED_URL',
                    'material_identity':'THUMB_MEDIA_ID_EQUAL','original_snapshot':'OPERATION_TARGETS'})
                continue
            if key != 'url' and different:
                differences.append(str(i) + '.' + key)
        additions.extend(str(i) + '.' + k for k in actual if k not in expected and k != 'url')
    return {'state': ('MISMATCH' if differences else
                     'PLATFORM_REPRESENTATION_MATCHED' if representations else 'PRESERVED'),
        'different_fields': differences, 'added_fields': additions,
        'official_representations': representations,
        'temporary_urls': 'EXPECTED_TO_CHANGE', 'unobserved_settings': 'NOT_CLAIMED'}


def _merge_payload(rows):
    from .wechat_picture_fields import picture_fields
    articles=[]
    for row in rows:
        article={key:deepcopy(value) for key,value in row.items() if key != 'url'}
        if row.get('article_type')=='newspic':
            # Validate the typed write shape without dropping any field whose
            # preservation cannot be established. The source remains intact.
            allowed={'article_type','title','author','content','image_info','cover_info',
                     'product_info','need_open_comment','only_fans_can_comment'}
            if set(article)-allowed or any(set(image)!={'image_media_id'}
                    for image in article.get('image_info',{}).get('image_list',[])):
                fail('GROUP_UNMAPPED_FIELD_HOLD')
            picture_fields(article)
        articles.append(article)
    return {'articles':articles}


def execute(service, method, args, deadline, cancel_guard=None):
    policy = service.policy
    initial_binding, account_key = binding(policy.data), stable_account(policy.data)
    required = {'draft_read', 'draft_save'}

    def guard():
        service.guard(deadline)
        if cancel_guard is not None:
            cancel_guard()
        if (args.get('connection_id') != policy.data['connection_id']
                or time.monotonic() >= deadline or binding(policy.data) != initial_binding
                or stable_account(policy.data) != account_key
                or not required <= set(policy.value['capabilities'])):
            fail('CURRENT_DRAFT_SCOPE_CHANGED')

    guard()
    if method == PREFIX + 'read':
        return read_selected(policy, args, guard)
    if method == PREFIX + 'status':
        return local_status(policy, args)
    # Mutation endpoints require the existing draft capability; Tencent remains
    # the authority on actual draft/delete/add permissions and quotas.
    if 'draft_save' not in policy.value['capabilities']:
        fail('OWN_ACCESS_DENIED')
    with journal(policy, create=True) as db:
        if method == PREFIX + 'resume':
            row = _load(db, policy, handle=args['operation_handle'])
            if row.get('content_version') == 1:
                fail('WECHAT_CONTENT_USE_ORIGINAL_READBACK')
            if (row['state'] == 'PRESERVATION_MISMATCH' and row['kind'] == 'merge'
                    and row.get('new_reference')
                    and row['new_reference'] not in {t['reference'] for t in row['targets']}):
                # Re-read this exact known destination, never create another.
                # Keep the original strict observation from the earlier version.
                row.setdefault('original_preservation', deepcopy(row.get('preservation')))
                row['state'] = 'VERIFY_NEW_GROUP'
                _save(db, row)
        else:
            kind = method.removeprefix(PREFIX)
            selections = args['selections'] if kind == 'merge' else [args['selection']]
            if len({s['inventory_handle'] for s in selections}) != 1:
                fail('CURRENT_DRAFT_MIXED_INVENTORIES')
            selections = sorted(selections, key=lambda s: s['index'])
            targets = [selected(policy, s, guard) for s in selections]
            if kind == 'merge':
                _merge_payload([item for target in targets for item in target['projection']['response']['news_item']])
            row, exists = _reserve(db, policy, args, kind, targets)
            if exists:
                return public(row)
        if row['state'] in {'COMPLETED', 'ADD_UNKNOWN', 'ADD_REJECTED', 'PRESERVATION_MISMATCH',
                            'SOURCE_CHANGED', 'SOURCE_UNAVAILABLE', 'DELETE_REJECTED', 'ABSENT_CAUSE_UNDETERMINED'}:
            return public(row)
        token = service.tokens.get(guard)
        sender = service.workflow.sender
        if type(sender) is not HTTPSender or not sender.enabled:
            fail('OWN_HTTP_DISABLED')

        def send(request, before_http=None):
            guard()
            if not service.tokens.valid(token):
                fail('OWN_TOKEN_UNAVAILABLE')
            remaining = min(30.0, deadline - time.monotonic(), token.wall_deadline - time.time())
            if remaining <= 0:
                fail('CONNECTION_QUEUE_EXPIRED')
            if before_http is not None:
                before_http()
            return sender.send(request, remaining)

        def get(reference):
            response = send(wire.encode_get(reference, token.token))
            value = wire.parse_get(response, token.token, reference, allow_picture=True)
            guard()
            return value

        def source_matches(target):
            snapshot = get(target['reference'])
            if type(snapshot) is not wire.GroupSnapshot:
                row['state'] = 'SOURCE_UNAVAILABLE'
                _save(db, row)
                _release_unsent_or_rejected(db, row)
                return False
            if wire.digest(wire.baseline_projection(snapshot)) != target['projection_sha256']:
                row['state'] = 'SOURCE_CHANGED'
                _save(db, row)
                _release_unsent_or_rejected(db, row)
                return False
            return True

        if row['state'] == 'PREPARED':
            for target in row['targets']:
                if not source_matches(target):
                    return public(row)
            if row['kind'] == 'merge':
                rows = [r for t in row['targets'] for r in t['projection']['response']['news_item']]
                # These are server-observed original fields, not caller payload.
                # In particular do not erase multi-article digests locally.
                payload = _merge_payload(rows)
                request = wire._encode('add', payload, token.token)
                guard()
                row.update(state='ADD_UNKNOWN', add_count=1)
                _save(db, row)  # A crash after send never releases another ADD.
                entered = []
                try:
                    response = send(request, lambda: entered.append(True))
                    row['error_code'] = wire.response_value(response, token.token).get('errcode', 0)
                    ack = wire.parse_add(response, token.token)
                except WCEError as error:
                    if not entered:
                        row.update(state='PREPARED', add_count=0)
                    elif error.code == 'GROUP_ADD_REJECTED':
                        row['state'] = 'ADD_REJECTED'
                    row['reason'] = error.code
                    _save(db, row)
                    _release_unsent_or_rejected(db, row)
                    return public(row)
                except (OSError, EOFError, TimeoutError):
                    if not entered:
                        row.update(state='PREPARED', add_count=0, reason='LOCAL_NOT_SENT')
                        _save(db, row)
                    return public(row)
                row.update(state='VERIFY_NEW_GROUP', new_reference=ack.reference)
                _save(db, row)  # Persist the real returned ID before more guards.
                if ack.reference in {t['reference'] for t in row['targets']}:
                    row['state'] = 'PRESERVATION_MISMATCH'
                    row['preservation'] = {'state': 'RETURNED_ID_IS_SOURCE'}
                    _save(db, row)
                    return public(row)
                guard()
            else:
                row['state'] = 'RETIRE_SOURCES'
                _save(db, row)
        if row['kind'] == 'merge' and row['state'] in {'VERIFY_NEW_GROUP', 'RETIRE_SOURCES'}:
            snapshot = get(row['new_reference'])
            if type(snapshot) is not wire.GroupSnapshot:
                row['state'] = 'PRESERVATION_MISMATCH'
                row['preservation'] = {'state': 'NEW_DRAFT_UNAVAILABLE'}
            else:
                expected = [r for t in row['targets'] for r in t['projection']['response']['news_item']]
                row['preservation'] = preservation(expected, snapshot.rows())
                row['state'] = ('RETIRE_SOURCES' if row['preservation']['state'] in
                               {'PRESERVED', 'PLATFORM_REPRESENTATION_MATCHED'}
                                else 'PRESERVATION_MISMATCH')
            _save(db, row)
            if row['state'] != 'RETIRE_SOURCES':
                return public(row)
        # Each original is compared just before its DELETE. No source disappears
        # until the new group has preserved every observed article field.
        for target, retirement in zip(row['targets'], row['retirements']):
            if retirement['state'] == 'DELETED':
                continue
            if retirement['state'] == 'DELETE_UNKNOWN':
                snapshot = get(target['reference'])
                if type(snapshot) is not wire.GroupSnapshot:
                    row['state'] = 'ABSENT_CAUSE_UNDETERMINED'
                    retirement['state'] = 'ABSENT_CAUSE_UNDETERMINED'
                _save(db, row)
                return public(row)  # Never repeat a possibly sent DELETE.
            if not source_matches(target):
                return public(row)
            request = wire.encode_delete(target['reference'], token.token)
            guard()
            retirement.update(state='DELETE_UNKNOWN', delete_count=1)
            _save(db, row)
            entered = []
            try:
                response = send(request, lambda: entered.append(True))
                row['error_code'] = wire.response_value(response, token.token).get('errcode', 0)
                wire.parse_delete(response, token.token, target['reference'])
            except WCEError as error:
                if not entered:
                    retirement.update(state='NOT_SENT', delete_count=0)
                elif error.code == 'GROUP_DELETE_REJECTED':
                    row['state'] = 'DELETE_REJECTED'
                    retirement['state'] = 'DELETE_REJECTED'
                row['reason'] = error.code
                _save(db, row)
                _release_unsent_or_rejected(db, row)
                return public(row)
            except (OSError, EOFError, TimeoutError):
                if not entered:
                    retirement.update(state='NOT_SENT', delete_count=0)
                    row['reason'] = 'LOCAL_NOT_SENT'
                    _save(db, row)
                return public(row)
            retirement['state'] = 'DELETED'
            _save(db, row)
            guard()
        row['state'] = 'COMPLETED'
        _save(db, row)
        return public(row)
