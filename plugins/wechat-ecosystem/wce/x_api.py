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


class XResponseUnknown(WCEError):
    def __init__(self, kind):
        if kind not in X_RESPONSE_ERROR_KINDS:
            raise ValueError('Invalid X response error kind')
        self.kind = kind
        super().__init__('X_RESPONSE_UNKNOWN')


class XHTTP:
    def __init__(self):
        self.opener = build_opener(NoRedirect())

    def request(self, method, path, *, token=None, body=None, query=None, form=False, multipart=None):
        if (method, path) != ('GET', '/2/usage/credits') and (method not in {'GET', 'POST'} or re.fullmatch(
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
            if type(value) is not dict or value.get('errors'):
                raise WCEError('X_RESPONSE_INCOMPLETE')
            return value
        except HTTPError as error:
            # Never surface the response body, request, token or callback code.
            status = error.code
            error.close()
            raise WCEError('X_HTTP_' + str(status)) from None
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

    def posts(self, token, user_id, *, cursor=None, start_time=None):
        query = self.post_query() | {'max_results': 5}
        if cursor:
            query['pagination_token'] = cursor
        if start_time:
            query['start_time'] = start_time
        return self.request('GET', '/2/users/' + identifier(user_id) + '/tweets', token=token, query=query)

    def post(self, token, post_id):
        return self.request('GET', '/2/tweets/' + identifier(post_id), token=token, query=self.post_query())

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

    def search(self, token, query, **options):
        return self.request('GET', '/2/tweets/search/recent', token=token,
                            query=self.context_query() | {'query': query} | options)

    def context(self, token, post_id):
        return self.request('GET', '/2/tweets/' + identifier(post_id), token=token, query=self.context_query())

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
        body = {'text': text, 'media': {'media_ids': media_ids}}
        if made_with_ai is not None:
            body['made_with_ai'] = made_with_ai
        return self.request('POST', '/2/tweets', token=token, body=body)
