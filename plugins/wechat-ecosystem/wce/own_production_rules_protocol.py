"""Local preference tools; app editing is separate from all WeChat rights."""
from copy import deepcopy
from .tools import schema
from .own_production_rules import (RulesStore, FIELDS, CHUNK_CHARACTERS, CHUNK_UTF8_BYTES,
                                   OP, fields_manifest, integer, need, text_chunk)

READ = 'own.production.rules.read'
SAVE = 'wce.settings.production.save'
RESTORE = 'wce.settings.production.restore'
NAMES = {READ, SAVE, RESTORE}
TEXT = {'type': 'string', 'maxLength': CHUNK_CHARACTERS,
        'description': 'At most 8192 Unicode scalar characters and 32768 UTF-8 bytes in this chunk. Automatically continue chunks; no total text/history quota.'}
ID = {'type': 'string', 'pattern': '^rules-[a-f0-9]{32}$'}
VERSION = {'type':'string','pattern':'^(?:rules-[a-f0-9]{32}|legacy-editor-[a-f0-9]{64})$'}
NUM = {'type': 'integer', 'minimum': 0, 'maximum': 2**53-1}
BASE = {'connection_id': {'type': 'string', 'maxLength': 128}, 'scope': {'enum': ['global','account'], 'type':'string'}}
FIELD = schema({'name': {'type':'string','enum':list(FIELDS)}, 'chunks':NUM,
                'unicode_length':NUM,'utf8_bytes':NUM,'sha256':{'type':'string','pattern':'^[a-f0-9]{64}$'}})
SPECS = {
    READ: schema(BASE | {'view':{'type':'string','enum':['summary','effective','chunk','history','operation','version']}},
                 {'version_id':VERSION,'field':{'type':'string','enum':list(FIELDS)},'index':NUM,'before':NUM,'operation_id':ID}),
    SAVE: {'oneOf': [schema(BASE | {'action':{'type':'string','const':'begin'},'operation_id':ID,
                                  'expected_store_revision':NUM,'expected_scope_revision':NUM,
                                  'fields':{'type':'array','minItems':0,'maxItems':len(FIELDS),'items':FIELD}}),
                         schema(BASE | {'action':{'type':'string','const':'chunk'},'operation_id':ID,
                                        'field':{'type':'string','enum':list(FIELDS)},'index':NUM,'text':TEXT}),
                         schema(BASE | {'action':{'type':'string','const':'commit'},'operation_id':ID})]},
    RESTORE: schema(BASE | {'operation_id':ID,'version_id':ID,'expected_store_revision':NUM,'expected_scope_revision':NUM}),
}


def descriptors():
    result=[]
    for name in (READ,SAVE,RESTORE):
        result.append({'name':name,'title':{READ:'读取内容生产规则',SAVE:'保存内容生产规则',RESTORE:'恢复生产规则版本'}[name],
            'description':('Local non-secret production preferences only; never API authority or changes to frozen articles. '
                'Read effective field manifests then every chunk to its declared count and verify SHA256. History is paginated, not truncated. '
                'Save uses automatic begin/chunk/commit with the same operation ID; unknown results query that ID.'),
            'inputSchema':deepcopy(SPECS[name]), 'outputSchema':{'type':'object'},
            'annotations':{'readOnlyHint':name==READ,'destructiveHint':False,'openWorldHint':False,'idempotentHint':True},
            '_meta':{'ui':{'visibility':['model','app'] if name==READ else ['app']}}})
    return result


def closed(value, keys):
    need(type(value) is dict and set(value)==set(keys))


def validate(name, value):
    # Deliberately not prepared.strict_validate: its fallback equates UTF-8
    # bytes and Unicode lengths, and is inappropriate for streamed rule text.
    need(name in NAMES and type(value) is dict)
    need(type(value.get('connection_id')) is str and len(value['connection_id'])<=128)
    RulesStore._scope(value.get('scope'),value['connection_id'])
    base={'scope','connection_id'}
    if name==READ:
        view=value.get('view');need(type(view)is str and view in {'summary','effective','chunk','history','operation','version'})
        extra={'summary':set(),'effective':set(),'chunk':{'version_id','field','index'},
               'history':({'before'} if 'before' in value else set()),'operation':{'operation_id'},'version':{'version_id'}}[view]
        closed(value,base|{'view'}|extra)
    elif name==SAVE:
        action=value.get('action');need(type(action)is str and action in {'begin','chunk','commit'})
        extra={'begin':{'fields','expected_store_revision','expected_scope_revision'},
               'chunk':{'field','index','text'},'commit':set()}[action]
        closed(value,base|{'action','operation_id'}|extra)
        if action=='begin':fields_manifest(value['fields'])
        if action=='chunk':text_chunk(value['text'])
    else:closed(value,base|{'operation_id','version_id','expected_store_revision','expected_scope_revision'})
    for key in ('operation_id','version_id'):
        if key in value:
            token=value[key]
            valid=type(token)is str and OP.fullmatch(token)is not None
            if key=='version_id' and name==READ and value['view']=='chunk':
                from .own_production_rules_legacy import PREFIX
                from .own_production_rules import HASH
                valid=valid or (type(token)is str and token.startswith(PREFIX) and HASH.fullmatch(token[len(PREFIX):])is not None)
            need(valid)
    for key in ('index','before','expected_store_revision','expected_scope_revision'):
        if key in value:integer(value[key])
    if 'field' in value:need(value['field'] in FIELDS)


def call(name, value, registry=None, *, store=None):
    validate(name,value)
    store=store or RulesStore(registry)
    cid,scope=value['connection_id'],value['scope']
    if name==READ:
        view=value['view']
        if view in ('summary','effective'):return store.summary(cid,scope,effective=view=='effective')
        if view=='chunk':return store.read_chunk(cid,scope,value['version_id'],value['field'],value['index'])
        if view=='version':return store.version(cid,scope,value['version_id'])
        if view=='history':return store.history(cid,scope,value.get('before',2**53-1))
        return store.operation(cid,scope,value['operation_id'])
    if name==RESTORE:
        return store.restore(cid,scope,value['operation_id'],value['version_id'],value['expected_store_revision'],value['expected_scope_revision'])
    if value['action']=='begin':return store.begin(cid,scope,value['operation_id'],value['expected_store_revision'],value['expected_scope_revision'],value['fields'])
    if value['action']=='chunk':return store.chunk(cid,scope,value['operation_id'],value['field'],value['index'],value['text'])
    return store.commit(cid,scope,value['operation_id'])


def full_tool_projection(actual):
    """Validate this distribution's exact catalog, never an old personal grant."""
    from .own_native_management_contract import contract
    from .service import digest
    value=contract()
    need(type(actual) is list and all(type(row) is dict and type(row.get('name')) is str for row in actual),'RULES_DESCRIPTOR_HOLD')
    need(len({row['name'] for row in actual})==len(actual),'RULES_DESCRIPTOR_HOLD')
    checksum=digest(sorted(actual,key=lambda row:row['name']))
    need(checksum==value['after_descriptor_sha256'],'RULES_DESCRIPTOR_HOLD')
    return {'total_tools':len(actual),'full_descriptor_sha256':checksum,'platform_rights_added':False}
