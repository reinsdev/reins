"""Gate framework (design doc §6.1). Owner: T0 (contract); gate modules: T3 / T4 / T5.

A gate module `gates/g<id>.py` (dots become underscores: g6_5, g8_9) exposes
exactly one function:

    def check(ctx: GateContext) -> List[Finding]

It only reports findings. Everything else is done here, identically for all
gates: skipped phases, config levels, locked checks, waivers, fingerprints,
output format and exit code. A gate module never prints, never exits, never
writes files, and never reads retrospective.md or .config.json itself.
"""

import hashlib
import importlib
import json
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import List, Tuple

from .. import config as config_mod
from .. import retro
from ..errors import BLOCK, OK, WARN
from ..meta import GATES
from ..project import Project

LEVELS = ("BLOCK", "WARN", "INFO")


@dataclass
class Finding:
    level: str                # BLOCK | WARN | INFO
    check: str                # stable kebab-case id within the gate, e.g. "ac-mapped"
    reason: str               # what is wrong, in Chinese, one line
    location: str = ""        # "spec.md:12" (path relative to the change dir) or ""
    fix: str = ""             # what to do about it, one line
    evidence: str = ""        # canonical content the fingerprint covers (violations, numbers,
                              # missing ids); empty means `reason`. Must not contain line numbers.
    locked: bool = False      # anti-self-deception checks and gate 6.7: config cannot lower it
    fingerprint: str = ""     # filled by the framework
    waived: bool = False      # filled by the framework


@dataclass
class GateContext:
    project: Project
    change: str
    change_dir: Path
    meta: dict
    config: dict
    strict: bool = False      # --strict: WARN counts as BLOCK
    extra: dict = field(default_factory=dict)  # gate-specific inputs (e.g. {"task": "T3"} for gate 6)


def module_name(gate: str) -> str:
    return "g" + gate.replace(".", "_")


def fingerprint(gate: str, f: Finding) -> str:
    raw = "\n".join([gate, f.check, f.evidence or f.reason])
    return hashlib.sha1(raw.encode("utf-8")).hexdigest()[:8]


def _apply_level(gate: str, f: Finding, cfg: dict) -> Finding:
    level = config_mod.gate_level(cfg, gate)
    if level is None or f.locked or f.level != "BLOCK":
        return f
    if level == "off":
        return None
    f.level = level.upper()
    return f


def evaluate(gate: str, ctx: GateContext) -> Tuple[List[Finding], int]:
    """Run one gate; return findings (after levels and waivers) and the exit code."""
    if gate not in GATES:
        raise ValueError("unknown gate %s" % gate)
    skipped = (ctx.meta.get("skipped") or {}).get(gate)
    if skipped:
        return [Finding("INFO", "skipped", "本 Phase 已跳过：%s" % skipped)], OK
    mod = importlib.import_module("%s.%s" % (__name__, module_name(gate)))
    findings = []
    for f in mod.check(ctx):
        if f.level not in LEVELS:
            raise ValueError("gate %s: bad level %r" % (gate, f.level))
        f.fingerprint = fingerprint(gate, f)
        f = _apply_level(gate, f, ctx.config)
        if f is not None:
            findings.append(f)
    waived = {(w.gate, w.check, w.fingerprint) for w in retro.waivers(ctx.change_dir)}
    for f in findings:
        if f.level == "BLOCK" and (gate, f.check, f.fingerprint) in waived:
            f.waived = True
    live = [f for f in findings if not f.waived]
    if any(f.level == "BLOCK" for f in live) or (ctx.strict and any(f.level == "WARN" for f in live)):
        return findings, BLOCK
    if any(f.level == "WARN" for f in live):
        return findings, WARN
    return findings, OK


def render(gate: str, findings: List[Finding], code: int) -> str:
    """Human output: one line per finding, then a verdict line."""
    lines = []
    for f in findings:
        tag = "WAIVED" if f.waived else f.level
        loc = (" — " + f.location) if f.location else " —"
        fix = (" → " + f.fix) if f.fix else ""
        lines.append("[%s] %s%s %s%s  #%s" % (tag, f.check, loc, f.reason, fix, f.fingerprint))
    verdict = {OK: "通过", WARN: "有告警", BLOCK: "拦截"}.get(code, "错误")
    lines.append("gate-%s：%s（退出码 %d）" % (gate, verdict, code))
    return "\n".join(lines)


def to_json(gate: str, findings: List[Finding], code: int) -> str:
    return json.dumps({"gate": gate, "exit": code, "findings": [asdict(f) for f in findings]},
                      ensure_ascii=False, indent=2)
