"""Well-known locations."""

import os
from pathlib import Path


def reins_home() -> Path:
    """Where hook logs and local install records live (~/.reins)."""
    return Path(os.environ.get("REINS_HOME", Path.home() / ".reins"))

