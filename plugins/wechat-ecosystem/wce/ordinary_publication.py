"""Ordinary publication of a saved draft through the official submit/get APIs."""
from contextlib import ExitStack
from dataclasses import asdict
from pathlib import Path
import json
import os
import re
import sqlite3
import time

from .contracts import WCEError
from .own_account_metadata import read_metadata
from .own_bootstrap_security import path_check
from .own_connection_policy import atomic_write, locked
from .publication_contract import digest, fail, stable_account
from .publication_store import sync_directory
from .publication_wire import DraftMediaID, TaskID, encode, parse
from .publication_receipt import _project
from .current_publication_store import public_target

STEP = re.compile(r'own-step-[0-9a-f]{32}\Z')
HANDLE = re.compile(r'current-pub-[0-9a-f]{48}\Z')
DIRECTORY = 'ordinary-publications'
# These responses explicitly reject before a send. Ambiguous outcomes keep the shared claim.
MASS_NOT_SENT = frozenset({45028, 45009, 45011, 48001, 61007})
MASS_TERMINAL = frozenset({'BROADCAST_SENT', 'BROADCAST_FAILED', 'BROADCAST_DELETED', 'NOT_SENT'})


def _anchor(policy, registry):
    return Path(registry).parent / 'publication-anchors' / stable_account(policy.data)


def _saved(policy, step_id):
    """The successful save contains the real media_id and article titles."""
    with sqlite3.connect((policy.root / 'state.sqlite3').as_uri() + '?mode=ro', uri=True) as db:
        db.row_factory = sqlite3.Row
        row = db.execute('SELECT operation,state,result,intent FROM own_steps '
            'WHERE tenant=? AND principal=? AND connection=? AND resource=? AND id=?',
            (policy.actor.tenant_id, policy.actor.principal_id, policy.data['connection_id'],
             policy.data['resource_id'], step_id)).fetchone()
    if row is None or row['operation'] != 'add' or row['state'] != 'SUCCEEDED':
        fail('CURRENT_PUBLICATION_SAVED_DRAFT_NOT_FOUND')
    result, intent = json.loads(row['result']), json.loads(row['intent'])
    articles = intent['projection']['articles']
    return result['reference'], [article['title'] for article in articles]


def _legacy(anchor, *, handle=None, reference=None):
    """Read the matching prior task only, without replaying its history."""
    path = anchor / 'slot-continuation-v1.sqlite3'
    if not path.exists():
        head = read_metadata(anchor / 'current-draft-intents-head.json')
        if head is None:
            return None
        event = read_metadata(anchor / 'current-draft-intents' / ('event-' + str(head['sequence']) + '.json'))
        candidates = event['value']['targets'].values()
        key, expected = ('intent_handle', handle) if handle else ('reference', reference)
        rows = [row for row in candidates if row[key] == expected]
        attempted = [row for row in rows if row.get('submit_count')]
        if len(attempted) > 1:
            fail('CURRENT_PUBLICATION_MULTIPLE_ORIGINAL_TASKS')
        row = attempted[0] if attempted else next(iter(rows), None)
        return _staged_task(anchor, row)
    path_check(path)
    selector, value = ('handle', handle) if handle else ("json_extract(row_json,'$.reference')", reference)
    rows = {}
    with sqlite3.connect(path.as_uri() + '?mode=ro', uri=True) as db:
        for table in ('old_intents', 'target_overlays'):
            for (raw,) in db.execute('SELECT row_json FROM ' + table + ' WHERE ' + selector + '=?', (value,)):
                row = json.loads(raw)
                rows[row['intent_handle']] = row
        attempted = [row for row in rows.values() if row.get('submit_count')]
        if len(attempted) > 1:
            fail('CURRENT_PUBLICATION_MULTIPLE_ORIGINAL_TASKS')
        row = attempted[0] if attempted else next(iter(rows.values()), None)
        if row is not None and row.get('task') is None and row.get('submit_count'):
            receipts = db.execute("SELECT receipt_json FROM return_receipts WHERE handle=? "
                "AND method='freepublish.submit'", (row['intent_handle'],)).fetchall()
            for (raw,) in receipts:
                result = json.loads(raw).get('result') or {}
                if result.get('task') is not None:
                    row = dict(row, task=result['task'], state='ACCEPTED')
    return _staged_task(anchor, row)


def _staged_task(anchor, row):
    if row is None or row.get('task') is not None or not row.get('submit_count'):
        return row
    directory = anchor / 'current-publication-receipts'
    if not directory.exists():
        return row
    for path in directory.glob('*.json'):
        proof = read_metadata(path)
        if (proof.get('intent_handle') == row['intent_handle']
                and proof.get('account_key') == row['account_key']
                and proof.get('method') == 'freepublish.submit'
                and proof.get('reason') == 'PARSED_SUCCESS'
                and proof.get('error_code') is None):
            task = (proof.get('result') or {}).get('task')
            if task is not None:
                return dict(row, task=task, state='ACCEPTED')
    return row


def _locate(policy, registry, handle, selected=None):
    anchor = _anchor(policy, registry)
    from .current_draft_management import HANDLE as MERGED, publication_source
    reference = None
    if selected is not None or STEP.fullmatch(handle or '') or MERGED.fullmatch(handle or ''):
        if selected is not None:
            reference = selected['reference']
            titles = [item['title'] for item in selected['projection']['response']['news_item']]
            source = {'inventory_projection_sha256': selected['projection_sha256']}
        elif MERGED.fullmatch(handle):
            reference, titles = publication_source(policy, handle)
            source = {'source_merge': handle}
        else:
            reference, titles = _saved(policy, handle)
            source = {'source_step': handle}
        publication = 'current-pub-' + digest([stable_account(policy.data), reference])[:48]
        path = anchor / DIRECTORY / (publication + '.json')
        row = read_metadata(path)
        if row is None:
            row = _legacy(anchor, reference=reference)
        if row is None:
            row = {'intent_handle': publication, 'account_key': stable_account(policy.data),
                'reference': reference, **source, 'state': 'NOT_ATTEMPTED',
                'submit_count': 0, 'task': None, 'article_count': len(titles), 'titles': titles,
                'queries': 0, 'reply': None, 'quality_source': 'NOT_REQUIRED'}
    elif HANDLE.fullmatch(handle or ''):
        path = anchor / DIRECTORY / (handle + '.json')
        row = read_metadata(path)
        if row is None:
            row = _legacy(anchor, handle=handle)
        if row is None:
            fail('CURRENT_PUBLICATION_NOT_FOUND')
    else:
        fail('CURRENT_PUBLICATION_INTENT_INVALID')
    if HANDLE.fullmatch(row.get('intent_handle', '')) is None:
        fail('CURRENT_PUBLICATION_INTENT_INVALID')
    path = anchor / DIRECTORY / (row['intent_handle'] + '.json')
    # A previously imported task may have advanced since the old journal.
    current = read_metadata(path)
    row = current if current is not None else row
    if row.get('account_key') != stable_account(policy.data):
        fail('CONNECTION_SCOPE_MISMATCH')
    if reference is not None and row.get('reference') != reference:
        fail('CURRENT_PUBLICATION_DRAFT_MISMATCH')
    if row.get('intent_handle') != path.stem:
        fail('CURRENT_PUBLICATION_INTENT_INVALID')
    return path, row


def _selected(policy, selection, guard):
    if selection is None:
        return None
    from .current_draft_management import selected
    if 'draft_read' not in policy.value['capabilities']:
        fail('OWN_ACCESS_DENIED')
    return selected(policy, selection, guard)


def local_status(policy, registry, handle, selection=None):
    """The original save or inventory selection is also a zero-network recovery handle."""
    def guard():
        policy.check(readonly=True)
    guard()
    target = _selected(policy, selection, guard)
    _, row = _locate(policy, registry, handle, target)
    guard()
    return public_target(row)


def _write(path, row):
    path.parent.mkdir(mode=0o700, exist_ok=True)
    path_check(path.parent, True)
    sync_directory(path.parent.parent)
    atomic_write(path, row, maximum=None)


def _coordination(policy, registry):
    from .publication_lock import _marker, _require_pin_if_migrated
    marker = _marker(policy.root, policy.data['appid'])
    _require_pin_if_migrated(policy.root, marker)
    if marker is not None and Path(marker['anchor']) != _anchor(policy, registry):
        fail('PUBLICATION_COORDINATION_UNVERIFIED')
    return marker


def _initialize_dispatch(policy, registry, guard):
    """First ordinary submit only; never repair existing objects or old pins."""
    marker = _coordination(policy, registry)
    if marker is not None:
        return
    from .current_publication_store import initialize_anchor
    from .publication_store import PublicationStore
    path_check(Path(registry).parent, True)
    guard()
    store = PublicationStore(policy, registry)
    initialize_anchor(store)
    for lock in (store.anchor / 'publication.lock', policy.root / 'publication-dispatch.lock',
                 policy.root / 'connection-policy.lock'):
        if not os.path.lexists(lock):
            guard()
            with locked(lock, nonblocking=True) as fd:
                if os.fstat(fd).st_size != 0:
                    fail('CONNECTION_UNSAFE_LOCK')
            sync_directory(lock.parent)
    guard()
    if _coordination(policy, registry) != marker:
        fail('PUBLICATION_COORDINATION_UNVERIFIED')


def _verify_draft(service, token, row, selected, timeout, guard, *, notify):
    from . import draft_group_wire as wire
    request = wire.encode_get(row['reference'], token.token)
    response = service.workflow.sender.send(request, timeout)
    guard()
    snapshot = wire.parse_get(response, token.token, row['reference'], allow_picture=True)
    projection = wire.baseline_projection(snapshot)
    articles = projection['response']['news_item']
    if [article['title'] for article in articles] != row['titles']:
        fail('CURRENT_DRAFT_SELECTION_CHANGED')
    current = digest(projection)
    previous = (row.get('notify_attempt') or {}).get('draft_projection_sha256')
    if ((selected is not None and selected['projection_sha256'] != current)
            or (previous is not None and previous != current)
            or (row.get('draft_projection_sha256') not in {None, current})):
        fail('CURRENT_DRAFT_SELECTION_CHANGED')
    if notify and any(article.get('article_type', 'news') != 'news' for article in articles):
        fail('WECHAT_BROADCAST_NEWS_REQUIRES_NEWS')
    return current


def guard_advanced_dispatch(policy, registry, reference):
    """The advanced send path already holds the account writer lock."""
    anchor = _anchor(policy, registry)
    handle = 'current-pub-' + digest([stable_account(policy.data), reference])[:48]
    row = read_metadata(anchor / DIRECTORY / (handle + '.json')) or _legacy(anchor, reference=reference)
    if row is not None and row.get('submit_count'):
        fail('CURRENT_PUBLICATION_ORIGINAL_REQUEST_REQUIRED')


def _guard_advanced_attempt(policy, reference, projection):
    from .current_draft_management import journal
    try:
        with journal(policy) as db:
            prior = db.execute(
                "SELECT 1 FROM operations WHERE json_extract(row_json,'$.kind')='send_broadcast' "
                "AND json_extract(row_json,'$.account_key')=? AND json_extract(row_json,'$.request_count')>0 "
                "AND (json_extract(row_json,'$.draft_reference_sha256')=? OR "
                "json_extract(row_json,'$.intent.draft_sha')=?) LIMIT 1",
                (stable_account(policy.data), digest(reference), projection)).fetchone()
    except WCEError as error:
        if error.code != 'CURRENT_DRAFT_OPERATION_NOT_FOUND':
            raise
        return
    if prior is not None:
        fail('WECHAT_BROADCAST_ORIGINAL_REQUEST_REQUIRED')


def _mass_result(row, reply, submitting):
    result, code = reply.result, reply.error_code
    if result is not None:
        if result.get('task') is not None and submitting:
            row['task'] = asdict(result['task'])
        if result.get('msg_data_id'):
            row['msg_data_id'] = result['msg_data_id']
        if submitting and row.get('task') is not None:
            row['permission_state'] = 'ACCEPTED_BY_WECHAT'
        status = result.get('platform_status')
        row['state'] = {
            'SENDING': 'PROCESSING', 'SEND_SUCCESS': 'BROADCAST_SENT',
            'SEND_FAIL': 'BROADCAST_FAILED', 'DELETE': 'BROADCAST_DELETED',
            'AWAITING_ADMIN': 'AWAITING_ADMIN',
        }.get(status, 'ACCEPTED')
    elif submitting and code in MASS_NOT_SENT:
        row['state'] = 'NOT_SENT'
        if code == 45028:
            row['quota_state'] = 'EXHAUSTED'
        if code in {48001, 61007}:
            row['permission_state'] = 'DENIED'


def execute(service, method, arguments, registry, deadline, cancel_guard=None):
    policy = service.policy

    def guard():
        service.guard(deadline)
        if cancel_guard is not None:
            cancel_guard()
        if arguments['connection_id'] != policy.data['connection_id']:
            fail('CONNECTION_SCOPE_MISMATCH')

    guard()
    anchor = _anchor(policy, registry)
    submitting = method.endswith('.dispatch')
    notify = arguments.get('mode', 'ordinary') == 'notify'
    fallback = arguments.get('fallback_from_notify', False)
    if notify and fallback:
        fail('CURRENT_PUBLICATION_FALLBACK_MODE_INVALID')
    selected = _selected(policy, arguments.get('selection'), guard)
    handle_arg = arguments.get('intent_handle')
    if submitting:
        # Validate the original successful save/task before creating anything.
        # Re-read under the original locks: another caller may submit meanwhile.
        _, initial = _locate(policy, registry, handle_arg, selected)
        if not initial['submit_count']:
            _initialize_dispatch(policy, registry, guard)
    with ExitStack() as stack:
        for lock in (anchor / 'publication.lock', policy.root / 'publication-dispatch.lock',
                     policy.root / 'connection-policy.lock'):
            stack.enter_context(locked(lock, nonblocking=True, existing=True))
        guard()
        _coordination(policy, registry)
        path, row = _locate(policy, registry, handle_arg, selected)
        if method.endswith('.status'):
            return public_target(row)
        can_fallback = (row.get('mode') == 'notify' and row['state'] == 'NOT_SENT'
                        and row.get('task') is None)
        if submitting and fallback and not can_fallback:
            if row.get('notify_attempt') is not None:
                return public_target(row)
            fail('CURRENT_PUBLICATION_FALLBACK_UNAVAILABLE')
        if submitting and row['submit_count'] and not fallback:
            return public_target(row)
        if not submitting:
            if row.get('task') is None or row['state'] in MASS_TERMINAL | {
                    'PUBLISHED', 'PLATFORM_FAILED', 'PLATFORM_REJECTED', 'DENIED', 'TASK_CONFLICT'}:
                return public_target(row)
            notify = row.get('mode') == 'notify'
        token = service.tokens.get(guard)
        guard()
        handle, account = row['intent_handle'], stable_account(policy.data)
        task = None if submitting else TaskID(**row['task'])
        wire_method = ('mass.sendall' if submitting else 'mass.get') if notify else (
            'freepublish.submit' if submitting else 'freepublish.get')
        payload = {'media_id': DraftMediaID(row['reference'], account, handle)} if submitting else {'task_id': task}
        if notify and submitting:
            payload['clientmsgid'] = digest([account, handle, 'ALL_FOLLOWERS'])[:32]
        request = encode(wire_method, payload, token.token, account_key=account, intent_id=handle)

        def remaining():
            guard()
            if not service.tokens.valid(token):
                fail('OWN_TOKEN_UNAVAILABLE')
            timeout = min(30.0, deadline - time.monotonic(), token.wall_deadline - time.time())
            if timeout <= 0:
                fail('CURRENT_PUBLICATION_DEADLINE')
            return timeout

        if submitting:
            if notify or fallback or selected is not None:
                projection = _verify_draft(service, token, row, selected, remaining(), guard, notify=notify)
            else:
                projection = None
            _guard_advanced_attempt(policy, row['reference'], projection)
            if fallback:
                snapshot = {name: row.get(name) for name in (
                    'state', 'reply', 'permission_state', 'quota_state', 'draft_projection_sha256')}
                row = dict(row, notify_attempt=snapshot, reply=None, queries=0)
            row = dict(row, mode='notify' if notify else 'ordinary', state='UNKNOWN',
                       submit_count=row['submit_count'] + 1)
            if projection is not None:
                row['draft_projection_sha256'] = projection
            if notify:
                from .wechat_official_profile import read_official_profile
                profile = read_official_profile(registry, policy.data['connection_id'],
                                                policy.data['appid'], getattr(policy, 'fingerprint', None))
                row['authorizer_permission_state'] = (
                    'AUTHORIZED' if 7 in profile.get('permissions', []) else 'MISSING'
                ) if profile['state'] == 'ACTIVE' else 'UNKNOWN'
        timeout = remaining()
        if submitting:
            # The durable marker precedes the only write request.
            _write(path, row)
        try:
            response = service.workflow.sender.send(request, timeout)
            reply = parse(wire_method, response, token.token, account_key=account,
                intent_id=handle, expected_task=task, article_count=row['article_count'])
            if notify:
                if not submitting:
                    row['queries'] = row.get('queries', 0) + 1
                _mass_result(row, reply, submitting)
            elif submitting:
                if reply.result is not None:
                    row.update(state='ACCEPTED', task=asdict(reply.result['task']))
                elif reply.error_code is not None:
                    row.update(state='PLATFORM_REJECTED')
            else:
                row['queries'] = row.get('queries', 0) + 1
                if reply.result is not None:
                    status = reply.result['platform_status']
                    row['state'] = ('PUBLISHED' if reply.result['url_evidence'] == 'COMPLETE'
                        else 'PUBLISHED_URLS_INCOMPLETE') if status == 0 else 'PROCESSING' if status == 1 else 'PLATFORM_FAILED'
            observation = dict(_project(reply.result) or {}, error_code=reply.error_code,
                reason=reply.reason, response_sha256=reply.response_sha, http_status=reply.http_status)
            if notify and not submitting and reply.result is None:
                row['last_query'] = observation
            else:
                row['reply'] = observation
                if notify and not submitting:
                    row.pop('last_query', None)
            if isinstance(row['reply'].get('article_id'), dict):
                row['reply']['article_id'] = row['reply']['article_id']['value']
            _write(path, row)
        except Exception:
            # An existing task remains queryable even after a failed GET.
            raise WCEError('CURRENT_PUBLICATION_RESULT_UNKNOWN_QUERY_ORIGINAL') from None
        return public_target(row)
