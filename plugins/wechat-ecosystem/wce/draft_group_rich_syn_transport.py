"""Actual C1 loopback TLS resources; A alone issues the synthetic domain.

No public endpoint, caller authority flags or standalone-capture issuer. The
production A table is empty. Resource preparation does not issue a send owner.
"""
from dataclasses import dataclass,field
from hashlib import sha256
from pathlib import Path
import math,os,socket,ssl,subprocess,threading,time
from .contracts import WCEError

SCENARIO='WCE_RICH_SYN_NEW_ONLY_EMPTY_ACCOUNT_C1_V1'
SEQUENCE=('TOKEN_POST','PREVIEW_ACCOUNT:LIST:1','PREVIEW_ACCOUNT:LIST:2','CHILD:ADD','CHILD:GET:NEW','CHILD:GET:FINAL_NEW')
CONFIG_SHA='840ffead94b7701acfccbcae0a9c40d1980d13f7bd5dcbaa0ef3138791d229f9'
OPENSSL_SHA='49db04c17e3a8c169ebc48a1149d78c165a86c04913203f46b2a14ce7f4a14fc'
_DOMAIN_BINDINGS={};_BINDINGS={};_PKI_ATTEMPTS={};_INFLIGHT={}
_MONOTONIC=time.monotonic


def fail():raise WCEError('GROUP_RICH_SYN_TRANSPORT_HOLD')


def _file_pin(path,*,directory=False):
    from .own_bootstrap_security import path_check
    return path_check(path,directory)


def _read_public(path,maximum):
    before=_file_pin(path)
    fd=os.open(path,os.O_RDONLY|os.O_NOFOLLOW|os.O_NONBLOCK)
    try:
        if os.fstat(fd).st_size>maximum:fail()
        with os.fdopen(fd,'rb',closefd=False) as source:raw=source.read(maximum+1)
        if len(raw)>maximum or _file_pin(path)!=before:fail()
        return raw,before
    finally:os.close(fd)


def _directory_identity(info):
    return info.st_dev,info.st_ino,info.st_uid,info.st_mode,info.st_nlink


def _output_identity(info):
    return info.st_dev,info.st_ino,info.st_uid,info.st_mode,info.st_nlink


def _open_parent_fds(root):
    held=[];current=Path('/');fd=None
    try:
        fd=os.open('/',os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW|os.O_NONBLOCK)
        held.append((current,fd,_directory_identity(os.fstat(fd))))
        for part in root.parts[1:]:
            current=current/part
            next_fd=os.open(part,os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW|os.O_NONBLOCK,dir_fd=fd)
            fd=next_fd;pin=_directory_identity(os.fstat(fd))
            if _directory_identity(current.lstat())!=pin:fail()
            held.append((current,fd,pin))
        return tuple(held)
    except BaseException:
        for _,owned,_ in reversed(held):os.close(owned)
        raise


def _check_parent_fds(held):
    for path,fd,pin in held:
        if _directory_identity(os.fstat(fd))!=pin or _directory_identity(path.lstat())!=pin:fail()



def _seal_reserved_parent_fds(held,before_names,outputs):
    # The two exclusive creations are our only permitted membership change.
    # Keep the original directory FDs; never reopen/rebase a changed parent.
    _check_parent_fds(held[:-1])
    directory,fd,original=held[-1]
    current=_directory_identity(os.fstat(fd))
    if (current[:-1]!=original[:-1] or _directory_identity(directory.lstat())!=current
            or type(before_names) is not frozenset
            or tuple(path.name for path,_,_ in outputs)!=('syn-c1-key.pem','syn-c1-cert.pem')):fail()
    expected=before_names|{'syn-c1-key.pem','syn-c1-cert.pem'}
    if len(expected)!=len(before_names)+2 or frozenset(os.listdir(fd))!=expected:fail()
    for path,output_fd,created in outputs:
        if (path.parent!=directory or _output_identity(os.fstat(output_fd))!=created
                or _output_identity(os.stat(path.name,dir_fd=fd,follow_symlinks=False))!=created
                or created[-1]!=1):fail()
    return held[:-1]+((directory,fd,current),)



class RichSYNTransportBinding:
    __slots__=()
    def __init__(self):fail()


@dataclass(frozen=True,slots=True)
class _ResourceFacts:
    binding: object=field(repr=False)
    domain: object=field(repr=False)
    policy: object=field(repr=False)
    generation: int
    owner_thread: int
    root: object=field(repr=False)
    root_pin: tuple
    tmp_pin: tuple
    certificate: object=field(repr=False)
    private_key: object=field(repr=False)
    certificate_pin: tuple
    private_key_pin: tuple
    certificate_der_sha: str
    client_context: object=field(repr=False)
    server_context: object=field(repr=False)
    context_pin: tuple=field(repr=False)
    server_pin: tuple=field(repr=False)
    listener: object=field(repr=False)
    listener_fd: int
    listener_address: tuple
    replies: tuple=field(repr=False)
    response_pins: tuple=field(repr=False)
    parent_fds: tuple=field(repr=False)
    state: object=field(repr=False)


class _RunState:
    def __init__(self):
        self.entry=None;self.deadline=None;self.thread=None;self.stop=threading.Event()
        self.connections=0;self.completed=0;self.failed=False;self.closed=False
        self.active_socket=None


def _domain_facts(domain,*,entry=None):
    from .draft_group_rich_syn_fixture import validate_rich_syn_domain
    facts=validate_rich_syn_domain(domain,entry=entry)
    if (facts.scenario_id!=SCENARIO or tuple(facts.sequence)!=SEQUENCE
            or facts.max_connection_upper!=6 or facts.thread!=threading.get_ident()):fail()
    return facts


def _resource(binding,domain):
    r=_BINDINGS.get(id(binding))
    if (type(binding) is not RichSYNTransportBinding or r is None or r.binding is not binding
            or r.domain is not domain or r.owner_thread!=threading.get_ident() or r.state.closed):fail()
    return r


def validate_rich_syn_transport_binding(binding,domain):
    """Fixed resource pins only. No current/Root/full/owner callbacks."""
    r=_resource(binding,domain);facts=_domain_facts(domain)
    _check_parent_fds(r.parent_fds)
    from .draft_group_transport import _ssl_context_pin
    if (facts.policy is not r.policy or facts.generation!=r.generation
            or Path(facts.transport_resource_root)!=r.root or _file_pin(r.root,directory=True)!=r.root_pin
            or _file_pin(r.root/'tmp',directory=True)!=r.tmp_pin
            or _file_pin(r.certificate)!=r.certificate_pin or _file_pin(r.private_key)!=r.private_key_pin
            or _ssl_context_pin(r.client_context)!=r.context_pin or _ssl_context_pin(r.server_context)!=r.server_pin
            or type(r.listener) is not socket.socket or r.listener.fileno()!=r.listener_fd
            or r.listener.getsockname()!=r.listener_address or r.listener_address[0]!='127.0.0.1'
            or r.client_context.verify_mode!=ssl.CERT_REQUIRED or r.client_context.check_hostname is not True
            or tuple(sha256(c).hexdigest() for c in r.client_context.get_ca_certs(binary_form=True))!=(r.certificate_der_sha,)
            or r.state.connections>6 or r.state.failed):fail()
    for path,pin in r.response_pins:
        if _file_pin(path)!=pin:fail()
    return None


def prepare_rich_syn_transport_resources(domain):
    """Exactly one approved openssl invocation; no accept thread until entry."""
    from .draft_group_transport import validate_transport_tcb
    validate_transport_tcb()
    facts=_domain_facts(domain)
    if facts.phase!='PREPARING' or id(domain) in _DOMAIN_BINDINGS:fail()
    root=Path(facts.transport_resource_root)
    root_pin=_file_pin(root,directory=True);tmp_pin=_file_pin(root/'tmp',directory=True)
    config=root/'tests/syn-c1-openssl.cnf';raw,_=_read_public(config,4096)
    if sha256(raw).hexdigest()!=CONFIG_SHA:fail()
    replies=[];response_pins=[]
    for expected,item in zip(SEQUENCE,facts.response_fixtures,strict=True):
        stage,path,checksum,size=item
        if stage!=expected or type(size) is not int or not 0<size<=2*1024*1024:fail()
        path=Path(path)
        if not (path.is_relative_to(Path(facts.fixture_root)) or path.is_relative_to(root)):fail()
        body,pin=_read_public(path,2*1024*1024)
        if len(body)!=size or sha256(body).hexdigest()!=checksum:fail()
        replies.append(body);response_pins.append((Path(path),pin))
    exe=Path('/usr/bin/openssl');st=exe.lstat()
    if exe.is_symlink() or st.st_uid!=0 or st.st_mode&0o777!=0o755 or sha256(exe.read_bytes()).hexdigest()!=OPENSSL_SHA:fail()
    key=root/'tmp/syn-c1-key.pem';cert=root/'tmp/syn-c1-cert.pem'
    if os.path.lexists(key) or os.path.lexists(cert) or id(domain) in _PKI_ATTEMPTS:fail()
    argv=['/usr/bin/openssl','req','-x509','-newkey','rsa:2048','-nodes','-keyout',str(key),'-out',str(cert),'-days','1','-config',str(config)]
    parents=_open_parent_fds(root/'tmp');before_names=frozenset(os.listdir(parents[-1][1]))
    _PKI_ATTEMPTS[id(domain)]=domain;mask=os.umask(0o077)
    listener=None;binding=None;outputs=[]
    try:
        for path in (key,cert):
            fd=os.open(path.name,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW|os.O_NONBLOCK,0o600,dir_fd=parents[-1][1])
            outputs.append((path,fd,_output_identity(os.fstat(fd))))
        parents=_seal_reserved_parent_fds(parents,before_names,outputs)
        _check_parent_fds(parents)
        environment={'PATH':'/usr/bin:/bin','TMPDIR':str(root/'tmp'),'LANG':'C','LC_ALL':'C'}
        subprocess.run(argv,check=True,timeout=15,cwd=str(root),env=environment,
            stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
        if _file_pin(root,directory=True)!=root_pin or _file_pin(root/'tmp',directory=True)!=tmp_pin:fail()
        for path,fd,created in outputs:
            if _output_identity(os.fstat(fd))!=created or _output_identity(path.lstat())!=created:fail()
        kp=_file_pin(key);cp=_file_pin(cert)
        public,_=_read_public(cert,16384);der=ssl.PEM_cert_to_DER_cert(public.decode('ascii'))
        der_sha=sha256(der).hexdigest()
        server=ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER);server.keylog_filename=None;server.load_cert_chain(str(cert),str(key))
        client=ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT);client.check_hostname=True;client.verify_mode=ssl.CERT_REQUIRED
        client.keylog_filename=None;client.load_verify_locations(cafile=str(cert))
        listener=socket.socket(socket.AF_INET,socket.SOCK_STREAM);listener.bind(('127.0.0.1',0));listener.listen(6);listener.settimeout(.25)
        from .draft_group_transport import _ssl_context_pin
        binding=object.__new__(RichSYNTransportBinding);state=_RunState()
        record=_ResourceFacts(binding,domain,facts.policy,facts.generation,threading.get_ident(),root,root_pin,tmp_pin,cert,key,cp,kp,der_sha,client,server,_ssl_context_pin(client),_ssl_context_pin(server),listener,listener.fileno(),listener.getsockname(),tuple(replies),tuple(response_pins),parents,state)
        _BINDINGS[id(binding)]=record;_DOMAIN_BINDINGS[id(domain)]=binding
        validate_rich_syn_transport_binding(binding,domain)
        from .draft_group_rich_syn_fixture import register_rich_syn_transport_binding
        register_rich_syn_transport_binding(domain,binding)
        return binding
    except BaseException as error:
        if binding is not None:
            _DOMAIN_BINDINGS.pop(id(domain),None);_BINDINGS.pop(id(binding),None)
        if listener is not None:listener.close()
        unsafe=False
        for path,fd,created in outputs:
            if os.path.lexists(path):
                try:
                    if _output_identity(path.lstat())!=created or _output_identity(os.fstat(fd))!=created:unsafe=True
                    else:path.unlink()
                except OSError:unsafe=True
        for _,fd,_ in reversed(parents):os.close(fd)
        if unsafe:raise WCEError('GROUP_RICH_SYN_CLEANUP_IDENTITY_CHANGED') from error
        raise
    finally:
        for _,fd,_ in outputs:os.close(fd)
        os.umask(mask)


def _server_remaining(r):
    now=_MONOTONIC()
    if type(now) is not float or not math.isfinite(now) or r.state.deadline is None or now>=r.state.deadline:fail()
    return min(2,r.state.deadline-now)


def _server_io(r,sock,method,*args):
    if r.state.stop.is_set():fail()
    sock.settimeout(_server_remaining(r));result=method(*args)
    _server_remaining(r)
    return result


def _serve(r):
    state=r.state
    while not state.stop.is_set() and _MONOTONIC()<state.deadline and state.connections<6:
        try:raw,peer=r.listener.accept()
        except socket.timeout:continue
        except OSError:break
        sock=None
        try:
            state.connections+=1
            if peer[0]!='127.0.0.1':fail()
            raw.settimeout(_server_remaining(r))
            sock=r.server_context.wrap_socket(raw,server_side=True);state.active_socket=sock
            _server_remaining(r)
            expected=_INFLIGHT.get(id(r.binding))
            if expected is None or expected[0] is not r.binding or expected[1]!=state.completed:fail()
            data=b''
            while b'\r\n\r\n' not in data:
                part=_server_io(r,sock,sock.recv,4096)
                if not part:fail()
                data+=part
                if len(data)>65536+2*1024*1024:fail()
            header,body=data.split(b'\r\n\r\n',1)
            if len(header)>65536:fail()
            lines=header.split(b'\r\n');method,target,protocol=lines[0].split(b' ')
            fields={}
            for line in lines[1:]:
                name,value=line.split(b':',1);name=name.lower()
                if name in fields:fail()
                fields[name]=value.strip()
            n=fields.get(b'content-length',b'')
            if not n or not n.isdigit() or len(n)>8 or int(n)>2*1024*1024 or b'transfer-encoding' in fields:fail()
            while len(body)<int(n):
                part=_server_io(r,sock,sock.recv,min(65536,int(n)-len(body)))
                if not part:fail()
                body+=part
            if (method!=b'POST' or protocol!=b'HTTP/1.1' or target!=expected[2]
                    or fields.get(b'host')!=('127.0.0.1:'+str(r.listener_address[1])).encode('ascii')
                    or body!=expected[3] or len(body)!=int(n)):fail()
            response=r.replies[state.completed]
            _server_io(r,sock,sock.sendall,b'HTTP/1.1 200 OK\r\nContent-Type: application/json\r\nContent-Length: '+str(len(response)).encode('ascii')+b'\r\nConnection: close\r\n\r\n'+response)
            state.completed+=1
            try:_server_io(r,sock,sock.unwrap).close()
            except (ssl.SSLError,TimeoutError):sock.close()
        except BaseException:state.failed=True;state.stop.set()
        finally:
            state.active_socket=None
            if sock is not None:sock.close()
            else:raw.close()
    state.stop.set()


def prepare_binding_for_entry(entry):
    """Full preparation layer, never called by a final pure validator."""
    from .draft_group_rich_syn_fixture import require_rich_syn_domain_for_entry
    domain=require_rich_syn_domain_for_entry(entry);binding=_DOMAIN_BINDINGS.get(id(domain))
    validate_rich_syn_transport_binding(binding,domain);r=_resource(binding,domain)
    if r.state.entry is None:
        deadline=entry.deadline
        if type(deadline) not in (int,float) or not math.isfinite(deadline) or not _MONOTONIC()<deadline<=_MONOTONIC()+300:fail()
        r.state.entry=entry;r.state.deadline=deadline
        thread=threading.Thread(target=_serve,args=(r,),name='WCE-SYN-C1-TLS',daemon=False)
        r.state.thread=thread;thread.start()
    validate_binding_for_entry(binding,entry)
    return binding


def validate_binding_for_entry(binding,entry):
    from .draft_group_rich_syn_fixture import require_rich_syn_domain_for_entry
    domain=require_rich_syn_domain_for_entry(entry);validate_rich_syn_transport_binding(binding,domain)
    r=_resource(binding,domain)
    if (r.state.entry is not entry or r.state.deadline!=entry.deadline or r.state.thread is None
            or (not r.state.thread.is_alive() and r.state.completed!=6) or not _MONOTONIC()<r.state.deadline):fail()
    return r


def binding_for_prepared_entry():
    from .draft_group_runtime_host import _ACTIVE
    entry=getattr(_ACTIVE,'entry',None)
    if entry is None:fail()
    return prepare_binding_for_entry(entry),entry


def bind_original_used_request(binding,entry,prepared,stage):
    r=validate_binding_for_entry(binding,entry)
    if (r.state.completed>=6 or SEQUENCE[r.state.completed]!=stage or id(binding) in _INFLIGHT):fail()
    # Actual used-owner binding remains in the caller's C transport registry.
    req=prepared.request
    if type(req.selector) is not str or type(req.data) is not bytes:fail()
    wire_target=req.selector.encode('ascii')
    _INFLIGHT[id(binding)]=(binding,r.state.completed,wire_target,req.data)


def finish_original_used_request(binding):
    _INFLIGHT.pop(id(binding),None)


def close_rich_syn_transport_resources(binding):
    r=_BINDINGS.get(id(binding))
    if r is None:return None
    if r.binding is not binding or r.owner_thread!=threading.get_ident():fail()
    r.state.closed=True;r.state.stop.set();r.listener.close()
    active=r.state.active_socket
    if active is not None:
        try:active.shutdown(socket.SHUT_RDWR)
        except OSError:pass
        active.close()
    if r.state.thread is not None:
        remaining=3 if r.state.deadline is None else max(0,min(3,r.state.deadline-_MONOTONIC()))
        r.state.thread.join(remaining)
        if r.state.thread.is_alive():raise WCEError('GROUP_RICH_SYN_WORKER_ACTIVE')
    finish_original_used_request(binding)
    _check_parent_fds(r.parent_fds)
    for path,pin in ((r.private_key,r.private_key_pin),(r.certificate,r.certificate_pin)):
        if _file_pin(path)!=pin:raise WCEError('GROUP_RICH_SYN_CLEANUP_IDENTITY_CHANGED')
        path.unlink()
    for _,fd,_ in reversed(r.parent_fds):os.close(fd)
    _DOMAIN_BINDINGS.pop(id(r.domain),None);_BINDINGS.pop(id(binding),None)
    return None


def transport_tcb_pin():
    import types
    classes=(RichSYNTransportBinding,_ResourceFacts,_RunState)
    class_pins=tuple((cls,tuple((key,id(value),getattr(value,'__code__',None)) for key,value in sorted(vars(cls).items()))) for cls in classes)
    return (class_pins,_MONOTONIC,socket.socket,ssl.SSLContext,threading.Thread,threading.Event,subprocess.run,
        tuple((name,value,value.__code__) for name,value in sorted(globals().items())
        if type(value) is types.FunctionType and value.__module__==__name__ and name!='transport_tcb_pin'))


def rich_syn_transport_status(binding):
    r=_BINDINGS.get(id(binding))
    if r is None or r.binding is not binding or r.owner_thread!=threading.get_ident():fail()
    return {'scenario':SCENARIO,'maximum_connections':6,'connections':r.state.connections,
        'completed':r.state.completed,'failed':r.state.failed,'closed':r.state.closed,
        'worker_alive':False if r.state.thread is None else r.state.thread.is_alive(),'authority':False}
