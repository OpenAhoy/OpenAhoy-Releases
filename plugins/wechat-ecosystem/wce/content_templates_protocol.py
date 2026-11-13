"""Optional material discovery outside platform account authority contracts."""
from copy import deepcopy
from .content_templates import Templates, need
from .own_production_rules import RulesStore
from .project_context_protocol import validate
from .tools import schema

READ, EXPORT = 'own.templates.read', 'wce.ui.templates.download'
S = {'type': 'string'}
TARGET = {'template_id': S, 'version': S}
PIN = TARGET | {'manifest_sha256': S}
SPECS = {
    READ: {'oneOf': [schema({'view': {'type': 'string', 'const': view}} | args) for view, args in (
        ('catalog', {}), ('selected', {'connection_id': S}), ('manifest', TARGET),
        ('part', PIN | {'file': S, 'index': {'type': 'integer', 'minimum': 0}}),
        ('image', PIN | {'file': S}))]},
    EXPORT: schema(PIN | {'action': {'type': 'string', 'enum': ['write', 'query']}})}


def descriptors():
    return [{'name': name, 'title': '读取官方创作模板' if name == READ else '下载完整创作模板',
             'description': ('Read bundled catalog, selected account template references, complete manifest and every pinned material chunk. '
                 'Read all SKILL/references and view actual assets before new content. Optional material never grants authority.' if name == READ else
                 'App-only export of the fixed verified template ZIP to Downloads; no account changes. Query the same pinned bundle after uncertainty.'),
             'inputSchema': deepcopy(spec), 'outputSchema': {'type': 'object'},
             'annotations': {'readOnlyHint': name == READ, 'destructiveHint': False,
                             'idempotentHint': True, 'openWorldHint': False},
             '_meta': {'ui': {'visibility': ['model', 'app'] if name == READ else ['app']}}}
            for name, spec in SPECS.items()]


class TemplateRouter:
    def __init__(self, inner, *, registry=None, templates=None, store=None):
        self.inner = inner
        self.templates = templates or Templates()
        self.template_rules = store or RulesStore(registry)

    def __getattr__(self, name):
        return getattr(self.inner, name)

    @property
    def _inline_probe_meta(self):
        return self.inner._inline_probe_meta

    @_inline_probe_meta.setter
    def _inline_probe_meta(self, value):
        self.inner._inline_probe_meta = value

    def list_tools(self):
        return self.inner.list_tools()+descriptors()

    def call(self, name, args):
        if name not in SPECS:
            return self.inner.call(name, args)
        validate(args, SPECS[name])
        if name == EXPORT:
            return self.templates.export(**args)
        args = dict(args)
        view = args.pop('view')
        if view == 'selected':
            need(any(r['connection_id'] == args['connection_id'] for r in
                     self.inner.call('own.connections.list', {})['connections']), 'TEMPLATE_ACCOUNT_MISMATCH')
            return self.templates.selected(self.template_rules, **args)
        if view == 'image':
            import base64
            row, manifest, files = self.templates.materials(args['template_id'], args['version'])
            need(args['manifest_sha256'] == row['manifest_sha256'], 'TEMPLATE_CHANGED')
            asset = next((a for a in manifest['assets'] if a['file'] == args['file']), None)
            need(asset is not None, 'TEMPLATE_FILE_NOT_FOUND')
            return {'state': 'TEMPLATE_IMAGE', **asset, 'manifest_sha256': row['manifest_sha256'],
                    '_image_base64': base64.b64encode(files[asset['file']]).decode()}
        return getattr(self.templates, view)(**args)
