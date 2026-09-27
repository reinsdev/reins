"""Run locked static quality checks against the project baseline.

T5's explicit exception permits writing only static-analysis-report.md here.
External quality commands own their configured tool reports.
"""

import re
from typing import List

from . import Finding, GateContext
from .. import java
from ..project import STATIC_ANALYSIS


def _block(check, reason, evidence):
    evidence = re.sub(r"\b(line|column) \d+", r"\1 ?", evidence)
    return Finding("BLOCK", check, reason, fix="修复质量检查或补齐配置与报告后重试",
                   evidence=evidence, locked=True)


def _cell(value):
    return " ".join(str(value).split()).replace("|", "\\|")


def _report(change, new, existing, repaid, errors):
    lines = ["<!-- generated-by: spec-driven gate-6.7 -->", "# Static Analysis: %s" % _cell(change),
             "", "## 结论", "", "| 新增 | 存量 | 已偿还 |", "| --- | --- | --- |",
             "| %s | %s | %s |" % (len(new), len(existing), len(repaid))]
    for title, entries in (("新增违规", new), ("存量违规", existing), ("已偿还", repaid)):
        lines += ["", "## %s" % title, "", "| 检查 | 规则 | 位置 | 说明 |", "| --- | --- | --- | --- |"]
        for entry in sorted(entries, key=lambda item: (item.check, item.file, item.rule, item.fingerprint)):
            location = "%s:%s" % (entry.file, entry.line) if entry.line else entry.file
            lines.append("| %s | %s | %s | %s |" % tuple(_cell(value) for value in
                                                       (entry.check, entry.rule, location, entry.message)))
    if errors:
        lines += ["", "## 执行失败", "", "检查未完成时，计数只包含已验证的结果。"]
        lines += ["", *["- %s：%s" % (_cell(key), _cell(value)) for key, value in sorted(errors.items())]]
    return "\n".join(lines) + "\n"


def check(ctx: GateContext) -> List[Finding]:
    findings = []
    errors = {}
    current = []
    baseline = []
    baseline_valid = False
    try:
        baseline = java.load_baseline(ctx.project.quality_baseline)
        baseline_valid = True
    except (ValueError, OSError, TypeError, KeyError) as exc:
        errors["quality-baseline"] = "质量基线缺失或无效：%s" % exc
        findings.append(_block("quality-baseline", errors["quality-baseline"], "invalid-quality-baseline"))
    if not ctx.project.config_path.is_file() or not isinstance(ctx.config.get("quality"), dict) or not ctx.config.get("quality"):
        errors["quality-config"] = "缺少 quality 配置，请由总控完成 Java 项目初始化"
        findings.append(_block("quality-config", errors["quality-config"], "missing-quality-config"))
    else:
        try:
            current, run_errors = java.run_quality(ctx.project.root, ctx.config["quality"])
            for name, reason in sorted(run_errors.items()):
                errors[name] = reason
                findings.append(_block(name, "%s 检查未完成：%s" % (name, reason), "execution:%s" % reason))
        except (ValueError, OSError, TypeError, KeyError) as exc:
            errors["quality-execution"] = "静态检查未完成：%s" % exc
            findings.append(_block("quality-execution", errors["quality-execution"], "quality-execution:%s" % exc))
    old = {entry.fingerprint: entry for entry in baseline}
    present = {entry.fingerprint: entry for entry in current}
    existing = [entry for key, entry in present.items() if key in old]
    new = [entry for key, entry in present.items() if key not in old]
    repaid = [entry for key, entry in old.items() if key not in present and entry.check not in errors]
    if not baseline_valid or "quality-config" in errors or "quality-execution" in errors:
        repaid = []
    for name in java.CHECKS:
        violations = [entry for entry in new if entry.check == name]
        if violations:
            findings.append(_block(name, "%s 有 %s 项新增违规" % (name, len(violations)),
                                   "\n".join(sorted(entry.fingerprint for entry in violations))))
    try:
        (ctx.change_dir / STATIC_ANALYSIS).write_text(_report(ctx.change, new, existing, repaid, errors), encoding="utf-8")
    except OSError as exc:
        findings.append(_block("quality-report", "无法写入静态分析报告：%s" % exc, "static-analysis-report-write"))
    return findings
