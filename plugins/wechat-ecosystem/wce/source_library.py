"""Reusable public source entrances and exact article references, scoped to one project and optional official account."""
from datetime import datetime, timezone
from hashlib import sha256
import ipaddress
import os
import re
from urllib.parse import parse_qsl, urlsplit, urlunsplit

from .contracts import WCEError
from .own_bootstrap_security import path_check
from .own_connection_policy import atomic_write, locked, read_optional, resolve
from .prepared_contracts import strict_validate
from .service import digest
from .source_scan import SourceScan, SCAN_LIMIT
from .tools import schema

TOOL = 'own.sources.library'
FOLDER = ('JiuseraAssets', 'Sources')
FORMAT = 1
MAX_CATALOG = 16 * 1024 * 1024
MAX_RESEARCH = 512 * 1024
MAX_REVISION = 2**53 - 1
CONNECTION = {'type': 'string', 'minLength': 1, 'maxLength': 128, 'pattern': r'^[A-Za-z0-9_-]+$'}
REVIEW = {'type': 'string', 'enum': ['pending', 'approved', 'rejected']}
STAMP = {'type': 'string', 'minLength': 1, 'maxLength': 50}
ID = {'type': 'string', 'pattern': r'[a-f0-9]{32}'}
WORK_ID = {'type': 'string', 'pattern': r'[A-Za-z0-9][A-Za-z0-9_-]{0,95}'}
CHECKPOINT = {'type': 'integer', 'minimum': 0, 'maximum': MAX_REVISION}
REVISION = CHECKPOINT | {'minimum': 1}
KIND = {'type': 'string', 'enum': ['website', 'newsroom', 'section', 'account', 'rss']}
ORIGIN = {'type': 'string', 'enum': ['user', 'codex']}
SENSITIVE_PARAMETER = re.compile(
    r'(?i)(?:token|access[_-]?token|refresh[_-]?token|api[_-]?key|secret|password|session|'
    r'sessionid|auth(?:orization)?|signature|x-amz-.+|oauth[_-]?.+)'
)


def text(size, minimum=0):
    return {'type': 'string', 'minLength': minimum, 'maxLength': size, 'x-wce-maxUtf8Bytes': size * 4}


def action(name, required, optional=None):
    return schema({'action': {'type': 'string', 'const': name}, 'project_id': ID, **required},
                  {'connection_id': CONNECTION, **(optional or {})})


URL = text(4096, 1)
METADATA = {'name': text(160, 1), 'topic': text(180), 'kind': KIND}
REFERENCE = schema({'url': URL}, {'title': text(500), 'source_id': ID})
ENTRY = schema({'id': ID, 'url': URL, 'origin': ORIGIN, 'revision': REVISION, **METADATA},
               {'review': REVIEW, 'reviewed_at': STAMP})
CONTEXT = schema({'platform': {'type': 'string', 'enum': ['wechat_official_account', 'x', 'xiaohongshu']},
                  'connection_id': text(128, 1)})
SPEC = {'oneOf': [
    action('list', {}, {'known_revision': CHECKPOINT}),
    action('add', {'url': URL, 'origin': ORIGIN}, METADATA),
    action('edit', {'source_id': ID, 'expected_revision': REVISION, 'name': METADATA['name']},
           {'topic': METADATA['topic'], 'kind': KIND, 'review': REVIEW}),
    action('configure', {'strict': {'type': 'boolean'}, 'expected_revision': CHECKPOINT}),
    action('record_research', {'research_id': WORK_ID, 'expected_revision': CHECKPOINT,
                               'title': text(250, 1), 'references': {
                                   'type': 'array', 'minItems': 1, 'maxItems': 50, 'items': REFERENCE}},
           {'account': CONTEXT}),
    action('read_research', {'research_id': WORK_ID}),
    action('start_scan', {'scan_id': WORK_ID, 'since': STAMP, 'through': STAMP}),
    action('check_scan', {'scan_id': WORK_ID}, {'limit': SCAN_LIMIT, 'retry_failed': {'type': 'boolean'},
                                                 'source_ids': {'type': 'array', 'minItems': 1, 'maxItems': 4, 'items': ID}}),
    action('read_scan', {'scan_id': WORK_ID}),
]}


def require(condition, code):
    if not condition:
        raise WCEError(code)


def source_id(address, connection=None):
    key = address if connection is None else connection + '\0' + address
    return sha256(key.encode()).hexdigest()[:32]


def valid_entry(identifier, row, connection=None):
    try:
        strict_validate(row, ENTRY)
        address = public_url(row['url'])
    except WCEError:
        raise WCEError('SOURCE_STORAGE_INVALID') from None
    require(row['id'] == identifier == source_id(address, connection)
            and row['url'] == address, 'SOURCE_STORAGE_INVALID')
    return row


def public_url(value):
    value = value.strip()
    require(not any(c.isspace() or ord(c) < 32 or c == '\\' for c in value), 'SOURCE_INVALID_URL')
    try:
        parts = urlsplit(value)
        host = parts.hostname or ''
        port = parts.port
        require(parts.scheme in ('http', 'https') and bool(host) and parts.username is None
                and parts.password is None, 'SOURCE_INVALID_URL')
        try:
            ip = ipaddress.ip_address(host)
        except ValueError:
            ip = None
        if ip is not None:
            require(ip.is_global and not ip.is_multicast, 'SOURCE_PUBLIC_URL_REQUIRED')
            host = f'[{ip.compressed}]' if ip.version == 6 else ip.compressed
        else:
            host = host.rstrip('.').encode('idna').decode('ascii').lower()
            labels = host.split('.')
            require(len(labels) > 1 and all(re.fullmatch(r'[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?', label)
                                             for label in labels)
                    and bool(re.search(r'[a-z]', labels[-1]))
                    and labels[-1] not in {'localhost', 'local', 'internal', 'test', 'invalid', 'onion'},
                    'SOURCE_PUBLIC_URL_REQUIRED')
        require(not any(SENSITIVE_PARAMETER.fullmatch(key) for key, _ in
                        parse_qsl(parts.query, keep_blank_values=True, max_num_fields=256)),
                'SOURCE_PRIVATE_URL_PARAMETER')
        default_port = 443 if parts.scheme == 'https' else 80
        authority = host if port in (None, default_port) else f'{host}:{port}'
        # Keep every path, query parameter and fragment so distinct sections remain distinct.
        return urlunsplit((parts.scheme, authority, parts.path or '/', parts.query, parts.fragment))
    except (UnicodeError, ValueError):
        raise WCEError('SOURCE_INVALID_URL') from None


class SourceLibrary:
    def __init__(self, router, connection_reader=resolve):
        self.director = router.director
        self.jobs = router.jobs
        self.connection_reader = connection_reader

    def scope(self, connection):
        if connection is None:
            return ()
        try:
            self.connection_reader(connection, readonly=True)
        except WCEError as error:
            code = 'SOURCE_ACCOUNT_NOT_BOUND' if error.code == 'CONNECTION_NOT_BOUND' else 'SOURCE_ACCOUNT_UNAVAILABLE'
            raise WCEError(code) from None
        return ('WeChat', sha256(connection.encode()).hexdigest())

    def folder(self, project, extra=(), *, scope=(), create=False):
        root, pin = self.director.project(project)
        parts = FOLDER + scope + extra
        try:
            fd = self.jobs._project_video_folder({'root': str(root)}, list(pin), create=create, components=parts)
        except FileNotFoundError:
            if not create:
                return None
            raise WCEError('SOURCE_STORAGE_UNAVAILABLE') from None
        except (OSError, WCEError):
            raise WCEError('SOURCE_STORAGE_UNAVAILABLE') from None
        os.close(fd)
        return root.joinpath(*parts)

    @staticmethod
    def catalog(folder):
        try:
            current = read_optional(folder / 'library.json', MAX_CATALOG) if folder is not None else None
        except (OSError, WCEError):
            raise WCEError('SOURCE_STORAGE_INVALID') from None
        if current is None:
            return {'format': FORMAT, 'revision': 0, 'sources': {}}
        require(type(current) is dict and type(current.get('format')) is int and current['format'] == FORMAT,
                'SOURCE_FORMAT_UNSUPPORTED')
        require(type(current.get('strict', False)) is bool and type(current.get('revision')) is int and 0 <= current['revision'] <= MAX_REVISION
                and type(current.get('sources')) is dict,
                'SOURCE_STORAGE_INVALID')
        return current

    @staticmethod
    def requested_metadata(args):
        return {key: args[key].strip() if key != 'kind' else args[key]
                for key in METADATA if key in args}

    def add(self, args, scope):
        address = public_url(args['url'])
        metadata = self.requested_metadata(args)
        connection = args.get('connection_id')
        identifier = source_id(address, connection)
        require(bool(metadata.get('name', urlsplit(address).hostname)), 'SOURCE_NAME_REQUIRED')
        folder = self.folder(args['project_id'], scope=scope, create=True)
        with locked(folder / 'library.lock'):
            pin = path_check(folder, True)
            state = self.catalog(folder)
            previous = state['sources'].get(identifier)
            if previous is not None:
                valid_entry(identifier, previous, connection)
                require(previous['url'] == address, 'SOURCE_ID_CONFLICT')
                return {'state': 'SOURCE_EXISTS', 'source': previous, 'revision': state['revision']}
            row = {'id': identifier, 'url': address, 'origin': args['origin'], 'revision': 1,
                   'name': urlsplit(address).hostname, 'topic': '', 'kind': 'website', **metadata}
            state['sources'][identifier] = row
            state['revision'] += 1
            require(state['revision'] <= MAX_REVISION, 'SOURCE_REVISION_LIMIT')
            atomic_write(folder / 'library.json', state, MAX_CATALOG, expected_parent=pin)
            return {'state': 'SOURCE_ADDED', 'source': row, 'revision': state['revision']}

    def edit(self, args, scope):
        folder = self.folder(args['project_id'], scope=scope)
        require(folder is not None, 'SOURCE_NOT_FOUND')
        with locked(folder / 'library.lock'):
            pin = path_check(folder, True)
            state = self.catalog(folder)
            row = state['sources'].get(args['source_id'])
            require(row is not None, 'SOURCE_NOT_FOUND')
            valid_entry(args['source_id'], row, args.get('connection_id'))
            metadata = self.requested_metadata(args)
            require(bool(metadata['name']), 'SOURCE_NAME_REQUIRED')
            if 'review' in args and args['review'] != row.get('review', 'pending'):
                metadata.update(review=args['review'], reviewed_at=datetime.now(timezone.utc).isoformat())
            if all(row.get(key) == value for key, value in metadata.items()):
                return {'state': 'SOURCE_UNCHANGED', 'source': row, 'revision': state['revision']}
            require(row['revision'] == args['expected_revision'], 'SOURCE_STALE_REVISION')
            row.update(metadata, revision=row['revision'] + 1)
            state['revision'] += 1
            require(state['revision'] <= MAX_REVISION, 'SOURCE_REVISION_LIMIT')
            atomic_write(folder / 'library.json', state, MAX_CATALOG, expected_parent=pin)
            return {'state': 'SOURCE_EDITED', 'source': row, 'revision': state['revision']}

    def configure(self, args, scope):
        require(bool(scope), 'SOURCE_ACCOUNT_REQUIRED')
        folder = self.folder(args['project_id'], scope=scope, create=True)
        with locked(folder / 'library.lock'):
            pin = path_check(folder, True)
            state = self.catalog(folder)
            if state.get('strict', False) != args['strict']:
                require(state['revision'] == args['expected_revision'], 'SOURCE_STALE_REVISION')
                state['strict'] = args['strict']
                state['revision'] += 1
                require(state['revision'] <= MAX_REVISION, 'SOURCE_REVISION_LIMIT')
                atomic_write(folder / 'library.json', state, MAX_CATALOG, expected_parent=pin)
            return {'state': 'SOURCE_CONFIGURED', 'strict': state.get('strict', False),
                    'revision': state['revision'], 'connection_id': args['connection_id']}

    @staticmethod
    def research_read(folder, identifier):
        previous = read_optional(folder / f'{identifier}.json', MAX_RESEARCH) if folder is not None else None
        if previous is not None:
            require(type(previous) is dict and type(previous.get('format')) is int and previous['format'] == FORMAT,
                    'SOURCE_FORMAT_UNSUPPORTED')
            require(previous.get('id') == identifier and type(previous.get('revision')) is int,
                    'SOURCE_STORAGE_INVALID')
        return previous

    def record(self, project, args, scope, *, catalog_connection=None):
        request_sha = digest(args)
        identifier = args['research_id']
        history = self.folder(project, ('Research',), scope=scope)
        existing = self.research_read(history, identifier)
        if existing and existing['request_sha256'] == request_sha:
            return {'state': 'SOURCE_RESEARCH_SAVED', 'research': existing}
        connection = args.get('connection_id')
        account = args.get('account')
        if connection:
            require(account is None or account == {'platform': 'wechat_official_account', 'connection_id': connection},
                    'SOURCE_RESEARCH_ACCOUNT_CONFLICT')
            account = {'platform': 'wechat_official_account', 'connection_id': connection}
        if catalog_connection:
            connection = catalog_connection
            catalog_scope = ('WeChat', sha256(connection.encode()).hexdigest())
        else:
            catalog_scope = scope
        catalog = self.catalog(self.folder(project, scope=catalog_scope))
        sources = catalog['sources']
        links = []
        seen = set()
        for raw in args['references']:
            normalized = public_url(raw['url'])
            require(normalized not in seen, 'SOURCE_RESEARCH_DUPLICATE_ARTICLE')
            seen.add(normalized)
            reference = {'url': raw['url'].strip(), 'title': raw.get('title', '').strip()}
            identifier_for_source = raw.get('source_id')
            if catalog.get('strict', False):
                require(identifier_for_source is not None, 'SOURCE_RESEARCH_SOURCE_REQUIRED')
            if identifier_for_source is not None:
                source = sources.get(identifier_for_source)
                require(source is not None, 'SOURCE_NOT_IN_ACCOUNT' if connection else 'SOURCE_NOT_FOUND')
                entrance = valid_entry(identifier_for_source, source, connection)['url']
                if catalog.get('strict', False):
                    article_host, entrance_host = urlsplit(normalized).hostname, urlsplit(entrance).hostname
                    require(article_host == entrance_host or article_host.endswith('.' + entrance_host),
                            'SOURCE_RESEARCH_URL_MISMATCH')
                    require(urlsplit(normalized)._replace(fragment='') != urlsplit(entrance)._replace(fragment=''),
                            'SOURCE_RESEARCH_NEEDS_ARTICLE_URL')
                    require(source.get('review') != 'rejected', 'SOURCE_RESEARCH_SOURCE_REJECTED')
                reference.update(source_id=identifier_for_source, entrance_url=entrance)
            links.append(reference)
        folder = self.folder(project, ('Research',), scope=scope, create=True)
        with locked(folder / f'{identifier}.lock'):
            pin = path_check(folder, True)
            previous = self.research_read(folder, identifier)
            if previous and previous['request_sha256'] == request_sha:
                return {'state': 'SOURCE_RESEARCH_SAVED', 'research': previous}
            if previous:
                require(previous.get('account') == account, 'SOURCE_RESEARCH_ACCOUNT_CONFLICT')
            revision = previous['revision'] if previous else 0
            require(revision == args['expected_revision'], 'SOURCE_RESEARCH_STALE_REVISION')
            row = dict(format=FORMAT, id=identifier, revision=revision + 1, title=args['title'].strip(),
                       references=links, request_sha256=request_sha)
            if account is not None:
                row['account'] = account
            atomic_write(folder / f'{identifier}.json', row, MAX_RESEARCH, expected_parent=pin)
            return {'state': 'SOURCE_RESEARCH_SAVED', 'research': row}

    def run(self, args):
        if isinstance(args, dict) and args.get('action') == 'edit' and not args.get('name'):
            raise WCEError('SOURCE_NAME_REQUIRED')
        strict_validate(args, SPEC)
        project, command = args['project_id'], args['action']
        connection = args.get('connection_id')
        if command == 'record_research' and not connection:
            # Older writers supplied the publication account without a catalog selector.
            # Honor strict policy when enabled for that bound account without moving old research.
            account = args.get('account', {})
            legacy_connection = account.get('connection_id')
            if account.get('platform') == 'wechat_official_account' and legacy_connection:
                candidate = ('WeChat', sha256(legacy_connection.encode()).hexdigest())
                if self.catalog(self.folder(project, scope=candidate)).get('strict', False):
                    self.scope(legacy_connection)
                    return self.record(project, args, (), catalog_connection=legacy_connection)
        scope = self.scope(connection)
        if command in ('start_scan', 'check_scan', 'read_scan'):
            return SourceScan(self).run(args, scope)
        if command == 'add':
            return self.add(args, scope)
        if command == 'edit':
            return self.edit(args, scope)
        if command == 'configure':
            return self.configure(args, scope)
        if command == 'record_research':
            return self.record(project, args, scope)
        if command == 'read_research':
            row = self.research_read(self.folder(project, ('Research',), scope=scope), args['research_id'])
            require(row is not None, 'SOURCE_RESEARCH_NOT_FOUND')
            return {'state': 'SOURCE_RESEARCH', 'research': row}
        state = self.catalog(self.folder(project, scope=scope))
        revision = state['revision']
        if args.get('known_revision') == revision:
            return {'state': 'SOURCES_UNCHANGED', 'revision': revision}
        sources = sorted((valid_entry(identifier, row, connection) for identifier, row in state['sources'].items()),
                         key=lambda row: (row['name'].casefold(), row['url']))
        result = {'state': 'SOURCES', 'revision': revision, 'sources': sources}
        if connection:
            result.update(connection_id=connection, strict=state.get('strict', False), storage='/'.join(FOLDER + scope))
        return result
