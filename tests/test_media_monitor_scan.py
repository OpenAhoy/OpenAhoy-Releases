"""Request-local scanning for the unified media monitor."""
from collections import Counter
import json
from pathlib import Path
import sys
from tempfile import TemporaryDirectory
from types import SimpleNamespace
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'plugins/wechat-ecosystem'))
from wce import audio_jobs, media_monitor, openai_gif_jobs, video_jobs
from wce.own_connection_policy import locked


class MonitorScan(unittest.TestCase):
    def setUp(self):
        scratch = TemporaryDirectory()
        self.addCleanup(scratch.cleanup)
        self.root = Path(scratch.name).resolve()
        self.projects = [{'id': str(i)*32, 'name': f'Fixture {i}', 'root': str(self.root)}
                         for i in (1, 2)]
        self.videos = video_jobs.Jobs(self.root / 'connections.json', api=object(), tokenhex=object())
        self.videos.projects = SimpleNamespace(view=lambda: {'projects': self.projects}, root=self.root)
        self.gifs = openai_gif_jobs.GifJobs(self.videos, api=object())
        self.audio = audio_jobs.AudioJobs(self.videos)
        for reader in (self.videos, self.gifs, self.audio):
            reader.root.mkdir(mode=0o700)

    def write(self, path, row):
        path.write_text(json.dumps(row))
        path.chmod(0o600)

    def video(self, attempt, project, **options):
        receipt, asset = self.videos._paths(attempt)
        asset.write_bytes(b'fixture')
        asset.chmod(0o600)
        self.write(receipt, {'generation_attempt_id': attempt, 'state': 'ASSET_READY', 'created_at': 1,
                             'request': {'project_id': project, 'model': video_jobs.MODEL, **options},
                             'asset': {'sha256': 'a'*64, 'seconds': 5, 'bytes': 7, 'audio_tracks': 1}})

    def test_scans_once_preserving_links_scope_and_claim(self):
        primary, other = (project['id'] for project in self.projects)
        self.video('first', primary)
        self.video('second', primary, source_attempt_id='first', source_sha256='a'*64)
        self.video('unregistered', '3'*32)
        receipt, _, lock = self.gifs.paths('gif-fixture')
        common = {'generation_attempt_id': 'gif-fixture', 'project_id': other,
                  'model': 'fixture', 'created_at': 4}
        self.write(receipt, common | {'state': 'FAILED'})
        self.write(receipt.with_suffix('.claim'), common | {'state': 'SUBMIT_UNKNOWN'})
        source = self.root / 'fixture-audio'
        source.write_bytes(b'fixture')
        source.chmod(0o600)
        self.write(self.audio.receipt('audio-fixture'),
                   {'attempt_id':'audio-fixture', 'project_id':other, 'title':'Fixture song',
                    'state':'ASSET_READY', 'kind':'song', 'file':source.name, 'created_at':3,
                    'bytes':7, 'seconds':2, 'sha256':'b'*64})
        self.write(self.audio.receipt('mix-fixture'),
                   {'attempt_id':'mix-fixture', 'project_id':primary, 'title':'Fixture mix',
                    'state':'ASSET_READY', 'kind':'soundtrack', 'file':source.name, 'created_at':3,
                    'bytes':7, 'seconds':2,'sha256':'c'*64,
                    'video_project_id':primary, 'video_attempt_id':'first', 'video_sha256':'a'*64,
                    'song_project_id':other, 'song_attempt_id':'audio-fixture','song_sha256':'b'*64,
                    'settings':{'video_start':0,'music_offset':0,'keep_original':False}})
        with locked(lock), patch.object(self.videos,'receipts',wraps=self.videos.receipts) as videos, \
                patch.object(self.gifs,'monitor_receipts',wraps=self.gifs.monitor_receipts) as gifs, \
                patch.object(self.audio,'receipts',wraps=self.audio.receipts) as audio:
            response=media_monitor.collect(self.videos,self.gifs,self.audio)
            videos.assert_called_once_with()
            gifs.assert_called_once_with({primary, other})
            audio.assert_called_once_with()
        self.assertEqual(response['unavailable'],[])
        values={row['attempt']:row for row in response['rows']}
        self.assertNotIn('unregistered',values)
        self.assertEqual(values['gif-fixture']['state'],'PROCESSING')
        self.assertEqual(values['gif-fixture']['project'],other)
        self.assertEqual(values['audio-fixture']['state'],'ASSET_READY')
        self.assertEqual(values['mix-fixture']['soundtrack']['target']['attempt'],'audio-fixture')
        self.assertEqual(values['mix-fixture']['original_audio'],'excluded')
        self.assertEqual({v['attempt'] for v in values['second']['versions']},{'first','second','mix-fixture'})
        self.assertFalse(any('file' in row or 'path' in row for row in values.values()))
        self.assertEqual(self.gifs.status('gif-fixture',primary),{'state':'NOT_FOUND'})

    def test_partial_gif_damage_keeps_healthy_registered_project(self):
        primary, other = (project['id'] for project in self.projects)
        for attempt, project in [('damaged', primary), ('stale', '3'*32), ('healthy', other)]:
            receipt, _, lock = self.gifs.paths(attempt)
            lock.touch(mode=0o600)
            row = {'generation_attempt_id':attempt, 'project_id':project, 'created_at':1}
            if attempt == 'healthy':
                row['state'] = 'FAILED'
            self.write(receipt, row)
        response = media_monitor.collect(self.videos,self.gifs,self.audio)
        self.assertEqual([row['attempt'] for row in response['rows']],['healthy'])
        self.assertEqual(response['unavailable'],[{'family':'gif','project_label':'Fixture 1'}])

    def test_audio_relation_keeps_creation_order_over_filename_order(self):
        primary = self.projects[0]['id']
        shared = {'project_id':primary, 'state':'ASSET_READY', 'file':'audio-file',
                  'kind':'song', 'title':'Fixture audio', 'bytes':1,'seconds':2}
        (self.root/'audio-file').write_bytes(b'a')
        (self.root/'audio-file').chmod(0o600)
        self.write(self.audio.receipt('music'), shared | {'attempt_id':'music','created_at':0,'sha256':'b'*64})
        for attempt, at in [('mix-z',1),('mix-a',2)]:
            self.write(self.audio.receipt(attempt), shared | {'attempt_id':attempt,'created_at':at,'sha256':'c'*64,
                  'kind':'soundtrack','song_attempt_id':'music','song_sha256':'b'*64,'song_project_id':primary})
        values = {row['attempt']:row for row in media_monitor.collect(self.videos,self.gifs,self.audio)['rows']}
        self.assertEqual([entry['attempt'] for entry in values['music']['used_in']],['mix-a','mix-z'])

    def test_snapshot_failure_isolated_by_family(self):
        self.video('first',self.projects[0]['id'])
        (self.audio.root/'bad.json').write_text('invalid')
        (self.audio.root/'bad.json').chmod(0o600)
        response=media_monitor.collect(self.videos,self.gifs,self.audio)
        self.assertEqual([row['attempt'] for row in response['rows']],['first'])
        self.assertEqual(response['unavailable'],
                         [{'family':'audio','project_label':p['name']} for p in self.projects])
