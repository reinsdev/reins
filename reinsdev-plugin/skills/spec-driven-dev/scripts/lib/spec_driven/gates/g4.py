"""gate-4: 任务拆分（任务关联 SC、分层顺序、bugfix T-regression）. Owner: T3. Rules: design doc §6.2, spec-driven-workflow.md §8.1."""

from typing import List

from . import Finding, GateContext


def check(ctx: GateContext) -> List[Finding]:
    raise NotImplementedError
