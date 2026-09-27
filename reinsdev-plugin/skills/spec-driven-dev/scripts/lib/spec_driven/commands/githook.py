"""`spec-driven githook`. Owner: T6. The git layer of the guardrails (design doc §2.4, layer 2).

  install      write .git/hooks/pre-commit and commit-msg; an existing foreign hook is kept
               as <hook>.reins-chained and still runs after ours
  pre-commit   reject staged retrospective.md that the CLI did not write, and staged edits
               to artifacts already frozen in HEAD (upstream freeze, §4 rule 1)
  commit-msg   in Phase 6, code commits must carry a Task-Id trailer

Rejections print the reason and exit 1; anything unexpected lets the commit through
(a broken hook must not block the user; layers 1 and 3 still hold).
"""

import os
import re
import shlex
import stat
import subprocess
import sys
from pathlib import Path
from typing import List, Optional

from .. import gitutil, locate, mdparse, retro, taskstate
from .. import project as P
from ..errors import ERROR, OK, fail
from ..meta import PHASES
from ..policies.common import ARTIFACT_PHASE, read_meta
from ..project import Project

MARK = "# reins-managed git hook"
EVENTS = ("pre-commit", "commit-msg")
LAUNCHER = Path(__file__).resolve().parents[3] / "spec-driven"


def register(sub):
    p = sub.add_parser("githook", help="git hook 入口与安装")
    p.add_argument("event", choices=["install", "pre-commit", "commit-msg"])
    p.add_argument("msgfile", nargs="?")


def _script(event: str) -> str:
    return """#!/bin/sh
%s (spec-driven githook install); do not edit
CLI=%s
if [ -f "$CLI" ]; then
  sh "$CLI" githook %s "$@" || exit $?
else
  echo "Reins 警告：找不到 $CLI，本次没有执行 Reins 检查。请用 reinsdev update 更新插件，再让当前会话查看状态以自动修复。" >&2
fi
if [ -x "$0.reins-chained" ]; then
  exec "$0.reins-chained" "$@"
fi
""" % (MARK, shlex.quote(LAUNCHER.as_posix()), event)


def install(root: Path) -> List[str]:
    """Install both hooks into the repository at `root`; return their paths."""
    hooks = Path(gitutil.git(["rev-parse", "--git-path", "hooks"], root))
    if not hooks.is_absolute():
        hooks = Path(root) / hooks
    hooks.mkdir(parents=True, exist_ok=True)
    written = []
    for event in EVENTS:
        path = hooks / event
        if path.is_file() and MARK not in path.read_text(encoding="utf-8", errors="replace"):
            chained = path.with_name(event + ".reins-chained")
            if chained.exists():
                fail("%s 和 %s 都已存在，无法安装 Reins git hook；请手工合并" % (path, chained))
            os.replace(str(path), str(chained))
        path.write_bytes(_script(event).encode("utf-8"))
        path.chmod(path.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
        written.append(str(path))
    return written


def ensure_current(root: Path) -> None:
    """Refresh installed Reins hooks after upgrades; diagnostics never change command results."""
    try:
        hooks = Path(gitutil.git(["rev-parse", "--git-path", "hooks"], root))
        if not hooks.is_absolute():
            hooks = Path(root) / hooks
        scripts = {}
        for event in EVENTS:
            path = hooks / event
            scripts[event] = path.read_text(encoding="utf-8", errors="replace") if path.is_file() else ""
        if not any(MARK in script for script in scripts.values()):
            return
        if not LAUNCHER.is_file():
            raise OSError("当前插件 CLI 不存在：%s" % LAUNCHER)
        if any(scripts[event] != _script(event) for event in EVENTS):
            install(root)
    except (Exception, SystemExit) as exc:
        sys.stderr.write("Reins 提示：git hook 自动修复失败（%s）；请用 reinsdev update 更新插件后重试。\n" % exc)


def _staged(root: Path) -> List[str]:
    out = gitutil.git(["diff", "--cached", "--name-only", "-z"], root)
    return [p for p in out.split("\0") if p]


def _show(root: Path, spec: str) -> Optional[str]:
    r = subprocess.run(["git", "show", spec], cwd=str(root), capture_output=True)
    return r.stdout.decode("utf-8", "replace") if r.returncode == 0 else None


def pre_commit(project: Project) -> List[str]:
    """Problems with the staged changes; [] when the commit may proceed."""
    root, problems = project.root, []
    prefix = project.changes_dir.relative_to(root).as_posix() + "/"
    for path in _staged(root):
        if not path.startswith(prefix):
            continue
        parts = path[len(prefix):].split("/")
        if len(parts) != 2 or parts[0] == "archive":
            continue
        change, name = parts
        change_dir = project.change_dir(change)
        if name == P.RETROSPECTIVE:
            staged = _show(root, ":" + path)
            if staged is not None and not retro.verify(change_dir, staged):
                problems.append("%s 有不是经 spec-driven 命令写入的改动；请撤销这些手工修改" % path)
            continue
        produced = ARTIFACT_PHASE.get(name)
        m = read_meta(change_dir)
        if not produced or not m or m.get("phase") not in PHASES:
            continue
        if PHASES.index(produced) >= PHASES.index(m["phase"]):
            continue
        before = _show(root, "HEAD:" + path)
        staged = _show(root, ":" + path)
        if before is not None and before != staged:
            if name == P.TASKS and m["phase"] == "6":
                done = taskstate.done_tasks(project, m)
                # render changes only task checkboxes; compare the index, never the working file.
                if staged == taskstate.render(before, done):
                    continue
            problems.append("%s 属于 Phase %s，已冻结（当前 Phase %s）；要改请先回退：spec-driven retry %s --reason ..."
                            % (path, produced, m["phase"], produced))
    return problems


def commit_msg(project: Project, msgfile: str) -> List[str]:
    try:
        change = locate.resolve(project)
    except SystemExit:
        return []
    m = read_meta(project.change_dir(change))
    if not m or m.get("phase") != "6":
        return []
    openspec = project.openspec.relative_to(project.root).as_posix() + "/"
    if not [p for p in _staged(project.root) if not p.startswith(openspec)]:
        return []
    trailers = gitutil.git(["interpret-trailers", "--parse", msgfile], project.root)
    ids = []
    for line in trailers.splitlines():
        key, _, value = line.partition(":")
        if key.strip().lower() == "task-id":
            ids += [t for t in re.split(r"[,\s]+", value) if t]
    task = re.compile(r"^(?:%s)$" % mdparse.ID_PATTERNS["TASK"])
    if not ids:
        return ["%s 正处于 Phase 6：代码提交必须带 Task-Id trailer（如 `Task-Id: T3`），用于判定任务完成" % change]
    bad = [i for i in ids if not task.match(i)]
    if bad:
        return ["Task-Id %s 格式不对，应为 T<数字> 或 T-regression" % "、".join(bad)]
    return []


def run(a) -> int:
    project = Project.here()
    if a.event == "install":
        for f in install(project.root):
            print("已安装 %s" % f)
        return OK
    if not project.enabled:
        return OK
    try:
        if a.event == "pre-commit":
            problems = pre_commit(project)
        else:
            if not a.msgfile:
                return OK
            problems = commit_msg(project, a.msgfile)
    except SystemExit:
        return OK  # e.g. git failed: let the commit through
    for p in problems:
        sys.stderr.write("reins: %s\n" % p)
    return ERROR if problems else OK
