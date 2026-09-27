"""gate-7: QA 评审报告校验（subagent 标记、降级措辞、格式契约、所有 SC PASS）.
Owner: T4. Rules: design doc §6.2, architecture.md §4.2, spec-driven-workflow.md §11.1.

Checks (all kebab-case, stable):
  g7-generated-by      首行 generated-by 标记（locked）
  g7-demotion-phrase   禁止「主线自评」「直接根据代码验证」等降级措辞（locked）
  g7-conclusion-table  「结论」表存在且格式正确（表头、非负整数、计数一致）
  g7-findings-table    「问题清单」表存在且「级别」取值合法
  g7-sc-results-table  「SC 验证结果」表存在且格式正确
  g7-sc-pass           spec.md 里的每个 SC 在「SC 验证结果」表里都有一行且「结果」为 PASS
"""

from typing import List

from .. import mdparse
from ..project import QA_REPORT, SPEC
from . import Finding, GateContext
from .g5 import _check_report_tables, _read

_AGENT = "qa-evaluator-subagent"

_DEMOTION_PHRASES = ["主线自评", "直接根据代码验证"]

_SC_RESULTS_HEADER = ["SC", "结果", "证据"]
_VALID_RESULTS = {"PASS", "FAIL"}


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

    # Checks 3-4: conclusion + findings tables.
    _check_report_tables("g7", text, QA_REPORT, findings)

    # Check 5: SC 验证结果 table.
    root = mdparse.parse(text)
    sc_results_section = mdparse.find(root, "sc-results")
    if sc_results_section is None:
        findings.append(Finding(
            level="BLOCK",
            check="g7-sc-results-table",
            reason="qa-report.md 缺少「SC 验证结果」节（## SC 验证结果）",
            location=QA_REPORT,
            fix="添加「## SC 验证结果」节及规定格式的表格",
        ))
        return findings

    sc_tables = mdparse.tables(sc_results_section.body)
    if not sc_tables:
        findings.append(Finding(
            level="BLOCK",
            check="g7-sc-results-table",
            reason="「SC 验证结果」节缺少表格",
            location=QA_REPORT,
            fix="添加格式为「| SC | 结果 | 证据 |」的表格",
        ))
        return findings

    sc_table = sc_tables[0]
    if sc_table.header != _SC_RESULTS_HEADER:
        findings.append(Finding(
            level="BLOCK",
            check="g7-sc-results-table",
            reason="「SC 验证结果」表头不符合契约，应为「SC | 结果 | 证据」，实际为「%s」"
                   % " | ".join(sc_table.header),
            location=QA_REPORT,
            fix="将表头改为「| SC | 结果 | 证据 |」",
            evidence="header=%s" % "|".join(sc_table.header),
        ))
        return findings

    bad_results = [r.get("结果", "").strip() for r in sc_table.rows
                   if r.get("结果", "").strip() not in _VALID_RESULTS]
    if bad_results:
        findings.append(Finding(
            level="BLOCK",
            check="g7-sc-results-table",
            reason="「SC 验证结果」有非法「结果」取值（只能是 PASS 或 FAIL）：%s"
                   % "、".join(bad_results[:5]),
            location=QA_REPORT,
            fix="将「结果」列改为 PASS 或 FAIL 之一",
            evidence="|".join(bad_results[:10]),
        ))
        return findings

    # Check 6: every SC in spec.md must have a PASS row.
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
    _sc_re = mdparse.id_re("SC")
    sc_ids = []
    for s in sc_sections:
        m = _sc_re.search(s.title)
        if m:
            sc_ids.append(m.group(0))

    if not sc_ids:
        return findings

    # Build lookup from the SC 验证结果 table (SC column holds just the ID).
    report_results = {}
    for row in sc_table.rows:
        sc_cell = row.get("SC", "").strip()
        m = _sc_re.search(sc_cell)
        if m:
            report_results[m.group(0)] = row.get("结果", "").strip()

    missing = [sc for sc in sc_ids if sc not in report_results]
    failed = [sc for sc in sc_ids if report_results.get(sc, "") == "FAIL"]

    if missing or failed:
        bad = sorted(set(missing + failed))
        reason_parts = []
        if missing:
            reason_parts.append("缺行：%s" % " ".join(missing))
        if failed:
            reason_parts.append("FAIL：%s" % " ".join(failed))
        findings.append(Finding(
            level="BLOCK",
            check="g7-sc-pass",
            reason="qa-report SC 验证结果不满足要求（%s）" % "；".join(reason_parts),
            location=QA_REPORT,
            fix="修复失败场景后重新评审，或由用户确认接受风险后放行",
            evidence=" ".join(bad),
        ))

    return findings
