"""`spec-driven uat accept | reject`. Owner: T11. Phase 8.9 user acceptance (architecture.md §4.5)."""

from ..errors import unavailable


def register(sub):
    p = sub.add_parser("uat", help="Phase 8.9 用户验收：accept 需用户输入口令授权；reject 回退修改")
    p.add_argument("action", choices=["accept", "reject"])
    p.add_argument("--phase", help="reject：回退到的 Phase")
    p.add_argument("--reason", help="reject：用户要修改的内容（用户原话）")
    p.add_argument("--change")


def run(a) -> int:
    return unavailable("uat")
