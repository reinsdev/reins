"""T15: quality runs are serialized per project and the gate 6.7 report is replaced atomically."""

import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import threading
import time
from types import SimpleNamespace
import unittest
from unittest import mock

from tests import CLI_LIB
from spec_driven import java
from spec_driven.commands import init_config
from spec_driven.gates import GateContext, g6_7
from spec_driven.project import Project

# Logs start/end around a sleep, then writes a clean ArchUnit report.
SLEEPER = """
import sys, time
from pathlib import Path
log = Path(sys.argv[1])
with log.open("a", encoding="utf-8") as handle:
    handle.write("start %r\\n" % time.time())
time.sleep(float(sys.argv[2]))
with log.open("a", encoding="utf-8") as handle:
    handle.write("end %r\\n" % time.time())
report = Path("reports/archunit-%s.xml" % sys.argv[3])
report.parent.mkdir(parents=True, exist_ok=True)
report.write_text('<testsuite tests="1" failures="0" errors="0"><testcase name="t"/></testsuite>', encoding="utf-8")
"""

RUNNER = """
import json, sys
sys.path.insert(0, sys.argv[1])
from pathlib import Path
from spec_driven import java
quality = json.loads(sys.argv[3])
violations, errors = java.run_quality(Path(sys.argv[2]), quality)
print(json.dumps(errors, ensure_ascii=False))
"""

CRASHER = """
import os, sys
sys.path.insert(0, sys.argv[1])
from pathlib import Path
from spec_driven import java
java.LOCK_MARGIN = float(sys.argv[3])
with java.quality_lock(Path(sys.argv[2]), {}):
    os._exit(1)
"""


class QualityLockTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        (self.root / ".openspec").mkdir()
        self.lock = self.root / ".openspec" / java.QUALITY_LOCK
        self.env = mock.patch.dict(os.environ, {"REINS_HOME": str(self.root / "reins-home")})
        self.env.start()
        self.addCleanup(self.env.stop)

    def quality(self, name, sleep=0.0, timeout=10):
        command = [sys.executable, "-c", SLEEPER, str(self.root / "runs.log"), str(sleep), name]
        return {"archunit": {"command": command, "report_path": "reports/archunit-%s.xml" % name, "timeout": timeout}}

    def foreign(self, expires):
        self.lock.write_text(json.dumps({"token": "other", "pid": 1, "expires": expires}), encoding="utf-8")

    def test_two_processes_run_quality_serially(self):
        processes = [subprocess.Popen([sys.executable, "-c", RUNNER, CLI_LIB, str(self.root),
                                       json.dumps(self.quality(name, 1.0))],
                                      stdout=subprocess.PIPE, stderr=subprocess.PIPE, encoding="utf-8")
                     for name in ("a", "b")]
        for process in processes:
            out, err = process.communicate(timeout=60)
            self.assertEqual(0, process.returncode, err)
            self.assertNotIn("archunit", json.loads(out.strip().splitlines()[-1]))
        events = [line.split() for line in (self.root / "runs.log").read_text(encoding="utf-8").splitlines()]
        self.assertEqual(["start", "end", "start", "end"], [kind for kind, _ in events])
        self.assertLessEqual(float(events[1][1]), float(events[2][1]))
        self.assertFalse(self.lock.exists())

    def test_wait_timeout_raises_and_keeps_foreign_lock(self):
        self.foreign(time.time() + 3600)
        with mock.patch.object(java, "LOCK_MARGIN", 0.3), mock.patch.object(java, "LOCK_POLL", 0.05):
            with self.assertRaises(java.JavaError) as caught:
                java.run_quality(self.root, self.quality("a", timeout=0.2))
        self.assertIn("另一个实例正在跑质量检查", str(caught.exception))
        self.assertFalse((self.root / "runs.log").exists())
        self.assertEqual("other", json.loads(self.lock.read_text(encoding="utf-8"))["token"])

    def test_gate_blocks_locked_when_lock_is_busy(self):
        self.foreign(time.time() + 3600)
        change = self.root / ".openspec" / "changes" / "demo"
        change.mkdir(parents=True)
        project = Project(self.root)
        project.config_path.write_text("{}", encoding="utf-8")
        project.quality_baseline.write_text('{"version": 1, "violations": []}', encoding="utf-8")
        ctx = GateContext(project, "demo", change, {}, {"quality": self.quality("a", timeout=0.2)})
        with mock.patch.object(java, "LOCK_MARGIN", 0.3), mock.patch.object(java, "LOCK_POLL", 0.05):
            findings = g6_7.check(ctx)
        busy = [f for f in findings if f.check == "quality-execution"]
        self.assertEqual(1, len(busy))
        self.assertEqual("BLOCK", busy[0].level)
        self.assertTrue(busy[0].locked)
        self.assertIn("另一个实例正在跑质量检查", busy[0].reason)
        self.assertIn("另一个实例正在跑质量检查", (change / "static-analysis-report.md").read_text(encoding="utf-8"))

    def test_init_config_waits_on_same_lock(self):
        (self.root / "pom.xml").write_text("<project/>", encoding="utf-8")
        project = Project(self.root)
        quality = {check: {"timeout": 0.1} for check in java.CHECKS}
        project.config_path.write_text(json.dumps({"quality": quality}), encoding="utf-8")
        self.foreign(time.time() + 3600)
        with mock.patch.object(Project, "here", return_value=project), \
                mock.patch.object(java, "LOCK_MARGIN", 0.3), mock.patch.object(java, "LOCK_POLL", 0.05):
            with self.assertRaises(SystemExit) as caught:
                init_config.run(SimpleNamespace(java=True, dry_run=False))
        self.assertIn("另一个实例正在跑质量检查", str(caught.exception.code))
        self.assertFalse(project.quality_baseline.exists())

    def test_crashed_holder_lock_is_reclaimed_after_expiry(self):
        crash = subprocess.run([sys.executable, "-c", CRASHER, CLI_LIB, str(self.root), "0.5"],
                               stdout=subprocess.PIPE, stderr=subprocess.PIPE, encoding="utf-8", timeout=60)
        self.assertEqual(1, crash.returncode, crash.stderr)
        self.assertTrue(self.lock.exists())
        started = time.monotonic()
        with mock.patch.object(java, "LOCK_POLL", 0.05):
            violations, errors = java.run_quality(self.root, self.quality("a"))
        self.assertNotIn("archunit", errors)
        self.assertGreater(time.monotonic() - started, 0.1)
        self.assertFalse(self.lock.exists())

    def test_unreadable_lock_expires_only_after_longest_possible_run(self):
        self.lock.write_text("", encoding="utf-8")
        with mock.patch.object(java, "LOCK_MARGIN", 0.3), mock.patch.object(java, "LOCK_POLL", 0.05):
            with self.assertRaises(java.JavaError):
                java.run_quality(self.root, self.quality("a", timeout=0.2))
            old = time.time() - len(java.CHECKS) * java.MAX_TIMEOUT - 10
            os.utime(str(self.lock), (old, old))
            self.assertNotIn("archunit", java.run_quality(self.root, self.quality("a"))[1])
        self.assertFalse(self.lock.exists())

    def test_expiry_outlasts_all_configured_checks(self):
        quality = {check: {"timeout": 100} for check in java.CHECKS}
        with java.quality_lock(self.root, quality):
            data = json.loads(self.lock.read_text(encoding="utf-8"))
        self.assertGreaterEqual(data["expires"] - time.time(), 500)

    def test_release_keeps_lock_taken_over_by_another_instance(self):
        with java.quality_lock(self.root, {}):
            self.foreign(time.time() + 3600)
        self.assertEqual("other", json.loads(self.lock.read_text(encoding="utf-8"))["token"])

    def test_lock_does_not_leave_created_openspec_behind(self):
        root = self.root / "fresh"
        root.mkdir()
        with java.quality_lock(root, {}):
            self.assertTrue((root / ".openspec" / java.QUALITY_LOCK).exists())
        self.assertFalse((root / ".openspec").exists())


class AtomicReportTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.path = Path(self.tmp.name) / "static-analysis-report.md"

    def test_reader_never_sees_partial_report(self):
        versions = ["# A\n" + "a" * 2000000 + "\n", "# B\n" + "b" * 2000000 + "\n"]
        g6_7._write(self.path, versions[0])
        seen = []
        stop = threading.Event()

        def reader():
            while not stop.is_set():
                try:
                    seen.append(self.path.read_text(encoding="utf-8"))
                except OSError:
                    pass

        thread = threading.Thread(target=reader)
        thread.start()
        try:
            for index in range(30):
                try:
                    g6_7._write(self.path, versions[index % 2])
                except PermissionError:
                    # Windows refuses to replace a file another handle has open.
                    if os.name != "nt":
                        raise
        finally:
            stop.set()
            thread.join()
        self.assertTrue(seen)
        self.assertTrue(all(text in versions for text in seen))
        self.assertEqual([self.path.name], os.listdir(self.tmp.name))

    def test_failed_replace_keeps_previous_report_and_no_temp(self):
        g6_7._write(self.path, "old\n")
        with mock.patch("spec_driven.gates.g6_7.os.replace", side_effect=OSError("disk full")):
            with self.assertRaises(OSError):
                g6_7._write(self.path, "new\n")
        self.assertEqual("old\n", self.path.read_text(encoding="utf-8"))
        self.assertEqual([self.path.name], os.listdir(self.tmp.name))


if __name__ == "__main__":
    unittest.main()
