"""Negative selection changes only; cannot grant or resume publication."""
import re
from .slot_control_semantics import command_text


def selection_changed(text, context):
    cleaned = command_text(text)
    selected = {target.connection_id for target in context.targets}
    for account in context.accounts:
        if account.connection_id in selected:
            continue
        names = '|'.join(re.escape(alias) for alias in sorted(account.aliases, key=len, reverse=True))
        switch = re.search(r'(?:改用|换用|切换到|改发到|发布到|发到)\s*(?:公众号)?\s*(?:' + names + ')', cleaned)
        if switch is not None:
            return True
    return False


def explicit_english_control(text):
    """Small direct imperatives; quoted/reported text is not a command."""
    # Drop quoted material before command_text removes decorative quotation
    # marks. A quoted or conditional resume cannot clear an earlier pause.
    unquoted = re.sub(r'[“「『\"]([^”」』\"\n]*)[”」』\"]', '', text)
    cleaned = command_text(unquoted).strip()
    if re.match(r"(?i)^(?:please\s+)?(?:do not|don't|stop|pause|cancel)\s+(?:publishing|publish|publication)\b", cleaned):
        return 'RESTRICT'
    if re.fullmatch(r'(?i)(?:please\s+)?(?:resume|continue)\s+(?:publishing|publication)[.!]?', cleaned):
        return 'RESUME'
    return None


def precise_content_changed(text, context):
    cleaned = command_text(text)
    selected = bool(re.search(r'这篇|那篇|这组|那组|这个稿|那个稿', cleaned)) or any(
        alias in cleaned for target in context.targets for alias in target.aliases)
    return selected and bool(re.search(
        r'(?:标题|作者|正文|配图|封面|摘要|图片).*?(?:改成|改为|替换|更换)|'
        r'(?:改成|改为|替换|更换).*?(?:标题|作者|正文|配图|封面|摘要|图片)', cleaned))
