"""Formal R1 schema 6 + publication schema 7; no implicit migration.

Caller owns its database connection and, for migration, BEGIN IMMEDIATE and
all required maintenance/publication locks. No account discovery or network.
"""
import sqlite3
from pathlib import Path

from .contracts import WCEError
from .own_store import OwnStore


def classify_read_only(db, source_kind, history_policy=None, *, history_locators=None):
    """Verify the complete owned structure/history before reporting a version."""
    version = db.execute('PRAGMA user_version').fetchone()[0]
    if version not in (5, 6, 7, 8, 9):
        raise WCEError('OWN_STATE_UNVERIFIED')
    OwnStore.check(db, source_kind, history_policy, history=history_locators)
    return version


def migrate_to_7(db, source_kind, guard, *, history_policy=None, fault=lambda phase: None, history_locators=None):
    """Migrate only a verified 5 or formal 6 under a caller-owned transaction.

    No commits or filesystem writes occur here. Caller must hold all required
    locks, perform enable/anchor ordering, and commit or roll back atomically.
    """
    guard()
    if not db.in_transaction:
        raise WCEError('OWN_STATE_UNVERIFIED')
    version = classify_read_only(db, source_kind, history_policy, history_locators=history_locators)
    owner = object.__new__(OwnStore)
    owner.path = Path(db.execute('PRAGMA database_list').fetchone()[2])
    owner.history_policy = history_policy
    owner._check_legacy_history(db, source_kind, history=history_locators)
    if version in (7, 8, 9):
        return
    from .own_lineage_replacement import migrate as migrate_replacement
    if version == 5:
        migrate_replacement(db, source_kind, guard, fault=fault, history_policy=history_policy, history_locators=history_locators)
    OwnStore.check(db, source_kind, history_policy, history=history_locators)
    if db.execute('PRAGMA user_version').fetchone()[0] != 6:
        raise WCEError('OWN_STATE_UNVERIFIED')
    from .publication_store import ALL_SCHEMA
    statement = ''
    for line in ALL_SCHEMA.splitlines(keepends=True):
        statement += line
        if sqlite3.complete_statement(statement):
            db.execute(statement.lstrip())
            statement = ''
    if statement.strip():
        raise WCEError('OWN_STATE_UNVERIFIED')
    db.execute('PRAGMA user_version=7')
    OwnStore.check(db, source_kind, history_policy, history=history_locators)
    owner._check_legacy_history(db, source_kind, history=history_locators)
    guard()
    fault('publication_schema_before_commit')
