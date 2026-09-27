"""`spec-driven new`. Owner: T2. Phase 0（§7）：校验 git 仓库与 Java 项目，建 .openspec/ 与 changes/<change>/，写 .meta.json 与 proposal.md 骨架，建议并绑定分支，安装 git hooks（githook.install），最后跑 gate-0。"""

from ..errors import unavailable


def register(sub):
    p = sub.add_parser("new", help="Phase 0：建 change")
    p.add_argument("change", nargs="?", help="feature：用户确认的 kebab-case 名；bugfix：留空时生成 fix-<YYYYMMDD>-<slug>")
    p.add_argument("--mode", choices=["feature", "bugfix"], default="feature")
    p.add_argument("--slug", help="bugfix 的简短描述，用于生成名字")
    p.add_argument("--no-branch", action="store_true", help="不创建 / 切换分支")


def run(a) -> int:
    return unavailable("new")
