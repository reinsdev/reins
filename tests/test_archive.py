"""T7 archive merge, transaction and gate behavior."""
import contextlib
import io
import json
import os
import tempfile
import unittest
from argparse import Namespace
from pathlib import Path
from unittest import mock

from spec_driven import archive, config, gitutil, meta, retro
from spec_driven.commands import archive as command
from spec_driven.gates import Finding, GateContext, evaluate
from spec_driven.gates import g8_9, g9
from spec_driven.project import Project

FIXTURES = Path(__file__).parent / "fixtures" / "t7"


def fixture(name):
    return (FIXTURES / name).read_text(encoding="utf-8")


def uat_check(ctx):
    if ctx.meta.get("uatAccepted") is True:
        return []
    return [Finding("BLOCK", "uat", "尚未通过用户验收", evidence="uatAccepted=false", locked=True)]


class MergeTests(unittest.TestCase):
    def test_four_merge_scenarios(self):
        for name in ("new", "append", "replace", "conflict"):
            with self.subTest(name=name):
                old = fixture(name + "/base.md")
                delta = fixture(name + "/delta.md")
                existing = {"approval": old} if old else {}
                if name == "conflict":
                    with self.assertRaisesRegex(archive.ArchiveError, "SC-approval-001"):
                        archive.merge_specs(existing, delta)
                else:
                    self.assertEqual(archive.merge_specs(existing, delta)["approval"],
                                     fixture(name + "/expected.md"))

    def test_duplicate_req_and_scenario_ids_are_rejected(self):
        delta = fixture("new/delta.md")
        bad = [delta + delta[delta.index("## REQ-"):],
               delta + "\n### SC-approval-001: 重复场景\nWHEN 再次提交\nTHEN 拒绝\n",
               delta.replace("REQ-approval-001", "REQ-other-001"),
               delta.replace("SC-approval-001", "SC-other-001"),
               delta.replace("`approval`", "`../outside`")]
        for value in bad:
            with self.subTest(value=value):
                with self.assertRaises(archive.ArchiveError):
                    archive.merge_specs({}, value)

    def test_fenced_ids_do_not_become_requirements(self):
        delta = fixture("new/delta.md") + "\n```markdown\n## REQ-other-001: 示例\n### SC-other-001: 示例\n```\n"
        self.assertEqual(archive.merge_specs({}, delta)["approval"], delta)

    def test_crlf_is_normalized(self):
        delta = fixture("new/delta.md")
        self.assertEqual(archive.merge_specs({}, delta.replace("\n", "\r\n"))["approval"], delta)

    def test_multiple_capabilities_route_to_separate_files(self):
        first = fixture("new/delta.md")
        other = first.replace("approval", "billing").replace("审批", "计费")
        merged = archive.merge_specs({}, first + "\n" + other)
        self.assertEqual(set(merged), {"approval", "billing"})
        self.assertEqual(merged["approval"], first)
        self.assertEqual(merged["billing"], other)

    def test_summary_tables_keep_other_requirements(self):
        old = fixture("replace/base.md") + "\n## 接口契约\n\n| Method | Path | 关联 SC |\n| --- | --- | --- |\n| POST | /old | SC-approval-001 |\n| DELETE | /keep | SC-approval-002 |\n"
        delta = fixture("replace/delta.md") + "\n## 接口契约\n\n| Method | Path | 关联 SC |\n| --- | --- | --- |\n| POST | /new | SC-approval-001 |\n"
        text = archive.merge_specs({"approval": old}, delta)["approval"]
        self.assertIn("/keep", text)
        self.assertIn("/new", text)
        self.assertNotIn("/old", text)


    def test_revision_comment_is_preserved(self):
        delta = "<!-- revised at 2026-09-26: 用户修正 -->\n" + fixture("new/delta.md")
        self.assertEqual(archive.merge_specs({}, delta)["approval"], delta)

    def test_data_model_tables_merge_recursively(self):
        old = fixture("replace/base.md") + "\n## 数据模型\n\n### 表结构\n\n| 表 | 字段 | 关联 SC |\n| --- | --- | --- |\n| approval | old | SC-approval-001 |\n| other | keep | SC-approval-002 |\n"
        delta = fixture("replace/delta.md") + "\n## 数据模型\n\n### 表结构\n\n| 表 | 字段 | 关联 SC |\n| --- | --- | --- |\n| approval | new | SC-approval-001 |\n"
        merged = archive.merge_specs({"approval": old}, delta)["approval"]
        self.assertIn("| other | keep |", merged)
        self.assertIn("| approval | new |", merged)
        self.assertNotIn("| approval | old |", merged)

    def test_ambiguous_shared_summary_row_blocks(self):
        old = fixture("replace/base.md") + "\n## 接口契约\n\n| Method | Path | 关联 SC |\n| --- | --- | --- |\n| POST | /shared | SC-approval-001, SC-approval-002 |\n"
        delta = fixture("replace/delta.md") + "\n## 接口契约\n\n| Method | Path | 关联 SC |\n| --- | --- | --- |\n| POST | /new | SC-approval-001 |\n"
        with self.assertRaises(archive.ArchiveError):
            archive.merge_specs({"approval": old}, delta)

    def test_summary_preserves_prose_around_table(self):
        summary = "\n## 接口契约\n\n所有端点必须携带 X-Tenant。\n\n| Method | Path | 关联 SC |\n| --- | --- | --- |\n| POST | /old | SC-approval-001 |\n\n响应须保留 requestId。\n"
        old = fixture("new/delta.md") + summary
        delta = fixture("replace/delta.md") + summary.replace("/old", "/new")
        merged = archive.merge_specs({"approval": old}, delta)["approval"]
        self.assertIn("所有端点必须携带 X-Tenant。", merged)
        self.assertIn("响应须保留 requestId。", merged)
        self.assertIn("/new", merged)
        conflicting = delta.replace("所有端点必须携带 X-Tenant。", "新接口重试必须复用幂等键。")
        with self.assertRaises(archive.ArchiveError):
            archive.merge_specs({"approval": old}, conflicting)

    def test_unchanged_word_in_prose_does_not_skip_table_updates(self):
        summary = "\n## 接口契约\n\n认证规则本次不变更；下表更新提交路径。\n\n| Method | Path | 关联 SC |\n| --- | --- | --- |\n| POST | /old | SC-approval-001 |\n"
        old = fixture("new/delta.md") + summary
        delta = fixture("replace/delta.md") + summary.replace("/old", "/new")
        merged = archive.merge_specs({"approval": old}, delta)["approval"]
        self.assertIn("/new", merged)
        self.assertNotIn("/old", merged)


class ArchiveTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.env = mock.patch.dict(os.environ, {"REINS_HOME": str(self.root / "reins-home")})
        self.env.start()
        self.addCleanup(self.env.stop)
        self.project = Project(self.root)
        self.change = "approval-change"
        self.source = self.project.change_dir(self.change)
        self.source.mkdir(parents=True)
        gitutil.git(["init"], self.root)
        gitutil.git(["config", "user.name", "Wilson"], self.root)
        gitutil.git(["config", "user.email", "wilson@example.invalid"], self.root)
        gitutil.git(["-c", "core.hooksPath=%s" % (self.root / "no-hooks"), "commit", "--allow-empty", "-m", "initial"], self.root)
        data = meta.new(self.change, "feature", gitutil.current_branch(self.root), gitutil.head(self.root))
        data.update(phase="9", tierConfirmed=True, uatAccepted=True,
                    uatAcceptedAt="2026-09-26T10:00:00Z", designDecision="方案 B")
        data["phaseStatus"] = {phase: "passed" for phase in meta.PHASES}
        data["phaseStatus"]["9"] = "in_progress"
        with meta.lock(self.source):
            meta.save(self.source, data)
        for name in ("proposal.md", "tasks.md", "spec-review.md", "implementation-log.md", "qa-report.md", "code-review.md"):
            (self.source / name).write_text("# 测试工件\n", encoding="utf-8")
        (self.source / "spec.md").write_text(fixture("new/delta.md"), encoding="utf-8")
        (self.source / "design.md").write_text(fixture("design.md"), encoding="utf-8")
        (self.source / "deploy-report.md").write_text("# Deploy\n\n## 结论\n\npassed\n", encoding="utf-8")
        retro.add_todo(self.source, "code-review WARN", "保留原有待优化项")
        gitutil.git(["add", "."], self.root)
        gitutil.git(["-c", "core.hooksPath=%s" % (self.root / "no-hooks"), "commit", "-m", "artifacts"], self.root)
        # T4's unimplemented gate is replaced only at its public check boundary.
        self.uat = mock.patch.object(g8_9, "check", side_effect=uat_check)
        self.uat.start()
        self.addCleanup(self.uat.stop)

    def context(self, directory=None):
        directory = directory or self.source
        return GateContext(self.project, self.change, directory, meta.load(directory), config.load(self.project))

    def plan(self):
        return archive.build_plan(self.project, self.change, self.source, meta.load(self.source))

    def invoke(self, dry_run=False):
        out = io.StringIO()
        with mock.patch.object(Project, "here", return_value=self.project), contextlib.redirect_stdout(out):
            code = command.run(Namespace(change=self.change, dry_run=dry_run))
        return code, out.getvalue()

    def snapshot(self):
        return {p.relative_to(self.project.openspec).as_posix(): p.read_bytes()
                for p in self.project.openspec.rglob("*") if p.is_file()}

    def test_dry_run_changes_neither_files_nor_index(self):
        before = self.snapshot()
        index = gitutil.git(["ls-files", "--stage"], self.root)
        code, text = self.invoke(True)
        self.assertEqual(code, 0)
        self.assertIn("approval.md", text)
        self.assertIn("0001-approval-change.md", text)
        self.assertIn("architecture.md", text)
        self.assertEqual(self.snapshot(), before)
        self.assertEqual(gitutil.git(["ls-files", "--stage"], self.root), index)

    def test_archive_preserves_audit_and_passes_gate(self):
        audit = (self.source / "retrospective.md").read_text(encoding="utf-8")
        plan = self.plan()
        code, text = self.invoke()
        self.assertEqual(code, 0, text)
        self.assertFalse(self.source.exists())
        self.assertTrue(plan.destination.is_dir())
        self.assertEqual(evaluate("9", self.context(plan.destination))[1], 0)
        self.assertEqual(meta.load(plan.destination)["phaseStatus"]["9"], "passed")
        retrospective = (plan.destination / "retrospective.md").read_text(encoding="utf-8")
        self.assertTrue(retrospective.startswith(audit))
        self.assertIn("passed", retrospective)
        self.assertTrue(retro.verify(plan.destination))
        self.assertIn("approval.md", (self.project.specs_dir / "README.md").read_text(encoding="utf-8"))
        adr = (self.project.decisions_dir / "0001-approval-change.md").read_text(encoding="utf-8")
        self.assertIn("**最终选择**：方案 B", adr)
        self.assertIn("兼容已有流程", adr)
        self.assertIn("archive/", gitutil.git(["diff", "--cached", "--name-only"], self.root))

    def test_adr_uses_maximum_existing_number(self):
        self.project.decisions_dir.mkdir()
        for name in ("0002-old.md", "0012-old.md", "README.md"):
            (self.project.decisions_dir / name).write_text("existing\n", encoding="utf-8")
        code, text = self.invoke()
        self.assertEqual(code, 0, text)
        self.assertTrue((self.project.decisions_dir / "0013-approval-change.md").is_file())

    def test_precondition_rejects_unaccepted_change_without_writes(self):
        meta.update(self.source, lambda data: data.update(uatAccepted=False, uatAcceptedAt=None))
        before = self.snapshot()
        self.assertEqual(self.invoke()[0], 3)
        self.assertEqual(self.snapshot(), before)

    def test_uat_waiver_is_honored_after_move(self):
        meta.update(self.source, lambda data: data.update(uatAccepted=False, uatAcceptedAt=None))
        findings, code = evaluate("8.9", self.context())
        finding = findings[0]
        retro.append_waiver(self.source, retro.Waiver("2026-09-26", "8.9", "uat", finding.reason,
                                                   "人工确认跳过", "ronnie", finding.fingerprint))
        self.assertEqual(self.invoke()[0], 0)

    def test_conflicting_scenario_does_not_publish_anything(self):
        self.project.specs_dir.mkdir()
        (self.project.specs_dir / "approval.md").write_text(fixture("conflict/base.md"), encoding="utf-8")
        (self.source / "spec.md").write_text(fixture("conflict/delta.md"), encoding="utf-8")
        before = self.snapshot()
        self.assertEqual(self.invoke()[0], 3)
        self.assertEqual(self.snapshot(), before)

    def test_existing_destination_is_not_overwritten(self):
        plan = self.plan()
        plan.destination.mkdir(parents=True)
        (plan.destination / "keep").write_text("existing", encoding="utf-8")
        before = self.snapshot()
        with self.assertRaises(archive.ArchiveError):
            self.plan()
        self.assertEqual(self.snapshot(), before)

    def test_git_move_failure_restores_files_and_staged_work(self):
        (self.root / "unrelated.txt").write_text("keep staged", encoding="utf-8")
        gitutil.git(["add", "unrelated.txt"], self.root)
        before = self.snapshot()
        staged = gitutil.git(["ls-files", "--stage"], self.root)
        real_git = gitutil.git
        def fail_move(args, cwd, check=True):
            if args[0] == "mv":
                raise OSError("模拟迁移失败")
            return real_git(args, cwd, check=check)
        with mock.patch.object(gitutil, "git", side_effect=fail_move), contextlib.redirect_stderr(io.StringIO()):
            with self.assertRaises(SystemExit):
                self.invoke()
        self.assertEqual(self.snapshot(), before)
        self.assertEqual(gitutil.git(["ls-files", "--stage"], self.root), staged)

    def test_gate_failure_after_move_rolls_back(self):
        before = self.snapshot()
        staged = gitutil.git(["ls-files", "--stage"], self.root)
        with mock.patch.object(g9, "check", return_value=[Finding("BLOCK", "archive-complete", "模拟损坏")]):
            self.assertEqual(self.invoke()[0], 3)
        self.assertEqual(self.snapshot(), before)
        self.assertEqual(gitutil.git(["ls-files", "--stage"], self.root), staged)

    def test_each_gate_check_has_passing_and_failing_fixture(self):
        cases = json.loads(fixture("gate-cases.json"))
        self.assertEqual(self.invoke()[0], 0)
        destination = next(self.project.archive_dir.iterdir())
        for case in cases:
            with self.subTest(check=case["check"]):
                self.assertNotIn(case["check"], [f.check for f in g9.check(self.context(destination))])
                path = None
                if case["mutation"] == "unaccepted":
                    path = destination / ".meta.json"
                    backup = path.read_bytes()
                    meta.update(destination, lambda data: data.update(uatAccepted=False, uatAcceptedAt=None))
                elif case["mutation"] == "active":
                    self.source.mkdir()
                elif case["mutation"] in ("missing-task", "missing-retro"):
                    path = destination / ("tasks.md" if case["mutation"] == "missing-task" else "retrospective.md")
                    backup = path.read_bytes()
                    path.unlink()
                else:
                    path = self.project.specs_dir / "approval.md"
                    backup = path.read_bytes()
                    path.write_text(fixture("replace/delta.md"), encoding="utf-8")
                findings = g9.check(self.context(destination))
                self.assertIn(case["check"], [f.check for f in findings])
                if path:
                    path.write_bytes(backup)
                else:
                    self.source.rmdir()


    def test_skipped_design_spec_qa_and_deploy_can_archive(self):
        def skip(data):
            data["complexity"] = "S"
            data["designDecision"] = None
            for phase in ("2", "3", "5", "7", "8.5"):
                data["phaseStatus"][phase] = "skipped"
        meta.update(self.source, skip)
        for name in ("design.md", "spec.md", "spec-review.md", "qa-report.md", "deploy-report.md"):
            (self.source / name).unlink()
        gitutil.git(["add", "-u"], self.root)
        code, text = self.invoke()
        self.assertEqual(code, 0, text)
        self.assertFalse(self.project.decisions_dir.exists())

    def test_dry_run_rejects_missing_deploy_conclusion(self):
        (self.source / "deploy-report.md").write_text("# Deploy\n", encoding="utf-8")
        before = self.snapshot()
        self.assertEqual(self.invoke(True)[0], 3)
        self.assertEqual(self.snapshot(), before)

    def test_archive_lock_does_not_remove_another_owners_lock(self):
        path = self.project.openspec / ".archive.lock"
        path.write_text("other", encoding="utf-8")
        before = self.snapshot()
        self.assertEqual(self.invoke()[0], 3)
        self.assertEqual(self.snapshot(), before)

    def test_missing_adr_is_detected_after_archive(self):
        self.assertEqual(self.invoke()[0], 0)
        destination = next(self.project.archive_dir.iterdir())
        next(self.project.decisions_dir.glob("*.md")).unlink()
        self.assertIn("archive-complete", [f.check for f in g9.check(self.context(destination))])

    def test_unsynced_interface_table_blocks_gate(self):
        summary = "\n## 接口契约\n\n| Method | Path | 关联 SC |\n| --- | --- | --- |\n| POST | /approval | SC-approval-001 |\n"
        with (self.source / "spec.md").open("a", encoding="utf-8") as stream:
            stream.write(summary)
        self.assertEqual(self.invoke()[0], 0)
        destination = next(self.project.archive_dir.iterdir())
        target = self.project.specs_dir / "approval.md"
        target.write_text(fixture("new/delta.md"), encoding="utf-8")
        self.assertIn("specs-synced", [f.check for f in g9.check(self.context(destination))])

    def test_invalid_archive_metadata_blocks_silently(self):
        self.assertEqual(self.invoke()[0], 0)
        destination = next(self.project.archive_dir.iterdir())
        ctx = self.context(destination)
        (destination / ".meta.json").write_text("{", encoding="utf-8")
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            findings = g9.check(ctx)
        self.assertIn("archive-complete", [f.check for f in findings])
        self.assertEqual(out.getvalue() + err.getvalue(), "")

    def test_interruption_after_move_restores_untracked_and_empty_directories(self):
        (self.source / "empty").mkdir()
        (self.source / "untracked.txt").write_text("keep me", encoding="utf-8")
        before = self.snapshot()
        staged = gitutil.git(["ls-files", "--stage"], self.root)
        with mock.patch.object(g9, "check", side_effect=KeyboardInterrupt):
            with self.assertRaises(KeyboardInterrupt):
                self.invoke()
        self.assertEqual(self.snapshot(), before)
        self.assertTrue((self.source / "empty").is_dir())
        self.assertEqual(gitutil.git(["ls-files", "--stage"], self.root), staged)

    def test_unavailable_prerequisite_is_reported_without_writes(self):
        before = self.snapshot()
        with mock.patch.object(g8_9, "check", side_effect=NotImplementedError), contextlib.redirect_stderr(io.StringIO()):
            self.assertEqual(self.invoke()[0], 1)
        self.assertEqual(self.snapshot(), before)

    def test_gate_blocks_when_prerequisite_is_unavailable(self):
        self.assertEqual(self.invoke()[0], 0)
        destination = next(self.project.archive_dir.iterdir())
        with mock.patch.object(g8_9, "check", side_effect=NotImplementedError):
            findings = g9.check(self.context(destination))
        self.assertIn("uat", [f.check for f in findings])

    def test_rollback_preserves_intent_to_add(self):
        intent = self.root / "intent.txt"
        intent.write_text("unstaged", encoding="utf-8")
        gitutil.git(["add", "-N", "intent.txt"], self.root)
        before = gitutil.git(["ls-files", "--debug"], self.root)
        with mock.patch.object(g9, "check", return_value=[Finding("BLOCK", "archive-complete", "模拟损坏")]):
            self.assertEqual(self.invoke()[0], 3)
        after = gitutil.git(["ls-files", "--debug"], self.root)
        self.assertIn("intent.txt", after)
        self.assertEqual(gitutil.git(["diff", "--cached", "--name-only", "--ita-invisible-in-index", "--", "intent.txt"], self.root), "")
        self.assertEqual(gitutil.git(["diff", "--name-only", "--", "intent.txt"], self.root), "intent.txt")

    def test_adr_accepts_comparison_in_decision_reason(self):
        text = fixture("design.md").replace("需要兼容已有流程", "延迟必须 < 100 ms")
        (self.source / "design.md").write_text(text, encoding="utf-8")
        self.assertEqual(self.invoke()[0], 0)
        adr = next(self.project.decisions_dir.glob("*.md")).read_text(encoding="utf-8")
        self.assertIn("延迟必须 < 100 ms", adr)

    def test_rollback_preserves_index_flags_and_ignored_intent(self):
        for name in ("assume.txt", "skip.txt", "both.txt"):
            (self.root / name).write_text("tracked", encoding="utf-8")
        gitutil.git(["add", "assume.txt", "skip.txt", "both.txt"], self.root)
        gitutil.git(["update-index", "--assume-unchanged", "assume.txt", "both.txt"], self.root)
        gitutil.git(["update-index", "--skip-worktree", "skip.txt", "both.txt"], self.root)
        (self.root / ".gitignore").write_text("ignored.txt\n", encoding="utf-8")
        (self.root / "ignored.txt").write_text("unstaged", encoding="utf-8")
        gitutil.git(["add", "-f", "-N", "ignored.txt"], self.root)
        before = gitutil.git(["ls-files", "-v"], self.root)
        with mock.patch.object(g9, "check", return_value=[Finding("BLOCK", "archive-complete", "模拟损坏")]):
            self.assertEqual(self.invoke()[0], 3)
        self.assertEqual(gitutil.git(["ls-files", "-v"], self.root), before)
        self.assertEqual(gitutil.git(["diff", "--cached", "--name-only", "--ita-invisible-in-index", "--", "ignored.txt"], self.root), "")

    def test_deleted_intent_file_is_rejected_before_publication(self):
        intent = self.root / "intent.txt"
        intent.write_text("unstaged", encoding="utf-8")
        gitutil.git(["add", "-N", "intent.txt"], self.root)
        intent.unlink()
        before = self.snapshot()
        staged = gitutil.git(["ls-files", "--stage", "-v"], self.root)
        for dry_run in (True, False):
            with self.subTest(dry_run=dry_run):
                self.assertEqual(self.invoke(dry_run)[0], 3)
                self.assertEqual(self.snapshot(), before)
                self.assertEqual(gitutil.git(["ls-files", "--stage", "-v"], self.root), staged)
                self.assertFalse(intent.exists())


if __name__ == "__main__":
    unittest.main()
