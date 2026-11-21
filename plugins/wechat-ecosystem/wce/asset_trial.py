"""Create an account-free example through the normal project and director stores."""
from hashlib import sha256
import json
import os
from pathlib import Path
from secrets import token_hex

from .bounded_file import FileSource, identity
from .contracts import WCEError
from .own_bootstrap_security import path_check
from .own_connection_policy import atomic_write, locked
from .own_connection_registry import mkdir
from .project_context import exact_path
from .service import digest
from .video_director import require
from .video_director_media import rename_image, validate_revision

BUNDLE = Path(__file__).resolve().parent.parent / 'assets' / 'asset-trial'
TRIAL = 'jiusera-asset-trial-v1'
TITLE = 'Jiusera 资产锁版试用'
STATE = '.jiusera-trial.json'
ID = ('project_id', 'work_id', 'scene_id', 'shot_id', 'revision_id')
SCENES = ('wide', 'close')
IMAGE_IDS = ('trial-shift-v1', 'trial-shift-v2')
VOICE_IDS = ('trial-voice-v1', 'trial-voice-v2')


def operation(name):
    return digest([TRIAL, name])[:32]


def make_directory(parent, name):
    folder = parent / name
    if not os.path.lexists(folder):
        try:
            mkdir(parent, name)
        except FileExistsError:
            pass
    path_check(folder, True)
    return folder


def local_digest(root, path):
    return sha256(b''.join(FileSource(root).iter_html(path))).hexdigest()


def copy_member(root, relative, data):
    path = Path(relative)
    require(not path.is_absolute() and not any(part in {'.', '..'} for part in path.parts),
            'DIRECTOR_TRIAL_INVALID')
    parent = root
    for name in path.parts[:-1]:
        parent = make_directory(parent, name)
    if not os.path.lexists(root / path):
        directory = os.open(parent, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
        try:
            require(path_check(parent, True) == identity(os.fstat(directory)), 'DIRECTOR_TRIAL_INVALID')
            name = '.trial-' + token_hex(16)
            fd = os.open(name, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600, dir_fd=directory)
            try:
                with os.fdopen(fd, 'wb') as stream:
                    stream.write(data)
                    stream.flush()
                    os.fsync(stream.fileno())
                require(path_check(parent, True) == identity(os.fstat(directory)), 'DIRECTOR_TRIAL_INVALID')
                try:
                    rename_image(directory, name, path.name)
                except FileExistsError:
                    pass
                else:
                    name = None
                os.fsync(directory)
            finally:
                if name is not None:
                    os.unlink(name, dir_fd=directory)
        finally:
            os.close(directory)
    require(local_digest(root, relative) == sha256(data).hexdigest(), 'DIRECTOR_TRIAL_FILE_CHANGED')


def file_ref(manifest, path):
    return {'path': path, 'sha256': manifest['files'][path]}


def state_at(root):
    record = root / STATE
    if not os.path.lexists(record):
        return None
    try:
        file = path_check(record)
        value = json.loads(b''.join(FileSource(root).iter_html(STATE, expected_state=file)))
        require(value.get('trial') == TRIAL, 'DIRECTOR_TRIAL_INVALID')
        return value
    except (OSError, ValueError, AttributeError, WCEError):
        raise WCEError('DIRECTOR_TRIAL_INVALID') from None


def stage_version(manifest, kind, number):
    scene = kind == 'scene'
    asset = 'studio' if scene else 'mic'
    version = f'{asset}-v{number}'
    directory = f"JiuseraAssets/{'Scenes' if scene else 'Objects'}/{version}"
    file = 'studio.blend' if scene else 'microphone.blend'
    image = 'screen-grid.png' if scene else 'grille-mask.png'
    title = '巡线演播室' if scene else '播报话筒'
    return {'version_id': version, 'asset_id': asset, 'kind': kind, 'title': f'{title} v{number}',
            'file': file_ref(manifest, f'{directory}/{file}'),
            'dependencies': [file_ref(manifest, f'{directory}/{image}')]}


def character_manifest(manifest):
    identity = {'id': 'trial-lamp-keeper', 'name': '巡灯人', 'series': 'Jiusera 试用', 'aliases': []}
    inputs = [
        ('trial-normal-v1', '常态 v1', 'normal.png', 'face', False, True),
        (IMAGE_IDS[0], '变身 v1', 'shift-v1.png', 'face', True, True),
        (IMAGE_IDS[1], '变身 v2', 'shift-v2.png', 'face', True, False),
        (VOICE_IDS[0], '人声 v1', 'voice-v1.wav', 'voice', True, True),
        (VOICE_IDS[1], '人声 v2', 'voice-v2.wav', 'voice', True, False),
    ]
    return {'schema': 2, 'assets': [
        {'id': version, 'character': identity, 'label': title, 'use': use,
         'initial_status': 'current' if current else 'candidate', 'source': 'Jiusera 本机试用',
         'description': '', **file_ref(manifest, f'References/{name}'),
         **({'form': {'id': 'shift', 'name': '变身'}} if shifted else {})}
        for version, title, name, use, shifted, current in inputs
    ]}


class AssetTrial:
    def __init__(self, router):
        self.router = router
        self.director = router.director
        self.projects = self.director.projects
        self.parent = self.projects.root / 'examples'
        self.path = self.parent / TITLE

    def state(self):
        exact_path(str(self.path))
        if not os.path.lexists(self.path):
            return {'state': 'NOT_CREATED'}
        path_check(self.path, True)
        record = state_at(self.path)
        if record is None or 'shots' not in record:
            return {'state': 'NOT_CREATED'}
        return self.project_state(record)

    def project_state(self, record):
        project_id = record['project_id']
        require(self.director.project(project_id)[0] == self.path, 'DIRECTOR_TRIAL_INVALID')
        catalog = self.router.stage.catalog(project_id)
        index = self.router.characters.index(project_id)
        asset = index['assets'][IMAGE_IDS[0]]
        from .character_library import primary_slot, slot

        active = {'image': index.get('primary', {}).get(primary_slot(asset)),
                  'image_current': index['current'].get(slot(asset)),
                  'voice': index['current'].get(slot(index['assets'][VOICE_IDS[0]])),
                  'scene': catalog['current'].get('scene/studio'),
                  'object': catalog['current'].get('object/mic')}
        version = next((n for n in (1, 2) if active == {
            'image': IMAGE_IDS[n - 1], 'image_current': IMAGE_IDS[n - 1],
            'voice': VOICE_IDS[n - 1], 'scene': f'studio-v{n}', 'object': f'mic-v{n}',
        }), None)
        return {'state': 'READY', 'shots': record['shots'], 'project_name': TITLE, 'default_version': version}

    def prepare(self):
        exact_path(str(self.path))
        root = self.projects.root
        if not os.path.lexists(root):
            try:
                os.mkdir(root, 0o700)
            except FileExistsError:
                pass
        path_check(root, True)
        make_directory(root, self.parent.name)

    def create(self):
        self.prepare()
        with locked(self.parent / f'{TRIAL}.lock'):
            root = make_directory(self.parent, self.path.name)
            record = state_at(root)
            if record is not None and 'shots' in record:
                return self.project_state(record)
            if record is None:
                require(not any(root.iterdir()), 'DIRECTOR_TRIAL_LOCATION_OCCUPIED')
                atomic_write(root / STATE, {'trial': TRIAL}, expected_parent=path_check(root, True))
            manifest = json.loads((BUNDLE / 'manifest.json').read_bytes())
            require(manifest['schema'] == 1, 'DIRECTOR_TRIAL_INVALID')
            for relative, checksum in manifest['files'].items():
                data = b''.join(FileSource(BUNDLE).iter_html(relative))
                require(sha256(data).hexdigest() == checksum, 'DIRECTOR_TRIAL_INVALID')
                copy_member(root, relative, data)
            catalog = self.projects.view()
            existing = next((row for row in catalog['projects'] if row['root'] == str(root)), None)
            if existing:
                project_id = existing['id']
            else:
                project_id = self.projects.sync(str(root), [], 'project-' + operation('project'),
                                                catalog['revision'])['project_id']
            self.create_assets(project_id, manifest)
            shots = self.create_shots(project_id, manifest)
            state = {'trial': TRIAL, 'project_id': project_id, 'shots': shots}
            atomic_write(root / STATE, state, expected_parent=path_check(root, True))
            return self.project_state(state)

    def create_assets(self, project_id, manifest):
        source = 'References/character-index.json'
        data = json.dumps(character_manifest(manifest), ensure_ascii=False).encode()
        copy_member(self.path, source, data)
        characters = self.router.characters
        spec = {'path': source, 'sha256': sha256(data).hexdigest()}
        plan = characters.preview(project_id, spec)
        characters.edit({'action': 'character_import', 'project_id': project_id, 'source': spec,
                         'expected_revision': plan['revision']})
        for version in ('trial-normal-v1', IMAGE_IDS[0]):
            from .character_library import primary_slot

            index = characters.index(project_id)
            slot = primary_slot(index['assets'][version])
            previous = index.get('primary', {}).get(slot)
            if previous is None:
                characters.edit({'action': 'character_set_primary', 'project_id': project_id, 'version_id': version})
        for number in (1, 2):
            for kind in ('scene', 'object'):
                version = stage_version(manifest, kind, number)
                self.router.stage.edit({'action': 'stage_register', 'project_id': project_id, 'version': version})
                if number == 1:
                    self.select_stage(project_id, kind, version['version_id'], only_missing=True)

    def director_edit(self, project_id, action, key, **args):
        def validate(*values):
            return validate_revision(self.router.jobs, *values)

        return self.director.edit({'action': action, 'project_id': project_id,
                                  'operation_id': operation(key), **args}, validate, jobs=self.router.jobs)

    def create_shots(self, project_id, manifest):
        from .character_library import descriptor

        assets = self.router.characters.index(project_id)['assets']
        image = {'asset_version': IMAGE_IDS[0], 'file': descriptor(assets[IMAGE_IDS[0]], project_id)}
        voice = {'asset_version': VOICE_IDS[0], 'file': descriptor(assets[VOICE_IDS[0]], project_id)}
        fields = {'images': [image | {'role': 'composition'}], 'voice': voice}
        poses = manifest['poses']
        labels = {'character': '巡灯人 · 变身图声', 'wide': '演播室 · 广角', 'close': '演播室 · 近景'}
        result = []
        for name in ('character', *SCENES):
            title = labels[name]
            rows = fields if name == 'character' else {'stage': poses[name] | {
                'scene_version_id': 'studio-v1', 'object_version_id': 'mic-v1',
                'preview': file_ref(manifest, f"JiuseraAssets/Scenes/Previews/studio-{name}.png")}}
            work = self.director_edit(project_id, 'create_work', 'work-' + name, fields={'title': title})
            scope = {'work_id': work['work_id']}
            scene = self.director_edit(project_id, 'create_scene', 'scene-' + name, **scope,
                                       title=title, start_ms=0, end_ms=8000)
            scope['scene_id'] = scene['scene_id']
            shot = self.director_edit(project_id, 'create_shot', 'shot-' + name, **scope, title=title)
            scope['shot_id'] = shot['shot_id']
            revised = self.director_edit(project_id, 'revise', 'revise-' + name, **scope,
                                         base_revision=shot['revision_id'], fields=rows)
            result.append({'id': name, 'title': title, 'tab': 'images' if name == 'character' else 'stage',
                           'scope': {key: revised[key] for key in ID}})
        return result

    def select_stage(self, project_id, kind, version_id, *, only_missing=False):
        catalog = self.router.stage.catalog(project_id)
        key = kind + ('/studio' if kind == 'scene' else '/mic')
        previous = catalog['current'].get(key)
        if (not only_missing or previous is None) and previous != version_id:
            fields = {'expected_current': previous} if previous is not None else {}
            self.router.stage.edit({'action': 'stage_set_current', 'project_id': project_id,
                                    'version_id': version_id, **fields})

    def switch(self, number):
        from .character_library import primary_slot, slot

        self.prepare()
        with locked(self.parent / f'{TRIAL}.lock'):
            record = state_at(self.path)
            require(record and 'shots' in record, 'DIRECTOR_TRIAL_NOT_CREATED')
            self.project_state(record)
            project = record['project_id']
            characters = self.router.characters
            index = characters.index(project)
            image, voice = IMAGE_IDS[number - 1], VOICE_IDS[number - 1]
            pointers = (
                ('character_set_primary', 'expected_primary', image,
                 index.get('primary', {}).get(primary_slot(index['assets'][image]))),
                ('character_set_current', 'expected_current', image,
                 index['current'].get(slot(index['assets'][image]))),
                ('character_set_current', 'expected_current', voice,
                 index['current'].get(slot(index['assets'][voice]))),
            )
            for action, field, current, previous in pointers:
                if current != previous:
                    expect = {field: previous} if previous is not None else {}
                    characters.edit({'action': action, 'project_id': project, 'version_id': current, **expect})
            self.select_stage(project, 'scene', f'studio-v{number}')
            self.select_stage(project, 'object', f'mic-v{number}')
            return self.project_state(record)
