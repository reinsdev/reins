"""Tests for gate-5, gate-7, gate-8, gate-8.5, gate-8.9 (T4). Owner: T4."""

import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from tests import CLI_LIB  # noqa: F401

from spec_driven import gates, meta as meta_mod
from spec_driven.errors import BLOCK, OK, WARN
from spec_driven.project import (
    CODE_REVIEW, DEPLOY_REPORT, QA_REPORT, SPEC, SPEC_REVIEW, Project,
)

FIXTURES = Path(os.path.dirname(__file__)) / "fixtures" / "t4"

# Warn text in pass_code_review.md — used to seed retro.todos mocks.
_PASS_WARN_TEXT = "方法命名不符合驼峰规范"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _meta(mode="feature", uat=False, skipped=None):
    m = meta_mod.new("test-change", mode, "branch-1", "abc1234")
    if uat:
        m["uatAccepted"] = True
    if skipped:
        m["skipped"] = skipped
    return m


def _ctx(tmp, meta_dict=None, cfg=None):
    root = Path(tmp)
    return gates.GateContext(
        project=Project(root),
        change="test-change",
        change_dir=root,
        meta=meta_dict or _meta(),
        config=cfg or {"gates": {}},
    )


def _write(tmp, filename, content):
    path = Path(tmp) / filename
    path.write_bytes(content.encode("utf-8"))


def _fixture(name):
    return (FIXTURES / name).read_text(encoding="utf-8")


def _run(gate_id, tmp, meta_dict=None, cfg=None, waivers=()):
    ctx = _ctx(tmp, meta_dict, cfg)
    with mock.patch("spec_driven.retro.waivers", return_value=list(waivers)):
        return gates.evaluate(gate_id, ctx)


def _checks(findings):
    return [f.check for f in findings]


# ---------------------------------------------------------------------------
# Gate 5 tests
# ---------------------------------------------------------------------------

class Gate5Test(unittest.TestCase):

    # --- pass ---

    def test_pass_feature(self):
        with tempfile.TemporaryDirectory() as tmp:
            _write(tmp, SPEC_REVIEW, _fixture("g5/pass_spec_review.md"))
            findings, code = _run("5", tmp)
        self.assertEqual(code, OK)
        self.assertNotIn("g5-generated-by", _checks(findings))
        self.assertNotIn("g5-conclusion-table", _checks(findings))
        self.assertNotIn("g5-findings-table", _checks(findings))
        self.assertNotIn("g5-block-count", _checks(findings))

    def test_pass_bugfix_keep(self):
        with tempfile.TemporaryDirectory() as tmp:
            _write(tmp, SPEC_REVIEW, _fixture("g5/pass_bugfix_keep_spec_review.md"))
            findings, code = _run("5", tmp, meta_dict=_meta(mode="bugfix"))
        self.assertEqual(code, OK)
        self.assertNotIn("g5-bugfix-upgrade", _checks(findings))

    # --- generated-by ---

    def test_fail_missing_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            findings, code = _run("5", tmp)
        self.assertEqual(code, BLOCK)
        self.assertIn("g5-generated-by", _checks(findings))
        for f in findings:
            if f.check == "g5-generated-by":
                self.assertTrue(f.locked)

    def test_fail_no_marker(self):
        with tempfile.TemporaryDirectory() as tmp:
            _write(tmp, SPEC_REVIEW, _fixture("g5/fail_no_marker_spec_review.md"))
            findings, code = _run("5", tmp)
        self.assertEqual(code, BLOCK)
        self.assertIn("g5-generated-by", _checks(findings))
        for f in findings:
            if f.check == "g5-generated-by":
                self.assertTrue(f.locked)

    # --- demotion phrase ---

    def test_fail_demotion_phrase(self):
        with tempfile.TemporaryDirectory() as tmp:
            _write(tmp, SPEC_REVIEW, _fixture("g5/fail_demotion_spec_review.md"))
            findings, code = _run("5", tmp)
        self.assertEqual(code, BLOCK)
        self.assertIn("g5-demotion-phrase", _checks(findings))
        for f in findings:
            if f.check == "g5-demotion-phrase":
                self.assertTrue(f.locked)

    # --- conclusion table format ---

    def test_fail_missing_conclusion(self):
        with tempfile.TemporaryDirectory() as tmp:
            _write(tmp, SPEC_REVIEW, _fixture("g5/fail_missing_conclusion_spec_review.md"))
            findings, code = _run("5", tmp)
        self.assertEqual(code, BLOCK)
        self.assertIn("g5-conclusion-table", _checks(findings))

    def test_fail_bad_header(self):
        with tempfile.TemporaryDirectory() as tmp:
            _write(tmp, SPEC_REVIEW, _fixture("g5/fail_bad_header_spec_review.md"))
            findings, code = _run("5", tmp)
        self.assertEqual(code, BLOCK)
        self.assertIn("g5-conclusion-table", _checks(findings))

    def test_fail_count_mismatch(self):
        with tempfile.TemporaryDirectory() as tmp:
            _write(tmp, SPEC_REVIEW, _fixture("g5/fail_count_mismatch_spec_review.md"))
            findings, code = _run("5", tmp)
        self.assertEqual(code, BLOCK)
        self.assertIn("g5-conclusion-table", _checks(findings))
        for f in findings:
            if f.check == "g5-conclusion-table":
                self.assertIn("declared=", f.evidence)

    # --- findings table format ---

    def test_fail_bad_level(self):
        with tempfile.TemporaryDirectory() as tmp:
            _write(tmp, SPEC_REVIEW, _fixture("g5/fail_bad_level_spec_review.md"))
            findings, code = _run("5", tmp)
        self.assertEqual(code, BLOCK)
        self.assertIn("g5-findings-table", _checks(findings))

    # --- block count ---

    def test_fail_block_count(self):
        with tempfile.TemporaryDirectory() as tmp:
            _write(tmp, SPEC_REVIEW, _fixture("g5/fail_has_block_spec_review.md"))
            findings, code = _run("5", tmp)
        self.assertEqual(code, BLOCK)
        self.assertIn("g5-block-count", _checks(findings))
        for f in findings:
            if f.check == "g5-block-count":
                self.assertIn("block_count=1", f.evidence)

    # --- bugfix upgrade ---

    def test_fail_bugfix_upgrade_design(self):
        with tempfile.TemporaryDirectory() as tmp:
            _write(tmp, SPEC_REVIEW, _fixture("g5/fail_bugfix_upgrade_spec_review.md"))
            findings, code = _run("5", tmp, meta_dict=_meta(mode="bugfix"))
        self.assertEqual(code, BLOCK)
        self.assertIn("g5-bugfix-upgrade", _checks(findings))
        for f in findings:
            if f.check == "g5-bugfix-upgrade":
                self.assertEqual(f.evidence, "应升级 design")

    def test_fail_bugfix_upgrade_missing_section(self):
        # feature report has no bugfix-upgrade section; in bugfix mode that's a BLOCK.
        with tempfile.TemporaryDirectory() as tmp:
            _write(tmp, SPEC_REVIEW, _fixture("g5/pass_spec_review.md"))
            findings, code = _run("5", tmp, meta_dict=_meta(mode="bugfix"))
        self.assertEqual(code, BLOCK)
        self.assertIn("g5-bugfix-upgrade", _checks(findings))

    def test_fail_bugfix_upgrade_invalid_value(self):
        report = (
            "<!-- generated-by: spec-evaluator-subagent -->\n"
            "## 结论\n\n| BLOCK | WARN | INFO |\n| --- | --- | --- |\n| 0 | 0 | 0 |\n\n"
            "## 问题清单\n\n| 级别 | 位置 | 问题 | 建议 |\n| --- | --- | --- | --- |\n\n"
            "## bugfix 升级判定\n\n可能需要升级\n"
        )
        with tempfile.TemporaryDirectory() as tmp:
            _write(tmp, SPEC_REVIEW, report)
            findings, code = _run("5", tmp, meta_dict=_meta(mode="bugfix"))
        self.assertEqual(code, BLOCK)
        self.assertIn("g5-bugfix-upgrade", _checks(findings))

    def test_bugfix_upgrade_not_checked_in_feature_mode(self):
        # Even if the report has "应升级 design" text, feature mode ignores the section.
        with tempfile.TemporaryDirectory() as tmp:
            _write(tmp, SPEC_REVIEW, _fixture("g5/fail_bugfix_upgrade_spec_review.md"))
            findings, code = _run("5", tmp, meta_dict=_meta(mode="feature"))
        self.assertNotIn("g5-bugfix-upgrade", _checks(findings))

    def test_skipped_phase_passes(self):
        with tempfile.TemporaryDirectory() as tmp:
            findings, code = _run("5", tmp, meta_dict=_meta(skipped={"5": "S 档"}))
        self.assertEqual(code, OK)
        self.assertEqual(findings[0].check, "skipped")


# ---------------------------------------------------------------------------
# Gate 7 tests
# ---------------------------------------------------------------------------

class Gate7Test(unittest.TestCase):

    # --- pass ---

    def test_pass_all_sc_pass(self):
        with tempfile.TemporaryDirectory() as tmp:
            _write(tmp, QA_REPORT, _fixture("g7/pass_qa_report.md"))
            _write(tmp, SPEC, _fixture("g7/pass_spec.md"))
            findings, code = _run("7", tmp)
        self.assertEqual(code, OK)

    # --- generated-by ---

    def test_fail_missing_qa_report(self):
        with tempfile.TemporaryDirectory() as tmp:
            _write(tmp, SPEC, _fixture("g7/pass_spec.md"))
            findings, code = _run("7", tmp)
        self.assertEqual(code, BLOCK)
        self.assertIn("g7-generated-by", _checks(findings))
        for f in findings:
            if f.check == "g7-generated-by":
                self.assertTrue(f.locked)

    # --- demotion phrase ---

    def test_fail_demotion_phrase(self):
        report = (
            "<!-- generated-by: qa-evaluator-subagent -->\n"
            "主线自评结果：全部通过\n"
            "## 结论\n\n| BLOCK | WARN | INFO |\n| --- | --- | --- |\n| 0 | 0 | 0 |\n\n"
            "## 问题清单\n\n| 级别 | 位置 | 问题 | 建议 |\n| --- | --- | --- | --- |\n\n"
            "## SC 验证结果\n\n| SC | 结果 | 证据 |\n| --- | --- | --- |\n"
        )
        with tempfile.TemporaryDirectory() as tmp:
            _write(tmp, QA_REPORT, report)
            _write(tmp, SPEC, _fixture("g7/pass_spec.md"))
            findings, code = _run("7", tmp)
        self.assertEqual(code, BLOCK)
        self.assertIn("g7-demotion-phrase", _checks(findings))
        for f in findings:
            if f.check == "g7-demotion-phrase":
                self.assertTrue(f.locked)

    # --- conclusion table ---

    def test_fail_missing_conclusion(self):
        report = (
            "<!-- generated-by: qa-evaluator-subagent -->\n"
            "## 问题清单\n\n| 级别 | 位置 | 问题 | 建议 |\n| --- | --- | --- | --- |\n\n"
            "## SC 验证结果\n\n| SC | 结果 | 证据 |\n| --- | --- | --- |\n"
        )
        with tempfile.TemporaryDirectory() as tmp:
            _write(tmp, QA_REPORT, report)
            _write(tmp, SPEC, _fixture("g7/pass_spec.md"))
            findings, code = _run("7", tmp)
        self.assertEqual(code, BLOCK)
        self.assertIn("g7-conclusion-table", _checks(findings))

    def test_fail_count_mismatch(self):
        report = (
            "<!-- generated-by: qa-evaluator-subagent -->\n"
            "## 结论\n\n| BLOCK | WARN | INFO |\n| --- | --- | --- |\n| 2 | 0 | 0 |\n\n"
            "## 问题清单\n\n| 级别 | 位置 | 问题 | 建议 |\n| --- | --- | --- | --- |\n"
            "| BLOCK | - | 只有一条 | 修复 |\n\n"
            "## SC 验证结果\n\n| SC | 结果 | 证据 |\n| --- | --- | --- |\n"
        )
        with tempfile.TemporaryDirectory() as tmp:
            _write(tmp, QA_REPORT, report)
            _write(tmp, SPEC, "# Spec\n")
            findings, code = _run("7", tmp)
        self.assertEqual(code, BLOCK)
        self.assertIn("g7-conclusion-table", _checks(findings))

    # --- bad header ---

    def test_fail_bad_conclusion_header(self):
        report = (
            "<!-- generated-by: qa-evaluator-subagent -->\n"
            "## 结论\n\n| Blockers | Warnings | Infos |\n| --- | --- | --- |\n| 0 | 0 | 0 |\n\n"
            "## 问题清单\n\n| 级别 | 位置 | 问题 | 建议 |\n| --- | --- | --- | --- |\n\n"
            "## SC 验证结果\n\n| SC | 结果 | 证据 |\n| --- | --- | --- |\n"
        )
        with tempfile.TemporaryDirectory() as tmp:
            _write(tmp, QA_REPORT, report)
            _write(tmp, SPEC, "# Spec\n")
            findings, code = _run("7", tmp)
        self.assertEqual(code, BLOCK)
        self.assertIn("g7-conclusion-table", _checks(findings))

    # --- bad level ---

    def test_fail_bad_level(self):
        report = (
            "<!-- generated-by: qa-evaluator-subagent -->\n"
            "## 结论\n\n| BLOCK | WARN | INFO |\n| --- | --- | --- |\n| 0 | 0 | 1 |\n\n"
            "## 问题清单\n\n| 级别 | 位置 | 问题 | 建议 |\n| --- | --- | --- | --- |\n"
            "| NOTE | - | 非法级别 | 无 |\n\n"
            "## SC 验证结果\n\n| SC | 结果 | 证据 |\n| --- | --- | --- |\n"
        )
        with tempfile.TemporaryDirectory() as tmp:
            _write(tmp, QA_REPORT, report)
            _write(tmp, SPEC, "# Spec\n")
            findings, code = _run("7", tmp)
        self.assertEqual(code, BLOCK)
        self.assertIn("g7-findings-table", _checks(findings))

    # --- SC results table ---

    def test_fail_bad_sc_results_header(self):
        with tempfile.TemporaryDirectory() as tmp:
            _write(tmp, QA_REPORT, _fixture("g7/fail_bad_sc_header_qa_report.md"))
            _write(tmp, SPEC, _fixture("g7/pass_spec.md"))
            findings, code = _run("7", tmp)
        self.assertEqual(code, BLOCK)
        self.assertIn("g7-sc-results-table", _checks(findings))

    def test_fail_sc_missing_row(self):
        """SC present in spec.md but missing from SC 验证结果 table."""
        with tempfile.TemporaryDirectory() as tmp:
            _write(tmp, QA_REPORT, _fixture("g7/fail_sc_missing_row_qa_report.md"))
            _write(tmp, SPEC, _fixture("g7/pass_spec.md"))
            findings, code = _run("7", tmp)
        self.assertEqual(code, BLOCK)
        self.assertIn("g7-sc-pass", _checks(findings))

    def test_fail_sc_result_is_fail(self):
        with tempfile.TemporaryDirectory() as tmp:
            _write(tmp, QA_REPORT, _fixture("g7/fail_sc_not_pass_qa_report.md"))
            _write(tmp, SPEC, _fixture("g7/pass_spec.md"))
            findings, code = _run("7", tmp)
        self.assertEqual(code, BLOCK)
        self.assertIn("g7-sc-pass", _checks(findings))
        for f in findings:
            if f.check == "g7-sc-pass":
                self.assertIn("SC-batch-approve-002", f.evidence)

    def test_fail_sc_id_extracted_from_full_title(self):
        """Regression: '### SC-c-001: 场景标题' — ID is extracted, not compared verbatim."""
        spec = (
            "# Capability: c (`c`)\n\n"
            "## REQ-c-001: 需求\n\n"
            "### SC-c-001: 场景标题带冒号和描述\n\nWHEN x\nTHEN y\n"
        )
        qa = (
            "<!-- generated-by: qa-evaluator-subagent -->\n"
            "## 结论\n\n| BLOCK | WARN | INFO |\n| --- | --- | --- |\n| 0 | 0 | 0 |\n\n"
            "## 问题清单\n\n| 级别 | 位置 | 问题 | 建议 |\n| --- | --- | --- | --- |\n\n"
            "## SC 验证结果\n\n| SC | 结果 | 证据 |\n| --- | --- | --- |\n"
            "| SC-c-001 | PASS | ok |\n"
        )
        with tempfile.TemporaryDirectory() as tmp:
            _write(tmp, SPEC, spec)
            _write(tmp, QA_REPORT, qa)
            findings, code = _run("7", tmp)
        self.assertEqual(code, OK)

    def test_no_sc_in_spec_passes(self):
        spec_no_sc = "# Spec\n\n## 接口契约\n\nGET /api/status\n"
        with tempfile.TemporaryDirectory() as tmp:
            _write(tmp, QA_REPORT, _fixture("g7/pass_qa_report.md"))
            _write(tmp, SPEC, spec_no_sc)
            findings, code = _run("7", tmp)
        self.assertEqual(code, OK)

    def test_skipped_phase_passes(self):
        with tempfile.TemporaryDirectory() as tmp:
            findings, code = _run("7", tmp, meta_dict=_meta(skipped={"7": "S 档"}))
        self.assertEqual(code, OK)
        self.assertEqual(findings[0].check, "skipped")


# ---------------------------------------------------------------------------
# Gate 8 tests
# ---------------------------------------------------------------------------

class Gate8Test(unittest.TestCase):

    # --- pass ---

    def test_pass_warn_in_todos(self):
        with tempfile.TemporaryDirectory() as tmp:
            _write(tmp, CODE_REVIEW, _fixture("g8/pass_code_review.md"))
            with mock.patch("spec_driven.retro.todos", return_value=[_PASS_WARN_TEXT]):
                findings, code = _run("8", tmp)
        self.assertEqual(code, OK)

    # --- generated-by ---

    def test_fail_missing_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            findings, code = _run("8", tmp)
        self.assertEqual(code, BLOCK)
        self.assertIn("g8-generated-by", _checks(findings))

    def test_fail_no_marker(self):
        report = (
            "# Code Review\n\n"
            "## 结论\n\n| BLOCK | WARN | INFO |\n| --- | --- | --- |\n| 0 | 0 | 0 |\n\n"
            "## 问题清单\n\n| 级别 | 位置 | 问题 | 建议 |\n| --- | --- | --- | --- |\n"
        )
        with tempfile.TemporaryDirectory() as tmp:
            _write(tmp, CODE_REVIEW, report)
            with mock.patch("spec_driven.retro.todos", return_value=[]):
                findings, code = _run("8", tmp)
        self.assertEqual(code, BLOCK)
        self.assertIn("g8-generated-by", _checks(findings))

    # --- demotion phrase ---

    def test_fail_demotion_phrase(self):
        report = (
            "<!-- generated-by: code-reviewer-subagent -->\n"
            "直接根据代码验证了安全性。\n"
            "## 结论\n\n| BLOCK | WARN | INFO |\n| --- | --- | --- |\n| 0 | 0 | 0 |\n\n"
            "## 问题清单\n\n| 级别 | 位置 | 问题 | 建议 |\n| --- | --- | --- | --- |\n"
        )
        with tempfile.TemporaryDirectory() as tmp:
            _write(tmp, CODE_REVIEW, report)
            with mock.patch("spec_driven.retro.todos", return_value=[]):
                findings, code = _run("8", tmp)
        self.assertEqual(code, BLOCK)
        self.assertIn("g8-demotion-phrase", _checks(findings))
        for f in findings:
            if f.check == "g8-demotion-phrase":
                self.assertTrue(f.locked)

    # --- conclusion table ---

    def test_fail_missing_conclusion(self):
        with tempfile.TemporaryDirectory() as tmp:
            _write(tmp, CODE_REVIEW, _fixture("g8/fail_missing_conclusion_code_review.md"))
            with mock.patch("spec_driven.retro.todos", return_value=[]):
                findings, code = _run("8", tmp)
        self.assertEqual(code, BLOCK)
        self.assertIn("g8-conclusion-table", _checks(findings))

    def test_fail_bad_header(self):
        with tempfile.TemporaryDirectory() as tmp:
            _write(tmp, CODE_REVIEW, _fixture("g8/fail_bad_header_code_review.md"))
            with mock.patch("spec_driven.retro.todos", return_value=[]):
                findings, code = _run("8", tmp)
        self.assertEqual(code, BLOCK)
        self.assertIn("g8-conclusion-table", _checks(findings))

    def test_fail_count_mismatch(self):
        with tempfile.TemporaryDirectory() as tmp:
            _write(tmp, CODE_REVIEW, _fixture("g8/fail_count_mismatch_code_review.md"))
            with mock.patch("spec_driven.retro.todos", return_value=[]):
                findings, code = _run("8", tmp)
        self.assertEqual(code, BLOCK)
        self.assertIn("g8-conclusion-table", _checks(findings))

    # --- bad level ---

    def test_fail_bad_level(self):
        with tempfile.TemporaryDirectory() as tmp:
            _write(tmp, CODE_REVIEW, _fixture("g8/fail_bad_level_code_review.md"))
            with mock.patch("spec_driven.retro.todos", return_value=[]):
                findings, code = _run("8", tmp)
        self.assertEqual(code, BLOCK)
        self.assertIn("g8-findings-table", _checks(findings))

    # --- block count ---

    def test_fail_has_block(self):
        with tempfile.TemporaryDirectory() as tmp:
            _write(tmp, CODE_REVIEW, _fixture("g8/fail_has_block_code_review.md"))
            with mock.patch("spec_driven.retro.todos", return_value=["方法命名不符合驼峰规范"]):
                findings, code = _run("8", tmp)
        self.assertEqual(code, BLOCK)
        self.assertIn("g8-block-count", _checks(findings))
        for f in findings:
            if f.check == "g8-block-count":
                self.assertIn("block_count=1", f.evidence)

    # --- warn in todos ---

    def test_fail_warn_not_in_todos(self):
        with tempfile.TemporaryDirectory() as tmp:
            _write(tmp, CODE_REVIEW, _fixture("g8/pass_code_review.md"))
            with mock.patch("spec_driven.retro.todos", return_value=[]):
                findings, code = _run("8", tmp)
        self.assertEqual(code, BLOCK)
        self.assertIn("g8-warn-in-todos", _checks(findings))

    def test_fail_warn_partial_match_not_enough(self):
        """前 40 字匹配不再被接受，必须完全相等。"""
        # The WARN text is "方法命名不符合驼峰规范", a prefix of it won't count.
        prefix = _PASS_WARN_TEXT[:4]
        with tempfile.TemporaryDirectory() as tmp:
            _write(tmp, CODE_REVIEW, _fixture("g8/pass_code_review.md"))
            with mock.patch("spec_driven.retro.todos", return_value=[prefix]):
                findings, code = _run("8", tmp)
        self.assertEqual(code, BLOCK)
        self.assertIn("g8-warn-in-todos", _checks(findings))

    def test_skipped_phase_passes(self):
        with tempfile.TemporaryDirectory() as tmp:
            findings, code = _run("8", tmp, meta_dict=_meta(skipped={"8": "S 档"}))
        self.assertEqual(code, OK)
        self.assertEqual(findings[0].check, "skipped")


# ---------------------------------------------------------------------------
# Gate 8.5 tests  (unchanged logic — just regression guard)
# ---------------------------------------------------------------------------

class Gate85Test(unittest.TestCase):

    def test_pass_deploy_report_passed(self):
        with tempfile.TemporaryDirectory() as tmp:
            _write(tmp, DEPLOY_REPORT, (FIXTURES / "g8_5/pass_deploy_report.md").read_text("utf-8"))
            findings, code = _run("8.5", tmp)
        self.assertEqual(code, OK)

    def test_fail_missing_deploy_report(self):
        with tempfile.TemporaryDirectory() as tmp:
            findings, code = _run("8.5", tmp)
        self.assertEqual(code, BLOCK)
        self.assertIn("g8_5-deploy-report", _checks(findings))

    def test_fail_conclusion_not_passed_chinese(self):
        with tempfile.TemporaryDirectory() as tmp:
            _write(tmp, DEPLOY_REPORT, (FIXTURES / "g8_5/fail_not_passed_zh.md").read_text("utf-8"))
            findings, code = _run("8.5", tmp)
        self.assertEqual(code, BLOCK)

    def test_fail_conclusion_not_passed_english(self):
        with tempfile.TemporaryDirectory() as tmp:
            _write(tmp, DEPLOY_REPORT, (FIXTURES / "g8_5/fail_not_passed_en.md").read_text("utf-8"))
            findings, code = _run("8.5", tmp)
        self.assertEqual(code, BLOCK)

    def test_fail_conclusion_explicit_failed(self):
        with tempfile.TemporaryDirectory() as tmp:
            _write(tmp, DEPLOY_REPORT, (FIXTURES / "g8_5/fail_explicit_failed.md").read_text("utf-8"))
            findings, code = _run("8.5", tmp)
        self.assertEqual(code, BLOCK)

    def test_pass_waiver_matches_framework_fingerprint(self):
        from spec_driven.retro import Waiver
        f = gates.Finding(level="BLOCK", check="g8_5-deploy-report",
                          reason="deploy-report.md 不存在，部署验收未完成")
        fp = gates.fingerprint("8.5", f)
        waiver = Waiver("2026-01-01 10:00", "8.5", "g8_5-deploy-report",
                        "跳过部署", "无法本地部署", "alice", fp)
        with tempfile.TemporaryDirectory() as tmp:
            findings, code = _run("8.5", tmp, waivers=[waiver])
        self.assertEqual(code, OK)

    def test_skipped_phase_passes(self):
        with tempfile.TemporaryDirectory() as tmp:
            findings, code = _run("8.5", tmp, meta_dict=_meta(skipped={"8.5": "S 档"}))
        self.assertEqual(code, OK)


# ---------------------------------------------------------------------------
# Gate 8.9 tests  (unchanged logic — just regression guard)
# ---------------------------------------------------------------------------

class Gate89Test(unittest.TestCase):

    def test_pass_uat_accepted(self):
        with tempfile.TemporaryDirectory() as tmp:
            findings, code = _run("8.9", tmp, meta_dict=_meta(uat=True))
        self.assertEqual(code, OK)

    def test_fail_uat_not_accepted(self):
        with tempfile.TemporaryDirectory() as tmp:
            findings, code = _run("8.9", tmp, meta_dict=_meta(uat=False))
        self.assertEqual(code, BLOCK)
        self.assertIn("g8_9-uat-accepted", _checks(findings))
        for f in findings:
            if f.check == "g8_9-uat-accepted":
                self.assertTrue(f.locked)

    def test_locked_config_cannot_lower(self):
        cfg = {"gates": {"8.9": {"level": "warn"}}}
        with tempfile.TemporaryDirectory() as tmp:
            findings, code = _run("8.9", tmp, meta_dict=_meta(uat=False), cfg=cfg)
        self.assertEqual(code, BLOCK)

    def test_skipped_phase_passes(self):
        with tempfile.TemporaryDirectory() as tmp:
            findings, code = _run("8.9", tmp, meta_dict=_meta(skipped={"8.9": "manual"}))
        self.assertEqual(code, OK)


if __name__ == "__main__":
    unittest.main()
