"""End-to-end CLI flows of T2 in a throwaway git repo. Gates, retrospective and
grants belong to other tasks, so they are stubbed here."""

import datetime
import json
import unittest
from pathlib import Path
from unittest import mock

from tests import CLI_LIB  # noqa: F401
from tests.support_t2 import cli, git, java_repo, mdparse_ready
from spec_driven.errors import BLOCK, ERROR, OK, WARN


def meta_of(root, change):
    return json.loads((root / ".openspec/changes" / change / ".meta.json").read_text(encoding="utf-8"))


def gates_return(code):
    return mock.patch("spec_driven.gates.evaluate", return_value=([], code))


class NewTest(unittest.TestCase):
    def test_feature(self):
        with java_repo() as root:
            code, out = cli("new", "batch-approve")
            self.assertEqual(code, OK, out)
            d = root / ".openspec/changes/batch-approve"
            for f in (".meta.json", "proposal.md", "invariants.json"):
                self.assertTrue((d / f).is_file(), f)
            m = meta_of(root, "batch-approve")
            self.assertEqual((m["mode"], m["complexity"], m["tierConfirmed"]), ("feature", "M", False))
            self.assertEqual(m["branch"], "feat/batch-approve")
            self.assertEqual(git(root, "branch", "--show-current"), "feat/batch-approve")
            self.assertEqual(m["baseCommit"], git(root, "rev-parse", "HEAD"))
            self.assertIn("gate-0", out)

    def test_bugfix_name_and_branch(self):
        with java_repo() as root:
            code, out = cli("new", "--mode", "bugfix", "--slug", "Login 500 after redirect!")
            self.assertEqual(code, OK, out)
            name = "fix-%s-login-500-after-redirect" % datetime.date.today().strftime("%Y%m%d")
            m = meta_of(root, name)
            self.assertEqual((m["mode"], m["tierConfirmed"], m["branch"]), ("bugfix", True, "fix/" + name))

    def test_no_branch(self):
        with java_repo() as root:
            cli("new", "stay-on-main", "--no-branch")
            self.assertEqual(meta_of(root, "stay-on-main")["branch"], "main")

    def test_rejections(self):
        with java_repo() as root:
            for argv in (["new", "Bad_Name"], ["new", "abc"], ["new"], ["new", "--mode", "bugfix"]):
                self.assertEqual(cli(*argv)[0], ERROR, argv)
            cli("new", "twice-change", "--no-branch")
            self.assertIn("已存在", cli("new", "twice-change", "--no-branch")[1])
            git(root, "rev-parse", "HEAD")
        with java_repo() as root:
            import shutil
            shutil.rmtree(str(root / ".git"))
            self.assertIn("git init", cli("new", "no-repo-change")[1])


class StatusResumeTest(unittest.TestCase):
    def test_status_and_resume(self):
        with java_repo():
            self.assertIn("尚未启用", cli("status")[1])
            cli("new", "status-change")
            code, out = cli("status")
            self.assertIn("status-change", out)
            self.assertIn("下一步=0", out)
            data = json.loads(cli("status", "--json")[1])
            self.assertEqual(data["changes"][0]["next"]["next"], "0")
            code, out = cli("resume")
            self.assertEqual(code, OK, out)
            for text in ("status-change", "临时", "Phase 0", "proposal.md"):
                self.assertIn(text, out)


class AdvanceTest(unittest.TestCase):
    def test_moves_skips_and_stops(self):
        with java_repo() as root:
            cli("new", "move-change")
            with gates_return(OK):
                self.assertEqual(cli("advance")[0], OK)
            self.assertEqual(meta_of(root, "move-change")["phase"], "1")
            with mock.patch("spec_driven.retro.append_tier_change"):
                self.assertEqual(cli("complexity", "set", "S")[0], OK)
            with gates_return(BLOCK):
                self.assertEqual(cli("advance")[0], BLOCK)
            self.assertEqual(meta_of(root, "move-change")["phase"], "1")
            with gates_return(OK):
                code, out = cli("advance")
            m = meta_of(root, "move-change")
            self.assertEqual((code, m["phase"]), (OK, "4"), out)
            self.assertEqual([m["phaseStatus"][p] for p in "123"], ["passed", "skipped", "skipped"])
            self.assertTrue(m["skipped"]["2"] and m["skipped"]["3"])

    def test_warn_needs_ack(self):
        with java_repo() as root:
            cli("new", "warn-change")
            with gates_return(WARN):
                self.assertEqual(cli("advance")[0], WARN)
                self.assertEqual(meta_of(root, "warn-change")["phase"], "0")
                self.assertEqual(cli("advance", "--ack-warn")[0], OK)
            self.assertEqual(meta_of(root, "warn-change")["phase"], "1")

    def test_unimplemented_gate_is_unavailable(self):
        with java_repo():
            cli("new", "stub-change")
            with mock.patch("spec_driven.gates.evaluate", side_effect=NotImplementedError):
                code, out = cli("advance")
            self.assertEqual(code, ERROR)
            self.assertIn("不可用", out)

    def test_phase_6_runs_sub_gates(self):
        with java_repo() as root:
            cli("new", "six-change")
            d = root / ".openspec/changes/six-change/.meta.json"
            m = json.loads(d.read_text(encoding="utf-8"))
            m["phase"] = "6"
            d.write_text(json.dumps(m), encoding="utf-8")
            with gates_return(OK) as ev:
                cli("advance")
            self.assertEqual([c.args[0] for c in ev.call_args_list], ["6", "6.5", "6.7"])


class RetryTest(unittest.TestCase):
    def test_retry_marks_downstream_stale(self):
        with java_repo() as root:
            cli("new", "retry-change")
            with gates_return(OK):
                for _ in range(4):
                    cli("advance")
            self.assertEqual(meta_of(root, "retry-change")["phase"], "4")
            code, out = cli("retry", "1", "--reason", "AC 漏了导出")
            self.assertEqual(code, OK, out)
            m = meta_of(root, "retry-change")
            self.assertEqual((m["phase"], m["staleFrom"]), ("1", "1"))
            self.assertEqual([m["phaseStatus"][p] for p in "1234"], ["in_progress", "stale", "stale", "stale"])
            proposal = (root / ".openspec/changes/retry-change/proposal.md").read_text(encoding="utf-8")
            self.assertTrue(proposal.startswith("<!-- revised at "))
            self.assertIn("AC 漏了导出", proposal.splitlines()[0])
            with gates_return(OK):
                cli("advance")
            m = meta_of(root, "retry-change")
            self.assertEqual((m["phase"], m["phaseStatus"]["2"]), ("2", "in_progress"))

    def test_retry_rejections(self):
        with java_repo():
            cli("new", "retry-bad")
            self.assertEqual(cli("retry", "1", "--reason", "x")[0], ERROR)   # not earlier than phase 0
            with gates_return(OK):
                cli("advance")
                cli("advance")
            self.assertEqual(cli("retry", "0", "--reason", "x")[0], ERROR)
            self.assertEqual(cli("retry", "7", "--reason", "x")[0], ERROR)
            self.assertEqual(cli("retry", "1", "--reason", " ")[0], ERROR)


class ComplexityTest(unittest.TestCase):
    def test_select_raise_and_guarded_downgrade(self):
        with java_repo() as root:
            cli("new", "tier-change")
            with mock.patch("spec_driven.retro.append_tier_change") as rec:
                self.assertEqual(cli("complexity", "set", "M")[0], OK)
                self.assertEqual(rec.call_args.args[3], "选定")
                self.assertEqual(cli("complexity", "set", "L")[0], OK)
                self.assertEqual(rec.call_args.args[3], "升档")
                code, out = cli("complexity", "set", "S")
                self.assertEqual(code, ERROR)
                self.assertIn("确认降档 tier-change S", out)
                with mock.patch("spec_driven.grants.consume", return_value=False):
                    self.assertEqual(cli("complexity", "set", "S", "--downgrade", "--reason", "小")[0], ERROR)
                self.assertEqual(meta_of(root, "tier-change")["complexity"], "L")
                with mock.patch("spec_driven.grants.consume", return_value=True) as consume:
                    self.assertEqual(cli("complexity", "set", "S", "--downgrade", "--reason", "小")[0], OK)
                consume.assert_called_once()
                self.assertEqual(consume.call_args.args[1:4], ("tier-change", "downgrade", "S"))
                self.assertEqual(rec.call_args.args[3], "降档")
            self.assertEqual(meta_of(root, "tier-change")["complexity"], "S")

    def test_record_failure_leaves_tier(self):
        with java_repo() as root:
            cli("new", "norec-change")
            with mock.patch("spec_driven.retro.append_tier_change", side_effect=NotImplementedError):
                code, out = cli("complexity", "set", "L")
            self.assertEqual(code, ERROR)
            self.assertIn("档位未修改", out)
            m = meta_of(root, "norec-change")
            self.assertEqual((m["complexity"], m["tierConfirmed"]), ("M", False))

    def test_show_and_recheck_only_raises(self):
        with java_repo() as root:
            cli("new", "recheck-change")
            d = root / ".openspec/changes/recheck-change"
            (d / "proposal.md").write_text("改一个文案 AC-1", encoding="utf-8")
            code, out = cli("complexity", "show")
            self.assertIn("推荐档位 S", out)
            with mock.patch("spec_driven.retro.append_tier_change"):
                cli("complexity", "set", "M")
                self.assertEqual(cli("complexity", "recheck", "--phase", "2")[0], OK)   # S < M: keep
                (d / "design.md").write_text("跨服务 MQ 分布式事务，新增接口，建表，状态机", encoding="utf-8")
                self.assertEqual(cli("complexity", "recheck", "--phase", "2")[0], WARN)
                self.assertEqual(meta_of(root, "recheck-change")["complexity"], "M")
                self.assertEqual(cli("complexity", "recheck", "--phase", "2", "--apply")[0], OK)
            self.assertEqual(meta_of(root, "recheck-change")["complexity"], "L")


class DesignTest(unittest.TestCase):
    def test_show_and_set(self):
        with java_repo() as root:
            cli("new", "design-change")
            d = root / ".openspec/changes/design-change"
            (d / "design.md").write_text("**AI 推荐**：方案 A\n\n**最终选择**：方案 B\n", encoding="utf-8")
            code, out = cli("design", "show")
            self.assertIn("方案 A", out)
            self.assertEqual(cli("design", "set")[0], OK)
            self.assertEqual(meta_of(root, "design-change")["designDecision"], "方案 B")
            self.assertEqual(cli("design", "set", "方案 A")[0], WARN)
            self.assertEqual(cli("design", "show")[0], WARN)


@unittest.skipUnless(mdparse_ready(), "needs T1 mdparse.checkboxes")
class TasksSyncTest(unittest.TestCase):
    def test_preview_then_apply(self):
        from tests.support_t2 import commit
        with java_repo() as root:
            cli("new", "sync-change")
            tasks = root / ".openspec/changes/sync-change/tasks.md"
            tasks.write_text("- [ ] T1. a\n- [ ] T2. b\n", encoding="utf-8")
            commit(root, "impl\n\nTask-Id: T1", {"src/A.java": "a"})
            code, out = cli("tasks-sync")
            self.assertIn("+ - [x] T1. a", out)
            self.assertIn("[ ] T1", tasks.read_text(encoding="utf-8"))
            cli("tasks-sync", "--apply")
            self.assertIn("[x] T1", tasks.read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
