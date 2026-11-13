"""Graph-external F/E/L/T reader. Catalogs are locators, never permission.

F is the actual configured process entry, E imports this core from its absolute
root, L independently accepts E/T and every row. No MCP/environment argument
selects these files. Deployment of F remains a separate maintenance action.
"""
from dataclasses import dataclass,field
from hashlib import sha256
from pathlib import Path
import inspect,json,os,sys,threading,time
from weakref import WeakKeyDictionary
from .contracts import WCEError
from .draft_group_contracts import canonical,digest
from .draft_group_pin_resources import PinPool,close_all

_PROCESS=None
_PROCESS_CLOSED=False
_ISSUED=WeakKeyDictionary()
_MAX=2*1024*1024
OPERATOR_EXTENSION_PROFILE='GROUP_CATALOG_OPERATOR_SOURCE_V1'
OPERATOR_EXTENSION_ROLES=('runtime_source_policy','first_covenant','original_root_evidence','qa_set','artifact_inventory')


def need(value,code='GROUP_HOST_EXTERNAL_LOADER_HOLD'):
    if value is not True:raise WCEError(code)


# These templates have no incoming model-controlled path/hash parameters. Only
# the reviewed, graph-external maintenance compiler fills their literals.
_F_BODY='''import hashlib,os,stat,sys
from pathlib import Path
_entry=Path(ENTRY_PATH)
_fd=os.open(_entry,os.O_RDONLY|os.O_NOFOLLOW|os.O_NONBLOCK)
try:
    _info=os.fstat(_fd)
    if not stat.S_ISREG(_info.st_mode) or _info.st_nlink!=1 or _info.st_uid!=os.getuid() or stat.S_IMODE(_info.st_mode)!=0o600 or _info.st_size>2097152:raise RuntimeError('GROUP_FIXED_ENTRY_TYPE')
    _raw=os.read(_fd,2097153)
    if hashlib.sha256(_raw).hexdigest()!=ENTRY_SHA or tuple(getattr(os.fstat(_fd),k)for k in ('st_dev','st_ino','st_mode','st_uid','st_gid','st_nlink','st_size','st_mtime_ns','st_ctime_ns'))!=tuple(getattr(_info,k)for k in ('st_dev','st_ino','st_mode','st_uid','st_gid','st_nlink','st_size','st_mtime_ns','st_ctime_ns')):raise RuntimeError('GROUP_FIXED_ENTRY_CHANGED')
    exec(compile(_raw,str(_entry),'exec'),{'__name__':'__wce_external_loader__','__file__':str(_entry)})
finally:os.close(_fd)
'''
_E_BODY='''import sys
sys.path.insert(0,CORE_ROOT)
from wce.group_host_external_loader import install_fixed_process_loader
install_fixed_process_loader()
if PROCESS_ROLE=='MCP':
    from wce.group_host_external_loader import run_fixed_process
    run_fixed_process()
elif PROCESS_ROLE=='BROKER':
    from wce.group_host_jobs import run_fixed_broker
    run_fixed_broker()
else:raise RuntimeError('GROUP_FIXED_PROCESS_ROLE')
'''
_F_KEYS=('ENTRY_PATH','ENTRY_SHA','ADOPTION_PATH','ADOPTION_SHA')
_E_KEYS=('CORE_ROOT','CORE_SCOPE','CATALOG_PATH','CATALOG_SHA','PROCESS_ROLE')


def _script(keys,values,body):
    need(type(values)is dict and set(values)==set(keys))
    need(all(type(values[k])is str for k in keys))
    return (''.join(k+'='+repr(values[k])+'\n'for k in keys)+body).encode()


def render_fixed_entrypoints(front,loader):
    """Detached compiler bytes only; neither rendering nor a dict installs F."""
    return _script(_F_KEYS,front,_F_BODY),_script(_E_KEYS,loader,_E_BODY)


@dataclass(frozen=True,eq=False,init=False)
class FixedProcessJobCatalog:
    authority:bool=False
    def __init__(self,*args,**kwargs):raise WCEError('GROUP_FIXED_CATALOG_ISSUER_REQUIRED')


@dataclass(frozen=True)
class _CatalogFacts:
    catalog:object
    thread:int
    core_root:Path
    core_scope:str
    loader_sha:str
    adoption_sha:str
    rows_raw:str
    files:tuple=field(repr=False)
    resources:object=field(repr=False)


class _CatalogPin:
    """Read-only lease; the process catalog owns its real leaf/ancestor FDs."""
    __slots__=('_view','_path','_sha','closed')
    def __init__(self,view,path,checksum):
        self._view,self._path,self._sha,self.closed=view,Path(path),checksum,False
        self.check()
    @property
    def path(self):return self._path
    @property
    def sha(self):self.check();return self._sha
    @property
    def raw(self):self.check();return self._view.raw
    @property
    def fd(self):self.check();return self._view.fd
    @property
    def pin(self):
        self.check();p=self._view.pin
        return (p[0],p[1],p[6],p[7],p[8],p[5])
    def check(self):
        need(not self.closed,'GROUP_FIXED_PIN_CLOSED')
        self._view.check()
        need(self._view.path==self._path and self._view._record.checksum==self._sha,
             'GROUP_FIXED_PIN_CHANGED')
        return True
    def close(self):
        if not self.closed:
            self._view.close();self.closed=True


class _CatalogResources:
    """One explicit creator-owned process lifetime, never an entry/H pool."""
    def __init__(self):
        self.pool=PinPool(self,catalog=True)
        self.closed=False
    def pin(self,path,checksum,maximum):
        need(not self.closed,'GROUP_FIXED_CATALOG_CLOSED')
        view=self.pool.acquire(Path(path),checksum,maximum,owner=self)
        return _CatalogPin(view,path,checksum)
    def borrow(self,path,checksum,maximum):
        need(not self.closed,'GROUP_FIXED_CATALOG_CLOSED')
        # The original fixed row/frame selects this pair. A sealed catalog may
        # only lend already-held physical leaves; worker acquisition is denied.
        view=self.pool.borrow_existing(Path(path),checksum,maximum,owner=self,borrower=object())
        return _CatalogPin(view,path,checksum)
    def seal(self):self.pool.seal(owner=self)
    def close(self,*,original=None):
        if self.closed:return
        need(self.pool.pid==os.getpid() and self.pool.thread==threading.get_ident(),
             'GROUP_FIXED_CATALOG_CLOSE_OWNER')
        self.closed=True
        close_all((lambda:self.pool.check_all(owner=self),
                   lambda:self.pool.close(owner=self,original=original)),original)


def _frame(frame,keys,body,*,resources,borrow=False):
    values={key:frame.f_globals.get(key)for key in keys}
    raw=_script(keys,values,body)
    path=Path(frame.f_code.co_filename)
    acquire=resources.borrow if borrow else resources.pin
    pin=acquire(path,sha256(raw).hexdigest(),_MAX)
    need(pin.raw==raw and frame.f_code==compile(raw,str(path),'exec'),'GROUP_FIXED_ENTRY_ORIGIN')
    need(frame.f_globals.get('__file__')==str(path),'GROUP_FIXED_ENTRY_ORIGIN')
    return values,pin


def close_process_catalog(*,original=None):
    """Explicit process shutdown; no worker may revoke a live owner's pool."""
    global _PROCESS,_PROCESS_CLOSED
    catalog=_PROCESS;facts=_ISSUED.get(catalog)if catalog is not None else None
    if facts is None:return
    need(facts.thread==threading.get_ident() and facts.resources.pool.pid==os.getpid(),
         'GROUP_FIXED_CATALOG_CLOSE_OWNER')
    _PROCESS=None;_PROCESS_CLOSED=True;_ISSUED.pop(catalog,None)
    _PRIVATE_PREPARATIONS.clear()
    callbacks=[pin.check for pin in facts.files]
    callbacks += [pin.close for pin in reversed(facts.files)]
    callbacks.append(lambda:facts.resources.close(original=original))
    close_all(callbacks,original)


def _borrow_fixed_row_pin(row,role):
    """Only existing exact catalog-row technical roles; no new path admission."""
    if _PROCESS is None:
        need(not _PROCESS_CLOSED,'GROUP_FIXED_CATALOG_CLOSED')
        return None
    facts=_ISSUED.get(_PROCESS)
    need(facts is not None and facts.catalog is _PROCESS and facts.resources.pool.sealed,
         'GROUP_FIXED_CATALOG_ROW_REQUIRED')
    # This is only an immutable locator selection. Original callers still run
    # all their original catalog_rows/code_scope/semantic checks; do not hash
    # the whole C again for each of seven mechanical pin leases.
    matches=[item for value in json.loads(facts.rows_raw)
             if (item:=_row(value,facts.core_scope))[0]==row]
    need(len(matches)==1,'GROUP_FIXED_CATALOG_ROW_REQUIRED')
    paths=dict(row[3])
    if role=='policy':pair=matches[0][1]
    elif (matches[0][2] is not None and matches[0][2]['profile']==OPERATOR_EXTENSION_PROFILE
          and role in OPERATOR_EXTENSION_ROLES):
        extension=matches[0][2];pair=(extension[role+'_path'],extension[role+'_sha'])
    else:
        need(role in paths,'GROUP_FIXED_CATALOG_ROLE_REQUIRED');pair=paths[role]
    return facts.resources.borrow(Path(pair[0]),pair[1],_MAX)


def _json(pin,keys,profile):
    from .draft_group_input_files import _plain,_closed
    try:value=json.loads(pin.raw)
    except (ValueError,UnicodeError):raise WCEError('GROUP_FIXED_CATALOG_JSON')
    _plain(value);_closed(value,keys)
    need(value['schema']==1 and type(value['schema'])is int and value['profile']==profile
         and value['authority']is False and pin.raw==(canonical(value)+'\n').encode(),'GROUP_FIXED_CATALOG_JSON')
    return value


def _pairs(value):
    from .draft_group_input_files import _hash
    need(type(value)is list)
    pairs=[]
    for item in value:
        need(type(item)is list and len(item)==2 and type(item[0])is str)
        _hash(item[1]);need(Path(item[0]).is_absolute())
        pairs.append((item[0],item[1]))
    return tuple(pairs)


def _row(value,core_scope):
    from .draft_group_input_files import _closed,_hash,_id
    _closed(value,('selector','account_key','candidate_scope','policy','paths','lookups','artifact_roots','helpers','retention','runtime_source'))
    _id(value['selector']);_hash(value['account_key']);_hash(value['candidate_scope'])
    policy=_pairs([value['policy']])[0]
    need(type(value['paths'])is dict and set(value['paths'])=={'configuration','semantic','source','review','arm_receipt','unarmed','armed'})
    named=tuple((key,_pairs([pair])[0])for key,pair in value['paths'].items())
    need(type(value['lookups'])is list and type(value['artifact_roots'])is list)
    lookups=[]
    for spec in value['lookups']:
        need(type(spec)is list and len(spec)==4 and all(type(x)is str for x in spec[:3])
             and all(Path(x).is_absolute()for x in spec[:2]) and type(spec[3])is list and all(type(x)is str for x in spec[3]))
        lookups.append((spec[0],spec[1],spec[2],tuple(spec[3])))
    roots=[]
    for key,path in value['artifact_roots']:
        _hash(key);need(type(path)is str and Path(path).is_absolute());roots.append((key,path))
    helpers=_pairs(value['helpers']);retention=_pairs(value['retention'])
    extension=value['runtime_source']
    if type(extension) is dict and extension.get('profile')==OPERATOR_EXTENSION_PROFILE:
        from .draft_group_operator_source_codec import CONTENT_SOURCE_TYPE
        keys=('schema','profile','authority','content_source_type','source_qualification','baseline_source_sha')+tuple(
            role+suffix for role in OPERATOR_EXTENSION_ROLES for suffix in ('_path','_sha'))
        _closed(extension,keys)
        need(type(extension['schema']) is int and extension['schema']==1 and extension['authority'] is False
             and extension['content_source_type']==CONTENT_SOURCE_TYPE
             and extension['source_qualification']=='NOT_ASSERTED'
             and extension['baseline_source_sha']==dict(named)['source'][1] and not lookups,
             'GROUP_OPERATOR_CATALOG_EXTENSION')
        for role in OPERATOR_EXTENSION_ROLES:
            pair=_pairs([[extension[role+'_path'],extension[role+'_sha']]])[0]
            need('..' not in Path(pair[0]).parts,'GROUP_OPERATOR_CATALOG_EXTENSION')
    elif extension is not None:
        from .draft_group_native_v2_codec import CATALOG_EXTENSION_KEYS,MODE
        _closed(extension,CATALOG_EXTENSION_KEYS)
        need(extension['schema']==1 and type(extension['schema'])is int
             and extension['profile']=='GROUP_CATALOG_RUNTIME_SOURCE_V1' and extension['mode']==MODE
             and extension['native_qualification']=='NOT_ASSERTED'
             and extension['baseline_source_sha']==dict(named)['source'][1]
             and type(extension['runtime_policy_path'])is str and Path(extension['runtime_policy_path']).is_absolute())
        _hash(extension['runtime_policy_sha']);_hash(extension['native_contract_sha'])
    row=(value['selector'],value['account_key'],value['candidate_scope'],named,tuple(lookups),tuple(roots),helpers,retention)
    return row,policy,extension


def install_fixed_process_loader():
    """Called only while the actual canonical F→E module frames are executing."""
    global _PROCESS
    need(not _PROCESS_CLOSED,'GROUP_FIXED_CATALOG_CLOSED')
    need(_PROCESS is None,'GROUP_FIXED_CATALOG_ALREADY_LOADED')
    frame=inspect.currentframe();held=[];resources=_CatalogResources()
    try:
        eframe=frame.f_back;fframe=eframe.f_back
        e,epin=_frame(eframe,_E_KEYS,_E_BODY,resources=resources);held.append(epin)
        f,fpin=_frame(fframe,_F_KEYS,_F_BODY,resources=resources);held.append(fpin)
        need(fframe.f_globals.get('__name__')=='__main__' and Path(sys.argv[0]).absolute()==fpin.path
             and f['ENTRY_PATH']==str(epin.path) and f['ENTRY_SHA']==epin.sha,'GROUP_FIXED_FRONT_NOT_RUNNING')
        result=_install_from_verified_entries(f,e,fpin,epin,held,resources=resources)
        resources=None
        return result
    finally:
        original=sys.exc_info()[1];del frame
        close_all([pin.close for pin in reversed(held)]+([] if resources is None else [lambda:resources.close(original=original)]),original)


def catalog_rows(policy=None):
    catalog=_PROCESS;facts=_ISSUED.get(catalog)if catalog is not None else None
    need(facts is not None and facts.catalog is catalog,'GROUP_HOST_LOADER_NOT_LOADED')
    from .own_connection_policy import code_scope
    need(code_scope()==facts.core_scope,'GROUP_FIXED_CORE_CHANGED')
    for pin in facts.files:pin.check()
    rows=[]
    for value in json.loads(facts.rows_raw):
        row,path,extension=_row(value,facts.core_scope)
        if policy is not None:
            need(policy.value['candidate_scope']==facts.core_scope,'GROUP_FIXED_POLICY_SCOPE')
            if str(policy.path)!=path[0]:continue
            actual=next(pin for pin in facts.files if str(pin.path)==path[0]and pin.sha==path[1]);actual.check()
        rows.append((row,path,extension))
    return tuple(rows)


def loaded_catalog_rows(policy=None):
    if _PROCESS is None:
        need(not _PROCESS_CLOSED,'GROUP_FIXED_CATALOG_CLOSED')
        return ()
    return catalog_rows(policy)


def _install_from_verified_entries(f,e,fpin,epin,held,*,resources):
    global _PROCESS
    root=Path(e['CORE_ROOT']);need(root.is_absolute())
    from . import group_host_jobs
    from .own_connection_policy import code_scope
    need(Path(__file__).absolute()==root/'wce/group_host_external_loader.py'
         and Path(group_host_jobs.__file__).absolute()==root/'wce/group_host_jobs.py'
         and code_scope()==e['CORE_SCOPE'],'GROUP_FIXED_CORE_ORIGIN')
    need(type(resources)is _CatalogResources and not resources.closed,'GROUP_FIXED_CATALOG_RESOURCES')
    if len(held)==4:
        lpin,tpin=held[2:]
        need(str(lpin.path)==f['ADOPTION_PATH']and lpin.sha==f['ADOPTION_SHA']
             and str(tpin.path)==e['CATALOG_PATH']and tpin.sha==e['CATALOG_SHA'],'GROUP_FIXED_CHILD_LOADER_BINDING')
    else:
        lpin=resources.pin(Path(f['ADOPTION_PATH']),f['ADOPTION_SHA'],_MAX);held.append(lpin)
        tpin=resources.pin(Path(e['CATALOG_PATH']),e['CATALOG_SHA'],_MAX);held.append(tpin)
    adoption=_json(lpin,('schema','profile','authority','loader','catalog','core_scope','rows_sha'), 'GROUP_FIXED_LOADER_ADOPTION_V1')
    table=_json(tpin,('schema','profile','authority','core_scope','rows'),'GROUP_FIXED_JOB_CATALOG_V1')
    need(adoption['loader']==[str(epin.path),epin.sha] and adoption['catalog']==[str(tpin.path),tpin.sha]
         and adoption['core_scope']==table['core_scope']==e['CORE_SCOPE']
         and adoption['rows_sha']==digest(table['rows']),'GROUP_FIXED_LOADER_ADOPTION')
    need(type(table['rows'])is list and 0<len(table['rows'])<=64,'GROUP_FIXED_CATALOG_ROWS')
    seen=set()
    for value in table['rows']:
        row,policy,extension=_row(value,e['CORE_SCOPE'])
        identity=(row[0],row[1]);need(identity not in seen,'GROUP_FIXED_CATALOG_DUPLICATE');seen.add(identity)
        for path,sha in (policy,)+tuple(pair for key,pair in row[3])+row[6]+row[7]:
            pin=resources.pin(Path(path),sha,_MAX);held.append(pin)
        if extension is not None:
            if extension['profile']==OPERATOR_EXTENSION_PROFILE:
                for role in OPERATOR_EXTENSION_ROLES:
                    held.append(resources.pin(Path(extension[role+'_path']),extension[role+'_sha'],_MAX))
            else:held.append(resources.pin(Path(extension['runtime_policy_path']),extension['runtime_policy_sha'],_MAX))
        # R independently binds U/C; A mechanically binds U/R/H. The full
        # semantic/source qualification remains inside the held Group Gate.
        named=dict(row[3]);files={str(p.path):p for p in held}
        review=json.loads(files[named['review'][0]].raw);arm=json.loads(files[named['arm_receipt'][0]].raw)
        from .draft_group_host_review import _arm_ast
        u,ua=_arm_ast(files[named['unarmed'][0]].raw);h,ha=_arm_ast(files[named['armed'][0]].raw)
        import ast
        need(u==h and all(type(v)is ast.Constant and v.value is None for v in ua.values())
             and ha['REVIEW_PATH'].value==named['review'][0] and ha['REVIEW_SHA'].value==named['review'][1]
             and review['candidate_scope']==row[2] and review['unarmed_sha']==named['unarmed'][1]
             and review['configuration_sha']==named['configuration'][1]
             and arm['unarmed_sha']==named['unarmed'][1] and arm['review_sha']==named['review'][1]
             and arm['armed_sha']==named['armed'][1] and arm['ast_diff']==['REVIEW_PATH','REVIEW_SHA'], 'GROUP_FIXED_CATALOG_ARM')
    for pin in held:pin.check()
    resources.seal()
    catalog=object.__new__(FixedProcessJobCatalog)
    facts=_CatalogFacts(catalog,threading.get_ident(),root,e['CORE_SCOPE'],epin.sha,lpin.sha,canonical(table['rows']),tuple(held),resources)
    _ISSUED[catalog]=facts;_PROCESS=catalog;held.clear()
    return catalog


def process_loader_anchor():
    catalog_rows()
    facts=_ISSUED[_PROCESS]
    # The first four fixed F/E/L/T descriptors are retained original FDs.
    epin,fpin,lpin,tpin=facts.files[:4]
    return {'front':[str(fpin.path),fpin.sha],'loader':[str(epin.path),epin.sha],
        'adoption':[str(lpin.path),lpin.sha],'catalog':[str(tpin.path),tpin.sha],
        'core_root':str(facts.core_root),'core_scope':facts.core_scope}


def _literal_script(pin,keys,body):
    import ast
    tree=ast.parse(pin.raw)
    values={}
    for node in tree.body[:len(keys)]:
        need(type(node)is ast.Assign and len(node.targets)==1 and type(node.targets[0])is ast.Name)
        key=node.targets[0].id;need(key in keys and key not in values)
        values[key]=ast.literal_eval(node.value)
    need(pin.raw==_script(keys,values,body),'GROUP_FIXED_CHILD_LOADER_ORIGIN')
    return values


def install_child_process_catalog(invocation):
    """Only original run_fixed's live H/parent-peer receipt may enter here."""
    global _PROCESS
    need(not _PROCESS_CLOSED,'GROUP_FIXED_CATALOG_CLOSED')
    need(_PROCESS is None,'GROUP_FIXED_CATALOG_ALREADY_LOADED')
    from .group_host_jobs import validate_child_invocation
    facts=validate_child_invocation(invocation)
    anchor=facts.request['loader_anchor']
    from .draft_group_input_files import _closed,_hash
    _closed(anchor,('front','loader','adoption','catalog','core_root','core_scope'))
    resources=facts.resources
    need(type(resources)is _CatalogResources and not resources.closed,'GROUP_FIXED_CATALOG_RESOURCES')
    held=[]
    try:
        pins={}
        for key in ('loader','front','adoption','catalog'):
            path,checksum=_pairs([anchor[key]])[0]
            pins[key]=resources.pin(Path(path),checksum,_MAX);held.append(pins[key])
        fpin,epin,lpin,tpin=(pins[k]for k in ('front','loader','adoption','catalog'))
        f=_literal_script(fpin,_F_KEYS,_F_BODY);e=_literal_script(epin,_E_KEYS,_E_BODY)
        need(f['ENTRY_PATH']==str(epin.path) and f['ENTRY_SHA']==epin.sha
             and f['ADOPTION_PATH']==str(lpin.path)and f['ADOPTION_SHA']==lpin.sha
             and e['CATALOG_PATH']==str(tpin.path)and e['CATALOG_SHA']==tpin.sha
             and e['CORE_ROOT']==anchor['core_root']and e['CORE_SCOPE']==anchor['core_scope']
             and e['CORE_SCOPE']==facts.constants['CORE_SCOPE']and e['CORE_ROOT']==facts.constants['CORE_ROOT'],
             'GROUP_FIXED_CHILD_LOADER_BINDING')
        # Reuse the same full L/T/R/U/H/A reader as the actual F→E process.
        result=_install_from_verified_entries(f,e,fpin,epin,held,resources=resources)
        rows=catalog_rows();matches=[item for item in rows if dict(item[0][3])['armed']==(str(facts.file.path),facts.file.sha)]
        need(len(matches)==1,'GROUP_FIXED_CHILD_ARM_NOT_CATALOGED')
        row,policy,extension=matches[0]
        need(policy==(facts.constants['POLICY_PATH'],facts.constants['POLICY_SHA'])
             and dict(row[3])['configuration']==(facts.constants['CONFIGURATION_PATH'],facts.constants['CONFIGURATION_SHA'])
             and row[2]==facts.constants['CORE_SCOPE']
             and facts.request['selector_sha']==dict(row[3])['configuration'][1], 'GROUP_FIXED_CHILD_INVOCATION_BINDING')
        validate_child_invocation(invocation)
        resources=None
        return result
    except BaseException as original:
        close_process_catalog(original=original)
        raise
    finally:
        original=sys.exc_info()[1]
        close_all([pin.close for pin in reversed(held)]+([] if resources is None else [lambda:resources.close(original=original)]),original)


def fixed_policy_from_arguments(arguments):
    """Only a catalog's exact existing policy is selectable by trusted argv."""
    need(type(arguments)is list and len(arguments)==3
         and arguments[0] in ('broker','prepare-group') and arguments[1]=='--policy'
         and type(arguments[2])is str,'GROUP_FIXED_PROCESS_ARGUMENTS')
    rows=catalog_rows()
    matches=[item for item in rows if item[1][0]==arguments[2]]
    need(len(matches)==1,'GROUP_FIXED_POLICY_SELECTION')
    row,pair,extension=matches[0]
    from .own_connection_policy import load_policy
    policy=load_policy(pair[0])
    need(len(catalog_rows(policy))==1,'GROUP_FIXED_POLICY_SELECTION')
    from .group_host_jobs import _compiled
    need(_compiled(policy)==row,'GROUP_FIXED_POLICY_SELECTION')
    policy.check()
    return policy


def run_fixed_process():
    """Canonical F is also the ordinary broker launcher, never a bootstrap."""
    try:
        accepted_at=time.monotonic()
        arguments=sys.argv[1:]
        if not arguments:
            catalog_rows()
            from .own_plugin import group_main
            return group_main()
        policy=fixed_policy_from_arguments(arguments)
        if arguments[0]=='prepare-group':
            invocation=_issue_private_preparation(policy,accepted_at+300)
            try:
                from .group_host_jobs import _compiled,_materialize
                from .draft_group_operator_review_chain import FixedOperatorHostPins
                from .draft_group_host_review import FixedHostPins
                pins=_materialize(policy,_compiled(policy))
                if type(pins) is FixedOperatorHostPins:
                    from .draft_group_first_control import prepare_group_first
                    result=prepare_group_first(policy,invocation)
                else:
                    need(type(pins) is FixedHostPins,'GROUP_PRIVATE_SOURCE_PROFILE')
                    from .draft_group_host_bootstrap import prepare_group_existing
                    result=prepare_group_existing(policy,invocation)
                sys.stdout.write(canonical(result)+'\n');sys.stdout.flush()
                return result
            finally:_PRIVATE_PREPARATIONS.pop(invocation,None)
        # setup.main sees only the exact broker form already checked above. Its
        # setup/add/enable/repair modes cannot enter through this fixed F.
        policy.check()
        from .own_connection_setup import main
        return main()
    finally:close_process_catalog(original=sys.exc_info()[1])


def fixed_default_launcher():
    """No issued catalog keeps the legacy route; a bad issued one fails shut."""
    if _PROCESS is None:
        need(not _PROCESS_CLOSED,'GROUP_FIXED_CATALOG_CLOSED')
        return None
    return Path(process_loader_anchor()['front'][0])


def check_process_loader_anchor(value):
    need(type(value)is dict and value==process_loader_anchor(),
         'GROUP_FIXED_PROCESS_ANCHOR_MISMATCH')
    return True


@dataclass(frozen=True,eq=False,init=False)
class _PrivatePreparation:
    def __init__(self,*args,**kwargs):raise WCEError('GROUP_PRIVATE_INVOCATION_ISSUER_REQUIRED')


_PRIVATE_PREPARATIONS=WeakKeyDictionary()


def _issue_private_preparation(policy,absolute_deadline):
    """Issue only while the actual canonical F/E prepare argv frame is live."""
    frame=inspect.currentframe();held=[]
    try:
        caller=frame.f_back
        need(caller.f_code is run_fixed_process.__code__, 'GROUP_PRIVATE_ENTRY_ORIGIN')
        catalog_rows()
        resources=_ISSUED[_PROCESS].resources
        eframe=caller.f_back;fframe=eframe.f_back
        e,epin=_frame(eframe,_E_KEYS,_E_BODY,resources=resources,borrow=True);held.append(epin)
        f,fpin=_frame(fframe,_F_KEYS,_F_BODY,resources=resources,borrow=True);held.append(fpin)
        anchor=process_loader_anchor()
        need(e['PROCESS_ROLE']=='MCP' and fframe.f_globals.get('__name__')=='__main__'
             and sys.argv==[str(fpin.path),'prepare-group','--policy',str(policy.path)]
             and anchor['front']==[str(fpin.path),fpin.sha]
             and anchor['loader']==[str(epin.path),epin.sha]
             and f['ENTRY_PATH']==str(epin.path) and f['ENTRY_SHA']==epin.sha,
             'GROUP_PRIVATE_ENTRY_ORIGIN')
        policy.check()
        from .group_host_jobs import _compiled
        row=_compiled(policy)
        need(type(absolute_deadline)is float and absolute_deadline==caller.f_locals['accepted_at']+300
             and time.monotonic()<absolute_deadline,'GROUP_DEADLINE')
        invocation=object.__new__(_PrivatePreparation)
        _PRIVATE_PREPARATIONS[invocation]={'pid':os.getpid(),'thread':threading.get_ident(),
            'catalog':_PROCESS,'policy':policy,'policy_pair':(str(policy.path),sha256(next(pin.raw for pin in _ISSUED[_PROCESS].files if pin.path==policy.path)).hexdigest()),
            'selection':(row[0],dict(row[3])['configuration'][1]),'deadline':absolute_deadline,
            'policy_sha':policy.fingerprint,'anchor':anchor,'consumed':False}
        return invocation
    finally:
        original=sys.exc_info()[1];del frame
        close_all([pin.close for pin in reversed(held)],original)


def check_private_preparation(invocation,policy,*,consume=False):
    try:facts=_PRIVATE_PREPARATIONS.get(invocation)
    except TypeError:facts=None
    need(type(invocation)is _PrivatePreparation and facts is not None
         and facts['pid']==os.getpid() and facts['catalog']is _PROCESS
         and facts['thread']==threading.get_ident() and facts['policy']is policy
         and facts['policy_sha']==policy.fingerprint,'GROUP_PRIVATE_INVOCATION_REQUIRED')
    policy.check();check_process_loader_anchor(facts['anchor'])
    from .group_host_jobs import _compiled
    row=_compiled(policy)
    need(facts['selection']==(row[0],dict(row[3])['configuration'][1])
         and facts['policy_pair'] in tuple(item[1] for item in catalog_rows(policy))
         and time.monotonic()<facts['deadline'],'GROUP_PRIVATE_INVOCATION_CHANGED')
    if consume:
        need(facts['consumed']is False,'GROUP_PRIVATE_INVOCATION_SPENT')
        facts['consumed']=True
    return facts['deadline']
