"""gate-2: 技术方案（方案数、6 字段、推荐与最终选择、压测场景、复杂度复评）. Owner: T3. Rules: design doc §6.2, spec-driven-workflow.md §6.2."""

from typing import List

from . import Finding, GateContext


def check(ctx: GateContext) -> List[Finding]:
    raise NotImplementedError
