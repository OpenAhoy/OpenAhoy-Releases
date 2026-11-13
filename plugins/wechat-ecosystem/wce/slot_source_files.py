"""Owned private local facts for Slot sources, never MCP-selected paths."""
from hashlib import sha256
import json,os,stat
from .draft_revision_native_source import canonical,require,checked_guard,Record,_open_source,_regular,MAX_LINE
from .own_bootstrap_security import path_check
from .own_connection_policy import atomic_write


def private_json(root,name,guard):
    require(type(name)is str and name and '/'not in name and '\\'not in name,'SLOT_PRIVATE_PATH_INVALID')
    expected=path_check(root,True);directory=os.open(root,os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW)
    try:
        fd=os.open(name,os.O_RDONLY|os.O_NOFOLLOW|os.O_NONBLOCK,dir_fd=directory)
        try:
            before=os.fstat(fd)
            require(stat.S_ISREG(before.st_mode) and before.st_uid==os.getuid()
                and stat.S_IMODE(before.st_mode)==0o600 and before.st_nlink==1,'SLOT_PRIVATE_FILE_INVALID')
            def read():
                os.lseek(fd,0,os.SEEK_SET);parts=[]
                while True:
                    checked_guard(guard);part=os.read(fd,65536)
                    if not part:return b''.join(parts)
                    parts.append(part)
            raw=read();require(read()==raw and len(raw)==os.fstat(fd).st_size,'SLOT_PRIVATE_FILE_CHANGED')
            now=os.stat(name,dir_fd=directory,follow_symlinks=False)
            require((now.st_dev,now.st_ino)==(before.st_dev,before.st_ino)
                and now.st_size==before.st_size==len(raw),'SLOT_PRIVATE_FILE_CHANGED')
        finally:os.close(fd)
        require(path_check(root,True)==expected,'SLOT_PRIVATE_FILE_CHANGED')
    finally:os.close(directory)
    def pairs(items):
        result={}
        for key,value in items:
            require(key not in result,'SLOT_PRIVATE_JSON_INVALID');result[key]=value
        return result
    value=json.loads(raw.decode('utf8'),object_pairs_hook=pairs,
        parse_constant=lambda value:require(False,'SLOT_PRIVATE_JSON_INVALID'))
    checked_guard(guard)
    return value,sha256(raw).hexdigest()


def save_json(root,name,value,guard):
    checked_guard(guard);pin=path_check(root,True)
    atomic_write(root/name,value,expected_parent=pin);checked_guard(guard)
    actual,_=private_json(root,name,guard)
    require(actual==value,'SLOT_PRIVATE_WRITE_UNKNOWN')


def original_record(source,ref,guard):
    require(type(ref)is dict and ref.get('source_id')==source.source_id
        and type(ref.get('byte_start'))is int and type(ref.get('byte_end'))is int
        and 0<=ref['byte_start']<ref['byte_end'] and ref['byte_end']-ref['byte_start']<=MAX_LINE,
        'SLOT_ORIGINAL_REF_INVALID')
    fd,parent,name,descriptors,chain=_open_source(source)
    try:
        def read():
            parts=[];offset=ref['byte_start']
            while offset<ref['byte_end']:
                checked_guard(guard);raw=os.pread(fd,min(65536,ref['byte_end']-offset),offset)
                require(raw,'SLOT_ORIGINAL_REF_CHANGED');parts.append(raw);offset+=len(raw)
            return b''.join(parts)
        raw=read();require(sha256(raw).hexdigest()==ref['raw_line_sha256'] and read()==raw,
            'SLOT_ORIGINAL_REF_CHANGED')
        _regular(os.fstat(fd),source);_regular(os.stat(name,dir_fd=parent,follow_symlinks=False),source)
        for ancestor,entry,identity in chain:
            info=os.stat(entry,dir_fd=ancestor,follow_symlinks=False)
            require(stat.S_ISDIR(info.st_mode)and(info.st_dev,info.st_ino)==identity,'SOURCE_ANCESTOR_CHANGED')
        checked_guard(guard)
        result=Record(source.source_id,ref['ordinal'],ref['byte_start'],ref['byte_end'],ref['raw_line_sha256'],raw)
        require(result.value['ordinal']==ref['ordinal'],'SLOT_ORIGINAL_REF_INVALID')
        return result
    finally:
        for descriptor in reversed(descriptors):os.close(descriptor)
