"""gate-8.5: 部署验收（deploy-report 存在且结论为 passed，或 retrospective 记录了跳过）.
Owner: T4. Rules: design doc §6.2, spec-driven-workflow.md §13.1.

Checks (all kebab-case, stable):
  g8_5-deploy-report   deploy-report.md 存在且结论为 passed，或 retrospective 已记录跳过
"""

from typing import List

from .. import mdparse, retro
from ..project import DEPLOY_REPORT
from . import Finding, GateContext

# Gate id as recorded in retrospective waivers when the user chooses to skip deployment.
_GATE = "8.5"

# The "conclusion" section's expected passed value.
_PASSED_VALUES = {"passed", "通过", "pass", "成功"}


def _read(change_dir, filename):
    path = change_dir / filename
    if not path.is_file():
        return None
    return path.read_text(encoding="utf-8").replace("\r\n", "\n")


def _deploy_passed(text):
    """Return True when the deploy-report conclusion section indicates passed."""
    root = mdparse.parse(text)
    section = mdparse.find(root, "conclusion")
    if section is None:
        section = mdparse.find(root, "manual-acceptance")
    if section is None:
        return False
    body = section.text().lower()
    return any(v in body for v in _PASSED_VALUES)


def _skip_recorded(change_dir):
    """Return True when retrospective has a waiver for gate 8.5 (deploy skipped by user)."""
    for w in retro.waivers(change_dir):
        if w.gate == _GATE:
            return True
    return False


def check(ctx: GateContext) -> List[Finding]:
    # If phase 8.5 is skipped in meta, gate framework handles it before calling us.
    text = _read(ctx.change_dir, DEPLOY_REPORT)

    if text is not None and _deploy_passed(text):
        return []

    if _skip_recorded(ctx.change_dir):
        return []

    if text is None:
        return [Finding(
            level="BLOCK",
            check="g8_5-deploy-report",
            reason="deploy-report.md 不存在，部署验收未完成",
            location=DEPLOY_REPORT,
            fix="运行本地部署（local-deploy skill）产出 deploy-report.md，或由用户确认跳过此步骤",
        )]

    return [Finding(
        level="BLOCK",
        check="g8_5-deploy-report",
        reason="deploy-report.md 结论不为 passed，部署验收未通过",
        location=DEPLOY_REPORT,
        fix="确认部署成功后更新 deploy-report.md 结论，或由用户确认跳过此步骤",
        evidence="conclusion_not_passed",
    )]
