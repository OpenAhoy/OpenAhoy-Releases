"""Shared pre-bridge and pre-Issue support-text projection. No raw text logs."""
import json
import re

RULES = [
    (r'```[\s\S]*?```', 'g', '[代码或原始数据已移除]'),
    (r'^(?:正文|文章内容|完整响应|响应体|返回体|response|content)\s*[:：=][\s\S]*', 'gim', '[正文或响应已移除]'),
    (r'["\']?(?:app[_ -]?secret|access[_ -]?token|refresh[_ -]?token|api[_ -]?key|client[_ -]?secret|authorization|password|cookie|secret|token|密码|密钥|验证码)["\']?\s*[:=：]\s*[^\r\n]+', 'gi', '[秘密字段已移除]'),
    (r'Bearer\s+[^\s,;]+', 'gi', '[凭据已移除]'),
    (r'["\'](?:content|body|response|article[_ -]?content|正文)["\']\s*:\s*[\s\S]*', 'gi', '[正文或响应已移除]'),
    (r'[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}', 'gi', '[邮箱已移除]'),
    (r'(?:https?|ssh)://[^\s<>()]+', 'gi', '[链接已移除]'),
    (r'(?:/Users/|/home/|/Volumes/|/private/|/var/|/tmp/|/Applications/|/opt/|/etc/|~/|[A-Z]:[\\/])[^\s<>"\']+', 'gi', '[本机路径已移除]'),
    (r'(?:wx[0-9a-f]{16}|@[A-Za-z0-9_]{1,50}|[0-9]{16,}|[A-Za-z0-9_-]{32,})', 'gi', '[账号或凭据值已移除]'),
    (r'["\'](?:账号|账户|用户名|用户ID|AppID|account[_ -]?id|user[_ -]?id|username|display_name|screen_name|openid|unionid)["\']\s*:\s*(?:"(?:[^"\\]|\\[\s\S])*"|\'(?:[^\'\\]|\\[\s\S])*\'|[^,}\r\n]+)', 'gi', '[账号字段已移除]'),
    (r'^(?:账号|账户|用户名|用户ID|AppID|account[_ -]?id|username)\s*[:：=][^\r\n]*', 'gim', '[账号字段已移除]'),
    (r'[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]', 'g', ''),
]


def redact(value):
    if type(value) is not str or len(value) > 24000:
        raise ValueError('SUPPORT_TEXT_INVALID')
    for pattern, flags, replacement in RULES:
        value = re.sub(pattern, replacement, value,
            flags=(re.I if 'i' in flags else 0)|(re.M if 'm' in flags else 0))
    return value.strip()


def javascript():
    return 'const supportRedact=value=>{for(const[p,f,r]of '+json.dumps(RULES,ensure_ascii=False)+')value=value.replace(new RegExp(p,f),r);return value.trim();};'
