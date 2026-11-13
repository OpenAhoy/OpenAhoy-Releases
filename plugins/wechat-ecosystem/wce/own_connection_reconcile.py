"""One claimed, Settings-reviewed read recovery for an original personal cover."""
from hashlib import sha256
import math
import os
import re
import threading
import time
from urllib.parse import urlencode

from .contracts import WCEError
from .http_transport import HTTPRequest, HTTPResponse
from .own_auth import READ_APIS
from .own_bootstrap_security import private_read, path_check, decode
from .own_connection_enrollment import exclusive
from .own_workflow import encoded
from .own_png import ORIGIN, MAX_INPUT
from .own_reconcile import SOURCES, original_fingerprint
from .own_cover_match import match_cover
from .service import digest
from . import own_cover_authority as auth
from . import upload_wire as upload
from .own_completed_cover_history import completed_record_identity


def proof_name(row, grant):
    return 'reconciliation-' + row['id'] + '-' + grant['id'] + '.json'


def validate_proof(w, db, p, row, intent, result, proof):
    """Historical validation never renews an expired grant or consumes it again."""
    try:
        keys = {'schema', 'authorization_source', 'grant_id', 'grant_sha256', 'claimed_sha256',
            'completed_at', 'read_counts', 'observation', 'original_target_digest', 'provenance'}
        if type(proof) is not dict or set(proof) != keys or type(proof['schema']) is not int or proof['schema'] != 3:
            raise ValueError()
        if proof['authorization_source'] != auth.AUTHORITY or result['completion_origin'] != ORIGIN:
            raise ValueError()
        grant_path = w.db.path.parent / auth.filename(proof['grant_id'])
        raw, grant_pin = private_read(grant_path)
        grant = auth.validate_grant(decode(raw))
        if (grant['id'] != proof['grant_id']
                or sha256(raw).hexdigest() != proof['grant_sha256'] or (encoded(grant)+'\n').encode() != raw
                or grant['binding'] != p.binding()
                or result['reconciliation_proof'] != proof_name(row, grant)):
            raise ValueError()
        proof_path = w.db.path.parent / result['reconciliation_proof']
        proof_raw, proof_pin = private_read(proof_path)
        if (proof_raw != (encoded(proof)+'\n').encode()
                or sha256(proof_raw).hexdigest() != result['reconciliation_proof_sha256']):
            raise ValueError()
        with completed_record_identity(w, db, p, row, intent, result, proof, grant):
            original = auth.target(w, db, p, row, intent)
            if encoded(grant['target']) != encoded(original) or proof['original_target_digest'] != digest(original):
                raise ValueError()
            claimed_path = w.db.path.parent / auth.filename(grant['id'], True)
            claimed_raw, claimed_pin = private_read(claimed_path)
            claimed = decode(claimed_raw)
            expected = {'schema': 1, 'authority': auth.AUTHORITY, 'grant_id': grant['id'],
                'grant_sha256': proof['grant_sha256'], 'activated_at': claimed.get('activated_at'),
                'maximum_execution_seconds': auth.MAX_SECONDS}
            if ((encoded(claimed)+'\n').encode() != claimed_raw or encoded(claimed) != encoded(expected)
                    or sha256(claimed_raw).hexdigest() != proof['claimed_sha256']):
                raise ValueError()
            start, end = claimed['activated_at'], proof['completed_at']
            if (type(start) not in (float, int) or type(end) not in (float, int)
                    or not math.isfinite(start) or not math.isfinite(end)
                    or not grant['confirmed_at'] <= start <= end < grant['expires_at']
                    or end - start >= auth.MAX_SECONDS or row['completed'] != end):
                raise ValueError()
            counts = proof['read_counts']
            if (type(counts) is not dict or set(counts) != {'list', 'image'}
                    or any(type(v) is not int for v in counts.values())
                    or not 2 <= counts['list'] <= auth.BUDGET['list']
                    or not 2 <= counts['image'] <= auth.BUDGET['image']):
                raise ValueError()
            observation = proof['observation']
            if (type(observation) is not dict or set(observation) != {'result', 'update_time',
                    'complete_list_digest', 'material_count', 'raster', 'remote_input_sha256',
                    'remote_input_size', 'unique_matches', 'final_remote_raw_equal', 'sources'}
                    or observation['result'] != {k: result[k] for k in ('media_id', 'url')}
                    or type(observation['unique_matches']) is not int or observation['unique_matches'] != 1
                    or observation['final_remote_raw_equal'] is not True
                    or observation['sources'] != {k: {'url': v[0], 'sha256': v[1]} for k, v in SOURCES.items()}
                    or type(observation['material_count']) is not int or not 1 <= observation['material_count'] <= 10000
                    or type(observation['update_time']) is not int or observation['update_time'] < 0
                    or type(observation['remote_input_size']) is not int or not 0 < observation['remote_input_size'] <= MAX_INPUT):
                raise ValueError()
            for key in ('remote_input_sha256', 'complete_list_digest'):
                if type(observation[key]) is not str or re.fullmatch('[a-f0-9]{64}', observation[key]) is None:
                    raise ValueError()
            expected_list = 2 * math.ceil(observation['material_count'] / 20)
            if counts['list'] != expected_list:
                raise ValueError()
            _, data = w._asset(db, p.binding(), intent['asset']['asset_ref'], 'cover')
            if encoded(observation['raster']) != encoded(original_fingerprint(w, data)):
                raise ValueError()
            expected_provenance = ('SYNTHETIC_OWN_' if p.source_kind == 'SYNTHETIC_SETUP' else 'OWN_OFFICIAL_') + 'PIXEL_READ_MATCH'
            if proof['provenance'] != expected_provenance:
                raise ValueError()
            for path, expected_raw, expected_pin in ((grant_path, raw, grant_pin),
                    (claimed_path, claimed_raw, claimed_pin), (proof_path, proof_raw, proof_pin)):
                if private_read(path) != (expected_raw, expected_pin):
                    raise ValueError()
    except Exception:
        raise WCEError('OWN_STATE_CORRUPT') from None


class ReadAttempt:
    def __init__(self, workflow, profile, grant, checksum, claimed, row, intent, original):
        self.w, self.p = workflow, profile
        self.grant, self.checksum, self.claimed = grant, checksum, claimed
        self.row, self.intent, self.original = row, intent, original
        self.started = time.monotonic()
        self.wall_started = workflow.clock()
        self.deadline = min(workflow.execution_deadline, self.started + auth.MAX_SECONDS,
                            self.started + auth.MAX_SECONDS - (self.wall_started - claimed['activated_at']))
        self.stop = threading.Event()
        self.counter_lock = threading.Lock()
        self.counts = {'list': 0, 'image': 0}
        self.diagnostics = {}
        self.lease = workflow.active_lease
        root = self.w.db.path.parent
        self.grant_raw, self.grant_pin = private_read(root / auth.filename(grant['id']))
        self.claimed_raw, self.claimed_pin = private_read(root / auth.filename(grant['id'], True))
        if (sha256(self.grant_raw).hexdigest() != checksum
                or decode(self.grant_raw) != grant or decode(self.claimed_raw) != claimed):
            raise WCEError('COVER_READ_AUTHORITY_CHANGED')

    def current(self):
        self.w.policy.check()
        elapsed = time.monotonic() - self.started
        wall_elapsed = self.w.clock() - self.wall_started
        if (self.stop.is_set() or elapsed < 0 or wall_elapsed < 0 or abs(elapsed-wall_elapsed) >= 5
                or time.monotonic() >= self.deadline
                or not self.grant['confirmed_at'] <= self.w.clock() < self.grant['expires_at']
                or self.w.clock() - self.claimed['activated_at'] >= auth.MAX_SECONDS
                or self.w.policy.delegation() != self.grant['policy']
                or self.grant['binding'] != self.p.binding()
                or self.w.active_lease is not self.lease):
            raise WCEError('COVER_READ_EXPIRED_OR_CHANGED')
        root = self.w.db.path.parent
        for name, raw, pin in ((auth.filename(self.grant['id']), self.grant_raw, self.grant_pin),
                (auth.filename(self.grant['id'], True), self.claimed_raw, self.claimed_pin)):
            if private_read(root/name) != (raw, pin):
                raise WCEError('COVER_READ_AUTHORITY_CHANGED')
        if (self.grant['root_pin'] != list(path_check(root, True))
                or self.grant['database_pin'] != list(path_check(self.w.db.path)[:2])):
            raise WCEError('COVER_READ_AUTHORITY_CHANGED')

    def guard(self):
        self.current()
        for action in READ_APIS:
            self.w._network(self.p, self.lease, action, read_attempt=True)
        with _history_transaction(self.w.db) as (db, history_locators):
            row, _, original = auth.unknown(self.w, db, self.p, self.row['request_key'], history_locators=history_locators)
            if encoded(row) != encoded(self.row) or encoded(original) != encoded(self.grant['target']):
                raise WCEError('COVER_READ_SNAPSHOT_CHANGED')

    def report(self, facts):
        from .own_run_outcome import safe_counts
        self.diagnostics = safe_counts(facts)

    def failed(self, error):
        self.stop.set()

    def read(self, action, payload):
        return self.reserve(action, payload)()

    def reserve(self, action, payload):
        self.guard()
        if action not in READ_APIS:
            raise WCEError('OWN_ACCESS_DENIED')
        kind = 'list' if action == READ_APIS[0] else 'image'
        # Consume before pool.submit, including work cancelled before dispatch.
        with self.counter_lock:
            self.current()
            if self.counts[kind] >= auth.BUDGET[kind] or sum(self.counts.values()) >= auth.BUDGET['total']:
                raise WCEError('COVER_READ_BUDGET_EXHAUSTED')
            self.counts[kind] += 1
        consumed = False
        def invoke():
            nonlocal consumed
            with self.counter_lock:
                if consumed:
                    raise WCEError('COVER_READ_BUDGET_EXHAUSTED')
                consumed = True
            return self._read_reserved(action, payload, kind)
        return invoke

    def _read_reserved(self, action, payload, kind):
        self.guard()
        endpoint = '/cgi-bin/material/' + ('batchget_material' if kind == 'list' else 'get_material')
        request = HTTPRequest('POST', endpoint + '?' + urlencode({'access_token': upload.secret_value(self.lease.token)}),
            {'Content-Type': 'application/json; charset=utf-8'}, encoded(payload).encode())
        response = self.w._send(self.p, self.lease, request, action, read_attempt=True)
        self.guard()
        if (type(response) is not HTTPResponse or not 200 <= response.status < 300
                or type(response.body) is not bytes or not 0 < len(response.body) <= MAX_INPUT
                or upload.contains_secret(response.body, self.lease.token)):
            raise WCEError('OWN_RECONCILE_READ_UNDETERMINED')
        return response.body

    def run(self):
        w, p, grant = self.w, self.p, self.grant
        synthetic = p.source_kind == 'SYNTHETIC_SETUP'
        observation = match_cover(self.read, self.guard, self.report, self.failed,
            self.stop, self.row, self.intent, self.original, True, synthetic, self.lease.token,
            prepare_read=self.reserve)
        observation.update(unique_matches=1, final_remote_raw_equal=True,
            sources={k: {'url': v[0], 'sha256': v[1]} for k, v in SOURCES.items()})
        self.guard()
        completed = w.clock()
        proof = {'schema': 3, 'authorization_source': auth.AUTHORITY, 'grant_id': grant['id'],
            'grant_sha256': self.checksum, 'claimed_sha256': sha256(self.claimed_raw).hexdigest(),
            'original_target_digest': digest(grant['target']), 'completed_at': completed,
            'read_counts': dict(self.counts), 'observation': observation,
            'provenance': ('SYNTHETIC_OWN_' if synthetic else 'OWN_OFFICIAL_') + 'PIXEL_READ_MATCH'}
        if upload.contains_secret(proof, self.lease.token):
            raise WCEError('OWN_RECONCILE_READ_UNDETERMINED')
        name = proof_name(self.row, grant)
        path = w.db.path.parent / name
        exclusive(path, proof, grant['root_pin'])
        raw, _ = private_read(path)
        if raw != (encoded(proof)+'\n').encode():
            raise WCEError('COVER_READ_PROOF_CHANGED')
        self.guard()
        result = observation['result'] | {'completion_origin': ORIGIN,
            'reconciliation_proof': name, 'reconciliation_proof_sha256': sha256(raw).hexdigest()}
        with _history_transaction(w.db, write=True) as (db, history_locators):
            w._resource(db, p, history_locators=history_locators)
            current, intent, original = auth.unknown(w, db, p, self.row['request_key'], history_locators=history_locators)
            if encoded(current) != encoded(self.row) or encoded(original) != encoded(grant['target']):
                raise WCEError('COVER_READ_SNAPSHOT_CHANGED')
            m, _ = w._bundle(db, p, intent['selector']['bundle_id'], intent['selector']['version'])
            w._owned_lock(db, p, m, current['id'])
            for action in READ_APIS: w._network(p, self.lease, action, read_attempt=True)
            changed = db.execute("UPDATE own_steps SET state='SUCCEEDED',result=?,result_digest=?,completed=? "
                "WHERE id=? AND owner=? AND state='RESULT_UNKNOWN' AND intent_digest=? AND approval_digest=?",
                (encoded(result), digest(result), completed, current['id'], current['owner'],
                 current['intent_digest'], current['approval_digest'])).rowcount
            if changed != 1: raise WCEError('COVER_READ_SNAPSHOT_CHANGED')
            w._release_lock(db, p, m, current['id'])
            w._step(db, p, db.execute('SELECT * FROM own_steps WHERE id=?', (current['id'],)).fetchone(), history_locators=history_locators)
            for action in READ_APIS: w._network(p, self.lease, action, read_attempt=True)
        # A failure after commit never rolls back the durable recovered state.
        self.current()
        return {'state': 'EXISTING_COVER_READ_MATCHED', 'original_write_response': 'RESULT_UNKNOWN',
            'request_key': current['request_key'], 'attempt_id': current['id'],
            'proof_sha256': sha256(raw).hexdigest(), 'result': observation['result'],
            'read_counts': dict(self.counts)}


from .draft_group_history_context import history_transaction as _history_transaction
