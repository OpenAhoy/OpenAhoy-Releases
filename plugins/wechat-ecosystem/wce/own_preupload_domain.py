"""Separate short Operator image service using the normal AccountService.

No Broker, root connection socket, Group grant or arbitrary SDK method routing.
Pinned source/QA/resume qualification is required before construction and on
requests; the ordinary SDK retains every final authorization and write gate.
"""
from .contracts import WCEError
from . import own_preupload_protocol as protocol
from .own_connection_policy import load_policy
from .own_connection_broker import AccountService
from .own_business_temporal import deadline_scope
from .own_fd_domain import regular_fd_domain
from .publication_lock import draft_writer
from .own_bootstrap_security import acquire_pending


class PreuploadSessionService:
    def __init__(self, entry):
        from . import own_preupload_entry as entry_runtime
        self.entry = entry
        view = entry_runtime.consume_service_construction(entry, self)
        self.deadline = view.deadline
        self.policy = load_policy(view.policy_path)
        self.active_request = None
        self.constructing = True
        self.core = self.workflow = None
        self.qa = None
        self.closed = False
        # This concrete input owner must authenticate current QA, the exact
        # selected declaration and the original stopped-phase resume. It does
        # not accept a caller-supplied safe flag or a plain JSON grant.
        self.inputs = None
        try:
            from .own_preupload_inputs import PreuploadInputs
            self.inputs = PreuploadInputs.from_fixed_entry(entry, self.policy)
            self.guard()
            with deadline_scope(self.deadline), regular_fd_domain(deadline=self.deadline):
                with draft_writer(self.policy.root, self.policy.data['appid']):
                    self.guard()
                    core = AccountService(self.policy)  # Actual normal constructor.
                    self.guard()
            self.core, self.workflow = core, core.workflow
            entry_runtime.bind_service(entry, self, core)
            self.constructing = False
            from .own_preupload_qa import _issue_preupload_qa
            self.qa = _issue_preupload_qa(entry,self)
            core.set_guard(self.guard)
            core.tokens.acquire = self.bounded_acquire
            self.guard()
        except BaseException as original:
            self.close(original=original)
            raise

    def guard(self):
        from . import own_preupload_entry as entry_runtime
        if self.closed:
            raise WCEError('PREUPLOAD_SESSION_CLOSED')
        entry_runtime.require_fixed_entry(self.entry, service=self)
        self.policy.check()
        self.inputs.check_current(self)
        if not self.constructing:
            entry_runtime.require_service_entry(self.entry, self, self.core)
        if self.qa is not None:
            from .own_preupload_qa import require_preupload_qa
            require_preupload_qa(self.qa,entry=self.entry,service=self)
        if self.active_request is not None:
            _, method, arguments = self.active_request
            entry_runtime.require_service_request(self.entry, self, self.core, method, arguments)
        # Never call core.guard here: its original implementation calls us.

    def bounded_acquire(self, appid, secret):
        # The trusted TokenCache invokes this internally after Keychain wait.
        # No credential is retained, returned, logged or added to an artifact.
        self.guard()
        if self.active_request is None or self.active_request[1] != protocol.EXECUTE:
            raise WCEError('PREUPLOAD_TOKEN_REQUEST_HOLD')
        if appid != self.policy.data['appid']:
            raise WCEError('PREUPLOAD_TOKEN_SCOPE_HOLD')
        result = acquire_pending(appid, secret, absolute_deadline=self.deadline)
        self.guard()
        return result

    def dispatch_next(self):
        from . import own_preupload_entry as entry_runtime
        self.guard()
        sequence, method, arguments = entry_runtime.receive_service_request(self.entry, self, self.core)
        self.active_request = (sequence, method, arguments)
        try:
            self.guard()
            member_id = arguments['member_id']
            if method == protocol.ACCEPT:
                value = self.inputs.accept_selected_in_service(self, member_id)
            elif method == protocol.STATUS:
                value = self.inputs.original_slot_status(self, member_id, arguments['slot'])
            elif method == protocol.EXECUTE:
                value = self.inputs.execute_original_slot(self, member_id, arguments['slot'])
            else:
                raise WCEError('PREUPLOAD_TRANSPORT_SCOPE_HOLD')
            self.guard()
            entry_runtime.respond_service_request(self.entry, self, self.core, value=value)
            return True
        except WCEError as error:
            # Any rejected or unknown operation ends this unit. No automatic
            # next partition, changed key, reconcile, or replacement dispatch.
            entry_runtime.respond_service_request(self.entry, self, self.core, error=error.code)
            return False
        finally:
            self.active_request = None

    def close(self, *, original=None):
        if not self.closed:
            self.closed = True
            from .own_preupload_qa import revoke_preupload_qa
            callbacks = [lambda:revoke_preupload_qa(self.qa,entry=self.entry,service=self)]
            if self.inputs is not None:
                callbacks.append(lambda:self.inputs.close(original=original))
            if self.core is not None:
                callbacks.append(self.core.tokens.clear)
            from .draft_group_pin_resources import close_all
            close_all(callbacks, original)


def serve_in_fixed_entry(entry):
    from . import own_preupload_entry as entry_runtime
    try:
        service = PreuploadSessionService(entry)
    except BaseException as original:
        # Send only a bounded fixed control code, never exception text, paths,
        # SQL, article bytes or secrets. A failed local constructor does not
        # become an ambiguous business response to a not-yet-sent RPC.
        code=original.code if isinstance(original,WCEError) else 'PREUPLOAD_INITIALIZATION_FAILED'
        try:entry_runtime.send_initialization(entry,error=code)
        except BaseException:pass  # Preserve the original failure, no retry.
        raise
    try:
        entry_runtime.send_initialization(entry,service)
        while service.dispatch_next():
            pass
    except EOFError:
        service.close()
    except BaseException as original:
        service.close(original=original)
        raise
    else:
        service.close()
