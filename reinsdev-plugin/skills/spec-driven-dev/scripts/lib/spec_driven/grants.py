"""One-time authorizations for waive / downgrade (design doc §6.6). Owner: T6.

Only the UserPromptSubmit hook issues a grant, and only when the user's own
prompt is exactly a confirmation phrase. `waive` and `complexity set --downgrade`
consume one and refuse without it. Grants live in <REINS_HOME>/grants/, which
the pre-tool policies protect from model writes.
"""

from pathlib import Path
from typing import Optional

from .paths import reins_home

TTL = 600  # seconds

# The whole prompt must match (after trimming); anything else issues nothing.
WAIVE_PHRASE = r"^确认放行\s+(?P<change>\S+)\s+(?P<gate>\S+)\s+(?P<check>\S+)$"
DOWNGRADE_PHRASE = r"^确认降档\s+(?P<change>\S+)\s+(?P<tier>[SML])$"


def grants_dir() -> Path:
    return reins_home() / "grants"


def issue_from_prompt(prompt: str, project_root: Path) -> Optional[str]:
    """If `prompt` is a confirmation phrase for a change that currently needs it (a live
    BLOCK with that gate/check, or a downgrade target below the current tier), write a
    grant bound to project, change, action and fingerprint; return a short note for the
    user, else None."""
    raise NotImplementedError


def consume(project_root: Path, change: str, action: str, key: str, fingerprint: str) -> bool:
    """Atomically take a matching, unexpired grant (action "waive": key "<gate> <check>";
    action "downgrade": key the target tier). True when one was taken."""
    raise NotImplementedError
