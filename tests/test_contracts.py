"""Contract tests (owner T0): the module layout and shared behaviour every task
relies on. A task that needs to change something here changes docs/dev/architecture.md
in the same PR and says so."""

import importlib
import inspect
import sys
import tempfile
import types
import unittest
from pathlib import Path
from unittest import mock

from tests import CLI_LIB  # noqa: F401
from spec_driven import gates, meta, policies
from spec_driven.commands import COMMANDS
from spec_driven.errors import BLOCK, OK, WARN
from spec_driven.project import Project
from spec_driven.retro import Waiver


class LayoutTest(unittest.TestCase):
    def test_every_command_module_has_register_and_run(self):
        for name in COMMANDS:
            mod = importlib.import_module("spec_driven.commands." + name)
            self.assertTrue(callable(getattr(mod, "register", None)), name)
            self.assertTrue(callable(getattr(mod, "run", None)), name)

    def test_every_gate_has_a_check(self):
        for g in meta.GATES:
            mod = importlib.import_module("spec_driven.gates." + gates.module_name(g))
            self.assertEqual(list(inspect.signature(mod.check).parameters), ["ctx"], g)

    def test_every_policy_exposes_its_hook(self):
        for chain, fn in ((policies.PRE_TOOL, "pre_tool"), (policies.PROMPT, "prompt")):
            for name in chain:
                mod = importlib.import_module("spec_driven.policies." + name)
                self.assertTrue(callable(getattr(mod, fn, None)), name)

    def test_phases_are_gates(self):
        self.assertTrue(set(meta.PHASES) <= set(meta.GATES))


def _ctx(tmp, meta_dict=None, cfg=None):
    root = Path(tmp)
    return gates.GateContext(Project(root), "demo-change", root, meta_dict or {"skipped": {}}, cfg or {"gates": {}})


class GateFrameworkTest(unittest.TestCase):
    """Exercises gates.evaluate with a fake gate module standing in for gate 1."""

    def run_gate(self, findings, meta_dict=None, cfg=None, waivers=(), strict=False):
        fake = types.ModuleType("spec_driven.gates.g1")
        fake.check = lambda ctx: [gates.Finding(**f) for f in findings]
        with tempfile.TemporaryDirectory() as tmp, \
                mock.patch.dict(sys.modules, {"spec_driven.gates.g1": fake}), \
                mock.patch("spec_driven.retro.waivers", return_value=list(waivers)):
            ctx = _ctx(tmp, meta_dict, cfg)
            ctx.strict = strict
            return gates.evaluate("1", ctx)

    def test_exit_codes(self):
        self.assertEqual(self.run_gate([])[1], OK)
        self.assertEqual(self.run_gate([dict(level="WARN", check="a", reason="r")])[1], WARN)
        self.assertEqual(self.run_gate([dict(level="BLOCK", check="a", reason="r")])[1], BLOCK)
        self.assertEqual(self.run_gate([dict(level="WARN", check="a", reason="r")], strict=True)[1], BLOCK)

    def test_skipped_phase_passes_without_running(self):
        f, code = self.run_gate([dict(level="BLOCK", check="a", reason="r")], meta_dict={"skipped": {"1": "S 档"}})
        self.assertEqual((code, f[0].check), (OK, "skipped"))

    def test_config_lowers_unlocked_block_only(self):
        cfg = {"gates": {"1": {"level": "warn"}}}
        f, code = self.run_gate([dict(level="BLOCK", check="a", reason="r")], cfg=cfg)
        self.assertEqual((code, f[0].level), (WARN, "WARN"))
        f, code = self.run_gate([dict(level="BLOCK", check="a", reason="r", locked=True)], cfg=cfg)
        self.assertEqual(code, BLOCK)
        f, code = self.run_gate([dict(level="BLOCK", check="a", reason="r")], cfg={"gates": {"1": {"level": "off"}}})
        self.assertEqual((code, f), (OK, []))

    def test_waiver_matches_fingerprint_only(self):
        finding = dict(level="BLOCK", check="coverage", reason="r", evidence="62%")
        fp = gates.fingerprint("1", gates.Finding(**finding))
        w = Waiver("t", "1", "coverage", "c", "why", "me", fp)
        f, code = self.run_gate([finding], waivers=[w])
        self.assertEqual((code, f[0].waived), (OK, True))
        changed = dict(finding, evidence="55%")
        self.assertEqual(self.run_gate([changed], waivers=[w])[1], BLOCK)

    def test_fingerprint_ignores_location(self):
        a = gates.Finding("BLOCK", "x", "r", location="spec.md:3", evidence="e")
        b = gates.Finding("BLOCK", "x", "r", location="spec.md:9", evidence="e")
        self.assertEqual(gates.fingerprint("3", a), gates.fingerprint("3", b))


class PolicyChainTest(unittest.TestCase):
    def test_broken_policy_fails_open_and_is_recorded(self):
        broken = types.ModuleType("spec_driven.policies.spec_gate")

        def boom(ev):
            raise RuntimeError("bug")
        broken.pre_tool = boom
        ev = {"paths": ["a.txt"], "command": ""}
        errors = []
        with mock.patch.dict(sys.modules, {"spec_driven.policies.spec_gate": broken}):
            self.assertIsNone(policies.pre_tool(ev, errors))
        self.assertTrue(errors and "spec_gate" in errors[0])

    def test_probe_still_blocks(self):
        ev = {"paths": [], "command": "touch x.reins-probe-block"}
        self.assertIsNotNone(policies.pre_tool(ev, []))


class CliTest(unittest.TestCase):
    def test_unavailable_contract(self):
        from spec_driven.errors import ERROR, unavailable
        with mock.patch("sys.stderr") as err:
            self.assertEqual(unavailable("x"), ERROR)
        self.assertIn("该能力不可用", "".join(c.args[0] for c in err.write.call_args_list))

    def test_every_command_parses_help(self):
        from spec_driven.cli import main
        for argv in (["--help"], ["gate", "--help"]):
            with self.assertRaises(SystemExit) as cm, mock.patch("sys.stdout"):
                main(argv)
            self.assertEqual(cm.exception.code, 0)

if __name__ == "__main__":
    unittest.main()
