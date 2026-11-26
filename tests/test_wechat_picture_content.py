"""Official picture-draft requests against a two-account synthetic server."""
from copy import deepcopy
import base64
from hashlib import sha256
import json
from pathlib import Path
import sqlite3
import struct
import tempfile
import threading
import time
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch
from urllib.parse import urlsplit

from wce import current_draft_inventory, current_draft_management, ordinary_publication, wechat_content
from wce.contracts import Secret, WCEError
from wce.http_transport import HTTPRequest, HTTPResponse, HTTPSender, MAX_BODY, MAX_WECHAT_MEDIA_BODY
from wce.own_connection_broker import AccountService


def response(value):
    return HTTPResponse(200, json.dumps(value, ensure_ascii=False).encode())


class TestPictures(unittest.TestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.base = Path(directory.name)
        self.service = self.account('A', '1')
        self.other = self.account('B', '2')
        self.groups = {}
        self.requests = []
        self.payloads = []
        self.reject = False
        self.lose_update = False
        self.lose_add = False
        self.lose_submit = False
        self.lose_broadcast = False
        self.broadcast_duplicate = False
        self.broadcast_error = None
        pixel_bytes=bytes((152,116,55))*(1024*1024)
        self.large_material = (b'BM'+struct.pack('<I4xI',54+len(pixel_bytes),54)
            +struct.pack('<IiiHHIIiiII',40,1024,1024,1,24,0,len(pixel_bytes),0,0,0,0)+pixel_bytes)
        self.source = {'mime_type': 'image/png', 'base64':
            'iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+a/D8AAAAASUVORK5CYII='}

    def account(self, name, digit):
        root = self.base / name
        root.mkdir(mode=0o700)
        state = root / 'state.sqlite3'
        with sqlite3.connect(state) as db:
            db.execute('PRAGMA user_version=6')
        state.chmod(0o600)
        app = 'wx' + digit*16
        registry = self.base / 'registry.json'
        policy = SimpleNamespace(root=root, check=Mock(),
            value={'capabilities':['draft_read','draft_save','draft_images'], 'registry_path':str(registry)},
            data={'actor':{'tenant_id':'t','principal_id':'p','client_id':'c','session_id':'s'},
                  'connection_id':name,'appid':app,'resource_id':app,
                  'generation':1,'epoch':0,'private_directory':str(root)})
        sender = HTTPSender(enabled=True)
        sender.send = lambda request, timeout: self.send(name,request,timeout)
        lease = SimpleNamespace(token=Secret('synthetic-api-token-for-'+name), wall_deadline=time.time()+300)
        return SimpleNamespace(policy=policy, guard=Mock(), serial=threading.Lock(),
            tokens=SimpleNamespace(get=lambda guard: guard() or lease, valid=lambda item:item is lease),
            workflow=SimpleNamespace(sender=sender))

    def send(self, account, request, timeout):
        self.assertGreater(timeout,0)
        self.assertFalse(request.test_only)
        endpoint=urlsplit(request.path).path
        self.requests.append((account,endpoint))
        if endpoint=='/cgi-bin/material/add_material':
            number=self.requests.count((account,endpoint))
            if 'type=video' in request.path:
                self.assertIn(b'name="description"',request.body)
                self.assertIn(b'Content-Type: video/mp4',request.body)
                return response({'media_id':'remote-video-'+account})
            return response({'media_id':'remote-image-'+account+(str(number) if number>1 else ''),
                             'url':'https://mmbiz.qpic.cn/mmbiz_png/Asset/0?wx_fmt=png'})
        if endpoint=='/cgi-bin/media/upload':
            self.assertIn(b'Content-Type: audio/amr',request.body)
            return response({'type':'voice','media_id':'remote-voice-'+account,'created_at':int(time.time())})
        if endpoint=='/cgi-bin/draft/count':
            self.assertEqual(request.method,'GET')
            return response({'total_count':sum(owner==account for owner,_ in self.groups)})
        if endpoint=='/cgi-bin/material/get_materialcount':
            self.assertEqual(request.method,'GET')
            return response({'image_count':2,'video_count':1,'voice_count':1,'news_count':0})
        if endpoint=='/cgi-bin/media/get':
            self.assertEqual(request.method,'GET')
            return HTTPResponse(200,b'#!AMR\nexample')
        data=json.loads(request.body)
        self.payloads.append((account,endpoint,deepcopy(data)))
        if endpoint=='/cgi-bin/material/batchget_material':
            return response({'total_count':1,'item':[{'media_id':'large-'+account,'name':'模拟大图'}]})
        if endpoint=='/cgi-bin/material/get_material':
            return HTTPResponse(200,self.large_material) if data['media_id']=='large-'+account else response({'errcode':40007})
        if endpoint=='/cgi-bin/freepublish/batchget':
            return response({'total_count':1,'item':[{'article_id':'published-'+account,
                'content':{'news_item':[{'title':'本号作品'}]}}]})
        if endpoint=='/cgi-bin/freepublish/getarticle':
            return response({'errcode':0,'news_item':[{'title':'本号作品','content':'<p>样稿</p>'}]})
        if endpoint=='/cgi-bin/freepublish/delete':
            return response({'errcode':0})
        if endpoint=='/channels/ec/service/product/getcardinfo':
            return response({'errcode':0,'product_key':'authorized-product'})
        if endpoint=='/cgi-bin/message/mass/preview':
            return response({'errcode':0,'errmsg':'preview success'})
        if endpoint=='/cgi-bin/media/uploadnews':
            return response({'type':'news','media_id':'remote-news-'+account,'created_at':int(time.time())})
        if endpoint in {'/cgi-bin/message/mass/sendall','/cgi-bin/message/mass/send'}:
            if self.broadcast_error:
                return response({'errcode':self.broadcast_error})
            if self.broadcast_duplicate:
                return response({'errcode':45065,'msg_id':9007199254740993})
            return HTTPResponse(502,b'') if self.lose_broadcast else response({'errcode':0,'msg_id':9007199254740993})
        if endpoint=='/cgi-bin/message/mass/get':
            return response({'msg_id':9007199254740993,'msg_status':'SEND_SUCCESS'})
        if endpoint=='/cgi-bin/draft/add':
            ref='remote-draft-'+str(len(self.groups)+1)
            if self.reject:
                return response({'errcode':48001})
            self.groups[(account,ref)]=deepcopy(data['articles'])
            return HTTPResponse(502,b'') if self.lose_add else response({'media_id':ref})
        if endpoint=='/cgi-bin/draft/update':
            self.groups[(account,data['media_id'])][data['index']]=deepcopy(data['articles'])
            return HTTPResponse(502,b'') if self.lose_update else response({'errcode':0})
        if endpoint=='/cgi-bin/draft/get':
            return response({'news_item':self.groups[(account,data['media_id'])]})
        if endpoint=='/cgi-bin/draft/delete':
            del self.groups[(account,data['media_id'])]
            return response({'errcode':0})
        if endpoint=='/cgi-bin/draft/batchget':
            items=[{'media_id':ref,'update_time':1} for owner,ref in self.groups if owner==account]
            return response({'total_count':len(items),'item_count':len(items),'item':items})
        if endpoint=='/cgi-bin/freepublish/submit':
            return HTTPResponse(502,b'') if self.lose_submit else response({'errcode':0,'publish_id':707})
        if endpoint=='/cgi-bin/freepublish/get':
            self.assertIn(str(data['publish_id']), ('707',))
            return response({'publish_id':707,'publish_status':0,'fail_idx':[],'article_id':'official-article-id',
                'article_detail':{'count':1,'item':[{'idx':1,'article_url':'https://mp.weixin.qq.com/s/examplelink'}]}})
        raise AssertionError(endpoint)

    def call(self, action, *, service=None, **args):
        service=service or self.service
        return AccountService._call(service,wechat_content.TOOL,
            {'connection_id':service.policy.data['connection_id'],'action':action}|args,time.monotonic()+60)

    def image(self, key='test-upload'):
        return self.call('upload_image',request_key=key,source=self.source)['operation_handle']

    def make(self, key='test-add', title='图片消息', count=1):
        return self.call('create_picture',request_key=key,
            article={'title':title,'content':'一段纯文本。','image_handles':[self.image()]*count})

    def select(self):
        value=current_draft_inventory.execute(self.service,{'connection_id':'A'},time.monotonic()+60)
        g=value['groups'][0]
        self.assertEqual(g['article_types'],['newspic'])
        return {'inventory_handle':value['inventory_handle'],'index':g['index'],
                'expected_projection_sha256':g['projection_sha256'],'article_count':g['article_count']}

    def document_group(self, owner='A'):
        self.groups[(owner,'document-'+owner)] = [{'article_type':'news','title':'已有图文',
            'content':'<p>本号原文</p>','thumb_media_id':'cover-'+owner,'digest':'现有摘要'}]

    def test_normal_article_create_and_edit_share_permanent_cover_contract(self):
        cover=self.call('upload_image',request_key='news-cover',source=self.source)
        self.assertEqual(cover['state'],'MEDIA_READY')
        article={'title':'本号图文','content':'<p>正文一</p>','cover_handle':cover['operation_handle']}
        with self.assertRaises(WCEError):
            self.call('create_news',service=self.other,request_key='wrong-cover',article=article)
        created=self.call('create_news',request_key='news-create',article=article)
        self.assertEqual(created['state'],'VERIFIED')
        self.assertEqual(self.call('create_news',request_key='news-create',article=article),created)
        selection=self.selections()[0]
        saved=self.call('update_news',request_key='news-edit',selection=selection,index=0,
                        changes={'content':'<p>正文二</p>','cover_handle':cover['operation_handle']})
        self.assertEqual(saved['state'],'VERIFIED')
        self.assertEqual(next(iter(self.groups.values()))[0]['content'],'<p>正文二</p>')
        self.assertEqual(self.requests.count(('A','/cgi-bin/draft/add')),1)
        self.assertEqual(self.requests.count(('A','/cgi-bin/draft/update')),1)
        self.assertFalse(any(path.startswith('/cgi-bin/freepublish/') for _,path in self.requests))

    def selections(self, service=None):
        service=service or self.service
        result=current_draft_inventory.execute(service,{'connection_id':service.policy.data['connection_id']},time.monotonic()+60)
        return [{'inventory_handle':result['inventory_handle'],'index':group['index'],
                 'expected_projection_sha256':group['projection_sha256'],'article_count':group['article_count']}
                for group in result['groups']]

    def test_documented_openid_recipient_wire_scope_status_and_limits(self):
        endpoint='/cgi-bin/message/mass/send'
        args=dict(request_key='openid-a',campaign='openid-campaign',confirm=True,
                  audience={'openids':['openid-z','openid-a']},message={'kind':'text','text':'名单测试'})
        value=self.call('send_broadcast',**args)
        self.assertEqual(value['state'],'ACCEPTED')
        self.assertEqual(value['result']['task_id'],'9007199254740993')
        self.assertEqual(self.call('send_broadcast',**(args|{'audience':{'openids':['openid-a','openid-z']}})),value)
        self.assertEqual(self.requests.count(('A',endpoint)),1)
        sent=self.payloads[-1][2]
        self.assertEqual(sent['touser'],['openid-a','openid-z'])
        self.assertNotIn('filter',sent)
        self.assertEqual(len(sent['clientmsgid']),32)
        self.assertEqual(self.call('broadcast_status',operation_handle=value['operation_handle'])['status'],'SEND_SUCCESS')
        with self.assertRaises(WCEError):
            self.call('broadcast_status',service=self.other,operation_handle=value['operation_handle'])
        for audience in (['same'],['same','same'],['openid-%05d'%n for n in range(10001)]):
            with self.assertRaises(WCEError):
                self.call('send_broadcast',**(args|{'audience':{'openids':audience}}))
        self.broadcast_error=48001
        denied=self.call('send_broadcast',service=self.other,**args)
        self.assertEqual((denied['state'],denied['error_code']),('REJECTED',48001))
        self.broadcast_error=None
        self.lose_broadcast=True
        unknown=self.call('send_broadcast',**(args|{'request_key':'openid-unknown','campaign':'openid-unknown',
              'audience':{'openids':['openid-one','openid-two']}}))
        self.assertEqual(unknown['state'],'UNKNOWN')
        with self.assertRaisesRegex(WCEError,'WECHAT_BROADCAST_ORIGINAL_REQUEST_REQUIRED'):
            self.call('send_broadcast',**(args|{'request_key':'openid-repeat','campaign':'openid-repeat',
                'audience':{'openids':['openid-two','openid-one']}}))
        self.assertEqual(self.requests.count(('A',endpoint)),2)
        self.lose_broadcast=False
        self.broadcast_duplicate=True
        maximum=['openid-%05d'%n for n in range(10000)]
        largest=self.call('send_broadcast',**(args|{'request_key':'openid-max','campaign':'openid-max',
              'audience':{'openids':maximum}}))
        self.assertEqual(largest['result']['task_id'],'9007199254740993')
        self.assertEqual(len(self.payloads[-1][2]['touser']),10000)

    def test_direct_draft_preview_and_send_use_original_media_and_live_projection(self):
        self.document_group()
        selection=self.selections()[0]
        message={'kind':'mpnews','media':{'draft_selection':selection}}
        args={'request_key':'existing-news','confirm':True,'message':message,'recipient':{'openid':'reader-A'}}
        self.assertEqual(self.call('preview_message',**args)['state'],'PREVIEW_ACCEPTED')
        self.assertEqual(self.payloads[-1][2],{'msgtype':'mpnews','mpnews':{'media_id':'document-A'},'touser':'reader-A'})
        self.assertEqual(self.call('send_broadcast',request_key='selected-broadcast',campaign='selected-broadcast',
            confirm=True,message=message,audience={'tag_id':0})['state'],'ACCEPTED')
        self.assertNotIn(('A','/cgi-bin/media/uploadnews'),self.requests)
        with self.assertRaises(WCEError):
            self.call('preview_message',service=self.other,**args)
        self.groups[('A','document-A')][0]['content']='<p>已被外部修改</p>'
        result=self.call('preview_message',**(args|{'request_key':'stale-news','recipient':{'openid':'reader-C'}}))
        self.assertEqual((result['state'],result['request_count']),('SOURCE_CHANGED',0))
        self.assertEqual(self.requests.count(('A','/cgi-bin/message/mass/preview')),1)

    def test_mixed_draft_merge_preserves_picture_order_and_all_originals_on_rejection(self):
        self.document_group()
        self.make(count=2)
        self.service.profile=Mock()
        self.service.workflow.activate=Mock()
        selections=self.selections()
        args={'connection_id':'A','request_key':'merge-rejected','selections':list(reversed(selections))}
        self.reject=True
        result=AccountService._call(self.service,'own.drafts.current.merge',args,time.monotonic()+60)
        self.assertEqual(result['state'],'ADD_REJECTED')
        self.assertEqual(self.call('draft_count')['total_count'],2)
        self.assertNotIn(('A','/cgi-bin/draft/delete'),self.requests)
        self.reject=False
        result=AccountService._call(self.service,'own.drafts.current.merge',args|{'request_key':'merge-confirmed'},time.monotonic()+60)
        self.assertEqual(result['state'],'COMPLETED')
        self.assertEqual(self.call('draft_count')['total_count'],1)
        rows=next(iter(self.groups.values()))
        self.assertEqual([row['article_type'] for row in rows],['news','newspic'])
        self.assertEqual(len(rows[1]['image_info']['image_list']),2)
        returned=AccountService._call(self.service,'own.drafts.current.merge',args|{'request_key':'merge-confirmed'},time.monotonic()+60)
        self.assertEqual(returned,result)
        self.assertEqual(self.requests.count(('A','/cgi-bin/draft/add')),3)

    def test_large_material_readback_reassembles_once_and_is_account_bound(self):
        read=self.call('material_details',media_id='large-A')
        self.assertEqual(read['body_state'],'CHUNKED')
        self.assertEqual(read['sha256'],sha256(self.large_material).hexdigest())
        data=bytearray()
        offset=0
        while offset is not None:
            chunk=self.call('material_bytes',read_handle=read['read_handle'],offset=offset)
            self.assertEqual(chunk['offset'],offset)
            data.extend(base64.b64decode(chunk['base64']))
            offset=chunk['next_offset']
        self.assertEqual(bytes(data),self.large_material)
        self.assertEqual(self.requests.count(('A','/cgi-bin/material/get_material')),1)
        with self.assertRaisesRegex(WCEError,'WECHAT_MEDIA_READ_EXPIRED'):
            self.call('material_bytes',service=self.other,read_handle=read['read_handle'],offset=0)
        with self.assertRaisesRegex(WCEError,'WECHAT_MEDIA_OFFSET_INVALID'):
            self.call('material_bytes',read_handle=read['read_handle'],offset=len(data))
        with patch('wce.wechat_content_ops.time.monotonic',return_value=time.monotonic()+301):
            with self.assertRaisesRegex(WCEError,'WECHAT_MEDIA_READ_EXPIRED'):
                self.call('material_bytes',read_handle=read['read_handle'],offset=0)

    def test_transport_only_expands_material_response_and_fails_closed_over_limit(self):
        from io import BytesIO
        exact=HTTPSender(enabled=True,safe_transport_diagnostics=True)
        def opened(data):
            reply=BytesIO(data)
            reply.code=200
            exact.opener=SimpleNamespace(open=lambda *_args,**_kwargs:reply)
        opened(self.large_material)
        path='/cgi-bin/material/get_material?access_token=fixture'
        self.assertEqual(exact.send(HTTPRequest('POST',path,{},b'{}'),2).body,self.large_material)
        opened(b'x'*(MAX_BODY+1))
        self.assertEqual(exact.send(HTTPRequest('GET','/cgi-bin/draft/count',{},b''),2).kind,'BODY_LIMIT')
        opened(b'x'*(MAX_WECHAT_MEDIA_BODY+1))
        self.assertEqual(exact.send(HTTPRequest('POST',path,{},b'{}'),2).kind,'BODY_LIMIT')

    def test_upload_create_list_update_and_original_publication(self):
        first=self.make(count=20)
        self.assertEqual(first['state'],'SAVED')
        original=first['intent_handle']
        self.assertEqual(self.make(count=20)['intent_handle'],original)
        backed=self.call('readback',operation_handle=original)
        self.assertEqual(backed['state'],'VERIFIED')
        self.assertEqual(len(backed['readback']['article']['image_info']['image_list']),20)
        self.assertEqual(backed['readback']['first_image_media_id'],'remote-image-A')
        updated=self.call('update_picture',request_key='new-text',selection=self.select(),index=0,
                          article={'title':'修改标题','content':'修改后保留原图。'})
        self.assertEqual(updated['state'],'SAVED')
        self.assertEqual(current_draft_management.publication_source(self.service.policy,updated['intent_handle']),
                         ('remote-draft-1',['修改标题']))
        args={'connection_id':'A','intent_handle':updated['intent_handle']}
        registry=Path(self.service.policy.value['registry_path'])
        for expected in ('ACCEPTED','ACCEPTED'):
            result=ordinary_publication.execute(self.service,'own.publications.current.dispatch',args,registry,time.monotonic()+60)
            self.assertEqual(result['state'],expected)
        published=ordinary_publication.execute(self.service,'own.publications.current.poll',
            args|{'intent_handle':result['intent_handle']},registry,time.monotonic()+60)
        self.assertEqual(published['state'],'PUBLISHED')
        self.assertEqual([list(row) for row in published['article_urls']],[[1,'https://mp.weixin.qq.com/s/examplelink']])
        self.assertEqual(self.requests.count(('A','/cgi-bin/freepublish/submit')),1)
        self.assertFalse(any('/message/mass' in path for _,path in self.requests))

    def test_two_accounts_rejected_and_unknown_original_request(self):
        image=self.image()
        with self.assertRaises(WCEError):
            self.call('create_picture',service=self.other,request_key='other-photos',
                      article={'title':'错号','content':'','image_handles':[image]})
        self.assertFalse(any(name=='B' for name,_ in self.requests))
        self.reject=True
        self.assertEqual(self.make()['error_code'],48001)
        self.reject=False
        self.lose_add=True
        lost=self.make(key='lost',title='未知')
        self.assertEqual(lost['state'],'UNKNOWN')
        self.assertEqual(self.call('status_by_key',request_key='lost')['operation_handle'],lost['operation_handle'])
        self.assertEqual(self.make(key='same-intent',title='未知')['state'],'UNKNOWN')
        self.assertEqual(self.requests.count(('A','/cgi-bin/draft/add')),2)

    def test_unknown_update_recovers_by_original_readback_without_resend(self):
        self.make()
        self.lose_update=True
        snapshot=self.select()
        data={'title':'仅成功一次','content':'更改正文'}
        lost=self.call('update_picture',request_key='update-unknown',selection=snapshot,index=0,article=data)
        self.assertEqual(lost['state'],'UNKNOWN')
        recovered=self.call('readback',operation_handle=lost['operation_handle'])
        self.assertEqual(recovered['state'],'VERIFIED')
        self.assertEqual(recovered['intent_handle'],lost['operation_handle'])
        self.assertEqual(self.requests.count(('A','/cgi-bin/draft/update')),1)

    def test_materials_product_and_publication_management(self):
        self.assertEqual(self.call('material_counts')['counts']['news_count'],0)
        media=self.call('upload_media',request_key='sound-one',media_type='voice',lifetime='temporary',
            mime_type='audio/amr',base64=base64.b64encode(b'#!AMR\nexample').decode())
        self.assertGreater(media['result']['expires_at'],time.time())
        reply=self.call('temporary_details',operation_handle=media['operation_handle'])
        self.assertEqual(base64.b64decode(reply['base64']),b'#!AMR\nexample')
        with self.assertRaises(WCEError):
            self.call('temporary_details',service=self.other,operation_handle=media['operation_handle'])
        self.assertEqual(self.call('product_card',product_id='product',article_type='newspic',card_type=2),
                         {'state':'OBSERVED','product':{'product_key':'authorized-product'}})
        rows=self.call('list_published')['items']
        self.assertEqual(rows[0]['article_id'],'published-A')
        item=self.call('read_published',article_id='published-A')
        self.assertEqual(item['content'],'<p>样稿</p>')
        for _ in range(2):
            result=self.call('delete_published',request_key='delete-one',article_id='published-A',index=1,confirm=True)
            self.assertEqual(result['state'],'COMPLETED')
        self.assertEqual(self.requests.count(('A','/cgi-bin/freepublish/delete')),1)

    def test_distinct_preview_and_broadcast_routes_and_unknown_duplicate(self):
        handle=self.image()
        preview=self.call('preview_message',request_key='preview-one',recipient={'wechat_name':'inspector'},
                          message={'kind':'image','media':{'media_handle':handle}},confirm=True)
        self.assertEqual(preview['state'],'PREVIEW_ACCEPTED')
        self.assertEqual(self.payloads[-1][2],{'image':{'media_id':'remote-image-A'},'msgtype':'image','towxname':'inspector'})
        broadcast=self.call('send_broadcast',request_key='send-one',campaign='campaign-one',audience={'tag_id':5},
                            message={'kind':'image','image_handles':[handle,handle]},confirm=True)
        payload=self.payloads[-1][2]
        self.assertEqual(payload['filter'],{'is_to_all':False,'tag_id':5})
        self.assertEqual(payload['images'],{'media_ids':['remote-image-A','remote-image-A']})
        self.assertEqual(len(payload['clientmsgid']),32)
        self.assertEqual(broadcast['result']['task_id'],'9007199254740993')
        self.assertEqual(self.call('broadcast_status',operation_handle=broadcast['operation_handle'])['status'],'SEND_SUCCESS')
        self.lose_broadcast=True
        args={'audience':{'all_followers':True},'message':{'kind':'text','text':'隔离群发'},'confirm':True}
        first=self.call('send_broadcast',request_key='unknown-send',campaign='campaign-two',**args)
        self.assertEqual(first['state'],'UNKNOWN')
        self.assertEqual(self.call('send_broadcast',request_key='unknown-alias',campaign='campaign-two',**args),
                         first)
        with self.assertRaisesRegex(WCEError,'ORIGINAL_REQUEST'):
            self.call('send_broadcast',request_key='new-key',campaign='mismatched',**args)
        self.assertEqual(self.requests.count(('A','/cgi-bin/message/mass/sendall')),2)
        extra=self.call('preview_message',request_key='music-preview',recipient={'openid':'remote-user'},
                        message={'kind':'music','music_media_id':'remote-music'},confirm=True)
        self.assertEqual(extra['state'],'PREVIEW_ACCEPTED')
        with self.assertRaises(WCEError):
            self.call('send_broadcast',request_key='bad',campaign='bad',audience={'all_followers':True},
                      message={'kind':'music','music_media_id':'remote-music'},confirm=True)

    def test_photo_limits_order_comment_crop_and_product(self):
        first=self.image()
        # A contrast image is registered through the same real uploader; both
        # exact strings in the official request are checked, not just the count.
        import struct
        import zlib
        def chunk(name, body):
            return struct.pack('>I',len(body))+name+body+struct.pack('>I',zlib.crc32(name+body))
        png=b'\x89PNG\r\n\x1a\n'+chunk(b'IHDR',struct.pack('>IIBBBBB',1,1,8,2,0,0,0))
        png+=chunk(b'IDAT',zlib.compress(b'\x00\xff\x00\x00'))+chunk(b'IEND',b'')
        second=self.call('upload_image',request_key='second-image',source={'mime_type':'image/png',
            'base64':base64.b64encode(png).decode()})['operation_handle']
        with self.assertRaises(WCEError):
            self.make(key='too-many',count=21)
        with self.assertRaisesRegex(WCEError,'TEXT_REQUIRED'):
            self.call('create_picture',request_key='bad-short-text',
                      article={'title':'错误','content':'<p>HTML</p>','image_handles':[first]})
        props={'title':'顺序','content':'2 < 3','image_handles':[second,first],'need_open_comment':1,
            'only_fans_can_comment':1,'product_key':'authorized-product',
            'cover_info':{'crop_percent_list':[{'ratio':'16_9','x1':'0','y1':'0','x2':'1','y2':'1'}]}}
        row=self.call('create_picture',request_key='oriented',article=props)
        back=self.call('readback',operation_handle=row['operation_handle'])['readback']['article']
        self.assertEqual([x['image_media_id'] for x in back['image_info']['image_list']],
                         ['remote-image-A2','remote-image-A'])
        self.assertEqual(back['need_open_comment'],1)
        self.assertEqual(back['product_info']['footer_product_info']['product_key'],'authorized-product')
        self.assertEqual(back['cover_info'],props['cover_info'])

    def test_news_voice_video_and_card_request_shapes(self):
        self.groups[('A','news-draft')]=[{'title':'同号文章','content':'<p>示例</p>',
                                       'thumb_media_id':'remote-cover','need_open_comment':1}]
        result=current_draft_inventory.execute(self.service,{'connection_id':'A'},time.monotonic()+60)
        g=result['groups'][0]
        selected={'inventory_handle':result['inventory_handle'],'index':0,
                  'expected_projection_sha256':g['projection_sha256'],'article_count':1}
        news=self.call('prepare_broadcast_news',request_key='news-src',selection=selected)
        voice=self.call('upload_media',request_key='voice-src',media_type='voice',lifetime='temporary',
            mime_type='audio/amr',base64=base64.b64encode(b'#!AMR\nexample').decode())
        video=self.call('upload_media',request_key='video-src',media_type='video',lifetime='permanent',
            mime_type='video/mp4',base64=base64.b64encode(b'\0\0\0\x18ftypisomcandidate').decode(),
            video_description={'title':'视频标题','introduction':'视频说明'})
        for kind,source in [('mpnews',news),('voice',voice),('mpvideo',video)]:
            message={'kind':kind,'media':{'media_handle':source['operation_handle']}}
            self.assertEqual(self.call('preview_message',request_key='preview-'+kind,
                recipient={'openid':'inspector'},message=message,confirm=True)['state'],'PREVIEW_ACCEPTED')
            self.assertEqual(self.payloads[-1][2][kind]['media_id'],source['result']['media_id'])
            self.assertEqual(self.call('send_broadcast',request_key='send-'+kind,campaign='campaign-'+kind,
                audience={'all_followers':True},message=message,confirm=True)['state'],'ACCEPTED')
            self.assertIn(kind,self.payloads[-1][2])
        card=self.call('preview_message',request_key='preview-card',recipient={'openid':'inspector'},confirm=True,
            message={'kind':'wxcard','card':{'card_id':'same-account-card','card_ext':{'signature':'fixture-signature'}}})
        self.assertEqual(card['state'],'PREVIEW_ACCEPTED')
        self.assertEqual(self.payloads[-1][2]['wxcard']['card_ext']['signature'],'fixture-signature')

    def test_local_video_file_over_inline_limit_reaches_broker_without_bytes_in_ipc(self):
        from wce.own_bootstrap_security import path_check
        fixture = self.base / 'recording.mp4'
        fixture.write_bytes(b'\0\0\0\x18ftypisom' + b'\x11' * (3 * 1024 * 1024))
        entries = self.service.policy.root / 'images'
        entries.mkdir(mode=0o700)
        self.service.policy.image_pin=path_check(entries,True)
        def local_broker(policy,name,args):
            self.assertNotIn('absolute_path',args)
            self.assertNotIn('base64',args)
            return AccountService._call(self.service,name,args,time.monotonic()+30)
        def capture(account,request,timeout):
            # Exercise the real concrete transport request validation, then
            # emulate the application response without opening a network connection.
            HTTPSender(enabled=True)._prepare_request(request,timeout)
            self.assertGreater(len(request.body),3*1024*1024)
            self.assertIn(b'Content-Type: video/mp4',request.body)
            return response({'media_id':'same-account-video'})
        self.service.workflow.sender.send=lambda request,timeout:capture('A',request,timeout)
        with patch('wce.own_connection_policy.resolve',return_value=self.service.policy), \
             patch('wce.own_connection_broker.ensure_started'), \
             patch('wce.own_connection_broker.call',side_effect=local_broker):
            router=wechat_content.ContentRouter(SimpleNamespace(registry=None,launcher=None))
            result=router.call(wechat_content.TOOL,{'action':'upload_media_file','connection_id':'A',
                'request_key':'large-local','media_type':'video','lifetime':'permanent','mime_type':'video/mp4',
                'absolute_path':str(fixture),'video_description':{'title':'视频','introduction':'测试'}})
        self.assertEqual(result['result']['media_id'],'same-account-video')

    def test_official_duplicate_receipt_uses_provider_original_task(self):
        self.broadcast_duplicate=True
        args={'request_key':'original-duplicate','campaign':'original-activity','audience':{'tag_id':3},
              'message':{'kind':'text','text':'当天原任务'},'confirm':True}
        result=self.call('send_broadcast',**args)
        self.assertEqual(result['state'],'ACCEPTED')
        self.assertEqual(result['result']['task_id'],'9007199254740993')
        self.assertEqual(self.call('send_broadcast',**args),result)
        self.assertEqual(self.requests.count(('A','/cgi-bin/message/mass/sendall')),1)

    def test_picture_update_without_changes_preserves_original_without_write(self):
        self.make()
        result=self.call('update_picture',request_key='unchanged',selection=self.select(),index=0,
                         article={'title':'图片消息','content':'一段纯文本。'})
        self.assertEqual(result['state'],'UNCHANGED')
        self.assertEqual(result['request_count'],0)
        self.assertEqual(current_draft_management.publication_source(self.service.policy,result['intent_handle']),
                         ('remote-draft-1',['图片消息']))
        self.assertNotIn(('A','/cgi-bin/draft/update'),self.requests)


if __name__ == '__main__':
    unittest.main()
