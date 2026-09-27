"""Check Phase 1 proposal evidence. Owner: T3.

Checks:
- proposal-readable: require a readable proposal.
- user-stories: require at least one filled user story.
- story-ac: require a valid AC for every story and reject orphan ACs.
- out-of-scope: require an explicit scope exclusion.
- ambiguities-resolved: require answered, typed and confirmed ambiguity rows.
- business-source: only the user can supply business values (locked).
- field-mapping: require confirmed mappings or an explicit absence (locked).
- affected-modules: require the affected module list.
- tier-confirmed: require the user-confirmed tier (locked).
- bugfix-analysis: require the five populated bugfix analysis sections.
- bugfix-reviewed: reject the automatic draft marker (locked).
- bugfix-ac-steps: require verification steps for every bugfix AC.
- bugfix-regression: require the regression acceptance criterion.
"""

import json
import re
from typing import List

from . import Finding, GateContext
from .. import mdparse
from ..project import BUGFIX_ANALYSIS, PROPOSAL


def _filled(value):
    value = value.strip().strip("`* ")
    return bool(value and not re.search(r"<[^>\n]+>", value)
                and value not in ("待确认", "待补充", "未答", "TODO", "TBD", "-", "…"))


def _body(section):
    if section is None:
        return ""
    return section.body + "".join(_body(child) for child in section.children)


def _rows(section):
    return [row for table in mdparse.tables(_body(section)) for row in table.rows]


def _explicit_none(text):
    return text.strip().strip("。.") in ("无", "本次无字段映射")


def _content(section):
    text = _body(section)
    tables = mdparse.tables(text)
    if tables:
        return any(all(_filled(v) for v in row.values()) for t in tables for row in t.rows)
    return any(_filled(line) for line in text.splitlines()
               if line.strip() and not line.strip().startswith(("<!--", "```", "~~~")))


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

    def add(name, reason, evidence, section=None, locked=False, file=PROPOSAL, fix="按 T1 模板补全实际内容"):
        location = file + (":%d" % section.line if section is not None else "")
        findings.append(Finding("BLOCK", name, reason, location, fix,
                                json.dumps(evidence, ensure_ascii=False, sort_keys=True), locked))

    try:
        text = (ctx.change_dir / PROPOSAL).read_text(encoding="utf-8")
        root = mdparse.parse(text)
    except (OSError, UnicodeError, ValueError) as exc:
        add("proposal-readable", "无法读取或解析 proposal.md", type(exc).__name__)
        return findings


    unique = {"user-stories": "user-stories", "acceptance-criteria": "story-ac",
              "out-of-scope": "out-of-scope", "ambiguities": "business-source",
              "field-mapping": "field-mapping", "affected-modules": "affected-modules"}
    for key, check_name in unique.items():
        matches = [s for s in _sections(root) if mdparse.find(s, key) is s]
        if len(matches) > 1:
            add(check_name, "同一章节存在多个标题或别名，无法确认唯一内容",
                {"section": key, "contents": [_section_evidence(s) for s in matches]},
                locked=key in ("ambiguities", "field-mapping"), fix="合并重复章节并保留实际确认内容")

    story_section = mdparse.find(root, "user-stories")
    stories = []
    malformed = []
    for line in _body(story_section).splitlines():
        if not line.strip():
            continue
        value = line.strip().lstrip("-* ").replace(":", "：", 1)
        label, sep, narrative = value.partition("：")
        if sep and _filled(label) and _filled(narrative):
            stories.append(label.strip())
        else:
            malformed.append(value)
    if not stories or malformed or len(stories) != len(set(stories)):
        add("user-stories", "至少填写一条编号唯一的用户故事", malformed or stories, story_section)

    ac_section = mdparse.find(root, "acceptance-criteria")
    ac_rows = _rows(ac_section)
    valid_ac = []
    invalid_ac = []
    seen = set()
    for row in ac_rows:
        ac = row.get("AC", "").strip()
        is_id = mdparse.ids(ac, "AC") == [ac] or (ctx.meta.get("mode") == "bugfix" and ac == "AC-regression")
        if (not is_id or ac in seen or row.get("用户故事", "").strip() not in stories
                or not _filled(row.get("验收标准", ""))):
            invalid_ac.append(row)
        else:
            valid_ac.append(row)
        seen.add(ac)
    missing = sorted(set(stories) - {r.get("用户故事", "").strip() for r in valid_ac})
    if not valid_ac or missing or invalid_ac:
        add("story-ac", "每条用户故事须有有效 AC，AC 编号不能重复或引用未知故事",
            {"missing": missing, "invalid": invalid_ac}, ac_section)

    section = mdparse.find(root, "out-of-scope")
    if not _content(section):
        add("out-of-scope", "Out of Scope 必须显式声明", "missing-scope", section)

    section = mdparse.find(root, "ambiguities")
    rows = [r for s in _sections(root) if mdparse.find(s, "ambiguities") is s for r in _rows(s)]
    unresolved = [r for r in rows if (not _filled(r.get("问题", ""))
                  or not _filled(r.get("影响范围", "")) or not _filled(r.get("回答", ""))
                  or not _filled(r.get("来源", "")) or r.get("状态", "").strip() != "✅"
                  or r.get("类型", "").strip() not in ("业务取值", "安全默认"))]
    if unresolved or (not rows and not _explicit_none(_body(section))):
        add("ambiguities-resolved", "歧义须逐条填写类型、回答、来源并标注 ✅，没有歧义时写无",
            unresolved or "missing-ambiguities", section)
    nonuser = [r for r in rows if r.get("类型", "").strip() == "业务取值"
               and r.get("来源", "").strip() != "用户"]
    if nonuser:
        add("business-source", "业务取值来源必须为用户", nonuser, section, locked=True,
            fix="请用户回答实际业务取值并记录来源")

    mapping = mdparse.find(root, "field-mapping")
    mapping_rows = [r for s in _sections(root) if mdparse.find(s, "field-mapping") is s for r in _rows(s)]
    # Exclude the mapping heading and its absence declaration from keyword detection.
    def surrounding(section):
        if section is mapping:
            return ""
        return section.body + "".join(surrounding(child) for child in section.children)
    triggered = any(word in surrounding(root) for word in ("字段映射", "文件格式", "转换器", "固定值"))
    bad_mapping = [r for r in mapping_rows if (
        any(not _filled(r.get(key, "")) for key in ("源字段", "目标字段", "转换规则或固定值"))
        or r.get("来源", "").strip() != "用户确认")]
    if bad_mapping or (not mapping_rows and (triggered or not _explicit_none(_body(mapping)))):
        add("field-mapping", "字段映射须填写完整并由用户确认；无映射时显式声明",
            bad_mapping or {"triggered": triggered, "missing": True}, mapping, locked=True,
            fix="请用户确认映射；确无映射时写本次无字段映射")

    section = mdparse.find(root, "affected-modules")
    if not _content(section):
        add("affected-modules", "请列出影响的现有模块", "missing-modules", section)
    if ctx.meta.get("tierConfirmed") is not True or ctx.meta.get("complexity") not in ("S", "M", "L"):
        add("tier-confirmed", "复杂度档位尚未经用户确认",
            {"confirmed": ctx.meta.get("tierConfirmed"), "tier": ctx.meta.get("complexity")},
            locked=True, file=".meta.json", fix="请用户确认档位后由总控通过 CLI 记录")

    if ctx.meta.get("mode") == "bugfix":
        try:
            analysis = mdparse.parse((ctx.change_dir / BUGFIX_ANALYSIS).read_text(encoding="utf-8"))
            missing = [key for key in ("basic-info", "evidence", "root-cause", "fix-plan", "impact")
                       if not _content(mdparse.find(analysis, key))]
        except (OSError, UnicodeError, ValueError) as exc:
            missing = [type(exc).__name__]
        if missing:
            add("bugfix-analysis", "bugfix-analysis.md 缺少可读取且已填写的五大节",
                missing, file=BUGFIX_ANALYSIS)
        if "AUTO-DRAFTED" in text:
            add("bugfix-reviewed", "proposal.md 仍带 AUTO-DRAFTED 草稿标志",
                "AUTO-DRAFTED", locked=True, fix="请用户 review 并补全后删除草稿标志")
        no_steps = [r.get("AC", "") for r in ac_rows if not _filled(r.get("验证步骤", ""))]
        if not ac_rows or no_steps:
            add("bugfix-ac-steps", "bugfix 每条 AC 都须填写验证步骤", no_steps or "missing-ac", ac_section)
        if "AC-regression" not in [r.get("AC", "").strip() for r in valid_ac]:
            add("bugfix-regression", "bugfix 必须包含 AC-regression", "AC-regression", ac_section)
    return findings
