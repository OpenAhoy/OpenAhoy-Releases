"""Finite Group V2 record interpretation. Facts only, no Host authority."""
from hashlib import sha256

from .draft_revision_native_source import Record, SourceHold, canonical
from .draft_revision_native_lookup import valid_thread
from .draft_revision_source_observer import _response
from .draft_group_native_source_observer import _assistant_shape, _technical, record_projection
from .draft_group_native_message_codec import pair_assistant_records
from .draft_group_native_v2_spans import control_fragments


def need(ok, suffix):
    if not ok:
        raise SourceHold('GROUP_NATIVE_V2_' + suffix)


def digest(value):
    return sha256(canonical(value)).hexdigest()


class ChargedState:
    """Exact serialized entry-wide state charge, independent of Python RSS."""
    def __init__(self):
        self.tables = {}
        self.charges = {}
        self.bytes = self.items = self.retained = 0

    def put(self, table, key, value):
        encoded_key = canonical(key)
        identity = table, encoded_key
        old = self.charges.get(identity)
        charge = len(canonical([table,key,value]))
        new_bytes = self.bytes - (old or 0) + charge
        new_items = self.items + (old is None)
        need(new_items <= 500000 and new_bytes+self.retained <= 67108864, 'STATE_RESOURCE')
        self.tables.setdefault(table,{})[encoded_key] = value
        self.charges[identity] = charge
        self.bytes, self.items = new_bytes, new_items

    def remove(self, table, key):
        encoded_key = canonical(key)
        identity = table, encoded_key
        value = self.tables[table].pop(encoded_key)
        self.bytes -= self.charges.pop(identity)
        self.items -= 1
        return value

    def get(self, table, key):
        return self.tables.get(table,{}).get(canonical(key))

    def retain(self, size):
        need(type(size) is int and size >= 0 and self.retained+size+self.bytes <= 67108864,
             'RETAINED_RESOURCE')
        self.retained += size


class FiniteInterpreterV2:
    def __init__(self, source, baseline, policy, replay, loop, charge):
        self.source, self.baseline, self.policy = source, baseline, policy
        self.replay, self.loop, self.charge = replay, loop, charge
        self.sid = source.source_id
        self.tasks = {}; self.contexts = {}; self.pending = {}; self.config_turns = set()
        self.assistants = {}; self.assistant_ids = set(); self.users_seen = set()
        self.whole = {}; self.controls = []; self.bindings = []; self.users = []; self.qa = []
        self.whole_count = self.fragment_count = 0
        self._bound = {canonical(x['reference']):x for x in baseline['retained_bindings']
                       if x['reference']['source_id']==self.sid}
        self._bound_seen = set()
        pairs = list(baseline['typed_raw_pairs'])
        for review in policy['known_user_reviews']:
            pair = {k:review[k] for k in ('human','raw','typed','disposition')}
            old = next((x for x in pairs if x['human'] == pair['human']), None)
            need(old is None or canonical(old) == canonical(pair), 'USER_REVIEW_CONFLICT')
            if old is None:
                pairs.append(pair)
        pairs=[x for x in pairs if x['raw']['source_id']==self.sid]
        self.raw_pairs = {canonical(x['raw']):x for x in pairs}
        self.typed_pairs = {canonical(x['typed']):x for x in pairs}
        need(len(self.raw_pairs) == len(self.typed_pairs) == len(pairs) <= 1024, 'USER_PAIR_DUPLICATE')
        self.selected = {canonical(x[k]):x for x in baseline['selected_assistant_pairs']
                         if x['source_id']==self.sid for k in ('raw','typed')}
        for item in self._bound.values():
            self._state('expected_binding',item['reference'],item)
        for side,values in (('raw',self.raw_pairs),('typed',self.typed_pairs)):
            for item in values.values():self._state('expected_'+side+'_pair',item[side],item)
        for key,item in self.selected.items():
            self._state('expected_qa',key.decode(),item)

    def _state(self, table, key, value):
        self.charge.put(table, [self.sid,key], value)

    def _read(self, reference):
        need(reference['source_id'] == self.sid, 'REFERENCE_SOURCE')
        raw = self.replay.read_captured_range(reference['byte_start'], reference['byte_end'], self.loop)
        need(sha256(raw).hexdigest() == reference['raw_line_sha256'], 'REFERENCE_CHANGED')
        record = Record(self.sid, reference['ordinal'], reference['byte_start'], reference['byte_end'],
                        reference['raw_line_sha256'], raw)
        need(record.value.get('ordinal') == reference['ordinal'], 'REFERENCE_ORDINAL')
        return record

    def _config(self, record, kind):
        reference = record.reference()
        bound = self._bound.get(canonical(reference))
        if bound is not None:
            need(bound['category'] == 'CONFIG_NON_AUTH', 'CONFIG_BINDING')
            return
        rules = [r for r in self.policy['config_equivalence_rules'] if r['kind'] == kind]
        need(len(rules) == 1, 'CONFIG_REVIEW_REQUIRED')
        rule = rules[0]
        original = self._read(rule['reference'])
        old = original.value
        new = record.value
        # Both physical records must independently satisfy original provenance.
        known = dict(self.tasks)
        old_turn = old['payload'].get('internal_chat_message_metadata_passthrough',{}).get('turn_id')
        if old_turn is not None and old_turn not in known:
            # Only a genuinely retained original task is eligible for rebinding.
            prior = self.charge.get('task', [self.sid,old_turn])
            need(prior is not None, 'CONFIG_ORIGINAL_TASK')
            known[old_turn] = prior
        result = _response(original, self.source.thread_id, known)
        need((result is None) == (kind == 'harness'), 'CONFIG_ORIGINAL_KIND')
        if rule['rule'] == 'EXACT_CONFIG_PAYLOAD_V1':
            need(canonical(old['payload']) == canonical(new['payload'])
                 and canonical(old.get('metadata')) == canonical(new.get('metadata')), 'CONFIG_CHANGED')
        else:
            need(kind == 'agents_md' and result is not None, 'CONFIG_RULE')
            # Code-fixed variable leaves; no input-provided exclusion paths.
            import json
            left = json.loads(canonical(old)); right = json.loads(canonical(new))
            for value in (left,right):
                value.pop('ordinal',None); value.pop('timestamp',None)
                metadata = value['payload']['internal_chat_message_metadata_passthrough']
                metadata.pop('create_time',None); metadata.pop('turn_id',None)
            need(canonical(left) == canonical(right), 'CONFIG_CHANGED')

    def _user(self, record, row):
        data = row['payload']; key = canonical(record.reference())
        raw = _response(record, self.source.thread_id, self.tasks)
        if raw is None or 'configuration_turn' in raw:
            kind = 'harness' if raw is None else 'agents_md'
            self._config(record, kind)
            if raw is not None:
                self.config_turns.add(raw['configuration_turn'])
                self._state('config_turn',raw['configuration_turn'],True)
            return 'CONFIG_HARNESS' if raw is None else 'CONFIG_AGENTS', 'CONFIG_NON_AUTH', {
                'kind':kind,'turn_id':None if raw is None else raw['configuration_turn']}
        pair = self.raw_pairs.get(key)
        need(pair is not None, 'NEW_USER_REVIEW_REQUIRED')
        human = pair['human']; turn = raw['turn_id']
        need(human['thread_id'] == self.source.thread_id and turn == human['turn_id']
             and raw['text_sha256'] == human['text_sha256'] and turn in self.contexts
             and turn in self.tasks and turn not in self.pending, 'USER_RAW_BINDING')
        attr = self.tasks[turn]['attribution']
        need(type(attr) is dict and attr.get('turn_id') == turn
             and {'turn_trigger','parent_turn_id','initiating_agent_path'} <= set(attr), 'USER_TASK_ATTRIBUTION')
        self.pending[turn] = raw; self._state('pending_user',turn,raw)
        return 'USER_RAW', 'USER_RAW', {'kind':'USER_RAW','turn_id':turn,
            'response_id':raw['response_id'],'text_sha256':raw['text_sha256'],'client_authored':raw['client_authored']}

    def _typed_user(self, record, data):
        pair = self.typed_pairs.get(canonical(record.reference()))
        need(pair is not None, 'NEW_USER_REVIEW_REQUIRED')
        item = data['item']; human = pair['human']; turn = data.get('turn_id'); ident = item.get('id')
        valid_thread(turn); valid_thread(ident)
        need(data.get('thread_id') == self.source.thread_id == human['thread_id']
             and turn == human['turn_id'] and ident == human['message_id']
             and ident not in self.users_seen, 'USER_TYPED_IDENTITY')
        content = item.get('content')
        need(type(content) is list and len(content) == 1 and type(content[0]) is dict
             and set(content[0]) == {'type','text','text_elements'} and content[0]['type'] == 'text'
             and type(content[0]['text']) is str and content[0]['text_elements'] == [], 'USER_TYPED_CONTENT')
        checksum = sha256(content[0]['text'].encode()).hexdigest()
        raw = self.pending.pop(turn,None)
        need(raw is not None and canonical(raw['record']) == canonical(pair['raw'])
             and checksum == raw['text_sha256'] == human['text_sha256'], 'USER_PAIR')
        raw_record = self._read(raw['record'])
        need(raw_record.value['payload']['content'][0]['text'] == content[0]['text'], 'USER_PAIR')
        self.charge.remove('pending_user',[self.sid,turn])
        attr = self.tasks[turn]['attribution']
        if pair['disposition'] == 'ORIGINAL_REQUEST':
            need(attr['turn_trigger'] == 'composer' and attr['parent_turn_id'] is None
                 and attr['initiating_agent_path'] is None, 'ORIGINAL_COMPOSER_REQUIRED')
        fact = {'kind':'USER_TYPED','thread_id':self.source.thread_id,'turn_id':turn,
                'message_id':ident,'text_sha256':checksum}
        user = {**fact,'disposition':pair['disposition'],'raw':raw['record'],'typed':record.reference(),
                'raw_response_id':raw['response_id'],'text':content[0]['text'],
                'review_status':'EXTERNAL_SEMANTIC_REVIEW_REQUIRED_NOT_AUTHORITY'}
        self.users_seen.add(ident); self.users.append(user)
        self._state('seen_user',ident,True); self._state('user_fact',ident,user)
        return 'USER_TYPED','USER_TYPED',fact

    def _assistant(self, record, row):
        data = row['payload']; raw_side = row['type'] == 'response_item'
        _assistant_shape(data, raw_side=raw_side, loop=self.loop)
        if not raw_side:
            need(data.get('thread_id') == self.source.thread_id and data.get('turn_id') in self.tasks
                 and data.get('turn_id') in self.contexts, 'ASSISTANT_CONTEXT')
        item = data if raw_side else data['item']
        ident = item.get('id')
        metadata = data.get('internal_chat_message_metadata_passthrough') if raw_side else None
        turn = metadata.get('turn_id') if type(metadata) is dict else None if raw_side else data.get('turn_id')
        selected = canonical(record.reference()) in self.selected
        if type(ident) is str and type(turn) is str:
            unique = raw_side, ident
            need(unique not in self.assistant_ids, 'ASSISTANT_ID_DUPLICATE')
            self.assistant_ids.add(unique); self._state('assistant_seen',[raw_side,ident],True)
            pair = self.assistants.setdefault((turn,ident),{})
            pair['raw' if raw_side else 'typed'] = record.reference()
            self._state('assistant_pair',[turn,ident],pair)
        else:
            need(not selected, 'QA_PAIR_IDENTITY')
        category = 'ASSISTANT_RAW' if raw_side else 'ASSISTANT_TYPED'
        return category, 'QA_FACT' if selected else 'ASSISTANT_NON_AUTH', None if selected else {
            'kind':category,'payload_sha256':digest(data)}

    def consume(self, record, *, prefix=False):
        self.loop(); row = record.value; data = row['payload']; outer = row['type']; kind = data.get('type')
        fact = None; binding_category = None; release = 'WHOLE_RECORD'
        if outer == 'session_meta':
            need(record.byte_start == 0 and record.ordinal == self.source.metadata_ordinal, 'DUPLICATE_METADATA')
            category = binding_category = 'SESSION_META'
            fact = {'kind':'session_meta','thread_id':self.source.thread_id,'raw_line_sha256':record.raw_line_sha256}
        elif prefix:
            return 'PREFIX_STRUCTURAL', (), (), []
        elif outer == 'event_msg' and kind == 'task_started':
            turn = data.get('turn_id'); valid_thread(turn)
            need(turn not in self.tasks, 'TASK_DUPLICATE')
            need('thread_id' not in data or data['thread_id'] == self.source.thread_id, 'TASK_THREAD')
            attr = data.get('turn_attribution'); need(attr is None or type(attr) is dict, 'TASK_ATTRIBUTION')
            self.tasks[turn] = {'attribution':attr,'record':record.reference(),'terminal':None}
            self._state('task',turn,self.tasks[turn])
            category, binding_category = 'TASK_STARTED','TASK_CONTROL'
            fact = {'kind':kind,'turn_id':turn,'attribution_sha256':digest(attr)}
        elif outer == 'turn_context':
            turn = data.get('turn_id'); valid_thread(turn)
            need(turn in self.tasks, 'CONTEXT_TASK')
            self.contexts[turn] = record.reference(); self._state('context',turn,record.reference())
            category, binding_category = 'TURN_CONTEXT','TASK_CONTROL'
            fact = {'kind':'turn_context','turn_id':turn,'payload_sha256':digest(data)}
        elif outer == 'response_item' and kind == 'message' and data.get('role') == 'user':
            category,binding_category,fact = self._user(record,row)
        elif outer == 'event_msg' and kind == 'item_completed' and type(data.get('item')) is dict and data['item'].get('type') == 'UserMessage':
            category,binding_category,fact = self._typed_user(record,data)
        elif (outer == 'response_item' and kind == 'message' and data.get('role') == 'assistant'
              or outer == 'event_msg' and kind == 'item_completed' and type(data.get('item')) is dict and data['item'].get('type') == 'AgentMessage'):
            category,binding_category,fact = self._assistant(record,row)
            if binding_category != 'QA_FACT':
                release = category + '_NONSELECTED'
        else:
            binding_category,fact = _technical(record,row,self.source,self.tasks,self.loop)
            if outer == 'event_msg' and kind in ('task_complete','turn_aborted'):
                category = 'TASK_TERMINAL'; self._state('task',data['turn_id'],self.tasks[data['turn_id']])
            elif outer == 'event_msg' and kind == 'token_count':
                category = 'USAGE'; release = 'TOKEN_COUNT'; binding_category = None
            else:
                kinds = {'function_call':'FUNCTION_CALL','custom_tool_call':'CUSTOM_TOOL_CALL',
                         'function_call_output':'FUNCTION_RESULT','custom_tool_call_output':'CUSTOM_TOOL_RESULT'}
                need(kind in kinds, 'RECORD_KIND_UNSUPPORTED')
                category = 'TOOL_CALL' if kind in ('function_call','custom_tool_call') else 'TOOL_RESULT'
                release = kinds[kind]; binding_category = None
        _, spans, fragments, fields = control_fragments(record.raw_line, release_kind=release, _loop=self.loop)
        self.charge.retain(sum(map(len,fragments)))
        if release == 'WHOLE_RECORD':
            self.whole[canonical(record.reference())] = record
            self.whole_count += 1
        else:
            self.controls.append((record.reference(),spans,fragments)); self.fragment_count += 1
        self._state('retained_record',record.ordinal,{'reference':record.reference(),'spans':[list(x) for x in spans]})
        if binding_category is not None and fact is not None:
            self._binding(record,binding_category,fact)
        return category, spans, fragments, fields

    def _binding(self, record, category, fact):
        value = {'category':category,'reference':record.reference(),
                 'payload_canonical_sha256':digest(record.value['payload']),
                 'safe_projection_sha256':record_projection(record,category,fact)}
        expected = self._bound.get(canonical(record.reference()))
        if expected is not None:
            need(canonical(expected) == canonical(value), 'RECORD_BINDING_CHANGED')
            self._bound_seen.add(canonical(record.reference()))
            self._state('expected_binding_seen',record.reference(),True)
        self.bindings.append(value); self._state('record_binding',record.ordinal,value)

    def finish(self):
        need(not self.pending and self.config_turns <= set(self.contexts), 'USER_OR_CONFIG_INCOMPLETE')
        expected = {x['human']['message_id'] for x in self.typed_pairs.values()
                    if x['human']['thread_id'] == self.source.thread_id}
        need(self.users_seen == expected, 'USER_EXPECTED_MISSING')
        consumed = set()
        for (turn,ident), refs in self.assistants.items():
            self.loop()
            selected = any(canonical(r) in self.selected for r in refs.values())
            if set(refs) != {'raw','typed'}:
                need(not selected, 'QA_PAIR_MISSING')
                continue
            raw,typed = self._read(refs['raw']),self._read(refs['typed'])
            value = pair_assistant_records(raw,typed,thread_id=self.source.thread_id)
            need(turn in self.tasks and turn in self.contexts, 'QA_CONTEXT')
            if selected:
                key = canonical(refs['raw']); selected_pair = self.selected.get(key)
                need(selected_pair is not None and canonical(selected_pair['typed']) == canonical(refs['typed'])
                     and canonical(self.tasks[turn]['terminal']) == canonical(selected_pair['terminal']), 'QA_TERMINAL')
                terminal = self._read(selected_pair['terminal'])
                need(terminal.value['type'] == 'event_msg' and terminal.value['payload'].get('type') == 'task_complete', 'QA_TERMINAL')
                fact = {'pair':value,'task':self.tasks[turn]['record'],'context':self.contexts[turn],
                        'terminal':selected_pair['terminal']}
                self.qa.append(fact); self._state('qa_fact',ident,fact)
                for side,record in (('raw',raw),('typed',typed)):
                    self._binding(record,'QA_FACT',{'kind':'QA_FACT_'+side.upper(),'pair_sha256':digest(value)})
                    consumed.add(canonical(record.reference()))
        required = {key for key,pair in self.selected.items() if pair['source_id'] == self.sid}
        need(consumed == required, 'QA_EXPECTED_MISSING')
        need(self._bound_seen == {key for key,item in self._bound.items()
                                if item['reference']['source_id'] == self.sid}, 'EXPECTED_BINDING_MISSING')
        self.bindings.sort(key=lambda x:x['reference']['ordinal'])
        return {'users':self.users,'qa':self.qa,'bindings':self.bindings,
                'whole_count':self.whole_count,'fragment_count':self.fragment_count}
