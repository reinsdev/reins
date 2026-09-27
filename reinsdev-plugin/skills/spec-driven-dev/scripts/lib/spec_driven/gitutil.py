"""Thin git wrappers. Owner: T2. Every git call in the CLI goes through `git()`.

Rules: pass argv lists (never a shell string), force `-c core.quotepath=false`
and UTF-8 decoding, and fail with `errors.fail()` when git is missing or the
directory is not a repository.
"""

from pathlib import Path
from typing import Dict, List, Optional


def git(args: List[str], cwd: Path, check: bool = True) -> str:
    """Run git, return stdout stripped."""
    raise NotImplementedError


def is_repo(cwd: Path) -> bool:
    raise NotImplementedError


def head(cwd: Path) -> str:
    """Full hash of HEAD."""
    raise NotImplementedError


def current_branch(cwd: Path) -> Optional[str]:
    """Branch name, or None when detached."""
    raise NotImplementedError


def changed_files(base: str, cwd: Path) -> List[str]:
    """Paths (repo-relative, forward slashes) changed between `base` and the working tree,
    including untracked files not ignored by .gitignore."""
    raise NotImplementedError


def commits(base: str, cwd: Path) -> List[Dict]:
    """Commits in base..HEAD, oldest first: {"hash", "subject", "trailers": {key: [values]}}.
    Trailers parsed with `git interpret-trailers --parse` semantics (e.g. Task-Id)."""
    raise NotImplementedError


def user_name(cwd: Path) -> str:
    """git config user.name, or "unknown"."""
    raise NotImplementedError
