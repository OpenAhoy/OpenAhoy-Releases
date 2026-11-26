"""Account-bound article metrics and moderation through the original WeChat broker."""
from datetime import date, datetime, timedelta, timezone
import math
import re

from .contracts import WCEError

CST = timezone(timedelta(hours=8))
DATA_ID = re.compile(r'[1-9][0-9]{0,18}')
COMMENT_ID = re.compile(r'(?:0|[1-9][0-9]{0,18})')
STATS_METRICS = ('read_user','share_user','zaikan_user','like_user','comment_count',
                 'collection_user','praise_money','read_subscribe_user','read_delivery_rate',
                 'read_finish_rate','read_avg_activetime')
MUTATIONS = {'reply_comment', 'feature_comment', 'unfeature_comment'}


def fail(code):
    raise WCEError(code)


def _number(text, pattern):
    if type(text) is not str or not pattern.fullmatch(text) or int(text) >= 2**63:
        fail('WECHAT_COMMENT_ID_INVALID')
    return int(text)


def _date(text):
    try:
        value = date.fromisoformat(text)
    except (TypeError, ValueError):
        fail('WECHAT_REPORT_DATE_INVALID')
    if value.isoformat() != text:
        fail('WECHAT_REPORT_DATE_INVALID')
    return value


def _metrics(value):
    output = {}
    for name in STATS_METRICS:
        point = value.get(name)
        if type(point) is int and point >= 0 or type(point) is float and math.isfinite(point) and point >= 0:
            output[name] = point
    return output


def _sources(values):
    if type(values) is not list:
        return []
    return [{'scene':value['scene_desc'][:80],'read_user':value['user_count']}
            for value in values[:64] if type(value) is dict and type(value.get('scene_desc')) is str
            and type(value.get('user_count')) is int and value['user_count']>=0]


def _article(item, start, end):
    from .publication_wire import article_url_supported

    if type(item) is not dict:
        fail('WECHAT_ARTICLE_STATS_UNVERIFIED')
    msgid = item.get('msgid')
    if type(msgid) is not str:
        fail('WECHAT_ARTICLE_STATS_UNVERIFIED')
    key = re.fullmatch(r'([1-9][0-9]{0,18})_([1-8])',msgid)
    if not key:
        fail('WECHAT_ARTICLE_STATS_UNVERIFIED')
    media = key[1]
    _number(media, DATA_ID)
    published = _date(item.get('ref_date'))
    if not start <= published <= end:
        fail('WECHAT_ARTICLE_STATS_SCOPE_CHANGED')
    details = item.get('detail_list')
    if type(details) is not list or len(details)>45 or any(type(d) is not dict for d in details):
        fail('WECHAT_ARTICLE_STATS_UNVERIFIED')
    snapshots = []
    visited = set()
    for entry in details:
        day = _date(entry.get('stat_date'))
        if not published<=day<published+timedelta(days=30) or day in visited:
            fail('WECHAT_ARTICLE_STATS_UNVERIFIED')
        visited.add(day)
        snapshots.append({'stat_date':day.isoformat(),'metrics':_metrics(entry),
                          'read_sources':_sources(entry.get('read_user_source'))})
    latest = max(snapshots,key=lambda d:d['stat_date']) if snapshots else None
    title = item.get('title')
    url = item.get('content_url')
    publish_type = item.get('publish_type')
    return {'msg_data_id':media,'index':int(key[2])-1,'published_at':published.isoformat(),
            'title':title[:128] if type(title) is str else None,
            'url':url if type(url) is str and article_url_supported(url) else None,
            'publish_type':publish_type if type(publish_type) is int and publish_type in (0,1) else None,
            'latest':latest}


def article_stats(client,args):
    from .http_transport import MAX_BODY
    from .wechat_content_ops import _delivery_value, _observed, _post
    start,end = _date(args['begin_date']),_date(args['end_date'])
    today = datetime.now(CST).date()
    if not date(2025,11,1)<=start==end<today:
        fail('WECHAT_REPORT_WINDOW_INVALID')
    result = _delivery_value(_post(client,'/datacube/getarticletotaldetail',
                                   {'begin_date':start.isoformat(),'end_date':end.isoformat()}),client,MAX_BODY)
    if result.get('errcode',0):
        return _observed(result)
    rows = result.get('list')
    if type(rows) is not list or len(rows)>320:
        fail('WECHAT_ARTICLE_STATS_UNVERIFIED')
    projected = [_article(row,start,end) for row in rows]
    if len({(r['msg_data_id'],r['index']) for r in projected})!=len(projected):
        fail('WECHAT_ARTICLE_STATS_UNVERIFIED')
    projected.sort(key=lambda row:(row['published_at'],row['msg_data_id'],row['index']), reverse=True)
    return _observed(result,items=projected,
        snapshot_semantics='LATEST_CUMULATIVE_PER_ARTICLE', delayed=result.get('is_delay') if type(result.get('is_delay')) is bool else None)


def target_of(args):
    return {'msg_data_id':_number(args['msg_data_id'], DATA_ID), 'index':args.get('index', 0),
            'user_comment_id':_number(args['comment_id'], COMMENT_ID)}


def find_comment(client,args):
    from .wechat_content_ops import _comment_page
    # This offset is a hint from the rendered page, never the comment identity.
    start = args.get('observed_offset',0)
    offsets = [start] + ([0] if start else [])
    visited = set()
    while offsets and len(visited) < 5:
        item = offsets.pop(0)
        if item in visited:
            continue
        visited.add(item)
        result = _comment_page(client,{**args,'offset':item,'count':20,'selection':0})
        if result['state'] != 'OBSERVED':
            return None,result['error_code']
        for row in result['items']:
            if row['id'] == args['comment_id']:
                return row,None
        if result['next_offset'] is not None and result['next_offset'] not in visited:
            offsets.append(result['next_offset'])
    return None,88008


def _prior_reply(db,client,identity):
    from .wechat_content import _operation
    from .publication_contract import stable_account
    result = db.execute(
        """SELECT handle FROM operations
           WHERE json_extract(row_json,'$.kind')='reply_comment'
             AND json_extract(row_json,'$.account_key')=?
             AND json_extract(row_json,'$.intent.subject')=?
             AND json_extract(row_json,'$.state') IN ('UNKNOWN','COMPLETED','ALREADY_REPLIED','OBSERVED_REPLY')
           LIMIT 1""",
        (stable_account(client.policy.data),identity)).fetchone()
    return _operation(db,client.policy,handle=result[0]) if result else None


def mutate(db,client,args,action, *, automatic=False):
    from .wechat_content import _at_send, _finish, _request, _reserve, public
    from .wechat_content_ops import _delivery_value
    from .draft_group_wire import digest
    from .http_transport import TransportFailure
    target = target_of(args)
    subject = digest(target)
    payload = {**target}
    if action == 'reply_comment':
        text = args['content'].strip()
        if not text or len(text.encode())>600:
            fail('WECHAT_COMMENT_REPLY_TEXT_INVALID')
        payload['content'] = text
        prior = _prior_reply(db,client,subject)
        if prior:
            row, _ = find_comment(client,args) if prior['state']=='UNKNOWN' else (None,None)
            if row and row.get('reply'):
                return _finish(db,client,prior,'OBSERVED_REPLY',result={'reply':row['reply']})
            return public(prior)
    operation = _reserve(db,client.policy,args['request_key'],action,
                         {'subject':subject,'target':target,'content':payload.get('content'),
                          'automatic':automatic,'key':args['request_key']})
    if operation['state']!='PREPARED':
        return public(operation)
    visible,error = find_comment(client,args)
    if error is not None:
        return _finish(db,client,operation,'REJECTED',error_code=error)
    if action=='reply_comment' and visible.get('reply'):
        return _finish(db,client,operation,'ALREADY_REPLIED',result={'reply':visible['reply']})
    if action!='reply_comment' and visible.get('comment_type')==int(action=='feature_comment'):
        return _finish(db,client,operation,'COMPLETED')
    route = '/cgi-bin/comment/'+{'reply_comment':'reply/add','feature_comment':'markelect','unfeature_comment':'unmarkelect'}[action]
    raw = client.send(_request(route,payload,client.secret),capability='draft_save',
                      before_http=lambda:_at_send(db,operation))
    if isinstance(raw,TransportFailure):
        return public(operation)
    try:
        result = _delivery_value(raw,client)
    except WCEError:
        return public(operation)
    code=result.get('errcode')
    if code==88005 and action=='reply_comment':
        return _finish(db,client,operation,'ALREADY_REPLIED',error_code=code)
    if code==0:
        return _finish(db,client,operation,'COMPLETED')
    if code in {40001,40014,42001,45009,48001,61007,88000,88001,88007,88008}:
        return _finish(db,client,operation,'REJECTED',error_code=code)
    return public(operation)
