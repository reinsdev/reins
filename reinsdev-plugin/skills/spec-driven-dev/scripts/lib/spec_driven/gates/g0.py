"""Check Phase 0 prerequisites. Owner: T3.

Checks:
- java-project: require a Java build file at the project root or an ancestor.
- change-name: require a lowercase kebab-case name of at least five characters.
- change-artifacts: require the change directory and proposal.
- change-mode: require feature or bugfix mode.
"""

import re
from typing import List

from . import Finding, GateContext
from ..project import PROPOSAL


def check(ctx: GateContext) -> List[Finding]:
    findings = []
    roots = [ctx.project.root] + list(ctx.project.root.parents)
    try:
        java = any((root / name).is_file() for root in roots
                   for name in ("pom.xml", "build.gradle", "build.gradle.kts"))
    except OSError:
        java = False
    if not java:
        findings.append(Finding(
            "BLOCK", "java-project", "Reins 只支持 Java 项目",
            fix="在项目根或上级目录提供 pom.xml / build.gradle(.kts)",
            evidence="missing-java-build"))
    if (not isinstance(ctx.change, str) or len(ctx.change) < 5
            or not re.fullmatch(r"[a-z][a-z0-9]*(?:-[a-z0-9]+)*", ctx.change)):
        findings.append(Finding(
            "BLOCK", "change-name", "change 名必须是至少 5 个字符的小写 kebab-case",
            fix="使用例如 batch-approve 的名称", evidence=str(ctx.change)))
    try:
        exists = ctx.change_dir.is_dir() and (ctx.change_dir / PROPOSAL).is_file()
    except OSError:
        exists = False
    if not exists:
        findings.append(Finding(
            "BLOCK", "change-artifacts", "change 目录或 proposal.md 缺失",
            location=PROPOSAL, fix="先完成 change 初始化", evidence="missing-proposal"))
    if ctx.meta.get("mode") not in ("feature", "bugfix"):
        findings.append(Finding(
            "BLOCK", "change-mode", "mode 必须为 feature 或 bugfix",
            location=".meta.json", fix="通过 CLI 重新初始化正确模式的 change",
            evidence=str(ctx.meta.get("mode"))))
    return findings
