"""Trusted local W04C snapshot -> test-only image multipart preparation.

No transport execution, new credentials, claims or material-ready mapping.
"""
from dataclasses import dataclass, field
import json
import re

from .contracts import Secret, WCEError
from .http_transport import HTTPRequest
from .local_preparation import sha
from .service import canonical, digest
from . import upload_wire


@dataclass(frozen=True)
class PreparedUpload:
    request: HTTPRequest = field(repr=False)
    _descriptor: str = field(repr=False)
    _secret: Secret = field(repr=False)
    _purpose: str
    test_only: bool = True
    executor_integration: str = "UNIMPLEMENTED"

    def summary(self):
        descriptor = json.loads(self._descriptor)
        return {"descriptor": descriptor, "descriptor_digest": digest(descriptor),
                "body_bytes": len(self.request.body), "body_sha256": sha(self.request.body),
                "state": "PROTOCOL_PREPARATION_ONLY", "test_only": True,
                "executor_integration": "UNIMPLEMENTED", "platform_verified": False,
                "platform_ready": False, "platform_state": "NEEDS_PLATFORM_MATERIALS"}

    def parse_response(self, response):
        return upload_wire.parse_response(self._purpose, response, self._secret)


class UploadPreparer:
    def __init__(self, service):
        self.service = service

    def _snapshot(self, db, actor, connection, bundle, version, content_digest, slot):
        local = self.service.local
        binding, fence = local._guard(db, actor, connection, True)
        manifest, actual_digest = local._bundle(db, binding, bundle, version)
        if actual_digest != content_digest:
            raise WCEError("UPLOAD_CONTENT_MISMATCH")
        latest = db.execute("SELECT version FROM prepared_versions WHERE bundle=? AND tenant=? AND principal=? "
                            "AND connection=? AND resource=? ORDER BY revision DESC LIMIT 1",
                            (bundle,) + local._scope(binding)).fetchone()
        if latest is None or latest["version"] != version:
            raise WCEError("UPLOAD_VERSION_STALE")
        created = manifest["binding"]
        if created["generation"] != binding["generation"] or created["epoch"] != binding["epoch"]:
            raise WCEError("ASSET_AUTHORIZATION_STALE")
        if slot == "cover":
            asset_ref = manifest["article"]["cover_asset_ref"]
            role, purpose = "cover", "permanent_cover"
        else:
            images = [b for b in manifest["article"]["blocks"] if b["type"] == "image" and b["slot"] == slot]
            if len(images) != 1:
                raise WCEError("INVALID_UPLOAD_SLOT")
            asset_ref = images[0]["asset_ref"]
            role, purpose = "body", "article_body"
        metadata, data, _ = local._asset(db, binding, asset_ref, current=True, role=role)
        registry = self.service.lifecycle.registry(db, connection)
        descriptor = {"schema": 1, "bundle_id": bundle, "version": version,
                      "content_digest": content_digest, "slot": slot, "purpose": purpose,
                      "binding": binding, "token_revision": registry["token_revision"], "asset": metadata,
                      "path": upload_wire.ENDPOINTS[purpose], "official_source": upload_wire.SOURCE_URLS[purpose],
                      "official_source_sha256": upload_wire.SOURCE_HASHES[purpose]}
        secret_ref = db.execute("SELECT secret_ref FROM connections WHERE id=?", (connection,)).fetchone()[0]
        return canonical(descriptor), data, fence, secret_ref

    def prepare(self, actor, connection_id, bundle_id, version, content_digest, slot):
        if (not isinstance(content_digest, str) or re.fullmatch(r"[a-f0-9]{64}", content_digest) is None
                or not isinstance(slot, str) or re.fullmatch(r"[A-Za-z0-9_-]{1,64}", slot) is None):
            raise WCEError("INVALID_UPLOAD_CONTEXT")
        with self.service.db.transaction(write=True) as db:
            descriptor, data, fence, secret_ref = self._snapshot(
                db, actor, connection_id, bundle_id, version, content_digest, slot)
        context = json.loads(descriptor)
        try:
            secret = self.service.secrets.get(actor.tenant_id, connection_id, secret_ref)
        except Exception:
            raise WCEError("UPLOAD_SECRET_UNAVAILABLE") from None
        if upload_wire.contains_secret(context, secret):
            raise WCEError("UPLOAD_SECRET_CONTAMINATION")
        request = upload_wire.build_request(context["purpose"], context["asset"]["declared_type"], data, secret)
        prepared = PreparedUpload(request, descriptor, secret, context["purpose"])
        if upload_wire.contains_secret(prepared.summary(), secret):
            raise WCEError("UPLOAD_SECRET_CONTAMINATION")
        with self.service.db.transaction(write=True) as db:
            self.service.local._final(db, actor, connection_id, fence, True)
            current, current_data, _, current_secret_ref = self._snapshot(
                db, actor, connection_id, bundle_id, version, content_digest, slot)
            if current != descriptor or current_data != data or current_secret_ref != secret_ref:
                raise WCEError("UPLOAD_CONTEXT_CHANGED")
            # Final gate after full package/BLOB checks, not before their work.
            self.service.local._final(db, actor, connection_id, fence, True)
        return prepared
