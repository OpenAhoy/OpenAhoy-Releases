"""Scoped projection of original provider receipts and registered local films."""
from base64 import b64encode
from functools import lru_cache
from hashlib import sha256
from math import isfinite
import os
import stat

from .bounded_file import FileSource, file_state
from .contracts import WCEError
from .own_connection_policy import read_optional
from .service import digest
from .video_director import display_name, lookup, require
from .video_jobs import PLAYBACK_CHUNK, RECEIPT_MAX, probe
from .video_engine_catalog import REFERENCE, validate_config
from .video_minimax import subject_body
from .video_relay import RELAY_MODEL, workflow_body
from .video_seedance import ARK_MODELS

ACTIVE = {'SUBMITTED', 'QUEUED', 'RUNNING', 'SAVE_PENDING'}
OBSERVED = ACTIVE | {'ASSET_READY', 'SUBMIT_UNKNOWN', 'SUBMIT_REJECTED', 'FAILED',
                     'EXPIRED', 'CANCELLED'}


def channel(request):
    if request['model'] == RELAY_MODEL:
        return 'relay'
    if request.get('provider') == 'tokenhex':
        return 'tokenhex'
    if request.get('provider_site') in ('cn', 'global'):
        return request['provider_site']
    return 'ark' if request['model'] in ARK_MODELS and not request.get('provider') else None


def read_receipt(jobs, attempt, project):
    path, _ = jobs._paths(attempt)
    row = read_optional(path, RECEIPT_MAX)
    if row is None:
        return None
    require(row['request']['project_id'] == project and row['generation_attempt_id'] == attempt,
            'DIRECTOR_ASSET_WRONG_PROJECT')
    return row


def receipt_witness(revision, project):
    config = revision['configuration']
    profile = validate_config(config, project, ready=True)
    prompt = revision['prompt']
    require(prompt.strip(), 'DIRECTOR_PROMPT_REQUIRED')
    mode = config['mode']
    if mode == 'subject':
        return {'request_sha256': sha256(subject_body(prompt, config['subject_image_url'])).hexdigest()}
    if mode == 'workflow':
        body = workflow_body({'prompt': prompt, **{k: config[k] for k in (
            'reference_images', 'reference_audio', 'duration', 'resolution') if k in config}})
        return {'request_sha256': sha256(body).hexdigest()}
    roles = profile['local_roles']
    images = revision['images']
    if profile['reference_count']:
        frames = [image for image in images if image['role'] in REFERENCE]
        require(1 <= len(frames) <= profile['reference_count'], 'DIRECTOR_REFERENCE_IMAGES_REQUIRED')
    else:
        frames = [image for role in roles for image in images if image['role'] == role]
        require(len(frames) == len(roles), 'DIRECTOR_INPUT_FRAMES_REQUIRED')
    params = {k: config[k] for k in ('duration', 'resolution', 'ratio', 'direction') if k in config}
    if config['provider'] == 'tokenhex':
        params.pop('ratio', None)
    if config['provider'] in ('ark', 'tokenhex'):
        params['audio'] = config.get('audio', False)
    if source := config.get('source'):
        params.update(source_attempt_id=source['attempt_id'], source_sha256=source['sha256'])
    params.update(frames=[image['file']['sha256'] for image in frames],
                  prompt_sha256=sha256(prompt.encode()).hexdigest())
    return {'request': params, 'reference_asset': config.get('source', {}).get('reference_asset')}


def generation_scope(row, spec):
    source = row['request']
    require(source['model'] == spec['model'] and channel(source) == spec['provider'],
            'DIRECTOR_GENERATION_SCOPE_CHANGED')
    # Old receipts did not write a mode for the default first-and-last route.
    actual_mode = source.get('mode', 'frames')
    require(actual_mode == spec['mode'], 'DIRECTOR_GENERATION_SCOPE_CHANGED')
    witness = spec['witness']
    if 'request_sha256' in witness:
        require(row.get('request_sha256') == witness['request_sha256'], 'DIRECTOR_GENERATION_SCOPE_CHANGED')
    else:
        fields = witness['request']
        require(all(source.get(k, False if k == 'audio' else None) == value for k, value in fields.items())
                and (row.get('recipe') or {}).get('reference_asset') == witness['reference_asset'],
                'DIRECTOR_GENERATION_SCOPE_CHANGED')


def local_video_source(root, file):
    from .video_director_media import local_file

    path = local_file(root, file)
    try:
        info = path.lstat()
    except OSError:
        raise WCEError('DIRECTOR_WORK_VIDEO_UNAVAILABLE') from None
    require(path.suffix.lower() == '.mp4' and stat.S_ISREG(info.st_mode)
            and info.st_uid == os.getuid() and info.st_nlink == 1 and info.st_size > 0,
            'DIRECTOR_WORK_VIDEO_UNAVAILABLE')
    return path, file_state(info)


@lru_cache(maxsize=4)
def verify_local_video(root, relative, pin, checksum):
    source = FileSource(root)
    length = 0
    content_hash = sha256()
    for chunk in source.iter_html(relative, expected_state=pin):
        if not length:
            require(chunk[4:8] == b'ftyp', 'DIRECTOR_WORK_VIDEO_INVALID')
        content_hash.update(chunk)
        length += len(chunk)
    require(content_hash.hexdigest() == checksum, 'DIRECTOR_ASSET_CHANGED')
    path = root / relative
    facts = probe(str(path), error='DIRECTOR_WORK_VIDEO_INVALID')
    seconds = facts.get('seconds')
    require(facts.get('playable') is True and type(seconds) in (int, float) and
            isfinite(seconds) and seconds > 0 and file_state(path.lstat()) == pin,
            'DIRECTOR_WORK_VIDEO_INVALID')
    return {'sha256': checksum, 'bytes': length, 'seconds': seconds}


def delivery_rows(work):
    tracked = work.get('generations', {})
    rows = {(spec['shot_id'], spec['attempt_id']): spec for spec in tracked.values()}
    for scene in work['scenes'].values():
        for shot in scene['shots'].values():
            for revision_id in dict.fromkeys(r for r in (shot['head_revision'], shot['adopted_revision']) if r):
                revision = shot['revisions'][revision_id]
                if result := revision.get('result'):
                    key = (shot['id'], result['attempt_id'])
                    row = {'attempt_id': result['attempt_id'], 'shot_id': shot['id'], 'scene_id': scene['id'],
                           'revision_id': revision_id, 'title': revision['title']}
                    # An explicit result association is already protected by its original digest.
                    if key not in rows or 'sha256' not in rows[key]:
                        rows[key] = rows.get(key, row) | {'sha256': result['sha256']}
    return rows


def track(jobs, state, work, args):
    scene = lookup(work['scenes'], args['scene_id'], 'DIRECTOR_SCENE_NOT_FOUND')
    shot = lookup(scene['shots'], args['shot_id'], 'DIRECTOR_SHOT_NOT_FOUND')
    revision = lookup(shot['revisions'], args['revision_id'], 'DIRECTOR_REVISION_NOT_FOUND')
    require(revision.get('configuration'), 'DIRECTOR_CONFIGURATION_REQUIRED')
    config = revision['configuration']
    spec = {key: args[key] for key in ('attempt_id', 'scene_id', 'shot_id', 'revision_id')}
    spec.update(title=revision['title'], witness=receipt_witness(revision, state['project_id']),
                **{key: config[key] for key in ('provider', 'model', 'mode')})
    for existing_work in state['works'].values():
        if prior := existing_work.get('generations', {}).get(args['attempt_id']):
            require(existing_work['id'] == work['id'] and prior == spec,
                    'DIRECTOR_GENERATION_SCOPE_CHANGED')
    if row := read_receipt(jobs, args['attempt_id'], state['project_id']):
        generation_scope(row, spec)
    work.setdefault('generations', {})[args['attempt_id']] = spec
    return {'work_id': work['id'], **{k: v for k, v in spec.items() if k != 'witness'}}


def register_work_video(root, work, args):
    file = args['file']
    require(file['project_id'] == args['project_id'], 'DIRECTOR_ASSET_WRONG_PROJECT')
    path, pin = local_video_source(root, file)
    asset = verify_local_video(root, file['path'], pin, file['sha256'])
    delivery_id = digest(['work_video', work['id'], file['sha256']])[:32]
    films = work.setdefault('films', {})
    if delivery_id in films:
        prior = films[delivery_id]
        # A repeat registration of the same original is one card.
        require(prior['file'] == file, 'DIRECTOR_WORK_VIDEO_CHANGED')
        chat_path = str(path)
    else:
        films[delivery_id] = {'file': file, 'asset': asset, 'title': display_name(args['title'])}
        chat_path = str(path)
    return {'work_id': work['id'], 'delivery_id': delivery_id, 'asset': asset, 'chat_path': chat_path}


def collect(jobs, root, project, work, *, poll_attempt=None):
    cards = []
    for key, spec in delivery_rows(work).items():
        attempt = spec['attempt_id']
        # A deliberate legacy canvas placement already displays this original.
        if any(node.get('shot_id') == spec['shot_id'] and node.get('asset', {}).get('family') == 'video'
               and node['asset']['attempt_id'] == attempt and node['asset']['project_id'] == project
               for node in work.get('canvas', {}).get('nodes', {}).values()):
            continue
        card = {'id': digest(['shot_video', work['id'], *key])[:32], 'kind': 'shot_video',
                **{k: spec[k] for k in ('shot_id', 'scene_id', 'revision_id', 'title')}, 'attempt_id': attempt,
                'state': 'AWAITING_RECEIPT'}
        try:
            row = read_receipt(jobs, attempt, project)
            if row:
                if 'provider' in spec:
                    generation_scope(row, spec)
                if attempt == poll_attempt and 'provider' in spec and row['state'] in ACTIVE and row.get('provider_task_id'):
                    try:
                        row = jobs.status(attempt, project, poll=True)
                    except (OSError, WCEError):
                        card['check_unavailable'] = True
                request = row['request']
                card.update(state=row['state'] if row['state'] in OBSERVED else 'UNKNOWN',
                            engine={'provider': channel(request), 'model': request['model']})
                if 'provider' in spec and row['state'] in ACTIVE and row.get('provider_task_id'):
                    card['pollable'] = True
                if row.get('query_error'):
                    card['check_unavailable'] = True
                if row['state'] == 'ASSET_READY':
                    asset = row['asset']
                    require(not spec.get('sha256') or spec['sha256'] == asset['sha256'],
                            'DIRECTOR_ASSET_CHANGED')
                    _, original = jobs._paths(attempt)
                    require(original.is_file() and not original.is_symlink() and original.stat().st_size == asset['bytes'],
                            'DIRECTOR_ASSET_CHANGED')
                    card['asset'] = {'family': 'video', 'project_id': project, 'attempt_id': attempt,
                                     'sha256': asset['sha256']}
        except (OSError, WCEError, KeyError, TypeError):
            card['state'] = 'UNAVAILABLE'
        cards.append(card)
    for identifier, film in work.get('films', {}).items():
        card = {'id': identifier, 'kind': 'work_video', 'title': film['title'], 'state': 'UNAVAILABLE'}
        try:
            _, pin = local_video_source(root, film['file'])
            asset = verify_local_video(root, film['file']['path'], pin, film['file']['sha256'])
            card.update(state='ASSET_READY', sha256=asset['sha256'])
        except (OSError, WCEError, TypeError, KeyError):
            pass
        cards.append(card)
    return cards


def chunk(root, work, args):
    film = lookup(work.get('films', {}), args['delivery_id'], 'DIRECTOR_WORK_VIDEO_UNAVAILABLE')
    file = film['file']
    require(file['project_id'] == args['project_id'], 'DIRECTOR_ASSET_WRONG_PROJECT')
    _, pin = local_video_source(root, file)
    asset = verify_local_video(root, file['path'], pin, file['sha256'])
    offset = args['offset']
    require(0 <= offset < asset['bytes'], 'VIDEO_ASSET_OFFSET_INVALID')
    data = b''.join(FileSource(root).iter_html(file['path'], expected_state=pin, offset=offset,
                                              length=min(PLAYBACK_CHUNK, asset['bytes']-offset)))
    return {'offset': offset, 'total': asset['bytes'], 'sha256': asset['sha256'],
            'bytes': b64encode(data).decode('ascii')}
