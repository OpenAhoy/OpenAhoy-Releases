"""Group-only strict HTTP/TLS transport. Ordinary HTTPSender is untouched.

Prepared objects/captures are process-local facts. TLS origin is issued only by
this concrete connection/response chain; a constructed class is never evidence.
No request, exception text, token body or token-body hash is serialised here.
"""
from dataclasses import dataclass, field
from hashlib import sha256
import http.client as hc
import io
import math
import re
import ssl
import socket
import threading
import types
import time
import urllib.request as ur
from urllib.error import HTTPError
from urllib.parse import urlsplit
from .contracts import WCEError
from .http_transport import HTTPSender, HTTPRequest, HTTPResponse, MAX_BODY, NoRedirect

PROFILE = 'STRICT_GROUP_HTTP_FRAMING_V1'
_MONOTONIC = time.monotonic
_WALL = time.time
_ACTIVE = threading.local()
_PREPARED = {}
_PREPARED_FACTS = {}
_EXCHANGE_USED = {}
_TOKEN_SHELLS = {}
_TOKEN_FILLED = {}
_TOKEN_IO_DEADLINES = {}
_CAPTURES = {}
_DISPOSITIONS = {}
_CONSUMED_ARRIVALS = {}
_MAX_HEADER = 65536
_MAX_ALL_HEADERS = 131072
_ENDPOINTS = frozenset(('/cgi-bin/stable_token','/cgi-bin/draft/batchget',
                       '/cgi-bin/draft/get','/cgi-bin/draft/add','/cgi-bin/draft/delete'))


def fail():
    raise WCEError('GROUP_TRANSPORT_UNQUALIFIED')


@dataclass(frozen=True, slots=True)
class GroupDeadline:
    deadline: float
    timeout: float = 10.0

    def remaining(self):
        # This is deliberately the pinned primitive, never a caller clock.
        if time.monotonic is not _MONOTONIC:
            fail()
        now = _MONOTONIC()
        if (type(now) is not float or not math.isfinite(now)
                or type(self.deadline) not in (int,float) or not math.isfinite(self.deadline)
                or type(self.timeout) not in (int,float) or not math.isfinite(self.timeout)
                or not 0 < self.timeout <= 30 or not 0 < self.deadline-now <= 30):
            fail()
        return min(self.timeout, self.deadline-now)


@dataclass(frozen=True,slots=True)
class GroupTokenOuterDeadline:
    deadline: float
    timeout: float=10.0

    def remaining(self):
        if time.monotonic is not _MONOTONIC:fail()
        now=_MONOTONIC()
        if (type(now) is not float or not math.isfinite(now) or type(self.deadline) not in (int,float)
                or not math.isfinite(self.deadline) or type(self.timeout) not in (int,float)
                or self.timeout!=10 or not 0<self.deadline-now<=300.001):fail()
        return min(10,self.deadline-now)


def _stdlib_code_pin():
    classes=(GroupDeadline,GroupTokenOuterDeadline,ur.Request,ur.OpenerDirector,ur.AbstractHTTPHandler,ur.HTTPSHandler,ur.HTTPHandler,
        ur.HTTPDefaultErrorHandler,ur.HTTPErrorProcessor,ur.ProxyHandler,NoRedirect,
        ur.UnknownHandler,ur.FTPHandler,ur.FileHandler,ur.DataHandler,
        hc.HTTPConnection,hc.HTTPSConnection,hc.HTTPResponse,HTTPSender,
        GroupStrictHTTPResponse,GroupHTTPSConnection,GroupHTTPSHandler,TokenTransportShell,threading.Thread,threading.Event,ssl.SSLContext,ssl.SSLSocket,socket.socket)
    return tuple((cls,tuple((key,id(value),id(value.__code__) if type(value) is types.FunctionType else None)
        for key,value in sorted(vars(cls).items()))) for cls in classes)


def _primitive_refs():
    from .draft_group_rich_syn_transport import transport_tcb_pin
    own_functions=tuple((name,fn,fn.__code__) for name,fn in sorted(globals().items())
        if type(fn) is types.FunctionType and fn.__module__==__name__ and name not in ('_primitive_refs','_stdlib_code_pin'))
    return ((_primitive_refs,_primitive_refs.__code__,_stdlib_code_pin,_stdlib_code_pin.__code__,own_functions),
        (transport_tcb_pin,transport_tcb_pin.__code__,transport_tcb_pin()),_stdlib_code_pin(),time.monotonic,time.time,(ssl.create_default_context,ssl.create_default_context.__code__),ssl.SSLContext,
        ssl.SSLSocket,ssl.SSLSocket.settimeout,hc.HTTPSConnection.connect,
        hc.HTTPConnection.request,hc.HTTPConnection.getresponse,hc.HTTPResponse.__init__,
        hc.parse_headers,ur.Request,ur.build_opener,ur.OpenerDirector.open,
        ur.AbstractHTTPHandler.do_open,ur.HTTPSHandler.__init__,ur.ProxyHandler,
        ur.HTTPRedirectHandler,ur.HTTPErrorProcessor.http_response,
        GroupHTTPSConnection.connect,GroupHTTPSConnection.getresponse,GroupHTTPSConnection.send,
        GroupHTTPSHandler.https_open,GroupStrictHTTPResponse.begin,
        GroupStrictHTTPResponse.read_framed,GroupStrictHTTPResponse._io,
        GroupStrictHTTPResponse._line,GroupStrictHTTPResponse._exact,
        (prepare_token_transport_shell,prepare_token_transport_shell.__code__),
        (validate_token_transport_shell,validate_token_transport_shell.__code__),
        (fill_token_request,fill_token_request.__code__))


class GroupTransportTCB:
    __slots__ = ('refs','thread')
    def __init__(self):
        self.refs = _primitive_refs()
        self.thread = threading.get_ident()


def validate_transport_tcb(tcb=None):
    if tcb is None:
        tcb = GroupTransportTCB()
    if (type(tcb) is not GroupTransportTCB or tcb.thread != threading.get_ident()
            or tcb.refs != _BASE_REFS or _primitive_refs() != _BASE_REFS
            or time.monotonic is not _MONOTONIC or time.time is not _WALL):
        fail()
    return tcb


class GroupStrictHTTPResponse(hc.HTTPResponse):
    """Bounded status/header parsing and exact, deliberately narrow framing.

    The separate component constructor may parse BytesIO fixtures but cannot
    enter the production capture registry without a registered TLS connection.
    """
    def __init__(self, sock, debuglevel=0, method=None, url=None):
        active = getattr(_ACTIVE, 'prepared', None)
        if active is None:
            fail()
        self._group_deadline = active.deadline
        self._group_socket = sock
        self._group_prepared = active
        self._group_header_total = 0
        self._group_header_block = 0
        self._group_wire = 0
        super().__init__(sock, debuglevel=0, method=method, url=url)
        self._group_fp = self.fp
        self._group_read = self.fp.read
        self._group_readline = self.fp.readline
        if active.connection is not None and active.connection.sock is sock:
            active.response = self

    def _io(self, method, *args):
        timeout = _remaining(self._group_prepared) if type(self._group_prepared) is PreparedTransport else self._group_deadline.remaining()
        if self.fp is not self._group_fp:
            fail()
        self._group_socket.settimeout(timeout)
        result = method(*args)
        (_remaining(self._group_prepared) if type(self._group_prepared) is PreparedTransport else self._group_deadline.remaining())
        if type(result) is not bytes:
            fail()
        return result

    def _line(self, maximum, *, header=False):
        if header:
            maximum=min(maximum,_MAX_HEADER-self._group_header_block,_MAX_ALL_HEADERS-self._group_header_total)
            if maximum<2:fail()
        line = self._io(self._group_readline, maximum+1)
        if not line or len(line)>maximum or not line.endswith(b'\r\n'):
            fail()
        if header:
            self._group_header_block += len(line)
            self._group_header_total += len(line)
            if self._group_header_block>_MAX_HEADER or self._group_header_total>_MAX_ALL_HEADERS:
                fail()
        return line

    def begin(self):
        if self.headers is not None:
            return
        if self._method != 'POST':
            fail()
        interim = 0
        while True:
            self._group_header_block=0
            line=self._line(8192,header=True)
            match=re.fullmatch(rb'(HTTP/1\.[01]) ([0-9]{3})(?: ([^\r\n]*))?\r\n',line)
            if match is None:
                fail()
            version,status,reason=match.groups(); status=int(status)
            if not 100<=status<=599:
                fail()
            lines=[]
            while True:
                line=self._line(8192,header=True)
                if line==b'\r\n':break
                if (line[:1] in (b' ',b'\t') or b':' not in line
                        or any(c<32 and c!=9 or c==127 for c in line[:-2])):
                    fail()
                name,value=line[:-2].split(b':',1)
                if re.fullmatch(rb"[!#$%&'*+.^_`|~0-9A-Za-z-]+",name) is None:
                    fail()
                # Exactly one conventional delimiter SP is permitted. The
                # framing values themselves cannot hide whitespace ambiguity.
                checked=value[1:] if value.startswith(b' ') else value
                if name.lower() in (b'content-length',b'transfer-encoding',b'content-encoding'):
                    if checked!=checked.strip(b' \t'):
                        fail()
                lines.append(line)
                if len(lines)>100:fail()
            if status==100:
                interim+=1
                if interim>8:fail()
                continue
            if status<200:fail()
            self.code=self.status=status
            self.reason=(reason or b'').decode('iso-8859-1').strip()
            self.version=10 if version==b'HTTP/1.0' else 11
            self.headers=self.msg=hc.parse_headers(io.BytesIO(b''.join(lines)+b'\r\n'))
            break
        cls=self.headers.get_all('Content-Length',[])
        tes=self.headers.get_all('Transfer-Encoding',[])
        ces=self.headers.get_all('Content-Encoding',[])
        if len(cls)>1 or len(tes)>1 or len(ces)>1 or cls and tes:
            fail()
        if ces and ces[0].lower()!='identity':fail()
        if tes and tes[0].lower()!='chunked':fail()
        length=None
        if cls:
            if re.fullmatch(r'[0-9]{1,10}',cls[0]) is None:fail()
            length=int(cls[0])
            if length>MAX_BODY:fail()
        self.chunked=bool(tes);self.chunk_left=None
        self.will_close=self._check_close()
        if not self.chunked and length is None:self.will_close=True
        self.length=0 if status in (204,304) else length
        self._group_mode='NO_BODY' if status in (204,304) else 'CHUNKED' if tes else 'CONTENT_LENGTH' if cls else 'CLOSE_EOF'

    def _exact(self, count):
        result=bytearray()
        while len(result)<count:
            part=self._io(self._group_read,min(65536,count-len(result)))
            if not part:fail()
            result.extend(part)
        return bytes(result)

    def read_framed(self):
        if self.headers is None:self.begin()
        if self._group_mode=='NO_BODY':return b''
        if self._group_mode=='CONTENT_LENGTH':return self._exact(self.length)
        out=bytearray()
        if self._group_mode=='CHUNKED':
            for index in range(4096):
                line=self._line(8192)
                self._group_wire+=len(line)
                if re.fullmatch(rb'[0-9a-fA-F]{1,8}\r\n',line) is None:fail()
                count=int(line[:-2],16)
                if self._group_wire+count+2>MAX_BODY+65536 or len(out)+count>MAX_BODY:fail()
                if count==0:
                    if self._line(2)!=b'\r\n':fail()
                    self._group_wire+=2
                    return bytes(out)
                out.extend(self._exact(count))
                if self._exact(2)!=b'\r\n':fail()
                self._group_wire+=count+2
            fail()
        if self._group_mode!='CLOSE_EOF' or not self.will_close:fail()
        while True:
            part=self._io(self._group_read,min(65536,MAX_BODY+1-len(out)))
            if not part:return bytes(out)
            out.extend(part)
            if len(out)>MAX_BODY:fail()


class GroupHTTPSConnection(hc.HTTPSConnection):
    response_class=GroupStrictHTTPResponse
    def connect(self):
        prepared=getattr(_ACTIVE,'prepared',None)
        if (prepared is None or self.host!=prepared.host or self._context is not prepared.context
                or self._tunnel_host is not None):fail()
        facts=_route_deadline_facts(prepared)
        if facts.syn_binding is not None:
            from .draft_group_rich_syn_transport import validate_binding_for_entry
            r=validate_binding_for_entry(facts.syn_binding,facts.syn_entry)
            if self.host!=r.listener_address[0] or self.port!=r.listener_address[1]:fail()
        self.timeout=_remaining(prepared)
        _ORIGINAL_CONNECT(self)
        _remaining(prepared)
        sock=self.sock
        if (type(sock) is not ssl.SSLSocket or sock.context is not prepared.context
                or sock.server_hostname!=prepared.host or sock.version() is None
                or prepared.context.verify_mode!=ssl.CERT_REQUIRED
                or prepared.context.check_hostname is not True):fail()
        if facts.syn_binding is not None:
            if sock.getpeername()[:2]!=r.listener_address or sha256(sock.getpeercert(binary_form=True)).hexdigest()!=r.certificate_der_sha:fail()
        # Unexpected TLS truncation must remain SSLEOFError, not b''.
        sock.suppress_ragged_eofs=False
        if (sock.suppress_ragged_eofs is not False
                or type(sock.makefile) is not types.MethodType or sock.makefile.__func__ is not socket.socket.makefile):fail()
        prepared.connection=self;prepared.socket=sock

    def send(self,data):
        prepared=getattr(_ACTIVE,'prepared',None)
        if prepared is None:fail()
        remaining=_remaining(prepared)
        if self.sock is not None:self.sock.settimeout(remaining)
        _ORIGINAL_SEND(self,data)
        _remaining(prepared)

    def getresponse(self):
        prepared=getattr(_ACTIVE,'prepared',None)
        if prepared is None or prepared.connection is not self:fail()
        response=_ORIGINAL_GETRESPONSE(self)
        _remaining(prepared)
        if prepared.response is not response or response._group_socket is not prepared.socket:fail()
        return response


class GroupHTTPSHandler(ur.HTTPSHandler):
    def https_open(self, request):
        prepared=getattr(_ACTIVE,'prepared',None)
        if (prepared is None or prepared.request is not request
                or self is not prepared.handler or self._context is not prepared.context):fail()
        return _ORIGINAL_DO_OPEN(self,GroupHTTPSConnection,request,context=self._context)


_ORIGINAL_SEND=hc.HTTPConnection.send
_ORIGINAL_CONNECT=hc.HTTPSConnection.connect
_ORIGINAL_GETRESPONSE=hc.HTTPConnection.getresponse
_ORIGINAL_DO_OPEN=ur.AbstractHTTPHandler.do_open


class PreparedTransport:
    __slots__=('request','context','handler','opener','deadline','tcb','thread','host',
               'connection','socket','response','_pin','_handlers','_used','token','synthetic','_context_pin')
    def __repr__(self):return '<PreparedGroupTransport>'


def _request_pin(req):
    if type(req) is not ur.Request:fail()
    def plain(value):
        kind=type(value)
        if kind is dict:
            if any(type(k) is not str for k in value):fail()
            return tuple((k,plain(v)) for k,v in sorted(value.items()))
        if kind in (str,bytes,int,float,bool,type(None)):return (kind,value)
        fail()
    return plain(vars(req))


def _registry_pin(value):
    if type(value) is dict:
        if any(type(k) not in (str,int) for k in value):fail()
        return tuple((k,_registry_pin(v)) for k,v in sorted(value.items(),key=lambda item:(type(item[0]).__name__,str(item[0]))))
    if type(value) in (list,tuple):return tuple(_registry_pin(x) for x in value)
    return id(value)


def _handler_pin(opener):
    allowed=(ur.ProxyHandler,NoRedirect,GroupHTTPSHandler,ur.UnknownHandler,ur.HTTPHandler,ur.HTTPDefaultErrorHandler,ur.FTPHandler,ur.FileHandler,ur.DataHandler,ur.HTTPErrorProcessor)
    if type(opener) is not ur.OpenerDirector or any(type(h) not in allowed for h in opener.handlers):fail()
    return (tuple(opener.handlers),tuple((type(h),_registry_pin(vars(h))) for h in opener.handlers),
        _registry_pin(vars(opener)))


def _ssl_context_pin(context):
    if type(context) is not ssl.SSLContext or vars(context):fail()
    return (context.protocol,context.verify_mode,context.check_hostname,context.options,
        context.minimum_version,context.maximum_version,context.verify_flags,
        context.hostname_checks_common_name,context.keylog_filename,context.post_handshake_auth,
        context.sni_callback,context.num_tickets,context.security_level,
        tuple(sorted(sha256(cert).digest() for cert in context.get_ca_certs(binary_form=True))),
        tuple((x['id'],x['name']) for x in context.get_ciphers()))


def _new_transport_resources(syn_binding=None,syn_entry=None):
    if syn_binding is not None:
        from .draft_group_rich_syn_transport import validate_binding_for_entry
        context=validate_binding_for_entry(syn_binding,syn_entry).client_context
    else:context=ssl.create_default_context()
    context.check_hostname=True;context.verify_mode=ssl.CERT_REQUIRED;context.keylog_filename=None
    handler=GroupHTTPSHandler(context=context)
    opener=ur.build_opener(ur.ProxyHandler({}),NoRedirect(),handler)
    return context,handler,opener


def _assemble_prepared(actual_sender,issued_request,deadline,tcb,source_kind,resources,*,shell=None,syn_binding=None,syn_entry=None):
    request=HTTPSender._prepare_request(actual_sender,issued_request,deadline.timeout)
    context,handler,opener=resources
    prepared=PreparedTransport()
    prepared.request=request;prepared.context=context;prepared.handler=handler;prepared.opener=opener
    prepared.deadline=deadline;prepared.tcb=tcb;prepared.thread=threading.get_ident();prepared.host='api.weixin.qq.com'
    if syn_binding is not None:
        from .draft_group_rich_syn_transport import validate_binding_for_entry
        r=validate_binding_for_entry(syn_binding,syn_entry)
        path=urlsplit(issued_request.path)
        request.full_url='https://127.0.0.1:'+str(r.listener_address[1])+path.path+('?' + path.query if path.query else '')
        prepared.host='127.0.0.1'
    prepared.connection=prepared.socket=prepared.response=None
    prepared._pin=_request_pin(request);prepared._handlers=_handler_pin(opener);prepared._context_pin=_ssl_context_pin(context)
    path=urlsplit(issued_request.path)
    prepared._used=False;prepared.token=path.path=='/cgi-bin/stable_token';prepared.synthetic=source_kind=='SYNTHETIC_SETUP'
    _PREPARED[id(prepared)]=prepared
    if shell is not None:_TOKEN_FILLED[id(shell)]=prepared
    _seal_prepared_facts(prepared,source_kind,path.path,shell=shell,syn_binding=syn_binding,syn_entry=syn_entry)
    validate_prepared(prepared)
    return prepared


def _prepare_group_transport(actual_sender,issued_request,deadline_clock_tcb,*,tcb=None,source_kind='OPERATOR_ATTESTED'):
    if (type(actual_sender) is not HTTPSender or actual_sender.enabled is not True
            or type(issued_request) is not HTTPRequest or type(deadline_clock_tcb) is not GroupDeadline):fail()
    if type(source_kind) is not str or source_kind not in ('OPERATOR_ATTESTED','SYNTHETIC_SETUP'):fail()
    checked_tcb=validate_transport_tcb(tcb);deadline_clock_tcb.remaining()
    path=urlsplit(issued_request.path)
    if (path.path not in _ENDPOINTS or issued_request.method!='POST'
            or type(issued_request.body) is not bytes or type(issued_request.headers) is not dict
            or issued_request.headers!={'Content-Type':'application/json; charset=utf-8'}):fail()
    binding=entry=None
    if source_kind=='SYNTHETIC_SETUP':
        from .draft_group_rich_syn_transport import binding_for_prepared_entry
        binding,entry=binding_for_prepared_entry()
        if actual_sender is not entry.service.workflow.sender:fail()
    return _assemble_prepared(actual_sender,issued_request,deadline_clock_tcb,checked_tcb,source_kind,
        _new_transport_resources(binding,entry),syn_binding=binding,syn_entry=entry)


@dataclass(frozen=True,slots=True)
class _PreparedFacts:
    prepared: object=field(repr=False)
    deadline: object=field(repr=False)
    deadline_values: tuple
    token: bool
    synthetic: bool
    source_kind: str
    route: str
    request_identity: object=field(repr=False)
    request_body_sha: str|None
    request_pin: tuple=field(repr=False)
    handlers_pin: tuple=field(repr=False)
    context_pin: tuple=field(repr=False)
    tcb: object=field(repr=False)
    opener: object=field(repr=False)
    handler: object=field(repr=False)
    context: object=field(repr=False)
    host: str
    thread: int
    token_shell: object=None
    syn_binding: object=None
    syn_entry: object=None


def _seal_prepared_facts(prepared,source_kind,route,*,shell=None,syn_binding=None,syn_entry=None):
    # Facts alone are not a used owner or a capture issuer. The standalone TLS
    # component uses these pins but can receive only unissued FramedBodyFacts.
    if id(prepared) in _PREPARED_FACTS or type(prepared.deadline) not in (GroupDeadline,GroupTokenOuterDeadline):fail()
    d=prepared.deadline
    values=(type(d),type(d.deadline),d.deadline,type(d.timeout),d.timeout)
    if type(prepared.token) is not bool or type(prepared.synthetic) is not bool:fail()
    facts=_PreparedFacts(prepared,d,values,prepared.token,prepared.synthetic,source_kind,route,
        prepared.request,None if prepared.token else sha256(prepared.request.data).hexdigest(),
        _request_pin(prepared.request),_handler_pin(prepared.opener),_ssl_context_pin(prepared.context),
        prepared.tcb,prepared.opener,prepared.handler,prepared.context,prepared.host,prepared.thread,shell,syn_binding,syn_entry)
    _PREPARED_FACTS[id(prepared)]=facts
    return facts


def _route_deadline_facts(prepared):
    facts=_PREPARED_FACTS.get(id(prepared))
    if (facts is None or facts.prepared is not prepared or prepared.deadline is not facts.deadline
            or prepared.tcb is not facts.tcb or prepared.opener is not facts.opener or prepared.handler is not facts.handler
            or prepared.context is not facts.context or type(prepared.host) is not str or prepared.host!=facts.host
            or prepared.thread!=facts.thread or facts.thread!=threading.get_ident()):fail()
    d=prepared.deadline
    if (type(d) not in (GroupDeadline,GroupTokenOuterDeadline) or (type(d),type(d.deadline),d.deadline,type(d.timeout),d.timeout)!=facts.deadline_values
            or type(prepared.token) is not bool or prepared.token is not facts.token
            or type(prepared.synthetic) is not bool or prepared.synthetic is not facts.synthetic):fail()
    if facts.syn_binding is not None:
        from .draft_group_rich_syn_transport import validate_binding_for_entry
        validate_binding_for_entry(facts.syn_binding,facts.syn_entry)
    if facts.token_shell is not None:
        _shell_identity(facts.token_shell)
        if _TOKEN_FILLED.get(id(facts.token_shell)) is not prepared:fail()
    return facts


def validate_prepared_identity_pure(prepared):
    """Gap identity only: no clock, file, domain, SSL API or source callback."""
    namespace,builtins,primitives,functions,classes,error,class_vars,length,runtime_error,missing,external,paired=_GAP_IDENTITY_TCB
    # Captured builtins inspect class dictionaries without invoking object hooks.
    # Check the error class first, using an immutable builtin on its corruption.
    rejection=runtime_error
    for owner,name,cls,bases,mro,attributes in classes:
        actual_bases=cls.__bases__;actual_mro=cls.__mro__
        if length(actual_bases)!=length(bases) or length(actual_mro)!=length(mro):raise rejection('GROUP_TRANSPORT_UNQUALIFIED')
        for actual,original in paired(actual_bases,bases):
            if actual is not original:raise rejection('GROUP_TRANSPORT_UNQUALIFIED')
        for actual,original in paired(actual_mro,mro):
            if actual is not original:raise rejection('GROUP_TRANSPORT_UNQUALIFIED')
        current=class_vars(cls)
        if owner.get(name,missing) is not cls or length(current)!=length(attributes):raise rejection('GROUP_TRANSPORT_UNQUALIFIED')
        for key,member,code in attributes:
            actual=current.get(key,missing)
            if actual is not member or (code is not None and actual.__code__ is not code):raise rejection('GROUP_TRANSPORT_UNQUALIFIED')
        rejection=error
    for name,primitive in primitives:
        if namespace.get(name,builtins.get(name)) is not primitive:raise error('GROUP_TRANSPORT_UNQUALIFIED')
    for owner,name,function in external:
        if owner.get(name) is not function:raise error('GROUP_TRANSPORT_UNQUALIFIED')
    for name,function,code in functions:
        if namespace.get(name) is not function or function.__code__ is not code:raise error('GROUP_TRANSPORT_UNQUALIFIED')
    request_pin=functions[0][1];handler_pin=functions[1][1];thread_ident=external[0][2]
    if type(prepared) is not PreparedTransport or _PREPARED.get(id(prepared)) is not prepared:fail()
    facts=_PREPARED_FACTS.get(id(prepared))
    if (type(facts) is not _PreparedFacts or facts.prepared is not prepared or facts.thread!=thread_ident()
            or prepared.thread!=facts.thread or prepared._used is not False
            or prepared.request is not facts.request_identity or prepared.opener is not facts.opener
            or prepared.handler is not facts.handler or prepared.context is not facts.context
            or prepared.deadline is not facts.deadline or prepared.tcb is not facts.tcb
            or type(prepared.host) is not str or prepared.host!=facts.host
            or prepared.connection is not None or prepared.socket is not None or prepared.response is not None
            or type(prepared.token) is not bool or prepared.token is not facts.token
            or type(prepared.synthetic) is not bool or prepared.synthetic is not facts.synthetic):fail()
    d=prepared.deadline
    if (type(d) not in (GroupDeadline,GroupTokenOuterDeadline)
            or (type(d),type(d.deadline),d.deadline,type(d.timeout),d.timeout)!=facts.deadline_values
            or type(prepared.context) is not ssl.SSLContext or type(prepared.handler) is not GroupHTTPSHandler
            or prepared.handler._context is not facts.context
            or request_pin(prepared.request)!=facts.request_pin
            or handler_pin(prepared.opener)!=facts.handlers_pin):fail()
    return None


def _remaining(prepared):
    facts=_route_deadline_facts(prepared)
    record=_TOKEN_IO_DEADLINES.get(id(prepared))
    if record is not None:
        if record[0] is not prepared or record[1] is not facts:fail()
        return GroupDeadline.remaining(record[2])
    return facts.deadline.remaining()


def _token_io_end_at(original_outer,now):
    if (type(original_outer) not in (int,float) or type(now) is not float
            or not math.isfinite(original_outer) or not math.isfinite(now) or not now<original_outer):fail()
    return min(original_outer,now+10)


def _begin_token_io(prepared,facts,used):
    if (not facts.token or type(facts.deadline) is not GroupTokenOuterDeadline
            or used is None or used[0] is not prepared or used[3] is not facts
            or _EXCHANGE_USED.get(id(prepared)) is not used or id(prepared) in _TOKEN_IO_DEADLINES):fail()
    if time.monotonic is not _MONOTONIC:fail()
    end=_token_io_end_at(facts.deadline.deadline,_MONOTONIC())
    _TOKEN_IO_DEADLINES[id(prepared)]=(prepared,facts,GroupDeadline(end,10))


def validate_prepared(prepared):
    if type(prepared) is not PreparedTransport:fail()
    validate_transport_tcb(prepared.tcb)
    facts=_route_deadline_facts(prepared)
    if facts.token_shell is not None:validate_token_transport_shell(facts.token_shell)
    facts.deadline.remaining()
    expected_host=prepared.host
    if facts.syn_binding is not None:
        from .draft_group_rich_syn_transport import validate_binding_for_entry
        expected_host+=':'+str(validate_binding_for_entry(facts.syn_binding,facts.syn_entry).listener_address[1])
    if (type(prepared) is not PreparedTransport or _PREPARED.get(id(prepared)) is not prepared
            or prepared.thread!=threading.get_ident() or prepared._used
            or prepared.request is not _route_deadline_facts(prepared).request_identity
            or _request_pin(prepared.request)!=facts.request_pin
            or _handler_pin(prepared.opener)!=facts.handlers_pin
            or type(prepared.context) is not ssl.SSLContext
            or prepared.context.protocol!=ssl.PROTOCOL_TLS_CLIENT
            or prepared.context.verify_mode!=ssl.CERT_REQUIRED
            or prepared.context.check_hostname is not True
            or facts.context_pin!=_ssl_context_pin(prepared.context)
            or prepared.handler._context is not prepared.context
            or prepared.request.host!=expected_host):fail()
    validate_transport_tcb(prepared.tcb)
    return None


@dataclass(frozen=True, slots=True)
class CapturedGroupOutcome:
    response: HTTPResponse = field(repr=False)
    framing: str
    completed_at_ms: int
    transport_origin: str


@dataclass(frozen=True, slots=True)
class TokenTransportCapture:
    response: HTTPResponse = field(repr=False)


@dataclass(frozen=True, slots=True)
class NoQualifiedDisposition:
    reason: str = 'NO_COMPLETE_TRANSPORT'



@dataclass(frozen=True,slots=True)
class FramedBodyFacts:
    response: HTTPResponse=field(repr=False)
    framing: str
    authority: bool=False


@dataclass(frozen=True,slots=True)
class _ArrivalWitness:
    arrival: object=field(repr=False)
    prepared: object=field(repr=False)
    thread: int
    facts: _PreparedFacts=field(repr=False)
    owner: object=field(repr=False)
    admission: object=field(repr=False)


def _exchange_group_prepared_once(used_owner, prepared):
    validate_prepared(prepared)
    from .draft_group_runtime_host import validate_used_transport_owner
    actual=validate_used_transport_owner(used_owner,prepared)
    if actual is not used_owner:fail()
    facts=_route_deadline_facts(prepared)
    if facts.synthetic and facts.syn_binding is None:fail()
    if facts.token:
        from .draft_group_token_runtime import GroupEffectOwner
        if (type(used_owner) is not GroupEffectOwner
                or used_owner.controller.host.chain.config['binding']['source_kind']!=facts.source_kind
                or facts.route!='/cgi-bin/stable_token' or facts.token_shell is None
                or getattr(used_owner.controller,'transport_shell',None) is not facts.token_shell):fail()
        admission=None
    else:
        from .draft_group_provider import bind_used_group_admission
        admission=bind_used_group_admission(used_owner,prepared,facts)
    _EXCHANGE_USED[id(prepared)]=(prepared,used_owner,admission,facts)
    prepared._used=True
    if facts.syn_binding is not None:
        from .draft_group_rich_syn_transport import bind_original_used_request,finish_original_used_request
        stage='TOKEN_POST' if facts.token else admission.syn_stage
        try:
            bind_original_used_request(facts.syn_binding,facts.syn_entry,prepared,stage)
            return _exchange_registered(prepared)
        finally:finish_original_used_request(facts.syn_binding)
    return _exchange_registered(prepared)


def _exchange_registered(prepared):
    response=None;closed=False
    facts=_route_deadline_facts(prepared)
    used=_EXCHANGE_USED.get(id(prepared))
    if (facts.token or facts.syn_binding is not None) and used is None:fail()
    try:
        _ACTIVE.prepared=prepared
        if facts.token and used is not None:_begin_token_io(prepared,facts,used)
        _remaining(prepared)
        try:response=ur.OpenerDirector.open(prepared.opener,prepared.request,timeout=_remaining(prepared))
        except HTTPError as error:
            if error.fp is not prepared.response:fail()
            response=error.fp
        _remaining(prepared)
        if (response is not prepared.response or type(response) is not GroupStrictHTTPResponse
                or prepared.connection is None or prepared.socket is not response._group_socket
                or prepared.socket.suppress_ragged_eofs is not False):fail()
        body=GroupStrictHTTPResponse.read_framed(response)
        _remaining(prepared)
        status=response.status
        if type(status) is not int or not 200<=status<=599:fail()
        response.close();closed=True
        _remaining(prepared)
        result=HTTPResponse(status,body)
        if used is None:
            # A real socket/framing component result is deliberately not an
            # issued capture and cannot be consumed by either production API.
            return FramedBodyFacts(result,response._group_mode)
        if used[0] is not prepared or used[3] is not facts:fail()
        capture=(TokenTransportCapture(result) if facts.token else
            CapturedGroupOutcome(result,response._group_mode,int(_WALL()*1000),
                'SYNTHETIC_GROUP_TRANSPORT_V1' if facts.synthetic else 'OFFICIAL_GROUP_PREPARED_TLS_V1'))
        _CAPTURES[id(capture)]=_ArrivalWitness(capture,prepared,threading.get_ident(),facts,used[1],used[2])
        return capture
    except Exception:
        disposition=NoQualifiedDisposition()
        if used is not None:
            _DISPOSITIONS[id(disposition)]=_ArrivalWitness(disposition,prepared,threading.get_ident(),facts,used[1],used[2])
        return disposition
    finally:
        if response is not None and not closed:
            try:response.close()
            except Exception:pass
        _ACTIVE.prepared=None;prepared.request=None;prepared._pin=None
        _PREPARED.pop(id(prepared),None);_PREPARED_FACTS.pop(id(prepared),None);_EXCHANGE_USED.pop(id(prepared),None);_TOKEN_IO_DEADLINES.pop(id(prepared),None)


def consume_capture(capture):
    witness=_CAPTURES.pop(id(capture),None)
    if (witness is None or witness.arrival is not capture or witness.thread!=threading.get_ident()
            or type(capture) is not CapturedGroupOutcome or witness.facts.token or witness.admission is None):fail()
    _CONSUMED_ARRIVALS[id(capture)]=witness
    return capture


def consume_token_capture(capture):
    if type(capture) is NoQualifiedDisposition:
        witness=_DISPOSITIONS.pop(id(capture),None)
        if witness is None or witness.arrival is not capture or witness.thread!=threading.get_ident() or not witness.facts.token:fail()
        fail()
    witness=_CAPTURES.pop(id(capture),None)
    if (witness is None or witness.arrival is not capture or witness.thread!=threading.get_ident()
            or type(capture) is not TokenTransportCapture or not witness.facts.token or witness.admission is not None):fail()
    return capture.response


def consume_disposition(disposition):
    witness=_DISPOSITIONS.pop(id(disposition),None)
    if (witness is None or witness.arrival is not disposition or witness.thread!=threading.get_ident()
            or not witness.prepared._used or witness.facts.token or witness.admission is None):fail()
    _CONSUMED_ARRIVALS[id(disposition)]=witness
    return disposition


def validate_arrival_for_archive(arrival,primary,expected_prepared,expected_pending):
    witness=_CONSUMED_ARRIVALS.get(id(arrival))
    if (witness is None or witness.arrival is not arrival or witness.thread!=threading.get_ident()
            or witness.prepared is not expected_prepared or witness.facts.prepared is not expected_prepared
            or witness.facts.token or witness.admission is None):fail()
    from .draft_group_provider import validate_bound_group_admission
    validate_bound_group_admission(witness.admission,witness.owner,expected_prepared,expected_pending,primary)
    transport=primary['transport']
    if witness.facts.request_body_sha!=transport['request_body_sha']:fail()
    endpoint={'/cgi-bin/draft/batchget':'BATCHGET','/cgi-bin/draft/get':'GET','/cgi-bin/draft/add':'ADD','/cgi-bin/draft/delete':'DELETE'}.get(witness.facts.route)
    if endpoint is None or transport['endpoint']!=endpoint:fail()
    if type(arrival) is CapturedGroupOutcome:
        if (transport['origin']!=arrival.transport_origin or transport['http_status']!=arrival.response.status
                or transport['response_body_sha']!=sha256(arrival.response.body).hexdigest()):fail()
    elif type(arrival) is NoQualifiedDisposition:
        if transport['origin']!='NO_QUALIFIED_RESPONSE' or transport['http_status'] is not None or transport['response_body_sha'] is not None:fail()
    else:fail()
    return witness.prepared


def forget_archived_arrival(arrival):
    _CONSUMED_ARRIVALS.pop(id(arrival),None)


def discard_prepared(prepared):
    if type(prepared) is not PreparedTransport or prepared.thread!=threading.get_ident():fail()
    if _PREPARED.get(id(prepared)) is prepared:
        prepared._used=True;prepared.request=None;prepared._pin=None
        _PREPARED.pop(id(prepared),None);_PREPARED_FACTS.pop(id(prepared),None);_EXCHANGE_USED.pop(id(prepared),None);_TOKEN_IO_DEADLINES.pop(id(prepared),None)


def discard_current_thread_prepared():
    for prepared in tuple(_PREPARED.values()):
        if prepared.thread==threading.get_ident():discard_prepared(prepared)
    for facts in tuple(_TOKEN_SHELLS.values()):
        if facts.thread==threading.get_ident():discard_token_transport_shell(facts.shell)


class TokenTransportShell:
    __slots__=('sender','source_kind','deadline','context','handler','opener','tcb','thread')
    def __init__(self):fail()
    def __repr__(self):return '<GroupTokenTransportShell>'


@dataclass(frozen=True,slots=True)
class _TokenShellFacts:
    shell: object=field(repr=False)
    sender: object=field(repr=False)
    source_kind: str
    deadline_type: type
    deadline: float
    context: object=field(repr=False)
    handler: object=field(repr=False)
    opener: object=field(repr=False)
    tcb: object=field(repr=False)
    thread: int
    context_pin: tuple=field(repr=False)
    handlers_pin: tuple=field(repr=False)
    syn_binding: object=None
    syn_entry: object=None


def _shell_identity(shell):
    facts=_TOKEN_SHELLS.get(id(shell))
    if (type(shell) is not TokenTransportShell or facts is None or facts.shell is not shell
            or facts.thread!=threading.get_ident() or shell.thread!=facts.thread
            or shell.sender is not facts.sender or type(shell.sender) is not HTTPSender or shell.sender.enabled is not True
            or type(shell.source_kind) is not str or shell.source_kind!=facts.source_kind
            or type(shell.deadline) is not facts.deadline_type or shell.deadline!=facts.deadline
            or shell.context is not facts.context or shell.handler is not facts.handler
            or shell.opener is not facts.opener or shell.tcb is not facts.tcb):fail()
    return facts


def validate_token_transport_shell(shell):
    facts=_shell_identity(shell)
    validate_transport_tcb(facts.tcb)
    if facts.syn_binding is not None:
        from .draft_group_rich_syn_transport import validate_binding_for_entry
        validate_binding_for_entry(facts.syn_binding,facts.syn_entry)
    if (_ssl_context_pin(facts.context)!=facts.context_pin or _handler_pin(facts.opener)!=facts.handlers_pin
            or facts.context.verify_mode!=ssl.CERT_REQUIRED or facts.context.check_hostname is not True
            or facts.handler._context is not facts.context):fail()
    # Original entry outer bound, not a prematurely started ten-second network
    # lease. A's final fixed primitive samples still run after this pure fence.
    now=_MONOTONIC()
    if time.monotonic is not _MONOTONIC or not math.isfinite(now) or not now<facts.deadline<=now+300.001:fail()
    return None


def prepare_token_transport_shell(sender,source_kind,deadline):
    if (type(sender) is not HTTPSender or sender.enabled is not True or type(source_kind) is not str
            or source_kind not in ('OPERATOR_ATTESTED','SYNTHETIC_SETUP')
            or type(deadline) not in (int,float) or not math.isfinite(deadline)):fail()
    now=_MONOTONIC()
    if not now<deadline<=now+300.001:fail()
    tcb=validate_transport_tcb();binding=entry=None
    if source_kind=='SYNTHETIC_SETUP':
        from .draft_group_rich_syn_transport import binding_for_prepared_entry
        binding,entry=binding_for_prepared_entry()
        if sender is not entry.service.workflow.sender:fail()
    context,handler,opener=_new_transport_resources(binding,entry)
    shell=object.__new__(TokenTransportShell)
    shell.sender=sender;shell.source_kind=source_kind;shell.deadline=deadline
    shell.context=context;shell.handler=handler;shell.opener=opener;shell.tcb=tcb;shell.thread=threading.get_ident()
    facts=_TokenShellFacts(shell,sender,source_kind,type(deadline),deadline,context,handler,opener,tcb,shell.thread,
        _ssl_context_pin(context),_handler_pin(opener),binding,entry)
    _TOKEN_SHELLS[id(shell)]=facts;validate_token_transport_shell(shell)
    return shell


def fill_token_request(shell,issued_request):
    validate_token_transport_shell(shell);facts=_shell_identity(shell)
    if id(shell) in _TOKEN_FILLED:fail()
    if (type(issued_request) is not HTTPRequest or issued_request.path!='/cgi-bin/stable_token'
            or issued_request.method!='POST' or type(issued_request.body) is not bytes
            or issued_request.headers!={'Content-Type':'application/json; charset=utf-8'}):fail()
    deadline=GroupTokenOuterDeadline(facts.deadline,10)
    try:
        return _assemble_prepared(facts.sender,issued_request,deadline,facts.tcb,facts.source_kind,
            (facts.context,facts.handler,facts.opener),shell=shell,syn_binding=facts.syn_binding,syn_entry=facts.syn_entry)
    except BaseException:
        discard_token_transport_shell(shell);raise


def discard_token_transport_shell(shell):
    facts=_TOKEN_SHELLS.get(id(shell))
    if facts is None:return
    if facts.shell is not shell or facts.thread!=threading.get_ident():fail()
    prepared=_TOKEN_FILLED.pop(id(shell),None)
    if type(prepared) is PreparedTransport:discard_prepared(prepared)
    _TOKEN_SHELLS.pop(id(shell),None)
    shell.context=None;shell.handler=None;shell.opener=None;shell.sender=None



def validate_syn_prepared_transport_in(prepared,entry):
    validate_prepared(prepared);facts=_route_deadline_facts(prepared)
    if not facts.synthetic or facts.token or facts.syn_binding is None or facts.syn_entry is not entry:fail()
    return facts


def _make_gap_identity_tcb():
    import builtins
    namespace=globals();builtin_namespace=vars(builtins)
    primitive_names=('type','id','vars','len','dict','list','tuple','str','int','float','bool','bytes','any','sorted','zip','ur','ssl','threading','_PREPARED','_PREPARED_FACTS')
    primitives=tuple((name,namespace.get(name,builtin_namespace.get(name))) for name in primitive_names)
    functions=tuple((name,namespace[name],namespace[name].__code__) for name in
        ('_request_pin','_handler_pin','_registry_pin','fail','validate_prepared_identity_pure'))
    selected=[(namespace,'WCEError',WCEError)]
    selected.extend((namespace,cls.__name__,cls) for cls in
        (PreparedTransport,_PreparedFacts,GroupDeadline,GroupTokenOuterDeadline,NoRedirect,GroupHTTPSHandler))
    selected.extend((vars(ur),cls.__name__,cls) for cls in
        (ur.BaseHandler,ur.HTTPRedirectHandler,ur.AbstractHTTPHandler,ur.HTTPSHandler,
         ur.Request,ur.OpenerDirector,ur.ProxyHandler,ur.UnknownHandler,ur.HTTPHandler,
         ur.HTTPDefaultErrorHandler,ur.FTPHandler,ur.FileHandler,ur.DataHandler,ur.HTTPErrorProcessor))
    selected.append((vars(ssl),'SSLContext',ssl.SSLContext))
    classes=tuple((owner,name,cls,cls.__bases__,cls.__mro__,tuple((key,value,value.__code__ if type(value) is types.FunctionType else None)
        for key,value in vars(cls).items())) for owner,name,cls in selected)
    return (namespace,builtin_namespace,primitives,functions,classes,WCEError,vars,len,RuntimeError,object(),
        ((vars(threading),'get_ident',threading.get_ident),),zip)


_GAP_IDENTITY_TCB=_make_gap_identity_tcb()

_BASE_REFS=_primitive_refs()
