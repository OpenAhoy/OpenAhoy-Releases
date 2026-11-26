from io import BytesIO
import json
import unittest
from urllib.error import HTTPError, URLError

from wce.openahoy_mcp_status import ENDPOINTS, TOOL, OpenAhoyMCPStatus, check


class OpenAhoyMCPStatusTests(unittest.TestCase):
    def test_check_uses_public_endpoint_without_credentials(self):
        for service, (url, method) in ENDPOINTS.items():
            with self.subTest(service=service):
                def open_fixture(request, timeout):
                    self.assertEqual((request.full_url, request.get_method()), (url, method))
                    self.assertNotIn('Authorization', request.headers)
                    self.assertNotIn('Cookie', request.headers)
                    self.assertEqual(timeout, 4)
                    if method == 'POST':
                        self.assertEqual(json.loads(request.data)['method'], 'initialize')
                    else:
                        self.assertIsNone(request.data)
                    raise HTTPError(url, 401, 'Authorization required', {}, BytesIO(b'{}'))

                result = check(service, opener=open_fixture)
                self.assertEqual(result['state'], 'AUTH_REQUIRED')
                self.assertEqual(result['verification'], 'PUBLIC_ENDPOINT_ONLY')
                self.assertIsInstance(result['checked_at'], int)

    def test_http_failures_do_not_become_authorization_or_read_access(self):
        for status, expected in ((400, 'UNAVAILABLE'), (403, 'REFUSED'),
                                 (429, 'RATE_LIMITED'), (503, 'UNAVAILABLE')):
            with self.subTest(status=status):
                def open_fixture(request, timeout):
                    raise HTTPError(request.full_url, status, 'Fixture', {}, BytesIO(b''))

                self.assertEqual(check('douyin', opener=open_fixture)['state'], expected)

        def unresponsive(request, timeout):
            raise URLError(TimeoutError())

        self.assertEqual(check('douyin', opener=unresponsive)['state'], 'UNAVAILABLE')

    def test_tool_is_app_only_and_read_only(self):
        class EmptyRouter:
            def list_tools(self):
                return []

        descriptor, = OpenAhoyMCPStatus(EmptyRouter()).list_tools()
        self.assertEqual(descriptor['name'], TOOL)
        self.assertEqual(descriptor['_meta']['ui']['visibility'], ['app'])
        self.assertTrue(descriptor['annotations']['readOnlyHint'])
        self.assertFalse(descriptor['annotations']['destructiveHint'])
