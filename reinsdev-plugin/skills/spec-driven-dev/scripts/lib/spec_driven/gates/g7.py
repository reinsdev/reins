"""gate-7: QA（subagent 标记、所有 SC PASS）. Owner: T4. Rules: design doc §6.2, spec-driven-workflow.md §11.1."""

from typing import List

from . import Finding, GateContext


def check(ctx: GateContext) -> List[Finding]:
    raise NotImplementedError
