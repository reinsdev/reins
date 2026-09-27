"""Markdown parsing shared by every gate (design doc §6.3). Owner: T1.

Gates never regex raw markdown themselves: they call these functions, and look
sections up by an ALIASES key, so a template heading change is made in one place.
Line numbers are 1-based and refer to the original text.
"""

import re
from dataclasses import dataclass, field
from typing import Dict, List, Optional

# Canonical section key -> accepted heading texts (case-insensitive, trimmed,
# numbering like "1." / "一、" ignored). Templates under templates/ use the first
# variant. T1 fills this from spec-driven-workflow.md; other tasks request new
# keys from T1 instead of matching headings themselves.
ALIASES: Dict[str, List[str]] = {}

# ID grammar (§6.3). <cap> is the capability id: lowercase kebab-case.
ID_PATTERNS = {
    "AC": r"AC-\d+",
    "REQ": r"REQ-[a-z][a-z0-9-]*-\d{3}",
    "SC": r"SC-[a-z][a-z0-9-]*-(?:\d{3}|E\d+)",
    "TASK": r"T\d+|T-regression",
}


@dataclass
class Section:
    title: str                 # heading text without the leading #s
    level: int                 # 1..6; 0 for the document root
    line: int                  # line of the heading; 0 for the root
    body: str                  # text under the heading up to the next heading of any level
    children: List["Section"] = field(default_factory=list)

    def text(self) -> str:
        """Body plus all descendant sections, as in the source."""
        raise NotImplementedError


@dataclass
class Table:
    line: int
    header: List[str]
    rows: List[Dict[str, str]]  # header cell -> cell text, stripped


@dataclass
class Checkbox:
    line: int
    state: str  # " " | "x" | "~"
    text: str


def parse(text: str) -> Section:
    """Split into a heading tree; ATX headings only, headings inside fenced code are ignored."""
    raise NotImplementedError


def find(root: Section, key: str) -> Optional[Section]:
    """First section whose heading matches any ALIASES[key] variant, at any depth."""
    raise NotImplementedError


def find_all(root: Section, pattern: str) -> List[Section]:
    """Sections whose heading matches the regex `pattern` (e.g. ID_PATTERNS["REQ"]), in order."""
    raise NotImplementedError


def ids(text: str, kind: str) -> List[str]:
    """Distinct IDs of ID_PATTERNS[kind] in order of first appearance, outside fenced code."""
    raise NotImplementedError


def tables(text: str) -> List[Table]:
    """Pipe tables; the separator row is required, escaped pipes (\\|) are kept in cells."""
    raise NotImplementedError


def checkboxes(text: str) -> List[Checkbox]:
    """List items `- [ ]`, `- [x]` (or X), `- [~]`."""
    raise NotImplementedError


def id_re(kind: str) -> "re.Pattern":
    return re.compile(r"\b(?:%s)\b" % ID_PATTERNS[kind])
