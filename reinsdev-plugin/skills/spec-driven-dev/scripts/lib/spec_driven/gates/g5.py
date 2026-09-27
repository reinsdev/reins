"""gate-5: spec 评审（subagent 标记、BLOCK 数、bugfix 升级判定）. Owner: T4. Rules: design doc §6.2, spec-driven-workflow.md §9.1."""

from typing import List

from . import Finding, GateContext


def check(ctx: GateContext) -> List[Finding]:
    raise NotImplementedError
