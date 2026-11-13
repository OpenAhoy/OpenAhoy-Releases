"""One human TTY enablement for the installed personal connection policy."""
import argparse
from hashlib import sha256
import json
from pathlib import Path
import secrets
import sys

from .contracts import WCEError
from .own_connection_policy import proposal, enable, load_policy
from .own_connection_broker import Broker, AccountService


def review(profile, source, output):
    if not source.isatty() or not output.isatty():
        raise WCEError('CONNECTION_HUMAN_TTY_REQUIRED')
    value = proposal(profile)
    output.write('WCE 个人公众号持续连接\n'
        '本次仅启用当前账号与当前插件版本，持续到你主动断开。\n'
        '宿主沿用同一系统钥匙串条目，按微信有效期自动取得短期 token；不在聊天输入密钥。\n'
        '启用后允许你在 Codex 明确请求的图片上传、草稿保存与读取；每篇仍绑定账号、内容版本和原请求键。\n'
        '这项持续委托替代新稿逐次终端确认。公开发布、群发及旧未知请求重发均不包含。\n'
        '旧稿、已用恢复次数和未知记录保留；关闭客户端后绑定保留，broker 闲置后退出、下次按需启动。\n'
        '你可以随时要求插件断开；断开不删除钥匙串，也不撤回已发出的请求。\n')
    # json escaping prevents identity text from becoming terminal control syntax.
    scope = sha256(json.dumps(value['identity'], sort_keys=True, separators=(',', ':')).encode()).hexdigest()
    output.write('DATA | ' + json.dumps(value | {'credential_scope': scope,
        'package_root': str(Path(__file__).resolve().parents[1]),
        'interpreter': str(Path(sys.executable).resolve()), 'python_version': sys.version.split()[0]},
        ensure_ascii=True) + '\n')
    challenge = 'enable ' + secrets.token_hex(16)
    output.write('同意请在此终端复制完整一行；取消输入 cancel：\n' + challenge + '\n')
    output.flush()
    answer = source.readline(200)
    if answer.rstrip('\r\n') != challenge:
        raise WCEError('CONNECTION_ENABLE_CANCELLED')
    policy = enable(value)
    output.write('CONNECTION_POLICY_ENABLED\n')
    output.flush()
    return policy


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('mode', choices=['setup', 'broker', 'add-account', 'enable-account', 'repair'])
    parser.add_argument('--profile')
    parser.add_argument('--policy')
    args = parser.parse_args()
    try:
        if args.mode == 'setup' and args.profile and not args.policy:
            review(args.profile, sys.stdin, sys.stdout)
        elif args.mode == 'broker' and args.policy and not args.profile:
            Broker(load_policy(args.policy)).serve()
        elif args.mode == 'add-account' and not args.profile and not args.policy:
            add_account(sys.stdin, sys.stdout)
        elif args.mode == 'enable-account' and not args.profile and not args.policy:
            enable_account(sys.stdin, sys.stdout)
        elif args.mode == 'repair' and not args.profile and not args.policy:
            from .own_bootstrap_security import Terminal
            from .own_connection_enrollment import resume_publication
            from .own_connection_policy import registry_path
            terminal = Terminal(sys.stdin, sys.stdout)
            name = terminal.ask('输入原设置的 transaction 标识；仅核对并恢复本地提交，不重发连接请求。')
            terminal.write('TRUSTED ' + resume_publication(name, registry_path()))
        else:
            raise WCEError('CONNECTION_INVALID_ARGUMENTS')
    except WCEError as error:
        print(error.code)
        raise SystemExit(1)
    except (KeyboardInterrupt, EOFError):
        raise SystemExit('CONNECTION_CANCELLED')
    except Exception:
        raise SystemExit('CONNECTION_START_UNDETERMINED')


def add_account(source, output):
    from .own_bootstrap_security import Terminal
    from .own_connection_registry import propose, prepare_default_registry
    from .own_connection_enrollment import enroll
    from .service import digest
    terminal = Terminal(source, output)
    registry = prepare_default_registry()
    terminal.write('TRUSTED WCE 添加自有公众号。AppID 与名称在此输入，密钥稍后隐藏输入。')
    appid = terminal.ask('请输入新公众号 AppID；取消输入 cancel：')
    if appid == 'cancel':
        raise WCEError('CONNECTION_ENABLE_CANCELLED')
    name = terminal.ask('请输入账号显示名称：')
    reviewed = propose(appid, name, registry)
    terminal.write('TRUSTED 本次把现有账号升级到下方精确插件版本，保持身份、密钥范围与全部历史。已断开的账号保持断开。')
    terminal.write('TRUSTED 新号持续委托包括明确请求的图片上传、草稿保存和读取，可随时断开；不含公开发布、群发或未知请求重发。')
    terminal.write('TRUSTED 本次仅为新号发送一次普通 stable_token 验证，成功后保存到该号系统钥匙串并启用；失败或未知不自动重试。原号不重新连接。')
    terminal.display({'new_identity': reviewed['identity'], 'label': reviewed['label'],
        'candidate_scope': reviewed['base']['scope'], 'transaction': reviewed['transaction'],
        'existing_accounts': [{'connection_id': old['value']['identity']['connection_id'],
            'appid': old['value']['identity']['appid'],
            'enabled_after_upgrade': old['value']['enabled'] and not old['revoked']}
            for old in reviewed['base']['policies'].values()],
        'capabilities': reviewed['base']['policies'] and next(iter(reviewed['base']['policies'].values()))['value']['capabilities']
            or ['connection', 'local_inputs', 'draft_images', 'draft_save', 'draft_read']})
    challenge = 'approve ' + secrets.token_hex(16)
    if terminal.ask('核对后输入完整一行，取消输入 cancel：\nTRUSTED ' + challenge) != challenge:
        raise WCEError('CONNECTION_ENABLE_CANCELLED')
    policy, cached, retained, lifetime = enroll(reviewed,
        lambda: terminal.ask('请输入新号 AppSecret，输入隐藏：', hidden=True))
    with retained:
        service = AccountService(policy)
        service.tokens.seed(cached, digest(policy.data))
        terminal.write('TRUSTED CONNECTION_VALIDATED_AND_BOUND')
        terminal.write('TRUSTED 连接由本终端持有；可直接使用插件读取状态。无需执行测试命令。')
        Broker(policy, service).serve(lifetime_fd=lifetime)


def enable_account(source, output):
    from .own_bootstrap_security import Terminal
    from .own_connection_policy import registry_path
    from .own_connection_registry import snapshot
    from .own_connection_enrollment import enable_existing
    terminal = Terminal(source, output)
    base = snapshot(registry_path())
    terminal.write('TRUSTED 选择要重新启用的账号；本次也会升级下方列出的旧版本账号。保持原身份、密钥和历史；不请求 token。')
    terminal.display({'accounts': [{'connection_id': x['value']['identity']['connection_id'],
        'appid': x['value']['identity']['appid']} for x in base['policies'].values()],
        'candidate_scope': base['scope']})
    cid = terminal.ask('请输入要启用的完整 connection_id；取消输入 cancel：')
    if cid == 'cancel': raise WCEError('CONNECTION_ENABLE_CANCELLED')
    if cid not in (base['registry_value'] or {}).get('connections', {}):
        raise WCEError('CONNECTION_NOT_BOUND')
    reviewed = {'base': base, 'reenable': cid, 'transaction': 'txn-' + secrets.token_hex(16)}
    changes = []
    for old in base['policies'].values():
        value = old['value']
        selected = value['identity']['connection_id'] == cid
        if selected or value['schema'] == 1 or value['candidate_scope'] != base['scope']:
            changes.append({'identity': value['identity'],
                'previous_candidate_scope': value['candidate_scope'],
                'candidate_scope': base['scope'],
                'enabled_before': value['enabled'] and not old['revoked'],
                'enabled_after': selected or (value['enabled'] and not old['revoked'])})
    terminal.display({'connection_id': cid, 'candidate_scope': base['scope'],
        'accounts_changed_by_this_confirmation': changes,
        'capabilities': ['connection', 'local_inputs', 'draft_images', 'draft_save', 'draft_read'],
        'duration': 'UNTIL_DISCONNECTED', 'transaction': reviewed['transaction']})
    terminal.write('TRUSTED 本次确认覆盖上方完整账号集合及各号启用状态。所选号重新启用，其余旧版本账号仅升级且保留原启用或撤销状态。')
    terminal.write('TRUSTED 启用账号允许明确请求的图片与草稿操作。不含公开发布、群发或未知请求重发。')
    challenge = 'enable ' + secrets.token_hex(16)
    if terminal.ask('核对后输入完整一行，取消输入 cancel：\nTRUSTED ' + challenge) != challenge:
        raise WCEError('CONNECTION_ENABLE_CANCELLED')
    enable_existing(reviewed)
    terminal.write('TRUSTED CONNECTION_POLICY_ENABLED')
