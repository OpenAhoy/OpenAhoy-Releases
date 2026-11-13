"""Group-only current stream facts from original retained Native/index FDs.

Resource callbacks are cancellation guards, never permission validators. The
Host must independently issue a current binding after its original QA checks.
"""
from dataclasses import dataclass, field, replace
from hashlib import sha256
import json
import os
import threading
import time
from weakref import WeakKeyDictionary

from .draft_revision_native_source import (Record, SourceHold, MAX_LINE, MAX_RECORDS,
    canonical, strict_json, registration_digest, _metadata_origin)
from .draft_revision_native_lookup import NativeThreadLookup
from .draft_group_native_stream import NativeStreamEntry, _Pin, _IndexPin, _snapshot_source, _base, _generation
from .draft_group_native_v2_replay import GroupRawReplayV2
from .draft_group_native_v2_interpreter import ChargedState, FiniteInterpreterV2, need, digest
from .draft_group_native_v2_codec import (decode_baseline, decode_runtime_policy,
    validate_observation, validate_checkpoint, CATEGORIES, MAX_PREFIX, MAX_RETAINED)
from .draft_group_native_v2_spans import fixed_body_spans, required_control_bytes

_CAPTURES = WeakKeyDictionary()


def _pin_facts(pin):
    return (pin, pin.fd, pin.parent, pin.name, pin.structure, tuple(pin.generation),
            tuple(pin.chain), tuple(pin.ancestors))


def _check_pin_facts(facts):
    pin, fd, parent, name, structure, generation, chain, ancestors = facts
    need(pin.fd == fd and pin.parent == parent and pin.name == name and pin.structure is structure
         and tuple(pin.generation) == generation and tuple(pin.chain) == chain
         and tuple(pin.ancestors) == ancestors, 'CAPTURE_MIRROR_CHANGED')
    need(_generation(os.fstat(fd),structure=structure) == generation
         == _generation(os.stat(name,dir_fd=parent,follow_symlinks=False),structure=structure), 'CHANGED')
    for (directory,name,identity),(original,attributes) in zip(chain,ancestors):
        info = os.stat(name,dir_fd=directory,follow_symlinks=False)
        need((info.st_dev,info.st_ino) == identity == original
             and _generation(info)[:6] == attributes, 'CHANGED')


@dataclass(frozen=True)
class _CaptureFacts:
    entry: object
    raw: bytes
    policy_raw: bytes
    request: bytes
    sources: tuple
    source_images: tuple
    lookups: tuple
    lookup_images: tuple
    pins: tuple
    indices: tuple
    full: object
    loop: object
    thread: int
    wall_start: float
    monotonic_start: float
    not_after: float
    deadline: float
    located_in_entry: bool
    observation_raw: bytes|None=None
    whole_records: tuple=()


def validate_native_v2_observer_capture(observer):
    """Private resource facts, still authority=False; never a Host gate."""
    need(type(observer) is GroupNativeV2SourceObserver, 'OBSERVER_TYPE')
    facts = _CAPTURES.get(observer)
    need(facts is not None and not observer._closed and not observer._poisoned
         and facts.thread == threading.get_ident(), 'CAPTURE_UNISSUED')
    entry = facts.entry
    need(observer._entry is entry and observer._raw is facts.raw and observer._policy_raw is facts.policy_raw
         and observer._request == facts.request and tuple(observer._sources) == facts.sources
         and all(_base(s) == image for s,image in zip(facts.sources,facts.source_images))
         and len(observer._sources) == len(facts.sources)
         and observer._lookups is facts.lookups
         and entry._full_callback is facts.full and entry._loop_callback is facts.loop,
         'CAPTURE_MIRROR_CHANGED')
    cached=observer._cached
    if facts.observation_raw is None:
        need(cached is None,'CAPTURE_OBSERVATION_UNISSUED')
    else:
        need(type(cached) is GroupSourceObservationV2 and type(cached.raw) is bytes
             and cached.raw==facts.observation_raw,'CAPTURE_OBSERVATION_CHANGED')
    from .draft_group_input_files import _plain
    _plain(observer._material);_plain(observer._policy);_plain(observer._historical);_plain(observer._prefix_markers)
    need(canonical([observer._material,observer._policy,observer._historical,observer._prefix_markers])==facts.request,
         'CAPTURE_REQUEST_CHANGED')
    for lookup,image in zip(facts.lookups,facts.lookup_images):
        need((str(lookup.state_path),str(lookup.session_root),lookup.owner_thread,
              tuple(sorted(lookup.allowed_threads))) == image, 'CAPTURE_LOOKUP_CHANGED')
    need(set(entry._pins) == {key for key,_ in facts.pins}
         and set(entry._indices) == {key for key,*_ in facts.indices}, 'CAPTURE_PIN_CHANGED')
    for key,pin in facts.pins:
        need(entry._pins[key] is pin[0], 'CAPTURE_PIN_CHANGED'); _check_pin_facts(pin)
    for key,index,main,sides,format_bytes in facts.indices:
        need(entry._indices[key] is index and index.main is main[0]
             and index.format == format_bytes and set(index.sides) == {k for k,_ in sides}, 'CAPTURE_INDEX_CHANGED')
        _check_pin_facts(main)
        need(os.pread(main[1],20,0) == format_bytes, 'CHANGED')
        for suffix,pin in sides:
            if pin is not None:
                need(index.sides[suffix] is pin[0], 'CAPTURE_INDEX_CHANGED'); _check_pin_facts(pin)
            else:
                need(index.sides[suffix] is None, 'CAPTURE_INDEX_CHANGED')
                try:os.stat(main[3]+suffix,dir_fd=main[2],follow_symlinks=False)
                except FileNotFoundError:pass
                else:raise SourceHold('GROUP_NATIVE_V2_CHANGED')
    need(time.time() < facts.not_after and time.monotonic() < facts.deadline, 'SOURCE_EXPIRED')
    return facts


@dataclass(frozen=True, slots=True)
class GroupSourceObservationV2:
    raw: bytes = field(repr=False)

    @property
    def authority(self):
        return False

    @property
    def value(self):
        value = strict_json(self.raw, maximum=MAX_RETAINED, nodes=1000000)
        return validate_observation(value)

    @property
    def summary(self):
        value = self.value
        return {'profile':value['profile'],'authority':False,'material_sha256':value['material_sha256'],
                'semantic_scope_sha':value['semantic_scope_sha'],'sources':len(value['sources']),
                'records':value['record_count'],'users':len(value['permission_facts']['users']),
                'assistant_facts':len(value['permission_facts']['selected_assistant_facts']),
                'qa_adoption_status':value['qa_adoption_status'],'retention_status':value['assistant_retention_status']}


class GroupNativeV2SourceObserver:
    def __init__(self, baseline_raw, policy_raw, registrations, full, loop, *, lookups,
                 checkpoints=(),prefix_markers=()):
        self._raw = baseline_raw
        self._policy_raw = policy_raw
        self._material = decode_baseline(baseline_raw)
        self._policy = decode_runtime_policy(policy_raw)
        need(self._policy['baseline_source_sha'] == sha256(baseline_raw).hexdigest()
             and self._policy['semantic_scope_sha'] == self._material['semantic_scope_sha'], 'POLICY_BINDING')
        need(type(registrations) is tuple and 0 <= len(registrations) <= 4
             and type(lookups) is tuple and 0 < len(lookups) <= 64, 'RESOURCE')
        need(type(checkpoints) is tuple and len(checkpoints) <= 256, 'CHECKPOINT_RESOURCE')
        self._historical = []
        for item in checkpoints:
            need(type(item) is dict and set(item) == {'source_id','checkpoint'}, 'CHECKPOINT_FIELDS')
            validate_checkpoint(item['checkpoint'])
            self._historical.append(json.loads(canonical(item)))
        need(type(prefix_markers) is tuple and len(prefix_markers)<=256,'PREFIX_MARKER_RESOURCE')
        self._prefix_markers=[];seen=set()
        for item in prefix_markers:
            from .draft_group_input_files import _plain,_id,_hash,_int
            _plain(item)
            need(type(item) is dict and set(item)=={'source_id','end','prefix_sha256'},'PREFIX_MARKER_FIELDS')
            _id(item['source_id']);_int(item['end'],0,MAX_PREFIX);_hash(item['prefix_sha256'])
            key=item['source_id'],item['end']
            need(key not in seen,'PREFIX_MARKER_DUPLICATE');seen.add(key)
            self._prefix_markers.append(json.loads(canonical(item)))
        self._entry = NativeStreamEntry(full,loop)
        self._lookups = lookups
        self._sources = ()
        self._closed = self._busy = self._poisoned = self._prepared = False
        self._cached = None
        self._interpreters = ()
        self._second_record_count = 0
        self._started_wall = time.time()
        self._started_mono = time.monotonic()
        self._not_after = min(self._started_wall+240,
            self._material['expires_policy']['not_after'], self._policy['original_input_not_after_ms']/1000)
        rights = self._policy['original_source_rights_expiry']
        if rights['kind'] == 'EXPLICIT_UNTIL':
            self._not_after = min(self._not_after, rights['not_after']/1000)
        self._deadline = self._started_mono + self._not_after-self._started_wall
        self._thread = threading.get_ident()
        self._request = canonical([self._material,self._policy,self._historical,self._prefix_markers])
        identities = self._material['source_identities']
        source_ids={x['source_id'] for x in identities}
        need(all(x['source_id'] in source_ids for x in self._historical+self._prefix_markers),'PREFIX_MARKER_SOURCE')
        need(all(type(x) is NativeThreadLookup for x in lookups), 'LOOKUP_TYPE')
        located_in_entry = not registrations
        if located_in_entry:
            actual=[]
            for identity in identities:
                matches=[x for x in lookups if identity['thread_id'] in x.allowed_threads]
                need(len(matches)==1,'LOOKUP_SCOPE')
                # This lookup reads the first Native header. The original local
                # t0 above already exists, including its fixed source deadline.
                self._entry._full()
                need(time.time()<self._not_after and time.monotonic()<self._deadline,'SOURCE_EXPIRED')
                actual.append(matches[0].locate(identity['thread_id']))
                need(time.time()<self._not_after and time.monotonic()<self._deadline,'SOURCE_EXPIRED')
            registrations=tuple(actual)
        self._sources = tuple(_snapshot_source(x) for x in registrations)
        need(len({s.source_id for s in self._sources}) == len(self._sources)
             and [s.source_id for s in self._sources] == [x['source_id'] for x in identities], 'SOURCE_SCOPE')
        physical = set(); groups = []
        for source, identity in zip(self._sources,identities):
            need(source.start_offset == 0 and source.start_ordinal == source.metadata_ordinal,
                 'REGISTRATION_START_ZERO')
            actual = {'source_id':source.source_id,'thread_id':source.thread_id,
                'path_utf8_sha256':sha256(str(source.path).encode()).hexdigest(),'device':source.device,
                'inode':source.inode,'session_meta_sha256':source.session_meta_sha256,'metadata_ordinal':source.metadata_ordinal}
            need(canonical(identity) == canonical(actual), 'SOURCE_IDENTITY')
            key = source.device,source.inode
            need(key not in physical, 'SOURCE_ALIAS'); physical.add(key)
            matches = [x for x in lookups if source.thread_id in x.allowed_threads]
            need(len(matches) == 1, 'LOOKUP_SCOPE')
            groups.append((source,(),matches[0]))
        self._entry._groups = tuple(groups)
        try:
            # t0 precedes first Native FD/header/lookup. Never pin a new EOF later.
            need(time.time() < self._not_after and time.monotonic() < self._deadline, 'SOURCE_EXPIRED')
            for source in self._sources:
                self._entry._pins[source.thread_id] = _Pin(source)
            for lookup in lookups:
                if lookup.state_path not in self._entry._indices:
                    self._entry._indices[lookup.state_path] = _IndexPin(lookup.state_path)
            self._entry._lookups = lookups
            self._entry._request = self._request
            marker_total=0
            for source in self._sources:
                end=self._entry._pins[source.thread_id].generation[6]
                start=next(x['reference']['byte_start'] for x in self._material['interpretation_starts'] if x['source_id']==source.source_id)
                ends={0,end,start}
                ends.update(x['end_byte'] for x in self._material['baseline_commitments'] if x['source_id']==source.source_id)
                ends.update(x['checkpoint']['end'] for x in self._historical if x['source_id']==source.source_id)
                ends.update(x['end'] for x in self._prefix_markers if x['source_id']==source.source_id)
                need(all(0<=x<=end for x in ends),'PREFIX_MARKER_EOF')
                marker_total+=len(ends)
            need(marker_total<=256,'CHECKPOINT_RESOURCE')
            _CAPTURES[self] = _CaptureFacts(self._entry,self._raw,self._policy_raw,self._request,
                self._sources,tuple(_base(s) for s in self._sources),lookups,
                tuple((str(l.state_path),str(l.session_root),l.owner_thread,tuple(sorted(l.allowed_threads))) for l in lookups),
                tuple((key,_pin_facts(pin)) for key,pin in self._entry._pins.items()),
                tuple((key,index,_pin_facts(index.main),tuple((suffix,None if pin is None else _pin_facts(pin))
                    for suffix,pin in index.sides.items()),index.format) for key,index in self._entry._indices.items()),
                self._entry._full_callback,self._entry._loop_callback,self._thread,
                self._started_wall,self._started_mono,self._not_after,self._deadline,located_in_entry)
            self._full()
            self._entry._locate()
            self._check_time()
        except BaseException:
            self.close(); raise

    def _check_time(self):
        facts = _CAPTURES.get(self)
        need(facts is not None and not self._closed and not self._poisoned
             and threading.get_ident() == facts.thread, 'ENTRY_CLOSED_OR_THREAD')
        need(time.time() < facts.not_after and time.monotonic() < facts.deadline, 'SOURCE_EXPIRED')

    def _loop(self):
        self._check_time(); self._entry._loop(); self._check_time()
        return True

    def _full(self):
        self._loop(); self._entry._full(); self._entry._pure_fence(); self._check_time()
        return True

    def _call(self, operation):
        try:
            self._check_time(); need(not self._busy, 'REENTRANT')
            self._busy = True
            return operation()
        except BaseException:
            self._poisoned = True; self.close(); raise
        finally:
            self._busy = False

    def _pass(self, source, pin, replay, charge, *, first):
        self._full()
        end = pin.generation[6]
        need(0 < end <= MAX_PREFIX, 'PREFIX_LIMIT')
        start = next(x['reference'] for x in self._material['interpretation_starts'] if x['source_id'] == source.source_id)
        need(start['byte_end'] <= end, 'START_EOF')
        markers = {0,end,start['byte_start']}
        expectations = [x for x in self._material['baseline_commitments'] if x['source_id'] == source.source_id]
        historical = [x['checkpoint'] for x in self._historical if x['source_id'] == source.source_id]
        prefix_markers=[x for x in self._prefix_markers if x['source_id']==source.source_id]
        markers.update(x['end_byte'] for x in expectations)
        markers.update(x['end'] for x in historical)
        markers.update(x['end'] for x in prefix_markers)
        need(len(markers) <= 256 and all(0 <= x <= end for x in markers), 'CHECKPOINT_RESOURCE')
        seed = {'source_registration_sha256':registration_digest(source),
                'interpretation_start':start['byte_start'],'interpretation_start_ordinal':start['ordinal']}
        ordered = sha256(b'GROUP_NATIVE_ORDERED_RECORDS_V2\0'+canonical(seed)).hexdigest()
        control = sha256(b'GROUP_NATIVE_CONTROL_BYTES_V2\0'+canonical(seed)).hexdigest()
        prefix_hash = sha256()
        counts = dict.fromkeys(CATEGORIES,0)
        checkpoints = []
        def checkpoint(offset, ordinal):
            if offset in markers:
                checkpoints.append({'end':offset,'absolute_end_ordinal':ordinal,'prefix_sha256':prefix_hash.hexdigest(),
                                    'ordered_records_sha256':ordered,'control_sha256':control})
        interpreter = FiniteInterpreterV2(source,self._material,self._policy,replay,self._loop,charge)
        offset = count = control_count = control_bytes = 0
        checkpoint(0,source.metadata_ordinal)
        os.lseek(pin.fd,0,os.SEEK_SET)
        with os.fdopen(os.dup(pin.fd),'rb',buffering=65536) as stream:
            while offset < end:
                self._loop()
                cumulative=self._entry._record_count if first else self._second_record_count
                need(type(cumulative) is int and 0<=cumulative<MAX_RECORDS,'ENTRY_RECORD_LIMIT')
                raw = stream.readline(min(MAX_LINE+1,end-offset+1))
                need(type(raw) is bytes and raw.endswith(b'\n') and 0 < len(raw) <= MAX_LINE
                     and offset+len(raw) <= end, 'LINE_LIMIT')
                row = strict_json(raw,maximum=MAX_LINE)
                ordinal = source.metadata_ordinal+count
                need(ordinal < MAX_RECORDS and type(row) is dict and type(row.get('ordinal')) is int
                     and row['ordinal'] == ordinal and type(row.get('type')) is str
                     and type(row.get('payload')) is dict, 'RECORD')
                checksum = sha256(raw).hexdigest()
                record = Record(source.source_id,ordinal,offset,offset+len(raw),checksum,raw)
                if offset == 0:
                    need(checksum == source.session_meta_sha256 and row['type'] == 'session_meta'
                         and row['payload'].get('id') == source.thread_id, 'METADATA')
                    _metadata_origin(row,source)
                if offset == start['byte_start']:
                    need(canonical(record.reference()) == canonical(start)
                         and (row['type'] == 'session_meta' or row['type'] == 'event_msg'
                              and row['payload'].get('type') == 'task_started'), 'INTERPRETATION_START')
                if first:
                    self._entry._record_count=cumulative+1
                    replay.capture(raw,self._loop)
                else:
                    self._second_record_count=cumulative+1
                    replay.compare(raw,self._loop)
                category,spans,fragments,fields = interpreter.consume(record,prefix=offset < start['byte_start'])
                counts[category] += 1
                ordered = sha256(b'GROUP_NATIVE_ORDERED_RECORDS_V2\1'+bytes.fromhex(ordered)
                    +canonical([category,record.reference(),digest(row['payload'])])).hexdigest()
                if spans:
                    projection = {'profile':'GROUP_NATIVE_CONTROL_PROJECTION_V2','category':category,
                                  'reference':record.reference(),'fields':fields}
                    control = sha256(b'GROUP_NATIVE_CONTROL_BYTES_V2\1'+bytes.fromhex(control)
                        +canonical([record.reference(),[list(x) for x in spans],
                                    sha256(b''.join(fragments)).hexdigest(),digest(projection)])).hexdigest()
                    control_count += 1; control_bytes += sum(map(len,fragments))
                prefix_hash.update(raw); offset += len(raw); count += 1
                need(count <= MAX_RECORDS, 'RECORD_LIMIT')
                checkpoint(offset,source.metadata_ordinal+count)
                self._loop()
        need(offset == end and {x['end'] for x in checkpoints} == markers, 'CHECKPOINT_BOUNDARY')
        actual = {x['end']:x for x in checkpoints}
        for item in expectations:
            got = actual[item['end_byte']]
            need(got['absolute_end_ordinal'] == item['absolute_end_ordinal']
                 and got['prefix_sha256'] == item['prefix_sha256'], 'BASELINE_PREFIX_CHANGED')
            for key in ('ordered_records_sha256','control_sha256'):
                need(item[key] is None or item[key] == got[key], 'BASELINE_CONTROL_CHANGED')
        for item in historical:
            need(canonical(item) == canonical(actual[item['end']]), 'HISTORICAL_PREFIX_CHANGED')
        for item in prefix_markers:
            need(actual[item['end']]['prefix_sha256']==item['prefix_sha256'],'ORIGIN_PREFIX_CHANGED')
        if first:
            replay.seal()
        else:
            replay.finish(self._loop)
        facts = interpreter.finish()
        self._full()
        summary = {'schema':'GROUP_NATIVE_CURRENT_STREAM_FACTS_V2','authority':False,
            'source_id':source.source_id,'thread_sha256':sha256(source.thread_id.encode()).hexdigest(),
            'source_registration_sha256':registration_digest(source),'interpretation_start':start['byte_start'],
            'interpretation_start_ordinal':start['ordinal'],'prefix_bytes':end,'prefix_sha256':prefix_hash.hexdigest(),
            'record_count':count,'first_ordinal':source.metadata_ordinal,'end_ordinal_exclusive':source.metadata_ordinal+count,
            'category_counts':counts,'request_scope_sha256':digest([seed,expectations,historical,prefix_markers]),
            'generation_sha256':digest([str(x) for x in pin.generation]),'ordered_records_sha256':ordered,
            'control_sha256':control,'control_record_count':control_count,'control_raw_bytes':control_bytes,'checkpoints':checkpoints}
        return interpreter, facts, summary

    def inspect(self, current_material_raw):
        def operation():
            need(type(current_material_raw) is bytes and current_material_raw == self._raw, 'MATERIAL_CHANGED')
            validate_native_v2_observer_capture(self)
            need(canonical([self._material,self._policy,self._historical,self._prefix_markers]) == self._request, 'REQUEST_CHANGED')
            self._full(); self._entry._locate(); self._entry._pure_fence()
            if self._cached is None:
                charge = ChargedState(); interpreters = []; summaries = []; results = []
                for source in self._sources:
                    pin = self._entry._pins[source.thread_id]
                    need(0 < pin.generation[6] <= MAX_PREFIX, 'PREFIX_LIMIT')
                    replay = GroupRawReplayV2(pin.generation[6])
                    previous = charge.bytes,charge.items,charge.retained
                    try:
                        first = self._pass(source,pin,replay,charge,first=True)
                        second_charge = ChargedState()
                        second_charge.bytes,second_charge.items,second_charge.retained = previous
                        second = self._pass(source,pin,replay,second_charge,first=False)
                        need(canonical(first[1:]) == canonical(second[1:])
                             and (charge.bytes,charge.items,charge.retained)
                             == (second_charge.bytes,second_charge.items,second_charge.retained), 'REPLAY_STATE_CHANGED')
                        interpreters.append(first[0]); results.append(first[1]); summaries.append(first[2])
                    finally:
                        replay.discard()
                users = [x for r in results for x in r['users']]
                bindings = [x for r in results for x in r['bindings']]
                permission = {'profile':'GROUP_SOURCE_PERMISSION_FACTS_V2',
                    'original_user_scope':self._material['original_user_scope'],'users':users,
                    'config_bindings':[x for x in bindings if x['category'] == 'CONFIG_NON_AUTH'],
                    'task_bindings':[x for x in bindings if x['category'] == 'TASK_CONTROL'],
                    'selected_assistant_facts':[x for r in results for x in r['qa']],
                    'qa_sources':self._material['qa_sources'],'semantic_scope_sha':self._material['semantic_scope_sha'],
                    'allowed_read_scope':self._material['allowed_read_scope'],'original_expires_policy':self._material['expires_policy']}
                value = {'schema':2,'profile':'GROUP_CURRENT_SOURCE_OBSERVATION_V2','authority':False,
                    'material_sha256':sha256(self._raw).hexdigest(),'semantic_scope_sha':self._material['semantic_scope_sha'],
                    'role_threads':self._material['role_threads'],'sources':summaries,
                    'record_count':sum(x['record_count'] for x in summaries),'permission_facts':permission,
                    'permission_facts_sha256':digest(permission),'retention_summary':{
                        'whole_record_count':sum(r['whole_count'] for r in results),
                        'control_fragment_record_count':sum(r['fragment_count'] for r in results),
                        'required_retained_raw_bytes':charge.retained,'state_charge_bytes':charge.bytes},
                    'qa_adoption_status':'UNPROVEN_REQUIRES_HOST_ARTIFACT_AND_ADOPTION_REVIEW',
                    'assistant_retention_status':'UNVERIFIED','authority_producer':'NONE'}
                validate_observation(value)
                packed = canonical(value); need(len(packed) <= MAX_RETAINED, 'OBSERVATION_LIMIT')
                # The source of truth is immutable bytes and primitive tuples
                # detached from all externally reachable Record/dict mirrors.
                whole=tuple((r.source_id,r.ordinal,r.byte_start,r.byte_end,r.raw_line_sha256,r.raw_line)
                    for interpreter in interpreters for r in interpreter.whole.values())
                need(all(type(v) is str for r in whole for v in (r[0],r[4]))
                     and all(type(v) is int for r in whole for v in r[1:4])
                     and all(type(r[5]) is bytes for r in whole),'CAPTURE_RECORD_TYPE')
                old=_CAPTURES.get(self)
                need(old is not None and old.observation_raw is None,'CAPTURE_ALREADY_SEALED')
                self._cached = GroupSourceObservationV2(packed)
                self._interpreters = tuple(interpreters)
                _CAPTURES[self]=replace(old,observation_raw=packed,whole_records=whole)
            self._full(); self._entry._locate(); self._entry._pure_fence()
            validate_native_v2_observer_capture(self)
            return self._cached
        return self._call(operation)

    def prepare_release(self, current_material_raw):
        value = GroupNativeV2SourceObserver.inspect(self,current_material_raw); self._prepared = True
        return value

    def pure_release_fence(self):
        def operation():
            need(self._prepared and self._cached is not None, 'RELEASE_NOT_PREPARED')
            self._check_time(); self._entry._live(); self._entry._pure_fence(); self._check_time()
            validate_native_v2_observer_capture(self)
        return self._call(operation)

    def finish(self, current_material_raw):
        value = GroupNativeV2SourceObserver.prepare_release(self,current_material_raw)
        GroupNativeV2SourceObserver.pure_release_fence(self)
        return value

    def retained_records(self):
        facts=validate_native_v2_observer_capture(self)
        need(facts.observation_raw is not None,'CAPTURE_NOT_SCANNED')
        records=tuple(Record(*fields) for fields in facts.whole_records)
        from .draft_group_native_source_observer import _copy_record
        return tuple(_copy_record(record) for record in records)

    @property
    def registrations(self):
        return validate_native_v2_observer_capture(self).sources

    def close(self):
        self._closed = True; self._cached = None; self._interpreters = ()
        _CAPTURES.pop(self,None)
        self._entry.close()
