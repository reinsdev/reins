"""gate-router / phase-router: on prompts like 「进入 Phase N」「继续」「下一步」「/archive」,
run the current phase's gate and return its verdict as a note, so the model sees
it before acting (§6.1). Owner: T6. Runs at most one gate; silent when there is
no current change or the gate is not implemented."""

import re
from typing import Optional

from .. import config, gates, locate
from ..errors import BLOCK, OK, WARN
from .common import project_of, read_meta

TRIGGER = re.compile(r"进入\s*(?:phase|阶段|第)?\s*\d|^\s*继续|下一步|下一阶段|/archive|归档", re.I)
MAX_LINES = 6


def prompt(ev: dict) -> Optional[str]:
    if not TRIGGER.search(ev.get("prompt") or ""):
        return None
    project = project_of(ev)
    if project is None or len(project.active_changes()) != 1:
        return None
    try:
        change = locate.resolve(project)
    except SystemExit:
        return None
    change_dir = project.change_dir(change)
    m = read_meta(change_dir)
    if not m or not m.get("phase"):
        return None
    gate = m["phase"]
    try:
        ctx = gates.GateContext(project, change, change_dir, m, config.load(project))
        findings, code = gates.evaluate(gate, ctx)
    except (NotImplementedError, SystemExit):
        return None
    verdict = {OK: "通过", WARN: "有告警", BLOCK: "拦截"}.get(code, "错误")
    lines = ["Reins：%s 当前 Phase %s 的 gate-%s %s。" % (change, gate, gate, verdict)]
    shown = [f for f in findings if f.level in ("BLOCK", "WARN") and not f.waived]
    for f in shown[:MAX_LINES]:
        lines.append("[%s] %s %s" % (f.level, f.check, f.reason))
    if len(shown) > MAX_LINES:
        lines.append("…共 %d 项，运行 spec-driven gate %s 查看全部" % (len(shown), gate))
    if code == BLOCK:
        lines.append("拦截未解决前不要进入下一个 Phase；把原因原样告诉用户，请用户选择回去修或放行。")
    return "\n".join(lines)
