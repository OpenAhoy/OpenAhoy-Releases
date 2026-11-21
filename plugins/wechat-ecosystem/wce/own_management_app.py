"""Real embedded management, using the original same-origin human form.

The MCP shell carries only a sealed UI capability. Account fields and secrets
stay inside the loopback child and never enter the parent RPC protocol.
"""
from html import escape
import json
import secrets
import threading
from types import SimpleNamespace

from .contracts import WCEError
from .own_settings_http import LimitedServer, SettingsHandler, SettingsSession
from .own_inline_probe import RESOURCE, MIME, _apply_host_config


_SEAL = object()


class UIResult:
    __slots__ = ('metadata', 'seal')

    def __init__(self, metadata, seal):
        if seal is not _SEAL:
            raise ValueError('MANAGEMENT_RESULT_HOLD')
        self.metadata, self.seal = metadata, seal


def take_metadata(value):
    if type(value) is not UIResult or value.seal is not _SEAL:
        raise ValueError('MANAGEMENT_RESULT_HOLD')
    result = value.metadata
    value.metadata = value.seal = None
    return result


SHELL_STYLE = '''html,body{margin:0;min-height:100%;background:#f6f6f7;color:#68717d;
font:12px/1.5 -apple-system,BlinkMacSystemFont,"PingFang SC",sans-serif}
.shell-tools{display:flex;justify-content:space-between;align-items:center;gap:12px;padding:8px 14px}
button{border:1px solid #e4e6eb;border-radius:9px;background:#fafafa;color:#424a56;
padding:6px 10px;font:500 12px/1.5 -apple-system,BlinkMacSystemFont,"PingFang SC",sans-serif;cursor:pointer;white-space:nowrap}
button:focus-visible{outline:2px solid #4c78c7;outline-offset:2px}
iframe{display:block;width:100%;height:calc(100vh - 48px);min-height:540px;border:0}
details{padding:0 14px 8px;font-size:11px}pre{white-space:pre-wrap;overflow-wrap:anywhere}
'''

SHELL_SCRIPT = r'''
(() => {
 'use strict';
 let counter=0, disposed=false, busy=false, bridgeReady=false;
 const bridge=window.parent;
 let initializeOrigin='UNAVAILABLE', phase='INITIALIZING', policyDirective=null;
 const pending=new Map(), status=document.getElementById('status');
 let frame=document.getElementById('frame');
 const originOnly=value=>{
   if(value==='null')return 'OPAQUE';
   if(typeof value!=='string'||value.length>512||!/^[-a-z0-9+.]+:\/\/[^/?#\s@]+$/i.test(value))return 'UNAVAILABLE';
   return value;
 };
 const context=()=>{
   let ancestors=null;
   try{if('ancestorOrigins' in location)ancestors=Array.from(location.ancestorOrigins,originOnly);}catch(_){}
   const networkPolicy={};
   const policy=document.permissionsPolicy||document.featurePolicy;
   for(const feature of ['local-network-access','local-network','loopback-network']){
     let current=null,child=null;
     try{if(policy?.features().includes(feature)){
       current=policy.allowsFeature(feature);child=policy.allowsFeature(feature,EXPECTED_ORIGIN);}}
     catch(_){}
     networkPolicy[feature]={current,child};
   }
   document.getElementById('frameContext').textContent=JSON.stringify({schema:1,
     documentOrigin:originOnly(location.origin),isTop:window.top===window.self,ancestorOrigins:ancestors,
     matchedInitializeMessageOrigin:initializeOrigin,bridgeReady,networkPolicy,phase,policyDirective},null,2);
 };
 addEventListener('securitypolicyviolation',event=>{
   if(['frame-src','child-src','frame-ancestors','default-src'].includes(event.effectiveDirective)){
     policyDirective=event.effectiveDirective;context();}
 });
 context();
 const send=(method,params)=>new Promise((resolve,reject)=>{
   if(disposed){reject(new Error('VIEW_CLOSED'));return;}
   const id=++counter, timer=setTimeout(()=>{pending.delete(id);reject(new Error('HOST_TIMEOUT'));},15000);
   pending.set(id,{resolve,reject,timer,method});bridge.postMessage({jsonrpc:'2.0',id,method,params},'*');
 });
 addEventListener('message',event=>{
   // The child is deliberately excluded: no account or credential messages.
   if(event.source!==bridge||!event.data||event.data.jsonrpc!=='2.0')return;
   const value=event.data, item=pending.get(value.id);if(!item)return;
   clearTimeout(item.timer);pending.delete(value.id);
   if(value.method||value.error||!Object.hasOwn(value,'result'))item.reject(new Error('HOST_ERROR'));
   else {if(item.method==='ui/initialize')initializeOrigin=originOnly(event.origin);item.resolve(value.result);}
 });
 async function open(){
   if(disposed||busy||!bridgeReady)return;busy=true;document.getElementById('retry').disabled=true;
   status.textContent='正在打开公众号管理…';
   phase='OPEN_REQUEST';policyDirective=null;context();
   try{
     const result=await send('tools/call',{name:'wce.settings.open',arguments:{}});
     const meta=result?._meta?.openahoyManagement;
     if(result?.isError)throw new Error('HOST_OPEN_REFUSED');
     if(result?.structuredContent?.state!=='SETTINGS_OPENED'||!meta)throw new Error('UI_METADATA_MISSING');
     if(meta.origin!==EXPECTED_ORIGIN)throw new Error('RESOURCE_ORIGIN_CHANGED');
     if(meta.processGeneration!==EXPECTED_GENERATION)throw new Error('RESOURCE_GENERATION_CHANGED');
     if(location.origin!==meta.trustedAppOrigin)throw new Error('APP_ORIGIN_MISMATCH');
     // MCP Apps normally run in a host frame. The child response's exact
     // frame-ancestors CSP checks every ancestor; top-level is not authority.
     const url=new URL(meta.url);
     if(url.origin!==EXPECTED_ORIGIN||url.pathname!=='/'||url.search||!/^#[A-Za-z0-9_-]{43}$/.test(url.hash))throw new Error('UI_URL_REJECTED');
     const replacement=frame.cloneNode(false);replacement.removeAttribute('src');frame.replaceWith(replacement);frame=replacement;
     frame.addEventListener('load',()=>{phase='FRAME_LOAD_EVENT_NOT_READINESS';context();});
     frame.src=url.href;status.textContent='公众号管理';
     phase='FRAME_REQUESTED';context();
   }catch(error){
     const labels={HOST_OPEN_REFUSED:'管理工具未能打开页面',UI_METADATA_MISSING:'未收到页面专用返回',
       RESOURCE_ORIGIN_CHANGED:'页面缓存的服务地址已改变',RESOURCE_GENERATION_CHANGED:'页面缓存的服务实例已改变',
       APP_ORIGIN_MISMATCH:'当前管理页来源与已核对来源不一致',
       UI_URL_REJECTED:'页面专用地址校验未通过',HOST_TIMEOUT:'管理工具响应超时',HOST_ERROR:'管理工具桥返回错误'};
     const code=Object.hasOwn(labels,error?.message)?error.message:'MANAGEMENT_VIEW_FAILED';
     status.textContent=(labels[code]||'管理页未能打开')+'（'+code+'）。可重新打开；已有账号操作不会自动重试。';
     phase=code;context();
   }
   finally{busy=false;if(!disposed)document.getElementById('retry').disabled=false;}
 }
 // Display-only empty open, same as initial mounting; never submits an account form.
 document.getElementById('retry').addEventListener('click',()=>open());
 addEventListener('pagehide',()=>{disposed=true;frame.removeAttribute('src');
   for(const item of pending.values()){clearTimeout(item.timer);item.reject(new Error('VIEW_CLOSED'));}pending.clear();});
 send('ui/initialize',{appInfo:{name:'openahoy-management',version:'0.4.96'},
   appCapabilities:{availableDisplayModes:['inline','fullscreen']},protocolVersion:'2026-01-26'})
 .then(host=>{
   if(disposed||host?.protocolVersion!=='2026-01-26'||!host.hostCapabilities?.serverTools)throw new Error('NO_SERVER_TOOLS');
   bridgeReady=true;
   bridge.postMessage({jsonrpc:'2.0',method:'ui/notifications/initialized'},'*');return open();
 }).catch(()=>{status.textContent='当前宿主尚未提供管理工具桥。';});
})();
'''


class ManagementApp:
    def __init__(self, router, *, backend_factory=None, trusted_ancestors=None):
        self.router, self.backend_factory = router, backend_factory
        self.lock = threading.RLock()
        self.trust = SimpleNamespace(lock=threading.RLock(), config_generation=-1,
            config_digest=None, ancestors=(), frame_ancestors=(), pending={}, sessions={})
        # Explicit fixture injection; never populated from an MCP argument/env.
        self.fixture_ancestors = trusted_ancestors
        self.generation = secrets.token_hex(16)
        self.server = self.thread = self.session = None
        self.closed = False

    def _trust(self):
        if self.fixture_ancestors is None:
            _apply_host_config(self.trust)
        else:
            from .own_inline_probe import trusted_origin
            self.trust.ancestors = tuple(trusted_origin(x) for x in self.fixture_ancestors)
            self.trust.config_generation = 0
            self.trust.config_digest = 'fixture'
        with self.trust.lock:
            if len(self.trust.ancestors) != 1:
                raise WCEError('SETTINGS_INLINE_HOST_HOLD')
            frames = self.trust.frame_ancestors or self.trust.ancestors
            return (self.trust.config_generation, self.trust.config_digest, self.trust.ancestors, frames)

    def _guard(self, expected):
        # Called inside backend admission too: do not take the lifecycle lock
        # or close sessions here. The expiry worker owns deferred closure.
        try:
            if self._trust() != expected:
                raise ValueError('HOST_CHANGED')
        except (ValueError, WCEError):
            raise WCEError('SETTINGS_EXPIRED') from None

    def _listener(self):
        if self.closed:
            raise WCEError('SETTINGS_EXPIRED')
        if self.server is None:
            self.server = LimitedServer(('127.0.0.1', 0), SettingsHandler)
            self.server.settings = None
            self.thread = threading.Thread(target=self.server.serve_forever,
                daemon=True, name='openahoy-management-http')
            self.thread.start()
        return 'http://127.0.0.1:' + str(self.server.server_port)

    def start(self):
        from .own_settings_backend import SettingsBackend
        from .own_settings_ui import PAGE, CSP
        with self.lock:
            try:
                pins = self._trust()
            except ValueError:
                raise WCEError('SETTINGS_INLINE_HOST_HOLD') from None
            origin = self._listener()
            if self.session is not None:
                with self.session.lock, self.session.backend.lock:
                    backend = self.session.backend
                    if (backend.state == 'ACTIVE' or backend.review is not None
                            or backend.pending_recovery is not None or backend.pending_publication is not None
                            or backend.navigation_pending
                            or (backend.state == 'RESULT' and backend.result.get('state') not in {
                                'BOUND_IDLE','UPGRADED','DISCONNECTED','TOKEN_CHECK_SUCCEEDED'})):
                        raise WCEError('SETTINGS_BUSY')
                    self.session.close()
            backend = (self.backend_factory() if self.backend_factory else
                SettingsBackend(self.router.registry, base_only=True))
            csp = CSP.replace("frame-ancestors 'none'", 'frame-ancestors ' + ' '.join(pins[3]))
            self.session = SettingsSession(backend, PAGE, csp, shared_server=self.server,
                embedding_guard=lambda: self._guard(pins))
            self.server.settings = self.session
            return UIResult({'openahoyManagement': {'origin': origin,
                'processGeneration': self.generation, 'trustedAppOrigin': pins[2][0],
                'url': origin + '/#' + self.session.bootstrap}}, _SEAL)

    def resource(self):
        with self.lock:
            origin = self._listener()
            script = ('const EXPECTED_ORIGIN=' + json.dumps(origin) + ';\n'
                + 'const EXPECTED_GENERATION=' + json.dumps(self.generation) + ';\n' + SHELL_SCRIPT)
            html = ('<!doctype html><html lang="zh-CN"><meta charset="utf-8">'
                '<meta name="viewport" content="width=device-width,initial-scale=1">'
                '<title>Jiusera · 公众号管理</title><style>' + SHELL_STYLE + '</style>'
                '<body><div class="shell-tools"><span id="status" role="status">正在连接管理工具…</span>'
                '<button id="retry">重新打开管理页</button></div>'
                '<details><summary>页面加载信息</summary><pre id="frameContext"></pre></details>'
                '<iframe id="frame" title="Jiusera 公众号管理" '
                'sandbox="allow-scripts allow-same-origin allow-popups" referrerpolicy="no-referrer"></iframe>'
                '<script>' + script + '</script></body></html>')
            return {'contents': [{'uri': RESOURCE, 'mimeType': MIME, 'text': html,
                '_meta': {'ui': {'csp': {'connectDomains': [], 'resourceDomains': [],
                    'frameDomains': [origin]}}, 'openai/ui': {
                    'availableDisplayModes': ['inline','fullscreen'], 'preferredDisplayMode':'inline'}}}]}

    def close(self):
        with self.lock:
            self.closed = True
            session, server, thread = self.session, self.server, self.thread
            self.session = self.server = self.thread = None
        if session is not None:
            session.close()
        if server is not None:
            server.shutdown(); server.server_close()
        if thread is not None:
            thread.join(timeout=5)
