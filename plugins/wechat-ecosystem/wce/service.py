"""Authorized offline workflow, version binding and durable request claims."""
from collections.abc import Callable
import hashlib
import hmac
import json
import math
import re
import time
from uuid import uuid4

from .contracts import (Actor, Capability, CapabilityState, Connection, DraftCallContext, FakeSecretProvider,
                        OfficialAccountAdapter, PublicationState, Receipt, RejectedOperation,
                        SecretProvider, Status, UncertainResult, WCEError)
from .storage import Database, BUSINESS_TABLES


def canonical(value) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False)


def digest(value) -> str:
    return hashlib.sha256(canonical(value).encode()).hexdigest()


def text(value, maximum=4096) -> str:
    if not isinstance(value, str) or not value.strip() or len(value) > maximum:
        raise WCEError("INVALID_INPUT")
    return value


def ttl(value, maximum=3600) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or not 0 < value <= maximum:
        raise WCEError("INVALID_TTL")
    return value


def mock_reference(value):
    return isinstance(value, str) and re.fullmatch(r"mock-(?:material|draft|preview|publication)-[a-f0-9]{32}", value) is not None


class OfficialAccountService:
    def __init__(self, path, adapter: OfficialAccountAdapter, secrets: SecretProvider | None = None,
                 clock: Callable[[], float] = time.time):
        if adapter.mode != "mock":
            raise ValueError("This candidate only accepts offline mock transport")
        self.db = Database(path)
        self.adapter = adapter
        self.secrets = secrets or FakeSecretProvider()
        self.clock = clock
        mode = adapter.workflow_mode
        if mode not in {"offline", "fixture"}:
            raise WCEError("TRANSPORT_MODE_MISMATCH")
        with self.db.transaction(write=True) as db:
            config = db.execute("SELECT mode FROM service_config WHERE id=1").fetchone()
            if config is None:
                # Legacy business objects were created using the offline adapter.
                if mode != "offline" and any(db.execute(f"SELECT 1 FROM {table} LIMIT 1").fetchone() for table in BUSINESS_TABLES):
                    raise WCEError("MODE_STATE_UNVERIFIED")
                db.execute("INSERT INTO service_config VALUES(1,?)", (mode,))
            elif config["mode"] != mode:
                raise WCEError("MODE_STATE_MISMATCH")
        from .connection_lifecycle import FixtureConnections
        self.lifecycle = FixtureConnections(self)
        from .local_preparation import LocalPreparations
        self.local = LocalPreparations(self)

    def evidence(self):
        if self.adapter.workflow_mode == "fixture":
            return {"transport": "mock", "mode": "test", "runtime": "wire_fixture",
                    "connected": False, "platform_verified": False, "evidence": "synthetic_wire_fixture"}
        return {"transport": "mock", "mode": "test", "runtime": "offline",
                "connected": False, "platform_verified": False}

    def _draft_context(self, db, actor, conn, draft_id, version, content_digest, material_ids, operation_id=None):
        self._materials(db, actor, conn["id"], material_ids)
        materials = tuple((local_id, db.execute(
            "SELECT platform_ref FROM materials WHERE id=? AND tenant=? AND connection=?",
            (local_id, actor.tenant_id, conn["id"])).fetchone()[0]) for local_id in material_ids)
        registry = self.lifecycle.usable(db, conn)
        session = self.lifecycle._session(db, actor)
        grant = db.execute("SELECT expires FROM grants WHERE connection=? AND principal=?",
                           (conn["id"], actor.principal_id)).fetchone()
        expires = min(conn["expires"], session["expires"], grant["expires"],
                      registry["token_expires"] if registry["managed"] else conn["expires"])
        artifact_generation, artifact_operation_id = conn["generation"], operation_id
        if operation_id is None:
            artifact = db.execute("SELECT o.id,o.generation FROM operations o JOIN versions v ON v.id=o.version "
                                  "WHERE o.tenant=? AND o.connection=? AND o.kind=? AND o.version=? "
                                  "AND o.state=? AND o.platform_ref=v.platform_ref",
                                  (actor.tenant_id, conn["id"], Capability.DRAFT, version, PublicationState.SUCCEEDED)).fetchone()
            if artifact is None:
                raise WCEError("DRAFT_UNAVAILABLE")
            artifact_generation, artifact_operation_id = artifact["generation"], artifact["id"]
        def registry_guard(action):
            capability = Capability.DRAFT if action == "draft.add" else Capability.READ_DRAFT
            with self.db.transaction() as current_db:
                current = self._authorize(current_db, actor, conn["id"], capability)
                latest = self.lifecycle.registry(current_db, conn["id"])
                if (current["generation"] != conn["generation"] or latest["profile"] != registry["profile"]
                        or latest["resource"] != registry["resource"] or latest["epoch"] != registry["epoch"]
                        or latest["token_revision"] != registry["token_revision"]):
                    raise WCEError("AUTHORIZATION_CHANGED")
        return DraftCallContext(actor, conn["id"], conn["generation"], expires, conn["secret_ref"],
                                conn["evidence"] == "synthetic" and conn["account_type"] == "synthetic_official_account"
                                and conn["qualification"] == "synthetic_qualified",
                                draft_id, version, content_digest, materials, operation_id,
                                registry["resource"], registry["token_revision"], registry_guard,
                                artifact_generation, artifact_operation_id)

    # Trusted fixture/administration functions. None are exposed as model tools.
    def register_connection(self, connection: Connection, principal: str, capabilities=None):
        with self.db.transaction(write=True) as db:
            db.execute("INSERT INTO connections VALUES(?,?,?,?,?,?,?,?,?,?,?)",
                       (connection.id, connection.tenant_id, connection.account_type, connection.qualification,
                        connection.secret_ref, canonical(connection.capabilities), connection.expires_at,
                        connection.authorization_generation, connection.active, connection.evidence, canonical(connection.preview_targets)))
            db.execute("INSERT INTO grants VALUES(?,?,?,?)",
                       (connection.id, principal, canonical(list(connection.capabilities if capabilities is None else capabilities)), connection.expires_at))
            self.lifecycle.register_legacy(db, db.execute("SELECT * FROM connections WHERE id=?", (connection.id,)).fetchone(), principal)

    def register_session(self, actor: Actor, connections: tuple[str, ...], expires_at: float):
        with self.db.transaction(write=True) as db:
            db.execute("INSERT INTO sessions VALUES(?,?,?,?,?,?,?)",
                       (actor.session_id, actor.tenant_id, actor.principal_id, actor.client_id, expires_at, 1, canonical(connections)))

    def revoke_session(self, session_id: str):
        with self.db.transaction(write=True) as db:
            db.execute("UPDATE sessions SET active=0 WHERE id=?", (session_id,))

    def revoke_connection(self, connection_id: str):
        self.lifecycle.revoke(connection_id)

    def _visible(self, db, actor: Actor, connection_id: str):
        now = self.clock()
        session = db.execute("SELECT * FROM sessions WHERE id=? AND tenant=? AND principal=? AND client=?",
                             (actor.session_id, actor.tenant_id, actor.principal_id, actor.client_id)).fetchone()
        if session is None or not session["active"] or session["expires"] <= now:
            raise WCEError("SESSION_INVALID")
        if connection_id not in json.loads(session["connections"]):
            raise WCEError("ACCESS_DENIED")
        conn = db.execute("SELECT * FROM connections WHERE id=? AND tenant=?", (connection_id, actor.tenant_id)).fetchone()
        grant = db.execute("SELECT * FROM grants WHERE connection=? AND principal=?", (connection_id, actor.principal_id)).fetchone()
        if conn is None or grant is None or grant["expires"] <= now:
            raise WCEError("ACCESS_DENIED")
        return conn

    def _authorize(self, db, actor: Actor, connection_id: str, capability: Capability | None = None):
        conn = self._visible(db, actor, connection_id)
        self.lifecycle.usable(db, conn)
        grant = db.execute("SELECT * FROM grants WHERE connection=? AND principal=?",
                           (connection_id, actor.principal_id)).fetchone()
        now = self.clock()
        if not conn["active"] or conn["expires"] <= now:
            raise WCEError("CONNECTION_REVOKED_OR_EXPIRED")
        if capability is not None:
            state = json.loads(conn["capabilities"]).get(capability, CapabilityState.NOT_IMPLEMENTED)
            if state != CapabilityState.AVAILABLE or capability not in json.loads(grant["capabilities"]):
                raise WCEError("CAPABILITY_UNAVAILABLE")
        return conn

    def capabilities(self, actor: Actor, connection_id: str):
        with self.db.transaction() as db:
            conn = self._authorize(db, actor, text(connection_id, 128))
            grant = db.execute("SELECT capabilities FROM grants WHERE connection=? AND principal=?",
                               (connection_id, actor.principal_id)).fetchone()
            states = json.loads(conn["capabilities"])
            allowed = json.loads(grant["capabilities"])
            result = {}
            for cap in Capability:
                state = states.get(cap, CapabilityState.NOT_IMPLEMENTED)
                if state == CapabilityState.AVAILABLE and cap not in allowed:
                    state = CapabilityState.UNAUTHORIZED
                result[cap] = state
            return {"connection_id": connection_id, "account_type": conn["account_type"],
                    "qualification": conn["qualification"], "authorization_generation": conn["generation"],
                    "capabilities": result, "evidence": conn["evidence"], "transport": "mock",
                    "platform_schema": "UNVERIFIED"} | self.evidence()

    def profiles(self, actor: Actor):
        """Sanitized lifecycle state. Inactive accounts do not block the list."""
        with self.db.transaction() as db:
            session = self.lifecycle._session(db, actor)
            connection_ids = json.loads(session["connections"])
        profiles = []
        for connection_id in connection_ids:
            try:
                profiles.append(self.lifecycle.status(actor, connection_id))
            except WCEError as error:
                if error.code != "ACCESS_DENIED":
                    raise
        from .connection_lifecycle import EVIDENCE
        return {"profiles": profiles} | EVIDENCE | self.evidence()

    def _unresolved(self, db, actor, conn, kind):
        resource = self.lifecycle.registry(db, conn["id"])["resource"]
        return db.execute("SELECT o.id FROM operations o JOIN connection_registry r ON r.connection=o.connection "
                          "JOIN account_profiles p ON p.id=r.profile "
                          "WHERE o.tenant=? AND p.tenant=? AND p.resource=? AND o.kind=? AND o.state=? LIMIT 1",
                          (actor.tenant_id, actor.tenant_id, resource, kind, PublicationState.UNKNOWN)).fetchone()

    def _credential(self, conn):
        return self.secrets.get(conn["tenant"], conn["id"], conn["secret_ref"])

    def _view(self, row):
        return {"operation_id": row["id"], "connection_id": row["connection"], "action": row["kind"],
                "state": row["state"], "platform_ref": row["platform_ref"],
                "result": json.loads(row["result"]), "transport": "mock", "evidence": "local_verified"} | self.evidence()

    def _claim(self, db, actor, conn, kind, request_key, payload, version=None, targets=()):
        text(request_key, 128)
        fingerprint = digest({"connection": conn["id"], "action": kind, "payload": payload})
        old = db.execute("SELECT * FROM operations WHERE tenant=? AND principal=? AND connection=? AND request_key=?",
                         (actor.tenant_id, actor.principal_id, conn["id"], request_key)).fetchone()
        if old:
            if old["fingerprint"] != fingerprint:
                raise WCEError("IDEMPOTENCY_CONFLICT")
            return old, False
        # Local TTL, aliases or a new payload must not license a retry after an
        # uncertain remote write. Conservatively pause this connection/action;
        # also covers legacy claims without a separate remote semantic digest.
        unresolved = self._unresolved(db, actor, conn, kind)
        if unresolved:
            raise WCEError("UNRESOLVED_OPERATION")
        if kind == Capability.PUBLISH:
            old_publication = db.execute("SELECT id FROM operations WHERE tenant=? AND connection=? AND version=? AND kind=?",
                                         (actor.tenant_id, conn["id"], version, kind)).fetchone()
            if old_publication:
                raise WCEError("PUBLICATION_ALREADY_REQUESTED")
        operation_id = uuid4().hex
        # Commit UNKNOWN before invoking the adapter. A crash never licenses retry.
        db.execute("INSERT INTO operations(id,tenant,principal,connection,kind,request_key,fingerprint,version,targets,generation,state,created) VALUES(?,?,?,?,?,?,?,?,?,?,?,?)",
                   (operation_id, actor.tenant_id, actor.principal_id, conn["id"], kind, request_key,
                    fingerprint, version, canonical(targets), conn["generation"], PublicationState.UNKNOWN, self.clock()))
        return db.execute("SELECT * FROM operations WHERE id=?", (operation_id,)).fetchone(), True

    def _perform(self, row, callback, on_success=None, guard=None, on_rejected=None):
        # The durable UNKNOWN claim already exists. Serialize the local dispatch
        # boundary with revocation and version changes; this is an offline lock,
        # not a production distributed transaction or a Tencent exactly-once claim.
        with self.db.transaction(write=True) as db:
            state, ref, result = PublicationState.UNKNOWN, None, json.loads(row["result"])
            try:
                if guard:
                    guard(db)
            except WCEError as error:
                state = PublicationState.FAILED
                result["error"] = error.code
            else:
                try:
                    receipt = callback()
                    if not isinstance(receipt, Receipt) or not mock_reference(receipt.platform_ref):
                        raise UncertainResult()
                    ref = receipt.platform_ref
                    if guard:
                        guard(db)  # an already-sent write stays UNKNOWN on expiry/change
                    state = PublicationState.SUBMITTED if row["kind"] == Capability.PUBLISH else PublicationState.SUCCEEDED
                except RejectedOperation:
                    state = PublicationState.FAILED
                    result["error"] = "ADAPTER_REJECTED"
                except UncertainResult as error:
                    ref = error.platform_ref if mock_reference(error.platform_ref) else None
                except Exception:
                    # Adapter/provider exceptions may contain secrets; no messages.
                    result["error"] = "ADAPTER_RESULT_UNKNOWN"
            if state == PublicationState.SUCCEEDED and on_success:
                result = on_success(db, ref)
            elif state == PublicationState.FAILED and on_rejected:
                # Only certified no-effect failures may restore local state.
                # A timeout/unknown result must retain its recovery boundary.
                on_rejected(db)
            db.execute("UPDATE operations SET state=?,platform_ref=?,result=? WHERE id=?",
                       (state, ref, canonical(result), row["id"]))
            return self._view(db.execute("SELECT * FROM operations WHERE id=?", (row["id"],)).fetchone())

    def add_material(self, actor: Actor, connection_id: str, content: str, request_key: str, expires_in=3600):
        text(content, 65536)
        ttl(expires_in)
        material_id = uuid4().hex
        content_digest = digest(content)
        with self.db.transaction(write=True) as db:
            conn = self._authorize(db, actor, connection_id, Capability.MATERIAL)
            row, new = self._claim(db, actor, conn, Capability.MATERIAL, request_key,
                                   {"digest": content_digest, "expires_in": expires_in})
            if not new:
                return self._view(row)
            db.execute("INSERT INTO materials VALUES(?,?,?,?,?,NULL)",
                       (material_id, actor.tenant_id, connection_id, content_digest, self.clock() + expires_in))
        def complete(db, ref):
            db.execute("UPDATE materials SET platform_ref=? WHERE id=?", (ref, material_id))
            return {"material_id": material_id, "content_digest": content_digest}
        def guard(db):
            current = self._authorize(db, actor, connection_id, Capability.MATERIAL)
            if current["generation"] != row["generation"]:
                raise WCEError("AUTHORIZATION_CHANGED")
        return self._perform(row, lambda: self.adapter.add_material(connection_id, content_digest, self._credential(conn)), complete, guard)

    def _materials(self, db, actor, connection_id, material_ids):
        if not isinstance(material_ids, (list, tuple)) or not 1 <= len(material_ids) <= 10:
            raise WCEError("INVALID_MATERIALS")
        if any(not isinstance(item, str) for item in material_ids) or len(set(material_ids)) != len(material_ids):
            raise WCEError("INVALID_MATERIALS")
        for material_id in material_ids:
            text(material_id, 128)
            row = db.execute("SELECT * FROM materials WHERE id=? AND tenant=? AND connection=?",
                             (material_id, actor.tenant_id, connection_id)).fetchone()
            if row is None or row["expires"] <= self.clock() or row["platform_ref"] is None:
                raise WCEError("MATERIAL_UNAVAILABLE")

    def save_draft(self, actor: Actor, connection_id: str, title: str, body: str, material_ids: list[str],
                   request_key: str, draft_id: str | None = None, expected_version: str | None = None):
        content = {"title": text(title, 256), "body": text(body, 65536), "material_ids": material_ids}
        content_digest = digest(content)
        version = uuid4().hex
        local_id = draft_id or uuid4().hex
        previous_version = None
        with self.db.transaction(write=True) as db:
            conn = self._authorize(db, actor, connection_id, Capability.DRAFT)
            self._materials(db, actor, connection_id, material_ids)
            row, new = self._claim(db, actor, conn, Capability.DRAFT, request_key,
                                   {"content": content, "draft_id": draft_id, "expected_version": expected_version}, version=version)
            if not new:
                return self._view(row)
            if draft_id:
                draft = self._draft(db, actor, connection_id, draft_id)
                if expected_version != draft["current_version"]:
                    raise WCEError("VERSION_CONFLICT")
                previous_version = draft["current_version"]
                db.execute("UPDATE drafts SET current_version=? WHERE id=?", (version, draft_id))
            elif expected_version is not None:
                raise WCEError("INVALID_INPUT")
            else:
                db.execute("INSERT INTO drafts VALUES(?,?,?,?)", (local_id, actor.tenant_id, connection_id, version))
            db.execute("INSERT INTO versions VALUES(?,?,?,?,NULL)", (version, local_id, canonical(content), content_digest))
            # Durable attempt identity permits exact recovery after a lost
            # response. It is not evidence that the platform write succeeded.
            db.execute("UPDATE operations SET result=? WHERE id=?",
                       (canonical({"draft_id": local_id, "version": version, "content_digest": content_digest}), row["id"]))
            row = db.execute("SELECT * FROM operations WHERE id=?", (row["id"],)).fetchone()
            context = self._draft_context(db, actor, conn, local_id, version, content_digest, material_ids, row["id"])
        def complete(db, ref):
            db.execute("UPDATE versions SET platform_ref=? WHERE id=?", (ref, version))
            return {"draft_id": local_id, "version": version, "content_digest": content_digest}
        def guard(db):
            current = self._authorize(db, actor, connection_id, Capability.DRAFT)
            if current["generation"] != row["generation"]:
                raise WCEError("AUTHORIZATION_CHANGED")
            self._materials(db, actor, connection_id, material_ids)
        def restore_rejected_update(db):
            if previous_version is not None:
                db.execute("UPDATE drafts SET current_version=? WHERE id=? AND current_version=?",
                           (previous_version, local_id, version))
        return self._perform(row, lambda: self.adapter.bind_draft(context).save_draft(connection_id, content, self._credential(conn)),
                             complete, guard, restore_rejected_update)

    def _draft(self, db, actor, connection_id, draft_id):
        row = db.execute("SELECT * FROM drafts WHERE id=? AND tenant=? AND connection=?",
                         (draft_id, actor.tenant_id, connection_id)).fetchone()
        if row is None:
            raise WCEError("DRAFT_UNAVAILABLE")
        return row

    def _version(self, db, actor, connection_id, draft_id, version):
        draft = self._draft(db, actor, connection_id, draft_id)
        if draft["current_version"] != version:
            raise WCEError("VERSION_CONFLICT")
        row = db.execute("SELECT * FROM versions WHERE id=? AND draft=?", (version, draft_id)).fetchone()
        if row is None or row["platform_ref"] is None:
            raise WCEError("DRAFT_UNAVAILABLE")
        self._materials(db, actor, connection_id, json.loads(row["content"])["material_ids"])
        return row

    def read_draft(self, actor: Actor, connection_id: str, draft_id: str):
        with self.db.transaction() as db:
            conn = self._authorize(db, actor, connection_id, Capability.READ_DRAFT)
            draft = self._draft(db, actor, connection_id, draft_id)
            version = self._version(db, actor, connection_id, draft_id, draft["current_version"])
            context = self._draft_context(db, actor, conn, draft_id, version["id"], version["digest"],
                                          json.loads(version["content"])["material_ids"])
        try:
            remote = self.adapter.bind_draft(context).read_draft(connection_id, version["platform_ref"], self._credential(conn))
            remote_digest = digest(remote)
        except Exception:
            # Preserve authorization failures observed by the new durable wire
            # guard, while keeping arbitrary adapter exception text redacted.
            context.registry_guard("draft.get")
            raise WCEError("ADAPTER_READ_FAILED") from None
        if remote_digest != version["digest"]:
            raise WCEError("DRAFT_READBACK_MISMATCH")
        with self.db.transaction() as db:
            current = self._authorize(db, actor, connection_id, Capability.READ_DRAFT)
            if current["generation"] != conn["generation"]:
                raise WCEError("AUTHORIZATION_CHANGED")
            self._version(db, actor, connection_id, draft_id, version["id"])
        return {"draft_id": draft_id, "version": version["id"], "content": remote,
                "content_digest": version["digest"], "transport": "mock", "evidence": "local_verified"} | self.evidence()

    def _intent_view(self, row, content_digest):
        return {"intent_id": row["id"], "action": row["kind"], "connection_id": row["connection"],
                "draft_id": row["draft"], "version": row["version"], "content_digest": content_digest,
                "targets": json.loads(row["targets"]), "expires_at": row["expires"],
                "authorization_generation": row["generation"], "binding": row["binding"],
                "confirmed": bool(row["confirmed"]), "transport": "mock"} | self.evidence()

    def _preview_required(self, db, actor, conn, version):
        preview = db.execute("SELECT id FROM operations WHERE tenant=? AND principal=? AND connection=? AND version=? AND kind=? AND state=? AND generation=?",
                             (actor.tenant_id, actor.principal_id, conn["id"], version, Capability.PREVIEW,
                              PublicationState.SUCCEEDED, conn["generation"])).fetchone()
        if preview is None:
            raise WCEError("PREVIEW_REQUIRED")

    def prepare_action(self, actor: Actor, connection_id: str, draft_id: str, version: str,
                       action: str, targets: list[str] | None = None, expires_in=300):
        if action not in (Capability.PREVIEW, Capability.PUBLISH):
            raise WCEError("ACTION_NOT_IMPLEMENTED")
        ttl(expires_in, 900)
        if action == Capability.PREVIEW:
            if not isinstance(targets, list) or not 1 <= len(targets) <= 5:
                raise WCEError("INVALID_TARGETS")
            targets = sorted(set(text(t, 128) for t in targets))
        else:
            if targets is not None:
                raise WCEError("PUBLICATION_TARGET_IS_FIXED")
            targets = ["public_article"]
        with self.db.transaction(write=True) as db:
            conn = self._authorize(db, actor, connection_id, Capability(action))
            if action == Capability.PREVIEW and not set(targets).issubset(json.loads(conn["preview_targets"])):
                raise WCEError("TARGET_NOT_AUTHORIZED")
            content = self._version(db, actor, connection_id, draft_id, version)
            if action == Capability.PUBLISH:
                self._preview_required(db, actor, conn, version)
            else:
                unresolved = self._unresolved(db, actor, conn, Capability.PREVIEW)
                if unresolved:
                    raise WCEError("UNRESOLVED_OPERATION")
            intent_id = uuid4().hex
            expires = self.clock() + expires_in
            binding = digest({"actor": actor.__dict__, "connection": connection_id, "generation": conn["generation"],
                              "action": action, "draft": draft_id, "version": version, "digest": content["digest"],
                              "targets": targets, "expires": expires})
            db.execute("INSERT INTO intents(id,tenant,principal,client,session,connection,generation,kind,draft,version,targets,expires,binding) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)",
                       (intent_id, actor.tenant_id, actor.principal_id, actor.client_id, actor.session_id,
                        connection_id, conn["generation"], action, draft_id, version, canonical(targets), expires, binding))
            return self._intent_view(db.execute("SELECT * FROM intents WHERE id=?", (intent_id,)).fetchone(), content["digest"])

    def _intent(self, db, actor, intent_id):
        row = db.execute("SELECT * FROM intents WHERE id=? AND tenant=? AND principal=? AND client=? AND session=?",
                         (intent_id, actor.tenant_id, actor.principal_id, actor.client_id, actor.session_id)).fetchone()
        if row is None:
            raise WCEError("INTENT_UNAVAILABLE")
        conn = self._authorize(db, actor, row["connection"], Capability(row["kind"]))
        if row["generation"] != conn["generation"] or row["expires"] <= self.clock():
            raise WCEError("CONFIRMATION_EXPIRED")
        version = self._version(db, actor, conn["id"], row["draft"], row["version"])
        if row["kind"] == Capability.PREVIEW and not set(json.loads(row["targets"])).issubset(json.loads(conn["preview_targets"])):
            raise WCEError("TARGET_NOT_AUTHORIZED")
        if row["kind"] == Capability.PUBLISH:
            self._preview_required(db, actor, conn, row["version"])
        return row, conn, version

    def confirm_action(self, actor: Actor, intent_id: str, binding: str):
        """Trusted operator/host confirmation; deliberately absent from model tools."""
        text(binding, 128)
        with self.db.transaction(write=True) as db:
            row, conn, version = self._intent(db, actor, intent_id)
            if not hmac.compare_digest(binding, row["binding"]):
                raise WCEError("CONFIRMATION_BINDING_MISMATCH")
            db.execute("UPDATE intents SET confirmed=1 WHERE id=?", (intent_id,))
            return {"intent_id": intent_id, "confirmed": True, "transport": "mock"} | self.evidence()

    def execute_action(self, actor: Actor, intent_id: str, request_key: str):
        with self.db.transaction(write=True) as db:
            intent, conn, version = self._intent(db, actor, intent_id)
            if not intent["confirmed"]:
                raise WCEError("CONFIRMATION_REQUIRED")
            if intent["operation_id"] is not None:
                bound_operation = db.execute("SELECT * FROM operations WHERE id=?", (intent["operation_id"],)).fetchone()
                if request_key != bound_operation["request_key"]:
                    raise WCEError("IDEMPOTENCY_CONFLICT")
                return self._view(bound_operation)
            targets = tuple(json.loads(intent["targets"]))
            row, new = self._claim(db, actor, conn, intent["kind"], request_key,
                                   {"version": intent["version"], "digest": version["digest"], "targets": targets,
                                    "authorization_generation": conn["generation"]}, intent["version"], targets)
            db.execute("UPDATE intents SET operation_id=? WHERE id=?", (row["id"], intent_id))
            if not new:
                return self._view(row)
        if intent["kind"] == Capability.PREVIEW:
            callback = lambda: self.adapter.preview(conn["id"], version["platform_ref"], targets, self._credential(conn))
        else:
            callback = lambda: self.adapter.submit_publication(conn["id"], version["platform_ref"], self._credential(conn))
        return self._perform(row, callback, guard=lambda db: self._intent(db, actor, intent_id))

    def operation(self, actor: Actor, connection_id: str, operation_id: str):
        with self.db.transaction() as db:
            conn = self._visible(db, actor, connection_id)
            if not self.lifecycle.registry(db, conn["id"])["managed"]:
                self._authorize(db, actor, connection_id)
            row = db.execute("SELECT * FROM operations WHERE id=? AND tenant=? AND principal=? AND connection=?",
                             (operation_id, actor.tenant_id, actor.principal_id, connection_id)).fetchone()
            if row is None:
                raise WCEError("OPERATION_UNAVAILABLE")
            return self._view(row)

    def poll_publication(self, actor: Actor, connection_id: str, operation_id: str):
        with self.db.transaction() as db:
            conn = self._authorize(db, actor, connection_id, Capability.STATUS)
            row = db.execute("SELECT * FROM operations WHERE id=? AND tenant=? AND principal=? AND connection=? AND kind=?",
                             (operation_id, actor.tenant_id, actor.principal_id, connection_id, Capability.PUBLISH)).fetchone()
            if row is None or row["generation"] != conn["generation"]:
                raise WCEError("OPERATION_UNAVAILABLE")
            if row["state"] in (PublicationState.SUCCEEDED, PublicationState.FAILED) or row["platform_ref"] is None:
                return self._view(row)
        state = PublicationState.UNKNOWN
        try:
            status = self.adapter.publication_status(connection_id, row["platform_ref"], self._credential(conn))
            if isinstance(status, Status) and isinstance(status.state, PublicationState):
                state = status.state
        except Exception:
            pass
        with self.db.transaction(write=True) as db:
            # Recheck current authorization after an asynchronous read boundary.
            current = self._authorize(db, actor, connection_id, Capability.STATUS)
            if current["generation"] != conn["generation"]:
                raise WCEError("AUTHORIZATION_CHANGED")
            latest = db.execute("SELECT * FROM operations WHERE id=?", (operation_id,)).fetchone()
            if latest["state"] not in (PublicationState.SUCCEEDED, PublicationState.FAILED):
                if latest["state"] == PublicationState.PROCESSING and state == PublicationState.SUBMITTED:
                    state = PublicationState.PROCESSING
                db.execute("UPDATE operations SET state=? WHERE id=?", (state, operation_id))
            return self._view(db.execute("SELECT * FROM operations WHERE id=?", (operation_id,)).fetchone())
