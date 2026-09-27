"""`spec-driven parallel plan | run | merge`. Owner: T19. Phase 6 multi-worker execution
(workflow §10.3). See docs/dev/tasks.md T19."""

from ..errors import unavailable


def register(sub):
    p = sub.add_parser("parallel", help="Phase 6 多实现者并行：plan 预演 / run 建 worktree / merge 串行合回")
    p.add_argument("action", choices=["plan", "run", "merge"])
    p.add_argument("--change")
    p.add_argument("--json", action="store_true")


def run(a) -> int:
    return unavailable("parallel")
