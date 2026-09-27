"""spec-gate: path locks for edit tools. Owner: T6. Shell writes are bash_guard's.

Blocks, for the change the edited file belongs to:
  - edits to artifacts of phases before the current one (upstream freeze, §4 rule 1);
    `retry` moves the phase back, which lifts the freeze;
  - edits to retrospective.md, .meta.json and their lock / signature (CLI-only files, §6.4);
  - evaluator agents writing anything but their own report (§5);
  - implementation-generator writing under .openspec/ except implementation-log.md (§5);
  - edits to .openspec/.config.json, quality-baseline.json and archived changes;
  - writes to <REINS_HOME>/grants/ (§6.6).
Agent rules apply where the runtime reports the subagent (Claude Code: agent_type).
"""

from typing import Optional

from .common import abs_path, write_violation


def pre_tool(ev: dict) -> Optional[str]:
    if ev.get("kind") != "edit":
        return None
    for raw in ev.get("paths") or []:
        reason = write_violation(ev, abs_path(ev, raw))
        if reason:
            return "Reins 拦截：" + reason
    return None
