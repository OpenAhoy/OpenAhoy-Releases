"""Closed five-operation GPT Actions contract. No authentication implementation."""
import argparse
from copy import deepcopy
from dataclasses import dataclass
import ipaddress
import json
from pathlib import Path
import re
from urllib.parse import urlsplit

from .tools import TOOL_SPECS

SAFE_ID = {"type": "string", "minLength": 1, "maxLength": 128,
           "pattern": "^[A-Za-z0-9_-]+$"}
MAX_REQUEST_BYTES = 96 * 1024
MAX_JSON_CHARS = 99999
MAX_RESPONSE_BYTES = 400000


@dataclass(frozen=True)
class Route:
    method: str
    path: str
    tool: str
    operation_id: str
    summary: str
    scope: str

    def arguments(self):
        spec = deepcopy(TOOL_SPECS[self.tool][2])
        for name in ("connection_id", "draft_id", "operation_id"):
            if name in spec["properties"]:
                spec["properties"][name] = deepcopy(SAFE_ID)
        return spec

    def match(self, path):
        names = re.findall(r"\{([a-z_]+)\}", self.path)
        pattern = re.escape(self.path)
        for name in names:
            pattern = pattern.replace(re.escape("{" + name + "}"), r"([A-Za-z0-9_-]{1,128})")
        found = re.fullmatch(pattern, path)
        return dict(zip(names, found.groups())) if found else None


ROUTES = (
    Route("GET", "/v1/connections", "connections.list", "listConnections", "查看本人可访问公众号（当前合成状态）", "wce:read"),
    Route("GET", "/v1/connections/{connection_id}/capabilities", "connections.capabilities", "getConnectionCapabilities", "查看所选公众号能力", "wce:read"),
    Route("POST", "/v1/drafts", "drafts.save", "saveDraft", "保存草稿固定版本（当前本地模拟）", "wce:draft"),
    Route("GET", "/v1/connections/{connection_id}/drafts/{draft_id}", "drafts.read", "readDraft", "读回草稿核对内容和版本", "wce:read"),
    Route("GET", "/v1/connections/{connection_id}/operations/{operation_id}", "operations.get", "getOperation", "查询已有操作结果，不重复写入", "wce:read"),
)


def https_origin(value):
    """Validate a future public origin syntactically, without DNS or deployment."""
    if (not isinstance(value, str) or len(value) > 253 or not value.isascii()
            or any(char.isspace() or ord(char) < 32 for char in value) or "?" in value or "#" in value):
        raise ValueError("PUBLIC_HTTPS_ORIGIN_REQUIRED")
    parsed = urlsplit(value)
    host = parsed.hostname
    try:
        port = parsed.port
    except ValueError:
        raise ValueError("PUBLIC_HTTPS_ORIGIN_REQUIRED") from None
    if (parsed.scheme != "https" or parsed.username is not None or parsed.password is not None
            or parsed.path not in ("", "/") or parsed.query or parsed.fragment or port not in (None, 443)
            or not host or ":" in host or not re.fullmatch(r"[a-z0-9.-]+", host)):
        raise ValueError("PUBLIC_HTTPS_ORIGIN_REQUIRED")
    if parsed.netloc.lower() not in {host, host + ":443"}:
        raise ValueError("PUBLIC_HTTPS_ORIGIN_REQUIRED")
    try:
        ipaddress.ip_address(host)
    except ValueError:
        pass
    else:
        raise ValueError("PUBLIC_HTTPS_ORIGIN_REQUIRED")
    labels = host.split(".")
    if (len(labels) < 2 or len(labels[-1]) < 2 or labels[-1].isdigit()
            or any(not 1 <= len(p) <= 63 or p.startswith("-") or p.endswith("-") for p in labels)
            or labels[-1] in {"localhost", "local", "internal", "invalid", "test", "example"}
            or host in {"example.com", "example.org", "example.net"}):
        raise ValueError("PUBLIC_HTTPS_ORIGIN_REQUIRED")
    return "https://" + host


def result_schema(tool):
    """Document fields that GPT needs for account selection and readback."""
    string = {"type": "string"}
    props = {"transport": {"const": "mock"}, "mode": {"const": "test"},
             "connected": {"const": False}, "platform_verified": {"const": False},
             "runtime": {"type": "string", "enum": ["offline", "wire_fixture"]},
             "http_entrypoint": {"const": "local_preparation"}}
    required = list(props)
    if tool == "connections.list":
        props["profiles"] = {"type": "array", "items": {"type": "object", "properties": {
            "connection_id": deepcopy(SAFE_ID), "profile_id": string, "account_id": string,
            "state": string, "capabilities": {"type": "object", "additionalProperties": {"type": "string"}},
            "authorization_generation": {"type": "integer"}, "token_revision": {"type": "integer"}},
            "required": ["connection_id", "profile_id", "state", "capabilities"], "additionalProperties": True}}
        required += ["profiles"]
    elif tool == "connections.capabilities":
        props |= {"connection_id": deepcopy(SAFE_ID), "capabilities": {"type": "object", "additionalProperties": {"type": "string"}},
                  "authorization_generation": {"type": "integer"}, "account_type": string, "qualification": string}
        required += ["connection_id", "capabilities", "authorization_generation"]
    elif tool == "drafts.read":
        props |= {"draft_id": deepcopy(SAFE_ID), "version": string, "content_digest": string,
                  "content": {"type": "object", "properties": {"title": string, "body": string,
                              "material_ids": {"type": "array", "items": string}},
                              "required": ["title", "body", "material_ids"], "additionalProperties": False}}
        required += ["draft_id", "version", "content_digest", "content"]
    else:
        props |= {"operation_id": deepcopy(SAFE_ID), "connection_id": deepcopy(SAFE_ID), "action": string,
                  "state": {"type": "string", "enum": ["SUBMITTED", "PROCESSING", "SUCCEEDED", "FAILED", "RESULT_UNKNOWN"]},
                  "platform_ref": {"type": ["string", "null"]},
                  "result": {"type": "object", "properties": {"draft_id": string, "version": string, "content_digest": string},
                             "additionalProperties": True}}
        required += ["operation_id", "connection_id", "state", "result"]
    return {"type": "object", "properties": props, "required": required, "additionalProperties": True}


def openapi(origin=None):
    """Without origin this is an intentionally non-installable offline template."""
    base = https_origin(origin) if origin is not None else None
    error_schema = {"type": "object", "properties": {"error": {"type": "string"}},
                    "required": ["error"], "additionalProperties": True}
    paths = {}
    for route in ROUTES:
        responses = {"200": {"description": "本地合成结果；mock/test，connected=false，platform_verified=false",
                              "content": {"application/json": {"schema": result_schema(route.tool)}}}}
        for status in (400, 401, 403, 404, 405, 408, 409, 413, 414, 415, 417, 431, 500, 503, 505):
            responses[str(status)] = {"description": "拒绝或不可用；error为脱敏错误码",
                                      "content": {"application/json": {"schema": deepcopy(error_schema)}}}
        operation = {"operationId": route.operation_id, "summary": route.summary,
                     "description": "W04A准备态；真实OAuth与微信API未接通。仅已有授权；不得传Actor、秘密、权限或fixture开关。",
                     "x-openai-isConsequential": route.method == "POST",
                     "security": [{"WCEUserOAuth": [route.scope]}], "responses": responses}
        if route.method == "POST":
            operation["requestBody"] = {"required": True, "content": {"application/json": {"schema": route.arguments()}}}
            operation["description"] += " material_ids必须由可信管理侧准备；无图片上传工具。request_key绑定相同内容；未知结果先查原操作，不自动再POST。"
        else:
            operation["parameters"] = [{"name": key, "in": "path", "required": True, "schema": deepcopy(SAFE_ID)}
                                       for key in re.findall(r"\{([a-z_]+)\}", route.path)]
        paths.setdefault(route.path, {})[route.method.lower()] = operation
    flows = {"authorizationCode": {"authorizationUrl": base + "/oauth/authorize" if base else "/oauth/authorize",
                                   "tokenUrl": base + "/oauth/token" if base else "/oauth/token",
                                   "scopes": {"wce:read": "读取本人已授权公众号、草稿和结果", "wce:draft": "保存本人已授权公众号草稿"}}}
    result = {"openapi": "3.1.0", "info": {"title": "WCE公众号草稿 Actions 准备包", "version": "0.4.0-local",
              "description": "仅准备配置，非安装或上线回执。真实OAuth及腾讯授权/API未实现。模板无servers，需未来有效HTTPS origin。"},
              "x-wce-readiness": "PREPARATION_ONLY_NOT_DEPLOYED",
              "x-wce-limits": {"requestUtf8Bytes": MAX_REQUEST_BYTES, "requestJsonChars": MAX_JSON_CHARS,
                               "responseUtf8Bytes": MAX_RESPONSE_BYTES, "responseJsonChars": MAX_JSON_CHARS},
              "security": [{"WCEUserOAuth": ["wce:read"]}], "paths": paths,
              "components": {"securitySchemes": {"WCEUserOAuth": {"type": "oauth2", "flows": flows}}}}
    if base:
        result["servers"] = [{"url": base}]
    return result


def main():
    parser = argparse.ArgumentParser(description="生成未来GPT Actions配置；不会部署或建立OAuth端点")
    parser.add_argument("--origin", required=True, help="管理侧未来公开HTTPS origin，仅语法检查")
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    try:
        result = openapi(args.origin)
    except ValueError:
        parser.error("需要有效公开HTTPS origin（仅443，无路径/秘密/query/fragment/模板/IP）")
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n")
    print("PREPARATION_ONLY_NOT_DEPLOYED: schema generated; OAuth/API readiness unverified")


if __name__ == "__main__":
    main()
