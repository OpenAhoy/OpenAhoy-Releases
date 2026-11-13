"""Bounded immutable package-contract readers; no private installer contracts."""
from copy import deepcopy
from dataclasses import replace
from hashlib import sha256
import json
import math
import os
import stat
from pathlib import Path
from .bounded_file import FileSource
from .contracts import WCEError
from .service import canonical,digest
def fail():
    raise WCEError('BODY5_INACTIVE_EXTENSION_HOLD')
def bounded_contract(data):
    """Private format bounds; does not expand any existing JSON reader."""
    if type(data) is not bytes or not 0<len(data)<=262144: fail()
    def pairs(items):
        result={}
        for key,value in items:
            if key in result: fail()
            result[key]=value
        return result
    def constant(_): fail()
    try:
        value=json.loads(data.decode('utf-8'),object_pairs_hook=pairs,parse_constant=constant)
        count=0
        def walk(item,depth):
            nonlocal count
            count+=1
            if count>16384 or depth>40: fail()
            if type(item) is dict:
                if len(item)>1024: fail()
                for key,child in item.items():walk(key,depth+1);walk(child,depth+1)
            elif type(item) is list:
                if len(item)>1024: fail()
                for child in item:walk(child,depth+1)
            elif type(item) is int:
                if abs(item)>2**53-1: fail()
            elif type(item) is float:
                if not math.isfinite(item): fail()
            elif type(item) not in (str,bool,type(None)): fail()
        walk(value,0);canonical(value).encode('utf-8')
        return value
    except (ValueError,UnicodeError,RecursionError,OverflowError): fail()
def read_bounded(path):
    path=Path(path);source=FileSource(path.parent);descriptors=[];chain=[]
    try:
        parent=source._root(descriptors,chain)
        fd=os.open(path.name,os.O_RDONLY|os.O_NOFOLLOW|os.O_NONBLOCK,dir_fd=parent);descriptors.append(fd)
        before=os.fstat(fd)
        if (not stat.S_ISREG(before.st_mode) or before.st_uid!=os.getuid() or before.st_nlink!=1
                or not 0<before.st_size<=262144): fail()
        raw=bytearray()
        while len(raw)<=262144:
            part=os.read(fd,min(65536,262145-len(raw)))
            if not part: break
            raw.extend(part)
        def state(info):
            return (info.st_dev,info.st_ino,info.st_size,info.st_mtime_ns,info.st_ctime_ns,info.st_mode,info.st_uid,info.st_nlink)
        if (len(raw)!=before.st_size or state(before)!=state(os.fstat(fd))
                or state(before)!=state(os.stat(path.name,dir_fd=parent,follow_symlinks=False))): fail()
        source._check_chain(chain);return bytes(raw)
    finally:source._close(descriptors)
