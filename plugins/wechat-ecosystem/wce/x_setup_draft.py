"""One-use public app details passed from the setup chat to its initiating panel."""
from secrets import token_hex
from time import monotonic

from .contracts import WCEError
from .x_application import CLIENT_ID
from .x_platform import valid_application_name, valid_client_id


class SetupDrafts:
    def __init__(self, clock=monotonic):
        self.clock = clock
        self.rows = {}

    def _prune(self):
        now = self.clock()
        for key in tuple(self.rows):
            if self.rows[key]['expires'] <= now:
                del self.rows[key]

    def begin(self, connection_id):
        self._prune()
        panel_key = token_hex(24)
        handoff = token_hex(24)
        self.rows[panel_key] = {'handoff': handoff, 'expires': self.clock() + 600,
                                'connection_id': connection_id, 'draft': None}
        return {'panel_key': panel_key, 'handoff': handoff, 'expires_in': 600}

    def submit(self, handoff, user_id, application_name, client_id):
        self._prune()
        row = next((row for row in self.rows.values() if row['handoff'] == handoff), None)
        if row is None or row['draft'] is not None:
            raise WCEError('X_SETUP_HANDOFF_UNAVAILABLE')
        if row['connection_id'] and row['connection_id'] != 'x-' + user_id:
            raise WCEError('X_AUTHORIZATION_ACCOUNT_MISMATCH')
        if not valid_application_name(application_name) or len(application_name) > 32:
            raise WCEError('X_APPLICATION_NAME_INVALID')
        if not valid_client_id(client_id) or client_id == CLIENT_ID:
            raise WCEError('X_OWN_CLIENT_ID_REQUIRED')
        row['draft'] = {'user_id': user_id, 'application_name': application_name, 'client_id': client_id}
        return {'state': 'DRAFT_READY'}

    def read(self, panel_key, connection_id):
        self._prune()
        row = self.rows.get(panel_key)
        if row is None or row['connection_id'] != connection_id:
            return {'state': 'UNAVAILABLE'}
        if row['draft'] is None:
            return {'state': 'WAITING'}
        del self.rows[panel_key]
        return {'state': 'READY', 'draft': row['draft']}

    def cancel(self, panel_key):
        self.rows.pop(panel_key, None)
        return {'state': 'CANCELLED'}
