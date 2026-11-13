"""Pure GROUP08 candidate values. Nothing here verifies authority or sends work.

The integrating service must load real provenance, coverage and permission
proofs. A Coverage.scope string is a claim to display, never a grant.
"""
from dataclasses import dataclass
import hashlib
import json
import re

MAX_BATCH = 64
MAX_MEMBERS = 8
MAX_POOL = 200
MAX_COUNTER = 2**63 - 1
_DIGEST = re.compile(r'[a-f0-9]{64}')
_ID = re.compile(r'[A-Za-z0-9][A-Za-z0-9_.:-]{0,127}')


class CandidateError(ValueError):
    """Only fixed codes, with no caller-controlled data in the exception."""


def fail(code):
    raise CandidateError(code)


def integer(value, low=0, high=MAX_COUNTER):
    if type(value) is not int or not low <= value <= high:
        fail('GROUP_INTEGER_INVALID')
    return value


def identifier(value):
    if type(value) is not str or _ID.fullmatch(value) is None:
        fail('GROUP_IDENTIFIER_INVALID')
    return value


def sha(value):
    if type(value) is not str or _DIGEST.fullmatch(value) is None:
        fail('GROUP_DIGEST_INVALID')
    return value


def canonical(value):
    # Exact service.canonical algorithm; importing service would import storage.
    return json.dumps(value, sort_keys=True, separators=(',', ':'),
                      ensure_ascii=False, allow_nan=False)


def digest(value):
    return hashlib.sha256(canonical(value).encode('utf-8')).hexdigest()


@dataclass(frozen=True, slots=True)
class Article:
    binding_sha: str
    article_id: str
    version_sha: str
    original_request_sha: str
    source_sha: str
    projection_sha: str
    origin: str = 'NEW_NOT_SENT'
    old_ref_sha: str | None = None
    old_position: int | None = None

    def __post_init__(self):
        sha(self.binding_sha)
        identifier(self.article_id)
        for value in (self.version_sha, self.original_request_sha,
                      self.source_sha, self.projection_sha):
            sha(value)
        if type(self.origin) is not str:
            fail('GROUP_SOURCE_INVALID')
        if self.origin == 'NEW_NOT_SENT':
            if self.old_ref_sha is not None or self.old_position is not None:
                fail('GROUP_SOURCE_INVALID')
        elif self.origin == 'LEGACY_REGISTERED':
            sha(self.old_ref_sha)
            integer(self.old_position, 0, MAX_MEMBERS - 1)
        else:
            fail('GROUP_SOURCE_INVALID')

    def value(self):
        return {name: getattr(self, name) for name in self.__slots__}


@dataclass(frozen=True, slots=True)
class PoolGroup:
    binding_sha: str
    group_id: str
    created_seq: int
    generation: int
    row_version: int
    state: str
    ref_sha: str
    members: tuple[Article, ...]
    main_article_id: str

    def __post_init__(self):
        sha(self.binding_sha)
        identifier(self.group_id)
        integer(self.created_seq)
        integer(self.generation, 1)
        integer(self.row_version, 1)
        sha(self.ref_sha)
        if type(self.state) is not str or self.state not in ('OPEN', 'FULL', 'PUBLISHED', 'HOLD', 'UNKNOWN'):
            fail('GROUP_POOL_STATE_INVALID')
        if type(self.members) is not tuple or not 1 <= len(self.members) <= MAX_MEMBERS:
            fail('GROUP_POOL_MEMBERS_INVALID')
        if self.state == 'OPEN' and len(self.members) >= MAX_MEMBERS:
            fail('GROUP_POOL_STATE_INVALID')
        if self.state == 'FULL' and len(self.members) != MAX_MEMBERS:
            fail('GROUP_POOL_STATE_INVALID')
        if any(type(member) is not Article for member in self.members):
            fail('GROUP_POOL_MEMBERS_INVALID')
        identifier(self.main_article_id)
        if self.main_article_id != self.members[0].article_id:
            fail('GROUP_MAIN_INVALID')
        seen = set()
        for position, member in enumerate(self.members):
            if type(member) is not Article or member.binding_sha != self.binding_sha:
                fail('GROUP_BINDING_INVALID')
            if (member.origin != 'LEGACY_REGISTERED' or member.old_ref_sha != self.ref_sha
                    or member.old_position != position):
                fail('GROUP_SOURCE_INVALID')
            if member.article_id in seen:
                fail('GROUP_DUPLICATE_ARTICLE')
            seen.add(member.article_id)

    def value(self):
        return {'binding_sha': self.binding_sha, 'group_id': self.group_id,
                'created_seq': self.created_seq, 'generation': self.generation,
                'row_version': self.row_version, 'state': self.state,
                'ref_sha': self.ref_sha, 'main_article_id': self.main_article_id,
                'members': [member.value() for member in self.members]}


@dataclass(frozen=True, slots=True)
class Coverage:
    binding_sha: str
    scope: str
    snapshot_sha: str
    pool_generation: int
    pool_head_sha: str

    def __post_init__(self):
        for value in (self.binding_sha, self.snapshot_sha, self.pool_head_sha):
            sha(value)
        integer(self.pool_generation)
        if type(self.scope) is not str or self.scope not in ('ACCOUNT', 'MANAGED_ONLY', 'UNKNOWN'):
            fail('GROUP_COVERAGE_INVALID')

    def value(self):
        return {name: getattr(self, name) for name in self.__slots__}


@dataclass(frozen=True, slots=True)
class LegacyMerge:
    """Explicit ordered source group IDs; complete members come from pool values.

    This is a requested map, not evidence that the selected refs are eligible.
    It cannot select raw refs or split one original group among children.
    """
    source_group_ids: tuple[str, ...]
    map_source_sha: str

    def __post_init__(self):
        sha(self.map_source_sha)
        if (type(self.source_group_ids) is not tuple
                or not 1 <= len(self.source_group_ids) <= MAX_MEMBERS):
            fail('GROUP_OLD_REF_BOUND')
        for group_id in self.source_group_ids:
            identifier(group_id)
        if len(set(self.source_group_ids)) != len(self.source_group_ids):
            fail('GROUP_OLD_REF_DUPLICATE')

    def value(self):
        return {'source_group_ids': list(self.source_group_ids),
                'map_source_sha': self.map_source_sha}


def read_slot(phase, old_index=None, retirement_cursor=None):
    return {'key': phase if old_index is None and retirement_cursor is None else
            phase + ':' + str(old_index if old_index is not None else retirement_cursor),
            'phase': phase, 'old_index': old_index,
            'retirement_cursor': retirement_cursor}


def budget_for(old_ref_count):
    """Fixed candidate vector, not permission to consume any slot."""
    n = integer(old_ref_count, 0, MAX_MEMBERS)
    if n == 0:
        healthy = [read_slot('NEW'), read_slot('FINAL_NEW')]
    else:
        healthy = [read_slot('OLD_BASELINE', i) for i in range(n)]
        healthy.append(read_slot('NEW'))
        healthy.extend(read_slot('OLD_PRE_SWITCH', i) for i in range(n))
        for cursor in range(n):
            if cursor and n > 1:
                healthy.extend((read_slot('NEW_REFRESH', retirement_cursor=cursor),
                                read_slot('OLD_REFRESH', cursor, cursor)))
            healthy.append(read_slot('OLD_INVALID', cursor, cursor))
        healthy.append(read_slot('FINAL_NEW'))
    recovery = [] if n <= 1 else [read_slot('RECOVERY_NEW'), read_slot('RECOVERY_OLD')]
    return {'get_healthy': len(healthy), 'get_cap': len(healthy) + len(recovery),
            'add_cap': 1, 'delete_cap': n, 'uploads': 'NOT_COUNTED_BY_PURE_COMPONENT',
            'healthy_reads': healthy, 'recovery_reads': recovery,
            'recovery_subject': 'CURRENT_UNFINISHED_CURSOR_FROM_OPERATION' if recovery else None,
            'delete_slots': [{'key': 'DELETE:' + str(i), 'old_index': i,
                              'before_read': 'OLD_INVALID:' + str(i)} for i in range(n)],
            'freshness': {'maximum_seconds': 60, 'same_lock_epoch_required': True,
                          'add_requires': ['OLD_BASELINE:' + str(i) for i in range(n)],
                          'switch_requires': ['NEW'] + ['OLD_PRE_SWITCH:' + str(i) for i in range(n)],
                          'delete_requires': [
                              {'old_index': i, 'reads':
                               (['NEW', 'OLD_PRE_SWITCH:0'] if i == 0 else
                                ['NEW_REFRESH:' + str(i), 'OLD_REFRESH:' + str(i)])}
                              for i in range(n)],
                          'later_cursor_pair_mandatory': n > 1,
                          'proof_status': 'UNVERIFIED_BY_PURE_COMPONENT'},
            'authority': 'NONE_LOCAL_CANDIDATE'}


def retirement_reserve(old_ref_count, cursor, consumed_read_keys, get_cap=None):
    """Pure arithmetic/ordering precheck; ALLOCATED never means DELETE admitted.

    All consumed claims (including UNKNOWN/rejected) count. This function does
    not know their outcomes, epoch, age, proof validity or permission. The service
    must additionally reject UNKNOWN and revalidate all these facts before DELETE.
    get_cap is a service-loaded cap bounded by this candidate's hard maximum.
    """
    n = integer(old_ref_count, 1, MAX_MEMBERS)
    integer(cursor, 0, n - 1)
    budget = budget_for(n)
    cap = budget['get_cap'] if get_cap is None else integer(get_cap, 0, budget['get_cap'])
    if type(consumed_read_keys) is not tuple or any(type(k) is not str for k in consumed_read_keys):
        fail('GROUP_READ_VECTOR_INVALID')
    healthy = [slot['key'] for slot in budget['healthy_reads']]
    recovery = [slot['key'] for slot in budget['recovery_reads']]
    if (len(set(consumed_read_keys)) != len(consumed_read_keys)
            or any(k not in healthy + recovery for k in consumed_read_keys)):
        fail('GROUP_READ_VECTOR_INVALID')
    ordinary = [key for key in consumed_read_keys if key not in recovery]
    # A claim out of phase or a skipped mandatory old/new refresh is not a prefix.
    if ordinary != healthy[:len(ordinary)]:
        fail('GROUP_READ_PHASE_CONFLICT')
    used_recovery = [key for key in consumed_read_keys if key in recovery]
    if used_recovery != recovery[:len(used_recovery)]:
        fail('GROUP_READ_PHASE_CONFLICT')
    if used_recovery:
        first = consumed_read_keys.index('RECOVERY_NEW')
        if 'NEW' not in consumed_read_keys[:first]:
            fail('GROUP_READ_PHASE_CONFLICT')
        if len(used_recovery) == 2 and consumed_read_keys[first:first + 2] != tuple(recovery):
            fail('GROUP_READ_PHASE_CONFLICT')
    cut = healthy.index('OLD_INVALID:' + str(cursor))
    prerequisites = healthy[:cut]
    future = healthy[cut:]
    used = len(consumed_read_keys)
    if ordinary != prerequisites or (used_recovery and len(used_recovery) != 2):
        reason = 'GROUP_READ_PREREQUISITES_REQUIRED'
    elif used > cap or cap - used < len(future):
        reason = 'GROUP_BUDGET_EXHAUSTED'
    else:
        reason = None
    return {'state': 'LOCAL_CANDIDATE', 'arithmetic_state': 'HOLD' if reason else 'ALLOCATED',
            'reason': reason, 'old_index': cursor, 'get_cap': cap, 'used': used,
            'remaining': max(0, cap - used), 'required_remaining': len(future),
            'reserved_reads': future, 'delete_admitted': False,
            'authority': 'NONE_LOCAL_CANDIDATE', 'remote_proofs_verified': False}
