"""Normal HTML envelopes derived from the official final-content boundary.

These are codec envelopes, never image-count, cache-lifetime or business quotas.
The final HTML (including tags and actual platform image URLs) is checked again.
"""
POLICY = 'WCE_IMPORTED_HTML_V2'
from .html_technical_standard import LIMITS, validate_content
CONTENT_CHARS = LIMITS['content_chars_exclusive'] - 1
CONTENT_BYTES = LIMITS['content_bytes_exclusive'] - 1
ARTICLES = 8
# Every emitted occurrence includes at least this literal markup (even before
# the nonempty official URL and alt/style bytes). It supplies a necessary lower
# bound, not an editorial image quota.
MIN_IMAGE_MARKUP = len('<img alt="" src="">')
IMAGE_POSITIONS = CONTENT_CHARS // MIN_IMAGE_MARKUP
ROLE_POSITIONS = IMAGE_POSITIONS + 1
# Replacing a possibly one-character URL by a bounded internal slot token can
# add at most len('wce-asset:') + 32 characters per occurrence. Derived fields
# retain both source and canonical fragments. UTF8 uses at most four bytes.
FRAGMENT_CHARS = CONTENT_CHARS + IMAGE_POSITIONS * (len('wce-asset:') + 32)
FRAGMENT_BYTES = FRAGMENT_CHARS * 4
# Closed records contain only ASCII slots, MIME enums, hashes and bounded
# references. Compute a conservative maximum from the largest declared record
# shapes instead of choosing an image/cache business quota.
import json as _json

def _record_bytes(value):
    return len(_json.dumps(value,separators=(',',':'),ensure_ascii=False).encode())

_provenance={'slot':'x'*32,'role':'cover','source_sha256':'f'*64,'transport_sha256':'f'*64,
    'source_mime':'image/jpeg','transport_mime':'image/jpeg','source_size':2097152,'transport_size':2097152}
_asset={'asset_ref':'own-asset-'+'f'*32,'role':'cover','declared_type':'image/jpeg',
    'sha256':'f'*64,'size':2097152,'slot':'a'*16+'--'+'b'*32}
# The largest existing upload-history snapshot shape is a lineage replacement.
# All its enum strings/IDs are <=64 ASCII chars; hashes are exactly64. Keep the
# shape bound even though normal HTML does not itself grant such a replacement.
_snapshot={key:'f'*64 for key in ('source','replacement_id','case_id','original_step_id','original_step_sha',
    'original_intent_digest','original_result_digest','intent_digest','result_digest','proof_sha256',
    'approval_digest','batch_id','batch_digest','unrelated_context_sha','unrelated_receipt_sha')}
RECORD_BYTES=sum(_record_bytes(x) for x in (_provenance,_asset,_snapshot))
# Fixed header/metadata: seven128-char binding IDs; eight64-char digests/IDs;
# official title/author/digest character maxima; source URL's existing1024-byte
# bound; crop/editorial/defaults/delegation closed fields and their key spelling.
# Six bytes per scalar character covers JSON escaping as well as UTF8.
HEADER_BYTES=6*(7*128+8*64+LIMITS['title_chars']+LIMITS['author_chars']+LIMITS['digest_chars']+LIMITS['source_url_bytes']+2*256+2048)
ENVELOPE_BYTES=ARTICLES*(2*FRAGMENT_BYTES+ROLE_POSITIONS*RECORD_BYTES+HEADER_BYTES)
# Provenance <=19 tree nodes, asset <=13, largest snapshot <=31;128 conservatively
# covers all of them and their containing array nodes;1024 covers fixed metadata.
ENVELOPE_NODES=ARTICLES*(ROLE_POSITIONS*128+1024)


def final_content(value):
    # Preserve the legacy public error code; the shared rule carries precise
    # bounded diagnostics for local review without changing tool wire schemas.
    from .contracts import WCEError
    try:
        return validate_content(value)
    except WCEError as error:
        compatible = WCEError('OWN_CONSERVATIVE_NEWS_LIMIT')
        compatible.technical_rule = error.technical_rule
        raise compatible from error
