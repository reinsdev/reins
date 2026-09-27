"""Where each platform's CLI and configuration live."""

import os
import shutil
from pathlib import Path

TARGETS = ["claude", "codex", "opencode"]

# Official installers' default directories. They add these to PATH only in
# interactive shell profiles, so GUI apps and non-interactive shells miss them.
INSTALLER_DIRS = ["~/.local/bin", "~/.claude/local", "~/.opencode/bin"]


def find_cli(name: str):
    """Absolute path of a platform CLI, searching PATH, then INSTALLER_DIRS."""
    extra = os.pathsep.join(str(Path(d).expanduser()) for d in INSTALLER_DIRS)
    return shutil.which(name) or shutil.which(name, path=extra)


def detected():
    return [n for n in TARGETS if find_cli(n)]


def codex_home() -> Path:
    return Path(os.environ.get("CODEX_HOME") or Path.home() / ".codex")


def opencode_config_dir() -> Path:
    if os.environ.get("OPENCODE_CONFIG_DIR"):
        return Path(os.environ["OPENCODE_CONFIG_DIR"])
    base = os.environ.get("XDG_CONFIG_HOME") or str(Path.home() / ".config")
    return Path(base) / "opencode"
