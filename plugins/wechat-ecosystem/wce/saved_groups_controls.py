"""Negative controls for an immutable saved-group selection; never a grant."""
import re
from .slot_control_semantics import command_text


def selection_changed(text):
    unquoted = re.sub(r"『[^』]*』|「[^」]*」|“[^”]*”|‘[^’]*’|\"[^\"]*\"|'[^']*'", '', text)
    cleaned = command_text(unquoted)
    clauses = re.split(r'[，,；;。！？?\n]', cleaned)
    for clause in clauses:
        if not clause.strip():
            continue
        # Questions and progress reports do not edit the frozen set.
        if re.search(r'是否|能否|能不能|可不可以|要不要|进度|怎么样|完成了吗', clause):
            continue
        if re.search(r'(?:只|仅).{0,32}(?:第.{0,8}组|[前后].{0,8}篇).{0,16}(?:发表|发布|发)', clause):
            return True
        if re.search(r'(?:改成|改为|换成|仅|只)(?:普通)?(?:发表|发布|发)\s*(?:前|后|第|这|那|一|二|三|四|五|六|七|八|九|十|\d)', clause):
            return True
        if (re.search(r'追加|添加|新增|移除|去掉|删掉|取消|排除|跳过|不要|别发', clause)
                and re.search(r'篇|组|文章|稿|本批|本次|这次', clause)):
            return True
        if (re.search(r'改成|改为|换成|调整', clause)
                and re.search(r'分组|组序|顺序|篇数|数量|第一组|第二组|第\d+组', clause)):
            return True
    return False
