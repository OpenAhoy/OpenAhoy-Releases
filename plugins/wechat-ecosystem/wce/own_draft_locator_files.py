"""Private, bounded locator evidence. No account database or general file reader.

The same-UID malicious writer is outside this filesystem integrity boundary.
Every accepted JSON byte string is canonical; every new record is exclusive and
durable before its caller may perform a network operation.
"""
from hashlib import sha256
import json
import math
import os
from pathlib import Path
import re
import stat

from .contracts import WCEError
from .own_bootstrap_security import path_check
from .bounded_file import file_state, identity
from .service import canonical

LIMITS = {'grant': (65536, 512, 16), 'attempt': (65536, 512, 16),
          'claim': (8192, 128, 8), 'outcome': (8192, 128, 8),
          'scan': (65536, 1024, 8), 'observation': (2097152, 12288, 20),
          'complete': (8192, 128, 8), 'stop': (8192, 128, 8),
          'payload': (524288, 4096, 16), 'http': (2097152, 16384, 16)}
MAX_FILES, MAX_BYTES = 64, 4194304


def fail(code='LOCATOR_EVIDENCE_INVALID'):
    raise WCEError(code)


def raw(value):
    try:
        return (canonical(value) + '\n').encode('utf-8')
    except (ValueError, TypeError, UnicodeError, RecursionError):
        fail()


def check_tree(value, nodes, depth, maximum):
    stack, count = [(value, 1)], 0
    while stack:
        item, level = stack.pop(); count += 1
        if count > nodes or level > depth:
            fail('LOCATOR_JSON_LIMIT')
        if type(item) is dict:
            if any(type(k) is not str for k in item): fail()
            stack.extend((v, level + 1) for v in item.keys())
            stack.extend((v, level + 1) for v in item.values())
        elif type(item) is list:
            stack.extend((v, level + 1) for v in item)
        elif type(item) is str:
            try: length = len(item.encode('utf-8'))
            except UnicodeError: fail()
            if length > maximum or any(ord(c) < 32 and c not in '\n\t' for c in item): fail()
        elif item is None or type(item) is bool:
            pass
        elif type(item) is int:
            if not -(2**63) <= item < 2**63: fail()
        elif type(item) is float:
            if not math.isfinite(item): fail()
        else: fail()
    return value


def decode(data, kind, *, canonical_bytes=True):
    maximum, nodes, depth = LIMITS[kind]
    if type(data) is not bytes or not 0 < len(data) <= maximum: fail('LOCATOR_BYTES_LIMIT')
    def unique(pairs):
        result = {}
        for key, value in pairs:
            if key in result: fail()
            result[key] = value
        return result
    try:
        value = json.loads(data.decode('utf-8'), object_pairs_hook=unique,
            parse_constant=lambda _: fail())
    except (ValueError, UnicodeError, RecursionError): fail()
    check_tree(value, nodes, depth, maximum)
    if canonical_bytes and raw(value) != data: fail()
    return value


def encoded(value, kind):
    data = raw(value)
    decode(data, kind)
    return data


def kind_for(name):
    if name in {'grant.json', 'attempt.json', 'observation.json', 'complete.json', 'stop.json'}:
        return name[:-5]
    if name in {'scan1.json', 'scan2.json'}: return 'scan'
    match = re.fullmatch(r'reads/(0[1-9]|1[0-5])\.(claim|outcome)\.json', name)
    if match: return match[2]
    fail('LOCATOR_DIRECTORY_INVALID')


class Evidence:
    def __init__(self, account_root, case_id):
        if type(case_id) is not str or re.fullmatch('[a-f0-9]{64}', case_id) is None: fail()
        self.account = Path(account_root)
        self.account_pin = path_check(self.account, True)
        self.parent = self.account / 'draft-locators'
        self.root = self.parent / case_id
        if not os.path.lexists(self.root): fail('LOCATOR_NOT_CONFIGURED')
        self.parent_pin = path_check(self.parent, True)
        self.pin = path_check(self.root, True)
        self.check()

    def check(self):
        if (path_check(self.account, True) != self.account_pin
                or path_check(self.parent, True) != self.parent_pin
                or path_check(self.root, True) != self.pin): fail()

    def inventory(self):
        self.check()
        names, total = set(), 0
        def scan(directory, prefix=''):
            nonlocal total
            parent_pin = path_check(directory, True)
            with os.scandir(directory) as entries:
                for entry in entries:
                    name = prefix + entry.name
                    if name == 'reads':
                        if not entry.is_dir(follow_symlinks=False): fail()
                        scan(directory / entry.name, 'reads/'); continue
                    if name == '.attempt.tmp':
                        kind = 'attempt'
                    elif name == 'revoked.json':
                        kind = 'stop'
                    else: kind = kind_for(name)
                    info = entry.stat(follow_symlinks=False)
                    path_check(directory / entry.name)
                    if info.st_size <= 0 or info.st_size > LIMITS[kind][0]: fail('LOCATOR_BYTES_LIMIT')
                    names.add(name); total += info.st_size
                    if len(names) > MAX_FILES or total > MAX_BYTES: fail('LOCATOR_CASE_LIMIT')
            if path_check(directory, True) != parent_pin: fail()
        scan(self.root)
        self.check()
        return names, total

    def exists(self, name):
        kind_for(name)
        self.inventory()
        return os.path.lexists(self.root / name)

    def read(self, name):
        kind = kind_for(name)
        self.inventory()
        path = self.root / name
        before, parent_pin = path_check(path), path_check(path.parent, True)
        parent = os.open(path.parent, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
        try:
            if identity(os.fstat(parent)) != parent_pin: fail()
            fd = os.open(path.name, os.O_RDONLY | os.O_NONBLOCK | os.O_NOFOLLOW, dir_fd=parent)
            try:
                if file_state(os.fstat(fd)) != before: fail()
                chunks, size = [], 0
                while True:
                    chunk = os.read(fd, min(65536, LIMITS[kind][0] + 1 - size))
                    if not chunk: break
                    chunks.append(chunk); size += len(chunk)
                    if size > LIMITS[kind][0]: fail('LOCATOR_BYTES_LIMIT')
                if file_state(os.fstat(fd)) != before or size != before[2]: fail()
            finally: os.close(fd)
            if path_check(path) != before or path_check(path.parent, True) != parent_pin: fail()
        finally: os.close(parent)
        self.check()
        data = b''.join(chunks)
        return decode(data, kind), sha256(data).hexdigest()

    def write(self, name, value, *, replace_attempt=False):
        kind = kind_for(name)
        data = encoded(value, kind)
        names, total = self.inventory()
        if replace_attempt and name != 'attempt.json': fail()
        if len(names) + 1 > MAX_FILES or total + len(data) > MAX_BYTES: fail('LOCATOR_CASE_LIMIT')
        path = self.root / name
        if name.startswith('reads/') and not os.path.lexists(path.parent):
            os.mkdir(path.parent, 0o700)
            self._sync(self.root)
        parent_pin = path_check(path.parent, True)
        parent = os.open(path.parent, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
        temporary = '.attempt.tmp' if replace_attempt else path.name
        try:
            if identity(os.fstat(parent)) != parent_pin: fail()
            fd = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600, dir_fd=parent)
            try:
                at = 0
                while at < len(data): at += os.write(fd, data[at:])
                os.fsync(fd)
                if os.fstat(fd).st_size != len(data): fail()
            finally: os.close(fd)
            self.check()
            if path_check(path.parent, True) != parent_pin: fail()
            if replace_attempt:
                os.replace(temporary, path.name, src_dir_fd=parent, dst_dir_fd=parent)
            os.fsync(parent)
        finally: os.close(parent)
        self.check()
        if self.read(name) != (value, sha256(data).hexdigest()): fail()
        return sha256(data).hexdigest()

    @staticmethod
    def _sync(path):
        fd = os.open(path, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
        try: os.fsync(fd)
        finally: os.close(fd)

    def revoked(self):
        self.inventory()
        return os.path.lexists(self.root / 'revoked.json')
