"""Unconfigured own-account STDIO entry. No secret/profile config reader."""
import argparse
import json
import sys

from .contracts import Actor, WCEError
from .mcp_stdio import StdioServer
from .own_contracts import list_tools, validate
from .own_workflow import OwnWorkflow
from .tools import ToolRouter


class OwnRouter:
    def __init__(self, actor, workflow, legacy=None):
        if type(actor) is not Actor or type(workflow) is not OwnWorkflow:
            raise WCEError('OWN_UNCONFIGURED')
        if legacy is not None and (type(legacy) is not ToolRouter or legacy.actor != actor):
            raise WCEError('OWN_UNCONFIGURED')
        self.actor, self.own, self.legacy = actor, workflow, legacy
        self.prepared = getattr(legacy, 'prepared', None)

    def list_tools(self):
        return ([] if self.legacy is None else self._legacy().list_tools()) + list_tools()

    def _legacy(self):
        if type(self.legacy) is not ToolRouter or self.legacy.actor != self.actor:
            raise WCEError('OWN_UNCONFIGURED')
        return self.legacy

    def evidence(self):
        return self.own.evidence()

    def call(self, name, arguments):
        if name.startswith('own.'):
            validate(name, arguments)
            return self.own.call(self.actor, name, arguments)
        if self.legacy is None:
            raise WCEError('TOOL_NOT_IMPLEMENTED')
        result = self._legacy().call(name, arguments)
        self._legacy()
        return result


def main():
    parser = argparse.ArgumentParser(description='WCE own account preparation; unconfigured, no live switch')
    parser.add_argument('--preflight', action='store_true', help='Print nonsecret missing conditions and exit')
    args = parser.parse_args()
    workflow = OwnWorkflow()
    actor = Actor('unconfigured', 'unconfigured', 'unconfigured', 'unconfigured')
    if args.preflight:
        print(json.dumps(workflow.call(actor, 'own.preflight', {}), ensure_ascii=False))
    else:
        StdioServer(OwnRouter(actor, workflow)).serve(sys.stdin.buffer, sys.stdout.buffer)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
