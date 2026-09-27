"""Command-line entry point of reinsdev, the Reins installer."""

import argparse
import sys

from .platforms import TARGETS

TARGET_HELP = "平台：%s，逗号分隔多个；all；detected（本机已装的）" % " / ".join(TARGETS)


def main(argv=None) -> int:
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, ValueError):
            pass
    p = argparse.ArgumentParser(prog="reinsdev", description="Reins 安装工具：把 Reins 装到本机的 Claude Code / Codex / OpenCode")
    sub = p.add_subparsers(dest="cmd", required=True)

    sub.add_parser("version", help="显示版本")

    i = sub.add_parser("install", help="安装到各平台")
    i.add_argument("--target", default="detected", help=TARGET_HELP + "（默认 detected）")
    i.add_argument("--dry-run", action="store_true")
    i.add_argument("--force", action="store_true", help="允许覆盖非 Reins 安装的同名文件")

    up = sub.add_parser("update", help="拉取最新版本并重装已安装的平台")
    up.add_argument("--dry-run", action="store_true")

    u = sub.add_parser("uninstall", help="撤销 install")
    u.add_argument("--target", default="all", help=TARGET_HELP + "（默认 all）")
    u.add_argument("--dry-run", action="store_true")

    sub.add_parser("doctor", help="检查环境与各平台护栏落实情况")

    st = sub.add_parser("setup", help="平台的一次性设置（Codex：安装 agents）")
    st.add_argument("runtime", choices=TARGETS)
    st.add_argument("--project", action="store_true", help="装到当前项目的 .codex/agents/")
    st.add_argument("--force", action="store_true")

    a = p.parse_args(argv)
    if a.cmd == "version":
        from spec_driven import VERSION
        print(VERSION)
        return 0
    if a.cmd == "doctor":
        from . import doctor
        return doctor.run()
    from . import install
    if a.cmd == "setup":
        return install.run_setup(a.runtime, a.project, a.force)
    if a.cmd == "install":
        return install.run_install(a.target, a.dry_run, a.force)
    if a.cmd == "update":
        return install.run_update(a.dry_run)
    return install.run_uninstall(a.target, a.dry_run)
