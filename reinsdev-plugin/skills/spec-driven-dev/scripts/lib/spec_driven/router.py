"""Phase routing (design doc §3.3). Owner: T2.

Pure functions of (meta, config): no file or git access, so every rule is unit-testable.
"""

from typing import Dict, List, Optional

from . import project as P
from .meta import PHASES

# What the controller does in each phase (SKILL.md main loop), shown by status / resume.
ACTIONS = {
    "0": "建 change",
    "1": "需求澄清：调用 requirements-clarify（bugfix 模式调用 bugfix）",
    "2": "技术方案：调用 tech-design-tradeoff",
    "3": "接口与数据：调用 api-design-rest、db-schema-design",
    "4": "任务拆分：调用 task-breakdown",
    "5": "spec 评审：调度 spec-evaluator agent",
    "6": "TDD 实现：逐个任务调度 implementation-generator agent",
    "7": "QA：调度 qa-evaluator agent",
    "8": "code review：调度 code-reviewer agent",
    "8.5": "部署验收：问用户 y / n / skip",
    "8.9": "用户验收：整理验收摘要请用户确认",
    "9": "归档",
}

# Artifact each phase produces (the one `retry` marks as revised).
OUTPUT = {
    "1": P.PROPOSAL, "2": P.DESIGN, "3": P.SPEC, "4": P.TASKS, "5": P.SPEC_REVIEW,
    "6": P.IMPLEMENTATION_LOG, "7": P.QA_REPORT, "8": P.CODE_REVIEW, "8.5": P.DEPLOY_REPORT,
}

# Artifacts to read before working on each phase (resume); missing ones are left out by the caller.
INPUTS = {
    "0": [P.PROPOSAL],
    "1": [P.PROPOSAL, P.BUGFIX_ANALYSIS],
    "2": [P.PROPOSAL, P.BUGFIX_ANALYSIS],
    "3": [P.PROPOSAL, P.DESIGN],
    "4": [P.SPEC, P.DESIGN],
    "5": [P.PROPOSAL, P.BUGFIX_ANALYSIS, P.DESIGN, P.SPEC, P.TASKS],
    "6": [P.TASKS, P.SPEC, P.INVARIANTS],
    "7": [P.SPEC, P.IMPLEMENTATION_LOG],
    "8": [P.SPEC, P.TASKS, P.STATIC_ANALYSIS],
    "8.5": [P.QA_REPORT, P.CODE_REVIEW],
    "8.9": [P.PROPOSAL, P.SPEC, P.QA_REPORT],
    "9": [P.DESIGN, P.SPEC, P.RETROSPECTIVE],
}

# Gates that must pass before a phase counts as done (`advance`).
PHASE_GATES = {"6": ["6", "6.5", "6.7"]}

_BUGFIX_DESIGN_FILES = 3  # bugfix touching >= this many files needs a design


def gates_of(phase: str) -> List[str]:
    return PHASE_GATES.get(phase, [phase])


def skip_reason(phase: str, meta: dict) -> Optional[str]:
    """Why a conditional phase (2, 3, 5, 7) is skipped for this tier / mode, or None if it runs.
    Phase 8.5 is never skipped here: the controller asks the user."""
    tier = meta.get("complexity")
    if phase in ("2", "3", "5", "7") and tier == "S":
        return "S 档跳过 Phase %s" % phase
    if meta.get("mode") != "bugfix" or phase not in ("2", "3"):
        return None
    scope = meta.get("bugfixScope")
    if not isinstance(scope, dict):
        return None  # no assessment yet: run the phase
    ddl, api = bool(scope.get("ddl")), bool(scope.get("publicApi"))
    if phase == "2":
        big = (scope.get("files") or 0) >= _BUGFIX_DESIGN_FILES or scope.get("crossService")
        if not (big or ddl or api):
            return "bugfix 未跨 ≥%d 文件、未跨服务、不改 DDL 和公开 API，跳过技术方案" % _BUGFIX_DESIGN_FILES
    if phase == "3" and not (ddl or api):
        return "bugfix 不改接口也不改 DDL，跳过接口与数据设计"
    return None


def stale_phases(meta: dict) -> List[str]:
    status = meta.get("phaseStatus") or {}
    return [p for p in PHASES if status.get(p) == "stale"]


def next_phase(meta: dict, config: dict) -> Optional[str]:
    """The phase the controller should work on next: the first phase (in meta.PHASES order)
    whose status is not passed/skipped. After `retry` that is the retried phase, then the
    stale ones in order, then pending ones. None when archived."""
    status = meta.get("phaseStatus") or {}
    for p in PHASES:
        if status.get(p, "pending") not in ("passed", "skipped"):
            return p
    return None


def review_rounds(meta: dict) -> int:
    """Rounds of spec review in Phase 5: 0 for S, 1 for M, 2 for L."""
    return {"S": 0, "M": 1, "L": 2}[meta.get("complexity", "M")]


def summary(meta: dict, config: dict) -> Dict:
    """What status / resume print: current phase, its state, next phase and action."""
    nxt = next_phase(meta, config)
    return {
        "phase": meta["phase"],
        "phaseStatus": (meta.get("phaseStatus") or {}).get(meta["phase"], "pending"),
        "next": nxt,
        "action": ACTIONS.get(nxt) if nxt else "已归档，没有下一步",
        "stale": stale_phases(meta),
    }
