"""gate-3: spec.md（AC→SC 映射、REQ/SC 结构、接口契约、数据模型、复杂度复评）. Owner: T3. Rules: design doc §6.2, spec-driven-workflow.md §7.1."""

from typing import List

from . import Finding, GateContext


def check(ctx: GateContext) -> List[Finding]:
    raise NotImplementedError
