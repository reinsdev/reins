"""Probe marker: blocks any path or command containing PROBE, so each runtime's
blocking path can be verified end to end (docs/verification.md §1)."""

from typing import Optional

PROBE = ".reins-probe-block"


def pre_tool(ev: dict) -> Optional[str]:
    haystack = " ".join(ev["paths"]) + " " + ev["command"]
    if PROBE in haystack:
        return "Reins 探针拦截：%s（用于验证 hook 拦截链路，属预期行为）" % PROBE
    return None
