"""`spec-driven design`. Owner: T2. design show 读 design.md 的 AI 推荐 / 最终选择；set 写 meta.designDecision（Gate 2 改选后必须 set）。"""

from ..errors import unavailable


def register(sub):
    p = sub.add_parser("design", help="方案决策：show / set")
    p.add_argument("action", choices=["show", "set"])
    p.add_argument("choice", nargs="?")
    p.add_argument("--change")


def run(a) -> int:
    return unavailable("design")
