"""Trusted host updater mechanics only. No MCP, credentials, IPC or business API.

Normal installer calls this module while its actual maintenance locks remain
held. CLI offers no mutation shortcut. Process arguments are inspected only in
memory and never returned. Same-version multi-process operation is supported.
"""
from contextlib import ExitStack
import ctypes
import errno
import fcntl
from hashlib import sha256
import json
import os
from pathlib import Path
import re
import signal
import stat
import struct
import subprocess
import sys
import time


class Hold(RuntimeError):
    pass


def need(value, code):
    if value is not True:
        raise Hold(code)


def digest(value):
    return sha256(json.dumps(value, sort_keys=True, separators=(',', ':'),
                             allow_nan=False).encode()).hexdigest()


def pin(info):
    return [info.st_dev, info.st_ino, info.st_mode, info.st_uid, info.st_gid,
            info.st_nlink, info.st_size, info.st_mtime_ns, info.st_ctime_ns]


def directory(path):
    path = Path(path)
    need(path.is_absolute() and '..' not in path.parts, 'PATH_INVALID')
    fd = os.open('/', os.O_RDONLY | os.O_DIRECTORY)
    try:
        for name in path.parts[1:]:
            child = os.open(name, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW,
                            dir_fd=fd)
            os.close(fd)
            fd = child
        return fd
    except BaseException:
        os.close(fd)
        raise


def file_pin(path, maximum=512 * 1024 * 1024):
    path = Path(path)
    parent = directory(path.parent)
    try:
        fd = os.open(path.name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK,
                     dir_fd=parent)
        try:
            before = os.fstat(fd)
            need(stat.S_ISREG(before.st_mode) and before.st_nlink == 1
                 and 0 <= before.st_size <= maximum, 'FILE_TYPE_OR_BOUND')
            value = sha256()
            offset = 0
            while offset < before.st_size:
                raw = os.pread(fd, min(1024 * 1024, before.st_size - offset), offset)
                need(bool(raw), 'FILE_SHORT_READ')
                value.update(raw)
                offset += len(raw)
            need(pin(os.fstat(fd)) == pin(before)
                 == pin(os.stat(path.name, dir_fd=parent, follow_symlinks=False)),
                 'FILE_CHANGED')
            return {'pin': pin(before), 'sha256': value.hexdigest()}
        finally:
            os.close(fd)
    finally:
        os.close(parent)


class HeldMaintenance:
    """Adopt actual installer FDs, never a caller's 'locks held' receipt.

    Pass descriptors in the already reviewed normal lock order. EX|NB on each
    live descriptor proves actual exclusion now; shared inherited descriptors
    work without opening a competing file description. This object neither
    closes nor unlocks installer-owned descriptors.
    """
    def __init__(self, descriptors, live_guard, *, expected_lock_paths):
        need(callable(live_guard) and bool(descriptors), 'LIVE_MAINTENANCE_REQUIRED')
        self.descriptors = tuple(descriptors)
        paths = [Path(p) for p, _ in self.descriptors]
        # The normal installer supplies its reviewed full ordered lock set.
        # Different generations have different account/dispatch lock sets.
        need(paths[0].name == 'connection-setup.lock' and len(paths) == len(set(paths))
             and len(paths) >= 2 and paths == list(map(Path, expected_lock_paths)),
             'LOCK_SET_OR_ORDER_INCOMPLETE')
        self.live_guard = live_guard
        self.pins = []
        for path, fd in self.descriptors:
            need(type(fd) is int and fd >= 0, 'LOCK_FD_REQUIRED')
            info = os.fstat(fd)
            need(stat.S_ISREG(info.st_mode) and info.st_uid == os.getuid()
                 and info.st_nlink == 1 and info.st_size == 0
                 and stat.S_IMODE(info.st_mode) == 0o600, 'LOCK_IDENTITY_INVALID')
            self.pins.append(pin(info))
        self.check()

    def check(self):
        need(self.live_guard() is True, 'LIVE_SAFE_POINT_NOT_CONFIRMED')
        for (path, fd), expected in zip(self.descriptors, self.pins):
            parent = directory(Path(path).parent)
            try:
                need(pin(os.fstat(fd)) == expected
                     == pin(os.stat(Path(path).name, dir_fd=parent,
                                    follow_symlinks=False)), 'LOCK_CHANGED')
                # A new file description must be blocked by the existing EX
                # owner. Never silently re-acquire a lock dropped by caller.
                probe = os.open(Path(path).name, os.O_RDONLY | os.O_NOFOLLOW,
                                dir_fd=parent)
                try:
                    need(pin(os.fstat(probe)) == expected, 'LOCK_PROBE_CHANGED')
                    try:
                        fcntl.flock(probe, fcntl.LOCK_SH | fcntl.LOCK_NB)
                    except OSError as error:
                        if error.errno not in (errno.EAGAIN, errno.EWOULDBLOCK):
                            raise
                    else:
                        fcntl.flock(probe, fcntl.LOCK_UN)
                        raise Hold('ORIGINAL_EXCLUSIVE_LOCK_NOT_HELD')
                    fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
                finally:
                    os.close(probe)
            finally:
                os.close(parent)


def startup_display_matches(display, executable_argument, entry):
    """Fixed no-space launcher display only, NOT kernel argv segmentation.

    This is one element of the independently pinned host/parent/start/executable
    evidence. A generic process with the same flat display is not authorized.
    """
    need(all(not any(c.isspace() for c in str(p))
             for p in (entry, executable_argument)), 'LAUNCH_PATH_AMBIGUOUS')
    return display == f'{executable_argument} -I -B {entry}'


class MacHost:
    """macOS no-env launch metadata; no sysctl KERN_PROCARGS2 request.

    libproc birth/executable/UID + fixed ps display + externally pinned parent.
    This does not attest kernel argv segmentation or running Python code bytes.
    """
    def __init__(self, reference_scan):
        need(sys.platform == 'darwin', 'MACOS_REQUIRED')
        need(callable(reference_scan), 'COMPLETE_REFERENCE_SCANNER_REQUIRED')
        self.reference_scan = reference_scan
        self.lib = ctypes.CDLL('/usr/lib/libproc.dylib', use_errno=True)
        self.lib.proc_pidinfo.argtypes = [ctypes.c_int, ctypes.c_int, ctypes.c_uint64,
                                         ctypes.c_void_p, ctypes.c_int]
        self.lib.proc_pidpath.argtypes = [ctypes.c_int, ctypes.c_void_p, ctypes.c_uint32]

    def process(self, pid):
        class BSD(ctypes.Structure):
            _fields_ = [(n, ctypes.c_uint32) for n in ('flags', 'status', 'xstatus',
                        'pid', 'ppid', 'uid', 'gid', 'ruid', 'rgid', 'svuid', 'svgid', 'reserved')]
            _fields_ += [('comm', ctypes.c_char * 16), ('name', ctypes.c_char * 32)]
            _fields_ += [(n, ctypes.c_uint32) for n in ('nfiles', 'pgid', 'pjobc', 'dev', 'tpgid', 'nice')]
            _fields_ += [('start_sec', ctypes.c_uint64), ('start_usec', ctypes.c_uint64)]
        need(type(pid) is int and pid > 1 and ctypes.sizeof(BSD) == 136, 'PID_INVALID')
        info = BSD()
        ctypes.set_errno(0)
        count = self.lib.proc_pidinfo(pid, 3, 0, ctypes.byref(info), ctypes.sizeof(info))
        if count == 0 and ctypes.get_errno() == 3:
            raise ProcessLookupError(pid)
        need(count == ctypes.sizeof(info), 'PROCESS_METADATA_INCOMPLETE')
        raw = ctypes.create_string_buffer(4096)
        need(self.lib.proc_pidpath(pid, raw, len(raw)) > 0, 'PROCESS_EXE_UNREADABLE')
        exe = os.fsdecode(raw.value)
        return {'pid': pid, 'ppid': info.ppid, 'uid': info.uid, 'ruid': info.ruid,
                'start': [info.start_sec, info.start_usec], 'exe': exe,
                'exe_file': file_pin(exe)}

    def native(self, pid, entry, executable_argument):
        info = self.process(pid)
        need(info['uid'] == info['ruid'] == os.getuid(), 'PROCESS_UID_MISMATCH')
        need(str(Path(executable_argument).resolve(strict=True)) == info['exe'],
             'PROCESS_EXECUTABLE_MISMATCH')
        run = subprocess.run(['/bin/ps', '-ww', '-p', str(pid), '-o', 'command='],
                             capture_output=True, timeout=3, check=False)
        need(run.returncode == 0 and not run.stderr
             and startup_display_matches(run.stdout.decode().rstrip('\n'),
                                         executable_argument, entry),
             'PROCESS_STARTUP_DISPLAY_MISMATCH')
        need(self.process(pid) == info, 'PROCESS_CHANGED_DURING_ARGV')
        info['startup_display_sha256'] = sha256(run.stdout.rstrip(b'\n')).hexdigest()
        info['entry'] = str(entry)
        info['parent'] = self.process(info['ppid'])
        return info

    def terminate(self, expected, entry, executable_argument, *, fence):
        # macOS has no portable pidfd signal operation. Recheck immediately;
        # do not claim malicious same-UID PID reuse is OS-atomically prevented.
        need(self.native(expected['pid'], entry, executable_argument) == expected,
             'PROCESS_CHANGED_BEFORE_SIGNAL')
        need(type(fence) is HeldMaintenance, 'LIVE_MAINTENANCE_REQUIRED')
        fence.check()  # Identity observation itself may have lost the safe point.
        os.kill(expected['pid'], signal.SIGTERM)

    def references(self, root):
        result = self.reference_scan(str(root))
        need(type(result) is dict and set(result) == {'coverage', 'references'}
             and result['coverage'] == 'COMPLETE'
             and type(result['references']) is list, 'REFERENCE_COVERAGE_UNKNOWN')
        return result['references']


def stop_native(expected, *, entry, executable_argument, historical_entry,
                cache_parent, current_version, expected_parent, restart_current=False,
                fence, host, timeout=15, clock=time.monotonic, sleep=time.sleep):
    """One SIGTERM only; no SIGKILL, broad name match, business retry or relaunch.

    historical_entry is a real independently reviewed frozen package file ref,
    NOT a claim about bytes loaded by an already running deleted-file process.
    """
    need(type(fence) is HeldMaintenance, 'LIVE_MAINTENANCE_REQUIRED')
    need(type(timeout) in (int, float) and 0 < timeout <= 60, 'TIMEOUT_INVALID')
    fence.check()
    need(expected.get('parent') == expected_parent, 'EXPECTED_PARENT_MISMATCH')
    entry = Path(entry)
    need(entry.is_absolute() and entry.name == 'wce_mcp.py'
         and entry.parent.name == 'scripts' and entry.parent.parent.parent == Path(cache_parent)
         and re.fullmatch(r'0\.4\.[0-9]+', entry.parent.parent.name) is not None,
         'NON_WCE_ENTRY_REJECTED')
    need(type(restart_current) is bool and
         (entry.parent.parent.name != current_version or restart_current),
         'CURRENT_PROCESS_PROTECTED')
    ref = Path(historical_entry['path'])
    need(file_pin(ref)['sha256'] == historical_entry['sha256'], 'HISTORICAL_ENTRY_MISMATCH')
    entry_state = 'ENTRY_PRESENT_MATCHED'
    try:
        need(file_pin(entry)['sha256'] == historical_entry['sha256'], 'LIVE_ENTRY_MISMATCH')
    except FileNotFoundError:
        entry_state = 'ENTRY_ABSENT_HISTORICAL_PACKAGE_MATCH'
    first = host.native(expected['pid'], entry, executable_argument)
    need(first == expected, 'PROCESS_IDENTITY_CHANGED')
    fence.check()
    need(host.native(expected['pid'], entry, executable_argument) == first,
         'PROCESS_SECOND_OBSERVATION_CHANGED')
    fence.check()
    host.terminate(first, entry, executable_argument, fence=fence)
    end = clock() + timeout
    while clock() < end:
        fence.check()
        try:
            current = host.process(expected['pid'])
        except ProcessLookupError:
            return {'state': 'ORIGINAL_PROCESS_EXITED', 'entry_state': entry_state,
                    'identity_sha256': digest(expected), 'signals': 1,
                    'evidence_kind': 'TRUSTED_HOST_LAUNCH_METADATA_MATCH'}
        if current['start'] != expected['start']:
            return {'state': 'ORIGINAL_EXITED_PID_REUSED_NOT_SIGNALLED',
                    'entry_state': entry_state, 'identity_sha256': digest(expected), 'signals': 1}
        sleep(min(.05, max(0, end - clock())))
    raise Hold('PROCESS_EXIT_NOT_CONFIRMED_NO_MORE_SIGNALS')


def _durable_file(path, raw):
    parent = directory(Path(path).parent)
    try:
        fd = os.open(Path(path).name, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW,
                     0o600, dir_fd=parent)
        try:
            pending = memoryview(raw)
            while pending:
                written = os.write(fd, pending)
                need(written > 0, 'ARCHIVE_SHORT_WRITE')
                pending = pending[written:]
            os.fsync(fd)
        finally:
            os.close(fd)
        os.fsync(parent)
    finally:
        os.close(parent)


def archive_known_pyc(package_root, declared_files, *, project_root, archive_root,
                       known_magic, fence):
    """Preserve verified timestamp PYC before restoring exact payload closure.

    declared_files is the installer's independently verified complete payload
    (including its package manifest). No marshal, bytecode execution or unknown
    extra is accepted. known_magic pins the already verified local interpreter
    tag, e.g. {'cpython-312': b'\\xcb\\x0d\\x0d\\x0a'}.
    """
    need(type(fence) is HeldMaintenance, 'LIVE_MAINTENANCE_REQUIRED')
    package_root, project_root, archive_root = map(Path, (package_root, project_root, archive_root))
    need(archive_root.is_absolute() and archive_root.is_relative_to(project_root / '_local')
         and not archive_root.is_relative_to(package_root), 'ARCHIVE_SCOPE_INVALID')
    need(type(known_magic) is dict and bool(known_magic)
         and all(re.fullmatch(r'cpython-[0-9]{3}', k) and type(v) is bytes and len(v) == 4
                 for k, v in known_magic.items()), 'PYC_MAGIC_NOT_PINNED')
    fence.check()
    before = tree_snapshot(package_root)
    need(type(declared_files) is dict and bool(declared_files), 'PAYLOAD_MANIFEST_REQUIRED')
    declared_directories = {'.'}
    for rel in declared_files:
        path = Path(rel)
        need(type(rel) is str and not path.is_absolute()
             and '..' not in path.parts and str(path) == rel, 'PAYLOAD_PATH_INVALID')
        declared_directories.update(str(parent) for parent in path.parents)
    need('wce/__pycache__' not in declared_directories, 'PYC_DECLARED_AS_PAYLOAD')
    need(set(before['directories']) <= declared_directories | {'wce/__pycache__'},
         'UNKNOWN_PAYLOAD_DIRECTORY')
    for rel, expected in declared_files.items():
        need(rel in before['files'] and before['files'][rel]['sha256'] == expected,
             'PAYLOAD_SOURCE_MISMATCH')
    extras = sorted(set(before['files']) - set(declared_files))
    records, raws = [], []
    for rel in extras:
        match = re.fullmatch(r'wce/__pycache__/([A-Za-z_][A-Za-z0-9_]*)\.(cpython-[0-9]{3})\.pyc', rel)
        need(match is not None, 'UNKNOWN_PAYLOAD_EXTRA')
        source = 'wce/' + match[1] + '.py'
        need(source in declared_files and match[2] in known_magic, 'PYC_SOURCE_OR_TAG_UNKNOWN')
        value = before['files'][rel]
        need(value['pin'][3] == os.getuid() and value['pin'][5] == 1
             and value['pin'][6] <= 2 * 1024 * 1024, 'PYC_FILE_INVALID')
        parent = directory((package_root / rel).parent)
        try:
            fd = os.open(Path(rel).name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=parent)
            try:
                need(pin(os.fstat(fd)) == value['pin'], 'PYC_CHANGED')
                raw = os.pread(fd, value['pin'][6] + 1, 0)
            finally:
                os.close(fd)
        finally:
            os.close(parent)
        need(len(raw) == value['pin'][6] and sha256(raw).hexdigest() == value['sha256']
             and len(raw) >= 16, 'PYC_CHANGED')
        magic, flags, mtime, size = struct.unpack('<4sIII', raw[:16])
        source_pin = before['files'][source]['pin']
        need(magic == known_magic[match[2]] and flags == 0
             and mtime == ((source_pin[7] // 1000000000) & 0xffffffff)
             and size == source_pin[6], 'PYC_HEADER_SOURCE_MISMATCH')
        records.append({'relative_path': rel, 'source': source, 'original': value,
                        'archive_name': sha256(rel.encode()).hexdigest() + '.pyc'})
        raws.append(raw)
    if not extras:
        need(set(before['directories']) == declared_directories,
             'PAYLOAD_DIRECTORY_CLOSURE_HOLD')
        return {'state': 'ALREADY_EXACT_PAYLOAD', 'archived': 0}
    fence.check()
    need(tree_snapshot(package_root) == before, 'PACKAGE_CHANGED_BEFORE_ARCHIVE')
    parent = directory(archive_root.parent)
    try:
        os.mkdir(archive_root.name, 0o700, dir_fd=parent)
        os.fsync(parent)
    finally:
        os.close(parent)
    for record, raw in zip(records, raws):
        _durable_file(archive_root / record['archive_name'], raw)
        need(file_pin(archive_root / record['archive_name'])['sha256'] == record['original']['sha256'],
             'ARCHIVE_READBACK_FAILED')
    _durable_file(archive_root / 'manifest.json',
                  (json.dumps({'state': 'COPIES_DURABLE_BEFORE_CACHE_REMOVAL',
                               'package': str(package_root), 'files': records}, sort_keys=True) + '\n').encode())
    for record in records:
        fence.check()
        path = package_root / record['relative_path']
        need(file_pin(package_root / record['source']) == before['files'][record['source']],
             'PYC_SOURCE_CHANGED_BEFORE_REMOVAL')
        need(file_pin(path) == record['original'], 'PYC_CHANGED_BEFORE_REMOVAL')
        fd = directory(path.parent)
        try:
            need(pin(os.stat(path.name, dir_fd=fd, follow_symlinks=False)) == record['original']['pin'],
                 'PYC_REPLACED_BEFORE_REMOVAL')
            os.unlink(path.name, dir_fd=fd)
            os.fsync(fd)
        finally:
            os.close(fd)
    pycache = package_root / 'wce/__pycache__'
    fd = directory(pycache)
    try:
        need(not os.listdir(fd), 'PYC_DIRECTORY_NEW_EXTRA')
    finally:
        os.close(fd)
    fd = directory(pycache.parent)
    try:
        need(pin(os.stat(pycache.name, dir_fd=fd, follow_symlinks=False))[:5]
             == before['directories']['wce/__pycache__']['pin'], 'PYC_DIRECTORY_REPLACED')
        os.rmdir(pycache.name, dir_fd=fd)
        os.fsync(fd)
    finally:
        os.close(fd)
    after = tree_snapshot(package_root)
    need(set(after['files']) == set(declared_files)
         and set(after['directories']) == declared_directories
         and all(after['files'][p]['sha256'] == h for p, h in declared_files.items()),
         'PAYLOAD_FINAL_CLOSURE_HOLD')
    return {'state': 'VERIFIED_PYC_ARCHIVED_EXACT_PAYLOAD_RESTORED', 'archived': len(records),
            'archive_manifest_sha256': file_pin(archive_root / 'manifest.json')['sha256']}


def tree_snapshot(root):
    root = Path(root)
    files, dirs = {}, {}
    todo = [root]
    while todo:
        path = todo.pop()
        fd = directory(path)
        try:
            info = os.fstat(fd)
            need(info.st_uid == os.getuid(), 'TREE_OWNER_MISMATCH')
            names = sorted(os.listdir(fd))
            dirs[str(path.relative_to(root))] = {'pin': pin(info)[:5], 'names': names}
            for name in names:
                child = path / name
                st = os.stat(name, dir_fd=fd, follow_symlinks=False)
                need(len(files) + len(dirs) < 10000, 'TREE_BOUND')
                if stat.S_ISDIR(st.st_mode):
                    todo.append(child)
                else:
                    need(stat.S_ISREG(st.st_mode) and st.st_uid == os.getuid(),
                         'TREE_LINK_OR_TYPE')
                    files[str(child.relative_to(root))] = file_pin(child)
            need(sorted(os.listdir(fd)) == names, 'TREE_CHANGED')
        finally:
            os.close(fd)
    return {'files': files, 'directories': dirs}


def remove_old_tree(root, expected_tree, *, cache_parent, current_version,
                    fence, host, readiness_guard):
    """Exact old cache only, after current install+CUP+native handoff guard.

    No recursive rmtree or glob. A missing old directory is a zero-delete no-op.
    Failure after partial deletion is HOLD, never automatic replay or restore.
    """
    need(type(fence) is HeldMaintenance and callable(readiness_guard), 'LIVE_GATES_REQUIRED')
    root, cache_parent = Path(root), Path(cache_parent)
    need(root.is_absolute() and root.parent == cache_parent
         and re.fullmatch(r'0\.4\.[0-9]+', root.name) is not None
         and root.name != current_version, 'CURRENT_OR_OUT_OF_SCOPE_TREE')
    fence.check()
    need(readiness_guard() is True, 'CURRENT_HANDOFF_NOT_CONFIRMED')
    if not os.path.lexists(root):
        return {'state': 'ALREADY_ABSENT', 'deleted_files': 0}
    need(tree_snapshot(root) == expected_tree, 'TREE_FINGERPRINT_CHANGED')
    need(host.references(root) == [], 'TREE_STILL_REFERENCED')
    # Keep the root and all parents pinned across every fd-relative unlink.
    with ExitStack() as stack:
        parent = directory(root.parent)
        stack.callback(os.close, parent)
        root_fd = directory(root)
        stack.callback(os.close, root_fd)
        root_pin = pin(os.fstat(root_fd))[:5]
        def guard():
            fence.check()
            need(readiness_guard() is True, 'CURRENT_HANDOFF_NOT_CONFIRMED')
            need(pin(os.stat(root.name, dir_fd=parent, follow_symlinks=False))[:5] == root_pin,
                 'TREE_ROOT_REPLACED')
            need(host.references(root) == [], 'TREE_REFERENCE_APPEARED')
        deleted = 0
        for rel, expected in sorted(expected_tree['files'].items()):
            guard()
            path = root / rel
            need(file_pin(path) == expected, 'TREE_FILE_CHANGED')
            fd = directory(path.parent)
            try:
                need(pin(os.stat(path.name, dir_fd=fd, follow_symlinks=False)) == expected['pin'],
                     'TREE_FILE_REPLACED')
                os.unlink(path.name, dir_fd=fd)
                os.fsync(fd)
                deleted += 1
            finally:
                os.close(fd)
        for rel, expected in sorted(expected_tree['directories'].items(),
                                    key=lambda item: len(Path(item[0]).parts), reverse=True):
            path = root if rel == '.' else root / rel
            guard()
            fd = directory(path)
            try:
                need(pin(os.fstat(fd))[:5] == expected['pin'] and not os.listdir(fd),
                     'TREE_DIRECTORY_CHANGED')
            finally:
                os.close(fd)
            par = directory(path.parent)
            try:
                need(pin(os.stat(path.name, dir_fd=par, follow_symlinks=False))[:5] == expected['pin'],
                     'TREE_DIRECTORY_REPLACED')
                os.rmdir(path.name, dir_fd=par)
                os.fsync(par)
            finally:
                os.close(par)
    return {'state': 'EXACT_OLD_TREE_REMOVED', 'deleted_files': deleted}


if __name__ == '__main__':
    raise SystemExit('HOST_INSTALLER_CONTEXT_REQUIRED; no standalone apply or MCP entry')


def production_rules_preservation(registry, fence):
    """Normal updater's actual setup fence protects preference bytes, not rights.

    Consume `files` as additional inventory extras; keep absent names separate
    and call again before returning from maintenance. No SQLite open or cleanup.
    The full database is stream-hashed once, never loaded as history/text.
    """
    need(type(fence) is HeldMaintenance, 'LIVE_MAINTENANCE_REQUIRED')
    fence.check()
    root = Path(registry).parent
    need(Path(fence.descriptors[0][0]) == root/'connection-setup.lock', 'RULES_SETUP_LOCK_MISMATCH')
    parent = directory(root)
    try:
        root_pin = pin(os.fstat(parent))[:5]
        transient = [root/(name+suffix) for name in ('production-rules.sqlite3',)
                     for suffix in ('-journal','-wal','-shm')]
        need(not any(os.path.lexists(path) for path in transient), 'RULES_WRITE_IN_FLIGHT')
        files, absent = {}, []
        for name in ('production-rules.sqlite3','production-rules.lock'):
            fence.check()
            path = root/name
            if not os.path.lexists(path):
                absent.append(str(path)); continue
            # No lifetime-size ceiling inherited from the generic hash helper.
            info = path.lstat()
            value = file_pin(path, maximum=info.st_size)
            need(value['pin'][3] == os.getuid() and value['pin'][5] == 1
                 and stat.S_IMODE(value['pin'][2]) == 0o600, 'RULES_FILE_IDENTITY_INVALID')
            files[str(path)] = value
        fence.check()
        need(pin(os.fstat(parent))[:5] == root_pin
             and not any(os.path.lexists(path) for path in transient+list(map(Path,absent))),
             'RULES_PRESERVATION_CHANGED')
        return {'files':files,'absent':absent,'transient_absent':list(map(str,transient)),
                'preferences_only':True,'business_calls':0}
    finally:
        os.close(parent)
