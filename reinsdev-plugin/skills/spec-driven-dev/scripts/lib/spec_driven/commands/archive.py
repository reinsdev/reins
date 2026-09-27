"""`spec-driven archive`. Owner: T7. Phase 9（§7）：前置 gate-8.9；spec.md 按 REQ 合并进 specs/<capability>.md；蒸馏 ADR；提示 architecture.md；补全 retrospective；git mv 到 archive/<date>-<change>/；刷新 specs/README.md；跑 gate-9。"""

from ..errors import unavailable


def register(sub):
    p = sub.add_parser("archive", help="Phase 9：归档 change")
    p.add_argument("--change")
    p.add_argument("--dry-run", action="store_true")


def run(a) -> int:
    return unavailable("archive")
