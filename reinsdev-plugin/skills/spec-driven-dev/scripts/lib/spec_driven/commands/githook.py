"""`spec-driven githook`. Owner: T6. git 层护栏（§2.4 第 2 层）：pre-commit 拒绝当前 Phase gate 未过、冻结工件与 retrospective 的非 CLI 改动；commit-msg 校验 Task-Id trailer。install 写入 .git/hooks（不覆盖他人 hook，链式调用）。"""

from ..errors import unavailable


def register(sub):
    p = sub.add_parser("githook", help="git hook 入口与安装")
    p.add_argument("event", choices=["install", "pre-commit", "commit-msg"])
    p.add_argument("msgfile", nargs="?")


def run(a) -> int:
    return unavailable("githook")
