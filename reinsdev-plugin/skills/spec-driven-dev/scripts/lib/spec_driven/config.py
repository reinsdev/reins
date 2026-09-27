"""`.openspec/.config.json`: team-level settings, merged over DEFAULTS.

Owner of new keys: the task that needs them adds the key and its default to
DEFAULTS here (the only edit other tasks may make to this file) and lists it
in its delivery notes (AGENTS.md §6).
"""

import copy
import json

from .errors import fail
from .project import Project

DEFAULTS = {
    # gates.<id>.level: block | warn | info | off. Locked checks ignore it (§6.1).
    "gates": {},
    "test": {"coverage": {"diff_threshold": 80}},
    # quality.<check>: {"command": "...", "report_path": "..."}; written by init-config (§6.5).
    "quality": {},
    # agents.<name>.model: model override for the retry (§5).
    "agents": {},
    # openapi.enabled: api-design-rest also drafts openapi.draft.json; gate_on_draft: warn | block
    # for gate 3's draft check (workflow §7). Read by gate 3 (T3).
    "openapi": {"enabled": False, "gate_on_draft": "warn"},
}

LEVELS = ("block", "warn", "info", "off")


def _merge(base: dict, over: dict) -> dict:
    out = copy.deepcopy(base)
    for k, v in over.items():
        out[k] = _merge(out[k], v) if isinstance(v, dict) and isinstance(out.get(k), dict) else v
    return out


def load(project: Project) -> dict:
    path = project.config_path
    if not path.is_file():
        return copy.deepcopy(DEFAULTS)
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except ValueError as e:
        fail("%s 不是合法 JSON：%s" % (path, e))
    return _merge(DEFAULTS, data)


def gate_level(config: dict, gate: str):
    """Configured level for a gate, or None when not overridden."""
    level = (config.get("gates", {}).get(gate) or {}).get("level")
    if level is not None and level not in LEVELS:
        fail("配置 gates.%s.level=%r 无效，可选 %s" % (gate, level, " / ".join(LEVELS)))
    return level
