"""`spec-driven design`. Owner: T2. `show` reads the recommended and final choice from
design.md (`**AI 推荐**：…`, `**最终选择**：…`) next to meta.designDecision; `set` writes
meta.designDecision (required after the user changes the choice at gate 2)."""

import re

from .. import locate, meta
from .. import project as P
from ..errors import OK, WARN, fail
from ..project import Project


def register(sub):
    p = sub.add_parser("design", help="方案决策：show / set")
    p.add_argument("action", choices=["show", "set"])
    p.add_argument("choice", nargs="?")
    p.add_argument("--change")


def labelled(text: str, label: str):
    """Value after a bold label such as **最终选择**：方案 B; None when absent."""
    m = re.search(r"\*\*%s\*\*\s*[:：]\s*(.+)" % re.escape(label), text)
    return m.group(1).strip() if m else None


def run(a) -> int:
    project = Project.here()
    change, change_dir, m = locate.load(project, a.change)
    path = change_dir / P.DESIGN
    text = path.read_text(encoding="utf-8") if path.is_file() else ""
    recommended, final = labelled(text, "AI 推荐"), labelled(text, "最终选择")
    if a.action == "show":
        if not text:
            print("还没有 design.md")
        print("AI 推荐   %s" % (recommended or "（未写）"))
        print("最终选择  %s" % (final or "（未写）"))
        print("已记录    %s" % (m["designDecision"] or "（未记录）"))
        if final and m["designDecision"] and final != m["designDecision"]:
            print("不一致：design.md 的最终选择与记录不同，用 design set 更新")
            return WARN
        return OK
    choice = (a.choice or final or "").strip()
    if not choice:
        fail("用法：design set <方案>；design.md 里也没有「**最终选择**」可用")
    meta.update(change_dir, lambda md: md.__setitem__("designDecision", choice))
    print("已记录方案决策：%s" % choice)
    if final and final != choice:
        print("注意：design.md 的最终选择是「%s」，gate-2 要求两者一致" % final)
        return WARN
    return OK
