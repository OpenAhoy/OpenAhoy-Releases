"""Private local tool transport. This does not isolate malicious same-UID code."""
import ctypes
import json
import os
from pathlib import Path
import socket
import stat
import struct
import sys

from .bounded_file import identity
from .contracts import WCEError
from .own_bootstrap_security import decode, path_check, private_read

MAX_FRAME = 1024 * 1024


def peer(connection):
    try:
        if sys.platform == 'darwin':
            uid, gid = ctypes.c_uint(), ctypes.c_uint()
            libc = ctypes.CDLL(None, use_errno=True)
            if libc.getpeereid(connection.fileno(), ctypes.byref(uid), ctypes.byref(gid)) != 0:
                raise ValueError()
            pid = struct.unpack('i', connection.getsockopt(0, 2, 4))[0]  # LOCAL_PEERPID
            return pid, uid.value
        if hasattr(socket, 'SO_PEERCRED'):
            pid, uid, _ = struct.unpack('3i', connection.getsockopt(socket.SOL_SOCKET, socket.SO_PEERCRED, 12))
            return pid, uid
    except Exception:
        pass
    raise WCEError('BOOTSTRAP_PEER_UNAVAILABLE')


def socket_pin(path):
    try:
        p = Path(path)
        path_check(p.parent, True)
        info = p.lstat()
        if not stat.S_ISSOCK(info.st_mode) or info.st_uid != os.getuid() or stat.S_IMODE(info.st_mode) != 0o600:
            raise ValueError()
        return identity(info)
    except Exception:
        raise WCEError('BOOTSTRAP_ENDPOINT_UNAVAILABLE') from None


def _normal_envelope(value):
    """Codec capacity only; the broker still checks runtime, policy and rights."""
    try:
        from .normal_html_limits import POLICY,ENVELOPE_BYTES
        from .own_group_json import normal_limit
        if type(value) is not dict:return False
        if set(value)=={'sequence','result'} and type(value['sequence']) is int and value['sequence']==1:
            result=value['result']
            if type(result) is not dict or 'content_digest' not in result:return False
            from .service import digest
            manifest_fields={'schema','binding','bundle_id','version','revision','document','assets'}
            evidence={'content_digest','connection_id','runtime','platform_ready','platform_verified'}
            if set(result) not in (manifest_fields|evidence,manifest_fields|evidence|{'connected'}):return False
            if (result['runtime'] not in ('personal_account_delegation','own_account_adapter_preparation')
                    or result['platform_ready'] is not False or result['platform_verified'] is not False
                    or 'connected' in result and result['connected'] is not False):return False
            bare={k:result[k] for k in manifest_fields}
            return (normal_limit(bare)==ENVELOPE_BYTES and result['content_digest']==digest(bare)
                and result['connection_id']==bare['binding']['connection'])
        if (set(value)!={'runtime','sequence','name','arguments'} or value['name']!='own.documents.prepare'
                or type(value['sequence']) is not int or value['sequence']!=1):return False
        runtime=value['runtime'];base={'schema','pid','instance','policy_digest','candidate_scope','identity_digest','root_pin'}
        if (type(runtime) is not dict or set(runtime) not in (base,base|{'domain'})
                or type(runtime['schema']) is not int or runtime['schema'] not in (2,3)
                or type(runtime['pid']) is not int or runtime['pid']<=0
                or type(runtime['root_pin']) is not list or len(runtime['root_pin'])!=2
                or any(type(n) is not int or n<0 for n in runtime['root_pin'])):return False
        import re
        if any(type(runtime[k]) is not str or re.fullmatch('[a-f0-9]{64}',runtime[k]) is None
               for k in ('instance','policy_digest','candidate_scope','identity_digest')):return False
        if runtime['schema']==3:
            from .own_base_domain import DOMAIN
            if runtime.get('domain')!=DOMAIN:return False
        elif 'domain' in runtime:return False
        args=value['arguments']
        from .own_contracts import validate
        validate('own.documents.prepare',args)
        return args['document'].get('policy')==POLICY
    except (WCEError,ValueError,TypeError,KeyError):return False


def send(stream, value):
    data = json.dumps(value, ensure_ascii=False, allow_nan=False, separators=(',', ':')).encode() + b'\n'
    if len(data) > MAX_FRAME:
        from .normal_html_limits import ENVELOPE_BYTES
        if len(data)>ENVELOPE_BYTES or not _normal_envelope(value):
            raise WCEError('BOOTSTRAP_FRAME_LIMIT')
    stream.write(data)
    stream.flush()


def receive(stream):
    from .normal_html_limits import ENVELOPE_BYTES,ENVELOPE_NODES
    data = stream.readline(ENVELOPE_BYTES + 1)
    if not data:raise EOFError()
    if len(data)>ENVELOPE_BYTES or not data.endswith(b'\n'):
        raise WCEError('BOOTSTRAP_FRAME_LIMIT')
    if len(data)<=MAX_FRAME:return decode(data,MAX_FRAME)
    from .prepared_draft_fixture import decode_json
    value=decode_json(data,ENVELOPE_BYTES,max_nodes=ENVELOPE_NODES)
    if not _normal_envelope(value):raise WCEError('BOOTSTRAP_FRAME_LIMIT')
    return value


def runtime_read(config):
    config.check()
    value, pin = private_read(config.root / 'runtime.json')
    value = decode(value)
    expected = {'schema', 'session', 'nonce', 'actor_digest', 'account', 'pid', 'config_digest'}
    if (type(value) is not dict or set(value) != expected or type(value['schema']) is not int
            or value['schema'] != 1 or type(value['pid']) is not int or value['pid'] < 1):
        raise WCEError('BOOTSTRAP_RUNTIME_INVALID')
    import re
    for name in ('session', 'nonce', 'actor_digest', 'config_digest'):
        if type(value[name]) is not str or re.fullmatch('[a-f0-9]{64}', value[name]) is None:
            raise WCEError('BOOTSTRAP_RUNTIME_INVALID')
    from .service import digest
    if (value['actor_digest'] != digest(vars(config.actor)) or value['account'] != config.data['appid']
            or value['config_digest'] != config_digest(config)):
        raise WCEError('BOOTSTRAP_SCOPE_MISMATCH')
    return value, pin


def config_digest(config):
    from .service import digest
    # Includes every identity/deadline field and the one selected profile file.
    # A different connection, generation, epoch or same-content alias cannot
    # borrow an operator's advertised scope through its private directory.
    return digest({'config': config.data, 'profile_path': str(config.path),
                   'profile_identity': list(config.file_pin[:2])})
