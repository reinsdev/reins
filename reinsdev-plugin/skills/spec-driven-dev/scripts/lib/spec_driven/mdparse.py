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
ALIASES: Dict[str, List[str]] = {
    "user-stories": ["用户故事", "User Stories", "User Story"],
    "acceptance-criteria": ["验收标准 AC", "验收标准", "Acceptance Criteria", "AC"],
    "out-of-scope": ["Out of Scope", "范围外", "不在范围内", "非目标"],
    "ambiguities": ["歧义清单", "歧义与澄清", "Ambiguities", "Open Questions"],
    "dependencies": ["隐含依赖", "依赖", "Dependencies", "Implicit Dependencies"],
    "field-mapping": ["5.1 字段映射确认表", "字段映射确认表", "字段映射", "Field Mapping"],
    "non-functional": ["关键非功能性需求", "非功能需求", "Non-functional Requirements", "NFR"],
    "affected-modules": ["影响的现有模块", "受影响模块", "Affected Modules"],
    "basic-info": ["基本信息", "Basic Information", "Overview"],
    "evidence": ["现场证据", "Evidence", "现场信息"],
    "root-cause": ["根因分析", "Root Cause Analysis", "Root Cause"],
    "fix-plan": ["修复方案", "Fix Plan", "修复计划"],
    "change-points": ["修改点", "改动点", "Change Points"],
    "impact": ["影响范围", "影响面", "Impact", "Impact Scope"],
    "complexity-assessment": ["复杂度判定", "复杂度评估", "Complexity Assessment"],
    "background": ["背景与目标", "背景和目标", "Background and Goals"],
    "current-system": ["现有系统分析", "现状分析", "Current System"],
    "alternatives": ["方案对比", "备选方案", "Alternatives", "Options"],
    "final-choice": ["推荐方案与最终决策", "推荐方案", "最终决策", "Final Choice", "Decision"],
    "detailed-design": ["详细设计", "Detailed Design"],
    "risks": ["风险与缓解", "风险及缓解措施", "Risks and Mitigations", "Risks"],
    "stress-test": ["压力测试自检", "压测自检", "Stress Test", "Stress-test Checklist"],
    "implementation-plan": ["实施计划", "Implementation Plan"],
    "interface-contract": ["接口契约", "接口设计", "Interface Contract", "API Contract"],
    "data-model": ["数据模型", "数据库设计", "Data Model"],
    "table-structure": ["表结构", "Table Structure", "Schema"],
    "indexes": ["索引", "Indexes", "Indices"],
    "constraints": ["约束", "Constraints"],
    "migrations": ["迁移与回滚", "迁移脚本", "Migrations", "Migration and Rollback"],
    "foundation": ["Foundation(底层依赖,必须先做)", "Foundation", "底层依赖", "基础层"],
    "domain-layer": ["Domain Layer", "领域层"],
    "application-layer": ["Application Layer", "App Layer", "应用层"],
    "adapter-layer": ["Adapter Layer", "适配层"],
    "test-layer": ["Test", "Tests", "测试"],
    "change-scope": ["变更范围", "Change Scope", "Scope"],
    "red": ["RED：失败测试", "RED", "RED: Failing Tests", "失败测试"],
    "green": ["GREEN：通过测试", "GREEN", "GREEN: Passing Tests", "通过测试"],
    "refactor": ["REFACTOR：重构", "REFACTOR", "重构"],
    "build": ["完整构建", "Build", "构建结果"],
    "coverage": ["增量覆盖率", "Diff Coverage", "Coverage"],
    "commits": ["提交记录", "Commits", "Commit Records"],
    "deployment-info": ["启动信息", "Deployment Information", "Startup Information"],
    "startup-result": ["启动结果", "Startup Result", "Deployment Result"],
    "deployment-errors": ["错误摘要与日志", "错误摘要", "Errors and Logs"],
    "manual-acceptance": ["用户人工验收结论", "人工验收", "Manual Acceptance"],
    "conclusion": ["结论", "Conclusion", "Result"],
}

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
        parts = [self.body]
        for child in self.children:
            parts.append(getattr(child, "_heading", "%s %s\n" % ("#" * child.level, child.title)))
            parts.append(child.text())
        return "".join(parts)


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
    root = Section("", 0, 0, "")
    stack = [root]
    body = []
    for number, line, visible in _lines(text):
        heading = _heading(line) if visible else None
        if heading is None:
            body.append(line)
            continue
        stack[-1].body = "".join(body)
        body = []
        level, title = heading
        while stack[-1].level >= level:
            stack.pop()
        section = Section(title, level, number, "")
        # Retain the original heading for lossless subtree reconstruction.
        section._heading = line
        stack[-1].children.append(section)
        stack.append(section)
    stack[-1].body = "".join(body)
    return root


def find(root: Section, key: str) -> Optional[Section]:
    """First section whose heading matches any ALIASES[key] variant, at any depth."""
    variants = {_normalize(title) for title in ALIASES.get(key, [])}
    return next((section for section in _sections(root)
                 if _normalize(section.title) in variants), None)


def find_all(root: Section, pattern: str) -> List[Section]:
    """Sections whose heading matches the regex `pattern` (e.g. ID_PATTERNS["REQ"]), in order."""
    regex = re.compile(pattern)
    return [section for section in _sections(root) if regex.search(section.title)]


def ids(text: str, kind: str) -> List[str]:
    """Distinct IDs of ID_PATTERNS[kind] in order of first appearance, outside fenced code."""
    regex = id_re(kind)
    result = []
    seen = set()
    for _, line, visible in _lines(text):
        if visible:
            for match in regex.finditer(line):
                value = match.group(0)
                if value not in seen:
                    seen.add(value)
                    result.append(value)
    return result


def tables(text: str) -> List[Table]:
    """Pipe tables; the separator row is required, escaped pipes (\\|) are kept in cells."""
    lines = list(_lines(text))
    result = []
    index = 0
    while index + 1 < len(lines):
        number, line, visible = lines[index]
        header = _cells(line) if visible else None
        separator = _cells(lines[index + 1][1]) if lines[index + 1][2] else None
        if (not header or not separator or len(header) != len(separator)
                or not all(re.fullmatch(r":?-{3,}:?", cell) for cell in separator)):
            index += 1
            continue
        table = Table(number, header, [])
        index += 2
        while index < len(lines) and lines[index][2]:
            cells = _cells(lines[index][1])
            if cells is None:
                break
            cells += [""] * (len(header) - len(cells))
            table.rows.append(dict(zip(header, cells)))
            index += 1
        result.append(table)
    return result


def checkboxes(text: str) -> List[Checkbox]:
    """List items `- [ ]`, `- [x]` (or X), `- [~]`."""
    result = []
    for number, line, visible in _lines(text):
        match = re.fullmatch(r"[ \t]*-[ \t]+\[([ xX~])\](?:[ \t]+(.*))?", line.rstrip("\r\n")) if visible else None
        if match:
            result.append(Checkbox(number, match.group(1).lower(), (match.group(2) or "").strip()))
    return result


def id_re(kind: str) -> "re.Pattern":
    return re.compile(r"\b(?:%s)\b" % ID_PATTERNS[kind])


def _lines(text):
    """Keep source positions while sharing fence rules across readers."""
    fence = ""
    fence_quotes = 0
    fence_indent = 0
    list_indents = []
    list_quotes = 0
    for number, line in enumerate(text.splitlines(keepends=True), 1):
        raw = line.rstrip("\r\n").expandtabs(4)
        if fence:
            value, quotes = _quote_content(raw, fence_quotes)
            indentation = len(value) - len(value.lstrip(" "))
            if quotes == fence_quotes and (not value.strip() or indentation >= fence_indent):
                if re.fullmatch(r" {0,3}%s{%d,} *" % (re.escape(fence[0]), len(fence)), value[fence_indent:]):
                    fence = ""
                yield number, line, False
                continue
            # An unclosed fence ends when its list or blockquote container ends.
            fence = ""
        value, quotes = _quote_content(raw)
        if quotes != list_quotes:
            list_indents = []
            list_quotes = quotes
        if value.strip():
            indentation = len(value) - len(value.lstrip(" "))
            while list_indents and indentation < list_indents[-1]:
                list_indents.pop()
        indent = list_indents[-1] if list_indents else 0
        value = value[indent:]
        while True:
            item = re.match(r" {0,3}(?:[-+*]|\d{1,9}[.)]) +", value)
            if item:
                indent += item.end()
                list_indents.append(indent)
                value = value[item.end():]
                continue
            content, nested_quotes = _quote_content(value)
            if nested_quotes:
                value = content
                quotes += nested_quotes
                list_quotes = quotes
                list_indents = []
                indent = 0
                continue
            break
        match = re.fullmatch(r" {0,3}(`{3,}|~{3,})(.*)", value)
        if match and not (match.group(1)[0] == "`" and "`" in match.group(2)):
            fence = match.group(1)
            fence_quotes = quotes
            fence_indent = indent
            yield number, line, False
        else:
            yield number, line, True


def _quote_content(value, limit=None):
    """Remove only the quote containers belonging to the surrounding block."""
    count = 0
    while limit is None or count < limit:
        marker = re.match(r" {0,3}> ?", value)
        if not marker:
            break
        value = value[marker.end():]
        count += 1
    return value, count


def _heading(line):
    match = re.fullmatch(r" {0,3}(#{1,6})(?:[ \t]+(.*))?", line.rstrip("\r\n"))
    if not match:
        return None
    title = match.group(2) or ""
    title = re.sub(r"(?:^|[ \t]+)#+[ \t]*$", "", title).strip()
    return len(match.group(1)), title


def _sections(root):
    """Visit real headings in source order, including a supplied subtree root."""
    if root.level:
        yield root
    for child in root.children:
        yield from _sections(child)


def _normalize(title):
    title = title.strip().casefold()
    title = re.sub(r"^(?:\d+(?:\.\d+)*[.、．)）]?|[一二三四五六七八九十百零〇]+[、.．]|[（(][\d一二三四五六七八九十百零〇]+[）)])[ \t]*", "", title)
    return " ".join(title.split())


def _cells(line):
    """Split unescaped delimiters without changing the cell's markdown."""
    value = line.strip()
    if not value or _heading(line):
        return None
    cells = []
    start = 0
    escaped = False
    for index, char in enumerate(value):
        if char == "|" and not escaped:
            cells.append(value[start:index].strip())
            start = index + 1
        escaped = char == "\\" and not escaped
    if not cells:
        return None
    cells.append(value[start:].strip())
    if value.startswith("|"):
        cells.pop(0)
    if start == len(value):
        cells.pop()
    return cells or None
