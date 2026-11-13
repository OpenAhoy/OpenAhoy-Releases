"""A persistent, local mock transport. No socket, HTTP or live API exists here."""
import json
from threading import Lock
from uuid import uuid4

from .contracts import PublicationState, Receipt, RejectedOperation, Secret, Status, UncertainResult
from .storage import Database

MOCK_SCHEMA = """
CREATE TABLE IF NOT EXISTS objects (
 ref TEXT PRIMARY KEY, connection TEXT NOT NULL, kind TEXT NOT NULL,
 payload TEXT NOT NULL, state TEXT NOT NULL, polls INTEGER NOT NULL DEFAULT 0);
"""


class MockOfficialAccountAdapter:
    mode = "mock"
    workflow_mode = "offline"

    def __init__(self, path):
        self.db = Database(path, MOCK_SCHEMA, 0x5743454D)
        self._faults: dict[str, str] = {}
        self._lock = Lock()

    def fail_next(self, kind: str, fault: str):
        """Test injection, absent from the tool boundary."""
        with self._lock:
            self._faults[kind] = fault

    def _fault(self, kind):
        with self._lock:
            return self._faults.pop(kind, None)

    def _write(self, connection, kind, payload, credential):
        fault = self._fault(kind)
        if fault == "reject":
            raise RejectedOperation("MOCK_REJECTED")
        if fault == "secret_error":
            raise RuntimeError(credential.reveal_for_adapter())
        ref = "mock-" + kind + "-" + uuid4().hex
        state = "PROCESSING" if kind == "publication" else "SUCCEEDED"
        with self.db.transaction(write=True) as db:
            db.execute("INSERT INTO objects(ref,connection,kind,payload,state) VALUES(?,?,?,?,?)",
                       (ref, connection, kind, json.dumps(payload), state))
        if fault == "lose_with_ref":
            raise UncertainResult(ref)
        if fault == "lose_without_ref":
            raise UncertainResult()
        return Receipt(ref)

    def add_material(self, connection_id: str, digest: str, credential: Secret) -> Receipt:
        return self._write(connection_id, "material", {"digest": digest}, credential)

    def save_draft(self, connection_id: str, content: dict, credential: Secret) -> Receipt:
        return self._write(connection_id, "draft", content, credential)

    def bind_draft(self, context):
        # Default offline behavior uses the existing mock contract unchanged.
        return self

    def _object(self, db, connection_id, platform_ref, kind):
        row = db.execute("SELECT * FROM objects WHERE ref=? AND connection=? AND kind=?",
                         (platform_ref, connection_id, kind)).fetchone()
        if row is None:
            raise RejectedOperation("MOCK_OBJECT_NOT_FOUND")
        return row

    def read_draft(self, connection_id: str, platform_ref: str, credential: Secret) -> dict:
        with self.db.transaction() as db:
            row = self._object(db, connection_id, platform_ref, "draft")
            return json.loads(row["payload"])

    def preview(self, connection_id: str, draft_ref: str, targets: tuple[str, ...], credential: Secret) -> Receipt:
        with self.db.transaction() as db:
            self._object(db, connection_id, draft_ref, "draft")
        return self._write(connection_id, "preview", {"draft_ref": draft_ref, "targets": targets}, credential)

    def submit_publication(self, connection_id: str, draft_ref: str, credential: Secret) -> Receipt:
        with self.db.transaction() as db:
            self._object(db, connection_id, draft_ref, "draft")
        return self._write(connection_id, "publication", {"draft_ref": draft_ref}, credential)

    def publication_status(self, connection_id: str, platform_ref: str, credential: Secret) -> Status:
        fault = self._fault("status")
        if fault == "timeout":
            raise TimeoutError()
        if fault == "malformed":
            return Status("unverified-platform-state")
        with self.db.transaction(write=True) as db:
            row = self._object(db, connection_id, platform_ref, "publication")
            state = row["state"]
            if state == "PROCESSING" and row["polls"] > 0:
                state = "SUCCEEDED"
            db.execute("UPDATE objects SET polls=polls+1,state=? WHERE ref=?", (state, platform_ref))
        return Status(PublicationState(state))

    def count(self, kind: str) -> int:
        with self.db.transaction() as db:
            return db.execute("SELECT count(*) FROM objects WHERE kind=?", (kind,)).fetchone()[0]

    def set_publication_state(self, platform_ref: str, state: PublicationState):
        with self.db.transaction(write=True) as db:
            db.execute("UPDATE objects SET state=? WHERE ref=? AND kind='publication'", (state.value, platform_ref))
