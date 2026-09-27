"""Task completion derived from git, never from hand-ticked boxes (workflow §10.5). Owner: T2.

Used read-only by `tasks-sync` (which may write tasks.md) and by gate 6.5.

A task is done when a non-RED commit since baseCommit carries `Task-Id: <id>`.
RED commits (the failing test of TDD) are marked by the trailer `TDD-Phase: RED`
or a subject starting with "RED" / "red:"; they prove the test came first but do
not complete the task.
"""

import re
from typing import Dict, List

from . import gitutil, mdparse
from .project import Project

_RED_SUBJECT = re.compile(r"^\s*(?:RED\b|red:|\[red\])")


def is_red(commit: dict) -> bool:
    phases = [v.upper() for v in commit["trailers"].get("TDD-Phase", [])]
    return "RED" in phases or bool(_RED_SUBJECT.match(commit["subject"]))


def done_tasks(project: Project, meta: dict) -> Dict[str, List[str]]:
    """Task id -> commit hashes carrying `Task-Id: <id>` since meta["baseCommit"]."""
    done = {}
    for c in gitutil.commits(meta["baseCommit"], project.root):
        if is_red(c):
            continue
        for value in c["trailers"].get("Task-Id", []):
            for tid in re.split(r"[,\s]+", value):
                if tid:
                    done.setdefault(tid, []).append(c["hash"])
    return done


def _task_boxes(tasks_md: str):
    """(checkbox, task id) for checkbox items that start with a task id."""
    task = re.compile(r"^\s*(%s)\b" % mdparse.ID_PATTERNS["TASK"])
    for box in mdparse.checkboxes(tasks_md):
        m = task.match(box.text)
        if m:
            yield box, m.group(1)


def render(tasks_md: str, done: Dict[str, List[str]]) -> str:
    """tasks.md text with each task's checkbox set from `done` ("x" when done, " " otherwise;
    "~" left untouched). Pure function; no other text changes."""
    lines = tasks_md.splitlines(True)
    for box, tid in _task_boxes(tasks_md):
        if box.state == "~":
            continue
        want = "x" if tid in done else " "
        i = box.line - 1
        lines[i] = re.sub(r"\[[ xX]\]", "[%s]" % want, lines[i], count=1)
    return "".join(lines)


def open_tasks(tasks_md: str, done: Dict[str, List[str]]) -> List[str]:
    """Task ids still open after rendering (what gate 6.5 reports)."""
    return [tid for box, tid in _task_boxes(tasks_md) if box.state != "~" and tid not in done]
