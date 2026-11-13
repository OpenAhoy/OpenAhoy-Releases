"""Optional software UI outside unchanged platform authority contracts."""
from copy import deepcopy

from .contracts import WCEError
from .own_updates import check

CHECK = 'wce.ui.updates.check'
RESOURCE = 'ui://wechat-ecosystem/management-updates-v1.html'


def descriptor():
    return {'name': CHECK, 'title': '检查 OpenAhoy 稳定版本',
        'description': 'App-only read of stable release tags from the fixed public OpenAhoy release repository. Uses noninteractive HTTPS Git access. No install, marketplace refresh, account/configuration or credential-file reads/writes.',
        'inputSchema': {'type': 'object', 'properties': {}, 'additionalProperties': False},
        'outputSchema': {'type': 'object'},
        'annotations': {'readOnlyHint': True, 'destructiveHint': False,
                        'openWorldHint': True, 'idempotentHint': True},
        '_meta': {'ui': {'visibility': ['app']}}}


class UpdateRouter:
    def __init__(self, inner, *, installed_version=None, checker=None):
        self.inner = inner
        if installed_version is None:
            from .own_plugin import _server_info
            installed_version = _server_info()['version']
        self.installed_version = installed_version
        self.checker = checker or check

    def __getattr__(self, name):
        return getattr(self.inner, name)

    @property
    def _inline_probe_meta(self):
        return self.inner._inline_probe_meta

    @_inline_probe_meta.setter
    def _inline_probe_meta(self, value):
        self.inner._inline_probe_meta = value

    def list_tools(self):
        from .own_native_management_contract import RESOURCE as previous
        rows = deepcopy(self.inner.list_tools())
        for row in rows:
            if row.get('_meta', {}).get('ui', {}).get('resourceUri') == previous:
                row['_meta']['ui']['resourceUri'] = RESOURCE
        return rows + [descriptor()]

    def call(self, name, arguments):
        if name != CHECK:
            return self.inner.call(name, arguments)
        if type(arguments) is not dict or arguments:
            raise WCEError('UPDATE_CHECK_INVALID_ARGUMENTS')
        return self.checker(self.installed_version)

    def update_resource(self, value, uri=RESOURCE):
        from .own_updates_ui import decorate
        return decorate(value, self.installed_version, uri)
