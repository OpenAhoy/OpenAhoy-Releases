"""Owner-local project references and preferences, never platform authority.

Source bodies stay in their original files. Only an explicit sync indexes a
project; the plugin's cwd is never used to infer the caller's project.
"""
from copy import deepcopy
from hashlib import sha256
import json
import os
from pathlib import Path
import re
import stat

from .contracts import WCEError
from .own_connection_policy import locked, registry_path, atomic_write
from .own_production_rules import SECRET, CONTROL
from .service import digest

PLATFORMS = ('wechat_official_account', 'x', 'xiaohongshu')
FIELDS = ('topics', 'selection', 'writing', 'reply_style', 'notes')
CHUNK = 8192
ID = re.compile(r'[a-f0-9]{32}')
OP = re.compile(r'project-[a-f0-9]{32}')
SOURCE_SECRET = re.compile(
    r'(?i)(?:(?:client[_ -]?secret|refresh[_ -]?token|id[_ -]?token|session[_ -]?token|'
    r'authorization|cookie|bearer)\s*[\"\']?\s*[:=：]\s*\S+'
    r'|-----BEGIN (?:[A-Z0-9]+ )*PRIVATE KEY-----)')


def require(value, code='PROJECT_INVALID_REQUEST'):
    if not value:
        raise WCEError(code)


def text(value):
    require(type(value) is str and CONTROL.search(value) is None)
    try:
        value.encode('utf-8')
    except UnicodeError:
        raise WCEError('PROJECT_INVALID_UNICODE') from None
    require(SECRET.search(value) is None and SOURCE_SECRET.search(value) is None,
            'PROJECT_SECRET_NOT_ALLOWED')
    return value


def exact_path(value):
    require(type(value) is str and value.startswith('/') and '..' not in Path(value).parts)
    text(value)
    path = Path(value)
    # Do not silently resolve a project alias into a different authority root.
    for item in (path, *path.parents):
        require(not item.is_symlink(), 'PROJECT_SYMLINK_NOT_ALLOWED')
    return path


def read_source(value):
    path = exact_path(value)
    require(path.name in ('AGENTS.md', 'AGENTS.override.md', 'SKILL.md'), 'PROJECT_SOURCE_UNSUPPORTED')
    fd = None
    directory = None
    try:
        directory = os.open('/', os.O_RDONLY | os.O_DIRECTORY)
        for part in path.parts[1:-1]:
            next_directory = os.open(part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=directory)
            os.close(directory)
            directory = next_directory
        fd = os.open(path.name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=directory)
        before = os.fstat(fd)
        require(stat.S_ISREG(before.st_mode) and before.st_uid == os.getuid(), 'PROJECT_SOURCE_UNAVAILABLE')
        with os.fdopen(fd, 'rb') as stream:
            fd = None
            raw = stream.read()
            after = os.fstat(stream.fileno())
        require((before.st_dev, before.st_ino, before.st_size, before.st_mtime_ns) ==
                (after.st_dev, after.st_ino, after.st_size, after.st_mtime_ns), 'PROJECT_SOURCE_CHANGED')
        require(path.stat().st_ino == before.st_ino and not path.is_symlink(), 'PROJECT_SOURCE_CHANGED')
        value = raw.decode('utf-8')
        text(value)
        return value, {'sha256': sha256(raw).hexdigest(), 'utf8_bytes': len(raw),
                       'unicode_length': len(value), 'chunks': max(1, (len(value) + CHUNK - 1) // CHUNK)}
    except (OSError, UnicodeError):
        raise WCEError('PROJECT_SOURCE_UNAVAILABLE') from None
    finally:
        if fd is not None:
            os.close(fd)
        if directory is not None:
            os.close(directory)


def source(path, kind, origin):
    body, manifest = read_source(str(path))
    name = path.parent.name if kind == 'skill' else path.name
    description = ''
    if kind == 'skill' and body.startswith('---\n'):
        for line in body.split('---', 2)[1].splitlines():
            key, sep, value = line.partition(':')
            if sep and key.strip() == 'name':
                name = value.strip().strip('\"\'') or name
            if sep and key.strip() == 'description':
                description = value.strip().strip('\"\'')
    return {'id': digest({'path': str(path), 'kind': kind})[:32], 'kind': kind,
            'origin': origin, 'path': str(path), 'name': name, 'description': description, **manifest}


def builtin():
    root = Path(__file__).resolve().parents[1]
    path = root / 'skills/wechat-ecosystem/SKILL.md'
    if not path.exists():
        path = root / 'integrations/codex/skills/wechat-ecosystem/SKILL.md'
    value = source(path, 'skill', 'plugin')
    value['id'] = 'builtin-openahoy'
    value['name'] = 'OpenAhoy 通用 Skill'
    return value


def catalog(root, extra):
    path = exact_path(root)
    require(path.is_dir() and path != Path('/'), 'PROJECT_ROOT_UNAVAILABLE')
    entries = []
    # Standard inherited instruction chain, not a recursive project/history scan.
    for folder in reversed((path, *path.parents)):
        override, normal = folder / 'AGENTS.override.md', folder / 'AGENTS.md'
        if os.path.lexists(override):
            entries.append(source(override, 'agents', 'project' if folder == path else 'inherited'))
        elif os.path.lexists(normal):
            entries.append(source(normal, 'agents', 'project' if folder == path else 'inherited'))
    for location in ('.agents/skills', '.codex/skills', 'skills'):
        base = path / location
        if not os.path.lexists(base):
            continue
        exact_path(str(base))
        require(base.is_dir(), 'PROJECT_SOURCE_UNAVAILABLE')
        for child in sorted(base.iterdir()):
            candidate = child / 'SKILL.md'
            if os.path.lexists(candidate):
                entries.append(source(candidate, 'skill', 'project'))
    require(type(extra) is list and all(type(p) is str for p in extra))
    entries.extend(source(exact_path(p), 'skill', 'selected') for p in extra)
    require(all(row['path'].endswith('/SKILL.md') for row in entries if row['kind'] == 'skill'))
    return list({row['id']: row for row in entries}.values())


def empty_settings():
    return {'project_id': '', 'skills': [], 'preferences': {name: '' for name in FIELDS}}


class ProjectStore:
    def __init__(self, registry=None, *, owner_resolver=None):
        self.registry = Path(registry) if registry else registry_path()
        self.root = self.registry.parent
        self.path = self.root / 'project-context.json'
        self.lock = self.root / 'project-context.lock'
        self.owner_resolver = owner_resolver

    def owner(self):
        if self.owner_resolver is not None:
            return self.owner_resolver('', self.registry)['owner']
        # This is a local preference namespace, not a WeChat connection grant.
        # X-only/unbound users need no WeChat owner or account to use this page.
        exact_path(str(self.root))
        if self.root.exists():
            from .own_bootstrap_security import path_check
            path_check(self.root, True)
        return digest({'namespace': 'openahoy-project-context-v1', 'uid': os.getuid(), 'root': str(self.root)})

    def _load(self):
        owner = self.owner()
        if not os.path.lexists(self.path):
            return {'schema': 1, 'owner': owner, 'revision': 0, 'projects': {}, 'bindings': {}, 'operations': {}}
        from .own_bootstrap_security import path_check
        pin = path_check(self.path)
        require(self.path.stat().st_nlink == 1, 'PROJECT_STORE_UNAVAILABLE')
        fd = os.open(self.path, os.O_RDONLY | os.O_NOFOLLOW)
        with os.fdopen(fd, 'rb') as stream:
            raw = stream.read()
        require(path_check(self.path) == pin, 'PROJECT_STORE_CHANGED')
        try:
            value = json.loads(raw)
        except (ValueError, UnicodeError):
            raise WCEError('PROJECT_STORE_UNAVAILABLE') from None
        require(type(value) is dict and set(value) == {'schema', 'owner', 'revision', 'projects', 'bindings', 'operations'}
                and value['schema'] == 1 and value['owner'] == owner
                and type(value['revision']) is int and value['revision'] >= 0
                and all(type(value[k]) is dict for k in ('projects', 'bindings', 'operations')), 'PROJECT_STORE_UNAVAILABLE')
        return value

    def _change(self, operation_id, payload, expected, mutate):
        require(type(operation_id) is str and OP.fullmatch(operation_id))
        require(type(expected) is int and expected >= 0)
        self.owner()
        if not os.path.lexists(self.root):
            try:
                os.mkdir(self.root, 0o700)
            except FileExistsError:
                pass
        with locked(self.lock):
            state = self._load()
            fingerprint = digest(payload)
            if operation_id in state['operations']:
                receipt = state['operations'][operation_id]
                require(receipt['fingerprint'] == fingerprint, 'PROJECT_OPERATION_CONFLICT')
                return deepcopy(receipt['result'])
            require(state['revision'] == expected, 'PROJECT_REVISION_CONFLICT')
            result = mutate(state)
            state['revision'] += 1
            result.update(state='SAVED', revision=state['revision'], operation_id=operation_id)
            state['operations'][operation_id] = {'fingerprint': fingerprint, 'result': result}
            require(state['owner'] == self.owner(), 'PROJECT_OWNER_CHANGED')
            raw = json.dumps(state, ensure_ascii=False).encode('utf-8')
            # Existing atomic writer, sized to actual data, not an overall quota.
            atomic_write(self.path, state, maximum=max(16384, len(raw) * 2 + 1024))
            return deepcopy(result)

    def sync(self, project_root, skill_paths, operation_id, expected_revision):
        project_root = str(exact_path(project_root))
        entries = catalog(project_root, skill_paths)
        pid = digest({'root': project_root})[:32]
        project = {'id': pid, 'root': project_root, 'name': Path(project_root).name,
                   'sources': entries, 'extra_skill_paths': skill_paths}
        project['source_digest'] = digest(entries)
        return self._change(operation_id, {'sync': project}, expected_revision,
            lambda state: (state['projects'].update({pid: project}) or {'project_id': pid, 'source_digest': project['source_digest']}))

    def view(self):
        state = self._load()
        return {'revision': state['revision'], 'projects': list(state['projects'].values()), 'builtin': builtin()}

    @staticmethod
    def scope(platform_id, connection_id):
        require(platform_id in PLATFORMS and type(connection_id) is str and len(connection_id) <= 128)
        return json.dumps([platform_id, connection_id], separators=(',', ':'))

    def settings(self, platform_id, connection_id):
        key = self.scope(platform_id, connection_id)
        state = self._load()
        default = state['bindings'].get(self.scope(platform_id, ''), empty_settings())
        own = state['bindings'].get(key)
        return {'revision': state['revision'], 'platform_id': platform_id, 'connection_id': connection_id,
                'overridden': key in state['bindings'], 'settings': deepcopy(own if own is not None else default),
                'inherited_from': 'account' if connection_id and own is not None else 'platform'}

    def save(self, platform_id, connection_id, settings, inherit, operation_id, expected_revision):
        key = self.scope(platform_id, connection_id)
        require(type(inherit) is bool and (connection_id or not inherit))
        require(type(settings) is dict and set(settings) == {'project_id', 'skills', 'preferences'})
        require(type(settings['project_id']) is str and (not settings['project_id'] or ID.fullmatch(settings['project_id'])))
        require(type(settings['skills']) is list and all(type(x) is str and ID.fullmatch(x) for x in settings['skills'])
                and len(set(settings['skills'])) == len(settings['skills']))
        require(type(settings['preferences']) is dict and set(settings['preferences']) == set(FIELDS))
        for value in settings['preferences'].values():
            text(value)
        def mutate(state):
            if inherit:
                state['bindings'].pop(key, None)
            else:
                project = state['projects'].get(settings['project_id'])
                require(not settings['project_id'] or project is not None, 'PROJECT_NOT_FOUND')
                skills = {row['id'] for row in project['sources'] if row['kind'] == 'skill'} if project else set()
                require(set(settings['skills']) <= skills, 'PROJECT_SKILL_NOT_FOUND')
                state['bindings'][key] = deepcopy(settings)
            return {'platform_id': platform_id, 'connection_id': connection_id, 'settings_sha256': digest(settings), 'inherited': inherit}
        return self._change(operation_id, {'scope': key, 'settings': settings, 'inherit': inherit}, expected_revision, mutate)

    def operation(self, operation_id):
        require(type(operation_id) is str and OP.fullmatch(operation_id))
        row = self._load()['operations'].get(operation_id)
        return deepcopy(row['result']) if row else {'state': 'NOT_FOUND', 'operation_id': operation_id}

    def effective(self, platform_id, connection_id):
        value = self.settings(platform_id, connection_id)
        state = self._load()
        require(state['revision'] == value['revision'], 'PROJECT_REVISION_CONFLICT')
        cfg = value['settings']
        project = state['projects'].get(cfg['project_id'])
        selected = set(cfg['skills'])
        by_id = {row['id']: row for row in project['sources']} if project else {}
        rows = ([row for row in project['sources'] if row['kind'] == 'agents'] +
                [by_id[sid] for sid in cfg['skills'] if sid in by_id]) if project else []
        present = {row['id'] for row in rows}
        missing = sorted(selected - present)
        checked = []
        for row in [builtin(), *rows]:
            status = 'CURRENT'
            try:
                _, current = read_source(row['path'])
                if current['sha256'] != row['sha256']:
                    status = 'CHANGED'
            except WCEError as error:
                status = error.code
            checked.append(dict(row, status=status))
        return value | {'state': 'CONFIGURED' if project else 'UNLINKED',
            'project': {k: project[k] for k in ('id', 'name', 'root', 'source_digest')} if project else None,
            'sources': checked, 'missing_skills': missing, 'model': 'FOLLOW_CURRENT_CODEX_TASK',
            'authority': False, 'existing_platform_rules': 'UNCHANGED_READ_SEPARATELY'}

    def chunk(self, project_id, source_id, expected_sha256, index):
        require(type(index) is int and index >= 0)
        if source_id == 'builtin-openahoy':
            row = builtin()
        else:
            project = self._load()['projects'].get(project_id)
            require(project is not None, 'PROJECT_NOT_FOUND')
            row = next((row for row in project['sources'] if row['id'] == source_id), None)
            require(row is not None, 'PROJECT_SOURCE_NOT_FOUND')
        require(row['sha256'] == expected_sha256, 'PROJECT_SOURCE_CHANGED')
        body, manifest = read_source(row['path'])
        require(manifest['sha256'] == expected_sha256, 'PROJECT_SOURCE_CHANGED')
        require(index < manifest['chunks'], 'PROJECT_CHUNK_NOT_FOUND')
        part = body[index * CHUNK:(index + 1) * CHUNK]
        return {'source_id': source_id, 'sha256': expected_sha256, 'index': index,
                'text': part, 'chunk_sha256': sha256(part.encode()).hexdigest(), **manifest}
