"""UNARMED fixed-source acquisition and pinned-F wrapper; no child launcher.

Only an explicit article call may acquire these sources. The original F loader
still issues/validates the real catalog and every business right in the child.
"""
import ast
from dataclasses import dataclass
from hashlib import sha256
from pathlib import Path
import os
import pwd

from wce.contracts import WCEError
from wce.draft_group_contracts import canonical, digest

# No reviewed integration generation is shipped by this pure prototype.
COMPONENT_ADOPTION_SHA256 = '4f4a60375c4f3b7d7d3268217fae8bd8db880ed567da4e97c526eb0636e0e52f'
VERSION = '0.4.62'
MAX_SOURCE = 2 * 1024 * 1024
BASE_TOOLS = frozenset({'own.preflight', 'own.connections.list', 'own.connections.status',
    'own.connections.connect', 'own.connections.disconnect', 'wce.settings.read',
    'wce.settings.update', 'wce.settings.manage', 'wce.settings.open', 'wce.settings.add'})
ARTICLE_TOOL_NAMES = frozenset({
    'own.drafts.inventory', 'own.publications.current.prepare',
    'own.publications.current.dispatch', 'own.publications.current.status',
    'own.publications.current.poll',
    'own.admission.read', 'own.articles.prepare', 'own.articles.read', 'own.articles.status',
    'own.assets.import', 'own.assets.receive', 'own.assets.status', 'own.documents.prepare',
    'own.documents.preview', 'own.draft_groups.plan', 'own.draft_groups.status',
    'own.draft_groups.execute', 'own.draft_groups.readback', 'own.drafts.locate',
    'own.drafts.readback', 'own.drafts.restore', 'own.drafts.restore_readback',
    'own.drafts.restore_reconcile', 'own.drafts.restore_status', 'own.drafts.restores',
    'own.drafts.revisions.execute', 'own.drafts.revisions.prepare',
    'own.drafts.revisions.readback', 'own.drafts.revisions.status', 'own.drafts.save',
    'own.drafts.status', 'own.editor.preferences.read', 'own.editor.preferences.update',
    'own.publications.dispatch', 'own.publications.poll', 'own.publications.status',
    'own.uploads.execute', 'own.uploads.reconcile', 'own.uploads.status'})

BUSINESS_TOOLS = frozenset({'own.draft_groups.' + suffix for suffix in ('plan','status','execute','readback')})

def need(value, code='ARTICLE_DOMAIN_NOT_READY'):
    if value is not True:
        raise WCEError(code)


def business_name(name):
    """No source access, authority, discovery side effect, or basic delegation."""
    need(type(name) is str and name in BUSINESS_TOOLS)
    return name


@dataclass(frozen=True)
class _RuntimeFacts:
    root: Path
    home: Path
    version: str
    scope: str
    plugin_sha: str

    @property
    def front(self):
        return self.home / '.wce/group-host-runtime' / self.version / 'front.py'


def _installed_runtime():
    # This function runs only after explicit business-name and adoption checks.
    from wce.bounded_file import FileSource
    from wce.own_connection_policy import code_scope
    from wce import group_host_external_loader as loader
    import json
    root = Path(__file__).absolute().parents[1]
    need(Path(loader.__file__).absolute() == root / 'wce/group_host_external_loader.py')
    raw = FileSource(root).read('plugin.json')
    metadata = json.loads(raw)
    need(type(metadata) is dict and metadata.get('name') == 'wechat-ecosystem'
         and metadata.get('version') == VERSION)
    home = Path(pwd.getpwuid(os.getuid()).pw_dir)
    need(home.is_absolute() and '..' not in home.parts)
    return _RuntimeFacts(root, home, VERSION, code_scope(), sha256(raw).hexdigest())


def _validate_materials(runtime, front, entry, adoption, catalog):
    """Pure codec/graph validation, NOT catalog issuance or business authority."""
    from wce import group_host_external_loader as loader
    need(type(runtime) is _RuntimeFacts and runtime.version == VERSION
         and front.path == runtime.front)
    f = loader._literal_script(front, loader._F_KEYS, loader._F_BODY)
    e = loader._literal_script(entry, loader._E_KEYS, loader._E_BODY)
    need(f['ENTRY_PATH'] == str(entry.path) and f['ENTRY_SHA'] == entry.sha
         and f['ADOPTION_PATH'] == str(adoption.path) and f['ADOPTION_SHA'] == adoption.sha
         and e['CORE_ROOT'] == str(runtime.root) and e['CORE_SCOPE'] == runtime.scope
         and e['PROCESS_ROLE'] == 'MCP'
         and e['CATALOG_PATH'] == str(catalog.path) and e['CATALOG_SHA'] == catalog.sha)
    accepted = loader._json(adoption,
        ('schema','profile','authority','loader','catalog','core_scope','rows_sha'),
        'GROUP_FIXED_LOADER_ADOPTION_V1')
    table = loader._json(catalog, ('schema','profile','authority','core_scope','rows'),
                         'GROUP_FIXED_JOB_CATALOG_V1')
    need(accepted['loader'] == [str(entry.path), entry.sha]
         and accepted['catalog'] == [str(catalog.path), catalog.sha]
         and accepted['core_scope'] == table['core_scope'] == runtime.scope
         and accepted['rows_sha'] == digest(table['rows'])
         and type(table['rows']) is list and 0 < len(table['rows']) <= 64)
    seen = set()
    for value in table['rows']:
        row, policy, extension = loader._row(value, runtime.scope)
        need(row[2] == runtime.scope and (row[0], row[1]) not in seen)
        seen.add((row[0], row[1]))
    # Seven row sources/helpers/policies/retention/current qualification remain
    # mandatory in the actual child loader/Gate. No Native/policy read here.
    return {'front_sha256': front.sha, 'entry_sha256': entry.sha,
            'adoption_sha256': adoption.sha, 'catalog_sha256': catalog.sha,
            'core_scope': runtime.scope, 'rows': len(table['rows'])}


class _HeldBusinessSources:
    """Private resource owner only; this object never grants any business right."""
    def __init__(self, runtime):
        from wce.draft_group_pin_resources import PinPool
        self.runtime = runtime
        self.pool = PinPool(self)
        self.views = []
        self.front = None
        self.closed = False

    def acquire(self, path, checksum):
        view = self.pool.acquire(path, checksum, MAX_SOURCE, owner=self)
        self.views.append(view)
        return view

    def guard(self):
        need(not self.closed)
        from wce.bounded_file import FileSource
        from wce.own_connection_policy import code_scope
        need(sha256(FileSource(self.runtime.root).read('plugin.json')).hexdigest() == self.runtime.plugin_sha
             and code_scope() == self.runtime.scope)
        self.pool.check_all(owner=self)

    def close(self, *, original=None):
        if not self.closed:
            self.closed = True
            from wce.draft_group_pin_resources import close_all
            close_all([view.close for view in reversed(self.views)] +
                      [lambda: self.pool.close(owner=self, original=original)], original)


def acquire_for_business(name):
    """No paths/hashes/versions from MCP, env or callers; default fails unarmed."""
    business_name(name)  # Basic calls fail before adoption/runtime/F inspection.
    need(type(COMPONENT_ADOPTION_SHA256) is str and len(COMPONENT_ADOPTION_SHA256) == 64
         and set(COMPONENT_ADOPTION_SHA256) <= set('0123456789abcdef'))
    from wce.bounded_file import FileSource
    from wce import group_host_external_loader as loader
    import sys
    resources = None
    try:
        runtime = _installed_runtime()
        resources = _HeldBusinessSources(runtime)
        # Original M03 root is the fixed reviewed locator. Read then acquire
        # the same SHA into real NOFOLLOW pin resources; drift cannot rebase.
        raw = FileSource(runtime.front.parent).read(runtime.front.name)
        front = resources.acquire(runtime.front, sha256(raw).hexdigest())
        f = loader._literal_script(front, loader._F_KEYS, loader._F_BODY)
        entry = resources.acquire(Path(f['ENTRY_PATH']), f['ENTRY_SHA'])
        e = loader._literal_script(entry, loader._E_KEYS, loader._E_BODY)
        need(e['CORE_ROOT'] == str(runtime.root) and e['CORE_SCOPE'] == runtime.scope
             and e['PROCESS_ROLE'] == 'MCP')
        adoption = resources.acquire(Path(f['ADOPTION_PATH']), f['ADOPTION_SHA'])
        catalog = resources.acquire(Path(e['CATALOG_PATH']), e['CATALOG_SHA'])
        resources.summary = _validate_materials(runtime, front, entry, adoption, catalog)
        resources.front = front
        resources.guard()
        return resources
    except BaseException as error:
        if resources is not None:
            resources.close(original=sys.exc_info()[1])
        if isinstance(error, (WCEError, OSError, ValueError, UnicodeError, RecursionError)):
            raise WCEError('ARTICLE_DOMAIN_NOT_READY') from None
        raise


# Rendered wrapper has no request-controlled inputs. Parent must pass only the
# held front FD using pass_fds. The child closes that FD before original F code.
_WRAPPER_BODY = '''import hashlib,os,stat,sys,threading
from pathlib import Path

def _watch_lifetime():
    try:os.read(LIFETIME_READER,1)
    except BaseException:pass
    os._exit(74)
if not stat.S_ISFIFO(os.fstat(LIFETIME_READER).st_mode):raise RuntimeError('ARTICLE_LIFETIME_TYPE')
threading.Thread(target=_watch_lifetime,daemon=True).start()

def _full(i):
    return (i.st_dev,i.st_ino,i.st_mode,i.st_uid,i.st_gid,i.st_nlink,i.st_size,i.st_mtime_ns,i.st_ctime_ns)
try:
    _info=os.fstat(FRONT_FD)
    if not stat.S_ISREG(_info.st_mode) or _info.st_uid!=os.getuid() or stat.S_IMODE(_info.st_mode)!=0o600 or _info.st_nlink!=1 or not 0<_info.st_size<=2097152 or _full(_info)!=FRONT_PIN or _full(os.stat(FRONT_PATH,follow_symlinks=False))!=FRONT_PIN:raise RuntimeError('ARTICLE_FRONT_CHANGED')
    os.lseek(FRONT_FD,0,os.SEEK_SET)
    _chunks=[];_size=0
    while _size<FRONT_SIZE:
        _part=os.read(FRONT_FD,min(65536,FRONT_SIZE-_size))
        if not _part:raise RuntimeError('ARTICLE_FRONT_CHANGED')
        _chunks.append(_part);_size+=len(_part)
    _raw=b''.join(_chunks)
    if hashlib.sha256(_raw).hexdigest()!=FRONT_SHA or _full(os.fstat(FRONT_FD))!=FRONT_PIN or _full(os.stat(FRONT_PATH,follow_symlinks=False))!=FRONT_PIN:raise RuntimeError('ARTICLE_FRONT_CHANGED')
finally:os.close(FRONT_FD)
sys.argv=[FRONT_PATH]
sys.path.insert(0,CORE_ROOT)
import wce.own_business_temporal as _temporal
if str(Path(_temporal.__file__).absolute())!=str(Path(CORE_ROOT)/'wce/own_business_temporal.py'):raise RuntimeError('ARTICLE_TEMPORAL_ORIGIN')
with _temporal.deadline_scope(ABSOLUTE_DEADLINE):
    exec(compile(_raw,FRONT_PATH,'exec',dont_inherit=True),{'__name__':'__main__','__file__':FRONT_PATH,'__package__':None})
'''


def execution_wrapper(resources, absolute_deadline, lifetime_read_fd):
    """Render fixed wrapper only; never spawn/exec a child in the parent."""
    import math
    import time
    import stat
    need(type(absolute_deadline) in (int, float) and math.isfinite(absolute_deadline)
         and time.monotonic() < absolute_deadline <= time.monotonic() + 300)
    need(type(lifetime_read_fd) is int and lifetime_read_fd >= 3
         and stat.S_ISFIFO(os.fstat(lifetime_read_fd).st_mode))
    need(type(resources) is _HeldBusinessSources and not resources.closed)
    resources.guard()
    front = resources.front
    need(front is not None)
    values = {'FRONT_PATH': str(front.path), 'FRONT_FD': front.fd,
              'FRONT_PIN': front.pin, 'FRONT_SIZE': len(front.raw), 'FRONT_SHA': front.sha,
              'CORE_ROOT': str(resources.runtime.root), 'ABSOLUTE_DEADLINE': absolute_deadline,
              'LIFETIME_READER': lifetime_read_fd}
    need(values['FRONT_PATH'] == str(resources.runtime.front)
         and type(values['FRONT_FD']) is int and values['FRONT_FD'] >= 3
         and type(values['FRONT_PIN']) is tuple and len(values['FRONT_PIN']) == 9
         and 0 < values['FRONT_SIZE'] <= MAX_SOURCE)
    raw = ''.join(name + '=' + repr(value) + '\n' for name, value in values.items()) + _WRAPPER_BODY
    ast.parse(raw)
    return raw.encode('utf-8'), (front.fd, lifetime_read_fd)
