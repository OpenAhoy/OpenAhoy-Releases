"""In-process draft wire fixture. No network, credential input or live switch.

The existing material/preview/publication behavior stays purely offline. Only
draft save/read go through the narrow wire codecs and HTTPExecutor journals.
"""
from dataclasses import dataclass
import json
import math
import re
import time
from urllib.parse import parse_qs, urlsplit
from uuid import uuid4

from .contracts import (DraftCallContext, FakeSecretProvider, Receipt, RejectedOperation, Secret,
                        UncertainResult, WCEError)
from .draft_wire import (NewsArticle, draft_add_operation, fixture_draft_get_operation,
                         unique_object)
from .http_transport import HTTPBinding, HTTPExecutor, HTTPResponse
from .mock import MOCK_SCHEMA, MockOfficialAccountAdapter
from .service import canonical, digest
from .storage import Database
from .token_provider import ScopedTokenCache, TokenLease

FIXTURE_SCHEMA = """
CREATE TABLE IF NOT EXISTS draft_links (
 tenant TEXT, connection TEXT, reference TEXT, generation INTEGER,
 operation_id TEXT, draft_id TEXT, version TEXT, content_digest TEXT, materials TEXT,
 PRIMARY KEY(tenant,connection,reference), UNIQUE(tenant,connection,operation_id));
"""


class DraftFixtureAdapter(MockOfficialAccountAdapter):
    workflow_mode = "fixture"

    def __init__(self, path, http_path, clock=time.time):
        super().__init__(path)
        self.db = Database(path, MOCK_SCHEMA + FIXTURE_SCHEMA, 0x5743454D)
        self.http_path, self.clock = http_path, clock
        self.wire_calls = []  # trusted tests only; no credential/query data
        self.provider = ScopedTokenCache(lambda key: TokenLease(
            Secret(FakeSecretProvider().get(key.tenant, key.connection, key.secret_ref).reveal_for_adapter()
                   + ("_REV_" + str(key.token_revision) if key.token_revision else "")), self.clock() + 3600), clock)

    def bind_draft(self, context):
        if (not isinstance(context, DraftCallContext) or not context.synthetic
                or type(context.generation) is not int or context.generation < 1
                or isinstance(context.expires_at, bool) or not isinstance(context.expires_at, (int, float))
                or not math.isfinite(context.expires_at) or context.expires_at <= self.clock()):
            raise WCEError("FIXTURE_CONTEXT_REQUIRED")
        return BoundDraftFixture(self, context)

    def add_material(self, connection_id, content_digest, credential):
        # Platform permanence is synthetic fixture typing, distinct from the
        # business layer's local reference-expiry policy. No real upload occurs.
        return self._write(connection_id, "material",
                           {"digest": content_digest, "fixture_material_type": "permanent"}, credential)

    def _cover(self, db, connection_id, reference):
        row = self._object(db, connection_id, reference, "material")
        if json.loads(row["payload"]).get("fixture_material_type") != "permanent":
            raise RejectedOperation("FIXTURE_PERMANENT_COVER_REQUIRED")
        return row


@dataclass(frozen=True)
class DraftFixtureSender:
    adapter: DraftFixtureAdapter
    context: DraftCallContext
    fault: str | None = None
    mode = "test"

    def send(self, request, timeout):
        c, root = self.context, self.adapter
        parts = urlsplit(request.path)
        token = FakeSecretProvider().get(c.actor.tenant_id, c.connection_id, c.secret_ref).reveal_for_adapter()
        if c.token_revision:
            token += "_REV_" + str(c.token_revision)
        if (not request.test_only or request.method != "POST" or parts.scheme or parts.netloc or parts.fragment
                or parts.path not in {"/cgi-bin/draft/add", "/cgi-bin/draft/get"}
                or parse_qs(parts.query, strict_parsing=True) != {"access_token": [token]}):
            raise WCEError("INVALID_FIXTURE_REQUEST")
        payload = json.loads(request.body.decode("utf-8"), object_pairs_hook=unique_object,
                             parse_constant=lambda _: (_ for _ in ()).throw(ValueError()))
        root.wire_calls.append({"tenant": c.actor.tenant_id, "principal": c.actor.principal_id,
                                "connection": c.connection_id, "generation": c.generation,
                                "operation_id": c.operation_id, "version": c.version,
                                "path": parts.path, "payload": payload})
        if self.fault == "token_invalid":
            return HTTPResponse(200, b'{"errcode":40014,"errmsg":"synthetic"}')
        if self.fault == "timeout_before":
            raise TimeoutError()
        if self.fault == "non_2xx":
            return HTTPResponse(503, b'{}')
        if parts.path == "/cgi-bin/draft/add":
            articles = payload.get("articles") if isinstance(payload, dict) else None
            if not isinstance(articles, list) or len(articles) != 1 or not isinstance(articles[0], dict):
                raise WCEError("INVALID_FIXTURE_REQUEST")
            a = articles[0]
            article = NewsArticle(a.get("title"), a.get("content"), a.get("thumb_media_id"),
                                  a.get("author"), a.get("digest"))
            if payload != article.payload() or c.operation_id is None:
                raise WCEError("INVALID_FIXTURE_REQUEST")
            ref = "mock-draft-" + uuid4().hex
            with root.db.transaction(write=True) as db:
                root._cover(db, c.connection_id, article.thumb_media_id)
                db.execute("INSERT INTO objects(ref,connection,kind,payload,state) VALUES(?,?,?,?,?)",
                           (ref, c.connection_id, "draft", canonical(a), "SUCCEEDED"))
                db.execute("INSERT INTO draft_links VALUES(?,?,?,?,?,?,?,?,?)",
                           (c.actor.tenant_id, c.connection_id, ref, c.generation, c.operation_id,
                            c.draft_id, c.version, c.content_digest, canonical(c.materials)))
            if self.fault in {"lose_with_ref", "lose_without_ref"}:
                # A lost wire response carries no usable reference back to the journal.
                raise TimeoutError()
            if self.fault == "malformed":
                return HTTPResponse(200, b'{"media_id":')
            if self.fault == "duplicate_keys":
                return HTTPResponse(200, b'{"media_id":"a","media_id":"b"}')
            if self.fault == "bool_errcode":
                return HTTPResponse(200, b'{"errcode":false,"media_id":"a"}')
            if self.fault == "missing_media_id":
                return HTTPResponse(200, b'{"errcode":0}')
            return HTTPResponse(200, canonical({"media_id": ref}).encode("utf-8"))
        if not isinstance(payload, dict) or set(payload) != {"media_id"}:
            raise WCEError("INVALID_FIXTURE_REQUEST")
        with root.db.transaction() as db:
            link = db.execute("SELECT * FROM draft_links WHERE tenant=? AND connection=? AND reference=?",
                              (c.actor.tenant_id, c.connection_id, payload["media_id"])).fetchone()
            if (link is None or link["generation"] != (c.artifact_generation or c.generation)
                    or c.artifact_operation_id is not None and link["operation_id"] != c.artifact_operation_id):
                raise WCEError("FIXTURE_DRAFT_UNAVAILABLE")
            article = json.loads(root._object(db, c.connection_id, payload["media_id"], "draft")["payload"])
        if self.fault == "body_mismatch":
            article["content"] = "Synthetic different body"
        if self.fault == "cover_mismatch":
            article["thumb_media_id"] = "mock-material-" + "0" * 32
        # The real documented get shape has no response media_id.
        return HTTPResponse(200, canonical({"news_item": [article]}).encode("utf-8"))


@dataclass(frozen=True)
class BoundDraftFixture:
    adapter: DraftFixtureAdapter
    context: DraftCallContext

    def _check(self, connection_id, credential):
        c = self.context
        expected = FakeSecretProvider().get(c.actor.tenant_id, c.connection_id, c.secret_ref)
        if connection_id != c.connection_id or credential.reveal_for_adapter() != expected.reveal_for_adapter():
            raise WCEError("FIXTURE_CONTEXT_MISMATCH")

    def _executor(self, fault):
        c = self.context
        binding = HTTPBinding(c.actor.tenant_id, c.actor.principal_id, c.connection_id, c.resource_id or c.connection_id,
                              c.secret_ref, mode="test", qualification_verified=True,
                              capabilities=frozenset({"draft.add", "draft.get"}),
                              expires_at=c.expires_at, generation=c.generation,
                              resource_id=c.resource_id, token_revision=c.token_revision)
        return HTTPExecutor(self.adapter.http_path, binding, self.adapter.provider,
                            DraftFixtureSender(self.adapter, c, fault), self.adapter.clock, c.registry_guard)

    def save_draft(self, connection_id, content, credential):
        c = self.context
        try:
            self._check(connection_id, credential)
            if (c.operation_id is None or not re.fullmatch(r"[a-f0-9]{32}", c.operation_id)
                    or digest(content) != c.content_digest or len(c.materials) != 1
                    or content["material_ids"] != [c.materials[0][0]]):
                raise WCEError("FIXTURE_CONTENT_CONTEXT_MISMATCH")
            article = NewsArticle(content["title"], content["body"], c.materials[0][1])
            with self.adapter.db.transaction() as db:
                self.adapter._cover(db, c.connection_id, article.thumb_media_id)
        except (WCEError, RejectedOperation, KeyError, TypeError, ValueError):
            # Only these local checks certify no dispatch and no side effect.
            raise RejectedOperation("FIXTURE_INPUT_REJECTED") from None
        fault = self.adapter._fault("draft")
        if fault == "reject":
            raise RejectedOperation("FIXTURE_REJECTED_BEFORE_DISPATCH")
        if fault == "secret_error":
            raise RuntimeError(credential.reveal_for_adapter())
        executor = self._executor(fault)
        result = executor.execute(draft_add_operation(article), article.payload(), c.operation_id)
        if (result["state"] != "SUCCEEDED" or not isinstance(result["reference"], str)
                or not re.fullmatch(r"mock-draft-[a-f0-9]{32}", result["reference"])):
            raise UncertainResult()
        self._link(result["reference"], c.operation_id)
        return Receipt(result["reference"])

    def _link(self, platform_ref, operation_id=None):
        c = self.context
        with self.adapter.db.transaction() as db:
            link = db.execute("SELECT * FROM draft_links WHERE tenant=? AND connection=? AND reference=?",
                              (c.actor.tenant_id, c.connection_id, platform_ref)).fetchone()
            if (link is None or link["generation"] != (c.artifact_generation or c.generation) or link["draft_id"] != c.draft_id
                    or link["version"] != c.version or link["content_digest"] != c.content_digest
                    or json.loads(link["materials"]) != [list(pair) for pair in c.materials]
                    or operation_id is not None and link["operation_id"] != operation_id
                    or c.artifact_operation_id is not None and link["operation_id"] != c.artifact_operation_id):
                raise WCEError("FIXTURE_DRAFT_CONTEXT_MISMATCH")

    def read_draft(self, connection_id, platform_ref, credential):
        c = self.context
        self._check(connection_id, credential)
        self._link(platform_ref)
        operation = fixture_draft_get_operation(platform_ref)
        articles = self._executor(self.adapter._fault("read")).pages(operation, {"media_id": platform_ref})
        if (len(articles) != 1 or len(c.materials) != 1 or articles[0]["thumb_media_id"] != c.materials[0][1]
                or articles[0]["author"] != "" or articles[0]["digest"] != ""):
            raise WCEError("FIXTURE_READBACK_MISMATCH")
        return {"title": articles[0]["title"], "body": articles[0]["content"],
                "material_ids": [c.materials[0][0]]}
