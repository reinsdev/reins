"""gate-8.9: 用户验收（uatAccepted，locked）. Owner: T4. Rules: design doc §6.2, spec-driven-workflow.md §14.1."""

from typing import List

from . import Finding, GateContext


def check(ctx: GateContext) -> List[Finding]:
    raise NotImplementedError
