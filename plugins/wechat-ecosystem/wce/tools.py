"""CLI tool boundary candidate, independent of any host registration or MCP server."""
from .contracts import Actor, WCEError
from .service import OfficialAccountService


def schema(required, optional=None):
    return {"type": "object", "properties": required | (optional or {}),
            "required": list(required), "additionalProperties": False}


STRING = {"type": "string", "minLength": 1, "maxLength": 65536}
ID = {"type": "string", "minLength": 1, "maxLength": 128}
STRINGS = {"type": "array", "items": ID, "minItems": 1, "maxItems": 10}
TTL = {"type": "number", "exclusiveMinimum": 0, "maximum": 3600}
TITLE = {"type": "string", "minLength": 1, "maxLength": 256}
PREVIEW_TARGETS = {"type": "array", "items": ID, "minItems": 1, "maxItems": 5}
CONFIRMATION_TTL = {"type": "number", "exclusiveMinimum": 0, "maximum": 900}

TOOL_SPECS = {
    "connections.list": ("profiles", "List accessible mock account profiles; not connected real accounts.", schema({})),
    "connections.capabilities": ("capabilities", "List synthetic account capabilities and unverified wire schema.", schema({"connection_id": ID})),
    "materials.add": ("add_material", "Create a synthetic material; no file download or real upload.", schema(
        {"connection_id": ID, "content": STRING, "request_key": ID}, {"expires_in": TTL})),
    "drafts.save": ("save_draft", "Save a fixed content version, without preview or publication.", schema(
        {"connection_id": ID, "title": TITLE, "body": STRING, "material_ids": STRINGS, "request_key": ID},
        {"draft_id": ID, "expected_version": ID})),
    "drafts.read": ("read_draft", "Read back a draft and verify its content digest.", schema({"connection_id": ID, "draft_id": ID})),
    "actions.prepare": ("prepare_action", "Prepare preview or public-article publication. Requires separate operator approval.", schema(
        {"connection_id": ID, "draft_id": ID, "version": ID, "action": {"type": "string", "enum": ["preview.send", "publication.submit"]}},
        {"targets": PREVIEW_TARGETS, "expires_in": CONFIRMATION_TTL})),
    "actions.execute": ("execute_action", "Execute an already approved action. Cannot create its own approval.", schema({"intent_id": ID, "request_key": ID})),
    "operations.get": ("operation", "Read an authorized local operation without another write.", schema({"connection_id": ID, "operation_id": ID})),
    "publications.poll": ("poll_publication", "Query a known publication reference. Never resubmit unknown writes.", schema({"connection_id": ID, "operation_id": ID})),
}


def list_tools():
    return [{"name": name, "description": description, "inputSchema": input_schema}
            for name, (_, description, input_schema) in TOOL_SPECS.items()]


def validate(value, spec):
    kind = spec["type"]
    if kind == "object":
        if not isinstance(value, dict) or set(value) - set(spec["properties"]) or set(spec["required"]) - set(value):
            raise WCEError("INVALID_TOOL_ARGUMENTS")
        for key, item in value.items():
            validate(item, spec["properties"][key])
    elif kind == "string":
        if not isinstance(value, str) or not spec.get("minLength", 0) <= len(value) <= spec.get("maxLength", 65536):
            raise WCEError("INVALID_TOOL_ARGUMENTS")
        if "enum" in spec and value not in spec["enum"]:
            raise WCEError("INVALID_TOOL_ARGUMENTS")
    elif kind == "array":
        if not isinstance(value, list) or not spec["minItems"] <= len(value) <= spec["maxItems"]:
            raise WCEError("INVALID_TOOL_ARGUMENTS")
        for item in value:
            validate(item, spec["items"])
    elif kind == "number":
        from math import isfinite
        if isinstance(value, bool) or not isinstance(value, (int, float)) or not isfinite(value) or not spec["exclusiveMinimum"] < value <= spec["maximum"]:
            raise WCEError("INVALID_TOOL_ARGUMENTS")


class ToolRouter:
    def __init__(self, service: OfficialAccountService, actor: Actor, prepared=None):
        # Host authentication supplies actor. Tool arguments cannot replace it.
        self.service, self.actor = service, actor
        if prepared is not None:
            from .prepared_host import HostDraftWorkflow
            if type(prepared) is not HostDraftWorkflow or prepared.service is not service:
                raise WCEError("SOURCE_UNCONFIGURED")
        self.prepared = prepared

    def list_tools(self):
        if self.prepared is None:
            return list_tools()
        from .prepared_contracts import list_tools as prepared_tools
        return list_tools() + prepared_tools()

    def evidence(self):
        return self.service.evidence()

    def call(self, name: str, arguments: dict):
        if self.prepared is not None and name.startswith("prepared."):
            return self.prepared.call(self.actor, name, arguments)
        if name not in TOOL_SPECS:
            raise WCEError("TOOL_NOT_IMPLEMENTED")
        method, _, input_schema = TOOL_SPECS[name]
        validate(arguments, input_schema)
        return getattr(self.service, method)(self.actor, **arguments)
