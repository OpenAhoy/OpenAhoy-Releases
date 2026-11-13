"""Non-authoritative, entry-local pure derived-value memo. Isolated proposal.

Does not issue Host/QA/H/SourceReview/current receipts. Caller must perform all
original raw reads/full pins and current authority checks before every lookup.
No filesystem, SQL, subprocess, raster retention or global cache.
"""
from dataclasses import dataclass
from hashlib import sha256
import json
import os
import threading
import inspect
import sys

from wce.contracts import WCEError

class CacheHold(WCEError):pass

def need(value):
    if value is not True:raise CacheHold('GROUP_PURE_DERIVED_CACHE_HOLD')

def canonical(value):
    # Only final builtins; no object hooks or custom serializer.
    def plain(v):
        need(type(v) in (dict,list,str,int,bool,type(None)))
        if type(v) is dict:
            need(all(type(k) is str for k in v))
            for x in v.values():plain(x)
        elif type(v) is list:
            for x in v:plain(x)
    plain(value)
    return json.dumps(value,sort_keys=True,ensure_ascii=False,separators=(',',':'),allow_nan=False).encode()

def _code_pins():
    # Fixed local pure decoder/converter closure only. Not an issuer registry.
    from wce import (local_html_import,import_images,own_png,html_document,
        import_styles,reading_layout,documents)
    modules=(sys.modules[__name__],local_html_import,import_images,own_png,
             html_document,import_styles,reading_layout,documents)
    pins=[];seen=set()
    for module in modules:
        for name,value in tuple(vars(module).items()):
            if inspect.isfunction(value):pins.append((module,name,value,value.__code__))
            elif inspect.isclass(value) and (value.__module__.startswith('wce.') or value.__module__==__name__):
                pins.append((module,name,value,None))
                if value in seen:continue
                seen.add(value)
                pins.append((value,'__mro_identity__',(value.__bases__,value.__mro__),None))
                pins.append((value,'__namespace_keys__',tuple(vars(value)),None))
                for attr,member in tuple(vars(value).items()):
                    fn=(member.__func__ if type(member) in (staticmethod,classmethod)
                        else member.fget if type(member) is property else member)
                    if inspect.isfunction(fn):pins.append((value,attr,member,fn.__code__))
    return tuple(pins)

def _check_code(pins):
    for owner,name,original,code in pins:
        if name=='__mro_identity__':
            need(owner.__bases__==original[0] and owner.__mro__==original[1]);continue
        if name=='__namespace_keys__':
            need(tuple(vars(owner))==original);continue
        actual=vars(owner).get(name)
        fn=(actual.__func__ if type(actual) in (staticmethod,classmethod)
            else actual.fget if type(actual) is property else actual)
        need(actual is original and (code is None or inspect.isfunction(fn) and fn.__code__ is code))

@dataclass(frozen=True)
class _Record:
    inputs_sha:str
    raw:bytes
    result_sha:str

class EntryDerivedCache:
    """Data cache only; `code_token` is fixed-owner snapshot, never user input.

    Production adapter owns one instance, closes with its Entry, and charges
    retained_bytes against original aggregate 64MiB raw bound. `fence` must
    include actual code-pin/package-C plus original physical/full/raw fences;
    it runs before key computation and again after each hit/miss, never cached.
    """
    def __init__(self,entry,code_scope,code_token,*,result_keys=('title','fragment','provenance'),max_retained_bytes=64*1024*1024):
        need(type(code_scope) is str and len(code_scope)==64
             and all(c in '0123456789abcdef' for c in code_scope))
        need(type(code_token) is tuple and code_token
             and type(max_retained_bytes) is int and 0<max_retained_bytes<=64*1024*1024)
        need(type(result_keys) is tuple and len(result_keys)>0 and all(type(x) is str for x in result_keys))
        self._result_keys=result_keys
        self._entry=entry;self._scope=code_scope;self._code=code_token
        self._owner=(os.getpid(),threading.get_ident());self._closed=False;self._pins=_code_pins()
        self._records={};self.retained_bytes=0;self.maximum=max_retained_bytes

    def resolve(self,entry,member_key,raw_inputs,parameters,*,code_scope,code_token,fence,reserve,derive):
        need(not self._closed and entry is self._entry
             and self._owner==(os.getpid(),threading.get_ident())
             and code_scope==self._scope and type(code_token) is tuple
             and len(code_token)==len(self._code)
             and all(a is b for a,b in zip(code_token,self._code)))
        _check_code(self._pins);fence()
        need(type(member_key) is str and 0<len(member_key)<=128
             and type(raw_inputs) is tuple and len(raw_inputs)>0)
        rows=[]
        for row in raw_inputs:
            need(type(row) is tuple and len(row)==3)
            label,mime,raw=row
            need(type(label) is str and type(mime) is str and type(raw) is bytes
                 and 0<len(raw)<=4*1024*1024)
            rows.append([label,mime,len(raw),sha256(raw).hexdigest()])
        material=canonical({'raw_inputs':rows,'parameters':parameters,'code_scope':code_scope})
        key=sha256(material).hexdigest();record=self._records.get(member_key)
        if record is not None:
            need(record.inputs_sha==key and sha256(record.raw).hexdigest()==record.result_sha)
            value=json.loads(record.raw)
            _check_code(self._pins);fence()
            return value
        value=derive()
        need(type(value) is dict and set(value)==set(self._result_keys))
        raw=canonical(value)
        _check_code(self._pins);fence()  # Failure never publishes a record.
        if self.retained_bytes+len(raw)>self.maximum:return json.loads(raw)
        try:reserve(len(raw))
        except WCEError as error:
            if error.code not in ('GROUP_MAINTENANCE_CASE_RAW_BOUND','GROUP_DERIVED_RAW_BOUND'):raise
            self.clear()  # Pure recomputation result, no authority fallback.
            fence()
            return json.loads(raw)
        record=_Record(key,raw,sha256(raw).hexdigest())
        # Charge before ownership transfer; an interrupted insertion stays
        # conservatively charged until entry close, never under-accounted.
        charged=self.retained_bytes+len(raw)
        self.retained_bytes=charged
        self._records[member_key]=record
        return json.loads(raw)

    def clear(self):
        self._records.clear();self.retained_bytes=0

    def close(self):
        self.clear();self._closed=True
