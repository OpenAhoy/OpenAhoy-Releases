"""Trusted, synthetic connection administration. No OAuth, HTTP or secret input.

The existing connections/grants/sessions remain the execution authority. The
registry supplies immutable account identity and independently accepted leases.
These Python APIs are intentionally absent from model tools.
"""
from dataclasses import dataclass
import hmac
import json
import math
from uuid import uuid4

from .contracts import Actor, Capability, CapabilityState, WCEError
from .service import canonical, digest, text, ttl
from .storage import register_legacy_profile

CALLBACK = "https://fixture.invalid/wce/synthetic-callback"
EVIDENCE = {"transport": "mock", "mode": "test", "connected": False,
            "platform_verified": False, "evidence": "synthetic_connection_fixture"}


def deadline(value, now):
    if (isinstance(value, bool) or not isinstance(value, (int, float))
            or not math.isfinite(value) or value <= now):
        raise WCEError("INVALID_DEADLINE")
    return value


def capabilities(values):
    if not isinstance(values, (list, tuple)) or any(not isinstance(v, str) or v not in set(Capability) for v in values):
        raise WCEError("INVALID_CAPABILITIES")
    return sorted(set(values))


@dataclass(frozen=True)
class SyntheticAccount:
    """Explicit trusted test input, never an authorization received from Tencent."""
    account_id: str
    account_capabilities: tuple[str, ...] = tuple(Capability)
    authorized_capabilities: tuple[str, ...] = tuple(Capability)
    verified: bool = True
    namespace: str = "wce.synthetic.third_party"

    def payload(self):
        text(self.account_id, 128)
        if self.namespace != "wce.synthetic.third_party" or type(self.verified) is not bool:
            raise WCEError("SYNTHETIC_ACCOUNT_REQUIRED")
        return {"account_id": self.account_id, "namespace": self.namespace,
                "account_capabilities": capabilities(self.account_capabilities),
                "authorized_capabilities": capabilities(self.authorized_capabilities), "verified": self.verified}


@dataclass(frozen=True)
class RenewalRequest:
    actor: Actor
    connection_id: str
    resource_id: str
    generation: int
    epoch: int
    token_revision: int
    guard_digest: str


@dataclass(frozen=True)
class SyntheticRenewal:
    request: RenewalRequest
    expires_at: float
    accepted: bool = True


class FixtureConnections:
    def __init__(self, service):
        self.service = service
        with service.db.transaction(write=True) as db:
            missing = db.execute("SELECT c.* FROM connections c LEFT JOIN connection_registry r "
                                 "ON r.connection=c.id WHERE r.connection IS NULL").fetchall()
            if missing:
                raise WCEError("CONNECTION_STATE_INCOMPLETE")
            invalid = db.execute("SELECT 1 FROM connection_registry r LEFT JOIN connections c ON c.id=r.connection "
                                 "LEFT JOIN account_profiles p ON p.id=r.profile "
                                 "WHERE c.id IS NULL OR p.id IS NULL OR c.tenant!=p.tenant LIMIT 1").fetchone()
            if invalid:
                raise WCEError("CONNECTION_STATE_INCOMPLETE")
            if db.execute("SELECT 1 FROM operations o LEFT JOIN connections c ON c.id=o.connection "
                          "WHERE c.id IS NULL OR c.tenant!=o.tenant LIMIT 1").fetchone():
                raise WCEError("CONNECTION_STATE_INCOMPLETE")

    def register_legacy(self, db, conn, owner):
        register_legacy_profile(db, conn, owner)

    def registry(self, db, connection_id):
        row = db.execute("SELECT r.*,p.tenant,p.namespace,p.account,p.resource,p.owner,p.epoch "
                         "FROM connection_registry r JOIN account_profiles p ON p.id=r.profile "
                         "WHERE r.connection=?", (connection_id,)).fetchone()
        if row is None:
            raise WCEError("CONNECTION_STATE_INCOMPLETE")
        return row

    def _session(self, db, actor):
        row = db.execute("SELECT * FROM sessions WHERE id=? AND tenant=? AND principal=? AND client=?",
                         (actor.session_id, actor.tenant_id, actor.principal_id, actor.client_id)).fetchone()
        if row is None or not row["active"] or row["expires"] <= self.service.clock():
            raise WCEError("SESSION_INVALID")
        return row

    def _owner(self, db, actor, connection_id):
        self._session(db, actor)
        row = self.registry(db, connection_id)
        if row["tenant"] != actor.tenant_id or row["owner"] != actor.principal_id:
            raise WCEError("ACCESS_DENIED")
        return row

    def _actor_digest(self, db, actor, connection_id):
        session = self._session(db, actor)
        grant = db.execute("SELECT * FROM grants WHERE connection=? AND principal=?",
                           (connection_id, actor.principal_id)).fetchone()
        return digest({"session": dict(session), "grant": dict(grant) if grant else None})

    def _states(self, account):
        own, authorized = set(account["account_capabilities"]), set(account["authorized_capabilities"])
        return {cap: (CapabilityState.NOT_IMPLEMENTED if cap == Capability.MASS_SEND else
                      CapabilityState.UNVERIFIED if not account["verified"] else
                      CapabilityState.NOT_OPEN if cap not in own else
                      CapabilityState.UNAUTHORIZED if cap not in authorized else CapabilityState.AVAILABLE)
                for cap in Capability}

    def begin_binding(self, actor, account, connection_id, authorization_expires, grant_expires,
                      token_expires, expires_in=300):
        if not isinstance(account, SyntheticAccount):
            raise WCEError("SYNTHETIC_ACCOUNT_REQUIRED")
        payload = account.payload()
        text(connection_id, 128)
        ttl(expires_in, 900)
        now = self.service.clock()
        for value in (authorization_expires, grant_expires, token_expires):
            deadline(value, now)
        payload |= {"authorization_expires": authorization_expires, "grant_expires": grant_expires,
                    "token_expires": token_expires, "callback": CALLBACK}
        with self.service.db.transaction(write=True) as db:
            self._session(db, actor)
            profile = db.execute("SELECT * FROM account_profiles WHERE tenant=? AND namespace=? AND account=?",
                                 (actor.tenant_id, account.namespace, account.account_id)).fetchone()
            if profile is None:
                profile_id = uuid4().hex
                db.execute("INSERT INTO account_profiles VALUES(?,?,?,?,?,?,0)",
                           (profile_id, actor.tenant_id, account.namespace, account.account_id, uuid4().hex, actor.principal_id))
                profile = db.execute("SELECT * FROM account_profiles WHERE id=?", (profile_id,)).fetchone()
            if profile["owner"] != actor.principal_id:
                raise WCEError("ACCESS_DENIED")
            current = db.execute("SELECT * FROM connections WHERE id=?", (connection_id,)).fetchone()
            if current:
                registry = self._owner(db, actor, connection_id)
                if registry["profile"] != profile["id"]:
                    raise WCEError("CONNECTION_IDENTITY_IMMUTABLE")
            binding_id, nonce = uuid4().hex, uuid4().hex
            db.execute("INSERT INTO binding_transactions VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,0)",
                       (binding_id, actor.tenant_id, actor.principal_id, actor.client_id, actor.session_id,
                        nonce, now + expires_in, connection_id, profile["id"],
                        current["generation"] if current else 0, profile["epoch"],
                        self._actor_digest(db, actor, connection_id), canonical(payload)))
            return {"binding_id": binding_id, "state": nonce, "callback_target": CALLBACK,
                    "expires_at": now + expires_in} | EVIDENCE

    def complete_binding(self, actor, binding_id, state, account, callback_target=CALLBACK):
        if (not isinstance(account, SyntheticAccount) or not isinstance(binding_id, str)
                or not isinstance(state, str) or not state.isascii() or len(state) != 32):
            raise WCEError("BINDING_INVALID")
        actual = account.payload()
        with self.service.db.transaction(write=True) as db:
            self._session(db, actor)
            txn = db.execute("SELECT * FROM binding_transactions WHERE id=? AND tenant=? AND principal=? "
                             "AND client=? AND session=?", (binding_id, actor.tenant_id, actor.principal_id,
                                                          actor.client_id, actor.session_id)).fetchone()
            if (txn is None or txn["used"] or txn["expires"] <= self.service.clock()
                    or not hmac.compare_digest(state, txn["nonce"])):
                raise WCEError("BINDING_INVALID")
            payload = json.loads(txn["payload"])
            profile = db.execute("SELECT * FROM account_profiles WHERE id=? AND tenant=? AND owner=?",
                                 (txn["profile"], actor.tenant_id, actor.principal_id)).fetchone()
            conn = db.execute("SELECT * FROM connections WHERE id=?", (txn["connection"],)).fetchone()
            if (profile is None or profile["epoch"] != txn["expected_epoch"]
                    or (conn["generation"] if conn else 0) != txn["expected_generation"]
                    or self._actor_digest(db, actor, txn["connection"]) != txn["guard_digest"]
                    or callback_target != CALLBACK or payload["callback"] != CALLBACK
                    or any(actual[key] != payload[key] for key in actual)):
                raise WCEError("BINDING_STALE_OR_MISMATCH")
            now = self.service.clock()
            for key in ("authorization_expires", "grant_expires", "token_expires"):
                deadline(payload[key], now)
            # Reauthorization fences all prior aliases. Identity and journals
            # remain immutable, including an already-dispatched UNKNOWN result.
            db.execute("UPDATE connections SET active=0,generation=generation+1 WHERE id IN "
                       "(SELECT connection FROM connection_registry WHERE profile=?)", (profile["id"],))
            db.execute("UPDATE connection_registry SET state='superseded',token_revision=token_revision+1 "
                       "WHERE profile=?", (profile["id"],))
            db.execute("UPDATE account_profiles SET epoch=epoch+1 WHERE id=?", (profile["id"],))
            generation = (conn["generation"] + 1) if conn else profile["epoch"] + 1
            states = self._states(payload)
            values = (txn["connection"], actor.tenant_id, "synthetic_official_account", "synthetic_qualified",
                      "synthetic-fixture-reference", canonical(states), payload["authorization_expires"],
                      generation, 1, "synthetic", canonical(("mock-reader",)))
            if conn:
                db.execute("UPDATE connections SET account_type=?,qualification=?,secret_ref=?,capabilities=?,expires=?,"
                           "generation=?,active=?,evidence=?,preview_targets=? WHERE id=? AND tenant=?",
                           values[2:] + (values[0], values[1]))
                db.execute("UPDATE connection_registry SET managed=1,state=?,token_expires=?,token_revision=token_revision+1,"
                           "account_caps=?,authorized_caps=? WHERE connection=?",
                           ("active" if payload["verified"] else "authorization_unverified", payload["token_expires"],
                            canonical(payload["account_capabilities"]), canonical(payload["authorized_capabilities"]), values[0]))
            else:
                db.execute("INSERT INTO connections VALUES(?,?,?,?,?,?,?,?,?,?,?)", values)
                db.execute("INSERT INTO connection_registry VALUES(?,?,1,?,?,1,?,?)",
                           (values[0], profile["id"], "active" if payload["verified"] else "authorization_unverified",
                            payload["token_expires"], canonical(payload["account_capabilities"]), canonical(payload["authorized_capabilities"])))
            db.execute("INSERT INTO grants VALUES(?,?,?,?) ON CONFLICT(connection,principal) DO UPDATE SET "
                       "capabilities=excluded.capabilities,expires=excluded.expires",
                       (values[0], actor.principal_id, canonical(payload["authorized_capabilities"]), payload["grant_expires"]))
            session = self._session(db, actor)
            selected = sorted(set(json.loads(session["connections"])) | {values[0]})
            db.execute("UPDATE sessions SET connections=? WHERE id=?", (canonical(selected), actor.session_id))
            db.execute("UPDATE binding_transactions SET used=1 WHERE id=?", (binding_id,))
        self._invalidate_profile(profile["id"])
        return self.status(actor, values[0])

    def _invalidate_profile(self, profile_id):
        provider = getattr(self.service.adapter, "provider", None)
        if provider is not None:
            with self.service.db.transaction() as db:
                rows = db.execute("SELECT c.tenant,c.id FROM connections c JOIN connection_registry r "
                                  "ON r.connection=c.id WHERE r.profile=?", (profile_id,)).fetchall()
            for conn in rows:
                provider.invalidate_connection(conn["tenant"], conn["id"])

    def usable(self, db, conn):
        row = self.registry(db, conn["id"])
        if row["managed"]:
            if row["state"] == "reauthorization_required":
                raise WCEError("CONNECTION_REAUTHORIZATION_REQUIRED")
            if row["state"] == "authorization_unverified":
                raise WCEError("CONNECTION_AUTHORIZATION_UNVERIFIED")
            if row["state"] != "active":
                raise WCEError("CONNECTION_REVOKED_OR_EXPIRED")
            if row["token_expires"] <= self.service.clock():
                raise WCEError("TOKEN_EXPIRED")
        return row

    def status(self, actor, connection_id):
        with self.service.db.transaction() as db:
            session = self._session(db, actor)
            conn = db.execute("SELECT * FROM connections WHERE id=? AND tenant=?", (connection_id, actor.tenant_id)).fetchone()
            grant = db.execute("SELECT * FROM grants WHERE connection=? AND principal=?", (connection_id, actor.principal_id)).fetchone()
            if conn is None or connection_id not in json.loads(session["connections"]):
                raise WCEError("ACCESS_DENIED")
            row = self.registry(db, connection_id)
            owner = row["owner"] == actor.principal_id
            allowed = json.loads(grant["capabilities"]) if grant else []
            if not owner and (grant is None or grant["expires"] <= self.service.clock()
                              or not set(allowed).intersection({Capability.READ_DRAFT, Capability.STATUS})):
                raise WCEError("ACCESS_DENIED")
            now = self.service.clock()
            state = row["state"]
            if state == "active" and (not conn["active"] or conn["expires"] <= now):
                state = "authorization_expired" if conn["active"] else "revoked"
            elif state == "active" and row["managed"] and row["token_expires"] <= now:
                state = "token_expired"
            if state == "active" and (grant is None or grant["expires"] <= now):
                state = "grant_expired"
            states = json.loads(conn["capabilities"])
            if grant is None or grant["expires"] <= now:
                states = {cap: CapabilityState.UNAUTHORIZED for cap in Capability}
            else:
                states = {cap: states.get(cap, CapabilityState.NOT_IMPLEMENTED) if cap in allowed
                          else CapabilityState.UNAUTHORIZED for cap in Capability}
            if state in {"revoked", "superseded", "reauthorization_required", "authorization_expired", "token_expired"}:
                states = {cap: CapabilityState.REVOKED if value == CapabilityState.AVAILABLE else value
                          for cap, value in states.items()}
            return {"connection_id": connection_id, "profile_id": row["profile"],
                    "account_id": row["profile"] if row["managed"] else connection_id,
                    "account_type": conn["account_type"], "qualification": conn["qualification"],
                    "state": state, "authorization_generation": conn["generation"], "token_revision": row["token_revision"],
                    "deadlines": {"token": row["token_expires"], "authorization": conn["expires"],
                                  "session": session["expires"], "grant": grant["expires"] if grant else None},
                    "capabilities": states, "identity_evidence": ("synthetic_unverified" if row["state"] == "authorization_unverified"
                                                               else "synthetic_verified") if row["managed"] else "legacy_local_only"} | EVIDENCE

    def renew_token(self, actor, connection_id, loader=None):
        with self.service.db.transaction() as db:
            row = self._owner(db, actor, connection_id)
            conn = self.service._visible(db, actor, connection_id)
            if not row["managed"] or row["state"] != "active" or not conn["active"] or conn["expires"] <= self.service.clock():
                raise WCEError("REAUTHORIZATION_REQUIRED")
            request = RenewalRequest(actor, connection_id, row["resource"], conn["generation"], row["epoch"],
                                     row["token_revision"], self._actor_digest(db, actor, connection_id))
        # No database write lock crosses provider work. This provider is always
        # synthetic; dispatch never calls renewal or performs network refresh.
        try:
            result = loader(request) if loader else SyntheticRenewal(request, self.service.clock() + 600)
            accepted = (isinstance(result, SyntheticRenewal) and result.request == request
                        and type(result.accepted) is bool and result.accepted)
            if accepted:
                deadline(result.expires_at, self.service.clock())
        except Exception:
            accepted = False
        with self.service.db.transaction(write=True) as db:
            current = self._owner(db, actor, connection_id)
            conn = self.service._visible(db, actor, connection_id)
            if (conn["generation"] != request.generation or current["epoch"] != request.epoch
                    or current["token_revision"] != request.token_revision or current["state"] != "active"
                    or conn["expires"] <= self.service.clock() or not conn["active"]
                    or self._actor_digest(db, actor, connection_id) != request.guard_digest):
                raise WCEError("REFRESH_STALE")
            if accepted:
                try:
                    deadline(result.expires_at, self.service.clock())
                except WCEError:
                    accepted = False
            if accepted:
                db.execute("UPDATE connection_registry SET token_expires=?,token_revision=token_revision+1 WHERE connection=?",
                           (result.expires_at, connection_id))
            else:
                self._fence(db, current["profile"], "reauthorization_required")
        self._invalidate_profile(current["profile"])
        return self.status(actor, connection_id) | {"refresh_accepted": accepted}

    def _fence(self, db, profile_id, state):
        db.execute("UPDATE connections SET active=0,generation=generation+1 WHERE id IN "
                   "(SELECT connection FROM connection_registry WHERE profile=?)", (profile_id,))
        db.execute("UPDATE connection_registry SET state=?,token_revision=token_revision+1 WHERE profile=?", (state, profile_id))
        db.execute("UPDATE account_profiles SET epoch=epoch+1 WHERE id=?", (profile_id,))

    def revoke(self, connection_id, actor=None):
        with self.service.db.transaction(write=True) as db:
            row = self._owner(db, actor, connection_id) if actor else self.registry(db, connection_id)
            self._fence(db, row["profile"], "revoked")
        self._invalidate_profile(row["profile"])

    def change_authorization(self, actor, connection_id, account):
        if not isinstance(account, SyntheticAccount):
            raise WCEError("SYNTHETIC_ACCOUNT_REQUIRED")
        payload = account.payload()
        with self.service.db.transaction(write=True) as db:
            row = self._owner(db, actor, connection_id)
            conn = self.service._visible(db, actor, connection_id)
            if (not row["managed"] or row["state"] != "active" or not conn["active"]
                    or conn["expires"] <= self.service.clock() or row["account"] != account.account_id
                    or row["namespace"] != account.namespace):
                raise WCEError("REAUTHORIZATION_REQUIRED")
            db.execute("UPDATE connections SET capabilities=?,generation=generation+1 WHERE id=?",
                       (canonical(self._states(payload)), connection_id))
            db.execute("UPDATE connection_registry SET state=?,account_caps=?,authorized_caps=?,token_revision=token_revision+1 "
                       "WHERE connection=?", ("active" if payload["verified"] else "authorization_unverified",
                                               canonical(payload["account_capabilities"]), canonical(payload["authorized_capabilities"]), connection_id))
            db.execute("UPDATE account_profiles SET epoch=epoch+1 WHERE id=?", (row["profile"],))
        self._invalidate_profile(row["profile"])
        return self.status(actor, connection_id)

    def grant_access(self, owner, connection_id, recipient, granted, expires_at):
        """Trusted fixture collaboration grant; selected recipient session only."""
        allowed = capabilities(granted)
        deadline(expires_at, self.service.clock())
        with self.service.db.transaction(write=True) as db:
            row = self._owner(db, owner, connection_id)
            self.service._authorize(db, owner, connection_id)
            session = self._session(db, recipient)
            if recipient.tenant_id != owner.tenant_id:
                raise WCEError("ACCESS_DENIED")
            db.execute("INSERT INTO grants VALUES(?,?,?,?) ON CONFLICT(connection,principal) DO UPDATE SET "
                       "capabilities=excluded.capabilities,expires=excluded.expires",
                       (connection_id, recipient.principal_id, canonical(allowed), expires_at))
            db.execute("UPDATE sessions SET connections=? WHERE id=?",
                       (canonical(sorted(set(json.loads(session["connections"])) | {connection_id})), recipient.session_id))
            db.execute("UPDATE connections SET generation=generation+1 WHERE id=?", (connection_id,))
            db.execute("UPDATE account_profiles SET epoch=epoch+1 WHERE id=?", (row["profile"],))
            db.execute("UPDATE connection_registry SET token_revision=token_revision+1 WHERE connection=?", (connection_id,))
        self._invalidate_profile(row["profile"])
        return self.status(recipient, connection_id) if set(allowed).intersection({Capability.READ_DRAFT, Capability.STATUS}) else EVIDENCE
