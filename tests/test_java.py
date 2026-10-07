"""Java report and command boundary tests."""
import importlib
import json
import os
import shutil
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from spec_driven import gitutil
try:
    java = importlib.import_module("spec_driven.java")
except ImportError:
    java = None

FIXTURES = Path(__file__).parent / "fixtures" / "t5" / "java"
CHECKS = ("archunit", "checkstyle", "spotbugs", "pmd", "sqlfluff")


class JavaTests(unittest.TestCase):
    def setUp(self):
        self.assertIsNotNone(java, "Java API 尚未实现")
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.env = patch.dict(os.environ, {"REINS_HOME": str(self.root / "home")})
        self.env.start()
        self.addCleanup(self.env.stop)

    def write(self, path, content):
        target = self.root / path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding="utf-8")
        return target

    def fixture(self, name, dest):
        return self.write(dest, (FIXTURES / name).read_text(encoding="utf-8"))

    def source(self, module=""):
        return self.write(module + "src/main/java/demo/Service.java", "class Service {}\n")

    def quality(self, failure=False, exitcode=0):
        result = {}
        for check in CHECKS:
            suffix = ".json" if check == "sqlfluff" else ".xml"
            name = check + ("-fail" if failure else "-pass") + suffix
            target = "reports/" + check + suffix
            content = (FIXTURES / name).read_text(encoding="utf-8")
            script = "from pathlib import Path; import sys; p=Path(%r); p.parent.mkdir(parents=True,exist_ok=True); p.write_text(%r,encoding='utf-8'); sys.exit(%s)" % (target, content, exitcode)
            result[check] = {"command": [sys.executable, "-c", script], "report_path": target}
        return result

    def test_detect_build_rejects_missing_and_ambiguous(self):
        with self.assertRaises(java.JavaError):
            java.detect_build(self.root)
        self.write("pom.xml", "<project/>")
        self.assertEqual(java.detect_build(self.root), "maven")
        self.write("build.gradle.kts", "")
        with self.assertRaises(java.JavaError):
            java.detect_build(self.root)
        (self.root / "pom.xml").unlink()
        self.assertEqual(java.detect_build(self.root), "gradle")

    def test_reports_sum_modules_without_aggregate_double_count(self):
        self.fixture("surefire-pass.xml", "a/target/surefire-reports/TEST-a.xml")
        content = (FIXTURES / "gradle-fail.xml").read_text(encoding="utf-8")
        self.write("b/build/test-results/test/TEST-b.xml", '<testsuites tests="2" failures="1">' + content + '</testsuites>')
        self.assertEqual(java.test_reports(self.root), {"tests": 5, "failures": 1, "errors": 0, "skipped": 1})

    def test_reports_reject_missing_corrupt_and_bad_counts(self):
        for content in (None, "<testsuite", '<testsuite tests="-1" failures="0" errors="0"/>', '<testsuite tests="1" failures="2" errors="0"/>', '<testsuite tests="NaN" failures="0" errors="0"/>'):
            with self.subTest(content=content):
                if content is not None:
                    self.write("report.xml", content)
                with self.assertRaises(java.JavaError):
                    java.test_reports(self.root, "report.xml")

    def test_skip_flags_detect_true_and_preserve_false(self):
        self.write("pom.xml", "<project/>")
        for command in ("mvn test -DskipTests", "mvn test -Dmaven.test.skip=true", "gradle check -x test", "gradle check --exclude-task=:api:test"):
            self.assertTrue(java.skip_reasons(self.root, [command]), command)
        self.assertEqual(java.skip_reasons(self.root, ["mvn test -DskipTests=false -Dmaven.test.skip=false", "gradle -x checkstyleMain test"]), [])

    def test_skip_pom_properties_modules_and_unresolved(self):
        self.write("pom.xml", '<project xmlns="http://maven.apache.org/POM/4.0.0"><properties><skip.flag>false</skip.flag></properties></project>')
        pom = '<project><build><plugins><plugin><artifactId>maven-surefire-plugin</artifactId><configuration><skipTests>${skip.flag}</skipTests></configuration></plugin></plugins></build></project>'
        self.write("api/pom.xml", pom)
        self.assertEqual(java.skip_reasons(self.root, []), [])
        self.write("api/pom.xml", pom.replace("skip.flag", "unknown.flag"))
        self.assertTrue(java.skip_reasons(self.root, []))
        self.write("api/pom.xml", pom.replace("${skip.flag}", "true"))
        self.assertTrue(java.skip_reasons(self.root, []))

    def test_changed_lines_only_committed_new_java_lines(self):
        gitutil.git(["init"], self.root)
        gitutil.git(["config", "user.name", "Test"], self.root)
        gitutil.git(["config", "user.email", "test@example.test"], self.root)
        self.write("api/src/main/java/demo/Service.java", "one\ntwo\nthree\n")
        self.write("api/src/main/java/demo/Gone.java", "gone\n")
        gitutil.git(["add", "."], self.root)
        gitutil.git(["commit", "-m", "initial"], self.root)
        base = gitutil.git(["rev-parse", "HEAD"], self.root)
        self.write("api/src/main/java/demo/Service.java", "one\nnew\nthree\nfour\n")
        (self.root / "api/src/main/java/demo/Gone.java").unlink()
        gitutil.git(["add", "."], self.root)
        gitutil.git(["commit", "-m", "change"], self.root)
        self.write("api/src/main/java/demo/Service.java", "uncommitted\n")
        self.assertEqual(java.changed_lines(self.root, base), {"api/src/main/java/demo/Service.java": {2, 4}})

    def test_coverage_counts_executable_changes_and_missing_source_blocks(self):
        self.source()
        self.fixture("jacoco.xml", "target/site/jacoco/jacoco.xml")
        result = java.diff_coverage(self.root, {"src/main/java/demo/Service.java": {1, 2, 3}})
        self.assertEqual(result, {"covered": 1, "total": 2, "percent": 50.0, "uncovered": ["src/main/java/demo/Service.java:2"]})
        with self.assertRaises(java.JavaError):
            java.diff_coverage(self.root, {"src/main/java/demo/Missing.java": {1}})

    def test_coverage_never_crosses_modules_with_same_source_name(self):
        self.source("a/")
        self.source("b/")
        self.fixture("jacoco.xml", "a/target/site/jacoco/jacoco.xml")
        lines = {"b/src/main/java/demo/Service.java": {1}}
        with self.assertRaises(java.JavaError):
            java.diff_coverage(self.root, lines)
        self.write("b/build/reports/jacoco/test/jacocoTestReport.xml", (FIXTURES / "jacoco.xml").read_text(encoding="utf-8").replace('mi="0" ci="2"', 'mi="2" ci="0"'))
        self.assertEqual(java.diff_coverage(self.root, lines)["percent"], 0.0)

    def test_coverage_no_changes_needs_no_report(self):
        self.assertEqual(java.diff_coverage(self.root, {}), {"covered": 0, "total": 0, "percent": 100.0, "uncovered": []})
        with self.assertRaises(java.JavaError):
            java.diff_coverage(self.root, {"src/main/java/demo/Service.java": {1}})

    def test_quality_parses_real_formats_and_sql_violation_exit_one(self):
        self.source()
        quality = self.quality(True, 0)
        quality["sqlfluff"]["command"][-1] = quality["sqlfluff"]["command"][-1].replace("sys.exit(0)", "sys.exit(1)")
        violations, errors = java.run_quality(self.root, quality)
        self.assertEqual(errors, {})
        self.assertEqual({v.check for v in violations}, set(CHECKS))
        self.assertEqual(len(violations), 5)
        self.assertEqual(next(v.file for v in violations if v.check == "spotbugs"), "src/main/java/demo/Service.java")
        self.assertEqual(next(v.line for v in violations if v.check == "pmd"), 7)

    def test_quality_clean_reports_pass(self):
        violations, errors = java.run_quality(self.root, self.quality())
        self.assertEqual((violations, errors), ([], {}))

    def test_quality_fails_closed_for_off_missing_and_stale_reports(self):
        quality = self.quality()
        quality["archunit"]["enabled"] = False
        quality["checkstyle"]["command"] = [sys.executable, "-c", "pass"]
        self.fixture("checkstyle-pass.xml", "reports/checkstyle.xml")
        del quality["pmd"]
        quality["spotbugs"]["report_path"] = "missing.xml"
        quality["sqlfluff"]["command"] = "off"
        violations, errors = java.run_quality(self.root, quality)
        self.assertEqual(set(errors), set(CHECKS))
        self.assertEqual(violations, [])

    def test_quality_rejects_tool_errors_even_with_valid_reports(self):
        quality = self.quality(True, 2)
        violations, errors = java.run_quality(self.root, quality)
        self.assertEqual(set(errors), set(CHECKS))
        quality = self.quality()
        quality["archunit"]["command"] = [sys.executable, "-c", "import time; time.sleep(1)"]
        quality["archunit"]["timeout"] = 0.01
        quality["pmd"]["command"] = ["no-such-quality-executable"]
        self.assertEqual(set(java.run_quality(self.root, quality)[1]), {"archunit", "pmd"})

    def test_quality_rejects_corrupt_reports_and_empty_archunit(self):
        quality = self.quality()
        for check in ("checkstyle", "spotbugs", "pmd", "sqlfluff"):
            target = quality[check]["report_path"]
            quality[check]["command"] = [sys.executable, "-c", "from pathlib import Path; p=Path(%r); p.parent.mkdir(parents=True,exist_ok=True); p.write_text('bad',encoding='utf-8')" % target]
        quality["archunit"]["command"] = [sys.executable, "-c", "from pathlib import Path; p=Path('reports/archunit.xml'); p.parent.mkdir(parents=True,exist_ok=True); p.write_text('<testsuite tests=\"0\" failures=\"0\" errors=\"0\"/>',encoding='utf-8')"]
        self.assertEqual(set(java.run_quality(self.root, quality)[1]), set(CHECKS))

    def test_sqlfluff_stdout_and_string_command(self):
        quality = self.quality()
        quality["sqlfluff"] = {"command": [sys.executable, "-c", "print('[]')"], "report_path": "-"}
        quality["pmd"]["command"] = __import__("shlex").join(quality["pmd"]["command"]) if hasattr(__import__("shlex"), "join") else quality["pmd"]["command"]
        self.assertEqual(java.run_quality(self.root, quality), ([], {}))

    def test_fingerprint_ignores_line_and_java_location_line(self):
        a = java.Violation("archunit", "layers", "src/main/java/demo/Service.java", 12, "Violation (Service.java:12)")
        b = java.Violation("archunit", "layers", "src/main/java/demo/Service.java", 90, "Violation (Service.java:90)")
        self.assertEqual(a.fingerprint, b.fingerprint)
        c = java.Violation("archunit", "layers", "src/main/java/demo/Service.java", 12, "Different rule (Service.java:12)")
        self.assertNotEqual(a.fingerprint, c.fingerprint)

    def test_baseline_strict_version_types_and_fingerprint(self):
        v = java.Violation("pmd", "Unused", "src/main/java/A.java", 1, "unused")
        path = self.write("baseline.json", json.dumps({"version": 1, "violations": [v.to_dict()]}))
        self.assertEqual(java.load_baseline(path), [v])
        for value in ({"version": 2, "violations": []}, {"version": 1, "violations": [{"check": "pmd"}]}, {"version": 1, "violations": [dict(v.to_dict(), fingerprint="wrong")]}, {"version": 1, "violations": [dict(v.to_dict(), line=True)]}):
            path.write_text(json.dumps(value), encoding="utf-8")
            with self.assertRaises(java.JavaError):
                java.load_baseline(path)

    def test_defaults_support_builds_and_lock_archunit_freeze(self):
        self.write("pom.xml", "<project/>")
        quality = java.quality_defaults(self.root)
        self.assertEqual(set(quality), set(CHECKS))
        self.assertIn("-Darchunit.freeze.store.default.allowStoreCreation=false", quality["archunit"]["command"])
        self.assertIn("-Darchunit.freeze.store.default.allowStoreUpdate=false", quality["archunit"]["command"])
        (self.root / "pom.xml").unlink()
        self.write("build.gradle", "")
        self.assertEqual(set(java.quality_defaults(self.root)), set(CHECKS))


    def test_archunit_freeze_updates_require_initialize(self):
        quality = self.quality()
        quality["archunit"]["command"].append("-Darchunit_freeze.store.default.allowStoreCreation=true")
        self.assertEqual(set(java.run_quality(self.root, quality)[1]), {"archunit"})
        self.assertEqual(java.run_quality(self.root, quality, initialize=True)[1], {})

    def test_archunit_environment_forces_freeze_policy_for_custom_commands(self):
        for initialize, value in ((False, "false"), (True, "true")):
            quality = self.quality()
            content = (FIXTURES / "archunit-pass.xml").read_text(encoding="utf-8")
            script = "import os; from pathlib import Path; assert '-Darchunit.freeze.store.default.allowStoreCreation=%s' in os.environ['JAVA_TOOL_OPTIONS']; assert '-Darchunit.freeze.store.default.allowStoreUpdate=%s' in os.environ['JAVA_TOOL_OPTIONS']; p=Path('reports/archunit.xml'); p.parent.mkdir(parents=True,exist_ok=True); p.write_text(%r,encoding='utf-8')" % (value, value, content)
            quality["archunit"]["command"] = [sys.executable, "-c", script]
            self.assertEqual(java.run_quality(self.root, quality, initialize=initialize)[1], {})

    def test_quality_module_reports_keep_identical_source_names_separate(self):
        self.source("a/")
        self.source("b/")
        quality = self.quality()
        content = (FIXTURES / "checkstyle-fail.xml").read_text(encoding="utf-8")
        script = "from pathlib import Path; [(p.parent.mkdir(parents=True,exist_ok=True), p.write_text(%r,encoding='utf-8')) for p in (Path('a/target/checkstyle-result.xml'),Path('b/target/checkstyle-result.xml'))]" % content
        quality["checkstyle"] = {"command": [sys.executable, "-c", script], "report_path": "**/target/checkstyle-result.xml"}
        violations, errors = java.run_quality(self.root, quality)
        self.assertEqual(errors, {})
        self.assertEqual({v.file for v in violations}, {"a/src/main/java/demo/Service.java", "b/src/main/java/demo/Service.java"})

    def test_jacoco_aggregate_group_resolves_modules_without_crossing(self):
        self.source("a/")
        self.source("b/")
        report = '<report name="all"><group name="a"><package name="demo"><sourcefile name="Service.java"><line nr="1" mi="0" ci="1"/></sourcefile></package></group><group name="b"><package name="demo"><sourcefile name="Service.java"><line nr="1" mi="1" ci="0"/></sourcefile></package></group></report>'
        self.write("target/site/jacoco-aggregate/jacoco.xml", report)
        self.assertEqual(java.diff_coverage(self.root, {"a/src/main/java/demo/Service.java": {1}, "b/src/main/java/demo/Service.java": {1}}), {"covered": 1, "total": 2, "percent": 50.0, "uncovered": ["b/src/main/java/demo/Service.java:1"]})

    def test_archunit_failure_type_and_sql_parse_errors_are_tool_errors(self):
        quality = self.quality()
        content = (FIXTURES / "archunit-fail.xml").read_text(encoding="utf-8").replace("java.lang.AssertionError", "java.lang.NullPointerException")
        quality["archunit"]["command"] = [sys.executable, "-c", "from pathlib import Path; p=Path('reports/archunit.xml'); p.parent.mkdir(parents=True,exist_ok=True); p.write_text(%r,encoding='utf-8')" % content]
        quality["sqlfluff"] = {"command": [sys.executable, "-c", "print('[{\"filepath\":\"migration.sql\",\"violations\":[{\"code\":\"PRS\",\"description\":\"Cannot parse SQL\",\"start_line_no\":1}]}]')"], "report_path": "-"}
        self.assertEqual(set(java.run_quality(self.root, quality)[1]), {"archunit", "sqlfluff"})

    def test_quality_stale_reports_cannot_mask_module_not_checked(self):
        quality = self.quality()
        self.fixture("pmd-pass.xml", "a/target/pmd.xml")
        quality["pmd"]["report_path"] = "**/target/pmd.xml"
        content = (FIXTURES / "pmd-pass.xml").read_text(encoding="utf-8")
        quality["pmd"]["command"] = [sys.executable, "-c", "from pathlib import Path; p=Path('b/target/pmd.xml'); p.parent.mkdir(parents=True,exist_ok=True); p.write_text(%r,encoding='utf-8')" % content]
        self.assertEqual(set(java.run_quality(self.root, quality)[1]), {"pmd"})


    def test_testcase_failures_cannot_hide_behind_passing_suite_counts(self):
        for content in ('<testsuite tests="1" failures="0" errors="0"><testcase name="failed"><failure message="failed"/></testcase></testsuite>', '<testsuite tests="1" failures="0" errors="0" skipped="0"><testcase name="skipped"><skipped/></testcase></testsuite>'):
            self.write("tests.xml", content)
            with self.assertRaises(java.JavaError):
                java.test_reports(self.root, "tests.xml")

    def test_quality_json_directory_and_path_escape_validation(self):
        quality = self.quality()
        quality["sqlfluff"]["report_path"] = "reports/sql"
        quality["sqlfluff"]["command"] = [sys.executable, "-c", "from pathlib import Path; p=Path('reports/sql/result.json'); p.parent.mkdir(parents=True,exist_ok=True); p.write_text('[]',encoding='utf-8')"]
        self.assertEqual(java.run_quality(self.root, quality)[1], {})
        quality["pmd"]["report_path"] = "../outside.xml"
        quality["spotbugs"]["timeout"] = "forever"
        self.assertEqual(set(java.run_quality(self.root, quality)[1]), {"pmd", "spotbugs"})

    def test_sql_resources_extract_flyway_and_mapper_include_and_bindings(self):
        self.write("src/main/resources/db/migration/V1__table.sql", "select 1;\n")
        self.write("src/main/resources/mapper/Mapper.xml", '<!DOCTYPE mapper PUBLIC "-//mybatis.org//DTD Mapper 3.0//EN" "http://mybatis.org/dtd/mybatis-3-mapper.dtd">\n<mapper namespace="demo.Mapper">\n<sql id="columns">id, name</sql>\n<select id="find">select <include refid="columns"/> from users where id = #{id}</select>\n</mapper>')
        quality = self.quality()
        script = "import json,sys; from pathlib import Path; paths=sorted(Path(sys.argv[-1]).glob('*.sql')); sqls=[p.read_text(encoding='utf-8') for p in paths]; assert {s.strip() for s in sqls} == {'select 1;', 'select id, name from users where id = ?'}; print(json.dumps([{'filepath':str(p),'violations':[{'code':'CP01','description':'Use upper case','start_line_no':1}]} for p in paths]))"
        quality["sqlfluff"] = {"command": [sys.executable, "-c", script], "report_path": "-", "source": "java-resources"}
        violations, errors = java.run_quality(self.root, quality)
        self.assertEqual(errors, {})
        sql = [v for v in violations if v.check == "sqlfluff"]
        self.assertEqual({(v.file, v.line) for v in sql}, {("src/main/resources/db/migration/V1__table.sql", 1), ("src/main/resources/mapper/Mapper.xml", 4)})

    def test_sql_resources_dynamic_or_missing_include_fail_closed(self):
        quality = self.quality()
        script = "import json,sys; from pathlib import Path; print(json.dumps([{'filepath':str(p),'violations':[]} for p in Path(sys.argv[-1]).glob('*.sql')]))"
        quality["sqlfluff"] = {"command": [sys.executable, "-c", script], "report_path": "-", "source": "java-resources"}
        for body in ('<select id="x">select * from users <if test="id != null">where id=#{id}</if></select>', '<select id="x">select ${columns} from users</select>'):
            self.write("src/main/resources/mapper/Mapper.xml", '<mapper namespace="demo.Mapper">' + body + '</mapper>')
            violations, errors = java.run_quality(self.root, quality)
            self.assertEqual(errors, {})
            self.assertEqual([v.rule for v in violations], ["mybatis-dollar-substitution"] if "${" in body else [])
        for body in ('<select id="x">select <include refid="missing"/> from users</select>', '<sql id="cycle"><include refid="cycle"/></sql><select id="x"><include refid="cycle"/></select>'):
            self.write("src/main/resources/mapper/Mapper.xml", '<mapper namespace="demo.Mapper">' + body + '</mapper>')
            self.assertEqual(set(java.run_quality(self.root, quality)[1]), {"sqlfluff"})

    def test_archunit_uses_actual_system_property_names(self):
        self.write("pom.xml", "<project/>")
        command = java.quality_defaults(self.root)["archunit"]["command"]
        self.assertIn("-Darchunit.freeze.store.default.allowStoreCreation=false", command)
        self.assertIn("-Darchunit.freeze.store.default.allowStoreUpdate=false", command)
        self.assertIn("-Darchunit.freeze.refreeze=false", command)
        quality = self.quality()
        quality["archunit"]["command"].append("-Darchunit.freeze.refreeze=true")
        self.assertIn("archunit", java.run_quality(self.root, quality)[1])

    def test_reports_older_than_java_sources_fail_closed(self):
        source = self.source()
        path = self.fixture("surefire-pass.xml", "target/surefire-reports/TEST-old.xml")
        older = source.stat().st_mtime - 10
        os.utime(str(path), (older, older))
        with self.assertRaises(java.JavaError):
            java.test_reports(self.root)
        path = self.fixture("jacoco.xml", "target/site/jacoco/jacoco.xml")
        os.utime(str(path), (older, older))
        with self.assertRaises(java.JavaError):
            java.diff_coverage(self.root, {"src/main/java/demo/Service.java": {1}})

    def test_module_report_does_not_claim_root_module_source(self):
        self.source()
        self.source("child/")
        quality = self.quality()
        content = (FIXTURES / "checkstyle-fail.xml").read_text(encoding="utf-8")
        script = "from pathlib import Path; p=Path('child/target/checkstyle-result.xml'); p.parent.mkdir(parents=True,exist_ok=True); p.write_text(%r,encoding='utf-8')" % content
        quality["checkstyle"] = {"command": [sys.executable, "-c", script], "report_path": "child/target/checkstyle-result.xml"}
        violations, errors = java.run_quality(self.root, quality)
        self.assertEqual(errors, {})
        self.assertEqual([v.file for v in violations], ["child/src/main/java/demo/Service.java"])

    def test_partial_report_with_compilation_failure_is_not_completed_check(self):
        quality = self.quality(True, 0)
        quality["checkstyle"]["command"][-1] = quality["checkstyle"]["command"][-1].replace("sys.exit(0)", "pass") + "; sys.stderr.write('module b compilation failure'); sys.exit(1)"
        violations, errors = java.run_quality(self.root, quality)
        self.assertIn("checkstyle", errors)
        self.assertNotIn("checkstyle", {v.check for v in violations})

    def test_archunit_location_uses_business_source_not_test_package(self):
        self.write("src/main/java/com/acme/service/OrderService.java", "class OrderService {}")
        report = '<testsuite name="arch" tests="1" failures="1" errors="0"><testcase classname="com.acme.arch.ArchitectureTest" name="layers"><failure type="java.lang.AssertionError" message="com.acme.service.OrderService.run() violates layers (OrderService.java:12)"/></testcase></testsuite>'
        quality = self.quality()
        script = "from pathlib import Path; p=Path('target/surefire-reports/TEST-Arch.xml'); p.parent.mkdir(parents=True,exist_ok=True); p.write_text(%r,encoding='utf-8')" % report
        quality["archunit"] = {"command": [sys.executable, "-c", script], "report_path": "target/surefire-reports/TEST-Arch.xml"}
        violations, errors = java.run_quality(self.root, quality)
        self.assertEqual(errors, {})
        self.assertEqual([(v.file, v.line) for v in violations], [("src/main/java/com/acme/service/OrderService.java", 12)])

    def test_wrapper_commands_remain_project_relative(self):
        self.write("pom.xml", "<project/>")
        self.write("mvnw.cmd" if os.name == "nt" else "mvnw", "")
        command = java.quality_defaults(self.root)["archunit"]["command"]
        self.assertEqual(command[0], "./mvnw.cmd" if os.name == "nt" else "./mvnw")
        self.assertNotIn(str(self.root), json.dumps(java.quality_defaults(self.root)))

    def test_sql_resource_mode_none_preserves_custom_command(self):
        self.write("src/main/resources/mapper/Mapper.xml", "broken xml")
        quality = self.quality()
        quality["sqlfluff"].update({"source": None, "report_path": "-", "command": [sys.executable, "-c", "print('[]')"]})
        self.assertEqual(java.run_quality(self.root, quality)[1], {})

    def test_sql_resources_map_multiline_violation_to_original_mapper_line(self):
        self.write("src/main/resources/mapper/Mapper.xml", '<mapper namespace="demo.Mapper">\n<select id="find">\nselect id\nfrom users\n</select>\n</mapper>')
        quality = self.quality()
        script = "import json,sys; from pathlib import Path; print(json.dumps([{'filepath':str(p),'violations':[{'code':'CP01','description':'Upper case','start_line_no':3}]} for p in Path(sys.argv[-1]).glob('*.sql')]))"
        quality["sqlfluff"] = {"command": [sys.executable, "-c", script], "report_path": "-", "source": "java-resources"}
        violations, errors = java.run_quality(self.root, quality)
        self.assertEqual(errors, {})
        self.assertEqual([(v.file, v.line) for v in violations], [("src/main/resources/mapper/Mapper.xml", 4)])


if __name__ == "__main__":
    unittest.main()
