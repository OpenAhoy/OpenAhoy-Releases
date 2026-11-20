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
    return {'sha256': checksum, 'bytes': length, 'seconds': seconds,
            'audio_tracks': facts.get('audio_tracks', 0)}


def shot_video_node(work, shot_id):
    return digest(['shot_video_node', work['id'], shot_id])[:32]


def candidate_id(work, key):
    return digest(['shot_video', work['id'], *key])[:32]


def delivery_rows(work):
    tracked = work.get('generations', {})
    rows = {(spec['shot_id'], spec['attempt_id']): spec for spec in tracked.values()}
    for scene in work['scenes'].values():
        for shot in scene['shots'].values():
            for revision in sorted(shot['revisions'].values(), key=lambda value: value['number'], reverse=True):
                if result := revision.get('result'):
                    key = (shot['id'], result['attempt_id'])
                    row = {'attempt_id': result['attempt_id'], 'shot_id': shot['id'], 'scene_id': scene['id'],
                           'revision_id': revision['id'], 'title': revision['title'],
                           'project_id': result['project_id']}
                    # An explicit result association is already protected by its original digest.
                    if key not in rows or 'sha256' not in rows[key]:
                        rows[key] = rows.get(key, row) | {'sha256': result['sha256']}
            for node in work.get('canvas', {}).get('nodes', {}).values():
                asset = node.get('asset', {})
                if node.get('shot_id') == shot['id'] and asset.get('family') == 'video':
                    key = (shot['id'], asset['attempt_id'])
                    rows.setdefault(key, {'attempt_id': asset['attempt_id'], 'shot_id': shot['id'],
                                          'scene_id': scene['id'], 'revision_id': None, 'title': node['title'],
                                          'sha256': asset['sha256'], 'project_id': asset['project_id']})
    return rows


def movable_video(work, node_id):
    return node_id in work.get('films', {}) or any(
        shot_video_node(work, shot_id) == node_id for shot_id, _ in delivery_rows(work))


def adopted_candidate(work, shot):
    if pinned := shot.get('adopted_video'):
        return pinned
    original = shot['revisions'].get(shot['adopted_revision'], {}).get('result')
    if original is None:
        return None
    return {'candidate_id': candidate_id(work, (shot['id'], original['attempt_id'])),
            'sha256': original['sha256']}


def candidate_spec(work, identifier):
    return next((spec for key, spec in delivery_rows(work).items() if candidate_id(work, key) == identifier), None)


def verified_candidate(jobs, project, spec, checksum):
    require(spec, 'DIRECTOR_RESULT_UNAVAILABLE')
    require(spec.get('project_id', project) == project, 'DIRECTOR_ASSET_WRONG_PROJECT')
    row = read_receipt(jobs, spec['attempt_id'], project)
    require(row, 'DIRECTOR_RESULT_UNAVAILABLE')
    if 'provider' in spec:
        generation_scope(row, spec)
    _, asset, _ = jobs._playable(spec['attempt_id'], project)
    require(asset['sha256'] == checksum == spec.get('sha256', checksum), 'DIRECTOR_ASSET_CHANGED')
    return asset


def adopt_video(jobs, project, work, args):
    scene = lookup(work['scenes'], args['scene_id'], 'DIRECTOR_SCENE_NOT_FOUND')
    shot = lookup(scene['shots'], args['shot_id'], 'DIRECTOR_SHOT_NOT_FOUND')
    prior = adopted_candidate(work, shot)
    require(args.get('expected_candidate_id') == (prior and prior['candidate_id']), 'DIRECTOR_STALE_REVISION')
    spec = candidate_spec(work, args['candidate_id'])
    require(spec and spec['scene_id'] == scene['id'] and spec['shot_id'] == shot['id'],
            'DIRECTOR_RESULT_UNAVAILABLE')
    verified_candidate(jobs, project, spec, args['sha256'])
    shot['adopted_video'] = {key: args[key] for key in ('candidate_id', 'sha256')}
    return {'work_id': work['id'], 'scene_id': scene['id'], 'shot_id': shot['id'],
            'adopted_video': shot['adopted_video']}


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


def inbox_id(project):
    return digest(['director_inbox', project])[:32]


def inbox_rows(jobs, project, project_pin, works):
    related = {}
    for work in works.values():
        for spec in delivery_rows(work).values():
            related.setdefault(spec['attempt_id'], []).append(spec)

    incoming = {}
    for row in jobs.receipts():
        if (row.get('director_binding') != {'kind': 'project_inbox', 'project_id': project}
                or row.get('project_video_root') != list(project_pin)
                or row['request']['project_id'] != project):
            continue
        attempt = row['generation_attempt_id']
        linked = False
        for spec in related.get(attempt, ()):
            try:
                if 'provider' in spec:
                    generation_scope(row, spec)
                elif row.get('asset', {}).get('sha256') != spec.get('sha256'):
                    continue
                linked = True
                break
            except (KeyError, WCEError):
                continue
        if not linked:
            incoming[digest(['director_inbox_take', project, attempt])[:32]] = row
    return incoming


def inbox_cards(rows, jobs, project):
    cards = []
    for identifier, row in sorted(rows.items(), key=lambda item: (item[1]['created_at'], item[0]), reverse=True):
        attempt = row['generation_attempt_id']
        request = row['request']
        card = {'id': identifier, 'kind': 'inbox_video', 'title': attempt, 'attempt_id': attempt,
                'state': row['state'] if row['state'] in OBSERVED else 'UNKNOWN',
                'engine': {'provider': channel(request), 'model': request['model']}}
        if row['state'] == 'ASSET_READY':
            try:
                _, asset, _ = jobs._playable(attempt, project)
                card['asset'] = {'family': 'video', 'project_id': project, 'attempt_id': attempt,
                                 **{key: asset[key] for key in ('sha256', 'bytes', 'seconds')},
                                 'audio_tracks': asset.get('audio_tracks', 0)}
            except (OSError, WCEError, KeyError):
                card['state'] = 'UNAVAILABLE'
        cards.append(card)
    return cards


def inbox_playback(rows, jobs, args):
    row = lookup(rows, args['delivery_id'], 'DIRECTOR_RESULT_UNAVAILABLE')
    attempt, project = row['generation_attempt_id'], args['project_id']
    _, asset, _ = jobs._playable(attempt, project)
    require(asset['sha256'] == args['sha256'], 'DIRECTOR_ASSET_CHANGED')
    if 'offset' in args:
        result = jobs.playback(attempt, project, args['offset'])
        require(result['sha256'] == args['sha256'], 'DIRECTOR_ASSET_CHANGED')
        return result
    return jobs.preview_frames(args['start'], attempt, project)


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
        scene = work['scenes'][spec['scene_id']]
        shot = scene['shots'][spec['shot_id']]
        adopted = adopted_candidate(work, shot)
        identifier = candidate_id(work, key)
        card = {'id': identifier, 'node_id': shot_video_node(work, shot['id']), 'kind': 'shot_video',
                **{k: spec[k] for k in ('shot_id', 'scene_id', 'revision_id', 'title')}, 'attempt_id': attempt,
                'state': 'AWAITING_RECEIPT', 'adopted_candidate_id': adopted and adopted['candidate_id']}
        try:
            require(spec.get('project_id', project) == project, 'DIRECTOR_ASSET_WRONG_PROJECT')
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
                binding = row.get('director_binding') or {}
                if (binding.get('kind') == 'shot' and binding.get('work_id') == work['id']
                        and binding.get('project_id') == project
                        and all(binding.get(key) == spec.get(key) for key in ('scene_id', 'shot_id', 'revision_id'))):
                    card['input_verification'] = binding['verification']
                    card['character_inputs'] = binding['characters']
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
                                     **{k: asset[k] for k in ('sha256', 'bytes', 'seconds')},
                                     'audio_tracks': asset.get('audio_tracks', 0)}
                    card['adopted'] = adopted == {'candidate_id': identifier, 'sha256': asset['sha256']}
        except (OSError, WCEError, KeyError, TypeError):
            card['state'] = 'UNAVAILABLE'
        cards.append(card)
    for identifier, film in work.get('films', {}).items():
        card = {'id': identifier, 'kind': 'work_video', 'title': film['title'], 'state': 'UNAVAILABLE'}
        try:
            _, pin = local_video_source(root, film['file'])
            asset = verify_local_video(root, film['file']['path'], pin, film['file']['sha256'])
            card.update(state='ASSET_READY', **asset)
        except (OSError, WCEError, TypeError, KeyError):
            pass
        cards.append(card)
    return cards


def work_video(root, work, args):
    film = lookup(work.get('films', {}), args['delivery_id'], 'DIRECTOR_WORK_VIDEO_UNAVAILABLE')
    file = film['file']
    require(file['project_id'] == args['project_id'], 'DIRECTOR_ASSET_WRONG_PROJECT')
    _, pin = local_video_source(root, file)
    asset = verify_local_video(root, file['path'], pin, file['sha256'])
    return file, pin, asset


def chunk(root, work, args):
    file, pin, asset = work_video(root, work, args)
    offset = args['offset']
    require(0 <= offset < asset['bytes'], 'VIDEO_ASSET_OFFSET_INVALID')
    data = b''.join(FileSource(root).iter_html(file['path'], expected_state=pin, offset=offset,
                                              length=min(PLAYBACK_CHUNK, asset['bytes']-offset)))
    return {'offset': offset, 'total': asset['bytes'], 'sha256': asset['sha256'],
            'bytes': b64encode(data).decode('ascii')}


def playback(jobs, root, work, args):
    project, identifier = args['project_id'], args['delivery_id']
    if identifier in work.get('films', {}):
        file, pin, asset = work_video(root, work, args)
        require(asset['sha256'] == args['sha256'], 'DIRECTOR_ASSET_CHANGED')
        if 'offset' in args:
            return chunk(root, work, args)
        start = args['start']
        require(start < asset['seconds'] * 8, 'VIDEO_ASSET_OFFSET_INVALID')
        frames = probe('frames', str(root / file['path']), str(start), error='VIDEO_PREVIEW_UNAVAILABLE')
        _, current = local_video_source(root, file)
        require(current == pin, 'DIRECTOR_ASSET_CHANGED')
        return {'start': start, **frames}
    spec = candidate_spec(work, identifier)
    verified_candidate(jobs, project, spec, args['sha256'])
    if 'offset' in args:
        part = jobs.playback(spec['attempt_id'], project, args['offset'])
        require(part['sha256'] == args['sha256'], 'DIRECTOR_ASSET_CHANGED')
        return part
    frames = jobs.preview_frames(args['start'], spec['attempt_id'], project)
    verified_candidate(jobs, project, spec, args['sha256'])
    return frames
