"""WCE business contracts; these are not verified Tencent wire schemas."""
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Callable, Protocol


class WCEError(Exception):
    def __init__(self, code: str):
        self.code = code
        super().__init__(code)


class Capability(StrEnum):
    MATERIAL = "material.write"
    DRAFT = "draft.write"
    READ_DRAFT = "draft.read"
    PREVIEW = "preview.send"
    PUBLISH = "publication.submit"
    STATUS = "publication.status"
    MASS_SEND = "mass_send"


class CapabilityState(StrEnum):
    AVAILABLE = "available"
    UNVERIFIED = "qualification_unverified"
    UNAUTHORIZED = "authorization_required"
    NOT_OPEN = "platform_not_open"
    NOT_IMPLEMENTED = "not_implemented"
    REVOKED = "revoked"


class PublicationState(StrEnum):
    SUBMITTED = "SUBMITTED"
    PROCESSING = "PROCESSING"
    SUCCEEDED = "SUCCEEDED"
    FAILED = "FAILED"
    UNKNOWN = "RESULT_UNKNOWN"


@dataclass(frozen=True)
class Actor:
    """Provided by trusted host authentication, never by tool arguments."""
    tenant_id: str
    principal_id: str
    client_id: str
    session_id: str


@dataclass(frozen=True)
class Connection:
    id: str
    tenant_id: str
    account_type: str
    qualification: str
    secret_ref: str = field(repr=False)
    capabilities: dict[Capability, CapabilityState]
    expires_at: float
    preview_targets: tuple[str, ...] = ("mock-reader",)
    authorization_generation: int = 1
    active: bool = True
    evidence: str = "synthetic"


class Secret:
    """Redacted diagnostic representation; only adapters receive this object."""
    __slots__ = ("__value",)

    def __init__(self, value: str):
        self.__value = value

    def reveal_for_adapter(self) -> str:
        return self.__value

    def __repr__(self) -> str:
        return "Secret(<redacted>)"

    __str__ = __repr__


class SecretProvider(Protocol):
    def get(self, tenant_id: str, connection_id: str, secret_ref: str) -> Secret: ...


class FakeSecretProvider:
    """Synthetic fixtures only. There is no real credential input path."""
    def get(self, tenant_id: str, connection_id: str, secret_ref: str) -> Secret:
        return Secret("SYNTHETIC_WCE_CANARY_" + tenant_id + "_" + connection_id)


@dataclass(frozen=True)
class Receipt:
    platform_ref: str


@dataclass(frozen=True)
class Status:
    state: PublicationState


class UncertainResult(Exception):
    """The side effect may have happened. Never automatically submit again."""
    def __init__(self, platform_ref: str | None = None):
        self.platform_ref = platform_ref
        super().__init__("RESULT_UNKNOWN")


class RejectedOperation(Exception):
    """Adapter certifies that a write was rejected before a side effect."""


@dataclass(frozen=True)
class DraftCallContext:
    """Trusted business snapshot, never supplied by model tool arguments."""
    actor: Actor
    connection_id: str
    generation: int
    expires_at: float
    secret_ref: str = field(repr=False)
    synthetic: bool
    draft_id: str
    version: str
    content_digest: str
    materials: tuple[tuple[str, str], ...]
    operation_id: str | None = None
    resource_id: str | None = None
    token_revision: int = 0
    registry_guard: Callable[[str], None] | None = field(default=None, repr=False, compare=False)
    artifact_generation: int | None = None
    artifact_operation_id: str | None = None


class OfficialAccountAdapter(Protocol):
    """Separate operations, using WCE types rather than guessed API fields."""
    mode: str
    workflow_mode: str
    def bind_draft(self, context: DraftCallContext) -> "OfficialAccountAdapter": ...
    def add_material(self, connection_id: str, digest: str, credential: Secret) -> Receipt: ...
    def save_draft(self, connection_id: str, content: dict, credential: Secret) -> Receipt: ...
    def read_draft(self, connection_id: str, platform_ref: str, credential: Secret) -> dict: ...
    def preview(self, connection_id: str, draft_ref: str, targets: tuple[str, ...], credential: Secret) -> Receipt: ...
    def submit_publication(self, connection_id: str, draft_ref: str, credential: Secret) -> Receipt: ...
    def publication_status(self, connection_id: str, platform_ref: str, credential: Secret) -> Status: ...
