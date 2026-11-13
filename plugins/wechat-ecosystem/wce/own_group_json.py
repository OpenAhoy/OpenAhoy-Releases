"""Extra capacity only for strictly typed multi-article imported documents.

Legacy records keep their original reader budget. No decoding path confers
identity, approval or permission; callers still validate the stored object.
"""
import re
from copy import deepcopy
import os
from threading import get_ident

from . import prepared_draft_fixture as _decoded

from .contracts import WCEError
from .local_preparation import MAX_MANIFEST_BYTES
from .prepared_draft_fixture import decode_json
from .prepared_contracts import ID, DIGEST, strict_validate
from .service import canonical, digest
from .normal_html_limits import ROLE_POSITIONS

GROUP_BYTES = 512 * 1024
GROUP_NODES = 4096


def _manifest_fields(value, *, normal=False):
    from .documents import ASSET, SLOT
    binding = value['binding']
    identifiers = {'tenant', 'principal', 'client', 'session', 'connection', 'account', 'resource'}
    if set(binding) != identifiers | {'epoch', 'generation', 'source_kind'}:
        return False
    for key in identifiers:
        strict_validate(binding[key], ID)
    if (type(binding['epoch']) is not int or not 0 <= binding['epoch'] <= 2**63 - 1
            or type(binding['generation']) is not int or not 1 <= binding['generation'] <= 2**63 - 1
            or binding['source_kind'] not in ('SYNTHETIC_SETUP', 'OPERATOR_ATTESTED')):
        return False
    for asset in value['assets']:
        if type(asset) is not dict or set(asset) != {'asset_ref', 'role', 'declared_type', 'sha256', 'size', 'slot'}:
            return False
        strict_validate(asset['asset_ref'], ASSET)
        strict_validate(asset['slot'], {'type':'string','pattern':'^[A-Za-z0-9]{1,16}--[A-Za-z0-9_-]{1,32}$'} if normal else SLOT)
        strict_validate(asset['sha256'], DIGEST)
        if (asset['role'] not in ('cover', 'body') or asset['declared_type'] not in ('image/png', 'image/jpeg')
                or type(asset['size']) is not int or not 0 < asset['size'] <= 2097152):
            return False
    return True


def _group_document(document, normalized):
    from .html_document import DERIVED, normalize
    from .import_styles import POLICY
    if (type(document) is not dict or document.get('format') != 3
            or document.get('policy') != POLICY or type(document.get('articles')) is not list
            or not 2 <= len(document['articles']) <= 8):
        return False
    if any(type(a) is not dict or (not normalized and DERIVED & set(a)) for a in document['articles']):
        return False
    checked = normalize(document)
    return not normalized or checked == document


def _new_binding(binding):
    identifiers = {'tenant', 'principal', 'client', 'session', 'connection', 'account', 'resource'}
    if type(binding) is not dict or set(binding) != identifiers | {'epoch', 'generation', 'source_kind'}:
        return False
    for key in identifiers:
        strict_validate(binding[key], ID)
    return (type(binding['epoch']) is int and 0 <= binding['epoch'] <= 2**63 - 1
        and type(binding['generation']) is int and 1 <= binding['generation'] <= 2**63 - 1
        and binding['source_kind'] in ('SYNTHETIC_SETUP', 'OPERATOR_ATTESTED'))


def _snapshot(value, synthetic):
    """Exact existing _uploads mapping shapes, never a proof validator."""
    if type(value) is not dict:
        return False
    normal = {'id', 'intent_digest', 'target', 'result_digest'}
    recovery = {'source', 'recovery_id', 'original_step_id', 'intent_digest', 'result_digest'}
    followup = {'source', 'followup_id', 'original_step_id', 'original_row_digest',
        'prior_recovery_id', 'prior_recovery_digest', 'intent_digest', 'observation_digest', 'result_digest'}
    terminal = {'source', 'attempt_id', 'ordinal', 'original_step_id', 'history_digest',
        'intent_digest', 'observation_digest', 'result_digest'}
    replacement = {'source', 'replacement_id', 'case_id', 'original_step_id', 'original_step_sha',
        'original_intent_digest', 'original_result_digest', 'intent_digest', 'result_digest',
        'proof_sha256', 'approval_digest', 'batch_id', 'batch_digest',
        'unrelated_context_sha', 'unrelated_receipt_sha'}
    fields = set(value)
    if fields == normal:
        ids = {'id': 'own-step-'}
    elif fields == recovery and value['source'] == 'EXPLICIT_BODY_REPLACEMENT_RESPONSE':
        ids = {'recovery_id': 'own-body-recovery-', 'original_step_id': 'own-step-'}
    elif fields == followup and value['source'] == 'BODY_URL_RESPONSE_V1':
        ids = {'followup_id': 'own-body-followup-', 'original_step_id': 'own-step-',
               'prior_recovery_id': 'own-body-recovery-'}
    elif fields == terminal and value['source'] == 'FINAL_BODY_ATTEMPT4_REFERENCE_V2':
        if type(value['ordinal']) is not int or value['ordinal'] != 4:
            return False
        ids = {'attempt_id': 'own-body-attempt-', 'original_step_id': 'own-step-'}
    elif fields == replacement and value['source'] == 'EXPLICIT_LINEAGE_BODY_REPLACEMENT_RESPONSE_V1':
        ids = {'replacement_id': 'lineage-replacement-', 'original_step_id': 'own-step-',
               'batch_id': 'replacement-batch-'}
    else:
        return False
    for key, prefix in ids.items():
        if type(value[key]) is not str or re.fullmatch(prefix + '[a-f0-9]{32}', value[key]) is None:
            return False
    for key in fields - set(ids) - {'source', 'ordinal'}:
        if key == 'unrelated_receipt_sha' and value[key] is None and synthetic:
            continue
        strict_validate(value[key], DIGEST)
    return True


def _new_add_group_intent(value, *, normal=False):
    fields = {'schema', 'binding', 'profile_fence', 'selector', 'operation', 'slot', 'asset',
        'projection', 'uploads', 'approval_id', 'approval_digest', 'article_metadata'}
    if (set(value) != fields or type(value['schema']) is not int or value['schema'] != 2
            or value['operation'] != 'add' or value['slot'] != 'draft' or value['asset'] is not None
            or not _new_binding(value['binding'])):
        return False
    strict_validate(value['profile_fence'], DIGEST)
    strict_validate(value['approval_digest'], DIGEST)
    if type(value['approval_id']) is not str or re.fullmatch('own-approval-[a-f0-9]{32}', value['approval_id']) is None:
        return False
    selector = value['selector']
    if type(selector) is not dict or set(selector) != {'bundle_id', 'version', 'content_digest'}:
        return False
    for key, prefix in (('bundle_id', 'own-bundle-'), ('version', 'own-version-')):
        if type(selector[key]) is not str or re.fullmatch(prefix + '[a-f0-9]{32}', selector[key]) is None:
            return False
    strict_validate(selector['content_digest'], DIGEST)
    projected = value['projection']
    if (type(projected) is not dict or set(projected) != {'articles'}
            or type(projected['articles']) is not list or not (1 if normal else 2) <= len(projected['articles']) <= 8):
        return False
    from .own_draft_defaults import validate_defaults_metadata
    # Syntactic self-consistency for codec eligibility only; _step revalidates
    # this binding against its trusted historical profile and exact approval.
    checked = validate_defaults_metadata(value['article_metadata'],
        expected_binding_sha=digest(value['binding']), article_count=len(projected['articles']))
    from .own_draft_wire import reference_valid
    from .documents import safe_url
    from .editor_contracts import crop_info
    synthetic = value['binding']['source_kind'] == 'SYNTHETIC_SETUP'
    required = {'article_type', 'title', 'content', 'thumb_media_id', 'author', 'digest',
        'content_source_url', 'need_open_comment', 'only_fans_can_comment'}
    for row in projected['articles']:
        if (type(row) is not dict or set(row) not in (required, required | {'cover_info'})
                or row['article_type'] != 'news'
                or any(type(row[k]) is not str for k in required - {'need_open_comment', 'only_fans_can_comment'})
                or not row['title'].strip() or len(row['title']) > 32
                or not row['content'] or len(row['content']) >= 20000 or len(row['content'].encode()) >= 1000000
                or len(row['author']) > 16 or (len(row['digest'])>120 if normal and len(projected['articles'])==1 else row['digest'] != '')
                or len(row['content_source_url']) > 1024
                or not reference_valid(row['thumb_media_id'], synthetic)
                or any(type(row[k]) is not int or row[k] != v for k, v in checked.comment_settings.items())):
            return False
        if row['content_source_url']:
            safe_url(row['content_source_url'])
        if 'cover_info' in row:
            crop_info(row['cover_info'])
    return (type(value['uploads']) is list and len(projected['articles']) <= len(value['uploads']) <= (ROLE_POSITIONS*8 if normal else 48)
        and all(_snapshot(item, synthetic) for item in value['uploads'])
        and len({item.get('id', item.get('original_step_id')) for item in value['uploads']}) == len(value['uploads']))


def normal_limit(value):
    """Closed normal HTML envelopes; syntactic eligibility never authority."""
    from .normal_html_limits import POLICY, ENVELOPE_BYTES, ROLE_POSITIONS
    if type(value) is not dict:return None
    fields=set(value)
    def document(doc,normalized):
        from .html_document import DERIVED,normalize
        if (type(doc) is not dict or doc.get('format')!=3 or doc.get('policy')!=POLICY
                or type(doc.get('articles')) is not list or not 1<=len(doc['articles'])<=8):return False
        if any(type(a) is not dict or (not normalized and DERIVED&set(a)) for a in doc['articles']):return False
        checked=normalize(doc)
        return not normalized or checked==doc
    if fields in ({'document'},{'document','bundle_id','expected_version'}):
        if 'bundle_id' in value:
            strict_validate(value['bundle_id'],{'type':'string','pattern':'^own-bundle-[a-f0-9]{32}$'})
            strict_validate(value['expected_version'],{'type':'string','pattern':'^own-version-[a-f0-9]{32}$'})
        return ENVELOPE_BYTES if document(value['document'],False) else None
    if (fields=={'schema','binding','bundle_id','version','revision','document','assets'}
            and type(value['schema']) is int and value['schema']==3
            and type(value['revision']) is int and value['revision']>=1
            and type(value['assets']) is list and 1<=len(value['assets'])<=8*ROLE_POSITIONS
            and _manifest_fields(value,normal=True) and document(value['document'],True)):
        strict_validate(value['bundle_id'],{'type':'string','pattern':'^own-bundle-[a-f0-9]{32}$'})
        strict_validate(value['version'],{'type':'string','pattern':'^own-version-[a-f0-9]{32}$'})
        return ENVELOPE_BYTES
    if value.get('normal_html_policy')!=POLICY:return None
    bare={k:v for k,v in value.items() if k!='normal_html_policy'}
    if 'operation' in bare:
        return ENVELOPE_BYTES if _new_add_group_intent(bare,normal=True) else None
    base={'schema','binding','fence','bundle_id','version','content_digest','slots','apis','expires'}
    if (set(bare) not in (base,base|{'delegated'}) or type(bare['schema']) is not int
            or bare['schema']!=(7 if 'delegated' in bare else 1) or not _new_binding(bare['binding'])
            or type(bare['slots']) is not list or not 1<=len(bare['slots'])<=8*ROLE_POSITIONS
            or not _manifest_fields({'binding':bare['binding'],'assets':bare['slots']},normal=True)):return None
    from .own_auth import APIS,finite
    if bare['apis']!=list(APIS) or not finite(bare['expires']):return None
    for key in ('fence','content_digest'):strict_validate(bare[key],DIGEST)
    for key,prefix in (('bundle_id','own-bundle-'),('version','own-version-')):
        strict_validate(bare[key],{'type':'string','pattern':'^'+prefix+'[a-f0-9]{32}$'})
    if 'delegated' in bare:
        from .prepared_contracts import schema
        from .upload_wire import BODY_API_REFERENCE_POLICY,COVER_RESPONSE_POLICY
        from .own_lineage import POLICY as LINEAGE_POLICY
        d=bare['delegated'];required={'schema','policy','lineage','lineage_digest','response_policy','cover_response_policy'}
        if type(d) is not dict or set(d) not in (required,required|{'article_metadata'}):return None
        if type(d['schema']) is not int or d['schema']!=(3 if 'article_metadata' in d else 2):return None
        if d['response_policy']!=BODY_API_REFERENCE_POLICY or d['cover_response_policy']!=COVER_RESPONSE_POLICY:return None
        strict_validate(d['policy'],schema({'id':ID,'revision':{'type':'integer','minimum':1},'policy_digest':DIGEST,'candidate_scope':DIGEST}))
        strict_validate(d['lineage'],schema({'lineage':DIGEST,'root_version':{'type':'string','pattern':'^own-version-[a-f0-9]{32}$'},
            'normalization_policy':{'type':'string','const':LINEAGE_POLICY},'legacy':{'type':'integer','const':0},'tenant':ID,'resource':ID}))
        strict_validate(d['lineage_digest'],DIGEST)
        if digest(d['lineage'])!=d['lineage_digest']:return None
        if 'article_metadata' in d:
            from .own_draft_defaults import validate_defaults_metadata
            meta=d['article_metadata']
            validate_defaults_metadata(meta,expected_binding_sha=digest(bare['binding']),article_count=meta.get('article_count') if type(meta) is dict else 0)
    return ENVELOPE_BYTES


def limit(value):
    """The larger envelope is not available to arbitrary legacy JSON shapes."""
    if type(value) is not dict:
        return MAX_MANIFEST_BYTES
    try:
        normal = normal_limit(value)
        if normal is not None:return normal
        fields = set(value)
        if fields == {'schema', 'binding', 'profile_fence', 'selector', 'operation', 'slot', 'asset',
                'projection', 'uploads', 'approval_id', 'approval_digest', 'article_metadata'} and _new_add_group_intent(value):
            return GROUP_BYTES
        if fields in ({'document'}, {'document', 'bundle_id', 'expected_version'}):
            if 'bundle_id' in value:
                if (type(value['bundle_id']) is not str or not re.fullmatch(r'own-bundle-[a-f0-9]{32}', value['bundle_id'])
                        or type(value['expected_version']) is not str
                        or not re.fullmatch(r'own-version-[a-f0-9]{32}', value['expected_version'])):
                    return MAX_MANIFEST_BYTES
            if _group_document(value['document'], False):
                return GROUP_BYTES
        if (fields == {'schema', 'binding', 'bundle_id', 'version', 'revision', 'document', 'assets'}
                and type(value['schema']) is int and value['schema'] == 3
                and type(value['binding']) is dict and type(value['revision']) is int and value['revision'] >= 1
                and type(value['bundle_id']) is str and re.fullmatch(r'own-bundle-[a-f0-9]{32}', value['bundle_id'])
                and type(value['version']) is str and re.fullmatch(r'own-version-[a-f0-9]{32}', value['version'])
                and type(value['assets']) is list and 1 <= len(value['assets']) <= 48
                and _manifest_fields(value)
                and _group_document(value['document'], True)):
            return GROUP_BYTES
    except (WCEError, ValueError, TypeError, KeyError):
        pass
    return MAX_MANIFEST_BYTES


def _read_full(raw, fingerprint, maximum=None):
    """Preserve original canonical bytes/hash; never repair data while reading."""
    try:
        data = raw.encode('utf-8')
        if maximum is not None:
            value = decode_json(data, maximum)
        else:
            try:
                value = decode_json(data, MAX_MANIFEST_BYTES)
            except WCEError:
                value = decode_json(data, GROUP_BYTES, max_nodes=GROUP_NODES)
                if limit(value) != GROUP_BYTES:
                    raise ValueError()
        if canonical(value) != raw or digest(value) != fingerprint:
            raise ValueError()
        return value
    except Exception:
        raise WCEError('OWN_STATE_CORRUPT') from None



def _read_normal_or_original(raw,fingerprint,maximum=None):
    # The frozen legacy reader body and all its explicit-maximum semantics stay
    # unchanged. Only a closed new-policy record gets the separate fallback.
    try:return _read_full(raw,fingerprint,maximum)
    except WCEError:
        if maximum is not None:raise
    try:
        from .normal_html_limits import ENVELOPE_BYTES,ENVELOPE_NODES
        data=raw.encode('utf-8');value=decode_json(data,ENVELOPE_BYTES,max_nodes=ENVELOPE_NODES)
        if normal_limit(value)!=ENVELOPE_BYTES or canonical(value)!=raw or digest(value)!=fingerprint:
            raise ValueError()
        return value
    except Exception:
        raise WCEError('OWN_STATE_CORRUPT') from None


def read(raw, fingerprint, maximum=None):
    """Reuse only successful pure codec results in the existing request pool.

    Exact UTF8 is a bijection of the eligible exact str input. Fingerprint,
    maximum and its type remain separate parts of the namespaced cache key.
    No SQL/source/current/approval/proof result is stored by this codec leaf.
    """
    memo = _decoded._DECODE_CURRENT.get()
    eligible = (memo is not None and memo.active and memo.pid == os.getpid()
        and memo.thread == get_ident() and type(raw) is str
        and type(fingerprint) is str and (maximum is None
            or type(maximum) is int and maximum > 0))
    if not eligible:
        return _read_normal_or_original(raw, fingerprint, maximum)
    try:
        data = raw.encode('utf-8')
        key = (data, fingerprint, maximum, type(maximum), 'own_group_json.read.v1')
        entry = memo.entries.get(key)
        if entry is not None:
            result = deepcopy(entry[0])
            memo.entries.move_to_end(key)
            return result
    except Exception:
        # Cache/key/copy faults do not replace the original codec semantics.
        memo.clear()
        return _read_normal_or_original(raw, fingerprint, maximum)
    value = _read_normal_or_original(raw, fingerprint, maximum)
    # Canonical equality already proved this exact serialized size. The pool
    # accounts the raw key, retained result and separate fingerprint together.
    try:
        memo.remember(key, value, serialized_size=len(data), extra_size=len(fingerprint.encode('utf-8')))
    except Exception:
        memo.clear()
    return value
