"""Read public, dated source entries and persist per-source coverage."""
from datetime import date, datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
from html.parser import HTMLParser
from http.client import HTTPConnection, HTTPException
import re
import time
from urllib.parse import quote, urljoin, urlsplit
from xml.etree import ElementTree

from .contracts import WCEError
from .own_bootstrap_security import path_check
from .own_connection_policy import atomic_write, locked, read_optional
from .video_relay import PublicHTTPSConnection, PublicDestinationError

MAX_BYTES = 768 * 1024
MAX_SOURCES = 100
MAX_RESULTS = 15
SCAN_BYTES = 10 * 1024 * 1024
SCAN_LIMIT = {'type': 'integer', 'minimum': 1, 'maximum': 4}
TIMEOUT = 5
SITE_GAP = 1.0
RSS_TYPES = {'application/rss+xml', 'application/atom+xml'}


def timestamp(value):
    try:
        result = datetime.fromisoformat(value.replace('Z', '+00:00'))
    except ValueError:
        try:
            result = parsedate_to_datetime(value)
        except (TypeError, ValueError, OverflowError):
            return None
    if result.tzinfo is None:
        return None
    return result.astimezone(timezone.utc)


def utc_now():
    return datetime.now(timezone.utc)


class PublicHTTPConnection(HTTPConnection):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Keep Host and TLS identity separate from the DNS-checked socket target.
        self._create_connection = PublicHTTPSConnection.connect_public


def fetch_page(url, public_url, admission):
    for _ in range(4):
        current = public_url(url)
        parts = urlsplit(current)
        if parts.port not in (None, 443 if parts.scheme == 'https' else 80):
            raise WCEError('SOURCE_SCAN_PORT_UNSUPPORTED')
        admission(parts.hostname)
        factory = PublicHTTPSConnection if parts.scheme == 'https' else PublicHTTPConnection
        conn = factory(parts.hostname, port=parts.port, timeout=TIMEOUT)
        try:
            target = quote(parts.path, safe="/:%@!$&'()*+,;=")
            if parts.query:
                target += '?' + quote(parts.query, safe="/?:%@!$&'()*+,;=")
            conn.request('GET', target, headers={
                'User-Agent': 'Jiusera source reader',
                'Accept': 'application/rss+xml, application/atom+xml, text/html, application/xml;q=0.9, */*;q=0.4',
                'Accept-Encoding': 'identity',
            })
            with conn.getresponse() as response:
                if response.status in {301, 302, 303, 307, 308} and response.getheader('Location'):
                    url = urljoin(current, response.getheader('Location'))
                    continue
                if response.status in {429, 503}:
                    raise WCEError('SOURCE_SCAN_RATE_LIMITED')
                if response.status != 200:
                    raise WCEError('SOURCE_SCAN_HTTP_' + str(response.status))
                if response.getheader('Content-Encoding', 'identity').lower() != 'identity':
                    raise WCEError('SOURCE_SCAN_ENCODING_UNSUPPORTED')
                size = response.getheader('Content-Length')
                if size is not None and (not size.isdecimal() or int(size) > MAX_BYTES):
                    raise WCEError('SOURCE_SCAN_RESPONSE_TOO_LARGE')
                body = response.read(MAX_BYTES + 1)
                if len(body) > MAX_BYTES:
                    raise WCEError('SOURCE_SCAN_RESPONSE_TOO_LARGE')
                charset = response.headers.get_param('charset') or 'utf-8-sig'
                try:
                    return current, response.headers.get_content_type(), body.decode(charset, errors='replace')
                except LookupError:
                    raise WCEError('SOURCE_SCAN_ENCODING_UNSUPPORTED') from None
        except PublicDestinationError:
            raise WCEError('SOURCE_SCAN_PUBLIC_DESTINATION_REQUIRED') from None
        except TimeoutError:
            raise WCEError('SOURCE_SCAN_TIMEOUT') from None
        except (OSError, HTTPException, ValueError):
            raise WCEError('SOURCE_SCAN_NETWORK_FAILED') from None
        finally:
            conn.close()
    raise WCEError('SOURCE_SCAN_REDIRECT_LIMIT')


def local(tag):
    return tag.rsplit('}', 1)[-1]


def feed_entries(document):
    if re.search(r'<!\s*(?:DOCTYPE|ENTITY)\b', document, re.I):
        raise WCEError('SOURCE_SCAN_UNSUPPORTED_FEED')
    try:
        root = ElementTree.fromstring(document)
    except ElementTree.ParseError:
        raise WCEError('SOURCE_SCAN_INVALID_FEED') from None
    kind = local(root.tag)
    if kind not in {'rss', 'feed', 'RDF'}:
        raise WCEError('SOURCE_SCAN_UNSUPPORTED_FEED')
    if kind == 'rss' and not any(local(child.tag) == 'channel' for child in root):
        raise WCEError('SOURCE_SCAN_INVALID_FEED')
    for item in root.iter():
        if local(item.tag) not in {'item', 'entry'}:
            continue
        fields = {}
        for child in item:
            key = local(child.tag)
            if key == 'link' and child.get('rel', 'alternate') != 'alternate':
                continue
            fields.setdefault(key, child.get('href') if key == 'link' and child.get('href') else ''.join(child.itertext()).strip())
        yield fields.get('link'), fields.get('title'), (fields.get('pubDate') or fields.get('published') or
                                                         fields.get('date') or fields.get('updated'))


class ArticleIndex(HTMLParser):
    """Static article/list rows with a real time element; no client JS or file execution."""

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.rows = []
        self.stack = []
        self.anchor = False
        self.feed_url = None
        self.meta = {}

    def handle_starttag(self, tag, pairs):
        attrs = dict(pairs)
        if tag == 'link' and attrs.get('type') in RSS_TYPES and 'alternate' in attrs.get('rel', '').split():
            self.feed_url = self.feed_url or attrs.get('href')
        if tag == 'meta':
            name = attrs.get('property')
            if name in {'og:url', 'og:title', 'article:published_time'}:
                self.meta[name] = attrs.get('content')
        if tag in {'li', 'article'}:
            self.stack.append({'tag': tag, 'link': None, 'title': '', 'date': None})
        if not self.stack:
            return
        row = self.stack[-1]
        if tag == 'time':
            row['date'] = row['date'] or attrs.get('datetime')
        if tag == 'a' and attrs.get('href') and not row['link']:
            row['link'] = attrs['href']
            self.anchor = True

    def handle_endtag(self, tag):
        if tag == 'a':
            self.anchor = False
        if self.stack and self.stack[-1]['tag'] == tag:
            row = self.stack.pop()
            if row['link'] and row['date']:
                self.rows.append((row['link'], row['title'].strip(), row['date']))

    def handle_data(self, value):
        if self.anchor and self.stack:
            row = self.stack[-1]
            row['title'] = (row['title'] + value)[:500]


def observed_date(raw, since, through):
    if not raw:
        return None
    observed = timestamp(raw)
    if observed is not None:
        return since <= observed < through, observed.isoformat(), 'time'
    try:
        day = date.fromisoformat(raw) if re.fullmatch(r'\d{4}-\d{2}-\d{2}', raw) else None
    except ValueError:
        return None
    if day is None:
        return None
    start = datetime.combine(day, datetime.min.time(), timezone.utc)
    end = start + timedelta(days=1)
    # A day without time/zone cannot resolve an overlapping sub-day boundary.
    if start >= since and end <= through:
        return True, day.isoformat(), 'day'
    if end <= since or start >= through:
        return False, day.isoformat(), 'day'
    return None


def observe(address, kind, since, through, public_url, admission, fetch):
    final, mime, document = fetch(address, public_url, admission)
    if mime in RSS_TYPES or kind == 'rss' or document.lstrip().startswith(('<?xml', '<rss', '<feed')):
        entries = list(feed_entries(document))
        representation = 'feed'
    else:
        parsed = ArticleIndex()
        try:
            parsed.feed(document)
        except (ValueError, AssertionError):
            raise WCEError('SOURCE_SCAN_INVALID_PAGE') from None
        entries = parsed.rows
        representation = 'html'
        if parsed.meta.get('article:published_time'):
            entries.append((parsed.meta.get('og:url') or final, parsed.meta.get('og:title'), parsed.meta['article:published_time']))
        if not entries and parsed.feed_url:
            feed_url = public_url(urljoin(final, parsed.feed_url))
            if urlsplit(feed_url).hostname != urlsplit(final).hostname:
                raise WCEError('SOURCE_SCAN_REDIRECTED_FEED_SCOPE')
            final, _, document = fetch(feed_url, public_url, admission)
            entries = list(feed_entries(document))
            representation = 'feed'
        if not entries and representation == 'html':
            raise WCEError('SOURCE_SCAN_NO_DATED_ARTICLES')
    articles = {}
    date_unknown = 0
    for link, title, raw_date in entries:
        try:
            original = public_url(urljoin(final, link)) if link else None
        except (ValueError, WCEError):
            original = None
        observed = observed_date(raw_date, since, through)
        if not original or not observed:
            date_unknown += 1
        elif observed[0] and original not in articles:
            articles[original] = {'url': original, 'title': (title or '')[:500],
                                  'published_at': observed[1], 'precision': observed[2]}
    articles = sorted(articles.values(), key=lambda item: item['published_at'], reverse=True)
    if date_unknown and not articles:
        raise WCEError('SOURCE_SCAN_INCOMPLETE_DATES')
    return {'status': 'new' if articles else 'no_update', 'articles': articles[:MAX_RESULTS],
            'article_count': len(articles), 'unresolved_entries': date_unknown, 'representation': representation}


class SourceScan:
    def __init__(self, library, *, fetch=fetch_page, clock=utc_now):
        self.library = library
        self.fetch = fetch
        self.clock = clock

    def run(self, args, scope):
        from .source_library import public_url, require, valid_entry
        require(bool(scope), 'SOURCE_ACCOUNT_REQUIRED')
        command, identifier = args['action'], args['scan_id']
        start = command == 'start_scan'
        folder = self.library.folder(args['project_id'], ('Scans',), scope=scope, create=start)
        require(folder is not None, 'SOURCE_SCAN_NOT_FOUND')
        path = folder / (identifier + '.json')
        if command == 'read_scan':
            snapshot = read_optional(path, SCAN_BYTES)
            require(snapshot is not None, 'SOURCE_SCAN_NOT_FOUND')
            return snapshot
        with locked(folder / (identifier + '.lock'), nonblocking=True):
            pin = path_check(folder, True)
            snapshot = read_optional(path, SCAN_BYTES)
            def store():
                atomic_write(path, snapshot, SCAN_BYTES, expected_parent=pin)
            if start:
                since = timestamp(args['since'])
                through = timestamp(args['through'])
                require(since is not None and through is not None and since < through <= self.clock()
                        and through-since <= timedelta(days=30), 'SOURCE_SCAN_WINDOW_INVALID')
                window = {'since': since.isoformat(), 'through': through.isoformat()}
                if snapshot is not None:
                    require(snapshot['window'] == window, 'SOURCE_SCAN_ID_CONFLICT')
                    return snapshot
                connection = args['connection_id']
                catalog = self.library.catalog(self.library.folder(args['project_id'], scope=scope))
                require(len(catalog['sources']) <= MAX_SOURCES, 'SOURCE_SCAN_CATALOG_LIMIT')
                rows = [valid_entry(key, row, connection) for key, row in sorted(catalog['sources'].items())]
                snapshot = dict(state='SOURCE_SCAN', scan_id=identifier, connection_id=connection,
                                project_id=args['project_id'], catalog_revision=catalog['revision'], window=window,
                                created_at=self.clock().isoformat(), rows=[{
                                    'source_id': row['id'], 'name': row['name'], 'url': row['url'],
                                    'kind': row['kind'], 'status': 'unscanned', 'attempts': 0,
                                } for row in rows])
                store()
                return snapshot
            require(snapshot is not None, 'SOURCE_SCAN_NOT_FOUND')
            pending = [row for row in snapshot['rows'] if row['status'] == 'unscanned']
            if args.get('retry_failed'):
                pending += [row for row in snapshot['rows'] if row['status'] == 'failed']
            if 'source_ids' in args:
                indexed = {row['source_id']: row for row in snapshot['rows']}
                requested = list(dict.fromkeys(args['source_ids']))
                require(all(ident in indexed for ident in requested), 'SOURCE_SCAN_ID_NOT_IN_SNAPSHOT')
                pending = [indexed[ident] for ident in requested if indexed[ident] in pending]
            if not pending:
                return snapshot
            limiter = self.library.folder(args['project_id'], ('ScanRate',), create=True)
            for row in pending[:args.get('limit', 1)]:
                if row.get('attempted_at'):
                    previous = {key: row[key] for key in ('status', 'attempted_at', 'completed_at', 'error') if key in row}
                    row['previous_attempts'] = (row.get('previous_attempts', []) + [previous])[-4:]
                row.pop('completed_at', None)
                row.pop('error', None)
                row.update(status='unscanned', attempted_at=self.clock().isoformat(), attempts=row['attempts']+1)
                store()
                try:
                    details = observe(row['url'],row['kind'],timestamp(snapshot['window']['since']),
                                      timestamp(snapshot['window']['through']),public_url,
                                      lambda host: self.admit(limiter, host),self.fetch)
                except WCEError as error:
                    details = {'status': 'failed', 'error': error.code}
                row.update(details, completed_at=self.clock().isoformat())
                store()
            return snapshot

    @staticmethod
    def admit(folder, host):
        from hashlib import sha256
        name = 'host-' + sha256(host.encode()).hexdigest()
        with locked(folder / (name + '.lock')):
            path = folder / (name + '.json')
            previous = read_optional(path) or {}
            wait = min(SITE_GAP, max(0, previous.get('at', 0) + SITE_GAP - time.time()))
            if wait:
                time.sleep(wait)
            atomic_write(path, {'at': time.time()}, expected_parent=path_check(folder, True))
