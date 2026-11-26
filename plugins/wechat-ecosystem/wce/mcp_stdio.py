"""MCP 2025-11-25 stdio subset; offline tools only, no client registration."""
import argparse
import json
from pathlib import Path
import sys
from threading import Lock
from tempfile import TemporaryDirectory
import time

from .contracts import WCEError
from .demo import ACTORS, seed
from .draft_fixture import DraftFixtureAdapter
from .mock import MockOfficialAccountAdapter
from .service import OfficialAccountService
from .tools import ToolRouter

VERSION = "2025-11-25"
MAX_FRAME = 1024 * 1024


def _normal_html_frame(message):
    """Only a typed normal document may use the derived content envelope."""
    try:
        from .normal_html_limits import POLICY
        from .own_connection_tools import validate
        if (type(message) is not dict or set(message)!={'jsonrpc','id','method','params'}
                or message['jsonrpc']!='2.0' or message['method']!='tools/call'
                or type(message['id']) not in (str,int)):
            return False
        params=message['params']
        if (type(params) is not dict or set(params) not in ({'name','arguments'},{'name','arguments','_meta'})
                or params['name']!='own.documents.prepare'):
            return False
        if '_meta' in params and (type(params['_meta']) is not dict
                or len(json.dumps(params['_meta'],ensure_ascii=False,allow_nan=False).encode())>MAX_FRAME):
            return False
        args=params['arguments'];validate('own.documents.prepare',args)
        return (type(args) is dict and type(args.get('document')) is dict
                and args['document'].get('policy')==POLICY)
    except (WCEError,ValueError,TypeError,KeyError,UnicodeError):
        return False


class RPCError(Exception):
    def __init__(self, code, message):
        self.code, self.message = code, message


class StdioServer:
    def __init__(self, router, clock=time.monotonic):
        self.router = router
        self.initialized = False
        self.ready = False
        self.clock = clock
        self.tokens, self.updated = 60.0, clock()

    def _charge(self, now):
        """Legacy/offline frontend protection; personal STDIO overrides it."""
        self.tokens=min(60,self.tokens+max(0,now-self.updated)*5)
        self.updated=now
        if self.tokens<1:raise RPCError(-32001,"Rate limit exceeded")
        self.tokens-=1

    def _tool_available(self, name, arguments):
        return name in {item["name"] for item in self.router.list_tools()}

    def _listed_tools(self):
        return self.router.list_tools()

    def dispatch(self, message):
        request_id = None
        notification = False
        try:
            if not isinstance(message, dict) or message.get("jsonrpc") != "2.0" or not isinstance(message.get("method"), str):
                raise RPCError(-32600, "Invalid Request")
            notification = "id" not in message
            if not notification:
                request_id = message["id"]
                if isinstance(request_id, bool) or not isinstance(request_id, (str, int)):
                    request_id = None
                    raise RPCError(-32600, "Invalid Request")
            params = message.get("params", {})
            if not isinstance(params, dict):
                raise RPCError(-32602, "Invalid params")
            if "_meta" in params and not isinstance(params["_meta"], dict):
                raise RPCError(-32602, "Invalid params")
            params = {key: value for key, value in params.items() if key != "_meta"}
            method = message["method"]
            # Notifications cannot invoke request methods or create side effects.
            if notification:
                if method == "notifications/initialized" and self.initialized and not params:
                    self.ready = True
                return None
            now = self.clock()
            self._charge(now)
            if method == "ping":
                if params:
                    raise RPCError(-32602, "Invalid params")
                result = {}
            elif method == "initialize":
                if self.initialized:
                    raise RPCError(-32600, "Already initialized")
                if not isinstance(params.get("protocolVersion"), str) or not isinstance(params.get("capabilities"), dict) or not isinstance(params.get("clientInfo"), dict):
                    raise RPCError(-32602, "Invalid params")
                info = params["clientInfo"]
                if not isinstance(info.get("name"), str) or not isinstance(info.get("version"), str):
                    raise RPCError(-32602, "Invalid params")
                self.initialized = True
                result = {"protocolVersion": VERSION, "capabilities": {"tools": {}},
                          "serverInfo": {"name": "wce-offline", "version": "0.2.0-protocol-candidate"},
                          "instructions": "Synthetic offline account tools. No real WeChat API. Approval must come from a separate trusted operator; no approval tool is exposed."}
                if self.router.evidence().get("runtime") == "wire_fixture":
                    result["serverInfo"]["name"] = "wce-wire-fixture"
                    result["instructions"] = "Test-only synthetic draft wire fixture. connected=false; platform_verified=false. No real API or live switch."
                if self.router.prepared is not None:
                    result["instructions"] += (" Prepared local workflow: select connection; receive scoped images with original keys; "
                        "prepare news using returned asset refs; retain returned bundle/version/digest; upload each slot; save; "
                        "query status and independently readback. Response loss: query the original key. UNKNOWN: no resend or new key. "
                        "Images require an operator-configured dedicated directory. No real GPT/WeChat connection, publication or approval tool.")
                if getattr(self.router, 'own', None) is not None:
                    result['serverInfo']['name'] = 'wce-own-account-preparation'
                    result['instructions'] += (' Own account path is unconfigured by default. Run own.preflight; '
                        'trusted operator setup and exact once-only trial approval are separate. '
                        'Synthetic wire results never verify a real account. UNKNOWN: status only, never resend.')
            elif not self.ready:
                raise RPCError(-32002, "Server not initialized")
            elif method in {'resources/list', 'resources/read'} and hasattr(self, 'resource'):
                result = self.resource(method, params)
            elif method == "tools/list":
                if params:
                    raise RPCError(-32602, "Invalid params")
                result = {"tools": self._listed_tools()}
            elif method == "tools/call":
                if set(params) - {"name", "arguments", "_meta"} or not isinstance(params.get("name"), str) or not isinstance(params.get("arguments", {}), dict):
                    raise RPCError(-32602, "Invalid params")
                if not self._tool_available(params["name"], params.get("arguments", {})):
                    raise RPCError(-32602, "Unknown tool")
                if params["name"] == "own.drafts.locate":
                    try:
                        id_bytes = json.dumps(request_id, ensure_ascii=False, allow_nan=False).encode("utf-8")
                    except (ValueError, TypeError, UnicodeError):
                        id_bytes = b''
                    if not id_bytes or len(id_bytes) > 4096:
                        request_id = None
                        raise RPCError(-32600, "Invalid Request")
                try:
                    result = self.tool_result(params["name"], params.get("arguments", {}))
                except WCEError as error:
                    result = {"content": [{"type": "text", "text": error.code}], "isError": True}
                    from .document_errors import location
                    where = location(error)
                    if where:
                        result["content"][0]["text"] = error.code + " " + json.dumps(where, sort_keys=True)
                    if self.router.evidence() or where:
                        result["structuredContent"] = {"error": error.code} | self.router.evidence() | where
            else:
                raise RPCError(-32601, "Method not found")
            return {"jsonrpc": "2.0", "id": request_id, "result": result}
        except RPCError as error:
            if notification:
                return None
            return {"jsonrpc": "2.0", "id": request_id, "error": {"code": error.code, "message": error.message}}
        except Exception:
            if notification:
                return None
            return {"jsonrpc": "2.0", "id": request_id, "error": {"code": -32603, "message": "Internal error"}}

    def tool_result(self,name,arguments):
        value=self.router.call(name,arguments)
        return {"content":[{"type":"text","text":json.dumps(value,ensure_ascii=False,allow_nan=False)}],
                "structuredContent":value,"isError":False}

    def handle_frame(self, message, send):
        return self.dispatch(message)

    def serve(self, source, destination):
        write_lock = Lock()

        def send(response):
            with write_lock:
                destination.write((json.dumps(response, ensure_ascii=False, allow_nan=False) + "\n").encode("utf-8"))
                destination.flush()

        def unique(pairs):
            value = {}
            for key, item in pairs:
                if key in value:
                    raise ValueError("duplicate key")
                value[key] = item
            return value
        from .normal_html_limits import ENVELOPE_BYTES
        while True:
            frame = source.readline(ENVELOPE_BYTES + 1)
            if not frame:return
            if len(frame)>ENVELOPE_BYTES:
                while frame and not frame.endswith(b"\n"):
                    frame=source.readline(MAX_FRAME+1)
                response={"jsonrpc":"2.0","id":None,"error":{"code":-32600,"message":"Frame too large"}}
            else:
                try:
                    message=json.loads(frame.decode("utf-8"),object_pairs_hook=unique,
                        parse_constant=lambda _: (_ for _ in ()).throw(ValueError()))
                except (ValueError,UnicodeError,RecursionError):
                    response={"jsonrpc":"2.0","id":None,"error":{
                        "code":-32600 if len(frame)>MAX_FRAME else -32700,
                        "message":"Frame too large" if len(frame)>MAX_FRAME else "Parse error"}}
                else:
                    from .own_configuration_export import content_frame as configuration_frame
                    if len(frame)>MAX_FRAME and not (_normal_html_frame(message) or configuration_frame(message, MAX_FRAME)):
                        response={"jsonrpc":"2.0","id":None,"error":{"code":-32600,"message":"Frame too large"}}
                    else:response=self.handle_frame(message, send)
            if response is not None:
                send(response)


def main():
    parser = argparse.ArgumentParser(description="WCE MCP stdio, local test only")
    parser.add_argument("--mode", choices=["offline", "fixture"], default="offline")
    parser.add_argument("--db", help="Existing seeded offline state; otherwise use temporary demo state")
    parser.add_argument("--session", choices=list(ACTORS), default="demo-session-a")
    parser.add_argument("--prepared", action="store_true", help="Enable the local prepared namespace; not installation")
    parser.add_argument("--image-root", help="Operator-selected dedicated image directory; no default")
    parser.add_argument("--image-connection", help="Explicit source-grant connection for the selected session")
    args = parser.parse_args()
    if bool(args.image_root) != bool(args.image_connection) or (args.image_root and not args.prepared):
        parser.error("Image root and connection must be paired with --prepared")
    def run(path, initialize=False):
        adapter = (DraftFixtureAdapter(str(path) + ".fixture.sqlite3", str(path) + ".fixture-http.sqlite3")
                   if args.mode == "fixture" else MockOfficialAccountAdapter(str(path) + ".mock.sqlite3"))
        service = OfficialAccountService(path, adapter)
        if initialize:
            seed(service)
        prepared = None
        if args.prepared:
            from .prepared_host import HostDraftWorkflow, ScopedImageDirectory
            actor = ACTORS[args.session]
            directory = None
            if args.image_root:
                with service.db.transaction() as db:
                    binding, _ = service.local._guard(db, actor, args.image_connection)
                directory = ScopedImageDirectory(args.image_root, actor, args.image_connection, binding["resource"])
            prepared = HostDraftWorkflow(service, image_directory=directory)
        StdioServer(ToolRouter(service, ACTORS[args.session], prepared)).serve(sys.stdin.buffer, sys.stdout.buffer)
    try:
        if args.db:
            run(Path(args.db))
        else:
            with TemporaryDirectory(prefix="wce-mcp-offline-") as tmp:
                run(Path(tmp) / "state.sqlite3", True)
        return 0
    except (Exception, KeyboardInterrupt):
        print("WCE stdio stopped", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
