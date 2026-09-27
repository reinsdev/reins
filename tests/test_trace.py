"""T18: `spec-driven trace` follows AC / REQ / SC / task ids through the artifact chain."""

import json
import os
import shutil
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from tests import CLI_LIB  # noqa: F401
from tests.support_t2 import cli, commit, git, java_repo
from spec_driven import meta, traceability
from spec_driven.errors import ERROR, OK, WARN

FIXTURES = Path(__file__).resolve().parent / "fixtures" / "t18"


def make_change(root, name, fixture, mode="feature", phase="8", skipped=None):
    change_dir = root / ".openspec/changes" / name
    change_dir.mkdir(parents=True)
    for f in (FIXTURES / fixture).iterdir():
        shutil.copy(str(f), str(change_dir / f.name))
    m = meta.new(name, mode, "main", git(root, "rev-parse", "HEAD") if (root / ".git").exists() else "")
    m["phase"] = phase
    m["skipped"].update(skipped or {})
    meta.save(change_dir, m)
    return change_dir


def task_commit(root, subject, task, phase=None, path="src/main/java/demo/Approve.java"):
    trailers = "Task-Id: %s" % task + ("\nTDD-Phase: %s" % phase if phase else "")
    return commit(root, "%s\n\n%s" % (subject, trailers), {path: subject + "\n"})


def trace_json(*argv):
    code, out = cli("trace", "--json", *argv)
    return code, json.loads(out)


def ids(entries, key="id"):
    return [e[key] for e in entries]


class FeatureTraceTest(unittest.TestCase):
    """M-tier feature: AC -> SC/REQ -> tasks -> commits -> QA."""

    def setUp(self):
        self.ctx = java_repo()
        self.root = self.ctx.__enter__()
        self.dir = make_change(self.root, "demo-change", "feature")
        self.red = task_commit(self.root, "RED: 批量审批测试", "T1", "RED")
        self.green = task_commit(self.root, "批量审批实现", "T1", "GREEN")

    def tearDown(self):
        self.ctx.__exit__(None, None, None)

    def test_from_ac(self):
        code, out = cli("trace", "AC-1")
        self.assertEqual(code, OK, out)
        for text in ("AC-1  proposal.md:11", "REQ-demo-001", "SC-demo-001", "SC-demo-E1", "T1  [ ]  tasks.md:5",
                     "RED", self.red[:7], "GREEN", self.green[:7], "SC-demo-001  PASS", "SC-demo-E1  FAIL",
                     "跳过：T3 已延期", "链路完整"):
            self.assertIn(text, out)
        self.assertNotIn("REQ-demo-002", out)

    def test_from_sc(self):
        code, r = trace_json("SC-demo-001")
        self.assertEqual(code, OK, r)
        self.assertEqual(ids(r["reqs"]), ["REQ-demo-001"])
        self.assertEqual(ids(r["acs"]), ["AC-1"])
        self.assertEqual(ids(r["tasks"]), ["T1", "T3"])
        self.assertEqual([(c["task"], c["phase"], c["hash"]) for c in r["commits"]],
                         [("T1", "RED", self.red), ("T1", "GREEN", self.green)])
        self.assertEqual([(q["sc"], q["result"]) for q in r["qa"]], [("SC-demo-001", "PASS")])
        self.assertTrue(r["complete"])
        self.assertEqual((r["change"], r["archived"], r["changeDir"]),
                         ("demo-change", False, ".openspec/changes/demo-change"))

    def test_from_task(self):
        code, r = trace_json("T1")
        self.assertEqual(code, OK, r)
        self.assertEqual(ids(r["scs"]), ["SC-demo-001", "SC-demo-E1"])
        self.assertEqual(ids(r["reqs"]), ["REQ-demo-001"])
        self.assertEqual(ids(r["acs"]), ["AC-1"])
        self.assertEqual(ids(r["qa"], "sc"), ["SC-demo-001", "SC-demo-E1"])

    def test_from_req(self):
        code, r = trace_json("REQ-demo-002")
        self.assertEqual(ids(r["scs"]), ["SC-demo-002"])
        self.assertEqual(ids(r["acs"]), ["AC-2"])
        self.assertEqual(ids(r["tasks"]), ["T2"])
        self.assertEqual(code, WARN)

    def test_missing_links_are_listed_not_guessed(self):
        code, out = cli("trace", "AC-2")
        self.assertEqual(code, WARN, out)
        self.assertIn("缺失：没有带 Task-Id: T2 的提交", out)
        self.assertIn("缺失：qa-report.md 的 SC 验证结果里没有 SC-demo-002", out)
        self.assertIn("链路不完整：缺失 2 处", out)
        code, r = trace_json("AC-2")
        self.assertEqual([(m["link"], m["id"]) for m in r["missing"]], [("commits", "T2"), ("qa", "SC-demo-002")])
        self.assertEqual(r["commits"], [])

    def test_red_alone_does_not_complete_a_task(self):
        task_commit(self.root, "RED: 上限测试", "T2", "RED")
        code, r = trace_json("T2")
        self.assertIn(("commits", "T2 只有 RED 提交，还没有 GREEN"), [(m["link"], m["reason"]) for m in r["missing"]])
        self.assertEqual([c["phase"] for c in r["commits"]], ["RED"])

    def test_undefined_reference_is_marked_missing(self):
        with (self.dir / "tasks.md").open("a", encoding="utf-8") as f:
            f.write("- [ ] T4. 补充；关联：SC-demo-009；依赖：T1；预估：1 小时；范围：a.java\n")
        code, r = trace_json("SC-demo-009")
        self.assertEqual(code, WARN)
        self.assertEqual(r["scs"], [{"id": "SC-demo-009", "defined": False}])
        self.assertIn(("spec", "spec.md 里没有 SC-demo-009"), [(m["link"], m["reason"]) for m in r["missing"]])
        self.assertEqual(ids(r["tasks"]), ["T4"])

    def test_unknown_or_malformed_id(self):
        code, out = cli("trace", "AC-9")
        self.assertEqual(code, ERROR)
        self.assertIn("都没有 AC-9", out)
        code, out = cli("trace", "story-1")
        self.assertEqual(code, ERROR)
        self.assertIn("不是 AC / REQ / SC / 任务编号", out)

    def test_absent_artifacts_are_missing(self):
        (self.dir / "spec.md").unlink()
        (self.dir / "qa-report.md").unlink()
        code, r = trace_json("AC-1")
        self.assertEqual(code, WARN)
        reasons = [m["reason"] for m in r["missing"]]
        self.assertIn("还没有 spec.md", reasons)
        self.assertEqual(r["scs"], [])

    def test_read_only(self):
        def snapshot():
            return {p.as_posix(): p.read_bytes() for p in self.root.rglob("*")
                    if p.is_file() and ".git" not in p.parts}
        before, status = snapshot(), git(self.root, "status", "--porcelain")
        for ident in ("AC-1", "AC-2", "SC-demo-E1", "REQ-demo-001", "T1", "T3"):
            cli("trace", ident)
            cli("trace", "--json", ident)
        self.assertEqual(snapshot(), before)
        self.assertEqual(git(self.root, "status", "--porcelain"), status)


class SkippedSpecTraceTest(unittest.TestCase):
    """S-tier feature links tasks to AC; slim bugfix links tasks to change points."""

    def setUp(self):
        self.ctx = java_repo()
        self.root = self.ctx.__enter__()

    def tearDown(self):
        self.ctx.__exit__(None, None, None)

    def test_s_tier_ac_links_tasks_directly(self):
        make_change(self.root, "demo-change", "s-tier",
                    skipped={"2": "S 档", "3": "S 档", "5": "S 档", "7": "S 档"})
        green = task_commit(self.root, "实现", "T1")
        code, out = cli("trace", "AC-1")
        self.assertEqual(code, OK, out)
        self.assertIn("跳过：Phase 3 已跳过：S 档", out)
        self.assertIn("跳过：Phase 7 已跳过：S 档", out)
        self.assertIn("T1  [ ]  tasks.md:5  关联 AC-1", out)
        self.assertIn(green[:7], out)
        code, r = trace_json("T1")
        self.assertEqual((code, ids(r["acs"]), r["scs"]), (OK, ["AC-1"], []))
        code, r = trace_json("AC-2")
        self.assertEqual(code, WARN)
        self.assertEqual([m["id"] for m in r["missing"]], ["T2"])

    def test_s_tier_ac_without_task(self):
        change_dir = make_change(self.root, "demo-change", "s-tier", skipped={"3": "S 档", "7": "S 档"})
        text = (change_dir / "tasks.md").read_text(encoding="utf-8").replace("关联：AC-2", "关联：AC-1")
        (change_dir / "tasks.md").write_text(text, encoding="utf-8")
        code, r = trace_json("AC-2")
        self.assertEqual(code, WARN)
        self.assertIn(("tasks", "没有任务关联 AC-2"), [(m["link"], m["reason"]) for m in r["missing"]])

    def test_slim_bugfix_goes_through_change_points(self):
        make_change(self.root, "fix-20260927-login-500", "bugfix", mode="bugfix",
                    skipped={"2": "bugfix 范围小", "3": "bugfix 范围小"})
        task_commit(self.root, "判空", "T1")
        code, r = trace_json("AC-1")
        self.assertEqual(code, OK, r)
        self.assertEqual(ids(r["points"]), ["P1"])
        self.assertEqual(ids(r["tasks"]), ["T1"])
        code, r = trace_json("AC-regression")
        self.assertEqual((ids(r["points"]), ids(r["tasks"])), (["P2"], ["T-regression"]))
        self.assertEqual([m["reason"] for m in r["missing"]], ["没有带 Task-Id: T-regression 的提交"])
        code, r = trace_json("T-regression")
        self.assertEqual(ids(r["acs"]), ["AC-regression"])


class ArchivedTraceTest(unittest.TestCase):
    def test_archived_change_stops_at_the_archive_commit(self):
        with java_repo() as root:
            make_change(root, "demo-change", "feature")
            done = task_commit(root, "上限校验", "T2")
            archive = root / ".openspec/changes/archive"
            archive.mkdir()
            git(root, "add", "-A")
            git(root, "mv", ".openspec/changes/demo-change", ".openspec/changes/archive/2026-09-27-demo-change")
            git(root, "commit", "-q", "-m", "archive demo-change")
            task_commit(root, "另一个 change 的 T2", "T2", path="src/main/java/demo/Other.java")
            self.assertEqual(cli("trace", "AC-2")[0], ERROR)  # no active change
            code, r = trace_json("AC-2", "--change", "demo-change")
            self.assertEqual([c["hash"] for c in r["commits"]], [done])
            self.assertTrue(r["archived"])
            self.assertEqual(r["changeDir"], ".openspec/changes/archive/2026-09-27-demo-change")
            code, out = cli("trace", "SC-demo-001", "--change", "2026-09-27-demo-change")
            self.assertIn("已归档", out)
            self.assertEqual(cli("trace", "AC-1", "--change", "nope-change")[0], ERROR)


class NoGitTraceTest(unittest.TestCase):
    def test_commits_missing_without_git(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp).resolve()
            make_change(root, "demo-change", "feature")
            old = os.getcwd()
            os.chdir(str(root))
            try:
                with mock.patch.dict(os.environ, {"REINS_HOME": str(root / "home")}):
                    code, r = trace_json("SC-demo-001")
            finally:
                os.chdir(old)
            self.assertEqual(code, WARN)
            self.assertEqual([m["link"] for m in r["missing"]], ["commits"])
            self.assertIn("不是 git 仓库", r["missing"][0]["reason"])
            self.assertEqual(ids(r["tasks"]), ["T1", "T3"])


class KindTest(unittest.TestCase):
    def test_kind_of(self):
        cases = {"AC-1": "AC", "AC-regression": "AC", "REQ-demo-001": "REQ", "SC-demo-E2": "SC",
                 "SC-demo-001": "SC", "T12": "TASK", "T-regression": "TASK", "SC-demo": None, "ac-1": None}
        self.assertEqual({k: traceability.kind_of(k) for k in cases}, cases)


if __name__ == "__main__":
    unittest.main()
