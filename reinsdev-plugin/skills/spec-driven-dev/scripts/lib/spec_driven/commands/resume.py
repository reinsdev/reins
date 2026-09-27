"""`spec-driven resume`. Owner: T2. 冷启动恢复：一屏输出 change、mode、档位、当前 Phase 与下一步、invariants 摘要、本 Phase 要读的工件（§8）。"""

from ..errors import unavailable


def register(sub):
    p = sub.add_parser("resume", help="新会话第一步：恢复当前 change 的上下文")
    p.add_argument("change", nargs="?")


def run(a) -> int:
    return unavailable("resume")
