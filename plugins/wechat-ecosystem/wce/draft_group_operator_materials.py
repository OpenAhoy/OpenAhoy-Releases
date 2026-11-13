"""Closed Operator material containers; detached facts, never W1/W2 or QA."""
from . import draft_group_operator_source_codec as codec

QA_SET_PROFILE = 'GROUP_OPERATOR_CURRENT_QA_SET_V1'
PREPARED_PROFILE = 'GROUP_OPERATOR_PREPARED_RELATION_INVENTORY_V1'
MAPPING_PROFILE = 'GROUP_OPERATOR_POSTUPLOAD_MAPPING_V1'
QA_KEYS = ('schema','profile','authority','selection_ref','artifact_roots_ref',
           'member_projection_ref','dossier_ref','acceptance_ref','binding_projection_sha256')
COMMON = ('schema','profile','authority','content_source_type','operator_request_identity_sha',
          'original_request_set_sha','account_partition_sha','selection_sha256','rows')
PREPARED_ROW = ('selected_article_id','source_article_id','prepare_request_key','selector','prepared_relation_sha256')
MAPPING_ROW = ('selected_article_id','member_identity','report_artifact_sha','upload_mapping_sha')


def _header(value, profile, keys):
    codec._closed(value, keys)
    codec._need(type(value['schema']) is int and value['schema'] == 1
                and value['profile'] == profile and value['authority'] is False)


def detached(value):
    import json
    return json.loads(codec.canonical(value))


def qa_set(value):
    _header(value, QA_SET_PROFILE, QA_KEYS)
    for key in QA_KEYS:
        if key.endswith('_ref'):codec._ref(value[key])
    codec._sha(value['binding_projection_sha256'])
    return detached(value)


def evidence_ref(value):
    """Explicit old evidence-byte unit conversion; source ref is unchanged."""
    codec._ref(value)
    return {'path':value['path'],'sha256':value['sha256'],'bytes':value['size']}


def projection(value):
    codec._closed(value, ('member_projection',))
    rows=value['member_projection']
    codec._need(type(rows) is list and len(rows)==28)
    for row in rows:
        codec._need(type(row) is list and len(row)==3)
        codec._id(row[0]);codec._sha(row[1]);codec._sha(row[2])
    codec._need(len({row[0] for row in rows})==28)
    return detached(value)


def qa_binding_projection(binding,source,container):
    """Acyclic actual data scope for new Group A, no runtime permission claim."""
    codec.validate_binding(binding)
    q=qa_set(container)
    result={'schema':1,'profile':'GROUP_OPERATOR_QA_BINDING_PROJECTION_V1',
        'authority':False,'binding':detached(binding)}
    for key in ('original_queue_sha','operator_request_identity_sha',
                'original_request_set_sha','account_partition_sha'):
        codec._sha(source[key]);result[key]=source[key]
    for key in ('selection_ref','artifact_roots_ref','member_projection_ref','dossier_ref'):
        result[key]=q[key]
    return detached(result)


def qa_binding_projection_sha(binding,source,container):
    return codec.digest(qa_binding_projection(binding,source,container))


def _rows(value, profile, source, row_keys):
    _header(value, profile, COMMON)
    codec._need(value['content_source_type']==codec.CONTENT_SOURCE_TYPE)
    for key in ('operator_request_identity_sha','original_request_set_sha','account_partition_sha'):
        codec._need(value[key]==source[key]);codec._sha(value[key])
    codec._need(value['selection_sha256']==source['selection_ref']['sha256'])
    rows=value['rows']
    codec._need(type(rows) is list and 1<=len(rows)<=28)
    for row in rows:
        codec._closed(row,row_keys);codec._id(row['selected_article_id'])
    codec._need(len({row['selected_article_id'] for row in rows})==len(rows))
    return rows


def prepared_relations(value, source):
    rows=_rows(value,PREPARED_PROFILE,source,PREPARED_ROW)
    for row in rows:
        codec._id(row['source_article_id'])
        codec._id(row['prepare_request_key']);codec._sha(row['prepared_relation_sha256'])
        codec._closed(row['selector'],('bundle_id','version','content_digest'))
        codec._id(row['selector']['bundle_id']);codec._id(row['selector']['version'])
        codec._sha(row['selector']['content_digest'])
    return detached(value)


def postupload_mapping(value, source):
    rows=_rows(value,MAPPING_PROFILE,source,MAPPING_ROW)
    for row in rows:
        codec._closed(row['member_identity'],('article_id','original_request_sha'))
        codec._id(row['member_identity']['article_id']);codec._sha(row['member_identity']['original_request_sha'])
        codec._sha(row['report_artifact_sha']);codec._sha(row['upload_mapping_sha'])
    codec._need(len({(row['member_identity']['article_id'],row['member_identity']['original_request_sha'])
                     for row in rows})==len(rows))
    return detached(value)


def partition_rows(selection, semantic, source, relations, mapping):
    """Exact ordered account partition; full 28 QA selection stays separate."""
    expected=semantic['semantic_scope']['authorized_member_ids']
    codec._need(type(expected) is list and bool(expected))
    current_sha=codec.digest(semantic['binding'])
    members=[row for row in selection['members'] if row['binding_sha256']==current_sha]
    prepared=prepared_relations(relations,source)['rows']
    mapped=postupload_mapping(mapping,source)['rows']
    codec._need([row['article_id'] for row in members]==expected
        ==[row['selected_article_id'] for row in prepared]
        ==[row['selected_article_id'] for row in mapped])
    for member,relation in zip(members,prepared):
        codec._need(member['prepare_request_key']==relation['prepare_request_key']
                    and member['selector']==relation['selector'])
    return detached(members),detached(prepared),detached(mapped)
