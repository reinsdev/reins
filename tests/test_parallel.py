"""Phase 6 multi-worker lane (T19): wave planning, worktrees, serial merge back."""

import json
import subprocess
import unittest
from pathlib import Path

from tests import CLI_LIB  # noqa: F401
from tests.support_t2 import cli, git, java_repo
from spec_driven import parallel

CHANGE = "par-demo"


def tasks_md(*rows):
    lines = ["# Tasks: %s" % CHANGE, "", "## Application Layer", ""]
    for tid, deps, scope in rows:
        lines.append("- [ ] %s. 实现 %s；关联：SC-demo-001；依赖：%s；预估：1 小时；范围：%s" % (tid, tid, deps, scope))
    return "\n".join(lines) + "\n"


class PlanTest(unittest.TestCase):
    def test_dependency_makes_second_wave(self):
        p = parallel.plan(tasks_md(("T1", "无", "src/a"), ("T2", "无", "src/b"), ("T3", "T1", "src/c")), {})
        self.assertEqual(p.problems, [])
        self.assertEqual(p.waves, [["T1", "T2"], ["T3"]])
        est = parallel.estimate(p)
        self.assertEqual((est["serialHours"], est["parallelHours"], est["verdict"]), (3, 2, "建议"))

    def test_overlapping_scope_never_shares_a_wave(self):
        p = parallel.plan(tasks_md(("T1", "无", "src/a"), ("T2", "无", "src/a/X.java"),
                                   ("T3", "无", "src/b")), {})
        self.assertEqual(p.waves, [["T1", "T3"], ["T2"]])
        p = parallel.plan(tasks_md(("T1", "无", "src/a/X.java"), ("T2", "无", "src/a/*.java")), {})
        self.assertEqual(p.waves, [["T1"], ["T2"]])
        self.assertEqual(parallel.estimate(p)["verdict"], "不建议")

    def test_overlap_rules(self):
        self.assertTrue(parallel.overlaps("src/a", "src/a/B.java"))
        self.assertTrue(parallel.overlaps("src/a/", "src/a"))
        self.assertFalse(parallel.overlaps("src/a", "src/ab"))
        self.assertTrue(parallel.overlaps("src/**/X.java", "src/b/Y.java"))
        self.assertFalse(parallel.overlaps("src/a/*.java", "src/b/Y.java"))

    def test_cycle_is_refused(self):
        p = parallel.plan(tasks_md(("T1", "T2", "src/a"), ("T2", "T1", "src/b"), ("T3", "无", "src/c")), {})
        self.assertEqual(len(p.problems), 1)
        self.assertIn("依赖有环", p.problems[0])
        self.assertIn("T1", p.problems[0])

    def test_missing_scope_or_dependency_is_refused(self):
        text = tasks_md(("T1", "无", "src/a")) + "- [ ] T2. 无范围；依赖：无；预估：1 小时\n" \
            + "- [ ] T3. 无依赖；预估：1 小时；范围：src/c\n" + "- [ ] T4. 坏路径；依赖：T9；预估：1 小时；范围：../x\n"
        problems = parallel.plan(text, {}).problems
        self.assertTrue(any("T2 缺少「范围」" in x for x in problems), problems)
        self.assertTrue(any("T3 缺少「依赖」" in x for x in problems), problems)
        self.assertTrue(any("T4 的范围含无效路径" in x for x in problems), problems)
        self.assertTrue(any("不存在的任务 T9" in x for x in problems), problems)
        self.assertEqual(parallel.plan(text, {}).waves, [])

    def test_done_and_deferred_tasks_are_not_scheduled(self):
        text = tasks_md(("T1", "无", "src/a"), ("T2", "T1", "src/b")).replace("- [ ] T1", "- [x] T1")
        text += "- [~] T3. 延期；依赖：无；预估：1 小时；范围：src/c\n- [ ] T4. 后续；依赖：T3；预估：1 小时；范围：src/d\n"
        p = parallel.plan(text, {"T1": ["abc"]})
        self.assertEqual((p.done, p.deferred, p.waves), (["T1"], ["T3"], [["T2", "T4"]]))
        self.assertTrue(any("T4 依赖已延期的 T3" in n for n in p.notes))

    def test_unknown_estimate_is_reported(self):
        text = tasks_md(("T1", "无", "src/a")) + "- [ ] T2. 无预估；依赖：无；范围：src/b\n"
        est = parallel.estimate(parallel.plan(text, {}))
        self.assertEqual(est["verdict"], "无法判断")


def commit_in(cwd, files, *message):
    for name, text in files.items():
        p = Path(cwd) / name
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(text, encoding="utf-8")
    git(cwd, "add", "-A")
    args = ["git", "commit", "-q"]
    for m in message:
        args += ["-m", m]
    r = subprocess.run(args, cwd=str(cwd), capture_output=True, encoding="utf-8")
    return r.returncode, r.stderr


class FlowTest(unittest.TestCase):
    def setup_change(self, root, rows, enabled=True):
        code, out = cli("new", CHANGE)
        self.assertIn(code, (0, 2), out)
        change_dir = root / ".openspec/changes" / CHANGE
        meta_path = change_dir / ".meta.json"
        m = json.loads(meta_path.read_text(encoding="utf-8"))
        m["phase"] = "6"
        meta_path.write_text(json.dumps(m, ensure_ascii=False, indent=2), encoding="utf-8")
        (change_dir / "tasks.md").write_text(tasks_md(*rows), encoding="utf-8")
        (root / ".openspec/.config.json").write_text(
            json.dumps({"parallel": {"enabled": enabled}}), encoding="utf-8")
        self.assertEqual(commit_in(root, {}, "spec: tasks")[0], 0)
        return change_dir

    def worktree(self, out, task):
        data = json.loads(out)
        return Path(next(w["path"] for w in data["worktrees"] if w["task"] == task))

    def test_disabled_refuses_run_and_merge(self):
        with java_repo() as root:
            self.setup_change(root, [("T1", "无", "src/a")], enabled=False)
            code, out = cli("parallel", "plan")
            self.assertEqual(code, 0, out)
            self.assertIn("parallel.enabled=false", out)
            for action in ("run", "merge"):
                code, out = cli("parallel", action)
                self.assertEqual(code, 1, out)
                self.assertIn("parallel.enabled=false", out)
            self.assertEqual(git(root, "worktree", "list").count("\n"), 0)

    def test_plan_refuses_cycle(self):
        with java_repo() as root:
            self.setup_change(root, [("T1", "T2", "src/a"), ("T2", "T1", "src/b")])
            code, out = cli("parallel", "plan")
            self.assertEqual(code, 1, out)
            self.assertIn("依赖有环", out)
            code, out = cli("parallel", "run")
            self.assertEqual(code, 1, out)

    def test_two_waves_then_gate_6_5_passes(self):
        with java_repo() as root:
            change_dir = self.setup_change(
                root, [("T1", "无", "src/a"), ("T2", "无", "src/b"), ("T3", "T1", "src/c")])
            code, out = cli("parallel", "plan")
            self.assertEqual(code, 0, out)
            self.assertIn("第 1 波", out)
            self.assertIn("第 2 波", out)

            code, out = cli("parallel", "run", "--json")
            self.assertEqual(code, 0, out)
            self.assertEqual([w["task"] for w in json.loads(out)["worktrees"]], ["T1", "T2"])
            t1, t2 = self.worktree(out, "T1"), self.worktree(out, "T2")
            self.assertNotIn(str(root), str(t1))
            self.assertTrue((t1 / ".openspec/changes" / CHANGE / ".meta.json").is_file())

            # The git hooks guard every worktree: a Phase 6 code commit needs Task-Id.
            code, err = commit_in(t1, {"src/a/A.java": "a\n"}, "no trailer")
            self.assertNotEqual(code, 0)
            self.assertIn("Task-Id", err)
            self.assertEqual(commit_in(t1, {}, "GREEN T1", "Task-Id: T1")[0], 0)

            code, out = cli("parallel", "merge")
            self.assertEqual(code, 1, out)
            self.assertIn("T2 还没有", out)

            self.assertEqual(commit_in(t2, {"src/b/B.java": "b\n"}, "GREEN T2", "Task-Id: T2")[0], 0)
            code, out = cli("parallel", "merge")
            self.assertEqual(code, 0, out)
            self.assertIn("还有 1 波待做", out)
            self.assertFalse(t1.exists())
            self.assertFalse(t2.exists())
            self.assertEqual(git(root, "branch", "--list", "spec-parallel/*"), "")
            self.assertTrue((root / "src/a/A.java").is_file() and (root / "src/b/B.java").is_file())
            self.assertIn("- [x] T1", (change_dir / "tasks.md").read_text(encoding="utf-8"))

            code, out = cli("parallel", "run", "--json")
            self.assertEqual(code, 0, out)
            t3 = self.worktree(out, "T3")
            self.assertTrue((t3 / "src/a/A.java").is_file())
            self.assertEqual(commit_in(t3, {"src/c/C.java": "c\n"}, "GREEN T3", "Task-Id: T3")[0], 0)
            code, out = cli("parallel", "merge")
            self.assertEqual(code, 0, out)
            self.assertIn("gate-6.5：通过", out)
            self.assertFalse(t3.exists())
            self.assertNotIn("- [ ]", (change_dir / "tasks.md").read_text(encoding="utf-8"))
            self.assertEqual(git(root, "rev-parse", "--abbrev-ref", "HEAD"), "feat/" + CHANGE)

            code, out = cli("parallel", "run")
            self.assertEqual(code, 0, out)
            self.assertIn("没有待做的任务", out)

    def test_conflict_aborts_and_keeps_everything(self):
        with java_repo() as root:
            self.setup_change(root, [("T1", "无", "src/a"), ("T2", "无", "src/b")])
            work_head = git(root, "rev-parse", "HEAD")
            code, out = cli("parallel", "run", "--json")
            self.assertEqual(code, 0, out)
            t1, t2 = self.worktree(out, "T1"), self.worktree(out, "T2")
            self.assertEqual(commit_in(t1, {"shared.txt": "from T1\n"}, "GREEN T1", "Task-Id: T1")[0], 0)
            self.assertEqual(commit_in(t2, {"shared.txt": "from T2\n"}, "GREEN T2", "Task-Id: T2")[0], 0)

            code, out = cli("parallel", "merge")
            self.assertEqual(code, 3, out)
            self.assertIn("T2 合入集成分支失败", out)
            self.assertIn("shared.txt", out)
            self.assertIn("本次已合入：T1", out)
            self.assertEqual(git(root, "rev-parse", "HEAD"), work_head)
            self.assertTrue(t1.is_dir() and t2.is_dir())
            integ = Path(parallel.worktrees(root)["spec-parallel/" + CHANGE])
            self.assertEqual((integ / "shared.txt").read_text(encoding="utf-8"), "from T1\n")
            self.assertEqual(git(integ, "status", "--porcelain"), "")
            self.assertEqual((t2 / "shared.txt").read_text(encoding="utf-8"), "from T2\n")

            # A human resolves it in T2's worktree; the rerun skips T1 and finishes.
            subprocess.run(["git", "merge", "-q", "spec-parallel/" + CHANGE], cwd=str(t2),
                           capture_output=True)
            self.assertEqual(commit_in(t2, {"shared.txt": "both\n"}, "resolve", "Task-Id: T2")[0], 0)
            code, out = cli("parallel", "merge")
            self.assertEqual(code, 0, out)
            self.assertIn("T1 已在集成分支上，跳过", out)
            self.assertEqual((root / "shared.txt").read_text(encoding="utf-8"), "both\n")
            self.assertFalse(integ.exists() or t1.exists() or t2.exists())

    def test_worker_cannot_write_tasks_md(self):
        with java_repo() as root:
            self.setup_change(root, [("T1", "无", "src/a")])
            code, out = cli("parallel", "run", "--json")
            self.assertEqual(code, 0, out)
            t1 = self.worktree(out, "T1")
            tasks = ".openspec/changes/%s/tasks.md" % CHANGE
            edited = (t1 / tasks).read_text(encoding="utf-8").replace("- [ ] T1", "- [x] T1")
            code, err = commit_in(t1, {"src/a/A.java": "a\n", tasks: edited}, "GREEN T1", "Task-Id: T1")
            self.assertNotEqual(code, 0)
            self.assertIn("已冻结", err)
            # Skipping the hooks does not get it merged either.
            git(t1, "commit", "-q", "--no-verify", "-m", "GREEN T1", "-m", "Task-Id: T1")
            code, out = cli("parallel", "merge")
            self.assertEqual(code, 1, out)
            self.assertIn("worker 不能写 tasks.md", out)
            self.assertTrue(t1.is_dir())

    def test_run_needs_clean_tree_and_phase_6(self):
        with java_repo() as root:
            change_dir = self.setup_change(root, [("T1", "无", "src/a")])
            (root / "wip.txt").write_text("x\n", encoding="utf-8")
            code, out = cli("parallel", "run")
            self.assertEqual(code, 1, out)
            self.assertIn("wip.txt", out)
            (root / "wip.txt").unlink()
            meta_path = change_dir / ".meta.json"
            m = json.loads(meta_path.read_text(encoding="utf-8"))
            m["phase"] = "5"
            meta_path.write_text(json.dumps(m), encoding="utf-8")
            code, out = cli("parallel", "run")
            self.assertEqual(code, 1, out)
            self.assertIn("Phase 6", out)


if __name__ == "__main__":
    unittest.main()
