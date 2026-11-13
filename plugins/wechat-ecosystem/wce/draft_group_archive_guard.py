"""Block legacy unarchived-success fallback for an actual linked Group ADD.

The ordinary caller has already completed its full resource/dispatch checks in
this same transaction. This leaf grants nothing and never archives or repairs.
"""
import sqlite3
from .contracts import WCEError


def require_ordinary_fallback_in(db, step, *, history_locators=None):
    if not isinstance(db,sqlite3.Connection) or not db.in_transaction:
        raise WCEError('GROUP_TRANSACTION_REQUIRED')
    version=db.execute('PRAGMA user_version').fetchone()[0]
    if type(version) is not int or version not in (4,5,6,7,8,9):
        raise WCEError('GROUP_SCHEMA_UNVERIFIED')
    if version<9:
        return
    from .draft_group_store import _linked_state
    if _linked_state(db,step, history_locators=history_locators) is not None:
        raise WCEError('GROUP_ARCHIVE_REQUIRED')
