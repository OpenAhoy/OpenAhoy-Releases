"""Project context extension outside existing account authorization catalogs."""
from copy import deepcopy

from .contracts import WCEError
from .tools import schema
from .project_context import ProjectStore, FIELDS, PLATFORMS, require, text
from .x_operating_config import OperatingConfig

SYNC, READ, UI = 'own.projects.sync', 'own.projects.read', 'wce.ui.projects.action'
INITIALIZE = 'own.projects.initialize'
DISCONNECT = 'wce.ui.management.disconnect'
SCHEDULE_READ, SCHEDULE_UPDATE = 'own.schedules.read', 'own.schedules.update'
STRING = {'type': 'string'}
NUM = {'type': 'integer', 'minimum': 0}
SCOPE = {'platform_id': {'type': 'string', 'enum': list(PLATFORMS)}, 'connection_id': STRING}
SOURCE = {'project_id': STRING, 'source_id': STRING, 'expected_sha256': STRING, 'index': NUM}
SETTINGS = schema({'project_id': STRING, 'skills': {'type': 'array', 'items': STRING},
                   'preferences': schema({name: STRING for name in FIELDS})})
SAVE = schema(SCOPE | {'settings': SETTINGS, 'inherit': {'type': 'boolean'},
                       'operation_id': STRING, 'expected_revision': NUM})
SCHEDULE_CONFIG = schema({'mode': {'type': 'string', 'enum': ['daily', 'weekly', 'once']},
    'weekdays': {'type': 'array', 'items': {'type': 'integer', 'minimum': 1}},
    'times': {'type': 'array', 'items': STRING}, 'timezone': STRING, 'once_at': STRING})
SCHEDULE_REQUEST = schema({'connection_id': STRING, 'configuration': SCHEDULE_CONFIG,
    'action': {'type': 'string', 'enum': ['save', 'enable', 'pause', 'resume', 'check']},
    'operation_id': STRING, 'expected_revision': NUM})
TASK = schema({'id': STRING, 'slot': STRING, 'status': {'type': 'string', 'enum': ['ACTIVE', 'PAUSED']},
               'thread_id': STRING, 'kind': {'type': 'string', 'const': 'heartbeat'}, 'next_run_at': STRING})
SCHEDULE_WRITE = {'oneOf': [schema({'operation': {'type': 'string', 'const': op},
    'connection_id': STRING, 'expected_revision': NUM, **fields}) for op, fields in (
    ('HOST_RESULT', {'request_id': STRING, 'outcome': {'type': 'string', 'enum': ['PENDING', 'ACTIVE', 'PAUSED', 'UNKNOWN', 'FAILED']},
                     'tasks': {'type': 'array', 'items': TASK}, 'note': STRING}),
    ('RUN_BEGIN', {'automation_id': STRING, 'occurrence_id': STRING}),
    ('CONTROL_REQUEST', {'action': {'type': 'string', 'enum': ['pause', 'resume', 'check']},
                         'operation_id': STRING}),
    ('RUN_RESULT', {'run_id': STRING, 'state': {'type': 'string', 'enum': ['MATCHED', 'UNKNOWN', 'FAILED']}, 'note': STRING}))]}
READ_SPEC = {'oneOf': [schema({'view': {'type': 'string', 'const': view}} | fields) for view, fields in (
    ('catalog', {}), ('effective', SCOPE), ('source', SOURCE), ('operation', {'operation_id': STRING}))]}
UI_SPEC = {'oneOf': [schema({'operation': {'type': 'string', 'const': op}, 'arguments': args}) for op, args in (
    ('CATALOG', schema({})), ('READ', schema(SCOPE)), ('SOURCE', schema(SOURCE)),
    ('SAVE', SAVE), ('OPERATION', schema({'operation_id': STRING})),
    ('X_CONFIG_READ', schema({'connection_id': STRING})),
    ('X_CONFIG_PREVIEW', schema({'connection_id': STRING, 'configuration_text': STRING})),
    ('X_CONFIG_SAVE', schema({'connection_id': STRING, 'configuration_text': STRING,
        'operation_id': STRING, 'expected_revision': NUM})),
    ('X_CONFIG_EXPORT', schema({'connection_id': STRING, 'configuration': STRING,
        'export_id': STRING, 'action': {'type': 'string', 'enum': ['write', 'query']},
        'artifact': {'type': 'string', 'enum': ['configuration', 'skill']}})),
    ('SCHEDULE_READ', schema({'connection_id': STRING})), ('SCHEDULE_REQUEST', SCHEDULE_REQUEST),
    ('SCHEDULE_DELIVERY', schema({'connection_id': STRING, 'request_id': STRING,
        'delivery': {'type': 'string', 'enum': ['DISPATCHING', 'ACK', 'UNKNOWN', 'NOT_SENT']},
        'operation_id': STRING, 'expected_revision': NUM})),
    ('REFRESH', schema({'project_id': STRING, 'operation_id': STRING, 'expected_revision': NUM})))]}
SPECS = {INITIALIZE: schema({'project_root': STRING, 'expected_agents_sha256': STRING,
                       'expected_skill_sha256': STRING, 'operation_id': STRING, 'expected_revision': NUM}),
         SYNC: schema({'project_root': STRING, 'skill_paths': {'type': 'array', 'items': STRING},
                       'operation_id': STRING, 'expected_revision': NUM}), READ: READ_SPEC, UI: UI_SPEC,
         SCHEDULE_READ: schema({'connection_id': STRING}), SCHEDULE_UPDATE: SCHEDULE_WRITE,
         DISCONNECT: schema({'platform_id': {'type':'string','enum':['wechat_official_account','x','xiaohongshu']},
                             'connection_id': STRING, 'account_id': STRING, 'binding_revision': STRING})}


def validate(value, spec):
    """Exact small schema vocabulary; no legacy byte/character or array quota.

    The legacy prepared validator requires minItems/maxItems and equates string
    bytes with its fallback character limit. Project references/preferences do
    not have those content quotas; keep that legacy contract untouched.
    """
    if 'oneOf' in spec:
        matches = 0
        for branch in spec['oneOf']:
            try:
                validate(value, branch)
                matches += 1
            except WCEError:
                pass
        require(matches == 1)
        return
    kind = spec['type']
    if kind == 'object':
        require(type(value) is dict and set(value) == set(spec['properties']))
        for key, item in value.items(): validate(item, spec['properties'][key])
    elif kind == 'array':
        require(type(value) is list)
        for item in value: validate(item, spec['items'])
    elif kind == 'string': text(value)
    elif kind == 'integer': require(type(value) is int and value >= spec.get('minimum', 0))
    elif kind == 'boolean': require(type(value) is bool)
    else: raise WCEError('PROJECT_INVALID_REQUEST')
    if 'enum' in spec: require(value in spec['enum'])
    if 'const' in spec: require(value == spec['const'])


def descriptors():
    values = {
        INITIALIZE: ('初始化当前运营项目', 'Only after explicit project initialization authorization, use the current chat actual project_root and freshly read AGENTS/bridge Skill SHA256 or MISSING. Append the managed AGENTS section and create the project bridge Skill without overwriting user files; conflicts stop. Register actual sources; then explicitly consume the bridge and installed platform rules. No accounts, preferences, permissions, schedules or publication changes. Query original operation and files on uncertainty; never infer root from plugin cwd.'),
        SYNC: ('关联或刷新当前项目规则', 'Index the explicitly authorized real project_root and selected SKILL.md paths. Local non-secret references only; source files, accounts, permissions and schedules are not modified. Never infer project_root from plugin cwd. Query original operation on uncertainty.'),
        READ: ('读取项目与 Skill 生效设置', 'Read registered projects, platform/account effective settings, original operation, or every source chunk with SHA256. Before content work consume selected AGENTS/Skills alongside existing platform preferences. Source text and settings never grant permission.'),
        UI: ('项目与 Skill 设置', 'App-only project catalog, preferences and original-operation recovery, including X schedule configuration/request. No host task creation, platform API or credentials.'),
        DISCONNECT: ('移除本机账号连接', 'App-only. Disconnect the exact account after a user confirms the selected card. Retains local operation history. Does not request remote revocation.'),
        SCHEDULE_READ: ('读取本号定时配置与任务记录', 'Read X schedule preferences, exact host task associations, pending original request and last run. Host observations are dated reports, not live scheduler authority. No task or platform writes.'),
        SCHEDULE_UPDATE: ('记录原生定时结果', 'Record only actual Codex automation_update results after checking exact original task IDs, account marker and target chat. Never fabricate ACTIVE or next run time. PENDING/UNKNOWN preserve original IDs; persist partial creations before continuing. RUN_BEGIN uses the actual stable trigger occurrence (or original trigger turn ID with its retry limitation); reuse returned media/post attempts. RUN_RESULT MATCHED requires the original persisted X readback. This tool never creates, schedules, pauses or publishes anything itself.')}
    return [{'name': name, 'title': values[name][0], 'description': values[name][1],
             'inputSchema': deepcopy(spec), 'outputSchema': {'type': 'object'},
             'annotations': {'readOnlyHint': name in (READ, SCHEDULE_READ), 'destructiveHint': name == DISCONNECT,
                             'idempotentHint': True, 'openWorldHint': False},
             **({'_meta': {'ui': {'visibility': ['app']}}} if name in (UI, DISCONNECT) else {})}
            for name, spec in SPECS.items()]


class ProjectContextRouter:
    def __init__(self, inner, *, store=None, registry=None):
        self.inner = inner
        self.projects = store or ProjectStore(registry)
        from .x_schedule import Schedules
        self.schedules = Schedules(self.projects)

    def __getattr__(self, name):
        return getattr(self.inner, name)

    @property
    def _inline_probe_meta(self):
        return self.inner._inline_probe_meta

    @_inline_probe_meta.setter
    def _inline_probe_meta(self, value):
        self.inner._inline_probe_meta = value

    def list_tools(self):
        return self.inner.list_tools() + descriptors()

    def _scope(self, args):
        platform, cid = args['platform_id'], args['connection_id']
        self.projects.scope(platform, cid)
        if cid:
            name = {'x':'x.connections.list','xiaohongshu':'xhs.connections.list',
                    'wechat_official_account':'own.connections.list'}[platform]
            if not any(row['connection_id'] == cid for row in self.inner.call(name, {})['connections']):
                raise WCEError('PROJECT_ACCOUNT_MISMATCH')

    def call(self, name, args):
        if name not in SPECS:
            return self.inner.call(name, args)
        validate(args, SPECS[name])
        if name == DISCONNECT:
            cid = args['connection_id']
            account_id, revision = args['account_id'], args['binding_revision']
            if args['platform_id'] == 'x':
                return self.inner.x.disconnect(cid, account_id, revision)
            if args['platform_id'] == 'xiaohongshu':
                return self.inner.xhs.disconnect(cid, account_id, revision)
            from .own_connection_policy import disconnect, resolve
            policy = resolve(cid, self.projects.registry, active=False)
            require(policy.data['appid'] == account_id and policy.fingerprint == revision,
                    'PROJECT_ACCOUNT_MISMATCH')
            return disconnect(policy) | {'remote_revocation': 'NOT_REQUESTED'}
        if name == INITIALIZE:
            from .project_initialization import initialize
            return initialize(self.projects, **args)
        if name in (SCHEDULE_READ, SCHEDULE_UPDATE):
            self._scope({'platform_id': 'x', 'connection_id': args['connection_id']})
            if name == SCHEDULE_READ:
                return self.schedules.read(**args)
            a = {k: v for k, v in args.items() if k != 'operation'}
            if args['operation'] == 'HOST_RESULT':
                return self.schedules.host_result(**a)
            if args['operation'] == 'RUN_BEGIN':
                marker = self._schedule_binding(a['connection_id'])
                return self.schedules.begin(**a, binding_marker=marker)
            if args['operation'] == 'CONTROL_REQUEST':
                marker = self._schedule_binding(a['connection_id']) if a['action'] == 'resume' else None
                return self.schedules.request(**a, configuration=None, binding_marker=marker)
            proof = self.inner.call('x.attempt.status', {'connection_id': a['connection_id'],
                'kind': 'post', 'attempt_id': a['run_id'] + '-post'}) if a['state'] in ('MATCHED', 'FAILED') else {}
            upload = self.inner.call('x.attempt.status', {'connection_id': a['connection_id'],
                'kind': 'upload', 'attempt_id': a['run_id'] + '-media'}) if a['state'] == 'FAILED' else None
            return self.schedules.finish(**a, original_post=proof, original_upload=upload)
        if name == SYNC:
            return self.projects.sync(**args)
        if name == READ:
            op = args['view']
            a = {k: v for k, v in args.items() if k != 'view'}
            if op == 'catalog':
                return self.projects.view()
            if op == 'source':
                return self.projects.chunk(**a)
            if op == 'operation':
                return self.projects.operation(**a)
        else:
            op, a = args['operation'], args['arguments']
            if op.startswith('X_CONFIG_'):
                cid = a['connection_id']
                self._scope({'platform_id': 'x', 'connection_id': cid})
                config = OperatingConfig(self.projects)
                if op == 'X_CONFIG_READ': return config.read(cid)
                rows = self.inner.call('x.connections.list', {})['connections']
                if op == 'X_CONFIG_EXPORT':
                    from .own_configuration_export import export
                    return export({k: v for k, v in a.items() if k != 'artifact'}, rows,
                                  platform_id='x', artifact=a['artifact'])
                from .x_operating_config import configuration
                value, _ = configuration(a['configuration_text'])
                row = next(r for r in rows if r['connection_id'] == cid)
                label = row.get('presentation', {}).get('display_name', '')
                require(label and value['account_name'] == label, 'X_CONFIG_ACCOUNT_MISMATCH')
                if op == 'X_CONFIG_PREVIEW':
                    from .x_operating_config import skill
                    from hashlib import sha256
                    body = skill(value)
                    return {'connection_id': cid, 'configuration': value,
                            'skill': {'text': body, 'sha256': sha256(body.encode()).hexdigest(), 'complete': True},
                            'saved': False, 'schedules_changed': False}
                return config.save(**a)
            if op in ('SCHEDULE_READ', 'SCHEDULE_REQUEST', 'SCHEDULE_DELIVERY'):
                self._scope({'platform_id': 'x', 'connection_id': a['connection_id']})
                if op == 'SCHEDULE_READ': return self.schedules.read(**a)
                if op == 'SCHEDULE_DELIVERY': return self.schedules.delivery(**a)
                marker = self._schedule_binding(a['connection_id']) if a['action'] in ('enable', 'resume') else None
                return self.schedules.request(**a, binding_marker=marker)
            if op == 'CATALOG':
                return self.projects.view()
            if op == 'SOURCE':
                return self.projects.chunk(**a)
            if op == 'OPERATION':
                return self.projects.operation(**a)
            if op == 'REFRESH':
                project = next((p for p in self.projects.view()['projects'] if p['id'] == a['project_id']), None)
                if project is None:
                    raise WCEError('PROJECT_NOT_FOUND')
                return self.projects.sync(project['root'], project['extra_skill_paths'],
                                          a['operation_id'], a['expected_revision'])
        self._scope(a)
        if op == 'SAVE':
            return self.projects.save(**a)
        value = self.projects.effective(**a)
        if a['platform_id'] == 'x' and a['connection_id']:
            configuration = OperatingConfig(self.projects).read(a['connection_id'])
            require(configuration['revision'] == value['revision'], 'PROJECT_REVISION_CONFLICT')
            value['x_configuration'] = configuration
        return value

    def _schedule_binding(self, cid):
        require(any(row['connection_id'] == cid and row.get('state') == 'BOUND_IDLE'
                    for row in self.inner.call('x.connections.list', {})['connections']),
                'SCHEDULE_CONNECTION_NOT_READY')
        marker = getattr(getattr(self.inner, 'x', None), 'automation_binding', None)
        return marker(cid) if marker else None
