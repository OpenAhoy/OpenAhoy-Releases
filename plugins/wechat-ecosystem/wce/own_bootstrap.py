"""Runnable local own-account bootstrap. Installation and live testing are separate."""
import argparse
import json
import os
import socket
import sys

from .contracts import WCEError
from .mcp_stdio import StdioServer
from .own_bootstrap_ipc import peer, receive, runtime_read, send, socket_pin
from .own_bootstrap_security import FLAGS, load_config, path_check
from .own_contracts import list_tools, validate
from .own_operator import operator


class Bridge:
    """No management RPC. Scope is fixed by the human-owned config/runtime."""
    prepared = None
    own = True

    def __init__(self, config):
        self.config, self.seq = config, 0
        self.info, self.info_pin = runtime_read(config)
        self.socket_path = config.root / 'operator.sock'
        self.endpoint_pin = socket_pin(self.socket_path)
        self.connection = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        self.connection.settimeout(20)
        self.stream = None
        try:
            self.connection.connect(str(self.socket_path))
            pid, uid = peer(self.connection)
            if pid != self.info['pid'] or uid != os.getuid():
                raise WCEError('BOOTSTRAP_PEER_DENIED')
            self.check()
            self.stream = self.connection.makefile('rwb')
        except Exception:
            self.close()
            raise WCEError('BOOTSTRAP_BRIDGE_UNAVAILABLE') from None

    def check(self):
        self.config.check()
        if (path_check(self.config.root / 'runtime.json') != self.info_pin
                or socket_pin(self.socket_path) != self.endpoint_pin):
            raise WCEError('BOOTSTRAP_ENDPOINT_CHANGED')

    def evidence(self):
        return FLAGS | {'runtime': 'own_account_operator_preparation'}

    def list_tools(self):
        return list_tools()

    def call(self, name, arguments):
        validate(name, arguments)
        self.check()
        self.seq += 1
        frame = {k: v for k, v in self.info.items() if k != 'pid'}
        frame |= {'seq': self.seq, 'name': name, 'arguments': arguments}
        try:
            send(self.stream, frame)
            reply = receive(self.stream)
            self.check()
            if type(reply) is not dict or type(reply.get('ok')) is not bool:
                raise ValueError()
            if reply['ok']:
                if set(reply) != {'ok', 'value'} or type(reply['value']) is not dict:
                    raise ValueError()
                if any(reply['value'].get(k) is not False for k in FLAGS):
                    raise ValueError()
                return reply['value']
            if (set(reply) != {'ok', 'error'} or type(reply['error']) is not str
                    or not reply['error'].replace('_', '').isalnum() or len(reply['error']) > 96):
                raise ValueError()
            raise WCEError(reply['error'])
        except WCEError:
            raise
        except Exception:
            self.close()
            raise WCEError('BOOTSTRAP_IPC_RESULT_UNKNOWN') from None

    def close(self):
        if self.stream is not None:
            self.stream.close()
            self.stream = None
        self.connection.close()


def preflight(config_path=None):
    result = FLAGS | {'runtime': 'own_account_operator_preparation', 'configured': False,
                     'missing': ['explicit_nonsecret_config', 'human_account_evidence', 'memory_lease',
                                 'exact_article_and_trial_approval']}
    if config_path is not None:
        config = load_config(config_path)
        result |= {'configured': True, 'target': {'account': config.data['appid'],
                    'resource': config.data['resource_id'], 'connection': config.data['connection_id'],
                    'actor': vars(config.actor), 'generation': config.data['generation'], 'epoch': config.data['epoch']},
                   'missing': ['human_account_evidence', 'memory_lease', 'exact_article_and_trial_approval']}
    return result


class OperatorStdioServer(StdioServer):
    def dispatch(self, message):
        reply = super().dispatch(message)
        if (type(message) is dict and message.get('method') == 'initialize'
                and reply is not None and 'result' in reply):
            result = reply['result']
            result['serverInfo'] = {'name': 'wce-own-account-operator', 'version': '0.1.0-local-preparation'}
            result['instructions'] = (
                'Local own-account operator path. Valid human configuration and scoped memory lease '
                'can execute the official WeChat image and draft APIs. Missing conditions deny execution. '
                'Inspect and exact once-only draft approval are separate human TTY actions; no approval '
                'or credential tool is exposed. connected=false, platform_ready=false and '
                'platform_verified=false describe unverified platform acceptance. Synthetic results '
                'cannot verify a real account. UNKNOWN: query the original key; never resend or use a new key.')
        return reply


def bridge(config_path):
    router = Bridge(load_config(config_path))
    try:
        OperatorStdioServer(router).serve(sys.stdin.buffer, sys.stdout.buffer)
    finally:
        router.close()


def main():
    parser = argparse.ArgumentParser(description='Own account local operator; no platform verification claim')
    parser.add_argument('mode', nargs='?', choices=['preflight', 'operator', 'bridge'], default='preflight')
    parser.add_argument('--config', help='Explicit absolute private nonsecret profile.json')
    parser.add_argument('--review-request', help='Optional private review.json; human operator mode only')
    parser.add_argument('--keychain', action='store_true', help='Host-only: remember this connection credential in macOS Keychain')
    args = parser.parse_args()
    try:
        if args.review_request is not None and args.mode != 'operator':
            raise WCEError('BOOTSTRAP_REVIEW_UNAVAILABLE')
        if args.keychain and args.mode != 'operator':
            raise WCEError('BOOTSTRAP_KEYCHAIN_UNAVAILABLE')
        if args.mode == 'preflight':
            print(json.dumps(preflight(args.config), ensure_ascii=False, allow_nan=False))
            return 0 if args.config else 1
        if not args.config:
            raise WCEError('BOOTSTRAP_CONFIG_REQUIRED')
        if args.mode == 'operator':
            operator(args.config, review_request=args.review_request, keychain=args.keychain)
        else:
            bridge(args.config)
        return 0
    except WCEError as error:
        print(error.code, file=sys.stderr)
        return 1
    except (Exception, KeyboardInterrupt, EOFError):
        print('BOOTSTRAP_STOPPED', file=sys.stderr)
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
