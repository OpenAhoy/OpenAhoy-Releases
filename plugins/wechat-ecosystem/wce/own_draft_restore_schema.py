"""Trusted schema8 additive migration; transaction owned by caller."""
import sqlite3
from .contracts import WCEError
from .own_store import OwnStore
from .own_draft_restore_store import SCHEMA


def migrate(db, source_kind, guard, *, history_policy, fault=lambda phase:None, history_locators=None):
    guard()
    if not db.in_transaction:
        raise WCEError('DRAFT_RESTORE_TRANSACTION_REQUIRED')
    OwnStore.check(db,source_kind,history_policy, history=history_locators)
    version=db.execute('PRAGMA user_version').fetchone()[0]
    if version in (8,9):
        return
    if version != 7:
        raise WCEError('DRAFT_RESTORE_NEUTRAL_BASE_REQUIRED')
    statement=''
    for line in SCHEMA.splitlines(keepends=True):
        statement+=line
        if sqlite3.complete_statement(statement):
            db.execute(statement.lstrip());statement=''
    if statement.strip():raise WCEError('DRAFT_RESTORE_SCHEMA_INVALID')
    db.execute('PRAGMA user_version=8')
    OwnStore.check(db,source_kind,history_policy, history=history_locators)
    guard();fault('restore_schema_before_commit')


# Restricted to the trusted migration stack. Ordinary model routes never set it.
from contextvars import ContextVar
_MIGRATING = ContextVar('trusted_draft_restore_migration', default=False)


def check_marker(db):
    from pathlib import Path
    import os
    from .publication_store import read_file
    path=db.execute('PRAGMA database_list').fetchone()[2]
    if not path:return
    marker=Path(path).parent/'draft-restore-migration.json'
    if not os.path.lexists(marker):return
    value=read_file(marker)
    if (type(value) is not dict or set(value) != {'schema','contract_sha','review_sha','base_version','target_version','phase'}
            or value['schema'] != 1 or value['target_version'] != 8
            or type(value.get('base_version')) is not int or value['base_version'] not in (5,6,7)
            or type(value.get('review_sha')) is not str or len(value['review_sha'])!=64
            or value['phase'] not in {'PREPARED','COMMITTED','ROLLED_BACK'}):
        raise WCEError('DRAFT_RESTORE_MIGRATION_HOLD')
    from .own_draft_restore_contract import SUPPORTED_CONTRACTS
    if value['contract_sha'] not in SUPPORTED_CONTRACTS:
        raise WCEError('DRAFT_RESTORE_MIGRATION_HOLD')
    if value['phase'] == 'PREPARED' and not _MIGRATING.get():
        raise WCEError('DRAFT_RESTORE_MIGRATION_HOLD')
    current_version=db.execute('PRAGMA user_version').fetchone()[0]
    if value['phase']=='ROLLED_BACK' and current_version!=value['base_version']:
        from hashlib import sha256
        from .own_bootstrap_security import private_read
        from .own_group_prerequisite import check_restore_bridge
        raw,_=private_read(marker)
        check_restore_bridge(db,sha256(raw).hexdigest())
    if value['phase'] == 'COMMITTED' and current_version == 9:
        from hashlib import sha256
        from .own_bootstrap_security import private_read
        from .own_group_schema import check_restore_ancestor
        raw,_=private_read(marker)
        check_restore_ancestor(db,sha256(raw).hexdigest())
    elif value['phase'] == 'COMMITTED' and current_version != 8:
        raise WCEError('DRAFT_RESTORE_MIGRATION_ROLLBACK_HOLD')


def trusted_initialize(policy, registry, admitted, guard, *, fault=lambda phase:None):
    """Atomic 5/6/7→8 plus neutral coordination; never grants publication."""
    from .own_draft_restore_authority import require_admitted
    from .own_draft_restore_contract import CONTRACT_SHA
    from .own_connection_policy import locked, atomic_write
    from .publication_store import PublicationStore, read_file
    from .publication_schema import migrate_to_7
    from .publication_lock import install_pin
    from .own_replacement_files import folder
    from .service import digest
    import os
    value=require_admitted(admitted);guard();policy.check()
    store=PublicationStore(policy,registry)
    marker=policy.root/'draft-restore-migration.json'
    with locked(store.anchor_root.parent/'connection-setup.lock',nonblocking=True):
        previous=read_file(marker) if os.path.lexists(marker) else None
        if previous is not None and previous.get('phase')=='PREPARED':
            raise WCEError('DRAFT_RESTORE_MIGRATION_HOLD')
        # New V2 admission must not overwrite even a rolled-back V1 marker.
        from .own_draft_restore_contract import V1_CONTRACT_SHA
        if previous is not None and previous.get('contract_sha')==V1_CONTRACT_SHA:
            raise WCEError('DRAFT_RESTORE_LEGACY_HISTORY_HOLD')
        # Only empty private lock directories may be prepared before the full
        # writer lock. No marker, pin or public head is published at this point.
        folder(store.anchor_root,create=True);folder(store.anchor,create=True)
        with store.dispatch_lock():
            guard();policy.check()
            with store.connection() as db, _history_scope(policy,db) as history_locators:
                source=db.execute('SELECT source_kind FROM own_config WHERE id=1').fetchone()[0]
                OwnStore.check(db,source,policy, history=history_locators)
                from .own_draft_restore_metadata import reject_legacy_for_new_grant
                reject_legacy_for_new_grant(db)
                base_version=db.execute('PRAGMA user_version').fetchone()[0]
            if base_version in (8,9):
                return {'state':'RESTORE_SCHEMA_READY','publication_granted':False}
            if base_version not in (5,6,7):raise WCEError('DRAFT_RESTORE_SCHEMA_INVALID')
            target={'schema':1,'contract_sha':CONTRACT_SHA,'review_sha':digest(value),
                    'base_version':base_version,'target_version':8,'phase':'PREPARED'}
            atomic_write(marker,target)
            token=_MIGRATING.set(True)
            try:
                store._make_anchor();install_pin(store)
                # Both feature layouts are in THIS transaction. Do not call
                # PublicationStore.migrate(), which commits a separate v7 step.
                with store.connection(write=True) as db, _history_scope(policy,db) as history_locators:
                    migrate_to_7(db,source,guard,history_policy=policy,fault=fault, history_locators=history_locators)
                    migrate(db,source,guard,history_policy=policy,fault=fault, history_locators=history_locators)
                    guard();policy.check()
                fault('restore_migration_db_committed')
                # This records already committed neutral maintenance even if the
                # page closed. It creates no restoration or publication grant.
                atomic_write(marker,dict(target,phase='COMMITTED'))
            except BaseException:
                try:
                    with store.connection() as db, _history_scope(policy,db) as history_locators:
                        current=db.execute('PRAGMA user_version').fetchone()[0]
                        OwnStore.check(db,source,policy, history=history_locators)
                    if current==base_version:
                        atomic_write(marker,dict(target,phase='ROLLED_BACK'))
                except Exception:
                    pass  # Unknown commit remains PREPARED/HOLD, never guessed.
                raise
            finally:
                _MIGRATING.reset(token)
    with store.connection() as db, _history_scope(policy,db) as history_locators:OwnStore.check(db,source,policy, history=history_locators)
    return {'state':'RESTORE_SCHEMA_READY','publication_granted':False}


from .draft_group_history_context import locator_scope as _history_scope
