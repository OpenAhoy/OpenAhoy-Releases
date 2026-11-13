"""Human Settings enrollment, preserving each strictly rejected attempt.

UNKNOWN attempts remain unchanged. A separately selected, newly credentialed
validation may append a schema3 attempt; no implicit retry or alternate identity.
"""
from contextlib import ExitStack
from copy import deepcopy
from dataclasses import asdict
import os
from pathlib import Path
import secrets
import time

from .contracts import Secret, WCEError
from .own_bootstrap_security import (CheckedTokenRejected, TokenRejectionProof,
    acquire_checked, finite, path_check)
from .own_connection_enrollment import (PendingIdentity, hold_upgrades, initialize,
    publish)
from .own_connection_policy import locked, registry_path
from .own_connection_registry import (APPID, check_snapshot,
    derived_identity, label, metadata, propose, snapshot, sync, transaction_path, write)
from .own_connection_token import CachedToken, ContinuousClock
from .own_keychain import KeychainCredential, valid_secret
from .service import canonical, digest

PROOF = asdict(TokenRejectionProof())
STATES = {
    'NOT_SENT': (1, 'NOT_STORED', 'NOT_COMMITTED'),
    'SPENT_RESULT_UNKNOWN': (2, 'NOT_STORED', 'NOT_COMMITTED'),
    'REJECTED_IP': (3, 'NOT_STORED', 'NOT_COMMITTED'),
    'VALIDATED': (3, 'STORE_ATTEMPT_UNKNOWN', 'NOT_COMMITTED'),
    'STORED': (4, 'STORED', 'NOT_COMMITTED'),
    'COMMITTED': (5, 'STORED', 'COMMITTED'),
}


def attempt(reviewed):
    return {'review': deepcopy(reviewed), 'state': 'NOT_SENT', 'credential': 'NOT_STORED',
        'binding': 'NOT_COMMITTED', 'started_at': None, 'finished_at': None, 'rejection': None}


def initial_record(reviewed, parent):
    return {'schema': 2, 'identity': deepcopy(reviewed['identity']), 'label': reviewed['label'],
        'parent': parent, 'pins': None, 'revision': 1, 'attempts': [attempt(reviewed)]}


def invalid():
    raise WCEError('CONNECTION_ENROLLMENT_REQUIRES_RECONCILIATION')


def validate_record(record):
    if (type(record) is not dict or set(record) != {'schema', 'identity', 'label', 'parent',
            'pins', 'revision', 'attempts'} or type(record['schema']) is not int or record['schema'] not in {2,3}
            or type(record['revision']) is not int or type(record['pins']) is not dict
            or set(record['pins']) != {'root', 'images', 'database', 'profile'}
            or type(record['attempts']) is not list or not record['attempts']):
        invalid()
    label(record['label'])
    weight, seen, prefix_schema = 0, set(), 2
    for index, current in enumerate(record['attempts']):
        if (type(current) is not dict or set(current) != {'review', 'state', 'credential',
                'binding', 'started_at', 'finished_at', 'rejection'}
                or type(current['state']) is not str or current['state'] not in STATES):
            invalid()
        state = current['state']
        weight += STATES[state][0]
        if (current['credential'], current['binding']) != STATES[state][1:]:
            invalid()
        reviewed = current['review']
        required = {'base', 'identity', 'label', 'transaction'} | ({'resume'} if index else set())
        if type(reviewed) is dict and 'preserve_existing' in reviewed:
            if reviewed['preserve_existing'] is not True: invalid()
            required |= {'preserve_existing'}
        continuation=reviewed.get('continuation') if type(reviewed) is dict else None
        if continuation is not None:
            if (not index or record['schema']!=3 or type(continuation) is not dict
                    or set(continuation)!={'prior_schema','mode'}
                    or type(continuation['prior_schema']) is not int
                    or continuation['prior_schema']!=prefix_schema
                    or type(continuation['mode']) is not str
                    or continuation['mode'] not in {'NEW_VALIDATION','IP_REJECTED'}):invalid()
            prior_state=record['attempts'][index-1]['state']
            expected='SPENT_RESULT_UNKNOWN' if continuation['mode']=='NEW_VALIDATION' else 'REJECTED_IP'
            if prior_state!=expected:invalid()
            required |= {'continuation'}
        elif prefix_schema==3:invalid()
        if (type(reviewed) is not dict or set(reviewed) != required
                or reviewed['identity'] != record['identity'] or reviewed['label'] != record['label']
                or type(reviewed['base']) is not dict
                or derived_identity(reviewed['base'], record['identity']['appid']) != record['identity']):
            invalid()
        transaction_path(Path(reviewed['base']['registry']), reviewed['transaction'])
        if reviewed['transaction'] in seen:
            invalid()
        seen.add(reviewed['transaction'])
        if index:
            if (any(a['review'].get('preserve_existing') is True for a in record['attempts'][:index])
                    and reviewed.get('preserve_existing') is not True):invalid()
            prior = record | {'schema':prefix_schema,'attempts': record['attempts'][:index], 'revision': weight - STATES[state][0]}
            if reviewed['resume'] != {'record_digest': digest(prior),
                    'revision': prior['revision'], 'next_sequence': index + 1}:
                invalid()
        if continuation is not None:prefix_schema=3
        started, finished = current['started_at'], current['finished_at']
        if state == 'NOT_SENT':
            if started is not None or finished is not None:
                invalid()
        elif not finite(started) or started <= 0:
            invalid()
        if state == 'REJECTED_IP':
            if (current['rejection'] != PROOF or not finite(finished) or finished < started):
                invalid()
        elif current['rejection'] is not None or finished is not None:
            invalid()
        if index < len(record['attempts']) - 1 and state != 'REJECTED_IP':
            next_review=record['attempts'][index+1].get('review',{})
            if state!='SPENT_RESULT_UNKNOWN' or next_review.get('continuation',{}).get('mode')!='NEW_VALIDATION':invalid()
    if weight != record['revision'] or prefix_schema!=record['schema']:
        invalid()
    return record


def pending_path(reviewed):
    return Path(reviewed['base']['registry']).parent / 'connection-enrollments' / (reviewed['identity']['appid'] + '.json')


def checked_pending(reviewed, path, record):
    validate_record(record)
    check_snapshot(reviewed['base'])
    if (record['identity'] != derived_identity(reviewed['base'], record['identity']['appid'])
            or record['identity'] != reviewed['identity'] or record['label'] != reviewed['label']
            or path != pending_path(reviewed)
            or record['parent'] != list(path_check(path.parent, True)) or metadata(path) != record):
        invalid()
    pending = PendingIdentity(reviewed)
    pending.check()
    if pending.pins() != record['pins']:
        invalid()
    return pending


def retryable(record, wall):
    validate_record(record)
    last = record['attempts'][-1]
    if last['state'] != 'REJECTED_IP':
        invalid()
    # A new explicit review may follow a strictly proved IP rejection.
    # Historical timestamps remain facts, not a client-side retry allowance.


def propose_checked(appid, display_label, registry=None, wall=time.time):
    registry = Path(registry or registry_path())
    if type(appid) is not str or APPID.fullmatch(appid) is None:
        raise WCEError('CONNECTION_INVALID_APPID')
    appid = appid.lower()
    path = registry.parent / 'connection-enrollments' / (appid + '.json')
    if not os.path.lexists(path):
        return propose(appid, display_label, registry)
    label(display_label)
    with locked(registry.parent / 'connection-setup.lock', nonblocking=True):
        record = metadata(path)
        retryable(record, wall)
        base = snapshot(registry)
        if any(p['value']['identity']['appid'].lower() == appid for p in base['policies'].values()):
            raise WCEError('CONNECTION_RESOURCE_ALREADY_BOUND')
        reviewed = {'base': base, 'identity': derived_identity(base, appid), 'label': display_label,
            'transaction': 'txn-' + secrets.token_hex(16),
            'resume': {'record_digest': digest(record), 'revision': record['revision'],
                       'next_sequence': len(record['attempts']) + 1}}
        checked_pending(reviewed, path, record)
        if record['attempts'][-1]['review'].get('preserve_existing') is True:
            reviewed['preserve_existing'] = True
        if record['schema']==3:
            reviewed['continuation']={'prior_schema':3,'mode':'IP_REJECTED'}
        # A visible rename after an uncertain fsync is not enough. Reconcile the
        # original file and directory before presenting a new human review.
        sync(path); sync(path.parent, True)
        checked_pending(reviewed, path, record)
        return reviewed


def prepare_revalidation(appid, registry):
    """New explicit validation intent, local only. Caller holds original run lock.

    Append NOT_SENT first. A crash before the inline view adopts its transaction
    is recoverable from this validated immediate predecessor; no network occurs.
    No original UNKNOWN, identity, credential scope or other account is replaced.
    """
    registry=Path(registry)
    with locked(registry.parent/'connection-setup.lock',nonblocking=True):
        path=registry.parent/'connection-enrollments'/(appid+'.json')
        record=metadata(path);validate_record(record);last=record['attempts'][-1]
        if (last['state']!='SPENT_RESULT_UNKNOWN' or last['credential']!='NOT_STORED'
                or last['binding']!='NOT_COMMITTED'):invalid()
        base=snapshot(registry)
        if any(p['value']['identity']['appid'].lower()==appid for p in base['policies'].values()):
            raise WCEError('CONNECTION_RESOURCE_ALREADY_BOUND')
        reviewed={'base':base,'identity':derived_identity(base,appid),'label':record['label'],
            'transaction':'txn-'+secrets.token_hex(16),'preserve_existing':True,
            'resume':{'record_digest':digest(record),'revision':record['revision'],
                'next_sequence':len(record['attempts'])+1},
            'continuation':{'prior_schema':record['schema'],'mode':'NEW_VALIDATION'}}
        pending=checked_pending(reviewed,path,record)
        new=record|{'schema':3,'revision':record['revision']+1,'attempts':record['attempts']+[attempt(reviewed)]}
        replace_record(path,record,new,pending)
        return reviewed


def replace_record(path, old, new, pending):
    pending.check()
    validate_record(new)
    if metadata(path) != old or list(path_check(path.parent, True)) != old['parent']:
        invalid()
    write(path, new, old['parent'])
    pending.check()
    if metadata(path) != new:
        invalid()
    return new


def transition(path, record, pending, state, **fields):
    current = record['attempts'][-1]
    allowed = {'NOT_SENT': {'SPENT_RESULT_UNKNOWN'},
               'SPENT_RESULT_UNKNOWN': {'REJECTED_IP', 'VALIDATED'},
               'VALIDATED': {'STORED'}, 'STORED': {'COMMITTED'}}
    if state not in allowed.get(current['state'], set()):
        invalid()
    updated = current | {'state': state, 'credential': STATES[state][1], 'binding': STATES[state][2]} | fields
    new = record | {'revision': record['revision'] + 1,
                    'attempts': record['attempts'][:-1] + [updated]}
    return replace_record(path, record, new, pending)


def enroll_checked(reviewed, read_secret, acquire=acquire_checked,
        credential_factory=KeychainCredential, wall=time.time, continuous=None, guard=lambda: None, resume_not_sent=False):
    from .own_replacement_batch import maintenance_gate
    with maintenance_gate(Path(reviewed['base']['registry'])):
        return _enroll_checked_under_replacement_gate(reviewed,read_secret,acquire,
            credential_factory,wall,continuous,guard,resume_not_sent)


def _enroll_checked_under_replacement_gate(reviewed,read_secret,acquire,
        credential_factory,wall,continuous,guard,resume_not_sent=False):
    continuous = continuous or ContinuousClock()
    registry = Path(reviewed['base']['registry'])
    with locked(registry.parent / 'connection-setup.lock', nonblocking=True), ExitStack() as locks:
        guard(); check_snapshot(reviewed['base'])
        held_roots = hold_upgrades(reviewed, locks)
        if resume_not_sent:
            path = pending_path(reviewed)
            record = metadata(path)
            validate_record(record)
            if (record['attempts'][-1]['state'] != 'NOT_SENT'
                    or record['attempts'][-1]['review'] != reviewed):
                invalid()
            pending = checked_pending(reviewed, path, record)
        elif 'resume' not in reviewed:
            pending, path, record = initialize(reviewed, schema=2)
            validate_record(record)
        else:
            path = pending_path(reviewed)
            record = metadata(path)
            retryable(record, wall)
            pending = checked_pending(reviewed, path, record)
            if reviewed['resume'] != {'record_digest': digest(record), 'revision': record['revision'],
                                     'next_sequence': len(record['attempts']) + 1}:
                invalid()
            sync(path); sync(path.parent, True)
            checked_pending(reviewed, path, record)
            record = replace_record(path, record, record | {'revision': record['revision'] + 1,
                'attempts': record['attempts'] + [attempt(reviewed)]}, pending)
        guard(); pending.check()
        secret = read_secret()
        try:
            if not valid_secret(secret):
                raise WCEError('BOOTSTRAP_CREDENTIAL_INVALID')
            guard(); pending.check()
            before_wall, before_cont = wall(), continuous()
            record = transition(path, record, pending, 'SPENT_RESULT_UNKNOWN', started_at=before_wall)
            guard(); pending.check()
            try:
                token, deadline, _ = acquire(pending.data['appid'], secret)
            except CheckedTokenRejected as error:
                # Only this acquire window can prove a rejected token attempt.
                if type(error.proof) is TokenRejectionProof and asdict(error.proof) == PROOF:
                    record = transition(path, record, pending, 'REJECTED_IP',
                        finished_at=wall(), rejection=dict(PROOF))
                raise
            if type(token) is not Secret or not 30 < deadline - before_wall <= 7200.1:
                raise WCEError('CONNECTION_TOKEN_TIME_INVALID')
            cached = CachedToken(token, before_wall, before_cont, deadline, before_cont + deadline - before_wall)
            guard(); pending.check()
            if (wall() + 30 >= deadline or continuous() + 30 >= cached.continuous_deadline
                    or wall() < before_wall or continuous() < before_cont
                    or abs((wall() - before_wall) - (continuous() - before_cont)) >= 5):
                raise WCEError('CONNECTION_TOKEN_TIME_INVALID')
            record = transition(path, record, pending, 'VALIDATED')
            try:
                credential_factory(pending).store(secret)
            except CheckedTokenRejected:
                # A typed exception from any later adapter is not token evidence.
                raise WCEError('CONNECTION_KEYCHAIN_STORE_UNDETERMINED') from None
            pending.check()
            record = transition(path, record, pending, 'STORED')
        finally:
            secret = None
        guard()
        policy, retained, lifetime = publish(reviewed, pending, held_roots)
        try:
            # Publication changed the snapshot intentionally. Only the original
            # reservation CAS remains, while policy checks the committed identity.
            policy.check()
            final = record | {'revision': record['revision'] + 1,
                'attempts': record['attempts'][:-1] + [record['attempts'][-1] |
                    {'state': 'COMMITTED', 'binding': 'COMMITTED'}]}
            validate_record(final)
            if metadata(path) != record:
                invalid()
            write(path, final, record['parent'])
            return policy, cached, retained, lifetime
        except BaseException:
            retained.close()
            raise


def publication_match(record, name):
    # An unrelated incomplete reservation must not poison another account's
    # local repair. Validate the one unique target after bounded selection.
    attempts = record.get('attempts')
    if type(attempts) is not list or not attempts:
        return False
    current = attempts[-1]
    return (type(current) is dict and type(current.get('review')) is dict
            and current['review'].get('transaction') == name)


def resume_checked_publication(path, record, registry):
    from .own_replacement_batch import maintenance_gate
    with maintenance_gate(Path(registry)):
        return _resume_checked_under_replacement_gate(path,record,registry)


def _resume_checked_under_replacement_gate(path, record, registry):
    validate_record(record)
    current = record['attempts'][-1]
    if current['state'] != 'STORED':
        raise WCEError('CONNECTION_ENROLLMENT_REQUIRES_HUMAN_DECISION')
    reviewed = current['review']
    if reviewed['base']['registry'] != str(registry):
        invalid()
    transaction = transaction_path(registry, reviewed['transaction'])
    if os.path.lexists(transaction):
        from .own_connection_enrollment import reconcile
        outcome = reconcile(transaction)
        if outcome == 'ROLLED_BACK':return outcome
        # Publication may already have committed before its process disappeared.
        # Verify the original physical identity and current membership rather
        # than demanding that the intentional registry change be undone.
        from .own_connection_policy import resolve, validate_identity
        with locked(registry.parent / 'connection-setup.lock', nonblocking=True):
            validate_record(record)
            if metadata(path)!=record or list(path_check(path.parent,True))!=record['parent']:
                invalid()
            identity=PendingIdentity(reviewed)
            validate_identity(record['identity'],identity.root)
            if identity.pins()!=record['pins']:invalid()
            policy=resolve(record['identity']['connection_id'],registry)
            if policy.data!=record['identity'] or policy.value['transaction']!=reviewed['transaction']:invalid()
            final=record | {'revision':record['revision']+1,'attempts':record['attempts'][:-1]+[
                current | {'state':'COMMITTED','binding':'COMMITTED'}]}
            validate_record(final)
            write(path,final,record['parent'])
            if metadata(path)!=final:invalid()
        return 'COMMITTED_BOUND_IDLE'
    with locked(registry.parent / 'connection-setup.lock', nonblocking=True), ExitStack() as locks:
        pending = checked_pending(reviewed, path, record)
        held_roots = hold_upgrades(reviewed, locks)
        policy, retained, _ = publish(reviewed, pending, held_roots)
        with retained:
            policy.check()
            final = record | {'revision': record['revision'] + 1,
                'attempts': record['attempts'][:-1] + [current | {'state': 'COMMITTED', 'binding': 'COMMITTED'}]}
            validate_record(final)
            if metadata(path) != record:
                invalid()
            write(path, final, record['parent'])
        return 'COMMITTED_BOUND_IDLE'
