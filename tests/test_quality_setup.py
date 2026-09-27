"""T16: transactional, offline-first Maven quality onboarding."""

import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest import mock
import xml.etree.ElementTree as ET

from tests import CLI_LIB  # noqa: F401
from tests.support_t2 import cli


POM = '''<project xmlns="http://maven.apache.org/POM/4.0.0">
  <modelVersion>4.0.0</modelVersion>
  <!-- keep this comment and whitespace -->
  <groupId>demo</groupId><artifactId>app</artifactId><version>1</version>
  <dependencies>
    <dependency><groupId>org.junit.jupiter</groupId><artifactId>junit-jupiter</artifactId><version>5.12.2</version><scope>test</scope></dependency>
  </dependencies>
</project>
'''


class QualitySetupTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.old = Path.cwd()
        os.chdir(str(self.root))
        self.addCleanup(os.chdir, str(self.old))
        patch = mock.patch.dict(os.environ, {"REINS_HOME": str(self.root / "home")})
        patch.start()
        self.addCleanup(patch.stop)
        self.write("pom.xml", POM)
        self.write("src/main/java/demo/domain/Points.java", "package demo.domain;\npublic class Points {}\n")

    def write(self, path, text):
        p = self.root / path
        p.parent.mkdir(parents=True, exist_ok=True)
        with p.open("w", encoding="utf-8", newline="") as stream:
            stream.write(text)

    def snapshot(self):
        return {p.relative_to(self.root).as_posix(): p.read_bytes() for p in self.root.rglob("*") if p.is_file()}

    def test_dry_run_lists_concrete_edits_without_writes(self):
        before = self.snapshot()
        code, output = cli("quality", "setup", "--dry-run")
        self.assertEqual(0, code, output)
        self.assertIn("archunit-junit5", output)
        self.assertIn("ReinsArchTest.java", output)
        self.assertIn("quality", output)
        self.assertEqual(before, self.snapshot())

    def test_offline_writes_minimal_pom_and_preserves_team_config(self):
        self.write(".openspec/.config.json", '{"test":{"require_tests":false},"quality":{"pmd":{"command":["custom-pmd"],"report_path":"custom.xml"}}}')
        with mock.patch("subprocess.run", side_effect=AssertionError("离线不得运行外部命令")):
            code, output = cli("quality", "setup")
        self.assertEqual(2, code, output)
        self.assertIn("预热", output)
        pom = (self.root / "pom.xml").read_text(encoding="utf-8")
        self.assertIn("<!-- keep this comment and whitespace -->", pom)
        self.assertEqual(POM.encode("utf-8"), (self.root / "pom.xml.reins-bak").read_bytes())
        xml = ET.fromstring(pom)
        deps = xml.findall("{*}dependencies/{*}dependency")
        self.assertEqual(2, len(deps))
        self.assertEqual("test", deps[1].findtext("{*}scope"))
        config = json.loads((self.root / ".openspec/.config.json").read_text(encoding="utf-8"))
        self.assertFalse(config["test"]["require_tests"])
        self.assertEqual(["custom-pmd"], config["quality"]["pmd"]["command"])
        self.assertIn("**/target/checkstyle-result.xml", config["quality"]["checkstyle"]["report_path"])
        self.assertTrue((self.root / "src/test/java/demo/architecture/ReinsArchTest.java").is_file())

    def test_repeated_setup_is_byte_identical(self):
        self.assertEqual(2, cli("quality", "setup")[0])
        before = self.snapshot()
        self.assertEqual(2, cli("quality", "setup")[0])
        self.assertEqual(before, self.snapshot())

    def test_existing_test_and_dependency_are_not_overwritten(self):
        self.write("pom.xml", POM.replace("</dependencies>", "<dependency><groupId>com.tngtech.archunit</groupId><artifactId>archunit-junit5</artifactId><version>1.2.1</version><scope>test</scope></dependency></dependencies>"))
        self.write("src/test/java/demo/architecture/ReinsArchTest.java", "// custom rules\n")
        before = (self.root / "pom.xml").read_bytes()
        code, output = cli("quality", "setup")
        self.assertEqual(2, code, output)
        self.assertEqual(before, (self.root / "pom.xml").read_bytes())
        self.assertEqual("// custom rules\n", (self.root / "src/test/java/demo/architecture/ReinsArchTest.java").read_text(encoding="utf-8"))
        self.assertIn("不覆盖", output)

    def test_junit4_dependency_and_crlf_are_preserved(self):
        self.write("pom.xml", POM.replace("org.junit.jupiter", "junit").replace("junit-jupiter", "junit").replace("5.12.2", "4.13.2").replace("\n", "\r\n"))
        code, output = cli("quality", "setup")
        self.assertEqual(2, code, output)
        data = (self.root / "pom.xml").read_bytes()
        self.assertIn(b"archunit-junit4", data)
        self.assertNotIn(b"\n", data.replace(b"\r\n", b""))

    def test_ambiguous_package_requires_explicit_confirmation(self):
        p = self.root / "src/main/java/demo/domain/Points.java"
        p.unlink()
        self.write("src/main/java/demo/Points.java", "package demo;\nclass Points {}\n")
        before = self.snapshot()
        code, output = cli("quality", "setup")
        self.assertEqual(1, code, output)
        self.assertIn("候选", output)
        self.assertEqual(before, self.snapshot())
        self.assertEqual(0, cli("quality", "setup", "--base-package", "demo", "--dry-run")[0])

    def test_no_junit_does_not_guess(self):
        self.write("pom.xml", "<project><modelVersion>4.0.0</modelVersion></project>")
        before = self.snapshot()
        code, output = cli("quality", "setup")
        self.assertEqual(1, code, output)
        self.assertIn("JUnit", output)
        self.assertEqual(before, self.snapshot())

    def test_multimodule_only_java_modules_are_edited(self):
        # The aggregator's dependency is inherited without rewriting it.
        (self.root / "src/main/java/demo/domain/Points.java").unlink()
        self.write("pom.xml", POM.replace("</project>", "<packaging>pom</packaging><modules><module>app</module><module>docs</module></modules></project>"))
        self.write("app/pom.xml", '<project><modelVersion>4.0.0</modelVersion><parent><groupId>demo</groupId><artifactId>app</artifactId><version>1</version></parent><artifactId>child</artifactId></project>')
        self.write("app/src/main/java/demo/domain/Value.java", "package demo.domain;\nclass Value {}")
        self.write("docs/pom.xml", "<project><packaging>pom</packaging></project>")
        parent = (self.root / "pom.xml").read_bytes()
        code, output = cli("quality", "setup")
        self.assertEqual(2, code, output)
        self.assertIn("docs", output)
        self.assertEqual(parent, (self.root / "pom.xml").read_bytes())
        self.assertIn("archunit-junit5", (self.root / "app/pom.xml").read_text(encoding="utf-8"))
        self.assertFalse((self.root / "docs/pom.xml.reins-bak").exists())

    def test_missing_or_external_module_fails_before_any_write(self):
        for module in ("missing", "../outside"):
            self.write("pom.xml", POM.replace("</project>", "<modules><module>%s</module></modules></project>" % module))
            before = self.snapshot()
            self.assertEqual(1, cli("quality", "setup")[0])
            self.assertEqual(before, self.snapshot())

    def test_gradle_reports_manual_steps_without_changes(self):
        (self.root / "pom.xml").unlink()
        self.write("build.gradle", "plugins { id 'java' }")
        before = self.snapshot()
        code, output = cli("quality", "setup")
        self.assertEqual(1, code, output)
        self.assertIn("暂不支持", output)
        self.assertIn("checkstyle", output)
        self.assertEqual(before, self.snapshot())

    def test_malformed_config_is_not_replaced(self):
        self.write(".openspec/.config.json", "{")
        before = self.snapshot()
        self.assertEqual(1, cli("quality", "setup")[0])
        self.assertEqual(before, self.snapshot())

    def test_online_failure_restores_all_managed_files(self):
        from spec_driven import java_setup
        before = self.snapshot()
        with mock.patch.object(java_setup, "warm", side_effect=RuntimeError("下载失败")):
            code, output = cli("quality", "setup", "--online")
        self.assertEqual(1, code, output)
        self.assertEqual(before, self.snapshot())

    def test_write_failure_restores_pom_and_keeps_existing_backup(self):
        from spec_driven import java_setup
        self.write("pom.xml.reins-bak", POM)
        before = self.snapshot()
        original = java_setup.write_text
        def failing(path, text):
            if Path(path).name == "ReinsArchTest.java":
                raise OSError("写入失败")
            original(path, text)
        with mock.patch.object(java_setup, "write_text", side_effect=failing):
            self.assertEqual(1, cli("quality", "setup")[0])
        self.assertEqual(before, self.snapshot())

    def test_sql_without_sqlfluff_gives_actionable_dialect_guidance(self):
        self.write("src/main/resources/db/migration/V1.sql", "select 1;")
        with mock.patch("shutil.which", return_value=None):
            code, output = cli("quality", "setup", "--dry-run")
        self.assertEqual(0, code, output)
        self.assertIn("sqlfluff", output)
        self.assertIn("dialect", output)


if __name__ == "__main__":
    unittest.main()
