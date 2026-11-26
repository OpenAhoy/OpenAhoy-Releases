"""Model-facing argument shapes for multi-operation tools.

These descriptors give the host action choices and supported field shapes.
The routers still validate the original, closed action-specific schemas before
dispatch. No validation or permission decisions use the projected descriptors.
"""

from collections import defaultdict
import json


BRANCH_TOOLS = frozenset({
    'audio.project.presets',
    'own.documents.prepare',
    'own.music.production',
    'own.publications.current.dispatch',
    'own.publications.current.poll',
    'own.publications.current.status',
    'own.wechat.authorized_drafts',
    'own.projects.read',
    'own.schedules.update',
    'own.sources.library',
    'own.templates.read',
    'own.writing.polish',
    'own.wechat.content',
    'video.director.edit',
    'video.director.read',
    'video.minimax.generation.submit',
    'video.relay.generation.submit',
    'x.posts.create',
})
NESTED_ACTION_FIELDS = {
    'audio.project.mix': 'timeline',
    'own.articles.prepare': 'article',
    'video.ark.generation.submit': 'configuration',
    'video.tokenhex.generation.submit': 'configuration',
}


def _merge_shapes(rules):
    first = rules[0]
    if all(rule == first for rule in rules) and len(json.dumps(first)) <= 190:
        return first

    if all(rule.get('type') == 'string' and
           ('const' in rule or 'enum' in rule) for rule in rules):
        choices = dict.fromkeys(item for rule in rules
                                for item in (rule.get('enum') or [rule.get('const')]))
        return {'type': 'string', 'enum': list(choices)}

    kinds = {rule.get('type') for rule in rules if isinstance(rule.get('type'), str)}
    if any(not isinstance(rule.get('type'), str) for rule in rules):
        return {}
    if len(kinds) != 1:
        return {'anyOf': [{'type': kind} for kind in sorted(kinds)]}

    kind = next(iter(kinds))
    if kind == 'array':
        items = [rule.get('items', {}) for rule in rules]
        return {'type': 'array', 'items': _merge_shapes(items) if all(
            isinstance(item, dict) for item in items) else {}}
    return {'type': kind}


def model_input_schema(name, schema):
    if name == 'own.production.rules.update':
        # Move the shared text limit out of each repeated field description.
        # Exact text limits and account revisions remain enforced by the router.
        changes = schema['properties']['changes']
        outlined = dict(changes, properties={
            name: {key: value for key, value in rule.items() if key != 'description'}
            for name, rule in changes['properties'].items()
        })
        return dict(schema, properties=dict(schema['properties'], changes=outlined))
    if name == 'own.music.production':
        # Reuse each unique field shape once. Keep the nested settings, clips,
        # stems and song window that a model needs to build the exact request.
        outline = _action_shape(schema['oneOf'])
        for field in ('suno_settings', 'clips', 'stems', 'window'):
            rule = next(branch['properties'][field] for branch in schema['oneOf']
                        if field in branch['properties'])
            outline['properties'][field] = rule
        return outline
    if name == 'x.connections.list':
        # Retain the read-only operation allowlist and each accepted argument
        # name. The router keeps the exact operation-to-arguments relationship.
        recovery = schema['properties']['recovery']
        outline = _action_shape(recovery['oneOf'])
        outline['properties']['arguments'] = _action_shape(
            [branch['properties']['arguments'] for branch in recovery['oneOf']])
        return dict(schema, properties=dict(schema['properties'], recovery=outline))
    if name in NESTED_ACTION_FIELDS:
        field = NESTED_ACTION_FIELDS[name]
        rule = schema['properties'][field]
        outline = dict(rule, properties={key: _merge_shapes([value])
                                        for key, value in rule['properties'].items()})
        return dict(schema, properties=dict(schema['properties'], **{field: outline}))
    if name not in BRANCH_TOOLS:
        return schema
    outline = _action_shape(schema['oneOf'])
    if name == 'video.relay.generation.submit':
        # The actual director model list is authoritative for workflow-specific
        # parameters. Keep the names and types here, and validate on dispatch.
        for field in ('workflow_id', 'resolution', 'style_preset'):
            outline['properties'][field] = {'type': 'string'}
    return outline


def _action_shape(alternatives):
    fields = defaultdict(list)
    required = set(alternatives[0].get('required', ()))
    for alternative in alternatives:
        required.intersection_update(alternative.get('required', ()))
        for key, rule in alternative['properties'].items():
            fields[key].append(rule)
    return {'type': 'object', 'properties': {key: _merge_shapes(rules) for key, rules in fields.items()},
            'required': sorted(required), 'additionalProperties': False}


MODEL_DESCRIPTIONS = {
    'audio.music.provider.read': 'Read default music provider.',
    'audio.project.cover_video': 'Make video from song and cover.',
    'audio.project.history': 'List songs and soundtracks.',
    'audio.project.import': 'Import authorized audio. Keep originals.',
    'audio.project.mix': 'Mix audio into video. Units: ms, %.',
    'audio.project.presets': 'Edit .jmusic recipes and shot pins.',
    'audio.project.video.inspect': 'Inspect video and media samples.',
    'image.openai.gif.configuration.status': 'Read GIF key status only.',
    'image.openai.gif.status': 'Read original GIF receipt and file.',
    'image.openai.gif.submit': 'Authorized billable GIF. Query original on UNKNOWN.',
    'media.library.prepare': 'Prepare media for selected account.',
    'openahoy.feedback.preview': 'Preview redacted feedback locally.',
    'openahoy.feedback.status': 'Read original feedback status.',
    'openahoy.feedback.submit': 'Explicitly authorized public feedback only. Reuse preview; query UNKNOWN.',
    'own.drafts.current.delete': 'Delete authorized drafts by exact selection.',
    'own.drafts.current.merge': 'Merge up to 8 selected drafts. Recover original handle.',
    'own.drafts.current.read': 'Read drafts by selection or media ID.',
    'own.drafts.current.resume': 'Read original draft receipt. Never resend UNKNOWN.',
    'own.drafts.current.status': 'Read original local draft receipt.',
    'own.drafts.inventory': 'List drafts with read access.',
    'own.music.production': 'Manage song takes and clip archives. Free Suno downloads only. Reuse request key.',
    'own.production.rules.read': 'Read rules, text and chunk manifests.',
    'own.production.rules.update': 'Edit fields with both revisions. Max 8192 chars/32768 B. Repeat identical args after UNKNOWN.',
    'own.projects.initialize': 'Initialize authorized project AGENTS and Skill pins.',
    'own.projects.read': 'Read project/Skill pins. Builtin source permits empty project_id.',
    'own.projects.sync': 'Index authorized project and Skills.',
    'own.schedules.read': 'Read account schedules.',
    'own.schedules.update': 'Record the real automation_update receipt for the original task and account.',
    'own.sources.library': 'Manage scoped sources and draft links.',
    'own.templates.read': 'Read template manifest and pins.',
    'own.wechat.authorized_drafts': 'Read authorized account drafts and publications.',
    'own.wechat.content': 'Manage WeChat content. Notifications need separate authorization.',
    'own.writing.polish': 'Read or revise writing by original ID. Preserve cited facts.',
    'video.ark.connection.status': 'Read local Ark key status.',
    'video.ark.generation.status': 'Query original Ark or relay task.',
    'video.ark.generation.submit': 'Authorized billable Seedance task. Recover original attempt.',
    'video.director.edit': 'Edit exact project/work/shot/article with revision guards.',
    'video.director.generation.submit': 'Authorized billable shot task. Recover original attempt.',
    'video.director.read': 'Read project, shots, models or exact receipts.',
    'video.minimax.generation.submit': 'Authorized billable MiniMax task. Query original attempt.',
    'video.relay.generation.submit': 'Authorized billable AutoDL. Read director models first. Query UNKNOWN.',
    'video.tokenhex.connection.check': 'List models visible to local Token Hex.',
    'video.tokenhex.generation.submit': 'Authorized billable Token Hex task. Recover original attempt.',
    'wce.ui.show_management': 'Read management status.',
    'x.articles.draft.create': 'Create authorized X Article draft with ordered same-account media.',
    'x.articles.publish': 'Publish authorized X Article by original attempt.',
    'x.articles.status': 'Read original X Article receipt or post.',
    'x.attempt.status': 'Read original X receipt. Poll known media.',
    'x.connections.list': 'List X accounts or recover original allowed reads.',
    'x.media.upload': 'Upload authorized same-account media. Query UNKNOWN.',
    'x.posts.context': 'Read exact X post context.',
    'x.posts.create': 'Publish authorized X post with ready media. Never resend UNKNOWN.',
    'x.posts.list': 'Page account posts. Preserve PARTIAL, continue with new token.',
    'x.posts.read': 'Read exact X post. Keep verified partial data.',
    'x.posts.readback': 'GET original post; verify text and ordered media.',
    'x.posts.reply': 'Send authorized reply to exact X parent.',
    'x.posts.search': 'Search using selected X account.',
    'x.profile.read': 'Read bound X profile.',
    'x.replies.readback': 'Verify original reply or reconcile from its timeline. Never resend.',
    'x.setup.draft.submit': 'Stage public X OAuth client ID and app name only. No secrets or binding changes.',
    'x.users.lookup': 'Look up exact X username and ID.',
    'xhs.attempt.status': 'Read original Xiaohongshu attempt.',
    'xhs.connections.list': 'List Xiaohongshu bindings.',
    'xhs.notes.list': 'List own notes and completeness.',
    'xhs.notes.publish': 'Publish authorized note with ordered images. Never resend UNKNOWN.',
    'xhs.notes.read': 'Read exact own note with canonical URL.',
    'xhs.notes.readback': 'Verify the original note independently.',
    'xhs.profile.read': 'Read bound profile. QR needs the user.',
    'own.articles.read': 'Read original account article.',
    'own.articles.status': 'Read original article status.',
    'own.assets.status': 'Read original asset status.',
    'own.connections.list': 'List WeChat connections.',
    'own.connections.status': 'Read selected connection status.',
    'own.documents.preview': 'Preview original document locally.',
    'own.drafts.locate': 'Locate original account drafts.',
    'own.drafts.readback': 'Read back original account draft.',
    'own.drafts.status': 'Read original draft status.',
    'own.editor.preferences.read': 'Read account writing preferences.',
    'own.preflight': 'Check original account and inputs.',
    'own.uploads.status': 'Read original upload status.',
}
