"""gate-8.5: 部署验收（deploy-report 或跳过记录）. Owner: T4. Rules: design doc §6.2, spec-driven-workflow.md §13.1."""

from typing import List

from . import Finding, GateContext


def check(ctx: GateContext) -> List[Finding]:
    raise NotImplementedError
