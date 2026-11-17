"""Offline regressions bound to the published package layout."""
from contextlib import nullcontext
from copy import deepcopy
from hashlib import sha256
import json
from pathlib import Path
import sys
from tempfile import TemporaryDirectory
import time
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

ROOT = Path(__file__).resolve().parents[1]
# The tests may intentionally run against a separately extracted baseline.
sys.path.append(str(ROOT / 'plugins/wechat-ecosystem'))

from wce import ordinary_publication as ordinary
from wce.audio_jobs import AudioJobs, invoke
from wce.contracts import Secret, WCEError
from wce.media_monitor import collect
from wce.openai_gif_inspect import gif_facts
from wce.openai_gif_jobs import GifJobs
from wce.own_connection_policy import atomic_write, locked
from wce.own_update_install import UpdateInstaller
from wce.project_context import ProjectStore
from wce.video_jobs import Jobs, MODEL, PROMO_DIR
from wce.x_api import XResponseUnknown
from wce.x_platform import XPlatform
from wce.x_schedule import Schedules
from wce.xhs_platform import XHSPlatform


def hexdigest(path):
    return sha256(path.read_bytes()).hexdigest()


class Review(unittest.TestCase):
    def setUp(self):
        fixture = TemporaryDirectory()
        self.addCleanup(fixture.cleanup)
        self.root = Path(fixture.name)

    def test_02_publication_local_refusal_leaves_original_reusable(self):
        row = {'submit_count': 0, 'state': 'NOT_ATTEMPTED', 'intent_handle': 'original',
               'reference': 'original-media', 'article_count': 1}
        def persist(path, value):
            row.update(deepcopy(value))
        service = Mock()
        service.policy = SimpleNamespace(root=self.root, data={'connection_id': 'local'})
        service.tokens.get.return_value = SimpleNamespace(token=Secret('test-only-token'),
                                                          wall_deadline=time.time()+60)
        service.tokens.valid.side_effect = [False, True]
        sender = service.workflow.sender.send
        sender.side_effect = OSError('response lost after send')
        with (patch.object(ordinary, '_anchor', return_value=self.root),
              patch.object(ordinary, '_locate', side_effect=lambda *_:(None, deepcopy(row))),
              patch.object(ordinary, '_initialize_dispatch'), patch.object(ordinary, '_coordination'),
              patch.object(ordinary, 'locked', side_effect=lambda *a, **k:nullcontext()),
              patch.object(ordinary, '_write', side_effect=persist),
              patch.object(ordinary, 'stable_account', return_value='fixture'),
              patch.object(ordinary, 'DraftMediaID'), patch.object(ordinary, 'encode')):
            args = (service, 'own.publications.current.dispatch',
                    {'connection_id':'local','intent_handle':'original'}, self.root, time.monotonic()+30)
            with self.assertRaisesRegex(WCEError, 'OWN_TOKEN_UNAVAILABLE'):
                ordinary.execute(*args)
            self.assertEqual(row['submit_count'], 0)
            sender.assert_not_called()
            with self.assertRaisesRegex(WCEError, 'RESULT_UNKNOWN'):
                ordinary.execute(*args)
            self.assertEqual(row['submit_count'], 1)
            self.assertEqual(row['state'], 'UNKNOWN')
            sender.assert_called_once()

    def test_03_x_rate_limit_retains_grant_and_unknown_freezes_it(self):
        now = 1000
        api, keychain = Mock(), Mock()
        keychain.load.return_value = Secret(json.dumps({'access_token':'fixture-original','refresh_token':'fixture-refresh'}))
        platform = XPlatform(root=self.root, api=api, keychain=keychain, clock=lambda:now)
        connection = {'state':'BOUND','expires_at':now,'credential_scope':'fixture-scope'}
        value = {'client_id':'fixture-app','connections':{'x-123':connection}}
        observed = []
        with patch.object(platform, '_save', side_effect=lambda data: observed.append(deepcopy(data))):
            api.refresh.side_effect=[WCEError('X_HTTP_429'), XResponseUnknown('TIMEOUT')]
            with self.assertRaisesRegex(WCEError,'X_HTTP_429'):
                platform._access(value,'x-123')
            self.assertEqual(connection['state'],'BOUND')
            self.assertEqual(connection['expires_at'],now)
            keychain.put.assert_not_called()
            with self.assertRaises(XResponseUnknown):
                platform._access(value,'x-123')
            self.assertEqual(connection['state'],'REFRESH_UNKNOWN')
            self.assertEqual([r['connections']['x-123']['state'] for r in observed],
                             ['REFRESH_UNKNOWN','BOUND','REFRESH_UNKNOWN'])
            with self.assertRaisesRegex(WCEError,'X_REAUTHORIZATION_REQUIRED'):
                platform._access(value,'x-123')
            self.assertEqual(api.refresh.call_count,2)

    def test_04_schedule_proven_no_change_releases_only_original_request(self):
        schedules = Schedules(ProjectStore(self.root/'connections.json'))
        account = 'x-123'
        cfg = {'mode':'daily','weekdays':[],'times':['11:42'],'timezone':'Asia/Shanghai','once_at':''}
        request = 'project-'+'a'*32
        schedules.request(account,'enable',cfg,request,0)
        revision = schedules.read(account)['revision']
        schedules.host_result(account,request,'UNKNOWN',[],'timeout',revision)
        revision = schedules.read(account)['revision']
        self.assertIsNotNone(schedules.read(account)['pending'])
        schedules.host_result(account,request,'NO_CHANGE',[],'official request rejected before changes',revision)
        self.assertIsNone(schedules.read(account)['pending'])
        self.assertEqual(schedules.read(account)['config'],cfg)
        next_request = 'project-'+'b'*32
        schedules.request(account,'enable',cfg,next_request,schedules.read(account)['revision'])
        task = {'id':'fixture','slot':'11:42','status':'ACTIVE','kind':'heartbeat',
                'thread_id':'12345678-1234-1234-1234-123456789abc','next_run_at':''}
        schedules.host_result(account,next_request,'PENDING',[task],'first change recorded',schedules.read(account)['revision'])
        with self.assertRaises(WCEError):
            schedules.host_result(account,next_request,'NO_CHANGE',[],'claimed no change',schedules.read(account)['revision'])
        self.assertEqual(schedules.read(account)['pending']['id'],next_request)
        self.assertEqual(schedules.read(account)['tasks'],[task])

    def test_05_xhs_original_id_survives_detail_fault_and_restart(self):
        candidate = '1'*24
        account = {'id':'2'*24}
        browser = Mock()
        browser.call.side_effect = [{'state':'RESOLVED','note_id':candidate},
                                    WCEError('XHS_NOTE_TEMPORARILY_UNAVAILABLE')]
        platform = XHSPlatform(root=self.root)
        path=self.root/'note.json'
        atomic_write(path,{'connection_id':'fixture','phase':'SUBMIT_STARTED','state':'UNKNOWN',
                           'input':{'title':'Fixture','body':'Text','topics':[]},'images':[]},maximum=None)
        with (patch.object(platform,'_path',return_value=path),
              patch.object(platform,'_session',return_value=nullcontext((account,browser,self.root))),
              patch.object(platform,'_receipt',side_effect=lambda row:row)):
            with self.assertRaisesRegex(WCEError,'TEMPORARILY_UNAVAILABLE'):
                platform.status('fixture','original',readback=True)
            self.assertEqual(json.loads(path.read_text())['note_id'],candidate)
            browser.call.side_effect = [{'id':candidate,'owner_id':account['id'],'title':'Fixture',
                                         'body':'wrong','images':[]}]
            with self.assertRaisesRegex(WCEError,'XHS_READBACK_MISMATCH'):
                platform.status('fixture','original',readback=True)
            self.assertEqual(json.loads(path.read_text())['note_id'],candidate)
            self.assertEqual([call.args[0] for call in browser.call.call_args_list],['RESOLVE','NOTE','NOTE'])

    def test_06_upgrade_status_recovers_orphan_and_archived_request(self):
        installer=UpdateInstaller('0.6.80',self.root/'connections.json')
        request='a'*32
        self.assertEqual(installer.status(request)['state'],'START_NOT_RECORDED')
        installer.root.mkdir(mode=0o700)
        worker=installer.root/'worker.lock'
        worker.touch(mode=0o600)
        row={'state':'FAILED','version':'0.6.81','revision':'b'*40,'request_id':request}
        atomic_write(installer.root/'status.json',row)
        self.assertEqual(installer.status(request)['state'],'FAILED')
        reference=installer.root/'status.json'
        raw=reference.read_bytes()
        (installer.root/('retained-'+sha256(raw).hexdigest()+'.json')).write_bytes(raw)
        (installer.root/('retained-'+sha256(raw).hexdigest()+'.json')).chmod(0o600)
        atomic_write(reference,{**row,'request_id':'c'*32})
        with locked(worker,existing=True):
            self.assertEqual(installer.status(request)['state'],'START_UNCONFIRMED')
        self.assertEqual(installer.status(request)['state'],'START_ARCHIVED')
        self.assertEqual(installer.status('d'*32)['state'],'START_NOT_RECORDED')

    def test_06_known_rollback_keeps_previous_receipt(self):
        from wce import own_update_install as module
        installer=UpdateInstaller('0.6.80',self.root/'connections.json',run=Mock(),readback=Mock())
        home=self.root/'.codex'
        package=home/'plugins/cache/fixture/wechat-ecosystem/0.6.80'
        package.mkdir(parents=True)
        (package/'package-manifest.json').write_text('{}')
        selector='wechat-ecosystem@fixture'
        installer.run.return_value={'installed':[{'name':'wechat-ecosystem','pluginId':selector,'version':'0.6.80','enabled':True}]}
        installer.root.mkdir(mode=0o700)
        (installer.root/'worker.lock').touch(mode=0o600)
        prior={'state':'INSTALLED_RELOAD_REQUIRED','version':'0.6.81','request_id':'e'*32}
        atomic_write(installer.root/'status.json',prior)
        raw=(installer.root/'status.json').read_bytes()
        with (patch.object(module.Path,'home',return_value=self.root),
              patch.object(module,'read_market',return_value=(('[plugins."'+selector+'"]\nenabled=true\n').encode(),None)),
              patch.object(module,'__file__',str(package/'wce/own_update_install.py'))):
            status=installer.status()
        self.assertEqual(status['state'],'LOADED')
        self.assertEqual(status['version'],'0.6.80')
        self.assertEqual(status['history']['version'],'0.6.81')
        self.assertEqual((installer.root/'status.json').read_bytes(),raw)
        installer.readback.assert_called_once()

    def video_fixture(self):
        owner=self.root/'owner'
        owner.mkdir(mode=0o700)
        project=self.root/'project'
        project.mkdir(mode=0o700)
        jobs=Jobs(owner/'connections.json')
        project_id='a'*32
        jobs.projects.view=lambda:{'projects':[{'id':project_id,'name':'Fixture','root':str(project)}]}
        jobs._directory()
        return jobs, project_id, project

    def video_receipt(self,jobs,project_id,attempt,*,state='ASSET_READY',raw=b'fixture-video'):
        receipt,file=jobs._paths(attempt)
        row={'state':state,'generation_attempt_id':attempt,'created_at':time.time(),
             'provider_task_id':'fixture-task',
             'request':{'model':MODEL,'project_id':project_id,'mode':'frames','duration':5,'resolution':'720p'}}
        if state=='ASSET_READY':
            file.write_bytes(raw);file.chmod(0o600)
            row['asset']={'sha256':hexdigest(file),'bytes':len(raw),'seconds':5}
        atomic_write(receipt,row)
        return receipt,file,row

    def test_08_alternating_video_and_mix_fragments_validate_each_file_once(self):
        jobs,pid,project=self.video_fixture()
        _,file,_=self.video_receipt(jobs,pid,'one')
        self.video_receipt(jobs,pid,'two',raw=b'second-video')
        with patch.object(jobs,'_asset_digest',wraps=jobs._asset_digest) as verify:
            for attempt in ('one','two')*5:
                jobs.playback(attempt,pid,0)
            self.assertEqual(verify.call_count,2)
            file.write_bytes(b'changed-video')
            with self.assertRaisesRegex(WCEError,'VIDEO_ASSET_CHANGED'):
                jobs.playback('one',pid,0)
        audio=AudioJobs(jobs);audio.init()
        for name in ('mix-one','mix-two'):
            file=project/(name+'.mp4')
            file.write_bytes(name.encode());file.chmod(0o600)
            atomic_write(audio.receipt(name), {'attempt_id':name,'project_id':pid,'state':'ASSET_READY',
                'kind':'soundtrack','file':file.name,'bytes':file.stat().st_size,'sha256':hexdigest(file)})
        with patch('wce.audio_jobs.sha256', wraps=sha256) as verify:
            for attempt in ('mix-one','mix-two')*5:
                audio.chunk(attempt,pid,0)
            self.assertEqual(verify.call_count,2)

    def test_10_video_diagnostics_persist_and_local_asset_wins(self):
        jobs,pid,_=self.video_fixture()
        _,_,row=self.video_receipt(jobs,pid,'original',state='RUNNING')
        with patch.object(jobs,'_query_task',side_effect=WCEError('VIDEO_QUERY_FAILED')):
            self.assertEqual(jobs.status('original',pid,True)['query_error'],'VIDEO_QUERY_FAILED')
        self.assertEqual(jobs.history(pid,monitor=True)['versions'][0]['monitor_diagnostic'],'VIDEO_QUERY_FAILED')
        with (patch.object(jobs,'_query_task',return_value=(Mock(),{'status':'succeeded','content':{}})),
              patch.object(jobs,'_save',side_effect=WCEError('VIDEO_ASSET_SAVE_FAILED'))):
            self.assertEqual(jobs.status('original',pid,True)['download_error'],'VIDEO_ASSET_SAVE_FAILED')
        self.assertEqual(jobs.history(pid,monitor=True)['versions'][0]['monitor_diagnostic'],'VIDEO_ASSET_SAVE_FAILED')
        self.video_receipt(jobs,pid,'ready')
        with patch.object(jobs,'_query_task',side_effect=AssertionError('provider query')):
            self.assertEqual(jobs.monitor_task('ready',pid)['state'],'ASSET_READY')

    def test_11_attached_picture_is_audio_but_video_essence_is_rejected(self):
        jobs,pid,project=self.video_fixture()
        audio=AudioJobs(jobs)
        cover=PROMO_DIR/'openahoy-intro-cover.jpg'
        for extension,codec in [('mp3','libmp3lame'),('m4a','aac')]:
            path=project/('attached.'+extension)
            invoke('ffmpeg',['-v','error','-f','lavfi','-i','sine=frequency=420:duration=0.5',
                '-i',str(cover),'-map','0:a','-map','1:v','-c:a',codec,'-c:v','copy',
                '-disposition:v','attached_pic',str(path)],15)
            row=audio.ingest(extension,pid,'Original cover',{'path':path.name,'sha256':hexdigest(path)})
            self.assertEqual(row['sha256'],hexdigest(path))
            self.assertEqual(row['state'],'ASSET_READY')
        counterfeit=project/'video.m4a'
        invoke('ffmpeg',['-v','error','-f','lavfi','-i','color=red:s=64x64:d=1',
                         '-f','lavfi','-i','sine=d=1','-c:a','aac','-c:v','libx264',
                         '-f','mp4',str(counterfeit)],15)
        with self.assertRaisesRegex(WCEError,'AUDIO_FILE_INVALID'):
            audio.ingest('video',pid,'Moving video',{'path':counterfeit.name,'sha256':hexdigest(counterfeit)})

    def test_12_monitor_projects_missing_gif_and_audio_without_writing_history(self):
        jobs,pid,project=self.video_fixture()
        audio,gifs=AudioJobs(jobs),GifJobs(jobs)
        audio.init();gifs.root.mkdir(mode=0o700)
        track=project/'tone.wav'
        invoke('ffmpeg',['-v','error','-f','lavfi','-i','sine=d=1',str(track)],15)
        row=audio.ingest('track',pid,'Tone',{'path':track.name,'sha256':hexdigest(track)})
        path,artifact,lock=gifs.paths('animation')
        invoke('ffmpeg',['-v','error','-f','lavfi','-i','testsrc2=size=64x64:rate=4:duration=1',str(artifact)],15)
        artifact.chmod(0o600);lock.touch(mode=0o600)
        raw=artifact.read_bytes()
        atomic_write(path,{'generation_attempt_id':'animation','project_id':pid,'state':'ASSET_READY',
            'created_at':time.time(),'root_identity':[],'project_copy':[],
            'asset':gif_facts(raw)|{'sha256':hexdigest(artifact),'bytes':len(raw)}})
        before={p:p.read_bytes() for p in (path,audio.receipt('track'))}
        self.assertEqual({r['state'] for r in collect(jobs,gifs,audio)['rows']},{'ASSET_READY'})
        artifact.unlink();(project/row['file']).unlink()
        self.assertEqual({r['state'] for r in collect(jobs,gifs,audio)['rows']},{'UNAVAILABLE'})
        self.assertEqual({p:p.read_bytes() for p in before},before)


if __name__ == '__main__':
    unittest.main()
