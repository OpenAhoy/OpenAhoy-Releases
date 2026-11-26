"""Unauthenticated endpoint checks for the official OpenAhoy setup guides."""

import json
from time import time
from urllib.error import HTTPError, URLError
from urllib.request import HTTPRedirectHandler, Request, build_opener

from .prepared_contracts import strict_validate
from .tools import schema

TOOL = 'wce.ui.openahoy.mcp.check'
ENDPOINTS = {
    'douyin': ('https://open.douyin.com/sse', 'GET'),
    'tiktok_ads': ('https://business-api.tiktok.com/open_mcp/tt-ads-mcp-layer', 'POST'),
    'meta_ads': ('https://mcp.facebook.com/ads', 'POST'),
}
SPEC = schema({'service': {'type': 'string', 'enum': list(ENDPOINTS)}})


class _NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs):
        return None


def check(service, *, opener=None):
    url, method = ENDPOINTS[service]
    body = None
    if method == 'POST':
        body = json.dumps({
            'jsonrpc': '2.0', 'id': 1, 'method': 'initialize',
            'params': {'protocolVersion': '2025-03-26', 'capabilities': {},
                       'clientInfo': {'name': 'OpenAhoy endpoint check', 'version': '1.0'}},
        }).encode('utf-8')
    headers = {'Accept': 'application/json, text/event-stream'}
    if body is not None:
        headers['Content-Type'] = 'application/json'
    req = Request(url, data=body, headers=headers, method=method)
    launch = opener or build_opener(_NoRedirect()).open
    try:
        with launch(req, timeout=4) as response:
            status = response.status
    except HTTPError as exc:
        status = exc.code
        exc.close()
    except (URLError, OSError):
        status = None
    if status == 401:
        state = 'AUTH_REQUIRED'
    elif status == 403:
        state = 'REFUSED'
    elif status == 429:
        state = 'RATE_LIMITED'
    elif status is not None and 200 <= status < 300:
        state = 'REACHABLE'
    else:
        state = 'UNAVAILABLE'
    return {'service': service, 'state': state, 'checked_at': int(time()),
            'verification': 'PUBLIC_ENDPOINT_ONLY'}


class OpenAhoyMCPStatus:
    def __init__(self, inner):
        self.inner = inner

    def __getattr__(self, name):
        return getattr(self.inner, name)

    @property
    def _inline_probe_meta(self):
        return self.inner._inline_probe_meta

    @_inline_probe_meta.setter
    def _inline_probe_meta(self, value):
        self.inner._inline_probe_meta = value

    def list_tools(self):
        return self.inner.list_tools() + [{
            'name': TOOL, 'title': '检查 OpenAhoy 官方 MCP 入口',
            'description': 'Check a fixed official public service endpoint without credentials. Does not authorize, read accounts, or invoke publishing and advertising tools.',
            'inputSchema': SPEC, 'outputSchema': {'type': 'object'},
            'annotations': {'readOnlyHint': True, 'destructiveHint': False,
                            'openWorldHint': True, 'idempotentHint': True},
            '_meta': {'ui': {'visibility': ['app']}},
        }]

    def call(self, name, arguments):
        if name != TOOL:
            return self.inner.call(name, arguments)
        strict_validate(arguments, SPEC)
        return check(arguments['service'])
