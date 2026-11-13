"""Complete fixed target-slot commitments, not source/QA or upload authority."""
from .draft_group_input_files import (_plain,_closed,_binding,_id,_hash,_int,
    _enum,_selector,_seq,_maybe,hold,MAX_TOP)
from .own_response_archive import _FIELDS
from .own_group_json import _snapshot
from .service import digest

PROFILE='GROUP_TARGET_UPLOAD_REUSE_MAP_V1'


def _asset(v):
    _closed(v,('asset_ref','role','declared_type','sha256','size','slot'))
    _id(v['asset_ref']);_id(v['slot']);_hash(v['sha256'])
    _enum(v['role'],('cover','body'));_enum(v['declared_type'],('image/png','image/jpeg'))
    _int(v['size'],1,2*1024*1024)


def _pin(v):
    _closed(v,_FIELDS)
    for k in _FIELDS:
        if k=='created':
            # Keep the real SQL REAL domain, not bool/int-wide equality.
            import math
            if type(v[k]) is not float or not math.isfinite(v[k]) or v[k]<0:hold()
        elif k in ('manifest_digest','target','approval_digest','intent_digest'):_hash(v[k])
        else:_id(v[k])
    _enum(v['operation'],('cover','body','add'))


def _proof(v):
    _closed(v,('sha256','size'));_hash(v['sha256']);_int(v['size'],1,MAX_TOP)


def _member(v):
    _closed(v,('article_id','version_sha','source_manifest_selector','source_asset_slot','source_asset_ref','member_evidence_sha'))
    for k in ('article_id','source_asset_slot','source_asset_ref'):_id(v[k])
    for k in ('version_sha','member_evidence_sha'):_hash(v[k])
    _selector(v['source_manifest_selector'])


def _save(v):
    _closed(v,('selector','step_pin','result_digest','archive_sha','original_position','article_id','projection_sha'))
    _selector(v['selector']);_pin(v['step_pin']);_int(v['original_position'],0,7);_id(v['article_id'])
    for k in ('result_digest','archive_sha','projection_sha'):_hash(v[k])
    if v['step_pin']['operation']!='add' or v['step_pin']['slot']!='draft' or v['step_pin']['manifest_digest']!=v['selector']['content_digest']:hold()


def _upload(v,synthetic):
    _closed(v,('selector','slot','operation','asset','base_step_pin','snapshot','result_digest','proof_files'))
    _selector(v['selector']);_id(v['slot']);_enum(v['operation'],('cover','body'))
    _asset(v['asset']);_pin(v['base_step_pin']);_hash(v['result_digest'])
    # _plain ran before any old snapshot equality or type checks.
    if not _snapshot(v['snapshot'],synthetic):hold()
    _seq(v['proof_files'],_proof,hi=16)
    if v['proof_files']!=sorted(v['proof_files'],key=lambda p:(p['sha256'],p['size'])):hold()
    pin=v['base_step_pin'];snap=v['snapshot']
    if (v['slot']!=v['asset']['slot'] or pin['slot']!=v['slot']
        or pin['operation']!=v['operation'] or pin['manifest_digest']!=v['selector']['content_digest']
        or (v['operation']=='cover')!=(v['asset']['role']=='cover')
        or snap['result_digest']!=v['result_digest']):hold()
    if 'id' in snap:
        if any(snap[k]!=pin[k] for k in ('id','intent_digest','target')):hold()
    elif snap['original_step_id']!=pin['id']:hold()


def validate_map(value):
    """Exact builtin structure only; all live/history proof checks are separate."""
    _plain(value)
    _closed(value,('schema','profile','authority','binding','operation_id','target_selector','target_manifest_sha','entries'))
    if type(value['schema']) is not int or value['schema']!=1 or type(value['profile']) is not str or value['profile']!=PROFILE or value['authority'] is not False:hold()
    _binding(value['binding']);_id(value['operation_id']);_selector(value['target_selector']);_hash(value['target_manifest_sha'])
    if value['target_manifest_sha']!=value['target_selector']['content_digest']:hold()
    if type(value['entries']) is not list or not 1<=len(value['entries'])<=48:hold()
    seen=set();synthetic=value['binding']['source_kind']=='SYNTHETIC_SETUP'
    for entry in value['entries']:
        _closed(entry,('target_slot','target_asset','source_member','original_upload','source_save','transmission'))
        _id(entry['target_slot']);_asset(entry['target_asset']);_member(entry['source_member'])
        _upload(entry['original_upload'],synthetic);_maybe(entry['source_save'],_save)
        _enum(entry['transmission'],('NONE_REUSE_VERIFIED_SUCCESS',))
        slot=entry['target_slot'];target=entry['target_asset'];upload=entry['original_upload'];source=upload['asset'];member=entry['source_member']
        if slot in seen or slot!=target['slot']:hold()
        seen.add(slot)
        if any(target[k]!=source[k] for k in ('asset_ref','role','declared_type','sha256','size')):hold()
        if member['source_asset_slot']!=source['slot'] or member['source_asset_ref']!=source['asset_ref']:hold()
        if entry['source_save'] is not None and entry['source_save']['article_id']!=member['article_id']:hold()
        pin=upload['base_step_pin']
        if any(pin[k]!=value['binding'][k] for k in ('tenant','principal','connection','resource')):hold()
        expected_target=digest({'tenant':value['binding']['tenant'],'resource':value['binding']['resource'],
            'manifest_digest':upload['selector']['content_digest'],'operation':upload['operation'],'slot':upload['slot']})
        if pin['target']!=expected_target:hold()
        saved=entry['source_save']
        if saved is not None:
            save_pin=saved['step_pin']
            if any(save_pin[k]!=value['binding'][k] for k in ('tenant','principal','connection','resource')):hold()
            if save_pin['target']!=digest({'tenant':value['binding']['tenant'],'resource':value['binding']['resource'],
                'manifest_digest':saved['selector']['content_digest'],'operation':'add','slot':'draft'}):hold()
    return None
