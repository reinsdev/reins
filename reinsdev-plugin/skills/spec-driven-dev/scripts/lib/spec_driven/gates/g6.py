"""Verify Java test evidence, TDD commits, scope and changed-line coverage."""

import json
import math
import re
import shlex
from pathlib import PurePosixPath
from typing import List

from . import Finding, GateContext
from .. import gitutil, java, mdparse, taskstate
from ..project import IMPLEMENTATION_LOG, TASKS


def _finding(check, reason, evidence, location="", level="BLOCK"):
    if check != "coverage":
        evidence = re.sub(r"\b(line|column) \d+", r"\1 ?", evidence)
    return Finding(level, check, reason, location=location,
                   fix="补齐真实测试、构建或提交证据后重跑验证门", evidence=evidence)


def _task_ids(commit):
    values = []
    for key, entries in commit.get("trailers", {}).items():
        if key.lower() == "task-id":
            for entry in entries:
                for part in entry.split(","):
                    value = part.strip()
                    if value and mdparse.ids(value, "TASK") == [value]:
                        values.append(value)
                    else:
                        return []
    return values


def _runs_tests(command):
    try:
        tokens = shlex.split(command)
    except ValueError:
        return False
    return any(token in ("test", "package", "verify", "install", "deploy", "integration-test", "check", "build")
               or token.endswith(":test") for token in tokens)


def _runs_build(command):
    try:
        return any(token in ("package", "verify", "install", "deploy", "build")
                   for token in shlex.split(command))
    except ValueError:
        return False


def _rows(section, key, columns):
    found = mdparse.find(section, key)
    if found is None:
        raise ValueError("缺少 %s 章节" % key)
    tables = mdparse.tables(found.body)
    if len(tables) != 1 or not set(columns).issubset(tables[0].header) or not tables[0].rows:
        raise ValueError("%s 表格缺失、重复或列不完整" % key)
    return tables[0].rows


def _log(ctx):
    text = (ctx.change_dir / IMPLEMENTATION_LOG).read_text(encoding="utf-8")
    root = mdparse.parse(text)
    sections = mdparse.find_all(root, mdparse.ID_PATTERNS["TASK"])
    sections = [s for s in sections if mdparse.ids(s.title, "TASK") and
                s.title.lstrip().startswith(mdparse.ids(s.title, "TASK")[0])]
    ids = [mdparse.ids(s.title, "TASK")[0] for s in sections]
    if len(ids) != len(set(ids)):
        raise ValueError("implementation-log.md 任务记录重复")
    task = ctx.extra.get("task")
    if task:
        sections = [s for s in sections if mdparse.ids(s.title, "TASK")[0] == task]
    if not sections:
        raise ValueError("implementation-log.md 缺少%s任务记录" % (" %s 的" % task if task else ""))
    return sections


def _scope(ctx, files):
    text = (ctx.change_dir / TASKS).read_text(encoding="utf-8")
    paths = []
    for box in mdparse.checkboxes(text):
        if "范围：" not in box.text:
            continue
        value = box.text.split("范围：", 1)[1].split("；", 1)[0]
        for item in value.replace("，", ",").split(","):
            path = item.strip().strip("`").replace("\\", "/")
            if not path or PurePosixPath(path).is_absolute() or ".." in PurePosixPath(path).parts:
                raise ValueError("tasks.md 含无效范围路径")
            paths.append(path)
    if not paths:
        raise ValueError("tasks.md 缺少任务范围")
    return sorted(path for path in files if not path.startswith(".openspec/") and
                  not any(path == scope.rstrip("/") or path.startswith(scope.rstrip("/") + "/")
                          for scope in paths))


def check(ctx: GateContext) -> List[Finding]:
    findings = []
    settings = ctx.config.get("test", {})
    if not isinstance(settings, dict):
        return [_finding("test-execution", "test 配置必须是对象", "invalid-test-config")]
    base = ctx.meta.get("baseCommit")
    try:
        if not isinstance(base, str) or not base or base.startswith("-"):
            raise ValueError("缺少有效的 baseCommit")
        files = gitutil.git(["-c", "core.quotePath=false", "diff", "--name-only", "--diff-filter=AMR", base, "HEAD", "--"], ctx.project.root).splitlines()
        all_files = gitutil.git(["-c", "core.quotePath=false", "diff", "--name-only", base, "HEAD", "--"], ctx.project.root).splitlines()
        parsed_commits = {c["hash"]: c for c in gitutil.commits(base, ctx.project.root)}
        hashes = gitutil.git(["rev-list", "--reverse", "%s..HEAD" % base, "--"], ctx.project.root).splitlines()
        # Check every commit even if its trailer record was unavailable.
        commits = [parsed_commits.get(value, {"hash": value, "subject": "", "trailers": {}}) for value in hashes]
    except (ValueError, OSError, SystemExit) as exc:
        return [_finding("git-evidence", "无法读取基线后的改动：%s" % exc, "base:%s" % base)]
    tests = [path for path in files if "/src/test/java/" in "/" + path]
    if not tests:
        warn = (ctx.meta.get("complexity") == "S" and ctx.meta.get("mode") != "bugfix") or settings.get("require_tests") is False
        findings.append(_finding("test-files", "本次提交没有新增或改动 src/test/java 测试文件", "no-changed-java-tests", level="WARN" if warn else "BLOCK"))
    integration = settings.get("integration", {})
    required = integration.get("required") if isinstance(integration, dict) else integration
    has_integration = any(PurePosixPath(path).stem.endswith(("IT", "ITCase", "IntegrationTest")) for path in tests)
    if not has_integration and (required is True or (required == "auto" and ctx.meta.get("qa_mode") == "full")):
        findings.append(_finding("integration-tests", "缺少新增或改动的集成测试文件", "integration:%s" % required,
                                 level="BLOCK" if required is True else "WARN"))
    try:
        result = java.test_reports(ctx.project.root, settings.get("report_path"))
        executed = result["tests"] - result["skipped"]
        if executed <= 0 or result["failures"] or result["errors"]:
            findings.append(_finding("test-execution", "测试未实际跑绿：运行 %s，失败 %s，错误 %s，跳过 %s" %
                                     (executed, result["failures"], result["errors"], result["skipped"]),
                                     json.dumps(result, sort_keys=True)))
    except (ValueError, OSError, TypeError, KeyError) as exc:
        findings.append(_finding("test-execution", "无法验证测试报告：%s" % exc, "test-report:%s" % exc))
    commands = [settings["command"]] if settings.get("command") else []
    try:
        sections = _log(ctx)
        if not ctx.extra.get("task"):
            completed = {task for commit in commits if not taskstate.is_red(commit) for task in _task_ids(commit)}
            logged = {mdparse.ids(section.title, "TASK")[0] for section in sections}
            missing = sorted(completed - logged)
            if missing:
                raise ValueError("任务缺少实现日志：%s" % ", ".join(missing))
    except (ValueError, OSError, TypeError) as exc:
        sections = []
        findings.append(_finding("implementation-log", "实现日志无效：%s" % exc,
                                 "implementation-log:%s" % exc, IMPLEMENTATION_LOG))
    for section in sections:
        task = mdparse.ids(section.title, "TASK")[0]
        try:
            for row in _rows(section, "green", ("命令", "退出码", "运行数", "失败数", "跳过数", "证据位置")):
                commands.append(row["命令"])
                if (int(row["退出码"]) != 0 or int(row["运行数"]) <= 0 or int(row["失败数"]) != 0
                        or int(row["跳过数"]) < 0 or int(row["运行数"]) <= int(row["跳过数"])
                        or not _runs_tests(row["命令"]) or not row["证据位置"].strip()):
                    raise ValueError("GREEN 必须记录真实测试命令、成功退出和实际运行数")
        except (ValueError, TypeError) as exc:
            findings.append(_finding("test-log", "%s 测试日志无效：%s" % (task, exc),
                                     "%s:%s" % (task, exc), IMPLEMENTATION_LOG))
        try:
            for row in _rows(section, "build", ("命令", "退出码", "结果", "证据位置")):
                commands.append(row["命令"])
                if int(row["退出码"]) != 0 or not _runs_build(row["命令"]) or row["结果"].strip().upper() not in ("PASS", "SUCCESS", "BUILD SUCCESS", "BUILD SUCCESSFUL", "通过", "成功") or not row["证据位置"].strip():
                    raise ValueError("完整构建必须成功并记录证据")
        except (ValueError, TypeError) as exc:
            findings.append(_finding("build", "%s 构建记录无效：%s" % (task, exc), "%s:%s" % (task, exc), IMPLEMENTATION_LOG))
    try:
        skipped = java.skip_reasons(ctx.project.root, commands)
        if skipped:
            findings.append(_finding("test-skip", "检测到跳过测试：%s" % "；".join(skipped), "\n".join(sorted(skipped))))
    except (ValueError, OSError, TypeError) as exc:
        findings.append(_finding("test-skip", "无法确认测试未被跳过：%s" % exc, "skip-config:%s" % exc))
    try:
        declared_text = (ctx.change_dir / TASKS).read_text(encoding="utf-8")
        declared = set(mdparse.ids(declared_text, "TASK"))
        for commit in commits:
            paths = gitutil.git(["diff-tree", "--root", "--no-commit-id", "--name-only", "-r", "-m", commit["hash"], "--"], ctx.project.root).splitlines()
            ids = _task_ids(commit)
            if any(not path.startswith(".openspec/") for path in paths) and (not ids or not set(ids).issubset(declared)):
                findings.append(_finding("task-id", "提交 %s 缺少合法的 Task-Id trailer" % commit["hash"][:8],
                                         commit["hash"] + ":" + ",".join(ids)))
        selected = ctx.extra.get("task")
        tasks = {selected} if selected else {task for commit in commits for task in _task_ids(commit)}
        for task in sorted(tasks):
            relevant = [c for c in commits if task in _task_ids(c)]
            red = [i for i, c in enumerate(relevant) if taskstate.is_red(c)]
            green = [i for i, c in enumerate(relevant) if not taskstate.is_red(c)]
            if not red:
                findings.append(_finding("red-before-green", "%s 缺少 RED 提交证据" % task, task + ":missing-red", level="WARN"))
            elif green and red[0] > green[0]:
                findings.append(_finding("red-before-green", "%s 的 RED 提交晚于实现提交" % task, task + ":red-after-green"))
    except (ValueError, OSError, TypeError, KeyError, SystemExit) as exc:
        findings.append(_finding("task-id", "无法核对任务提交：%s" % exc, "task-commits:%s" % exc))
    try:
        outside = _scope(ctx, all_files)
        if outside:
            findings.append(_finding("scope", "提交超出任务范围：%s" % ", ".join(outside), "\n".join(outside), TASKS))
    except (ValueError, OSError, TypeError) as exc:
        findings.append(_finding("scope", "无法核对任务范围：%s" % exc, "scope:%s" % exc, TASKS))
    try:
        coverage = settings.get("coverage", {})
        threshold = coverage.get("diff_threshold", 80)
        if isinstance(threshold, bool):
            raise ValueError("覆盖率阈值必须是 0 到 100 的数字")
        threshold = float(threshold)
        if not math.isfinite(threshold) or not 0 <= threshold <= 100:
            raise ValueError("覆盖率阈值必须是 0 到 100 的数字")
        result = java.diff_coverage(ctx.project.root, java.changed_lines(ctx.project.root, base), coverage.get("report_path"))
        if result["percent"] < threshold:
            evidence = json.dumps({"covered": result["covered"], "total": result["total"],
                                   "percent": result["percent"], "threshold": threshold,
                                   "uncovered": sorted(result["uncovered"])}, sort_keys=True)
            findings.append(_finding("coverage", "增量覆盖率 %.2f%% < %.2f%%；未覆盖：%s" %
                                     (result["percent"], threshold, ", ".join(result["uncovered"])), evidence))
    except (ValueError, OSError, TypeError, KeyError, AttributeError, SystemExit) as exc:
        findings.append(_finding("coverage", "无法计算增量覆盖率：%s" % exc, "coverage:%s" % exc))
    return findings
