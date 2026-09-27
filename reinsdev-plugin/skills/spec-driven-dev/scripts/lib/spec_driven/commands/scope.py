"""`spec-driven scope set | show`. Owner: T11. bugfix scope assessment (architecture.md §4.5)."""

from ..errors import unavailable


def register(sub):
    p = sub.add_parser("scope", help="bugfix 改动范围评估，决定 Phase 2 / 3 是否跳过")
    p.add_argument("action", choices=["set", "show"])
    p.add_argument("--files", type=int, help="预计改动的文件数")
    p.add_argument("--cross-service", action="store_true")
    p.add_argument("--ddl", action="store_true")
    p.add_argument("--public-api", action="store_true")
    p.add_argument("--change")


def run(a) -> int:
    return unavailable("scope")
