"""Verify Phase 4 links when feature specifications are skipped."""

import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from spec_driven import config
from spec_driven.gates import GateContext, evaluate, fingerprint
from spec_driven.gates import g4
from spec_driven.project import Project


PROPOSAL = """# Proposal: points-demo

## 验收标准 AC

| AC | 用户故事 | 验收标准 | 验证步骤 |
| --- | --- | --- | --- |
| AC-1 | US-1 | 增加积分 | 加一后积分增加一 |
| AC-2 | US-1 | 拒绝负积分 | 输入负数时拒绝 |
"""


class SkippedSpecTaskLinksTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)
        env = patch.dict(os.environ, {"REINS_HOME": str(self.root / "home")})
        env.start()
        self.addCleanup(env.stop)
        project = Project(self.root)
        change_dir = project.change_dir("points-demo")
        change_dir.mkdir(parents=True)
        self.ctx = GateContext(project, "points-demo", change_dir,
                               {"mode": "feature", "complexity": "S",
                                "skipped": {"3": "S 档跳过"}}, config.load(project))
        self.write("proposal.md", PROPOSAL)
        self.tasks("AC-1", "AC-2")

    def write(self, name, text):
        (self.ctx.change_dir / name).write_text(text, encoding="utf-8")

    def tasks(self, *links):
        rows = ["# Tasks: points-demo", "", "## Application Layer", ""]
        for index, link in enumerate(links, 1):
            rows.append("- [ ] T%d. 校验积分；关联：%s；依赖：无；预估：1 小时；范围：src/Points.java"
                        % (index, link))
        self.write("tasks.md", "\n".join(rows) + "\n")

    def findings(self, check):
        return [f for f in g4.check(self.ctx) if f.check == check]

    def test_feature_without_spec_passes_with_ac_links(self):
        findings, code = evaluate("4", self.ctx)
        self.assertEqual((findings, code), ([], 0))
        self.assertFalse((self.ctx.change_dir / "spec.md").exists())

    def test_one_task_can_cover_multiple_acs(self):
        self.tasks("AC-1、AC-2")
        self.assertEqual(g4.check(self.ctx), [])

    def test_unknown_ac_is_blocked_even_alongside_known_acs(self):
        self.tasks("AC-1, AC-2, AC-99")
        findings = self.findings("task-link")
        self.assertEqual(len(findings), 1)
        self.assertEqual(json.loads(findings[0].evidence)["unknown"], ["AC-99"])
        self.assertEqual(evaluate("4", self.ctx)[1], 3)

    def test_every_task_requires_an_ac_link(self):
        for link in ("", "SC-points-001", "AC-unknown"):
            with self.subTest(link=link):
                self.tasks("AC-1、AC-2", link)
                self.assertEqual(len(self.findings("task-link")), 1)

    def test_malformed_reference_cannot_hide_beside_valid_acs(self):
        for link in ("AC-1、AC-2、AC-unknown", "AC-1、AC-2、SC-points-001",
                     "AC-1、AC-2、待定"):
            with self.subTest(link=link):
                self.tasks(link)
                self.assertEqual(len(self.findings("task-link")), 1)
                self.assertEqual(evaluate("4", self.ctx)[1], 3)

    def test_duplicate_acceptance_sections_are_blocked(self):
        table = "| AC | 用户故事 | 验收标准 | 验证步骤 |\n| --- | --- | --- | --- |\n"
        for heading in ("验收标准 AC", "Acceptance Criteria", "1. 验收标准"):
            with self.subTest(heading=heading):
                self.write("proposal.md", PROPOSAL + "\n## " + heading + "\n\n" + table +
                           "| AC-3 | US-1 | 保留已有积分 | 增加零分后积分不变 |\n")
                for links in (("AC-1、AC-2",), ("AC-1、AC-2、AC-3",)):
                    self.tasks(*links)
                    self.assertTrue(self.findings("task-sources"))
                    self.assertEqual(evaluate("4", self.ctx)[1], 3)

    def test_uncovered_ac_is_blocked(self):
        self.tasks("AC-1")
        findings = self.findings("ac-covered")
        self.assertEqual(len(findings), 1)
        self.assertIn("AC-2", findings[0].evidence)
        self.assertEqual(evaluate("4", self.ctx)[1], 3)

    def test_only_acceptance_table_definitions_are_link_targets(self):
        self.write("proposal.md", PROPOSAL + "\n## Out of Scope\n\nAC-99 不在本次范围。\n")
        self.tasks("AC-1、AC-2、AC-99")
        self.assertEqual(len(self.findings("task-link")), 1)

    def test_missing_or_invalid_acceptance_sources_are_blocked(self):
        for text in ("", "# Proposal\nAC-1 AC-2\n",
                     PROPOSAL.replace("| AC |", "| 编号 |"),
                     PROPOSAL.replace("AC-2 |", "AC-<编号> |"),
                     PROPOSAL.replace("AC-2 |", "AC-2 待定 |")):
            with self.subTest(text=text):
                self.write("proposal.md", text)
                self.assertTrue(self.findings("task-sources"))
        (self.ctx.change_dir / "proposal.md").unlink()
        self.assertTrue(self.findings("task-sources"))

    def test_alias_and_crlf_are_supported(self):
        self.write("proposal.md", PROPOSAL.replace("验收标准 AC", "Acceptance Criteria").replace("\n", "\r\n"))
        self.assertEqual(g4.check(self.ctx), [])

    def test_acceptance_subsection_links_are_valid(self):
        table = "| AC | 用户故事 | 验收标准 | 验证步骤 |\n| --- | --- | --- | --- |\n"
        self.write("proposal.md", PROPOSAL.replace("| AC-2 |", "\n### 异常验收\n\n" + table + "| AC-2 |"))
        self.assertEqual(g4.check(self.ctx), [])

    def test_acceptance_subsection_acs_must_be_covered(self):
        table = "| AC | 用户故事 | 验收标准 | 验证步骤 |\n| --- | --- | --- | --- |\n"
        self.write("proposal.md", PROPOSAL.replace("| AC-2 |", "\n### 异常验收\n\n" + table + "| AC-2 |"))
        self.tasks("AC-1")
        findings = self.findings("ac-covered")
        self.assertEqual(len(findings), 1)
        self.assertEqual(json.loads(findings[0].evidence), ["AC-2"])

    def test_skipped_phase_selects_ac_links_regardless_of_tier(self):
        self.ctx.meta["complexity"] = "M"
        self.assertEqual(g4.check(self.ctx), [])

    def test_without_skip_reason_feature_still_requires_scs(self):
        self.write("spec.md", "# Capability: points\n\n## REQ-points-001\n\n### SC-points-001\n")
        for skipped in ({}, {"3": ""}):
            with self.subTest(skipped=skipped):
                self.ctx.meta["skipped"] = skipped
                self.tasks("AC-1、AC-2")
                self.assertTrue(self.findings("task-link"))
                self.tasks("SC-points-001")
                self.assertEqual(g4.check(self.ctx), [])

    def test_other_task_checks_still_apply_to_ac_tasks(self):
        self.tasks("AC-1、AC-2")
        path = self.ctx.change_dir / "tasks.md"
        original = path.read_text(encoding="utf-8")
        for old, new, check in (("1 小时", "3 小时", "task-estimate"),
                                ("依赖：无", "依赖：T9", "task-order"),
                                ("T1.", "无编号", "task-identifiers")):
            with self.subTest(check=check):
                self.write("tasks.md", original.replace(old, new))
                self.assertTrue(self.findings(check))

    def test_coverage_fingerprint_ignores_line_shifts(self):
        self.tasks("AC-1")
        before = self.findings("ac-covered")
        self.assertEqual(len(before), 1)
        self.write("proposal.md", "\n\n" + PROPOSAL)
        after = self.findings("ac-covered")
        self.assertEqual(fingerprint("4", before[0]), fingerprint("4", after[0]))


if __name__ == "__main__":
    unittest.main()
