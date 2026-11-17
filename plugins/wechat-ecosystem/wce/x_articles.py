"""Account-scoped native X Articles and their original receipts."""

import re

from .contracts import WCEError
from .own_connection_policy import atomic_write, locked
from .x_api import identifier
from .x_discovery import require
from .x_platform import fingerprint


DRAFT = 'article-draft'
PUBLISH = 'article-publish'
TEXT_BLOCKS = ('unstyled', 'header-one', 'header-two', 'unordered-list-item',
               'ordered-list-item', 'blockquote')
READBACK_FIELDS = {'readback_state', 'readback_checks', 'post_url', 'article_url'}


def owned_image(x, state, cid, attempt_id):
    _, receipt = x._receipt(cid, 'upload', attempt_id)
    require(receipt and receipt['state'] == 'SUCCEEDED' and
            receipt.get('media_category', 'tweet_image') == 'tweet_image', 'X_ARTICLE_IMAGE_UNAVAILABLE')
    require(x._receipt_scope(state, cid, receipt) == state['connections'][cid]['credential_scope'],
            'X_MEDIA_APPLICATION_MISMATCH')
    result = receipt['result']
    require(result['expires_at'] > x.clock(), 'X_ARTICLE_IMAGE_UNAVAILABLE')
    return {'media_id': identifier(result['media_id']), 'media_category': 'tweet_image'}, result['media_key']


def draft_payload(x, state, cid, title, blocks, cover_attempt):
    projected, entities, image_keys = [], [], []
    for block in blocks:
        if block['type'] != 'image':
            projected.append(block)
            continue
        media, media_key = owned_image(x, state, cid, block['upload_attempt_id'])
        data = {'media_items': [media]}
        if 'caption' in block:
            data['caption'] = block['caption']
        key = len(entities)
        entities.append({'key': str(key), 'value': {'type': 'image', 'mutability': 'immutable', 'data': data}})
        projected.append({'type': 'atomic', 'text': ' ', 'entity_ranges': [{'key': key, 'offset': 0, 'length': 1}]})
        image_keys.append({'id': media['media_id'], 'key': media_key})
    payload = {'title': title, 'content_state': {'blocks': projected, 'entities': entities}}
    cover_key = None
    if cover_attempt is not None:
        payload['cover_media'], key = owned_image(x, state, cid, cover_attempt)
        cover_key = {'id': payload['cover_media']['media_id'], 'key': key}
    return payload, {'cover': cover_key, 'body': image_keys}


def claim(x, state, cid, kind, attempt_id, intent, path, send, **original):
    access = x._access(state, cid)
    receipt = {'connection_id': cid, 'kind': kind, 'attempt_id': attempt_id,
               'state': 'RESULT_UNKNOWN', 'created_at': x.clock(), 'fingerprint': fingerprint(intent),
               'application_scope': state['connections'][cid]['credential_scope'], **original}
    atomic_write(path, receipt, maximum=None)
    return x._send_receipt(path, receipt, send, access)


def create_draft(x, cid, attempt_id, title, blocks, cover_upload_attempt_id=None):
    intent = {'title': title, 'blocks': blocks, 'cover_upload_attempt_id': cover_upload_attempt_id}
    x._connection(cid)
    with locked(x.root / 'connection.lock'):
        state = x._load()
        x._connection(cid, state)
        path, original = x._receipt(cid, DRAFT, attempt_id)
        if original is not None:
            require(original['fingerprint'] == fingerprint(intent), 'X_ATTEMPT_CONFLICT')
            return original
        payload, media = draft_payload(x, state, cid, title, blocks, cover_upload_attempt_id)

        def send(access):
            response = x.api.article_draft(access, payload)
            data = response['data']
            article_id = identifier(data.get('id'))
            title_received = data.get('title')
            result = {'article_id': article_id, 'title': title_received if type(title_received) is str else None}
            if response.get('errors'):
                result['response_partial'] = True
            return result

        return claim(x, state, cid, DRAFT, attempt_id, intent, path, send,
                     input=intent, request=payload, media=media)


def publish(x, cid, draft_attempt_id):
    x._connection(cid)
    with locked(x.root / 'connection.lock'):
        state = x._load()
        connection = x._connection(cid, state)
        _, draft = x._receipt(cid, DRAFT, draft_attempt_id)
        require(draft and draft['state'] == 'SUCCEEDED', 'X_ARTICLE_DRAFT_NOT_AVAILABLE')
        require(not draft['result'].get('response_partial'), 'X_ARTICLE_DRAFT_RESPONSE_INCOMPLETE')
        require(draft['result']['title'] == draft['input']['title'], 'X_ARTICLE_DRAFT_TITLE_MISMATCH')
        article_id = draft['result']['article_id']
        path, original = x._receipt(cid, PUBLISH, article_id)
        if original is not None:
            require(original['draft_attempt_id'] == draft_attempt_id, 'X_ATTEMPT_CONFLICT')
            return original
        require(x._receipt_scope(state, cid, draft) == connection['credential_scope'],
                'X_ARTICLE_APPLICATION_MISMATCH')

        def send(access):
            response = x.api.article_publish(access, article_id)
            result = {'post_id': identifier(response['data'].get('post_id'))}
            if response.get('errors'):
                result['response_partial'] = True
            return result

        return claim(x, state, cid, PUBLISH, article_id, {'draft_attempt_id': draft_attempt_id},
                     path, send, article_id=article_id, draft_attempt_id=draft_attempt_id)


def object_field(obj, key):
    if type(obj) is not dict:
        return {}
    value = obj.get(key)
    return value if type(value) is dict else {}


def media_matches(actual, expected):
    if type(actual) is str:
        return actual in (expected['key'], expected['id'])
    if type(actual) is not dict:
        return False
    fields = {'media_key': expected['key'], 'media_id': expected['id']}
    observed = fields.keys() & actual.keys()
    return bool(observed) and all(actual[field] == fields[field] for field in observed)


def observed_article_url(post, article_id):
    urls = object_field(post, 'entities').get('urls')
    if type(urls) is list:
        for row in urls:
            url = row.get('expanded_url') if type(row) is dict else None
            if type(url) is str and re.fullmatch(
                    r'https://(?:www\.)?x\.com/i/article/' + article_id, url):
                return url
    return None


def check_readback(draft, publication, profile, response):
    post = object_field(response, 'data')
    article = object_field(post, 'article')
    expected = draft['media']
    post_id = publication['result']['post_id']
    def match(source, field, value):
        return None if field not in source else source[field] == value

    checks = {'post_id': match(post, 'id', post_id), 'author': match(post, 'author_id', profile['id']),
              'article_id': match(article, 'id', publication['article_id']),
              'title': match(article, 'title', draft['input']['title'])}
    if 'cover_media' not in article:
        checks['cover'] = None
    elif expected['cover'] is None:
        checks['cover'] = article['cover_media'] is None
    else:
        checks['cover'] = media_matches(article['cover_media'], expected['cover'])
    # Expansions can name the right media without proving their position in the article.
    actual_media = article.get('media_entities')
    checks['media_entities_order'] = (len(actual_media) == len(expected['body']) and
                                     all(media_matches(row, media) for row, media in zip(actual_media, expected['body']))
                                     if type(actual_media) is list else None)
    # The published Article object is open in the official read schema. Compare the
    # document only when the response supplies the same structural representation.
    content = object_field(article, 'content_state')
    checks['body_content'] = (content == draft['request']['content_state']
                              if type(content.get('blocks')) is list and
                              type(content.get('entities')) is list else None)
    if response and type(response) is dict and response.get('errors'):
        return {'readback_state': 'INCOMPLETE', 'readback_checks': {}}
    if False in checks.values():
        readback_state = 'MISMATCH'
    elif None in checks.values():
        readback_state = 'INCOMPLETE'
    else:
        readback_state = 'MATCHED'
    result = {'readback_state': readback_state, 'readback_checks': checks}
    if checks['post_id'] and checks['author']:
        result['post_url'] = 'https://x.com/' + profile['username'] + '/status/' + post_id
        url = observed_article_url(post, publication['article_id']) if checks['article_id'] else None
        if url is not None:
            result['article_url'] = url
    return result


def status(x, cid, draft_attempt_id, readback=False):
    with locked(x.root / 'connection.lock'):
        state = x._load()
        connection = state['connections'].get(cid)
        require(connection, 'X_CONNECTION_NOT_FOUND')
        _, draft = x._receipt(cid, DRAFT, draft_attempt_id)
        if draft is None:
            return {'connection_id': cid, 'draft_attempt_id': draft_attempt_id, 'state': 'NOT_FOUND'}
        result = {'connection_id': cid, 'draft': draft}
        if draft['state'] != 'SUCCEEDED':
            return result
        path, publication = x._receipt(cid, PUBLISH, draft['result']['article_id'])
        if publication is None:
            return result
        require(publication['draft_attempt_id'] == draft_attempt_id, 'X_ATTEMPT_CONFLICT')
        if readback and publication['state'] == 'SUCCEEDED':
            receipt = {key: value for key, value in publication.items() if key not in READBACK_FIELDS}
            try:
                token = x._access(state, cid, publication)
                response = x.api.article_post(token, publication['result']['post_id'])
            except WCEError as error:
                unavailable = {'readback_state': 'UNAVAILABLE', 'latest_readback_error': error.code}
                return result | {'publication': receipt | unavailable}
            publication = receipt | check_readback(draft, publication, connection['profile'], response)
            atomic_write(path, publication, maximum=None)
        return result | {'publication': publication}
