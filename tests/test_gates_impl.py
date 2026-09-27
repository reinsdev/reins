"""T5 gate fixtures exercise real commits and Java report files."""

import copy
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "reinsdev-plugin/skills/spec-driven-dev/scripts/lib"))
from spec_driven import gitutil
from spec_driven.gates import GateContext
from spec_driven.gates import g6, g6_5, g6_7
from spec_driven.project import Project

FIXTURES = ROOT / "tests/fixtures/t5/gates"


class GateProject(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.env = mock.patch.dict(os.environ, {"REINS_HOME": str(self.root / "reins-home")})
        self.env.start()
        self.addCleanup(self.env.stop)
        self.project = Project(self.root)
        self.change = self.project.change_dir("demo-change")
        self.change.mkdir(parents=True)
        gitutil.git(["init"], self.root)
        gitutil.git(["config", "user.name", "T5 Fixture"], self.root)
        gitutil.git(["config", "user.email", "t5@example.invalid"], self.root)
        self.write("pom.xml", "<project><modelVersion>4.0.0</modelVersion></project>\n")
        self.write("src/main/java/demo/A.java", "package demo;\nclass A {\n int value() { return 0; }\n}\n")
        self.commit("baseline", ["pom.xml", "src"])
        self.base = gitutil.head(self.root)
        self.write("src/test/java/demo/ATest.java", "package demo;\nclass ATest {}\n")
        self.commit("RED: value\n\nTask-Id: T1\nTDD-Phase: RED", ["src/test"])
        self.write("src/main/java/demo/A.java", "package demo;\nclass A {\n int value() { return 1; }\n}\n")
        self.commit("GREEN: value\n\nTask-Id: T1\nTDD-Phase: GREEN", ["src/main"])
        for name in ("tasks.md", "implementation-log.md"):
            (self.change / name).write_text((FIXTURES / name).read_text(encoding="utf-8"), encoding="utf-8")
        self.write("target/surefire-reports/TEST-demo.ATest.xml", (FIXTURES / "surefire.xml").read_text(encoding="utf-8"))
        self.write("target/site/jacoco/jacoco.xml", (FIXTURES / "jacoco.xml").read_text(encoding="utf-8"))
        self.ctx = GateContext(self.project, "demo-change", self.change,
                               {"baseCommit": self.base, "complexity": "M", "mode": "feature", "qa_mode": "full"},
                               {"test": {"coverage": {"diff_threshold": 80}}})

    def write(self, name, text):
        path = self.root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
        return path

    def commit(self, message, paths):
        gitutil.git(["add", "--"] + paths, self.root)
        gitutil.git(["commit", "-m", message], self.root)

    def checks(self, gate=g6):
        return {item.check: item for item in gate.check(self.ctx)}


class TestGate6(GateProject):
    def test_valid_fixture(self):
        self.assertEqual([], g6.check(self.ctx))

    def test_every_check_has_passing_and_failing_fixture(self):
        cases = json.loads((FIXTURES / "cases.json").read_text(encoding="utf-8"))
        for case in cases:
            with self.subTest(**case):
                isolated = TestGate6(methodName="test_valid_fixture")
                isolated.setUp()
                try:
                    self.assertNotIn(case["check"], isolated.checks())
                    isolated.mutate(case["mutation"])
                    finding = isolated.checks()[case["check"]]
                    self.assertEqual("BLOCK", finding.level)
                    self.assertTrue(finding.evidence)
                finally:
                    isolated.doCleanups()

    def mutate(self, name):
        report = self.root / "target/surefire-reports/TEST-demo.ATest.xml"
        log = self.change / "implementation-log.md"
        if name == "no_test_changes":
            self.ctx.meta["baseCommit"] = gitutil.git(["rev-parse", "HEAD~1"], self.root)
        elif name in ("zero_tests", "failed_tests", "skipped_tests"):
            text = report.read_text(encoding="utf-8")
            if name == "zero_tests":
                text = '<testsuite name="empty" tests="0" failures="0" errors="0" skipped="0"/>'
            elif name == "failed_tests":
                text = text.replace('failures="0"', 'failures="1"').replace('time="0.01"/>', 'time="0.01"><failure message="bad"/></testcase>')
            else:
                text = text.replace('skipped="0"', 'skipped="1"').replace('time="0.01"/>', 'time="0.01"><skipped/></testcase>')
            report.write_text(text, encoding="utf-8")
        elif name == "missing_report":
            report.unlink()
        elif name == "skip_command":
            self.ctx.config["test"]["command"] = "mvn -o test -DskipTests"
        elif name == "pom_skip":
            self.write("pom.xml", "<project><build><plugins><plugin><artifactId>maven-surefire-plugin</artifactId><configuration><skip>true</skip></configuration></plugin></plugins></build></project>")
        elif name == "missing_log":
            log.unlink()
        elif name == "compile_as_test":
            log.write_text(log.read_text(encoding="utf-8").replace("mvn -o test | 0", "mvn -o compile | 0"), encoding="utf-8")
        elif name == "failed_build":
            log.write_text(log.read_text(encoding="utf-8").replace("mvn -o verify | 0", "mvn -o verify | 1"), encoding="utf-8")
        elif name == "uncovered":
            path = self.root / "target/site/jacoco/jacoco.xml"
            path.write_text(path.read_text(encoding="utf-8").replace('mi="0" ci="2"', 'mi="2" ci="0"'), encoding="utf-8")
        elif name == "missing_coverage":
            (self.root / "target/site/jacoco/jacoco.xml").unlink()
        elif name == "missing_trailer":
            self.write("src/main/java/demo/B.java", "class B {}\n")
            self.commit("implementation without trailer", ["src/main/java/demo/B.java"])
        elif name == "late_red":
            self.ctx.meta["baseCommit"] = gitutil.git(["rev-parse", "HEAD~1"], self.root)
            self.write("src/test/java/demo/BTest.java", "class BTest {}\n")
            self.commit("late test\n\nTask-Id: T1\nTDD-Phase: RED", ["src/test/java/demo/BTest.java"])
        elif name == "outside_scope":
            self.write("unrelated.txt", "outside scope\n")
            self.commit("unrelated\n\nTask-Id: T1", ["unrelated.txt"])
        elif name == "missing_integration":
            self.ctx.config["test"]["integration"] = {"required": True}
        else:
            self.fail("unknown mutation %s" % name)

    def test_no_tests_warn_for_small_feature_but_block_bugfix(self):
        self.mutate("no_test_changes")
        self.ctx.meta["complexity"] = "S"
        self.assertEqual("WARN", self.checks()["test-files"].level)
        self.ctx.meta["mode"] = "bugfix"
        self.assertEqual("BLOCK", self.checks()["test-files"].level)

    def test_missing_red_warns_but_late_red_blocks(self):
        self.mutate("no_test_changes")
        self.assertEqual("WARN", self.checks()["red-before-green"].level)
        self.mutate("late_red")
        self.assertEqual("BLOCK", self.checks()["red-before-green"].level)

    def test_coverage_evidence_contains_value_and_uncovered_lines(self):
        self.mutate("uncovered")
        first = self.checks()["coverage"]
        self.assertIn("0", first.evidence)
        self.assertIn("src/main/java/demo/A.java:3", first.evidence)
        log = self.change / "implementation-log.md"
        log.write_text("\n\n" + log.read_text(encoding="utf-8"), encoding="utf-8")
        self.assertEqual(first.evidence, self.checks()["coverage"].evidence)

    def test_task_selection_requires_existing_task(self):
        self.ctx.extra["task"] = "T9"
        self.assertEqual("BLOCK", self.checks()["implementation-log"].level)

    def test_invalid_configuration_and_missing_base_fail_closed(self):
        self.ctx.config["test"]["coverage"]["diff_threshold"] = "invalid"
        self.assertEqual("BLOCK", self.checks()["coverage"].level)
        self.ctx.meta.pop("baseCommit")
        self.assertEqual("BLOCK", self.checks()["git-evidence"].level)

    def test_full_build_is_not_just_unit_tests(self):
        path = self.change / "implementation-log.md"
        path.write_text(path.read_text(encoding="utf-8").replace("mvn -o verify", "mvn -o test"), encoding="utf-8")
        self.assertIn("build", self.checks())

    def test_duplicate_task_log_is_ambiguous(self):
        path = self.change / "implementation-log.md"
        path.write_text(path.read_text(encoding="utf-8") * 2, encoding="utf-8")
        self.assertIn("implementation-log", self.checks())

    def test_parse_failure_evidence_ignores_report_line_numbers(self):
        path = self.root / "target/surefire-reports/TEST-demo.ATest.xml"
        path.write_text("<testsuite>", encoding="utf-8")
        first = self.checks()["test-execution"].evidence
        path.write_text("\n\n<testsuite>", encoding="utf-8")
        self.assertEqual(first, self.checks()["test-execution"].evidence)

    def test_each_completed_task_requires_its_own_log(self):
        path = self.change / "tasks.md"
        path.write_text(path.read_text(encoding="utf-8") + "\n- [ ] T2. 增加场景；范围：src/test/java/\n", encoding="utf-8")
        self.write("src/test/java/demo/BTest.java", "class BTest {}\n")
        self.commit("RED: second task\n\nTask-Id: T2\nTDD-Phase: RED", ["src/test"])
        self.write("src/test/java/demo/BTest.java", "class BTest { int value = 1; }\n")
        self.commit("GREEN: second task\n\nTask-Id: T2\nTDD-Phase: GREEN", ["src/test"])
        self.assertEqual([], g6_5.check(self.ctx))
        self.assertIn("T2", self.checks()["implementation-log"].reason)
        self.ctx.extra["task"] = "T1"
        self.assertNotIn("implementation-log", self.checks())

    def test_no_gate_writes(self):
        before = {p.relative_to(self.change): p.read_bytes() for p in self.change.iterdir()}
        g6.check(self.ctx)
        g6_5.check(self.ctx)
        self.assertEqual(before, {p.relative_to(self.change): p.read_bytes() for p in self.change.iterdir()})


class TestGate65(GateProject):
    def test_commit_evidence_closes_unchecked_task(self):
        self.assertEqual([], g6_5.check(self.ctx))

    def test_manual_checked_task_is_still_open(self):
        (self.change / "tasks.md").write_text("# Tasks\n- [x] T2. 手工勾选\n", encoding="utf-8")
        finding = self.checks(g6_5)["tasks-complete"]
        self.assertEqual("BLOCK", finding.level)
        self.assertEqual("T2", finding.evidence)

    def test_small_feature_warn_and_bugfix_block(self):
        (self.change / "tasks.md").write_text("# Tasks\n- [ ] T2. 未完成\n", encoding="utf-8")
        self.ctx.meta["complexity"] = "S"
        self.assertEqual("WARN", self.checks(g6_5)["tasks-complete"].level)
        self.ctx.meta["mode"] = "bugfix"
        self.assertEqual("BLOCK", self.checks(g6_5)["tasks-complete"].level)

    def test_deferred_default_and_configuration(self):
        (self.change / "tasks.md").write_text("# Tasks\n- [~] T2. 延期\n", encoding="utf-8")
        self.assertEqual([], g6_5.check(self.ctx))
        self.ctx.config["tasks"] = {"allow_deferred": False}
        self.assertIn("tasks-deferred", self.checks(g6_5))
        self.ctx.config["tasks"]["completion_gate"] = "off"
        self.assertEqual([], g6_5.check(self.ctx))

    def test_missing_malformed_and_duplicate_tasks_fail_closed(self):
        path = self.change / "tasks.md"
        for text in ("# Tasks\n", "- [ ] 没有编号\n", "- [ ] T1. a\n- [ ] T1. b\n"):
            with self.subTest(text=text):
                path.write_text(text, encoding="utf-8")
                self.assertEqual("BLOCK", self.checks(g6_5)["tasks-artifact"].level)
        path.unlink()
        self.assertEqual("BLOCK", self.checks(g6_5)["tasks-artifact"].level)

    def test_red_commit_alone_does_not_finish(self):
        (self.change / "tasks.md").write_text("- [ ] T2. 未实现\n", encoding="utf-8")
        self.write("src/test/java/demo/BTest.java", "class BTest {}\n")
        self.commit("red\n\nTask-Id: T2\nTDD-Phase: RED", ["src/test/java/demo/BTest.java"])
        self.assertIn("T2", self.checks(g6_5)["tasks-complete"].evidence)


class TestGate67(GateProject):
    def setUp(self):
        super().setUp()
        from spec_driven import java
        self.java = java
        self.ctx.config["quality"] = java.quality_defaults(self.root)
        self.project.config_path.write_text(json.dumps(self.ctx.config), encoding="utf-8")
        self.old = java.Violation("checkstyle", "LineLength", "src/main/java/demo/A.java", 3, "行过长")
        self.new = java.Violation("pmd", "Unused", "src/main/java/demo/A.java", 4, "未使用变量")
        self.baseline([self.old])

    def baseline(self, values):
        self.project.quality_baseline.write_text(json.dumps({"version": 1, "violations": [v.to_dict() for v in values]}), encoding="utf-8")

    def run_quality(self, values, errors=None):
        with mock.patch("spec_driven.java.run_quality", return_value=(values, errors or {})):
            return g6_7.check(self.ctx)

    def report(self):
        return (self.change / "static-analysis-report.md").read_text(encoding="utf-8")

    def test_new_existing_repaid_and_contract_report(self):
        findings = self.run_quality([self.new])
        self.assertEqual(["pmd"], [f.check for f in findings])
        self.assertTrue(all(f.locked for f in findings))
        self.assertTrue(self.report().startswith("<!-- generated-by: spec-driven gate-6.7 -->\n"))
        self.assertIn("| 1 | 0 | 1 |", self.report())
        from spec_driven import mdparse
        parsed = mdparse.parse(self.report())
        for key in ("new-violations", "baseline-violations", "repaid-violations"):
            self.assertEqual(["检查", "规则", "位置", "说明"], mdparse.tables(mdparse.find(parsed, key).body)[0].header)
        self.assertEqual([], self.run_quality([self.old]))
        self.assertIn("| 0 | 1 | 0 |", self.report())

    def test_waiver_evidence_ignores_line_number(self):
        first = self.run_quality([self.new])[0]
        moved = self.java.Violation(self.new.check, self.new.rule, self.new.file, 99, self.new.message)
        self.assertEqual(first.evidence, self.run_quality([moved])[0].evidence)
        self.assertNotIn(":4", first.evidence)

    def test_no_check_can_be_disabled_or_downgraded(self):
        from spec_driven import gates
        self.ctx.config["gates"] = {"6.7": {"level": "off"}}
        for check in self.java.CHECKS:
            with self.subTest(check=check):
                value = self.java.Violation(check, "rule", "a.java", 1, "新增")
                with mock.patch("spec_driven.java.run_quality", return_value=([value], {})):
                    findings, code = gates.evaluate("6.7", self.ctx)
                self.assertEqual(3, code)
                self.assertTrue(findings[0].locked)

    def test_failure_report_does_not_mark_unchecked_baseline_repaid(self):
        findings = self.run_quality([], {"checkstyle": "报告缺失"})
        self.assertEqual("BLOCK", findings[0].level)
        self.assertTrue(findings[0].locked)
        self.assertIn("报告缺失", self.report())
        self.assertIn("| 0 | 0 | 0 |", self.report())

    def test_missing_and_corrupt_baseline_or_config_still_write_report(self):
        for data in (None, "{", '{"version":1,"violations":"invalid"}'):
            with self.subTest(data=data):
                if data is None:
                    self.project.quality_baseline.unlink()
                else:
                    self.project.quality_baseline.write_text(data, encoding="utf-8")
                findings = self.run_quality([])
                self.assertTrue(any(f.check == "quality-baseline" and f.locked for f in findings))
                self.assertIn("## 结论", self.report())
        self.baseline([])
        self.project.config_path.unlink()
        self.assertTrue(any(f.check == "quality-config" for f in self.run_quality([])))

    def test_report_write_failure_is_locked_block(self):
        (self.change / "static-analysis-report.md").mkdir()
        findings = self.run_quality([])
        self.assertTrue(any(f.check == "quality-report" and f.locked for f in findings))

    def test_report_escapes_table_content(self):
        value = self.java.Violation("pmd", "R|1", "A.java", 1, "bad | message\nnext")
        self.run_quality([value])
        from spec_driven import mdparse
        section = mdparse.find(mdparse.parse(self.report()), "new-violations")
        rows = mdparse.tables(section.body)[0].rows
        self.assertEqual(1, len(rows))
        self.assertIn("bad", rows[0]["说明"])


if __name__ == "__main__":
    unittest.main()
