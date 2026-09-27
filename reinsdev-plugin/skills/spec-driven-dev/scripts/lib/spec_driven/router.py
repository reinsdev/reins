"""Phase routing (design doc §3.3). Owner: T2.

Pure functions of (meta, config): no file or git access, so every rule is unit-testable.
"""

from typing import Optional


def skip_reason(phase: str, meta: dict) -> Optional[str]:
    """Why a conditional phase (2, 3, 5, 7) is skipped for this tier / mode, or None if it runs.
    Phase 8.5 is never skipped here: the controller asks the user."""
    raise NotImplementedError


def next_phase(meta: dict, config: dict) -> Optional[str]:
    """The phase the controller should work on next: the first phase (in meta.PHASES order)
    whose status is not passed/skipped; stale phases come first. None when archived."""
    raise NotImplementedError


def review_rounds(meta: dict) -> int:
    """Rounds of spec review in Phase 5: 0 for S, 1 for M, 2 for L."""
    raise NotImplementedError
