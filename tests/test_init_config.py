"""T5 initialization keeps user configuration and never expands an existing baseline."""

import contextlib
import io
import json
import os
from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "reinsdev-plugin/skills/spec-driven-dev/scripts/lib"))
from spec_driven import java
from spec_driven.commands import init_config
from spec_driven.project import Project


class InitConfigTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.project = Project(self.root)
        (self.root / "pom.xml").write_text("<project/>", encoding="utf-8")
        self.env = mock.patch.dict(os.environ, {"REINS_HOME": str(self.root / "reins-home")})
        self.env.start()
        self.addCleanup(self.env.stop)
        self.here = mock.patch.object(Project, "here", return_value=self.project)
        self.here.start()
        self.addCleanup(self.here.stop)
        self.args = SimpleNamespace(java=True, dry_run=False)
        self.issue = java.Violation("pmd", "Unused", "A.java", 1, "unused")

    def run_config(self, values=None, errors=None):
        with mock.patch("spec_driven.java.run_quality", return_value=(values or [], errors or {})) as runner:
            with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
                try:
                    result = init_config.run(self.args)
                except SystemExit as exc:
                    result = exc.code if isinstance(exc.code, int) else 1
        return result, runner

    def test_initialization_writes_quality_and_real_baseline(self):
        result, runner = self.run_config([self.issue])
        self.assertEqual(0, result)
        config = json.loads(self.project.config_path.read_text(encoding="utf-8"))
        self.assertEqual(set(java.CHECKS), set(config["quality"]))
        self.assertEqual([self.issue], java.load_baseline(self.project.quality_baseline))
        self.assertTrue(runner.call_args.kwargs["initialize"])

    def test_preserves_unrelated_configuration_and_existing_commands(self):
        self.project.openspec.mkdir()
        config = {"test": {"coverage": {"diff_threshold": 93}}, "quality": {"pmd": {"command": ["custom", "pmd"], "report_path": "custom.xml"}}}
        self.project.config_path.write_text(json.dumps(config), encoding="utf-8")
        self.assertEqual(0, self.run_config()[0])
        written = json.loads(self.project.config_path.read_text(encoding="utf-8"))
        self.assertEqual(config["test"], written["test"])
        self.assertEqual(config["quality"]["pmd"], written["quality"]["pmd"])

    def test_custom_sql_command_is_not_reinterpreted_as_resource_scanner(self):
        self.project.openspec.mkdir()
        custom = {"command": ["custom", "sql-check"], "report_path": "sql.json"}
        self.project.config_path.write_text(json.dumps({"quality": {"sqlfluff": custom}}), encoding="utf-8")
        defaults = java.quality_defaults(self.root)
        defaults["sqlfluff"]["source"] = "java-resources"
        with mock.patch("spec_driven.java.quality_defaults", return_value=defaults):
            self.assertEqual(0, self.run_config()[0])
        written = json.loads(self.project.config_path.read_text(encoding="utf-8"))
        self.assertIsNone(written["quality"]["sqlfluff"].get("source"))

    def test_failure_does_not_publish_partial_files(self):
        result, _ = self.run_config(errors={"spotbugs": "命令不可用"})
        self.assertEqual(1, result)
        self.assertFalse(self.project.config_path.exists())
        self.assertFalse(self.project.quality_baseline.exists())

    def test_dry_run_runs_no_commands_and_writes_nothing(self):
        self.args.dry_run = True
        result, runner = self.run_config()
        self.assertEqual(0, result)
        runner.assert_not_called()
        self.assertFalse(self.project.openspec.exists())

    def test_reinitialization_does_not_adopt_new_debt(self):
        self.assertEqual(0, self.run_config([self.issue])[0])
        before = self.project.quality_baseline.read_bytes()
        newer = java.Violation("pmd", "NewRule", "B.java", 2, "new")
        result, runner = self.run_config([self.issue, newer])
        self.assertEqual(1, result)
        self.assertEqual(before, self.project.quality_baseline.read_bytes())
        self.assertFalse(runner.call_args.kwargs["initialize"])
        self.assertEqual(0, self.run_config([])[0])
        self.assertEqual(before, self.project.quality_baseline.read_bytes())

    def test_deleted_initialized_baseline_cannot_adopt_new_debt(self):
        self.assertEqual(0, self.run_config([self.issue])[0])
        self.project.quality_baseline.unlink()
        newer = java.Violation("pmd", "NewRule", "B.java", 2, "new")
        result, runner = self.run_config([newer])
        self.assertEqual(1, result)
        runner.assert_not_called()
        self.assertFalse(self.project.quality_baseline.exists())

    def test_invalid_existing_config_and_baseline_are_not_overwritten(self):
        self.project.openspec.mkdir()
        for text in ("{", "[]", '{"quality":false}'):
            with self.subTest(text=text):
                self.project.config_path.write_text(text, encoding="utf-8")
                self.assertEqual(1, self.run_config()[0])
                self.assertEqual(text, self.project.config_path.read_text(encoding="utf-8"))
        self.project.config_path.write_text("{}", encoding="utf-8")
        self.project.quality_baseline.write_text("{}", encoding="utf-8")
        self.assertEqual(1, self.run_config()[0])
        self.assertEqual("{}", self.project.quality_baseline.read_text(encoding="utf-8"))

    def test_real_commands_initialize_then_block_new_debt(self):
        from spec_driven.gates import GateContext, g6_7
        fixtures = ROOT / "tests/fixtures/t5/java"
        self.project.openspec.mkdir()
        command_script = self.root / "quality_tool.py"
        command_script.write_text("import sys\nfrom pathlib import Path\nPath(sys.argv[2]).write_text(Path(sys.argv[1]).read_text(encoding='utf-8'), encoding='utf-8')\n", encoding="utf-8")
        config = {"quality": {}}
        for check in java.CHECKS:
            suffix = ".json" if check == "sqlfluff" else ".xml"
            payload = self.root / (check + "-payload" + suffix)
            payload.write_text((fixtures / (check + "-pass" + suffix)).read_text(encoding="utf-8"), encoding="utf-8")
            config["quality"][check] = {"command": [sys.executable, str(command_script), str(payload), check + suffix],
                                         "report_path": check + suffix, "source": None}
        self.project.config_path.write_text(json.dumps(config), encoding="utf-8")
        with contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(0, init_config.run(self.args))
        self.assertEqual([], java.load_baseline(self.project.quality_baseline))
        change = self.project.change_dir("e2e-quality")
        change.mkdir(parents=True)
        config = json.loads(self.project.config_path.read_text(encoding="utf-8"))
        ctx = GateContext(self.project, "e2e-quality", change, {"complexity": "S"}, config)
        self.assertEqual([], g6_7.check(ctx))
        (self.root / "pmd-payload.xml").write_text((fixtures / "pmd-fail.xml").read_text(encoding="utf-8"), encoding="utf-8")
        findings = g6_7.check(ctx)
        self.assertEqual(["pmd"], [f.check for f in findings])
        self.assertTrue(findings[0].locked)
        self.assertEqual([], java.load_baseline(self.project.quality_baseline))
        self.assertIn("## 新增违规", (change / "static-analysis-report.md").read_text(encoding="utf-8"))

    def test_non_java_project_fails_without_writes(self):
        (self.root / "pom.xml").unlink()
        self.assertEqual(1, self.run_config()[0])
        self.assertFalse(self.project.openspec.exists())


if __name__ == "__main__":
    unittest.main()
