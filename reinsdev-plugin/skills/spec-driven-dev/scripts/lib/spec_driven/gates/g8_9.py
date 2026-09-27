"""gate-8.9: 用户验收（uatAccepted == true，locked）.
Owner: T4. Rules: design doc §6.2, spec-driven-workflow.md §14.1.

Checks (all kebab-case, stable):
  g8_9-uat-accepted    meta.uatAccepted == true（locked，无法通过配置降级）
"""

from typing import List

from . import Finding, GateContext


def check(ctx: GateContext) -> List[Finding]:
    if ctx.meta.get("uatAccepted") is True:
        return []

    return [Finding(
        level="BLOCK",
        check="g8_9-uat-accepted",
        reason="用户验收尚未完成（uatAccepted 不为 true），不得归档",
        location=".meta.json",
        fix="由用户在总控 Phase 8.9 验收摘要处选择「通过」，系统将写入 uatAccepted=true",
        evidence="uatAccepted=%r" % ctx.meta.get("uatAccepted"),
        locked=True,
    )]
