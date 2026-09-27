"""gate-1: 需求澄清（用户故事、AC、业务取值来源、映射确认表、tierConfirmed）. Owner: T3. Rules: design doc §6.2, spec-driven-workflow.md §5.3."""

from typing import List

from . import Finding, GateContext


def check(ctx: GateContext) -> List[Finding]:
    raise NotImplementedError
