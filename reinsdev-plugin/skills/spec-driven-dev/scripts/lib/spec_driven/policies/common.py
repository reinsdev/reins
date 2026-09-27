"""Shared by the T6 policies: where an event happens and whether writing a path is allowed.
Owner: T6. Pure reads of the file system; never raises for a missing project."""

import json
import os
from pathlib import Path
from typing import Optional

from .. import grants
from .. import project as P
from ..meta import PHASES
from ..project import Project

# Files only the CLI writes.
CLI_FILES = {P.META, ".meta.lock", P.RETROSPECTIVE, ".retro.sha256"}
# Project-level files the model must not edit (they could loosen the gates).
PROTECTED = {".config.json": "团队配置 .openspec/.config.json 只能由用户本人修改",
             "quality-baseline.json": "质量基线只能由 init-config 生成、由归档收缩"}

# Phase that produces each artifact; editing it in a later phase breaks the upstream freeze.
ARTIFACT_PHASE = {
    P.PROPOSAL: "1", P.BUGFIX_ANALYSIS: "1", P.DESIGN: "2", P.SPEC: "3", P.TASKS: "4",
    P.SPEC_REVIEW: "5", P.IMPLEMENTATION_LOG: "6", P.STATIC_ANALYSIS: "6", P.QA_REPORT: "7",
    P.CODE_REVIEW: "8", P.DEPLOY_REPORT: "8.5",
}
EVALUATOR_REPORT = {"spec-evaluator": P.SPEC_REVIEW, "qa-evaluator": P.QA_REPORT, "code-reviewer": P.CODE_REVIEW}
GENERATOR = "implementation-generator"


def cwd_of(ev: dict) -> Path:
    return Path(ev.get("cwd") or os.getcwd())


def project_of(ev: dict) -> Optional[Project]:
    p = Project.here(cwd_of(ev))
    return p if p.enabled else None


def abs_path(ev: dict, raw: str) -> Path:
    path = Path(os.path.expanduser(raw))
    if not path.is_absolute():
        path = cwd_of(ev) / path
    return Path(os.path.normpath(str(path)))


def _within(path: Path, base: Path) -> Optional[Path]:
    try:
        return path.relative_to(Path(os.path.normpath(str(base))))
    except ValueError:
        try:
            return path.resolve().relative_to(base.resolve())
        except (ValueError, OSError):
            return None


def read_meta(change_dir: Path) -> Optional[dict]:
    try:
        return json.loads((change_dir / P.META).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def write_violation(ev: dict, path: Path) -> Optional[str]:
    """Why the event's actor may not write `path`, or None."""
    agent = ev.get("agent") or ""
    if _within(path, grants.grants_dir()) is not None:
        return "放行授权只能由用户在对话里输入确认口令产生，不能写 %s" % grants.grants_dir()
    project = project_of(ev)
    rel = _within(path, project.openspec) if project else None
    if rel is None:
        if agent in EVALUATOR_REPORT:
            return "%s 是只读评审 agent，只能写自己的报告 %s" % (agent, EVALUATOR_REPORT[agent])
        return None
    parts = rel.parts
    if len(parts) == 1 and parts[0] in PROTECTED:
        return PROTECTED[parts[0]]
    if len(parts) >= 2 and parts[0] == "changes" and parts[1] == "archive":
        return "已归档的 change 不能再修改"
    if len(parts) < 3 or parts[0] != "changes":
        if agent in EVALUATOR_REPORT or agent == GENERATOR:
            return "%s 不能修改 .openspec/ 下的 %s" % (agent, rel.as_posix())
        return None
    change, name = parts[1], "/".join(parts[2:])
    if name in CLI_FILES:
        return "%s 只能经 spec-driven 命令写入，不能直接编辑" % name
    if agent in EVALUATOR_REPORT and name != EVALUATOR_REPORT[agent]:
        return "%s 是只读评审 agent，只能写自己的报告 %s" % (agent, EVALUATOR_REPORT[agent])
    if agent == GENERATOR and name != P.IMPLEMENTATION_LOG:
        return "implementation-generator 只能追加 implementation-log.md，不能改 .openspec/ 下的工件"
    meta = read_meta(project.change_dir(change))
    produced = ARTIFACT_PHASE.get(name)
    if meta and produced and meta.get("phase") in PHASES \
            and PHASES.index(produced) < PHASES.index(meta["phase"]):
        return ("%s 属于 Phase %s，当前已进入 Phase %s，上游工件已冻结；确需修改，先请用户同意后回退到 Phase %s（spec-driven retry %s --reason ...）"
                % (name, produced, meta["phase"], produced, produced))
    return None
