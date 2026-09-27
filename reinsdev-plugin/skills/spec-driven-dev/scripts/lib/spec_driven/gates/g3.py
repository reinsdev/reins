"""Check Phase 3 behavior and contract evidence. Owner: T3.

Checks:
- spec-readable: require readable spec, proposal and complexity inputs.
- ac-mapped: require every proposal AC to appear in a real scenario.
- scenario-structure: require unique H2 REQs and H3 SCs with WHEN/THEN.
- interface-contract: require all API fields and existing SC references.
- data-model: require schema, indexes, constraints and rollback evidence.
- complexity-upgrade: warn on a higher recommendation without mutating meta.
- openapi-draft: explicitly report the unavailable optional validator.
"""

import json
import re
from typing import List

from . import Finding, GateContext
from .. import mdparse, tiering
from ..project import DESIGN, PROPOSAL, SPEC


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
    return [r for table in mdparse.tables(section.body) for r in table.rows]


def _row_problems(section, fields, scenario_ids):
    rows = _rows(section)
    if not rows:
        return ["missing-table"]
    problems = []
    for row in rows:
        links = mdparse.ids(row.get("关联 SC", ""), "SC")
        missing = {key: row.get(key, "") for key in fields if not _filled(row.get(key, ""))}
        unknown = sorted(set(links) - scenario_ids)
        if missing or not links or unknown:
            problems.append({"row": {key: row.get(key, "") for key in fields[:2]},
                             "fields": missing, "missing-sc": not links, "unknown-sc": unknown})
    return problems


def _unchanged(section):
    return section is not None and section.body.strip().strip("。.") == "本次不变更" and not section.children


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

    def add(name, reason, evidence, section=None, level="BLOCK", fix="按 spec.md 模板补全可核验的行为与契约"):
        findings.append(Finding(
            level, name, reason, SPEC + (":%d" % section.line if section else ""), fix,
            json.dumps(evidence, ensure_ascii=False, sort_keys=True)))

    try:
        spec_text = (ctx.change_dir / SPEC).read_text(encoding="utf-8")
        root = mdparse.parse(spec_text)
        proposal = mdparse.parse((ctx.change_dir / PROPOSAL).read_text(encoding="utf-8"))
    except (OSError, UnicodeError, ValueError) as exc:
        add("spec-readable", "无法读取或解析 spec.md / proposal.md", type(exc).__name__)
        return findings
    unique = {"interface-contract": "interface-contract", "data-model": "data-model",
              "table-structure": "data-model", "indexes": "data-model",
              "constraints": "data-model", "migrations": "data-model"}
    for key, check_name in unique.items():
        matches = [s for s in _sections(root) if mdparse.find(s, key) is s]
        if len(matches) > 1:
            add(check_name, "同一契约章节存在多个标题或别名，无法确认唯一内容",
                {"section": key, "contents": [_section_evidence(s) for s in matches]},
                fix="合并重复章节并保留实际确认内容")
    ac_sections = [s for s in _sections(proposal) if mdparse.find(s, "acceptance-criteria") is s]
    if len(ac_sections) > 1:
        add("ac-mapped", "proposal.md 中存在多个验收标准章节，无法确认完整映射",
            {"duplicate": [_section_evidence(s) for s in ac_sections]}, fix="在 Phase 1 合并验收标准章节，再重新验证")
    reqs = mdparse.find_all(root, mdparse.ID_PATTERNS["REQ"])
    scenarios = mdparse.find_all(root, mdparse.ID_PATTERNS["SC"])
    req_ids = [(mdparse.ids(s.title, "REQ") or [""])[0] for s in reqs]
    sc_ids = [(mdparse.ids(s.title, "SC") or [""])[0] for s in scenarios]
    invalid = []
    for req, identifier in zip(reqs, req_ids):
        if not identifier or req.level != 2 or not req.title.startswith(identifier):
            invalid.append({"req": identifier, "level": req.level})
    for section, identifier in zip(scenarios, sc_ids):
        parents = [req for req in reqs if section in req.children]
        clauses = {}
        for line in _visible_lines(section.body):
            words = line.strip().split(None, 1)
            if words and words[0] in ("WHEN", "THEN"):
                clauses.setdefault(words[0], []).append(words[1] if len(words) > 1 else "")
        if (not identifier or section.level != 3 or not section.title.startswith(identifier) or len(parents) != 1
                or parents[0].level != 2
                or any(not clauses.get(key) or not all(_filled(v) for v in clauses[key])
                       for key in ("WHEN", "THEN"))):
            invalid.append({"sc": identifier, "level": section.level,
                            "parent": [r.title for r in parents], "clauses": clauses})
    if (not reqs or not scenarios or len(req_ids) != len(set(req_ids))
            or len(sc_ids) != len(set(sc_ids)) or invalid):
        add("scenario-structure", "REQ 须为 H2、SC 须为其 H3 子节，编号唯一且 WHEN/THEN 完整",
            {"invalid": invalid, "reqs": req_ids, "scenarios": sc_ids})

    ac_section = mdparse.find(proposal, "acceptance-criteria")
    ac_rows = _rows(ac_section)
    ac_ids = [r.get("AC", "").strip() for r in ac_rows]
    invalid_ac = [ac for ac in ac_ids if not (
        mdparse.ids(ac, "AC") == [ac] or (ctx.meta.get("mode") == "bugfix" and ac == "AC-regression"))]
    mapped = set()
    for section in scenarios:
        mapped.update(mdparse.ids(section.body, "AC"))
        # AC-regression is the one fixed non-numeric ID in the template.
        if any("AC-regression" in line.replace("、", " ").replace(",", " ").split()
               for line in _visible_lines(section.body.replace("：", " ").replace(":", " "))):
            mapped.add("AC-regression")
    missing = sorted(set(ac_ids) - mapped)
    if not ac_ids or missing or invalid_ac:
        add("ac-mapped", "proposal.md 每条 AC 至少须关联一个 SC",
            {"missing": missing, "invalid": invalid_ac, "empty": not ac_ids})

    section = mdparse.find(root, "interface-contract")
    fields = ("Method", "Path", "请求字段", "响应字段", "错误码", "幂等性", "限流")
    problems = _row_problems(section, fields, set(sc_ids))
    if not _unchanged(section) and problems:
        add("interface-contract", "接口契约须填全 Method/Path、请求响应、错误码、幂等性、限流并引用 SC",
            problems, section)

    section = mdparse.find(root, "data-model")
    if not _unchanged(section):
        required = {
            "table-structure": ("表", "字段", "类型", "可空", "默认值", "含义"),
            "indexes": ("表", "索引", "字段顺序", "唯一性", "用途"),
            "constraints": ("表", "约束", "规则"),
            "migrations": ("迁移脚本", "回滚脚本", "执行顺序", "数据兼容与风险"),
        }
        missing_sections = []
        for key, columns in required.items():
            child = mdparse.find(section, key) if section else None
            problems = _row_problems(child, columns, set(sc_ids))
            if problems:
                missing_sections.append((key, problems))
        if missing_sections:
            add("data-model", "数据模型须填全表结构、索引、约束、迁移及回滚，并引用 SC",
                missing_sections, section)

    try:
        if not (ctx.meta.get("skipped") or {}).get("2"):
            (ctx.change_dir / DESIGN).read_text(encoding="utf-8")
        tier, points, reasons = tiering.recommend(ctx.change_dir, "3")
        ranks = {"S": 0, "M": 1, "L": 2}
        if ranks[tier] > ranks[ctx.meta.get("complexity")]:
            add("complexity-upgrade", "复杂度复评建议升至 %s；当前档位保持不变" % tier,
                {"current": ctx.meta.get("complexity"), "recommended": tier,
                 "points": points, "reasons": reasons}, level="WARN",
                fix="请用户确认后由总控通过 CLI 升档")
    except (OSError, UnicodeError, ValueError, KeyError) as exc:
        add("spec-readable", "复杂度复评所需工件或档位无法解析", type(exc).__name__)
    openapi = ctx.config.get("openapi", {})
    if not isinstance(openapi, dict):
        add("openapi-draft", "OpenAPI 配置须为对象，无法确认校验策略",
            {"invalid-config": openapi}, fix="请修正 openapi 配置后重跑验证门")
    elif openapi.get("enabled"):
        # No public validator contract exists yet; never claim a draft passed.
        level = "WARN" if openapi.get("gate_on_draft", "warn") == "warn" else "BLOCK"
        add("openapi-draft", "已启用 OpenAPI 草稿校验，但当前尚无可用的校验接口",
            "openapi-validator-unavailable", level=level,
            fix="请协调者接入 OpenAPI 草稿校验接口；当前不能确认草稿合格")
    return findings
