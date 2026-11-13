"""Deterministic slot projection and old-intent representability, never authority.

No SQL, file, network, approval ID, Gate or source qualification is created.
The caller must validate each actual original upload/proof before supplying
facts, and revalidate them on every current/history path. Fixed-width math
checks the eventual intent budget before an actual approval exists; the real
complete intent still goes through the unchanged original reader at admission.
"""
import json

from .contracts import WCEError
from .draft_group_input_files import _plain
from .own_group_json import _snapshot, _new_binding, _manifest_fields
from .own_group_json import GROUP_BYTES, GROUP_NODES
from .local_preparation import MAX_MANIFEST_BYTES
from .prepared_draft_fixture import decode_json
from .prepared_contracts import strict_validate, DIGEST
from .service import canonical, digest
from . import documents, own_group_json
from . import own_workflow as ordinary

ERROR = 'HOLD_UPLOAD_SNAPSHOT_UNREPRESENTABLE'


def _hold():
    raise WCEError(ERROR)


def _copy(value):
    # Exact builtin validation precedes canonical/equality/key operations.
    _plain(value)
    raw = canonical(value).encode('utf-8')
    return json.loads(raw), raw


def _group_projection_fields(value):
    """Exact original eligibility tail, applied only to real known fields.

    Copied from dd0e4a62 _new_add_group_intent starting at projected=; no
    dummy approval/fence value is manufactured. Full original function stays
    unchanged and is invoked on the actual complete intent below.
    """
    projected = value['projection']
    if (type(projected) is not dict or set(projected) != {'articles'}
            or type(projected['articles']) is not list or not 2 <= len(projected['articles']) <= 8):
        return False
    from .own_draft_defaults import validate_defaults_metadata
    # Syntactic self-consistency for codec eligibility only; _step revalidates
    # this binding against its trusted historical profile and exact approval.
    checked = validate_defaults_metadata(value['article_metadata'],
        expected_binding_sha=digest(value['binding']), article_count=len(projected['articles']))
    from .own_draft_wire import reference_valid
    from .documents import safe_url
    from .editor_contracts import crop_info
    synthetic = value['binding']['source_kind'] == 'SYNTHETIC_SETUP'
    required = {'article_type', 'title', 'content', 'thumb_media_id', 'author', 'digest',
        'content_source_url', 'need_open_comment', 'only_fans_can_comment'}
    for row in projected['articles']:
        if (type(row) is not dict or set(row) not in (required, required | {'cover_info'})
                or row['article_type'] != 'news'
                or any(type(row[k]) is not str for k in required - {'need_open_comment', 'only_fans_can_comment'})
                or not row['title'].strip() or len(row['title']) > 32
                or not row['content'] or len(row['content']) >= 20000 or len(row['content'].encode()) >= 1000000
                or len(row['author']) > 16 or row['digest'] != ''
                or len(row['content_source_url']) > 1024
                or not reference_valid(row['thumb_media_id'], synthetic)
                or any(type(row[k]) is not int or row[k] != v for k, v in checked.comment_settings.items())):
            return False
        if row['content_source_url']:
            safe_url(row['content_source_url'])
        if 'cover_info' in row:
            crop_info(row['cover_info'])
    return (type(value['uploads']) is list and len(projected['articles']) <= len(value['uploads']) <= 48
        and all(_snapshot(item, synthetic) for item in value['uploads'])
        and len({item.get('id', item.get('original_step_id')) for item in value['uploads']}) == len(value['uploads']))


def _full_intent_size(known):
    # These three actual future fields are strict fixed-width ASCII by the
    # unchanged original decoder. Count their bytes; do not fabricate IDs.
    widths = {'profile_fence': 64 + 2,
              'approval_id': len('own-approval-') + 32 + 2,
              'approval_digest': 64 + 2}
    size = len(canonical(known).encode('utf-8'))
    return size + sum(1 + len(canonical(key).encode()) + 1 + width
                      for key, width in widths.items())


def _nodes(value):
    count, depth, stack = 0, 0, [(value, 1)]
    while stack:
        item, level = stack.pop()
        count += 1
        depth = max(depth, level)
        if type(item) is dict:
            stack.extend((v, level + 1) for pair in item.items() for v in pair)
        elif type(item) is list:
            stack.extend((v, level + 1) for v in item)
    return count, depth


def derive_reuse_projection(manifest, slot_facts, *, article_metadata=None):
    """Value-only D-before checks; return detached complete slot mappings.

    slot_facts is a list in manifest.assets order, each exactly
    {target_slot, mapping, snapshot}. It asserts no genuine success. Snapshot
    deduplication cannot replace the caller's per-slot original proof checks.
    """
    try:
        m, _ = _copy(manifest)
        facts, _ = _copy(slot_facts)
        metadata, _ = _copy(article_metadata)
        if (type(m) is not dict or type(m.get('schema')) is not int or m['schema'] not in (1, 2, 3)
                or set(m) != {'schema', 'binding', 'bundle_id', 'version', 'revision', 'assets',
                             'article' if m['schema'] == 1 else 'document'}
                or type(m['assets']) is not list or not 1 <= len(m['assets']) <= 48
                or not _manifest_fields(m) or not _new_binding(m['binding'])
                or type(m['revision']) is not int or m['revision'] < 1):
            _hold()
        strict_validate(m['bundle_id'], ordinary.SPECS['own.articles.read']['properties']['bundle_id'])
        strict_validate(m['version'], ordinary.SPECS['own.articles.read']['properties']['version'])
        # Use the same actual manifest shape/budget reader, without approval.
        own_group_json.read(canonical(m), digest(m))
        if m['schema'] in (2, 3):
            if documents.normalize(m['document']) != m['document']:
                _hold()
        else:
            strict_validate(m['article'], ordinary.SPECS['own.articles.prepare']['properties']['article'])
        if type(facts) is not list or len(facts) != len(m['assets']):
            _hold()
        mappings, snapshots, seen = {}, [], {}
        synthetic = m['binding']['source_kind'] == 'SYNTHETIC_SETUP'
        for asset, fact in zip(m['assets'], facts):
            if (type(fact) is not dict or set(fact) != {'target_slot', 'mapping', 'snapshot'}
                    or type(fact['target_slot']) is not str or fact['target_slot'] != asset['slot']
                    or fact['target_slot'] in mappings or type(fact['mapping']) is not dict
                    or not _snapshot(fact['snapshot'], synthetic)):
                _hold()
            slot, snapshot = fact['target_slot'], fact['snapshot']
            mappings[slot] = fact['mapping']
            key = snapshot['id'] if 'id' in snapshot else snapshot['original_step_id']
            _, raw = _copy(snapshot)
            if key in seen:
                if seen[key] != raw:
                    _hold()
            else:
                seen[key] = raw
                snapshots.append(snapshot)
        projected = ordinary.projection(m, mappings)
        count = len(projected['articles']) if 'articles' in projected else 1
        if not 1 <= count <= 8 or not count <= len(snapshots) <= 48:
            _hold()
        if metadata is not None:
            projected = ordinary._defaults_projection(projected, metadata, m['binding'])
        known = {'schema': 2 if metadata is not None else 1, 'binding': m['binding'],
                 'selector': {'bundle_id': m['bundle_id'], 'version': m['version'],
                              'content_digest': digest(m)},
                 'operation': 'add', 'slot': 'draft', 'asset': None,
                 'projection': projected, 'uploads': snapshots}
        if metadata is not None:
            known['article_metadata'] = metadata
        # Reuse the original known-field eligibility predicates to choose its
        # original capacity. Only actual approval/fence fields remain deferred.
        extended = (metadata is not None and 'articles' in projected
                    and 2 <= count <= 8 and _group_projection_fields(known))
        maximum, max_nodes = ((GROUP_BYTES, GROUP_NODES) if extended else
                              (MAX_MANIFEST_BYTES, 1024))
        actual_known = canonical(known).encode('utf-8')
        decode_json(actual_known, maximum, max_nodes=max_nodes)
        nodes, depth = _nodes(known)
        # Three missing root string fields add one key + one value each.
        if (_full_intent_size(known) > maximum or nodes + 6 > max_nodes or depth > 16):
            _hold()
        result = {'authority': False, 'mappings': mappings, 'snapshots': snapshots,
                  'projection': projected, 'intent_bytes': _full_intent_size(known),
                  'intent_maximum': maximum}
        return _copy(result)[0]
    except (WCEError, ValueError, TypeError, KeyError, UnicodeError, RecursionError, OverflowError):
        raise WCEError(ERROR) from None


def validate_reuse_intent(manifest, slot_facts, intent):
    """Actual ADD-only complete reader check; never synthesize an approval.

    Call after the genuine intent/approval exists. Historical reentry must
    reconstruct the same source facts. Does not repair archived duplicates.
    """
    try:
        manifest, _ = _copy(manifest)
        value, raw = _copy(intent)
        if (type(value) is not dict or type(value.get('schema')) is not int
                or value['schema'] not in (1, 2)
                or set(value) != {'schema', 'binding', 'profile_fence', 'selector',
                    'operation', 'slot', 'asset', 'projection', 'uploads', 'approval_id',
                    'approval_digest'} | ({'article_metadata'} if value['schema'] == 2 else set())
                or value['operation'] != 'add' or value['slot'] != 'draft' or value['asset'] is not None):
            _hold()
        derived = derive_reuse_projection(manifest, slot_facts,
                                          article_metadata=value.get('article_metadata'))
        if (value['projection'] != derived['projection'] or value['uploads'] != derived['snapshots']
                or value['binding'] != manifest['binding']
                or value['selector'] != {'bundle_id': manifest['bundle_id'], 'version': manifest['version'],
                                         'content_digest': digest(manifest)}
                or len(raw) != derived['intent_bytes']):
            _hold()
        strict_validate(value['profile_fence'], DIGEST)
        strict_validate(value['approval_digest'], DIGEST)
        import re
        if (type(value['approval_id']) is not str
                or re.fullmatch('own-approval-[a-f0-9]{32}', value['approval_id']) is None):
            _hold()
        own_group_json.read(raw.decode('utf-8'), digest(value))
        if derived['intent_maximum'] == GROUP_BYTES and not own_group_json._new_add_group_intent(value):
            _hold()
        return None
    except (WCEError, ValueError, TypeError, KeyError, UnicodeError, RecursionError, OverflowError):
        raise WCEError(ERROR) from None
