"""Isolated zero-account MCP App transport probe; never import WCE account code."""
from __future__ import annotations

import base64
import hashlib
import hmac
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import re
import secrets
import threading
import os
import stat
from pathlib import Path
import time
from urllib.parse import urlsplit

RESOURCE = "ui://wechat-ecosystem/inline-account-probe-v1.html"
MIME = "text/html;profile=mcp-app"
SHOW = "wce.ui.show_management"
START = "wce.settings.open"
EMPTY_SCHEMA = {"type": "object", "properties": {}, "additionalProperties": False}
TTL_SECONDS = 120  # Probe authentication lifetime; not a business quota.
MAX_BODY = 2048


def _registered_app_origin(value: str) -> bool:
    return type(value) is str and re.fullmatch(
        r'https://mcp-registration-[a-f0-9]{32}\.web-sandbox\.oaiusercontent\.com', value) is not None


def exact_frame_origin(value: str) -> str:
    """Serialized origin in an owner-pinned, observed complete frame chain.

    This parses a single CSP source, not a wildcard or permission grant. Only
    the private observation/config pair below can adopt a chain.
    """
    if (type(value) is not str or len(value) > 512
            or not re.fullmatch(r'[a-z][a-z0-9+.-]*://[a-zA-Z0-9.\-:\[\]]+', value)):
        raise ValueError('EXACT_FRAME_ORIGIN_REQUIRED')
    p = urlsplit(value)
    if (p.scheme not in {'http','https','app','codex-sandbox'} or not p.hostname
            or p.username or p.password or p.path or p.query or p.fragment
            or (p.port is not None and not 1 <= p.port <= 65535)):
        raise ValueError('EXACT_FRAME_ORIGIN_REQUIRED')
    return value


def trusted_origin(value: str) -> str:
    """Only operator-configured exact origins; never accept RPC origin input."""
    p = urlsplit(value)
    if (p.username or p.password or p.path or p.query or p.fragment
            or not p.hostname or "*" in value or value == "null"):
        raise ValueError("EXACT_TRUSTED_ORIGIN_REQUIRED")
    if p.scheme == "codex-sandbox":
        if not re.fullmatch(r"mcp-app-[a-f0-9]+\.web-sandbox\.oaiusercontent\.com", p.hostname):
            raise ValueError("EXACT_TRUSTED_ORIGIN_REQUIRED")
    elif p.scheme in {"http", "https"}:
        registered_app = _registered_app_origin(value)
        if not registered_app and p.hostname != "127.0.0.1" and not p.hostname.endswith(".test"):
            raise ValueError("PROBE_ORIGIN_NOT_LOCAL_OR_FIXTURE")
    else:
        raise ValueError("EXACT_TRUSTED_ORIGIN_REQUIRED")
    if p.netloc != p.hostname and not re.fullmatch(re.escape(p.hostname) + r":[0-9]+", p.netloc):
        raise ValueError("EXACT_TRUSTED_ORIGIN_REQUIRED")
    if p.port is not None and not 1 <= p.port <= 65535:
        raise ValueError("EXACT_TRUSTED_ORIGIN_REQUIRED")
    return value


CHILD_SCRIPT = r"""
(() => {
 'use strict';
 const status = document.getElementById('status');
 let bootstrap = location.hash.slice(1), session = '', ended = false;
 history.replaceState(null, '', location.pathname);
 const clear = () => {
   ended = true; bootstrap = session = '';
   for (const input of document.querySelectorAll('input')) input.value = '';
   document.getElementById('empty-post').disabled = true;
 };
 addEventListener('pagehide', clear);
 async function call(path, value, token = '') {
   const r = await fetch(path, {method:'POST', headers:{'Content-Type':'application/json',
     'X-WCE-Probe-Session':token, 'X-WCE-Probe-Generation':document.querySelector('meta[name=probe-process]').content}, body:JSON.stringify(value), credentials:'omit',
     cache:'no-store', redirect:'error', referrerPolicy:'no-referrer'});
   const result = await r.json();
   if (!r.ok || ended) throw new Error('PROBE_CHANNEL_UNAVAILABLE');
   return result;
 }
 document.getElementById('empty-post').addEventListener('click', async event => {
   if (!session || ended) return;
   try { const value = await call('/empty', {}, session);
     if (value.state !== 'EMPTY_POST_OK') throw new Error('INVALID_RESULT');
     status.textContent = '空请求通道通过；未提交任何账号信息。';
   } catch (_) { clear(); status.textContent = 'EMPTY_POST_HOLD：同源空POST未通过；没有账号操作。'; }
 });
 call('/bootstrap', {bootstrap}).then(value => {
   bootstrap = '';
   if (value.state !== 'PROBE_READY' || typeof value.session !== 'string') throw new Error('INVALID_RESULT');
   session = value.session;
   status.textContent = '本机子页面已载入；所有账号字段均为禁用占位。';
   document.getElementById('empty-post').disabled = false;
 }).catch(() => { clear(); status.textContent = 'CHILD_BOOTSTRAP_HOLD：子页已执行但同源启动未通过；没有账号操作。'; });
 setTimeout(() => {clear(); status.textContent = '测试会话已过期；没有账号操作。';}, 120000);
})();
"""

CHILD_HTML = """<!doctype html><html lang="zh-CN"><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>内嵌页面通道测试</title><body>
<h1>内嵌页面通道测试</h1><p>零账号原型。请勿输入真实资料或 AppSecret。</p>
<fieldset disabled><legend>不可编辑的展示占位</legend>
<label>AppID <input type="text" autocomplete="off" placeholder="仅占位，禁止真实输入"></label>
<label>名称 <input type="text" autocomplete="off" placeholder="仅占位，禁止真实输入"></label>
<label>AppSecret <input type="password" autocomplete="off" placeholder="仅占位，禁止真实输入"></label>
</fieldset><p id="status">正在验证本机子页面通道。</p>
<button id="empty-post" type="button" disabled>测试空请求（不含账号信息）</button>
<script>""" + CHILD_SCRIPT + "</script></body></html>"


def csp_hash(value: str) -> str:
    return "'sha256-" + base64.b64encode(hashlib.sha256(value.encode()).digest()).decode() + "'"


APP_SCRIPT = r"""
(() => {
 'use strict';
 let id = 0, disposed = false;
 const pending = new Map(), status = document.getElementById('status');

 function send(method, params) {
   if (disposed) return Promise.reject(new Error('CLOSED'));
   return new Promise((resolve, reject) => {
     const request = ++id;
     const timer = setTimeout(() => {pending.delete(request); reject(new Error('HOST_TIMEOUT'));}, 60000);
     pending.set(request, {resolve, reject, timer});
     parent.postMessage({jsonrpc:'2.0', id:request, method, params}, '*');
   });
 }
 function dispose() {
   disposed = true;
   document.getElementById('frame').removeAttribute('src');
   for (const item of pending.values()) {clearTimeout(item.timer); item.reject(new Error('CLOSED'));}
   pending.clear();
 }
 addEventListener('pagehide', dispose);
 addEventListener('message', event => {
   if (event.source !== parent || !event.data || event.data.jsonrpc !== '2.0') return;
   const data = event.data, item = pending.get(data.id);
   if (!item) return;
   clearTimeout(item.timer); pending.delete(data.id);
   if (data.method || data.error || !Object.hasOwn(data,'result')) item.reject(new Error('HOST_ERROR'));
   else item.resolve(data.result);
 });
 async function startProbe() {
   try {
     const result = await send('tools/call', {name:'wce.settings.open',arguments:{}});
     mount(result);
   } catch (error) {
     const labels = {HOST_CONFIG_HOLD:'HOST_CONFIG_HOLD：新页面来源尚未受信核验；未签发会话。', HOST_TIMEOUT:'HOST_TIMEOUT：宿主显示桥超时；未重发。', HOST_ERROR:'HOST_RPC_HOLD：宿主调用拒绝；未进行账号操作。', INVALID_PROBE_RESULT:'INVALID_META：未获得合法UI专用结果。', HOST_ORIGIN_MISMATCH:'HOST_ORIGIN_MISMATCH：当前页面来源未经核验。', INVALID_PROBE_URL:'TRANSPORT_MISMATCH：资源缓存或传输来源不符。'};
     status.textContent = labels[error.message] || 'HOST_CHANNEL_HOLD：通道未建立；没有账号操作。';
   }
 }
 function mount(result) {
   if (disposed) return;
   const value = result?._meta?.wceInlineProbe;
   if (result?.isError) {
     const code = result?.structuredContent?.error;
     throw new Error(code === 'SETTINGS_INLINE_HOST_HOLD' ? 'HOST_CONFIG_HOLD' : 'HOST_ERROR');
   }
   if (result?.structuredContent?.state !== 'SETTINGS_OPENED' ||
       !value || value.origin !== EXPECTED_ORIGIN || value.processGeneration !== EXPECTED_PROCESS_GENERATION || typeof value.url !== 'string') throw new Error('INVALID_PROBE_RESULT');
   if (typeof value.trustedAppOrigin !== 'string' || location.origin !== value.trustedAppOrigin || window.top !== window.self) throw new Error('HOST_ORIGIN_MISMATCH');
   const url = new URL(value.url);
   if (url.origin !== EXPECTED_ORIGIN || url.pathname !== '/probe' || url.search || !/^#[a-f0-9]{64}$/.test(url.hash)) throw new Error('INVALID_PROBE_URL');
   const frame = document.getElementById('frame');
   frame.addEventListener('load', () => {status.textContent = 'FRAME_LOAD_EVENT：请核对子页标题；不代表空POST已通过。';}, {once:true});
   frame.src = value.url;
   status.textContent = '已请求内嵌测试页；实际加载与空请求仍需观察。';
 }
 document.getElementById('retry').addEventListener('click', () => {startProbe();});
 send('ui/initialize', {appInfo:{name:'wce-zero-account-inline-probe',version:'probe-v1'},
   appCapabilities:{availableDisplayModes:['inline','fullscreen']},protocolVersion:'2026-01-26'})
 .then(async host => {
   if (disposed || host.protocolVersion !== '2026-01-26' || !host.hostCapabilities?.serverTools)
     throw new Error('NO_SERVER_TOOLS');
   parent.postMessage({jsonrpc:'2.0',method:'ui/notifications/initialized'}, '*');
   document.getElementById('retry').disabled = false;
   await startProbe();
 }).catch(() => {status.textContent = '内嵌通道未能建立；没有账号操作。';});
})();
"""


class Probe:
    def __init__(self, trusted_ancestors=(), clock=time.monotonic):
        self.ancestors = tuple(trusted_origin(item) for item in trusted_ancestors)
        self.process_generation = secrets.token_hex(16)
        self.config_generation = -1
        self.config_digest = None
        self.config_guard = False
        self.clock = clock
        self.lock = threading.Lock()
        self.closed = False
        self.pending = {}
        self.sessions = {}
        self.http = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
        self.http.daemon_threads = True
        self.http.probe = self
        self.origin = 'http://127.0.0.1:' + str(self.http.server_port)
        self.host = '127.0.0.1:' + str(self.http.server_port)
        self.thread = threading.Thread(target=self.http.serve_forever, daemon=True)
        self.thread.start()

    def close(self):
        with self.lock:
            self.closed = True
            self.pending.clear()
            self.sessions.clear()
        self.http.shutdown()
        self.http.server_close()
        self.thread.join(timeout=5)

    def expire(self):
        now = self.clock()
        for store in (self.pending, self.sessions):
            for key, record in list(store.items()):
                if not 0 <= now - record[0] < TTL_SECONDS:
                    del store[key]

    def _refresh(self):
        if self.config_guard:
            _apply_host_config(self)

    def _record(self):
        return (self.clock(), self.process_generation, self.config_generation, self.config_digest)

    def _current_record(self, record):
        return record[1:] == (self.process_generation, self.config_generation, self.config_digest)

    def start(self):
        self._refresh()
        if not self.ancestors:
            raise ValueError('TRUSTED_ANCESTORS_NOT_CONFIGURED')
        with self.lock:
            if self.closed:raise ValueError('PROBE_ACCESS_DENIED')
            self.expire()
            token = secrets.token_hex(32)
            self.pending[token] = self._record()
        return {'content': [{'type': 'text', 'text': 'SETTINGS_OPENED'}],
                'structuredContent': {'state': 'SETTINGS_OPENED'},
                '_meta': {'wceInlineProbe': {'origin': self.origin, 'processGeneration': self.process_generation, 'configGeneration': self.config_generation, 'configDigest': self.config_digest,
                    'url': self.origin + '/probe#' + token}}}

    def bootstrap(self, value):
        self._refresh()
        if (type(value) is not dict or set(value) != {'bootstrap'} or type(value['bootstrap']) is not str
                or not re.fullmatch(r'[a-f0-9]{64}', value['bootstrap'])):
            raise ValueError('PROBE_INVALID_REQUEST')
        with self.lock:
            if self.closed:raise ValueError('PROBE_ACCESS_DENIED')
            self.expire()
            match = next((key for key in self.pending if hmac.compare_digest(key, value['bootstrap'])), None)
            if match is None:
                raise ValueError('PROBE_ACCESS_DENIED')
            created = self.pending.pop(match)
            if not self._current_record(created):raise ValueError('PROBE_ACCESS_DENIED')
            session = secrets.token_hex(32)
            self.sessions[session] = created  # Bootstrap never extends TTL.
        return {'state': 'PROBE_READY', 'session': session}

    def empty(self, value, token):
        self._refresh()
        if type(value) is not dict or value:
            raise ValueError('PROBE_INVALID_REQUEST')
        with self.lock:
            if self.closed:raise ValueError('PROBE_ACCESS_DENIED')
            self.expire()
            if (not re.fullmatch(r'[a-f0-9]{64}', token)
                    or not any(hmac.compare_digest(key, token) and self._current_record(record) for key, record in self.sessions.items())):
                raise ValueError('PROBE_ACCESS_DENIED')
        return {'state': 'EMPTY_POST_OK'}

    def resource(self):
        html = '<!doctype html><html lang="zh-CN"><meta charset="utf-8">' \
            '<title>WCE 零账号内嵌通道测试</title><body><h1>WCE 零账号内嵌通道测试</h1>' \
            '<p id="status">正在初始化宿主桥。</p><button id="retry" type="button" disabled>重试零账号通道</button>' \
            '<iframe id="frame" title="内嵌页面通道测试" width="100%" height="520" ' \
            'sandbox="allow-scripts allow-same-origin" referrerpolicy="no-referrer"></iframe>' \
            '<script>const EXPECTED_ORIGIN=' + json.dumps(self.origin) + ';\nconst EXPECTED_PROCESS_GENERATION=' + json.dumps(self.process_generation) + ';\n' + APP_SCRIPT + '</script></body></html>'
        return {'contents': [{'uri': RESOURCE, 'mimeType': MIME, 'text': html,
            '_meta': {'ui': {'csp': {'connectDomains': [], 'resourceDomains': [],
                                     'frameDomains': [self.origin]}},
                      'openai/ui': {'availableDisplayModes': ['inline', 'fullscreen'],
                                    'preferredDisplayMode': 'inline'}}}]}



class Handler(BaseHTTPRequestHandler):
    def log_message(self, *_):
        pass  # Never persist HTTP requests, headers or body.

    def send_error(self, *_args, **_kwargs):
        # BaseHTTPRequestHandler otherwise reflects malformed request text.
        self.respond(400, {'error': 'PROBE_ACCESS_DENIED'})

    def setup(self):
        super().setup()
        self.connection.settimeout(3)

    def respond(self, code, value, html=False):
        raw = value.encode() if html else json.dumps(value).encode()
        p = self.server.probe
        ancestors = ' '.join(p.ancestors) if p.ancestors else "'none'"
        self.send_response(code)
        self.send_header('Content-Type', 'text/html; charset=utf-8' if html else 'application/json')
        self.send_header('Content-Length', str(len(raw)))
        self.send_header('Cache-Control', 'no-store')
        self.send_header('Referrer-Policy', 'no-referrer')
        self.send_header('X-Content-Type-Options', 'nosniff')
        self.send_header('Content-Security-Policy', "default-src 'none'; script-src " + csp_hash(CHILD_SCRIPT)
                         + "; connect-src 'self'; base-uri 'none'; form-action 'none'; frame-ancestors " + ancestors)
        self.end_headers()
        try:
            self.wfile.write(raw)
        except (OSError, TimeoutError):
            pass

    def valid(self, post=False):
        p = self.server.probe
        names = ('Host', 'Origin', 'Content-Length', 'Content-Type', 'X-WCE-Probe-Session', 'X-WCE-Probe-Generation')
        if any(len(self.headers.get_all(name, [])) > 1 for name in names):
            return False
        if self.headers.get('Host') != p.host or self.headers.get_all('Transfer-Encoding'):
            return False
        return not post or (self.headers.get('Origin') == p.origin
                            and self.headers.get('Content-Type') == 'application/json'
                            and self.headers.get('X-WCE-Probe-Generation') == p.process_generation)

    def do_GET(self):
        if self.valid() and self.path == '/probe':
            page = CHILD_HTML.replace('<title>', '<meta name="probe-process" content="' + self.server.probe.process_generation + '"><title>', 1)
            self.respond(200, page, html=True)
        else:
            self.respond(403, {'error': 'PROBE_ACCESS_DENIED'})

    def do_POST(self):
        if not self.valid(post=True):
            self.respond(403, {'error': 'PROBE_ACCESS_DENIED'})
            return
        try:
            length = self.headers.get('Content-Length', '')
            if not length.isascii() or not length.isdecimal() or not 1 <= int(length) <= MAX_BODY:
                raise ValueError('PROBE_INVALID_REQUEST')
            def unique(pairs):
                result = {}
                for key, item in pairs:
                    if key in result:
                        raise ValueError('PROBE_INVALID_REQUEST')
                    result[key] = item
                return result
            value = json.loads(self.rfile.read(int(length)), object_pairs_hook=unique)
            if self.path == '/bootstrap':
                result = self.server.probe.bootstrap(value)
            elif self.path == '/empty':
                result = self.server.probe.empty(value, self.headers.get('X-WCE-Probe-Session', ''))
            else:
                raise ValueError('PROBE_INVALID_REQUEST')
            self.respond(200, result)
        except (ValueError, TypeError, UnicodeError, OSError, TimeoutError):
            self.respond(403, {'error': 'PROBE_ACCESS_DENIED'})


# Explicit V2 zero-account UI mode; no caller parameter/env/global MCP config.
# The shell is enabled, but no session capability can be issued until local
# operator observation pins the new resource origin in HOST_CONFIG.
# The observation is current-view-only. A changed origin is a HOLD, never broadened.
ENABLED = False
_transport = None
_transport_lock = threading.Lock()


def configured():
    return ENABLED is True


def current():
    global _transport
    if not configured():
        return None
    with _transport_lock:
        if _transport is None:
            _transport = Probe()
            _transport.config_guard = True
        return _transport


def close():
    global _transport
    with _transport_lock:
        former, _transport = _transport, None
    if former is not None:
        former.close()

_UI_SEAL = object()


class _UIResult:
    __slots__ = ('_meta', '_seal')

    def __init__(self, meta, seal):
        if seal is not _UI_SEAL:
            raise ValueError('PROBE_RESULT_HOLD')
        self._meta, self._seal = meta, seal


def start_for_app(probe):
    if type(probe) is not Probe:
        raise ValueError('PROBE_RESULT_HOLD')
    _apply_host_config(probe)
    meta = probe.start()['_meta']
    meta['wceInlineProbe']['trustedAppOrigin'] = probe.ancestors[0]
    return _UIResult(meta, _UI_SEAL)


def take_metadata(value):
    if type(value) is not _UIResult or value._seal is not _UI_SEAL:
        raise ValueError('PROBE_RESULT_HOLD')
    result = value._meta
    value._meta, value._seal = None, None
    return result

# Fixed project-local, non-secret operator configuration; never tool params.
HOST_CONFIG = Path.home() / '.wce' / 'inline-host.json'

HOST_OBSERVATION = HOST_CONFIG.parent / 'host-observation.json'


def _identity(info):
    return (info.st_dev, info.st_ino, info.st_uid, stat.S_IMODE(info.st_mode))


def _leaf_identity(info):
    return _identity(info) + (info.st_size, info.st_mtime_ns, info.st_ctime_ns)


def _read_private_snapshot(path):
    """Read one fixed file through physical dirfds and verify the chain twice."""
    if not path.is_absolute() or '..' in path.parts:
        raise ValueError('HOST_CONFIG_HOLD')
    fds = []
    chain = []
    try:
        parent = os.open('/', os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
        fds.append(parent)
        for component in path.parts[1:-1]:
            child = os.open(component, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=parent)
            fds.append(child)
            info = os.fstat(child)
            if info.st_uid not in {0, os.getuid()} or stat.S_IMODE(info.st_mode) & 0o022:
                raise ValueError('HOST_CONFIG_HOLD')
            chain.append((parent, component, child, _identity(info)))
            parent = child
        fd = os.open(path.name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=parent)
        fds.append(fd)
        before = os.fstat(fd)
        if (not stat.S_ISREG(before.st_mode) or before.st_uid != os.getuid()
                or stat.S_IMODE(before.st_mode) != 0o600 or before.st_size > 4096):
            raise ValueError('HOST_CONFIG_HOLD')
        raw = os.read(fd, 4097)
        os.lseek(fd, 0, os.SEEK_SET)
        if raw != os.read(fd, 4097) or len(raw) != before.st_size:
            raise ValueError('HOST_CONFIG_HOLD')
        after = os.fstat(fd)
        if _leaf_identity(before) != _leaf_identity(after):
            raise ValueError('HOST_CONFIG_HOLD')
        if _leaf_identity(os.stat(path.name, dir_fd=parent, follow_symlinks=False)) != _leaf_identity(after):
            raise ValueError('HOST_CONFIG_HOLD')
        for ancestor, component, child, identity in chain:
            if (_identity(os.fstat(child)) != identity
                    or _identity(os.stat(component, dir_fd=ancestor, follow_symlinks=False)) != identity):
                raise ValueError('HOST_CONFIG_HOLD')
        return raw
    except (OSError, TypeError, UnicodeError):
        raise ValueError('HOST_CONFIG_HOLD') from None
    finally:
        for fd in reversed(fds):
            os.close(fd)


def _unique_json(raw):
    def unique(pairs):
        value = {}
        for k, v in pairs:
            if k in value:raise ValueError('HOST_CONFIG_HOLD')
            value[k] = v
        return value
    return json.loads(raw, object_pairs_hook=unique)


def _apply_host_config(probe):
    try:
        raw = _read_private_snapshot(HOST_CONFIG)
        value = _unique_json(raw)
        common = {'schema','profile','generation','resource_uri','document_origin','observation_sha256'}
        schema = value.get('schema') if type(value) is dict else None
        legacy = type(schema) is int and schema == 1
        chain = type(schema) is int and schema == 3
        if (type(value) is not dict
                or set(value) != common | ({'is_top','ancestor_origins'} if legacy else {'frame_ancestors'} if chain else set())
                or type(schema) is not int or schema not in {1,2,3}
                or value['profile'] != ({1:'WCE_INLINE_ZERO_ACCOUNT_HOST_V1',2:'WCE_INLINE_HOST_ORIGIN_V2',3:'WCE_INLINE_FRAME_CHAIN_V3'}[schema])
                or type(value['generation']) is not int or value['generation'] < 0
                or value['resource_uri'] != RESOURCE
                or (legacy and (value['is_top'] is not True or value['ancestor_origins'] != []))):
            raise ValueError('HOST_CONFIG_HOLD')
        origin, evidence = value['document_origin'], value['observation_sha256']
        observed_raw = None
        frames = ()
        if origin is None:
            if evidence is not None or chain:raise ValueError('HOST_CONFIG_HOLD')
            ancestors = ()
        else:
            if (type(origin) is not str or not (origin.startswith('codex-sandbox://')
                    or _registered_app_origin(origin))
                    or type(evidence) is not str or not re.fullmatch('[a-f0-9]{64}', evidence)):
                raise ValueError('HOST_CONFIG_HOLD')
            ancestors = (trusted_origin(origin),)
            frames = ancestors
            observed_raw = _read_private_snapshot(HOST_OBSERVATION)
            if hashlib.sha256(observed_raw).hexdigest() != evidence:
                raise ValueError('HOST_CONFIG_HOLD')
            observed = _unique_json(observed_raw)
            if chain:
                if (type(observed) is not dict or type(observed.get('ancestor_origins')) is not list):
                    raise ValueError('HOST_CONFIG_HOLD')
                actual_chain = [exact_frame_origin(item) for item in observed['ancestor_origins']]
                if type(observed.get('is_top')) is not bool or observed['is_top'] != (not actual_chain):
                    raise ValueError('HOST_CONFIG_HOLD')
                frames = tuple(dict.fromkeys([origin] + actual_chain))
                if type(value['frame_ancestors']) is not list or value['frame_ancestors'] != list(frames):
                    raise ValueError('HOST_CONFIG_HOLD')
            expected_observation = ({'schema':3,'resource_uri':RESOURCE,'document_origin':origin,
                'is_top':observed['is_top'],'ancestor_origins':actual_chain,
                'evidence_kind':'ROOT_CUA_SCRIPT_FRAME_CONTEXT_OBSERVATION'} if chain else
                {'schema':1,'resource_uri':RESOURCE,'document_origin':origin,
                'is_top':True,'ancestor_origins':[],'evidence_kind':'ROOT_CUA_READONLY_OBSERVATION'} if legacy else
                {'schema':2,'resource_uri':RESOURCE,'document_origin':origin,
                 'evidence_kind':'ROOT_CUA_DOCUMENT_ORIGIN_OBSERVATION'})
            if (type(observed) is not dict or type(observed.get('schema')) is not int
                    or observed != expected_observation):
                raise ValueError('HOST_CONFIG_HOLD')
        # Re-read both exact files after semantic checks, before adopting a snapshot.
        if _read_private_snapshot(HOST_CONFIG) != raw:
            raise ValueError('HOST_CONFIG_HOLD')
        if observed_raw is not None and _read_private_snapshot(HOST_OBSERVATION) != observed_raw:
            raise ValueError('HOST_CONFIG_HOLD')
        digest = hashlib.sha256(raw).hexdigest()
        with probe.lock:
            if (value['generation'] < probe.config_generation
                    or (value['generation'] == probe.config_generation and digest != probe.config_digest)):
                raise ValueError('HOST_CONFIG_HOLD')
            if digest != probe.config_digest:
                probe.pending.clear(); probe.sessions.clear()
                probe.config_generation, probe.config_digest = value['generation'], digest
            probe.ancestors = ancestors
            probe.frame_ancestors = frames
    except (OSError, TypeError, KeyError, UnicodeError, ValueError):
        with probe.lock:
            probe.pending.clear(); probe.sessions.clear(); probe.ancestors = (); probe.frame_ancestors = ()
        raise ValueError('HOST_CONFIG_HOLD') from None
