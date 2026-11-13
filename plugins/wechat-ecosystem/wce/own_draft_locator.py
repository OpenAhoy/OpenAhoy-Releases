"""One fixed human-delegated draft observation; never reconcile or write drafts.

Only execute() is a tool seam. prepare_grant() is a read-only host preparation
API: a reviewed maintenance installer, not this module or MCP, verifies the
human source and installs its returned grant exclusively under account locks.
"""
from dataclasses import dataclass, field, replace
from hashlib import sha256
import json
import math
import os
import re
import secrets
import time
from urllib.parse import urlencode

from .contracts import Secret, WCEError
from .http_transport import HTTPRequest, HTTPResponse, HTTPSender
from .own_auth import DRAFT_READ_APIS
from .own_draft_wire import reference_valid
from .own_response_archive import row_pin, eligible, filename
from .own_workflow import stored
from .prepared_contracts import ID, DIGEST, strict_validate
from .service import canonical, digest
from .upload_wire import contains_secret, secret_value
from . import own_draft_locator_files as files

METHOD = 'own.drafts.locate'
POLICY = 'DRAFT_CANDIDATE_LOCATE_V1'
OBSERVATION = 'OFFICIAL_DRAFT_CANDIDATE_OBSERVATION_V1'
PROJECTION = 'OFFICIAL_DRAFT_NEWS_ITEMS_RAW_JSON_V1'
BUDGET = dict(max_drafts=100, page_size=20, scans=2, list=10, candidate_get=4,
    final_get=1, total=15, seconds=300, max_http=2097152, total_http=31457280,
    max_payload=524288, zero_writes=0, no_content=1)
OFFICIAL = [
    {'url': 'https://developers.weixin.qq.com/doc/service/api/draftbox/draftmanage/api_draft_batchget',
     'sha256': '7d300262ef78ad19948c3399cbc0a0bc77e788acb11328a06cd769ab73534c87'},
    {'url': 'https://developers.weixin.qq.com/doc/service/api/draftbox/draftmanage/api_getdraft',
     'sha256': '40dd64c6fe083b8bf5f337cda869f2a1b98ff0bf507deb9c894538f4aff014b0'}]
META = ('title', 'author', 'thumb_media_id', 'content_source_url')
HOLD_REASONS = frozenset({'LOCATOR_NOT_CONFIGURED', 'LOCATOR_INCOMPLETE', 'LOCATOR_CANCELLED',
    'LOCATOR_DEADLINE', 'LOCATOR_TRANSPORT_UNKNOWN', 'LOCATOR_HTTP_REJECTED',
    'LOCATOR_API_REJECTED', 'LOCATOR_SECRET_REFLECTION', 'LOCATOR_INVALID_JSON',
    'LOCATOR_PAYLOAD_INVALID', 'LOCATOR_BYTES_LIMIT', 'LOCATOR_JSON_LIMIT',
    'LOCATOR_CASE_LIMIT', 'LOCATOR_TOTAL_LIMIT', 'LOCATOR_LIST_INVALID',
    'LOCATOR_LIST_DRIFT', 'LOCATOR_UNEXPECTED_LIST_BODY', 'LOCATOR_CANDIDATE_LIMIT',
    'LOCATOR_NO_UNIQUE_CANDIDATE', 'LOCATOR_FINAL_DRIFT', 'LOCATOR_BINDING_CHANGED',
    'LOCATOR_GRANT_CHANGED', 'LOCATOR_GRANT_REVOKED', 'LOCATOR_BUDGET_SPENT',
    'LOCATOR_EVIDENCE_INVALID', 'LOCATOR_OUTPUT_LIMIT', 'LOCATOR_AUTHORIZATION_CHANGED'})
GRANT_FIELDS = {'schema', 'policy', 'case_id', 'human_source', 'binding',
    'original_row_pin', 'selector', 'original_intent_sha', 'expected_projection_sha',
    'uploads_sha', 'known_exclusion', 'candidate_scope', 'current_policy_sha',
    'budget', 'official_sources', 'created_at'}
ATTEMPT_FIELDS = {'schema', 'case_id', 'attempt_id', 'grant_sha', 'owner_sha',
    'binding_sha', 'original_pin_sha', 'admitted_at', 'phase', 'hold_reason'}
CLAIM_FIELDS = {'schema', 'case_id', 'attempt_id', 'grant_sha', 'owner_sha',
    'ordinal', 'api', 'request_sha', 'claimed_at', 'elapsed_ms'}
OUTCOME_FIELDS = {'schema', 'case_id', 'attempt_id', 'claim_sha', 'state',
    'http_status', 'platform_code', 'response_sha', 'response_bytes'}
OBS_FIELDS = {'schema', 'policy', 'case_id', 'attempt_id', 'grant_sha',
    'binding_sha', 'original_row_pin', 'selector', 'expected_projection_sha',
    'uploads_sha', 'scan_shas', 'candidate_summaries', 'selected_reference',
    'first_payload', 'final_payload', 'first_claim_sha', 'final_claim_sha',
    'observed_at', 'read_counts', 'quality_state', 'original_request_reconciled'}


def fail(code='LOCATOR_EVIDENCE_INVALID'):
    raise WCEError(code)


def shape(value, keys):
    if type(value) is not dict or set(value) != keys or type(value.get('schema')) is not int or value['schema'] != 1:
        fail()


def finite(value):
    return type(value) in (int, float) and math.isfinite(value)


def sha(value):
    strict_validate(value, DIGEST)


def stable_case(binding, row, selector):
    return digest({'binding': binding, 'step_id': row['id'], 'owner': row['owner'],
        'intent_digest': row['intent_digest'], 'target': row['target'], 'selector': selector})


def original_proof_present(root, row):
    return (os.path.lexists(root / filename(row)) or os.path.lexists(root /
        ('response-index-' + row['id'] + '-' + row['owner'] + '.json')))


def snapshot(service, arguments, *, exclusion_id=None, exclusion_key=None):
    """Historical validation only; no _current, token, write gate, or SQL write."""
    w, p = service.workflow, service.profile()
    with _history_transaction(w.db) as (db, history_locators):
        w._resource(db, p, history_locators=history_locators)
        row = w._history(db, p, arguments['request_key'], history_locators=history_locators)
        if row is None or row['operation'] != 'add': fail('LOCATOR_NOT_CONFIGURED')
        intent, _ = w._step(db, p, row, history_locators=history_locators)
        eligible(w, db, p, row, history_locators=history_locators)
        expected = intent['projection'].get('articles')
        if type(expected) is not list or len(expected) != 8: fail('LOCATOR_BINDING_CHANGED')
        if len(intent['uploads']) != 40: fail('LOCATOR_BINDING_CHANGED')
        for upload in intent['uploads']:
            other = db.execute('SELECT * FROM own_steps WHERE id=?', (upload['id'],)).fetchone()
            if other is None or other['state'] != 'SUCCEEDED': fail('LOCATOR_BINDING_CHANGED')
            w._step(db, p, other, history_locators=history_locators)
            if any(other[k] != upload[k] for k in ('id', 'intent_digest', 'target', 'result_digest')):
                fail('LOCATOR_BINDING_CHANGED')
        result = {'row': dict(row), 'pin': row_pin(row), 'binding': p.binding(),
            'selector': intent['selector'], 'projection': intent['projection'],
            'uploads': intent['uploads'], 'metadata': [{k: a[k] for k in META} for a in expected]}
        result['case_id'] = stable_case(result['binding'], row, intent['selector'])
        if exclusion_id is not None or exclusion_key is not None:
            old = (db.execute('SELECT * FROM own_steps WHERE id=?', (exclusion_id,)).fetchone()
                if exclusion_id is not None else w._history(db, p, exclusion_key, history_locators=history_locators))
            if old is None or old['operation'] != 'add' or old['state'] != 'SUCCEEDED' or old['id'] == row['id']:
                fail('LOCATOR_BINDING_CHANGED')
            _, saved = w._step(db, p, old, history_locators=history_locators)
            if not reference_valid(saved.get('reference'), p.source_kind == 'SYNTHETIC_SETUP'): fail()
            result['known_exclusion'] = {'step_id': old['id'], 'row_pin_sha': digest(row_pin(old)),
                'result_sha': digest(saved)}
            result['excluded_reference'] = saved['reference']
    return result


def prepare_grant(service, arguments, human_source, known_exclusion_key):
    """Read-only host proposal. This neither approves nor installs a grant."""
    validate_arguments(service, arguments)
    service.policy.check()
    current = snapshot(service, arguments, exclusion_key=known_exclusion_key)
    if current['row']['state'] != 'RESULT_UNKNOWN': fail('LOCATOR_BINDING_CHANGED')
    if original_proof_present(service.policy.root, current['row']): fail('LOCATOR_BINDING_CHANGED')
    delegation = service.policy.delegation()
    value = {'schema': 1, 'policy': POLICY, 'case_id': current['case_id'],
        'human_source': human_source, 'binding': current['binding'],
        'original_row_pin': current['pin'], 'selector': current['selector'],
        'original_intent_sha': current['row']['intent_digest'],
        'expected_projection_sha': digest(current['projection']), 'uploads_sha': digest(current['uploads']),
        'known_exclusion': current['known_exclusion'], 'candidate_scope': delegation['candidate_scope'],
        'current_policy_sha': delegation['policy_digest'], 'budget': dict(BUDGET),
        'official_sources': list(OFFICIAL), 'created_at': time.time()}
    validate_grant(value, current)
    return value


def validate_arguments(service, arguments):
    if type(arguments) is not dict or set(arguments) != {'connection_id', 'request_key'}: fail('LOCATOR_NOT_CONFIGURED')
    for value in arguments.values(): strict_validate(value, ID)
    if arguments['connection_id'] != service.policy.data['connection_id']:
        fail('CONNECTION_SCOPE_MISMATCH')


def validate_grant(g, s):
    shape(g, GRANT_FIELDS)
    human = g['human_source']
    if type(human) is not dict or set(human) != {'thread_id', 'message_id', 'instruction_sha256'}: fail()
    strict_validate(human['thread_id'], ID); strict_validate(human['message_id'], ID)
    sha(human['instruction_sha256'])
    exclusion = g['known_exclusion']
    if type(exclusion) is not dict or set(exclusion) != {'step_id', 'row_pin_sha', 'result_sha'}: fail()
    strict_validate(exclusion['step_id'], ID)
    for name in ('row_pin_sha', 'result_sha'): sha(exclusion[name])
    for name in ('case_id', 'original_intent_sha', 'expected_projection_sha', 'uploads_sha', 'candidate_scope', 'current_policy_sha'):
        sha(g[name])
    if (g['policy'] != POLICY or g['budget'] != BUDGET
            or any(type(g['budget'].get(k)) is not int for k in BUDGET)
            or g['official_sources'] != OFFICIAL or not finite(g['created_at'])
            or g['case_id'] != s['case_id'] or canonical(g['binding']) != canonical(s['binding'])
            or canonical(g['original_row_pin']) != canonical(s['pin']) or canonical(g['selector']) != canonical(s['selector'])
            or g['original_intent_sha'] != s['row']['intent_digest']
            or g['expected_projection_sha'] != digest(s['projection'])
            or g['uploads_sha'] != digest(s['uploads'])
            or g['known_exclusion'] != s['known_exclusion']): fail('LOCATOR_BINDING_CHANGED')
    files.encoded(g, 'grant')


def full_payload(value, synthetic):
    files.encoded(value, 'payload')
    if type(value) is not dict or type(value.get('news_item')) is not list or len(value['news_item']) != 8:
        fail('LOCATOR_PAYLOAD_INVALID')
    for article in value['news_item']:
        if type(article) is not dict or any(type(article.get(k)) is not str for k in (*META, 'content')):
            fail('LOCATOR_PAYLOAD_INVALID')
        if not reference_valid(article['thumb_media_id'], synthetic): fail('LOCATOR_PAYLOAD_INVALID')
    return value


def result(observation, state, key, cached):
    value = {'schema': 1, 'state': 'CANDIDATE_READ', 'original_request_reconciled': False,
        'original_journal_state': state, 'readback_state': 'UNVERIFIED',
        'case_id': observation['case_id'], 'request_key': key,
        'candidate_reference': observation['selected_reference'], 'article_count': 8,
        'actual_projection_policy': PROJECTION, 'actual_projection': observation['final_payload'],
        'observed_at': observation['observed_at'], 'from_cache': cached,
        'read_counts': observation['read_counts']}
    # Match actual IPC and MCP encoders, including duplicated text/structured
    # content. A maximal valid inbound RPC ID reserves the ID's frame budget;
    # root transport rejects oversized request IDs before invoking this method.
    ipc = json.dumps({'ok': True, 'result': value}, ensure_ascii=False, allow_nan=False, separators=(',', ':')).encode() + b'\n'
    text = json.dumps(value, ensure_ascii=False, allow_nan=False)
    mcp = json.dumps({'jsonrpc': '2.0', 'id': 'x' * 4096, 'result': {
        'content': [{'type': 'text', 'text': text}], 'structuredContent': value, 'isError': False}},
        ensure_ascii=False, allow_nan=False).encode() + b'\n'
    if max(len(ipc), len(mcp)) > 1048576:
        return hold(observation['case_id'], 'LOCATOR_OUTPUT_LIMIT') | {'observation_archived': True}
    return value


def hold(case_id, reason):
    return {'schema': 1, 'state': 'HOLD', 'reason': reason if reason in HOLD_REASONS else 'LOCATOR_EVIDENCE_INVALID',
        'case_id': case_id, 'readback_state': 'UNVERIFIED', 'original_request_reconciled': False}


def check_cancel(guard):
    if guard is not None:
        try: guard()
        except (EOFError, OSError, WCEError): fail('LOCATOR_CANCELLED')


@dataclass(eq=False)
class LocatorReadContext:
    """Created only by execute's fresh durable attempt, never deserialized."""
    service: object = field(repr=False)
    arguments: dict = field(repr=False)
    evidence: object = field(repr=False)
    grant: dict = field(repr=False)
    grant_sha: str
    initial: dict = field(repr=False)
    attempt: dict = field(repr=False)
    deadline: float
    owner: Secret = field(repr=False)
    cancel_guard: object = field(default=None, repr=False)
    started: float = field(default_factory=time.monotonic)
    token: object = field(default=None, repr=False)
    profile: object = field(default=None, repr=False)
    active_claim: object = field(default=None, repr=False)
    records: list = field(default_factory=list, repr=False)
    http_bytes: int = 0
    counts: dict = field(default_factory=lambda: {'list': 0, 'candidate_get': 0, 'final_get': 0, 'total': 0})
    live: bool = True
    candidates: tuple = field(default=(), repr=False)
    selected: str = field(default=None, repr=False)

    def current(self):
        if not self.live: fail('LOCATOR_AUTHORIZATION_CHANGED')
        check_cancel(self.cancel_guard)
        if type(self.owner) is not Secret or digest(secret_value(self.owner)) != self.attempt['owner_sha']:
            fail('LOCATOR_AUTHORIZATION_CHANGED')
        if time.monotonic() >= self.deadline: fail('LOCATOR_DEADLINE')
        self.service.guard(self.deadline)
        if self.evidence.revoked(): fail('LOCATOR_GRANT_REVOKED')
        if self.evidence.exists('stop.json'): fail('LOCATOR_CANCELLED')
        if self.evidence.read('grant.json') != (self.grant, self.grant_sha): fail('LOCATOR_GRANT_CHANGED')
        delegation = self.service.policy.delegation()
        if (self.grant['candidate_scope'] != delegation['candidate_scope']
                or self.grant['current_policy_sha'] != delegation['policy_digest']): fail('LOCATOR_GRANT_CHANGED')
        s = snapshot(self.service, self.arguments, exclusion_id=self.grant['known_exclusion']['step_id'])
        validate_grant(self.grant, s)
        if s['row']['state'] != 'RESULT_UNKNOWN' or original_proof_present(self.service.policy.root, s['row']):
            fail('LOCATOR_BINDING_CHANGED')
        if self.evidence.read('attempt.json')[0] != self.attempt: fail()
        if self.token is not None:
            w = self.service.workflow
            if self.profile.granted_actions != frozenset(DRAFT_READ_APIS) | {'local.read'}: fail()
            w._current(self.profile, w.active_lease)
            if not self.service.tokens.valid(self.token): fail('LOCATOR_AUTHORIZATION_CHANGED')

    def read(self, api, payload, category):
        self.current()
        if api not in DRAFT_READ_APIS or category not in self.counts or category == 'total': fail()
        if self.counts[category] >= BUDGET[category] or self.counts['total'] >= 15: fail('LOCATOR_BUDGET_SPENT')
        if api == 'draft.batchget':
            if category != 'list' or set(payload) != {'offset', 'count', 'no_content'} or payload['count'] != 20 or payload['no_content'] != 1:
                fail()
            if type(payload['offset']) is not int or payload['offset'] not in range(0, 100, 20): fail()
        else:
            if category not in {'candidate_get', 'final_get'} or set(payload) != {'media_id'}:
                fail()
            if not reference_valid(payload['media_id'], self.profile.source_kind == 'SYNTHETIC_SETUP'): fail()
            if (category == 'candidate_get' and payload['media_id'] not in self.candidates
                    or category == 'final_get' and payload['media_id'] != self.selected): fail()
        ordinal = len(self.records) + 1
        claim = {'schema': 1, 'case_id': self.grant['case_id'], 'attempt_id': self.attempt['attempt_id'],
            'grant_sha': self.grant_sha, 'owner_sha': self.attempt['owner_sha'], 'ordinal': ordinal,
            'api': api, 'request_sha': digest({'api': api, 'payload': payload}),
            'claimed_at': time.time(), 'elapsed_ms': max(0, int((time.monotonic() - self.started) * 1000))}
        name = f'reads/{ordinal:02d}'
        claim_sha = self.evidence.write(name + '.claim.json', claim)
        self.active_claim = (claim, claim_sha)
        self.counts[category] += 1; self.counts['total'] += 1
        self.current()  # fsync -> current scope -> exact claim -> transport
        if self.evidence.read(name + '.claim.json') != self.active_claim: fail()
        w = self.service.workflow
        w._current(self.profile, w.active_lease, api)
        sender = w.sender
        if self.profile.source_kind == 'SYNTHETIC_SETUP':
            if type(sender) is HTTPSender or getattr(sender, 'mode', None) != 'SYNTHETIC_OWN_WIRE': fail()
        elif type(sender) is not HTTPSender or not sender.enabled: fail('OWN_HTTP_DISABLED')
        request = HTTPRequest('POST', '/cgi-bin/' + api.replace('.', '/') + '?' +
            urlencode({'access_token': secret_value(self.token.token)}),
            {'Content-Type': 'application/json; charset=utf-8'}, canonical(payload).encode())
        timeout = min(10.0, self.deadline - time.monotonic(), self.token.wall_deadline - time.time())
        if timeout <= 0: fail('LOCATOR_DEADLINE')
        response, value, reason = None, None, None
        outcome = {'schema': 1, 'case_id': self.grant['case_id'], 'attempt_id': self.attempt['attempt_id'],
            'claim_sha': claim_sha, 'state': 'TRANSPORT_UNKNOWN', 'http_status': None,
            'platform_code': None, 'response_sha': None, 'response_bytes': 0}
        try:
            try: response = sender.send(request, timeout)
            except Exception: fail('LOCATOR_TRANSPORT_UNKNOWN')
            if type(response) is not HTTPResponse or type(response.body) is not bytes: fail('LOCATOR_TRANSPORT_UNKNOWN')
            length = len(response.body)
            self.http_bytes += length
            outcome['response_bytes'] = min(length, BUDGET['max_http'])
            if type(response.status) is int and 100 <= response.status <= 599: outcome['http_status'] = response.status
            if length > BUDGET['max_http'] or self.http_bytes > BUDGET['total_http']: fail('LOCATOR_BYTES_LIMIT')
            if contains_secret(response.body, self.token.token): fail('LOCATOR_SECRET_REFLECTION')
            value = files.decode(response.body, 'http', canonical_bytes=False)
            if contains_secret(value, self.token.token, max_nodes=16384): fail('LOCATOR_SECRET_REFLECTION')
            outcome['response_sha'] = sha256(response.body).hexdigest()
            if type(value) is not dict: fail('LOCATOR_INVALID_JSON')
            if type(response.status) is not int or response.status != 200: fail('LOCATOR_HTTP_REJECTED')
            code = value.get('errcode', 0)
            if type(code) is not int or not -(2**31) <= code < 2**31: fail('LOCATOR_INVALID_JSON')
            if code:
                outcome['platform_code'] = code
                fail('LOCATOR_API_REJECTED')
            outcome['state'] = 'RECEIVED'
        except WCEError as error:
            reason = error.code
            if reason in {'LOCATOR_API_REJECTED', 'LOCATOR_HTTP_REJECTED'}: outcome['state'] = 'REJECTED'
            elif reason != 'LOCATOR_TRANSPORT_UNKNOWN': outcome['state'] = 'PARSE_HOLD'
        outcome_sha = self.evidence.write(name + '.outcome.json', outcome)
        self.records.append({'claim': claim, 'claim_sha': claim_sha, 'outcome': outcome, 'outcome_sha': outcome_sha})
        self.active_claim = None
        if reason: fail(reason)
        # The caller may archive a fully qualified final response after revoke;
        # all future network calls and the result-release gate still use current.
        return value, self.records[-1]


def scan(context, number):
    items, claims, total, offset = {}, [], None, 0
    while total is None or offset < total:
        value, record = context.read('draft.batchget', {'offset': offset, 'count': 20, 'no_content': 1}, 'list')
        context.current()
        amount, count, page = value.get('total_count'), value.get('item_count'), value.get('item')
        if type(amount) is not int or not 0 <= amount <= 100: fail('LOCATOR_TOTAL_LIMIT')
        if total is None: total = amount
        if amount != total or type(count) is not int or type(page) is not list or count != len(page) or count != min(20, max(0, total - offset)):
            fail('LOCATOR_LIST_INVALID')
        for item in page:
            if type(item) is not dict or not reference_valid(item.get('media_id'), context.profile.source_kind == 'SYNTHETIC_SETUP'):
                fail('LOCATOR_LIST_INVALID')
            changed, reference = item.get('update_time'), item['media_id']
            if type(changed) is not int or changed < 0 or reference in items: fail('LOCATOR_LIST_INVALID')
            # no_content=1 may omit content entirely; never demand title metadata.
            content = item.get('content')
            if type(content) is dict and 'news_item' in content:
                news = content['news_item']
                if type(news) is not list or any(type(a) is not dict or a.get('content') not in (None, '') for a in news):
                    fail('LOCATOR_UNEXPECTED_LIST_BODY')
            if 'news_item' in item:
                news = item['news_item']
                if type(news) is not list or any(type(a) is not dict or a.get('content') not in (None, '') for a in news):
                    fail('LOCATOR_UNEXPECTED_LIST_BODY')
            items[reference] = changed
        claims.append(record['claim_sha']); offset += 20
    value = {'schema': 1, 'case_id': context.grant['case_id'], 'attempt_id': context.attempt['attempt_id'],
        'grant_sha': context.grant_sha, 'scan': number, 'total': total,
        'items': [{'media_id': k, 'update_time': items[k]} for k in sorted(items)], 'claims': claims}
    return value, context.evidence.write(f'scan{number}.json', value)


def observe(context):
    first_scan, sha1 = scan(context, 1)
    s = context.initial
    candidates = [a['media_id'] for a in first_scan['items']
        if abs(a['update_time'] - s['row']['created']) <= 300 and a['media_id'] != s['excluded_reference']]
    if len(candidates) > 4: fail('LOCATOR_CANDIDATE_LIMIT')
    if not candidates: fail('LOCATOR_NO_UNIQUE_CANDIDATE')
    context.candidates = tuple(candidates)
    summaries, matches = [], []
    for reference in candidates:
        value, record = context.read('draft.get', {'media_id': reference}, 'candidate_get')
        value = full_payload(value, context.profile.source_kind == 'SYNTHETIC_SETUP')
        context.current()
        match = [{k: a[k] for k in META} for a in value['news_item']] == s['metadata']
        summaries.append({'id_sha': digest(reference), 'claim_sha': record['claim_sha'],
            'response_sha': record['outcome']['response_sha'], 'article_count': 8, 'metadata_match': match})
        if match: matches.append((reference, value, record))
    second_scan, sha2 = scan(context, 2)
    if first_scan['total'] != second_scan['total'] or first_scan['items'] != second_scan['items']:
        fail('LOCATOR_LIST_DRIFT')
    if len(matches) != 1: fail('LOCATOR_NO_UNIQUE_CANDIDATE')
    reference, first, record = matches[0]
    context.selected = reference
    final, final_record = context.read('draft.get', {'media_id': reference}, 'final_get')
    full_payload(final, context.profile.source_kind == 'SYNTHETIC_SETUP')
    if canonical(final) != canonical(first): fail('LOCATOR_FINAL_DRIFT')
    # Immutable history is rechecked here; a post-response revoke blocks release,
    # never changes the already obtained official observation into a write.
    historical = snapshot(context.service, context.arguments, exclusion_id=context.grant['known_exclusion']['step_id'])
    validate_grant(context.grant, historical)
    observation = {'schema': 1, 'policy': OBSERVATION, 'case_id': context.grant['case_id'],
        'attempt_id': context.attempt['attempt_id'], 'grant_sha': context.grant_sha,
        'binding_sha': digest(s['binding']), 'original_row_pin': s['pin'], 'selector': s['selector'],
        'expected_projection_sha': context.grant['expected_projection_sha'], 'uploads_sha': context.grant['uploads_sha'],
        'scan_shas': [sha1, sha2], 'candidate_summaries': summaries, 'selected_reference': reference,
        'first_payload': first, 'final_payload': final, 'first_claim_sha': record['claim_sha'],
        'final_claim_sha': final_record['claim_sha'], 'observed_at': time.time(),
        'read_counts': dict(context.counts), 'quality_state': 'UNVERIFIED', 'original_request_reconciled': False}
    observation_sha = context.evidence.write('observation.json', observation)
    complete = {'schema': 1, 'case_id': context.grant['case_id'], 'attempt_id': context.attempt['attempt_id'],
        'grant_sha': context.grant_sha, 'owner_sha': context.attempt['owner_sha'],
        'observation_sha': observation_sha, 'claims_sha': digest(context.records), 'completed_at': time.time()}
    context.evidence.write('complete.json', complete)
    context.attempt = context.attempt | {'phase': 'COMPLETE'}
    context.evidence.write('attempt.json', context.attempt, replace_attempt=True)
    return observation


def cached(service, arguments, evidence, grant, grant_sha, initial, deadline, cancel_guard=None):
    """A seal is history, never an invitation to resume an interrupted owner."""
    attempt, _ = evidence.read('attempt.json')
    shape(attempt, ATTEMPT_FIELDS)
    sha(attempt['owner_sha'])
    if (attempt['case_id'] != grant['case_id']
            or attempt['attempt_id'] != digest({'locator_attempt': grant['case_id']})
            or attempt['grant_sha'] != grant_sha or attempt['binding_sha'] != digest(initial['binding'])
            or attempt['original_pin_sha'] != digest(initial['pin']) or not finite(attempt['admitted_at'])
            or attempt['phase'] not in {'ADMITTED', 'READING', 'COMPLETE', 'HOLD'}
            or attempt['hold_reason'] not in HOLD_REASONS | {None}): fail()
    if not evidence.exists('complete.json'):
        reason = 'LOCATOR_INCOMPLETE'
        if evidence.exists('stop.json'):
            stop, _ = evidence.read('stop.json')
            shape(stop, {'schema', 'case_id', 'attempt_id', 'reason', 'stopped_at'})
            if (stop['case_id'] != grant['case_id'] or stop['attempt_id'] != attempt['attempt_id']
                    or stop['reason'] not in HOLD_REASONS or not finite(stop['stopped_at'])): fail()
            reason = stop['reason']
        return hold(grant['case_id'], reason)
    seal, _ = evidence.read('complete.json')
    shape(seal, {'schema', 'case_id', 'attempt_id', 'grant_sha', 'owner_sha',
        'observation_sha', 'claims_sha', 'completed_at'})
    for key in ('observation_sha', 'claims_sha'): sha(seal[key])
    if (any(seal[k] != attempt[k] for k in ('case_id', 'attempt_id', 'grant_sha', 'owner_sha'))
            or not finite(seal['completed_at']) or seal['completed_at'] < attempt['admitted_at']): fail()
    observation, observed_sha = evidence.read('observation.json')
    shape(observation, OBS_FIELDS)
    if (observed_sha != seal['observation_sha'] or observation['policy'] != OBSERVATION
            or any(observation[k] != attempt[k] for k in ('case_id', 'attempt_id', 'grant_sha', 'binding_sha'))
            or canonical(observation['original_row_pin']) != canonical(initial['pin'])
            or canonical(observation['selector']) != canonical(initial['selector'])
            or observation['expected_projection_sha'] != grant['expected_projection_sha']
            or observation['uploads_sha'] != grant['uploads_sha']
            or observation['quality_state'] != 'UNVERIFIED' or observation['original_request_reconciled'] is not False
            or not finite(observation['observed_at']) or not attempt['admitted_at'] <= observation['observed_at'] <= seal['completed_at']): fail()
    synthetic = initial['binding']['source_kind'] == 'SYNTHETIC_SETUP'
    first, final = observation['first_payload'], observation['final_payload']
    full_payload(first, synthetic); full_payload(final, synthetic)
    if canonical(first) != canonical(final) or [{k: a[k] for k in META} for a in first['news_item']] != initial['metadata']: fail()
    if not reference_valid(observation['selected_reference'], synthetic): fail()
    scan_values, scan_shas = [], []
    for number in (1, 2):
        value, scan_sha = evidence.read(f'scan{number}.json')
        shape(value, {'schema', 'case_id', 'attempt_id', 'grant_sha', 'scan', 'total', 'items', 'claims'})
        if (any(value[k] != attempt[k] for k in ('case_id', 'attempt_id', 'grant_sha'))
                or type(value['scan']) is not int or value['scan'] != number
                or type(value['total']) is not int or not 1 <= value['total'] <= 100
                or type(value['items']) is not list or len(value['items']) != value['total']): fail()
        seen = set()
        for item in value['items']:
            if type(item) is not dict or set(item) != {'media_id', 'update_time'}:
                fail()
            if (not reference_valid(item['media_id'], synthetic) or item['media_id'] in seen
                    or type(item['update_time']) is not int or item['update_time'] < 0): fail()
            seen.add(item['media_id'])
        if value['items'] != sorted(value['items'], key=lambda a: a['media_id']): fail()
        scan_values.append(value); scan_shas.append(scan_sha)
    if (observation['scan_shas'] != scan_shas or scan_values[0]['total'] != scan_values[1]['total']
            or scan_values[0]['items'] != scan_values[1]['items']): fail()
    candidates = [a['media_id'] for a in scan_values[0]['items']
        if abs(a['update_time'] - initial['row']['created']) <= 300 and a['media_id'] != initial['excluded_reference']]
    summaries = observation['candidate_summaries']
    if not 1 <= len(candidates) <= 4 or type(summaries) is not list or len(summaries) != len(candidates): fail()
    matches = []
    for reference, summary in zip(candidates, summaries):
        if type(summary) is not dict or set(summary) != {'id_sha', 'claim_sha', 'response_sha', 'article_count', 'metadata_match'}:
            fail()
        for key in ('id_sha', 'claim_sha', 'response_sha'): sha(summary[key])
        if (summary['id_sha'] != digest(reference) or type(summary['metadata_match']) is not bool
                or type(summary['article_count']) is not int or summary['article_count'] != 8): fail()
        if summary['metadata_match']: matches.append(reference)
    if matches != [observation['selected_reference']]: fail()
    total = scan_values[0]['total']
    pages = max(1, (total + 19) // 20)
    expected = [('draft.batchget', {'offset': x * 20, 'count': 20, 'no_content': 1}) for x in range(pages)]
    expected += [('draft.get', {'media_id': r}) for r in candidates]
    expected += [('draft.batchget', {'offset': x * 20, 'count': 20, 'no_content': 1}) for x in range(pages)]
    expected += [('draft.get', {'media_id': observation['selected_reference']})]
    counts = {'list': pages * 2, 'candidate_get': len(candidates), 'final_get': 1, 'total': len(expected)}
    if observation['read_counts'] != counts or any(type(observation['read_counts'].get(k)) is not int for k in counts): fail()
    records = []
    for ordinal, (api, payload) in enumerate(expected, 1):
        claim, claim_sha = evidence.read(f'reads/{ordinal:02d}.claim.json')
        outcome, outcome_sha = evidence.read(f'reads/{ordinal:02d}.outcome.json')
        shape(claim, CLAIM_FIELDS); shape(outcome, OUTCOME_FIELDS)
        if (any(claim[k] != attempt[k] for k in ('case_id', 'attempt_id', 'grant_sha', 'owner_sha'))
                or type(claim['ordinal']) is not int or claim['ordinal'] != ordinal or claim['api'] != api
                or claim['request_sha'] != digest({'api': api, 'payload': payload})
                or not finite(claim['claimed_at']) or not attempt['admitted_at'] <= claim['claimed_at'] <= seal['completed_at']
                or type(claim['elapsed_ms']) is not int or not 0 <= claim['elapsed_ms'] <= 300000
                or any(outcome[k] != attempt[k] for k in ('case_id', 'attempt_id'))
                or outcome['claim_sha'] != claim_sha or outcome['state'] != 'RECEIVED'
                or type(outcome['http_status']) is not int or outcome['http_status'] != 200
                or outcome['platform_code'] is not None or type(outcome['response_bytes']) is not int
                or not 0 < outcome['response_bytes'] <= BUDGET['max_http']): fail()
        sha(outcome['response_sha'])
        records.append({'claim': claim, 'claim_sha': claim_sha, 'outcome': outcome, 'outcome_sha': outcome_sha})
    if digest(records) != seal['claims_sha'] or sum(r['outcome']['response_bytes'] for r in records) > BUDGET['total_http']: fail()
    if (scan_values[0]['claims'] != [r['claim_sha'] for r in records[:pages]]
            or scan_values[1]['claims'] != [r['claim_sha'] for r in records[pages + len(candidates):-1]]): fail()
    for summary, record in zip(summaries, records[pages:pages + len(candidates)]):
        if summary['claim_sha'] != record['claim_sha'] or summary['response_sha'] != record['outcome']['response_sha']: fail()
    selected_record = records[pages + candidates.index(observation['selected_reference'])]
    if observation['first_claim_sha'] != selected_record['claim_sha'] or observation['final_claim_sha'] != records[-1]['claim_sha']: fail()
    names, _ = evidence.inventory()
    expected_names = {'grant.json', 'attempt.json', 'scan1.json', 'scan2.json', 'observation.json', 'complete.json'}
    expected_names |= {f'reads/{n:02d}.{k}.json' for n in range(1, len(records) + 1) for k in ('claim', 'outcome')}
    if names != expected_names: fail()
    # These are historical grant scope/policy hashes; only CURRENT policy,
    # binding and draft_read control release. Never turn old grant into new I/O.
    service.guard(deadline)
    check_cancel(cancel_guard)
    if evidence.revoked(): fail('LOCATOR_GRANT_REVOKED')
    return result(observation, initial['row']['state'], arguments['request_key'], True)


def execute(service, arguments, deadline, *, cancel_guard=None):
    validate_arguments(service, arguments)
    check_cancel(cancel_guard)
    remaining = deadline - time.monotonic()
    if remaining <= 0 or not service.serial.acquire(timeout=max(0, min(60, remaining))):
        raise WCEError('CONNECTION_QUEUE_EXPIRED')
    evidence, context, case_id = None, None, None
    try:
        service.guard(deadline)
        check_cancel(cancel_guard)
        if 'draft_read' not in service.policy.value['capabilities']: fail('LOCATOR_AUTHORIZATION_CHANGED')
        initial = snapshot(service, arguments)
        case_id = initial['case_id']
        evidence = files.Evidence(service.policy.root, case_id)
        if evidence.revoked(): fail('LOCATOR_GRANT_REVOKED')
        if not evidence.exists('grant.json'): fail('LOCATOR_NOT_CONFIGURED')
        grant, grant_sha = evidence.read('grant.json')
        shape(grant, GRANT_FIELDS)
        initial = snapshot(service, arguments, exclusion_id=grant['known_exclusion']['step_id'])
        validate_grant(grant, initial)
        if evidence.exists('attempt.json'):
            return cached(service, arguments, evidence, grant, grant_sha, initial, deadline, cancel_guard)
        if evidence.exists('stop.json') or evidence.exists('complete.json'): fail('LOCATOR_EVIDENCE_INVALID')
        names, _ = evidence.inventory()
        if names != {'grant.json'}: fail('LOCATOR_EVIDENCE_INVALID')
        delegated = service.policy.delegation()
        if grant['candidate_scope'] != delegated['candidate_scope'] or grant['current_policy_sha'] != delegated['policy_digest']:
            fail('LOCATOR_GRANT_CHANGED')
        if initial['row']['state'] != 'RESULT_UNKNOWN' or original_proof_present(service.policy.root, initial['row']):
            fail('LOCATOR_BINDING_CHANGED')
        service.guard(deadline)
        check_cancel(cancel_guard)
        owner = Secret(secrets.token_hex(32))
        attempt = {'schema': 1, 'case_id': case_id, 'attempt_id': digest({'locator_attempt': case_id}),
            'grant_sha': grant_sha, 'owner_sha': digest(secret_value(owner)), 'binding_sha': digest(initial['binding']),
            'original_pin_sha': digest(initial['pin']), 'admitted_at': time.time(), 'phase': 'ADMITTED', 'hold_reason': None}
        evidence.write('attempt.json', attempt)
        context = LocatorReadContext(service, dict(arguments), evidence, grant, grant_sha, initial, attempt,
            min(deadline, time.monotonic() + 300), owner, cancel_guard)
        context.current()
        # Durable attempt precedes even the cache-miss credential/token branch.
        context.token = service.tokens.get(context.current)
        context.profile = replace(service.profile(context.token), granted_actions=frozenset(DRAFT_READ_APIS) | {'local.read'})
        service.workflow.activate(context.profile, context.token, context.deadline)
        context.current()
        observation = observe(context)
        service.guard(deadline)
        check_cancel(cancel_guard)
        if evidence.revoked(): fail('LOCATOR_GRANT_REVOKED')
        return result(observation, initial['row']['state'], arguments['request_key'], False)
    except (WCEError, OSError, EOFError, ValueError, KeyError, TypeError) as error:
        if (case_id is not None and isinstance(error, WCEError)
                and error.code == 'LOCATOR_NOT_CONFIGURED'):
            return hold(case_id, 'LOCATOR_NOT_CONFIGURED')
        if case_id is None or evidence is None:
            if isinstance(error, WCEError): raise
            fail()
        reason = error.code if isinstance(error, WCEError) else 'LOCATOR_EVIDENCE_INVALID'
        if reason not in HOLD_REASONS: reason = 'LOCATOR_AUTHORIZATION_CHANGED' if reason.startswith(('OWN_', 'CONNECTION_')) else 'LOCATOR_EVIDENCE_INVALID'
        if context is not None:
            try:
                if not evidence.exists('complete.json') and not evidence.exists('stop.json'):
                    evidence.write('stop.json', {'schema': 1, 'case_id': case_id,
                        'attempt_id': context.attempt['attempt_id'], 'reason': reason, 'stopped_at': time.time()})
            except (WCEError, OSError): pass  # attempt itself remains an irrevocable spend.
        return hold(case_id, reason)
    finally:
        if context is not None: context.live = False; context.token = None; context.owner = None
        service.workflow.active_lease = None
        service.workflow.active_token = None
        service.serial.release()


from .draft_group_history_context import history_transaction as _history_transaction
