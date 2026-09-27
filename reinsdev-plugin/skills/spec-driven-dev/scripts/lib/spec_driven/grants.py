"""One-time authorizations for waive / downgrade (design doc §6.6). Owner: T6.

Only the UserPromptSubmit hook issues a grant (policies/waive_grant), and only when
the user's own prompt is exactly a confirmation phrase and the thing it confirms is
live (a current BLOCK, or a tier below the current one). `waive` and
`complexity set --downgrade` consume one and refuse without it. Grants live in
<REINS_HOME>/grants/, which the pre-tool policies protect from model writes.

This module only matches phrases and stores / consumes grants; deciding whether a
phrase confirms something live needs the gates, so it lives in the policy.
"""

import hashlib
import json
import os
import re
import time
import uuid
from pathlib import Path
from typing import Optional

from .paths import reins_home

TTL = 600  # seconds

# The whole prompt must match (after trimming); anything else issues nothing.
WAIVE_PHRASE = r"^确认放行\s+(?P<change>\S+)\s+(?P<gate>\S+)\s+(?P<check>\S+)$"
DOWNGRADE_PHRASE = r"^确认降档\s+(?P<change>\S+)\s+(?P<tier>[SML])$"


def grants_dir() -> Path:
    return reins_home() / "grants"


def match_phrase(prompt: str) -> Optional[dict]:
    """{"action": "waive", "change", "gate", "check"} or {"action": "downgrade", "change", "tier"},
    or None when the prompt is not exactly a confirmation phrase."""
    text = (prompt or "").strip()
    m = re.match(WAIVE_PHRASE, text)
    if m:
        return dict(m.groupdict(), action="waive")
    m = re.match(DOWNGRADE_PHRASE, text)
    if m:
        return dict(m.groupdict(), action="downgrade")
    return None


def _root(project_root: Path) -> str:
    return str(Path(project_root).resolve())


def _name(project_root: Path, change: str, action: str, key: str) -> str:
    raw = "\n".join([_root(project_root), change, action, key])
    return hashlib.sha1(raw.encode("utf-8")).hexdigest()[:20] + ".json"


def issue(project_root: Path, change: str, action: str, key: str, fingerprint: str) -> Path:
    """Write (or replace) the grant for this project / change / action / key.
    action "waive": key "<gate> <check>", fingerprint the sorted live fingerprints joined by ",";
    action "downgrade": key the target tier, fingerprint ""."""
    d = grants_dir()
    d.mkdir(parents=True, exist_ok=True)
    path = d / _name(project_root, change, action, key)
    data = {"project": _root(project_root), "change": change, "action": action, "key": key,
            "fingerprint": fingerprint, "expiresAt": time.time() + TTL}
    tmp = d / (path.name + ".%s.tmp" % uuid.uuid4().hex)
    tmp.write_bytes(json.dumps(data, ensure_ascii=False).encode("utf-8"))
    os.replace(str(tmp), str(path))
    return path


def consume(project_root: Path, change: str, action: str, key: str, fingerprint: str) -> bool:
    """Atomically take a matching, unexpired grant (action "waive": key "<gate> <check>";
    action "downgrade": key the target tier). True when one was taken."""
    path = grants_dir() / _name(project_root, change, action, key)
    taken = path.with_name(path.name + ".taken-%s" % uuid.uuid4().hex)
    try:
        os.rename(str(path), str(taken))  # only one consumer can win the rename
    except OSError:
        return False
    try:
        data = json.loads(taken.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return False
    finally:
        try:
            taken.unlink()
        except OSError:
            pass
    return (data.get("project") == _root(project_root) and data.get("change") == change
            and data.get("action") == action and data.get("key") == key
            and data.get("fingerprint") == fingerprint and time.time() < data.get("expiresAt", 0))
