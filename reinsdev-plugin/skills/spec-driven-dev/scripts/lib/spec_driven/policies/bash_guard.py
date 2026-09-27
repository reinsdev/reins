"""bash-guard: shell command rules. Owner: T6.

Blocks:
  - deleting test code (anything under src/test/) with rm, rmdir, unlink, git rm, find -delete;
  - skipping the git hooks: `git commit --no-verify` / `-n`, changing core.hooksPath;
  - shell writes to paths the edit rules protect (common.write_violation): redirections,
    tee, sed -i, cp / mv / install destinations, rm, truncate, touch, dd of=, git checkout /
    restore of those files, and inline scripts (python -c, node -e ...) naming them;
  - repository-changing git commands from evaluator agents (commit, push, reset, checkout ...).
`spec-driven waive` / `complexity set --downgrade` are not blocked here: the CLI refuses
them without a grant by itself.
Parsing is best effort (quotes, &&, ||, ;, |, newlines, `sh -c "..."`); what it cannot
see is still caught by the gates and the git hooks.
"""

import os
import re
import shlex
from typing import List, Optional

from .common import EVALUATOR_REPORT, abs_path, write_violation

_REDIRECT = re.compile(r"^(?:\d?>>?|&>>?)(.*)$")
_WRAPPERS = {"sudo", "command", "env", "nohup", "time", "exec", "xargs"}
_SHELLS = {"sh", "bash", "zsh", "dash"}
_INLINE = {"python": "-c", "python3": "-c", "node": "-e", "perl": "-e", "ruby": "-e"}
_PROTECTED_WORDS = (".meta.json", "retrospective.md", ".retro.sha256", ".config.json",
                    "quality-baseline.json", "/grants")
_EVALUATOR_GIT = {"commit", "push", "reset", "checkout", "switch", "restore", "stash", "clean",
                  "merge", "rebase", "cherry-pick", "revert", "am", "apply", "rm", "mv", "tag", "branch"}


def _tokens(segment: str) -> List[str]:
    try:
        lex = shlex.shlex(segment, posix=True, punctuation_chars="<>&")
        lex.whitespace_split = True
        return list(lex)
    except ValueError:
        return segment.split()


def split_commands(command: str) -> List[str]:
    """Split on ; && || | and newlines outside quotes."""
    parts, buf, quote, i = [], [], None, 0
    while i < len(command):
        c = command[i]
        if quote:
            buf.append(c)
            if c == "\\" and quote == '"' and i + 1 < len(command):
                buf.append(command[i + 1])
                i += 1
            elif c == quote:
                quote = None
        elif c in "'\"":
            quote = c
            buf.append(c)
        elif c in ";|\n" or (c == "&" and command[i + 1:i + 2] == "&"):
            parts.append("".join(buf))
            buf = []
            if command[i + 1:i + 2] in ("&", "|") and c in "&|":
                i += 1
        else:
            buf.append(c)
        i += 1
    parts.append("".join(buf))
    return parts


def segments(command: str, depth: int = 0) -> List[List[str]]:
    """Token lists of every simple command, unwrapping `sh -c "..."`."""
    out = []
    for part in split_commands(command or ""):
        toks = _tokens(part.strip())
        while toks and (re.match(r"^\w+=", toks[0]) or os.path.basename(toks[0]) in _WRAPPERS):
            toks = toks[1:]
        if not toks:
            continue
        if os.path.basename(toks[0]) in _SHELLS and "-c" in toks and depth < 3:
            i = toks.index("-c")
            if i + 1 < len(toks):
                out.extend(segments(toks[i + 1], depth + 1))
                continue
        out.append(toks)
    return out


def _is_test_path(p: str) -> bool:
    return "src/test" in p.replace("\\", "/")


def _args(toks: List[str]) -> List[str]:
    return [t for t in toks[1:] if not t.startswith("-")]


def write_targets(toks: List[str]) -> List[str]:
    """Paths a simple command writes, as far as we can tell."""
    targets, rest = [], []
    i = 0
    while i < len(toks):
        if toks[i] in ("<", "<<", "<<<"):
            i += 2  # input redirection and its source
            continue
        m = _REDIRECT.match(toks[i])
        if m:
            if m.group(1):
                targets.append(m.group(1))
            elif i + 1 < len(toks):
                targets.append(toks[i + 1])
                i += 1
            targets = [t for t in targets if not t.startswith("&")]  # 2>&1 is not a file
        else:
            rest.append(toks[i])
        i += 1
    if not rest:
        return targets
    cmd, args = os.path.basename(rest[0]), _args(rest)
    if cmd == "tee":
        targets += args
    elif cmd == "sed" and any(t == "-i" or t.startswith("-i") or t == "--in-place" for t in rest[1:]):
        targets += args[1:]
    elif cmd in ("cp", "install") and args:
        targets.append(args[-1])
    elif cmd in ("mv", "rm", "unlink", "truncate", "touch", "rmdir", "shred"):
        targets += args
    elif cmd == "dd":
        targets += [a[3:] for a in rest[1:] if a.startswith("of=")]
    elif cmd == "git" and len(rest) > 1 and rest[1] in ("checkout", "restore", "rm", "mv"):
        targets += [a for a in rest[2:] if not a.startswith("-") and a != "--"]
    return targets


def _git_rule(toks: List[str], agent: str) -> Optional[str]:
    if os.path.basename(toks[0]) != "git":
        return None
    args = toks[1:]
    if any(a.startswith("core.hooksPath") or a.startswith("core.hookspath") for a in args):
        return "不能修改 git 的 core.hooksPath：它会绕过 Reins 的 git hook"
    sub = next((a for a in args if not a.startswith("-") and "=" not in a), "")
    if sub == "commit" and ("--no-verify" in args or "-n" in args):
        return "不能用 --no-verify 跳过 Reins 的 git hook；被拦截时按提示修复"
    if agent in EVALUATOR_REPORT and sub in _EVALUATOR_GIT:
        return "%s 是只读评审 agent，不能执行 git %s" % (agent, sub)
    return None


def pre_tool(ev: dict) -> Optional[str]:
    if ev.get("kind") != "shell" or not ev.get("command"):
        return None
    agent = ev.get("agent") or ""
    for toks in segments(ev["command"]):
        reason = _git_rule(toks, agent)
        if reason:
            return "Reins 拦截：" + reason
        cmd = os.path.basename(toks[0])
        deleting = cmd in ("rm", "rmdir", "unlink", "shred") or (cmd == "git" and "rm" in toks[1:2]) \
            or (cmd == "find" and "-delete" in toks)
        if deleting and any(_is_test_path(t) for t in toks[1:]):
            return "Reins 拦截：不能删除测试代码（src/test/）；测试失败请修实现，不要删测试"
        if cmd in _INLINE and _INLINE[cmd] in toks and any(w in " ".join(toks) for w in _PROTECTED_WORDS):
            return "Reins 拦截：不能用脚本改写 Reins 受保护的文件（.meta.json、retrospective.md、配置、授权）"
        for target in write_targets(toks):
            reason = write_violation(ev, abs_path(ev, target))
            if reason:
                return "Reins 拦截：" + reason
    return None
