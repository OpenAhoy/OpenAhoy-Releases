"""Local preference tools; app editing is separate from all WeChat rights."""
from copy import deepcopy
from hashlib import sha256
from .tools import schema
from .own_production_rules import (RulesStore, FIELDS, CHUNK_CHARACTERS, CHUNK_UTF8_BYTES,
                                   OP, fields_manifest, integer, need, text_chunk)

READ = 'own.production.rules.read'
SAVE = 'wce.settings.production.save'
RESTORE = 'wce.settings.production.restore'
UPDATE = 'own.production.rules.update'
NAMES = {READ, SAVE, RESTORE, UPDATE}
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
    UPDATE: schema({'connection_id':{'type':'string','minLength':1,'maxLength':128},
                    'expected_store_revision':NUM,'expected_scope_revision':NUM,
                    'changes':{'type':'object','minProperties':1,'maxProperties':len(FIELDS),
                               'additionalProperties':False,'properties':{key:TEXT for key in FIELDS}}}),
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


def update_descriptor():
    return {'name':UPDATE,'title':'修改当前公众号的创作偏好','inputSchema':deepcopy(SPECS[UPDATE]),
        'description':'Apply explicitly requested local writing-preference changes to one exact WeChat connection. '
        'Read own.production.rules.read account summary first, use its two expected revisions, send only fields the user wants changed. '
        'Omitted fields stay unchanged and this never sends, publishes, binds or changes permissions. '
        'If the result is unknown, repeat the identical request to recover its original operation.',
        'annotations':{'idempotentHint':True,'openWorldHint':False},'_meta':{'ui':{'visibility':['model','app']}}}


class RulesUpdateRouter:
    """Add model-facing preference updates without changing legacy UI descriptors."""

    def __init__(self,inner,registry):
        self.inner=inner
        self.registry=registry

    def __getattr__(self,name):
        return getattr(self.inner,name)

    def list_tools(self):
        return self.inner.list_tools()+[update_descriptor()]

    def call(self,name,args):
        if name==UPDATE:
            return call(name,args,self.registry)
        return self.inner.call(name,args)


def closed(value, keys):
    need(type(value) is dict and set(value)==set(keys))


def validate(name, value):
    # Deliberately not prepared.strict_validate: its fallback equates UTF-8
    # bytes and Unicode lengths, and is inappropriate for streamed rule text.
    need(name in NAMES and type(value) is dict)
    need(type(value.get('connection_id')) is str and len(value['connection_id'])<=128)
    if name==UPDATE:
        closed(value,{'connection_id','expected_store_revision','expected_scope_revision','changes'})
        RulesStore._scope('account',value['connection_id'])
        integer(value['expected_store_revision']);integer(value['expected_scope_revision'])
        patch=value['changes']
        need(type(patch) is dict and 0<len(patch)<=len(FIELDS) and set(patch)<=set(FIELDS))
        for text in patch.values():
            text_chunk(text)
        return
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
    if name==UPDATE:
        return update_account(store,value)
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


def update_account(store,args):
    """Reuse rule chunks and version history; keep other fields in the same scope."""
    from .contracts import WCEError
    from .own_production_rules import SECRET
    from .service import digest

    cid=args['connection_id']
    patch=args['changes']
    base=args['expected_store_revision'],args['expected_scope_revision']
    operation='rules-'+digest(['account-patch',cid,base,patch])[:32]
    granted='account'
    try:
        known=store.operation(cid,granted,operation)
    except WCEError as error:
        if error.code not in ('RULES_OPERATION_UNAVAILABLE','RULES_OPERATION_NOT_FOUND'):
            raise
        known=None
    if known and known['state']=='COMMITTED':
        return {**known,'connection_id':cid,'changed_fields':sorted(patch),'already_applied':True}
    current=store.summary(cid,granted)
    need((current['store_revision'],current['scope_revision'])==base,'RULES_VERSION_CONFLICT')
    manifests=[]
    for field in FIELDS:
        if field in patch:
            text=patch[field]
            need(SECRET.search(text) is None,'RULES_SECRET_NOT_ALLOWED')
            raw=text.encode('utf-8')
            manifests.append({'name':field,'chunks':int(bool(text)),
              'unicode_length':len(text),'utf8_bytes':len(raw),'sha256':sha256(raw).hexdigest()})
        elif field in current['fields']:
            before=current['fields'][field]
            manifests.append({'name':field,**{key:before[key] for key in ('chunks','unicode_length','utf8_bytes','sha256')}})
    store.begin(cid,granted,operation,*base,manifests)
    for field in manifests:
        key=field['name']
        for index in range(field['chunks']):
            text=patch[key] if key in patch else store.read_chunk(
                cid,granted,current['fields'][key]['version_id'],key,index)['text']
            store.chunk(cid,granted,operation,key,index,text)
    result=store.commit(cid,granted,operation)
    observed=store.summary(cid,granted,effective=True)
    return {**result,'connection_id':cid,'changed_fields':sorted(patch),
            'readback_matches':all(observed['fields'][k]['sha256']==sha256(v.encode('utf-8')).hexdigest()
                                   for k,v in patch.items())}


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
