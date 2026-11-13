"""A host-maintained/CUP-pinned role, never producer self-attestation."""
from pathlib import Path
from dataclasses import dataclass
from .draft_revision_native_source import require,checked_guard,registration_digest
from .draft_revision_native_lookup import NativeThreadLookup,valid_thread
from .slot_native_lookup import ProducerThreadLookup
from .slot_source_files import private_json,original_record
from .publication_contract import binding

ROLE_FILE='slot-producer-roles.json'
_SEAL=object()

@dataclass(frozen=True)
class ProducerRole:
    value:dict
    lookup:object
    manifest_sha256:str
    _revalidate:object
    _seal:object
    def __post_init__(self):require(self._seal is _SEAL,'SLOT_UNCHECKED_ROLE')
    def fence(self):self._revalidate();return True


class RoleRegistry:
    """adopted_sha is supplied only by the host's precise CUP registration.

    Public discover never receives this constructor, a path, or a producer id.
    """
    def __init__(self,standing,adopted_sha,guard):
        require(type(adopted_sha)is str and len(adopted_sha)==64,'SLOT_ROLE_ADOPTION_REQUIRED')
        self.standing,self.sha,self.guard=standing,adopted_sha,guard

    def roles(self):
        standing=self.standing;standing.base_fence()
        value,raw_sha=private_json(standing.root,ROLE_FILE,self.guard)
        require(raw_sha==self.sha and type(value)is dict and set(value)=={
            'schema','purpose','principal','tenant','code_scope','standing_config_sha256','account_aliases','producers'}
            and value['schema']==1 and value['purpose']=='HOST_REGISTERED_SLOT_PRODUCERS_V1'
            and value['principal']==standing.policy.data['actor']['principal_id']
            and value['tenant']==standing.policy.data['actor']['tenant_id']
            and value['code_scope']==standing.scope['code_scope_sha256']
            and value['standing_config_sha256']==standing.config_sha
            and type(value['producers'])is list,'SLOT_ROLE_MANIFEST_UNADOPTED')
        require(type(value['account_aliases'])is dict and set(value['account_aliases'])==set(standing.value['connections'])
            and all(type(v)is list and v and all(type(a)is str and a for a in v)for v in value['account_aliases'].values()),
            'SLOT_ROLE_ALIASES_INVALID')
        self.aliases=value['account_aliases']
        seen=set();result=[]
        for entry in value['producers']:
            require(type(entry)is dict and set(entry)=={'producer_role','channel','producer_thread','owner_thread',
                'connections','schedule_id','slots','activation'} and entry['producer_role']not in seen
                and all(type(entry[k])is str and entry[k] for k in ('producer_role','channel','schedule_id'))
                and entry['owner_thread']==standing.value['owner_thread']
                and type(entry['connections'])is list and set(entry['connections'])<=set(standing.value['connections'])
                and type(entry['slots'])is list and entry['slots'] and all(type(s)is str and s for s in entry['slots']),
                'SLOT_ROLE_MANIFEST_INVALID')
            seen.add(entry['producer_role']);valid_thread(entry['producer_thread'])
            # Structure/adoption is global, native availability belongs only
            # to this account's actually selected producer role.
            if standing.policy.data['connection_id'] not in entry['connections']:continue
            native=Path(standing.value['native_root'])
            owner=NativeThreadLookup(native/'state_5.sqlite',native/'sessions',entry['owner_thread'],self.guard,
                allowed_threads=(entry['producer_thread'],))
            lookup=ProducerThreadLookup(native/'state_5.sqlite',native/'sessions',entry['producer_thread'],self.guard)
            def check(entry=entry,lookup=lookup,owner=owner):
                standing.base_fence();checked_guard(self.guard)
                require(private_json(standing.root,ROLE_FILE,self.guard)[1]==self.sha,'SLOT_ROLE_REVOKED')
                path,creator=owner._row(entry['producer_thread'])
                source=lookup.locate()
                require(source.path==path,'SLOT_ROLE_NATIVE_IDENTITY_CHANGED')
                activation=entry['activation']
                require(type(activation)is dict and set(activation)=={'registration_sha256','after_ordinal','tail'}
                    and activation['registration_sha256']==registration_digest(source)
                    and type(activation['after_ordinal'])is int
                    and activation['tail']['ordinal']+1==activation['after_ordinal'],
                    'SLOT_ROLE_CONTINUITY_REQUIRED')
                original_record(source,activation['tail'],self.guard)
                checked_guard(self.guard)
            check();result.append(ProducerRole(entry,lookup,self.sha,check,_SEAL))
        return tuple(result)
