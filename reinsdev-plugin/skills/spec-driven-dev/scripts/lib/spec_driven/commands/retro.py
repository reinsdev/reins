"""`spec-driven retro`. Owner: T6. retro add：向 retrospective.md 待优化清单追加一条（retro.add_todo）。"""

from ..errors import unavailable


def register(sub):
    p = sub.add_parser("retro", help="retrospective.md 留痕")
    p.add_argument("action", choices=["add"])
    p.add_argument("text")
    p.add_argument("--source", default="manual")
    p.add_argument("--change")


def run(a) -> int:
    return unavailable("retro")
