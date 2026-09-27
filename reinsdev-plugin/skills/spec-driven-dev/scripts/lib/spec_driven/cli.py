"""Command-line entry point. Subcommands live in commands/ (see commands/__init__.py)."""

import argparse
import sys
from importlib import import_module

from .commands import COMMANDS


def _utf8_stdio():
    # Windows consoles and pipes default to the ANSI code page; runtimes read
    # hook output as UTF-8, and Chinese messages must survive either way.
    for stream in (sys.stdin, sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, ValueError):
            pass


def main(argv=None) -> int:
    _utf8_stdio()
    p = argparse.ArgumentParser(prog="spec-driven", description="Reins 规格驱动工件链 CLI（内部命令，由总控和平台 hook 调用；安装与检查用 reinsdev）")
    sub = p.add_subparsers(dest="cmd", required=True)
    modules = {}
    for name in COMMANDS:
        mod = import_module("%s.commands.%s" % (__package__, name))
        before = set(sub.choices)
        mod.register(sub)
        for cmd in set(sub.choices) - before:
            modules[cmd] = mod
    a = p.parse_args(argv)
    return modules[a.cmd].run(a)
