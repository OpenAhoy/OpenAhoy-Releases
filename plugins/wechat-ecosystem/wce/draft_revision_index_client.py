"""Bounded fresh-exec transport for the trusted native index lookup only."""
import errno
import math
import os
from pathlib import Path
import selectors
import subprocess
import sys
import time
from .draft_revision_native_source import SourceHold, checked_guard, require
from .draft_revision_index_worker import (INPUT_LIMIT, OUTPUT_LIMIT, QUERY_SECONDS,
    PROTOCOL, ERROR_CODES, WorkerHold, encode, decode, validate_request, validate_rows)

WORKER_PATH = Path(__file__).with_name('draft_revision_index_worker.py')


def _finish(child):
    """Only this invocation's child; real exit observed before successful return."""
    try:
        if child.poll() is None:
            child.terminate()
            try:
                child.wait(timeout=0.2)
            except subprocess.TimeoutExpired:
                child.kill()
                child.wait(timeout=1.0)
        else:
            child.wait(timeout=0)
    except (OSError, subprocess.TimeoutExpired):
        raise SourceHold('HOST_INDEX_WORKER_CLEANUP_HOLD') from None
    finally:
        for stream in (child.stdin, child.stdout, child.stderr):
            if stream is not None:
                stream.close()


def _exchange(request, guard, deadline):
    """Fixed executable/script and minimal environment; no caller spawn options."""
    checked_guard(guard)
    require(time.monotonic() < deadline, 'HOST_INDEX_WORKER_DEADLINE')
    raw = encode(request)
    require(len(raw) <= INPUT_LIMIT, 'HOST_INDEX_WORKER_PROTOCOL')
    child = None
    selector = selectors.DefaultSelector()
    try:
        # No inherited account/secret environment, shell, preexec_fn, pass_fds,
        # package path injection, persistent process or child retry.
        child = subprocess.Popen([sys.executable, '-I', '-B', str(WORKER_PATH)],
            stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            shell=False, close_fds=True, env={'LC_ALL': 'C', 'LANG': 'C'},
            cwd=str(WORKER_PATH.parent), bufsize=0)
        for stream in (child.stdin, child.stdout, child.stderr):
            os.set_blocking(stream.fileno(), False)
        selector.register(child.stdin, selectors.EVENT_WRITE, 'input')
        selector.register(child.stdout, selectors.EVENT_READ, 'output')
        selector.register(child.stderr, selectors.EVENT_READ, 'error')
        sent, output = 0, bytearray()
        while selector.get_map():
            checked_guard(guard)
            remaining = deadline - time.monotonic()
            require(remaining > 0, 'HOST_INDEX_WORKER_DEADLINE')
            for key, _ in selector.select(min(0.05, remaining)):
                if key.data == 'input':
                    try:
                        count = os.write(key.fd, raw[sent:])
                    except BlockingIOError as error:
                        if error.errno not in (errno.EAGAIN, errno.EWOULDBLOCK):
                            raise
                        # Readiness is advisory; keep this child and offset.
                        continue
                    require(count > 0, 'HOST_INDEX_WORKER_PROTOCOL')
                    sent += count
                    if sent == len(raw):
                        selector.unregister(key.fileobj)
                        key.fileobj.close()
                else:
                    # Read at most the bounded remainder + one sentinel byte.
                    size = min(4096, OUTPUT_LIMIT + 1 - len(output)) if key.data == 'output' else 1
                    try:
                        part = os.read(key.fd, size)
                    except BlockingIOError as error:
                        if error.errno not in (errno.EAGAIN, errno.EWOULDBLOCK):
                            raise
                        # No bytes is not EOF until the actual read returns it.
                        continue
                    if not part:
                        selector.unregister(key.fileobj)
                    elif key.data == 'error':
                        raise SourceHold('HOST_INDEX_WORKER_PROTOCOL')
                    else:
                        output.extend(part)
                        require(len(output) <= OUTPUT_LIMIT, 'HOST_INDEX_WORKER_PROTOCOL')
        while child.poll() is None:
            checked_guard(guard)
            remaining = deadline - time.monotonic()
            require(remaining > 0, 'HOST_INDEX_WORKER_DEADLINE')
            try:
                child.wait(timeout=min(0.05, remaining))
            except subprocess.TimeoutExpired:
                pass
        checked_guard(guard)
        require(time.monotonic() < deadline, 'HOST_INDEX_WORKER_DEADLINE')
        require(child.returncode == 0 and sent == len(raw), 'HOST_INDEX_WORKER_PROTOCOL')
        return bytes(output)
    except (OSError, ValueError, subprocess.SubprocessError):
        raise SourceHold('HOST_INDEX_WORKER_START_OR_IO_HOLD') from None
    finally:
        selector.close()
        if child is not None:
            _finish(child)


def query_index(state_path, session_root, identity, thread, owner_thread, guard, *, deadline=None):
    """Trusted host parameters only. Caller must retain and recheck source pins."""
    checked_guard(guard)
    now = time.monotonic()
    require(deadline is None or (type(deadline) in (float, int) and math.isfinite(deadline)),
            'HOST_INDEX_WORKER_DEADLINE')
    effective_deadline = min(deadline, now + QUERY_SECONDS) if deadline is not None else now + QUERY_SECONDS
    require(effective_deadline > now, 'HOST_INDEX_WORKER_DEADLINE')
    request = {'protocol': PROTOCOL, 'index_path': str(state_path), 'session_root': str(session_root),
        'device': identity[0], 'inode': identity[1], 'owner_thread': owner_thread,
        'thread': thread, 'deadline': effective_deadline}
    try:
        validate_request(request)
        raw = _exchange(request, guard, effective_deadline)
        result = decode(raw, OUTPUT_LIMIT)
        require(type(result) is dict and result.get('protocol') == PROTOCOL,
                'HOST_INDEX_WORKER_PROTOCOL')
        if result.get('status') == 'HOLD':
            require(set(result) == {'protocol', 'status', 'code'}
                    and type(result['code']) is str and result['code'] in ERROR_CODES,
                    'HOST_INDEX_WORKER_PROTOCOL')
            raise SourceHold(result['code'])
        require(set(result) == {'protocol', 'status', 'rows'} and result['status'] == 'OK',
                'HOST_INDEX_WORKER_PROTOCOL')
        row = validate_rows(result['rows'], thread, owner_thread, Path(session_root))
    except WorkerHold as error:
        raise SourceHold(error.code if error.code in ERROR_CODES else 'HOST_INDEX_WORKER_PROTOCOL') from None
    except (TypeError, ValueError, UnicodeError, OverflowError):
        raise SourceHold('HOST_INDEX_WORKER_PROTOCOL') from None
    checked_guard(guard)
    require(time.monotonic() < effective_deadline, 'HOST_INDEX_WORKER_DEADLINE')
    return row
