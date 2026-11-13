"""Private transaction-local immutable-content reuse; never authorization.

Only OwnStore's fresh connections qualify. Unsupported SQLite customization
falls back to complete validation. This is not a raw-Python security sandbox.
"""
from contextlib import contextmanager
from contextvars import ContextVar
import json
import math
import os
import re
import sqlite3
import threading

MAX_BUNDLES = 32
MAX_BYTES = 2 * 1024 * 1024
_ACTIVE = ContextVar('own_content_validation', default=None)
_READ_PRAGMA = re.compile(r'PRAGMA\s+(?:(?:main\.)?(?:data_version|schema_version|user_version|application_id)|database_list|temp\.schema_version)\s*;?\s*\Z', re.I)
_SELECT = re.compile(r'SELECT\b', re.I)


class OwnedCursor(sqlite3.Cursor):
    def __setattr__(self, name, value):
        if name == 'row_factory' and value is not None and value is not sqlite3.Row:
            self.connection._disable_content_reuse()
        super().__setattr__(name, value)


class OwnedConnection(sqlite3.Connection):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._content_epoch = 0
        self._transaction_generation = 0
        self._content_disabled = False
        self._content_scopes = []
        try:
            self._install_content_trace()
        except BaseException:
            self._disable_content_reuse()

    def _install_content_trace(self):
        # Bypass only our public override during this one fresh initialization.
        sqlite3.Connection.set_trace_callback(self, self._content_trace)

    def _disable_content_reuse(self):
        self._content_disabled = True
        for scope in self._content_scopes:
            scope.clear()

    def _content_trace(self, statement):
        try:
            self._content_trace_step(statement)
        except BaseException:
            # SQLite can swallow trace exceptions. Disable before returning.
            self._disable_content_reuse()

    def _content_trace_step(self, statement):
        # Independent lifetime observation before any read/cache early return.
        if not self.in_transaction:
            self._transaction_generation += 1
        sql = statement.lstrip()
        if _SELECT.match(sql) or _READ_PRAGMA.fullmatch(sql):
            return
        self._content_epoch += 1
        for scope in self._content_scopes:
            scope.clear()

    def __setattr__(self, name, value):
        if ((name == 'row_factory' and value is not None and value is not sqlite3.Row)
                or (name == 'text_factory' and value is not str)):
            self._disable_content_reuse()
        super().__setattr__(name, value)

    def cursor(self, factory=OwnedCursor):
        if factory is not OwnedCursor:
            self._disable_content_reuse()
        return super().cursor(factory=factory)

    def execute(self, sql, parameters=()):
        return self.cursor().execute(sql, parameters)

    def executemany(self, sql, parameters):
        return self.cursor().executemany(sql, parameters)

    def executescript(self, sql):
        return self.cursor().executescript(sql)

    def set_trace_callback(self, callback, **kwargs):
        self._disable_content_reuse()
        return super().set_trace_callback(callback, **kwargs)

    def blobopen(self, *args, **kwargs):
        self._disable_content_reuse()
        return super().blobopen(*args, **kwargs)

    def deserialize(self, *args, **kwargs):
        self._disable_content_reuse()
        return super().deserialize(*args, **kwargs)

    def create_function(self, *args, **kwargs):
        self._disable_content_reuse()
        return super().create_function(*args, **kwargs)

    def create_aggregate(self, *args, **kwargs):
        self._disable_content_reuse()
        return super().create_aggregate(*args, **kwargs)

    def create_window_function(self, *args, **kwargs):
        self._disable_content_reuse()
        return super().create_window_function(*args, **kwargs)

    def create_collation(self, *args, **kwargs):
        self._disable_content_reuse()
        return super().create_collation(*args, **kwargs)

    def set_authorizer(self, *args, **kwargs):
        self._disable_content_reuse()
        return super().set_authorizer(*args, **kwargs)

    def set_progress_handler(self, *args, **kwargs):
        self._disable_content_reuse()
        return super().set_progress_handler(*args, **kwargs)

    def setlimit(self, *args, **kwargs):
        self._disable_content_reuse()
        return super().setlimit(*args, **kwargs)

    def enable_load_extension(self, *args, **kwargs):
        self._disable_content_reuse()
        return super().enable_load_extension(*args, **kwargs)

    def load_extension(self, *args, **kwargs):
        self._disable_content_reuse()
        return super().load_extension(*args, **kwargs)

    def setconfig(self, *args, **kwargs):
        self._disable_content_reuse()
        return super().setconfig(*args, **kwargs)

    def close(self):
        self._disable_content_reuse()
        for scope in self._content_scopes[:]:
            scope.close()
        return super().close()


def _transaction_marker(db):
    """Fresh exact-owned outer lifetime fact; never authorization or a cache."""
    if type(db) is not OwnedConnection or db._content_disabled is not False:
        return None
    generation = db._transaction_generation
    if type(generation) is not int or generation < 0:
        db._disable_content_reuse()
        return None
    try:
        return generation if db.in_transaction else None
    except sqlite3.Error:
        # A closed connection cannot leak raw ProgrammingError through query.
        db._disable_content_reuse()
        return None


def _structured(value):
    """Reject bytes/Secret/custom objects; cache stores JSON bytes, never BLOBs."""
    if value is None or type(value) in (str, bool, int):
        return True
    if type(value) is float:
        return math.isfinite(value)
    if type(value) is list:
        return all(_structured(v) for v in value)
    return (type(value) is dict and all(type(k) is str and _structured(v)
                                      for k, v in value.items()))


class _ContentScope:
    def __init__(self, store, db):
        self.store, self.db = store, db
        self.thread = threading.get_ident()
        self.path = str(store.path)
        info = os.stat(store.path, follow_symlinks=False)
        self.inode = info.st_dev, info.st_ino
        self.active = True
        self.entries = {}
        self.bytes = 0
        self.last_marker = None
        db._content_scopes.append(self)

    def clear(self):
        self.entries.clear()
        self.bytes = 0
        self.last_marker = None

    def close(self):
        self.clear()
        self.active = False
        if self in self.db._content_scopes:
            self.db._content_scopes.remove(self)

    def marker(self):
        db = self.db
        if (not self.active or threading.get_ident() != self.thread
                or type(db) is not OwnedConnection or db._content_disabled
                or not db.in_transaction or (db.row_factory is not None and db.row_factory is not sqlite3.Row)
                or db.text_factory is not str or str(self.store.path) != self.path):
            self.clear()
            return None
        info = os.stat(self.store.path, follow_symlinks=False)
        if (info.st_dev, info.st_ino) != self.inode:
            self.clear()
            return None
        values = tuple(db.execute('PRAGMA '+name).fetchone()[0] for name in
                       ('data_version', 'schema_version', 'user_version', 'application_id'))
        marker = (db._content_epoch, db.total_changes, values, id(db.row_factory), id(db.text_factory))
        if marker != self.last_marker:
            self.clear()
            self.last_marker = marker
        return marker


@contextmanager
def content_scope(store, db):
    scope = None
    if type(db) is OwnedConnection and not db._content_disabled and db.in_transaction:
        try:
            scope = _ContentScope(store, db)
        except (OSError, sqlite3.Error):
            pass  # An optimization never rejects a legal legacy caller.
    token = _ACTIVE.set(scope)
    try:
        yield
    finally:
        if scope is not None:
            scope.close()
        _ACTIVE.reset(token)


def bundle_content(store, db, binding, bundle, version, full_validation):
    """The callback is the original full _bundle, with no dynamic gates moved."""
    scope = _ACTIVE.get()
    if scope is None or scope.store is not store or scope.db is not db:
        return full_validation()
    try:
        before = scope.marker()
        if before is None:
            return full_validation()
        key = json.dumps((binding, bundle, version), sort_keys=True,
                         separators=(',', ':'), allow_nan=False)
        raw = scope.entries.get(key)
        if raw is not None:
            # Keep recent immutable content useful when the verified history
            # exceeds the memory budget. Every hit still follows marker().
            del scope.entries[key]
            scope.entries[key] = raw
            value = json.loads(raw)
            return value[0], value[1]
    except (OSError, sqlite3.Error, TypeError, ValueError):
        scope.clear()
        return full_validation()
    result = full_validation()
    try:
        # _bundle's exact contract is (JSON manifest dict, digest str). Nested
        # tuples/custom objects cannot enter and silently change type on a hit.
        if (scope.marker() != before or type(result) is not tuple or len(result) != 2
                or type(result[0]) is not dict or type(result[1]) is not str
                or not _structured(result[0])):
            return result
        raw = json.dumps(result, sort_keys=True, separators=(',', ':'),
                         ensure_ascii=False, allow_nan=False).encode()
        size = len(key.encode()) + len(raw)
        if size <= MAX_BYTES:
            # Eviction only discards an optimization. It never discards a
            # durable row, a proof check or a current authorization decision.
            while scope.entries and (len(scope.entries) >= MAX_BUNDLES
                                     or scope.bytes + size > MAX_BYTES):
                oldest = next(iter(scope.entries))
                previous = scope.entries.pop(oldest)
                scope.bytes -= len(oldest.encode()) + len(previous)
            scope.entries[key] = raw
            scope.bytes += size
    except (OSError, sqlite3.Error, TypeError, ValueError, RecursionError):
        scope.clear()
    return result
