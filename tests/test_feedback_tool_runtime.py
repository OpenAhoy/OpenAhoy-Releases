"""Regression tests for OpenAhoy's native stdio and local feedback boundaries."""
from io import BytesIO
import json
import os
from pathlib import Path
import sys
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import Mock, patch
from urllib.parse import urlsplit

PACKAGE = Path(__file__).resolve().parents[1] / 'plugins/wechat-ecosystem'
sys.path.append(str(PACKAGE))

from wce.contracts import Secret, WCEError
from wce.own_connection_policy import atomic_write
from wce.own_connection_tools import ConnectionRouter
from wce.own_plugin import PersonalStdioServer
from wce.x_api import SCOPES
from wce.x_platform import fingerprint


CONNECTION = 'x-123'
POST = {'connection_id': CONNECTION, 'post_id': '456'}
USER = {'connection_id': CONNECTION, 'username': 'fixture'}
DESCRIPTION = '读取帖子时遇到问题。'
TOKEN_JSON = '{"access_token":"synthetic-access","refresh_token":"synthetic-refresh"}'
INVALID_EXPIRY_RESPONSE = {
    'token_type': 'bearer', 'access_token': 'synthetic-new-access',
    'refresh_token': 'synthetic-new-refresh', 'scope': ' '.join(SCOPES),
    'expires_in': 10**309,
}


def request(method, identifier, params=None):
    message = {'jsonrpc': '2.0', 'method': method, 'params': params or {}}
    if identifier is not None:
        message['id'] = identifier
    return message


def tool(identifier, name, arguments):
    return request('tools/call', identifier, {'name': name, 'arguments': arguments})


class WireTests(unittest.TestCase):
    def setUp(self):
        temporary = TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.home = Path(temporary.name).resolve()
        home = patch.dict(os.environ, {'HOME': str(self.home), 'CODEX_HOME': str(self.home / '.codex')})
        home.start()
        self.addCleanup(home.stop)
        self.parent = self.home / '.wce'
        self.server = PersonalStdioServer(ConnectionRouter(
            launcher=PACKAGE / 'scripts/wce_connection.py', registry=self.parent / 'connections.json'))

    def wire(self, *messages, initialize=True):
        if initialize:
            handshake = (request('initialize', 1, {
                'protocolVersion': '2025-11-25', 'capabilities': {},
                'clientInfo': {'name': 'synthetic', 'version': '1'},
            }), request('notifications/initialized', None))
            messages = (*handshake, *messages)
        source = BytesIO(''.join(json.dumps(row) + '\n' for row in messages).encode())
        destination = BytesIO()
        self.server.serve(source, destination)
        raw = destination.getvalue()
        self.assertNotIn(b'synthetic-access', raw)
        self.assertNotIn(b'synthetic-refresh', raw)
        self.assertNotIn(b'synthetic-new-', raw)
        self.assertNotIn(os.fsencode(self.home), raw)
        return {row['id']: row for row in map(json.loads, raw.splitlines())}

    def assert_tool_error(self, row, code):
        self.assertTrue(row['result']['isError'])
        result = row['result']
        self.assertEqual(result.get('structuredContent', {}).get('error', result['content'][0]['text']), code)

    def fixture_x(self, token_json=TOKEN_JSON, expires_at=4102444800):
        self.parent.mkdir(mode=0o700)
        x = self.server.router.x
        x.root.mkdir(mode=0o700)
        client = 'fixture-client'
        scope = fingerprint(['x', client, '123'])
        metadata = x.root / 'connection.json'
        atomic_write(metadata, {'schema': 2, 'client_id': client, 'connections': {
            CONNECTION: {
                'connection_id': CONNECTION, 'profile': {'id': '123', 'name': '示例', 'username': 'fixture'},
                'scope': list(SCOPES), 'expires_at': expires_at, 'state': 'BOUND', 'credential_scope': scope,
            },
        }})
        keychain = Mock()
        keychain.load.return_value = Secret(token_json)
        x._keychain = keychain
        transport = Mock()
        transport.open.side_effect = AssertionError('Unexpected provider call')
        x.api.opener = transport
        return metadata, keychain, transport

    def test_old_contract_eviction_keeps_wire_catalog_and_preflight_signal(self):
        first = self.wire(request('tools/list', 2))[2]['result']['tools']
        original = Path.read_bytes

        def after_eviction(path):
            if path.name in ('ui-inline-account-probe-v2.json', 'plugin.json'):
                raise FileNotFoundError(path.name)
            return original(path)

        with patch.object(Path, 'read_bytes', after_eviction):
            replies = self.wire(
                request('tools/list', 3), tool(4, 'own.preflight', {}),
                tool(5, 'x.connections.list', {}), tool(6, 'x.posts.read', POST),
                tool(7, 'x.users.lookup', USER),
                tool(8, 'openahoy.feedback.preview', {'description': DESCRIPTION, 'platform': 'x'}),
                tool(9, 'x.unknown', {}), request('ping', 10), initialize=False)
        self.assertEqual(replies[3]['result']['tools'], first)
        preflight = replies[4]['result']['structuredContent']
        self.assertFalse(preflight['platform_verified'])
        discovery = preflight['server_discovery']
        self.assertEqual(discovery['state'], 'AVAILABLE')
        self.assertEqual(discovery['host_model_exposure'], 'NOT_OBSERVED_BY_SERVER')
        observation = discovery['tools_list_observation']
        self.assertEqual(observation['state'], 'SUCCESS_REPLY_PREPARED')
        self.assertEqual(observation['descriptor_sha256'], discovery['descriptor_sha256'])
        self.assertEqual(
            observation['declared_tool_count'], len(first))
        self.assertEqual(replies[5]['result']['structuredContent']['connections'], [])
        self.assert_tool_error(replies[6], 'X_CONNECTION_NOT_FOUND')
        self.assert_tool_error(replies[7], 'X_CONNECTION_NOT_FOUND')
        self.assertEqual(replies[8]['result']['structuredContent']['state'], 'PREPARED')
        self.assertEqual(replies[9]['error']['code'], -32602)
        self.assertEqual(replies[10]['result'], {})

    def test_invalid_credential_cannot_begin_refresh_or_modify_the_binding(self):
        metadata, keychain, transport = self.fixture_x('{"access_token":"synthetic-access"}', expires_at=0)
        before = metadata.read_bytes()
        replies = self.wire(tool(2, 'x.posts.read', POST), tool(3, 'x.users.lookup', USER),
                            tool(4, 'x.connections.list', {}), request('ping', 5))
        for index in (2, 3):
            self.assert_tool_error(replies[index], 'X_STORED_CREDENTIAL_INVALID')
        self.assertEqual(replies[4]['result']['structuredContent']['connections'][0]['state'], 'BOUND_IDLE')
        self.assertEqual(replies[5]['result'], {})
        self.assertEqual(metadata.read_bytes(), before)
        keychain.put.assert_not_called()
        transport.open.assert_not_called()

    def test_invalid_expiry_is_typed_and_does_not_read_keychain(self):
        _, keychain, transport = self.fixture_x(expires_at='invalid')
        replies = self.wire(tool(2, 'x.posts.read', POST), tool(3, 'x.users.lookup', USER))
        for index in (2, 3):
            self.assert_tool_error(replies[index], 'X_CONNECTION_INVALID')
        keychain.load.assert_not_called()
        transport.open.assert_not_called()

    def test_refresh_with_unrepresentable_expiry_preserves_unknown_state_and_original_credential(self):
        metadata, keychain, transport = self.fixture_x(expires_at=0)
        before = json.loads(metadata.read_bytes())
        transport.open.side_effect = [BytesIO(json.dumps(INVALID_EXPIRY_RESPONSE).encode())]
        replies = self.wire(tool(2, 'x.posts.read', POST), tool(3, 'x.users.lookup', USER),
                            tool(4, 'x.connections.list', {}), request('ping', 5))
        self.assert_tool_error(replies[2], 'X_CREDENTIAL_EXPIRY_INVALID')
        self.assert_tool_error(replies[3], 'X_REAUTHORIZATION_REQUIRED')
        self.assertEqual(replies[4]['result']['structuredContent']['connections'][0]['state'],
                         'ACTION_REQUIRED')
        self.assertEqual(replies[5]['result'], {})
        before['connections'][CONNECTION]['state'] = 'REFRESH_UNKNOWN'
        self.assertEqual(json.loads(metadata.read_bytes()), before)
        keychain.put.assert_not_called()
        self.assertEqual(keychain.load.return_value.reveal_for_adapter(), TOKEN_JSON)
        transport.open.assert_called_once()
        sent = transport.open.call_args.args[0]
        self.assertEqual((sent.get_method(), urlsplit(sent.full_url).path), ('POST', '/2/oauth2/token'))

    def test_authorization_with_unrepresentable_expiry_does_not_displace_original_binding(self):
        metadata, keychain, transport = self.fixture_x()
        before = metadata.read_bytes()
        with self.assertRaises(WCEError) as error:
            self.server.router.x._finish('fixture-client', INVALID_EXPIRY_RESPONSE,
                                         expected_connection_id=CONNECTION)
        self.assertEqual(error.exception.code, 'X_CREDENTIAL_EXPIRY_INVALID')
        self.assertEqual(metadata.read_bytes(), before)
        keychain.put.assert_not_called()
        transport.open.assert_not_called()

    def test_unencodable_provider_values_return_typed_errors_and_keep_stdio_open(self):
        _, _, transport = self.fixture_x()
        transport.open.side_effect = [
            BytesIO(br'{"data":{"id":"456","author_id":"123","text":"\ud800"}}'),
            BytesIO(b'{"data":{"id":"123","username":"fixture","ext":1e400}}'),
            BytesIO(b'{"data":null}'),
            BytesIO('{"data":{"id":"456","author_id":"123","text":"有效帖子"}}'.encode()),
        ]
        replies = self.wire(tool(2, 'x.posts.read', POST), tool(3, 'x.users.lookup', USER),
                            tool(4, 'x.users.lookup', USER), tool(5, 'x.posts.read', POST), request('ping', 6))
        for index in (2, 3):
            self.assert_tool_error(replies[index], 'X_RESPONSE_UNKNOWN')
        self.assert_tool_error(replies[4], 'X_RESPONSE_INCOMPLETE')
        self.assertEqual(replies[5]['result']['structuredContent']['result']['data']['text'], '有效帖子')
        self.assertEqual(replies[6]['result'], {})
        self.assertTrue(all(call.args[0].get_method() == 'GET' and
                            urlsplit(call.args[0].full_url).netloc == 'api.x.com'
                            for call in transport.open.call_args_list))

    def test_corrupt_feedback_store_returns_typed_error_without_overwrite(self):
        diagnostics = self.parent / 'diagnostics'
        self.parent.mkdir(mode=0o700)
        diagnostics.mkdir(mode=0o700)
        database = diagnostics / 'feedback.sqlite3'
        database.write_bytes(b'synthetic unreadable database')
        database.chmod(0o600)
        replies = self.wire(tool(2, 'openahoy.feedback.preview', {'description': DESCRIPTION, 'platform': 'x'}),
                            request('ping', 3))
        self.assert_tool_error(replies[2], 'SUPPORT_STORAGE_UNAVAILABLE')
        self.assertEqual(database.read_bytes(), b'synthetic unreadable database')
        self.assertEqual(replies[3]['result'], {})


if __name__ == '__main__':
    unittest.main()
