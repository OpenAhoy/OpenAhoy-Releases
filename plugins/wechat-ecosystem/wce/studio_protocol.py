"""Application-only transport for the registered project Studio."""
from copy import deepcopy
import json
import logging
from pathlib import Path
import re
import subprocess
from threading import Lock, Thread

from .contracts import WCEError
from .own_connection_policy import atomic_write, locked
from .project_context import ProjectStore, exact_path
from . import studio_draft
from . import studio_master_bus as master
from . import studio_production as production
from .studio_live import ACTIONS as MONITOR_ACTIONS, SCHEMA_FIELDS as MONITOR_FIELDS, LiveBus
from .studio_projects import (AUDIO_TYPES, CATALOG, IMAGE_TYPES, StudioError, chunk, cover_media, digest,
                              normalize_catalog, preview_chunk, read_json, require, studio_directory, valid_id)
from .tools import schema

TOOL = 'wce.ui.studio'
ACTION_FIELDS = {
    **MONITOR_ACTIONS,
    'start_mv': ('project', 'song', 'version', 'window'),
    'mv_binding': ('project', 'work_id'),
    'catalog': (), 'home_activity': (), 'parameters': (),
    'draft': ('project', 'song', 'version'),
    'save_draft': ('project', 'song', 'version', 'draft'),
    'start_analysis': ('project', 'song', 'version', 'revision', 'rate', 'settings'),
    'start_master': ('project', 'song', 'version', 'revision', 'analysis'),
    'monitor_media': ('project', 'song', 'version', 'analysis', 'asset', 'offset'),
    'master_status': ('project', 'song', 'version', 'job'),
    'adopt': ('project', 'song', 'version'),
    'cover': ('project', 'song', 'version', 'offset'),
    'project_cover': ('project', 'offset'),
    'song_preview': ('project', 'song', 'version', 'asset', 'offset'),
    'media': ('project', 'song', 'version', 'asset', 'offset'),
}
ID_SCHEMA = {'type': 'string', 'pattern': '^[A-Za-z0-9_][A-Za-z0-9_-]{0,95}$', 'maxLength': 96}
SCHEMA = schema({'action': {'type': 'string', 'enum': list(ACTION_FIELDS)}}, {
    **MONITOR_FIELDS,
    'window': production.SPECS['start_mv']['properties']['window'],
    'work_id': {'type': 'string', 'pattern': '^[a-f0-9]{32}$'},
    'project': ID_SCHEMA, 'song': ID_SCHEMA, 'version': ID_SCHEMA, 'asset': ID_SCHEMA, 'job': ID_SCHEMA, 'analysis': ID_SCHEMA,
    'offset': {'type': 'integer', 'minimum': 0}, 'revision': {'type': 'integer', 'minimum': 0},
    'rate': {'type': 'integer', 'minimum': 44100, 'maximum': 192000},
    'settings': {'type': 'array', 'items': {'type': 'number'}, 'minItems': 12, 'maxItems': 12},
    'draft': {'type': 'object', 'additionalProperties': True},
})
LOG = logging.getLogger(__name__)


class StudioRouter:
    def __init__(self, inner, registry):
        self.inner = inner
        self.projects = ProjectStore(registry)
        self.production = production.ProductionLibrary(self, registry)
        self.live = LiveBus(self)
        self.jobs = {}
        self.lock = Lock()

    def __getattr__(self, name):
        return getattr(self.inner, name)

    @property
    def _inline_probe_meta(self):
        return self.inner._inline_probe_meta

    @_inline_probe_meta.setter
    def _inline_probe_meta(self, value):
        self.inner._inline_probe_meta = value

    def list_tools(self):
        return self.inner.list_tools() + [production.descriptor(), {
            'name': TOOL, 'title': 'L-unify IMW',
            'description': 'App only. Edit registered local arrangements, run native Stereo Out Output Master, '
                           'audition, export and adopt within the same project. No external publishing.',
            'inputSchema': deepcopy(SCHEMA), 'annotations': {
                'readOnlyHint': False, 'destructiveHint': False, 'idempotentHint': False, 'openWorldHint': False},
            '_meta': {'ui': {'visibility': ['app']}},
        }]

    def registered(self):
        return self.projects.view()['projects']

    def project(self, row, *, production_state=None, include_recent=False):
        root = exact_path(row['root'])
        catalog_file = root / CATALOG
        # Recheck each ancestor before accepting a new catalog.
        exact_path(str(catalog_file))
        manifest = read_json(catalog_file)
        if manifest is None and not (catalog_file.parent / production.FILENAME).exists() and production_state is None:
            return root, None, []
        folder = studio_directory(root)
        state = production.ledger(folder) if production_state is None else production_state
        supplied = manifest if manifest is not None else {'schema': 1, 'songs': []}
        receipt_date = self.production.archived_at if include_recent else None
        songs = normalize_catalog(root, row['id'], production.merge_catalog(supplied, state, receipt_date),
                                  include_recent=include_recent)
        return root, folder, songs

    def with_masters(self, folder, project, song):
        key = project, song['id']
        versions = list(song['versions'])
        selection_file = folder / ('adopted-' + digest(key) + '.json')
        selection = read_json(selection_file, {})
        rows = []
        for path in folder.glob('master-*'):
            if not re.fullmatch(r'master-[0-9a-f]{32}', path.name) or path.is_symlink() or not path.is_dir():
                continue
            row = master.artifact(folder, path.name, key)
            if row:
                rows.append(row)
        for index, row in enumerate(sorted(rows, key=lambda value: value['id']), 1):
            base = '/master-file/' + '/'.join((*key, row['id'])) + '/'
            source = next((take for take in versions if take['id'] == row['key'][2]), None)
            seconds = row['frames'] / row['sample_rate']
            versions.append({'id': row['id'], 'name': f'Output Master · {index}', 'source': 'Output Master',
                             'mastered': True, 'masterAudioSha': row['files']['wav'], 'settings': row['settings'], 'delivery': row['delivery'],
                             'sampleRate': row['sample_rate'], 'sourceMedia': row['source_media'],
                             'rateBasis': row['rate_basis'], 'deliveryQC': row['qc'], 'previewAAC': base+'aac',
                             'bypassAAC': base+'bypass', 'bypassGain': row['bypass_monitor']['gain_db'],
                             'sourceVersion': row['key'][2], 'lyrics': source['lyrics'] if source else '',
                             'tracks': [{'id': 'mix', 'name': '立体声母带', 'start': 0, 'sourceIn': 0,
                                         'duration': seconds, 'url': base+'wav'}],
                             'timelineLimit': max(180, int(seconds)+1)})
            if source and source.get('cover'):
                versions[-1]['cover'] = source['cover']
        song = song | {'versions': versions, 'hasMasters': True}
        if any(v['id'] == selection.get('version') for v in versions):
            song |= {'adopted': selection['version'], 'explicit': selection['version']}
        return song

    @staticmethod
    def visible_track(track):
        values = {key: value for key, value in track.items() if key not in ('file', 'sha256')}
        if track.get('file'):
            values['mediaType'] = AUDIO_TYPES[Path(track['file']).suffix.lower()]
        return values

    @classmethod
    def visible_song(cls, song):
        from .studio_mv_audio import mix_identity
        return song | {'versions': [
            {key: value for key, value in version.items() if key != 'coverMedia'}
            | {'mixIdentity': mix_identity(version), 'tracks': [cls.visible_track(track) for track in version['tracks']]}
            for version in song['versions']]}

    def catalog(self):
        result = []
        for row in self.registered():
            record = {'id': row['id'], 'name': row['name'], 'songs': []}
            try:
                root, folder, songs = self.project(row, include_recent=True)
                if folder:
                    record['songs'] = [self.visible_song(self.with_masters(folder, row['id'], song)) for song in songs]
                    if cover_media(root, read_json(root / CATALOG, {}).get('cover')):
                        record['cover'] = '/project-cover/' + row['id']
            except (WCEError, ValueError, OSError):
                record['state'] = 'studio_catalog_unavailable'
            result.append(record)
        return {'projects': result}

    def bound(self, key, *, include_masters=False):
        row = next((item for item in self.registered() if item['id'] == key[0]), None)
        require(row is not None, 'studio_project_not_registered', 404)
        root, folder, songs = self.project(row)
        song = next((item for item in songs if item['id'] == key[1]), None)
        require(song is not None, 'studio_song_unavailable', 404)
        if include_masters or key[2].startswith('master-'):
            song = self.with_masters(folder, key[0], song)
        version = next((item for item in song['versions'] if item['id'] == key[2]), None)
        require(version is not None, 'studio_version_unavailable', 404)
        return root, folder, song, version

    def start_job(self, key, args, root, folder, version):
        require(not version.get('mastered'), 'studio_original_required')
        draft = studio_draft.read_draft(folder, key)
        revision = args['revision']
        require(draft['revision'] == revision, 'draft_changed', 409)
        analyze = args['action'] == 'start_analysis'
        version_digest = digest(version)
        if analyze:
            values = master.checked_settings(master.parameters(), args['settings'])
            master.choose(version['masterRate'], args['rate'])
            renderer = master.analyze
            processing = (values, args['rate'])
        else:
            renderer = master.build
            processing = (self.analysis(folder, key, args['analysis']),)
        # The version and draft revision identify the exact project intent.
        job = 'job-' + digest([key, args, version_digest, master.engine_identity()])[:32]
        with self.lock:
            prior = self.jobs.get(job)
            if prior and prior['state'] != 'failed':
                return prior | {'job': job}
            require(not any(value['state'] == 'running' for value in self.jobs.values()), 'studio_master_busy', 409)
            if len(self.jobs) >= 64:
                self.jobs.pop(next(iter(self.jobs)))
            self.jobs[job] = {'key': key, 'state': 'running'}

        def current():
            latest_root, _, _, latest = self.bound(key)
            return latest_root == root and digest(latest) == version_digest

        def run():
            try:
                receipt = renderer(root, folder, key, version, draft, revision, *processing, current)
                value = {'key': key, 'state': 'ready', 'id': receipt['id']}
                if analyze:
                    value.update(frames=receipt['frames'], sampleRate=receipt['sample_rate'])
            except WCEError as problem:
                value = {'key': key, 'state': 'failed', 'error': str(problem)}
            except (OSError, ValueError, RuntimeError, KeyError, subprocess.SubprocessError) as problem:
                LOG.warning('Studio master failed (%s)', type(problem).__name__)
                value = {'key': key, 'state': 'failed', 'error': 'studio_render_failed'}
            with self.lock:
                self.jobs[job] = value

        Thread(target=run, name='studio-master-render', daemon=True).start()
        return {'job': job, 'state': 'running'}

    @staticmethod
    def analysis(folder, key, identifier):
        require(type(identifier) is str and re.fullmatch(r'analysis-[0-9a-f]{32}', identifier),
                'studio_analysis_unavailable', 404)
        receipt = master.artifact(folder, identifier, key)
        require(receipt is not None and receipt['key'] == list(key), 'studio_analysis_unavailable', 404)
        return receipt

    def call(self, name, args):
        if name == production.TOOL:
            try:
                return self.production.dispatch(args)
            except StudioError as error:
                return {'error': str(error), 'status': error.status}
            except WCEError as error:
                return {'error': str(error), 'status': 422}
            except (ValueError, TypeError, KeyError, OSError, subprocess.SubprocessError):
                return {'error': 'music_production_unavailable', 'status': 422}
        if name != TOOL:
            return self.inner.call(name, args)
        try:
            return self.dispatch(args)
        except StudioError as error:
            return {'error': str(error), 'status': error.status}
        except (WCEError, ValueError, TypeError, KeyError, OSError, subprocess.SubprocessError):
            return {'error': 'studio_action_unavailable', 'status': 422}

    def dispatch(self, args):
        action = args.get('action')
        if action in MONITOR_ACTIONS:
            return self.live.dispatch(args)
        require(action in ACTION_FIELDS and set(args) == {'action', *ACTION_FIELDS[action]})
        if action in ('start_mv', 'mv_binding'):
            return self.production.dispatch(args)
        if action == 'catalog':
            return self.catalog()
        if action == 'home_activity':
            from .home_overview import recent_activity
            return recent_activity(self, self.inner.director, self.inner.video_jobs)
        if action == 'parameters':
            return {'parameters': master.parameters()}
        if action == 'project_cover':
            project = next((row for row in self.registered() if row['id'] == args['project']), None)
            require(project is not None, 'studio_project_not_registered', 404)
            root = exact_path(project['root'])
            cover = cover_media(root, read_json(root / CATALOG, {}).get('cover'))
            require(cover is not None, 'studio_cover_unavailable', 404)
            return chunk(root, cover['file'], cover['sha256'], args['offset'], IMAGE_TYPES)
        key = tuple(args[field] for field in ('project','song','version'))
        require(all(map(valid_id, key)))
        root, folder, _, version = self.bound(key)
        if action == 'cover':
            cover = version.get('coverMedia')
            require(cover is not None, 'studio_cover_unavailable', 404)
            return chunk(root, cover['file'], cover['sha256'], args['offset'], IMAGE_TYPES)
        if action == 'song_preview':
            tracks = version['tracks']
            require(len(tracks) == 1 and not version.get('mastered'), 'studio_media_invalid', 404)
            track, = tracks
            require(track['id'] == args['asset'] and track['start'] == track['sourceIn'] == 0,
                    'studio_media_invalid', 404)
            return preview_chunk(root, track, args['offset'])
        if action == 'draft':
            return studio_draft.read_draft(folder, key)
        if action == 'save_draft':
            value = args['draft']
            require(type(value) is dict and len(json.dumps(value)) <= 1024 * 1024)
            return studio_draft.save(folder, key, version, value)
        if action in ('start_analysis', 'start_master'):
            require(type(args['revision']) is int and (action != 'start_analysis' or type(args['rate']) is int))
            return self.start_job(key, args, root, folder, version)
        if action == 'monitor_media':
            row = self.analysis(folder, key, args['analysis'])
            kind = args['asset']
            require(kind in master.MONITOR and kind in row.get('files', {}), 'studio_media_invalid', 404)
            relative = str((folder / row['id'] / master.MONITOR[kind]).relative_to(root))
            return chunk(root, relative, row['files'][kind], args['offset'])
        if action == 'master_status':
            require(valid_id(args['job']))
            with self.lock:
                row = self.jobs.get(args['job'])
                require(row is not None and row['key'] == key, 'studio_job_unavailable', 404)
                return {field: value for field, value in row.items() if field != 'key'}
        if action == 'adopt':
            if version.get('mastered'):
                row = master.artifact(folder, key[2], key)
                require(row is not None, 'studio_version_unavailable', 404)
                # Confirm this exact candidate still has both verified deliverables.
                for kind in ('wav','aac'):
                    master.media_pin(root, str((folder / key[2] / master.MEDIA[kind]).relative_to(root)),
                                               row['files'][kind])
            with locked(folder / 'state.lock'):
                atomic_write(folder / ('adopted-' + digest(key[:2]) + '.json'), {'version': key[2]})
            return {'project': key[0], 'song': key[1], 'adopted': key[2]}
        if action == 'media':
            if version.get('mastered'):
                kind = args['asset']
                require(kind in master.MEDIA, 'studio_media_invalid', 404)
                receipt = master.artifact(folder, key[2], key)
                relative = str((folder / key[2] / master.MEDIA[kind]).relative_to(root))
                return chunk(root, relative, receipt['files'][kind], args['offset'])
            source = next((t for t in version['tracks'] if t['id'] == args['asset']), None)
            require(source is not None, 'studio_media_invalid', 404)
            return chunk(root, source['file'], source['sha256'], args['offset'])
        raise StudioError('invalid_studio_request', 400)
