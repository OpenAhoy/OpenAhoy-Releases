"""Read-only, path-free projection of the existing project media receipts."""
from math import isfinite
from time import time

from .contracts import WCEError

FAILED = {'FAILED', 'SUBMIT_REJECTED', 'NOT_SENT', 'CANCELLED', 'EXPIRED', 'UNAVAILABLE'}
PENDING = {'SUBMIT_UNKNOWN', 'SAVE_PENDING', 'RESULT_RECEIVED'}
MEDIA_FIELDS = ('sha256', 'bytes', 'seconds', 'width', 'height', 'frames',
                'frame_count', 'audio_tracks', 'mime')


def _asset(value):
    return {key: value[key] for key in MEDIA_FIELDS if key in value}


def _row(family, project, receipt, title, asset, **fields):
    return {'family': family, 'kind': family, 'project': project['id'],
            'project_label': project['name'], 'attempt': receipt['generation_attempt_id'],
            'title': title, 'state': receipt['state'], 'created_at': receipt['created_at'],
            'updated_at': receipt.get('updated_at', receipt['created_at']),
            'asset': _asset(asset), **fields}


def _video_rows(videos, audio, project, receipts):
    result = videos.project_history(project, receipts, monitor=True)
    library = {row['generation_attempt_id']: row for row in result.get('library', [])}
    for receipt in result['versions']:
        attempt = receipt['generation_attempt_id']
        entry = library.get(attempt, {})
        if entry.get('trashed'):
            continue
        attribution = audio.media.account('video', attempt, project['id'])
        row = _row('video', project, receipt, attribution.get('title') or entry.get('name') or attempt,
                   receipt.get('asset', {}), account_label=attribution.get('account_label'), account_key=attribution.get('account_key'),
                   model=receipt['model'], provider=receipt.get('provider'),
                   provider_site=receipt.get('provider_site'), usage=receipt.get('usage'),
                   list_price_cny=receipt.get('list_price_cny'), list_price_usd=receipt.get('list_price_usd'),
                   original_task=receipt.get('provider_task_id'), diagnostic=receipt.get('monitor_diagnostic'))
        if entry.get('state') == 'UNAVAILABLE':
            row.update(state='UNAVAILABLE', asset={})
        parent = _ref('video', project['id'], receipt.get('source_attempt_id'), receipt.get('source_sha256'))
        yield row, parent, None, {}


def _gif_rows(gifs, audio, project, receipts):
    for raw, active in receipts:
        receipt = gifs.project_row(raw, active=active, project=project)
        attempt = receipt['generation_attempt_id']
        attribution = audio.media.account('gif', attempt, project['id'])
        row = _row('gif', project, receipt, attribution.get('title') or attempt, receipt.get('asset', {}),
                   account_label=attribution.get('account_label'), account_key=attribution.get('account_key'), model=receipt.get('model'), provider='OpenAI',
                   original_task=receipt.get('provider_request_id'), diagnostic=(receipt.get('diagnostic') or {}).get('code'))
        if row['state'] == 'ASSET_READY' and not gifs.source_present(attempt, row['asset']['bytes']):
            row.update(state='UNAVAILABLE', asset={})
        yield row, None, None, {}


def _audio_rows(audio, project, receipts):
    for receipt in sorted(receipts, key=lambda row: row.get('created_at', 0), reverse=True):
        attempt = receipt['attempt_id']
        asset = _asset(receipt)
        row = _row('audio', project, {**receipt, 'generation_attempt_id': attempt}, receipt['title'], asset,
                   provider=receipt.get('provider'), account_label=receipt.get('account_label'),
                   account_key=audio.media.account('audio', attempt, project['id']).get('account_key'))
        row['project_label'] = receipt.get('project_label') or row['project_label']
        if row['state'] == 'ASSET_READY' and not audio.source_present(receipt, project=project):
            row.update(state='UNAVAILABLE', asset={})
        if receipt['kind'] != 'song':
            row.update(kind='video', composition=receipt['kind'])
        parent = _ref('video', receipt.get('video_project_id') or project['id'],
                      receipt.get('video_attempt_id'), receipt.get('video_sha256'))
        track = _ref('audio', receipt.get('song_project_id') or project['id'],
                     receipt.get('song_attempt_id'), receipt.get('song_sha256'))
        yield row, parent, track, receipt.get('settings') or {}


def _ref(family, project, attempt, digest):
    if attempt and digest:
        return (family, project, attempt, digest)
    return None


def _key(row):
    return (row['family'], row['project'], row['attempt'])


def _link(row):
    return {name: row[name] for name in ('family', 'project', 'attempt', 'title', 'project_label')}


def _interval(settings, parent, track):
    values = (settings.get('video_start'), settings.get('music_offset'),
              parent.get('asset', {}).get('seconds'), track.get('asset', {}).get('seconds'))
    if all(type(value) in (int, float) and isfinite(value) and value >= 0 for value in values):
        start, offset, video_seconds, song_seconds = values
        duration = min(video_seconds - start, song_seconds - offset)
        if duration > 0:
            return {'video_start': start, 'music_offset': offset, 'seconds': duration}
    return {}


def _project_receipts(projects, rows, project_id):
    groups = {project['id']: [] for project in projects}
    for row in rows:
        if row is not None:
            group = groups.get(project_id(row))
            if group is not None:
                group.append(row)
    return groups


def collect(videos, gifs, audio, *, include_scope=False):
    projects = videos.projects.view()['projects']
    receipts = []
    unavailable = []
    registered = {project['id'] for project in projects}
    for family, read, scope, load in (
        ('video', videos.receipts, lambda row: row['request']['project_id'],
         lambda project, rows: _video_rows(videos, audio, project, rows)),
        ('gif', lambda: gifs.monitor_receipts(registered), lambda row: row[0]['project_id'],
         lambda project, rows: _gif_rows(gifs, audio, project, rows)),
        ('audio', audio.receipts, lambda row: row['project_id'],
         lambda project, rows: _audio_rows(audio, project, rows)),
    ):
        directory = projects
        try:
            if family == 'audio':
                directory = audio.library_projects(projects)
            groups = _project_receipts(directory, read(), scope) if directory else {}
        except (WCEError, OSError, KeyError, TypeError):
            unavailable.extend({'family': family, 'project_label': row['name'], 'project_id': row['id']} for row in directory)
            continue
        for project in directory:
            try:
                receipts.extend(list(load(project, groups[project['id']])))
            except (WCEError, OSError, KeyError, TypeError):
                unavailable.append({'family': family, 'project_label': project['name'], 'project_id': project['id']})

    index = {(*_key(row), row['asset']['sha256']): row for row, *_ in receipts
             if row['state'] == 'ASSET_READY' and row['asset'].get('sha256')}
    parents = {}
    for row, parent_ref, track_ref, settings in receipts:
        parent = index.get(parent_ref)
        track = index.get(track_ref)
        if parent:
            parents[_key(row)] = _key(parent)
        if track_ref and row['state'] == 'ASSET_READY':
            row['soundtrack'] = {'attempt': track_ref[2]}
            if track and track['kind'] == 'audio':
                relation = _interval(settings, parent or {}, track)
                row['soundtrack'].update(relation, target=_link(track), provider=track.get('provider'))
                track.setdefault('used_in', []).append({**_link(row), **relation})
        if row.get('composition') == 'soundtrack' and type(settings.get('keep_original')) is bool:
            if not settings['keep_original']:
                row['original_audio'] = 'excluded'
            elif parent and 'audio_tracks' in parent['asset']:
                row['original_audio'] = 'retained' if parent['asset']['audio_tracks'] else 'silent'

    def lineage(key):
        seen = set()
        while key in parents and key not in seen:
            seen.add(key)
            key = parents[key]
        return min(seen) if key in seen else key

    versions = {}
    rows = [row for row, *_ in receipts]
    for row in rows:
        state = row['state']
        row['group'] = ('complete' if state == 'ASSET_READY' else 'failed' if state in FAILED else
                        'pending' if state in PENDING else 'running' if state in ('SUBMITTED', 'PROCESSING', 'QUEUED', 'RUNNING')
                        else 'pending')
        if row['kind'] == 'video':
            versions.setdefault(lineage(_key(row)), []).append(row)
    for group in versions.values():
        if len(group) > 1:
            group.sort(key=lambda row: (row['created_at'], _key(row)))
            for number, row in enumerate(group, 1):
                row['version'] = number
                row['versions'] = [{**_link(other), 'version': index} for index, other in enumerate(group, 1)]
    rows.sort(key=lambda row: (row['group'] in ('pending', 'failed'), row['group'] == 'running',
                               row['updated_at'], _key(row)), reverse=True)
    if not include_scope:
        for item in unavailable:
            item.pop('project_id', None)
        for row in rows:
            row.pop('account_key', None)
    return {'rows': rows, 'read_at': time(), 'unavailable': unavailable}
