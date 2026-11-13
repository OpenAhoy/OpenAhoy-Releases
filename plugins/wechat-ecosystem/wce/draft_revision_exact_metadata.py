"""Pinned author-supplied revision fields; no registration or permission.

The original immutable save proof and fresh platform snapshot are validated by
other components.  This adapter never fills an absent author or permits a
change outside the explicitly reviewed title/content/digest projection.
"""
from copy import deepcopy
from hashlib import sha256
from .contracts import WCEError
from .publication_contract import strict_json

PROFILE='FOUR_DRAFT_EXACT_METADATA_V1'

def hold():
    raise WCEError('DRAFT_REVISION_EXACT_METADATA_HOLD')

def derive(raw, expected_sha, original_projection, revised_projection):
    """Bind title/digest differences to the exact pinned metadata file bytes.

    Inputs are private evidence produced by trusted acquisition, not MCP
    arguments. The returned object is evidence only, never authorization.
    """
    if (type(raw) is not bytes or type(expected_sha) is not str or len(expected_sha)!=64
            or any(c not in '0123456789abcdef' for c in expected_sha)
            or sha256(raw).hexdigest()!=expected_sha
            or type(original_projection) is not dict or type(revised_projection) is not dict):hold()
    try:value=strict_json(raw,maximum=131072)
    except Exception:hold()
    if type(value) is not dict or not {'title','digest','author'}<=set(value):hold()
    title,digest,author=(value[k] for k in ('title','digest','author'))
    if (type(title) is not str or not title.strip() or len(title)>32 or len(title.encode())>128
            or type(digest) is not str or len(digest)>120 or len(digest.encode())>480
            or type(author) is not str or len(author)>16 or len(author.encode())>64):hold()
    # Only known writable keys participate. Metadata author and all other
    # fields are evidence, not permission to overwrite the remote baseline.
    required={'title','content','digest'}
    if not required<=set(original_projection) or not required<=set(revised_projection):hold()
    if revised_projection['title']!=title or revised_projection['digest']!=digest:hold()
    if any(type(revised_projection[k]) is not str for k in required):hold()
    changed={k:deepcopy(revised_projection[k]) for k in ('title','content','digest')
        if revised_projection[k]!=original_projection[k]}
    if not changed:hold()
    return {'profile':PROFILE,'metadata_sha256':expected_sha,'changes':changed}
