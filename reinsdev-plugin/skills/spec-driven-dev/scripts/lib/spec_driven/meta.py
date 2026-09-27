"""`.meta.json`: flow state of one change (design doc §3.2). Owner: T2.

Only flow state lives here (where the change is, where it goes next). Audit
records (waivers, tier changes, todo items) go to retrospective.md via retro.py.
Every write goes through `update()`, which holds the change lock.
"""

import json
import os
import time
import uuid
from contextlib import contextmanager
from pathlib import Path
from typing import Callable, Iterator

from .errors import fail
from .project import META

# Phase order of the state machine (§3.3). Gates 6.5 and 6.7 are sub-gates of
# phase 6 and have no phaseStatus entry of their own.
PHASES = ["0", "1", "2", "3", "4", "5", "6", "7", "8", "8.5", "8.9", "9"]
GATES = ["0", "1", "2", "3", "4", "5", "6", "6.5", "6.7", "7", "8", "8.5", "8.9", "9"]

STATUSES = ("pending", "in_progress", "passed", "skipped", "stale", "blocked")
MODES = ("feature", "bugfix")
TIERS = ("S", "M", "L")

# Phases whose running depends on tier or mode (router.skip_reason).
CONDITIONAL = ("2", "3", "5", "7")

LOCK_TIMEOUT = 10.0  # seconds to wait for the lock
LOCK_STALE = 60.0    # a lock file older than this is considered abandoned
LOCK_FILE = ".meta.lock"

# Key order written to disk, as in §3.2. `bugfixScope` is optional: the bugfix skill's
# assessment {"files": int, "crossService": bool, "ddl": bool, "publicApi": bool} that
# router uses to skip phases 2 / 3; absent means "run them".
KEYS = ["change", "mode", "source", "defect_code", "complexity", "tierConfirmed", "phase",
        "phaseStatus", "skipped", "designDecision", "branch", "baseCommit", "uatAccepted",
        "uatAcceptedAt", "staleFrom", "bugfixScope"]
REQUIRED = KEYS[:-1]


def tier_rank(tier: str) -> int:
    return TIERS.index(tier)


def new(change: str, mode: str, branch: str, base_commit: str) -> dict:
    """A fresh meta for Phase 0: provisional M, tierConfirmed false, phase "0" in_progress,
    every other phase pending. Keys and value types exactly as in §3.2."""
    if mode not in MODES:
        raise ValueError("mode %r" % mode)
    status = {p: "pending" for p in PHASES}
    status["0"] = "in_progress"
    return {
        "change": change,
        "mode": mode,
        "source": None,
        "defect_code": None,
        "complexity": "M",
        "tierConfirmed": False,
        "phase": "0",
        "phaseStatus": status,
        "skipped": {p: None for p in CONDITIONAL},
        "designDecision": None,
        "branch": branch,
        "baseCommit": base_commit,
        "uatAccepted": False,
        "uatAcceptedAt": None,
        "staleFrom": None,
    }


def validate(meta: dict) -> None:
    """Raise ValueError naming the first problem."""
    missing = [k for k in REQUIRED if k not in meta]
    if missing:
        raise ValueError("缺少字段 %s" % "、".join(missing))
    if meta["mode"] not in MODES:
        raise ValueError("mode=%r 无效" % meta["mode"])
    if meta["complexity"] not in TIERS:
        raise ValueError("complexity=%r 无效" % meta["complexity"])
    if meta["phase"] not in PHASES:
        raise ValueError("phase=%r 无效" % meta["phase"])
    if not isinstance(meta["phaseStatus"], dict) or not isinstance(meta["skipped"], dict):
        raise ValueError("phaseStatus / skipped 必须是对象")
    for p, s in meta["phaseStatus"].items():
        if p not in PHASES or s not in STATUSES:
            raise ValueError("phaseStatus.%s=%r 无效" % (p, s))
    for p in meta["skipped"]:
        if p not in PHASES:
            raise ValueError("skipped.%s 不是 Phase" % p)


def load(change_dir: Path) -> dict:
    """Read and validate `.meta.json`; `errors.fail()` with a clear message when missing or invalid."""
    path = Path(change_dir) / META
    if not path.is_file():
        fail("%s 不存在：这个 change 还没建好，或目录不对" % path)
    try:
        meta = json.loads(path.read_text(encoding="utf-8"))
        validate(meta)
    except ValueError as e:
        fail("%s 无效：%s" % (path, e))
    return meta


@contextmanager
def lock(change_dir: Path) -> Iterator[None]:
    """Exclusive lock via `os.open(<change_dir>/.meta.lock, O_CREAT | O_EXCL)`, with
    LOCK_TIMEOUT and stale-lock cleanup; identical behaviour on macOS, Linux, Windows."""
    path = Path(change_dir) / LOCK_FILE
    owner = "%s:%s" % (os.getpid(), uuid.uuid4().hex)
    deadline = time.monotonic() + LOCK_TIMEOUT
    while True:
        try:
            fd = os.open(str(path), os.O_CREAT | os.O_EXCL | os.O_WRONLY)
            break
        except FileExistsError:
            try:
                if time.time() - path.stat().st_mtime > LOCK_STALE:
                    path.unlink()
                    continue
            except OSError:
                continue  # holder released it between our calls
            if time.monotonic() > deadline:
                fail("%s 被另一个进程占用（锁文件 %s）；确认没有其他命令在运行后删除它" % (change_dir, path))
            time.sleep(0.05)
    try:
        try:
            os.write(fd, owner.encode("ascii"))
        finally:
            os.close(fd)
        yield
    finally:
        try:
            if path.read_text(encoding="utf-8") == owner:
                path.unlink()
        except (OSError, UnicodeError):
            pass


def save(change_dir: Path, meta: dict) -> None:
    """Atomic write (temp file + os.replace), UTF-8, indent 2, key order as §3.2. Caller holds the lock."""
    validate(meta)
    ordered = {k: meta[k] for k in KEYS if k in meta}
    ordered.update({k: v for k, v in meta.items() if k not in ordered})
    path = Path(change_dir) / META
    tmp = path.with_name(META + ".tmp")
    tmp.write_bytes((json.dumps(ordered, ensure_ascii=False, indent=2) + "\n").encode("utf-8"))
    os.replace(str(tmp), str(path))


def update(change_dir: Path, fn: Callable[[dict], None]) -> dict:
    """Lock, load, let `fn` mutate the dict in place, validate, save; return the new meta."""
    with lock(change_dir):
        meta = load(change_dir)
        fn(meta)
        try:
            save(change_dir, meta)
        except ValueError as e:
            fail("写入 .meta.json 被拒绝：%s" % e)
        return meta
