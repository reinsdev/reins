"""bash-guard: shell command rules. Owner: T6.

Blocks: deleting test directories (src/test/**), mutating commands from evaluator
agents (file writes, git commit/checkout/reset/push ...), writes to
<REINS_HOME>/grants/, and `spec-driven waive` / `complexity set --downgrade`
without a grant is left to the CLI (it refuses by itself).
Command parsing must tolerate quoting, `&&`, `;`, pipes and `sh -c "..."`.
"""

from typing import Optional


def pre_tool(ev: dict) -> Optional[str]:
    raise NotImplementedError
