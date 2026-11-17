"""Portable discovery of the existing own tools; no credentials or auto operator."""
import json
import os
from pathlib import Path
import sys
import threading
from copy import deepcopy

from .contracts import WCEError
from .own_bootstrap import Bridge, OperatorStdioServer, preflight
from .own_bootstrap_security import FLAGS, load_config
from .own_contracts import list_tools, validate


# Codex budgets the namespace instructions once per model-facing tool.
# The packaged Skill holds the shared account, authorization and retry rules.
INSTRUCTIONS = 'OpenAhoy Skill.'

PUBLICATION_DESCRIPTIONS = {
    'own.publications.current.dispatch': (
        'Publish an explicitly requested draft once without follower push. Use its original '
        'successful save attempt_id or completed merge intent_handle. Never resend UNKNOWN.'
    ),
    'own.publications.current.poll': (
        'Query WeChat for the original publication task. Polling never submits or resends.'
    ),
    'own.publications.current.status': (
        'Read the local status of the original save or publication. Does not contact WeChat.'
    ),
}


def _mcp_tools(catalog):
    """Publish MCP object roots without changing frozen internal authority specs.

    Every existing union branch is already a closed object. Codex App discovery
    also requires the explicit root type; adding that redundant assertion here
    retains the original alternatives, validation and authorization hashes.
    """
    from .own_branding import host_icons

    rows = deepcopy(catalog)
    for row in rows:
        if row['name'] == 'wce.ui.show_management':
            # Keep the legacy model tool as plain status, with UI reserved for
            # the explicit native thread and global entrypoints.
            row.get('_meta', {}).get('ui', {}).pop('resourceUri', None)
        if row['name'] == 'wce.settings.manage':
            row['icons'] = list(host_icons())
        spec = row.get('inputSchema', {})
        if 'type' not in spec and spec.get('oneOf'):
            if not all(branch.get('type') == 'object' for branch in spec['oneOf']):
                raise ValueError('MCP_INPUT_OBJECT_REQUIRED')
            spec['type'] = 'object'
        if row.get('description', '').startswith('Select one human-enabled personal connection. Explicit user-requested images and drafts only;'):
            # The old generic paragraph repeats the same workflow guidance for
            # every legacy tool, including ordinary-publication tools. Keep the
            # complete workflow in the packaged Skill, not each budgeted spec.
            row['description'] = 'Use the enabled account and original IDs. Never resend UNKNOWN.'
        if row['name'] in PUBLICATION_DESCRIPTIONS:
            row['description'] = PUBLICATION_DESCRIPTIONS[row['name']]
    return rows


def _server_info():
    """Report the installed package or the source-tree package template."""
    root=Path(__file__).resolve().parents[1]
    manifest=root/'plugin.json'
    if not os.path.lexists(manifest):
        manifest=root/'integrations'/'codex'/'plugin.json'
    if manifest.is_symlink():
        raise ValueError('Invalid plugin identity metadata')
    metadata=json.loads(manifest.read_bytes())
    name,version=metadata.get('name'),metadata.get('version')
    if name!='wechat-ecosystem' or type(version) is not str or not version:
        raise ValueError('Invalid plugin identity metadata')
    return {'name':name,'title':'OpenAhoy','version':version}


def _discovery_info(router):
    """Non-secret server declarations; never host availability or permission."""
    from .service import digest
    catalog = _mcp_tools(router.list_tools())
    return {'state': 'AVAILABLE', 'server_info': _server_info(),
        'declared_tool_count': len(catalog),
        'descriptor_sha256': digest(sorted(catalog, key=lambda row: row['name'])),
        'tools': [{'name': row['name'], 'declared_visibility':
                   row.get('_meta', {}).get('ui', {}).get('visibility', ['model', 'app'])}
                  for row in catalog],
        'host_model_exposure': 'NOT_OBSERVED_BY_SERVER',
        'platform_permission': 'NOT_VERIFIED'}


def _tools_list_observation(message, reply):
    """Observe a real discovery response, without reflecting request data.

    This records the reply prepared by dispatch in this server instance, not
    proof that the host received or selected it. No IDs, metadata, arguments,
    schemas, credentials or platform data are retained.
    """
    from .service import digest
    params = message.get('params', {})
    cursor_present = type(params) is dict and 'cursor' in params
    catalog = reply.get('result', {}).get('tools') if type(reply.get('result')) is dict else None
    if type(catalog) is list:
        visible = [row for row in catalog
            if 'model' in row.get('_meta', {}).get('ui', {}).get('visibility', ['model', 'app'])]
        return {'state': 'SUCCESS_REPLY_PREPARED',
            'declared_tool_count': len(catalog),
            'model_visible_declaration_count': len(visible),
            'app_only_declaration_count': len(catalog) - len(visible),
            'descriptor_sha256': digest(sorted(catalog, key=lambda row: row['name'])),
            'raw_name_order_sha256': digest([row['name'] for row in catalog]),
            'cursor_parameter_present': cursor_present,
            'host_receipt_and_selection': 'NOT_OBSERVED_BY_SERVER'}
    error = reply.get('error')
    if type(error) is dict and type(error.get('code')) is int:
        return {'state': 'ERROR_REPLY_PREPARED', 'rpc_error_code': error['code'],
            'cursor_parameter_present': cursor_present}
    return {'state': 'NO_TOOLS_LIST_RESULT'}


class PortableRouter:
    prepared = None
    own = True

    def list_tools(self):
        return list_tools()

    def evidence(self):
        return FLAGS | {'runtime': 'own_account_portable_bridge'}

    def call(self, name, arguments):
        validate(name, arguments)
        profile = os.environ.get('WCE_PROFILE_PATH')
        if not profile:
            if name == 'own.preflight':
                return preflight() | {'runtime': 'own_account_portable_bridge'}
            raise WCEError('BOOTSTRAP_CONFIG_REQUIRED')
        path = Path(profile).expanduser()
        if not path.is_absolute():
            raise WCEError('BOOTSTRAP_INVALID_CONFIG')
        try:
            connection = Bridge(load_config(path))
        except WCEError as error:
            if name != 'own.preflight':
                raise
            return self.evidence() | {'configured': False, 'preflight_ready': False,
                'missing': [error.code, 'human_owned_operator_and_current_approval']}
        try:
            return connection.call(name, arguments)
        finally:
            connection.close()


def main():
    """Use the normal per-connection service without requiring a Group catalog."""
    # Keep legacy profile selection out of the native entry. An explicit
    # package launcher avoids the separate fixed Group default constructor.
    from .own_connection_tools import ConnectionRouter
    launcher = Path(__file__).resolve().parents[1] / 'scripts' / 'wce_connection.py'
    PersonalStdioServer(ConnectionRouter(launcher=launcher)).serve(sys.stdin.buffer, sys.stdout.buffer)


def group_main():
    """Business entry: only the original authenticated, current Group catalog."""
    if os.environ.get('WCE_PROFILE_PATH'):
        raise WCEError('BASE_DOMAIN_PROFILE_UNSUPPORTED')
    from .group_host_external_loader import catalog_rows
    catalog_rows()
    from .own_connection_tools import ConnectionRouter
    PersonalStdioServer(ConnectionRouter()).serve(sys.stdin.buffer, sys.stdout.buffer)


class PersonalStdioServer(OperatorStdioServer):
    def _charge(self, now):
        # The stdin loop already provides serial backpressure; normal account
        # calls retain broker/SQLite locks, deadlines, revocation and original
        # intent checks. There is no client-side burst or lifetime usage quota.
        return None

    def __init__(self, router, *args, settings_manager=None, **kwargs):
        from .own_settings_protocol import DisplayNameRouter, SettingsRouter
        from .x_protocol import XPlatformRouter
        from .xhs_protocol import XHSRouter
        from .own_updates_protocol import UpdateRouter
        from .project_context_protocol import ProjectContextRouter
        from .content_templates_protocol import TemplateRouter
        from .support_protocol import SupportRouter, LOCAL_ONLY_TOOLS
        from .current_draft_management_protocol import DraftManagementRouter
        from .video_protocol import VideoRouter
        from .own_storage_adoption_protocol import AdoptionRouter
        self._inline_open_lock = threading.Lock()
        self._last_tools_list_observation = {'state': 'NOT_OBSERVED_IN_THIS_SERVER'}
        self._management_resources = {}
        support=SupportRouter(TemplateRouter(ProjectContextRouter(UpdateRouter(XHSRouter(XPlatformRouter(DisplayNameRouter(SettingsRouter(router, settings_manager))))), registry=router.registry), registry=router.registry), registry=router.registry, instrument=False)
        managed=AdoptionRouter(DraftManagementRouter(VideoRouter(support, router.registry),
            registry=router.registry, launcher=router.launcher), router.registry)
        self._tool_observer=support
        rows=managed.list_tools()
        support.tool_names=frozenset(t['name']for t in rows)
        support.readonly_tools=support.tool_names & LOCAL_ONLY_TOOLS
        super().__init__(managed, *args, **kwargs)

    def _tool_available(self, name, arguments):
        from .own_updates_protocol import INSTALL
        # Codex can remove the previous cache after installing the verified
        # target. This exact read remains available in the original process.
        if (name == INSTALL and isinstance(arguments, dict)
                and arguments.get('action') == 'status' and set(arguments) <= {'action', 'request_id'}):
            return name in self._tool_observer.tool_names
        return super()._tool_available(name, arguments)

    def tool_result(self,name,arguments):
        # One hook surrounds every formal tool and its MCP representation.
        from .video_protocol import AUDIO_VIDEO, WORKSPACE
        if name == WORKSPACE and arguments.get('action') in {'playback', 'preview_frames', 'intro_frames', 'audio_chunk'}:
            value = self.router.call(name, arguments)
            return {'content': [], 'structuredContent': value, 'isError': False}
        if name == AUDIO_VIDEO and 'frame_start' in arguments:
            value = self.router.call(name, arguments)
            preview = value.pop('preview')
            start = preview['start']
            frames = preview['frames']
            value['preview'] = {'start': start, 'timecodes_ms': [(start+i)*125 for i in range(len(frames))]}
            return {'content': [{'type':'text', 'text':json.dumps(value, ensure_ascii=False)}] +
                [{'type':'image', 'mimeType':'image/jpeg', 'data':frame} for frame in frames],
                'structuredContent':value, 'isError':False}
        return self._tool_observer.observe(name,lambda:super(PersonalStdioServer,self).tool_result(name,arguments),protocol_result=True)

    def resource(self, method, params):
        from .own_settings_protocol import resource
        from .own_native_management import RESOURCE, MIME
        from .own_updates_protocol import RESOURCE as UPDATE_RESOURCE
        if method == 'resources/read' and params in ({'uri': RESOURCE}, {'uri': UPDATE_RESOURCE}):
            uri = params['uri']
            if uri not in self._management_resources:
                self._management_resources[uri] = self.router.update_resource(self.router.management.resource(), uri)
            return deepcopy(self._management_resources[uri])
        if method == 'resources/list' and not params:
            return {'resources': [{'uri': UPDATE_RESOURCE, 'name': 'openahoy-management',
                'title': 'OpenAhoy · 账号管理', 'mimeType': MIME}]}
        return resource(method, params)

    def serve(self, source, destination):
        try:
            super().serve(source, destination)
        finally:
            try:
                self.router.video_credential.close()
                self.router.x.close()
                self.router.binding.close()
                self.router.manager.close()
                self.router.management.close()
            finally:
                from .own_inline_probe import close
                close()

    def dispatch(self, message):
        opening = (type(message) is dict and message.get('method') == 'tools/call'
                   and type(message.get('params')) is dict
                   and message['params'].get('name') == 'wce.settings.open')
        if not opening or 'id' not in message:
            return self._dispatch_serial_result(message)
        if not self._inline_open_lock.acquire(blocking=False):
            request_id = message.get('id')
            if type(request_id) not in {str, int}:request_id = None
            return {'jsonrpc':'2.0','id':request_id,
                    'error':{'code':-32600,'message':'Concurrent UI open refused'}}
        try:
            self.router._inline_probe_meta = None
            return self._dispatch_serial_result(message)
        finally:
            self.router._inline_probe_meta = None
            self._inline_open_lock.release()

    def _dispatch_serial_result(self, message):
        reply = super().dispatch(message)
        if (type(message) is dict and message.get('method') == 'tools/call'
                and type(message.get('params')) is dict
                and message['params'].get('name') == 'wce.settings.open'
                and type(reply) is dict and type(reply.get('result')) is dict
                and reply['result'].get('isError') is False
                and reply['result'].get('structuredContent') == {'state': 'SETTINGS_OPENED'}):
            meta, self.router._inline_probe_meta = self.router._inline_probe_meta, None
            if meta is not None:
                from .own_management_app import UIResult, take_metadata as management_metadata
                from .own_inline_probe import take_metadata
                reply['result']['_meta'] = management_metadata(meta) if type(meta) is UIResult else take_metadata(meta)
        if (type(message) is dict and message.get('method') == 'tools/list'
                and type(reply) is dict):
            if isinstance(reply.get('result'), dict) and isinstance(reply['result'].get('tools'), list):
                reply['result']['tools'] = _mcp_tools(reply['result']['tools'])
            try:self._last_tools_list_observation = _tools_list_observation(message, reply)
            except Exception:
                self._last_tools_list_observation = {'state': 'OBSERVATION_UNAVAILABLE'}
        if (type(message) is dict and message.get('method') == 'tools/call'
                and isinstance(message.get('params'), dict)
                and message['params'].get('name') == 'own.preflight'
                and isinstance(reply, dict) and isinstance(reply.get('result'), dict)):
            result = reply['result']
            value = result.get('structuredContent')
            if result.get('isError') is not True and isinstance(value, dict):
                # Server declarations are not the host's selected tool set or
                # API authority. This never calls a tool or starts a broker.
                try:
                    discovery = _discovery_info(self.router)
                    discovery['tools_list_observation'] = dict(self._last_tools_list_observation)
                except Exception:
                    discovery = {'state': 'UNAVAILABLE', 'error': 'SERVER_DISCOVERY_UNAVAILABLE'}
                value = dict(value, server_discovery=discovery)
                result['structuredContent'] = value
                result['content'] = [{'type': 'text', 'text': json.dumps(value, ensure_ascii=False)}]
        if (type(message) is dict and message.get('method') == 'tools/call'
                and isinstance(message.get('params'), dict)
                and message['params'].get('name') == 'wce.settings.add'
                and isinstance(reply, dict) and isinstance(reply.get('result'), dict)):
            result = reply['result']
            messages = {
                'SETTINGS_ADD_READY': '已打开添加公众号页面，请在安全页面填写账号信息。',
                'SETTINGS_ADD_NOT_CONFIRMED': '未能确认添加页面已显示，请检查已有的 Safari 安全页面。',
                'SETTINGS_ADD_UNKNOWN': '添加页面的切换结果尚未确认，请先检查已有安全页面，避免重复点击。',
            }
            if result.get('isError') is True:
                value = result.get('structuredContent')
                code = value.get('error') if isinstance(value, dict) else None
                if code is None:
                    content = result.get('content')
                    code = content[0].get('text') if isinstance(content, list) and content and isinstance(content[0], dict) else None
                if code in {'SETTINGS_LAUNCH_UNKNOWN', 'SETTINGS_NAVIGATION_UNKNOWN'}:
                    text = '添加页面的切换结果尚未确认，请先检查已有安全页面，避免重复点击。'
                elif code == 'SETTINGS_BUSY':
                    text = '安全页面有操作正在进行，请先完成已有页面的操作。'
                else:
                    text = '添加页面暂时无法确认，请先检查已有安全页面和进行中的操作，避免重复点击。'
            else:
                value = result.get('structuredContent')
                state = value.get('state') if isinstance(value, dict) else None
                text = messages.get(state, '添加页面的结果尚未确认，请先检查已有安全页面，避免重复点击。')
            result['content'] = [{'type': 'text', 'text': text}]
        if (type(message) is dict and message.get('method') == 'initialize'
                and reply is not None and 'result' in reply):
            from .own_branding import host_icons
            reply['result']['serverInfo'] = {**_server_info(), 'icons': list(host_icons())}
            reply['result']['capabilities'].update({'resources': {}, 'extensions': {
                'openai/settings': {'readTool': 'wce.settings.read',
                                    'updateTool': 'wce.settings.update'}}})
            reply['result']['instructions'] = INSTRUCTIONS
        if (type(message) is dict and message.get('method') == 'tools/call'
                and isinstance(message.get('params'), dict)
                and message['params'].get('name') == 'own.templates.read'
                and isinstance(reply, dict) and isinstance(reply.get('result'), dict)):
            result = reply['result']
            value = result.get('structuredContent')
            if result.get('isError') is not True and isinstance(value, dict) and value.get('state') == 'TEMPLATE_IMAGE':
                public = dict(value)
                data = public.pop('_image_base64')
                result['structuredContent'] = public
                result['content'] = [{'type': 'text', 'text': json.dumps(public, ensure_ascii=False)},
                                     {'type': 'image', 'mimeType': public['mime'], 'data': data}]
        return reply


if __name__ == '__main__':
    main()
