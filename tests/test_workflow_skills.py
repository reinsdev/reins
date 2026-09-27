"""Integration checks for T8 skill metadata, navigation, and CLI examples."""

import argparse
import importlib
import re
import shlex
import unittest
from pathlib import Path

from tests import PLUGIN
from spec_driven import frontmatter
from spec_driven.commands import COMMANDS


SKILLS = Path(PLUGIN) / "skills"
NAMES = ("spec-driven-dev", "spec", "bugfix", "requirements-clarify", "tech-design-tradeoff",
         "api-design-rest", "db-schema-design", "task-breakdown", "tdd-implement", "tiered-code-review")


def documents():
    paths = [SKILLS / name / "SKILL.md" for name in NAMES]
    return paths + sorted((SKILLS / "spec-driven-dev" / "references").glob("*.md"))


class WorkflowSkillsTest(unittest.TestCase):
    def test_runtime_can_load_each_skill_by_directory_name(self):
        for name in NAMES:
            with self.subTest(name=name):
                metadata, body = frontmatter.parse((SKILLS / name / "SKILL.md").read_text(encoding="utf-8"))
                self.assertEqual(metadata["name"], name)
                self.assertTrue(metadata["description"])
                self.assertTrue(body.strip())
                if name in ("spec", "bugfix"):
                    self.assertEqual(metadata["disable-model-invocation"], "true")
                else:
                    self.assertEqual(metadata["user-invocable"], "false")

    def test_local_navigation_reaches_bundled_skills_references_and_templates(self):
        for path in documents():
            for target in re.findall(r"\]\(([^)]+)\)", path.read_text(encoding="utf-8")):
                with self.subTest(path=path.name, target=target):
                    self.assertNotIn("://", target)
                    self.assertTrue((path.parent / target.split("#", 1)[0]).is_file())

    def test_full_cli_examples_parse_with_current_command_contracts(self):
        parser = argparse.ArgumentParser()
        sub = parser.add_subparsers(dest="command", required=True)
        for name in COMMANDS:
            importlib.import_module("spec_driven.commands." + name).register(sub)
        prefix = "<spec-driven-dev skill 目录>/scripts/spec-driven "
        samples = 0
        for path in documents():
            for line in path.read_text(encoding="utf-8").splitlines():
                if not line.startswith(prefix):
                    continue
                command = line[len(prefix):]
                substitutions = {"phase": "1", "tier": "M", "task": "T1", "change": "demo-change",
                                 "choice": "A", "reason": "user-reason", "warn-text": "review-warning"}
                for key, value in substitutions.items():
                    command = command.replace("<%s>" % key, value)
                with self.subTest(path=path.name, command=command):
                    self.assertNotRegex(command, r"<[^>]+>")
                    parsed = parser.parse_args(shlex.split(command))
                    self.assertIsNotNone(parsed.command)
                samples += 1
        self.assertGreater(samples, 0)


if __name__ == "__main__":
    unittest.main()
