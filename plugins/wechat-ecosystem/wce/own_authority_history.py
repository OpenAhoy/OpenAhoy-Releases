"""Fixed baseline parent evidence; never membership, H, or maintenance authority."""
from contextlib import contextmanager
from dataclasses import dataclass
from dataclasses import replace
from hashlib import sha256
from pathlib import Path
import os
import stat
import sys
from weakref import WeakSet, WeakKeyDictionary

from .own_bootstrap_security import decode, path_check
from .own_history_source import HeldFiles, hold, safe_path, file_metadata
from .own_history_locators import _CheckpointEvidence, _Proofs
from .own_connection_registry import transaction_path, owner_value
from .service import canonical, digest


_ACTIONS, _REQUESTS, _PARENTS, _JOURNAL_PLANS = WeakSet(), WeakSet(), WeakSet(), WeakSet()
_METADATA_PROOF_ACTIONS = WeakSet()
_METADATA_EVIDENCE = WeakSet()
_METADATA_PROOF_REQUESTS = WeakSet()
_FIXED_PAIR_REQUESTS = WeakKeyDictionary()


class _AuthorityFiles(HeldFiles):
    def __init__(self, base):
        super().__init__(base)
        # Maintenance Actions share this aggregate across every Request and
        # final verification; ordinary historical readers keep their own cap.
        self.budget['proof'] = 1024 * 1024
        self.budget['authority'] = 1024 * 1024
        self.streamed['authority'] = 0
        self.limits = dict(self.budget)
        self.work_remaining = {kind: limit * 64 for kind, limit in self.limits.items()}
        self.admitted, self.read_counts = {}, {}
        self.fixed_paths, self.external_sources = set(), set()

    def register_external(self, path):
        path = safe_path(path)
        hold(not path.is_relative_to(self.base) and len(self.external_sources | {path}) <= 32)
        self.external_sources.add(path)

    def file(self, path, *, mutable=False):
        path = safe_path(path)
        if path not in self.external_sources:
            return super().file(path, mutable=mutable)
        hold(not mutable and not path.is_relative_to(self.base))
        if path not in self.files:
            parent = self.parent(path.parent)
            self._capacity(1)
            fd = os.open(path.name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=parent)
            self.stack.callback(os.close, fd)
            info = os.fstat(fd)
            hold(stat.S_ISREG(info.st_mode) and info.st_uid == os.getuid() and info.st_nlink == 1)
            self.files[path] = {'fd':fd,'pin':file_metadata(info),'mutable':False,'raw':None,'category':None}
            self._capacity()
        self.check_file(path)
        return self.files[path]

    def read(self, path, maximum, category, *, force=False):
        path = safe_path(path)
        from .own_account_metadata import account_carrier
        aggregate=account_carrier(path,self.base)
        if path in self.fixed_paths:
            category = 'authority'
            if not aggregate:
                maximum = min(maximum, 262144)
        item = self.file(path)
        size = item['pin']['bytes']
        hold(0 < size and (aggregate or size <= maximum) and category in self.budget
             and item['category'] in (None, category))
        # A fresh, factory-validated Request may observe legitimate metadata
        # writes. Charge each newly pinned generation; do not invent a permanent
        # path identity rule across those original source phases.
        generation = (category, path, tuple(sorted(item['pin'].items())))
        source = (category, path)
        admitted = self.admitted.get(generation)
        if admitted is not None:
            hold(admitted['sha256'] is not None)
        if item['raw'] is not None and not force:
            checksum = sha256(item['raw']).hexdigest()
            hold(admitted is not None and checksum == admitted['sha256'])
            return item['pin'] | {'sha256': checksum}, item['raw']
        # Admission bounds new trusted inputs. Work bounds every actual full
        # reread, including fresh Request holders and final verification passes.
        if admitted is None:
            if not aggregate:
                hold(size <= self.budget[category])
                self.budget[category] -= size
            admitted = {'sha256': None}
            self.admitted[generation] = admitted
        if not aggregate:
            hold(self.read_counts.get(source, 0) < 64 and size <= self.work_remaining[category])
            self.work_remaining[category] -= size
        self.read_counts[source] = self.read_counts.get(source, 0) + 1
        os.lseek(item['fd'], 0, os.SEEK_SET)
        parts, consumed, checksum = [], 0, sha256()
        while consumed < size:
            block = os.read(item['fd'], min(65536, size - consumed))
            hold(bool(block))
            consumed += len(block)
            self.streamed[category] += len(block)
            checksum.update(block)
            parts.append(block)
        self.check_file(path)
        raw = b''.join(parts)
        checksum = checksum.hexdigest()
        hold(consumed == size and (item['raw'] is None or item['raw'] == raw)
             and admitted['sha256'] in (None, checksum))
        admitted['sha256'] = checksum
        item['raw'], item['category'] = raw, category
        return item['pin'] | {'sha256': checksum}, raw

    def verify(self, category=None):
        hold(category is None or category in self.limits)
        selected = []
        sizes = dict.fromkeys(self.limits, 0)
        for path, item in list(self.files.items()):
            self.check_file(path)
            if item['raw'] is not None and (category is None or item['category'] == category):
                from .own_account_metadata import account_carrier
                if not account_carrier(path,self.base):sizes[item['category']] += item['pin']['bytes']
                selected.append((path, item['category']))
        # Reject an excessive sweep before its first disk read. Each source is
        # still fully reread and rehashed at every original real boundary.
        hold(all(size <= self.limits[kind] for kind, size in sizes.items()))
        for path, kind in selected:
            maximum = {'proof': 262144, 'checkpoint': 4 * 1024 * 1024,
                       'record': 2 * 1024 * 1024, 'authority': 262144}[kind]
            self.read(path, maximum, kind, force=True)
        self.check_directories()
        self._capacity()


class _HeldPathGuard:
    """Immutable path/FD guard only. This is deliberately not a SQLite source."""
    def __init__(self, files): self.files = files
    def guard(self):
        self.files.check_directories()
        for path in self.files.files: self.files.check_file(path)


class _AuthorityAction:
    def __init__(self):
        from .own_compatible_upgrade import registry_path
        self.registry = registry_path()
        self.files = _AuthorityFiles(self.registry.parent)
        self.source = _HeldPathGuard(self.files)
        self.proof_nodes = set()
        self.reader = _Proofs(self)
        self.closed = False

    def dependency(self, path, pins):
        from .own_post_body5_upgrade import BASELINE_ATTESTATION_SHA
        selected = [Path(p) for p, checksum in pins.dependencies if checksum == BASELINE_ATTESTATION_SHA]
        hold(selected == [Path(path)])
        if not Path(path).is_relative_to(self.registry.parent): self.files.register_external(path)
        self.files.fixed_paths.add(Path(path))
        hold(len(self.files.fixed_paths) <= 2)
        return self.files.read(path, 262144, 'authority', force=True)[1]

    def __enter__(self):
        _ACTIONS.add(self)
        return self

    def __exit__(self, kind, error, traceback):
        first = error
        try:
            if kind is None: self.files.verify()
        except BaseException as failure:
            first = failure
            raise
        finally:
            self.closed = True; _ACTIONS.discard(self); _METADATA_PROOF_ACTIONS.discard(self)
            try: self.files.close()
            except BaseException:
                if first is None: raise


def action_scope():
    return _AuthorityAction()


def checked_action(action):
    hold(type(action) is _AuthorityAction and action in _ACTIONS and not action.closed)
    action.source.guard()
    return action


@contextmanager
def pins_scope(pins):
    from .own_compatible_upgrade import TrustedInstallerPins
    hold(type(pins) is TrustedInstallerPins)
    if pins._authority_action is None:
        hold(pins._authority_request is None)
        from .own_post_body5_upgrade import BASELINE_ATTESTATION_SHA
        # Unrelated legacy authorities retain their original strict path.
        if not any(checksum == BASELINE_ATTESTATION_SHA for _, checksum in pins.dependencies):
            yield pins
            return
        with action_scope() as action:
            yield replace(pins, _authority_action=action)
    else:
        checked_action(pins._authority_action)
        if pins._authority_request is not None:
            hold(checked_request(pins._authority_request).action is pins._authority_action)
        yield pins


class _AuthorityRequest:
    def __init__(self, action, current_raw, pins):
        from . import own_compatible_upgrade as sdk
        sdk.verify_installer(pins)
        if current_raw is not None:
            hold(type(current_raw) is bytes and len(current_raw) <= sdk.LIMIT
                 and sha256(current_raw).hexdigest() == pins.attestation_sha256)
            current = sdk.decode_json(current_raw, sdk.LIMIT, max_nodes=4096)
            hold(type(current) is dict and current.get('installed') == pins.installed
                 and current.get('contract') == pins.contract)
            sdk.identifier(current.get('operation_id'), 'cup')
        else:
            current = None
        self.action, self.current, self.pins = checked_action(action), current, pins
        self.registry = action.registry
        self.files = _AuthorityFiles(self.registry.parent)
        self.files.budget = action.files.budget
        self.files.streamed = action.files.streamed
        self.files.limits = action.files.limits
        self.files.work_remaining = action.files.work_remaining
        self.files.admitted = action.files.admitted
        self.files.read_counts = action.files.read_counts
        self.absent, self.observed_sources = set(), set()
        self.journal_evidence = None
        self.source = self
        self.proof_nodes = action.proof_nodes
        self.reader = _Proofs(self)
        self.closed = False

    def guard(self):
        hold(not self.closed)
        _HeldPathGuard(self.files).guard()
        for path in self.absent:
            parent = self.files.parents[path.parent]
            try: os.stat(path.name, dir_fd=parent, follow_symlinks=False)
            except FileNotFoundError: continue
            hold(False)

    def observe_source(self, path, *, optional=False):
        path = Path(path)
        hold(len(self.observed_sources | {path}) <= 32)
        self.observed_sources.add(path)
        if not path.is_relative_to(self.registry.parent): self.files.register_external(path)
        self.guard()
        if path in self.absent: return None
        if path in self.action.files.fixed_paths:
            return self.action.files.read(path, 262144, 'authority', force=True)[1]
        try:
            return self.files.read(path, 262144, 'record', force=True)[1]
        except FileNotFoundError:
            if not optional or path in self.files.files: raise
            self.files.parent(path.parent)
            self.absent.add(path)
            self.guard()
            return None


@contextmanager
def request_scope(action, current_raw, pins):
    request = _AuthorityRequest(action, current_raw, pins)
    _REQUESTS.add(request)
    first = None
    try:
        yield request
        if request.journal_evidence is not None: request.journal_evidence.finish()
        request.files.verify()
        request.guard()
    except BaseException as error:
        first = error
        raise
    finally:
        request.closed = True; _REQUESTS.discard(request); _FIXED_PAIR_REQUESTS.pop(request, None)
        _METADATA_PROOF_REQUESTS.discard(request)
        try: request.files.close()
        except BaseException:
            if first is None: raise


def checked_request(request):
    hold(type(request) is _AuthorityRequest and request in _REQUESTS and not request.closed)
    checked_action(request.action)
    return request


def metadata_proof_aggregate(owner, *, reader=None):
    """Recognize a factory-bound metadata graph, not a caller capacity flag."""
    if reader is not None and getattr(owner, 'reader', None) is not reader:
        return False
    if type(owner) is _AuthorityAction:
        action = owner
    elif type(owner) is _AuthorityRequest:
        if owner not in _REQUESTS or owner.closed:
            return False
        action = owner.action
        hold(type(owner.files) is _AuthorityFiles
             and owner.proof_nodes is action.proof_nodes
             and owner.files.budget is action.files.budget
             and owner.files.work_remaining is action.files.work_remaining
             and owner.files.read_counts is action.files.read_counts)
    else:
        return False
    if action not in _METADATA_PROOF_ACTIONS:
        return False
    checked_action(action)
    hold(type(action.files) is _AuthorityFiles and type(action.reader) is _Proofs
         and action.reader.owner is action and type(action.source) is _HeldPathGuard
         and action.source.files is action.files)
    return True


def metadata_evidence_graph(evidence):
    """Recognize only a constructed, live evidence view of an admitted graph."""
    if type(evidence) is not _AuthorityEvidence or evidence not in _METADATA_EVIDENCE:
        return False
    request = checked_request(evidence.request)
    if request not in _METADATA_PROOF_REQUESTS:
        return False
    action = request.action
    hold(evidence.files is action.files and evidence.reader is action.reader
         and evidence.registry == request.registry and evidence.base == request.registry.parent
         and evidence.owner == evidence.qualified['owner'])
    return metadata_proof_aggregate(action, reader=evidence.reader)


def check_metadata_relocation_predecessors(evidence, proof, visited):
    # Reauthenticate immediately before taking the aggregate-only branch.
    hold(metadata_evidence_graph(evidence))
    from .own_history_identity import _check_relocation_predecessor_stems
    _check_relocation_predecessor_stems(proof, visited)


@contextmanager
def source_request(pins, raw=None, *, fixed_view=False):
    action = checked_action(pins._authority_action)
    request = pins._authority_request
    if request is None:
        with request_scope(action, raw, pins) as request:
            yield replace(pins, _authority_request=request)
    else:
        checked_request(request)
        hold(request.action is action)
        if raw is not None:
            if fixed_view:
                from .own_post_body5_upgrade import BASELINE_ATTESTATION_SHA
                hold(sha256(raw).hexdigest() == pins.attestation_sha256 == BASELINE_ATTESTATION_SHA)
            else:
                hold(request.current is not None and request.pins.attestation_sha256 == pins.attestation_sha256
                     and request.pins.installed == pins.installed and request.pins.contract == pins.contract)
        yield pins


def read_fixed_pair(request, pins):
    """The only production role is the original compiled v26 baseline."""
    from . import own_post_body5_upgrade as post
    request = checked_request(request)
    matches = [Path(path) for path, checksum in pins.dependencies
               if checksum == post.BASELINE_ATTESTATION_SHA]
    hold(len(matches) == 1)
    operation = request.action.registry.parent / 'compatible-upgrades' / (post.BASELINE['operation_id'] + '.json')
    attestation = matches[0]
    paths = {operation, attestation}
    files = request.action.files
    hold(files.fixed_paths <= paths)
    files.fixed_paths = paths
    if not attestation.is_relative_to(request.registry.parent): files.register_external(attestation)
    files.proof_lock(operation.with_suffix('.lock'))
    _, op_raw = files.read(operation, 262144, 'authority', force=True)
    _, att_raw = files.read(attestation, 262144, 'authority', force=True)
    hold(sha256(op_raw).hexdigest() == post.BASELINE['record_sha256']
         and sha256(att_raw).hexdigest() == post.BASELINE_ATTESTATION_SHA)
    _FIXED_PAIR_REQUESTS[request] = (op_raw, att_raw)
    return operation, op_raw, attestation, att_raw


def admit_metadata_proof_graph(pins):
    """Post-baseline's pure fixed-pair projection has qualified graph input.

    The producer independently checks the bound fixed pair and whole current
    authority's pure projection. Full historical/source validation follows;
    no usable authority is issued here.
    """
    from .own_body5_upgrade import SOURCE_SHA
    request = checked_request(pins._authority_request)
    if request.current is None:
        # The established direct source_authority API has no attestation raw.
        # Keep its original aggregate domain; do not turn absence into a grant
        # or a new refusal for otherwise valid bounded legacy verification.
        return False
    hold(request in _FIXED_PAIR_REQUESTS
         and request.pins.authority_source_sha256 == SOURCE_SHA
         and pins._authority_action is request.action)
    from . import own_compatible_upgrade as sdk, own_post_body5_upgrade as post
    op_raw, att_raw = _FIXED_PAIR_REQUESTS[request]
    hold(sha256(op_raw).hexdigest() == post.BASELINE['record_sha256']
         and sha256(att_raw).hexdigest() == post.BASELINE_ATTESTATION_SHA)
    anchor = sdk.decode_json(op_raw, sdk.LIMIT, max_nodes=4096)
    original = sdk.decode_json(att_raw, sdk.LIMIT, max_nodes=4096)
    plan = anchor['plan']
    hold(anchor['id'] == post.BASELINE['operation_id'] and anchor['state'] == 'COMMITTED'
         and anchor['completion_origin'] == sdk.ORIGINS[post.extension.MODE]
         and anchor['authority_source_sha256'] == SOURCE_SHA
         and anchor['attestation_sha256'] == plan['attestation_sha256'] == post.BASELINE_ATTESTATION_SHA
         and plan['selected_cids'] == list(request.pins.selected_cids)
         and digest(plan['base']['owner']) == request.pins.owner_digest
         and original['operation_id'] == plan['operation_id']
         and original['transaction_id'] == plan['transaction_id']
         and original['before_snapshot_sha256'] == digest(plan['base'])
         and original['installed']['code_scope'] == plan['base']['scope']
         and original['authority']['schema'] == 2
         and original['authority']['mode'] == post.extension.MODE
         and original['authority']['source_bundle_sha256'] == SOURCE_SHA)
    current = request.current
    sdk.exact(current, 'schema kind plugin_id operation_id transaction_id authority installed registry accounts before_snapshot_sha256 contract issued_at')
    hold(type(current['schema']) is int and current['schema'] == 1
         and current['kind'] == 'TRUSTED_LOCAL_INSTALLER_VERIFIED' and current['plugin_id'] == sdk.PLUGIN
         and current['installed'] == request.pins.installed and current['contract'] == request.pins.contract
         and current['registry']['path'] == str(request.registry)
         and current['registry']['owner_digest'] == request.pins.owner_digest
         and [item['cid'] for item in current['accounts']] == list(request.pins.selected_cids))
    schema = current['authority'].get('schema')
    hold(type(schema) is int and 3 <= schema <= 8)
    expected = post.authority_from(original['authority'])
    from . import own_revision_upgrade, own_group_upgrade
    from . import own_current_publication_upgrade, own_current_correction_upgrade, own_normal_operations_upgrade
    for version, module in ((4, own_revision_upgrade), (5, own_group_upgrade),
                            (6, own_current_publication_upgrade), (7, own_current_correction_upgrade),
                            (8, own_normal_operations_upgrade)):
        if schema >= version:
            expected = (module.authority_from(expected, source_registration=current['authority']['normal_operations_extension'].get('source_registration'))
                        if version == 8 else module.authority_from(expected))
    hold(canonical(current['authority']) == canonical(expected))
    _METADATA_PROOF_ACTIONS.add(checked_action(request.action))
    _METADATA_PROOF_REQUESTS.add(request)
    return True


@dataclass(frozen=True)
class _BaseMember:
    """An authenticated metadata-before view, never a ConnectionPolicy."""
    path: Path
    value: dict
    root_pin: tuple
    image_pin: tuple
    database_pin: tuple

    @property
    def root(self): return self.path.parent
    @property
    def data(self): return self.value['identity']


def _qualified_base(request):
    """Current observation or the same validated operation's immutable before."""
    from . import own_compatible_upgrade as sdk
    from .own_connection_registry import metadata
    request = checked_request(request)
    current, registry = request.current, request.registry
    operation_path = (registry.parent / 'compatible-upgrades' / (current['operation_id'] + '.json')
                      if current is not None else None)
    if operation_path is None or not os.path.lexists(operation_path):
        base = sdk.snapshot(registry, readonly=True, proof_reader=request.reader)
        sdk.validate_base(base)
        stage = {'kind': 'NORMAL_MEMBERS', 'base': base}
    else:
        _, raw = request.files.read(operation_path, sdk.LIMIT, 'record')
        from .own_account_metadata import decode_metadata_strict
        operation = decode_metadata_strict(raw)
        sdk.validate_operation(operation, current, request.pins)
        base = operation['plan']['base']
        observed = sdk.observe(operation, proof_reader=request.reader, phase_reader=request.reader)
        hold(operation['state'] == 'PREPARED' or operation['state'] == observed['state'])
        if observed['state'] == 'UNKNOWN':
            # The original observer validates the exact prepared inner record.
            # Validate every partial slot too, without asking it to be a member first.
            transaction = operation['plan']['transaction']
            hold(type(transaction) is dict
                 and canonical(metadata(registry)) in (canonical(transaction['before']), canonical(transaction['after'])))
            for path, item in base['policies'].items():
                change = transaction['policies'].get(path)
                allowed = (change['before'], change['after']) if change is not None else (item['value'],)
                hold(canonical(metadata(Path(path))) in tuple(canonical(value) for value in allowed))
        stage = {'kind': 'ORIGINAL_OPERATION', 'record': operation, 'observation': observed}
    hold(base['registry'] == str(registry) and digest(base['owner']) == request.pins.owner_digest
         and set(base['registry_value']['connections']) == set(request.pins.selected_cids))
    # Capture actual current slots separately. The qualified before remains unchanged.
    request.files.read(registry, 262144, 'record')
    request.files.read(registry.parent / 'connection-owner.json', 16384, 'record')
    for path, item in base['policies'].items():
        root = Path(path).parent
        request.files.read(Path(path), 16384, 'record')
        profile, _ = request.files.read(root / 'profile.json', 16384, 'record')
        hold(list(path_check(root, True)) == item['root']
             and list(path_check(root / 'images', True)) == item['images']
             and list(path_check(root / 'state.sqlite3')[:2]) == item['database']
             and profile['sha256'] == item['profile_sha256']
             and owner_value(registry, item['value']['identity']['actor']) == base['owner'])
    request.source.guard()
    return base, stage


class _AuthorityEvidence(_CheckpointEvidence):
    """Pure before-member proof relationships, deliberately not HistoricalLocators."""
    def __init__(self, request):
        self.request = checked_request(request)
        self.qualified, self.stage = _qualified_base(request)
        action = request.action
        self.registry, self.base = request.registry, request.registry.parent
        self.owner, self.files, self.reader = self.qualified['owner'], action.files, action.reader
        self.cases, self.checkpoints, self.records = {}, {}, {}
        self.value_refs, self.value_ref_bytes = [], 0
        self.members = {}
        for path, item in self.qualified['policies'].items():
            member = _BaseMember(Path(path), item['value'], tuple(item['root']),
                                 tuple(item['images']), tuple(path_check(Path(path).parent / 'state.sqlite3')))
            self.members[member.data['connection_id']] = member
        _METADATA_EVIDENCE.add(self)

    def _registry_value(self): return self.qualified['registry_value']

    def member(self, identity):
        member = self.members.get(identity.get('connection_id'))
        hold(member is not None and member.data == identity)
        self.request.source.guard()
        return member

    def parent(self, operation_path, operation, attestation):
        parents = []
        for member in self.members.values():
            case = self._case(member)
            self._witness(case, operation_path, operation)
            old = operation['plan']['base']['parent']
            transaction = operation['plan']['transaction']
            hold(attestation['registry']['parent_pin'] == old
                 and operation['plan']['base']['registry'] == str(self.registry)
                 and transaction is not None and transaction['registry_parent'] == old)
            self._pin(case, old, self.base, 'registry')
            parents.append(old)
        hold(len(parents) == 2 and all(parent == parents[0] for parent in parents))
        return list(parents[0])

    def journal_parent(self, operation_path, operation):
        plan=operation['plan'];transaction=plan['transaction']
        hold(type(transaction) is dict and plan['base']['registry']==str(self.registry)
             and transaction['registry']==str(self.registry)
             and transaction['registry_parent']==plan['base']['parent']
             and digest(plan['base']['owner'])==digest(self.owner)
             and plan['selected_cids']==list(self.request.pins.selected_cids))
        journal=self.base/'connection-transactions'
        parents=[]
        for member in self.members.values():
            case=self._case(member)
            self._witness(case,operation_path,operation)
            self._pin(case,plan['base']['parent'],self.base,'registry')
            self._pin(case,transaction['journal_parent'],journal)
            parents.append(transaction['journal_parent'])
        hold(len(parents)==2 and canonical(parents[0])==canonical(parents[1]))
        return list(parents[0])

    def finish(self):
        # A request lives only during one source-verification phase, not across writes.
        base, stage = _qualified_base(self.request)
        hold(canonical(base) == canonical(self.qualified) and canonical(stage) == canonical(self.stage))
        for value, raw in self.value_refs:
            hold(raw == (canonical(value) + '\n').encode())
        self.files.verify()
        self.request.files.verify()
        self.request.source.guard()


class _AuthorityParent:
    def __init__(self, request, parent, checksum):
        self.request, self.parent, self.checksum = request, parent, checksum
        self.closed = False


def checked_parent(parent, raw, pins):
    from .own_post_body5_upgrade import BASELINE_ATTESTATION_SHA
    hold(type(parent) is _AuthorityParent and parent in _PARENTS and not parent.closed
         and sha256(raw).hexdigest() == pins.attestation_sha256 == parent.checksum == BASELINE_ATTESTATION_SHA)
    hold(checked_request(parent.request).action is pins._authority_action)
    return list(parent.parent)


def verify_fixed_baseline_attestation(raw, pins):
    """Only post_body5's original compiled v26 recursive position calls this."""
    from . import own_compatible_upgrade as sdk
    from . import own_post_body5_upgrade as post
    request = checked_request(pins._authority_request)
    hold(sha256(raw).hexdigest() == pins.attestation_sha256 == post.BASELINE_ATTESTATION_SHA)
    attestation = sdk.decode_json(raw, sdk.LIMIT, max_nodes=4096)
    hold(attestation['operation_id'] == post.BASELINE['operation_id'])
    if attestation['registry']['parent_pin'] == list(path_check(request.registry.parent, True)):
        return sdk._verify_attestation_body(raw, pins, readonly_history=True, _fixed_view=True)
    operation_path, op_raw, _, att_raw = read_fixed_pair(request, pins)
    hold(att_raw == raw)
    operation = sdk.decode_json(op_raw, sdk.LIMIT, max_nodes=4096)
    verify_historical_anchor(operation,op_raw,operation_path,pins,'POST_BODY5_BASELINE')
    hold(operation['id'] == post.BASELINE['operation_id'] and operation['state'] == 'COMMITTED'
         and operation['attestation_sha256'] == operation['plan']['attestation_sha256'] == post.BASELINE_ATTESTATION_SHA)
    evidence = _AuthorityEvidence(request)
    parent = _AuthorityParent(request, evidence.parent(operation_path, operation, attestation), post.BASELINE_ATTESTATION_SHA)
    _PARENTS.add(parent)
    try:
        result = sdk._verify_attestation_body(raw, pins, readonly_history=True,
                                               _parent=parent, _fixed_view=True)
        evidence.finish()
        return result
    finally:
        parent.closed = True; _PARENTS.discard(parent)


@dataclass(frozen=True,eq=False)
class _JournalPlan:
    """Issued only for a fixed source ancestor; never a current plan permit."""
    request: object
    operation_sha256: str
    parent: tuple
    closed: bool=False


def checked_journal_parent(context,operation,request,proof_reader):
    hold(type(context) is _JournalPlan and context in _JOURNAL_PLANS and not context.closed)
    hold(request is context.request)
    request=checked_request(request)
    hold(proof_reader is request.action.reader)
    request.guard()
    request.action.source.guard()
    hold(digest(operation)==context.operation_sha256)
    return list(context.parent)


def verify_historical_anchor(operation,raw,path,pins,role):
    """Three fixed ancestors of schema4, with all original shape/source checks."""
    from . import own_compatible_upgrade as sdk
    from . import own_body5_upgrade as body5
    from . import own_post_body5_upgrade as post
    roles={'POST_BODY5_BASELINE':post.BASELINE,
           'BODY5_PARENT':{'operation_id':body5.PARENT_ID,'record_sha256':body5.PARENT_SHA},
           'INITIALIZER_BASELINE':body5.INITIALIZER}
    hold(role in roles)
    expected=roles[role]
    reader=sdk._authority_reader(pins)
    # Unrelated legacy callers keep their exact original strict path.
    if (pins._authority_request is None or pins._authority_action is None
            or (role=='INITIALIZER_BASELINE' and operation.get('id')!=expected['operation_id'])):
        return sdk.anchor_shape(operation,proof_reader=reader)
    request=checked_request(pins._authority_request)
    hold(request.action is pins._authority_action
         and pins.authority_source_sha256==body5.SOURCE_SHA
         and tuple(pins.selected_cids)==tuple(sdk.SELECTED_CIDS)
         and Path(path)==sdk.operation_path(expected['operation_id'])
         and type(raw) is bytes and sha256(raw).hexdigest()==expected['record_sha256']
         and operation.get('id')==expected['operation_id']
         and canonical(sdk.decode_json(raw,sdk.LIMIT,max_nodes=4096))==canonical(operation))
    transaction=operation.get('plan',{}).get('transaction')
    if transaction is None:
        return sdk.anchor_shape(operation,proof_reader=reader)
    sdk.pin(transaction['journal_parent'])
    current=list(path_check(request.registry.parent/'connection-transactions',True))
    if canonical(transaction['journal_parent'])==canonical(current):
        return sdk.anchor_shape(operation,proof_reader=reader)
    if request.journal_evidence is None:
        request.journal_evidence=_AuthorityEvidence(request)
    parent=request.journal_evidence.journal_parent(Path(path),operation)
    context=_JournalPlan(request,digest(operation),tuple(parent));_JOURNAL_PLANS.add(context)
    try:
        return sdk.anchor_shape(operation,proof_reader=reader,_journal_plan=context,_journal_request=request)
    finally:
        object.__setattr__(context,'closed',True);_JOURNAL_PLANS.discard(context)
