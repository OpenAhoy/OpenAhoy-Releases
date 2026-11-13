"""Pure closed DRAFT_DEFAULTS_V1 metadata and exact projection transformation.

Only new schema2 intent callers may opt in. No account, preferences, database,
network, declaration, moderation or approval operation is performed here.
"""
from dataclasses import dataclass
from hashlib import sha256
import json
import re

from .contracts import WCEError

POLICY = 'DRAFT_DEFAULTS_V1'
SOURCE_KIND = 'FIXED_PRODUCT_DEFAULT_V1'
COMMENT_FIELDS = ('need_open_comment', 'only_fans_can_comment')


def _values():
    return {'comment_settings': {'need_open_comment': 1, 'only_fans_can_comment': 0},
            'originality_intent': 'review_required', 'auto_feature_intent': 'review_required'}


def _digest(value):
    return sha256(json.dumps(value, ensure_ascii=False, sort_keys=True,
                             separators=(',', ':'), allow_nan=False).encode('utf-8')).hexdigest()


VALUES_SHA = _digest(_values())


@dataclass(frozen=True)
class ValidatedDefaults:
    article_count: int
    binding_sha: str
    values_sha: str

    @property
    def comment_settings(self):
        return dict(_values()['comment_settings'])


def _fail(code='OWN_DRAFT_DEFAULTS_INVALID'):
    raise WCEError(code)


def _hash(value):
    return type(value) is str and re.fullmatch(r'[a-f0-9]{64}', value) is not None


def _count(value):
    return type(value) is int and 1 <= value <= 8


def validate_defaults_metadata(value, *, expected_binding_sha, article_count):
    """Validate against the caller's trusted live binding and actual count.

    expected_binding_sha must come from digest(p.binding()), not a model input.
    This schema=1 is metadata's version, never an instruction to reinterpret a
    legacy intent schema1. SQL/history routing remains the caller's boundary.
    """
    if not _hash(expected_binding_sha) or not _count(article_count):
        _fail()
    if (type(value) is not dict or set(value) != {
            'schema', 'policy', 'article_count', 'comment_settings',
            'originality_intent', 'auto_feature_intent', 'defaults_source'}
            or type(value['schema']) is not int or value['schema'] != 1
            or type(value['policy']) is not str or value['policy'] != POLICY
            or not _count(value['article_count']) or value['article_count'] != article_count):
        _fail()
    settings = value['comment_settings']
    if (type(settings) is not dict or set(settings) != set(COMMENT_FIELDS)
            or any(type(settings[key]) is not int for key in COMMENT_FIELDS)
            or settings != _values()['comment_settings']
            or type(value['originality_intent']) is not str
            or value['originality_intent'] != 'review_required'
            or type(value['auto_feature_intent']) is not str
            or value['auto_feature_intent'] != 'review_required'):
        _fail()
    source = value['defaults_source']
    if (type(source) is not dict or set(source) != {'kind', 'binding_sha', 'revision', 'values_sha'}
            or type(source['kind']) is not str or source['kind'] != SOURCE_KIND
            or not _hash(source['binding_sha']) or source['binding_sha'] != expected_binding_sha
            or type(source['revision']) is not int or source['revision'] != 0
            or not _hash(source['values_sha'])
            or source['values_sha'] != _digest({key: value[key] for key in _values()})
            or source['values_sha'] != VALUES_SHA):
        _fail()
    return ValidatedDefaults(article_count, source['binding_sha'], source['values_sha'])


def apply_comment_settings(old_projection, validated_metadata):
    """Return a detached projection; reject every existing comment field.

    Ordered article ordinals are their original zero-based list positions.
    Nothing is sorted, renumbered, inferred, merged or overwritten.
    """
    if (type(validated_metadata) is not ValidatedDefaults
            or not _count(validated_metadata.article_count)
            or not _hash(validated_metadata.binding_sha)
            or type(validated_metadata.values_sha) is not str
            or validated_metadata.values_sha != VALUES_SHA):
        _fail()
    if type(old_projection) is not dict:
        _fail('OWN_DRAFT_DEFAULTS_PROJECTION')
    single_fields = {'title', 'content', 'thumb_media_id'}
    grouped = set(old_projection) == {'articles'}
    if grouped:
        rows = old_projection['articles']
        if type(rows) is not list or not _count(len(rows)):
            _fail('OWN_DRAFT_DEFAULTS_PROJECTION')
    elif set(old_projection) == single_fields:
        rows = [old_projection]
    else:
        _fail('OWN_DRAFT_DEFAULTS_PROJECTION')
    if len(rows) != validated_metadata.article_count:
        _fail('OWN_DRAFT_DEFAULTS_PROJECTION')
    output = []
    for row in rows:
        required = single_fields | ({'article_type', 'author', 'digest', 'content_source_url'} if grouped else set())
        if (type(row) is not dict or not required <= set(row)
                or set(row) - required - ({'cover_info'} if grouped else set())
                or any(type(row[key]) is not str for key in required)
                or (grouped and row['article_type'] != 'news')):
            _fail('OWN_DRAFT_DEFAULTS_PROJECTION')
        # Existing same-value fields are rejected too; no silent replay/merge.
        if any(key in row for key in COMMENT_FIELDS):
            _fail('OWN_DRAFT_DEFAULTS_PROJECTION')
        copied = {key: row[key] for key in required}
        if 'cover_info' in row:
            from .editor_contracts import crop_info
            crop_info(row['cover_info'])
            copied['cover_info'] = {'crop_percent_list': [dict(crop) for crop in row['cover_info']['crop_percent_list']]}
        output.append(copied | validated_metadata.comment_settings)
    return {'articles': output} if grouped else output[0]
