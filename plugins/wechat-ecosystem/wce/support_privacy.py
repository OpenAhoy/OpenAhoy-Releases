"""Shared pre-bridge and pre-Issue support-text projection. No raw text logs."""
import json
import re

from .support_diagnostics import UPDATE_CACHE_CODES

RULES = [
    (r'```[\s\S]*?```', 'g', '[代码或原始数据已移除]'),
    (r'^(?:正文|文章内容|完整响应|响应体|返回体|response|content)\s*[:：=][\s\S]*', 'gim', '[正文或响应已移除]'),
    (r'["\']?(?:app[_ -]?secret|access[_ -]?token|refresh[_ -]?token|api[_ -]?key|client[_ -]?secret|authorization|password|cookie|secret|token|密码|密钥|验证码)["\']?\s*[:=：]\s*[^\r\n]+', 'gi', '[秘密字段已移除]'),
    (r'Bearer\s+[^\s,;]+', 'gi', '[凭据已移除]'),
    (r'["\'](?:content|body|response|article[_ -]?content|正文)["\']\s*:\s*[\s\S]*', 'gi', '[正文或响应已移除]'),
    (r'[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}', 'gi', '[邮箱已移除]'),
    (r'(?:https?|ssh)://[^\s<>()]+', 'gi', '[链接已移除]'),
    (r'(?:/Users/|/home/|/Volumes/|/private/|/var/|/tmp/|/Applications/|/opt/|/etc/|~/|[A-Z]:[\\/])[^\s<>"\']+', 'gi', '[本机路径已移除]'),
    (r'(?:wx[0-9a-f]{16}|@[A-Za-z0-9_]{1,50}|[0-9]{16,}|[A-Za-z0-9_-]{32,})', 'gi', None),
    (r'["\'](?:账号|账户|用户名|用户ID|AppID|account[_ -]?id|user[_ -]?id|username|display_name|screen_name|openid|unionid)["\']\s*:\s*(?:"(?:[^"\\]|\\[\s\S])*"|\'(?:[^\'\\]|\\[\s\S])*\'|[^,}\r\n]+)', 'gi', '[账号字段已移除]'),
    (r'^(?:账号|账户|用户名|用户ID|AppID|account[_ -]?id|username)\s*[:：=][^\r\n]*', 'gim', '[账号字段已移除]'),
    (r'[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]', 'g', ''),
]


def redact(value):
    if type(value) is not str or len(value) > 24000:
        raise ValueError('SUPPORT_TEXT_INVALID')
    for pattern, flags, replacement in RULES:
        value = re.sub(pattern, replacement if replacement is not None else account_or_secret, value,
            flags=(re.I if 'i' in flags else 0)|(re.M if 'm' in flags else 0))
    return value.strip()


def account_or_secret(match):
    token = match[0]
    return token if token in UPDATE_CACHE_CODES else '[账号或凭据值已移除]'


def javascript():
    rules = json.dumps(RULES, ensure_ascii=False)
    codes = json.dumps(sorted(UPDATE_CACHE_CODES))
    return ('const supportRedact=value=>{const codes=new Set(' + codes + ');'
            'for(const[p,f,r]of ' + rules + ')value=value.replace(new RegExp(p,f),r??'
            '(token=>codes.has(token)?token:"[账号或凭据值已移除]"));return value.trim();};')
