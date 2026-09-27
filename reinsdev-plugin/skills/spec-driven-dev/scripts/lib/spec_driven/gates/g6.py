"""gate-6: TDD 实现（测试真跑、implementation-log、增量覆盖率）. Owner: T5. Rules: design doc §6.2, spec-driven-workflow.md §10.4."""

from typing import List

from . import Finding, GateContext


def check(ctx: GateContext) -> List[Finding]:
    raise NotImplementedError
