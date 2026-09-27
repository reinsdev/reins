"""Test helpers (owner T2): throwaway git projects and running the CLI inside them."""

import contextlib
import io
import os
import subprocess
import tempfile
from pathlib import Path
from unittest import mock

from tests import CLI_LIB  # noqa: F401
from spec_driven.cli import main


def git(cwd, *args):
    return subprocess.run(["git"] + list(args), cwd=str(cwd), check=True, capture_output=True,
                          encoding="utf-8").stdout.strip()


def commit(cwd, message, files=None):
    for name, text in (files or {"f.txt": message}).items():
        p = Path(cwd) / name
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(text, encoding="utf-8")
    git(cwd, "add", "-A")
    git(cwd, "commit", "-q", "-m", message)
    return git(cwd, "rev-parse", "HEAD")


@contextlib.contextmanager
def java_repo(java=True):
    """A temp git repo with one commit (and a pom.xml); cwd and REINS_HOME point into it."""
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp).resolve() / "proj"
        root.mkdir()
        git(root, "init", "-q", "-b", "main")
        git(root, "config", "user.name", "tester")
        git(root, "config", "user.email", "t@example.com")
        commit(root, "init", {"pom.xml": "<project/>\n"} if java else {"README.md": "x\n"})
        old = os.getcwd()
        os.chdir(str(root))
        try:
            with mock.patch.dict(os.environ, {"REINS_HOME": str(Path(tmp) / "home")}):
                yield root
        finally:
            os.chdir(old)


def cli(*argv):
    """Run the CLI; return (exit code, stdout + stderr)."""
    out = io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(out):
        try:
            code = main(list(argv))
        except SystemExit as e:
            code = e.code if isinstance(e.code, int) else 1
            if not isinstance(e.code, int) and e.code:
                out.write(str(e.code))
    return code, out.getvalue()


def mdparse_ready() -> bool:
    from spec_driven import mdparse
    try:
        mdparse.checkboxes("- [ ] x")
        return True
    except NotImplementedError:
        return False
