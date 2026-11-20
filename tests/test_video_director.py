"""Close the director's project, revision, and provider boundaries without network access."""
from base64 import b64decode, b64encode
from concurrent.futures import ThreadPoolExecutor
from hashlib import sha256
import json
import os
from pathlib import Path
import secrets
import struct
import sys
import tempfile
import unittest
from unittest.mock import Mock, patch
import zlib

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'plugins/wechat-ecosystem'))

from wce.contracts import WCEError
from wce.document_errors import location
from wce.video_director_protocol import DirectorRouter, EDIT, MEDIA, READ, SUBMIT, prompt_cards
from wce.video_jobs import Jobs, PROMO_DIR
from wce.own_connection_policy import atomic_write
from wce.video_director_media import models
from wce.video_engine_catalog import public_media_url
from wce.video_seedance import MODEL


def make_png(path, color):
    def chunk(kind, data):
        return struct.pack('!I', len(data)) + kind + data + struct.pack('!I', zlib.crc32(kind + data))
    width, height = 640, 360
    raw = (b'\x00' + bytes(color) * width) * height
    path.write_bytes(b'\x89PNG\r\n\x1a\n' + chunk(b'IHDR', struct.pack('!2I5B', width,height,8,2,0,0,0))
                     + chunk(b'IDAT', zlib.compress(raw)) + chunk(b'IEND', b''))
    return sha256(path.read_bytes()).hexdigest()


class DirectorTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name).resolve()
        self.home = self.root / 'settings'
        self.home.mkdir(mode=0o700)
        self.project = self.root / 'project'
        self.project.mkdir()
        self.other = self.root / 'other'
        self.other.mkdir()
        self.jobs = Jobs(self.home / 'connections.json', api=Mock(), credential=Mock())
        self.p = self.jobs.projects.sync(str(self.project), [], 'project-'+'a'*32, 0)['project_id']
        self.q = self.jobs.projects.sync(str(self.other), [], 'project-'+'b'*32, 1)['project_id']
        self.inner = Mock(video_jobs=self.jobs)
        self.inner.list_tools.return_value = [{'name': 'existing'}]
        self.desk = DirectorRouter(self.inner)
        self.work = self.edit('create_work', {'fields': {'title': '测试作品','duration_ms': 4*3600_000}})['work_id']
        self.base = {'project_id': self.p, 'work_id': self.work}
        self.one = self.edit('create_scene', self.base|{'title':'进入','start_ms':0,'end_ms':6000})['scene_id']
        self.two = self.edit('create_scene', self.base|{'title':'交流','start_ms':6000,'end_ms':12000})['scene_id']
        self.a = self.shot(self.one, '远景')
        self.b = self.shot(self.one, '转角')
        self.c = self.shot(self.two, '近景')
        self.image1 = self.asset('image-1.png',(60,120,180))
        self.image2 = self.asset('image-2.png',(130,110,30))

    def asset(self, filename, color):
        return {'project_id':self.p,'path':filename,'sha256':make_png(self.project/filename,color)}

    def read(self, action, args=None):
        return self.desk.call(READ, {'action': action, **(args or {})})

    def edit(self, action, args, operation_id=None):
        params = {'project_id': self.p, 'action': action, **args}
        if not action.startswith('character_'):
            params['operation_id'] = operation_id or secrets.token_hex(16)
        return self.desk.call(EDIT, params)

    def shot(self, scene, title):
        row = self.edit('create_shot', self.base|{'scene_id':scene,'title':title})
        return {k:row[k] for k in ('project_id','work_id','scene_id','shot_id','revision_id')}

    def revised(self, target, fields, operation_id=None):
        spec = {k:v for k,v in target.items() if k!='revision_id'}
        row = self.edit('revise', spec|{'base_revision':target['revision_id'],'origin':'codex','fields':fields}, operation_id)
        return spec|{'revision_id':row['revision_id']}

    def test_two_scenes_three_shots_choose_and_reopen_immutable_history(self):
        edit1 = self.revised(self.b, {'opening':'窗外','prompt':'保留\n真实换行','notes':'完整文字'})
        edit2 = self.revised(edit1, {'images':[{'role':'composition','file':self.image1}]})
        self.revised(self.c, {'images':[{'role':'composition','file':self.image2}], 'action':'接触'})
        self.edit('adopt', edit2|{'base_revision':edit2['revision_id']})
        self.desk = DirectorRouter(self.inner)
        view = self.read('overview', self.base)['work']
        self.assertEqual([s['id'] for s in view['scenes']], [self.one,self.two])
        self.assertEqual([len(s['shots']) for s in view['scenes']],[2,1])
        self.assertEqual(view['selection']['revision_id'],edit2['revision_id'])
        self.assertEqual(self.read('context', edit1)['revision']['images'],[])
        new = self.read('context', edit2)['revision']
        self.assertEqual((new['opening'],new['prompt'],new['images'][0]['file']['sha256']),
                         ('窗外','保留\n真实换行',self.image1['sha256']))
        image = self.desk.call(MEDIA, {'action':'image',**edit2})
        self.assertEqual(image['sha256'],self.image1['sha256'])
        self.assertEqual(image['mime_type'],'image/jpeg')
        self.assertTrue(image['data'].startswith('/9j/'))

    def test_default_prefers_an_adopted_image_over_text_only_or_unadopted_shots(self):
        self.revised(self.a,{'opening':'text only'})
        candidate=self.revised(self.b,{'images':[{'role':'composition','file':self.image1}]})
        another=self.revised(self.c,{'images':[{'role':'composition','file':self.image2}]})
        view=self.read('overview',self.base)['work']
        self.assertEqual(view['selection']['revision_id'],candidate['revision_id'])
        self.edit('adopt',another|{'base_revision':another['revision_id']})
        self.desk=DirectorRouter(self.inner)
        self.assertEqual(self.read('overview',self.base)['work']['selection']['revision_id'],another['revision_id'])

    def test_rejects_cross_project_symlink_changed_file_and_stale_revision(self):
        for target,file,reason in [
            (self.a|{'project_id':self.q},self.image1,'DIRECTOR_WORK_NOT_FOUND'),
            (self.a,self.image1|{'project_id':self.q},'DIRECTOR_ASSET_WRONG_PROJECT'),
            (self.a,self.image1|{'path':'../other/secret.png'},'DIRECTOR_ASSET_OUTSIDE_PROJECT'),
            (self.a,self.image1|{'sha256':'f'*64},'VIDEO_FRAME_CHANGED'),
        ]:
            with self.subTest(reason=reason),self.assertRaisesRegex(WCEError,reason):
                self.revised(target, {'images':[{'role':'first','file':file}]})
        self.assertFalse((self.other/'.openahoy-director').exists())
        (self.project/'alias.png').symlink_to(self.project/'image-1.png')
        with self.assertRaisesRegex(WCEError,'INVALID_LOCAL_FILE'):
            self.revised(self.a,{'images':[{'role':'first','file':self.image1|{'path':'alias.png'}}]})
        after = self.revised(self.a,{'action':'new'})
        with self.assertRaisesRegex(WCEError,'DIRECTOR_STALE_REVISION'):
            self.revised(self.a,{'action':'stale'})
        self.assertEqual(self.read('context',after)['revision']['action'],'new')

    def test_concurrent_same_request_and_conflicting_head(self):
        op='f'*32
        with ThreadPoolExecutor(max_workers=2) as threads:
            results=list(threads.map(lambda _:self.revised(self.a, {'notes':'stop'}, op), range(2)))
        self.assertEqual(results[0],results[1])
        with self.assertRaisesRegex(WCEError,'DIRECTOR_OPERATION_CONFLICT'):
            self.revised(self.a,{'notes':'different'},op)
        self.assertEqual(self.read('context',results[0])['revision']['number'],2)

    def test_canvas_preserves_view_and_nodes_without_mutating_original_shots(self):
        a = self.edit('canvas_add', self.base | {'expected_canvas_version': 0,
            'node': {'kind': 'note', 'title': '字幕', 'text': '保留这行正文', 'shot_id': self.a['shot_id']},
            'position': {'x': 6, 'y': 5}})
        node_id = a['node_id']
        with self.assertRaisesRegex(WCEError, 'DIRECTOR_CANVAS_CHANGED'):
            self.edit('canvas_move', self.base | {'expected_canvas_version': 0, 'node_id': node_id,
                                                 'position': {'x': 2, 'y': 4}})
        self.edit('canvas_move', self.base | {'expected_canvas_version': 1, 'node_id': self.a['shot_id'],
                                             'position': {'x': 23, 'y': 52}})
        self.edit('canvas_note_edit', self.base | {'expected_canvas_version': 2, 'node_id': node_id,
                                                  'title': '字幕', 'text': '修改这行正文'})
        viewport = {'x': -32, 'y': 14, 'scale': 128}
        self.edit('canvas_view', self.base | {'expected_canvas_version': 3, 'viewport': viewport})
        self.desk = DirectorRouter(self.inner)
        canvas = self.read('overview', self.base)['work']['canvas']
        self.assertEqual(canvas['viewport'], viewport)
        self.assertEqual(canvas['positions'][self.a['shot_id']], {'x': 23, 'y': 52})
        self.assertEqual(canvas['nodes'][node_id]['text'], '修改这行正文')
        self.assertEqual(self.read('context', self.a)['head_revision'], self.a['revision_id'])
        self.assertIsNone(self.read('overview', {'project_id': self.q})['work'])
        self.edit('canvas_remove', self.base | {'expected_canvas_version': 4, 'node_id': node_id})
        self.assertEqual(self.read('overview', self.base)['work']['canvas']['nodes'], {})

    def test_png_file_import_resumes_once_and_attaches_original_digest(self):
        raw = (self.project / self.image1['path']).read_bytes()
        digest = sha256(raw).hexdigest()
        request = self.base | {'action': 'import_image_chunk', 'total': len(raw), 'sha256': digest}

        def upload(offset, payload):
            return self.desk.call(MEDIA, request | {'offset': offset, 'data': b64encode(payload).decode()})

        boundary = 19
        first = upload(0, raw[:boundary])
        self.assertEqual(first, {'state': 'RECEIVING', 'received': boundary})
        self.assertEqual(upload(0, raw[:boundary]), first)
        with self.assertRaisesRegex(WCEError, 'DIRECTOR_IMAGE_IMPORT_CONFLICT'):
            upload(0, b'!' + raw[1:boundary])
        final = upload(boundary, raw[boundary:])
        self.assertEqual(final['state'], 'IMPORTED')
        self.assertEqual(final['file']['sha256'], digest)
        self.assertEqual(upload(0, raw[:boundary]), final)
        asset = final['file']
        self.assertEqual((self.project / asset['path']).read_bytes(), raw)
        with self.assertRaisesRegex(WCEError, 'DIRECTOR_ASSET_WRONG_PROJECT'):
            self.edit('canvas_add', self.base | {'expected_canvas_version': 0,
                      'position': {'x': 0, 'y': 0}, 'node': {'kind': 'image', 'title': '外部项目',
                      'file': asset | {'project_id': self.q}}})
        added = self.edit('canvas_add', self.base | {'expected_canvas_version': 0,
                          'position': {'x': 0, 'y': 0}, 'node': {'kind': 'image', 'title': '原图', 'file': asset}})
        self.desk = DirectorRouter(self.inner)
        image = self.desk.call(MEDIA, self.base | {'action': 'canvas_image', 'node_id': added['node_id']})
        self.assertEqual(image['sha256'], digest)
        self.assertEqual(self.revised(self.a, {'images':[{'role':'composition','file':asset}]})['shot_id'],
                         self.a['shot_id'])

    def test_channel_catalog_and_strict_provider_specific_save(self):
        with patch('wce.video_director_media.status', return_value={'state':'NOT_CONFIGURED'}), \
                patch('wce.video_director_media.configured_connection', return_value='NOT_CONFIGURED'):
            inventory = models({'state':'MODELS_VISIBLE', 'models':[MODEL, 'unrelated'],
                                'selected_model':MODEL, 'native_verified':False})
        self.assertEqual({provider:len(rows) for provider,rows in inventory['models'].items()},
                         {'ark':7, 'cn':13, 'global':13, 'relay':1, 'tokenhex':7})
        self.assertEqual(inventory['tokenhex_catalog']['models'], [MODEL])
        self.assertEqual(inventory['tokenhex_catalog']['selected_model'], MODEL)
        self.assertEqual({row['visibility'] for row in inventory['models']['tokenhex']}, {'VISIBLE', 'NOT_VISIBLE'})
        subject = {'provider':'cn','model':'S2V-01','mode':'subject',
                   'subject_image_url':'https://cdn.example.org/subject.png?sortKey=1'}
        revision = self.revised(self.a, {'configuration':subject,'prompt':'本地预检'})
        result = self.read('preflight',revision)['request']
        self.assertEqual(result['inputs'], [{'role':'subject','url':subject['subject_image_url']}])
        self.assertNotIn('duration',result['configuration'])
        with self.assertRaisesRegex(WCEError,'VIDEO_OUTPUT_UNSUPPORTED'):
            self.revised(revision, {'configuration':subject|{'resolution':'2K'}})
        with self.assertRaisesRegex(WCEError,'PROJECT_SECRET_NOT_ALLOWED'):
            public_media_url('https://cdn.example.org/subject.png?X-Amz-Signature=fixture')
        relay = {'provider':'relay','model':'MiniMax-H3-Relay','mode':'workflow','duration':4,
                 'resolution':'768p横','reference_images':['https://cdn.example.org/first.png'],
                 'reference_audio':['https://cdn.example.org/track.wav']}
        updated = self.revised(revision, {'configuration':relay})
        result = self.read('preflight',updated)['request']
        self.assertEqual([row['role'] for row in result['inputs']],['reference_image','reference_audio'])
        with self.assertRaisesRegex(WCEError,'VIDEO_MODE_UNSUPPORTED'):
            self.revised(updated, {'configuration':relay|{'mode':'frames'}})

    def test_work_delivery_reads_original_once_and_keeps_separate_local_edit(self):
        movie = (PROMO_DIR / 'openahoy-intro.mp4').read_bytes()
        config = {'provider':'ark','model':MODEL,'mode':'text','duration':10,
                  'resolution':'720p','ratio':'16:9','audio':True}
        prompt = '原镜头文字'
        rev = self.revised(self.a, {'configuration':config,'prompt':prompt})
        track = rev | {'attempt_id':'original-attempt'}
        self.edit('track_generation', track)
        query = {'action':'deliveries', **self.base}
        self.assertEqual(self.desk.call(READ, query)['cards'][0]['state'], 'AWAITING_RECEIPT')
        self.jobs._directory()
        receipt, original = self.jobs._paths('original-attempt')
        request = {'project_id':self.p,'model':MODEL,'frames':[], 'prompt_sha256':sha256(prompt.encode()).hexdigest(),
                   **{k:config[k] for k in ('mode','duration','resolution','ratio','audio')}}
        pending = {'generation_attempt_id':'original-attempt','state':'RUNNING','created_at':1,
                   'provider_task_id':'cgt-original','request':request}
        atomic_write(receipt, pending|{'request':request|{'duration':11}})
        rejected = self.desk.call(EDIT, self.base|{'action':'poll_delivery','attempt_id':'original-attempt'})
        self.assertEqual(rejected['cards'][0]['state'], 'UNAVAILABLE')
        self.jobs.api.query.assert_not_called()
        atomic_write(receipt, pending)
        self.assertEqual(self.desk.call(READ, query)['cards'][0]['state'], 'RUNNING')
        self.jobs.api.query.return_value={'status':'succeeded','content':{'video_url':'https://cdn.example.org/original.mp4'}}
        self.jobs.api.download.side_effect=lambda _uri, target: target.write(movie)
        from wce.contracts import Secret
        self.jobs.credential.return_value=Secret('fixture')
        ready = self.desk.call(EDIT,self.base|{'action':'poll_delivery','attempt_id':'original-attempt'})
        self.assertEqual(ready['cards'][0]['state'], 'ASSET_READY')
        self.assertEqual(sha256(original.read_bytes()).hexdigest(),sha256(movie).hexdigest())
        self.jobs.api.query.assert_called_once()
        self.jobs.api.submit.assert_not_called()
        checksum = sha256(movie).hexdigest()
        linked = self.revised(rev, {'result': {'project_id':self.p,'attempt_id':'original-attempt','sha256':checksum}})
        shot = self.read('context',linked)
        self.assertEqual(shot['revision']['result']['attempt_id'],'original-attempt')
        with self.assertRaisesRegex(WCEError,'DIRECTOR_GENERATION_SCOPE_CHANGED'):
            self.edit('track_generation',linked|{'attempt_id':'original-attempt'})
        composition = self.project/'review-cut.mp4'
        composition.write_bytes(movie)
        file = {'project_id':self.p,'path':composition.name,'sha256':checksum}
        film = self.edit('register_work_video',self.base|{'file':file,'title':'整片'})
        repeated = self.edit('register_work_video',self.base|{'file':file,'title':'整片'})
        self.assertEqual(film['delivery_id'],repeated['delivery_id'])
        self.assertEqual(film['chat_path'],str(composition))
        self.desk = DirectorRouter(self.inner)
        cards = self.desk.call(READ,query)['cards']
        self.assertEqual([row['kind'] for row in cards],['shot_video','work_video'])
        self.assertEqual([row['state'] for row in cards],['ASSET_READY','ASSET_READY'])
        chunk = self.desk.call(MEDIA,self.base|{'action':'work_video_chunk','delivery_id':film['delivery_id'],'offset':0})
        self.assertEqual(b64decode(chunk['bytes']),movie[:len(b64decode(chunk['bytes']))])
        self.assertEqual(chunk['sha256'],checksum)
        self.assertEqual(sha256(composition.read_bytes()).hexdigest(),checksum)
        self.assertEqual(self.desk.call(EDIT,self.base|{'action':'poll_delivery','attempt_id':'original-attempt'})['cards'],cards)
        self.jobs.api.query.assert_called_once()
        other = self.edit('create_work',{'fields':{'title':'不同作品'}})['work_id']
        self.assertEqual(self.desk.call(READ,query|{'work_id':other})['cards'],[])

        # Preserve an explicit older revision after the head links a different original.
        alternate_receipt, alternate_media = self.jobs._paths('alternate-attempt')
        alternate_media.write_bytes(movie)
        alternate_media.chmod(0o600)
        atomic_write(alternate_receipt, json.loads(receipt.read_text()) | {'generation_attempt_id':'alternate-attempt'})
        current = self.revised(linked, {'result': {'project_id':self.p,'attempt_id':'alternate-attempt',
                                                  'sha256':checksum}})
        candidate, alternate, whole = self.desk.call(READ, query)['cards']
        self.assertEqual(candidate['id'], cards[0]['id'])
        self.assertEqual(candidate['node_id'], alternate['node_id'])
        self.assertEqual(whole['id'], film['delivery_id'])
        for version, node_id in enumerate((candidate['node_id'], whole['id'])):
            self.edit('canvas_move', self.base | {'node_id': node_id,
                      'expected_canvas_version': version, 'position': {'x': 330, 'y': 42 + version}})
        saved = self.read('overview', self.base)['work']['canvas']
        self.assertEqual(saved['positions'][candidate['node_id']], {'x': 330, 'y': 42})
        self.assertEqual(saved['positions'][whole['id']], {'x': 330, 'y': 43})
        self.assertEqual(self.read('overview', self.base)['work']['scenes'][0]['shots'][0]['head_revision'],
                         current['revision_id'])
        for card in (candidate, whole):
            scope = self.base | {'delivery_id': card['id'], 'sha256': checksum}
            frames = self.desk.call(MEDIA, scope | {'action':'canvas_video_frames','start':4})
            self.assertEqual(len(frames['frames']), 4)
            with self.assertRaisesRegex(WCEError, 'DIRECTOR_(RESULT_UNAVAILABLE|ASSET_CHANGED)'):
                self.desk.call(MEDIA, scope | {'action':'canvas_video_chunk','offset':0,'sha256':'0'*64})
            with self.assertRaisesRegex(WCEError, 'DIRECTOR_RESULT_UNAVAILABLE'):
                self.desk.call(MEDIA, scope | {'action':'canvas_video_chunk','offset':0,'work_id':other})
        pick = self.base | {'scene_id': self.one, 'shot_id': self.a['shot_id'],
                            'candidate_id': candidate['id'], 'sha256': checksum}
        with self.assertRaisesRegex(WCEError, 'DIRECTOR_RESULT_UNAVAILABLE'):
            self.edit('adopt_video', pick | {'shot_id': self.b['shot_id']})
        before = self.read('context', current)
        self.assertEqual(self.edit('adopt_video', pick)['adopted_video']['candidate_id'], candidate['id'])
        self.assertEqual(self.read('context', current), before)
        self.assertTrue(self.desk.call(READ, query)['cards'][0]['adopted'])
        with self.assertRaisesRegex(WCEError, 'DIRECTOR_STALE_REVISION'):
            self.edit('adopt_video', pick)

    def character_entry(self, version, file, status='candidate', use='full_body'):
        return {'id': version, 'character': {'id': 'aria', 'name': '阿岚', 'series': '港口篇', 'aliases': ['Aria']},
                'use': use, 'initial_status': status, 'label': version, 'description': '三视图',
                'source': '隔离原图', 'path': file['path'], 'sha256': file['sha256']}

    def character_manifest(self, *entries):
        path = self.project / 'characters.json'
        raw = json.dumps({'schema': 1, 'assets': entries}, ensure_ascii=False).encode()
        path.write_bytes(raw)
        return {'path': path.name, 'sha256': sha256(raw).hexdigest()}

    def test_character_library_locks_old_reference_across_current_updates_and_reopen(self):
        old = self.character_entry('aria-v1', self.image1, 'current')
        new = self.character_entry('aria-v2', self.image2)
        face = self.character_entry('aria-face-v1', self.image2, 'current', 'face')
        manifest = self.character_manifest(old, new, face)
        args = {'project_id': self.p, 'source': manifest}
        plan = self.read('character_import_preview', args)
        self.assertEqual([row['availability'] for row in plan['assets']], ['available'] * 3)
        self.assertEqual(self.edit('character_import', args | {'expected_revision': plan['revision']})['added'], 3)
        reference = {'role': 'reference', 'file': self.image1, 'asset_version': old['id']}
        locked = self.revised(self.a, {'images': [reference]})
        with self.assertRaisesRegex(WCEError, 'DIRECTOR_STALE_REVISION'):
            self.revised(self.a, {'images': [reference]})
        self.edit('character_set_current', {'version_id': new['id'], 'expected_current': old['id']})
        self.assertEqual(self.edit('character_import', args | {'expected_revision': 0})['state'], 'UNCHANGED')
        self.desk = DirectorRouter(self.inner)
        assets = next(project['assets'] for project in self.read('character_library')['projects'] if project['id'] == self.p)
        self.assertEqual({row['id']: row['status'] for row in assets},
                         {old['id']: 'historical', new['id']: 'current', face['id']: 'current'})
        self.assertEqual(self.read('context', locked)['revision']['images'], [reference])
        self.assertEqual(self.read('context', self.a)['revision']['images'], [])
        for file in [self.image2, self.image1 | {'project_id': self.q}]:
            with self.assertRaisesRegex(WCEError, 'DIRECTOR_(CHARACTER_REFERENCE_MISMATCH|ASSET_WRONG_PROJECT)'):
                self.revised(self.b, {'images': [reference | {'file': file}]})
        result = self.desk.call(MEDIA, {'action': 'character_original', 'project_id': self.p,
                                      'version_id': old['id'], 'sha256': old['sha256'], 'offset': 0})
        self.assertEqual(b64decode(result['data']), (self.project / old['path']).read_bytes())
        self.assertFalse((self.project / '.openahoy-director' / 'images').exists())

    def test_character_library_import_conflicts_and_unavailable_original(self):
        missing = self.character_entry('missing', self.image2 | {'path': 'missing.png'})
        old = self.character_entry('aria-v1', self.image1, 'current')
        with self.assertRaisesRegex(WCEError, 'DIRECTOR_ASSET_OUTSIDE_PROJECT'):
            self.read('character_import_preview', {'project_id': self.p,
                'source': self.character_manifest(old | {'path': '../other/image.png'})})
        manifest = self.character_manifest(old, missing)
        args = {'project_id': self.p, 'source': manifest}
        self.assertEqual(self.read('character_import_preview', args)['assets'][1]['availability'], 'missing')
        self.edit('character_import', args | {'expected_revision': 0})
        with self.assertRaisesRegex(WCEError, 'DIRECTOR_CHARACTER_MANIFEST_CHANGED'):
            conflicting = self.character_manifest(old | {'label': '新的文字'})
            self.read('character_import_preview', args)
        with self.assertRaisesRegex(WCEError, 'DIRECTOR_CHARACTER_VERSION_CONFLICT'):
            self.edit('character_import', {'source': conflicting, 'expected_revision': 1})
        with self.assertRaisesRegex(WCEError, 'DIRECTOR_CHARACTER_ORIGINAL_UNAVAILABLE'):
            self.edit('character_set_current', {'version_id': missing['id'], 'expected_current': old['id']})
        media = {'action': 'character_thumbnail', 'project_id': self.p,
                 'version_id': old['id'], 'sha256': old['sha256']}
        self.desk.call(MEDIA, media)
        make_png(self.project / old['path'], (3, 60, 168))
        with self.assertRaisesRegex(WCEError, 'VIDEO_FRAME_CHANGED'):
            self.desk.call(MEDIA, media)
        (self.project / old['path']).unlink()
        with self.assertRaisesRegex(WCEError, 'DIRECTOR_CHARACTER_ORIGINAL_MISSING'):
            self.desk.call(MEDIA, media)
        self.assertTrue(any(row['id'] == old['id'] for project in self.read('character_library')['projects']
                            for row in project['assets']))
        with self.assertRaisesRegex(WCEError, 'DIRECTOR_CHARACTER_VERSION_NOT_FOUND'):
            self.desk.call(MEDIA, media | {'project_id': self.q})

    def test_character_nested_style_index_and_explicit_cross_project_copy(self):
        nested = self.project / 'references' / 'faces'
        nested.mkdir(parents=True)
        style = self.character_entry('style-v1', self.image1, use='style')
        (nested / 'good.json').write_text(json.dumps({'schema': 1, 'assets': [style]}))
        (nested / 'bad.json').write_text(json.dumps({'schema': 1, 'assets': [style, style | {'use': 'unknown'}]}))
        (nested / 'escape').symlink_to(self.other, target_is_directory=True)

        def media(action, **fields):
            return self.desk.call(MEDIA, {'action': action, 'project_id': self.p} | fields)

        self.assertEqual(media('character_manifest_files', directory='references/faces'),
                         {'directory': 'references/faces', 'folders': [], 'files': ['bad.json', 'good.json']})
        for path in ('references/faces/escape', '../other'):
            with self.assertRaises(WCEError):
                media('character_manifest_files', directory=path)
        with self.assertRaisesRegex(WCEError, 'DIRECTOR_CHARACTER_MANIFEST_INVALID') as error:
            media('character_manifest_pick', path='references/faces/bad.json')
        self.assertEqual(location(error.exception), {'manifest_position': 2, 'manifest_field': 'use',
            'allowed_values': ['full_body', 'face', 'expression', 'pose', 'style']})
        plan = media('character_manifest_pick', path='references/faces/good.json')
        self.assertEqual(plan['source']['path'], 'references/faces/good.json')
        self.edit('character_import', {'source': plan['source'], 'expected_revision': plan['revision']})
        index = self.project / '.openahoy-director/character-library.json'
        original_index = index.read_bytes()
        original_asset = (self.project / style['path']).read_bytes()
        origin = {'project_id': self.p, 'version_id': style['id'], 'sha256': style['sha256']}
        args = {'project_id': self.q, 'origin': origin}
        with self.assertRaisesRegex(WCEError, 'DIRECTOR_PROJECT_NOT_REGISTERED'):
            self.edit('character_import_version', args | {'origin': origin | {'project_id': 'b' * 32}})
        with self.assertRaisesRegex(WCEError, 'DIRECTOR_CHARACTER_REFERENCE_MISMATCH'):
            self.edit('character_import_version', args | {'origin': origin | {'sha256': '0' * 64}})
        target_work = self.edit('create_work', {'project_id': self.q, 'fields': {'title': 'Target'}})['work_id']
        scope = {'project_id': self.q, 'work_id': target_work}
        scene = self.edit('create_scene', scope | {'title':'Scene','start_ms':0,'end_ms':1000})['scene_id']
        target = self.edit('create_shot', scope | {'scene_id': scene, 'title': 'Target shot'})
        target = {key: target[key] for key in ('project_id','work_id','scene_id','shot_id','revision_id')}
        with self.assertRaisesRegex(WCEError, 'DIRECTOR_ASSET_WRONG_PROJECT'):
            self.revised(target, {'images': [{'role':'reference','file':self.image1,'asset_version':style['id']}]})
        imported = self.edit('character_import_version', args)
        self.assertEqual((imported['state'], imported['origin']), ('IMPORTED', origin))
        before = (self.other / imported['file']['path']).read_bytes()
        self.assertEqual(before, original_asset)
        same = self.edit('character_import_version', args)
        self.assertEqual(same, imported | {'state': 'UNCHANGED'})
        pinned = {'role':'reference','file':imported['file'],'asset_version':imported['version_id']}
        saved = self.revised(target, {'images':[pinned]})
        self.assertEqual(index.read_bytes(), original_index)
        self.assertEqual((self.project / style['path']).read_bytes(), original_asset)
        make_png(self.project / style['path'], (8, 7, 6))
        with self.assertRaisesRegex(WCEError, 'VIDEO_FRAME_CHANGED'):
            self.edit('character_import_version', args)
        self.desk = DirectorRouter(self.inner)
        self.assertEqual(self.read('context', saved)['revision']['images'], [pinned])
        listing = self.read('character_library')['projects']
        copied, = next(row['assets'] for row in listing if row['id'] == self.q)
        self.assertEqual((copied['origin'], copied['use']), (origin, 'style'))

    def test_character_current_competing_writers_cannot_replace_each_other(self):
        a = self.character_entry('aria-v1', self.image1, 'current')
        b = self.character_entry('aria-v2', self.image2)
        c = self.character_entry('aria-v3', self.image2)
        self.edit('character_import', {'source': self.character_manifest(a, b, c), 'expected_revision': 0})

        def select(row):
            try:
                return self.edit('character_set_current', {'version_id': row['id'], 'expected_current': a['id']})['state']
            except WCEError as failure:
                return str(failure)

        with ThreadPoolExecutor(max_workers=2) as pool:
            self.assertCountEqual(pool.map(select, (b, c)), ['SAVED', 'DIRECTOR_CHARACTER_CURRENT_CONFLICT'])

    def test_default_submit_pins_exact_input_and_original_result(self):
        old = self.character_entry('aria-v1', self.image1, 'current')
        new = self.character_entry('aria-v2', self.image2)
        manifest = self.character_manifest(old, new)
        self.edit('character_import', {'source': manifest, 'expected_revision': 0})
        config = {'provider':'ark','model':MODEL,'mode':'frames','duration':5,'resolution':'720p','ratio':'16:9'}
        target = self.revised(self.a, {'prompt': 'Slow push towards the door.',
            'images': [{'role':'last','file':self.image2}, {'role':'first','file':self.image1,'asset_version':old['id']}],
            'configuration': config})
        self.edit('character_set_current', {'version_id': new['id'], 'expected_current': old['id']})
        job = {'generation_attempt_id':'exact-original', **target}
        attempt = job['generation_attempt_id']
        receipt, artifact = self.jobs._paths(attempt)
        original = b'fixture-original-video-bytes'
        self.jobs.inspect = lambda path: {'width':640,'height':360,'seconds':5,'audio_tracks':0}

        def accept(key, body):
            guard = json.loads(receipt.read_text())
            self.assertEqual(guard['state'], 'SUBMIT_UNKNOWN')
            self.assertEqual(guard['request_sha256'], sha256(body).hexdigest())
            self.assertTrue(all(guard['director_binding'][key] == value for key, value in target.items()))
            self.assertEqual(guard['request']['frames'], [self.image1['sha256'],self.image2['sha256']])
            cards = self.read('deliveries', self.base)['cards']
            self.assertEqual([(card['attempt_id'],card['state']) for card in cards], [(attempt,'SUBMIT_UNKNOWN')])
            return 'upstream-original'

        self.jobs.api.submit.side_effect = accept
        tool = next(row for row in self.desk.list_tools() if row['name'] == SUBMIT)
        self.assertEqual(tool['_meta']['ui']['visibility'], ['model'])
        self.assertEqual(self.desk.call(SUBMIT, job)['provider_task_id'], 'upstream-original')
        submitted = self.read('deliveries', self.base)['cards'][0]
        self.assertEqual(submitted['state'], 'SUBMITTED')
        self.assertEqual(submitted['character_inputs'], [{'position':1,'role':'first','version_id':old['id'],
                                                           'sha256':self.image1['sha256']}])
        with self.assertRaisesRegex(WCEError, 'DIRECTOR_GENERATION_SCOPE_CHANGED'):
            self.desk.call(SUBMIT, self.b | {'generation_attempt_id': attempt})
        with self.assertRaises(WCEError):
            self.desk.call(SUBMIT, job | {'project_id': self.q})
        self.assertEqual(self.desk.call(SUBMIT, job)['state'], 'SUBMITTED')
        self.jobs.api.submit.assert_called_once()
        artifact.write_bytes(original)
        artifact.chmod(0o600)
        value = json.loads(receipt.read_text())
        atomic_write(receipt, dict(value,state='SAVE_PENDING',download_sha256=sha256(original).hexdigest()))
        latest = self.jobs.status(attempt, self.p, poll=False)
        self.assertEqual(latest['state'], 'ASSET_READY')
        card = self.read('deliveries', self.base)['cards'][0]
        self.assertEqual(card['asset']['sha256'], latest['asset']['sha256'])
        data = self.desk.call(MEDIA, self.base | {'action':'canvas_video_chunk', 'delivery_id':card['id'],
                             'sha256':card['asset']['sha256'],'offset':0})
        self.assertEqual(b64decode(data['bytes']), original)
        self.assertEqual(self.read('context', target)['revision']['images'][1]['asset_version'], old['id'])

    def test_default_submit_keeps_unknown_attempt_and_rejects_changed_bytes(self):
        config = {'provider':'ark','model':MODEL,'mode':'first','duration':5,'resolution':'720p','ratio':'16:9'}
        target = self.revised(self.a, {'prompt':'Approach the gate.',
            'images':[{'role':'first','file':self.image1}], 'configuration':config})
        args = target | {'generation_attempt_id':'unknown-original'}
        self.jobs.api.submit.side_effect = WCEError('VIDEO_NETWORK_ERROR')
        self.assertEqual(self.desk.call(SUBMIT, args)['state'], 'SUBMIT_UNKNOWN')
        make_png(self.project / self.image1['path'], (11,23,31))
        self.assertEqual(self.desk.call(SUBMIT, args)['state'], 'SUBMIT_UNKNOWN')
        with self.assertRaisesRegex(WCEError, 'VIDEO_FRAME_CHANGED'):
            self.desk.call(SUBMIT, args | {'generation_attempt_id':'different-request'})
        self.jobs.api.submit.assert_called_once()
        self.assertEqual([item['attempt_id'] for item in self.read('deliveries', self.base)['cards']], ['unknown-original'])

    def test_exact_submit_reuses_minimax_and_relay_adapters_with_honest_url_provenance(self):
        from wce.video_minimax import H3, SUBJECT_MODEL
        from wce.video_relay import RELAY_MODEL
        minimax, relay = Mock(), Mock()
        minimax.submit.return_value = 'minimax-fixture'
        relay.submit.return_value = 'relay-fixture'
        self.jobs.minimax = lambda site:minimax
        self.jobs.minimax_credential = lambda **_: 'fixture'
        self.jobs.relay = lambda origin:relay
        self.jobs.relay_credential = lambda: ('https://relay.example.com','fixture-connection','fixture')
        original = 'https://media.example.com/reference.png'
        test_cases = [
            (self.a, {'provider':'cn','model':H3,'mode':'first',
                      'duration':4,'resolution':'768P','ratio':'adaptive'}, 'direct-h3','LOCAL_INPUTS'),
            (self.b, {'provider':'global','model':SUBJECT_MODEL,'mode':'subject',
                      'subject_image_url':original}, 'subject-h3','URL_UNVERIFIED'),
            (self.c, {'provider':'relay','model':RELAY_MODEL,'mode':'workflow',
                      'reference_images':[original]}, 'relay-h3','URL_UNVERIFIED'),
        ]
        for shot, config, attempt, verification in test_cases:
            with self.subTest(attempt=attempt):
                target = self.revised(shot, {'prompt':'Camera tracks across the harbor.',
                    'images':[{'role':'first','file':self.image1}], 'configuration':config})
                accepted = self.desk.call(SUBMIT, target | {'generation_attempt_id':attempt})
                self.assertEqual(accepted['state'], 'SUBMITTED')
                self.assertEqual(accepted['director_binding']['verification'], verification)
                self.assertEqual(accepted['director_binding']['characters'], [])
        self.assertEqual(minimax.submit.call_count, 2)
        relay.submit.assert_called_once()

    def test_project_only_receipts_stay_in_their_project_inbox(self):
        workspace = {'mode':'text','paths':[],'duration':5,'resolution':'720p','ratio':'16:9','audio':False}
        self.jobs.api.submit.side_effect = ('task-a','task-b')
        with ThreadPoolExecutor(max_workers=2) as pool:
            values = list(pool.map(lambda item:self.jobs.submit(item[0],item[1],None,None,'Plan from the harbor.',
                            model=MODEL,workspace=workspace), [('unplaced-a',self.p),('unplaced-b',self.q)]))
        self.assertEqual({row['state'] for row in values}, {'SUBMITTED'})
        for project, attempt in [(self.p, 'unplaced-a'), (self.q,'unplaced-b')]:
            overview = self.read('overview', {'project_id':project})
            inbox = next(row['id'] for row in overview['works'] if row.get('inbox'))
            selected = self.read('overview', {'project_id':project,'work_id':inbox})
            self.assertTrue(selected['work']['inbox'])
            results = self.read('deliveries', {'project_id':project,'work_id':inbox})
            self.assertEqual([row['attempt_id'] for row in results['cards']],[attempt])
            self.assertEqual(results['cards'][0]['kind'], 'inbox_video')
        self.assertEqual(self.read('deliveries', self.base)['cards'],[])
        self.assertEqual(self.jobs.api.submit.call_count,2)

    def test_provider_preflight_does_not_use_credentials_or_submit(self):
        config = {'provider':'ark','model':MODEL,'mode':'frames','duration':5,'resolution':'720p','ratio':'16:9'}
        target = self.revised(self.a,{'prompt':'穿过门廊，停在窗边。','configuration':config,
            'images':[{'role':'composition','file':self.image2}]})
        with self.assertRaisesRegex(WCEError,'DIRECTOR_INPUT_FRAMES_REQUIRED'):
            self.read('preflight',target)
        target = self.revised(target,{'images':[{'role':'last','file':self.image2},{'role':'first','file':self.image1}]})
        with patch('wce.video_director_protocol.models',return_value={'connections':{'ark':'NOT_CONFIGURED'}}):
            proof = self.read('preflight',target)
        self.assertEqual(proof['state'],'PREFLIGHT_VALID')
        self.assertEqual(proof['connection'],'NOT_CONFIGURED')
        self.assertEqual([row['role'] for row in proof['request']['inputs']],['first','last'])
        self.jobs.credential.assert_not_called()
        self.jobs.api.submit.assert_not_called()

    def test_selected_shot_whitebox_plan_and_catalog_are_durable(self):
        whitebox={'mode':'plan','camera_path':'Door to window','subject_path':'Stay to frame left',
                  'key_points':'1.2 s threshold'}
        card=prompt_cards()['cards'][0]
        chosen=self.revised(self.a,{'whitebox':whitebox,'cards':[{'id':card['id'],'version':card['version']}]})
        self.desk=DirectorRouter(self.inner)
        view=self.read('context',chosen)['revision']
        self.assertEqual(view['whitebox'],whitebox)
        self.assertEqual(self.read('cards',{'card_id':card['id']}),card)
        self.assertTrue(any(t['name']=='existing' for t in self.desk.list_tools()))
        self.assertFalse(any(set(p.suffixes)=={'.mp4'} for p in self.project.glob('.openahoy-director/**/*')))


if __name__ == '__main__':
    unittest.main()
