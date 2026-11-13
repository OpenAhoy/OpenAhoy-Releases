"""Trusted nonsecret identity and scoped, already acquired memory leases.

There is no environment, config, keychain, acquisition or refresh implementation.
None of these management objects is accepted by model tool arguments.
"""
from dataclasses import dataclass, field
import math

from .contracts import Actor, Secret, WCEError
from .prepared_contracts import DIGEST, ID, strict_validate
from .service import digest

SOURCES = {'SYNTHETIC_SETUP', 'OPERATOR_ATTESTED'}
APIS = ('material.add_material', 'media.uploadimg', 'draft.add', 'draft.get')
READ_APIS = ('material.batchget_material', 'material.get_material')
DRAFT_READ_APIS = ('draft.batchget', 'draft.get')
KINDS = frozenset(APIS) | {'qualification', 'egress', 'quota', 'token_route', 'news_schema_resolution'}


def finite(value):
    return type(value) in (int, float) and math.isfinite(value)


@dataclass(frozen=True)
class OwnerEvidence:
    kind: str
    account: str
    resource: str
    generation: int
    expires: float
    state: str
    source_sha256: str
    source_kind: str


@dataclass(frozen=True)
class OwnProfile:
    actor: Actor
    connection_id: str
    account_id: str
    resource_id: str
    generation: int
    epoch: int
    token_revision: int
    expires: float
    session_expires: float
    grant_expires: float
    credential_expires: float
    credential_handle: str = field(repr=False)
    source_kind: str
    granted_actions: frozenset
    evidence_tuple: tuple
    active: bool = True

    def binding(self):
        return {'tenant': self.actor.tenant_id, 'principal': self.actor.principal_id,
                'client': self.actor.client_id, 'session': self.actor.session_id,
                'connection': self.connection_id, 'account': self.account_id,
                'resource': self.resource_id, 'generation': self.generation,
                'epoch': self.epoch, 'source_kind': self.source_kind}

    def fence(self):
        return digest(self.binding() | {'token_revision': self.token_revision,
            'deadlines': [self.expires, self.session_expires, self.grant_expires, self.credential_expires],
            'handle_digest': digest(self.credential_handle), 'active': self.active,
            'granted': sorted(self.granted_actions), 'evidence': [vars(e) for e in self.evidence_tuple]})


def validate_profile(profile, now):
    try:
        if type(profile) is not OwnProfile or type(profile.actor) is not Actor or not finite(now):
            raise ValueError()
        for value in (*vars(profile.actor).values(), profile.connection_id, profile.account_id,
                      profile.resource_id, profile.credential_handle):
            strict_validate(value, ID)
        if (type(profile.active) is not bool or not profile.active or profile.source_kind not in SOURCES
                or any(type(n) is not int or n < 0 for n in (profile.generation, profile.epoch, profile.token_revision))
                or profile.generation < 1
                or any(not finite(t) or t <= now for t in (profile.expires, profile.session_expires,
                                                           profile.grant_expires, profile.credential_expires))
                or type(profile.granted_actions) is not frozenset
                or profile.granted_actions - (frozenset(APIS + READ_APIS + DRAFT_READ_APIS) | {'local.read', 'local.write'})
                or type(profile.evidence_tuple) is not tuple):
            raise ValueError()
        seen = set()
        for e in profile.evidence_tuple:
            if (type(e) is not OwnerEvidence or e.kind not in KINDS | frozenset(READ_APIS + DRAFT_READ_APIS) or e.kind in seen
                    or e.account != profile.account_id or e.resource != profile.resource_id
                    or type(e.generation) is not int or e.generation != profile.generation
                    or not finite(e.expires) or e.state not in {'AVAILABLE', 'UNKNOWN', 'REVOKED'}
                    or e.source_kind != profile.source_kind):
                raise ValueError()
            strict_validate(e.source_sha256, DIGEST)
            seen.add(e.kind)
        return profile
    except Exception:
        raise WCEError('OWN_AUTHORIZATION_UNAVAILABLE') from None


def require_evidence(profile, kinds, now):
    found = {e.kind: e for e in profile.evidence_tuple}
    if any(k not in found or found[k].state != 'AVAILABLE' or found[k].expires <= now for k in kinds):
        raise WCEError('OWN_PLATFORM_CONDITION_UNVERIFIED')


class OwnRegistry:
    """Host owned lookup; callers cannot change it through the model boundary."""
    def __init__(self, profiles=()):
        self.profiles = {(p.actor, p.connection_id): p for p in profiles}

    def resolve(self, actor, connection):
        if type(actor) is not Actor:
            raise WCEError('OWN_AUTHORIZATION_UNAVAILABLE')
        value = self.profiles.get((actor, connection))
        if type(value) is not OwnProfile or value.actor != actor or value.connection_id != connection:
            raise WCEError('OWN_AUTHORIZATION_UNAVAILABLE')
        return value


@dataclass(frozen=True)
class OwnTokenScope:
    actor: Actor
    connection: str
    account: str
    resource: str
    generation: int
    epoch: int
    token_revision: int
    handle: str = field(repr=False)

    @classmethod
    def from_profile(cls, p):
        return cls(p.actor, p.connection_id, p.account_id, p.resource_id,
                   p.generation, p.epoch, p.token_revision, p.credential_handle)


@dataclass(frozen=True)
class OwnTokenLease:
    scope: OwnTokenScope
    token: Secret = field(repr=False)
    expires_at: float


class ScopedOwnTokenBroker:
    """Resolve an existing memory lease only; never acquire, refresh or retry."""
    def __init__(self, loader=None, current_validator=None, clock=None):
        import time
        self.loader, self.validator, self.clock = loader, current_validator, clock or time.time

    def current(self, scope, lease):
        try:
            return (type(lease) is OwnTokenLease and type(lease.scope) is OwnTokenScope
                    and lease.scope == scope and type(lease.token) is Secret
                    and finite(lease.expires_at) and lease.expires_at > self.clock()
                    and self.validator is not None and self.validator(scope, lease) is True)
        except Exception:
            return False

    def load(self, scope):
        try:
            lease = self.loader(scope) if self.loader is not None else None
        except Exception:
            raise WCEError('OWN_TOKEN_UNAVAILABLE') from None
        if not self.current(scope, lease):
            raise WCEError('OWN_TOKEN_UNAVAILABLE')
        return lease
