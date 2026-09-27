"""gate-7: QA 评审报告校验（subagent 标记、降级措辞、所有 SC PASS）.
Owner: T4. Rules: design doc §6.2, spec-driven-workflow.md §11.1.

Checks (all kebab-case, stable):
  g7-generated-by      首行 generated-by 标记（locked）
  g7-demotion-phrase   禁止「主线自评」「直接根据代码验证」等降级措辞（locked）
  g7-sc-pass           spec.md 里的每个 SC 在 qa-report 里都为 PASS
"""

import re
from typing import List

from .. import mdparse
from ..project import QA_REPORT, SPEC
from . import Finding, GateContext

_AGENT = "qa-evaluator-subagent"

_DEMOTION_PHRASES = [
    "主线自评",
    "直接根据代码验证",
]

# Column names that hold the per-SC result in a qa-report table.
_RESULT_COL_NAMES = {"结果", "Result", "Status", "状态"}


def _read(change_dir, filename):
    path = change_dir / filename
    if not path.is_file():
        return None
    return path.read_text(encoding="utf-8").replace("\r\n", "\n")


def _sc_results(text):
    """Return {sc_id: result_upper} from the qa-report.

    Primary path: mdparse.tables() looking for a table with an 'SC' column.
    Fallback: regex scan using ID_PATTERNS["SC"] for inline "SC-xxx | PASS" forms.
    """
    results = {}
    _sc_re = mdparse.id_re("SC")

    for table in mdparse.tables(text):
        if "SC" not in table.header:
            continue
        result_col = next((h for h in table.header if h in _RESULT_COL_NAMES), None)
        if result_col is None:
            continue
        for row in table.rows:
            m = _sc_re.search(row.get("SC", ""))
            if m:
                results[m.group(0)] = row.get(result_col, "").strip().upper()

    if not results:
        _fallback = re.compile(
            r"(%s)\s*[|:]\s*(PASS|FAIL|SKIP)" % mdparse.ID_PATTERNS["SC"],
            re.IGNORECASE,
        )
        for m in _fallback.finditer(text):
            results[m.group(1)] = m.group(2).upper()

    return results


def check(ctx: GateContext) -> List[Finding]:
    findings = []
    text = _read(ctx.change_dir, QA_REPORT)

    if text is None:
        findings.append(Finding(
            level="BLOCK",
            check="g7-generated-by",
            reason="qa-report.md 不存在，无法确认评审来源",
            location=QA_REPORT,
            fix="由 qa-evaluator subagent 产出 qa-report.md",
            locked=True,
        ))
        return findings

    # Check 1: generated-by marker (locked).
    first_line = next((l for l in text.splitlines() if l.strip()), "")
    expected = "<!-- generated-by: %s -->" % _AGENT
    if first_line.strip() != expected:
        findings.append(Finding(
            level="BLOCK",
            check="g7-generated-by",
            reason="qa-report.md 首行缺少正确的 generated-by 标记，无法确认是独立 subagent 产出",
            location=QA_REPORT,
            fix="确保 qa-evaluator subagent 写入报告，首行为：%s" % expected,
            evidence=first_line.strip()[:120],
            locked=True,
        ))

    # Check 2: no demotion phrases (locked).
    found_phrases = [p for p in _DEMOTION_PHRASES if p in text]
    if found_phrases:
        findings.append(Finding(
            level="BLOCK",
            check="g7-demotion-phrase",
            reason="qa-report.md 含降级措辞，表明评审不独立：%s" % "、".join(found_phrases),
            location=QA_REPORT,
            fix="由真正的独立 subagent 重新产出报告",
            evidence="|".join(found_phrases),
            locked=True,
        ))

    # Check 3: every SC in spec.md must be PASS in the qa-report.
    spec_text = _read(ctx.change_dir, SPEC)
    if spec_text is None:
        findings.append(Finding(
            level="BLOCK",
            check="g7-sc-pass",
            reason="spec.md 不存在，无法校验 SC 覆盖情况",
            location=SPEC,
            fix="确保 spec.md 存在",
        ))
        return findings

    spec_root = mdparse.parse(spec_text)
    sc_sections = mdparse.find_all(spec_root, mdparse.ID_PATTERNS["SC"])
    # Extract the SC ID (e.g. "SC-policy-001") from the full title which may include
    # a description suffix like ": 全部审批通过".
    _sc_re = mdparse.id_re("SC")
    sc_ids = []
    for s in sc_sections:
        m = _sc_re.search(s.title)
        if m:
            sc_ids.append(m.group(0))

    if not sc_ids:
        return findings

    results = _sc_results(text)
    failed = [sc for sc in sc_ids if results.get(sc, "") != "PASS"]
    if failed:
        findings.append(Finding(
            level="BLOCK",
            check="g7-sc-pass",
            reason="qa-report 有 %d 个 SC 未 PASS：%s" % (len(failed), " ".join(failed)),
            location=QA_REPORT,
            fix="修复失败场景或由用户确认接受风险后放行",
            evidence=" ".join(failed),
        ))

    return findings
