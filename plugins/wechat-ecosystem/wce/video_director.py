"""Project-owned storyboards. Shot revisions are immutable; focus and adoption are pointers."""
from collections import defaultdict
from copy import deepcopy
import json
import os
from pathlib import Path
import secrets
import stat

from .bounded_file import FileSource, identity
from .contracts import WCEError
from .own_bootstrap_security import path_check
from .own_connection_policy import atomic_write, locked
from .project_context import exact_path, text as project_text
from .service import digest

ROOT_NAME = '.openahoy-director'
REVISION_FIELDS = {
    'title': '', 'purpose': '', 'ratio': '', 'start_ms': 0, 'end_ms': 0,
    'subjects': '', 'opening': '', 'action': '', 'ending': '', 'transition': '',
    'composition': '', 'camera': '', 'lens': '', 'focus': '', 'lighting': '',
    'color': '', 'sound': '', 'review': '', 'prompt': '', 'notes': '', 'cards': [],
    'images': [], 'configuration': None, 'whitebox': None, 'result': None,
}
WORK_FIELDS = {'title': '', 'brief': '', 'platform': '', 'audience': '', 'ratio': '16:9',
               'duration_ms': 0, 'tone': '', 'references': '', 'style': '',
               'caption_safe_area': '', 'sound': ''}


def require(condition, code='DIRECTOR_INVALID_REQUEST'):
    if not condition:
        raise WCEError(code)


def tidy_text(value):
    return project_text(value if isinstance(value, str) else '').strip()


def display_name(title):
    require(tidy_text(title), 'DIRECTOR_TITLE_REQUIRED')
    return tidy_text(title)


def lookup(rows, selector, code):
    row = rows.get(selector)
    require(row is not None, code)
    return row


def in_order(rows):
    return sorted(rows.values(), key=lambda row: row['position'])


def current_selection(work):
    if work['focus']:
        return work['focus']
    imaged, first = None, None
    for scene in in_order(work['scenes']):
        for shot in in_order(scene['shots']):
            adopted = shot['adopted_revision']
            head = shot['head_revision']
            scope = {'scene_id': scene['id'], 'shot_id': shot['id']}
            first = first or scope | {'revision_id': adopted or head}
            if adopted and shot['revisions'][adopted]['images']:
                return scope | {'revision_id': adopted}
            if shot['revisions'][head]['images']:
                imaged = imaged or scope | {'revision_id': head}
    return imaged or first


def canvas_state(work):
    return work.get('canvas', {
        'version': 0, 'viewport': {'x': 28, 'y': 28, 'scale': 100}, 'positions': {}, 'nodes': {},
    })


def engine_node_id(work, shot_id):
    return digest(['engine_node', work['id'], shot_id])[:32]

def reference_node_id(work, shot_id):
    return digest(['shot_reference', work['id'], shot_id])[:32]


def primary_reference_index(images):
    return next((index for index, row in enumerate(images) if row['role'] == 'composition'), 0)


def revision_overview(revision):
    result = {key: revision[key] for key in
              ('id', 'number', 'title', 'notes', 'start_ms', 'end_ms', 'origin')}
    if images := revision['images']:
        item = images[primary_reference_index(images)]
        result['reference_sha256'] = item['file']['sha256']
    return result


def canvas_edit(work, args, verify_node):
    canvas = canvas_state(work)
    require(canvas['version'] == args['expected_canvas_version'], 'DIRECTOR_CANVAS_CHANGED')
    operation = args['action']
    shots = {shot_id for scene in work['scenes'].values() for shot_id in scene['shots']}
    if operation == 'canvas_view':
        canvas['viewport'] = args['viewport']
        receipt = {}
    elif operation == 'canvas_add':
        node = args['node']
        require('shot_id' not in node or node['shot_id'] in shots, 'DIRECTOR_SHOT_NOT_FOUND')
        verify_node(node)
        node_id = secrets.token_hex(16)
        canvas['nodes'][node_id] = dict(node, id=node_id, title=display_name(node['title']))
        canvas['positions'][node_id] = args['position']
        receipt = {'node_id': node_id}
    elif operation == 'canvas_note_edit':
        node_id = args['node_id']
        node = lookup(canvas['nodes'], node_id, 'DIRECTOR_CANVAS_NODE_NOT_FOUND')
        require(node['kind'] == 'note', 'DIRECTOR_CANVAS_NODE_NOT_FOUND')
        node.update(title=display_name(args['title']), text=project_text(args['text']))
        receipt = {'node_id': node_id}
    elif operation == 'canvas_move':
        from .video_director_delivery import movable_video

        node_id = args['node_id']
        engine_nodes = {engine_node_id(work, shot['id']) for scene in work['scenes'].values()
                        for shot in scene['shots'].values()
                        if shot['revisions'][shot['head_revision']].get('configuration')}
        references = {reference_node_id(work, shot['id']) for scene in work['scenes'].values()
                      for shot in scene['shots'].values() if any(rev['images'] for rev in shot['revisions'].values())}
        require(node_id in shots or node_id in canvas['nodes'] or node_id in engine_nodes
                or node_id in references or movable_video(work, node_id),
                'DIRECTOR_CANVAS_NODE_NOT_FOUND')
        canvas['positions'][node_id] = args['position']
        receipt = {'node_id': node_id}
    else:
        node_id = args['node_id']
        require(node_id in canvas['nodes'], 'DIRECTOR_CANVAS_NODE_NOT_FOUND')
        del canvas['nodes'][node_id]
        canvas['positions'].pop(node_id, None)
        receipt = {'node_id': node_id}
    canvas['version'] += 1
    work['canvas'] = canvas
    return receipt | {'canvas_version': canvas['version'], 'work_id': work['id']}


def engine_view(config):
    return {key: config[key] for key in ('provider', 'model', 'mode')} if config else None


def work_view(work):
    result = {key: value for key, value in work.items() if key not in ('scenes', 'focus', 'generations', 'films', 'timeline', 'timeline_exports')}
    result['selection'] = current_selection(work)
    result['canvas'] = canvas_state(work)
    result['scenes'] = [
        {**{key: val for key, val in scene.items() if key != 'shots'},
         'shots': [
             {**{key: value for key, value in shot.items() if key != 'revisions'},
              'revisions': [revision_overview(rev) for rev in
                            sorted(shot['revisions'].values(), key=lambda row: row['number'])],
              'engine': engine_view(shot['revisions'][shot['head_revision']].get('configuration')),
              'engine_node_id': engine_node_id(work, shot['id']),
              'reference_node_id': reference_node_id(work, shot['id']),
              'cover_revision': (shot['adopted_revision'] or shot['head_revision'])
              if shot['revisions'][shot['adopted_revision'] or shot['head_revision']]['images'] else None}
             for shot in in_order(scene['shots'])
         ]}
        for scene in in_order(work['scenes'])
    ]
    return result


class Director:
    def __init__(self, projects):
        self.projects = projects

    def registered(self):
        projects = self.projects.view()['projects']
        parents = defaultdict(list)
        for row in projects:
            parents[row['name']].append(Path(row['root']).parent)
        result = []
        for row in projects:
            name, parent = row['name'], Path(row['root']).parent
            item = {'id': row['id'], 'name': name}
            if len(parents[name]) > 1:
                for length in range(1, len(parent.parts) + 1):
                    suffix = parent.parts[-length:]
                    if sum(other.parts[-length:] == suffix for other in parents[name]) == 1:
                        item['label'] = f'{name} · {Path(*suffix)}'
                        break
            result.append(item)
        return result

    def project(self, project_id):
        project = next((row for row in self.projects.view()['projects'] if row['id'] == project_id), None)
        require(project is not None, 'DIRECTOR_PROJECT_NOT_REGISTERED')
        root = exact_path(project['root'])
        try:
            info = root.lstat()
            require(stat.S_ISDIR(info.st_mode) and info.st_uid == os.getuid(), 'DIRECTOR_PROJECT_UNAVAILABLE')
        except OSError:
            raise WCEError('DIRECTOR_PROJECT_UNAVAILABLE') from None
        return root, identity(info)

    def storage(self, root, pin, create=False):
        location = root / ROOT_NAME
        if create and not os.path.lexists(location):
            descriptor = os.open(root, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
            try:
                require(identity(os.fstat(descriptor)) == pin, 'DIRECTOR_PROJECT_CHANGED')
                try:
                    os.mkdir(ROOT_NAME, 0o700, dir_fd=descriptor)
                    os.fsync(descriptor)
                except FileExistsError:
                    pass
            finally:
                os.close(descriptor)
        if os.path.lexists(location):
            path_check(location, True)
        require(identity(root.lstat()) == pin, 'DIRECTOR_PROJECT_CHANGED')
        return location

    def load(self, project_id, location):
        path = location / 'storyboards.json'
        if not os.path.lexists(path):
            return {'schema': 1, 'project_id': project_id, 'version': 0, 'works': {},
                    'selected_work': None, 'operations': {}}
        try:
            pin = path_check(path)
            raw = b''.join(FileSource(location).iter_html(path.name, expected_state=pin))
            data = json.loads(raw)
            require(type(data) is dict and set(data) == {
                'schema', 'project_id', 'version', 'works', 'selected_work', 'operations'}
                and data['schema'] == 1 and data['project_id'] == project_id
                and type(data['version']) is int and data['version'] >= 0
                and all(type(data[k]) is dict for k in ('works', 'operations'))
                and (data['selected_work'] is None or data['selected_work'] in data['works']),
                'DIRECTOR_STORE_UNAVAILABLE')
            return data
        except (OSError, ValueError, TypeError):
            raise WCEError('DIRECTOR_STORE_UNAVAILABLE') from None

    @staticmethod
    def scoped(state, args):
        work = lookup(state['works'], args['work_id'], 'DIRECTOR_WORK_NOT_FOUND')
        scene = lookup(work['scenes'], args['scene_id'], 'DIRECTOR_SCENE_NOT_FOUND')
        shot = lookup(scene['shots'], args['shot_id'], 'DIRECTOR_SHOT_NOT_FOUND')
        return work, scene, shot

    def overview(self, project_id, work_id=None, *, state=None):
        if state is None:
            root, pin = self.project(project_id)
            state = self.load(project_id, self.storage(root, pin))
        data = state
        selected = work_id or data['selected_work'] or next((work['id'] for work in in_order(data['works'])), None)
        current = lookup(data['works'], selected, 'DIRECTOR_WORK_NOT_FOUND') if selected else None
        return {
            'project_id': project_id, 'version': data['version'],
            'works': [{'id': row['id'], 'title': row['title']} |
                      ({'kind': 'article'} if row.get('kind') == 'article' else {})
                      for row in in_order(data['works'])],
            'work': work_view(current) if current else None,
        }

    def context(self, args):
        project_id = args['project_id']
        root, pin = self.project(project_id)
        data = self.load(project_id, self.storage(root, pin))
        work, scene, shot = self.scoped(data, args)
        revision = lookup(shot['revisions'], args['revision_id'], 'DIRECTOR_REVISION_NOT_FOUND')
        return {
            'project_id': project_id, 'project_name': root.name, 'project_root': str(root), 'work_id': work['id'],
            'work': {key: work[key] for key in WORK_FIELDS},
            'scene_id': scene['id'], 'scene': {key: scene[key] for key in ('title', 'start_ms', 'end_ms')},
            'shot_id': shot['id'], 'revision': revision, 'head_revision': shot['head_revision'],
            'adopted_revision': shot['adopted_revision'],
        }

    def request(self, operation_id):
        binding = self.projects.director_request(operation_id)
        if binding is None:
            return {'state': 'NOT_FOUND', 'operation_id': operation_id}
        project_id, work_id = binding['project_id'], binding['work_id']
        root, pin = self.project(project_id)
        state = self.load(project_id, self.storage(root, pin))
        if work_id is None:
            operation = state['operations'].get('start:' + operation_id)
            if operation is None:
                return {'state': 'PENDING', 'operation_id': operation_id, 'project_id': project_id}
            work_id = operation['receipt']['work_id']
        lookup(state['works'], work_id, 'DIRECTOR_WORK_NOT_FOUND')
        return {'state': 'READY', 'operation_id': operation_id, 'project_id': project_id, 'work_id': work_id}

    def start_work(self, args, verify_revision):
        project_id, operation_id = args['project_id'], args['operation_id']
        root, _ = self.project(project_id)
        require(root == exact_path(args['project_root']), 'DIRECTOR_PROJECT_CHANGED')
        if 'work_id' in args:
            self.overview(project_id, args['work_id'])
        else:
            self.new_work_fields(args['fields'])
        # Reserve before the project write so the original request cannot move to another root after a crash.
        self.projects.reserve_director_request(operation_id, project_id, args.get('work_id'), digest(args))
        if 'fields' in args:
            self.edit(args, verify_revision)
        return self.request(operation_id)

    def edit(self, args, verify_revision, verify_canvas_node=None, jobs=None, publish_timeline=None):
        project_id = args['project_id']
        root, pin = self.project(project_id)
        for_chat = args['action'] == 'start_work'
        operation = ('start:' if for_chat else '') + args['operation_id']
        location = self.storage(root, pin, create=for_chat or args['action'] in ('create_work', 'register_article'))
        require(location.is_dir(), 'DIRECTOR_WORK_NOT_FOUND')
        location_pin = path_check(location, True)
        state_path = location / 'storyboards.json'
        with locked(location / 'writer.lock'):
            state = self.load(project_id, location)
            fingerprint = digest(args)
            previous = state['operations'].get(operation)
            if previous is not None:
                require(previous['fingerprint'] == fingerprint, 'DIRECTOR_OPERATION_CONFLICT')
                return previous['receipt']
            receipt = self.apply(state, args, root, location, verify_revision, verify_canvas_node, jobs, publish_timeline)
            state['version'] += 1
            receipt.update(state='SAVED', project_id=project_id, version=state['version'])
            state['operations'][operation] = {'fingerprint': fingerprint, 'receipt': receipt}
            require(self.project(project_id) == (root, pin), 'DIRECTOR_PROJECT_CHANGED')
            limit = len(json.dumps(state, ensure_ascii=False).encode('utf-8')) + 1024
            atomic_write(state_path, state, maximum=limit, expected_parent=location_pin)
            require(self.load(project_id, location)['operations'].get(operation, {}).get('receipt')
                    == receipt, 'DIRECTOR_SAVE_NOT_VERIFIED')
            return receipt

    @staticmethod
    def new_work_fields(fields):
        values = WORK_FIELDS | fields
        values['title'] = display_name(values['title'])
        for key in WORK_FIELDS:
            if isinstance(values[key], str):
                values[key] = project_text(values[key])
        return values

    def apply(self, state, args, root, scratch, verify_revision, verify_canvas_node=None, jobs=None, publish_timeline=None):
        action = args['action']
        if action == 'register_article':
            pointer = args['article']
            existing = next((row for row in state['works'].values() if row.get('article') == pointer), None)
            if existing:
                return {'work_id': existing['id'], 'kind': 'article'}
            work_id = secrets.token_hex(16)
            state['works'][work_id] = self.new_work_fields(args['fields']) | {
                'id': work_id, 'position': len(state['works']), 'kind': 'article',
                'article': pointer, 'scenes': {}, 'focus': None,
            }
            if not state['selected_work']:
                state['selected_work'] = work_id
            return {'work_id': work_id, 'kind': 'article'}
        if action in ('create_work', 'start_work'):
            work_id = secrets.token_hex(16)
            values = self.new_work_fields(args['fields'])
            state['works'][work_id] = {'id': work_id, 'position': len(state['works']),
                                       **values, 'scenes': {}, 'focus': None}
            if action == 'create_work':
                state['selected_work'] = work_id
            return {'work_id': work_id}
        work_id = args['work_id']
        work = lookup(state['works'], work_id, 'DIRECTOR_WORK_NOT_FOUND')
        if work.get('kind') == 'article':
            require(action == 'select_work', 'ARTICLE_WORK_USE_ARTICLE_TOOLS')
        if action in ('canvas_add', 'canvas_view', 'canvas_move', 'canvas_remove', 'canvas_note_edit'):
            return canvas_edit(work, args, lambda node: verify_canvas_node(node, root, state['project_id']))
        if action == 'create_clip_variant':
            require(callable(publish_timeline), 'DIRECTOR_VARIANT_RENDER_REQUIRED')
            return publish_timeline(root, work)
        if action in ('timeline_save', 'timeline_export'):
            from . import video_director_timeline as timeline
            current = timeline.saved(work)
            require(current['timeline_version'] == args['expected_timeline_version'], 'DIRECTOR_TIMELINE_CHANGED')
            if action == 'timeline_export':
                require(callable(publish_timeline), 'DIRECTOR_RENDER_REQUIRED')
                return publish_timeline(root, work)
            return timeline.save(jobs, root, state['project_id'], work, args)
        if action == 'track_generation':
            from .video_director_delivery import track
            return track(jobs, state, work, args)
        if action == 'register_work_video':
            from .video_director_delivery import register_work_video
            return register_work_video(root, work, args)
        if action == 'adopt_video':
            from .video_director_delivery import adopt_video
            return adopt_video(jobs, state['project_id'], work, args)
        if action == 'select_work':
            state['selected_work'] = work_id
            return {'work_id': work_id}
        if action == 'edit_work':
            require(args['expected_version'] == state['version'], 'DIRECTOR_STALE_REVISION')
            work.update({key: project_text(value) if isinstance(value, str) else value
                         for key, value in args['fields'].items()})
            work['title'] = display_name(work['title'])
            return {'work_id': work_id}
        if action == 'create_scene':
            scene_id = secrets.token_hex(16)
            require(args['end_ms'] >= args['start_ms'], 'DIRECTOR_TIME_RANGE_INVALID')
            work['scenes'][scene_id] = {'id': scene_id, 'position': len(work['scenes']),
                                       'title': display_name(args['title']),
                                       'start_ms': args['start_ms'], 'end_ms': args['end_ms'], 'shots': {}}
            return {'work_id': work_id, 'scene_id': scene_id}
        scene_id = args['scene_id']
        scene = lookup(work['scenes'], scene_id, 'DIRECTOR_SCENE_NOT_FOUND')
        if action == 'select_scene':
            state['selected_work'] = work_id
            work['focus'] = {'scene_id': scene_id}
            return {'work_id': work_id, 'scene_id': scene_id}
        if action == 'create_shot':
            shot_id = secrets.token_hex(16)
            revision_id = secrets.token_hex(16)
            values = REVISION_FIELDS | {'title': display_name(args['title']),
                                        'ratio': work['ratio'], 'start_ms': scene['start_ms'], 'end_ms': scene['start_ms']}
            revision = {**deepcopy(values), 'id': revision_id, 'number': 1, 'parent_revision': None,
                        'origin': args.get('origin', 'panel')}
            scene['shots'][shot_id] = {'id': shot_id, 'position': len(scene['shots']),
                                       'head_revision': revision_id, 'adopted_revision': None,
                                       'revisions': {revision_id: revision}}
            selection = {'scene_id': scene_id, 'shot_id': shot_id, 'revision_id': revision_id}
            if work['focus'] == {'scene_id': scene_id}:
                work['focus'] = selection
            return {'work_id': work_id, **selection}
        shot_id = args['shot_id']
        shot = lookup(scene['shots'], shot_id, 'DIRECTOR_SHOT_NOT_FOUND')
        receipt = {'work_id': work_id, 'scene_id': scene_id, 'shot_id': shot_id}
        if action in ('select_revision', 'adopt'):
            revision_id = args['revision_id']
            lookup(shot['revisions'], revision_id, 'DIRECTOR_REVISION_NOT_FOUND')
            if action == 'adopt':
                require(args['base_revision'] == shot['head_revision'], 'DIRECTOR_STALE_REVISION')
                require(args.get('expected_adopted') == shot['adopted_revision'], 'DIRECTOR_STALE_REVISION')
                shot['adopted_revision'] = revision_id
            state['selected_work'] = work_id
            work['focus'] = {'scene_id': scene_id, 'shot_id': shot_id, 'revision_id': revision_id}
            return receipt | {'revision_id': revision_id}
        require(action == 'revise')
        base = args['base_revision']
        require(base == shot['head_revision'], 'DIRECTOR_STALE_REVISION')
        original = shot['revisions'][base]
        patch = args['fields']
        previous = {key: original[key] for key in REVISION_FIELDS}
        previous.update({key: original[key] for key in ('voice', 'stage') if key in original})
        values = previous | patch
        for key in REVISION_FIELDS:
            if type(values[key]) is str:
                values[key] = project_text(values[key])
        values['title'] = display_name(values['title'])
        require(values['end_ms'] >= values['start_ms'], 'DIRECTOR_TIME_RANGE_INVALID')
        verify_revision(values, patch, root, scratch, args['project_id'], work_id, original['images'])
        for key in ('voice', 'stage'):
            if values.get(key) is None:
                values.pop(key, None)
        if values == previous:
            return receipt | {'revision_id': base}
        revision_id = secrets.token_hex(16)
        shot['revisions'][revision_id] = {**values, 'id': revision_id, 'number': original['number'] + 1,
                                          'parent_revision': base, 'origin': args.get('origin', 'panel')}
        shot['head_revision'] = revision_id
        focus = work['focus']
        if state['selected_work'] == work_id and focus == {
                'scene_id': scene_id, 'shot_id': shot_id, 'revision_id': base}:
            work['focus'] = {'scene_id': scene_id, 'shot_id': shot_id, 'revision_id': revision_id}
        return receipt | {'revision_id': revision_id}
