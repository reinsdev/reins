"""gate-5: spec 评审报告校验（subagent 标记、降级措辞、格式契约、BLOCK 数、bugfix 升级判定）.
Owner: T4. Rules: design doc §6.2, architecture.md §4.2, spec-driven-workflow.md §9.1.

Checks (all kebab-case, stable):
  g5-generated-by      首行 generated-by 标记（locked）
  g5-demotion-phrase   禁止「主线自评」「直接根据代码验证」等降级措辞（locked）
  g5-conclusion-table  「结论」表存在且格式正确（表头、非负整数、计数一致）
  g5-findings-table    「问题清单」表存在且「级别」取值合法
  g5-block-count       BLOCK 数 = 0（从问题清单计）
  g5-bugfix-upgrade    bugfix 模式：「bugfix 升级判定」节存在，取值为「保持 bugfix」或「应升级 design」
"""

from typing import List, Optional, Tuple

from .. import mdparse
from ..project import SPEC_REVIEW
from . import Finding, GateContext

_AGENT = "spec-evaluator-subagent"

_DEMOTION_PHRASES = ["主线自评", "直接根据代码验证"]

_CONCLUSION_HEADER = ["BLOCK", "WARN", "INFO"]
_FINDINGS_HEADER = ["级别", "位置", "问题", "建议"]
_VALID_LEVELS = {"BLOCK", "WARN", "INFO"}
_BUGFIX_VALID = {"保持 bugfix", "应升级 design"}


def _read(change_dir, filename):
    path = change_dir / filename
    if not path.is_file():
        return None
    return path.read_text(encoding="utf-8").replace("\r\n", "\n")


def _parse_conclusion_row(table):
    """Return (block, warn, info) ints or None if malformed."""
    if not table.rows:
        return None
    row = table.rows[0]
    try:
        b = int(row.get("BLOCK", "").strip())
        w = int(row.get("WARN", "").strip())
        i = int(row.get("INFO", "").strip())
        if b < 0 or w < 0 or i < 0:
            return None
        return b, w, i
    except (ValueError, AttributeError):
        return None


def _check_report_tables(gate_prefix, text, report_file, findings):
    """Validate conclusion + findings tables per architecture §4.2.

    Appends Finding objects to `findings`.
    Returns (block_count, warn_texts) when both tables are valid; (None, []) otherwise.
    """
    root = mdparse.parse(text)

    conclusion_section = mdparse.find(root, "conclusion")
    if conclusion_section is None:
        findings.append(Finding(
            level="BLOCK",
            check="%s-conclusion-table" % gate_prefix,
            reason="报告缺少「结论」节（## 结论）",
            location=report_file,
            fix="在报告中添加「## 结论」及规定格式的表格",
        ))
        return None, []

    c_tables = mdparse.tables(conclusion_section.body)
    if not c_tables:
        findings.append(Finding(
            level="BLOCK",
            check="%s-conclusion-table" % gate_prefix,
            reason="「结论」节缺少表格",
            location=report_file,
            fix="添加格式为「| BLOCK | WARN | INFO |」的表格",
        ))
        return None, []

    c_table = c_tables[0]
    if c_table.header != _CONCLUSION_HEADER:
        findings.append(Finding(
            level="BLOCK",
            check="%s-conclusion-table" % gate_prefix,
            reason="「结论」表头不符合契约，应为「BLOCK | WARN | INFO」，实际为「%s」"
                   % " | ".join(c_table.header),
            location=report_file,
            fix="将表头改为「| BLOCK | WARN | INFO |」",
            evidence="header=%s" % "|".join(c_table.header),
        ))
        return None, []

    counts = _parse_conclusion_row(c_table)
    if counts is None:
        findings.append(Finding(
            level="BLOCK",
            check="%s-conclusion-table" % gate_prefix,
            reason="「结论」表的数据行必须是三个非负整数",
            location=report_file,
            fix="确保 BLOCK / WARN / INFO 列都填写非负整数",
        ))
        return None, []

    declared_b, declared_w, declared_i = counts

    findings_section = mdparse.find(root, "findings")
    if findings_section is None:
        findings.append(Finding(
            level="BLOCK",
            check="%s-findings-table" % gate_prefix,
            reason="报告缺少「问题清单」节（## 问题清单）",
            location=report_file,
            fix="在报告中添加「## 问题清单」及规定格式的表格",
        ))
        return None, []

    f_tables = mdparse.tables(findings_section.body)
    if not f_tables:
        findings.append(Finding(
            level="BLOCK",
            check="%s-findings-table" % gate_prefix,
            reason="「问题清单」节缺少表格",
            location=report_file,
            fix="添加格式为「| 级别 | 位置 | 问题 | 建议 |」的表格",
        ))
        return None, []

    f_table = f_tables[0]
    if f_table.header != _FINDINGS_HEADER:
        findings.append(Finding(
            level="BLOCK",
            check="%s-findings-table" % gate_prefix,
            reason="「问题清单」表头不符合契约，应为「级别 | 位置 | 问题 | 建议」，实际为「%s」"
                   % " | ".join(f_table.header),
            location=report_file,
            fix="将表头改为「| 级别 | 位置 | 问题 | 建议 |」",
            evidence="header=%s" % "|".join(f_table.header),
        ))
        return None, []

    bad_levels = [r.get("级别", "").strip() for r in f_table.rows
                  if r.get("级别", "").strip() not in _VALID_LEVELS]
    if bad_levels:
        findings.append(Finding(
            level="BLOCK",
            check="%s-findings-table" % gate_prefix,
            reason="「问题清单」有非法「级别」取值（只能是 BLOCK / WARN / INFO）：%s"
                   % "、".join(bad_levels[:5]),
            location=report_file,
            fix="将「级别」列改为 BLOCK、WARN 或 INFO 之一",
            evidence="|".join(bad_levels[:10]),
        ))
        return None, []

    actual_b = sum(1 for r in f_table.rows if r.get("级别", "").strip() == "BLOCK")
    actual_w = sum(1 for r in f_table.rows if r.get("级别", "").strip() == "WARN")
    actual_i = sum(1 for r in f_table.rows if r.get("级别", "").strip() == "INFO")

    if (declared_b, declared_w, declared_i) != (actual_b, actual_w, actual_i):
        findings.append(Finding(
            level="BLOCK",
            check="%s-conclusion-table" % gate_prefix,
            reason="「结论」表计数与「问题清单」行数不一致：结论 BLOCK=%d/WARN=%d/INFO=%d，"
                   "清单 BLOCK=%d/WARN=%d/INFO=%d"
                   % (declared_b, declared_w, declared_i, actual_b, actual_w, actual_i),
            location=report_file,
            fix="修正「结论」表的数字，使其等于「问题清单」各级别的行数",
            evidence="declared=%d/%d/%d actual=%d/%d/%d"
                     % (declared_b, declared_w, declared_i, actual_b, actual_w, actual_i),
        ))
        return None, []

    warn_texts = [r.get("问题", "").strip() for r in f_table.rows
                  if r.get("级别", "").strip() == "WARN"]
    return actual_b, warn_texts


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

    # Check 1: generated-by marker (locked).
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
            fix="由真正的独立 subagent 重新产出报告",
            evidence="|".join(found_phrases),
            locked=True,
        ))

    # Checks 3-4: conclusion + findings tables (validates format and consistency).
    block_count, _warn_texts = _check_report_tables("g5", text, SPEC_REVIEW, findings)

    # Check 5: BLOCK count must be 0.
    if block_count is not None and block_count > 0:
        findings.append(Finding(
            level="BLOCK",
            check="g5-block-count",
            reason="spec-review 问题清单有 %d 条 BLOCK，spec 未通过评审" % block_count,
            location=SPEC_REVIEW,
            fix="修复 spec 工件中的问题后重新评审，或由用户确认接受风险后放行",
            evidence="block_count=%d" % block_count,
        ))

    # Check 6: bugfix upgrade judgment (bugfix mode only).
    if ctx.meta.get("mode") == "bugfix":
        root = mdparse.parse(text)
        upgrade_section = mdparse.find(root, "bugfix-upgrade")
        if upgrade_section is None:
            findings.append(Finding(
                level="BLOCK",
                check="g5-bugfix-upgrade",
                reason="bugfix 模式下 spec-review 缺少「bugfix 升级判定」节",
                location=SPEC_REVIEW,
                fix="在 spec-review 添加「## bugfix 升级判定」节，首行写「保持 bugfix」或「应升级 design」",
            ))
        else:
            first = next((l.strip() for l in upgrade_section.body.splitlines() if l.strip()), "")
            if first not in _BUGFIX_VALID:
                findings.append(Finding(
                    level="BLOCK",
                    check="g5-bugfix-upgrade",
                    reason="「bugfix 升级判定」首行取值非法（应为「保持 bugfix」或「应升级 design」），"
                           "实际为：「%s」" % first[:80],
                    location=SPEC_REVIEW,
                    fix="将该节首行改为「保持 bugfix」或「应升级 design」",
                    evidence=first[:80],
                ))
            elif first == "应升级 design":
                findings.append(Finding(
                    level="BLOCK",
                    check="g5-bugfix-upgrade",
                    reason="spec-review 判定该 bugfix 应升级为 design 流程，请先确认是否需要走 Phase 2/3",
                    location=SPEC_REVIEW,
                    fix="使用 `spec-driven complexity set M --reason '...'` 升档后重新走流程，或放行此项",
                    evidence="应升级 design",
                ))

    return findings
