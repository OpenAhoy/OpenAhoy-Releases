"""Trusted-host TTY adapter, deliberately absent from MCP and ordinary settings.

A reviewed installation bootstrap must supply the fixed TrustedCase. This
module cannot create/reserve a case or select a checkpoint supplied by a model.
"""
import json

from .contracts import WCEError
from .own_identity_recovery import RecoverySession


def human_recover(case, source, output):
    if not source.isatty() or not output.isatty():
        raise WCEError('CONNECTION_RELOCATION_HUMAN_TTY_REQUIRED')
    session = RecoverySession(case)
    try:
        review = session.prepare()
        output.write('TRUSTED OpenAhoy：仅恢复下列既有账号的本机身份绑定。\n')
        output.write('TRUSTED 保留原密钥范围、历史草稿、未知结果和已用额度；已断开账号保持断开。\n')
        output.write('TRUST 观察前历史及整机回滚未被证明；本轮不连接微信、不上传、不保存草稿。\n')
        output.write('DATA | ' + json.dumps(review, ensure_ascii=True, sort_keys=True) + '\n')
        output.write('TRUSTED 核对后输入完整一行；取消请输入 cancel：\n')
        output.write('TRUSTED ' + session.proposed['challenge'] + '\n'); output.flush()
        answer = source.readline(128)
        if not answer or answer.strip() == 'cancel':
            return {'state': session.close()}
        return session.commit(answer.rstrip('\r\n'))
    finally:
        session.close()
