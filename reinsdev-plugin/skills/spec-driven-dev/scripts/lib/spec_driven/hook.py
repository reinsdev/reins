"""`spec-driven hook <event>`: the single decision point behind every
runtime's hooks. Reads the runtime's JSON from stdin, normalizes it,
records it, and decides.

How a block is reported depends on the runtime:
  claude, codex  exit 0 + JSON `permissionDecision: deny` on stdout. Codex on
                 Windows runs hooks via `pwsh -Command`, which turns exit 2
                 into 1, so exit codes cannot carry a block there (openai/codex
                 #48183); the JSON form works on every OS for both runtimes.
  opencode       exit 2 + reason on stderr (read directly by our JS plugin).

The decisions themselves live in policies/ (see policies/__init__.py); this
module only translates between the platforms and that chain.
"""

import json
import os
import re
import sys
import time

from . import policies
from .paths import reins_home
from .policies.probe import PROBE  # noqa: F401  (re-exported for tests)

LOG_MAX_BYTES = 5 * 1024 * 1024

JSON_RUNTIMES = {"claude", "codex"}

SHELL_TOOLS = {"bash", "shell", "exec_command", "local_shell"}
EDIT_TOOLS = {"edit", "write", "multiedit", "notebookedit", "apply_patch", "patch"}
_PATCH_FILE = re.compile(r"^\*\*\* (?:Add|Update|Delete) File: (.+)$", re.M)


def normalize(payload: dict, runtime: str) -> dict:
    tool = str(payload.get("tool_name") or "")
    args = payload.get("tool_input") or {}
    if not isinstance(args, dict):
        args = {"input": args}
    kind = "shell" if tool.lower() in SHELL_TOOLS else "edit" if tool.lower() in EDIT_TOOLS else "other"

    paths = []
    for k in ("file_path", "filePath", "path", "notebook_path"):
        if isinstance(args.get(k), str):
            paths.append(args[k])
    # Codex sends the patch body of apply_patch in tool_input.command.
    patch = args.get("patch") or args.get("input") or args.get("command") or ""
    if tool.lower() in ("apply_patch", "patch") and isinstance(patch, str):
        paths.extend(_PATCH_FILE.findall(patch))
    for e in args.get("edits") or []:  # multi-file edit shapes
        if isinstance(e, dict) and isinstance(e.get("file_path"), str):
            paths.append(e["file_path"])

    # One separator everywhere so path rules work the same on Windows.
    paths = [p.replace("\\", "/") for p in paths]

    command = "" if kind == "edit" else (args.get("command") or args.get("cmd") or "")
    if isinstance(command, list):
        command = " ".join(str(c) for c in command)

    return {
        "runtime": runtime,
        "event": payload.get("hook_event_name") or "",
        "tool": tool,
        "kind": kind,
        "paths": paths,
        "command": command,
        "prompt": payload.get("prompt") or "",
        "cwd": payload.get("cwd") or "",
        # Subagent name without the plugin prefix ("reins:spec-evaluator" -> "spec-evaluator");
        # "" on the main thread or when the runtime does not say (Codex and OpenCode
        # PreToolUse payloads carry no agent identity).
        "agent": str(payload.get("agent_type") or "").split(":")[-1],
    }


def decide(ev: dict, errors: list = None):
    """Return a block reason, or None to allow."""
    return policies.pre_tool(ev, errors if errors is not None else [])


def _record(ev: dict, verdict: str, errors=()) -> None:
    try:
        log = reins_home() / "logs" / "hooks.jsonl"
        log.parent.mkdir(parents=True, exist_ok=True)
        rec = dict(ev, verdict=verdict, ts=time.strftime("%Y-%m-%dT%H:%M:%S"))
        if errors:
            rec["policyErrors"] = list(errors)
        rec.pop("prompt", None)  # never persist raw prompts
        try:
            if log.stat().st_size > LOG_MAX_BYTES:
                os.replace(str(log), str(log.with_name("hooks.jsonl.1")))
        except OSError:
            pass  # Rotation is best effort; still try to append this event.
        data = (json.dumps(rec, ensure_ascii=False) + "\n").encode("utf-8")
        fd = os.open(str(log), os.O_WRONLY | os.O_CREAT | os.O_APPEND | getattr(os, "O_BINARY", 0), 0o600)
        try:
            os.write(fd, data)
        finally:
            os.close(fd)
    except OSError:
        pass


def run(event: str, runtime: str) -> int:
    raw = sys.stdin.read()
    try:
        payload = json.loads(raw) if raw.strip() else {}
    except ValueError:
        return 0  # malformed input must never block the user
    ev = normalize(payload, runtime)
    ev["event"] = ev["event"] or event
    errors = []
    if event == "prompt-submit":
        note = policies.prompt(ev, errors)
        _record(ev, "allow", errors)
        if note and runtime in JSON_RUNTIMES:
            sys.stdout.write(json.dumps({"hookSpecificOutput": {
                "hookEventName": "UserPromptSubmit",
                "additionalContext": note,
            }}, ensure_ascii=False) + "\n")
        return 0
    reason = decide(ev, errors)
    _record(ev, "block" if reason else "allow", errors)
    if not reason:
        return 0
    if runtime in JSON_RUNTIMES:
        sys.stdout.write(json.dumps({"hookSpecificOutput": {
            "hookEventName": "PreToolUse",
            "permissionDecision": "deny",
            "permissionDecisionReason": reason,
        }}, ensure_ascii=False) + "\n")
        return 0
    sys.stderr.write(reason + "\n")
    return 2
