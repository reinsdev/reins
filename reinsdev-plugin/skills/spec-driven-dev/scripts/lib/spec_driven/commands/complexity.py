"""`spec-driven complexity`. Owner: T2. 复杂度通道（§3.2、workflow §2.4）：show 给推荐档与理由；set 选定或升档；--downgrade 须消费 grants 授权；recheck 在 Phase 2/3 复评，只升不降。每次变更经 retro.append_tier_change 留痕。"""

from ..errors import unavailable


def register(sub):
    p = sub.add_parser("complexity", help="档位：show / set / recheck")
    p.add_argument("action", choices=["show", "set", "recheck"])
    p.add_argument("tier", nargs="?", choices=["S", "M", "L"])
    p.add_argument("--phase", choices=["2", "3"])
    p.add_argument("--apply", action="store_true")
    p.add_argument("--downgrade", action="store_true")
    p.add_argument("--reason")
    p.add_argument("--change")


def run(a) -> int:
    return unavailable("complexity")
