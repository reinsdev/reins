"""Check Phase 2 design evidence. Owner: T3.

Checks:
- design-readable: require readable design and complexity inputs.
- alternatives-count: require two distinct options, or three for tier L.
- alternatives-fields: require all six comparison fields for each option.
- recommendation: require a named recommendation with a concrete reason.
- design-decision: require the final choice to match the recorded decision.
- impact-paths: require concrete affected file paths.
- stress-scenarios: require answers for all four stress scenarios.
- complexity-upgrade: warn about a higher recommended tier without writing state.
"""

import json
import re
from pathlib import PurePosixPath
from typing import List

from . import Finding, GateContext
from .. import mdparse, tiering
from ..project import DESIGN, PROPOSAL


def _filled(value):
    return bool(value.strip() and not re.search(r"<[^>\n]+>", value)
                and value.strip() not in ("待确认", "待补充", "未答", "TODO", "TBD", "-", "…"))



def _visible_lines(text):
    """Delegate fence visibility to mdparse using temporary heading probes."""
    lines = text.splitlines()
    probes = []
    candidates = {}
    for index, line in enumerate(lines):
        stripped = line.lstrip()
        if not stripped or stripped.startswith((chr(96) * 3, "~~~", ">")):
            probes.append(line)
            continue
        marker = "t3-prose-%d" % index
        candidates[marker] = line
        indent = line[:len(line) - len(stripped)]
        probes.append(indent + "###### " + marker)
    root = mdparse.parse("\n".join(probes))
    return [candidates[s.title] for s in mdparse.find_all(root, r"^t3-prose-\d+$")
            if s.title in candidates]


def _rows(section):
    if section is None:
        return []
    return [row for table in mdparse.tables(section.body) for row in table.rows]


def _labels(section):
    values = {}
    reasons = []
    in_recommendation = False
    if section is not None:
        for line in _visible_lines(section.body):
            stripped = line.strip()
            label = next((s for s in ("AI 推荐", "最终选择")
                          if stripped.startswith("**%s**" % s)), None)
            if label:
                value = stripped[len(label) + 4:].lstrip("：: ").strip()
                values.setdefault(label, []).append(value)
                in_recommendation = label == "AI 推荐"
            elif in_recommendation and stripped:
                reasons.append(stripped)
    return values, reasons


def _section_evidence(section):
    return {"title": section.title,
            "body": [line.strip() for line in section.body.splitlines() if line.strip()],
            "children": [_section_evidence(child) for child in section.children]}


def _sections(root):
    yield root
    for child in root.children:
        yield from _sections(child)


def check(ctx: GateContext) -> List[Finding]:
    findings = []

    def add(name, reason, evidence, section=None, level="BLOCK", fix="按 design.md 模板补全可核验的设计内容"):
        findings.append(Finding(
            level, name, reason, DESIGN + (":%d" % section.line if section else ""), fix,
            json.dumps(evidence, ensure_ascii=False, sort_keys=True)))

    try:
        root = mdparse.parse((ctx.change_dir / DESIGN).read_text(encoding="utf-8"))
    except (OSError, UnicodeError, ValueError) as exc:
        add("design-readable", "无法读取或解析 design.md", type(exc).__name__)
        return findings
    unique = {"alternatives": "alternatives-count", "final-choice": "design-decision",
              "current-system": "impact-paths", "stress-test": "stress-scenarios"}
    for key, check_name in unique.items():
        matches = [s for s in _sections(root) if mdparse.find(s, key) is s]
        if len(matches) > 1:
            add(check_name, "同一设计章节存在多个标题或别名，无法确认唯一内容",
                {"section": key, "contents": [_section_evidence(s) for s in matches]},
                fix="合并重复章节并保留实际确认内容")
    options_section = mdparse.find(root, "alternatives")
    rows = _rows(options_section)
    names = [r.get("方案", "").strip() for r in rows if _filled(r.get("方案", ""))]
    required = 3 if ctx.meta.get("complexity") == "L" else 2
    if len(set(names)) < required or len(names) != len(set(names)):
        add("alternatives-count", "至少比较 %d 个不同方案" % required,
            {"required": required, "options": sorted(names)}, options_section)
    fields = ("方案", "核心思路", "复杂度", "优点", "缺点", "工作量", "适用场景")
    invalid = [r for r in rows if any(not _filled(r.get(key, "")) for key in fields)]
    if not rows or invalid:
        add("alternatives-fields", "每个方案须填全思路、复杂度、优点、缺点、工作量和适用场景",
            invalid or "missing-options", options_section)

    section = mdparse.find(root, "final-choice")
    values, reasons = _labels(section)
    recommendation = values.get("AI 推荐", [])
    if (len(recommendation) != 1 or recommendation[0] not in names
            or not reasons or not all(_filled(r) for r in reasons)
            or any("视情况而定" in r for r in reasons)):
        add("recommendation", "AI 推荐须指向已比较方案并说明具体理由",
            {"recommendation": recommendation, "reasons": reasons}, section)
    choice = values.get("最终选择", [])
    if (len(choice) != 1 or choice[0] not in names
            or choice[0] != ctx.meta.get("designDecision")):
        add("design-decision", "最终选择须与已记录的 designDecision 一致",
            {"choice": choice, "recorded": ctx.meta.get("designDecision")}, section,
            fix="请用户确定方案，由总控通过 CLI 记录并同步最终选择行")

    section = mdparse.find(root, "current-system")
    paths = [r.get("项目相对路径", "").strip().strip(chr(96)) for r in _rows(section)]
    def file_path(value):
        path = PurePosixPath(value)
        return (_filled(value) and "\\" not in value and not path.is_absolute()
                and ".." not in path.parts and bool(path.suffix))
    if not paths or not all(file_path(value) for value in paths):
        add("impact-paths", "影响面须列出具体项目相对文件路径", paths or "missing-paths", section)
    section = mdparse.find(root, "stress-test")
    expected = ("并发 10 倍", "下游挂掉", "3 个月后扩展", "新人接手")
    stress = _rows(section)
    missing = [name for name in expected
               if not any(r.get("场景", "").strip() == name and _filled(r.get("回答", "")) for r in stress)]
    if missing:
        add("stress-scenarios", "四个压力测试场景都须回答", missing, section)

    try:
        (ctx.change_dir / PROPOSAL).read_text(encoding="utf-8")
        tier, points, reasons = tiering.recommend(ctx.change_dir, "2")
        ranks = {"S": 0, "M": 1, "L": 2}
        if ranks[tier] > ranks[ctx.meta.get("complexity")]:
            add("complexity-upgrade", "复杂度复评建议升至 %s；当前档位保持不变" % tier,
                {"current": ctx.meta.get("complexity"), "recommended": tier,
                 "points": points, "reasons": reasons}, level="WARN",
                fix="请用户确认后由总控通过 CLI 升档")
    except (OSError, UnicodeError, ValueError, KeyError) as exc:
        add("design-readable", "复杂度复评所需工件或档位无法解析", type(exc).__name__)
    return findings
