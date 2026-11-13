"""Incremental host-native USER pairs, no approval pins or authority grants."""
from copy import deepcopy
from hashlib import sha256
import math
from .draft_revision_native_source import require, SourceHold
from .draft_revision_native_lookup import valid_thread
from .draft_revision_source_observer import _response


def _slot_response(record, thread, known_tasks, *, allow_opaque_images=False,
        allow_incomplete_control=False):
    """Recognize exact non-authority configurations and an opt-in USER profile.

    The revision reader keeps its original contract. Explicit metadata, even
    an empty dict, must still pass that reader; absence is a distinct native
    agents_md record profile. The exact two-item agents_md/environment batch
    is also configuration only. Neither configuration supplies a human fact.
    """
    require(type(allow_incomplete_control) is bool
        and (not allow_incomplete_control or allow_opaque_images), 'SLOT_HUMAN_IMAGE_PROFILE_INVALID')
    row = record.value
    if allow_opaque_images:
        from .slot_control_text_profile import raw_response
        projected = raw_response(record, allow_incomplete_control=allow_incomplete_control)
        if projected is not None:
            return projected
    value = row['payload']
    passthrough = value.get('internal_chat_message_metadata_passthrough')
    entries = passthrough.get('content_item_metadata') if type(passthrough) is dict else None
    if type(entries) is not list or not all(type(item) is dict for item in entries):
        return _response(record, thread, known_tasks)
    provenances = [item.get('provenance') for item in entries]
    kinds = None
    if 'metadata' not in row and provenances == [{'type': 'agents_md'}]:
        kinds = ['agents_md.instructions']
    elif (provenances == [{'type': 'agents_md'}, {'type': 'harness', 'hook': False}]
            and provenances[1]['hook'] is False):
        metadata = row.get('metadata')
        if (type(metadata) is dict and set(metadata) == {'client_authored', 'mcp_attribution'}
                and metadata['client_authored'] is False and type(metadata['mcp_attribution']) is dict):
            kinds = ['agents_md.instructions', 'environments.environment_context']
    if kinds is None:
        return _response(record, thread, known_tasks)
    content = value.get('content')
    created = passthrough.get('create_time')
    require(all(set(item) == {'provenance'} for item in entries)
        and set(passthrough) == {'content_item_metadata', 'content_item_kinds', 'create_time', 'turn_id'}
        and passthrough['content_item_kinds'] == kinds
        and type(content) is list and len(content) == len(kinds)
        and all(type(item) is dict and set(item) == {'type', 'text'}
            and item['type'] == 'input_text' and type(item['text']) is str for item in content)
        and type(created) in (int, float)
        and 0 <= created <= 9007199254740991 and math.isfinite(created),
        'SLOT_HUMAN_CONFIGURATION_INVALID')
    turn = passthrough['turn_id']
    valid_thread(turn)
    require(type(known_tasks) is dict and turn in known_tasks,
        'SLOT_HUMAN_CONFIGURATION_TASK_INVALID')
    return {'configuration_turn': turn}


def initial_state(thread_id, next_ordinal=0):
    valid_thread(thread_id)
    require(type(next_ordinal) is int and next_ordinal >= 0, 'SLOT_HUMAN_STATE_INVALID')
    return {'schema': 1, 'thread_id': thread_id, 'next_ordinal': next_ordinal, 'turns': {}, 'focus':None, 'event_head':None, 'controlled_cids':[]}


def _validate_state(state):
    require(type(state) is dict and set(state) == {'schema','thread_id','next_ordinal','turns','focus','event_head','controlled_cids'}
            and state['schema'] == 1 and type(state['next_ordinal']) is int
            and state['next_ordinal'] >= 0 and type(state['turns']) is dict,
            'SLOT_HUMAN_STATE_INVALID')
    valid_thread(state['thread_id'])
    require(type(state['controlled_cids']) is list and state['controlled_cids'] == sorted(set(state['controlled_cids']))
        and all(type(cid) is str and cid for cid in state['controlled_cids']), 'SLOT_HUMAN_STATE_INVALID')
    require(state['focus'] is None or type(state['focus']) is dict, 'SLOT_HUMAN_STATE_INVALID')
    require(state['event_head'] is None or type(state['event_head']) is str and len(state['event_head']) == 64,
            'SLOT_HUMAN_STATE_INVALID')
    for turn, item in state['turns'].items():
        valid_thread(turn)
        require(type(item) is dict and set(item) == {'root_turn_id','started_ordinal',
            'context_ordinal','attribution','raw'}, 'SLOT_HUMAN_STATE_INVALID')
        valid_thread(item['root_turn_id'])
        start, context = item['started_ordinal'], item['context_ordinal']
        require(type(start) is int and 0 <= start < state['next_ordinal']
            and (context is None or type(context) is int and start < context < state['next_ordinal'])
            and type(item['attribution']) is dict, 'SLOT_HUMAN_STATE_INVALID')
        if item['raw'] is not None:
            raw = item['raw']
            require(type(raw) is dict and set(raw) in (
                {'ordinal','response_id','text_sha256','created'},
                {'ordinal','response_id','text_sha256','created','opaque_images'})
                and context is not None and context < raw['ordinal'] < state['next_ordinal']
                and type(raw['response_id']) is str and bool(raw['response_id'])
                and type(raw['text_sha256']) is str and len(raw['text_sha256']) == 64,
                'SLOT_HUMAN_STATE_INVALID')
            if 'opaque_images' in raw:
                from .slot_control_text_profile import validate_descriptor
                validate_descriptor(raw['opaque_images'])


def pending_ordinals(state):
    result = set()
    for item in state['turns'].values():
        result.add(str(item['started_ordinal']))
        if item['context_ordinal'] is not None: result.add(str(item['context_ordinal']))
        if item['raw'] is not None: result.add(str(item['raw']['ordinal']))
    return result


def consume(state, record, *, allow_opaque_images=False):
    """record is the actual verified Record, not an MCP dictionary.

    Raw native response ids and typed UserMessage ids are distinct domains.
    The pair is tied by the actual task/thread and exact complete text digest.
    """
    _validate_state(state)
    require(type(allow_opaque_images) is bool, 'SLOT_HUMAN_STATE_INVALID')
    require(allow_opaque_images or all(item['raw'] is None or 'opaque_images' not in item['raw']
        for item in state['turns'].values()), 'SLOT_HUMAN_IMAGE_PROFILE_NOT_ENABLED')
    row = record.value
    require(row['ordinal'] == state['next_ordinal'], 'SLOT_HUMAN_ORDINAL_INVALID')
    result = deepcopy(state); result['next_ordinal'] += 1
    data, family, ordinal = row['payload'], row['type'], row['ordinal']
    kind = data.get('type'); turns = result['turns']; facts = []
    if family == 'event_msg' and kind == 'task_started':
        turn = data.get('turn_id'); valid_thread(turn)
        attr = data.get('turn_attribution')
        require(type(attr) is dict and attr.get('turn_id') == turn
            and {'root_turn_id','turn_trigger','parent_turn_id','initiating_agent_path'} <= set(attr)
            and turn not in turns, 'SLOT_HUMAN_TASK_INVALID')
        root = attr['root_turn_id']; valid_thread(root)
        require(data.get('root_turn_id', root) == root, 'SLOT_HUMAN_TASK_INVALID')
        turns[turn] = {'root_turn_id':root, 'started_ordinal':ordinal,
            'context_ordinal':None,'attribution':deepcopy(attr),'raw':None}
    elif family == 'turn_context':
        turn = data.get('turn_id'); valid_thread(turn)
        require(turn in turns, 'SLOT_HUMAN_CONTEXT_INVALID')
        if turns[turn]['context_ordinal'] is None: turns[turn]['context_ordinal'] = ordinal
    elif family == 'response_item' and kind == 'message' and data.get('role') == 'user':
        raw = _slot_response(record, state['thread_id'], turns, allow_opaque_images=allow_opaque_images)
        if raw is not None and 'configuration_turn' not in raw:
            turn = raw['turn_id']
            require(turn in turns and turns[turn]['context_ordinal'] is not None
                and turns[turn]['raw'] is None, 'SLOT_HUMAN_PAIR_PENDING')
            meta = data['internal_chat_message_metadata_passthrough']
            created = meta.get('create_time', row.get('timestamp'))
            require(created is None or type(created) in (int,float,str), 'SLOT_HUMAN_TIME_INVALID')
            turns[turn]['raw'] = {'ordinal':ordinal,'response_id':raw['response_id'],
                'text_sha256':raw['text_sha256'],'created':created}
            if 'opaque_images' in raw:
                turns[turn]['raw']['opaque_images'] = deepcopy(raw['opaque_images'])
    elif family == 'event_msg' and kind == 'item_completed':
        item = data.get('item')
        if type(item) is dict and item.get('type') == 'UserMessage':
            turn = data.get('turn_id'); valid_thread(turn); ident = item.get('id'); valid_thread(ident)
            require(data.get('thread_id') == state['thread_id'] and turn in turns,
                'SLOT_HUMAN_TYPED_IDENTITY_INVALID')
            content = item.get('content')
            current = turns[turn]; raw = current['raw']
            if raw is not None and 'opaque_images' in raw:
                from .slot_control_text_profile import typed_body
                text = typed_body(content, raw['opaque_images'])
            else:
                require(type(content) is list and len(content) == 1 and type(content[0]) is dict
                    and set(content[0]) == {'type','text','text_elements'} and content[0]['type'] == 'text'
                    and type(content[0]['text']) is str and content[0]['text_elements'] == [],
                    'SLOT_HUMAN_TYPED_CONTENT_INVALID')
                text = content[0]['text']
            require(raw is not None and sha256(text.encode('utf8')).hexdigest()
                == raw['text_sha256'], 'SLOT_HUMAN_PAIR_INVALID')
            facts.append({'schema':1,'authority':False,'thread_id':state['thread_id'],
                'turn_id':turn,'root_turn_id':current['root_turn_id'],'item_id':ident,
                'response_id':raw['response_id'],'text_sha256':raw['text_sha256'],
                'created':raw['created'],'attribution':deepcopy(current['attribution']),
                'started_ordinal':current['started_ordinal'],'context_ordinal':current['context_ordinal'],
                'raw_ordinal':raw['ordinal'],'typed_ordinal':ordinal})
            if 'opaque_images' in raw:
                facts[-1]['opaque_images'] = deepcopy(raw['opaque_images'])
            current['raw'] = None
    elif family == 'event_msg' and kind == 'user_message':
        raise SourceHold('SLOT_HUMAN_LEGACY_UNPAIRED')
    elif family == 'event_msg' and kind in ('task_complete','task_aborted','turn_aborted'):
        turn = data.get('turn_id'); valid_thread(turn)
        require(turn in turns and turns[turn]['raw'] is None, 'SLOT_HUMAN_PAIR_PENDING')
        turns.pop(turn)
    _validate_state(result)
    return result, facts
