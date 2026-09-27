"""reinsdev, the Reins installer: installs the plugin from the checkout it
runs from into the local Claude Code / Codex / OpenCode, checks the setup,
updates and uninstalls. Users get it from the one-line installer (install.sh /
install.ps1); it is never part of the plugin."""

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
PLUGIN = ROOT / "reinsdev-plugin"

# Shared with the plugin's bundled CLI: VERSION, reins_home(), frontmatter.
_lib = str(PLUGIN / "skills" / "spec-driven-dev" / "scripts" / "lib")
if _lib not in sys.path:
    sys.path.insert(0, _lib)
