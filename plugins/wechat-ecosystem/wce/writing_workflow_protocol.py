"""Model refinements and app-only selection of the installed writing-method data."""
from copy import deepcopy

from .content_templates_protocol import READ as TEMPLATES
from .own_connection_policy import registry_path
from .own_production_rules_protocol import READ as PREFERENCES
from .prepared_contracts import strict_validate
from .service import digest
from .tools import schema
from .writing_workflow import METHODS, WritingStore, pin, require, verify_text

MODEL = 'own.writing.polish'
UI = 'wce.ui.writing.rules'
S = {'type': 'string'}
ID = S | {'pattern': '^[A-Za-z0-9][A-Za-z0-9._-]{0,95}$'}
SHA = S | {'pattern': '^[a-f0-9]{64}$'}
PIN = schema({'version': S, 'manifest_sha256': SHA})
SCOPE = {
    'kind': S | {'enum': ['wechat', 'text']},
    'connection_id': S | {'maxLength': 128},
}


def choices(action, branches):
    return {'oneOf': [schema({action: S | {'const': mode}} | fields, optional)
                      for mode, fields, optional in branches]}


def items(spec, maximum):
    return {'type': 'array', 'items': spec, 'maxItems': maximum}


GENRES = {
    'article': '按段落主旨去重，保留作者的节奏、措辞和原有叙述视角。',
    'paper': '核对术语、引文、数字、单位和限定范围，保持结论强度。证据冲突保留原句并提示作者。',
    'copy': '围绕原文明确的读者、利益和行动润色。保留条件及限制，不添加承诺。',
}
GENRE = S | {'enum': list(GENRES)}
BODY = S | {'maxLength': 262_144, 'minLength': 1}
SPECS = {
    MODEL: choices('action', (
        ('context', SCOPE | {'genre': GENRE}, {}),
        ('reopen', SCOPE | {'draft_id': ID}, {}),
        ('save', SCOPE | {'draft_id': ID, 'genre': GENRE, 'rules': PIN, 'basis_sha256': SHA,
                          'original': BODY, 'revised': BODY},
         {'protected': items(S, 150), 'author_sample_sha256': items(SHA, 2),
          'author_notes': items(S | {'maxLength': 2048}, 10)}),
    )),
    UI: choices('action', (
        ('state', {}, {}),
        ('install', {'expected': PIN, 'package_text': S | {'maxLength': 16_384}}, {}),
        ('activate', {'expected': PIN, 'reference': PIN}, {}),
    )),
}


def descriptors():
    descriptions = {
        MODEL: ('公众号和普通文字的写作编辑',
                'Polish existing article, paper or copy. Load the method and scoped preference/template pins, '
                'save the original and finished revision, or reopen a saved local draft by ID. '
                'Keep quotations, numbers and protected text. No platform calls or permissions.'),
        UI: ('写作规则版本', 'App-only import of writing-method data and explicit selection of an installed version.'),
    }
    return [{'name': name, 'title': descriptions[name][0], 'description': descriptions[name][1],
             'inputSchema': deepcopy(spec), 'outputSchema': {'type': 'object'},
             'annotations': {'readOnlyHint': False, 'destructiveHint': False,
                             'idempotentHint': True, 'openWorldHint': False},
             '_meta': {'ui': {'visibility': ['model'] if name == MODEL else ['app']}}}
            for name, spec in SPECS.items()]


class WritingRouter:
    def __init__(self, inner, registry=None):
        self.inner = inner
        self.writing = WritingStore(registry if registry is not None else registry_path())

    def __getattr__(self, name):
        return getattr(self.inner, name)

    @property
    def _inline_probe_meta(self):
        return self.inner._inline_probe_meta

    @_inline_probe_meta.setter
    def _inline_probe_meta(self, value):
        self.inner._inline_probe_meta = value

    def list_tools(self):
        return self.inner.list_tools() + descriptors()

    def owner(self, kind, connection_id):
        if kind == 'text':
            require(connection_id == '')
            return {'kind': kind}
        row = next((row for row in self.inner.call('own.connections.list', {})['connections']
                    if row['connection_id'] == connection_id), None)
        require(row and row.get('account_id'), 'WRITING_ACCOUNT_NOT_FOUND')
        return {'kind': kind, 'connection_id': connection_id, 'account_id': row['account_id']}

    def basis(self, owner, rule, genre):
        require(owner['kind'] != 'wechat' or genre == 'article')
        preferences, templates = None, []
        if owner['kind'] == 'wechat':
            cid = owner['connection_id']
            scope = {'connection_id': cid, 'scope': 'account', 'view': 'effective'}
            before = self.inner.call(PREFERENCES, scope)
            templates = self.inner.call(TEMPLATES, {'view': 'selected', 'connection_id': cid})['templates']
            after = self.inner.call(PREFERENCES, scope)
            require(before == after and self.owner('wechat', cid) == owner, 'WRITING_CONTEXT_CHANGED')
            preferences = {field: before[field] for field in
                           ('global_revision', 'scope_revision', 'effective_sha256')}
        return {'owner': owner, 'genre': genre, 'rules': pin(rule), 'preferences': preferences, 'templates': templates}

    def call(self, name, args):
        if name not in SPECS:
            return self.inner.call(name, args)
        strict_validate(args, SPECS[name])
        action = args['action']
        if name == UI:
            if action == 'state':
                return self.writing.state()
            if action == 'activate':
                return self.writing.change(args['expected'], reference=args['reference'])
            return self.writing.change(args['expected'], package_text=args['package_text'])

        owner = self.owner(args['kind'], args['connection_id'])
        if action == 'context':
            rule = self.writing.active()
            basis = self.basis(owner, rule, args['genre'])
            return {'state': 'WRITING_CONTEXT', 'basis': basis, 'basis_sha256': digest(basis),
                    'methods': [METHODS[code] for code in rule['methods']], 'genre_method': GENRES[args['genre']],
                    'genre_note': rule['genre_notes'].get(args['genre'], '')}
        stored = self.writing.read_draft(owner, args['draft_id'])
        if action == 'reopen':
            require(stored is not None, 'WRITING_DRAFT_NOT_FOUND')
            self.writing.rules(stored['record']['basis']['rules'])
            return {'state': 'WRITING_REOPENED', **stored}
        request_sha = digest(args)
        if stored is not None:
            require(stored['request_sha256'] == request_sha, 'WRITING_DRAFT_CONFLICT')
            return {'state': 'WRITING_SAVED', **stored}
        rule = self.writing.rules(args['rules'])
        basis = self.basis(owner, rule, args['genre'])
        require(digest(basis) == args['basis_sha256'], 'WRITING_CONTEXT_CHANGED')
        original, revised = args['original'], args['revised']
        protected = args.get('protected', [])
        verify_text(original, revised, protected, args['genre'])
        result = {'basis': basis, 'original': original, 'revised': revised, 'protected': protected,
                  'outcome': 'UNCHANGED' if original == revised else 'POLISHED',
                  'author_sample_sha256': args.get('author_sample_sha256', []),
                  'author_notes': args.get('author_notes', [])}
        stored = self.writing.save_draft(owner, args['draft_id'], request_sha, result)
        return {'state': 'WRITING_SAVED', **stored}
