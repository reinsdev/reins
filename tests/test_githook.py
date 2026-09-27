"""Git layer (T6): hooks installed by `new`, exercised with real `git commit`."""

import json
import subprocess
import unittest

from tests import CLI_LIB  # noqa: F401
from tests.support_t2 import cli, git, java_repo
from spec_driven.commands import githook


def try_commit(root, message, files):
    for name, text in files.items():
        p = root / name
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(text, encoding="utf-8")
    git(root, "add", "-A")
    r = subprocess.run(["git", "commit", "-q", "-m", message], cwd=str(root), capture_output=True, encoding="utf-8")
    return r.returncode, r.stderr


def set_phase(root, change, phase):
    p = root / ".openspec/changes" / change / ".meta.json"
    m = json.loads(p.read_text(encoding="utf-8"))
    m["phase"] = phase
    p.write_text(json.dumps(m), encoding="utf-8")


class InstallTest(unittest.TestCase):
    def test_new_installs_and_chains_foreign_hook(self):
        with java_repo() as root:
            hooks = root / ".git/hooks"
            hooks.mkdir(exist_ok=True)
            (hooks / "pre-commit").write_text("#!/bin/sh\necho foreign > foreign-ran.txt\n", encoding="utf-8")
            (hooks / "pre-commit").chmod(0o755)
            code, out = cli("new", "hook-change")
            self.assertIn("pre-commit", out)
            self.assertIn(githook.MARK, (hooks / "pre-commit").read_text(encoding="utf-8"))
            self.assertTrue((hooks / "pre-commit.reins-chained").is_file())
            githook.install(root)   # idempotent: does not chain itself
            self.assertIn("foreign", (hooks / "pre-commit.reins-chained").read_text(encoding="utf-8"))
            self.assertEqual(try_commit(root, "x", {"a.txt": "a"})[0], 0)
            self.assertTrue((root / "foreign-ran.txt").is_file())


class PreCommitTest(unittest.TestCase):
    def test_retrospective_must_come_from_cli(self):
        with java_repo() as root:
            cli("new", "retro-change")
            cli("retro", "add", "补文档")
            self.assertEqual(try_commit(root, "cli write", {})[0], 0)
            path = ".openspec/changes/retro-change/retrospective.md"
            text = (root / path).read_text(encoding="utf-8") + "| 伪造 | 放行 |\n"
            code, err = try_commit(root, "manual", {path: text})
            self.assertEqual(code, 1)
            self.assertIn("retrospective.md", err)

    def test_frozen_artifact(self):
        with java_repo() as root:
            cli("new", "freeze-change")
            path = ".openspec/changes/freeze-change/proposal.md"
            self.assertEqual(try_commit(root, "phase 1 work", {path: "# v1\n"})[0], 0)
            set_phase(root, "freeze-change", "3")
            code, err = try_commit(root, "late edit", {path: "# v2\n"})
            self.assertEqual(code, 1)
            self.assertIn("已冻结", err)
            git(root, "reset", "-q", "HEAD")
            set_phase(root, "freeze-change", "1")
            self.assertEqual(try_commit(root, "after retry", {path: "# v2\n"})[0], 0)


class CommitMsgTest(unittest.TestCase):
    def test_task_id_in_phase_6(self):
        with java_repo() as root:
            cli("new", "six-change")
            self.assertEqual(try_commit(root, "phase 0 code", {"src/A.java": "a"})[0], 0)
            set_phase(root, "six-change", "6")
            code, err = try_commit(root, "impl", {"src/B.java": "b"})
            self.assertEqual(code, 1)
            self.assertIn("Task-Id", err)
            self.assertEqual(try_commit(root, "impl\n\nTask-Id: TX", {})[0], 1)
            self.assertEqual(try_commit(root, "impl\n\nTask-Id: T3", {})[0], 0)
            self.assertEqual(try_commit(root, "docs only", {".openspec/changes/six-change/implementation-log.md": "x"})[0], 0)


if __name__ == "__main__":
    unittest.main()
