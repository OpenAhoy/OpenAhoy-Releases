"""Small official X v2 transport. No retries, credentials in URLs, or redirects."""
import base64
from http.client import HTTPException
import json
import math
import re
import uuid
from datetime import datetime
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import HTTPRedirectHandler, Request, build_opener

from .contracts import Secret, WCEError

SCOPES = ('tweet.read', 'users.read', 'tweet.write', 'media.write', 'offline.access')
CALLBACK = 'http://127.0.0.1:62197/x/callback'
PLATFORM = {'id': 'x', 'name': 'X', 'account_noun': 'X 账号',
            'account_id_label': 'X User ID', 'settings_supported': False,
            'binding_supported': True, 'settings_help': '通过 X 官方页面授权，名称和头像从 X 读取。'}


def identifier(value):
    if type(value) is not str or re.fullmatch(r'[0-9]{1,19}', value) is None:
        raise WCEError('X_INVALID_PLATFORM_ID')
    return value


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs):
        return None


X_RESPONSE_ERROR_KINDS = frozenset({'TIMEOUT', 'TRANSPORT_ERROR', 'RESPONSE_DECODE_ERROR'})
READ_PROBLEMS = {
    'not-authorized-for-resource': 'X_READ_PERMISSION_DENIED',
    'client-forbidden': 'X_READ_PERMISSION_DENIED',
    'usage-capped': 'X_READ_QUOTA_EXCEEDED',
    'rate-limit-exceeded': 'X_READ_RATE_LIMITED',
    'resource-not-found': 'X_READ_RESOURCE_UNAVAILABLE',
    'invalid-request': 'X_READ_REQUEST_INVALID',
}
READ_HTTP_CODES = {
    400: 'X_READ_REQUEST_INVALID', 401: 'X_READ_PERMISSION_DENIED',
    402: 'X_READ_QUOTA_EXCEEDED', 403: 'X_READ_PERMISSION_DENIED',
    404: 'X_READ_RESOURCE_UNAVAILABLE', 410: 'X_READ_RESOURCE_UNAVAILABLE',
    429: 'X_READ_RATE_LIMITED',
}
READ_UNKNOWN = 'X_READ_UPSTREAM_UNKNOWN'
READ_CODES = frozenset(READ_PROBLEMS.values()) | {READ_UNKNOWN,
    'X_READ_AUTHOR_INCOMPLETE', 'X_READ_CONTEXT_INCOMPLETE', 'X_READ_MEDIA_INCOMPLETE',
    'X_READ_PAGE_INCOMPLETE', 'X_SEARCH_CURSOR_INVALID'}


def read_problem(row):
    if type(row) is not dict:
        return READ_UNKNOWN
    kind = row.get('type')
    if type(kind) is str:
        match = re.fullmatch(r'https://api\.(?:x|twitter)\.com/2/problems/([a-z-]+)', kind)
        if match and match[1] in READ_PROBLEMS:
            return READ_PROBLEMS[match[1]]
    status = row.get('status')
    return READ_HTTP_CODES.get(status, READ_UNKNOWN) if type(status) is int else READ_UNKNOWN


def read_problem_codes(errors):
    if type(errors) is not list:
        return {READ_UNKNOWN}
    return {read_problem(row) for row in errors}


def read_http_error(error):
    # Only structured problem types are read. Free-form details never leave
    # this function, including when an HTTP 429 represents a usage cap.
    try:
        raw = error.read(32769)
        value = json.loads(raw) if len(raw) <= 32768 else {}
    except (ValueError, OSError, HTTPException, RecursionError):
        value = {}
    codes = read_problem_codes(value.get('errors', [value])) if type(value) is dict else set()
    known = codes - {READ_UNKNOWN}
    if len(known) == 1:
        return known.pop()
    return READ_HTTP_CODES.get(error.code, READ_UNKNOWN)


class XResponseUnknown(WCEError):
    def __init__(self, kind):
        if kind not in X_RESPONSE_ERROR_KINDS:
            raise ValueError('Invalid X response error kind')
        self.kind = kind
        super().__init__('X_RESPONSE_UNKNOWN')


class XHTTP:
    def __init__(self):
        self.opener = build_opener(NoRedirect())

    def request(self, method, path, *, token=None, body=None, query=None, form=False, multipart=None,
                user_post_read=False):
        article_write = method == 'POST' and re.fullmatch(r'/2/articles/(draft|[0-9]{1,19}/publish)', path)
        if user_post_read and (method != 'GET' or re.fullmatch(
                r'/2/(?:tweets/(?:[0-9]{1,19}|search/recent)|users/[0-9]{1,19}/tweets)', path) is None):
            raise WCEError('X_ENDPOINT_UNSUPPORTED')
        if not article_write and (method, path) != ('GET', '/2/usage/credits') and (method not in {'GET', 'POST'} or re.fullmatch(
                r'/2/(oauth2/token|users/me|users/by/username/[A-Za-z0-9_]{1,15}|users/[0-9]{1,19}/tweets|tweets/search/recent|tweets(?:/[0-9]{1,19})?|media/upload(?:/initialize|/[0-9]{1,19}/(?:append|finalize))?)', path) is None):
            raise WCEError('X_ENDPOINT_UNSUPPORTED')
        url = 'https://api.x.com' + path
        if query:
            url += '?' + urlencode(query)
        headers = {'Accept': 'application/json', 'User-Agent': 'OpenAhoy-X/1'}
        if token is not None:
            if type(token) is not Secret:
                raise WCEError('X_INVALID_CREDENTIAL')
            headers['Authorization'] = 'Bearer ' + token.reveal_for_adapter()
        raw = None
        if multipart is not None:
            if body is not None or form or not re.fullmatch(r'/2/media/upload/[0-9]{1,19}/append',path):
                raise WCEError('X_ENDPOINT_UNSUPPORTED')
            index,chunk=multipart
            if type(index)is not int or not 0<=index<=9999 or type(chunk)is not bytes:
                raise WCEError('X_MEDIA_SEGMENT_INVALID')
            boundary='OpenAhoy'+uuid.uuid4().hex
            raw=(('--'+boundary+'\r\nContent-Disposition: form-data; name="segment_index"\r\n\r\n'+str(index)+'\r\n--'+boundary+'\r\nContent-Disposition: form-data; name="media"; filename="segment"\r\nContent-Type: application/octet-stream\r\n\r\n').encode()+chunk+('\r\n--'+boundary+'--\r\n').encode())
            headers['Content-Type']='multipart/form-data; boundary='+boundary
        elif body is not None:
            raw = (urlencode(body) if form else json.dumps(body, ensure_ascii=False)).encode()
            headers['Content-Type'] = 'application/x-www-form-urlencoded' if form else 'application/json'
        try:
            with self.opener.open(Request(url, raw, headers, method=method), timeout=30) as response:
                response_raw=response.read()
                value = {} if not response_raw and path.endswith('/append') else json.loads(response_raw)
            if type(value) is not dict or (value.get('errors') and not (article_write or user_post_read)):
                raise WCEError('X_RESPONSE_INCOMPLETE')
            return value
        except HTTPError as error:
            # Never surface the response body, request, token or callback code.
            try:
                code = read_http_error(error) if user_post_read else 'X_HTTP_' + str(error.code)
            finally:
                error.close()
            raise WCEError(code) from None
        except WCEError:
            raise
        except URLError as error:
            kind = 'TIMEOUT' if isinstance(error.reason, TimeoutError) else 'TRANSPORT_ERROR'
            raise XResponseUnknown(kind) from None
        except TimeoutError:
            raise XResponseUnknown('TIMEOUT') from None
        except (OSError, HTTPException):
            raise XResponseUnknown('TRANSPORT_ERROR') from None
        except (ValueError, RecursionError):
            raise XResponseUnknown('RESPONSE_DECODE_ERROR') from None

    def exchange(self, client_id, code, verifier):
        return self.request('POST', '/2/oauth2/token', form=True, body={
            'grant_type': 'authorization_code', 'client_id': client_id, 'code': code,
            'code_verifier': verifier, 'redirect_uri': CALLBACK})

    def refresh(self, client_id, refresh_token):
        return self.request('POST', '/2/oauth2/token', form=True, body={
            'grant_type': 'refresh_token', 'client_id': client_id,
            'refresh_token': refresh_token.reveal_for_adapter()})

    def credits(self, token):
        value = self.request('GET', '/2/usage/credits', token=token).get('data')
        def amount(number, *, signed=False):
            if (type(number) not in {int, float} or (type(number) is float and not math.isfinite(number))
                    or (not signed and number < 0)):
                raise WCEError('X_CREDITS_RESPONSE_INVALID')
            return number
        if type(value) is not dict or type(value.get('free_grants')) is not list:
            raise WCEError('X_CREDITS_RESPONSE_INVALID')
        grants = []
        for grant in value['free_grants']:
            if type(grant) is not dict:
                raise WCEError('X_CREDITS_RESPONSE_INVALID')
            expires = grant.get('expires_at')
            try:
                if 'expires_at' in grant and (type(expires) is not str or 'T' not in expires
                        or datetime.fromisoformat(expires.replace('Z', '+00:00')).utcoffset() is None):
                    raise ValueError()
            except ValueError:
                raise WCEError('X_CREDITS_RESPONSE_INVALID') from None
            grants.append({'amount': amount(grant.get('amount')), 'expires_at': expires})
        return {'total_balance': amount(value.get('total_balance')),
                'prepaid_balance': amount(value.get('prepaid_balance'), signed=True),
                'free_balance': amount(value.get('free_balance')), 'free_grants': grants}

    def profile(self, token):
        data = self.request('GET', '/2/users/me', token=token,
                            query={'user.fields': 'id,name,username,profile_image_url'})['data']
        identifier(data.get('id'))
        if (type(data.get('name')) is not str or not data['name'] or
                type(data.get('username')) is not str or re.fullmatch(r'[A-Za-z0-9_]{1,15}', data['username']) is None):
            raise WCEError('X_PROFILE_INVALID')
        result = {key: data[key] for key in ('id', 'name', 'username')}
        avatar = data.get('profile_image_url')
        if type(avatar) is str and re.fullmatch(r'https://pbs\.twimg\.com/profile_images/[A-Za-z0-9_./-]+', avatar):
            result['profile_image_url'] = avatar
        return result

    @staticmethod
    def post_query():
        return {'post.fields': 'id,text,attachments,created_at,entities',
                'expansions': 'author_id,attachments.media_keys', 'media.fields': 'media_key,type,url'}

    def posts(self, token, user_id, *, cursor=None, start_time=None, user_post_read=False):
        query = self.post_query() | {'max_results': 5}
        if cursor:
            query['pagination_token'] = cursor
        if start_time:
            query['start_time'] = start_time
        return self.request('GET', '/2/users/' + identifier(user_id) + '/tweets', token=token, query=query,
                            user_post_read=user_post_read)

    def post(self, token, post_id, *, user_post_read=False, include_note=False):
        query = self.post_query()
        query['expansions'] += ',referenced_posts'
        if user_post_read or include_note:
            query['post.fields'] += ',note_post'
        return self.request('GET', '/2/tweets/' + identifier(post_id), token=token, query=query,
                            user_post_read=user_post_read)

    def article_draft(self, token, content):
        return self.request('POST', '/2/articles/draft', token=token, body=content)

    def article_publish(self, token, article_id):
        return self.request('POST', '/2/articles/' + identifier(article_id) + '/publish', token=token)

    def article_post(self, token, post_id):
        query = {'post.fields': 'id,article,article_title,entities',
                 'expansions': 'author_id,article.cover_media,article.media_entities',
                 'media.fields': 'media_key,type'}
        return self.request('GET', '/2/tweets/' + identifier(post_id), token=token, query=query)

    @staticmethod
    def context_query():
        # Current X docs use post.fields / referenced_posts / note_post.
        # Keep the original illustrated-post representation unchanged.
        return {'post.fields': 'id,text,created_at,entities,conversation_id,lang,public_metrics,reply_settings,note_post',
                'expansions': 'author_id,referenced_posts,entities.mentions.username',
                'user.fields': 'id,name,username,verified,verified_type'}

    def user(self, token, username):
        if type(username) is not str or re.fullmatch(r'[A-Za-z0-9_]{1,15}', username) is None:
            raise WCEError('X_USERNAME_INVALID')
        return self.request('GET', '/2/users/by/username/' + username, token=token,
                            query={'user.fields': 'id,name,username,verified,verified_type'})

    def search(self, token, query, *, user_post_read=False, **options):
        return self.request('GET', '/2/tweets/search/recent', token=token,
                            query=self.context_query() | {'query': query} | options,
                            user_post_read=user_post_read)

    def context(self, token, post_id, *, user_post_read=False):
        query = self.context_query()
        if user_post_read:
            query['post.fields'] += ',attachments'
            query['expansions'] += ',attachments.media_keys'
            query['media.fields'] = self.post_query()['media.fields']
        return self.request('GET', '/2/tweets/' + identifier(post_id), token=token, query=query,
                            user_post_read=user_post_read)

    def reply_posts(self, token, user_id, *, cursor=None, start_time=None):
        query = self.context_query() | {'max_results': 100}
        if cursor:
            query['pagination_token'] = cursor
        if start_time:
            query['start_time'] = start_time
        return self.request('GET', '/2/users/' + identifier(user_id) + '/tweets', token=token, query=query)

    def reply(self, token, post_id, text):
        return self.request('POST', '/2/tweets', token=token,
                            body={'text': text, 'reply': {'in_reply_to_tweet_id': identifier(post_id)}})

    def upload(self, token, raw):
        return self.request('POST', '/2/media/upload', token=token, body={
            'media': base64.b64encode(raw).decode('ascii'), 'media_category': 'tweet_image'})

    def media_initialize(self, token, total_bytes, media_type, media_category):
        return self.request('POST','/2/media/upload/initialize',token=token,body={
            'total_bytes':total_bytes,'media_type':media_type,'media_category':media_category})

    def media_append(self, token, media_id, index, chunk):
        return self.request('POST','/2/media/upload/'+identifier(media_id)+'/append',token=token,multipart=(index,chunk))

    def media_finalize(self, token, media_id):
        return self.request('POST','/2/media/upload/'+identifier(media_id)+'/finalize',token=token)

    def media_status(self, token, media_id):
        return self.request('GET','/2/media/upload',token=token,query={'media_id':identifier(media_id),'command':'STATUS'})

    def create(self, token, text, media_ids, *, made_with_ai=None):
        body = {'text': text}
        if media_ids:
            body['media'] = {'media_ids': media_ids}
        if made_with_ai is not None:
            body['made_with_ai'] = made_with_ai
        return self.request('POST', '/2/tweets', token=token, body=body)
