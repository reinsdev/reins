"""gate-5: spec 评审报告校验（subagent 标记、降级措辞、BLOCK 数、bugfix 升级判定）.
Owner: T4. Rules: design doc §6.2, spec-driven-workflow.md §9.1.

Checks (all kebab-case, stable):
  g5-generated-by      首行 generated-by 标记（locked）
  g5-demotion-phrase   禁止「主线自评」「直接根据代码验证」等降级措辞（locked）
  g5-block-count       BLOCK 数 = 0 或显式接受风险
  g5-bugfix-upgrade    bugfix 报告未标「应升级 design」
"""

import re
from typing import List

from ..project import SPEC_REVIEW
from . import Finding, GateContext

_AGENT = "spec-evaluator-subagent"

_DEMOTION_PHRASES = [
    "主线自评",
    "直接根据代码验证",
]

_LEVEL_LINE = re.compile(r"^\[(?P<level>BLOCK|WARN|INFO|WAIVED)\]")

_BUGFIX_UPGRADE_PHRASE = "应升级 design"


def _read(change_dir, filename):
    path = change_dir / filename
    if not path.is_file():
        return None
    return path.read_text(encoding="utf-8").replace("\r\n", "\n")


def _count_blocks(text):
    """Count non-waived BLOCK lines in the report."""
    count = 0
    for line in text.splitlines():
        m = _LEVEL_LINE.match(line.strip())
        if m and m.group("level") == "BLOCK":
            count += 1
    return count


def check(ctx: GateContext) -> List[Finding]:
    findings = []
    text = _read(ctx.change_dir, SPEC_REVIEW)

    if text is None:
        findings.append(Finding(
            level="BLOCK",
            check="g5-generated-by",
            reason="spec-review.md 不存在，无法确认评审来源",
            location=SPEC_REVIEW,
            fix="由 spec-evaluator subagent 产出 spec-review.md",
            locked=True,
        ))
        return findings

    # Check 1: generated-by marker on the first non-empty line (locked).
    first_line = next((l for l in text.splitlines() if l.strip()), "")
    expected = "<!-- generated-by: %s -->" % _AGENT
    if first_line.strip() != expected:
        findings.append(Finding(
            level="BLOCK",
            check="g5-generated-by",
            reason="spec-review.md 首行缺少正确的 generated-by 标记，无法确认是独立 subagent 产出",
            location=SPEC_REVIEW,
            fix="确保 spec-evaluator subagent 写入报告，首行为：%s" % expected,
            evidence=first_line.strip()[:120],
            locked=True,
        ))

    # Check 2: no demotion phrases (locked).
    found_phrases = [p for p in _DEMOTION_PHRASES if p in text]
    if found_phrases:
        findings.append(Finding(
            level="BLOCK",
            check="g5-demotion-phrase",
            reason="spec-review.md 含降级措辞，表明评审不独立：%s" % "、".join(found_phrases),
            location=SPEC_REVIEW,
            fix="由真正的独立 subagent 重新产出报告，不得在报告里自我申报已直接验证",
            evidence="|".join(found_phrases),
            locked=True,
        ))

    # Check 3: BLOCK count = 0.
    block_count = _count_blocks(text)
    if block_count > 0:
        findings.append(Finding(
            level="BLOCK",
            check="g5-block-count",
            reason="spec-review.md 有 %d 条 BLOCK，spec 未通过评审" % block_count,
            location=SPEC_REVIEW,
            fix="修复 spec 工件中的问题后重新评审，或由用户确认接受风险后放行",
            evidence="block_count=%d" % block_count,
        ))

    # Check 4: bugfix reports must not flag for design upgrade.
    if ctx.meta.get("mode") == "bugfix" and _BUGFIX_UPGRADE_PHRASE in text:
        findings.append(Finding(
            level="BLOCK",
            check="g5-bugfix-upgrade",
            reason="spec-review 标记该 bugfix 应升级为 design 流程，请先确认是否需要走 Phase 2/3",
            location=SPEC_REVIEW,
            fix="使用 `spec-driven complexity set M --reason '...'` 升档后重新走流程，或放行此项",
            evidence=_BUGFIX_UPGRADE_PHRASE,
        ))

    return findings
