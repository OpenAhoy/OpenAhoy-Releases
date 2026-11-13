"""Explicit synthetic fixture and vertical workflow, with two logical clients."""
from uuid import uuid4

from .contracts import Actor, Capability, CapabilityState, Connection
from .service import OfficialAccountService
from .tools import ToolRouter
from .storage import BUSINESS_TABLES

ACTORS = {
    "demo-session-a": Actor("tenant-a", "editor-a", "computer-a", "demo-session-a"),
    "demo-session-a2": Actor("tenant-a", "editor-a", "computer-b", "demo-session-a2"),
    "demo-session-b": Actor("tenant-b", "editor-b", "computer-c", "demo-session-b"),
}


def seed(service: OfficialAccountService):
    with service.db.transaction() as db:
        count = db.execute("SELECT count(*) FROM connections").fetchone()[0]
        existing = {r["id"] for r in db.execute("SELECT id FROM sessions")}
        nonempty = any(db.execute(f"SELECT 1 FROM {table} LIMIT 1").fetchone() for table in BUSINESS_TABLES)
    if count:
        if set(ACTORS).issubset(existing):
            return
        raise ValueError("Refusing to seed nonempty state with synthetic identities")
    if nonempty:
        raise ValueError("Refusing to seed nonempty state with synthetic identities")
    capabilities = {cap: CapabilityState.AVAILABLE for cap in Capability if cap != Capability.MASS_SEND}
    capabilities[Capability.MASS_SEND] = CapabilityState.NOT_IMPLEMENTED
    expires = service.clock() + 86400
    for connection_id, actor in [("oa-a", ACTORS["demo-session-a"]), ("oa-a-second", ACTORS["demo-session-a"]), ("oa-b", ACTORS["demo-session-b"])]:
        service.register_connection(Connection(connection_id, actor.tenant_id, "synthetic_official_account",
                                               "synthetic_qualified", "fake-reference", capabilities, expires), actor.principal_id)
    for actor in ACTORS.values():
        service.register_session(actor, ("oa-a", "oa-a-second") if actor.tenant_id == "tenant-a" else ("oa-b",), expires)


def workflow(service: OfficialAccountService):
    seed(service)
    actor = ACTORS["demo-session-a"]
    router = ToolRouter(service, actor)
    prefix = uuid4().hex
    material = router.call("materials.add", {"connection_id": "oa-a", "content": "SYNTHETIC illustration",
                                              "request_key": prefix + "-material"})
    draft = router.call("drafts.save", {"connection_id": "oa-a", "title": "WCE offline example",
                                        "body": "Synthetic article. Nothing is sent to WeChat.",
                                        "material_ids": [material["result"]["material_id"]], "request_key": prefix + "-draft"})
    details = draft["result"]
    readback = router.call("drafts.read", {"connection_id": "oa-a", "draft_id": details["draft_id"]})
    preview_intent = router.call("actions.prepare", {"connection_id": "oa-a", "draft_id": details["draft_id"],
                                                      "version": details["version"], "action": Capability.PREVIEW,
                                                      "targets": ["mock-reader"]})
    # Simulates trusted operator approval; model-facing tools have no approval tool.
    service.confirm_action(actor, preview_intent["intent_id"], preview_intent["binding"])
    preview = router.call("actions.execute", {"intent_id": preview_intent["intent_id"], "request_key": prefix + "-preview"})
    publish_intent = router.call("actions.prepare", {"connection_id": "oa-a", "draft_id": details["draft_id"],
                                                      "version": details["version"], "action": Capability.PUBLISH})
    service.confirm_action(actor, publish_intent["intent_id"], publish_intent["binding"])
    submitted = router.call("actions.execute", {"intent_id": publish_intent["intent_id"], "request_key": prefix + "-publish"})
    other = ToolRouter(service, ACTORS["demo-session-a2"])
    polling = {"connection_id": "oa-a", "operation_id": submitted["operation_id"]}
    processing = other.call("publications.poll", polling)
    complete = other.call("publications.poll", polling)
    return {"transport": "mock", "platform_verified": False, "operator_approval": "synthetic",
            "capabilities": router.call("connections.capabilities", {"connection_id": "oa-a"}),
            "material": material, "draft": draft, "readback": readback, "preview": preview,
            "publication": submitted, "processing": processing, "final": complete,
            "mass_send": "NOT_IMPLEMENTED", "two_clients": "same_mock_backend"}


def seed_lifecycle(service):
    """Trusted synthetic binding of two accounts per tenant, only on empty DB."""
    from .connection_lifecycle import SyntheticAccount
    with service.db.transaction() as db:
        if any(db.execute(f"SELECT 1 FROM {table} LIMIT 1").fetchone()
               for table in BUSINESS_TABLES):
            raise ValueError("Refusing to overwrite existing lifecycle state")
    now = service.clock()
    for actor in ACTORS.values():
        service.register_session(actor, (), now + 86400)
    for tenant, session in (("a", "demo-session-a"), ("b", "demo-session-b")):
        actor = ACTORS[session]
        for suffix in ("", "-second"):
            account = SyntheticAccount("shared-account" + suffix)
            pending = service.lifecycle.begin_binding(actor, account, "oa-" + tenant + suffix,
                                                     now + 43200, now + 21600, now + 3600)
            service.lifecycle.complete_binding(actor, pending["binding_id"], pending["state"], account)
    # A second trusted local client gets an explicitly selected allowlist;
    # neither a pending callback nor a model request modifies other sessions.
    with service.db.transaction(write=True) as db:
        from .service import canonical
        db.execute("UPDATE sessions SET connections=? WHERE id=?",
                   (canonical(("oa-a", "oa-a-second")), "demo-session-a2"))


def lifecycle_workflow(service):
    """Local executable binding/rotation/scope/revoke/reconnect demonstration."""
    from .connection_lifecycle import SyntheticAccount
    seed_lifecycle(service)
    actor = ACTORS["demo-session-a"]
    before = service.profiles(actor)
    rotated = service.lifecycle.renew_token(actor, "oa-a")
    service.lifecycle.change_authorization(actor, "oa-a", SyntheticAccount(
        "shared-account", authorized_capabilities=(Capability.READ_DRAFT, Capability.STATUS)))
    narrowed = service.profiles(actor)
    service.lifecycle.revoke("oa-a", actor)
    revoked = service.profiles(actor)
    pending = service.lifecycle.begin_binding(actor, SyntheticAccount("shared-account"), "oa-a-reconnected",
                                             service.clock() + 43200, service.clock() + 21600, service.clock() + 3600)
    restored = service.lifecycle.complete_binding(actor, pending["binding_id"], pending["state"], SyntheticAccount("shared-account"))
    return {"before": before, "rotation": rotated, "narrowed": narrowed, "revoked": revoked,
            "restored": restored, "tenant_b": service.profiles(ACTORS["demo-session-b"])}
