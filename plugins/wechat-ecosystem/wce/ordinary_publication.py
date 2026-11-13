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


def _locate(policy, registry, handle):
    anchor = _anchor(policy, registry)
    from .current_draft_management import HANDLE as MERGED, publication_source
    if STEP.fullmatch(handle) or MERGED.fullmatch(handle):
        is_merge = MERGED.fullmatch(handle) is not None
        reference, titles = publication_source(policy, handle) if is_merge else _saved(policy, handle)
        publication = 'current-pub-' + digest([stable_account(policy.data), reference])[:48]
        path = anchor / DIRECTORY / (publication + '.json')
        row = read_metadata(path)
        if row is None:
            row = _legacy(anchor, reference=reference)
        if row is None:
            row = {'intent_handle': publication, 'account_key': stable_account(policy.data),
                'reference': reference, 'source_merge' if is_merge else 'source_step': handle, 'state': 'NOT_ATTEMPTED',
                'submit_count': 0, 'task': None, 'article_count': len(titles), 'titles': titles,
                'queries': 0, 'reply': None, 'quality_source': 'NOT_REQUIRED'}
    elif HANDLE.fullmatch(handle):
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
    if (STEP.fullmatch(handle) or MERGED.fullmatch(handle)) and row.get('reference') != reference:
        fail('CURRENT_PUBLICATION_DRAFT_MISMATCH')
    if row.get('intent_handle') != path.stem:
        fail('CURRENT_PUBLICATION_INTENT_INVALID')
    return path, row


def local_status(policy, registry, handle):
    """The original save handle is also a zero-network recovery handle."""
    policy.check(readonly=True)
    _, row = _locate(policy, registry, handle)
    policy.check(readonly=True)
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
    if method.endswith('.dispatch'):
        # Validate the original successful save/task before creating anything.
        # Re-read under the original locks: another caller may submit meanwhile.
        _, initial = _locate(policy, registry, arguments['intent_handle'])
        if not initial['submit_count']:
            _initialize_dispatch(policy, registry, guard)
    with ExitStack() as stack:
        for lock in (anchor / 'publication.lock', policy.root / 'publication-dispatch.lock',
                     policy.root / 'connection-policy.lock'):
            stack.enter_context(locked(lock, nonblocking=True, existing=True))
        guard()
        _coordination(policy, registry)
        path, row = _locate(policy, registry, arguments['intent_handle'])
        if method.endswith('.status'):
            return public_target(row)
        submitting = method.endswith('.dispatch')
        if submitting and row['submit_count']:
            return public_target(row)
        if not submitting and (row.get('task') is None or row['state'] in
                {'PUBLISHED', 'PLATFORM_FAILED', 'PLATFORM_REJECTED', 'DENIED', 'TASK_CONFLICT'}):
            return public_target(row)
        token = service.tokens.get(guard)
        guard()
        handle, account = row['intent_handle'], stable_account(policy.data)
        task = None if submitting else TaskID(**row['task'])
        wire_method = 'freepublish.submit' if submitting else 'freepublish.get'
        payload = {'media_id': DraftMediaID(row['reference'], account, handle)} if submitting else {'task_id': task}
        request = encode(wire_method, payload, token.token, account_key=account, intent_id=handle)
        if submitting:
            # Persist before HTTP. A lost response never causes a second submit.
            row = dict(row, state='UNKNOWN', submit_count=1)
            _write(path, row)
        try:
            guard()
            if not service.tokens.valid(token):
                fail('OWN_TOKEN_UNAVAILABLE')
            timeout = min(30.0, deadline - time.monotonic(), token.wall_deadline - time.time())
            if timeout <= 0:
                fail('CURRENT_PUBLICATION_DEADLINE')
            response = service.workflow.sender.send(request, timeout)
            reply = parse(wire_method, response, token.token, account_key=account,
                intent_id=handle, expected_task=task, article_count=row['article_count'])
            if submitting:
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
            row['reply'] = dict(_project(reply.result) or {}, error_code=reply.error_code,
                reason=reply.reason, response_sha256=reply.response_sha, http_status=reply.http_status)
            if isinstance(row['reply'].get('article_id'), dict):
                row['reply']['article_id'] = row['reply']['article_id']['value']
            _write(path, row)
        except Exception:
            # An existing task remains queryable even after a failed GET.
            raise WCEError('CURRENT_PUBLICATION_RESULT_UNKNOWN_QUERY_ORIGINAL') from None
        return public_target(row)
