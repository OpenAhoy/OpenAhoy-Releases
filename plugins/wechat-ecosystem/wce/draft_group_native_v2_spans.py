"""Locate fixed BODY tokens only after the original complete strict parser.

This module produces integrity facts. Release kinds do not authorize Native
records; the stream interpreter derives them after its task/QA/control checks.
"""
import json

from .draft_revision_native_source import MAX_LINE, SourceHold, canonical, strict_json


def _need(ok):
    if not ok:
        raise SourceHold('GROUP_NATIVE_V2_BODY_SPAN_HOLD')


def _same(left, right):
    _need(type(left) is type(right) and canonical(left) == canonical(right))


def _paths(row, release_kind):
    _need(type(release_kind) is str)
    if release_kind == 'WHOLE_RECORD':
        return ()
    _need(type(row) is dict and type(row.get('payload')) is dict)
    data = row['payload']
    if release_kind in ('ASSISTANT_RAW_NONSELECTED', 'ASSISTANT_TYPED_NONSELECTED'):
        from .draft_group_native_source_observer import _assistant_shape
        raw_side = release_kind == 'ASSISTANT_RAW_NONSELECTED'
        _need(row.get('type') == ('response_item' if raw_side else 'event_msg'))
        if raw_side:
            _need(data.get('type') == 'message' and data.get('role') == 'assistant')
        else:
            _need(data.get('type') == 'item_completed'
                  and type(data.get('item')) is dict
                  and data['item'].get('type') == 'AgentMessage')
        _assistant_shape(data, raw_side=raw_side, loop=lambda: None)
        stem = ('payload',) if raw_side else ('payload', 'item')
        item = data if raw_side else data['item']
        return tuple(stem + ('content', i, 'text') for i in range(len(item['content'])))
    tools = {
        'FUNCTION_CALL': ('function_call', 'arguments', (str,)),
        'CUSTOM_TOOL_CALL': ('custom_tool_call', 'input', (str,)),
        'FUNCTION_RESULT': ('function_call_output', 'output', (str, list)),
        'CUSTOM_TOOL_RESULT': ('custom_tool_call_output', 'output', (str, list)),
    }
    if release_kind in tools:
        tag, key, types = tools[release_kind]
        _need(row.get('type') == 'response_item' and data.get('type') == tag
              and type(data.get(key)) in types)
        if release_kind in ('FUNCTION_CALL', 'CUSTOM_TOOL_CALL'):
            _need(type(data.get('name')) is str and type(data.get('call_id')) is str)
        else:
            _need(type(data.get('call_id')) is str if release_kind == 'CUSTOM_TOOL_RESULT'
                  else data.get('call_id') is None or type(data['call_id']) is str)
        return (('payload', key),)
    if release_kind == 'TOKEN_COUNT':
        _need(row.get('type') == 'event_msg' and data.get('type') == 'token_count'
              and set(data) <= {'type', 'info', 'rate_limits'}
              and all(data.get(k) is None or type(data[k]) is dict
                      for k in ('info', 'rate_limits')))
        return tuple(('payload', k) for k in ('info', 'rate_limits')
                     if type(data.get(k)) is dict)
    raise SourceHold('GROUP_NATIVE_V2_RELEASE_KIND_UNSUPPORTED')


def _locate(text, row, paths, loop):
    """Traverse just fixed path ancestors; stdlib locates disjoint subtrees."""
    decoder = json.JSONDecoder()
    trie = {}
    for path in paths:
        node = trie
        for key in path:
            node = node.setdefault(key, {})
        node[None] = True
    spans = []
    fields = []

    def skip(i):
        while i < len(text) and text[i] in ' \t\r\n':
            i += 1
        return i

    def pointer(path):
        return ''.join('/' + str(k).replace('~', '~0').replace('/', '~1') for k in path)

    def walk(i, expected, branch, path):
        loop()
        i = skip(i)
        if not branch or None in branch:
            decoded, end = decoder.raw_decode(text, i)
            _same(decoded, expected)
            if None in branch:
                spans.append((i, end, expected))
            else:
                fields.append([pointer(path), expected])
            return end
        if type(expected) is dict:
            _need(i < len(text) and text[i] == '{')
            i = skip(i + 1)
            seen = set()
            while i < len(text) and text[i] != '}':
                loop()
                key, end = decoder.raw_decode(text, i)
                _need(type(key) is str and key in expected and key not in seen)
                seen.add(key)
                i = skip(end)
                _need(i < len(text) and text[i] == ':')
                i = skip(walk(i + 1, expected[key], branch.get(key, {}), path + (key,)))
                _need(i < len(text))
                if text[i] != ',':
                    break
                i = skip(i + 1)
            _need(i < len(text) and text[i] == '}' and seen == set(expected))
            _need(set(branch) <= seen)
            return i + 1
        _need(type(expected) is list and i < len(text) and text[i] == '[')
        i = skip(i + 1)
        count = 0
        while i < len(text) and text[i] != ']':
            loop()
            _need(count < len(expected))
            i = skip(walk(i, expected[count], branch.get(count, {}), path + (count,)))
            count += 1
            _need(i < len(text))
            if text[i] != ',':
                break
            i = skip(i + 1)
        _need(i < len(text) and text[i] == ']' and count == len(expected))
        _need(all(type(k) is int and 0 <= k < count for k in branch))
        return i + 1

    end = walk(0, row, trie, ())
    _need(skip(end) == len(text) and len(spans) == len(paths))
    return spans, fields


def _byte_offsets(text, endpoints, loop):
    """Single forward UTF8 walk: no per-span encoding of an entire prefix."""
    result = {}
    character = byte = 0
    for end in sorted(set(endpoints) | {len(text)}):
        _need(type(end) is int and character <= end <= len(text))
        while character < end:
            loop()
            next_character = min(end, character + 4096)
            byte += len(text[character:next_character].encode('utf-8'))
            character = next_character
        result[end] = byte
    return result


def control_fragments(raw, *, release_kind='WHOLE_RECORD', _loop=None):
    """Return (drop spans, retained spans, exact fragments, retained fields).

    The original parser runs for the complete input before any BODY selection;
    each disjoint drop slice independently passes that same parser afterwards.
    """
    loop = (lambda: None) if _loop is None else _loop
    loop()
    row = strict_json(raw, maximum=MAX_LINE)
    loop()
    _need(raw.endswith(b'\n'))
    paths = _paths(row, release_kind)
    text = raw.decode('utf-8')
    try:
        char_spans, fields = _locate(text, row, paths, loop)
        offsets = _byte_offsets(text, [n for a, b, _ in char_spans for n in (a, b)], loop)
        _need(offsets[len(text)] == len(raw))
        drop = []
        last = 0
        for start, end, expected in char_spans:
            loop()
            start, end = offsets[start], offsets[end]
            _need(last <= start < end <= len(raw))
            _same(strict_json(raw[start:end], maximum=MAX_LINE), expected)
            loop()
            drop.append((start, end))
            last = end
        retained = []
        last = 0
        for start, end in drop:
            if last < start:
                retained.append((last, start))
            last = end
        if last < len(raw):
            retained.append((last, len(raw)))
        fragments = tuple(raw[a:b] for a, b in retained)
        return tuple(drop), tuple(retained), fragments, fields
    except (ValueError, UnicodeError, RecursionError, IndexError, KeyError, TypeError):
        raise SourceHold('GROUP_NATIVE_V2_BODY_SPAN_HOLD') from None


def fixed_body_spans(raw, *, release_kind='WHOLE_RECORD'):
    return control_fragments(raw, release_kind=release_kind)[0]


def required_control_bytes(raw, *, release_kind='WHOLE_RECORD'):
    return b''.join(control_fragments(raw, release_kind=release_kind)[2])
