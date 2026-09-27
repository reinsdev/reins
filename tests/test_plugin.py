"""The plugin directory is the product: check that every platform's entry
points at real files and that the shared content stays consistent."""

import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from tests import PLUGIN, ROOT
from spec_driven import VERSION, frontmatter
from reinsdev.agents import codex_agent, install_agents

try:
    import tomllib
except ImportError:  # Python < 3.11
    tomllib = None

PLUGIN = Path(PLUGIN)
ROOT = Path(ROOT)
SCRIPTS = PLUGIN / "skills" / "spec-driven-dev" / "scripts"
CLAUDE_TOOLS = {"read": ["Read", "Grep", "Glob"], "shell-readonly": ["Bash"], "shell": ["Bash"],
                "write-own-report": ["Write"], "write": ["Edit", "Write"]}


def load(rel):
    return json.loads((ROOT / rel).read_text(encoding="utf-8"))


class ManifestTest(unittest.TestCase):
    def test_marketplaces_point_at_plugin_dir(self):
        claude = load(".claude-plugin/marketplace.json")
        codex = load(".agents/plugins/marketplace.json")
        self.assertEqual((claude["name"], codex["name"]), ("reinsdev", "reinsdev"))
        self.assertEqual(claude["plugins"][0]["source"], "./reinsdev-plugin")
        self.assertEqual(codex["plugins"][0]["source"]["path"], "./reinsdev-plugin")

    def test_one_version_everywhere(self):
        versions = {
            "spec_driven": VERSION,
            "claude plugin.json": load("reinsdev-plugin/.claude-plugin/plugin.json")["version"],
            "codex plugin.json": load("reinsdev-plugin/.codex-plugin/plugin.json")["version"],
            "package.json": load("reinsdev-plugin/package.json")["version"],
            "claude marketplace": load(".claude-plugin/marketplace.json")["plugins"][0]["version"],
        }
        self.assertEqual(len(set(versions.values())), 1, versions)

    def test_manifest_paths_exist(self):
        claude = load("reinsdev-plugin/.claude-plugin/plugin.json")
        codex = load("reinsdev-plugin/.codex-plugin/plugin.json")
        npm = load("reinsdev-plugin/package.json")
        for rel in (claude["hooks"], codex["skills"], codex["extensions"]["com.openai"]["hooks"],
                    npm["main"], *(x for x in npm["files"] if not x.startswith("!"))):
            self.assertTrue((PLUGIN / rel).exists(), rel)

    def test_hook_commands_target_bundled_cli(self):
        for name, root_var in (("claude.json", "${CLAUDE_PLUGIN_ROOT}"), ("codex.json", "${PLUGIN_ROOT}")):
            hooks = json.loads((PLUGIN / "hooks" / name).read_text(encoding="utf-8"))["hooks"]
            for entries in hooks.values():
                for h in entries[0]["hooks"]:
                    self.assertTrue(h["command"].startswith('"%s/skills/spec-driven-dev/scripts/spec-driven"' % root_var))
                    if "commandWindows" in h:
                        self.assertIn("spec-driven.cmd", h["commandWindows"])


class ContentTest(unittest.TestCase):
    def test_agents_claude_tools_match_access(self):
        for md in sorted((PLUGIN / "agents").glob("*.md")):
            meta, body = frontmatter.parse(md.read_text(encoding="utf-8"))
            self.assertEqual(meta["name"], md.stem)
            want = []
            for level in ["read"] + meta["access"]:
                want += [t for t in CLAUDE_TOOLS[level] if t not in want]
            self.assertEqual(meta["tools"], ", ".join(want), md.name)
            if meta.get("report"):  # evaluators must sign their report
                self.assertIn("<!-- generated-by: %s-subagent -->" % meta["name"], body)

    def test_entry_skills(self):
        for name in ("spec", "bugfix", "waive"):
            meta, _ = frontmatter.parse((PLUGIN / "skills" / name / "SKILL.md").read_text(encoding="utf-8"))
            self.assertEqual(meta["name"], name)

    def test_no_placeholders_or_caches(self):
        for f in PLUGIN.rglob("*"):
            self.assertNotEqual(f.name, "tests", f)
            if f.is_file() and f.suffix in (".md", ".json", ".js"):
                self.assertNotIn("{{", f.read_text(encoding="utf-8"), f)


class CodexAgentTest(unittest.TestCase):
    def test_toml(self):
        text = codex_agent(PLUGIN / "agents" / "qa-evaluator.md")
        self.assertIn('sandbox_mode = "workspace-write"', text)
        if tomllib:
            data = tomllib.loads(text)
            self.assertEqual(data["name"], "qa-evaluator")
            self.assertTrue(data["developer_instructions"].startswith("你是独立的 QA 验证者"))

    def test_install_refuses_foreign_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            dest = Path(tmp)
            (dest / "spec-evaluator.toml").write_text("mine", encoding="utf-8")
            with self.assertRaises(SystemExit):
                install_agents(dest, force=False)
            self.assertEqual(len(install_agents(dest, force=True)), 4)


class LauncherTest(unittest.TestCase):
    def test_line_endings(self):
        self.assertIn(b"\r\n", (SCRIPTS / "spec-driven.cmd").read_bytes())
        self.assertNotIn(b"\r\n", (SCRIPTS / "spec-driven").read_bytes())

    def test_entry_runs(self):
        r = subprocess.run([sys.executable, str(SCRIPTS / "spec-driven.py"), "version"],
                           capture_output=True, encoding="utf-8")
        self.assertEqual((r.returncode, r.stdout.strip()), (0, VERSION), r.stderr)

    @unittest.skipIf(os.name == "nt", "sh launcher")
    def test_sh_launcher_executable(self):
        self.assertTrue(os.access(SCRIPTS / "spec-driven", os.X_OK))


if __name__ == "__main__":
    unittest.main()
