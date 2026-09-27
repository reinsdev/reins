"""gate-0: change 与项目前提（Java 项目、change 名、proposal、mode）. Owner: T3. Rules: design doc §6.2, spec-driven-workflow.md §四."""

from typing import List

from . import Finding, GateContext


def check(ctx: GateContext) -> List[Finding]:
    raise NotImplementedError
