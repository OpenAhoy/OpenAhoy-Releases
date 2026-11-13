"""Official search parameters and post relationship checks, without an LLM or scheduler."""
from datetime import datetime, timezone
import re

from .contracts import WCEError
from .x_api import identifier

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
        require(type(row) is dict and row.get('type') in {'replied_to', 'quoted', 'retweeted'})
        result.append({'type': row['type'], 'id': identifier(row.get('id'))})
    # A response with an incompatible legacy field is not evidence of no parent.
    require('referenced_tweets' not in post, 'X_RELATIONSHIP_SCHEMA_UNSUPPORTED')
    require(len({(r['type'], r['id']) for r in result}) == len(result))
    return result


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
