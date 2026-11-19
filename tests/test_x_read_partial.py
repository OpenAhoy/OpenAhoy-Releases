"""Exercise the real X transport and MCP routes with synthetic response bytes."""
from io import BytesIO
import json
from pathlib import Path
import sys
from tempfile import TemporaryDirectory
import unittest
from urllib.error import HTTPError
from urllib.parse import parse_qs, urlsplit

ROOT = Path(__file__).resolve().parents[1]
sys.path.append(str(ROOT / 'plugins/wechat-ecosystem'))

from wce.contracts import WCEError
from wce.mcp_stdio import StdioServer
from wce.own_connection_policy import atomic_write
from wce.support_protocol import SupportRouter
from wce.x_api import XHTTP
from wce.x_platform import XPlatform
from wce.x_protocol import XPlatformRouter

CID = 'x-123'
POST = {'id': '4501', 'author_id': '123', 'text': 'Original text'}
REPLY = {'id': '4502', 'author_id': '123', 'text': 'Reply',
         'referenced_posts': [{'type': 'replied_to', 'id': '4400'}]}
MEDIA_KEY = '3_777'
PHOTO = {'media_key': MEDIA_KEY, 'type': 'photo', 'url': 'https://pbs.twimg.com/media/fixture.jpg'}
PRIVATE = 'SYNTHETIC_UPSTREAM_SECRET'


def problem(category, **extra):
    return {'type': f'https://api.x.com/2/problems/{category}',
            'title': PRIVATE, 'detail': PRIVATE, 'resource_id': PRIVATE} | extra


class Transport:
    def __init__(self):
        self.pending = []
        self.requests = []

    def open(self, request, timeout):
        parsed = urlsplit(request.full_url)
        if request.get_method() != 'GET' or parsed.netloc != 'api.x.com':
            raise AssertionError('The fixture must not issue a write or contact another origin')
        self.requests.append((parsed.path, parse_qs(parsed.query)))
        status, response = self.pending.pop(0)
        body = BytesIO(json.dumps(response).encode())
        if status != 200:
            raise HTTPError(request.full_url, status, PRIVATE, {}, body)
        return body


class FixtureKeychain:
    def __init__(self):
        self.values = {}

    def put(self, scope, value):
        self.values[scope] = value

    def load(self, scope):
        return self.values.get(scope)


class FixtureInner:
    def list_tools(self):
        return []

    def evidence(self):
        return {'runtime': 'synthetic-read-fixture'}


class ReadTests(unittest.TestCase):
    def setUp(self):
        tmp = TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.api = XHTTP()
        self.transport = Transport()
        self.api.opener = self.transport
        self.platform = XPlatform(root=Path(tmp.name) / 'x', api=self.api, keychain=FixtureKeychain(),
                                  clock=lambda: 1794955000)
        self.transport.pending.append((200, {'data': {'id': '123', 'username': 'fixture', 'name': 'Fixture'}}))
        self.platform.configure('fixture-client')
        self.platform._finish('fixture-client', {'access_token': 'synthetic-access',
            'refresh_token': 'synthetic-refresh', 'scope': 'tweet.read users.read tweet.write media.write offline.access',
            'expires_in': 7200, 'token_type': 'bearer'})
        self.router = XPlatformRouter(FixtureInner(), self.platform)
        self.support = SupportRouter(self.router, registry=Path(tmp.name) / 'registry.json', version='0.6.82')
        self.server = StdioServer(self.support)
        self.server.dispatch({'jsonrpc':'2.0','id':1,'method':'initialize','params':{
            'protocolVersion':'2025-11-25','capabilities':{},'clientInfo':{'name':'synthetic','version':'1'}}})
        self.server.dispatch({'jsonrpc':'2.0','method':'notifications/initialized'})
        self.transport.requests.clear()

    def read(self, tool, response, *, status=200, **args):
        self.transport.pending.append((status, response))
        result = self.server.dispatch({'jsonrpc':'2.0','id':2,'method':'tools/call',
            'params': {'name': tool, 'arguments': {'connection_id': CID} | args}})
        self.assertNotIn(PRIVATE, json.dumps(result))
        self.assertNotIn('synthetic-access', json.dumps(result))
        self.assertIn('result', result, result)
        return result['result']

    def lookup(self, response, *, tool='x.posts.read', status=200):
        return self.read(tool, response, post_id=POST['id'], status=status)

    def search(self, response, status=200, **options):
        return self.read('x.posts.search', response, status=status, discovery_type='topics',
                         query='from:fixture is:reply', **options)

    def success(self, reply):
        self.assertFalse(reply['isError'], reply)
        return reply['structuredContent']

    def error(self, reply, code):
        self.assertTrue(reply['isError'], reply)
        self.assertEqual(reply['structuredContent']['error'], code)

    def seed_receipt(self, kind, content, result=None):
        attempt = 'original-' + kind
        path, _ = self.platform._receipt(CID, kind, attempt)
        receipt = {'connection_id': CID, 'kind': kind, 'attempt_id': attempt, 'input': content,
                   'created_at': self.platform.clock(), 'state': 'RESULT_UNKNOWN'}
        if result is not None:
            receipt |= {'state': 'SUCCEEDED', 'result': result}
        atomic_write(path, receipt, maximum=None)
        return attempt, path, path.read_bytes()

    def test_known_post_retains_long_text_and_missing_media_in_both_routes(self):
        original = POST | {'note_post': {'text': 'Full long text.'}, 'attachments': {'media_keys': [MEDIA_KEY]}}
        response = {'data': original, 'errors': [problem('resource-not-found')]}
        for tool in ('x.posts.read', 'x.posts.context'):
            reply = self.success(self.lookup(response, tool=tool))
            self.assertEqual(reply['state'], 'PARTIAL')
            self.assertEqual(reply['result']['data'], original)
            self.assertEqual(reply['missing_media_keys'], [MEDIA_KEY])
            self.assertEqual(reply['diagnostic']['code'], 'X_READ_RESOURCE_UNAVAILABLE')
            self.assertNotIn('errors', reply['result'])
            fields = self.transport.requests[-1][1]['post.fields'][0]
            self.assertIn('note_post', fields)
            self.assertIn('attachments', fields)
        reply = self.success(self.lookup({'data': original, 'includes': {'media': [PHOTO]}}))
        self.assertEqual(reply['state'], 'COMPLETE')
        self.assertEqual(reply['missing_media_keys'], [])

    def test_only_requested_id_is_returned_and_context_missing_is_explicit(self):
        original = POST | {'referenced_posts': [{'id': '4050', 'type': 'quoted'}]}
        self.error(self.lookup({'data': original | {'id': '4500'}, 'errors': [problem('resource-not-found')]}),
                   'X_CONTEXT_INCOMPLETE')
        reply = self.success(self.lookup({'data': original}, tool='x.posts.context'))
        self.assertEqual(reply['missing_context_ids'], ['4050'])
        self.assertEqual(reply['state'], 'PARTIAL')
        reply = self.success(self.lookup({'data': original | {'referenced_posts': [{'id':'4050','type':[]}]}},
                                         tool='x.posts.context'))
        self.assertEqual(reply['diagnostic']['code'], 'X_READ_CONTEXT_INCOMPLETE')

    def test_search_with_replies_keeps_its_first_window_and_valid_continuation(self):
        first = self.success(self.search({'data': [POST, REPLY], 'meta': {'result_count': 2, 'next_token': 'p2'},
            'errors': [problem('not-authorized-for-resource')]}))
        self.assertEqual((first['state'], first['page_state'], first['next_token']), ('PARTIAL','PARTIAL','p2'))
        self.assertEqual(first['result']['data'], [POST, REPLY])
        self.assertFalse(first['high_water_committed'])
        self.assertEqual(first['diagnostic']['code'], 'X_READ_PERMISSION_DENIED')
        second = self.success(self.search({'data': [], 'meta': {'result_count': 0}},
            next_token='p2', end_time=first['request']['end_time']))
        self.assertEqual(second['page_state'], 'COMPLETE')
        self.assertEqual(second['request']['end_time'], first['request']['end_time'])
        self.assertEqual(self.transport.requests[-1][1]['query'], ['from:fixture is:reply'])
        self.assertFalse(second['high_water_committed'])

    def test_failed_search_page_cannot_report_zero_but_keeps_valid_cursor(self):
        errors = [problem('rate-limit-exceeded')]
        failed = self.success(self.search({'errors': errors, 'meta': {'result_count': 0,'next_token': 'p2'}}))
        self.assertEqual((failed['state'], failed['page_state']), ('FAILED','FAILED'))
        self.assertEqual(failed['next_token'], 'p2')
        self.assertEqual(failed['result'], {'meta': {'next_token': 'p2'}})
        self.error(self.search({'errors': errors, 'data': [], 'meta': {'result_count': 0}}), 'X_READ_RATE_LIMITED')
        self.error(self.search({'data': [], 'meta': {'result_count': 0}, 'errors': None}), 'X_READ_UPSTREAM_UNKNOWN')
        valid = self.success(self.search({'meta': {'result_count': 0}, 'errors': []}))
        self.assertEqual(valid['page_state'], 'COMPLETE')
        self.assertEqual(valid['result']['meta']['result_count'], 0)

    def test_repeated_or_malformed_cursor_never_reenters_the_page(self):
        for cursor in ('p2', 'has spaces', {'opaque': PRIVATE}):
            result = self.success(self.search({'data': [REPLY], 'meta': {'result_count': 1,'next_token': cursor},
                'errors': [problem('unknown-problem')]}, next_token='p2', end_time='2026-11-18T00:00:00Z'))
            self.assertEqual(result['page_state'], 'PARTIAL')
            self.assertIsNone(result['next_token'])
            self.assertNotIn('next_token', result['result']['meta'])
            self.assertIn('X_SEARCH_CURSOR_INVALID', result['diagnostic']['codes'])
        self.error(self.search({'data':[REPLY], 'meta':{'result_count':1,'next_token':'p2'}},
            next_token='p2', end_time='2026-11-18T00:00:00Z'), 'X_SEARCH_CURSOR_INVALID')

    def test_invalid_or_duplicate_rows_in_partial_page_are_not_counted(self):
        response = {'data': [POST, REPLY, POST | {'text': 'Conflict'}, {'id':'not-an-id'}],
                    'meta': {'result_count': 4, 'next_token': 'p3'}, 'errors': [problem('usage-capped')]}
        result = self.success(self.search(response))
        self.assertEqual(result['result']['data'], [REPLY])
        self.assertEqual(result['result']['meta']['result_count'], 1)
        self.assertEqual(result['next_token'], 'p3')
        self.assertIn('X_READ_PAGE_INCOMPLETE', result['diagnostic']['codes'])
        self.error(self.search({'data': [POST, POST], 'meta': {'result_count': 2}}), 'X_SEARCH_INCOMPLETE')
        self.error(self.search({'data': [POST], 'meta': {'result_count': 0}}), 'X_SEARCH_INCOMPLETE')

    def test_partial_post_without_author_retains_the_verified_id_and_text(self):
        data = {'id': '4501', 'text': 'Verified text'}
        errors = [problem('resource-not-found')]
        single = self.success(self.lookup({'data': data | {'author_id': PRIVATE}, 'errors': errors}))
        self.assertEqual(single['result']['data'], data)
        self.assertIn('X_READ_AUTHOR_INCOMPLETE', single['diagnostic']['codes'])
        page = self.success(self.search({'data': [data], 'meta': {'result_count': 1}, 'errors': errors}))
        self.assertEqual(page['result']['data'], [data])
        self.assertIn('X_READ_AUTHOR_INCOMPLETE', page['diagnostic']['codes'])

    def test_support_logs_only_safe_codes_for_partial_and_failed_reads(self):
        self.success(self.lookup({'data': POST, 'errors': [problem('resource-not-found')]}))
        self.error(self.search({'errors': [problem('usage-capped')]}), 'X_READ_QUOTA_EXCEEDED')
        events = self.support.support.logs.snapshot()['events']
        by_tool = {event['tool']: event for event in events}
        self.assertEqual(by_tool['x.posts.read']['result'], 'PARTIAL')
        self.assertEqual(by_tool['x.posts.read']['code'], 'X_READ_RESOURCE_UNAVAILABLE')
        self.assertEqual(by_tool['x.posts.search']['result'], 'TOOL_ERROR')
        self.assertEqual(by_tool['x.posts.search']['code'], 'X_READ_QUOTA_EXCEEDED')
        serialized = json.dumps(events)
        for sensitive in (PRIVATE, POST['text'], 'is:reply', 'synthetic-access'):
            self.assertNotIn(sensitive, serialized)

    def test_timeline_uses_same_partial_contract(self):
        response = {'data':[POST], 'meta':{'result_count':1,'next_token':'tail'},
                    'errors':[problem('resource-not-found')]}
        result = self.success(self.read('x.posts.list', response))
        self.assertEqual((result['page_state'], result['result']['data'], result['next_token']), ('PARTIAL',[POST],'tail'))
        self.assertEqual(self.transport.requests[-1][0], '/2/users/123/tweets')

    def test_official_read_error_diagnostics_are_finite(self):
        for status, body, code in [
            (200, {'errors':[problem('client-forbidden')]}, 'X_READ_PERMISSION_DENIED'),
            (200, {'errors':[problem('usage-capped')]}, 'X_READ_QUOTA_EXCEEDED'),
            (200, {'errors':[problem('resource-not-found')]}, 'X_READ_RESOURCE_UNAVAILABLE'),
            (200, {'errors':[{'type':'https://untrusted.invalid/usage-capped','detail':PRIVATE}]}, 'X_READ_UPSTREAM_UNKNOWN'),
            (402, {'detail':PRIVATE}, 'X_READ_QUOTA_EXCEEDED'),
            (403, {'detail':PRIVATE}, 'X_READ_PERMISSION_DENIED'),
            (404, {'detail':PRIVATE}, 'X_READ_RESOURCE_UNAVAILABLE'),
            (429, problem('usage-capped'), 'X_READ_QUOTA_EXCEEDED'),
            (429, {'title':PRIVATE}, 'X_READ_RATE_LIMITED'),
            (502, {'title':PRIVATE}, 'X_READ_UPSTREAM_UNKNOWN'),
        ]:
            with self.subTest(status=status, code=code):
                self.error(self.lookup(body, status=status), code)

    def test_post_readback_rejects_partial_response_and_still_checks_media_text_and_identity(self):
        post = POST | {'attachments': {'media_keys':[MEDIA_KEY]}}
        original = {'text':POST['text'], 'media_keys':[MEDIA_KEY]}
        attempt, path, before = self.seed_receipt('post', original, {'post_id':POST['id']})
        complete = {'data':post, 'includes': {'media':[PHOTO]}}
        self.error(self.read('x.posts.readback', complete | {'errors':[problem('resource-not-found')]},
                             attempt_id=attempt), 'X_RESPONSE_INCOMPLETE')
        self.assertEqual(path.read_bytes(), before)
        for response in ({'data':post}, complete | {'data':post | {'author_id':'456'}},
                         complete | {'data':post | {'text':'Wrong body'}}):
            rejected = self.success(self.read('x.posts.readback', response, attempt_id=attempt))
            self.assertEqual(rejected['readback_state'], 'MISMATCH')
            self.assertEqual(path.read_bytes(), before)
        matched = self.success(self.read('x.posts.readback', complete, attempt_id=attempt))
        self.assertEqual(matched['readback_state'], 'MATCHED')
        self.assertEqual(len(self.transport.requests), 5)

    def test_strict_known_long_photo_post_uses_full_text_from_original_id(self):
        text = '完整正文保留原始换行、标点与图文顺序。' * 32 + '\n结尾。'
        keys = [MEDIA_KEY, '3_778']
        attempt, path, before = self.seed_receipt('post', {'text': text, 'media_keys': keys},
                                                  {'post_id': POST['id']})
        url = 'https://t.co/picture'
        post = POST | {'text': text[:90] + '… ' + url, 'note_post': {'text': text},
                       'attachments': {'media_keys': keys},
                       'entities': {'urls': [{'url': url, 'expanded_url': 'https://x.com/fixture/status/4501/photo/1'}]}}
        response = {'data': post, 'includes': {'media': [PHOTO | {'media_key': keys[1]}, PHOTO]}}
        matched = self.success(self.read('x.posts.readback', response, attempt_id=attempt))
        self.assertEqual(matched['readback_state'], 'MATCHED')
        self.assertEqual(matched['result'], {'post_id': POST['id']})
        self.assertEqual(matched['actual']['data']['note_post']['text'], text)
        self.assertEqual(matched['input'], json.loads(before)['input'])
        self.assertEqual(json.loads(path.read_bytes()), matched)
        path_requested, query = self.transport.requests[0]
        self.assertEqual(path_requested, '/2/tweets/' + POST['id'])
        self.assertIn('note_post', query['post.fields'][0].split(','))
        self.assertIn('attachments.media_keys', query['expansions'][0].split(','))
        self.assertEqual(len(self.transport.requests), 1)

    def test_strict_note_missing_or_different_does_not_fall_back_to_preview(self):
        text = 'Long native post with original content. ' * 22
        attempt, path, before = self.seed_receipt('post', {'text': text, 'media_key': MEDIA_KEY},
                                                  {'post_id': POST['id']})
        post = POST | {'text': text, 'attachments': {'media_keys': [MEDIA_KEY]}}
        for fields in (
            {'text': text[:90] + '…'},
            {'note_post': {'text': text + ' changed'}},
            {'note_post': {'entities': {}}},
            {'note_post': {'text': '   '}},
            {'note_post': {'text': ['invalid']}},
            {'note_post': None},
        ):
            with self.subTest(fields=fields):
                response = {'data': post | fields, 'includes': {'media': [PHOTO]}}
                mismatch = self.success(self.read('x.posts.readback', response, attempt_id=attempt))
                self.assertEqual(mismatch['readback_state'], 'MISMATCH')
                self.assertEqual(mismatch['state'], 'SUCCEEDED')
                self.assertEqual(mismatch['result'], {'post_id': POST['id']})
                self.assertEqual(path.read_bytes(), before)

    def test_strict_note_needs_exact_attachment_order_and_complete_expansion(self):
        text = 'Native full text. ' * 30
        keys = [MEDIA_KEY, '3_778']
        attempt, path, before = self.seed_receipt('post', {'text': text, 'media_keys': keys},
                                                  {'post_id': POST['id']})
        post = POST | {'text': text, 'note_post': {'text': text}, 'attachments': {'media_keys': keys}}
        media = [PHOTO, PHOTO | {'media_key': keys[1]}]
        complete = {'data': post, 'includes': {'media': media}}
        for response in (
            complete | {'data': post | {'author_id': '456'}},
            complete | {'data': post | {'id': '4509'}},
            complete | {'data': post | {'attachments': {'media_keys': keys[::-1]}}},
            complete | {'data': post | {'attachments': {'media_keys': keys, 'poll_ids': ['100']}}},
            complete | {'includes': {'media': media[:1]}},
            complete | {'includes': {'media': [*media, media[0]]}},
            complete | {'includes': {'media': [*media, 'bad row']}},
            complete | {'includes': {'media': [*media, PHOTO | {'media_key': '3_999'}]}},
        ):
            with self.subTest(response=response):
                mismatch = self.success(self.read('x.posts.readback', response, attempt_id=attempt))
                self.assertEqual(mismatch['readback_state'], 'MISMATCH')
                self.assertEqual(path.read_bytes(), before)
        self.error(self.read('x.posts.readback', complete | {'errors': [problem('resource-not-found')]},
                             attempt_id=attempt), 'X_RESPONSE_INCOMPLETE')
        self.assertEqual(path.read_bytes(), before)

    def test_strict_plain_note_uses_only_its_own_evidenced_urls(self):
        original = '全文 ' * 130
        short_url, full_url = 'https://t.co/source', 'https://example.com/post'
        raw = original + short_url
        text = original + full_url
        attempt, path, before = self.seed_receipt('post', {'text': text}, {'post_id': POST['id']})
        urls = [{'url': short_url, 'expanded_url': full_url, 'start': len(original), 'end': len(raw)}]
        post = POST | {'text': text, 'entities': {'urls': urls}, 'note_post': {'text': raw}}
        mismatch = self.success(self.read('x.posts.readback', {'data': post}, attempt_id=attempt))
        self.assertEqual(mismatch['readback_state'], 'MISMATCH')
        self.assertEqual(path.read_bytes(), before)
        post['note_post']['entities'] = {'urls': urls}
        matched = self.success(self.read('x.posts.readback', {'data': post}, attempt_id=attempt))
        self.assertEqual(matched['readback_state'], 'MATCHED')
        self.assertEqual(matched['input']['text'], text)

    def test_strict_illustrated_note_keeps_evidenced_media_url_and_html_forms(self):
        original = 'Long original & another detail. ' * 24
        photo_url = 'https://t.co/picture'
        attempt, path, before = self.seed_receipt('post', {'text': original, 'media_key': MEDIA_KEY},
                                                  {'post_id': POST['id']})
        note = {'text': original.replace('&', '&amp;') + ' ' + photo_url}
        url = {'url': photo_url, 'expanded_url': 'https://x.com/fixture/status/4501/photo/1'}
        post = POST | {'text': original[:95] + '… ' + photo_url, 'note_post': note,
                       'entities': {'urls': [url]}, 'attachments': {'media_keys': [MEDIA_KEY]}}
        response = {'data': post, 'includes': {'media': [PHOTO]}}
        mismatch = self.success(self.read('x.posts.readback', response, attempt_id=attempt))
        self.assertEqual(mismatch['readback_state'], 'MISMATCH')
        self.assertEqual(path.read_bytes(), before)
        note['entities'] = {'urls': [url]}
        matched = self.success(self.read('x.posts.readback', response, attempt_id=attempt))
        self.assertEqual(matched['readback_state'], 'MATCHED')

    def test_ordinary_post_and_reply_still_use_strict_original_readback(self):
        attempt, path, before = self.seed_receipt('post', {'text': POST['text']},
                                                  {'post_id': POST['id']})
        malformed = {'data': POST, 'errors': {}}
        mismatch = self.success(self.read('x.posts.readback', malformed, attempt_id=attempt))
        self.assertEqual(mismatch['readback_state'], 'MISMATCH')
        self.assertEqual(path.read_bytes(), before)
        post = self.success(self.read('x.posts.readback', {'data': POST}, attempt_id=attempt))
        self.assertEqual(post['readback_state'], 'MATCHED')
        reply_attempt, reply_path, reply_before = self.seed_receipt(
            'reply', {'text': REPLY['text'], 'parent_id': '4400'},
            {'post_id': REPLY['id'], 'parent_id': '4400'})
        wrong_parent = REPLY | {'referenced_posts': [{'type': 'replied_to', 'id': '4409'}]}
        mismatch = self.success(self.read('x.replies.readback', {'data': wrong_parent}, attempt_id=reply_attempt))
        self.assertEqual(mismatch['readback_state'], 'MISMATCH')
        self.assertEqual(reply_path.read_bytes(), reply_before)
        reply = self.success(self.read('x.replies.readback', {'data': REPLY}, attempt_id=reply_attempt))
        self.assertEqual(reply['readback_state'], 'MATCHED')
        self.assertEqual([route for route, _ in self.transport.requests],
                         ['/2/tweets/4501', '/2/tweets/4501', '/2/tweets/4502', '/2/tweets/4502'])

    def test_unknown_long_photo_does_not_claim_a_timeline_candidate_by_note(self):
        text = 'Long post awaiting an original response. ' * 20
        attempt, path, before = self.seed_receipt('post', {'text': text, 'media_key': MEDIA_KEY})
        post = POST | {'text': text[:90] + '…', 'note_post': {'text': text},
                       'attachments': {'media_keys': [MEDIA_KEY]}}
        unknown = self.success(self.read('x.posts.readback', {'data': [post]}, attempt_id=attempt))
        self.assertEqual((unknown['state'], unknown['readback_state']), ('RESULT_UNKNOWN', 'NO_UNIQUE_MATCH'))
        self.assertEqual(path.read_bytes(), before)
        self.assertEqual(len(self.transport.requests), 1)
        route, query = self.transport.requests[0]
        self.assertEqual(route, '/2/users/123/tweets')
        self.assertNotIn('note_post', query['post.fields'][0].split(','))

    def test_unknown_post_and_known_reply_readback_remain_strict(self):
        attempt,path,before = self.seed_receipt('post', {'text':POST['text'],'media_keys':[MEDIA_KEY]})
        self.error(self.read('x.posts.readback', {'data':[POST], 'meta':{'result_count':1,'next_token':'p2'},
                   'errors':[problem('resource-not-found')]}, attempt_id=attempt), 'X_RESPONSE_INCOMPLETE')
        self.assertEqual(path.read_bytes(), before)
        reply_attempt, reply_path, reply_file = self.seed_receipt('reply', {'text':REPLY['text'],'parent_id':'4400'},
                                                                 {'post_id':REPLY['id'],'parent_id':'4400'})
        self.error(self.read('x.replies.readback', {'data':REPLY,'errors':[problem('resource-not-found')]},
                             attempt_id=reply_attempt), 'X_RESPONSE_INCOMPLETE')
        self.assertEqual(reply_path.read_bytes(), reply_file)
        with self.assertRaisesRegex(WCEError, 'X_RESPONSE_INCOMPLETE'):
            self.transport.pending.append((200, {'data':POST, 'errors':[problem('resource-not-found')]}))
            self.api.article_post(self.platform._access(self.platform._load(), CID), POST['id'])
        self.assertEqual(len(self.transport.requests), 3)


if __name__ == '__main__':
    unittest.main()
