"""`spec-driven quality setup`. Owner: T16. Bring a Maven / Gradle project up to what gate 6.7
needs (ArchUnit test dependency and rules, Checkstyle / PMD / SpotBugs commands), so that
`init-config --java` can run the checks and build the baseline. See docs/dev/tasks.md T16."""

from ..errors import unavailable


def register(sub):
    p = sub.add_parser("quality", help="接入质量检查工具（ArchUnit、Checkstyle、PMD、SpotBugs）")
    p.add_argument("action", choices=["setup", "show"])
    p.add_argument("--dry-run", action="store_true", help="只列出将要做的修改")
    p.add_argument("--online", action="store_true", help="允许联网下载插件和依赖并预热本地仓库")


def run(a) -> int:
    return unavailable("quality")
