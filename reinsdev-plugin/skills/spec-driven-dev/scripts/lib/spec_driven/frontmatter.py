"""Minimal YAML-frontmatter reader (stdlib only).

Supports the subset Reins uses: `key: scalar`, `key: [a, b]`, and block lists
(`key:` followed by `  - item` lines). Anything richer should not appear in
the plugin's agent or skill files.
"""

import json
import re
from typing import Dict, List, Tuple, Union

Value = Union[str, List[str]]

_FM = re.compile(r"\A---\r?\n(.*?)\r?\n---\r?\n?(.*)\Z", re.S)


def _scalar(raw: str) -> str:
    raw = raw.strip()
    if len(raw) >= 2 and raw[0] == raw[-1] and raw[0] in "\"'":
        return json.loads(raw) if raw[0] == '"' else raw[1:-1]
    return raw


def parse(text: str) -> Tuple[Dict[str, Value], str]:
    m = _FM.match(text)
    if not m:
        return {}, text
    meta: Dict[str, Value] = {}
    key = None
    for line in m.group(1).splitlines():
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        item = re.match(r"^\s+-\s+(.*)$", line)
        if item and key is not None:
            cur = meta.get(key)
            if not isinstance(cur, list):
                cur = []
            cur.append(_scalar(item.group(1)))
            meta[key] = cur
            continue
        kv = re.match(r"^([A-Za-z0-9_-]+):\s*(.*)$", line)
        if not kv:
            raise ValueError("无法解析的 frontmatter 行: %r" % line)
        key, raw = kv.group(1), kv.group(2).strip()
        if raw.startswith("[") and raw.endswith("]"):
            meta[key] = [_scalar(x) for x in raw[1:-1].split(",") if x.strip()]
        elif raw == "":
            meta[key] = []
        else:
            meta[key] = _scalar(raw)
    body = m.group(2)
    return meta, body[1:] if body.startswith("\n") else body  # blank line after ---

