"""One-shot existing-draft intents, separate from legacy ADD and auto policy.

Every caller mutating this ledger owns PublicationStore.dispatch_lock. The
stable AppID anchor is shared by aliases and both publication lanes. A durable
claim is never made available again, including a crash before HTTP starts.
"""
import os
from copy import deepcopy
import re
import secrets
import threading
from dataclasses import dataclass, field
from hashlib import sha256
from pathlib import Path

from .own_bootstrap_security import path_check
from .contracts import WCEError
from .own_connection_policy import atomic_write
from .publication_contract import binding, digest, exact, fail, legacy_projection_claims
from .publication_store import PublicationStore, read_file, sync_directory

MAX_LEDGER = 1024 * 1024
DIRECTORY = 'current-draft-intents'
STATES = {'READY', 'SUBMIT_CLAIMED', 'UNKNOWN', 'ACCEPTED', 'PROCESSING',
          'PUBLISHED', 'PUBLISHED_URLS_INCOMPLETE', 'PLATFORM_FAILED', 'DENIED',
          'PLATFORM_REJECTED', 'TASK_CONFLICT'}
HANDLE = re.compile(r'current-pub-[a-f0-9]{48}\Z')
PERMISSION_ERRORS = frozenset({48001, 48002, 48004, 48005, 53503, 53504, 53505})
TRANSITIONS = {
    'READY': {'READY', 'SUBMIT_CLAIMED'},
    'SUBMIT_CLAIMED': {'SUBMIT_CLAIMED', 'UNKNOWN', 'ACCEPTED', 'DENIED', 'PLATFORM_REJECTED', 'TASK_CONFLICT'},
    'UNKNOWN': {'UNKNOWN', 'ACCEPTED', 'TASK_CONFLICT'},
    'ACCEPTED': {'ACCEPTED', 'PROCESSING', 'PUBLISHED', 'PUBLISHED_URLS_INCOMPLETE', 'PLATFORM_FAILED', 'TASK_CONFLICT'},
    'PROCESSING': {'PROCESSING', 'PUBLISHED', 'PUBLISHED_URLS_INCOMPLETE', 'PLATFORM_FAILED', 'TASK_CONFLICT'},
    'PUBLISHED_URLS_INCOMPLETE': {'PUBLISHED_URLS_INCOMPLETE', 'PUBLISHED', 'TASK_CONFLICT'},
    'PUBLISHED': {'PUBLISHED'}, 'PLATFORM_FAILED': {'PLATFORM_FAILED'},
    'DENIED': {'DENIED'}, 'PLATFORM_REJECTED': {'PLATFORM_REJECTED'}, 'TASK_CONFLICT': {'TASK_CONFLICT'},
}
MUTABLE_TARGET_FIELDS = frozenset({'state', 'submit_count', 'quota', 'task', 'reply',
    'queries', 'query_pending', 'reason', 'last_query', 'recovered_receipt_sha256'})
_TICKET_SEAL = object()


@dataclass(frozen=True)
class _ReplyTicket:
    account_key: str
    binding_sha: str
    handle: str
    method: str
    request: object = field(repr=False)
    token: object = field(repr=False)
    task: object = field(repr=False)
    article_count: int
    head: object = field(repr=False)
    enrollment: object = field(repr=False)
    root_identity: tuple
    anchor_identity: tuple
    process_id: int
    thread_id: int
    _seal: object = field(repr=False)


def initialize_anchor(store):
    # Do not call legacy _make_anchor(): it creates a legacy head/migration.
    for directory in (store.anchor_root, store.anchor):
        try:
            directory.mkdir(mode=0o700)
        except FileExistsError:
            pass
        path_check(directory, True)
        sync_directory(directory.parent)


def _bounded_names(directory):
    names = set()
    with os.scandir(directory) as entries:
        for entry in entries:
            names.add(entry.name)
            if len(names) > 4096:
                fail('CURRENT_PUBLICATION_LEDGER_LIMIT')
    return names


def _successor_row(old, link):
    if type(old) is not dict or type(link) is not dict or type(link.get('effect')) is not dict:
        fail('CURRENT_REVISION_SUCCESSOR_CORRUPT')
    effect=link['effect'];projection=effect.get('projection')
    if (type(projection) is not dict or type(projection.get('response')) is not dict
            or type(projection['response'].get('news_item')) is not list):
        fail('CURRENT_REVISION_SUCCESSOR_CORRUPT')
    rows=projection['response']['news_item']
    if not 1<=len(rows)<=8 or any(type(item) is not dict or type(item.get('title')) is not str for item in rows):
        fail('CURRENT_REVISION_SUCCESSOR_CORRUPT')
    result=deepcopy(old)
    result.update(intent_handle=link['successor_handle'],revision_successor_of=link['original_intent'],
        projection_sha256=effect['projection_sha256'],response_sha256=effect['response_sha256'],
        article_count=len(rows),titles=[item['title'] for item in rows],
        content_claims=[list(item) for item in legacy_projection_claims(projection)])
    return result


def _transition(before, after, verify_recovery, verify_revision=None, verify_successor=None, verify_pending_upload=None):
    if (type(before) is not dict or type(after) is not dict
            or before.get('sequence', -1) + 1 != after.get('sequence')
            or before.get('schema') != after.get('schema')
            or before.get('account_key') != after.get('account_key')
            or type(before.get('batches')) is not dict or type(after.get('batches')) is not dict
            or type(before.get('targets')) is not dict or type(after.get('targets')) is not dict
            or not set(before['batches']) <= set(after['batches'])
            or not set(before['targets']) <= set(after['targets'])
            or (before.get('denial') is not None and before.get('denial') != after.get('denial'))):
        fail('CURRENT_PUBLICATION_LEDGER_CORRUPT')
    old_reservations = before.get('revision_reservations', {})
    new_reservations = after.get('revision_reservations', {})
    old_pending=before.get('revision_pending_images',{})
    new_pending=after.get('revision_pending_images',{})
    if (type(old_pending) is not dict or type(new_pending) is not dict
            or not set(old_pending)<=set(new_pending)
            or any(new_pending[k]!=v for k,v in old_pending.items())):
        fail('CURRENT_REVISION_PENDING_HOLD')
    from .current_publication_pending_image import validate as validate_pending
    for handle in new_pending:
        if (handle not in before['targets'] or before['targets'][handle]!=after['targets'].get(handle)):
            fail('CURRENT_REVISION_PENDING_HOLD')
        validate_pending(before['targets'][handle],new_pending[handle])
    old_baselines=before.get('revision_pending_baselines',{})
    new_baselines=after.get('revision_pending_baselines',{})
    if (type(old_baselines) is not dict or type(new_baselines) is not dict
            or not set(old_baselines)<=set(new_baselines) or not set(new_baselines)<=set(old_pending)):
        fail('DRAFT_REVISION_PENDING_BASELINE_HOLD')
    from .draft_revision_pending_baseline import validate as validate_pending_baseline
    for handle,new in new_baselines.items():
        validate_pending_baseline(new,old_pending[handle])
        old=old_baselines.get(handle)
        if old is None:
            if new['state']!='CLAIMED' or new['ordinal']!=1:fail('DRAFT_REVISION_PENDING_BASELINE_HOLD')
        elif old!=new:
            same_claim=(old['state']=='CLAIMED' and new['state'] in {'OBSERVED','UNKNOWN','MISMATCH'}
                and old['ordinal']==new['ordinal'])
            next_read=(old['state']=='UNKNOWN' and new['state']=='CLAIMED'
                and new['ordinal']==old['ordinal']+1 and new['ordinal']<=5)
            if (not (same_claim or next_read)
                    or any(old[k]!=new[k] for k in ('proposal_sha256','request_sha256'))):
                fail('DRAFT_REVISION_PENDING_BASELINE_HOLD')
    old_uploads=before.get('revision_pending_uploads',{})
    new_uploads=after.get('revision_pending_uploads',{})
    if (type(old_uploads) is not dict or type(new_uploads) is not dict
            or not set(old_uploads)<=set(new_uploads) or not set(new_uploads)<=set(old_baselines)):
        fail('DRAFT_REVISION_PENDING_UPLOAD_HOLD')
    from .draft_revision_pending_upload import validate as validate_pending_upload
    for handle,new in new_uploads.items():
        validate_pending_upload(new,old_pending[handle],old_baselines[handle])
        old=old_uploads.get(handle)
        if old is None:
            if new['state']!='CLAIMED':fail('DRAFT_REVISION_PENDING_UPLOAD_HOLD')
        elif old!=new:
            legal=((old['state']=='CLAIMED' and new['state'] in {'SUCCEEDED','UNKNOWN','REJECTED'})
                or (old['state']=='UNKNOWN' and new['state'] in {'SUCCEEDED','REJECTED'}))
            if (not legal
                    or any(old[k]!=new[k] for k in ('proposal_sha256','request_sha256','image_sha256'))):
                fail('DRAFT_REVISION_PENDING_UPLOAD_HOLD')
            if new['state'] in {'SUCCEEDED','REJECTED'}:
                if verify_pending_upload is None:fail('DRAFT_REVISION_PENDING_UPLOAD_HOLD')
                verify_pending_upload(handle,new)
    if (type(old_reservations) is not dict or type(new_reservations) is not dict
            or not set(old_reservations) <= set(new_reservations)
            or any(new_reservations[k] != v for k, v in old_reservations.items())):
        fail('CURRENT_REVISION_RESERVATION_CORRUPT')
    for handle in old_reservations:
        if before['targets'].get(handle)!=after['targets'].get(handle):
            fail('CURRENT_REVISION_RESERVATION_CORRUPT')
    for handle in set(new_reservations) - set(old_reservations):
        if handle not in before['targets'] or before['targets'][handle] != after['targets'].get(handle):
            fail('CURRENT_REVISION_RESERVATION_CORRUPT')
        if verify_revision is None:fail('CURRENT_REVISION_RESERVATION_CORRUPT')
        verify_revision(handle, before['targets'][handle], new_reservations[handle])
    old_successors = before.get('revision_successors', {})
    new_successors = after.get('revision_successors', {})
    if (type(old_successors) is not dict or type(new_successors) is not dict
            or not set(old_successors) <= set(new_successors)
            or any(new_successors[k] != v for k, v in old_successors.items())):
        fail('CURRENT_REVISION_SUCCESSOR_CORRUPT')
    for handle in set(new_successors) - set(old_successors):
        if (handle not in old_reservations or handle not in before['targets']
                or before['targets'][handle] != after['targets'].get(handle)
                or verify_successor is None):
            fail('CURRENT_REVISION_SUCCESSOR_CORRUPT')
        verify_successor(handle,before['targets'][handle],old_reservations[handle],new_successors[handle])
    activated = {}
    for original, link in old_successors.items():
        if (type(link) is not dict or type(link.get('successor_handle')) is not str
                or original not in before['targets']):
            fail('CURRENT_REVISION_SUCCESSOR_CORRUPT')
        child=link['successor_handle']
        if child not in before['targets'] and child in after['targets']:
            if verify_successor is None or original not in old_reservations:
                fail('CURRENT_REVISION_SUCCESSOR_CORRUPT')
            verify_successor(original,before['targets'][original],old_reservations[original],link)
            if after['targets'][child]!=_successor_row(before['targets'][original],link):
                fail('CURRENT_REVISION_SUCCESSOR_CORRUPT')
            activated[child]=original
    for source, old_batch in before['batches'].items():
        new_batch=after['batches'][source]
        if type(old_batch) is not dict or type(new_batch) is not dict:
            fail('CURRENT_PUBLICATION_LEDGER_CORRUPT')
        appended=[child for child,original in activated.items()
                  if before['targets'][original]['batch_source_sha']==source]
        if new_batch != dict(old_batch,intent_handles=old_batch['intent_handles']+appended):
            fail('CURRENT_PUBLICATION_LEDGER_CORRUPT')
    for handle in set(after['targets'])-set(before['targets']):
        if handle not in activated and after['targets'][handle].get('batch_source_sha') in before['batches']:
            fail('CURRENT_REVISION_SUCCESSOR_CORRUPT')
    for handle, old in before['targets'].items():
        new = after['targets'][handle]
        if (type(old) is not dict or type(new) is not dict
                or {k: v for k, v in old.items() if k not in MUTABLE_TARGET_FIELDS}
                   != {k: v for k, v in new.items() if k not in MUTABLE_TARGET_FIELDS}
                or old.get('state') not in TRANSITIONS
                or new.get('state') not in TRANSITIONS[old['state']]
                or (old.get('task') is not None and old['task'] != new.get('task'))
                or (old.get('quota') is not None and old['quota'] != new.get('quota'))
                or type(old.get('queries')) is not int or type(new.get('queries')) is not int
                or old['queries'] < 0 or new['queries'] not in (old['queries'], old['queries'] + 1)):
            fail('CURRENT_PUBLICATION_LEDGER_CORRUPT')
        old_receipt = old.get('recovered_receipt_sha256')
        new_receipt = new.get('recovered_receipt_sha256')
        if old_receipt != new_receipt:
            if (old_receipt is not None or old.get('state') not in {'SUBMIT_CLAIMED', 'UNKNOWN'}
                    or new.get('state') not in {'ACCEPTED', 'TASK_CONFLICT'} or old.get('task') is not None
                    or type(new_receipt) is not str or re.fullmatch('[0-9a-f]{64}', new_receipt) is None
                    or {k: v for k, v in old.items() if k not in {'state', 'task', 'reply', 'reason', 'recovered_receipt_sha256'}}
                       != {k: v for k, v in new.items() if k not in {'state', 'task', 'reply', 'reason', 'recovered_receipt_sha256'}}):
                fail('CURRENT_PUBLICATION_LEDGER_CORRUPT')
            verify_recovery(before, old, new)
        elif old.get('state') == 'UNKNOWN' and new.get('state') in {'ACCEPTED', 'TASK_CONFLICT'}:
            fail('CURRENT_PUBLICATION_LEDGER_CORRUPT')
        was, now = old.get('query_pending', False), new.get('query_pending', False)
        if (type(was) is not bool or type(now) is not bool
                or (new['queries'] == old['queries'] + 1 and (was or not now))
                or (new['queries'] == old['queries'] + 1 and old['state'] != new['state'])
                or (new['queries'] == old['queries'] and not was and now)):
            fail('CURRENT_PUBLICATION_LEDGER_CORRUPT')
    for handle in set(after['targets']) - set(before['targets']):
        row = after['targets'][handle]
        if type(row) is not dict or row.get('state') != 'READY' or row.get('submit_count') != 0:
            fail('CURRENT_PUBLICATION_LEDGER_CORRUPT')


class Store:
    def __init__(self, policy, registry, *, guard=None):
        if guard is not None and not callable(guard):
            fail('CURRENT_PUBLICATION_INVALID_GUARD')
        self.legacy = PublicationStore(policy, registry)
        self.policy = policy
        self.runtime_guard = guard or policy.check
        self.directory = self.legacy.anchor / DIRECTORY
        self.path = self.legacy.anchor / 'current-draft-intents-head.json'
        self.pin = policy.root / 'current-draft-intents-pin.json'
        self.enrollment_dir = Path(registry).parent / 'current-publication-enrollments'
        self.enrollment = self.enrollment_dir / (self.legacy.key + '.json')

    def _marker(self):
        pin = {'schema': 1, 'account_key': self.legacy.key,
            'directory': str(self.directory), 'identity': list(path_check(self.directory, True))}
        enrollment = read_file(self.enrollment, 16384)
        exact(enrollment, 'schema account_key anchor directory directory_identity pin sequence head_sha256')
        if (read_file(self.pin, 16384) != pin or enrollment['schema'] != 1
                or enrollment['account_key'] != self.legacy.key
                or enrollment['anchor'] != str(self.legacy.anchor)
                or enrollment['directory'] != str(self.directory)
                or enrollment['directory_identity'] != pin['identity']
                or enrollment['pin'] != str(self.pin)
                or type(enrollment['sequence']) is not int or not 0 <= enrollment['sequence'] <= 4096
                or (enrollment['head_sha256'] is not None if enrollment['sequence'] == 0 else
                    type(enrollment['head_sha256']) is not str or
                    re.fullmatch('[0-9a-f]{64}', enrollment['head_sha256']) is None)):
            fail('CURRENT_PUBLICATION_HISTORY_MISSING')
        return enrollment

    def _ensure_legacy_writable(self):
        # Once continuation initialization starts, the old source is the
        # immutable baseline. Pending/malformed markers are not permission to
        # resume writes; the continuation adapter must handle later changes.
        marker = self.policy.root / 'slot-continuation-v1-enrollment.json'
        if os.path.lexists(marker):
            fail('CURRENT_PUBLICATION_CONTINUATION_WRITE_REQUIRED')

    def initialize_locked(self):
        self.runtime_guard()
        self.policy.check()
        path_check(self.enrollment_dir.parent, True)
        try: self.enrollment_dir.mkdir(mode=0o700)
        except FileExistsError: pass
        path_check(self.enrollment_dir, True)
        sync_directory(self.enrollment_dir.parent)
        present = [os.path.lexists(p) for p in (self.directory, self.path, self.pin, self.enrollment)]
        if any(present) and not all(present):
            fail('CURRENT_PUBLICATION_HISTORY_MISSING')
        if not any(present):
            self.directory.mkdir(mode=0o700)
            sync_directory(self.directory.parent)
            directory_identity = list(path_check(self.directory, True))
            atomic_write(self.pin, {'schema': 1, 'account_key': self.legacy.key,
                'directory': str(self.directory), 'identity': directory_identity})
            atomic_write(self.enrollment, {'schema': 1, 'account_key': self.legacy.key,
                'anchor': str(self.legacy.anchor), 'directory': str(self.directory),
                'directory_identity': directory_identity, 'pin': str(self.pin),
                'sequence': 0, 'head_sha256': None})
            self.save({'schema': 1, 'account_key': self.legacy.key,
                'batches': {}, 'targets': {}, 'denial': None, 'sequence': 1})
        value = self.read()
        from .publication_lock import install_pin
        install_pin(self.legacy)
        return value

    def read(self):
        from .current_publication_continuation import ContinuationIndex
        index = ContinuationIndex(self)
        if any(os.path.lexists(path) for path in
               (index.enrollment_path,index.marker_path,index.db_path,index.head_path)):
            return index.legacy_view()
        return self._read_legacy()

    def _read_legacy(self):
        self.runtime_guard()
        enrollment = self._marker()
        head = read_file(self.path, 16384)
        exact(head, 'schema account_key sequence sha256')
        if (head['schema'] != 1 or head['account_key'] != self.legacy.key
                or type(head['sequence']) is not int or not 1 <= head['sequence'] <= 4096):
            fail('CURRENT_PUBLICATION_LEDGER_CORRUPT')
        if (head['sequence'] != enrollment['sequence']
                or head['sha256'] != enrollment['head_sha256']):
            fail('CURRENT_PUBLICATION_COMMIT_UNDETERMINED')
        expected = head['sha256']
        value, newer = None, None
        for sequence in range(head['sequence'], 0, -1):
            self.runtime_guard()
            event = read_file(self.directory / ('event-' + str(sequence) + '.json'), MAX_LEDGER)
            exact(event, 'value previous_sha256')
            if (type(event['value']) is not dict or digest(event) != expected
                    or event['value'].get('sequence') != sequence):
                fail('CURRENT_PUBLICATION_LEDGER_CORRUPT')
            if value is None:
                value = event['value']
            if newer is not None:
                _transition(event['value'], newer, self._verify_recovery, self._verify_revision_reservation, self._verify_revision_successor,self._verify_pending_upload_archive)
            newer = event['value']
            expected = event['previous_sha256']
        if expected is not None:
            fail('CURRENT_PUBLICATION_LEDGER_CORRUPT')
        names = _bounded_names(self.directory)
        expected_names = {'event-' + str(seq) + '.json' for seq in range(1, head['sequence'] + 1)}
        if names != expected_names:
            # Any missing or extra file is unacknowledged history. Do not
            # silently discard an orphan, including a non-adjacent event.
            fail('CURRENT_PUBLICATION_COMMIT_UNDETERMINED')
        expected_keys = {'schema','account_key','batches','targets','denial','sequence'}
        optional={'revision_reservations','revision_successors','revision_pending_images','revision_pending_baselines','revision_pending_uploads'}
        if type(value) is not dict or set(value)-optional!=expected_keys:
            fail('CURRENT_PUBLICATION_LEDGER_CORRUPT')
        if (value['schema'] != 1 or value['account_key'] != self.legacy.key
                or type(value['batches']) is not dict or type(value['targets']) is not dict
                or type(value['sequence']) is not int or value['sequence'] < 0):
            fail('CURRENT_PUBLICATION_LEDGER_CORRUPT')
        references, tasks = {}, set()
        from .publication_wire import TaskID, _task, article_url_supported
        listed = set()
        for source, batch in value['batches'].items():
            self.runtime_guard()
            if (type(source) is not str or re.fullmatch('[a-f0-9]{64}', source) is None
                    or type(batch) is not dict or set(batch) != {'inventory_handle', 'authority',
                        'intent_handles', 'inventory_sha256'}
                    or type(batch['inventory_handle']) is not str
                    or re.fullmatch('inventory-[a-f0-9]{48}', batch['inventory_handle']) is None
                    or type(batch['authority']) is not dict
                    or batch['authority'].get('source_sha256') != source
                    or type(batch['inventory_sha256']) is not str
                    or re.fullmatch('[a-f0-9]{64}', batch['inventory_sha256']) is None
                    or type(batch['intent_handles']) is not list):
                fail('CURRENT_PUBLICATION_LEDGER_CORRUPT')
            for handle in batch['intent_handles']:
                if (type(handle) is not str or handle in listed or handle not in value['targets']
                        or value['targets'][handle].get('batch_source_sha') != source):
                    fail('CURRENT_PUBLICATION_LEDGER_CORRUPT')
                listed.add(handle)
        if listed != set(value['targets']):
            fail('CURRENT_PUBLICATION_LEDGER_CORRUPT')
        for handle, row in value['targets'].items():
            self.runtime_guard()
            if (type(handle) is not str or HANDLE.fullmatch(handle) is None or type(row) is not dict
                    or row.get('intent_handle') != handle or row.get('state') not in STATES
                    or row.get('account_key') != self.legacy.key
                    or type(row.get('reference')) is not str
                    or type(row.get('submit_count')) is not int or row.get('submit_count') not in (0, 1)
                    or (row['state'] == 'READY') != (row['submit_count'] == 0)
                    or row.get('batch_source_sha') not in value['batches']
                    or type(row.get('queries')) is not int or row['queries'] < 0
                    or type(row.get('query_pending', False)) is not bool):
                fail('CURRENT_PUBLICATION_LEDGER_CORRUPT')
            with_task = row['state'] in {'ACCEPTED', 'PROCESSING', 'PUBLISHED',
                'PUBLISHED_URLS_INCOMPLETE', 'PLATFORM_FAILED', 'TASK_CONFLICT'}
            if with_task:
                try:
                    task = TaskID(**row['task'])
                    _task(task, 'PUBLISH_TASK', self.legacy.key, handle)
                except Exception:
                    fail('CURRENT_PUBLICATION_LEDGER_CORRUPT')
                if row['state'] != 'TASK_CONFLICT':
                    if (task.kind, task.digits) in tasks:
                        fail('CURRENT_PUBLICATION_LEDGER_CORRUPT')
                    tasks.add((task.kind, task.digits))
            elif row.get('task') is not None:
                fail('CURRENT_PUBLICATION_LEDGER_CORRUPT')
            if row.get('query_pending', False) and row['state'] not in {
                    'ACCEPTED', 'PROCESSING', 'PUBLISHED_URLS_INCOMPLETE'}:
                fail('CURRENT_PUBLICATION_LEDGER_CORRUPT')
            if row['state'] == 'PUBLISHED':
                reply = row.get('reply')
                if (type(reply) is not dict or type(reply.get('platform_status')) is not int
                        or reply['platform_status'] != 0 or reply.get('url_evidence') != 'COMPLETE'
                        or type(reply.get('article_id')) is not str or not reply['article_id']
                        or type(reply.get('article_urls')) is not list
                        or type(row.get('article_count')) is not int
                        or len(reply['article_urls']) != row['article_count']
                        or any(type(item) is not list or len(item) != 2 or type(item[0]) is not int
                            or item[0] != index or not article_url_supported(item[1])
                            for index, item in enumerate(reply['article_urls'], 1))
                        or len({item[1] for item in reply['article_urls']}) != len(reply['article_urls'])):
                    fail('CURRENT_PUBLICATION_LEDGER_CORRUPT')
            references.setdefault(row['reference'], []).append(handle)
        reservations = value.get('revision_reservations', {})
        pending=value.get('revision_pending_images',{})
        if type(pending) is not dict or not set(pending)<=set(value['targets']):
            fail('CURRENT_REVISION_PENDING_HOLD')
        from .current_publication_pending_image import validate as validate_pending
        for handle,record in pending.items():validate_pending(value['targets'][handle],record)
        baselines=value.get('revision_pending_baselines',{})
        if type(baselines) is not dict or not set(baselines)<=set(pending):
            fail('DRAFT_REVISION_PENDING_BASELINE_HOLD')
        from .draft_revision_pending_baseline import validate as validate_pending_baseline
        for handle,record in baselines.items():validate_pending_baseline(record,pending[handle])
        uploads=value.get('revision_pending_uploads',{})
        if type(uploads) is not dict or not set(uploads)<=set(baselines):
            fail('DRAFT_REVISION_PENDING_UPLOAD_HOLD')
        from .draft_revision_pending_upload import validate as validate_pending_upload
        for handle,record in uploads.items():
            validate_pending_upload(record,pending[handle],baselines[handle]);self._verify_pending_upload_archive(handle,record)
        if type(reservations) is not dict or not set(reservations) <= set(value['targets']):
            fail('CURRENT_REVISION_RESERVATION_CORRUPT')
        for handle, reservation in reservations.items():
            self._verify_revision_reservation(handle, value['targets'][handle], reservation)
            if handle in pending:
                from .current_publication_pending_image import verify_case_link
                verify_case_link(self,value,handle,reservation['case_id'],self.runtime_guard)
        successors = value.get('revision_successors', {})
        if type(successors) is not dict or not set(successors) <= set(reservations):
            fail('CURRENT_REVISION_SUCCESSOR_CORRUPT')
        successor_ids=set()
        for handle, successor in successors.items():
            self._verify_revision_successor(handle,value['targets'][handle],reservations[handle],successor)
            sid=successor['successor_handle']
            if sid in successor_ids:
                fail('CURRENT_REVISION_SUCCESSOR_CORRUPT')
            if sid in value['targets']:
                derived=_successor_row(value['targets'][handle],successor)
                if {k:v for k,v in derived.items() if k not in MUTABLE_TARGET_FIELDS} != {k:v for k,v in value['targets'][sid].items() if k not in MUTABLE_TARGET_FIELDS}:
                    fail('CURRENT_REVISION_SUCCESSOR_CORRUPT')
            successor_ids.add(sid)
        for handles in references.values():
            if len(handles)==1:continue
            if len(handles)!=2 or not any(original in handles and link['successor_handle'] in handles for original,link in successors.items()):
                fail('CURRENT_PUBLICATION_LEDGER_CORRUPT')
        if value['denial'] is not None:
            denial = value['denial']
            if (type(denial) is not dict or set(denial) != {'intent_handle', 'reply'}
                    or denial['intent_handle'] not in value['targets']
                    or value['targets'][denial['intent_handle']]['state'] != 'DENIED'
                    or value['targets'][denial['intent_handle']]['reply'] != denial['reply']):
                fail('CURRENT_PUBLICATION_LEDGER_CORRUPT')
        if self._marker() != enrollment:
            fail('CURRENT_PUBLICATION_COMMIT_UNDETERMINED')
        if read_file(self.path, 16384) != head or _bounded_names(self.directory) != expected_names:
            fail('CURRENT_PUBLICATION_COMMIT_UNDETERMINED')
        self.runtime_guard()
        return value

    def save(self, value):
        from .current_publication_continuation import ContinuationIndex
        index = ContinuationIndex(self)
        if any(os.path.lexists(path) for path in
               (index.enrollment_path,index.marker_path,index.db_path,index.head_path)):
            return index.legacy_save(value)
        return self._save_legacy(value)

    def _save_legacy(self, value):
        from .service import canonical
        from .publication_contract import strict_json
        self.runtime_guard()
        value = strict_json(canonical(value).encode('utf-8'), MAX_LEDGER)
        enrollment = self._marker()
        if os.path.lexists(self.path):
            before = self.read()
            _transition(before, value, self._verify_recovery, self._verify_revision_reservation, self._verify_revision_successor,self._verify_pending_upload_archive)
            previous = read_file(self.path, 16384)
        else:
            if _bounded_names(self.directory):
                fail('CURRENT_PUBLICATION_COMMIT_UNDETERMINED')
            previous = None
        if value['sequence'] != (previous['sequence'] + 1 if previous else 1):
            fail('CURRENT_PUBLICATION_LEDGER_SEQUENCE')
        event = {'value': value, 'previous_sha256': previous['sha256'] if previous else None}
        raw = (canonical(event) + '\n').encode()
        if len(raw) > MAX_LEDGER:
            fail('CURRENT_PUBLICATION_LEDGER_LIMIT')
        event_path = self.directory / ('event-' + str(value['sequence']) + '.json')
        self.runtime_guard()
        parent_pin = path_check(self.directory, True)
        fd = os.open(event_path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
        try:
            with os.fdopen(fd, 'wb', closefd=False) as output:
                output.write(raw)
                output.flush()
                os.fsync(fd)
        finally:
            os.close(fd)
        sync_directory(self.directory)
        if path_check(self.directory, True) != parent_pin or read_file(event_path, MAX_LEDGER) != event:
            fail('CURRENT_PUBLICATION_COMMIT_UNDETERMINED')
        self.runtime_guard()
        event_sha = digest(event)
        # Advance the independent high-water anchor first. If either write
        # loses acknowledgement, disagreement stays HOLD; never resend.
        atomic_write(self.enrollment, enrollment | {
            'sequence': value['sequence'], 'head_sha256': event_sha})
        self.runtime_guard()
        atomic_write(self.path, {'schema': 1, 'account_key': self.legacy.key,
            'sequence': value['sequence'], 'sha256': event_sha})
        self.runtime_guard()
        self.read()

    def _authority(self, authority, guard, source=None):
        from .single_publication_source import is_authority
        if (not is_authority(authority)
                or authority.policy_binding != binding(self.policy.data)
                or authority.connection_id != self.policy.data['connection_id']
                or (source is not None and authority.source_sha != source)):
            fail('CURRENT_PUBLICATION_HUMAN_SCOPE_REQUIRED')
        guard()
        authority.fence()
        guard()

    def preflight_single(self, inventory, targets, authority, guard):
        """Target-negative checks before reserving a request-wide choice.

        The native service calls this under the same account coordination lock
        as prepare. It never creates permission, a batch, or a submit claim.
        """
        from .single_publication_source import is_single
        if not is_single(authority):
            fail('SINGLE_PUBLICATION_AUTHORITY_REQUIRED')
        self._authority(authority, guard)
        if (inventory.get('coverage') != 'COMPLETE_OBSERVED_PAGINATION'
                or inventory.get('observed_groups') != inventory.get('total_groups')
                or len(targets) != inventory.get('total_groups')):
            fail('CURRENT_PUBLICATION_INVENTORY_INCOMPLETE')
        selected = [target for target in targets if target['reference'] == authority.proof.value['reference']]
        if len(selected) != 1 or selected[0]['article_count'] != 1:
            fail('SINGLE_PUBLICATION_WHOLE_SINGLE_GROUP_REQUIRED')
        target = selected[0]
        value = self.read()
        own = value['batches'].get(authority.source_sha)
        if own is not None:
            if len(own['intent_handles']) != 1:
                fail('SINGLE_PUBLICATION_ORIGINAL_SELECTION_ONLY')
            authority.check_target(value['targets'][own['intent_handles'][0]])
            return
        if value['denial'] is not None:
            fail('CURRENT_PUBLICATION_ACCOUNT_DENIED')
        wanted = set(map(tuple, target['content_claims']))
        for row in value['targets'].values():
            if row['reference'] == target['reference'] or (row['submit_count'] and
                    wanted.intersection(map(tuple, row.get('content_claims', [])))):
                fail('CURRENT_PUBLICATION_ORIGINAL_INTENT_REQUIRED')
        from .current_publication_continuation import ContinuationIndex
        index = ContinuationIndex(self)
        if any(os.path.lexists(path) for path in
                (index.enrollment_path, index.marker_path, index.db_path, index.head_path)):
            if index.slot_conflicts_held(target['reference'], target['content_claims']):
                fail('CURRENT_PUBLICATION_ORIGINAL_INTENT_REQUIRED')
        self.guard_legacy(target['reference'], target['content_claims'], authority=authority,
            guard=guard, source_sha=authority.source_sha)
        self._authority(authority, guard)

    def preflight_saved_groups(self, inventory, targets, authority, guard):
        """All exact requested groups remain eligible before any batch commit."""
        from .saved_groups_publication_source import is_saved_groups
        from .publication_inventory_access import complete_for
        if not is_saved_groups(authority) or not complete_for(authority, inventory):
            fail('SAVED_GROUPS_AUTHORITY_REQUIRED')
        self._authority(authority, guard)
        if (type(targets) is not list or len(targets) != inventory['total_groups']
                or [t['reference'] for t in targets] != inventory['target_references']):
            fail('SAVED_GROUPS_INVENTORY_SCOPE_CHANGED')
        value = self.read()
        own = value['batches'].get(authority.source_sha)
        if own is not None:
            original = [value['targets'][h] for h in own['intent_handles']
                        if 'revision_successor_of' not in value['targets'][h]]
            if [row['reference'] for row in original] != inventory['target_references']:
                fail('SAVED_GROUPS_ORIGINAL_SELECTION_ONLY')
            for row in original:
                authority.check_target(row)
            return
        if value['denial'] is not None:
            fail('CURRENT_PUBLICATION_ACCOUNT_DENIED')
        from .current_publication_continuation import ContinuationIndex
        index = ContinuationIndex(self)
        continuation_present = any(os.path.lexists(path) for path in
            (index.enrollment_path, index.marker_path, index.db_path, index.head_path))
        for target in targets:
            wanted = set(map(tuple, target['content_claims']))
            for row in value['targets'].values():
                if row['reference'] == target['reference'] or (row['submit_count'] and
                        wanted.intersection(map(tuple, row.get('content_claims', [])))):
                    fail('CURRENT_PUBLICATION_ORIGINAL_INTENT_REQUIRED')
            if continuation_present and index.slot_conflicts_held(target['reference'], target['content_claims']):
                fail('CURRENT_PUBLICATION_ORIGINAL_INTENT_REQUIRED')
            self.guard_legacy(target['reference'], target['content_claims'], authority=authority,
                guard=guard, source_sha=authority.source_sha)
        self._authority(authority, guard)

    def prepare(self, inventory, targets, authority, guard):
        from . import publication_inventory_access as observed
        from .current_publication_service import content_claims
        if type(inventory) is not dict or type(targets) is not list:
            fail('CURRENT_PUBLICATION_HUMAN_SCOPE_REQUIRED')
        self._authority(authority, guard)
        checked = observed.load_complete(self.policy, inventory.get('inventory_handle'), guard)
        if checked != inventory or not observed.complete_for(authority, checked):
            fail('CURRENT_PUBLICATION_BATCH_CHANGED')
        derived = []
        for page, index, page_sha, target in observed.frozen_targets(self.policy, checked, guard):
            if page['observed_ms'] < authority.request_ms:
                fail('CURRENT_PUBLICATION_INVENTORY_PRECEDES_REQUEST')
            rows = target['projection']['response']['news_item']
            derived.append({key: target[key] for key in ('reference', 'listed_update_time',
                'projection_sha256', 'response_sha256')} | {
                'inventory_handle': checked['inventory_handle'], 'page': page['page'],
                'page_sha256': page_sha, 'page_index': index,
                'article_count': len(rows), 'titles': [row['title'] for row in rows],
                'content_claims': content_claims(target['projection'])})
        derived.sort(key=lambda item: (item['page'], item['page_index']))
        if len(derived) != checked.get('total_groups'):
            fail('CURRENT_PUBLICATION_INVENTORY_INCOMPLETE')
        from .single_publication_source import selected_targets, is_single, QUALITY
        from .saved_groups_publication_source import is_saved_groups
        if is_single(authority):
            self.preflight_single(checked, derived, authority, guard)
        derived = selected_targets(authority, checked, derived)
        if is_saved_groups(authority):
            self.preflight_saved_groups(checked, derived, authority, guard)
        if (derived != targets or len({row['reference'] for row in derived}) != len(derived)):
            fail('CURRENT_PUBLICATION_INVENTORY_TARGET_MISMATCH')
        authority.fence()
        guard()
        value = self.read()
        if (not observed.complete_for(authority, inventory)
                or (not is_single(authority) and len(targets) != inventory.get('total_groups'))):
            fail('CURRENT_PUBLICATION_INVENTORY_INCOMPLETE')
        evidence = authority.evidence()
        source = evidence['source_sha256']
        batch = value['batches'].get(source)
        if batch is not None:
            original_handles=[h for h in batch['intent_handles'] if 'revision_successor_of' not in value['targets'][h]]
            if (batch['inventory_handle'] != inventory['inventory_handle']
                    or batch['inventory_sha256'] != digest(inventory)):
                fail('CURRENT_PUBLICATION_BATCH_ALREADY_FROZEN')
            # The complete checkpoint remains frozen, while intent_handles is
            # the immutable first-admission subset. Reentry never fills holes,
            # even when an excluded target's hold has since been removed.
            by_reference = {target['reference']: target for target in derived}
            for handle in original_handles:
                stored = value['targets'][handle]
                target = by_reference.get(stored['reference'])
                if target is None:
                    fail('CURRENT_PUBLICATION_BATCH_ALREADY_FROZEN')
                if digest({key: stored[key] for key in target}) != digest(target):
                    fail('CURRENT_PUBLICATION_BATCH_ALREADY_FROZEN')
            authority.fence()
            guard()
            return value
        if value['denial'] is not None:
            fail('CURRENT_PUBLICATION_ACCOUNT_DENIED')
        existing = {row['reference']: row for row in value['targets'].values()}
        new = {}
        from .current_publication_continuation import ContinuationIndex
        index = ContinuationIndex(self)
        continuation_present = any(os.path.lexists(path) for path in
            (index.enrollment_path,index.marker_path,index.db_path,index.head_path))
        for target in targets:
            if target['reference'] in existing:
                # Preserve the original intent and its authority. It is not a
                # prerequisite for unrelated targets, nor reissued here.
                continue
            if continuation_present and index.slot_conflicts_held(target['reference'],target['content_claims']):
                self._authority(authority,guard,source)
                continue
            try:
                self.guard_legacy(target['reference'], target['content_claims'], authority=authority, guard=guard, source_sha=source)
            except WCEError as error:
                if error.code not in {'DRAFT_REVISION_TARGET_WRITE_HOLD',
                        'CURRENT_PUBLICATION_LEGACY_CONFLICT',
                        'CURRENT_PUBLICATION_LEGACY_CONTENT_CONFLICT'}:
                    raise
                # Only these exact target-negative results are exclusions.
                # Source, identity, corruption and all unknown errors remain
                # whole-operation failures, including a changed authority now.
                self._authority(authority, guard, source)
                continue
            handle = 'current-pub-' + secrets.token_hex(24)
            new[handle] = dict(target, intent_handle=handle, batch_source_sha=source,
                account_key=self.legacy.key, binding_sha256=binding(self.policy.data),
                state='READY', submit_count=0, task=None, reply=None, queries=0)
            if is_single(authority):
                new[handle]['quality_source'] = QUALITY
            from .saved_groups_publication_source import is_saved_groups
            if is_saved_groups(authority):
                new[handle]['quality_source'] = authority.quality_source
                authority.check_target(new[handle])
        value['batches'][source] = {'inventory_handle': inventory['inventory_handle'],
            'authority': evidence, 'intent_handles': list(new),
            'inventory_sha256': digest(inventory)}
        value['targets'].update(new)
        value['sequence'] += 1
        authority.fence()
        guard()
        if continuation_present:
            index.legacy_prepare(value, inventory, targets, authority, guard)
        else:
            self.save(value)
        authority.fence()
        guard()
        return value

    def _verify_revision_reservation(self, handle, row, reservation):
        from .current_publication_revision_reservation import verify_reservation
        verify_reservation(self, handle, row, reservation, self.runtime_guard)

    def _verify_pending_upload_archive(self,handle,record):
        from .draft_revision_pending_upload import verify_archive
        return verify_archive(self,handle,record)

    def reserve_revision(self, handle, case_id, gate, authority, guard):
        """Reserve an exact READY target before a revision may write or upload."""
        from .current_publication_revision_reservation import reserve
        return reserve(self, handle, case_id, gate, authority, guard)

    def _verify_revision_successor(self,handle,row,reservation,successor):
        from .current_publication_revision_successor import verify_successor
        verify_successor(self,handle,row,reservation,successor,self.runtime_guard)

    def stage_revision_successor(self,handle,case_id,gate,authority,guard):
        from .current_publication_revision_successor import stage
        return stage(self,handle,case_id,gate,authority,guard)

    def activate_revision_successor(self,handle,gate,authority,guard):
        from .current_publication_revision_successor import activate
        return activate(self,handle,gate,authority,guard)

    def target(self, handle):
        if type(handle) is not str or HANDLE.fullmatch(handle) is None:
            fail('CURRENT_PUBLICATION_INTENT_INVALID')
        value = self.read()
        if handle not in value['targets']:
            fail('CURRENT_PUBLICATION_INTENT_NOT_FOUND')
        return value, value['targets'][handle]

    def verify_claim(self, handle, guard, authority):
        """Perform the original read-only admission checks without writing."""
        from . import publication_inventory_access as observed
        from .current_publication_service import content_claims
        value, row = self.target(handle)
        self._authority(authority, guard, row['batch_source_sha'])
        from .single_publication_source import is_single
        from .saved_groups_publication_source import is_saved_groups
        if is_single(authority) or is_saved_groups(authority): authority.check_target(row)
        if value['denial'] is not None:
            fail('CURRENT_PUBLICATION_ACCOUNT_DENIED')
        if handle in value.get('revision_reservations', {}) or handle in value.get('revision_pending_images',{}):
            fail('CURRENT_PUBLICATION_REVISION_RESERVED')
        if row['state'] != 'READY' or row['submit_count'] != 0:
            fail('CURRENT_PUBLICATION_ORIGINAL_INTENT_REQUIRED')
        wanted = set(map(tuple, row['content_claims']))
        for other in value['targets'].values():
            if other['intent_handle'] == handle or not other['submit_count']:
                continue
            if wanted.intersection(map(tuple, other['content_claims'])):
                fail('CURRENT_PUBLICATION_CONTENT_ALREADY_CLAIMED')
        original=row.get('revision_successor_of')
        if original is not None:
            link=value.get('revision_successors',{}).get(original)
            if (type(link) is not dict or link.get('successor_handle')!=handle
                    or original not in value.get('revision_reservations',{})):
                fail('CURRENT_REVISION_SUCCESSOR_CORRUPT')
            self._verify_revision_successor(original,value['targets'][original],
                value['revision_reservations'][original],link)
            projection=link['effect']['projection']
            if (digest(projection)!=row['projection_sha256']
                    or digest(content_claims(projection))!=digest(row['content_claims'])):
                fail('CURRENT_PUBLICATION_FROZEN_TARGET_CHANGED')
            self.guard_legacy(row['reference'],row['content_claims'],authority=authority,
                guard=guard,source_sha=row['batch_source_sha'],successor_handle=handle)
        else:
            checkpoint = observed.load_complete(self.policy, row['inventory_handle'], guard)
            if digest(checkpoint) != value['batches'][row['batch_source_sha']]['inventory_sha256']:
                fail('CURRENT_PUBLICATION_BATCH_CHANGED')
            matches = []
            for page, index, page_sha, target in observed.frozen_targets(self.policy, checkpoint, guard):
                if page['page'] == row['page'] and index == row['page_index']:
                    matches.append((page, page_sha, target))
            if len(matches) != 1:
                fail('CURRENT_PUBLICATION_FROZEN_TARGET_CHANGED')
            page, page_sha, target = matches[0]
            if (page_sha != row['page_sha256'] or page['observed_ms'] < authority.request_ms
                    or target['reference'] != row['reference']
                    or target['projection_sha256'] != row['projection_sha256']
                    or digest(content_claims(target['projection'])) != digest(row['content_claims'])):
                fail('CURRENT_PUBLICATION_FROZEN_TARGET_CHANGED')
            self.guard_legacy(row['reference'], row['content_claims'], authority=authority, guard=guard, source_sha=row['batch_source_sha'])
        self._authority(authority, guard, row['batch_source_sha'])
        return value, row

    def claim(self, handle, guard, quota, authority):
        value, row = self.verify_claim(handle, guard, authority)
        row.update(state='SUBMIT_CLAIMED', submit_count=1, quota=quota)
        value['sequence'] += 1
        self.save(value)
        self._authority(authority, guard, row['batch_source_sha'])
        return row

    def record_unknown(self, handle, guard):
        """A claimed submit with no trustworthy original result never retries."""
        value, row = self.target(handle)
        guard()
        if row['state'] not in {'SUBMIT_CLAIMED', 'UNKNOWN'} or row['task'] is not None:
            fail('CURRENT_PUBLICATION_INVALID_TRANSITION')
        if row['state'] == 'UNKNOWN':
            return row
        row.update(state='UNKNOWN', reason='SUBMIT_RESULT_UNDETERMINED')
        value['sequence'] += 1
        self.save(value)
        guard()
        return row

    def record_query_claim(self, handle, guard):
        """Record consumption before a read; an unknown read is never refunded."""
        value, row = self.target(handle)
        guard()
        if (row['state'] not in {'ACCEPTED', 'PROCESSING', 'PUBLISHED_URLS_INCOMPLETE'}
                or row['task'] is None or row.get('query_pending', False)
                or type(row['queries']) is not int or row['queries'] < 0):
            fail('CURRENT_PUBLICATION_INVALID_TRANSITION')
        row.update(query_pending=True, queries=row['queries'] + 1)
        value['sequence'] += 1
        self.save(value)
        guard()
        return row

    def record_query_unknown(self, handle, guard):
        value, row = self.target(handle)
        guard()
        if row.get('query_pending') is not True or row['state'] not in {
                'ACCEPTED', 'PROCESSING', 'PUBLISHED_URLS_INCOMPLETE'}:
            fail('CURRENT_PUBLICATION_INVALID_TRANSITION')
        row.update(query_pending=False, last_query={'reason': 'QUERY_RESULT_UNDETERMINED',
            'error_code': None, 'http_status': None, 'response_sha256': None})
        value['sequence'] += 1
        self.save(value)
        guard()
        return row

    def _legacy_task_conflict(self, task):
        from .publication_store import _history_scope
        self.runtime_guard()
        with self.legacy.connection() as db, _history_scope(self.policy, db) as history:
            if not self.legacy.exists(db, history_locators=history):
                return False
            self.legacy._verify(db, history_locators=history)
            return bool(db.execute('SELECT 1 FROM publication_intents WHERE account_key=? '
                'AND task_kind=? AND task_digits=? LIMIT 1',
                (self.legacy.key, task.kind, task.digits)).fetchone())

    def reply_ticket(self, handle, method, request, token, guard):
        """Capture fixed original request on the locked stack before HTTP."""
        from .http_transport import HTTPRequest
        from .publication_wire import DraftMediaID, TaskID, _task, encode
        value, row = self.target(handle)
        guard()
        if type(request) is not HTTPRequest or method not in {'freepublish.submit', 'freepublish.get'}:
            fail('CURRENT_PUBLICATION_INVALID_TRANSITION')
        if method == 'freepublish.submit':
            if row['state'] != 'SUBMIT_CLAIMED' or row['task'] is not None:
                fail('CURRENT_PUBLICATION_INVALID_TRANSITION')
            task = None
            expected = encode(method, {'media_id': DraftMediaID(row['reference'], self.legacy.key, handle)},
                token, account_key=self.legacy.key, intent_id=handle)
        else:
            if (row['state'] not in {'ACCEPTED', 'PROCESSING', 'PUBLISHED_URLS_INCOMPLETE'}
                    or row.get('query_pending') is not True or type(row['task']) is not dict):
                fail('CURRENT_PUBLICATION_INVALID_TRANSITION')
            try:
                task = TaskID(**row['task'])
                _task(task, 'PUBLISH_TASK', self.legacy.key, handle)
            except Exception:
                fail('CURRENT_PUBLICATION_ORIGINAL_TASK_REQUIRED')
            expected = encode(method, {'task_id': task}, token,
                account_key=self.legacy.key, intent_id=handle)
        if request != expected or type(row['article_count']) is not int or not 1 <= row['article_count'] <= 8:
            fail('CURRENT_PUBLICATION_REQUEST_MISMATCH')
        head = read_file(self.path, 16384)
        enrollment = self._marker()
        if head['sequence'] != enrollment['sequence'] or head['sha256'] != enrollment['head_sha256']:
            fail('CURRENT_PUBLICATION_COMMIT_UNDETERMINED')
        ticket = _ReplyTicket(self.legacy.key, binding(self.policy.data), handle, method, request, token,
            task, row['article_count'], head, enrollment, path_check(self.policy.root, True),
            path_check(self.legacy.anchor, True), os.getpid(), threading.get_ident(), _TICKET_SEAL)
        guard()
        return ticket

    def stage_reply(self, ticket, response, token):
        """Durably stage the minimal original reply after one admitted HTTP.

        Same process/thread and the caller's stable account lock are required.
        This bounded local receipt is intentionally independent of the expired
        send deadline; it grants no new request or publication permission.
        """
        from .publication_receipt import _project
        from .publication_wire import parse
        if (type(ticket) is not _ReplyTicket or ticket._seal is not _TICKET_SEAL
                or ticket.process_id != os.getpid() or ticket.thread_id != threading.get_ident()
                or ticket.account_key != self.legacy.key or ticket.binding_sha != binding(self.policy.data)
                or token is not ticket.token
                or path_check(self.policy.root, True) != ticket.root_identity
                or path_check(self.legacy.anchor, True) != ticket.anchor_identity
                or self._marker() != ticket.enrollment or read_file(self.path, 16384) != ticket.head):
            fail('CURRENT_PUBLICATION_RECEIPT_SCOPE_CHANGED')
        reply = parse(ticket.method, response, token, account_key=ticket.account_key,
            intent_id=ticket.handle, expected_task=ticket.task,
            article_count=ticket.article_count if ticket.task else None)
        proof = {'schema': 'CURRENT_PUBLICATION_RETURN_RECEIPT_V1',
            'account_key': ticket.account_key, 'binding_sha256': ticket.binding_sha,
            'intent_handle': ticket.handle, 'method': ticket.method,
            'head_sequence': ticket.head['sequence'], 'head_sha256': ticket.head['sha256'],
            'request_sha256': sha256(ticket.request.body).hexdigest(),
            'reason': reply.reason, 'error_code': reply.error_code,
            'http_status': reply.http_status, 'response_sha256': reply.response_sha,
            'result': _project(reply.result)}
        receipt_dir = self.legacy.anchor / 'current-publication-receipts'
        try:
            receipt_dir.mkdir(mode=0o700)
            sync_directory(receipt_dir.parent)
        except FileExistsError:
            pass
        path_check(receipt_dir, True)
        name = digest({key: proof[key] for key in ('account_key', 'intent_handle', 'method',
            'head_sequence', 'head_sha256', 'request_sha256')}) + '.json'
        path = receipt_dir / name
        if os.path.lexists(path):
            if read_file(path, 128 * 1024) != proof:
                fail('CURRENT_PUBLICATION_RECEIPT_CONFLICT')
        else:
            atomic_write(path, proof, maximum=128 * 1024)
        if (self._marker() != ticket.enrollment or read_file(self.path, 16384) != ticket.head
                or read_file(path, 128 * 1024) != proof):
            fail('CURRENT_PUBLICATION_RECEIPT_UNDETERMINED')
        return {'state': 'ORIGINAL_REPLY_STAGED', 'receipt_sha256': digest(proof),
            'receipt_name': name, 'intent_handle': ticket.handle, 'method': ticket.method}

    def staged_submit(self, handle, guard):
        """Read one original locally staged task; no send or ledger mutation."""
        import json
        from .publication_wire import TaskID, _task
        value, row = self.target(handle)
        return self._staged_submit(value, row, guard, check_conflict=True)

    def _staged_submit(self, value, row, guard, *, check_conflict):
        import json
        from .publication_wire import TaskID, _task
        handle = row['intent_handle']
        guard()
        if row['state'] not in {'SUBMIT_CLAIMED', 'UNKNOWN'} or row['submit_count'] != 1:
            fail('CURRENT_PUBLICATION_INVALID_TRANSITION')
        directory = self.legacy.anchor / 'current-publication-receipts'
        if not os.path.lexists(directory):
            return {'state': 'ORIGINAL_RECEIPT_NOT_FOUND'}
        path_check(directory, True)
        names = _bounded_names(directory)
        if (any(type(name) is not str
                or re.fullmatch('[0-9a-f]{64}\\.json', name) is None for name in names)):
            fail('CURRENT_PUBLICATION_RECEIPT_UNDETERMINED')
        matches = []
        expected_request = sha256(json.dumps({'media_id': row['reference']}, sort_keys=True,
            separators=(',', ':'), ensure_ascii=True).encode('ascii')).hexdigest()
        for name in names:
            guard()
            proof = read_file(directory / name, 128 * 1024)
            if type(proof) is not dict:
                fail('CURRENT_PUBLICATION_RECEIPT_UNDETERMINED')
            exact(proof, 'schema account_key binding_sha256 intent_handle method head_sequence '
                'head_sha256 request_sha256 reason error_code http_status response_sha256 result')
            if proof['intent_handle'] != handle or proof['method'] != 'freepublish.submit':
                continue
            if (proof['schema'] != 'CURRENT_PUBLICATION_RETURN_RECEIPT_V1'
                    or proof['account_key'] != self.legacy.key
                    or proof['binding_sha256'] != binding(self.policy.data)
                    or proof['request_sha256'] != expected_request
                    or type(proof['head_sequence']) is not int or not 1 <= proof['head_sequence'] <= 4096):
                fail('CURRENT_PUBLICATION_RECEIPT_UNDETERMINED')
            expected_name = digest({key: proof[key] for key in ('account_key', 'intent_handle', 'method',
                'head_sequence', 'head_sha256', 'request_sha256')}) + '.json'
            event = read_file(self.directory / ('event-' + str(proof['head_sequence']) + '.json'), MAX_LEDGER)
            old_row = event.get('value', {}).get('targets', {}).get(handle)
            if (name != expected_name or digest(event) != proof['head_sha256']
                    or type(old_row) is not dict or old_row.get('state') != 'SUBMIT_CLAIMED'
                    or {k: v for k, v in old_row.items() if k not in MUTABLE_TARGET_FIELDS}
                       != {k: v for k, v in row.items() if k not in MUTABLE_TARGET_FIELDS}
                    or old_row.get('submit_count') != 1):
                fail('CURRENT_PUBLICATION_RECEIPT_UNDETERMINED')
            result = proof['result']
            if (proof['reason'] != 'PARSED_SUCCESS' or proof['error_code'] is not None
                    or proof['http_status'] != 200 or type(result) is not dict
                    or type(result.get('task')) is not dict):
                continue
            try:
                task = TaskID(**result['task'])
                _task(task, 'PUBLISH_TASK', self.legacy.key, handle)
            except Exception:
                fail('CURRENT_PUBLICATION_RECEIPT_UNDETERMINED')
            if (task.source_method != 'freepublish.submit' or task.response_sha != proof['response_sha256']
                    or result.get('observed_task') != result['task']):
                fail('CURRENT_PUBLICATION_RECEIPT_UNDETERMINED')
            matches.append((task, digest(proof), proof))
        if len(matches) > 1:
            fail('CURRENT_PUBLICATION_RECEIPT_UNDETERMINED')
        if not matches:
            return {'state': 'ORIGINAL_RECEIPT_NOT_FOUND'}
        task, proof_sha, proof = matches[0]
        conflict = any(other['intent_handle'] != handle and type(other.get('task')) is dict
            and (other['task'].get('kind'), other['task'].get('digits')) == (task.kind, task.digits)
            for other in value['targets'].values())
        if check_conflict:
            try:
                conflict = self._legacy_task_conflict(task) or conflict
            except Exception:
                fail('CURRENT_PUBLICATION_RECEIPT_UNDETERMINED')
        guard()
        projection = {'error_code': proof['error_code'], 'reason': proof['reason'],
            'api_method': 'freepublish.submit', 'request_sha256': proof['request_sha256'],
            'response_sha256': proof['response_sha256'], 'http_status': proof['http_status']}
        return {'state': 'ORIGINAL_TASK_CONFLICT' if check_conflict and conflict else
            'ORIGINAL_TASK_STAGED_LOCAL_ONLY', 'receipt_sha256': proof_sha,
            'task': task, 'reply': projection}

    def _verify_recovery(self, previous, old, new):
        from dataclasses import asdict
        result = self._staged_submit(previous, old, self.runtime_guard, check_conflict=False)
        if (result['state'] != 'ORIGINAL_TASK_STAGED_LOCAL_ONLY'
                or result['receipt_sha256'] != new.get('recovered_receipt_sha256')
                or asdict(result['task']) != new.get('task')
                or result['reply'] != new.get('reply')
                or new.get('reason') != ('DUPLICATE_TASK_ID' if new.get('state') == 'TASK_CONFLICT' else None)):
            fail('CURRENT_PUBLICATION_RECEIPT_UNDETERMINED')

    def adopt_staged_submit(self, handle, authority, guard):
        """Adopt the original durable submit task; never sends or grants a new claim."""
        from dataclasses import asdict
        value, row = self.target(handle)
        self._authority(authority, guard, row['batch_source_sha'])
        if (row['binding_sha256'] != binding(self.policy.data)
                or {k: v for k, v in value['batches'][row['batch_source_sha']]['authority'].items()
                    if k not in {'observed_ms', 'native_observation_sha256', 'code_scope_sha256'}}
                   != {k: v for k, v in authority.evidence().items()
                    if k not in {'observed_ms', 'native_observation_sha256', 'code_scope_sha256'}}):
            fail('CURRENT_PUBLICATION_HUMAN_SCOPE_REQUIRED')
        if row.get('task') is not None:
            return row
        if row['state'] not in {'SUBMIT_CLAIMED', 'UNKNOWN'} or row['submit_count'] != 1:
            fail('CURRENT_PUBLICATION_INVALID_TRANSITION')
        result = self._staged_submit(value, row, guard, check_conflict=True)
        if result['state'] not in {'ORIGINAL_TASK_STAGED_LOCAL_ONLY', 'ORIGINAL_TASK_CONFLICT'}:
            return result
        self._authority(authority, guard, row['batch_source_sha'])
        conflict = result['state'] == 'ORIGINAL_TASK_CONFLICT'
        row.update(state='TASK_CONFLICT' if conflict else 'ACCEPTED',
            task=asdict(result['task']), reply=result['reply'],
            reason='DUPLICATE_TASK_ID' if conflict else None,
            recovered_receipt_sha256=result['receipt_sha256'])
        if conflict:
            task = result['task']
            for other in value['targets'].values():
                prior = other.get('task')
                if (other['intent_handle'] != handle and type(prior) is dict
                        and (prior.get('kind'), prior.get('digits')) == (task.kind, task.digits)
                        and other['state'] in {'ACCEPTED', 'PROCESSING', 'PUBLISHED_URLS_INCOMPLETE'}):
                    other.update(state='TASK_CONFLICT', reason='DUPLICATE_TASK_ID', query_pending=False)
        value['sequence'] += 1
        self.save(value)
        self._authority(authority, guard, row['batch_source_sha'])
        return row

    def record_reply(self, handle, method, request, response, token, guard, *, ticket):
        """Parse only the fixed request/response on its trusted host return stack.

        No MCP tool accepts these objects. The host must pass the actual sender
        response, not a model-supplied Reply or a persisted JSON projection.
        """
        from dataclasses import asdict
        if (type(ticket) is not _ReplyTicket or ticket.handle != handle or ticket.method != method
                or ticket.request != request):
            fail('CURRENT_PUBLICATION_RECEIPT_SCOPE_CHANGED')
        self.stage_reply(ticket, response, token)
        from .http_transport import HTTPRequest
        from .publication_wire import (ArticleID, DraftMediaID, TaskID, _task,
            article_url_supported, encode, parse)
        value, row = self.target(handle)
        guard()
        if type(request) is not HTTPRequest or method not in {'freepublish.submit', 'freepublish.get'}:
            fail('CURRENT_PUBLICATION_INVALID_TRANSITION')
        if method == 'freepublish.submit':
            if row['state'] != 'SUBMIT_CLAIMED' or row['task'] is not None:
                fail('CURRENT_PUBLICATION_INVALID_TRANSITION')
            task = None
            expected_request = encode(method, {'media_id': DraftMediaID(row['reference'],
                self.legacy.key, handle)}, token, account_key=self.legacy.key, intent_id=handle)
        else:
            if (row['state'] not in {'ACCEPTED', 'PROCESSING', 'PUBLISHED_URLS_INCOMPLETE'}
                    or row.get('query_pending') is not True or type(row['task']) is not dict):
                fail('CURRENT_PUBLICATION_INVALID_TRANSITION')
            try:
                task = TaskID(**row['task'])
                _task(task, 'PUBLISH_TASK', self.legacy.key, handle)
            except Exception:
                fail('CURRENT_PUBLICATION_ORIGINAL_TASK_REQUIRED')
            expected_request = encode(method, {'task_id': task}, token,
                account_key=self.legacy.key, intent_id=handle)
        if request != expected_request:
            fail('CURRENT_PUBLICATION_REQUEST_MISMATCH')
        reply = parse(method, response, token, account_key=self.legacy.key,
            intent_id=handle, expected_task=task, article_count=row['article_count'] if task else None)
        guard()
        projection = {'error_code': reply.error_code, 'reason': reply.reason,
            'api_method': method, 'request_sha256': sha256(request.body).hexdigest(),
            'response_sha256': reply.response_sha, 'http_status': reply.http_status}
        if method == 'freepublish.submit':
            if reply.result is not None:
                observed = reply.result.get('task')
                try:
                    _task(observed, 'PUBLISH_TASK', self.legacy.key, handle)
                except Exception:
                    fail('CURRENT_PUBLICATION_ORIGINAL_TASK_REQUIRED')
                if (observed.source_method != method or observed.response_sha != reply.response_sha
                        or reply.http_status != 200 or reply.reason != 'PARSED_SUCCESS'):
                    fail('CURRENT_PUBLICATION_ORIGINAL_TASK_REQUIRED')
                conflict = any(other['intent_handle'] != handle
                    and type(other.get('task')) is dict
                    and (other['task'].get('kind'), other['task'].get('digits'))
                        == (observed.kind, observed.digits)
                    for other in value['targets'].values())
                conflict_reason = 'DUPLICATE_TASK_ID' if conflict else None
                try:
                    if self._legacy_task_conflict(observed):
                        conflict_reason = 'DUPLICATE_TASK_ID'
                except Exception:
                    # Preserve the original returned task, but never treat it
                    # as uniquely attributed when legacy verification fails.
                    conflict_reason = 'TASK_UNIQUENESS_UNVERIFIED'
                row.update(state='TASK_CONFLICT' if conflict_reason else 'ACCEPTED',
                    task=asdict(observed), reply=projection)
                if conflict_reason:
                    row['reason'] = conflict_reason
                    for other in value['targets'].values():
                        prior = other.get('task')
                        if (other['intent_handle'] != handle and type(prior) is dict
                                and (prior.get('kind'), prior.get('digits')) == (observed.kind, observed.digits)
                                and other['state'] in {'ACCEPTED', 'PROCESSING', 'PUBLISHED_URLS_INCOMPLETE'}):
                            other.update(state='TASK_CONFLICT', reason='DUPLICATE_TASK_ID', query_pending=False)
            elif reply.error_code is not None:
                state = 'DENIED' if reply.error_code in PERMISSION_ERRORS else 'PLATFORM_REJECTED'
                row.update(state=state, reply=projection)
                if state == 'DENIED':
                    value['denial'] = {'intent_handle': handle, 'reply': projection}
            else:
                row.update(state='UNKNOWN', reply=projection)
        else:
            row['query_pending'] = False
            row['last_query'] = {'reason': reply.reason, 'error_code': reply.error_code,
                'http_status': reply.http_status, 'response_sha256': reply.response_sha}
            if reply.result is None:
                pass  # Keep the prior task and last observed publication status.
            else:
                result = reply.result
                status = result['platform_status']
                if type(status) is not int or not 0 <= status <= 6 or result['task'] != task:
                    fail('CURRENT_PUBLICATION_SUCCESS_EVIDENCE_REQUIRED')
                if row['state'] == 'PUBLISHED_URLS_INCOMPLETE' and status != 0:
                    fail('CURRENT_PUBLICATION_INVALID_TRANSITION')
                projection.update({key: val for key, val in result.items()
                    if key not in {'task', 'observed_task', 'article_id', 'article_urls'}})
                article = result.get('article_id')
                if article is not None:
                    if (type(article) is not ArticleID or article.account_key != self.legacy.key
                            or article.intent_id != handle):
                        fail('CURRENT_PUBLICATION_SUCCESS_EVIDENCE_REQUIRED')
                    projection['article_id'] = article.value
                urls = result['article_urls']
                if (type(urls) is not tuple or any(type(item) is not tuple or len(item) != 2
                        or type(item[0]) is not int or not article_url_supported(item[1]) for item in urls)):
                    fail('CURRENT_PUBLICATION_SUCCESS_EVIDENCE_REQUIRED')
                projection['article_urls'] = [list(item) for item in urls]
                if status == 0:
                    if result['url_evidence'] == 'COMPLETE':
                        if (article is None or len(urls) != row['article_count']
                                or [item[0] for item in urls] != list(range(1, row['article_count'] + 1))
                                or len({item[1] for item in urls}) != len(urls)):
                            fail('CURRENT_PUBLICATION_SUCCESS_EVIDENCE_REQUIRED')
                        state = 'PUBLISHED'
                    else:
                        state = 'PUBLISHED_URLS_INCOMPLETE'
                elif status == 1:
                    state = 'PROCESSING'
                else:
                    state = 'PLATFORM_FAILED'
                row.update(state=state, reply=projection)
        value['sequence'] += 1
        guard()
        self.save(value)
        stored = self.target(handle)[1]
        guard()
        return stored

    def guard_legacy(self, reference, claims=(), *, authority=None, guard=None, source_sha=None, successor_handle=None):
        from .draft_group_history_context import readonly_history_snapshot
        with readonly_history_snapshot(self.policy, self.legacy.path, timeout=10) as (db, history):
            if self.legacy.exists(db, history_locators=history):
                self.legacy._verify(db, history_locators=history)
                if db.execute('SELECT 1 FROM publication_intents WHERE account_key=? '
                        'AND draft_media_id=? LIMIT 1', (self.legacy.key, reference)).fetchone():
                    fail('CURRENT_PUBLICATION_LEGACY_CONFLICT')
                for kind, fingerprint in claims:
                    if db.execute('SELECT 1 FROM publication_claims WHERE account_key=? '
                            'AND kind=? AND fingerprint=? LIMIT 1',
                            (self.legacy.key, kind, fingerprint)).fetchone():
                        fail('CURRENT_PUBLICATION_LEGACY_CONTENT_CONFLICT')
            # Validate the old group journal, but do not turn a historical ADD
            # UNKNOWN into a prerequisite for an independently observed draft.
            # Actual concurrent writers share the stable account writer lock.
            from .draft_group_store import _account_writer_states
            opened = not db.in_transaction
            if opened:
                db.execute('BEGIN')
            try:
                _account_writer_states(db, history_locators=history)
            finally:
                if opened:
                    db.rollback()
        if authority is None:
            # Every non-current/old caller keeps the original strict route.
            from .draft_revision_guard import guard_claims, policy_binding
            guard_claims(self.policy, policy_binding(self.policy, 'OPERATOR_ATTESTED'),
                [('DRAFT_REF', digest(reference))])
        else:
            self._authority(authority, guard, source_sha)
            if successor_handle is None:
                from .current_publication_revision_exclusion import exclude_reference
                exclude_reference(self.policy, authority, guard, source_sha, reference)
            else:
                value,child=self.target(successor_handle)
                original=child.get('revision_successor_of')
                link=value.get('revision_successors',{}).get(original)
                reservation=value.get('revision_reservations',{}).get(original)
                if (type(link) is not dict or type(reservation) is not dict
                        or link.get('successor_handle')!=successor_handle or child['reference']!=reference
                        or child['batch_source_sha']!=source_sha):
                    fail('CURRENT_REVISION_SUCCESSOR_CORRUPT')
                self._verify_revision_successor(original,value['targets'][original],reservation,link)
                from .current_publication_revision_exclusion import exclude_completed_reference
                exclude_completed_reference(self.policy,authority,guard,source_sha,reference,reservation['case_id'])


def guard_legacy_dispatch(policy, registry, reference, claims, *, guard=None):
    """Legacy dispatcher calls this under the same stable account lock."""
    store = Store(policy, registry, guard=guard)
    from .current_publication_continuation import guard_external_held
    guard_external_held(store,reference=reference,claims=claims)
    if os.path.lexists(store.enrollment_dir):
        path_check(store.enrollment_dir, True)
    present = [os.path.lexists(p) for p in (store.directory, store.path, store.pin, store.enrollment)]
    if any(present) and not all(present):
        fail('CURRENT_PUBLICATION_HISTORY_MISSING')
    if not any(present):
        return
    wanted = set(map(tuple, claims))
    for row in store.read()['targets'].values():
        if (row['reference'] == reference
                or wanted.intersection(map(tuple, row.get('content_claims', ())))):
            fail('PUBLICATION_EXISTING_DRAFT_INTENT_CONFLICT')


def guard_legacy_task(policy, registry, task, *, guard=None):
    """Old route: compare a real returned task while holding same account lock.

    On conflict/unverified history the caller must preserve its original
    platform receipt and HOLD, never resend or attribute it to another draft.
    """
    from .publication_wire import TaskID, _task
    store = Store(policy, registry, guard=guard)
    if type(task) is not TaskID:
        fail('CURRENT_PUBLICATION_ORIGINAL_TASK_REQUIRED')
    try:
        _task(task, 'PUBLISH_TASK', store.legacy.key, task.intent_id)
    except Exception:
        fail('CURRENT_PUBLICATION_ORIGINAL_TASK_REQUIRED')
    from .current_publication_continuation import guard_external_held
    guard_external_held(store,task=task)
    if os.path.lexists(store.enrollment_dir):
        path_check(store.enrollment_dir, True)
    present = [os.path.lexists(p) for p in (store.directory, store.path, store.pin, store.enrollment)]
    if any(present) and not all(present):
        fail('CURRENT_PUBLICATION_HISTORY_MISSING')
    if not any(present):
        return
    for row in store.read()['targets'].values():
        other = row.get('task')
        if type(other) is dict and (other.get('kind'), other.get('digits')) == (task.kind, task.digits):
            fail('PUBLICATION_EXISTING_DRAFT_TASK_CONFLICT')


def public_target(row):
    reply = row.get('reply') or {}
    reason = row.get('reason')
    if reason not in {'DUPLICATE_TASK_ID', 'TASK_UNIQUENESS_UNVERIFIED', 'SUBMIT_RESULT_UNDETERMINED'}:
        reason = None
    return {'intent_handle': row['intent_handle'], 'state': row['state'],
        'article_count': row['article_count'], 'titles': row['titles'],
        'submit_count': row['submit_count'], 'queries': row.get('queries', 0),
        'platform_status': reply.get('platform_status'),
        'error_code': reply.get('error_code'),
        'article_id': reply.get('article_id'),
        'article_urls': reply.get('article_urls', []),
        'url_evidence': reply.get('url_evidence'),
        'last_query': row.get('last_query'),
        'reason': reason,
        'quality_source': row.get('quality_source', 'HUMAN_ACCEPTED_CURRENT_DRAFTS'),
        'route': 'FREEPUBLISH', 'audience': 'NO_PUSH'}
