"""spec-gate: path locks for edit tools and shell writes. Owner: T6.

Blocks, for the change the event's cwd belongs to:
  - edits to artifacts of phases before the current one (upstream freeze, §4 rule 1),
    unless that phase is in_progress after `retry`;
  - edits to retrospective.md and .meta.json (CLI-only files, §6.4);
  - evaluator agents writing anything but their own report (§5);
  - implementation-generator writing under .openspec/ (§5);
  - writes to <REINS_HOME>/grants/ (§6.6).
"""

from typing import Optional


def pre_tool(ev: dict) -> Optional[str]:
    raise NotImplementedError
