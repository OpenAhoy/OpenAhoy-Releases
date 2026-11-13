"""Private, pinned review inputs. These files are never authorization tickets."""
from dataclasses import dataclass
from datetime import datetime
from hashlib import sha256
from pathlib import Path

from .contracts import WCEError
from .own_auth import APIS, READ_APIS, DRAFT_READ_APIS
from .own_bootstrap_ipc import config_digest
from .own_bootstrap_security import decode, private_read
from .prepared_contracts import strict_validate, ID
from .own_contracts import SPECS
from .own_workflow import binding_validate

KINDS = frozenset(APIS) | {'qualification', 'egress', 'quota'}
SOURCE_FIELDS = {'schema', 'kind', 'account', 'resource', 'connection', 'generation', 'epoch',
    'source', 'prepared_at', 'statement_to_review', 'human_confirmation',
    'requested_validity_seconds', 'source_kind'}


@dataclass(frozen=True)
class ReviewRequest:
    path: Path
    pin: tuple
    raw: bytes
    data: dict
    sources: tuple

    @classmethod
    def load(cls, config, profile, path, now):
        # An explicitly selected file in the already private account directory;
        # no arbitrary source paths, URL fetches, environment or secret discovery.
        path = Path(path)
        if path.parent != config.root:
            raise WCEError('BOOTSTRAP_REVIEW_INVALID')
        raw, pin = private_read(path)
        data = decode(raw)
        try:
            if type(data) is not dict or type(data.get('schema')) is not int or data['schema'] not in (1, 2, 3, 4, 5, 6, 7):
                raise ValueError()
            recovery = data['schema'] in (2, 3)
            fields = {'schema', 'config_digest', 'binding', 'selector', 'sources'}
            kinds_required = KINDS | (frozenset(READ_APIS) if recovery else frozenset())
            if data['schema'] == 7:
                from .prepared_contracts import DIGEST
                from .own_draft_reconcile import POLICY
                fields.add('draft_recovery')
                kinds_required = frozenset(DRAFT_READ_APIS) | {'qualification', 'egress', 'quota'}
                properties = {'request_key': ID, 'candidate_scope': DIGEST,
                    'policy': {'type': 'string', 'enum': [POLICY]}}
                strict_validate(data['draft_recovery'], {'type': 'object', 'properties': properties,
                    'required': list(properties), 'additionalProperties': False})
            if data['schema'] == 4:
                from .prepared_contracts import DIGEST
                fields.add('body_recovery')
                properties = {'original_request_key': ID, 'candidate_scope': DIGEST,
                    'maximum_new_sends': {'type': 'integer', 'enum': [1]}}
                value = data['body_recovery']
                if (type(value) is not dict or set(value) != set(properties) | {'duplicate_image_risk_accepted'}
                        or value['duplicate_image_risk_accepted'] is not True):
                    raise ValueError()
                strict_validate({k: value[k] for k in properties}, {'type': 'object', 'properties': properties,
                    'required': list(properties), 'additionalProperties': False})
            if data['schema'] == 5:
                from .prepared_contracts import DIGEST
                fields.add('body_followup')
                value = data['body_followup']
                if type(value) is not dict or value.get('action') not in {'SEND_ONCE', 'ADOPT_OBSERVATION_ONLY'}:
                    raise ValueError()
                adopt = value['action'] == 'ADOPT_OBSERVATION_ONLY'
                properties = {'original_request_key': ID, 'candidate_scope': DIGEST,
                    'policy': {'type': 'string', 'enum': ['BODY_URL_RESPONSE_V1']},
                    'action': {'type': 'string', 'enum': [value['action']]},
                    'maximum_new_sends': {'type': 'integer', 'enum': [0 if adopt else 1]}}
                if adopt:
                    properties.update(followup_id=ID, intent_digest=DIGEST, observation_digest=DIGEST)
                if (set(value) != set(properties) | {'duplicate_image_risk_accepted'}
                        or value['duplicate_image_risk_accepted'] is not True):
                    raise ValueError()
                strict_validate({k: value[k] for k in properties}, {'type': 'object', 'properties': properties,
                    'required': list(properties), 'additionalProperties': False})
            if data['schema'] == 6:
                from .prepared_contracts import DIGEST
                from .own_body_attempt import SEND, ADOPT, POLICY
                from .upload_wire import BODY_API_REFERENCE_POLICY
                fields.add('body_attempt')
                value = data['body_attempt']
                if type(value) is not dict or value.get('action') not in {SEND, ADOPT}:
                    raise ValueError()
                adopt = value['action'] == ADOPT
                properties = {'original_request_key': ID, 'draft_request_key': ID, 'candidate_scope': DIGEST,
                    'policy': {'type': 'string', 'enum': [POLICY]},
                    'response_policy': {'type': 'string', 'enum': [BODY_API_REFERENCE_POLICY]},
                    'action': {'type': 'string', 'enum': [value['action']]},
                    'maximum_total_admissions': {'type': 'integer', 'enum': [4]},
                    'maximum_new_sends': {'type': 'integer', 'enum': [0 if adopt else 1]}}
                if adopt:
                    properties.update(attempt_id=ID, owner=ID, intent_digest=DIGEST, observation_digest=DIGEST)
                if (set(value) != set(properties) | {'duplicate_image_risk_accepted'}
                        or value['duplicate_image_risk_accepted'] is not True):
                    raise ValueError()
                strict_validate({k: value[k] for k in properties}, {'type': 'object', 'properties': properties,
                    'required': list(properties), 'additionalProperties': False})
            if recovery:
                fields.add('reconcile_cover')
                properties = {'request_key': ID}
                if data['schema'] == 3:
                    from .own_png import POLICY_ID
                    properties['match_policy'] = {'type': 'string', 'enum': [POLICY_ID]}
                strict_validate(data['reconcile_cover'], {'type': 'object', 'properties': properties,
                    'required': list(properties), 'additionalProperties': False})
            if (set(data) != fields
                    or data['config_digest'] != config_digest(config) or data['binding'] != profile.binding()
                    or type(data['selector']) is not dict
                    or set(data['selector']) != {'bundle_id', 'version', 'content_digest'}
                    or type(data['sources']) is not list or len(data['sources']) != len(kinds_required)):
                raise ValueError()
            spec = SPECS['own.articles.read']['properties']
            binding_validate(data['binding'])
            for key in ('bundle_id', 'version'):
                strict_validate(data['selector'][key], spec[key])
            strict_validate(data['selector']['content_digest'], {'type': 'string', 'maxLength': 64, 'pattern': '^[a-f0-9]{64}$'})
            sources, kinds = [], set()
            for entry in data['sources']:
                if (type(entry) is not dict or set(entry) != {'source_bytes', 'source_sha256'}
                        or type(entry['source_bytes']) is not str):
                    raise ValueError()
                source_bytes = entry['source_bytes'].encode('utf-8')
                if sha256(source_bytes).hexdigest() != entry['source_sha256']:
                    raise ValueError()
                source = decode(source_bytes)
                if (type(source) is not dict or set(source) != SOURCE_FIELDS
                        or type(source['schema']) is not int or source['schema'] != 1
                        or source['kind'] not in kinds_required or source['kind'] in kinds
                        or source['source_kind'] != profile.source_kind
                        or source['human_confirmation'] != 'PENDING_NOT_REGISTERED'
                        or type(source['requested_validity_seconds']) is not int
                        or not 0 < source['requested_validity_seconds'] <= 3600):
                    raise ValueError()
                for key, expected in (('account', profile.account_id), ('resource', profile.resource_id),
                        ('connection', profile.connection_id), ('generation', profile.generation), ('epoch', profile.epoch)):
                    if type(source[key]) is not type(expected) or source[key] != expected:
                        raise ValueError()
                for key, maximum in (('source', 512), ('statement_to_review', 2048)):
                    if type(source[key]) is not str or not 0 < len(source[key]) <= maximum:
                        raise ValueError()
                observed = datetime.fromisoformat(source['prepared_at'])
                if observed.tzinfo is None or observed.timestamp() > now:
                    raise ValueError()
                expires = observed.timestamp() + source['requested_validity_seconds']
                if expires <= now:
                    raise ValueError()
                sources.append((source, entry['source_sha256'], expires))
                kinds.add(source['kind'])
            if kinds != kinds_required:
                raise ValueError()
            return cls(path, pin, raw, data, tuple(sources))
        except (ValueError, TypeError, KeyError, OverflowError):
            raise WCEError('BOOTSTRAP_REVIEW_INVALID') from None

    def check(self, config, profile, now):
        config.check(now)
        raw, pin = private_read(self.path)
        if raw != self.raw or pin != self.pin or self.data['config_digest'] != config_digest(config):
            raise WCEError('BOOTSTRAP_REVIEW_CHANGED')
        if self.data['binding'] != profile.binding() or any(expiry <= now for _, _, expiry in self.sources):
            raise WCEError('BOOTSTRAP_REVIEW_EXPIRED')

    def snapshot(self, runtime):
        runtime.paths_current()
        self.check(runtime.config, runtime.profile, runtime.clock())
        s = self.data['selector']
        # Trusted host read before hidden input, so secret reflection can be
        # rejected before anything from this material is printed.
        with _history_transaction(runtime.workflow.db) as (db, history_locators):
            runtime.workflow._resource(db, runtime.profile, history_locators=history_locators)
            manifest, content_digest = runtime.workflow._bundle(db, runtime.profile, s['bundle_id'], s['version'])
        if content_digest != s['content_digest']:
            raise WCEError('OWN_SNAPSHOT_CHANGED')
        return manifest | {'content_digest': content_digest}


from .draft_group_history_context import history_transaction as _history_transaction
