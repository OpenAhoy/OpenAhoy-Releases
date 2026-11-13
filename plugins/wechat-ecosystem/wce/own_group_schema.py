"""Explicit business8→9 SQL/ancestry component, not a maintenance authority.

Only a qualified maintenance producer holding the existing writer lock may
prepare these non-secret files and call migrate_in. No public route calls it.
It creates no grant/owner/token and never commits a caller's SQL transaction.
"""
from contextlib import closing, contextmanager
from contextvars import ContextVar
from hashlib import sha256
import json
import math
import os
from pathlib import Path
import re
import sqlite3

from .contracts import WCEError
from .service import canonical, digest

MIGRATION_SCHEMA = """
CREATE TABLE group_schema_migrations(
 id INTEGER PRIMARY KEY CHECK(typeof(id)='integer' AND id=1),
 operation_id TEXT NOT NULL UNIQUE, checkpoint_sha TEXT NOT NULL,
 source_kind TEXT NOT NULL CHECK(source_kind IN ('SYNTHETIC_SETUP','OPERATOR_ATTESTED')));
CREATE TRIGGER group_schema_migration_no_update BEFORE UPDATE ON group_schema_migrations
 BEGIN SELECT RAISE(ABORT,'GROUP_SCHEMA_ANCESTRY_IMMUTABLE'); END;
CREATE TRIGGER group_schema_migration_no_delete BEFORE DELETE ON group_schema_migrations
 BEGIN SELECT RAISE(ABORT,'GROUP_SCHEMA_ANCESTRY_IMMUTABLE'); END;
"""
PROFILE = 'GROUP_BUSINESS_8_TO_9_CHECKPOINT_V2'
MARKER = 'group-schema-migration.json'
CHECKPOINT = 'group-schema-checkpoint.json'
_MIGRATING = ContextVar('trusted_group_schema_migration', default=None)
_HASH = re.compile('[a-f0-9]{64}\\Z')
_ID = re.compile('[a-zA-Z0-9_-]{1,128}\\Z')
MAXIMUM = 64 * 1024 * 1024
# Only columns actually mutated by the frozen033 legacy implementation.
_MUTABLE = {
 'own_approvals': {'cancelled'},
 'own_steps': {'state','result','result_digest','completed','readback'},
 'own_body_recoveries': {'state','result','result_digest','completed','diagnostic','diagnostic_digest'},
 'own_body_followups': {'state','result','result_digest','completed'},
 'own_body_attempts': {'state','result','result_digest','completed','observation','observation_digest'},
 'own_lineage_replacements': {'state','result','result_digest','proof_name','proof_sha','completed'},
 'own_draft_restores': {'state','result','result_digest','proof_name','proof_sha','completed','readback'},
 'own_draft_restore_reads': {'state','response_sha','comparison'},
 'publication_policy': {'enabled','retired'},
 'publication_intents': {'review_id','snapshot_sha','state','submit_count','submit_claim_seq','submit_ms',
     'task_kind','task_digits','task_wire_type','task_raw_token','platform_status','effect','url_evidence',
     'query_used','query_seq','last_proof_sha'},
 'publication_query_claims': {'state','proof_sha'},
}
_DERIVED_LOCKS = frozenset(('own_resource_locks','own_lineage_locks','own_draft_restore_locks'))


def fail(code='GROUP_SCHEMA_UNVERIFIED'):
    raise WCEError(code)


def _hash(value):
    if type(value) is not str or not _HASH.fullmatch(value): fail()
    return value


def _id(value):
    if type(value) is not str or not _ID.fullmatch(value): fail()
    return value


def _root(db):
    rows = db.execute('PRAGMA database_list').fetchall()
    path = next((r[2] for r in rows if r[1] == 'main'), '')
    if type(path) is not str or not path: fail('GROUP_SCHEMA_FILE_REQUIRED')
    value=Path(path)
    if not value.is_absolute() or value.name!='state.sqlite3' or '..' in value.parts:fail('GROUP_SCHEMA_FILE_REQUIRED')
    from .own_bootstrap_security import path_check
    path_check(value);path_check(value.parent,True)
    return value.parent


def _version(db):
    from .own_store import APP_ID
    version = db.execute('PRAGMA user_version').fetchone()[0]
    if db.execute('PRAGMA application_id').fetchone()[0] != APP_ID or version not in (8,9): fail()
    return version


def legacy_schema():
    from .own_store import SCHEMA
    from .own_lineage import SCHEMA as LINEAGE
    from .own_lineage_replacement import SCHEMA as REPLACEMENT
    from .publication_store import ALL_SCHEMA as PUBLICATION
    from .own_draft_restore_store import SCHEMA as RESTORE
    return SCHEMA + LINEAGE + REPLACEMENT + PUBLICATION + RESTORE


def _group_schema():
    from .draft_group_store import SCHEMA
    if type(SCHEMA) is not str or not SCHEMA.strip(): fail()
    return SCHEMA


def contract_sha():
    return digest({'profile':PROFILE,'base':8,'target':9,
        'legacy_ddl_sha':sha256(legacy_schema().encode()).hexdigest(),
        'group_ddl_sha':sha256(_group_schema().encode()).hexdigest(),
        'migration_ddl_sha':sha256(MIGRATION_SCHEMA.encode()).hexdigest(),
        'delta_profile':'FROZEN033_LEGACY_TYPED_PINS_AND_MONOTONE_RESULTS_V1',
        'ordinary_migration':False,'new_grants':False})


def _fingerprint(db):
    from .storage import _normalized_sql
    master = [tuple(r[:3]) + (_normalized_sql(r[3]) if r[3] is not None else None,)
        for r in db.execute('SELECT type,name,tbl_name,sql FROM sqlite_master ORDER BY type,name')]
    detail = {}
    for (name,) in db.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"):
        quoted = '"' + name.replace('"','""') + '"'
        detail[name] = {key: [tuple(r) for r in db.execute('PRAGMA '+key+'('+quoted+')')]
            for key in ('table_info','foreign_key_list','index_list')}
    return master, detail


def check_layout(db, source_kind, *, group_schema=None):
    """Full exact composite9; does not call OwnStore or any history validator."""
    from .own_store import APP_ID
    if type(source_kind) is not str or source_kind not in ('SYNTHETIC_SETUP','OPERATOR_ATTESTED'): fail()
    if _version(db) != 9: fail()
    actual_group_schema=_group_schema()
    group_schema = actual_group_schema if group_schema is None else group_schema
    if type(group_schema) is not str or group_schema!=actual_group_schema: fail()
    with closing(sqlite3.connect(':memory:')) as expected:
        expected.executescript(legacy_schema() + group_schema + MIGRATION_SCHEMA)
        if _fingerprint(db) != _fingerprint(expected): fail()
    rows = db.execute('SELECT * FROM own_config').fetchall()
    if len(rows) != 1 or rows[0]['id'] != 1 or rows[0]['source_kind'] != source_kind: fail()
    if db.execute('PRAGMA foreign_key_check').fetchone(): fail()


def _cell(value):
    kind = type(value)
    if value is None: return ['null', None]
    if kind is int: return ['integer', str(value)]
    if kind is float:
        if not math.isfinite(value): fail()
        return ['real', value.hex()]
    if kind is str: return ['text', value]
    if kind is bytes: return ['blob', len(value), sha256(value).hexdigest()]
    fail()


def _inventory(db):
    """Exact typed preexisting tables; group objects are a separate domain."""
    return _inventory_for_schema(db,legacy_schema())


def _inventory_for_schema(db,script):
    with closing(sqlite3.connect(':memory:')) as expected:
        expected.executescript(script)
        names = [r[0] for r in expected.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name")]
    result = {}
    count = 0
    for name in names:
        quoted = '"' + name.replace('"','""') + '"'
        info = list(db.execute('PRAGMA table_info('+quoted+')'))
        columns = [r[1] for r in info]
        pk = [r[1] for r in sorted(info, key=lambda r:r[5]) if r[5]]
        if not pk: fail('GROUP_SCHEMA_LEGACY_KEY_MISSING')
        rows = [[_cell(v) for v in tuple(r)] for r in db.execute('SELECT * FROM '+quoted)]
        count += len(rows)
        if count > 200000: fail('GROUP_SCHEMA_CHECKPOINT_BOUND')
        rows.sort(key=canonical)
        result[name] = {'columns': columns, 'pk': pk, 'rows': rows}
    if len(canonical(result).encode()) > MAXIMUM: fail('GROUP_SCHEMA_CHECKPOINT_BOUND')
    return result


def _strict_checkpoint(value):
    keys = {'schema','profile','operation_id','source_kind','binding_sha','code_scope','contract_sha',
        'base_version','target_version','legacy_ddl_sha','group_ddl_sha','migration_ddl_sha',
        'old_restore_marker_sha','inventory','prerequisite_proof_sha'}
    if type(value) is not dict or set(value) != keys: fail()
    if type(value['schema']) is not int or value['schema'] != 2 or type(value['profile']) is not str or value['profile'] != PROFILE: fail()
    _id(value['operation_id'])
    if type(value['source_kind']) is not str or value['source_kind'] not in ('SYNTHETIC_SETUP','OPERATOR_ATTESTED'): fail()
    for key in ('binding_sha','code_scope','contract_sha','legacy_ddl_sha','group_ddl_sha','migration_ddl_sha'): _hash(value[key])
    if value['prerequisite_proof_sha'] is not None: _hash(value['prerequisite_proof_sha'])
    if value['old_restore_marker_sha'] is not None: _hash(value['old_restore_marker_sha'])
    for key, target in (('base_version',8),('target_version',9)):
        if type(value[key]) is not int or value[key] != target: fail()
    if value['contract_sha']!=contract_sha() or type(value['inventory']) is not dict: fail()
    # Canonical bytes are later compared to a freshly generated inventory at
    # admission; on read, the exact schema/columns/cells are validated by delta.
    return value


def _read_json(path, maximum):
    from .bounded_file import FileSource, file_state, identity
    from .own_bootstrap_security import path_check
    from .prepared_draft_fixture import decode_json
    import stat
    source=FileSource(path.parent); descriptors=[];chain=[]
    try:
        root=source._root(descriptors,chain)
        if identity(os.fstat(root))!=path_check(path.parent,True):fail()
        fd=os.open(path.name,os.O_RDONLY|os.O_NOFOLLOW|os.O_NONBLOCK,dir_fd=root)
        descriptors.append(fd);before=os.fstat(fd)
        if (not stat.S_ISREG(before.st_mode) or before.st_uid!=os.getuid()
                or stat.S_IMODE(before.st_mode)!=0o600 or before.st_nlink!=1
                or not 0<before.st_size<=maximum):fail()
        raw=bytearray()
        while len(raw)<=maximum:
            chunk=os.read(fd,min(65536,maximum+1-len(raw)))
            if not chunk:break
            raw.extend(chunk)
        after=os.fstat(fd);entry=os.stat(path.name,dir_fd=root,follow_symlinks=False)
        if file_state(before)!=file_state(after) or file_state(after)!=file_state(entry) or len(raw)!=before.st_size:fail()
        source._check_chain(chain)
        value=decode_json(bytes(raw),maximum,max_nodes=2_000_000)
        if (canonical(value)+'\n').encode()!=bytes(raw):fail()
        return value,sha256(raw).hexdigest()
    finally:source._close(descriptors)


def _old_marker_sha(db):
    root = _root(db)
    path = root / 'draft-restore-migration.json'
    if not os.path.lexists(path): return None
    from .own_bootstrap_security import private_read
    raw, _ = private_read(path)
    return sha256(raw).hexdigest()


def _files(db):
    root = _root(db)
    checkpoint, checkpoint_sha = _read_json(root / CHECKPOINT, MAXIMUM)
    _strict_checkpoint(checkpoint)
    marker, _ = _read_json(root / MARKER, 8192)
    if (type(marker) is not dict or set(marker) != {'schema','operation_id','checkpoint_sha','phase'}
            or type(marker['schema']) is not int or marker['schema'] != 1
            or type(marker['phase']) is not str or marker['phase'] not in ('PREPARED','COMMITTED','ROLLED_BACK')): fail()
    _id(marker['operation_id']); _hash(marker['checkpoint_sha'])
    if marker['operation_id'] != checkpoint['operation_id'] or marker['checkpoint_sha'] != checkpoint_sha: fail()
    if (checkpoint['legacy_ddl_sha'] != sha256(legacy_schema().encode()).hexdigest()
            or checkpoint['group_ddl_sha'] != sha256(_group_schema().encode()).hexdigest()
            or checkpoint['migration_ddl_sha'] != sha256(MIGRATION_SCHEMA.encode()).hexdigest()
            or checkpoint['old_restore_marker_sha'] != _old_marker_sha(db)): fail()
    return checkpoint, checkpoint_sha, marker


def _binding(checkpoint, source_kind, history_policy, db):
    if type(source_kind) is not str or source_kind not in ('SYNTHETIC_SETUP','OPERATOR_ATTESTED'):fail()
    if checkpoint['source_kind'] != source_kind: fail()
    if source_kind == 'OPERATOR_ATTESTED' and history_policy is None: fail('GROUP_SCHEMA_HISTORY_POLICY_REQUIRED')
    if history_policy is not None:
        from .publication_contract import binding
        if (checkpoint['binding_sha'] != binding(history_policy.data)
                or history_policy.data['private_directory']!=str(_root(db))):fail('GROUP_SCHEMA_BINDING_CHANGED')


def _value(cell):
    if type(cell) is not list or not cell or type(cell[0]) is not str: fail()
    tag = cell[0]
    if tag == 'null' and cell == ['null',None]: return None
    if tag == 'integer' and len(cell)==2 and type(cell[1]) is str:
        try: number = int(cell[1])
        except ValueError: fail()
        if _cell(number) != cell: fail()
        return number
    if tag == 'real' and len(cell)==2 and type(cell[1]) is str:
        try: number = float.fromhex(cell[1])
        except ValueError: fail()
        if not math.isfinite(number) or _cell(number) != cell: fail()
        return number
    if tag == 'text' and len(cell)==2 and type(cell[1]) is str: return cell[1]
    if tag == 'blob' and len(cell)==3 and type(cell[1]) is int and cell[1]>=0:
        _hash(cell[2]); return tuple(cell)
    fail()


def _monotone(table, before, after):
    # Columns admitted below remain subject to the original current proof and
    # record validators; this is an ancestor floor, not a replacement verifier.
    for key in ('cancelled','retired','submit_count','query_used','query_seq'):
        if key in before and after[key] < before[key]: fail('GROUP_SCHEMA_HISTORY_ROLLBACK')
    if table == 'publication_policy' and after['enabled'] > before['enabled']: fail()
    if 'state' in before and before['state'] == 'SUCCEEDED':
        for key in ('state','result','result_digest','completed','proof_name','proof_sha'):
            if key in before and (type(before[key]) is not type(after[key]) or before[key] != after[key]): fail('GROUP_SCHEMA_HISTORY_ROLLBACK')
    if table in ('own_draft_restore_reads','publication_query_claims') and before['state'] != 'CLAIMED' and before['state'] != 'ACTIVE':
        if before != after: fail('GROUP_SCHEMA_HISTORY_ROLLBACK')
    if table in ('own_steps','own_body_recoveries','own_body_followups','own_body_attempts','own_draft_restores','own_lineage_replacements'):
        if before['state'] == 'RESULT_UNKNOWN' and after['state'] not in ('RESULT_UNKNOWN','SUCCEEDED'): fail()
        if before['state'] == after['state'] == 'RESULT_UNKNOWN':
            for key in ('result','result_digest','completed','proof_name','proof_sha'):
                if key in before and before[key] != after[key]: fail()
    for key in ('diagnostic','diagnostic_digest','observation','observation_digest'):
        if key in before and before[key] not in ('{}', digest({})) and before[key]!=after[key]: fail('GROUP_SCHEMA_HISTORY_ROLLBACK')
    if table == 'publication_intents':
        if before.get('state') in ('PUBLISHED','PLATFORM_FAILED','PLATFORM_DELETED','PLATFORM_BLOCKED','REJECTED_LOCKED','CANCELLED_BEFORE_SUBMIT') and before!=after:
            fail('GROUP_SCHEMA_HISTORY_ROLLBACK')
        for key in ('task_kind','task_digits','task_wire_type','task_raw_token'):
            if before[key] is not None and before[key] != after[key]: fail('GROUP_SCHEMA_HISTORY_ROLLBACK')
        if before['submit_count'] == 1:
            for key in ('review_id','snapshot_sha','submit_claim_seq','submit_ms'):
                if before[key] != after[key]: fail('GROUP_SCHEMA_HISTORY_ROLLBACK')


def verify_legacy_delta(checkpoint, db, *, current_inventory=None):
    current = _inventory(db) if current_inventory is None else current_inventory
    old = checkpoint['inventory']
    if set(old) != set(current): fail()
    for table, now in current.items():
        prior = old[table]
        if type(prior) is not dict or set(prior) != {'columns','pk','rows'}: fail()
        if (type(prior['columns']) is not list or type(prior['pk']) is not list or type(prior['rows']) is not list
                or prior['columns'] != now['columns'] or prior['pk'] != now['pk']): fail()
        if any(type(v) is not str for v in prior['columns']+prior['pk']): fail()
        columns = now['columns']; pk = [columns.index(k) for k in now['pk']]
        def mapping(rows):
            result = {}
            for row in rows:
                if type(row) is not list or len(row) != len(columns): fail()
                values = [_value(c) for c in row]
                key = canonical([row[i] for i in pk])
                if key in result: fail()
                result[key] = (row, dict(zip(columns, values)))
            return result
        previous, present = mapping(prior['rows']), mapping(now['rows'])
        if table in _DERIVED_LOCKS:
            # The original full record check independently recomputes the exact
            # live locks from retained owner/UNKNOWN/result history.
            continue
        for key, (cells, before) in previous.items():
            if key not in present: fail('GROUP_SCHEMA_HISTORY_REMOVED')
            after_cells, after = present[key]
            mutable = _MUTABLE.get(table, set())
            for i, column in enumerate(columns):
                if column not in mutable and canonical(cells[i]) != canonical(after_cells[i]): fail('GROUP_SCHEMA_HISTORY_CHANGED')
            _monotone(table, before, after)


def check_pending(db):
    version = db.execute('PRAGMA user_version').fetchone()[0]
    if version not in (1,2,3,4,5,6,7,8,9): fail()
    path = db.execute('PRAGMA database_list').fetchone()[2]
    if not path: return
    marker = Path(path).parent / MARKER
    checkpoint = Path(path).parent / CHECKPOINT
    if not os.path.lexists(marker) and not os.path.lexists(checkpoint):
        if version == 9: fail('GROUP_SCHEMA_ANCESTRY_MISSING')
        return
    if not os.path.lexists(marker) and os.path.lexists(checkpoint):
        value, _ = _read_json(checkpoint, MAXIMUM); _strict_checkpoint(value)
        if version==8 and _MIGRATING.get()==value['operation_id']:
            return
        fail('GROUP_SCHEMA_MIGRATION_PENDING')
    value, _, progress = _files(db)
    if version == 8 and progress['phase']=='COMMITTED':
        fail('GROUP_SCHEMA_DATABASE_ROLLBACK_HOLD')
    if version != 9:
        if version != 8 or progress['phase'] != 'ROLLED_BACK':
            if _MIGRATING.get() != value['operation_id']: fail('GROUP_SCHEMA_MIGRATION_PENDING')


def _legacy_history(db, source_kind, history_policy, *, history=None):
    from .own_store import OwnStore
    owner=object.__new__(OwnStore)
    owner.path=_root(db)/'state.sqlite3';owner.history_policy=history_policy
    owner._check_legacy_history(db, source_kind, history=history)


def check_ancestry(db, source_kind, history_policy=None, *, history=None):
    if _version(db) != 9: fail()
    value, checkpoint_sha, marker = _files(db)
    _binding(value, source_kind, history_policy, db)
    from .own_group_prerequisite import verify_core_reference
    verify_core_reference(db,value,source_kind,history_policy)
    if marker['phase'] != 'COMMITTED' and not (marker['phase']=='PREPARED' and _MIGRATING.get()==value['operation_id']): fail('GROUP_SCHEMA_MIGRATION_PENDING')
    rows = db.execute('SELECT * FROM group_schema_migrations').fetchall()
    if len(rows) != 1 or dict(rows[0]) != {'id':1,'operation_id':value['operation_id'],'checkpoint_sha':checkpoint_sha,'source_kind':source_kind}: fail()
    verify_legacy_delta(value, db)
    _legacy_history(db, source_kind, history_policy, history=history)
    return value


def check_restore_ancestor(db, marker_sha):
    value, checkpoint_sha, marker = _files(db)
    _hash(marker_sha)
    if _version(db) != 9 or value['old_restore_marker_sha'] != marker_sha: fail()
    if marker['phase'] != 'COMMITTED' and _MIGRATING.get() != value['operation_id']: fail()
    try:rows = db.execute('SELECT * FROM group_schema_migrations').fetchall()
    except sqlite3.Error:fail()
    if len(rows)!=1 or rows[0]['checkpoint_sha']!=checkpoint_sha or rows[0]['operation_id']!=value['operation_id']: fail()


def _write_new(path, value):
    from .own_bootstrap_security import path_check
    from .bounded_file import FileSource, identity
    raw = (canonical(value)+'\n').encode()
    if not 0<len(raw)<=MAXIMUM:fail()
    source=FileSource(path.parent);descriptors=[];chain=[]
    try:
        directory=source._root(descriptors,chain)
        if identity(os.fstat(directory))!=path_check(path.parent,True):fail()
        fd=os.open(path.name,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o600,dir_fd=directory)
        with os.fdopen(fd,'wb') as stream:
            os.fchmod(stream.fileno(),0o600)
            stream.write(raw);stream.flush();os.fsync(stream.fileno())
        os.fsync(directory);source._check_chain(chain)
        observed,observed_sha=_read_json(path,MAXIMUM)
        if observed_sha!=sha256(raw).hexdigest() or canonical(observed)!=canonical(value):fail()
    finally:
        # Unknown/partial originals are intentionally retained for same-ID
        # observation; never unlink or replace them with a fresh operation.
        source._close(descriptors)


def prepare_checkpoint(db, source_kind, *, operation_id, binding_sha, code_scope,
                       contract_sha, guard, history_policy=None, history_locators=None):
    """Trusted maintenance component; caller proves lock/backup/authority first."""
    _require_maintenance_history(history_policy,db,history_locators)
    from .own_store import OwnStore
    guard(); _id(operation_id)
    if not db.in_transaction: fail('GROUP_SCHEMA_TRANSACTION_REQUIRED')
    for value in (binding_sha,code_scope,contract_sha): _hash(value)
    if _version(db)!=8: fail()
    OwnStore.check(db,source_kind,history_policy,history=history_locators)
    _legacy_history(db,source_kind,history_policy,history=history_locators)
    from .own_group_prerequisite import classify_for_core
    prerequisite=classify_for_core(db,source_kind,history_policy,operation_id)
    value = {'schema':2,'profile':PROFILE,'operation_id':operation_id,'source_kind':source_kind,
        'binding_sha':binding_sha,'code_scope':code_scope,'contract_sha':contract_sha,
        'base_version':8,'target_version':9,'legacy_ddl_sha':sha256(legacy_schema().encode()).hexdigest(),
        'group_ddl_sha':sha256(_group_schema().encode()).hexdigest(),
        'migration_ddl_sha':sha256(MIGRATION_SCHEMA.encode()).hexdigest(),
        'old_restore_marker_sha':_old_marker_sha(db),'inventory':_inventory(db),'prerequisite_proof_sha':prerequisite}
    _strict_checkpoint(value); _binding(value,source_kind,history_policy,db)
    root = _root(db)
    if os.path.lexists(root/MARKER) or os.path.lexists(root/CHECKPOINT): fail('GROUP_SCHEMA_ORIGINAL_OPERATION_REQUIRED')
    guard(); _write_new(root/CHECKPOINT,value)
    checkpoint_sha=sha256((canonical(value)+'\n').encode()).hexdigest()
    guard(); _write_new(root/MARKER,{'schema':1,'operation_id':operation_id,'checkpoint_sha':checkpoint_sha,'phase':'PREPARED'})
    guard()
    return checkpoint_sha



def migrate_in(db, source_kind, *, operation_id, checkpoint_sha, guard, history_policy=None, fault=lambda phase:None, history_locators=None):
    """One caller-owned SQL transaction; never commit or redo a committed ID."""
    _require_maintenance_history(history_policy,db,history_locators)
    from .own_store import OwnStore
    _id(operation_id);_hash(checkpoint_sha);guard()
    if not db.in_transaction: fail('GROUP_SCHEMA_TRANSACTION_REQUIRED')
    if _version(db)!=8: fail('GROUP_SCHEMA_ORIGINAL_OPERATION_REQUIRED')
    value, actual_sha, marker = _files(db)
    if value['operation_id']!=operation_id or actual_sha!=checkpoint_sha or marker['phase']!='PREPARED': fail()
    _binding(value,source_kind,history_policy,db)
    from .own_group_prerequisite import verify_core_reference
    verify_core_reference(db,value,source_kind,history_policy)
    token=_MIGRATING.set(operation_id)
    try:
        OwnStore.check(db,source_kind,history_policy,history=history_locators)
        _legacy_history(db,source_kind,history_policy,history=history_locators)
        if canonical(_inventory(db)) != canonical(value['inventory']): fail('GROUP_SCHEMA_BASE_DRIFT')
        for script in (_group_schema(),MIGRATION_SCHEMA):
            statement=''
            for line in script.splitlines(keepends=True):
                statement+=line
                if sqlite3.complete_statement(statement):
                    db.execute(statement.lstrip());statement='';guard();fault('group_schema_ddl')
            if statement.strip(): fail()
        db.execute('INSERT INTO group_schema_migrations VALUES(1,?,?,?)',(operation_id,checkpoint_sha,source_kind))
        if canonical(_inventory(db)) != canonical(value['inventory']): fail('GROUP_SCHEMA_BASE_DRIFT')
        fault('group_schema_before_version');guard()
        db.execute('PRAGMA user_version=9')
        OwnStore.check(db,source_kind,history_policy,history=history_locators)
        guard();fault('group_schema_before_commit')
    finally:
        _MIGRATING.reset(token)



def _no_sidecars(path):
    if any(os.path.lexists(str(path)+suffix) for suffix in ('-wal','-shm','-journal')):
        fail('GROUP_SCHEMA_DATABASE_BUSY')


@contextmanager
def readonly_connection(path):
    """Qualified local caller only: exact owned business file; no creation/locks.

    The original read-only Owned connection supplies actual SQLite provenance;
    the trusted caller still keeps its independent writer exclusion throughout.
    The before/after identity/state checks fail on any observed concurrent edit.
    """
    from .own_bootstrap_security import path_check
    from .bounded_file import file_state
    path=Path(path)
    if not path.is_absolute() or path.name!='state.sqlite3' or '..' in path.parts:fail()
    parent=path_check(path.parent,True);pin=path_check(path)
    before=file_state(path.lstat());_no_sidecars(path)
    from .own_history_source import owned_connection
    with owned_connection(path,readonly=True,timeout=5,isolation_level=None) as db:
        db.row_factory=sqlite3.Row
        try:
            db.execute('PRAGMA query_only=ON');db.execute('PRAGMA trusted_schema=OFF')
            db.execute('PRAGMA foreign_keys=ON');db.execute('BEGIN')
            if path_check(path)!=pin or file_state(path.lstat())!=before:fail()
            _no_sidecars(path)
            yield db
            _no_sidecars(path)
            if path_check(path)!=pin or file_state(path.lstat())!=before or path_check(path.parent,True)!=parent:fail()
        finally:
            db.rollback()


def query_migration(db, source_kind, *, operation_id, checkpoint_sha, history_policy=None, history_locators=None):
    """Same-ID pure local observation: no DDL, file write, repair, grant or API."""
    _id(operation_id);_hash(checkpoint_sha)
    try:
        _require_maintenance_history(history_policy,db,history_locators)
        if not db.in_transaction or db.execute('PRAGMA query_only').fetchone()[0]!=1:
            fail('GROUP_SCHEMA_READ_TRANSACTION_REQUIRED')
        _no_sidecars(_root(db)/'state.sqlite3')
        root=_root(db)
        if os.path.lexists(root/CHECKPOINT) and not os.path.lexists(root/MARKER):
            value,actual_sha=_read_json(root/CHECKPOINT,MAXIMUM);_strict_checkpoint(value)
            if _version(db)!=8:fail()
            marker=None
            if (value['legacy_ddl_sha']!=sha256(legacy_schema().encode()).hexdigest()
                    or value['group_ddl_sha']!=sha256(_group_schema().encode()).hexdigest()
                    or value['migration_ddl_sha']!=sha256(MIGRATION_SCHEMA.encode()).hexdigest()
                    or value['old_restore_marker_sha']!=_old_marker_sha(db)):fail()
        else:value, actual_sha, marker = _files(db)
        if value['operation_id']!=operation_id or actual_sha!=checkpoint_sha: fail()
        _binding(value,source_kind,history_policy,db)
        from .own_group_prerequisite import verify_core_reference
        verify_core_reference(db,value,source_kind,history_policy)
        version=_version(db)
        if version==8:
            if marker is not None and marker['phase']=='COMMITTED':
                fail('GROUP_SCHEMA_DATABASE_ROLLBACK_HOLD')
            from .own_lineage_replacement import schema_check
            # Complete old layout/records still checked; pending marker is only
            # admitted for THIS local history query, never a new business claim.
            token=_MIGRATING.set(operation_id)
            try:
                from .own_store import OwnStore
                OwnStore.check(db,source_kind,history_policy,history=history_locators)
                if marker is not None and marker['phase']=='ROLLED_BACK':
                    verify_legacy_delta(value,db)
                elif canonical(_inventory(db))!=canonical(value['inventory']): fail()
                _legacy_history(db,source_kind,history_policy,history=history_locators)
            finally:_MIGRATING.reset(token)
            return {'state':'NOT_COMMITTED','operation_id':operation_id}
        token=_MIGRATING.set(operation_id)
        try:
            from .own_store import OwnStore
            OwnStore.check(db,source_kind,history_policy,history=history_locators)
        finally:_MIGRATING.reset(token)
        return {'state':'COMMITTED','operation_id':operation_id}
    except (WCEError,sqlite3.Error,ValueError,TypeError,KeyError,OSError):
        return {'state':'UNDETERMINED','operation_id':operation_id}



def finish_marker(db, source_kind, *, operation_id, checkpoint_sha, guard, history_policy=None, history_locators=None):
    """Trusted same-ID local tail only; never rerun SQL or consume a claim."""
    _require_maintenance_history(history_policy,db,history_locators)
    from .own_connection_policy import atomic_write
    guard()
    result=query_migration(db,source_kind,operation_id=operation_id,checkpoint_sha=checkpoint_sha,history_policy=history_policy,history_locators=history_locators)
    if result['state'] not in ('COMMITTED','NOT_COMMITTED'): fail('GROUP_SCHEMA_RECONCILE_HOLD')
    if not os.path.lexists(_root(db)/MARKER):
        # Original prepare interrupted after durable checkpoint and before its
        # marker. Exact same ID/SHA + unchanged8 can only close as ROLLED_BACK.
        if result['state']!='NOT_COMMITTED':fail()
        guard()
        fresh=query_migration(db,source_kind,operation_id=operation_id,checkpoint_sha=checkpoint_sha,history_policy=history_policy,history_locators=history_locators)
        if fresh!=result or os.path.lexists(_root(db)/MARKER):fail('GROUP_SCHEMA_RECONCILE_HOLD')
        _write_new(_root(db)/MARKER,{'schema':1,'operation_id':operation_id,'checkpoint_sha':checkpoint_sha,'phase':'ROLLED_BACK'});guard()
        return result
    value, actual_sha, marker=_files(db)
    if value['operation_id']!=operation_id or actual_sha!=checkpoint_sha:
        fail('GROUP_SCHEMA_RECONCILE_HOLD')
    phase='COMMITTED' if result['state']=='COMMITTED' else 'ROLLED_BACK'
    if marker['phase'] not in ('PREPARED',phase): fail()
    if marker['phase']!=phase:
        guard()
        fresh=query_migration(db,source_kind,operation_id=operation_id,checkpoint_sha=checkpoint_sha,history_policy=history_policy,history_locators=history_locators)
        fresh_value,fresh_sha,fresh_marker=_files(db)
        if (fresh!=result or fresh_value['operation_id']!=operation_id or fresh_sha!=checkpoint_sha
                or canonical(fresh_marker)!=canonical(marker)):
            fail('GROUP_SCHEMA_RECONCILE_HOLD')
        atomic_write(_root(db)/MARKER,dict(marker,phase=phase));guard()
    return result



def _require_maintenance_history(policy,db,history_locators):
    """Formal maintenance borrows its real SQL owner's H; never opens one."""
    from .own_connection_policy import ConnectionPolicy
    if type(policy)is ConnectionPolicy and policy.value.get('schema')==2:
        from .draft_group_history_context import require_history
        require_history(policy,db,history_locators)
