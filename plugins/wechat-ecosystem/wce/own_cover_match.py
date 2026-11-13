"""Shared bounded official-cover observation; no authority, journal or CAS."""
import math
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from .contracts import WCEError
from .local_preparation import image_check, sha
from .own_png import decode_png
from .prepared_draft_fixture import decode_json
from .service import digest
from . import upload_wire as upload

def match_cover(read, guard, report, failed, read_stop, row, intent, original,
                pixel, synthetic, secret, prepare_read=None, executor_factory=ThreadPoolExecutor):
    # Validation policy is shared with the legacy host; authority is supplied
    # only by its caller. No URLs or selectors are accepted from the model.
    from .own_reconcile import MAX_MATERIALS, MAX_READ_WORKERS, PAGE_SIZE, MAX_CANDIDATES, ITEM_FIELDS, item_issue
    from .own_auth import READ_APIS
    def prepared(action, payload):
        return prepare_read(action, payload) if prepare_read else lambda: read(action, payload)

    def page(offset):
        return prepared(READ_APIS[0], {'type': 'image', 'offset': offset, 'count': PAGE_SIZE})()

    def drain(pool, pending, primary_error):
        """Retain the caller's serial ownership until actual worker completion.

        Interrupting Thread.join can make its bookkeeping unreliable. Worker
        finally-events, or cancellation before start, provide the second barrier.
        """
        interrupted = None
        while True:
            try:
                pool.shutdown(wait=True, cancel_futures=True)
                for future, done in pending:
                    while not future.cancelled() and not done.wait(.05):
                        pass
                break
            except BaseException as error:
                interrupted = interrupted or error
                try:
                    read_stop.set()
                    failed(primary_error or error)
                except BaseException:
                    pass
                # Never release account ownership while an admitted read worker
                # may still run. All transport calls retain their I/O timeout.
        if interrupted is not None and primary_error is None:
            raise interrupted

    def validate_page(raw, offset, expected):
        from .own_run_outcome import field_type
        def invalid(reason, **counts):
            error = WCEError('OWN_RECONCILE_INVALID_LIST')
            report({'reason': reason, 'offset': offset,
                'limit': MAX_MATERIALS} | counts)
            raise error
        try:
            value = decode_json(raw, 65536)
        except Exception:
            report({'reason': 'LIST_JSON', 'offset': offset,
                'limit': MAX_MATERIALS})
            raise
        if type(value) is not dict:
            invalid('LIST_OBJECT', field_type=field_type(value))
        if upload.contains_secret(value, secret):
            invalid('LIST_REFLECTION')
        if type(value.get('errcode', 0)) is not int or value.get('errcode', 0) != 0:
            error = WCEError('OWN_RECONCILE_API_REJECTED')
            try:
                report({'reason': 'LIST_API_REJECTED', 'offset': offset,
                    'wechat_error_code': value.get('errcode', 0),
                    'field_type': field_type(value.get('errcode', 0))})
            except BaseException:
                pass  # Even diagnostic construction cannot replace this refusal.
            raise error
        if set(value) - {'total_count', 'item_count', 'item', 'errcode', 'errmsg'}:
            invalid('LIST_KEYS', extra_key_count=len(set(value) - {'total_count', 'item_count', 'item', 'errcode', 'errmsg'}))
        total, count, page = value.get('total_count'), value.get('item_count'), value.get('item')
        def incomplete(reason):
            error = WCEError('OWN_RECONCILE_INCOMPLETE_LIST')
            report({'reason': reason, 'offset': offset,
                'total': total, 'item_count': count,
                'page_length': len(page) if type(page) is list else None, 'limit': MAX_MATERIALS})
            raise error
        if type(total) is not int or type(count) is not int or type(page) is not list:
            incomplete('METADATA_SHAPE')
        if not 0 <= total <= MAX_MATERIALS:
            incomplete('TOTAL_BOUND')
        if count != len(page):
            incomplete('PAGE_LENGTH')
        if count != min(PAGE_SIZE, max(0, total - offset)):
            incomplete('PAGE_SHORT')
        if expected is not None and expected != total:
            incomplete('TOTAL_DRIFT')
        projected = []
        for index, item in enumerate(page):
            issue = item_issue(item, synthetic)
            if issue is not None:
                reason, counts = issue
                invalid(reason, total=total, item_count=count, page_length=len(page), item_index=index, **counts)
            # The full response, including extensions, has already passed the
            # bounded decoder and secret checks. Only validated identity fields
            # participate in recovery; extension values never reach its proof.
            projected.append({field: item[field] for field in ITEM_FIELDS})
        return total, projected
    def scan():
        total, items = validate_page(page(0), 0, None)
        # Only one small batch is scheduled at a time. Complete scans do not
        # assume Tencent sorts by update time, or stop after finding a match.
        if total > PAGE_SIZE:
            pool = executor_factory(max_workers=MAX_READ_WORKERS, thread_name_prefix='wce-cover-read')
            primary_error, futures, pending = None, {}, []
            try:
                for start in range(PAGE_SIZE, total, PAGE_SIZE * MAX_READ_WORKERS):
                    guard()
                    offsets = range(start, min(total, start + PAGE_SIZE * MAX_READ_WORKERS), PAGE_SIZE)
                    futures = {}
                    for offset in offsets:
                        guard()
                        invoke = prepared(READ_APIS[0],
                            {'type': 'image', 'offset': offset, 'count': PAGE_SIZE})
                        done = threading.Event()
                        def worker(invoke=invoke, done=done):
                            try:
                                return invoke()
                            finally:
                                done.set()
                        future = pool.submit(worker)
                        pending.append((future, done))
                        futures[future] = offset
                    pages = {}
                    for future in as_completed(futures):
                        offset = futures[future]
                        _, pages[offset] = validate_page(future.result(), offset, total)
                    for offset in sorted(pages):
                        items.extend(pages[offset])
            except BaseException as error:
                primary_error = error
                try:
                    read_stop.set()
                except BaseException:
                    failed(primary_error)
                for future in futures:
                    try:
                        future.cancel()
                    except BaseException:
                        failed(primary_error)
                raise
            finally:
                drain(pool, pending, primary_error)
        guard()
        if len(items) != total or len({i['media_id'] for i in items}) != total:
            error = WCEError('OWN_RECONCILE_INCOMPLETE_LIST')
            report({'reason': 'DUPLICATE_IDS', 'offset': 0,
                'total': total, 'item_count': len(items), 'page_length': len(items), 'limit': MAX_MATERIALS})
            raise error
        return sorted(items, key=lambda i: i['media_id'])

    original_raster = decode_png(original, guard) if pixel else None
    first = scan()
    # A deliberately narrow local association policy, not an assertion about
    # Tencent clock synchronization or list ordering. A miss remains UNKNOWN.
    candidates = [i for i in first if i['name'] == 'cover.png'
        and math.floor(row['created']) - 2 <= i['update_time'] <= math.ceil(row['created']) + 30]
    if not 0 < len(candidates) <= MAX_CANDIDATES:
        raise WCEError('OWN_RECONCILE_NO_UNIQUE_CANDIDATE')
    matches = []
    completed_reads = size_matches = png_signatures = jpeg_signatures = byte_matches = 0
    matched_raw = None
    def image(media_id):
        data = prepared(READ_APIS[1], {'media_id': media_id})()
        mime = 'image/png' if data.startswith(b'\x89PNG\r\n\x1a\n') else 'image/jpeg'
        try:
            image_check(data, mime)
        except Exception:
            raise WCEError('OWN_RECONCILE_MEDIA_UNDETERMINED') from None
        return data
    for item in candidates:
        data = image(item['media_id'])
        completed_reads += 1
        if data.startswith(b'\x89PNG\r\n\x1a\n'):
            png_signatures += 1
        else:
            jpeg_signatures += 1
        same_size = len(data) == len(original)
        size_matches += int(same_size)
        same_bytes = same_size and sha(data) == intent['asset']['sha256']
        byte_matches += int(same_bytes)
        matches_policy = decode_png(data, guard) == original_raster if pixel else same_bytes
        if matches_policy:
            matches.append(item)
            matched_raw = data
    if len(matches) != 1:
        error = WCEError('OWN_RECONCILE_NO_UNIQUE_MATCH')
        # Only completed reads produce these counts. Signatures do not prove
        # decoded pixels or a platform transformation; bytes remain the gate.
        if pixel:
            report({'reason': 'PIXEL_MATCH_COUNTS', 'candidate_count': len(candidates),
                'completed_reads': completed_reads, 'decoded_png_count': completed_reads,
                'pixel_matches': len(matches), 'byte_matches': byte_matches})
        else:
            report({'reason': 'IMAGE_MATCH_COUNTS', 'candidate_count': len(candidates),
                'completed_reads': completed_reads, 'size_matches': size_matches, 'exact_matches': len(matches),
                'png_signature_count': png_signatures, 'jpeg_signature_count': jpeg_signatures})
        raise error
    second = scan()
    if first != second:
        raise WCEError('OWN_RECONCILE_LIST_CHANGED')
    match = matches[0]
    final_data = image(match['media_id'])
    if final_data != (matched_raw if pixel else original):
        raise WCEError('OWN_RECONCILE_IMAGE_CHANGED')
    if pixel and decode_png(final_data, guard) != original_raster:
        raise WCEError('OWN_RECONCILE_IMAGE_CHANGED')
    result = {k: match[k] for k in ('media_id', 'url')}
    return {'result': result, 'update_time': match['update_time'],
        'complete_list_digest': digest(first), 'material_count': len(first),
        'raster': original_raster.fingerprint() if pixel else None,
        'remote_input_sha256': sha(matched_raw) if pixel else None,
        'remote_input_size': len(matched_raw) if pixel else None}
