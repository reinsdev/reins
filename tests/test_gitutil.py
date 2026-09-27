import unittest
from pathlib import Path

from tests import CLI_LIB  # noqa: F401
from tests.support_t2 import commit, git, java_repo
from spec_driven import gitutil


class GitutilTest(unittest.TestCase):
    def test_basics(self):
        with java_repo() as root:
            self.assertTrue(gitutil.is_repo(root))
            self.assertEqual(gitutil.head(root), git(root, "rev-parse", "HEAD"))
            self.assertEqual(gitutil.current_branch(root), "main")
            self.assertEqual(gitutil.user_name(root), "tester")
            git(root, "checkout", "-q", "--detach")
            self.assertIsNone(gitutil.current_branch(root))

    def test_changed_files_includes_untracked_and_unicode(self):
        with java_repo() as root:
            base = gitutil.head(root)
            commit(root, "c1", {"src/A.java": "a"})
            (root / "pom.xml").write_text("<changed/>", encoding="utf-8")
            (root / "文档.md").write_text("x", encoding="utf-8")
            (root / ".gitignore").write_text("ignored.txt\n", encoding="utf-8")
            (root / "ignored.txt").write_text("x", encoding="utf-8")
            files = gitutil.changed_files(base, root)
            self.assertEqual(set(files), {"src/A.java", "pom.xml", "文档.md", ".gitignore"})

    def test_commits_with_trailers(self):
        with java_repo() as root:
            base = gitutil.head(root)
            commit(root, "RED: failing test\n\nTask-Id: T1\nTDD-Phase: RED")
            commit(root, "green\n\nbody line\n\nTask-Id: T1, T2")
            got = gitutil.commits(base, root)
            self.assertEqual([c["subject"] for c in got], ["RED: failing test", "green"])
            self.assertEqual(got[0]["trailers"], {"Task-Id": ["T1"], "TDD-Phase": ["RED"]})
            self.assertEqual(got[1]["trailers"], {"Task-Id": ["T1, T2"]})

    def test_not_a_repo(self):
        with java_repo() as root:
            outside = Path(root).parent
            self.assertFalse(gitutil.is_repo(outside))
            with self.assertRaises(SystemExit):
                gitutil.head(outside)


if __name__ == "__main__":
    unittest.main()
