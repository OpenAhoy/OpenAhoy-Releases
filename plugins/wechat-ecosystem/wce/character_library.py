"""Project-owned character references shared by the library and storyboard editor."""

from base64 import b64encode
from functools import lru_cache
from hashlib import sha256
import json
import os
from pathlib import Path
import tempfile

from .bounded_file import FileSource, file_state
from .contracts import WCEError
from .prepared_contracts import strict_validate
from .own_bootstrap_security import path_check
from .own_connection_policy import atomic_write, locked
from .project_context import text as project_text
from .video_director import require
from .video_director_media import IMAGE_CHUNK, local_file, preview_image, source_image


INDEX = 'character-library.json'
ID = {'type': 'string', 'pattern': '^[a-z0-9][a-z0-9._-]{0,79}$', 'maxLength': 80}
DIGEST = {'type': 'string', 'pattern': '^[a-f0-9]{64}$', 'maxLength': 64}
PATH = {'type': 'string', 'minLength': 1, 'maxLength': 4096}
USE = {'type': 'string', 'enum': ['full_body', 'face', 'expression', 'pose']}
STATUS = {'type': 'string', 'enum': ['candidate', 'current', 'historical']}
NAME = {'type': 'string', 'minLength': 1, 'maxLength': 160, 'x-wce-maxUtf8Bytes': 640}
NOTE = {'type': 'string', 'maxLength': 1000, 'x-wce-maxUtf8Bytes': 4000}


def object_schema(properties):
    return {'type': 'object', 'properties': properties, 'required': list(properties),
            'additionalProperties': False}


ENTRY = object_schema({
    'id': ID, 'character': object_schema({
        'id': ID, 'name': NAME, 'series': NAME,
        'aliases': {'type': 'array', 'items': NAME, 'maxItems': 24},
    }),
    'use': USE, 'initial_status': STATUS, 'label': NAME, 'description': NOTE,
    'source': NOTE, 'path': PATH, 'sha256': DIGEST,
})
MANIFEST = object_schema({
    'schema': {'type': 'integer', 'const': 1},
    'assets': {'type': 'array', 'items': ENTRY, 'minItems': 1},
})
SELECTOR = {'version_id': ID}
SOURCE = object_schema({'path': PATH, 'sha256': DIGEST})


def descriptor(record, project_id):
    return {'project_id': project_id, 'path': record['path'], 'sha256': record['sha256']}


def slot(record):
    return record['character']['id'] + '/' + record['use']


def status_of(index, row):
    if index['current'].get(slot(row)) == row['id']:
        return 'current'
    return 'historical' if row.get('was_current') else row['initial_status']


def validate_labels(row):
    for label in (row['character']['name'], row['character']['series'], *row['character']['aliases'],
                  row['label'], row['description'], row['source']):
        project_text(label)


def read_index(project_id, directory):
    path = directory / INDEX
    if not os.path.lexists(path):
        return {'schema': 1, 'project_id': project_id, 'revision': 0,
                'assets': {}, 'current': {}}
    try:
        pin = path_check(path)
        data = json.loads(b''.join(FileSource(directory).iter_html(INDEX, expected_state=pin)))
        require(type(data) is dict and set(data) == {'schema', 'project_id', 'revision', 'assets', 'current'}
                and data['schema'] == 1 and data['project_id'] == project_id
                and type(data['revision']) is int and data['revision'] >= 0
                and all(type(data[key]) is dict for key in ('assets', 'current')),
                'DIRECTOR_CHARACTER_INDEX_UNAVAILABLE')
        for version_id, row in data['assets'].items():
            fields = {key: value for key, value in row.items() if key != 'was_current'}
            strict_validate(fields, ENTRY)
            validate_labels(row)
            require(version_id == row['id'] and type(row.get('was_current', False)) is bool,
                    'DIRECTOR_CHARACTER_INDEX_UNAVAILABLE')
        for key, target in data['current'].items():
            require(target in data['assets'] and slot(data['assets'][target]) == key,
                    'DIRECTOR_CHARACTER_INDEX_UNAVAILABLE')
        return data
    except (OSError, ValueError, TypeError, AttributeError, WCEError):
        raise WCEError('DIRECTOR_CHARACTER_INDEX_UNAVAILABLE') from None


def verify_reference(directory, project_id, row):
    version = row.get('asset_version')
    if version is None:
        return
    record = read_index(project_id, directory)['assets'].get(version)
    require(record and descriptor(record, project_id) == row['file'], 'DIRECTOR_CHARACTER_REFERENCE_MISMATCH')


def file_pin(root, spec):
    path = local_file(root, spec)
    pin = file_state(path.lstat())
    # Zero-byte read still checks root, every directory, owner and the opened file.
    list(FileSource(root).iter_html(path.relative_to(root).as_posix(), expected_state=pin, length=0))
    return pin


@lru_cache(maxsize=96)
def thumbnail(root, relative, checksum, pin):
    result = preview_image(root, {'path': relative, 'sha256': checksum}, True)
    require(file_pin(root, {'path': relative, 'sha256': checksum}) == pin, 'DIRECTOR_ASSET_CHANGED')
    return result


@lru_cache(maxsize=1)
def original(root, relative, checksum, pin):
    with tempfile.TemporaryDirectory(prefix='openahoy-character-') as folder:
        spec = {'path': relative, 'sha256': checksum}
        result = source_image(root, spec, Path(folder))
        require(file_pin(root, spec) == pin, 'DIRECTOR_ASSET_CHANGED')
        return result


def safe_availability(root, spec):
    try:
        pin = file_pin(root, spec)
        thumbnail(root, spec['path'], spec['sha256'], pin)
        return 'available'
    except FileNotFoundError:
        return 'missing'
    except (WCEError, OSError):
        return 'unavailable'


class CharacterLibrary:
    def __init__(self, director):
        self.director = director

    def index(self, project_id):
        root, pin = self.director.project(project_id)
        directory = self.director.storage(root, pin)
        return read_index(project_id, directory)

    def list(self):
        projects = []
        for project in self.director.registered():
            try:
                index = self.index(project['id'])
                rows = []
                for row in index['assets'].values():
                    current = index['current'].get(slot(row))
                    rows.append({key: row[key] for key in ('id', 'character', 'use', 'label', 'description', 'source')}
                                | {'status': status_of(index, row), 'current': current,
                                   'file': descriptor(row, project['id'])})
                projects.append(project | {'revision': index['revision'], 'assets': rows})
            except (WCEError, OSError):
                projects.append(project | {'unavailable': True, 'assets': []})
        return {'projects': projects}

    def manifest(self, root, request):
        spec = {'path': request['path'], 'sha256': request['sha256']}
        path = local_file(root, spec)
        try:
            raw = FileSource(root).read_html(path.relative_to(root).as_posix())
            require(sha256(raw).hexdigest() == spec['sha256'], 'DIRECTOR_CHARACTER_MANIFEST_CHANGED')
            plan = json.loads(raw)
            strict_validate(plan, MANIFEST)
        except (UnicodeError, ValueError, TypeError):
            raise WCEError('DIRECTOR_CHARACTER_MANIFEST_INVALID') from None
        require(len({row['id'] for row in plan['assets']}) == len(plan['assets']),
                'DIRECTOR_CHARACTER_DUPLICATE')
        for row in plan['assets']:
            local_file(root, row)
            validate_labels(row)
        return plan['assets']

    def preview(self, project_id, source):
        root, _ = self.director.project(project_id)
        index = self.index(project_id)
        records = self.manifest(root, source)
        slots = set(index['current'])
        results = []
        for row in records:
            existing = index['assets'].get(row['id'])
            entry = 'new'
            if existing:
                entry = 'existing' if self.same_record(existing, row) else 'conflict'
            elif row['initial_status'] == 'current':
                key = slot(row)
                if key in slots:
                    entry = 'conflict'
                slots.add(key)
            results.append({'id': row['id'], 'name': row['character']['name'],
                            'status': status_of(index, existing) if existing else row['initial_status'],
                            'availability': safe_availability(root, row), 'entry': entry})
        return {'revision': index['revision'], 'assets': results}

    @staticmethod
    def same_record(existing, record):
        return {key: existing[key] for key in ENTRY['properties']} == record

    def edit(self, args):
        project_id = args['project_id']
        root, pin = self.director.project(project_id)
        importing = args['action'] == 'character_import'
        directory = self.director.storage(root, pin, create=importing)
        require(directory.is_dir(), 'DIRECTOR_CHARACTER_INDEX_UNAVAILABLE')
        directory_pin = path_check(directory, True)
        with locked(directory / 'writer.lock'):
            index = read_index(project_id, directory)
            if importing:
                receipt, changed = self.import_assets(root, index, args)
            else:
                receipt, changed = self.set_current(root, index, args)
            if changed:
                require(self.director.project(project_id) == (root, pin), 'DIRECTOR_PROJECT_CHANGED')
                index['revision'] += 1
                receipt['revision'] = index['revision']
                size = len(json.dumps(index, ensure_ascii=False).encode('utf-8')) + 1024
                atomic_write(directory / INDEX, index, maximum=size, expected_parent=directory_pin)
            return receipt

    def import_assets(self, root, index, args):
        records = self.manifest(root, args['source'])
        new = [row for row in records if row['id'] not in index['assets']]
        require(all(self.same_record(index['assets'][row['id']], row)
                    for row in records if row['id'] in index['assets']), 'DIRECTOR_CHARACTER_VERSION_CONFLICT')
        if not new:
            return {'state': 'UNCHANGED', 'revision': index['revision'], 'added': 0}, False
        require(index['revision'] == args['expected_revision'], 'DIRECTOR_CHARACTER_STALE_INDEX')
        for row in new:
            version_id = row['id']
            # Pending or historical references may keep a missing original. An initial
            # current pointer requires exact available bytes, like a later change.
            if row['initial_status'] == 'current':
                key = slot(row)
                require(key not in index['current'], 'DIRECTOR_CHARACTER_CURRENT_CONFLICT')
                require(safe_availability(root, row) == 'available', 'DIRECTOR_CHARACTER_ORIGINAL_UNAVAILABLE')
                index['current'][key] = version_id
            index['assets'][version_id] = row
        return {'state': 'SAVED', 'revision': index['revision'], 'added': len(new)}, True

    @staticmethod
    def set_current(root, index, args):
        version_id = args['version_id']
        row = index['assets'].get(version_id)
        require(row, 'DIRECTOR_CHARACTER_VERSION_NOT_FOUND')
        key = slot(row)
        previous = index['current'].get(key)
        require(previous == args.get('expected_current'), 'DIRECTOR_CHARACTER_CURRENT_CONFLICT')
        require(safe_availability(root, row) == 'available', 'DIRECTOR_CHARACTER_ORIGINAL_UNAVAILABLE')
        if previous != version_id:
            if previous is not None:
                index['assets'][previous]['was_current'] = True
            index['current'][key] = version_id
        return {'state': 'SAVED' if previous != version_id else 'UNCHANGED',
                'revision': index['revision'], 'current': version_id}, previous != version_id

    def media(self, args):
        project_id = args['project_id']
        root, project_pin = self.director.project(project_id)
        directory = self.director.storage(root, project_pin)
        row = read_index(project_id, directory)['assets'].get(args['version_id'])
        require(row, 'DIRECTOR_CHARACTER_VERSION_NOT_FOUND')
        spec = descriptor(row, project_id)
        require(spec['sha256'] == args['sha256'], 'DIRECTOR_CHARACTER_REFERENCE_MISMATCH')
        try:
            pin = file_pin(root, spec)
            params = root, spec['path'], spec['sha256'], pin
            if args['action'] == 'character_thumbnail':
                result = thumbnail(*params)
                require(self.director.project(project_id) == (root, project_pin), 'DIRECTOR_PROJECT_CHANGED')
                return result
            mime, data = original(*params)
            require(self.director.project(project_id) == (root, project_pin), 'DIRECTOR_PROJECT_CHANGED')
            offset = args['offset']
            require(0 <= offset < len(data), 'DIRECTOR_CHARACTER_OFFSET_INVALID')
            return {'mime_type': mime, 'sha256': spec['sha256'], 'total': len(data),
                    'offset': offset, 'data': b64encode(data[offset:offset + IMAGE_CHUNK]).decode('ascii')}
        except FileNotFoundError:
            raise WCEError('DIRECTOR_CHARACTER_ORIGINAL_MISSING') from None
        except OSError:
            raise WCEError('DIRECTOR_CHARACTER_ORIGINAL_UNAVAILABLE') from None
