"""Tests for gate-5, gate-7, gate-8, gate-8.5, gate-8.9 (T4). Owner: T4."""

import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

# Ensure CLI lib is on path.
from tests import CLI_LIB  # noqa: F401

from spec_driven import gates, meta as meta_mod
from spec_driven.errors import BLOCK, OK, WARN
from spec_driven.project import (
    CODE_REVIEW, DEPLOY_REPORT, QA_REPORT, SPEC, SPEC_REVIEW, Project,
)

FIXTURES = Path(os.path.dirname(__file__)) / "fixtures" / "t4"


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


def _ctx(tmp, meta_dict=None, cfg=None, extra=None):
    root = Path(tmp)
    return gates.GateContext(
        project=Project(root),
        change="test-change",
        change_dir=root,
        meta=meta_dict or _meta(),
        config=cfg or {"gates": {}},
        extra=extra or {},
    )


def _write(tmp, filename, content):
    path = Path(tmp) / filename
    path.write_bytes(content.encode("utf-8"))


def _fixture(name):
    return (FIXTURES / name).read_text(encoding="utf-8")


def _run(gate_id, tmp, meta_dict=None, cfg=None, extra=None, waivers=()):
    ctx = _ctx(tmp, meta_dict, cfg, extra)
    with mock.patch("spec_driven.retro.waivers", return_value=list(waivers)):
        return gates.evaluate(gate_id, ctx)


# ---------------------------------------------------------------------------
# Gate 5 tests
# ---------------------------------------------------------------------------

class Gate5Test(unittest.TestCase):

    def test_pass_clean_report(self):
        with tempfile.TemporaryDirectory() as tmp:
            _write(tmp, SPEC_REVIEW, _fixture("g5/pass_spec_review.md"))
            findings, code = _run("5", tmp)
        # gate-5 only produces findings for its own checks; the report's WARN
        # lines are not surfaced as gate-5 findings.
        self.assertEqual(code, OK)
        checks = [f.check for f in findings if f.level != "INFO"]
        self.assertNotIn("g5-generated-by", checks)
        self.assertNotIn("g5-demotion-phrase", checks)
        self.assertNotIn("g5-block-count", checks)

    def test_fail_missing_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            findings, code = _run("5", tmp)
        self.assertEqual(code, BLOCK)
        checks = [f.check for f in findings]
        self.assertIn("g5-generated-by", checks)
        locked = {f.check: f.locked for f in findings}
        self.assertTrue(locked["g5-generated-by"])

    def test_fail_no_marker(self):
        with tempfile.TemporaryDirectory() as tmp:
            _write(tmp, SPEC_REVIEW, _fixture("g5/fail_no_marker_spec_review.md"))
            findings, code = _run("5", tmp)
        self.assertEqual(code, BLOCK)
        checks = [f.check for f in findings]
        self.assertIn("g5-generated-by", checks)
        for f in findings:
            if f.check == "g5-generated-by":
                self.assertTrue(f.locked)

    def test_fail_block_count(self):
        with tempfile.TemporaryDirectory() as tmp:
            _write(tmp, SPEC_REVIEW, _fixture("g5/fail_has_block_spec_review.md"))
            findings, code = _run("5", tmp)
        self.assertEqual(code, BLOCK)
        checks = [f.check for f in findings]
        self.assertIn("g5-block-count", checks)
        for f in findings:
            if f.check == "g5-block-count":
                self.assertIn("block_count=1", f.evidence)

    def test_fail_demotion_phrase(self):
        with tempfile.TemporaryDirectory() as tmp:
            _write(tmp, SPEC_REVIEW, _fixture("g5/fail_demotion_spec_review.md"))
            findings, code = _run("5", tmp)
        self.assertEqual(code, BLOCK)
        checks = [f.check for f in findings]
        self.assertIn("g5-demotion-phrase", checks)
        for f in findings:
            if f.check == "g5-demotion-phrase":
                self.assertTrue(f.locked)

    def test_fail_bugfix_upgrade(self):
        with tempfile.TemporaryDirectory() as tmp:
            _write(tmp, SPEC_REVIEW, _fixture("g5/fail_bugfix_upgrade_spec_review.md"))
            findings, code = _run("5", tmp, meta_dict=_meta(mode="bugfix"))
        self.assertEqual(code, BLOCK)
        checks = [f.check for f in findings]
        self.assertIn("g5-bugfix-upgrade", checks)

    def test_bugfix_upgrade_not_triggered_for_feature(self):
        with tempfile.TemporaryDirectory() as tmp:
            _write(tmp, SPEC_REVIEW, _fixture("g5/fail_bugfix_upgrade_spec_review.md"))
            findings, code = _run("5", tmp, meta_dict=_meta(mode="feature"))
        checks = [f.check for f in findings]
        self.assertNotIn("g5-bugfix-upgrade", checks)

    def test_skipped_phase_passes(self):
        with tempfile.TemporaryDirectory() as tmp:
            findings, code = _run("5", tmp, meta_dict=_meta(skipped={"5": "S 档"}))
        self.assertEqual(code, OK)
        self.assertEqual(findings[0].check, "skipped")


# ---------------------------------------------------------------------------
# Gate 7 tests
# ---------------------------------------------------------------------------

class Gate7Test(unittest.TestCase):

    def test_pass_all_sc_pass(self):
        """SC titles with description suffix (e.g. '### SC-xxx-001: 标题') are correctly matched."""
        with tempfile.TemporaryDirectory() as tmp:
            _write(tmp, QA_REPORT, _fixture("g7/pass_qa_report.md"))
            _write(tmp, SPEC, _fixture("g7/pass_spec.md"))
            findings, code = _run("7", tmp)
        self.assertEqual(code, OK)
        checks = [f.check for f in findings if f.level != "INFO"]
        self.assertEqual(checks, [])

    def test_fail_sc_id_extracted_from_full_title(self):
        """Regression: title '### SC-batch-approve-001: 全部审批通过' must not be compared
        verbatim against the qa-report — only the ID part should be extracted."""
        spec = (
            "# Capability: c (`c`)\n\n"
            "## REQ-c-001: 需求\n\n"
            "### SC-c-001: 场景标题带冒号和描述\n\n"
            "WHEN x\nTHEN y\n"
        )
        qa = (
            "<!-- generated-by: qa-evaluator-subagent -->\n\n"
            "| SC | 结果 |\n| --- | --- |\n| SC-c-001 | PASS |\n"
        )
        with tempfile.TemporaryDirectory() as tmp:
            _write(tmp, SPEC, spec)
            _write(tmp, QA_REPORT, qa)
            findings, code = _run("7", tmp)
        self.assertEqual(code, OK)
        checks = [f.check for f in findings if f.level == "BLOCK"]
        self.assertNotIn("g7-sc-pass", checks)

    def test_fail_missing_qa_report(self):
        with tempfile.TemporaryDirectory() as tmp:
            _write(tmp, SPEC, _fixture("g7/pass_spec.md"))
            findings, code = _run("7", tmp)
        self.assertEqual(code, BLOCK)
        checks = [f.check for f in findings]
        self.assertIn("g7-generated-by", checks)
        for f in findings:
            if f.check == "g7-generated-by":
                self.assertTrue(f.locked)

    def test_fail_sc_not_pass(self):
        with tempfile.TemporaryDirectory() as tmp:
            _write(tmp, QA_REPORT, _fixture("g7/fail_sc_not_pass_qa_report.md"))
            _write(tmp, SPEC, _fixture("g7/pass_spec.md"))
            findings, code = _run("7", tmp)
        self.assertEqual(code, BLOCK)
        checks = [f.check for f in findings]
        self.assertIn("g7-sc-pass", checks)
        for f in findings:
            if f.check == "g7-sc-pass":
                self.assertIn("SC-batch-approve-002", f.evidence)

    def test_fail_demotion_phrase(self):
        report = "<!-- generated-by: qa-evaluator-subagent -->\n\n主线自评结果：全部通过\n"
        with tempfile.TemporaryDirectory() as tmp:
            _write(tmp, QA_REPORT, report)
            _write(tmp, SPEC, _fixture("g7/pass_spec.md"))
            findings, code = _run("7", tmp)
        self.assertEqual(code, BLOCK)
        checks = [f.check for f in findings]
        self.assertIn("g7-demotion-phrase", checks)
        for f in findings:
            if f.check == "g7-demotion-phrase":
                self.assertTrue(f.locked)

    def test_fail_missing_spec(self):
        with tempfile.TemporaryDirectory() as tmp:
            _write(tmp, QA_REPORT, _fixture("g7/pass_qa_report.md"))
            findings, code = _run("7", tmp)
        self.assertEqual(code, BLOCK)
        checks = [f.check for f in findings]
        self.assertIn("g7-sc-pass", checks)

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

    def test_pass_no_blocks_warns_in_todos(self):
        warn_text = "naming-convention — UserService.java 方法命名不规范 → 改为驼峰命名  #aa112233"
        with tempfile.TemporaryDirectory() as tmp:
            _write(tmp, CODE_REVIEW, _fixture("g8/pass_code_review.md"))
            with mock.patch("spec_driven.retro.todos", return_value=[warn_text[:40]]):
                findings, code = _run("8", tmp)
        self.assertEqual(code, OK)

    def test_fail_missing_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            findings, code = _run("8", tmp)
        self.assertEqual(code, BLOCK)
        checks = [f.check for f in findings]
        self.assertIn("g8-generated-by", checks)

    def test_fail_has_block(self):
        with tempfile.TemporaryDirectory() as tmp:
            _write(tmp, CODE_REVIEW, _fixture("g8/fail_has_block_code_review.md"))
            with mock.patch("spec_driven.retro.todos", return_value=["缺少关键操作日志"]):
                findings, code = _run("8", tmp)
        self.assertEqual(code, BLOCK)
        checks = [f.check for f in findings]
        self.assertIn("g8-block-count", checks)

    def test_fail_warn_not_in_todos(self):
        with tempfile.TemporaryDirectory() as tmp:
            _write(tmp, CODE_REVIEW, _fixture("g8/pass_code_review.md"))
            with mock.patch("spec_driven.retro.todos", return_value=[]):
                findings, code = _run("8", tmp)
        self.assertEqual(code, BLOCK)
        checks = [f.check for f in findings]
        self.assertIn("g8-warn-in-todos", checks)

    def test_fail_demotion_phrase(self):
        report = "<!-- generated-by: code-reviewer-subagent -->\n\n直接根据代码验证了安全性。\n"
        with tempfile.TemporaryDirectory() as tmp:
            _write(tmp, CODE_REVIEW, report)
            with mock.patch("spec_driven.retro.todos", return_value=[]):
                findings, code = _run("8", tmp)
        self.assertEqual(code, BLOCK)
        checks = [f.check for f in findings]
        self.assertIn("g8-demotion-phrase", checks)
        for f in findings:
            if f.check == "g8-demotion-phrase":
                self.assertTrue(f.locked)

    def test_fail_no_marker(self):
        report = "# Code Review\n\n[WARN] something — x → y  #12345678\n"
        with tempfile.TemporaryDirectory() as tmp:
            _write(tmp, CODE_REVIEW, report)
            with mock.patch("spec_driven.retro.todos", return_value=["something"]):
                findings, code = _run("8", tmp)
        self.assertEqual(code, BLOCK)
        checks = [f.check for f in findings]
        self.assertIn("g8-generated-by", checks)

    def test_skipped_phase_passes(self):
        with tempfile.TemporaryDirectory() as tmp:
            findings, code = _run("8", tmp, meta_dict=_meta(skipped={"8": "S 档"}))
        self.assertEqual(code, OK)
        self.assertEqual(findings[0].check, "skipped")


# ---------------------------------------------------------------------------
# Gate 8.5 tests
# ---------------------------------------------------------------------------

class Gate85Test(unittest.TestCase):

    def test_pass_deploy_report_passed(self):
        with tempfile.TemporaryDirectory() as tmp:
            _write(tmp, DEPLOY_REPORT, _fixture("g8_5/pass_deploy_report.md"))
            findings, code = _run("8.5", tmp)
        self.assertEqual(code, OK)

    def test_fail_missing_deploy_report(self):
        with tempfile.TemporaryDirectory() as tmp:
            findings, code = _run("8.5", tmp)
        self.assertEqual(code, BLOCK)
        checks = [f.check for f in findings]
        self.assertIn("g8_5-deploy-report", checks)

    def test_fail_deploy_report_not_passed(self):
        with tempfile.TemporaryDirectory() as tmp:
            _write(tmp, DEPLOY_REPORT, _fixture("g8_5/fail_deploy_report.md"))
            findings, code = _run("8.5", tmp)
        self.assertEqual(code, BLOCK)
        checks = [f.check for f in findings]
        self.assertIn("g8_5-deploy-report", checks)

    def test_fail_conclusion_not_passed_chinese(self):
        """'未通过' contains '通过' but must NOT be treated as passed (substring trap)."""
        with tempfile.TemporaryDirectory() as tmp:
            _write(tmp, DEPLOY_REPORT, _fixture("g8_5/fail_not_passed_zh.md"))
            findings, code = _run("8.5", tmp)
        self.assertEqual(code, BLOCK)
        checks = [f.check for f in findings]
        self.assertIn("g8_5-deploy-report", checks)

    def test_fail_conclusion_not_passed_english(self):
        """'not passed' contains 'passed' but must NOT be treated as passed (substring trap)."""
        with tempfile.TemporaryDirectory() as tmp:
            _write(tmp, DEPLOY_REPORT, _fixture("g8_5/fail_not_passed_en.md"))
            findings, code = _run("8.5", tmp)
        self.assertEqual(code, BLOCK)
        checks = [f.check for f in findings]
        self.assertIn("g8_5-deploy-report", checks)

    def test_fail_conclusion_explicit_failed(self):
        with tempfile.TemporaryDirectory() as tmp:
            _write(tmp, DEPLOY_REPORT, _fixture("g8_5/fail_explicit_failed.md"))
            findings, code = _run("8.5", tmp)
        self.assertEqual(code, BLOCK)
        checks = [f.check for f in findings]
        self.assertIn("g8_5-deploy-report", checks)

    def test_pass_waiver_matches_framework_fingerprint(self):
        """The framework's fingerprint-based waiver mechanism marks the finding as WAIVED."""
        from spec_driven.retro import Waiver
        # Compute the actual fingerprint the gate will produce for the missing-report finding.
        f = gates.Finding(
            level="BLOCK",
            check="g8_5-deploy-report",
            reason="deploy-report.md 不存在，部署验收未完成",
        )
        fp = gates.fingerprint("8.5", f)
        waiver = Waiver("2026-01-01 10:00", "8.5", "g8_5-deploy-report",
                        "跳过部署", "无法本地部署", "alice", fp)
        with tempfile.TemporaryDirectory() as tmp:
            findings, code = _run("8.5", tmp, waivers=[waiver])
        self.assertEqual(code, OK)
        self.assertTrue(any(f.waived for f in findings))

    def test_waiver_after_content_change_is_rejected(self):
        """If the report now exists but fails, the old 'no-report' waiver must not match."""
        from spec_driven.retro import Waiver
        f = gates.Finding(
            level="BLOCK",
            check="g8_5-deploy-report",
            reason="deploy-report.md 不存在，部署验收未完成",
        )
        fp = gates.fingerprint("8.5", f)
        old_waiver = Waiver("2026-01-01 10:00", "8.5", "g8_5-deploy-report",
                            "跳过部署", "旧理由", "alice", fp)
        with tempfile.TemporaryDirectory() as tmp:
            # Now a report exists but says "failed" — different content, different fingerprint.
            _write(tmp, DEPLOY_REPORT, _fixture("g8_5/fail_explicit_failed.md"))
            findings, code = _run("8.5", tmp, waivers=[old_waiver])
        # The finding for "not passed" has a different evidence/fingerprint than "no file",
        # so the old waiver must not apply.
        self.assertEqual(code, BLOCK)

    def test_skipped_phase_passes(self):
        with tempfile.TemporaryDirectory() as tmp:
            findings, code = _run("8.5", tmp, meta_dict=_meta(skipped={"8.5": "S 档"}))
        self.assertEqual(code, OK)
        self.assertEqual(findings[0].check, "skipped")


# ---------------------------------------------------------------------------
# Gate 8.9 tests
# ---------------------------------------------------------------------------

class Gate89Test(unittest.TestCase):

    def test_pass_uat_accepted(self):
        with tempfile.TemporaryDirectory() as tmp:
            findings, code = _run("8.9", tmp, meta_dict=_meta(uat=True))
        self.assertEqual(code, OK)
        self.assertEqual(findings, [])

    def test_fail_uat_not_accepted(self):
        with tempfile.TemporaryDirectory() as tmp:
            findings, code = _run("8.9", tmp, meta_dict=_meta(uat=False))
        self.assertEqual(code, BLOCK)
        checks = [f.check for f in findings]
        self.assertIn("g8_9-uat-accepted", checks)
        for f in findings:
            if f.check == "g8_9-uat-accepted":
                self.assertTrue(f.locked)

    def test_fail_uat_missing(self):
        """uatAccepted absent from meta also blocks."""
        m = _meta()
        m.pop("uatAccepted", None)
        with tempfile.TemporaryDirectory() as tmp:
            findings, code = _run("8.9", tmp, meta_dict=m)
        self.assertEqual(code, BLOCK)
        checks = [f.check for f in findings]
        self.assertIn("g8_9-uat-accepted", checks)

    def test_locked_config_cannot_lower(self):
        """locked=True findings must not be downgraded by config."""
        cfg = {"gates": {"8.9": {"level": "warn"}}}
        with tempfile.TemporaryDirectory() as tmp:
            findings, code = _run("8.9", tmp, meta_dict=_meta(uat=False), cfg=cfg)
        self.assertEqual(code, BLOCK)

    def test_skipped_phase_passes(self):
        with tempfile.TemporaryDirectory() as tmp:
            findings, code = _run("8.9", tmp, meta_dict=_meta(skipped={"8.9": "manual"}))
        self.assertEqual(code, OK)
        self.assertEqual(findings[0].check, "skipped")


if __name__ == "__main__":
    unittest.main()
