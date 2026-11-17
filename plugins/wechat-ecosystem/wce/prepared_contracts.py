"""Closed prepared-workflow contracts; runtime file objects are HTTP-only."""
from copy import deepcopy
import re

from .actions_contracts import Route, SAFE_ID, openapi
from .contracts import WCEError
from .tools import schema


def string(maximum, pattern=None, minimum=1):
    result = {"type": "string", "minLength": minimum, "maxLength": maximum}
    if pattern is not None:
        result["pattern"] = pattern
    return result


ID = deepcopy(SAFE_ID)
ASSET = string(44, r"^local-asset-[a-f0-9]{32}$")
BUNDLE = string(45, r"^local-bundle-[a-f0-9]{32}$")
VERSION = string(46, r"^local-version-[a-f0-9]{32}$")
DIGEST = string(64, r"^[a-f0-9]{64}$")
ROLE = {"type": "string", "enum": ["cover", "body"]}
MIME = {"type": "string", "enum": ["image/png", "image/jpeg", "image/webp"]}
PATH = string(4096)
ARTICLE = schema({
    "article_type": {"type": "string", "const": "news"}, "title": string(512),
    "cover_asset_ref": ASSET,
    "blocks": {"type": "array", "minItems": 1, "maxItems": 64, "items": {"oneOf": [
        schema({"type": {"type": "string", "const": kind}, "text": string(65536)})
        for kind in ("paragraph", "heading", "quote")
    ] + [schema({"type": {"type": "string", "const": "image"},
                 "slot": string(64, r"^[A-Za-z0-9_-]+$"), "asset_ref": ASSET,
                 "alt": string(1024, minimum=0)})]}}
})
FILE = schema({"name": string(128, r"^[^/\\:?#\x00-\x1f\x7f-\x9f]+$"), "id": ID, "mime_type": MIME,
               "download_link": string(4096)})

KEY_ARGS = {"connection_id": ID, "request_key": ID}
SELECTOR_ARGS = {"connection_id": ID, "bundle_id": BUNDLE, "version": VERSION,
                 "content_digest": DIGEST, "request_key": ID}
SPECS = {
    "prepared.assets.receive": ("Receive one actual image from the configured scoped source. Keep the original request_key; no URL fetch.",
        schema(KEY_ARGS | {"relative_path": PATH, "role": ROLE, "declared_type": MIME})),
    "prepared.assets.status": ("Recover the original image ref by request_key, without rereading the source.", schema(KEY_ARGS)),
    "prepared.articles.prepare": ("Freeze news and returned image refs. Retry the original key; paired bundle/expected_version appends one local revision.",
        schema(KEY_ARGS | {"article": ARTICLE}, {"bundle_id": BUNDLE, "expected_version": VERSION})),
    "prepared.articles.status": ("Recover original bundle/version/digest by request_key; never create another revision.", schema(KEY_ARGS)),
    "prepared.articles.read": ("Read the immutable local version and image order, not a real WeChat draft.",
        schema({"connection_id": ID, "bundle_id": BUNDLE, "version": VERSION})),
    "prepared.uploads.execute": ("Upload exactly one declared cover/body slot to a test-only fixture. On UNKNOWN stop writes and query the same key.",
        schema(SELECTOR_ARGS | {"slot": string(64, r"^[A-Za-z0-9_-]+$")})),
    "prepared.uploads.status": ("Query an original upload key; UNKNOWN never resends.", schema(KEY_ARGS)),
    "prepared.drafts.save": ("Save one prepared version to the fixed durable fixture. All declared slots must succeed. No publication.", schema(SELECTOR_ARGS)),
    "prepared.drafts.readback": ("Physically GET a known saved fixture draft and compare all fields. UNKNOWN only returns status.", schema(KEY_ARGS)),
    "prepared.drafts.status": ("Query the original draft key without sending again. FIXTURE_SAVED is separate from READBACK_MATCHED.", schema(KEY_ARGS)),
}


def arguments(name, transport="mcp", runtime=False):
    result = deepcopy(SPECS[name][1])
    if name == "prepared.assets.receive" and transport == "http":
        del result["properties"]["relative_path"]
        result["required"].remove("relative_path")
        result["properties"]["openaiFileIdRefs"] = {
            "type": "array", "minItems": 1, "maxItems": 1,
            "description": "One PNG/JPEG file ID from this conversation. The Actions host supplies name/id/mime_type/download_link at runtime; local fixed registry only.",
            "items": deepcopy(FILE) if runtime else ID}
        result["required"].append("openaiFileIdRefs")
    return result


_STRING_CONTROL = re.compile(r'[\x00-\x08\x0b-\x1f\x7f-\x9f]')


def strict_validate(value, spec, depth=0):
    """Only the schema vocabulary used here; never silently skip a type."""
    if depth > 16:
        raise WCEError("INVALID_TOOL_ARGUMENTS")
    if "oneOf" in spec:
        successes = 0
        for branch in spec["oneOf"]:
            try:
                strict_validate(value, branch, depth + 1)
                successes += 1
            except WCEError:
                pass
        if successes != 1:
            raise WCEError("INVALID_TOOL_ARGUMENTS")
        return
    kind = spec.get("type")
    if kind == "object":
        if (type(value) is not dict or set(value) - set(spec["properties"])
                or set(spec["required"]) - set(value)):
            raise WCEError("INVALID_TOOL_ARGUMENTS")
        for key, item in value.items():
            strict_validate(item, spec["properties"][key], depth + 1)
    elif kind == "array":
        if type(value) is not list or not spec.get("minItems", 0) <= len(value) <= spec.get("maxItems", len(value)):
            raise WCEError("INVALID_TOOL_ARGUMENTS")
        for item in value:
            strict_validate(item, spec["items"], depth + 1)
    elif kind == "string":
        if (type(value) is not str or not spec.get("minLength", 0) <= len(value) <= spec.get("maxLength", 65536)
                or (spec.get("minLength", 0) and not value.strip())
                or _STRING_CONTROL.search(value) is not None):
            raise WCEError("INVALID_TOOL_ARGUMENTS")
        try:
            if len(value.encode("utf-8")) > spec.get("x-wce-maxUtf8Bytes", spec.get("maxLength", 65536)):
                raise WCEError("INVALID_TOOL_ARGUMENTS")
        except UnicodeError:
            raise WCEError("INVALID_TOOL_ARGUMENTS") from None
        if "pattern" in spec and re.fullmatch(spec["pattern"], value) is None:
            raise WCEError("INVALID_TOOL_ARGUMENTS")
    elif kind == "integer":
        if type(value) is not int or not spec.get("minimum", 0) <= value <= spec.get("maximum", 2**63 - 1):
            raise WCEError("INVALID_TOOL_ARGUMENTS")
    elif kind == "boolean":
        if type(value) is not bool:
            raise WCEError("INVALID_TOOL_ARGUMENTS")
    else:
        raise WCEError("INVALID_TOOL_ARGUMENTS")
    if "enum" in spec and value not in spec["enum"]:
        raise WCEError("INVALID_TOOL_ARGUMENTS")
    if "const" in spec and (type(value) is not type(spec["const"]) or value != spec["const"]):
        raise WCEError("INVALID_TOOL_ARGUMENTS")


def validate_arguments(name, value, transport="mcp"):
    if name not in SPECS or transport not in {"mcp", "http"}:
        raise WCEError("TOOL_NOT_IMPLEMENTED")
    strict_validate(value, arguments(name, transport, runtime=True))
    if name == "prepared.articles.prepare" and (("bundle_id" in value) != ("expected_version" in value)):
        raise WCEError("INVALID_TOOL_ARGUMENTS")


def list_tools():
    return [{"name": name, "description": description + " Local mock/test; platform_ready=false.",
             "inputSchema": arguments(name)} for name, (description, _) in SPECS.items()]


class PreparedRoute(Route):
    def arguments(self):
        return arguments(self.tool, "http")


PREFIX = "/v1/prepared/connections/{connection_id}"
ROUTES = (
    PreparedRoute("POST", "/v1/prepared/assets", "prepared.assets.receive", "receivePreparedImage", "接收一张会话图片（本地固定来源）", "wce:draft"),
    PreparedRoute("GET", PREFIX + "/assets/{request_key}", "prepared.assets.status", "getPreparedImageStatus", "按原键取回图片引用", "wce:read"),
    PreparedRoute("POST", "/v1/prepared/articles", "prepared.articles.prepare", "prepareNewsArticle", "冻结或追加本地图文版本", "wce:draft"),
    PreparedRoute("GET", PREFIX + "/articles/requests/{request_key}", "prepared.articles.status", "getPreparedArticleStatus", "按原键取回版本引用", "wce:read"),
    PreparedRoute("GET", PREFIX + "/articles/{bundle_id}/{version}", "prepared.articles.read", "readPreparedArticle", "核对本地图文与图片顺序", "wce:read"),
    PreparedRoute("POST", "/v1/prepared/uploads", "prepared.uploads.execute", "uploadPreparedSlot", "上传单个图片slot到fixture", "wce:draft"),
    PreparedRoute("GET", PREFIX + "/uploads/{request_key}", "prepared.uploads.status", "getPreparedUploadStatus", "只查原图片上传状态", "wce:read"),
    PreparedRoute("POST", "/v1/prepared/drafts", "prepared.drafts.save", "savePreparedDraft", "保存固定图文到fixture草稿", "wce:draft"),
    PreparedRoute("POST", "/v1/prepared/drafts/readback", "prepared.drafts.readback", "readbackPreparedDraft", "实际GET已知fixture草稿并比较", "wce:draft"),
    PreparedRoute("GET", PREFIX + "/drafts/{request_key}", "prepared.drafts.status", "getPreparedDraftStatus", "只查原草稿保存状态", "wce:read"),
)


def result_schema(name):
    """Accurate HTTP fieldsets; executor projections retain their own evidence."""
    common = {"transport": {"const": "mock"}, "mode": {"const": "test"},
              "http_entrypoint": {"const": "local_preparation"}, "connected": {"const": False},
              "platform_verified": {"const": False}, "platform_ready": {"const": False},
              "test_only": {"const": True}, "connection_id": ID}
    integer = {"type": "integer", "minimum": 1}
    asset = schema({"asset_ref": ASSET, "role": ROLE, "declared_type": MIME,
                    "size": integer, "sha256": DIGEST})
    if name.startswith(("prepared.uploads.", "prepared.drafts.")):
        selector = {k: v for k, v in SELECTOR_ARGS.items() if k not in {"connection_id", "request_key"}}
        is_upload = name.startswith("prepared.uploads.")
        if is_upload:
            selector["slot"] = string(64, r"^[A-Za-z0-9_-]+$")
        common |= {"attempt_id": ID, "request_key": ID, "state": {"enum": ["RESULT_UNKNOWN", "FIXTURE_SUCCEEDED" if is_upload else "FIXTURE_SAVED"]},
                   "resource_id": ID, "selector": schema(selector), "fingerprint": DIGEST,
                   "provenance": {"const": "LOCAL_FIXED_FIXTURE"}}
        nullable = {"type": ["string", "null"]}
        common |= ({"cover_media_id": nullable, "cover_url": nullable, "body_url": nullable}
                   if is_upload else {"reference": nullable})
        result = schema(common)
        if name == "prepared.drafts.readback":
            result["properties"]["readback_state"] = {"enum": ["READBACK_MATCHED", "READBACK_UNVERIFIED"]}
        return result
    common |= {"runtime": {"enum": ["offline", "wire_fixture"]}, "state": {"const": "LOCAL_PREPARED"},
               "image_check": {"const": "SIGNATURE_ONLY_NOT_DECODED"},
               "input_evidence": {"const": "ACTUAL_LOCAL_BYTES"},
               "platform_state": {"const": "NEEDS_PLATFORM_MATERIALS"}}
    if name == "prepared.articles.read":
        common |= {"bundle_id": BUNDLE, "version": VERSION, "revision": integer, "content_digest": DIGEST,
                   "article": ARTICLE, "assets": {"type": "array", "items": asset, "minItems": 1, "maxItems": 5},
                   "material_requirements": {"type": "array", "minItems": 1, "maxItems": 5, "items": schema({
                       "slot": string(64), "asset_ref": ASSET, "needs": {"enum": ["PERMANENT_COVER", "UPLOADED_BODY_URL"]}})}}
    else:
        common |= {"request_key": ID, "input_operation_id": ID, "input_state": {"const": "COMMITTED"}}
        if name.startswith("prepared.assets."):
            common |= asset["properties"] | {"source_kind": {"enum": ["codex_local", "gpt_fixed_fixture"]}}
        else:
            common |= {"bundle_id": BUNDLE, "version": VERSION, "revision": integer, "content_digest": DIGEST}
    return schema(common)


def prepared_openapi(origin=None):
    """Noninstalled template: the unchanged five routes plus ten prepared routes."""
    result = openapi(origin)
    result["info"]["version"] = "0.7.0-local-host-workflow"
    for route in ROUTES:
        operation = {"operationId": route.operation_id, "summary": route.summary,
                     "description": SPECS[route.tool][0] + " Select connection first. Use returned refs; keep each original key. UNKNOWN: query only. Real GPT/WeChat unconnected.",
                     "x-openai-isConsequential": route.method == "POST", "security": [{"WCEUserOAuth": [route.scope]}],
                     "responses": deepcopy(next(iter(result["paths"].values()))["get"]["responses"])}
        operation["responses"]["200"]["content"]["application/json"]["schema"] = result_schema(route.tool)
        if route.method == "POST":
            operation["requestBody"] = {"required": True, "content": {"application/json": {"schema": route.arguments()}}}
        else:
            spec = arguments(route.tool)
            operation["parameters"] = [{"name": key, "in": "path", "required": True,
                                        "schema": deepcopy(spec["properties"][key])}
                                       for key in re.findall(r"\{([a-z_]+)\}", route.path)]
        result["paths"].setdefault(route.path, {})[route.method.lower()] = operation
    return result
