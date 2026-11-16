"""One on-demand per-user account broker; no scheduler or background publishing."""
from contextlib import closing, nullcontext, contextmanager, ExitStack
from hashlib import sha256
from dataclasses import dataclass
from types import MethodType
import stat
import os
import math
from pathlib import Path
import re
import secrets
import select
import socket
import sqlite3
import subprocess
import sys
import threading
import time

from .own_fd_domain import regular_fd_domain, phase_deadline, owned_lifetime
from .bounded_file import file_state, identity
from .contracts import WCEError
from .http_transport import HTTPSender
from .own_auth import APIS, OwnProfile, OwnRegistry
from .own_bootstrap_ipc import peer, receive, send, socket_pin
from .own_bootstrap_security import decode, path_check, private_read
from .own_connection_policy import atomic_write, locked, load_policy, ConnectionPolicy
from .own_connection_token import TokenCache
from .own_connection_workflow import PersistentWorkflow
from .own_contracts import validate
from .prepared_host import ScopedImageDirectory
from .service import digest, canonical

SOCKET, RUNTIME = 'connection.sock', 'connection-runtime.json'
IDLE_SECONDS, QUEUE_SECONDS = 1800, 60
# The three ordinary image/draft calls may spend their existing lease doing
# bounded history checks. Queue admission remains separate and never renews
# this request's execution deadline or any credential/authorization deadline.
ORDINARY_EXECUTION_SECONDS = 300
STARTUP_SECONDS = 120
RECOVERY_SECONDS = 300
RECOVERY_METHOD = 'own.uploads.reconcile'
LOCATOR_METHOD, LOCATOR_SECONDS = 'own.drafts.locate', 300
# Trusted maintenance transport only. Never add to any MCP SPECS/router.
MAINTENANCE_METHOD = '_wce.maintenance.idle_drain.v1'
_SOFTWARE_FIELD = '_broker_software_id'
_BUSY_HANDSHAKE = 'CONNECTION_FD_DOMAIN_BUSY_V1'
from .current_draft_management import NETWORK as DRAFT_MANAGEMENT_NETWORK
NETWORK = {'own.uploads.execute', 'own.drafts.save', 'own.drafts.readback',
           'own.drafts.inventory', 'own.publications.current.prepare',
           'own.publications.current.dispatch', 'own.publications.current.poll',
           'own.publications.slots.discover'} | DRAFT_MANAGEMENT_NETWORK
WRITES = {'own.uploads.execute', 'own.drafts.save'}


def software_identity(root):
    """Software lifetime identity only; never an account permission or grant."""
    try:
        root = Path(root).resolve(strict=True)
        info = root.stat()
        manifest = root / 'package-manifest.json'
        value = {'root': str(root), 'directory': [info.st_dev, info.st_ino],
            'broker': sha256((root / 'wce' / 'own_connection_broker.py').read_bytes()).hexdigest(),
            'manifest': sha256(manifest.read_bytes()).hexdigest() if manifest.exists() else None,
            'python': str(Path(sys.executable).resolve(strict=True))}
        return digest(value)
    except (OSError, ValueError):
        raise WCEError('CONNECTION_SOFTWARE_UNAVAILABLE') from None


def socket_address(path):
    value = str(path)
    if len(os.fsencode(value)) > 100:
        from .draft_group_rich_syn_fixture import rich_syn_socket_address
        synthetic = rich_syn_socket_address(path)
        if synthetic is not None:
            return synthetic
        raise WCEError('CONNECTION_SOCKET_PATH_LIMIT')
    return value



def locator_client_guard(client):
    """Reject a disconnected or protocol-violating client before another read."""
    try:
        readable, _, exceptional = select.select([client], [], [client], 0)
        if exceptional:
            raise WCEError('LOCATOR_CANCELLED')
        if readable:
            try:
                client.recv(1, socket.MSG_PEEK | socket.MSG_DONTWAIT)
            except BlockingIOError:
                return
            # Both EOF and a second request violate the one-request protocol.
            raise WCEError('LOCATOR_CANCELLED')
    except (OSError, ValueError):
        raise WCEError('LOCATOR_CANCELLED') from None


@dataclass(frozen=True)
class _ClientCancellationGuard:
    """Only the native non-consuming client liveness callback, not authority."""
    client: object

    def __post_init__(self):
        if type(self.client) is not _REV_SOCKET_TYPE:
            raise WCEError('LOCATOR_CANCELLED')

    def __call__(self):
        if type(self.client) is not _REV_SOCKET_TYPE:
            raise WCEError('LOCATOR_CANCELLED')
        return locator_client_guard(self.client)


@dataclass(frozen=True)
class _RevisionGuardSnapshot:
    service: object
    policy: object
    workflow: object
    live: object
    owner: object
    active: tuple
    references: tuple
    state: tuple


def _revision_hold():
    raise WCEError('CONNECTION_REVISION_GUARD_HOLD')


def _revision_helpers_original():
    """Unknown Python overrides retain the original three-check path."""
    from . import draft_revision_gate as gates
    from . import publication_lock as writer
    return (AccountService is _REV_SERVICE and AccountService.guard is _REV_ACCOUNT_GUARD
        and Broker is _REV_BROKER and Broker.guard is _REV_BROKER_GUARD
        and Broker._guard_revision is _REV_BROKER_LEAF
        and ConnectionPolicy is _REV_POLICY and ConnectionPolicy.check is _REV_POLICY_CHECK
        and PersistentWorkflow is _REV_WORKFLOW
        and read_runtime is _REV_READ_RUNTIME and read_runtime.__code__ is _REV_RUNTIME_CODE
        and read_runtime.__defaults__ == (True,)
        and private_read is _REV_PRIVATE_READ and decode is _REV_DECODE
        and socket_pin is _REV_SOCKET_PIN and digest is _REV_DIGEST and canonical is _REV_CANONICAL
        and _revision_guard_snapshot is _REV_CAPTURE and _revision_assert_snapshot is _REV_ASSERT
        and _revision_helpers_original is _REV_HELPERS and _revision_hold is _REV_HOLD
        and MethodType is _REV_METHOD_TYPE
        and writer._writer_guard is _REV_WRITER_FACTORY
        and threading.Event is _REV_STOP_TYPE and threading.Event.is_set is _REV_STOP_METHOD
        and _RevisionGuardSnapshot is _REV_SNAPSHOT
        and _ClientCancellationGuard is _REV_CANCEL_TYPE
        and _ClientCancellationGuard.__call__ is _REV_CANCEL_CALL
        and locator_client_guard is _REV_CLIENT_GUARD
        and gates.RevisionExecutionGate is _REV_GATE and gates._ACTIVE is _REV_ACTIVE
        and gates.guard_current is _REV_CANCEL_CURRENT)


def _revision_guard_snapshot(service, deadline):
    """Capture only this stack's concrete binding; never call Gate.held()."""
    if not _REV_HELPERS() or type(service) is not _REV_SERVICE or 'guard' in vars(service):
        return None
    active = _REV_ACTIVE.get()
    if type(active) is not tuple or len(active) != 4:
        return None
    gate = active[0]
    if (type(gate) is not _REV_GATE or gate._active_entry is not active
            or gate.service is not service or active[1] != threading.get_ident()
            or gate.deadline != deadline or type(gate.entry_id) is not str):
        return None
    cancel = gate.cancel_guard
    if cancel is not None and (type(cancel) is not _REV_CANCEL_TYPE
            or type(cancel.client) is not _REV_SOCKET_TYPE):
        return None
    policy, workflow = service.policy, service.workflow
    if (type(policy) is not _REV_POLICY or 'check' in vars(policy)
            or type(policy.check) is not MethodType or policy.check.__self__ is not policy
            or policy.check.__func__ is not _REV_POLICY_CHECK
            or type(workflow) is not _REV_WORKFLOW or workflow.policy is not policy):
        return None
    live = workflow.live_guard
    if type(live) is not MethodType or live.__func__ is not _REV_BROKER_GUARD:
        return None
    owner = live.__self__
    if (type(owner) is not _REV_BROKER or owner.service is not service or owner.policy is not policy
            or 'guard' in vars(owner) or '_guard_revision' in vars(owner)
            or type(owner.guard) is not MethodType or owner.guard.__func__ is not _REV_BROKER_GUARD
            or owner.guard.__self__ is not owner
            or type(service.serial) is not _REV_LOCK_TYPE
            or type(owner.stop) is not _REV_STOP_TYPE or 'is_set' in vars(owner.stop)
            or type(owner.stop.is_set) is not MethodType or owner.stop.is_set.__func__ is not _REV_STOP_METHOD):
        return None
    # This is fresh held-FD ownership observation, not permission memoization.
    try:
        fd, expected = active[2:]
        info = os.fstat(fd); actual = (policy.root / 'connection-policy.lock').lstat()
        if (identity(info) != expected or identity(actual) != expected
                or not stat.S_ISREG(info.st_mode) or not stat.S_ISREG(actual.st_mode)
                or info.st_uid != os.getuid() or actual.st_uid != os.getuid()
                or info.st_nlink != 1 or actual.st_nlink != 1
                or stat.S_IMODE(info.st_mode) != 0o600 or actual.st_mode != info.st_mode
                or not service.serial.locked()):
            _REV_HOLD()
        if _REV_WRITER_FACTORY(policy.root, policy.data['appid'])() is not True:
            _REV_HOLD()
        # Mutable dictionaries are copied to immutable canonical strings.
        state = (gate.entry_id, gate.deadline, policy.path, tuple(policy.pin),
            tuple(policy.root_pin), tuple(policy.image_pin), tuple(policy.database_pin),
            _REV_CANONICAL(policy.value), _REV_CANONICAL(owner.runtime),
            tuple(owner.runtime_pin), owner.socket_path, tuple(owner.socket_pin),
            None if cancel is None else cancel.client.fileno())
        references = (service.serial, owner.stop, cancel, None if cancel is None else cancel.client)
    except (OSError, TypeError, ValueError, AttributeError, KeyError):
        _REV_HOLD()
    return _REV_SNAPSHOT(service, policy, workflow, live, owner, active, references, state)


def _revision_assert_snapshot(snapshot, service, deadline):
    if type(snapshot) is not _REV_SNAPSHOT or snapshot.service is not service:
        _REV_HOLD()
    current = _REV_CAPTURE(service, deadline)
    if (current is None or any(getattr(current, name) is not getattr(snapshot, name)
            for name in ('service', 'policy', 'workflow', 'live', 'owner', 'active'))
            or any(left is not right for left, right in zip(current.references, snapshot.references))
            or current.state != snapshot.state):
        _REV_HOLD()


def read_backup(path):
    pin = path_check(path)
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    try:
        if file_state(os.fstat(fd)) != pin or not 0 < os.fstat(fd).st_size <= 64 * 1024 * 1024:
            raise WCEError('CONNECTION_BACKUP_CONFLICT')
        with os.fdopen(fd, 'rb', closefd=False) as source:
            value = source.read(64 * 1024 * 1024 + 1)
        if file_state(os.fstat(fd)) != pin or path_check(path) != pin or len(value) != pin[2]:
            raise WCEError('CONNECTION_BACKUP_CONFLICT')
        return value
    finally: os.close(fd)


def backup_before_migration(policy, *, physical_resources=None):
    """Bounded byte-identical backup while SQLite excludes other writers."""
    policy.check()
    group_existing=False
    path = policy.root / 'state.sqlite3'
    with closing(sqlite3.connect(str(path), timeout=5)) as db:
        db.execute('BEGIN IMMEDIATE')
        try:
            version = db.execute('PRAGMA user_version').fetchone()[0]
            if version == 9:
                group_existing=True
            elif version in (5, 6, 7, 8):
                return
            elif version != 4:
                raise WCEError('CONNECTION_MIGRATION_UNSUPPORTED')
            else:
                if any(os.path.lexists(str(path) + suffix) for suffix in ('-wal', '-journal')):
                    raise WCEError('CONNECTION_DATABASE_BUSY')
                fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
                try:
                    before = os.fstat(fd)
                    if identity(before) != policy.database_pin[:2] or not 0 < before.st_size <= 64 * 1024 * 1024:
                        raise WCEError('CONNECTION_DATABASE_CHANGED')
                    chunks, total = [], 0
                    while True:
                        chunk = os.read(fd, 65536)
                        if not chunk: break
                        chunks.append(chunk); total += len(chunk)
                        if total > 64 * 1024 * 1024:
                            raise WCEError('CONNECTION_DATABASE_LIMIT')
                    data = b''.join(chunks)
                    if file_state(before) != file_state(os.fstat(fd)) or total != before.st_size:
                        raise WCEError('CONNECTION_DATABASE_CHANGED')
                finally:
                    os.close(fd)
                name = 'state-before-schema5-' + sha256(data).hexdigest() + '.sqlite3'
                target = policy.root / name
                try:
                    fd = os.open(target, os.O_WRONLY | os.O_EXCL | os.O_CREAT | os.O_NOFOLLOW, 0o600)
                except FileExistsError:
                    raw = read_backup(target)
                    if raw != data: raise WCEError('CONNECTION_BACKUP_CONFLICT')
                else:
                    try:
                        with os.fdopen(fd, 'wb', closefd=False) as out:
                            out.write(data); out.flush(); os.fsync(fd)
                    finally: os.close(fd)
                    directory = os.open(policy.root, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
                    try: os.fsync(directory)
                    finally: os.close(directory)
                raw = read_backup(target)
                if raw != data: raise WCEError('CONNECTION_BACKUP_UNVERIFIED')
                policy.check()
        finally:
            db.rollback()


    if group_existing:
        _check_existing_schema9_storage(policy,**({} if physical_resources is None else {"physical_resources":physical_resources}))


def _check_existing_schema9_storage(policy, *, physical_resources=None):
    from .own_history_source import owned_connection
    from .own_history_locators import history_scope
    from .own_store import OwnStore,_check_legacy_history_in
    from .draft_group_runtime_host import ExistingHistoryStoreView
    from .draft_group_history_context import history_policy_context,physical_material_scope
    path=policy.root/'state.sqlite3'
    with owned_connection(path,timeout=5) as db:
        db.row_factory=sqlite3.Row
        db.execute('PRAGMA foreign_keys=ON')
        db.execute('BEGIN IMMEDIATE')
        try:
            if db.execute('PRAGMA user_version').fetchone()[0]!=9:
                raise WCEError('CONNECTION_DATABASE_CHANGED')
            source=db.execute('SELECT source_kind FROM own_config WHERE id=1').fetchone()[0]
            with history_policy_context(path,db,policy),physical_material_scope(db,policy,physical_resources),history_scope(policy,db) as history:
                OwnStore.check(db,source,policy,history=history)
                _check_legacy_history_in(db,source,ExistingHistoryStoreView(path,policy),history=history)
        finally:db.rollback()


class AccountService:
    def __init__(self, policy):
        with regular_fd_domain(deadline=phase_deadline(STARTUP_SECONDS)):
            self._init_mechanical(policy)
            self._init_storage(policy)

    def _init_mechanical(self, policy):
        self.policy, self.tokens = policy, TokenCache(policy)
        self.serial = threading.Lock()

    def _init_storage(self, policy, *, physical_resources=None):
        with regular_fd_domain(deadline=phase_deadline(STARTUP_SECONDS)):
            backup_before_migration(policy,**({} if physical_resources is None else {"physical_resources":physical_resources}))
            initial = self.profile()
            directory = ScopedImageDirectory(policy.root / 'images', policy.actor,
                policy.data['connection_id'], policy.data['resource_id'])
            self.workflow = PersistentWorkflow(policy.root / 'state.sqlite3', OwnRegistry([initial]),
                sender=HTTPSender(enabled=True, safe_transport_diagnostics=True), image_directory=directory,
                policy=policy, token_cache=self.tokens,
                **({} if physical_resources is None else {"physical_resources":physical_resources}))
            self.workflow.activate(initial)

    def set_guard(self, guard):
        self.workflow.live_guard = guard

    def guard(self, deadline):
        # This route merges only one concrete revision boundary. Unknown or
        # shadowed contexts keep the original policy-first sequence below.
        if _REV_HELPERS():
            snapshot = _REV_CAPTURE(self, deadline)
            if snapshot is not None:
                # Only None or the exact native pure wrapper can reach here.
                # Call its frozen original detector, never an unknown callback.
                if snapshot.references[2] is not None:
                    _REV_CLIENT_GUARD(snapshot.references[3])
                _REV_ASSERT(snapshot, self, deadline)
                _REV_BROKER_LEAF(snapshot.owner, snapshot, deadline)
                if time.monotonic() >= deadline:
                    raise WCEError('CONNECTION_QUEUE_EXPIRED')
                return
        self.policy.check()
        from .draft_revision_gate import guard_current
        guard_current(self)
        if self.workflow.live_guard is not None:
            self.workflow.live_guard()
        if time.monotonic() >= deadline:
            raise WCEError('CONNECTION_QUEUE_EXPIRED')

    def profile(self, token=None):
        data, now = self.policy.data, time.time()
        deadline = min(now + 300, token.wall_deadline) if token else now + 300
        from .own_auth import DRAFT_READ_APIS
        granted = frozenset(APIS) | {'local.read', 'local.write'}
        if 'draft_read' in self.policy.value.get('capabilities', ()):
            granted |= frozenset(DRAFT_READ_APIS)
        from .draft_group_rich_syn_fixture import rich_syn_profile_source_kind
        source_kind = rich_syn_profile_source_kind(self)
        return self._profile_values(self.policy.actor, data['connection_id'], data['appid'], data['resource_id'],
            data['generation'], data['epoch'], secrets.randbits(60), deadline, deadline, deadline,
            deadline, 'connection-lease-' + secrets.token_hex(16), source_kind,
            granted, ())

    def _profile_values(self, actor, connection, account, resource, generation, epoch, revision,
                        expires, session_expires, grant_expires, credential_expires, handle, source_kind,
                        granted, evidence):
        return OwnProfile(actor,connection,account,resource,generation,epoch,revision,expires,
            session_expires,grant_expires,credential_expires,handle,source_kind,granted,evidence)

    def call(self, name, arguments, deadline, *, cancel_guard=None, history_locators=None,
             admission_deadline=None):
        with regular_fd_domain(deadline=deadline, admission_deadline=admission_deadline):
            from .own_lineage_request import request_scope
            from .prepared_draft_fixture import decoded_json_scope
            with request_scope(), decoded_json_scope():
                return self._call(name, arguments, deadline, cancel_guard=cancel_guard,
                    history_locators=history_locators, admission_deadline=admission_deadline)

    def _call(self, name, arguments, deadline, *, cancel_guard=None, history_locators=None,
              admission_deadline=None):
        from .draft_group_host_bootstrap import NETWORK_NAMES as group_network, PRIVATE_METHOD as group_bootstrap
        if name in group_network or name == group_bootstrap:
            from .draft_group_host_bootstrap import dispatch_warm_group
            return dispatch_warm_group(self, name, arguments, deadline, cancel_guard)
        from . import draft_revision_tools
        if name in draft_revision_tools.NETWORK:
            draft_revision_tools.validate(name,arguments)
            from .draft_revision_runtime import execute
            return execute(self,name,arguments,deadline,cancel_guard=cancel_guard)
        if name == LOCATOR_METHOD:
            from .own_connection_tools import validate as validate_tool
            validate_tool(name, arguments)
            if arguments['connection_id'] != self.policy.data['connection_id']:
                raise WCEError('CONNECTION_SCOPE_MISMATCH')
            from . import own_draft_locator as locator
            return locator.execute(self, arguments, deadline, cancel_guard=cancel_guard)
        from . import own_replacement_executor as replacements
        from .own_replacement_batch import known_key
        if name == replacements.METHOD:
            return replacements.execute(self, arguments, deadline, history_locators=history_locators)
        if name == RECOVERY_METHOD:
            from .own_connection_tools import validate as validate_tool
            validate_tool(name, arguments)
            if arguments['connection_id'] != self.policy.data['connection_id']:
                raise WCEError('CONNECTION_SCOPE_MISMATCH')
            if known_key(self.policy, arguments['request_key']):
                return replacements.reconcile(self, arguments, deadline)
        queue_deadline = deadline if admission_deadline is None else min(deadline, admission_deadline)
        remaining = queue_deadline - time.monotonic()
        if remaining <= 0 or not self.serial.acquire(timeout=max(0, min(QUEUE_SECONDS, remaining))):
            raise WCEError('CONNECTION_QUEUE_EXPIRED')
        try:
            if time.monotonic() >= queue_deadline: raise WCEError('CONNECTION_QUEUE_EXPIRED')
            self.guard(deadline)
            if name in DRAFT_MANAGEMENT_NETWORK:
                from .current_draft_management_protocol import validate as validate_management
                validate_management(name, arguments)
                if arguments['connection_id'] != self.policy.data['connection_id']:
                    raise WCEError('CONNECTION_SCOPE_MISMATCH')
                self.workflow.activate(self.profile(), deadline=deadline)
                from .current_draft_management import execute
                return execute(self, name, arguments, deadline, cancel_guard)
            from .own_connection_tools import validate as validate_tool
            validate_tool(name, arguments)
            if arguments.get('connection_id') != self.policy.data['connection_id']:
                raise WCEError('CONNECTION_SCOPE_MISMATCH')
            if (name in {'own.drafts.inventory', 'own.publications.slots.discover'}
                    or name == 'own.publications.current.prepare'):
                # Each normal call owns a fresh local profile. These routes
                # return before the common activation below; retaining the
                # startup profile would reject a still-enabled connection
                # after its call-local lifetime. Token acquisition remains in
                # the route, under its original authority and deadline.
                self.workflow.activate(self.profile(), deadline=deadline)
            if name == 'own.drafts.inventory':
                from .current_draft_inventory import execute
                return execute(self, arguments, deadline, cancel_guard)
            if name == 'own.publications.slots.discover':
                from .current_publication_service import execute
                return execute(self, name, arguments, deadline, cancel_guard)
            if name.startswith('own.publications.current.'):
                from .current_publication_service import execute
                return execute(self, name, arguments, deadline, cancel_guard)
            if name == 'own.connections.connect':
                self.tokens.get(lambda: self.guard(deadline))
                self.guard(deadline)
                return self.tokens.status()
            if name in {'own.connections.status', 'own.preflight'}:
                return self.tokens.status()
            if name == RECOVERY_METHOD:
                return self.reconcile(arguments['request_key'], deadline)
            validate(name, arguments)
            if name in {'own.uploads.execute', 'own.drafts.save', 'own.drafts.readback'}:
                # Cover this call's fixed remaining execution window before any
                # request approval/admission. Never extend a token or deadline.
                minimum_validity = max(30.0, min(300.0, deadline - time.monotonic()))
                token = self.tokens.get(lambda: self.guard(deadline),
                    minimum_validity_seconds=minimum_validity)
            else:
                token = self.tokens.get(lambda: self.guard(deadline)) if name in NETWORK else None
            profile = self.profile(token)
            self.guard(deadline)
            self.workflow.activate(profile, token, deadline)
            if name == 'own.assets.receive':
                from .own_connection_input import verify
                verify(self.policy, arguments['relative_path'], arguments['declared_type'])
            if name in WRITES:
                self.workflow.authorize_request(arguments)
            if name in NETWORK:
                with self.workflow.ordinary_http_call():
                    return self.workflow.call(self.policy.actor, name, arguments)
            return self.workflow.call(self.policy.actor, name, arguments)
        finally:
            self.serial.release()

    def reconcile(self, key, deadline):
        from .publication_lock import draft_writer
        with draft_writer(self.policy.root, self.policy.data['appid']):
            return self._reconcile_locked(key, deadline)

    def _reconcile_locked(self, key, deadline):
        from dataclasses import replace
        from .own_auth import READ_APIS
        from . import own_cover_authority as auth
        from .own_connection_reconcile import ReadAttempt
        w, profile = self.workflow, self.profile()
        w.activate(profile, deadline=deadline)
        with _history_transaction(w.db) as (db, history_locators):
            w._resource(db, profile, history_locators=history_locators)
            row = w._history(db, profile, key, history_locators=history_locators)
            if row is not None and row['operation'] in ('body', 'cover'):
                from .own_response_archive import filename, reconcile as restore_response
                has_proof = os.path.lexists(w.db.path.parent / filename(row))
                response_row = dict(row) if has_proof and row['state'] == 'RESULT_UNKNOWN' else None
                if row['operation'] == 'body' and row['state'] == 'RESULT_UNKNOWN' and not has_proof:
                    raise WCEError('OWN_RESPONSE_PROOF_MISSING')
                response_cached = dict(row) if row['state'] == 'SUCCEEDED' else None
            else:
                response_row = response_cached = None
            if response_row is not None or response_cached is not None:
                cached = None
            elif row is not None and row['operation'] == 'cover' and row['state'] == 'SUCCEEDED':
                cached = dict(row)
            else:
                cached = None
                row, intent, original = auth.unknown(w, db, profile, key, history_locators=history_locators)
                _, data = w._asset(db, profile.binding(), intent['asset']['asset_ref'], 'cover')
        if response_row is not None:
            restore_response(w, profile, response_row)
            self.guard(deadline)
            return w._view(profile, response_row)
        if response_cached is not None:
            return w._view(profile, response_cached)
        if cached is not None:
            return w._view(profile, cached)  # No token, claim or scan for success.
        grant, checksum, pin = auth.active(self.policy, original, time.time())
        claimed = auth.claim(self.policy, grant, checksum, time.time())
        from .own_workflow import encoded
        grant_raw = (encoded(grant) + '\n').encode()
        claimed_raw, claimed_pin = private_read(self.policy.root / auth.filename(grant['id'], True))
        if claimed_raw != (encoded(claimed) + '\n').encode():
            raise WCEError('COVER_READ_AUTHORITY_CHANGED')

        def guard():
            self.guard(deadline)
            now = time.time()
            if (not grant['confirmed_at'] <= now < grant['expires_at']
                    or not 0 <= now-claimed['activated_at'] < RECOVERY_SECONDS
                    or private_read(self.policy.root / auth.filename(grant['id'])) != (grant_raw, pin)
                    or private_read(self.policy.root / auth.filename(grant['id'], True)) != (claimed_raw, claimed_pin)):
                raise WCEError('COVER_READ_EXPIRED_OR_CHANGED')
        attempt = None
        try:
            guard()
            token = self.tokens.get(guard)
            guard()
            profile = replace(self.profile(token), granted_actions=frozenset(READ_APIS) | {'local.read'})
            w.activate(profile, token, deadline)
            attempt = ReadAttempt(w, profile, grant, checksum, claimed, row, intent, data)
            w.read_attempt = attempt
            return attempt.run()
        except WCEError as error:
            return {'state': 'RECOVERY_STOPPED', 'request_key': key, 'error': error.code,
                'read_counts': dict(attempt.counts) if attempt else {'list': 0, 'image': 0},
                'diagnostic': dict(attempt.diagnostics) if attempt else {}}
        finally:
            if attempt is not None:
                attempt.stop.set()
            w.read_attempt = None
            # Clearing does not require a still-enabled policy. The next call
            # must activate its own fresh profile before doing any work.
            w.active_lease = w.active_token = None
            w.execution_deadline = None



def read_runtime(policy, active=True):
    policy.check()
    raw, pin = private_read(policy.root / RUNTIME)
    value = decode(raw)
    from .own_base_domain import DOMAIN
    keys = {'schema', 'pid', 'instance', 'policy_digest',
            'candidate_scope', 'identity_digest', 'root_pin'}
    ordinary = (type(value) is dict and set(value) == keys and value.get('schema') == 2)
    basic = (type(value) is dict and set(value) == keys | {'domain'}
             and value.get('schema') == 3 and value.get('domain') == DOMAIN)
    if (not (ordinary or basic)
            or type(value['schema']) is not int
            or type(value['pid']) is not int or value['pid'] <= 0
            or any(type(value[k]) is not str or re.fullmatch('[a-f0-9]{64}', value[k]) is None
                   for k in ('instance', 'policy_digest', 'candidate_scope', 'identity_digest'))
            or value['identity_digest'] != digest(policy.data)
            or type(value['root_pin']) is not list or len(value['root_pin']) != 2
            or any(type(x) is not int or x < 0 for x in value['root_pin'])
            or (active and (value['policy_digest'] != policy.fingerprint
                            or value['candidate_scope'] != policy.value['candidate_scope']))):
        raise WCEError('CONNECTION_RUNTIME_CHANGED')
    if value['root_pin'] != list(policy.root_pin):
        # Only dead-instance cleanup may inspect a pre-reboot root pin.
        # The ordinary active-runtime path still requires current device and inode.
        if active or policy.value['schema'] != 2:
            raise WCEError('CONNECTION_RUNTIME_CHANGED')
        from .own_connection_registry import metadata, transaction_path
        from .own_volume_identity import matches as match_volume
        registry = Path(policy.value['registry_path'])
        proof_path = transaction_path(registry, policy.value['transaction'])
        with locked(proof_path.with_suffix('.lock'), shared=True, existing=True,
                    readonly=True, nonblocking=True):
            proof = metadata(proof_path)
            if (not proof or proof['state'] != 'COMMITTED'
                    or proof['policies'][str(policy.path)]['pins']['root'] != value['root_pin']
                    or match_volume(registry,proof,[(policy.root,value['root_pin'],policy.root_pin)]) is not True):
                raise WCEError('CONNECTION_RUNTIME_CHANGED')
        policy.check()
    return value, pin


def stale_endpoint(policy):
    """Read-only proof for reclaiming a dead instance of this same identity/root.

    A newly human-enabled policy may have a different revision/code scope. These
    are never accepted for a live call, but need not strand a dead old instance.
    Cleanup itself additionally holds the process-lifetime lock.
    """
    info, endpoint = policy.root / RUNTIME, policy.root / SOCKET
    info_pin = endpoint_pin = None
    if os.path.lexists(info):
        old, info_pin = read_runtime(policy, active=False)
        try: os.kill(old['pid'], 0)
        except ProcessLookupError: pass
        except OSError: raise WCEError('CONNECTION_ENDPOINT_CONFLICT') from None
        else: raise WCEError('CONNECTION_ENDPOINT_CONFLICT')
    if os.path.lexists(endpoint):
        endpoint_pin = socket_pin(endpoint)
        with socket.socket(socket.AF_UNIX) as probe:
            probe.settimeout(1)
            try: probe.connect(socket_address(endpoint))
            except ConnectionRefusedError: pass
            except OSError: raise WCEError('CONNECTION_ENDPOINT_CONFLICT') from None
            else: raise WCEError('CONNECTION_ENDPOINT_CONFLICT')
        if socket_pin(endpoint) != endpoint_pin: raise WCEError('CONNECTION_ENDPOINT_CONFLICT')
    policy.check()
    return info_pin, endpoint_pin


class Broker:
    def __init__(self, policy, service=None):
        with regular_fd_domain(deadline=phase_deadline(STARTUP_SECONDS)):
            self.policy, self.service = policy, service
            self.stop = threading.Event()
            self.workers, self.workers_lock = set(), threading.Lock()
            self.slots = threading.BoundedSemaphore(8)
            self.last_call = time.monotonic()
            self.software_id = software_identity(Path(__file__).resolve().parents[1])
            self.runtime = {'schema': 2, 'pid': os.getpid(), 'instance': secrets.token_hex(32),
                'policy_digest': policy.fingerprint, 'candidate_scope': policy.value['candidate_scope'],
                'identity_digest': digest(policy.data), 'root_pin': list(policy.root_pin)}

            from .draft_group_tools import NETWORK as group_names
            from .draft_group_host_bootstrap import PRIVATE_METHOD as group_bootstrap
            from .own_replacement_executor import METHOD as replacement_name
            from .draft_revision_tools import NETWORK as revision_names
            self._fd_route_names = (frozenset(group_names) | {group_bootstrap}, replacement_name, frozenset(revision_names))

    def guard(self):
        with regular_fd_domain(deadline=phase_deadline(QUEUE_SECONDS), stop=self.stop):
            if self.stop.is_set():
                raise WCEError('CONNECTION_STOPPED')
            self.policy.check()
            actual, pin = read_runtime(self.policy)
            if actual != self.runtime or pin != self.runtime_pin or socket_pin(self.socket_path) != self.socket_pin:
                raise WCEError('CONNECTION_RUNTIME_CHANGED')

    def _guard_revision(self, snapshot, deadline):
        """One fresh full check at the original read_runtime entry, never a grant."""
        # A foreign/stale call is a pure rejection, never a queued metadata phase.
        # The complete original snapshot/FD checks still run inside the domain.
        if (type(snapshot) is not _REV_SNAPSHOT or snapshot.owner is not self
                or snapshot.active is not _REV_ACTIVE.get()
                or type(snapshot.active) is not tuple or len(snapshot.active)!=4
                or snapshot.active[1]!=threading.get_ident()):
            _REV_HOLD()
        with regular_fd_domain(deadline=deadline, stop=self.stop):
            _REV_ASSERT(snapshot, snapshot.service, deadline)
            policy = snapshot.policy
            if self.stop.is_set():
                raise WCEError('CONNECTION_STOPPED')
            # The original function remains byte-identical and performs its full
            # policy.check before reading/validating runtime. No result is cached.
            actual, pin = _REV_READ_RUNTIME(policy, active=True)
            if actual != self.runtime or pin != self.runtime_pin or _REV_SOCKET_PIN(self.socket_path) != self.socket_pin:
                raise WCEError('CONNECTION_RUNTIME_CHANGED')
            _REV_ASSERT(snapshot, snapshot.service, deadline)
            if _REV_STOP_METHOD(self.stop):
                raise WCEError('CONNECTION_STOPPED')

    def serve(self, lifetime_fd=None):
        startup_deadline = phase_deadline(STARTUP_SECONDS)
        with regular_fd_domain(deadline=startup_deadline, stop=self.stop):
            if lifetime_fd is not None:
                import fcntl
                if identity(os.fstat(lifetime_fd)) != path_check(self.policy.root / 'connection.lock')[:2]:
                    raise WCEError('CONNECTION_LOCK_HANDOFF_REJECTED')
                fcntl.flock(lifetime_fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
            owner = nullcontext() if lifetime_fd is not None else locked(self.policy.root / 'connection.lock', nonblocking=True)
        with owned_lifetime(owner, deadline=startup_deadline, stop=self.stop):
            with self._listener_initialized(startup_deadline=startup_deadline) as listener:
                self._accept_loop(listener)

    @contextmanager
    def _listener_initialized(self, *, startup_deadline=None):
        startup_deadline = phase_deadline(STARTUP_SECONDS) if startup_deadline is None else startup_deadline
        with ExitStack() as resources:
            with regular_fd_domain(deadline=startup_deadline, stop=self.stop):
                self.policy.check()
                if self.policy.value['schema'] == 2:
                    from .own_connection_registry import check_member
                    check_member(self.policy, durable=True)
                # The separate legacy operator is never displaced or silently killed.
                if any(os.path.lexists(self.policy.root / p) for p in ('operator.sock', 'runtime.json')):
                    raise WCEError('CONNECTION_LEGACY_OPERATOR_ACTIVE')
                self.socket_path = self.policy.root / SOCKET
                address = socket_address(self.socket_path)
                info = self.policy.root / RUNTIME
                stale_info_pin, stale_pin = stale_endpoint(self.policy)
                if stale_pin is not None:
                    if socket_pin(self.socket_path) != stale_pin: raise WCEError('CONNECTION_ENDPOINT_CONFLICT')
                    self.socket_path.unlink()
                if stale_info_pin is not None:
                    if path_check(info) != stale_info_pin: raise WCEError('CONNECTION_RUNTIME_CHANGED')
                    info.unlink()
                self.service = self.service or AccountService(self.policy)
                listener = resources.enter_context(socket.socket(socket.AF_UNIX))
                listener.bind(address); os.chmod(self.socket_path, 0o600)
                self.socket_pin = socket_pin(self.socket_path)
                atomic_write(info, self.runtime)
                self.runtime_pin = path_check(info)
                listener.listen(8); listener.settimeout(1)
                if hasattr(self.service, 'set_guard'):
                    self.service.set_guard(self.guard)
            try:
                yield listener
            finally:
                self.stop.set()
                # No domain or workers_lock is held while joining. Waiting
                # workers observe stop before entering a metadata/SQL phase.
                with self.workers_lock: workers = list(self.workers)
                for worker in workers: worker.join()
                with regular_fd_domain():
                    if getattr(self.service, 'workflow', None) is not None:
                        self.service.workflow.close_preview()
                    self.service.tokens.clear()
                    for path, pin, checker in ((self.socket_path, self.socket_pin, socket_pin),
                            (info, self.runtime_pin, path_check)):
                        try:
                            if checker(path) == pin: path.unlink()
                        except (OSError, WCEError): pass

    def _accept_loop(self, listener):
        while not self.stop.is_set():
            with regular_fd_domain(stop=self.stop, wait=False) as acquired:
                if acquired:
                    self.guard()
                    with self.workers_lock: active = bool(self.workers)
                    idle = not active and time.monotonic() - self.last_call >= IDLE_SECONDS
            # Accepting/registering a socket does not inspect regular files.
            # A busy worker emits only a negative pre-request handshake below.
            if acquired and idle: break
            try: client, _ = listener.accept()
            except socket.timeout: continue
            self.admit(client)

    def admit(self, client):
        # The same lock linearizes idle-drain and every admitted worker.
        # Starting while holding it also prevents finally.join from observing
        # a registered-but-not-started thread if startup raises.
        with self.workers_lock:
            if self.stop.is_set() or not self.slots.acquire(blocking=False):
                client.close()
                return None
            worker = threading.Thread(target=self.handle, args=(client,), daemon=True)
            self.workers.add(worker)
            try:
                worker.start()
            except BaseException:
                self.workers.discard(worker)
                self.slots.release()
                client.close()
                raise
            return worker

    def idle_drain(self, arguments):
        with regular_fd_domain(deadline=phase_deadline(QUEUE_SECONDS), stop=self.stop):
            # Internal installer RPC; the ordinary model router rejects this name.
            # Same-UID local transport is not a malicious-code sandbox.
            expected = {'connection_id': self.policy.data['connection_id'],
                        'instance': self.runtime['instance']}
            if type(arguments) is not dict or arguments != expected:
                raise WCEError('MAINTENANCE_SCOPE_MISMATCH')
            self.guard()
            current = threading.current_thread()
            with self.workers_lock:
                self.guard()  # policy/runtime/pins fresh at the linearization point
                if current not in self.workers or self.workers != {current}:
                    return {'state': 'MAINTENANCE_BUSY'}
                self.stop.set()
                return {'state': 'DRAIN_ACCEPTED'}

    def note_unexpected_error(self, error):
        """One bounded safe receipt; never exception text, locals or arguments."""
        try:
            self.policy.check()
            kind = next((cls.__name__ for cls in
                (ModuleNotFoundError, ImportError, OSError, sqlite3.Error, ValueError,
                 TypeError, KeyError, AttributeError, RuntimeError, AssertionError)
                if isinstance(error, cls)), 'UnexpectedError')
            site = {}
            frame = error.__traceback__
            package = str(Path(__file__).parent) + os.sep
            while frame is not None:
                code = frame.tb_frame.f_code
                if (code.co_filename.startswith(package)
                        and re.fullmatch('[a-zA-Z0-9_]+[.]py', Path(code.co_filename).name)
                        and re.fullmatch('[a-zA-Z0-9_<>]{1,96}', code.co_name)):
                    site = {'file': Path(code.co_filename).name, 'function': code.co_name,
                            'line': frame.tb_lineno}
                frame = frame.tb_next
            atomic_write(self.policy.root / 'connection-last-error.json',
                {'schema': 1, 'phase': 'BROKER_SERVICE', 'type': kind,
                 'site': site, 'software_id': self.software_id})
        except Exception:
            pass  # Diagnostics must not replace the original uncertain result.

    def _fd_effective_deadline(self, request, received_at, route_started_at):
        ordinary = received_at + QUEUE_SECONDS
        if type(request) is not dict or type(request.get('name')) is not str:
            return ordinary
        group_names, replacement_name, revision_names = self._fd_route_names
        name = request['name']
        if name in NETWORK and 'ordinary_absolute_deadline' in request:
            selected = request['ordinary_absolute_deadline']
            if (type(selected) in (int, float)
                    and received_at < selected <= received_at + ORDINARY_EXECUTION_SECONDS
                    and math.isfinite(selected)):
                return selected
            return ordinary  # The closed-envelope validation rejects it below.
        if name in group_names:
            selected = request.get('group_absolute_deadline')
            if (type(selected) in (int, float) and math.isfinite(selected)
                    and received_at < selected <= received_at + RECOVERY_SECONDS):
                return selected
            return ordinary  # Full original envelope/route validation still rejects it.
        if name in (replacement_name, RECOVERY_METHOD):
            return route_started_at + RECOVERY_SECONDS
        if name == LOCATOR_METHOD:
            return received_at + LOCATOR_SECONDS
        if name in revision_names:
            return received_at + RECOVERY_SECONDS
        return ordinary

    def handle(self, client):
        try:
            received_at = time.monotonic()
            deadline = received_at + QUEUE_SECONDS
            client.settimeout(75)
            if peer(client)[1] != os.getuid(): raise WCEError('CONNECTION_PEER_REJECTED')
            with client, client.makefile('rwb') as stream:
                with regular_fd_domain(deadline=deadline, stop=self.stop, wait=False) as acquired:
                    if acquired:self.guard()
                if not acquired:
                    # Not a passed guard or business reply. No request is read.
                    send(stream, {'state': _BUSY_HANDSHAKE, 'runtime': self.runtime})
                    return
                send(stream, self.runtime)
                request = receive(stream)
                effective_deadline = self._fd_effective_deadline(request, received_at, time.monotonic())
                admission_deadline = (min(received_at + QUEUE_SECONDS, effective_deadline)
                    if type(request) is dict and type(request.get('name')) is str
                    and request['name'] in NETWORK and 'ordinary_absolute_deadline' in request else None)
                if (admission_deadline is not None
                        and type(request['ordinary_absolute_deadline']) in (int, float)
                        and received_at < request['ordinary_absolute_deadline'] <= received_at + ORDINARY_EXECUTION_SECONDS
                        and math.isfinite(request['ordinary_absolute_deadline'])):
                    # The producer fixed E at call entry. Derive that same
                    # call's Q rather than restarting queue time at the server.
                    admission_deadline = min(admission_deadline,
                        request['ordinary_absolute_deadline'] - ORDINARY_EXECUTION_SECONDS + QUEUE_SECONDS)
                with regular_fd_domain(deadline=effective_deadline, stop=self.stop,
                                       admission_deadline=admission_deadline):
                    deadline = effective_deadline
                    if (type(request) is not dict or set(request) not in ({'runtime', 'sequence', 'name', 'arguments'}, {'runtime', 'sequence', 'name', 'arguments', 'ordinary_absolute_deadline'}, {'runtime', 'sequence', 'name', 'arguments', 'group_absolute_deadline', 'group_loader_anchor'})
                            or request['runtime'] != self.runtime or type(request['sequence']) is not int
                            or request['sequence'] != 1 or type(request['name']) is not str
                            or type(request['arguments']) is not dict):
                        raise WCEError('CONNECTION_REQUEST_REJECTED')
                    if 'ordinary_absolute_deadline' in request:
                        selected = request['ordinary_absolute_deadline']
                        if (request['name'] not in NETWORK or type(selected) not in (int, float)
                                or not received_at < selected <= received_at + ORDINARY_EXECUTION_SECONDS
                                or not math.isfinite(selected)):
                            raise WCEError('CONNECTION_REQUEST_REJECTED')
                    from .own_base_domain import is_base_runtime, require_method
                    if is_base_runtime(self.runtime) and request['name'] != MAINTENANCE_METHOD:
                        # Before any Group/revision/restore dispatcher or claim.
                        try:
                            require_method(request['name'])
                        except WCEError as error:
                            self.guard()
                            send(stream, {'sequence': 1, 'error': error.code})
                            return
                    self.guard()
                    from .draft_group_tools import NETWORK as group_network, validate as validate_group
                    from .draft_group_host_bootstrap import PRIVATE_METHOD as group_bootstrap
                    group_request=request['name'] in group_network|{group_bootstrap}
                    if group_request:
                        if set(request)!={'runtime','sequence','name','arguments','group_absolute_deadline','group_loader_anchor'}:
                            raise WCEError('CONNECTION_REQUEST_REJECTED')
                        from .group_host_external_loader import check_process_loader_anchor
                        check_process_loader_anchor(request['group_loader_anchor'])
                        if request['name']==group_bootstrap:
                            if request['arguments']:
                                raise WCEError('GROUP_FIXED_BOOTSTRAP_ARGUMENTS')
                        else:
                            validate_group(request['name'],request['arguments'])
                            if request['arguments']['connection_id']!=self.policy.data['connection_id']:
                                raise WCEError('CONNECTION_SCOPE_MISMATCH')
                        selected=request['group_absolute_deadline']
                        if type(selected) not in (int,float) or not math.isfinite(selected) or not received_at<selected<=received_at+RECOVERY_SECONDS:
                            raise WCEError('GROUP_DEADLINE')
                        deadline=selected;client.settimeout(max(.001,deadline-time.monotonic()+10))
                    elif 'group_absolute_deadline' in request or 'group_loader_anchor' in request:
                        raise WCEError('CONNECTION_REQUEST_REJECTED')
                    from .own_replacement_executor import METHOD as REPLACEMENT_METHOD, validate as validate_replacement
                    if request['name'] == REPLACEMENT_METHOD:
                        validate_replacement(request['arguments'])
                        if request['arguments']['connection_id'] != self.policy.data['connection_id']:
                            raise WCEError('CONNECTION_SCOPE_MISMATCH')
                        deadline = effective_deadline
                        client.settimeout(RECOVERY_SECONDS + 15)
                    if request['name'] == RECOVERY_METHOD:
                        from .own_connection_tools import validate as validate_tool
                        validate_tool(request['name'], request['arguments'])
                        if request['arguments']['connection_id'] != self.policy.data['connection_id']:
                            raise WCEError('CONNECTION_SCOPE_MISMATCH')
                        deadline = effective_deadline
                        client.settimeout(RECOVERY_SECONDS + 15)
                    if request['name'] == LOCATOR_METHOD:
                        from .own_connection_tools import validate as validate_tool
                        validate_tool(request['name'], request['arguments'])
                        if request['arguments']['connection_id'] != self.policy.data['connection_id']:
                            raise WCEError('CONNECTION_SCOPE_MISMATCH')
                        deadline = received_at + LOCATOR_SECONDS
                        client.settimeout(LOCATOR_SECONDS + 10)
                    from . import draft_revision_tools
                    if request['name'] in draft_revision_tools.NETWORK:
                        draft_revision_tools.validate(request['name'],request['arguments'])
                        if request['arguments']['connection_id']!=self.policy.data['connection_id']:
                            raise WCEError('CONNECTION_SCOPE_MISMATCH')
                        deadline=received_at+RECOVERY_SECONDS
                        client.settimeout(RECOVERY_SECONDS+15)
                    try:
                        if request['name'] == MAINTENANCE_METHOD:
                            result = self.idle_drain(request['arguments'])
                            # An accepted drain deliberately set stop. Do not call
                            # guard again and turn its own ACK into STOPPED.
                        else:
                            if (request['name'] in DRAFT_MANAGEMENT_NETWORK
                                    or request['name'] in {'own.drafts.inventory','own.publications.slots.discover'}
                                    or request['name'].startswith('own.publications.current.')):
                                result = self.service.call(request['name'], request['arguments'], deadline,
                                    cancel_guard=_ClientCancellationGuard(client),
                                    admission_deadline=admission_deadline)
                            elif request['name'] == LOCATOR_METHOD or request['name'] in draft_revision_tools.NETWORK or group_request or is_base_runtime(self.runtime):
                                result = self.service.call(request['name'], request['arguments'], deadline,
                                    cancel_guard=_ClientCancellationGuard(client))
                            elif admission_deadline is not None:
                                result = self.service.call(request['name'], request['arguments'], deadline,
                                    admission_deadline=admission_deadline)
                            else:
                                result = self.service.call(request['name'], request['arguments'], deadline)
                            self.guard()
                            if group_request:
                                check_process_loader_anchor(request['group_loader_anchor'])
                            if request['name'] == 'own.connections.status':
                                result = result | {_SOFTWARE_FIELD: self.software_id}
                        response = {'sequence': 1, 'result': result}
                    except WCEError as error:
                        from .document_errors import location
                        response = {'sequence': 1, 'error': error.code}
                        if location(error): response['location'] = location(error)
                    except Exception as error:
                        self.note_unexpected_error(error)
                        response = {'sequence': 1, 'error': 'CONNECTION_RESULT_UNDETERMINED'}
                send(stream, response)
        except (OSError, EOFError, WCEError):
            pass
        finally:
            client.close()
            self.last_call = time.monotonic()
            with self.workers_lock: self.workers.discard(threading.current_thread())
            self.slots.release()



def _startup_remaining(deadline):
    remaining = deadline - time.monotonic()
    if remaining <= 0:
        raise WCEError('CONNECTION_START_PENDING')
    return remaining


class _StartupStream:
    """Only the startup status handshake: one deadline across fragmented frames."""
    def __init__(self, client, deadline):
        self.client, self.deadline = client, deadline
        self.buffer = bytearray()

    def readline(self, maximum):
        while True:
            _startup_remaining(self.deadline)
            end = self.buffer.find(b'\n', 0, maximum)
            if end >= 0 or len(self.buffer) >= maximum:
                size = end + 1 if end >= 0 else maximum
                value = bytes(self.buffer[:size]); del self.buffer[:size]
                return value
            self.client.settimeout(_startup_remaining(self.deadline))
            try:
                data = self.client.recv(min(4096, maximum - len(self.buffer)))
            except socket.timeout:
                raise WCEError('CONNECTION_START_PENDING') from None
            _startup_remaining(self.deadline)
            if not data:
                value = bytes(self.buffer); self.buffer.clear()
                return value
            self.buffer.extend(data)

    def write(self, data):
        self.client.settimeout(_startup_remaining(self.deadline))
        try:
            self.client.sendall(data)
        except socket.timeout:
            raise WCEError('CONNECTION_START_PENDING') from None
        _startup_remaining(self.deadline)
        return len(data)

    def flush(self):
        _startup_remaining(self.deadline)



@contextmanager
def _ready_transport(policy, runtime, pin, endpoint_pin, absolute_deadline, *, startup=False, absolute_stream=False):
    """Queue only before dispatch on an authenticated negative busy handshake.

    Same runtime/PID/socket/policy are rechecked on every new connection. Any
    other error, and every error after yielding, propagates without reconnect.
    """
    def remaining():
        value=absolute_deadline-time.monotonic()
        if value<=0:
            raise WCEError('CONNECTION_START_PENDING' if startup else 'CONNECTION_QUEUE_EXPIRED')
        return value
    endpoint=policy.root/SOCKET
    while True:
        remaining()
        current,current_pin=read_runtime(policy)
        if current!=runtime or current_pin!=pin or socket_pin(endpoint)!=endpoint_pin:
            raise WCEError('CONNECTION_RUNTIME_CHANGED')
        policy.check();remaining()
        with socket.socket(socket.AF_UNIX) as client:
            client.settimeout(remaining())
            try:client.connect(socket_address(endpoint))
            except socket.timeout:
                if startup:raise WCEError('CONNECTION_START_PENDING') from None
                raise
            remaining()
            if peer(client)!=(runtime['pid'],os.getuid()):raise WCEError('CONNECTION_PEER_REJECTED')
            stream_context=(nullcontext(_StartupStream(client,absolute_deadline))
                            if startup or absolute_stream else client.makefile('rwb'))
            with stream_context as stream:
                try:value=receive(stream)
                except WCEError as error:
                    if not startup and error.code=='CONNECTION_START_PENDING':
                        raise WCEError('CONNECTION_QUEUE_EXPIRED') from None
                    raise
                remaining()
                if path_check(policy.root/RUNTIME)!=pin or socket_pin(endpoint)!=endpoint_pin:
                    raise WCEError('CONNECTION_RUNTIME_CHANGED')
                policy.check()
                busy=(type(value) is dict and set(value)=={'state','runtime'}
                      and value['state']==_BUSY_HANDSHAKE and value['runtime']==runtime)
                if not busy:
                    if value!=runtime:raise WCEError('CONNECTION_RUNTIME_CHANGED')
                    remaining()
                    if not startup and not absolute_stream:client.settimeout(75)
                    yield client,stream
                    return
        # The server read no request. Close first, retain the same deadline.
        time.sleep(min(.05,remaining()))


class _ExecutionResponseStream(_StartupStream):
    """One absolute post-dispatch receive bound; never a reconnect signal."""
    def readline(self, maximum):
        try:
            return super().readline(maximum)
        except WCEError as error:
            if error.code == 'CONNECTION_START_PENDING':
                raise WCEError('CONNECTION_RESULT_UNDETERMINED') from None
            raise


def call(policy, name, arguments, *, startup_deadline=None):
    ordinary_deadline = time.monotonic() + ORDINARY_EXECUTION_SECONDS if name in NETWORK else None
    startup = startup_deadline is not None
    if startup:
        if (name != 'own.connections.status'
                or arguments != {'connection_id': policy.data['connection_id']}
                or type(startup_deadline) not in (int, float) or not math.isfinite(startup_deadline)):
            raise WCEError('CONNECTION_INVALID_ARGUMENTS')
        _startup_remaining(startup_deadline)
    from .own_replacement_executor import METHOD as REPLACEMENT_METHOD, validate as validate_replacement
    if name == REPLACEMENT_METHOD:
        validate_replacement(arguments)
        if arguments['connection_id'] != policy.data['connection_id']:
            raise WCEError('CONNECTION_SCOPE_MISMATCH')
    if name == RECOVERY_METHOD:
        from .own_connection_tools import validate as validate_tool
        validate_tool(name, arguments)
        if arguments['connection_id'] != policy.data['connection_id']:
            raise WCEError('CONNECTION_SCOPE_MISMATCH')
    if name == LOCATOR_METHOD:
        from .own_connection_tools import validate as validate_tool
        validate_tool(name, arguments)
        if arguments['connection_id'] != policy.data['connection_id']:
            raise WCEError('CONNECTION_SCOPE_MISMATCH')
    from . import draft_revision_tools
    if name in draft_revision_tools.NETWORK:
        draft_revision_tools.validate(name,arguments)
        if arguments['connection_id']!=policy.data['connection_id']:
            raise WCEError('CONNECTION_SCOPE_MISMATCH')
    runtime, pin = read_runtime(policy)
    from .own_base_domain import is_base_runtime, require_method
    if is_base_runtime(runtime):
        require_method(name)
    endpoint = policy.root / SOCKET
    endpoint_pin = socket_pin(endpoint)
    queue_deadline=startup_deadline if startup else time.monotonic()+QUEUE_SECONDS
    if ordinary_deadline is not None:
        queue_deadline = min(queue_deadline,
            ordinary_deadline - ORDINARY_EXECUTION_SECONDS + QUEUE_SECONDS)
    with _ready_transport(policy,runtime,pin,endpoint_pin,queue_deadline,startup=startup,
                          absolute_stream=ordinary_deadline is not None) as (client,stream):
        if path_check(policy.root / RUNTIME) != pin or socket_pin(endpoint) != endpoint_pin:
            raise WCEError('CONNECTION_RUNTIME_CHANGED')
        policy.check()
        if time.monotonic()>=queue_deadline:
            raise WCEError('CONNECTION_START_PENDING' if startup else 'CONNECTION_QUEUE_EXPIRED')
        request = {'runtime': runtime, 'sequence': 1, 'name': name, 'arguments': arguments}
        if ordinary_deadline is not None:
            request['ordinary_absolute_deadline'] = ordinary_deadline
        send(stream, request)
        if name in {RECOVERY_METHOD, REPLACEMENT_METHOD}:
            client.settimeout(RECOVERY_SECONDS + 15)
        if name == LOCATOR_METHOD:
            client.settimeout(LOCATOR_SECONDS + 10)
        if name in draft_revision_tools.NETWORK:
            client.settimeout(RECOVERY_SECONDS+15)
        response = receive(_ExecutionResponseStream(client, ordinary_deadline + 15)
                           if ordinary_deadline is not None else stream)
        policy.check()
        # This authenticated original stream may carry a negative stop ACK
        # while the owner finishes removing its pinned endpoints. It grants
        # no result or retry; all successful results retain fresh pin checks.
        if (type(response) is dict and set(response) == {'sequence', 'error'}
                and type(response['sequence']) is int and response['sequence'] == 1
                and response['error'] == 'CONNECTION_STOPPED'):
            raise WCEError('CONNECTION_STOPPED')
        current_runtime, current_pin = read_runtime(policy)
        if current_runtime != runtime or current_pin != pin or socket_pin(endpoint) != endpoint_pin:
            raise WCEError('CONNECTION_RUNTIME_CHANGED')
        if (type(response) is not dict or type(response.get('sequence')) is not int or response['sequence'] != 1
                or set(response) not in ({'sequence', 'error'}, {'sequence', 'error', 'location'}, {'sequence', 'result'})):
            raise WCEError('CONNECTION_RESULT_UNDETERMINED')
        if 'error' in response:
            if type(response['error']) is not str or re.fullmatch('[A-Z][A-Z0-9_]{0,95}', response['error']) is None:
                raise WCEError('CONNECTION_RESULT_UNDETERMINED')
            from .document_errors import restore
            raise restore(response['error'], response.get('location', {}))
        if type(response['result']) is not dict:
            raise WCEError('CONNECTION_RESULT_UNDETERMINED')
        if startup: _startup_remaining(startup_deadline)
        result = response['result']
        if name == 'own.connections.status' and not startup:
            result = {key: value for key, value in result.items() if key != _SOFTWARE_FIELD}
        return result


@contextmanager
def _startup_gate(policy, deadline):
    # Queueing belongs to the same startup budget, never a second wait window.
    with ExitStack() as stack:
        while True:
            _startup_remaining(deadline); policy.check(); _startup_remaining(deadline)
            try:
                stack.enter_context(locked(policy.root / 'connection-start.lock', nonblocking=True))
                break
            except WCEError as error:
                if error.code != 'CONNECTION_BUSY': raise
                time.sleep(min(.05, _startup_remaining(deadline)))
        yield


def _startup_has_owner(policy):
    # Probe the existing lifetime lock without creating or changing it.
    try:
        with locked(policy.root / 'connection.lock', nonblocking=True,
                    shared=True, existing=True, readonly=True):
            return False
    except FileNotFoundError:
        return False
    except WCEError as error:
        if error.code == 'CONNECTION_BUSY': return True
        raise


def _replace_idle_software_owner(policy, deadline):
    """No business has been sent. Reuse the exact existing idle-drain RPC."""
    runtime, pin = read_runtime(policy)
    endpoint = policy.root / SOCKET
    endpoint_pin = socket_pin(endpoint)
    while True:
        remaining = _startup_remaining(deadline)
        result = request_idle_drain(policy, runtime, pin, endpoint_pin,
            reviewed_scope=policy.value['candidate_scope'], timeout=min(3, remaining),
            absolute_deadline=deadline)
        if result == {'state': 'DRAIN_ACCEPTED'}:
            break
        if result != {'state': 'MAINTENANCE_BUSY'}:
            raise WCEError('MAINTENANCE_RESULT_UNKNOWN')
        # BUSY is a definite negative acknowledgment, never an uncertain drain.
        time.sleep(min(.05, _startup_remaining(deadline)))
    while True:
        _startup_remaining(deadline); policy.check()
        if os.path.lexists(policy.root / RUNTIME):
            try:
                current = read_runtime(policy)
            except (OSError, WCEError) as error:
                if (os.path.lexists(policy.root / RUNTIME)
                        or not (isinstance(error, FileNotFoundError)
                            or isinstance(error, WCEError) and error.code in
                               {'BOOTSTRAP_UNSAFE_PATH', 'BOOTSTRAP_PATH_CHANGED'})):
                    raise
                current = None  # Our acknowledged owner finished cleanup here.
            if current is not None and current != (runtime, pin):
                raise WCEError('MAINTENANCE_RUNTIME_CHANGED')
        if os.path.lexists(endpoint):
            try:
                current_socket = socket_pin(endpoint)
            except (OSError, WCEError) as error:
                if (os.path.lexists(endpoint)
                        or not (isinstance(error, FileNotFoundError)
                            or isinstance(error, WCEError)
                               and error.code == 'BOOTSTRAP_ENDPOINT_UNAVAILABLE')):
                    raise
                current_socket = None
            if current_socket is not None and current_socket != endpoint_pin:
                raise WCEError('MAINTENANCE_RUNTIME_CHANGED')
        if (not _startup_has_owner(policy)
                and not any(os.path.lexists(policy.root / p) for p in (SOCKET, RUNTIME))):
            return
        time.sleep(min(.05, _startup_remaining(deadline)))


def ensure_started(policy, launcher):
    deadline = time.monotonic() + STARTUP_SECONDS
    with _startup_gate(policy, deadline):
        policy.check(); _startup_remaining(deadline)
        launcher = Path(launcher).resolve(strict=True)
        expected_software = software_identity(launcher.parent.parent)
        stale_runtime_pin = None
        wait_existing = False
        if any(os.path.lexists(policy.root / p) for p in (SOCKET, RUNTIME)):
            try:
                ready = call(policy, 'own.connections.status', {'connection_id': policy.data['connection_id']},
                     startup_deadline=deadline)
            except (ConnectionRefusedError, FileNotFoundError):
                wait_existing = _startup_has_owner(policy)
                if wait_existing:
                    # A partially published exact current runtime may still be
                    # entering listen(). A different scope is never joined.
                    if os.path.lexists(policy.root / RUNTIME): read_runtime(policy)
                else:
                    stale_runtime_pin, _ = stale_endpoint(policy)
            except WCEError as error:
                if error.code == 'CONNECTION_START_PENDING': raise
                stale_runtime_pin, _ = stale_endpoint(policy)
            else:
                if ready.get(_SOFTWARE_FIELD) == expected_software:
                    return
                _replace_idle_software_owner(policy, deadline)
        else:
            wait_existing = _startup_has_owner(policy)
        _startup_remaining(deadline)
        def start_current():
            policy.check(); _startup_remaining(deadline)
            return subprocess.Popen([sys.executable, '-I', '-B', str(launcher), 'broker',
                '--policy', str(policy.path)], cwd=launcher.parent.parent,
                stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                start_new_session=True, env={'PATH': '/usr/bin:/bin:/usr/sbin:/sbin', 'HOME': str(Path.home())})
        process = None
        if not wait_existing:
            # At most one spawn for this call. Timeout never kills/restarts it.
            process = start_current()
        while True:
            _startup_remaining(deadline); policy.check(); _startup_remaining(deadline)
            if process is not None and process.poll() is not None:
                raise WCEError('CONNECTION_START_FAILED')
            if os.path.lexists(policy.root / RUNTIME) and os.path.lexists(policy.root / SOCKET):
                try:
                    ready = call(policy, 'own.connections.status', {'connection_id': policy.data['connection_id']},
                         startup_deadline=deadline)
                    if ready.get(_SOFTWARE_FIELD) != expected_software:
                        if process is not None:
                            raise WCEError('CONNECTION_SOFTWARE_CHANGED')
                        # A preexisting owner may have been starting without
                        # endpoints at entry. Replace it within this same gate.
                        _replace_idle_software_owner(policy, deadline)
                        wait_existing = False
                        process = start_current()
                        continue
                    return
                except (ConnectionRefusedError, FileNotFoundError): pass
                except WCEError as error:
                    if error.code == 'CONNECTION_START_PENDING': raise
                    # Only the exact dead instance accepted before this one
                    # spawn may be replaced by that child. New mismatches fail.
                    if os.path.lexists(policy.root / RUNTIME):
                        if stale_runtime_pin is None or path_check(policy.root / RUNTIME) != stale_runtime_pin:
                            raise
            if wait_existing and not _startup_has_owner(policy):
                # Do not turn an unknown owner's exit into another launch.
                raise WCEError('CONNECTION_START_FAILED')
            time.sleep(min(.05, _startup_remaining(deadline)))


def request_idle_drain(policy, expected_runtime, expected_runtime_pin, expected_socket_pin,
                       *, reviewed_scope, timeout=3, absolute_deadline=None):
    """Trusted installer only; never starts a broker, renews tokens or retries.

    Installer validates the reviewed package scope before invoking this helper.
    A matching old016 runtime is still unsupported; do not probe it. An ACK
    proves stop was accepted, not that cleanup/lifetime-lock release completed.
    """
    dispatched = False
    try:
        if (type(reviewed_scope) is not str or re.fullmatch('[a-f0-9]{64}', reviewed_scope) is None
                or type(expected_runtime) is not dict
                or expected_runtime.get('candidate_scope') != reviewed_scope
                or type(timeout) not in (int, float) or not 0 < timeout <= 3):
            raise WCEError('MAINTENANCE_UNSUPPORTED_OR_INVALID')
        now = time.monotonic()
        if absolute_deadline is not None and (type(absolute_deadline) not in (int, float)
                or not math.isfinite(absolute_deadline) or absolute_deadline <= now):
            raise WCEError('MAINTENANCE_UNSUPPORTED_OR_INVALID')
        deadline = min(now + timeout, absolute_deadline) if absolute_deadline is not None else now + timeout
        _startup_remaining(deadline)
        runtime, pin = read_runtime(policy)
        endpoint = policy.root / SOCKET
        if (runtime != expected_runtime or pin != expected_runtime_pin
                or socket_pin(endpoint) != expected_socket_pin):
            raise WCEError('MAINTENANCE_RUNTIME_CHANGED')
        with socket.socket(socket.AF_UNIX) as client:
            client.settimeout(_startup_remaining(deadline))
            client.connect(socket_address(endpoint))
            if peer(client) != (runtime['pid'], os.getuid()):
                raise WCEError('CONNECTION_PEER_REJECTED')
            with nullcontext(_StartupStream(client, deadline)) as stream:
                greeting=receive(stream)
                busy=(type(greeting) is dict and set(greeting)=={'state','runtime'}
                      and greeting['state']==_BUSY_HANDSHAKE and greeting['runtime']==runtime)
                if busy:
                    if (read_runtime(policy)!=(runtime,pin) or socket_pin(endpoint)!=expected_socket_pin):
                        raise WCEError('MAINTENANCE_RUNTIME_CHANGED')
                    policy.check()
                    _startup_remaining(deadline)
                    return {'state':'MAINTENANCE_BUSY'}
                if greeting != runtime:
                    raise WCEError('MAINTENANCE_RUNTIME_CHANGED')
                if (path_check(policy.root / RUNTIME) != pin
                        or socket_pin(endpoint) != expected_socket_pin):
                    raise WCEError('MAINTENANCE_RUNTIME_CHANGED')
                policy.check()
                # Set before send: even a partial write may reach the broker.
                dispatched = True
                send(stream, {'runtime': runtime, 'sequence': 1, 'name': MAINTENANCE_METHOD,
                    'arguments': {'connection_id': policy.data['connection_id'],
                                  'instance': runtime['instance']}})
                response = receive(stream)
                if response not in ({'sequence': 1, 'result': {'state': 'DRAIN_ACCEPTED'}},
                                    {'sequence': 1, 'result': {'state': 'MAINTENANCE_BUSY'}}):
                    raise WCEError('MAINTENANCE_RESULT_UNKNOWN')
                # bool compares equal to 1 in Python; sequence must be strict.
                if type(response['sequence']) is not int:
                    raise WCEError('MAINTENANCE_RESULT_UNKNOWN')
                result = response['result']
                if result['state'] == 'MAINTENANCE_BUSY':
                    latest, latest_pin = read_runtime(policy)
                    if (latest != runtime or latest_pin != pin
                            or socket_pin(endpoint) != expected_socket_pin):
                        raise WCEError('MAINTENANCE_RUNTIME_CHANGED')
                # On ACCEPTED, finally may already have removed the endpoint.
                # Do not misclassify that expected cleanup as a failed ACK.
                _startup_remaining(deadline)
                return result
    except (OSError, EOFError):
        # The one drain may have been accepted; no reconnect/replay is allowed.
        raise WCEError('MAINTENANCE_RESULT_UNKNOWN') from None
    except WCEError:
        if dispatched:
            # Includes strict decoder/pin failures after the one request. No
            # downstream caller may mistake these for a never-sent request.
            raise WCEError('MAINTENANCE_RESULT_UNKNOWN') from None
        raise


# Fixed implementation identities for this narrow route. These are integrity
# checks within ordinary same-UID Python, never a malicious-code OS boundary.
from .draft_revision_gate import RevisionExecutionGate as _REV_GATE, _ACTIVE as _REV_ACTIVE, guard_current as _REV_CANCEL_CURRENT
_REV_SERVICE, _REV_BROKER, _REV_POLICY, _REV_WORKFLOW = AccountService, Broker, ConnectionPolicy, PersistentWorkflow
_REV_ACCOUNT_GUARD, _REV_BROKER_GUARD, _REV_POLICY_CHECK = AccountService.guard, Broker.guard, ConnectionPolicy.check
_REV_BROKER_LEAF = Broker._guard_revision
_REV_READ_RUNTIME, _REV_RUNTIME_CODE = read_runtime, read_runtime.__code__
_REV_PRIVATE_READ, _REV_DECODE, _REV_SOCKET_PIN = private_read, decode, socket_pin
_REV_DIGEST, _REV_CANONICAL = digest, canonical
_REV_CLIENT_GUARD, _REV_SOCKET_TYPE = locator_client_guard, socket.socket
_REV_CANCEL_TYPE, _REV_CANCEL_CALL = _ClientCancellationGuard, _ClientCancellationGuard.__call__
_REV_SNAPSHOT = _RevisionGuardSnapshot
_REV_CAPTURE, _REV_ASSERT, _REV_HELPERS = _revision_guard_snapshot, _revision_assert_snapshot, _revision_helpers_original

from .publication_lock import _writer_guard as _REV_WRITER_FACTORY
_REV_HOLD, _REV_METHOD_TYPE = _revision_hold, MethodType
_REV_LOCK_TYPE, _REV_STOP_TYPE, _REV_STOP_METHOD = type(threading.Lock()), threading.Event, threading.Event.is_set


from .draft_group_history_context import history_transaction as _history_transaction


from .draft_group_history_context import locator_scope as _history_scope
