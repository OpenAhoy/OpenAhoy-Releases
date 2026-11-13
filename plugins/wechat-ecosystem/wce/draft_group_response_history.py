"""Nonrecursive Group primary/claim/source replay; reads, never grants or repairs."""
from hashlib import sha256
import json
from .contracts import WCEError
from . import draft_group_store as store
from . import draft_group_wire as wire
from . import draft_group_response_codec as codec
from .draft_group_response_files import OriginalClaimLocator,_register_locator

CONTRACT_SHA='fa30b973f6819e4f3195d6d4c338133fd78c3dc716e6ef43d814fc2ac82dff4d'


def fail():raise WCEError('GROUP_RESPONSE_HISTORY_HOLD')


def _find_claim(state,claim_id):
    found=[]
    for gid,grant in state['preview_grants'].items():
        for claim in grant['claims']:
            if claim['id']==claim_id:found.append(('PREVIEW',gid,grant,None,claim))
    for oid,op in state['operations'].items():
        for claim in op['claims']:
            if claim['id']==claim_id:found.append(('CHILD',oid,None,op,claim))
    if len(found)!=1:fail()
    return found[0]


def _admission_event(db,account,kind,holder,claim):
    event_kind='PREVIEW_READ' if kind=='PREVIEW' else claim['kind']+'_CLAIM'
    found=[];preview_ordinals={}
    for row in db.execute('SELECT * FROM group_events WHERE account_key=? AND kind=? ORDER BY seq',(account,event_kind)):
        p=json.loads(row['payload'])
        if kind=='PREVIEW':
            key=(p['grant_id'],p['api']);ordinal=preview_ordinals.get(key,0)+1;preview_ordinals[key]=ordinal
            actual=wire.digest({'binding_sha':account,'grant_id':p['grant_id'],'api':p['api'],'ordinal':ordinal})
            matches=ordinal==claim['ordinal'] and p['grant_id']==holder and p['api']==claim['api'] and p['request_sha']==claim['request_sha'] and p['at_ms']<=claim['at_ms']
        else:
            slot='ADD' if event_kind=='ADD_CLAIM' else 'DELETE:'+str(p['old_index']) if event_kind=='DELETE_CLAIM' else p['slot']
            actual=wire.digest({'binding_sha':account,'operation_id':p['operation_id'],'kind':claim['kind'],'slot':slot})
            matches=p['operation_id']==holder and slot==claim['slot']
        if actual==claim['id'] and matches:found.append((dict(row),p))
    if len(found)!=1:fail()
    return found[0]


def _expected_projection(op,claim):
    slot=claim['slot']
    if slot.startswith(('OLD_BASELINE:','OLD_PRE_SWITCH:','OLD_REFRESH:','OLD_INVALID:')):
        return op['pins']['old_projection_shas'][int(slot.split(':')[1])]
    if slot=='RECOVERY_OLD':return op['pins']['old_projection_shas'][claim['cursor']]
    return op['pins']['target_projection_sha']


def _locator_primary_facts(state,claim_id,raw,history_policy,row,payload):
    kind,holder,grant,op,claim=_find_claim(state,claim_id)
    expected=_expected_projection(op,claim) if kind=='CHILD' and claim['kind']=='GET' else None
    primary=codec.decode_primary(raw,claim_at_ms=payload['at_ms'],expected_projection_sha=expected)
    a=primary['admission'];c=primary['archive_context'];api=claim['api'] if kind=='PREVIEW' else claim['kind']
    if (a['ledger_kind']!=kind or a['api']!=api or a['claim_id']!=claim_id
            or a['ordinal']!=claim['ordinal'] or a['admission_event_sha']!=row['event_sha']
            or a['admission_payload_sha']!=wire.digest(payload)
            or c['contract_sha']!=CONTRACT_SHA or c['source_epoch']!=payload['epoch']
            or primary['binding']['source_kind']!=state['source_kind']
            or wire.digest(primary['binding'])!=state['binding_sha']
            or primary['account_root_identity_sha']!=wire.digest({'device':history_policy.root_pin[0],'inode':history_policy.root_pin[1]})):fail()
    if kind=='PREVIEW':
        if a['gid']!=holder or a['operation_id'] is not None or a['slot']!='PREVIEW_'+api+':'+str(claim['ordinal']):fail()
        subject=claim['subject_sha'];request_sha=claim['request_sha']
    else:
        if a['operation_id']!=holder or a['slot']!=claim['slot'] or a['gid'] is not None:fail()
        if api=='ADD':
            subject=wire.digest({'profile':'GROUP_ADD_TARGET_SUBJECT_V1','operation_id':holder,
                'manifest_sha':op['own_link']['manifest_sha'],'target_projection_sha':op['pins']['target_projection_sha']})
            request_sha=op['own_link']['request_sha']
            if wire.canonical(a['own_step_pin'])!=wire.canonical(op['own_link']['step_pin']):fail()
        else:subject=claim['subject_sha'];request_sha=claim['request_sha']
    if a['subject_sha']!=subject or a['request_sha']!=request_sha:fail()
    return kind,holder,claim,expected,primary,subject,request_sha


def _locator_value_from_fact(state,claim_id,raw,row,payload,basis,record,*,reference=None,list_offset=None):
    # Pure original locator suffix. Its result alone is not an issued locator.
    from .draft_group_source_facts import source_fact_qid
    kind,holder,claim,expected,primary,subject,request_sha=basis
    a=primary['admission'];c=primary['archive_context'];api=a['api']
    fact=record['candidate'];sel=fact['claim_selector']
    fact_subject=holder
    qid=source_fact_qid(binding_sha=state['binding_sha'],ledger_kind=kind,subject=fact_subject,
        api=api,slot=a['slot'],ordinal=claim['ordinal'])
    if (fact['qid']!=qid or fact['binding_sha']!=state['binding_sha']
            or fact['family_id']!=a['family_id'] or fact['purpose_key']!=a['purpose_key']
            or fact['gid']!=a['gid'] or fact['operation_id']!=a['operation_id']
            or c['group_input_sha']!=(fact['registration_sha'] if kind=='PREVIEW' else fact['parent_execution_sha'])
            or c['source_qualification_locator']['event_seq']+1!=row['seq']
            or sel!={'ledger_kind':kind,'api':api,'slot':a['slot'],'ordinal':a['ordinal'],
                      'subject_sha':subject,'request_sha':request_sha}):fail()
    expected_proof=claim['proof_sha'] if api!='ADD' else None
    if expected_proof is not None and sha256(raw).hexdigest()!=expected_proof:fail()
    if reference is not None and api in ('GET','DELETE') and wire.reference_sha(reference,synthetic=state['source_kind']=='SYNTHETIC_SETUP')!=subject:fail()
    locator=OriginalClaimLocator(state['binding_sha'],claim_id,wire.canonical(a),wire.canonical(c),
        wire.canonical(primary['binding']),payload['at_ms'],expected_proof,expected,reference,list_offset)
    return locator


def locator_from_primary_in(db,state,claim_id,raw,history_policy,*,reference=None,list_offset=None):
    kind,holder,grant,op,claim=_find_claim(state,claim_id)
    row,payload=_admission_event(db,state['binding_sha'],kind,holder,claim)
    basis=_locator_primary_facts(state,claim_id,raw,history_policy,row,payload)
    from .draft_group_source_facts import query_source_fact_in
    record=query_source_fact_in(db,basis[4]['archive_context']['source_qualification_locator'],history_policy=history_policy)
    return _register_locator(_locator_value_from_fact(state,claim_id,raw,row,payload,basis,record,
        reference=reference,list_offset=list_offset),db)


def load_original_locator_in(files,db,state,claim_id,*,reference=None,list_offset=None):
    role='group_response';folder,name=files._name(role,claim_id)
    with files._directory(folder) as (fd,fence):
        raw,pin=files._read_at(fd,name,fence,16384,with_pin=True)
    locator=locator_from_primary_in(db,state,claim_id,raw,files.policy,reference=reference,list_offset=list_offset)
    files._bind(locator);files._remember(role,claim_id,pin)
    primary=files.read_primary(locator)
    files.read_snapshot(locator,primary);files.collective_fence()
    return locator


def validate_group_add_archive_in(db,step,proof,primary,*,primary_sha):
    """Pure link/codec validation in caller SQL. Never _load/OwnStore/current."""
    from .own_response_archive import row_pin
    from .draft_group_store import _PIN_FIELDS
    if not db.in_transaction:fail()
    from .draft_group_input_files import _plain,_closed
    _plain(proof)
    _closed(proof,('schema','policy','provenance','binding','row','request_sha256','response_sha256','result','group'))
    if (type(proof['schema']) is not int or proof['schema']!=2 or proof['policy']!='ADMITTED_RESPONSE_ARCHIVE_V2_GROUP'
            or proof['row']!=row_pin(step) or proof['binding']!=primary['binding']
            or proof['provenance']!=('SYNTHETIC_OWN_WIRE' if primary['binding']['source_kind']=='SYNTHETIC_SETUP' else 'OWN_OFFICIAL_WIRE')
            or type(proof['result']) is not dict or set(proof['result'])!={'reference'}
            or step['operation']!='add' or step['slot']!='draft'):fail()
    rows=db.execute('SELECT * FROM group_own_step_links WHERE step_id=?',(step['id'],)).fetchall()
    if len(rows)!=1:fail()
    row=rows[0];link=json.loads(row['value'])
    if wire.digest(link)!=row['value_sha']:fail()
    op_row=db.execute('SELECT value,value_sha FROM group_operations WHERE account_key=? AND operation_id=?',(row['account_key'],row['operation_id'])).fetchone()
    if op_row is None:fail()
    op=json.loads(op_row['value'])
    if wire.digest(op)!=op_row['value_sha']:fail()
    a=primary['admission'];o=primary['observation']
    if (proof['group']!={'profile':'GROUP_ADD_CAPTURE_LINK_V1','claim_id':row['claim_id'],
                        'operation_id':row['operation_id'],'group_response_sha':primary_sha}
            or a['api']!='ADD' or a['claim_id']!=row['claim_id'] or a['operation_id']!=row['operation_id']
            or a['own_step_pin']!=row_pin(step) or a['request_sha']!=proof['request_sha256']
            or primary['transport']['response_body_sha']!=proof['response_sha256']
            or o['outcome']!='KNOWN_SUCCESS' or o['reference']!=proof['result']['reference']
            or op['own_link']['step_pin']!={key:step[key] for key in _PIN_FIELDS}):fail()
    return None


def check_group_response_records_in(db,states,history_policy, *, history_locators=None):
    """Full reducer ran already. No _load/OwnStore/current/SQL mutation here."""
    from .draft_group_runtime_host import response_history_context_in,resolve_group_reference_in
    from .draft_group_response_files import GroupResponseFiles
    from .draft_group_source_facts import candidate_profile,is_source_profile,validate_source_fact,query_source_fact_in
    context=None;files=None
    def get_files():
        nonlocal context,files
        if files is None:
            context=response_history_context_in(db,history_policy)
            files=GroupResponseFiles.from_history_context(history_policy,context)
        return files
    def original_fact(state,claim):
        actual=get_files();folder,name=actual._name('group_response',claim['id'])
        with actual._directory(folder) as (fd,fence):
            raw,pin=actual._read_at(fd,name,fence,16384,with_pin=True)
        kind,holder,grant,op,_=_find_claim(state,claim['id'])
        expected=_expected_projection(op,claim) if kind=='CHILD' and claim['kind']=='GET' else None
        primary=codec.decode_primary(raw,expected_projection_sha=expected)
        actual._remember('group_response',claim['id'],pin)
        return query_source_fact_in(db,primary['archive_context']['source_qualification_locator'],history_policy=history_policy)['candidate']
    for account,item in states.items():
        state=item[0] if type(item) is tuple else item
        has_facts=False
        for row in db.execute("SELECT payload FROM group_events WHERE account_key=? AND kind='PREVIEW'",(account,)):
            payload=json.loads(row[0])
            if is_source_profile(candidate_profile(payload)):
                # B owns exact FACTS1/FACTS2 and the reserved unknown domain.
                # Validate every reserved record; a prior valid fact must not
                # hide a later unsupported profile behind an early break.
                validate_source_fact(payload['candidate']);has_facts=True
        if not has_facts:
            has_results=any(c['proof_sha'] is not None for g in state['preview_grants'].values() for c in g['claims']) or any(c['proof_sha'] is not None for op in state['operations'].values() for c in op['claims'])
            if has_results:fail()
            continue
        for gid,grant in state['preview_grants'].items():
            list_pages=[]
            for claim in grant['claims']:
                if claim['proof_sha'] is None:continue
                api=claim['api'];offset=None;ref=None
                fact=original_fact(state,claim)
                if api=='GET':ref=resolve_group_reference_in(db,history_policy,fact,claim['subject_sha'], history_locators=history_locators)
                elif not list_pages:offset=0
                else:
                    total=list_pages[0]['total_count'];pages=max(1,(total+19)//20)
                    offset=((claim['ordinal']-1)%pages)*20
                locator=load_original_locator_in(files,db,state,claim['id'],reference=ref,list_offset=offset)
                primary=files.read_primary(locator);snapshot=files.read_snapshot(locator,primary)
                if api=='LIST' and snapshot is not None:list_pages.append(json.loads(snapshot.raw))
                value=primary.value
                if value['observation']['outcome']!=claim['outcome'] or primary.sha256!=claim['proof_sha']:fail()
        for oid,op in state['operations'].items():
            for claim in op['claims']:
                if claim['proof_sha'] is None:continue
                api=claim['kind'];fact=original_fact(state,claim)
                ref=None if api=='ADD' else resolve_group_reference_in(db,history_policy,fact,claim['subject_sha'], history_locators=history_locators)
                locator=load_original_locator_in(files,db,state,claim['id'],reference=ref)
                primary=files.read_primary(locator);obs=primary.value['observation']
                if obs['outcome']!=claim['outcome']:fail()
                if api=='ADD' and obs['outcome']=='KNOWN_SUCCESS':
                    _check_group_add_pair_in(db,op,claim,primary,files,history_policy)
        if files is not None:files.collective_fence()


# Read-only, nonrecursive history view. These registries carry no source/current
# qualification, owner or publication permission.
from dataclasses import dataclass,field
import threading
import math
from .own_validation_scope import OwnedConnection,_transaction_marker

_REPLAY_VIEWS={}
_REPLAY_FILE_CONTEXTS={}
_REPLAY_READERS={}
_REPLAY_LOCATOR_IDS={}


@dataclass(frozen=True,slots=True)
class _ReplayedSQLView:
    db: object=field(repr=False)
    transaction_epoch: object=field(repr=False)
    thread: int
    changes: int
    schema_pin: tuple
    states: object=field(repr=False)
    events: object=field(repr=False)
    states_json: str=field(repr=False)
    events_json: str=field(repr=False)
    source_facts: object=field(repr=False)


def _owned_replay_transaction(db):
    if type(db) is not OwnedConnection or not db.in_transaction:fail()
    marker=_transaction_marker(db)
    if marker is None:fail()
    return marker


def _replay_schema_pin(db):
    # SQL namespace and header pragmas can change without total_changes. They
    # must remain the original snapshot, independently of SAVEPOINT epochs.
    main=db.execute('PRAGMA main.schema_version').fetchone()[0]
    temp=db.execute('PRAGMA temp.schema_version').fetchone()[0]
    version=db.execute('PRAGMA main.user_version').fetchone()[0]
    appid=db.execute('PRAGMA main.application_id').fetchone()[0]
    databases=tuple(tuple(row) for row in db.execute('PRAGMA database_list'))
    if any(row[1] not in ('main','temp') for row in databases):fail()
    # This fixed OwnStore reader has no temp objects. Reject initial namespace
    # shadows rather than trusting that an unqualified table means main.
    if db.execute('SELECT 1 FROM temp.sqlite_master LIMIT 1').fetchone():fail()
    return main,temp,version,appid,databases


def _read_group_replay_snapshot_unchecked(db):
    """Actual SQL -> original pure reducer/projection checks; never _load.

    Detached values are facts. Only this exact pair is accepted by the receipt
    reader in the same actual Owned transaction. No caller fact is trusted.
    """
    marker=_owned_replay_transaction(db);changes=db.total_changes;schema_pin=_replay_schema_pin(db)
    if db.execute('PRAGMA user_version').fetchone()[0]!=9 or db.execute('PRAGMA application_id').fetchone()[0]!=0x57434f31:fail()
    store._check_group_layout(db)
    if db.execute('PRAGMA foreign_key_check').fetchone():fail()
    pools=db.execute('SELECT * FROM group_pools ORDER BY account_key').fetchall()
    states={};events=[]
    for pool in pools:
        account=pool['account_key'];store.sha(account)
        state=None;seq=0;head=store.ZERO
        for row in db.execute('SELECT * FROM group_events WHERE account_key=? ORDER BY seq',(account,)):
            seq+=1
            if row['seq']!=seq or row['previous_sha']!=head:fail()
            payload=json.loads(row['payload']);store._json(payload)
            if wire.canonical(payload)!=row['payload']:fail()
            event={'account_key':account,'seq':seq,'kind':row['kind'],'payload':payload,'previous_sha':head}
            if wire.digest(event)!=row['event_sha']:fail()
            state=store._reduce(state,row['kind'],payload);head=row['event_sha']
            if state['binding_sha']!=account:fail()
            events.append({k:v for k,v in event.items() if k!='previous_sha'}|{'event_sha':head})
        if state is None or seq!=pool['seq'] or head!=pool['head']:fail()
        # Original materialization and own-link checks, no alternate reducers.
        for table,expected in store._projection_rows(state,seq,head).items():
            actual=[tuple(row) for row in db.execute('SELECT * FROM '+table+' WHERE account_key=?',(account,))]
            if sorted(actual,key=wire.canonical)!=sorted(expected,key=wire.canonical):fail()
        store._verify_links(db,state)
        states[account]=(state,seq,head)
    if db.execute('SELECT 1 FROM group_events LEFT JOIN group_pools USING(account_key) WHERE group_pools.account_key IS NULL').fetchone():fail()
    from .draft_group_source_facts import replay_source_facts
    # Replay only the real snapshot, using B's unique closed chain codec. Keep
    # this private independently decoded value separate from the returned pair.
    events_json=wire.canonical(events);states_json=wire.canonical(states)
    source_facts=replay_source_facts(json.loads(events_json))
    if _owned_replay_transaction(db)!=marker or db.total_changes!=changes or _replay_schema_pin(db)!=schema_pin:fail()
    view=_ReplayedSQLView(db,marker,threading.get_ident(),changes,schema_pin,states,events,states_json,events_json,source_facts)
    _REPLAY_VIEWS[(id(states),id(events))]=view
    return states,events


def read_group_replay_snapshot_in(db):
    try:return _read_group_replay_snapshot_unchecked(db)
    except WCEError:raise
    except Exception:raise WCEError('GROUP_RESPONSE_HISTORY_HOLD') from None


def _primitive_replay_value(value,budget,depth=0):
    # Bound this comparison by the already issued actual SQL bytes, while
    # rejecting user hooks/cycles before canonical serialization.
    budget[0]-=1
    if budget[0]<0 or depth>128:fail()
    kind=type(value)
    if kind is dict:
        for k,v in value.items():
            if type(k) is not str:fail()
            _primitive_replay_value(v,budget,depth+1)
    elif kind is list:
        for v in value:_primitive_replay_value(v,budget,depth+1)
    elif kind is float:
        if not math.isfinite(value):fail()
    elif kind not in (str,int,bool,type(None)):fail()


def _primitive_replay_pair(states,events,maximum):
    if type(states) is not dict or type(events) is not list:fail()
    budget=[maximum*2+1024]
    for account,item in states.items():
        if type(account) is not str or type(item) is not tuple or len(item)!=3:fail()
        if type(item[1]) is not int or type(item[2]) is not str:fail()
        _primitive_replay_value(item[0],budget)
    _primitive_replay_value(events,budget)


def _require_replay_view(db,states,events):
    view=_REPLAY_VIEWS.get((id(states),id(events)))
    if view is not None:_primitive_replay_pair(states,events,len(view.states_json)+len(view.events_json))
    if (view is None or view.db is not db or view.states is not states or view.events is not events
            or view.thread!=threading.get_ident() or _owned_replay_transaction(db)!=view.transaction_epoch
            or db.total_changes!=view.changes or _replay_schema_pin(db)!=view.schema_pin or wire.canonical(states)!=view.states_json
            or wire.canonical(events)!=view.events_json):fail()
    return view


def verify_group_replay_inputs_in(db,states,events):
    _require_replay_view(db,states,events)
    return None


@dataclass(frozen=True,slots=True)
class GroupReplayFileContext:
    view: object=field(repr=False)
    policy: object=field(repr=False)
    authority: bool=False


def validate_replay_file_context(policy,context):
    record=_REPLAY_FILE_CONTEXTS.get(id(context))
    if (type(context) is not GroupReplayFileContext or record is None or record[0] is not context
            or context.view is not record[1] or context.policy is not record[2] or record[3]!=threading.get_ident()
            or context.policy is not policy or context.authority is not False):fail()
    view=context.view;_require_replay_view(view.db,view.states,view.events)
    from .draft_group_history_context import current_history_policy
    from .draft_group_read_family_store import _history_file_guard
    if current_history_policy(view.db) is not policy:fail()
    _history_file_guard(policy)
    return None


@dataclass(frozen=True,slots=True)
class GroupReplayedReceipt:
    locator: object=field(repr=False)
    primary: object=field(repr=False)
    snapshot: object=field(repr=False)
    source_locator_json: str=field(repr=False)
    admission_event_json: str=field(repr=False)
    files: object=field(repr=False)
    authority: bool=False


def _admission_event_from_replay(events,account,kind,holder,claim):
    event_kind='PREVIEW_READ' if kind=='PREVIEW' else claim['kind']+'_CLAIM'
    found=[];preview_ordinals={}
    for row in events:
        if row['account_key']!=account or row['kind']!=event_kind:continue
        p=row['payload']
        if kind=='PREVIEW':
            key=(p['grant_id'],p['api']);ordinal=preview_ordinals.get(key,0)+1;preview_ordinals[key]=ordinal
            actual=wire.digest({'binding_sha':account,'grant_id':p['grant_id'],'api':p['api'],'ordinal':ordinal})
            matches=ordinal==claim['ordinal'] and p['grant_id']==holder and p['api']==claim['api'] and p['request_sha']==claim['request_sha'] and p['at_ms']<=claim['at_ms']
        else:
            slot='ADD' if event_kind=='ADD_CLAIM' else 'DELETE:'+str(p['old_index']) if event_kind=='DELETE_CLAIM' else p['slot']
            actual=wire.digest({'binding_sha':account,'operation_id':p['operation_id'],'kind':claim['kind'],'slot':slot})
            matches=p['operation_id']==holder and slot==claim['slot']
        if actual==claim['id'] and matches:found.append((row,p))
    if len(found)!=1:fail()
    return found[0]


def _read_group_receipt_from_replay_unchecked(db,states,events,history_policy,claim_id,*,reference=None,list_offset=None):
    """Fixed historical receipt reader. No _load/OwnStore/current/owner paths.

    Outer full9 still validates physical SourceFacts/root evidence before the
    Parent hook; this leaf proves this actual response's original fact/claim
    association and reads only the unchanged two C roles with collective pins.
    """
    view=_require_replay_view(db,states,events);store.sha(claim_id)
    matches=[]
    for account,item in states.items():
        state=item[0]
        try:parts=_find_claim(state,claim_id)
        except WCEError:continue
        matches.append((state,parts))
    if len(matches)!=1:fail()
    state,parts=matches[0];kind,holder,grant,op,claim=parts
    if claim['proof_sha'] is None:fail()
    row,payload=_admission_event_from_replay(events,state['binding_sha'],kind,holder,claim)
    reader=_REPLAY_READERS.get((id(view),id(history_policy)))
    if reader is None:
        context=GroupReplayFileContext(view,history_policy)
        _REPLAY_FILE_CONTEXTS[id(context)]=(context,view,history_policy,threading.get_ident())
        validate_replay_file_context(history_policy,context)
        from .draft_group_response_files import GroupResponseFiles
        files=GroupResponseFiles(history_policy,context)
        _REPLAY_READERS[(id(view),id(history_policy))]=(view,history_policy,files)
    else:
        if reader[0] is not view or reader[1] is not history_policy:fail()
        files=reader[2];files.collective_fence()
    role='group_response';folder,name=files._name(role,claim_id)
    with files._directory(folder) as (fd,fence):raw,pin=files._read_at(fd,name,fence,16384,with_pin=True)
    basis=_locator_primary_facts(state,claim_id,raw,history_policy,row,payload)
    source_locator=basis[4]['archive_context']['source_qualification_locator']
    from .draft_group_source_facts import _locator_in
    record=_locator_in(view.source_facts,source_locator)
    loc=_locator_value_from_fact(state,claim_id,raw,row,payload,basis,record,reference=reference,list_offset=list_offset)
    api=basis[4]['admission']['api']
    # Bind external snapshot parsing arguments to the actual original request
    # body; no Secret or caller request is needed for these fixed request types.
    if api=='LIST':
        if reference is not None:fail()
        from .draft_group_discovery import _offset,PAGE_SIZE
        _offset(list_offset)
        body=wire.canonical({'offset':list_offset,'count':PAGE_SIZE,'no_content':1}).encode('utf-8')
        if sha256(body).hexdigest()!=claim['request_sha']:fail()
    elif api in ('GET','DELETE'):
        if reference is None or list_offset is not None:fail()
        body=wire.canonical({'media_id':reference}).encode('utf-8')
        if sha256(body).hexdigest()!=basis[6]:fail()
    elif reference is not None or list_offset is not None:fail()
    locator=_register_locator(loc,db)
    _REPLAY_LOCATOR_IDS.setdefault(id(view),set()).add(id(locator))
    files._bind(locator);files._remember(role,claim_id,pin)
    primary=files.read_primary(locator);snapshot=files.read_snapshot(locator,primary)
    if primary.value['observation']['outcome']!=claim['outcome']:fail()
    if api=='ADD':
        if claim['outcome']=='KNOWN_SUCCESS':_check_group_add_pair_in(db,op,claim,primary,files,history_policy)
        elif primary.sha256!=claim['proof_sha']:fail()
    files.collective_fence();_require_replay_view(db,states,events)
    return GroupReplayedReceipt(locator,primary,snapshot,wire.canonical(source_locator),wire.canonical(row),files)


def read_group_receipt_from_replay_in(db,states,events,history_policy,claim_id,*,reference=None,list_offset=None):
    try:return _read_group_receipt_from_replay_unchecked(db,states,events,history_policy,claim_id,
        reference=reference,list_offset=list_offset)
    except WCEError:raise
    except Exception:raise WCEError('GROUP_RESPONSE_HISTORY_HOLD') from None


def release_group_replay_snapshot_in(db,states,events):
    """Finally-only cleanup; it cannot qualify a read, write or next effect."""
    key=(id(states),id(events));view=_REPLAY_VIEWS.get(key)
    if view is None:return None
    if view.db is not db or view.states is not states or view.events is not events or view.thread!=threading.get_ident():fail()
    from .draft_group_response_files import _LOCATORS
    for identity in _REPLAY_LOCATOR_IDS.pop(id(view),set()):_LOCATORS.pop(identity,None)
    for identity,record in tuple(_REPLAY_FILE_CONTEXTS.items()):
        if record[1] is view:_REPLAY_FILE_CONTEXTS.pop(identity,None)
    for identity,record in tuple(_REPLAY_READERS.items()):
        if record[0] is view:_REPLAY_READERS.pop(identity,None)
    _REPLAY_VIEWS.pop(key,None)
    return None


def _check_group_add_pair_in(db,op,claim,primary,files,history_policy):
    """Original contiguous ADD primary -> ownproof/index checks; no reentry."""
    from .own_response_archive import filename
    from .own_bootstrap_security import private_read
    step=db.execute('SELECT * FROM own_steps WHERE id=?',(op['expected_own_step_id'],)).fetchone()
    raw,pin=private_read(history_policy.root/filename(step));proof=json.loads(raw)
    index_raw,index_pin=private_read(history_policy.root/('response-index-'+step['id']+'-'+step['owner']+'.json'))
    files._remember_own_archive_file(step,filename(step),pin)
    files._remember_own_archive_file(step,'response-index-'+step['id']+'-'+step['owner']+'.json',index_pin)
    index=json.loads(index_raw)
    if (len(raw)>8192 or (wire.canonical(proof)+'\n').encode()!=raw or sha256(raw).hexdigest()!=claim['proof_sha'] or index!={'schema':1,'row_sha256':wire.digest({k:step[k] for k in store._PIN_FIELDS}),'proof_sha256':claim['proof_sha']}
            or (wire.canonical(index)+'\n').encode()!=index_raw):fail()
    validate_group_add_archive_in(db,step,proof,primary.value,primary_sha=primary.sha256)
