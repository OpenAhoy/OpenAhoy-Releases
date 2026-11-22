"""Supplementary official material, publication, and delivery endpoints."""
from copy import deepcopy
import base64
import binascii
from hashlib import sha256
import secrets
import time
from urllib.parse import urlencode

from .contracts import WCEError
from .http_transport import HTTPRequest, MAX_BODY, MAX_WECHAT_MEDIA_BODY, TransportFailure
from .own_draft_wire import reference_valid, response_value
from .tools import schema
from . import current_draft_management as managed
from . import draft_group_wire as wire
from . import upload_wire


MEDIA = {'type': 'string', 'minLength': 1, 'maxLength': 128}
TEXT = {'type': 'string', 'minLength': 1, 'maxLength': 2048}
TYPE = {'type': 'string', 'enum': ['image', 'voice', 'video', 'thumb']}
TYPE_LIST = {'type': 'string', 'enum': ['image', 'voice', 'video', 'news']}
ACK = {'type': 'boolean', 'const': True}
SEQ = {'type': 'integer', 'minimum': 1, 'maximum': 8}


def specs(action, key, handle, page, inline_max):
    card = schema({'card_id': MEDIA}, {'card_ext': schema({}, {
        name: TEXT for name in ('code', 'openid', 'timestamp', 'nonce_str', 'signature')})})
    variants = [schema({'kind': {'type': 'string', 'const': name}, **body})
                for name, body in [('text', {'text': TEXT}), ('wxcard', {'card': card}),
                    ('music', {'music_media_id': MEDIA})]]
    from .current_draft_management_protocol import SELECTION
    for name in ('mpnews', 'voice', 'mpvideo'):
        media = [schema({'media_handle': handle})]
        if name=='mpnews':
            media.append(schema({'draft_selection': SELECTION}))
        variants.append(schema({'kind': {'type': 'string', 'const': name},
                                'media': {'oneOf': media}},
            {'send_ignore_reprint': {'type': 'integer', 'enum': [0, 1]}} if name=='mpnews' else {}))
    preview_image = schema({'kind':{'type':'string','const':'image'},'media':schema({'media_handle':handle})})
    send_images = schema({'kind':{'type':'string','const':'image'},
        'image_handles':{'type':'array','minItems':1,'maxItems':20,'items':handle}},
        {'recommend':TEXT,'title':TEXT,'need_open_comment':{'type':'integer','enum':[0,1]},
         'only_fans_can_comment':{'type':'integer','enum':[0,1]}})
    preview = {'oneOf': [schema({'openid': MEDIA}), schema({'wechat_name': MEDIA})]}
    recipients = {'oneOf': [schema({'all_followers': ACK}),
                             schema({'tag_id': {'type': 'integer', 'minimum': 0, 'maximum': 2**31-1}}),
                             schema({'openids': {'type':'array', 'minItems':2,'maxItems':10000,'items':MEDIA}})]}
    media_required={'request_key':key,'media_type':TYPE,
                    'lifetime':{'type':'string','enum':['temporary','permanent']},
                    'mime_type':{'type':'string','enum':list(MIME_EXT)}}
    media_optional={'video_description':schema({'title':TEXT,'introduction':TEXT})}
    return {
        'material_counts': action('material_counts', {}),
        'draft_count': action('draft_count', {}),
        'list_materials': action('list_materials', {'media_type': TYPE_LIST}, page),
        'material_details': action('material_details', {'media_id': MEDIA}),
        'material_bytes': action('material_bytes', {
            'read_handle':{'type':'string','pattern':'^wx-media-read-[a-f0-9]{32}$'},
            'offset':{'type':'integer','minimum':0,'maximum':MAX_WECHAT_MEDIA_BODY-1}}),
        'temporary_details': action('temporary_details', {'operation_handle': handle}),
        'high_quality_voice': action('high_quality_voice', {'operation_handle': handle}),
        'upload_media': action('upload_media', {**media_required,
            'base64': {'type': 'string', 'minLength': 4, 'maxLength': 4*((inline_max+2)//3)}},
            media_optional),
        'upload_media_file': action('upload_media_file', {**media_required,
            'absolute_path':{'type':'string','minLength':1,'maxLength':4096}},media_optional),
        'delete_material': action('delete_material', {'request_key': key, 'media_id': MEDIA, 'confirm': ACK}),
        'list_published': action('list_published', {}, page),
        'read_published': action('read_published', {'article_id': MEDIA},
            {'index': SEQ, 'content_offset': {'type': 'integer', 'minimum': 0, 'maximum': 20000}}),
        'delete_published': action('delete_published', {'request_key': key, 'article_id': MEDIA,
            'index': SEQ, 'confirm': ACK}),
        'product_card': action('product_card', {'product_id': MEDIA,
            'article_type': {'type': 'string', 'enum':['news','newspic']},
            'card_type': {'type': 'integer', 'enum':[0,1,2,3]}}),
        'prepare_broadcast_news': action('prepare_broadcast_news', {'request_key': key, 'selection': SELECTION}),
        'preview_message': action('preview_message', {'request_key': key,
            'recipient': preview, 'message': {'oneOf': variants+[preview_image]}, 'confirm': ACK}),
        'send_broadcast': action('send_broadcast', {'request_key': key, 'campaign': key,
            'audience': recipients, 'message': {'oneOf':[v for v in variants
                if v['properties']['kind']['const']!='music']+[send_images]}, 'confirm': ACK}),
        'broadcast_status': action('broadcast_status', {'operation_handle': handle}),
        'delete_broadcast_article': action('delete_broadcast_article', {'request_key': key,
            'operation_handle': handle, 'index': SEQ, 'confirm': ACK}),
        'broadcast_speed': action('broadcast_speed', {}),
        'set_broadcast_speed': action('set_broadcast_speed', {'request_key':key, 'confirm':ACK,
            'speed':{'type':'integer','minimum':0,'maximum':4}}),
    }


MIME_EXT = {'image/jpeg': 'jpg', 'image/png': 'png', 'image/gif': 'gif',
            'audio/mpeg':'mp3','audio/amr':'amr','video/mp4':'mp4'}
READS = {'material_counts', 'draft_count', 'list_materials', 'material_details', 'material_bytes', 'temporary_details',
         'high_quality_voice', 'list_published', 'read_published', 'product_card',
         'broadcast_status', 'broadcast_speed'}
WECHAT_API = 'https://developers.weixin.qq.com/doc/subscription/api/'


def fail(code):
    raise WCEError(code)


def _opaque(value):
    if not reference_valid(value):
        fail('WECHAT_MEDIA_REFERENCE_INVALID')
    return value


def _get(client, path, fields=None):
    fields = fields or {}
    token = client.secret
    if upload_wire.contains_secret(fields,token):
        fail('REQUEST_SECRET_REFLECTION')
    query = {'access_token': upload_wire.secret_value(token), **fields}
    return client.send(HTTPRequest('GET',path+'?'+urlencode(query),{},b''))


def _post(client, path, payload):
    from .wechat_content import _request
    return client.send(_request(path,payload,client.secret))


def _value(response, client):
    try:
        return response_value(response, client.secret, list_response=True)
    except WCEError:
        fail('WECHAT_CONTENT_RESULT_UNDETERMINED')


def _delivery_value(response, client):
    from .publication_contract import strict_json
    if (type(response.status) is not int or not 200<=response.status<300
            or upload_wire.contains_secret(response.body,client.secret, max_nodes=16384)):
        fail('WECHAT_CONTENT_RESULT_UNDETERMINED')
    value=strict_json(response.body,128*1024)
    if (type(value) is not dict or type(value.get('errcode',0)) is not int
            or upload_wire.contains_secret(value,client.secret, max_nodes=16384)):
        fail('WECHAT_CONTENT_RESULT_UNDETERMINED')
    return value


def _observed(value, **result):
    if value.get('errcode',0):
        return {'state':'REJECTED','error_code':value['errcode']}
    return {'state':'OBSERVED',**result}


def _read_media(raw,client):
    if isinstance(raw,TransportFailure) and raw.kind=='BODY_LIMIT':
        fail('WECHAT_MEDIA_BODY_LIMIT')
    if (isinstance(raw,TransportFailure) or type(raw.status) is not int or not 200 <= raw.status < 300
            or not 0 < len(raw.body) <= MAX_WECHAT_MEDIA_BODY or upload_wire.contains_secret(raw.body,client.secret)):
        fail('WECHAT_CONTENT_RESULT_UNDETERMINED')
    if raw.body.lstrip()[:1] == b'{':
        value=_value(raw,client)
        allowed={k:value[k] for k in ('title','description','down_url','video_url','voice_url','item','news_item')
                 if k in value}
        return _observed(value,details=allowed)
    mime=_mime(raw.body)
    if mime is None:
        fail('WECHAT_MEDIA_TYPE_UNVERIFIED')
    result={'mime_type':mime,'bytes':len(raw.body),'sha256':sha256(raw.body).hexdigest()}
    if len(raw.body)<=700*1024:
        result['base64']=base64.b64encode(raw.body).decode()
    else:
        client.guard()
        # The broker serializes calls for this account. Keep at most two
        # short-lived bodies in its memory, never in logs or the operation journal.
        cache=getattr(client.service,'wechat_material_reads',None)
        if cache is None:
            client.service.wechat_material_reads=cache={}
        now=time.monotonic()
        for handle,item in list(cache.items()):
            if now>=item[0] or item[1]!=client.binding_sha:
                del cache[handle]
        if len(cache)>=2:
            del cache[next(iter(cache))]
        handle='wx-media-read-'+secrets.token_hex(16)
        cache[handle]=(now+300,client.binding_sha,result['sha256'],raw.body)
        result.update(body_state='CHUNKED',read_handle=handle)
    return {'state':'OBSERVED',**result}


def _material_chunk(client,args):
    item=getattr(client.service,'wechat_material_reads',{}).get(args['read_handle'])
    if item is None or time.monotonic()>=item[0] or item[1]!=client.binding_sha:
        fail('WECHAT_MEDIA_READ_EXPIRED')
    _,_,digest,data=item
    start=args['offset']
    if start>=len(data):
        fail('WECHAT_MEDIA_OFFSET_INVALID')
    end=min(start+512*1024,len(data))
    return {'state':'OBSERVED','offset':start,'next_offset':end if end<len(data) else None,
            'bytes':len(data),'sha256':digest,'base64':base64.b64encode(data[start:end]).decode()}


def _mime(data):
    if data.startswith(b'\xff\xd8\xff'):return 'image/jpeg'
    if data.startswith(b'\x89PNG\r\n\x1a\n'):return 'image/png'
    if data.startswith((b'GIF87a',b'GIF89a')):return 'image/gif'
    if data.startswith(b'#!AMR\n'):return 'audio/amr'
    if data.startswith(b'#!AMR-WB\n'):return 'audio/amr'
    if data.startswith(b'BM') and len(data)>=54:return 'image/bmp'
    if data.startswith(b'RIFF') and data[8:12]==b'WAVE':return 'audio/wav'
    if data.startswith(bytes.fromhex('3026b2758e66cf11a6d900aa0062ce6c')):return 'audio/x-ms-wma'
    if data.startswith(b'ID3') or len(data)>3 and data[0]==255 and data[1]&0xe0==0xe0:return 'audio/mpeg'
    if data[4:8]==b'ftyp':return 'video/mp4'
    return None


def _multipart(client,args):
    mime=args['mime_type'];kind=args['media_type'];lifetime=args['lifetime']
    if 'staged_media' in args:
        from .bounded_file import MAX_WECHAT_VIDEO_BYTES
        from .own_connection_input import verify_content_media
        data=verify_content_media(client.policy,args['staged_media'],MIME_EXT[mime])
        maximum=MAX_WECHAT_VIDEO_BYTES if kind=='video' else MAX_BODY
    else:
        try:data=base64.b64decode(args['base64'],validate=True)
        except (ValueError,binascii.Error):fail('WECHAT_MEDIA_INVALID')
        maximum=700*1024
    if _mime(data)!=mime or not 0<len(data)<=maximum:
        fail('WECHAT_MEDIA_INVALID')
    permitted={'image':{'image/jpeg','image/png','image/gif'},'thumb':{'image/jpeg'},
               'voice':{'audio/mpeg','audio/amr'},'video':{'video/mp4'}}
    if mime not in permitted[kind] or kind=='thumb' and len(data)>64*1024:
        fail('WECHAT_MEDIA_TYPE_UNVERIFIED')
    if mime in {'image/jpeg','image/png'}:
        from .local_preparation import image_check
        image_check(data,mime)
    description=args.get('video_description')
    if bool(description)!=(kind=='video' and lifetime=='permanent'):
        fail('WECHAT_VIDEO_DESCRIPTION_MISMATCH')
    secret=client.secret
    boundary='wce-'+secrets.token_hex(16)
    if boundary.encode() in data or upload_wire.contains_secret((data,description),secret):
        fail('REQUEST_SECRET_REFLECTION')
    prefixes=(f'--{boundary}\r\nContent-Disposition: form-data; name="media"; filename="asset.{MIME_EXT[mime]}"\r\n'
              f'Content-Type: {mime}\r\n\r\n').encode()
    body=prefixes+data+b'\r\n'
    if description:
        body+=(f'--{boundary}\r\nContent-Disposition: form-data; name="description"\r\n'
               'Content-Type: application/json; charset=utf-8\r\n\r\n').encode()+wire.canonical(description).encode()+b'\r\n'
    body+=f'--{boundary}--\r\n'.encode()
    if kind!='video' and len(body)>MAX_BODY:
        fail('WECHAT_CONTENT_TRANSPORT_LIMIT')
    query=urlencode({'access_token':upload_wire.secret_value(secret),'type':kind})
    path='/cgi-bin/material/add_material' if lifetime=='permanent' else '/cgi-bin/media/upload'
    metadata={'media_type':kind,'lifetime':lifetime,'sha256':sha256(data).hexdigest(),
              'mime_type':mime,'video_description':description}
    return HTTPRequest('POST',path+'?'+query,{'Content-Type':'multipart/form-data; boundary='+boundary},body),metadata


def _record(db,client,args,action,payload,path=None,request=None,identity=None,preflight=None):
    from .wechat_content import _reserve,_request,_at_send,_finish,public
    row=_reserve(db,client.policy,args['request_key'],action,identity or payload)
    if row['state']!='PREPARED':
        return public(row)
    if preflight is not None:
        try:
            rejected=preflight()
        except WCEError as error:
            if error.code=='CURRENT_DRAFT_SELECTION_CHANGED':
                return _finish(db,client,row,'SOURCE_CHANGED')
            raise
        if rejected is not None:
            return _finish(db,client,row,'REJECTED',error_code=rejected)
    raw=client.send(request or _request(path,payload,client.secret),
                    before_http=lambda:_at_send(db,row),capability='draft_save')
    try:
        value=(_delivery_value(raw,client) if action in {'preview_message','send_broadcast'}
               else response_value(raw,client.secret))
    except WCEError:return public(row)
    code=value.get('errcode',0)
    # The provider returns the existing original msg_id when a clientmsgid is
    # already accepted. Keep that task on this original request.
    task=value.get('msg_id')
    valid_task=type(task) is int and 0<task<2**64
    if code and valid_task and not (action=='send_broadcast' and code==45065):
        return public(row)
    if code and not (action=='send_broadcast' and code==45065 and valid_task):
        return _finish(db,client,row,'REJECTED',error_code=code)
    if action in {'upload_media','prepare_broadcast_news'}:
        media_id=value.get('thumb_media_id',value.get('media_id'))
        if not reference_valid(media_id):
            return public(row)
        result={'media_id':media_id}
        if action=='upload_media':
            result['media_type']=args['media_type']
            result['lifetime']=args['lifetime']
            if result['lifetime']=='temporary':
                created=value.get('created_at')
                if type(created) is not int or created<=0:
                    return public(row)
                result['expires_at']=created+3*86400
        return _finish(db,client,row,'MEDIA_READY', result=result)
    if action=='preview_message':
        if value.get('errcode')!=0:
            return public(row)
        return _finish(db,client,row,'PREVIEW_ACCEPTED')
    if action=='send_broadcast':
        if not valid_task or 'errcode' not in value:
            return public(row)
        return _finish(db,client,row,'ACCEPTED',result={'task_id':str(task)})
    if value.get('errcode')!=0:
        return public(row)
    return _finish(db,client,row,'COMPLETED')


def _original(db,client,handle,kinds):
    from .wechat_content import _operation
    row=_operation(db,client.policy,handle=handle)
    if row['kind'] not in kinds:
        fail('WECHAT_CONTENT_OPERATION_NOT_FOUND')
    return row


def _media_reference(db,client,handle,kind):
    row=_original(db,client,handle,{'upload_image','upload_media','prepare_broadcast_news'})
    if row['state']!='MEDIA_READY':
        fail('WECHAT_MEDIA_NOT_READY')
    media=row['result'];expires=media.get('expires_at')
    if expires is not None and time.time()>=expires:
        fail('WECHAT_TEMPORARY_MEDIA_EXPIRED')
    actual={'upload_image':'image','prepare_broadcast_news':'mpnews'}.get(row['kind'],media.get('media_type'))
    expected={'mpvideo':'video'}.get(kind,kind)
    if actual!=expected or 'media_id' not in media:
        fail('WECHAT_MEDIA_TYPE_MISMATCH')
    return media['media_id']


def _message(db,client,args,action):
    message=args['message'];kind=message['kind']
    target=None
    if kind=='text':
        payload={'content':message['text']}
    elif kind=='wxcard':
        payload=deepcopy(message['card'])
        _opaque(payload['card_id'])
        if action=='send_broadcast' and 'card_ext' in payload:
            fail('WECHAT_MASS_CARD_EXT_NOT_SUPPORTED')
    elif kind=='music':
        payload={'media_id':_opaque(message['music_media_id'])}
    elif kind=='image' and action=='send_broadcast':
        payload={'media_ids':[_media_reference(db,client,handle,'image') for handle in message['image_handles']],
                 **{k:message[k] for k in ('recommend','title','need_open_comment','only_fans_can_comment') if k in message}}
    elif kind=='mpnews' and 'draft_selection' in message['media']:
        target=managed.selected(client.policy,message['media']['draft_selection'],client.guard)
        if any(row.get('article_type','news')!='news' for row in target['projection']['response']['news_item']):
            fail('WECHAT_BROADCAST_NEWS_REQUIRES_NEWS')
        payload={'media_id':target['reference']}
    else:
        payload={'media_id':_media_reference(db,client,message['media']['media_handle'],kind)}
    body={'msgtype':kind,('images' if kind=='image' and action=='send_broadcast' else kind):payload}
    def check_draft():
        observed=client.snapshot(target['reference'])
        if wire.digest(wire.baseline_projection(observed))!=target['projection_sha256']:
            fail('CURRENT_DRAFT_SELECTION_CHANGED')

    before_send=check_draft if target is not None else None
    draft_sha={'draft_sha':target['projection_sha256']} if target is not None else {}
    if action=='preview_message':
        recipient=args['recipient']
        if 'openid' in recipient:
            body['touser']=_opaque(recipient['openid'])
        else:
            body['towxname']=_opaque(recipient['wechat_name'])
        return _record(db,client,args,action,body,'/cgi-bin/message/mass/preview',
                       identity={**body,**draft_sha},preflight=before_send)
    audience=args['audience']
    path='/cgi-bin/message/mass/sendall'
    if 'openids' in audience:
        openids=sorted(_opaque(value) for value in audience['openids'])
        if len(set(openids))!=len(openids):
            fail('WECHAT_BROADCAST_DUPLICATE_RECIPIENTS')
        path='/cgi-bin/message/mass/send'
        body['touser']=openids
        if kind=='mpvideo':
            body['msgtype']='video'  # Service-account OpenID route defines video + mpvideo object.
    else:
        body['filter']=({'is_to_all':True} if 'all_followers' in audience
                        else {'is_to_all':False,'tag_id':audience['tag_id']})
    if kind=='mpnews':
        body['send_ignore_reprint']=message.get('send_ignore_reprint',0)
    delivery_sha=wire.digest(body)
    prior=db.execute("SELECT handle FROM operations WHERE json_extract(row_json,'$.kind')='send_broadcast' "
        "AND json_extract(row_json,'$.state')='UNKNOWN' AND json_extract(row_json,'$.intent.delivery_sha')=?",
        (delivery_sha,)).fetchone()
    if prior is not None:
        original=_original(db,client,prior[0],{'send_broadcast'})
        if original['intent']['campaign']!=args['campaign']:
            fail('WECHAT_BROADCAST_ORIGINAL_REQUEST_REQUIRED')
    body['clientmsgid']=wire.digest([client.binding_sha,args['campaign'],body])[:32]
    return _record(db,client,args,action,body,path,preflight=before_send,
                   identity={'delivery_sha':delivery_sha,'campaign':args['campaign'],**draft_sha})


def _published(client, reference):
    result=_value(_post(client,'/cgi-bin/freepublish/getarticle',{'article_id':_opaque(reference)}),client)
    if result.get('errcode',0):
        return result,[]
    news=result.get('news_item')
    if type(news) is not list or not 1<=len(news)<=8 or any(type(row) is not dict for row in news):
        fail('WECHAT_PUBLISHED_ARTICLE_UNVERIFIED')
    return result,news


def execute(db,client,args,action):
    if action=='draft_count':
        value=_value(_get(client,'/cgi-bin/draft/count'),client)
        count=value.get('total_count')
        if not value.get('errcode',0) and (type(count) is not int or count<0):
            fail('WECHAT_DRAFT_COUNT_UNVERIFIED')
        return _observed(value,total_count=count)
    if action=='material_counts':
        value=_value(_get(client,'/cgi-bin/material/get_materialcount'),client)
        return _observed(value,counts={k:value[k] for k in ('voice_count','video_count','image_count','news_count') if k in value and type(value[k]) is int})
    if action=='list_materials':
        value=_value(_post(client,'/cgi-bin/material/batchget_material',
            {'type':args['media_type'],'offset':args.get('offset',0),'count':args.get('count',20)}),client)
        items=value.get('item',[])
        if type(items) is not list or len(items)>20:fail('WECHAT_MATERIAL_LIST_UNVERIFIED')
        return _observed(value,total_count=value.get('total_count'),items=[{k:item[k] for k in
            ('media_id','name','update_time','url') if k in item} for item in items if type(item) is dict])
    if action=='material_details':
        return _read_media(_post(client,'/cgi-bin/material/get_material',{'media_id':_opaque(args['media_id'])}),client)
    if action=='material_bytes':
        return _material_chunk(client,args)
    if action in {'temporary_details','high_quality_voice'}:
        row=_original(db,client,args['operation_handle'],{'upload_media'})
        media=row.get('result',{})
        if media.get('lifetime')!='temporary' or media.get('expires_at',0)<=time.time():
            fail('WECHAT_TEMPORARY_MEDIA_EXPIRED')
        if action=='high_quality_voice' and media.get('media_type')!='voice':
            fail('WECHAT_MEDIA_TYPE_MISMATCH')
        path='/cgi-bin/media/get/jssdk' if action=='high_quality_voice' else '/cgi-bin/media/get'
        return _read_media(_get(client,path,{'media_id':media['media_id']}),client)
    if action in {'upload_media','upload_media_file'}:
        request,identity=_multipart(client,args)
        return _record(db,client,args,'upload_media',None,request=request,identity=identity)
    if action=='delete_material':
        reference=_opaque(args['media_id'])
        return _record(db,client,args,action,{'media_id':reference},'/cgi-bin/material/del_material')
    if action=='list_published':
        value=_value(_post(client,'/cgi-bin/freepublish/batchget',{'offset':args.get('offset',0),
            'count':args.get('count',20),'no_content':1}),client)
        items=value.get('item',[])
        if type(items) is not list or len(items)>20:fail('WECHAT_PUBLISHED_LIST_UNVERIFIED')
        return _observed(value,total_count=value.get('total_count'),items=items)
    if action=='delete_published':
        def preflight():
            value,news=_published(client,args['article_id'])
            if value.get('errcode',0):return value['errcode']
            if args['index']>len(news):fail('WECHAT_PUBLISHED_INDEX_INVALID')
        return _record(db,client,args,action,{'article_id':_opaque(args['article_id']),'index':args['index']},
                       '/cgi-bin/freepublish/delete',preflight=preflight)
    if action=='read_published':
        value,news=_published(client,args['article_id'])
        if value.get('errcode',0):return _observed(value)
        index=args.get('index',1)
        if not 1<=index<=len(news):fail('WECHAT_PUBLISHED_INDEX_INVALID')
        article=deepcopy(news[index-1]);text=article.pop('content','')
        offset=args.get('content_offset',0)
        if type(text) is not str or offset>len(text):fail('WECHAT_PUBLISHED_CONTENT_UNVERIFIED')
        end=min(len(text),offset+12000)
        return _observed(value,article=article,article_count=len(news),index=index,
                         content=text[offset:end],next_content_offset=end if end<len(text) else None)
    if action=='product_card':
        value=_value(_post(client,'/channels/ec/service/product/getcardinfo',{k:args[k] for k in
            ('product_id','article_type','card_type')}),client)
        return _observed(value,product={k:value[k] for k in ('product_key','DOM') if type(value.get(k)) is str})
    if action=='prepare_broadcast_news':
        selection=managed.selected(client.policy,args['selection'],client.guard)
        rows=selection['projection']['response']['news_item']
        if any(row.get('article_type','news')!='news' for row in rows):
            fail('WECHAT_BROADCAST_NEWS_REQUIRES_NEWS')
        allowed={'thumb_media_id','author','title','content_source_url','content','digest',
                 'need_open_comment','only_fans_can_comment'}
        articles=[{k:v for k,v in row.items() if k in allowed} for row in rows]
        return _record(db,client,args,action,{'articles':articles},'/cgi-bin/media/uploadnews')
    if action in {'preview_message','send_broadcast'}:
        return _message(db,client,args,action)
    if action in {'broadcast_status','delete_broadcast_article'}:
        row=_original(db,client,args['operation_handle'],{'send_broadcast'})
        if row['state']!='ACCEPTED':
            from .wechat_content import public
            return public(row)
        task=int(row['result']['task_id'])
        if action=='broadcast_status':
            value=_delivery_value(_post(client,'/cgi-bin/message/mass/get',{'msg_id':task}),client)
            if value.get('errcode',0):return _observed(value)
            from .publication_wire import MASS_STATES
            if (type(value.get('msg_id')) not in {int,str} or str(value['msg_id'])!=str(task)
                    or type(value.get('msg_status')) is not str or value['msg_status'] not in MASS_STATES):
                fail('WECHAT_BROADCAST_STATUS_UNVERIFIED')
            return _observed(value,task_id=str(task),status=value['msg_status'])
        return _record(db,client,args,action,{'msg_id':task,'article_idx':args['index']},'/cgi-bin/message/mass/delete')
    if action=='broadcast_speed':
        value=_value(_post(client,'/cgi-bin/message/mass/speed/get',{}),client)
        return _observed(value,speed=value.get('speed'),realspeed=value.get('realspeed'))
    if action=='set_broadcast_speed':
        return _record(db,client,args,action,{'speed':args['speed']},'/cgi-bin/message/mass/speed/set')
    fail('INVALID_TOOL_ARGUMENTS')
