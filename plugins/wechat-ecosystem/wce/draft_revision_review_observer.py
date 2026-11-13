"""Fresh, exact-instance source continuation; observations never grant actions.

The sealed witness owns manifest/Case/policy authority. This module rechecks
actual source bytes, every retained record and every human pair. Attachment
paths and the four opaque envelope fields are data, never I/O or permissions.
"""
from dataclasses import asdict, replace
from hashlib import sha256
import base64
import binascii
import os
import threading
import time

from .draft_revision_native_lookup import NativeThreadLookup, valid_thread
from .draft_revision_native_source import (
    MAX_PREFIX, SourceHold, canonical, checked_guard, registration_digest,
    require, _open_source, _regular,
)
from .draft_revision_scan import RevisionScanGuard, full as full_guard
from .draft_revision_stream import read_current_prefix
from . import draft_revision_source_observer as original

HOLD = 'REVISION_SOURCE_REVIEW_HOLD'
SINGLE = 'EXACT_SINGLE_TEXT_MATERIAL'
IMAGE = 'EXACT_TEXT_LOCAL_IMAGE_NON_GRANT'
RESUME = 'GENUINE_COMPOSER_RESUME_EXACT_ORIGINAL_CASE_ONLY'
DISPOSITIONS = {
    'NON_GRANT_OTHER_ARTICLE_RESEARCH_AND_REFERENCE_IMAGE',
    'NON_GRANT_FUTURE_DRAFT_GROUPING_POLICY',
    'NON_GRANT_GROUP08_CLARIFICATION_NO_ORIGINAL_CASE_CHANGE', RESUME,
}
_EPOCH_KEY = object()
_FAILED = object()


def _sha(value):
    require(type(value) is str, HOLD)
    return sha256(value.encode('utf-8')).hexdigest()


def _domain(name, value):
    return sha256(b'WCE-R219-INVENTORY-V1\0' + name.encode('ascii')
                  + b'\0' + canonical(value)).hexdigest()


def _hex(value, length=64):
    return (type(value) is str and len(value) == length
            and all(c in '0123456789abcdef' for c in value))


class _ReviewBoundary:
    def __init__(self, review, guard):
        from .draft_revision_review import SourceReviewWitness
        from .draft_revision_gate import _ACTIVE
        require(type(review) is SourceReviewWitness
                and type(guard) is RevisionScanGuard, HOLD)
        self.review, self.guard, self.active = review, guard, _ACTIVE.get()
        self._held()
        full_guard(guard)
        require(review.check() is True, HOLD)
        self.epoch = review.epoch()
        require(_hex(self.epoch, 32), HOLD)
        self.manifest, self.asset, self.reference = review.manifest, review.asset, review.reference
        require(type(self.manifest) is dict and type(self.asset) is dict
                and type(self.reference) is dict, HOLD)
        require(set(self.reference) == {'profile', 'review_id', 'review_sha', 'manifest_sha', 'published'}
                and self.reference['profile'] == 'SOURCE_REVIEW_CONTINUATION_V1'
                and type(self.reference['published']) is bool
                and type(self.reference['review_id']) is str
                and bool(self.reference['review_id'])
                and _hex(self.reference['review_sha']) and _hex(self.reference['manifest_sha']), HOLD)
        self.snapshot = canonical([self.manifest, self.asset, self.reference])
        self.full()

    def _held(self):
        from .draft_revision_gate import _ACTIVE, RevisionExecutionGate
        active = _ACTIVE.get()
        require(active is self.active and type(active) is tuple and len(active) == 4, HOLD)
        gate = active[0]
        require(type(gate) is RevisionExecutionGate and gate._active_entry is active
                and active[1] == threading.get_ident()
                and gate.service is self.review.service is self.guard.service
                and self.guard.active is active
                and gate.deadline == self.review.deadline == self.guard.deadline
                and time.monotonic() < gate.deadline, HOLD)

    def full(self):
        self._held()
        full_guard(self.guard)
        require(self.review.check() is True and self.review.epoch() == self.epoch, HOLD)
        require(canonical([self.review.manifest, self.review.asset, self.review.reference])
                == self.snapshot, HOLD)
        self._held()


def _poison(guard):
    """Separate Gate-owned state: adapter cache clearing cannot undo failure."""
    from .draft_revision_gate import _ACTIVE, RevisionExecutionGate
    active = _ACTIVE.get()
    if (type(guard) is RevisionScanGuard and type(active) is tuple and len(active) == 4
            and type(active[0]) is RevisionExecutionGate and active[0]._active_entry is active
            and active[1] == threading.get_ident() and guard.active is active
            and guard.service is active[0].service):
        states = getattr(active[0], '_review_epoch_states', None)
        if type(states) is dict:
            states[_EPOCH_KEY] = _FAILED


class _EpochFence:
    """Generation baseline only; never reuse decoded records or observations."""
    def __init__(self, lookup, boundary):
        self.boundary = boundary
        gate = boundary.active[0]
        self.states = getattr(gate, '_review_epoch_states', None)
        require(type(self.states) is dict, HOLD)
        previous = self.states.get(_EPOCH_KEY)
        require(previous is not _FAILED, HOLD)
        descriptors = boundary.manifest['source_windows']
        require(type(descriptors) is list and len(descriptors) == 2
                and len({d['thread_id'] for d in descriptors}) == 2
                and lookup.allowed_threads == frozenset(d['thread_id'] for d in descriptors), HOLD)
        if previous is None:
            sources = []
            for descriptor in descriptors:
                boundary.full()
                fresh = lookup.locate(descriptor['thread_id'])
                source = replace(fresh, start_offset=descriptor['start_offset'],
                                 start_ordinal=descriptor['start_ordinal'],
                                 preceding_sha256=descriptor['preceding_sha256'])
                require(registration_digest(source) == descriptor['source_registration_sha256']
                        and _sha(str(source.path)) == descriptor['path_utf8_sha256']
                        and source.session_meta_sha256 == descriptor['session_meta_sha256'], HOLD)
                sources.append((source, original._current_generation(source)))
            self.state = (boundary.active, boundary.epoch, boundary.snapshot, tuple(sources))
            # All native-index/full callbacks precede the pure two-source fence.
            boundary.full()
            for source, generation in sources:
                require(original._current_generation(source) == generation,
                        'REVISION_SOURCE_CHANGED_REOBSERVE')
            self.states[_EPOCH_KEY] = self.state
        else:
            require(type(previous) is tuple and len(previous) == 4
                    and previous[0] is boundary.active and previous[1] == boundary.epoch
                    and previous[2] == boundary.snapshot, HOLD)
            self.state = previous
            for source, _ in self.state[3]:
                boundary.full()
                _source_matches(lookup, source)
            boundary.full()
        self.release()

    def generation(self, source):
        matches = [generation for registered, generation in self.state[3]
                   if registration_digest(registered) == registration_digest(source)]
        require(len(matches) == 1, HOLD)
        return matches[0]

    def release(self):
        # No guard/lookup callbacks: caller must run all full boundaries first.
        require(getattr(self.boundary.active[0], '_review_epoch_states', None) is self.states
                and self.states.get(_EPOCH_KEY) is self.state, HOLD)
        for source, generation in self.state[3]:
            require(original._current_generation(source) == generation,
                    'REVISION_SOURCE_CHANGED_REOBSERVE')


def _source_matches(lookup, source):
    actual = lookup.locate(source.thread_id)
    require((actual.source_id, actual.path, actual.device, actual.inode,
             actual.session_meta_sha256, actual.metadata_ordinal)
            == (source.source_id, source.path, source.device, source.inode,
                source.session_meta_sha256, source.metadata_ordinal),
            'REVISION_SOURCE_INDEX_CHANGED')
    return actual


def _material(manifest, window):
    require(manifest.get('schema') == 'R219_EXACT_SOURCE_REVIEW_MATERIAL_MANIFEST_V1'
            and manifest.get('authority') is False
            and manifest.get('purpose') == 'REVIEW_ONE_EXISTING_ORIGINAL_CASE_NOT_A_GRANT'
            and manifest.get('instance_profile', {}).get('name')
            == 'HOST_REVIEWED_NON_GRANT_TEXT_LOCAL_IMAGE_EXACT_V1', HOLD)
    source = window.source
    matches = [w for w in manifest['source_windows'] if w['thread_id'] == source.thread_id]
    require(len(matches) == 1, HOLD)
    bound = matches[0]
    require(bound['source_registration_sha256'] == registration_digest(source)
            and bound['path_utf8_sha256'] == _sha(str(source.path))
            and bound['session_meta_sha256'] == source.session_meta_sha256
            and bound['start_offset'] == source.start_offset
            and bound['start_ordinal'] == source.start_ordinal
            and bound['preceding_sha256'] == source.preceding_sha256
            and type(bound['prefix_bytes']) is int
            and source.start_offset < bound['prefix_bytes'] <= MAX_PREFIX
            and _hex(bound['prefix_sha256']), HOLD)
    pins = [p for group in manifest['origin_pins'] for p in group
            if p['thread_id'] == source.thread_id]
    require(pins == [asdict(p) for p in window.pins], HOLD)
    wanted = {}
    raw_refs = set()
    origin = {p.message_id: p for p in window.pins}
    for is_new, rows in ((False, manifest['old_seven_pair_evidence']),
                         (True, manifest['reviewed_new_users'])):
        for row in rows:
            if row['thread_id'] != source.thread_id:
                continue
            ident = row['message_id']
            valid_thread(ident); valid_thread(row['turn_id'])
            require(ident not in wanted and row['authority'] is False
                    and row['profile'] in {SINGLE, IMAGE}, HOLD)
            if is_new:
                require(ident not in origin and row['authorizes_new_action_or_budget'] is False
                        and row['disposition'] in DISPOSITIONS
                        and _hex(row['full_text_sha256']), HOLD)
                purpose = 'resume_same_case' if row['disposition'] == RESUME else 'reviewed_non_grant'
                checksum = row['full_text_sha256']
                require((row['profile'] == IMAGE)
                        == (row['disposition'] == 'NON_GRANT_OTHER_ARTICLE_RESEARCH_AND_REFERENCE_IMAGE'), HOLD)
            else:
                require(ident in origin and row['profile'] == SINGLE
                        and row['turn_id'] == origin[ident].turn_id, HOLD)
                purpose, checksum = origin[ident].purpose, origin[ident].text_sha256
            raw, typed = row['raw']['reference'], row['typed']['reference']
            require(raw['source_id'] == typed['source_id'] == source.source_id
                    and raw['ordinal'] < typed['ordinal']
                    and row['candidate_raw_ordinals'] == [raw['ordinal']]
                    and row['retained_identity_uses_raw_utf8_hash'] is True
                    and row['retained_complete'] is (row['profile'] == SINGLE), HOLD)
            key = canonical(raw)
            require(key not in raw_refs, HOLD)
            raw_refs.add(key)
            wanted[ident] = (row, purpose, checksum)
    require(set(origin) <= set(wanted) and bool(wanted), HOLD)
    bindings = {}
    for row in manifest['all_retained_record_bindings']:
        ref = row['reference']
        if ref['source_id'] != source.source_id:
            continue
        key = canonical(ref)
        require(key not in bindings and source.start_offset <= ref['byte_start']
                < ref['byte_end'] <= bound['prefix_bytes']
                and _hex(ref['raw_line_sha256'])
                and _hex(row['payload_canonical_sha256']), HOLD)
        bindings[key] = row
    require(len(bindings) == bound['retained_records'], HOLD)
    for row, _, _ in wanted.values():
        for kind in ('raw', 'typed'):
            require(bindings.get(canonical(row[kind]['reference'])) == row[kind], HOLD)
    return bound, wanted, bindings


def _reviewed_prefix(source, bound, guard, generation):
    """Hash original bytes from zero, not canonical JSON or a retained subset."""
    fd, parent, name, descriptors, chain = _open_source(source)
    try:
        _regular(os.fstat(fd), source)
        require(os.fstat(fd).st_size >= bound['prefix_bytes'], HOLD)
        remaining = bound['prefix_bytes']; checksum = sha256(); last = b''
        while remaining:
            checked_guard(guard)
            raw = os.read(fd, min(2 * 1024 * 1024, remaining))
            require(bool(raw), HOLD)
            checksum.update(raw); remaining -= len(raw); last = raw[-1:]
            checked_guard(guard)
        require(last == b'\n' and checksum.hexdigest() == bound['prefix_sha256'], HOLD)
        opened = os.fstat(fd); entry = os.stat(name, dir_fd=parent, follow_symlinks=False)
        _regular(opened, source); _regular(entry, source)
        require(original._generation(opened) == original._generation(entry) == generation['file']
                and original._ancestors(chain) == generation['ancestors'],
                'REVISION_SOURCE_CHANGED_REOBSERVE')
    finally:
        for descriptor in reversed(descriptors):
            os.close(descriptor)


def _record_binding(record, binding):
    row = record.value
    require(record.reference() == binding['reference']
            and sha256(record.raw_line).hexdigest() == binding['reference']['raw_line_sha256']
            and _domain('record-payload', row['payload']) == binding['payload_canonical_sha256'], HOLD)


def _image_response(record, expected, asset):
    row = record.value; data = row['payload']; meta = row.get('metadata')
    require(set(data) == {'type', 'id', 'role', 'content', 'internal_chat_message_metadata_passthrough'}
            and data['type'] == 'message' and data['role'] == 'user' and type(data['id']) is str, HOLD)
    passthrough = data['internal_chat_message_metadata_passthrough']
    require(type(passthrough) is dict
            and set(passthrough) == {'content_item_metadata', 'content_item_kinds', 'create_time', 'turn_id'}
            and passthrough['turn_id'] == expected['turn_id']
            and passthrough['content_item_metadata'] == [{'provenance': {'type': 'user'}}] * 4
            and passthrough['content_item_kinds'] == ['user.text', 'user.text', 'user.image', 'user.text'], HOLD)
    require(type(meta) is dict and set(meta) == {'client_authored', 'mcp_attribution', 'retained_source', 'user_input_order'}
            and (meta['client_authored'] is None or type(meta['client_authored']) is bool)
            and type(meta['mcp_attribution']) is dict and set(meta['mcp_attribution']) == {'status', 'sources'}
            and type(meta['mcp_attribution']['status']) is str, HOLD)
    retained = meta['retained_source']
    require(type(retained) is dict and set(retained) == {'complete', 'id', 'revision'}
            and retained['complete'] is False
            and retained['id'] == {'message_id': data['id'], 'turn_id': expected['turn_id'], 'role': 'user'}, HOLD)
    parts = data['content']
    require(type(parts) is list and len(parts) == 4, HOLD)
    for index in (0, 1, 3):
        part = parts[index]
        require(type(part) is dict and set(part) == {'type', 'text'}
                and part['type'] == 'input_text' and type(part['text']) is str, HOLD)
    image = parts[2]
    require(type(image) is dict and set(image) == {'type', 'image_url', 'detail'}
            and image['type'] == 'input_image' and image['detail'] == 'high'
            and type(image['image_url']) is str and parts[3]['text'] == '</image>', HOLD)
    require(asset.get('profile') == 'SUPPORTED_API_USER_ATTACHMENT_READ_V1'
            and asset.get('authority') is False and asset.get('png_signature') is True
            and asset.get('before_after_identity_equal') is True
            and asset.get('message_id') == expected['message_id']
            and asset.get('thread_id') == expected['thread_id']
            and asset.get('turn_id') == expected['turn_id']
            and type(asset.get('size')) is int and 0 < asset['size'] <= 16 * 1024 * 1024
            and _hex(asset.get('sha256')) and _hex(asset.get('logical_path_sha256')), HOLD)
    prefix = 'data:image/png;base64,'
    encoded = image['image_url']
    require(encoded.startswith(prefix) and len(encoded) == len(prefix) + 4 * ((asset['size'] + 2) // 3), HOLD)
    try:
        decoded = base64.b64decode(encoded[len(prefix):], validate=True)
    except (ValueError, binascii.Error):
        raise SourceHold(HOLD) from None
    require(len(decoded) == asset['size'] and decoded.startswith(b'\x89PNG\r\n\x1a\n')
            and sha256(decoded).hexdigest() == asset['sha256']
            and base64.b64encode(decoded).decode('ascii') == encoded[len(prefix):], HOLD)
    return {'turn_id': expected['turn_id'], 'text_sha256': _sha(parts[0]['text']),
            'record': record.reference(), 'client_authored': meta['client_authored'],
            'text': parts[0]['text'], 'open': parts[1]['text']}


def _interpret(stream, source, bound, wanted, bindings, asset, guard):
    seen = set(); seen_bindings = set(); used_raw = set()
    tasks = {}; contexts = set(); configuration_turns = set(); pending = {}; observed = []
    raw_pairs = {canonical(row['raw']['reference']): row for row, _, _ in wanted.values()}
    for record in stream.records:
        checked_guard(guard)
        ref = record.reference(); key = canonical(ref); row = record.value
        data = row['payload']; outer = row['type']
        if ref['byte_start'] < bound['prefix_bytes']:
            require(key in bindings and key not in seen_bindings, HOLD)
            _record_binding(record, bindings[key]); seen_bindings.add(key)
        if outer == 'event_msg' and data.get('type') == 'task_started':
            turn = data.get('turn_id'); valid_thread(turn); attr = data.get('turn_attribution')
            require(type(attr) is dict and attr.get('turn_id') == turn
                    and {'turn_trigger', 'parent_turn_id', 'initiating_agent_path'} <= set(attr),
                    'REVISION_SOURCE_TASK_HOLD')
            tasks[turn] = {'attribution': attr, 'record': ref}
        elif outer == 'turn_context':
            turn = data.get('turn_id'); valid_thread(turn)
            require(turn in tasks, 'REVISION_SOURCE_CONTEXT_HOLD'); contexts.add(turn)
        elif outer == 'response_item' and data.get('type') == 'message' and data.get('role') == 'user':
            pair = raw_pairs.get(key)
            if pair is not None and pair['profile'] == IMAGE:
                raw = _image_response(record, pair, asset)
            else:
                raw = original._response(record, source.thread_id, tasks)
            if raw is not None:
                if 'configuration_turn' in raw:
                    require(pair is None, HOLD)
                    configuration_turns.add(raw['configuration_turn']); continue
                require(pair is not None and key not in used_raw
                        and raw['turn_id'] == pair['turn_id']
                        and _sha(data['id']) == pair['raw_response_id_utf8_sha256']
                        and _domain('response-content-ordered', data['content'])
                        == pair['raw_ordered_content_sha256'], HOLD)
                turn = raw['turn_id']
                require(turn in tasks and turn in contexts and turn not in pending,
                        'REVISION_SOURCE_UNPAIRED_USER_HOLD')
                pending[turn] = raw
            else:
                require(pair is None, HOLD)
        elif outer == 'event_msg' and data.get('type') == 'user_message':
            raise SourceHold('REVISION_SOURCE_LEGACY_USER_HOLD')
        elif (outer == 'event_msg' and data.get('type') == 'item_completed'
              and type(data.get('item')) is dict and data['item'].get('type') == 'UserMessage'):
            item = data['item']; ident = item.get('id'); turn = data.get('turn_id')
            valid_thread(ident); valid_thread(turn)
            require(ident in wanted and ident not in seen and data.get('thread_id') == source.thread_id,
                    'REVISION_NEW_HUMAN_SOURCE_REQUIRES_REVIEW')
            pair, purpose, checksum = wanted[ident]
            require(turn == pair['turn_id'] and ref == pair['typed']['reference'], HOLD)
            content = item.get('content'); image = pair['profile'] == IMAGE
            require(type(content) is list and len(content) == (2 if image else 1)
                    and type(content[0]) is dict and set(content[0]) == {'type', 'text', 'text_elements'}
                    and content[0]['type'] == 'text' and type(content[0]['text']) is str
                    and content[0]['text_elements'] == []
                    and _domain('typed-content-ordered', content) == pair['typed_ordered_content_sha256'], HOLD)
            raw = pending.pop(turn, None)
            require(raw is not None and raw['record'] == pair['raw']['reference']
                    and _sha(content[0]['text']) == raw['text_sha256'] == checksum, HOLD)
            if image:
                local = content[1]
                require(set(item) == {'type', 'id', 'client_id', 'content'}
                        and type(local) is dict and set(local) == {'type', 'path'}
                        and local['type'] == 'local_image' and type(local['path']) is str
                        and _sha(local['path']) == asset['logical_path_sha256']
                        and raw['text'] == content[0]['text']
                        and raw['open'] == '<image name=[Image #1] path="' + local['path'] + '">', HOLD)
            task = tasks[turn]; attr = task['attribution']
            if purpose in {'initial_edit', 'resume_same_case', 'current_draft_revision'}:
                require(attr['turn_trigger'] == 'composer' and attr['parent_turn_id'] is None
                        and attr['initiating_agent_path'] is None, 'REVISION_SOURCE_COMPOSER_REQUIRED')
            observed.append({'message_id': ident, 'turn_id': turn, 'text_sha256': checksum,
                             'purpose': purpose, 'typed': ref, 'response': raw['record'],
                             'task': task['record'], 'client_authored': raw['client_authored']})
            seen.add(ident); used_raw.add(canonical(raw['record']))
        else:
            raise SourceHold(HOLD)
    require(configuration_turns <= contexts, 'REVISION_SOURCE_CONFIGURATION_CONTEXT_HOLD')
    require(not pending, 'REVISION_SOURCE_UNPAIRED_USER_HOLD')
    require(seen == set(wanted) and used_raw == set(raw_pairs)
            and seen_bindings == set(bindings), HOLD)
    return observed


def observe_reviewed_window(lookup, window, guard, review):
    """No fallback: review failure cannot select the old observer or regrant."""
    try:
        require(type(lookup) is NativeThreadLookup and type(window) is original.SourceWindow,
                'REVISION_SOURCE_BOOTSTRAP_REQUIRED')
        boundary = _ReviewBoundary(review, guard)
        epoch = _EpochFence(lookup, boundary)
        source = window.source
        bound, wanted, bindings = _material(boundary.manifest, window)
        actual = _source_matches(lookup, source)
        generation = epoch.generation(source)
        _reviewed_prefix(source, bound, guard, generation)
        boundary.full()
        stream = read_current_prefix(source, guard)
        boundary.full()
        require(stream.prefix_bytes >= bound['prefix_bytes'], HOLD)
        observed = _interpret(stream, source, bound, wanted, bindings, boundary.asset, guard)
        require(registration_digest(_source_matches(lookup, source)) == registration_digest(actual),
                'REVISION_SOURCE_INDEX_CHANGED')
        boundary.full()
        require(original._current_generation(source) == generation
                and int(generation['file'][6]) == stream.prefix_bytes,
                'REVISION_SOURCE_CHANGED_REOBSERVE')
        evidence = {'schema': 'REVISION_NATIVE_DIRECTIVE_OBSERVATION_V2', 'authority': False,
                    'source_registration_sha256': registration_digest(source), 'thread_id': source.thread_id,
                    'prefix_bytes': stream.prefix_bytes, 'prefix_sha256': stream.prefix_sha256,
                    'users': observed, 'final_stat': generation['file'][7:9], 'generation': generation,
                    'review': boundary.reference, 'gate_epoch': boundary.epoch}
        # The old seal remains host-private, not an OS security boundary.
        result = original.ObservedDirectiveSet(canonical(evidence), original._SEAL)
        boundary.full()
        # No callback follows this pure fence. Caller also releases all windows
        # together after its later artifact/policy checks.
        epoch.release()
        return result
    except BaseException as error:
        _poison(guard)
        if isinstance(error, (KeyError, TypeError, ValueError, UnicodeError, OverflowError)):
            raise SourceHold(HOLD) from None
        raise
