"""X v2 chunked media within the original account/attempt, no worker or retries.

4 MiB is a transport buffer, not a content quota. Original media is captured
without conversion in the account's existing private attempt directory. A
confirmed offset can continue; an UNKNOWN write cannot be silently replayed.
"""
from hashlib import sha256
from pathlib import Path
import math
import os
import time
import uuid

from .bounded_file import FileSource, file_state
from .contracts import WCEError
from .own_connection_policy import atomic_write
from .own_connection_policy import locked
from .x_api import XResponseUnknown, identifier

SEGMENT_BYTES=4*1024*1024  # below official 8 MB multipart maximum
TRANSFER_SECONDS=20  # cooperative call yield, never a file/duration quota
SIMPLE_IMAGE_BYTES = 5_000_000  # route larger inputs to the streaming endpoint


def media_type(head):
    if head.startswith(b'\x89PNG\r\n\x1a\n'):return 'image/png','tweet_image'
    if head.startswith(b'\xff\xd8\xff'):return 'image/jpeg','tweet_image'
    if head[:4] == b'RIFF' and head[8:12] == b'WEBP':return 'image/webp','tweet_image'
    if head.startswith((b'GIF87a',b'GIF89a')):return 'image/gif','tweet_gif'
    if len(head)>=12 and head[4:8]==b'ftyp':
        return ('video/quicktime'if head[8:12]==b'qt  'else 'video/mp4'),'tweet_video'
    if head.startswith(b'\x1aE\xdf\xa3'):return 'video/webm','tweet_video'
    if len(head)>376 and head[0]==head[188]==head[376]==0x47:return 'video/mp2t','tweet_video'
    # Legacy QuickTime without ftyp. Codec validity remains X's decision.
    if len(head)>=8 and head[4:8]in (b'moov',b'mdat',b'wide'):return 'video/quicktime','tweet_video'
    raise WCEError('X_IMAGE_TYPE_UNSUPPORTED') # preserve legacy unsupported-file error


def source_bytes(source):
    if not source.is_absolute():raise WCEError('X_IMAGE_PATH_INVALID')
    return FileSource(source.parent).iter_html(source.name)


def gif_category(artifact):
    """Distinguish one image frame from animation without decoding the pixels."""
    with artifact.open('rb') as source:
        header = source.read(13)
        if len(header) != 13:
            return 'tweet_gif'
        if header[10] & 0x80:
            source.seek(3 * (2 << (header[10] & 7)), os.SEEK_CUR)
        frames = 0
        while True:
            marker = source.read(1)
            if marker == b';':
                return 'tweet_image' if frames == 1 else 'tweet_gif'
            if marker == b',':
                frames += 1
                descriptor = source.read(9)
                if frames > 1 or len(descriptor) != 9:
                    return 'tweet_gif'
                if descriptor[8] & 0x80:
                    source.seek(3 * (2 << (descriptor[8] & 7)), os.SEEK_CUR)
                if not source.read(1):
                    return 'tweet_gif'
            elif marker != b'!' or not source.read(1):
                return 'tweet_gif'
            while length := source.read(1):
                if not length[0]:
                    break
                source.seek(length[0], os.SEEK_CUR)


def capture(x,path,source):
    """Atomically retain exact stable bytes; never overwrite an older capture."""
    artifact=path.with_suffix('.media')
    temporary=x.root/('.media-capture-'+uuid.uuid4().hex)
    fd=None
    try:
        original_pin = file_state(source.stat(follow_symlinks=False))
        digest=sha256();size=0;head=b''
        fd=os.open(temporary,os.O_CREAT|os.O_EXCL|os.O_WRONLY|os.O_NOFOLLOW,0o600)
        for chunk in FileSource(source.parent).iter_html(source.name, expected_state=original_pin):
            if len(head)<512:head=(head+chunk)[:512]
            digest.update(chunk);size+=len(chunk)
            view=memoryview(chunk)
            while view:
                written=os.write(fd,view)
                if written<=0:raise OSError('capture write failed')
                view=view[written:]
        os.fsync(fd);os.close(fd);fd=None
        mime,category=media_type(head)
        if mime == 'image/gif':
            category = gif_category(temporary)
        content={'sha256':digest.hexdigest(),'bytes':size}
        # All legitimate capture writers hold the existing connection.lock.
        # Atomic rename publishes complete bytes in one step; unlike link/unlink
        # it cannot strand nlink=2 after a crash. Never replace an existing input.
        if os.path.lexists(artifact):
            check=sha256();count=0
            for chunk in source_bytes(artifact):check.update(chunk);count+=len(chunk)
            if count!=size or check.hexdigest()!=content['sha256']:raise WCEError('X_ATTEMPT_CONFLICT')
        else:
            os.rename(temporary,artifact)
        if os.path.lexists(temporary):temporary.unlink()
        directory=os.open(x.root,os.O_RDONLY|os.O_DIRECTORY)
        try:os.fsync(directory)
        finally:os.close(directory)
        return content,mime,category,artifact,list(file_state(artifact.stat(follow_symlinks=False))),list(original_pin)
    finally:
        if fd is not None:os.close(fd)
        if os.path.lexists(temporary):temporary.unlink()


def save(path,row):
    atomic_write(path,row,maximum=None)
    return row


def error(row,exc):
    code=getattr(exc,'code','X_RESPONSE_UNKNOWN')
    row['error']=code if type(code)is str and (code.startswith('X_HTTP_')or code in {
        'X_MEDIA_RESPONSE_INCOMPLETE','X_MEDIA_IDENTITY_MISMATCH','X_INVALID_PLATFORM_ID',
        'LOCAL_FILE_CHANGED','INVALID_LOCAL_FILE','X_MEDIA_SEGMENT_INVALID'})else 'X_RESPONSE_UNKNOWN'
    if type(code)is str and code.startswith('X_HTTP_4') and code!='X_HTTP_408':row['state']='REJECTED'
    if isinstance(exc, XResponseUnknown):
        row['error_kind'] = exc.kind
    # UNKNOWN retains its in-flight phase; no new INIT/APPEND/FINALIZE.


def accept(x,row,value,*,ready=False):
    data=value.get('data')if type(value)is dict else None
    if type(data)is not dict:raise WCEError('X_MEDIA_RESPONSE_INCOMPLETE')
    known=row.get('result',{});result=dict(known)
    if 'id'in data:
        mid=identifier(data['id'])
        if known.get('media_id')not in (None,mid):raise WCEError('X_MEDIA_IDENTITY_MISMATCH')
        result['media_id']=mid
    if 'media_key'in data:
        key=data['media_key']
        if type(key)is not str or not key or known.get('media_key')not in (None,key):raise WCEError('X_MEDIA_IDENTITY_MISMATCH')
        result['media_key']=key
    if 'expires_after_secs'in data:
        ttl=data['expires_after_secs']
        if type(ttl)is not int or ttl<=0:raise WCEError('X_MEDIA_RESPONSE_INCOMPLETE')
        expiry=x.clock()+ttl
        if not math.isfinite(expiry):raise WCEError('X_MEDIA_RESPONSE_INCOMPLETE')
        result['expires_at']=expiry
    if not all(k in result for k in ('media_id','media_key','expires_at')):raise WCEError('X_MEDIA_RESPONSE_INCOMPLETE')
    processing=data.get('processing_info')
    if processing is not None:
        if type(processing)is not dict or processing.get('state')not in {'pending','in_progress','succeeded','failed'}:raise WCEError('X_MEDIA_RESPONSE_INCOMPLETE')
        state=processing['state'];row['processing_state']=state
        if state=='failed':row.update(state='REJECTED',phase='PROCESSING',error='X_MEDIA_PROCESSING_FAILED')
        elif state=='succeeded':row.update(state='SUCCEEDED',phase='READY');row.pop('error',None)
        else:
            delay=processing.get('check_after_secs',1)
            if type(delay)is not int or delay<0:raise WCEError('X_MEDIA_RESPONSE_INCOMPLETE')
            next_check=x.clock()+delay
            if not math.isfinite(next_check):raise WCEError('X_MEDIA_RESPONSE_INCOMPLETE')
            row.update(state='PROCESSING',phase='PROCESSING',next_check_at=next_check,check_after_secs=delay);row.pop('error',None)
    elif ready:
        row.update(state='SUCCEEDED',phase='READY');row.pop('error',None)
    row['result']=result
    row.pop('query_error',None)
    row.pop('query_error_kind',None)
    if 'error' not in row:
        row.pop('error_kind',None)


def poll(x,cid,path,row):
    """Optional GET of known processing only, never upload bytes or create post."""
    if row['state']in {'SUCCEEDED','REJECTED','EXPIRED'}:return row
    known=row.get('result',{})
    if not known.get('media_id')or row.get('phase')not in {'FINALIZE_UNKNOWN','PROCESSING'}:return row
    if known['expires_at']<=x.clock():return save(path,row|{'state':'EXPIRED','error':'X_MEDIA_EXPIRED'})
    if x.clock()<row.get('next_check_at',0):return row
    try:
        value=x.api.media_status(x._access(x._load(),cid,row),known['media_id'])
        # Missing processing_info cannot prove an unacknowledged FINALIZE was
        # accepted. Only explicit processing progress/terminal state reconciles.
        data=value.get('data')if type(value)is dict else None
        if type(data)is not dict or type(data.get('processing_info'))is not dict:raise WCEError('X_MEDIA_RESPONSE_INCOMPLETE')
        accept(x,row,value)
    except Exception as exc:
        # A failed GET is not a failed upload: retain the original phase/identity.
        row['query_error']=getattr(exc,'code','X_RESPONSE_UNKNOWN')if isinstance(exc,WCEError)else 'X_RESPONSE_UNKNOWN'
        row.pop('query_error_kind', None)
        if isinstance(exc, XResponseUnknown):
            row['query_error_kind'] = exc.kind
    return save(path,row)


def advance(x,cid,path,row,artifact):
    if row['state']in {'SUCCEEDED','REJECTED','EXPIRED','RESULT_UNKNOWN'}:
        return poll(x,cid,path,row)if row.get('phase')=='FINALIZE_UNKNOWN'else row
    if row['state']=='PROCESSING':return poll(x,cid,path,row)
    token=x._access(x._load(),cid,row)
    deadline=time.monotonic()+TRANSFER_SECONDS
    if row['phase']=='PREPARED':
        row.update(state='RESULT_UNKNOWN',phase='INIT_UNKNOWN');save(path,row)
        try:
            accept(x,row,x.api.media_initialize(token,row['input']['bytes'],row['media_type'],row['media_category']))
            row.update(state='UPLOADING',phase='APPENDING',confirmed_bytes=0,next_segment=0)
        except Exception as exc:error(row,exc);return save(path,row)
        save(path,row)
    if row['result']['expires_at']<=x.clock():return save(path,row|{'state':'EXPIRED','error':'X_MEDIA_EXPIRED'})
    stream=FileSource(artifact.parent).iter_html(artifact.name,expected_state=row['source_state'],offset=row['confirmed_bytes'])
    buffer=bytearray()
    try:
        while True:
            # Exhaust the stable source stream before FINALIZE; its final check
            # matters even when the last block exactly fills a segment.
            while len(buffer)<SEGMENT_BYTES:
                try:buffer.extend(next(stream))
                except StopIteration:break
            if not buffer:break
            chunk=bytes(buffer[:SEGMENT_BYTES]);del buffer[:SEGMENT_BYTES]
            index=row['next_segment']
            if index>9999:raise WCEError('X_MEDIA_SEGMENT_INVALID') # official protocol range
            row.update(state='RESULT_UNKNOWN',phase='APPEND_UNKNOWN');save(path,row)
            try:x.api.media_append(token,row['result']['media_id'],index,chunk)
            except Exception as exc:error(row,exc);return save(path,row)
            row.update(state='UPLOADING',phase='APPENDING',confirmed_bytes=row['confirmed_bytes']+len(chunk),next_segment=index+1)
            save(path,row)
            if time.monotonic()>=deadline:return row
    except Exception as exc:
        # Local file mismatch before send cannot be hidden as a platform reject.
        row.update(state='SOURCE_UNAVAILABLE',error=getattr(exc,'code','INVALID_LOCAL_FILE'));return save(path,row)
    finally:stream.close()
    try:
        for _ in FileSource(artifact.parent).iter_html(artifact.name,expected_state=row['source_state'],offset=row['input']['bytes']):pass
    except Exception as exc:
        return save(path,row|{'state':'SOURCE_UNAVAILABLE','error':getattr(exc,'code','INVALID_LOCAL_FILE')})
    if row['confirmed_bytes']!=row['input']['bytes']:return save(path,row|{'state':'SOURCE_UNAVAILABLE','error':'LOCAL_FILE_CHANGED'})
    row.update(state='RESULT_UNKNOWN',phase='FINALIZE_UNKNOWN');save(path,row)
    try:
        value=x.api.media_finalize(token,row['result']['media_id'])
        accept(x,row,value,ready=True)
    except Exception as exc:error(row,exc)
    return save(path,row)


def upload(x,cid,attempt_id,path):
    source=Path(path);x._connection(cid)
    # Keep the legacy simple image endpoint/fingerprint and UNKNOWN semantics.
    stream=source_bytes(source)
    try:
        first=next(stream);mime,category=media_type(first[:512])
        if category=='tweet_image':
            raw=bytearray(first)
            for chunk in stream:
                raw.extend(chunk)
                if len(raw) > SIMPLE_IMAGE_BYTES:
                    break
        else:
            raw=None
        if raw is not None and len(raw) <= SIMPLE_IMAGE_BYTES:
            raw=bytes(raw)
            content={'sha256':sha256(raw).hexdigest(),'bytes':len(raw)}
            def send(token):
                data=x.api.upload(token,raw)['data'];mid=identifier(data.get('id'))
                if type(data.get('media_key'))is not str or type(data.get('expires_after_secs'))is not int or data['expires_after_secs']<=0:raise WCEError('X_MEDIA_RESPONSE_INCOMPLETE')
                if data.get('processing_info')and data['processing_info'].get('state')!='succeeded':raise WCEError('X_MEDIA_PROCESSING_NOT_COMPLETE')
                return {'media_id':mid,'media_key':data['media_key'],'expires_at':x.clock()+data['expires_after_secs']}
            return x._write_once(cid,'upload',attempt_id,content,send)
    finally:stream.close()
    with locked(x.root/'connection.lock'):
        connection=x._connection(cid);receipt_path,old=x._receipt(cid,'upload',attempt_id)
        source_key = sha256(os.fsencode(source)).hexdigest()
        if (old and old.get('source_key') == source_key and
                old.get('original_source_state') == list(file_state(source.stat(follow_symlinks=False)))):
            return advance(x,cid,receipt_path,old,receipt_path.with_suffix('.media'))
        content,mime,category,artifact,pin,original_pin=capture(x,receipt_path,source)
        if old is not None:
            if old['fingerprint']!=x_fingerprint(content):raise WCEError('X_ATTEMPT_CONFLICT')
            if old.get('media_protocol')!='X_V2_CHUNKED':return old
            if old['media_type']!=mime or (old['media_category']!=category and mime!='image/gif'):
                raise WCEError('X_ATTEMPT_CONFLICT')
            row=old
        else:
            row={'connection_id':cid,'kind':'upload','attempt_id':attempt_id,'fingerprint':x_fingerprint(content),
                'state':'UPLOADING','created_at':x.clock(),'input':content,'media_protocol':'X_V2_CHUNKED',
                'phase':'PREPARED','media_type':mime,'media_category':category,'source_state':pin,
                'application_scope':connection['credential_scope']}
        row.update(source_key=source_key,original_source_state=original_pin)
        save(receipt_path,row)
        return advance(x,cid,receipt_path,row,artifact)


def x_fingerprint(content):
    # Exact legacy serialization, retained for old receipts and callers.
    from .x_platform import fingerprint
    return fingerprint(content)
