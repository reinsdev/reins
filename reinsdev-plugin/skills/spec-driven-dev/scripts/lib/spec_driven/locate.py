"""Which change a command acts on (design doc §4 step 1). Owner: T2."""

import json
from typing import Optional

from . import gitutil
from .errors import fail
from .project import META, Project


def _branch_of(project: Project, change: str) -> Optional[str]:
    try:
        return json.loads((project.change_dir(change) / META).read_text(encoding="utf-8")).get("branch")
    except (OSError, ValueError):
        return None


def resolve(project: Project, explicit: Optional[str] = None) -> str:
    """explicit name > change bound to the current git branch (meta.branch) > the only
    active change > errors.fail() listing the candidates. Also fails when the project has
    no .openspec/ ("尚未启用 Reins，用 /spec 开始").
    Multi-instance callers must supply an explicit change name."""
    if not project.enabled:
        fail("项目 %s 尚未启用 Reins（没有 .openspec/），用 /spec 开始" % project.root)
    active = project.active_changes()
    if explicit:
        if explicit not in active:
            fail("没有进行中的 change「%s」；现有：%s" % (explicit, "、".join(active) or "无"))
        return explicit
    if gitutil.is_repo(project.root):
        branch = gitutil.current_branch(project.root)
        bound = [c for c in active if branch and _branch_of(project, c) == branch]
        if len(bound) == 1:
            return bound[0]
    if len(active) == 1:
        return active[0]
    if not active:
        fail("没有进行中的 change，用 /spec 或 /bugfix 开始一个")
    fail("有多个进行中的 change，请指定一个：%s" % "、".join(active))


def load(project: Project, explicit: Optional[str] = None):
    """(change, change_dir, meta) for the resolved change."""
    from . import meta
    change = resolve(project, explicit)
    change_dir = project.change_dir(change)
    return change, change_dir, meta.load(change_dir)
