"""Group bounded source/control facts; no semantic approval, seal or grant.

Actual desktop assistant retention/QA adoption and current host qualification
remain separate. Unrelated index writes are not source changes; SQL lookup is
point-in-time and its final identity fence does not exclude later row/ABA edits.
"""
from dataclasses import dataclass, field, replace
from hashlib import sha256
import math
import time

from .draft_group_input_files import decode as decode_material, _plain
from .draft_group_native_stream import (NativeStreamEntry, SourceWindow,
    observe as stream_observe, recheck as stream_recheck, _snapshot_source)
from .draft_group_native_message_codec import pair_assistant_records
from .draft_revision_native_source import (RegisteredSource, Record, SourceHold,
    MAX_SEGMENT, canonical, strict_json)
from .draft_revision_native_lookup import NativeThreadLookup, valid_thread
from .draft_revision_source_observer import _response as user_response

PROFILE = 'GROUP_CURRENT_SOURCE_OBSERVATION_V1'
PROJECTION = 'GROUP_NATIVE_RECORD_PROJECTION_V1'
_TECHNICAL_RAW = ('function_call', 'function_call_output', 'custom_tool_call', 'custom_tool_call_output')
_DISPOSITIONS = ('ORIGINAL_REQUEST', 'NON_SCOPE_CHANGE', 'INPUT_FACT', 'NON_GRANT')


def _need(condition, code):
    if not condition:
        raise SourceHold('GROUP_SOURCE_' + code)


def _hash(value):
    return type(value) is str and len(value) == 64 and all(c in '0123456789abcdef' for c in value)


def _key(ref):
    return canonical(ref)


def _sha(value):
    return sha256(canonical(value)).hexdigest()


def record_projection(record, category, fact):
    """Fixed Group digest convention; a projection/hash is never review truth."""
    _need(type(record) is Record and type(category) is str and type(fact) is dict, 'PROJECTION_INPUT')
    record = _copy_record(record)
    _plain(fact)
    row = record.value
    value = {'profile': PROJECTION, 'category': category, 'reference': record.reference(),
             'payload_sha256': _sha(row['payload']), 'fact': fact}
    return _sha(value)


def _copy_record(record):
    _need(type(record) is Record, 'RECORD_TYPE')
    # Never trust caller methods or Python frozen object identity as a seal.
    values = (record.source_id, record.ordinal, record.byte_start, record.byte_end,
              record.raw_line_sha256, record.raw_line)
    _need(type(values[0]) is str and 0 < len(values[0]) <= 128
          and all(type(x) is int and 0 <= x <= 2**53 - 1 for x in values[1:4])
          and _hash(values[4]) and type(values[5]) is bytes, 'RECORD_TYPE')
    result = Record(*values)
    row = result.value
    _need(type(row) is dict and type(row.get('ordinal')) is int and row['ordinal'] == result.ordinal
          and type(row.get('type')) is str and type(row.get('payload')) is dict, 'RECORD_TYPE')
    return result


@dataclass(frozen=True, slots=True)
class GroupSourceObservation:
    raw: bytes = field(repr=False)

    @property
    def authority(self):
        return False

    @property
    def value(self):
        # Private host facts may contain untrusted assistant/user text. Not an
        # MCP projection, executable instruction or qualification object.
        return strict_json(self.raw, maximum=MAX_SEGMENT, nodes=1000000)

    @property
    def summary(self):
        value = self.value
        return {'profile': value['profile'], 'authority': False,
                'material_sha256': value['material_sha256'],
                'semantic_scope_sha': value['semantic_scope_sha'],
                'sources': len(value['sources']), 'records': value['record_count'],
                'users': len(value['users']), 'assistant_facts': len(value['assistant_facts']),
                'technical_tail': value['technical_tail_count'],
                'qa_adoption_status': value['qa_adoption_status'],
                'retention_status': value['assistant_retention_status']}


def _material(raw, binding):
    _need(type(raw) is bytes and _hash(binding), 'MATERIAL_INPUT')
    value = decode_material('source', raw)
    _need(value['profile']=='GROUP_BATCH_NATIVE_SOURCE_REVIEW_V1' and value['schema']==1 and type(value['schema'])is int,'MATERIAL_PROFILE')
    _need(all(role['binding_sha'] == binding for role in value['role_threads']), 'ROLE_BINDING')
    role_keys = [(role['role'], role['thread_id']) for role in value['role_threads']]
    _need(len(set(role_keys)) == len(role_keys), 'ROLE_DUPLICATE')
    _need({r['thread_id'] for r in value['role_threads']}
          == {w['thread_id'] for w in value['source_windows']}, 'ROLE_WINDOW')
    for role in value['role_threads']:
        valid_thread(role['thread_id'])
    _need(all(descriptor['kind'] == 'QA' for descriptor in value['qa_sources']), 'QA_DESCRIPTOR_KIND')
    return value


def _windows(material, registrations):
    _need(type(registrations) is tuple and 0 < len(registrations) <= 4, 'REGISTRATIONS')
    sources = tuple(_snapshot_source(source) for source in registrations)
    by_id = {source.source_id: source for source in sources}
    _need(len(by_id) == len(sources), 'REGISTRATION_DUPLICATE')
    _need(set(by_id) == {window['source_id'] for window in material['source_windows']}, 'REGISTRATION_SCOPE')
    result = []
    for window in material['source_windows']:
        source = by_id[window['source_id']]
        _need(source.thread_id == window['thread_id']
              and source.device == window['device'] and source.inode == window['inode']
              and source.session_meta_sha256 == window['session_meta_sha256']
              and source.metadata_ordinal == window['metadata_ordinal']
              and sha256(str(source.path).encode()).hexdigest() == window['path_utf8_sha256'], 'REGISTRATION_BINDING')
        fixed = replace(source, start_offset=window['start_offset'], start_ordinal=window['start_ordinal'],
                        preceding_sha256=window['preceding_sha256'])
        result.append(SourceWindow(fixed, window['prefix_bytes'], window['prefix_sha256']))
    return tuple(result)


def _binding_inventory(material, windows):
    bindings = {}
    intervals = {}
    for window in windows:
        sid = window.source.source_id
        low, high = intervals.get(sid, (window.source.start_offset, window.reviewed_end))
        intervals[sid] = min(low, window.source.start_offset), max(high, window.reviewed_end)
    for binding in material['retained_bindings']:
        ref = binding['reference']; key = _key(ref)
        _need(ref['source_id'] in intervals and key not in bindings, 'INVENTORY_DUPLICATE_OR_SOURCE')
        low, high = intervals[ref['source_id']]
        _need(low <= ref['byte_start'] < ref['byte_end'] <= high, 'INVENTORY_BOUNDARY')
        bindings[key] = binding
    other = set()
    for binding in material['reviewed_other_records']:
        key = _key(binding['reference'])
        _need(key in bindings and key not in other and canonical(binding) == canonical(bindings[key])
              and binding['category'] not in ('USER_RAW', 'USER_TYPED', 'SESSION_META', 'TASK_CONTROL'), 'REVIEWED_OTHER')
        other.add(key)
    # The review inventory is complete for every observed non-USER extra.
    wanted_other = {key for key, binding in bindings.items()
                    if binding['category'] not in ('USER_RAW', 'USER_TYPED', 'SESSION_META', 'TASK_CONTROL')}
    _need(other == wanted_other, 'REVIEWED_OTHER_MISSING')
    return bindings, intervals


def _expected_pairs(material, bindings):
    raw, typed, identities = {}, {}, set()
    for pair in material['typed_raw_pairs']:
        human = pair['human']
        for value in (human['thread_id'], human['turn_id'], human['message_id']):
            valid_thread(value)
        r, t = _key(pair['raw']), _key(pair['typed'])
        identity = (human['thread_id'], human['message_id'])
        _need(pair['disposition'] in _DISPOSITIONS and r not in raw and t not in typed
              and identity not in identities and r in bindings and t in bindings
              and bindings[r]['category'] == 'USER_RAW' and bindings[t]['category'] == 'USER_TYPED', 'USER_PAIR_INVENTORY')
        raw[r] = typed[t] = pair
        identities.add(identity)
    anchored = {canonical(human) for human in material['original_user_scope']['human_refs']}
    original = {canonical(pair['human']) for pair in material['typed_raw_pairs']
                if pair['disposition'] == 'ORIGINAL_REQUEST'}
    _need(len(anchored) == len(material['original_user_scope']['human_refs']) and anchored == original,
          'ORIGINAL_REQUEST_ANCHORS')
    return raw, typed


def _technical(record, row, source, tasks, loop):
    """Only finite known tags, all payload bytes remain committed as data."""
    outer, data = row['type'], row['payload']
    kind = data.get('type')
    loop()
    if outer == 'response_item' and kind in _TECHNICAL_RAW:
        if kind in ('function_call', 'custom_tool_call'):
            _need(type(data.get('name')) is str and type(data.get('call_id')) is str
                  and type(data.get('arguments' if kind == 'function_call' else 'input')) is str,
                  'TOOL_SHAPE_UNSUPPORTED')
        else:
            _need('output' in data and type(data['output']) in (str, list)
                  and (type(data.get('call_id')) is str if kind == 'custom_tool_call_output'
                       else data.get('call_id') is None or type(data['call_id']) is str), 'TOOL_SHAPE_UNSUPPORTED')
        return 'TOOL_NON_AUTH', {'kind': kind, 'payload_sha256': _sha(data)}
    if outer == 'event_msg' and kind == 'token_count':
        _need(set(data) <= {'type', 'info', 'rate_limits'}
              and all(data.get(key) is None or type(data[key]) is dict for key in ('info', 'rate_limits')),
              'USAGE_SHAPE_UNSUPPORTED')
        return 'TASK_CONTROL', {'kind': kind, 'payload_sha256': _sha(data)}
    if outer == 'event_msg' and kind in ('task_complete', 'turn_aborted'):
        turn = data.get('turn_id')
        _need(type(turn) is str and turn in tasks, 'TERMINAL_TURN_UNPROVEN')
        if 'thread_id' in data:
            _need(data['thread_id'] == source.thread_id, 'TASK_THREAD')
        if kind == 'task_complete':
            _need(data.get('last_agent_message') is None or type(data['last_agent_message']) is str,
                  'TERMINAL_SHAPE_UNSUPPORTED')
        else:
            _need(data.get('reason') in ('interrupted', 'replaced', 'review_ended', 'budget_limited'),
                  'TERMINAL_SHAPE_UNSUPPORTED')
        _need(tasks[turn]['terminal'] is None, 'TERMINAL_DUPLICATE')
        tasks[turn]['terminal'] = record.reference()
        return 'TASK_CONTROL', {'kind': kind, 'turn_id': turn, 'payload_sha256': _sha(data)}
    raise SourceHold('GROUP_SOURCE_RECORD_KIND_UNSUPPORTED')



def _assistant_shape(data, *, raw_side, loop):
    # This is only the same finite clear-text subset as the existing pure codec.
    # Missing optional raw identity may remain unpaired data; it cannot be QA.
    item = data if raw_side else data['item']
    parts = item.get('content')
    _need(type(parts) is list and 0 < len(parts) <= 1024, 'ASSISTANT_SHAPE_UNSUPPORTED')
    for part in parts:
        loop()
        _need(type(part) is dict and part.get('type') == ('output_text' if raw_side else 'Text')
              and type(part.get('text')) is str, 'ASSISTANT_SHAPE_UNSUPPORTED')
        _need(set(part) <= {'type', 'text', 'annotations', 'logprobs'} if raw_side
              else set(part) == {'type', 'text'}, 'ASSISTANT_SHAPE_UNSUPPORTED')
        if raw_side:
            _need(all(part.get(k) is None or type(part[k]) is list for k in ('annotations', 'logprobs')),
                  'ASSISTANT_SHAPE_UNSUPPORTED')
    phase = item.get('phase')
    _need(phase is None or type(phase) is str and phase in ('commentary', 'partial_answer', 'final_answer'),
          'ASSISTANT_SHAPE_UNSUPPORTED')
    if raw_side:
        _need(data.get('encrypted_content') is None, 'ASSISTANT_SHAPE_UNSUPPORTED')
        metadata = data.get('internal_chat_message_metadata_passthrough')
        _need(metadata is None or type(metadata) is dict, 'ASSISTANT_SHAPE_UNSUPPORTED')
        ident = data.get('id')
        _need(ident is None or type(ident) is str, 'ASSISTANT_SHAPE_UNSUPPORTED')
        turn = None if metadata is None else metadata.get('turn_id')
        _need(turn is None or type(turn) is str, 'ASSISTANT_SHAPE_UNSUPPORTED')
    else:
        _need(type(item.get('id')) is str, 'ASSISTANT_SHAPE_UNSUPPORTED')
        completed = data.get('completed_at_ms')
        _need(completed is None or type(completed) is int and 0 <= completed <= 2**53 - 1,
              'ASSISTANT_SHAPE_UNSUPPORTED')


def _interpret_source(records, source, bindings, intervals, raw_pairs, typed_pairs, loop):
    facts = {}; users = []; assistants = []; assistant_raw = {}; assistant_typed = {}; unpaired = []
    assistant_ids = set(); qa_required = set()
    seen = set(); seen_users = set(); seen_raw = set(); pending = {}; tasks = {}; contexts = set(); configurations = set()
    latest = None; tail = 0
    for original in records:
        loop(); record = _copy_record(original); row = record.value; loop()
        ref = record.reference(); key = _key(ref); data = row['payload']; outer = row['type']; kind = data.get('type')
        _need(key not in seen, 'RECORD_DUPLICATE'); seen.add(key)
        _need(ref['source_id'] == source.source_id, 'RECORD_SOURCE')
        bound = bindings.get(key)
        if ref['byte_start'] < intervals[source.source_id][1]:
            _need(bound is not None, 'INVENTORY_RECORD_MISSING')
        else:
            _need(bound is None, 'INVENTORY_FUTURE_RECORD'); tail += 1
        if outer == 'session_meta':
            _need(record.ordinal == source.metadata_ordinal, 'DUPLICATE_METADATA')
            category, fact = 'SESSION_META', {'kind': 'session_meta', 'thread_id': source.thread_id,
                                             'raw_line_sha256': record.raw_line_sha256}
        elif outer == 'event_msg' and kind == 'task_started':
            turn = data.get('turn_id'); valid_thread(turn)
            _need(turn not in tasks, 'TASK_DUPLICATE')
            if 'thread_id' in data:
                _need(data['thread_id'] == source.thread_id, 'TASK_THREAD')
            attr = data.get('turn_attribution')
            _need(attr is None or type(attr) is dict, 'TASK_ATTRIBUTION')
            tasks[turn] = {'attribution': attr, 'record': ref, 'terminal': None}
            latest = turn
            category, fact = 'TASK_CONTROL', {'kind': kind, 'turn_id': turn, 'attribution_sha256': _sha(attr)}
        elif outer == 'turn_context':
            turn = data.get('turn_id'); valid_thread(turn)
            _need(turn in tasks, 'CONTEXT_TASK')
            contexts.add(turn)
            category, fact = 'TASK_CONTROL', {'kind': 'turn_context', 'turn_id': turn, 'payload_sha256': _sha(data)}
        elif outer == 'response_item' and kind == 'message' and data.get('role') == 'user':
            try:
                raw = user_response(record, source.thread_id, tasks)
            except BaseException:
                raise SourceHold('GROUP_SOURCE_USER_PROVENANCE_OR_WRAPPER') from None
            if raw is None or 'configuration_turn' in raw:
                _need(key not in raw_pairs and bound is not None, 'CONFIG_REVIEW_REQUIRED')
                if raw is not None:
                    configurations.add(raw['configuration_turn'])
                category, fact = 'CONFIG_NON_AUTH', {'kind': 'harness' if raw is None else 'agents_md',
                    'turn_id': None if raw is None else raw['configuration_turn']}
            else:
                pair = raw_pairs.get(key)
                _need(pair is not None and key not in seen_raw, 'NEW_USER_REVIEW_REQUIRED')
                human = pair['human']; turn = raw['turn_id']
                _need(human['thread_id'] == source.thread_id and turn == human['turn_id']
                      and raw['text_sha256'] == human['text_sha256'] and turn in contexts and turn in tasks
                      and turn not in pending, 'USER_RAW_BINDING')
                attr = tasks[turn]['attribution']
                _need(type(attr) is dict and attr.get('turn_id') == turn
                      and {'turn_trigger', 'parent_turn_id', 'initiating_agent_path'} <= set(attr), 'USER_TASK_ATTRIBUTION')
                pending[turn] = raw
                category, fact = 'USER_RAW', {'kind': 'USER_RAW', 'turn_id': turn,
                    'response_id': raw['response_id'], 'text_sha256': raw['text_sha256'],
                    'client_authored': raw['client_authored']}
                seen_raw.add(key)
        elif outer == 'event_msg' and kind == 'item_completed' and type(data.get('item')) is dict and data['item'].get('type') == 'UserMessage':
            pair = typed_pairs.get(key)
            _need(pair is not None, 'NEW_USER_REVIEW_REQUIRED')
            item = data['item']; human = pair['human']; turn = data.get('turn_id'); ident = item.get('id')
            valid_thread(turn); valid_thread(ident)
            _need(data.get('thread_id') == source.thread_id == human['thread_id']
                  and turn == human['turn_id'] and ident == human['message_id'] and ident not in seen_users,
                  'USER_TYPED_IDENTITY')
            content = item.get('content')
            _need(type(content) is list and len(content) == 1 and type(content[0]) is dict
                  and set(content[0]) == {'type', 'text', 'text_elements'} and content[0]['type'] == 'text'
                  and type(content[0]['text']) is str and content[0]['text_elements'] == [], 'USER_TYPED_CONTENT')
            checksum = sha256(content[0]['text'].encode()).hexdigest(); raw = pending.pop(turn, None)
            _need(raw is not None and _key(raw['record']) == _key(pair['raw'])
                  and checksum == raw['text_sha256'] == human['text_sha256'], 'USER_PAIR_MISMATCH')
            attr = tasks[turn]['attribution']
            if pair['disposition'] == 'ORIGINAL_REQUEST':
                _need(attr['turn_trigger'] == 'composer' and attr['parent_turn_id'] is None
                      and attr['initiating_agent_path'] is None, 'ORIGINAL_COMPOSER_REQUIRED')
            fact = {'kind': 'USER_TYPED', 'thread_id': source.thread_id, 'turn_id': turn,
                    'message_id': ident, 'text_sha256': checksum}
            users.append(fact | {'disposition': pair['disposition'], 'raw': raw['record'], 'typed': ref,
                'raw_response_id': raw['response_id'], 'text': content[0]['text'],
                'review_status': 'EXTERNAL_SEMANTIC_REVIEW_REQUIRED_NOT_AUTHORITY'})
            category = 'USER_TYPED'; seen_users.add(ident)
        elif outer == 'event_msg' and kind == 'user_message':
            raise SourceHold('GROUP_SOURCE_LEGACY_USER_UNSUPPORTED')
        elif (outer == 'response_item' and kind == 'message' and data.get('role') == 'assistant'
              or outer == 'event_msg' and kind == 'item_completed' and type(data.get('item')) is dict
              and data['item'].get('type') == 'AgentMessage'):
            category = 'QA_FACT' if bound is not None and bound['category'] == 'QA_FACT' else 'ASSISTANT_NON_AUTH'
            if outer == 'event_msg':
                _need(data.get('thread_id') == source.thread_id and type(data.get('turn_id')) is str
                      and data['turn_id'] in tasks and data['turn_id'] in contexts, 'ASSISTANT_THREAD_OR_CONTEXT')
            raw_side = outer == 'response_item'
            _assistant_shape(data, raw_side=raw_side, loop=loop)
            ident = data.get('id') if raw_side else data['item'].get('id')
            metadata = data.get('internal_chat_message_metadata_passthrough') if raw_side else None
            turn = metadata.get('turn_id') if type(metadata) is dict else None if raw_side else data.get('turn_id')
            if type(ident) is str and type(turn) is str:
                unique = (raw_side, ident)
                _need(unique not in assistant_ids, 'ASSISTANT_ID_DUPLICATE')
                assistant_ids.add(unique)
                target = assistant_raw if raw_side else assistant_typed
                target[(turn, ident)] = record
            else:
                _need(category != 'QA_FACT', 'QA_PAIR_UNSUPPORTED')
                unpaired.append({'reference': ref, 'reason': 'OPTIONAL_RAW_ID_OR_TURN_UNAVAILABLE',
                                 'authority': False})
            if category == 'QA_FACT':
                qa_required.add(key)
                fact = None
            else:
                fact = {'kind': 'ASSISTANT_RAW' if raw_side else 'ASSISTANT_TYPED', 'payload_sha256': _sha(data)}
        else:
            category, fact = _technical(record, row, source, tasks, loop)
        facts[key] = (record, category, fact)
        loop()
    _need(not pending and configurations <= contexts, 'USER_OR_CONFIG_INCOMPLETE')
    expected_users = {pair['human']['message_id'] for pair in typed_pairs.values()
                      if pair['human']['thread_id'] == source.thread_id}
    _need(seen_users == expected_users, 'USER_EXPECTED_MISSING')
    consumed_qa = set()
    for key in sorted(set(assistant_raw) | set(assistant_typed)):
        loop()
        raw_record, typed_record = assistant_raw.get(key), assistant_typed.get(key)
        if raw_record is None or typed_record is None:
            record = raw_record if raw_record is not None else typed_record
            _need(_key(record.reference()) not in qa_required, 'QA_PAIR_UNSUPPORTED')
            unpaired.append({'reference': record.reference(), 'reason': 'NO_SUPPORTED_SAME_ID_PAIR', 'authority': False})
            continue
        raw_key, typed_key = _key(raw_record.reference()), _key(typed_record.reference())
        is_qa = raw_key in qa_required or typed_key in qa_required
        _need(not is_qa or raw_key in qa_required and typed_key in qa_required, 'QA_PAIR_INVENTORY_INCOMPLETE')
        try:
            value = pair_assistant_records(raw_record, typed_record, thread_id=source.thread_id)
        except BaseException:
            raise SourceHold('GROUP_SOURCE_QA_PAIR_UNSUPPORTED' if is_qa else 'GROUP_SOURCE_ASSISTANT_PAIR_UNSUPPORTED') from None
        _need(value['turn_id'] in tasks and value['turn_id'] in contexts, 'QA_TASK_CONTEXT')
        checksum = _sha(value)
        if is_qa:
            for side, record in (('raw', raw_record), ('typed', typed_record)):
                facts[_key(record.reference())] = (record, 'QA_FACT', {'kind': 'QA_FACT_' + side.upper(), 'pair_sha256': checksum})
            consumed_qa.update((raw_key, typed_key))
        beyond_review = raw_record.byte_end > intervals[source.source_id][1] or typed_record.byte_end > intervals[source.source_id][1]
        assistants.append(value | {'material_category': 'QA_FACT' if is_qa else 'ASSISTANT_NON_AUTH',
            'review_status': 'UNREVIEWED_CURRENT_FACT_NOT_FOR_QA_OR_INPUT' if beyond_review else 'INVENTORY_BOUND_NOT_QA_ADOPTION'})
        loop()
    _need(consumed_qa == qa_required, 'QA_PAIR_UNSUPPORTED')
    return facts, users, assistants, tail, None if latest is None else tasks[latest] | {'turn_id': latest}, unpaired


class GroupNativeSourceObserver:
    """One bounded native observation entry, never a Group execution Gate."""
    def __init__(self, material_raw, registrations, lookups, *, binding_sha, full, loop, clock=time.time):
        self._closed = self._poisoned = self._busy = self._prepared = False
        self._cached = None
        _need(callable(full) and callable(loop) and callable(clock), 'GUARDS_REQUIRED')
        self._raw = material_raw
        self._material = _material(material_raw, binding_sha)
        self._windows = _windows(self._material, registrations)
        _need(type(lookups) is tuple and all(type(item) is NativeThreadLookup for item in lookups), 'LOOKUPS_REQUIRED')
        self._lookups = lookups
        self._full_callback, self._loop_callback, self._clock = full, loop, clock
        self._entry = NativeStreamEntry(self._full, self._loop)
        self._bindings, self._intervals = _binding_inventory(self._material, self._windows)
        self._raw_pairs, self._typed_pairs = _expected_pairs(self._material, self._bindings)
        self._check_time()

    def __enter__(self):
        return self

    def __exit__(self, *_):
        self.close()

    def _check_time(self):
        try:
            now = self._clock()
        except BaseException:
            raise SourceHold('GROUP_SOURCE_CLOCK_HOLD') from None
        _need(type(now) in (int, float) and math.isfinite(now)
              and now < self._material['expires_policy']['not_after'], 'EXPIRED')

    def _guard(self, callback):
        _need(not self._closed and not self._poisoned, 'ENTRY_CLOSED')
        self._check_time()
        try:
            accepted = callback()
        except BaseException:
            raise SourceHold('GROUP_SOURCE_GUARD_HOLD') from None
        _need(accepted is True, 'GUARD_HOLD')
        self._check_time()
        return True

    def _full(self):
        return self._guard(self._full_callback)

    def _loop(self):
        return self._guard(self._loop_callback)

    def _call(self, operation):
        try:
            _need(not self._closed and not self._poisoned and not self._busy, 'ENTRY_CLOSED_OR_REENTRANT')
            self._busy = True
            return operation()
        except BaseException as error:
            self._poisoned = True
            self.close()
            code = (error.code if type(error) is SourceHold and type(error.code) is str
                    and error.code.startswith('GROUP_SOURCE_') else 'GROUP_SOURCE_OBSERVATION_HOLD')
            raise SourceHold(code) from None
        finally:
            self._busy = False

    def _current(self, raw):
        _need(type(raw) is bytes and raw == self._raw, 'MATERIAL_CHANGED')
        self._check_time()

    def inspect(self, current_material_raw):
        def operation():
            self._prepared = False
            self._current(current_material_raw)
            streams = stream_observe(self._entry, self._windows, lookups=self._lookups)
            if self._cached is None:
                all_facts = {}; users = []; assistants = []; unpaired = []; tail = 0; controls = []; summaries = []
                for stream in streams:
                    self._full()
                    source = next(window.source for window in self._windows
                                  if window.source.source_id == stream.records[0].source_id)
                    facts, humans, qa, technical, control, unmatched = _interpret_source(stream.records, source,
                        self._bindings, self._intervals, self._raw_pairs, self._typed_pairs, self._loop)
                    all_facts.update(facts); users.extend(humans); assistants.extend(qa); tail += technical
                    unpaired.extend(unmatched)
                    controls.append({'source_id': source.source_id, 'latest_task': control})
                    summaries.append(stream.summary)
                    self._full()
                actual_reviewed = {key for key, (record, _, _) in all_facts.items()
                                   if record.byte_start < self._intervals[record.source_id][1]}
                _need(actual_reviewed == set(self._bindings), 'INVENTORY_UNUSED_BINDING')
                inventory = []
                for key, (record, category, fact) in all_facts.items():
                    self._loop()
                    if key in self._bindings:
                        binding = self._bindings[key]
                        _need(binding['category'] == category and binding['payload_canonical_sha256'] == _sha(record.value['payload'])
                              and binding['safe_projection_sha256'] == record_projection(record, category, fact), 'RECORD_BINDING_MISMATCH')
                    inventory.append({'category': category, 'reference': record.reference(),
                                      'payload_sha256': _sha(record.value['payload'])})
                value = {'profile': PROFILE, 'authority': False, 'material_sha256': sha256(self._raw).hexdigest(),
                    'semantic_scope_sha': self._material['semantic_scope_sha'], 'role_threads': self._material['role_threads'],
                    'sources': summaries, 'record_count': len(inventory), 'inventory': inventory,
                    'users': users, 'assistant_facts': assistants, 'unpaired_assistant_records': unpaired, 'controls': controls,
                    'technical_tail_count': tail, 'declared_qa_sources': self._material['qa_sources'],
                    'qa_adoption_status': 'UNPROVEN_REQUIRES_HOST_ARTIFACT_AND_ADOPTION_REVIEW',
                    'assistant_retention_status': 'UNVERIFIED', 'authority_producer': 'NONE'}
                packed = canonical(value)
                _need(len(packed) <= MAX_SEGMENT, 'FACTS_LIMIT')
                self._cached = GroupSourceObservation(packed)
                self._cached.value  # Validate detached decoding before any release.
            stream_recheck(self._entry)
            return self._cached
        return self._call(operation)

    def prepare_release(self, current_material_raw):
        # inspect performs current native rechecks even when semantic memo exists.
        result = self.inspect(current_material_raw)
        self._prepared = True
        return result

    def pure_release_fence(self):
        def operation():
            _need(self._prepared and self._cached is not None, 'RELEASE_NOT_PREPARED')
            self._entry._live()
            self._entry._pure_fence()  # Fixed internal only; no external callback.
        return self._call(operation)

    def finish(self, current_material_raw):
        result = self.prepare_release(current_material_raw)
        self.pure_release_fence()
        self.close()
        return result

    def close(self):
        self._closed = True
        self._cached = None
        if hasattr(self, '_entry'):
            self._entry.close()
