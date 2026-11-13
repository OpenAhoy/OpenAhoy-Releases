"""Read-only lookup of one native thread from the host's current thread index.

Trusted host bootstrap chooses roots and owner thread. None is accepted from an
MCP caller. This proves observed USER records/stream identity, not article or
publication authority. No account, credential, token, transport or model call.
"""
from dataclasses import dataclass, field, replace
from hashlib import sha256
import os
from pathlib import Path
import re
import sqlite3
import stat
import threading
import math
import time
from .draft_revision_index_client import query_index
from .draft_revision_index_worker import QUERY_SECONDS
from .draft_revision_native_source import (RegisteredSource, PrefixRead, SourceHold, canonical, checked_guard,
    digest, require, strict_json, _open_source, _first_line, _metadata_origin,
    read_current_prefix, registration_digest)

UUID=r'[a-f0-9]{8}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{12}'


def valid_thread(value):
    require(type(value) is str and re.fullmatch(UUID,value),'HOST_THREAD_ID_INVALID')


_INDEX_LOCK=threading.RLock()


class NativeThreadLookup:
    def __init__(self,state_path,session_root,owner_thread,guard,*,allowed_threads,deadline=None):
        self.state_path=Path(state_path);self.session_root=Path(session_root)
        require(self.state_path.is_absolute() and self.session_root.is_absolute()
            and '..' not in self.state_path.parts and '..' not in self.session_root.parts
            and self.state_path.name=='state_5.sqlite' and self.session_root.name=='sessions'
            and self.session_root.parent==self.state_path.parent,'HOST_NATIVE_ROOT_INVALID')
        require(type(allowed_threads) is tuple and 1<=len(allowed_threads)<=2
            and len(set(allowed_threads))==len(allowed_threads),'HOST_THREAD_SCOPE_REQUIRED')
        for thread in allowed_threads:valid_thread(thread)
        self.allowed_threads=frozenset(allowed_threads)
        valid_thread(owner_thread);require(callable(guard),'HOST_NATIVE_GUARD_REQUIRED')
        require(deadline is None or (type(deadline) in (int,float) and math.isfinite(deadline)),
            'HOST_INDEX_WORKER_DEADLINE')
        self.owner_thread=owner_thread;self.guard=guard;self.deadline=deadline;self.registered={}

    def _row(self,thread):
        valid_thread(thread)
        require(thread in self.allowed_threads,'HOST_THREAD_OUT_OF_SCOPE')
        deadline=min(self.deadline,time.monotonic()+QUERY_SECONDS) if self.deadline is not None else time.monotonic()+QUERY_SECONDS
        while True:
            checked_guard(self.guard)
            require(time.monotonic()<deadline,'HOST_INDEX_WORKER_DEADLINE')
            if _INDEX_LOCK.acquire(timeout=0.05):break
        try:return self._row_locked(thread,deadline)
        finally:_INDEX_LOCK.release()

    def _row_locked(self,thread,deadline):
        checked_guard(self.guard)
        try:
            info=self.state_path.lstat()
            prototype=RegisteredSource('host-thread-index',self.state_path,info.st_dev,info.st_ino,
                'host-thread-index',0,0,sha256(b'').hexdigest(),'0'*64)
            fd,parent,name,descriptors,chain=_open_source(prototype)
            try:
                require(os.read(fd,16)==b'SQLite format 3\x00','HOST_NATIVE_INDEX_INVALID')
                from .slot_index_witness import _query_row
                path,owner=_query_row(self,thread,(info.st_dev,info.st_ino),deadline)
                checked_guard(self.guard)
                after=self.state_path.lstat();opened=os.fstat(fd)
                require((after.st_dev,after.st_ino)==(info.st_dev,info.st_ino)==(opened.st_dev,opened.st_ino)
                    and stat.S_ISREG(after.st_mode) and after.st_uid==os.getuid() and after.st_nlink==1,
                    'HOST_NATIVE_INDEX_CHANGED')
                for ancestor,item,identity in chain:
                    current=os.stat(item,dir_fd=ancestor,follow_symlinks=False)
                    require(stat.S_ISDIR(current.st_mode) and (current.st_dev,current.st_ino)==identity,
                        'HOST_NATIVE_INDEX_CHANGED')
            finally:
                for descriptor in reversed(descriptors):os.close(descriptor)
        except (OSError,sqlite3.Error,TypeError,ValueError):
            raise SourceHold('HOST_NATIVE_LOOKUP_HOLD') from None
        checked_guard(self.guard)
        require(time.monotonic()<deadline,'HOST_INDEX_WORKER_DEADLINE')
        from .slot_index_witness import _verified_row
        _verified_row(self,thread,(path,owner))
        return path,owner

    def locate(self,thread):
        path,owner=self._row(thread)
        try:
            info=path.lstat()
            temporary=RegisteredSource('native-header',path,info.st_dev,info.st_ino,thread,0,0,
                sha256(b'').hexdigest(),'0'*64)
            fd,parent,name,descriptors,chain=_open_source(temporary)
            try:first=_first_line(fd,os.fstat(fd).st_size,self.guard)
            finally:
                for descriptor in reversed(descriptors):os.close(descriptor)
            meta=strict_json(first,maximum=32*1024*1024)
            require(type(meta) is dict and type(meta.get('payload')) is dict,'HOST_NATIVE_METADATA_MISMATCH')
            payload=meta['payload']
            require(meta.get('type')=='session_meta' and type(meta.get('ordinal')) is int
                and payload.get('id')==thread
                and (payload.get('creator_user_id'),payload.get('creator_account_id'))==owner,
                'HOST_NATIVE_METADATA_MISMATCH')
            meta_sha=sha256(first).hexdigest();ordinal=meta['ordinal']
            source_id='native-'+digest({'thread':thread,'path_sha256':sha256(str(path).encode()).hexdigest(),
                'device':info.st_dev,'inode':info.st_ino,'metadata_sha256':meta_sha,'metadata_ordinal':ordinal})[:48]
            source=RegisteredSource(source_id,path,info.st_dev,info.st_ino,thread,0,ordinal,
                sha256(b'').hexdigest(),meta_sha,ordinal)
            _metadata_origin(meta,source)
            require(self._row(thread)==(path,owner),'HOST_NATIVE_POINTER_CHANGED')
        except OSError:raise SourceHold('HOST_NATIVE_SOURCE_HOLD') from None
        checked_guard(self.guard)
        return source

    def read(self,thread):
        registration=self.locate(thread)
        value=read_current_prefix(registration,self.guard)
        require(registration_digest(self.locate(thread))==registration_digest(registration),
            'HOST_NATIVE_POINTER_CHANGED')
        return value

    def capture_active_parent(self,thread):
        snapshot=self.control(thread);value=snapshot.value;latest=value['latest_task']
        require(latest is not None and latest['terminal'] is None,'HOST_PARENT_NOT_ACTIVE')
        turn=latest['turn_id'];valid_thread(turn)
        registration=replace(snapshot.source,start_offset=value['source_prefix_bytes'],
            start_ordinal=value['absolute_end_ordinal'],preceding_sha256=value['source_prefix_sha256'])
        self.registered[registration.source_id]=registration
        return registration,turn

    def control(self,thread,expectations=()):
        from .draft_revision_native_control import scan_current_control
        registration=self.locate(thread)
        snapshot=scan_current_control(registration,expectations,self.guard)
        require(registration_digest(self.locate(thread))==registration_digest(registration),
            'HOST_NATIVE_POINTER_CHANGED')
        checked_guard(self.guard)
        return snapshot

    def resolve(self,source_id):
        require(type(source_id) is str and source_id in self.registered,'HOST_NATIVE_SOURCE_NOT_REGISTERED')
        registered=self.registered[source_id];current=self.locate(registered.thread_id)
        require(current.source_id==source_id and current.path==registered.path
            and current.device==registered.device and current.inode==registered.inode
            and current.session_meta_sha256==registered.session_meta_sha256
            and current.metadata_ordinal==registered.metadata_ordinal,'HOST_NATIVE_POINTER_CHANGED')
        return registered


_HUMAN_OBSERVED=object()
@dataclass(frozen=True)
class ObservedHumanEvent:
    thread_id:str
    turn_id:str
    message_id:str
    message_sha256:str
    canonical_bytes:bytes=field(repr=False)
    _seal:object=field(repr=False)

    def __post_init__(self):
        require(self._seal is _HUMAN_OBSERVED and type(self.canonical_bytes) is bytes,
            'HOST_UNCHECKED_HUMAN_EVENT')

    @property
    def value(self):return strict_json(self.canonical_bytes)


def observe_user_event(stream,*,thread_id,turn_id,message_id,expected_text_sha256):
    """Typed native USER provenance only; no purpose/permit/binding inference."""
    require(type(stream) is PrefixRead and stream.source.thread_id==thread_id,'HOST_HUMAN_SOURCE_REQUIRED')
    for value in (thread_id,turn_id,message_id):valid_thread(value)
    require(type(expected_text_sha256) is str and re.fullmatch('[a-f0-9]{64}',expected_text_sha256),
        'HOST_HUMAN_EXPECTATION_REQUIRED')
    matches=[]
    for record in stream.records:
        outer=record.value;data=outer['payload'];item=data.get('item',{})
        if outer['type']=='event_msg' and data.get('type')=='item_completed' and item.get('id')==message_id:
            matches.append(record)
    require(len(matches)==1,'HOST_HUMAN_EVENT_NOT_UNIQUE')
    record=matches[0];data=record.value['payload'];item=data['item']
    require(item.get('type')=='UserMessage' and data.get('thread_id')==thread_id
        and data.get('turn_id')==turn_id,'HOST_HUMAN_EVENT_MISMATCH')
    content=item.get('content')
    require(type(content) is list and len(content)==1 and type(content[0]) is dict
        and set(content[0])=={'type','text','text_elements'} and content[0]['type']=='text'
        and type(content[0]['text']) is str and type(content[0]['text_elements']) is list,
        'HOST_HUMAN_CONTENT_UNSUPPORTED')
    text_sha=sha256(content[0]['text'].encode()).hexdigest()
    require(text_sha==expected_text_sha256,'HOST_HUMAN_TEXT_CHANGED')
    evidence={'schema':'HOST_OBSERVED_USER_EVENT_V1','thread_id':thread_id,'turn_id':turn_id,
        'user_message_id':message_id,'message_sha256':text_sha,'record':record.reference(),
        'source_registration_sha256':registration_digest(stream.source),
        'source_prefix_bytes':stream.prefix_bytes,'source_prefix_sha256':stream.prefix_sha256}
    return ObservedHumanEvent(thread_id,turn_id,message_id,text_sha,canonical(evidence),_HUMAN_OBSERVED)
