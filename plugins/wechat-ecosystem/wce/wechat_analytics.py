"""Read-only WeChat Data Cube projections for a single bound account."""
from datetime import date, datetime, timedelta, timezone
import json
import time
from urllib.parse import urlencode, urlsplit

from .contracts import WCEError
from .http_transport import DATACUBE_PATHS, HTTPRequest, HTTPResponse, HTTPSender
from .publication_contract import strict_json
from .publication_wire import article_url_supported
from .upload_wire import contains_secret, secret_value

TOOL = 'wce.ui.wechat.analytics'
BEIJING = timezone(timedelta(hours=8))
DAY = timedelta(days=1)
CONTENT_START = date(2025, 11, 1)
STAT_KEYS = ('read_user', 'share_user', 'zaikan_user', 'like_user', 'comment_count',
             'collection_user', 'redirect_ori_page_user', 'send_page_count', 'read_subscribe_user')
PERMISSION_CODES = {48001, 48002, 48004, 50001}
FANS = 'getusersummary'
TOTAL = 'getusercumulate'
CONTENT = 'getbizsummary'
ARTICLE = 'getarticletotaldetail'
WINDOWS = {FANS: 7, TOTAL: 7, CONTENT: 30, ARTICLE: 1}


def count(value):
    return value if type(value) is int and 0 <= value < 2**53 else None


def readable_link(value):
    if not article_url_supported(value):
        return None
    parts = urlsplit(value)
    return parts._replace(scheme='https', netloc='mp.weixin.qq.com').geturl()


def metrics(data):
    result = {k: v for k in STAT_KEYS if (v := count(data.get(k))) is not None}
    sources = data.get('read_user_source')
    if isinstance(sources, list):
        result['sources'] = [{'name': row['scene_desc'][:48], 'value': row['user_count']}
                             for row in sources[:24] if isinstance(row, dict)
                             and isinstance(row.get('scene_desc'), str) and count(row.get('user_count')) is not None]
    return result


def articles(rows, end):
    result = {}
    for row in rows:
        title = row.get('title')
        snapshots = row.get('detail_list')
        if not isinstance(title, str) or not isinstance(snapshots, list):
            continue
        links = readable_link(row.get('content_url'))
        if len(result.get(row['ref_date'], ())) >= 10:
            continue
        published = date.fromisoformat(row['ref_date'])
        available = []
        for obj in snapshots:
            if not isinstance(obj, dict) or not isinstance(obj.get('stat_date'), str):
                continue
            try:
                cutoff = date.fromisoformat(obj['stat_date'])
            except ValueError:
                continue
            if published <= cutoff <= min(end, published+29*DAY):
                available.append((cutoff, obj))
        item = {'title': title[:180], 'url': links, 'published': row['ref_date']}
        if available:
            cutoff, detail = max(available, key=lambda pair: pair[0])
            item.update(metrics(detail), stat_date=cutoff.isoformat())
            for field in ('read_finish_rate', 'read_avg_activetime'):
                value = detail.get(field)
                if type(value) in (int, float) and 0 <= value <= (1 if field.endswith('_rate') else 24 * 60):
                    item[field] = value
        result.setdefault(row['ref_date'], []).append(item)
    return result


def project(kind, rows, end):
    if kind == ARTICLE:
        return articles(rows, end)
    result = {}
    seen = set()
    for row in rows:
        day = row['ref_date']
        if kind == FANS:
            source = row.get('user_source')
            key = (day, count(source))
            if key[1] is None or key in seen:
                raise ValueError('invalid follower source')
            seen.add(key)
            fields = result.setdefault(day, {})
            for name in ('new_user', 'cancel_user'):
                amount = count(row.get(name))
                previous = fields.get(name, 0)
                fields[name] = amount + previous if amount is not None and previous is not None else None
        elif kind == TOTAL:
            if day in result:
                raise ValueError('invalid follower total')
            result[day] = {'cumulate_user': count(row.get('cumulate_user'))}
        elif kind == CONTENT:
            if day in result or not isinstance(row.get('detail'), dict):
                raise ValueError('invalid content stats')
            result[day] = metrics(row['detail'])
    return result


def decode(kind, response, token, first, last, end):
    if not isinstance(response, HTTPResponse) or not 200 <= response.status < 300:
        return 'UNAVAILABLE', {}, None
    try:
        body = strict_json(response.body, 2 * 1024 * 1024)
        if not isinstance(body, dict) or contains_secret(response.body, token):
            raise ValueError('unsafe API response')
        code = body.get('errcode', 0)
        if type(code) is not int or not -(2**31) <= code < 2**31:
            raise ValueError('malformed API error code')
        if code:
            state = 'PERMISSION' if code in PERMISSION_CODES else 'DELAYED' if code == 61503 else 'UNAVAILABLE'
            return state, {}, code
        rows = body.get('list')
        if not isinstance(rows, list) or any(not isinstance(row, dict) or not isinstance(row.get('ref_date'), str)
                or not first.isoformat() <= row['ref_date'] <= last.isoformat() or date.fromisoformat(row['ref_date']).isoformat() != row['ref_date'] for row in rows):
            raise ValueError('malformed date series')
        delay = body.get('is_delay', False)
        if type(delay) not in (str, bool) or delay not in (True, False, 'true', 'false'):
            raise ValueError('malformed delay state')
        values = project(kind, rows, end)
        if contains_secret(values, token, max_nodes=16384):
            raise ValueError('unsafe projected analytics')
        return ('DELAYED' if delay in (True, 'true') else 'READY'), values, None
    except (WCEError, ValueError, TypeError, RecursionError):
        return 'UNAVAILABLE', {}, None


class Analytics:
    def __init__(self, tokens, sender=None, clock=None):
        self.tokens = tokens
        self.sender = sender or HTTPSender(enabled=True, safe_transport_diagnostics=True)
        self.clock = clock or (lambda: datetime.now(BEIJING))
        self.days = {}

    def read(self, cid, days, refresh, guard, deadline):
        current = self.clock().astimezone(BEIJING)
        latest = current.date() - (DAY if current.hour >= 8 else 2*DAY)
        first = latest - (days-1)*DAY
        dates = [first + index*DAY for index in range(days)]
        now = current.timestamp()
        fresh = time.monotonic()
        self.days = {key: value for key, value in self.days.items() if key[1] >= latest-29*DAY}
        checks = {}
        observed_at = []
        token = None

        def fetch(kind, requested):
            nonlocal token
            missing = []
            for day in requested:
                saved = self.days.get((kind, day))
                if refresh or saved is None or saved[0] <= fresh:
                    missing.append(day)
            while missing:
                batch = missing[:1]
                for day in missing[1:WINDOWS[kind]]:
                    if day != batch[-1]+DAY:
                        break
                    batch.append(day)
                del missing[:len(batch)]
                if time.monotonic() >= deadline:
                    checks.setdefault(kind, []).append(('UNAVAILABLE', None))
                    break
                guard()
                if token is None:
                    token = self.tokens.get(guard)
                left = min(8.0, deadline - time.monotonic(), token.wall_deadline - time.time())
                if left <= 0 or not self.tokens.valid(token):
                    raise WCEError('OWN_TOKEN_UNAVAILABLE')
                path = DATACUBE_PATHS[kind] + '?' + urlencode({'access_token': secret_value(token.token)})
                body = json.dumps({'begin_date': batch[0].isoformat(), 'end_date': batch[-1].isoformat()}).encode('ascii')
                response = self.sender.send(HTTPRequest('POST', path, {'Content-Type': 'application/json'}, body), left)
                guard()
                state, values, code = decode(kind, response, token.token, batch[0], batch[-1], latest)
                ttl = 300 if state == 'READY' else 60
                affected = batch
                if state in {'PERMISSION', 'UNAVAILABLE'} or code == 61503:
                    # A range-level rejection/latency message isn't a daily zero.
                    affected = [day for day in requested if day >= batch[0]]
                    missing.clear()
                for day in affected:
                    previous = self.days.get((kind, day))
                    row = values.get(day.isoformat())
                    if row is None and previous and state != 'PERMISSION':
                        if previous[3] is not None and state != 'READY':
                            row = previous[3]
                    flag = 'EMPTY' if state == 'READY' and row is None else state
                    self.days[(kind, day)] = (fresh+ttl, flag, code, row, int(now))
            projection = {}
            for day in requested:
                saved = self.days.get((kind, day))
                if saved:
                    checks.setdefault(kind, []).append((saved[1], saved[2]))
                    observed_at.append(saved[4])
                    if saved[3] is not None:
                        projection[day] = saved[3]
            return projection

        fans = fetch(FANS, dates)
        totals = fetch(TOTAL, dates)
        content_days = [day for day in dates if day >= CONTENT_START]
        content = fetch(CONTENT, content_days)
        published = [day for day in reversed(content_days) if content.get(day, {}).get('send_page_count', 0) > 0]
        detail_days = sorted((published or list(reversed(content_days)))[:4])
        if any(state == 'PERMISSION' for state, _ in checks.get(CONTENT, ())):
            detail_days = detail_days[-1:]
        detail = fetch(ARTICLE, detail_days)
        records = [item for day in reversed(detail_days) for item in detail.get(day, ())]
        timeline = [{'date':day.isoformat(), **fans.get(day, {}), **totals.get(day, {}),
                     **{k:v for k,v in content.get(day,{}).items() if k != 'sources'}} for day in dates]
        states = {}
        for kind, values in checks.items():
            flags = {flag for flag, _ in values}
            codes = sorted({code for _,code in values if code is not None})
            states[kind] = {'states': sorted(flags), 'codes': codes}
        available = [row['date'] for row in timeline if any(v is not None for k,v in row.items() if k!='date')]
        guard()
        return {'connection_id': cid, 'days': days, 'start': first.isoformat(), 'end': latest.isoformat(),
                'read_at': max(observed_at, default=None), 'latest_data': available[-1] if available else None,
                'timeline': timeline, 'articles': records[:40], 'article_dates': len(detail_days), 'status': states}
