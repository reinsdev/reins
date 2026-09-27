"""gate-router / phase-router: on prompts like 「进入 Phase N」「继续」「/archive」,
run the current phase's gate and return its verdict as a note, so the model sees
it before acting (§6.1). Owner: T6. Must stay fast: run at most one gate."""

from typing import Optional


def prompt(ev: dict) -> Optional[str]:
    raise NotImplementedError
