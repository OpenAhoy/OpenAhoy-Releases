"""Pinned fixed-program inputs for the separate, short Operator image domain.

These resources establish program/input identity only. They grant neither an
upload nor a Group operation. No request, environment or command-line argument
can choose the bootstrap. The final integration adoption is initially unarmed.
"""
import ast
from dataclasses import dataclass
from hashlib import sha256
import json
import math
import os
from pathlib import Path
import pwd
import re
import stat
import threading
import time

from .bounded_file import FileSource
from .contracts import WCEError
from .draft_group_pin_resources import PinPool, capacity, close_all, full, path_value, MAX_RAW_BYTES
from .own_connection_policy import code_scope

PREUPLOAD_ENTRY_ADOPTION = '7c8ba660856b785accd008d48579cf33ded916da7a1f82f3c99f1474dc1fdded'
MAX_SOURCE = 2 * 1024 * 1024
BOOTSTRAP_KEYS = ('CORE_ROOT', 'CORE_SCOPE', 'PROCESS_ROLE', 'BINDING_SHA256')
BOOTSTRAP_BODY = '''import sys
sys.path.insert(0,CORE_ROOT)
from wce.own_preupload_entry import run_fixed_entry
run_fixed_entry()
'''
_HASH = re.compile('[0-9a-f]{64}\\Z')


def need(value):
    if value is not True:
        raise WCEError('PREUPLOAD_FIXED_SOURCE_HOLD')


def _hash(value):
    need(type(value) is str and _HASH.fullmatch(value) is not None)


def canonical(value):
    try:
        return json.dumps(value, ensure_ascii=False, sort_keys=True,
                          separators=(',', ':'), allow_nan=False).encode('utf-8')
    except (ValueError, TypeError, UnicodeError, RecursionError):
        raise WCEError('PREUPLOAD_FIXED_SOURCE_HOLD') from None


def _json(raw):
    from .own_bootstrap_security import decode
    value = decode(raw, MAX_SOURCE)
    need(type(value) is dict and canonical(value) == raw)
    return value


def bootstrap_bytes(root, scope, binding_sha):
    path_value(root)
    _hash(scope)
    _hash(binding_sha)
    values = (str(root), scope, 'PREUPLOAD', binding_sha)
    return (''.join(key+'='+repr(value)+'\n' for key, value in zip(BOOTSTRAP_KEYS, values))
            + BOOTSTRAP_BODY).encode('utf-8')


def parse_bootstrap(raw):
    try:
        tree = ast.parse(raw)
        need(len(tree.body) >= len(BOOTSTRAP_KEYS))
        values = {}
        for node, key in zip(tree.body, BOOTSTRAP_KEYS):
            need(type(node) is ast.Assign and len(node.targets) == 1
                 and type(node.targets[0]) is ast.Name and node.targets[0].id == key)
            value = ast.literal_eval(node.value)
            need(type(value) is str)
            values[key] = value
        need(values['PROCESS_ROLE'] == 'PREUPLOAD')
        need(raw == bootstrap_bytes(values['CORE_ROOT'], values['CORE_SCOPE'], values['BINDING_SHA256']))
        return values
    except (SyntaxError, TypeError, ValueError, UnicodeError):
        raise WCEError('PREUPLOAD_FIXED_SOURCE_HOLD') from None


@dataclass(frozen=True)
class _Runtime:
    root: Path
    version: str
    scope: str
    plugin_sha: str
    bootstrap: Path


def installed_runtime():
    _hash(PREUPLOAD_ENTRY_ADOPTION)  # Before reading any account or runtime input.
    root = Path(__file__).absolute().parents[1]
    from . import own_preupload_entry, own_preupload_protocol
    need(Path(own_preupload_entry.__file__).absolute() == root/'wce/own_preupload_entry.py'
         and Path(own_preupload_protocol.__file__).absolute() == root/'wce/own_preupload_protocol.py')
    raw = FileSource(root).read('plugin.json')
    metadata = json.loads(raw)
    need(type(metadata) is dict and metadata.get('name') == 'wechat-ecosystem')
    version = metadata.get('version')
    need(type(version) is str and re.fullmatch(r'[0-9]+\.[0-9]+\.[0-9]+', version) is not None)
    home = path_value(pwd.getpwuid(os.getuid()).pw_dir)
    return _Runtime(root, version, code_scope(), sha256(raw).hexdigest(),
                    home/'.wce/operator-preupload-runtime'/version/'bootstrap.py')


class _EvidenceView:
    """Non-authoritative original QA/rule evidence, retaining its real mode.

    Private bootstrap/bindings/policy stay on the original 0600-only PinPool
    leaf path. Existing selected reports/rules may legitimately be 0644; this
    explicit evidence reader neither changes them nor issues a permission.
    """
    def __init__(self, owner, path, checksum, maximum):
        self.owner, self.path = owner, path_value(path)
        self.closed, self._fd = False, None
        owner.pool._guard(owner)
        parent = owner.pool.directory(self.path.parent, owner=owner)
        capacity(1, persistent=True)
        fd = os.open(self.path.name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=parent)
        self._fd, self.parent = fd, parent
        try:
            info = os.fstat(fd)
            need(stat.S_ISREG(info.st_mode) and info.st_uid == os.getuid()
                 and info.st_nlink == 1 and stat.S_IMODE(info.st_mode) in (0o600, 0o644)
                 and 0 < info.st_size <= maximum
                 and owner.pool.raw_bytes + owner.evidence_bytes + info.st_size <= MAX_RAW_BYTES)
            self._pin, self._sha = full(info), checksum
            chunks, size = [], 0
            stop = time.monotonic()+2
            while size <= maximum:
                need(time.monotonic() < stop)
                block = os.read(fd, min(65536, maximum+1-size))
                if not block:break
                chunks.append(block);size += len(block)
            self._raw = b''.join(chunks)
            need(size == info.st_size and sha256(self._raw).hexdigest() == checksum)
            self.check()
            owner.evidence_bytes += size
        except BaseException as original:
            close_all([self.close], original)
            raise

    def check(self):
        need(not self.closed and not self.owner.closed)
        self.owner.pool._guard(self.owner)
        self.owner.pool._check_chain(self.path.parent)
        need(self._pin == full(os.fstat(self._fd)) == full(os.stat(self.path.name,
             dir_fd=self.parent, follow_symlinks=False)))
        return True

    @property
    def raw(self):self.check();return self._raw
    @property
    def sha(self):self.check();return self._sha
    @property
    def fd(self):self.check();return self._fd
    @property
    def pin(self):self.check();return self._pin

    def close(self):
        if not self.closed:
            self.closed = True
            if self._fd is not None:
                fd, self._fd = self._fd, None
                os.close(fd)


class _HeldPreuploadSources:
    def __init__(self, runtime):
        need(type(runtime) is _Runtime)
        self.runtime, self.closed = runtime, False
        self.pid, self.thread = os.getpid(), threading.get_ident()
        self.pool, self.views = PinPool(self), []
        self.evidence_bytes, self.evidence_views = 0, {}
        self.bootstrap = self.binding = self.selection = self.resume = self.policy_file = None
        self._binding_raw = None

    def acquire(self, path, checksum):
        view = self.pool.acquire(path, checksum, MAX_SOURCE, owner=self)
        self.views.append(view)
        return view

    def acquire_evidence(self, ref):
        # Only the fixed QA/resume reader supplies a closed ref from held
        # bindings. This mechanical method itself grants no source/QA right.
        need(type(ref) is dict and set(ref) == {'path', 'sha256', 'bytes'})
        _hash(ref['sha256'])
        need(type(ref['bytes']) is int and 0 < ref['bytes'] <= MAX_SOURCE)
        path = path_value(ref['path'])
        prior = self.evidence_views.get(path)
        if prior is not None:
            need(prior.sha == ref['sha256'] and len(prior.raw) == ref['bytes'])
            return prior
        view = _EvidenceView(self, path, ref['sha256'], ref['bytes'])
        self.views.append(view)
        self.evidence_views[path] = view
        need(len(view.raw) == ref['bytes'])
        return view

    def guard(self):
        need(not self.closed and self.pid == os.getpid() and self.thread == threading.get_ident())
        need(code_scope() == self.runtime.scope and
             sha256(FileSource(self.runtime.root).read('plugin.json')).hexdigest() == self.runtime.plugin_sha)
        self.pool.check_all(owner=self)
        for view in self.evidence_views.values():view.check()
        if self._binding_raw is not None:
            value = _json(self._binding_raw)
            need(time.time() < value['not_after'])
        return True

    def values(self):
        self.guard()
        return _json(self._binding_raw)

    def close(self, *, original=None):
        if not self.closed:
            self.closed = True
            close_all([view.close for view in reversed(self.views)] +
                      [lambda: self.pool.close(owner=self, original=original)], original)


def _load_inputs(resources, program):
    runtime = resources.runtime
    need(program['CORE_ROOT'] == str(runtime.root) and program['CORE_SCOPE'] == runtime.scope)
    resources.binding = resources.acquire(runtime.bootstrap.parent/'bindings.json', program['BINDING_SHA256'])
    value = _json(resources.binding.raw)
    need(set(value) == {'schema', 'profile', 'authority', 'purpose', 'candidate_scope',
        'selection', 'resume', 'policy', 'not_after', 'member_projection', 'qa'})
    need(type(value['schema']) is int and value['schema'] == 2
         and value['profile'] == 'PREUPLOAD_FIXED_BINDINGS_WITH_QA_V2'
         and value['authority'] is False and value['purpose'] == 'OPERATOR_PREUPLOAD_V1'
         and value['candidate_scope'] == runtime.scope
         and type(value['not_after']) in (int, float) and math.isfinite(value['not_after'])
         and time.time() < value['not_after'])
    for name in ('selection', 'resume', 'policy'):
        ref = value[name]
        need(type(ref) is dict and set(ref) == {'path', 'sha256'})
        _hash(ref['sha256'])
        path = path_value(ref['path'])
        setattr(resources, 'policy_file' if name == 'policy' else name,
                resources.acquire(path, ref['sha256']))
    projection = value['member_projection']
    need(type(projection) is list and len(projection) == 28)
    need(all(type(row) is list and len(row) == 3 for row in projection))
    expected_projection = tuple(tuple(row) for row in projection)
    # This remains a non-authoritative declaration, despite its pinned origin.
    from .draft_group_selected_source_codec import decode_manifest
    decode_manifest(resources.selection.raw, expected_member_projection=expected_projection)
    from .own_preupload_qa import reference
    need(type(value['qa']) is dict and set(value['qa']) == {'dossier_ref','acceptance_ref'})
    for ref in value['qa'].values():
        reference(ref)
        resources.acquire_evidence(ref)
    resources._binding_raw = resources.binding.raw
    resources.guard()


def acquire_fixed_sources():
    """No paths/roles/observations supplied by the caller."""
    resources = None
    try:
        runtime = installed_runtime()
        resources = _HeldPreuploadSources(runtime)
        raw = FileSource(runtime.bootstrap.parent).read(runtime.bootstrap.name)
        resources.bootstrap = resources.acquire(runtime.bootstrap, sha256(raw).hexdigest())
        _load_inputs(resources, parse_bootstrap(resources.bootstrap.raw))
        return resources
    except BaseException as original:
        if resources is not None:
            resources.close(original=original)
        raise


WRAPPER_KEYS = ('BOOTSTRAP_PATH', 'BOOTSTRAP_FD', 'BOOTSTRAP_PIN', 'BOOTSTRAP_SIZE',
    'BOOTSTRAP_SHA', 'CORE_ROOT', 'CORE_SCOPE', 'BINDING_SHA256', 'SESSION_FD',
    'LIFETIME_READER', 'ABSOLUTE_DEADLINE')
WRAPPER_BODY = '''import hashlib,os,select,stat,sys,threading,time
from pathlib import Path

def _watch_lifetime():
    try:select.select([LIFETIME_READER],[],[],max(0,ABSOLUTE_DEADLINE-time.monotonic()))
    except BaseException:pass
    os._exit(74)
if not stat.S_ISFIFO(os.fstat(LIFETIME_READER).st_mode):raise RuntimeError('PREUPLOAD_LIFETIME_TYPE')
threading.Thread(target=_watch_lifetime,daemon=True).start()
def _full(i):
    return (i.st_dev,i.st_ino,i.st_mode,i.st_uid,i.st_gid,i.st_nlink,i.st_size,i.st_mtime_ns,i.st_ctime_ns)
_info=os.fstat(BOOTSTRAP_FD)
if not stat.S_ISREG(_info.st_mode) or _info.st_uid!=os.getuid() or stat.S_IMODE(_info.st_mode)!=0o600 or _info.st_nlink!=1 or _full(_info)!=BOOTSTRAP_PIN or _full(os.stat(BOOTSTRAP_PATH,follow_symlinks=False))!=BOOTSTRAP_PIN:raise RuntimeError('PREUPLOAD_PROGRAM_CHANGED')
os.lseek(BOOTSTRAP_FD,0,os.SEEK_SET)
_chunks=[];_size=0
while _size<BOOTSTRAP_SIZE:
    _part=os.read(BOOTSTRAP_FD,min(65536,BOOTSTRAP_SIZE-_size))
    if not _part:raise RuntimeError('PREUPLOAD_PROGRAM_CHANGED')
    _chunks.append(_part);_size+=len(_part)
_raw=b''.join(_chunks)
if hashlib.sha256(_raw).hexdigest()!=BOOTSTRAP_SHA or _full(os.fstat(BOOTSTRAP_FD))!=BOOTSTRAP_PIN or _full(os.stat(BOOTSTRAP_PATH,follow_symlinks=False))!=BOOTSTRAP_PIN:raise RuntimeError('PREUPLOAD_PROGRAM_CHANGED')
sys.argv=[BOOTSTRAP_PATH]
sys.path.insert(0,CORE_ROOT)
from wce.own_business_temporal import deadline_scope
with deadline_scope(ABSOLUTE_DEADLINE):
    _program=compile(_raw,BOOTSTRAP_PATH,'exec',dont_inherit=True)
    exec(_program,{'__name__':'__main__','__file__':BOOTSTRAP_PATH,'__package__':None})
'''


def render_wrapper_values(values):
    need(type(values) is dict and tuple(values) == WRAPPER_KEYS)
    return (''.join(key+'='+repr(values[key])+'\n' for key in WRAPPER_KEYS)
            + WRAPPER_BODY).encode('utf-8')


def render_wrapper(resources, session_fd, lifetime_fd, deadline):
    import socket
    need(type(resources) is _HeldPreuploadSources)
    resources.guard()
    need(type(deadline) in (int, float) and math.isfinite(deadline)
         and time.monotonic() < deadline <= time.monotonic()+300)
    need(type(session_fd) is int and type(lifetime_fd) is int
         and session_fd >= 3 and lifetime_fd >= 3
         and stat.S_ISSOCK(os.fstat(session_fd).st_mode)
         and stat.S_ISFIFO(os.fstat(lifetime_fd).st_mode))
    program = resources.bootstrap
    need(len({program.fd, session_fd, lifetime_fd}) == 3)
    values = dict(zip(WRAPPER_KEYS, (str(program.path), program.fd, program.pin,
        len(program.raw), program.sha, str(resources.runtime.root), resources.runtime.scope,
        resources.binding.sha, session_fd, lifetime_fd, deadline)))
    return render_wrapper_values(values), (program.fd, session_fd, lifetime_fd)
