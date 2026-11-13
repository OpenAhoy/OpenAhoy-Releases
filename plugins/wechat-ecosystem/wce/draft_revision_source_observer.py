"""Native USER evidence/fences for one host-reviewed revision, never a grant.

The trusted maintenance host selects roots, threads, semantic pins and start
ordinals. None is an MCP argument. Model-provided role/source strings are not
accepted. An observation must still be bound by the registrar to the exact human
scope, original success proof, account and frozen revision artifact.
"""
from dataclasses import dataclass,field,replace
from hashlib import sha256
import os
import math
import stat
from .draft_revision_native_source import (RegisteredSource,SourceHold,MAX_LINE,
    MAX_RECORDS,canonical,digest,require,checked_guard,strict_json,_open_source,_regular,
    registration_digest)
from .draft_revision_stream import read_current_prefix
from .draft_revision_scan import full as full_guard
from .draft_revision_native_lookup import NativeThreadLookup,valid_thread

_SEAL=object()


def _generation(info):
    # Decimal strings preserve nanosecond and inode precision in canonical JSON.
    return [str(value) for value in (info.st_dev,info.st_ino,info.st_mode,
        info.st_uid,info.st_gid,info.st_nlink,info.st_size,info.st_mtime_ns,info.st_ctime_ns)]


def _ancestors(chain):
    identities=[]
    for parent,name,pin in chain:
        current=os.stat(name,dir_fd=parent,follow_symlinks=False)
        require(stat.S_ISDIR(current.st_mode) and (current.st_dev,current.st_ino)==pin,
            'SOURCE_ANCESTOR_CHANGED')
        identities.append([str(pin[0]),str(pin[1])])
    return identities


def _current_generation(source):
    fd,parent,name,descriptors,chain=_open_source(source)
    try:
        opened=os.fstat(fd);entry=os.stat(name,dir_fd=parent,follow_symlinks=False)
        _regular(opened,source);_regular(entry,source)
        require(_generation(opened)==_generation(entry),'REVISION_SOURCE_CHANGED_REOBSERVE')
        return {'file':_generation(opened),'ancestors':_ancestors(chain)}
    finally:
        for descriptor in reversed(descriptors):os.close(descriptor)


@dataclass(frozen=True)
class HumanPin:
    thread_id:str
    turn_id:str
    message_id:str
    text_sha256:str
    purpose:str  # Observed host review category, not a self-attested permission.


@dataclass(frozen=True)
class SourceWindow:
    source:RegisteredSource=field(repr=False)
    pins:tuple=field(repr=False)


@dataclass(frozen=True)
class ObservedDirectiveSet:
    canonical_bytes:bytes=field(repr=False)
    _seal:object=field(repr=False)
    def __post_init__(self):require(self._seal is _SEAL,'REVISION_UNCHECKED_SOURCE')
    @property
    def value(self):return strict_json(self.canonical_bytes)
    @property
    def sha256(self):return sha256(self.canonical_bytes).hexdigest()


def _capture_window(lookup,thread,start_ordinal,pins,guard):
    """Host-only fixed cursor capture, no Case, budget, account or permission."""
    require(type(lookup) is NativeThreadLookup and type(start_ordinal) is int
        and 0<=start_ordinal<MAX_RECORDS,'REVISION_SOURCE_BOOTSTRAP_REQUIRED')
    require(type(pins) is tuple and 1<=len(pins)<=4 and all(type(p) is HumanPin for p in pins),
        'REVISION_HUMAN_PINS_REQUIRED')
    for pin in pins:
        for value in (pin.thread_id,pin.turn_id,pin.message_id):valid_thread(value)
        require(pin.thread_id==thread and pin.purpose in {'initial_edit','resume_same_case','refinement',
                'current_inventory_publication','current_draft_revision','single_saved_draft_publication',
                'saved_groups_publication'}
            and type(pin.text_sha256) is str and len(pin.text_sha256)==64
            and all(c in '0123456789abcdef' for c in pin.text_sha256),'REVISION_HUMAN_PIN_INVALID')
    require(len({p.message_id for p in pins})==len(pins),'REVISION_HUMAN_PIN_DUPLICATE')
    source=lookup.locate(thread);fd,parent,name,descriptors,chain=_open_source(source)
    try:
        end=os.fstat(fd).st_size;require(0<end,'REVISION_SOURCE_PREFIX_LIMIT')
        offset=0;ordinal=source.metadata_ordinal;prior=sha256();found=None
        with os.fdopen(os.dup(fd),'rb',buffering=65536) as stream:
            while offset<end:
                checked_guard(guard)
                # Cursor is derived from the validated absolute ordinal, never
                # from a model's physical-line number or chosen truncated N.
                if ordinal==start_ordinal:
                    found=replace(source,start_offset=offset,start_ordinal=ordinal,
                        preceding_sha256=prior.hexdigest());break
                raw=stream.readline(min(MAX_LINE+1,end-offset+1))
                require(raw and len(raw)<=MAX_LINE and offset+len(raw)<=end
                    and raw.endswith(b'\n'),'REVISION_SOURCE_LINE_HOLD')
                row=strict_json(raw,maximum=MAX_LINE)
                require(type(row) is dict and type(row.get('ordinal')) is int and row['ordinal']==ordinal,
                    'REVISION_SOURCE_ORDINAL_HOLD')
                prior.update(raw);offset+=len(raw);ordinal+=1
        require(found is not None,'REVISION_SOURCE_CURSOR_MISSING')
        _regular(os.fstat(fd),source)
        require(registration_digest(lookup.locate(thread))==registration_digest(source),
            'REVISION_SOURCE_INDEX_CHANGED')
    finally:
        for descriptor in reversed(descriptors):os.close(descriptor)
    return SourceWindow(found,pins)


def bootstrap_window(lookup,thread,start_ordinal,pins,guard,*,single_context=None,request_context=None,current_context=None):
    window=_capture_window(lookup,thread,start_ordinal,pins,guard)
    observe_window(lookup,window,guard,single_context=single_context,request_context=request_context,current_context=current_context)
    return window


def _response(record,thread,known_tasks=None):
    row=record.value;value=row['payload'];metadata=row.get('metadata',{})
    passthrough=value.get('internal_chat_message_metadata_passthrough',{})
    entries=passthrough.get('content_item_metadata') if type(passthrough) is dict else None
    require(type(entries) is list and len(entries)==1 and type(entries[0]) is dict,
        'REVISION_SOURCE_PROVENANCE_HOLD')
    provenance=entries[0].get('provenance',{})
    require(type(provenance) is dict and provenance.get('type') in {'user','harness','agents_md'},
        'REVISION_SOURCE_PROVENANCE_HOLD')
    if provenance['type']=='harness':return None  # Never grants or cancels USER authority.
    if provenance['type']=='agents_md':
        # Native configuration provenance cannot satisfy a human directive.
        # Its complete bytes remain part of both source passes and the fence.
        content=value.get('content');created=passthrough.get('create_time')
        require(set(entries[0])=={'provenance'} and set(provenance)=={'type'}
            and set(passthrough)=={'content_item_metadata','content_item_kinds','create_time','turn_id'}
            and passthrough['content_item_kinds']==['agents_md.instructions']
            and type(metadata) is dict and set(metadata)=={'client_authored','mcp_attribution'}
            and metadata['client_authored'] is False and type(metadata['mcp_attribution']) is dict
            and type(content) is list and len(content)==1 and type(content[0]) is dict
            and set(content[0])=={'type','text'} and content[0]['type']=='input_text'
            and type(content[0]['text']) is str and type(created) in (int,float)
            and 0<=created<=9007199254740991 and math.isfinite(created),
            'REVISION_SOURCE_CONFIGURATION_HOLD')
        turn=passthrough['turn_id'];valid_thread(turn)
        require(type(known_tasks) is dict and turn in known_tasks,'REVISION_SOURCE_CONFIGURATION_TASK_HOLD')
        return {'configuration_turn':turn}
    turn=passthrough.get('turn_id');valid_thread(turn)
    retained=metadata.get('retained_source') if type(metadata) is dict else None
    require(type(retained) is dict and retained.get('complete') is True
        and retained.get('id')=={'message_id':value.get('id'),'turn_id':turn,'role':'user'},
        'REVISION_SOURCE_RETAINED_HOLD')
    content=value.get('content')
    require(type(content) is list and len(content)==1 and type(content[0]) is dict
        and content[0].get('type')=='input_text' and type(content[0].get('text')) is str,
        'REVISION_SOURCE_CONTENT_HOLD')
    require(metadata.get('client_authored') is None or type(metadata.get('client_authored')) is bool,
        'REVISION_SOURCE_METADATA_HOLD')
    return {'turn_id':turn,'text_sha256':sha256(content[0]['text'].encode()).hexdigest(),
        'response_id':value['id'],'record':record.reference(),
        'client_authored':metadata.get('client_authored')}


def current_restrictions(events, connection_id):
    """Account-only controls: empty/unknown scope cannot silently match nothing."""
    current = {}; content_changed = set()
    for event in events:
        for effect in event['effects']:
            ids = effect['scope']['connection_ids']
            if ids and connection_id not in ids: continue
            key = event['thread_id']
            if effect['kind'] == 'RESUME': current[key] = False
            elif effect['kind'] in {'RESTRICT','AMBIGUOUS','AUDIENCE_CHANGE'}: current[key] = True
            elif effect['kind'] == 'CONTENT_CHANGE': content_changed.add(key)
    return bool(content_changed or any(current.values()))


def _current_control(text, fact, context, previous):
    from .slot_control_semantics import interpret, command_text
    from .single_publication_controls import explicit_english_control
    import re
    # Only the interpretation is projected. The already-validated raw/typed
    # USER pair and the returned evidence keep the original complete text hash.
    cleaned = re.sub(r'[“「『\"‘]([^”」』\"’\n]*)[”」』\"’]',
        lambda match: '' if re.search(r'停|取消|撤销|撤回|别发|只发|群发|修改|继续|恢复|(?i:stop|pause|cancel|resume|continue)', match[1]) else match[1], text)
    cleaned = command_text(cleaned)
    clauses = [clause.strip() for clause in re.split(r'[，,。；;！!\n]|但是|但|不过|而是',cleaned) if clause.strip()]
    event = interpret(text,fact,context,previous)
    event['effects'] = []
    for clause in clauses:
        if re.match(r'^(?:(?:新闻|报道|文章(?:里|中)|材料(?:里|中)).*(?:说|提到|表示|宣布)|(?:他|她|他们|对方|别人|同事|模型)说|引用|转述)',clause):
            continue
        projection = dict(fact,text_sha256=sha256(clause.encode()).hexdigest())
        parsed = interpret(clause,projection,context,tuple(previous)+(event,))
        ids = [a.connection_id for a in context.accounts if any(alias in clause for alias in a.aliases)]
        related = bool(ids or re.search(r'发表|发布|发文|草稿|稿件|文章|这批|本批|本次|这篇|那篇|这组|那组',clause))
        content = bool(re.search(r'修改|重写|换图|改标题|改内容|调整顺序|重新排版',clause))
        selection = bool(re.search(r'(?:只|仅)(?:发|发表|发布|把|将)|第[一二三四五六七八九十\d]+(?:篇|组)|前[一二三四五六七八九十\d]+篇|追加.*(?:篇|稿)|去掉.*(?:篇|稿)',clause))
        selector_free = clause
        for account in context.accounts:
            for alias in sorted(account.aliases,key=len,reverse=True):
                selector_free = selector_free.replace(alias,'')
        stop = bool(re.fullmatch(r'(?:(?:那就|现在|先|暂时)\s*)*(?:暂停|停止|停下|停|等等|等一下|别动|不要动)(?:一下|一停|吧|了)*',selector_free.strip())
            or re.search(r'(?:撤销|撤回|取消)(?:本次|本批|所有|全部)?(?:普通|公开)?(?:发表|发布|授权|委托)',clause))
        event['effects'].extend(effect for effect in parsed['effects']
            if effect['kind']!='NON_CONTROL' and (effect['kind']!='CONTENT_CHANGE' or related))
        english = explicit_english_control(clause)
        if stop or english is not None or (related and (selection or content)):
            kind = english or ('CONTENT_CHANGE' if content else 'RESTRICT' if (ids or stop) else 'AMBIGUOUS')
            event['effects'].append({'kind':kind,'reason':'EXPLICIT_CURRENT_INVENTORY_CONTROL',
                'scope':{'connection_ids':ids or ([a.connection_id for a in context.accounts] if stop or english else []),
                    'dates':[],'group_ids':[],'article_ids':[],'version_ids':[],'target_keys':[]}})
    if not event['effects']:
        event['effects'] = [{'kind':'NON_CONTROL','reason':'NO_CURRENT_INVENTORY_CONTROL',
            'scope':{'connection_ids':[],'dates':[],'group_ids':[],
                'article_ids':[],'version_ids':[],'target_keys':[]}}]
    return event


def observe_window(lookup,window,guard,*,source_review=None,single_context=None,request_context=None,current_context=None,
        registered_request_steering=False):
    if source_review is not None:
        require(single_context is None and request_context is None and current_context is None,'REVISION_SOURCE_CONTEXT_MIXED')
        from .draft_revision_review_observer import observe_reviewed_window
        return observe_reviewed_window(lookup,window,guard,source_review)
    require(type(lookup) is NativeThreadLookup and type(window) is SourceWindow,
        'REVISION_SOURCE_BOOTSTRAP_REQUIRED')
    controls=[]
    require(sum(item is not None for item in (single_context,request_context,current_context))<=1,'REVISION_SOURCE_CONTEXT_MIXED')
    if single_context is not None:
        from .slot_control_semantics import Context
        require(type(single_context) is Context and len(window.pins)==1
            and window.pins[0].purpose=='single_saved_draft_publication',
            'SINGLE_PUBLICATION_CONTROL_CONTEXT_REQUIRED')
        single_context.validate()
    if request_context is not None:
        from .slot_control_semantics import Context
        require(type(request_context) is Context and len(window.pins)==1
            and window.pins[0].purpose=='saved_groups_publication',
            'SAVED_GROUPS_PUBLICATION_CONTROL_CONTEXT_REQUIRED')
        request_context.validate()
        require(bool(request_context.targets)
            and len({target.connection_id for target in request_context.targets})==1,
            'SAVED_GROUPS_PUBLICATION_CONTROL_CONTEXT_REQUIRED')
    elif any(pin.purpose=='saved_groups_publication' for pin in window.pins):
        raise SourceHold('SAVED_GROUPS_PUBLICATION_CONTROL_CONTEXT_REQUIRED')
    if current_context is not None:
        from .slot_control_semantics import Context
        require(type(current_context) is Context and len(window.pins)==1
            and window.pins[0].purpose=='current_inventory_publication'
            and not current_context.targets,'CURRENT_PUBLICATION_CONTROL_CONTEXT_REQUIRED')
        current_context.validate()
    require(type(registered_request_steering) is bool
        and (not registered_request_steering or request_context is not None),
        'SAVED_GROUPS_PUBLICATION_CONTROL_CONTEXT_REQUIRED')
    context=current_context if current_context is not None else single_context if single_context is not None else request_context
    error_prefix='SAVED_GROUPS_PUBLICATION' if request_context is not None else 'SINGLE_PUBLICATION'
    full_guard(guard)
    source=window.source;actual=lookup.locate(source.thread_id)
    require((actual.source_id,actual.path,actual.device,actual.inode,actual.session_meta_sha256,
        actual.metadata_ordinal)==(source.source_id,source.path,source.device,source.inode,
        source.session_meta_sha256,source.metadata_ordinal),'REVISION_SOURCE_INDEX_CHANGED')
    before_generation=_current_generation(source)
    stream=read_current_prefix(source,guard)
    wanted={p.message_id:p for p in window.pins};seen=set();tasks={};contexts=set();configuration_turns=set();pending={};observed=[];current_pin_seen=False
    for record in stream.records:
        checked_guard(guard);row=record.value;data=row['payload'];outer=row['type']
        if outer=='event_msg' and data.get('type')=='task_started':
            turn=data.get('turn_id');valid_thread(turn);attr=data.get('turn_attribution')
            require(type(attr) is dict and attr.get('turn_id')==turn
                and {'turn_trigger','parent_turn_id','initiating_agent_path'}<=set(attr),
                'REVISION_SOURCE_TASK_HOLD')
            tasks[turn]={'attribution':attr,'record':record.reference()}
        elif outer=='turn_context':
            turn=data.get('turn_id');valid_thread(turn)
            require(turn in tasks,'REVISION_SOURCE_CONTEXT_HOLD');contexts.add(turn)
        elif outer=='response_item' and data.get('type')=='message' and data.get('role')=='user':
            if request_context is not None or current_context is not None:
                # Exact configuration-only native profiles are shared with the
                # incremental human codec; they never provide USER evidence.
                from .slot_human_codec import _slot_response
                raw=_slot_response(record,source.thread_id,tasks,
                    allow_opaque_images=current_context is not None,
                    allow_incomplete_control=current_context is not None and current_pin_seen)
            else:
                raw=_response(record,source.thread_id,tasks)
            if raw is not None:
                if 'configuration_turn' in raw:
                    configuration_turns.add(raw['configuration_turn'])
                    continue
                turn=raw['turn_id']
                require(turn in tasks and turn in contexts and turn not in pending,
                    'REVISION_SOURCE_UNPAIRED_USER_HOLD')
                if request_context is not None or current_context is not None:
                    # Retain only in memory until the typed pair is matched.
                    raw['_raw_text_bytes']=data['content'][0]['text'].encode('utf-8')
                    if registered_request_steering:
                        order = row.get('metadata', {}).get('user_input_order')
                        raw['_native_user_order'] = type(order) is int and order >= 0
                pending[turn]=raw
        elif outer=='event_msg' and data.get('type')=='user_message':
            raise SourceHold('REVISION_SOURCE_LEGACY_USER_HOLD')
        elif outer=='event_msg' and data.get('type')=='item_completed' and type(data.get('item')) is dict and data['item'].get('type')=='UserMessage':
            item=data['item'];ident=item.get('id');turn=data.get('turn_id')
            valid_thread(ident);valid_thread(turn)
            require((ident in wanted or context is not None) and ident not in seen and data.get('thread_id')==source.thread_id,
                'REVISION_NEW_HUMAN_SOURCE_REQUIRES_REVIEW')
            expected=wanted.get(ident);content=item.get('content')
            raw=pending.get(turn)
            require(expected is None or turn==expected.turn_id, 'REVISION_SOURCE_TYPED_CONTENT_HOLD')
            require(raw is None or not raw.get('control_only') or
                (current_context is not None and current_pin_seen and expected is None),
                'CURRENT_PUBLICATION_CONTROL_ONLY_CANNOT_GRANT')
            if current_context is not None and raw is not None and 'opaque_images' in raw:
                from .slot_control_text_profile import typed_body
                body=typed_body(content,raw['opaque_images'])
            else:
                require(type(content) is list and len(content)==1
                    and type(content[0]) is dict and set(content[0])=={'type','text','text_elements'}
                    and content[0]['type']=='text' and type(content[0]['text']) is str
                    and content[0]['text_elements']==[], 'REVISION_SOURCE_TYPED_CONTENT_HOLD')
                body=content[0]['text']
            checksum=sha256(body.encode()).hexdigest();raw=pending.pop(turn,None)
            require(raw is not None and checksum==raw['text_sha256']
                and (expected is None or checksum==expected.text_sha256)
                and ((request_context is None and current_context is None) or raw.pop('_raw_text_bytes',None)==body.encode('utf-8')),
                'REVISION_SOURCE_USER_PAIR_HOLD')
            task=tasks[turn];attr=task['attribution']
            if current_context is None and expected is not None and expected.purpose in {'initial_edit','resume_same_case','current_inventory_publication','current_draft_revision','single_saved_draft_publication','saved_groups_publication'}:
                composer = (attr['turn_trigger']=='composer' and attr['parent_turn_id'] is None
                            and attr['initiating_agent_path'] is None)
                # A separately registered scope may bind a real desktop
                # steering message. The peer prompt is a harness record, not
                # the complete raw/typed USER pair checked above.
                steering = (registered_request_steering and expected.purpose=='saved_groups_publication'
                            and attr['turn_trigger']=='app_tool_send_message'
                            and attr['parent_turn_id'] is not None and attr['initiating_agent_path'] is None
                            and raw.get('_native_user_order') is True)
                require(composer or steering,'REVISION_SOURCE_COMPOSER_REQUIRED')
            # A genuine USER steering event can arrive inside an agent-started
            # turn. Its origin is the complete typed/response pair, not the
            # peer's turn trigger, role string, or client_authored boolean.
            observed.append({'message_id':ident,'turn_id':turn,'text_sha256':checksum,
                'purpose':expected.purpose if expected is not None else ('current_inventory_control' if current_context is not None else 'saved_groups_request_control' if request_context is not None else 'single_request_control'),
                'typed':record.reference(),'response':raw['record'],
                'task':task['record'],'client_authored':raw['client_authored']})
            if current_context is not None and 'opaque_images' in raw:
                observed[-1]['opaque_images']=dict(raw['opaque_images'])
                if raw.get('control_only'): observed[-1]['control_only']=True
            if expected is None:
                from .slot_control_semantics import interpret,restrictions,matches
                fact={'authority':False,'thread_id':source.thread_id,'turn_id':turn,'item_id':ident,
                    'text_sha256':checksum,'raw_ordinal':raw['record']['ordinal'],
                    'typed_ordinal':record.reference()['ordinal'],'created':row.get('timestamp')}
                text=body
                if current_context is not None and 'opaque_images' in raw:
                    fact['opaque_images']=dict(raw['opaque_images'])
                if current_context is not None:
                    event = _current_control(text,fact,context,controls)
                    if raw.get('control_only'):
                        # Incomplete attachments can carry restrictions, never
                        # widen a scope or clear an earlier stop. A later fully
                        # retained USER resume still folds in causal order.
                        for effect in event['effects']:
                            if effect['kind'] == 'RESUME':
                                effect['kind'] = 'AMBIGUOUS'
                                effect['reason'] = 'INCOMPLETE_CONTROL_CANNOT_WIDEN'
                    if not current_pin_seen:
                        event['effects'] = [{'kind':'NON_CONTROL','reason':'BEFORE_CURRENT_AUTHORIZATION_PIN',
                            'scope':{'connection_ids':[],'dates':[],'group_ids':[],
                                'article_ids':[],'version_ids':[],'target_keys':[]}}]
                    controls.append(event)
                    seen.add(ident)
                    continue
                event=interpret(text,fact,context,controls)
                controls.append(event)
                from .single_publication_controls import (selection_changed,
                    explicit_english_control,precise_content_changed)
                require(not precise_content_changed(text,context),
                    error_prefix+'_CONTENT_CHANGE_REQUIRED')
                extra_kind = 'RESTRICT' if selection_changed(text,context) else explicit_english_control(text)
                if request_context is not None:
                    from .saved_groups_controls import selection_changed as groups_selection_changed
                    if groups_selection_changed(text):
                        extra_kind='RESTRICT'
                    import re
                    if re.search(r'(?:撤销|撤回|取消)(?:本次|本批|所有|全部)?(?:普通|公开)?(?:发表|发布|授权|委托)',text):
                        extra_kind='RESTRICT'
                if extra_kind is not None:
                    for target in context.targets:
                        event['effects'].append({'kind':extra_kind,'reason':('EXPLICIT_SAVED_GROUPS_CONTROL' if request_context is not None else 'EXPLICIT_SINGLE_TARGET_CONTROL'),
                            'scope':{'connection_ids':[target.connection_id],'dates':[target.date],
                                'group_ids':[target.group_id],'article_ids':[target.article_id],
                                'version_ids':[target.version_id],
                                'target_keys':[[target.connection_id,target.date,target.group_id]]}})
                for target in context.targets:
                    selected={'connection_id':target.connection_id,'date':target.date,'group_id':target.group_id}
                    require(not any(effect['kind']=='CONTENT_CHANGE' and matches(effect['scope'],selected)
                        for effect in event['effects']),error_prefix+'_CONTENT_CHANGE_REQUIRED')
            if current_context is not None and expected is not None:
                current_pin_seen=True
            seen.add(ident)
    if context is not None:
        from .slot_control_semantics import restrictions
        for target in context.targets:
            selected={'connection_id':target.connection_id,'date':target.date,'group_id':target.group_id}
            require(restrictions(controls,selected)['state']!='RESTRICTED',
                error_prefix+'_TARGET_CONTROL_HOLD')
    require(configuration_turns<=contexts,'REVISION_SOURCE_CONFIGURATION_CONTEXT_HOLD')
    require(not pending,'REVISION_SOURCE_UNPAIRED_USER_HOLD')
    require((seen==set(wanted) if context is None else set(wanted)<=seen),
        'REVISION_SOURCE_USER_MISSING')
    require(registration_digest(lookup.locate(source.thread_id))==registration_digest(actual),
        'REVISION_SOURCE_INDEX_CHANGED')
    full_guard(guard)
    # A fixed prefix reader deliberately permits later append. This consumer
    # must not release an observation once that captured boundary is stale.
    # This is a point-in-time fence; the execution host must re-observe before
    # every admission. It cannot prevent a future event after the fence.
    fd,parent,name,descriptors,chain=_open_source(source)
    try:
        info=os.fstat(fd);_regular(info,source)
        current=os.stat(name,dir_fd=parent,follow_symlinks=False);_regular(current,source)
        require(info.st_size==current.st_size==stream.prefix_bytes,
            'REVISION_SOURCE_APPENDED_REOBSERVE')
        require(_generation(info)==_generation(current)==before_generation['file']
            and _ancestors(chain)==before_generation['ancestors'],
            'REVISION_SOURCE_CHANGED_REOBSERVE')
    finally:
        for descriptor in reversed(descriptors):os.close(descriptor)
    evidence={'schema':'REVISION_NATIVE_DIRECTIVE_OBSERVATION_V1','authority':False,
        'source_registration_sha256':registration_digest(source),'thread_id':source.thread_id,
        'prefix_bytes':stream.prefix_bytes,'prefix_sha256':stream.prefix_sha256,'users':observed,
        'final_stat':[str(info.st_mtime_ns),str(info.st_ctime_ns)],
        'generation':before_generation}
    if single_context is not None:
        evidence['single_control_context_sha256']=single_context.sha256
        evidence['single_control_events']=controls
    if request_context is not None:
        evidence['saved_groups_control_context_sha256']=request_context.sha256
        evidence['saved_groups_control_events']=controls
    if current_context is not None:
        evidence['current_control_context_sha256']=current_context.sha256
        evidence['current_control_events']=controls
    result=ObservedDirectiveSet(canonical(evidence),_SEAL)
    full_guard(guard)
    require(_current_generation(source)==before_generation,'REVISION_SOURCE_CHANGED_REOBSERVE')
    return result


def fence_window(lookup,window,observation,guard):
    """Cheap final fence after other input checks; append requires reobserve.

    This is the last observed boundary, not an atomic lock over the native host.
    Current execution performs it again before every admitted operation.
    """
    require(type(observation) is ObservedDirectiveSet,'REVISION_SOURCE_OBSERVATION_REQUIRED')
    value=observation.value;source=window.source
    require(value['source_registration_sha256']==registration_digest(source),
        'REVISION_SOURCE_INDEX_CHANGED')
    checked_guard(guard)
    current=lookup.locate(source.thread_id)
    from dataclasses import replace
    current=replace(current,start_offset=source.start_offset,start_ordinal=source.start_ordinal,
        preceding_sha256=source.preceding_sha256)
    require(registration_digest(current)==registration_digest(source),'REVISION_SOURCE_INDEX_CHANGED')
    fd,parent,name,descriptors,chain=_open_source(source)
    try:
        info=os.fstat(fd);_regular(info,source)
        entry=os.stat(name,dir_fd=parent,follow_symlinks=False);_regular(entry,source)
        require(info.st_size==entry.st_size==value['prefix_bytes']
            and [str(info.st_mtime_ns),str(info.st_ctime_ns)]==value['final_stat']
            and [str(entry.st_mtime_ns),str(entry.st_ctime_ns)]==value['final_stat'],
            'REVISION_SOURCE_CHANGED_REOBSERVE')
        generation=value.get('generation')
        require(type(generation) is dict and set(generation)=={'file','ancestors'}
            and _generation(info)==_generation(entry)==generation['file']
            and _ancestors(chain)==generation['ancestors'],
            'REVISION_SOURCE_CHANGED_REOBSERVE')
    finally:
        for descriptor in reversed(descriptors):os.close(descriptor)
    checked_guard(guard)


def release_window(window,observation):
    """Pure final generation fence, after all caller guards/callbacks.

    This performs no native-index query or external callback; it is still only
    a point-in-time observation, not a lock preventing later host activity.
    """
    require(type(window) is SourceWindow and type(observation) is ObservedDirectiveSet,
        'REVISION_SOURCE_OBSERVATION_REQUIRED')
    value=observation.value
    require(value['source_registration_sha256']==registration_digest(window.source),
        'REVISION_SOURCE_INDEX_CHANGED')
    require(_current_generation(window.source)==value.get('generation'),
        'REVISION_SOURCE_CHANGED_REOBSERVE')
