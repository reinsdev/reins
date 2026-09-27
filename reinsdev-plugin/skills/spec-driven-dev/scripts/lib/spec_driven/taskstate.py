"""Task completion derived from git, never from hand-ticked boxes (workflow §10.5). Owner: T2.

Used read-only by `tasks-sync` (which may write tasks.md) and by gate 6.5.
"""

from typing import Dict, List

from .project import Project


def done_tasks(project: Project, meta: dict) -> Dict[str, List[str]]:
    """Task id -> commit hashes carrying `Task-Id: <id>` since meta["baseCommit"]."""
    raise NotImplementedError


def render(tasks_md: str, done: Dict[str, List[str]]) -> str:
    """tasks.md text with each task's checkbox set from `done` ("x" when done, " " otherwise;
    "~" left untouched). Pure function; no other text changes."""
    raise NotImplementedError


def open_tasks(tasks_md: str, done: Dict[str, List[str]]) -> List[str]:
    """Task ids still open after rendering (what gate 6.5 reports)."""
    raise NotImplementedError
