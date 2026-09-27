"""Markdown contracts used by artifact gates."""

import unittest
from pathlib import Path

from tests import PLUGIN
from spec_driven import mdparse


class SectionsTest(unittest.TestCase):
    def test_nested_sections_keep_preamble_bodies_and_source_lines(self):
        source = "前言\n# 文档\n正文\n### 子节\n细节\n#### 末节\n末尾\n## 同级\n结束"
        root = mdparse.parse(source)
        self.assertEqual((root.title, root.level, root.line, root.body), ("", 0, 0, "前言\n"))
        doc = root.children[0]
        self.assertEqual((doc.title, doc.level, doc.line, doc.body), ("文档", 1, 2, "正文\n"))
        self.assertEqual([(s.title, s.line) for s in doc.children], [("子节", 4), ("同级", 8)])
        self.assertEqual(doc.children[0].children[0].level, 4)
        self.assertEqual(doc.children[0].text(), "细节\n#### 末节\n末尾\n")
        self.assertEqual(root.text(), source)

    def test_text_preserves_heading_spelling_and_crlf(self):
        source = "# 文档\r\n正文\r\n  ##  一、用户故事  ##  \r\n故事\r\n### 子节\r\n末尾"
        root = mdparse.parse(source)
        story = mdparse.find(root, "user-stories")
        self.assertEqual((story.title, story.line, story.body), ("一、用户故事", 3, "故事\r\n"))
        self.assertEqual(root.text(), source)
        self.assertEqual(story.text(), "故事\r\n### 子节\r\n末尾")

    def test_atx_only_and_six_levels(self):
        source = "#Title\n####### too deep\n    # indented\nSetext\n======\n######\n"
        root = mdparse.parse(source)
        self.assertEqual(len(root.children), 1)
        self.assertEqual((root.children[0].title, root.children[0].level, root.children[0].line), ("", 6, 6))
        self.assertIn("Setext", root.body)

    def test_empty_and_heading_only_documents(self):
        for source in ("", "plain", "#", "# 文档", "# 文档\n", "# 文档\n## 子节"):
            with self.subTest(source=source):
                self.assertEqual(mdparse.parse(source).text(), source)

    def test_repeated_headings_and_regex_search_follow_source_order(self):
        root = mdparse.parse("# 用户故事\n## 用户故事\n# 用户故事\n## REQ-x-001: 功能\n### SC-x-E2: 异常\n")
        self.assertEqual(mdparse.find(root, "user-stories").line, 1)
        self.assertEqual([s.line for s in mdparse.find_all(root, "用户故事")], [1, 2, 3])
        self.assertEqual([s.line for s in mdparse.find_all(root, mdparse.ID_PATTERNS["SC"])], [5])
        self.assertEqual(mdparse.find_all(root, "missing"), [])
        self.assertIsNone(mdparse.find(root, "out-of-scope"))

    def test_aliases_ignore_numbering_case_and_surrounding_spaces(self):
        for title in ("一、范围外", "1. Out of Scope", "1.2 OUT OF SCOPE", "（二）范围外", "2、范围外", "  out of scope  "):
            with self.subTest(title=title):
                section = mdparse.find(mdparse.parse("## %s\n正文" % title), "out-of-scope")
                self.assertIsNotNone(section)
                self.assertEqual(section.body, "正文")
        self.assertIsNone(mdparse.find(mdparse.parse("# Out of Scope 附加说明"), "out-of-scope"))

    def test_unknown_alias_is_not_a_literal_heading_fallback(self):
        self.assertIsNone(mdparse.find(mdparse.parse("# unknown-key"), "unknown-key"))

    def test_manually_constructed_section_text_includes_descendants(self):
        child = mdparse.Section("子节", 2, 2, "正文")
        root = mdparse.Section("", 0, 0, "前言\n", [child])
        self.assertEqual(root.text(), "前言\n## 子节\n正文")


class FencesTest(unittest.TestCase):
    def test_fenced_examples_are_not_artifact_content(self):
        source = ("# 真标题\n````markdown\n## 假标题\nAC-99\n- [x] T99\n"
                  "| a |\n| --- |\n| 假 |\n```\n~~~\n# 仍在代码块\n````\n"
                  "## 后续\nAC-1\n- [ ] T1\n")
        root = mdparse.parse(source)
        self.assertEqual([s.title for s in mdparse.find_all(root, ".+")], ["真标题", "后续"])
        self.assertEqual(mdparse.ids(source, "AC"), ["AC-1"])
        self.assertEqual([(c.line, c.text) for c in mdparse.checkboxes(source)], [(15, "T1")])
        self.assertEqual(mdparse.tables(source), [])
        self.assertEqual(root.text(), source)

    def test_tilde_fences_indentation_and_longer_closers(self):
        source = "   ~~~ text\n# 假标题\nAC-9\n    ~~~\nAC-8\n   ~~~~~  \n# 真标题\nAC-1"
        self.assertEqual(mdparse.ids(source, "AC"), ["AC-1"])
        self.assertEqual([s.line for s in mdparse.find_all(mdparse.parse(source), ".+")], [7])

    def test_unclosed_fence_hides_rest_of_document(self):
        source = "AC-1\n```\nAC-2\n## 假标题\n``` trailing text\nAC-3"
        self.assertEqual(mdparse.ids(source, "AC"), ["AC-1"])
        self.assertEqual(mdparse.parse(source).children, [])

    def test_backticks_in_info_string_do_not_open_fence(self):
        self.assertEqual(mdparse.ids("```bad`info\nAC-1", "AC"), ["AC-1"])

    def test_list_fence_fixture_keeps_real_content_after_closer(self):
        source = (Path(__file__).parent / "fixtures" / "t1" / "list-fence.md").read_text(encoding="utf-8")
        self.assertEqual(mdparse.ids(source, "AC"), ["AC-1"])
        root = mdparse.parse(source)
        self.assertEqual(mdparse.find(root, "user-stories").line, 11)
        self.assertEqual(root.text(), source)
        self.assertEqual([(c.line, c.text) for c in mdparse.checkboxes(source)], [(13, "T1")])
        table, = mdparse.tables(source)
        self.assertEqual((table.line, table.rows), (15, [{"字段": "实际"}]))

    def test_bullet_and_ordered_list_fences(self):
        for marker in ("-", "+", "*", "1.", "12)"):
            with self.subTest(marker=marker):
                indent = " " * (len(marker) + 1)
                source = "%s ~~~\n%sAC-99\n%s~~~\nAC-1\n" % (marker, indent, indent)
                self.assertEqual(mdparse.ids(source, "AC"), ["AC-1"])

    def test_fence_in_list_continuation_can_have_four_spaces(self):
        source = "- 示例\n\n    ```\n    AC-99\n    - [x] T99\n    | a |\n    | --- |\n    ```\n\nAC-1\n"
        self.assertEqual(mdparse.ids(source, "AC"), ["AC-1"])
        self.assertEqual(mdparse.checkboxes(source), [])
        self.assertEqual(mdparse.tables(source), [])

    def test_blockquote_and_nested_quote_list_fences(self):
        for opening, prefix in (("> ```", "> "), ("> > ```", "> > "),
                                ("> - ```", ">   "), ("- > ```", "  > ")):
            with self.subTest(opening=opening):
                source = "%s\n%sAC-99\n%s```\nAC-1\n## 用户故事\n正文" % (opening, prefix, prefix)
                self.assertEqual(mdparse.ids(source, "AC"), ["AC-1"])
                self.assertIsNotNone(mdparse.find(mdparse.parse(source), "user-stories"))

    def test_unclosed_container_fences_end_with_their_container(self):
        for opening, prefix in (("> ```", "> "), ("- ```", "  ")):
            with self.subTest(opening=opening):
                source = "%s\n%sAC-99\n# 用户故事\nAC-1" % (opening, prefix)
                self.assertEqual(mdparse.ids(source, "AC"), ["AC-1"])
                self.assertIsNotNone(mdparse.find(mdparse.parse(source), "user-stories"))


class IdsTest(unittest.TestCase):
    def test_distinct_ids_keep_first_appearance_order(self):
        cases = [
            ("AC", "AC-2 AC-1 AC-2", ["AC-2", "AC-1"]),
            ("REQ", "REQ-order-api-002 REQ-x-001 REQ-order-api-002", ["REQ-order-api-002", "REQ-x-001"]),
            ("SC", "SC-x-E2 SC-x-001 SC-x-E12 SC-x-E2", ["SC-x-E2", "SC-x-001", "SC-x-E12"]),
            ("TASK", "T3 T-regression T1 T3", ["T3", "T-regression", "T1"]),
        ]
        for kind, source, expected in cases:
            with self.subTest(kind=kind):
                self.assertEqual(mdparse.ids(source, kind), expected)
                self.assertEqual(mdparse.ids("", kind), [])

    def test_ids_do_not_match_inside_words(self):
        source = "XAC-1 AC-2suffix ac-3 AC-4 _AC-5"
        self.assertEqual(mdparse.ids(source, "AC"), ["AC-4"])
        self.assertEqual(mdparse.ids("SC-x-12 SC-X-001 SC-x-0001 SC-x-E2", "SC"), ["SC-x-E2"])

    def test_unknown_kind_is_a_programming_error(self):
        with self.assertRaises(KeyError):
            mdparse.ids("AC-1", "unknown")


class TablesTest(unittest.TestCase):
    def test_pipe_tables_keep_line_headers_rows_and_escaped_pipes(self):
        source = "前言\r\n| 字段 | 值 |\r\n| :--- | ---: |\r\n| 名称 | a\\|b |\r\n| 空 | |\r\n"
        table, = mdparse.tables(source)
        self.assertEqual((table.line, table.header), (2, ["字段", "值"]))
        self.assertEqual(table.rows, [{"字段": "名称", "值": "a\\|b"}, {"字段": "空", "值": ""}])

    def test_empty_tables_and_optional_outer_pipes(self):
        source = "a | b\n--- | ---\n\n| 独列 |\n| --- |\n| 一行 |\n"
        first, second = mdparse.tables(source)
        self.assertEqual((first.line, first.rows), (1, []))
        self.assertEqual(second.rows, [{"独列": "一行"}])

    def test_separator_is_required_and_must_match_header_width(self):
        for source in ("| a | b |\n| value | row |", "a | b\n--- | nope", "a | b\n---", "| a |\n| - |"):
            with self.subTest(source=source):
                self.assertEqual(mdparse.tables(source), [])

    def test_short_rows_are_padded_and_extra_cells_ignored(self):
        table, = mdparse.tables("a | b\n--- | ---\nx |\ny | z | extra\n")
        self.assertEqual(table.rows, [{"a": "x", "b": ""}, {"a": "y", "b": "z"}])

    def test_even_backslashes_do_not_escape_cell_delimiter(self):
        table, = mdparse.tables("a | b\n--- | ---\nleft\\\\| right\n")
        self.assertEqual(table.rows, [{"a": "left\\\\", "b": "right"}])

    def test_table_stops_at_non_table_content_and_fence(self):
        source = "| a |\n| --- |\n| one |\n## 标题 | 文本\n```\n| hidden |\n```\n"
        table, = mdparse.tables(source)
        self.assertEqual(table.rows, [{"a": "one"}])


class CheckboxesTest(unittest.TestCase):
    def test_three_states_and_uppercase_x_with_source_lines(self):
        source = "# 任务\r\n- [ ] T1\r\n  - [x] T2\r\n- [X] T3\r\n- [~] T4\r\n- [ ]\r\n"
        self.assertEqual([(c.line, c.state, c.text) for c in mdparse.checkboxes(source)],
                         [(2, " ", "T1"), (3, "x", "T2"), (4, "x", "T3"), (5, "~", "T4"), (6, " ", "")])

    def test_non_checkbox_text_is_ignored(self):
        source = "text - [ ] T1\n- [] T2\n- [v] T3\n- [xx] T4\n- [x]no-space\n"
        self.assertEqual(mdparse.checkboxes(source), [])


TEMPLATES = Path(PLUGIN) / "skills" / "spec-driven-dev" / "templates"
TEMPLATE_KEYS = {
    "proposal.md": ["user-stories", "acceptance-criteria", "out-of-scope", "ambiguities",
                    "dependencies", "field-mapping", "non-functional", "affected-modules"],
    "proposal-bugfix.md": ["user-stories", "acceptance-criteria", "out-of-scope", "ambiguities",
                           "dependencies", "field-mapping", "non-functional", "affected-modules"],
    "bugfix-analysis.md": ["basic-info", "evidence", "root-cause", "fix-plan", "change-points",
                           "impact", "complexity-assessment"],
    "design.md": ["background", "current-system", "alternatives", "final-choice", "detailed-design",
                  "risks", "stress-test", "implementation-plan"],
    "spec.md": ["interface-contract", "data-model", "table-structure", "indexes", "constraints", "migrations"],
    "tasks.md": ["foundation", "domain-layer", "application-layer", "adapter-layer", "test-layer"],
    "implementation-log.md": ["change-scope", "red", "green", "refactor", "build", "coverage", "commits"],
    "deploy-report.md": ["deployment-info", "startup-result", "deployment-errors", "manual-acceptance", "conclusion"],
}


class TemplatesTest(unittest.TestCase):
    def test_required_sections_are_findable_in_each_template(self):
        for filename, keys in TEMPLATE_KEYS.items():
            with self.subTest(filename=filename):
                source = (TEMPLATES / filename).read_text(encoding="utf-8")
                root = mdparse.parse(source)
                self.assertEqual(root.text(), source)
                for key in keys:
                    section = mdparse.find(root, key)
                    self.assertIsNotNone(section, (filename, key))
                    self.assertEqual(section.title, mdparse.ALIASES[key][0])

    def test_all_aliases_resolve_to_real_template_headings(self):
        found = set()
        for filename in TEMPLATE_KEYS:
            root = mdparse.parse((TEMPLATES / filename).read_text(encoding="utf-8"))
            found.update(key for key in mdparse.ALIASES if mdparse.find(root, key) is not None)
        self.assertEqual(found, set(mdparse.ALIASES))
        for key, variants in mdparse.ALIASES.items():
            for title in variants:
                with self.subTest(key=key, title=title):
                    self.assertIsNotNone(mdparse.find(mdparse.parse("## %s\n正文" % title.upper()), key))

    def test_proposal_tables_expose_gate_fields_without_fabricated_answers(self):
        for filename in ("proposal.md", "proposal-bugfix.md"):
            root = mdparse.parse((TEMPLATES / filename).read_text(encoding="utf-8"))
            for key, headers in (("ambiguities", ["问题", "影响范围", "类型", "回答", "来源", "状态"]),
                                 ("field-mapping", ["源字段", "目标字段", "转换规则或固定值", "来源"]),
                                 ("acceptance-criteria", ["AC", "用户故事", "验收标准", "验证步骤"])):
                with self.subTest(filename=filename, key=key):
                    table, = mdparse.tables(mdparse.find(root, key).text())
                    self.assertEqual(table.header, headers)
                    for row in table.rows:
                        if "来源" in row:
                            self.assertTrue(row["来源"].startswith("<"))

    def test_rendered_spec_keeps_req_scenario_hierarchy_and_ac_links(self):
        source = (TEMPLATES / "spec.md").read_text(encoding="utf-8")
        source = source.replace("<capability>", "orders").replace("<NNN>", "001").replace("<E编号>", "E2")
        source = source.replace("<AC 编号>", "AC-1")
        root = mdparse.parse(source)
        req, = mdparse.find_all(root, mdparse.ID_PATTERNS["REQ"])
        scenarios = mdparse.find_all(req, mdparse.ID_PATTERNS["SC"])
        self.assertEqual(req.level, 2)
        self.assertEqual([s.level for s in scenarios], [3, 3])
        self.assertEqual(mdparse.ids(source, "SC"), ["SC-orders-001", "SC-orders-E2"])
        for scenario in scenarios:
            self.assertIn("WHEN ", scenario.body)
            self.assertIn("THEN ", scenario.body)
            self.assertEqual(mdparse.ids(scenario.body, "AC"), ["AC-1"])

    def test_task_layers_have_unchecked_tasks_and_regression_task(self):
        root = mdparse.parse((TEMPLATES / "tasks.md").read_text(encoding="utf-8"))
        self.assertEqual([section.title for section in root.children[0].children],
                         ["Foundation(底层依赖,必须先做)", "Domain Layer", "Application Layer", "Adapter Layer", "Test"])
        for key in TEMPLATE_KEYS["tasks.md"]:
            tasks = mdparse.checkboxes(mdparse.find(root, key).text())
            self.assertTrue(tasks, key)
            self.assertTrue(all(task.state == " " for task in tasks))
        self.assertIn("T-regression", mdparse.ids(root.text(), "TASK"))

    def test_alias_index_maps_every_key_to_existing_template_titles(self):
        doc = (Path(__file__).resolve().parents[1] / "docs" / "dev" / "tasks.md").read_text(encoding="utf-8")
        section, = mdparse.find_all(mdparse.parse(doc), "^别名索引$")
        index, = mdparse.tables(section.text())
        self.assertEqual({row["ALIASES 键"] for row in index.rows}, set(mdparse.ALIASES))
        for row in index.rows:
            for filename in row["模板文件"].split("、"):
                root = mdparse.parse((TEMPLATES / filename).read_text(encoding="utf-8"))
                self.assertEqual(mdparse.find(root, row["ALIASES 键"]).title, row["模板标题"])


if __name__ == "__main__":
    unittest.main()
