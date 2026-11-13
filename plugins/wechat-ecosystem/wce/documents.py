"""Versioned, closed document input and pure reading theme. No IO or authority."""
from copy import deepcopy
from html import escape
import re
from urllib.parse import urlsplit

from .contracts import WCEError
from .service import canonical
from .tools import schema
from .editor_contracts import COVER_INFO, DIMENSIONS, INTENT, validate as validate_editorial
from .prepared_contracts import strict_validate

THEME, RENDERER = 'reading-v1', 'wce-html-v2'
TEXT = {'type': 'string', 'minLength': 0, 'maxLength': 8192}
SLOT = {'type': 'string', 'pattern': '^[A-Za-z0-9_-]{1,32}$'}
ASSET = {'type': 'string', 'pattern': '^own-asset-[a-f0-9]{32}$'}
INLINE = {'oneOf': [schema({'type': {'type': 'string', 'const': t}, 'text': TEXT},
                         {'href': {'type': 'string', 'maxLength': 1024}} if t == 'link' else {})
                      for t in ('text', 'strong', 'em', 'link')]}
INLINES = {'type': 'array', 'minItems': 1, 'maxItems': 128, 'items': INLINE}

def list_spec(depth):
    item = schema({'inlines': INLINES}, {'children': list_spec(depth - 1)} if depth > 1 else {})
    return schema({'type': {'type': 'string', 'const': 'list'}, 'ordered': {'type': 'boolean'},
                   'items': {'type': 'array', 'minItems': 1, 'maxItems': 40, 'items': item}})

BLOCK = {'oneOf': [schema({'type': {'type': 'string', 'const': t}, 'inlines': INLINES},
                          {'level': {'type': 'integer', 'enum': [2, 3]}} if t == 'heading' else {})
                      for t in ('paragraph', 'heading', 'quote')] + [
    schema({'type': {'type': 'string', 'const': 'divider'}}), list_spec(2),
    schema({'type': {'type': 'string', 'const': 'image'}, 'slot': SLOT, 'asset_ref': ASSET,
            'alt': {'type': 'string', 'maxLength': 1024}},
           {'caption': {'type': 'string', 'maxLength': 2048}})]}
ARTICLE = schema({'id': {'type': 'string', 'pattern': '^[A-Za-z0-9]{1,16}$'},
    'title': {'type': 'string', 'minLength': 1, 'maxLength': 128}, 'cover_asset_ref': ASSET}, {
    'author': {'type': 'string', 'maxLength': 64}, 'digest': {'type': 'string', 'maxLength': 480},
    'source_url': {'type': 'string', 'maxLength': 1024},
    'cover_info': COVER_INFO, 'cover_dimensions': DIMENSIONS, 'editorial_intent': INTENT,
    'blocks': {'type': 'array', 'minItems': 1, 'maxItems': 64, 'items': BLOCK},
    'markdown': {'type': 'string', 'minLength': 1, 'maxLength': 65536},
    'image_slots': {'type': 'array', 'maxItems': 4, 'items': schema({'slot': SLOT, 'asset_ref': ASSET})}})
DOCUMENT = schema({'format': {'type': 'integer', 'const': 2}, 'theme': {'type': 'string', 'const': THEME},
    'renderer': {'type': 'string', 'const': RENDERER},
    'articles': {'type': 'array', 'minItems': 1, 'maxItems': 8, 'items': ARTICLE}})

def fail(code='DOCUMENT_INVALID', line=None):
    # Location is a bounded integer; never reflect submitted text in errors.
    error = WCEError(code)
    error.line = line
    raise error

def safe_url(value):
    if (type(value) is not str or not 0 < len(value.encode()) <= 1024
            or any(ord(c) < 33 or ord(c) == 127 for c in value) or '\\' in value):
        fail('DOCUMENT_INVALID_URL')
    try:
        u = urlsplit(value)
        if u.scheme not in ('http', 'https') or not u.hostname or u.username is not None or u.password is not None:
            fail('DOCUMENT_INVALID_URL')
        u.port
        u.hostname.encode('idna')
    except (ValueError, UnicodeError):
        fail('DOCUMENT_INVALID_URL')
    return value

def nodes(v):
    if isinstance(v, dict):
        return 1 + sum(1 + nodes(x) for x in v.values())
    if isinstance(v, list):
        return 1 + sum(nodes(x) for x in v)
    return 1

def inline_markdown(text, line):
    parts, plain, i = [], '', 0
    def flush():
        nonlocal plain
        if plain:
            parts.append({'type': 'text', 'text': plain}); plain = ''
    while i < len(text):
        if text[i] == '\\':
            if i + 1 >= len(text) or text[i + 1] not in r'\*_[]<>`|':
                fail('DOCUMENT_MARKDOWN_UNSUPPORTED', line)
            plain += text[i + 1]; i += 2; continue
        token = '**' if text.startswith('**', i) else '*' if text[i] == '*' else None
        if token:
            end = text.find(token, i + len(token))
            if end < 0 or end == i + len(token):
                fail('DOCUMENT_MARKDOWN_UNSUPPORTED', line)
            value = text[i + len(token):end]
            if any(c in value for c in '*[]`<>\\\n'):
                fail('DOCUMENT_MARKDOWN_UNSUPPORTED', line)
            flush(); parts.append({'type': 'strong' if token == '**' else 'em', 'text': value})
            i = end + len(token); continue
        if text[i] == '[':
            match = re.match(r'\[([^\[\]\n]+)\]\(([^\s()]+)\)', text[i:])
            if not match:
                fail('DOCUMENT_MARKDOWN_UNSUPPORTED', line)
            if any(c in match[1] for c in '\\*_`<>'):
                fail('DOCUMENT_MARKDOWN_UNSUPPORTED', line)
            flush(); safe_url(match[2]); parts.append({'type': 'link', 'text': match[1], 'href': match[2]})
            i += len(match[0]); continue
        if text[i] in '[]<>`|_!' or text.startswith('~~', i):
            fail('DOCUMENT_MARKDOWN_UNSUPPORTED', line)
        if text[i] == '\n':
            line += 1
        plain += text[i]; i += 1
    flush()
    if not parts:
        fail('DOCUMENT_MARKDOWN_UNSUPPORTED', line)
    return parts

def markdown_blocks(text, slots):
    lines, result, used = text.split('\n'), [], set()
    i = 0
    def parse_list(start, indent):
        items, ordered = [], None
        while start < len(lines):
            m = re.fullmatch(r'( *)([-+]|[1-9][0-9]*\.) (.+)', lines[start])
            if not m or len(m[1]) < indent:
                break
            if len(m[1]) != indent or indent > 2:
                fail('DOCUMENT_MARKDOWN_UNSUPPORTED', start + 1)
            current = m[2].endswith('.')
            if ordered is not None and current != ordered:
                break
            ordered = current
            if current and m[2] != str(len(items) + 1) + '.':
                fail('DOCUMENT_MARKDOWN_UNSUPPORTED', start + 1)
            item = {'inlines': inline_markdown(m[3], start + 1)}
            start += 1
            if start < len(lines):
                child = re.match(r'( +)(?:[-+]|[1-9][0-9]*\.) ', lines[start])
                if child and len(child[1]) > indent:
                    if len(child[1]) != indent + 2:
                        fail('DOCUMENT_MARKDOWN_UNSUPPORTED', start + 1)
                    item['children'], start = parse_list(start, indent + 2)
            items.append(item)
        return {'type': 'list', 'ordered': bool(ordered), 'items': items}, start
    while i < len(lines):
        line, number = lines[i], i + 1
        if not line:
            i += 1; continue
        if line == '---':
            result.append({'type': 'divider'}); i += 1; continue
        if re.match(r'( *)([-+]|[1-9][0-9]*\.) ', line):
            if line.startswith(' '):
                fail('DOCUMENT_MARKDOWN_UNSUPPORTED', number)
            block, i = parse_list(i, 0); result.append(block); continue
        image = re.fullmatch(r'!\[([^\[\]]*)\]\(asset:([A-Za-z0-9_-]{1,32})\)', line)
        if image:
            slot = image[2]
            if '\\' in image[1]:
                fail('DOCUMENT_MARKDOWN_UNSUPPORTED', number)
            if slot not in slots or slot in used:
                fail('DOCUMENT_MARKDOWN_IMAGE', number)
            used.add(slot); result.append({'type': 'image', 'slot': slot, 'asset_ref': slots[slot], 'alt': image[1]})
            i += 1; continue
        heading = re.fullmatch(r'(##|###) (.+)', line)
        if heading:
            result.append({'type': 'heading', 'level': len(heading[1]), 'inlines': inline_markdown(heading[2], number)})
            i += 1; continue
        if line.startswith('> '):
            result.append({'type': 'quote', 'inlines': inline_markdown(line[2:], number)}); i += 1; continue
        if re.fullmatch(r'={3,}', line):
            fail('DOCUMENT_MARKDOWN_UNSUPPORTED', number)
        if line.startswith(('#', ' ', '\t', '>', '```', '~~~', '---', '***')) or '\r' in line:
            fail('DOCUMENT_MARKDOWN_UNSUPPORTED', number)
        paragraph = [line]; i += 1
        while i < len(lines) and lines[i] and not re.match(r'^(?:#|>|!|---|\s|[-+] |[1-9][0-9]*\. )', lines[i]):
            if re.fullmatch(r'(?:=+|-+)', lines[i]):
                fail('DOCUMENT_MARKDOWN_UNSUPPORTED', i + 1)
            paragraph.append(lines[i]); i += 1
        if i < len(lines) and re.fullmatch(r'(?:=+|-+)', lines[i]):
            fail('DOCUMENT_MARKDOWN_UNSUPPORTED', i + 1)
        result.append({'type': 'paragraph', 'inlines': inline_markdown('\n'.join(paragraph), number)})
    if set(slots) != used:
        fail('DOCUMENT_MARKDOWN_IMAGE')
    return result

def walk_inlines(block):
    if 'inlines' in block:
        yield block['inlines']
    for item in block.get('items', []):
        yield item['inlines']
        if 'children' in item:
            yield from walk_inlines(item['children'])

def normalize(value):
    if type(value) is dict and value.get('format') == 3:
        from .html_document import normalize as normalize_html
        return normalize_html(value)
    strict_validate(value, DOCUMENT, -16)
    result = deepcopy(value)
    ids = set()
    for article in result['articles']:
        if article['id'] in ids or not article['title'].strip():
            fail()
        ids.add(article['id'])
        from .html_technical_standard import validate_metadata
        validate_metadata(article, article_count=len(result['articles']))
        validate_editorial(article)
        if article.get('source_url'):
            safe_url(article['source_url'])
        if ('blocks' in article) == ('markdown' in article) or 'blocks' in article and 'image_slots' in article:
            fail()
        if 'markdown' in article:
            slots = article.pop('image_slots', [])
            mapping = {s['slot']: s['asset_ref'] for s in slots}
            if len(mapping) != len(slots):
                fail()
            article['blocks'] = markdown_blocks(article.pop('markdown'), mapping)
        strict_validate(article, ARTICLE, -16)
        if not any(b['type'] in ('paragraph', 'heading', 'quote', 'list') for b in article['blocks']):
            fail()
        for b in article['blocks']:
            for inlines in walk_inlines(b):
                for inline in inlines:
                    if inline['type'] == 'link':
                        if 'href' not in inline:
                            fail('DOCUMENT_INVALID_URL')
                        safe_url(inline['href'])
        body = [b for b in article['blocks'] if b['type'] == 'image']
        if (len(body) > 4 or len({b['slot'] for b in body}) != len(body) or any(b['slot'] == 'cover' for b in body)
                or len({article['cover_asset_ref']} | {b['asset_ref'] for b in body}) != len(body) + 1):
            fail()
    if len(canonical(result).encode()) > 96 * 1024 or nodes(result) > 650:
        fail('DOCUMENT_LIMIT')
    return result

def visible_text(article):
    if 'canonical_html' in article:
        from .html_document import visible_text as html_text
        return html_text(article)
    return '\n'.join(''.join(i['text'] for i in inline) for b in article['blocks'] for inline in walk_inlines(b))

def assets(document):
    if document.get('format') == 3:
        from .html_document import assets as html_assets
        yield from html_assets(document)
        return
    for article in document['articles']:
        yield article['id'] + '--cover', article['cover_asset_ref'], 'cover'
        for block in article['blocks']:
            if block['type'] == 'image':
                yield article['id'] + '--' + block['slot'], block['asset_ref'], 'body'

ROOT_STYLE = 'font-size:16px;line-height:1.8;color:#26342e;text-align:left;white-space:pre-wrap;overflow-wrap:anywhere;word-break:break-word;'
P_STYLE = 'margin:0 0 16px;white-space:pre-wrap;'
LINK_STYLE = 'color:#226448;text-decoration:underline;overflow-wrap:anywhere;'

def inlines_html(inlines, preview=False):
    parts = []
    for item in inlines:
        content = escape(item['text'], quote=True).replace('\n', '<br>')
        kind = item['type']
        if kind in ('strong', 'em'):
            content = f'<{kind}>{content}</{kind}>'
        elif kind == 'link':
            href = safe_url(item['href'])
            content = (f'<span style="{LINK_STYLE}">{content}</span>' if preview else
                       f'<a href="{escape(href, quote=True)}" style="{LINK_STYLE}">{content}</a>')
        parts.append(content)
    return ''.join(parts)

def render_blocks(article, urls, preview=False):
    if 'canonical_html' in article:
        from .html_document import render
        return render(article, urls, preview)
    def render_list(block):
        tag = 'ol' if block['ordered'] else 'ul'
        items = ''.join('<li style="margin:0 0 8px;">' + inlines_html(i['inlines'], preview) +
                        (render_list(i['children']) if 'children' in i else '') + '</li>' for i in block['items'])
        return f'<{tag} style="margin:0 0 16px;padding-left:24px;">{items}</{tag}>'
    parts = []
    for block in article['blocks']:
        kind = block['type']
        if kind in ('paragraph', 'heading', 'quote'):
            text = inlines_html(block['inlines'], preview)
            if kind == 'paragraph':
                html = f'<p style="{P_STYLE}">{text}</p>'
            elif kind == 'heading':
                level = block.get('level', 2)
                html = f'<h{level} style="font-size:{24 if level == 2 else 20}px;line-height:1.5;margin:28px 0 16px;font-weight:700;">{text}</h{level}>'
            else:
                html = f'<blockquote style="margin:0 0 16px;padding:12px 16px;border-left:3px solid #9bb9a7;background:#f3f7f4;">{text}</blockquote>'
        elif kind == 'divider':
            html = '<hr style="border:0;border-top:1px solid #dfe7e1;margin:24px 0;">'
        elif kind == 'list':
            html = render_list(block)
        else:
            url = urls[article['id'] + '--' + block['slot']]
            if not preview:
                safe_url(url)
            html = '<section style="margin:20px 0;"><img style="display:block;max-width:100%;height:auto;margin:0 auto;" src="' + escape(url, quote=True) + '" alt="' + escape(block['alt'], quote=True) + '">'
            if block.get('caption'):
                html += '<p style="font-size:13px;line-height:1.6;color:#68796e;text-align:center;margin:8px 0 0;white-space:pre-wrap;">' + escape(block['caption']) + '</p>'
            html += '</section>'
        parts.append(html)
    return '<section style="' + ROOT_STYLE + '">' + ''.join(parts) + '</section>'

def render_projection(document, mappings):
    rows = []
    urls = {k: v['url'] for k, v in mappings.items() if 'url' in v}
    for article in document['articles']:
        content = render_blocks(article, urls)
        from .normal_html_limits import final_content
        final_content(content)
        rows.append({'article_type': 'news', 'title': article['title'], 'content': content,
            'thumb_media_id': mappings[article['id'] + '--cover']['media_id'],
            'author': article.get('author', ''), 'digest': article.get('digest', ''),
            'content_source_url': article.get('source_url', ''),
            **({'cover_info': article['cover_info']} if 'cover_info' in article else {})})
    return {'articles': rows}
