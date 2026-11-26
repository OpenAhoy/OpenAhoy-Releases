"""Read-only drafts for the account reached through WeChat admin authorization."""
import json
import re
from urllib.error import HTTPError
from urllib.parse import urlencode
from urllib.request import Request, build_opener

from .contracts import WCEError
from .publication_contract import strict_json
from .tools import schema
from .wechat_component_binding import BASE, _NoRedirect, _cid

TOOL = 'own.wechat.authorized_drafts'
HOST = BASE.split('/jiusera/',1)[0]
MAX_BYTES = 4 * 1024 * 1024
REF = re.compile(r'[0-9a-f]{48}')
SHA = re.compile(r'[0-9a-f]{64}')
CONNECTION = {'type':'string','pattern':r'^[A-Za-z0-9_-]{1,128}$'}
PUBLISHED_ID = re.compile(r'[A-Za-z0-9_-]{1,256}')
SPEC={'oneOf':[
    schema({'action':{'type':'string','const':'list'},'connection_id':CONNECTION},
           {'offset':{'type':'integer','minimum':0,'maximum':999999999}}),
    schema({'action':{'type':'string','const':'read'},'connection_id':CONNECTION,
            'draft_ref':{'type':'string','pattern':'^[0-9a-f]{48}$'}}),
    schema({'action':{'type':'string','const':'list_published'},'connection_id':CONNECTION},
           {'offset':{'type':'integer','minimum':0,'maximum':999999999}}),
    schema({'action':{'type':'string','const':'read_published'},'connection_id':CONNECTION,
            'article_id':{'type':'string','pattern':'^[A-Za-z0-9_-]{1,256}$'}}),
]}
CODES={401:'WORKSPACE_AUTH_REQUIRED',403:'WORKSPACE_ACCESS_DENIED',
       404:'READ_UNAVAILABLE',409:'GRANT_CHANGED',429:'RATE_LIMITED',503:'WECHAT_READ_UNAVAILABLE'}


def descriptor():
    return {'name':TOOL,'inputSchema':SPEC,'title':'读取管理员扫码授权的公众号草稿',
        'description':'Read the selected workspace account’s drafts or published articles by the original same-account reference.',
        'annotations':{'readOnlyHint':True,'openWorldHint':True},'_meta':{'ui':{'visibility':['app','model']}}}


def account(binding, inner, cid, permissions=frozenset((11,100))):
    cached=binding._cache()
    if not cached:
        raise WCEError('WECHAT_AUTHORIZED_DRAFTS_GRANT_UNAVAILABLE')
    linked=next((row for row in cached['rows'] if _cid(row['appid'])==cid),None)
    if linked is None:
        rows=inner.call('own.connections.list',{})['connections']
        owned=next((row for row in rows if row.get('connection_id')==cid and
                    row.get('state')!='DISCONNECTED'),None)
        if owned:
            appid=owned.get('account_id') or owned.get('appid') or owned.get('resource_id')
            linked=next((row for row in cached['rows'] if row['appid']==appid),None)
    if not linked or linked['state']!='ACTIVE' or not permissions.intersection(linked['funcInfo']):
        raise WCEError('WECHAT_AUTHORIZED_DRAFTS_NOT_GRANTED')
    return linked


def _draft(value, titles):
    ref,sha,count=value.get('draft_ref'),value.get('expected_projection_sha256'),value.get('article_count')
    if (type(ref) is not str or not REF.fullmatch(ref) or type(sha) is not str or not SHA.fullmatch(sha)
            or type(count) is not int or not 1<=count<=8):
        raise WCEError('WECHAT_AUTHORIZED_DRAFTS_UNVERIFIED')
    key='titles' if titles else 'articles'
    rows=value.get(key)
    if type(rows) is not list or len(rows)!=count:
        raise WCEError('WECHAT_AUTHORIZED_DRAFTS_UNVERIFIED')
    if titles:
        if any(type(title) is not str or not 1<=len(title)<=512 for title in rows):
            raise WCEError('WECHAT_AUTHORIZED_DRAFTS_UNVERIFIED')
    else:
        if any(type(article) is not dict or type(article.get('title')) is not str for article in rows):
            raise WCEError('WECHAT_AUTHORIZED_DRAFTS_UNVERIFIED')
        rows=[{k:a[k] for k in ('title','author','digest','content','article_type')
               if type(a.get(k)) is str} for a in rows]
    from .wechat_article_safety import image_url
    extra={}
    if type(value.get('update_time')) is int and value['update_time']>0:
        extra['update_time']=value['update_time']
    if titles and type(value.get('covers')) is list and len(value['covers'])==count:
        extra['covers']=[image_url(item) for item in value['covers']]
    if not titles and type(value.get('document_version')) is str and SHA.fullmatch(value['document_version']):
        extra['document_version']=value['document_version']
    return {'draft_ref':ref,'expected_projection_sha256':sha,'article_count':count,key:rows,**extra}


def _published_articles(values, *, detail):
    from .wechat_article_safety import image_url
    if values is None and not detail:
        return None
    if type(values) is not list or not 1<=len(values)<=8:
        raise WCEError('WECHAT_AUTHORIZED_PUBLISHED_UNVERIFIED')
    result=[]
    for index,row in enumerate(values):
        if type(row) is not dict or (detail and (type(row.get('index')) is not int or row['index']!=index)):
            raise WCEError('WECHAT_AUTHORIZED_PUBLISHED_UNVERIFIED')
        deleted=row.get('deleted') is True
        fields=('title',) if deleted else ('title','author','digest','url','content_source_url','content') if detail else ('title','url')
        article={key:row[key] for key in fields if type(row.get(key)) is str}
        if detail and not deleted and 'content' not in article:
            raise WCEError('WECHAT_AUTHORIZED_PUBLISHED_UNVERIFIED')
        thumb=image_url(row.get('cover_url') or row.get('thumb_url'))
        if thumb and not deleted:article['cover_url']=thumb
        result.append({'index':index,'deleted':deleted,**article})
    return result


def read(binding, linked, args, opener=None):
    proof=binding.proof.read()
    if proof is None:
        return {'state':'WORKSPACE_AUTH_REQUIRED'}
    action=args['action']
    published=action.endswith('published')
    path=HOST+'/jiusera/api/wechat/accounts/'+linked['appid']+('/published' if published else '/drafts')
    cid=args['connection_id']
    offset=args.get('offset',0)
    if action in ('list','list_published'):
        path+='?'+urlencode({'offset':offset,'count':20})
    elif action=='read_published':
        path+='/detail?'+urlencode({'article_id':args['article_id']})
    else:
        path+='/'+args['draft_ref']
    bearer=proof.reveal_for_adapter()
    request=Request(path,headers={'Accept':'application/json','Authorization':'Bearer '+bearer,
        'X-Jiusera-Grant-Generation':str(linked['generation'])},method='GET')
    network=opener or build_opener(_NoRedirect()).open
    try:
        with network(request,timeout=10) as response:
            if response.geturl()!=path or response.status!=200:
                return {'state':'WECHAT_READ_UNAVAILABLE'}
            raw=response.read(MAX_BYTES+1)
    except HTTPError as error:
        error.close()
        return {'state':CODES.get(error.code,'WECHAT_READ_UNAVAILABLE'),'http_status':error.code}
    except OSError:
        return {'state':'WECHAT_READ_UNAVAILABLE'}
    if bearer.encode() in raw:
        raise WCEError('WECHAT_AUTHORIZED_DRAFTS_UNVERIFIED')
    value=strict_json(raw,MAX_BYTES)
    if type(value) is not dict:
        raise WCEError('WECHAT_AUTHORIZED_DRAFTS_UNVERIFIED')
    base={'state':'OBSERVED','connection_id':cid,'grant_generation':linked['generation']}
    if action=='read_published':
        if value.get('article_id')!=args['article_id']:
            raise WCEError('WECHAT_AUTHORIZED_PUBLISHED_UNVERIFIED')
        return base|{'article_id':args['article_id'],'articles':_published_articles(value.get('articles'),detail=True)}
    if action=='read':
        result=_draft(value,False)
        if result['draft_ref']!=args['draft_ref']:
            raise WCEError('WECHAT_AUTHORIZED_DRAFTS_UNVERIFIED')
        return base|result
    size,total,items=value.get('item_count'),value.get('total_count'),value.get('items')
    if (type(total) is not int or type(size) is not int or not 0<=size<=min(20,total)
            or type(items) is not list or len(items)!=size or any(type(row) is not dict for row in items)):
        raise WCEError('WECHAT_AUTHORIZED_DRAFTS_UNVERIFIED')
    if published:
        projected=[]
        for row in items:
            article_id=row.get('article_id')
            if type(article_id) is not str or not PUBLISHED_ID.fullmatch(article_id):
                raise WCEError('WECHAT_AUTHORIZED_PUBLISHED_UNVERIFIED')
            stamp=row.get('update_time')
            projected.append({'article_id':article_id,'update_time':stamp if type(stamp) is int and stamp>0 else None,
                              'articles':_published_articles(row.get('articles'),detail=False)})
    else:
        projected=[_draft(row,True) for row in items]
    return base|{'total_count':total,'items':projected,
                 'next_offset':offset+size if size and offset+size<total else None}
