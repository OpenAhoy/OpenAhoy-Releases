"""Reusable public source entrances and exact article references, scoped to one project."""
from hashlib import sha256
import ipaddress
import os
import re
from urllib.parse import parse_qsl, urlsplit, urlunsplit

from .contracts import WCEError
from .own_bootstrap_security import path_check
from .own_connection_policy import atomic_write, locked, read_optional
from .prepared_contracts import strict_validate
from .service import digest
from .tools import schema

TOOL = 'own.sources.library'
FOLDER = ('JiuseraAssets', 'Sources')
FORMAT = 1
MAX_CATALOG = 16 * 1024 * 1024
MAX_RESEARCH = 512 * 1024
MAX_REVISION = 2**53 - 1
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
    return schema({'action': {'type': 'string', 'const': name}, 'project_id': ID, **required}, optional)


URL = text(4096, 1)
METADATA = {'name': text(160, 1), 'topic': text(180), 'kind': KIND}
REFERENCE = schema({'url': URL}, {'title': text(500), 'source_id': ID})
ENTRY = schema({'id': ID, 'url': URL, 'origin': ORIGIN, 'revision': REVISION, **METADATA})
CONTEXT = schema({'platform': {'type': 'string', 'enum': ['wechat_official_account', 'x', 'xiaohongshu']},
                  'connection_id': text(128, 1)})
SPEC = {'oneOf': [
    action('list', {}, {'known_revision': CHECKPOINT}),
    action('add', {'url': URL, 'origin': ORIGIN}, METADATA),
    action('edit', {'source_id': ID, 'expected_revision': REVISION, 'name': METADATA['name']},
           {'topic': METADATA['topic'], 'kind': KIND}),
    action('record_research', {'research_id': WORK_ID, 'expected_revision': CHECKPOINT,
                               'title': text(250, 1), 'references': {
                                   'type': 'array', 'minItems': 1, 'maxItems': 50, 'items': REFERENCE}},
           {'account': CONTEXT}),
    action('read_research', {'research_id': WORK_ID}),
]}


def require(condition, code):
    if not condition:
        raise WCEError(code)


def valid_entry(identifier, row):
    try:
        strict_validate(row, ENTRY)
        address = public_url(row['url'])
    except WCEError:
        raise WCEError('SOURCE_STORAGE_INVALID') from None
    require(row['id'] == identifier == sha256(address.encode()).hexdigest()[:32]
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
    def __init__(self, router):
        self.director = router.director
        self.jobs = router.jobs

    def folder(self, project, extra=(), *, create=False):
        root, pin = self.director.project(project)
        parts = FOLDER + extra
        try:
            fd = self.jobs._project_video_folder({'root': str(root)}, list(pin), create=create, components=parts)
        except FileNotFoundError:
            if not create:
                return None
            raise WCEError('SOURCE_STORAGE_UNAVAILABLE') from None
        except OSError:
            raise WCEError('SOURCE_STORAGE_UNAVAILABLE') from None
        os.close(fd)
        return root.joinpath(*parts)

    @staticmethod
    def catalog(folder):
        current = read_optional(folder / 'library.json', MAX_CATALOG) if folder is not None else None
        if current is None:
            return {'format': FORMAT, 'revision': 0, 'sources': {}}
        require(type(current) is dict and type(current.get('format')) is int and current['format'] == FORMAT,
                'SOURCE_FORMAT_UNSUPPORTED')
        require(type(current.get('revision')) is int and 0 <= current['revision'] <= MAX_REVISION
                and type(current.get('sources')) is dict,
                'SOURCE_STORAGE_INVALID')
        return current

    @staticmethod
    def requested_metadata(args):
        return {key: args[key].strip() if key != 'kind' else args[key]
                for key in METADATA if key in args}

    def add(self, args):
        address = public_url(args['url'])
        metadata = self.requested_metadata(args)
        identifier = sha256(address.encode()).hexdigest()[:32]
        folder = self.folder(args['project_id'], create=True)
        with locked(folder / 'library.lock'):
            pin = path_check(folder, True)
            state = self.catalog(folder)
            previous = state['sources'].get(identifier)
            if previous is not None:
                valid_entry(identifier, previous)
                require(previous['url'] == address, 'SOURCE_ID_CONFLICT')
                return {'state': 'SOURCE_EXISTS', 'source': previous, 'revision': state['revision']}
            row = {'id': identifier, 'url': address, 'origin': args['origin'], 'revision': 1,
                   'name': urlsplit(address).hostname, 'topic': '', 'kind': 'website', **metadata}
            state['sources'][identifier] = row
            state['revision'] += 1
            require(state['revision'] <= MAX_REVISION, 'SOURCE_REVISION_LIMIT')
            atomic_write(folder / 'library.json', state, MAX_CATALOG, expected_parent=pin)
            return {'state': 'SOURCE_ADDED', 'source': row, 'revision': state['revision']}

    def edit(self, args):
        folder = self.folder(args['project_id'])
        require(folder is not None, 'SOURCE_NOT_FOUND')
        with locked(folder / 'library.lock'):
            pin = path_check(folder, True)
            state = self.catalog(folder)
            row = state['sources'].get(args['source_id'])
            require(row is not None, 'SOURCE_NOT_FOUND')
            valid_entry(args['source_id'], row)
            metadata = self.requested_metadata(args)
            if all(row[key] == value for key, value in metadata.items()):
                return {'state': 'SOURCE_UNCHANGED', 'source': row, 'revision': state['revision']}
            require(row['revision'] == args['expected_revision'], 'SOURCE_STALE_REVISION')
            row.update(metadata, revision=row['revision'] + 1)
            state['revision'] += 1
            require(state['revision'] <= MAX_REVISION, 'SOURCE_REVISION_LIMIT')
            atomic_write(folder / 'library.json', state, MAX_CATALOG, expected_parent=pin)
            return {'state': 'SOURCE_EDITED', 'source': row, 'revision': state['revision']}

    @staticmethod
    def research_read(folder, identifier):
        previous = read_optional(folder / f'{identifier}.json', MAX_RESEARCH) if folder is not None else None
        if previous is not None:
            require(type(previous) is dict and type(previous.get('format')) is int and previous['format'] == FORMAT,
                    'SOURCE_FORMAT_UNSUPPORTED')
            require(previous.get('id') == identifier and type(previous.get('revision')) is int,
                    'SOURCE_STORAGE_INVALID')
        return previous

    def record(self, project, args):
        request_sha = digest(args)
        identifier = args['research_id']
        sources = self.catalog(self.folder(project))['sources']
        links = []
        seen = set()
        for raw in args['references']:
            normalized = public_url(raw['url'])
            require(normalized not in seen, 'SOURCE_RESEARCH_DUPLICATE_ARTICLE')
            seen.add(normalized)
            reference = {'url': raw['url'].strip(), 'title': raw.get('title', '').strip()}
            source_id = raw.get('source_id')
            if source_id is not None:
                source = sources.get(source_id)
                require(source is not None, 'SOURCE_NOT_FOUND')
                reference.update(source_id=source_id, entrance_url=valid_entry(source_id, source)['url'])
            links.append(reference)
        folder = self.folder(project, ('Research',), create=True)
        with locked(folder / f'{identifier}.lock'):
            pin = path_check(folder, True)
            previous = self.research_read(folder, identifier)
            if previous and previous['request_sha256'] == request_sha:
                return {'state': 'SOURCE_RESEARCH_SAVED', 'research': previous}
            if previous:
                require(previous.get('account') == args.get('account'), 'SOURCE_RESEARCH_ACCOUNT_CONFLICT')
            revision = previous['revision'] if previous else 0
            require(revision == args['expected_revision'], 'SOURCE_RESEARCH_STALE_REVISION')
            row = dict(format=FORMAT, id=identifier, revision=revision + 1, title=args['title'].strip(),
                       references=links, request_sha256=request_sha)
            if 'account' in args:
                row['account'] = args['account']
            atomic_write(folder / f'{identifier}.json', row, MAX_RESEARCH, expected_parent=pin)
            return {'state': 'SOURCE_RESEARCH_SAVED', 'research': row}

    def run(self, args):
        strict_validate(args, SPEC)
        project, command = args['project_id'], args['action']
        if command == 'add':
            return self.add(args)
        if command == 'edit':
            return self.edit(args)
        if command == 'record_research':
            return self.record(project, args)
        if command == 'read_research':
            row = self.research_read(self.folder(project, ('Research',)), args['research_id'])
            require(row is not None, 'SOURCE_RESEARCH_NOT_FOUND')
            return {'state': 'SOURCE_RESEARCH', 'research': row}
        state = self.catalog(self.folder(project))
        revision = state['revision']
        if args.get('known_revision') == revision:
            return {'state': 'SOURCES_UNCHANGED', 'revision': revision}
        sources = sorted((valid_entry(identifier, row) for identifier, row in state['sources'].items()),
                         key=lambda row: (row['name'].casefold(), row['url']))
        return {'state': 'SOURCES', 'revision': revision, 'sources': sources}
