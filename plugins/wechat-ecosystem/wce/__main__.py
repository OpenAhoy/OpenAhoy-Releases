"""Run with python3 -m wce. This is an offline CLI, not a registered MCP server."""
import argparse
import json
from pathlib import Path
from tempfile import TemporaryDirectory

from .contracts import WCEError
from .demo import ACTORS, seed, workflow, seed_lifecycle, lifecycle_workflow
from .draft_fixture import DraftFixtureAdapter
from .mock import MockOfficialAccountAdapter
from .service import OfficialAccountService
from .tools import ToolRouter, list_tools


def main():
    parser = argparse.ArgumentParser(description="WCE offline Official Account candidate")
    parser.add_argument("--mode", choices=["offline", "fixture"], default="offline",
                        help="Trusted local startup selection; fixture is test-only and has no live mode")
    parser.add_argument("--db", help="Explicit local SQLite state path; adapter files are separate and adjacent")
    parser.add_argument("--session", choices=list(ACTORS), default="demo-session-a",
                        help="Synthetic identity selection, not production authentication")
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("tools")
    commands.add_parser("init-demo")
    commands.add_parser("init-lifecycle", help="Trusted synthetic two-account binding per user; empty state only")
    commands.add_parser("lifecycle-demo", help="Trusted synthetic lifecycle demonstration; empty state only")
    commands.add_parser("demo")
    call = commands.add_parser("call")
    call.add_argument("name")
    call.add_argument("arguments", help="JSON tool arguments; cannot contain identity or approval fields")
    approve = commands.add_parser("approve", help="Trusted local operator approves the displayed exact binding")
    approve.add_argument("intent_id")
    approve.add_argument("binding")
    asset = commands.add_parser("local-asset", help="Trusted local file acquisition; no platform upload")
    asset.add_argument("connection_id")
    asset.add_argument("root", help="Explicit absolute nonsymlink local sample root")
    asset.add_argument("relative_path")
    asset.add_argument("role", choices=["cover", "body"])
    asset.add_argument("declared_type", choices=["image/png", "image/jpeg"])
    prepare = commands.add_parser("local-prepare", help="Trusted immutable news input; JSON contains asset refs, never paths")
    prepare.add_argument("connection_id")
    prepare.add_argument("article", help="Internal structured article JSON")
    prepare.add_argument("--bundle-id")
    prepare.add_argument("--expected-version")
    read = commands.add_parser("local-read", help="Verify actual frozen bytes and return static input metadata")
    read.add_argument("connection_id")
    read.add_argument("bundle_id")
    read.add_argument("version")
    args = parser.parse_args()
    errors = {"transport": "mock", "mode": "test", "runtime": "offline",
              "connected": False, "platform_verified": False}
    if args.mode == "fixture":
        errors |= {"mode": "test", "runtime": "wire_fixture", "connected": False, "platform_verified": False}

    def run(path):
        adapter = (DraftFixtureAdapter(str(path) + ".fixture.sqlite3", str(path) + ".fixture-http.sqlite3")
                   if args.mode == "fixture" else MockOfficialAccountAdapter(str(path) + ".mock.sqlite3"))
        service = OfficialAccountService(path, adapter)
        actor = ACTORS[args.session]
        router = ToolRouter(service, actor)
        if args.command == "local-asset":
            from .bounded_file import FileSource
            return service.local.accept_asset(actor, args.connection_id, FileSource(args.root),
                                              args.relative_path, args.role, args.declared_type)
        if args.command == "local-prepare":
            return service.local.prepare(actor, args.connection_id, json.loads(args.article),
                                         args.bundle_id, args.expected_version)
        if args.command == "local-read":
            return service.local.read_bundle(actor, args.connection_id, args.bundle_id, args.version)
        if args.command == "init-lifecycle":
            seed_lifecycle(service)
            return router.call("connections.list", {})
        if args.command == "lifecycle-demo":
            return lifecycle_workflow(service)
        if args.command == "init-demo":
            seed(service)
            return {"transport": "mock", "connections": ["oa-a", "oa-a-second", "oa-b"], "sessions": list(ACTORS), "platform_verified": False} | router.evidence()
        if args.command == "demo":
            return workflow(service) | router.evidence()
        if args.command == "approve":
            return service.confirm_action(actor, args.intent_id, args.binding) | router.evidence()
        return router.call(args.name, json.loads(args.arguments))

    try:
        if args.command == "tools":
            result = {"entrypoint": "offline_cli_candidate", "mcp_registered": False, "tools": list_tools()}
            if args.mode == "fixture":
                result |= errors | {"entrypoint": "wire_fixture_cli_candidate"}
        elif args.db:
            result = run(Path(args.db))
        elif args.command in {"demo", "lifecycle-demo"}:
            with TemporaryDirectory(prefix="wce-offline-") as directory:
                result = run(Path(directory) / "state.sqlite3")
        else:
            raise WCEError("EXPLICIT_DB_PATH_REQUIRED")
        print(json.dumps(result, ensure_ascii=False, allow_nan=False))
        return 0
    except WCEError as error:
        print(json.dumps({"error": error.code} | errors))
        return 1
    except (ValueError, TypeError):
        print(json.dumps({"error": "INVALID_REQUEST_OR_STATE"} | errors))
        return 1
    except Exception:
        print(json.dumps({"error": "INTERNAL_ERROR"} | errors))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
