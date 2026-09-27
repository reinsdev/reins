"""Keep T9 report guidance compatible with the shared report consumers."""

import unittest
from pathlib import Path

from tests import PLUGIN
from spec_driven import mdparse


REPORTS = Path(PLUGIN) / "skills" / "spec-driven-dev" / "templates" / "reports"
CASES = (
    ("spec-review.md", "spec-evaluator", "Spec Review"),
    ("qa-report.md", "qa-evaluator", "QA Report"),
    ("code-review.md", "code-reviewer", "Code Review"),
)


class ReportTemplateContractTest(unittest.TestCase):
    def read_report(self, name):
        return (REPORTS / name).read_text(encoding="utf-8")

    def table(self, text, key, header):
        section = mdparse.find(mdparse.parse(text), key)
        self.assertIsNotNone(section, key)
        tables = mdparse.tables(section.text())
        self.assertEqual(len(tables), 1, key)
        self.assertEqual(tables[0].header, header)
        return tables[0]

    def test_report_identity_and_required_tables_survive_guidance(self):
        for name, agent, title in CASES:
            with self.subTest(report=name):
                text = self.read_report(name)
                lines = [line for line in text.splitlines() if line.strip()]
                self.assertEqual(lines[0], "<!-- generated-by: %s-subagent -->" % agent)
                self.assertEqual(lines[1], "# %s: <change-name>" % title)
                self.table(text, "conclusion", ["BLOCK", "WARN", "INFO"])
                self.table(text, "findings", ["级别", "位置", "问题", "建议"])

    def test_filled_empty_and_mixed_findings_are_parseable(self):
        placeholder = "| <BLOCK、WARN 或 INFO> | <文件:行，或 -> | <问题，一句话> | <修复建议> |"
        cases = (
            ((0, 0, 0), "", []),
            ((1, 1, 0),
             "| BLOCK | src/A.java:42 | 状态校验缺失 | 校验状态 |\n"
             "| WARN | - | 命名含义不清 | 使用业务名称 |", ["BLOCK", "WARN"]),
        )
        for name, _, _ in CASES:
            for counts, rows, levels in cases:
                with self.subTest(report=name, counts=counts):
                    text = self.read_report(name).replace(placeholder, rows)
                    for level, count in zip(("BLOCK", "WARN", "INFO"), counts):
                        text = text.replace("<%s 数>" % level, str(count))
                    summary = self.table(text, "conclusion", ["BLOCK", "WARN", "INFO"])
                    findings = self.table(text, "findings", ["级别", "位置", "问题", "建议"])
                    self.assertEqual(summary.rows, [dict(zip(("BLOCK", "WARN", "INFO"), map(str, counts)))])
                    self.assertEqual([row["级别"] for row in findings.rows], levels)

    def test_qa_results_keep_exact_ids_and_outcomes(self):
        text = self.read_report("qa-report.md").replace(
            "| <SC 编号，只写 ID> | <PASS 或 FAIL> | <测试名、命令输出或截图位置> |",
            "| SC-approval-001 | PASS | ApprovalTest: 1 test, 0 failures |\n"
            "| SC-approval-E1 | FAIL | 数据库不可用，未完成验证 |")
        table = self.table(text, "sc-results", ["SC", "结果", "证据"])
        self.assertEqual([(row["SC"], row["结果"]) for row in table.rows],
                         [("SC-approval-001", "PASS"), ("SC-approval-E1", "FAIL")])
        self.assertEqual(table.rows[1]["证据"], "数据库不可用，未完成验证")

    def test_bugfix_decision_is_first_nonempty_line(self):
        placeholder = "<仅 bugfix 模式需要：第一行只写「保持 bugfix」或「应升级 design」。>"
        for decision in ("保持 bugfix", "应升级 design"):
            with self.subTest(decision=decision):
                text = self.read_report("spec-review.md").replace(placeholder, decision)
                section = mdparse.find(mdparse.parse(text), "bugfix-upgrade")
                self.assertIsNotNone(section)
                first = next(line.strip() for line in section.body.splitlines() if line.strip())
                self.assertEqual(first, decision)


if __name__ == "__main__":
    unittest.main()
