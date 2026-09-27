import unittest

from tests import CLI_LIB  # noqa: F401
from tests.support_t2 import cli, git, java_repo
from spec_driven import locate
from spec_driven.project import Project


class LocateTest(unittest.TestCase):
    def test_not_enabled(self):
        with java_repo() as root, self.assertRaises(SystemExit) as cm:
            locate.resolve(Project(root))
        self.assertIn("尚未启用", str(cm.exception.code))

    def test_single_branch_and_explicit(self):
        with java_repo() as root:
            cli("new", "first-change")
            self.assertEqual(locate.resolve(Project(root)), "first-change")
            git(root, "add", ".openspec")
            git(root, "commit", "-qm", "save first change before switching")
            cli("new", "second-change")          # now on feat/second-change
            self.assertEqual(locate.resolve(Project(root)), "second-change")
            self.assertEqual(locate.resolve(Project(root), "first-change"), "first-change")
            git(root, "switch", "-q", "-c", "unbound-branch")
            with self.assertRaises(SystemExit) as cm:
                locate.resolve(Project(root))
            self.assertIn("多个", str(cm.exception.code))
            with self.assertRaises(SystemExit):
                locate.resolve(Project(root), "nope-change")


if __name__ == "__main__":
    unittest.main()
