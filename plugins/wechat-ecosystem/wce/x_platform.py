"""Explicit account-scoped X identities and private OAuth credentials."""
from copy import deepcopy
from contextlib import nullcontext
from datetime import datetime, timezone
from hashlib import sha256
import json
import html
import os
from pathlib import Path
import re
import secrets
import time

from .bounded_file import FileSource
from .contracts import Secret, WCEError
from .own_account_metadata import read_metadata
from .own_bootstrap_security import path_check
from .own_connection_policy import atomic_write, locked, registry_path
from .own_connection_registry import mkdir
from .x_api import CALLBACK, SCOPES, XHTTP, identifier
from .x_application import CLIENT_ID
from .x_oauth import OAuthFlow
from .x_discovery import DISCOVERY_TYPES, post_data, references, reply_matches, require, search_options


def fingerprint(value):
    return sha256(json.dumps(value, sort_keys=True, separators=(',', ':'), ensure_ascii=False).encode()).hexdigest()


def credential(value, old_refresh=None):
    if (type(value) is not dict or value.get('token_type', '').lower() != 'bearer'
            or type(value.get('access_token')) is not str or not value['access_token']
            or type(value.get('expires_in')) is not int or value['expires_in'] <= 0
            or set(value.get('scope', ' '.join(SCOPES) if old_refresh else '').split()) != set(SCOPES)):
        raise WCEError('X_AUTHORIZATION_SCOPES_INVALID')
    refresh = value.get('refresh_token', old_refresh)
    if type(refresh) is not str or not refresh:
        raise WCEError('X_OFFLINE_ACCESS_MISSING')
    return Secret(json.dumps({'access_token': value['access_token'], 'refresh_token': refresh}, separators=(',', ':')))


class XPlatform:
    def __init__(self, *, root=None, api=None, keychain=None, flow_factory=OAuthFlow, clock=time.time):
        self.root = Path(root) if root is not None else registry_path().parent / 'x-platform'
        self.api = api or XHTTP()
        self._keychain = keychain
        self.flow_factory, self.clock = flow_factory, clock
        self.flow = None
        self.flow_handle = None

    @property
    def keychain(self):
        if self._keychain is None:
            from .x_keychain import XKeychain
            self._keychain = XKeychain()
        return self._keychain

    def _prepare(self):
        if not os.path.lexists(self.root):
            path_check(self.root.parent, True)
            mkdir(self.root.parent, self.root.name)
        path_check(self.root, True)

    def _load(self):
        empty={'schema':2,'client_id':CLIENT_ID,'connections':{}}
        if not os.path.lexists(self.root):return empty
        path_check(self.root,True)
        value=read_metadata(self.root/'connection.json')
        if value is None:return empty
        if type(value)is not dict:raise WCEError('X_CONNECTION_INVALID')
        # Read-only normalization: installing/listing never rewrites old state.
        if value.get('schema')==1 and set(value)=={'schema','client_id','connection'}:
            c=value['connection']
            if c is not None and (type(c)is not dict or type(c.get('connection_id'))is not str):raise WCEError('X_CONNECTION_INVALID')
            value={'schema':2,'client_id':value['client_id'],'connections':{} if c is None else {c['connection_id']:c}}
        if set(value)!={'schema','client_id','connections'} or value['schema']!=2 or type(value['connections'])is not dict:
            raise WCEError('X_CONNECTION_INVALID')
        if type(value['client_id'])is not str or (value['client_id'] and re.fullmatch(r'[A-Za-z0-9._~+/=-]+',value['client_id'])is None):
            raise WCEError('X_CLIENT_ID_INVALID')
        for cid,c in value['connections'].items():
            if type(c)is not dict or set(c)!={'connection_id','profile','scope','expires_at','state','credential_scope'} or type(c['profile'])is not dict:
                raise WCEError('X_CONNECTION_INVALID')
            user=identifier(c['profile'].get('id'))
            scope=fingerprint(['x',value['client_id'],user])
            if cid!='x-'+user or c['connection_id']!=cid or c['credential_scope']!=scope or c['scope']!=list(SCOPES):
                raise WCEError('X_CONNECTION_INVALID')
        return value

    def _save(self,value):
        # Called only under the existing connection lock. Preserve the complete old
        # metadata before the first necessary write; never change Keychain scope.
        path=self.root/'connection.json'
        old=read_metadata(path)
        if type(old)is dict and old.get('schema')==1:
            backup=self.root/'connection.schema1.before-multi.json'
            if not os.path.lexists(backup):atomic_write(backup,old,maximum=None)
        atomic_write(path,value,maximum=None)

    def overview(self):
        try:
            rows=[]
            for c in self._load()['connections'].values():
                profile=c['profile']
                rows.append({'platform_id':'x','connection_id':c['connection_id'],'account_id':profile['id'],
                    'state':'BOUND_IDLE' if c['state']=='BOUND' else 'ACTION_REQUIRED',
                    'presentation':{'display_name':profile['name'],'avatar':None},
                    'username':profile['username'],'profile_image_url':profile.get('profile_image_url')})
            return rows
        except WCEError:
            return [{'platform_id':'x','connection_id':'x-unavailable','state':'ACTION_REQUIRED',
                     'presentation':{'display_name':'X 连接需要处理','avatar':None}}]

    def settings(self,authorization_handle=None):
        value=self._load()
        authorization=self.flow.snapshot() if self.flow and authorization_handle==self.flow_handle else {'state':'NOT_STARTED','result':None}
        return {'client_id':value['client_id'],'callback_uri':CALLBACK,'required_scopes':list(SCOPES),
                'connections':deepcopy(list(value['connections'].values())),'authorization':authorization}

    def configure(self, client_id):
        if type(client_id) is not str or re.fullmatch(r'[A-Za-z0-9._~+/=-]{1,4096}', client_id) is None:
            raise WCEError('X_CLIENT_ID_INVALID')
        self._prepare()
        if self.flow and self.flow.snapshot()['state'] in {'AWAITING_AUTHORIZATION', 'EXCHANGING'}:
            raise WCEError('X_AUTHORIZATION_IN_PROGRESS')
        with locked(self.root / 'connection.lock'):
            value = self._load()
            if value['connections'] and value['client_id'] != client_id:
                raise WCEError('X_APPLICATION_ALREADY_BOUND')
            value['client_id'] = client_id
            self._save(value)
        return {'state': 'X_APPLICATION_CONFIGURED', 'callback_uri': CALLBACK}

    def begin(self, expected_connection_id=None):
        value = self._load()
        if not value['client_id']:
            raise WCEError('X_APPLICATION_REQUIRED')
        if expected_connection_id is not None and expected_connection_id not in value['connections']:
            raise WCEError('X_CONNECTION_NOT_FOUND')
        # All host processes share this OS lock for the fixed callback listener.
        if self.flow:
            if self.flow.snapshot()['state'] in {'AWAITING_AUTHORIZATION', 'EXCHANGING'}:
                raise WCEError('X_AUTHORIZATION_IN_PROGRESS')
            self.flow.close()
        self.flow_handle='x-auth-'+secrets.token_hex(24)
        finish=lambda client,tokens,guard=nullcontext:self._finish(client,tokens,guard,expected_connection_id=expected_connection_id)
        self.flow = self.flow_factory(value['client_id'], self.api, finish)
        return {'state': 'AWAITING_AUTHORIZATION', 'authorization_handle':self.flow_handle, 'authorization_url': self.flow.authorization_url()}

    def _finish(self, client_id, token_value, guard=nullcontext, *, expected_connection_id=None):
        secret = credential(token_value)
        tokens = json.loads(secret.reveal_for_adapter())
        profile = self.api.profile(Secret(tokens['access_token']))
        self._prepare()
        with guard(), locked(self.root / 'connection.lock'):
            value = self._load()
            if value['client_id'] != client_id:
                raise WCEError('X_APPLICATION_CHANGED')
            cid='x-'+profile['id']
            if expected_connection_id is not None and (expected_connection_id not in value['connections'] or cid!=expected_connection_id):
                raise WCEError('X_AUTHORIZATION_ACCOUNT_MISMATCH')
            scope = fingerprint(['x', client_id, profile['id']])
            # Save a reauthorization marker before touching a rotating credential.
            # A crash cannot turn uncommitted new credentials into an active grant.
            c = {'connection_id': 'x-' + profile['id'], 'profile': profile, 'scope': list(SCOPES),
                 'expires_at': self.clock() + token_value['expires_in'],
                 'state': 'CREDENTIAL_COMMIT_PENDING', 'credential_scope': scope}
            value['connections'][c['connection_id']] = c
            self._save(value)
            self.keychain.put(scope, secret)
            c['state'] = 'BOUND'
            self._save(value)
        return {'connection_id': c['connection_id'], 'profile': profile, 'scopes': list(SCOPES), 'state': 'BOUND'}

    def cancel(self, authorization_handle):
        if not self.flow or authorization_handle!=self.flow_handle:
            raise WCEError('X_AUTHORIZATION_SESSION_MISMATCH')
        self.flow.close()
        return {'state': 'CANCELLED'}

    def close(self):
        if self.flow:
            self.flow.close()

    def _connection(self, cid, value=None):
        c = (value if value is not None else self._load())['connections'].get(cid)
        if c is None:
            raise WCEError('X_CONNECTION_NOT_FOUND')
        if c['state'] != 'BOUND':
            raise WCEError('X_REAUTHORIZATION_REQUIRED')
        return c

    def _access(self, value, cid):
        c = self._connection(cid,value)
        stored = self.keychain.load(c['credential_scope'])
        if stored is None:
            raise WCEError('X_REAUTHORIZATION_REQUIRED')
        tokens = json.loads(stored.reveal_for_adapter())
        if c['expires_at'] <= self.clock() + 30:
            c['state'] = 'REFRESH_UNKNOWN'
            self._save(value)
            updated = self.api.refresh(value['client_id'], Secret(tokens['refresh_token']))
            secret = credential(updated, tokens['refresh_token'])
            self.keychain.put(c['credential_scope'], secret)
            c['expires_at'], c['state'] = self.clock() + updated['expires_in'], 'BOUND'
            self._save(value)
            tokens = json.loads(secret.reveal_for_adapter())
        return Secret(tokens['access_token'])

    def read(self, cid, kind, post_id=None, cursor=None):
        self._connection(cid)
        with locked(self.root / 'connection.lock'):
            self._connection(cid)
            value = self._load()
            token = self._access(value,cid)
            if kind == 'profile':
                result = self.api.profile(token)
                if result['id'] != value['connections'][cid]['profile']['id']:
                    raise WCEError('X_IDENTITY_CHANGED')
                value['connections'][cid]['profile'] = result
                self._save(value)
            elif kind == 'posts':
                result = self.api.posts(token, value['connections'][cid]['profile']['id'], cursor=cursor)
            else:
                result = self.api.post(token, identifier(post_id))
            return {'connection_id': cid, 'source': 'X_API', 'result': result}

    def _attempt_path(self, cid, kind, attempt_id):
        if type(attempt_id) is not str or re.fullmatch(r'[A-Za-z0-9_-]{1,128}', attempt_id) is None:
            raise WCEError('X_INVALID_ATTEMPT_ID')
        return self.root / (fingerprint([cid, kind, attempt_id]) + '.json')

    def search(self, cid, query, *, discovery_type, **options):
        require(discovery_type in DISCOVERY_TYPES, 'X_DISCOVERY_TYPE_INVALID')
        options = search_options(query, options, self.clock())
        self._connection(cid)
        with locked(self.root / 'connection.lock'):
            self._connection(cid)
            result = self.api.search(self._access(self._load(),cid), query, **options)
            require(type(result) is dict and not result.get('errors'), 'X_SEARCH_INCOMPLETE')
            rows, meta = result.get('data', []), result.get('meta')
            require(type(rows) is list and type(meta) is dict and type(meta.get('result_count')) is int
                    and meta['result_count'] == len(rows), 'X_SEARCH_INCOMPLETE')
            for row in rows:
                require(type(row) is dict, 'X_SEARCH_INCOMPLETE')
                post_data({'data': row}, identifier(row.get('id')))
            require(len({r['id'] for r in rows}) == len(rows), 'X_SEARCH_INCOMPLETE')
            cursor = meta.get('next_token')
            require(cursor is None or (type(cursor) is str and cursor and cursor not in (
                options.get('next_token'), options.get('pagination_token'))), 'X_SEARCH_CURSOR_INVALID')
            # No persistent high-water mark is advanced by a partial page.
            return {'connection_id': cid, 'source': 'X_API', 'discovery_type': discovery_type,
                    'request': {'query': query} | options, 'result': result,
                    'page_state': 'MORE' if cursor else 'COMPLETE', 'next_token': cursor,
                    'high_water_committed': False}

    def user(self, cid, username):
        self._connection(cid)
        with locked(self.root / 'connection.lock'):
            self._connection(cid)
            result = self.api.user(self._access(self._load(),cid), username)
            user = result.get('data', {})
            identifier(user.get('id'))
            require(type(user.get('username')) is str and user['username'].lower() == username.lower(),
                    'X_USER_MISMATCH')
            return {'connection_id': cid, 'source': 'X_API', 'result': result}

    def context(self, cid, post_id):
        post_id = identifier(post_id)
        self._connection(cid)
        with locked(self.root / 'connection.lock'):
            self._connection(cid)
            result = self.api.context(self._access(self._load(),cid), post_id)
            post = post_data(result, post_id)
            refs = references(post)
            included = result.get('includes', {}).get('posts', [])
            require(type(included) is list)
            available = {row.get('id') for row in included if type(row) is dict}
            return {'connection_id': cid, 'source': 'X_API', 'result': result,
                    'references': refs, 'missing_context_ids': [r['id'] for r in refs if r['id'] not in available],
                    'content_is_untrusted': True}

    def _receipt(self, cid, kind, attempt_id):
        path = self._attempt_path(cid, kind, attempt_id)
        value = read_metadata(path)
        if value is not None and (value.get('connection_id') != cid or value.get('kind') != kind or value.get('attempt_id') != attempt_id):
            raise WCEError('X_ATTEMPT_MISMATCH')
        return path, value

    def _write_once(self, cid, kind, attempt_id, content, send):
        self._connection(cid)
        with locked(self.root / 'connection.lock'):
            self._connection(cid)
            path, old = self._receipt(cid, kind, attempt_id)
            digest = fingerprint(content)
            if old is not None:
                if old['fingerprint'] != digest:
                    raise WCEError('X_ATTEMPT_CONFLICT')
                return old
            state = self._load()
            token = self._access(state,cid)
            receipt = {'connection_id': cid, 'kind': kind, 'attempt_id': attempt_id, 'fingerprint': digest,
                       'state': 'RESULT_UNKNOWN', 'created_at': self.clock(), 'input': content}
            atomic_write(path, receipt, maximum=None)
            return self._send_receipt(path, receipt, send, token)

    @staticmethod
    def _send_receipt(path, receipt, send, token):
        try:
            receipt['result'] = send(token)
            receipt['state'] = 'SUCCEEDED'
        except WCEError as error:
            receipt['error'] = error.code
            if re.fullmatch(r'X_HTTP_4[0-9]{2}', error.code) and error.code != 'X_HTTP_408':
                receipt['state'] = 'REJECTED'
        except Exception:
            receipt['error'] = 'X_RESPONSE_UNKNOWN'
        atomic_write(path, receipt, maximum=None)
        return receipt

    def reply(self, cid, attempt_id, parent_id, text):
        parent_id = identifier(parent_id)
        require(type(text) is str and bool(text.strip()), 'X_REPLY_TEXT_INVALID')
        content = {'parent_id': parent_id, 'text': text}
        self._connection(cid)
        with locked(self.root / 'connection.lock'):
            c = self._connection(cid)
            path, old = self._receipt(cid, 'reply', attempt_id)
            digest = fingerprint(content)
            if old is not None:
                require(old['fingerprint'] == digest, 'X_ATTEMPT_CONFLICT')
                if old['state'] != 'NOT_SUBMITTED':
                    return old
            # This index is independent of discovery category and attempt alias.
            # Persist it before POST; even a crash before the receipt cannot
            # make another category/key silently submit the same parent twice.
            intent_path = self.root / (fingerprint([cid, 'reply-parent', parent_id]) + '.json')
            intent = read_metadata(intent_path)
            if intent is not None:
                require(intent.get('connection_id') == cid and intent.get('parent_id') == parent_id,
                        'X_REPLY_INTENT_MISMATCH')
                if old is None or intent['attempt_id'] != attempt_id:
                    _, original = self._receipt(cid, 'reply', intent['attempt_id'])
                    return {'state': 'ALREADY_HANDLED', 'connection_id': cid, 'parent_id': parent_id,
                            'original_attempt_id': intent['attempt_id'],
                            'original': original or {'state': 'RESULT_UNKNOWN', 'error': 'X_REPLY_RECEIPT_MISSING'}}
            token = self._access(self._load(),cid)
            parent_result = self.api.context(token, parent_id)
            parent = post_data(parent_result, parent_id)
            refs = references(parent)
            require(parent['author_id'] != c['profile']['id'], 'X_REPLY_SELF_TARGET')
            mention_sources = [parent, parent.get('note_post', {})]
            summoned = any(type(source) is dict and any(type(row) is dict and row.get('id') == c['profile']['id']
                for row in source.get('entities', {}).get('mentions', [])) for source in mention_sources)
            evidence = {'type': 'mention', 'parent_id': parent_id} if summoned else None
            if not summoned:
                for ref in refs:
                    if ref['type'] == 'quoted':
                        quoted = post_data(self.api.context(token, ref['id']), ref['id'])
                        if quoted['author_id'] == c['profile']['id']:
                            evidence = {'type': 'quote', 'parent_id': parent_id, 'quoted_id': ref['id']}
                            break
            if evidence is None:
                return {'state': 'NOT_EXECUTED', 'reason': 'X_SELF_SERVE_REPLY_REQUIRES_SUMMON',
                        'connection_id': cid, 'parent_id': parent_id, 'attempt_id': attempt_id}
            identity = self.api.profile(token)
            require(identity['id'] == c['profile']['id'], 'X_IDENTITY_CHANGED')
            receipt = {'connection_id': cid, 'kind': 'reply', 'attempt_id': attempt_id,
                       'fingerprint': digest, 'state': 'NOT_SUBMITTED', 'created_at': self.clock(),
                       'input': content, 'summon_evidence': evidence}
            # A pre-POST crash must remain queryable through the original
            # attempt. NOT_SUBMITTED is persisted before claiming the parent;
            # POST is impossible until the subsequent UNKNOWN write succeeds.
            atomic_write(path, receipt, maximum=None)
            atomic_write(intent_path, {'connection_id': cid, 'parent_id': parent_id,
                                      'attempt_id': attempt_id}, maximum=None)
            receipt['state'] = 'RESULT_UNKNOWN'
            atomic_write(path, receipt, maximum=None)
            def send(access):
                data = self.api.reply(access, parent_id, text).get('data', {})
                return {'post_id': identifier(data.get('id')), 'parent_id': parent_id}
            return self._send_receipt(path, receipt, send, token)

    def reply_status(self, cid, attempt_id, *, readback=False):
        self._connection(cid)
        with locked(self.root / 'connection.lock'):
            c = self._connection(cid)
            path, receipt = self._receipt(cid, 'reply', attempt_id)
            if receipt is None:
                return {'state': 'NOT_FOUND', 'attempt_id': attempt_id, 'connection_id': cid}
            if receipt['state'] == 'NOT_SUBMITTED':
                return receipt | {'state': 'NOT_EXECUTED', 'reason': 'X_REPLY_NOT_SUBMITTED'}
            if not readback or receipt['state'] == 'REJECTED':
                return receipt
            token = self._access(self._load(),cid)
            if receipt['state'] == 'RESULT_UNKNOWN':
                start = datetime.fromtimestamp(receipt['created_at'] - 10, timezone.utc).isoformat(timespec='seconds').replace('+00:00', 'Z')
                cursor, seen, matches = None, set(), {}
                while True:
                    page = self.api.reply_posts(token, c['profile']['id'], cursor=cursor, start_time=start)
                    require(type(page) is dict and not page.get('errors') and type(page.get('data', [])) is list,
                            'X_TIMELINE_INCOMPLETE')
                    for row in page.get('data', []):
                        require(type(row) is dict, 'X_TIMELINE_INCOMPLETE')
                        if reply_matches(row, c['profile']['id'], receipt['input'], self._text):
                            matches[identifier(row.get('id'))] = row
                    cursor = page.get('meta', {}).get('next_token')
                    if not cursor: break
                    require(type(cursor) is str and cursor not in seen, 'X_TIMELINE_INCOMPLETE')
                    seen.add(cursor)
                if len(matches) != 1:
                    return receipt | {'readback_state': 'NO_UNIQUE_MATCH'}
                receipt['result'] = {'post_id': next(iter(matches)), 'parent_id': receipt['input']['parent_id']}
            pid = receipt['result']['post_id']
            result = self.api.context(token, pid)
            post = post_data(result, pid)
            if not reply_matches(post, c['profile']['id'], receipt['input'], self._text):
                return receipt | {'readback_state': 'MISMATCH', 'actual': result}
            receipt.update(state='SUCCEEDED', readback_state='MATCHED', actual=result,
                           url='https://x.com/i/web/status/' + pid,
                           text_comparison='EXACT_RAW_OR_EVIDENCED_X_URL_AND_HTML_REPRESENTATION')
            atomic_write(path, receipt, maximum=None)
            return receipt

    def upload(self, cid, attempt_id, path):
        from .x_media import upload
        return upload(self,cid,attempt_id,path)

    def create(self, cid, attempt_id, text, upload_attempt):
        self._connection(cid)
        _, media = self._receipt(cid, 'upload', upload_attempt)
        if not media or media['state'] != 'SUCCEEDED':
            raise WCEError('X_MEDIA_NOT_AVAILABLE')
        content = {'text': text, 'media_id': media['result']['media_id'], 'media_key': media['result']['media_key']}
        _, original = self._receipt(cid, 'post', attempt_id)
        if original:
            if original['fingerprint'] != fingerprint(content):
                raise WCEError('X_ATTEMPT_CONFLICT')
            return original
        if media['result']['expires_at'] <= self.clock():
            raise WCEError('X_MEDIA_NOT_AVAILABLE')
        def send(token):
            data = self.api.create(token, text, [content['media_id']])['data']
            return {'post_id': identifier(data.get('id'))}
        return self._write_once(cid, 'post', attempt_id, content, send)

    @staticmethod
    def _text(post):
        """Reconstruct evidenced X URL representations, never guess shortened URLs."""
        text = post.get('text')
        if type(text) is not str:
            return None
        for entity in post.get('entities', {}).get('urls', []):
            url, expanded = entity.get('url'), entity.get('expanded_url')
            if (type(url) is str and re.fullmatch(r'https://t\.co/[A-Za-z0-9]+', url)
                    and type(expanded) is str and re.fullmatch(
                        r'https://(?:x\.com|twitter\.com)/[A-Za-z0-9_]+/status/' + re.escape(str(post.get('id'))) + r'/(?:photo|video)/1', expanded)
                    and text.endswith(' ' + url)):
                text = text[:-len(url)-1]
        for entity in post.get('entities', {}).get('urls', []):
            url, expanded = entity.get('url'), entity.get('expanded_url')
            if (type(url) is str and re.fullmatch(r'https://t\.co/[A-Za-z0-9]+', url)
                    and type(expanded) is str and re.fullmatch(r'https?://[^\s]+', expanded)):
                text = text.replace(url, expanded)
        return text

    @staticmethod
    def _matches(post, c, receipt):
        content = receipt['input']
        representations = [post.get('text'), XPlatform._text(post)]
        representations += [html.unescape(text) for text in representations if type(text) is str]
        return (post.get('author_id') == c['profile']['id'] and content['text'] in representations and
                post.get('attachments', {}).get('media_keys') == [content['media_key']])

    def status(self, cid, kind, attempt_id, *, readback=False, poll_media=False):
        self._connection(cid)
        with locked(self.root / 'connection.lock'):
            c = self._connection(cid)
            path, receipt = self._receipt(cid, kind, attempt_id)
            if receipt is None:
                return {'state': 'NOT_FOUND', 'attempt_id': attempt_id, 'connection_id': cid}
            if kind=='upload' and poll_media and receipt.get('media_protocol')=='X_V2_CHUNKED':
                from .x_media import poll
                return poll(self,cid,path,receipt)
            if kind != 'post' or not readback or receipt['state'] == 'REJECTED':
                return receipt
            token = self._access(self._load(),cid)
            if receipt['state'] == 'RESULT_UNKNOWN':
                start = datetime.fromtimestamp(receipt['created_at'] - 10, timezone.utc).isoformat(timespec='seconds').replace('+00:00', 'Z')
                cursor, seen, matches = None, set(), []
                while True:
                    page = self.api.posts(token, c['profile']['id'], cursor=cursor, start_time=start)
                    if type(page.get('data', [])) is not list:
                        raise WCEError('X_TIMELINE_INCOMPLETE')
                    matches.extend(row for row in page.get('data', []) if self._matches(row, c, receipt))
                    cursor = page.get('meta', {}).get('next_token')
                    if not cursor:
                        break
                    if type(cursor) is not str or cursor in seen:
                        raise WCEError('X_TIMELINE_INCOMPLETE')
                    seen.add(cursor)
                if len(matches) != 1:
                    return receipt | {'readback_state': 'NO_UNIQUE_MATCH'}
                receipt['result'] = {'post_id': identifier(matches[0].get('id'))}
            result = self.api.post(token, receipt['result']['post_id'])
            post = result.get('data', {})
            media_keys = [row.get('media_key') for row in result.get('includes', {}).get('media', [])]
            if (post.get('id') != receipt['result']['post_id'] or not self._matches(post, c, receipt)
                    or receipt['input']['media_key'] not in media_keys):
                return receipt | {'readback_state': 'MISMATCH', 'actual': result}
            receipt['state'], receipt['readback_state'] = 'SUCCEEDED', 'MATCHED'
            receipt['text_comparison'] = 'EXACT_RAW_OR_EVIDENCED_X_URL_AND_HTML_REPRESENTATION'
            receipt['actual'] = result
            receipt['url'] = 'https://x.com/' + c['profile']['username'] + '/status/' + identifier(post['id'])
            atomic_write(path, receipt, maximum=None)
            return receipt
