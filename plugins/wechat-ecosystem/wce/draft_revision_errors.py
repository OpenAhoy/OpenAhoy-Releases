"""Closed source diagnostics; no source text or arbitrary exception code escapes."""
from .contracts import WCEError
from .draft_revision_native_source import SourceHold


_SOURCE_CODES = {
    'REVISION_SOURCE_REVIEW_HOLD': 'DRAFT_REVISION_SOURCE_REVIEW_HOLD',
    'REVISION_SOURCE_APPENDED_REOBSERVE': 'DRAFT_REVISION_SOURCE_APPENDED_REOBSERVE',
    'REVISION_SOURCE_CHANGED_REOBSERVE': 'DRAFT_REVISION_SOURCE_CHANGED_REOBSERVE',
    'REVISION_NEW_HUMAN_SOURCE_REQUIRES_REVIEW': 'DRAFT_REVISION_NEW_HUMAN_SOURCE_REQUIRES_REVIEW',
    'HOST_SQLITE_CONNECTION_IDENTITY_UNPROVEN': 'DRAFT_REVISION_SOURCE_INDEX_IDENTITY_HOLD',
}
SOURCE_OUTCOMES = frozenset(_SOURCE_CODES.values()) | {'DRAFT_REVISION_SOURCE_HOLD'}


def source_failure(error):
    code = error.code if type(error) is SourceHold else None
    safe = _SOURCE_CODES.get(code) if type(code) is str else None
    return WCEError(safe or 'DRAFT_REVISION_SOURCE_HOLD')
