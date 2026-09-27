"""`spec-driven trace <id>`. Owner: T18. Follow an AC / REQ / SC / task id through proposal,
spec, tasks, commits and QA results. See docs/dev/tasks.md T18."""

from ..errors import unavailable


def register(sub):
    p = sub.add_parser("trace", help="按 AC / REQ / SC / 任务编号追溯需求到测试的链路")
    p.add_argument("id")
    p.add_argument("--change")
    p.add_argument("--json", action="store_true")


def run(a) -> int:
    return unavailable("trace")
