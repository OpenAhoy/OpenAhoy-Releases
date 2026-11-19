from concurrent.futures import ThreadPoolExecutor
import json
from pathlib import Path
import subprocess
import sys
from tempfile import TemporaryDirectory
from threading import Barrier
from unittest import TestCase
from unittest.mock import patch

PACKAGE = Path(__file__).resolve().parents[1] / 'plugins/wechat-ecosystem'
sys.path.insert(0, str(PACKAGE))

from wce import music_preferences
from wce.contracts import WCEError
from wce.video_protocol import MUSIC_PROVIDER, WORKSPACE, VideoRouter


class MusicPreferencesTest(TestCase):
    def setUp(self):
        temp = TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.base = Path(temp.name).resolve()
        self.root = self.base / 'private'
        self.registry = self.root / 'connections.json'
        self.first = VideoRouter(None, self.registry)
        self.second = VideoRouter(None, self.registry)

    def write(self, provider, revision, router=None):
        return (router or self.first).call(WORKSPACE, {'action': 'music_provider_save',
                                'provider': provider, 'expected_revision': revision})

    def test_unconfigured_default_without_persisting_or_contacting_provider(self):
        self.assertEqual(self.first.call(MUSIC_PROVIDER, {}), {'state':'READY','provider':'suno','revision':0})
        self.assertFalse(self.root.exists())
        self.assertEqual(self.first.call(WORKSPACE, {'action':'music_provider_read'}),
                         self.first.call(MUSIC_PROVIDER, {}))
        with self.assertRaises(WCEError):
            self.first.call(MUSIC_PROVIDER, {'project_id':'a'*32})
        self.assertEqual(self.write('suno', 0)['save_status'], 'UNCHANGED')
        self.assertFalse((self.root/'music-preferences.json').exists())

    def test_two_projects_shared_and_new_process_restores_value_in_new_cwd(self):
        for i, router in enumerate((self.first, self.second)):
            project=self.base / f'project{i}'
            project.mkdir()
            router.video_jobs.projects.sync(str(project), [], 'project-'+str(i)*32, i)
        project_state=(self.root/'project-context.json').read_bytes()
        sentinel=self.root/'prior-asset'
        sentinel.write_bytes(b'unchanged original')
        self.assertEqual(self.write('ace-music', 0)['save_status'], 'SAVED')
        self.assertEqual(self.second.call(MUSIC_PROVIDER, {})['provider'], 'ace-music')
        script = ("import json,sys; from pathlib import Path; sys.path.insert(0,sys.argv[1]); "
                  "from wce.video_protocol import VideoRouter,MUSIC_PROVIDER; "
                  "print(json.dumps(VideoRouter(None, Path(sys.argv[2])).call(MUSIC_PROVIDER, {})))")
        for work in (self.base/'project0',self.base/'project1'):
            out=subprocess.check_output([sys.executable,'-IB','-c',script,str(PACKAGE),str(self.registry)], cwd=work)
            self.assertEqual(json.loads(out), {'state':'READY','provider':'ace-music','revision':1})
        self.assertEqual(self.write('suno', 1, self.second)['provider'], 'suno')
        self.assertEqual(self.first.call(MUSIC_PROVIDER, {})['revision'], 2)
        self.assertEqual((self.root/'project-context.json').read_bytes(), project_state)
        self.assertEqual(sentinel.read_bytes(), b'unchanged original')

    def test_racing_stale_writer_reads_current_choice(self):
        self.write('ace-music', 0)
        barrier=Barrier(2)
        def save(router):
            barrier.wait(timeout=3)
            return self.write('suno', 1, router)
        with ThreadPoolExecutor(2) as pool:
            result=list(pool.map(save, (self.first,self.second)))
        self.assertEqual({row['save_status'] for row in result}, {'SAVED','STALE'})
        self.assertTrue(all(row['provider']=='suno' and row['revision']==2 for row in result))

    def test_write_failure_before_and_after_replace_returns_actual_choice(self):
        self.write('ace-music', 0)
        with patch.object(music_preferences,'atomic_write',side_effect=OSError):
            self.assertEqual(self.write('suno',1),
                             {'state':'READY','provider':'ace-music','revision':1,'save_status':'FAILED'})
        original=music_preferences.atomic_write
        def changed_then_failed(*args,**kwargs):
            original(*args,**kwargs)
            raise OSError
        with patch.object(music_preferences,'atomic_write',side_effect=changed_then_failed):
            self.assertEqual(self.write('suno',1),
                             {'state':'READY','provider':'suno','revision':2,'save_status':'FAILED'})

    def test_invalid_storage_reports_unavailable_without_provider_fallback(self):
        self.write('ace-music', 0)
        marker=self.root/'music-preferences.json'
        marker.write_text('{"schema":2,"provider":"ace-music","revision":10}')
        self.assertEqual(self.first.call(MUSIC_PROVIDER, {}), {'state':'UNAVAILABLE'})
        self.assertEqual(self.write('suno', 0), {'state':'UNAVAILABLE','save_status':'FAILED'})
        self.assertIn('"schema":2', marker.read_text())
