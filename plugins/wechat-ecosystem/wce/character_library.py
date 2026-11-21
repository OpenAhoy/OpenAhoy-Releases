"""Project-owned character references shared by the library and storyboard editor."""

from base64 import b64encode
from functools import lru_cache
from hashlib import sha256
from io import BytesIO
import json
import os
import stat
import subprocess
from pathlib import Path
from secrets import token_hex
import tempfile
import wave

from .bounded_file import FileSource, MAX_SOURCE_HTML_BYTES, file_state, identity
from .contracts import WCEError
from .prepared_contracts import strict_validate
from .own_bootstrap_security import path_check
from .own_connection_policy import atomic_write, locked
from .project_context import text as project_text
from .video_director import require
from .video_jobs import Jobs
from .video_director_media import IMAGE_CHUNK, local_file, preview_image, rename_image, source_image


INDEX = 'character-library.json'
ASSET_ROOT = 'JiuseraAssets'
LEGACY_ASSET_FOLDER = ('Jiusera资产', '形象')
ID = {'type': 'string', 'pattern': '^[a-z0-9][a-z0-9._-]{0,79}$', 'maxLength': 80}
DIGEST = {'type': 'string', 'pattern': '^[a-f0-9]{64}$', 'maxLength': 64}
PATH = {'type': 'string', 'minLength': 1, 'maxLength': 4096}
USE = {'type': 'string', 'enum': ['full_body', 'face', 'expression', 'pose', 'style',
                                  'angle', 'wardrobe', 'accessory', 'voice']}
EXTENDED_USES = {'angle', 'wardrobe', 'accessory', 'voice'}
NORMAL_FORM = {'id': 'normal', 'name': '常态'}
STATUS = {'type': 'string', 'enum': ['candidate', 'current', 'historical']}
NAME = {'type': 'string', 'minLength': 1, 'maxLength': 160, 'x-wce-maxUtf8Bytes': 640}
NOTE = {'type': 'string', 'maxLength': 1000, 'x-wce-maxUtf8Bytes': 4000}


def object_schema(properties, optional=None):
    return {'type': 'object', 'properties': properties | (optional or {}), 'required': list(properties),
            'additionalProperties': False}


FORM = object_schema({'id': ID, 'name': NAME})
CROP = object_schema({'source_version_id': ID} | {
    key: {'type': 'integer', 'minimum': 0 if key in ('x', 'y') else 1}
    for key in ('x', 'y', 'width', 'height')
})
PINNED_CROP = object_schema(CROP['properties'] | {'source_sha256': DIGEST})
REFERENCE = object_schema({'character_id': ID, 'form_id': ID, 'version_id': ID},
                          {'work_id': ID, 'crop': PINNED_CROP})
LAYOUT = {
    'form': FORM, 'category': {'type': 'string', 'enum': ['standard', 'special']},
    'work_id': ID, 'crop': CROP, 'face_visible': {'type': 'boolean'},
}


ENTRY = object_schema({
    'id': ID, 'character': object_schema({
        'id': ID, 'name': NAME, 'series': NAME,
        'aliases': {'type': 'array', 'items': NAME, 'maxItems': 24},
    }),
    'use': USE, 'initial_status': STATUS, 'label': NAME, 'description': NOTE,
    'source': NOTE, 'path': PATH, 'sha256': DIGEST,
}, LAYOUT)
ORIGIN = object_schema({'project_id': ID, 'version_id': ID, 'sha256': DIGEST})
SELECTOR = {'version_id': ID}
SOURCE = object_schema({'path': PATH, 'sha256': DIGEST})


def manifest_error(field, position=None, code='DIRECTOR_CHARACTER_MANIFEST_INVALID'):
    error = WCEError(code)
    error.manifest_field = field
    error.manifest_position = position
    raise error


def invalid_field(value, schema, path):
    """Find the first failed field using the same schema as persisted rows."""
    try:
        strict_validate(value, schema)
    except WCEError:
        if schema['type'] == 'object' and type(value) is dict:
            for key, field in schema['properties'].items():
                name = f'{path}.{key}' if path else key
                if key not in value:
                    if key in schema['required']:
                        return name
                    continue
                invalid = invalid_field(value[key], field, name)
                if invalid:
                    return invalid
        return path or 'entry'
    return None


def manifest_parts(relative):
    parts = project_text(relative).split('/')
    require(all(part and not part.startswith('.') and '\\' not in part and ':' not in part for part in parts),
            'DIRECTOR_ASSET_OUTSIDE_PROJECT')
    return parts


def imported_id(origin):
    key = '\0'.join((origin['project_id'], origin['version_id'], origin['sha256']))
    return 'imported-' + sha256(key.encode()).hexdigest()


def managed_path(checksum, suffix):
    kind = 'Audio' if suffix == 'wav' else 'Characters'
    return Path(ASSET_ROOT, kind, f'{checksum}.{suffix}')


def save_asset(root, project_pin, target, data, check_project):
    """Publish checked bytes into the same project's content-addressed asset folder."""
    check_project()
    parts = target.parts[:2]
    require(len(target.parts) == 3 and parts[0] == ASSET_ROOT, 'DIRECTOR_ASSET_OUTSIDE_PROJECT')
    folder = Jobs._project_video_folder({'root': str(root)}, list(project_pin), create=True,
                                        components=parts)
    try:
        directory_pin = identity(os.fstat(folder))
        source = FileSource(root)

        def check_folder():
            check_project()
            with source.open_directory(parts) as registered:
                info = os.fstat(registered)
                require(identity(info) == directory_pin and not info.st_mode & 0o022, 'DIRECTOR_PROJECT_CHANGED')

        try:
            info = os.stat(target.name, dir_fd=folder, follow_symlinks=False)
        except FileNotFoundError:
            stage = '.character-' + token_hex(16)
            staged = os.open(stage, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600, dir_fd=folder)
            try:
                with os.fdopen(staged, 'wb') as temporary:
                    temporary.write(data)
                    temporary.flush()
                    os.fsync(temporary.fileno())
                check_folder()
                try:
                    rename_image(folder, stage, target.name)
                except FileExistsError:
                    pass
                else:
                    stage = None
            finally:
                if stage is not None:
                    os.unlink(stage, dir_fd=folder)
            info = os.stat(target.name, dir_fd=folder, follow_symlinks=False)
        require(stat.S_ISREG(info.st_mode) and info.st_nlink == 1 and info.st_size == len(data), 'DIRECTOR_ASSET_CHANGED')
        current = b''.join(source.iter_html(target.as_posix(), expected_state=file_state(info)))
        require(current == data, 'DIRECTOR_ASSET_CHANGED')
        check_folder()
        os.fsync(folder)
    finally:
        os.close(folder)


@lru_cache(maxsize=2)
def voice_original(root, relative, checksum, pin):
    raw = b''.join(FileSource(root).iter_html(relative, expected_state=pin))
    require(sha256(raw).hexdigest() == checksum, 'DIRECTOR_ASSET_CHANGED')
    try:
        with wave.open(BytesIO(raw)) as stream:
            frames = stream.getnframes()
            size = frames * stream.getnchannels() * stream.getsampwidth()
            require(0 < frames and 0 < size <= len(raw) and stream.getframerate() > 0
                    and len(stream.readframes(frames)) == size, 'DIRECTOR_CHARACTER_VOICE_INVALID')
    except (wave.Error, EOFError, ValueError, OverflowError):
        raise WCEError('DIRECTOR_CHARACTER_VOICE_INVALID') from None
    return 'audio/wav', raw


def adopted_bytes(root, record):
    pin = file_pin(root, record)
    reader = voice_original if record['use'] == 'voice' else original
    return reader(root, record['path'], record['sha256'], pin)


def descriptor(record, project_id):
    return {'project_id': project_id, 'path': record['path'], 'sha256': record['sha256']}


def needs_layout(record):
    return bool(record.keys() & LAYOUT.keys() or record['use'] in EXTENDED_USES
                or 'registered_path' in record)


def form_of(record):
    return record.get('form', NORMAL_FORM)


def primary_slot(record):
    return record['character']['id'] + '/' + form_of(record)['id']


def slot(record):
    form = form_of(record)['id']
    parts = [record['character']['id']]
    if 'work_id' in record:
        parts.extend((form, 'work', record['work_id']))
    elif form != NORMAL_FORM['id']:
        parts.append(form)
    return '/'.join((*parts, record['use']))


def main_eligible(record):
    return ('work_id' not in record and record['use'] != 'voice'
            and record.get('face_visible', record['use'] == 'face'))


def version_pin(assets, record):
    value = {'character_id': record['character']['id'], 'form_id': form_of(record)['id'],
             'version_id': record['id']}
    if 'work_id' in record:
        value['work_id'] = record['work_id']
    if crop := record.get('crop'):
        value['crop'] = crop | {'source_sha256': assets[crop['source_version_id']]['sha256']}
    return value


def validate_scope(record):
    form = form_of(record)
    if form['id'] == NORMAL_FORM['id']:
        require(form == NORMAL_FORM, 'DIRECTOR_CHARACTER_FORM_CONFLICT')
    require(('work_id' in record) == (record.get('category', 'standard') == 'special'),
            'DIRECTOR_CHARACTER_WORK_SCOPE_MISMATCH')


def layouts(assets):
    names = {}
    for row in assets.values():
        validate_scope(row)
        form_name = form_of(row)['name']
        require(names.setdefault(primary_slot(row), form_name) == form_name, 'DIRECTOR_CHARACTER_FORM_CONFLICT')
        if crop := row.get('crop'):
            source = assets.get(crop['source_version_id'])
            require(row['use'] != 'voice' and source and source['id'] != row['id']
                    and source['use'] != 'voice' and 'crop' not in source
                    and source['character']['id'] == row['character']['id']
                    and ('work_id' not in source or source['work_id'] == row.get('work_id')),
                    'DIRECTOR_CHARACTER_CROP_INVALID')


def status_of(index, row):
    if index['current'].get(slot(row)) == row['id']:
        return 'current'
    return 'historical' if row.get('was_current') else row['initial_status']


def validate_labels(row):
    for label in (row['character']['name'], row['character']['series'], *row['character']['aliases'],
                  row['label'], row['description'], row['source'], form_of(row)['name']):
        project_text(label)


def read_index(project_id, directory):
    path = directory / INDEX
    if not os.path.lexists(path):
        return {'schema': 1, 'project_id': project_id, 'revision': 0,
                'assets': {}, 'current': {}}
    try:
        pin = path_check(path)
        data = json.loads(b''.join(FileSource(directory).iter_html(INDEX, expected_state=pin)))
        require(type(data) is dict and type(data.get('schema')) is int and data['schema'] in (1, 2),
                'DIRECTOR_CHARACTER_INDEX_UNAVAILABLE')
        extra = {'primary'} if data['schema'] == 2 else set()
        require(set(data) == {'schema', 'project_id', 'revision', 'assets', 'current'} | extra
                and data['project_id'] == project_id and type(data['revision']) is int and data['revision'] >= 0
                and all(type(data[key]) is dict for key in {'assets', 'current'} | extra),
                'DIRECTOR_CHARACTER_INDEX_UNAVAILABLE')
        for version_id, row in data['assets'].items():
            fields = {key: value for key, value in row.items()
                      if key not in {'was_current', 'origin', 'registered_path'}}
            strict_validate(fields, ENTRY)
            if 'registered_path' in row:
                strict_validate(row['registered_path'], PATH)
                suffixes = ('wav',) if row['use'] == 'voice' else ('png', 'jpg')
                managed = {managed_path(row['sha256'], ext).as_posix() for ext in suffixes}
                managed.update(Path(*LEGACY_ASSET_FOLDER, f"{row['sha256']}.{ext}").as_posix() for ext in suffixes)
                require(row['path'] in managed, 'DIRECTOR_CHARACTER_INDEX_UNAVAILABLE')
            require(data['schema'] == 2 or not needs_layout(row), 'DIRECTOR_CHARACTER_INDEX_UNAVAILABLE')
            if 'origin' in row:
                origin = row['origin']
                strict_validate(origin, ORIGIN)
                require(origin['project_id'] != project_id and origin['sha256'] == row['sha256']
                        and imported_id(origin) == version_id, 'DIRECTOR_CHARACTER_INDEX_UNAVAILABLE')
            validate_labels(row)
            require(version_id == row['id'] and type(row.get('was_current', False)) is bool,
                    'DIRECTOR_CHARACTER_INDEX_UNAVAILABLE')
        layouts(data['assets'])
        for key, target in data.get('primary', {}).items():
            row = data['assets'].get(target)
            require(row and primary_slot(row) == key and main_eligible(row), 'DIRECTOR_CHARACTER_INDEX_UNAVAILABLE')
        for key, target in data['current'].items():
            require(target in data['assets'] and slot(data['assets'][target]) == key,
                    'DIRECTOR_CHARACTER_INDEX_UNAVAILABLE')
        return data
    except (OSError, ValueError, TypeError, AttributeError, WCEError):
        raise WCEError('DIRECTOR_CHARACTER_INDEX_UNAVAILABLE') from None


def verify_reference(directory, project_id, row, work_id=None, *, selecting=False, voice=False):
    version = row.get('asset_version')
    if version is None:
        require(not voice and 'character_reference' not in row, 'DIRECTOR_CHARACTER_REFERENCE_MISMATCH')
        return row['file'], None
    assets = read_index(project_id, directory)['assets']
    record = assets.get(version)
    require(record and (record['use'] == 'voice') == voice, 'DIRECTOR_CHARACTER_REFERENCE_MISMATCH')
    file = descriptor(record, project_id)
    prior_path = record.get('registered_path')
    require(file == row['file'] or (selecting and prior_path and row['file'] == file | {'path': prior_path}),
            'DIRECTOR_CHARACTER_REFERENCE_MISMATCH')
    require('work_id' not in record or record['work_id'] == work_id, 'DIRECTOR_CHARACTER_WORK_SCOPE_MISMATCH')
    pinned = version_pin(assets, record)
    require(row.get('character_reference', pinned) == pinned, 'DIRECTOR_CHARACTER_REFERENCE_MISMATCH')
    return file, pinned


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


def validate_crop(root, source, crop):
    try:
        _, raw = original(root, source['path'], source['sha256'], file_pin(root, source))
        with tempfile.NamedTemporaryFile(prefix='character-crop-') as image:
            image.write(raw)
            image.flush()
            result = subprocess.run(['/usr/bin/sips', '-g', 'pixelWidth', '-g', 'pixelHeight', image.name],
                                    capture_output=True, text=True, check=True, timeout=12)
        dimensions = {}
        for line in result.stdout.splitlines():
            key, _, value = line.strip().partition(':')
            if key in ('pixelWidth', 'pixelHeight'):
                dimensions[key] = int(value)
        require(crop['x'] + crop['width'] <= dimensions['pixelWidth']
                and crop['y'] + crop['height'] <= dimensions['pixelHeight'], 'DIRECTOR_CHARACTER_CROP_INVALID')
    except (OSError, ValueError, KeyError, subprocess.SubprocessError, WCEError):
        raise WCEError('DIRECTOR_CHARACTER_CROP_INVALID') from None


def safe_availability(root, spec):
    try:
        pin = file_pin(root, spec)
        reader = voice_original if spec['use'] == 'voice' else thumbnail
        reader(root, spec['path'], spec['sha256'], pin)
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
                root, pin = self.director.project(project['id'])
                directory = self.director.storage(root, pin)
                index = read_index(project['id'], directory)
                works = (self.director.load(project['id'], directory)['works']
                         if any('work_id' in row for row in index['assets'].values()) else {})
                rows = []
                for row in index['assets'].values():
                    current = index['current'].get(slot(row))
                    primary = index.get('primary', {}).get(primary_slot(row))
                    rows.append({key: row[key] for key in ('id', 'character', 'use', 'label', 'description', 'source')}
                                | {key: row[key] for key in ('work_id', 'crop', 'face_visible', 'origin') if key in row}
                                | {'status': status_of(index, row), 'current': current,
                                   'file': descriptor(row, project['id']), 'form': form_of(row),
                                   'category': row.get('category', 'standard'), 'primary': primary == row['id'],
                                   'primary_version_id': primary}
                                | ({'work_title': works.get(row['work_id'], {}).get('title')}
                                   if 'work_id' in row else {}))
                projects.append(project | {'revision': index['revision'], 'assets': rows})
            except (WCEError, OSError):
                projects.append(project | {'unavailable': True, 'assets': []})
        return {'projects': projects}

    def manifest_files(self, project_id, relative):
        root, pin = self.director.project(project_id)
        parts = manifest_parts(relative) if relative else []
        folders, files = [], []
        with FileSource(root).open_directory(parts) as directory, os.scandir(directory) as entries:
            for entry in entries:
                try:
                    manifest_parts(entry.name)
                    info = entry.stat(follow_symlinks=False)
                except (OSError, WCEError):
                    continue
                if info.st_uid != os.getuid():
                    continue
                if stat.S_ISDIR(info.st_mode):
                    folders.append(entry.name)
                elif (entry.name.lower().endswith('.json') and stat.S_ISREG(info.st_mode)
                      and info.st_nlink == 1 and 0 < info.st_size <= MAX_SOURCE_HTML_BYTES):
                    files.append(entry.name)
        require(self.director.project(project_id) == (root, pin), 'DIRECTOR_PROJECT_CHANGED')
        return {'directory': relative, 'folders': sorted(folders), 'files': sorted(files)}

    def pick_manifest(self, project_id, relative):
        manifest_parts(relative)
        require(relative.lower().endswith('.json'), 'DIRECTOR_CHARACTER_MANIFEST_INVALID')
        root, pin = self.director.project(project_id)
        raw = self.manifest_bytes(root, {'path': relative})
        require(self.director.project(project_id) == (root, pin), 'DIRECTOR_PROJECT_CHANGED')
        source = {'path': relative, 'sha256': sha256(raw).hexdigest()}
        return self.preview(project_id, source) | {'source': source}

    @staticmethod
    def manifest_bytes(root, spec):
        path = local_file(root, spec)
        pin = file_pin(root, spec)
        require(0 < pin[2] <= MAX_SOURCE_HTML_BYTES, 'LOCAL_FILE_LIMIT')
        return b''.join(FileSource(root).iter_html(path.relative_to(root).as_posix(), expected_state=pin))

    def manifest(self, root, request):
        raw = self.manifest_bytes(root, request)
        require(sha256(raw).hexdigest() == request['sha256'], 'DIRECTOR_CHARACTER_MANIFEST_CHANGED')
        try:
            plan = json.loads(raw)
        except (UnicodeError, ValueError, RecursionError):
            manifest_error('json')
        if type(plan) is not dict or set(plan) != {'schema', 'assets'}:
            manifest_error('manifest')
        if type(plan['schema']) is not int or plan['schema'] not in (1, 2):
            manifest_error('schema')
        if type(plan['assets']) is not list or not plan['assets']:
            manifest_error('assets')
        seen = set()
        for position, row in enumerate(plan['assets'], 1):
            field = invalid_field(row, ENTRY, '')
            if not field and plan['schema'] == 1 and needs_layout(row):
                field = 'schema'
            if field:
                manifest_error(field, position)
            if row['id'] in seen:
                manifest_error('id', position, 'DIRECTOR_CHARACTER_DUPLICATE')
            seen.add(row['id'])
            try:
                local_file(root, row)
            except WCEError as error:
                manifest_error('path', position, error.code)
            validate_labels(row)
        return plan['assets']

    def preview(self, project_id, source):
        root, pin = self.director.project(project_id)
        directory = self.director.storage(root, pin)
        index = read_index(project_id, directory)
        records = self.manifest(root, source)
        self.check_layout(root, directory, index, records)
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
                            'availability': safe_availability(root, existing or row), 'entry': entry})
        require(self.director.project(project_id) == (root, pin), 'DIRECTOR_PROJECT_CHANGED')
        return {'revision': index['revision'], 'assets': results}

    @staticmethod
    def same_record(existing, record):
        fields = {key: existing[key] for key in ENTRY['properties'] if key in existing}
        fields['path'] = existing.get('registered_path', fields['path'])
        return fields == record

    def edit(self, args):
        project_id = args['project_id']
        root, pin = self.director.project(project_id)
        command = args['action']
        adopting = command == 'character_import_version'
        origin = args['origin'] if adopting else None
        source = self.copy_source(project_id, origin) if adopting else None
        directory = self.director.storage(root, pin, create=adopting or command == 'character_import')
        require(directory.is_dir(), 'DIRECTOR_CHARACTER_INDEX_UNAVAILABLE')
        directory_pin = path_check(directory, True)
        with locked(directory / 'writer.lock'):
            index = read_index(project_id, directory)
            if command == 'character_import':
                receipt, changed = self.import_assets(root, pin, directory, index, args)
            elif command == 'character_set_primary':
                receipt, changed = self.set_primary(root, index, args)
            elif adopting:
                receipt, changed = self.import_version(project_id, root, pin, index, origin, source)
            else:
                receipt, changed = self.set_current(root, index, args)
            if changed:
                require(self.director.project(project_id) == (root, pin), 'DIRECTOR_PROJECT_CHANGED')
                index['revision'] += 1
                receipt['revision'] = index['revision']
                size = len(json.dumps(index, ensure_ascii=False).encode('utf-8')) + 1024
                atomic_write(directory / INDEX, index, maximum=size, expected_parent=directory_pin)
            return receipt

    def copy_source(self, project_id, origin):
        source_id = origin['project_id']
        require(source_id != project_id, 'DIRECTOR_CHARACTER_ALREADY_IN_PROJECT')
        root, pin = self.director.project(source_id)
        index = read_index(source_id, self.director.storage(root, pin))
        record = index['assets'].get(origin['version_id'])
        require(record and record['sha256'] == origin['sha256'], 'DIRECTOR_CHARACTER_REFERENCE_MISMATCH')
        require('work_id' not in record, 'DIRECTOR_CHARACTER_WORK_SCOPE_MISMATCH')
        require('crop' not in record, 'DIRECTOR_CHARACTER_CROP_ORIGINAL_PROJECT_REQUIRED')
        try:
            checked = file_pin(root, record)
            reader = voice_original if record['use'] == 'voice' else original
            mime, data = reader(root, record['path'], record['sha256'], checked)
            require(file_pin(root, record) == checked, 'DIRECTOR_ASSET_CHANGED')
            require(self.director.project(source_id) == (root, pin), 'DIRECTOR_PROJECT_CHANGED')
        except FileNotFoundError:
            raise WCEError('DIRECTOR_CHARACTER_ORIGINAL_MISSING') from None
        except OSError:
            raise WCEError('DIRECTOR_CHARACTER_ORIGINAL_UNAVAILABLE') from None
        return record, mime, data

    def import_version(self, project_id, root, pin, index, origin, source):
        upstream, mime, data = source
        checksum = origin['sha256']
        ext = {'image/png': 'png', 'image/jpeg': 'jpg', 'audio/wav': 'wav'}[mime]
        version_id = imported_id(origin)
        previous = index['assets'].get(version_id)
        target = Path(previous['path']) if previous else managed_path(checksum, ext)
        row = {key: upstream[key] for key in ENTRY['properties'] if key in upstream}
        row.update(id=version_id, path=target.as_posix(), initial_status='candidate', origin=origin)
        require(previous is None or (previous.get('origin') == origin
                and descriptor(previous, project_id) == descriptor(row, project_id)),
                'DIRECTOR_CHARACTER_VERSION_CONFLICT')

        def check_project():
            require(self.director.project(project_id) == (root, pin), 'DIRECTOR_PROJECT_CHANGED')

        if previous is None:
            layouts(index['assets'] | {version_id: row})
        if target.parts[0] == ASSET_ROOT:
            save_asset(root, pin, target, data, check_project)
        else:
            # Re-read the old saved copy at its original path. A historical
            # import must not replace its established file or reference.
            require(adopted_bytes(root, row) == (mime, data), 'DIRECTOR_ASSET_CHANGED')
        if previous is None:
            index['assets'][version_id] = row
            if needs_layout(row):
                self.enable_layout(index)
        return {'state': 'UNCHANGED' if previous else 'IMPORTED', 'revision': index['revision'],
                'version_id': version_id, 'file': descriptor(row, project_id), 'origin': origin}, previous is None

    @staticmethod
    def enable_layout(index):
        index['schema'] = 2
        index.setdefault('primary', {})

    def check_layout(self, root, directory, index, records):
        new = {row['id']: row for row in records if row['id'] not in index['assets']}
        assets = index['assets'] | new
        layouts(assets)
        if any('work_id' in row for row in new.values()):
            works = self.director.load(index['project_id'], directory)['works']
            require(all(row['work_id'] in works for row in new.values() if 'work_id' in row),
                    'DIRECTOR_CHARACTER_WORK_SCOPE_MISMATCH')
        for row in new.values():
            if crop := row.get('crop'):
                validate_crop(root, assets[crop['source_version_id']], crop)

    def import_assets(self, root, pin, directory, index, args):
        project_id = index['project_id']
        records = self.manifest(root, args['source'])
        new = [row for row in records if row['id'] not in index['assets']]
        require(all(self.same_record(index['assets'][row['id']], row)
                    for row in records if row['id'] in index['assets']), 'DIRECTOR_CHARACTER_VERSION_CONFLICT')
        if new:
            require(index['revision'] == args['expected_revision'], 'DIRECTOR_CHARACTER_STALE_INDEX')
            self.check_layout(root, directory, index, new)

        def check_project():
            require(self.director.project(project_id) == (root, pin), 'DIRECTOR_PROJECT_CHANGED')

        for row in records:
            existing = index['assets'].get(row['id'])
            if existing is not None:
                target = Path(existing['path'])
                if 'registered_path' in existing and target.parts[0] == ASSET_ROOT and not os.path.lexists(root / target):
                    # A previously missing candidate can be recovered by reimporting
                    # the same source without changing its version or recorded path.
                    try:
                        _, raw = adopted_bytes(root, row)
                    except (OSError, WCEError):
                        continue
                    save_asset(root, pin, target, raw, check_project)
                continue
            if row['initial_status'] == 'current':
                key = slot(row)
                require(key not in index['current'], 'DIRECTOR_CHARACTER_CURRENT_CONFLICT')
                index['current'][key] = row['id']
            try:
                mime, raw = adopted_bytes(root, row)
            except (OSError, WCEError):
                require(row['initial_status'] != 'current', 'DIRECTOR_CHARACTER_ORIGINAL_UNAVAILABLE')
                raw = None
                suffix = 'wav' if row['use'] == 'voice' else (
                    'png' if Path(row['path']).suffix.lower() == '.png' else 'jpg')
            else:
                suffix = {'image/png': 'png', 'image/jpeg': 'jpg', 'audio/wav': 'wav'}[mime]
            target = managed_path(row['sha256'], suffix)
            if raw is not None:
                save_asset(root, pin, target, raw, check_project)
            index['assets'][row['id']] = row | {'path': target.as_posix(), 'registered_path': row['path']}
        if new:
            self.enable_layout(index)
        return {'state': 'SAVED' if new else 'UNCHANGED', 'revision': index['revision'], 'added': len(new)}, bool(new)

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

    @classmethod
    def set_primary(cls, root, index, args):
        version_id = args['version_id']
        row = index['assets'].get(version_id)
        require(row, 'DIRECTOR_CHARACTER_VERSION_NOT_FOUND')
        require(main_eligible(row), 'DIRECTOR_CHARACTER_FACE_REFERENCE_REQUIRED')
        key = primary_slot(row)
        previous = index.get('primary', {}).get(key)
        require(previous == args.get('expected_primary'), 'DIRECTOR_CHARACTER_CURRENT_CONFLICT')
        require(safe_availability(root, row) == 'available', 'DIRECTOR_CHARACTER_ORIGINAL_UNAVAILABLE')
        if previous != version_id:
            cls.enable_layout(index)
            index['primary'][key] = version_id
        return {'state': 'SAVED' if previous != version_id else 'UNCHANGED',
                'revision': index['revision'], 'primary_version_id': version_id}, previous != version_id

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
                require(row['use'] != 'voice', 'DIRECTOR_CHARACTER_VOICE_NO_THUMBNAIL')
                result = thumbnail(*params)
                require(self.director.project(project_id) == (root, project_pin), 'DIRECTOR_PROJECT_CHANGED')
                return result
            reader = voice_original if row['use'] == 'voice' else original
            mime, data = reader(*params)
            require(self.director.project(project_id) == (root, project_pin), 'DIRECTOR_PROJECT_CHANGED')
            offset = args['offset']
            require(0 <= offset < len(data), 'DIRECTOR_CHARACTER_OFFSET_INVALID')
            return {'mime_type': mime, 'sha256': spec['sha256'], 'total': len(data),
                    'offset': offset, 'data': b64encode(data[offset:offset + IMAGE_CHUNK]).decode('ascii')}
        except FileNotFoundError:
            raise WCEError('DIRECTOR_CHARACTER_ORIGINAL_MISSING') from None
        except OSError:
            raise WCEError('DIRECTOR_CHARACTER_ORIGINAL_UNAVAILABLE') from None
