"""Position-bound observations for normal HTML drafts, without URL or text output."""
from collections import Counter

from .contracts import WCEError
from .normal_html_limits import FRAGMENT_CHARS, POLICY
from .own_platform_representation import _HTML
from .service import digest

POLICY_NAME = 'NORMAL_DRAFT_BODY_LINKS_V1'
UNVERIFIED = 'UNVERIFIED'


def _body(raw, *, prepared=False):
    """Keep matched offsets and destinations in memory only."""
    try:
        parsed = _HTML(raw, max_content_chars=FRAGMENT_CHARS) if prepared else _HTML(raw)
    except (ValueError, TypeError, IndexError, UnicodeError):
        return None
    parts, links = [], []
    offset, open_link, hidden = 0, None, 0
    for kind, name, *attributes in parsed.tokens:
        if kind in ('start', 'end') and name in ('script', 'style', 'template'):
            hidden += 1 if kind == 'start' else -1
        elif not hidden and name == 'a' and kind in ('start', 'end', 'empty'):
            if kind == 'start':
                if open_link is not None:
                    return None
                open_link = (offset, dict(attributes[0]).get('href'))
            elif kind == 'end':
                if open_link is None:
                    return None
                links.append((open_link[0], offset, open_link[1]))
                open_link = None
            else:
                links.append((offset, offset, dict(attributes[0]).get('href')))
        elif not hidden and kind == 'data':
            parts.append(name)
            offset += len(name)
    return ''.join(parts), tuple(link for link in links if link[2])


def _match(source, target, link, unique):
    if not unique or target is None or source[0] != target[0]:
        return UNVERIFIED, None
    start, end, href = link
    exact = [hit for hit in target[1] if hit[:2] == (start, end)]
    if len(exact) == 1:
        return ('PRESERVED' if exact[0][2] == href else 'TARGET_CHANGED'), exact[0]
    if (not exact and start < end and source[0][start:end].strip()
            and not any(a < end and b > start for a, b, _ in target[1])):
        return 'TEXT_ONLY', None
    return UNVERIFIED, None


def _original_state(row, name):
    if row is None:
        return UNVERIFIED
    value = row.get(name)
    if type(value) is not str:
        return UNVERIFIED
    return 'SET' if value else 'ABSENT'


def _article(position, source_row, outbound_row, readback_row):
    source = _body(source_row.get('canonical_html'), prepared=True)
    outbound = _body(outbound_row.get('content')) if outbound_row is not None else None
    readback = _body(readback_row.get('content')) if readback_row is not None else None
    links = source[1] if source is not None else ()
    spans = Counter(link[:2] for link in links)
    observations = []
    for link_index, link in enumerate(links, 1):
        unique = spans[link[:2]] == 1
        delivery, sent = _match(source, outbound, link, unique)
        seen, _ = _match(source, readback, link, unique)
        after, _ = _match(outbound, readback, sent, True) if sent is not None else (UNVERIFIED, None)
        observations.append({'link_position': link_index, 'source_to_outbound': delivery,
            'outbound_to_readback': after, 'source_to_readback': seen})
    return {'article_position': position, 'source_link_count': len(links) if source is not None else None,
        'links': observations, 'read_original': {
            'source': _original_state(source_row, 'source_url') if 'source_url' in source_row else 'ABSENT',
            'outbound': _original_state(outbound_row, 'content_source_url'),
            'readback': _original_state(readback_row, 'content_source_url')}}


def _rows(projection, total):
    rows = projection.get('articles') if type(projection) is dict else None
    return rows if type(rows) is list and len(rows) == total and all(type(row) is dict for row in rows) else None


def _outbound(workflow, profile, row, intent, result):
    from .own_response_archive import ORIGIN, _read, completed
    if result.get('completion_origin') != ORIGIN:
        return None
    try:
        proof, raw, _ = _read(workflow, profile, row)
        if result == completed(proof, raw, row) and proof['request_sha256'] == digest(intent['projection']):
            # encode_draft uses this exact canonical UTF-8 JSON as the HTTP body.
            return intent['projection']
    except (WCEError, OSError, ValueError, TypeError, KeyError, UnicodeError):
        pass
    return None


def observe(workflow, profile, row, intent, result, document, actual):
    if intent.get('normal_html_policy') != POLICY or document.get('policy') != POLICY:
        return None
    source = document['articles']
    sent = _rows(_outbound(workflow, profile, row, intent, result), len(source))
    seen = _rows(actual, len(source))
    articles = []
    for index, original in enumerate(source):
        outgoing = sent[index] if sent is not None and sent[index].get('title') == original.get('title') else None
        readback = seen[index] if seen is not None and seen[index].get('title') == original.get('title') else None
        articles.append(_article(index + 1, original, outgoing, readback))
    return {'policy': POLICY_NAME, 'authority': False, 'source_evidence': 'PREPARED_HTML',
        'outbound_evidence': 'ORIGINAL_REQUEST_ARCHIVE' if sent is not None else UNVERIFIED,
        'readback_evidence': 'INDEPENDENT_PLATFORM_GET' if seen is not None else UNVERIFIED,
        'articles': articles}


def preview_summary(article):
    if article.get('style_policy') != POLICY:
        return ''
    # The prepared HTML has already been validated; the preview serializer uses
    # the same tree and replaces each anchor with a numbered, inactive span.
    from .html_document import Fragment
    tree = Fragment(article['canonical_html'], policy=POLICY).root
    pending, count = [tree], 0
    while pending:
        current = pending.pop()
        if type(current) is dict:
            count += current['tag'] == 'a'
            pending.extend(current['children'])
    original = '已设置' if article.get('source_url') else '未设置'
    hint = '。微信保存后可能仅保留锚文字，保存成功后可核对正文链接。' if count else '。'
    return f'<p class="wce-link-note">正文链接 {count} 处 · 阅读原文：{original}{hint}</p>'
