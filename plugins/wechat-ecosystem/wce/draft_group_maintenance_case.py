"""UNARMED fixed Operator maintenance ingress, before business schema9.

This entry never creates AccountService/OwnProfile/GroupHost/SourceFacts/W1/W2.
Canonical external B/review/arm files bind C without embedding their future
hashes into C. No public argument, environment value, or JSON can issue a case.
The actual inventory producer retains all writer/H/migration responsibilities.
"""
from contextlib import contextmanager, _GeneratorContextManager
from dataclasses import dataclass
from hashlib import sha256
import ast
import inspect
import json
import math
import os
from pathlib import Path
import pwd
import re
import stat
import sys
import threading
import time
from types import MethodType
from weakref import WeakKeyDictionary

from .contracts import WCEError
from .service import canonical, digest
from .draft_group_pin_resources import (PinPool, close_all, full, path_value,
    capacity, MAX_RAW_BYTES)
from .own_preupload_sources import _EvidenceView
from .own_body_recovery import code_scope

# Adoption is the accepted entry CONTRACT digest, never C/B/A/arm's digest.
# Missing final literal is an unarmed refusal, before any account/policy read.
MAINTENANCE_ENTRY_ADOPTION = '3d18d6a99f57123162fabe7430c720ae1a89255a48f0108a079086f18af42f1c'
BACKUP_STREAM_MODEL = 'EXACT_STAGE_DB_STREAM_V1'
BACKUP_CHUNK_BYTES = 1024 * 1024
MAINTENANCE_EXECUTION_SECONDS = 300
MAX_SOURCE = 2 * 1024 * 1024
BOOTSTRAP_KEYS = ('CORE_ROOT','CORE_SCOPE','BINDING_SHA256','REVIEW_SHA256','ARM_SHA256')
BOOTSTRAP_BODY = '''import sys
sys.path.insert(0,CORE_ROOT)
from wce.draft_group_maintenance_case import enter_fixed_maintenance_case
from wce.draft_group_maintenance_inventory import run_fixed_case
with enter_fixed_maintenance_case() as case:
    run_fixed_case(case)
'''
WRAPPER_KEYS = ('BOOTSTRAP_PATH','BOOTSTRAP_FD','BOOTSTRAP_PIN','BOOTSTRAP_SIZE',
    'BOOTSTRAP_SHA','ABSOLUTE_DEADLINE')
WRAPPER_BODY = '''import os,stat,hashlib,sys
def _full(i):
    return (i.st_dev,i.st_ino,i.st_mode,i.st_uid,i.st_gid,i.st_nlink,i.st_size,i.st_mtime_ns,i.st_ctime_ns)
_info=os.fstat(BOOTSTRAP_FD)
if not stat.S_ISREG(_info.st_mode) or _info.st_uid!=os.getuid() or stat.S_IMODE(_info.st_mode)!=0o600 or _info.st_nlink!=1 or _full(_info)!=BOOTSTRAP_PIN or _full(os.stat(BOOTSTRAP_PATH,follow_symlinks=False))!=BOOTSTRAP_PIN:raise RuntimeError('MAINTENANCE_PROGRAM_CHANGED')
_raw=os.pread(BOOTSTRAP_FD,BOOTSTRAP_SIZE+1,0)
if len(_raw)!=BOOTSTRAP_SIZE or hashlib.sha256(_raw).hexdigest()!=BOOTSTRAP_SHA or _full(os.fstat(BOOTSTRAP_FD))!=BOOTSTRAP_PIN or _full(os.stat(BOOTSTRAP_PATH,follow_symlinks=False))!=BOOTSTRAP_PIN:raise RuntimeError('MAINTENANCE_PROGRAM_CHANGED')
sys.argv=[BOOTSTRAP_PATH]
_program=compile(_raw,BOOTSTRAP_PATH,'exec',dont_inherit=True)
exec(_program,{'__name__':'__main__','__file__':BOOTSTRAP_PATH,'__package__':None})
'''
_ISSUED=WeakKeyDictionary()
_ACTIVE=None


def need(value,code='HOLD'):
    if value is not True:raise WCEError('GROUP_MAINTENANCE_CASE_'+code)


def _sha(value):
    need(type(value) is str and re.fullmatch('[0-9a-f]{64}',value) is not None,'SHA')


def _closed(value,keys):
    need(type(value) is dict and set(value)==set(keys),'CLOSED')


def _json(raw,*,line=False):
    from .own_bootstrap_security import decode
    need(type(raw) is bytes and 0<len(raw)<=MAX_SOURCE,'JSON_BOUND')
    value=decode(raw,MAX_SOURCE)
    need(type(value) is dict and (canonical(value)+('\n' if line else '')).encode()==raw,'CANONICAL')
    return value


def _ref(value):
    _closed(value,('path','sha256','bytes'));path_value(value['path']);_sha(value['sha256'])
    need(type(value['bytes']) is int and 0<value['bytes']<=MAX_SOURCE,'REF_BOUND')


def bootstrap_bytes(root,scope,binding_sha,review_sha,arm_sha):
    path_value(root)
    for value in (scope,binding_sha,review_sha,arm_sha):_sha(value)
    return (''.join(key+'='+repr(value)+'\n' for key,value in zip(BOOTSTRAP_KEYS,
        (str(root),scope,binding_sha,review_sha,arm_sha)))+BOOTSTRAP_BODY).encode()


def parse_bootstrap(raw):
    try:
        tree=ast.parse(raw);values={}
        for node,key in zip(tree.body,BOOTSTRAP_KEYS):
            need(type(node) is ast.Assign and len(node.targets)==1
                 and type(node.targets[0]) is ast.Name and node.targets[0].id==key,'BOOTSTRAP_AST')
            values[key]=ast.literal_eval(node.value)
        need(tuple(values)==BOOTSTRAP_KEYS and all(type(v) is str for v in values.values()),'BOOTSTRAP_AST')
        need(raw==bootstrap_bytes(*(values[key] for key in BOOTSTRAP_KEYS)),'BOOTSTRAP_BODY')
        return values
    except (SyntaxError,ValueError,TypeError,UnicodeError):
        raise WCEError('GROUP_MAINTENANCE_CASE_BOOTSTRAP_AST') from None


def render_wrapper_values(values):
    need(type(values) is dict and tuple(values)==WRAPPER_KEYS,'WRAPPER_KEYS')
    # The launcher must supply a held original program FD; no path-only exec.
    path_value(values['BOOTSTRAP_PATH']);_sha(values['BOOTSTRAP_SHA'])
    need(type(values['BOOTSTRAP_FD']) is int and values['BOOTSTRAP_FD']>=3
         and type(values['BOOTSTRAP_PIN']) is tuple and len(values['BOOTSTRAP_PIN'])==9
         and all(type(x) is int for x in values['BOOTSTRAP_PIN'])
         and type(values['BOOTSTRAP_SIZE']) is int and 0<values['BOOTSTRAP_SIZE']<=MAX_SOURCE
         and type(values['ABSOLUTE_DEADLINE']) in (int,float)
         and math.isfinite(values['ABSOLUTE_DEADLINE']),'WRAPPER_VALUES')
    return (''.join(key+'='+repr(values[key])+'\n' for key in WRAPPER_KEYS)+WRAPPER_BODY).encode()


def _runtime():
    _sha(MAINTENANCE_ENTRY_ADOPTION)
    root=Path(__file__).absolute().parents[1]
    need(all(Path(module.__file__).absolute()==root/'wce'/Path(module.__file__).name
             for module in _DEPENDENCIES),'MODULE_ROOT_CHANGED')
    from .bounded_file import FileSource
    raw=FileSource(root).read('plugin.json');metadata=json.loads(raw)
    need(type(metadata) is dict and metadata.get('name')=='wechat-ecosystem'
         and type(metadata.get('version')) is str
         and re.fullmatch(r'[0-9]+\.[0-9]+\.[0-9]+',metadata['version']) is not None,'PACKAGE')
    home=path_value(pwd.getpwuid(os.getuid()).pw_dir)
    return root,code_scope(),home/'.wce/group-maintenance-runtime'/metadata['version']/'bootstrap.py'


def _check_program(values,raw):
    fd=values['BOOTSTRAP_FD'];info=os.fstat(fd)
    need(stat.S_ISREG(info.st_mode) and info.st_uid==os.getuid()
         and stat.S_IMODE(info.st_mode)==0o600 and info.st_nlink==1
         and full(info)==values['BOOTSTRAP_PIN']==full(os.stat(values['BOOTSTRAP_PATH'],follow_symlinks=False))
         and len(raw)==values['BOOTSTRAP_SIZE']==info.st_size
         and sha256(raw).hexdigest()==values['BOOTSTRAP_SHA'],'PROGRAM')
    need(os.pread(fd,len(raw)+1,0)==raw and full(os.fstat(fd))==full(info)
         ==full(os.stat(values['BOOTSTRAP_PATH'],follow_symlinks=False)),'PROGRAM_CHANGED')


def _preflight():
    frame=inspect.currentframe()
    try:
        issue=frame.f_back;entered=issue.f_back;manager=entered.f_back
        bootstrap=manager.f_back;wrapper=bootstrap.f_back
        need(issue.f_code is _ISSUE_CODE and entered.f_code is _ENTER_CODE
             and manager.f_code is _GeneratorContextManager.__enter__.__code__
             and bootstrap is not None and wrapper is not None
             and wrapper.f_code.co_filename=='<string>','CANONICAL_CALLER')
        values={key:wrapper.f_locals.get(key) for key in WRAPPER_KEYS}
        need(wrapper.f_code==compile(render_wrapper_values(values),'<string>','exec',dont_inherit=True)
             and wrapper.f_locals.get('_program') is bootstrap.f_code,'CANONICAL_WRAPPER')
        raw=wrapper.f_locals.get('_raw');_check_program(values,raw)
        root,scope,path=_runtime();program=parse_bootstrap(raw)
        need(values['BOOTSTRAP_PATH']==str(path) and sys.argv==[str(path)]
             and bootstrap.f_globals.get('__name__')=='__main__'
             and bootstrap.f_globals.get('__file__')==str(path)
             and bootstrap.f_code==compile(raw,str(path),'exec',dont_inherit=True)
             and program['CORE_ROOT']==str(root) and program['CORE_SCOPE']==scope
             and all(bootstrap.f_globals.get(key)==program[key] for key in BOOTSTRAP_KEYS),
             'FIXED_PROGRAM')
        now=time.monotonic();deadline=values['ABSOLUTE_DEADLINE']
        need(now<deadline<=now+MAINTENANCE_EXECUTION_SECONDS,'DEADLINE')
        return root,scope,path,program,values,raw
    finally:del frame


@dataclass(frozen=True,eq=False,init=False,slots=True,weakref_slot=True)
class FixedMaintenanceCase:
    def __init__(self,*args,**kwargs):need(False,'PRIVATE_ISSUER_REQUIRED')
    @property
    def authority(self):return False
    @property
    def policy(self):return _record(self).policy
    @property
    def registry(self):return _record(self).registry
    @property
    def operation_id(self):return _record(self).source['operation_id']
    @property
    def code_scope(self):return _record(self).scope
    @property
    def source_sha(self):return _record(self).source_pin.sha
    @property
    def backup_root(self):return Path(_record(self).source['backup_root'])
    @property
    def deadline(self):return _record(self).deadline
    def guard(self):
        record=_record(self)
        try:_guard(record)
        except BaseException:record.poisoned=True;raise
        return None
    def require_current_in(self,db,H):
        record=_record(self)
        try:
            _guard(record)
            if record.phase=='CURRENT_PENDING_HISTORY_OBSERVATION':
                _checkpoint_observation_in(record,db,H,require_finished=True)
            image,receipts=_current(record,db,H)
            if record.current_sha is None:
                need(record.phase=='CURRENT_PENDING_HISTORY_OBSERVATION','CURRENT_UNISSUED')
                second,second_receipts=_current(record,db,H)
                need(canonical(image)==canonical(second),'DOUBLE_PASS_CHANGED')
                for receipt in (*receipts,*second_receipts):receipt.collective_fence()
                record.current_sha=digest(second);record.receipts=tuple(second_receipts)
                record.not_after=min(record.not_after,image['qa']['not_after_wall'])
                record.phase='CURRENT_QUALIFIED'
            else:need(record.phase=='CURRENT_QUALIFIED' and record.current_sha==digest(image),'CURRENT_CHANGED')
            for receipt in receipts:receipt.collective_fence()
            _guard(record)
        except BaseException:record.poisoned=True;raise
        return None
    def require_migration_ready(self):
        record=_record(self)
        try:
            _guard(record)
            need(record.phase=='CURRENT_QUALIFIED' and record.current_sha is not None,
                 'PENDING_HISTORY_QUERY_FINISH_ONLY')
        except BaseException:record.poisoned=True;raise
        return None
    def require_backup(self,manifestSHA,path):
        record=_record(self)
        try:_guard(record);_backup(record,manifestSHA,path);_guard(record)
        except BaseException:record.poisoned=True;raise
        return None


class _Resources:
    """Actual resource owner, never a fake PREUPLOAD entry or source issuer."""
    def __init__(self,root,scope,deadline):
        self.runtime=type('_RuntimeView',(),{'root':root,'scope':scope})()
        self.deadline=deadline;self.closed=False;self.owner=(os.getpid(),threading.get_ident())
        self.pool=PinPool(self);self.views={};self.private_views={};self.evidence_bytes=0;self.active_files=None
        self.selection=None;self.projection=None;self.derived_cache=None
    def guard(self):
        need(not self.closed and self.owner==(os.getpid(),threading.get_ident())
             and time.monotonic()<self.deadline and code_scope()==self.runtime.scope,'RESOURCE_LIFETIME')
        if self.active_files is not None:
            from .own_preupload_selected_files import SelectedMemberFiles
            need(type(self.active_files) is SelectedMemberFiles
                 and self.active_files.parent_resources is self and not self.active_files.closed,
                 'ACTIVE_SELECTED_OWNER')
        active=0 if self.active_files is None else (
            self.active_files.pool.raw_bytes+self.active_files.evidence_bytes)
        need(self.pool.raw_bytes+self.evidence_bytes+active+self.derived_bytes<=MAX_RAW_BYTES,'RAW_BOUND')
        self.pool.check_all(owner=self)
        for view in self.views.values():view.check()
    @property
    def derived_bytes(self):
        return 0 if self.derived_cache is None else self.derived_cache.retained_bytes
    def prepare_selected(self,member):
        needed=sum(item['size'] for item in (member['html'],member['body'],*[image['artifact'] for image in member['images']]))
        if self.pool.raw_bytes+self.evidence_bytes+self.derived_bytes+needed>MAX_RAW_BYTES:
            self.derived_cache.clear()
    def reserve_derived(self,extra):
        active=0 if self.active_files is None else self.active_files.pool.raw_bytes+self.active_files.evidence_bytes
        need(self.pool.raw_bytes+self.evidence_bytes+active+self.derived_bytes+extra<=MAX_RAW_BYTES,'RAW_BOUND')
    def values(self):self.guard();return json.loads(canonical(self.projection))
    def acquire_evidence(self,ref):
        _ref(ref);self.guard();path=path_value(ref['path']);prior=self.views.get(path)
        if prior is not None:
            need(prior.sha==ref['sha256'] and len(prior.raw)==ref['bytes'],'REF_CHANGED');return prior
        active=0 if self.active_files is None else self.active_files.evidence_bytes+self.active_files.pool.raw_bytes
        need(self.pool.raw_bytes+self.evidence_bytes+active+self.derived_bytes+ref['bytes']<=MAX_RAW_BYTES,'RAW_BOUND')
        view=_EvidenceView(self,path,ref['sha256'],ref['bytes'])
        try:
            need(len(view.raw)==ref['bytes'],'REF_BYTES');self.views[path]=view
        except BaseException as original:
            close_all([view.close],original);raise
        self.guard();return view
    def private(self,path,checksum):
        self.guard();path=path_value(path)
        prior=self.private_views.get(path)
        if prior is not None:
            prior.check();need(prior.sha==checksum,'PRIVATE_REBASE');return prior
        parent=self.pool.directory(path.parent,owner=self)
        info=os.stat(path.name,dir_fd=parent,follow_symlinks=False)
        active=0 if self.active_files is None else self.active_files.pool.raw_bytes+self.active_files.evidence_bytes
        need(0<info.st_size<=MAX_SOURCE and self.pool.raw_bytes+self.evidence_bytes+active+self.derived_bytes+info.st_size<=MAX_RAW_BYTES,
             'RAW_BOUND')
        view=self.pool.acquire(path,checksum,info.st_size,owner=self)
        need(view.pin==full(info),'PRIVATE_FILE_CHANGED')
        self.private_views[path]=view;self.guard();return view
    def close(self,*,original=None):
        if not self.closed:
            self.closed=True
            close_all(([self.derived_cache.close] if self.derived_cache is not None else [])+
                [view.close for view in reversed(tuple(self.views.values()))]+
                [lambda:self.pool.close(owner=self,original=original)],original)


def _decode_source(value):
    _closed(value,('schema','profile','authority','purpose','entry_contract_sha','operation_id',
        'candidate_scope','binding','partition','selection_ref','artifact_roots_ref','member_projection_ref',
        'dossier_ref','acceptance_ref','original','owner_completion_ref','backup_root','scratch_root','not_after',
        'limits'))
    _sha(value['entry_contract_sha'])
    need(type(value['schema']) is int and value['schema']==1
         and value['profile']=='GROUP_FIXED_MAINTENANCE_CASE_V2' and value['authority'] is False
         and value['purpose']=='SCHEMA6_TO8_TO9_NO_BUSINESS_GRANT'
         and value['entry_contract_sha']==MAINTENANCE_ENTRY_ADOPTION,'SOURCE_PROFILE')
    _sha(value['candidate_scope']);from .prepared_contracts import strict_validate,ID
    strict_validate(value['operation_id'],ID)
    from .own_prepared_history import binding_validate
    binding_validate(value['binding']);need(value['binding']['source_kind']=='OPERATOR_ATTESTED','SOURCE_KIND')
    _closed(value['partition'],('connection_id','member_ids','scope_policy'))
    p=value['partition'];need(p['connection_id']==value['binding']['connection']
        and p['scope_policy']=='EXACT_ACCEPTED_ACCOUNT_PARTITION_ALL_ORIGINAL_SLOT_STATES'
        and type(p['member_ids']) is list and 0<len(p['member_ids'])<=28
        and len(set(p['member_ids']))==len(p['member_ids']),'PARTITION')
    for member in p['member_ids']:strict_validate(member,ID)
    for name in ('selection_ref','artifact_roots_ref','member_projection_ref','dossier_ref',
                 'acceptance_ref','owner_completion_ref'):_ref(value[name])
    path_value(value['backup_root']);path_value(value['scratch_root'])
    need(type(value['not_after']) in (int,float) and math.isfinite(value['not_after'])
         and value['not_after']>0,'EXPIRY')
    _closed(value['limits'],('maximum_execution_seconds','backup_stream_model','new_business_budget'))
    limits=value['limits'];need(type(limits['maximum_execution_seconds']) is int
        and limits['maximum_execution_seconds']==MAINTENANCE_EXECUTION_SECONDS
        and type(limits['backup_stream_model']) is str
        and limits['backup_stream_model']==BACKUP_STREAM_MODEL
        and type(limits['new_business_budget']) is int and limits['new_business_budget']==0,'LIMITS')
    return value


def _load_sources(resources,program,path):
    binding=resources.private(path.parent/'bindings.json',program['BINDING_SHA256'])
    b=_json(binding.raw)
    _closed(b,('schema','profile','authority','candidate_scope','entry_contract_sha','source_ref',
        'policy_ref','registry_path','consumer_module','consumer_function'))
    _sha(b['entry_contract_sha'])
    need(type(b['schema']) is int and b['schema']==1 and b['profile']=='GROUP_MAINTENANCE_BINDINGS_V1'
         and b['authority'] is False and b['candidate_scope']==resources.runtime.scope
         and b['entry_contract_sha']==MAINTENANCE_ENTRY_ADOPTION
         and b['consumer_module']=='wce.draft_group_maintenance_inventory'
         and b['consumer_function']=='run_fixed_case','BINDING')
    _ref(b['source_ref']);_ref(b['policy_ref']);registry=path_value(b['registry_path'])
    source_pin=resources.private(b['source_ref']['path'],b['source_ref']['sha256'])
    need(len(source_pin.raw)==b['source_ref']['bytes'],'SOURCE_SIZE')
    source=_decode_source(_json(source_pin.raw))
    policy_pin=resources.private(b['policy_ref']['path'],b['policy_ref']['sha256'])
    need(len(policy_pin.raw)==b['policy_ref']['bytes'],'POLICY_SIZE')
    review_pin=resources.private(path.parent/'acceptance.json',program['REVIEW_SHA256'])
    arm_pin=resources.private(path.parent/'arm.json',program['ARM_SHA256'])
    projection={'entry_contract_sha':MAINTENANCE_ENTRY_ADOPTION,'candidate_scope':resources.runtime.scope,
        'binding_sha256':program['BINDING_SHA256'],'source_sha256':source_pin.sha,
        'operation_id':source['operation_id'],'partition':source['partition'],'new_business_budget':0}
    review=_json(review_pin.raw)
    _closed(review,('schema','profile','authority','decision','projection','projection_sha256','review_ref'))
    need(type(review['schema']) is int and review['schema']==1
         and review['profile']=='GROUP_MAINTENANCE_EXTERNAL_ACCEPTANCE_V1' and review['authority'] is False
         and review['decision']=='ACCEPTED_EXACT_CASE_NO_BUSINESS_GRANT'
         and canonical(review['projection'])==canonical(projection)
         and review['projection_sha256']==digest(projection),'REVIEW')
    resources.acquire_evidence(review['review_ref'])
    arm=_json(arm_pin.raw)
    _closed(arm,('schema','profile','authority','review_sha256','projection_sha256','operation_id',
        'new_business_budget','not_after'))
    need(type(arm['schema']) is int and arm['schema']==1
         and arm['profile']=='GROUP_MAINTENANCE_FIXED_ARM_V1' and arm['authority'] is False
         and arm['review_sha256']==review_pin.sha and arm['projection_sha256']==digest(projection)
         and arm['operation_id']==source['operation_id'] and type(arm['new_business_budget']) is int
         and arm['new_business_budget']==0 and type(arm['not_after']) in (int,float)
         and math.isfinite(arm['not_after']) and time.time()<arm['not_after']<=source['not_after'], 'ARM')
    need(source['candidate_scope']==resources.runtime.scope,'C_CHANGED')
    return source_pin,source,policy_pin,registry,arm['not_after']


def _original_inputs(record):
    from .own_preupload_inputs import (_ORIGINAL_KEYS,KEY_TABLE_SHA,JOURNAL_SHA,_original_completion,_read)
    from .draft_group_selected_source_codec import ORIGINAL_QUEUE_SHA256,decode_manifest
    r=record.resources;s=record.source;o=s['original'];_closed(o,_ORIGINAL_KEYS)
    need(o['queue']['sha256']==ORIGINAL_QUEUE_SHA256 and o['key_table']['sha256']==KEY_TABLE_SHA
         and o['journal_binding_sha256']==o['journal_bindings']['sha256']==JOURNAL_SHA
         and type(o['member_count']) is int and o['member_count']==28
         and type(o['role_count']) is int and o['role_count']==109
         and o['effective_phase_state']=='STOPPED','ORIGINAL_REFS')
    loaded={}
    for name,ref in o.items():
        if type(ref) is dict:
            r.acquire_evidence(ref)
            if name not in ('v8_driver','phase_runner'):loaded[name]=_read(r,ref)
    _original_completion(r,o,loaded,s['owner_completion_ref'])
    projection=_read(r,s['member_projection_ref']);_closed(projection,('member_projection',))
    need(type(projection['member_projection']) is list and len(projection['member_projection'])==28,'FULL28')
    r.projection=projection;r.selection=r.acquire_evidence(s['selection_ref'])
    selected,_,selection_sha=decode_manifest(r.selection.raw,
        expected_member_projection=tuple(tuple(row) for row in projection['member_projection']))
    from .own_preupload_selected_files import decode_roots
    roots_raw=r.acquire_evidence(s['artifact_roots_ref']).raw
    roots,_=decode_roots(roots_raw,selected,loaded['journal_bindings']['flat_root'],
        expected_flat_manifest_ref=o['flat_manifest'])
    need(all(not path_value(s[workspace]).is_relative_to(path_value(root['absolute_path']))
        for workspace in ('scratch_root','backup_root') for root in roots.values()),'SOURCE_WORKSPACE_OVERLAP')
    for root in roots.values():
        path=path_value(root['absolute_path']);fd=r.pool.directory(path,owner=r)
        pin=tuple(root['physical_pin'])
        need(full(os.fstat(fd))==pin==full(path.lstat()),'SELECTED_ROOT_CHANGED')
        record.selected_dirs[str(path)]=(path,fd,pin)
    for name in ('queue','key_table','flat_manifest','title_adoption','title_mapping'):
        need({k:o[name][k] for k in ('path','sha256')}==loaded['v8_bindings'][name],'ORIGINAL_BINDING')
    from .own_preupload_derivation import original_member_rows
    original=original_member_rows(loaded['queue'],loaded['key_table'],loaded['flat_manifest'],
        loaded['v8_bindings'],loaded['title_adoption'],loaded['title_mapping'])
    rolemap=loaded['role_map']
    need(rolemap['profile']=='ORIGINAL109_PROJECT_ROLE_MAP_NOT_QUALIFICATION'
         and rolemap['authority'] is False and rolemap['SDK_queried'] is False
         and len(rolemap['rows'])==109 and rolemap['original_out']==o['original_out'],'ROLE_MAP')
    roles={};bykey={row['member_id']:(i+1,row) for i,row in enumerate(loaded['key_table']['members'])}
    for row in rolemap['rows']:
        ordinal,key=bykey[row['member_id']];short=row['slot'].split('--',1)[1]
        need(row['member_ordinal']==ordinal and row['prepare_request_key']==key['prepare']
             and row['request_key']==key['uploads'][short]
             and row['slot']==key['document_article_id']+'--'+short
             and row['original_tag']==f'm{ordinal:02d}-execute-{short}','ORIGINAL_ROLE')
        pair=(row['member_id'],row['slot']);need(pair not in roles,'DUP_ROLE');roles[pair]=row
    members=[m for m in selected['members'] if m['binding_sha256']==digest(s['binding'])]
    need([m['article_id'] for m in members]==s['partition']['member_ids']
         and {row['member_id'] for row in roles.values()
              if row['connection_id']==s['binding']['connection']}==set(s['partition']['member_ids']),
         'EXACT_PARTITION')
    record.members=members;record.full_members=selected['members']
    record.roots=roots;record.original=original;record.roles=roles
    record.selection_sha=selection_sha


def _full_source_files(record):
    """Read full28 once with rolling FDs; retain each actual leaf stat witness.

    This is source I/O, not a query/permission for another account. Holding the
    parent's original directory FD preserves no-follow naming after closing
    each member's raw-file reader; no source generation can be rebased.
    """
    from .own_preupload_selected_files import SelectedMemberFiles
    for member in record.full_members:
        _guard(record)
        record.resources.prepare_selected(member)
        with SelectedMemberFiles(record.resources,record.roots,member,
                    extra_raw_bytes=record.resources.derived_bytes) as files:
            record.resources.active_files=files
            try:
                for path,(_,pin) in files.root_pins.items():
                    fd=record.resources.pool.directory(path,owner=record.resources)
                    need(full(os.fstat(fd))==pin,'SELECTED_ROOT_CHANGED')
                    record.selected_dirs[str(path)]=(path,fd,pin)
                for view in files.files.values():
                    view.check();parent=record.resources.pool.directory(view.path.parent,owner=record.resources)
                    key=str(view.path);witness=(view.path,parent,view.pin)
                    old=record.selected_pins.get(key)
                    need(old is None or old==witness,'SELECTED_REBASE')
                    record.selected_pins[key]=witness
                files.check();_guard(record)
            finally:record.resources.active_files=None
        del files


def _qa(record):
    from .own_content_qa_join import check_import_package_contents
    from .own_preupload_qa import CONSUMER_FILES
    s=record.source
    projection={'schema':1,'profile':'GROUP_MAINTENANCE_QA_BINDING_PROJECTION_V1','authority':False,
        'binding':s['binding'],'operation_id':s['operation_id'],'partition':s['partition'],
        'selection_ref':s['selection_ref'],'artifact_roots_ref':s['artifact_roots_ref'],
        'member_projection_ref':s['member_projection_ref'],'dossier_ref':s['dossier_ref']}
    return check_import_package_contents(record.resources,dossier_ref=s['dossier_ref'],
        acceptance_ref=s['acceptance_ref'],selection_sha256=record.selection_sha,
        binding_projection_sha256=digest(projection),
        member_ids=tuple(m['article_id'] for m in json.loads(record.resources.selection.raw)['members']),
        selected_roots=record.roots,expected_consumer_files=tuple(CONSUMER_FILES)+
            ('own_content_qa_join.py','draft_group_maintenance_case.py','draft_group_maintenance_inventory.py','draft_group_pure_derived_cache.py'))


@dataclass(frozen=True)
class _HistoryStore:
    path:Path
    history_policy:object


def _slot_observation_in(workflow,db,profile,manifest,fingerprint,role,asset,H):
    """Observe original admission state; this is NOT upload eligibility.

    Maintenance must precede first preupload. Absence/order/UNKNOWN is therefore
    retained as an exact fact, never converted into a new send or all-success
    prerequisite. The original full OwnStore/H validation has already run.
    """
    from .draft_group_upload_proof_reads import read_original_upload_success_with_proofs_in
    from .own_response_archive import row_pin
    operation='cover' if asset['role']=='cover' else 'body'
    selector={'bundle_id':manifest['bundle_id'],'version':manifest['version'],'content_digest':fingerprint}
    target=workflow._target(profile,fingerprint,operation,asset['slot'])
    need(role['connection_id']==profile.connection_id and role['selector']==selector
         and role['asset']==asset and role['operation']==operation
         and role['project_derived_target_sha256']==target,'ROLE_TARGET')
    key=role['request_key']
    # Existing complete schema/H validators own each family. A matching original
    # key must still have no alien input/Group family in its actual namespace.
    need(db.execute('SELECT 1 FROM own_inputs WHERE request_key=? LIMIT 1',(key,)).fetchone() is None,
         'ORIGINAL_KEY_OTHER_NAMESPACE')
    for table,column in (('group_batches','request_key'),('group_operations','child_key'),
                         ('group_previews','request_key')):
        if db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name=?",(table,)).fetchone():
            need(db.execute('SELECT 1 FROM '+table+' WHERE '+column+'=? LIMIT 1',(key,)).fetchone() is None,
                 'ORIGINAL_KEY_OTHER_NAMESPACE')
    rows=list(db.execute('SELECT * FROM own_steps WHERE request_key=? OR target=? OR '
        '(manifest_digest=? AND operation=? AND slot=?)',(key,target,fingerprint,operation,asset['slot'])))
    actual=workflow._history(db,profile,key,operation=operation,selector=selector,
        slot=asset['slot'],history_locators=H)
    common={'authority':False,'new_business_budget':0,'selector':selector,'asset':asset,
        'slot':asset['slot'],'operation':operation,'request_key':key,'target':target,
        'original_tag':role['original_tag'],
        'upload_eligibility':'NOT_ASSERTED','project_once_eligibility':'NOT_ASSERTED'}
    if not rows:
        need(actual is None,'ORIGINAL_ADMISSION_CHANGED')
        # No own_steps row means no SDK intent/slot admission: own_steps is the
        # original atomic intent+admission table. A project intent may be spent;
        # this observation deliberately grants no permission to retry it.
        try:workflow._check_upload_order_in(db,profile,manifest,fingerprint,asset['slot'],history_locators=H)
        except WCEError as error:
            if error.code!='OWN_STEP_ORDER':raise
            order='PENDING_OR_UNKNOWN_PREDECESSOR'
        else:order='ORIGINAL_ORDER_SATISFIED'
        return dict(common,state=None,observation='ABSENT_VERIFIED_NO_ADMISSION_VERIFIED',
            original_row_pin=None,original_row_sha256=None,original_intent_sha=None,
            original_order=order,success_proof=None),None
    need(len(rows)==1 and actual is not None,'ORIGINAL_SLOT_COVERAGE');row=rows[0]
    need(dict(row)==dict(actual) and row['request_key']==key and row['target']==target
         and row['tenant']==profile.actor.tenant_id and row['principal']==profile.actor.principal_id
         and row['connection']==profile.connection_id and row['resource']==profile.resource_id,
         'ORIGINAL_SLOT_IDENTITY')
    workflow._step(db,profile,row,history_locators=H)
    if row['state']=='SUCCEEDED':
        facts,receipt=read_original_upload_success_with_proofs_in(workflow,db,profile,row['id'],history_locators=H)
        need(facts['selector']==selector and facts['asset']==asset and facts['slot']==asset['slot']
             and facts['operation']==operation and facts['base_step_pin']['id']==row['id'],'ORIGINAL_PROOF')
        receipt.collective_fence()
        return dict(common,state='SUCCEEDED',observation='ORIGINAL_SUCCESS_PROOF_VERIFIED',
            original_row_pin=row_pin(row),original_row_sha256=digest(dict(row)),original_intent_sha=row['intent_digest'],
            original_order='HISTORICAL_ADMISSION_PRESERVED',success_proof=facts),receipt
    need(row['state']=='RESULT_UNKNOWN','ORIGINAL_STATE')
    return dict(common,state='RESULT_UNKNOWN',observation='ORIGINAL_UNKNOWN_PRESERVED_NO_RESEND',
        original_row_pin=row_pin(row),original_row_sha256=digest(dict(row)),original_intent_sha=row['intent_digest'],
        original_order='HISTORICAL_ADMISSION_PRESERVED',success_proof=None),None


def _current(record,db,H):
    """Only a caller's actual RO/H safe point; never open a DB in guard()."""
    from .own_validation_scope import OwnedConnection,_transaction_marker
    from .draft_group_history_context import require_history
    from .own_selected_history import _PreparedHistoryReader,_policy_binding
    need(type(db) is OwnedConnection and _transaction_marker(db) is not None
         and db.execute('PRAGMA query_only').fetchone()[0]==1
         and db.execute('PRAGMA user_version').fetchone()[0] in (6,8,9),'RO_SAFE_POINT_REQUIRED')
    require_history(record.policy,db,H)
    record.policy.check(readonly=True,proof_reader=H.reader)
    need(_policy_binding(record.policy,'OPERATOR_ATTESTED')==record.source['binding'],'BINDING_CHANGED')
    from .own_workflow import OwnWorkflow
    from .own_preupload_selected_files import SelectedMemberFiles
    from .own_preupload_derivation import derive_document
    import tempfile
    reader=_PreparedHistoryReader(record.policy,db,H);receipts=[];members=[]
    workflow=object.__new__(OwnWorkflow)
    workflow.db=_HistoryStore(record.policy.root/'state.sqlite3',record.policy)
    workflow.policy=record.policy;workflow.history_locators=H
    try:
        for member in record.members:
            _guard(record);identity=member['article_id'];source=record.original[identity]
            need(record.resources.active_files is None,'ACTIVE_SELECTED')
            record.resources.prepare_selected(member)
            with SelectedMemberFiles(record.resources,record.roots,member,
                    extra_raw_bytes=record.resources.derived_bytes) as files:
                record.resources.active_files=files
                try:
                    relation=reader.prepared_relation(prepare_request_key=member['prepare_request_key'],selector=member['selector'])
                    manifest,fingerprint=reader._bundle_full(db,reader.profile,
                        member['selector']['bundle_id'],member['selector']['version'])
                    need(fingerprint==member['selector']['content_digest']
                         and relation['parameters_sha256']==member['import_receipt_sha256']
                         and relation['assets']==manifest['assets'],'PREPARED_CHANGED')
                    approval=member['historical_approval_sha256']
                    need((approval is None and relation['approval_state']=='ABSENT_VERIFIED'
                          and relation['historical_approvals']==[]) or
                         (approval is not None and any(row['body_sha256']==approval
                          for row in relation['historical_approvals'])),'HISTORICAL_APPROVAL_CHANGED')
                    def derive():
                        # Scratch is fixed source input, never account-root or caller chosen.
                        scratch=path_value(record.source['scratch_root'])
                        scratch_fd=record.resources.pool.directory(scratch,owner=record.resources)
                        info=os.fstat(scratch_fd)
                        need(stat.S_ISDIR(info.st_mode) and info.st_uid==os.getuid()
                             and stat.S_IMODE(info.st_mode)==0o700,'PRIVATE_SCRATCH')
                        with tempfile.TemporaryDirectory(prefix='maintenance-member-',dir=scratch) as work:
                            document=derive_document(files,source,scratch=work,guard=lambda:_guard(record))
                        return document
                    def fence():
                        _guard(record);files.check()
                    raw_inputs=tuple((key,'selected-original',view.raw)
                        for key,view in sorted(files.files.items()))
                    document=record.resources.derived_cache.resolve(record.resources,identity,raw_inputs,
                        {'member':member,'original_row':source},code_scope=record.scope,
                        code_token=(derive_document.__code__,),fence=fence,
                        reserve=record.resources.reserve_derived,derive=derive)
                    need(canonical(document)==canonical(manifest['document']),'FULL_DOCUMENT_CHANGED')
                    need(manifest['assets']==[{'asset_ref':image['asset_ref'],'role':image['role'],
                        'slot':image['slot'],'declared_type':image['artifact']['media_type'],
                        'size':image['artifact']['size'],'sha256':image['artifact']['sha256']}
                        for image in member['images']],'SELECTED_ASSET_SET')
                    article=document['articles'][0]
                    need(digest({key:article[key] for key in ('title','author','digest','source_url',
                        'cover_dimensions','cover_info','editorial_intent') if key in article})==member['settings_sha256'],
                        'SETTINGS_CHANGED')
                    uploads=[]
                    for asset in manifest['assets']:
                        role=record.roles[(identity,asset['slot'])]
                        observation,receipt=_slot_observation_in(workflow,db,reader.profile,manifest,
                            fingerprint,role,asset,H)
                        if receipt is not None:receipts.append(receipt)
                        uploads.append(observation)
                    need(len(uploads)==len(member['images'])==len(manifest['assets']),'ALL_ORIGINAL_SLOTS')
                    need(db.execute("SELECT 1 FROM own_steps s JOIN own_articles a ON a.digest=s.manifest_digest "
                        "WHERE s.operation='add' AND a.bundle=? LIMIT 1",(member['selector']['bundle_id'],)).fetchone() is None,
                        'ORDINARY_ADD_EXISTS')
                    members.append({'article_id':identity,'relation':relation,'document_sha':digest(document),'uploads':uploads})
                    files.check();reader.check()
                finally:record.resources.active_files=None
            del files,document,article,raw_inputs
        reader._check_all_history()
        for receipt in receipts:receipt.collective_fence()
        qa=_qa(record);_guard(record)
        return {'binding':record.source['binding'],'members':members,'qa':qa},receipts
    finally:reader.close()


@dataclass
class _BackupFD:
    """Idempotent ownership cell; dictionary transfer cannot leave a stale fd."""
    fd:int|None=None
    def close(self):
        fd,self.fd=self.fd,None
        if fd is not None:os.close(fd)


def _backup(record,manifestSHA,path):
    _sha(manifestSHA);path=path_value(path);root=path_value(record.source['backup_root'])
    need(path.parent==root,'BACKUP_ROOT')
    raw=record.resources.private(path,manifestSHA);value=_json(raw.raw,line=True)
    _closed(value,('schema','profile','authority','operation_id','source_version','source_kind',
        'code_scope','qualified_materials_sha','source_pin','raw_sha256','raw_bytes','backup_name'))
    version=value['source_version'];need(type(value['schema']) is int and value['schema']==1
        and value['profile']=='GROUP_OPERATOR_MAINTENANCE_RAW_DB_BACKUP_V1' and value['authority'] is False
        and type(version) is int and version in (6,8) and value['source_kind']=='OPERATOR_ATTESTED'
        and value['operation_id']==record.source['operation_id'] and value['code_scope']==record.scope
        and value['qualified_materials_sha']==record.source_pin.sha
        and path.name==value['operation_id']+'-before-schema'+str(version)+'-backup.json','BACKUP_MANIFEST')
    _sha(value['raw_sha256']);need(type(value['raw_bytes']) is int
        and 0<value['raw_bytes']<2**63,'BACKUP_BYTES')
    need(type(value['source_pin']) is list and len(value['source_pin'])==9
        and all(type(x) is int and x>=0 for x in value['source_pin'])
        and stat.S_ISREG(value['source_pin'][2]) and stat.S_IMODE(value['source_pin'][2])==0o600
        and value['source_pin'][3]==os.getuid() and value['source_pin'][5]==1
        and value['source_pin'][6]==value['raw_bytes'],'BACKUP_SOURCE_PIN')
    name=value['operation_id']+'-before-schema'+str(version)+'-'+value['raw_sha256']+'.sqlite3'
    need(value['backup_name']==name,'BACKUP_NAME');backup=root/name
    prior=record.backups.get(str(path))
    if prior is not None:
        need(prior[0]==manifestSHA and prior[1]==value,'BACKUP_REBASE');_check_backup(prior);return
    parent=record.resources.pool.directory(root,owner=record.resources);capacity(1,persistent=True)
    lease=_BackupFD()
    fd=os.open(name,os.O_RDONLY|os.O_NOFOLLOW|os.O_NONBLOCK,dir_fd=parent)
    try:
        lease.fd=fd
        info=os.fstat(fd);pin=full(info)
        need(stat.S_ISREG(info.st_mode) and info.st_uid==os.getuid()
             and stat.S_IMODE(info.st_mode)==0o600 and info.st_nlink==1
             and info.st_size==value['raw_bytes'] and pin==full(backup.lstat()),'BACKUP_FILE')
        h=sha256();count=0
        while count<value['raw_bytes']:
            _guard(record);block=os.read(fd,min(BACKUP_CHUNK_BYTES,value['raw_bytes']-count));need(bool(block),'BACKUP_SHORT')
            count+=len(block);h.update(block)
        need(os.read(fd,1)==b'' and h.hexdigest()==value['raw_sha256']
             and pin==full(os.fstat(fd))==full(backup.lstat()),'BACKUP_READBACK')
        record.backups[str(path)]=(manifestSHA,value,backup,lease,pin)
    except BaseException as original:
        close_all([lease.close] if lease.fd is not None else [lambda:os.close(fd)],original);raise


def _check_backup(prior):
    _,_,path,lease,pin=prior
    need(type(lease) is _BackupFD and type(lease.fd) is int,'BACKUP_CLOSED')
    fd=lease.fd
    need(full(os.fstat(fd))==pin==full(path.lstat()),'BACKUP_CHANGED')


def _checkpoint_observation_in(record,db,H,*,require_finished=False):
    """Only original same-op queries can authorize the history-only stage.

    The original query owns its own pending scope. This function neither sets
    SDK _MIGRATING/_SCOPE nor suppresses a check_pending failure. It never
    executes DDL/finish. Mutable marker/proof files remain owned by the original
    finish algorithm; only immutable checkpoints are stat-pinned by this case.
    """
    from .own_validation_scope import OwnedConnection,_transaction_marker
    from .draft_group_history_context import require_history
    from . import own_group_schema as group,own_group_prerequisite as neutral
    from .publication_contract import binding
    need(type(db) is OwnedConnection and _transaction_marker(db) is not None
         and db.execute('PRAGMA query_only').fetchone()[0]==1,'RO_SAFE_POINT_REQUIRED')
    require_history(record.policy,db,H)
    pending=False;found=[]
    for module,version in ((neutral,6),(group,8)):
        path=record.policy.root/module.CHECKPOINT
        if not os.path.lexists(path):
            need(not os.path.lexists(record.policy.root/module.MARKER),'CHECKPOINT_MISSING')
            if module is neutral:need(not os.path.lexists(record.policy.root/module.PROOF),'CHECKPOINT_MISSING')
            continue
        parent=record.resources.pool.directory(path.parent,owner=record.resources)
        before=full(os.stat(path.name,dir_fd=parent,follow_symlinks=False))
        need(stat.S_ISREG(before[2]) and stat.S_IMODE(before[2])==0o600
             and before[3]==os.getuid() and before[5]==1
             and 0<before[6]<=group.MAXIMUM
             and record.resources.pool.raw_bytes+record.resources.evidence_bytes+record.resources.derived_bytes+before[6]<=MAX_RAW_BYTES,
             'CHECKPOINT_BOUND')
        value,checksum=group._read_json(path,group.MAXIMUM)
        (neutral._strict if module is neutral else group._strict_checkpoint)(value)
        need(value['operation_id']==record.operation_id and value['code_scope']==record.scope
             and value['source_kind']=='OPERATOR_ATTESTED'
             and value['binding_sha']==binding(record.policy.data),'CHECKPOINT_CASE_CHANGED')
        if module is neutral:need(value['source_sha']==record.source_pin.sha,'CHECKPOINT_SOURCE_CHANGED')
        need(full(os.stat(path.name,dir_fd=parent,follow_symlinks=False))==before,'CHECKPOINT_CHANGED')
        prior=record.checkpoint_pins.get(str(path));witness=(path,parent,before,checksum)
        need(prior is None or prior==witness,'CHECKPOINT_REBASE')
        record.checkpoint_pins[str(path)]=witness
        manifest=Path(record.source['backup_root'])/(record.operation_id+'-before-schema'+str(version)+'-backup.json')
        meta_pin=record.resources.private(manifest,sha256(_read_manifest_bytes(record,manifest)).hexdigest())
        _backup(record,meta_pin.sha,manifest)
        backup=record.backups[str(manifest)][1]
        if module is neutral:need(backup['raw_sha256']==value['backup_sha'],'CHECKPOINT_BACKUP_CHANGED')
        marker=record.policy.root/module.MARKER
        if not os.path.lexists(marker):pending=True
        else:
            state,_=group._read_json(marker,8192)
            pending=pending or state.get('phase')=='PREPARED'
        found.append((module,checksum))
        del value
    # The latest pending core scope must be queried first; a neutral ordinary
    # ancestry query cannot bypass a later Group pending marker.
    ordered=list(reversed(found))
    for index,(module,checksum) in enumerate(ordered):
        kwargs=dict(operation_id=record.operation_id,checkpoint_sha=checksum,
                    history_policy=record.policy,history_locators=H)
        result=(module.query(db,'OPERATOR_ATTESTED',guard=lambda:_guard(record),**kwargs)
                if module is neutral else module.query_migration(db,'OPERATOR_ATTESTED',**kwargs))
        need(result.get('operation_id')==record.operation_id
             and result.get('state') in ('COMMITTED','NOT_COMMITTED'),'PENDING_QUERY_UNDETERMINED')
        if require_finished:
            need(result['state']=='COMMITTED','PENDING_NOT_COMMITTED')
            values=(module._files(db,allow_missing_marker=False) if module is neutral else module._files(db))
            need(values[1]==checksum and values[2]['phase']=='COMMITTED','PENDING_NOT_FINISHED')
        elif pending:
            # This is only a historical observation, never current qualification.
            # The caller will query+finish this latest original operation itself.
            break
    if require_finished:need(not pending,'PENDING_NOT_FINISHED')
    _guard(record)
    return pending


def _read_manifest_bytes(record,path):
    """Mechanical immutable manifest read to discover its actual SHA, no grant."""
    from .bounded_file import FileSource
    parent=record.resources.pool.directory(path.parent,owner=record.resources)
    before=full(os.stat(path.name,dir_fd=parent,follow_symlinks=False))
    need(stat.S_ISREG(before[2]) and stat.S_IMODE(before[2])==0o600
         and before[3]==os.getuid() and before[5]==1 and 0<before[6]<=MAX_SOURCE
         and record.resources.pool.raw_bytes+record.resources.evidence_bytes+record.resources.derived_bytes+before[6]<=MAX_RAW_BYTES,
         'BACKUP_MANIFEST')
    raw=FileSource(path.parent).read(path.name)
    need(len(raw)==before[6] and full(os.stat(path.name,dir_fd=parent,follow_symlinks=False))==before,'BACKUP_CHANGED')
    return raw


def _record(case):
    need(_assert_integrity is _INTEGRITY_FUNCTION and _assert_integrity.__code__ is _INTEGRITY_CODE,'TCB_CHANGED')
    _assert_integrity()
    need(type(case) is FixedMaintenanceCase and _ACTIVE is case,'UNISSUED')
    record=_ISSUED.get(case)
    need(record is not None and record.owner==(os.getpid(),threading.get_ident())
         and not record.closed and not record.poisoned,'UNISSUED')
    return record


def _guard(record):
    need(_assert_integrity is _INTEGRITY_FUNCTION and _assert_integrity.__code__ is _INTEGRITY_CODE,'TCB_CHANGED')
    _assert_integrity();record.resources.guard()
    need(not record.closed and not record.poisoned and record.owner==(os.getpid(),threading.get_ident())
         and time.monotonic()<record.deadline and time.time()<record.not_after
         and canonical(record.policy.value)==record.policy_raw
         and record.policy.path==record.policy_pin.path
         and record.source['operation_id']==record.operation_id,'LIFETIME')
    _check_program(record.wrapper,record.program_raw)
    # Actual current delegation/registry/owner/epoch/revocation, no OwnStore or
    # borrowed closed H. check_member uses original read-only metadata locks.
    from .own_connection_policy import ConnectionPolicy
    need(type(record.policy) is ConnectionPolicy and type(record.policy.check) is MethodType
         and record.policy.check.__func__ is ConnectionPolicy.check,'POLICY_METHOD')
    record.policy.check(readonly=True)
    for path,fd,pin in record.selected_dirs.values():
        need(full(os.fstat(fd))==pin==full(path.lstat()),'SELECTED_ROOT_CHANGED')
    for path,parent,pin in record.selected_pins.values():
        need(full(os.stat(path.name,dir_fd=parent,follow_symlinks=False))==pin,'SELECTED_CHANGED')
    for path,parent,pin,_ in record.checkpoint_pins.values():
        need(full(os.stat(path.name,dir_fd=parent,follow_symlinks=False))==pin,'CHECKPOINT_CHANGED')
    for receipt in record.receipts:receipt.collective_fence()
    for backup in record.backups.values():_check_backup(backup)


def require_fixed_maintenance_case(case):
    """Exact registry consumer entry. Returns the same object, no JSON permit."""
    case_record=_record(case)
    try:_guard(case_record)
    except BaseException:case_record.poisoned=True;raise
    return case


@dataclass
class _Record:
    resources:object
    policy:object
    policy_pin:object
    registry:Path
    source_pin:object
    source:dict
    scope:str
    deadline:float
    not_after:float
    wrapper:dict
    program_raw:bytes
    owner:tuple
    operation_id:str
    policy_raw:str
    current_sha:str|None=None
    members:object=None
    full_members:object=None
    roots:object=None
    original:object=None
    roles:object=None
    selection_sha:str|None=None
    receipts:tuple=()
    backups:object=None
    selected_pins:object=None
    selected_dirs:object=None
    checkpoint_pins:object=None
    phase:str='INITIALIZING'
    closed:bool=False
    poisoned:bool=False


def _issue_case():
    global _ACTIVE
    need(_assert_integrity is _INTEGRITY_FUNCTION and _assert_integrity.__code__ is _INTEGRITY_CODE,'TCB_CHANGED')
    _assert_integrity();_sha(MAINTENANCE_ENTRY_ADOPTION);need(_ACTIVE is None,'NESTED')
    root,scope,path,program,wrapper,raw=_preflight();resources=None
    try:
        resources=_Resources(root,scope,wrapper['ABSOLUTE_DEADLINE'])
        helper=resources.private(path,wrapper['BOOTSTRAP_SHA']);need(helper.raw==raw,'HELPER_CHANGED')
        source_pin,source,policy_pin,registry,arm_expiry=_load_sources(resources,program,path)
        from .own_connection_policy import load_policy,ConnectionPolicy
        policy=load_policy(policy_pin.path)
        need(type(policy) is ConnectionPolicy and policy.value['schema']==2
             and policy.value['registry_path']==str(registry) and registry.name=='connections.json', 'CURRENT_POLICY')
        need(not path_value(source['scratch_root']).is_relative_to(policy.root)
             and not path_value(source['backup_root']).is_relative_to(policy.root),'PROJECT_WORKSPACE_REQUIRED')
        from .own_selected_history import _policy_binding,readonly_prepared_history
        need(_policy_binding(policy,'OPERATOR_ATTESTED')==source['binding'],'CURRENT_BINDING')
        record=_Record(resources,policy,policy_pin,registry,source_pin,source,scope,wrapper['ABSOLUTE_DEADLINE'],
            min(source['not_after'],arm_expiry),wrapper,raw,(os.getpid(),threading.get_ident()),
            source['operation_id'],canonical(policy.value),backups={},selected_pins={},selected_dirs={},checkpoint_pins={})
        from .draft_group_pure_derived_cache import EntryDerivedCache
        from .own_preupload_derivation import derive_document
        resources.derived_cache=EntryDerivedCache(resources,scope,(derive_document.__code__,),
            result_keys=('format','policy','articles'))
        _original_inputs(record)
        _full_source_files(record)
        first=None
        from .own_fd_domain import regular_fd_domain
        with regular_fd_domain(deadline=record.deadline):
            from .draft_group_history_context import readonly_history_snapshot
            with readonly_history_snapshot(policy,policy.root/'state.sqlite3') as (db,H):
                pending=_checkpoint_observation_in(record,db,H)
            if pending:
                qa=_qa(record);record.not_after=min(record.not_after,qa['not_after_wall'])
                record.phase='CURRENT_PENDING_HISTORY_OBSERVATION'
            else:
                with readonly_prepared_history(policy) as reader:
                    first,receipts=_current(record,reader.sql,reader.history)
                    second,second_receipts=_current(record,reader.sql,reader.history)
                    need(canonical(first)==canonical(second),'DOUBLE_PASS_CHANGED')
                    for receipt in (*receipts,*second_receipts):receipt.collective_fence()
                    record.receipts=tuple(second_receipts)
                record.not_after=min(record.not_after,first['qa']['not_after_wall'])
                record.current_sha=digest(first);record.phase='CURRENT_QUALIFIED'
        _guard(record)
        case=object.__new__(FixedMaintenanceCase);_ISSUED[case]=record;_ACTIVE=case
        require_fixed_maintenance_case(case);return case
    except BaseException as original:
        if _ACTIVE is not None:_close_case(_ACTIVE,original=original)
        else:
            close_all(([lambda:resources.close(original=original)] if resources is not None else [])+
                [lambda:os.close(wrapper['BOOTSTRAP_FD'])],original)
        raise


def _close_case(case,*,original=None):
    global _ACTIVE
    record=_ISSUED.pop(case,None)
    if record is None:return
    record.closed=True
    if _ACTIVE is case:_ACTIVE=None
    close_all([item[3].close for item in record.backups.values()]+
        [lambda:record.resources.close(original=original),
         lambda:os.close(record.wrapper['BOOTSTRAP_FD'])],original)


@contextmanager
def enter_fixed_maintenance_case():
    case=_issue_case()
    try:
        yield case
        case.guard()
    except BaseException as original:_close_case(case,original=original);raise
    else:_close_case(case)


_ISSUE_CODE=_issue_case.__code__
_ENTER_CODE=enter_fixed_maintenance_case.__wrapped__.__code__


def _call_snapshot(module):
    values=[]
    for name,value in vars(module).items():
        if inspect.isfunction(value):values.append((module,name,value,value.__code__,value.__defaults__,
            None if value.__kwdefaults__ is None else dict(value.__kwdefaults__)))
        elif inspect.isclass(value) and value.__module__==module.__name__:
            for key,method in vars(value).items():
                actual=(method.__func__ if type(method) in (classmethod,staticmethod)
                        else method.fget if type(method) is property else method)
                if inspect.isfunction(actual):values.append((value,key,method,actual.__code__,actual.__defaults__,
                    None if actual.__kwdefaults__ is None else dict(actual.__kwdefaults__)))
    return values


def _assert_integrity():
    for module,name,original in _CLASS_BINDINGS:
        need(vars(module).get(name) is original,'TCB_CHANGED')
    for owner,name,original,code,defaults,kwdefaults in _CALLS:
        actual=vars(owner).get(name)
        function=(actual.__func__ if type(actual) in (classmethod,staticmethod)
                  else actual.fget if type(actual) is property else actual)
        need(actual is original and inspect.isfunction(function) and function.__code__ is code
             and function.__defaults__==defaults and function.__kwdefaults__==kwdefaults,'TCB_CHANGED')
    need(BOOTSTRAP_KEYS==_FIXED_CONSTANTS[0] and BOOTSTRAP_BODY==_FIXED_CONSTANTS[1]
         and WRAPPER_KEYS==_FIXED_CONSTANTS[2] and WRAPPER_BODY==_FIXED_CONSTANTS[3]
         and MAINTENANCE_ENTRY_ADOPTION==_FIXED_CONSTANTS[4]
         and (BACKUP_STREAM_MODEL,BACKUP_CHUNK_BYTES,MAINTENANCE_EXECUTION_SECONDS)==_FIXED_CONSTANTS[5:],
         'TCB_CONSTANT_CHANGED')


# Snapshot actual parser/validator/resource functions, no runtime/account call.
from . import (own_preupload_inputs as _inputs,own_preupload_derivation as _derive,
    own_preupload_selected_files as _selected,own_preupload_qa as _qa_module,
    own_content_qa_join as _join,own_selected_history as _history,
    draft_group_upload_proof_reads as _proofs,own_step_history as _step,
    own_connection_policy as _policy,own_connection_registry as _registry,
    draft_group_pin_resources as _pins,own_workflow as _workflow,
    own_prepared_history as _prepared,own_history_source as _history_source,
    own_history_locators as _locators,draft_group_history_context as _history_context,
    own_validation_scope as _validation,own_response_archive as _archive,
    own_preupload_sources as _sources,own_body_recovery as _recovery,
    own_store as _store,own_lineage as _lineage,import_images as _images,
    draft_group_pure_derived_cache as _pure_derived_cache,
    local_html_import as _html,documents as _documents,
    draft_group_source_members as _members,draft_group_selected_source_codec as _selected_codec,
    own_group_schema as _group_schema,own_group_prerequisite as _prerequisite)
_FIXED_CONSTANTS=(BOOTSTRAP_KEYS,BOOTSTRAP_BODY,WRAPPER_KEYS,WRAPPER_BODY,MAINTENANCE_ENTRY_ADOPTION,
    BACKUP_STREAM_MODEL,BACKUP_CHUNK_BYTES,MAINTENANCE_EXECUTION_SECONDS)
_INTEGRITY_FUNCTION=_assert_integrity
_INTEGRITY_CODE=_assert_integrity.__code__
_DEPENDENCIES=(_inputs,_derive,_selected,_qa_module,_join,_history,_proofs,_step,_policy,_registry,_pins,_workflow,
    _prepared,_history_source,_locators,_history_context,_validation,_archive,_sources,_recovery,
    _store,_lineage,_images,_html,_documents,_members,_selected_codec,_group_schema,_prerequisite,_pure_derived_cache)
_CLASS_BINDINGS=tuple((module,name,value) for module in (sys.modules[__name__],*_DEPENDENCIES)
    for name,value in vars(module).items() if inspect.isclass(value))
_CALLS=tuple(item for module in (sys.modules[__name__],*_DEPENDENCIES) for item in _call_snapshot(module))
