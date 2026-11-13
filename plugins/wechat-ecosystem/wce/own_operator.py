"""TTY-owned runtime: human authority and memory lease never enter MCP."""
from dataclasses import replace
import json
import math
import os
from pathlib import Path
import re
import secrets
import socket
import sys
import threading
import time

from .bounded_file import identity
from .contracts import WCEError
from .http_transport import HTTPSender
from .own_auth import (APIS, READ_APIS, DRAFT_READ_APIS, OwnerEvidence, OwnProfile, OwnRegistry, OwnTokenLease,
                      OwnTokenScope, ScopedOwnTokenBroker)
from .own_bootstrap_security import (FLAGS, NEWS_SOURCE, TOKEN_SOURCE, Terminal,
                                     TokenIPDenied, acquire, acquire_pending, path_check, load_config)
from .own_bootstrap_ipc import config_digest, peer, receive, send, socket_pin
from .own_contracts import validate
from .own_stdio import OwnRouter
from .own_workflow import OwnWorkflow
from .prepared_host import ScopedImageDirectory
from .service import digest

HUMAN_KINDS = frozenset(APIS) | {'qualification', 'egress', 'quota'}


class Operator:
    def __init__(self, config, acquisition_sender=None, wire_sender=None,
                 source_kind='OPERATOR_ATTESTED', clock=time.time):
        if source_kind not in {'OPERATOR_ATTESTED', 'SYNTHETIC_SETUP'}:
            raise WCEError('BOOTSTRAP_SOURCE_INVALID')
        if source_kind == 'OPERATOR_ATTESTED' and (acquisition_sender is not None or wire_sender is not None):
            raise WCEError('BOOTSTRAP_SENDER_INVALID')
        if source_kind == 'SYNTHETIC_SETUP' and any(
                s is None or type(s) is HTTPSender or getattr(s, 'mode', None) != 'SYNTHETIC_OWN_WIRE'
                for s in (acquisition_sender, wire_sender)):
            raise WCEError('BOOTSTRAP_SENDER_INVALID')
        self.config, self.clock, self.source_kind = config, clock, source_kind
        self.credential_store = None
        self.keychain_state = 'UNUSED'
        self.run_phase, self.run_failure, self.reconcile_diagnostics = 'START', None, {}
        self.diagnostic_id = secrets.token_hex(16)
        self.actor, self.connection = config.actor, config.data['connection_id']
        d = config.data
        self.registry = OwnRegistry()
        self.lease, self.mono_expiry, self.alive = None, 0, True
        self.acquisition_sender = acquisition_sender
        self.profile = OwnProfile(self.actor, self.connection, d['appid'], d['resource_id'],
            d['generation'], d['epoch'], secrets.randbits(62), d['expires_at'], d['expires_at'],
            d['expires_at'], d['expires_at'], 'memory-' + secrets.token_hex(16), source_kind,
            frozenset({'local.read', 'local.write'}), ())
        self._publish(self.profile)
        broker = ScopedOwnTokenBroker(lambda scope: self.lease, self.current, clock)
        directory = ScopedImageDirectory(config.root / 'images', self.actor, self.connection, d['resource_id'])
        self.workflow = OwnWorkflow(config.root / 'state.sqlite3', self.registry, broker,
            wire_sender if source_kind == 'SYNTHETIC_SETUP' else HTTPSender(enabled=True), directory, clock)
        self.db_pin = identity((config.root / 'state.sqlite3').lstat())
        self.router = OwnRouter(self.actor, self.workflow)
        self.info = {'schema': 1, 'session': secrets.token_hex(32), 'nonce': secrets.token_hex(32),
                     'actor_digest': digest(vars(self.actor)), 'account': d['appid'], 'pid': os.getpid(),
                     'config_digest': config_digest(config)}
        self.socket_path, self.info_path = config.root / 'operator.sock', config.root / 'runtime.json'
        self.listener, self.endpoint_pin, self.info_pin = None, None, None
        self.clients, self.workers, self.client_lock = set(), [], threading.Lock()
        self.slots = threading.BoundedSemaphore(8)
        self.accept_worker = None
        self.guided_context = None
        self.pending_token = None
        self.local_adoption_context = None

    def _publish(self, profile):
        self.profile = profile
        self.registry.profiles[(self.actor, self.connection)] = profile

    def paths_current(self):
        self.config.check(self.clock())
        if identity((self.config.root / 'state.sqlite3').lstat()) != self.db_pin:
            raise WCEError('BOOTSTRAP_PATH_CHANGED')
        if self.endpoint_pin is not None and socket_pin(self.socket_path) != self.endpoint_pin:
            raise WCEError('BOOTSTRAP_ENDPOINT_CHANGED')
        if self.info_pin is not None and path_check(self.info_path) != self.info_pin:
            raise WCEError('BOOTSTRAP_RUNTIME_CHANGED')

    def current(self, scope, lease):
        self.paths_current()  # Called by every workflow internal send/final authority guard.
        return (self.alive and lease is self.lease and scope == OwnTokenScope.from_profile(self.profile)
                and lease.expires_at > self.clock() and time.monotonic() < self.mono_expiry)

    def start(self, accept_clients=True):
        self.config.check(self.clock())
        if os.path.lexists(self.socket_path) or os.path.lexists(self.info_path):
            raise WCEError('BOOTSTRAP_ENDPOINT_EXISTS')
        try:
            fd = os.open(self.info_path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
            with os.fdopen(fd, 'wb') as stream:
                stream.write(json.dumps(self.info, separators=(',', ':')).encode())
                stream.flush()
                os.fsync(stream.fileno())
            self.info_pin = path_check(self.info_path)
            self.listener = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
            self.listener.bind(str(self.socket_path))
            os.chmod(self.socket_path, 0o600)
            self.endpoint_pin = socket_pin(self.socket_path)
            self.listener.listen(8)
            self.listener.settimeout(0.5)
            if accept_clients:
                self._serve_clients()
        except Exception:
            error = WCEError('BOOTSTRAP_ENDPOINT_UNAVAILABLE')
            self._failure(error)
            try:
                self.close()
            except BaseException:
                pass
            raise error from None

    def _serve_clients(self):
        if not self.alive or self.accept_worker is not None or self.listener is None:
            raise WCEError('BOOTSTRAP_ENDPOINT_UNAVAILABLE')
        self.accept_worker = threading.Thread(target=self._accept, daemon=True)
        self.accept_worker.start()

    def _accept(self):
        while self.alive:
            try:
                client, _ = self.listener.accept()
            except socket.timeout:
                continue
            except OSError:
                return
            if not self.alive:
                client.close()
                return
            if not self.slots.acquire(blocking=False):
                client.close()
                continue
            with self.client_lock:
                self.clients.add(client)
            worker = threading.Thread(target=self._client, args=(client,), daemon=True)
            self.workers = [w for w in self.workers if w.is_alive()] + [worker]
            worker.start()

    def _client(self, client):
        try:
            pid, uid = peer(client)
            if uid != os.getuid() or pid < 1:
                raise WCEError('BOOTSTRAP_PEER_DENIED')
            client.settimeout(20)
            with client.makefile('rwb') as stream:
                seq = 0
                while self.alive:
                    frame = receive(stream)
                    self.paths_current()
                    expected = {'schema', 'session', 'nonce', 'actor_digest', 'account', 'seq', 'name', 'arguments', 'config_digest'}
                    if (type(frame) is not dict or set(frame) != expected
                            or type(frame['schema']) is not int or frame['schema'] != 1
                            or any(frame[k] != self.info[k] for k in ('session', 'nonce', 'actor_digest', 'account', 'config_digest'))
                            or type(frame['seq']) is not int or frame['seq'] != seq + 1):
                        raise WCEError('BOOTSTRAP_IPC_DENIED')
                    seq += 1
                    try:
                        validate(frame['name'], frame['arguments'])
                        if self.lease is not None and self._contains(frame['arguments'], self.lease.token.reveal_for_adapter()):
                            raise WCEError('BOOTSTRAP_SECRET_INPUT_DENIED')
                        value = self.router.call(frame['name'], frame['arguments'])
                        self.paths_current()
                        if not self.alive:
                            raise WCEError('BOOTSTRAP_STOPPED')
                        if self.lease is not None and self._contains(value, self.lease.token.reveal_for_adapter()):
                            raise WCEError('BOOTSTRAP_SECRET_OUTPUT_DENIED')
                        reply = {'ok': True, 'value': value}
                    except WCEError as error:
                        reply = {'ok': False, 'error': error.code}
                    send(stream, reply)
        except BaseException:
            # Do not reveal transport exception chains, frame data or nonce.
            pass
        finally:
            with self.client_lock:
                self.clients.discard(client)
            client.close()
            self.slots.release()

    @staticmethod
    def _contains(value, secret):
        if type(value) is str:
            return secret in value
        if type(value) is dict:
            return any(Operator._contains(k, secret) or Operator._contains(v, secret) for k, v in value.items())
        if type(value) in (list, tuple):
            return any(Operator._contains(v, secret) for v in value)
        return False

    def challenge(self, terminal, verb):
        code = secrets.token_hex(16)
        answer = terminal.ask('CHALLENGE ' + code)
        if answer != verb + ' ' + code:
            raise WCEError('BOOTSTRAP_CONFIRMATION_DENIED')

    def attest(self, terminal, kind):
        if kind not in HUMAN_KINDS:
            raise WCEError('BOOTSTRAP_EVIDENCE_INVALID')
        terminal.display({'kind': kind, 'binding': self.profile.binding(), 'state': 'UNKNOWN'})
        proof = terminal.ask('SOURCE_SHA256')
        seconds = terminal.ask('EVIDENCE_TTL_SECONDS')
        if re.fullmatch('[a-f0-9]{64}', proof) is None or re.fullmatch('[0-9]{1,5}', seconds) is None:
            raise WCEError('BOOTSTRAP_EVIDENCE_INVALID')
        ttl = int(seconds)
        if not 0 < ttl <= 3600:
            raise WCEError('BOOTSTRAP_EVIDENCE_INVALID')
        self.challenge(terminal, 'confirm')
        self.paths_current()
        p = self.profile
        evidence = OwnerEvidence(kind, p.account_id, p.resource_id, p.generation,
            min(self.clock() + ttl, self.config.data['expires_at']), 'AVAILABLE', proof, self.source_kind)
        proofs = tuple(e for e in p.evidence_tuple if e.kind != kind) + (evidence,)
        grants = p.granted_actions | (frozenset({kind}) if kind in APIS else frozenset())
        self._publish(replace(p, evidence_tuple=proofs, granted_actions=grants))
        if self.lease is not None:
            deadline = min(self.lease.expires_at, evidence.expires)
            self.mono_expiry = min(self.mono_expiry, time.monotonic() + max(0, deadline - self.clock()))
            self.lease = replace(self.lease, expires_at=deadline)
            self._publish(replace(self.profile, credential_expires=deadline, session_expires=deadline))
        terminal.write('TRUSTED EVIDENCE_REGISTERED')

    def obtain(self, terminal, review_inputs=None):
        token, expires, mono = self._prepare_token(terminal, review_inputs)
        self._activate_token(terminal, token, expires, mono)

    def _prepare_token(self, terminal, review_inputs=None, pending=False):
        self.paths_current()
        # A human-requested new acquisition invalidates the old lease before
        # sending. A failed acquisition must never act as an old-token fallback.
        self.lease, self.mono_expiry, self.pending_token = None, 0, None
        terminal.display({'account': self.profile.account_id, 'resource': self.profile.resource_id,
                          'binding': self.profile.binding(), 'ordinary_mode': True})
        self.run_phase = 'CREDENTIAL'
        saved = self.credential_store.load() if self.credential_store is not None else None
        if saved is None:
            secret = terminal.ask('APPSECRET_HIDDEN', hidden=True)
        else:
            self.keychain_state = 'LOADED'
            terminal.write('TRUSTED KEYCHAIN_CREDENTIAL_LOADED')
            secret = saved.reveal_for_adapter()
        try:
            if review_inputs is not None and self._contains(review_inputs, secret):
                raise WCEError('BOOTSTRAP_SECRET_INPUT_DENIED')
            acquisition = acquire_pending if pending else acquire
            token, expires, mono = acquisition(self.profile.account_id, secret, self.acquisition_sender, self.clock)
            if review_inputs is not None and self._contains(review_inputs, token.reveal_for_adapter()):
                raise WCEError('BOOTSTRAP_SECRET_OUTPUT_DENIED')
            if self.credential_store is not None and saved is None:
                # Persist only after this same value obtained a valid ordinary
                # token and passed the existing reflection checks.
                self.credential_store.store(secret)
                self.keychain_state = 'STORED'
                terminal.write('TRUSTED KEYCHAIN_CREDENTIAL_STORED')
        except TokenIPDenied as error:
            if error.observed_ip is not None:
                terminal.display({'wechat_reported_ip': error.observed_ip,
                                  'source': 'stable_token_40164'})
            else:
                terminal.write('TRUSTED IP_DETAIL_UNAVAILABLE')
            raise
        finally:
            secret, saved = None, None
        self.paths_current()
        return token, expires, mono

    def _activate_token(self, terminal, token, expires, mono):
        self.paths_current()
        now, p = self.clock(), self.profile
        # Protocol proofs are minted by this new acquisition. An expired prior
        # protocol proof must not permanently block a fresh human-requested lease.
        existing = [e.expires for e in p.evidence_tuple if e.kind in HUMAN_KINDS and e.state == 'AVAILABLE']
        deadline = min([now + 300, expires, self.config.data['expires_at']] + existing)
        if not self.alive or deadline <= now or time.monotonic() >= mono:
            raise WCEError('BOOTSTRAP_TOKEN_EXPIRED')
        protocols = tuple(OwnerEvidence(k, p.account_id, p.resource_id, p.generation, deadline,
            'AVAILABLE', source, self.source_kind) for k, source in (
                ('token_route', TOKEN_SOURCE), ('news_schema_resolution', NEWS_SOURCE)))
        proofs = tuple(e for e in p.evidence_tuple if e.kind in HUMAN_KINDS) + protocols
        p = replace(p, token_revision=secrets.randbits(62), credential_handle='memory-' + secrets.token_hex(16),
                    credential_expires=deadline, session_expires=deadline, evidence_tuple=proofs)
        self._publish(p)
        self.lease = OwnTokenLease(OwnTokenScope.from_profile(p), token, deadline)
        start = time.monotonic()
        duration = min(300, deadline - now)
        end = start + duration
        # Floating addition can round upward across a binary exponent boundary.
        # Keep the represented remaining lifetime within the original cap.
        if end - start > duration:
            end = math.nextafter(end, -math.inf)
        self.mono_expiry = min(mono, end)
        terminal.write('TRUSTED LEASE_ACQUIRED')

    def guided_adoption(self, terminal, review, snapshot, policy, *, original,
                        review_started, review_monotonic, source_deadline):
        """Pure local observation adoption. No credential access or API call.

        This path does not create a memory lease, platform grants or IPC. Any
        later draft write must go through a separate normal current review.
        """
        from .own_body_recovery import code_scope
        # Keep the entry clock pair. Slow snapshots or wall-clock rollback
        # cannot rebase the original source/config/profile deadline.
        deadline = min(review_started + 300, source_deadline)
        mono = review_monotonic + (deadline - review_started)

        def current():
            if (not self.alive or self.profile != original or self.lease is not None
                    or self.pending_token is not None or self.clock() >= deadline
                    or time.monotonic() >= mono or review.snapshot(self) != snapshot
                    or policy['candidate_scope'] != code_scope()):
                raise WCEError('BOOTSTRAP_REVIEW_CHANGED')
            if review.data['schema'] == 6:
                from .own_body_attempt import validate_policy
            else:
                from .own_body_followup import validate_policy
            with _history_transaction(self.workflow.db) as (db, history_locators):
                self.workflow._resource(db, original, history_locators=history_locators)
                validate_policy(db, policy)

        approval = None
        try:
            current()
            terminal.flush()
            terminal.write('TRUSTED REVIEW_BEGIN')
            terminal.write('TRUSTED 本轮仅在本机采纳已保存的安全正文响应观察；新增上传次数为0，不取用钥匙串、不获取token、不调用任何远端接口。')
            terminal.write('TRUSTED 原UNKNOWN历史保留。后续草稿保存及独立GET须另有有效连接和本人精确图文批准。')
            terminal.display({'body_attempt' if review.data['schema'] == 6 else 'body_followup': policy, 'snapshot': snapshot, 'expires': deadline})
            for source, proof, _ in review.sources:
                terminal.display({'source': source, 'source_sha256': proof})
            terminal.write('TRUSTED REVIEW_END')
            code = secrets.token_hex(16)
            terminal.write('TRUSTED approve ' + code)
            if terminal.ask('CHALLENGE ' + code) != 'approve ' + code:
                raise WCEError('BOOTSTRAP_CONFIRMATION_DENIED')
            current()
            selector = review.data['selector']
            approval = self.workflow.authorize_trial(self.actor, self.connection,
                selector['bundle_id'], selector['version'], selector['content_digest'], deadline,
                **({'body_attempt': policy} if review.data['schema'] == 6 else {'body_followup': policy}))
            current()
            self.local_adoption_context = (review, snapshot, policy, deadline, mono, approval, current)
            return approval
        except BaseException as error:
            self._failure(error)
            if approval is not None:
                self.workflow.cancel_trial(approval)
            self.close()
            raise

    def guided_review(self, terminal, request_path):
        """One human review, before any IPC listener or business send exists."""
        from .own_guided_review import ReviewRequest
        if not self.alive or self.listener is not None or self.lease is not None:
            raise WCEError('BOOTSTRAP_REVIEW_UNAVAILABLE')
        review_started, review_monotonic = self.clock(), time.monotonic()
        original = self.profile
        review = ReviewRequest.load(self.config, original, request_path, review_started)
        source_deadline = min([self.config.data['expires_at'], original.expires,
            original.session_expires, original.grant_expires, original.credential_expires]
            + [expiry for _, _, expiry in review.sources]
            + [e.expires for e in original.evidence_tuple])
        self.run_phase = 'SNAPSHOT'
        snapshot = review.snapshot(self)
        body_policy = None
        draft_policy = None
        def draft_snapshot():
            from .own_draft_reconcile import snapshot as draft_snapshot_impl
            with _history_transaction(self.workflow.db) as (db, history_locators):
                self.workflow._resource(db, self.profile, history_locators=history_locators)
                return draft_snapshot_impl(self.workflow, db, self.profile, review.data['selector'],
                    review.data['draft_recovery']['request_key'], history_locators=history_locators)
        if review.data['schema'] == 7:
            draft_policy = draft_snapshot()
            requested = review.data['draft_recovery']
            if (requested['candidate_scope'] != draft_policy['candidate_scope']
                    or requested['policy'] != draft_policy['policy']):
                raise WCEError('BOOTSTRAP_REVIEW_CHANGED')
        if review.data['schema'] == 4:
            body_policy = self.workflow.body_recovery_snapshot(self.actor, self.connection,
                review.data['selector'], review.data['body_recovery']['original_request_key'])
            if any(review.data['body_recovery'][k] != body_policy[k] for k in review.data['body_recovery']):
                raise WCEError('BOOTSTRAP_REVIEW_CHANGED')
        if review.data['schema'] == 5:
            body_policy = self.workflow.body_followup_snapshot(self.actor, self.connection,
                review.data['selector'], review.data['body_followup']['original_request_key'],
                review.data['body_followup']['action'])
            if any(review.data['body_followup'][k] != body_policy[k] for k in review.data['body_followup']):
                raise WCEError('BOOTSTRAP_REVIEW_CHANGED')
            if body_policy['action'] == 'ADOPT_OBSERVATION_ONLY':
                return self.guided_adoption(terminal, review, snapshot, body_policy, original=original,
                    review_started=review_started, review_monotonic=review_monotonic,
                    source_deadline=source_deadline)
        if review.data['schema'] == 6:
            from .own_body_attempt import ADOPT
            requested = review.data['body_attempt']
            body_policy = self.workflow.body_attempt_snapshot(self.actor, self.connection,
                review.data['selector'], requested['original_request_key'], requested['draft_request_key'], requested['action'])
            if any(requested[k] != body_policy[k] for k in requested):
                raise WCEError('BOOTSTRAP_REVIEW_CHANGED')
            if body_policy['action'] == ADOPT:
                return self.guided_adoption(terminal, review, snapshot, body_policy, original=original,
                    review_started=review_started, review_monotonic=review_monotonic,
                    source_deadline=source_deadline)
        if review.data['schema'] in (2, 3):
            from .own_reconcile import cover_snapshot
            cover_snapshot(self, review.data['reconcile_cover']['request_key'], review.data['selector'])
        if self.credential_store is None:
            terminal.write('TRUSTED 请输入公众号 AppSecret；输入隐藏，仅保存在本次进程内存中。')
        else:
            terminal.write('TRUSTED 本连接使用系统钥匙串；首次隐藏输入的 AppSecret 将在微信验证后保存，之后由宿主自动读取。')
        # Fix the original review/source lifetime before any Keychain, hidden
        # input or network wait. A later wall-clock rollback cannot remap it.
        source_mono = review_monotonic + (source_deadline - review_started)
        approval = None
        try:
            # Validate once before displaying any untrusted review material, so
            # both the secret and the actual returned token can be rejected as
            # reflections. Keep only a private pending result during the wait;
            # no broker capability, protocol proof, grants or IPC exists yet.
            pending = self._prepare_token(terminal,
                {'review': review.data, 'sources': [s for s, _, _ in review.sources],
                 'snapshot': snapshot}, pending=True)
            self.pending_token = pending
            token_deadline, token_mono = pending[1:]
            review_deadline = min(token_deadline, source_deadline)
            review_mono = min(token_mono, source_mono)

            def confirmation_digest():
                recovery = None
                if review.data['schema'] == 7:
                    recovery = draft_snapshot()
                    if recovery != draft_policy:
                        raise WCEError('BOOTSTRAP_REVIEW_CHANGED')
                if review.data['schema'] == 4:
                    recovery = self.workflow.body_recovery_snapshot(self.actor, self.connection,
                        review.data['selector'], review.data['body_recovery']['original_request_key'])
                    if recovery != body_policy:
                        raise WCEError('BOOTSTRAP_REVIEW_CHANGED')
                if review.data['schema'] == 5:
                    recovery = self.workflow.body_followup_snapshot(self.actor, self.connection,
                        review.data['selector'], body_policy['original_request_key'], body_policy['action'])
                    if recovery != body_policy:
                        raise WCEError('BOOTSTRAP_REVIEW_CHANGED')
                if review.data['schema'] == 6:
                    recovery = self.workflow.body_attempt_snapshot(self.actor, self.connection,
                        review.data['selector'], body_policy['original_request_key'],
                        body_policy['draft_request_key'], body_policy['action'])
                    if recovery != body_policy:
                        raise WCEError('BOOTSTRAP_REVIEW_CHANGED')
                if review.data['schema'] in (2, 3):
                    from .own_reconcile import cover_snapshot, MAX_MATERIALS, MAX_READ_WORKERS, PAGE_SIZE, MAX_CANDIDATES
                    row, intent, image = cover_snapshot(self, review.data['reconcile_cover']['request_key'],
                                                        review.data['selector'])
                    from .local_preparation import sha
                    recovery = {'row': row, 'intent': intent, 'image_sha256': sha(image),
                        'image_size': len(image), 'maximum_materials': MAX_MATERIALS,
                        'maximum_workers': MAX_READ_WORKERS, 'page_size': PAGE_SIZE,
                        'maximum_candidates': MAX_CANDIDATES, 'mode': 'OFFICIAL_READ_MATCH'}
                    if review.data['schema'] == 3:
                        from .own_png import recovery_binding, ORIGIN
                        recovery.update(mode=ORIGIN, recovery_policy=recovery_binding(row, intent))
                return digest({'profile_fence': original.fence(), 'binding': original.binding(),
                    'config_digest': config_digest(self.config), 'review': review.data,
                    'source_expiries': [expiry for _, _, expiry in review.sources],
                    'snapshot': snapshot, 'recovery': recovery, 'apis': [] if draft_policy else list(APIS),
                    'read_apis': list(DRAFT_READ_APIS) if draft_policy else list(READ_APIS) if review.data['schema'] in (2, 3) else [],
                    'maximum_execution_seconds': 300, 'review_expires': review_deadline})

            seal = confirmation_digest()
            terminal.flush()
            terminal.write('TRUSTED REVIEW_BEGIN')
            self.run_phase = 'REVIEW'
            terminal.write('TRUSTED 请核对账号条件和下方完整图文。本次仅查询已存在的同一篇草稿并独立读回，不上传图片、不再次保存。' if draft_policy else
                'TRUSTED 请核对账号条件和下方完整图文。本次确认仅批准这篇草稿的配图上传、保存和回读。')
            terminal.write('TRUSTED 连接验证已完成；确认后才启用最多五分钟的执行期，且不超过原凭据及审核材料期限。')
            if draft_policy:
                terminal.write('TRUSTED 只读两遍完整草稿列表，最多1000篇/100次列表、4次候选GET、1次末GET及1次独立GET，最多106次读；拒绝或不明确即停。')
                terminal.write('TRUSTED 列表会读取最多1000条草稿的完整正文；非目标内容仅在进程内检查后丢弃，不进入证明或诊断。每页上限2MiB，超限停止，不保证任何1000条以内的库都可完成。')
                terminal.write('TRUSTED 仅唯一单篇news的标题、完整正文HTML和封面标识逐字符相同才接受；不修改HTML或图片URL，不下载CDN。')
                terminal.write('TRUSTED 成功仅证明找到唯一现存同内容草稿，不证明是原未知请求创建，两遍扫描不是原子快照；原未知响应历史保留。')
                terminal.display({'draft_read_policy': draft_policy, 'read_apis': list(DRAFT_READ_APIS), 'remote_write_budget': 0})
            if review.data['schema'] == 4:
                terminal.write('TRUSTED 本轮额外发送原正文图最多一次，可能产生重复图片；原UNKNOWN历史保留，封面不重传。')
                terminal.write('TRUSTED 新尝试再次未知即停止；仅允许同一篇草稿保存及独立GET，不公开发布。')
                terminal.display({'body_recovery': body_policy})
            if review.data['schema'] == 5:
                terminal.write('TRUSTED 原正文图已实际发送两次且均UNKNOWN，先前额外一次预算已用尽。')
                terminal.write('TRUSTED 本轮是同图第三次实际发送，最多再发1次，可能再次产生重复图片；原两次历史不改，封面不重传。')
                terminal.write('TRUSTED 显式选择BODY_URL_RESPONSE_V1：可信官方HTTPS回包中经严格安全检查的图片URL可作为业务引用；errcode若存在必须为整数0，缺失按此本地政策接受，不宣称旧失败原因已查明。')
                terminal.write('TRUSTED 安全响应观察先保存；再次未知即停止，不递归追加发送。仅保存同一篇草稿并独立GET，不公开发布。')
                terminal.display({'body_followup': body_policy})
            if review.data['schema'] == 6:
                terminal.write('TRUSTED 原正文图三次发送均UNKNOWN，已用预算保留；本轮是最后第4次，新增最多1次，总准入硬上限4，无第5次或递归追加。')
                terminal.write('TRUSTED 本次可能产生重复图片；固定原图、账号、文章和草稿key，封面不重传，仅保存同一篇草稿并独立GET，不公开发布。')
                terminal.write('TRUSTED 显式选择BODY_API_REFERENCE_V2：严格检查官方API响应，路径和未知参数视为opaque业务引用，不授权访问CDN；凭据键和当前token检查不能证明排除了全部未知秘密。')
                terminal.write('TRUSTED 安全观察先保存再核当前批准；再次UNKNOWN永停。spent seal和准入提交未知时即使未实际POST也可能保守损失最后机会，不自动恢复发送权。')
                terminal.write('TRUSTED spent seal仅保护新代码受支持入口的SQLite快照还原，不能检测旧binary与旧DB或整机连seal同时回滚；准入后不得用旧DB回收预算。')
                terminal.display({'body_attempt': body_policy})
            if review.data['schema'] in (2, 3):
                if review.data['schema'] == 3:
                    from .own_png import policy
                    terminal.write('TRUSTED 本轮选择PNG8精确像素策略：文件字节可以不同，但尺寸及每个RGBA像素字节（包括透明RGB和alpha）必须完全相同。')
                    terminal.write('TRUSTED 仅接受受限RGB8/RGBA8非交错PNG；忽略指定text/caBX元数据，不验证C2PA来源认证、不声称整文件相同；不缩放或近似比较。')
                    terminal.write('TRUSTED 所有候选必须完整解码且仅一个精确匹配；两遍完整列表相同，末次GET原始文件字节必须等于首次选定候选。')
                    terminal.display({'exact_pixel_policy': policy()})
                else:
                    terminal.write('TRUSTED 本轮先通过素材列表及素材读取，对账原封面未知请求；只在唯一原图片字节哈希完全匹配时继续。')
                terminal.write('TRUSTED 无匹配、多个匹配或查询不明确时停止；不会重新发送封面上传。')
                terminal.display({'read_apis': list(READ_APIS), 'reconcile_cover': review.data['reconcile_cover']})
            terminal.write('TRUSTED 条件来自本人此前核对；这些声明不表示各业务接口已经实测成功。')
            terminal.display({'target': original.binding(), 'confirmation_digest': seal,
                'review_expires': review_deadline, 'maximum_execution_seconds': 300,
                'apis': [] if draft_policy else list(APIS), 'snapshot': snapshot})
            for source, proof, _ in review.sources:
                terminal.display({'source': source, 'source_sha256': proof})
            terminal.write('TRUSTED REVIEW_END')
            code = secrets.token_hex(16)
            terminal.write('TRUSTED 确认请复制下面完整一行（含空格和随机码），取消请输入 cancel：')
            terminal.write('TRUSTED approve ' + code)
            answer = terminal.ask('CHALLENGE ' + code)
            if answer != 'approve ' + code:
                raise WCEError('BOOTSTRAP_CONFIRMATION_DENIED')
            if (not self.alive or self.profile != original or self.lease is not None
                    or self.pending_token is not pending
                    or self.clock() >= review_deadline or time.monotonic() >= review_mono
                    or review.snapshot(self) != snapshot or confirmation_digest() != seal):
                raise WCEError('BOOTSTRAP_REVIEW_CHANGED')
            token, expires, mono = pending
            self.pending_token = None
            pending = None
            self._activate_token(terminal, token, expires, mono)
            token = None
            lease = self.lease
            self.mono_expiry = min(self.mono_expiry, review_mono)
            deadline = min(review_deadline, lease.expires_at)
            active = self.profile
            proofs = tuple(OwnerEvidence(source['kind'], active.account_id, active.resource_id,
                active.generation, deadline, 'UNKNOWN' if source['kind'] in (DRAFT_READ_APIS if draft_policy else READ_APIS) else 'AVAILABLE', proof, self.source_kind)
                for source, proof, _ in review.sources)
            review_kinds = frozenset(source['kind'] for source, _, _ in review.sources)
            grants = (frozenset(DRAFT_READ_APIS) | {'local.read', 'local.write'} if draft_policy else
                active.granted_actions | frozenset(APIS) | (frozenset(READ_APIS) if review.data['schema'] in (2, 3) else frozenset()))
            candidate = replace(active, evidence_tuple=tuple(e for e in active.evidence_tuple
                if e.kind not in review_kinds) + proofs, granted_actions=grants)
            # No endpoint exists during this publication/DB commit. A failure
            # closes the runtime and invalidates its fence; no RPC can see a
            # partially granted profile. Future starts mint a fresh revision.
            self._publish(candidate)
            if review.snapshot(self) != snapshot or confirmation_digest() != seal:
                raise WCEError('BOOTSTRAP_REVIEW_CHANGED')
            s = review.data['selector']
            recovery_policy = None
            if review.data['schema'] == 3:
                from .own_reconcile import cover_snapshot
                from .own_png import recovery_binding
                row, intent, _ = cover_snapshot(self, review.data['reconcile_cover']['request_key'], s)
                recovery_policy = recovery_binding(row, intent)
            approval = self.workflow.authorize_trial(self.actor, self.connection,
                s['bundle_id'], s['version'], s['content_digest'], deadline,
                **({'draft_recovery': draft_policy} if draft_policy is not None else
                   {'recovery_policy': recovery_policy} if recovery_policy is not None else
                   {'body_recovery': body_policy} if review.data['schema'] == 4 else
                   {'body_followup': body_policy} if review.data['schema'] == 5 else
                   {'body_attempt': body_policy} if review.data['schema'] == 6 else {}))
            self.workflow._current(candidate, lease, 'local.write')
            if (self.clock() >= deadline or review.snapshot(self) != snapshot
                    or confirmation_digest() != seal):
                raise WCEError('BOOTSTRAP_REVIEW_CHANGED')
            self.guided_context = (review, snapshot, deadline, approval, candidate, lease)
            return approval
        except BaseException as error:
            self._failure(error)
            try:
                self._publish(original)
            except BaseException:
                pass
            if approval is not None:
                try:
                    self.workflow.cancel_trial(approval)
                except BaseException:
                    pass  # Runtime closes; fresh-start fence cannot use this row.
            try:
                self.close()
            except BaseException:
                pass
            raise
        finally:
            self.pending_token = None
            token, pending = None, None

    def _guided_current(self, approval):
        if self.guided_context is None:
            raise WCEError('BOOTSTRAP_REVIEW_UNAVAILABLE')
        review, snapshot, deadline, approved, candidate, lease = self.guided_context
        if approval != approved or self.clock() >= deadline:
            raise WCEError('BOOTSTRAP_REVIEW_EXPIRED')
        self.workflow._current(candidate, lease, 'local.write')
        if review.snapshot(self) != snapshot:
            raise WCEError('BOOTSTRAP_REVIEW_CHANGED')
        with _history_transaction(self.workflow.db) as (db, history_locators):
            self.workflow._resource(db, candidate, history_locators=history_locators)
            self.workflow._approval(db, candidate, snapshot, snapshot['content_digest'], approval,
                allow_draft_read=review.data['schema'] == 7)

    def inspect(self, terminal, bundle, version):
        result = self.router.call('own.articles.read', {'connection_id': self.connection,
                                                      'bundle_id': bundle, 'version': version})
        p = self.profile
        lease = self.workflow.broker.load(OwnTokenScope.from_profile(p))
        deadline = min([self.clock() + 300, lease.expires_at, p.expires, p.session_expires,
                        p.grant_expires, p.credential_expires] + [e.expires for e in p.evidence_tuple])
        terminal.flush()
        terminal.write('TRUSTED REVIEW_BEGIN')
        terminal.display({'target': p.binding(), 'token_revision': p.token_revision, 'apis': list(APIS),
                          'expires': deadline, 'snapshot': result})
        terminal.write('TRUSTED REVIEW_END')
        self.challenge(terminal, 'approve')
        self.paths_current()
        self.workflow._current(p, lease, 'local.write')
        approval = self.workflow.authorize_trial(self.actor, self.connection, bundle, version,
                                                 result['content_digest'], deadline)
        terminal.write('TRUSTED APPROVED ' + approval)

    def revoke(self, kind):
        if kind not in HUMAN_KINDS:
            raise WCEError('BOOTSTRAP_EVIDENCE_INVALID')
        p = self.profile
        proofs = tuple(replace(e, state='REVOKED') if e.kind == kind else e for e in p.evidence_tuple)
        self._publish(replace(p, evidence_tuple=proofs, granted_actions=p.granted_actions - {kind}))

    def run(self, terminal, review_request=None):
        approval = self.guided_review(terminal, review_request) if review_request is not None else None
        try:
            if self.local_adoption_context is not None:
                self.run_phase = 'BODY_ADOPTION'
                adopt = (self.workflow.adopt_final_body_observation if self.local_adoption_context[0].data['schema'] == 6
                    else self.workflow.adopt_body_observation)
                result = adopt(self.actor, self.connection, approval, self.local_adoption_context[-1])
                terminal.display(result)
                terminal.write('TRUSTED BODY_OBSERVATION_ADOPTED_ZERO_NETWORK')
                self.close()
                return
            if approval is not None:
                self._guided_current(approval)
                if self.guided_context[0].data['schema'] == 7:
                    self.run_phase = 'DRAFT_RECONCILE'
                    from .own_draft_reconcile import reconcile
                    result = reconcile(self, approval)
                    terminal.write('TRUSTED EXISTING_DRAFT_READ_MATCHED')
                    self._guided_current(approval)
                if self.guided_context[0].data['schema'] == 4:
                    self.run_phase = 'BODY_RECOVERY'
                    result = self.workflow.execute_body_recovery(self.actor, self.connection, approval)
                    terminal.display(result)
                    if result['state'] != 'SUCCEEDED':
                        raise WCEError('OWN_BODY_RECOVERY_RESULT_UNKNOWN')
                    terminal.write('TRUSTED BODY_REPLACEMENT_SUCCEEDED_ORIGINAL_UNKNOWN_RETAINED')
                    self._guided_current(approval)
                if self.guided_context[0].data['schema'] == 5:
                    self.run_phase = 'BODY_FOLLOWUP'
                    result = self.workflow.execute_body_followup(self.actor, self.connection, approval)
                    terminal.display(result)
                    if result['state'] != 'SUCCEEDED':
                        raise WCEError('OWN_BODY_FOLLOWUP_RESULT_UNKNOWN')
                    terminal.write('TRUSTED BODY_FOLLOWUP_SUCCEEDED_ORIGINAL_UNKNOWNS_RETAINED')
                    self._guided_current(approval)
                if self.guided_context[0].data['schema'] == 6:
                    self.run_phase = 'BODY_ATTEMPT4'
                    result = self.workflow.execute_body_attempt(self.actor, self.connection, approval)
                    terminal.display(result)
                    if result['state'] != 'SUCCEEDED':
                        raise WCEError('OWN_BODY_ATTEMPT_RESULT_UNKNOWN')
                    terminal.write('TRUSTED FINAL_BODY_ATTEMPT4_SUCCEEDED_OLD_UNKNOWNS_RETAINED')
                    self._guided_current(approval)
                if self.guided_context[0].data['schema'] in (2, 3):
                    self.run_phase = 'RECONCILE'
                    from .own_reconcile import reconcile_cover
                    result = reconcile_cover(self, approval)
                    terminal.display(result)
                    terminal.write('TRUSTED COVER_RECONCILED_BY_OFFICIAL_READ')
                    self._guided_current(approval)
            self.start(accept_clients=approval is None)
            if approval is not None:
                self._guided_current(approval)
                self._serve_clients()
                terminal.write('TRUSTED APPROVED ' + approval)
        except BaseException as error:
            self._failure(error)
            try:
                self.close()
            except BaseException:
                pass
            try:
                if approval is not None:
                    self.workflow.cancel_trial(approval)
            except BaseException:
                pass
            raise
        terminal.write('TRUSTED OPERATOR_READY')
        self.run_phase = 'READY'
        try:
            while self.alive:
                try:
                    command = terminal.ask('COMMAND').split(' ')
                    if command == ['quit']:
                        break
                    if command == ['lease']:
                        self.obtain(terminal)
                    elif len(command) == 2 and command[0] == 'attest':
                        self.attest(terminal, command[1])
                    elif len(command) == 2 and command[0] == 'revoke':
                        self.paths_current()
                        self.revoke(command[1])
                        terminal.write('TRUSTED EVIDENCE_REVOKED')
                    elif len(command) == 3 and command[0] == 'inspect':
                        self.inspect(terminal, command[1], command[2])
                    elif len(command) == 2 and command[0] == 'cancel':
                        self.paths_current()
                        if re.fullmatch('own-approval-[a-f0-9]{32}', command[1]) is None:
                            raise WCEError('BOOTSTRAP_INVALID_INPUT')
                        self.workflow.cancel_trial(command[1])
                        terminal.write('TRUSTED APPROVAL_CANCELLED')
                    else:
                        raise WCEError('BOOTSTRAP_INVALID_INPUT')
                except WCEError as error:
                    terminal.write('TRUSTED ERROR ' + error.code)
        except BaseException as error:
            self._failure(error)
            try:
                self.close()
            except BaseException:
                pass
            raise
        else:
            self.close()

    def close(self):
        self.alive, self.lease, self.mono_expiry = False, None, 0
        self.guided_context = None
        self.local_adoption_context = None
        self.pending_token = None
        self._publish(replace(self.profile, active=False))
        if self.listener is not None:
            self.listener.close()
        with self.client_lock:
            for client in list(self.clients):
                try:
                    client.shutdown(socket.SHUT_RDWR)
                except OSError:
                    pass

                client.close()
        deadline = time.monotonic() + 11
        for worker in [self.accept_worker] + self.workers:
            if worker is not None and worker is not threading.current_thread():
                worker.join(max(0, deadline - time.monotonic()))
        # Exact identity guards: stranger endpoint and durable state are never removed.
        for path, pin, check in ((self.socket_path, self.endpoint_pin, socket_pin),
                                 (self.info_path, self.info_pin, path_check)):
            if pin is not None:
                try:
                    if check(path) == pin:
                        path.unlink()
                except Exception:
                    pass

    def _failure(self, error):
        from .own_run_outcome import safe_code
        if self.run_failure is None:
            self.run_failure = safe_code(error.code if isinstance(error, WCEError) else None)
        # Revoke the live capability before fallible filesystem/DB/thread
        # cleanup. A cleanup exception cannot leave a usable lease behind.
        self.alive, self.lease, self.mono_expiry = False, None, 0
        self.guided_context = None
        self.pending_token = None


def operator(config_path, acquisition_sender=None, wire_sender=None, source_kind='OPERATOR_ATTESTED', review_request=None, keychain=False):
    terminal = Terminal(sys.stdin, sys.stdout)  # Reject before config, DB, endpoint or input fallback.
    config = load_config(config_path)
    runtime = Operator(config, acquisition_sender, wire_sender, source_kind)
    primary_error = None
    try:
        if type(keychain) is not bool:
            raise WCEError('BOOTSTRAP_KEYCHAIN_UNAVAILABLE')
        if keychain:
            if source_kind != 'OPERATOR_ATTESTED':
                raise WCEError('BOOTSTRAP_SOURCE_INVALID')
            from .own_keychain import KeychainCredential
            runtime.credential_store = KeychainCredential(config)
        runtime.run(terminal, review_request)
    except BaseException as error:
        primary_error = error
        runtime._failure(error)
        raise
    finally:
        try:
            runtime.close()
        except BaseException as error:
            runtime._failure(error)
            if primary_error is None:
                raise
        finally:
            try:
                from .own_run_outcome import write_outcome
                if not write_outcome(runtime):
                    raise WCEError('BOOTSTRAP_RUN_UNDETERMINED')
            except BaseException:
                try:
                    terminal.write('TRUSTED RUN_OUTCOME_RECORD_UNAVAILABLE')
                except BaseException:
                    pass  # Diagnostic delivery cannot replace the first error.


from .draft_group_history_context import history_transaction as _history_transaction
