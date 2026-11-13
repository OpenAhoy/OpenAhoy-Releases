"""Private continuation bridge for original inventory-authorized intents.

The host supplies the actual existing Authorization and policy guard. This
module never manufactures a slot source or grants publication authority.
It is not registered as an MCP tool.
"""
from contextlib import contextmanager
from copy import deepcopy
from .contracts import WCEError
from .single_publication_source import is_authority
from .current_publication_store import Store
from .current_publication_continuation import ContinuationIndex
from .publication_contract import binding


def _hold():
    raise WCEError('CURRENT_PUBLICATION_CONTINUATION_AUTHORIZATION_REQUIRED')


class LegacyContinuationBridge:
    def __init__(self, store, guard, authority):
        if type(store) is not Store or not is_authority(authority) or not callable(guard):
            _hold()
        self.old, self.guard, self.authority = store, guard, authority
        self.expected_binding = binding(store.policy.data)
        self.index = ContinuationIndex(store)

    def _checked(self, action, row):
        if binding(self.old.policy.data) != self.expected_binding:
            _hold()
        self.guard()
        if action == 'claim':
            _, original = self.old.verify_claim(row['intent_handle'],self.guard,self.authority)
            # Preserve the original immutable target and source; quota and
            # continuation state are separately validated by the host.
            from .current_publication_store import MUTABLE_TARGET_FIELDS
            if ({k:v for k,v in original.items() if k not in MUTABLE_TARGET_FIELDS}
                    != {k:v for k,v in row.items() if k not in MUTABLE_TARGET_FIELDS}):
                _hold()
        elif action == 'send':
            _, current = self.old.target(row['intent_handle'])
            if (current != row or current.get('state') != 'SUBMIT_CLAIMED'
                    or current.get('submit_count') != 1):
                _hold()
            self.old._authority(self.authority,self.guard,current['batch_source_sha'])
            self.old.guard_legacy(current['reference'],current.get('content_claims',[]),
                authority=self.authority,guard=self.guard,source_sha=current['batch_source_sha'],
                successor_handle=current['intent_handle'] if current.get('revision_successor_of') else None)
        elif action not in {'read','recover','query','query_recover'}:
            _hold()
        self.guard()
        return True

    def _conflicts(self, action, row):
        self.guard()
        if action == 'claim':
            self.old.guard_legacy(row['reference'],row.get('content_claims',[]),
                authority=self.authority,guard=self.guard,source_sha=row['batch_source_sha'],
                successor_handle=row['intent_handle'] if row.get('revision_successor_of') else None)
        elif action == 'task':
            from .publication_wire import TaskID
            task = TaskID(**row['task'])
            if self.old._legacy_task_conflict(task):
                _hold()
        else:
            _hold()
        self.guard()
        return True

    @contextmanager
    def session(self):
        with self.index.session(self._checked,self._conflicts) as selected:
            yield selected


def local_status(policy, registry, handle):
    """Read previously recorded local status without renewed submit authority.

    This does not recover a receipt, acquire a token, or perform a query.
    It uses the existing historical identity guard and never advances an anchor.
    """
    from .draft_revision_guard import historical_identity_guard
    from .current_publication_store import public_target
    from .current_publication_continuation import _ContinuationSession
    guard = historical_identity_guard(policy)
    old = Store(policy, registry, guard=guard)
    index = ContinuationIndex(old)
    with index._db(readonly=True,historical=True) as (db,identity):
        from .current_publication_existing_task import readonly_head
        db.execute('BEGIN')
        head,ahead = readonly_head(index,db,identity)
        index._check_old_index(db,index._meta(db,identity))
        selected = _ContinuationSession(index,db,identity,None,None)
        try:
            row = selected._row(handle)
            result = public_target(row)
            if ahead:
                result['local_anchor_state'] = 'COMMITTED_CHAIN_PENDING_ANCHOR_CONFIRMATION'
            origin = db.execute('SELECT origin FROM target_overlays WHERE handle=?',(handle,)).fetchone()
            if origin is not None and origin['origin'] == 'SLOT':
                result['quality_source'] = 'PRODUCER_QA_UNDER_STANDING_SLOT_RULE'
            if row['state'] in {'SUBMIT_CLAIMED','UNKNOWN'}:
                receipts = db.execute("SELECT * FROM return_receipts WHERE handle=? AND method='freepublish.submit'",(handle,)).fetchall()
                if receipts:
                    _, task = selected._receipt_task(handle,row,receipts)
                    result['original_receipt_state'] = 'ORIGINAL_TASK_STAGED_LOCAL_ONLY' if task is not None else 'ORIGINAL_RECEIPT_UNDETERMINED'
                    result['original_task_observed'] = task is not None
                else:
                    value = old._read_legacy()
                    original = value['targets'].get(handle)
                    if original is not None and original.get('state') in {'SUBMIT_CLAIMED','UNKNOWN'}:
                        staged = old._staged_submit(value,original,guard,check_conflict=False)
                        result['original_receipt_state'] = staged['state']
                        result['original_task_observed'] = staged.get('task') is not None
                    else:
                        result['original_receipt_state'] = 'ORIGINAL_RECEIPT_NOT_FOUND'
                        result['original_task_observed'] = False
            guard()
            if readonly_head(index,db,identity)[0] != head:
                _hold()
            db.execute('COMMIT')
            return result
        finally:
            selected.active = False


class _LegacyProxy:
    def __init__(self, facade):
        self.facade = facade

    def __getattr__(self, name):
        return getattr(self.facade.old.legacy, name)

    @contextmanager
    def dispatch_lock(self):
        if self.facade._session is not None:
            _hold()
        with self.facade.bridge.session() as session:
            self.facade._session = session
            try:
                yield
            finally:
                self.facade._session = None


class LegacyStoreFacade:
    """Original C inventory compatibility under the existing service contract.

    Only old frozen inventory handles are supported here. New Slot source is a
    separate host provider; this facade never interprets a caller source/path.
    """
    def __init__(self, store, guard, authority):
        self.old, self.guard, self.authority = store, guard, authority
        self.bridge = LegacyContinuationBridge(store,guard,authority)
        self.legacy = _LegacyProxy(self)
        self._session = None

    def __getattr__(self, name):
        return getattr(self.old, name)

    def _selected(self):
        if self._session is None:
            _hold()
        return self._session

    def _value(self):
        # The original baseline is bounded by the old schema. New Slot rows
        # are intentionally not aggregated into this compatibility view.
        value = self.old.read()
        selected = self._selected()
        for handle in value['targets']:
            value['targets'][handle] = selected.target(handle)
        return value

    def initialize_locked(self):
        return self._value()

    def target(self, handle):
        value = self._value()
        if handle not in value['targets']:
            _hold()
        return value,value['targets'][handle]

    def prepare(self, inventory, targets, authority, guard):
        from .service import digest
        self.old._authority(authority,guard)
        value = self._value()
        batch = value['batches'].get(authority.source_sha)
        if batch is None:
            return self.old.prepare(inventory, targets, authority, guard)
        if (batch['inventory_handle'] != inventory.get('inventory_handle')
                or batch['inventory_sha256'] != digest(inventory)):
            _hold()
        by_reference = {row['reference']:row for row in targets}
        for handle in batch['intent_handles']:
            row = value['targets'][handle]
            if row.get('revision_successor_of'):
                continue
            supplied = by_reference.get(row['reference'])
            if supplied is None or digest({key:row.get(key) for key in supplied}) != digest(supplied):
                _hold()
        self.old._authority(authority,guard,authority.source_sha)
        return value

    def claim(self, handle, guard, quota, authority):
        if authority is not self.authority:
            _hold()
        guard()
        return self._selected().claim(handle,quota=quota)

    def reply_ticket(self, handle, method, request, token, guard):
        guard()
        if method == 'freepublish.submit':
            return self._selected().submit_ticket(handle,request,token)
        if method == 'freepublish.get':
            return self._selected().query_ticket(handle,request,token)
        _hold()

    def record_reply(self, handle, method, request, response, token, guard, *, ticket):
        session = self._selected()
        if method == 'freepublish.submit':
            session.stage_submit_reply(ticket,response,token)
            result = session.adopt_staged_submit(handle)
        elif method == 'freepublish.get':
            session.stage_query_reply(ticket,response,token)
            result = session.apply_staged_query(handle)
        else:
            _hold()
        guard()
        return result

    def staged_submit(self, handle, guard):
        session = self._selected()
        row = session.target(handle)
        receipts = session.db.execute("SELECT * FROM return_receipts WHERE handle=? AND method='freepublish.submit'",(handle,)).fetchall()
        if receipts:
            receipt_sha,task = session._receipt_task(handle,row,receipts)
            return {'state':'ORIGINAL_TASK_STAGED_LOCAL_ONLY' if task is not None else 'ORIGINAL_RECEIPT_UNDETERMINED',
                    'receipt_sha256':receipt_sha,'task':task}
        value = self.old._read_legacy()
        original = value['targets'].get(handle)
        if original is not None and original.get('state') in {'SUBMIT_CLAIMED','UNKNOWN'}:
            return self.old._staged_submit(value,original,guard,check_conflict=True)
        return {'state':'ORIGINAL_RECEIPT_NOT_FOUND'}

    def record_unknown(self, handle, guard):
        guard()
        return self._selected().mark_submit_unknown(handle)

    def record_query_claim(self, handle, guard):
        guard()
        return self._selected().claim_query(handle)

    def record_query_unknown(self, handle, guard):
        guard()
        return self._selected().mark_query_unknown(handle)

    def adopt_staged_submit(self, handle, authority, guard):
        if authority is not self.authority:
            _hold()
        guard()
        session = self._selected()
        result = session.adopt_staged_submit(handle)
        if result.get('state') == 'ORIGINAL_RECEIPT_NOT_FOUND':
            result = session.adopt_old_staged_submit(handle)
        guard()
        return result
