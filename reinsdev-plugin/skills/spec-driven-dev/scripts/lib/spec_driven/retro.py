"""retrospective.md: the audit trail of a change (design doc §3.2, §6.4, §6.6). Owner: T6.

Only the CLI writes this file (spec-gate blocks model edits). Tables:
  人工确认记录   written by `waive`         | 时间 | Gate | 检查项 | 拦截内容 | 理由 | 确认人 | 指纹 |
  档位变更记录   written by `complexity set` | 时间 | Phase | 变更 | 类型 | 理由 | 确认人 |
  待优化清单     written by `retro add`
Appends create the file and the table on first use and never rewrite existing rows.
"""

from dataclasses import dataclass
from pathlib import Path
from typing import List


@dataclass
class Waiver:
    time: str
    gate: str
    check: str
    content: str
    reason: str
    confirmer: str
    fingerprint: str


def waivers(change_dir: Path) -> List[Waiver]:
    """Rows of 人工确认记录; [] when the file or table does not exist.

    Until T6 lands this returns [] so gates fail closed (nothing is waived)."""
    return []


def append_waiver(change_dir: Path, w: Waiver) -> None:
    raise NotImplementedError


def append_tier_change(change_dir: Path, phase: str, change: str, kind: str, reason: str, confirmer: str) -> None:
    """kind: 选定 | 升档 | 降档."""
    raise NotImplementedError


def todos(change_dir: Path) -> List[str]:
    """Texts in 待优化清单, in order; [] when absent."""
    raise NotImplementedError


def add_todo(change_dir: Path, source: str, text: str) -> None:
    """Append to 待优化清单; `source` e.g. "code-review WARN"."""
    raise NotImplementedError
