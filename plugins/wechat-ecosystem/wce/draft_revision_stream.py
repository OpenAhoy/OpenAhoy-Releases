"""Revision-only bounded-retention source reader; validates every input record.

The full history prefix is hashed incrementally without a file-size ceiling.
Line/JSON/ordinal validation and exact raw suffix replay remain; compressed
first-pass suffix bytes stay only in RAM.
Only observer-consumed records are retained, bounded by the original 64 MiB;
large tool/assistant records are parsed/validated/hashed rather than accumulated.
No raw source is written to disk and no previous observation is reused.
"""
from hashlib import sha256
import os,stat,re,zlib
from .draft_revision_native_source import (RegisteredSource,Record,PrefixRead,SourceHold,
    MAX_PREFIX,MAX_SEGMENT,MAX_LINE,MAX_RECORDS,require,checked_guard,strict_json,
    _open_source,_regular,_read_exact,_first_line,_metadata_origin,_identity)
from .draft_revision_scan import full


def needed(row):
    kind=row['type'];p=row['payload']
    return (kind=='turn_context'
        or kind=='response_item' and p.get('type')=='message' and p.get('role')=='user'
        or kind=='event_msg' and (p.get('type') in ('task_started','user_message')
            or p.get('type')=='item_completed' and type(p.get('item')) is dict
                and p['item'].get('type')=='UserMessage'))


class _RawReplay:
    """Bounded independent RAM blocks; second pass compares actual bytes."""
    BLOCK=2*1024*1024
    def __init__(self,expected):
        require(type(expected) is int and 0<expected<=MAX_PREFIX,'SOURCE_REPLAY_LIMIT')
        self.expected=expected;self.captured=0;self.decoded=0;self.stored=0
        self.pending=bytearray();self.blocks=[];self.index=0;self.buffer=b'';self.position=0;self.sealed=False
    def _block(self,raw):
        require(0<len(raw)<=self.BLOCK,'SOURCE_REPLAY_LIMIT')
        c=zlib.compressobj(level=1,wbits=-15);packed=c.compress(raw)+c.flush()
        require(len(packed)<=4*1024*1024,'SOURCE_REPLAY_LIMIT')
        compressed=len(packed)<len(raw);data=packed if compressed else raw
        self.blocks.append((compressed,len(raw),data));self.stored+=len(data)
        require(self.stored<=self.captured<=self.expected
            and len(self.blocks)<=(self.expected+self.BLOCK-1)//self.BLOCK,'SOURCE_REPLAY_LIMIT')
    def capture(self,raw,guard):
        require(type(raw) is bytes and not self.sealed
            and self.captured+len(raw)<=self.expected,'SOURCE_REPLAY_LIMIT')
        self.captured+=len(raw);offset=0
        while offset<len(raw):
            checked_guard(guard);size=min(self.BLOCK-len(self.pending),len(raw)-offset)
            self.pending.extend(raw[offset:offset+size]);offset+=size
            if len(self.pending)==self.BLOCK:
                self._block(bytes(self.pending));self.pending.clear()
            checked_guard(guard)
    def seal(self):
        require(not self.sealed and self.captured==self.expected,'SOURCE_REPLAY_LIMIT')
        if self.pending:self._block(bytes(self.pending));self.pending.clear()
        self.sealed=True
    def _load(self):
        require(self.sealed and self.index<len(self.blocks),'SOURCE_PREFIX_CHANGED')
        block=self.blocks[self.index]
        require(type(block) is tuple and len(block)==3,'SOURCE_PREFIX_CHANGED')
        compressed,size,data=block
        expected=min(self.BLOCK,self.expected-self.index*self.BLOCK)
        require(type(compressed) is bool and type(size) is int and size==expected
            and 0<size<=self.BLOCK and type(data) is bytes and 0<len(data)<=size,'SOURCE_PREFIX_CHANGED')
        if compressed:
            d=zlib.decompressobj(-15);raw=d.decompress(data,size+1)
            require(len(raw)==size and d.eof and not d.unconsumed_tail and not d.unused_data,'SOURCE_PREFIX_CHANGED')
        else:
            require(len(data)==size,'SOURCE_PREFIX_CHANGED');raw=data
        self.buffer=raw;self.position=0;self.index+=1
    def compare(self,raw,guard):
        require(type(raw) is bytes and self.sealed
            and self.decoded+len(raw)<=self.expected,'SOURCE_PREFIX_CHANGED')
        offset=0
        while offset<len(raw):
            checked_guard(guard)
            if self.position==len(self.buffer):self._load()
            size=min(len(self.buffer)-self.position,len(raw)-offset)
            require(size>0 and raw[offset:offset+size]==self.buffer[self.position:self.position+size],
                'SOURCE_PREFIX_CHANGED')
            offset+=size;self.position+=size;self.decoded+=size
    def finish(self,guard):
        checked_guard(guard)
        require(self.sealed and self.captured==self.decoded==self.expected
            and not self.pending and self.index==len(self.blocks)
            and self.position==len(self.buffer)
            and len(self.blocks)==(self.expected+self.BLOCK-1)//self.BLOCK,'SOURCE_PREFIX_CHANGED')


def _pass(fd,end,source,guard,*,retain,replay,first):
    os.lseek(fd,0,os.SEEK_SET);whole=sha256();before=sha256();offset=0
    while offset<source.start_offset:
        checked_guard(guard)
        raw=os.read(fd,min(2*1024*1024,source.start_offset-offset));require(bool(raw),'SOURCE_TRUNCATED')
        whole.update(raw);before.update(raw);offset+=len(raw)
    records=[];retained=0;count=0
    with os.fdopen(os.dup(fd),'rb',buffering=65536) as stream:
        while offset<end:
            checked_guard(guard)
            raw=stream.readline(min(MAX_LINE+1,end-offset+1))
            require(raw and raw.endswith(b'\n') and len(raw)<=MAX_LINE
                and offset+len(raw)<=end,'SOURCE_LINE_LIMIT')
            if source.start_offset==0 and count==0:require(raw==first,'SOURCE_META_CHANGED')
            row=strict_json(raw,maximum=MAX_LINE);ordinal=source.start_ordinal+count
            require(ordinal<MAX_RECORDS and type(row) is dict
                and type(row.get('ordinal')) is int and row['ordinal']==ordinal
                and type(row.get('type')) is str and type(row.get('payload')) is dict,
                'SOURCE_RECORD_INVALID')
            checked_guard(guard);whole.update(raw)
            if retain:
                replay.capture(raw,guard)
                if needed(row):
                    retained+=len(raw);require(retained<=MAX_SEGMENT,'REVISION_RETAINED_SOURCE_LIMIT')
                    records.append(Record(source.source_id,ordinal,offset,offset+len(raw),sha256(raw).hexdigest(),raw))
            else:replay.compare(raw,guard)
            offset+=len(raw);count+=1
    require(offset==end and count>0,'SOURCE_RANGE_INVALID')
    if retain:replay.seal()
    else:replay.finish(guard)
    full(guard)
    return whole.hexdigest(),before.hexdigest(),count,tuple(records)


def read_current_prefix(source,guard):
    require(type(source) is RegisteredSource,'UNREGISTERED_NATIVE_SOURCE')
    require(type(source.metadata_ordinal) is int and 0<=source.metadata_ordinal<MAX_RECORDS,'SOURCE_META_INVALID')
    require(all(type(v) is str and re.fullmatch(r'[A-Za-z0-9_-]{1,128}',v)
        for v in (source.source_id,source.thread_id))
        and all(type(v) is str and re.fullmatch('[a-f0-9]{64}',v)
            for v in (source.preceding_sha256,source.session_meta_sha256))
        and all(type(v) is int and v>=0 for v in (source.device,source.inode)),
        'SOURCE_REGISTRATION_INVALID')
    full(guard);fd,parent,name,descriptors,chain=_open_source(source)
    try:
        end=os.fstat(fd).st_size
        require(type(source.start_offset) is int and type(source.start_ordinal) is int
            and 0<=source.start_offset<end and 0<=source.start_ordinal<MAX_RECORDS,'SOURCE_PREFIX_LIMIT')
        if source.start_offset:
            os.lseek(fd,source.start_offset-1,os.SEEK_SET)
            require(_read_exact(fd,1)==b'\n','SOURCE_CURSOR_NOT_LINE_BOUNDARY')
        first=_first_line(fd,end,guard)
        require(sha256(first).hexdigest()==source.session_meta_sha256,'SOURCE_META_CHANGED')
        meta=strict_json(first,maximum=MAX_LINE)
        require(type(meta) is dict and type(meta.get('ordinal')) is int
            and meta['ordinal']==source.metadata_ordinal and meta.get('type')=='session_meta'
            and type(meta.get('payload')) is dict and meta['payload'].get('id')==source.thread_id,'SOURCE_META_INVALID')
        _metadata_origin(meta,source)
        if source.start_offset==0:require(source.start_ordinal==source.metadata_ordinal,'SOURCE_META_INVALID')
        full(guard)
        replay=_RawReplay(end-source.start_offset)
        first_pass=_pass(fd,end,source,guard,retain=True,replay=replay,first=first)
        require(first_pass[1]==source.preceding_sha256,'SOURCE_CURSOR_CHANGED')
        full(guard);second=_pass(fd,end,source,guard,retain=False,replay=replay,first=first)
        require(second[:3]==first_pass[:3],'SOURCE_PREFIX_CHANGED')
        require(_first_line(fd,end,guard)==first,'SOURCE_META_CHANGED')
        _regular(os.fstat(fd),source);current=os.stat(name,dir_fd=parent,follow_symlinks=False);_regular(current,source)
        require(current.st_size>=end,'SOURCE_TRUNCATED')
        for ancestor,entry,pin in chain:
            current=os.stat(entry,dir_fd=ancestor,follow_symlinks=False)
            require(stat.S_ISDIR(current.st_mode) and _identity(current)==pin,'SOURCE_ANCESTOR_CHANGED')
        full(guard)
        result=PrefixRead(source,end,first_pass[0],Record(source.source_id,source.metadata_ordinal,
            0,len(first),sha256(first).hexdigest(),first),first_pass[3])
    except (OSError,zlib.error,MemoryError):raise SourceHold('SOURCE_READ_HOLD') from None
    finally:
        for descriptor in reversed(descriptors):os.close(descriptor)
    full(guard);return result
