"""Dispatch immutable inventory readers by their actual typed profile.

Legacy full-pagination readers keep their original strict contract.  A saved
request snapshot has its own reader and cannot be consumed by an old authority.
"""
from pathlib import Path
from . import current_draft_inventory as legacy
from . import requested_draft_inventory as requested
from .publication_store import read_file
from .publication_contract import fail


def is_requested(checkpoint):
    return type(checkpoint) is dict and checkpoint.get('profile') == requested.PROFILE


def load_complete(policy, handle, guard):
    if type(handle) is not str or legacy.HANDLE.fullmatch(handle) is None:
        fail('CURRENT_DRAFT_CURSOR_INVALID')
    value = read_file(policy.root / 'current-draft-publication' / (handle + '.json'), legacy.INDEX_MAX)
    if is_requested(value):
        return requested.load_complete(policy, handle, guard)
    return legacy.load_complete(policy, handle, guard)


def frozen_targets(policy, checkpoint, guard):
    reader = requested if is_requested(checkpoint) else legacy
    yield from reader.frozen_targets(policy, checkpoint, guard)


def _read_page(directory, handle, number, expected_sha, binding_sha, guard):
    directory = Path(directory)
    # The immutable checkpoint selects a reader; no refusal is retried under
    # the other format.  Each reader still checks the expected page SHA.
    value = read_file(directory / (handle + '.json'), legacy.INDEX_MAX)
    reader = requested.read_page if is_requested(value) else legacy._read_page
    return reader(directory, handle, number, expected_sha, binding_sha, guard)


def complete_for(authority, checkpoint):
    from .saved_groups_publication_source import is_saved_groups
    if is_requested(checkpoint):
        return requested.matches_source(authority, checkpoint)
    return (not is_saved_groups(authority)
        and checkpoint.get('coverage') == 'COMPLETE_OBSERVED_PAGINATION'
        and checkpoint.get('observed_groups') == checkpoint.get('total_groups'))
