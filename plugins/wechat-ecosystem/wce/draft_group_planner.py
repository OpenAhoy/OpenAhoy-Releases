"""Deterministic local-only GROUP08 planning, with no effectful dependencies."""
from .draft_group_contracts import (
    Article, CandidateError, Coverage, LegacyMerge, MAX_BATCH, MAX_COUNTER,
    MAX_MEMBERS, MAX_POOL, PoolGroup, budget_for, canonical, digest, fail,
    identifier, sha,
)


def _envelope(binding_sha, request_key, articles, groups, coverage, legacy):
    sha(binding_sha)
    identifier(request_key)
    if type(articles) is not tuple or not 1 <= len(articles) <= MAX_BATCH:
        fail('GROUP_BATCH_LIMIT')
    if type(groups) is not tuple or len(groups) > MAX_POOL:
        fail('GROUP_POOL_BOUND')
    if type(coverage) is not Coverage or coverage.binding_sha != binding_sha:
        fail('GROUP_BINDING_INVALID')
    if legacy is not None and type(legacy) is not LegacyMerge:
        fail('GROUP_LEGACY_MAP_INVALID')
    for article in articles:
        if type(article) is not Article or article.binding_sha != binding_sha:
            fail('GROUP_BINDING_INVALID')
    ids, references, sequences = set(), set(), set()
    memberships = {}
    published_versions = {}
    for group in groups:
        if type(group) is not PoolGroup or group.binding_sha != binding_sha:
            fail('GROUP_BINDING_INVALID')
        if group.group_id in ids or group.ref_sha in references or group.created_seq in sequences:
            fail('GROUP_POOL_DUPLICATE')
        ids.add(group.group_id)
        references.add(group.ref_sha)
        sequences.add(group.created_seq)
        if group.state == 'PUBLISHED':
            for member in group.members:
                published_versions.setdefault(member.article_id, set()).add(member.version_sha)
            continue
        for member in group.members:
            if member.article_id in memberships:
                fail('GROUP_ACTIVE_MEMBERSHIP_CONFLICT')
            memberships[member.article_id] = member
    ordered = tuple(sorted(groups, key=lambda g: (g.created_seq, g.group_id)))
    value = {'binding_sha': binding_sha, 'request_key': request_key,
             'articles': [article.value() for article in articles],
             'pool': [group.value() for group in ordered], 'coverage': coverage.value(),
             'legacy_map': None if legacy is None else legacy.value()}
    return ordered, memberships, published_versions, value


def _base(binding_sha, request_key, input_value):
    batch_id = 'group-batch-' + digest({'binding_sha': binding_sha, 'request_key': request_key})
    return {'schema': 1, 'state': 'LOCAL_CANDIDATE', 'executable': False,
            'authorization': 'NOT_PROVIDED_OR_CREATED', 'real_account_verified': False,
            'source_and_policy_verified': False, 'batch_id': batch_id,
            'input_sha': digest(input_value), 'binding_sha': binding_sha,
            'request_key': request_key, 'coverage_claim': input_value['coverage'],
            'pool_sha': digest(input_value['pool']), 'legacy_map_sha':
            None if input_value['legacy_map'] is None else digest(input_value['legacy_map'])}


def _finish(result):
    # A hash is a value identity, not a signature, proof or execution permit.
    result['candidate_sha'] = digest(result)
    return result


def _hold(base, reason):
    return _finish({**base, 'plan_state': 'HOLD', 'reason': reason,
                    'children': [], 'parent_caps': None,
                    'reservations_created': False,
                    'required_service_checks': _requirements()})


def _requirements():
    return ['CURRENT_FULL_BINDING_AND_SOURCE', 'REGISTERED_SAVE_AND_MEDIA_PROOFS',
            'CURRENT_OBJECT_UNCONSUMED_QUALIFICATION', 'FRESH_ACCOUNT_COVERAGE_AND_POOL_HEAD',
            'ORIGINAL_AND_HIDDEN_SETTINGS_REVIEW', 'CURRENT_POLICY_AND_ROUTE',
            'EXACT_PARENT_GRANT_INCLUDING_EACH_DELETE', 'SHARED_WRITER_LOCK_AND_ATOMIC_CLAIMS',
            'GLOBAL_ARTICLE_AND_OLD_REF_RESERVATIONS', 'UNKNOWN_AND_CANCEL_RECOVERY_BARRIERS',
            'FRESH_EPOCH_READ_PROOFS_AND_REMAINING_BUDGET', 'FINAL_PLATFORM_AND_VISIBLE_READBACK']


def _child(base, ordinal, target_id, generation, source_groups, members):
    n = len(source_groups)
    route = ('CREATE_NEW' if n == 0 else 'REPLACE_SINGLE' if n == 1 else 'MERGE_LEGACY_REFS_V1')
    old_indexes = {group.ref_sha: i for i, group in enumerate(source_groups)}
    origins = []
    for position, article in enumerate(members):
        old_index = old_indexes.get(article.old_ref_sha) if article.origin == 'LEGACY_REGISTERED' else None
        if article.origin == 'LEGACY_REGISTERED' and old_index is None:
            fail('GROUP_LEGACY_MAP_INCOMPLETE')
        origins.append({'target_position': position, **article.value(),
                        'source_old_index': old_index})
    old_refs = [{'old_index': i, 'ref_sha': group.ref_sha,
                 'group_id': group.group_id, 'generation': group.generation,
                 'row_version': group.row_version, 'main_article_id': group.main_article_id,
                 'members_sha': digest([article.value() for article in group.members]),
                 'member_count': len(group.members), 'delete_cap': 1,
                 'qualification': 'UNVERIFIED_BY_PURE_COMPONENT',
                 'required_retirement_profile': 'DELETE_ACK_AND_INVALIDATED_REFERENCE'}
                for i, group in enumerate(source_groups)]
    main = members[0].article_id
    main_changes = [{'article_id': group.main_article_id, 'old_group_id': group.group_id,
                     'old_role': 'MAIN', 'new_role': 'SECONDARY',
                     'new_position': next(i for i, article in enumerate(members)
                                          if article.article_id == group.main_article_id),
                     'exact_review_required': True}
                    for group in source_groups if group.main_article_id != main]
    key_fields = {'binding_sha': base['binding_sha'], 'batch_id': base['batch_id'],
                  'ordinal': ordinal, 'group_id': target_id, 'generation': generation,
                  'members_sha': digest(origins), 'old_refs_sha': digest(old_refs), 'route': route}
    child_key = digest(key_fields)
    return {'schema': 1, 'state': 'LOCAL_CANDIDATE', 'executable': False,
            'candidate_activation': 'PLANNED' if ordinal == 0 else 'WAITING',
            'ordinal': ordinal, 'child_key': child_key, 'operation_id': 'group-op-' + child_key,
            'target_group_id': target_id, 'target_generation': generation,
            'route': route, 'member_count': len(members), 'main_article_id': main,
            'members': origins, 'old_ref_set': old_refs, 'main_changes': main_changes,
            'budget': budget_for(n), 'settings': 'UNVERIFIED_BY_PURE_COMPONENT',
            'digest_projection': 'EMPTY_FOR_MULTI_KEEP_ORIGINAL_IN_ARCHIVE' if len(members) > 1
                                 else 'PRESERVE_EXPLICIT_SINGLE_DIGEST',
            'retirement_required': bool(n), 'platform_completion': 'NOT_OBSERVED'}


def _coverage(children, requested, expected_old):
    """Every request and each complete old membership once, without cross-child refs."""
    actual, old_members, old_owner = {}, {}, {}
    for child in children:
        for old in child['old_ref_set']:
            ref = old['ref_sha']
            if ref in old_owner:
                fail('GROUP_OLD_REF_CROSS_CHILD')
            old_owner[ref] = child['ordinal']
        for member in child['members']:
            aid = member['article_id']
            if aid in actual:
                fail('GROUP_DUPLICATE_ARTICLE')
            actual[aid] = member
            if member['origin'] == 'LEGACY_REGISTERED':
                key = (member['old_ref_sha'], member['old_position'])
                if key in old_members:
                    fail('GROUP_LEGACY_MAP_INCOMPLETE')
                old_members[key] = member
    for article in requested:
        member = actual.get(article.article_id)
        if member is None or any(member[name] != value for name, value in article.value().items()):
            fail('GROUP_REQUEST_COVERAGE_INVALID')
    expected = {(g.ref_sha, pos): article for g in expected_old
                for pos, article in enumerate(g.members)}
    if set(old_members) != set(expected):
        fail('GROUP_LEGACY_MAP_INCOMPLETE')
    for key, article in expected.items():
        if any(old_members[key][name] != value for name, value in article.value().items()):
            fail('GROUP_LEGACY_MAP_INCOMPLETE')
    expected_ids = {article.article_id for article in requested}
    expected_ids.update(article.article_id for group in expected_old for article in group.members)
    if set(actual) != expected_ids:
        fail('GROUP_REQUEST_COVERAGE_INVALID')
    return {'requested_count': len(requested), 'inherited_old_count': len(expected),
            'target_count': len(actual), 'every_requested_member_once': True,
            'every_original_member_once': True, 'old_ref_cross_child': False,
            'scope': 'VALUE_MAP_ONLY_NOT_PROVENANCE_OR_AUTHORITY'}


def plan_batch(binding_sha, request_key, articles, groups, coverage, legacy=None):
    """Plan 1..64 parsed requested articles against a bounded parsed pool.

    Malformed values raise fixed CandidateError. Well-formed business conflicts
    yield a HOLD candidate with no children; no partial reservations are made.
    Determinism assumes equal inputs, not that those inputs are trustworthy.
    """
    ordered, active, published_versions, value = _envelope(
        binding_sha, request_key, articles, groups, coverage, legacy)
    base = _base(binding_sha, request_key, value)
    seen = {}
    for article in articles:
        previous = seen.get(article.article_id)
        if previous is not None:
            return _hold(base, 'GROUP_HOLD_REVISION' if previous.version_sha != article.version_sha
                         else 'GROUP_DUPLICATE_ARTICLE')
        seen[article.article_id] = article
    if coverage.scope == 'UNKNOWN':
        return _hold(base, 'GROUP_POOL_COVERAGE_HOLD')
    available = [group for group in ordered if group.state not in ('FULL', 'PUBLISHED')]
    queue = list(articles)
    children, inherited = [], []
    if legacy is not None:
        selected_ids = legacy.source_group_ids
        if any(group.state in ('HOLD', 'UNKNOWN') for group in available[:len(selected_ids)]):
            return _hold(base, 'GROUP_EARLIER_POOL_BLOCKED')
        selected = tuple(available[:len(selected_ids)])
        if tuple(group.group_id for group in selected) != selected_ids:
            return _hold(base, 'GROUP_LEGACY_POOL_ORDER_CONFLICT')
        old_articles = tuple(article for group in selected for article in group.members)
        if len(old_articles) > MAX_MEMBERS:
            return _hold(base, 'GROUP_OLD_MEMBER_BOUND')
        if tuple(queue[:len(old_articles)]) != old_articles:
            return _hold(base, 'GROUP_LEGACY_MAP_INCOMPLETE')
        if any(article.origin != 'NEW_NOT_SENT' for article in queue[len(old_articles):]):
            return _hold(base, 'GROUP_LEGACY_MAP_INCOMPLETE')
        if len(selected) == 1 and len(queue) == len(old_articles):
            return _hold(base, 'GROUP_NO_CHANGE')
        queue = queue[len(old_articles):]
        inherited.extend(selected)
        available = available[len(selected):]
        take = min(MAX_MEMBERS - len(old_articles), len(queue))
        members = old_articles + tuple(queue[:take])
        queue = queue[take:]
        if selected[0].generation == MAX_COUNTER:
            fail('GROUP_GENERATION_EXHAUSTED')
        children.append(_child(base, 0, selected[0].group_id, selected[0].generation + 1,
                               selected, members))
    # Registered articles are accepted only through the exact complete legacy map.
    for article in queue:
        if article.origin != 'NEW_NOT_SENT':
            return _hold(base, 'GROUP_LEGACY_MAP_REQUIRED')
    for article in articles:
        existing = active.get(article.article_id)
        if existing is not None:
            if not (legacy is not None and article.origin == 'LEGACY_REGISTERED' and article == existing):
                return _hold(base, 'GROUP_HOLD_REVISION' if article.version_sha != existing.version_sha
                             else 'GROUP_ALREADY_ACTIVE')
        # PUBLISHED is excluded from the capacity pool, not from stable identity
        # history. No NEW_NOT_SENT label can reset a known published article ID.
        versions = published_versions.get(article.article_id)
        if versions is not None and article.origin == 'NEW_NOT_SENT':
            return _hold(base, 'GROUP_ALREADY_PUBLISHED' if article.version_sha in versions
                         else 'GROUP_HOLD_REVISION')
    while queue:
        source = ()
        if available:
            group = available.pop(0)
            if group.state in ('HOLD', 'UNKNOWN'):
                return _hold(base, 'GROUP_EARLIER_POOL_BLOCKED')
            source = (group,)
            old = group.members
            if group.generation == MAX_COUNTER:
                fail('GROUP_GENERATION_EXHAUSTED')
            generation, target_id = group.generation + 1, group.group_id
            inherited.append(group)
        else:
            if coverage.scope != 'ACCOUNT':
                return _hold(base, 'GROUP_ACCOUNT_COVERAGE_REQUIRED_FOR_CREATE')
            old, generation = (), 1
            target_id = 'group-' + digest({'batch_id': base['batch_id'], 'ordinal': len(children)})
        count = min(MAX_MEMBERS - len(old), len(queue))
        members = old + tuple(queue[:count])
        queue = queue[count:]
        children.append(_child(base, len(children), target_id, generation, source, members))
    completeness = _coverage(children, articles, inherited)
    caps = {'draft_get_healthy': sum(c['budget']['get_healthy'] for c in children),
            'draft_get_cap': sum(c['budget']['get_cap'] for c in children),
            'draft_add': len(children),
            'draft_delete': sum(c['budget']['delete_cap'] for c in children),
            'discovery_and_qualification': 'SEPARATE_READ_GRANTS_NOT_INCLUDED',
            'new_image_uploads': 'EXACT_SERVICE_SLOT_COUNT_REQUIRED',
            'existing_image_uploads': 0, 'authority': 'NONE_LOCAL_CANDIDATE'}
    return _finish({**base, 'plan_state': 'CANDIDATE_ALLOCATED', 'reason': None,
                    'children': children, 'parent_caps': caps,
                    'membership_coverage': completeness,
                    'reservations_created': False,
                    'required_service_checks': _requirements(),
                    'preview_ready': False,
                    'required_preview_fields': ['ACCOUNT_AND_BINDING', 'SOURCE_AND_INPUT_GENERATION',
                        'CURRENT_POOL_AND_COVERAGE', 'EVERY_OLD_OBJECT_AND_ORIGIN_MAP',
                        'TARGET_ORDER_AND_MAIN_CHANGES', 'AUTHOR_AND_PUBLIC_FIELD_DIFFS',
                        'HIDDEN_SETTINGS_AND_ORIGINALITY_UNKNOWNS', 'PER_API_PER_CHILD_PER_REF_CAPS',
                        'NON_ATOMIC_AND_UNKNOWN_RISKS', 'EXACT_ONE_TIME_HUMAN_CHOICE']})


def _same_json(value, expected):
    """Exact generated JSON tree types, avoiding bool/int/float equality aliases.

    This candidate only generates null, boolean, integer, string, list and dict.
    Floats (including NaN/infinity), subclasses and non-string object keys are
    rejected rather than coerced or reflected in an exception.
    """
    kind = type(expected)
    if type(value) is not kind:
        return False
    if kind is dict:
        if len(value) != len(expected) or any(type(key) is not str for key in value):
            return False
        return value.keys() == expected.keys() and all(
            _same_json(value[key], item) for key, item in expected.items())
    if kind is list:
        return len(value) == len(expected) and all(
            _same_json(item, other) for item, other in zip(value, expected))
    if kind in (str, int, bool, type(None)):
        return value == expected
    return False


def normalize_preview(value, *, binding_sha, request_key, articles, groups, coverage, legacy=None):
    """Regenerate from service-retained typed values and emit canonical bytes.

    Exact JSON types reject boolean/numeric aliases, added fields and forged budget/digest
    changes. Regeneration is still only a pure consistency check; neither the
    candidate nor its input coverage string is a proof or execution grant.
    """
    expected = plan_batch(binding_sha, request_key, articles, groups, coverage, legacy)
    if not _same_json(value, expected):
        fail('GROUP_PREVIEW_MISMATCH')
    raw = canonical(expected).encode('utf-8')
    if len(raw) > 2 * 1024 * 1024:
        fail('GROUP_PREVIEW_BOUND')
    return raw
