"""Short-lived immutable loopback artifact. No account, token or remote images."""
import base64
from hashlib import sha256
from html import escape
from http.server import BaseHTTPRequestHandler
import secrets
import struct
import threading
import time

from .button_feedback import PREVIEW_STYLE
from .contracts import WCEError
from .own_settings_http import LimitedServer
from .documents import render_blocks

CSP = "default-src 'none'; img-src data:; style-src 'unsafe-inline'; base-uri 'none'; form-action 'none'; sandbox"

def dimensions(raw, mime):
    if not 0 < len(raw) <= 2097152:
        raise WCEError('DOCUMENT_PREVIEW_IMAGE')
    if mime == 'image/png' and raw[:8] == b'\x89PNG\r\n\x1a\n' and len(raw) >= 33 and raw[8:16] == b'\0\0\0\rIHDR':
        width, height = struct.unpack_from('>II', raw, 16)
    elif mime == 'image/jpeg' and raw[:2] == b'\xff\xd8' and raw[-2:] == b'\xff\xd9':
        i, width, height = 2, 0, 0
        for _ in range(512):
            if i + 4 > len(raw) or raw[i] != 255:
                raise WCEError('DOCUMENT_PREVIEW_IMAGE')
            while i < len(raw) and raw[i] == 255:
                i += 1
            marker = raw[i]; i += 1
            if marker in (0xDA, 0xD9):
                break
            size = int.from_bytes(raw[i:i+2], 'big')
            if size < 2 or i + size > len(raw):
                raise WCEError('DOCUMENT_PREVIEW_IMAGE')
            if marker in (0xC0, 0xC1, 0xC2):
                if size < 8 or raw[i+2] != 8:
                    raise WCEError('DOCUMENT_PREVIEW_IMAGE')
                height, width = struct.unpack_from('>HH', raw, i+3)
                break
            i += size
    else:
        raise WCEError('DOCUMENT_PREVIEW_IMAGE')
    if not 0 < width <= 4096 or not 0 < height <= 4096 or width * height > 4194304:
        raise WCEError('DOCUMENT_PREVIEW_IMAGE')
    return width, height


def html(document, images):
    from .documents import normalize
    from .import_styles import POLICY
    document = normalize(document)
    pixel_limit = (48 if document.get('format') == 3 and document.get('policy') == POLICY else 32) * 1024 * 1024
    urls, total, pixels = {}, 0, 0
    for slot, (mime, raw) in images.items():
        width, height = dimensions(raw, mime)
        total += len(raw); pixels += width * height
        if total > 32 * 1024 * 1024 or pixels > pixel_limit:
            raise WCEError('DOCUMENT_PREVIEW_LIMIT')
        urls[slot] = 'data:' + mime + ';base64,' + base64.b64encode(raw).decode('ascii')
    if document.get('format') == 3:
        from .own_body_link_diagnostic import preview_summary
        articles = []
        for index, article in enumerate(document['articles']):
            articles.append('<details class="wce-card"' + (' open' if index == 0 else '') +
                '><summary class="wce-summary">' + str(index+1) + ' · ' + escape(article['title']) +
                '</summary>' + preview_summary(article) +
                '<div class="wce-content">' + render_blocks(article, urls, preview=True) + '</div></details>')
        # Chrome selectors never match submitted content; no inherited reading theme.
        style = 'body{margin:0}.wce-header{padding:18px;background:#f1f5f2;font:14px system-ui;color:#375142}.wce-main{max-width:720px;margin:24px auto;padding:0 12px}.wce-card{margin-bottom:20px;border:1px solid #dce5de;border-radius:10px}.wce-summary{padding:14px;font:14px system-ui;cursor:pointer;overflow-wrap:anywhere}.wce-content{padding:16px}.wce-link-note{margin:0;padding:0 14px 12px;font:14px/1.5 system-ui;color:#375142}@media(min-width:760px){.wce-content{padding:30px}}'
        result = ('<!doctype html><html lang="zh-CN"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">'
            '<title>Jiusera · HTML 预览</title><style>' + style + PREVIEW_STYLE + '</style><header class="wce-header">Jiusera · 直接 HTML 本机预览</header><main class="wce-main">' + ''.join(articles) + '</main></html>').encode()
        if len(result) > 48 * 1024 * 1024:
            raise WCEError('DOCUMENT_PREVIEW_LIMIT')
        return result
    articles = []
    for index, article in enumerate(document['articles']):
        articles.append('<details' + (' open' if index == 0 else '') + '><summary>' +
            f'<span>{index+1:02d}</span> ' + escape(article['title']) + '</summary><article><h1>' +
            escape(article['title']) + '</h1>' +
            ('<p class="author">' + escape(article.get('author', '')) + '</p>' if article.get('author') else '') +
            render_blocks(article, urls, preview=True) + '</article></details>')
    style = '''*{box-sizing:border-box}body{margin:0;background:#f4f6f3;color:#26342e;font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif;overflow-wrap:anywhere}header{padding:20px 16px;border-bottom:1px solid #dfe7e1;background:#fff;font-size:13px;color:#64756a}main{max-width:720px;margin:24px auto;padding:0 16px}details{margin:0 0 16px;border:1px solid #dfe7e1;border-radius:12px;background:#fff;overflow:hidden}summary{white-space:pre-wrap;padding:16px;cursor:pointer;font-size:14px;font-weight:600;overflow-wrap:anywhere}summary span{color:#708477;margin-right:8px}article{padding:16px}h1{white-space:pre-wrap;font-size:28px;line-height:1.4;margin:0 0 12px}.author{white-space:pre-wrap;font-size:13px;color:#68796e;margin:0 0 24px}img{max-width:100%}blockquote{min-width:0}@media(min-width:760px){article{padding:32px}}'''
    result = ('<!doctype html><html lang="zh-CN"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">'
        '<title>Jiusera · 图文预览</title><style>' + style + PREVIEW_STYLE + '</style><header>Jiusera · 本机图文预览</header><main>' + ''.join(articles) + '</main></html>').encode()
    if len(result) > 48 * 1024 * 1024:
        raise WCEError('DOCUMENT_PREVIEW_LIMIT')
    return result


class PreviewServer:
    def __init__(self, content, guard=lambda: None, lifetime=300, clock=time.monotonic):
        if type(content) is not bytes or not 0 < len(content) <= 48 * 1024 * 1024 or not 0 < lifetime <= 300:
            raise WCEError('DOCUMENT_PREVIEW_LIMIT')
        guard()
        self.lock, self.guard, self.clock = threading.RLock(), guard, clock
        self.content, self.deadline, self.closed = content, clock() + lifetime, False
        self.digest = sha256(content).hexdigest()
        self.path = '/' + secrets.token_urlsafe(32)
        self.server = LimitedServer(('127.0.0.1', 0), Handler)
        self.server.daemon_threads = True
        self.server.preview = self
        self.host = '127.0.0.1:' + str(self.server.server_port)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True, name='wce-preview')
        self.thread.start()
        self.timer = threading.Timer(lifetime, self.close)
        self.timer.daemon = True
        self.timer.start()

    @property
    def url(self):
        return 'http://' + self.host + self.path

    def close(self):
        with self.lock:
            if self.closed:
                return
            self.closed, self.content = True, b''
        self.timer.cancel()
        self.server.shutdown()
        self.server.server_close()


class Handler(BaseHTTPRequestHandler):
    protocol_version = 'HTTP/1.0'
    def log_message(self, *args):
        pass
    def setup(self):
        super().setup()
        self.connection.settimeout(3)
    def handle_content(self, head=False):
        p = self.server.preview
        try:
            with p.lock:
                if (p.closed or p.clock() >= p.deadline or self.path != p.path
                        or self.headers.get_all('Host') != [p.host] or self.headers.get_all('Origin')):
                    raise WCEError('DOCUMENT_PREVIEW_DENIED')
                p.guard()
                content = p.content
                self.send_response(200)
                self.send_header('Content-Type', 'text/html; charset=utf-8')
                self.send_header('Content-Length', str(len(content)))
                self.send_header('Content-Security-Policy', CSP)
                self.send_header('Cache-Control', 'no-store')
                self.send_header('Referrer-Policy', 'no-referrer')
                self.send_header('X-Content-Type-Options', 'nosniff')
                self.end_headers()
                if not head:
                    self.wfile.write(content)
        except (WCEError, OSError, ValueError):
            self.send_error(403, 'Preview unavailable')
    def do_GET(self):
        self.handle_content()
    def do_HEAD(self):
        self.handle_content(True)
    def do_POST(self):
        self.send_error(405, 'Read only')
