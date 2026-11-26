"""Current platform directory and fixed adapters; never infer a fallback."""
from copy import deepcopy

from .contracts import WCEError
from .prepared_contracts import strict_validate
from .tools import schema
from .own_production_rules_protocol import SPECS as RULE_SPECS, READ, SAVE, RESTORE

WECHAT = 'wechat_official_account'
OPERATIONS = {'READ_RULES': READ, 'SAVE_RULES': SAVE, 'RESTORE_RULES': RESTORE}
DIRECTORY = ({'id': WECHAT, 'name': '公众号', 'account_noun': '公众号',
              'account_id_label': 'AppID',
              'settings_help': '默认规则仅用于公众号，可按本号覆盖；不会作用于其他平台。',
              'settings_supported': True, 'binding_supported': True},)


def platforms():
    return deepcopy(list(DIRECTORY))


def require_platform(platform_id):
    if type(platform_id) is not str or platform_id != WECHAT:
        raise WCEError('PLATFORM_UNSUPPORTED')
    return DIRECTORY[0]


def action_schema():
    variants = []
    from .own_inline_binding import BINDING_SPECS
    from .own_configuration_export import SPEC as EXPORT_SPEC
    for operation in (*OPERATIONS, 'EXPORT_CONFIG', 'OPEN_BINDING', 'OPEN_SECURITY', *BINDING_SPECS):
        arguments = (RULE_SPECS[OPERATIONS[operation]] if operation in OPERATIONS else
                     EXPORT_SPEC if operation == 'EXPORT_CONFIG' else BINDING_SPECS.get(operation,schema({})))
        variants.append(schema({'platform_id': {'type': 'string', 'enum': [WECHAT]},
            'operation': {'type': 'string', 'const': operation}, 'arguments': deepcopy(arguments)}))
    return {'oneOf': variants}


def perform(value, settings):
    # Select a registered adapter before entering any platform domain.
    if type(value) is not dict:
        raise WCEError('PLATFORM_INVALID_REQUEST')
    require_platform(value.get('platform_id'))
    from .own_inline_binding import BINDING_SPECS
    if (set(value) != {'platform_id', 'operation', 'arguments'}
            or type(value['operation']) is not str
            or value['operation'] not in {*OPERATIONS, 'EXPORT_CONFIG', 'OPEN_BINDING', 'OPEN_SECURITY', *BINDING_SPECS}
            or type(value['arguments']) is not dict):
        raise WCEError('PLATFORM_INVALID_REQUEST')
    operation, arguments = value['operation'], value['arguments']
    if operation == 'EXPORT_CONFIG':
        from .own_configuration_export import export
        from .own_settings_protocol import overview
        from .wechat_component_binding import configuration_account
        rows = overview(settings.original)['connections']
        authorized = configuration_account(settings.original.registry, arguments.get('connection_id') or '')
        if authorized:
            rows.append(authorized)
        return export(arguments, rows)
    if operation in OPERATIONS:
        from .own_production_rules_protocol import call
        return call(OPERATIONS[operation], arguments, settings.original.registry)
    if operation in BINDING_SPECS:
        strict_validate(arguments,BINDING_SPECS[operation])
        method={'BINDING_CHECK':'channel_check','BINDING_BEGIN':'begin','BINDING_SUBMIT':'submit','BINDING_STATUS':'status','BINDING_CANCEL':'cancel','BINDING_RESUME':'resume',
                'REBIND_BEGIN':'rebind_begin','REBIND_SUBMIT':'rebind_submit',
                'REBIND_STATUS':'rebind_status','REBIND_CANCEL':'rebind_cancel'}[operation]
        return getattr(settings.binding,method)(**arguments)
    strict_validate(arguments, schema({}))
    if operation == 'OPEN_BINDING':
        return settings.binding.open()
    return settings.manager.open()
