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
    return _action_shape(schema['oneOf'])


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
    'audio.music.provider.read': 'Read the saved music provider. An explicit provider wins; otherwise use the saved default.',
    'audio.project.cover_video': 'Create a local video from the selected project song and cover image.',
    'audio.project.import': 'Import one authorized local audio asset into the registered project; retain the original.',
    'audio.project.mix': 'Mix existing project audio into a new local video. Times and fades are ms; gain is percent.',
    'audio.project.presets': 'Read or edit local .jmusic recipes and pin candidates to exact shots. No generation.',
    'audio.project.video.inspect': 'Read video facts and optional frame/audio samples from the current project.',
    'image.openai.gif.submit': 'Submit one authorized billable GIF task from a project image. Query the original attempt on uncertainty.',
    'media.library.prepare': 'Prepare existing project media for the selected account. Does not publish.',
    'own.drafts.current.delete': 'Delete only explicitly authorized current WeChat drafts by exact selection.',
    'own.drafts.current.merge': 'Merge selected current WeChat drafts in inventory order, up to eight articles. Recover UNKNOWN by original handle.',
    'own.drafts.current.read': 'Read complete existing WeChat drafts by inventory selection or media ID.',
    'own.drafts.current.resume': 'Read the original current-draft operation receipt. Never reissue an unknown write.',
    'own.production.rules.read': 'Read non-secret production rules, manifests, and pinned chunks. Rules confer no API authority.',
    'own.projects.initialize': 'Initialize an authorized project with current AGENTS and bridge Skill hashes. Preserve existing text.',
    'own.projects.read': 'Read scoped project/AGENTS/Skill pins and effective settings or resume the exact operation.',
    'own.projects.sync': 'Index authorized project and selected Skills. Does not edit source or accounts.',
    'own.schedules.read': 'Read existing Codex publishing schedule references for one connection.',
    'own.schedules.update': 'Record the actual Codex automation_update receipt for the exact original task and account. Retain UNKNOWN.',
    'own.sources.library': 'Manage scoped public sources and preserve exact references used in each topic or draft.',
    'own.templates.read': 'Read the scoped template manifest, materials and pinned chunks before use.',
    'own.wechat.content': 'Official WeChat materials, drafts, publication and preview. Broadcasts require separate authorization.',
    'own.writing.polish': 'Read polish rules, save a revision, or reopen the exact original. Preserve citations and protected facts.',
    'video.ark.generation.status': 'Read or recover the exact original Ark or relay task; never submit another generation.',
    'video.ark.generation.submit': 'Submit one authorized billable Seedance task by exact attempt. Use supported project images and model options.',
    'video.director.edit': 'Edit an exact project, work, shot or article revision. Use action and original IDs; honor current revision guards.',
    'video.director.generation.submit': 'Submit one authorized billable generation from the exact saved shot revision. Recover the original attempt.',
    'video.director.read': 'Read project, story, shot, article, model options or exact receipt. Preflight does not generate.',
    'video.minimax.generation.submit': 'Submit one authorized billable MiniMax task. Respect provider site and exact source mode. Query the original attempt.',
    'video.relay.generation.submit': 'Submit one authorized billable AutoDL attempt. Read video.director.read action=models for exact workflow and input roles.',
    'video.tokenhex.generation.submit': 'Submit one authorized billable Token Hex Seedance task. Recover the original attempt.',
    'wce.ui.show_management': 'Read management status for the current binding.',
    'x.articles.draft.create': 'Create one authorized X Article draft with ordered blocks and same-account upload receipts.',
    'x.articles.publish': 'Publish one authorized X Article draft using its exact original attempt.',
    'x.articles.status': 'Read the original X Article receipt. Optional readback verifies the known post.',
    'x.attempt.status': 'Read an original X upload, post or reply receipt. poll_media queries known media only.',
    'x.connections.list': 'List bound X accounts. Optional recovery permits only the listed original read operations.',
    'x.media.upload': 'Upload one authorized same-account image, GIF or video from image_path. Resume the original attempt on uncertainty.',
    'x.posts.context': 'Read the exact X post and requested context for this account.',
    'x.posts.create': 'Publish authorized X text with optional ready same-account media. Never repeat an unknown attempt.',
    'x.posts.readback': 'Independently GET the original X post and compare text and ordered media.',
    'x.posts.reply': 'Send one authorized reply to the exact X parent. Follow platform mention, quote and automation restrictions.',
    'x.posts.search': 'Search X posts under the selected account and its actual read permissions.',
    'xhs.notes.publish': 'Publish one authorized image-text note through Creator Studio. Retain ordered images and original ID; never repeat UNKNOWN.',
    'xhs.notes.readback': 'Verify the original known Xiaohongshu note independently. Never submits.',
}
