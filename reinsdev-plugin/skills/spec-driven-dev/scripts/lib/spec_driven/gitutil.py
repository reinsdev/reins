"""Thin git wrappers. Owner: T2. Every git call in the CLI goes through `git()`.

Rules: pass argv lists (never a shell string), force `-c core.quotepath=false`
and UTF-8 decoding, and fail with `errors.fail()` when git is missing or the
directory is not a repository.
"""

import subprocess
from pathlib import Path
from typing import Dict, List, Optional

from .errors import fail

_FIELD = "\x1f"
_RECORD = "\x1e"


def git(args: List[str], cwd: Path, check: bool = True) -> str:
    """Run git, return stdout stripped."""
    try:
        r = subprocess.run(["git", "-c", "core.quotepath=false"] + list(args), cwd=str(cwd),
                           capture_output=True, encoding="utf-8", errors="replace")
    except OSError:
        fail("找不到 git，请先安装 git")
    if check and r.returncode != 0:
        fail("git %s 失败：%s" % (" ".join(args), (r.stderr or r.stdout).strip()))
    return (r.stdout or "").strip()


def is_repo(cwd: Path) -> bool:
    try:
        r = subprocess.run(["git", "rev-parse", "--is-inside-work-tree"], cwd=str(cwd),
                           capture_output=True, encoding="utf-8", errors="replace")
    except OSError:
        return False
    return r.returncode == 0 and r.stdout.strip() == "true"


def head(cwd: Path) -> str:
    """Full hash of HEAD."""
    return git(["rev-parse", "HEAD"], cwd)


def current_branch(cwd: Path) -> Optional[str]:
    """Branch name, or None when detached."""
    name = git(["symbolic-ref", "--quiet", "--short", "HEAD"], cwd, check=False)
    return name or None


def changed_files(base: str, cwd: Path) -> List[str]:
    """Paths (repo-relative, forward slashes) changed between `base` and the working tree,
    including untracked files not ignored by .gitignore."""
    tracked = git(["diff", "--name-only", "-z", base], cwd).split("\0")
    untracked = git(["ls-files", "--others", "--exclude-standard", "-z"], cwd).split("\0")
    seen, out = set(), []
    for p in tracked + untracked:
        p = p.strip().replace("\\", "/")
        if p and p not in seen:
            seen.add(p)
            out.append(p)
    return out


def _trailers(block: str) -> Dict[str, List[str]]:
    out = {}
    for line in block.splitlines():
        key, sep, value = line.partition(":")
        if sep and key.strip() and " " not in key.strip():
            out.setdefault(key.strip(), []).append(value.strip())
    return out


def commits(base: str, cwd: Path) -> List[Dict]:
    """Commits in base..HEAD, oldest first: {"hash", "subject", "trailers": {key: [values]}}.
    Trailers parsed with `git interpret-trailers --parse` semantics (e.g. Task-Id)."""
    fmt = _FIELD.join(["%H", "%s", "%(trailers:unfold,only)"]) + _RECORD
    raw = git(["log", "--reverse", "--format=" + fmt, "%s..HEAD" % base], cwd)
    out = []
    for rec in raw.split(_RECORD):
        rec = rec.strip("\n")
        if not rec:
            continue
        parts = rec.split(_FIELD)
        if len(parts) < 3:
            continue
        out.append({"hash": parts[0].strip(), "subject": parts[1], "trailers": _trailers(parts[2])})
    return out


def user_name(cwd: Path) -> str:
    """git config user.name, or "unknown"."""
    return git(["config", "user.name"], cwd, check=False) or "unknown"
