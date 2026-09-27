import tempfile
import unittest
from pathlib import Path

from tests import CLI_LIB  # noqa: F401
from spec_driven import retro


class RetroTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self.tmp.name) / "demo-change"
        self.dir.mkdir()

    def tearDown(self):
        self.tmp.cleanup()

    def test_empty(self):
        self.assertEqual((retro.waivers(self.dir), retro.todos(self.dir)), ([], []))
        self.assertTrue(retro.verify(self.dir))

    def test_tables_coexist_and_round_trip(self):
        w = retro.Waiver("2026-09-26 14:02", "6", "coverage", "增量覆盖率 62% | T5", "遗留 DAO\n无法 mock", "ronnie", "3fa1c09e")
        retro.append_waiver(self.dir, w)
        retro.append_tier_change(self.dir, "1", "M → M", "选定", "推荐档，用户确认", "ronnie")
        retro.add_todo(self.dir, "code-review WARN", "拆分 OrderService")
        retro.append_waiver(self.dir, retro.Waiver("t", "6.7", "pmd", "c", "r", "me", "aa"))
        retro.add_todo(self.dir, "manual", "补文档")
        got = retro.waivers(self.dir)
        self.assertEqual(len(got), 2)
        self.assertEqual(got[0].content, "增量覆盖率 62% | T5")
        self.assertEqual(got[0].reason, "遗留 DAO 无法 mock")
        self.assertEqual(retro.todos(self.dir), ["拆分 OrderService", "补文档"])
        text = (self.dir / "retrospective.md").read_text(encoding="utf-8")
        self.assertTrue(text.startswith("# Retrospective: demo-change"))
        self.assertEqual(text.count("## 人工确认记录"), 1)
        self.assertIn("| 选定 |", text)

    def test_signature_detects_manual_edits(self):
        retro.add_todo(self.dir, "manual", "x")
        self.assertTrue(retro.verify(self.dir))
        path = self.dir / "retrospective.md"
        path.write_text(path.read_text(encoding="utf-8") + "| 伪造 |\n", encoding="utf-8")
        self.assertFalse(retro.verify(self.dir))
        self.assertTrue(retro.verify(self.dir, path.read_text(encoding="utf-8").replace("| 伪造 |\n", "")))

    def test_crlf_signature(self):
        retro.add_todo(self.dir, "manual", "x")
        text = (self.dir / "retrospective.md").read_text(encoding="utf-8")
        self.assertTrue(retro.verify(self.dir, text.replace("\n", "\r\n")))


if __name__ == "__main__":
    unittest.main()
