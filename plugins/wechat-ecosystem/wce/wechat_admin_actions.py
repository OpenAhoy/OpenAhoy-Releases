"""Explicit account administration. All upstream actions have fixed routes."""
from .contracts import WCEError
from .draft_group_wire import digest
from .tools import schema

LABEL = {'type':'string','minLength':1,'maxLength':30}
CLICK = {'type':'string','pattern':r'^[A-Za-z0-9_.:-]{1,128}$'}
BUTTON = {'oneOf':[
    schema({'name':LABEL,'type':{'type':'string','const':'view'},'url':{'type':'string','maxLength':1024}}),
    schema({'name':LABEL,'type':{'type':'string','const':'click'},'key':CLICK}),
]}
MENU = {'type':'array','minItems':1,'maxItems':3,'items':{'oneOf':[*BUTTON['oneOf'],
    schema({'name':LABEL,'sub_button':{'type':'array','minItems':1,'maxItems':5,'items':BUTTON}})]}}
READS = {'list_tags','plan_menu'}
WRITES = {'create_tag','update_menu','create_channel_qr'}


def actions(action,key,confirm):
    write = {'request_key':key,'confirm':confirm}
    return {
        'list_tags':action('list_tags',{}),
        'create_tag':action('create_tag',{**write,'name':LABEL}),
        'plan_menu':action('plan_menu',{'buttons':MENU}),
        'update_menu':action('update_menu',{**write,'buttons':MENU,
            'expected_menu_sha256':{'type':'string','pattern':'^[a-f0-9]{64}$'}}),
        'create_channel_qr':action('create_channel_qr',{**write,'scene':CLICK,
            'expires_in':{'type':'integer','minimum':60,'maximum':2592000}}),
    }


def clean_menu(rows, *, child=False):
    from urllib.parse import urlsplit
    cleaned=[]
    for row in rows:
        name=row['name'].strip()
        if not name or len(name.encode())>(60 if child else 16):
            raise WCEError('WECHAT_MENU_NAME_INVALID')
        if 'sub_button' in row:
            cleaned.append({'name':name,'sub_button':clean_menu(row['sub_button'],child=True)})
        else:
            if row['type']=='view':
                url=urlsplit(row['url'])
                if (url.scheme!='https' or not url.hostname or url.username or url.password
                        or len(row['url'].encode())>1024):
                    raise WCEError('WECHAT_MENU_URL_INVALID')
            cleaned.append({**row,'name':name})
    return cleaned


def current(client):
    from .wechat_content_ops import _get,_value
    from .upload_wire import contains_secret
    raw=_value(_get(client,'/cgi-bin/menu/get'),client)
    code=raw.get('errcode',0)
    if code==46003:
        return {'button':[]}
    if code:
        return raw
    menu=raw.get('menu')
    if type(menu) is not dict or type(menu.get('button')) is not list:
        raise WCEError('WECHAT_MENU_UNVERIFIED')
    if contains_secret(menu,client.secret,max_nodes=16384):
        raise WCEError('WECHAT_MENU_UNVERIFIED')
    return menu


def execute(db,client,args,action):
    from urllib.parse import quote
    from .http_transport import TransportFailure
    from .wechat_content import _at_send,_finish,_request,_reserve,public
    from .wechat_content_ops import _delivery_value,_get,_observed,_value

    if action=='list_tags':
        raw=_value(_get(client,'/cgi-bin/tags/get'),client)
        if raw.get('errcode',0):
            return _observed(raw)
        tags=raw.get('tags')
        if type(tags) is not list or any(type(r) is not dict or type(r.get('id')) is not int
                or type(r.get('name')) is not str for r in tags):
            raise WCEError('WECHAT_TAGS_UNVERIFIED')
        return _observed(raw,items=[{k:r[k] for k in ('id','name','count') if k in r} for r in tags])
    if action in {'plan_menu','update_menu'}:
        payload={'button':clean_menu(args['buttons'])}
        if action=='plan_menu':
            old=current(client)
            return _observed(old,current=old['button'],proposed=payload['button'],expected_menu_sha256=digest(old)) if not old.get('errcode') else _observed(old)
        route='/cgi-bin/menu/create'
    elif action=='create_tag':
        name=args['name'].strip()
        if not name or len(name)>30:
            raise WCEError('WECHAT_TAG_NAME_INVALID')
        payload={'tag':{'name':name}}
        route='/cgi-bin/tags/create'
    else:
        if len(args['scene'])>64:
            raise WCEError('WECHAT_QR_SCENE_INVALID')
        payload={'expire_seconds':args['expires_in'],'action_name':'QR_STR_SCENE',
                 'action_info':{'scene':{'scene_str':args['scene']}}}
        route='/cgi-bin/qrcode/create'
    saved=_reserve(db,client.policy,args['request_key'],action,
        {'payload':payload,'expected_menu_sha256':args.get('expected_menu_sha256')})
    if saved['state']!='PREPARED':
        return public(saved)
    if action=='update_menu':
        old=current(client)
        if old.get('errcode'):
            return _finish(db,client,saved,'REJECTED',error_code=old['errcode'])
        if digest(old)!=args['expected_menu_sha256']:
            return _finish(db,client,saved,'SOURCE_CHANGED')
    raw=client.send(_request(route,payload,client.secret),before_http=lambda:_at_send(db,saved),capability='draft_save')
    if isinstance(raw,TransportFailure):
        return public(saved)
    try:
        value=_delivery_value(raw,client)
    except WCEError:
        return public(saved)
    if value.get('errcode',0):
        return _finish(db,client,saved,'REJECTED',error_code=value['errcode'])
    if action=='create_tag':
        tag=value.get('tag')
        if not isinstance(tag,dict) or type(tag.get('id')) is not int or tag.get('name')!=name:
            return public(saved)
        return _finish(db,client,saved,'COMPLETED',result={'id':tag['id'],'name':name})
    if action=='create_channel_qr':
        ticket=value.get('ticket')
        expires=value.get('expire_seconds')
        if type(ticket) is not str or not 0<len(ticket)<=512 or type(expires) is not int or not 0<expires<=2592000:
            return public(saved)
        return _finish(db,client,saved,'COMPLETED',result={'expires_in':expires,'scene':args['scene'],
            'url':'https://mp.weixin.qq.com/cgi-bin/showqrcode?ticket='+quote(ticket,safe='')})
    return _finish(db,client,saved,'COMPLETED')
