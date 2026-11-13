"""Pure bounded decoder for original full-Group MCP replies; no transport."""
from copy import deepcopy
import json
import re

from wce.contracts import WCEError
from wce.draft_group_input_files import _plain
from wce.draft_group_contracts import canonical
from wce.document_errors import restore

MAX_FRAME = 1024 * 1024
CODE = re.compile(r'[A-Z][A-Z0-9_]{0,127}')
PROTOCOL = '2025-11-25'


def fail():
    raise WCEError('ARTICLE_CHANNEL_PROTOCOL_HOLD')


def require(value):
    if value is not True:
        fail()


def strict_json(raw):
    require(type(raw) is bytes and 0 < len(raw) <= MAX_FRAME)

    def unique(pairs):
        value = {}
        for key, item in pairs:
            if key in value:
                fail()
            value[key] = item
        return value

    try:
        value = json.loads(raw.decode('utf-8'), object_pairs_hook=unique,
            parse_constant=lambda value: fail())
        _plain(value)
        return value
    except WCEError:
        raise WCEError('ARTICLE_CHANNEL_PROTOCOL_HOLD') from None
    except (ValueError, UnicodeError, RecursionError, OverflowError):
        fail()


def response(frame, expected_id):
    require(type(frame) is bytes and frame.endswith(b'\n') and len(frame) <= MAX_FRAME
            and type(expected_id) is int and not isinstance(expected_id, bool))
    value = strict_json(frame[:-1])
    require(type(value) is dict and set(value) == {'jsonrpc', 'id', 'result'}
            and value['jsonrpc'] == '2.0' and type(value['id']) is int
            and value['id'] == expected_id and type(value['result']) is dict)
    return value['result']


def initialize_result(frame, version):
    result = response(frame, 1)
    require(type(version) is str and version == '0.4.62'
            and set(result) == {'protocolVersion', 'serverInfo', 'capabilities', 'instructions'}
            and result['protocolVersion'] == PROTOCOL
            and result['serverInfo'] == {'name': 'wechat-ecosystem', 'version': version}
            and type(result['instructions']) is str and len(result['instructions']) <= 8192)
    require(result['capabilities'] == {'tools': {}, 'resources': {}, 'extensions': {
        'openai/settings': {'readTool': 'wce.settings.read', 'updateTool': 'wce.settings.update'}}})


def tools_result(frame, expected_specs):
    result = response(frame, 2)
    require(set(result) == {'tools'} and type(result['tools']) is list
            and type(expected_specs) is dict and 0 < len(expected_specs) <= 64
            and len(result['tools']) == len(expected_specs))
    seen = set()
    for descriptor in result['tools']:
        require(type(descriptor) is dict and type(descriptor.get('name')) is str
                and descriptor['name'] in expected_specs and descriptor['name'] not in seen
                and canonical(descriptor.get('inputSchema')) == canonical(expected_specs[descriptor['name']]))
        seen.add(descriptor['name'])
    require(seen == set(expected_specs))


def tool_value(frame):
    """Return original value or fixed WCEError, never the nested MCP envelope."""
    result = response(frame, 3)
    require(set(result) == {'content', 'structuredContent', 'isError'}
            and type(result['isError']) is bool and type(result['content']) is list
            and len(result['content']) == 1 and type(result['content'][0]) is dict
            and set(result['content'][0]) == {'type', 'text'}
            and result['content'][0]['type'] == 'text'
            and type(result['content'][0]['text']) is str
            and type(result['structuredContent']) is dict)
    text, value = result['content'][0]['text'], result['structuredContent']
    if not result['isError']:
        try:
            decoded = strict_json(text.encode('utf-8'))
            require(canonical(decoded) == canonical(value))
        except (UnicodeError, ValueError, RecursionError):
            fail()
        return deepcopy(value)
    require(set(value) <= {'error', 'runtime', 'platform_ready', 'platform_verified', 'line', 'column', 'technical_rule'}
            and {'error', 'runtime', 'platform_ready', 'platform_verified'} <= set(value)
            and type(value['error']) is str and CODE.fullmatch(value['error']) is not None
            and value['runtime'] == 'personal_account_connection'
            and value['platform_ready'] is False and value['platform_verified'] is False)
    code = value['error']
    where = {key: value[key] for key in ('line', 'column', 'technical_rule') if key in value}
    require(text == code + (' ' + json.dumps(where, sort_keys=True) if where else ''))
    # Reuse original safe document-location codec, not arbitrary exception text.
    try:
        error = restore(code, where)
    except WCEError:
        fail()
    raise error


def encode_request(method, params, request_id=None):
    """Pure serializer only: caller state machine owns the one-send decision."""
    require(type(method) is str and method in {'initialize', 'notifications/initialized', 'tools/list', 'tools/call'}
            and type(params) is dict and (request_id is None or type(request_id) is int))
    value = {'jsonrpc': '2.0', 'method': method, 'params': params}
    if request_id is not None:
        value['id'] = request_id
    try:
        raw = (json.dumps(value, ensure_ascii=False, allow_nan=False) + '\n').encode('utf-8')
    except (ValueError, UnicodeError, TypeError, RecursionError, OverflowError):
        fail()
    require(len(raw) <= MAX_FRAME)
    return raw
