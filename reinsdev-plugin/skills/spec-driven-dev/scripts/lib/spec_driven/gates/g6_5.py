"""Check task completion from commit evidence without rewriting artifacts."""

from typing import List

from . import Finding, GateContext
from .. import mdparse, taskstate
from ..project import TASKS


def check(ctx: GateContext) -> List[Finding]:
    settings = ctx.config.get("tasks", {})
    if not isinstance(settings, dict):
        return [Finding("BLOCK", "tasks-artifact", "tasks 配置必须是对象", evidence="invalid-tasks-config")]
    if settings.get("completion_gate") == "off":
        return []
    try:
        text = (ctx.change_dir / TASKS).read_text(encoding="utf-8")
        boxes = mdparse.checkboxes(text)
        ids = []
        for box in boxes:
            found = mdparse.ids(box.text, "TASK")
            if not found or not box.text.lstrip().startswith(found[0]):
                raise ValueError("任务缺少有效的 T 编号")
            ids.append(found[0])
        if not ids or len(set(ids)) != len(ids):
            raise ValueError("任务清单为空或任务编号重复")
        if not ctx.meta.get("baseCommit"):
            raise ValueError("缺少 baseCommit，无法核对提交")
        done = taskstate.done_tasks(ctx.project, ctx.meta)
        remaining = taskstate.open_tasks(text, done)
    except (OSError, ValueError, TypeError, KeyError, SystemExit) as exc:
        return [Finding("BLOCK", "tasks-artifact", "无法判定任务完成情况：%s" % exc,
                        location=TASKS, fix="补齐任务清单和基线提交后重试", evidence="tasks-artifact:%s" % exc)]
    level = "WARN" if ctx.meta.get("complexity") == "S" and ctx.meta.get("mode") != "bugfix" else "BLOCK"
    findings = []
    if remaining:
        value = ", ".join(sorted(remaining))
        findings.append(Finding(level, "tasks-complete", "任务尚无完成提交：%s" % value,
                                location=TASKS, fix="完成任务并提交 Task-Id，或明确延期", evidence=value))
    if settings.get("allow_deferred", True) is False:
        deferred = sorted(ids[i] for i, box in enumerate(boxes) if box.state == "~")
        if deferred:
            value = ", ".join(deferred)
            findings.append(Finding(level, "tasks-deferred", "配置不允许延期任务：%s" % value,
                                    location=TASKS, fix="完成延期任务", evidence=value))
    return findings
