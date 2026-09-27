"""Repository tests. Put the plugin's bundled CLI and the repo tools on sys.path."""
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PLUGIN = os.path.join(ROOT, "reinsdev-plugin")
CLI_LIB = os.path.join(PLUGIN, "skills", "spec-driven-dev", "scripts", "lib")
for p in (CLI_LIB, os.path.join(ROOT, "tools")):
    if p not in sys.path:
        sys.path.insert(0, p)
