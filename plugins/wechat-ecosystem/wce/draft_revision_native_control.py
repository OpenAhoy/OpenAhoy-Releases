"""Bounded projection of current native USER and task-control provenance.

Not a raw-history export, PrefixRead, permission interpreter or QA source. The
generic 64 MiB retained-segment reader and fresh-child verifier are unchanged.
"""
from dataclasses import dataclass,field
from hashlib import sha256
import io
import os
import re
import stat

from .draft_revision_native_source import (SourceHold,RegisteredSource,Record,MAX_PREFIX,MAX_LINE,MAX_RECORDS,
    canonical,strict_json,require,checked_guard,registration_digest,_open_source,
    _regular,_metadata_origin,_first_line)

MAX_USER_REFS=1024
MAX_PROJECTION=2*1024*1024
_SEAL=object()
_UUID=re.compile('[a-f0-9]{8}(?:-[a-f0-9]{4}){3}-[a-f0-9]{12}')


def _uuid(value):
    require(type(value) is str and _UUID.fullmatch(value) is not None,'CONTROL_NATIVE_ID')


@dataclass(frozen=True)
class UserExpectation:
    turn_id:str
    message_id:str
    text_sha256:str


@dataclass(frozen=True)
class NativeControlSnapshot:
    source:RegisteredSource=field(repr=False)
    canonical_bytes:bytes=field(repr=False)
    human_events:tuple=field(repr=False)
    _seal:object=field(repr=False)

    def __post_init__(self):require(self._seal is _SEAL,'CONTROL_UNCHECKED_SOURCE')
    @property
    def value(self):return strict_json(self.canonical_bytes,maximum=MAX_PROJECTION)
    @property
    def sha256(self):return sha256(self.canonical_bytes).hexdigest()


class _BoundedFile(io.RawIOBase):
    def __init__(self,fd,size,guard):self.fd=fd;self.remaining=size;self.guard=guard
    def readable(self):return True
    def readinto(self,buffer):
        if not self.remaining:return 0
        checked_guard(self.guard)
        value=os.read(self.fd,min(len(buffer),self.remaining))
        require(bool(value),'CONTROL_SOURCE_TRUNCATED')
        buffer[:len(value)]=value;self.remaining-=len(value)
        checked_guard(self.guard)
        return len(value)


def _project(fd,end,source,expectations,guard):
    os.lseek(fd,0,os.SEEK_SET)
    header=None;full=sha256();offset=0;count=0;users=[];pinned={};typed_ids=set();pinned_ids=set();latest=None
    wanted={e.message_id:e for e in expectations}
    # The bounded raw reader never prefetches bytes after captured N. One raw
    # line and its bounded parsed object are transient; no raw USER is retained.
    with io.BufferedReader(_BoundedFile(fd,end,guard),buffer_size=65536) as reader:
        while offset<end:
            checked_guard(guard)
            line=reader.readline(MAX_LINE+1)
            require(bool(line) and line.endswith(b'\n') and len(line)<=MAX_LINE,'CONTROL_LINE_LIMIT')
            value=strict_json(line,maximum=MAX_LINE)
            ordinal=source.metadata_ordinal+count
            require(ordinal<MAX_RECORDS and type(value) is dict
                and type(value.get('ordinal')) is int and value['ordinal']==ordinal
                and type(value.get('type')) is str and type(value.get('payload')) is dict,
                'CONTROL_RECORD_INVALID')
            record=Record(source.source_id,ordinal,offset,offset+len(line),sha256(line).hexdigest(),line)
            ref=record.reference();data=value['payload'];outer=value['type']
            if count==0:
                require(outer=='session_meta' and data.get('id')==source.thread_id
                    and record.raw_line_sha256==source.session_meta_sha256,'CONTROL_META_CHANGED')
                _metadata_origin(value,source);header=ref
            else:require(outer!='session_meta','CONTROL_DUPLICATE_METADATA')
            if outer=='event_msg':
                kind=data.get('type');item=data.get('item',{})
                if kind=='item_completed' and type(item) is dict and item.get('id') in wanted:
                    ident=item['id']
                    require(ident not in pinned_ids and item.get('type')=='UserMessage',
                        'CONTROL_PINNED_USER_NOT_UNIQUE')
                    pinned_ids.add(ident)
                if kind=='task_started':
                    turn=data.get('turn_id');_uuid(turn)
                    if 'thread_id' in data:require(data['thread_id']==source.thread_id,'CONTROL_TASK_THREAD')
                    latest={'turn_id':turn,'started':ref,'terminal':None}
                elif kind in ('task_complete','turn_aborted','task_aborted') and latest is not None:
                    latest['terminal']=ref
                elif kind=='user_message':
                    users.append({'kind':'USER_CONTROL','message_id':None,'turn_id':None,'record':ref})
                elif kind=='item_completed' and item.get('type')=='UserMessage':
                    ident=item.get('id');turn=data.get('turn_id');_uuid(ident);_uuid(turn)
                    require(data.get('thread_id')==source.thread_id and ident not in typed_ids,
                        'CONTROL_USER_NOT_UNIQUE')
                    typed_ids.add(ident)
                    users.append({'kind':'TYPED_USER','message_id':ident,'turn_id':turn,'record':ref})
                    if ident in wanted:
                        expected=wanted[ident];content=item.get('content')
                        require(turn==expected.turn_id and type(content) is list and len(content)==1
                            and type(content[0]) is dict and set(content[0])=={'type','text','text_elements'}
                            and content[0]['type']=='text' and type(content[0]['text']) is str
                            and type(content[0]['text_elements']) is list,'CONTROL_USER_SHAPE')
                        text_sha=sha256(content[0]['text'].encode()).hexdigest()
                        require(text_sha==expected.text_sha256,'CONTROL_USER_TEXT_CHANGED')
                        pinned[ident]={'turn_id':turn,'message_sha256':text_sha,'record':ref}
            if outer=='response_item' and data.get('type')=='message' and data.get('role')=='user':
                users.append({'kind':'RAW_USER','message_id':None,'turn_id':None,'record':ref})
            require(len(users)<=MAX_USER_REFS,'CONTROL_USER_LIMIT')
            full.update(line);offset+=len(line);count+=1
            # Drop all content, including selected text, before the next line.
            del record,value,data,line
            item=None;content=None;expected=None
    require(offset==end and count>0 and header is not None,'CONTROL_PREFIX_INVALID')
    require(set(pinned)==set(wanted),'CONTROL_PINNED_USER_MISSING')
    return full.hexdigest(),count,header,users,pinned,latest


def scan_current_control(source,expectations,guard):
    require(type(source) is RegisteredSource and source.start_offset==0
        and source.start_ordinal==source.metadata_ordinal
        and source.preceding_sha256==sha256(b'').hexdigest()
        and type(source.metadata_ordinal) is int and 0<=source.metadata_ordinal<MAX_RECORDS
        and all(type(v) is str and re.fullmatch('[A-Za-z0-9_-]{1,128}',v)
            for v in (source.source_id,source.thread_id))
        and type(source.session_meta_sha256) is str
        and re.fullmatch('[a-f0-9]{64}',source.session_meta_sha256), 'CONTROL_BOOTSTRAP_REGISTRATION')
    require(type(expectations) is tuple and len(expectations)<=4
        and all(type(e) is UserExpectation for e in expectations),'CONTROL_EXPECTATIONS_REQUIRED')
    for expected in expectations:
        _uuid(expected.turn_id);_uuid(expected.message_id)
        require(type(expected.text_sha256) is str and re.fullmatch('[a-f0-9]{64}',expected.text_sha256),
            'CONTROL_EXPECTATION_SHA')
    require(len({e.message_id for e in expectations})==len(expectations),'CONTROL_EXPECTATION_DUPLICATE')
    checked_guard(guard)
    fd,parent,name,descriptors,chain=_open_source(source)
    try:
        end=os.fstat(fd).st_size
        require(0<end<=MAX_PREFIX,'CONTROL_PREFIX_LIMIT')
        prefix,count,meta,users,pinned,latest=_project(fd,end,source,expectations,guard)
        os.lseek(fd,0,os.SEEK_SET);second=sha256();remaining=end
        while remaining:
            checked_guard(guard);chunk=os.read(fd,min(65536,remaining))
            require(bool(chunk),'CONTROL_SOURCE_TRUNCATED')
            remaining-=len(chunk);second.update(chunk)
        require(second.hexdigest()==prefix,'CONTROL_PREFIX_CHANGED')
        require(sha256(_first_line(fd,end,guard)).hexdigest()==source.session_meta_sha256,'CONTROL_META_CHANGED')
        _regular(os.fstat(fd),source)
        current=os.stat(name,dir_fd=parent,follow_symlinks=False);_regular(current,source)
        require(current.st_size>=end,'CONTROL_SOURCE_TRUNCATED')
        for ancestor,entry,identity in chain:
            info=os.stat(entry,dir_fd=ancestor,follow_symlinks=False)
            require(stat.S_ISDIR(info.st_mode) and (info.st_dev,info.st_ino)==identity,
                'CONTROL_ANCESTOR_CHANGED')
        checked_guard(guard)
    except OSError:raise SourceHold('CONTROL_SOURCE_READ_HOLD') from None
    finally:
        for descriptor in reversed(descriptors):os.close(descriptor)
    from .draft_revision_native_lookup import ObservedHumanEvent,_HUMAN_OBSERVED
    events=[]
    for expected in expectations:
        value=pinned[expected.message_id]
        evidence={'schema':'HOST_OBSERVED_USER_EVENT_V1','thread_id':source.thread_id,
            'turn_id':expected.turn_id,'user_message_id':expected.message_id,
            'message_sha256':value['message_sha256'],'record':value['record'],
            'source_registration_sha256':registration_digest(source),
            'source_prefix_bytes':end,'source_prefix_sha256':prefix}
        events.append(ObservedHumanEvent(source.thread_id,expected.turn_id,expected.message_id,
            value['message_sha256'],canonical(evidence),_HUMAN_OBSERVED))
    value={'schema':'NATIVE_CONTROL_PROJECTION_V1','source_registration_sha256':registration_digest(source),
        'source_prefix_bytes':end,'source_prefix_sha256':prefix,'metadata':meta,
        'absolute_end_ordinal':source.metadata_ordinal+count,'scanned_records':count,
        'user_controls':users,'latest_task':latest,
        'observed_user_event_sha256':[sha256(e.canonical_bytes).hexdigest() for e in events]}
    raw=canonical(value);require(len(raw)<=MAX_PROJECTION,'CONTROL_PROJECTION_LIMIT')
    snapshot=NativeControlSnapshot(source,raw,tuple(events),_SEAL)
    checked_guard(guard)
    return snapshot
