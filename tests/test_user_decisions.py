"""T11: uat / scope / deploy skip in a throwaway git repo (architecture.md §4.5)."""

import json
import unittest
from unittest import mock

from tests import CLI_LIB  # noqa: F401
from tests.support_t2 import cli, java_repo
from spec_driven import config, gates, grants, meta, policies, retro
from spec_driven.errors import ERROR, OK
from spec_driven.project import Project


def meta_path(root, change):
    return root / ".openspec/changes" / change / ".meta.json"


def read_meta(root, change):
    return json.loads(meta_path(root, change).read_text(encoding="utf-8"))


def set_meta(root, change, **fields):
    m = read_meta(root, change)
    m.update(fields)
    meta_path(root, change).write_text(json.dumps(m), encoding="utf-8")


def at_phase(root, change, phase):
    m = read_meta(root, change)
    for p in meta.PHASES[:meta.PHASES.index(phase)]:
        m["phaseStatus"][p] = "passed"
    m["phaseStatus"][phase] = "in_progress"
    m["phase"] = phase
    meta_path(root, change).write_text(json.dumps(m), encoding="utf-8")


def prompt(root, text):
    return policies.prompt({"prompt": text, "cwd": str(root)}, [])


class UatTest(unittest.TestCase):
    def setUp(self):
        self.ctx = java_repo()
        self.root = self.ctx.__enter__()
        cli("new", "uat-change")
        self.dir = self.root / ".openspec/changes/uat-change"
        (self.dir / "spec.md").write_text("### SC-a-001: x\n", encoding="utf-8")
        (self.dir / "qa-report.md").write_text("qa v1\n", encoding="utf-8")
        at_phase(self.root, "uat-change", "8.9")

    def tearDown(self):
        self.ctx.__exit__(None, None, None)

    def test_accept_needs_the_users_phrase(self):
        code, out = cli("uat", "accept")
        self.assertEqual(code, ERROR)
        self.assertIn("确认验收 uat-change", out)
        self.assertIn("验收通过", prompt(self.root, "确认验收 uat-change"))
        code, out = cli("uat", "accept")
        self.assertEqual(code, OK, out)
        m = read_meta(self.root, "uat-change")
        self.assertTrue(m["uatAccepted"])
        self.assertTrue(m["uatAcceptedAt"])
        self.assertIn("| 通过 |", (self.dir / "retrospective.md").read_text(encoding="utf-8"))
        self.assertTrue(retro.verify(self.dir))

    def test_grant_bound_to_spec_and_qa_report(self):
        prompt(self.root, "确认验收 uat-change")
        (self.dir / "qa-report.md").write_text("qa v2\n", encoding="utf-8")
        self.assertEqual(cli("uat", "accept")[0], ERROR)
        self.assertFalse(read_meta(self.root, "uat-change")["uatAccepted"])

    def test_wrong_phase_and_no_grant_outside_8_9(self):
        at_phase(self.root, "uat-change", "8")
        self.assertIn("只在 Phase 8.9", prompt(self.root, "确认验收 uat-change"))
        self.assertFalse(grants.grants_dir().exists() and list(grants.grants_dir().glob("*.json")))
        self.assertEqual(cli("uat", "accept")[0], ERROR)

    def test_model_cannot_accept_without_user_message(self):
        # A phrase that is not the whole prompt, or arrives only as model text, issues nothing.
        self.assertIsNone(prompt(self.root, "用户说：确认验收 uat-change"))
        self.assertEqual(cli("uat", "accept")[0], ERROR)

    def test_gate_8_9_sees_acceptance(self):
        prompt(self.root, "确认验收 uat-change")
        cli("uat", "accept")
        m = meta.load(self.dir)
        ctx = gates.GateContext(Project(self.root), "uat-change", self.dir, m, config.load(Project(self.root)))
        try:
            _, code = gates.evaluate("8.9", ctx)
        except NotImplementedError:
            self.skipTest("gate 8.9 (T4) not merged yet")
        self.assertEqual(code, OK)

    def test_reject_records_and_rolls_back(self):
        code, out = cli("uat", "reject", "--phase", "3", "--reason", "用户：导出字段少了备注")
        self.assertEqual(code, OK, out)
        m = read_meta(self.root, "uat-change")
        self.assertEqual((m["phase"], m["phaseStatus"]["4"], m["uatAccepted"]), ("3", "stale", False))
        text = (self.dir / "retrospective.md").read_text(encoding="utf-8")
        self.assertIn("需要修改（回退到 Phase 3）", text)
        self.assertIn("导出字段少了备注", text)

    def test_reject_rejections(self):
        self.assertEqual(cli("uat", "reject", "--reason", "x")[0], ERROR)           # no phase
        self.assertEqual(cli("uat", "reject", "--phase", "9", "--reason", "x")[0], ERROR)
        self.assertEqual(cli("uat", "reject", "--phase", "3")[0], ERROR)           # no reason
        self.assertFalse((self.dir / "retrospective.md").exists())


class ScopeTest(unittest.TestCase):
    def test_small_bugfix_skips_design_phases(self):
        with java_repo() as root:
            cli("new", "--mode", "bugfix", "--slug", "npe on export")
            change = Project(root).active_changes()[0]
            self.assertIn("尚未评估", cli("scope", "show")[1])
            self.assertEqual(cli("scope", "set", "--files", "1")[0], ERROR)      # still Phase 0
            at_phase(root, change, "1")
            code, out = cli("scope", "set", "--files", "1")
            self.assertEqual(code, OK, out)
            self.assertIn("Phase 2：跳过", out)
            self.assertEqual(read_meta(root, change)["bugfixScope"],
                             {"files": 1, "crossService": False, "ddl": False, "publicApi": False})
            with mock.patch("spec_driven.gates.evaluate", return_value=([], OK)):
                cli("advance")
            m = read_meta(root, change)
            self.assertEqual((m["phase"], m["phaseStatus"]["2"], m["phaseStatus"]["3"]), ("4", "skipped", "skipped"))

    def test_ddl_keeps_phase_3(self):
        with java_repo() as root:
            cli("new", "--mode", "bugfix", "--slug", "missing index")
            change = Project(root).active_changes()[0]
            at_phase(root, change, "1")
            out = cli("scope", "set", "--files", "2", "--ddl")[1]
            self.assertIn("Phase 2：执行", out)
            self.assertIn("Phase 3：执行", out)

    def test_feature_mode_and_missing_files_rejected(self):
        with java_repo() as root:
            cli("new", "feature-change")
            at_phase(root, "feature-change", "1")
            self.assertEqual(cli("scope", "set", "--files", "1")[0], ERROR)
            self.assertIn("bugfix", cli("scope", "set", "--files", "1")[1])


class DeploySkipTest(unittest.TestCase):
    def test_skip_moves_to_8_9_and_gate_passes(self):
        with java_repo() as root:
            cli("new", "deploy-change")
            at_phase(root, "deploy-change", "8.5")
            code, out = cli("deploy", "skip", "--reason", "用户：本地没有测试库")
            self.assertEqual(code, OK, out)
            m = read_meta(root, "deploy-change")
            self.assertEqual((m["phaseStatus"]["8.5"], m["phase"], m["phaseStatus"]["8.9"]),
                             ("skipped", "8.9", "in_progress"))
            d = root / ".openspec/changes/deploy-change"
            self.assertIn("本地没有测试库", (d / "retrospective.md").read_text(encoding="utf-8"))
            ctx = gates.GateContext(Project(root), "deploy-change", d, meta.load(d), config.load(Project(root)))
            findings, code = gates.evaluate("8.5", ctx)
            self.assertEqual((code, findings[0].check), (OK, "skipped"))

    def test_rejections(self):
        with java_repo() as root:
            cli("new", "deploy-bad")
            self.assertEqual(cli("deploy", "skip", "--reason", "x")[0], ERROR)     # not in 8.5
            at_phase(root, "deploy-bad", "8.5")
            self.assertEqual(cli("deploy", "skip", "--reason", "  ")[0], ERROR)


if __name__ == "__main__":
    unittest.main()
