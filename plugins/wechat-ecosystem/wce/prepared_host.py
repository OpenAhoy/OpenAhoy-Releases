"""Trusted local host workflow. No CDN fetcher or production authorization."""
from dataclasses import dataclass, field
import json
import math
from pathlib import Path
import re
from types import MappingProxyType
from urllib.parse import urlsplit
from uuid import uuid4

from .bounded_file import FileSource, MAX_COMPONENTS
from .contracts import Actor, Capability, WCEError
from .local_preparation import MAX_ASSET_BYTES, MAX_MANIFEST_BYTES, image_check, sha
from .prepared_contracts import (ARTICLE, DIGEST, FILE, ID, MIME, ROLE, schema,
                                 strict_validate, validate_arguments)
from .prepared_draft import PreparedDraftExecutor
from .service import canonical, digest
from .upload_executor import UploadExecutor


def _scope(actor, connection, resource):
    return actor.tenant_id, actor.principal_id, connection, resource


def _path(value):
    parts = value.split("/")
    if (value.startswith("/") or ":" in value or "\\" in value
            or any(ord(c) < 32 or ord(c) == 127 for c in value)
            or len(parts) > MAX_COMPONENTS or any(p in {"", ".", ".."} for p in parts)):
        raise WCEError("INVALID_IMAGE_PATH")


class ScopedImageDirectory:
    """Only a trusted operator constructs this grant; no directory enumeration."""
    def __init__(self, root, actor, connection_id, resource_id):
        if not isinstance(actor, Actor):
            raise WCEError("ACCESS_DENIED")
        selected = Path(root)
        project = Path(__file__).resolve().parent.parent
        wide = (Path.home(), project, Path("/tmp"), Path("/private/tmp"),
                Path("/var/tmp"), Path("/private/var/tmp"))
        resolved = selected.resolve()
        if (not selected.is_absolute() or len(resolved.parts) < 3
                or any(resolved == item or resolved in item.parents for item in wide)):
            raise WCEError("INVALID_LOCAL_ROOT")
        strict_validate(connection_id, ID)
        strict_validate(resource_id, ID)
        self.source = FileSource(selected)
        self.scope = _scope(actor, connection_id, resource_id)

    def read(self, actor, connection, resource, relative_path):
        if self.scope != _scope(actor, connection, resource) or type(self.source) is not FileSource:
            raise WCEError("FILE_REFERENCE_UNAVAILABLE")
        return self.source.read(relative_path)


@dataclass(frozen=True)
class FixtureFile:
    """Startup-owned bytes and expiry; never includes a URL."""
    actor: Actor
    connection_id: str
    resource_id: str
    file_id: str
    name: str
    mime_type: str
    expires: float
    data: bytes = field(repr=False)


def _uri(value):
    # An input restriction, not DNS/TLS/CDN ownership verification.
    if (not value.isascii() or any(c.isspace() or ord(c) < 32 or ord(c) == 127 for c in value)
            or "\\" in value or len(value) > 4096):
        raise WCEError("INVALID_FILE_REFERENCE")
    try:
        parsed = urlsplit(value)
        if (parsed.scheme != "https" or parsed.netloc not in {"files.oaiusercontent.com", "files.oaiusercontent.com:443"}
                or parsed.port not in (None, 443) or parsed.username is not None or parsed.password is not None
                or not parsed.path or not parsed.query or parsed.fragment or "#" in value):
            raise ValueError
    except ValueError:
        raise WCEError("INVALID_FILE_REFERENCE") from None


class FixedFixtureFiles:
    """Exact fixed implementation: look up trusted bytes, never perform network I/O."""
    def __init__(self, records=()):
        registry = {}
        for record in records:
            if type(record) is not FixtureFile or not isinstance(record.actor, Actor):
                raise WCEError("FILE_REFERENCE_UNAVAILABLE")
            strict_validate({"name": record.name, "id": record.file_id,
                             "mime_type": record.mime_type, "download_link": "unused"}, FILE)
            strict_validate(record.connection_id, ID)
            strict_validate(record.resource_id, ID)
            if (type(record.expires) not in (int, float) or not math.isfinite(record.expires)
                    or type(record.data) is not bytes or not 0 < len(record.data) <= MAX_ASSET_BYTES):
                raise WCEError("FILE_REFERENCE_UNAVAILABLE")
            key = _scope(record.actor, record.connection_id, record.resource_id) + (record.file_id,)
            if key in registry:
                raise WCEError("FILE_REFERENCE_UNAVAILABLE")
            registry[key] = record
        self.records = MappingProxyType(registry)
        self.calls = 0

    def receive(self, actor, connection, resource, item, now):
        strict_validate(item, FILE)
        _uri(item["download_link"])
        record = self.records.get(_scope(actor, connection, resource) + (item["id"],))
        if record is None or record.name != item["name"] or record.mime_type != item["mime_type"]:
            raise WCEError("FILE_REFERENCE_UNAVAILABLE")
        if type(now) not in (int, float) or not math.isfinite(now) or now >= record.expires:
            raise WCEError("FILE_REFERENCE_EXPIRED")
        self.calls += 1
        return record.data


class HostDraftWorkflow:
    """Prepared namespace with durable atomic input keys and fixed executors."""
    def __init__(self, service, image_directory=None, files=None):
        if ((image_directory is not None and type(image_directory) is not ScopedImageDirectory)
                or (files is not None and type(files) is not FixedFixtureFiles)):
            raise WCEError("SOURCE_UNCONFIGURED")
        self.service = service
        self.image_directory, self.files = image_directory, files
        self.uploads = UploadExecutor(service)
        self.drafts = PreparedDraftExecutor(service)

    def _evidence(self):
        original = self.service.evidence()
        return {k: original[k] for k in ("transport", "mode", "runtime", "connected", "platform_verified")} | {
            "platform_ready": False, "test_only": True, "state": "LOCAL_PREPARED",
            "image_check": "SIGNATURE_ONLY_NOT_DECODED", "input_evidence": "ACTUAL_LOCAL_BYTES",
            "platform_state": "NEEDS_PLATFORM_MATERIALS"}

    def _gate(self, db, actor, connection, write=False, fence=None, deadline=None):
        if not isinstance(actor, Actor):
            raise WCEError("ACCESS_DENIED")
        # Check finite leases before canonicalizing the authorization fence.
        # Nonfinite expiry values otherwise fail during the fence's JSON digest.
        self.service._authorize(db, actor, connection, Capability.READ_DRAFT)
        self.drafts._deadline(db, actor, connection)
        binding, actual, lease = self.drafts._authorization(db, actor, connection, write, fence)
        if deadline is not None:
            self.drafts._lease(deadline)
        return binding, actual, lease

    def _view(self, row, result, parameters):
        view = result | self._evidence() | {"connection_id": row["connection"], "request_key": row["request_key"],
                "input_operation_id": row["id"], "input_state": "COMMITTED"}
        if row["kind"] == "asset":
            view["source_kind"] = parameters["source_kind"]
        return view

    def _bundle(self, db, binding, bundle, version):
        manifest, content_digest = self.service.local._bundle(db, binding, bundle, version)
        # JSON booleans compare equal to 0/1 in Python. Check durable types before
        # exposing the new closed host contract, even after coordinated rehashing.
        if (type(manifest["schema"]) is not int or manifest["schema"] != 1
                or type(manifest["revision"]) is not int or manifest["revision"] < 1
                or any(type(manifest["binding"][key]) is not int
                       or manifest["binding"][key] < 0 for key in ("generation", "epoch"))):
            raise WCEError("PREPARATION_CORRUPT")
        return manifest, content_digest

    def _stored(self, db, row):
        """Recompute original stored bytes/manifest; no external source access."""
        try:
            if (len(row["intent"].encode()) > MAX_MANIFEST_BYTES or len(row["result"].encode()) > 2048
                    or row["mode"] != "test" or row["provenance"] != "LOCAL_HOST_INPUT"
                    or re.fullmatch(r"local-input-[a-f0-9]{32}", row["id"]) is None
                    or type(row["created"]) not in (int, float) or not math.isfinite(row["created"])
                    or row["kind"] not in {"asset", "prepare"}):
                raise ValueError
            strict_validate(row["request_key"], ID)
            intent, result = json.loads(row["intent"]), json.loads(row["result"])
            if (canonical(intent) != row["intent"] or canonical(result) != row["result"]
                    or digest(intent) != row["fingerprint"] or digest(result) != row["result_digest"]
                    or set(intent) != {"schema", "kind", "binding", "parameters"}
                    or type(intent["schema"]) is not int or intent["schema"] != 1 or intent["kind"] != row["kind"]):
                raise ValueError
            binding = {k: row[k] for k in ("tenant", "principal", "connection", "resource", "generation", "epoch")}
            if (intent["binding"] != binding or type(intent["binding"]) is not dict
                    or any(type(intent["binding"][k]) is not int or type(binding[k]) is not int or binding[k] < 0
                           for k in ("generation", "epoch"))):
                raise ValueError
            for key in ("tenant", "principal", "connection", "resource"):
                strict_validate(binding[key], ID)
            parameters = intent["parameters"]
            if row["kind"] == "asset":
                if parameters.get("source_kind") == "codex_local":
                    spec = schema({"source_kind": {"type": "string", "const": "codex_local"},
                                   "path_digest": DIGEST, "role": ROLE, "declared_type": MIME})
                else:
                    spec = schema({"source_kind": {"type": "string", "const": "gpt_fixed_fixture"},
                                   "file_id": ID, "name": FILE["properties"]["name"], "role": ROLE, "declared_type": MIME})
                strict_validate(parameters, spec)
                if set(result) != {"asset_ref", "role", "declared_type", "size", "sha256"}:
                    raise ValueError
                actual, _, asset = self.service.local._asset(db, binding, result["asset_ref"])
                if (actual != result or actual["role"] != parameters["role"] or actual["declared_type"] != parameters["declared_type"]
                        or any(asset[k] != binding[k] for k in ("generation", "epoch"))):
                    raise ValueError
            else:
                from .prepared_contracts import BUNDLE, VERSION
                strict_validate(parameters, schema({"article": ARTICLE}, {"bundle_id": BUNDLE, "expected_version": VERSION}))
                if (("bundle_id" in parameters) != ("expected_version" in parameters)
                        or set(result) != {"bundle_id", "version", "revision", "content_digest"}):
                    raise ValueError
                manifest, actual_digest = self._bundle(db, binding, result["bundle_id"], result["version"])
                if (manifest["binding"] != binding or manifest["article"] != parameters["article"]
                        or actual_digest != result["content_digest"] or manifest["revision"] != result["revision"]
                        or type(result["revision"]) is not int
                        or ("bundle_id" in parameters and parameters["bundle_id"] != result["bundle_id"])):
                    raise ValueError
                if "bundle_id" in parameters:
                    predecessor = db.execute("SELECT version FROM prepared_versions WHERE bundle=? AND revision=? "
                        "AND tenant=? AND principal=? AND connection=? AND resource=?",
                        (result["bundle_id"], result["revision"] - 1) + self.service.local._scope(binding)).fetchone()
                    if predecessor is None or predecessor[0] != parameters["expected_version"]:
                        raise ValueError
                    self._bundle(db, binding, result["bundle_id"], predecessor[0])
                elif result["revision"] != 1:
                    raise ValueError
            return result, parameters
        except Exception:
            raise WCEError("HOST_INPUT_JOURNAL_CORRUPT") from None

    def _history(self, db, actor, connection, kind, key, parameters=None):
        binding, fence, deadline = self._gate(db, actor, connection)
        row = db.execute("SELECT * FROM host_input_operations WHERE mode='test' AND tenant=? AND principal=? "
                         "AND connection=? AND kind=? AND request_key=?",
                         (actor.tenant_id, actor.principal_id, connection, kind, key)).fetchone()
        if row is None:
            return None
        if row["resource"] != binding["resource"]:
            raise WCEError("ACCESS_DENIED")
        result, original = self._stored(db, row)
        if parameters is not None and parameters != original:
            raise WCEError("IDEMPOTENCY_CONFLICT")
        view = self._view(row, result, original)
        self._gate(db, actor, connection, fence=fence, deadline=deadline)
        return view

    def _commit(self, db, actor, connection, kind, key, parameters, binding, fence, deadline, result):
        intent = {"schema": 1, "kind": kind, "binding": binding, "parameters": parameters}
        if len(canonical(intent).encode()) > MAX_MANIFEST_BYTES:
            raise WCEError("PREPARATION_LIMIT")
        identifier = "local-input-" + uuid4().hex
        values = (identifier, "test", "LOCAL_HOST_INPUT") + tuple(binding[k] for k in (
            "tenant", "principal", "connection", "resource", "generation", "epoch")) + (
            kind, key, canonical(intent), digest(intent), canonical(result), digest(result), self.service.clock())
        db.execute("INSERT INTO host_input_operations VALUES(" + ",".join("?" for _ in values) + ")", values)
        row = db.execute("SELECT * FROM host_input_operations WHERE id=?", (identifier,)).fetchone()
        result, original = self._stored(db, row)
        self._gate(db, actor, connection, True, fence, deadline)
        return self._view(row, result, original)

    def _asset(self, actor, args, transport):
        connection, key = args["connection_id"], args["request_key"]
        role, mime = args["role"], args["declared_type"]
        if mime == "image/webp":
            raise WCEError("UNSUPPORTED_IMAGE_FORMAT")
        if transport == "mcp":
            _path(args["relative_path"])
            parameters = {"source_kind": "codex_local", "path_digest": sha(args["relative_path"].encode()),
                          "role": role, "declared_type": mime}
        else:
            item = args["openaiFileIdRefs"][0]
            if item["mime_type"] == "image/webp":
                raise WCEError("UNSUPPORTED_IMAGE_FORMAT")
            if item["mime_type"] != mime:
                raise WCEError("INVALID_FILE_REFERENCE")
            parameters = {"source_kind": "gpt_fixed_fixture", "file_id": item["id"], "name": item["name"],
                          "role": role, "declared_type": mime}
        with self.service.db.transaction(write=True) as db:
            old = self._history(db, actor, connection, "asset", key, parameters)
            if old is not None:
                return old
            binding, fence, deadline = self._gate(db, actor, connection, True)
        if transport == "mcp":
            if type(self.image_directory) is not ScopedImageDirectory:
                raise WCEError("SOURCE_UNCONFIGURED")
            data = self.image_directory.read(actor, connection, binding["resource"], args["relative_path"])
        else:
            if type(self.files) is not FixedFixtureFiles:
                raise WCEError("SOURCE_UNCONFIGURED")
            data = self.files.receive(actor, connection, binding["resource"], item, self.service.clock())
        if type(data) is not bytes or not 0 < len(data) <= MAX_ASSET_BYTES:
            raise WCEError("LOCAL_FILE_LIMIT")
        image_check(data, mime)
        with self.service.db.transaction(write=True) as db:
            old = self._history(db, actor, connection, "asset", key, parameters)
            if old is not None:
                return old
            current, _, _ = self._gate(db, actor, connection, True, fence, deadline)
            result = self.service.local._insert_asset(db, current, data, role, mime)
            return self._commit(db, actor, connection, "asset", key, parameters, current, fence, deadline, result)

    def _prepare(self, actor, args):
        connection, key = args["connection_id"], args["request_key"]
        parameters = {k: v for k, v in args.items() if k not in {"connection_id", "request_key"}}
        with self.service.db.transaction(write=True) as db:
            old = self._history(db, actor, connection, "prepare", key, parameters)
            if old is not None:
                return old
            binding, fence, deadline = self._gate(db, actor, connection, True)
            result = self.service.local._prepare_in(db, actor, connection, binding, fence, **parameters)
            return self._commit(db, actor, connection, "prepare", key, parameters, binding, fence, deadline, result)

    def _status(self, actor, args, kind):
        with self.service.db.transaction(write=True) as db:
            value = self._history(db, actor, args["connection_id"], kind, args["request_key"])
            if value is None:
                raise WCEError("HOST_INPUT_NOT_FOUND")
            return value

    def _read(self, actor, args):
        connection = args["connection_id"]
        with self.service.db.transaction(write=True) as db:
            binding, fence, deadline = self._gate(db, actor, connection)
            manifest, actual_digest = self._bundle(db, binding, args["bundle_id"], args["version"])
            requirements = [{"slot": "cover", "asset_ref": manifest["article"]["cover_asset_ref"], "needs": "PERMANENT_COVER"}]
            requirements += [{"slot": b["slot"], "asset_ref": b["asset_ref"], "needs": "UPLOADED_BODY_URL"}
                             for b in manifest["article"]["blocks"] if b["type"] == "image"]
            result = {k: manifest[k] for k in ("bundle_id", "version", "revision", "article", "assets")} | {
                "connection_id": connection, "content_digest": actual_digest, "material_requirements": requirements}
            self._gate(db, actor, connection, fence=fence, deadline=deadline)
            return result | self._evidence()

    def call(self, actor, name, args, transport="mcp"):
        validate_arguments(name, args, transport)
        connection = args["connection_id"]
        self.drafts._sender_guard()
        self.uploads._sender_guard()
        with self.service.db.transaction() as db:
            _, fence, deadline = self._gate(db, actor, connection)
        if name == "prepared.assets.receive":
            result = self._asset(actor, args, transport)
        elif name == "prepared.assets.status":
            result = self._status(actor, args, "asset")
        elif name == "prepared.articles.prepare":
            result = self._prepare(actor, args)
        elif name == "prepared.articles.status":
            result = self._status(actor, args, "prepare")
        elif name == "prepared.articles.read":
            result = self._read(actor, args)
        elif name.startswith("prepared.uploads."):
            method = self.uploads.execute if name.endswith("execute") else self.uploads.status
            result = method(actor, **args)
        else:
            method = {"prepared.drafts.save": self.drafts.save, "prepared.drafts.status": self.drafts.status,
                      "prepared.drafts.readback": self.drafts.readback}[name]
            result = method(actor, **args)
        with self.service.db.transaction() as db:
            self._gate(db, actor, connection, fence=fence, deadline=deadline)
        return result
