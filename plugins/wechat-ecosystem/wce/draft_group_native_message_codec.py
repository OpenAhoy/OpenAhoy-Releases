"""Pure tagged-protocol assistant pair facts; never source or QA authority.

Only the explicit rust-v0.164.0 subset below is supported.  Real desktop
retention/completeness, source ownership, duplicate inventory, QA adoption and
artifact binding are separate host checks.  This module performs no I/O.
The existing revision USER/config/task observer is not replaced or weakened.
"""
from hashlib import sha256
import re

from .draft_revision_native_source import Record, SourceHold, MAX_LINE, strict_json, canonical

PROFILE = 'GROUP_NATIVE_ASSISTANT_PAIR_FACTS_V1'
_MAX_INT = 2**53 - 1
_PHASES = ('commentary', 'partial_answer', 'final_answer')


def _need(condition, suffix):
    if not condition:
        raise SourceHold('GROUP_NATIVE_CODEC_' + suffix)


def _id(value):
    _need(type(value) is str and re.fullmatch('[A-Za-z0-9_-]{1,128}', value) is not None, 'ID_HOLD')
    return value


def _text(value):
    _need(type(value) is str, 'TEXT_HOLD')
    try:
        value.encode('utf-8', 'strict')
    except UnicodeError:
        raise SourceHold('GROUP_NATIVE_CODEC_TEXT_HOLD') from None
    return value


def _record(record):
    # Snapshot primitive fields before parsing, without calling caller methods.
    _need(type(record) is Record, 'RECORD_HOLD')
    sid, ordinal, start, end, checksum, raw = (record.source_id, record.ordinal,
        record.byte_start, record.byte_end, record.raw_line_sha256, record.raw_line)
    _id(sid)
    _need(all(type(v) is int and 0 <= v <= _MAX_INT for v in (ordinal, start, end)), 'RECORD_HOLD')
    _need(type(checksum) is str and re.fullmatch('[a-f0-9]{64}', checksum) is not None, 'RECORD_HOLD')
    _need(type(raw) is bytes and 0 < len(raw) <= MAX_LINE and raw.endswith(b'\n'), 'RECORD_HOLD')
    _need(end - start == len(raw) and sha256(raw).hexdigest() == checksum, 'RECORD_HOLD')
    row = strict_json(raw, maximum=MAX_LINE)
    _need(type(row) is dict and type(row.get('ordinal')) is int and row['ordinal'] == ordinal
          and type(row.get('type')) is str and type(row.get('payload')) is dict, 'RECORD_HOLD')
    ref = {'source_id': sid, 'ordinal': ordinal, 'byte_start': start,
           'byte_end': end, 'raw_line_sha256': checksum}
    return row, ref


def _phase(value):
    _need(value is None or (type(value) is str and value in _PHASES), 'PHASE_HOLD')
    return value


def pair_assistant_records(raw_record, completed_record, *, thread_id):
    """Return detached facts for one exact raw/typed pair, authority=False.

    Optional raw IDs or turn attribution which are absent cannot be guessed.
    Record adjacency, task_complete text and legacy agent_message do not pair.
    Even final_answer does not mean QA PASS, adoption or source completeness.
    """
    _need(type(thread_id) is str and re.fullmatch(
        '[a-f0-9]{8}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{12}', thread_id) is not None,
        'THREAD_HOLD')
    raw, raw_ref = _record(raw_record)
    typed, typed_ref = _record(completed_record)
    _need(raw_ref['source_id'] == typed_ref['source_id']
          and raw_ref['ordinal'] != typed_ref['ordinal']
          and (raw_ref['byte_end'] <= typed_ref['byte_start']
               or typed_ref['byte_end'] <= raw_ref['byte_start']), 'PAIR_HOLD')
    _need(raw['type'] == 'response_item' and typed['type'] == 'event_msg', 'SHAPE_HOLD')
    message, event = raw['payload'], typed['payload']
    _need(message.get('type') == 'message' and message.get('role') == 'assistant'
          and event.get('type') == 'item_completed', 'SHAPE_HOLD')
    _need(type(event.get('thread_id')) is str and event['thread_id'] == thread_id, 'THREAD_HOLD')
    turn = _id(event.get('turn_id'))
    item = event.get('item')
    _need(type(item) is dict and item.get('type') == 'AgentMessage', 'SHAPE_HOLD')
    message_id = _id(message.get('id'))
    _need(type(item.get('id')) is str and item['id'] == message_id, 'PAIR_HOLD')
    passthrough = message.get('internal_chat_message_metadata_passthrough')
    _need(type(passthrough) is dict and type(passthrough.get('turn_id')) is str
          and passthrough['turn_id'] == turn, 'TURN_HOLD')
    # Ciphertext cannot be interpreted as complete clear-text message content.
    _need(message.get('encrypted_content') is None, 'ENCRYPTED_HOLD')
    raw_parts, typed_parts = message.get('content'), item.get('content')
    _need(type(raw_parts) is list and type(typed_parts) is list
          and 0 < len(raw_parts) == len(typed_parts) <= 1024, 'CONTENT_HOLD')
    texts = []
    for left, right in zip(raw_parts, typed_parts):
        _need(type(left) is dict and type(right) is dict
              and left.get('type') == 'output_text' and right.get('type') == 'Text'
              and set(left) <= {'type', 'text', 'annotations', 'logprobs'}
              and set(right) == {'type', 'text'}, 'CONTENT_HOLD')
        for key in ('annotations', 'logprobs'):
            _need(left.get(key) is None or type(left[key]) is list, 'CONTENT_HOLD')
        first, second = _text(left.get('text')), _text(right.get('text'))
        _need(first == second, 'TEXT_MISMATCH_HOLD')
        texts.append(first)
    phase = _phase(message.get('phase'))
    _need(_phase(item.get('phase')) == phase, 'PHASE_HOLD')
    completed_at = event.get('completed_at_ms')
    _need(completed_at is None or (type(completed_at) is int and 0 <= completed_at <= _MAX_INT), 'TIME_HOLD')
    # All fields below come from actual parsed bytes but carry no truth/authority seal.
    return {'profile': PROFILE, 'authority': False, 'kind': 'ASSISTANT_PAIR_FACTS',
        'thread_id': thread_id, 'turn_id': turn, 'message_id': message_id,
        'phase': phase, 'text_parts': texts,
        'text_parts_sha256': sha256(canonical(texts)).hexdigest(),
        'completed_at_ms': completed_at, 'raw': raw_ref, 'typed': typed_ref,
        'raw_payload_sha256': sha256(canonical(message)).hexdigest(),
        'typed_payload_sha256': sha256(canonical(event)).hexdigest(),
        'retention_status': 'UNVERIFIED', 'qa_status': 'UNASSESSED'}
