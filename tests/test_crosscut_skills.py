"""Validate the discoverable T10 skill files through the shared parser."""
import unittest
from pathlib import Path

from tests import PLUGIN
from spec_driven import frontmatter


SKILLS = (
    'root-cause-analysis', 'incident-analysis', 'code-quality-optimize',
    'codegraph', 'log-search', 'local-deploy', 'openapi-check', 'safety-check',
)


class CrosscutSkillsTest(unittest.TestCase):
    def test_skills_are_discoverable_with_supported_frontmatter(self):
        for name in SKILLS:
            with self.subTest(skill=name):
                path = Path(PLUGIN) / 'skills' / name / 'SKILL.md'
                self.assertTrue(path.is_file(), 'Missing skill: %s' % name)
                text = path.read_text(encoding='utf-8')
                meta, body = frontmatter.parse(text)
                self.assertEqual(meta.get('name'), name)
                self.assertIsInstance(meta.get('description'), str)
                self.assertTrue(meta['description'].strip())
                self.assertTrue(body.strip())
                self.assertEqual(frontmatter.parse(text.replace('\n', '\r\n'))[0], meta)


if __name__ == '__main__':
    unittest.main()
