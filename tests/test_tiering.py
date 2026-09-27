import tempfile
import unittest
from pathlib import Path

from tests import CLI_LIB  # noqa: F401
from spec_driven import tiering


class TieringTest(unittest.TestCase):
    def test_small_change_is_s(self):
        tier, points, reasons = tiering.score_text("修改提示文案。AC-1 显示新文案")
        self.assertEqual((tier, points), ("S", 0))
        self.assertTrue(reasons)

    def test_interface_and_table_is_m(self):
        tier, _, reasons = tiering.score_text("新增接口 POST /x，新增表 t_x。AC-1 AC-2")
        self.assertEqual(tier, "M")
        self.assertEqual(len(reasons), 2)

    def test_cross_service_many_acs_is_l(self):
        text = "跨服务调用，通过 MQ 通知。" + " ".join("AC-%d" % i for i in range(1, 9))
        self.assertEqual(tiering.score_text(text)[0], "L")

    def test_files_counted_once(self):
        paths = " ".join(["src/main/java/a/F%d.java" % i for i in range(3)] * 2)
        self.assertIn("影响 ≥3 个文件（3 个）", tiering.score_text(paths)[2])

    def test_recommend_reads_phase_sources(self):
        with tempfile.TemporaryDirectory() as tmp:
            d = Path(tmp)
            (d / "proposal.md").write_text("AC-1", encoding="utf-8")
            (d / "design.md").write_text("跨服务 分布式事务", encoding="utf-8")
            self.assertEqual(tiering.recommend(d, "1")[0], "S")
            self.assertEqual(tiering.recommend(d, "2")[0], "M")


if __name__ == "__main__":
    unittest.main()
