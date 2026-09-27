"""`spec-driven tasks-sync`. Owner: T2. 据 commit 的 Task-Id trailer 单点渲染 tasks.md 勾选（workflow §10.5）；默认 dry-run，--apply 才写。"""

from ..errors import unavailable


def register(sub):
    p = sub.add_parser("tasks-sync", help="按 Task-Id trailer 同步 tasks.md 勾选")
    p.add_argument("--apply", action="store_true")
    p.add_argument("--change")


def run(a) -> int:
    return unavailable("tasks-sync")
