"""UNARMED proposal: normal neutral6→8→9 caller, never Group admission.

The actual compiled case producer is not implemented here. No free JSON,
source bool, caller-selected policy or constructor can authorize this entry.
"""
from contextlib import contextmanager
from hashlib import sha256
from pathlib import Path
import json,math,os,sqlite3,stat,sys,time

from .contracts import WCEError
from .service import canonical
from .own_connection_policy import ConnectionPolicy,locked
from .own_connection_broker import _startup_gate
from .own_history_source import owned_connection,connection_source
from .own_history_locators import history_scope
from .draft_group_history_context import history_policy_context,require_history
from .own_validation_scope import OwnedConnection
from .own_fd_domain import regular_fd_domain
from .draft_group_pin_resources import capacity,close_all,full
from .draft_group_maintenance_case import BACKUP_CHUNK_BYTES
from . import own_group_prerequisite as neutral
from . import own_group_schema as group

CASE_ADOPTION_SHA = None
SOURCE_KIND = 'OPERATOR_ATTESTED'
CHUNK = BACKUP_CHUNK_BYTES


def need(value, code='GROUP_OPERATOR_MAINTENANCE_HOLD'):
    if value is not True:raise WCEError(code)


class _Resources:
    """Mechanical context owner; every exit is attempted, first error retained."""
    def __init__(self):self.callbacks=[]
    def enter(self, cm):
        callback=lambda original:cm.__exit__(None if original is None else type(original),
            original,None if original is None else original.__traceback__)
        value=cm.__enter__()
        try:self.callbacks.append(callback);return value
        except BaseException as original:
            if callback not in self.callbacks:close_all([lambda:callback(original)],original)
            raise
    def __enter__(self):return self
    def __exit__(self,kind,original,tb):
        callbacks,self.callbacks=self.callbacks,[]
        close_all([lambda c=c:c(original) for c in reversed(callbacks)],original)
        return False


def _guard(case):
    need(type(CHUNK) is int and CHUNK==BACKUP_CHUNK_BYTES==1024*1024,
         'GROUP_MAINTENANCE_CHUNK_CHANGED')
    need(type(case.deadline) in (int,float) and math.isfinite(case.deadline)
         and time.monotonic()<case.deadline,'GROUP_MAINTENANCE_DEADLINE')
    # Actual issued case keeps its already-held files/QA/proofs/policy/op pins.
    # This must NOT reopen ordinary full current while migration is pending.
    case.guard()


@contextmanager
def _exclusion(case):
    policy=case.policy
    need(type(policy) is ConnectionPolicy and type(case.registry) is type(Path('/')))
    from .publication_store import PublicationStore
    from .own_replacement_files import folder
    store=PublicationStore(policy,case.registry)
    with _Resources() as owner:
        capacity(2,persistent=True)
        owner.enter(_startup_gate(policy,case.deadline))
        held=[]
        def take(path,existing):
            capacity(2,persistent=True)  # locked opens parent plus leaf transiently.
            fd=owner.enter(locked(path,nonblocking=True,existing=existing))
            held.append((path,fd,full(os.fstat(fd))))
        # No drain, kill, stale endpoint removal or busy-owner bypass lives here.
        take(policy.root/'connection.lock',True)
        take(case.registry.parent/'connection-setup.lock',True)
        folder(store.anchor_root,create=True);folder(store.anchor,create=True)
        take(store.anchor/'publication.lock',False)
        for name in ('publication-dispatch.lock','connection-policy.lock',
                     'connection-import.lock','connection-token.lock'):
            take(policy.root/name,True)
        def guard():
            _guard(case)
            for path,fd,pin in held:
                need(pin==full(os.fstat(fd))==full(path.lstat()),'GROUP_MAINTENANCE_LOCK_CHANGED')
        guard();yield guard;guard()


@contextmanager
def _transaction(case, held, *, readonly):
    if not readonly:case.require_migration_ready()
    policy=case.policy;path=policy.root/'state.sqlite3'
    opener=(group.readonly_connection(path) if readonly else
            owned_connection(path,readonly=False,isolation_level=None,timeout=5))
    with _Resources() as owner:
        db=owner.enter(opener);db.row_factory=sqlite3.Row
        need(type(db) is OwnedConnection and connection_source(db) is not None)
        if not readonly:
            db.execute('PRAGMA foreign_keys=ON');db.execute('BEGIN IMMEDIATE')
        need(db.in_transaction)
        try:
            with _Resources() as contexts:
                contexts.enter(history_policy_context(path,db,policy))
                history=contexts.enter(history_scope(policy,db))
                def guard():
                    held();connection_source(db).guard();require_history(policy,db,history)
                    policy.check(readonly=True,proof_reader=None if history is None else history.reader)
                guard();yield db,history,guard;guard()
            # Real normal Owned commit, after the actual H scope has exited.
            # No contextmanager auto-commit, SQL COMMIT string or fake receipt.
            if not readonly:
                try:
                    OwnedConnection.commit(db)
                    need(not db.in_transaction,'GROUP_MAINTENANCE_COMMIT_UNKNOWN')
                except BaseException:
                    raise WCEError('GROUP_MAINTENANCE_COMMIT_UNKNOWN') from None
        except BaseException as original:
            # Rollback may close local SQL but never clears PREPARED files or
            # converts a commit error into a safe retry/ROLLED_BACK assertion.
            if db.in_transaction:close_all([db.rollback],original)
            raise


@contextmanager
def _directory(path):
    """Descriptor-relative NOFOLLOW ancestry; mechanical ownership only."""
    path=Path(path)
    need(path.is_absolute() and '..' not in path.parts and len(path.parts)<=32)
    fds=[];chain=[];original=None;fd=None
    try:
        capacity(1,persistent=True);fd=os.open('/',os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW);fds.append(fd)
        for name in path.parts[1:]:
            parent=fd;capacity(1,persistent=True)
            fd=os.open(name,os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW|os.O_NONBLOCK,dir_fd=parent)
            fds.append(fd);chain.append((parent,name,fd,full(os.fstat(fd))[:5]))
        def fence():
            for parent,name,item,core in chain:
                a=os.fstat(item);b=os.stat(name,dir_fd=parent,follow_symlinks=False)
                need(stat.S_ISDIR(a.st_mode) and full(a)[:5]==core==full(b)[:5])
        fence();yield fd,fence;fence()
    except BaseException as error:original=error;raise
    finally:
        # If a post-open append is interrupted before ownership transfer,
        # retain/close that actual local FD as well; never double-close one
        # whose append completed before the interruption.
        if fd is not None and fd not in fds:fds.append(fd)
        close_all([lambda fd=fd:os.close(fd) for fd in reversed(fds)],original)


def _regular(info, maximum):
    need(stat.S_ISREG(info.st_mode) and info.st_uid==os.getuid()
         and stat.S_IMODE(info.st_mode)==0o600 and info.st_nlink==1
         and 0<info.st_size<=maximum,'GROUP_MAINTENANCE_BACKUP_FILE')


def _database(info, *, exact_size=None):
    """Validate a finite stage-local stream, separate from retained JSON/RAM.

    The caller freezes the actual source stat under its normal RO/H and writer
    exclusion. Every copy/readback must equal that size and all existing pins.
    No supplied JSON or free-space value can select an arbitrary larger limit.
    """
    need(stat.S_ISREG(info.st_mode) and info.st_uid==os.getuid()
         and stat.S_IMODE(info.st_mode)==0o600 and info.st_nlink==1
         and type(info.st_size) is int and 0<info.st_size<2**63,
         'GROUP_MAINTENANCE_BACKUP_FILE')
    if exact_size is not None:
        need(type(exact_size) is int and 0<exact_size<2**63
             and info.st_size==exact_size,'GROUP_MAINTENANCE_BACKUP_FILE')


def _hash_fd(fd, size, guard):
    value=sha256();offset=0
    while offset<size:
        guard();raw=os.pread(fd,min(CHUNK,size-offset),offset);need(len(raw)>0)
        value.update(raw);offset+=len(raw)
    need(not os.pread(fd,1,size));guard()
    return value.hexdigest()


def _new_json(directory,name,value,guard):
    raw=(canonical(value)+'\n').encode();capacity(1,persistent=True)
    created=True
    try:fd=os.open(name,os.O_RDWR|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW|os.O_NONBLOCK,0o600,dir_fd=directory)
    except FileExistsError:
        created=False;capacity(1,persistent=True)
        fd=os.open(name,os.O_RDONLY|os.O_NOFOLLOW|os.O_NONBLOCK,dir_fd=directory)
    original=None
    try:
        if created:
            pending=memoryview(raw)
            while pending:
                count=os.write(fd,pending);need(type(count) is int and count>0);pending=pending[count:]
        info=os.fstat(fd);_regular(info,1024*1024)
        need(info.st_size==len(raw) and os.pread(fd,len(raw)+1,0)==raw)
        os.fsync(fd);os.fsync(directory);guard()
        need(full(info)==full(os.fstat(fd))==full(os.stat(name,dir_fd=directory,follow_symlinks=False)))
        return sha256(raw).hexdigest()
    except BaseException as error:original=error;raise
    finally:close_all([lambda:os.close(fd)],original)


def _backup(case, held, version):
    """Fresh exact raw DB bytes/readback, under external writer exclusion+RO H.

    Caller invokes this only in a stable pre-maintenance snapshot. It is not
    backup_before_migration (that helper intentionally returns for schema6/8).
    """
    group._id(case.operation_id);need(version in (6,8))
    with _directory(case.policy.root) as (source_dir,source_fence), _directory(case.backup_root) as (out,out_fence):
        out_info=os.fstat(out)
        need(out_info.st_uid==os.getuid() and stat.S_IMODE(out_info.st_mode)==0o700)
        capacity(1,persistent=True);source=os.open('state.sqlite3',os.O_RDONLY|os.O_NOFOLLOW|os.O_NONBLOCK,dir_fd=source_dir)
        original=None
        try:
            before=os.fstat(source);_database(before)
            need((before.st_dev,before.st_ino)==case.policy.database_pin[:2])
            def guard():
                held();source_fence();out_fence();group._no_sidecars(case.policy.root/'state.sqlite3')
                need(full(before)==full(os.fstat(source))==full(os.stat('state.sqlite3',dir_fd=source_dir,follow_symlinks=False)))
            digest=_hash_fd(source,before.st_size,guard)
            name=case.operation_id+'-before-schema'+str(version)+'-'+digest+'.sqlite3'
            capacity(1,persistent=True)
            created=True
            try:copy=os.open(name,os.O_RDWR|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW|os.O_NONBLOCK,0o600,dir_fd=out)
            except FileExistsError:
                created=False;capacity(1,persistent=True)
                copy=os.open(name,os.O_RDONLY|os.O_NOFOLLOW|os.O_NONBLOCK,dir_fd=out)
            try:
                offset=0
                while created and offset<before.st_size:
                    guard();chunk=os.pread(source,min(CHUNK,before.st_size-offset),offset);need(len(chunk)>0)
                    rest=memoryview(chunk)
                    while rest:
                        count=os.write(copy,rest);need(type(count) is int and count>0);rest=rest[count:]
                    offset+=len(chunk)
                copied=os.fstat(copy);_database(copied,exact_size=before.st_size)
                need(copied.st_size==before.st_size and _hash_fd(copy,copied.st_size,guard)==digest)
                os.fsync(copy);os.fsync(out)
                need(full(copied)==full(os.fstat(copy))==full(os.stat(name,dir_fd=out,follow_symlinks=False)))
            except BaseException as error:
                close_all([lambda:os.close(copy)],error);raise
            else:os.close(copy)
            # Independent FD readback after the actual writer FD is closed.
            capacity(1,persistent=True);verify=os.open(name,os.O_RDONLY|os.O_NOFOLLOW|os.O_NONBLOCK,dir_fd=out)
            try:
                actual=os.fstat(verify);_database(actual,exact_size=before.st_size)
                need(full(actual)==full(copied) and _hash_fd(verify,actual.st_size,guard)==digest
                     and full(actual)==full(os.fstat(verify))==full(os.stat(name,dir_fd=out,follow_symlinks=False)))
            except BaseException as error:
                close_all([lambda:os.close(verify)],error);raise
            else:os.close(verify)
            manifest={'schema':1,'profile':'GROUP_OPERATOR_MAINTENANCE_RAW_DB_BACKUP_V1','authority':False,
                'operation_id':case.operation_id,'source_version':version,'source_kind':SOURCE_KIND,
                'code_scope':case.code_scope,'qualified_materials_sha':case.source_sha,
                'source_pin':list(full(before)),'raw_sha256':digest,'raw_bytes':before.st_size,'backup_name':name}
            manifest_name=case.operation_id+'-before-schema'+str(version)+'-backup.json'
            manifest_sha=_new_json(out,manifest_name,manifest,guard)
            guard();case.require_backup(manifest_sha,case.backup_root/manifest_name)
            return digest
        except BaseException as error:original=error;raise
        finally:close_all([lambda:os.close(source)],original)


def _checkpoint(case,module):
    path=case.policy.root/module.CHECKPOINT
    if not os.path.lexists(path):return None
    # Original strict checkpoint reader/validator, never free JSON/caller ID.
    value,checksum=group._read_json(path,64*1024*1024)
    (neutral._strict if module is neutral else group._strict_checkpoint)(value)
    need(value['operation_id']==case.operation_id and value['source_kind']==SOURCE_KIND,
         'GROUP_MAINTENANCE_ORIGINAL_OPERATION_REQUIRED')
    return checksum


def _read_backup_manifest(path):
    """Read this fullstat manifest, not the SDK wire's signed32 JSON dialect."""
    from .own_bootstrap_security import unique
    def integer(text):
        value=int(text);need(0<=value<2**64);return value
    def reject(_):raise WCEError('GROUP_MAINTENANCE_BACKUP_FILE')
    with _directory(path.parent) as (directory,fence):
        capacity(1,persistent=True)
        fd=os.open(path.name,os.O_RDONLY|os.O_NOFOLLOW|os.O_NONBLOCK,dir_fd=directory)
        original=None
        try:
            info=os.fstat(fd);_regular(info,1024*1024)
            raw=os.pread(fd,info.st_size+1,0)
            need(len(raw)==info.st_size)
            value=json.loads(raw.decode('utf-8'),object_pairs_hook=unique,
                parse_int=integer,parse_float=reject,parse_constant=reject)
            need(type(value) is dict and raw==(canonical(value)+'\n').encode())
            fence();need(full(info)==full(os.fstat(fd))==full(
                os.stat(path.name,dir_fd=directory,follow_symlinks=False)))
            return value,sha256(raw).hexdigest()
        except BaseException as error:original=error;raise
        finally:close_all([lambda:os.close(fd)],original)


def _require_saved_backup(case,version,*,expected_raw_sha=None):
    path=case.backup_root/(case.operation_id+'-before-schema'+str(version)+'-backup.json')
    value,checksum=_read_backup_manifest(path)
    need(value['schema']==1 and type(value['schema']) is int and value['authority'] is False
         and value['profile']=='GROUP_OPERATOR_MAINTENANCE_RAW_DB_BACKUP_V1'
         and value['operation_id']==case.operation_id and value['source_version']==version
         and value['source_kind']==SOURCE_KIND)
    if expected_raw_sha is not None:need(value['raw_sha256']==expected_raw_sha)
    # Genuine case checks the held original provenance and independent actual
    # complete raw file/hash, never just this manifest's presence or bool.
    case.require_backup(checksum,path)


def _query_finish(case,held,module,checksum):
    with _transaction(case,held,readonly=True) as (db,history,guard):
        kwargs=dict(operation_id=case.operation_id,checkpoint_sha=checksum,
                    history_policy=case.policy,history_locators=history)
        result=(module.query(db,SOURCE_KIND,guard=guard,**kwargs) if module is neutral else
                module.query_migration(db,SOURCE_KIND,**kwargs))
        need(result['state'] in ('COMMITTED','NOT_COMMITTED'),'GROUP_MAINTENANCE_QUERY_UNKNOWN')
        finish=module.finish if module is neutral else module.finish_marker
        finished=finish(db,SOURCE_KIND,guard=guard,**kwargs)
        need(finished==result and db.total_changes==0,'GROUP_MAINTENANCE_FINISH_UNKNOWN')
        return result


def _run_case(case,held):
    neutral_sha=_checkpoint(case,neutral);group_sha=_checkpoint(case,group)
    # Pin both original backups before any marker finalization. The newest
    # pending core stage must be queried/finished before stable neutral
    # ancestry: neutral.query intentionally cannot bypass a pending core gate.
    if neutral_sha is not None:
        value,_=group._read_json(case.policy.root/neutral.CHECKPOINT,64*1024*1024)
        _require_saved_backup(case,6,expected_raw_sha=value['backup_sha'])
    if group_sha is not None:_require_saved_backup(case,8)
    for module,checksum in ((group,group_sha),(neutral,neutral_sha)):
        if checksum is None:continue
        result=_query_finish(case,held,module,checksum)
        if result['state']!='COMMITTED':return dict(state='NOT_COMMITTED',authority=False,operation_id=case.operation_id)
    with _transaction(case,held,readonly=True) as (db,history,guard):
        # This full-current check occurs only before any pending phase or after
        # its query+finish. Never re-enter ordinary full current mid-pending.
        case.require_current_in(db,history);version=neutral._version(db);need(version in (6,8,9))
    initial_version=version
    if version==6:
        need(neutral_sha is None and group_sha is None)
        with _transaction(case,held,readonly=True) as (db,history,guard):backup_sha=_backup(case,guard,6)
        from .publication_contract import binding
        with _transaction(case,held,readonly=False) as (db,history,guard):
            neutral_sha=neutral.prepare_checkpoint(db,SOURCE_KIND,operation_id=case.operation_id,
                binding_sha=binding(case.policy.data),code_scope=case.code_scope,source_sha=case.source_sha,
                backup_sha=backup_sha,guard=guard,history_policy=case.policy,registry=case.registry,history_locators=history)
        with _transaction(case,held,readonly=False) as (db,history,guard):
            neutral.prepare_coordination(db,SOURCE_KIND,operation_id=case.operation_id,checkpoint_sha=neutral_sha,
                guard=guard,history_policy=case.policy,registry=case.registry,history_locators=history)
        with _transaction(case,held,readonly=False) as (db,history,guard):
            neutral.migrate_in(db,SOURCE_KIND,operation_id=case.operation_id,checkpoint_sha=neutral_sha,
                guard=guard,history_policy=case.policy,history_locators=history)
        need(_query_finish(case,held,neutral,neutral_sha)['state']=='COMMITTED')
        version=8
    if version==8:
        need(group_sha is None)
        with _transaction(case,held,readonly=True) as (db,history,guard):
            case.require_current_in(db,history);_backup(case,guard,8)
        from .publication_contract import binding
        with _transaction(case,held,readonly=False) as (db,history,guard):
            group_sha=group.prepare_checkpoint(db,SOURCE_KIND,operation_id=case.operation_id,
                binding_sha=binding(case.policy.data),code_scope=case.code_scope,contract_sha=group.contract_sha(),
                guard=guard,history_policy=case.policy,history_locators=history)
        with _transaction(case,held,readonly=False) as (db,history,guard):
            group.migrate_in(db,SOURCE_KIND,operation_id=case.operation_id,checkpoint_sha=group_sha,
                guard=guard,history_policy=case.policy,history_locators=history)
        need(_query_finish(case,held,group,group_sha)['state']=='COMMITTED')
        version=9
    need(version==9 and group_sha is not None,'GROUP_MAINTENANCE_ORIGINAL_OPERATION_REQUIRED')
    with _transaction(case,held,readonly=True) as (db,history,guard):
        from .own_store import OwnStore
        OwnStore.check(db,SOURCE_KIND,case.policy,history=history)
        group._legacy_history(db,SOURCE_KIND,case.policy,history=history)
        case.require_current_in(db,history);need(group._version(db)==9)
    return dict(state='NORMAL_GROUP_MAINTENANCE_COMMITTED_AND_INDEPENDENTLY_QUERIED',authority=False,
        initial_version_this_run=initial_version,final_version=9,
        operation_id=case.operation_id,prerequisite_checkpoint_sha=neutral_sha,group_checkpoint_sha=group_sha,
        token_calls=0,HTTP_calls=0,Group_admission_calls=0)


def run_fixed_maintenance():
    # Pure unarmed refusal happens before importing a case producer or opening
    # any account. Filling a technical adoption is not a new user approval.
    need(type(CASE_ADOPTION_SHA) is str and len(CASE_ADOPTION_SHA)==64
         and all(c in '0123456789abcdef' for c in CASE_ADOPTION_SHA),
         'GROUP_MAINTENANCE_UNARMED')
    from .draft_group_maintenance_case import enter_fixed_maintenance_case
    with enter_fixed_maintenance_case() as case:
        return run_fixed_case(case)


def run_fixed_case(case):
    from .draft_group_maintenance_case import require_fixed_maintenance_case
    # Exact actual issuer/registry/frame, not a caller-created object shape.
    require_fixed_maintenance_case(case)
    _guard(case)
    need(type(case.policy) is ConnectionPolicy and case.code_scope==case.policy.value['candidate_scope'])
    group._id(case.operation_id);group._hash(case.source_sha);group._hash(case.code_scope)
    with regular_fd_domain(deadline=case.deadline):
        with _exclusion(case) as held:return _run_case(case,held)
