"""gate-6.7: 静态质量（新增违规 BLOCK、存量不追溯，locked）. Owner: T5. Rules: design doc §6.2, spec-driven-workflow.md §10.7."""

from typing import List

from . import Finding, GateContext


def check(ctx: GateContext) -> List[Finding]:
    raise NotImplementedError
