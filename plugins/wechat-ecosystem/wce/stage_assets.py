"""Immutable local Blender asset versions, pinned per shot with a rendered preview."""
from hashlib import sha256
import json
from pathlib import Path

from .bounded_file import FileSource
from .contracts import WCEError
from .own_bootstrap_security import path_check
from .own_connection_policy import atomic_write, locked
from .prepared_contracts import strict_validate
from .tools import schema
from .video_director import require
from .video_director_media import preview_image
from .character_library import DIGEST, ID, NAME, PATH

INDEX = 'stage-assets.json'
ROOT = 'JiuseraAssets'
FOLDERS = {'scene': 'Scenes', 'object': 'Objects'}
FILE = schema({'path': PATH, 'sha256': DIGEST})
KIND = {'type': 'string', 'enum': list(FOLDERS)}
VERSION = schema({'version_id': ID, 'asset_id': ID, 'kind': KIND, 'title': NAME, 'file': FILE,
                  'dependencies': {'type': 'array', 'items': FILE}})
INTEGER = {'type': 'integer', 'minimum': -(2**53-1), 'maximum': 2**53-1}
VECTOR = {'type': 'array', 'items': INTEGER, 'minItems': 3, 'maxItems': 3}
POSE = {'location_mm': VECTOR, 'rotation_mdeg': VECTOR}
CAMERA = schema(POSE | {'lens_um': INTEGER | {'minimum': 1}})
PLACEMENT = schema(POSE | {'scale_permille': VECTOR | {'items': INTEGER | {'minimum': 1}}})
ASSIGNMENT = schema({'scene_version_id': ID, 'object_version_id': ID, 'camera': CAMERA,
                     'placement': PLACEMENT, 'preview': FILE})


def slot(version):
    return version['kind'] + '/' + version['asset_id']


def read_index(directory, project):
    path = directory / INDEX
    if not path.exists() and not path.is_symlink():
        return {'schema': 1, 'project_id': project, 'versions': {}, 'current': {}}
    try:
        state = path_check(path)
        data = json.loads(b''.join(FileSource(directory).iter_html(INDEX, expected_state=state)))
        require(type(data) is dict and set(data) == {'schema', 'project_id', 'versions', 'current'}
                and data['schema'] == 1 and data['project_id'] == project
                and isinstance(data['versions'], dict) and isinstance(data['current'], dict),
                'DIRECTOR_STAGE_INDEX_INVALID')
        for version_id, version in data['versions'].items():
            strict_validate(version, VERSION)
            require(version_id == version['version_id'], 'DIRECTOR_STAGE_INDEX_INVALID')
        for key, version_id in data['current'].items():
            require(version_id in data['versions'] and slot(data['versions'][version_id]) == key,
                    'DIRECTOR_STAGE_INDEX_INVALID')
        return data
    except (OSError, ValueError, TypeError, WCEError):
        raise WCEError('DIRECTOR_STAGE_INDEX_INVALID') from None


def check_file(root, spec, folder):
    path = spec['path']
    parts = path.split('/')
    require(len(parts) >= 3 and parts[:2] == [ROOT, folder] and '\\' not in path
            and not any(x.startswith('.') or not x for x in parts),
            'DIRECTOR_STAGE_FILE_OUTSIDE_PROJECT')
    digest = sha256()
    for chunk in FileSource(root).iter_html(path):
        digest.update(chunk)
    require(digest.hexdigest() == spec['sha256'], 'DIRECTOR_STAGE_FILE_CHANGED')


def check_version(root, version):
    folder = FOLDERS[version['kind']]
    require(Path(version['file']['path']).suffix == '.blend', 'DIRECTOR_STAGE_BLEND_REQUIRED')
    check_file(root, version['file'], folder)
    seen = {version['file']['path']}
    version_root = Path(version['file']['path']).parent
    for dependency in version['dependencies']:
        require(dependency['path'] not in seen and len(version_root.parts) > 2
                and Path(dependency['path']).is_relative_to(version_root), 'DIRECTOR_STAGE_DEPENDENCY_INVALID')
        seen.add(dependency['path'])
        check_file(root, dependency, folder)


def pin_stage(root, directory, project, request):
    version_rows = read_index(directory, project)['versions']
    picks = {}
    for kind in FOLDERS:
        version = version_rows.get(request[kind + '_version_id'])
        require(version and version['kind'] == kind, 'DIRECTOR_STAGE_VERSION_NOT_FOUND')
        check_version(root, version)
        picks[kind] = version
    check_file(root, request['preview'], 'Scenes')
    # Previews are rendered elsewhere. They must be decodable images with
    # the same project-relative bytes that the revision will keep.
    preview_image(root, request['preview'], True)
    return {**request, **picks}


def preview(root, directory, project, stage):
    expected = {key: stage[key] for key in ASSIGNMENT['properties']}
    require(pin_stage(root, directory, project, expected) == stage, 'DIRECTOR_STAGE_VERSION_CHANGED')
    return preview_image(root, stage['preview'], False)


class StageLibrary:
    def __init__(self, director):
        self.director = director

    def catalog(self, project):
        root, pin = self.director.project(project)
        return read_index(self.director.storage(root, pin), project)

    def edit(self, args):
        project = args['project_id']
        root, pin = self.director.project(project)
        directory = self.director.storage(root, pin, create=True)
        folder_pin = path_check(directory, True)
        with locked(directory / 'writer.lock'):
            index = read_index(directory, project)
            if args['action'] == 'stage_register':
                version = args['version']
                check_version(root, version)
                version_id = version['version_id']
                prior = index['versions'].get(version_id)
                require(prior is None or prior == version, 'DIRECTOR_STAGE_VERSION_CONFLICT')
                if prior:
                    return {'state': 'UNCHANGED', 'version_id': version_id}
                index['versions'][version_id] = version
            else:
                version_id = args['version_id']
                version = index['versions'].get(version_id)
                require(version, 'DIRECTOR_STAGE_VERSION_NOT_FOUND')
                key = slot(version)
                previous = index['current'].get(key)
                require(previous == args.get('expected_current'), 'DIRECTOR_STAGE_CURRENT_CHANGED')
                check_version(root, version)
                if previous == version_id:
                    return {'state': 'UNCHANGED', 'version_id': version_id}
                index['current'][key] = version_id
            require(self.director.project(project) == (root, pin), 'DIRECTOR_PROJECT_CHANGED')
            limit = len(json.dumps(index,ensure_ascii=False).encode()) + 1024
            atomic_write(directory / INDEX, index, maximum=limit, expected_parent=folder_pin)
            return {'state': 'SAVED', 'version_id': version_id}
