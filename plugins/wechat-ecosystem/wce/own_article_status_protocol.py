"""App-only local article facts; no Tencent or account authority extension."""
from copy import deepcopy
from .tools import schema
from .own_article_status import validate,read

READ='wce.settings.articles.read'
CID={'type':'string','minLength':1,'maxLength':128,'pattern':'^[A-Za-z0-9_-]+$'}
SPECS={READ:{'oneOf':[schema({'connection_id':CID,'view':{'type':'string','const':'summary'}}),
    schema({'connection_id':CID,'view':{'type':'string','enum':['drafts','publications']}},
        {'before':{'type':'string','pattern':'^article-page-[a-f0-9]{64}-[0-9]+$'}})]}}


def descriptors():
    return [{'name':READ,'title':'读取本机文章状态',
        'description':'Read existing, validated local draft-save and publication journals only. Never queries WeChat, starts a broker, initializes storage or changes an article. Not current online inventory. Missing statistics are null, never fabricated zero. Continue next_before pages; a page is not a total article allowance.',
        'inputSchema':deepcopy(SPECS[READ]),'outputSchema':{'type':'object'},
        'annotations':{'readOnlyHint':True,'destructiveHint':False,'openWorldHint':False,'idempotentHint':True},
        '_meta':{'ui':{'visibility':['app']}}}]


def call(name,value,registry=None):
    if name!=READ:
        from .contracts import WCEError
        raise WCEError('ARTICLE_STATUS_INVALID_REQUEST')
    validate(value)
    return read(value,registry)
