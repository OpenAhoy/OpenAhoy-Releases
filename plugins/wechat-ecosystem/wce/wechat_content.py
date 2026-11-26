"""Account-bound WeChat content operations through the existing direct broker."""
import base64
import binascii
from contextlib import nullcontext
import time
from copy import deepcopy
from urllib.parse import urlencode

from .contracts import WCEError
from .editor_contracts import COORDINATE
from .http_transport import HTTPRequest, HTTPSender, MAX_BODY
from .own_draft_wire import reference_valid, response_value
from .prepared_contracts import ID, strict_validate
from .publication_contract import binding, stable_account
from .tools import schema
from .wechat_picture_fields import image_ids, picture_fields
from . import current_draft_management as managed
from . import draft_group_wire as wire
from . import upload_wire

TOOL = 'own.wechat.content'
HANDLE = {'type': 'string', 'pattern': '^managed-draft-[a-f0-9]{48}$'}
ASSET = {'type': 'string', 'pattern': '^own-asset-[a-f0-9]{32}$'}
INLINE_IMAGE_MAX = 700 * 1024
PAGE = {'offset': {'type': 'integer', 'minimum': 0, 'maximum': 100000},
        'count': {'type': 'integer', 'minimum': 1, 'maximum': 20}}
CROP = schema({'ratio': {'type': 'string', 'enum': ['1_1', '16_9', '2.35_1']},
               **{name: COORDINATE for name in ('x1', 'y1', 'x2', 'y2')}})
PICTURE = schema({
    'title': {'type': 'string', 'minLength': 1, 'maxLength': 32},
    'content': {'type': 'string', 'maxLength': 19999},
}, {
    'image_handles': {'type': 'array', 'minItems': 1, 'maxItems': 20, 'items': HANDLE},
    'author': {'type': 'string', 'maxLength': 16},
    'need_open_comment': {'type': 'integer', 'enum': [0, 1]},
    'only_fans_can_comment': {'type': 'integer', 'enum': [0, 1]},
    'cover_info': schema({'crop_percent_list': {'type': 'array', 'minItems': 1, 'maxItems': 3, 'items': CROP}}),
    'product_key': {'type': 'string', 'minLength': 1, 'maxLength': 1024},
})
NEWS_CHANGES = schema({}, {
    'title': {'type': 'string', 'minLength': 1, 'maxLength': 64},
    'author': {'type': 'string', 'maxLength': 16},
    'digest': {'type': 'string', 'maxLength': 120},
    'content': {'type': 'string', 'minLength': 1, 'maxLength': 19999},
    'cover_handle': HANDLE,
})
NEWS_CREATE = schema({key:NEWS_CHANGES['properties'][key] for key in ('title','content','cover_handle')},
    {key:NEWS_CHANGES['properties'][key] for key in ('author','digest')})


def action_schema(action, required, optional=None):
    return schema({'action': {'type': 'string', 'const': action}, 'connection_id': ID,
                   **required}, optional or {})


def specs():
    from .current_draft_management_protocol import SELECTION
    from .wechat_content_ops import specs as additional
    image_data = schema({'mime_type': {'type': 'string', 'enum': ['image/jpeg', 'image/png']},
                         'base64': {'type': 'string', 'minLength': 4,
                                    'maxLength': 4 * ((INLINE_IMAGE_MAX + 2) // 3)}})
    return {
        'upload_image': action_schema('upload_image', {'request_key': ID, 'source': {'oneOf': [
            schema({'asset_ref': ASSET}), image_data]}},
            {'purpose': {'type': 'string', 'enum': ['permanent_image', 'body_image']}}),
        'create_picture': action_schema('create_picture', {'request_key': ID, 'article': PICTURE}),
        'update_picture': action_schema('update_picture', {'request_key': ID, 'selection': SELECTION,
            'index': {'type': 'integer', 'minimum': 0, 'maximum': 7}, 'article': PICTURE}),
        'update_news': action_schema('update_news', {'request_key': ID, 'selection': SELECTION,
            'index': {'type': 'integer', 'minimum': 0, 'maximum': 7}, 'changes': NEWS_CHANGES}),
        'create_news': action_schema('create_news', {'request_key': ID, 'article': NEWS_CREATE}),
        'status': action_schema('status', {'operation_handle': HANDLE}),
        'status_by_key': action_schema('status_by_key', {'request_key': ID}),
        'readback': action_schema('readback', {'operation_handle': HANDLE}),
    } | additional(action_schema, ID, HANDLE, PAGE, INLINE_IMAGE_MAX)


def descriptor():
    return {'name': TOOL, 'inputSchema': {'type': 'object', 'oneOf': list(specs().values())},
            'description': 'Official WeChat content: pictures, materials, published works, preview and separately authorized broadcasts. '
            'Picture drafts use 1–20 ordered same-account permanent upload handles; first is cover. UNKNOWN writes are recovered '
            'by original key/handle and never replayed. Ordinary publication uses the saved intent_handle. Existing HTML entry: '
            'own.documents.prepare. Delivery tool calls require the intended audience and explicit user authorization.',
            '_meta': {'ui': {'visibility': ['model', 'app']}},
            'annotations': {'idempotentHint': True, 'readOnlyHint': False,
                            'destructiveHint': True, 'openWorldHint': True}}


def validate(args, *, broker=False):
    action = args.get('action') if type(args) is dict else None
    catalog = specs()
    if type(action) is not str or action not in catalog:
        raise WCEError('INVALID_TOOL_ARGUMENTS')
    contract=catalog[action]
    if action=='upload_media_file' and broker:
        required=set(contract['required'])
        contract=schema({name:value for name,value in contract['properties'].items()
                         if name in required and name!='absolute_path'} |
                        {'staged_media':{'type':'string','pattern':r'^wxmedia-[0-9a-f]{64}\.(jpg|png|gif|amr|mp3|mp4)$'}},
                        {name:value for name,value in contract['properties'].items() if name not in required})
    strict_validate(args, contract)
    return action


class ContentRouter:
    def __init__(self, inner):
        self.inner = inner

    def __getattr__(self, name):
        return getattr(self.inner, name)

    @property
    def _inline_probe_meta(self):
        return self.inner._inline_probe_meta

    @_inline_probe_meta.setter
    def _inline_probe_meta(self, value):
        self.inner._inline_probe_meta = value

    def list_tools(self):
        return self.inner.list_tools() + [descriptor()]

    def call(self, name, args):
        if name != TOOL:
            return self.inner.call(name, args)
        action = validate(args)
        from .own_connection_policy import resolve
        local = action in {'status','status_by_key'}
        policy = resolve(args['connection_id'], self.inner.registry, active=not local)
        if local:
            return local_status(policy, args)
        if action == 'upload_media_file':
            from .own_connection_input import stage_content_media
            from .wechat_content_ops import MIME_EXT
            args = {key:value for key,value in args.items() if key!='absolute_path'} | {
                'staged_media':stage_content_media(policy,args['absolute_path'],MIME_EXT[args['mime_type']])}
        from .own_connection_broker import call, ensure_started
        ensure_started(policy, self.inner.launcher)
        try:
            return call(policy, name, args)
        except (OSError, EOFError):
            fail('CONNECTION_RESULT_UNDETERMINED_QUERY_ORIGINAL_KEY')


def fail(code):
    raise WCEError(code)


def public(row):
    result = {name: deepcopy(row[name]) for name in (
        'operation_handle', 'kind', 'state', 'request_count', 'error_code', 'result',
        'readback', 'article_count', 'titles') if name in row}
    result['connection_id'] = row['connection_id']
    if row['kind'] in {'create_picture', 'update_picture'} and row['state'] in {'SAVED', 'VERIFIED', 'UNCHANGED'}:
        result['intent_handle'] = row['operation_handle']
    return result


def _operation(db, policy, *, handle=None, request_key=None):
    row = managed._load(db, policy, handle=handle, request_key=request_key)
    if row.get('content_version') != 1:
        fail('WECHAT_CONTENT_OPERATION_NOT_FOUND')
    return row


def local_status(policy, args):
    policy.check(readonly=True, allow_disconnected=True)
    with managed.journal(policy) as db:
        row = _operation(db, policy, handle=args.get('operation_handle'), request_key=args.get('request_key'))
    policy.check(readonly=True, allow_disconnected=True)
    return public(row)


def _reserve(db, policy, request_key, kind, intent):
    account_key = stable_account(policy.data)
    binding_sha = binding(policy.data)
    identity = wire.digest([kind, account_key, binding_sha, intent])
    handle = 'managed-draft-' + wire.digest([account_key, 'wechat-content', request_key])[:48]
    db.execute('BEGIN IMMEDIATE')
    prior = db.execute('SELECT handle FROM request_keys WHERE key=?', (request_key,)).fetchone()
    if prior is not None:
        row = _operation(db, policy, handle=prior[0])
        if row['intent_sha256'] != identity:
            fail('WECHAT_CONTENT_REQUEST_KEY_CONFLICT')
    else:
        original = db.execute("SELECT handle FROM operations WHERE json_extract(row_json,'$.intent_sha256')=? "
                              "AND json_extract(row_json,'$.content_version')=1", (identity,)).fetchone()
        if original is None:
            row = {'profile': managed.PROFILE, 'content_version': 1, 'operation_handle': handle,
                   'kind': kind, 'intent_sha256': identity, 'connection_id': policy.data['connection_id'],
                   'account_key': account_key, 'binding_sha256': binding_sha, 'state': 'PREPARED',
                   'request_count': 0, 'intent': intent}
            db.execute('INSERT INTO operations VALUES(?,?)', (handle, wire.canonical(row)))
        else:
            row = _operation(db, policy, handle=original[0])
        db.execute('INSERT INTO request_keys VALUES(?,?)', (request_key, row['operation_handle']))
    db.commit()
    return row


def _asset(service, source):
    if 'asset_ref' in source:
        with service.workflow.db.transaction() as db:
            metadata, data = service.workflow._asset(db, service.profile().binding(), source['asset_ref'])
        return metadata['declared_type'], data
    try:
        data = base64.b64decode(source['base64'], validate=True)
    except (binascii.Error, ValueError):
        fail('INVALID_LOCAL_IMAGE')
    if not 0 < len(data) <= MAX_BODY:
        fail('UPLOAD_TRANSPORT_LIMIT')
    return source['mime_type'], data


def _picture(db, policy, article, previous=None):
    data = {name: deepcopy(value) for name, value in article.items()
            if name not in {'image_handles', 'product_key'}}
    images = []
    for handle in article.get('image_handles', ()):
        row = _operation(db, policy, handle=handle)
        direct = row['kind'] == 'upload_image' and row['intent']['purpose'] == 'permanent_image'
        imported = row['kind'] == 'upload_media' and row.get('result', {}).get('media_type') == 'image' and row.get('result', {}).get('lifetime') == 'permanent'
        if row['state'] != 'MEDIA_READY' or not (direct or imported):
            fail('WECHAT_PERMANENT_IMAGE_REQUIRED')
        images.append({'image_media_id': row['result']['media_id']})
    if not images and previous is None:
        fail('WECHAT_PERMANENT_IMAGE_REQUIRED')
    data['image_info'] = {'image_list': images} if images else previous['image_info']
    if previous is not None:
        observed = picture_fields(previous)
        for name in ('author', 'cover_info', 'product_info', 'need_open_comment', 'only_fans_can_comment'):
            if name in observed:
                data.setdefault(name, observed[name])
    if 'product_key' in article:
        data['product_info'] = {'footer_product_info': {'product_key': article['product_key']}}
    return picture_fields(data, writing=True)


def _request(path, data, secret, *, method='POST'):
    if upload_wire.contains_secret(data, secret, max_nodes=16384):
        fail('REQUEST_SECRET_REFLECTION')
    token_query = '?' + urlencode({'access_token': upload_wire.secret_value(secret)})
    body = wire.canonical(data).encode() if method == 'POST' else b''
    if len(body) > MAX_BODY:
        fail('WECHAT_CONTENT_TRANSPORT_LIMIT')
    return HTTPRequest(method, path + token_query, {'Content-Type': 'application/json; charset=utf-8'}, body)


class Session:
    def __init__(self, service, args, deadline, cancel_guard):
        self.service, self.args, self.deadline = service, args, deadline
        self.cancel_guard = cancel_guard
        self.policy = service.policy
        self.binding_sha = binding(self.policy.data)
        self.lease = None

    def guard(self, capability='draft_read'):
        self.service.guard(self.deadline)
        if self.cancel_guard is not None:
            self.cancel_guard()
        if (self.args['connection_id'] != self.policy.data['connection_id']
                or self.binding_sha != binding(self.policy.data)
                or capability not in self.policy.value['capabilities']):
            fail('WECHAT_CONTENT_SCOPE_CHANGED')

    @property
    def secret(self):
        if self.lease is None:
            self.lease = self.service.tokens.get(self.guard)
        return self.lease.token

    def send(self, request, *, before_http=None, capability='draft_read'):
        self.guard(capability)
        sender = self.service.workflow.sender
        if type(sender) is not HTTPSender or not sender.enabled:
            fail('OWN_HTTP_DISABLED')
        if self.lease is None or not self.service.tokens.valid(self.lease):
            fail('OWN_TOKEN_UNAVAILABLE')
        timeout = min(30, self.deadline-time.monotonic(), self.lease.wall_deadline-time.time())
        if timeout <= 0:
            fail('CONNECTION_QUEUE_EXPIRED')
        if before_http is not None:
            before_http()
        return sender.send(request, timeout)

    def snapshot(self, reference):
        raw = self.send(wire.encode_get(reference, self.secret))
        snapshot = wire.parse_get(raw, self.secret, reference, allow_picture=True)
        self.guard()
        if type(snapshot) is not wire.GroupSnapshot:
            fail('WECHAT_DRAFT_UNAVAILABLE')
        return snapshot


def _at_send(db, row):
    row.update(state='UNKNOWN', request_count=1)
    managed._save(db, row)


def _finish(db, client, row, state, **fields):
    row.update(state=state, **fields)
    managed._save(db, row)
    client.guard()
    return public(row)


def _upload(db, client, args):
    mime, data = _asset(client.service, args['source'])
    from hashlib import sha256
    purpose = args.get('purpose', 'permanent_image')
    kind = 'permanent_cover' if purpose == 'permanent_image' else 'article_body'
    row = _reserve(db, client.policy, args['request_key'], 'upload_image',
                   {'purpose': purpose, 'mime_type': mime, 'sha256': sha256(data).hexdigest()})
    if row['state'] != 'PREPARED':
        return public(row)
    from .own_wire import encode_upload
    request = encode_upload(kind, mime, data, client.secret)
    raw = client.send(request, before_http=lambda: _at_send(db, row), capability='draft_images')
    parse_policy = (upload_wire.COVER_RESPONSE_POLICY if purpose == 'permanent_image'
                    else upload_wire.BODY_API_REFERENCE_POLICY)
    reply = upload_wire.inspect_response(kind, raw, client.secret, production=True, policy=parse_policy).reply
    if reply.error_code is not None:
        return _finish(db, client, row, 'REJECTED', error_code=reply.error_code)
    if reply.url is None or purpose == 'permanent_image' and reply.media_id is None:
        return public(row)
    result = {'url': reply.url}
    if reply.media_id is not None:
        result['media_id'] = reply.media_id
    return _finish(db, client, row, 'MEDIA_READY', result=result)


def _draft(db, client, action, args):
    target = managed.selected(client.policy, args['selection'], client.guard) if action == 'update_picture' else None
    index = args.get('index', 0)
    if target:
        rows = target['projection']['response']['news_item']
        if index >= len(rows) or rows[index].get('article_type') != 'newspic':
            fail('WECHAT_PICTURE_DRAFT_REQUIRED')
        article = _picture(db, client.policy, args['article'], rows[index])
    else:
        article = _picture(db, client.policy, args['article'])
        rows = [article]
    row = _reserve(db, client.policy, args['request_key'], action, {'article': article, 'index': index,
        'reference': target['reference'] if target else None,
        'before': target['projection_sha256'] if target else None,
        'baseline': [{'title': item['title'], 'digest': _row_digest(item)} for item in rows]})
    if row['state'] != 'PREPARED':
        return public(row)
    intent = row['intent']
    reference = intent['reference']
    if reference:
        conflict = db.execute("SELECT handle FROM operations WHERE handle!=? "
                              "AND json_extract(row_json,'$.kind')='update_picture' "
                              "AND json_extract(row_json,'$.state')='UNKNOWN' "
                              "AND json_extract(row_json,'$.intent.reference')=?",
                              (row['operation_handle'], reference)).fetchone()
        if conflict is not None:
            fail('WECHAT_CONTENT_ORIGINAL_UPDATE_REQUIRED')
        current = client.snapshot(reference)
        if wire.digest(wire.baseline_projection(current)) != intent['before']:
            return _finish(db, client, row, 'SOURCE_CHANGED')
        if picture_fields(current.rows()[index]) == article:
            titles = [item['title'] for item in intent['baseline']]
            return _finish(db, client, row, 'UNCHANGED', article_count=len(titles), titles=titles,
                           new_reference=reference, result={'media_id': reference, 'index': index})
        path, payload = '/cgi-bin/draft/update', {'media_id': reference, 'index': index, 'articles': article}
    else:
        path, payload = '/cgi-bin/draft/add', {'articles': [article]}
    raw = client.send(_request(path, payload, client.secret),
                      before_http=lambda: _at_send(db, row), capability='draft_save')
    try:
        value = response_value(raw, client.secret)
    except WCEError:
        return public(row)
    if value.get('errcode', 0) != 0:
        return _finish(db, client, row, 'REJECTED', error_code=value['errcode'])
    if reference and value.get('errcode') != 0:
        return public(row)
    reference = reference or value.get('media_id')
    if not reference_valid(reference):
        return public(row)
    titles = [item['title'] for item in intent['baseline']]
    titles[index] = article['title']
    return _finish(db, client, row, 'SAVED', article_count=len(titles), titles=titles,
                   new_reference=reference, result={'media_id': reference, 'index': index})


def _update_news(db,client,args):
    from .documents import safe_url
    from .draft_revision_wire import WRITE_FIELDS, PRESERVATION_FIELDS
    target=managed.selected(client.policy,args['selection'],client.guard)
    index=args['index'];rows=target['projection']['response']['news_item']
    if index>=len(rows) or not args['changes']:
        fail('WECHAT_DRAFT_EDIT_INVALID')
    original=rows[index]
    if (original.get('article_type','news')!='news' or not PRESERVATION_FIELDS<=set(original)
            or set(original)-WRITE_FIELDS-{'url','thumb_url'}):
        fail('WECHAT_DRAFT_EDIT_OPEN_OFFICIAL')
    changes=deepcopy(args['changes'])
    cover=changes.pop('cover_handle',None)
    if cover:
        changes['thumb_media_id']=_news_cover(db,client,cover)
    article={key:deepcopy(value) for key,value in original.items() if key in WRITE_FIELDS}
    article.update(changes)
    if not reference_valid(article['thumb_media_id']):
        fail('WECHAT_DRAFT_COVER_NOT_AVAILABLE')
    if article['content_source_url']:
        safe_url(article['content_source_url'])
    if not isinstance(article['content'],str) or not article['content'] or len(article['content'].encode())>=1_000_000:
        fail('WECHAT_DRAFT_EDIT_INVALID')
    if 'content' in changes:
        from .wechat_article_safety import validate_manual_body
        validate_manual_body(original['content'],changes['content'])
    row=_reserve(db,client.policy,args['request_key'],'update_news',{
        'article':article,'index':index,'reference':target['reference'],'before':target['projection_sha256'],
        'baseline':[{'title':item['title'],'digest':_row_digest(item)} for item in rows]})
    if row['state']!='PREPARED':
        return public(row)
    reference=target['reference']
    previous=db.execute("SELECT handle FROM operations WHERE handle!=? AND "
        "json_extract(row_json,'$.kind') IN ('update_news','update_picture') AND "
        "json_extract(row_json,'$.state')='UNKNOWN' AND json_extract(row_json,'$.intent.reference')=?",
        (row['operation_handle'],reference)).fetchone()
    if previous is not None:
        fail('WECHAT_CONTENT_ORIGINAL_UPDATE_REQUIRED')
    before=client.snapshot(reference)
    if wire.digest(wire.baseline_projection(before))!=target['projection_sha256']:
        return _finish(db,client,row,'SOURCE_CHANGED')
    if all(original.get(key)==value for key,value in changes.items()):
        return _finish(db,client,row,'UNCHANGED',new_reference=reference)
    raw=client.send(_request('/cgi-bin/draft/update',{'media_id':reference,'index':index,'articles':article},client.secret),
                    before_http=lambda:_at_send(db,row),capability='draft_save')
    try:
        result=response_value(raw,client.secret)
    except WCEError:
        return public(row)
    if type(result.get('errcode')) is not int:
        return public(row)
    if result['errcode']!=0:
        return _finish(db,client,row,'REJECTED',error_code=result['errcode'])
    _finish(db,client,row,'SAVED',new_reference=reference,article_count=len(rows))
    return _readback(db,client,{'operation_handle':row['operation_handle']})


def _news_cover(db,client,handle):
    uploaded=_operation(db,client.policy,handle=handle)
    result=uploaded.get('result',{})
    if (uploaded['kind']!='upload_image' or uploaded['state'] not in {'MEDIA_READY','UPLOADED'}
            or uploaded.get('intent', {}).get('purpose')!='permanent_image'
            or not reference_valid(result.get('media_id'))):
        fail('WECHAT_DRAFT_COVER_NOT_AVAILABLE')
    return result['media_id']


def _create_news(db,client,args):
    from .wechat_article_safety import validate_manual_body
    article=deepcopy(args['article'])
    article.update(article_type='news',thumb_media_id=_news_cover(db,client,article.pop('cover_handle')),
                   content_source_url='',need_open_comment=0,only_fans_can_comment=0)
    article.setdefault('author','');article.setdefault('digest','')
    validate_manual_body('',article['content'])
    row=_reserve(db,client.policy,args['request_key'],'create_news',{
        'article':article,'index':0,'reference':None,'baseline':[{'title':article['title'],'digest':_row_digest(article)}]})
    if row['state']!='PREPARED':
        return public(row)
    raw=client.send(_request('/cgi-bin/draft/add',{'articles':[article]},client.secret),
                    before_http=lambda:_at_send(db,row),capability='draft_save')
    try:
        result=response_value(raw,client.secret)
    except WCEError:
        return public(row)
    if result.get('errcode',0):
        return _finish(db,client,row,'REJECTED',error_code=result['errcode'])
    reference=result.get('media_id')
    if not reference_valid(reference):
        return public(row)
    _finish(db,client,row,'SAVED',new_reference=reference,article_count=1)
    return _readback(db,client,{'operation_handle':row['operation_handle']})


def _readback(db, client, args):
    row = _operation(db, client.policy, handle=args['operation_handle'])
    if row.get('kind') not in {'create_picture', 'update_picture','update_news','create_news'} or row['state'] not in {
            'SAVED', 'VERIFIED', 'UNCHANGED', 'UNKNOWN', 'READBACK_MISMATCH'}:
        return public(row)
    intent = row['intent']
    reference = row.get('new_reference') or intent['reference']
    if not reference:
        return public(row)
    got = client.snapshot(reference).rows()
    index, article = intent['index'], intent['article']
    stable_neighbors = len(got) == len(intent['baseline']) and all(
        _row_digest(actual) == previous['digest']
        for i, (actual, previous) in enumerate(zip(got, intent['baseline'])) if i != index)
    match = False
    if stable_neighbors and row['kind'] in {'update_news','create_news'}:
        observed=got[index]
        match=all(article[key]==observed.get(key) for key in article)
        if match:return _finish(db,client,row,'VERIFIED',new_reference=reference,
            article_count=len(got),titles=[item['title'] for item in got],readback={'state':'MATCHED'})
    elif stable_neighbors and got[index].get('article_type') == 'newspic':
        observed = picture_fields(got[index])
        match = all(article[key] == observed.get(key) for key in article)
    if not match:
        if row['state'] == 'UNKNOWN':
            return public(row) | {'readback': {'state': 'NOT_MATCHED'}}
        return _finish(db, client, row, 'READBACK_MISMATCH', readback={'state': 'NOT_MATCHED'})
    return _finish(db, client, row, 'VERIFIED', new_reference=reference,
        article_count=len(got), titles=[item['title'] for item in got],
        result={'media_id': reference, 'index': index}, readback={
            'state': 'MATCHED', 'article': picture_fields(got[index]),
            'first_image_media_id': image_ids(got[index])[0]})


def _row_digest(article):
    return wire.digest({key: value for key, value in article.items() if key != 'url'})


def execute(service, args, deadline, cancel_guard=None):
    action = validate(args,broker=True)
    client = Session(service, args, deadline, cancel_guard)
    client.guard()
    if action.startswith('status'):
        return local_status(client.policy, args)
    from . import wechat_content_ops as extra
    if action not in extra.READS | {'readback','comment_auto_disable','comment_take_over'} and upload_wire.contains_secret(args, client.secret, max_nodes=16384):
        fail('REQUEST_SECRET_REFLECTION')
    if action in extra.READS:
        if action in {'temporary_details', 'high_quality_voice', 'broadcast_status'}:
            with managed.journal(client.policy) as db:
                return extra.execute(db, client, args, action)
        return extra.execute(None, client, args, action)
    from .publication_lock import draft_writer
    draft_message = action in {'preview_message','send_broadcast'} and 'draft_selection' in args['message'].get('media',{})
    writer = (draft_writer(client.policy.root, client.policy.data['appid'])
              if draft_message or action in {'create_picture', 'update_picture', 'create_news', 'update_news', 'readback'} else nullcontext())
    with writer, managed.journal(client.policy, create=action != 'readback', writable=True) as db:
        if action == 'upload_image':
            return _upload(db, client, args)
        if action == 'readback':
            return _readback(db, client, args)
        if action in {'create_picture','update_picture'}:
            return _draft(db, client, action, args)
        if action=='update_news':
            return _update_news(db,client,args)
        if action=='create_news':
            return _create_news(db,client,args)
        return extra.execute(db, client, args, action)
