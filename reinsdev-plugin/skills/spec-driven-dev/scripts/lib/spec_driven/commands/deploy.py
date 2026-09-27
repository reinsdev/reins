"""`spec-driven deploy skip`. Owner: T11. Phase 8.5 skip by user choice (architecture.md §4.5)."""

from ..errors import unavailable


def register(sub):
    p = sub.add_parser("deploy", help="Phase 8.5 部署验收：用户选择跳过")
    p.add_argument("action", choices=["skip"])
    p.add_argument("--reason", required=True, help="用户的理由（用户原话）")
    p.add_argument("--change")


def run(a) -> int:
    return unavailable("deploy")
