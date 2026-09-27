"""gate-8: code review 报告校验（subagent 标记、降级措辞、格式契约、BLOCK=0、WARN 进待优化清单）.
Owner: T4. Rules: design doc §6.2, architecture.md §4.2, spec-driven-workflow.md §12.1.

Checks (all kebab-case, stable):
  g8-generated-by      首行 generated-by 标记（locked）
  g8-demotion-phrase   禁止「主线自评」「直接根据代码验证」等降级措辞（locked）
  g8-conclusion-table  「结论」表存在且格式正确（表头、非负整数、计数一致）
  g8-findings-table    「问题清单」表存在且「级别」取值合法
  g8-block-count       BLOCK 数 = 0（从问题清单计）
  g8-warn-in-todos     每条 WARN 的「问题」原文完整出现在 retro.todos() 里
"""

from typing import List

from .. import retro
from ..project import CODE_REVIEW
from . import Finding, GateContext
from .g5 import _check_report_tables, _read

_AGENT = "code-reviewer-subagent"

_DEMOTION_PHRASES = ["主线自评", "直接根据代码验证"]


def check(ctx: GateContext) -> List[Finding]:
    findings = []
    text = _read(ctx.change_dir, CODE_REVIEW)

    if text is None:
        findings.append(Finding(
            level="BLOCK",
            check="g8-generated-by",
            reason="code-review.md 不存在，无法确认评审来源",
            location=CODE_REVIEW,
            fix="由 code-reviewer subagent 产出 code-review.md",
            locked=True,
        ))
        return findings

    # Check 1: generated-by marker (locked).
    first_line = next((l for l in text.splitlines() if l.strip()), "")
    expected = "<!-- generated-by: %s -->" % _AGENT
    if first_line.strip() != expected:
        findings.append(Finding(
            level="BLOCK",
            check="g8-generated-by",
            reason="code-review.md 首行缺少正确的 generated-by 标记，无法确认是独立 subagent 产出",
            location=CODE_REVIEW,
            fix="确保 code-reviewer subagent 写入报告，首行为：%s" % expected,
            evidence=first_line.strip()[:120],
            locked=True,
        ))

    # Check 2: no demotion phrases (locked).
    found_phrases = [p for p in _DEMOTION_PHRASES if p in text]
    if found_phrases:
        findings.append(Finding(
            level="BLOCK",
            check="g8-demotion-phrase",
            reason="code-review.md 含降级措辞，表明评审不独立：%s" % "、".join(found_phrases),
            location=CODE_REVIEW,
            fix="由真正的独立 subagent 重新产出报告",
            evidence="|".join(found_phrases),
            locked=True,
        ))

    # Checks 3-4: conclusion + findings tables.
    block_count, warn_texts = _check_report_tables("g8", text, CODE_REVIEW, findings)

    # Check 5: BLOCK count must be 0.
    if block_count is not None and block_count > 0:
        findings.append(Finding(
            level="BLOCK",
            check="g8-block-count",
            reason="code-review 问题清单有 %d 条 BLOCK，代码评审未通过" % block_count,
            location=CODE_REVIEW,
            fix="修复代码问题后重新评审，或由用户确认接受风险后放行",
            evidence="block_count=%d" % block_count,
        ))

    # Check 6: every WARN's "问题" text must appear verbatim in retro.todos().
    if warn_texts:
        todos = set(retro.todos(ctx.change_dir))
        missing = [w for w in warn_texts if w not in todos]
        if missing:
            findings.append(Finding(
                level="BLOCK",
                check="g8-warn-in-todos",
                reason="code-review 问题清单有 %d 条 WARN 的「问题」原文未出现在 retrospective 待优化清单里"
                       % len(missing),
                location=CODE_REVIEW,
                fix="运行 `spec-driven retro add --source \"code-review WARN\" \"<问题原文>\"` "
                    "将每条 WARN 加入待优化清单，或由用户放行",
                evidence="warn_count=%d" % len(missing),
            ))

    return findings
