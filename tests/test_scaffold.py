"""T18: `spec-driven scaffold` generates only the current phase's artifact, never overwrites."""

import unittest

from tests import CLI_LIB  # noqa: F401
from tests.support_t2 import cli, git, java_repo
from spec_driven import mdparse, meta
from spec_driven.errors import ERROR, OK

# artifact -> (phase, file, ALIASES keys its gate looks up; see the alias index in docs/dev/tasks.md)
CASES = {
    "bugfix-analysis": ("1", "bugfix-analysis.md",
                        ["basic-info", "evidence", "root-cause", "fix-plan", "change-points", "impact",
                         "complexity-assessment"]),
    "design": ("2", "design.md",
               ["background", "current-system", "alternatives", "final-choice", "detailed-design", "risks",
                "stress-test", "implementation-plan"]),
    "spec": ("3", "spec.md",
             ["interface-contract", "data-model", "table-structure", "indexes", "constraints", "migrations"]),
    "tasks": ("4", "tasks.md",
              ["foundation", "domain-layer", "application-layer", "adapter-layer", "test-layer"]),
    "implementation-log": ("6", "implementation-log.md",
                           ["change-scope", "red", "green", "refactor", "build", "coverage", "commits"]),
    "deploy-report": ("8.5", "deploy-report.md",
                      ["deployment-info", "startup-result", "deployment-errors", "manual-acceptance",
                       "conclusion"]),
}


def make_change(root, name, mode="feature", phase="0"):
    change_dir = root / ".openspec/changes" / name
    change_dir.mkdir(parents=True)
    m = meta.new(name, mode, "main", git(root, "rev-parse", "HEAD"))
    m["phase"] = phase
    meta.save(change_dir, m)
    return change_dir


def set_phase(change_dir, phase):
    meta.update(change_dir, lambda m: m.__setitem__("phase", phase))


class ScaffoldTest(unittest.TestCase):
    def setUp(self):
        self.ctx = java_repo()
        self.root = self.ctx.__enter__()

    def tearDown(self):
        self.ctx.__exit__(None, None, None)

    def test_each_artifact_in_its_phase_has_every_gate_section(self):
        for mode in ("feature", "bugfix"):
            change = "demo-%s" % mode
            change_dir = make_change(self.root, change, mode)
            for artifact, (phase, name, keys) in CASES.items():
                if artifact == "bugfix-analysis" and mode != "bugfix":
                    continue
                with self.subTest(mode=mode, artifact=artifact):
                    set_phase(change_dir, phase)
                    code, out = cli("scaffold", artifact, "--change", change)
                    self.assertEqual(code, OK, out)
                    self.assertIn(".openspec/changes/%s/%s" % (change, name), out)
                    text = (change_dir / name).read_text(encoding="utf-8")
                    self.assertNotIn("<change-name>", text)
                    if artifact != "spec":  # the spec title names the capability, not the change
                        self.assertIn(change, text.splitlines()[0])
                    root = mdparse.parse(text)
                    self.assertEqual([k for k in keys if mdparse.find(root, k) is None], [])
            leftovers = [p.name for p in change_dir.iterdir() if p.name.endswith(".tmp")]
            self.assertEqual(leftovers, [])

    def test_other_phases_are_refused(self):
        change_dir = make_change(self.root, "demo-change", phase="4")
        code, out = cli("scaffold", "design")
        self.assertEqual(code, ERROR)
        self.assertIn("已冻结", out)
        self.assertIn("Phase 2", out)
        code, out = cli("scaffold", "implementation-log")
        self.assertEqual(code, ERROR)
        self.assertIn("还没到 Phase 6", out)
        self.assertFalse((change_dir / "design.md").exists())
        self.assertFalse((change_dir / "implementation-log.md").exists())
        self.assertEqual(cli("scaffold", "tasks")[0], OK)

    def test_bugfix_analysis_only_for_bugfix(self):
        change_dir = make_change(self.root, "demo-change", phase="1")
        code, out = cli("scaffold", "bugfix-analysis")
        self.assertEqual(code, ERROR)
        self.assertIn("bugfix", out)
        self.assertFalse((change_dir / "bugfix-analysis.md").exists())

    def test_existing_file_is_not_overwritten(self):
        change_dir = make_change(self.root, "demo-change", phase="2")
        (change_dir / "design.md").write_text("我的草稿\n", encoding="utf-8")
        code, out = cli("scaffold", "design")
        self.assertEqual(code, ERROR)
        self.assertIn("已存在", out)
        self.assertEqual((change_dir / "design.md").read_text(encoding="utf-8"), "我的草稿\n")
        self.assertEqual(cli("scaffold", "design")[0], ERROR)

    def test_change_must_be_named_when_ambiguous(self):
        make_change(self.root, "demo-one", phase="2")
        other = make_change(self.root, "demo-two", phase="2")
        self.assertEqual(cli("scaffold", "design")[0], ERROR)
        self.assertEqual(cli("scaffold", "design", "--change", "demo-two")[0], OK)
        self.assertTrue((other / "design.md").is_file())


if __name__ == "__main__":
    unittest.main()
