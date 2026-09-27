"""gate-8: code review（subagent 标记、BLOCK=0、WARN 进待优化清单）. Owner: T4. Rules: design doc §6.2, spec-driven-workflow.md §12.1."""

from typing import List

from . import Finding, GateContext


def check(ctx: GateContext) -> List[Finding]:
    raise NotImplementedError
