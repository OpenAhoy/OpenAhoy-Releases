"""Content-free pre-activation scan, never completion or execution authority.

Only a current registered role and its exact original terminal tail can select
this derived cache. Ambiguous/non-quiescent history uses the old strict lane.
"""
from copy import deepcopy
from dataclasses import dataclass
from hashlib import sha256
import json
from .draft_revision_native_source import require,canonical,registration_digest
from .slot_source_files import original_record
from .slot_native_codec import initial_state,_validate_state,consume

PROFILE='PRODUCER_TERMINAL_PREFIX_V2'
_SEAL=object()


class SeedNotApplicable(Exception):
    """Not a grant/denial: select the existing strict cache, without resetting it."""


@dataclass(frozen=True)
class ProducerSeed:
    frozen:bytes
    _verify:object
    _seal:object
    def __post_init__(self):require(self._seal is _SEAL,'SLOT_UNCHECKED_PRODUCER_SEED')
    @property
    def value(self):return json.loads(self.frozen)
    @property
    def sha256(self):return sha256(self.frozen).hexdigest()
    def fence(self):self._verify();return True


def for_role(role,guard):
    from .slot_producer_roles import ProducerRole
    require(type(role)is ProducerRole,'SLOT_UNCHECKED_ROLE');role.fence()
    source=role.lookup.locate();activation=deepcopy(role.value['activation'])
    require(activation['registration_sha256']==registration_digest(source),
        'SLOT_ROLE_CONTINUITY_REQUIRED')
    tail=original_record(source,activation['tail'],guard);row=tail.value;data=row['payload']
    if (row['type']!='event_msg' or data.get('type') not in {'task_complete','task_aborted','turn_aborted'}
            or type(data.get('turn_id'))is not str or not data['turn_id']
            or type(data.get('root_turn_id'))is not str or not data['root_turn_id']):
        return None
    require(type(activation['after_ordinal'])is int
        and activation['after_ordinal']==tail.ordinal+1
        and activation['after_ordinal']>source.metadata_ordinal,'SLOT_ROLE_CONTINUITY_REQUIRED')
    value={'profile':PROFILE,'thread_id':source.thread_id,'producer_role':role.value['producer_role'],
        'registration_sha256':registration_digest(source),'activation':activation}
    def verify():
        role.fence();current=role.lookup.locate()
        require(registration_digest(current)==value['registration_sha256']
            and role.value['activation']==activation,'SLOT_PRODUCER_SEED_CHANGED')
        require(original_record(current,activation['tail'],guard).reference()==tail.reference(),
            'SLOT_PRODUCER_SEED_CHANGED')
    verify();return ProducerSeed(canonical(value),verify,_SEAL)


def initial(seed,source,*,projection_profile=None):
    require(type(seed)is ProducerSeed,'SLOT_UNCHECKED_PRODUCER_SEED');seed.fence()
    require(seed.value['registration_sha256']==registration_digest(source),
        'SLOT_PRODUCER_SEED_CHANGED')
    return {'profile':PROFILE,'seed_sha256':seed.sha256,'phase':'PREFIX',
        'projection_profile':projection_profile,'next_ordinal':source.metadata_ordinal,
        'frontier':{},'unambiguous':True,'codec':None}


def validate(seed,state,*,projection_profile=None):
    require(type(seed)is ProducerSeed and type(state)is dict and set(state)=={
        'profile','seed_sha256','phase','next_ordinal','frontier','unambiguous','codec','projection_profile'}
        and state['profile']==PROFILE and state['seed_sha256']==seed.sha256
        and state['projection_profile']==projection_profile
        and type(state['next_ordinal'])is int and state['next_ordinal']>=0
        and type(state['frontier'])is dict and type(state['unambiguous'])is bool,
        'SLOT_PRODUCER_SEED_CACHE_CHANGED')
    after=seed.value['activation']['after_ordinal']
    if state['phase']=='PREFIX':
        require(state['next_ordinal']<after and state['codec']is None
            and all(type(k)is str and k and type(v)is str and v for k,v in state['frontier'].items()),
            'SLOT_PRODUCER_SEED_CACHE_CHANGED')
    else:
        require(state['phase']=='ACTIVE' and state['next_ordinal']>=after
            and state['frontier']=={} and state['unambiguous']is True,
            'SLOT_PRODUCER_SEED_CACHE_CHANGED')
        _validate_state(state['codec'])
        require(state['codec']['thread_id']==seed.value['thread_id']
            and state['codec'].get('projection_profile')==projection_profile
            and state['codec']['next_ordinal']==state['next_ordinal'],
            'SLOT_PRODUCER_SEED_CACHE_CHANGED')


def advance(seed,state,record,*,projection_profile=None):
    validate(seed,state,projection_profile=projection_profile);require(record.ordinal==state['next_ordinal'],'SLOT_PRODUCER_SEED_CACHE_CHANGED')
    result=deepcopy(state);result['next_ordinal']+=1;value=record.value
    if result['phase']=='ACTIVE':
        result['codec'],facts=consume(result['codec'],{key:value[key]for key in ('ordinal','type','payload')})
        validate(seed,result,projection_profile=projection_profile);return result,facts
    data=value['payload'];kind=data.get('type');frontier=result['frontier']
    if value['type']=='event_msg' and kind in {'task_started','task_complete','task_aborted','turn_aborted'}:
        turn,root=data.get('turn_id'),data.get('root_turn_id')
        valid=(type(turn)is str and bool(turn) and turn.isprintable()
            and type(root)is str and bool(root) and root.isprintable())
        if kind=='task_started':
            if not valid or turn in frontier:result['unambiguous']=False
            else:frontier[turn]=root
        elif not valid or frontier.get(turn)!=root:result['unambiguous']=False
        else:del frontier[turn]
    elif value['type']=='turn_context':
        turn=data.get('turn_id')
        if type(turn)is not str or turn not in frontier:result['unambiguous']=False
    activation=seed.value['activation']
    if result['next_ordinal']==activation['after_ordinal']:
        require(record.reference()==activation['tail'],'SLOT_PRODUCER_SEED_CHANGED')
        if not result['unambiguous'] or frontier:raise SeedNotApplicable()
        result['phase']='ACTIVE';result['codec']=initial_state(seed.value['thread_id'],result['next_ordinal'],
            projection_profile=projection_profile)
    validate(seed,result,projection_profile=projection_profile);return result,[]


def pending_codec(seed,state,*,projection_profile=None):
    validate(seed,state,projection_profile=projection_profile)
    return state['codec'] if state['phase']=='ACTIVE' else {'turns':{}}
