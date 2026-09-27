"""Which change a command acts on (design doc §4 step 1). Owner: T2."""

from typing import Optional

from .project import Project


def resolve(project: Project, explicit: Optional[str] = None) -> str:
    """explicit name > change bound to the current git branch (meta.branch) > the only
    active change > errors.fail() listing the candidates. Also fails when the project has
    no .openspec/ ("尚未启用 Reins，用 /spec 开始")."""
    raise NotImplementedError
