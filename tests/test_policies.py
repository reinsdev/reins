"""T6 hook policies: block / allow / odd input for each rule, and the waive grant flow."""

import json
import os
import sys
import tempfile
import types
import unittest
from pathlib import Path
from unittest import mock

from tests import CLI_LIB  # noqa: F401
from tests.support_t2 import cli, java_repo
from spec_driven import gates, grants, hook, meta, policies, retro
from spec_driven.policies import bash_guard, gate_router, spec_gate, waive_grant

CHANGE = "demo-change"


def make_project(tmp, phase="4"):
    root = Path(tmp) / "proj"
    d = root / ".openspec/changes" / CHANGE
    d.mkdir(parents=True)
    m = meta.new(CHANGE, "feature", "feat/x", "abc")
    m["phase"] = phase
    (d / ".meta.json").write_text(json.dumps(m), encoding="utf-8")
    (root / ".openspec/changes/archive/2026-01-01-old").mkdir(parents=True)
    return root


def edit(root, path, agent=""):
    return {"kind": "edit", "paths": [path], "command": "", "cwd": str(root), "agent": agent}


def shell(root, command, agent=""):
    return {"kind": "shell", "paths": [], "command": command, "cwd": str(root), "agent": agent}


class Base(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.env = mock.patch.dict(os.environ, {"REINS_HOME": str(Path(self.tmp.name) / "home")})
        self.env.start()
        self.root = make_project(self.tmp.name)
        self.cd = ".openspec/changes/%s/" % CHANGE

    def tearDown(self):
        self.env.stop()
        self.tmp.cleanup()


class SpecGateTest(Base):
    def blocked(self, path, agent=""):
        return spec_gate.pre_tool(edit(self.root, path, agent))

    def test_upstream_freeze(self):
        self.assertIn("已冻结", self.blocked(self.cd + "proposal.md"))
        self.assertIn("已冻结", self.blocked(self.cd + "spec.md"))
        self.assertIsNone(self.blocked(self.cd + "tasks.md"))            # current phase 4
        self.assertIsNone(self.blocked(self.cd + "qa-report.md"))        # later phase

    def test_cli_only_and_project_files(self):
        for name in (".meta.json", "retrospective.md", ".retro.sha256"):
            self.assertIn("spec-driven", self.blocked(self.cd + name), name)
        self.assertIn("团队配置", self.blocked(".openspec/.config.json"))
        self.assertIn("基线", self.blocked(".openspec/quality-baseline.json"))
        self.assertIn("归档", self.blocked(".openspec/changes/archive/2026-01-01-old/spec.md"))
        self.assertIsNone(self.blocked("src/main/java/A.java"))
        self.assertIsNone(self.blocked(".openspec/architecture.md"))

    def test_absolute_windows_style_and_relative_paths(self):
        abs_path = str(self.root / (self.cd + "proposal.md"))
        self.assertIsNotNone(self.blocked(abs_path))
        ev = hook.normalize({"tool_name": "Edit", "tool_input": {"file_path": abs_path.replace("/", "\\")},
                             "cwd": str(self.root)}, "claude")
        self.assertIsNotNone(spec_gate.pre_tool(dict(ev, cwd=str(self.root))))
        ev = edit(self.root / "src", "../" + self.cd + "proposal.md")
        self.assertIsNotNone(spec_gate.pre_tool(ev))

    def test_agents(self):
        self.assertIsNone(self.blocked(self.cd + "spec-review.md", "spec-evaluator"))
        self.assertIn("只读评审", self.blocked(self.cd + "qa-report.md", "spec-evaluator"))
        self.assertIn("只读评审", self.blocked("src/main/java/A.java", "code-reviewer"))
        self.assertIsNone(self.blocked(self.cd + "implementation-log.md", "implementation-generator"))
        self.assertIn("implementation-generator", self.blocked(self.cd + "tasks.md", "implementation-generator"))
        self.assertIsNone(self.blocked("src/main/java/A.java", "implementation-generator"))

    def test_grants_dir(self):
        self.assertIn("确认口令", self.blocked(str(grants.grants_dir() / "x.json")))

    def test_outside_project_and_non_edit(self):
        self.assertIsNone(spec_gate.pre_tool(edit(Path(self.tmp.name), "notes.md")))
        self.assertIsNone(spec_gate.pre_tool(shell(self.root, "rm " + self.cd + ".meta.json")))


class BashGuardTest(Base):
    def blocked(self, command, agent=""):
        return bash_guard.pre_tool(shell(self.root, command, agent))

    def test_test_deletion(self):
        for c in ("rm -rf src/test", "rm src/test/java/ATest.java", "git rm -r src/test/java",
                  "find src/test -name '*.java' -delete", "cd x && rm -rf ../src/test", 'sh -c "rm -rf src/test"'):
            self.assertIn("测试", self.blocked(c) or "", c)
        self.assertIsNone(self.blocked("rm -rf target"))
        self.assertIsNone(self.blocked("find src/test -name '*.java'"))

    def test_git_hook_bypass(self):
        for c in ("git commit --no-verify -m x", "git commit -n -m x", "git -c core.hooksPath=/dev/null commit -m x",
                  "git config core.hooksPath .nohooks"):
            self.assertIsNotNone(self.blocked(c), c)
        self.assertIsNone(self.blocked("git commit -m 'n; x'"))
        self.assertIsNone(self.blocked("git log -n 3"))

    def test_protected_writes(self):
        for c in ("echo {} > %s.meta.json" % self.cd, "echo x>>%sretrospective.md" % self.cd,
                  "cat x | tee -a %sretrospective.md" % self.cd, "sed -i 's/a/b/' %sproposal.md" % self.cd,
                  "cp /tmp/p.md %sproposal.md" % self.cd, "mv %s.meta.json /tmp/" % self.cd,
                  "git checkout -- %sproposal.md" % self.cd, "python3 -c \"open('.meta.json','w')\"",
                  "echo 1 > .openspec/.config.json", "touch %s/x.json" % grants.grants_dir(),
                  'bash -c "echo x > %s.meta.json"' % self.cd):
            self.assertIsNotNone(self.blocked(c), c)
        for c in ("cat %s.meta.json" % self.cd, "echo x > build.log 2>&1", "sed -i 's/a/b/' src/A.java",
                  "cp %sproposal.md /tmp/" % self.cd, "ls -la", "mvn -q test"):
            self.assertIsNone(self.blocked(c), c)

    def test_evaluator_git(self):
        self.assertIsNotNone(self.blocked("git commit -m x", "qa-evaluator"))
        self.assertIsNotNone(self.blocked("git checkout main", "code-reviewer"))
        self.assertIsNone(self.blocked("git diff HEAD~1", "code-reviewer"))
        self.assertIsNotNone(self.blocked("echo x > src/A.java", "code-reviewer"))
        self.assertIsNone(self.blocked("git commit -m x", "implementation-generator"))

    def test_odd_input(self):
        for c in ("echo 'unbalanced", "", "   ", ">", "&& ||", "sh -c"):
            bash_guard.pre_tool(shell(self.root, c))  # must not raise
        self.assertIsNone(bash_guard.pre_tool({"kind": "shell", "command": "ls", "paths": [], "cwd": ""}))


class NormalizeTest(unittest.TestCase):
    def test_agent_and_codex_patch(self):
        ev = hook.normalize({"tool_name": "Write", "tool_input": {"file_path": "a"},
                             "agent_type": "reins:spec-evaluator"}, "claude")
        self.assertEqual(ev["agent"], "spec-evaluator")
        patch = "*** Begin Patch\n*** Update File: .openspec/changes/c/proposal.md\n*** End Patch"
        ev = hook.normalize({"tool_name": "apply_patch", "tool_input": {"command": patch}}, "codex")
        self.assertEqual((ev["kind"], ev["paths"], ev["command"]), ("edit", [".openspec/changes/c/proposal.md"], ""))


def fake_gate(findings):
    mod = types.ModuleType("spec_driven.gates.g5")
    mod.check = lambda ctx: [gates.Finding(**f) for f in findings]
    return mock.patch.dict(sys.modules, {"spec_driven.gates.g5": mod})


BLOCKS = [dict(level="BLOCK", check="marker", reason="缺少 generated-by 标记", evidence="spec-review.md"),
          dict(level="BLOCK", check="marker", reason="降级措辞", evidence="主线自评"),
          dict(level="BLOCK", check="other", reason="x")]


class WaiveFlowTest(unittest.TestCase):
    """UserPromptSubmit phrase -> grant -> `spec-driven waive` in a real temp repo."""

    def prompt(self, root, text):
        return policies.prompt({"prompt": text, "cwd": str(root)}, [])

    def test_phrase_then_waive(self):
        with java_repo() as root:
            cli("new", "waive-change")
            with fake_gate(BLOCKS):
                code, out = cli("waive", "5", "marker", "--reason", "用户：先上线")
                self.assertEqual(code, 1)
                self.assertIn("确认放行 waive-change 5 marker", out)
                note = self.prompt(root, "确认放行 waive-change 5 marker")
                self.assertIn("2 项", note)
                code, out = cli("waive", "5", "marker", "--reason", "用户：先上线")
                self.assertEqual(code, 0, out)
                self.assertEqual(out.count("[WAIVED]"), 2)
                d = root / ".openspec/changes/waive-change"
                self.assertEqual({w.check for w in retro.waivers(d)}, {"marker"})
                self.assertEqual(len(retro.waivers(d)), 2)
                self.assertEqual(cli("waive", "5", "marker", "--reason", "again")[0], 1)   # nothing live
                self.assertEqual(cli("waive", "5", "other", "--reason", "x")[0], 1)        # no grant

    def test_grant_bound_to_content(self):
        with java_repo() as root:
            cli("new", "bound-change")
            with fake_gate(BLOCKS):
                self.prompt(root, "确认放行 bound-change 5 marker")
            changed = [dict(BLOCKS[0], evidence="新内容")]
            with fake_gate(changed):
                self.assertEqual(cli("waive", "5", "marker", "--reason", "x")[0], 1)

    def test_no_grant_for_non_live_or_unknown(self):
        with java_repo() as root:
            cli("new", "none-change")
            with fake_gate([]):
                self.assertIn("没有检查项", self.prompt(root, "确认放行 none-change 5 marker"))
            self.assertIn("没有进行中", self.prompt(root, "确认放行 ghost-change 5 marker"))
            self.assertIn("没有 gate-42", self.prompt(root, "确认放行 none-change 42 marker"))
            self.assertIsNone(self.prompt(root, "放行吧"))
            self.assertEqual(list(grants.grants_dir().glob("*.json")) if grants.grants_dir().exists() else [], [])

    def test_downgrade_grant(self):
        with java_repo() as root:
            cli("new", "down-change")
            self.assertIn("不是降档", self.prompt(root, "确认降档 down-change S"))   # tier not confirmed yet
            cli("complexity", "set", "L")
            self.assertIn("从 L 降到 S", self.prompt(root, "确认降档 down-change S"))
            self.assertEqual(cli("complexity", "set", "S", "--downgrade", "--reason", "用户：只改查询")[0], 0)
            self.assertIn("| 降档 |", (root / ".openspec/changes/down-change/retrospective.md").read_text(encoding="utf-8"))


class GateRouterTest(Base):
    def test_trigger_runs_current_gate(self):
        fake = types.ModuleType("spec_driven.gates.g4")
        fake.check = lambda ctx: [gates.Finding("BLOCK", "sc-linked", "T3 没有关联 SC")]
        with mock.patch.dict(sys.modules, {"spec_driven.gates.g4": fake}):
            note = gate_router.prompt({"prompt": "继续，进入 Phase 5", "cwd": str(self.root)})
        self.assertIn("gate-4 拦截", note)
        self.assertIn("T3 没有关联 SC", note)
        self.assertIsNone(gate_router.prompt({"prompt": "帮我看看这个函数", "cwd": str(self.root)}))

    def test_silent_when_unimplemented_or_no_project(self):
        with mock.patch("spec_driven.gates.evaluate", side_effect=NotImplementedError):
            self.assertIsNone(gate_router.prompt({"prompt": "继续", "cwd": str(self.root)}))
        self.assertIsNone(gate_router.prompt({"prompt": "继续", "cwd": self.tmp.name}))


if __name__ == "__main__":
    unittest.main()
