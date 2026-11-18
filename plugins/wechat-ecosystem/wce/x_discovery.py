"""Official search parameters and post relationship checks, without an LLM or scheduler."""
from datetime import datetime, timezone
import re

from .contracts import WCEError
from .x_api import READ_PROBLEMS, READ_HTTP_CODES, READ_UNKNOWN, identifier, read_problem_codes

DISCOVERY_TYPES = ('key_people', 'topics', 'friendship', 'prescribed_reply')


def require(value, code='X_CONTEXT_INCOMPLETE'):
    if not value:
        raise WCEError(code)


def search_options(query, options, now):
    require(type(query) is str and 1 <= len(query) <= 4096, 'X_SEARCH_QUERY_INVALID')
    allowed = {'max_results', 'start_time', 'end_time', 'since_id', 'until_id',
               'next_token', 'pagination_token', 'sort_order'}
    require(type(options) is dict and not set(options) - allowed, 'X_SEARCH_PARAMETERS_INVALID')
    out = dict(options)
    require(all(not (a in out and b in out) for a, b in (
        ('start_time', 'since_id'), ('end_time', 'until_id'), ('next_token', 'pagination_token'))),
        'X_SEARCH_PARAMETERS_CONFLICT')
    require(type(out.get('max_results', 100)) is int and 10 <= out.get('max_results', 100) <= 100,
            'X_SEARCH_PAGE_SIZE_INVALID')
    require(out.get('sort_order', 'recency') in {'recency', 'relevancy'}, 'X_SEARCH_PARAMETERS_INVALID')
    for key in ('since_id', 'until_id'):
        if key in out: identifier(out[key])
    for key in ('next_token', 'pagination_token'):
        if key in out: require(type(out[key]) is str and bool(out[key]), 'X_SEARCH_CURSOR_INVALID')
    times = {}
    for key in ('start_time', 'end_time'):
        if key in out:
            require(type(out[key]) is str and re.fullmatch(r'\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?Z', out[key]),
                    'X_SEARCH_TIME_INVALID')
            try:
                times[key] = datetime.fromisoformat(out[key].replace('Z', '+00:00')).timestamp()
            except ValueError:
                raise WCEError('X_SEARCH_TIME_INVALID') from None
    require(not ('start_time' in times and 'end_time' in times and times['start_time'] >= times['end_time']),
            'X_SEARCH_TIME_INVALID')
    if not {'end_time', 'until_id'} & set(out):
        # X requires end_time to be at least ten seconds old. Freeze this first
        # page's end, then require the caller to retain it on every continuation.
        require(not {'next_token', 'pagination_token'} & set(out), 'X_SEARCH_WINDOW_REQUIRED')
        out['end_time'] = datetime.fromtimestamp(now - 30, timezone.utc).isoformat(timespec='seconds').replace('+00:00', 'Z')
    return {'max_results': 100, 'sort_order': 'recency'} | out


def post_data(result, post_id):
    require(type(result) is dict and not result.get('errors'))
    post = result.get('data')
    require(type(post) is dict and post.get('id') == post_id and type(post.get('text')) is str)
    identifier(post.get('author_id'))
    return post


def references(post):
    rows = post.get('referenced_posts', [])
    require(type(rows) is list)
    result = []
    for row in rows:
        require(type(row) is dict and row.get('type') in ('replied_to', 'quoted', 'retweeted'))
        result.append({'type': row['type'], 'id': identifier(row.get('id'))})
    # A response with an incompatible legacy field is not evidence of no parent.
    require('referenced_tweets' not in post, 'X_RELATIONSHIP_SCHEMA_UNSUPPORTED')
    require(len({(r['type'], r['id']) for r in result}) == len(result))
    return result


def read_diagnostic(codes):
    upstream = set(READ_PROBLEMS.values()) | set(READ_HTTP_CODES.values())
    ordered = sorted(codes, key=lambda code: (code not in upstream, code == READ_UNKNOWN, code))
    return {'code': ordered[0], 'codes': ordered}


def read_payload(result, code):
    require(type(result) is dict, code)
    # Project known envelope members. Problem URLs, free text, resource IDs
    # inside errors, and other upstream diagnostic properties stay private.
    payload = {key: result[key] for key in ('data', 'includes', 'meta') if key in result}
    return payload, read_problem_codes(result.get('errors', []))


def single_post_read(result, post_id):
    payload, codes = read_payload(result, 'X_CONTEXT_INCOMPLETE')
    post = payload.get('data')
    if post is None and codes:
        raise WCEError(read_diagnostic(codes)['code'])
    require(type(post) is dict and post.get('id') == post_id and type(post.get('text')) is str)
    try:
        identifier(post.get('author_id'))
    except WCEError:
        codes.add('X_READ_AUTHOR_INCOMPLETE')
        post = {key: value for key, value in post.items() if key != 'author_id'}
        payload['data'] = post

    try:
        refs = references(post)
    except WCEError:
        refs = []
        codes.add('X_READ_CONTEXT_INCOMPLETE')
    expanded = payload.get('includes', {})
    if type(expanded) is not dict:
        codes.add('X_READ_CONTEXT_INCOMPLETE')
        payload.pop('includes')
        expanded = {}
    posts = expanded.get('posts', [])
    if type(posts) is not list:
        codes.add('X_READ_CONTEXT_INCOMPLETE')
        posts = []
    available = {r['id'] for r in posts if type(r) is dict and type(r.get('id')) is str
                 and type(r.get('text')) is str}
    missing_context = list(dict.fromkeys(ref['id'] for ref in refs if ref['id'] not in available))
    if missing_context:
        codes.add('X_READ_CONTEXT_INCOMPLETE')

    attachments = post.get('attachments', {})
    keys = attachments.get('media_keys', []) if type(attachments) is dict else None
    if type(keys) is not list or any(type(key) is not str or not key for key in keys):
        keys = []
        codes.add('X_READ_MEDIA_INCOMPLETE')
    media = expanded.get('media', [])
    if type(media) is not list:
        media = []
        codes.add('X_READ_MEDIA_INCOMPLETE')
    complete_media = []
    for row in media:
        if (type(row) is dict and type(row.get('media_key')) is str
                and row.get('type') in ('photo', 'video', 'animated_gif')
                and (row['type'] != 'photo' or (type(row.get('url')) is str and row['url'].startswith('https://')))):
            complete_media.append(row['media_key'])
    missing_media = list(dict.fromkeys(key for key in keys if complete_media.count(key) != 1))
    if missing_media:
        codes.add('X_READ_MEDIA_INCOMPLETE')
    info = {'state': 'PARTIAL' if codes else 'COMPLETE', 'result': payload, 'references': refs,
            'missing_context_ids': missing_context, 'missing_media_keys': missing_media,
            'content_is_untrusted': True}
    if codes:
        info['diagnostic'] = read_diagnostic(codes)
    return info


def post_page_read(result, request_cursor, *, search=False):
    incomplete = 'X_SEARCH_INCOMPLETE' if search else 'X_TIMELINE_INCOMPLETE'
    payload, codes = read_payload(result, incomplete)
    data, meta = payload.get('data', []), payload.get('meta', {})
    has_errors = bool(codes)
    rows, ids, duplicate_ids = [], set(), set()
    if type(data) is not list:
        require(has_errors, incomplete)
        codes.add('X_READ_PAGE_INCOMPLETE')
        data = []
    for row in data:
        try:
            require(type(row) is dict, incomplete)
            pid = identifier(row.get('id'))
            require(type(row.get('text')) is str, incomplete)
        except WCEError:
            require(has_errors, incomplete)
            codes.add('X_READ_PAGE_INCOMPLETE')
            continue
        if search:
            try:
                identifier(row.get('author_id'))
            except WCEError:
                require(has_errors, incomplete)
                codes.add('X_READ_AUTHOR_INCOMPLETE')
                row = {key: value for key, value in row.items() if key != 'author_id'}
        if pid in ids:
            require(has_errors, incomplete)
            duplicate_ids.add(pid)
            codes.add('X_READ_PAGE_INCOMPLETE')
            continue
        ids.add(pid)
        rows.append(row)
    rows = [row for row in rows if row['id'] not in duplicate_ids]
    if type(meta) is not dict:
        require(has_errors, incomplete)
        codes.add('X_READ_PAGE_INCOMPLETE')
        meta = {}
    count = meta.get('result_count')
    count_matches = type(count) is int and count == len(data)
    if not count_matches and (search or count is not None or 'data' not in payload):
        require(has_errors, incomplete)
        codes.add('X_READ_PAGE_INCOMPLETE')

    cursor = meta.get('next_token')
    if cursor is not None and (type(cursor) is not str or not re.fullmatch(r'[A-Za-z0-9._~+/=-]+', cursor)
                               or cursor == request_cursor):
        require(has_errors, 'X_SEARCH_CURSOR_INVALID')
        codes.add('X_SEARCH_CURSOR_INVALID')
        cursor = None
    if codes and not rows:
        # A continuation may still be valid. Return it without a count or
        # empty data array so the failed page cannot be consumed as zero.
        diagnostic = read_diagnostic(codes)
        if cursor is None:
            raise WCEError(diagnostic['code'])
        return {'state': 'FAILED', 'page_state': 'FAILED', 'next_token': cursor,
                'result': {'meta': {'next_token': cursor}}, 'diagnostic': diagnostic}
    if codes:
        payload['data'] = rows
        payload['meta'] = {'result_count': len(rows)}
        if cursor is not None:
            payload['meta']['next_token'] = cursor
        return {'state': 'PARTIAL', 'page_state': 'PARTIAL', 'next_token': cursor, 'result': payload,
                'diagnostic': read_diagnostic(codes)}
    state = 'MORE' if cursor else 'COMPLETE'
    return {'state': state, 'page_state': state, 'next_token': cursor, 'result': payload}


def text_forms(post, url_text):
    import html
    forms = [post.get('text'), url_text(post)]
    note = post.get('note_post')
    if type(note) is dict and type(note.get('text')) is str:
        forms += [note['text'], url_text(post | note)]
    return forms + [html.unescape(t) for t in forms if type(t) is str]


def reply_matches(post, account_id, content, url_text):
    try:
        refs = references(post)
        return (post.get('author_id') == account_id and content['text'] in text_forms(post, url_text)
                and [r['id'] for r in refs if r['type'] == 'replied_to'] == [content['parent_id']])
    except WCEError:
        return False
