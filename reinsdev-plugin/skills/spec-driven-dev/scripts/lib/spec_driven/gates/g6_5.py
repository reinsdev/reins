"""gate-6.5: 任务完成（tasks-sync 后无裸复选框）. Owner: T5. Rules: design doc §6.2, spec-driven-workflow.md §10.6."""

from typing import List

from . import Finding, GateContext


def check(ctx: GateContext) -> List[Finding]:
    raise NotImplementedError
