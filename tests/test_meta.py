import json
import multiprocessing
import os
import tempfile
import time
import unittest
from pathlib import Path
from unittest import mock

from tests import CLI_LIB  # noqa: F401
from spec_driven import meta


def _bump(change_dir, n):
    from spec_driven import meta as m
    for _ in range(n):
        m.update(Path(change_dir), lambda d: d.__setitem__("counter", d.get("counter", 0) + 1))


class MetaTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self.tmp.name)
        with meta.lock(self.dir):
            meta.save(self.dir, meta.new("demo-change", "feature", "feat/demo-change", "abc"))

    def tearDown(self):
        self.tmp.cleanup()

    def test_new_matches_schema(self):
        m = meta.load(self.dir)
        self.assertEqual((m["complexity"], m["tierConfirmed"], m["phase"]), ("M", False, "0"))
        self.assertEqual(m["phaseStatus"]["0"], "in_progress")
        self.assertTrue(all(m["phaseStatus"][p] == "pending" for p in meta.PHASES[1:]))
        self.assertEqual(list(json.loads((self.dir / ".meta.json").read_text(encoding="utf-8")))[:3],
                         ["change", "mode", "source"])

    def test_invalid_values_rejected(self):
        for key, value in (("mode", "hotfix"), ("complexity", "XL"), ("phase", "10")):
            m = meta.new("demo-change", "feature", "b", "c")
            m[key] = value
            with self.assertRaises(ValueError):
                meta.validate(m)
        m = meta.new("demo-change", "feature", "b", "c")
        m["phaseStatus"]["3"] = "done"
        with self.assertRaises(ValueError):
            meta.validate(m)

    def test_load_reports_missing_and_broken(self):
        with tempfile.TemporaryDirectory() as other, self.assertRaises(SystemExit):
            meta.load(Path(other))
        (self.dir / ".meta.json").write_text("{", encoding="utf-8")
        with self.assertRaises(SystemExit):
            meta.load(self.dir)

    def test_update_refuses_invalid_result_and_keeps_file(self):
        with self.assertRaises(SystemExit):
            meta.update(self.dir, lambda d: d.__setitem__("phase", "x"))
        self.assertEqual(meta.load(self.dir)["phase"], "0")
        self.assertFalse((self.dir / meta.LOCK_FILE).exists())

    def test_concurrent_updates_do_not_lose_writes(self):
        ctx = multiprocessing.get_context("spawn")
        procs = [ctx.Process(target=_bump, args=(str(self.dir), 25)) for _ in range(3)]
        for p in procs:
            p.start()
        for p in procs:
            p.join(60)
        self.assertEqual(meta.load(self.dir)["counter"], 75)

    def test_stale_lock_is_cleaned(self):
        lock = self.dir / meta.LOCK_FILE
        lock.write_text("1", encoding="utf-8")
        old = time.time() - meta.LOCK_STALE - 5
        os.utime(str(lock), (old, old))
        meta.update(self.dir, lambda d: None)
        self.assertFalse(lock.exists())

    def test_busy_lock_times_out(self):
        (self.dir / meta.LOCK_FILE).write_text("1", encoding="utf-8")
        with mock.patch.object(meta, "LOCK_TIMEOUT", 0.2), self.assertRaises(SystemExit):
            meta.update(self.dir, lambda d: None)


if __name__ == "__main__":
    unittest.main()
