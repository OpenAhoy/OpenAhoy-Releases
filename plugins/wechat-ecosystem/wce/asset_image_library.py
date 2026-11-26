"""Read original images already referenced in registered production works."""

from base64 import b64encode
from pathlib import PurePosixPath

from . import character_library as verified_images
from .contracts import WCEError
from .video_director import canvas_state, require
from .video_director_media import IMAGE_CHUNK, preview_image_bytes


def images_in(project_id, snapshot, registry, failures=None):
    rows = {}

    def add(file, label, usage):
        if file['project_id'] != project_id:
            return
        checksum = file['sha256']
        if checksum not in rows:
            rows[checksum] = [{'project_id': project_id, 'sha256': checksum,
                               'title': label or PurePosixPath(file['path']).name, 'uses': []}, {}]
        row, proven = rows[checksum]
        row['uses'].append(usage)
        proven[file['path']] = file

    from .article_work import snapshot as article_source
    for work in snapshot['works'].values():
        owner = {'work_id': work['id'], 'work': work['title']}
        if work.get('kind') == 'article':
            try:
                article = article_source(work['article'], registry)
            except (OSError, WCEError):
                if failures is not None:
                    failures.append(work['id'])
                continue
            owner['work'] = article['title']
            for slot, item in article['images'].items():
                checksum = item['sha256']
                label = article['title']
                row, proven = rows.setdefault(checksum, [
                    {'project_id': project_id, 'sha256': checksum, 'title': label, 'uses': []}, {},
                ])
                row['uses'].append(owner | {
                    'kind': 'article', 'role': item['role'], 'account': article['account_label'],
                    'connection_id': article['connection_id'],
                    'revision': article['revision'], 'slot': slot,
                })
                proven[(work['id'], slot)] = {
                    'pointer': work['article'], 'version': article['version'], 'slot': slot,
                }
            continue
        for node in canvas_state(work)['nodes'].values():
            if node['kind'] == 'image':
                add(node['file'], node['title'], owner | {
                    'kind': 'canvas', 'node_id': node['id'], 'title': node['title'],
                })
        for scene in work['scenes'].values():
            for shot in scene['shots'].values():
                for revision in sorted(shot['revisions'].values(), key=lambda rev: -rev['number']):
                    for frame in revision['images']:
                        add(frame['file'], revision['title'], owner | {
                            'kind': 'shot', 'shot_id': shot['id'], 'shot': revision['title'],
                            'revision_id': revision['id'], 'revision': revision['number'], 'role': frame['role'],
                        })
    return rows


def catalog(director):
    projects = []
    for project in director.registered():
        project_id = project['id']
        entry = {'id': project_id, 'name': project.get('label') or project['name'], 'images': []}
        try:
            root, pin = director.project(project_id)
            snapshot = director.load(project_id, director.storage(root, pin))
            entry['images'] = [row | {'project_label': entry['name']}
                               for row, _ in images_in(project_id, snapshot, director.projects.registry).values()]
        except (OSError, WCEError):
            entry['unavailable'] = True
        projects.append(entry)
    return {'projects': projects}


def original(director, args, *, thumbnail=False, allowed_uses=None):
    project_id = args['project_id']
    root, project_pin = director.project(project_id)
    snapshot = director.load(project_id, director.storage(root, project_pin))
    registry = director.projects.registry
    row = images_in(project_id, snapshot, registry).get(args['sha256'])
    require(row, 'DIRECTOR_IMAGE_NOT_REGISTERED')
    checksum = args['sha256']
    connection = args.get('connection_id')
    for path, spec in row[1].items():
        if allowed_uses is not None:
            cid=spec.get('pointer',{}).get('connection_id')
            if not any(use.get('connection_id')==cid for use in allowed_uses):
                continue
        if connection and spec.get('pointer', {}).get('connection_id') != connection:
            continue
        if 'pointer' in spec:
            from .article_work import snapshot as article_source
            try:
                part = article_source(spec['pointer'], registry, version=spec['version'],
                                      slot=spec['slot'], offset=args.get('offset', 0), thumbnail=thumbnail)
                require(part['sha256'] == checksum, 'DIRECTOR_ASSET_CHANGED')
            except (OSError, WCEError):
                continue
            require(director.project(project_id) == (root, project_pin), 'DIRECTOR_PROJECT_CHANGED')
            if thumbnail:
                return part
            return {'mime_type': part['declared_type'], 'sha256': checksum,
                    'total': part['size'], 'offset': part['offset'], 'data': part['data']}
        try:
            pin = verified_images.file_pin(root, spec)
            mime, data = verified_images.original(root, path, checksum, pin)
        except (OSError, WCEError):
            continue
        require(director.project(project_id) == (root, project_pin), 'DIRECTOR_PROJECT_CHANGED')
        if thumbnail:
            return preview_image_bytes(data, checksum, False)
        offset = args['offset']
        require(0 <= offset < len(data), 'DIRECTOR_IMAGE_OFFSET_INVALID')
        return {'mime_type': mime, 'sha256': checksum, 'total': len(data), 'offset': offset,
                'data': b64encode(data[offset:offset + IMAGE_CHUNK]).decode('ascii')}
    raise WCEError('DIRECTOR_IMAGE_ORIGINAL_UNAVAILABLE')
