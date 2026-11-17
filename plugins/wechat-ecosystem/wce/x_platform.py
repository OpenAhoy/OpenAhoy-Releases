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
from .x_api import CALLBACK, SCOPES, XHTTP, XResponseUnknown, identifier
from .x_application import CLIENT_ID
from .x_oauth import AuthorizationAccountMismatch, OAuthFlow
from .x_discovery import DISCOVERY_TYPES, post_data, references, reply_matches, require, search_options


def fingerprint(value):
    return sha256(json.dumps(value, sort_keys=True, separators=(',', ':'), ensure_ascii=False).encode()).hexdigest()


def valid_client_id(value):
    return type(value) is str and re.fullmatch(r'[A-Za-z0-9._~+/=-]{1,4096}', value) is not None


def valid_application_name(value):
    return type(value) is str and 1 <= len(value) <= 80 and value.isprintable() and value == value.strip()


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
        fields = {'schema','client_id','connections'}
        if value.get('schema') == 3:
            fields.add('retired')
        if set(value) != fields or value['schema'] not in {2, 3} or type(value['connections']) is not dict:
            raise WCEError('X_CONNECTION_INVALID')
        if value['client_id'] != '' and not valid_client_id(value['client_id']):
            raise WCEError('X_CLIENT_ID_INVALID')
        def check(cid, c):
            base = {'connection_id','profile','scope','expires_at','state','credential_scope'}
            if type(c) is not dict or set(c) - {'removal_marker','binding_revision'} not in (base, base | {'client_id', 'application_name'}) or type(c['profile']) is not dict:
                raise WCEError('X_CONNECTION_INVALID')
            if 'binding_revision' in c and (type(c['binding_revision']) is not str
                                            or re.fullmatch('[a-f0-9]{64}',c['binding_revision']) is None):
                raise WCEError('X_CONNECTION_INVALID')
            if 'removal_marker' in c and (type(c['removal_marker']) is not str
                                          or re.fullmatch('[a-f0-9]{32}', c['removal_marker']) is None):
                raise WCEError('X_CONNECTION_INVALID')
            if 'client_id' in c and (value['schema'] != 3 or not valid_client_id(c['client_id'])
                                     or c['client_id'] == CLIENT_ID or not valid_application_name(c['application_name'])):
                raise WCEError('X_CONNECTION_INVALID')
            user=identifier(c['profile'].get('id'))
            scope=fingerprint(['x',c.get('client_id', value['client_id']),user])
            if cid!='x-'+user or c['connection_id']!=cid or c['credential_scope']!=scope or c['scope']!=list(SCOPES):
                raise WCEError('X_CONNECTION_INVALID')
        for cid, c in value['connections'].items():
            check(cid, c)
        retired = value.get('retired', {})
        if type(retired) is not dict or not retired.keys() <= value['connections'].keys():
            raise WCEError('X_CONNECTION_INVALID')
        for cid, grants in retired.items():
            if type(grants) is not dict:
                raise WCEError('X_CONNECTION_INVALID')
            for scope, grant in grants.items():
                check(cid, grant)
                if scope != grant['credential_scope'] or scope == value['connections'][cid]['credential_scope']:
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
        if type(old) is dict and old.get('schema') in {1, 2} and value['schema'] == 3:
            backup = self.root / 'connection.before-applications.json'
            if not os.path.lexists(backup):
                atomic_write(backup, old, maximum=None)
        atomic_write(path,value,maximum=None)

    def overview(self):
        try:
            rows=[]
            for c in self._load()['connections'].values():
                profile=c['profile']
                rows.append({'platform_id':'x','connection_id':c['connection_id'],'account_id':profile['id'],
                    'state':{'BOUND':'BOUND_IDLE','DISCONNECTED':'DISCONNECTED'}.get(c['state'],'ACTION_REQUIRED'),
                    'presentation':{'display_name':profile['name'],'avatar':None},
                    'binding_revision':self._binding_revision(c),'username':profile['username'],'profile_image_url':profile.get('profile_image_url'),
                    'own_application': 'CONNECTED' if 'client_id' in c and c['state']=='BOUND'
                    else 'NEEDS_AUTHORIZATION' if 'client_id' in c else 'UNCONFIGURED'})
            return rows
        except WCEError:
            return [{'platform_id':'x','connection_id':'x-unavailable','state':'ACTION_REQUIRED',
                     'presentation':{'display_name':'X 连接需要处理','avatar':None}}]

    @staticmethod
    def _binding_revision(connection):
        return connection.get('binding_revision', fingerprint(['binding',connection['credential_scope']]))

    def disconnect(self, cid, account_id, binding_revision):
        with locked(self.root / 'connection.lock', nonblocking=True):
            value = self._load()
            connection = value['connections'].get(cid)
            if connection is None or connection['profile']['id'] != account_id:
                raise WCEError('X_CONNECTION_NOT_FOUND')
            if self._binding_revision(connection) != binding_revision:
                raise WCEError('X_CONNECTION_CHANGED')
            if connection['state'] != 'DISCONNECTED':
                connection['state'] = 'DISCONNECTED'
                connection['removal_marker'] = secrets.token_hex(16)
                for grant in value.get('retired', {}).get(cid, {}).values():
                    grant['state'] = 'DISCONNECTED'
                self._save(value)
        return {'connection_id': cid, 'state': 'DISCONNECTED', 'remote_revocation': 'NOT_REQUESTED'}

    def automation_binding(self, cid):
        return self._connection(cid).get('removal_marker')

    def settings(self,authorization_handle=None):
        value=self._load()
        authorization=self.flow.snapshot() if self.flow and authorization_handle==self.flow_handle else {'state':'NOT_STARTED','result':None}
        connections = []
        for c in value['connections'].values():
            client = c.get('client_id', value['client_id'])
            connections.append({'connection_id': c['connection_id'], 'profile': deepcopy(c['profile']),
                'state': c['state'], 'application': {'mode': 'OWN_APP' if 'client_id' in c else 'LEGACY_APP',
                    'name': c.get('application_name'), 'client_id_suffix': client[-6:],
                    'selection': c['credential_scope']}})
        return {'callback_uri':CALLBACK,'required_scopes':list(SCOPES),
                'connections':connections,'authorization':authorization}

    def configure(self, client_id):
        if not valid_client_id(client_id):
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

    def _saved_application(self, cid):
        if cid is not None and not re.fullmatch(r'x-[0-9]{1,19}', cid):
            raise WCEError('X_CONNECTION_NOT_FOUND')
        if cid is not None and cid not in self._load()['connections']:
            raise WCEError('X_CONNECTION_NOT_FOUND')
        path = self.root / ('application-draft-' + (cid or 'new') + '.json')
        draft = read_metadata(path) if self.root.exists() else None
        if draft is not None and (
            type(draft) is not dict or set(draft) != {'application_name', 'client_id', 'expected_user_id'}
            or not valid_application_name(draft['application_name']) or not valid_client_id(draft['client_id'])
            or draft['client_id'] == CLIENT_ID
            or (draft['expected_user_id'] is not None
                and (type(draft['expected_user_id']) is not str
                     or not re.fullmatch(r'[0-9]{1,19}', draft['expected_user_id'])
                     or (cid is not None and cid != 'x-' + draft['expected_user_id'])))
        ):
            raise WCEError('X_APPLICATION_DRAFT_INVALID')
        return path, draft

    def application_draft(self, cid=None):
        _, draft = self._saved_application(cid)
        return {'draft': draft, 'revision': fingerprint(draft) if draft else None}

    def save_application_draft(self, application_name, client_id, cid=None, expected_user_id=None):
        if not valid_application_name(application_name):
            raise WCEError('X_APPLICATION_NAME_INVALID')
        if not valid_client_id(client_id) or client_id == CLIENT_ID:
            raise WCEError('X_OWN_CLIENT_ID_REQUIRED')
        if expected_user_id is not None:
            identifier(expected_user_id)
            if cid is not None and cid != 'x-' + expected_user_id:
                raise WCEError('X_AUTHORIZATION_ACCOUNT_MISMATCH')
        self._prepare()
        with locked(self.root / 'connection.lock'):
            path, _ = self._saved_application(cid)
            draft = {'application_name': application_name, 'client_id': client_id, 'expected_user_id': expected_user_id}
            atomic_write(path, draft)
            result = self.application_draft(cid)
            if result['draft'] != draft:
                raise WCEError('X_APPLICATION_SAVE_UNCONFIRMED')
            return result

    def authorize_saved_application(self, revision, cid=None):
        saved = self.application_draft(cid)
        if not saved['draft'] or saved['revision'] != revision:
            raise WCEError('X_APPLICATION_DRAFT_CHANGED')
        return self.begin(cid, **saved['draft'])

    def begin(self, expected_connection_id=None, *, client_id=None, application_name=None, expected_user_id=None):
        value = self._load()
        own_app = client_id is not None
        prior = value['connections'].get(expected_connection_id)
        if own_app and (not valid_client_id(client_id) or client_id == CLIENT_ID):
            raise WCEError('X_OWN_CLIENT_ID_REQUIRED')
        if own_app and not valid_application_name(application_name):
            raise WCEError('X_APPLICATION_NAME_INVALID')
        if not own_app and expected_connection_id is not None and prior:
            client_id = prior.get('client_id', value['client_id'])
            application_name = prior.get('application_name')
        elif not own_app:
            client_id = value['client_id']
        if not client_id:
            raise WCEError('X_APPLICATION_REQUIRED')
        if expected_connection_id is not None and (prior is None or prior['state']=='DISCONNECTED'):
            raise WCEError('X_CONNECTION_NOT_FOUND')
        if expected_user_id is not None:
            identifier(expected_user_id)
            if expected_connection_id is not None and expected_connection_id != 'x-' + expected_user_id:
                raise WCEError('X_AUTHORIZATION_ACCOUNT_MISMATCH')
        # All host processes share this OS lock for the fixed callback listener.
        if self.flow:
            if self.flow.snapshot()['state'] in {'AWAITING_AUTHORIZATION', 'EXCHANGING'}:
                raise WCEError('X_AUTHORIZATION_IN_PROGRESS')
            self.flow.close()
        removal_markers = {cid: c['removal_marker'] for cid,c in value['connections'].items()
                           if 'removal_marker' in c}
        def finish(client, tokens, guard=nullcontext):
            return self._finish(client, tokens, guard, expected_connection_id=expected_connection_id,
                                application_name=application_name, expected_scope=prior['credential_scope'] if prior else None,
                                expected_user_id=expected_user_id, removal_markers=removal_markers)
        self.flow = self.flow_factory(client_id, self.api, finish)
        self.flow_handle='x-auth-'+secrets.token_hex(24)
        result = {'state':'AWAITING_AUTHORIZATION', 'authorization_handle':self.flow_handle,
                  'authorization_url':self.flow.authorization_url()}
        if prior:
            result['expected_username'] = prior['profile'].get('username')
        return result

    def billing(self, cid, expected_application):
        self._connection(cid)
        with locked(self.root / 'connection.lock'):
            value = self._load()
            c = self._connection(cid, value)
            if 'client_id' not in c:
                return {'state': 'LEGACY_APP', 'connection_id': cid}
            if c['credential_scope'] != expected_application:
                raise WCEError('X_APPLICATION_CHANGED')
            credits = self.api.credits(self._access(value, cid))
            return {'state': 'AVAILABLE', 'connection_id': cid, 'application': expected_application,
                    'currency': 'USD', 'source': 'X_API', 'checked_at': self.clock(), **credits}

    def _finish(self, client_id, token_value, guard=nullcontext, *, expected_connection_id=None,
                application_name=None, expected_scope=None, expected_user_id=None, removal_markers=None):
        secret = credential(token_value)
        tokens = json.loads(secret.reveal_for_adapter())
        profile = self.api.profile(Secret(tokens['access_token']))
        cid = 'x-' + identifier(profile['id'])
        if ((expected_user_id is not None and profile['id'] != expected_user_id)
                or (expected_connection_id is not None and cid != expected_connection_id)):
            original = self._load()['connections'].get(expected_connection_id, {})
            raise AuthorizationAccountMismatch(original.get('profile', {}).get('username'), profile.get('username'))
        self._prepare()
        with locked(self.root / 'connection.lock'), guard():
            value = self._load()
            if application_name is None and value['client_id'] != client_id:
                raise WCEError('X_APPLICATION_CHANGED')
            if expected_connection_id is not None and expected_connection_id not in value['connections']:
                raise WCEError('X_CONNECTION_CHANGED')
            previous = value['connections'].get(cid)
            if removal_markers is not None and (previous or {}).get('removal_marker') != removal_markers.get(cid):
                raise WCEError('X_CONNECTION_CHANGED')
            if expected_scope is not None and previous['credential_scope'] != expected_scope:
                raise WCEError('X_APPLICATION_CHANGED')
            if previous and previous['state'] != 'DISCONNECTED' and expected_connection_id is None and (application_name is not None or 'client_id' in previous):
                raise WCEError('X_SELECT_EXISTING_ACCOUNT')
            if application_name is not None and (not valid_client_id(client_id) or client_id == CLIENT_ID
                                                  or not valid_application_name(application_name)):
                raise WCEError('X_OWN_CLIENT_ID_REQUIRED')
            scope = fingerprint(['x', client_id, profile['id']])
            c = {'connection_id': 'x-' + profile['id'], 'profile': profile, 'scope': list(SCOPES),
                 'expires_at': self.clock() + token_value['expires_in'],
                 'state': 'BOUND', 'credential_scope': scope, 'binding_revision': secrets.token_hex(32)}
            if previous and 'removal_marker' in previous:
                c['removal_marker'] = previous['removal_marker']
            if application_name is not None:
                value['schema'] = 3
                retired = value.setdefault('retired', {}).setdefault(cid, {})
                retired.pop(scope, None)
                if previous and previous['credential_scope'] != scope:
                    retired[previous['credential_scope']] = previous
                c.update(client_id=client_id, application_name=application_name)
            # A different scope can be made durable before changing its live pointer.
            # Keep the historical marker for callers of the original shared-app path.
            elif previous is None or previous['credential_scope'] == scope:
                value['connections'][cid] = c | {'state': 'CREDENTIAL_COMMIT_PENDING'}
                self._save(value)
            self.keychain.put(scope, secret)
            value['connections'][cid] = c
            self._save(value)
        return {'connection_id': c['connection_id'], 'profile': profile, 'scopes': list(SCOPES), 'state': 'BOUND'}

    def cancel(self, authorization_handle):
        if not self.flow or authorization_handle!=self.flow_handle:
            raise WCEError('X_AUTHORIZATION_SESSION_MISMATCH')
        state = self.flow.close()
        return {'state': state or 'CANCELLED'}

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

    def _receipt_scope(self, value, cid, receipt):
        # All receipts without an application marker predate per-account grants.
        return receipt.get('application_scope', fingerprint(['x', value['client_id'], cid[2:]]))

    def _access(self, value, cid, receipt=None):
        c = value['connections'].get(cid)
        if not c:
            raise WCEError('X_CONNECTION_NOT_FOUND')
        if c['state'] == 'DISCONNECTED':
            raise WCEError('X_REAUTHORIZATION_REQUIRED')
        if receipt is not None:
            scope = self._receipt_scope(value, cid, receipt)
            if scope != c['credential_scope']:
                c = value.get('retired', {}).get(cid, {}).get(scope)
                if c is None:
                    raise WCEError('X_ORIGINAL_APPLICATION_UNAVAILABLE')
        if c['state'] != 'BOUND':
            raise WCEError('X_REAUTHORIZATION_REQUIRED')
        stored = self.keychain.load(c['credential_scope'])
        if stored is None:
            raise WCEError('X_REAUTHORIZATION_REQUIRED')
        tokens = json.loads(stored.reveal_for_adapter())
        if c['expires_at'] <= self.clock() + 30:
            c['state'] = 'REFRESH_UNKNOWN'
            self._save(value)
            try:
                updated = self.api.refresh(c.get('client_id', value['client_id']), Secret(tokens['refresh_token']))
            except WCEError as error:
                if error.code == 'X_HTTP_429':
                    # The explicit rejection did not rotate the refresh token.
                    c['state'] = 'BOUND'
                    self._save(value)
                raise
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
                       'state': 'RESULT_UNKNOWN', 'created_at': self.clock(), 'input': content,
                       'application_scope': state['connections'][cid]['credential_scope']}
            atomic_write(path, receipt, maximum=None)
            return self._send_receipt(path, receipt, send, token)

    @staticmethod
    def _send_receipt(path, receipt, send, token):
        try:
            receipt['result'] = send(token)
            receipt['state'] = 'SUCCEEDED'
        except WCEError as error:
            receipt['error'] = error.code
            if isinstance(error, XResponseUnknown):
                receipt['error_kind'] = error.kind
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
            value = self._load()
            if old and self._receipt_scope(value, cid, old) != c['credential_scope']:
                raise WCEError('X_ORIGINAL_APPLICATION_CHANGED')
            token = self._access(value, cid)
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
                       'input': content, 'summon_evidence': evidence, 'application_scope': c['credential_scope']}
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
        if cid not in self._load()['connections']:
            raise WCEError('X_CONNECTION_NOT_FOUND')
        with locked(self.root / 'connection.lock'):
            value = self._load()
            c = value['connections'][cid]
            path, receipt = self._receipt(cid, 'reply', attempt_id)
            if receipt is None:
                return {'state': 'NOT_FOUND', 'attempt_id': attempt_id, 'connection_id': cid}
            if receipt['state'] == 'NOT_SUBMITTED':
                return receipt | {'state': 'NOT_EXECUTED', 'reason': 'X_REPLY_NOT_SUBMITTED'}
            if not readback or receipt['state'] == 'REJECTED':
                return receipt
            token = self._access(value, cid, receipt)
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

    def create(self, cid, attempt_id, text, upload_attempt=None, *, upload_attempt_ids=None, made_with_ai=None):
        require(made_with_ai is None or type(made_with_ai) is bool, 'INVALID_TOOL_ARGUMENTS')
        if upload_attempt is None and upload_attempt_ids is None:
            require(made_with_ai is None and type(text) is str and bool(text.strip()), 'INVALID_TOOL_ARGUMENTS')

            def send_text(access):
                data = self.api.create(access, text, [])['data']
                return {'post_id': identifier(data.get('id'))}

            return self._write_once(cid, 'post', attempt_id, {'text': text}, send_text)
        require((upload_attempt is None) != (upload_attempt_ids is None), 'INVALID_TOOL_ARGUMENTS')
        attempts = [upload_attempt] if upload_attempt_ids is None else upload_attempt_ids
        require(type(attempts) is list and 1 <= len(attempts) <= 4
                and all(type(item) is str for item in attempts)
                and len(set(attempts)) == len(attempts), 'INVALID_TOOL_ARGUMENTS')
        self._connection(cid)
        with locked(self.root / 'connection.lock'):
            value = self._load()
            c = self._connection(cid, value)
            uploads = [self._receipt(cid, 'upload', item)[1] for item in attempts]
            require(all(row and row['state'] == 'SUCCEEDED' for row in uploads), 'X_MEDIA_NOT_AVAILABLE')
            require(len(uploads) == 1 or all(row.get('media_category', 'tweet_image') == 'tweet_image'
                                             for row in uploads), 'X_MEDIA_COMBINATION_INVALID')
            media_ids = [row['result']['media_id'] for row in uploads]
            media_keys = [row['result']['media_key'] for row in uploads]
            require(len(set(media_ids)) == len(uploads) and len(set(media_keys)) == len(uploads),
                    'X_MEDIA_COMBINATION_INVALID')
            if len(uploads) == 1:
                # Preserve the original persisted input and its fingerprint.
                content = {'text': text, 'media_id': media_ids[0], 'media_key': media_keys[0]}
            else:
                content = {'text': text, 'media_ids': media_ids, 'media_keys': media_keys}
            if made_with_ai is not None:
                content['made_with_ai'] = made_with_ai
            path, original = self._receipt(cid, 'post', attempt_id)
            digest = fingerprint(content)
            if original:
                require(original['fingerprint'] == digest, 'X_ATTEMPT_CONFLICT')
                return original
            require(all(self._receipt_scope(value, cid, row) == c['credential_scope'] for row in uploads),
                    'X_MEDIA_APPLICATION_MISMATCH')
            require(all(row['result']['expires_at'] > self.clock() for row in uploads),
                    'X_MEDIA_NOT_AVAILABLE')
            token = self._access(value, cid)
            receipt = {'connection_id': cid, 'kind': 'post', 'attempt_id': attempt_id,
                       'fingerprint': digest, 'state': 'RESULT_UNKNOWN', 'created_at': self.clock(),
                       'input': content, 'application_scope': c['credential_scope']}
            atomic_write(path, receipt, maximum=None)

            def send(access):
                options = {} if made_with_ai is None else {'made_with_ai': made_with_ai}
                data = self.api.create(access, text, media_ids, **options)['data']
                return {'post_id': identifier(data.get('id'))}

            return self._send_receipt(path, receipt, send, token)

    @staticmethod
    def _text(post):
        """Reconstruct evidenced X URL representations, never guess shortened URLs."""
        text = post.get('text')
        if type(text) is not str:
            return None
        entities = post.get('entities', {})
        urls = entities.get('urls', []) if type(entities) is dict else []
        if type(urls) is not list or any(type(entity) is not dict for entity in urls):
            return None
        for entity in urls:
            url, expanded = entity.get('url'), entity.get('expanded_url')
            if (type(url) is str and re.fullmatch(r'https://t\.co/[A-Za-z0-9]+', url)
                    and type(expanded) is str and re.fullmatch(
                        r'https://(?:x\.com|twitter\.com)/[A-Za-z0-9_]+/status/' + re.escape(str(post.get('id'))) + r'/(?:photo|video)/1', expanded)
                    and text.endswith(' ' + url)):
                text = text[:-len(url)-1]
        for entity in urls:
            url, expanded = entity.get('url'), entity.get('expanded_url')
            if (type(url) is str and re.fullmatch(r'https://t\.co/[A-Za-z0-9]+', url)
                    and type(expanded) is str and re.fullmatch(r'https?://[^\s]+', expanded)):
                text = text.replace(url, expanded)
        return text

    @staticmethod
    def _plain_text_with_expanded_urls(post):
        text = post.get('text')
        entities = post.get('entities', {})
        urls = entities.get('urls', []) if type(entities) is dict else None
        if type(text) is not str or type(urls) is not list:
            return None
        replacements = []
        for entity in urls:
            if type(entity) is not dict:
                return None
            url, expanded = entity.get('url'), entity.get('expanded_url')
            start, end = entity.get('start'), entity.get('end')
            if (type(start) is not int or type(end) is not int or not 0 <= start < end <= len(text)
                    or type(url) is not str or not re.fullmatch(r'https://t\.co/[A-Za-z0-9]+', url)
                    or text[start:end] != url or type(expanded) is not str
                    or not re.fullmatch(r'https?://[^\s]+', expanded)):
                return None
            replacements.append((start, end, expanded))
        boundary = len(text)
        for start, end, expanded in sorted(replacements, reverse=True):
            if end > boundary:
                return None
            text = text[:start] + expanded + text[end:]
            boundary = start
        return text

    @staticmethod
    def _media_keys(receipt):
        content = receipt['input']
        if set(content) == {'text'}:
            return []
        return content['media_keys'] if 'media_keys' in content else [content['media_key']]

    @staticmethod
    def _matches(post, c, receipt):
        if type(post) is not dict or post.get('author_id') != c['profile']['id']:
            return False
        content = receipt['input']
        keys = XPlatform._media_keys(receipt)
        attachments = post.get('attachments', {})
        if type(attachments) is not dict:
            return False
        if keys:
            if attachments.get('media_keys') != keys:
                return False
        elif (set(attachments) - {'media_keys'} or attachments.get('media_keys', []) != []
                or post.get('referenced_posts', []) != []):
            return False
        normalized = XPlatform._text(post) if keys else XPlatform._plain_text_with_expanded_urls(post)
        representations = [post.get('text'), normalized]
        if keys:
            representations += [html.unescape(text) for text in representations if type(text) is str]
        return content['text'] in representations

    def status(self, cid, kind, attempt_id, *, readback=False, poll_media=False):
        if cid not in self._load()['connections']:
            raise WCEError('X_CONNECTION_NOT_FOUND')
        with locked(self.root / 'connection.lock'):
            value = self._load()
            c = value['connections'][cid]
            path, receipt = self._receipt(cid, kind, attempt_id)
            if receipt is None:
                return {'state': 'NOT_FOUND', 'attempt_id': attempt_id, 'connection_id': cid}
            if kind=='upload' and poll_media and receipt.get('media_protocol')=='X_V2_CHUNKED':
                from .x_media import poll
                return poll(self,cid,path,receipt)
            if kind != 'post' or not readback or receipt['state'] == 'REJECTED':
                return receipt
            text_only = not self._media_keys(receipt)
            if receipt['state'] == 'RESULT_UNKNOWN' and text_only:
                # An identical timeline post can belong to another client or attempt.
                return receipt | {'readback_state': 'NO_UNIQUE_MATCH'}
            token = self._access(value, cid, receipt)
            if receipt['state'] == 'RESULT_UNKNOWN':
                start = datetime.fromtimestamp(receipt['created_at'] - 10, timezone.utc).isoformat(timespec='seconds').replace('+00:00', 'Z')
                cursor, seen, matches = None, set(), []
                while True:
                    page = self.api.posts(token, c['profile']['id'], cursor=cursor, start_time=start)
                    if (type(page) is not dict or page.get('errors') or type(page.get('data', [])) is not list
                            or any(type(row) is not dict for row in page.get('data', []))):
                        raise WCEError('X_TIMELINE_INCOMPLETE')
                    matches.extend(identifier(row.get('id')) for row in page.get('data', [])
                                   if self._matches(row, c, receipt))
                    cursor = page.get('meta', {}).get('next_token')
                    if not cursor:
                        break
                    if type(cursor) is not str or cursor in seen:
                        raise WCEError('X_TIMELINE_INCOMPLETE')
                    seen.add(cursor)
                if len(matches) != 1:
                    return receipt | {'readback_state': 'NO_UNIQUE_MATCH'}
                receipt['result'] = {'post_id': matches[0]}
            result = self.api.post(token, receipt['result']['post_id'])
            post = result.get('data') if type(result) is dict else None
            includes = result.get('includes') if type(result) is dict else None
            media = includes.get('media') if type(includes) is dict else None
            media_keys = [row.get('media_key') for row in media if type(row) is dict] if type(media) is list else []
            if (type(result) is not dict or result.get('errors') or not self._matches(post, c, receipt)
                    or post.get('id') != receipt['result']['post_id']
                    or (text_only and ((includes is not None and type(includes) is not dict)
                                       or (type(includes) is dict and 'media' in includes and media != [])))
                    or any(media_keys.count(key) != 1 for key in self._media_keys(receipt))):
                return receipt | {'readback_state': 'MISMATCH', 'actual': result}
            receipt['state'], receipt['readback_state'] = 'SUCCEEDED', 'MATCHED'
            receipt['text_comparison'] = ('EXACT_RAW_OR_EVIDENCED_X_URL_REPRESENTATION' if text_only else
                                          'EXACT_RAW_OR_EVIDENCED_X_URL_AND_HTML_REPRESENTATION')
            receipt['actual'] = result
            receipt['url'] = 'https://x.com/' + c['profile']['username'] + '/status/' + identifier(post['id'])
            atomic_write(path, receipt, maximum=None)
            return receipt
