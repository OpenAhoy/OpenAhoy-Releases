"""Conservative publication quota accounting, transaction-level integration proposal.

This module has NO network, token access, grant, or independent transaction.
The caller must hold PublicationStore.dispatch_lock and invoke these SQL helpers
inside store.event/commit_event. No live observation provider is implemented.
"""
from dataclasses import dataclass
from hashlib import sha256
import json
import re
import sqlite3

DRAFT = '/cgi-bin/draft/get'
SUBMIT = '/cgi-bin/freepublish/submit'
POLL = '/cgi-bin/freepublish/get'
PATHS = frozenset((DRAFT, SUBMIT, POLL))
STEPS = {'INITIAL': DRAFT, 'FINAL': DRAFT, 'SUBMIT': SUBMIT, 'POLL': POLL}

# Additive schema for the unreleased composite schema7; it must be incorporated
# into exact schema fingerprint, migration and event/recovery validation.
SCHEMA = '''
CREATE TABLE publication_quota_observations (
 account_key TEXT NOT NULL, observation_sha TEXT NOT NULL,
 binding_sha TEXT NOT NULL, api_path TEXT NOT NULL,
 remaining INTEGER NOT NULL CHECK(remaining >= 0),
 call_count INTEGER NOT NULL CHECK(call_count > 0),
 refresh_ms INTEGER NOT NULL CHECK(refresh_ms > 0),
 observed_wall_ms INTEGER NOT NULL, observed_mono_ms INTEGER NOT NULL,
 deadline_wall_ms INTEGER NOT NULL, deadline_mono_ms INTEGER NOT NULL,
 boot_id TEXT NOT NULL, source_sha TEXT NOT NULL,
 PRIMARY KEY(account_key, observation_sha));
CREATE TABLE publication_quota_claims (
 account_key TEXT NOT NULL, candidate_id TEXT NOT NULL, intent_id TEXT,
 step TEXT NOT NULL CHECK(step IN ('INITIAL','FINAL','SUBMIT','POLL')),
 ordinal INTEGER NOT NULL CHECK(ordinal >= 1), attempt INTEGER NOT NULL CHECK(attempt >= 1), api_path TEXT NOT NULL,
 observation_sha TEXT NOT NULL, binding_sha TEXT NOT NULL,
 created_wall_ms INTEGER NOT NULL, created_mono_ms INTEGER NOT NULL,
 boot_id TEXT NOT NULL,
 PRIMARY KEY(account_key,candidate_id,step,ordinal),
 FOREIGN KEY(account_key,candidate_id) REFERENCES publication_candidates(account_key,artifact_id),
 FOREIGN KEY(account_key,intent_id) REFERENCES publication_intents(account_key,intent_id),
 FOREIGN KEY(account_key,observation_sha) REFERENCES publication_quota_observations(account_key,observation_sha),
 CHECK((step='POLL' AND ordinal BETWEEN 1 AND 5 AND intent_id IS NOT NULL)
    OR (step='SUBMIT' AND ordinal=1 AND intent_id IS NOT NULL)
    OR (step IN ('INITIAL','FINAL') AND ordinal=attempt AND intent_id IS NULL)));
CREATE INDEX publication_quota_by_path ON publication_quota_claims(account_key,api_path);
CREATE TABLE publication_quota_reservations (
 account_key TEXT NOT NULL, candidate_id TEXT NOT NULL, intent_id TEXT NOT NULL,
 attempt INTEGER NOT NULL CHECK(attempt >= 1), api_path TEXT NOT NULL CHECK(api_path='/cgi-bin/freepublish/submit'),
 observation_sha TEXT NOT NULL, binding_sha TEXT NOT NULL,
 created_wall_ms INTEGER NOT NULL, created_mono_ms INTEGER NOT NULL, boot_id TEXT NOT NULL,
 PRIMARY KEY(account_key,candidate_id,attempt),
 FOREIGN KEY(account_key,candidate_id) REFERENCES publication_candidates(account_key,artifact_id),
 FOREIGN KEY(account_key,intent_id) REFERENCES publication_intents(account_key,intent_id),
 FOREIGN KEY(account_key,observation_sha) REFERENCES publication_quota_observations(account_key,observation_sha));
CREATE TRIGGER publication_quota_reservation_no_update BEFORE UPDATE ON publication_quota_reservations
BEGIN SELECT RAISE(ABORT, 'quota reservations immutable'); END;
CREATE TRIGGER publication_quota_reservation_no_delete BEFORE DELETE ON publication_quota_reservations
BEGIN SELECT RAISE(ABORT, 'quota reservations immutable'); END;
CREATE TRIGGER publication_quota_claim_no_update BEFORE UPDATE ON publication_quota_claims
BEGIN SELECT RAISE(ABORT, 'quota claims immutable'); END;
CREATE TRIGGER publication_quota_claim_no_delete BEFORE DELETE ON publication_quota_claims
BEGIN SELECT RAISE(ABORT, 'quota claims immutable'); END;
CREATE TRIGGER publication_quota_observation_no_update BEFORE UPDATE ON publication_quota_observations
BEGIN SELECT RAISE(ABORT, 'quota observations immutable'); END;
CREATE TRIGGER publication_quota_observation_no_delete BEFORE DELETE ON publication_quota_observations
BEGIN SELECT RAISE(ABORT, 'quota observations immutable'); END;
'''

class UnavailableProvider:
    """Default real runtime. No access token or network will be requested."""

class TrustedHostProvider:
    """Reserved host-only interface; intentionally unsupported until verified.

    Future implementation must fetch the fixed paths using account-bound READ
    grant, protect its own bounded quota, and bind receipt and shared ledger.
    It must never accept externally supplied observation or verifier over MCP.
    """

class SyntheticProvider:
    """In-process fake only; must never be exposed to real MCP callers."""
    def __init__(self):
        self._issued = set()
        self._seq = 0

    def observe(self, account_key, binding_sha, api_path, wall_ms, mono_ms):
        self._seq += 1
        source = _fingerprint({'synthetic': True, 'seq': self._seq,
                               'path': api_path, 'account_key': account_key})
        result = Observation(account_key, binding_sha, api_path, 10000, 10000,
            60000, wall_ms, mono_ms, 'synthetic-boot', wall_ms+60000,
            mono_ms+60000, source)
        self._issued.add(result)
        return result

    def verify(self, observation):
        return observation in self._issued

def require_provider(provider, *, synthetic_context=False):
    if type(provider) is SyntheticProvider and synthetic_context is True:
        return
    _hold('QUOTA_TRUSTED_SOURCE_UNAVAILABLE')

class QuotaHold(Exception):
    pass


def _hold(code):
    raise QuotaHold(code)


def _id(value):
    if type(value) is not str or not re.fullmatch(r'[A-Za-z0-9._:-]{1,160}', value):
        _hold('QUOTA_ID_INVALID')
    return value


def _sha(value):
    if type(value) is not str or not re.fullmatch(r'[0-9a-f]{64}', value):
        _hold('QUOTA_SOURCE_INVALID')
    return value


def _integer(value, *, minimum=0, maximum=2**31-1):
    if type(value) is not int or not minimum <= value <= maximum:
        _hold('QUOTA_SOURCE_INVALID')
    return value


def _clock(wall_ms, mono_ms, boot_id):
    _integer(wall_ms, minimum=1, maximum=2**63-1)
    _integer(mono_ms, minimum=0, maximum=2**63-1)
    _id(boot_id)


def _fingerprint(row):
    return sha256(json.dumps(row, sort_keys=True, separators=(',', ':'), ensure_ascii=True).encode()).hexdigest()


@dataclass(frozen=True)
class Observation:
    """Only the trusted host adapter may create and submit this projection.

    Runtime trust is enforced by independently supplied `verify_source`; it
    must validate the actual trusted receipt and authorization, not a field
    supplied over MCP. Until that adapter exists, do not configure a verifier.
    """
    account_key: str
    binding_sha: str
    api_path: str
    remaining: int
    call_count: int
    refresh_ms: int
    observed_wall_ms: int
    observed_mono_ms: int
    boot_id: str
    authority_deadline_wall_ms: int
    authority_deadline_mono_ms: int
    source_sha: str


def _validated(observation, verify_source, wall_ms, mono_ms, boot_id):
    _clock(wall_ms, mono_ms, boot_id)
    if type(observation) is not Observation or not callable(verify_source):
        _hold('QUOTA_TRUSTED_SOURCE_UNAVAILABLE')
    o = observation
    _id(o.account_key); _sha(o.binding_sha); _sha(o.source_sha); _id(o.boot_id)
    if o.api_path not in PATHS:
        _hold('QUOTA_PATH_UNSUPPORTED')
    _integer(o.remaining)
    _integer(o.call_count, minimum=1)
    _integer(o.refresh_ms, minimum=1, maximum=2**31-1)
    _clock(o.observed_wall_ms, o.observed_mono_ms, o.boot_id)
    _integer(o.authority_deadline_wall_ms, minimum=1, maximum=2**63-1)
    _integer(o.authority_deadline_mono_ms, minimum=1, maximum=2**63-1)
    if o.boot_id != boot_id:
        _hold('QUOTA_BOOT_CHANGED')
    dw, dm = wall_ms-o.observed_wall_ms, mono_ms-o.observed_mono_ms
    if dw < 0 or dm < 0 or abs(dw-dm) >= 5000:
        _hold('QUOTA_CLOCK_CHANGED')
    ttl = min(60000, o.refresh_ms)
    deadline_wall = min(o.observed_wall_ms+ttl, o.authority_deadline_wall_ms)
    deadline_mono = min(o.observed_mono_ms+ttl, o.authority_deadline_mono_ms)
    if wall_ms >= deadline_wall or mono_ms >= deadline_mono:
        _hold('QUOTA_OBSERVATION_EXPIRED')
    try:
        verified = verify_source(o)
    except Exception:
        _hold('QUOTA_TRUSTED_SOURCE_UNAVAILABLE')
    if verified is not True:
        _hold('QUOTA_TRUSTED_SOURCE_UNAVAILABLE')
    projection = dict(account_key=o.account_key, binding_sha=o.binding_sha,
        api_path=o.api_path, remaining=o.remaining, call_count=o.call_count,
        refresh_ms=o.refresh_ms, observed_wall_ms=o.observed_wall_ms,
        observed_mono_ms=o.observed_mono_ms, deadline_wall_ms=deadline_wall,
        deadline_mono_ms=deadline_mono, boot_id=o.boot_id, source_sha=o.source_sha)
    return projection, _fingerprint(projection)


def record_observation(db, observation, *, verify_source=None, wall_ms, mono_ms, boot_id):
    """Call only inside the event transaction; caller anchors its hash."""
    if not db.in_transaction:
        _hold('QUOTA_TRANSACTION_REQUIRED')
    row, value = _validated(observation, verify_source, wall_ms, mono_ms, boot_id)
    keys = ('account_key','binding_sha','api_path','remaining','call_count','refresh_ms',
            'observed_wall_ms','observed_mono_ms','deadline_wall_ms','deadline_mono_ms','boot_id','source_sha')
    db.execute('INSERT INTO publication_quota_observations (observation_sha,'+','.join(keys)+') VALUES ('+
               ','.join('?' for _ in range(len(keys)+1))+')', (value, *(row[k] for k in keys)))
    return value


def _claim(db, *, account_key, binding_sha, candidate_id, intent_id, step, ordinal, attempt,
          observation_sha, wall_ms, mono_ms, boot_id, shared_accounting_verified=False,
          reserve_check=False, joint=False):
    """Spend before HTTP. Invoke in same anchored transaction as corresponding claim.

    The True shared-accounting signal must come from a host-controlled account
    boundary, never an MCP argument. No such production signal is provided here.
    """
    if not db.in_transaction:
        _hold('QUOTA_TRANSACTION_REQUIRED')
    if shared_accounting_verified is not True:
        _hold('QUOTA_SHARED_ACCOUNTING_UNAVAILABLE')
    _clock(wall_ms, mono_ms, boot_id)
    _id(account_key); _sha(binding_sha); _id(candidate_id); _sha(observation_sha)
    if step not in STEPS or type(ordinal) is not int or type(attempt) is not int or attempt < 1:
        _hold('QUOTA_STEP_INVALID')
    if step == 'FINAL' and not joint: _hold('QUOTA_JOINT_RESERVATION_REQUIRED')
    if step in ('INITIAL','FINAL'):
        if intent_id is not None or ordinal != attempt: _hold('QUOTA_STEP_INVALID')
    elif step == 'SUBMIT':
        _id(intent_id)
        if ordinal != 1: _hold('QUOTA_STEP_INVALID')
    else:
        _id(intent_id)
        if not 1 <= ordinal <= 5: _hold('QUOTA_STEP_INVALID')
    rows = db.execute('SELECT account_key,binding_sha,api_path,remaining,call_count,refresh_ms,observed_wall_ms,observed_mono_ms,deadline_wall_ms,deadline_mono_ms,boot_id,source_sha FROM publication_quota_observations WHERE account_key=? AND observation_sha=?', (account_key,observation_sha)).fetchall()
    if len(rows) != 1: _hold('QUOTA_OBSERVATION_MISSING')
    keys = ('account_key','binding_sha','api_path','remaining','call_count','refresh_ms',
            'observed_wall_ms','observed_mono_ms','deadline_wall_ms','deadline_mono_ms','boot_id','source_sha')
    obs = dict(zip(keys,rows[0]))
    if (_fingerprint(obs) != observation_sha or obs['binding_sha'] != binding_sha
            or obs['api_path'] != STEPS[step] or obs['boot_id'] != boot_id):
        _hold('QUOTA_OBSERVATION_MISMATCH')
    dw, dm = wall_ms-obs['observed_wall_ms'], mono_ms-obs['observed_mono_ms']
    if dw < 0 or dm < 0 or abs(dw-dm) >= 5000: _hold('QUOTA_CLOCK_CHANGED')
    if wall_ms >= obs['deadline_wall_ms'] or mono_ms >= obs['deadline_mono_ms']:
        _hold('QUOTA_OBSERVATION_EXPIRED')
    candidate = db.execute('SELECT 1 FROM publication_candidates WHERE account_key=? AND artifact_id=?', (account_key,candidate_id)).fetchone()
    if candidate is None: _hold('QUOTA_CANDIDATE_MISSING')
    last_initial = db.execute("SELECT COALESCE(MAX(attempt),0) FROM publication_quota_claims WHERE account_key=? AND candidate_id=? AND step='INITIAL'", (account_key,candidate_id)).fetchone()[0]
    prior_submit = db.execute("SELECT attempt FROM publication_quota_claims WHERE account_key=? AND candidate_id=? AND step='SUBMIT'", (account_key,candidate_id)).fetchone()
    if step == 'INITIAL':
        if prior_submit is not None: _hold('QUOTA_SUBMIT_SPENT')
        if attempt != last_initial+1: _hold('QUOTA_ATTEMPT_SEQUENCE_INVALID')
    elif step in ('FINAL','SUBMIT'):
        if step == 'SUBMIT' and prior_submit is not None: _hold('QUOTA_SUBMIT_SPENT')
        if attempt != last_initial or last_initial == 0: _hold('QUOTA_INITIAL_REQUIRED')
    elif step == 'POLL':
        if prior_submit is None or prior_submit[0] != attempt: _hold('QUOTA_SUBMIT_REQUIRED')
    if step in ('SUBMIT','POLL'):
        intent = db.execute('SELECT artifact_id,submit_count,submit_ms,query_used FROM publication_intents WHERE account_key=? AND intent_id=?', (account_key,intent_id)).fetchone()
        if intent is None or intent[0] != candidate_id: _hold('QUOTA_INTENT_MISMATCH')
        if not db.execute("SELECT 1 FROM publication_quota_claims WHERE account_key=? AND candidate_id=? AND step='FINAL' AND attempt=?", (account_key,candidate_id,attempt)).fetchone():
            _hold('QUOTA_FINAL_REQUIRED')
        if step == 'SUBMIT' and intent[1] != 0: _hold('QUOTA_SUBMIT_SPENT')
        if step == 'SUBMIT' and not reserve_check:
            reservation = db.execute('SELECT intent_id,observation_sha,binding_sha,boot_id FROM publication_quota_reservations WHERE account_key=? AND candidate_id=? AND attempt=?', (account_key,candidate_id,attempt)).fetchone()
            if reservation is None or tuple(reservation) != (intent_id,observation_sha,binding_sha,boot_id):
                _hold('QUOTA_SUBMIT_RESERVATION_REQUIRED')
        if step == 'POLL':
            submitted = db.execute("SELECT 1 FROM publication_quota_claims WHERE account_key=? AND candidate_id=? AND intent_id=? AND step='SUBMIT' AND attempt=?", (account_key,candidate_id,intent_id,attempt)).fetchone()
            if not submitted: _hold('QUOTA_SUBMIT_REQUIRED')
            if intent[1] != 1 or intent[2] is None or not 0 <= wall_ms-intent[2] < 60000:
                _hold('QUOTA_POLL_WINDOW_EXPIRED')
            if intent[3] != ordinal-1: _hold('QUOTA_POLL_SEQUENCE_INVALID')
    # Conservatively subtract ALL existing local claims, including unknown and
    # pre-observation calls. No evidence that WeChat has accounted for them is
    # currently available. This intentionally may exhaust quota prematurely.
    spent = db.execute('SELECT COUNT(*) FROM publication_quota_claims WHERE account_key=? AND api_path=?', (account_key,obs['api_path'])).fetchone()[0]
    if obs['api_path'] == SUBMIT:
        reserved = db.execute("SELECT COUNT(*) FROM publication_quota_reservations r WHERE r.account_key=? AND NOT EXISTS (SELECT 1 FROM publication_quota_claims c WHERE c.account_key=r.account_key AND c.candidate_id=r.candidate_id AND c.attempt=r.attempt AND c.step='SUBMIT') AND NOT (r.candidate_id=? AND r.attempt=? AND ?='SUBMIT' AND ?=0)", (account_key,candidate_id,attempt,step,int(reserve_check))).fetchone()[0]
        spent += reserved
    if spent >= obs['remaining']: _hold('QUOTA_EXHAUSTED')
    # Across reboot the rate window cannot be reconstructed conservatively.
    different_boot = db.execute('SELECT 1 FROM publication_quota_claims WHERE account_key=? AND api_path=? AND boot_id!=? LIMIT 1', (account_key,obs['api_path'],boot_id)).fetchone()
    if different_boot: _hold('QUOTA_RATE_WINDOW_UNKNOWN')
    future = db.execute('SELECT 1 FROM publication_quota_claims WHERE account_key=? AND api_path=? AND boot_id=? AND created_mono_ms>? LIMIT 1', (account_key,obs['api_path'],boot_id,mono_ms)).fetchone()
    if future: _hold('QUOTA_CLOCK_CHANGED')
    recent = db.execute('SELECT COUNT(*) FROM publication_quota_claims WHERE account_key=? AND api_path=? AND boot_id=? AND created_mono_ms>?', (account_key,obs['api_path'],boot_id,mono_ms-obs['refresh_ms'])).fetchone()[0]
    if obs['api_path'] == SUBMIT:
        recent += db.execute("SELECT COUNT(*) FROM publication_quota_reservations r WHERE r.account_key=? AND r.boot_id=? AND r.created_mono_ms>? AND NOT EXISTS (SELECT 1 FROM publication_quota_claims c WHERE c.account_key=r.account_key AND c.candidate_id=r.candidate_id AND c.attempt=r.attempt AND c.step='SUBMIT') AND NOT (r.candidate_id=? AND r.attempt=? AND ?='SUBMIT' AND ?=0)", (account_key,boot_id,mono_ms-obs['refresh_ms'],candidate_id,attempt,step,int(reserve_check))).fetchone()[0]
    if recent >= obs['call_count']: _hold('QUOTA_RATE_LIMIT')
    try:
        db.execute('INSERT INTO publication_quota_claims VALUES (?,?,?,?,?,?,?,?,?,?,?,?)',
            (account_key,candidate_id,intent_id,step,ordinal,attempt,obs['api_path'],observation_sha,binding_sha,wall_ms,mono_ms,boot_id))
    except sqlite3.IntegrityError:
        _hold('QUOTA_CLAIM_ALREADY_SPENT')


def claim(db, **kwargs):
    """Spend once; SUBMIT additionally requires its joint reservation."""
    if 'reserve_check' in kwargs or 'joint' in kwargs: _hold('QUOTA_STEP_INVALID')
    return _claim(db, **kwargs)


def reserve_final_submit(db, *, draft_observation_sha, submit_observation_sha, **kwargs):
    """Reserve final draft GET and submit atomically before final GET is sent.

    Must be called from a single store.event apply with caller's stable account
    lock held. Failed checks roll back to the savepoint; caller must abort the
    enclosing event on any exception. No reservation is a remote allocation.
    """
    if not db.in_transaction: _hold('QUOTA_TRANSACTION_REQUIRED')
    if any(k in kwargs for k in ('step','ordinal','observation_sha','reserve_check','joint')):
        _hold('QUOTA_STEP_INVALID')
    intent_id=kwargs.get('intent_id')
    _id(intent_id)
    db.execute('SAVEPOINT quota_joint')
    try:
        common = dict(kwargs)
        common['intent_id'] = None
        _claim(db,step='FINAL',ordinal=kwargs['attempt'],observation_sha=draft_observation_sha,joint=True,**common)
        # Run all submit quota and binding checks without retaining the claim.
        db.execute('SAVEPOINT quota_probe')
        try:
            _claim(db,step='SUBMIT',ordinal=1,observation_sha=submit_observation_sha,reserve_check=True,**kwargs)
        finally:
            db.execute('ROLLBACK TO quota_probe');db.execute('RELEASE quota_probe')
        db.execute('INSERT INTO publication_quota_reservations VALUES (?,?,?,?,?,?,?,?,?,?)',
            (kwargs['account_key'],kwargs['candidate_id'],intent_id,kwargs['attempt'],SUBMIT,
             submit_observation_sha,kwargs['binding_sha'],kwargs['wall_ms'],kwargs['mono_ms'],kwargs['boot_id']))
        db.execute('RELEASE quota_joint')
    except BaseException:
        db.execute('ROLLBACK TO quota_joint');db.execute('RELEASE quota_joint')
        raise


TABLES = ('publication_quota_observations','publication_quota_claims','publication_quota_reservations')

def snapshot(db, account_key):
    """Canonical safe complete table projection, including rejection of orphan accounts."""
    _id(account_key)
    result = {}
    for table in TABLES:
        columns = [r[1] for r in db.execute('PRAGMA table_info('+table+')')]
        if not columns: _hold('QUOTA_SCHEMA_UNAVAILABLE')
        rows = [dict(zip(columns,row)) for row in db.execute('SELECT * FROM '+table)]
        if any(row['account_key'] != account_key for row in rows):
            _hold('QUOTA_ACCOUNT_MISMATCH')
        result[table] = sorted(rows, key=lambda row: json.dumps(row,sort_keys=True,separators=(',',':')))
    return result


def append_event_data(db, account_key, event_data, before):
    """Append exact new rows and aggregate hash to trusted event's data."""
    after = snapshot(db, account_key)
    added = {}
    for table in TABLES:
        old = {json.dumps(r,sort_keys=True,separators=(',',':')) for r in before[table]}
        new = {json.dumps(r,sort_keys=True,separators=(',',':')) for r in after[table]}
        if not old <= new: _hold('QUOTA_HISTORY_MUTATED')
        added[table] = [r for r in after[table] if json.dumps(r,sort_keys=True,separators=(',',':')) not in old]
    if any(added.values()):
        if 'quota_delta' in event_data or 'quota_state_sha' in event_data:
            _hold('QUOTA_EVENT_COLLISION')
        event_data['quota_delta'] = added
        event_data['quota_state_sha'] = _fingerprint(after)


def replay_event(data, replay):
    has_delta = 'quota_delta' in data
    if has_delta != ('quota_state_sha' in data): _hold('QUOTA_HISTORY_INVALID')
    if not has_delta: return
    delta = data['quota_delta']
    if type(delta) is not dict or set(delta) != set(TABLES): _hold('QUOTA_HISTORY_INVALID')
    for table in TABLES:
        if type(delta[table]) is not list: _hold('QUOTA_HISTORY_INVALID')
        for row in delta[table]:
            if type(row) is not dict or row in replay[table]: _hold('QUOTA_HISTORY_INVALID')
            replay[table].append(row)
        replay[table].sort(key=lambda row: json.dumps(row,sort_keys=True,separators=(',',':')))
    if _fingerprint(replay) != data['quota_state_sha']: _hold('QUOTA_HISTORY_INVALID')


def verify_replay(db, account_key, replay):
    if snapshot(db, account_key) != replay: _hold('QUOTA_HISTORY_INVALID')
