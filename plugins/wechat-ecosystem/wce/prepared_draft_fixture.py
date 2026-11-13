"""Fixed local wire receiver and independently committed synthetic news objects.

GET reads received persistent objects. It never receives an expected article.
This store has its own application ID and is not a business/HTTP/mock database.
"""
from contextlib import closing, contextmanager
from contextvars import ContextVar
from collections import OrderedDict
from copy import deepcopy
from dataclasses import dataclass, field
import json
import math
import os
from pathlib import Path
import re
import sqlite3
from threading import Lock, get_ident
import time
from urllib.parse import parse_qsl, urlsplit
from uuid import uuid4

from .contracts import WCEError
from .draft_wire import unique_object
from .http_transport import HTTPRequest, HTTPResponse, MAX_BODY
from .local_preparation import plain, ref
from .service import canonical, digest
from .storage import _structure
from .upload_wire import _integer, _float, _constant

FIXTURE_APP_ID = 0x57435046
FIXTURE_SCHEMA_VERSION = 1
PROVENANCE = 'LOCAL_FIXED_FIXTURE'
FIXTURE_SCHEMA = """
CREATE TABLE fixture_config (
 id INTEGER PRIMARY KEY CHECK(id=1),
 mode TEXT NOT NULL CHECK(mode='test'),
 provenance TEXT NOT NULL CHECK(provenance='LOCAL_FIXED_FIXTURE'));
CREATE TABLE fixture_news (
 reference TEXT PRIMARY KEY, context TEXT NOT NULL,
 article TEXT NOT NULL, created REAL NOT NULL);
"""


def reference_valid(value):
    return isinstance(value, str) and re.fullmatch('fixture-prepared-draft-[a-f0-9]{32}', value) is not None


# Exact forbidden controls: HT/LF remain valid JSON string data.
_JSON_CONTROL = re.compile(r'[\x00-\x08\x0b-\x1f]')


# Logical retained raw + serialized JSON bytes, not a Python heap estimate.
_DECODE_ENTRIES = 2048
_DECODE_BYTES = 64 * 1024 * 1024
_DECODE_CURRENT = ContextVar('wce_decoded_json_request', default=None)


class _DecodedJsonMemo:
    def __init__(self):
        self.pid, self.thread = os.getpid(), get_ident()
        self.active = True
        self.entries, self.retained = OrderedDict(), 0

    def clear(self):
        self.entries.clear()
        self.retained = 0

    def remove(self, key):
        previous = self.entries.pop(key, None)
        if previous is not None:
            self.retained -= previous[1]

    def remember(self, key, value, *, serialized_size=None, extra_size=0):
        try:
            # Every cached tree came from the full decoder below, never a
            # caller object. Copy before returning the first mutable result.
            if serialized_size is None:
                serialized_size = len(json.dumps(value, ensure_ascii=False,
                    separators=(',', ':'), allow_nan=False).encode('utf-8'))
            if type(serialized_size) is not int or serialized_size < 0 or type(extra_size) is not int or extra_size < 0:
                raise ValueError()
            size = len(key[0]) + serialized_size + extra_size
            if size > _DECODE_BYTES:
                return  # One oversized item cannot disable other useful entries.
            saved = deepcopy(value)
            self.remove(key)
            while self.entries and (len(self.entries) >= _DECODE_ENTRIES
                                    or self.retained + size > _DECODE_BYTES):
                _, (_, previous_size) = self.entries.popitem(last=False)
                self.retained -= previous_size
            if _DECODE_ENTRIES > 0 and self.retained + size <= _DECODE_BYTES:
                self.entries[key] = (saved, size)
                self.retained += size
        except Exception:
            # A pure optimization cannot change a successful original decode.
            self.clear()


@contextmanager
def decoded_json_scope():
    memo = _DecodedJsonMemo()
    token = _DECODE_CURRENT.set(memo)
    try:
        yield
    finally:
        # A captured Context still points at this object after reset. Revoke
        # that lifetime before clearing it; a later Context.run cannot revive it.
        memo.active = False
        memo.clear()
        _DECODE_CURRENT.reset(token)


def decode_json(data, maximum=MAX_BODY, *, max_nodes=1024):
    """Request-local exact-byte pure parsing reuse; never source or authority."""
    memo = _DECODE_CURRENT.get()
    eligible = (memo is not None and memo.active and memo.pid == os.getpid()
        and memo.thread == get_ident() and type(data) is bytes
        and type(maximum) is int and maximum > 0
        and type(max_nodes) is int and max_nodes > 0)
    if not eligible:
        return _decode_json_full(data, maximum, max_nodes=max_nodes)
    key = (data, maximum, max_nodes)
    entry = memo.entries.get(key)
    if entry is not None:
        try:
            result = deepcopy(entry[0])
            memo.entries.move_to_end(key)
            return result
        except Exception:
            memo.remove(key)
    value = _decode_json_full(data, maximum, max_nodes=max_nodes)
    memo.remember(key, value)
    return value


def _decode_json_full(data, maximum=MAX_BODY, *, max_nodes=1024):
    """Strict bounded JSON; LF/HT remain data, never executable HTML."""
    if not isinstance(data, bytes) or not 0 < len(data) <= maximum:
        raise WCEError('INVALID_PREPARED_DRAFT_WIRE')
    try:
        value = json.loads(data.decode('utf-8'), object_pairs_hook=unique_object,
                           parse_constant=_constant, parse_int=_integer, parse_float=_float)
        stack, nodes = [(value, 1)], 0
        while stack:
            item, depth = stack.pop()
            nodes += 1
            if nodes > max_nodes or depth > 16:
                raise ValueError()
            if isinstance(item, str):
                if len(item.encode()) > maximum or _JSON_CONTROL.search(item) is not None:
                    raise ValueError()
            elif isinstance(item, dict):
                stack.extend((v, depth + 1) for v in item.keys())
                stack.extend((v, depth + 1) for v in item.values())
            elif isinstance(item, list):
                stack.extend((v, depth + 1) for v in item)
        return value
    except Exception:
        raise WCEError('INVALID_PREPARED_DRAFT_WIRE') from None


def validate_article(article):
    try:
        if not isinstance(article, dict) or set(article) != {'title', 'content', 'thumb_media_id'}:
            raise ValueError()
        plain(article['title'], 128)
        plain(article['content'], 2000)
        if (len(article['title']) > 32 or len(article['content'].encode()) >= 2000
                or not isinstance(article['thumb_media_id'], str)
                or re.fullmatch('[A-Za-z0-9_-]{1,128}', article['thumb_media_id']) is None):
            raise ValueError()
        return article
    except (WCEError, ValueError, UnicodeError):
        raise WCEError('INVALID_PREPARED_NEWS') from None


@dataclass(frozen=True)
class _FixtureContext:
    scope: str = field(repr=False)
    selector: str = field(repr=False)
    renderer_version: int
    projection_digest: str

    def value(self):
        try:
            scope = decode_json(self.scope.encode(), 2048)
            selector = decode_json(self.selector.encode(), 2048)
            if (not isinstance(scope, dict) or set(scope) != {'tenant', 'principal', 'connection', 'resource'}
                    or canonical(scope) != self.scope or not isinstance(selector, dict)
                    or set(selector) != {'bundle_id', 'version', 'content_digest'} or canonical(selector) != self.selector
                    or type(self.renderer_version) is not int or self.renderer_version != 1
                    or re.fullmatch('[a-f0-9]{64}', self.projection_digest) is None
                    or re.fullmatch('[a-f0-9]{64}', selector['content_digest']) is None):
                raise ValueError()
            for value in scope.values():
                plain(value, 128)
            ref(selector['bundle_id'], 'bundle')
            ref(selector['version'], 'version')
            return {'scope': scope, 'selector': selector, 'renderer_version': 1,
                    'projection_digest': self.projection_digest}
        except Exception:
            raise WCEError('INVALID_PREPARED_FIXTURE_CONTEXT') from None


class _FixtureStore:
    def __init__(self, path, clock):
        self.path, self.clock = Path(path), clock
        if self.path.is_symlink():
            raise ValueError('Fixture state must not be a symlink')
        self.path.parent.mkdir(parents=True, exist_ok=True)
        try:
            fd = os.open(self.path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
            os.close(fd)
        except FileExistsError:
            pass
        with self.transaction(True, check=False) as db:
            app = db.execute('PRAGMA application_id').fetchone()[0]
            version = db.execute('PRAGMA user_version').fetchone()[0]
            objects = db.execute("SELECT name FROM sqlite_master WHERE type IN ('table','view')").fetchall()
            if objects:
                if app != FIXTURE_APP_ID or version != FIXTURE_SCHEMA_VERSION:
                    raise ValueError('Refusing unrelated fixture state')
                self._check(db)
            else:
                if app not in (0, FIXTURE_APP_ID) or version != 0:
                    raise ValueError('Unsupported fixture state')
                for statement in FIXTURE_SCHEMA.split(';'):
                    if statement.strip():
                        db.execute(statement)
                db.execute('INSERT INTO fixture_config VALUES(1,?,?)', ('test', PROVENANCE))
                db.execute(f'PRAGMA application_id={FIXTURE_APP_ID}')
                db.execute(f'PRAGMA user_version={FIXTURE_SCHEMA_VERSION}')
                self._check(db)

    def _check(self, db):
        if (db.execute('PRAGMA application_id').fetchone()[0] != FIXTURE_APP_ID
                or db.execute('PRAGMA user_version').fetchone()[0] != FIXTURE_SCHEMA_VERSION):
            raise ValueError('Invalid fixture state identity')
        names = {r[0] for r in db.execute("SELECT name FROM sqlite_master WHERE type IN ('table','view')")}
        if names != {'fixture_config', 'fixture_news'}:
            raise ValueError('Invalid fixture state structure')
        with closing(sqlite3.connect(':memory:')) as expected:
            expected.executescript(FIXTURE_SCHEMA)
            for table in names:
                if _structure(db, table) != _structure(expected, table):
                    raise ValueError('Invalid fixture state structure')
        if [tuple(r) for r in db.execute('SELECT * FROM fixture_config')] != [(1, 'test', PROVENANCE)]:
            raise ValueError('Invalid fixture state mode')

    @contextmanager
    def transaction(self, write=False, check=True):
        if self.path.is_symlink():
            raise ValueError('Fixture state must not be a symlink')
        db = sqlite3.connect(self.path, timeout=10, isolation_level=None)
        db.row_factory = sqlite3.Row
        try:
            db.execute('BEGIN IMMEDIATE' if write else 'BEGIN')
            if check:
                self._check(db)
            yield db
            db.commit()
        except BaseException:
            db.rollback()
            raise
        finally:
            db.close()

    def add(self, context, article):
        value = context.value()
        validate_article(article)
        if digest(article) != value['projection_digest']:
            raise WCEError('PREPARED_FIXTURE_PROJECTION_MISMATCH')
        reference = 'fixture-prepared-draft-' + uuid4().hex
        now = self.clock()
        if type(now) not in (int, float) or not math.isfinite(now):
            raise WCEError('INVALID_PREPARED_FIXTURE_CLOCK')
        with self.transaction(True) as db:
            db.execute('INSERT INTO fixture_news VALUES(?,?,?,?)',
                       (reference, canonical(value), canonical(article), now))
        return reference  # remote commit precedes the independent business commit

    def get(self, context, reference):
        if not reference_valid(reference):
            raise WCEError('INVALID_PREPARED_FIXTURE_REFERENCE')
        value = context.value()
        with self.transaction() as db:
            row = db.execute('SELECT * FROM fixture_news WHERE reference=?', (reference,)).fetchone()
            if row is None:
                raise WCEError('PREPARED_FIXTURE_NOT_FOUND')
            stored = decode_json(row['context'].encode(), 4096)
            article = decode_json(row['article'].encode(), 16384)
            if (stored != value or canonical(stored) != row['context'] or canonical(article) != row['article']
                    or type(row['created']) not in (int, float) or not math.isfinite(row['created'])):
                raise WCEError('PREPARED_FIXTURE_OBJECT_MISMATCH')
            validate_article(article)
        return article  # actual stored body; no caller expected content is available


class FixturePreparedDraftSender:
    mode = 'test'

    def __init__(self, path, clock=time.time):
        self.store = _FixtureStore(path, clock)
        self.calls = self.add_calls = self.get_calls = 0
        self.last_request = None
        self._lock = Lock()

    def send(self, request, context, timeout):
        if (self.mode != 'test' or type(context) is not _FixtureContext or type(request) is not HTTPRequest
                or request.test_only is not True or request.method != 'POST' or timeout != 10
                or request.headers != {'Content-Type': 'application/json; charset=utf-8'}
                or not isinstance(request.path, str) or len(request.path) > 8192):
            raise WCEError('INVALID_PREPARED_FIXTURE_REQUEST')
        parts = urlsplit(request.path)
        query = parse_qsl(parts.query, keep_blank_values=True, strict_parsing=True)
        if (parts.scheme or parts.netloc or parts.fragment or parts.path not in ('/cgi-bin/draft/add', '/cgi-bin/draft/get')
                or len(query) != 1 or query[0][0] != 'access_token' or not 8 <= len(query[0][1]) <= 4096
                or any(not 33 <= ord(c) <= 126 for c in query[0][1])):
            raise WCEError('INVALID_PREPARED_FIXTURE_REQUEST')
        context.value()
        body = decode_json(request.body, 16384)
        add = parts.path == '/cgi-bin/draft/add'
        if add:
            if not isinstance(body, dict) or set(body) != {'articles'} or not isinstance(body['articles'], list) or len(body['articles']) != 1:
                raise WCEError('INVALID_PREPARED_FIXTURE_REQUEST')
            validate_article(body['articles'][0])
        elif not isinstance(body, dict) or set(body) != {'media_id'} or not reference_valid(body['media_id']):
            raise WCEError('INVALID_PREPARED_FIXTURE_REQUEST')
        with self._lock:
            self.calls += 1
            self.add_calls += int(add)
            self.get_calls += int(not add)
            self.last_request = request
        if add:
            reference = self.store.add(context, body['articles'][0])
            return HTTPResponse(200, canonical({'media_id': reference}).encode())
        article = self.store.get(context, body['media_id'])
        return HTTPResponse(200, canonical({'news_item': [article]}).encode())
