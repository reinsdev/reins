import unittest

from tests import CLI_LIB  # noqa: F401
from spec_driven import frontmatter


class FrontmatterTest(unittest.TestCase):
    def test_scalars_inline_and_block_lists(self):
        meta, body = frontmatter.parse(
            "---\nname: a\ndescription: x: y\naccess: [read, write]\ntags:\n  - one\n  - \"two\"\n---\nbody\n")
        self.assertEqual(meta["name"], "a")
        self.assertEqual(meta["description"], "x: y")
        self.assertEqual(meta["access"], ["read", "write"])
        self.assertEqual(meta["tags"], ["one", "two"])
        self.assertEqual(body, "body\n")

    def test_no_frontmatter(self):
        self.assertEqual(frontmatter.parse("plain"), ({}, "plain"))


if __name__ == "__main__":
    unittest.main()
