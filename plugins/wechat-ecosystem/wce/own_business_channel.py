"""One explicit Group tool per owned stdio child; never an ordinary fallback.

UNARMED source component gates production acquisition. Unit tests drive only the
pure session using fake I/O. No actual child has been launched for this prototype.
"""
import json
import math
import os
from pathlib import Path
import selectors
import select
import stat
import threading
import errno
import subprocess
import sys
import time

from wce.contracts import WCEError
from wce.draft_group_contracts import digest
from wce import own_business_rpc as rpc
from wce import own_business_source as sources
from wce import own_business_temporal as temporal
from wce.own_fd_domain import fd_capacity_allowed

MAX_STDOUT = 3 * rpc.MAX_FRAME
MAX_STDERR = 65536
SLICE = .05
UNKNOWN = 'ARTICLE_CHANNEL_RESULT_UNKNOWN_QUERY_ORIGINAL_KEY'
NOT_READY = 'ARTICLE_DOMAIN_NOT_READY'


class _IOFailure(Exception):
    """Private fixed classification only; never includes child text."""


def _remaining(deadline, cancel, clock):
    if cancel is not None and cancel() is True:
        raise _IOFailure('CANCELLED')
    remaining = deadline - clock()
    if remaining <= 0:
        raise _IOFailure('DEADLINE')
    return remaining


_OWNED_LOCK = threading.Lock()
_OWNED_CHILD = None  # Strong ownership survives a partial cleanup/failed wait.


def _reserve_child(owner):
    global _OWNED_CHILD
    with _OWNED_LOCK:
        if _OWNED_CHILD is not None:
            raise _IOFailure('CHILD_REAP_PENDING')
        _OWNED_CHILD = owner
        owner.slot_registered = True


def _release_child(owner):
    global _OWNED_CHILD
    with _OWNED_LOCK:
        if _OWNED_CHILD is owner and owner.closed:
            _OWNED_CHILD = None
            owner.slot_registered = False


def _require_spawn_available():
    with _OWNED_LOCK:
        owner = _OWNED_CHILD
    if owner is not None and owner.cleanup_started:
        # This only reaps the same owned handle with wait(0). No signal, replay,
        # spawn, indefinite wait or cleanup of another broker is performed.
        owner.reap_nonblocking()
    with _OWNED_LOCK:
        if _OWNED_CHILD is not None:
            raise _IOFailure('CHILD_REAP_PENDING')


def retry_pending_child_cleanup():
    """Internal bounded owner handoff; not a tool, scheduler or business retry."""
    with _OWNED_LOCK:
        owner = _OWNED_CHILD
    if owner is None:
        return True
    if not owner.cleanup_started:
        return False
    try:
        owner.close()
    except BaseException:
        return owner.closed
    return owner.closed


class _ParentInputEOF:
    """Non-consuming EOF only, not concurrent MCP message/cancel processing."""
    def __init__(self, fd):
        if type(fd) is not int or fd < 0:
            raise _IOFailure('PARENT_INPUT')
        info = os.fstat(fd)
        if not (stat.S_ISFIFO(info.st_mode) or stat.S_ISSOCK(info.st_mode)):
            raise _IOFailure('PARENT_INPUT')
        self.kqueue = None
        self.poller = None
        self.closed = False
        try:
            if hasattr(select, 'kqueue'):
                self.kqueue = select.kqueue()
                event = select.kevent(fd, filter=select.KQ_FILTER_READ,
                    flags=select.KQ_EV_ADD | select.KQ_EV_CLEAR)
                self.kqueue.control([event], 0, 0)
            elif hasattr(select, 'poll'):
                self.poller = select.poll()
                self.poller.register(fd, select.POLLHUP | select.POLLERR | select.POLLNVAL)
            else:
                raise _IOFailure('PARENT_INPUT_UNSUPPORTED')
        except BaseException:
            try:self.close()
            except BaseException:pass  # Never replace the original registration failure.
            raise

    def __call__(self):
        if self.closed:
            return True
        if self.kqueue is not None:
            events = self.kqueue.control(None, 1, 0)
            return any(event.flags & (select.KQ_EV_EOF | select.KQ_EV_ERROR) for event in events)
        return any(mask & (select.POLLHUP | select.POLLERR | select.POLLNVAL)
                   for fd, mask in self.poller.poll(0))

    def close(self):
        if not self.closed:
            if self.kqueue is not None:self.kqueue.close()
            self.closed = True


class _SubprocessIO:
    """Nonblocking three-pipe owner. Kills only this exact short child on stop."""
    def __init__(self, resources, deadline, cancel=None, clock=time.monotonic):
        self.clock, self.cancel, self.deadline = clock, cancel, deadline
        self.pending = bytearray()
        self.stdout_bytes = self.stderr_bytes = 0
        self.eof = set()
        self.closed = False
        self.io_closed = False
        self.child_reaped = False
        self.cleanup_started = False
        self.cleanup_state = 'OPEN'
        self.cleanup_lock = threading.Lock()
        self.slot_registered = False
        self.first_cleanup_error = None
        self.process = None
        self.life_reader = self.life_writer = None
        self.life_pins = {}
        self.selector = selectors.DefaultSelector()
        try:
            _require_spawn_available()
            _remaining(deadline, cancel, clock)
            resources.guard()
            self.life_reader, self.life_writer = os.pipe()
            self.life_pins = {name:self._pipe_identity(os.fstat(getattr(self,name)))
                              for name in ('life_reader','life_writer')}
            # Popen may transiently open three pipe pairs plus its exec-error
            # pipe. Existing source pins, lifetime ends and EOF detector count
            # in the real baseline; keep the original 35-FD source reserve.
            if not fd_capacity_allowed(len(os.listdir('/dev/fd')), 8, 35):
                raise _IOFailure('FD_CAPACITY')
            wrapper, inherited = sources.execution_wrapper(resources, deadline, self.life_reader)
            executable = Path(sys.executable)
            if not executable.is_absolute():
                raise _IOFailure('INTERPRETER')
            # No shell/env/argv chooses a source. HOME is the verified passwd
            # home, not inherited state. Child may create its legitimate Group
            # owner under original rules; cleanup never signals that owner.
            _reserve_child(self)
            self.process = subprocess.Popen([str(executable), '-I', '-B', '-c', wrapper.decode('utf-8')],
                cwd=resources.runtime.root, env={'PATH':'/usr/bin:/bin:/usr/sbin:/sbin',
                    'HOME':str(resources.runtime.home)}, stdin=subprocess.PIPE,
                stdout=subprocess.PIPE, stderr=subprocess.PIPE, close_fds=True,
                pass_fds=inherited)
            self._close_lifetime('life_reader')
            for stream, role in ((self.process.stdout,'out'), (self.process.stderr,'err')):
                os.set_blocking(stream.fileno(), False)
                self.selector.register(stream, selectors.EVENT_READ, role)
            os.set_blocking(self.process.stdin.fileno(), False)
            _remaining(deadline, cancel, clock)
        except BaseException:
            try:self.close()
            except BaseException:pass
            raise

    def _pump(self, *, write=False):
        timeout = min(SLICE, _remaining(self.deadline, self.cancel, self.clock))
        events = self.selector.select(timeout)
        writable = False
        for key, mask in events:
            role = key.data
            if role == 'in':
                writable = True
                continue
            try:
                block = os.read(key.fileobj.fileno(), 65536)
            except BlockingIOError:
                continue
            if not block:
                self.eof.add(role)
                self.selector.unregister(key.fileobj)
                continue
            if role == 'err':
                # Discard bytes; no decoding/logging of possibly private stderr.
                self.stderr_bytes += len(block)
                if self.stderr_bytes > MAX_STDERR:
                    raise _IOFailure('STDERR_LIMIT')
            else:
                self.stdout_bytes += len(block)
                if self.stdout_bytes > MAX_STDOUT:
                    raise _IOFailure('STDOUT_LIMIT')
                self.pending.extend(block)
                # A complete frame's bound is checked by read_frame. Retained
                # aggregate is bounded too; no unbounded line or trailing spam.
                if len(self.pending) > MAX_STDOUT:
                    raise _IOFailure('STDOUT_LIMIT')
        _remaining(self.deadline, self.cancel, self.clock)
        return writable

    def write(self, frame):
        if type(frame) is not bytes or len(frame) > rpc.MAX_FRAME:
            raise _IOFailure('INPUT_LIMIT')
        remaining = memoryview(frame)
        stdin = self.process.stdin
        self.selector.register(stdin, selectors.EVENT_WRITE, 'in')
        try:
            while remaining:
                _remaining(self.deadline, self.cancel, self.clock)
                try:
                    written = os.write(stdin.fileno(), remaining)
                except BlockingIOError:
                    written = 0
                if written:
                    remaining = remaining[written:]
                else:
                    self._pump(write=True)
        finally:
            try:self.selector.unregister(stdin)
            except KeyError:pass

    def read_frame(self):
        while b'\n' not in self.pending:
            if len(self.pending) >= rpc.MAX_FRAME or 'out' in self.eof:
                raise _IOFailure('EOF_OR_FRAME_LIMIT')
            self._pump()
        _remaining(self.deadline, self.cancel, self.clock)
        position = self.pending.index(b'\n') + 1
        if position > rpc.MAX_FRAME:
            raise _IOFailure('FRAME_LIMIT')
        frame = bytes(self.pending[:position])
        del self.pending[:position]
        return frame

    def finish(self):
        self.process.stdin.close()
        while self.process.poll() is None or self.eof != {'out','err'}:
            self._pump()
        if self.pending or self.process.returncode != 0:
            raise _IOFailure('TRAILING_OR_EXIT')
        _remaining(self.deadline, self.cancel, self.clock)

    @staticmethod
    def _pipe_identity(info):
        return (info.st_dev,info.st_ino,info.st_mode)

    def _close_lifetime(self, name):
        fd = getattr(self,name)
        if fd is None:
            return
        try:
            info = os.fstat(fd)
        except OSError as error:
            if error.errno == errno.EBADF:
                setattr(self,name,None)
                return
            raise
        # A previous interrupted close may already have released the number.
        # Never retry-close a reused, unrelated descriptor.
        expected = self.life_pins.get(name)
        if expected is None and self.process is not None:
            raise _IOFailure('LIFETIME_PIN_MISSING')
        if expected is not None and self._pipe_identity(info) != expected:
            setattr(self,name,None)
            raise _IOFailure('LIFETIME_DESCRIPTOR_CHANGED')
        os.close(fd)
        setattr(self,name,None)

    def _wait_owned(self, timeout):
        if self.process is None:
            self.child_reaped = True
            return None
        try:
            status = self.process.wait(timeout=timeout)
            if type(status) is not int:
                raise _IOFailure('CHILD_REAP_INVALID')
            self.child_reaped = True
            return None
        except BaseException as error:
            return error

    def _finish_cleanup_state(self):
        self.closed = self.io_closed and self.child_reaped
        self.cleanup_state = ('CLOSED_REAPED' if self.closed else
                              'CHILD_REAP_PENDING' if not self.child_reaped else 'IO_CLEANUP_PENDING')
        if self.closed:
            _release_child(self)

    def reap_nonblocking(self):
        if not self.cleanup_started or not self.cleanup_lock.acquire(blocking=False):
            return False
        try:
            self._wait_owned(0)
            self._finish_cleanup_state()
            return self.closed
        finally:
            self.cleanup_lock.release()

    def close(self):
        if self.closed:
            return
        if not self.cleanup_lock.acquire(blocking=False):
            raise _IOFailure('CLEANUP_ACTIVE')
        first = None
        try:
            self.cleanup_started = True
            if not self.io_closed:
                callbacks = [lambda:self._close_lifetime('life_writer'),
                             lambda:self._close_lifetime('life_reader'), self.selector.close]
                if self.process is not None:
                    callbacks += [stream.close for stream in
                        (self.process.stdin,self.process.stdout,self.process.stderr) if stream is not None]
                complete = True
                for callback in callbacks:
                    try:callback()
                    except BaseException as error:
                        complete = False
                        if first is None:first = error
                self.io_closed = complete
            # wait() is mandatory even when poll/terminate/kill would raise.
            # Only an actual completed wait releases the owned-child slot.
            wait_error = self._wait_owned(0)
            if not self.child_reaped:
                if not isinstance(wait_error,subprocess.TimeoutExpired) and first is None:
                    first = wait_error
                try:self.process.terminate()
                except BaseException as error:
                    if first is None:first = error
                wait_error = self._wait_owned(.2)
                if not self.child_reaped:
                    if not isinstance(wait_error,subprocess.TimeoutExpired) and first is None:
                        first = wait_error
                    try:self.process.kill()
                    except BaseException as error:
                        if first is None:first = error
                    wait_error = self._wait_owned(.2)
                    if not self.child_reaped and first is None:first = wait_error
            self._finish_cleanup_state()
            if self.first_cleanup_error is None and first is not None:
                self.first_cleanup_error = first
            if not self.closed:
                raise _IOFailure('CLEANUP_REAP_PENDING' if not self.child_reaped
                                 else 'CLEANUP_IO_PENDING') from None
            if first is not None:
                raise _IOFailure('CLEANUP') from None
        finally:
            self.cleanup_lock.release()


def _run_session(io, resources, name, arguments, expected_specs, deadline, cancel=None,
                 clock=time.monotonic):
    """Internal state machine, not a standalone business admission entrance."""
    may_send = False
    result = None
    error = None
    known_business_error = None
    try:
        sources.business_name(name)
        _remaining(deadline, cancel, clock)
        resources.guard()
        io.write(rpc.encode_request('initialize', {'protocolVersion':rpc.PROTOCOL,
            'capabilities':{},'clientInfo':{'name':'wce-fixed-business-channel','version':'1'}}, 1))
        rpc.initialize_result(io.read_frame(), resources.runtime.version)
        io.write(rpc.encode_request('notifications/initialized', {}))
        io.write(rpc.encode_request('tools/list', {}, 2))
        rpc.tools_result(io.read_frame(), expected_specs)
        _remaining(deadline, cancel, clock)
        resources.guard()
        _remaining(deadline, cancel, clock)
        # Mark BEFORE the first attempted business write; partial/unknown write
        # is spent/UNKNOWN at the original key, never retried by this channel.
        frame = rpc.encode_request('tools/call', {'name':name,'arguments':arguments}, 3)
        may_send = True
        io.write(frame)
        try:
            result = rpc.tool_value(io.read_frame())
        except WCEError as failure:
            if failure.code == 'ARTICLE_CHANNEL_PROTOCOL_HOLD':
                raise
            known_business_error = failure
        io.finish()
        _remaining(deadline, cancel, clock)
        resources.guard()
        _remaining(deadline, cancel, clock)
    except BaseException as failure:
        error = failure
    finally:
        try:io.close()
        except BaseException as failure:
            if error is None:error = failure
    if error is not None:
        # Never expose raw pipe exceptions/stderr. Cancellation has exactly the
        # same conservative boundary as EOF/deadline once a send was possible.
        raise WCEError(UNKNOWN if may_send else NOT_READY) from None
    if known_business_error is not None:
        raise known_business_error
    return result


def call_business(name, arguments, *, absolute_deadline=None, cancel=None):
    """Only Group four, fixed source recipe, one owned child, no replay."""
    sources.business_name(name)
    deadline = temporal.phase_deadline(300)
    if absolute_deadline is not None:
        if type(absolute_deadline) not in (int,float) or not math.isfinite(absolute_deadline):
            raise WCEError(NOT_READY)
        deadline = min(deadline, absolute_deadline)
    resources = None
    error = None
    session_finished = False
    parent_eof = None
    try:
        _require_spawn_available()
        parent_eof = _ParentInputEOF(sys.stdin.fileno())
        caller_cancel = cancel
        cancel = lambda: parent_eof() or (caller_cancel is not None and caller_cancel() is True)
        _remaining(deadline, cancel, time.monotonic)
        from wce.draft_group_tools import validate
        validate(name, arguments)
        resources = sources.acquire_for_business(name)
        _remaining(deadline, cancel, time.monotonic)
        from wce.bounded_file import FileSource
        from wce import own_group_upgrade
        contract = rpc.strict_json(FileSource(resources.runtime.root/'contracts').read('current-with-groups.json'))
        if digest(contract) != own_group_upgrade.AFTER_SHA:
            raise WCEError(NOT_READY)
        io = _SubprocessIO(resources, deadline, cancel)
        value = _run_session(io, resources, name, arguments, contract['tools'], deadline, cancel)
        session_finished = True
        return value
    except BaseException as failure:
        error = failure
        if isinstance(failure, (_IOFailure, OSError)):
            raise WCEError(NOT_READY) from None
        raise
    finally:
        if parent_eof is not None:
            try:parent_eof.close()
            except BaseException:
                if error is None:
                    error = _IOFailure('PARENT_INPUT_CLOSE')
        if resources is not None:
            try:resources.close(original=error)
            except BaseException:
                if error is None:
                    raise WCEError(UNKNOWN if session_finished else NOT_READY) from None
        if session_finished and error is not None:
            raise WCEError(UNKNOWN) from None
