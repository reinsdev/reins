"""T20 SQL extraction, quality debt counts, and executable diagnostics."""
import contextlib
import io
import json
import os
import shutil
import shlex
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from spec_driven import config, java
from spec_driven.commands import init_config
from spec_driven.gates import GateContext, g6_7
from spec_driven.project import Project


class SqlQualityTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.environment = dict(os.environ, REINS_HOME=str(self.root / "home"))
        self.env = patch.dict(os.environ, self.environment)
        self.env.start()
        self.addCleanup(self.env.stop)
        self.write("pom.xml", "<project/>")

    def write(self, filename, text):
        path = self.root / filename
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
        return path

    def mapper(self, body, filename="src/main/resources/Mapper.xml"):
        return self.write(filename, '<mapper namespace="demo">\n' + body + '\n</mapper>')

    def fake(self, violations=None, assertion="", exitcode=None):
        script = """import json, sys
from pathlib import Path
directory = Path(sys.argv[-1])
files = sorted(directory.glob('*.sql'))
with Path('calls.txt').open('a', encoding='utf-8') as handle:
    handle.write('call\\n')
rows = []
for path in files:
    sql = path.read_text(encoding='utf-8')
    %s
    rows.append({'filepath': str(path), 'violations': %r})
print(json.dumps(rows))
sys.exit(%s)
""" % (assertion or "pass", violations or [], exitcode if exitcode is not None else int(bool(violations)))
        return [sys.executable, "-c", script, "-"]

    def scan(self, violations=None, assertion="", paths=None, exitcode=None):
        return java._sql_resources(self.root, self.fake(violations, assertion, exitcode),
                                   self.environment, 10, paths=paths)

    def quality(self, sql_command=None):
        reports = {
            "archunit": '<testsuite tests="1" failures="0" errors="0" skipped="0"><testcase name="layers"/></testsuite>',
            "checkstyle": '<checkstyle/>', "spotbugs": '<BugCollection/>', "pmd": '<pmd/>',
        }
        result = {}
        for name, content in reports.items():
            filename = "reports/%s.xml" % name
            script = "from pathlib import Path; p=Path(%r); p.parent.mkdir(parents=True,exist_ok=True); p.write_text(%r,encoding='utf-8')" % (filename, content)
            result[name] = {"command": [sys.executable, "-c", script], "report_path": filename}
        result["sqlfluff"] = {"command": sql_command or self.fake(), "report_path": "-", "source": "java-resources"}
        return result

    def context(self, baseline, quality):
        project = Project(self.root)
        self.write(".openspec/.config.json", json.dumps({"quality": quality}))
        self.write(".openspec/quality-baseline.json", json.dumps({"version": 1, "violations": [v.to_dict() for v in baseline]}))
        directory = self.root / ".openspec/changes/demo"
        directory.mkdir(parents=True, exist_ok=True)
        return GateContext(project, "demo", directory, {}, {"quality": quality})

    def test_all_dynamic_tags_expand_with_original_line_numbers(self):
        path = self.mapper('''<sql id="column">id</sql>
<select id="find">
SELECT <include refid="demo.column"/> FROM users
<bind name="pattern" value="name"/>
<where>
<if test="id != null">AND id = #{id}</if>
<choose><when test="active">AND active = #{active}</when><otherwise>OR archived = #{archived}</otherwise></choose>
</where>
AND id IN <foreach collection="ids" item="id" open="(" close=")" separator=",">#{id}</foreach>
</select>
<update id="modify">UPDATE users <set><if test="name">name = #{name},</if></set> WHERE id = #{id}</update>
<select id="trim">SELECT id FROM users <trim prefix="WHERE" prefixOverrides="AND |OR " suffixOverrides=",">OR id = #{id},</trim></select>''')
        sources = java._mapper_sql(self.root, path)
        self.assertEqual(len(sources), 4)
        texts = [" ".join(sql.split()) for _, sql, _ in sources]
        self.assertIn("SELECT id FROM users WHERE id = ? AND active = ? AND id IN (?)", texts)
        self.assertIn("SELECT id FROM users WHERE id = ? OR archived = ? AND id IN (?)", texts)
        self.assertIn("UPDATE users SET name = ? WHERE id = ?", texts)
        self.assertIn("SELECT id FROM users WHERE id = ?", texts)
        for _, sql, lines in sources[:2]:
            index = next(i for i, line in enumerate(sql.splitlines()) if "id = ?" in line)
            self.assertEqual(lines[index], 7)

    def test_nested_choices_form_independent_variants(self):
        path = self.mapper('<select id="a">SELECT <choose><when test="a">a</when><otherwise>b</otherwise></choose> FROM <choose><when test="x">x</when><otherwise>y</otherwise></choose></select>')
        self.assertEqual({" ".join(sql.split()) for _, sql, _ in java._mapper_sql(self.root, path)},
                         {"SELECT a FROM x", "SELECT a FROM y", "SELECT b FROM x", "SELECT b FROM y"})

    def test_batch_of_100_statements_runs_once_and_maps_each_file(self):
        self.mapper("\n".join('<select id="s%s">select id from users</select>' % n for n in range(100)))
        values = self.scan([{"code": "CP01", "description": "Upper case", "start_line_no": 1}],
                           "assert sql.strip() == 'select id from users'")
        self.assertEqual(len(values), 100)
        self.assertEqual({v.line for v in values}, set(range(2, 102)))
        self.assertEqual((self.root / "calls.txt").read_text(encoding="utf-8"), "call\n")

    def test_choose_duplicates_once_but_distinct_occurrences_remain(self):
        self.mapper('<select id="a">select <choose><when test="x">id</when><otherwise>name</otherwise></choose> from users</select>\n<select id="b">select id from users</select>')
        values = self.scan([{"code": "CP01", "description": "Upper case", "start_line_no": 1},
                            {"code": "CP01", "description": "Upper case", "start_line_no": 1}])
        self.assertEqual(len(values), 4)

    def test_distinct_choice_branch_locations_on_same_xml_line_count_separately(self):
        self.mapper('<select id="a">SELECT <choose><when test="x">bad1</when><otherwise>bad2</otherwise></choose> FROM users</select>')
        script = "import json,sys; from pathlib import Path; rows=[]\nfor p in sorted(Path(sys.argv[-1]).glob('*.sql')):\n sql=p.read_text(encoding='utf-8'); rows.append({'filepath':str(p),'violations':[{'code':'CP02','description':'Capitalise identifier','start_line_no':1,'start_line_pos':sql.index('bad')+1}]})\nprint(json.dumps(rows))"
        values = java._sql_resources(self.root, [sys.executable, "-c", script], self.environment, 10)
        self.assertEqual(len(values), 2)
        self.assertEqual([v.line for v in values], [2, 2])

    def test_trim_keyword_does_not_glue_to_surrounding_sql(self):
        path = self.mapper('<select id="a">SELECT id FROM users<where>AND id=#{id}</where>ORDER BY id</select>')
        self.assertEqual(" ".join(java._mapper_sql(self.root, path)[0][1].split()),
                         "SELECT id FROM users WHERE id=? ORDER BY id")

    def test_where_removes_connectors_before_newline_or_tab(self):
        for connector in ("AND\n", "AND\t", "OR\n", "OR\t", "and\r\n"):
            with self.subTest(connector=connector):
                path = self.mapper('<select id="a">SELECT id FROM users<where>' + connector + 'id=#{id}</where></select>')
                self.assertEqual(" ".join(java._mapper_sql(self.root, path)[0][1].split()),
                                 "SELECT id FROM users WHERE id=?")

    def test_missing_or_unknown_batch_file_fails_closed_with_log(self):
        self.mapper('<select id="a">SELECT id FROM users</select>')
        for script in ("print('[]')", "print('[{\"filepath\":\"unknown.sql\",\"violations\":[]}]')"):
            with self.subTest(script=script), self.assertRaises(java.JavaError) as caught:
                java._sql_resources(self.root, [sys.executable, "-c", script], self.environment, 10)
            self.assertIn(".openspec/logs/quality-sqlfluff.log", str(caught.exception))

    def test_parse_errors_and_invalid_warning_marker_fail_closed(self):
        self.mapper('<select id="a">SELECT id FROM users</select>')
        for row in ({"code": "PRS", "description": "Unable to parse", "start_line_no": 1},
                    {"code": "CP01", "description": "case", "start_line_no": 1, "warning": "false"},
                    {"code": "CP01", "description": "case", "start_line_no": 99}):
            with self.subTest(row=row), self.assertRaises(java.JavaError):
                self.scan([row])

    def test_end_of_file_rule_location_maps_to_last_source_token(self):
        self.write("src/main/resources/q.sql", "SELECT id;")
        values = self.scan([{"code": "LT12", "description": "Missing trailing newline", "start_line_no": 1, "start_line_pos": 11}])
        self.assertEqual([(v.file, v.line) for v in values], [("src/main/resources/q.sql", 1)])

    def test_dollar_debt_does_not_mask_unexplained_sqlfluff_failure(self):
        self.mapper('<select id="a">SELECT ${column} FROM users</select>')
        with self.assertRaises(java.JavaError):
            self.scan(exitcode=1)

    def test_initialization_surfaces_failure_diagnostics(self):
        quality = self.quality()
        quality["archunit"]["command"] = [sys.executable, "-c", "import sys; print('archunit failed',file=sys.stderr); sys.exit(9)"]
        self.write(".openspec/.config.json", json.dumps({"quality": quality}))
        with patch.object(Project, "here", return_value=Project(self.root)), self.assertRaises(SystemExit) as caught:
            init_config.run(SimpleNamespace(java=True, dry_run=False))
        for value in ("退出码：9", "archunit failed", ".openspec/logs/quality-archunit.log"):
            self.assertIn(value, str(caught.exception))

    def test_dollar_substitution_is_debt_and_other_rules_still_run(self):
        self.mapper('<select id="a">select ${column} from users WHERE id = #{id}</select>')
        values = self.scan([{"code": "CP01", "description": "Upper case", "start_line_no": 1}],
                           "assert '${' not in sql and '#{' not in sql and 'WHERE id = ?' in sql and 'NULL' not in sql")
        self.assertEqual({v.rule for v in values}, {"CP01", "mybatis-dollar-substitution"})
        self.assertEqual({v.line for v in values}, {2})
        self.assertIn("SQL 注入", next(v.message for v in values if v.rule == "mybatis-dollar-substitution"))

    def test_extra_paths_deduplicate_sources_and_reject_escape(self):
        self.mapper('<select id="a">SELECT id FROM users</select>', "custom/mappers/M.xml")
        self.write("custom/schema.sql", "SELECT id FROM users;")
        self.write("src/main/resources/schema.sql", "SELECT id FROM users;")
        self.assertEqual(len(self.scan([{"code": "CP01", "description": "case", "start_line_no": 1}],
                                      paths=["custom", "src/main/resources"])), 3)
        for paths in (["../outside"], [str(self.root.parent)], "custom", ["missing"]):
            with self.subTest(paths=paths), self.assertRaises(java.JavaError):
                self.scan(paths=paths)

    def test_trim_empty_tags_and_case_insensitive_overrides(self):
        path = self.mapper('<select id="a">SELECT id FROM users <where><bind name="x" value="x"/></where></select>\n<update id="b">UPDATE users <set>name=#{name}, </set></update>\n<select id="c">SELECT id FROM users <trim prefix="WHERE" prefixOverrides="AND |OR ">and id=#{id}</trim></select>')
        self.assertEqual([" ".join(sql.split()) for _, sql, _ in java._mapper_sql(self.root, path)],
                         ["SELECT id FROM users", "UPDATE users SET name=?", "SELECT id FROM users WHERE id=?"])

    def test_warning_is_reported_but_does_not_block(self):
        self.write("src/main/resources/q.sql", "SELECT id FROM users;")
        quality = self.quality(self.fake([{"code": "LT05", "description": "Too long", "start_line_no": 1, "warning": True}], exitcode=0))
        ctx = self.context([], quality)
        findings = g6_7.check(ctx)
        self.assertEqual([(f.check, f.level) for f in findings], [("sqlfluff", "WARN")])
        report = (ctx.change_dir / "static-analysis-report.md").read_text(encoding="utf-8")
        self.assertIn("[WARN] Too long", report)
        self.assertIn("| 0 | 0 | 0 |", report)
        quality["sqlfluff"]["command"] = self.fake([{"code": "CP01", "description": "Upper case", "start_line_no": 1}])
        self.assertEqual([(f.check, f.level) for f in g6_7.check(ctx)], [("sqlfluff", "BLOCK")])

    def test_duplicate_baseline_records_preserve_counts(self):
        issue = java.Violation("pmd", "Unused", "A.java", 1, "unused")
        path = self.write("baseline.json", json.dumps({"version": 1, "violations": [issue.to_dict(), issue.to_dict()]}))
        self.assertEqual(len(java.load_baseline(path)), 2)

    def test_new_and_repaid_counts_apply_to_every_check(self):
        for name in java.CHECKS:
            with self.subTest(check=name):
                baseline = [java.Violation(name, "Rule", "A.java", 1, "same")]
                current = [java.Violation(name, "Rule", "A.java", n, "same") for n in (10, 20)]
                ctx = self.context(baseline, self.quality())
                with patch.object(java, "run_quality", return_value=(current, {})):
                    findings = g6_7.check(ctx)
                self.assertEqual([(f.check, f.level) for f in findings], [(name, "BLOCK")])
                report = (ctx.change_dir / "static-analysis-report.md").read_text(encoding="utf-8")
                self.assertIn("| 1 | 1 | 0 |", report)
                self.context(current, self.quality())
                with patch.object(java, "run_quality", return_value=(baseline, {})):
                    self.assertEqual(g6_7.check(ctx), [])
                self.assertIn("| 0 | 1 | 1 |", (ctx.change_dir / "static-analysis-report.md").read_text(encoding="utf-8"))
                with patch.object(java, "run_quality", return_value=([], {name: "failed"})):
                    g6_7.check(ctx)
                self.assertIn("| 0 | 0 | 0 |", (ctx.change_dir / "static-analysis-report.md").read_text(encoding="utf-8"))

    def test_run_quality_does_not_collapse_identical_xml_violations(self):
        quality = self.quality()
        filename = "reports/pmd.xml"
        content = '<pmd><file name="A.java"><violation rule="Unused" beginline="1">unused</violation><violation rule="Unused" beginline="2">unused</violation></file></pmd>'
        quality["pmd"]["command"] = [sys.executable, "-c", "from pathlib import Path; p=Path(%r); p.parent.mkdir(parents=True,exist_ok=True); p.write_text(%r,encoding='utf-8')" % (filename, content)]
        values, errors = java.run_quality(self.root, quality)
        self.assertEqual(errors, {})
        self.assertEqual([v.line for v in values], [1, 2])

    def test_reinitialization_preserves_counts_and_refuses_more_debt(self):
        issue = java.Violation("pmd", "Unused", "A.java", 1, "unused")
        args = SimpleNamespace(java=True, dry_run=False)
        with patch.object(Project, "here", return_value=Project(self.root)), patch.object(java, "run_quality", return_value=([issue, issue], {})), contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(init_config.run(args), 0)
        baseline = Project(self.root).quality_baseline
        self.assertEqual(len(java.load_baseline(baseline)), 2)
        before = baseline.read_bytes()
        with patch.object(Project, "here", return_value=Project(self.root)), patch.object(java, "run_quality", return_value=([issue] * 3, {})), contextlib.redirect_stderr(io.StringIO()), self.assertRaises(SystemExit):
            init_config.run(args)
        self.assertEqual(baseline.read_bytes(), before)

    def test_command_failure_contains_full_command_exit_stderr_and_log(self):
        quality = self.quality()
        script = "import sys; print('full stdout'); [print('stderr-%s'%n,file=sys.stderr) for n in range(20)]; sys.exit(7)"
        command = [sys.executable, "-c", script, "argument with spaces"]
        quality["pmd"]["command"] = command
        _, errors = java.run_quality(self.root, quality)
        error = errors["pmd"]
        displayed = error.split("完整命令：", 1)[1].split("；退出码：", 1)[0]
        self.assertEqual(shlex.split(displayed), command)
        for value in ("7", "stderr-19", ".openspec/logs/quality-pmd.log"):
            self.assertIn(value, error)
        log = (self.root / ".openspec/logs/quality-pmd.log").read_text(encoding="utf-8")
        self.assertIn("full stdout", log)
        self.assertIn("stderr-0\n", log)
        self.assertIn("stderr-19", log)

    def test_failed_start_and_timeout_keep_diagnostics(self):
        quality = self.quality()
        quality["pmd"]["command"] = [str(self.root / "missing-command")]
        _, errors = java.run_quality(self.root, quality)
        self.assertIn(".openspec/logs/quality-pmd.log", errors["pmd"])
        quality["pmd"]["command"] = [sys.executable, "-c", "import sys,time; print('before timeout',flush=True); print('timeout stderr',file=sys.stderr,flush=True); time.sleep(5)"]
        quality["pmd"]["timeout"] = 0.1
        _, errors = java.run_quality(self.root, quality)
        self.assertIn("超时", errors["pmd"])
        tail = errors["pmd"].split("stderr 最后 10 行：", 1)[1].split("日志：", 1)[0]
        self.assertIn("timeout stderr", tail)
        self.assertIn("before timeout", (self.root / ".openspec/logs/quality-pmd.log").read_text(encoding="utf-8"))

    def test_archunit_accepts_dotted_keys_and_rejects_legacy_true(self):
        quality = self.quality()
        script = quality["archunit"]["command"][-1]
        quality["archunit"]["command"][-1] = "import os; assert '-Darchunit.freeze.store.default.allowStoreCreation=false' in os.environ['JAVA_TOOL_OPTIONS']; " + script
        self.assertEqual(java.run_quality(self.root, quality)[1], {})
        for key in ("archunit.freeze.refreeze", "archunit_freeze.refreeze", "archunit_freeze.store.default.allowStoreUpdate"):
            with self.subTest(key=key):
                bad = self.quality()
                bad["archunit"]["command"].append("-D%s=true" % key)
                self.assertIn("archunit", java.run_quality(self.root, bad)[1])

    def test_sql_paths_default_is_empty(self):
        self.assertEqual(config.DEFAULTS["quality"]["sqlfluff"]["paths"], [])

    @unittest.skipUnless(shutil.which("sqlfluff"), "未安装 SQLFluff，跳过真实集成测试")
    def test_real_sqlfluff_placeholder_and_warning(self):
        template = Path(__file__).resolve().parents[1] / "reinsdev-plugin/skills/spec-driven-dev/templates/quality/sqlfluff.template"
        self.write(".sqlfluff", template.read_text(encoding="utf-8").replace("<dialect>", "mysql"))
        self.mapper('<select id="a">SELECT id FROM users WHERE id = #{id}</select>')
        values = java._sql_resources(self.root, [shutil.which("sqlfluff"), "lint", "--format", "json", "-"], self.environment, 30)
        self.assertFalse(any(v.rule in ("PRS", "TMP", "LXR", "CV05") for v in values))
        self.mapper('<select id="a">SELECT id FROM users WHERE ' + ' OR '.join(['id = #{id}'] * 30) + '</select>')
        values = java._sql_resources(self.root, [shutil.which("sqlfluff"), "lint", "--format", "json", "-"], self.environment, 30)
        self.assertTrue(any(v.rule == "LT05" and v.warning for v in values))


if __name__ == "__main__":
    unittest.main()
