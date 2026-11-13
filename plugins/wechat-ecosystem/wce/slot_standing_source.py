"""Real same-owner REQUEST/SLOT_RULE pins become a distinct standing source.

No legacy Authorization/bootstrap/full-history cap or caller approval is used.
"""
from dataclasses import dataclass,asdict
from hashlib import sha256
from pathlib import Path
import json,os
from .draft_revision_native_source import require,registration_digest,canonical,checked_guard
from .publication_contract import binding
from .current_publication_source import CONFIG,REQUEST,SLOT_RULE,PURPOSE,ACCOUNTS,_contract_scope
from .slot_human_lookup import HumanThreadLookup
from .slot_human_codec import initial_state,consume,pending_ordinals
from .slot_source_stream import initial,read_next,Checkpoint
from .slot_source_files import private_json,save_json,original_record
from .own_connection_policy import locked

_SEAL=object()


def _hash(value):return sha256(canonical(value)).hexdigest()


def _pin_text(source,proof,guard):
    refs=proof['references'];state=initial_state(source.thread_id,refs['started']['ordinal']);facts=[];text=None
    for key in ('started','context','raw','typed'):
        record=original_record(source,refs[key],guard);state['next_ordinal']=record.ordinal
        state,added=consume(state,record);facts.extend(added)
        if key=='typed':text=record.value['payload']['item']['content'][0]['text']
    require(len(facts)==1 and facts[0]==proof['fact'],'SLOT_STANDING_PIN_CHANGED')
    return text


@dataclass(frozen=True)
class SeedBoundary:
    source:object
    checkpoint:object
    codec_json:bytes
    references_json:bytes
    pin_proofs_json:bytes
    standing_sha256:str
    _revalidate:object
    _seal:object
    def __post_init__(self):require(self._seal is _SEAL,'SLOT_UNCHECKED_SEED')
    def fence(self):self._revalidate();return True


class StandingSource:
    """Private host construction; no tool schema accepts config/source/pins."""
    def __init__(self,policy,registry,directory,guard,*,scan_guard=None):
        self.policy=policy;self.registry=Path(registry);self.directory=Path(directory);self.guard=guard
        self.scan_guard=guard if scan_guard is None else scan_guard
        self.root=self.registry.parent;self.path=self.root/CONFIG
        self.value,self.config_sha=private_json(self.root,CONFIG,self.guard)
        value=self.value
        require(set(value)==set('schema purpose owner_thread source_thread turn_id message_id text_sha256 request_text start_ordinal native_root connections followups'.split())
            and value['schema']==1 and value['purpose']==PURPOSE
            and type(value['request_text'])is str and sha256(value['request_text'].encode()).hexdigest()==value['text_sha256']
            and value['request_text'].split('## My request:')[-1].strip()==REQUEST
            and set(value['connections'])==set(ACCOUNTS) and type(value['followups'])is list and len(value['followups'])==1,
            'SLOT_STANDING_SOURCE_REQUIRED')
        follow=value['followups'][0]
        require(set(follow)=={'turn_id','message_id','request_text','text_sha256'}
            and sha256(follow['request_text'].encode()).hexdigest()==follow['text_sha256']
            and follow['request_text'].split('## My request:')[-1].strip()==SLOT_RULE,
            'SLOT_STANDING_RULE_REQUIRED')
        require(ACCOUNTS.get(policy.data['connection_id'])==policy.data['appid']
            and value['connections'][policy.data['connection_id']]==binding(policy.data),'SLOT_STANDING_BINDING_CHANGED')
        native=Path(value['native_root']);require(native==Path.home()/'.codex' and native.is_absolute(),
            'SLOT_STANDING_NATIVE_ROOT_INVALID')
        require(type(value['start_ordinal'])is int and value['start_ordinal']>=0,
            'SLOT_STANDING_START_INVALID')
        self.semantic_start=value['start_ordinal']
        self.scope=_contract_scope(policy)
        self.lookup=HumanThreadLookup(native/'state_5.sqlite',native/'sessions',value['owner_thread'],value['source_thread'],guard)
        self.wanted={value['message_id']:{k:value[k]for k in ('turn_id','message_id','text_sha256','request_text')},
                     follow['message_id']:follow}
        self.slot_id=follow['message_id'];self.request_id=value['message_id']
        self.standing_sha=_hash({'purpose':'STANDING_SLOT_FREEPUBLISH_NO_PUSH_V1','config_sha256':self.config_sha,
            'events':[{k:item[k]for k in ('turn_id','message_id','text_sha256')}for item in (value,follow)],
            'connections':value['connections']})
        self.boundary=None

    def base_fence(self):
        checked_guard(self.guard);self.policy.check()
        require(private_json(self.root,CONFIG,self.guard)[1]==self.config_sha
            and _contract_scope(self.policy)==self.scope
            and self.value['connections'][self.policy.data['connection_id']]==binding(self.policy.data),
            'SLOT_STANDING_SOURCE_CHANGED')

    def advance(self,**work):
        self.base_fence();source=self.lookup.locate();reg=registration_digest(source)
        require(self.semantic_start>=source.metadata_ordinal,'SLOT_STANDING_START_INVALID')
        with locked(self.directory/'standing-seed.lock',nonblocking=True):
            name='standing-seed-progress-v2.json'
            if os.path.lexists(self.directory/name):
                progress,_=private_json(self.directory,name,self.guard)
                require(set(progress)=={'profile','semantic_start','config_sha256','registration_sha256',
                    'cursor','codec','references','pins'} and progress['profile']=='STANDING_CUP_START_V2'
                    and type(progress['semantic_start'])is int and progress['semantic_start']==self.semantic_start
                    and progress['config_sha256']==self.config_sha and progress['registration_sha256']==reg,
                    'SLOT_STANDING_CONTINUITY_REQUIRED')
                cursor=Checkpoint(**progress['cursor']);codec=progress['codec'];refs=progress['references'];pins=progress['pins']
                require((cursor.next_ordinal<=self.semantic_start and codec is None and refs=={} and pins=={})
                    or (cursor.next_ordinal>self.semantic_start and type(codec)is dict
                        and codec.get('next_ordinal')==cursor.next_ordinal), 'SLOT_STANDING_CONTINUITY_REQUIRED')
            else:
                cursor=initial(source);codec=None;refs={};pins={}
            if self.slot_id in pins:
                self._release(source,cursor,codec,refs,pins)
                return {'authority':False,'state':'SEED_VERIFIED','standing_sha256':self.standing_sha}
            segment=read_next(source,cursor,self.scan_guard,**work)
            for index,record in enumerate(segment.records):
                if record.ordinal<self.semantic_start:
                    # Byte/ordinal/hash-chain verification remains read_next's
                    # job; pre-grant legacy records establish no human facts.
                    continue
                if codec is None:
                    row=record.value;data=row['payload']
                    require(record.ordinal==self.semantic_start and row['type']=='event_msg'
                        and data.get('type')=='task_started' and data.get('turn_id')==self.value['turn_id'],
                        'SLOT_STANDING_START_CHANGED')
                    codec=initial_state(source.thread_id,self.semantic_start)
                refs[str(record.ordinal)]=record.reference();codec,facts=consume(codec,record)
                for fact in facts:
                    wanted=self.wanted.get(fact['item_id'])
                    if wanted is None:continue
                    require(fact['turn_id']==wanted['turn_id'] and fact['text_sha256']==wanted['text_sha256']
                        and fact['attribution']['turn_trigger']=='composer'
                        and fact['attribution']['parent_turn_id']is None
                        and fact['attribution']['initiating_agent_path']is None,'SLOT_STANDING_PIN_INVALID')
                    locations={kind:refs[str(fact[kind+'_ordinal'])]for kind in ('started','context','raw','typed')}
                    proof={'fact':fact,'references':locations}
                    require(_pin_text(source,proof,self.guard)==wanted['request_text'],'SLOT_STANDING_PIN_INVALID')
                    require(fact['item_id']not in pins or pins[fact['item_id']]==proof,'SLOT_STANDING_PIN_CONFLICT')
                    pins[fact['item_id']]=proof
                    if fact['item_id']==self.slot_id:
                        require(self.request_id in pins and pins[self.request_id]['fact']['typed_ordinal']<fact['typed_ordinal'],
                            'SLOT_STANDING_REQUEST_MISSING')
                        exact=read_next(source,cursor,self.scan_guard,work_records=index+1)
                        require(exact.records[-1].reference()==record.reference(),'SLOT_STANDING_BOUNDARY_CHANGED')
                        cursor=exact.checkpoint
                        refs={key:item for key,item in refs.items()if key in pending_ordinals(codec)}
                        self._save(name,reg,cursor,codec,refs,pins)
                        self._release(source,cursor,codec,refs,pins)
                        return {'authority':False,'state':'SEED_VERIFIED','standing_sha256':self.standing_sha}
                refs={key:item for key,item in refs.items()if key in pending_ordinals(codec)}
            cursor=segment.checkpoint;self._save(name,reg,cursor,codec,refs,pins)
            self.base_fence();require(registration_digest(self.lookup.locate())==reg,'SLOT_STANDING_SOURCE_CHANGED')
            return {'authority':False,'state':'INPUT_PENDING' if segment.state!='CURRENT' else 'PIN_MISSING',
                'checkpoint_sha256':_hash(asdict(cursor))}

    def _save(self,name,reg,cursor,codec,refs,pins):
        save_json(self.directory,name,{'profile':'STANDING_CUP_START_V2','semantic_start':self.semantic_start,
            'config_sha256':self.config_sha,'registration_sha256':reg,
            'cursor':asdict(cursor),'codec':codec,'references':refs,'pins':pins},self.guard)

    def _release(self,source,cursor,codec,refs,pins):
        def revalidate():
            self.base_fence();require(registration_digest(self.lookup.locate())==registration_digest(source),
                'SLOT_STANDING_CONTINUITY_REQUIRED')
            require(self.request_id in pins and pins[self.request_id]['fact']['started_ordinal']==self.semantic_start
                and pins[self.request_id]['fact']['turn_id']==self.value['turn_id'],
                'SLOT_STANDING_START_CHANGED')
            for ident,wanted in self.wanted.items():
                require(ident in pins and _pin_text(source,pins[ident],self.guard)==wanted['request_text'],
                    'SLOT_STANDING_PIN_CHANGED')
            require(cursor.offset==pins[self.slot_id]['references']['typed']['byte_end']
                and cursor.next_ordinal==pins[self.slot_id]['fact']['typed_ordinal']+1,'SLOT_STANDING_BOUNDARY_CHANGED')
            self.base_fence()
        revalidate()
        self.boundary=SeedBoundary(source,cursor,canonical(codec),canonical(refs),canonical(pins),self.standing_sha,revalidate,_SEAL)


def adopt_seed(cache,boundary):
    """Only a true native pin boundary can choose the initial control cursor."""
    require(type(boundary)is SeedBoundary and boundary._seal is _SEAL,'SLOT_UNCHECKED_SEED');boundary.fence()
    from .slot_control_cache import _hash as hashed,_json,_updates_hash
    from .own_connection_policy import atomic_write
    cache.initialize();source=boundary.source;reg=registration_digest(source)
    codec=json.loads(boundary.codec_json);refs=json.loads(boundary.references_json);cursor=boundary.checkpoint
    with locked(cache.lock,nonblocking=True),cache._database()as db:
        cache._validate(db);existing=cache._anchored_projection(db,reg)
        name='standing-seed-adoption.json'
        adoption={'standing_sha256':boundary.standing_sha256,'registration_sha256':reg,
            'boundary_sha256':hashed(asdict(cursor))}
        if existing is not None:
            require(private_json(cache.directory,name,cache.guard)[0]==adoption,'SLOT_STANDING_SEED_CONFLICT');return
        if os.path.lexists(cache.directory/name):
            require(private_json(cache.directory,name,cache.guard)[0]==adoption,'SLOT_STANDING_SEED_CONFLICT')
        else:save_json(cache.directory,name,adoption,cache.guard)
        boundary.fence()
        after={'thread_id':source.thread_id,'cursor':asdict(cursor),'codec':codec,'references':refs,
            'state':'SCANNING','captured_end':cursor.offset,'version':1,'delta_sha256':_updates_hash({})}
        header=cache._header(reg,hashed(after),1)
        atomic_write(cache._marker_path(reg,'pending'),{'before':None,'after':header},expected_parent=cache.root_pin)
        db.execute('BEGIN IMMEDIATE');db.execute('INSERT INTO streams VALUES(?,?,?,?,?,?,?,?,?)',
            (reg,source.thread_id,_json(asdict(cursor)),_json(codec),_json(refs),'SCANNING',cursor.offset,1,_updates_hash({})))
        db.execute('INSERT INTO segments VALUES(?,?,?,?,?,?,?)',(reg,cursor.previous_start,cursor.previous_end,
            cursor.previous_sha256,'SEED_BOUNDARY',cursor.chain_sha256,header['state_sha256']))
        boundary.fence();db.commit();cache._recover(db,reg)
        require(cache._anchored_projection(db,reg)==after,'SLOT_STANDING_ADOPTION_UNKNOWN')
        boundary.fence()
