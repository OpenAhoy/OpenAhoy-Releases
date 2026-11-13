"""Own one fixed, short image-session child; no base broker/drain fallback."""
import math
import os
from pathlib import Path
import socket
import subprocess
import sys
import threading
import time

from .contracts import WCEError
from .draft_group_pin_resources import capacity, close_all
from .own_bootstrap_ipc import receive, send
from . import own_preupload_protocol as protocol
from . import own_preupload_sources as sources

_LOCK = threading.Lock()
_OWNED = None


def _need(value):
    if value is not True:
        raise WCEError('PREUPLOAD_CHILD_HOLD')


class OwnedPreuploadSession:
    def __init__(self, *args, **kwargs):
        raise WCEError('PREUPLOAD_SESSION_ISSUER_REQUIRED')

    def guard(self):
        _need(_OWNED is self and self.pid == os.getpid()
              and self.thread == threading.get_ident() and not self.cleanup_started
              and self.process is not None and self.process.poll() is None
              and time.monotonic() < self.deadline)
        self.sources.guard()
        if self.child_journal is not None:self.child_journal.check()

    def call(self, method, arguments):
        """Only the three strict private frames; never arbitrary SDK forwarding."""
        self.guard()
        sequence = self.sequence+1
        frame = protocol.request_frame(self.observation, sequence, method, arguments)
        # Once the frame may reach the child, failure poisons this session. The
        # caller must inspect the original operation rather than replay here.
        self.sequence = sequence
        try:
            send(self.stream, frame)
            result = receive(self.stream)
            value, error = protocol.validate_response(result,
                observation=self.observation, expected_sequence=sequence)
            self.guard()
            if error is not None:
                raise WCEError(error)
            return value
        except BaseException as original:
            self.close(original=original)
            raise

    def close(self, *, original=None):
        global _OWNED
        if self.closed:
            return
        self.cleanup_started = True
        callbacks = []
        if not self.io_closed:
            self.io_closed = True
            for name in ('connection', 'child_connection'):
                connection = getattr(self, name)
                if connection is not None:
                    callbacks.append(connection.close)
            for name in ('life_reader', 'life_writer'):
                fd = getattr(self, name)
                if fd is not None:
                    setattr(self, name, None)
                    callbacks.append(lambda fd=fd: os.close(fd))
        callbacks.append(self._reap)
        # Preserve the first failure across IO, reaping and source cleanup.
        # A finally block must not replace an earlier error with close failure.
        first = original
        try:
            close_all(callbacks, original)
        except BaseException as error:
            first = error
        try:
            reaped = ((self.process is None and not self.popen_attempted)
                      or (self.process is not None and self.process.poll() is not None))
        except BaseException as error:
            if first is None:
                first = error
            reaped = False  # Unknown process state retains the strong owner.
        if reaped:
            if self.child_journal is not None:
                try:
                    if hasattr(self.child_journal,'claim_sha'):
                        self.child_journal.finish(self.process)
                except BaseException as error:
                    if first is None:first=error
                try:self.child_journal.close(original=first)
                except BaseException as error:
                    if first is None:first=error
            try:
                self.sources.close(original=first)
            except BaseException as error:
                if first is None:
                    first = error
            self.closed = self.sources.closed
            if self.closed:
                with _LOCK:
                    if _OWNED is self:
                        _OWNED = None
        if original is None and first is not None:
            raise first

    def _reap(self):
        process = self.process
        if process is None or process.poll() is not None:
            return
        # Only the handle created by this exact owner is ever signalled.
        process.terminate()
        try:
            process.wait(timeout=.5)
        except subprocess.TimeoutExpired:
            process.kill()
            try:
                process.wait(timeout=.5)
            except subprocess.TimeoutExpired:
                raise WCEError('PREUPLOAD_CHILD_REAP_PENDING') from None


def _reserve(resources, deadline):
    global _OWNED
    with _LOCK:
        # No PIDs supplied by the caller, and no re-spawn while an owned
        # process or failed cleanup is still pending.
        _need(_OWNED is None)
        owner = object.__new__(OwnedPreuploadSession)
        owner.sources, owner.deadline = resources, deadline
        owner.pid, owner.thread = os.getpid(), threading.get_ident()
        owner.process = owner.connection = owner.child_connection = None
        owner.life_reader = owner.life_writer = None
        owner.closed = owner.io_closed = owner.cleanup_started = False
        owner.stream = owner.observation = None
        owner.sequence = 0
        owner.child_journal = None
        owner.popen_attempted = False
        _OWNED = owner
        return owner


def start_fixed_preupload_session():
    """Acquire only the fixed installed inputs. No free path/role/callback."""
    resources = sources.acquire_fixed_sources()
    owner = None
    try:
        value = resources.values()
        remaining = value['not_after']-time.time()
        _need(math.isfinite(remaining) and remaining > 0)
        deadline = time.monotonic()+min(300, remaining)
        owner = _reserve(resources, deadline)
        from .own_preupload_child_journal import TechnicalChildJournal
        from .own_preupload_inputs import JOURNAL_SHA,_FIXED_PHASE_SHAS
        request=sources._json(resources.resume.raw)
        _need(request['profile']=='PREUPLOAD_ORIGINAL_PHASE_SCOPE_V1'
              and request['authority'] is False and request['new_business_budget']==0
              and request['original']['journal_binding_sha256']==JOURNAL_SHA
              and request['original']['phase_claim']['sha256']==_FIXED_PHASE_SHAS['phase_claim'])
        if request['previous_child_terminal_ref'] is not None:
            resources.acquire_evidence(request['previous_child_terminal_ref'])
        owner.child_journal=TechnicalChildJournal(request['original']['original_out'],
            ordinal=request['child_ordinal'],resume_id=request['resume_id'],
            phase_sha=request['original']['phase_claim']['sha256'],binding_sha=resources.binding.sha)
        owner.child_journal.reserve(request['previous_child_terminal_ref'])
        capacity(8, persistent=True)
        owner.connection, owner.child_connection = socket.socketpair(socket.AF_UNIX, socket.SOCK_STREAM)
        owner.life_reader, owner.life_writer = os.pipe()
        raw, inherited = sources.render_wrapper(resources,
            owner.child_connection.fileno(), owner.life_reader, deadline)
        executable = Path(sys.executable)
        _need(executable.is_absolute())
        resources.guard()
        _need(time.monotonic() < deadline)
        # The strong owner slot exists before Popen and its returned handle is
        # stored before closing any descriptor or making a fallible check.
        owner.popen_attempted = True
        owner.child_journal.popen_attempted = True
        owner.process = subprocess.Popen([str(executable), '-I', '-B', '-c', raw.decode('utf-8')],
            cwd=resources.runtime.root, env={'PATH':'/usr/bin:/bin:/usr/sbin:/sbin'},
            stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            close_fds=True, pass_fds=inherited)
        owner.child_journal.created(owner.process)
        owner.child_connection.close()
        owner.child_connection = None
        os.close(owner.life_reader)
        owner.life_reader = None
        owner.observation, owner.stream = protocol.parent_handshake(owner.connection,
            owned_child_pid=owner.process.pid, program_sha256=resources.bootstrap.sha,
            selection_sha256=resources.selection.sha, resume_sha256=resources.resume.sha,
            candidate_scope=resources.runtime.scope, deadline=deadline)
        initialization=receive(owner.stream)
        error=protocol.validate_initialization(initialization,observation=owner.observation)
        if error is not None:raise WCEError(error)
        owner.guard()
        return owner
    except BaseException as original:
        if owner is None:
            resources.close(original=original)
        else:
            owner.close(original=original)
        raise
