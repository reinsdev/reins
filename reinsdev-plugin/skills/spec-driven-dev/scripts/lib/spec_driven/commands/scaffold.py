"""`spec-driven scaffold <artifact>`. Owner: T18. Copy the template of an artifact of the current
phase into the change directory (design, spec, tasks, bugfix-analysis, implementation-log,
deploy-report). See docs/dev/tasks.md T18."""

from ..errors import unavailable

ARTIFACTS = ["bugfix-analysis", "design", "spec", "tasks", "implementation-log", "deploy-report"]


def register(sub):
    p = sub.add_parser("scaffold", help="按模板生成当前 Phase 工件的骨架")
    p.add_argument("artifact", choices=ARTIFACTS)
    p.add_argument("--change")


def run(a) -> int:
    return unavailable("scaffold")
