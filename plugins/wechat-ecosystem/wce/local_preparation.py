"""Actual local bytes, immutable news preparations; no platform side effects.

    Trusted management primitives; W04G wraps them in a separate host namespace.
    Images receive signature checks only: no decoding, preview or upload claim.
"""
import hashlib
import json
import re
from uuid import uuid4

from .bounded_file import FileSource, MAX_ASSET_BYTES
from .contracts import Actor, Capability, WCEError
from .service import canonical, digest

MAX_IMAGES = 4
MAX_BLOCKS = 64
MAX_TEXT_BYTES = 64 * 1024
MAX_PACKAGE_BYTES = 8 * 1024 * 1024
MAX_MANIFEST_BYTES = 128 * 1024
IMAGE_CHECK = "SIGNATURE_ONLY_NOT_DECODED"


def sha(data):
    return hashlib.sha256(data).hexdigest()


def ref(value, kind):
    if not isinstance(value, str) or re.fullmatch(r"local-" + kind + r"-[a-f0-9]{32}", value) is None:
        raise WCEError("INVALID_PREPARATION")
    return value


def plain(value, maximum, allow_empty=False):
    if (not isinstance(value, str) or len(value) > maximum
            or (not allow_empty and not value.strip())):
        raise WCEError("INVALID_PREPARATION")
    try:
        size = len(value.encode("utf-8"))
    except UnicodeError:
        raise WCEError("INVALID_PREPARATION") from None
    if size > maximum or any(ord(c) < 32 and c not in "\n\t" for c in value):
        raise WCEError("INVALID_PREPARATION")
    return value


def image_check(data, declared_type):
    valid = ((declared_type == "image/png" and len(data) >= 20
              and data.startswith(b"\x89PNG\r\n\x1a\n") and data.endswith(b"\x00\x00\x00\x00IEND\xaeB`\x82"))
             or (declared_type == "image/jpeg" and len(data) >= 5
                 and data.startswith(b"\xff\xd8\xff") and data.endswith(b"\xff\xd9")))
    if not valid:
        raise WCEError("INVALID_LOCAL_IMAGE")


class LocalPreparations:
    def __init__(self, service):
        self.service = service

    def _guard(self, db, actor, connection_id, write=False):
        if not isinstance(actor, Actor):
            raise WCEError("ACCESS_DENIED")
        plain(connection_id, 128)
        conn = self.service._authorize(db, actor, connection_id,
                                       Capability.MATERIAL if write else Capability.READ_DRAFT)
        if write:
            self.service._authorize(db, actor, connection_id, Capability.DRAFT)
        registry = self.service.lifecycle.registry(db, connection_id)
        binding = {"tenant": actor.tenant_id, "principal": actor.principal_id, "connection": connection_id,
                   "resource": registry["resource"], "generation": conn["generation"], "epoch": registry["epoch"]}
        fence = digest({"connection": dict(conn), "registry": dict(registry),
                        "actor": self.service.lifecycle._actor_digest(db, actor, connection_id)})
        return binding, fence

    def _final(self, db, actor, connection_id, fence, write=False):
        binding, current = self._guard(db, actor, connection_id, write)
        if current != fence:
            raise WCEError("AUTHORIZATION_CHANGED")
        return binding

    def _evidence(self):
        return self.service.evidence() | {"input_evidence": "ACTUAL_LOCAL_BYTES", "image_check": IMAGE_CHECK,
                                          "state": "LOCAL_PREPARED", "platform_state": "NEEDS_PLATFORM_MATERIALS",
                                          "platform_ready": False}

    @staticmethod
    def _scope(binding):
        return tuple(binding[k] for k in ("tenant", "principal", "connection", "resource"))

    def accept_asset(self, actor, connection_id, source: FileSource, relative_path, role, declared_type):
        if (not isinstance(source, FileSource) or not isinstance(role, str) or role not in {"cover", "body"}
                or not isinstance(declared_type, str) or declared_type not in {"image/png", "image/jpeg"}):
            raise WCEError("INVALID_PREPARATION")
        with self.service.db.transaction() as db:
            binding, fence = self._guard(db, actor, connection_id, True)
        data = source.read(relative_path)
        if not isinstance(data, bytes) or not 0 < len(data) <= MAX_ASSET_BYTES:
            raise WCEError("LOCAL_FILE_LIMIT")
        image_check(data, declared_type)
        with self.service.db.transaction(write=True) as db:
            self._final(db, actor, connection_id, fence, True)
            metadata = self._insert_asset(db, binding, data, role, declared_type)
            self._final(db, actor, connection_id, fence, True)
        return metadata | self._evidence()

    def _insert_asset(self, db, binding, data, role, declared_type):
        """Transaction-local core; trusted callers own admission and final gates."""
        if (type(data) is not bytes or not 0 < len(data) <= MAX_ASSET_BYTES
                or role not in {"cover", "body"} or declared_type not in {"image/png", "image/jpeg"}):
            raise WCEError("INVALID_PREPARATION")
        image_check(data, declared_type)
        asset_ref = "local-asset-" + uuid4().hex
        metadata = {"asset_ref": asset_ref, "role": role, "declared_type": declared_type,
                    "size": len(data), "sha256": sha(data)}
        db.execute("INSERT INTO local_assets VALUES(?,?,?,?,?,?,?,?,?,?,?,?)",
                   (asset_ref,) + self._scope(binding) + (binding["generation"], binding["epoch"], role,
                   declared_type, len(data), metadata["sha256"], data))
        return metadata

    def _asset(self, db, binding, asset_ref, current=False, role=None):
        ref(asset_ref, "asset")
        row = db.execute("SELECT id,tenant,principal,connection,resource,generation,epoch,role,declared_type,size,digest,"
                         "length(data) AS stored_size FROM local_assets WHERE id=? AND tenant=? AND principal=? "
                         "AND connection=? AND resource=?", (asset_ref,) + self._scope(binding)).fetchone()
        if row is None:
            raise WCEError("ACCESS_DENIED")
        if (type(row["size"]) is not int or not 0 < row["size"] <= MAX_ASSET_BYTES
                or row["stored_size"] != row["size"]):
            raise WCEError("PREPARATION_CORRUPT")
        if role is not None and row["role"] != role:
            raise WCEError("ASSET_ROLE_MISMATCH")
        if current and (row["generation"] != binding["generation"] or row["epoch"] != binding["epoch"]):
            raise WCEError("ASSET_AUTHORIZATION_STALE")
        data = db.execute("SELECT data FROM local_assets WHERE id=?", (asset_ref,)).fetchone()[0]
        if not isinstance(data, bytes) or sha(data) != row["digest"]:
            raise WCEError("PREPARATION_CORRUPT")
        try:
            image_check(data, row["declared_type"])
        except WCEError:
            raise WCEError("PREPARATION_CORRUPT") from None
        metadata = {"asset_ref": row["id"], "role": row["role"], "declared_type": row["declared_type"],
                    "size": row["size"], "sha256": row["digest"]}
        return metadata, data, row

    def asset_bytes(self, actor, connection_id, asset_ref):
        with self.service.db.transaction(write=True) as db:
            binding, fence = self._guard(db, actor, connection_id)
            _, data, _ = self._asset(db, binding, asset_ref)
            self._final(db, actor, connection_id, fence)
        return data

    def _content(self, db, binding, article, current=True):
        if not isinstance(article, dict) or set(article) != {"article_type", "title", "cover_asset_ref", "blocks"}:
            raise WCEError("INVALID_PREPARATION")
        if article["article_type"] != "news":
            raise WCEError("INVALID_PREPARATION")
        title = plain(article["title"], 512)
        blocks = article["blocks"]
        if not isinstance(blocks, list) or not 1 <= len(blocks) <= MAX_BLOCKS:
            raise WCEError("INVALID_PREPARATION")
        cover, _, _ = self._asset(db, binding, article["cover_asset_ref"], current, "cover")
        assets, slots, asset_ids = [cover], set(), {cover["asset_ref"]}
        text_bytes = len(title.encode())
        image_bytes = cover["size"]
        normalized = []
        for block in blocks:
            if not isinstance(block, dict):
                raise WCEError("INVALID_PREPARATION")
            kind = block.get("type")
            if isinstance(kind, str) and kind in {"paragraph", "heading", "quote"}:
                if set(block) != {"type", "text"}:
                    raise WCEError("INVALID_PREPARATION")
                value = plain(block["text"], MAX_TEXT_BYTES)
                text_bytes += len(value.encode())
                normalized.append({"type": kind, "text": value})
            elif kind == "image":
                if set(block) != {"type", "slot", "asset_ref", "alt"}:
                    raise WCEError("INVALID_PREPARATION")
                slot = plain(block["slot"], 64)
                if re.fullmatch(r"[A-Za-z0-9_-]+", slot) is None or slot == "cover" or slot in slots or len(slots) >= MAX_IMAGES:
                    raise WCEError("INVALID_PREPARATION")
                slots.add(slot)
                asset = ref(block["asset_ref"], "asset")
                if asset in asset_ids:
                    raise WCEError("INVALID_PREPARATION")
                asset_ids.add(asset)
                meta, _, _ = self._asset(db, binding, asset, current, "body")
                image_bytes += meta["size"]
                alt = plain(block["alt"], 1024, True)
                text_bytes += len(alt.encode())
                normalized.append({"type": "image", "slot": slot, "asset_ref": asset, "alt": alt})
                assets.append(meta)
            else:
                raise WCEError("INVALID_PREPARATION")
            if text_bytes > MAX_TEXT_BYTES or image_bytes > MAX_PACKAGE_BYTES:
                raise WCEError("PREPARATION_LIMIT")
        if not any(b["type"] != "image" for b in normalized):
            raise WCEError("INVALID_PREPARATION")
        return {"article_type": "news", "title": title, "cover_asset_ref": cover["asset_ref"], "blocks": normalized}, assets

    def prepare(self, actor, connection_id, article, bundle_id=None, expected_version=None):
        if bundle_id is not None:
            ref(bundle_id, "bundle")
            ref(expected_version, "version")
        elif expected_version is not None:
            raise WCEError("INVALID_PREPARATION")
        with self.service.db.transaction(write=True) as db:
            binding, fence = self._guard(db, actor, connection_id, True)
            result = self._prepare_in(db, actor, connection_id, binding, fence, article,
                                      bundle_id, expected_version)
        return result | self._evidence()

    def _prepare_in(self, db, actor, connection_id, binding, fence, article,
                    bundle_id=None, expected_version=None):
        """Transaction-local immutable version creation, with original CAS gates."""
        revision = 1
        if bundle_id is not None:
            latest = db.execute("SELECT version,revision FROM prepared_versions WHERE bundle=? AND tenant=? AND principal=? "
                                "AND connection=? AND resource=? ORDER BY revision DESC LIMIT 1",
                                (bundle_id,) + self._scope(binding)).fetchone()
            if latest is None:
                raise WCEError("ACCESS_DENIED")
            if latest["version"] != expected_version:
                raise WCEError("PREPARATION_VERSION_CONFLICT")
            # Verify the predecessor rather than appending onto a damaged lineage.
            self._bundle(db, binding, bundle_id, expected_version)
            revision = latest["revision"] + 1
        article, assets = self._content(db, binding, article)
        bundle_id = bundle_id or "local-bundle-" + uuid4().hex
        version = "local-version-" + uuid4().hex
        manifest = {"schema": 1, "bundle_id": bundle_id, "version": version, "revision": revision,
                    "binding": binding, "article": article, "assets": assets, "image_check": IMAGE_CHECK}
        encoded = canonical(manifest)
        if len(encoded.encode()) > MAX_MANIFEST_BYTES:
            raise WCEError("PREPARATION_LIMIT")
        content_digest = digest(manifest)
        db.execute("INSERT INTO prepared_versions VALUES(?,?,?,?,?,?,?,?,?,?,?)",
                   (version, bundle_id, revision) + self._scope(binding)
                   + (binding["generation"], binding["epoch"], encoded, content_digest))
        self._final(db, actor, connection_id, fence, True)
        return {"bundle_id": bundle_id, "version": version, "revision": revision,
                "content_digest": content_digest}

    def _bundle(self, db, binding, bundle_id, version):
        ref(bundle_id, "bundle")
        ref(version, "version")
        row = db.execute("SELECT version,bundle,revision,tenant,principal,connection,resource,generation,epoch,digest,"
                         "length(CAST(manifest AS BLOB)) AS manifest_size FROM prepared_versions WHERE version=? AND bundle=? "
                         "AND tenant=? AND principal=? AND connection=? AND resource=?",
                         (version, bundle_id) + self._scope(binding)).fetchone()
        if row is None:
            raise WCEError("ACCESS_DENIED")
        if type(row["manifest_size"]) is not int or not 0 < row["manifest_size"] <= MAX_MANIFEST_BYTES:
            raise WCEError("PREPARATION_CORRUPT")
        stored = db.execute("SELECT manifest FROM prepared_versions WHERE version=?", (version,)).fetchone()[0]
        try:
            manifest = json.loads(stored)
            if canonical(manifest) != stored or digest(manifest) != row["digest"]:
                raise WCEError("PREPARATION_CORRUPT")
            artifact_binding = {k: row[k] for k in ("tenant", "principal", "connection", "resource", "generation", "epoch")}
            content, assets = self._content(db, artifact_binding, manifest["article"], False)
            expected = {"schema": 1, "bundle_id": bundle_id, "version": version, "revision": row["revision"],
                        "binding": artifact_binding, "article": content, "assets": assets, "image_check": IMAGE_CHECK}
            if manifest != expected:
                raise WCEError("PREPARATION_CORRUPT")
            for asset in assets:
                _, _, actual = self._asset(db, artifact_binding, asset["asset_ref"])
                if actual["generation"] != artifact_binding["generation"] or actual["epoch"] != artifact_binding["epoch"]:
                    raise WCEError("PREPARATION_CORRUPT")
        except (ValueError, TypeError, KeyError, RecursionError, UnicodeError, WCEError):
            raise WCEError("PREPARATION_CORRUPT") from None
        return manifest, row["digest"]

    def read_bundle(self, actor, connection_id, bundle_id, version):
        with self.service.db.transaction(write=True) as db:
            binding, fence = self._guard(db, actor, connection_id)
            manifest, content_digest = self._bundle(db, binding, bundle_id, version)
            self._final(db, actor, connection_id, fence)
        requirements = [{"slot": "cover", "asset_ref": manifest["article"]["cover_asset_ref"], "needs": "PERMANENT_COVER"}]
        requirements += [{"slot": b["slot"], "asset_ref": b["asset_ref"], "needs": "UPLOADED_BODY_URL"}
                         for b in manifest["article"]["blocks"] if b["type"] == "image"]
        return {"manifest": manifest, "content_digest": content_digest,
                "material_requirements": requirements} | self._evidence()

    def draft_payload(self, actor, connection_id, bundle_id, version):
        self.read_bundle(actor, connection_id, bundle_id, version)
        raise WCEError("NEEDS_PLATFORM_MATERIALS")
