"""gate-9: 归档（目录迁移、主 specs 合并、retrospective）. Owner: T7. Rules: design doc §6.2, spec-driven-workflow.md §15.1."""

from typing import List

from . import Finding, GateContext


def check(ctx: GateContext) -> List[Finding]:
    raise NotImplementedError
