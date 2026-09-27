import json
import os
import tempfile
import time
import unittest
from pathlib import Path
from unittest import mock

from tests import CLI_LIB  # noqa: F401
from spec_driven import grants


class PhraseTest(unittest.TestCase):
    def test_matches_only_whole_phrase(self):
        self.assertEqual(grants.match_phrase("  确认放行 demo-change 6 coverage \n"),
                         {"action": "waive", "change": "demo-change", "gate": "6", "check": "coverage"})
        self.assertEqual(grants.match_phrase("确认放行　demo-change 6.7 pmd")["gate"], "6.7")
        self.assertEqual(grants.match_phrase("确认降档 demo-change S"),
                         {"action": "downgrade", "change": "demo-change", "tier": "S"})
        for text in ("放行", "可以，确认放行 demo-change 6 coverage", "确认放行 demo-change 6",
                     "确认放行 demo-change 6 coverage 吧", "确认降档 demo-change s", "确认降档 demo-change XL", "", None):
            self.assertIsNone(grants.match_phrase(text), text)


class GrantTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.env = mock.patch.dict(os.environ, {"REINS_HOME": self.tmp.name})
        self.env.start()
        self.root = Path(self.tmp.name) / "proj"
        self.root.mkdir()

    def tearDown(self):
        self.env.stop()
        self.tmp.cleanup()

    def test_consume_once(self):
        grants.issue(self.root, "c", "waive", "6 coverage", "aa,bb")
        self.assertTrue(grants.consume(self.root, "c", "waive", "6 coverage", "aa,bb"))
        self.assertFalse(grants.consume(self.root, "c", "waive", "6 coverage", "aa,bb"))

    def test_mismatches_refused(self):
        cases = [(Path(self.tmp.name), "c", "waive", "6 coverage", "aa"),
                 (self.root, "other", "waive", "6 coverage", "aa"),
                 (self.root, "c", "waive", "6 pmd", "aa"),
                 (self.root, "c", "downgrade", "6 coverage", "aa")]
        for args in cases:
            grants.issue(self.root, "c", "waive", "6 coverage", "aa")
            self.assertFalse(grants.consume(*args), args)
        grants.issue(self.root, "c", "waive", "6 coverage", "aa")
        self.assertFalse(grants.consume(self.root, "c", "waive", "6 coverage", "bb"))  # content changed

    def test_expired_and_tampered(self):
        path = grants.issue(self.root, "c", "downgrade", "S", "")
        data = json.loads(path.read_text(encoding="utf-8"))
        data["expiresAt"] = time.time() - 1
        path.write_text(json.dumps(data), encoding="utf-8")
        self.assertFalse(grants.consume(self.root, "c", "downgrade", "S", ""))
        path = grants.issue(self.root, "c", "downgrade", "S", "")
        path.write_text("{", encoding="utf-8")
        self.assertFalse(grants.consume(self.root, "c", "downgrade", "S", ""))
        self.assertEqual(list(grants.grants_dir().iterdir()), [])


if __name__ == "__main__":
    unittest.main()
