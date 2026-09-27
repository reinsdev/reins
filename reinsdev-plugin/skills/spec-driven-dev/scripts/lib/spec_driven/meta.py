"""`.meta.json`: flow state of one change (design doc §3.2). Owner: T2.

Only flow state lives here (where the change is, where it goes next). Audit
records (waivers, tier changes, todo items) go to retrospective.md via retro.py.
Every write goes through `update()`, which holds the change lock.
"""

from contextlib import contextmanager
from pathlib import Path
from typing import Callable, Iterator

# Phase order of the state machine (§3.3). Gates 6.5 and 6.7 are sub-gates of
# phase 6 and have no phaseStatus entry of their own.
PHASES = ["0", "1", "2", "3", "4", "5", "6", "7", "8", "8.5", "8.9", "9"]
GATES = ["0", "1", "2", "3", "4", "5", "6", "6.5", "6.7", "7", "8", "8.5", "8.9", "9"]

STATUSES = ("pending", "in_progress", "passed", "skipped", "stale", "blocked")
MODES = ("feature", "bugfix")
TIERS = ("S", "M", "L")

LOCK_TIMEOUT = 10.0  # seconds to wait for the lock
LOCK_STALE = 60.0    # a lock file older than this is considered abandoned


def new(change: str, mode: str, branch: str, base_commit: str) -> dict:
    """A fresh meta for Phase 0: provisional M, tierConfirmed false, phase "0" in_progress,
    every other phase pending. Keys and value types exactly as in §3.2."""
    raise NotImplementedError


def load(change_dir: Path) -> dict:
    """Read and validate `.meta.json`; `errors.fail()` with a clear message when missing or invalid."""
    raise NotImplementedError


@contextmanager
def lock(change_dir: Path) -> Iterator[None]:
    """Exclusive lock via `os.open(<change_dir>/.meta.lock, O_CREAT | O_EXCL)`, with
    LOCK_TIMEOUT and stale-lock cleanup; identical behaviour on macOS, Linux, Windows."""
    raise NotImplementedError
    yield  # pragma: no cover


def save(change_dir: Path, meta: dict) -> None:
    """Atomic write (temp file + os.replace), UTF-8, indent 2, key order as §3.2. Caller holds the lock."""
    raise NotImplementedError


def update(change_dir: Path, fn: Callable[[dict], None]) -> dict:
    """Lock, load, let `fn` mutate the dict in place, validate, save; return the new meta."""
    raise NotImplementedError
