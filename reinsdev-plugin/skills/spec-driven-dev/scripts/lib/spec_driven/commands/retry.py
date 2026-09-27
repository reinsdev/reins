"""`spec-driven retry`. Owner: T2. 回退（§8）：目标工件顶部写 revised 注释，该 Phase 置 in_progress，下游全部 stale，解除冻结。"""

from ..errors import unavailable


def register(sub):
    p = sub.add_parser("retry", help="回退到某个 Phase")
    p.add_argument("phase")
    p.add_argument("--reason", required=True)
    p.add_argument("--change")


def run(a) -> int:
    return unavailable("retry")
