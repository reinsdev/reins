"""retrospective.md: the audit trail of a change (design doc §3.2, §6.4, §6.6). Owner: T6.

Only the CLI writes this file (spec-gate blocks model edits). Tables:
  人工确认记录   written by `waive`         | 时间 | Gate | 检查项 | 拦截内容 | 理由 | 确认人 | 指纹 |
  档位变更记录   written by `complexity set` | 时间 | Phase | 变更 | 类型 | 理由 | 确认人 |
  待优化清单     written by `retro add`      | 时间 | 来源 | 内容 |
Appends create the file and the table on first use and never rewrite existing rows.

The file is machine-written, so the reader here only understands what the writer
produces (a fixed heading and a pipe table under it); it is not a general markdown
parser. Every write also stores the content hash in SIG_FILE, which the git
pre-commit hook compares to catch edits that did not go through the CLI.
"""

import datetime
import hashlib
import re
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional

from . import meta
from .project import RETROSPECTIVE

SIG_FILE = ".retro.sha256"

WAIVERS = ("人工确认记录", ["时间", "Gate", "检查项", "拦截内容", "理由", "确认人", "指纹"])
TIERS = ("档位变更记录", ["时间", "Phase", "变更", "类型", "理由", "确认人"])
TODOS = ("待优化清单", ["时间", "来源", "内容"])

_PIPE = re.compile(r"(?<!\\)\|")


@dataclass
class Waiver:
    time: str
    gate: str
    check: str
    content: str
    reason: str
    confirmer: str
    fingerprint: str


def now() -> str:
    return datetime.datetime.now().strftime("%Y-%m-%d %H:%M")


def signature(text: str) -> str:
    return hashlib.sha256(text.replace("\r\n", "\n").encode("utf-8")).hexdigest()


def _cell(value: str) -> str:
    return " ".join(str(value).split()).replace("|", "\\|")


def _row(cells: List[str]) -> str:
    return "| " + " | ".join(_cell(c) for c in cells) + " |"


def _split(line: str) -> List[str]:
    parts = _PIPE.split(line.strip())
    return [p.strip().replace("\\|", "|") for p in parts[1:-1]]


def _table_span(lines: List[str], title: str):
    """(first row index, end index) of the table under `## <title>`, or None."""
    try:
        start = [l.rstrip() for l in lines].index("## " + title)
    except ValueError:
        return None
    i = start + 1
    while i < len(lines) and not lines[i].lstrip().startswith("|"):
        i += 1
    first = i + 2  # skip header and separator
    end = first
    while end < len(lines) and lines[end].lstrip().startswith("|"):
        end += 1
    return first, end


def _rows(change_dir: Path, table) -> List[List[str]]:
    path = Path(change_dir) / RETROSPECTIVE
    if not path.is_file():
        return []
    lines = path.read_text(encoding="utf-8").splitlines()
    span = _table_span(lines, table[0])
    if span is None:
        return []
    width = len(table[1])
    return [r for r in (_split(l) for l in lines[span[0]:span[1]]) if len(r) == width]


def _append(change_dir: Path, table, cells: List[str]) -> None:
    change_dir = Path(change_dir)
    path = change_dir / RETROSPECTIVE
    with meta.lock(change_dir):
        text = path.read_text(encoding="utf-8") if path.is_file() else "# Retrospective: %s\n" % change_dir.name
        lines = text.splitlines()
        span = _table_span(lines, table[0])
        if span is None:
            while lines and not lines[-1].strip():
                lines.pop()
            lines += ["", "## " + table[0], "", _row(table[1]), "| " + " | ".join("---" for _ in table[1]) + " |"]
            span = (len(lines), len(lines))
        lines.insert(span[1], _row(cells))
        text = "\n".join(lines) + "\n"
        path.write_bytes(text.encode("utf-8"))
        (change_dir / SIG_FILE).write_bytes((signature(text) + "\n").encode("ascii"))


def verify(change_dir: Path, text: Optional[str] = None) -> bool:
    """True when `text` (default: the file on disk) is what the CLI last wrote.
    A change without retrospective.md and without a signature verifies."""
    change_dir = Path(change_dir)
    sig = change_dir / SIG_FILE
    if text is None:
        path = change_dir / RETROSPECTIVE
        text = path.read_text(encoding="utf-8") if path.is_file() else None
    if text is None:
        return True
    return sig.is_file() and sig.read_text(encoding="ascii").strip() == signature(text)


def waivers(change_dir: Path) -> List[Waiver]:
    """Rows of 人工确认记录; [] when the file or table does not exist."""
    return [Waiver(*r) for r in _rows(change_dir, WAIVERS)]


def append_waiver(change_dir: Path, w: Waiver) -> None:
    _append(change_dir, WAIVERS, [w.time, w.gate, w.check, w.content, w.reason, w.confirmer, w.fingerprint])


def append_tier_change(change_dir: Path, phase: str, change: str, kind: str, reason: str, confirmer: str) -> None:
    """kind: 选定 | 升档 | 降档."""
    _append(change_dir, TIERS, [now(), phase, change, kind, reason, confirmer])


def todos(change_dir: Path) -> List[str]:
    """Texts in 待优化清单, in order; [] when absent."""
    return [r[2] for r in _rows(change_dir, TODOS)]


def add_todo(change_dir: Path, source: str, text: str) -> None:
    """Append to 待优化清单; `source` e.g. "code-review WARN"."""
    _append(change_dir, TODOS, [now(), source, text])
