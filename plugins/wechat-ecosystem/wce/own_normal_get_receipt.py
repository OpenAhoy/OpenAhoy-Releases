"""Small facts from the same successful normal GET, never publication authority.

No caller parameter, database migration, additional query or transport occurs.
The first parsed read of one original ADD is immutable, including UNVERIFIED.
"""
from hashlib import sha256
import inspect
import os
import re
import stat

from .contracts import WCEError
from .bounded_file import file_state,identity
from .own_bootstrap_security import decode,path_check
from .service import canonical,digest

PROFILE='NORMAL_DRAFT_GET_OBSERVED_V1'
MAX_BYTES=16384
_HASH=re.compile(r'[a-f0-9]{64}\Z')
_STEP=re.compile(r'own-step-[a-f0-9]{32}\Z')
_OWNER=re.compile(r'[a-f0-9]{32}\Z')
_FIELDS={'schema','profile','authority','provenance','binding_sha256','original','selector',
         'normal_get_observed','readback_state','diagnostic','response_sha256','platform_representation'}
_ORIGINAL={'step_id','owner','intent_digest','result_digest','manifest_digest','request_key_sha256','reference_sha256'}
_REP={'profile','state','platform_representation_match','byte_exact','expected_projection_sha256',
      'actual_projection_sha256','actual_response_sha256'}


def _need(value):
    if value is not True:raise WCEError('NORMAL_GET_RECEIPT_UNAVAILABLE')


def filename(step_id):
    _need(type(step_id)is str and _STEP.fullmatch(step_id)is not None)
    return 'draft-normal-get-'+step_id+'.json'


def _original(row,intent,result):
    _need(row['operation']=='add' and row['state']=='SUCCEEDED'
        and digest(intent)==row['intent_digest'] and digest(result)==row['result_digest']
        and type(intent.get('selector'))is dict and type(result.get('reference'))is str)
    _need(type(row['id'])is str and _STEP.fullmatch(row['id'])is not None
        and type(row['owner'])is str and _OWNER.fullmatch(row['owner'])is not None)
    return {'step_id':row['id'],'owner':row['owner'],'intent_digest':row['intent_digest'],
        'result_digest':row['result_digest'],'manifest_digest':row['manifest_digest'],
        'request_key_sha256':digest(row['request_key']),'reference_sha256':digest(result['reference'])}


def _validate(value):
    _need(type(value)is dict and set(value)==_FIELDS and type(value['schema'])is int and value['schema']==1
        and value['profile']==PROFILE and value['authority']is False and value['normal_get_observed']is True
        and value['provenance']in('OWN_OFFICIAL_WIRE','SYNTHETIC_OWN_WIRE')
        and value['readback_state']in('MATCHED','UNVERIFIED'))
    original=value['original'];selector=value['selector'];diagnostic=value['diagnostic'];representation=value['platform_representation']
    _need(type(original)is dict and set(original)==_ORIGINAL
        and type(original['step_id'])is str and _STEP.fullmatch(original['step_id'])is not None
        and type(original['owner'])is str and _OWNER.fullmatch(original['owner'])is not None
        and all(type(original[k])is str and _HASH.fullmatch(original[k])is not None for k in _ORIGINAL-{'step_id','owner'})
        and type(selector)is dict and set(selector)=={'bundle_id','version','content_digest'}
        and all(type(v)is str for v in selector.values())
        and type(diagnostic)is dict and set(diagnostic)=={'reason','http_status','wechat_code'}
        and diagnostic=={'reason':'PARSED_SUCCESS','http_status':200,'wechat_code':None}
        and all(type(value[k])is str and _HASH.fullmatch(value[k])is not None for k in ('binding_sha256','response_sha256')))
    from .prepared_contracts import ID,DIGEST,strict_validate
    for k in ('bundle_id','version'):strict_validate(selector[k],ID)
    strict_validate(selector['content_digest'],DIGEST)
    if representation is not None:
        _need(type(representation)is dict and set(representation)==_REP
            and representation['profile']=='ORDINARY_DRAFT_PLATFORM_REPRESENTATION_V1'
            and representation['state']in('UNVERIFIED','PLATFORM_REPRESENTATION_MATCHED')
            and type(representation['platform_representation_match'])is bool and type(representation['byte_exact'])is bool
            and all(type(representation[k])is str and _HASH.fullmatch(representation[k])is not None
                    for k in _REP-{'profile','state','platform_representation_match','byte_exact'})
            and representation['actual_response_sha256']==value['response_sha256'])
    _need(len((canonical(value)+'\n').encode())<=MAX_BYTES)
    return value


def _read(root,name,expected_root):
    _need(path_check(root,True)==expected_root)
    directory=os.open(root,os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW)
    try:
        _need(identity(os.fstat(directory))==expected_root)
        fd=os.open(name,os.O_RDONLY|os.O_NOFOLLOW|os.O_NONBLOCK,dir_fd=directory)
        try:
            before=os.fstat(fd)
            _need(stat.S_ISREG(before.st_mode) and before.st_uid==os.getuid()
                and stat.S_IMODE(before.st_mode)==0o600 and before.st_nlink==1 and 0<before.st_size<=MAX_BYTES)
            raw=bytearray()
            while len(raw)<=MAX_BYTES:
                part=os.read(fd,min(65536,MAX_BYTES+1-len(raw)))
                if not part:break
                raw.extend(part)
            _need(len(raw)==before.st_size and file_state(before)==file_state(os.fstat(fd))
                and file_state(before)==file_state(os.stat(name,dir_fd=directory,follow_symlinks=False)))
        finally:os.close(fd)
        _need(path_check(root,True)==expected_root)
    finally:os.close(directory)
    raw=bytes(raw);value=_validate(decode(raw,MAX_BYTES))
    _need(raw==(canonical(value)+'\n').encode())
    return value,sha256(raw).hexdigest()


def load(workflow,profile,row,intent,result):
    """Read one fixed original-step fact, not a Source or a current permit."""
    root=workflow.db.path.parent;name=filename(row['id'])
    try:
        value,checksum=_read(root,name,workflow.state_root_identity)
        # Re-establish durability after an earlier file/directory fsync outcome
        # was unknown. No new platform GET is needed for this local fact.
        directory=os.open(root,os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW)
        try:
            _need(identity(os.fstat(directory))==workflow.state_root_identity)
            fd=os.open(name,os.O_RDONLY|os.O_NOFOLLOW|os.O_NONBLOCK,dir_fd=directory)
            try:
                before=os.fstat(fd)
                _need(stat.S_ISREG(before.st_mode) and before.st_uid==os.getuid()
                    and stat.S_IMODE(before.st_mode)==0o600 and before.st_nlink==1)
                os.fsync(fd)
                _need(file_state(before)==file_state(os.fstat(fd))
                    and file_state(before)==file_state(os.stat(name,dir_fd=directory,follow_symlinks=False)))
            finally:os.close(fd)
            os.fsync(directory)
        finally:os.close(directory)
        _need(_read(root,name,workflow.state_root_identity)==(value,checksum))
    except (OSError,ValueError,TypeError,KeyError,UnicodeError):
        raise WCEError('NORMAL_GET_RECEIPT_UNAVAILABLE') from None
    _need(value['binding_sha256']==digest(profile.binding()) and value['original']==_original(row,intent,result)
        and value['selector']==intent['selector']
        and value['provenance']==('SYNTHETIC_OWN_WIRE'if profile.source_kind=='SYNTHETIC_SETUP'else'OWN_OFFICIAL_WIRE'))
    return value,checksum


def record(workflow,profile,lease,row,intent,result,output,response,parsed):
    """Called only by the real normal parser frame, between existing guards."""
    from .own_workflow import OwnWorkflow
    from .own_connection_workflow import PersistentWorkflow
    from .http_transport import HTTPResponse
    frame=inspect.currentframe();caller=frame.f_back
    try:
        _need(type(workflow)is PersistentWorkflow and caller.f_code is OwnWorkflow._readback.__code__
            and caller.f_locals.get('self')is workflow and caller.f_locals.get('p')is profile
            and caller.f_locals.get('lease')is lease and caller.f_locals.get('row')is row
            and caller.f_locals.get('intent')is intent and caller.f_locals.get('result')is result
            and caller.f_locals.get('output')is output and caller.f_locals.get('response')is response
            and getattr(caller.f_locals.get('reply'),'result',None)is parsed)
    finally:del caller,frame
    # Original profile/version/current and writer checks stay OUTSIDE receipt
    # I/O failure handling. The original final _readback_guard follows this call.
    from .publication_lock import _writer_guard
    writer_current=_writer_guard(workflow.db.path.parent,profile.account_id)
    diagnostic=output.get('readback_diagnostic',{})
    if (type(response)is not HTTPResponse or response.status!=200 or type(parsed)is not dict
            or diagnostic.get('reason')!='PARSED_SUCCESS'):
        writer_current()
        return {'normal_get_receipt_state':'UNAVAILABLE','normal_get_receipt_reason':'NO_PARSED_SUCCESS'}
    from .own_draft_wire import reference_valid
    _need(reference_valid(result.get('reference'),profile.source_kind=='SYNTHETIC_SETUP'))
    _need((type(parsed.get('articles'))is list and 1<=len(parsed['articles'])<=8
           and all(type(article)is dict for article in parsed['articles']))
          if 'articles'in intent['projection'] else
          {'title','content','thumb_media_id'}<=set(parsed))
    try:
        representation=output.get('platform_representation')
        value={'schema':1,'profile':PROFILE,'authority':False,
            'provenance':'SYNTHETIC_OWN_WIRE'if profile.source_kind=='SYNTHETIC_SETUP'else'OWN_OFFICIAL_WIRE',
            'binding_sha256':digest(profile.binding()),'original':_original(row,intent,result),
            'selector':dict(intent['selector']),'normal_get_observed':True,'readback_state':output['readback_state'],
            'diagnostic':{k:diagnostic[k]for k in ('reason','http_status','wechat_code')},
            'response_sha256':sha256(response.body).hexdigest(),
            'platform_representation':({k:representation[k]for k in _REP}if representation is not None else None)}
        _validate(value)
        name=filename(row['id'])
        from .own_draft_reconcile import write_once
        try:
            checksum=write_once(workflow.db.path.parent,name,value,expected_root=workflow.state_root_identity)
            state='RECORDED'
        except WCEError as error:
            if error.code!='OWN_DRAFT_RECONCILE_ATTEMPT_SPENT':raise
            _,checksum=load(workflow,profile,row,intent,result);state='EXISTING'
        outcome={'normal_get_receipt_state':state,'normal_get_receipt_sha256':checksum}
    except (WCEError,OSError,ValueError,TypeError,KeyError,UnicodeError):
        outcome={'normal_get_receipt_state':'UNAVAILABLE','normal_get_receipt_reason':'RECEIPT_STORAGE_UNVERIFIED'}
    writer_current()
    return outcome
