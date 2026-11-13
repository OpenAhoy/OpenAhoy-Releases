"""Incremental native producer facts, never human or publication authority.

The caller owns source identity, byte verification and durable checkpoints.
This pure codec accepts successive records without a cumulative record cap.
Pending pairs can cross processing batches and survive a serialized checkpoint.
"""
from copy import deepcopy
from hashlib import sha256

from .contracts import WCEError
from .slot_visible_projection import PROFILE as VISIBLE_PROFILE,project,validate as validate_projection


def _need(condition):
    if not condition:
        raise WCEError('SLOT_NATIVE_PAIR_INVALID')


def _identifier(value):
    _need(type(value) is str and bool(value) and value.isprintable())
    return value


def _text_fingerprint(parts, kind, *, raw=False):
    _need(type(parts) is list and len(parts) == 1)
    item = parts[0]
    required = {'type', 'text', 'annotations', 'logprobs'} if raw else {'type', 'text'}
    _need(type(item) is dict and set(item) == required and item['type'] == kind
          and type(item['text']) is str)
    if raw:
        _need(item['annotations'] == [] and item['logprobs'] == [])
    encoded = item['text'].encode('utf-8', errors='strict')
    return {'sha256': sha256(encoded).hexdigest(), 'bytes': len(encoded)}


def initial_state(thread_id, next_ordinal=0, *, projection_profile=None):
    """Only a source owner's continuous checkpoint may select the ordinal."""
    _identifier(thread_id)
    _need(type(next_ordinal) is int and next_ordinal >= 0)
    _need(projection_profile in (None,VISIBLE_PROFILE))
    value={'schema':1 if projection_profile is None else 2,'thread_id':thread_id,
        'next_ordinal':next_ordinal,'turns':{}}
    if projection_profile is not None:value['projection_profile']=VISIBLE_PROFILE
    return value


def _validate_state(state):
    _need(type(state)is dict and type(state.get('schema'))is int and state['schema']in(1,2))
    fields={'schema','thread_id','next_ordinal','turns'}
    if state['schema']==2:
        fields.add('projection_profile');_need(state.get('projection_profile')==VISIBLE_PROFILE)
    _need(set(state)==fields)
    _need(type(state['schema']) is int
          and type(state['next_ordinal']) is int and state['next_ordinal'] >= 0
          and type(state['turns']) is dict)
    _identifier(state['thread_id'])
    for turn, item in state['turns'].items():
        _identifier(turn)
        _need(type(item) is dict and set(item) == {
            'root_turn_id', 'started_ordinal', 'context_ordinal', 'typed', 'raw'})
        _identifier(item['root_turn_id'])
        start = item['started_ordinal']
        context = item['context_ordinal']
        _need(type(start) is int and 0 <= start < state['next_ordinal'])
        _need(context is None or type(context) is int and start < context < state['next_ordinal'])
        for name in ('typed', 'raw'):
            pair = item[name]
            if pair is None:
                continue
            projected=(name=='raw' and state['schema']==2 and type(pair)is dict and 'projection'in pair)
            _need(type(pair) is dict and set(pair) == ({'item_id','text','ordinal','projection'}if projected else {'item_id','text','ordinal'}))
            _identifier(pair['item_id'])
            _need(type(pair['ordinal']) is int and context is not None
                  and context < pair['ordinal'] < state['next_ordinal'])
            text = pair['text']
            _need(type(text) is dict and set(text) == {'sha256', 'bytes'}
                  and type(text['sha256']) is str and len(text['sha256']) == 64
                  and all(char in '0123456789abcdef' for char in text['sha256'])
                  and type(text['bytes']) is int and text['bytes'] >= 0)
        if item['raw'] is not None:
            _need(item['typed'] is not None
                  and item['typed']['ordinal'] < item['raw']['ordinal']
                  and item['typed']['item_id'] == item['raw']['item_id'])
            if 'projection'in item['raw']:
                _need(state['schema']==2)
                validate_projection(item['raw']['projection'],item['typed']['text'],item['raw']['text'])
            else:_need(item['typed']['text'] == item['raw']['text'])


def consume(state, record):
    """Return a detached new state and zero or one paired completion facts.

    An exception cannot partially advance the supplied checkpoint. Unknown
    non-completion records are consumed, not mistaken for permission changes.
    Human control interpretation belongs to the separate standing-source lane.
    """
    _validate_state(state)
    _need(type(record) is dict and set(record) == {'ordinal', 'type', 'payload'}
          and type(record['ordinal']) is int
          and record['ordinal'] == state['next_ordinal']
          and type(record['type']) is str and type(record['payload']) is dict)
    result = deepcopy(state)
    ordinal = record['ordinal']
    result['next_ordinal'] += 1
    payload, family = record['payload'], record['type']
    kind = payload.get('type')
    turns = result['turns']
    facts = []
    if family == 'event_msg' and kind == 'task_started':
        turn = _identifier(payload.get('turn_id'))
        root = _identifier(payload.get('root_turn_id'))
        attribution = payload.get('turn_attribution')
        _need(turn not in turns and type(attribution) is dict
              and attribution.get('turn_id') == turn
              and attribution.get('root_turn_id') == root)
        turns[turn] = {'root_turn_id': root, 'started_ordinal': ordinal,
                       'context_ordinal': None, 'typed': None, 'raw': None}
    elif family == 'turn_context':
        turn = _identifier(payload.get('turn_id'))
        _need(turn in turns)
        # Repeated turn_context records are normal during a live turn.
        if turns[turn]['context_ordinal'] is None:
            turns[turn]['context_ordinal'] = ordinal
    elif family == 'event_msg' and kind == 'item_completed':
        item = payload.get('item')
        if type(item) is dict and item.get('phase') == 'final_answer':
            _need(item.get('type') == 'AgentMessage')
            turn = _identifier(payload.get('turn_id'))
            _need(turn in turns and turns[turn]['context_ordinal'] is not None
                  and payload.get('thread_id') == result['thread_id']
                  and turns[turn]['typed'] is None)
            turns[turn]['typed'] = {
                'item_id': _identifier(item.get('id')),
                'text': _text_fingerprint(item.get('content'), 'Text'),
                'ordinal': ordinal}
    elif family == 'response_item' and kind == 'message' and payload.get('role') == 'assistant':
        if payload.get('phase') == 'final_answer':
            metadata = payload.get('internal_chat_message_metadata_passthrough')
            _need(type(metadata) is dict)
            turn = _identifier(metadata.get('turn_id'))
            _need(turn in turns and turns[turn]['context_ordinal'] is not None
                  and payload.get('status') == 'completed'
                  and turns[turn]['typed'] is not None and turns[turn]['raw'] is None)
            raw = {'item_id': _identifier(payload.get('id')),
                   'text': _text_fingerprint(payload.get('content'), 'output_text', raw=True),
                   'ordinal': ordinal}
            typed = turns[turn]['typed']
            _need(typed['item_id'] == raw['item_id'])
            if typed['text']!=raw['text']:
                _need(result['schema']==2)
                raw['projection']=project(payload['content'][0]['text'],typed['text'])
            turns[turn]['raw'] = raw
    elif family == 'event_msg' and kind in ('task_complete', 'task_aborted', 'turn_aborted'):
        turn = _identifier(payload.get('turn_id'))
        _need(turn in turns)
        item = turns.pop(turn)
        _need(payload.get('root_turn_id') == item['root_turn_id'])
        if kind == 'task_complete':
            typed, raw = item['typed'], item['raw']
            if typed is not None or raw is not None:
                text = payload.get('last_agent_message')
                _need(typed is not None and raw is not None and type(text) is str)
                encoded = text.encode('utf-8', errors='strict')
                terminal={'sha256':sha256(encoded).hexdigest(),'bytes':len(encoded)}
                projection=raw.get('projection')
                _need((typed['text']if projection is not None else raw['text'])==terminal)
                fact={'schema':2 if projection is not None else 1,'authority':False,
                    'thread_id': result['thread_id'], 'turn_id': turn,
                    'root_turn_id': item['root_turn_id'], 'item_id': raw['item_id'],
                    'text_sha256':typed['text']['sha256'],
                    'started_ordinal': item['started_ordinal'],
                    'context_ordinal': item['context_ordinal'],
                    'typed_ordinal': typed['ordinal'], 'raw_ordinal': raw['ordinal'],
                    'terminal_ordinal':ordinal}
                if projection is not None:fact.update(projection)
                facts.append(fact)
        # An aborted turn consumes no completion and retains no fake success.
    _validate_state(result)
    return result, facts
