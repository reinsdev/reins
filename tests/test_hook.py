import unittest

from tests import CLI_LIB  # noqa: F401
from spec_driven import hook


class NormalizeTest(unittest.TestCase):
    def test_claude_write(self):
        ev = hook.normalize({"hook_event_name": "PreToolUse", "tool_name": "Write",
                             "tool_input": {"file_path": "/p/a.md"}}, "claude")
        self.assertEqual((ev["kind"], ev["paths"]), ("edit", ["/p/a.md"]))

    def test_codex_apply_patch(self):
        patch = "*** Begin Patch\n*** Update File: src/a.py\n@@\n*** Add File: .openspec/x.md\n*** End Patch"
        ev = hook.normalize({"tool_name": "apply_patch", "tool_input": {"patch": patch}}, "codex")
        self.assertEqual(ev["kind"], "edit")
        self.assertEqual(ev["paths"], ["src/a.py", ".openspec/x.md"])

    def test_codex_bash_command_list(self):
        ev = hook.normalize({"tool_name": "Bash", "tool_input": {"command": ["git", "status"]}}, "codex")
        self.assertEqual((ev["kind"], ev["command"]), ("shell", "git status"))

    def test_opencode_edit(self):
        ev = hook.normalize({"tool_name": "edit", "tool_input": {"filePath": "/p/b.ts"}}, "opencode")
        self.assertEqual((ev["kind"], ev["paths"]), ("edit", ["/p/b.ts"]))


class DecideTest(unittest.TestCase):
    def test_probe_blocks(self):
        ev = hook.normalize({"tool_name": "Bash", "tool_input": {"command": "touch x.reins-probe-block"}}, "claude")
        self.assertIsNotNone(hook.decide(ev))

    def test_normal_allows(self):
        ev = hook.normalize({"tool_name": "Bash", "tool_input": {"command": "ls"}}, "claude")
        self.assertIsNone(hook.decide(ev))


if __name__ == "__main__":
    unittest.main()


class RunTest(unittest.TestCase):
    """End-to-end: how each runtime receives a block."""

    def _run(self, runtime, command):
        import json, os, subprocess, sys, tempfile
        from pathlib import Path
        env = dict(os.environ, REINS_HOME=tempfile.mkdtemp(),
                   PYTHONPATH=str(Path(hook.__file__).resolve().parents[1]))
        payload = json.dumps({"tool_name": "Bash", "tool_input": {"command": command}})
        return subprocess.run([sys.executable, "-m", "spec_driven", "hook", "pre-tool", "--runtime", runtime],
                              input=payload, capture_output=True, encoding="utf-8", env=env)

    def test_json_deny_for_claude_and_codex(self):
        import json
        for runtime in ("claude", "codex"):
            r = self._run(runtime, "touch x.reins-probe-block")
            self.assertEqual(r.returncode, 0, runtime)
            out = json.loads(r.stdout)["hookSpecificOutput"]
            self.assertEqual(out["permissionDecision"], "deny")

    def test_exit_code_for_opencode(self):
        r = self._run("opencode", "touch x.reins-probe-block")
        self.assertEqual((r.returncode, r.stdout), (2, ""))
        self.assertIn("探针", r.stderr)

    def test_allow_is_silent(self):
        for runtime in ("claude", "codex", "opencode"):
            r = self._run(runtime, "ls")
            self.assertEqual((r.returncode, r.stdout), (0, ""), runtime)
