"""gate-8: code review 报告校验（subagent 标记、降级措辞、BLOCK=0、WARN 进待优化清单）.
Owner: T4. Rules: design doc §6.2, spec-driven-workflow.md §12.1.

Checks (all kebab-case, stable):
  g8-generated-by      首行 generated-by 标记（locked）
  g8-demotion-phrase   禁止「主线自评」「直接根据代码验证」等降级措辞（locked）
  g8-block-count       BLOCK 数 = 0
  g8-warn-in-todos     WARN 条目已进 retrospective 待优化清单
"""

import re
from typing import List

from .. import retro
from ..project import CODE_REVIEW
from . import Finding, GateContext

_AGENT = "code-reviewer-subagent"

_DEMOTION_PHRASES = [
    "主线自评",
    "直接根据代码验证",
]

_LEVEL_LINE = re.compile(r"^\[(?P<level>BLOCK|WARN|INFO|WAIVED)\]\s+(?P<rest>.+)")


def _read(change_dir, filename):
    path = change_dir / filename
    if not path.is_file():
        return None
    return path.read_text(encoding="utf-8").replace("\r\n", "\n")


def _findings_by_level(text):
    """Return (block_lines, warn_texts) parsed from report finding lines."""
    blocks = []
    warns = []
    for line in text.splitlines():
        m = _LEVEL_LINE.match(line.strip())
        if not m:
            continue
        level = m.group("level")
        rest = m.group("rest").strip()
        if level == "BLOCK":
            blocks.append(rest)
        elif level == "WARN":
            warns.append(rest)
    return blocks, warns


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

    block_lines, warn_texts = _findings_by_level(text)

    # Check 3: BLOCK count = 0.
    if block_lines:
        findings.append(Finding(
            level="BLOCK",
            check="g8-block-count",
            reason="code-review.md 有 %d 条 BLOCK，代码评审未通过" % len(block_lines),
            location=CODE_REVIEW,
            fix="修复代码问题后重新评审，或由用户确认接受风险后放行",
            evidence="block_count=%d" % len(block_lines),
        ))

    # Check 4: every WARN must appear in retrospective todos.
    if warn_texts:
        todos = retro.todos(ctx.change_dir)
        missing = [w for w in warn_texts if not any(w[:40] in t for t in todos)]
        if missing:
            findings.append(Finding(
                level="BLOCK",
                check="g8-warn-in-todos",
                reason="code-review.md 有 %d 条 WARN 未进入 retrospective 待优化清单" % len(missing),
                location=CODE_REVIEW,
                fix="运行 `spec-driven retro add` 将 WARN 条目加入待优化清单，或由用户放行",
                evidence="warn_count=%d" % len(missing),
            ))

    return findings
