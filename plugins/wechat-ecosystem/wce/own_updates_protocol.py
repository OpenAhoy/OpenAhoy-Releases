"""Optional software UI outside unchanged platform authority contracts."""
from copy import deepcopy
from importlib import import_module

from .contracts import WCEError
from .own_updates import check
from .own_update_install import UpdateInstaller

CHECK = 'wce.ui.updates.check'
INSTALL = 'wce.ui.updates.install'
RESOURCE = 'ui://wechat-ecosystem/management-updates-v1.html'


def descriptor():
    return {'name': CHECK, 'title': '检查 Jiusera 稳定版本',
        'description': 'App-only anonymous read of the published stable Jiusera release and its Git tag from the fixed public repository. No installation, marketplace refresh, or account access.',
        'inputSchema': {'type': 'object', 'properties': {}, 'additionalProperties': False},
        'outputSchema': {'type': 'object'},
        'annotations': {'readOnlyHint': True, 'destructiveHint': False,
                        'openWorldHint': True, 'idempotentHint': True},
        '_meta': {'ui': {'visibility': ['app']}}}


def install_descriptor():
    from .tools import schema
    return {'name': INSTALL, 'title': '立即升级 Jiusera',
            'description': 'App-only stable update explicitly initiated by the user in the Jiusera panel.',
            'inputSchema': {'type': 'object', 'oneOf': [
                schema({'action': {'type': 'string', 'const': 'status'}},
                       optional={'request_id': {'type': 'string', 'pattern': '^[0-9a-f]{32}$'}}),
                schema({'action': {'type': 'string', 'const': 'start'},
                        'version': {'type': 'string', 'maxLength': 29},
                        'revision': {'type': 'string', 'pattern': '^[0-9a-f]{40}([0-9a-f]{24})?$'}},
                       optional={'request_id': {'type': 'string', 'pattern': '^[0-9a-f]{32}$'}}),
            ]}, 'outputSchema': {'type': 'object'},
            'annotations': {'readOnlyHint': False, 'destructiveHint': False,
                            'openWorldHint': True, 'idempotentHint': True},
            '_meta': {'ui': {'visibility': ['app']}}}


class UpdateRouter:
    def __init__(self, inner, *, installed_version=None, checker=None, installer=None):
        self.inner = inner
        if installed_version is None:
            from .own_plugin import _server_info
            installed_version = _server_info()['version']
        self.installed_version = installed_version
        self.checker = checker or check
        self.installer = installer
        # A first-ever receipt read may happen after Codex prunes this
        # process's package. Load the private reader's lazy dependency now.
        import_module('.draft_group_upload_proof_reads', __package__)

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
        return rows + [descriptor(), install_descriptor()]

    def call(self, name, arguments):
        if name == INSTALL:
            from .prepared_contracts import strict_validate
            strict_validate(arguments, install_descriptor()['inputSchema'])
            installer = self.installer or UpdateInstaller(self.installed_version, getattr(self.inner, 'registry', None),
                                                         checker=self.checker)
            if arguments['action'] == 'status':
                request_id = arguments.get('request_id')
                return installer.status(request_id) if request_id is not None else installer.status()
            request_id = arguments.get('request_id')
            if request_id is None:
                return installer.start(arguments['version'], arguments['revision'])
            try:
                return installer.start(arguments['version'], arguments['revision'], request_id)
            except WCEError as error:
                if error.code in ('UPDATE_TARGET_INVALID', 'UPDATE_PLATFORM_UNSUPPORTED'):
                    return {'state': 'START_REJECTED', 'code': error.code, 'request_id': request_id}
                raise
        if name != CHECK:
            return self.inner.call(name, arguments)
        if type(arguments) is not dict or arguments:
            raise WCEError('UPDATE_CHECK_INVALID_ARGUMENTS')
        return self.checker(self.installed_version)

    def update_resource(self, value, uri=RESOURCE):
        from .own_updates_ui import decorate
        return decorate(value, self.installed_version, uri)
