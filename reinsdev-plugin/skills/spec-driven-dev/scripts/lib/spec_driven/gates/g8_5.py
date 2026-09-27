"""gate-8.5: 部署验收（deploy-report 存在且结论为 passed）.
Owner: T4. Rules: design doc §6.2, spec-driven-workflow.md §13.1.

Checks (all kebab-case, stable):
  g8_5-deploy-report   deploy-report.md 存在且 结论 节首行精确等于 "passed"

Note: 用户选择跳过部署验收时，由 waive 写入放行记录，框架统一处理 [WAIVED] 标记，
本 gate 只负责报告事实（deploy-report 是否存在且通过），不自行读 retrospective。
待 T2 协调者交付 deploy skip 命令后，再对接跳过流程。
"""

from typing import List

from .. import mdparse
from ..project import DEPLOY_REPORT
from . import Finding, GateContext


def _read(change_dir, filename):
    path = change_dir / filename
    if not path.is_file():
        return None
    return path.read_text(encoding="utf-8").replace("\r\n", "\n")


def _deploy_passed(text):
    """Return True only when the conclusion section's first non-empty line is exactly 'passed'.

    Exact match prevents false positives from substrings like '未通过' containing '通过'
    or 'not passed' containing 'passed'. Template says fill with exactly 'passed' or 'failed'.
    Unrecognised content is treated as failure (gate fails closed).
    """
    root = mdparse.parse(text)
    section = mdparse.find(root, "conclusion")
    if section is None:
        return False
    first = next((l.strip() for l in section.body.splitlines() if l.strip()), "")
    return first.lower() == "passed"


def check(ctx: GateContext) -> List[Finding]:
    text = _read(ctx.change_dir, DEPLOY_REPORT)

    if text is not None and _deploy_passed(text):
        return []

    if text is None:
        return [Finding(
            level="BLOCK",
            check="g8_5-deploy-report",
            reason="deploy-report.md 不存在，部署验收未完成",
            location=DEPLOY_REPORT,
            fix="运行本地部署（local-deploy skill）产出 deploy-report.md，或由用户确认跳过此步骤后放行",
        )]

    return [Finding(
        level="BLOCK",
        check="g8_5-deploy-report",
        reason="deploy-report.md 结论不为 passed，部署验收未通过",
        location=DEPLOY_REPORT,
        fix="确认部署成功后将 deploy-report.md 结论节改为 passed，或由用户确认跳过后放行",
        evidence="conclusion_not_passed",
    )]
