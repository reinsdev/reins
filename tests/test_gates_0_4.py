"""Exercise early gates using filled T1 templates and explicit fault fixtures."""

import contextlib
import copy
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from spec_driven import config, mdparse, meta
from spec_driven.gates import GateContext, evaluate, fingerprint
from spec_driven.gates import g0, g1, g2, g3, g4
from spec_driven.project import Project

FIXTURES = Path(__file__).parent / "fixtures" / "t3"
CLI = (Path(__file__).resolve().parents[1] / "reinsdev-plugin" / "skills"
       / "spec-driven-dev" / "scripts" / "spec-driven.py")
MODULES = {"0": g0, "1": g1, "2": g2, "3": g3, "4": g4}
CASES = json.loads((FIXTURES / "cases.json").read_text(encoding="utf-8"))


class EarlyGateTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.home = self.root / "reins-home"
        env = patch.dict(os.environ, {"REINS_HOME": str(self.home)})
        env.start()
        self.addCleanup(env.stop)

    def project(self, case=None, broken=False):
        case = case or {}
        root = self.root / ("broken" if broken else "valid")
        root.mkdir(exist_ok=True)
        project = Project(root)
        change = case.get("change", "batch-approve") if broken else "batch-approve"
        change_dir = project.change_dir(change)
        change_dir.mkdir(parents=True, exist_ok=True)
        (root / "pom.xml").write_text("<project/>", encoding="utf-8")
        for source in (FIXTURES / "valid").iterdir():
            (change_dir / source.name).write_text(source.read_text(encoding="utf-8"), encoding="utf-8")
        mode = "bugfix" if case.get("bugfix") else "feature"
        m = meta.new(change, mode, "feat/batch-approve", "a" * 40)
        m.update(complexity="L", tierConfirmed=True, designDecision="方案 A", phase=case.get("gate", "0"))
        if case.get("bugfix"):
            proposal = change_dir / "proposal.md"
            text = proposal.read_text(encoding="utf-8").replace(
                "## Out of Scope",
                "| AC-regression | US1 | 自动化回归且不退化已有测试 | 运行全量测试，全部通过 |\n\n## Out of Scope")
            # Keep regression in the same table.
            text = text.replace("均为通过 |\n\n| AC-regression", "均为通过 |\n| AC-regression")
            proposal.write_text(text, encoding="utf-8")
            spec = change_dir / "spec.md"
            spec.write_text(spec.read_text(encoding="utf-8").replace(
                "关联 AC：AC-1", "关联 AC：AC-1、AC-regression"), encoding="utf-8")
            tasks = change_dir / "tasks.md"
            tasks.write_text(tasks.read_text(encoding="utf-8") +
                "\n- [ ] T-regression: 为批量审批编写自动化回归测试；关联：SC-approval-001；依赖：T5；预估：1 小时；范围：src/test/java/RegressionTest.java\n", encoding="utf-8")
        if broken:
            m.update(case.get("meta", {}))
            for edit in case.get("edits", []):
                path = change_dir / edit["file"]
                text = path.read_text(encoding="utf-8")
                self.assertIn(edit["old"], text, "bad fixture")
                path.write_text(text.replace(edit["old"], edit["value"]), encoding="utf-8")
            for name, text in case.get("replace", {}).items():
                (change_dir / name).write_text(text, encoding="utf-8")
            for name in case.get("remove", []):
                (change_dir / name).unlink()
            if case.get("removeBuild"):
                (root / "pom.xml").unlink()
        (change_dir / ".meta.json").write_text(json.dumps(m), encoding="utf-8")
        cfg = copy.deepcopy(config.DEFAULTS)
        cfg.update(case.get("config", {}) if broken else {})
        (project.root / ".openspec" / ".config.json").write_text(json.dumps(cfg), encoding="utf-8")
        return GateContext(project, change, change_dir, m, cfg)

    def check_gate(self, gate, ctx):
        try:
            return MODULES[gate].check(ctx)
        except NotImplementedError:
            self.fail("gate-%s 尚未实现" % gate)

    def test_each_check_has_passing_and_failing_fixture(self):
        for case in CASES:
            with self.subTest(gate=case["gate"], check=case["check"]):
                good = self.project(case)
                self.assertEqual([], self.check_gate(case["gate"], good))
                bad = self.project(case, broken=True)
                findings = self.check_gate(case["gate"], bad)
                matching = [f for f in findings if f.check == case["check"]]
                self.assertTrue(matching, [f.check for f in findings])
                self.assertTrue(all(f.level == case.get("level", "BLOCK") for f in matching))
                self.assertTrue(all(f.reason and f.fix and f.evidence for f in matching))

    def test_cli_matches_fixture_verdicts(self):
        for case in CASES:
            if case["check"] == "change-mode" or case.get("meta", {}).get("tierConfirmed") == "true":
                continue  # CLI rejects malformed meta before the gate.
            with self.subTest(gate=case["gate"], check=case["check"]):
                for broken in (False, True):
                    ctx = self.project(case, broken)
                    result = subprocess.run(
                        [sys.executable, str(CLI), "gate", case["gate"], "--change", ctx.change, "--json"],
                        cwd=str(ctx.project.root), text=True, encoding="utf-8", capture_output=True)
                    expected = (2 if case.get("level") == "WARN" else 3) if broken else 0
                    self.assertEqual(expected, result.returncode, result.stdout + result.stderr)
                    report = json.loads(result.stdout)
                    self.assertEqual(expected, report["exit"])
                    if broken:
                        self.assertIn(case["check"], [f["check"] for f in report["findings"]])

    def test_checks_are_read_only_and_silent(self):
        for gate in MODULES:
            ctx = self.project({"gate": gate})
            before = {p.relative_to(ctx.project.root): p.read_bytes()
                      for p in ctx.project.root.rglob("*") if p.is_file()}
            state = copy.deepcopy(ctx.meta)
            output = io.StringIO()
            with contextlib.redirect_stdout(output), contextlib.redirect_stderr(output):
                self.check_gate(gate, ctx)
            self.assertEqual("", output.getvalue())
            self.assertEqual(state, ctx.meta)
            after = {p.relative_to(ctx.project.root): p.read_bytes()
                     for p in ctx.project.root.rglob("*") if p.is_file()}
            self.assertEqual(before, after)
        self.assertFalse(self.home.exists())

    def test_locked_checks_survive_off_configuration(self):
        for check in ("business-source", "field-mapping", "tier-confirmed", "bugfix-reviewed"):
            case = next(c for c in CASES if c["check"] == check)
            ctx = self.project(case, True)
            ctx.config["gates"] = {"1": {"level": "off"}}
            findings, code = evaluate("1", ctx)
            self.assertEqual(3, code)
            self.assertTrue(any(f.check == check and f.locked for f in findings))

    def test_fingerprints_ignore_added_blank_lines_and_crlf(self):
        for case in CASES:
            ctx = self.project(case, True)
            before = sorted((f.check, fingerprint(case["gate"], f))
                            for f in self.check_gate(case["gate"], ctx))
            for path in ctx.change_dir.glob("*.md"):
                text = "\n\n" + path.read_text(encoding="utf-8")
                path.write_bytes(text.replace("\n", "\r\n").encode("utf-8"))
            after = sorted((f.check, fingerprint(case["gate"], f))
                           for f in self.check_gate(case["gate"], ctx))
            self.assertEqual(before, after, case["check"])

    def test_java_build_can_be_in_parent(self):
        ctx = self.project()
        (ctx.project.root / "pom.xml").unlink()
        (self.root / "build.gradle.kts").write_text("plugins {}", encoding="utf-8")
        self.assertEqual([], self.check_gate("0", ctx))

    def test_unfilled_templates_do_not_pass(self):
        templates = CLI.parent.parent / "templates"
        for gate, name in (("1", "proposal.md"), ("2", "design.md"),
                           ("3", "spec.md"), ("4", "tasks.md")):
            ctx = self.project()
            (ctx.change_dir / name).write_text((templates / name).read_text(encoding="utf-8"), encoding="utf-8")
            self.assertTrue(self.check_gate(gate, ctx), gate)

    def test_bad_encoding_blocks_without_raising(self):
        for gate, name in (("1", "proposal.md"), ("2", "design.md"),
                           ("3", "spec.md"), ("4", "tasks.md")):
            ctx = self.project()
            (ctx.change_dir / name).write_bytes(b"\xff")
            findings = self.check_gate(gate, ctx)
            self.assertTrue(any(f.level == "BLOCK" for f in findings))

    def test_bugfix_links_change_points_when_spec_skipped(self):
        ctx = self.project({"bugfix": True})
        ctx.meta["skipped"]["3"] = "不改接口签名 + 不改 DDL"
        (ctx.change_dir / "spec.md").unlink()
        tasks = ctx.change_dir / "tasks.md"
        tasks.write_text(tasks.read_text(encoding="utf-8").replace("SC-approval-001", "FIX-1"), encoding="utf-8")
        self.assertEqual([], self.check_gate("4", ctx))
        tasks.write_text(tasks.read_text(encoding="utf-8").replace("FIX-1", "FIX-9"), encoding="utf-8")
        self.assertIn("task-link", [f.check for f in self.check_gate("4", ctx)])

    def test_no_change_contract_sections_are_allowed(self):
        ctx = self.project()
        path = ctx.change_dir / "spec.md"
        text = path.read_text(encoding="utf-8").split("## 接口契约")[0]
        path.write_text(text + "## 接口契约\n\n本次不变更\n\n## 数据模型\n\n本次不变更\n", encoding="utf-8")
        self.assertEqual([], self.check_gate("3", ctx))

    def test_when_then_need_nonempty_clauses_under_real_headings(self):
        for old, new in (("THEN 两条记录均变成已通过", "THEN"),
                         ("WHEN 审批人提交两条待审批记录", "WHEN"),
                         ("## REQ-approval", "### REQ-approval")):
            ctx = self.project({"edits": [{"file": "spec.md", "old": old, "value": new}]}, True)
            self.assertIn("scenario-structure", [f.check for f in self.check_gate("3", ctx)])

    def test_header_aliases_are_accepted(self):
        ctx = self.project()
        path = ctx.change_dir / "proposal.md"
        text = path.read_text(encoding="utf-8")
        for old, new in (("用户故事\n", "User Stories\n"), ("验收标准 AC\n", "Acceptance Criteria\n"),
                         ("Out of Scope\n", "范围外\n"), ("歧义清单\n", "Ambiguities\n")):
            text = text.replace(old, new)
        path.write_text(text, encoding="utf-8")
        self.assertEqual([], self.check_gate("1", ctx))


    def test_fixing_one_api_field_preserves_unrelated_failure_fingerprint(self):
        ctx = self.project()
        path = ctx.change_dir / "spec.md"
        text = path.read_text(encoding="utf-8").replace("每秒 10 次，超限 429", "")
        path.write_text(text, encoding="utf-8")
        before = next(f for f in self.check_gate("3", ctx) if f.check == "interface-contract")
        path.write_text(text.replace("count: 整数", "count: 非负整数"), encoding="utf-8")
        after = next(f for f in self.check_gate("3", ctx) if f.check == "interface-contract")
        self.assertEqual(fingerprint("3", before), fingerprint("3", after))

    def test_missing_upstream_complexity_input_blocks(self):
        ctx = self.project()
        (ctx.change_dir / "proposal.md").unlink()
        self.assertIn("design-readable", [f.check for f in self.check_gate("2", ctx)])

    def test_bad_requirement_id_does_not_raise(self):
        ctx = self.project()
        path = ctx.change_dir / "spec.md"
        path.write_text(path.read_text(encoding="utf-8").replace("REQ-approval-001:", "REQ-approval-001x:"), encoding="utf-8")
        self.assertIn("scenario-structure", [f.check for f in self.check_gate("3", ctx)])

    def test_sc_link_must_occupy_the_association_field(self):
        ctx = self.project()
        path = ctx.change_dir / "tasks.md"
        path.write_text(path.read_text(encoding="utf-8").replace("关联：SC-approval-001；", "关联：SC-approval-001x；"), encoding="utf-8")
        self.assertIn("task-link", [f.check for f in self.check_gate("4", ctx)])

    def test_m_tier_allows_two_options_and_hour_boundary(self):
        ctx = self.project()
        ctx.meta["complexity"] = "M"
        path = ctx.change_dir / "design.md"
        text = path.read_text(encoding="utf-8")
        text = "\n".join(line for line in text.splitlines() if not line.startswith("| 方案 C |"))
        path.write_text(text, encoding="utf-8")
        self.assertNotIn("alternatives-count", [f.check for f in self.check_gate("2", ctx)])
        path = ctx.change_dir / "tasks.md"
        path.write_text(path.read_text(encoding="utf-8").replace("预估：2 小时", "预估：120 分钟"), encoding="utf-8")
        self.assertNotIn("task-estimate", [f.check for f in self.check_gate("4", ctx)])


    def test_duplicate_ambiguities_cannot_hide_unconfirmed_business_value(self):
        ctx = self.project()
        path = ctx.change_dir / "proposal.md"
        path.write_text(path.read_text(encoding="utf-8") + """
## 歧义与澄清

| 问题 | 影响范围 | 类型 | 回答 | 来源 | 状态 |
| --- | --- | --- | --- | --- | --- |
| 实际上限 | 性能 | 业务取值 | 99 | 模型 | 未答 |
""", encoding="utf-8")
        findings = self.check_gate("1", ctx)
        self.assertTrue(any(f.check == "business-source" and f.locked for f in findings))

    def test_fenced_fields_are_not_design_decisions_or_scenario_clauses(self):
        for gate, name, start, end, check in (
            ("2", "design.md", "**AI 推荐**：方案 A", "用户选择复用现有逻辑以缩短交付时间。", "recommendation"),
            ("3", "spec.md", "WHEN 审批人提交两条待审批记录", "AND 保留审批日志", "scenario-structure"),
        ):
            for fence in ("~~~", chr(96) * 3):
                ctx = self.project()
                path = ctx.change_dir / name
                text = path.read_text(encoding="utf-8")
                text = text.replace(start, fence + "\\n" + start).replace(end, end + "\\n" + fence)
                path.write_text(text.replace("\\n", "\n"), encoding="utf-8")
                self.assertIn(check, [f.check for f in self.check_gate(gate, ctx)])

    def test_phase_three_requires_design_unless_it_was_skipped(self):
        ctx = self.project()
        (ctx.change_dir / "design.md").unlink()
        self.assertIn("spec-readable", [f.check for f in self.check_gate("3", ctx)])
        ctx.meta["skipped"]["2"] = "不需要完整设计"
        self.assertNotIn("spec-readable", [f.check for f in self.check_gate("3", ctx)])


    def test_duplicate_design_spec_and_ac_sections_are_rejected(self):
        for gate, name, suffix, check in (
            ("2", "design.md", "\n## Decision\n\n**最终选择**：方案 B\n", "design-decision"),
            ("3", "spec.md", "\n## API Contract\n\n未答\n", "interface-contract"),
            ("3", "spec.md", "\n## 数据库设计\n\n未答\n", "data-model"),
            ("3", "proposal.md", "\n## Acceptance Criteria\n\n| AC | 用户故事 | 验收标准 | 验证步骤 |\n| --- | --- | --- | --- |\n| AC-2 | US1 | 审批失败不能丢记录 | 提交无权限记录 |\n", "ac-mapped"),
        ):
            ctx = self.project()
            path = ctx.change_dir / name
            path.write_text(path.read_text(encoding="utf-8") + suffix, encoding="utf-8")
            self.assertIn(check, [f.check for f in self.check_gate(gate, ctx)])

    def test_openapi_validation_gap_can_be_configured_to_block(self):
        ctx = self.project()
        ctx.config["openapi"] = {"enabled": True, "gate_on_draft": "block"}
        findings = self.check_gate("3", ctx)
        self.assertTrue(any(f.check == "openapi-draft" and f.level == "BLOCK" for f in findings))

    def test_fence_variations_do_not_supply_scenario_evidence(self):
        for start, end in ((chr(96) * 3, ""), ("~~~", ""), ("> " + chr(96) * 3, "> " + chr(96) * 3)):
            ctx = self.project()
            path = ctx.change_dir / "spec.md"
            text = path.read_text(encoding="utf-8")
            text = text.replace("WHEN 审批人提交两条待审批记录", start + "\nWHEN 审批人提交两条待审批记录")
            text = text.replace("AND 保留审批日志", "AND 保留审批日志\n" + end)
            if start.startswith(">"):
                text = text.replace("\nWHEN ", "\n> WHEN ").replace("\nTHEN ", "\n> THEN ").replace("\nAND ", "\n> AND ")
            path.write_text(text, encoding="utf-8")
            self.assertIn("scenario-structure", [f.check for f in self.check_gate("3", ctx)])


    def test_duplicate_section_waiver_fingerprint_changes_with_new_content(self):
        for gate, filename, suffix, old, new, check in (
            ("1", "proposal.md", "\n## 歧义清单\n\n| 问题 | 影响范围 | 类型 | 回答 | 来源 | 状态 |\n| --- | --- | --- | --- | --- | --- |\n| 上限 | 性能 | 业务取值 | 20 | 用户 | ✅ |\n", "| 用户 |", "| 模型 |", "business-source"),
            ("2", "design.md", "\n## Decision\n\n**最终选择**：方案 A\n", "方案 A", "方案 B", "design-decision"),
            ("3", "spec.md", "\n## API Contract\n\n错误码待确认\n", "错误码待确认", "响应字段待确认", "interface-contract"),
        ):
            ctx = self.project()
            path = ctx.change_dir / filename
            original = path.read_text(encoding="utf-8")
            path.write_text(original + suffix, encoding="utf-8")
            before = {fingerprint(gate, f) for f in self.check_gate(gate, ctx) if f.check == check}
            path.write_text(original + suffix.replace(old, new), encoding="utf-8")
            after = {fingerprint(gate, f) for f in self.check_gate(gate, ctx) if f.check == check}
            self.assertTrue(after - before, check)


if __name__ == "__main__":
    unittest.main()
